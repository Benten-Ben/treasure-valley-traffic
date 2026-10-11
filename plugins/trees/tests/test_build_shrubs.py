"""The shrubs build end to end (build_shrubs.py) on a synthetic area: lidar rasters, a building mask, a 4-band photo in
NAIP's CRS, a LAS cloud and crop fields, then the loader's reading of what it wrote. Needs PDAL, GDAL, rasterio, NumPy,
SciPy and pyproj: run it in the worker image, where a skip counts as a failure."""
import json
import os
import shutil
import sys
import tempfile
import unittest

try:
    import numpy as np
    import pdal  # noqa: F401
    import rasterio
    from osgeo import ogr  # noqa: F401
    from pyproj import Transformer
    from rasterio.transform import from_origin
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))
sys.path.insert(0, HERE)

X0, Y1, PX, N = 500000.0, 4800060.0, 0.5, 120          # a 60 m square in EPSG:6340
GROUND = 100.0
BUSH, SAGE, SKIPPED = (10.25, 10.25), (30.25, 10.25), (50.25, 10.25)   # metres east and south of the NW corner
CROP = (30.0, 30.0, 50.0, 50.0)                                   # east0, south0, east1, south1


def dome(cx, cy, H, W, a=0.6, n=2.0):
    yy, xx = np.mgrid[0:N, 0:N]
    d = np.hypot((xx + 0.5) * PX - cx, (yy + 0.5) * PX - cy) / (W / 2)
    return np.where(d <= 1, H * (1 - a * np.minimum(d, 1) ** n), 0.0)


def ball(rng, cx, cy, z, r, n):
    from test_cloud import DTYPE
    u = rng.normal(size=(n, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    k = rng.random(n) ** (1 / 3)
    out = np.zeros(n, DTYPE)
    out["X"], out["Y"], out["Z"] = X0 + cx + r * k * u[:, 0], Y1 - cy + r * k * u[:, 1], GROUND + z + 0.5 * r * k * u[:, 2]
    out["Classification"] = 1
    return out


def make_area(d):
    from test_cloud import DTYPE, write_las
    rng = np.random.default_rng(7)
    h = np.maximum.reduce([dome(*BUSH, 1.2, 1.7), dome(*SAGE, 0.8, 1.4), dome(*SKIPPED, 1.1, 1.6)])
    e0, s0, e1, s1 = CROP
    crop = np.zeros((N, N), bool)
    crop[int(s0 / PX):int(s1 / PX), int(e0 / PX):int(e1 / PX)] = True
    h[crop] = 1.0 + rng.normal(0, 0.03, int(crop.sum()))                 # an even crop, 1 m tall
    bld = np.zeros((N, N), bool)
    bld[10:22, 80:92] = True                                             # a building 6 m square, 4 m tall
    h[bld] = 4.0
    tf = from_origin(X0, Y1, PX, PX)
    for name, arr in (("dsm", GROUND + h), ("dtm", np.full((N, N), GROUND))):
        with rasterio.open(os.path.join(d, name + ".tif"), "w", driver="GTiff", width=N, height=N, count=1,
                           dtype="float32", crs="EPSG:6340", transform=tf, nodata=-9999) as ds:
            ds.write(arr.astype(np.float32), 1)
    np.save(os.path.join(d, "mask.npy"), bld)
    # the photo: NAIP's CRS and 0.3 m cells; green (NDVI 0.6) on the bush, the skipped bush and the crop
    green = (dome(*BUSH, 1, 1.7) > 0) | (dome(*SKIPPED, 1, 1.6) > 0) | crop
    pn = 220
    ptf = from_origin(X0 - 3, Y1 + 3, 0.3, 0.3)
    yy, xx = np.mgrid[0:pn, 0:pn]
    col = np.floor(((xx + 0.5) * 0.3 - 3) / PX).astype(int)
    row = np.floor(((yy + 0.5) * 0.3 - 3) / PX).astype(int)
    inside = (row >= 0) & (row < N) & (col >= 0) & (col < N)
    g = np.zeros((pn, pn), bool)
    g[inside] = green[row[inside], col[inside]]
    bands = np.stack([np.where(g, 40, 60), np.full((pn, pn), 60), np.full((pn, pn), 50), np.where(g, 160, 60)])
    with rasterio.open(os.path.join(d, "photo.tif"), "w", driver="GTiff", width=pn, height=pn, count=4, dtype="uint8",
                       crs="EPSG:26911", transform=ptf) as ds:
        ds.write(bands.astype(np.uint8))
    # the cloud: ground, and scattered volumes where the plants are (the sage is a plant to the lidar only)
    gg = np.arange(0.125, 60, 0.25)
    gx, gy = np.meshgrid(gg, gg)
    ground = np.zeros(gx.size, DTYPE)
    ground["X"], ground["Y"], ground["Z"], ground["Classification"] = X0 + gx.ravel(), Y1 - gy.ravel(), GROUND, 2
    pts = np.concatenate([ground, ball(rng, *BUSH, 0.8, 0.8, 2000), ball(rng, *SAGE, 0.5, 0.7, 2000),
                          ball(rng, *SKIPPED, 0.7, 0.8, 2000)])
    pts["ReturnNumber"], pts["NumberOfReturns"] = 1, 1
    write_las(os.path.join(d, "cloud.las"), pts)
    # crop fields as a farm or CSB vector in WGS84: the crop, and a pasture over the bush that --crop-where leaves out
    to_ll = Transformer.from_crs("EPSG:6340", 4326, always_xy=True)

    def poly(e0, s0, e1, s1):
        ring = [(e0, s0), (e1, s0), (e1, s1), (e0, s1), (e0, s0)]
        return {"type": "Polygon", "coordinates": [[list(to_ll.transform(X0 + e, Y1 - s)) for e, s in ring]]}
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"CDL2025": 1}, "geometry": poly(e0 - 2, s0 - 2, e1 + 2, s1 + 2)},
        {"type": "Feature", "properties": {"CDL2025": 176}, "geometry": poly(5, 5, 15, 15)}]}
    with open(os.path.join(d, "crop.geojson"), "w") as f:
        json.dump(fc, f)


