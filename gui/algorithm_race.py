"""AI ALGORITHM RACE and the single-algorithm exploration visualiser.

RACE:    BFS and A* solve the identical navigation problem side by side.
EXPLORE: one algorithm is replayed on a large grid with per-cell values
         (BFS depth, or A* f / g / h).

Both algorithms are run by ``core.integration.compare_algorithms`` on the same
grid, start and goal.  Playback advances both by one node expansion per tick,
so neither is slowed down or sped up: the one that needs fewer expansions
simply finishes its search first.
"""
import glob
import os

import pygame

from config import settings as S
from core.environment import InputError, load_environment_checked
from core.integration import compare_algorithms, comparison_summary
from entities.particles import ParticleSystem
from entities.robot import Robot
from gui import ui
from gui.ai_brain import draw_log, stat_tile
from gui.app import Screen
from gui.grid_view import GridView, draw_legend
from gui.playback import SearchPlayback
from gui.results_screen import fmt_time

MODES = ["RACE", "EXPLORE BFS", "EXPLORE A*"]
LEFT_RECT = (20, 122, 566, 500)
RIGHT_RECT = (600, 122, 566, 500)
BIG_RECT = (20, 76, 760, 760)
PANEL_X, PANEL_W = 1182, 398


class Racer:
    """One algorithm's playback plus the robot that drives its path."""
    def __init__(self, run):
        self.run = run
        self.playback = SearchPlayback(run)
        self.robot = Robot(run.start)
        self.robot.state = "thinking"
        self.todo = None          # remaining path cells once the search is done
        self.arrived = False
        self.moves = 0
        self.log_i = 0

    @property
    def status(self):
        pb = self.playback
        if pb.failed:
            return "NO PATH", S.RED
        if self.arrived:
            return "ARRIVED", S.GREEN
        if pb.done:
            return "PATH FOUND", S.CYAN
        return ("SEARCHING", S.ORANGE) if pb.i else ("READY", S.MUTED)

    @property
    def finished(self):
        return self.arrived or self.playback.failed


