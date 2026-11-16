"""Interactive environment editor."""
import os

import pygame

from config import settings as S
from core.environment import (MIN_DIRTY, MIN_GRID, MIN_OBSTACLES, EnvironmentGrid, InputError,
                              check_layout, format_schedule, load_environment_checked,
                              load_schedule_checked, save_environment, unreachable_dirty)
from gui import ui
from gui.app import Screen
from gui.grid_view import GridView

GRID_RECT = (20, 76, 800, 800)
TOOLS = [("obstacle", "ADD OBSTACLE", S.MUTED), ("dirty", "ADD DIRTY LOCATION", S.ORANGE),
         ("charger", "SET CHARGING STATION", S.BLUE), ("erase", "ERASE CELL", S.RED)]


class Layout:
    """Editable layout that looks enough like an EnvironmentGrid for GridView."""
    def __init__(self, rows=MIN_GRID, cols=MIN_GRID):
        self.rows, self.cols = rows, cols
        self.obstacles = set()
        self.dirty = []                 # ordered: index + 1 is the task number
        self.charging_station = None

    @property
    def dirty_locations(self):
        return {f"D{i + 1}": p for i, p in enumerate(self.dirty)}

    @property
    def pos_to_dirty(self):
        return {p: f"D{i + 1}" for i, p in enumerate(self.dirty)}

    def snapshot(self):
        return (self.rows, self.cols, set(self.obstacles), list(self.dirty), self.charging_station)

    def restore(self, snap):
        self.rows, self.cols, obs, dirty, self.charging_station = snap
        self.obstacles, self.dirty = set(obs), list(dirty)

    def erase(self, cell):
        self.obstacles.discard(cell)
        if cell in self.dirty:
            self.dirty.remove(cell)
        if self.charging_station == cell:
            self.charging_station = None

    def problems(self):
        chargers = [self.charging_station] if self.charging_station else []
        return check_layout(self.rows, self.cols, sorted(self.obstacles), self.dirty, chargers, strict=True)


