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
    import rasterio.windows
    from osgeo import ogr  # noqa: F401
    from pyproj import Transformer
    from rasterio.transform import from_origin
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))
sys.path.insert(0, HERE)
CSB_CREDIT = "USDA NASS Crop Sequence Boundaries 2018-2025"

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
                           "--crop-licence", "public-domain", "--crop-republish", "yes", "--crop-credit", CSB_CREDIT,
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
        self.assertEqual(chk["pieces_called_crop"], c["dropped_pieces"]["crop"])
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
        self.assertEqual(p["photo_cover"], 1.0)
        self.assertEqual(p["rule"]["crop_piece_share"], 0.5)

    def test_the_licence_is_the_strictest_of_the_inputs(self):
        b = self.build
        self.assertEqual((b["license"], b["republish"]), ("public-domain", "yes"))
        self.assertEqual(b["credit"], f"U.S. Geological Survey, 3D Elevation Program; USDA NAIP; {CSB_CREDIT}")
        ins = b["inputs"]
        self.assertEqual(sorted(ins), ["crop", "lidar", "photo"])
        self.assertEqual((ins["lidar"]["source"], ins["photo"]["source"]), ("trees/usgs_3dep_lidar", "trees/usda_naip"))
        for role, name in (("dsm", "dsm.tif"), ("dtm", "dtm.tif"), ("mask", "mask.npy")):
            f = ins["lidar"]["files"][role]
            self.assertEqual(f["file"], name)
            self.assertEqual(f["sha256"], B().M.sha256_of(os.path.join(self.tmp, name)))
        self.assertEqual(ins["lidar"]["points"], [{"file": "cloud.las",
                                                   "bytes": os.path.getsize(os.path.join(self.tmp, "cloud.las"))}])
        self.assertEqual(ins["photo"]["sha256"], B().M.sha256_of(os.path.join(self.tmp, "photo.tif")))
        self.assertEqual((ins["crop"]["file"], ins["crop"]["given"], ins["crop"]["credit"]),
                         ("crop.geojson", True, [CSB_CREDIT]))

    def test_a_photo_that_misses_part_of_the_area_stops_the_build(self):
        import build_shrubs
        p = lambda n: os.path.join(self.tmp, n)  # noqa: E731
        with rasterio.open(p("photo.tif")) as ds:
            prof, half = ds.profile, ds.read(window=rasterio.windows.Window(0, 0, ds.width // 2, ds.height))
            prof.update(width=half.shape[2])
        with rasterio.open(p("half.tif"), "w", **prof) as ds:
            ds.write(half)
        with self.assertRaises(SystemExit) as cm:
            build_shrubs.main(["--area", "x", "--dsm", p("dsm.tif"), "--dtm", p("dtm.tif"), "--points", p("cloud.las"),
                               "--photo", p("half.tif"), "--lidar-date", "2023-10-24", "--out", p("x-half")])
        self.assertIn("NDVI on", str(cm.exception))
        self.assertFalse(os.path.exists(p("x-half")))        # it stopped before the point cloud

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

    def test_a_shift_must_earn_its_distance(self):
        import build_shrubs as B
        choose = B.choose_shift
        self.assertEqual(choose({(0, 0): 0.101, (-4, 0): 0.106, (2, 2): 0.09}), (0, 0))     # 2 m for 0.005: noise
        self.assertEqual(choose({(0, 0): 0.388, (-4, 0): 0.411, (-3, 0): 0.40}), (-4, 0))   # 2 m for 0.023
        self.assertEqual(choose({(0, 0): 0.485, (1, 0): 0.488}), (1, 0))                    # 0.5 m for 0.003
        self.assertEqual(choose({(0, 0): 0.136, (0, -1): 0.1362}), (0, 0))                  # 0.5 m for 0.0002
        self.assertEqual(choose({(0, 0): 0.5, (2, 0): 0.6, (-2, 0): 0.6}), (2, 0))          # ties: either, shortest

    def test_a_crs_in_the_same_utm_zone_is_the_same_frame(self):
        import build_shrubs as B
        self.assertTrue(B.same_frame("EPSG:26911", "EPSG:6340"))
        self.assertTrue(B.same_frame("EPSG:32611", "EPSG:6340"))
        self.assertFalse(B.same_frame("EPSG:5070", "EPSG:6340"))
        self.assertFalse(B.same_frame("EPSG:26912", "EPSG:6340"))

    def test_another_datum_is_refused_not_shifted_by_100_m(self):
        import build_shrubs as B
        with self.assertRaises(SystemExit):
            B.same_frame("EPSG:26711", "EPSG:6340")                 # NAD27 / UTM 11N
        with self.assertRaises(SystemExit):
            B.check_datum("EPSG:4267", "EPSG:6340", "x")            # NAD27
        for ok in ("EPSG:26911", "EPSG:32611", "EPSG:5070", "EPSG:6350", "EPSG:4326", "EPSG:3857"):
            B.check_datum(ok, "EPSG:6340", ok)                      # NAD83's realisations and WGS 84
        from osgeo import ogr, osr
        from rasterio.crs import CRS
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = os.path.join(d, "fields.gpkg")
            ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(4267)
            lyr = ds.CreateLayer("fields", srs, ogr.wkbPolygon)
            f = ogr.Feature(lyr.GetLayerDefn())
            f.SetGeometry(ogr.CreateGeometryFromWkt("POLYGON((-117 43,-116.9 43,-116.9 43.1,-117 43))"))
            lyr.CreateFeature(f)
            ds = None
            with self.assertRaises(SystemExit) as cm:
                B.crop_mask(path, None, from_origin(X0, Y1, PX, PX), CRS.from_epsg(6340), (N, N))
            self.assertIn("1927", str(cm.exception))


def B():
    import build_shrubs
    return build_shrubs


def crop_cover(folder, west, north, n=10):
    """A crop cover as farm exports it (3 bands on the ground's 10 m grid, EPSG:32611): corn in a 20 m square 30-50 m
    in from its corner."""
    path = os.path.join(folder, "crop_cover.tif")
    bands = np.zeros((3, n, n), np.uint8)
    bands[0, 3:5, 3:5] = 1
    bands[1], bands[2] = 1, 1
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=3, dtype="uint8", crs="EPSG:32611",
                       transform=from_origin(west, north, 10, 10)) as ds:
        ds.write(bands)
    return path


def farm_export(root, build="20261011T130710Z", republish="yes", n=10):
    """crop_cover.tif in <root>/farm/export/<build>/ with its manifest, written by the ground's own writer."""
    M = B().M
    folder = os.path.join(root, "farm", "export", build)
    os.makedirs(folder)
    path = crop_cover(folder, X0 - 20, Y1 + 20, n)
    inputs = [{"name": "csb", "licence": "public-domain", "republish": republish, "credit": CSB_CREDIT,
               "source": "farm/nass_csb", "version": "csb-2018-2025-rev23", "sha256": "0" * 64},
              {"name": "sentinel-2", "licence": "Copernicus", "republish": "yes",
               "credit": "Contains modified Copernicus Sentinel data 2025"}]
    layer = {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
             "grid": {"res": 10, "west": X0 - 20, "north": Y1 + 20, "width": n, "height": n},
             "bands": [{"name": "group", "type": "uint8"}, {"name": "state", "type": "uint8"},
                       {"name": "confidence", "type": "uint8"}],
             "inputs": ["csb", "sentinel-2"], "licence": "Copernicus", "base": False}
    M.write(folder, "farm", inputs, [layer])
    return path


@unittest.skipIf(np is None, "PDAL/GDAL/rasterio/NumPy/pyproj not installed (run in the worker image)")
class CropCoverTest(unittest.TestCase):
    def test_farms_crop_cover_on_its_own_10_m_grid(self):
        from rasterio.crs import CRS
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = crop_cover(d, X0 - 20, Y1 + 20)
            m, info = B().crop_mask(path, None, from_origin(X0, Y1, PX, PX), CRS.from_epsg(6340), (N, N))
            self.assertEqual(info, {"crop_raster": "crop_cover.tif"})
            self.assertEqual(int(m.sum()), 1600)          # 20 m x 20 m of 0.5 m cells, 10-30 m in from the grid's
            self.assertTrue(m[20:60, 20:60].all())

    def test_a_crop_cover_that_misses_part_of_the_area_stops_the_build(self):
        from rasterio.crs import CRS
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = crop_cover(d, X0 - 20, Y1 + 20, n=7)  # ends 10 m short of the grid's east and south edges
            with self.assertRaises(SystemExit) as cm:
                B().crop_mask(path, None, from_origin(X0, Y1, PX, PX), CRS.from_epsg(6340), (N, N))
            self.assertIn("doesn't cover", str(cm.exception))

    def test_an_export_gives_its_licence_build_and_sha256(self):
        build = B()
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = farm_export(d)
            reg = {"farm/nass_csb": {"republish": "yes"}}
            got = build.crop_input(path, registry=reg)
            self.assertEqual((got["plugin"], got["build"], got["layer"]), ("farm", "20261011T130710Z", "crop_cover"))
            self.assertEqual(got["sha256"], build.M.sha256_of(path))
            self.assertEqual((got["licence"], got["republish"]), ("Copernicus", "yes"))
            self.assertEqual(got["credit"], [CSB_CREDIT, "Contains modified Copernicus Sentinel data 2025"])
            self.assertEqual(got["inputs"][0], {"name": "csb", "version": "csb-2018-2025-rev23", "sha256": "0" * 64})
            with self.assertRaises(SystemExit):              # a manifest states the licence: no flags
                build.crop_input(path, "public-domain", "yes", "x", registry=reg)
            with open(path, "r+b") as f:                    # a file that isn't the one the manifest describes
                f.seek(-1, 2)
                last = f.read(1)[0]
                f.seek(-1, 2)
                f.write(bytes([last ^ 0xFF]))
            with self.assertRaises(SystemExit) as cm:
                build.crop_input(path, registry=reg)
            self.assertIn("sha256", str(cm.exception))

    def test_licences_and_republish(self):
        build = B()
        lidar = {"name": "lidar", "licence": "public-domain", "republish": "yes", "credit": ["USGS 3DEP"]}
        photo = {"name": "photo", "licence": "public-domain", "republish": "yes", "credit": ["USDA NAIP"]}
        crop = {"name": "crop", "licence": "Copernicus", "republish": "yes", "credit": ["CSB", "Copernicus 2025"]}
        self.assertEqual(build.licence_of([lidar, photo]), ("public-domain", "yes", ["USGS 3DEP", "USDA NAIP"]))
        self.assertEqual(build.licence_of([lidar, photo, crop]),
                         ("Copernicus", "yes", ["USGS 3DEP", "USDA NAIP", "CSB", "Copernicus 2025"]))
        osm = dict(crop, licence="ODbL-1.0", credit=["© OpenStreetMap contributors"])
        self.assertEqual(build.licence_of([lidar, osm])[0], "ODbL-1.0")
        build.require_republish([lidar, photo, crop])
        with self.assertRaises(SystemExit) as cm:
            build.require_republish([lidar, dict(crop, republish="internal")])
        self.assertIn("crop (internal)", str(cm.exception))
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = os.path.join(d, "fields.geojson")
            with open(path, "w") as f:
                json.dump({"type": "FeatureCollection", "features": []}, f)
            with self.assertRaises(SystemExit):              # no manifest and nothing given
                build.crop_input(path)
            with self.assertRaises(SystemExit):              # looser than the licence allows
                build.crop_input(path, "restricted", "yes", "x")
            with self.assertRaises(SystemExit):              # rests on a source's decision: needs a manifest
                build.crop_input(path, "none-stated", "yes", "x")
            got = build.crop_input(path, "public-domain", "internal", CSB_CREDIT + "; USDA NASS CDL")
            self.assertEqual(got["credit"], [CSB_CREDIT, "USDA NASS CDL"])
            with self.assertRaises(SystemExit):
                build.require_republish([lidar, got])

    def test_an_export_that_may_not_be_republished_stops_the_build_first(self):
        build = B()
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = farm_export(d, republish="internal")
            out = os.path.join(d, "x-internal")
            with self.assertRaises(SystemExit) as cm:
                build.main(["--area", "x", "--dsm", "nothing.tif", "--dtm", "nothing.tif", "--points", "x.las",
                            "--photo", "nothing.tif", "--crop", path, "--out", out])
            self.assertIn("may not be republished", str(cm.exception))
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
