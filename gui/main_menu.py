"""Main menu and the two information screens (How to Play / About)."""
import math
import os
import random

import pygame

from config import settings as S
from core.environment import InputError, load_environment_checked
from core.graph_search import search
from entities.particles import ParticleSystem
from entities.robot import Robot
from gui import ui
from gui.app import Screen
from gui.grid_view import GridView


class MenuDemo:
    """The little living scene on the menu: the robot runs real A* tours of
    the sample environment, cleaning each dirty cell in turn."""

    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.ok = False
        try:
            self.grid = load_environment_checked(os.path.join(S.ROOT_DIR, S.MISSIONS[0]["env"]))
        except InputError:
            return
        self.ok = True
        self.view = GridView(self.grid, self.rect, coords=False)
        self.robot = Robot(self.grid.charging_station)
        self.particles = ParticleSystem()
        self.reset()

    def reset(self):
        self.cleaned = set()
        self.queue = list(self.grid.dirty_locations.items())
        random.shuffle(self.queue)
        self.path = []
        self.target = None
        self.wait = 0.6
        self.robot.state = "idle"

    def _plan(self, goal):
        path, _, _ = search(self.grid, self.robot.cell, goal, "A*")
        return path[1:] if path else None

    def update(self, dt):
        if not self.ok:
            return
        self.particles.update(dt)
        arrived = self.robot.update(dt)
        centre = self.view.center((self.robot.row, self.robot.col))
        if self.robot.busy:
            return
        if self.path:
            self.robot.move_to(self.path.pop(0), 0.26)
            return
        if arrived and self.target is not None:
            self.wait = 1.0
            self.robot.state = "cleaning" if self.target != "C" else "charging"
        if self.wait > 0:
            self.wait -= dt
            if self.robot.state == "cleaning":
                self.particles.dust(centre, self.view.cell * 0.4, 1)
            elif self.robot.state == "charging":
                self.robot.charge_level = min(1.0, 1 - self.wait)
                self.particles.energy(centre, self.view.cell * 0.6, 1, S.BLUE)
            if self.wait > 0:
                return
            if self.robot.state == "cleaning":
                self.cleaned.add(self.target)
                self.particles.sparkle(centre, self.view.cell * 0.5, 10)
            elif self.target == "C":
                self.reset()
                self.wait = 0.0
            self.robot.state = "idle"
        while True:
            if self.queue:
                self.target, goal = self.queue.pop(0)
            elif self.target != "C" or self.robot.cell != self.grid.charging_station:
                self.target, goal = "C", self.grid.charging_station
            else:
                self.reset()
                return
            path = self._plan(goal)
            if path:
                self.path = path
                return
            if self.target == "C":
                self.reset()
                return

    def draw(self, surf, t):
        if not self.ok:
            return
        remaining = [self.robot.cell] + self.path if self.path else None
        self.view.draw(surf, t, cleaned=self.cleaned, path=remaining,
                       charging=self.robot.state == "charging")
        self.robot.draw(surf, self.view.center((self.robot.row, self.robot.col)), self.view.cell * 1.1)
        self.particles.draw(surf)


