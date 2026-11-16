"""Core tests: the extracted modules must behave exactly like the original
notebook, tracing must not change results, and every scenario must give the
expected outcome.  Run with:  python -m unittest discover -s tests
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import environment as env_mod, graph_search as gs, csp_scheduler as csp, integration as integ

SCENARIOS = [("Environment_Sample.txt", "Schedule_Sample.txt"),
             ("Environment.txt", "Schedule.txt"),
             ("Environment_Error.txt", "Schedule_Error.txt"),
             ("Environment_Error.txt", "Schedule_Sample.txt"),
             ("Environment_Sample.txt", "Schedule_Error.txt")]


def P(name):
    return os.path.join(ROOT, name)


def notebook_namespace():
    """Execute the notebook's algorithm cells (parsers, search, CSP,
    integration) and return their namespace for comparison."""
    with open(P("optisweep_simulation.ipynb"), encoding="utf-8") as f:
        nb = json.load(f)
    ns = {}
    for cell in nb["cells"]:
        src = "".join(cell["source"])
        if cell["cell_type"] != "code":
            continue
        if any(tag in src for tag in ("SECTION 1:", "SECTION 2:", "SECTION 3:", "SECTION 4:")):
            src = "\n".join(l for l in src.splitlines() if "matplotlib" not in l and "numpy" not in l)
            exec(src, ns)
    return ns


class NotebookParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nb = notebook_namespace()

    def test_search_matches_notebook(self):
        for env_file, _ in SCENARIOS[:3]:
            g_new = env_mod.load_environment(P(env_file))
            g_old = self.nb["load_environment"](P(env_file))
            pts = [g_new.charging_station] + list(g_new.dirty_locations.values())
            for a in pts:
                for b in pts:
                    for algo in ("BFS", "A*"):
                        self.assertEqual(gs.search(g_new, a, b, algo),
                                         self.nb["search"](g_old, a, b, algo))

    def test_csp_and_integration_match_notebook(self):
        for env_file, sched_file in SCENARIOS:
            g_new = env_mod.load_environment(P(env_file))
            g_old = self.nb["load_environment"](P(env_file))
            new = env_mod.load_schedule_constraints(P(sched_file), g_new.dirty_locations.keys())
            old = self.nb["load_schedule_constraints"](P(sched_file), g_old.dirty_locations.keys())
            self.assertEqual(new, old)
            a_new = csp.backtracking_search(*new)
            a_old = self.nb["backtracking_search"](*old)
            self.assertEqual(a_new, a_old)
            if a_new is None:
                continue
            for algo in ("BFS", "A*"):
                with redirect_stdout(io.StringIO()):
                    r_new = integ.execute_schedule(g_new, g_new.charging_station, a_new, algo)
                    r_old = self.nb["execute_schedule"](g_old, g_old.charging_station, a_old, algo)
                self.assertEqual(r_new, r_old)


class TracingIsPassive(unittest.TestCase):
    def test_search_trace_does_not_change_results(self):
        for env_file, _ in SCENARIOS[:3]:
            g = env_mod.load_environment(P(env_file))
            pts = [g.charging_station] + list(g.dirty_locations.values())
            for a in pts:
                for b in pts:
                    for algo in ("BFS", "A*"):
                        rec = integ.TraceRecorder()
                        plain = gs.search(g, a, b, algo)
                        traced = gs.search(g, a, b, algo, trace=rec)
                        self.assertEqual(plain, traced)
                        expands = sum(1 for e, _ in rec.events if e == "expand")
                        self.assertEqual(expands, plain[2])

    def test_csp_trace_does_not_change_results(self):
        for env_file, sched_file in SCENARIOS:
            g = env_mod.load_environment(P(env_file))
            v, d, c = env_mod.load_schedule_constraints(P(sched_file), g.dirty_locations.keys())
            rec = integ.TraceRecorder()
            self.assertEqual(csp.backtracking_search(v, d, c),
                             csp.backtracking_search(v, d, c, trace=rec))
            self.assertIn(rec.events[-1][0], ("solution", "failure"))


class Scenarios(unittest.TestCase):
    def plan(self, env_file, sched_file, algo="A*"):
        with redirect_stdout(io.StringIO()):
            return integ.plan_mission(P(env_file), P(sched_file), algo, repeats=2)

    def check_success(self, plan):
        g, c = plan.grid, plan.constraints
        self.assertTrue(plan.success)
        self.assertEqual(plan.status, "ok")
        a = plan.assignment
        self.assertEqual(len(set(a.values())), len(a))                       # exclusivity
        for before, after in c["precedence"]:
            self.assertLess(csp.slot_to_int(a[before]), csp.slot_to_int(a[after]))
        for task, latest in c["latest_slot"]:
            self.assertLessEqual(csp.slot_to_int(a[task]), csp.slot_to_int(latest))
        path = plan.complete_path
        self.assertEqual(path[0], g.charging_station)
        self.assertEqual(path[-1], g.charging_station)
        self.assertEqual(plan.total_cost, len(path) - 1)
        for p, q in zip(path, path[1:]):                                     # 4-directional, no walls
            self.assertEqual(abs(p[0] - q[0]) + abs(p[1] - q[1]), 1)
            self.assertTrue(g.is_valid_cell(*q))
        for pos in g.dirty_locations.values():
            self.assertIn(pos, path)
        self.assertEqual(len(plan.legs), len(g.dirty_locations) + 1)
        for leg in plan.legs:                                                # both optimal
            self.assertEqual(leg.runs["BFS"].cost, leg.runs["A*"].cost)

    def test_sample_and_custom_succeed(self):
        for env_file, sched_file in SCENARIOS[:2]:
            for algo in ("BFS", "A*"):
                self.check_success(self.plan(env_file, sched_file, algo))

    def test_sample_schedule_is_expected(self):
        plan = self.plan(*SCENARIOS[0])
        self.assertEqual(len(plan.ordered_schedule), 4)
        self.assertEqual(plan.total_cost_of("BFS"), plan.total_cost_of("A*"))
        self.assertLessEqual(plan.total_nodes("A*"), plan.total_nodes("BFS"))

    def test_infeasible_schedule(self):
        plan = self.plan(*SCENARIOS[2])
        self.assertFalse(plan.success)
        self.assertEqual(plan.status, "infeasible")
        self.assertIsNone(plan.assignment)
        self.assertEqual(plan.legs, [])

    def test_unreachable_destination(self):
        plan = self.plan(*SCENARIOS[3])
        self.assertFalse(plan.success)
        self.assertEqual(plan.status, "unreachable")
        self.assertEqual(plan.unreachable, ["D2"])
        self.assertFalse(plan.legs[-1].runs["A*"].found)
        self.assertIn("D2", plan.failure_reason)

    def test_comparison_summary_uses_real_numbers(self):
        g = env_mod.load_environment(P("Environment_Sample.txt"))
        runs = integ.compare_algorithms(g, g.charging_station, g.dirty_locations["D3"], repeats=2)
        text = " ".join(integ.comparison_summary(runs["BFS"], runs["A*"]))
        self.assertIn(str(runs["BFS"].nodes_expanded), text)
        self.assertIn(str(runs["A*"].nodes_expanded), text)


class InputErrors(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        f.write(text); f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def env_error(self, text):
        with self.assertRaises(env_mod.InputError) as cm:
            env_mod.load_environment_checked(self.write(text))
        return str(cm.exception)

    def test_environment_errors(self):
        with self.assertRaises(env_mod.InputError):
            env_mod.load_environment_checked(P("does_not_exist.txt"))
        self.assertIn("expected 6 lines", self.env_error("8,8\n1\n(1,1)\n"))
        self.assertIn("whole number", self.env_error("a,8\n1\n(1,1)\n1\n(2,2)\n(0,0)\n"))
        self.assertIn("dimensions", self.env_error("0,8\n1\n(1,1)\n1\n(2,2)\n(0,0)\n"))
        self.assertIn("Overlapping", self.env_error("8,8\n1\n(1,1)\n1\n(1,1)\n(0,0)\n"))
        self.assertIn("outside", self.env_error("8,8\n1\n(9,1)\n1\n(2,2)\n(0,0)\n"))
        self.assertIn("Missing charging", self.env_error("8,8\n1\n(1,1)\n1\n(2,2)\nnone\n"))
        self.assertIn("2 charging", self.env_error("8,8\n1\n(1,1)\n1\n(2,2)\n(0,0), (0,1)\n"))
        self.assertIn("declares 3", self.env_error("8,8\n3\n(1,1)\n1\n(2,2)\n(0,0)\n"))

    def test_schedule_errors(self):
        labels = ["D1", "D2"]
        def err(text):
            with self.assertRaises(env_mod.InputError) as cm:
                env_mod.load_schedule_checked(self.write(text), labels)
            return str(cm.exception)
        self.assertIn("invalid task label 'D9'", err("2\n1\n(D1,D9)\n0\n"))
        self.assertIn("invalid time slot 'T5'", err("2\n0\n1\n(D1,T5)\n"))
        self.assertIn("malformed", err("2\n2\n(D1,D2)\n0\n"))
        self.assertIn("whole number", err("x\n0\n0\n"))
        with self.assertRaises(env_mod.InputError):
            env_mod.load_schedule_checked(P("nope.txt"), labels)

    def test_insufficient_slots_is_infeasible(self):
        sched = self.write("2\n0\n0\n")
        with redirect_stdout(io.StringIO()):
            plan = integ.plan_mission(P("Environment_Sample.txt"), sched, repeats=1)
        self.assertEqual(plan.status, "infeasible")
        self.assertIn("Insufficient time slots", plan.failure_reason)

    def test_layout_validation_and_roundtrip(self):
        g = env_mod.load_environment(P("Environment.txt"))
        obstacles = sorted(g.obstacles)
        dirty = list(g.dirty_locations.values())
        self.assertEqual(env_mod.check_layout(g.rows, g.cols, obstacles, dirty, [g.charging_station]), [])
        path = self.write(env_mod.format_environment(g.rows, g.cols, obstacles, dirty, g.charging_station))
        g2 = env_mod.load_environment_checked(path)
        self.assertEqual((g2.rows, g2.cols, g2.obstacles, g2.dirty_locations, g2.charging_station),
                         (g.rows, g.cols, g.obstacles, g.dirty_locations, g.charging_station))
        ge = env_mod.load_environment(P("Environment_Error.txt"))
        problems = env_mod.check_layout(ge.rows, ge.cols, sorted(ge.obstacles),
                                        list(ge.dirty_locations.values()), [ge.charging_station])
        self.assertTrue(any("unreachable" in p for p in problems))
        self.assertTrue(env_mod.check_layout(6, 6, [], [], []))


if __name__ == "__main__":
    unittest.main()
