"""Small immediate-mode style UI toolkit: fonts, drawing helpers and widgets."""
import math
import os

import pygame

from config import settings as S

_fonts = {}
_text_cache = {}
_glow_cache = {}

SANS = ["arial", "liberationsans", "helvetica", "segoeui", "dejavusans", "freesans"]
MONO = ["consolas", "dejavusansmono", "menlo", "liberationmono", "couriernew"]


def font(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _fonts:
        path = None
        installed = set(pygame.font.get_fonts())
        for name in (MONO if mono else SANS):
            if name in installed:          # avoid fontconfig's silent substitutions
                path = pygame.font.match_font(name, bold=bold)
                if path:
                    break
        try:
            f = pygame.font.Font(path, size)
        except Exception:
            f = pygame.font.Font(None, int(size * 1.25))
        if bold and path and "bold" not in os.path.basename(path).lower():
            f.set_bold(True)
        _fonts[key] = f
    return _fonts[key]


def render(string, size=16, color=S.WHITE, bold=False, mono=False):
    key = (string, size, color, bold, mono)
    surf = _text_cache.get(key)
    if surf is None:
        if len(_text_cache) > 3000:
            _text_cache.clear()
        surf = font(size, bold, mono).render(string, True, color)
        _text_cache[key] = surf
    return surf


def text(surf, string, pos, size=16, color=S.WHITE, bold=False, mono=False,
         anchor="topleft", max_width=None, alpha=None):
    string = str(string)
    if max_width is not None:
        string = fit(string, size, max_width, bold, mono)
    img = render(string, size, color, bold, mono)
    rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if alpha is not None and alpha < 255:
        img = img.copy()
        img.set_alpha(max(0, int(alpha)))
    surf.blit(img, rect)
    return rect


def fit(string, size, max_width, bold=False, mono=False):
    f = font(size, bold, mono)
    if f.size(string)[0] <= max_width:
        return string
    while len(string) > 1 and f.size(string + "..")[0] > max_width:
        string = string[:-1]
    return string + ".."


def wrap(string, size, max_width, bold=False, mono=False):
    f = font(size, bold, mono)
    lines = []
    for para in str(string).split("\n"):
        line = ""
        for word in para.split(" "):
            trial = (line + " " + word).strip()
            if f.size(trial)[0] <= max_width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def paragraph(surf, string, pos, size, max_width, color=S.MUTED, line_gap=6, bold=False):
    x, y = pos
    for line in wrap(string, size, max_width, bold):
        text(surf, line, (x, y), size, color, bold)
        y += size + line_gap
    return y


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def rrect(surf, color, rect, radius=10, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


def rrect_alpha(surf, color, rect, radius=10, alpha=128, width=0):
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    tmp = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(tmp, (*color[:3], int(max(0, min(255, alpha)))), tmp.get_rect(), width,
                     border_radius=radius)
    surf.blit(tmp, rect)


def glow(surf, pos, radius, color, alpha=90):
    """Soft additive radial glow."""
    radius = int(radius)
    if radius < 2 or alpha <= 0:
        return
    bucket = max(1, int(alpha) // 8 * 8)
    key = (radius, color, bucket)
    img = _glow_cache.get(key)
    if img is None:
        if len(_glow_cache) > 400:
            _glow_cache.clear()
        img = pygame.Surface((radius * 2, radius * 2))
        steps = max(6, min(28, radius // 2))
        for i in range(steps):
            k = i / steps
            r = int(radius * (1 - k))
            strength = (k ** 2.2) * bucket / 255.0
            pygame.draw.circle(img, tuple(int(c * strength) for c in color), (radius, radius), r)
        _glow_cache[key] = img
    surf.blit(img, (int(pos[0]) - radius, int(pos[1]) - radius), special_flags=pygame.BLEND_RGB_ADD)


def panel(surf, rect, title=None, accent=S.CYAN, fill=S.PANEL, border=S.BORDER, radius=14,
          title_size=14):
    """Rounded panel with an optional small-caps title.  Returns the y where
    content may start."""
    rect = pygame.Rect(rect)
    rrect(surf, fill, rect, radius)
    rrect(surf, border, rect, radius, 1)
    if title:
        pygame.draw.rect(surf, accent, (rect.x + 14, rect.y + 15, 4, 14), border_radius=2)
        text(surf, title, (rect.x + 26, rect.y + 12), title_size, S.WHITE, bold=True)
        return rect.y + 40
    return rect.y + 12


def progress_bar(surf, rect, frac, color=S.CYAN, back=S.DARK):
    rect = pygame.Rect(rect)
    rrect(surf, back, rect, rect.h // 2)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        w = max(rect.h, int(rect.w * frac))
        rrect(surf, color, (rect.x, rect.y, w, rect.h), rect.h // 2)


def badge(surf, label, pos, color, size=12, anchor="topleft", filled=False):
    img = render(label, size, S.DARK if filled else color, bold=True)
    rect = img.get_rect().inflate(16, 8)
    setattr(rect, anchor, (int(pos[0]), int(pos[1])))
    if filled:
        rrect(surf, color, rect, rect.h // 2)
    else:
        rrect_alpha(surf, color, rect, rect.h // 2, 40)
        rrect(surf, color, rect, rect.h // 2, 1)
    surf.blit(img, img.get_rect(center=rect.center))
    return rect


def arrow(surf, color, start, end, width=2, head=6):
    pygame.draw.line(surf, color, start, end, width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    for da in (2.6, -2.6):
        pygame.draw.line(surf, color, end, (end[0] + head * math.cos(ang + da),
                                            end[1] + head * math.sin(ang + da)), width)


def check_mark(surf, color, center, size, width=3):
    x, y = center
    pts = [(x - size * 0.5, y), (x - size * 0.12, y + size * 0.38), (x + size * 0.55, y - size * 0.4)]
    pygame.draw.lines(surf, color, False, pts, width)


def bolt(surf, color, center, size):
    x, y = center
    s = size
    pts = [(x + 0.10 * s, y - 0.5 * s), (x - 0.30 * s, y + 0.06 * s), (x - 0.02 * s, y + 0.06 * s),
           (x - 0.12 * s, y + 0.5 * s), (x + 0.30 * s, y - 0.10 * s), (x + 0.02 * s, y - 0.10 * s)]
    pygame.draw.polygon(surf, color, pts)


# ------------------------------------------------------------------ widgets --

class Button:
    STYLES = {
        "primary": (S.CYAN, S.DARK),
        "blue": (S.BLUE, S.WHITE),
        "green": (S.GREEN, S.DARK),
        "orange": (S.ORANGE, S.DARK),
        "danger": (S.RED, S.WHITE),
        "ghost": (S.PANEL_HI, S.WHITE),
    }

    def __init__(self, rect, label, on_click=None, style="ghost", size=16, enabled=True,
                 hint=None, sound="click", align="center"):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.style = style
        self.size = size
        self.enabled = enabled
        self.hint = hint
        self.sound = sound
        self.align = align
        self.hover = 0.0
        self.press = 0.0
        self.active = False       # highlighted (e.g. selected tool)
        self.visible = True

    def handle(self, event, app=None):
        if not (self.visible and self.enabled):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self.press = 1.0
            if app is not None and self.sound:
                app.audio.play(self.sound)
            if self.on_click:
                self.on_click()
            return True
        return False

    def update(self, dt, mouse):
        over = self.visible and self.enabled and self.rect.collidepoint(mouse)
        self.hover += ((1.0 if over else 0.0) - self.hover) * min(1.0, dt * 14)
        self.press = max(0.0, self.press - dt * 5)

    def draw(self, surf):
        if not self.visible:
            return
        base, fg = self.STYLES[self.style]
        r = self.rect.inflate(int(4 * self.hover - 4 * self.press), int(2 * self.hover - 4 * self.press))
        radius = min(12, r.h // 2)
        if not self.enabled:
            rrect(surf, S.BG2, r, radius)
            rrect(surf, S.BORDER, r, radius, 1)
            fg = mix(S.MUTED, S.BG2, 0.45)
        elif self.style == "ghost":
            fill = mix(S.PANEL_HI, S.CYAN, 0.16 * self.hover + (0.22 if self.active else 0))
            rrect(surf, fill, r, radius)
            rrect(surf, mix(S.BORDER, S.CYAN, max(self.hover, 1.0 if self.active else 0)), r, radius,
                  2 if self.active else 1)
            fg = S.CYAN if self.active else S.WHITE
        else:
            if self.hover > 0.02:
                glow(surf, r.center, int(r.w * 0.55), base, int(40 * self.hover))
            rrect(surf, mix(base, S.WHITE, 0.18 * self.hover), r, radius)
        if self.align == "left":
            text(surf, self.label, (r.x + 22 + 6 * self.hover, r.centery), self.size, fg, bold=True,
                 anchor="midleft")
        else:
            text(surf, self.label, r.center, self.size, fg, bold=True, anchor="center",
                 max_width=r.w - 10)


class Segmented:
    """A row of mutually exclusive options."""
    def __init__(self, rect, options, value, on_change=None, size=15, color=S.CYAN):
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        self.value = value
        self.on_change = on_change
        self.size = size
        self.color = color
        self.anim = float(self.index)
        self.enabled = True

    @property
    def index(self):
        return self.options.index(self.value) if self.value in self.options else 0

    def cell(self, i):
        w = self.rect.w / len(self.options)
        return pygame.Rect(self.rect.x + int(i * w), self.rect.y, int(w), self.rect.h)

    def handle(self, event, app=None):
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            for i, opt in enumerate(self.options):
                if self.cell(i).collidepoint(event.pos):
                    if opt != self.value:
                        self.value = opt
                        if app is not None:
                            app.audio.play("click")
                        if self.on_change:
                            self.on_change(opt)
                    return True
        return False

    def update(self, dt, mouse=None):
        self.anim += (self.index - self.anim) * min(1.0, dt * 16)

    def draw(self, surf):
        rrect(surf, S.DARK, self.rect, self.rect.h // 2)
        rrect(surf, S.BORDER, self.rect, self.rect.h // 2, 1)
        w = self.rect.w / len(self.options)
        knob = pygame.Rect(self.rect.x + int(self.anim * w) + 3, self.rect.y + 3, int(w) - 6, self.rect.h - 6)
        rrect(surf, self.color, knob, knob.h // 2)
        for i, opt in enumerate(self.options):
            near = 1 - min(1.0, abs(self.anim - i))
            text(surf, str(opt), self.cell(i).center, self.size, mix(S.MUTED, S.DARK, near),
                 bold=True, anchor="center")


class TextInput:
    def __init__(self, rect, value="", placeholder="", max_len=60):
        self.rect = pygame.Rect(rect)
        self.value = value
        self.placeholder = placeholder
        self.max_len = max_len
        self.focus = False
        self.t = 0.0

    def handle(self, event, app=None):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focus = self.rect.collidepoint(event.pos)
            return self.focus
        if self.focus and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                self.focus = False
            elif event.unicode and event.unicode.isprintable() and len(self.value) < self.max_len:
                if event.unicode not in '\\/:*?"<>|':
                    self.value += event.unicode
            return True
        return False

    def update(self, dt, mouse=None):
        self.t += dt

    def draw(self, surf):
        rrect(surf, S.DARK, self.rect, 8)
        rrect(surf, S.CYAN if self.focus else S.BORDER, self.rect, 8, 1)
        shown = self.value or self.placeholder
        color = S.WHITE if self.value else S.MUTED
        r = text(surf, shown, (self.rect.x + 12, self.rect.centery), 15, color, anchor="midleft",
                 max_width=self.rect.w - 24)
        if self.focus and int(self.t * 2) % 2 == 0:
            x = r.right + 2 if self.value else self.rect.x + 12
            pygame.draw.line(surf, S.CYAN, (x, self.rect.y + 8), (x, self.rect.bottom - 8), 2)


class FilePicker:
    """Modal .txt file browser.  ``on_pick(path)`` is called with the choice."""
    def __init__(self, app, title, on_pick, start_dir=None):
        self.app = app
        self.title = title
        self.on_pick = on_pick
        self.dir = start_dir or S.ROOT_DIR
        self.rect = pygame.Rect(0, 0, 720, 600)
        self.rect.center = (S.WIDTH // 2, S.HEIGHT // 2)
        self.scroll = 0
        self.entries = []
        self.error = ""
        self.done = False
        self.cancel = Button((self.rect.right - 150, self.rect.bottom - 58, 126, 40), "CANCEL", self.close)
        self.refresh()

    def close(self):
        self.done = True

    def refresh(self):
        self.entries = []
        self.error = ""
        try:
            names = sorted(os.listdir(self.dir), key=str.lower)
        except OSError as exc:
            self.error = f"Cannot open folder: {exc.strerror or exc}"
            names = []
        parent = os.path.dirname(self.dir)
        if parent and parent != self.dir:
            self.entries.append(("..", parent, True))
        for n in names:
            full = os.path.join(self.dir, n)
            if os.path.isdir(full) and not n.startswith((".", "__")):
                self.entries.append((n + "/", full, True))
        for n in names:
            full = os.path.join(self.dir, n)
            if os.path.isfile(full) and n.lower().endswith(".txt") and n.lower() != "requirements.txt":
                self.entries.append((n, full, False))
        self.scroll = 0

    def row_rect(self, i):
        return pygame.Rect(self.rect.x + 24, self.rect.y + 104 + (i - self.scroll) * 38, self.rect.w - 48, 34)

    VISIBLE = 11

    def handle(self, event):
        if self.cancel.handle(event, self.app):
            return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(max(0, len(self.entries) - self.VISIBLE), self.scroll - event.y))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                self.close()
                return True
            for i in range(self.scroll, min(len(self.entries), self.scroll + self.VISIBLE)):
                if self.row_rect(i).collidepoint(event.pos):
                    name, full, is_dir = self.entries[i]
                    self.app.audio.play("click")
                    if is_dir:
                        self.dir = full
                        self.refresh()
                    else:
                        self.done = True
                        self.on_pick(full)
                    break
        return True

    def update(self, dt, mouse):
        self.cancel.update(dt, mouse)

    def draw(self, surf):
        rrect_alpha(surf, S.DARK, surf.get_rect(), 0, 190)
        panel(surf, self.rect, self.title, title_size=16)
        text(surf, self.dir, (self.rect.x + 26, self.rect.y + 52), 13, S.MUTED, mono=True,
             max_width=self.rect.w - 52)
        text(surf, "Click a folder to open it or a .txt file to select it.",
             (self.rect.x + 26, self.rect.y + 76), 13, S.MUTED)
        mouse = self.app.mouse
        for i in range(self.scroll, min(len(self.entries), self.scroll + self.VISIBLE)):
            name, full, is_dir = self.entries[i]
            r = self.row_rect(i)
            hot = r.collidepoint(mouse)
            rrect(surf, S.PANEL_HI if hot else S.BG2, r, 8)
            if hot:
                rrect(surf, S.CYAN, r, 8, 1)
            text(surf, name, (r.x + 14, r.centery), 15, S.ORANGE if is_dir else S.WHITE,
                 anchor="midleft", mono=True, max_width=r.w - 120)
            text(surf, "FOLDER" if is_dir else "FILE", (r.right - 14, r.centery), 11, S.MUTED,
                 bold=True, anchor="midright")
        if self.error:
            text(surf, self.error, (self.rect.x + 26, self.rect.bottom - 46), 14, S.RED)
        elif len(self.entries) > self.VISIBLE:
            text(surf, f"Scroll for more ({len(self.entries)} items)",
                 (self.rect.x + 26, self.rect.bottom - 46), 13, S.MUTED)
        self.cancel.draw(surf)


class WidgetGroup:
    """Convenience container to forward events / update / draw."""
    def __init__(self, app):
        self.app = app
        self.items = []

    def add(self, widget):
        self.items.append(widget)
        return widget

    def handle(self, event):
        for w in self.items:
            if w.handle(event, self.app):
                return True
        return False

    def update(self, dt):
        for w in self.items:
            w.update(dt, self.app.mouse)

    def draw(self, surf):
        for w in self.items:
            w.draw(surf)
