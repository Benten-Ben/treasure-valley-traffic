"""The presence check's worker step (plugins/water/build/presence.py, issue #309) on invented inputs: the field and
level rules, the share arithmetic, and the whole measurement on a small synthetic NWI cut, CSB cut, CDL years and mask
layers. The raster classes need the worker image (GDAL, NumPy): they skip elsewhere, and in the worker image a skip
counts as a failure.

    /srv/tvt/work/bin/worker-test -C <checkout> discover -s plugins/water/tests -t . -p 'test_presence.py'
"""

import importlib.util
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

try:
    import numpy as np
    from osgeo import gdal, ogr, osr
    from basemap.ground import grid as G, rasterize as R
    HAVE = True
except ImportError:                                  # outside the worker image
    np = None
    HAVE = False

from plugins.water.ingest import wetlands
from plugins.water.tests import synthetic as S
from plugins.water.tests.test_wetlands import albers_gpkg, wetland

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(os.path.dirname(HERE), "build", "presence.py")


def load():
    spec = importlib.util.spec_from_file_location("water_presence", PATH)    # soils has a prepare.py too: no clashes
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load()
X0, Y0 = 551000.0, 4822000.0                         # in box d, on every level of the grid


class RulesTest(unittest.TestCase):
    def test_a_field_cropped_six_of_eight_years_is_cultivated(self):
        self.assertEqual(P.field_kind([1, 36, 61, 24, 1, 36, 176, 176]), P.FIELD_CULTIVATED)
        self.assertEqual(P.field_kind([1, 36, 61, 24, 1, 176, 176, 176]), P.FIELD_NONE)     # five crops, three pasture

    def test_alfalfa_and_fallow_are_crops_but_hay_and_pasture_are_not(self):
        for code in (36, 61, 1, 24, 41, 49, 69, 205, 254):
            self.assertIn(code, P.CROPS, code)
        for code in (37, 176, 121, 122, 190, 195, 111, 141, 152, 0, 62, 63, 87, 88):
            self.assertNotIn(code, P.CROPS, code)

    def test_a_field_in_hay_or_pasture_four_of_eight_years_is_hay_pasture(self):
        self.assertEqual(P.field_kind([176, 176, 37, 176, 1, 1, 1, 36]), P.FIELD_HAY)
        self.assertEqual(P.field_kind([176, 176, 37, 1, 1, 1, 36, 36]), P.FIELD_NONE)

    def test_cultivated_wins_only_with_six_years_so_the_two_never_collide(self):
        for cult in range(9):
            codes = [1] * cult + [176] * (8 - cult)
            kind = P.field_kind(codes)
            self.assertFalse(cult >= 6 and kind != P.FIELD_CULTIVATED)
            self.assertFalse(cult < 6 and kind == P.FIELD_CULTIVATED)

    def test_missing_years_count_for_nothing(self):
        self.assertEqual(P.field_kind([1, 1, 1, 1, 1, None, None, 0]), P.FIELD_NONE)
        self.assertEqual(P.field_kind([1, 1, 1, 1, 1, 1, None, 0]), P.FIELD_CULTIVATED)

    def test_the_finest_level_that_keeps_a_window_under_3000_cells(self):
        self.assertEqual(P.pick_level(50, 80), 0.5)
        self.assertEqual(P.pick_level(1500, 100), 0.5)
        self.assertEqual(P.pick_level(1501, 100), 2.0)
        self.assertEqual(P.pick_level(6000, 6000), 2.0)
        self.assertEqual(P.pick_level(6001, 10), 10.0)
        self.assertEqual(P.pick_level(60000, 60000), 10.0)

    def test_keys_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "keys.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# old and interim\nA\n\nB#2\nA\n  C  \n")
            self.assertEqual(P.read_keys(path), ["A", "B#2", "C"])

    def test_share_is_held_to_0_to_1_and_rounded(self):
        self.assertEqual(P.share(1, 3), 0.3333)
        self.assertEqual(P.share(5, 4), 1.0)
        self.assertEqual(P.share(0, 0), 0.0)


