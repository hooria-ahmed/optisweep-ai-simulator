"""AI analytics dashboard: BFS vs A* on real mission data."""
import os

import pygame

from config import settings as S
from core.environment import InputError
from core.integration import compare_algorithms, plan_mission
from gui import ui
from gui.app import Screen
from gui.results_screen import fmt_time


def build_rows(plan):
    """[(leg name, BFS run, A* run)] for a plan.  When the mission has no
    navigation legs (infeasible schedule) the charger -> each dirty location
    problems are compared instead, so there is still real data to show."""
    if plan.legs:
        return [(leg.name, leg.runs["BFS"], leg.runs["A*"]) for leg in plan.legs], "mission legs"
    g = plan.grid
    rows = []
    for label, pos in g.dirty_locations.items():
        runs = compare_algorithms(g, g.charging_station, pos)
        rows.append((f"C > {label}", runs["BFS"], runs["A*"]))
    return rows, "charger to each target (no schedule exists)"


def insights(rows):
    """Sentences computed from the measured totals."""
    bn = sum(b.nodes_expanded for _, b, _ in rows)
    an = sum(a.nodes_expanded for _, _, a in rows)
    bt = sum(b.seconds for _, b, _ in rows)
    at = sum(a.seconds for _, _, a in rows)
    solved = [(b, a) for _, b, a in rows if b.found and a.found]
    out = []
    if bn > an:
        out.append(f"Across {len(rows)} problems A* expanded {an} nodes against {bn} for BFS: "
                   f"{100 * (bn - an) / bn:.0f}% fewer.")
    elif bn < an:
        out.append(f"A* expanded {an} nodes against {bn} for BFS on these problems.")
    else:
        out.append(f"Both algorithms expanded {bn} nodes in total.")
    if solved:
        if all(b.cost == a.cost for b, a in solved):
            out.append(f"Path costs are identical on all {len(solved)} solved problems "
                       f"(total {sum(b.cost for b, _ in solved)} moves): both are optimal here.")
        else:
            out.append("Path costs differ on at least one problem.")
    failed = [name for name, b, a in rows if not (b.found and a.found)]
    if failed:
        out.append(f"No path exists for {', '.join(failed)}: both searches exhausted every reachable cell.")
    if bt > 0 and at > 0:
        fast, ratio = ("A*", bt / at) if at < bt else ("BFS", at / bt)
        out.append(f"{fast} was {ratio:.1f}x faster in wall-clock time ({fmt_time(at)} A* vs {fmt_time(bt)} BFS).")
    return out


