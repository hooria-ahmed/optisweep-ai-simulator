"""Mission selection: three preset scenarios plus any other input files."""
import os

import pygame

from config import settings as S
from core.environment import InputError, load_environment_checked, load_schedule_checked
from gui import ui
from gui.app import Screen
from gui.grid_view import GridView


class MissionInfo:
    """Loads a mission's two input files for preview; never raises."""
    def __init__(self, env_path, sched_path):
        self.env_path, self.sched_path = env_path, sched_path
        self.grid = self.constraints = None
        self.error = ""
        try:
            self.grid = load_environment_checked(env_path)
            _, _, self.constraints = load_schedule_checked(sched_path, self.grid.dirty_locations.keys())
        except InputError as exc:
            self.error = str(exc)

    @property
    def ok(self):
        return not self.error

    def facts(self):
        g, c = self.grid, self.constraints
        rows = []
        if g is not None:
            rows += [("Grid", f"{g.rows} x {g.cols}"), ("Obstacles", str(len(g.obstacles))),
                     ("Dirty locations", str(len(g.dirty_locations))),
                     ("Charging station", f"({g.charging_station[0]},{g.charging_station[1]})")]
        if c is not None:
            rows += [("Time slots", str(c["num_slots"])),
                     ("Precedence rules", str(len(c["precedence"]))),
                     ("Latest-slot rules", str(len(c["latest_slot"])))]
        return rows


def draw_preview(surf, info, rect, t, cache):
    """Mini map of a mission's environment inside ``rect``."""
    rect = pygame.Rect(rect)
    if info.grid is None:
        ui.rrect(surf, S.DARK, rect, 12)
        ui.text(surf, "NO PREVIEW", rect.center, 16, S.MUTED, bold=True, anchor="center")
        return
    key = (id(info), rect.topleft, rect.size)
    if key not in cache:
        cache.clear()
        cache[key] = GridView(info.grid, rect, coords=False)
    cache[key].draw(surf, t)


