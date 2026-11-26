"""Application shell: window, main loop, screen manager and shared state."""
import math
import os
import random

# Keep native-pixel rendering when launched directly (tests, notebook, etc.).
from config.dpi import enable_hidpi

enable_hidpi()

import pygame

from config import settings as S
from gui import ui
from gui.audio import Audio


class Screen:
    """Base class for all screens."""
    name = ""

    def __init__(self, app):
        self.app = app

    def enter(self, **kwargs):
        pass

    def leave(self):
        pass

    def handle(self, event):
        pass

    def update(self, dt):
        pass

    def draw(self, surf):
        pass


class MissionState:
    """What the player has chosen so far; shared between screens."""
    def __init__(self):
        m = S.MISSIONS[0]
        self.mission_title = f"MISSION {m['id']} - {m['title']}"
        self.env_path = os.path.join(S.ROOT_DIR, m["env"])
        self.sched_path = os.path.join(S.ROOT_DIR, m["sched"])
        self.algorithm = "A*"
        self.mode = "AUTOMATIC"
        self.speed = "NORMAL"
        self.plan = None          # core.integration.MissionPlan of the last started mission
        self.result = None        # dict produced by the simulation screen

    @property
    def speed_factor(self):
        return dict(S.SPEEDS)[self.speed]


