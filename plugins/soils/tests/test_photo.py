"""The photo statistics' arithmetic (plugins/soils/build/photo.py) on synthetic arrays. Needs NumPy and SciPy: skipped
where they're missing (the ingest image); on the VM, `worker-test -C <checkout> plugins.soils.tests.test_photo`,
where a skip fails.
"""

import os
import sys
import unittest

try:
    import numpy as np
    import scipy  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)


@unittest.skipIf(np is None, "NumPy and SciPy not installed")
class ColourTest(unittest.TestCase):
    def setUp(self):
        import photo
        self.P = photo

    def test_oklab_matches_the_map_and_transit_code(self):
        from plugins.transit.ingest import route_colors as rc
        for hexc in ("#000000", "#ffffff", "#989088", "#b9a07f", "#748357", "#2b2a33"):
            r, g, b = (np.array([[int(hexc[i:i + 2], 16)]], np.uint8) for i in (1, 3, 5))
            L, a, bb = self.P.colour(r, g, b)
            want = rc.oklab(hexc)
            for got, w in zip((L[0, 0], a[0, 0], bb[0, 0]), want):
                self.assertAlmostEqual(float(got), w, places=5)
        self.assertEqual(self.P.oklab_to_srgb(rc.oklab("#989088")), (0x98, 0x90, 0x88))
        self.assertAlmostEqual(self.P.delta_e((0.5, 0, 0), (0.53, 0.04, 0)), 5.0, places=6)

    def test_ndvi_and_the_flight_curves(self):
        nir = np.array([[200, 100, 0, 50]], np.uint8)
        red = np.array([[100, 100, 0, 150]], np.uint8)
        raw = self.P.ndvi(nir, red)
        np.testing.assert_allclose(raw, [[1 / 3, 0, 0, -0.5]], atol=1e-6)
        day1 = self.P.Curve([-1, 0, 1], [-1, 0.2, 1], "a")
        day2 = self.P.Curve([-1, 1], [-1, 1], "b")
        flight = np.array([[1, 2, 0, 1]], np.uint8)
        out = self.P.normalised_ndvi(raw, flight, [day1, day2])
        self.assertAlmostEqual(float(out[0, 0]), 0.2 + 0.8 / 3, places=5)
        self.assertAlmostEqual(float(out[0, 1]), 0.0, places=6)
        self.assertTrue(np.isnan(out[0, 2]))                          # no flight, no value
        self.assertAlmostEqual(float(out[0, 3]), -0.4, places=5)
        with self.assertRaises(self.P.PhotoError):
            self.P.Curve([0, 0, 1], [0, 1, 2])
        with self.assertRaises(self.P.PhotoError):
            self.P.Curve([0, 1], [1, 0])

    def test_ndvi_coding_for_the_cog(self):
        v = np.array([-1.0, 0.0, 1.0, 0.5, np.nan, -2.0], np.float32)
        code = self.P.encode_ndvi(v)
        self.assertEqual(code.tolist(), [1, 128, 255, 192, 0, 1])
        back = self.P.decode_ndvi(code)
        np.testing.assert_allclose(back[:4], [-1, 0, 1, 64 / 127], atol=1e-6)
        self.assertTrue(np.isnan(back[4]))


