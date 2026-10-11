"""Pooling the photo statistics to ground types, the fallbacks and the checks (plugins/soils/build/pool.py), on
synthetic sums. Needs NumPy and SciPy: skipped where they're missing; on the VM, `worker-test -C <checkout>
plugins.soils.tests.test_pool`, where a skip fails.
"""

import os
import sys
import unittest

try:
    import numpy as np
    import scipy  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)

FLIGHTS = ["2025-05-25", "2025-06-18"]


def soil(gid, series, texcl, landform, albedo, misc=None):
    return {"gid": gid, "series": series, "texcl": texcl, "landform": landform, "albedo_dry": albedo, "misc": misc}


TYPES = {
    "m1:silt-loam": soil(1, "M1", "Silt loam", "terraces", 0.15),
    "m2:silt-loam": soil(2, "M2", "Silt loam", "terraces", 0.20),
    "m3:silt-loam": soil(3, "M3", "Silt loam", "fan remnants", 0.25),
    "m4:loam": soil(4, "M4", "Loam", "terraces", 0.30),
    "m5:loam": soil(5, "M5", "Loam", "hillslopes", 0.35),
    "m1:loam": soil(6, "M1", "Loam", "hillslopes", 0.15),           # few pixels: borrows its series
    "elijah:silt-loam": soil(7, "Elijah", "Silt loam", "terraces", 0.25),   # none: texture class and landform
    "xyz:sand": soil(8, "Xyz", "Sand", "dunes", 0.40),              # no peers but an albedo
    "nope:clay": soil(9, "Nope", "Clay", "playas", None),            # nothing to borrow
    "rock-outcrop": soil(10, "Rock outcrop", None, None, None, "rock"),
    "notcom": soil(11, "NOTCOM", None, None, None, "nodata"),
    "dune-land": soil(12, "Dune land", None, None, None, "other"),     # one big polygon: measured all the same
}
L_OF = {"m1:silt-loam": 0.60, "m2:silt-loam": 0.65, "m3:silt-loam": 0.70, "m4:loam": 0.75, "m5:loam": 0.80,
        "m1:loam": 0.62, "dune-land": 0.85}


def synthetic(outlier=True):
    """Map units (one per type), their sums per (map unit, flight) and per polygon. m2:silt-loam has 20 polygons, one
    of them far from the rest (when outlier); m1:silt-loam reads 5 dE lighter on its second flight day."""
    import photo
    rng = np.random.default_rng(11)
    mapunits = [{"mukey": f"mu{i}", "type": t} for i, t in enumerate(TYPES)]
    nf = len(FLIGHTS)
    acc = photo.Accumulator(len(mapunits) * nf)
    polys = []
    for i, t in enumerate(TYPES):
        if t not in L_OF:
            continue
        n, count = {"m1:loam": (1000, 4), "m2:silt-loam": (60000, 20), "dune-land": (25000, 1)}.get(t, (30000, 4))
        for p in range(count):
            m = n // count
            L = rng.normal(L_OF[t], 0.03, m).astype(np.float32)
            a = rng.normal(0.005, 0.004, m).astype(np.float32)
            b = rng.normal(0.035, 0.006, m).astype(np.float32)
            f = 0 if p < count // 2 else 1
            if t == "m1:silt-loam" and f == 1:
                L = L + np.float32(0.05)
            if outlier and t == "m2:silt-loam" and p == count - 1:
                L, b = L + np.float32(0.15), b + np.float32(0.04)
            acc.add(np.full(m, i * nf + f), L, a, b)
            for k in range(5):
                acc.add_texture(k, np.full(10, i * nf + f), np.full(10, 0.01 * (k + 1), np.float32),
                                np.full(10, 0.002, np.float32))
            polys.append((i, L, a, b))
    pacc = photo.Accumulator(len(polys), hist_dtype=np.int32)
    for j, (_, L, a, b) in enumerate(polys):
        pacc.add(np.full(len(L), j), L, a, b)
    return mapunits, acc, {"gid": np.arange(100, 100 + len(polys)), "mu": np.array([q[0] for q in polys]),
                           "acc": pacc}


