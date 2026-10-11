"""The crop-fields build (plugins/farm/build/build.py) on synthetic inputs. Needs the worker image (GDAL, NumPy,
SciPy); elsewhere it skips, and worker-test counts a skip as a failure:

    data/dev/worker-test-remote.sh <worktree> p3-data plugins.farm.tests.test_build

The inputs, all synthetic: the three-field GeoPackage (synthetic.py) in NASS's Albers; CDL rasters for 2025 (10 m)
and 2023 (30 m) on an Albers grid, painted with each field's code, a strip of alfalfa across F1's west end, a 1 ha
block of wheat outside every field and a 3 x 3-cell speck of corn; and a July NDVI median on a window of the ground's
10 m grid (F1 green, F2 bare, F3 growing, the rest dry, with a hole of no data), tagged with its July 2025 views as the
Sentinel-2 composite tags its median.
"""

import json
import os
import tempfile
import unittest

try:
    import numpy as np
    from osgeo import gdal, ogr, osr

    from basemap.ground import grid, tif
    from basemap.ground import rasterize as R
    from plugins.farm.build import build as B
except ImportError:  # pragma: no cover - outside the worker image
    B = None

from plugins.farm.tests import synthetic as S

ALBERS = (S.X0 - 1000, S.Y0 + 1300)       # the CDL rasters' upper-left corner (Albers metres)
WHEAT = (S.X0 + 1400, S.Y0 + 400, 100)    # a 100 m square of wheat outside every field: 1 ha, a cluster
SPECK = (S.X0 + 1400, S.Y0 - 200, 30)     # 30 m of corn: 9 cells at 10 m, under 0.5 ha
NDVI = {S.F1: 8500, S.F2: 1000, S.F3: 4500}
BACKGROUND_NDVI = 2000
ACQUISITIONS = "2025-07-01 Sentinel-2C R027, 2025-07-13 Sentinel-2A R027, 2025-07-26 Sentinel-2A R070"


