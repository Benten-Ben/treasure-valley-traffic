"""The box classes' reading and writing (classes.py) on synthetic files: the frames, July's cells, the lines, the
ground brightness from a synthetic point cloud, the product's GeoTIFF and manifest as the ground reads them, and the
build itself on a synthetic recipe for the ten boxes (staging, a partial build, the recipe's shift, the preflight, the
lock, a stopped build, pruning and the command line).
Needs the worker image (GDAL, PDAL, NumPy, SciPy): the tests skip elsewhere, and in the worker image a skip counts
as a failure."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import numpy as np
    import pdal
    from osgeo import gdal, ogr, osr
    from basemap.ground import classes as CL
    from basemap.ground import classrules as CR
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import grid as G
from basemap.ground import inputs as I
from basemap.ground import manifest as M

BOX = G.box("f")


def lidar_grid(x0=None, y1=None, rows=40, cols=60):
    s = osr.SpatialReference()
    s.ImportFromEPSG(6340)
    w = BOX.window()
    return CL.LidarGrid(w.west if x0 is None else x0, w.north if y1 is None else y1, rows, cols, s.ExportToWkt())


@unittest.skipIf(np is None, "needs the worker image (GDAL, PDAL, NumPy, SciPy)")
class TestFrames(unittest.TestCase):
    def test_into_the_photo_frame(self):
        a = np.arange(30, dtype=np.uint8).reshape(5, 6) + 1
        out = CL.to_photo_frame(a, (1.0, 0.5))                  # 2 cells east, 1 north
        self.assertEqual(out[0, 2], a[1, 0])
        self.assertEqual(out[3, 5], a[4, 3])
        self.assertTrue((out[4, :] == 0).all() and (out[:, :2] == 0).all())
        self.assertIs(CL.to_photo_frame(a, (0.0, 0.0)), a)

    def test_lines_move_onto_the_lidar(self):
        g = lidar_grid()
        x = g.x0 + 10.25                                        # a line through column 20's centre, in the photo
        line = ogr.CreateGeometryFromWkt(f"LINESTRING({x} {g.y1 - 1}, {x} {g.y1 - 19})")
        m = CL.burn_lines([line], g, (1.0, 0.0))                # the photo sits 1 m east of the lidar
        cols = np.flatnonzero(m.any(axis=0))
        self.assertEqual(cols.tolist(), [18])
        wide = CL.burn_lines([line], g, (0.0, 0.0), reach_m=2.0)
        self.assertEqual(np.flatnonzero(wide[10]).tolist(), list(range(16, 25)))

    def test_the_lidar_grid_in_the_box_window(self):
        w = BOX.window()
        CL.check_box_grid(BOX, lidar_grid(rows=w.height, cols=w.width))
        g = lidar_grid(x0=w.west + 0.5, rows=w.height, cols=w.width - 2)          # box h's: half a metre inside
        self.assertEqual(CL.box_offset(BOX, g), (0, 1))
        with self.assertRaises(CL.ClassError):
            CL.check_box_grid(BOX, g)
        a = np.ones(g.shape, np.uint8)
        e = CL.embed(a, BOX, (0, 1))
        self.assertEqual(e.shape, w.shape)
        self.assertEqual((int(e[0, 0]), int(e[0, 1]), int(e[0, w.width - 2]), int(e[0, w.width - 1])), (0, 1, 1, 0))
        with self.assertRaises(CL.ClassError):
            CL.box_offset(BOX, lidar_grid(x0=w.west + 0.25))                     # off the 0.5 m grid
        with self.assertRaises(CL.ClassError):
            CL.box_offset(BOX, lidar_grid(x0=w.west - 5000))                     # nowhere near


@unittest.skipIf(np is None, "needs the worker image (GDAL, PDAL, NumPy, SciPy)")
class TestJulyCells(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_each_cell_takes_its_ten_metre_cell(self):
        g = lidar_grid(x0=550000.0, y1=4802000.0, rows=40, cols=40)    # on the 10 m grid's edges
        s = osr.SpatialReference()
        s.ImportFromEPSG(32611)
        c0, r0 = int((g.x0 - G.ORIGIN_X) / 10), int((G.ORIGIN_Y - g.y1) / 10)
        for name, dtype, val in (("ndvi_median", gdal.GDT_Int16, None), ("ndvi_max", gdal.GDT_Int16, 6000),
                                 ("ndvi_min", gdal.GDT_Int16, 1000), ("clear_count", gdal.GDT_Byte, 7)):
            ds = gdal.GetDriverByName("GTiff").Create(os.path.join(self.dir, f"{name}.tif"), G.COLS, G.ROWS, 1,
                                                      dtype, options=["TILED=YES", "COMPRESS=DEFLATE",
                                                                      "SPARSE_OK=TRUE"])
            ds.SetGeoTransform((G.ORIGIN_X, 10, 0, G.ORIGIN_Y, 0, -10))
            ds.SetProjection(s.ExportToWkt())
            b = ds.GetRasterBand(1)
            if dtype == gdal.GDT_Int16:
                b.SetNoDataValue(-32768)
            if val is None:
                blk = np.array([[1000, 2000], [3000, -32768]], np.int16)
            else:
                blk = np.full((2, 2), val, np.int16 if dtype == gdal.GDT_Int16 else np.uint8)
            b.WriteArray(blk, c0, r0)
            ds = None
        july, cell = CL.read_july(self.dir, g)
        self.assertAlmostEqual(float(july["med"][0, 0]), 0.1, places=5)
        self.assertAlmostEqual(float(july["med"][0, 39]), 0.2, places=5)
        self.assertAlmostEqual(float(july["med"][39, 0]), 0.3, places=5)
        self.assertTrue(np.isnan(july["med"][39, 39]))
        self.assertEqual(int(july["n"][5, 5]), 7)
        self.assertEqual(len(np.unique(cell)), 4)
        self.assertEqual(int(cell[0, 0]), int(cell[19, 19]))
        self.assertNotEqual(int(cell[0, 0]), int(cell[0, 20]))


@unittest.skipIf(np is None, "needs the worker image (GDAL, PDAL, NumPy, SciPy)")
class TestBrightness(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_each_line_over_its_own_median(self):
        g = lidar_grid(rows=20, cols=20)
        rng = np.random.default_rng(3)
        n = 20000
        dt = np.dtype([("X", "<f8"), ("Y", "<f8"), ("Z", "<f8"), ("Intensity", "<u2"), ("Classification", "u1"),
                       ("PointSourceId", "<u2")])
        pts = np.zeros(n, dt)
        pts["X"] = g.x0 + rng.uniform(0, 10, n)
        pts["Y"] = g.y1 - rng.uniform(0, 10, n)
        pts["Z"] = 800.0
        pts["Classification"] = 2
        west = pts["X"] < g.x0 + 5
        pts["PointSourceId"] = np.where(west, 1, 2)
        pts["Intensity"] = np.where(west, 100, 300)             # two lines, each bright in its own way
        dark = (pts["X"] < g.x0 + 2) & (pts["Y"] > g.y1 - 2)
        pts["Intensity"][dark] = 50                             # asphalt: half its line's level
        noise = rng.random(n) < 0.05
        pts["Classification"][noise] = 7
        pts["Intensity"][noise] = 5000
        path = os.path.join(self.dir, "pts.las")
        p = pdal.Pipeline(json.dumps([{"type": "writers.las", "filename": path, "a_srs": "EPSG:6340",
                                       "scale_x": 0.01, "scale_y": 0.01, "scale_z": 0.01,
                                       "extra_dims": "all"}]), arrays=[pts])
        p.execute()
        bright, st = CL.ground_brightness([path], g, log=lambda *_: None)
        self.assertEqual(st["lines"], 2)
        self.assertAlmostEqual(float(np.nanmedian(bright[:20, 12:20])), 1.0, places=2)
        self.assertAlmostEqual(float(np.nanmedian(bright[:20, :8])), 1.0, places=2)
        self.assertAlmostEqual(float(bright[1, 1]), 0.5, places=2)
        self.assertTrue(np.isnan(bright[19, 19]) or bright[19, 19] > 0)


@unittest.skipIf(np is None, "needs the worker image (GDAL, PDAL, NumPy, SciPy)")
class TestProduct(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def entries(self):
        E = I.RAW_BY_NAME
        return [E["3dep"].entry("QL1 2023"), E["naip"].entry("2025"), E["sentinel-2"].entry("July 2025"),
                E["osm"].entry("cd09"), E["overture-buildings"].entry("masks")]

    def write(self, ents, build="20261015T000000Z-part"):
        folder = M.export_dir(self.dir, CL.PRODUCT, build)
        os.makedirs(folder)
        w = BOX.window()
        cls = np.full(w.shape, CR.SHORT_DRY, np.uint8)
        CL.write_box(os.path.join(folder, "f.tif"), BOX, cls, cls)
        lay = {"name": "f", "file": "f.tif", "format": "GeoTIFF", "crs": G.CRS,
               "grid": {"res": w.res, "west": w.west, "north": w.north, "width": w.width, "height": w.height},
               "bands": CL.band_specs(), "inputs": [e["name"] for e in ents], "base": False}
        return M.write(folder, CL.PRODUCT, ents, [lay], build=build)

    def test_the_ground_reads_it(self):
        m = self.write(self.entries())
        lay = m.layer("f")
        self.assertEqual((lay["licence"], lay["republish"]), ("ODbL-1.0", "yes"))
        use = next(u for u in I.USES if u.plugin == CL.PRODUCT)
        I.check_public(lay, m)
        I.check_raw_only(lay, m)
        I.check_use(use, lay)
        self.assertEqual(lay["bands"][0]["values"]["13"], "forest floor")

    def test_a_non_raw_input_is_refused(self):
        ents = self.entries() + [{"name": "achd", "licence": "none-stated", "republish": "internal",
                                  "credit": "ACHD", "source": "roads/achd_roads"}]
        try:
            m = self.write(ents)
        except M.ManifestError:
            return                                              # refused already when written
        with self.assertRaises(I.InputError):
            I.check_public(m.layer("f"), m)


# ---- the build itself, on a synthetic recipe -------------------------------------------------------------------------

SIDE = 40                                             # each box's lidar: 40 x 40 cells (20 m) at its north-west corner


def _tif(path, arr, transform, epsg, nodata=None, dtype=None):
    arr = np.asarray(arr)
    bands = arr if arr.ndim == 3 else arr[None]
    gtype = dtype or {np.dtype("uint8"): gdal.GDT_Byte, np.dtype("float32"): gdal.GDT_Float32,
                      np.dtype("int16"): gdal.GDT_Int16}[bands.dtype]
    ds = gdal.GetDriverByName("GTiff").Create(path, bands.shape[2], bands.shape[1], bands.shape[0], gtype)
    ds.SetGeoTransform(transform)
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    ds.SetProjection(s.ExportToWkt())
    for i, band in enumerate(bands, start=1):
        ds.GetRasterBand(i).WriteArray(band)
        if nodata is not None:
            ds.GetRasterBand(i).SetNoDataValue(nodata)
    ds = None


def _osm(path, lines):
    """An OSM XML file of highway lines given in grid metres: [(((x, y), ...), {tags})]."""
    from ingest.utm import from_utm
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6" generator="test_classes">']
    ways, nid = [], 1000
    for i, (pts, tags) in enumerate(lines):
        ids = []
        for x, y in pts:
            lon, lat = from_utm(x, y)
            out.append(f'  <node id="{nid}" version="1" lat="{lat:.9f}" lon="{lon:.9f}"/>')
            ids.append(nid)
            nid += 1
        ways.append((100 + i, ids, tags))
    for wid, ids, tags in ways:
        out.append(f'  <way id="{wid}" version="1">')
        out += [f'    <nd ref="{n}"/>' for n in ids]
        out += [f'    <tag k="{k}" v="{v}"/>' for k, v in tags.items()]
        out.append("  </way>")
    out.append("</osm>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def make_recipe(root):
    """A recipe for all ten boxes, each a 20 m lidar grid at its window's north-west corner: flat bare ground with a
    small tree, a mapped track down the middle (box f's, bright in the photo) and a street along the south edge."""
    os.makedirs(root)
    july = os.path.join(root, "july")
    os.makedirs(july)
    s = osr.SpatialReference()
    s.ImportFromEPSG(32611)
    full = {}
    for name, dtype in (("ndvi_median", gdal.GDT_Int16), ("ndvi_max", gdal.GDT_Int16), ("ndvi_min", gdal.GDT_Int16),
                        ("clear_count", gdal.GDT_Byte)):
        ds = gdal.GetDriverByName("GTiff").Create(os.path.join(july, f"{name}.tif"), G.COLS, G.ROWS, 1, dtype,
                                                  options=["TILED=YES", "COMPRESS=DEFLATE", "SPARSE_OK=TRUE"])
        ds.SetGeoTransform((G.ORIGIN_X, 10, 0, G.ORIGIN_Y, 0, -10))
        ds.SetProjection(s.ExportToWkt())
        if dtype == gdal.GDT_Int16:
            ds.GetRasterBand(1).SetNoDataValue(-32768)
        full[name] = ds
    norm = os.path.join(root, "fits.json")
    curve = {"lut_x": [-1.0, 1.0], "lut_y": [-1.0, 1.0]}
    with open(norm, "w", encoding="utf-8") as f:
        json.dump({"naip2025": {"days": {"2025-05-25": {"curve": curve}}},
                   "naip2023_boxes_h_i_j": {"pooled_curve": curve}}, f)
    lines, boxes = [], {}
    rng = np.random.default_rng(7)
    for b in G.boxes():
        w = b.window()
        x0, y1 = float(w.west), float(w.north)
        d = os.path.join(root, b.id)
        os.makedirs(os.path.join(d, "lidar"))
        gt = (x0, 0.5, 0.0, y1, 0.0, -0.5)
        dtm = np.full((SIDE, SIDE), 800.0, np.float32)
        dsm = dtm.copy()
        dsm[5:11, 5:11] += 6.0                                    # a tree
        _tif(os.path.join(d, "lidar", "dtm.tif"), dtm, gt, 6340, nodata=-9999.0)
        _tif(os.path.join(d, "lidar", "dsm.tif"), dsm, gt, 6340, nodata=-9999.0)
        np.save(os.path.join(d, "mask.npy"), np.zeros((SIDE, SIDE), bool))
        shrubs = os.path.join(d, "shrubs")
        os.makedirs(os.path.join(shrubs, "work", "chunks"))
        _tif(os.path.join(shrubs, "why.tif"), np.zeros((SIDE, SIDE), np.uint8), gt, 6340)
        with open(os.path.join(shrubs, "build.json"), "w", encoding="utf-8") as f:
            json.dump({"build_id": f"shrubs-{b.id}", "params": {"photo_shift_m": [0.0, 0.0]},
                       "inputs": {"crop": {"inputs": [{"name": "csb", "version": "2025"}]}}}, f)
        with open(os.path.join(shrubs, "work", "cues.json"), "w", encoding="utf-8") as f:
            json.dump({"key": {"grid": [x0, y1, 0.5, SIDE, SIDE], "chunk_m": SIDE * 0.5}}, f)
        n_ag = np.zeros((SIDE, SIDE), np.uint16)
        n_ag[5:11, 5:11] = 9
        np.savez(os.path.join(shrubs, "work", "chunks", "0_0.npz"), n_ag=n_ag,
                 scat=np.where(n_ag > 0, 1.0, 0.0).astype(np.float32))
        # the photo: 1 m cells over the lidar and 10 m around it; red, green, blue, near-infrared (NDVI 0.2: dry)
        ph = np.zeros((4, 40, 40), np.float32)
        ph[:] = np.array([60, 60, 55, 90], np.float32)[:, None, None]
        ph[:, :, 19:21] *= 1.2                                     # the track, bright
        ph[3, 12:16, 12:16] = 200                                  # the tree, green
        _tif(os.path.join(d, "photo.tif"), ph, (x0 - 10, 1.0, 0.0, y1 + 10, 0.0, -1.0), 32611)
        # the points: ground points on two flight lines
        n = 4000
        dt = np.dtype([("X", "<f8"), ("Y", "<f8"), ("Z", "<f8"), ("Intensity", "<u2"), ("Classification", "u1"),
                       ("PointSourceId", "<u2")])
        pts = np.zeros(n, dt)
        pts["X"] = x0 + rng.uniform(0, SIDE * 0.5, n)
        pts["Y"] = y1 - rng.uniform(0, SIDE * 0.5, n)
        pts["Z"] = 800.0
        pts["Classification"] = 2
        pts["PointSourceId"] = np.where(pts["X"] < x0 + 10, 1, 2)
        pts["Intensity"] = 200
        las = os.path.join(d, "points.las")
        pdal.Pipeline(json.dumps([{"type": "writers.las", "filename": las, "a_srs": "EPSG:6340", "scale_x": 0.01,
                                   "scale_y": 0.01, "scale_z": 0.01, "extra_dims": "all"}]), arrays=[pts]).execute()
        # July: dry, a 10 m cell at a time
        c0, r0 = int((x0 - G.ORIGIN_X) // 10) - 1, int((G.ORIGIN_Y - y1) // 10) - 1
        for name, val in (("ndvi_median", 1500), ("ndvi_max", 2500), ("ndvi_min", 1000), ("clear_count", 6)):
            full[name].GetRasterBand(1).WriteArray(np.full((5, 5), val, np.int16 if name != "clear_count"
                                                           else np.uint8), c0, r0)
        lines.append((((x0 + 10.0, y1 + 5), (x0 + 10.0, y1 - 25)), {"highway": "track"}))
        lines.append((((x0 - 5, y1 - 18.0), (x0 + 25, y1 - 18.0)), {"highway": "residential"}))
        boxes[b.id] = {"lidar": os.path.join(d, "lidar"), "mask": os.path.join(d, "mask.npy"), "shrubs": shrubs,
                       "points": [las], "points_srs": None, "photo": os.path.join(d, "photo.tif"),
                       "curve": "naip2023" if b.id in ("h", "i", "j") else "naip2025:2025-05-25",
                       "lidar_name": "a synthetic survey", "lidar_date": "2023-10-27"}
    for ds in full.values():
        ds.FlushCache()
    full.clear()
    cut = os.path.join(root, "cut")
    os.makedirs(cut)
    osm = os.path.join(cut, "valley.osm")
    _osm(osm, lines)
    with open(os.path.join(cut, "valley.json"), "w", encoding="utf-8") as f:
        json.dump({"extract": "idaho-test.osm.pbf", "md5": "0123456789abcdef0123456789abcdef",
                   "sha256": M.sha256_of(osm)}, f)
    return {"osm": osm, "july": july, "norm": norm, "boxes": boxes}


def quiet(*_a, **_k):
    pass


def class_band(path):
    ds = gdal.Open(path)
    return ds.GetRasterBand(1).ReadAsArray()


@unittest.skipIf(np is None, "needs the worker image (GDAL, PDAL, NumPy, SciPy)")
class TestBuild(unittest.TestCase):
    """classes.build() end to end on a synthetic recipe: staging and one rename, the manifest's raw inputs, a partial
    build, the recipe's photo shift, the preflight, the lock, a stopped build, pruning and the command line."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.recipe = make_recipe(os.path.join(cls.dir, "in"))
        cls.archive = os.path.join(cls.dir, "archive")
        os.makedirs(cls.archive)
        cls.m = CL.build(cls.archive, cls.recipe, build_id="20261016T000000Z", log=quiet)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def other(self, name):
        path = os.path.join(self.dir, name)
        os.makedirs(path)
        return path

    def test_a_whole_build(self):
        m = self.m
        self.assertEqual(m.folder, M.export_dir(self.archive, CL.PRODUCT, "20261016T000000Z"))
        self.assertEqual(sorted(lay.name for lay in m.layers), sorted(b.id for b in G.boxes()))
        self.assertEqual(os.listdir(os.path.join(self.archive, CL.PRODUCT, CL.STAGING)), [])
        self.assertEqual(CL.latest(self.archive).build, m.build)
        for lay in m.layers:                                    # what the ground checks before it reads them
            I.check_public(lay, m)
            I.check_raw_only(lay, m)
            I.check_use(next(u for u in I.USES if u.plugin == CL.PRODUCT), lay)
        self.assertEqual(sorted(m.inputs), ["3dep", "csb", "naip", "osm", "overture-buildings", "sentinel-2"])
        self.assertEqual(m.inputs["osm"]["version"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(m.inputs["csb"]["version"], "2025")
        with open(os.path.join(m.folder, "report.json"), encoding="utf-8") as f:
            rep = json.load(f)
        f_ = next(r for r in rep["boxes"] if r["box"] == "f")
        self.assertEqual((f_["shift_from"], f_["shift_m"]), ("shrub build", [0.0, 0.0]))
        self.assertEqual(f_["osm_lines"], {"roads": 1, "tracks": 1})
        self.assertGreater(f_["track_line_cells"], 0)
        self.assertEqual(rep["rules"]["classes"]["2"], "tree")
        cls = class_band(os.path.join(m.folder, "f.tif"))
        self.assertTrue((cls[:SIDE, :SIDE] > 0).all())          # the lidar's cells have a class
        self.assertTrue((cls[SIDE:, :] == 0).all() and (cls[:, SIDE:] == 0).all())
        self.assertEqual(int(cls[7, 7]), CR.TREE)

    def test_a_partial_build_and_the_recipes_shift(self):
        archive = self.other("partial")
        recipe = json.loads(json.dumps(self.recipe))
        recipe["boxes"]["d"]["shift"] = [1.0, 0.0]               # the photo sits 1 m east of the lidar
        m = CL.build(archive, recipe, box_ids=["f", "d"], log=quiet)
        self.assertTrue(M.is_partial(m.build))
        self.assertEqual([lay.name for lay in m.layers], ["d", "f"])
        self.assertIsNone(CL.latest(archive))                   # readers skip it
        self.assertEqual(CL.latest(archive, partial=True).build, m.build)
        with open(os.path.join(m.folder, "report.json"), encoding="utf-8") as f:
            rep = {r["box"]: r for r in json.load(f)["boxes"]}
        self.assertEqual((rep["d"]["shift_from"], rep["d"]["shift_m"]), ("recipe", [1.0, 0.0]))
        self.assertEqual(rep["d"]["shrub_build_shift_m"], [0.0, 0.0])
        d = class_band(os.path.join(m.folder, "d.tif"))
        whole = class_band(os.path.join(self.m.folder, "d.tif"))
        self.assertTrue((d[:SIDE, :2] == 0).all() and (d[:SIDE, 2:SIDE + 2] > 0).all())   # moved two cells east
        self.assertTrue((whole[:SIDE, :SIDE] > 0).all() and (whole[:SIDE, SIDE:] == 0).all())
        trees = np.argwhere(whole == CR.TREE)                    # the lidar's tree moves with the classes
        np.testing.assert_array_equal(np.argwhere(d == CR.TREE), trees + [0, 2])
        with self.assertRaises(CL.ClassError):
            CL.build(archive, recipe, box_ids=["f"], build_id="20261016T000000Z", log=quiet)   # a whole build's id
        bad = json.loads(json.dumps(recipe))
        bad["boxes"]["d"]["shift"] = [0.3, 0.0]
        with self.assertRaises(CL.ClassError) as ctx:
            CL.build(archive, bad, box_ids=["d"], build_id="20261016T050000Z-part", log=quiet)
        self.assertIn("multiple of 0.5", str(ctx.exception))

    def test_the_preflight_refuses_before_any_box(self):
        archive = self.other("preflight")
        recipe = json.loads(json.dumps(self.recipe))
        recipe["boxes"]["j"]["photo"] = os.path.join(self.dir, "no-such-photo.tif")
        calls = []
        with mock.patch.object(CL, "classify_box", side_effect=lambda *a, **k: calls.append(a)):
            with self.assertRaises(CL.ClassError) as ctx:
                CL.build(archive, recipe, log=quiet)
        self.assertIn("box j: no file", str(ctx.exception))
        self.assertEqual(calls, [])
        self.assertEqual(M.builds(archive, CL.PRODUCT, partial=True), [])
        self.assertEqual(os.listdir(os.path.join(archive, CL.PRODUCT, CL.STAGING)), [])

    def test_a_stopped_build_leaves_nothing(self):
        archive = self.other("stopped")
        real = CL.classify_box
        seen = []

        def stop_on_the_second(box, *a, **k):
            seen.append(box.id)
            if len(seen) == 2:
                raise SystemExit(143)                            # SIGTERM, as _stopped raises it
            return real(box, *a, **k)
        with mock.patch.object(CL, "classify_box", side_effect=stop_on_the_second):
            with self.assertRaises(SystemExit):
                CL.build(archive, self.recipe, log=quiet)
        self.assertEqual(M.builds(archive, CL.PRODUCT, partial=True), [])
        self.assertEqual(os.listdir(os.path.join(archive, CL.PRODUCT, CL.STAGING)), [])

    def test_one_build_at_a_time(self):
        archive = self.other("locked")
        with CL._Lock(archive):
            with self.assertRaises(CL.ClassError) as ctx:
                CL.build(archive, self.recipe, box_ids=["f"], log=quiet)
        self.assertIn("another class build is running", str(ctx.exception))

    def test_pruning_keeps_the_tiles_build(self):
        from basemap.ground.tests.test_inputs import write_classes
        archive = self.other("prune")
        for b in ("20261014T000000Z", "20261015T000000Z", "20261016T000000Z", "20261016T010000Z-part"):
            write_classes(archive, build=b)
        tiles_dir = self.other("prune-tiles")
        with open(os.path.join(tiles_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"ground": {"inputs": ["ground_classes/a@20261014T000000Z", "soils/ground@1"]}}, f)
        protect = CL.tiles_builds(tiles_dir)
        self.assertEqual(protect, {"20261014T000000Z"})
        gone = CL.prune(archive, keep=1, protect=protect, log=quiet)
        self.assertEqual(gone, ["20261015T000000Z"])
        self.assertEqual(M.builds(archive, CL.PRODUCT, partial=True),
                         ["20261014T000000Z", "20261016T000000Z", "20261016T010000Z-part"])
        with self.assertRaises(CL.ClassError):
            CL.prune(archive, keep=0)
        with self.assertRaises(CL.ClassError):
            CL.build(archive, self.recipe, keep=0, log=quiet)

    def test_the_command_line(self):
        recipe = os.path.join(self.dir, "recipe.json")
        with open(recipe, "w", encoding="utf-8") as f:
            json.dump(self.recipe, f)
        archive = self.other("cli")
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"TVT_ARCHIVE": archive}), contextlib.redirect_stderr(err):
            code = CL.main(["build", "--recipe", recipe, "--box", "f"])
        self.assertEqual(code, 2)
        self.assertIn("a build of some boxes is partial", err.getvalue())
        self.assertFalse(os.path.exists(os.path.join(archive, CL.PRODUCT)))
        other = self.other("cli-other")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"TVT_ARCHIVE": archive}), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = CL.main(["build", "--recipe", recipe, "--box", "f", "--archive", other])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(len(M.builds(other, CL.PRODUCT, partial=True)), 1)


if __name__ == "__main__":
    unittest.main()
