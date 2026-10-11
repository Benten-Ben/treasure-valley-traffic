"""The spring cue (docs/19 §19.3) on synthetic Sentinel-2 rasters: an early-April NDVI with its clear and snow view
counts, and a July NDVI, on the ground's 10 m grid. Needs NumPy, SciPy, rasterio and pyproj: run it in the worker image,
where a skip counts as a failure."""
import json
import math
import os
import sys
import tempfile
import unittest

try:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from scipy import ndimage  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))

# A 400 m square of the ground grid (E 495920, N 4855750 at 10 m): 6,398 columns east and 2,565 rows south of its corner.
X0, Y1, N = 559900.0, 4830100.0, 40
ND = -32768


def cone(shape, cy, cx, H, R_m):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return np.clip(H * (1 - np.hypot(yy - cy, xx - cx) * 0.5 / R_m), 0, None)


def dome(shape, cy, cx, H, R_m, a=0.774, n=1.643):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.hypot(yy - cy, xx - cx) * 0.5 / R_m
    return np.where(d <= 1, H * (1 - a * np.minimum(d, 1) ** n), 0.0)


def write(path, arr, dtype, nodata=None, x0=X0, y1=Y1, res=10.0, crs="EPSG:32611", tags=None):
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype, crs=crs,
                transform=from_origin(x0, y1, res, res), nodata=nodata)
    with rasterio.open(path, "w", **prof) as ds:
        ds.write(arr.astype(dtype), 1)
        if tags:
            ds.update_tags(**tags)


def seasons_dirs(tmp, apr=0.5, jul=0.8, snow=2, clear=2, patch=None, **kw):
    """Two folders like the server's: spring (ndvi_median, clear_count, snow_count) and summer (ndvi_median). patch:
    {(row, col): april NDVI} for single cells."""
    spring, summer = os.path.join(tmp, "april2025"), os.path.join(tmp, "july2025")
    os.makedirs(spring, exist_ok=True); os.makedirs(summer, exist_ok=True)
    a = np.full((N, N), apr * 1e4)
    for (r, c), v in (patch or {}).items():
        a[r, c] = ND if v is None else v * 1e4
    write(os.path.join(spring, "ndvi_median.tif"), a, "int16", ND, tags={"ACQUISITIONS": "2025-04-05 test"}, **kw)
    write(os.path.join(spring, "clear_count.tif"), np.full((N, N), clear), "uint8", **kw)
    write(os.path.join(spring, "snow_count.tif"), np.full((N, N), snow), "uint8", **kw)
    write(os.path.join(summer, "ndvi_median.tif"), np.full((N, N), jul * 1e4), "int16", ND,
          tags={"ACQUISITIONS": "2025-07 test"}, **kw)
    return spring, summer


