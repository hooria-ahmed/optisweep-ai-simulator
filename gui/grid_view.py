"""Dynamic grid renderer shared by every screen that shows an environment."""
import math

import pygame

from config import settings as S
from gui import ui

FREE = (24, 32, 44)
FREE_EDGE = (34, 45, 60)
MARGIN = 22


class GridView:
    def __init__(self, grid, rect, coords=True):
        self.grid = grid
        self.rect = pygame.Rect(rect)
        m = MARGIN if coords else 0
        self.coords = coords
        self.cell = max(4, int(min((self.rect.w - m) / grid.cols, (self.rect.h - m) / grid.rows)))
        w, h = self.cell * grid.cols, self.cell * grid.rows
        self.x0 = self.rect.x + m + (self.rect.w - m - w) // 2
        self.y0 = self.rect.y + m + (self.rect.h - m - h) // 2
        self.area = pygame.Rect(self.x0, self.y0, w, h)
        self.gap = max(1, self.cell // 22)
        self.radius = max(2, self.cell // 7)
        self._static = None

    # ----------------------------------------------------------- geometry --
    def cell_rect(self, r, c):
        g = self.gap
        return pygame.Rect(self.x0 + c * self.cell + g, self.y0 + r * self.cell + g,
                           self.cell - 2 * g, self.cell - 2 * g)

    def center(self, pos):
        """Pixel centre of a (row, col) position; fractional values allowed."""
        return (self.x0 + (pos[1] + 0.5) * self.cell, self.y0 + (pos[0] + 0.5) * self.cell)

    def cell_at(self, pixel):
        if not self.area.collidepoint(pixel):
            return None
        return (int((pixel[1] - self.y0) // self.cell), int((pixel[0] - self.x0) // self.cell))

    # -------------------------------------------------------- static layer --
    def _build_static(self):
        surf = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        ox, oy = -self.rect.x, -self.rect.y
        back = self.area.move(ox, oy).inflate(8, 8)
        ui.rrect(surf, S.DARK, back, self.radius + 4)
        g = self.grid
        for r in range(g.rows):
            for c in range(g.cols):
                cr = self.cell_rect(r, c).move(ox, oy)
                if (r, c) in g.obstacles:
                    self._brick(surf, cr)
                else:
                    ui.rrect(surf, FREE, cr, self.radius)
                    ui.rrect(surf, FREE_EDGE, cr, self.radius, 1)
        if self.coords:
            size = max(9, min(13, self.cell // 4))
            for r in range(g.rows):
                ui.text(surf, str(r), (self.x0 + ox - 9, self.y0 + oy + (r + 0.5) * self.cell), size,
                        S.MUTED, anchor="midright", mono=True)
            for c in range(g.cols):
                ui.text(surf, str(c), (self.x0 + ox + (c + 0.5) * self.cell, self.y0 + oy - 9), size,
                        S.MUTED, anchor="midbottom", mono=True)
        self._static = surf

    def _brick(self, surf, cr):
        ui.rrect(surf, (16, 20, 28), cr, self.radius)
        rows = 3 if cr.h >= 24 else 2
        bh = cr.h / rows
        for i in range(rows):
            cols = 2
            off = (cr.w / 4) if i % 2 else 0
            y = cr.y + i * bh
            x = cr.x - off
            k = 0
            while x < cr.right:
                bw = cr.w / cols
                br = pygame.Rect(int(x) + 1, int(y) + 1, int(bw) - 2, int(bh) - 2).clip(cr.inflate(-2, -2))
                if br.w > 2 and br.h > 2:
                    shade = 52 + ((i * 7 + k * 13) % 3) * 7
                    pygame.draw.rect(surf, (shade, shade + 8, shade + 20), br, border_radius=2)
                    pygame.draw.line(surf, (shade + 22, shade + 30, shade + 44), br.topleft,
                                     (br.right - 1, br.top))
                x += bw
                k += 1
        ui.rrect(surf, (70, 82, 100), cr, self.radius, 1)

    # ------------------------------------------------------------- drawing --
    def draw(self, surf, t, cleaned=(), visited=None, path=None, playback=None, slots=None,
             start=None, goal=None, show_values=False, accent=S.CYAN, tasks=True, current_task=None,
             charging=False):
        if self._static is None:
            self._build_static()
        surf.blit(self._static, self.rect)
        g = self.grid
        cell = self.cell

        # visited trail (subtle blue)
        if visited:
            for pos in visited:
                if pos not in g.pos_to_dirty and pos != g.charging_station:
                    ui.rrect_alpha(surf, S.BLUE, self.cell_rect(*pos), self.radius, 38)

        # search exploration overlay
        if playback is not None:
            n = max(1, playback.nodes_expanded)
            for pos, order in playback.explored.items():
                age = (n - order) / n
                ui.rrect_alpha(surf, accent, self.cell_rect(*pos), self.radius, int(95 - 50 * age))
            pulse = 0.5 + 0.5 * math.sin(t * 8)
            for pos in playback.frontier:
                cr = self.cell_rect(*pos)
                ui.rrect_alpha(surf, S.WHITE, cr, self.radius, int(26 + 20 * pulse))
                ui.rrect(surf, ui.mix(accent, S.WHITE, 0.35 + 0.3 * pulse), cr, self.radius, 2)
            if playback.current is not None and not playback.done:
                cr = self.cell_rect(*playback.current)
                ui.glow(surf, cr.center, cell * 0.8, accent, 110)
                ui.rrect(surf, S.WHITE, cr, self.radius, 3)

        # special cells
        if tasks:
            for label, pos in g.dirty_locations.items():
                self._dirty(surf, t, label, pos, label in cleaned, slots, label == current_task)
        self._charger(surf, t, charging)

        # start / goal markers (race & explorer)
        if start is not None:
            self._marker(surf, start, S.GREEN, "S", t)
        if goal is not None:
            self._marker(surf, goal, S.RED, "G", t)

        if show_values and playback is not None and cell >= 40:
            self._values(surf, playback)

        if path and len(path) > 1:
            self._path(surf, t, path, accent)

    def _dirty(self, surf, t, label, pos, cleaned, slots, current):
        cr = self.cell_rect(*pos)
        cell = self.cell
        if cleaned:
            ui.rrect(surf, ui.mix(FREE, S.GREEN, 0.20), cr, self.radius)
            ui.rrect(surf, S.GREEN, cr, self.radius, 2)
            ui.check_mark(surf, S.GREEN, (cr.centerx, cr.centery + cell * 0.06), cell * 0.36,
                          max(2, cell // 14))
            tw = 0.5 + 0.5 * math.sin(t * 3 + pos[0] * 1.7 + pos[1])
            sx, sy = cr.right - cell * 0.22, cr.y + cell * 0.24
            d = cell * 0.09 * (0.5 + tw)
            pygame.draw.line(surf, S.WHITE, (sx - d, sy), (sx + d, sy), 2)
            pygame.draw.line(surf, S.WHITE, (sx, sy - d), (sx, sy + d), 2)
        else:
            pulse = 0.5 + 0.5 * math.sin(t * (6 if current else 2.5) + pos[1])
            ui.rrect(surf, ui.mix(FREE, S.ORANGE, 0.16 + (0.14 * pulse if current else 0.04 * pulse)), cr, self.radius)
            if current:
                ui.glow(surf, cr.center, cell * 0.75, S.ORANGE, int(50 + 50 * pulse))
            ui.rrect(surf, S.ORANGE, cr, self.radius, 3 if current else 2)
            # dirt icon: a cluster of grime blobs
            cx, cy = cr.centerx, cr.centery + cell * 0.08
            for dx, dy, rr, col in ((-0.14, 0.02, 0.11, (122, 92, 58)), (0.10, -0.04, 0.13, (146, 110, 66)),
                                    (0.02, 0.12, 0.09, (104, 78, 50)), (0.20, 0.12, 0.05, (160, 124, 78)),
                                    (-0.22, -0.12, 0.04, (160, 124, 78)), (-0.04, -0.15, 0.05, (132, 100, 62))):
                pygame.draw.circle(surf, col, (int(cx + dx * cell), int(cy + dy * cell)), max(1, int(rr * cell)))
        size = max(9, min(16, cell // 5))
        if cell >= 26:
            ui.text(surf, label, (cr.x + max(4, cell * 0.10), cr.y + max(3, cell * 0.07)), size,
                    S.GREEN if cleaned else S.ORANGE, bold=True)
            if slots and label in slots and cell >= 48:
                ui.text(surf, slots[label], (cr.right - max(3, cell * 0.07), cr.bottom - max(2, cell * 0.04)),
                        max(9, size - 2), S.MUTED, bold=True, anchor="bottomright")

    def _charger(self, surf, t, charging):
        pos = self.grid.charging_station
        if pos is None:
            return
        cr = self.cell_rect(*pos)
        cell = self.cell
        pulse = (t * (1.6 if charging else 0.7)) % 1.0
        ui.rrect(surf, ui.mix(FREE, S.BLUE, 0.30), cr, self.radius)
        ui.glow(surf, cr.center, cell * (0.7 + 0.25 * pulse), S.BLUE, int(90 * (1 - pulse)) + (60 if charging else 10))
        ui.rrect(surf, S.BLUE, cr, self.radius, 2)
        ring = cr.inflate(-int(cell * 0.28 * (1 - pulse)) - 4, -int(cell * 0.28 * (1 - pulse)) - 4)
        ui.rrect(surf, ui.mix(S.BLUE, FREE, pulse), ring, self.radius, 1)
        ui.bolt(surf, ui.mix(S.BLUE, S.WHITE, 0.55 + 0.45 * math.sin(t * 5)), cr.center, cell * 0.52)
        if cell >= 40:
            ui.text(surf, "C", (cr.x + max(3, cell * 0.07), cr.y + max(2, cell * 0.04)),
                    max(9, min(16, cell // 5)), S.BLUE, bold=True)

    def _marker(self, surf, pos, color, letter, t):
        cr = self.cell_rect(*pos)
        pulse = 0.5 + 0.5 * math.sin(t * 5)
        ui.glow(surf, cr.center, self.cell * 0.7, color, int(60 + 50 * pulse))
        ui.rrect(surf, color, cr, self.radius, 3)
        b = pygame.Rect(0, 0, max(14, self.cell // 3), max(14, self.cell // 3))
        b.bottomright = (cr.right - 2, cr.bottom - 2)
        ui.rrect(surf, color, b, 4)
        ui.text(surf, letter, b.center, max(10, b.h - 5), S.DARK, bold=True, anchor="center")

    def _values(self, surf, pb):
        cell = self.cell
        big = max(11, min(20, cell // 4))
        small = max(8, min(12, cell // 7))
        for pos, v in pb.values.items():
            if pos not in pb.explored and pos not in pb.frontier:
                continue
            cr = self.cell_rect(*pos)
            col = S.WHITE if pos in pb.explored else S.MUTED
            if "f" in v:
                ui.text(surf, str(v["f"]), (cr.centerx, cr.centery + cell * 0.08), big, col, bold=True,
                        anchor="center", mono=True)
                if cell >= 56:
                    ui.text(surf, f"g{v['g']}", (cr.x + 4, cr.bottom - 3), small, col, anchor="bottomleft", mono=True)
                    ui.text(surf, f"h{v['h']}", (cr.right - 4, cr.bottom - 3), small, col, anchor="bottomright", mono=True)
            else:
                ui.text(surf, str(v["depth"]), cr.center, big, col, bold=True, anchor="center", mono=True)

    def _path(self, surf, t, path, color):
        pts = [self.center(p) for p in path]
        cell = self.cell
        layer = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        local = [(x - self.rect.x, y - self.rect.y) for x, y in pts]
        for width, alpha in ((cell * 0.40, 34), (cell * 0.22, 70)):
            w = max(2, int(width))
            pygame.draw.lines(layer, (*color, alpha), False, local, w)
            for p in local:
                pygame.draw.circle(layer, (*color, alpha), (int(p[0]), int(p[1])), w // 2)
        surf.blit(layer, self.rect)
        core = max(2, int(cell * 0.07))
        pygame.draw.lines(surf, color, False, pts, core)
        # energy pulses travelling along the path
        seg = len(pts) - 1
        for k in range(0, seg, 2):
            u = (t * 2.2) % 2.0 + k
            i = int(u)
            if i < seg:
                f = u - i
                x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
                y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
                pygame.draw.circle(surf, S.WHITE, (int(x), int(y)), core + 1)
        ex, ey = pts[-1]
        r = cell * (0.22 + 0.05 * math.sin(t * 6))
        pygame.draw.circle(surf, color, (int(ex), int(ey)), int(r), max(2, core))


LEGEND = [("charger", "Charging station"), ("free", "Free cell"), ("obstacle", "Obstacle"),
          ("dirty", "Dirty"), ("cleaned", "Cleaned"), ("visited", "Visited"),
          ("path", "Current path"), ("explored", "Explored"), ("frontier", "Frontier")]


def draw_legend(surf, pos, keys=None, accent=S.CYAN, spacing=None, size=13):
    """Horizontal legend row.  Returns the x after the last item."""
    x, y = pos
    for key, label in LEGEND:
        if keys is not None and key not in keys:
            continue
        sw = pygame.Rect(x, y, 18, 18)
        if key == "charger":
            ui.rrect(surf, ui.mix(FREE, S.BLUE, 0.3), sw, 4); ui.rrect(surf, S.BLUE, sw, 4, 2)
            ui.bolt(surf, S.WHITE, sw.center, 11)
        elif key == "free":
            ui.rrect(surf, FREE, sw, 4); ui.rrect(surf, FREE_EDGE, sw, 4, 1)
        elif key == "obstacle":
            ui.rrect(surf, (58, 66, 80), sw, 4); ui.rrect(surf, (84, 96, 116), sw, 4, 1)
            pygame.draw.line(surf, (16, 20, 28), (sw.x + 1, sw.centery), (sw.right - 2, sw.centery))
            pygame.draw.line(surf, (16, 20, 28), (sw.centerx, sw.y + 1), (sw.centerx, sw.centery))
        elif key == "dirty":
            ui.rrect(surf, ui.mix(FREE, S.ORANGE, 0.2), sw, 4); ui.rrect(surf, S.ORANGE, sw, 4, 2)
            pygame.draw.circle(surf, (146, 110, 66), sw.center, 4)
        elif key == "cleaned":
            ui.rrect(surf, ui.mix(FREE, S.GREEN, 0.2), sw, 4); ui.rrect(surf, S.GREEN, sw, 4, 2)
            ui.check_mark(surf, S.GREEN, sw.center, 9, 2)
        elif key == "visited":
            ui.rrect(surf, ui.mix(FREE, S.BLUE, 0.25), sw, 4); ui.rrect(surf, FREE_EDGE, sw, 4, 1)
        elif key == "path":
            pygame.draw.line(surf, accent, (sw.x, sw.centery), (sw.right, sw.centery), 4)
        elif key == "explored":
            ui.rrect(surf, ui.mix(FREE, accent, 0.4), sw, 4)
        elif key == "frontier":
            ui.rrect(surf, ui.mix(FREE, S.WHITE, 0.15), sw, 4); ui.rrect(surf, ui.mix(accent, S.WHITE, 0.5), sw, 4, 2)
        r = ui.text(surf, label, (x + 25, y + 9), size, S.MUTED, anchor="midleft")
        x = r.right + (spacing or 20)
    return x
