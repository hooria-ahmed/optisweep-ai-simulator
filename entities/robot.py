"""The OptiSweep cleaning robot: a vector-drawn, fully animated character.

The robot is drawn facing "up" on an oversized canvas and then rotated to its
heading and scaled down, which also anti-aliases it.  It has a metallic shell,
two wheels with moving treads, spinning side brushes, a sensor bumper, an LED
ring, a direction chevron and a small display with digital eyes whose
expression follows the robot's state.
"""
import math
import random

import pygame

from config import settings as S

HEADINGS = {(-1, 0): 0.0, (0, 1): 90.0, (1, 0): 180.0, (0, -1): 270.0}
DIRECTION_NAMES = {(-1, 0): "UP", (0, 1): "RIGHT", (1, 0): "DOWN", (0, -1): "LEFT"}

LED = {"idle": S.CYAN, "moving": S.CYAN, "thinking": S.PURPLE, "cleaning": S.GREEN,
       "charging": S.BLUE, "error": S.RED, "victory": S.GREEN}


def _band(surf, color, cx, cy, r_in, r_out, a0, a1, steps=24):
    """Filled ring segment between angles a0..a1 (degrees, 0 = up, clockwise)."""
    pts = []
    for i in range(steps + 1):
        a = math.radians(a0 + (a1 - a0) * i / steps - 90)
        pts.append((cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
    for i in range(steps, -1, -1):
        a = math.radians(a0 + (a1 - a0) * i / steps - 90)
        pts.append((cx + r_in * math.cos(a), cy + r_in * math.sin(a)))
    pygame.draw.polygon(surf, color, pts)


class Robot:
    def __init__(self, cell=(0, 0), heading=180.0):
        self.row, self.col = float(cell[0]), float(cell[1])
        self.heading = heading
        self.target_heading = heading
        self.state = "idle"
        self.direction = None           # last move delta (dr, dc)
        self.t = random.uniform(0, 10)
        self.wheel = 0.0
        self.brush = 0.0
        self.blink = random.uniform(1.5, 4.0)
        self.battery = 100.0
        self.charge_level = 1.0
        self._move = None               # [from, to, elapsed, duration]

    # ------------------------------------------------------------- control --
    @property
    def cell(self):
        return (int(round(self.row)), int(round(self.col)))

    @property
    def busy(self):
        return self._move is not None

    def place(self, cell, heading=None):
        self.row, self.col = float(cell[0]), float(cell[1])
        self._move = None
        if heading is not None:
            self.heading = self.target_heading = heading

    def move_to(self, cell, duration):
        """Glide to a 4-neighbour cell.  Diagonal or longer moves are refused."""
        frm = self.cell
        delta = (cell[0] - frm[0], cell[1] - frm[1])
        if delta not in HEADINGS:
            raise ValueError(f"Illegal robot move {frm} -> {cell}")
        self.direction = delta
        self.target_heading = HEADINGS[delta]
        self._move = [frm, cell, 0.0, max(0.02, duration)]
        self.state = "moving"

    def face(self, delta):
        if delta in HEADINGS:
            self.target_heading = HEADINGS[delta]

    def update(self, dt):
        """Advance animation.  Returns True on the frame a move completes."""
        self.t += dt
        arrived = False
        turn = ((self.target_heading - self.heading + 180) % 360) - 180
        step = 900 * dt
        if abs(turn) <= step:
            self.heading = self.target_heading % 360
        else:
            self.heading = (self.heading + math.copysign(step, turn)) % 360
            self.wheel += dt * 4
        if self._move:
            frm, to, elapsed, duration = self._move
            elapsed = min(duration, elapsed + dt)
            self._move[2] = elapsed
            k = elapsed / duration
            self.row = frm[0] + (to[0] - frm[0]) * k
            self.col = frm[1] + (to[1] - frm[1]) * k
            self.wheel += dt / duration * 3.0
            if elapsed >= duration:
                self.row, self.col = float(to[0]), float(to[1])
                self._move = None
                arrived = True
        spin = {"moving": 620, "cleaning": 1300, "charging": 0, "error": 0}.get(self.state, 70)
        self.brush = (self.brush + spin * dt) % 360
        self.blink -= dt
        if self.blink < -0.14:
            self.blink = random.uniform(2.0, 4.5)
        return arrived

    # ------------------------------------------------------------- drawing --
    def draw(self, surf, center, size, shadow=True):
        """Draw the robot centred on ``center``; ``size`` is its body diameter
        plus brushes, roughly the footprint of one grid cell."""
        from gui import ui
        led = LED.get(self.state, S.CYAN)
        pulse = 0.5 + 0.5 * math.sin(self.t * (7 if self.state in ("cleaning", "thinking") else 3))
        if shadow:
            sh = pygame.Surface((int(size * 0.8), int(size * 0.8)), pygame.SRCALPHA)
            pygame.draw.circle(sh, (0, 0, 0, 70), sh.get_rect().center, int(size * 0.39))
            surf.blit(sh, (center[0] - size * 0.4 + size * 0.03, center[1] - size * 0.4 + size * 0.05))
        ui.glow(surf, center, size * 0.72, led, int(38 + 30 * pulse))

        C = max(48, int(size * (2.4 if size < 150 else 1.5)))   # supersample small sprites more
        C += C % 2
        cv = pygame.Surface((C, C), pygame.SRCALPHA)
        cx = cy = C / 2
        R = C * 0.30
        lw = max(1, int(C * 0.012))

        # --- wheels with moving treads ---------------------------------------
        ww, wh = R * 0.44, R * 0.88
        for sx in (-1, 1):
            wr = pygame.Rect(0, 0, int(ww), int(wh))
            wr.center = (int(cx + sx * R * 0.95), int(cy + R * 0.10))
            pygame.draw.rect(cv, (34, 42, 56), wr, border_radius=int(ww * 0.35))
            gap = wh / 5
            off = (self.wheel * gap) % gap
            for i in range(-1, 6):
                y = wr.y + i * gap + off
                if wr.y + lw * 2 < y < wr.bottom - lw * 2:
                    pygame.draw.line(cv, (118, 134, 156), (wr.x + lw, y), (wr.right - lw, y), lw * 2)
            pygame.draw.rect(cv, (84, 98, 120), wr, lw, border_radius=int(ww * 0.35))

        # --- spinning side brushes (partly under the shell) ------------------
        for sx in (-1, 1):
            hx, hy = cx + sx * R * 0.66, cy - R * 0.72
            sweep = pygame.Surface((C, C), pygame.SRCALPHA)
            pygame.draw.circle(sweep, (*led, 34), (int(hx), int(hy)), int(R * 0.36))
            cv.blit(sweep, (0, 0))
            for k in range(4):
                a = math.radians(self.brush * sx + k * 90)
                ex, ey = hx + math.cos(a) * R * 0.34, hy + math.sin(a) * R * 0.34
                pygame.draw.line(cv, (150, 232, 255), (hx, hy), (ex, ey), max(2, int(C * 0.026)))
                pygame.draw.circle(cv, S.ORANGE, (int(ex), int(ey)), max(2, int(C * 0.02)))
            pygame.draw.circle(cv, (30, 38, 50), (int(hx), int(hy)), max(2, int(R * 0.10)))

        # --- metallic shell ---------------------------------------------------
        pygame.draw.circle(cv, (46, 58, 76), (cx, cy), R)
        pygame.draw.circle(cv, (150, 164, 182), (cx, cy), R * 0.95)
        pygame.draw.circle(cv, (190, 201, 216), (cx - R * 0.03, cy - R * 0.05), R * 0.88)
        pygame.draw.circle(cv, (214, 223, 234), (cx - R * 0.07, cy - R * 0.10), R * 0.78)
        # front bumper with sensors
        _band(cv, (38, 50, 66), cx, cy, R * 0.80, R * 0.99, -62, 62)
        for i, ang in enumerate((-42, -21, 0, 21, 42)):
            a = math.radians(ang - 90)
            on = (int(self.t * 6) + i) % 5 == 0 if self.state in ("moving", "thinking") else pulse > 0.5
            col = led if (on or i == 2) else (70, 92, 116)
            pygame.draw.circle(cv, col, (int(cx + R * 0.895 * math.cos(a)), int(cy + R * 0.895 * math.sin(a))),
                               max(2, int(R * 0.045)))
        # rear dust-bin handle and vents
        hr = pygame.Rect(0, 0, int(R * 0.5), int(R * 0.09))
        hr.center = (int(cx), int(cy + R * 0.80))
        pygame.draw.rect(cv, (120, 134, 152), hr, border_radius=hr.h // 2)

        # --- dark glass top panel + LED ring ---------------------------------
        pygame.draw.circle(cv, (22, 30, 42), (cx, cy), R * 0.66)
        pygame.draw.circle(cv, (34, 46, 62), (cx, cy), R * 0.58)
        ring_dim = ui.mix((40, 56, 74), led, 0.25)
        if self.state == "charging":
            _band(cv, ring_dim, cx, cy, R * 0.585, R * 0.665, 0, 360, 48)
            _band(cv, led, cx, cy, R * 0.585, R * 0.665, 0, max(4, 360 * self.charge_level), 48)
        else:
            _band(cv, ui.mix(ring_dim, led, 0.45 + 0.55 * pulse), cx, cy, R * 0.585, R * 0.665, 0, 360, 48)
        # glass highlight
        _band(cv, (58, 74, 96), cx, cy, R * 0.46, R * 0.53, 200, 250, 10)

        # --- direction chevron -----------------------------------------------
        pygame.draw.polygon(cv, led, [(cx, cy - R * 0.55), (cx - R * 0.12, cy - R * 0.38),
                                      (cx, cy - R * 0.43), (cx + R * 0.12, cy - R * 0.38)])

        # --- display with digital eyes ---------------------------------------
        dr = pygame.Rect(0, 0, int(R * 0.80), int(R * 0.42))
        dr.center = (int(cx), int(cy + R * 0.10))
        pygame.draw.rect(cv, (6, 10, 18), dr, border_radius=int(dr.h * 0.35))
        pygame.draw.rect(cv, ui.mix((30, 44, 60), led, 0.5), dr, lw, border_radius=int(dr.h * 0.35))
        self._draw_face(cv, dr, R, led, lw)

        sprite = pygame.transform.rotozoom(cv, -self.heading, 1.2 * size / C)
        bob = math.sin(self.t * 2.2) * size * 0.012 if self.state in ("idle", "thinking", "charging") else 0
        if self.state == "cleaning":
            center = (center[0] + math.sin(self.t * 38) * size * 0.012, center[1] + math.cos(self.t * 31) * size * 0.012)
        surf.blit(sprite, sprite.get_rect(center=(int(center[0]), int(center[1] + bob))))

    def _draw_face(self, cv, dr, R, led, lw):
        cx, cy = dr.center
        ew, eh = R * 0.15, R * 0.24
        gap = R * 0.21
        thick = max(2, int(R * 0.06))
        state = self.state
        if state == "error":
            for sx in (-1, 1):
                x = cx + sx * gap
                d = R * 0.09
                pygame.draw.line(cv, S.RED, (x - d, cy - d), (x + d, cy + d), thick)
                pygame.draw.line(cv, S.RED, (x - d, cy + d), (x + d, cy - d), thick)
        elif state in ("cleaning", "victory"):
            for sx in (-1, 1):
                x = cx + sx * gap
                d = R * 0.10
                pygame.draw.lines(cv, led, False, [(x - d, cy + d * 0.5), (x, cy - d * 0.6), (x + d, cy + d * 0.5)], thick)
        elif state == "thinking":
            for i in range(3):
                dy = -abs(math.sin(self.t * 6 - i * 0.7)) * R * 0.09
                pygame.draw.circle(cv, led, (int(cx + (i - 1) * R * 0.2), int(cy + R * 0.04 + dy)), max(2, int(R * 0.055)))
        elif state == "charging":
            bars = 4
            bw = dr.w * 0.15
            for i in range(bars):
                on = self.charge_level * bars > i + 0.05
                br = pygame.Rect(0, 0, int(bw), int(dr.h * 0.5))
                br.center = (int(cx + (i - 1.5) * bw * 1.35), int(cy))
                pygame.draw.rect(cv, led if on else (30, 44, 60), br, border_radius=2)
        else:
            look = math.sin(self.t * 0.9) * R * 0.05 if state == "idle" else 0
            h = eh * (0.12 if self.blink < 0 else 1.0)
            for sx in (-1, 1):
                er = pygame.Rect(0, 0, int(ew), max(2, int(h)))
                er.center = (int(cx + sx * gap + look), int(cy))
                pygame.draw.rect(cv, led, er, border_radius=int(ew * 0.45))
