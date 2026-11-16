"""End-to-end GUI tests, run headless through the real event loop.

    python -m unittest discover -s tests
"""
import io
import os
import random
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from harness import ROOT, click, find, key, make_app, press, run, run_until

import pygame

from config import settings as S
from core.integration import plan_mission


def P(name):
    return os.path.join(ROOT, name)


class GuiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls._env_dir = S.CUSTOM_ENV_DIR
        S.CUSTOM_ENV_DIR = os.path.join(cls.tmp, "environments")
        cls.app = make_app()

    @classmethod
    def tearDownClass(cls):
        S.CUSTOM_ENV_DIR = cls._env_dir
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.app.errors.clear()
        self.app.state.mode = "AUTOMATIC"
        self.app.state.speed = "VERY FAST"
        self.app.state.algorithm = "A*"
        self.goto("menu")

    def tearDown(self):
        self.assertEqual(self.app.errors, [], "a screen raised an exception")

    def goto(self, name, **kw):
        self.app.go(name, **kw)
        return self.wait_screen(name, 5)

    def wait_screen(self, name, timeout=20):
        app = self.app
        ok = run_until(app, lambda: app._pending is None and app._fade == 0 and app.current.name == name, timeout)
        self.assertTrue(ok, f"never reached screen {name!r} (on {self.app.current.name!r})")
        return self.app.current

    # --------------------------------------------------------------- helpers --
    def start_mission(self, index, algorithm="A*", mode="AUTOMATIC"):
        """Menu -> mission selection -> configuration -> simulation, by clicking."""
        app = self.app
        press(app, find(app.current, "START MISSION"))
        sel = self.wait_screen("missions")
        press(app, sel.select_btns[index])
        cfg = self.wait_screen("config")
        click(app, cfg.algo.cell(cfg.algo.options.index(algorithm)).center)
        click(app, cfg.mode.cell(cfg.mode.options.index(mode)).center)
        click(app, cfg.speed.cell(3).center)
        self.assertEqual((app.state.algorithm, app.state.mode, app.state.speed), (algorithm, mode, "VERY FAST"))
        with redirect_stdout(io.StringIO()):
            press(app, cfg.start)
            return self.wait_screen("simulation")

    def watch(self, sim):
        """Invariant checked on every frame: the robot is on the grid, never
        inside an obstacle, and never moves diagonally."""
        g = sim.plan.grid
        r = sim.robot
        self.assertTrue(abs(r.row - round(r.row)) < 1e-6 or abs(r.col - round(r.col)) < 1e-6, "diagonal motion")
        for cell in {(int(r.row), int(r.col)), (int(-(-r.row // 1)), int(-(-r.col // 1)))}:
            self.assertTrue(g.is_valid_cell(*cell), f"robot entered blocked cell {cell}")

    def finish(self, sim, timeout=240):
        self.assertTrue(run_until(self.app, lambda: sim.finished is not None, timeout, each=lambda: self.watch(sim)))


class Navigation(GuiTestCase):
    def test_every_menu_button_works(self):
        app = self.app
        targets = {"START MISSION": "missions", "CUSTOM ENVIRONMENT": "editor", "ALGORITHM RACE": "race",
                   "AI ANALYTICS": "analytics", "HOW TO PLAY": "info", "ABOUT PROJECT": "info"}
        for label, screen in targets.items():
            self.goto("menu")
            press(app, find(app.current, label))
            self.wait_screen(screen)
            key(app, pygame.K_ESCAPE)
            self.wait_screen("menu")
        press(app, find(app.current, "EXIT"))
        self.assertFalse(app.running)
        app.running = True

    def test_mute_button_and_resize_mapping(self):
        app = self.app
        press(app, app.mute_btn)
        self.assertTrue(app.audio.muted)
        press(app, app.mute_btn)
        self.assertFalse(app.audio.muted)
        # Test independent music mute
        press(app, app.music_btn)
        self.assertTrue(app.audio.music_muted)
        self.assertFalse(app.audio.muted)  # SFX remains unmuted!
        press(app, app.music_btn)
        self.assertFalse(app.audio.music_muted)
        self.assertEqual(app.to_logical((800, 450)), (800, 450))

    def test_back_buttons_navigation(self):
        app = self.app
        # 1. Menu -> Analytics -> Back Button -> Menu
        self.goto("menu")
        press(app, find(app.current, "AI ANALYTICS"))
        an = self.wait_screen("analytics")
        self.assertEqual(an.b_back.label, "< BACK")
        press(app, an.b_back)
        self.wait_screen("menu")

        # 2. Menu -> Algorithm Race -> Back Button -> Menu
        self.goto("menu")
        press(app, find(app.current, "ALGORITHM RACE"))
        race = self.wait_screen("race")
        self.assertEqual(race.b_back.label, "< BACK")
        press(app, race.b_back)
        self.wait_screen("menu")

        # 3. Analytics -> Algorithm Race -> Back Button -> Analytics
        self.goto("analytics")
        press(app, find(app.current, "ALGORITHM RACE"))
        race = self.wait_screen("race")
        self.assertEqual(race.b_back.label, "< ANALYTICS")
        press(app, race.b_back)
        self.wait_screen("analytics")

    def test_random_input_never_crashes(self):
        app = self.app
        rng = random.Random(323)
        keys = [pygame.K_SPACE, pygame.K_n, pygame.K_r, pygame.K_1, pygame.K_4, pygame.K_RETURN, pygame.K_a,
                pygame.K_BACKSPACE, pygame.K_RIGHT]
        for name in ("menu", "missions", "config", "editor", "race", "analytics", "info"):
            self.goto(name)
            for _ in range(140):
                if rng.random() < 0.7:
                    click(app, (rng.randrange(S.WIDTH), rng.randrange(S.HEIGHT)), rng.choice((1, 1, 3)))
                else:
                    key(app, rng.choice(keys), "a")
                app.running = True
                app.modal = None if rng.random() < 0.3 else app.modal
            run(app, 0.4)
        with redirect_stdout(io.StringIO()):
            app.state.plan = plan_mission(P("Environment.txt"), P("Schedule.txt"), "BFS", repeats=2)
        self.goto("simulation", plan=app.state.plan)
        for _ in range(400):
            if rng.random() < 0.5:
                click(app, (rng.randrange(S.WIDTH), rng.randrange(S.HEIGHT)))
            else:
                key(app, rng.choice(keys), "a")
            if app.current.name != "simulation":
                self.goto("simulation", plan=app.state.plan)


class Missions(GuiTestCase):
    def check_success(self, index, algorithm):
        app = self.app
        sim = self.start_mission(index, algorithm)
        plan = sim.plan
        self.assertEqual(plan.algorithm, algorithm)
        self.finish(sim)
        self.assertEqual(sim.finished, "success")
        self.assertEqual(sim.journey, plan.complete_path)          # robot drove the planned journey
        self.assertEqual(sim.moves, plan.total_cost)
        self.assertEqual(sim.nav_cost, plan.total_cost)
        self.assertEqual(sim.nodes_done, plan.total_nodes())
        self.assertEqual(sim.cleaned, [task for task, _ in plan.ordered_schedule])
        self.assertEqual(sim.robot.cell, plan.grid.charging_station)
        self.assertEqual(sim.csp.assignment, plan.assignment)
        res_screen = self.wait_screen("results")
        res = app.state.result
        self.assertTrue(res["success"] and res["returned"])
        self.assertEqual(len(res["cleaned"]), res["total_dirty"])
        # results buttons
        press(app, find(res_screen, "VIEW FULL JOURNEY"))
        run(app, 1.0)
        self.assertTrue(res_screen.journey_mode)
        press(app, res_screen.close_btn)
        press(app, find(res_screen, "VIEW AI ANALYTICS"))
        an = self.wait_screen("analytics")
        self.assertEqual(an.source, "LAST RUN")
        self.assertEqual(len(an.rows), len(plan.legs))
        # Test back button returns directly to results
        press(app, an.b_back)
        self.wait_screen("results")
        press(app, find(res_screen, "REPLAY MISSION"))
        sim = self.wait_screen("simulation")
        self.assertIsNone(sim.finished)
        self.assertEqual(sim.moves, 0)
        press(app, sim.b_menu)
        self.wait_screen("menu")

    def test_mission_01_astar(self):
        self.check_success(0, "A*")

    def test_mission_01_bfs(self):
        self.check_success(0, "BFS")

    def test_mission_02_astar(self):
        self.check_success(1, "A*")

    def test_mission_02_bfs(self):
        self.check_success(1, "BFS")

    def test_mission_03_infeasible_schedule(self):
        app = self.app
        sim = self.start_mission(2)
        self.finish(sim)
        self.assertEqual(sim.finished, "failed")
        self.assertTrue(sim.csp.failed)
        self.assertEqual((sim.moves, sim.cleaned), (0, []))
        self.wait_screen("results")
        res = app.state.result
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "infeasible")
        self.assertFalse(find(app.current, "VIEW FULL JOURNEY").enabled)
        press(app, find(app.current, "MAIN MENU"))
        self.wait_screen("menu")

    def test_unreachable_destination(self):
        app = self.app
        st = app.state
        st.env_path, st.sched_path = P("Environment_Error.txt"), P("Schedule_Sample.txt")
        cfg = self.goto("config")
        with redirect_stdout(io.StringIO()):
            press(app, cfg.start)
            sim = self.wait_screen("simulation")
        self.finish(sim)
        self.assertEqual(sim.finished, "failed")
        self.assertEqual(sim.cleaned, ["D1"])                       # cleaned what it could reach
        self.assertTrue(sim.search.failed)
        self.wait_screen("results")
        res = app.state.result
        self.assertFalse(res["success"])
        self.assertFalse(res["returned"])
        self.assertEqual(res["status"], "unreachable")
        self.assertIn("D2", res["reason"])

    def test_step_by_step_and_controls(self):
        app = self.app
        sim = self.start_mission(0, "A*", "STEP-BY-STEP")
        self.assertFalse(sim.running)
        run(app, 1.0)
        self.assertEqual(sim.csp.i, 0, "step mode must wait for the player")
        for expected in range(1, 6):                                 # one CSP event per step
            press(app, sim.b_step)
            self.assertEqual(sim.csp.i, expected)
        while sim.phase in ("csp", "csp_done"):
            press(app, sim.b_step)
        self.assertEqual(sim.phase, "search")
        n = sim.search.nodes_expanded
        press(app, sim.b_step)
        self.assertEqual(sim.search.nodes_expanded, n + 1)           # one node expansion per step
        while sim.phase == "search":
            press(app, sim.b_step)
        self.assertEqual(sim.phase, "move")
        run(app, 0.5)
        self.assertEqual(sim.moves, 0)
        press(app, sim.b_step)
        run(app, 0.5)
        self.assertEqual(sim.moves, 1)                               # exactly one cell per step
        # resume -> runs; pause -> stops
        press(app, sim.b_resume)
        run(app, 0.6)
        self.assertGreater(sim.moves, 1)
        press(app, sim.b_pause)
        run(app, 0.3)
        frozen = (sim.moves, sim.phase, len(sim.nav_log))
        run(app, 1.0)
        self.assertEqual(frozen, (sim.moves, sim.phase, len(sim.nav_log)))
        key(app, pygame.K_SPACE)
        self.assertTrue(sim.running)
        # speed keys and restart
        key(app, pygame.K_1)
        self.assertEqual(app.state.speed, "SLOW")
        key(app, pygame.K_4)
        press(app, sim.b_restart)
        self.assertEqual((sim.moves, sim.cleaned, sim.phase, sim.csp.i), (0, [], "csp", 0))
        self.assertFalse(sim.running)
        press(app, sim.b_play)
        self.finish(sim)
        self.assertEqual(sim.finished, "success")
        self.assertEqual(app.current.name, "simulation")             # step mode waits on the final screen
        press(app, sim.b_results)
        self.wait_screen("results")

    def test_task_inspector(self):
        app = self.app
        sim = self.start_mission(0)
        run_until(app, lambda: sim.csp.solved, 30)
        press(app, sim.b_pause)
        run(app, 0.1)
        rect, label = sim.schedule.rows[0]
        click(app, rect.center)
        self.assertEqual(sim.schedule.selected, label)
        run(app, 0.2)
        click(app, (800, 450))
        self.assertIsNone(sim.schedule.selected)


class BadInput(GuiTestCase):
    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_missing_and_malformed_files_are_reported(self):
        app = self.app
        st = app.state
        cases = [
            (P("no_such_file.txt"), P("Schedule.txt"), "not found"),
            (self.write("bad_dims.txt", "x,8\n0\n\n1\n(1,1)\n(0,0)\n"), P("Schedule.txt"), "expected 6 lines"),
            (self.write("overlap.txt", "8,8\n1\n(1,1)\n1\n(1,1)\n(0,0)\n"), P("Schedule.txt"), "Overlapping"),
            (self.write("two_c.txt", "8,8\n1\n(1,1)\n1\n(2,2)\n(0,0),(0,1)\n"), P("Schedule.txt"), "charging stations"),
            (self.write("no_c.txt", "8,8\n1\n(1,1)\n1\n(2,2)\n-\n"), P("Schedule.txt"), "Missing charging"),
            (P("Environment_Sample.txt"), self.write("bad_label.txt", "4\n1\n(D1,D9)\n0\n"), "invalid task label"),
            (P("Environment_Sample.txt"), self.write("garbage.txt", "hello\n"), "whole number"),
        ]
        for env, sched, needle in cases:
            st.env_path, st.sched_path = env, sched
            cfg = self.goto("config")
            self.assertIn(needle, cfg.error, f"{os.path.basename(env)} / {os.path.basename(sched)}")
            self.assertFalse(cfg.start.enabled)
            run(app, 0.2)
            key(app, pygame.K_RETURN)                 # must not start anything
            run(app, 0.3)
            self.assertEqual(app.current.name, "config")
            self.goto("menu")

    def test_file_deleted_after_validation(self):
        app = self.app
        st = app.state
        with open(P("Environment_Sample.txt"), encoding="utf-8") as f:
            env = self.write("vanish.txt", f.read())
        st.env_path, st.sched_path = env, P("Schedule_Sample.txt")
        cfg = self.goto("config")
        self.assertTrue(cfg.start.enabled)
        os.remove(env)
        press(app, cfg.start)
        run(app, 1.5)
        self.assertEqual(app.current.name, "config")
        self.assertIn("not found", cfg.error)

    def test_insufficient_time_slots(self):
        app = self.app
        st = app.state
        st.env_path = P("Environment_Sample.txt")
        st.sched_path = self.write("few_slots.txt", "2\n0\n0\n")
        cfg = self.goto("config")
        press(app, cfg.start)
        sim = self.wait_screen("simulation")
        self.finish(sim)
        self.assertEqual(sim.finished, "failed")
        self.assertIn("Insufficient time slots", sim.fail_reason)

    def test_custom_file_picker(self):
        app = self.app
        sel = self.goto("missions")
        sel.pick("env")
        self.assertIsNotNone(app.modal)
        run(app, 0.2)
        names = [e[0] for e in app.modal.entries]
        self.assertIn("Environment_Sample.txt", names)
        self.assertNotIn("requirements.txt", names)
        i = names.index("Environment_Sample.txt")
        while not (app.modal.scroll <= i < app.modal.scroll + app.modal.VISIBLE):
            app.frame(1 / 60, [pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1)])
        click(app, app.modal.row_rect(i).center)
        self.assertIsNone(app.modal)
        self.assertEqual(sel.custom_env, P("Environment_Sample.txt"))
        # Environment_Sample has 4 tasks but Schedule.txt mentions D5 -> clear error, button disabled
        self.assertIn("invalid task label 'D5'", sel.infos[3].error)
        self.assertFalse(sel.select_btns[3].enabled)
        sel.custom_sched = P("Schedule_Sample.txt")
        sel.reload()
        press(app, sel.select_btns[3])
        self.wait_screen("config")
        self.assertEqual(app.state.env_path, P("Environment_Sample.txt"))


class Editor(GuiTestCase):
    def test_build_validate_save_load_play(self):
        app = self.app
        ed = self.goto("editor")
        press(app, find(ed, "CLEAR GRID"))
        self.assertFalse(ed.validate(quiet=True))
        self.assertIsNone(ed.save())                                  # invalid layouts are not saved
        run(app, 0.1)
        v = ed.view
        press(app, ed.tool_btns["obstacle"])
        for c in [(1, 1), (1, 2), (1, 3), (2, 3), (3, 3), (5, 5)]:
            click(app, v.center(c))
        press(app, ed.tool_btns["dirty"])
        for c in [(0, 7), (7, 7), (7, 0), (4, 4)]:
            click(app, v.center(c))
        press(app, ed.tool_btns["charger"])
        click(app, v.center((0, 0)))
        click(app, v.center((0, 1)))                                  # moving the charger keeps exactly one
        self.assertEqual(ed.layout.charging_station, (0, 1))
        click(app, v.center((0, 7)))                                  # charger replaces a dirty cell: no overlap
        self.assertEqual(len(ed.layout.dirty), 3)
        self.assertFalse(ed.validate(quiet=True))
        click(app, v.center((0, 0)))
        press(app, ed.tool_btns["dirty"])
        click(app, v.center((0, 7)))
        self.assertEqual(ed.layout.dirty_locations["D4"], (0, 7))
        click(app, v.center((6, 6)), button=3)                        # right-click erases
        press(app, find(ed, "VALIDATE ENVIRONMENT"))
        self.assertTrue(ed.report_ok, ed.report)

        # an enclosed dirty location must be rejected
        press(app, ed.tool_btns["obstacle"])
        for c in [(6, 7), (7, 6)]:
            click(app, v.center(c))
        self.assertFalse(ed.validate(quiet=True))
        self.assertTrue(any("unreachable" in p for p in ed.report))
        press(app, ed.tool_btns["erase"])
        click(app, v.center((6, 7)))
        self.assertTrue(ed.validate(quiet=True))

        # resize up and down, save, clear, reset, load
        press(app, [w for w in ed.widgets.items if getattr(w, "label", "") == "+"][0])
        self.assertEqual(ed.layout.rows, 9)
        press(app, [w for w in ed.widgets.items if getattr(w, "label", "") == "-"][0])
        press(app, [w for w in ed.widgets.items if getattr(w, "label", "") == "-"][0])
        self.assertEqual(ed.layout.rows, 8)                           # never below the minimum
        click(app, ed.filename.rect.center)
        for _ in range(40):
            key(app, pygame.K_BACKSPACE)
        for ch in "my_room":
            key(app, ord(ch), ch)
        key(app, pygame.K_RETURN)
        press(app, find(ed, "SAVE ENVIRONMENT"))
        saved = os.path.join(S.CUSTOM_ENV_DIR, "my_room.txt")
        self.assertTrue(os.path.isfile(saved))
        with open(saved) as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "8,8")
        self.assertEqual(len(lines), 6)
        before = ed.layout.snapshot()
        press(app, find(ed, "CLEAR GRID"))
        self.assertEqual(len(ed.layout.obstacles), 0)
        press(app, find(ed, "RESET GRID"))
        self.assertEqual(ed.layout.snapshot(), before)
        press(app, find(ed, "CLEAR GRID"))
        press(app, find(ed, "LOAD ENVIRONMENT"))
        app.modal.on_pick(saved)
        app.modal = None
        self.assertEqual(ed.layout.snapshot(), before)

        # play: goes to configuration with a generated, loadable schedule, and the mission succeeds
        press(app, find(ed, "PLAY THIS ENVIRONMENT"))
        cfg = self.wait_screen("config")
        self.assertEqual(app.state.env_path, saved)
        self.assertEqual(cfg.error, "")
        press(app, cfg.start)
        sim = self.wait_screen("simulation")
        self.finish(sim)
        self.assertEqual(sim.finished, "success")


class RaceAndAnalytics(GuiTestCase):
    def test_race_is_fair_and_reports_real_numbers(self):
        app = self.app
        app.state.env_path = P("Environment.txt")
        race = self.goto("race")
        race.set_env(P("Environment.txt"))
        b, a = race.racers["BFS"], race.racers["A*"]
        self.assertEqual((b.run.start, b.run.goal), (a.run.start, a.run.goal))     # identical problem
        click(app, race.seg_speed.cell(3).center)
        press(app, race.b_start)
        run(app, 0.25)
        # one expansion per algorithm per tick: counts stay equal until one finishes
        if not a.playback.done and not b.playback.done:
            self.assertEqual(a.playback.nodes_expanded, b.playback.nodes_expanded)
        press(app, race.b_pause)
        snap = (a.playback.i, b.playback.i)
        run(app, 0.5)
        self.assertEqual(snap, (a.playback.i, b.playback.i))
        press(app, race.b_step)
        self.assertGreater(b.playback.i, snap[1])
        press(app, race.b_resume)
        self.assertTrue(run_until(app, lambda: race.finished, 120))
        for r in (a, b):
            self.assertEqual(r.playback.nodes_expanded, r.run.nodes_expanded)
            self.assertEqual(r.moves, r.run.cost)
            self.assertEqual(r.robot.cell, r.run.goal)
        text = " ".join(race.summary)
        self.assertIn(str(b.run.nodes_expanded), text)
        self.assertIn(str(a.run.nodes_expanded), text)
        run(app, 0.3)
        # change the problem with the mouse and the buttons
        view = race.views["BFS"]
        click(app, view.center((9, 9)))
        self.assertEqual(race.goal, (9, 9))
        click(app, view.center((5, 0)), button=3)
        self.assertEqual(race.start, (5, 0))
        click(app, view.center((1, 2)))                               # obstacle: refused
        self.assertEqual(race.goal, (9, 9))
        press(app, find(race, "NEXT TARGET"))
        press(app, find(race, "SWAP START / GOAL"))
        press(app, find(race, "NEXT ENVIRONMENT"))
        press(app, find(race, "RESTART"))
        self.assertFalse(race.started)

    def test_exploration_modes(self):
        app = self.app
        race = self.goto("race")
        for mode, algo in (("EXPLORE BFS", "BFS"), ("EXPLORE A*", "A*")):
            click(app, race.seg_mode.cell(race.seg_mode.options.index(mode)).center)
            self.assertEqual(race.mode, mode)
            self.assertEqual(len(race.active), 1)
            press(app, race.b_step)
            self.assertEqual(race.active[0].playback.nodes_expanded, 1)
            press(app, race.b_start)
            self.assertTrue(run_until(app, lambda: race.finished, 120))
            self.assertEqual(race.active[0].run.algorithm, algo)
            self.assertTrue(race.log)
        click(app, race.seg_mode.cell(0).center)

    def test_race_on_unreachable_goal(self):
        app = self.app
        race = self.goto("race")
        race.set_env(P("Environment_Error.txt"))
        race.goal = (3, 7)
        race.compute()
        race.speed_name = "VERY FAST"
        press(app, race.b_start)
        self.assertTrue(run_until(app, lambda: race.finished, 200))
        self.assertTrue(all(r.playback.failed for r in race.active))
        self.assertIn("unreachable", " ".join(race.summary))
        run(app, 0.3)

    def test_analytics_sources_and_export(self):
        app = self.app
        an = self.goto("analytics")
        with redirect_stdout(io.StringIO()):
            for i, name in enumerate(("MISSION 01", "MISSION 02", "MISSION 03")):
                click(app, an.seg.cell(i).center)
                self.assertEqual(an.source, name)
                self.assertTrue(an.rows)
                for _, b, a in an.rows:
                    if b.found:
                        self.assertEqual(b.cost, a.cost)
                run(app, 1.2)
        app.state.plan = None
        click(app, an.seg.cell(3).center)                             # no last run yet: refused politely
        self.assertEqual(an.source, "MISSION 03")
        out = os.path.join(ROOT, "exports", "analytics_mission_03.png")
        if os.path.exists(out):
            os.remove(out)
        press(app, find(an, "EXPORT CHARTS (PNG)"))
        self.assertTrue(os.path.isfile(out))
        os.remove(out)


if __name__ == "__main__":
    unittest.main()