class MainMenu(Screen):
    def __init__(self, app):
        super().__init__(app)
        go = app.go
        items = [
            ("START MISSION", lambda: go("missions"), "primary"),
            ("CUSTOM ENVIRONMENT", lambda: go("editor"), "ghost"),
            ("ALGORITHM RACE", lambda: go("race"), "ghost"),
            ("AI ANALYTICS", lambda: go("analytics"), "ghost"),
            ("HOW TO PLAY", lambda: go("info", page="how"), "ghost"),
            ("ABOUT PROJECT", lambda: go("info", page="about"), "ghost"),
            ("EXIT", app.quit, "ghost"),
        ]
        self.buttons = ui.WidgetGroup(app)
        y = 372
        for label, action, style in items:
            self.buttons.add(ui.Button((96, y, 400, 54), label, action, style, size=18, align="left"))
            y += 64
        self.hero = Robot((0, 0), heading=180)
        self.demo = MenuDemo((1010, 420, 470, 410))
        self.particles = ParticleSystem()
        self.t = 0.0

    def enter(self, **kwargs):
        self.t = 0.0

    def handle(self, event):
        self.buttons.handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.app.go("missions")

    def update(self, dt):
        self.t += dt
        self.buttons.update(dt)
        # the hero robot slowly looks around and "cleans" now and then
        cycle = self.t % 9.0
        self.hero.state = "cleaning" if 5.2 < cycle < 6.8 else ("thinking" if 2.2 < cycle < 3.4 else "idle")
        self.hero.target_heading = 180 + 24 * math.sin(self.t * 0.6)
        self.hero.update(dt)
        if self.hero.state == "cleaning":
            self.particles.dust((1245 + random.choice((-70, 70)), 345), 46, 1)
        self.particles.update(dt)
        self.demo.update(dt)

    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        t = self.t
        slide = ui.ease(min(1.0, t / 0.6))
        x = 96 - int((1 - slide) * 60)

        # ---- left: title block ------------------------------------------------
        ui.glow(surf, (x + 260, 180), 330, S.CYAN, 26)
        r = ui.text(surf, "OPTISWEEP", (x - 4, 128), 92, S.WHITE, bold=True)
        ui.text(surf, "AI", (r.right + 20, 128), 92, S.CYAN, bold=True)
        pygame.draw.rect(surf, S.CYAN, (x, 242, 120 + int(40 * math.sin(t * 2)), 4), border_radius=2)
        ui.text(surf, S.APP_SUBTITLE, (x, 258), 26, S.MUTED)
        ui.paragraph(surf, "Command an intelligent vacuum robot. A CSP scheduler decides when each "
                           "location is cleaned; BFS and A* search decide how to get there. Watch "
                           "every decision as it happens.", (x, 302), 16, 560, S.MUTED, 5)
        self.buttons.draw(surf)
        ui.text(surf, "ENTER  start mission      M  mute      F3  FPS", (96, S.HEIGHT - 38), 13, S.MUTED)

        # ---- right: hero robot + live demo ------------------------------------
        cx, cy = 1245, 232
        for i in range(3):
            rad = 150 + i * 46 + 10 * math.sin(t * 1.4 + i)
            pygame.draw.circle(surf, ui.mix(S.BG2, S.CYAN, 0.30 - i * 0.08), (cx, cy), int(rad), 1)
        for i in range(8):
            a = t * 0.5 + i * math.pi / 4
            p = (cx + math.cos(a) * 196, cy + math.sin(a) * 196)
            pygame.draw.circle(surf, S.CYAN if i % 2 else S.BLUE, (int(p[0]), int(p[1])), 3)
        self.hero.draw(surf, (cx, cy + 6 * math.sin(t * 1.6)), 300)
        self.particles.draw(surf)

        panel = self.demo.rect.inflate(36, 64).move(0, -8)
        ui.rrect_alpha(surf, S.PANEL, panel, 16, 205)
        ui.rrect(surf, S.BORDER, panel, 16, 1)
        ui.text(surf, "LIVE DEMO", (panel.x + 20, panel.y + 14), 13, S.CYAN, bold=True)
        ui.text(surf, "real A* navigation on the sample environment", (panel.x + 112, panel.y + 14), 13, S.MUTED)
        pygame.draw.circle(surf, S.GREEN if int(t * 2) % 2 else ui.mix(S.GREEN, S.PANEL, 0.6),
                           (panel.right - 22, panel.y + 22), 5)
        self.demo.draw(surf, t)


HOW = [
    ("1  CHOOSE A MISSION", "Pick one of the three scenarios or load your own Environment / Schedule "
     "text files. You can also build a floor plan in the Custom Environment editor."),
    ("2  CONFIGURE", "Select the navigation algorithm (BFS or A*), the execution mode "
     "(Automatic or Step-by-Step) and the simulation speed."),
    ("3  WATCH THE AI THINK", "The AI Brain panel shows the CSP solver choosing variables with MRV and "
     "Degree, ordering values with LCV, forward checking and backtracking, then every node the "
     "search algorithm expands."),
    ("4  CONTROL THE SIMULATION", "PLAY / PAUSE / RESUME, NEXT STEP for one decision at a time, RESTART "
     "to replay. Click a task in the schedule to inspect it."),
    ("5  COMPARE", "Run the Algorithm Race to see BFS and A* solve the same problem side by side and "
     "open AI Analytics for charts and tables."),
]
KEYS = [("SPACE", "Play / pause"), ("N  or  RIGHT", "Next step"), ("R", "Restart"),
        ("1 2 3 4", "Simulation speed"), ("ESC", "Back / main menu"), ("M", "Mute sound"),
        ("F3", "Show FPS")]

