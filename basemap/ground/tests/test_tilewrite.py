"""The tile writer (tilewrite.py) on synthetic paint: where a painted line lands in a tile, the blocks, the pyramid and
the assembled PMTiles files. Needs the worker image (GDAL, NumPy, Pillow): the tests skip elsewhere, and in the worker
image a skip counts as a failure."""

import io
import json
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


def stub_plan(versions=None):
    versions = dict(versions or {})
    return types.SimpleNamespace(status="painted", reason="", missing_versions=[], raw_names=sorted(versions),
                                 versions=versions, choices=[], credits=["© OpenStreetMap contributors"],
                                 licence="ODbL-1.0", republish="yes", refs=["soils/ground@20261015T000000Z"])


REPORT = {"painter": "test", "types": {"measured": 2, "borrowed": 0, "flat": 2, "water": 0},
          "flat_types": [{"gid": 30, "id": "pits", "series": "Pits"}, {"gid": 7, "id": "dams", "series": "Dams"}]}


def begun(out, plan=None):
    """A run's Blocks, begun for plan (the stub's by default), with REPORT as the painter's report."""
    plan = plan or stub_plan()
    blocks = TW.Blocks(out)
    blocks.begin(dict(TW.run_stamp(plan), paint=REPORT))
    return blocks


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
        blocks = begun(self.dir)
        n = TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        self.assertEqual(n, 21)
        self.assertEqual(TW.paint_valley_block(StubPainter(), blocks, x, y, 80), 0)    # done: kept, not repainted
        got = {(z, tx, ty): b for _f, z, tx, ty, b in blocks.all()}
        self.assertEqual(sorted({k[0] for k in got}), [13, 14, 15])
        t = np.asarray(Image.open(io.BytesIO(got[(15, 4 * x, 4 * y)])).convert("RGB"))
        self.assertEqual(t.shape, (512, 512, 3))
        self.assertIsNotNone(blocks.read_png(13, x, y))
        self.assertEqual(blocks.index()[f"v13-{x}-{y}"]["digest"], TW.run_digest(stub_plan()))
        self.assertTrue(hasattr(blocks.all(), "__next__"))            # a block at a time, never every tile at once

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
        blocks = begun(self.dir)
        x12, y12 = T.valley_tiles(12)[60]
        for j in (0, 1):
            for i in (0, 1):
                blocks.keep_png(13, 2 * x12 + i, 2 * y12 + j, np.full((512, 512, 3), 50 * (1 + i + 2 * j), np.uint8))
        n = TW.pyramid(blocks, 80, lowest=11, log=lambda *_: None)
        self.assertEqual(n, 2)
        z12 = blocks.read_png(12, x12, y12)
        self.assertEqual(z12[0, 0].tolist(), [50, 50, 50])
        self.assertEqual(z12[511, 511].tolist(), [200, 200, 200])
        self.assertEqual(blocks.index()["p12"]["gaps"], 0)
        self.assertGreater(blocks.index()["p11"]["gaps"], 0)          # its other z12 children aren't painted
        os.remove(os.path.join(blocks.png, f"13-{2 * x12 + 1}-{2 * y12 + 1}.png"))
        TW.pyramid(blocks, 80, lowest=12, log=lambda *_: None)
        self.assertEqual(blocks.index()["p12"]["gaps"], 1)            # a child in the map box, not painted yet

    def test_assembled_files(self):
        x, y, *_ = tile_of(LINE_X, 4810000.0, 13)
        blocks = begun(self.dir)
        TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        blocks.write("d15-1-1", {(17, 4 * 4 * x, 4 * 4 * y): b"detail"}, file="detail")
        blocks.write("w10-1-1", {(10, x // 8, y // 8): b"view"}, file="view")
        valley, detail, entry, digest = TW.assemble(self.dir, stub_plan(), partial=True, log=lambda *_: None)
        self.assertTrue(valley.endswith("-partial.pmtiles") and detail.endswith("-partial.pmtiles"))
        self.assertIsNone(entry)
        self.assertEqual(len(P.tile_sizes(valley)), 22)                # the block's 21 and the view tile
        self.assertEqual(P.tile_data(detail, 17, 16 * x, 16 * y), b"detail")
        meta = P.read_metadata(valley)
        self.assertEqual((meta["licence"], meta["republish"], meta["partial"]), ("ODbL-1.0", "yes", True))
        self.assertEqual((meta["digest"], meta["code"]), (digest, TW.CODE))
        self.assertEqual(meta["paint"]["flat_types"], REPORT["flat_types"])
        self.assertEqual(meta["fallbacks"], ["soils/palette: 2 ground types without a measured or borrowed colour, "
                                             "painted a flat colour by texture (Dams, Pits)"])
        self.assertEqual(P.read_header(valley).tile_type, 4)
        self.assertEqual(digest, TW.run_digest(stub_plan()))
        self.assertEqual(digest, T.digest(stub_plan(), painter=f"{TW.paint.PAINTER_VERSION} code {TW.CODE}"))

    def test_readback_of_named_bounds(self):
        x, y, *_ = tile_of(LINE_X, 4810000.0, 13)
        blocks = begun(self.dir)
        TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        valley, _detail, _entry, _digest = TW.assemble(self.dir, stub_plan(), partial=True, log=lambda *_: None)
        out = os.path.join(self.dir, "rb")
        argv = ["readback", "--pmtiles", valley, "--zoom", "15", "--out", out]
        b = f"{LINE_X - 500},4809500,{LINE_X + 500},4810500"
        self.assertEqual(TW.main(argv + ["--bounds", f"seam={b}"]), 0)
        self.assertTrue(os.path.getsize(os.path.join(out, "seam-z15.tif")) > 0)
        self.assertEqual(TW.main(argv + ["--bounds", "bad=1,2,0,3"]), 2)            # W must be under E
        self.assertEqual(TW.main(argv + ["--bounds", "=1,2,3,4"]), 2)               # a name is needed

    def test_a_whole_file_needs_every_tile(self):
        x, y, *_ = tile_of(LINE_X, 4810000.0, 13)
        blocks = begun(self.dir)
        TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        with self.assertRaises(TW.TileError) as ctx:
            TW.assemble(self.dir, stub_plan(), partial=False, log=lambda *_: None)
        self.assertIn("14,552 valley tiles", str(ctx.exception))
        self.assertIn("612 detail tiles (z17 612)", str(ctx.exception))
        self.assertFalse([n for n in os.listdir(self.dir) if n.endswith(".pmtiles")])
        # every tile of the spec: whole files, and the entry the manifest takes
        want = TW.expected()
        self.assertEqual((len(want["valley"]), len(want["detail"])), (14573, 612))
        shutil.rmtree(self.dir)
        blocks = begun(self.dir)
        tile = TW.webp(np.full((512, 512, 3), 120, np.uint8))
        lows = {t for t in want["valley"] if t[0] <= 12}
        blocks.write("v13-all", {t: tile for t in want["valley"] - lows})
        for z in range(8, 13):
            blocks.write(f"p{z}", {t: tile for t in lows if t[0] == z}, gaps=1 if z == 12 else 0)
        blocks.write("d15-all", {t: tile for t in want["detail"]}, file="detail")
        blocks.write("w10-0-0", {(10, 0, 0): b"view"}, file="view")    # the estimate's: left out of a whole file
        with self.assertRaises(TW.TileError) as ctx:                   # the pyramid was made too early
            TW.assemble(self.dir, stub_plan(), partial=False, log=lambda *_: None)
        self.assertIn("p12", str(ctx.exception))
        blocks.write("p12", {t: tile for t in lows if t[0] == 12})
        valley, detail, entry, digest = TW.assemble(self.dir, stub_plan(), partial=False, log=lambda *_: None)
        self.assertEqual(len(P.tile_sizes(valley)), 14573)
        self.assertEqual(len(P.tile_sizes(detail)), 612)
        self.assertNotIn("partial", valley)
        T.check_entry(entry)
        self.assertEqual(entry["file"], T.file_names(digest)[0])
        self.assertIn("painted a flat colour by texture (Dams, Pits)", entry["fallbacks"][-1])
        tiles_dir = os.path.join(self.dir, "tiles")
        os.makedirs(tiles_dir)
        with open(os.path.join(tiles_dir, "manifest.json"), "w") as f:
            f.write("{}")
        TW.switch_in(tiles_dir, (valley, detail), entry)
        TW.switch_in(tiles_dir, (valley, detail), entry)                # the same bytes again: fine
        with open(os.path.join(tiles_dir, os.path.basename(detail)), "ab") as f:
            f.write(b"x")
        with self.assertRaises(TW.TileError):                          # a name is a version
            TW.switch_in(tiles_dir, (valley, detail), entry)

    def test_one_run_one_digest(self):
        x, y, *_ = tile_of(LINE_X, 4810000.0, 13)
        blocks = begun(self.dir)
        TW.paint_valley_block(StubPainter(), blocks, x, y, 80)
        begun(self.dir)                                                 # the same inputs: it resumes
        newer = stub_plan({"naip": "2026"})                            # an input changed since
        with self.assertRaises(TW.TileError) as ctx:
            begun(self.dir, newer)
        self.assertIn("Paint into a new folder", str(ctx.exception))
        with self.assertRaises(TW.TileError) as ctx:                   # ... or changed between paint and assemble
            TW.assemble(self.dir, newer, partial=True, log=lambda *_: None)
        self.assertIn("Paint them again", str(ctx.exception))
        # a block painted for another digest is never kept as done, nor assembled
        with open(os.path.join(blocks.dir, f"v13-{x}-{y}.json")) as f:
            idx = json.load(f)
        with open(os.path.join(blocks.dir, f"v13-{x}-{y}.json"), "w") as f:
            json.dump(dict(idx, digest="0" * 64), f)
        with self.assertRaises(TW.TileError):
            TW.paint_valley_block(StubPainter(), begun(self.dir), x, y, 80)
        with self.assertRaises(TW.TileError) as ctx:
            TW.assemble(self.dir, stub_plan(), partial=True, log=lambda *_: None)
        self.assertIn("weren't painted for", str(ctx.exception))
        # blocks with no run.json: their origin is unknown
        os.remove(os.path.join(self.dir, "run.json"))
        with self.assertRaises(TW.TileError):
            begun(self.dir)
        with self.assertRaises(TW.TileError):
            TW.assemble(self.dir, stub_plan(), partial=True, log=lambda *_: None)
        with self.assertRaises(TW.TileError):                          # a block is written for a digest
            TW.Blocks(os.path.join(self.dir, "new")).write("x", {(13, 1, 1): b"x"})

    def test_first_load_from_tile_sizes(self):
        view = [(10, x, y) for x in range(179, 183) for y in range(372, 375)]
        sizes = {t: 40000 for t in view[:-1]}
        sizes[(15, 5800, 11900)] = 30000
        est = TW.first_load(view, sizes)
        self.assertEqual(est["tiles"], 12)
        self.assertEqual(est["missing"], [[10, 182, 374]])
        self.assertEqual(est["tile_bytes"], 12 * 40000)                # a missing tile counts at its zoom's median
        self.assertEqual(est["requests"], 1 + est["leaves"] + 12)
        self.assertLessEqual(est["leaves"], 1)                         # z10's entries are all in the first leaf
        self.assertEqual(est["bytes"], 16384 + est["leaf_bytes"] + 480000)
        self.assertEqual(est["ok"], est["bytes"] <= 600000 and est["requests"] <= 14)

    def test_the_boxes_blocks_and_the_detail_blocks(self):
        near = TW.blocks_near_boxes(13)
        self.assertGreaterEqual(len(near), 10)
        self.assertLess(len(near), 120)
        d = TW.detail_blocks()
        kids = {(4 * bx + i, 4 * by + j) for bx, by in d for i in range(4) for j in range(4)}
        self.assertTrue(set(T.detail_tiles(17)) <= kids)

    def test_the_photo_inputs_name_their_versions(self):
        self.assertEqual(TW.photo_of(None, None), (None, {}))
        with self.assertRaises(TW.TileError):
            TW.photo_of(None, "dem.tif")                                # a DEM alone has nothing to normalise
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        with self.assertRaises(TW.TileError):
            TW.photo_of(d)                                              # no COG there
        for name in ("naip2025_2m.tif", "naip2025_2m.json"):
            with open(os.path.join(d, name), "w") as f:
                f.write("{}" if name.endswith("json") else "x")
        with self.assertRaises(TW.TileError):
            TW.photo_of(d)                                              # a sidecar without its sha256
        with open(os.path.join(d, "naip2025_2m.json"), "w") as f:
            json.dump({"sha256": "ab" * 32}, f)
        dem = os.path.join(d, "dem.tif")
        with open(dem, "wb") as f:
            f.write(b"elevations")
        photo, versions = TW.photo_of(d, dem)
        self.assertEqual(versions["naip-2m"], "ab" * 32)
        self.assertEqual(versions["3dep"], TW.sha256_of(dem))
        self.assertIsNone(photo.flights)
        self.assertEqual(TW.photo_of(d)[1], {"naip-2m": "ab" * 32})
        with self.assertRaises(TW.TileError):
            TW.photo_of(d, os.path.join(d, "nope.tif"))
        bal = os.path.join(d, "flight_balance.json")                    # #415: a flight balance beside the COG is part of the name
        with open(bal, "w") as f:
            json.dump({"schema": "ground.flight-balance/1", "cells": {"1:2": {"n": 3000, "med": [0.7, 0.01, 0.04]}}}, f)
        with_bal, v1 = TW.photo_of(d)
        self.assertIsNotNone(with_bal.balance)
        self.assertTrue(v1["naip-2m"].startswith("ab" * 32 + "+flight-balance."))
        with open(bal, "w") as f:
            json.dump({"schema": "ground.flight-balance/1", "cells": {"1:2": {"n": 3000, "med": [0.71, 0.01, 0.04]}}}, f)
        self.assertNotEqual(TW.photo_of(d)[1], v1)                      # another balance, another digest

    def test_the_digest_names_the_photo(self):
        a = T.digest(stub_plan({"naip-2m": "aa"}), painter="p")
        self.assertNotEqual(a, T.digest(stub_plan({"naip-2m": "bb"}), painter="p"))
        self.assertNotEqual(a, T.digest(stub_plan(), painter="p"))


if __name__ == "__main__":
    unittest.main()
