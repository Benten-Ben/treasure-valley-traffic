"""The developed-land worker step (plugins/roads/build/developed.py) on synthetic CDL rasters. Needs the worker image
(GDAL, NumPy); elsewhere it skips, and worker-test counts a skip as a failure:

    data/dev/worker-test-remote.sh <worktree> p8-data plugins.roads.tests.test_developed_build

The raster, all synthetic: 30 x 20 cells of 10 m on an Albers grid offset by 5 m as NASS's is, mostly corn (1), with
a block of class 122 across a window's edge, a block of 124, one 123 cell in a corner, two 122 cells touching only
at a corner, and a block of 121 (developed open space, left out). 63 developed cells, 6,300 m2.
"""

import json
import os
import tempfile
import unittest

try:
    import numpy as np
    from osgeo import gdal, osr

    from plugins.roads.build import developed as B
except ImportError:  # pragma: no cover - outside the worker image
    B = None

from plugins.roads.ingest import developed as D

X0, Y0, RES = -1619505.0, 2463325.0, 10.0          # the north-west corner, on a grid offset by 5 m like NASS's
WIDTH, HEIGHT = 30, 20
CELLS = 63


def pattern():
    a = np.ones((HEIGHT, WIDTH), np.uint8)              # corn
    a[2:6, 2:13] = 122                                  # 44 cells, across the 8-cell windows' edge at column 8
    a[10:14, 20:24] = 124                               # 16
    a[0, 29] = 123                                      # 1, in the corner
    a[18, 10] = a[19, 11] = 122                         # 2, touching only at a corner: two pieces (4-connected)
    a[15:18, 0:6] = 121                                 # developed open space: not developed land
    return a


@unittest.skipUnless(B, "needs the worker image (GDAL, NumPy)")
class DevelopedBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cdl = os.path.join(self.tmp.name, "cdl")
        os.makedirs(self.cdl)

    def raster(self, path, array=None, epsg=5070, bands=1, res=RES):
        array = pattern() if array is None else array
        ds = gdal.GetDriverByName("GTiff").Create(path, array.shape[1], array.shape[0], bands, gdal.GDT_Byte,
                                                  ["TILED=YES", "BLOCKXSIZE=16", "BLOCKYSIZE=16", "COMPRESS=DEFLATE"])
        ds.SetGeoTransform((X0, res, 0.0, Y0, 0.0, -res))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(epsg)
        ds.SetSpatialRef(srs)
        for b in range(1, bands + 1):
            ds.GetRasterBand(b).WriteArray(array)
            ds.GetRasterBand(b).SetNoDataValue(0)
        ds = None
        return path

    def build(self, window, name):
        out = os.path.join(self.tmp.name, "roads", "developed", name)
        return out, B.build(self.cdl, out, window=window, log=lambda m: None)

    def polygons(self, out):
        return [json.loads(g) for _, g in D.pieces(out)]

    @staticmethod
    def area(p):
        def ring(r):
            return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:]))) / 2
        return ring(p["coordinates"][0]) - sum(ring(r) for r in p["coordinates"][1:])

    def test_pieces_cover_exactly_the_developed_cells(self):
        self.raster(os.path.join(self.cdl, "cdl_2024_10m.tif"), np.ones((HEIGHT, WIDTH), np.uint8))
        path = self.raster(os.path.join(self.cdl, "cdl_2025_10m.tif"))              # the newest year is read
        for window, pieces in ((512, 5), (8, 6)):
            with self.subTest(window=window):
                out, doc = self.build(window, f"w{window}")
                self.assertEqual(D.read_build(out), doc)                             # the loader's checks pass
                self.assertEqual((doc["counts"]["pieces"], doc["counts"]["cells"], doc["counts"]["area_km2"]),
                                 (pieces, CELLS, 0.0063))
                self.assertEqual(doc["cdl"]["file"], "cdl_2025_10m.tif")
                self.assertEqual((doc["cdl"]["year"], doc["cdl"]["res_m"], doc["cdl"]["sha256"], doc["cdl"]["credit"],
                                  doc["cdl"]["license"]),
                                 (2025, 10.0, B.sha256_of(path), "USDA NASS Cropland Data Layer 2025", "public domain"))
                self.assertEqual((doc["classes"], doc["srid"]), ([122, 123, 124], 5070))
                self.assertEqual(doc["extent"], [X0, Y0 - HEIGHT * RES, X0 + WIDTH * RES, Y0])
                polygons = self.polygons(out)
                self.assertEqual(sum(self.area(p) for p in polygons), CELLS * RES * RES)
                for p in polygons:
                    xs = [x for r in p["coordinates"] for x, _ in r]
                    ys = [y for r in p["coordinates"] for _, y in r]
                    self.assertTrue(all(isinstance(v, int) and (v - X0) % RES == 0 for v in xs))   # cell edges
                    self.assertTrue(all(isinstance(v, int) and (Y0 - v) % RES == 0 for v in ys))
                    col0, col1 = (min(xs) - X0) / RES, (max(xs) - X0) / RES
                    self.assertEqual(col0 // window, (col1 - 1) // window)                  # within one window
                    self.assertTrue(all(len(r) <= 5 for r in p["coordinates"]))             # turning points only

    def test_one_file_and_the_refusals(self):
        path = self.raster(os.path.join(self.cdl, "cdl_2025_10m.tif"))
        out = os.path.join(self.tmp.name, "one")
        self.assertEqual(B.build(path, out, log=lambda m: None)["counts"]["cells"], CELLS)
        with self.assertRaises(B.BuildError):
            B.build(path, out, log=lambda m: None)                                     # a finished build
        os.makedirs(os.path.join(self.tmp.name, "utm"))
        ones = np.ones((HEIGHT, WIDTH), np.uint8)
        cases = {
            "not on EPSG:5070": self.raster(os.path.join(self.tmp.name, "utm", "cdl_2025_10m.tif"), epsg=32611),
            "not named as a CDL raster": self.raster(os.path.join(self.tmp.name, "developed.tif")),
            "named 30 m, with 10 m cells": self.raster(os.path.join(self.tmp.name, "cdl_2025_30m.tif")),
            "no developed cells": self.raster(os.path.join(self.tmp.name, "cdl_2023_10m.tif"), ones),
        }
        two = os.path.join(self.tmp.name, "two")
        os.makedirs(two)
        cases["two bands"] = self.raster(os.path.join(two, "cdl_2025_10m.tif"), bands=2)
        cases["a folder without rasters"] = os.path.join(self.tmp.name, "roads")
        os.makedirs(cases["a folder without rasters"])
        for what, p in cases.items():
            with self.subTest(what):
                with self.assertRaises(B.BuildError):
                    B.build(p, os.path.join(self.tmp.name, "out", what.replace(" ", "-")), log=lambda m: None)

    def test_main(self):
        self.raster(os.path.join(self.cdl, "cdl_2025_10m.tif"))
        out = os.path.join(self.tmp.name, "main")
        self.assertEqual(B.main(["--cdl", self.cdl, "--out", out, "--window", "8"]), 0)
        self.assertEqual(D.read_build(out)["counts"]["pieces"], 6)
        self.assertEqual(B.main(["--cdl", self.cdl, "--out", out]), 1)


if __name__ == "__main__":
    unittest.main()