@unittest.skipIf(np is None, "NumPy and SciPy not installed")
class PoolTest(unittest.TestCase):
    def setUp(self):
        import photo
        import pool
        self.P, self.PL = photo, pool
        self.mapunits, acc, self.polys = synthetic()
        self.rows, self.report = pool.pool(self.mapunits, TYPES, FLIGHTS, acc, self.polys)
        self.by = {(r["level"], r["key"], r["flight"]): r for r in self.rows}

    def test_map_units_get_a_row_per_flight_and_pooled(self):
        r = self.by[("mapunit", "mu0", None)]
        self.assertEqual((r["n_px"], r["n_polygons"], r["fallback"], r["photo"], r["mask"]),
                         (30000, 4, None, "naip2025", "photo-v1"))
        self.assertEqual(self.by[("mapunit", "mu0", "2025-05-25")]["n_px"], 15000)
        self.assertIsNone(self.by[("mapunit", "mu0", "2025-05-25")]["n_polygons"])
        self.assertNotIn(("mapunit", "mu6", None), self.by)                 # elijah: no pixels, no row
        self.assertEqual(len(r["lab_cov"]), 6)
        self.assertEqual(len(r["oct_l"]), 5)
        self.assertAlmostEqual(r["oct_l"][2], 0.03 ** 2, places=8)

    def test_measured_types(self):
        for t, L in L_OF.items():
            if t in ("m1:loam", "dune-land"):
                continue
            r = self.by[("ground_type", t, None)]
            self.assertIsNone(r["fallback"])
            self.assertEqual(r["n_polygons"], 20 if t == "m2:silt-loam" else 4)
            want = L + (0.025 if t == "m1:silt-loam" else 0)
            self.assertAlmostEqual(r["lab_med"][0], want, delta=0.02)
        self.assertIn(("ground_type", "m1:silt-loam", "2025-06-18"), self.by)
        self.assertEqual(self.report["counts"], {"measured": 6, "series": 1, "texture": 1, "albedo": 1, "none": 3})
        dune = self.by[("ground_type", "dune-land", None)]
        self.assertEqual((dune["fallback"], dune["n_polygons"]), (None, 1))

    def test_fallbacks(self):
        series = self.by[("ground_type", "m1:loam", None)]
        self.assertEqual((series["fallback"], series["n_px"]), ("series", 1000))
        self.assertGreater(series["lab_med"][0], 0.60)                     # mostly m1:silt-loam's pixels
        self.assertNotIn(("ground_type", "m1:loam", "2025-05-25"), self.by)  # no per-flight rows for a fallback
        tex = self.by[("ground_type", "elijah:silt-loam", None)]
        self.assertEqual((tex["fallback"], tex["n_px"], tex["n_polygons"]), ("texture", 0, 0))
        self.assertLess(tex["lab_med"][0], 0.69)                           # m1 and m2 (terraces), not m3
        alb = self.by[("ground_type", "xyz:sand", None)]
        self.assertEqual(alb["fallback"], "albedo")
        fit = self.report["albedo_fit"]
        self.assertEqual(fit["n"], 5)
        self.assertTrue(fit["sets_l"])
        self.assertAlmostEqual(alb["lab_med"][0], fit["intercept"] + fit["slope"] * 0.40, places=4)
        self.assertGreater(alb["lab_med"][0], 0.8)
        self.assertLess(alb["l_p10"], alb["lab_med"][0])
        for t in ("nope:clay", "rock-outcrop", "notcom"):
            self.assertNotIn(("ground_type", t, None), self.by)
            self.assertEqual(self.report["types"][t]["status"], "none")
        self.assertEqual(self.report["types"]["xyz:sand"]["gid"], 8)
        self.assertRegex(self.report["types"]["m1:loam"]["from"], "series M1")

    def test_checks(self):
        fd = self.report["flight_days"]
        self.assertEqual(fd["types_on_two_or_more"], 1)        # only m2 has MIN_PX on each day (30,000 a day)
        self.assertFalse(fd["gains_needed"])
        self.assertFalse(fd["gains_applied"])
        self.assertFalse(fd["over_rule"])
        self.assertGreater(self.report["variance_explained"], 0.5)
        self.assertAlmostEqual(self.report["spearman_l_albedo"], 1.0, places=6)
        out = self.report["polygon_outliers"]
        self.assertEqual([o["type"] for o in out["polygons"]], ["m2:silt-loam"])
        self.assertGreater(out["polygons"][0]["mahalanobis"], 3)
        self.assertEqual(out["polygons"][0]["polygon"], 100 + 4 + 19)

    def test_flight_days_measured_when_each_day_has_enough(self):
        old = self.PL.MIN_PX
        try:
            self.PL.MIN_PX = 5000
            _, acc, polys = synthetic(outlier=False)
            _, report = self.PL.pool(self.mapunits, TYPES, FLIGHTS, acc, polys)
        finally:
            self.PL.MIN_PX = old
        fd = report["flight_days"]
        self.assertEqual(fd["types_on_two_or_more"], 5)                     # dune land: one polygon, one day
        worst = {t["type"]: t["max_de"] for t in fd["types"]}
        self.assertAlmostEqual(worst["m1:silt-loam"], 5.0, delta=0.6)
        self.assertLess(worst["m3:silt-loam"], 1.0)
        self.assertFalse(fd["gains_needed"])                                 # the median type is under 3
        off = fd["pair_offsets"]["2025-05-25/2025-06-18"]
        self.assertEqual(off["types"], 5)
        self.assertLess(abs(off["dL"]), 1.0)                                 # four of five types don't move

    def test_with_gains_the_rule_reports_what_is_left(self):
        old, old_de = self.PL.MIN_PX, self.PL.FLIGHT_DE
        try:
            self.PL.MIN_PX, self.PL.FLIGHT_DE = 5000, 0.0                    # so the median type is over the rule
            _, acc, polys = synthetic(outlier=False)
            _, before = self.PL.pool(self.mapunits, TYPES, FLIGHTS, acc, polys)
            _, after = self.PL.pool(self.mapunits, TYPES, FLIGHTS, acc, polys, gains_applied=True)
        finally:
            self.PL.MIN_PX, self.PL.FLIGHT_DE = old, old_de
        self.assertEqual((before["flight_days"]["over_rule"], before["flight_days"]["gains_needed"]), (True, True))
        self.assertEqual((after["flight_days"]["over_rule"], after["flight_days"]["gains_needed"]), (True, False))
        self.assertTrue(after["flight_days"]["gains_applied"])

    def test_a_weak_albedo_fit_doesnt_set_l(self):
        # Scrambled albedos: the measured types' L no longer follows them (r under ALBEDO_MIN_R), so xyz:sand takes
        # its texture-class peers' colour as it is (it has none: all measured soils), labelled texture.
        scrambled = dict(TYPES)
        for t, a in (("m1:silt-loam", 0.35), ("m2:silt-loam", 0.15), ("m3:silt-loam", 0.30), ("m4:loam", 0.20),
                     ("m5:loam", 0.25)):
            scrambled[t] = dict(TYPES[t], albedo_dry=a)
        _, acc, polys = synthetic()
        rows, report = self.PL.pool(self.mapunits, scrambled, FLIGHTS, acc, polys)
        fit = report["albedo_fit"]
        self.assertLess(fit["r"], self.PL.ALBEDO_MIN_R)
        self.assertFalse(fit["sets_l"])
        by = {(r["level"], r["key"], r["flight"]): r for r in rows}
        sand = by[("ground_type", "xyz:sand", None)]
        self.assertEqual(sand["fallback"], "texture")
        self.assertEqual(report["types"]["xyz:sand"]["status"], "texture")
        self.assertRegex(report["types"]["xyz:sand"]["from"], "too weak to set L")
        self.assertLess(sand["lab_med"][0], 0.8)                             # the soils' pooled L, not the line's
        self.assertEqual(report["counts"]["albedo"], 0)


class SpearmanTest(unittest.TestCase):
    @unittest.skipIf(np is None, "NumPy and SciPy not installed")
    def test_ties_and_short_input(self):
        import pool
        self.assertAlmostEqual(pool.spearman([1, 2, 3, 4], [10, 20, 20, 40]), 0.9486832980505138)
        self.assertIsNone(pool.spearman([1, 2], [3, 4]))
        self.assertIsNone(pool.spearman([1, 1, 1], [1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
