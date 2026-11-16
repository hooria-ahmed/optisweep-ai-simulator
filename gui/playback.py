"""Replay of recorded algorithm traces.

A playback consumes the events recorded by the real algorithms (see
``core.graph_search.search`` and ``core.csp_scheduler``) one at a time and
maintains the state the GUI draws.  It also turns each event into a short log
message for the AI Brain panel.  Nothing here invents data.
"""
from config import settings as S

TAG_COLOR = {
    "CSP": S.CYAN, "MRV": S.PURPLE, "DEGREE": S.PURPLE, "LCV": S.BLUE, "TRY": S.WHITE,
    "CONSTRAINT": S.ORANGE, "FORWARD CHECK": S.CYAN, "ASSIGN": S.GREEN, "REJECT": S.RED,
    "BACKTRACK": S.RED, "BFS": S.ORANGE, "A*": S.CYAN, "DEQUEUE": S.ORANGE, "ENQUEUE": S.BLUE,
    "EXPAND": S.CYAN, "OPEN": S.BLUE, "GOAL TEST": S.GREEN, "PATH": S.GREEN, "FAIL": S.RED,
    "SKIP": S.MUTED, "SUCCESSORS": S.MUTED, "NAV": S.WHITE,
}


def cell_str(p):
    return f"({p[0]},{p[1]})"


class SearchPlayback:
    """Step-by-step replay of one BFS or A* run."""

    def __init__(self, run):
        self.run = run
        self.algorithm = run.algorithm
        self.events = run.events
        self.reset()

    def reset(self):
        self.i = 0
        self.explored = {}        # cell -> expansion order (closed list / visited)
        self.frontier = set()     # queue / open list contents
        self.values = {}          # cell -> dict(g,h,f) or dict(depth)
        self.current = None
        self.current_values = {}
        self.frontier_size = 0
        self.nodes_expanded = 0
        self.generated = 0
        self.path = None
        self.done = False
        self.failed = False
        self.goal_reached = False
        self.log = []             # [(tag, text)]

    @property
    def progress(self):
        return self.i / max(1, len(self.events))

    def _emit(self, tag, text):
        self.log.append((tag, text))

    def step_event(self):
        """Apply one recorded event.  Returns False when nothing is left."""
        if self.i >= len(self.events):
            self.done = True
            return False
        name, d = self.events[self.i]
        self.i += 1
        astar = self.algorithm == "A*"
        if name == "start":
            self.frontier = {d["start"]}
            self.frontier_size = 1
            if astar:
                self.values[d["start"]] = {"g": 0, "h": d["h"], "f": d["h"]}
                self._emit("A*", f"Open list <- start {cell_str(d['start'])}  h={d['h']}")
            else:
                self.values[d["start"]] = {"depth": 0}
                self._emit("BFS", f"Queue <- start {cell_str(d['start'])}")
        elif name == "expand":
            st = d["state"]
            self.current = st
            self.frontier.discard(st)
            self.explored[st] = d["order"]
            self.nodes_expanded = d["order"]
            self.frontier_size = d["frontier"]
            if astar:
                self.current_values = {"g": d["g"], "h": d["h"], "f": d["f"]}
                self.values[st] = dict(self.current_values)
                self._emit("EXPAND", f"{cell_str(st)}  g={d['g']} h={d['h']} f={d['f']}")
            else:
                self.current_values = {"depth": d["depth"]}
                self._emit("DEQUEUE", f"{cell_str(st)}  depth {d['depth']}  queue {d['frontier']}")
        elif name == "generate":
            st = d["state"]
            self.frontier.add(st)
            self.frontier_size = d["frontier"]
            self.generated += 1
            if astar:
                self.values[st] = {"g": d["g"], "h": d["h"], "f": d["f"]}
                self._emit("OPEN", f"{d['action']:<5} {cell_str(st)}  g={d['g']} h={d['h']} f={d['f']}")
            else:
                self.values[st] = {"depth": d["depth"]}
                self._emit("ENQUEUE", f"{d['action']:<5} {cell_str(st)}  depth {d['depth']}")
        elif name == "stale":
            self._emit("SKIP", f"stale entry {cell_str(d['state'])} (better g known)")
        elif name == "goal":
            self.goal_reached = True
            self.current = d["state"]
            cost = d.get("g", d.get("depth"))
            self._emit("GOAL TEST", f"{cell_str(d['state'])} is the goal  cost {cost}")
        elif name == "path":
            self.path = d["path"]
            self._emit("PATH", f"reconstructed: {d['cost']} moves, {d['nodes_expanded']} nodes expanded")
            self.done = True
        elif name == "fail":
            self.failed = True
            self.done = True
            what = "open list" if astar else "queue"
            self._emit("FAIL", f"{what} empty after {d['nodes_expanded']} nodes: no path")
        elif name == "trivial":
            self.path = [d["state"]]
            self.done = True
            self._emit("GOAL TEST", f"start {cell_str(d['state'])} is already the goal")
        elif name == "invalid":
            self.failed = True
            self.done = True
            self._emit("FAIL", "start or goal is blocked / outside the grid")
        if self.i >= len(self.events):
            self.done = True
        return True

    def step(self):
        """Advance by one node expansion (the expansion plus its successors)."""
        if self.done:
            return False
        if self.i == 0 and self.events and self.events[0][0] == "start":
            self.step_event()               # initialisation belongs to the first expansion
        self.step_event()
        while not self.done and self.i < len(self.events) and self.events[self.i][0] != "expand":
            self.step_event()
        return True

    def finish(self):
        while not self.done:
            self.step_event()


