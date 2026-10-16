"""The painter (paint.py) on a synthetic world: soils, a palette, mask v0's surfaces, a crop cover and fields, and box
f's classes. Needs the worker image (GDAL, NumPy, SciPy): the tests skip elsewhere, and in the worker image a skip
counts as a failure."""

import json
import os
import shutil
import tempfile
import unittest

try:
    import numpy as np
    from osgeo import gdal, osr
    from basemap.ground import classrules as CR
    from basemap.ground import colour as K
    from basemap.ground import paint
    from basemap.ground.tests.test_rasterize import square, write_layer
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import grid as G

X_EDGE = 547000.0           # soil A west of it, B east
N0, N1 = 4801300.0, 4802700.0
WATER = (546400.0, 4802500.0, 40.0)                   # a SSURGO Water unit inside A
FIELD = (546000.0, 4801400.0, 400.0)                  # a corn field (crop group 1), rows north-south
BOX = G.box("f")
ROAD_Y = 4802000.0                                    # a road across box f, 8 m wide


def rect(w, s, e, n):
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, SciPy)")
class TestPainter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        d = cls.dir
        bw, bs, be, bn = BOX.utm
        soils = write_layer(os.path.join(d, "ground.fgb"), 32611, [
            (rect(545000, N0 - 200, X_EDGE, N1 + 200), {"id": 1, "ground_type": 1}),
            (rect(X_EDGE, N0 - 200, bw - 100, N1 + 200), {"id": 2, "ground_type": 2}),
            (square(WATER[0], WATER[1], WATER[2]), {"id": 3, "ground_type": 3}),
            (rect(bw - 100, bs - 100, be + 100, bn + 100), {"id": 4, "ground_type": 4})])
        types = [{"gid": 1, "id": "a:loam", "misc": None}, {"gid": 2, "id": "b:clay", "misc": None},
                 {"gid": 3, "id": "water", "misc": "water"}, {"gid": 4, "id": "c:sandy-loam", "misc": None}]
        with open(os.path.join(d, "ground_types.json"), "w") as f:
            json.dump({"schema": "soils.ground_types/1", "types": types}, f)
        pal = {"schema": "soils.palette/1", "types": [
            {"gid": 1, "id": "a:loam", "status": "measured", "misc": None, "lab_med": [0.80, 0.01, 0.04]},
            {"gid": 2, "id": "b:clay", "status": "none", "misc": None},
            {"gid": 4, "id": "c:sandy-loam", "status": "measured", "misc": None, "lab_med": [0.60, 0.01, 0.04]}]}
        with open(os.path.join(d, "palette.json"), "w") as f:
            json.dump(pal, f)
        fields = (("id", "int"), ("intermittent", "int"))
        roads = write_layer(os.path.join(d, "roads.fgb"), 32611,
                            [(rect(bw - 50, ROAD_Y - 4, be + 50, ROAD_Y + 4), {"id": 1})], fields=(("id", "int"),))
        empty = (rect(500000, 4790000, 500001, 4790001), {"id": 1})
        paving = write_layer(os.path.join(d, "paving.fgb"), 32611, [empty], fields=(("id", "int"),))
        roofs = write_layer(os.path.join(d, "roofs.fgb"), 32611, [empty], fields=(("id", "int"),))
        water = write_layer(os.path.join(d, "water.fgb"), 32611, [(rect(500000, 4790000, 500001, 4790001),
                                                                     {"id": 1, "intermittent": 0})], fields=fields)
        cls.mask = paint._ManifestOf([])
        cls.mask._layers = {"roads": roads, "paving": paving, "roofs": roofs, "water": water}
        cls.fields = write_layer(os.path.join(d, "fields.fgb"), 32611, [
            (square(*FIELD), {"id": 1, "crop_group": 1, "bearing": 0.0})],
            fields=(("id", "int"), ("crop_group", "int"), ("bearing", "double")))
        cls.cover = os.path.join(d, "crop_cover.tif")
        ds = gdal.GetDriverByName("GTiff").Create(cls.cover, G.COLS, G.ROWS, 3, gdal.GDT_Byte,
                                                  options=["TILED=YES", "COMPRESS=DEFLATE", "SPARSE_OK=TRUE"])
        ds.SetGeoTransform((G.ORIGIN_X, 10, 0, G.ORIGIN_Y, 0, -10))
        s = osr.SpatialReference()
        s.ImportFromEPSG(32611)
        ds.SetProjection(s.ExportToWkt())
        c0, r0 = int((FIELD[0] - G.ORIGIN_X) / 10), int((G.ORIGIN_Y - FIELD[1] - FIELD[2]) / 10)
        n = int(FIELD[2] / 10)
        for b, v in ((1, 1), (2, 1), (3, 1)):                 # corn, green, field interior
            ds.GetRasterBand(b).WriteArray(np.full((n, n), v, np.uint8), c0, r0)
        ds = None
        cls.boxf = os.path.join(d, "f.tif")
        w = BOX.window()
        ds = gdal.GetDriverByName("GTiff").Create(cls.boxf, w.width, w.height, 2, gdal.GDT_Byte,
                                                  options=["TILED=YES", "COMPRESS=DEFLATE"])
        ds.SetGeoTransform(w.transform)
        ds.SetProjection(s.ExportToWkt())
        a = np.full((w.height, w.width), CR.SHORT_GREEN, np.uint8)
        rr = int((bn - ROAD_Y) / 0.5)
        a[rr - 20:rr + 20, :] = CR.DARK                       # asphalt 10 m either side of the road's line
        for b in (1, 2):
            ds.GetRasterBand(b).WriteArray(a)
        ds = None
        cls.soils = soils
        cls.palette = paint.Palette.from_files(os.path.join(d, "ground_types.json"), os.path.join(d, "palette.json"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def painter(self, boxes=True, crops=True):
        return paint.Painter(self.soils, self.palette, self.mask, crop_cover=self.cover if crops else None,
                             fields=self.fields if crops else None, classes={"f": self.boxf} if boxes else None)

    def win(self, w, s, e, n, res=2.0):
        return G.window((w, s, e, n), res, snap="out")

    def test_palette_counts_and_flat_colours(self):
        self.assertEqual(self.palette.counts, {"measured": 2, "borrowed": 0, "flat": 1, "water": 1})
        self.assertAlmostEqual(float(self.palette.lab[2][0]), 0.68)          # clay: flat by texture
        self.assertAlmostEqual(float(paint.flat_lab("x:silty-clay-loam", None)[0]), 0.72)
        self.assertAlmostEqual(float(paint.flat_lab("rock-outcrop", "rock")[0]), paint.FLAT_ROCK[0])
        self.assertAlmostEqual(float(self.palette.valley[0]), 0.70, places=5)   # the measured types' median

    def test_types_meet_in_a_twenty_metre_ramp(self):
        y = 4802200.0
        lab = self.painter(boxes=False, crops=False).paint_lab(self.win(X_EDGE - 60, y - 20, X_EDGE + 60, y + 20))
        L = lab[10, :, 0]
        xs = X_EDGE - 60 + 1 + 2 * np.arange(len(L))
        self.assertAlmostEqual(float(L[xs < X_EDGE - 12].mean()), 0.80, places=3)
        self.assertAlmostEqual(float(L[xs > X_EDGE + 12].mean()), 0.68, places=3)
        mid = np.interp(X_EDGE, xs, L)
        self.assertAlmostEqual(float(mid), 0.74, places=2)
        ramp = (xs > X_EDGE - 8) & (xs < X_EDGE + 8)
        self.assertTrue(np.all(np.diff(L[ramp]) < 0))

    def test_windows_meet_without_a_seam(self):
        p = self.painter()
        w = self.win(546000, 4801900, 546800, 4802700)
        whole = p.paint_lab(w)
        left = p.paint_lab(self.win(546000, 4801900, 546400, 4802700))
        right = p.paint_lab(self.win(546400, 4801900, 546800, 4802700))
        self.assertTrue(np.allclose(np.concatenate([left, right], axis=1), whole, atol=1e-5))

    def test_a_water_unit_takes_the_soil_around_it(self):
        x, y, s = WATER
        lab = self.painter(boxes=False, crops=False).paint_lab(self.win(x, y, x + s, y + s))
        self.assertAlmostEqual(float(lab[10, 10, 0]), 0.80, places=3)

    def test_a_green_corn_field_in_rows(self):
        x, y, s = FIELD
        lab = self.painter(boxes=False).paint_lab(self.win(x + 100, y + 100, x + 300, y + 300))
        corn = paint._lab(paint.CROP_GREEN[1])
        self.assertLess(float(np.median(K.delta_e(lab, corn))), 2.0)
        self.assertGreater(float(lab[50, :, 0].std()), 0.004)               # rows north-south: L varies east-west
        self.assertLess(float(lab[:, 50, 0].std()), 1e-4)                   # ... and not along a row
        self.assertGreater(float(K.delta_e(lab[0, 0], self.palette.lab[1])), 5)

    def test_box_classes_feather_in(self):
        bw, bs, be, bn = BOX.utm
        p = self.painter(crops=False)
        yc = bn - 200.0
        lab = p.paint_lab(self.win(bw + 300, yc - 10, bw + 400, yc + 10))
        self.assertLess(float(K.delta_e(lab[5, 25], K.token_lab("lawn"))), 0.5)
        edge = p.paint_lab(self.win(bw, yc - 10, bw + 100, yc + 10))
        soil = self.palette.lab[4]
        self.assertLess(float(K.delta_e(edge[5, 0], soil)), 2.0)            # the box's edge: the valley paint
        self.assertLess(float(K.delta_e(edge[5, 45], K.token_lab("lawn"))), 2.0)   # 90 m in: the class

    def test_paved_classes_beside_a_road_paint_the_soil(self):
        bw, bs, be, bn = BOX.utm
        x = (bw + be) / 2
        lab = self.painter(crops=False).paint_lab(self.win(x - 10, ROAD_Y - 10, x + 10, ROAD_Y + 10, res=0.5))
        soil = self.palette.lab[4]
        row = lambda y: int((ROAD_Y + 10 - y) / 0.5)              # noqa: E731
        self.assertLess(float(K.delta_e(lab[row(ROAD_Y), 20], soil)), 0.5)       # on the road
        self.assertLess(float(K.delta_e(lab[row(ROAD_Y + 6), 20], soil)), 0.5)   # 2 m beside it
        self.assertLess(float(K.delta_e(lab[row(ROAD_Y + 8.5), 20], K.token_lab("asphalt"))), 0.5)   # 4.5 m

    def test_outside_the_grid_is_the_flat_valley(self):
        rgb = self.painter().paint(self.win(G.ORIGIN_X - 40, 4802000, G.ORIGIN_X + 40, 4802040))
        self.assertEqual(tuple(rgb[5, 0]), K.hex_rgb(K.TOKENS["flat_valley"]))

    def test_a_coarse_level_paints_the_same_colours(self):
        x, y, s = FIELD
        p = self.painter()
        fine = p.paint_lab(self.win(x + 100, y + 100, x + 300, y + 300)).reshape(-1, 3).mean(0)
        coarse = p.paint_lab(self.win(x + 100, y + 100, x + 300, y + 300, res=10.0)).reshape(-1, 3).mean(0)
        self.assertLess(float(K.delta_e(fine, coarse)), 1.0)


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, SciPy)")
class TestColour(unittest.TestCase):
    def test_round_trip(self):
        for h in K.TOKENS.values():
            rgb = np.array(K.hex_rgb(h), float)
            back = K.oklab_to_rgb(K.rgb_to_oklab(rgb))
            self.assertTrue(np.allclose(back, rgb, atol=0.01), h)

    def test_white_and_grey(self):
        lab = K.rgb_to_oklab(np.array([255.0, 255.0, 255.0]))
        self.assertAlmostEqual(float(lab[0]), 1.0, places=4)
        self.assertAlmostEqual(float(abs(lab[1]) + abs(lab[2])), 0.0, places=4)

    def test_crop_greens_are_no_darker_than_lawn(self):
        lawn = K.token_lab("lawn")[0]
        for h in list(paint.CROP_GREEN.values()) + [paint.TALL_GREEN]:
            self.assertGreaterEqual(float(paint._lab(h)[0]) + 0.01, float(lawn), h)


if __name__ == "__main__":
    unittest.main()
