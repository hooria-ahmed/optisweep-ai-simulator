"""Interactive editor for custom scheduling constraints.

Builds the same ``Schedule.txt`` format used by the three preset missions:
a number of time slots, a list of ``(before, after)`` precedence rules and a
list of ``(task, latest_slot)`` deadline rules.  Rules are checked against the
dirty-task labels of the environment before they can be saved.
"""
import os

import pygame

from config import settings as S
from core.environment import (InputError, check_schedule, format_schedule,
                              load_environment_checked, load_schedule_checked)
from gui import ui
from gui.app import Screen

MAX_SLOTS = 32
MAX_PRECEDENCE = 14
MAX_LATEST = 10
ROW_H = 26


class Stepper:
    """Small ``<  VALUE  >`` picker over a fixed list of choices."""
    def __init__(self, rect, values, index=0, arrow=32, on_change=None):
        self.rect = pygame.Rect(rect)
        self.values = list(values)
        self.index = max(0, min(index, max(0, len(self.values) - 1)))
        self.arrow = arrow
        self.on_change = on_change
        self.left = pygame.Rect(self.rect.x, self.rect.y, arrow, self.rect.h)
        self.right = pygame.Rect(self.rect.right - arrow, self.rect.y, arrow, self.rect.h)

    @property
    def value(self):
        return self.values[self.index] if self.values else ""

    def set_values(self, values):
        previous = self.value
        self.values = list(values)
        self.index = self.values.index(previous) if previous in self.values else 0

    def _move(self, delta):
        if not self.values:
            return
        self.index = (self.index + delta) % len(self.values)
        if self.on_change is not None:
            self.on_change(self.value)

    def handle(self, event, app=None):
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        if self.left.collidepoint(event.pos):
            self._move(-1)
            return True
        if self.right.collidepoint(event.pos):
            self._move(1)
            return True
        return False

    def draw(self, surf, color=S.CYAN):
        ui.rrect(surf, S.DARK, self.rect, 8)
        ui.rrect(surf, color, self.rect, 8, 1)
        ui.text(surf, "<", self.left.center, 16, S.MUTED, bold=True, anchor="center")
        ui.text(surf, ">", self.right.center, 16, S.MUTED, bold=True, anchor="center")
        ui.text(surf, self.value, self.rect.center, 14, S.WHITE, bold=True, anchor="center",
                max_width=max(20, self.rect.w - 2 * self.arrow - 8))


