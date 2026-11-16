"""Mission configuration: algorithm, execution mode, speed and launch."""
import math
import os
import threading

import pygame

from config import settings as S
from core.environment import InputError
from core.integration import plan_mission
from gui import ui
from gui.app import Screen
from gui.mission_selection import MissionInfo, draw_preview

ALGO_TEXT = {
    "BFS": "Breadth-First Search: uninformed. Expands the map in rings using a FIFO queue. "
           "Optimal for unit step costs but explores many cells.",
    "A*": "A* Search: informed. Orders its open list by f(n) = g(n) + h(n) with the Manhattan "
          "heuristic, so it heads for the goal and expands fewer nodes.",
}
MODE_TEXT = {
    "AUTOMATIC": "The mission plays continuously. You can pause at any time.",
    "STEP-BY-STEP": "The mission waits for you. Each NEXT STEP runs one AI decision or one move.",
}
STAGES = ["Load environment", "Load scheduling constraints", "Execute CSP scheduler",
          "Generate cleaning schedule", "Calculate navigation paths", "Prepare robot journey"]


class MissionConfig(Screen):
    def __init__(self, app):
        super().__init__(app)
        st = app.state
        self.info = None
        self.cache = {}
        self.error = ""
        self.job = None            # background planning thread
        self.job_result = None
        self.job_time = 0.0
        self.widgets = ui.WidgetGroup(app)
        x, w = 960, 580
        self.algo = self.widgets.add(ui.Segmented((x, 150, w, 50), ["BFS", "A*"], st.algorithm, self.set_algo, 17))
        self.mode = self.widgets.add(ui.Segmented((x, 318, w, 50), ["AUTOMATIC", "STEP-BY-STEP"], st.mode,
                                                  lambda v: setattr(st, "mode", v), 16))
        self.speed = self.widgets.add(ui.Segmented((x, 458, w, 50), [n for n, _ in S.SPEEDS], st.speed,
                                                   lambda v: setattr(st, "speed", v), 15))
        self.start = self.widgets.add(ui.Button((x, 724, w, 64), "START MISSION", self.launch, "primary",
                                                size=24, sound="start"))
        self.widgets.add(ui.Button((40, S.HEIGHT - 70, 190, 46), "BACK", lambda: app.go("missions")))

    def set_algo(self, value):
        self.app.state.algorithm = value

    def enter(self, **kwargs):
        st = self.app.state
        self.info = MissionInfo(st.env_path, st.sched_path)
        self.cache.clear()
        self.error = self.info.error
        self.start.enabled = self.info.ok
        self.algo.value, self.mode.value, self.speed.value = st.algorithm, st.mode, st.speed
        self.job = None

    # ------------------------------------------------------------ planning --
    def launch(self):
        if self.job is not None:
            return
        st = self.app.state
        self.error = ""
        self.job_result = None
        self.job_time = 0.0

        def work():
            try:
                self.job_result = ("ok", plan_mission(st.env_path, st.sched_path, st.algorithm))
            except InputError as exc:
                self.job_result = ("error", str(exc))
            except Exception as exc:                      # never crash on bad input
                self.job_result = ("error", f"Unexpected planning error: {exc}")

        self.job = threading.Thread(target=work, daemon=True)
        self.job.start()

    def handle(self, event):
        if self.job is not None:
            return
        if self.widgets.handle(event):
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.go("missions")
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.start.enabled:
                self.app.audio.play("start")
                self.launch()

    def update(self, dt):
        self.widgets.update(dt)
        if self.job is not None:
            self.job_time += dt
            if self.job_result is not None and self.job_time > 0.9:
                kind, payload = self.job_result
                self.job = None
                if kind == "ok":
                    self.app.state.plan = payload
                    self.app.go("simulation", plan=payload)
                else:
                    self.error = payload
                    self.app.audio.play("error")

    def draw(self, surf):
        app, st = self.app, self.app.state
        app.draw_background(surf)
        app.header(surf, "MISSION CONFIGURATION", st.mission_title)

        # ---- left: mission summary -----------------------------------------
        left = pygame.Rect(40, 84, 860, 726)
        y = ui.panel(surf, left, "MISSION SUMMARY")
        prev = pygame.Rect(left.x + 24, y + 6, 400, 400)
        ui.rrect(surf, S.DARK, prev, 12)
        draw_preview(surf, self.info, prev.inflate(-12, -12), app.t, self.cache)
        fx = prev.right + 28
        fy = y + 6
        ui.text(surf, st.mission_title, (fx, fy), 18, S.WHITE, bold=True, max_width=left.right - fx - 20)
        fy += 36
        for key, val in self.info.facts():
            ui.text(surf, key, (fx, fy), 15, S.MUTED)
            ui.text(surf, val, (left.right - 28, fy), 15, S.WHITE, bold=True, anchor="topright")
            fy += 27
        fy += 10
        for tag, path in (("ENV", st.env_path), ("SCHED", st.sched_path)):
            ui.text(surf, tag, (fx, fy + 2), 11, S.CYAN, bold=True)
            ui.text(surf, os.path.basename(path), (fx + 54, fy), 13, S.WHITE, mono=True,
                    max_width=left.right - fx - 80)
            fy += 24
        cy = prev.bottom + 22
        c = self.info.constraints
        ui.text(surf, "SCHEDULING CONSTRAINTS", (left.x + 26, cy), 13, S.CYAN, bold=True)
        cy += 28
        if c is not None:
            x = left.x + 26
            for a, b in c["precedence"]:
                r = ui.badge(surf, f"{a} before {b}", (x, cy), S.ORANGE, 13)
                x = r.right + 10
                if x > left.right - 150:
                    x, cy = left.x + 26, cy + 34
            x, cy = left.x + 26, cy + 38
            for task, slot in c["latest_slot"]:
                r = ui.badge(surf, f"{task} by {slot}", (x, cy), S.PURPLE, 13)
                x = r.right + 10
            x, cy = left.x + 26, cy + 38
            ui.badge(surf, "one task per time slot", (x, cy), S.BLUE, 13)
            ui.text(surf, f"Variables: {', '.join(self.info.grid.dirty_locations)}    "
                          f"Domain: T1..T{c['num_slots']}", (left.x + 26, cy + 42), 14, S.MUTED)
        ui.text(surf, f"Plan:  {st.algorithm} navigation   |   {st.mode.title()} mode   |   {st.speed.title()} speed",
                (left.x + 26, left.bottom - 40), 16, S.WHITE, bold=True)

        # ---- right: options --------------------------------------------------
        right = pygame.Rect(930, 84, 640, 726)
        ui.panel(surf, right)
        x = 960
        ui.text(surf, "NAVIGATION ALGORITHM", (x, 116), 14, S.CYAN, bold=True)
        ui.paragraph(surf, ALGO_TEXT[st.algorithm], (x, 214), 14, 580, S.MUTED, 5)
        ui.text(surf, "EXECUTION MODE", (x, 284), 14, S.CYAN, bold=True)
        ui.paragraph(surf, MODE_TEXT[st.mode], (x, 382), 14, 580, S.MUTED, 5)
        ui.text(surf, "SIMULATION SPEED", (x, 424), 14, S.CYAN, bold=True)
        ui.text(surf, f"x{st.speed_factor:g} playback of robot motion and AI decisions", (x, 522), 14, S.MUTED)
        self.widgets.draw(surf)

        if self.error:
            box = pygame.Rect(x, 566, 580, 140)
            ui.rrect_alpha(surf, S.RED, box, 10, 36)
            ui.rrect(surf, S.RED, box, 10, 1)
            ui.text(surf, "CANNOT START MISSION", (box.x + 16, box.y + 12), 14, S.RED, bold=True)
            ui.paragraph(surf, self.error, (box.x + 16, box.y + 38), 14, box.w - 32, S.WHITE, 5)
        else:
            ui.text(surf, "On START the game loads both files, runs the CSP scheduler,",
                    (x, 640), 14, S.MUTED)
            ui.text(surf, "plans every navigation leg and hands the journey to the robot.",
                    (x, 662), 14, S.MUTED)

        if self.job is not None:
            self.draw_loading(surf)

    def draw_loading(self, surf):
        ui.rrect_alpha(surf, S.DARK, surf.get_rect(), 0, 200)
        box = pygame.Rect(0, 0, 560, 360)
        box.center = (S.WIDTH // 2, S.HEIGHT // 2)
        ui.panel(surf, box, "PREPARING MISSION", title_size=16)
        done = self.job_result is not None
        shown = len(STAGES) if done and self.job_time > 0.75 else min(len(STAGES) - 1, int(self.job_time / 0.13))
        for i, stage in enumerate(STAGES):
            y = box.y + 62 + i * 40
            if i < shown:
                ui.check_mark(surf, S.GREEN, (box.x + 40, y + 10), 14, 3)
                col = S.WHITE
            elif i == shown:
                a = self.app.t * 6
                pygame.draw.circle(surf, S.CYAN, (int(box.x + 40 + 8 * math.cos(a)), int(y + 10 + 8 * math.sin(a))), 3)
                col = S.CYAN
            else:
                pygame.draw.circle(surf, S.BORDER, (box.x + 40, y + 10), 4)
                col = S.MUTED
            ui.text(surf, stage, (box.x + 68, y), 17, col, bold=i == shown)