def export_charts(rows, title, path):
    """Write the three comparison charts to a PNG with Matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = [n for n, _, _ in rows]
    hexc = lambda c: "#%02x%02x%02x" % c
    fig, axes = plt.subplots(1, 3, figsize=(16, 5), facecolor=hexc(S.BG))
    specs = [("Nodes Expanded", lambda r: r.nodes_expanded),
             ("Path Cost (moves)", lambda r: r.cost if r.found else 0),
             ("Execution Time (microseconds)", lambda r: r.seconds * 1e6)]
    xs = range(len(rows))
    for ax, (label, fn) in zip(axes, specs):
        ax.set_facecolor(hexc(S.PANEL))
        ax.bar([x - 0.2 for x in xs], [fn(b) for _, b, _ in rows], 0.4, label="BFS", color=hexc(S.ORANGE))
        ax.bar([x + 0.2 for x in xs], [fn(a) for _, _, a in rows], 0.4, label="A*", color=hexc(S.CYAN))
        ax.set_title(f"BFS vs A* - {label}", color=hexc(S.WHITE), fontweight="bold")
        ax.set_xticks(list(xs))
        ax.set_xticklabels(names, color=hexc(S.MUTED), rotation=20)
        ax.tick_params(colors=hexc(S.MUTED))
        for spine in ax.spines.values():
            spine.set_color(hexc(S.BORDER))
        ax.grid(axis="y", color=hexc(S.BORDER), linewidth=0.6)
        ax.set_axisbelow(True)
        ax.legend(facecolor=hexc(S.BG2), edgecolor=hexc(S.BORDER), labelcolor=hexc(S.WHITE))
    fig.suptitle(f"OptiSweep AI analytics - {title}", color=hexc(S.WHITE), fontweight="bold")
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)


class AnalyticsScreen(Screen):
    def __init__(self, app):
        super().__init__(app)
        self.rows = []
        self.note = ""
        self.title = ""
        self.error = ""
        self.lines = []
        self.t = 0.0
        self.cache = {}                      # source name -> plan
        self.source = "MISSION 01"
        self.back_target = "menu"
        self.widgets = ui.WidgetGroup(app)
        self.seg = self.widgets.add(ui.Segmented((40, 74, 580, 40), ["MISSION 01", "MISSION 02", "MISSION 03", "LAST RUN"],
                                                 self.source, self.set_source, 13))
        self.widgets.add(ui.Button((S.WIDTH - 760, 74, 180, 40), "ALGORITHM RACE", lambda: app.go("race"), size=14))
        self.widgets.add(ui.Button((S.WIDTH - 564, 74, 210, 40), "EXPORT CHARTS (PNG)", self.export, "blue", size=14))
        self.widgets.add(ui.Button((S.WIDTH - 338, 74, 150, 40), "MAIN MENU", lambda: app.go("menu"), size=14))
        self.b_back = self.widgets.add(ui.Button((S.WIDTH - 172, 74, 132, 40), "< BACK", self.on_back, "primary", size=14))

    def enter(self, source=None, back=None, **kwargs):
        if back:
            self.back_target = back
        elif getattr(self.app, "prev_screen", None) in ("results", "race", "menu"):
            self.back_target = self.app.prev_screen
        elif self.app.state.result is not None:
            self.back_target = "results"
        else:
            self.back_target = "menu"
        self.b_back.label = "< RESULTS" if self.back_target == "results" else "< BACK"

        if source == "mission" and self.app.state.plan is not None:
            self.source = "LAST RUN"
        elif self.source == "LAST RUN" and self.app.state.plan is None:
            self.source = "MISSION 01"
        self.seg.value = self.source
        self.load()

    def on_back(self):
        target = self.back_target or "menu"
        if target == "results" and self.app.state.result is None:
            target = "menu"
        self.app.go(target)

    def set_source(self, value):
        if value == "LAST RUN" and self.app.state.plan is None:
            self.app.notify("No mission has been run yet - start one from the main menu.", S.ORANGE)
            self.seg.value = self.source
            return
        self.source = value
        self.load()

    def load(self):
        self.t = 0.0
        self.error = ""
        st = self.app.state
        try:
            if self.source == "LAST RUN":
                plan = st.plan
                self.title = st.mission_title
            else:
                m = S.MISSIONS[int(self.source[-2:]) - 1]
                self.title = f"MISSION {m['id']} - {m['title']}"
                if self.source not in self.cache:
                    self.cache[self.source] = plan_mission(os.path.join(S.ROOT_DIR, m["env"]),
                                                           os.path.join(S.ROOT_DIR, m["sched"]), st.algorithm)
                plan = self.cache[self.source]
            self.rows, self.note = build_rows(plan)
            self.lines = insights(self.rows) if self.rows else []
            if plan.status != "ok":
                self.lines.insert(0, f"Mission status: {plan.failure_reason}")
        except InputError as exc:
            self.rows, self.lines, self.error = [], [], str(exc)

    def export(self):
        if not self.rows:
            self.app.notify("Nothing to export.", S.ORANGE)
            return
        path = os.path.join(S.ROOT_DIR, "exports", "analytics_" + self.source.replace(" ", "_").lower() + ".png")
        try:
            export_charts(self.rows, self.title, path)
            self.app.notify(f"Charts saved to exports/{os.path.basename(path)}", S.GREEN, 5)
        except ImportError:
            self.app.notify("Matplotlib is not installed: pip install matplotlib", S.ORANGE, 5)
        except Exception as exc:
            self.app.notify(f"Could not export charts: {exc}", S.RED, 5)

    def handle(self, event):
        if self.widgets.handle(event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.on_back()

    def update(self, dt):
        self.t += dt
        self.widgets.update(dt)

    # --------------------------------------------------------------- drawing --
    def chart(self, surf, rect, title, getter, fmt, unit=""):
        rect = pygame.Rect(rect)
        y0 = ui.panel(surf, rect, title, S.CYAN)
        for i, (name, col) in enumerate((("BFS", S.ORANGE), ("A*", S.CYAN))):
            x = rect.right - 118 + i * 58
            pygame.draw.rect(surf, col, (x, rect.y + 16, 12, 12), border_radius=3)
            ui.text(surf, name, (x + 17, rect.y + 13), 13, S.WHITE, bold=True)
        plot = pygame.Rect(rect.x + 50, y0 + 18, rect.w - 70, rect.h - (y0 - rect.y) - 62)
        values = [(getter(b), getter(a)) for _, b, a in self.rows]
        top = max([v for pair in values for v in pair if v is not None] or [1]) or 1
        for k in range(5):                                   # horizontal grid lines + axis labels
            gy = plot.bottom - plot.h * k / 4
            pygame.draw.line(surf, S.BORDER, (plot.x, gy), (plot.right, gy))
            ui.text(surf, fmt(top * k / 4), (plot.x - 8, gy), 11, S.MUTED, anchor="midright", mono=True)
        n = max(1, len(values))
        slot = plot.w / n
        bw = max(6, min(34, slot * 0.34))
        grow = ui.ease(min(1.0, self.t / 0.9))
        for i, (bv, av) in enumerate(values):
            cx = plot.x + (i + 0.5) * slot
            for v, col, dx in ((bv, S.ORANGE, -bw / 2 - 2), (av, S.CYAN, bw / 2 + 2)):
                if v is None:
                    ui.text(surf, "none", (cx + dx, plot.bottom - 8), 10, S.RED, anchor="midbottom", bold=True)
                    continue
                h = plot.h * (v / top) * grow
                bar = pygame.Rect(0, 0, int(bw), max(2, int(h)))
                bar.midbottom = (int(cx + dx), plot.bottom)
                pygame.draw.rect(surf, col, bar, border_top_left_radius=4, border_top_right_radius=4)
                if grow >= 1.0 and slot > 56:
                    ui.text(surf, fmt(v), (bar.centerx, bar.y - 3), 10, S.WHITE, anchor="midbottom", mono=True)
            ui.text(surf, self.rows[i][0], (cx, plot.bottom + 8), 11 if n <= 6 else 9, S.MUTED, anchor="midtop",
                    max_width=int(slot) - 2)
        if unit:
            ui.text(surf, unit, (rect.x + 14, rect.bottom - 22), 11, S.MUTED)

    def draw(self, surf):
        app = self.app
        app.draw_background(surf)
        app.header(surf, "AI ANALYTICS", "BFS vs A* - measured on the real algorithm runs")
        self.widgets.draw(surf)
        if self.error or not self.rows:
            ui.text(surf, self.error or "No data available.", (S.WIDTH // 2, 420), 20, S.RED, anchor="center",
                    max_width=1300)
            return
        ui.text(surf, f"{self.title}   -   {self.note}", (40, 124), 14, S.MUTED, max_width=1500)

        w = (S.WIDTH - 80 - 40) // 3
        self.chart(surf, (40, 150, w, 300), "BFS vs A*  -  NODES EXPANDED", lambda r: r.nodes_expanded,
                   lambda v: f"{v:.0f}", "nodes expanded per navigation problem")
        self.chart(surf, (60 + w, 150, w, 300), "BFS vs A*  -  PATH COST", lambda r: r.cost if r.found else None,
                   lambda v: f"{v:.0f}", "moves (unit step cost)")
        self.chart(surf, (80 + 2 * w, 150, w, 300), "BFS vs A*  -  EXECUTION TIME", lambda r: r.seconds * 1e6,
                   lambda v: f"{v:.0f}", "microseconds, mean of repeated runs")

        # ---- comparison table -------------------------------------------------------
        box = pygame.Rect(40, 466, 960, 414)
        y = ui.panel(surf, box, "COMPARISON TABLE", S.ORANGE)
        cols = [("PROBLEM", 20), ("COST", 190), ("", 250), ("NODES", 330), ("", 400), ("TIME", 480), ("", 580),
                ("LENGTH", 690), ("", 750), ("NODE SAVING", 830)]
        sub = ["", "BFS", "A*", "BFS", "A*", "BFS", "A*", "BFS", "A*", "A* vs BFS"]
        for (name, x), s in zip(cols, sub):
            if name:
                ui.text(surf, name, (box.x + x, y), 11, S.MUTED, bold=True)
            if s:
                col = S.ORANGE if s == "BFS" else (S.CYAN if s == "A*" else S.MUTED)
                ui.text(surf, s, (box.x + x, y + 16), 12, col, bold=True)
        y += 38
        n = len(self.rows)
        row_h = max(18, min(34, (box.bottom - y - 50) // (n + 1)))
        fs = 14 if row_h >= 24 else 12

        def draw_row(yy, name, vals, bold=False):
            ui.text(surf, name, (box.x + 20, yy), fs, S.WHITE, bold=True, max_width=160)
            for (_, x), v in zip(cols[1:], vals):
                col = S.WHITE
                if isinstance(v, tuple):
                    v, col = v
                ui.text(surf, v, (box.x + x, yy), fs, col, bold=bold, mono=True)

        def saving(b, a):
            if b.nodes_expanded == 0:
                return ("-", S.MUTED)
            pct = 100 * (b.nodes_expanded - a.nodes_expanded) / b.nodes_expanded
            return (f"{pct:+.0f}%".replace("+", "") if pct >= 0 else f"{pct:.0f}%",
                    S.GREEN if pct > 0 else (S.RED if pct < 0 else S.MUTED))

        cost = lambda r: str(r.cost) if r.found else ("none", S.RED)
        for i, (name, b, a) in enumerate(self.rows):
            if i % 2 == 0:
                ui.rrect(surf, S.BG2, (box.x + 10, y - 4, box.w - 20, row_h - 2), 6)
            draw_row(y, name, [cost(b), cost(a), str(b.nodes_expanded), str(a.nodes_expanded),
                               fmt_time(b.seconds), fmt_time(a.seconds),
                               str(b.path_length) if b.found else "-", str(a.path_length) if a.found else "-",
                               saving(b, a)])
            y += row_h
        pygame.draw.line(surf, S.BORDER, (box.x + 14, y), (box.right - 14, y))
        y += 8
        bs = [b for _, b, _ in self.rows]
        as_ = [a for _, _, a in self.rows]
        tot = lambda runs, f: sum(f(r) for r in runs)

        class _T:                                           # totals presented like a run
            pass
        tb, ta = _T(), _T()
        tb.nodes_expanded, ta.nodes_expanded = tot(bs, lambda r: r.nodes_expanded), tot(as_, lambda r: r.nodes_expanded)
        draw_row(y, "TOTAL", [str(tot(bs, lambda r: r.cost if r.found else 0)), str(tot(as_, lambda r: r.cost if r.found else 0)),
                              str(tb.nodes_expanded), str(ta.nodes_expanded),
                              fmt_time(tot(bs, lambda r: r.seconds)), fmt_time(tot(as_, lambda r: r.seconds)),
                              str(tot(bs, lambda r: r.path_length)), str(tot(as_, lambda r: r.path_length)),
                              saving(tb, ta)], bold=True)

        # ---- explanation -----------------------------------------------------------------
        box = pygame.Rect(1020, 466, 540, 414)
        y = ui.panel(surf, box, "SEARCH BEHAVIOUR", S.GREEN)
        x, w2 = box.x + 20, box.w - 40
        ui.text(surf, "UNINFORMED - BFS", (x, y), 12, S.ORANGE, bold=True)
        y = ui.paragraph(surf, "Knows nothing about where the goal is. Expands nodes in order of depth with a "
                               "FIFO queue, flooding outwards in every direction.", (x, y + 18), 13, w2, S.WHITE, 3) + 6
        ui.text(surf, "INFORMED - A*", (x, y), 12, S.CYAN, bold=True)
        y = ui.paragraph(surf, "Orders its open list by f(n) = g(n) + h(n), using the Manhattan distance to "
                               "prefer nodes that look closer to the goal.", (x, y + 18), 13, w2, S.WHITE, 3) + 6
        f = pygame.Rect(x, y, w2, 52)
        ui.rrect(surf, S.DARK, f, 8)
        ui.rrect(surf, S.CYAN, f, 8, 1)
        ui.text(surf, "MANHATTAN DISTANCE HEURISTIC", (f.x + 12, f.y + 7), 10, S.MUTED, bold=True)
        ui.text(surf, "h(n) = |row_current - row_goal| + |col_current - col_goal|", (f.x + 12, f.y + 26), 13,
                S.CYAN, bold=True, mono=True, max_width=f.w - 20)
        y = f.bottom + 10
        ui.text(surf, "MEASURED ON THIS DATA", (x, y), 12, S.GREEN, bold=True)
        y += 20
        for line in self.lines:
            if y > box.bottom - 30:
                break
            pygame.draw.circle(surf, S.GREEN, (x + 4, y + 8), 3)
            y = ui.paragraph(surf, line, (x + 16, y), 13, w2 - 16, S.WHITE, 3) + 5