class App:
    def __init__(self, headless=False, sound=True):
        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        pygame.init()
        pygame.display.set_caption(f"{S.APP_NAME} - {S.APP_SUBTITLE}")
        self.headless = headless
        if headless:
            self.window = pygame.display.set_mode((S.WIDTH, S.HEIGHT))
        else:
            # Info() must be queried *before* set_mode(): it reports the
            # desktop size beforehand, but the window size afterwards.  With
            # DPI awareness enabled it reports physical pixels, so on a normal
            # 1080p screen `scale` is 1.0 and the canvas is presented 1:1.
            info = pygame.display.Info()
            scale = 1.0
            if info.current_w > 0 and info.current_h > 0:      # unknown on some drivers
                scale = min(1.0, (info.current_w * 0.94) / S.WIDTH, (info.current_h * 0.86) / S.HEIGHT)
            size = (max(640, int(S.WIDTH * scale)), max(360, int(S.HEIGHT * scale)))
            self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.canvas = pygame.Surface((S.WIDTH, S.HEIGHT))
        self._scaled = None                  # cached smoothscale result
        self._scaled_size = None
        self.clock = pygame.time.Clock()
        self.audio = Audio(enabled=sound and not headless)
        self.state = MissionState()
        self.mouse = (0, 0)
        self.t = 0.0
        self.running = True
        self.fps = 60.0
        self.show_fps = False
        self.toast = None                 # (text, color, time_left)
        self.modal = None                 # e.g. ui.FilePicker
        self._screens = {}
        self._factories = {}
        self.current = None
        self._pending = None              # (name, kwargs) during fade-out
        self._fade = 0.0                  # 1 = fully black
        self._fade_dir = 0
        self._bg = self._make_background()
        self._motes = [(random.uniform(0, S.WIDTH), random.uniform(0, S.HEIGHT),
                        random.uniform(6, 22), random.uniform(0, 6.28)) for _ in range(46)]
        self.prev_screen = None
        self.music_btn = ui.Button((S.WIDTH - 228, 14, 102, 32), "MUSIC ON", self.toggle_music, size=12)
        self.mute_btn = ui.Button((S.WIDTH - 118, 14, 98, 32), "SOUND ON", self.toggle_mute, size=12)
        self._register()
        self.go("menu", instant=True)

    # ------------------------------------------------------------- screens --
    def _register(self):
        from gui.main_menu import MainMenu, InfoScreen
        from gui.mission_selection import MissionSelection
        from gui.environment_editor import EnvironmentEditor
        from gui.schedule_editor import ScheduleEditor
        from gui.mission_config import MissionConfig
        from gui.simulation_screen import SimulationScreen
        from gui.algorithm_race import AlgorithmRace
        from gui.analytics_screen import AnalyticsScreen
        from gui.results_screen import ResultsScreen
        self._factories = {
            "menu": MainMenu, "info": InfoScreen, "missions": MissionSelection,
            "editor": EnvironmentEditor, "sched_editor": ScheduleEditor, "config": MissionConfig,
            "simulation": SimulationScreen,
            "race": AlgorithmRace, "analytics": AnalyticsScreen, "results": ResultsScreen,
        }

    def screen(self, name):
        if name not in self._screens:
            self._screens[name] = self._factories[name](self)
            self._screens[name].name = name
        return self._screens[name]

    def go(self, name, instant=False, **kwargs):
        """Switch screen with a short fade."""
        if instant or self.current is None:
            self._switch(name, kwargs)
            self._fade, self._fade_dir = 1.0, -1
        else:
            self._pending = (name, kwargs)
            self._fade_dir = 1

    def _switch(self, name, kwargs):
        if self.current is not None:
            self.prev_screen = self.current.name
            self.current.leave()
        self.modal = None
        self.current = self.screen(name)
        self.current.enter(**kwargs)

    def notify(self, text, color=S.CYAN, seconds=3.5):
        self.toast = [text, color, seconds, seconds]

    def toggle_mute(self):
        muted = self.audio.toggle()
        self.mute_btn.label = "SOUND OFF" if muted else "SOUND ON"
        self.notify("All Audio Muted" if muted else "All Audio Enabled", S.CYAN, 1.8)

    def toggle_music(self):
        muted = self.audio.toggle_music()
        self.music_btn.label = "MUSIC OFF" if muted else "MUSIC ON"
        self.notify("Background Music Muted" if muted else "Background Music On", S.CYAN, 1.8)

    def quit(self):
        self.running = False

    # ---------------------------------------------------------- background --
    def _make_background(self):
        bg = pygame.Surface((S.WIDTH, S.HEIGHT))
        for y in range(S.HEIGHT):
            pygame.draw.line(bg, ui.mix(S.BG, S.BG2, y / S.HEIGHT), (0, y), (S.WIDTH, y))
        line = ui.mix(S.BG2, S.BORDER, 0.35)
        for x in range(0, S.WIDTH, 50):
            pygame.draw.line(bg, line, (x, 0), (x, S.HEIGHT))
        for y in range(0, S.HEIGHT, 50):
            pygame.draw.line(bg, line, (0, y), (S.WIDTH, y))
        ui.glow(bg, (S.WIDTH * 0.82, S.HEIGHT * 0.2), 620, S.BLUE, 40)
        ui.glow(bg, (S.WIDTH * 0.1, S.HEIGHT * 0.95), 520, S.CYAN, 26)
        return bg

    def draw_background(self, surf):
        surf.blit(self._bg, (0, 0))
        for x, y, speed, phase in self._motes:
            yy = (y - self.t * speed) % S.HEIGHT
            xx = x + math.sin(self.t * 0.4 + phase) * 14
            b = 0.35 + 0.3 * math.sin(self.t * 1.3 + phase)
            pygame.draw.circle(surf, ui.mix(S.BG2, S.CYAN, b), (int(xx), int(yy)), 2 if speed > 14 else 1)

    def header(self, surf, title, subtitle="", accent=S.CYAN):
        """Standard top bar used by the inner screens."""
        ui.rrect_alpha(surf, S.DARK, (0, 0, S.WIDTH, 60), 0, 150)
        pygame.draw.line(surf, S.BORDER, (0, 60), (S.WIDTH, 60))
        pygame.draw.rect(surf, accent, (22, 18, 5, 26), border_radius=2)
        r = ui.text(surf, title, (38, 30), 24, S.WHITE, bold=True, anchor="midleft")
        if subtitle:
            ui.text(surf, subtitle, (r.right + 18, 32), 15, S.MUTED, anchor="midleft",
                    max_width=S.WIDTH - r.right - 540)
        ui.text(surf, S.APP_NAME, (S.WIDTH - 246, 30), 14, S.CYAN, bold=True, anchor="midright")

    # ------------------------------------------------------------ main loop --
    def _viewport(self):
        """Window rectangle that the logical canvas is drawn into.

        Letterboxing preserves the 16:9 aspect ratio when the window is
        resized, so text is never stretched or squashed.
        """
        ww, wh = self.window.get_size()
        scale = min(ww / S.WIDTH, wh / S.HEIGHT)
        vw = max(1, int(round(S.WIDTH * scale)))
        vh = max(1, int(round(S.HEIGHT * scale)))
        return pygame.Rect((ww - vw) // 2, (wh - vh) // 2, vw, vh)

    def to_logical(self, pos):
        vp = self._viewport()
        return (int(round((pos[0] - vp.x) * S.WIDTH / max(1, vp.w))),
                int(round((pos[1] - vp.y) * S.HEIGHT / max(1, vp.h))))

    def translate(self, event):
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            data = dict(event.dict)
            data["pos"] = self.to_logical(event.pos)
            return pygame.event.Event(event.type, data)
        return event

    def process(self, events):
        for raw in events:
            if raw.type == pygame.QUIT:
                self.running = False
                return
            if raw.type == pygame.KEYDOWN and raw.key == pygame.K_F3:
                self.show_fps = not self.show_fps
            if raw.type == pygame.KEYDOWN and raw.key == pygame.K_m and not self._typing():
                self.toggle_mute()
                continue
            if raw.type == pygame.KEYDOWN and raw.key == pygame.K_b and not self._typing():
                self.toggle_music()
                continue
            if self._pending is not None:
                continue                      # ignore input while fading out
            event = self.translate(raw)
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
                self.mouse = event.pos
            if self.music_btn.handle(event, self):
                continue
            if self.mute_btn.handle(event, self):
                continue
            try:
                if self.modal is not None:
                    self.modal.handle(event)
                    if self.modal is not None and self.modal.done:
                        self.modal = None
                else:
                    self.current.handle(event)
            except Exception as exc:          # a screen must never take the game down
                self._report(exc)

    def _typing(self):
        focus = getattr(self.current, "text_focus", None)
        return bool(focus and focus())

    def _report(self, exc):
        import traceback
        traceback.print_exc()
        self.audio.play("error")
        self.notify(f"Unexpected error: {exc}", S.RED, 6)

    def update(self, dt):
        self.t += dt
        if not self.headless:
            self.mouse = self.to_logical(pygame.mouse.get_pos())
        self.music_btn.update(dt, self.mouse)
        self.mute_btn.update(dt, self.mouse)
        if self._fade_dir:
            self._fade += self._fade_dir * dt / 0.16
            if self._fade >= 1.0 and self._pending is not None:
                name, kwargs = self._pending
                self._pending = None
                self._fade = 1.0
                self._fade_dir = -1
                try:
                    self._switch(name, kwargs)
                except Exception as exc:
                    self._report(exc)
                    if self.current is None or self.current.name != "menu":
                        self._switch("menu", {})
            elif self._fade <= 0.0:
                self._fade, self._fade_dir = 0.0, 0
        try:
            if self.modal is not None:
                self.modal.update(dt, self.mouse)
            self.current.update(dt)
        except Exception as exc:
            self._report(exc)
        if self.toast:
            self.toast[2] -= dt
            if self.toast[2] <= 0:
                self.toast = None

    def draw(self):
        surf = self.canvas
        try:
            self.current.draw(surf)
            if self.modal is not None:
                self.modal.draw(surf)
        except Exception as exc:
            self._report(exc)
        self.music_btn.draw(surf)
        self.mute_btn.draw(surf)
        if self.toast:
            msg, color, left, total = self.toast
            k = min(1.0, left / 0.3, (total - left) / 0.2)
            img = ui.render(ui.fit(msg, 16, 1100, True), 16, S.WHITE, bold=True)
            r = img.get_rect().inflate(48, 26)
            r.midbottom = (S.WIDTH // 2, S.HEIGHT - 22 + int((1 - k) * 30))
            ui.rrect(surf, S.DARK, r, 12)
            ui.rrect(surf, color, r, 12, 2)
            pygame.draw.circle(surf, color, (r.x + 18, r.centery), 5)
            surf.blit(img, img.get_rect(midleft=(r.x + 32, r.centery)))
        if self.show_fps:
            ui.text(surf, f"{self.fps:5.1f} FPS", (S.WIDTH - 12, S.HEIGHT - 8), 12, S.MUTED,
                    anchor="bottomright", mono=True)
        if self._fade > 0:
            veil = pygame.Surface((S.WIDTH, S.HEIGHT))
            veil.fill(S.DARK)
            veil.set_alpha(int(255 * ui.ease(min(1.0, self._fade))))
            surf.blit(veil, (0, 0))
        vp = self._viewport()
        self.window.fill(S.DARK)             # letterbox bars, if any
        if vp.size == (S.WIDTH, S.HEIGHT):
            self.window.blit(surf, vp.topleft)
        else:
            if self._scaled_size != vp.size:
                self._scaled = pygame.Surface(vp.size)
                self._scaled_size = vp.size
            pygame.transform.smoothscale(surf, vp.size, self._scaled)
            self.window.blit(self._scaled, vp.topleft)
        pygame.display.flip()

    def frame(self, dt, events=()):
        """Run exactly one frame (used by the main loop and by the tests)."""
        self.process(events)
        self.update(dt)
        self.draw()

    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(S.FPS) / 1000.0)
            self.fps += (self.clock.get_fps() - self.fps) * 0.1
            self.frame(dt, pygame.event.get())
        pygame.quit()
