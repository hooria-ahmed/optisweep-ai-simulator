"""System integration for OptiSweep AI.

``execute_schedule`` is the CS-323 CEP notebook function (Section 4).  The
rest of the module packages a whole mission (load -> CSP -> navigation) into a
:class:`MissionPlan` that the game replays.  Everything in a plan comes from
running the real algorithms; the GUI only animates it.
"""
import time
from dataclasses import dataclass, field

from .environment import (InputError, load_environment_checked, load_schedule_checked,
                          unreachable_dirty)
from .graph_search import search
from .csp_scheduler import backtracking_search, slot_to_int

ALGORITHMS = ("BFS", "A*")


# ==============================================================================
# SECTION 4: SYSTEM INTEGRATION (Section 7.2 Required Signature)
# ==============================================================================

def execute_schedule(grid, charging_station, schedule, algorithm="A*"):
    """
    Executes the CSP-generated schedule using graph-based search.
    Returns complete_path, total_cost, and success status.
    """
    if not schedule:
        print("Integration Failure: Cannot execute an empty or infeasible CSP schedule.")
        return [], 0, False

    # Normalize schedule into an ordered list of (task_label, time_slot)
    if isinstance(schedule, dict):
        ordered_tasks = sorted(schedule.items(), key=lambda x: slot_to_int(x[1]))
    elif isinstance(schedule, list) and isinstance(schedule[0], tuple):
        if schedule[0][0].startswith("D"):
            ordered_tasks = sorted(schedule, key=lambda x: slot_to_int(x[1]))
        else:
            ordered_tasks = [(task, slot) for slot, task in sorted(schedule, key=lambda x: slot_to_int(x[0]))]
    else:
        ordered_tasks = [(task, f"T{i+1}") for i, task in enumerate(schedule)]

    current_pos = charging_station
    complete_path = [current_pos]
    total_cost = 0
    total_nodes_expanded = 0
    cleaned_locations = set()

    # Visit each dirty location in scheduled order
    for step_idx, (task_label, slot_label) in enumerate(ordered_tasks, 1):
        target_pos = grid.dirty_locations[task_label]
        leg_path, leg_cost, nodes_exp = search(grid, current_pos, target_pos, algorithm)
        total_nodes_expanded += nodes_exp

        if leg_path is None:
            print(f"  [FAILURE] Step {step_idx} ({slot_label}): No valid path found from {current_pos} to {task_label} at {target_pos}!")
            return complete_path, total_cost, False

        # Append path avoiding duplicate shared endpoints
        complete_path.extend(leg_path[1:])
        total_cost += leg_cost
        current_pos = target_pos
        cleaned_locations.add(task_label)

    # Return to charging station after cleaning all locations
    ret_path, ret_cost, ret_nodes = search(grid, current_pos, charging_station, algorithm)
    total_nodes_expanded += ret_nodes

    if ret_path is None:
        print(f"  [FAILURE] Return Leg: No valid path found from {current_pos} back to Charging Station {charging_station}!")
        return complete_path, total_cost, False

    complete_path.extend(ret_path[1:])
    total_cost += ret_cost

    success = (len(cleaned_locations) == len(grid.dirty_locations)) and (complete_path[-1] == charging_station)

    return complete_path, total_cost, success


# ==============================================================================
# MISSION PLANNING FOR THE GAME
# ==============================================================================

class TraceRecorder:
    """Collects ``trace(event, **data)`` calls into a list of (event, data)."""
    def __init__(self):
        self.events = []

    def __call__(self, event, **data):
        self.events.append((event, data))


def time_search(grid, start, goal, algorithm, repeats=25):
    """Mean wall-clock time (seconds) of the untraced ``search`` call."""
    t0 = time.perf_counter()
    for _ in range(repeats):
        search(grid, start, goal, algorithm)
    return (time.perf_counter() - t0) / repeats


