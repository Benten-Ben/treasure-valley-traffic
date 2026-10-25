"""The DEM step (dem.py): the map's terrain-RGB tiles onto the painter's 2 m grid. Needs the worker image (GDAL,
NumPy, Pillow); the tests skip elsewhere, and in the worker image a skip counts as a failure."""

import json
import math
import os
import shutil
import tempfile
import unittest
from io import BytesIO

try:
    import numpy as np
    from osgeo import osr
    from PIL import Image
    from basemap.ground import dem as D
    from basemap.ground import rasterize as R
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import grid as G
from basemap.ground import pmtw

Z = 14


def elevation(mx, my):
    """The synthetic surface, a function of Web Mercator metres: a plane (so bilinear resampling is exact)."""
    return 900.0 + 0.04 * (mx + 12960000.0) - 0.03 * (my - 5370000.0)


def encode(arr):
    v = np.rint((arr - D.BASE) / D.UNIT).astype(np.uint32)
    rgb = np.dstack([(v >> 16) & 255, (v >> 8) & 255, v & 255]).astype(np.uint8)
    buf = BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "PNG")
    return buf.getvalue()


def tile_xy(mx, my, z=Z):
    size = 2 * D.WEBMERC / (1 << z)
    return int((mx + D.WEBMERC) // size), int((D.WEBMERC - my) // size)


def tile_pixels(x, y, z=Z, fn=elevation):
    size = 2 * D.WEBMERC / (1 << z)
    px = size / D.TILE_PX
    mx = -D.WEBMERC + x * size + (np.arange(D.TILE_PX) + 0.5) * px
    my = D.WEBMERC - y * size - (np.arange(D.TILE_PX) + 0.5) * px
    return fn(mx[None, :], my[:, None])


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, Pillow)")
class TestDem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        ct = osr.CoordinateTransformation(R.srs_of(G.CRS), R.srs_of("EPSG:3857"))
        cls.to_merc = ct
        e, n = 549300.0, 4801900.0                                    # box f's neighbourhood
        mx, my = ct.TransformPoint(e, n)[:2]
        tx, ty = tile_xy(mx, my)
        size = 2 * D.WEBMERC / (1 << Z)
        # the window sits across the corner between tiles (tx, ty) and (tx + 1, ty + 1)
        cx, cy = -D.WEBMERC + (tx + 1) * size, D.WEBMERC - (ty + 1) * size
        back = osr.CoordinateTransformation(R.srs_of("EPSG:3857"), R.srs_of(G.CRS))
        ce, cn = back.TransformPoint(cx, cy)[:2]
        cls.window = G.window((ce - 300, cn - 300, ce + 300, cn + 300), 2.0)        # 300 x 300 cells
        cls.tiles = [(tx, ty), (tx + 1, ty), (tx, ty + 1), (tx + 1, ty + 1)]
        cls.path = os.path.join(cls.dir, "terrain.pmtiles")
        w = pmtw.Writer(cls.path, 2, {"encoding": "mapbox", "format": "png", "minzoom": "13", "maxzoom": str(Z),
                                      "name": "terrain"})
        for x, y in cls.tiles:
            w.add(Z, x, y, encode(tile_pixels(x, y)))
        wx, wy = tile_xy(mx, my, 13)
        w.add(13, wx, wy, encode(np.full((D.TILE_PX, D.TILE_PX), 1.0)))        # a coarser tile that must not be read
        w.finish((-117.05, 43.0, -115.95, 43.85), (-116.4, 43.4, 10))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def expected(self, win):
        cols = win.west + (np.arange(win.width) + 0.5) * win.res
        rows = win.north - (np.arange(win.height) + 0.5) * win.res
        out = np.empty(win.shape, np.float64)
        for i, n in enumerate(rows):
            pts = [self.to_merc.TransformPoint(float(e), float(n))[:2] for e in cols]
            out[i] = [elevation(m[0], m[1]) for m in pts]
        return out

    def build(self, name, **kw):
        out = os.path.join(self.dir, name)
        info = D.build(self.path, out, window=kw.pop("window", self.window), log=lambda *_: None, **kw)
        return out, info

    def test_decodes_mapbox_values(self):
        arr = np.full((D.TILE_PX, D.TILE_PX), 812.3)
        got = D.decode_tile(encode(arr))
        self.assertTrue(np.allclose(got, 812.3, atol=0.051))
        self.assertEqual(got.dtype, np.float32)
        with self.assertRaises(D.DemError):
            D.decode_tile(b"not an image")

    def test_the_surface_lands_on_the_grid_across_a_tile_corner(self):
        out, info = self.build("a.tif", size=128)                # 3 x 3 blocks; the tiles meet inside the middle one
        want = self.expected(self.window)
        ds = D.gdal.Open(out)
        got = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
        self.assertEqual(got.shape, want.shape)
        self.assertTrue(np.isfinite(got).all())
        # the tiles hold 0.1 m steps and the plane is exact under bilinear resampling: within a step and a bit
        self.assertLess(float(np.abs(got - want).max()), 0.12)
        self.assertEqual(info["blocks"], 9)
        self.assertEqual(info["finite_share"], 1.0)
        self.assertEqual(ds.GetGeoTransform(), self.window.transform)
        self.assertEqual(D.check(out), [])

    def test_blocks_meet_without_a_seam(self):
        whole, _ = self.build("w.tif", size=512)
        parts, _ = self.build("p.tif", size=64)
        a = D.gdal.Open(whole).ReadAsArray()
        b = D.gdal.Open(parts).ReadAsArray()
        # the blocks' mosaics start at different tiles, so the resampler's arithmetic differs in the last bits only
        self.assertLess(float(np.abs(a.astype(np.float64) - b).max()), 0.01)

    def test_the_highest_zoom_is_read_and_a_missing_tile_is_nan(self):
        t = D.Terrain(self.path)
        self.assertEqual(t.zoom, Z)
        self.assertAlmostEqual(t.pixel_m, 2 * D.WEBMERC / (512 * (1 << Z)), places=6)
        # a window two tiles away from every tile in the file: NaN, not the z13 tile's flat 1 m
        ce, cn = self.window.east + 6000.0, self.window.north + 6000.0
        far = G.window((ce, cn, ce + 200, cn + 200), 2.0)
        out, info = self.build("far.tif", window=far)
        self.assertTrue(np.isnan(D.gdal.Open(out).ReadAsArray()).all())
        self.assertEqual(info["finite_share"], 0.0)
        self.assertIsNone(info["min_m"])
        self.assertGreater(info["tiles_wanted"], info["tiles_read"] - 1)

    def test_the_sidecar_names_the_source_and_the_file(self):
        out, info = self.build("s.tif")
        with open(D.sidecar_path(out)) as f:
            side = json.load(f)
        self.assertEqual(side, info)
        self.assertEqual(side["sha256"], D.sha256(out))
        self.assertEqual(side["source"]["sha256"], D.sha256(self.path))
        self.assertEqual(side["source"]["zoom"], Z)
        self.assertEqual(side["grid"]["res"], 2.0)
        self.assertFalse(os.path.exists(out + ".part"))

    def test_never_overwrites_and_a_stopped_build_is_not_finished(self):
        out, _ = self.build("o.tif")
        with self.assertRaises(D.DemError):
            D.build(self.path, out, window=self.window, log=lambda *_: None)
        stop = os.path.join(self.dir, "stop.tif")
        self.assertIsNone(D.build(self.path, stop, window=self.window, size=128, limit=2, log=lambda *_: None))
        self.assertFalse(os.path.exists(stop))
        self.assertTrue(os.path.exists(stop + ".part"))
        D.build(self.path, stop, window=self.window, size=128, log=lambda *_: None)      # restarts from scratch
        self.assertTrue(os.path.exists(stop))
        self.assertFalse(os.path.exists(stop + ".part"))

    def test_refuses_other_files(self):
        w = pmtw.Writer(os.path.join(self.dir, "mvt.pmtiles"), 1, {})
        w.add(14, 3000, 5000, b"x")
        w.finish((-117, 43, -116, 44), (-116.5, 43.5, 14))
        with self.assertRaises(D.DemError):
            D.Terrain(os.path.join(self.dir, "mvt.pmtiles"))
        w = pmtw.Writer(os.path.join(self.dir, "terrarium.pmtiles"), 2, {"encoding": "terrarium"})
        w.add(14, 3000, 5000, b"x")
        w.finish((-117, 43, -116, 44), (-116.5, 43.5, 14))
        with self.assertRaises(D.DemError):
            D.Terrain(os.path.join(self.dir, "terrarium.pmtiles"))
        with self.assertRaises(D.DemError):
            D.Terrain(self.path, zoom=15)
        with self.assertRaises(D.DemError):
            D.build(self.path, os.path.join(self.dir, "x.tif"), window=G.window((549000, 4801000, 549100, 4801100), 10.0),
                    log=lambda *_: None)

    def test_check_refuses_a_misplaced_raster(self):
        bad = os.path.join(self.dir, "bad.tif")
        ds = D.gdal.GetDriverByName("GTiff").Create(bad, 10, 10, 1, D.gdal.GDT_Float32)
        ds.SetGeoTransform((G.ORIGIN_X + 1.0, 2.0, 0, G.ORIGIN_Y, 0, -2.0))
        ds.SetProjection(R.srs_of(G.CRS).ExportToWkt())
        ds = None
        self.assertIn("not on the ground's grid", D.check(bad))

    def test_slope_shares_count_known_cells(self):
        out, _ = self.build("sl.tif")
        shares = D.slope_shares(out, cuts=(1.0, 10.0), size=100)
        self.assertEqual(list(shares), ["valley"])                      # the window holds none of the ten boxes
        self.assertEqual(shares["valley"]["cells"], self.window.width * self.window.height)
        # the plane falls about 0.07 on the ground: 4 degrees, so every cell is over 1 and none over 10
        self.assertEqual(shares["valley"]["over"][1.0], 1.0)
        self.assertEqual(shares["valley"]["over"][10.0], 0.0)

    def test_the_painter_reads_it(self):
        from basemap.ground import paint
        out, _ = self.build("pt.tif")
        p = paint.Photo("unused.tif", dem=out)
        W = self.window.pad(-20)
        gain, ok = p._light(W)
        self.assertEqual(gain.shape, W.shape)
        self.assertGreater(p.dem_finite, 0)
        self.assertEqual(p.dem_finite, p.dem_cells)
        # the plane slopes about 0.05, 3 degrees: lit and usable everywhere
        self.assertTrue(ok.all())


if __name__ == "__main__":
    unittest.main()