class MissionSelection(Screen):
    CARD_W, CARD_H, GAP = 362, 650, 24

    def __init__(self, app):
        super().__init__(app)
        self.custom_env = os.path.join(S.ROOT_DIR, "Environment.txt")
        self.custom_sched = os.path.join(S.ROOT_DIR, "Schedule.txt")
        self.infos = []
        self.caches = [dict() for _ in range(4)]
        self.widgets = ui.WidgetGroup(app)
        self.widgets.add(ui.Button((40, S.HEIGHT - 70, 190, 46), "MAIN MENU", lambda: app.go("menu")))
        self.select_btns = []
        for i in range(4):
            r = self.card(i)
            b = ui.Button((r.x + 20, r.bottom - 64, r.w - 40, 46), "SELECT MISSION",
                          lambda i=i: self.select(i), "primary", size=16)
            self.select_btns.append(self.widgets.add(b))
        r = self.card(3)
        self.widgets.add(ui.Button((r.x + 20, r.y + 372, r.w - 40, 38), "CHOOSE ENVIRONMENT FILE",
                                   lambda: self.pick("env"), size=13))
        self.widgets.add(ui.Button((r.x + 20, r.y + 452, r.w - 40, 38), "CHOOSE SCHEDULE FILE",
                                   lambda: self.pick("sched"), size=13))

    def card(self, i):
        total = 4 * self.CARD_W + 3 * self.GAP
        x = (S.WIDTH - total) // 2 + i * (self.CARD_W + self.GAP)
        return pygame.Rect(x, 150, self.CARD_W, self.CARD_H)

    def enter(self, **kwargs):
        self.reload()

    def reload(self):
        self.infos = [MissionInfo(os.path.join(S.ROOT_DIR, m["env"]), os.path.join(S.ROOT_DIR, m["sched"]))
                      for m in S.MISSIONS]
        self.infos.append(MissionInfo(self.custom_env, self.custom_sched))
        for c in self.caches:
            c.clear()
        for info, btn in zip(self.infos, self.select_btns):
            btn.enabled = info.ok

    def pick(self, which):
        def chosen(path):
            if which == "env":
                self.custom_env = path
            else:
                self.custom_sched = path
            self.reload()
            info = self.infos[3]
            if info.ok:
                self.app.notify("Files loaded and validated.", S.GREEN)
            else:
                self.app.audio.play("error")
        title = "SELECT ENVIRONMENT FILE" if which == "env" else "SELECT SCHEDULE FILE"
        self.app.modal = ui.FilePicker(self.app, title, chosen)

    def select(self, i):
        info = self.infos[i]
        if not info.ok:
            return
        st = self.app.state
        st.env_path, st.sched_path = info.env_path, info.sched_path
        if i < 3:
            st.mission_title = f"MISSION {S.MISSIONS[i]['id']} - {S.MISSIONS[i]['title']}"
        else:
            st.mission_title = "CUSTOM FILES - " + os.path.basename(info.env_path)
        self.app.go("config")

    def handle(self, event):
        if self.widgets.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.go("menu")

    def update(self, dt):
        self.widgets.update(dt)

    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        app.header(surf, "MISSION SELECTION", "Choose a scenario - every map and schedule is loaded from its text files")
        ui.text(surf, "SELECT YOUR MISSION", (S.WIDTH // 2, 104), 30, S.WHITE, bold=True, anchor="center")
        for i in range(4):
            self.draw_card(surf, i)
        self.widgets.draw(surf)

    def draw_card(self, surf, i):
        r = self.card(i)
        info = self.infos[i]
        preset = S.MISSIONS[i] if i < 3 else None
        color = preset["color"] if preset else S.PURPLE
        hot = r.collidepoint(self.app.mouse)
        if hot:
            ui.glow(surf, r.center, 330, color, 24)
        ui.rrect(surf, S.PANEL, r, 16)
        ui.rrect(surf, color if hot else S.BORDER, r, 16, 2 if hot else 1)
        pygame.draw.rect(surf, color, (r.x + 20, r.y, 70, 4), border_bottom_left_radius=3, border_bottom_right_radius=3)
        ui.text(surf, f"MISSION {preset['id']}" if preset else "MISSION 04", (r.x + 20, r.y + 20), 13, color, bold=True)
        ui.text(surf, preset["title"] if preset else "LOAD OTHER FILES", (r.x + 20, r.y + 40), 21, S.WHITE, bold=True)
        prev = pygame.Rect(r.x + 20, r.y + 78, r.w - 40, 210 if preset else 270)
        ui.rrect(surf, S.DARK, prev, 12)
        draw_preview(surf, info, prev.inflate(-10, -10), self.app.t, self.caches[i])
        y = prev.bottom + 12
        if preset:
            y = ui.paragraph(surf, preset["blurb"], (r.x + 20, y), 14, r.w - 40, S.MUTED, 4) + 8
            for key, val in info.facts():
                ui.text(surf, key, (r.x + 20, y), 14, S.MUTED)
                ui.text(surf, val, (r.right - 20, y), 14, S.WHITE, bold=True, anchor="topright")
                y += 23
            ui.text(surf, f"{preset['env']}  +  {preset['sched']}", (r.x + 20, r.bottom - 92), 12, S.MUTED,
                    mono=True, max_width=r.w - 40)
        else:
            ui.text(surf, "ENV", (r.x + 22, r.y + 352), 11, S.MUTED, bold=True)
            ui.text(surf, os.path.basename(info.env_path), (r.x + 56, r.y + 350), 13, S.WHITE, mono=True,
                    max_width=r.w - 80)
            ui.text(surf, "SCHED", (r.x + 22, r.y + 432), 11, S.MUTED, bold=True)
            ui.text(surf, os.path.basename(info.sched_path), (r.x + 70, r.y + 430), 13, S.WHITE, mono=True,
                    max_width=r.w - 94)
            if info.ok:
                g, c = info.grid, info.constraints
                ui.text(surf, f"{g.rows}x{g.cols} grid, {len(g.dirty_locations)} dirty, {c['num_slots']} slots, "
                              f"{len(c['precedence']) + len(c['latest_slot'])} rules",
                        (r.x + 20, r.y + 506), 13, S.GREEN, max_width=r.w - 40)
                ui.text(surf, "Inputs are valid.", (r.x + 20, r.y + 528), 13, S.MUTED)
        if not info.ok:
            box = pygame.Rect(r.x + 20, r.y + 500, r.w - 40, 78)
            ui.rrect_alpha(surf, S.RED, box, 8, 36)
            ui.rrect(surf, S.RED, box, 8, 1)
            ui.paragraph(surf, info.error, (box.x + 10, box.y + 8), 12, box.w - 20, S.RED, 3)
