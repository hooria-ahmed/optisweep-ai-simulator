"""Environment and schedule parsing for OptiSweep AI.

``EnvironmentGrid``, ``load_environment`` and ``load_schedule_constraints``
are taken unchanged from the CS-323 CEP notebook (optisweep_simulation.ipynb,
Section 1).  The helpers below them (validation, saving, strict loading) are
additions used by the game; they never change what the original functions
return.
"""
import os
import re
from collections import deque


# ==============================================================================
# SECTION 1: ENVIRONMENT & SCHEDULE PARSERS  (original notebook code)
# ==============================================================================

class EnvironmentGrid:
    """
    Represents the 2D grid environment loaded from Environment.txt.
    Supports standard 2D indexing grid[r][c] as well as metadata attributes.
    """
    def __init__(self, rows, cols, obstacles, dirty_list, charging_station):
        self.rows = rows
        self.cols = cols
        self.obstacles = set(obstacles)
        # Assign D1, D2, ... in order of appearance
        self.dirty_locations = {f"D{i+1}": pos for i, pos in enumerate(dirty_list)}
        self.pos_to_dirty = {pos: f"D{i+1}" for i, pos in enumerate(dirty_list)}
        self.charging_station = charging_station

        # Build 2D representation
        self.cells = [["." for _ in range(cols)] for _ in range(rows)]
        for (r, c) in self.obstacles:
            self.cells[r][c] = "X"
        for label, (r, c) in self.dirty_locations.items():
            self.cells[r][c] = label
        cr, cc = self.charging_station
        self.cells[cr][cc] = "C"

    def __getitem__(self, idx):
        return self.cells[idx]

    def __len__(self):
        return self.rows

    def is_valid_cell(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols and (r, c) not in self.obstacles


def load_environment(filepath="Environment.txt"):
    """
    Parses Environment.txt according to Section 5.2 specification.
    Handles both 'rows,cols' and 'rows.cols' formats safely.
    """
    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Line 1: Grid dimensions
    dims = re.split(r"[,\.]", lines[0])
    rows, cols = int(dims[0]), int(dims[1])

    # Line 2 & 3: Number of obstacles & Obstacle coordinates
    num_obstacles = int(lines[1])
    obs_matches = re.findall(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", lines[2])
    obstacles = [(int(r), int(c)) for r, c in obs_matches]
    if len(obstacles) != num_obstacles:
        print(f"Warning: Expected {num_obstacles} obstacles, parsed {len(obstacles)}.")

    # Line 4 & 5: Number of dirty locations & Dirty location coordinates
    num_dirty = int(lines[3])
    dirty_matches = re.findall(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", lines[4])
    dirty_list = [(int(r), int(c)) for r, c in dirty_matches]
    if len(dirty_list) != num_dirty:
        print(f"Warning: Expected {num_dirty} dirty locations, parsed {len(dirty_list)}.")

    # Line 6: Charging station coordinate
    cs_match = re.findall(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", lines[5])[0]
    charging_station = (int(cs_match[0]), int(cs_match[1]))

    return EnvironmentGrid(rows, cols, obstacles, dirty_list, charging_station)


def load_schedule_constraints(filepath="Schedule.txt", dirty_variables=None):
    """
    Parses Schedule.txt according to Section 6.3 specification.
    Returns (variables, domains, constraints).
    """
    with open(filepath, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    idx = 0
    num_slots = int(lines[idx]); idx += 1
    time_slots = [f"T{i+1}" for i in range(num_slots)]

    num_prec = int(lines[idx]); idx += 1
    precedence = []
    for _ in range(num_prec):
        match = re.findall(r"\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)", lines[idx])[0]
        precedence.append((match[0], match[1]))
        idx += 1

    num_latest = int(lines[idx]); idx += 1
    latest_slot = []
    for _ in range(num_latest):
        match = re.findall(r"\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)", lines[idx])[0]
        latest_slot.append((match[0], match[1]))
        idx += 1

    variables = list(dirty_variables) if dirty_variables is not None else []
    domains = {var: list(time_slots) for var in variables}
    constraints = {
        "num_slots": num_slots,
        "time_slots": time_slots,
        "precedence": precedence,      # List of (task_before, task_after)
        "latest_slot": latest_slot     # List of (task, latest_allowed_slot)
    }
    return variables, domains, constraints


# ==============================================================================
# ADDITIONS FOR THE GAME: strict loading, validation and saving
# ==============================================================================

class InputError(Exception):
    """Raised when an input file is missing or malformed.  The message is
    written for end users and is shown directly in the GUI."""


MIN_GRID = 8          # CEP minimum grid dimension
MIN_OBSTACLES = 6     # CEP minimum number of obstacles
MIN_DIRTY = 4         # CEP minimum number of dirty locations
_COORD = r"\(\s*(-?\d+)\s*,\s*(-?\d+)\s*\)"


def _read_lines(filepath, what):
    if not filepath:
        raise InputError(f"No {what} file was selected.")
    if not os.path.isfile(filepath):
        raise InputError(f"{what.capitalize()} file not found: {os.path.basename(filepath)}")
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return [line.strip() for line in f if line.strip()]
    except OSError as exc:
        raise InputError(f"Cannot read {os.path.basename(filepath)}: {exc.strerror or exc}")


def _to_int(text, description, name):
    try:
        return int(text)
    except ValueError:
        raise InputError(f"{name}: {description} must be a whole number, found '{text}'.")


def reachable_cells(grid, start):
    """All cells reachable from ``start`` using four-directional moves."""
    if not grid.is_valid_cell(*start):
        return set()
    seen = {start}
    queue = deque([start])
    while queue:
        r, c = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nxt = (r + dr, c + dc)
            if nxt not in seen and grid.is_valid_cell(*nxt):
                seen.add(nxt)
                queue.append(nxt)
    return seen


def unreachable_dirty(grid):
    """Labels of dirty locations that cannot be reached from the charger."""
    seen = reachable_cells(grid, grid.charging_station)
    return [lbl for lbl, pos in grid.dirty_locations.items() if pos not in seen]


def check_layout(rows, cols, obstacles, dirty_list, chargers, strict=True):
    """Validate a raw layout.  Returns a list of human readable problems
    (empty list = valid).  ``chargers`` is a list so that zero or several
    charging stations can be reported.  With ``strict`` the CEP minimums
    (grid size, obstacle count, dirty count, reachability) are enforced too.
    """
    problems = []
    if rows < 1 or cols < 1:
        return [f"Invalid grid dimensions {rows}x{cols}."]
    if strict and (rows < MIN_GRID or cols < MIN_GRID):
        problems.append(f"Grid is {rows}x{cols}; the minimum size is {MIN_GRID}x{MIN_GRID}.")

    def outside(p):
        return not (0 <= p[0] < rows and 0 <= p[1] < cols)

    for name, cells in (("Obstacle", obstacles), ("Dirty location", dirty_list),
                        ("Charging station", chargers)):
        for p in cells:
            if outside(p):
                problems.append(f"{name} {p} is outside the {rows}x{cols} grid.")

    if len(chargers) == 0:
        problems.append("Missing charging station (exactly one is required).")
    elif len(chargers) > 1:
        problems.append(f"{len(chargers)} charging stations found (exactly one is required).")

    seen = {}
    for name, cells in (("obstacle", obstacles), ("dirty location", dirty_list),
                        ("charging station", chargers)):
        for p in cells:
            if p in seen:
                problems.append(f"Overlapping cells: {p} is used as {seen[p]} and {name}.")
            else:
                seen[p] = name

    if strict:
        if len(set(obstacles)) < MIN_OBSTACLES:
            problems.append(f"Only {len(set(obstacles))} obstacles; at least {MIN_OBSTACLES} are required.")
        if len(set(dirty_list)) < MIN_DIRTY:
            problems.append(f"Only {len(set(dirty_list))} dirty locations; at least {MIN_DIRTY} are required.")

    if not problems and len(chargers) == 1 and strict:
        grid = EnvironmentGrid(rows, cols, obstacles, dirty_list, chargers[0])
        for lbl in unreachable_dirty(grid):
            problems.append(f"{lbl} at {grid.dirty_locations[lbl]} is unreachable from the charging station.")
    return problems


def load_environment_checked(filepath):
    """Strict wrapper around :func:`load_environment`.

    Checks the file for structural problems first (missing file, bad numbers,
    out-of-range or overlapping cells, missing charger) and raises
    :class:`InputError` with a clear message.  When the file is well formed the
    grid is produced by the original ``load_environment``.

    Unreachable dirty locations are *not* rejected here: they are a navigation
    failure that the mission itself must detect and report.
    """
    name = os.path.basename(filepath or "")
    lines = _read_lines(filepath, "environment")
    if len(lines) < 6:
        raise InputError(f"{name}: expected 6 lines (size, obstacle count, obstacles, "
                         f"dirty count, dirty locations, charging station), found {len(lines)}.")
    dims = [d for d in re.split(r"[,\.]", lines[0]) if d.strip()]
    if len(dims) != 2:
        raise InputError(f"{name}: line 1 must be 'rows,cols', found '{lines[0]}'.")
    rows = _to_int(dims[0], "row count", name)
    cols = _to_int(dims[1], "column count", name)
    if rows < 1 or cols < 1:
        raise InputError(f"{name}: invalid grid dimensions {rows}x{cols}.")
    n_obs = _to_int(lines[1], "obstacle count", name)
    obstacles = [(int(a), int(b)) for a, b in re.findall(_COORD, lines[2])]
    n_dirty = _to_int(lines[3], "dirty-location count", name)
    dirty = [(int(a), int(b)) for a, b in re.findall(_COORD, lines[4])]
    chargers = [(int(a), int(b)) for a, b in re.findall(_COORD, lines[5])]
    if len(obstacles) != n_obs:
        raise InputError(f"{name}: declares {n_obs} obstacles but lists {len(obstacles)}.")
    if len(dirty) != n_dirty:
        raise InputError(f"{name}: declares {n_dirty} dirty locations but lists {len(dirty)}.")
    if not dirty:
        raise InputError(f"{name}: there are no dirty locations to clean.")
    problems = check_layout(rows, cols, obstacles, dirty, chargers, strict=False)
    if problems:
        raise InputError(f"{name}: {problems[0]}")
    try:
        return load_environment(filepath)
    except (ValueError, IndexError) as exc:  # defensive: anything the checks missed
        raise InputError(f"{name}: invalid environment format ({exc}).")


def load_schedule_checked(filepath, dirty_variables):
    """Strict wrapper around :func:`load_schedule_constraints`.

    Raises :class:`InputError` for missing files, malformed lines and
    constraints that mention unknown task labels or time slots.  Too few time
    slots is *not* an input error: the CSP solver reports that as infeasible.
    """
    name = os.path.basename(filepath or "")
    lines = _read_lines(filepath, "schedule")
    pair = r"\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)"
    if not lines:
        raise InputError(f"{name}: the schedule file is empty.")
    idx = 0
    n_slots = _to_int(lines[idx], "number of time slots", name); idx += 1
    if n_slots < 1:
        raise InputError(f"{name}: the number of time slots must be at least 1.")
    sections = []
    for title in ("precedence", "latest-slot"):
        if idx >= len(lines):
            raise InputError(f"{name}: missing the {title} constraint count.")
        count = _to_int(lines[idx], f"{title} constraint count", name); idx += 1
        if count < 0:
            raise InputError(f"{name}: {title} constraint count cannot be negative.")
        rows = []
        for k in range(count):
            if idx >= len(lines) or not re.fullmatch(pair, lines[idx]):
                found = lines[idx] if idx < len(lines) else "end of file"
                raise InputError(f"{name}: {title} constraint {k + 1} of {count} is "
                                 f"missing or malformed (found '{found}').")
            rows.append(re.fullmatch(pair, lines[idx]).groups()); idx += 1
        sections.append(rows)
    known = set(dirty_variables)
    slots = {f"T{i + 1}" for i in range(n_slots)}
    for a, b in sections[0]:
        for task in (a, b):
            if task not in known:
                raise InputError(f"{name}: invalid task label '{task}' in precedence ({a},{b}); "
                                 f"the environment defines {', '.join(sorted(known, key=_label_key))}.")
        if a == b:
            raise InputError(f"{name}: precedence ({a},{b}) relates a task to itself.")
    for task, slot in sections[1]:
        if task not in known:
            raise InputError(f"{name}: invalid task label '{task}' in latest-slot ({task},{slot}).")
        if slot not in slots:
            raise InputError(f"{name}: invalid time slot '{slot}' in latest-slot ({task},{slot}); "
                             f"only T1..T{n_slots} exist.")
    try:
        return load_schedule_constraints(filepath, dirty_variables)
    except (ValueError, IndexError) as exc:
        raise InputError(f"{name}: invalid schedule format ({exc}).")


def _label_key(label):
    digits = re.sub(r"\D", "", label)
    return int(digits) if digits else 0


def format_environment(rows, cols, obstacles, dirty_list, charging_station):
    """Serialise a layout in the original six-line Environment.txt format."""
    fmt = lambda cells: ", ".join(f"({r},{c})" for r, c in cells)
    return (f"{rows},{cols}\n{len(obstacles)}\n{fmt(obstacles)}\n"
            f"{len(dirty_list)}\n{fmt(dirty_list)}\n"
            f"({charging_station[0]},{charging_station[1]})\n")


def save_environment(filepath, rows, cols, obstacles, dirty_list, charging_station):
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(format_environment(rows, cols, obstacles, dirty_list, charging_station))


def format_schedule(num_slots, precedence, latest_slot):
    """Serialise constraints in the original Schedule.txt format."""
    lines = [str(num_slots), str(len(precedence))]
    lines += [f"({a},{b})" for a, b in precedence]
    lines.append(str(len(latest_slot)))
    lines += [f"({a},{b})" for a, b in latest_slot]
    return "\n".join(lines) + "\n"