@unittest.skipIf(np is None, "NumPy and SciPy not installed")
class MaskTest(unittest.TestCase):
    def setUp(self):
        import photo
        self.P = photo

    def test_inner_keeps_pixels_ten_metres_from_any_edge(self):
        pid = np.ones((60, 60), np.int64)
        pid[:, 40:] = 2
        pid[0:3, :] = 0                               # no polygon along the top
        ok = self.P.inner(pid, 0.6)                   # 10 m is 17 pixels at 0.6 m
        self.assertFalse(ok[:, 23:57].any())          # within 17 pixels of the edge at column 40, on either side
        self.assertTrue(ok[30, 22])                   # its centre is 10.5 m from the edge
        self.assertFalse(ok[30, 23])                  # 9.9 m
        self.assertTrue(ok[30, 57])
        self.assertFalse(ok[19, 10])                  # 17 rows below the no-polygon rows
        self.assertTrue(ok[20, 10])
        self.assertFalse(ok[pid == 0].any())

    def test_dark_rule(self):
        L = np.array([0.4, 0.4, 0.4, 0.6, 0.45], np.float32)
        a = np.array([0.0, 0.03, 0.03, 0.0, 0.03], np.float32)
        b = np.array([0.0, 0.03, -0.01, 0.0, 0.01], np.float32)
        # neutral and dark; coloured and dark (soil in shade, not blue); blue and dark; neutral but light; coloured
        self.assertEqual(self.P.dark(L, a, b).tolist(), [True, False, True, False, False])

    def test_sample_mask_gives_the_first_reason(self):
        n = len(self.P.REASONS) + 1
        ones = np.ones(n, bool)
        valid, pid, inner = ones.copy(), np.ones(n, np.int64), ones.copy()
        covered, flight = np.zeros(n, bool), np.ones(n, np.uint8)
        ndvi = np.full(n, 0.1, np.float32)
        july = np.full(n, 0.2, np.float32)
        L, a, b = np.full(n, 0.8, np.float32), np.full(n, 0.01, np.float32), np.full(n, 0.03, np.float32)
        crop = ones.copy()
        valid[1] = False                              # one pixel per reason, in REASONS order
        pid[2] = 0
        inner[3] = False
        covered[4] = True
        flight[5] = 0
        july[6] = np.nan
        ndvi[7] = 0.5
        L[8], a[8], b[8] = 0.3, 0.0, 0.0
        crop[9] = False
        U, why = self.P.sample_mask(valid, pid, inner, covered, flight, ndvi, july, L, a, b, crop)
        self.assertEqual(U.tolist(), [True] + [False] * (n - 1))
        self.assertEqual(why.tolist(), [-1] + list(range(n - 1)))
        july[0] = 0.35                                # green in July: green, whatever the photo says
        U, why = self.P.sample_mask(valid, pid, inner, covered, flight, ndvi, july, L, a, b, crop)
        self.assertEqual(self.P.REASONS[why[0]], "green")

    def test_crop_rule(self):
        cover = np.array([0, 1, 2, 3, 4, 5, 6, 0], np.uint8)
        field_drop = np.array([False] * 7 + [True])
        self.assertEqual(self.P.crop_ok(cover, field_drop).tolist(),
                         [True, True, False, False, True, False, True, False])

    def test_configure_changes_the_dark_rule_and_records_it(self):
        P = self.P
        old = (P.DARK_L, P.NEUTRAL_C, P.BLUE_B)
        try:
            P.configure(dark_l=0.7, blue_b=None)
            self.assertEqual((P.DARK_L, P.RULES["dark_l"]), (0.7, 0.7))
            self.assertTrue(P.dark(np.array([0.6]), np.array([0.0]), np.array([0.0]))[0])
            with self.assertRaises(P.PhotoError):
                P.configure(green_cut=0.5)
        finally:
            P.configure(dark_l=old[0], neutral_c=old[1], blue_b=old[2])


@unittest.skipIf(np is None, "NumPy and SciPy not installed")
class AccumulatorTest(unittest.TestCase):
    def setUp(self):
        import photo
        self.P = photo
        rng = np.random.default_rng(7)
        self.key = rng.integers(0, 3, 20000)
        self.L = rng.normal(0.7, 0.05, 20000).astype(np.float32)
        self.a = rng.normal(0.01, 0.01, 20000).astype(np.float32)
        self.b = (rng.normal(0.04, 0.01, 20000) + 0.2 * (self.L - 0.7)).astype(np.float32)

    def test_sums_give_the_median_and_covariance(self):
        acc = self.P.Accumulator(4)
        acc.add(self.key, self.L, self.a, self.b)
        self.assertEqual(acc.n.tolist()[3], 0)
        for k in range(3):
            sel = self.key == k
            st = self.P.stats(acc.n[k], acc.s[k], acc.h[k])
            want = np.cov(np.vstack([self.L[sel], self.a[sel], self.b[sel]]).astype(np.float64))
            np.testing.assert_allclose(st["cov"], [want[0, 0], want[0, 1], want[0, 2], want[1, 1], want[1, 2],
                                                   want[2, 2]], rtol=1e-6, atol=1e-10)
            for c, v in enumerate((self.L, self.a, self.b)):
                width = (self.P.RANGES[c][1] - self.P.RANGES[c][0]) / self.P.BINS
                self.assertAlmostEqual(st["med"][c], float(np.median(v[sel])), delta=width)
            self.assertAlmostEqual(st["l_p10"], float(np.percentile(self.L[sel], 10)), delta=0.004)
        self.assertIsNone(self.P.stats(0, acc.s[3], acc.h[3]))

    def test_sparse_merge_is_the_same_as_adding_at_once(self):
        whole = self.P.Accumulator(3)
        whole.add(self.key, self.L, self.a, self.b)
        whole.add_texture(2, self.key[:100], self.L[:100], self.a[:100])
        merged = self.P.Accumulator(3)
        for part in (slice(0, 5000), slice(5000, 20000)):
            local = self.P.Accumulator(3)
            local.add(self.key[part], self.L[part], self.a[part], self.b[part])
            if part.start == 0:
                local.add_texture(2, self.key[:100], self.L[:100], self.a[:100])
            merged.merge(local.sparse("c_"), "c_")
        for k in ("n", "s", "h", "tn", "tl", "tc"):
            np.testing.assert_allclose(getattr(merged, k), getattr(whole, k), rtol=1e-12)
        # Local rows with labels, merged through a key map.
        local = self.P.Accumulator(2)
        local.add(np.array([0, 1, 1]), np.array([0.5, 0.6, 0.7], np.float32), np.zeros(3, np.float32),
                  np.zeros(3, np.float32))
        z = local.sparse("p_", labels=np.array([40, 7]))
        self.assertEqual(z["p_keys"].tolist(), [40, 7])
        glob = self.P.Accumulator(3)
        keymap = np.full(50, -1)
        keymap[[7, 40]] = [2, 0]
        glob.merge(z, "p_", keymap=keymap)
        self.assertEqual(glob.n.tolist(), [1, 0, 2])

    def test_quantiles_from_a_histogram(self):
        h = np.zeros(self.P.BINS)
        h[100] = 10
        mid = self.P.RANGES[0][0] + 100.5 / self.P.BINS
        self.assertAlmostEqual(self.P.hist_quantile(h, 0.5, 0), mid, places=6)
        self.assertIsNone(self.P.hist_quantile(np.zeros(self.P.BINS), 0.5, 0))
        # Out-of-range values land in the end bins rather than being lost.
        self.assertEqual(self.P.bins(np.array([-5.0, 5.0]), 1).tolist(), [0, self.P.BINS - 1])


