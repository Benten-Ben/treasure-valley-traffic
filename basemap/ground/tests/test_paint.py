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


X0, X1 = 545200.0, 545600.0                           # G1b's test window: type 1's ground, clear of the field
Y0, Y1 = 4801300.0, 4801700.0
MED = (0.80, 0.01, 0.04)                              # type 1's median; type 4's L is 0.60
COV = [4e-4, 0, 0, 1e-4, 0, 1e-4]                     # a spread of 0.02 in L and 0.01 in a and b


def write_cog(path, bounds, strips, hole=None, bands=4):
    """A 2 m COG-like GeoTIFF over bounds: strips = [(west, east, (L, a, b), ndvi byte)] colour the columns; hole =
    (west, east) is left out of the internal mask."""
    w, s_, e, n = bounds
    cols, rows = int((e - w) / 2), int((n - s_) / 2)
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, bands, gdal.GDT_Byte, options=["COMPRESS=DEFLATE"])
    ds.SetGeoTransform((w, 2, 0, n, 0, -2))
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(32611)
    ds.SetProjection(sr.ExportToWkt())
    arr = np.zeros((bands, rows, cols), np.uint8)
    for x0, x1, lab, nd in strips:
        c0, c1 = int((x0 - w) / 2), int((x1 - w) / 2)
        rgb = K.oklab_to_rgb8(np.array(lab, float))
        for b in range(3):
            arr[b, :, c0:c1] = rgb[b]
        if bands > 3:
            arr[3, :, c0:c1] = nd
    for b in range(bands):
        ds.GetRasterBand(b + 1).WriteArray(arr[b])
    if hole:
        ds.CreateMaskBand(gdal.GMF_PER_DATASET)
        m = np.full((rows, cols), 255, np.uint8)
        m[:, int((hole[0] - w) / 2):int((hole[1] - w) / 2)] = 0
        ds.GetRasterBand(1).GetMaskBand().WriteArray(m)
    ds = None
    return path


