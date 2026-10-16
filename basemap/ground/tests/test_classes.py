"""The box classes' reading and writing (classes.py) on synthetic files: the frames, July's cells, the lines, the
ground brightness from a synthetic point cloud, and the product's GeoTIFF and manifest as the ground reads them.
Needs the worker image (GDAL, PDAL, NumPy, SciPy): the tests skip elsewhere, and in the worker image a skip counts
as a failure."""

import json
import os
import shutil
import tempfile
import unittest

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

    def test_box_grid_must_be_the_box_window(self):
        w = BOX.window()
        CL.check_box_grid(BOX, lidar_grid(rows=w.height, cols=w.width))
        with self.assertRaises(CL.ClassError):
            CL.check_box_grid(BOX, lidar_grid(x0=w.west + 0.5, rows=w.height, cols=w.width))


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


if __name__ == "__main__":
    unittest.main()