class ScheduleEditor(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.env_path = app.state.env_path
        self.labels = ["D1", "D2", "D3", "D4"]
        self.slots = 4
        self.precedence = []
        self.latest = []
        self.report, self.report_ok = [], None

        # Load the environment the app already has selected, if it is readable.
        try:
            g = load_environment_checked(self.env_path)
            self.labels = list(g.dirty_locations)
        except (InputError, OSError):
            pass
        self.slots = max(1, len(self.labels))

        self.slot_step = Stepper((330, 175, 118, 38),
                                 [f"T{i + 1}" for i in range(MAX_SLOTS)],
                                 self.slots - 1, 28, self.on_slots)
        self.before = Stepper((56, 250, 150, 36), self.labels)
        self.after = Stepper((226, 250, 150, 36), self.labels)
        self.task = Stepper((506, 250, 130, 36), self.labels)
        self.deadline = Stepper((646, 250, 110, 36),
                                [f"T{i + 1}" for i in range(self.slots)], self.slots - 1, 28)
        self.steps = (self.slot_step, self.before, self.after, self.task, self.deadline)

        self.widgets = ui.WidgetGroup(app)
        self.widgets.add(ui.Button((386, 250, 100, 36), "ADD RULE", self.add_precedence,
                                   "blue", size=12))
        self.widgets.add(ui.Button((766, 250, 110, 36), "ADD DEADLINE", self.add_latest,
                                   "blue", size=12))
        self.filename = ui.TextInput((996, 152, 548, 40), self.default_filename(), "file name")
        self.widgets.add(self.filename)
        self.widgets.add(ui.Button((996, 212, 548, 44), "VALIDATE SCHEDULE", self.validate,
                                   "blue", size=15))
        self.widgets.add(ui.Button((996, 264, 548, 44), "SAVE SCHEDULE", self.save,
                                   "green", size=15))
        self.widgets.add(ui.Button((996, 316, 548, 44), "LOAD SCHEDULE", self.load, size=15))
        self.widgets.add(ui.Button((996, 380, 548, 54), "PLAY THIS SCHEDULE", self.play,
                                   "primary", size=17))
        self.widgets.add(ui.Button((996, 446, 548, 44), "CHOOSE ENVIRONMENT", self.choose_env, size=14))
        self.widgets.add(ui.Button((996, 500, 548, 44), "BACK TO ENVIRONMENT",
                                   lambda: app.go("editor"), size=14))
        self.rule_widgets = ui.WidgetGroup(app)
        self.rebuild_rules()

    # ------------------------------------------------------------------ setup --
    def default_filename(self):
        base = os.path.basename(self.env_path or "Environment.txt")
        if base.lower().startswith("environment_"):
            return "Schedule_" + base[len("Environment_"):]
        return "Schedule_Custom.txt"

    def enter(self, env_path=None, labels=None, **kwargs):
        if env_path:
            self.choose_env_path(env_path)
        elif labels is not None:
            self.set_labels(labels)
        self.report, self.report_ok = [], None

    def set_labels(self, labels):
        self.labels = list(labels) or ["D1"]
        self.before.set_values(self.labels)
        self.after.set_values(self.labels)
        self.task.set_values(self.labels)
        self.precedence = [(a, b) for a, b in self.precedence
                           if a in self.labels and b in self.labels]
        self.latest = [(t, s) for t, s in self.latest if t in self.labels]
        self.rebuild_rules()

    def choose_env_path(self, path):
        try:
            g = load_environment_checked(path)
        except (InputError, OSError) as exc:
            self.app.audio.play("error")
            self.app.notify(str(exc), S.RED, 6)
            return False
        self.env_path = path
        self.filename.value = self.default_filename()
        self.set_labels(list(g.dirty_locations))
        self.report, self.report_ok = [], None
        self.app.notify(f"Environment: {os.path.basename(path)}", S.GREEN, 3)
        return True

    def choose_env(self):
        start = S.CUSTOM_ENV_DIR if os.path.isdir(S.CUSTOM_ENV_DIR) else S.ROOT_DIR
        self.app.modal = ui.FilePicker(self.app, "CHOOSE ENVIRONMENT",
                                       lambda path: self.choose_env_path(path), start_dir=start)

    def on_slots(self, value):
        self.slots = int(value[1:])
        self.deadline.set_values([f"T{i + 1}" for i in range(self.slots)])
        self.latest = [(t, s) for t, s in self.latest if s in self.deadline.values]
        self.rebuild_rules()
        self.report, self.report_ok = [], None

    # ------------------------------------------------------------------ rules --
    def add_precedence(self):
        if len(self.precedence) >= MAX_PRECEDENCE:
            self.app.notify(f"At most {MAX_PRECEDENCE} precedence rules are shown.", S.ORANGE, 3)
            return
        pair = (self.before.value, self.after.value)
        if pair[0] == pair[1]:
            self.app.notify("A task cannot precede itself.", S.ORANGE, 3)
            return
        if pair not in self.precedence:
            self.precedence.append(pair)
        self.rebuild_rules()

    def add_latest(self):
        if len(self.latest) >= MAX_LATEST:
            self.app.notify(f"At most {MAX_LATEST} deadline rules are shown.", S.ORANGE, 3)
            return
        pair = (self.task.value, self.deadline.value)
        if pair not in self.latest:
            self.latest.append(pair)
        self.rebuild_rules()

    def rebuild_rules(self):
        self.rule_widgets.items.clear()
        for i in range(len(self.precedence)):
            x, y = 56, 298 + i * ROW_H
            self.rule_widgets.add(ui.Button((x + 320, y, 56, 22), "X",
                                            lambda i=i: self.remove_precedence(i),
                                            "danger", size=11, sound="tick"))
        for i in range(len(self.latest)):
            x, y = 506, 298 + i * ROW_H
            self.rule_widgets.add(ui.Button((x + 374, y, 56, 22), "X",
                                            lambda i=i: self.remove_latest(i),
                                            "danger", size=11, sound="tick"))

    def remove_precedence(self, i):
        self.precedence.pop(i)
        self.rebuild_rules()

    def remove_latest(self, i):
        self.latest.pop(i)
        self.rebuild_rules()

    # ------------------------------------------------------------ file actions --
    def path_for_name(self):
        name = self.filename.value.strip() or "Schedule_Custom.txt"
        if not name.lower().endswith(".txt"):
            name += ".txt"
        return os.path.join(S.CUSTOM_ENV_DIR, os.path.basename(name))

    def validate(self, quiet=False):
        problems, warnings = check_schedule(self.slots, self.precedence, self.latest, self.labels)
        # A well-formatted schedule that cannot be solved is still a failed
        # schedule: too few slots or a precedence cycle must show a red box
        # and must not be saved.  Show every issue inside the report panel.
        issues = list(problems) + list(warnings)
        self.report = issues or ["Schedule is valid: all task labels and time slots exist."]
        self.report_ok = not issues
        if not quiet:
            self.app.audio.play("cleaned" if self.report_ok else "error")
        return self.report_ok

    def save(self):
        if not self.validate(quiet=True):
            self.app.audio.play("error")
            self.app.notify("Cannot save: " + self.report[0], S.RED, 5)
            return None
        path = self.path_for_name()
        try:
            os.makedirs(S.CUSTOM_ENV_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(format_schedule(self.slots, self.precedence, self.latest))
        except OSError as exc:
            self.app.notify(f"Could not save: {exc.strerror or exc}", S.RED, 5)
            return None
        self.app.state.sched_path = path
        self.app.notify(f"Saved {os.path.relpath(path, S.ROOT_DIR)}", S.GREEN, 4)
        return path

    def load(self):
        def chosen(path):
            try:
                _, _, c = load_schedule_checked(path, self.labels)
            except InputError as exc:
                self.app.audio.play("error")
                self.app.notify(str(exc), S.RED, 6)
                return
            self.slots = min(max(1, c["num_slots"]), MAX_SLOTS)
            self.slot_step.index = self.slots - 1
            self.on_slots(self.slot_step.values[self.slot_step.index])
            self.precedence = [tuple(rule) for rule in c["precedence"]]
            self.latest = [tuple(rule) for rule in c["latest_slot"]]
            self.deadline.set_values([f"T{i + 1}" for i in range(self.slots)])
            self.filename.value = os.path.basename(path)
            self.rebuild_rules()
            self.report, self.report_ok = [], None
            self.app.notify(f"Loaded {os.path.basename(path)}", S.GREEN, 3)
        self.app.modal = ui.FilePicker(self.app, "LOAD SCHEDULE", chosen)

    def play(self):
        path = self.save()
        if path is None:
            return
        st = self.app.state
        st.env_path, st.sched_path = self.env_path, path
        st.mission_title = "CUSTOM - " + os.path.basename(self.env_path)
        self.app.go("config")

    def text_focus(self):
        return self.filename.focus

    # ------------------------------------------------------------------ events --
    def handle(self, event):
        if self.widgets.handle(event):
            return
        if self.rule_widgets.handle(event):
            return
        for step in self.steps:
            if step.handle(event):
                return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go("editor")

    def update(self, dt):
        self.widgets.update(dt)
        self.rule_widgets.update(dt)

    # ----------------------------------------------------------------- drawing --
    def draw_rules(self, surf, x, rules, slot_based=False):
        for i, (a, b) in enumerate(rules):
            y = 298 + i * ROW_H
            label = f"{a} by {b}" if slot_based else f"{a}  ->  {b}"
            ui.text(surf, label, (x, y + 3), 14, S.WHITE if i % 2 == 0 else S.MUTED, mono=True)

    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        app.header(surf, "SCHEDULE EDITOR",
                   "Define precedence and deadline rules, then validate and save as Schedule.txt",
                   accent=S.PURPLE)

        left = pygame.Rect(30, 84, 920, 726)
        y = ui.panel(surf, left, "SCHEDULING CONSTRAINTS", accent=S.PURPLE)
        ui.text(surf, "ENVIRONMENT", (left.x + 26, y + 4), 11, S.CYAN, bold=True)
        ui.text(surf, os.path.basename(self.env_path or "(none)"), (left.x + 140, y + 2), 14,
                S.WHITE, mono=True, max_width=left.w - 180)
        ui.text(surf, f"Tasks: {', '.join(self.labels)}", (left.x + 26, y + 32), 13, S.MUTED,
                max_width=left.w - 52)
        ui.text(surf, "TIME SLOTS", (left.x + 26, 175), 13, S.CYAN, bold=True)
        self.slot_step.draw(surf)
        ui.text(surf, f"({len(self.labels)} task(s))", (left.x + 160, 185), 13, S.MUTED)

        for x, title in ((56, "PRECEDENCE  (before -> after)"), (506, "LATEST SLOT  (task by slot)")):
            ui.text(surf, title, (x, 222), 12, S.CYAN, bold=True)
        self.before.draw(surf)
        self.after.draw(surf)
        self.task.draw(surf, S.PURPLE)
        self.deadline.draw(surf, S.PURPLE)
        self.draw_rules(surf, 56, self.precedence)
        self.draw_rules(surf, 506, self.latest, slot_based=True)
        self.rule_widgets.draw(surf)

        rep = pygame.Rect(56, 682, 868, 118)
        ui.rrect(surf, S.DARK, rep, 8)
        if self.report_ok is None:
            ui.rrect(surf, S.BORDER, rep, 8, 1)
            ui.text(surf, "Build your rules, then press VALIDATE SCHEDULE. Saving validates automatically.",
                    (rep.x + 14, rep.y + 12), 13, S.MUTED)
            ui.text(surf, "Precedence (A,B) means A must be cleaned before B; (D3,T2) means D3 no later than T2.",
                    (rep.x + 14, rep.y + 36), 13, S.MUTED)
            ui.text(surf, "The file is saved in environments/ in the original Schedule.txt format.",
                    (rep.x + 14, rep.y + 60), 13, S.MUTED)
        else:
            col = S.GREEN if self.report_ok else S.RED
            ui.rrect(surf, col, rep, 8, 1)
            ui.text(surf, "VALID" if self.report_ok else f"FAILED - {len(self.report)} PROBLEM(S)",
                    (rep.x + 14, rep.y + 9), 12, col, bold=True)
            # Every message - including "too few slots" / "cycle" - is drawn
            # inside the panel, never on the border or outside it.
            for i, line in enumerate(self.report[:4]):
                ui.text(surf, f"{i + 1}. {line}", (rep.x + 14, rep.y + 29 + i * 19), 12,
                        S.WHITE if self.report_ok else S.ORANGE, max_width=rep.w - 28)

        right = pygame.Rect(970, 84, 600, 726)
        ui.panel(surf, right, "SCHEDULE FILE", accent=S.PURPLE)
        ui.text(surf, "FILE NAME", (996, 126), 11, S.CYAN, bold=True)
        self.widgets.draw(surf)
        ui.text(surf, f"Time slots: {self.slots}", (996, 574), 15, S.WHITE, bold=True)
        ui.text(surf, f"Precedence rules: {len(self.precedence)}", (996, 602), 15, S.WHITE, bold=True)
        ui.text(surf, f"Deadline rules: {len(self.latest)}", (996, 630), 15, S.WHITE, bold=True)
        ui.paragraph(surf, "PLAY THIS SCHEDULE saves the file and opens mission configuration "
                           "with this environment and schedule selected.", (996, 676), 13,
                     548, S.MUTED, 4)