@unittest.skipUnless(HAVE, "needs the worker image (GDAL, NumPy)")
class SharesTest(unittest.TestCase):
    def test_each_share_is_over_the_polygons_cells_only(self):
        poly = np.zeros((4, 4), bool)
        poly[:, :2] = True                                       # 8 cells
        built = np.zeros((4, 4), bool)
        built[:2, :] = True                                      # 4 of the 8 are inside the polygon
        ones = np.ones((4, 4), bool)
        none = np.zeros((4, 4), bool)
        kind = np.zeros((4, 4), np.uint8)
        kind[:, 1] = P.FIELD_CULTIVATED                          # 4 of 8
        kind[0, 0] = P.FIELD_HAY                                 # 1 of 8
        wet = np.zeros((4, 4), bool)
        wet[3, 0] = True
        got = P.shares_of(poly, built, ones, ones, wet, none, kind)
        self.assertEqual(got, {"built": 0.5, "developed": 1.0, "cultivated": 0.5, "hay_pasture": 0.125,
                               "cdl_wetland": 0.125})

    def test_developed_needs_both_years_and_wetland_needs_either(self):
        poly = np.ones((2, 2), bool)
        a = np.array([[True, True], [False, False]])
        b = np.array([[True, False], [True, False]])
        kind = np.zeros((2, 2), np.uint8)
        none = np.zeros((2, 2), bool)
        got = P.shares_of(poly, none, a, b, a, b, kind)
        self.assertEqual((got["developed"], got["cdl_wetland"]), (0.25, 0.75))


def utm_to_albers():
    return osr.CoordinateTransformation(R.srs_of(G.CRS), R.srs_of("EPSG:5070"))


def albers_square(ct, x0, y0, x1, y1):
    """An NWI-style MultiPolygon WKB in Albers for a rectangle given in grid metres (corner offsets from X0, Y0)."""
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
        ring.AddPoint_2D(X0 + x, Y0 + y)
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(ring)
    poly.Transform(ct)
    multi = ogr.Geometry(ogr.wkbMultiPolygon)
    multi.AddGeometry(poly)
    return bytes(multi.ExportToIsoWkb())


