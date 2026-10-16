"""The PMTiles writer (pmtw.py), read back with the bake's reader. Standard library only."""

import os
import random
import tempfile
import unittest

from basemap.ground import pmtw
from basemap.landscape import pmtiles as P


class TestWriter(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self.dir):
            os.remove(os.path.join(self.dir, name))
        os.rmdir(self.dir)

    def write(self, tiles, name="t.pmtiles", meta=None):
        path = os.path.join(self.dir, name)
        w = pmtw.Writer(path, 4, meta or {"name": "test"})
        items = list(tiles.items())
        random.Random(7).shuffle(items)                     # any order in, tile-id order out
        for (z, x, y), b in items:
            w.add(z, x, y, b)
        h = w.finish((-117.05, 43.0, -115.95, 43.85), (-116.4, 43.6, 10))
        return path, h

    def test_round_trip(self):
        tiles = {(8, 46, 92): b"a" * 10, (9, 93, 185): b"bb" * 7, (10, 186, 370): b"ccc" * 5}
        path, h = self.write(tiles)
        self.assertEqual(h.tile_type, 4)
        self.assertEqual((h.min_zoom, h.max_zoom), (8, 10))
        self.assertTrue(h.clustered)
        for (z, x, y), b in tiles.items():
            self.assertEqual(P.tile_data(path, z, x, y), b)
        self.assertIsNone(P.tile_data(path, 10, 0, 0))
        self.assertEqual(P.read_metadata(path), {"name": "test"})
        self.assertFalse(os.path.exists(path + ".tiles") or os.path.exists(path + ".part"))

    def test_repeated_tiles_are_stored_once(self):
        flat = b"flat-tile" * 20
        tiles = {(12, x, 1500): flat for x in range(740, 760)}
        tiles[(12, 760, 1500)] = b"other"
        path, h = self.write(tiles)
        self.assertEqual(h.addressed_tiles, 21)
        self.assertEqual(h.tile_contents, 2)
        self.assertLess(h.data_length, 2 * len(flat))
        for (z, x, y), b in tiles.items():
            self.assertEqual(P.tile_data(path, z, x, y), b)

    def test_many_tiles_use_leaf_directories(self):
        rnd = random.Random(1)
        tiles = {(15, 5800 + i % 150, 11900 + i // 150): rnd.randbytes(rnd.randint(1, 40)) for i in range(15000)}
        budget, leaf = pmtw.ROOT_BUDGET, pmtw.LEAF_SIZE
        pmtw.ROOT_BUDGET, pmtw.LEAF_SIZE = 600, 256          # a small root, as if the tiles were many more
        try:
            path, h = self.write(tiles)
        finally:
            pmtw.ROOT_BUDGET, pmtw.LEAF_SIZE = budget, leaf
        self.assertLessEqual(h.root_length, 600)
        self.assertGreater(h.leaf_length, 0)
        got = P.tile_sizes(path)
        self.assertEqual(len(got), len(tiles))
        for k in list(tiles)[::997]:
            self.assertEqual(P.tile_data(path, *k), tiles[k])
        first, leaves = pmtw.first_request(path)
        self.assertEqual(first, 16384)
        self.assertEqual(leaves, h.leaf_length)

    def test_twice_and_empty_are_refused(self):
        w = pmtw.Writer(os.path.join(self.dir, "x.pmtiles"))
        w.add(8, 1, 1, b"x")
        with self.assertRaises(ValueError):
            w.add(8, 1, 1, b"y")
        w.abort()
        w = pmtw.Writer(os.path.join(self.dir, "y.pmtiles"))
        with self.assertRaises(ValueError):
            w.finish((0, 0, 1, 1), (0, 0, 8))
        self.assertEqual(os.listdir(self.dir), [])

    def test_directory_encoding_matches_the_reader(self):
        entries = [P.Entry(5, 0, 10, 1), P.Entry(6, 10, 4, 3), P.Entry(20, 0, 10, 1), P.Entry(21, 14, 2, 1)]
        self.assertEqual(P.decode_directory(pmtw.encode_directory(entries)), entries)


if __name__ == "__main__":
    unittest.main()