@unittest.skipIf(np is None, "PDAL/GDAL/rasterio/NumPy/pyproj not installed (run in the worker image)")
class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_shrubs
        cls.tmp = tempfile.mkdtemp(dir="/tmp")
        make_area(cls.tmp)
        cls.out = os.path.join(cls.tmp, "x-test")
        p = lambda n: os.path.join(cls.tmp, n)  # noqa: E731
        skip = f"{X0 + 45},{Y1 - 15},{X0 + 55},{Y1 - 5}"
        build_shrubs.main(["--area", "x", "--dsm", p("dsm.tif"), "--dtm", p("dtm.tif"), "--mask", p("mask.npy"),
                           "--points", p("cloud.las"), "--photo", p("photo.tif"), "--photo-shift", "0,0",
                           "--crop", p("crop.geojson"), "--crop-where", "CDL2025 BETWEEN 1 AND 61",
                           "--skip-rect", skip, "--lidar", "synthetic lidar", "--lidar-date", "2023-10-24",
                           "--chunk-m", "20", "--out", cls.out])
        with open(os.path.join(cls.out, "build.json")) as f:
            cls.build = json.load(f)
        with open(os.path.join(cls.out, "shrubs.geojson")) as f:
            cls.shrubs = json.load(f)["features"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def located(self):
        tr = Transformer.from_crs(4326, "EPSG:6340", always_xy=True)
        out = []
        for f in self.shrubs:
            x, y = tr.transform(*f["geometry"]["coordinates"])
            out.append((round(x - X0), round(Y1 - y), f["properties"]))
        return out

    def test_a_bush_and_a_sage_and_nothing_else(self):
        got = sorted((e, s, p["look"]) for e, s, p in self.located())
        self.assertEqual(got, [(10, 10, "bush"), (30, 10, "sage")])
        props = {p["look"]: p for _, _, p in self.located()}
        self.assertAlmostEqual(props["bush"]["height_m"], 1.2, delta=0.05)
        self.assertAlmostEqual(props["sage"]["height_m"], 0.8, delta=0.05)
        self.assertEqual(props["bush"]["ground_m"], GROUND)
        self.assertTrue(props["bush"]["id"].startswith("x-"))

    def test_crops_are_left_alone_and_the_rule_checks_them(self):
        c = self.build["counts"]
        self.assertGreaterEqual(c["dropped_pieces"]["crop"], 1)
        chk = c["crop_check"]
        self.assertEqual(chk["crop_input"], {"crop_fields": 1})
        self.assertGreater(chk["shrub_cells_called_crop"], 1000)
        self.assertGreaterEqual(chk["rule_field_blocks"], 1)
        self.assertEqual(chk["rule_shrub_cells_left_by_crop"], 0)
        self.assertEqual(chk["rule_shrubs"], 0)
        import shrubs as S
        with rasterio.open(os.path.join(self.out, "why.tif")) as ds:
            why = ds.read(1)
        self.assertEqual(why[80, 80], S.WHY["crop"])
        self.assertEqual(why[20, 20], S.WHY["shrub"])

    def test_the_skipped_part_is_left_out(self):
        b = self.build
        self.assertEqual(b["params"]["skip_rects"], [[X0 + 45, Y1 - 15, X0 + 55, Y1 - 5]])
        self.assertAlmostEqual(b["counts"]["area_ha"], 0.35, delta=0.005)
        self.assertEqual(b["geom"]["type"], "MultiPolygon")
        self.assertEqual(b["counts"]["shrubs"], 2)
        # the outline is the grid's edge exactly, with the skipped square cut out exactly
        tr = Transformer.from_crs(4326, "EPSG:6340", always_xy=True)
        pts = [tr.transform(*p) for poly in b["geom"]["coordinates"] for ring in poly for p in ring]
        xs, ys = [p[0] - X0 for p in pts], [Y1 - p[1] for p in pts]
        self.assertAlmostEqual(min(xs), 0, delta=0.01)
        self.assertAlmostEqual(max(xs), 60, delta=0.01)
        self.assertAlmostEqual(min(ys), 0, delta=0.01)
        self.assertAlmostEqual(max(ys), 60, delta=0.01)
        corners = {(round(x, 1), round(y, 1)) for x, y in zip(xs, ys)}
        self.assertTrue({(45.0, 5.0), (55.0, 5.0), (45.0, 15.0), (55.0, 15.0)} <= corners, corners)

    def test_the_settings_are_recorded(self):
        p = self.build["params"]
        self.assertEqual(p["photo_shift_m"], [0.0, 0.0])
        self.assertTrue(0 < p["ndvi_cut"] < 0.6, p["ndvi_cut"])   # sage (NDVI 0) below, green (0.6) above
        self.assertEqual(p["rule"]["band_m"], [0.3, 2.4])
        self.assertEqual(p["width"]["bush"]["a"], 1.478)
        self.assertEqual(self.build["counts"]["cloud"]["above_ground"], 6000)

    def test_the_loader_reads_it(self):
        from plugins.trees.ingest import shrubs_load
        build, shrubs = shrubs_load.read_build(self.out)
        self.assertEqual(build["build_id"], "x-test")
        self.assertEqual(len(shrubs), 2)
        lines = list(shrubs_load.rows(build, shrubs))
        self.assertTrue(all(line.count("\t") == len(shrubs_load.COLUMNS) - 1 for line in lines))


@unittest.skipIf(np is None, "PDAL/GDAL/rasterio/NumPy/pyproj not installed (run in the worker image)")
class ShiftTest(unittest.TestCase):
    def area(self, n_trees):
        rng = np.random.default_rng(5)
        h = np.zeros((200, 200), np.float32)
        yy, xx = np.mgrid[0:200, 0:200]
        for _ in range(n_trees):
            cy, cx, r = rng.integers(20, 180), rng.integers(20, 180), rng.integers(4, 9)
            h[np.hypot(yy - cy, xx - cx) <= r] = 8.0
        return h, np.zeros(h.shape, bool), np.zeros(h.shape, bool)

    def test_the_shift_is_where_the_photos_green_meets_the_trees(self):
        import build_shrubs as B
        h, bld, bad = self.area(80)
        P = B.SHIFT_REACH
        green = np.zeros((200 + 2 * P, 200 + 2 * P), bool)
        green[P + 1:P + 201, P + 3:P + 203] = h >= 2.4        # the photo's trees sit 1.5 m east and 0.5 m south
        (dx, dy), d = B.measure_shift(np.where(green, 0.6, 0.05).astype(np.float32), h, bld, bad)
        self.assertEqual((dx, dy), (3, 1))
        self.assertGreater(d["iou_best"], 0.9)

    def test_no_shift_without_trees(self):
        import build_shrubs as B
        h, bld, bad = self.area(2)
        P = B.SHIFT_REACH
        ndvi = np.full((200 + 2 * P, 200 + 2 * P), 0.05, np.float32)
        (dx, dy), d = B.measure_shift(ndvi, h, bld, bad)
        self.assertEqual((dx, dy), (0, 0))
        self.assertIn("too few trees", d["why"])

    def test_a_crs_in_the_same_utm_zone_is_the_same_frame(self):
        import build_shrubs as B
        self.assertTrue(B.same_frame("EPSG:26911", "EPSG:6340"))
        self.assertTrue(B.same_frame("EPSG:32611", "EPSG:6340"))
        self.assertFalse(B.same_frame("EPSG:5070", "EPSG:6340"))
        self.assertFalse(B.same_frame("EPSG:26912", "EPSG:6340"))


if __name__ == "__main__":
    unittest.main()
