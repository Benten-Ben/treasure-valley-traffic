"""The tile writer's spec (tiles.py, spec.json): standard library only."""

import json
import os
import re
import shutil
import tempfile
import unittest

from basemap.ground import grid as G, inputs as I, manifest as M, tiles as T
from basemap.ground.tests.test_inputs import fgb_layer, write_export
from basemap.ground.tests.test_manifest import SSURGO

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class SpecTest(unittest.TestCase):
    def test_the_spec(self):
        self.assertEqual((T.TILE_SIZE, T.FORMAT), (512, "webp"))
        self.assertEqual(T.VALLEY_ZOOMS, (8, 15))
        self.assertEqual(T.DETAIL_ZOOMS, (16, 17))
        self.assertEqual(T.DETAIL_ZOOMS[0], T.VALLEY_ZOOMS[1] + 1)      # no gap between the two files
        self.assertTrue(T.TILES["opaque"])
        self.assertEqual(T.BUDGET["valleyDefault"], {"maxBytes": 600000, "maxRequests": 14})
        self.assertEqual(T.BUDGET["clayDefault"], {"maxBytes": 0, "maxRequests": 0})

    def test_z15_matches_the_painter(self):
        lat = (G.MAP_LONLAT[1] + G.MAP_LONLAT[3]) / 2
        self.assertAlmostEqual(T.mpp(15, lat), 1.73, places=2)          # 512 px tiles: the 2 m painter's scale
        self.assertLess(T.mpp(15, G.MAP_LONLAT[1]), G.LEVELS["painter"])
        self.assertLess(T.mpp(17, lat), G.LEVELS["classes"])             # 0.43 m: the class boxes show whole

    def test_flat_colours_are_the_apps(self):
        with open(os.path.join(REPO, "app", "src", "lib", "map", "flavors.ts"), encoding="utf-8") as f:
            m = re.search(r"export const GROUND = \{ valley: '(#[0-9a-f]{6})', clay: '(#[0-9a-f]{6})' \}", f.read())
        self.assertIsNotNone(m, "flavors.ts GROUND moved: update spec.json's flat colours and this test")
        self.assertEqual(T.FLAT, {"valley": m.group(1), "clay": m.group(2)})

    def test_budget_view_is_the_default_view(self):
        with open(os.path.join(REPO, "basemap", "build.sh"), encoding="utf-8") as f:
            text = f.read()
        centre = re.search(r"CENTER=\$\{CENTER:-([-0-9.,]+)\}", text)
        view = T.BUDGET["view"]
        if centre:
            self.assertEqual(tuple(float(v) for v in centre.group(1).split(",")[:2]), tuple(view["center"]))
        with open(os.path.join(REPO, "app", "scripts", "perf.mjs"), encoding="utf-8") as f:
            self.assertIn("viewport: { width: %d, height: %d }" % tuple(view["viewport"]), f.read())


class TileMathTest(unittest.TestCase):
    def test_tile_round_trip(self):
        z, x, y = 15, 5760, 11940
        w, s, e, n = T.tile_lonlat(z, x, y)
        xs, ys = T.tile_range((w + 1e-9, s + 1e-9, e - 1e-9, n - 1e-9), z)
        self.assertEqual((list(xs), list(ys)), ([x], [y]))
        mw, ms, me, mn = T.tile_mercator(z, x, y)
        self.assertAlmostEqual(me - mw, 2 * 20037508.342789244 / 2 ** 15, places=6)
        self.assertAlmostEqual(mn - ms, me - mw, places=6)

    def test_counts(self):
        c = T.counts()
        self.assertEqual(sorted(c["valley"]), list(range(8, 16)))
        self.assertEqual(sorted(c["detail"]), [16, 17])
        self.assertTrue(10000 < c["valley"][15] < 12000, c["valley"][15])
        self.assertLess(sum(c["valley"].values()), 16000)            # about 0.6 GB at about 40 KB a tile
        self.assertLessEqual(c["valley"][10], 20)                     # the whole map box at z10
        detail = set(T.detail_tiles(17))
        for b in G.boxes():                                           # every box is covered at z17
            xs, ys = T.tile_range(G.lonlat_of(b.utm), 17)
            self.assertTrue({(x, y) for x in xs for y in ys} <= detail, b.id)

    def test_detail_tiles_are_inside_the_valley_file(self):
        for z in range(*T.DETAIL_ZOOMS):
            parents = {(x >> (z - 15), y >> (z - 15)) for x, y in T.detail_tiles(z)}
            self.assertTrue(parents <= set(T.valley_tiles(15)))

    def test_tile_window_covers_the_tile(self):
        z, x, y = 15, 5760, 11940
        win = T.tile_window(z, x, y, G.LEVELS["painter"])
        w, s, e, n = G.envelope(T.tile_lonlat(z, x, y))
        self.assertLessEqual(win.west, w - 2 * win.res)
        self.assertGreaterEqual(win.east, e + 2 * win.res)
        self.assertLessEqual(win.south, s - 2 * win.res)
        self.assertGreaterEqual(win.north, n + 2 * win.res)
        self.assertLess(win.width, 520)                               # about 888 m / 2 m plus margins


class EntryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_flat_entry(self):
        e = T.flat_entry("Flat ground: the painted ground needs the soil survey's ground types, which isn't built yet.",
                         built="2026-10-11")
        T.check_entry(e)
        self.assertEqual(e, {"status": "flat", "reason": e["reason"], "built": "2026-10-11", "spec": 1})
        with self.assertRaises(ValueError):
            T.flat_entry("  ")

    def test_painted_entry(self):
        write_export(self.dir, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        plan = I.resolve(M.find(self.dir))
        d = T.digest(plan, painter="g1a-test")
        e = T.painted_entry(plan, d, built="2026-10-20")
        T.check_entry(e)
        self.assertEqual(e["file"], f"ground-{d[:12]}.pmtiles")
        self.assertEqual(e["detail"]["file"], f"ground-detail-{d[:12]}.pmtiles")
        self.assertEqual(e["detail"]["boxes"], [b.id for b in G.boxes()])
        self.assertEqual((e["licence"], e["republish"]), ("ODbL-1.0", "yes"))
        self.assertIn("© OpenStreetMap contributors", e["attribution"])
        self.assertIn(SSURGO["credit"], e["attribution"])
        self.assertEqual(e["inputs"], ["soils/ground@20261012T031500Z"])
        self.assertEqual(len(e["fallbacks"]), 4)
        bad = dict(e, republish="internal")
        with self.assertRaises(ValueError):
            T.check_entry(bad)
        with self.assertRaises(ValueError):
            T.painted_entry(I.resolve({}), d)                          # nothing to paint

    def test_digest_follows_the_inputs(self):
        write_export(self.dir, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        plan = I.resolve(M.find(self.dir))
        a = T.digest(plan, "v1")
        self.assertEqual(a, T.digest(plan, "v1"))
        self.assertNotEqual(a, T.digest(plan, "v2"))
        plan.choices[0].layer.spec["sha256"] = "f" * 64
        self.assertNotEqual(a, T.digest(plan, "v1"))

    def test_update_manifest_keeps_the_rest(self):
        tiles_dir = os.path.join(self.dir, "tiles")
        os.makedirs(tiles_dir)
        path = os.path.join(tiles_dir, "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"bounds": [-117.05, 43.0, -115.95, 43.85], "imagery": {"file": "imagery.pmtiles"}}, f)
        T.update_manifest(tiles_dir, T.flat_entry("Flat ground: not built yet."))
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["imagery"], {"file": "imagery.pmtiles"})
        self.assertEqual(m["ground"]["status"], "flat")
        self.assertEqual(sorted(os.listdir(tiles_dir)), ["manifest.json"])
        with self.assertRaises(ValueError):
            T.update_manifest(tiles_dir, {"status": "painted"})

    def test_first_load(self):
        reqs = [{"url": "/tiles/terrain.pmtiles", "bytes": 3_000_000}] + \
               [{"url": "/tiles/ground-0123456789ab.pmtiles", "bytes": 40_000} for _ in range(12)]
        self.assertEqual(T.first_load(reqs), (True, 480_000, 12))
        self.assertFalse(T.first_load(reqs + [{"url": "/tiles/ground-0123456789ab.pmtiles?x", "bytes": 200_000}])[0])
        self.assertFalse(T.first_load(reqs * 2)[0])
        self.assertFalse(T.first_load(reqs, look="clay")[0])
        self.assertTrue(T.first_load(reqs[:1], look="clay")[0])


if __name__ == "__main__":
    unittest.main()
