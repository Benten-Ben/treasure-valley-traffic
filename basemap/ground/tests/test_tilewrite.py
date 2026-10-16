"""The tile writer (tilewrite.py) on synthetic paint: where a painted line lands in a tile, the blocks, the pyramid and
the assembled PMTiles files. Needs the worker image (GDAL, NumPy, Pillow): the tests skip elsewhere, and in the worker
image a skip counts as a failure."""

import io
import os
import shutil
import tempfile
import types
import unittest

try:
    import numpy as np
    from osgeo import osr
    from PIL import Image
    from basemap.ground import tilewrite as TW
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import grid as G
from basemap.ground import tiles as T
from basemap.landscape import pmtiles as P

LINE_X = 550001.0                                     # a north-south line in grid metres, inside the valley


class StubPainter:
    """Red west of LINE_X, blue east of it; flat Valley outside the grid."""

    def paint(self, win):
        xs = G.ORIGIN_X + (win.col + np.arange(win.width) + 0.5) * win.res
        rgb = np.zeros((win.height, win.width, 3), np.uint8)
        rgb[:, xs < LINE_X] = (200, 40, 40)
        rgb[:, xs >= LINE_X] = (40, 40, 200)
        return rgb


def tile_of(x_m, y_m, z):
    s = osr.SpatialReference()
    s.ImportFromEPSG(32611)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    g = osr.SpatialReference()
    g.ImportFromEPSG(4326)
    g.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    lon, lat, _ = osr.CoordinateTransformation(s, g).TransformPoint(x_m, y_m)
    xs, ys = T.tile_range((lon, lat, lon, lat), z)
    return xs[0], ys[0], lon, lat


def stub_plan():
    return types.SimpleNamespace(status="painted", reason="", missing_versions=[], raw_names=[], versions={},
                                 choices=[], credits=["© OpenStreetMap contributors"], licence="ODbL-1.0",
                                 republish="yes", refs=["soils/ground@20261015T000000Z"])


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, Pillow)")
class TestTiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_painted_line_lands_where_mercator_puts_it(self):
        x, y, lon, lat = tile_of(LINE_X, 4810000.0, 13)
        win = T.tile_window(13, x, y, TW.PAINT_RES)
        mosaic = TW.warp(StubPainter().paint(win), win, 13, x, y, 4)
        self.assertEqual(mosaic.shape, (2048, 2048, 3))
        w, s, e, n = T.tile_mercator(13, x, y)
        mx = lon * 20037508.342789244 / 180.0                     # the line's Web Mercator x at that latitude
        expect = (mx - w) / (e - w) * 2048
        row = int(round((n - (np.log(np.tan(np.radians(45 + lat / 2))) * 6378137.0)) / (n - s) * 2048))
        reds = np.flatnonzero(mosaic[row, :, 0] > 120)
        self.assertLess(abs((reds.max() + 1) - expect), 1.5)

    def test_a_block_makes_its_z15_z14_and_z13_tiles(self):
        x, y, *_ = tile_of(LINE_X, 4810000.0, 13)
        blocks = TW.Blocks(self.dir)
        n = TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        self.assertEqual(n, 21)
        self.assertEqual(TW.paint_valley_block(StubPainter(), blocks, x, y, 80), 0)    # done: kept, not repainted
        got = {(z, tx, ty): b for _f, z, tx, ty, b in blocks.all()}
        self.assertEqual(sorted({k[0] for k in got}), [13, 14, 15])
        t = np.asarray(Image.open(io.BytesIO(got[(15, 4 * x, 4 * y)])).convert("RGB"))
        self.assertEqual(t.shape, (512, 512, 3))
        self.assertIsNotNone(blocks.read_png(13, x, y))

    def test_halve_and_cut(self):
        a = np.zeros((4, 4, 3), np.uint8)
        a[:2, :2] = 100
        a[0, 0] = 104
        self.assertEqual(TW.halve(a)[0, 0].tolist(), [101, 101, 101])
        big = np.zeros((1024, 1024, 3), np.uint8)
        big[512:, 512:] = 9
        parts = TW.cut(big, 10, 3, 5, 2)
        self.assertEqual(sorted(parts), [(11, 6, 10), (11, 6, 11), (11, 7, 10), (11, 7, 11)])
        self.assertEqual(int(parts[(11, 7, 11)].max()), 9)
        self.assertEqual(int(parts[(11, 6, 10)].max()), 0)

    def test_the_pyramid_from_kept_tiles(self):
        blocks = TW.Blocks(self.dir)
        x12, y12 = T.valley_tiles(12)[60]
        for j in (0, 1):
            for i in (0, 1):
                blocks.keep_png(13, 2 * x12 + i, 2 * y12 + j, np.full((512, 512, 3), 50 * (1 + i + 2 * j), np.uint8))
        n = TW.pyramid(blocks, 80, lowest=11, log=lambda *_: None)
        self.assertEqual(n, 2)
        z12 = blocks.read_png(12, x12, y12)
        self.assertEqual(z12[0, 0].tolist(), [50, 50, 50])
        self.assertEqual(z12[511, 511].tolist(), [200, 200, 200])

    def test_assembled_files(self):
        x, y, *_ = tile_of(LINE_X, 4810000.0, 13)
        blocks = TW.Blocks(self.dir)
        TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        blocks.write("d15-1-1", {(17, 4 * 4 * x, 4 * 4 * y): b"detail"}, file="detail")
        valley, detail, entry, digest = TW.assemble(self.dir, stub_plan(), partial=True, log=lambda *_: None)
        self.assertTrue(valley.endswith("-partial.pmtiles") and detail.endswith("-partial.pmtiles"))
        self.assertIsNone(entry)
        self.assertEqual(len(P.tile_sizes(valley)), 21)
        self.assertEqual(P.tile_data(detail, 17, 16 * x, 16 * y), b"detail")
        meta = P.read_metadata(valley)
        self.assertEqual((meta["licence"], meta["republish"], meta["partial"]), ("ODbL-1.0", "yes", True))
        self.assertEqual(P.read_header(valley).tile_type, 4)
        shutil.rmtree(os.path.join(self.dir, "blocks"))
        os.makedirs(os.path.join(self.dir, "blocks"))
        TW.paint_valley_block(StubPainter(), TW.Blocks(self.dir), x, y, 80)
        TW.Blocks(self.dir).write("d15-1-1", {(17, 4 * 4 * x, 4 * 4 * y): b"detail"}, file="detail")
        _v, _d, entry, digest2 = TW.assemble(self.dir, stub_plan(), partial=False, log=lambda *_: None)
        self.assertEqual(digest, digest2)
        T.check_entry(entry)
        self.assertEqual(entry["file"], T.file_names(digest)[0])

    def test_the_boxes_blocks_and_the_detail_blocks(self):
        near = TW.blocks_near_boxes(13)
        self.assertGreaterEqual(len(near), 10)
        self.assertLess(len(near), 120)
        d = TW.detail_blocks()
        kids = {(4 * bx + i, 4 * by + j) for bx, by in d for i in range(4) for j in range(4)}
        self.assertTrue(set(T.detail_tiles(17)) <= kids)


if __name__ == "__main__":
    unittest.main()