@unittest.skipIf(np is None, "NumPy and SciPy not installed")
class TextureTest(unittest.TestCase):
    def setUp(self):
        import photo
        self.P = photo

    def test_energy_moves_to_the_octave_of_the_pattern(self):
        # Stripes with a 6 m period (10 pixels of 0.6 m) put their energy in the 2.4-4.8 m octaves, not 19.2 m.
        x = np.arange(256)
        stripes = np.tile(0.05 * np.sin(2 * np.pi * x / 10.0), (256, 1)).astype(np.float32)
        U = np.ones((256, 256), bool)
        e = self.P.octave_energy(stripes, U)
        self.assertEqual(len(e), 5)
        self.assertEqual(int(np.argmax(e)), 1)
        self.assertLess(e[4], e[1] / 50)
        flat = self.P.octave_energy(np.full((256, 256), 0.7, np.float32), U)
        self.assertTrue(all(v < 1e-12 for v in flat))

    def test_covered_pixels_never_leak_in(self):
        rng = np.random.default_rng(3)
        img = (0.7 + 0.01 * rng.standard_normal((256, 256))).astype(np.float32)
        U = np.ones((256, 256), bool)
        U[:, 120:136] = False                     # a road: covered
        with_road = img.copy()
        with_road[:, 120:136] = 0.1               # dark asphalt under the mask
        a = self.P.octave_energy(img, U)
        b = self.P.octave_energy(with_road, U)
        np.testing.assert_allclose(a, b, rtol=1e-4)

    def test_support_rule_and_levels(self):
        U = np.zeros((64, 64), bool)
        U[16:48, 16:48] = True
        img = np.zeros((64, 64), np.float32)
        levels = list(self.P.octaves([img], U, 0.6))
        self.assertEqual([lv[1] for lv in levels], [0.6, 1.2, 2.4, 4.8, 9.6])
        self.assertEqual([lv[3].shape for lv in levels], [(64, 64), (32, 32), (16, 16), (8, 8), (4, 4)])
        counted0 = levels[0][3]
        self.assertTrue(counted0[32, 32] and not counted0[16, 16] and not counted0[0, 0])
        self.assertFalse(levels[4][3].any())      # 19.2 m support doesn't fit in a 19 m square at 75%
        with self.assertRaises(self.P.PhotoError):
            list(self.P.octaves([img[:60]], U[:60], 0.6))


@unittest.skipIf(np is None, "NumPy and SciPy not installed")
class GridTest(unittest.TestCase):
    def setUp(self):
        import photo
        self.P = photo

    def test_area_means_onto_the_2m_grid(self):
        # 0.6 m pixels from 0.3 m past a 2 m edge; brute force on a 0.1 m lattice gives the same sums.
        rng = np.random.default_rng(1)
        v = rng.random((23, 31)).astype(np.float32)
        Ax = self.P.overlap(0.3, 0.6, 31, 0.0, 2.0, 9)
        Ay = self.P.overlap(0.9, 0.6, 23, 0.0, 2.0, 7)
        got = self.P.area_sum(Ay, Ax, v)
        fine = np.repeat(np.repeat(v, 6, axis=0), 6, axis=1)          # 0.1 m cells
        fy, fx = 9, 3                                                  # 0.9 m and 0.3 m in 0.1 m cells
        want = np.zeros((7, 9))
        for j in range(7):
            for i in range(9):
                r0, r1 = max(j * 20 - fy, 0), min((j + 1) * 20 - fy, fine.shape[0])
                c0, c1 = max(i * 20 - fx, 0), min((i + 1) * 20 - fx, fine.shape[1])
                if r1 > r0 and c1 > c0:
                    want[j, i] = fine[r0:r1, c0:c1].sum() * 0.01
        np.testing.assert_allclose(got, want, rtol=1e-5, atol=1e-6)
        ones = self.P.area_sum(Ay, Ax, np.ones((23, 31), np.float32))
        self.assertAlmostEqual(float(ones[2, 2]), 4.0, places=5)       # a cell fully inside: 4 m2


if __name__ == "__main__":
    unittest.main()