ABOUT = [
    ("THE PROBLEM", "An autonomous vacuum robot must clean every dirty location of a grid world, "
     "respecting scheduling rules, avoiding obstacles, and then return to its charging station."),
    ("BRAIN 1 - CSP SCHEDULER", "Variables are the dirty locations, domains are the time slots. "
     "Constraints: slot exclusivity, precedence (A before B) and latest-slot deadlines. Solved by "
     "backtracking search with MRV, the Degree heuristic, LCV ordering and forward checking."),
    ("BRAIN 2 - GRAPH SEARCH", "Breadth-First Search (uninformed) and A* (informed, Manhattan "
     "distance heuristic) plan each leg with four-directional moves of unit cost."),
    ("INTEGRATION", "The CSP schedule fixes the visiting order; the navigator plans each leg; the "
     "simulation executes the journey and reports cost, nodes expanded and success."),
    ("HONEST VISUALS", "Everything shown in the game is recorded from the real algorithm runs: the "
     "same functions as the original simulation notebook, extended only with optional trace callbacks."),
]


class InfoScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.page = "how"
        self.back = ui.Button((40, S.HEIGHT - 76, 200, 48), "MAIN MENU", lambda: app.go("menu"))
        self.robot = Robot((0, 0), heading=200)

    def enter(self, page="how", **kwargs):
        self.page = page

    def handle(self, event):
        self.back.handle(event, self.app)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go("menu")

    def update(self, dt):
        self.back.update(dt, self.app.mouse)
        self.robot.target_heading = 200 + 20 * math.sin(self.app.t)
        self.robot.update(dt)

    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        how = self.page == "how"
        app.header(surf, "HOW TO PLAY" if how else "ABOUT PROJECT",
                   "Mission briefing" if how else "Artificial Intelligence - Autonomous Cleaning Robot Simulator")
        main = pygame.Rect(40, 84, 1040, 716)
        ui.panel(surf, main)
        y = main.y + 26
        for title, body in (HOW if how else ABOUT):
            ui.text(surf, title, (main.x + 30, y), 18, S.CYAN, bold=True)
            y = ui.paragraph(surf, body, (main.x + 30, y + 30), 16, main.w - 60, S.WHITE, 7) + 20
        side = pygame.Rect(1100, 84, 460, 716)
        y = ui.panel(surf, side, "KEYBOARD" if how else "HEURISTIC")
        if how:
            for key, what in KEYS:
                ui.badge(surf, key, (side.x + 24, y + 6), S.CYAN, 13)
                ui.text(surf, what, (side.x + 190, y + 10), 16, S.WHITE)
                y += 44
        else:
            ui.text(surf, "Manhattan distance", (side.x + 24, y + 4), 16, S.WHITE, bold=True)
            ui.text(surf, "h(n) = |row_n - row_goal|", (side.x + 24, y + 36), 16, S.CYAN, mono=True)
            ui.text(surf, "     + |col_n - col_goal|", (side.x + 24, y + 60), 16, S.CYAN, mono=True)
            y = ui.paragraph(surf, "Admissible and consistent for four-directional unit-cost moves, so "
                                   "A* returns optimal paths while expanding fewer nodes than BFS.",
                             (side.x + 24, y + 98), 15, side.w - 48, S.MUTED) + 8
            ui.text(surf, "f(n) = g(n) + h(n)", (side.x + 24, y + 6), 16, S.CYAN, mono=True)
            y += 40
        self.robot.draw(surf, (side.centerx, side.bottom - 170), 230)
        self.back.draw(surf)