def area():
    """The 120 x 80 m test area (the build test's DSM), as (west, south, east, north)."""
    return 560000.0, 4829920.0, 560120.0, 4830000.0


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class SeasonsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def seasons(self, **kw):
        import build
        return build.Seasons(*seasons_dirs(self.tmp.name, **kw), area())

    def test_the_test_square_is_on_the_ground_grid(self):
        import build
        self.assertEqual(((X0 - build.grid.ORIGIN_X) / 10, (build.grid.ORIGIN_Y - Y1) / 10), (6398.0, 2565.0))

    def test_a_green_crown_over_snow_is_evergreen(self):
        c = self.seasons().cue(560050.0, 4829960.0, 6.0)
        self.assertEqual(c["apr_ndvi"], 0.5)
        self.assertEqual(c["jul_ndvi"], 0.8)
        self.assertEqual(c["snow_share"], 1.0)
        self.assertEqual(c["april_views"], 2)
        self.assertAlmostEqual(c["crown_m2"], math.pi * 36, places=1)
        self.assertTrue(c["evergreen"])

    def test_without_snow_it_cant_tell(self):
        # in the valley the April lawns are green too: a green crown there says nothing
        import build
        c = self.seasons(snow=0).cue(560050.0, 4829960.0, 6.0)
        self.assertEqual(c["snow_share"], 0.0)
        self.assertFalse(build.can_tell_spring(c))
        self.assertFalse(c["evergreen"])
        c = self.seasons(snow=1).cue(560050.0, 4829960.0, 6.0)     # one of two views snow: half, enough
        self.assertEqual(c["snow_share"], 0.5)
        self.assertTrue(c["evergreen"])

    def test_a_small_crown_cant_tell(self):
        # under half a 10 m cell, the cells' colour is mostly the neighbourhood's
        import build
        r = math.sqrt(build.SPRING_MIN_CROWN_M2 / math.pi)
        s = self.seasons()
        self.assertFalse(s.cue(560050.0, 4829960.0, r - 0.05)["evergreen"])
        self.assertTrue(s.cue(560050.0, 4829960.0, r + 0.05)["evergreen"])

    def test_a_dark_crown_over_snow_says_nothing(self):
        # one-sided: it isn't evergreen, but it isn't called broadleaf either (a snow-laden conifer reads dark)
        import build
        c = self.seasons(apr=0.05).cue(560050.0, 4829960.0, 6.0)
        self.assertTrue(build.can_tell_spring(c))
        self.assertFalse(c["evergreen"])
        model = build.model_for(json.load(open(os.path.join(os.path.dirname(HERE), "model", "crown_model.json"))))
        keep = build.KEEP_WIDTH_CONIFER
        try:
            for k, want in ((True, "conifer"), (False, "broadleaf")):
                build.KEEP_WIDTH_CONIFER = k
                self.assertEqual(build.placed_type(None, 15.0, "conifer", model, c), want)
        finally:
            build.KEEP_WIDTH_CONIFER = keep

    def test_the_crown_is_weighted_by_its_area_in_each_cell(self):
        # a crown centred on a cell corner covers four cells equally; one of them reads 0.1, the others 0.5
        s = self.seasons(patch={(13, 14): 0.1})                    # the cell west of E 560050 and north of N 4829960
        c = s.cue(560050.0, 4829960.0, 6.0)
        self.assertAlmostEqual(c["apr_ndvi"], 0.4, delta=0.02)     # points on a cell edge count to the east and south
        c = s.cue(560045.0, 4829965.0, 3.0)                         # wholly inside that cell
        self.assertAlmostEqual(c["apr_ndvi"], 0.1, places=3)

    def test_cells_without_an_april_view_are_left_out(self):
        s = self.seasons(patch={(13, 14): None})
        self.assertAlmostEqual(s.cue(560050.0, 4829960.0, 6.0)["apr_ndvi"], 0.5, places=3)
        self.assertIsNone(s.cue(560045.0, 4829965.0, 3.0)["apr_ndvi"])

    def test_the_snow_share_is_read_within_50_m(self):
        # snow only far from the crown: it can't tell; snow in the cells around it: it can
        import build
        d = self.tmp.name
        spring, summer = seasons_dirs(d, snow=0)
        sn = np.zeros((N, N)); sn[:, 30:] = 2                        # E 560200 and east: over 140 m from the crown
        write(os.path.join(spring, "snow_count.tif"), sn, "uint8")
        c = build.Seasons(spring, summer, area()).cue(560050.0, 4829960.0, 6.0)
        self.assertEqual(c["snow_share"], 0.0)
        sn = np.zeros((N, N)); sn[4:25, 5:26] = 2                   # every cell within 50 m of it, and more
        write(os.path.join(spring, "snow_count.tif"), sn, "uint8")
        c = build.Seasons(spring, summer, area()).cue(560050.0, 4829960.0, 6.0)
        self.assertEqual(c["snow_share"], 1.0)

    def test_rasters_off_the_grid_are_refused(self):
        import build
        d = self.tmp.name
        for kw in ({"x0": X0 + 5}, {"res": 20.0}, {"crs": "EPSG:26911"}):
            with self.subTest(**kw):
                with self.assertRaises(ValueError):
                    build.Seasons(*seasons_dirs(os.path.join(d, str(len(kw)) + list(kw)[0]), **kw), area())

    def test_what_the_build_records(self):
        import build
        ab = self.seasons().about()
        self.assertEqual(ab["april"], "2025-04-05 test")
        self.assertEqual(ab["july"], "2025-07 test")
        self.assertEqual(ab["credit"], "Contains modified Copernicus Sentinel data 2025")
        self.assertEqual(sorted(ab["files"]), ["spring/clear_count.tif", "spring/ndvi_median.tif",
                                               "spring/snow_count.tif", "summer/ndvi_median.tif"])
        self.assertTrue(all(len(f["sha256"]) == 64 and f["bytes"] > 0 for f in ab["files"].values()))
        self.assertEqual(ab["rule"], {"near_m": build.SPRING_NEAR_M, "snow_min": build.SPRING_SNOW_MIN,
                                      "min_crown_m2": build.SPRING_MIN_CROWN_M2, "ndvi_min": build.SPRING_NDVI_MIN})
        self.assertNotIn(self.tmp.name, json.dumps(ab))                 # no paths


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class SpringTypeTest(unittest.TestCase):
    def setUp(self):
        import build
        self.model = build.model_for(json.load(open(os.path.join(os.path.dirname(HERE), "model", "crown_model.json"))))
        self.keep = build.KEEP_WIDTH_CONIFER

    def tearDown(self):
        import build
        build.KEEP_WIDTH_CONIFER = self.keep

    def test_the_order_narrow_spring_then_the_curve(self):
        import build
        narrow_p = {"top_m": 10.0, "drop_1m": 0.2, "drop_2m": 0.4, "drop_3m": 0.6, "rough": 0.05}
        green = {"apr_ndvi": 0.4, "jul_ndvi": 0.7, "snow_share": 1.0, "april_views": 2, "crown_m2": 80.0}
        dark = dict(green, apr_ndvi=0.1)
        valley = dict(green, snow_share=0.0)
        for keep in (True, False):
            build.KEEP_WIDTH_CONIFER = keep
            self.assertEqual(build.placed_type(narrow_p, 9.2, "broadleaf", self.model, green), "narrow")
            self.assertEqual(build.placed_type(None, 9.2, "broadleaf", self.model, green), "conifer")
            self.assertEqual(build.placed_type(None, 9.2, "narrow", self.model, green), "conifer")
            for s in (dark, valley, None):
                self.assertEqual(build.placed_type(None, 9.2, "broadleaf", self.model, s), "broadleaf")
                self.assertEqual(build.placed_type(None, 9.2, "conifer", self.model, s), "conifer" if keep else "broadleaf")

    def test_the_rule_matches_its_constants(self):
        import build
        ok = {"apr_ndvi": build.SPRING_NDVI_MIN, "jul_ndvi": 0.5, "snow_share": build.SPRING_SNOW_MIN, "april_views": 1,
              "crown_m2": build.SPRING_MIN_CROWN_M2}
        self.assertTrue(build.evergreen(ok))
        for k, v in (("apr_ndvi", build.SPRING_NDVI_MIN - 0.001), ("snow_share", build.SPRING_SNOW_MIN - 0.01),
                     ("crown_m2", build.SPRING_MIN_CROWN_M2 - 0.1), ("apr_ndvi", None), ("snow_share", None)):
            self.assertFalse(build.evergreen(dict(ok, **{k: v})), k)
        self.assertFalse(build.evergreen(None))
        self.assertFalse(build.evergreen({}))


