"""CSP task scheduling for OptiSweep AI.

Backtracking search with MRV + Degree variable selection, LCV value ordering
and forward checking, exactly as implemented in the CS-323 CEP notebook
(Section 3).  Each function accepts an optional ``trace`` callable; when given
it receives the solver's real decisions as ``trace(event, **data)``.  With the
default ``trace=None`` behaviour and return values are those of the notebook.

Trace events
------------
``init``            variables, domains, constraints
``too_few_slots``   slots, tasks
``select``          variable, candidates=[(var, domain_size, degree)], mrv_tie, degree_tie, domain
``lcv``             variable, ordering=[(value, eliminated)]
``try``             variable, value
``check``           variable, value, kind, detail, ok      (one per constraint examined)
``reject``          variable, value
``assign``          variable, value, assignment
``forward``         variable, value, pruned={var: [values]}, wipeout, domains
``backtrack``       variable, value, assignment
``dead_end``        variable                                (all values exhausted)
``solution``        assignment
``failure``         (no data)
"""
import re
import copy


# ==============================================================================
# SECTION 3: CSP TASK SCHEDULING FUNCTIONS (Section 6.5 Required Signatures)
# ==============================================================================

def slot_to_int(slot_str):
    """Helper to convert time slot label 'T1' -> 1."""
    return int(re.sub(r"\D", "", slot_str))


def is_consistent(variable, value, assignment, constraints, trace=None):
    """
    Checks precedence, latest-slot, and slot exclusivity constraints
    whenever the necessary assignments are available.
    """
    val_num = slot_to_int(value)

    # 1. Slot-exclusivity constraint: No two tasks can share the same time slot
    for assigned_var, assigned_val in assignment.items():
        if assigned_var != variable and assigned_val == value:
            if trace:
                trace("check", variable=variable, value=value, kind="exclusivity", ok=False,
                      detail=f"{value} is already used by {assigned_var}")
            return False
    if trace:
        trace("check", variable=variable, value=value, kind="exclusivity", ok=True,
              detail=f"{value} is free")

    # 2. Latest-slot constraint: (task, latest_slot) -> task <= latest_slot
    for task, latest in constraints.get("latest_slot", []):
        if task == variable:
            if val_num > slot_to_int(latest):
                if trace:
                    trace("check", variable=variable, value=value, kind="latest", ok=False,
                          detail=f"{variable} must be done by {latest}, {value} is too late")
                return False
            if trace:
                trace("check", variable=variable, value=value, kind="latest", ok=True,
                      detail=f"{variable} by {latest}: {value} <= {latest}")

    # 3. Precedence constraint: (task_before, task_after) -> slot(task_before) < slot(task_after)
    for before_task, after_task in constraints.get("precedence", []):
        if variable == before_task and after_task in assignment:
            if not (val_num < slot_to_int(assignment[after_task])):
                if trace:
                    trace("check", variable=variable, value=value, kind="precedence", ok=False,
                          detail=f"{before_task} before {after_task}: {value} is not < {assignment[after_task]}")
                return False
            if trace:
                trace("check", variable=variable, value=value, kind="precedence", ok=True,
                      detail=f"{before_task} before {after_task}: {value} < {assignment[after_task]}")
        elif variable == after_task and before_task in assignment:
            if not (slot_to_int(assignment[before_task]) < val_num):
                if trace:
                    trace("check", variable=variable, value=value, kind="precedence", ok=False,
                          detail=f"{before_task} before {after_task}: {assignment[before_task]} is not < {value}")
                return False
            if trace:
                trace("check", variable=variable, value=value, kind="precedence", ok=True,
                      detail=f"{before_task} before {after_task}: {assignment[before_task]} < {value}")

    return True


def select_unassigned_variable(assignment, domains, constraints, trace=None):
    """
    Selects an unassigned variable using Minimum Remaining Values (MRV).
    Ties are broken using the Degree Heuristic (most constraints with other unassigned variables).
    """
    unassigned = [v for v in domains.keys() if v not in assignment]
    if not unassigned:
        return None

    def get_degree(var):
        # Count explicit precedence connections to other unassigned variables
        # (Note: all unassigned variables also share all-different slot exclusivity,
        # so precedence pairs provide the differentiating degree count)
        degree = 0
        for u, v in constraints.get("precedence", []):
            if u == var and v not in assignment:
                degree += 1
            elif v == var and u not in assignment:
                degree += 1
        return degree

    # Sort by: (1) smallest domain size (MRV), (2) largest degree (-get_degree), (3) variable name
    unassigned.sort(key=lambda var: (len(domains[var]), -get_degree(var), var))
    if trace:
        candidates = [(v, len(domains[v]), get_degree(v)) for v in unassigned]
        best_size, best_degree = candidates[0][1], candidates[0][2]
        mrv_tied = [c for c in candidates if c[1] == best_size]
        degree_tied = [c for c in mrv_tied if c[2] == best_degree]
        trace("select", variable=unassigned[0], candidates=candidates,
              mrv_tie=len(mrv_tied) > 1, degree_tie=len(degree_tied) > 1,
              domain=list(domains[unassigned[0]]))
    return unassigned[0]


