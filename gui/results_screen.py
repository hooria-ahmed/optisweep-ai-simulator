"""Mission results: success / failure report and the full-journey viewer."""
import math

import pygame

from config import settings as S
from core.csp_scheduler import slot_to_int
from entities.particles import ParticleSystem
from entities.robot import Robot
from gui import ui
from gui.app import Screen
from gui.grid_view import GridView


def fmt_time(seconds):
    if seconds < 1e-3:
        return f"{seconds * 1e6:.0f} us"
    if seconds < 1.0:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.2f} s"


class ResultsScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.res = None
        self.particles = ParticleSystem()
        self.robot = Robot()
        self.view = None
        self.big = None
        self.journey_mode = False
        self.t = 0.0
        self.widgets = ui.WidgetGroup(app)
        y, w = S.HEIGHT - 78, 300
        x = (S.WIDTH - (4 * w + 3 * 20)) // 2
        self.b_journey = self.widgets.add(ui.Button((x, y, w, 52), "VIEW FULL JOURNEY", self.toggle_journey, "blue"))
        self.widgets.add(ui.Button((x + (w + 20), y, w, 52), "VIEW AI ANALYTICS",
                                   lambda: app.go("analytics", source="mission", back="results")))
        self.widgets.add(ui.Button((x + 2 * (w + 20), y, w, 52), "REPLAY MISSION", self.replay, "primary"))
        self.widgets.add(ui.Button((x + 3 * (w + 20), y, w, 52), "MAIN MENU", lambda: app.go("menu")))
        self.close_btn = ui.Button((S.WIDTH - 260, S.HEIGHT - 78, 220, 52), "CLOSE JOURNEY", self.toggle_journey, "primary")

    def enter(self, **kwargs):
        self.res = self.app.state.result
        if self.res is None:
            self.app.go("menu")
            return
        plan = self.res["plan"]
        self.view = GridView(plan.grid, (1100, 218, 440, 440), coords=False)
        self.big = GridView(plan.grid, (30, 76, 760, 720))
        self.robot = Robot(plan.grid.charging_station)
        self.robot.state = "victory" if self.res["success"] else "error"
        self.particles.clear()
        self.journey_mode = False
        self.t = 0.0
        self.b_journey.enabled = len(self.res["journey"]) > 1

    def replay(self):
        self.app.go("simulation", plan=self.res["plan"])

    def toggle_journey(self):
        self.journey_mode = not self.journey_mode
        self.t = 0.0

    def handle(self, event):
        if self.res is None:
            return
        if self.journey_mode:
            self.close_btn.handle(event, self.app)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.toggle_journey()
            return
        if self.widgets.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go("menu")

    def update(self, dt):
        if self.res is None:
            return
        self.t += dt
        self.widgets.update(dt)
        self.close_btn.update(dt, self.app.mouse)
        self.particles.update(dt)
        if self.res["success"] and not self.journey_mode and self.t < 6.0:
            self.particles.confetti(S.WIDTH, 2)
        if self.journey_mode:
            # the robot retraces the recorded journey on a loop
            journey = self.res["journey"]
            if not self.robot.busy:
                i = getattr(self, "_ji", 0)
                if i >= len(journey) - 1 or self.robot.cell != journey[i]:
                    i = 0
                    self.robot.place(journey[0])
                    self.robot.state = "idle"
                else:
                    self.robot.move_to(journey[i + 1], 0.11)
                    i += 1
                self._ji = i
            self.robot.update(dt)
        else:
            self._ji = 0
            self.robot.place(self.res["plan"].grid.charging_station)
            self.robot.state = "victory" if self.res["success"] else "error"
            if self.res["success"]:
                self.robot.target_heading = (self.t * 200) % 360 if (self.t % 3.0) < 1.8 else 180
            self.robot.update(dt)

    # --------------------------------------------------------------- drawing --
    def draw(self, surf):
        app, res = self.app, self.res
        app.draw_background(surf)
        if res is None:
            return
        if self.journey_mode:
            self.draw_journey(surf)
            return
        plan = res["plan"]
        ok = res["success"]
        color = S.GREEN if ok else S.RED
        t = self.t
        pop = ui.ease(min(1.0, t / 0.5))
        ui.glow(surf, (S.WIDTH // 2, 86), 460, color, int(34 * pop))
        ui.text(surf, "MISSION COMPLETED!" if ok else "MISSION FAILED", (S.WIDTH // 2, 80 - int((1 - pop) * 30)),
                62, color, bold=True, anchor="center")
        sub = ("Every dirty location was cleaned and the robot is back on its charging station."
               if ok else res["reason"])
        ui.text(surf, sub, (S.WIDTH // 2, 136), 17, S.WHITE if ok else S.ORANGE, anchor="center", max_width=1400)

        # ---- left: statistics ----------------------------------------------------
        left = pygame.Rect(40, 172, 500, 610)
        y = ui.panel(surf, left, "MISSION STATISTICS", color)
        total, cleaned = res["total_dirty"], len(res["cleaned"])
        tiles = [("DIRTY LOCATIONS", total, S.ORANGE), ("CLEANED", f"{cleaned}/{total}", S.GREEN if cleaned == total else S.RED),
                 ("TOTAL MOVEMENTS", res["moves"], S.CYAN), ("NAVIGATION COST", res["nav_cost"], S.CYAN),
                 ("NODES EXPANDED", res["nodes_expanded"], S.PURPLE), ("ALGORITHM", res["algorithm"], S.ALGO_COLOR[res["algorithm"]])]
        tw, th = (left.w - 60) // 2, 92
        for i, (lab, val, col) in enumerate(tiles):
            tr = pygame.Rect(left.x + 20 + (i % 2) * (tw + 20), y + 6 + (i // 2) * (th + 14), tw, th)
            ui.rrect(surf, S.BG2, tr, 10)
            ui.rrect(surf, S.BORDER, tr, 10, 1)
            ui.text(surf, lab, (tr.x + 14, tr.y + 12), 11, S.MUTED, bold=True)
            shown = val
            if isinstance(val, int):                       # count-up animation
                shown = int(round(val * ui.ease(min(1.0, t / 1.2))))
            ui.text(surf, str(shown), (tr.x + 14, tr.y + 34), 38, col, bold=True)
        y += 3 * (th + 14) + 16
        rows = [("AI execution time (CSP + search)", fmt_time(res["compute_seconds"])),
                ("Simulation time", f"{res['sim_seconds']:.1f} s"),
                ("CSP constraint checks / backtracks", f"{res['csp_checks']} / {res['csp_backtracks']}"),
                ("Returned to charging station", "YES" if res["returned"] else "NO")]
        for key, val in rows:
            ui.text(surf, key, (left.x + 22, y), 15, S.MUTED)
            vc = S.WHITE if val not in ("YES", "NO") else (S.GREEN if val == "YES" else S.RED)
            ui.text(surf, val, (left.right - 22, y), 15, vc, bold=True, anchor="topright")
            y += 30

        # ---- middle: schedule / diagnosis ------------------------------------------
        mid = pygame.Rect(560, 172, 500, 610)
        c = plan.constraints
        if plan.assignment:
            y = ui.panel(surf, mid, "CSP SCHEDULE", S.PURPLE)
            a = plan.assignment
            for task, slot in res["schedule"]:
                done = task in res["cleaned"]
                pos = plan.grid.dirty_locations[task]
                ui.text(surf, slot, (mid.x + 26, y + 3), 18, S.PURPLE, bold=True)
                ui.arrow(surf, S.MUTED, (mid.x + 70, y + 14), (mid.x + 116, y + 14), 2, 6)
                ui.text(surf, task, (mid.x + 134, y + 3), 18, S.WHITE, bold=True)
                ui.text(surf, f"({pos[0]},{pos[1]})", (mid.x + 190, y + 5), 15, S.MUTED, mono=True)
                ui.text(surf, "CLEANED" if done else "NOT CLEANED", (mid.right - 26, y + 6), 12,
                        S.GREEN if done else S.RED, bold=True, anchor="topright")
                y += 32
            y += 8
            pygame.draw.line(surf, S.BORDER, (mid.x + 20, y), (mid.right - 20, y))
            y += 12
            ui.text(surf, "CONSTRAINT VERIFICATION", (mid.x + 26, y), 12, S.CYAN, bold=True)
            y += 24
            checks = [(f"{b} before {aft}:  {a[b]} < {a[aft]}", slot_to_int(a[b]) < slot_to_int(a[aft]))
                      for b, aft in c["precedence"]]
            checks += [(f"{task} by {late}:  {a[task]} <= {late}", slot_to_int(a[task]) <= slot_to_int(late))
                       for task, late in c["latest_slot"]]
            checks.append((f"Slot exclusivity:  {len(set(a.values()))} slots for {len(a)} tasks",
                           len(set(a.values())) == len(a)))
            step = min(26, (mid.bottom - 16 - y) // max(1, len(checks)))
            for line, good in checks:
                if good:
                    ui.check_mark(surf, S.GREEN, (mid.x + 36, y + 8), 12, 3)
                else:
                    ui.text(surf, "X", (mid.x + 30, y - 1), 15, S.RED, bold=True)
                ui.text(surf, line, (mid.x + 58, y), 14, S.WHITE, mono=True, max_width=mid.w - 84)
                y += step
        else:
            y = ui.panel(surf, mid, "WHY THE SCHEDULER FAILED", S.RED)
            y = ui.paragraph(surf, res["reason"], (mid.x + 26, y + 4), 16, mid.w - 52, S.WHITE, 6) + 14
            ui.text(surf, "CONSTRAINTS GIVEN TO THE CSP", (mid.x + 26, y), 12, S.CYAN, bold=True)
            y += 26
            ui.text(surf, f"{len(plan.variables)} tasks ({', '.join(plan.variables)}),  {c['num_slots']} time slots",
                    (mid.x + 26, y), 14, S.WHITE, max_width=mid.w - 52)
            y += 28
            for b, aft in c["precedence"]:
                ui.badge(surf, f"{b} before {aft}", (mid.x + 26, y), S.ORANGE, 13)
                y += 32
            for task, late in c["latest_slot"]:
                ui.badge(surf, f"{task} by {late}", (mid.x + 26, y), S.PURPLE, 13)
                y += 32
            y += 6
            ui.paragraph(surf, f"The backtracking solver tried every option: {res['csp_checks']} constraint checks "
                               f"and {res['csp_backtracks']} backtracks across {len(plan.csp_events)} recorded "
                               "decisions before proving no schedule exists.",
                         (mid.x + 26, y), 14, mid.w - 52, S.MUTED, 5)

        # ---- right: journey map -------------------------------------------------------
        right = pygame.Rect(1080, 172, 480, 610)
        ui.panel(surf, right, "JOURNEY MAP", S.BLUE)
        cleaned_set = set(res["cleaned"])
        journey = res["journey"]
        self.view.draw(surf, app.t, cleaned=cleaned_set, visited=set(journey),
                       path=journey if len(journey) > 1 else None, slots=plan.assignment, accent=S.CYAN)
        if not ok and plan.unreachable:
            for lbl in plan.unreachable:
                cr = self.view.cell_rect(*plan.grid.dirty_locations[lbl])
                ui.rrect(surf, S.RED, cr.inflate(4, 4), 6, 3)
        centre = self.view.center(plan.grid.charging_station)
        bounce = abs(math.sin(t * 5)) * 6 if ok else 0
        self.robot.draw(surf, (centre[0], centre[1] - bounce), self.view.cell * 1.05)
        note = (f"{len(journey) - 1} moves recorded" if len(journey) > 1 else "The robot never left the charger.")
        if not ok and plan.unreachable:
            note += f"   |   unreachable: {', '.join(plan.unreachable)}"
        ui.text(surf, note, (right.centerx, right.bottom - 60), 14, S.MUTED, anchor="center", max_width=right.w - 30)
        ui.text(surf, f"{res['algorithm']} navigation - {plan.grid.rows}x{plan.grid.cols} grid",
                (right.centerx, right.bottom - 34), 13, S.MUTED, anchor="center")

        self.widgets.draw(surf)
        self.particles.draw(surf)

    def draw_journey(self, surf):
        app, res = self.app, self.res
        plan = res["plan"]
        app.header(surf, "FULL JOURNEY", f"{res['algorithm']} - {res['moves']} moves - cost {res['nav_cost']}")
        journey = res["journey"]
        self.big.draw(surf, app.t, cleaned=set(res["cleaned"]), visited=set(journey),
                      path=journey if len(journey) > 1 else None, slots=plan.assignment)
        self.robot.draw(surf, self.big.center((self.robot.row, self.robot.col)), self.big.cell * 1.1)
        panel = pygame.Rect(810, 76, 750, 720)
        y = ui.panel(surf, panel, "LEG-BY-LEG JOURNEY", S.BLUE)
        algo = res["algorithm"]
        legs = plan.legs
        per = max(70, min(118, (panel.bottom - y - 50) // max(1, len(legs))))
        for leg in legs:
            run = plan.run(leg)
            box = pygame.Rect(panel.x + 16, y, panel.w - 32, per - 8)
            ui.rrect(surf, S.BG2, box, 10)
            ui.rrect(surf, S.BORDER if run.found else S.RED, box, 10, 1)
            ui.text(surf, f"LEG {leg.index + 1}", (box.x + 14, box.y + 10), 12, S.CYAN, bold=True)
            ui.text(surf, f"{leg.start_label}  to  {leg.goal_label}" + (f"   ({leg.slot})" if leg.slot else "   (return)"),
                    (box.x + 78, box.y + 8), 16, S.WHITE, bold=True)
            if run.found:
                ui.text(surf, f"cost {run.cost}   nodes {run.nodes_expanded}", (box.right - 14, box.y + 10), 13,
                        S.MUTED, anchor="topright", mono=True)
                cells = " ".join(f"({r},{c})" for r, c in run.path)
                lines = ui.wrap(cells, 12, box.w - 28, mono=True)
                room = max(1, (box.h - 38) // 16)
                if len(lines) > room:
                    lines = lines[:room]
                    lines[-1] = ui.fit(lines[-1] + " ...", 12, box.w - 60, mono=True) + " .."
                for i, line in enumerate(lines):
                    ui.text(surf, line, (box.x + 14, box.y + 34 + i * 16), 12, S.MUTED, mono=True)
            else:
                ui.text(surf, f"NO PATH - {algo} expanded {run.nodes_expanded} nodes and found the goal unreachable",
                        (box.x + 14, box.y + 36), 13, S.RED, max_width=box.w - 28)
            y += per
        ui.text(surf, f"Complete journey: {len(journey)} cells visited in order, "
                      f"starting {'and ending ' if res['returned'] else ''}at the charging station "
                      f"{plan.grid.charging_station}.", (panel.x + 20, panel.bottom - 30), 13, S.MUTED,
                max_width=panel.w - 40)
        self.close_btn.draw(surf)