@unittest.skipIf(np is None, "NumPy/SciPy/rasterio not installed (run in the worker image)")
class SpringBuildTest(unittest.TestCase):
    def run_build(self, tmp, **kw):
        """Two crowns 30 m apart on flat ground, as in test_narrow: a cone that falls fast and a broad dome."""
        import build
        shape = (160, 240)
        hgt = np.maximum(cone(shape, 80, 60, 14.0, 5.0), dome(shape, 80, 180, 15.0, 7.0)).astype(np.float32)
        ground = np.full(shape, 1800.0, np.float32)
        prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=1, dtype="float32", crs="EPSG:32611",
                    transform=from_origin(560000.0, 4830000.0, 0.5, 0.5), nodata=-9999.0)
        for name, arr in (("dsm.tif", ground + hgt), ("dtm.tif", ground)):
            with rasterio.open(os.path.join(tmp, name), "w", **prof) as ds:
                ds.write(arr, 1)
        spring, summer = seasons_dirs(tmp, **kw)
        out = os.path.join(tmp, "out")
        build.main(["--area", "t", "--dsm", os.path.join(tmp, "dsm.tif"), "--dtm", os.path.join(tmp, "dtm.tif"),
                    "--lidar", "synthetic", "--spring", spring, "--summer", summer, "--out", out])
        with open(os.path.join(out, "trees.geojson")) as f:
            trees = [ft["properties"] for ft in json.load(f)["features"]]
        with open(os.path.join(out, "build.json")) as f:
            return trees, json.load(f)

    def tallest(self, trees, east):
        near = [t for t in trees if abs(int(t["id"].split("-")[1]) - east) <= 4]
        self.assertTrue(near, [t["id"] for t in trees])
        return max(near, key=lambda t: t["height_m"])

    def test_over_snow_the_dome_is_a_conifer_and_the_cone_stays_narrow(self):
        import build
        with tempfile.TemporaryDirectory() as tmp:
            trees, bj = self.run_build(tmp)
        dome_t, cone_t = self.tallest(trees, 560090), self.tallest(trees, 560030)
        self.assertEqual(dome_t["type"], "conifer")
        self.assertTrue(dome_t["fit"]["spring"]["evergreen"])
        self.assertEqual(cone_t["type"], "narrow")                    # the narrow rule comes first
        m = build.model_for(json.load(open(os.path.join(os.path.dirname(HERE), "model", "crown_model.json"))))
        for t in trees:                                               # a stored build can be retyped
            fit = t["fit"]
            self.assertEqual(t["type"], build.placed_type(fit["profile"], t["height_m"], fit["width_curve"], m,
                                                          fit["spring"]))
        sp = bj["params"]["spring"]
        self.assertEqual(sp["credit"], "Contains modified Copernicus Sentinel data 2025")
        self.assertEqual(sp["rule"]["ndvi_min"], build.SPRING_NDVI_MIN)
        self.assertEqual([s["source"] for s in bj["params"]["sources"]], ["trees/usgs_3dep_lidar", "trees/sentinel2"])
        c = bj["counts"]["spring"]
        self.assertGreaterEqual(c["can_tell"], c["evergreen"])
        self.assertGreaterEqual(c["evergreen"], c["conifer"])
        self.assertGreaterEqual(c["conifer"], 1)
        self.assertEqual(c["conifer"], sum(1 for t in trees if t["type"] == "conifer" and t["fit"]["spring"]["evergreen"]))

    def test_in_the_valley_nothing_changes(self):
        import build
        keep = build.KEEP_WIDTH_CONIFER
        build.KEEP_WIDTH_CONIFER = False
        try:
            with tempfile.TemporaryDirectory() as tmp:
                trees, bj = self.run_build(tmp, snow=0, apr=0.7)          # green April lawns, no snow
        finally:
            build.KEEP_WIDTH_CONIFER = keep
        self.assertEqual(self.tallest(trees, 560090)["type"], "broadleaf")
        self.assertEqual(bj["counts"]["spring"], {"can_tell": 0, "evergreen": 0, "conifer": 0})

    def test_spring_and_summer_go_together(self):
        import build
        with self.assertRaises(SystemExit):
            build.main(["--area", "t", "--dsm", "x", "--dtm", "y", "--spring", "s", "--out", "o"])

    def test_a_lidar_outside_utm_11n_is_refused(self):
        import build
        with tempfile.TemporaryDirectory() as tmp:
            prof = dict(driver="GTiff", height=10, width=10, count=1, dtype="float32", crs="EPSG:32612",
                        transform=from_origin(560000.0, 4830000.0, 0.5, 0.5), nodata=-9999.0)
            for name in ("dsm.tif", "dtm.tif"):
                with rasterio.open(os.path.join(tmp, name), "w", **prof) as ds:
                    ds.write(np.zeros((10, 10), np.float32), 1)
            spring, summer = seasons_dirs(tmp)
            with self.assertRaises(SystemExit) as cm:
                build.main(["--area", "t", "--dsm", os.path.join(tmp, "dsm.tif"), "--dtm", os.path.join(tmp, "dtm.tif"),
                            "--spring", spring, "--summer", summer, "--out", os.path.join(tmp, "out")])
            self.assertIn("UTM 11N", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
