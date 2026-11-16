"""Graph-based search (BFS and A*) for OptiSweep AI.

The functions are the ones from the CS-323 CEP notebook (Section 2).  The only
addition is the optional ``trace`` argument of :func:`search`: when a callable
is supplied it is told about every real step the algorithm takes (expansions,
pushes, goal tests...) so the GUI can visualise the search.  With the default
``trace=None`` the code path, the results and the return values are exactly
those of the notebook.
"""
from collections import deque
import heapq


# ==============================================================================
# SECTION 2: GRAPH-BASED SEARCH FUNCTIONS (Section 5.5 Required Signatures)
# ==============================================================================

def get_successors(state, grid):
    """
    Find all valid successor states without including cells outside the grid or obstacles.
    Returns: A list of valid successors, each as (next_state, action, step_cost).
    """
    r, c = state
    directions = [
        ((-1, 0), "UP"),
        ((1, 0),  "DOWN"),
        ((0, -1), "LEFT"),
        ((0, 1),  "RIGHT")
    ]
    successors = []
    for (dr, dc), action in directions:
        nr, nc = r + dr, c + dc
        if grid.is_valid_cell(nr, nc):
            successors.append(((nr, nc), action, 1))
    return successors


def goal_test(state, goal_state):
    """
    Checks whether the goal has been reached.
    """
    return state == goal_state


def path_cost(path):
    """
    Calculates the total cost of a path.
    Handles empty paths and single-state paths appropriately.
    """
    if not path or len(path) <= 1:
        return 0
    return len(path) - 1


def heuristic(state, goal_state):
    """
    Manhattan distance heuristic for 4-directional movement:
    h(n) = |row_n - row_goal| + |col_n - col_goal|
    """
    return abs(state[0] - goal_state[0]) + abs(state[1] - goal_state[1])


def search(grid, start, goal, algorithm="A*", trace=None):
    """
    Implements the selected graph-search algorithm ('BFS' or 'A*').
    Returns: (path, cost, nodes_expanded)
    If no path exists, returns (None, float('inf'), nodes_expanded).

    ``trace`` (optional) is called as ``trace(event, **data)`` for each step:

    ============  ==============================================================
    event         data
    ============  ==============================================================
    ``start``     algorithm, start, goal, h (A* only)
    ``invalid``   start, goal                       (blocked / outside grid)
    ``trivial``   state                             (start is the goal)
    ``expand``    state, depth | g/h/f, frontier (size after the pop), order
    ``generate``  parent, state, action, depth | g/h/f, frontier
    ``seen``      parent, state                     (successor not enqueued)
    ``stale``     state, g                          (A* skips an outdated entry)
    ``goal``      state, depth | g
    ``path``      path, cost, nodes_expanded
    ``fail``      nodes_expanded                    (frontier exhausted)
    ============  ==============================================================
    """
    # Validate start and goal
    if not grid.is_valid_cell(*start) or not grid.is_valid_cell(*goal):
        if trace: trace("invalid", start=start, goal=goal)
        return None, float("inf"), 0

    # Trivial case: start equals goal
    if goal_test(start, goal):
        if trace: trace("trivial", state=start)
        return [start], 0, 0

    algo = algorithm.upper().strip()
    nodes_expanded = 0

    if algo == "BFS":
        # Uninformed Graph Search: FIFO Queue
        frontier = deque([(start, [start])])
        visited = {start}
        if trace: trace("start", algorithm="BFS", start=start, goal=goal)

        while frontier:
            current_state, current_path = frontier.popleft()
            nodes_expanded += 1
            if trace:
                trace("expand", state=current_state, depth=len(current_path) - 1,
                      frontier=len(frontier), order=nodes_expanded)

            for next_state, action, step_cost in get_successors(current_state, grid):
                if next_state not in visited:
                    new_path = current_path + [next_state]
                    if goal_test(next_state, goal):
                        if trace:
                            trace("goal", state=next_state, depth=len(new_path) - 1)
                            trace("path", path=new_path, cost=path_cost(new_path),
                                  nodes_expanded=nodes_expanded)
                        return new_path, path_cost(new_path), nodes_expanded
                    visited.add(next_state)
                    frontier.append((next_state, new_path))
                    if trace:
                        trace("generate", parent=current_state, state=next_state, action=action,
                              depth=len(new_path) - 1, frontier=len(frontier))
                elif trace:
                    trace("seen", parent=current_state, state=next_state)

        if trace: trace("fail", nodes_expanded=nodes_expanded)
        return None, float("inf"), nodes_expanded

    elif algo in ("A*", "ASTAR", "A_STAR"):
        # Informed Graph Search: Priority Queue ordered by f(n) = g(n) + h(n)
        counter = 0  # Tie-breaker for heap
        start_h = heuristic(start, goal)
        frontier = [(start_h, 0, counter, start, [start])]
        best_g = {start: 0}
        if trace: trace("start", algorithm="A*", start=start, goal=goal, h=start_h)

        while frontier:
            f_val, g_val, _, current_state, current_path = heapq.heappop(frontier)

            # Skip stale entries in priority queue
            if g_val > best_g.get(current_state, float("inf")):
                if trace: trace("stale", state=current_state, g=g_val)
                continue

            if goal_test(current_state, goal):
                if trace:
                    trace("goal", state=current_state, g=g_val)
                    trace("path", path=current_path, cost=path_cost(current_path),
                          nodes_expanded=nodes_expanded)
                return current_path, path_cost(current_path), nodes_expanded

            nodes_expanded += 1
            if trace:
                trace("expand", state=current_state, g=g_val, h=f_val - g_val, f=f_val,
                      frontier=len(frontier), order=nodes_expanded)

            for next_state, action, step_cost in get_successors(current_state, grid):
                new_g = g_val + step_cost
                if new_g < best_g.get(next_state, float("inf")):
                    best_g[next_state] = new_g
                    new_f = new_g + heuristic(next_state, goal)
                    counter += 1
                    heapq.heappush(frontier, (new_f, new_g, counter, next_state, current_path + [next_state]))
                    if trace:
                        trace("generate", parent=current_state, state=next_state, action=action,
                              g=new_g, h=new_f - new_g, f=new_f, frontier=len(frontier))
                elif trace:
                    trace("seen", parent=current_state, state=next_state)

        if trace: trace("fail", nodes_expanded=nodes_expanded)
        return None, float("inf"), nodes_expanded

    else:
        raise ValueError(f"Unsupported algorithm '{algorithm}'. Choose 'BFS' or 'A*'.")
