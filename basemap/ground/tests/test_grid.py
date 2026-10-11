"""The ground grid (grid.py, spec.json): standard library only.

    python3 -m unittest discover -s basemap/ground -t .
"""

import math
import re
import unittest

from basemap.ground import grid as G


class MapGridTest(unittest.TestCase):
    def test_the_grid_is_the_map_box_on_sentinel2_pixels(self):
        # Rebuilt from the map box: its envelope in UTM 11N, widened to whole 10 m pixels (Sentinel-2's own edges).
        w, s, e, n = G.snap_out(G.envelope(G.MAP_LONLAT), 10)
        self.assertEqual((w, n), (495920, 4855750))
        self.assertEqual((G.ORIGIN_X, G.ORIGIN_Y), (495920, 4855750))
        self.assertEqual(((e - w) / 10, (n - s) / 10), (8967, 9494))
        self.assertEqual((G.COLS, G.ROWS), (8967, 9494))
        self.assertEqual(G.EXTENT, (495920, 4760810, 585590, 4855750))
        self.assertEqual(G.CRS, "EPSG:32611")

    def test_build_sh_map_box(self):
        with open(f"{G.SPEC_PATH.rsplit('/', 2)[0]}/build.sh", encoding="utf-8") as f:
            m = re.search(r"BBOX=\$\{BBOX:-([-0-9.,]+)\}", f.read())
        self.assertEqual(tuple(float(v) for v in m.group(1).split(",")), G.MAP_LONLAT)

    def test_levels_are_exact_subgrids(self):
        self.assertEqual(G.LEVELS, {"sentinel2": 10.0, "painter": 2.0, "classes": 0.5})
        self.assertEqual(G.size(10), (8967, 9494))
        self.assertEqual(G.size(2), (44835, 47470))
        self.assertEqual(G.size(0.5), (179340, 189880))
        for r in (10, 5, 2, 1, 0.5, 0.25, 20, 30):
            G.check_res(r)
        for r in (0.6, 0.3, 3, 15, 0, -2):
            with self.assertRaises(ValueError):
                G.check_res(r)

    def test_window_edges_line_up_across_levels(self):
        w10 = G.Window(10.0, 1234, 567, 100, 80)
        w2 = w10.at(2)
        self.assertEqual((w2.col, w2.row, w2.width, w2.height), (1234 * 5, 567 * 5, 500, 400))
        w05 = w10.at(0.5)
        self.assertEqual((w05.col, w05.row, w05.width, w05.height), (1234 * 20, 567 * 20, 2000, 1600))
        self.assertEqual(w10.bounds, w2.bounds)
        self.assertEqual(w10.bounds, w05.bounds)
        # a finer window that isn't on the coarser grid widens outward
        f = G.Window(0.5, 3, 7, 10, 10)
        c = f.at(10)
        self.assertEqual((c.col, c.row, c.width, c.height), (0, 0, 1, 1))
        self.assertEqual(G.Window(2.0, 5, 5, 5, 5).at(10), G.Window(10.0, 1, 1, 1, 1))

    def test_window_transform_and_bounds(self):
        w = G.Window(2.0, 10, 20, 30, 40)
        self.assertEqual(w.transform, (495940.0, 2.0, 0.0, 4855710.0, 0.0, -2.0))
        self.assertEqual(w.bounds, (495940.0, 4855630.0, 496000.0, 4855710.0))
        self.assertEqual(w.shape, (40, 30))
        self.assertEqual(w.key, "2m-r20-c10-30x40")
        self.assertEqual(G.Window(0.5, 0, 0, 1, 1).key, "0.5m-r0-c0-1x1")
        self.assertEqual(w.crs, "EPSG:32611")

    def test_snapping(self):
        b = (495925.3, 4855700.0, 495990.0, 4855744.9)
        out = G.window(b, 10)
        self.assertEqual((out.col, out.row, out.width, out.height), (0, 0, 7, 5))
        inn = G.window(b, 10, snap="in")
        self.assertEqual((inn.col, inn.row, inn.width, inn.height), (1, 1, 6, 4))
        with self.assertRaises(ValueError):
            G.window(b, 10, snap="exact")
        ex = G.window((495930, 4855700, 495990, 4855740), 10, snap="exact")
        self.assertEqual((ex.col, ex.row, ex.width, ex.height), (1, 1, 6, 4))
        with self.assertRaises(ValueError):
            G.window((495930, 4855700, 495930, 4855740), 10)

    def test_windows_tile_the_area_once_with_halos(self):
        bounds = (500000, 4800000, 500937, 4800411)
        seen = set()
        n = 0
        for core, padded in G.windows(2, 128, bounds=bounds, halo_m=21):
            n += 1
            self.assertLessEqual(core.width, 128)
            self.assertEqual(padded.col, core.col - 11)          # ceil(21 / 2) cells
            self.assertEqual(padded.width, core.width + 22)
            rows, cols = core.inner(padded)
            self.assertEqual((rows.stop - rows.start, cols.stop - cols.start), core.shape)
            for r in range(core.row, core.row + core.height):
                for c in range(core.col, core.col + core.width):
                    self.assertNotIn((r, c), seen)
                    seen.add((r, c))
        area = G.window(bounds, 2)
        self.assertEqual(len(seen), area.width * area.height)
        self.assertEqual(n, math.ceil(area.width / 128) * math.ceil(area.height / 128))

    def test_windows_cover_the_whole_grid(self):
        total = sum(c.width * c.height for c, _ in G.windows(10, 1000))
        self.assertEqual(total, G.COLS * G.ROWS)

    def test_inner_rejects_outside(self):
        with self.assertRaises(ValueError):
            G.Window(2.0, 0, 0, 10, 10).inner(G.Window(2.0, 1, 1, 10, 10))
        with self.assertRaises(ValueError):
            G.Window(2.0, 0, 0, 10, 10).inner(G.Window(10.0, 0, 0, 10, 10))

    def test_clip(self):
        self.assertEqual(G.Window(10.0, -5, -5, 10, 10).clip(), G.Window(10.0, 0, 0, 5, 5))
        self.assertIsNone(G.Window(10.0, G.COLS, 0, 3, 3).clip())

    def test_aligned(self):
        self.assertTrue(G.aligned((495920.0, 10.0, 0.0, 4855750.0, 0.0, -10.0)))
        self.assertTrue(G.aligned((566158.0, 0.5, 0.0, 4838452.0, 0.0, -0.5), 0.5))   # box a's lidar rasters
        self.assertTrue(G.aligned((566158.0, 0.5, 0.0, 4838452.0, 0.0, -0.5)))
        self.assertFalse(G.aligned((566158.0, 0.5, 0.0, 4838452.0, 0.0, -0.5), 2))     # not on the 2 m grid
        self.assertFalse(G.aligned((495920.3, 10.0, 0.0, 4855750.0, 0.0, -10.0)))
        self.assertFalse(G.aligned((495920.0, 10.0, 0.1, 4855750.0, 0.0, -10.0)))      # rotated
        self.assertFalse(G.aligned((495920.0, 10.0, 0.0, 4855750.0, 0.0, 10.0)))       # south-up
        self.assertFalse(G.aligned((566158.2, 0.2999999999, 0.0, 4838451.3, 0.0, -0.2999999999)))   # a NAIP crop

    def test_lonlat_round_trip(self):
        b = G.box("c")
        lon_w, lat_s, lon_e, lat_n = G.lonlat_of(b.utm)
        w, s, e, n = G.envelope((lon_w, lat_s, lon_e, lat_n))
        self.assertLessEqual(w, b.utm[0] + 1e-6)
        self.assertGreaterEqual(e, b.utm[2] - 1e-6)
        # the UTM envelope holds the lon/lat box, so its lon/lat envelope does too, within about 20 m
        for got, want, sign in zip((lon_w, lat_s, lon_e, lat_n), b.lonlat, (-1, -1, 1, 1)):
            self.assertGreaterEqual(sign * (got - want), -1e-9)
            self.assertLess(abs(got - want), 3e-4)

    def test_datum_policy_codes(self):
        self.assertTrue(G.same_coordinates(32611))
        self.assertTrue(G.same_coordinates(26911))       # NAIP
        self.assertTrue(G.same_coordinates(6340))        # the lidar products
        self.assertFalse(G.same_coordinates(4326))
        self.assertFalse(G.same_coordinates(5070))       # CDL's Albers needs a projection


