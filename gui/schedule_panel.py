"""CSP scheduling visualiser: timeline, schedule table and task inspector."""
import math

import pygame

from config import settings as S
from core.csp_scheduler import slot_to_int
from gui import ui

STATUS = {"completed": ("COMPLETED", S.GREEN), "current": ("CURRENT", S.CYAN),
          "pending": ("PENDING", S.ORANGE), "scheduling": ("SCHEDULING", S.PURPLE),
          "unscheduled": ("UNSCHEDULED", S.RED)}


class SchedulePanel:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.rows = []            # [(pygame.Rect, label)] of the last draw, for clicks
        self.selected = None      # task label shown in the inspector

    def handle(self, event):
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        if self.selected is not None:
            self.selected = None
            return True
        for rect, label in self.rows:
            if rect.collidepoint(event.pos):
                self.selected = label
                return True
        return False

    @staticmethod
    def ordered(plan, assignment):
        """Tasks ordered by assigned slot; unassigned tasks keep label order at the end."""
        known = sorted(assignment.items(), key=lambda kv: slot_to_int(kv[1]))
        rest = [(v, None) for v in plan.variables if v not in assignment]
        return known + rest

    def draw(self, surf, t, plan, assignment, solved, status_of, mouse, home_done=False):
        r = self.rect
        y = ui.panel(surf, r, "CLEANING SCHEDULE", S.PURPLE)
        ui.text(surf, "CSP result" if solved else "CSP solving...", (r.right - 16, r.y + 13), 12,
                S.GREEN if solved else S.PURPLE, bold=True, anchor="topright")
        tasks = self.ordered(plan, assignment)
        n = len(tasks)

        # ---- timeline: C > D.. > C -------------------------------------------
        stops = [("C", "home")] + [(lbl, status_of(lbl)) for lbl, _ in tasks] + [("C", "home")]
        x0, x1 = r.x + 30, r.right - 30
        ty = y + 14
        step = (x1 - x0) / (len(stops) - 1)
        for i, (lbl, st) in enumerate(stops):
            cx = x0 + i * step
            if i:
                reached = st in ("completed", "current") or (st == "home" and home_done)
                pygame.draw.line(surf, S.GREEN if reached else S.BORDER, (cx - step + 13, ty), (cx - 13, ty), 3)
            col = S.BLUE if st == "home" else STATUS[st][1]
            if st == "home" and (i == 0 or home_done):
                st = "completed"
            rad = 12
            if st == "current":
                ui.glow(surf, (cx, ty), 26, S.CYAN, int(70 + 60 * math.sin(t * 6)))
            pygame.draw.circle(surf, col if st in ("completed", "current") else S.DARK, (int(cx), ty), rad)
            pygame.draw.circle(surf, col, (int(cx), ty), rad, 2)
            ui.text(surf, lbl, (cx, ty), 10 if len(lbl) > 2 else 11,
                    S.DARK if st in ("completed", "current") else col, bold=True, anchor="center")
        y = ty + 24

        # ---- table -------------------------------------------------------------
        ui.text(surf, "TIME SLOT", (r.x + 18, y), 10, S.MUTED, bold=True)
        ui.text(surf, "TASK", (r.x + 116, y), 10, S.MUTED, bold=True)
        ui.text(surf, "CELL", (r.x + 176, y), 10, S.MUTED, bold=True)
        ui.text(surf, "STATUS", (r.right - 18, y), 10, S.MUTED, bold=True, anchor="topright")
        y += 16
        foot = 44
        row_h = max(16, min(26, (r.bottom - foot - y) // max(1, n)))
        self.rows = []
        for lbl, slot in tasks:
            st = status_of(lbl)
            name, col = STATUS[st]
            row = pygame.Rect(r.x + 10, y, r.w - 20, row_h - 2)
            hot = row.collidepoint(mouse)
            if st == "current":
                ui.rrect_alpha(surf, S.CYAN, row, 6, 46)
                ui.rrect(surf, S.CYAN, row, 6, 1)
            elif hot:
                ui.rrect(surf, S.PANEL_HI, row, 6)
            cy = row.centery
            fs = 14 if row_h >= 22 else 12
            ui.text(surf, slot or "?", (r.x + 22, cy), fs, col, bold=True, anchor="midleft")
            ui.arrow(surf, S.MUTED, (r.x + 62, cy), (r.x + 98, cy), 2, 5)
            ui.text(surf, lbl, (r.x + 116, cy), fs, S.WHITE, bold=True, anchor="midleft")
            pos = plan.grid.dirty_locations[lbl]
            ui.text(surf, f"({pos[0]},{pos[1]})", (r.x + 176, cy), fs - 1, S.MUTED, anchor="midleft", mono=True)
            ui.text(surf, name, (r.right - 22, cy), 11, col, bold=True, anchor="midright")
            self.rows.append((row, lbl))
            y += row_h

        # ---- constraints footer -------------------------------------------------
        c = plan.constraints
        fy = r.bottom - foot + 4
        pygame.draw.line(surf, S.BORDER, (r.x + 14, fy - 4), (r.right - 14, fy - 4))
        prec = "  ".join(f"{a}<{b}" for a, b in c["precedence"]) or "none"
        late = "  ".join(f"{a}<={b}" for a, b in c["latest_slot"]) or "none"
        ui.text(surf, "PRECEDENCE", (r.x + 18, fy + 1), 10, S.ORANGE, bold=True)
        ui.text(surf, prec, (r.x + 104, fy), 12, S.WHITE, mono=True, max_width=r.w - 122)
        ui.text(surf, "LATEST SLOT", (r.x + 18, fy + 19), 10, S.PURPLE, bold=True)
        ui.text(surf, late, (r.x + 104, fy + 18), 12, S.WHITE, mono=True, max_width=r.w - 122)

    def draw_inspector(self, surf, plan, assignment, status_of):
        """Task detail card (drawn on top of everything while a task is selected)."""
        lbl = self.selected
        if lbl is None or lbl not in plan.grid.dirty_locations:
            self.selected = None
            return
        ui.rrect_alpha(surf, S.DARK, surf.get_rect(), 0, 150)
        box = pygame.Rect(0, 0, 520, 390)
        box.center = (S.WIDTH // 2, S.HEIGHT // 2)
        ui.panel(surf, box, f"TASK {lbl}", S.PURPLE, title_size=18)
        c = plan.constraints
        pos = plan.grid.dirty_locations[lbl]
        name, col = STATUS[status_of(lbl)]
        ui.badge(surf, name, (box.right - 20, box.y + 14), col, 12, anchor="topright", filled=True)
        rows = [("Task label", lbl), ("Grid coordinates", f"row {pos[0]}, column {pos[1]}"),
                ("Assigned time slot", assignment.get(lbl, "not assigned yet"))]
        y = box.y + 62
        for key, val in rows:
            ui.text(surf, key, (box.x + 26, y), 15, S.MUTED)
            ui.text(surf, val, (box.right - 26, y), 16, S.WHITE, bold=True, anchor="topright")
            y += 32
        y += 6
        ui.text(surf, "PRECEDENCE REQUIREMENTS", (box.x + 26, y), 12, S.ORANGE, bold=True)
        y += 24
        lines = [f"{lbl} must be cleaned before {b}" for a, b in c["precedence"] if a == lbl]
        lines += [f"{lbl} must be cleaned after {a}" for a, b in c["precedence"] if b == lbl]
        for line in lines or ["No precedence constraints involve this task."]:
            ui.text(surf, line, (box.x + 26, y), 15, S.WHITE)
            y += 24
        y += 8
        ui.text(surf, "LATEST-SLOT REQUIREMENT", (box.x + 26, y), 12, S.PURPLE, bold=True)
        y += 24
        late = [f"{lbl} must be cleaned no later than {s}" for a, s in c["latest_slot"] if a == lbl]
        for line in late or ["No deadline for this task."]:
            ui.text(surf, line, (box.x + 26, y), 15, S.WHITE)
            y += 24
        ui.text(surf, "Click anywhere to close", (box.centerx, box.bottom - 24), 12, S.MUTED, anchor="center")
