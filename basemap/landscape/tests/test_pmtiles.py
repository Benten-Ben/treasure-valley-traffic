"""The PMTiles reader and metadata rewriter (pmtiles.py): standard library only, against archives written by
tests/pmt.py. test_bake.py reads GDAL's own archives with it too (worker image)."""

import gzip
import json
import os
import random
import shutil
import tempfile
import unittest

from basemap.landscape import pmtiles as P
from basemap.landscape.tests import pmt


def tiles_at(z, xs, ys, size=40, seed=1):
    rnd = random.Random(seed)
    return {(z, x, y): bytes(rnd.randrange(256) for _ in range(size + (x + y) % 7)) for x in xs for y in ys}


class TileIdTest(unittest.TestCase):
    def test_known_ids(self):
        # The spec's examples: zoom 0 is id 0; zoom 1 runs (0,0), (0,1), (1,1), (1,0) along the curve.
        self.assertEqual([P.tile_id(*t) for t in [(0, 0, 0), (1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0),
                                                  (2, 0, 0)]], [0, 1, 2, 3, 4, 5])
        self.assertEqual(P.tile_id(16, 0, 0), (4 ** 16 - 1) // 3)

    def test_round_trip(self):
        rnd = random.Random(7)
        for z in range(0, 21):
            for _ in range(50):
                n = 1 << z
                t = (z, rnd.randrange(n), rnd.randrange(n))
                self.assertEqual(P.zxy(P.tile_id(*t)), t)

    def test_outside_the_zoom(self):
        with self.assertRaises(ValueError):
            P.tile_id(2, 4, 0)


class ReadTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_header_metadata_and_tiles(self):
        tiles = tiles_at(16, range(11613, 11618), range(23923, 23929))
        tiles.update(tiles_at(8, [45], [93], size=300))
        path = pmt.write(os.path.join(self.dir, "a.pmtiles"), tiles, {"name": "x", "vector_layers": []},
                         minzoom=8, maxzoom=16)
        h = P.read_header(path)
        self.assertEqual((h.min_zoom, h.max_zoom, h.tile_type_name, h.tile_compression_name), (8, 16, "mvt", "gzip"))
        self.assertAlmostEqual(h.bounds[0], -117.05)
        self.assertEqual(P.read_metadata(path)["name"], "x")
        sizes = P.tile_sizes(path)
        self.assertEqual(sizes, {t: len(b) for t, b in tiles.items()})
        for t, b in tiles.items():
            self.assertEqual(P.tile_data(path, *t), b)
        self.assertIsNone(P.tile_data(path, 16, 0, 0))
        some = [(16, 11613, 23923), (16, 11617, 23928), (16, 1, 1)]
        self.assertEqual(P.tile_sizes(path, some), {t: len(tiles[t]) for t in some[:2]})

    def test_runs_leaves_gaps_and_no_compression(self):
        tiles = tiles_at(14, range(2900, 2910), range(5980, 5990))
        same = b"the same bytes"                    # a run: zoom 1's four tiles (ids 1-4) share one tile
        tiles.update({(1, 0, 0): same, (1, 0, 1): same, (1, 1, 1): same, (1, 1, 0): same})
        for internal in (1, 2):
            path = pmt.write(os.path.join(self.dir, f"b{internal}.pmtiles"), tiles, {"k": internal},
                             leaf_size=7, internal=internal, gap=True)
            es = P.entries(path)
            self.assertTrue(any(e.run_length == 4 for e in es))
            self.assertGreater(P.read_header(path).leaf_length, 0)
            self.assertEqual(P.tile_sizes(path), {t: len(b) for t, b in tiles.items()})
            self.assertEqual(P.tile_data(path, 1, 1, 0), same)
            self.assertEqual(P.read_metadata(path), {"k": internal})

    def test_rewrite_metadata_keeps_every_tile(self):
        tiles = tiles_at(15, range(5806, 5812), range(11962, 11966))
        tiles[(9, 90, 186)] = b"z9"
        for leaf in (None, 5):
            src = pmt.write(os.path.join(self.dir, f"src{leaf}.pmtiles"), tiles, {"old": True}, leaf_size=leaf)
            dst = os.path.join(self.dir, f"dst{leaf}.pmtiles")
            P.write_with_metadata(src, dst, {"new": "metadata", "tvt": {"landscape": {"status": "baked"}}})
            self.assertEqual(P.read_metadata(dst), {"new": "metadata", "tvt": {"landscape": {"status": "baked"}}})
            a, b = P.read_header(src), P.read_header(dst)
            for k in ("root_length", "leaf_length", "data_length", "addressed_tiles", "tile_entries",
                      "tile_contents", "clustered", "internal_compression", "tile_compression", "tile_type",
                      "min_zoom", "max_zoom", "bounds", "center_zoom", "center"):
                self.assertEqual(getattr(a, k), getattr(b, k), k)
            self.assertEqual(b.root_offset, P.HEADER_LEN)
            self.assertEqual(b.data_offset + b.data_length, os.path.getsize(dst))
            for t, data in tiles.items():
                self.assertEqual(P.tile_data(dst, *t), data)

    def test_damage_is_reported(self):
        path = os.path.join(self.dir, "bad.pmtiles")
        with open(path, "wb") as f:
            f.write(b"PMTiles" + bytes([2]) + bytes(119))
        with self.assertRaisesRegex(P.PMTilesError, "version 2"):
            P.read_header(path)
        with open(path, "wb") as f:
            f.write(b"not a pmtiles file at all" * 10)
        with self.assertRaisesRegex(P.PMTilesError, "magic"):
            P.read_header(path)
        good = pmt.write(os.path.join(self.dir, "good.pmtiles"), tiles_at(10, [181], [373]), {"a": 1})
        with open(good, "rb") as f:
            data = f.read()
        h = P.parse_header(data)
        with open(path, "wb") as f:
            f.write(data[:h.metadata_offset + 3])           # cut off inside the metadata
        with self.assertRaisesRegex(P.PMTilesError, "truncated"):
            P.read_metadata(path)
        with open(path, "wb") as f:                          # metadata that isn't JSON
            body = gzip.compress(b"[1, 2")
            h.metadata_length = len(body)
            h.leaf_offset = h.metadata_offset + len(body)
            h.data_offset = h.leaf_offset
            f.write(P.pack_header(h) + data[h.root_offset:h.root_offset + h.root_length] + body
                    + data[P.parse_header(data).data_offset:])
        with self.assertRaisesRegex(P.PMTilesError, "JSON"):
            P.read_metadata(path)
        self.assertEqual(json.loads(json.dumps(P.read_metadata(good))), {"a": 1})


if __name__ == "__main__":
    unittest.main()
