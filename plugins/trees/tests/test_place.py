"""The crown placer on synthetic canopies (needs NumPy and SciPy: skipped where they're missing, e.g. the ingest image)."""
import json
import math
import os
import sys
import unittest

try:
    import numpy as np
    from scipy import ndimage  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))


def dome(shape, cy, cx, H, R, a=0.77, n=1.64):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.hypot(yy - cy, xx - cx) / R
    return np.where(d <= 1, H * (1 - a * np.minimum(d, 1) ** n), 0.0)


@unittest.skipIf(np is None, "NumPy/SciPy not installed")
class PlacerTest(unittest.TestCase):
    def model(self):
        from place import Model
        shapes = {"broadleaf": [(0.77, 1.64), (0.45, 1.64)], "narrow": [(0.95, 2.09), (0.7, 2.09)]}
        return Model({"broadleaf": (0.75, 0.98), "narrow": (0.58, 0.88)}, shapes, 0.22, ["broadleaf", "narrow"])

    def run_placer(self, s, **kw):
        from place import Placer
        pl = Placer(s.astype(np.float32), np.ones(s.shape, bool), self.model(), **kw)
        pl.run_greedy()
        pl.repair(sweeps=2)
        return pl

    def test_one_lone_tree_is_one_tree(self):
        m = self.model()
        R = m.radius_cells(15, "broadleaf")
        s = dome((120, 120), 60, 60, 15, R)
        pl = self.run_placer(s, theta=0.2, lam=20)
        self.assertEqual(pl.count(), 1)
        t = pl.alive()[0]
        self.assertLess(math.hypot(t["y"] - 60, t["x"] - 60), 2.5)
        self.assertAlmostEqual(t["H"], 15, delta=1.0)

    def test_two_separate_trees_are_two(self):
        m = self.model()
        R = m.radius_cells(12, "broadleaf")
        s = np.maximum(dome((120, 200), 60, 50, 12, R), dome((120, 200), 60, 150, 14, m.radius_cells(14, "broadleaf")))
        self.assertEqual(self.run_placer(s, theta=0.2, lam=20).count(), 2)

    def test_two_touching_trees_with_a_dip_are_two(self):
        m = self.model()
        R = m.radius_cells(16, "broadleaf")
        s = np.maximum(dome((140, 200), 70, 70, 16, R), dome((140, 200), 70, 70 + 1.6 * R, 16, R))
        self.assertEqual(self.run_placer(s, theta=0.2, lam=20).count(), 2)

    def test_fixed_trees_survive_repair(self):
        from place import Placer
        m = self.model()
        R = m.radius_cells(15, "broadleaf")
        s = dome((120, 120), 60, 60, 15, R).astype(np.float32)
        pl = Placer(s, np.ones(s.shape, bool), m, theta=0.2, lam=20)
        # a catalogue says there are two trees, the second one 4 cells off: both stay
        for x in (60, 64):
            t = {"y": 60.0, "x": float(x), "H": 15.0, "R": R, "type": "broadleaf", "a": 0.77, "n": 1.64, "fixed": True}
            pl.add(t)
        pl.repair(sweeps=2)
        self.assertEqual(sum(1 for t in pl.alive() if t.get("fixed")), 2)

    def test_overlap_share(self):
        from place import overlap_share
        a = {"y": 0, "x": 0, "R": 10}
        self.assertEqual(overlap_share(a, {"y": 0, "x": 25, "R": 10}), 0)
        self.assertAlmostEqual(overlap_share(a, {"y": 0, "x": 0, "R": 5}), 1.0)
        self.assertTrue(0 < overlap_share(a, {"y": 0, "x": 15, "R": 10}) < 0.5)


@unittest.skipIf(np is None, "NumPy/SciPy not installed")
class ModelFilesTest(unittest.TestCase):
    def test_model_files_have_what_the_build_reads(self):
        model = os.path.join(os.path.dirname(HERE), "model")
        cm = json.load(open(os.path.join(model, "crown_model.json")))
        for k in ("valley broadleaf + small", "valley conifer", "mountain conifer", "mountain broadleaf"):
            self.assertIn("a", cm["width"][k]); self.assertIn("sd_log", cm["width"][k])
        for k in ("broadleaf", "narrow"):
            self.assertIn("n", cm["shape"][k])
        utd = json.load(open(os.path.join(model, "utd_boise.json")))
        self.assertIn("BDL", utd["by_type"]); self.assertIn("CEL", utd["by_type"])

    def test_one_model_everywhere_with_three_types(self):
        # owner, Oct 8: no classification by place; every tree tries broadleaf, conifer and narrow
        import build
        model = os.path.join(os.path.dirname(HERE), "model")
        m = build.model_for(json.load(open(os.path.join(model, "crown_model.json"))))
        self.assertEqual(m.types, ["broadleaf", "conifer", "narrow"])
        for t in m.types:
            self.assertIn(t, m.widths); self.assertIn(t, m.shapes)
        self.assertFalse(hasattr(build, "MOUNTAIN"))

    def test_a_pointed_crown_comes_out_conifer(self):
        # a lone tree 15 m tall with a mountain conifer's narrow, pointed crown is placed as a conifer
        import build
        from place import Placer
        cm = json.load(open(os.path.join(os.path.dirname(HERE), "model", "crown_model.json")))
        m = build.model_for(cm)
        R = m.radius_cells(15.0, "conifer")
        s = dome((80, 80), 40, 40, 15.0, R, a=0.952, n=2.089)
        pl = Placer(s, np.ones(s.shape, bool), m, theta=0.2, lam=20.0)
        pl.run_greedy()
        types = [t["type"] for t in pl.alive()]
        self.assertEqual(len(types), 1)
        self.assertIn(types[0], ("conifer", "narrow"))