def write_dem(path, bounds, f, res=10.0):
    w, s_, e, n = bounds
    cols, rows = int((e - w) / res), int((n - s_) / res)
    ds = gdal.GetDriverByName("GTiff").Create(path, cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((w, res, 0, n, 0, -res))
    sr = osr.SpatialReference()
    sr.ImportFromEPSG(32611)
    ds.SetProjection(sr.ExportToWkt())
    xs = w + (np.arange(cols) + 0.5) * res
    ys = n - (np.arange(rows) + 0.5) * res
    ds.GetRasterBand(1).WriteArray(np.broadcast_to(f(xs[None, :], ys[:, None]), (rows, cols)).astype(np.float32))
    ds = None
    return path


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, SciPy)")
class TestTexturePhoto(unittest.TestCase):
    """G1b: the procedural noise and the photo's variation on the same synthetic world."""

    @classmethod
    def setUpClass(cls):
        TestPainter.setUpClass.__func__(cls)
        d = cls.dir
        cls.pal_path = os.path.join(d, "palette.json")

        def palette(cov=COV, oct_l=(0, 0, 0, 0, 0)):
            types = [{"gid": 1, "id": "a:loam", "status": "measured", "misc": None, "lab_med": list(MED),
                      "lab_cov": cov, "oct_l": list(oct_l), "oct_c": [0, 0, 0, 0, 0]},
                     {"gid": 4, "id": "c:sandy-loam", "status": "measured", "misc": None, "lab_med": [0.60, 0.01, 0.04],
                      "lab_cov": COV, "oct_l": [0, 0, 0, 0, 0], "oct_c": [0, 0, 0, 0, 0]}]
            path = os.path.join(d, f"palette-{len(os.listdir(d))}.json")
            with open(path, "w") as f:
                json.dump({"schema": "soils.palette/1", "types": types}, f)
            return paint.Palette.from_files(os.path.join(d, "ground_types.json"), path)
        cls.make_palette = staticmethod(palette)
        cls.bounds = (X0, Y0, X1, Y1)
        cls.cog = write_cog(os.path.join(d, "cog.tif"), cls.bounds, [
            (X0, 545300.0, (0.82, 0.01, 0.04), 128), (545300.0, 545400.0, (0.82, 0.01, 0.04), 128),
            (545400.0, X1, (0.95, 0.01, 0.04), 128)], hole=(545300.0, 545400.0))

    @classmethod
    def tearDownClass(cls):
        TestPainter.tearDownClass.__func__(cls)

    def painter(self, palette=None, photo=None, texture=True, **kw):
        return paint.Painter(self.soils, palette or self.make_palette(), self.mask, photo=photo, texture=texture, **kw)

    def win(self, w, s, e, n, res=2.0):
        return G.window((w, s, e, n), res, snap="out")

    def column(self, lab, x, w0=X0):
        return lab[:, int((x - w0) / 2)]

    def test_the_palette_carries_the_spread_and_the_energies(self):
        pal = self.make_palette(oct_l=(0, 1e-4, 2e-4, 3e-4, 4e-4))
        self.assertTrue(np.all(np.isfinite(pal.inv_cov[1])))
        self.assertTrue(np.allclose(pal.inv_cov[1][0, 0], 1 / 4e-4, rtol=1e-3))
        self.assertTrue(np.all(np.isnan(pal.inv_cov[2])))                         # clay: flat, no spread
        self.assertTrue(np.allclose(pal.oct_l[1], [0, 1e-4, 2e-4, 3e-4, 4e-4]))
        self.assertTrue(np.allclose(pal.oct_l[2], pal.valley_oct_l))              # a type without its own: the valley's
        self.assertTrue(np.allclose(pal.valley_oct_l, [0, 0.5e-4, 1e-4, 1.5e-4, 2e-4]))   # the median of types 1 and 4

    def test_noise_follows_the_types_energy_and_windows_meet(self):
        pal = self.make_palette(oct_l=(0, 0, 0, 4e-4, 4e-4))
        p = self.painter(pal)
        lab = p.paint_lab(self.win(X0, Y0, X1, Y1))
        self.assertAlmostEqual(float(lab[..., 0].mean()), MED[0], delta=0.012)
        self.assertGreater(float(lab[..., 0].std()), 0.015)
        self.assertLess(float(lab[..., 0].std()), 0.04)
        left = p.paint_lab(self.win(X0, Y0, 545400.0, Y1))
        right = p.paint_lab(self.win(545400.0, Y0, X1, Y1))
        self.assertTrue(np.allclose(np.concatenate([left, right], axis=1), lab, atol=1e-5))
        flat = self.painter(pal, texture=False).paint_lab(self.win(X0, Y0, X1, Y1))
        self.assertLess(float(flat[..., 0].std()), 1e-6)                          # texture=False is G1a's paint
        coarse = p.paint_lab(self.win(X0, Y0, X1, Y1, res=40.0))
        self.assertLess(float(coarse[..., 0].std()), 1e-6)                        # nothing a 40 m cell can draw

    def test_the_photos_variation_inside_2_5_sd_and_gone_outside_it(self):
        p = self.painter(photo=paint.Photo(self.cog))
        lab = p.paint_lab(self.win(X0, Y0, X1, Y1))
        mid = lab.shape[0] // 2
        self.assertAlmostEqual(float(lab[mid, int((545250.0 - X0) / 2), 0]), 0.82, delta=0.012)    # 1 sd: the photo's own
        self.assertAlmostEqual(float(lab[mid, int((545350.0 - X0) / 2), 0]), MED[0], delta=0.004)  # the mask's hole
        self.assertAlmostEqual(float(lab[mid, int((545500.0 - X0) / 2), 0]), MED[0], delta=0.004)  # 7.5 sd: not this ground
        out = p.paint_lab(self.win(545000.0, Y0, 545100.0, Y1))                                    # beyond the COG
        self.assertAlmostEqual(float(out[..., 0].mean()), MED[0], delta=0.004)

    def test_windows_meet_with_the_photo(self):
        p = self.painter(photo=paint.Photo(self.cog))
        whole = p.paint_lab(self.win(X0, Y0, X1, Y1))
        left = p.paint_lab(self.win(X0, Y0, 545322.0, Y1))
        right = p.paint_lab(self.win(545322.0, Y0, X1, Y1))
        self.assertTrue(np.allclose(np.concatenate([left, right], axis=1), whole, atol=1e-5))

    def test_a_coarse_level_takes_the_photo_too(self):
        p = self.painter(photo=paint.Photo(self.cog))
        lab = p.paint_lab(self.win(X0, Y0, 545300.0, Y1, res=10.0))
        self.assertAlmostEqual(float(lab[2:-2, 2:-2, 0].mean()), 0.82, delta=0.015)
        fine = p.paint_lab(self.win(X0, Y0, 545300.0, Y1))
        self.assertLess(float(K.delta_e(fine.reshape(-1, 3).mean(0), lab.reshape(-1, 3).mean(0))), 1.5)

    def test_no_variation_on_a_mapped_surface_or_its_band(self):
        bw, bs, be, bn = BOX.utm
        x = G.ORIGIN_X + 2 * round((bw + 200.0 - G.ORIGIN_X) / 2)               # on the 2 m grid
        cog = write_cog(os.path.join(self.dir, "road.tif"), (x - 100, ROAD_Y - 40, x + 100, ROAD_Y + 40),
                        [(x - 100, x + 100, (0.62, 0.01, 0.04), 128)])
        p = self.painter(photo=paint.Photo(cog))
        lab = p.paint_lab(self.win(x - 20, ROAD_Y - 20, x + 20, ROAD_Y + 20))
        row = lambda y: int((ROAD_Y + 20 - y) / 2)                               # noqa: E731
        self.assertAlmostEqual(float(lab[row(ROAD_Y), 10, 0]), 0.60, delta=0.004)         # on the road
        self.assertAlmostEqual(float(lab[row(ROAD_Y + 6), 10, 0]), 0.60, delta=0.004)     # in the 3 m band
        self.assertAlmostEqual(float(lab[row(ROAD_Y + 11), 10, 0]), 0.62, delta=0.012)    # beyond it: the photo's

    def test_a_cast_shadow_near_a_roof_is_covered(self):
        d = self.dir
        roofs = write_layer(os.path.join(d, "roofs-g1b.fgb"), 32611, [(square(545300, 4801500, 20), {"id": 1})],
                            fields=(("id", "int"),))
        mask = paint._ManifestOf([])
        mask._layers = dict(self.mask._layers, roofs=roofs)
        cog = write_cog(os.path.join(d, "dark.tif"), self.bounds, [(X0, X1, (0.66, 0.01, 0.02), 128)])   # dark and blue
        wide = [0.0064, 0, 0, 1e-4, 0, 4e-4]                                      # 0.08 in L, 0.02 in b: 2 sd stays inside
        p = paint.Painter(self.soils, self.make_palette(cov=wide), mask, photo=paint.Photo(cog))
        lab = p.paint_lab(self.win(X0, Y0, X1, Y1))
        near = lab[int((Y1 - 4801540.0) / 2), int((545310.0 - X0) / 2), 0]       # 20 m beside the roof
        far = lab[int((Y1 - 4801540.0) / 2), int((545500.0 - X0) / 2), 0]
        self.assertAlmostEqual(float(near), MED[0], delta=0.004)
        self.assertAlmostEqual(float(far), 0.66, delta=0.012)

    def test_the_dems_slopes_put_the_light_back(self):
        d = self.dir
        t = np.tan(np.radians(20))
        dem = write_dem(os.path.join(d, "dem.tif"), (544900.0, 4801000.0, 545900.0, 4802000.0),
                        lambda x, y: 1000.0 - t * (y - 4801000.0))                 # falls to the north: faces north
        sun = paint.Photo.REFERENCE_SUN_LOCAL
        az, el = TX_sun(sun)
        gain, ok = paint.TX.illumination_gain(np.float32(np.radians(20)), np.float32(0.0), az, el)
        self.assertTrue(ok)
        lin = K.srgb_to_linear(K.oklab_to_rgb(np.array(MED, float)) / 255.0) / float(gain)
        lit = K.rgb_to_oklab(K.linear_to_srgb(lin) * 255.0)                       # the colour that slope's photo shows
        cog = write_cog(os.path.join(d, "slope.tif"), self.bounds, [(X0, X1, tuple(lit), 128)])
        with_dem = self.painter(photo=paint.Photo(cog, dem=dem)).paint_lab(self.win(X0, Y0, X1, Y1))
        without = self.painter(photo=paint.Photo(cog)).paint_lab(self.win(X0, Y0, X1, Y1))
        self.assertAlmostEqual(float(with_dem[100, 100, 0]), MED[0], delta=0.012)
        self.assertLess(float(without[100, 100, 0]), MED[0] - 0.015)              # unnormalised: shaded, partly kept
        self.assertGreater(float(abs(without[100, 100, 0] - with_dem[100, 100, 0])), 0.015)

    def test_a_crop_cluster_is_painted_where_the_photo_confirms_it(self):
        d = self.dir
        cover = os.path.join(d, "cluster.tif")
        ds = gdal.GetDriverByName("GTiff").Create(cover, G.COLS, G.ROWS, 3, gdal.GDT_Byte,
                                                  options=["TILED=YES", "COMPRESS=DEFLATE", "SPARSE_OK=TRUE"])
        ds.SetGeoTransform((G.ORIGIN_X, 10, 0, G.ORIGIN_Y, 0, -10))
        sr = osr.SpatialReference()
        sr.ImportFromEPSG(32611)
        ds.SetProjection(sr.ExportToWkt())
        c0, r0 = int((545300.0 - G.ORIGIN_X) / 10), int((G.ORIGIN_Y - 4801600.0) / 10)
        for b, v in ((1, 1), (2, 1), (3, 3)):                                      # corn, green, confidence 3
            ds.GetRasterBand(b).WriteArray(np.full((10, 10), v, np.uint8), c0, r0)
        ds = None
        ndvi = lambda v: int(round(1 + (v + 1) * 127))                           # noqa: E731
        green = write_cog(os.path.join(d, "green.tif"), self.bounds, [(X0, X1, MED, ndvi(0.6))])
        brown = write_cog(os.path.join(d, "brown.tif"), self.bounds, [(X0, X1, MED, ndvi(0.1))])
        win = self.win(545300.0, 4801500.0, 545400.0, 4801600.0)
        corn = paint._lab(paint.CROP_GREEN[1])
        yes = self.painter(photo=paint.Photo(green), crop_cover=cover).paint_lab(win)
        no = self.painter(photo=paint.Photo(brown), crop_cover=cover).paint_lab(win)
        none = self.painter(crop_cover=cover).paint_lab(win)
        self.assertLess(float(K.delta_e(yes[25, 25], corn)), 4.0)
        self.assertLess(float(K.delta_e(no[25, 25], np.array(MED))), 1.0)
        self.assertLess(float(K.delta_e(none[25, 25], np.array(MED))), 1.0)          # without the COG: G1a's wait

    def test_a_wrong_cog_is_refused(self):
        cog = write_cog(os.path.join(self.dir, "three.tif"), self.bounds, [(X0, X1, MED, 0)], bands=3)
        with self.assertRaises(paint.PaintError):
            self.painter(photo=paint.Photo(cog)).paint_lab(self.win(X0, Y0, 545300.0, 4801400.0))

    def test_the_report_says_what_the_photo_did(self):
        p = self.painter(photo=paint.Photo(self.cog, dem="d.tif"))
        rep = paint.photo_report(p)
        self.assertTrue(rep["noise"])
        self.assertEqual(rep["photo"]["cog"], "cog.tif")
        self.assertIn("DEM", rep["photo"]["light"])
        self.assertIn("reference", paint.photo_report(self.painter(photo=paint.Photo(self.cog)))["photo"]["sun"])
        self.assertEqual(paint.photo_report(self.painter(texture=False)), {"noise": False, "photo": None})


def TX_sun(local):
    az, el = paint.TX.sun_position(paint.TX.parse_local(local))
    return az, el


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
