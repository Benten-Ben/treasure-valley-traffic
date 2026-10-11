"""PMTiles v3 reading and writing (pmtiles.py): standard library only.

    python3 -m unittest discover -s basemap/sheets -t .
"""

import gzip
import os
import struct
import tempfile
import unittest

from basemap.sheets import pmtiles as PM


class TileIdTest(unittest.TestCase):
    def test_the_specs_examples(self):
        # spec v3, "Tile IDs": z0 is 0; z1's four tiles follow the Hilbert curve.
        self.assertEqual(PM.zxy_to_tileid(0, 0, 0), 0)
        self.assertEqual(PM.zxy_to_tileid(1, 0, 0), 1)
        self.assertEqual(PM.zxy_to_tileid(1, 0, 1), 2)
        self.assertEqual(PM.zxy_to_tileid(1, 1, 1), 3)
        self.assertEqual(PM.zxy_to_tileid(1, 1, 0), 4)
        self.assertEqual(PM.zxy_to_tileid(2, 0, 0), 5)

    def test_every_zoom_2_tile_once_in_curve_order(self):
        ids = sorted(PM.zxy_to_tileid(2, x, y) for x in range(4) for y in range(4))
        self.assertEqual(ids, list(range(5, 21)))
        # consecutive ids are neighbours on the curve
        where = {PM.zxy_to_tileid(3, x, y): (x, y) for x in range(8) for y in range(8)}
        for t in range(21, 21 + 63):
            (x0, y0), (x1, y1) = where[t], where[t + 1]
            self.assertEqual(abs(x0 - x1) + abs(y0 - y1), 1)

    def test_out_of_range(self):
        with self.assertRaises(PM.PMTilesError):
            PM.zxy_to_tileid(1, 2, 0)


class MercatorTest(unittest.TestCase):
    def test_tile_math(self):
        x, y = PM.lonlat_to_xy(-116.2, 43.61)
        c, r = PM.tile_of(x, y, 18)
        w, s, e, n = PM.tile_bounds(18, int(c), int(r))
        self.assertTrue(w <= x < e and s < y <= n)
        self.assertAlmostEqual(PM.pixel_m(18, 43.61), 0.2162, places=3)
        self.assertAlmostEqual(PM.pixel_m(15, 43.61), 1.730, places=2)


class RoundTripTest(unittest.TestCase):
    def test_write_then_read(self):
        tiles = {(0, 0, 0): b"zero", (1, 1, 0): b"one-one-zero", (18, 45000, 95000): b"deep",
                 (18, 45001, 95000): b"deep2"}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.pmtiles")
            PM.write(path, tiles, tile_type=4, bounds=(-117.0, 43.0, -116.0, 44.0))
            with PM.Reader(path) as r:
                h = r.header
                self.assertEqual((h["min_zoom"], h["max_zoom"], h["tile_type_name"]), (0, 18, "webp"))
                self.assertEqual(h["bounds"], (-117.0, 43.0, -116.0, 44.0))
                for (z, x, y), data in tiles.items():
                    self.assertEqual(r.get(z, x, y), data)
                self.assertIsNone(r.get(1, 0, 0))
                self.assertIsNone(r.get(18, 45002, 95000))
                self.assertIsNone(r.get(19, 0, 0))

    def test_runs_and_leaves(self):
        # A hand-made archive: a root pointing at a leaf directory, whose entry covers a run of three tiles.
        leaf = bytearray()
        for v in (1, PM.zxy_to_tileid(2, 0, 0), 3, 4, 1):     # 1 entry; id; run 3; length 4; offset 0 (+1)
            PM._put_varint(leaf, v)
        leaf = gzip.compress(bytes(leaf))
        root = bytearray()
        for v in (1, 0, 0, len(leaf), 1):                     # 1 entry; id 0; run 0 (a leaf); length; offset 0
            PM._put_varint(root, v)
        root = gzip.compress(bytes(root))
        data = b"TILE"
        r_off = PM.HEADER_LEN
        l_off = r_off + len(root)
        d_off = l_off + len(leaf)
        header = PM._HEADER.pack(PM.MAGIC, 3, r_off, len(root), d_off, 0, l_off, len(leaf), d_off, len(data),
                                 3, 1, 1, 1, 2, 1, 4, 0, 2, 0, 0, 0, 0, 0, 0, 0)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.pmtiles")
            with open(path, "wb") as f:
                f.write(header + root + leaf + data)
            with PM.Reader(path) as r:
                ids = [PM.zxy_to_tileid(2, 0, 0) + k for k in range(3)]
                got = [(z, x, y) for z, x, y in ((2, a, b) for a in range(4) for b in range(4))
                       if PM.zxy_to_tileid(z, x, y) in ids]
                self.assertEqual(len(got), 3)
                for z, x, y in got:
                    self.assertEqual(r.get(z, x, y), b"TILE")
                self.assertIsNone(r.get(2, 3, 3))

    def test_refuses_other_files(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x")
            with open(path, "wb") as f:
                f.write(b"not a pmtiles" + bytes(200))
            with self.assertRaises(PM.PMTilesError):
                PM.Reader(path)
            with open(path, "wb") as f:
                f.write(struct.pack("<7sB", b"PMTiles", 2) + bytes(200))
            with self.assertRaisesRegex(PM.PMTilesError, "version 2"):
                PM.Reader(path)


if __name__ == "__main__":
    unittest.main()