@unittest.skipUnless(B, "needs the worker image (GDAL, NumPy, SciPy)")
class BuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = cls.tmp.name
        cls.rows = S.fields()
        cls.gpkg = S.write_gpkg(os.path.join(t, "csb.gpkg"), cls.rows)
        cls.cdl = os.path.join(t, "cdl")
        os.makedirs(cls.cdl)
        cls.albers = osr.SpatialReference()
        cls.albers.ImportFromEPSG(5070)
        cls.utm_fields = cls._utm_fields(os.path.join(t, "fields_utm.fgb"))
        cls._cdl(2025, 10, {S.F1: 1, S.F2: 123, S.F3: 122}, strip=True)
        cls._cdl(2023, 30, {S.F1: 24, S.F2: 121, S.F3: 41})
        cls.window = cls._ndvi(os.path.join(t, "ndvi.tif"))
        cls.ndvi = os.path.join(t, "ndvi.tif")
        cls.out = os.path.join(t, "farm", "build", "20261011T120000Z")
        cls.doc = B.build(cls.gpkg, cls.cdl, cls.ndvi, cls.out, log=lambda m: None)
        cls.small = os.path.join(t, "farm", "build", "20261011T120001Z")
        B.build(cls.gpkg, cls.cdl, cls.ndvi, cls.small, window_cells=7, log=lambda m: None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def _utm_fields(cls, path):
        """The fields on the ground grid's CRS (null shift), with n and the CSBID, as the build sees them."""
        ct = osr.CoordinateTransformation(R.srs_of(cls.albers), R.srs_of(grid.CRS))
        ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(path)
        lyr = ds.CreateLayer("f", R.srs_of(grid.CRS), ogr.wkbMultiPolygon)
        lyr.CreateField(ogr.FieldDefn("n", ogr.OFTInteger))
        for n, r in enumerate(cls.rows, 1):
            g = ogr.CreateGeometryFromWkb(S.wkb_multipolygon(r["_polygons"]))
            if not g.IsValid():
                g = g.MakeValid()
            g.Transform(ct)
            f = ogr.Feature(lyr.GetLayerDefn())
            f.SetField("n", n)
            f.SetGeometry(g)
            lyr.CreateFeature(f)
        ds = None
        return path

    @classmethod
    def _cdl(cls, year, res, codes, strip=False):
        w, h = int(3200 / res), int(2300 / res)
        path = os.path.join(cls.cdl, f"cdl_{year}_{res}m.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, w, h, 1, gdal.GDT_Byte)
        ds.SetGeoTransform((ALBERS[0], res, 0, ALBERS[1], 0, -res))
        ds.SetProjection(cls.albers.ExportToWkt())
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(0)
        arr = np.full((h, w), 152, np.uint8)                     # shrubland around the fields
        mem = R._mem_vector()
        lyr = mem.CreateLayer("f", cls.albers, ogr.wkbMultiPolygon)
        lyr.CreateField(ogr.FieldDefn("code", ogr.OFTInteger))
        for r in cls.rows:
            g = ogr.CreateGeometryFromWkb(S.wkb_multipolygon(r["_polygons"]))
            f = ogr.Feature(lyr.GetLayerDefn())
            f.SetField("code", codes[r["CSBID"]])
            f.SetGeometry(g.MakeValid() if not g.IsValid() else g)
            lyr.CreateFeature(f)
        band.WriteArray(arr)
        gdal.RasterizeLayer(ds, [1], lyr, options=["ATTRIBUTE=code"])
        arr = band.ReadAsArray()

        def cells(x, y, size):
            c0, r0 = int((x - ALBERS[0]) / res), int((ALBERS[1] - (y + size)) / res)
            return slice(r0, r0 + max(1, int(size / res))), slice(c0, c0 + max(1, int(size / res)))

        if strip:   # alfalfa across F1's west 40 m: CSB says corn, the pixels disagree there
            c0, c1 = int((S.X0 - ALBERS[0]) / res), int((S.X0 + 40 - ALBERS[0]) / res)
            r0, r1 = int((ALBERS[1] - (S.Y0 + 100)) / res), int((ALBERS[1] - S.Y0) / res)
            arr[r0:r1, c0:c1] = 36
            arr[cells(*WHEAT)] = 24
            arr[cells(*SPECK)] = 1
        band.WriteArray(arr)
        ds = None

    @classmethod
    def _ndvi(cls, path):
        ds = ogr.Open(cls.utm_fields)
        w, e, s, n = ds.GetLayer(0).GetExtent()
        win = grid.window((w - 600, s - 600, e + 600, n + 600), 10.0)
        ids = R.rasterize(win, cls.utm_fields, attribute="n", dtype="int32")
        arr = np.full(win.shape, BACKGROUND_NDVI, np.int16)
        for k, r in enumerate(cls.rows, 1):
            arr[ids == k] = NDVI[r["CSBID"]]
        arr[0:3, 0:3] = B.NDVI_NODATA
        out = gdal.GetDriverByName("GTiff").Create(path, win.width, win.height, 1, gdal.GDT_Int16)
        out.SetGeoTransform(win.transform)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32611)
        out.SetProjection(srs.ExportToWkt())
        out.GetRasterBand(1).SetNoDataValue(B.NDVI_NODATA)
        out.GetRasterBand(1).WriteArray(arr)
        out.SetMetadata({"ACQUISITIONS": ACQUISITIONS,
                         "CREDIT": "Contains modified Copernicus Sentinel data 2025, processed by Treasure Valley Traffic"})
        out = None
        return win

    def tagged(self, name, tags):
        """A copy of the NDVI raster with these tags instead of its own."""
        path = os.path.join(self.tmp.name, name)
        src = gdal.Open(self.ndvi)
        ds = gdal.GetDriverByName("GTiff").Create(path, src.RasterXSize, src.RasterYSize, 1, gdal.GDT_Int16)
        ds.SetGeoTransform(src.GetGeoTransform())
        ds.SetProjection(src.GetProjection())
        ds.GetRasterBand(1).SetNoDataValue(B.NDVI_NODATA)
        ds.GetRasterBand(1).WriteArray(src.GetRasterBand(1).ReadAsArray())
        if tags:
            ds.SetMetadata(tags)
        ds = None
        return path

    def fields(self, folder=None):
        with open(os.path.join(folder or self.out, "fields.jsonl")) as f:
            return {r["field_id"]: r for r in map(json.loads, f)}

    def cover(self, folder=None):
        ds = gdal.Open(os.path.join(folder or self.out, "crop_cover.tif"))
        return ds, [ds.GetRasterBand(b).ReadAsArray() for b in (1, 2, 3)]

    def masks(self):
        inside = R.rasterize(self.window, self.utm_fields, attribute="n", dtype="int32")
        touched = R.rasterize(self.window, self.utm_fields, attribute="n", dtype="int32", all_touched=True)
        return inside, touched

    def test_the_build_folder(self):
        names = sorted(n for n in os.listdir(self.out))
        self.assertEqual(names, ["build.json", "crop_cover.tif", "fields.jsonl"])     # the work folder is gone
        d = self.doc
        self.assertEqual((d["format"], d["build_id"], d["cover_year"], d["july_year"]),
                         (B.FORMAT, "20261011T120000Z", 2025, 2025))
        self.assertEqual((d["inputs"]["ndvi"]["year"], d["inputs"]["ndvi"]["acquired"]),
                         (2025, ["2025-07-01", "2025-07-26"]))
        self.assertEqual(d["credit"], "USDA NASS Crop Sequence Boundaries 2018-2025; USDA NASS Cropland Data Layer "
                                      "2025; Contains modified Copernicus Sentinel data 2025")
        self.assertEqual(d["counts"]["fields"], 3)
        self.assertEqual(d["inputs"]["csb"]["sha256"], B.sha256_of(self.gpkg))
        self.assertEqual(sorted(d["inputs"]["cdl"]), ["2023", "2025"])
        self.assertEqual(d["files"]["crop_cover.tif"]["sha256"], B.sha256_of(os.path.join(self.out, "crop_cover.tif")))
        self.assertEqual(d["grid"], {"crs": "EPSG:32611", "res": 10.0, "west": self.window.west,
                                     "north": self.window.north, "width": self.window.width,
                                     "height": self.window.height})
        with self.assertRaises(B.BuildError):
            B.build(self.gpkg, self.cdl, self.ndvi, self.out, log=lambda m: None)    # finished: refused

    def test_agreement(self):
        f = self.fields()
        a1 = f[S.F1]["agree"]
        self.assertAlmostEqual(a1["2025"], 0.9, delta=0.03)       # the alfalfa strip is a tenth of F1
        self.assertEqual(a1["2023"], 1.0)
        self.assertEqual(f[S.F1]["px"]["2025"], 400)
        self.assertEqual(f[S.F2]["agree"]["2025"], 1.0)
        self.assertEqual(f[S.F3]["agree"]["2025"], 1.0)
        self.assertIn("2023", f[S.F2]["agree"])
        self.assertAlmostEqual(self.doc["counts"]["agreement_share"]["2025"], 860 / 900, delta=0.02)

    def test_july_state_per_field(self):
        f = self.fields()
        self.assertEqual((f[S.F1]["july"]["state"], f[S.F1]["july"]["ndvi"], f[S.F1]["july"]["year"]),
                         ("green", 0.85, 2025))
        self.assertEqual(f[S.F2]["july"]["state"], "bare")
        self.assertEqual(f[S.F3]["july"]["state"], "growing")
        self.assertGreater(f[S.F1]["july"]["px"], 300)
        self.assertEqual(self.doc["counts"]["july"], {"green": 1, "growing": 1, "bare": 1, "none": 0})

    def test_crop_cover_is_on_the_ground_grid(self):
        ds, _ = self.cover()
        self.assertEqual(ds.GetGeoTransform(), self.window.transform)
        self.assertEqual((ds.RasterXSize, ds.RasterYSize, ds.RasterCount), (self.window.width, self.window.height, 3))
        self.assertEqual([ds.GetRasterBand(b).DataType for b in (1, 2, 3)], [gdal.GDT_Byte] * 3)
        self.assertEqual([ds.GetRasterBand(b).GetDescription() for b in (1, 2, 3)], ["group", "state", "confidence"])
        h = tif.read_header(os.path.join(self.out, "crop_cover.tif"))
        self.assertEqual((h.epsg, h.width, h.height, h.sample_types), (32611, self.window.width, self.window.height,
                                                                       ("uint8",) * 3))
        self.assertIn("Copernicus", ds.GetMetadataItem("CREDIT"))

    def test_crop_cover_classes(self):
        _, (group, state, conf) = self.cover()
        inside, touched = self.masks()
        f1 = inside == 1
        lo = np.minimum.reduce([np.roll(np.roll(inside, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
        hi = np.maximum.reduce([np.roll(np.roll(inside, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
        interior = (inside == 1) & (lo == 1) & (hi == 1)
        self.assertTrue(interior.any())
        # F1's interior: corn, sure, green
        self.assertTrue((group[interior] == 1).all() and (conf[interior] == 1).all() and (state[interior] == 1).all())
        # F1's edge band: corn where the CDL agrees, nothing where the alfalfa strip is
        edge = (touched == 1) & ~interior
        self.assertTrue(set(np.unique(conf[edge])) <= {0, 2})
        self.assertGreater((conf[edge] == 2).sum(), 10)
        self.assertGreater((conf[edge] == 0).sum(), 0)
        self.assertTrue((group[edge & (conf == 2)] == 1).all())
        # F2 and F3 are developed in 2025: not crop
        self.assertFalse((group[(touched == 2) | (touched == 3)] > 0).any())
        # outside every field: the 1 ha wheat block is a cluster (grain, bare in July), the corn speck isn't
        out = (touched == 0) & (conf == 3)
        self.assertAlmostEqual(int(out.sum()), 100, delta=25)
        self.assertTrue((group[out] == 3).all() and (state[out] == 3).all())
        self.assertFalse(((conf == 3) & (group == 1)).any())
        self.assertFalse((conf[touched > 0] == 3).any())
        self.assertTrue((state[group == 0] == 0).all() and (conf[group == 0] == 0).all())
        cells = self.doc["counts"]["cover_cells"]
        self.assertEqual(sorted(cells), ["corn", "grain"])

    def test_windows_dont_change_the_result(self):
        """Seven-cell windows (with their 500 m halo) give the same cover and stats as one window."""
        _, big = self.cover()
        _, small = self.cover(self.small)
        for a, b in zip(big, small):
            np.testing.assert_array_equal(a, b)
        self.assertEqual(self.fields(), self.fields(self.small))

    def test_medians(self):
        ns = np.array([1, 1, 1, 2, 2, 3, 1], np.int32)
        vs = np.array([5, 1, 3, 10, 20, 7, 100], np.int16)
        med, count = B.medians(ns, vs, 4)
        self.assertEqual(count.tolist(), [0, 4, 2, 1, 0])
        self.assertEqual(med[1:4].tolist(), [4.0, 15.0, 7.0])
        self.assertTrue(np.isnan(med[0]) and np.isnan(med[4]))

    def test_the_july_year_is_the_ndvis(self):
        """The state's year comes from the NDVI's tags, not the crop year; --july-year only for an untagged raster."""
        def year(tags, given=None):
            return B.july_year_of(gdal.Open(self.tagged("y.tif", tags)), given)

        self.assertEqual(year({"ACQUISITIONS": ACQUISITIONS}), (2025, ["2025-07-01", "2025-07-26"]))
        self.assertEqual(year({"ACQUISITIONS": ACQUISITIONS}, 2025)[0], 2025)
        self.assertEqual(year({"CREDIT": "Contains modified Copernicus Sentinel data 2024"}), (2024, None))
        self.assertEqual(year({}, 2023), (2023, None))
        for tags, given in (({"ACQUISITIONS": ACQUISITIONS}, 2026),                    # disagrees with the tags
                            ({}, None),                                                 # says nothing
                            ({"ACQUISITIONS": "2025-04-04 Sentinel-2A R027"}, None),    # an April median
                            ({"ACQUISITIONS": "2024-07-09 S2B, 2025-07-11 S2C"}, None),  # two years
                            ({"ACQUISITIONS": "2025-07-32 S2A"}, None)):                # not a date
            with self.subTest(tags=tags, given=given), self.assertRaises(B.BuildError):
                year(tags, given)

    def test_a_newer_crop_year_keeps_its_julys_year(self):
        """A July 2024 median under 2025's crops: every field's July, the CREDIT tag and build.json say 2024."""
        ndvi = self.tagged("july2024.tif", {"ACQUISITIONS": ACQUISITIONS.replace("2025-", "2024-")})
        out = os.path.join(self.tmp.name, "farm", "build", "20261011T120002Z")
        doc = B.build(self.gpkg, self.cdl, ndvi, out, log=lambda m: None)
        self.assertEqual((doc["cover_year"], doc["july_year"]), (2025, 2024))
        self.assertEqual({r["july"]["year"] for r in self.fields(out).values()}, {2024})
        credit = gdal.Open(os.path.join(out, "crop_cover.tif")).GetMetadataItem("CREDIT")
        self.assertTrue(credit.endswith("Cropland Data Layer 2025; Contains modified Copernicus Sentinel data 2024"),
                        credit)
        bad = os.path.join(self.tmp.name, "farm", "build", "20261011T120003Z")
        with self.assertRaises(B.BuildError):
            B.build(self.gpkg, self.cdl, self.tagged("april.tif", {"ACQUISITIONS": "2025-04-04 S2A"}), bad,
                    log=lambda m: None)
        self.assertFalse(os.path.exists(bad))                # refused before anything was written

    def test_refuses_an_ndvi_off_the_grid(self):
        path = os.path.join(self.tmp.name, "off.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 10, 10, 1, gdal.GDT_Int16)
        ds.SetGeoTransform((self.window.west + 5, 10, 0, self.window.north, 0, -10))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32611)
        ds.SetProjection(srs.ExportToWkt())
        ds = None
        with self.assertRaises(B.BuildError):
            B.area_of(gdal.Open(path))


if __name__ == "__main__":
    unittest.main()