def write_cdl(path, classes):
    """A 10 m CDL tile on the grid's CRS over X0 - 500 .. X0 + 500, Y0 - 500 .. Y0 + 500: `classes` is {(x0, y0, x1, y1):
    class} in metres from X0, Y0."""
    n = 100
    a = np.zeros((n, n), np.uint8)
    for (x0, y0, x1, y1), c in classes.items():
        c0, c1 = int((x0 + 500) // 10), int((x1 + 500) // 10)
        r0, r1 = int((500 - y1) // 10), int((500 - y0) // 10)
        a[r0:r1, c0:c1] = c
    ds = gdal.GetDriverByName("GTiff").Create(path, n, n, 1, gdal.GDT_Byte)
    ds.SetGeoTransform((X0 - 500, 10, 0, Y0 + 500, 0, -10))
    ds.SetProjection(R.srs_of(G.CRS).ExportToWkt())
    ds.GetRasterBand(1).WriteArray(a)
    ds = None


def write_csb(path, ct, fields):
    """A CSB cut in Albers (layer csb_mapbox, CDL2018..CDL2025): fields is [(rect, [eight codes])]."""
    drv = ogr.GetDriverByName("GPKG")
    ds = drv.CreateDataSource(path)
    lyr = ds.CreateLayer("csb_mapbox", R.srs_of("EPSG:5070"), ogr.wkbMultiPolygon)
    for y in range(2018, 2026):
        lyr.CreateField(ogr.FieldDefn(f"CDL{y}", ogr.OFTInteger))
    for (x0, y0, x1, y1), codes in fields:
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetGeometry(ogr.CreateGeometryFromWkb(albers_square(ct, x0, y0, x1, y1)))
        for y, c in zip(range(2018, 2026), codes):
            f.SetField(f"CDL{y}", c)
        lyr.CreateFeature(f)
    ds = None


def write_layer(path, rects):
    """A FlatGeobuf of rectangles (grid metres from X0, Y0) in the grid's CRS: stands in for a mask v0 layer."""
    ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(path)
    lyr = ds.CreateLayer("layer", R.srs_of(G.CRS), ogr.wkbMultiPolygon)
    for x0, y0, x1, y1 in rects:
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
            ring.AddPoint_2D(X0 + x, Y0 + y)
        poly = ogr.Geometry(ogr.wkbPolygon)
        poly.AddGeometry(ring)
        f = ogr.Feature(lyr.GetLayerDefn())
        multi = ogr.Geometry(ogr.wkbMultiPolygon)
        multi.AddGeometry(poly)
        f.SetGeometry(multi)
        lyr.CreateFeature(f)
    ds = None


@unittest.skipUnless(HAVE, "needs the worker image (GDAL, NumPy)")
class MeasureTest(unittest.TestCase):
    """The wetland is the square 0..100 m, 0..100 m. A roof covers its west fifth (x 0..20), a road its north tenth
    (y 90..100, overlapping the roof's corner), paving a 10 x 10 m patch (x 50..60, y 40..50). CDL 2024 and 2025:
    developed in the south-east quarter (x 50..100, y 0..50) in both years, but only 2025 over the north-east
    quarter; woody wetlands in 2024 over the strip x 20..30. A crop field (codes all 1) takes x 30..60, y 0..100; a
    pasture field takes x 60..100, y 50..100; a field cropped 5 of 8 years takes x 60..100, y 0..50."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        cls.ct = utm_to_albers()
        write_cdl(os.path.join(d, "cdl_2024_10m.tif"), {(50, 0, 100, 50): 123, (20, 0, 30, 100): 190,
                                                               (0, 0, 20, 100): 121})
        write_cdl(os.path.join(d, "cdl_2025_10m.tif"), {(50, 0, 100, 50): 124, (50, 50, 100, 100): 122})
        write_csb(os.path.join(d, "csb.gpkg"), cls.ct, [((30, 0, 60, 100), [1] * 8), ((60, 50, 100, 100), [176] * 8),
                                                        ((60, 0, 100, 50), [1, 1, 1, 1, 1, 176, 176, 176])])
        for name, rects in (("roofs", [(0, 0, 20, 100)]), ("roads", [(0, 90, 100, 100)]),
                            ("paving", [(50, 40, 60, 50)])):
            write_layer(os.path.join(d, name + ".fgb"), rects)
        sq = albers_square(cls.ct, 0, 0, 100, 100)
        albers_gpkg(os.path.join(d, "nwi.gpkg"),
                    [wetland("A", "PEM1C", sq), wetland("A", "PEM1Cx", albers_square(cls.ct, 200, 0, 250, 50)),
                     wetland("B", "PSS1A", albers_square(cls.ct, -400, -400, -300, -300))], [])
        cls.dir = d

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def layer_path(self, name):
        return os.path.join(self.dir, name + ".fgb")

    def built(self, target):
        out = None
        for name in ("roofs", "roads", "paving"):
            a = R.rasterize(target, self.layer_path(name)).astype(bool)
            out = a if out is None else out | a
        return out

    def inputs(self):
        _ds, fields, counts = P.csb_fields(os.path.join(self.dir, "csb.gpkg"))
        self._ds = _ds
        return P.Inputs(self.built, P.Cdl(os.path.join(self.dir, "cdl_2024_10m.tif")),
                        P.Cdl(os.path.join(self.dir, "cdl_2025_10m.tif")), fields), counts

    def test_csb_fields_keep_only_cultivated_and_hay_fields(self):
        _inputs, counts = self.inputs()
        self.assertEqual(counts, {"fields": 3, "cultivated": 1, "hay_pasture": 1})

    def test_shares_of_the_square(self):
        inputs, _ = self.inputs()
        wkb = albers_square(self.ct, 0, 0, 100, 100)
        got, res = P.measure(wkb, inputs, osr.CoordinateTransformation(R.srs_of("EPSG:5070"), R.srs_of(G.CRS)))
        self.assertEqual(res, 0.5)
        # built: roof 20 x 100 + road 80 x 10 (x 20..100) + paving 100 m2 = 2,000 + 800 + 100 of 10,000
        self.assertAlmostEqual(got["built"], 0.29, places=3)
        self.assertAlmostEqual(got["developed"], 0.25, places=3)         # the south-east quarter in both years
        self.assertAlmostEqual(got["cdl_wetland"], 0.10, places=3)       # x 20..30
        self.assertAlmostEqual(got["cultivated"], 0.30, places=3)        # x 30..60 of 100
        self.assertAlmostEqual(got["hay_pasture"], 0.20, places=3)       # x 60..100, y 50..100

    def test_class_121_counts_for_nothing(self):
        inputs, _ = self.inputs()
        wkb = albers_square(self.ct, 0, 0, 20, 100)                      # all CDL 121 in 2024, nothing in 2025
        got, _res = P.measure(wkb, inputs, osr.CoordinateTransformation(R.srs_of("EPSG:5070"), R.srs_of(G.CRS)))
        self.assertEqual(got["developed"], 0.0)
        self.assertEqual(got["built"], 1.0)

    def test_a_polygon_off_every_input_measures_nothing(self):
        inputs, _ = self.inputs()
        wkb = albers_square(self.ct, 200, 0, 250, 50)
        got, _res = P.measure(wkb, inputs, osr.CoordinateTransformation(R.srs_of("EPSG:5070"), R.srs_of(G.CRS)))
        self.assertEqual(got, {"built": 0.0, "developed": 0.0, "cultivated": 0.0, "hay_pasture": 0.0,
                               "cdl_wetland": 0.0})

    def test_run_writes_the_file_nwi_presence_reads_for_the_keys_asked(self):
        keys = os.path.join(self.dir, "keys.txt")
        with open(keys, "w", encoding="utf-8") as f:
            f.write("A\nA#2\n")
        out = os.path.join(self.dir, "shares.json")
        m = SimpleNamespace(build="20261011T144701Z", layer=lambda n: {"sha256": "ab" * 32})
        args = SimpleNamespace(nwi=os.path.join(self.dir, "nwi.gpkg"), csb=os.path.join(self.dir, "csb.gpkg"),
                               cdl_dir=self.dir, archive=self.dir, keys=keys, out=out, limit=None)
        lines = []
        P.run(args, log=lines.append, mask_opener=lambda _archive: (self.built, m))
        computed_on, inputs, rows = wetlands.read_shares(out)
        self.assertEqual([r[0] for r in rows], ["A", "A#2"])             # B was not asked for
        by = {r[0]: r for r in rows}
        self.assertAlmostEqual(by["A"][1], 0.29, places=3)               # built
        self.assertEqual(by["A#2"][1:6], (0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertEqual(inputs["mask"]["build"], "20261011T144701Z")
        self.assertEqual(inputs["nwi"]["measured"], 2)
        self.assertEqual(inputs["levels"], {"0.5 m": 2})
        with open(out, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["computed_on"], str(computed_on))

    def test_a_key_the_cut_does_not_hold_is_refused(self):
        keys = os.path.join(self.dir, "keys-bad.txt")
        with open(keys, "w", encoding="utf-8") as f:
            f.write("A\nZ\n")
        args = SimpleNamespace(nwi=os.path.join(self.dir, "nwi.gpkg"), csb=os.path.join(self.dir, "csb.gpkg"),
                               cdl_dir=self.dir, archive=self.dir, keys=keys, out=None, limit=None)
        with self.assertRaises(SystemExit):
            P.run(args, log=lambda *_: None, mask_opener=lambda _a: (self.built, None))


if __name__ == "__main__":
    unittest.main()