@dataclass
class SearchRun:
    """One real execution of BFS or A* on one navigation problem."""
    algorithm: str
    start: tuple
    goal: tuple
    path: list            # None when no path exists
    cost: float
    nodes_expanded: int
    seconds: float        # mean time of the untraced search
    events: list          # trace of the algorithm's actual steps

    @property
    def found(self):
        return self.path is not None

    @property
    def path_length(self):
        """Number of cells on the path (cost + 1), 0 when there is none."""
        return len(self.path) if self.path else 0


def run_search(grid, start, goal, algorithm, repeats=25):
    """Run ``search`` once with tracing (for visualisation) and time the
    untraced call (for honest execution-time figures)."""
    rec = TraceRecorder()
    path, cost, nodes = search(grid, start, goal, algorithm, trace=rec)
    seconds = time_search(grid, start, goal, algorithm, repeats)
    return SearchRun(algorithm, start, goal, path, cost, nodes, seconds, rec.events)


def compare_algorithms(grid, start, goal, repeats=25):
    """Run BFS and A* on the identical problem.  Returns {'BFS': run, 'A*': run}."""
    return {algo: run_search(grid, start, goal, algo, repeats) for algo in ALGORITHMS}


def comparison_summary(bfs, astar):
    """Sentences describing a BFS / A* comparison, derived from the results."""
    lines = []
    if not bfs.found and not astar.found:
        lines.append("Neither algorithm found a path: the destination is unreachable.")
        lines.append(f"BFS exhausted {bfs.nodes_expanded} nodes and A* exhausted "
                     f"{astar.nodes_expanded} before giving up.")
        return lines
    if bfs.nodes_expanded > astar.nodes_expanded:
        saved = bfs.nodes_expanded - astar.nodes_expanded
        pct = 100.0 * saved / bfs.nodes_expanded
        lines.append(f"BFS explored more nodes ({bfs.nodes_expanded} vs {astar.nodes_expanded}).")
        lines.append(f"A* expanded {saved} fewer nodes ({pct:.0f}% less) using its Manhattan heuristic.")
    elif bfs.nodes_expanded < astar.nodes_expanded:
        lines.append(f"A* expanded more nodes here ({astar.nodes_expanded} vs {bfs.nodes_expanded}): "
                     "many cells tie on f(n), and BFS stops as soon as it generates the goal.")
    else:
        lines.append(f"Both algorithms expanded the same number of nodes ({bfs.nodes_expanded}).")
    if bfs.cost == astar.cost:
        lines.append(f"Both found paths with equal cost ({bfs.cost} moves), so both are optimal.")
    elif bfs.cost < astar.cost:
        lines.append(f"BFS found a cheaper path ({bfs.cost} vs {astar.cost} moves).")
    else:
        lines.append(f"A* found a cheaper path ({astar.cost} vs {bfs.cost} moves).")
    if bfs.seconds > 0 and astar.seconds > 0:
        if astar.seconds < bfs.seconds:
            lines.append(f"A* ran {bfs.seconds / astar.seconds:.1f}x faster "
                         f"({astar.seconds * 1e6:.0f} us vs {bfs.seconds * 1e6:.0f} us).")
        else:
            lines.append(f"BFS ran {astar.seconds / bfs.seconds:.1f}x faster "
                         f"({bfs.seconds * 1e6:.0f} us vs {astar.seconds * 1e6:.0f} us): "
                         "its queue operations are cheaper per node than A*'s heap.")
    return lines


@dataclass
class Leg:
    """One navigation leg of the mission (C->D.., D..->D.., D..->C)."""
    index: int
    start_label: str
    goal_label: str
    slot: str             # time slot of the goal task ('' for the return leg)
    runs: dict            # {'BFS': SearchRun, 'A*': SearchRun}

    @property
    def name(self):
        return f"{self.start_label} > {self.goal_label}"


