"""AI BRAIN panel: live view of the CSP scheduler and the search algorithm.

The panel only *draws* the state of the two playbacks (``gui.playback``), which
in turn replay events recorded from the real algorithms.
"""
import math

import pygame

from config import settings as S
from gui import ui
from gui.playback import TAG_COLOR, cell_str


def draw_log(surf, rect, entries, line_h=18, size=12):
    """Newest entries at the bottom, older ones fading out."""
    rect = pygame.Rect(rect)
    ui.rrect(surf, S.DARK, rect, 8)
    lines = max(1, (rect.h - 8) // line_h)
    shown = entries[-lines:]
    y = rect.bottom - 5 - len(shown) * line_h
    for i, (tag, msg) in enumerate(shown):
        age = len(shown) - 1 - i
        fade = max(0.35, 1.0 - age * 0.11)
        color = ui.mix(S.DARK, TAG_COLOR.get(tag, S.WHITE), fade)
        r = ui.text(surf, f"[{tag}]", (rect.x + 8, y), size, color, bold=True, mono=True)
        ui.text(surf, msg, (r.right + 6, y), size, ui.mix(S.DARK, S.WHITE, fade), mono=True,
                max_width=rect.right - r.right - 12)
        y += line_h
    if not entries:
        ui.text(surf, "waiting for activity...", (rect.x + 10, rect.bottom - 22), size, S.MUTED, mono=True)


def stat_tile(surf, rect, label, value, color=S.CYAN):
    rect = pygame.Rect(rect)
    ui.rrect(surf, S.DARK, rect, 8)
    ui.rrect(surf, ui.mix(S.BORDER, color, 0.5), rect, 8, 1)
    ui.text(surf, label, (rect.centerx, rect.y + 6), 10, S.MUTED, bold=True, anchor="midtop")
    ui.text(surf, str(value), (rect.centerx, rect.bottom - 5), 20, color, bold=True, anchor="midbottom",
            mono=True)


def draw_domains(surf, rect, csp, t):
    """Domain table: one row per variable, one chip per time slot.
    Chips show the live domain: available, assigned, just pruned or removed."""
    rect = pygame.Rect(rect)
    variables, slots = csp.variables, csp.time_slots
    if not variables or not slots:
        return
    row_h = min(26, rect.h / len(variables))
    label_w = 40
    chip_w = min(46, (rect.w - label_w) / len(slots))
    chip_h = max(8, int(row_h) - 5)
    size = 11 if chip_w >= 30 and chip_h >= 14 else 0
    for i, var in enumerate(variables):
        y = rect.y + i * row_h
        current = var == csp.current_var
        assigned = csp.assignment.get(var)
        col = S.GREEN if assigned else (S.CYAN if current else S.MUTED)
        if current:
            ui.rrect_alpha(surf, S.CYAN, (rect.x - 4, y - 2, rect.w + 8, row_h - 1), 6, 30)
        ui.text(surf, var, (rect.x + 2, y + chip_h / 2), 13, col, bold=True, anchor="midleft")
        domain = csp.domains.get(var, [])
        pruned = csp.pruned.get(var, [])
        for j, slot in enumerate(slots):
            chip = pygame.Rect(int(rect.x + label_w + j * chip_w), int(y), int(chip_w) - 4, chip_h)
            if assigned == slot:
                ui.rrect(surf, S.GREEN, chip, 5)
                fg = S.DARK
            elif slot in pruned:
                k = 0.5 + 0.5 * math.sin(t * 10)
                ui.rrect(surf, ui.mix(S.DARK, S.RED, 0.35 + 0.3 * k), chip, 5)
                ui.rrect(surf, S.RED, chip, 5, 1)
                pygame.draw.line(surf, S.RED, chip.bottomleft, chip.topright, 2)
                fg = S.RED
            elif assigned is None and slot in domain:
                trying = current and slot == csp.current_value
                ui.rrect(surf, ui.mix(S.DARK, S.CYAN, 0.55 if trying else 0.18), chip, 5)
                ui.rrect(surf, S.WHITE if trying else S.CYAN, chip, 5, 1)
                fg = S.WHITE if trying else S.CYAN
            else:
                ui.rrect(surf, S.DARK, chip, 5)
                ui.rrect(surf, S.BORDER, chip, 5, 1)
                fg = ui.mix(S.BORDER, S.MUTED, 0.4)
            if size:
                ui.text(surf, slot, chip.center, size, fg, bold=True, anchor="center")


class AIBrainPanel:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)

    def draw(self, surf, t, csp, search, nav_log, phase, algorithm, leg_text=""):
        r = self.rect
        ui.rrect(surf, S.PANEL, r, 14)
        ui.rrect(surf, S.BORDER, r, 14, 1)
        active_csp = phase == "csp"
        active_search = phase == "search"
        thinking = active_csp or active_search

        # ---- header with pulsing "chip" icon ---------------------------------
        cx, cy = r.x + 30, r.y + 26
        pulse = 0.5 + 0.5 * math.sin(t * (9 if thinking else 2))
        ui.glow(surf, (cx, cy), 26, S.CYAN, int(50 + 70 * pulse) if thinking else 30)
        chip = pygame.Rect(0, 0, 22, 22)
        chip.center = (cx, cy)
        for k in (-6, 0, 6):
            pygame.draw.line(surf, S.CYAN, (cx + k, cy - 15), (cx + k, cy + 15), 1)
            pygame.draw.line(surf, S.CYAN, (cx - 15, cy + k), (cx + 15, cy + k), 1)
        ui.rrect(surf, S.DARK, chip, 5)
        ui.rrect(surf, S.CYAN, chip, 5, 2)
        pygame.draw.circle(surf, ui.mix(S.DARK, S.CYAN, pulse), (cx, cy), 4)
        ui.text(surf, "AI BRAIN", (r.x + 54, r.y + 15), 20, S.WHITE, bold=True)
        label, color = {
            "csp": ("SCHEDULING", S.PURPLE), "csp_done": ("SCHEDULE READY", S.GREEN),
            "search": ("SEARCHING", S.CYAN), "move": ("EXECUTING", S.BLUE), "clean": ("EXECUTING", S.GREEN),
            "charge": ("DOCKING", S.BLUE), "done": ("COMPLETE", S.GREEN), "failed": ("FAILED", S.RED),
        }.get(phase, ("STANDBY", S.MUTED))
        ui.badge(surf, label, (r.right - 16, r.y + 26), color, 11, anchor="midright", filled=thinking)

        # ---- A. CSP brain -----------------------------------------------------
        box = pygame.Rect(r.x + 10, r.y + 52, r.w - 20, 372)
        self._section(surf, box, "CSP BRAIN", "CLEANING SCHEDULER", S.PURPLE, active_csp)
        x, y = box.x + 12, box.y + 34
        var = csp.current_var or "-"
        val = csp.assignment.get(csp.current_var) or csp.current_value or "-"
        ui.text(surf, "VARIABLE", (x, y), 10, S.MUTED, bold=True)
        ui.text(surf, var, (x + 62, y - 4), 17, S.CYAN, bold=True)
        ui.text(surf, "TIME SLOT", (x + 108, y), 10, S.MUTED, bold=True)
        ui.text(surf, val, (x + 174, y - 4), 17, S.GREEN if csp.current_var in csp.assignment else S.WHITE, bold=True)
        dom = csp.domains.get(csp.current_var, []) if csp.current_var else []
        ui.text(surf, "DOMAIN", (x + 216, y), 10, S.MUTED, bold=True)
        ui.text(surf, "{" + ",".join(dom) + "}" if csp.current_var else "-", (x + 266, y - 1), 12, S.WHITE,
                mono=True, max_width=box.right - x - 272)
        y += 22
        ui.text(surf, "HEURISTIC", (x, y), 10, S.MUTED, bold=True)
        ui.text(surf, csp.heuristic or "-", (x + 70, y - 2), 13, S.PURPLE, bold=True, max_width=box.w - 94)
        y += 20
        ui.text(surf, "STATUS", (x, y), 10, S.MUTED, bold=True)
        scol = S.MUTED if csp.status_ok is None else (S.GREEN if csp.status_ok else S.RED)
        ui.text(surf, csp.status, (x + 70, y - 2), 13, scol, bold=True, max_width=box.w - 94)
        y += 22
        done = len(csp.assignment)
        ui.progress_bar(surf, (x, y + 2, 96, 8), csp.progress, S.RED if csp.failed else S.GREEN)
        ui.text(surf, f"{done}/{len(csp.variables)} assigned   backtracks {csp.backtracks}   checks {csp.checks}",
                (x + 106, y - 2), 12, S.MUTED, max_width=box.right - x - 116)
        y += 20
        table_h = min(140, 26 * len(csp.variables))
        draw_domains(surf, (x + 2, y, box.w - 28, table_h), csp, t)
        y += table_h + 4
        draw_log(surf, (box.x + 8, y, box.w - 16, box.bottom - y - 8), csp.log)

        # ---- B. Search brain --------------------------------------------------
        box = pygame.Rect(r.x + 10, box.bottom + 8, r.w - 20, r.bottom - box.bottom - 18)
        acol = S.ALGO_COLOR[algorithm]
        self._section(surf, box, "SEARCH BRAIN", f"{algorithm} NAVIGATION", acol, active_search)
        x, y = box.x + 12, box.y + 34
        ui.text(surf, "LEG", (x, y), 10, S.MUTED, bold=True)
        ui.text(surf, leg_text or "-", (x + 32, y - 2), 13, S.WHITE, bold=True, max_width=150)
        ui.text(surf, "NODE", (x + 196, y), 10, S.MUTED, bold=True)
        node = cell_str(search.current) if search is not None and search.current is not None else "-"
        ui.text(surf, node, (x + 236, y - 3), 15, acol, bold=True, mono=True)
        y += 22
        tw = (box.w - 24 - 3 * 6) / 4
        v = search.current_values if search is not None else {}
        if algorithm == "A*":
            tiles = [("g(n) COST", v.get("g", "-"), S.WHITE), ("h(n) HEUR.", v.get("h", "-"), S.PURPLE),
                     ("f(n) = g+h", v.get("f", "-"), S.CYAN),
                     ("OPEN/CLOSED", f"{search.frontier_size}/{len(search.explored)}" if search else "-", S.ORANGE)]
        else:
            tiles = [("DEPTH", v.get("depth", "-"), S.WHITE),
                     ("QUEUE", search.frontier_size if search else "-", S.ORANGE),
                     ("VISITED", (len(search.explored) + len(search.frontier)) if search else "-", S.BLUE),
                     ("EXPANDED", search.nodes_expanded if search else "-", S.CYAN)]
        for i, (lab, value, col) in enumerate(tiles):
            stat_tile(surf, (x + i * (tw + 6), y, tw, 48), lab, value, col)
        y += 54
        draw_log(surf, (box.x + 8, y, box.w - 16, box.bottom - y - 8), nav_log)

    def _section(self, surf, box, title, subtitle, color, active):
        ui.rrect(surf, S.BG2, box, 10)
        ui.rrect(surf, color if active else S.BORDER, box, 10, 2 if active else 1)
        pygame.draw.circle(surf, color if active else S.BORDER, (box.x + 16, box.y + 17), 4)
        rr = ui.text(surf, title, (box.x + 28, box.y + 9), 13, color if active else S.WHITE, bold=True)
        ui.text(surf, subtitle, (rr.right + 8, box.y + 11), 11, S.MUTED, bold=True)
        if active:
            ui.text(surf, "ACTIVE", (box.right - 12, box.y + 11), 10, color, bold=True, anchor="topright")