class CSPPlayback:
    """Step-by-step replay of the backtracking CSP solver."""

    def __init__(self, events, variables, time_slots):
        self.events = events
        self.variables = list(variables)
        self.time_slots = list(time_slots)
        self.reset()

    def reset(self):
        self.i = 0
        self.domains = {v: list(self.time_slots) for v in self.variables}
        self.assignment = {}
        self.current_var = None
        self.current_value = None
        self.lcv_order = []
        self.pruned = {}          # last forward-check removals {var: [slots]}
        self.wipeout = None
        self.status = "Waiting"
        self.status_ok = None     # True / False / None
        self.heuristic = ""
        self.backtracks = 0
        self.checks = 0
        self.done = False
        self.solved = False
        self.failed = False
        self.flash = 0.0          # animation timer reset by the GUI on change
        self.log = []

    @property
    def progress(self):
        return len(self.assignment) / max(1, len(self.variables))

    def _emit(self, tag, text):
        self.log.append((tag, text))

    def step(self):
        if self.i >= len(self.events):
            self.done = True
            return False
        name, d = self.events[self.i]
        self.i += 1
        self.flash = 1.0
        if name == "init":
            c = d["constraints"]
            self._emit("CSP", f"Initializing {len(d['variables'])} scheduling variables, "
                              f"{len(c['time_slots'])} time slots.")
            self._emit("CSP", f"{len(c['precedence'])} precedence + {len(c['latest_slot'])} latest-slot "
                              "constraints, slots exclusive.")
            self.status, self.status_ok = "Solver initialised", None
        elif name == "too_few_slots":
            self._emit("CSP", f"Only {d['slots']} slots for {d['tasks']} tasks: cannot schedule.")
            self.status, self.status_ok = "Insufficient time slots", False
        elif name == "select":
            self.current_var = d["variable"]
            self.current_value = None
            self.pruned, self.wipeout = {}, None
            var, size, degree = d["candidates"][0]
            if d["mrv_tie"]:
                tied = [c[0] for c in d["candidates"] if c[1] == size]
                self._emit("MRV", f"Tie: {', '.join(tied)} each have {size} values left.")
                if d["degree_tie"]:
                    self._emit("DEGREE", f"Tie again (degree {degree}): choosing {var} by label.")
                    self.heuristic = "MRV tie > Degree tie > label order"
                else:
                    self._emit("DEGREE", f"{var} wins the tie with degree {degree}.")
                    self.heuristic = f"MRV tie > Degree ({degree})"
            else:
                self._emit("MRV", f"{var} has the smallest domain ({size} values).")
                self.heuristic = f"MRV (domain size {size})"
            self.status, self.status_ok = f"Selected variable {var}", None
        elif name == "lcv":
            self.lcv_order = d["ordering"]
            order = "  ".join(f"{v}({n})" for v, n in d["ordering"])
            self._emit("LCV", f"Order for {d['variable']}: {order}")
        elif name == "try":
            self.current_var, self.current_value = d["variable"], d["value"]
            self.pruned, self.wipeout = {}, None
            self._emit("TRY", f"{d['variable']} = {d['value']} ?")
            self.status, self.status_ok = f"Testing {d['variable']} = {d['value']}", None
        elif name == "check":
            self.checks += 1
            self._emit("CONSTRAINT", ("ok: " if d["ok"] else "VIOLATED: ") + d["detail"])
            self.status, self.status_ok = d["detail"], d["ok"]
        elif name == "reject":
            self._emit("REJECT", f"{d['variable']} = {d['value']} is inconsistent.")
        elif name == "assign":
            self.assignment = dict(d["assignment"])
            self._emit("ASSIGN", f"{d['variable']} <- {d['value']}")
            self.status, self.status_ok = f"{d['variable']} assigned {d['value']}", True
        elif name == "forward":
            self.pruned = {k: list(v) for k, v in d["pruned"].items()}
            self.wipeout = d["wipeout"]
            self.domains = {k: list(v) for k, v in d["domains"].items()}
            if d["pruned"]:
                parts = "  ".join(f"{k}:-{','.join(v)}" for k, v in d["pruned"].items())
                self._emit("FORWARD CHECK", f"Pruned {parts}")
            else:
                self._emit("FORWARD CHECK", "No domain values needed removing.")
            if d["wipeout"]:
                self._emit("FORWARD CHECK", f"Domain of {d['wipeout']} is empty: dead end.")
                self.status, self.status_ok = f"Domain wipe-out for {d['wipeout']}", False
        elif name == "backtrack":
            self.backtracks += 1
            self.assignment = dict(d["assignment"])
            self.domains = {k: list(v) for k, v in d["domains"].items()}
            self.pruned, self.wipeout = {}, None
            self._emit("BACKTRACK", f"Undo {d['variable']} = {d['value']}, restore domains.")
            self.status, self.status_ok = f"Backtracking from {d['variable']}", False
        elif name == "dead_end":
            self._emit("BACKTRACK", f"No time slot works for {d['variable']}.")
        elif name == "solution":
            self.assignment = dict(d["assignment"])
            self.solved = True
            self.current_var = self.current_value = None
            self._emit("CSP", "Feasible cleaning schedule generated.")
            self.status, self.status_ok = "All constraints satisfied", True
        elif name == "failure":
            self.failed = True
            self.current_var = self.current_value = None
            self._emit("CSP", "Search space exhausted: no feasible schedule.")
            self.status, self.status_ok = "Infeasible schedule", False
        if self.i >= len(self.events):
            self.done = True
        return True

    def finish(self):
        while self.step():
            pass