class AlgorithmRace(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.mode = "RACE"
        self.grid = None
        self.env_path = ""
        self.env_paths = []
        self.error = ""
        self.start = self.goal = None
        self.targets = []
        self.racers = {}
        self.views = {}
        self.particles = ParticleSystem()
        self.running = False
        self.started = False
        self.timer = 0.0
        self.summary = []
        self.log = []
        self.speed_name = "NORMAL"
        self.widgets = ui.WidgetGroup(app)
        x, w = PANEL_X + 16, PANEL_W - 32
        self.seg_mode = self.widgets.add(ui.Segmented((x, 112, w, 42), MODES, self.mode, self.set_mode, 12))
        half = (w - 10) // 2
        self.widgets.add(ui.Button((x, 232, half, 38), "NEXT ENVIRONMENT", self.next_env, size=12))
        self.widgets.add(ui.Button((x + half + 10, 232, half, 38), "LOAD FILE", self.load_file, size=12))
        self.widgets.add(ui.Button((x, 352, half, 38), "NEXT TARGET", self.next_target, size=12))
        self.widgets.add(ui.Button((x + half + 10, 352, half, 38), "SWAP START / GOAL", self.swap, size=12))
        self.seg_speed = self.widgets.add(ui.Segmented((x, 452, w, 40), [n for n, _ in S.SPEEDS], self.speed_name,
                                                       lambda v: setattr(self, "speed_name", v), 12))
        self.b_start = self.widgets.add(ui.Button((x, 514, w, 54), "START RACE", self.start_run, "primary", size=20,
                                                  sound="start"))
        third = (w - 20) // 3
        self.b_pause = self.widgets.add(ui.Button((x, 580, third, 44), "PAUSE", self.pause, "orange", size=14))
        self.b_resume = self.widgets.add(ui.Button((x + third + 10, 580, third, 44), "RESUME", self.resume, "green", size=14))
        self.b_step = self.widgets.add(ui.Button((x + 2 * (third + 10), 580, third, 44), "STEP", self.step, "blue",
                                                 size=14, sound="tick"))
        self.back_target = "menu"
        self.widgets.add(ui.Button((x, 636, third, 44), "RESTART", self.restart, size=13))
        self.b_back = self.widgets.add(ui.Button((x + third + 10, 636, third, 44), "< BACK", self.on_back, "primary", size=13))
        self.widgets.add(ui.Button((x + 2 * (third + 10), 636, third, 44), "MAIN MENU", lambda: app.go("menu"), size=13))

    # --------------------------------------------------------------- set-up --
    def enter(self, back=None, **kwargs):
        if back:
            self.back_target = back
        elif getattr(self.app, "prev_screen", None) in ("analytics", "results", "menu"):
            self.back_target = self.app.prev_screen
        else:
            self.back_target = "menu"
        self.b_back.label = "< ANALYTICS" if self.back_target == "analytics" else ("< RESULTS" if self.back_target == "results" else "< BACK")

        paths = [os.path.join(S.ROOT_DIR, m["env"]) for m in S.MISSIONS]
        paths += sorted(glob.glob(os.path.join(S.CUSTOM_ENV_DIR, "*.txt")))
        current = self.app.state.env_path
        if current not in paths:
            paths.append(current)
        self.env_paths = paths
        if self.grid is None:
            self.set_env(current if os.path.isfile(current) else paths[0])
        else:
            self.restart()

    def set_env(self, path):
        try:
            grid = load_environment_checked(path)
        except InputError as exc:
            self.error = str(exc)
            self.app.audio.play("error")
            if self.grid is None:                      # fall back to the first loadable preset
                for other in self.env_paths:
                    try:
                        grid = load_environment_checked(other)
                        path = other
                        break
                    except InputError:
                        continue
                else:
                    return
            else:
                return
        else:
            self.error = ""
        self.grid, self.env_path = grid, path
        self.start = grid.charging_station
        self.targets = list(grid.dirty_locations.items()) + [("C", grid.charging_station)]
        self.goal = next(iter(grid.dirty_locations.values()))      # default problem: C -> D1
        self.views = {"BFS": GridView(grid, LEFT_RECT), "A*": GridView(grid, RIGHT_RECT),
                      "BIG": GridView(grid, BIG_RECT)}
        self.compute()

    def compute(self):
        """Run both algorithms on the identical problem and reset playback."""
        runs = compare_algorithms(self.grid, self.start, self.goal, repeats=40)
        self.racers = {algo: Racer(run) for algo, run in runs.items()}
        self.particles.clear()
        self.running = self.started = False
        self.timer = 0.0
        self.summary = []
        self.log = []

    def restart(self):
        if self.grid is not None:
            self.compute()

    def set_mode(self, mode):
        self.mode = mode
        self.restart()

    def next_env(self):
        if self.env_paths:
            i = self.env_paths.index(self.env_path) if self.env_path in self.env_paths else -1
            self.set_env(self.env_paths[(i + 1) % len(self.env_paths)])

    def load_file(self):
        def chosen(path):
            if path not in self.env_paths:
                self.env_paths.append(path)
            self.set_env(path)
            if self.error:
                self.app.notify(self.error, S.RED, 5)
        self.app.modal = ui.FilePicker(self.app, "SELECT ENVIRONMENT FILE", chosen)

    def next_target(self):
        cells = [p for _, p in self.targets if p != self.start]
        if not cells:
            return
        i = cells.index(self.goal) if self.goal in cells else -1
        self.goal = cells[(i + 1) % len(cells)]
        self.compute()

    def swap(self):
        self.start, self.goal = self.goal, self.start
        self.compute()

    def label_of(self, pos):
        if pos == self.grid.charging_station:
            return "C"
        return self.grid.pos_to_dirty.get(pos, "")

    # ------------------------------------------------------------- playback --
    @property
    def active(self):
        """The racers taking part in the current mode."""
        if self.mode == "RACE":
            return [self.racers["BFS"], self.racers["A*"]]
        return [self.racers["BFS" if self.mode == "EXPLORE BFS" else "A*"]]

    @property
    def finished(self):
        return bool(self.racers) and all(r.finished for r in self.active)

    @property
    def speed(self):
        return dict(S.SPEEDS)[self.speed_name]

    def start_run(self):
        if self.finished:
            self.compute()
        self.running = self.started = True

    def pause(self):
        self.running = False

    def resume(self):
        if self.started and not self.finished:
            self.running = True

    def step(self):
        if self.finished:
            return
        self.running = False
        self.started = True
        self.tick()
        for r in self.active:           # in step mode each step also moves the robots one cell
            self._drive(r, force=True)

    def tick(self):
        """One synchronous step: every unfinished search expands one node."""
        for r in self.active:
            pb = r.playback
            if not pb.done:
                pb.step()
                if self.mode != "RACE":
                    self.log.extend(pb.log[r.log_i:])
                    r.log_i = len(pb.log)
                if pb.done:
                    if pb.path is not None:
                        r.todo = list(pb.path[1:])
                        r.robot.state = "idle"
                        self.app.audio.play("cleaned")
                    else:
                        r.robot.state = "error"
                        self.app.audio.play("fail")

    def _drive(self, r, force=False):
        if r.todo is None or r.arrived or r.robot.busy:
            return
        if not r.todo:
            r.arrived = True
            r.robot.state = "victory"
            view = self.views["BIG" if self.mode != "RACE" else r.run.algorithm]
            self.particles.sparkle(view.center(r.robot.cell), view.cell * 0.6, 16, S.ALGO_COLOR[r.run.algorithm])
            return
        if self.running or force:
            r.robot.move_to(r.todo.pop(0), S.MOVE_SECONDS * 0.7 / self.speed)

    def update(self, dt):
        self.widgets.update(dt)
        self.particles.update(dt)
        if not self.racers:
            return
        if self.running:
            self.timer += dt * self.speed
            interval = S.SEARCH_STEP_SECONDS * 1.4
            n = 0
            while self.timer >= interval and n < 10:
                self.timer -= interval
                self.tick()
                n += 1
            if n:
                self.app.audio.play("tick")
        for r in self.active:
            if r.robot.update(dt):
                r.moves += 1
                self.app.audio.play("move")
            self._drive(r)
        if self.finished:
            if self.running or not self.summary:
                self.running = False
                bfs, astar = self.racers["BFS"].run, self.racers["A*"].run
                self.summary = comparison_summary(bfs, astar)
                if self.started:
                    self.app.audio.play("success" if any(r.arrived for r in self.active) else "fail")
        done = self.finished
        self.b_start.label = ("RACE AGAIN" if done else "START RACE") if self.mode == "RACE" else \
            ("EXPLORE AGAIN" if done else "START EXPLORATION")
        self.b_start.enabled = not self.running
        self.b_pause.enabled = self.running
        self.b_resume.enabled = self.started and not self.running and not done
        self.b_step.enabled = not done

    def on_back(self):
        target = self.back_target or "menu"
        if target == "results" and self.app.state.result is None:
            target = "menu"
        self.app.go(target)

    def handle(self, event):
        if self.widgets.handle(event):
            return
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                self.on_back()
            elif k == pygame.K_SPACE:
                if self.running:
                    self.pause()
                elif self.started and not self.finished:
                    self.resume()
                else:
                    self.start_run()
            elif k in (pygame.K_n, pygame.K_RIGHT):
                self.step()
            elif k == pygame.K_r:
                self.restart()
            elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self.speed_name = self.seg_speed.value = S.SPEEDS[k - pygame.K_1][0]
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3) and self.grid is not None:
            views = [self.views["BFS"], self.views["A*"]] if self.mode == "RACE" else [self.views["BIG"]]
            for view in views:
                cell = view.cell_at(event.pos)
                if cell is None:
                    continue
                if not self.grid.is_valid_cell(*cell):
                    self.app.notify("That cell is an obstacle.", S.ORANGE, 2)
                elif event.button == 1 and cell != self.start:
                    self.goal = cell
                    self.compute()
                    self.app.audio.play("click")
                elif event.button == 3 and cell != self.goal:
                    self.start = cell
                    self.compute()
                    self.app.audio.play("click")
                break

    # --------------------------------------------------------------- drawing --
    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        race = self.mode == "RACE"
        app.header(surf, "AI ALGORITHM RACE" if race else "ALGORITHM EXPLORATION",
                   "BFS vs A* on the identical problem" if race else
                   "Watch one algorithm explore the environment node by node", S.ORANGE if race else S.CYAN)
        if self.grid is None:
            ui.text(surf, self.error or "No environment could be loaded.", (S.WIDTH // 2, 400), 20, S.RED,
                    anchor="center", max_width=1200)
            self.widgets.draw(surf)
            return
        if race:
            self.draw_race(surf)
        else:
            self.draw_explore(surf)
        self.draw_controls(surf)
        self.particles.draw(surf)

    def draw_side(self, surf, algo, view, values=False):
        r = self.racers[algo]
        col = S.ALGO_COLOR[algo]
        pb = r.playback
        path = None
        if pb.path is not None:
            path = [(r.robot.row, r.robot.col)] + r.todo if not r.arrived else pb.path
        view.draw(surf, self.app.t, playback=pb, path=path, start=self.start, goal=self.goal,
                  accent=col, tasks=False, show_values=values)
        r.robot.draw(surf, view.center((r.robot.row, r.robot.col)), view.cell * 1.1)

    def draw_race(self, surf):
        t = self.app.t
        for algo, rect in (("BFS", LEFT_RECT), ("A*", RIGHT_RECT)):
            r = self.racers[algo]
            col = S.ALGO_COLOR[algo]
            x, y, w, _ = rect
            pygame.draw.rect(surf, col, (x + 8, y - 40, 5, 26), border_radius=2)
            ui.text(surf, f"{algo} ROBOT", (x + 22, y - 42), 24, col, bold=True)
            ui.text(surf, "uninformed - FIFO queue" if algo == "BFS" else "informed - f(n) = g(n) + h(n)",
                    (x + 22 + (150 if algo == "BFS" else 136), y - 34), 13, S.MUTED)
            label, scol = r.status
            ui.badge(surf, label, (x + w - 4, y - 28), scol, 12, anchor="midright", filled=label == "ARRIVED")
            self.draw_side(surf, algo, self.views[algo])

        # ---- live statistics table ------------------------------------------------
        box = pygame.Rect(20, 634, 700, 248)
        y = ui.panel(surf, box, "LIVE STATISTICS", S.ORANGE)
        cx = [box.x + 24, box.x + 330, box.x + 540]
        ui.text(surf, "METRIC", (cx[0], y), 11, S.MUTED, bold=True)
        ui.text(surf, "BFS", (cx[1], y - 3), 15, S.ALGO_COLOR["BFS"], bold=True)
        ui.text(surf, "A*", (cx[2], y - 3), 15, S.ALGO_COLOR["A*"], bold=True)
        y += 24
        b, a = self.racers["BFS"], self.racers["A*"]
        done = self.finished

        def cell(r, kind):
            pb, run = r.playback, r.run
            if kind == "nodes":
                return pb.nodes_expanded, str(pb.nodes_expanded)
            if not pb.done:
                return None, "searching..." if pb.i else "-"
            if kind == "time":
                return run.seconds, fmt_time(run.seconds)
            if not run.found:
                return None, "no path"
            if kind == "cost":
                return run.cost, f"{run.cost} moves"
            return run.path_length, f"{run.path_length} cells"

        for name, kind in (("Path Cost", "cost"), ("Nodes Expanded", "nodes"),
                           ("Execution Time", "time"), ("Path Length", "length")):
            row = pygame.Rect(box.x + 12, y - 4, box.w - 24, 34)
            ui.rrect(surf, S.BG2, row, 8)
            ui.text(surf, name, (cx[0], y + 3), 16, S.WHITE, bold=True)
            (bv, bt), (av, at) = cell(b, kind), cell(a, kind)
            for x, mine, other, txt in ((cx[1], bv, av, bt), (cx[2], av, bv, at)):
                best = done and mine is not None and other is not None and mine < other
                col = S.GREEN if best else (S.WHITE if mine is not None else S.MUTED)
                rr = ui.text(surf, txt, (x, y + 2), 17, col, bold=True, mono=True)
                if best:
                    ui.badge(surf, "BETTER", (rr.right + 10, y + 4), S.GREEN, 9)
            y += 40
        ui.text(surf, "Execution time = mean wall-clock time of the real search() call (40 runs, no tracing).",
                (box.x + 24, box.bottom - 22), 12, S.MUTED)

        # ---- summary ------------------------------------------------------------------
        box = pygame.Rect(734, 634, 432, 248)
        y = ui.panel(surf, box, "COMPARISON SUMMARY", S.GREEN)
        if done and self.summary:
            for line in self.summary:
                pygame.draw.circle(surf, S.GREEN, (box.x + 24, y + 9), 3)
                y = ui.paragraph(surf, line, (box.x + 36, y), 14, box.w - 56, S.WHITE, 4) + 6
        else:
            ui.paragraph(surf, "Both robots receive the same grid, start and goal. Each tick every "
                               "algorithm expands exactly one node, so the search that needs fewer "
                               "expansions finishes first. The verdict appears here when both are done.",
                         (box.x + 22, y), 14, box.w - 44, S.MUTED, 5)

    def draw_explore(self, surf):
        algo = "BFS" if self.mode == "EXPLORE BFS" else "A*"
        col = S.ALGO_COLOR[algo]
        r = self.racers[algo]
        pb = r.playback
        self.draw_side(surf, algo, self.views["BIG"], values=True)
        draw_legend(surf, (28, 846), ("obstacle", "explored", "frontier", "path"), col, spacing=18)
        ui.text(surf, "S start    G goal    cell numbers: " +
                ("f(n) with g / h below" if algo == "A*" else "BFS depth (level)"), (420, 855), 13, S.MUTED,
                anchor="midleft")

        box = pygame.Rect(796, 76, 372, 806)
        y = ui.panel(surf, box, f"{algo} EXPLORATION", col)
        label, scol = r.status
        ui.badge(surf, label, (box.right - 14, box.y + 10), scol, 11, anchor="topright")
        if algo == "BFS":
            body = ("Breadth-first search expands the oldest node in its FIFO queue, so the frontier "
                    "grows level by level: every cell at depth d is expanded before depth d+1.")
        else:
            body = ("A* always expands the open node with the lowest f(n) = g(n) + h(n). The Manhattan "
                    "heuristic h(n) pulls the search towards the goal.")
        y = ui.paragraph(surf, body, (box.x + 18, y), 13, box.w - 36, S.MUTED, 4) + 8
        tw = (box.w - 36 - 18) / 4
        v = pb.current_values
        if algo == "A*":
            tiles = [("g(n)", v.get("g", "-"), S.WHITE), ("h(n)", v.get("h", "-"), S.PURPLE),
                     ("f(n)", v.get("f", "-"), S.CYAN), ("OPEN", pb.frontier_size, S.ORANGE)]
        else:
            tiles = [("DEPTH", v.get("depth", "-"), S.WHITE), ("QUEUE", pb.frontier_size, S.ORANGE),
                     ("VISITED", len(pb.explored) + len(pb.frontier), S.BLUE), ("LEVELS", max(
                         [x.get("depth", 0) for x in pb.values.values()] or [0]), S.PURPLE)]
        for i, (lab, val, c) in enumerate(tiles):
            stat_tile(surf, (box.x + 18 + i * (tw + 6), y, tw, 50), lab, val, c)
        y += 60
        rows = [("Current node", f"({pb.current[0]},{pb.current[1]})" if pb.current else "-"),
                ("Nodes expanded", f"{pb.nodes_expanded} of {r.run.nodes_expanded}"),
                ("Closed list / explored" if algo == "A*" else "Explored", str(len(pb.explored))),
                ("Path cost", f"{r.run.cost} moves" if pb.done and r.run.found else ("no path" if pb.failed else "-")),
                ("Execution time", fmt_time(r.run.seconds) if pb.done else "-")]
        for key, val in rows:
            ui.text(surf, key, (box.x + 18, y), 14, S.MUTED)
            ui.text(surf, val, (box.right - 18, y), 14, S.WHITE, bold=True, anchor="topright")
            y += 23
        ui.progress_bar(surf, (box.x + 18, y + 4, box.w - 36, 8), pb.progress, col)
        y += 22
        draw_log(surf, (box.x + 10, y, box.w - 20, box.bottom - y - 10), self.log)

    def draw_controls(self, surf):
        box = pygame.Rect(PANEL_X, 76, PANEL_W, 806)
        ui.panel(surf, box, "RACE CONTROL", S.CYAN)
        x = box.x + 16
        ui.text(surf, "ENVIRONMENT", (x, 170), 11, S.CYAN, bold=True)
        g = self.grid
        ui.text(surf, os.path.basename(self.env_path), (x, 188), 15, S.WHITE, bold=True, max_width=box.w - 32)
        ui.text(surf, f"{g.rows}x{g.cols} grid, {len(g.obstacles)} obstacles", (x, 209), 13, S.MUTED)
        ui.text(surf, "NAVIGATION PROBLEM", (x, 288), 11, S.CYAN, bold=True)
        sl, gl = self.label_of(self.start), self.label_of(self.goal)
        ui.text(surf, f"Start {sl} ({self.start[0]},{self.start[1]})", (x, 306), 15, S.GREEN, bold=True)
        ui.text(surf, f"Goal {gl} ({self.goal[0]},{self.goal[1]})", (x + 186, 306), 15, S.RED, bold=True)
        ui.text(surf, "Left-click a cell = goal   |   right-click = start", (x, 328), 12, S.MUTED)
        ui.text(surf, "PLAYBACK SPEED", (x, 430), 11, S.CYAN, bold=True)
        self.widgets.draw(surf)
        y = 700
        if self.error:
            ui.paragraph(surf, self.error, (x, y), 13, box.w - 32, S.RED, 4)
            return
        ui.text(surf, "FAIR RACE RULES", (x, y), 11, S.CYAN, bold=True)
        for i, line in enumerate(("Same grid, obstacles, start and goal.",
                                  "One node expansion per algorithm per tick.",
                                  "Robots drive at the same speed.",
                                  "All numbers come from the real runs.")):
            ui.check_mark(surf, S.GREEN, (x + 8, y + 30 + i * 24), 10, 2)
            ui.text(surf, line, (x + 24, y + 21 + i * 24), 13, S.WHITE)
        ui.text(surf, "SPACE start/pause   N step   R restart", (x, box.bottom - 26), 12, S.MUTED)
