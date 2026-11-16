"""Simulation and AI Control Center: the main screen of the game.

The screen replays a :class:`core.integration.MissionPlan`.  The CSP trace is
shown first, then for every leg the search trace followed by the robot driving
the path that search returned.  The plan is computed once; RESTART and the
playback controls never recompute it.
"""
import math

import pygame

from config import settings as S
from entities.particles import ParticleSystem
from entities.robot import DIRECTION_NAMES, Robot
from gui import ui
from gui.ai_brain import AIBrainPanel
from gui.app import Screen
from gui.grid_view import GridView, draw_legend
from gui.playback import CSPPlayback, SearchPlayback
from gui.schedule_panel import SchedulePanel

GRID_RECT = (16, 70, 744, 732)
BRAIN_RECT = (774, 70, 408, 760)
COL_X, COL_W = 1194, 390


class SimulationScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.plan = None
        self.particles = ParticleSystem()
        self.brain = AIBrainPanel(BRAIN_RECT)
        self.schedule = SchedulePanel((COL_X, 268, COL_W, 300))
        self.widgets = ui.WidgetGroup(app)
        y, h = 842, 46
        self.b_play = self.widgets.add(ui.Button((16, y, 110, h), "PLAY", self.play, "primary"))
        self.b_pause = self.widgets.add(ui.Button((134, y, 110, h), "PAUSE", self.pause, "orange"))
        self.b_resume = self.widgets.add(ui.Button((252, y, 120, h), "RESUME", self.resume, "green"))
        self.b_step = self.widgets.add(ui.Button((380, y, 140, h), "NEXT STEP", self.next_step, "blue", sound="tick"))
        self.b_restart = self.widgets.add(ui.Button((528, y, 124, h), "RESTART", self.restart))
        self.b_menu = self.widgets.add(ui.Button((660, y, 140, h), "MAIN MENU", lambda: app.go("menu")))
        self.speed = self.widgets.add(ui.Segmented((1194, y + 2, 390, h - 4), [n for n, _ in S.SPEEDS],
                                                   app.state.speed, self.set_speed, 13))
        self.b_results = self.widgets.add(ui.Button((812, y, 170, h), "VIEW RESULTS", self.show_results, "primary"))

    # ------------------------------------------------------------ lifecycle --
    def enter(self, plan=None, **kwargs):
        if plan is not None:
            self.plan = plan
        if self.plan is None:
            self.app.go("missions")
            return
        self.speed.value = self.app.state.speed
        self.reset()

    def reset(self):
        plan, st = self.plan, self.app.state
        g = plan.grid
        self.view = GridView(g, GRID_RECT)
        self.robot = Robot(g.charging_station, heading=180)
        self.particles.clear()
        self.csp = CSPPlayback(plan.csp_events, plan.variables, plan.constraints["time_slots"])
        self.search = None
        self.nav_log = []
        self._log_i = 0
        self.phase = "csp"
        self.leg_i = -1
        self.cleaned = []
        self.visited = {g.charging_station}
        self.journey = [g.charging_station]
        self.path_cells = []
        self.moves = 0
        self.nav_cost = 0
        self.nodes_done = 0
        self.timer = 0.0
        self.work_started = False      # a clean / charge action is in progress
        self.step_budget = 0
        self.elapsed = 0.0
        self.end_timer = 0.0
        self.finished = None           # None | "success" | "failed"
        self.fail_reason = ""
        self.result_sent = False
        self.running = st.mode == "AUTOMATIC"
        self.started = self.running
        self.robot.state = "thinking" if self.running else "idle"
        self.schedule.selected = None

    def set_speed(self, value):
        self.app.state.speed = value

    # ------------------------------------------------------------- controls --
    def play(self):
        if self.finished is None:
            self.running = self.started = True

    def pause(self):
        self.running = False

    def resume(self):
        if self.finished is None and self.started:
            self.running = True

    def next_step(self):
        if self.finished is not None:
            return
        self.running = False
        self.started = True
        if self.phase == "csp":
            self._csp_tick()
        elif self.phase == "csp_done":
            self._begin_leg(0)
        elif self.phase == "search":
            self._search_tick()
        else:
            self.step_budget = 1       # one move / one clean / the docking

    def restart(self):
        self.reset()

    def show_results(self):
        if self.finished is not None:
            self._send_result()

    @property
    def active(self):
        return self.finished is None and (self.running or self.step_budget > 0)

    def handle(self, event):
        if self.schedule.selected is not None:
            self.schedule.handle(event)
            return
        if self.widgets.handle(event):
            return
        if self.schedule.handle(event):
            self.app.audio.play("click")
            return
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_SPACE:
                if self.running:
                    self.pause()
                elif self.started:
                    self.resume()
                else:
                    self.play()
            elif k in (pygame.K_n, pygame.K_RIGHT):
                self.next_step()
            elif k == pygame.K_r:
                self.restart()
            elif k == pygame.K_ESCAPE:
                self.app.go("menu")
            elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self.speed.value = S.SPEEDS[k - pygame.K_1][0]
                self.set_speed(self.speed.value)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.show_results()

    # ------------------------------------------------------- mission engine --
    @property
    def leg(self):
        return self.plan.legs[self.leg_i] if 0 <= self.leg_i < len(self.plan.legs) else None

    def _nav(self, tag, text):
        self.nav_log.append((tag, text))

    def _csp_tick(self):
        self.csp.step()
        self.app.audio.play("tick")
        if self.csp.done:
            if self.csp.solved:
                self.phase, self.timer = "csp_done", 0.0
                self.app.audio.play("cleaned")
            else:
                self._fail(self.plan.failure_reason or "No feasible cleaning schedule exists.")

    def _begin_leg(self, index):
        self.leg_i = index
        leg = self.leg
        if leg is None:                      # defensive; plans always end with a C leg
            self._fail("Mission plan ended before the robot returned to the charging station.")
            return
        run = self.plan.run(leg)
        self.search = SearchPlayback(run)
        self._log_i = 0
        self.phase, self.timer = "search", 0.0
        self.robot.state = "thinking"
        self._nav("NAV", f"Leg {index + 1}/{self.total_legs}: {leg.start_label} {run.start} -> "
                         f"{leg.goal_label} {run.goal}")

    @property
    def total_legs(self):
        return len(self.plan.ordered_schedule) + 1

    def _search_tick(self):
        s = self.search
        s.step()
        self.nav_log.extend(s.log[self._log_i:])
        self._log_i = len(s.log)
        if len(self.nav_log) > 400:
            del self.nav_log[:200]
        if not s.done:
            return
        self.nodes_done += s.nodes_expanded
        if s.failed or s.path is None:
            self._fail(self.plan.failure_reason or "Navigation failure: destination unreachable.")
            return
        self.nav_cost += self.plan.run(self.leg).cost
        self.path_cells = list(s.path[1:])
        self.phase = "move"
        self.work_started = False
        self.robot.state = "idle"

    def _arrive_cell(self):
        cell = self.robot.cell
        self.journey.append(cell)
        self.visited.add(cell)
        self.moves += 1
        self.robot.battery = max(5.0, self.robot.battery - S.BATTERY_PER_MOVE)
        self.app.audio.play("move")

    def _arrive_goal(self):
        self.timer = 0.0
        self.work_started = False
        self.phase = "charge" if self.leg.goal_label == "C" else "clean"

    def _finish_clean(self):
        label = self.leg.goal_label
        self.cleaned.append(label)
        centre = self.view.center(self.robot.cell)
        self.particles.sparkle(centre, self.view.cell * 0.55, 18)
        self.app.audio.play("cleaned")
        self._nav("NAV", f"{label} cleaned ({len(self.cleaned)}/{len(self.plan.grid.dirty_locations)}).")
        self._begin_leg(self.leg_i + 1)

    def _finish_charge(self):
        g = self.plan.grid
        self.robot.battery = 100.0
        all_clean = set(self.cleaned) == set(g.dirty_locations)
        home = self.robot.cell == g.charging_station
        # Success is only ever reported when the simulated robot really cleaned
        # everything, is back on the charger, and the planner agrees.
        if all_clean and home and self.plan.success:
            self.finished = "success"
            self.phase = "done"
            self.robot.state = "victory"
            self.running = False
            self.app.audio.play("success")
            self._nav("NAV", "Docked. Mission complete.")
        else:
            self._fail("Mission ended without cleaning every location.")

    def _fail(self, reason):
        self.finished = "failed"
        self.fail_reason = reason
        self.phase = "failed"
        self.robot.state = "error"
        self.running = False
        self.step_budget = 0
        self.app.audio.play("fail")
        self._nav("FAIL", reason)

    def _send_result(self):
        plan = self.plan
        self.result_sent = True
        self.app.state.result = {
            "success": self.finished == "success",
            "reason": self.fail_reason,
            "status": plan.status if self.finished == "failed" else "ok",
            "plan": plan,
            "algorithm": plan.algorithm,
            "total_dirty": len(plan.grid.dirty_locations),
            "cleaned": list(self.cleaned),
            "journey": list(self.journey),
            "moves": self.moves,
            "nav_cost": self.nav_cost,
            "nodes_expanded": self.nodes_done,
            "schedule": list(plan.ordered_schedule),
            "returned": self.robot.cell == plan.grid.charging_station and self.finished == "success",
            "sim_seconds": self.elapsed,
            "compute_seconds": plan.csp_seconds + sum(plan.run(l).seconds for l in plan.legs),
            "csp_backtracks": self.csp.backtracks,
            "csp_checks": self.csp.checks,
        }
        self.app.go("results")

    def update(self, dt):
        if self.plan is None:
            return
        speed = self.app.state.speed_factor
        self.widgets.update(dt)
        self.particles.update(dt)
        robot = self.robot
        if robot.update(dt):
            self._arrive_cell()
        centre = self.view.center((robot.row, robot.col))
        cell = self.view.cell
        if self.active:
            self.elapsed += dt

        if self.phase == "csp" and self.running:
            robot.state = "thinking"
            self.timer += dt * speed
            while self.timer >= S.CSP_EVENT_SECONDS and self.phase == "csp":
                self.timer -= S.CSP_EVENT_SECONDS
                self._csp_tick()
        elif self.phase == "csp_done" and self.running:
            self.timer += dt * speed
            if self.timer >= 1.0:
                self._begin_leg(0)
        elif self.phase == "search" and self.running:
            self.timer += dt * speed
            n = 0
            while self.timer >= S.SEARCH_STEP_SECONDS and self.phase == "search" and n < 12:
                self.timer -= S.SEARCH_STEP_SECONDS
                self._search_tick()
                n += 1
            if n:
                self.app.audio.play("tick")
        elif self.phase == "move":
            if not robot.busy:
                if not self.path_cells:
                    self._arrive_goal()
                elif self.active:
                    robot.move_to(self.path_cells.pop(0), S.MOVE_SECONDS / speed)
                    self.step_budget = 0
                else:
                    robot.state = "idle"
            elif int(self.app.t * 60) % 3 == 0:
                self.particles.trail((centre[0], centre[1]), cell * 0.5, S.CYAN)
        if self.phase in ("clean", "charge"):
            if not self.work_started and self.active:
                self.work_started = True
                self.step_budget = 0
                robot.state = "cleaning" if self.phase == "clean" else "charging"
                self.app.audio.play("clean" if self.phase == "clean" else "charge")
            if self.work_started:
                self.timer += dt * speed
                if self.phase == "clean":
                    self.particles.dust(centre, cell * 0.42, 2)
                    if self.timer >= S.CLEAN_SECONDS:
                        self._finish_clean()
                else:
                    k = min(1.0, self.timer / S.CHARGE_SECONDS)
                    robot.charge_level = k
                    self.particles.energy(centre, cell * 0.7, 2, S.BLUE)
                    if k >= 1.0:
                        self._finish_charge()
            elif not robot.busy:
                robot.state = "idle"

        if self.finished is not None:
            self.end_timer += dt
            if self.finished == "success" and int(self.app.t * 60) % 4 == 0:
                self.particles.sparkle(centre, cell * 0.8, 2, S.CYAN)
            wait = 2.4 if self.finished == "success" else 3.2
            if self.end_timer >= wait and not self.result_sent and self.app.state.mode == "AUTOMATIC":
                self._send_result()

        done = self.finished is not None
        self.b_play.enabled = not self.started and not done
        self.b_pause.enabled = self.running and not done
        self.b_resume.enabled = self.started and not self.running and not done
        self.b_step.enabled = not done
        self.b_results.visible = done

    # --------------------------------------------------------------- status --
    def task_status(self, label):
        if label in self.cleaned:
            return "completed"
        if not self.csp.solved:
            return "unscheduled" if self.csp.failed else "scheduling"
        leg = self.leg
        if leg is not None and leg.goal_label == label and self.finished is None:
            return "current"
        return "pending"

    def action_text(self):
        ph = self.phase
        if ph == "failed":
            return "MISSION ABORTED", S.RED
        if ph == "done":
            return "MISSION COMPLETE", S.GREEN
        if not self.started:
            return "READY - PRESS PLAY", S.MUTED
        paused = "" if self.active or self.robot.busy or self.work_started else "  (PAUSED)"
        if ph == "csp":
            return "SCHEDULING TASKS" + paused, S.PURPLE
        if ph == "csp_done":
            return "SCHEDULE READY" + paused, S.GREEN
        if ph == "search":
            return f"PLANNING PATH ({self.plan.algorithm})" + paused, S.ALGO_COLOR[self.plan.algorithm]
        if ph == "move":
            d = DIRECTION_NAMES.get(self.robot.direction, "")
            return (f"MOVING {d}" if self.robot.busy else "MOVING") + paused, S.CYAN
        if ph == "clean":
            return "CLEANING" + paused, S.GREEN
        return "CHARGING" + paused, S.BLUE

    # --------------------------------------------------------------- drawing --
    def draw(self, surf):
        app, plan = self.app, self.plan
        app.draw_background(surf)
        if plan is None:
            return
        g = plan.grid
        t = app.t
        app.header(surf, "AI CONTROL CENTER", app.state.mission_title)
        algo = plan.algorithm
        acol = S.ALGO_COLOR[algo]
        leg = self.leg

        # ---- grid ---------------------------------------------------------------
        slots = dict(self.csp.assignment) if self.csp.solved else None
        searching = self.phase == "search" or (self.phase == "failed" and self.search is not None)
        path = None
        if self.phase == "move":
            path = [(self.robot.row, self.robot.col)] + self.path_cells
        current = leg.goal_label if leg is not None and self.finished is None else None
        self.view.draw(surf, t, cleaned=self.cleaned, visited=self.visited, path=path,
                       playback=self.search if searching else None, slots=slots, accent=acol,
                       current_task=current, charging=self.phase == "charge" and self.work_started)
        self.robot.draw(surf, self.view.center((self.robot.row, self.robot.col)), self.view.cell * 1.12)
        self.particles.draw(surf)
        draw_legend(surf, (24, 810), ("charger", "obstacle", "dirty", "cleaned", "visited", "path",
                                      "explored", "frontier"), acol, spacing=14, size=12)

        # ---- AI brain -------------------------------------------------------------
        leg_text = f"{self.leg_i + 1}/{self.total_legs}  {leg.name}" if leg is not None else ""
        self.brain.draw(surf, t, self.csp, self.search, self.nav_log, self.phase, algo, leg_text)

        # ---- A. robot status --------------------------------------------------------
        r = pygame.Rect(COL_X, 70, COL_W, 190)
        y = ui.panel(surf, r, "ROBOT STATUS")
        action, a_col = self.action_text()
        ui.badge(surf, action, (r.right - 14, r.y + 10), a_col, 11, anchor="topright")
        pos = self.robot.cell
        if leg is not None and self.finished is None:
            goal = plan.run(leg).goal
            dest = f"{leg.goal_label} ({goal[0]},{goal[1]})"
            task = f"{leg.slot} - clean {leg.goal_label}" if leg.goal_label != "C" else "Return to charger"
        else:
            dest = "-"
            task = "Solve cleaning schedule" if self.phase in ("csp", "csp_done") else "-"
        for key, val in (("Position", f"({pos[0]},{pos[1]})"), ("Destination", dest), ("Current task", task)):
            ui.text(surf, key, (r.x + 18, y), 14, S.MUTED)
            ui.text(surf, val, (r.right - 18, y), 14, S.WHITE, bold=True, anchor="topright", max_width=230)
            y += 24
        total = len(g.dirty_locations)
        ui.text(surf, "Cleaning progress", (r.x + 18, y + 2), 14, S.MUTED)
        ui.text(surf, f"{len(self.cleaned)}/{total}", (r.right - 18, y + 2), 14, S.GREEN, bold=True, anchor="topright")
        ui.progress_bar(surf, (r.x + 150, y + 6, r.w - 216, 10), len(self.cleaned) / max(1, total), S.GREEN)
        y += 26
        batt = self.robot.battery if self.phase != "charge" or not self.work_started else \
            self.robot.battery + (100 - self.robot.battery) * self.robot.charge_level
        ui.text(surf, "Battery", (r.x + 18, y + 2), 14, S.MUTED)
        ui.text(surf, f"{batt:.0f}%", (r.right - 18, y + 2), 14, S.WHITE, bold=True, anchor="topright")
        ui.progress_bar(surf, (r.x + 150, y + 6, r.w - 216, 10), batt / 100,
                        S.GREEN if batt > 50 else (S.ORANGE if batt > 20 else S.RED))

        # ---- B. schedule --------------------------------------------------------------
        self.schedule.draw(surf, t, plan, self.csp.assignment, self.csp.solved, self.task_status, app.mouse,
                           home_done=self.finished == "success")

        # ---- C. navigation -------------------------------------------------------------
        r = pygame.Rect(COL_X, 576, COL_W, 124)
        y = ui.panel(surf, r, "NAVIGATION", acol)
        ui.badge(surf, algo, (r.right - 14, r.y + 10), acol, 12, anchor="topright", filled=True)
        run = plan.run(leg) if leg is not None else None
        planned = run is not None and self.phase not in ("search",) and run.found
        live_nodes = self.search.nodes_expanded if self.search is not None else 0
        direction = DIRECTION_NAMES.get(self.robot.direction, "-") if self.phase == "move" else "-"
        left = [("Leg", f"{self.leg_i + 1} of {self.total_legs}: {leg.name}" if leg else "-"),
                ("Path cost", str(run.cost) if planned else ("searching" if self.phase == "search" else "-")),
                ("Nodes expanded", str(live_nodes) if leg else "-")]
        for key, val in left:
            ui.text(surf, key, (r.x + 18, y), 14, S.MUTED)
            ui.text(surf, val, (r.x + 132, y), 14, S.WHITE, bold=True, max_width=150)
            y += 25
        ui.text(surf, "DIRECTION", (r.right - 56, r.y + 46), 10, S.MUTED, bold=True, anchor="midtop")
        self._compass(surf, (r.right - 56, r.y + 86), direction, acol)

        # ---- D. statistics ----------------------------------------------------------------
        r = pygame.Rect(COL_X, 708, COL_W, 122)
        y = ui.panel(surf, r, "MISSION STATISTICS", S.GREEN)
        nodes = self.nodes_done + (live_nodes if self.phase == "search" else 0)
        cells = [("DIRTY", total, S.ORANGE), ("CLEANED", len(self.cleaned), S.GREEN),
                 ("REMAINING", total - len(self.cleaned), S.WHITE), ("MOVES", self.moves, S.CYAN),
                 ("NAV COST", self.nav_cost, S.CYAN), ("NODES", nodes, S.PURPLE)]
        w = (r.w - 24) / len(cells)
        for i, (lab, val, col) in enumerate(cells):
            cx = r.x + 12 + (i + 0.5) * w
            ui.text(surf, str(val), (cx, y + 8), 26, col, bold=True, anchor="midtop")
            ui.text(surf, lab, (cx, y + 46), 10, S.MUTED, bold=True, anchor="midtop")
        ui.text(surf, f"mission time {self.elapsed:5.1f}s", (r.right - 14, r.y + 13), 12, S.MUTED,
                anchor="topright", mono=True)

        # ---- controls -------------------------------------------------------------------------
        self.widgets.draw(surf)
        if not self.b_results.visible:
            mode = app.state.mode
            hint = "SPACE play/pause   N step   R restart   1-4 speed"
            ui.text(surf, f"{mode} MODE", (816, 850), 12, S.CYAN, bold=True)
            ui.text(surf, hint, (816, 868), 12, S.MUTED)
        ui.text(surf, "SPEED", (1186, 865), 11, S.MUTED, bold=True, anchor="midright")

        if self.finished is not None:
            self._banner(surf, t)
        self.schedule.draw_inspector(surf, plan, self.csp.assignment, self.task_status)

    def _compass(self, surf, center, direction, color):
        cx, cy = center
        pygame.draw.circle(surf, S.DARK, (cx, cy), 28)
        pygame.draw.circle(surf, S.BORDER, (cx, cy), 28, 1)
        for name, (dx, dy) in (("UP", (0, -1)), ("RIGHT", (1, 0)), ("DOWN", (0, 1)), ("LEFT", (-1, 0))):
            on = name == direction
            tip = (cx + dx * 20, cy + dy * 20)
            base = (cx + dx * 9, cy + dy * 9)
            px, py = -dy * 6, dx * 6
            pygame.draw.polygon(surf, color if on else S.BORDER,
                                [tip, (base[0] + px, base[1] + py), (base[0] - px, base[1] - py)])
        ui.text(surf, direction, (cx, cy + 32), 10, color if direction != "-" else S.MUTED, bold=True, anchor="midtop")

    def _banner(self, surf, t):
        ok = self.finished == "success"
        color = S.GREEN if ok else S.RED
        k = ui.ease(min(1.0, self.end_timer / 0.35))
        box = pygame.Rect(0, 0, 640, 104 if ok else 138)
        box.midbottom = (self.view.rect.centerx, self.view.rect.bottom - 14 + int((1 - k) * 30))
        ui.rrect_alpha(surf, S.DARK, box, 16, int(235 * k))
        ui.rrect(surf, color, box, 16, 2)
        ui.text(surf, "MISSION COMPLETED!" if ok else "MISSION FAILED", (box.centerx, box.y + 16), 34, color,
                bold=True, anchor="midtop")
        if ok:
            ui.text(surf, "All locations cleaned - robot docked at the charging station.",
                    (box.centerx, box.y + 66), 15, S.WHITE, anchor="midtop")
        else:
            lines = ui.wrap(self.fail_reason, 14, box.w - 40)[:3]
            for i, line in enumerate(lines):
                ui.text(surf, line, (box.centerx, box.y + 64 + i * 21), 14, S.WHITE, anchor="midtop")
