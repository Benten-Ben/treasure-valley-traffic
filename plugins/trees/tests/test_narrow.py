"""The narrow rule (docs/19 §19.3) on synthetic crowns. Needs NumPy, SciPy, rasterio and pyproj: run it in the worker
image, where a skip counts as a failure."""
import json
import math
import os
import sys
import tempfile
import unittest

try:
    import numpy as np
    import rasterio  # noqa: F401
    from scipy import ndimage  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))


def cone(shape, cy, cx, H, R_m):
    """A crown that falls in a straight line from its top: m metres out it has fallen m / R_m of its height."""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.hypot(yy - cy, xx - cx) * 0.5
    return np.clip(H * (1 - d / R_m), 0, None)


def dome(shape, cy, cx, H, R_m, a=0.774, n=1.643):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.hypot(yy - cy, xx - cx) * 0.5 / R_m
    return np.where(d <= 1, H * (1 - a * np.minimum(d, 1) ** n), 0.0)


def model():
    import build
    with open(os.path.join(os.path.dirname(HERE), "model", "crown_model.json")) as f:
        return build.model_for(json.load(f))


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class ProfileTest(unittest.TestCase):
    def test_a_cone_falls_by_distance_over_radius(self):
        import build
        h = cone((80, 80), 40, 40, 12.0, 5.0)
        p = build.crown_profile(h, 40, 40, 2)
        self.assertAlmostEqual(p["top_m"], 12.0, places=2)
        for m in (1, 2, 3):
            self.assertAlmostEqual(p[f"drop_{m}m"], m / 5.0, delta=0.05)
        self.assertLess(p["rough"], 0.05)

    def test_the_top_is_the_highest_cell_within_reach(self):
        import build
        h = cone((80, 80), 40, 44, 12.0, 5.0)
        self.assertAlmostEqual(build.crown_profile(h, 40, 40, 5)["top_m"], 12.0, places=2)   # 4 cells off, found
        self.assertLess(build.crown_profile(h, 40, 40, 2)["top_m"], 12.0)                     # out of reach

    def test_no_profile_off_the_grid(self):
        import build
        h = cone((80, 80), 3, 40, 12.0, 5.0)
        self.assertIsNone(build.crown_profile(h, 3, 40, 2))            # the 3 m ring runs off the top edge
        self.assertIsNone(build.crown_profile(h, -5, 40, 2))
        self.assertFalse(build.narrow_rule(None, 12.0, model()))


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class NarrowRuleTest(unittest.TestCase):
    def setUp(self):
        self.model = model()

    def p(self, h, y=40, x=40):
        import build
        return build.crown_profile(h, y, x, 2)

    def narrow(self, p, H=None):
        # H: the tree's height (the smoothed surface's); by default the top's, a tree whose top is its own
        import build
        return build.narrow_rule(p, p["top_m"] if H is None and p else H, self.model)

    def test_a_crown_that_falls_fast_is_narrow(self):
        import build
        p = self.p(cone((80, 80), 40, 40, 14.0, 5.0))              # falls 60% within 3 m
        self.assertTrue(self.narrow(p), p)

    def test_a_broad_dome_is_not(self):
        import build
        p = self.p(dome((80, 80), 40, 40, 15.0, 6.0))              # a lone broadleaf crown: falls about 25% within 3 m
        self.assertLess(p["drop_3m"], 0.45)
        self.assertFalse(self.narrow(p))

    def test_a_crown_that_ends_within_3_m_is_too_small_to_tell(self):
        import build
        p = self.p(dome((80, 80), 40, 40, 9.0, 2.5))               # the ground 3 m out in every direction
        self.assertGreaterEqual(p["drop_3m"], 0.95)
        self.assertFalse(self.narrow(p))

    def test_an_uneven_top_is_not(self):
        import build
        h = cone((80, 80), 40, 40, 14.0, 5.0)
        yy, xx = np.mgrid[0:80, 0:80]
        h[(xx > 40) & (np.abs(yy - 40) <= 2)] *= 0.4               # one side of the top broken away
        p = self.p(h)
        self.assertGreaterEqual(p["rough"], 0.2)
        self.assertFalse(self.narrow(p))

    def test_a_short_crown_is_too_small_to_tell(self):
        # a 6 m top: a typical broadleaf crown that tall ends before 3 m, so what lies 3 m out isn't the crown
        p = self.p(cone((80, 80), 40, 40, 6.0, 5.0))
        self.assertTrue(0.45 <= p["drop_3m"] < 0.95 and p["rough"] < 0.2, p)
        self.assertFalse(self.narrow(p))

    def test_the_floor_is_on_the_top_not_the_height(self):
        # the width curves were fitted on the lone trees' tops; the tree's height, from the smoothed surface, is lower
        import build
        top = build.narrow_min_top(self.model)
        p = self.p(cone((80, 80), 40, 40, top + 0.3, 5.0))
        self.assertTrue(self.narrow(p, H=top - 1.0), p)                  # a top over the floor, a height under it
        p = self.p(cone((80, 80), 40, 40, top - 0.3, 5.0))
        self.assertFalse(self.narrow(p, H=top - 1.0), p)                  # a top under the floor

    def test_a_top_well_above_the_tree_isnt_its_own(self):
        # a profile whose top stands 2 m or more above the tree's height is a neighbour's crown or a roof
        import build
        p = self.p(cone((80, 80), 40, 40, 14.0, 5.0))
        self.assertTrue(self.narrow(p, H=14.0 - build.NARROW_OWN_TOP_M + 0.01))
        self.assertFalse(self.narrow(p, H=14.0 - build.NARROW_OWN_TOP_M))
        self.assertFalse(self.narrow(p, H=6.0))

    def test_the_cue_starts_where_a_broadleaf_crown_reaches_3_m(self):
        import build
        top = build.narrow_min_top(self.model)
        self.assertAlmostEqual(top, 8.3, delta=0.1)                 # valley broadleaf width 0.75 x H^0.981 = 6 m
        self.assertAlmostEqual(self.model.radius_cells(top, "broadleaf") * 0.5, build.NARROW_REACH_M, places=6)

    def test_the_rule_matches_its_constants(self):
        import build
        lo, hi = build.NARROW_DROP_3M
        ok = {"top_m": build.narrow_min_top(self.model), "drop_3m": lo, "rough": 0.0}
        self.assertTrue(self.narrow(ok))
        self.assertTrue(self.narrow(ok, H=ok["top_m"] - build.NARROW_OWN_TOP_M + 0.001))
        self.assertFalse(self.narrow(ok, H=ok["top_m"] - build.NARROW_OWN_TOP_M))
        self.assertFalse(self.narrow(dict(ok, top_m=ok["top_m"] - 0.01)))
        self.assertFalse(self.narrow(dict(ok, drop_3m=lo - 0.01)))
        self.assertFalse(self.narrow(dict(ok, drop_3m=hi)))
        self.assertFalse(self.narrow(dict(ok, rough=build.NARROW_ROUGH_MAX)))


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class TypePlacedTest(unittest.TestCase):
    def setUp(self):
        import build
        self.model = model()
        self.keep = build.KEEP_WIDTH_CONIFER

    def tearDown(self):
        import build
        build.KEEP_WIDTH_CONIFER = self.keep

    def tree(self, H, R_m, width_curve, a=0.952, n=2.089):
        return {"y": 40.0, "x": 40.0, "H": H, "R": R_m / 0.5, "type": width_curve, "a": a, "n": n}

    def typical(self, H, curve):
        return self.model.radius_cells(H, curve) * 0.5

    def test_the_narrow_curve_doesnt_make_a_tree_narrow(self):
        # a broad dome fitted with the narrow curve stays broadleaf; the fit keeps the curve and the profile
        import build
        R = self.typical(15.0, "narrow")
        typ, fit = build.type_placed(dome((80, 80), 40, 40, 15.0, 6.0), self.tree(15.0, R, "narrow"), self.model)
        self.assertEqual(typ, "broadleaf")
        self.assertEqual(fit["width_curve"], "narrow")
        self.assertIn("drop_3m", fit["profile"])

    def test_the_width_is_compared_with_the_curve_that_sized_it(self):
        # a crown of the narrow curve's typical width is typical, whatever type the narrow rule gives it
        import build
        R = self.typical(15.0, "narrow")
        for h in (dome((80, 80), 40, 40, 15.0, 6.0), cone((80, 80), 40, 40, 15.0, 5.0)):
            typ, fit = build.type_placed(h, self.tree(15.0, R, "narrow"), self.model)
            self.assertAlmostEqual(fit["width_vs_typical_sd"], 0.0, delta=0.01)
        _, fit = build.type_placed(dome((80, 80), 40, 40, 15.0, 6.0), self.tree(15.0, 2 * R, "narrow"), self.model)
        self.assertAlmostEqual(fit["width_vs_typical_sd"], math.log(2) / self.model.sd, delta=0.01)

    def test_a_fast_falling_crown_is_narrow_whatever_its_curve(self):
        import build
        for curve in ("broadleaf", "conifer", "narrow"):
            typ, fit = build.type_placed(cone((80, 80), 40, 40, 14.0, 5.0), self.tree(14.0, 5.0, curve, 0.774, 1.643),
                                         self.model)
            self.assertEqual(typ, "narrow", curve)
            self.assertEqual(fit["width_curve"], curve)
            self.assertEqual(fit["crowded"], curve != "broadleaf")      # a lone broadleaf top, crowded for the others

    def test_the_conifer_curves_call_stands_until_the_owner_decides(self):
        # pending (docs/DECISIONS.md): a tree the narrow rule doesn't call narrow keeps the conifer curve's call
        import build
        cases = [(dome((80, 80), 40, 40, 15.0, 6.0), 15.0), (dome((80, 80), 40, 40, 9.0, 2.5), 9.0),
                 (cone((80, 80), 40, 40, 6.0, 5.0), 6.0)]
        for keep, want in ((True, "conifer"), (False, "broadleaf")):
            build.KEEP_WIDTH_CONIFER = keep
            for h, H in cases:
                typ, _ = build.type_placed(h, self.tree(H, 2.5, "conifer"), self.model)
                self.assertEqual(typ, want, (keep, H))

    def test_placed_type_takes_the_stored_fit(self):
        # placed_type works from what the fit stores (profile, height, curve), so a build can be retyped without placing
        import build
        p = {"top_m": 10.0, "drop_1m": 0.2, "drop_2m": 0.4, "drop_3m": 0.6, "rough": 0.05}
        self.assertEqual(build.placed_type(p, 9.2, "broadleaf", self.model), "narrow")
        self.assertEqual(build.placed_type(p, 7.9, "broadleaf", self.model), "broadleaf")    # top not its own
        self.assertEqual(build.placed_type(p, 7.9, "conifer", self.model), "conifer")
        self.assertEqual(build.placed_type(None, 9.2, "narrow", self.model), "broadleaf")


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class BuildTest(unittest.TestCase):
    def test_a_build_types_its_trees_by_the_rule(self):
        # two crowns 30 m apart on flat ground: one that falls fast from its top, one broad dome
        import build
        from rasterio.transform import from_origin
        shape = (160, 240)
        hgt = np.maximum(cone(shape, 80, 60, 14.0, 5.0), dome(shape, 80, 180, 15.0, 7.0)).astype(np.float32)
        ground = np.full(shape, 800.0, np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=1, dtype="float32", crs="EPSG:32611",
                        transform=from_origin(560000.0, 4830000.0, 0.5, 0.5), nodata=-9999.0)
            for name, arr in (("dsm.tif", ground + hgt), ("dtm.tif", ground)):
                with rasterio.open(os.path.join(tmp, name), "w", **prof) as ds:
                    ds.write(arr, 1)
            out = os.path.join(tmp, "out")
            build.main(["--area", "t", "--dsm", os.path.join(tmp, "dsm.tif"), "--dtm", os.path.join(tmp, "dtm.tif"),
                        "--lidar", "synthetic", "--no-mask", "--out", out])
            with open(os.path.join(out, "trees.geojson")) as f:
                fc = json.load(f)
            with open(os.path.join(out, "build.json")) as f:
                bj = json.load(f)
        trees = [f["properties"] for f in fc["features"]]
        self.assertTrue(trees)
        self.assertEqual({t["kind"] for t in trees}, {"placed"})
        # the tallest tree on each crown: the cone's is narrow, the dome's broadleaf
        x_of = lambda t: (t["id"].split("-")[1])                     # noqa: E731  ids are area-easting-northing
        cone_trees = [t for t in trees if abs(int(x_of(t)) - 560030) <= 3]
        dome_trees = [t for t in trees if abs(int(x_of(t)) - 560090) <= 4]
        self.assertTrue(cone_trees and dome_trees, [t["id"] for t in trees])
        self.assertEqual(max(cone_trees, key=lambda t: t["height_m"])["type"], "narrow")
        self.assertEqual(max(dome_trees, key=lambda t: t["height_m"])["type"], "broadleaf")
        m = model()
        for t in trees:
            self.assertIn(t["fit"]["width_curve"], ("broadleaf", "conifer", "narrow"))
            fit = t["fit"]
            self.assertEqual(t["type"], build.placed_type(fit["profile"], t["height_m"], fit["width_curve"], m))
        self.assertEqual(bj["params"]["narrow_rule"], {"drop_3m": list(build.NARROW_DROP_3M),
                                                       "rough_max": build.NARROW_ROUGH_MAX,
                                                       "min_top_m": round(build.narrow_min_top(m), 2),
                                                       "own_top_m": build.NARROW_OWN_TOP_M})
        self.assertEqual(bj["params"]["conifer_from_width_curve"], build.KEEP_WIDTH_CONIFER)
        # without --spring there is no spring cue: no Sentinel-2 source, and no tree's fit has one
        self.assertIsNone(bj["params"]["spring"])
        self.assertIsNone(bj["counts"]["spring"])
        self.assertEqual(bj["params"]["sources"], [{"source": "trees/usgs_3dep_lidar", "credit": build.LIDAR_CREDIT,
                                                    "version": "synthetic"}])
        self.assertTrue(all(t["fit"]["spring"] is None for t in trees))
        self.assertEqual(sum(bj["counts"]["types"].values()), len(trees))


if __name__ == "__main__":
    unittest.main()