@dataclass
class MissionPlan:
    env_path: str
    sched_path: str
    algorithm: str
    grid: object
    variables: list
    domains: dict
    constraints: dict
    csp_events: list
    csp_seconds: float
    assignment: dict                     # None when the CSP is infeasible
    ordered_schedule: list = field(default_factory=list)   # [(task, slot)] by slot
    legs: list = field(default_factory=list)               # legs actually attempted
    complete_path: list = field(default_factory=list)      # from execute_schedule
    total_cost: float = 0
    success: bool = False
    status: str = "ok"                   # ok | infeasible | unreachable
    failure_reason: str = ""
    unreachable: list = field(default_factory=list)        # labels cut off from the charger

    def run(self, leg, algorithm=None):
        return leg.runs[algorithm or self.algorithm]

    def total_nodes(self, algorithm=None):
        return sum(self.run(leg, algorithm).nodes_expanded for leg in self.legs)

    def total_seconds(self, algorithm=None):
        return sum(self.run(leg, algorithm).seconds for leg in self.legs)

    def total_cost_of(self, algorithm=None):
        return sum(self.run(leg, algorithm).cost for leg in self.legs
                   if self.run(leg, algorithm).found)


def plan_mission(env_path, sched_path, algorithm="A*", repeats=25):
    """Load the inputs, solve the CSP and plan every navigation leg.

    Raises :class:`InputError` for unusable input files.  Infeasible schedules
    and unreachable destinations are *results*, reported through
    ``plan.status`` / ``plan.failure_reason`` with ``plan.success`` False.
    """
    algorithm = "BFS" if algorithm.upper().strip() == "BFS" else "A*"
    grid = load_environment_checked(env_path)
    variables, domains, constraints = load_schedule_checked(sched_path, grid.dirty_locations.keys())

    rec = TraceRecorder()
    assignment = backtracking_search(variables, domains, constraints, trace=rec)
    t0 = time.perf_counter()
    backtracking_search(variables, domains, constraints)      # untraced, for timing
    csp_seconds = time.perf_counter() - t0

    plan = MissionPlan(env_path, sched_path, algorithm, grid, variables, domains,
                       constraints, rec.events, csp_seconds, assignment,
                       unreachable=unreachable_dirty(grid))

    if assignment is None:
        plan.status = "infeasible"
        slots, tasks = len(constraints["time_slots"]), len(variables)
        if slots < tasks:
            plan.failure_reason = (f"Insufficient time slots: {tasks} cleaning tasks but only "
                                   f"{slots} time slots are available.")
        else:
            plan.failure_reason = ("No feasible cleaning schedule exists: the precedence and "
                                   "latest-slot constraints contradict each other.")
        return plan

    plan.ordered_schedule = sorted(assignment.items(), key=lambda item: slot_to_int(item[1]))

    # The authoritative journey comes from the original integration function.
    plan.complete_path, plan.total_cost, plan.success = execute_schedule(
        grid, grid.charging_station, plan.ordered_schedule, algorithm=algorithm)

    # Per-leg runs of both algorithms (identical inputs) for replay and analytics.
    waypoints = ([("C", grid.charging_station, "")]
                 + [(task, grid.dirty_locations[task], slot) for task, slot in plan.ordered_schedule]
                 + [("C", grid.charging_station, "")])
    for i in range(len(waypoints) - 1):
        (s_lbl, s_pos, _), (g_lbl, g_pos, g_slot) = waypoints[i], waypoints[i + 1]
        leg = Leg(i, s_lbl, g_lbl, g_slot, compare_algorithms(grid, s_pos, g_pos, repeats))
        plan.legs.append(leg)
        if not leg.runs[algorithm].found:
            plan.status = "unreachable"
            target = (f"{g_lbl} at {g_pos}" if g_lbl != "C" else f"the charging station at {g_pos}")
            plan.failure_reason = (f"Navigation failure on leg {s_lbl} > {g_lbl}: "
                                   f"{algorithm} found no path from {s_pos} to {target}.")
            break

    # Cross-check the replay data against execute_schedule's own result.
    replay = [grid.charging_station]
    for leg in plan.legs:
        run = leg.runs[algorithm]
        if run.found:
            replay.extend(run.path[1:])
    if replay != plan.complete_path or (plan.status == "ok") != plan.success:
        raise RuntimeError("Internal error: replay data disagrees with execute_schedule().")
    return plan