class BoxesTest(unittest.TestCase):
    def test_ten_boxes(self):
        ids = [b.id for b in G.boxes()]
        self.assertEqual(ids, ["a", "b", "c", "d", "e", "f", "downtown", "h", "i", "j"])

    def test_box_windows_are_the_lidar_rasters(self):
        # The lidar products' sizes from the spike's inventory (0.5 m, Oct 8).
        lidar = {"a": (2932, 2920), "b": (2940, 2920), "c": (2934, 2918), "d": (2932, 2912), "e": (2926, 2904),
                 "f": (2940, 2910), "downtown": (4000, 4000), "i": (2936, 2900), "j": (2944, 2898)}
        for b in G.boxes():
            w = G.window(b.utm, 0.5, snap="exact")              # on the class grid
            self.assertEqual(w, b.window())
            if b.id in lidar:
                self.assertEqual((w.width, w.height), lidar[b.id], b.id)

    def test_box_utm_is_its_lonlat_envelope(self):
        for b in G.boxes():
            if b.lonlat is None:
                continue
            w, s, e, n = G.envelope(b.lonlat)
            self.assertEqual(b.utm, (math.floor(w), math.floor(s), math.ceil(e), math.ceil(n)), b.id)

    def test_boxes_inside_the_grid(self):
        for b in G.boxes():
            w = b.window(10)
            self.assertEqual(w.clip(), w, b.id)

    def test_unknown_box(self):
        with self.assertRaises(KeyError):
            G.box("g")


if __name__ == "__main__":
    unittest.main()