class EnvironmentEditor(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.layout = Layout()
        self.saved = self.layout.snapshot()
        self.view = None
        self.tool = "obstacle"
        self.report = []                    # last explicit validation result
        self.report_ok = None
        self.painting = None                # tool being dragged
        self.widgets = ui.WidgetGroup(app)
        x = 850
        self.tool_btns = {}
        for i, (key, label, _) in enumerate(TOOLS):
            b = ui.Button((x + (i % 2) * 356, 122 + (i // 2) * 52, 346, 44), label, lambda k=key: self.set_tool(k), size=14)
            self.tool_btns[key] = self.widgets.add(b)
        self.widgets.add(ui.Button((x, 226, 346, 44), "CLEAR GRID", self.clear, "danger", size=14))
        self.widgets.add(ui.Button((x + 356, 226, 346, 44), "RESET GRID", self.reset, size=14))
        for i, (axis, dx) in enumerate((("rows", 0), ("cols", 356))):
            self.widgets.add(ui.Button((x + dx + 190, 318, 44, 40), "-", lambda a=axis: self.resize(a, -1), size=20))
            self.widgets.add(ui.Button((x + dx + 302, 318, 44, 40), "+", lambda a=axis: self.resize(a, +1), size=20))
        self.filename = ui.TextInput((x + 110, 668, 592, 40), "Environment_Custom.txt", "file name")
        self.widgets.add(self.filename)
        self.widgets.add(ui.Button((x, 722, 228, 46), "VALIDATE ENVIRONMENT", self.validate, "blue", size=13))
        self.widgets.add(ui.Button((x + 237, 722, 228, 46), "SAVE ENVIRONMENT", self.save, "green", size=13))
        self.widgets.add(ui.Button((x + 474, 722, 228, 46), "LOAD ENVIRONMENT", self.load, size=13))
        self.widgets.add(ui.Button((x, 780, 465, 54), "PLAY THIS ENVIRONMENT", self.play, "primary", size=18))
        self.widgets.add(ui.Button((x + 474, 780, 228, 54), "MAIN MENU", lambda: app.go("menu"), size=15))
        self.rebuild()
        self.set_tool("obstacle")

    def text_focus(self):
        return self.filename.focus

    def rebuild(self):
        self.view = GridView(self.layout, GRID_RECT)

    def changed(self):
        self.view._static = None
        self.report, self.report_ok = [], None

    # ----------------------------------------------------------------- tools --
    def set_tool(self, key):
        self.tool = key
        for k, b in self.tool_btns.items():
            b.active = k == key

    def clear(self):
        lay = self.layout
        lay.obstacles.clear()
        lay.dirty.clear()
        lay.charging_station = None
        self.changed()

    def reset(self):
        self.layout.restore(self.saved)
        self.rebuild()
        self.changed()
        self.app.notify("Grid reset to the last saved / loaded state.", S.CYAN, 2.5)

    def resize(self, axis, delta):
        lay = self.layout
        value = getattr(lay, axis) + delta
        if not (S.EDITOR_MIN <= value <= S.EDITOR_MAX):
            self.app.notify(f"Grid size must stay between {S.EDITOR_MIN} and {S.EDITOR_MAX}.", S.ORANGE, 2.5)
            return
        setattr(lay, axis, value)
        inside = lambda p: p[0] < lay.rows and p[1] < lay.cols
        lay.obstacles = {p for p in lay.obstacles if inside(p)}
        lay.dirty = [p for p in lay.dirty if inside(p)]
        if lay.charging_station and not inside(lay.charging_station):
            lay.charging_station = None
        self.rebuild()
        self.changed()

    def apply(self, cell, tool):
        """Apply a tool to a cell.  Placing anything first clears the cell, so
        two things can never overlap."""
        lay = self.layout
        if tool == "erase":
            lay.erase(cell)
        elif tool == "obstacle":
            if cell not in lay.obstacles:
                lay.erase(cell)
                lay.obstacles.add(cell)
        elif tool == "dirty":
            if cell not in lay.dirty:
                lay.erase(cell)
                lay.dirty.append(cell)
        elif tool == "charger":
            lay.erase(cell)
            lay.charging_station = cell
        self.changed()

    # ------------------------------------------------------------ file actions --
    def validate(self, quiet=False):
        problems = self.layout.problems()
        self.report = problems or ["Environment is valid: every dirty location is reachable with "
                                   "four-directional movement."]
        self.report_ok = not problems
        if not quiet:
            self.app.audio.play("cleaned" if not problems else "error")
        return not problems

    def path_for_name(self):
        name = (self.filename.value.strip() or "Environment_Custom.txt")
        if not name.lower().endswith(".txt"):
            name += ".txt"
        return os.path.join(S.CUSTOM_ENV_DIR, os.path.basename(name))

    def save(self):
        if not self.validate(quiet=True):
            self.app.audio.play("error")
            self.app.notify("Cannot save: " + self.report[0], S.RED, 5)
            return None
        lay = self.layout
        path = self.path_for_name()
        try:
            os.makedirs(S.CUSTOM_ENV_DIR, exist_ok=True)
            save_environment(path, lay.rows, lay.cols, sorted(lay.obstacles), lay.dirty, lay.charging_station)
        except OSError as exc:
            self.app.notify(f"Could not save: {exc.strerror or exc}", S.RED, 5)
            return None
        self.saved = lay.snapshot()
        self.app.notify(f"Saved environments/{os.path.basename(path)}", S.GREEN, 4)
        return path

    def load(self):
        def chosen(path):
            try:
                g = load_environment_checked(path)
            except InputError as exc:
                self.app.audio.play("error")
                self.app.notify(str(exc), S.RED, 6)
                return
            if not (g.rows <= S.EDITOR_MAX and g.cols <= S.EDITOR_MAX):
                self.app.notify(f"That grid is larger than the editor supports ({S.EDITOR_MAX}x{S.EDITOR_MAX}).", S.RED, 5)
                return
            lay = self.layout
            lay.rows, lay.cols = g.rows, g.cols
            lay.obstacles = set(g.obstacles)
            lay.dirty = list(g.dirty_locations.values())
            lay.charging_station = g.charging_station
            self.saved = lay.snapshot()
            self.filename.value = os.path.basename(path)
            self.rebuild()
            self.changed()
            self.app.notify(f"Loaded {os.path.basename(path)}", S.GREEN, 3)
        self.app.modal = ui.FilePicker(self.app, "LOAD ENVIRONMENT", chosen)

    def play(self):
        """Save, make sure a compatible schedule exists, and go to configuration."""
        path = self.save()
        if path is None:
            return
        labels = list(self.layout.dirty_locations)
        sched = os.path.join(S.CUSTOM_ENV_DIR, "Schedule_" + os.path.basename(path))
        usable = False
        if os.path.isfile(sched):
            try:
                _, _, c = load_schedule_checked(sched, labels)
                usable = c["num_slots"] >= len(labels)
            except InputError:
                usable = False
        if not usable:
            # A starter schedule in the standard format (the sample's rules),
            # with one time slot per dirty location.  Edit the file to change it.
            with open(sched, "w", encoding="utf-8") as f:
                f.write(format_schedule(len(labels), [("D1", "D3"), ("D2", "D4"), ("D1", "D4")],
                                        [("D3", "T3"), ("D2", "T3")]))
        st = self.app.state
        st.env_path, st.sched_path = path, sched
        st.mission_title = "CUSTOM - " + os.path.basename(path)
        self.app.go("config")

    # ------------------------------------------------------------------ events --
    def handle(self, event):
        if self.widgets.handle(event):
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go("menu")
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            cell = self.view.cell_at(event.pos)
            if cell is not None:
                tool = "erase" if event.button == 3 else self.tool
                self.apply(cell, tool)
                self.painting = tool if tool in ("obstacle", "erase") else None
                self.app.audio.play("tick")
        elif event.type == pygame.MOUSEBUTTONUP:
            self.painting = None
        elif event.type == pygame.MOUSEMOTION and self.painting:
            cell = self.view.cell_at(event.pos)
            if cell is not None:
                self.apply(cell, self.painting)

    def update(self, dt):
        self.widgets.update(dt)

    # ----------------------------------------------------------------- drawing --
    def checklist(self):
        lay = self.layout
        rows = [(f"Grid at least {MIN_GRID}x{MIN_GRID}  ({lay.rows}x{lay.cols})", lay.rows >= MIN_GRID and lay.cols >= MIN_GRID),
                ("Exactly one charging station", lay.charging_station is not None),
                (f"At least {MIN_OBSTACLES} obstacles  ({len(lay.obstacles)})", len(lay.obstacles) >= MIN_OBSTACLES),
                (f"At least {MIN_DIRTY} dirty locations  ({len(lay.dirty)})", len(lay.dirty) >= MIN_DIRTY),
                ("No overlapping cells", True)]
        if lay.charging_station is not None and lay.dirty:
            grid = EnvironmentGrid(lay.rows, lay.cols, lay.obstacles, lay.dirty, lay.charging_station)
            cut = unreachable_dirty(grid)
            rows.append(("All dirty locations reachable (4-directional)" if not cut else
                         f"Unreachable: {', '.join(cut)}", not cut))
        else:
            rows.append(("All dirty locations reachable (4-directional)", False))
        return rows

    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        app.header(surf, "ENVIRONMENT EDITOR", "Build a floor plan - left-click to place, right-click to erase, drag to paint")
        lay = self.layout
        self.view.draw(surf, app.t)
        cell = self.view.cell_at(app.mouse) if app.modal is None else None
        if cell is not None:
            col = dict((k, c) for k, _, c in TOOLS)[self.tool]
            ui.rrect(surf, col, self.view.cell_rect(*cell), self.view.radius, 3)
            ui.text(surf, f"({cell[0]},{cell[1]})", (GRID_RECT[0] + 30, GRID_RECT[1] + GRID_RECT[3] + 4), 13, S.MUTED, mono=True)

        box = pygame.Rect(836, 76, 730, 800)
        ui.panel(surf, box, "TOOLS")
        x = 850
        ui.text(surf, "GRID DIMENSIONS", (x, 288), 11, S.CYAN, bold=True)
        for label, value, dx in (("ROWS", lay.rows, 0), ("COLUMNS", lay.cols, 356)):
            ui.text(surf, label, (x + dx, 330), 14, S.MUTED, bold=True)
            ui.text(surf, str(value), (x + dx + 268, 338), 24, S.WHITE, bold=True, anchor="center")
        ui.text(surf, "REQUIREMENTS", (x, 378), 11, S.CYAN, bold=True)
        y = 400
        for line, ok in self.checklist():
            if ok:
                ui.check_mark(surf, S.GREEN, (x + 10, y + 9), 12, 3)
            else:
                pygame.draw.line(surf, S.RED, (x + 4, y + 3), (x + 16, y + 15), 3)
                pygame.draw.line(surf, S.RED, (x + 16, y + 3), (x + 4, y + 15), 3)
            ui.text(surf, line, (x + 30, y), 15, S.WHITE if ok else S.ORANGE)
            y += 26
        rep = pygame.Rect(x, 566, 702, 90)
        ui.rrect(surf, S.DARK, rep, 8)
        if self.report_ok is None:
            ui.rrect(surf, S.BORDER, rep, 8, 1)
            ui.text(surf, "Press VALIDATE ENVIRONMENT to check the layout. Saving validates automatically.",
                    (rep.x + 14, rep.y + 12), 13, S.MUTED)
            ui.text(surf, "Dirty locations are numbered D1, D2, ... in the order you place them.",
                    (rep.x + 14, rep.y + 34), 13, S.MUTED)
            ui.text(surf, "Files are saved in the original Environment.txt format, in the environments/ folder.",
                    (rep.x + 14, rep.y + 56), 13, S.MUTED)
        else:
            col = S.GREEN if self.report_ok else S.RED
            ui.rrect(surf, col, rep, 8, 1)
            ui.text(surf, "VALID" if self.report_ok else f"{len(self.report)} PROBLEM(S)", (rep.x + 14, rep.y + 9), 12, col, bold=True)
            for i, line in enumerate(self.report[:3]):
                ui.text(surf, line, (rep.x + 14, rep.y + 30 + i * 19), 13, S.WHITE, max_width=rep.w - 28)
        ui.text(surf, "FILE NAME", (x, 681), 11, S.CYAN, bold=True)
        self.widgets.draw(surf)