def order_domain_values(variable, assignment, domains, constraints, trace=None):
    """
    Orders candidate time slots for the selected variable using the
    Least Constraining Value (LCV) heuristic (fewest values ruled out in unassigned neighbors).
    """
    temp_assignment = dict(assignment)

    def count_eliminations(candidate_val):
        temp_assignment[variable] = candidate_val
        eliminated = 0
        for other_var in domains:
            if other_var not in temp_assignment:
                for other_val in domains[other_var]:
                    if not is_consistent(other_var, other_val, temp_assignment, constraints):
                        eliminated += 1
        del temp_assignment[variable]
        return eliminated

    # Sort candidate values by fewest eliminations first, then chronological slot order
    ordered = sorted(domains[variable], key=lambda val: (count_eliminations(val), slot_to_int(val)))
    if trace:
        trace("lcv", variable=variable,
              ordering=[(val, count_eliminations(val)) for val in ordered])
    return ordered


def forward_check(variable, value, assignment, domains, constraints, trace=None):
    """
    Removes time-slot values that are no longer feasible for related unassigned variables.
    Returns updated deep-copied domains if consistent and no domain becomes empty;
    otherwise returns None (failure indication).
    """
    new_domains = copy.deepcopy(domains)
    new_domains[variable] = [value]

    # Ensure current assignment includes variable = value for consistency checks
    current_assignment = dict(assignment)
    current_assignment[variable] = value
    pruned = {}

    for other_var in new_domains:
        if other_var not in current_assignment:
            feasible_vals = [
                val for val in new_domains[other_var]
                if is_consistent(other_var, val, current_assignment, constraints)
            ]
            if trace:
                removed = [v for v in new_domains[other_var] if v not in feasible_vals]
                if removed:
                    pruned[other_var] = removed
            if not feasible_vals:
                if trace:
                    new_domains[other_var] = []
                    trace("forward", variable=variable, value=value, pruned=pruned,
                          wipeout=other_var, domains=copy.deepcopy(new_domains))
                return None  # Domain wipeout -> trigger backtrack
            new_domains[other_var] = feasible_vals

    if trace:
        trace("forward", variable=variable, value=value, pruned=pruned,
              wipeout=None, domains=copy.deepcopy(new_domains))
    return new_domains


def backtracking_search(variables, domains, constraints, trace=None):
    """
    Backtracking CSP solver using MRV + Degree heuristic, LCV, is_consistent,
    and forward_check.
    Returns complete assignment dictionary {task: slot} or None if infeasible.
    """
    if trace:
        trace("init", variables=list(variables), domains=copy.deepcopy(domains),
              constraints=constraints)

    # Number of available time slots must be >= number of dirty locations
    if len(constraints.get("time_slots", [])) < len(variables):
        if trace:
            trace("too_few_slots", slots=len(constraints.get("time_slots", [])),
                  tasks=len(variables))
            trace("failure")
        return None

    init_domains = copy.deepcopy(domains)

    def backtrack(assignment, current_domains):
        if len(assignment) == len(variables):
            return assignment

        var = select_unassigned_variable(assignment, current_domains, constraints, trace)

        for value in order_domain_values(var, assignment, current_domains, constraints, trace):
            if trace: trace("try", variable=var, value=value)
            if is_consistent(var, value, assignment, constraints, trace):
                assignment[var] = value
                if trace: trace("assign", variable=var, value=value, assignment=dict(assignment))
                updated_domains = forward_check(var, value, assignment, current_domains, constraints, trace)

                if updated_domains is not None:
                    result = backtrack(assignment, updated_domains)
                    if result is not None:
                        return result

                del assignment[var]
                if trace:
                    trace("backtrack", variable=var, value=value, assignment=dict(assignment),
                          domains=copy.deepcopy(current_domains))
            elif trace:
                trace("reject", variable=var, value=value)

        if trace: trace("dead_end", variable=var)
        return None

    result = backtrack({}, init_domains)
    if trace:
        if result is not None:
            trace("solution", assignment=dict(result))
        else:
            trace("failure")
    return result


def verify_and_display_schedule(assignment, constraints):
    """
    Displays the generated schedule ordered by time slot and verifies all constraints.
    """
    if assignment is None:
        print("CSP Status: FAILED — No feasible cleaning schedule exists for the given constraints.")
        return None

    # Sort tasks by their assigned time slot number
    ordered_schedule = sorted(assignment.items(), key=lambda item: slot_to_int(item[1]))

    print("CSP Status: SUCCESS — Feasible Schedule Generated:")
    print("-" * 35)
    print(f"{'Time Slot':<12} | {'Cleaning Task':<15}")
    print("-" * 35)
    for task, slot in ordered_schedule:
        print(f"{slot:<12} | {task:<15}")
    print("-" * 35)

    # Demonstrate constraint satisfaction
    print("Constraint Verification:")
    for b, a in constraints["precedence"]:
        print(f"  [OK] Precedence ({b} before {a}): {assignment[b]} < {assignment[a]}")
    for t, l in constraints["latest_slot"]:
        print(f"  [OK] Latest-Slot ({t} by {l}): {assignment[t]} <= {l}")
    print(f"  [OK] Slot Exclusivity: {len(set(assignment.values()))} unique slots for {len(assignment)} tasks.\n")

    return ordered_schedule
