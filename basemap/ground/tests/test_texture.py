"""G1b's rules (texture.py) on small arrays: the noise, the sun and the light, Mahalanobis, shadows. NumPy only."""

import unittest

try:
    import numpy as np
    from basemap.ground import texture as T
except ImportError:                                  # no NumPy here
    np = None


@unittest.skipIf(np is None, "needs NumPy")
class TestNoise(unittest.TestCase):
    def test_unit_variance_and_zero_mean(self):
        xs = np.arange(0, 3000, 1.0) + 0.5
        n = T.value_noise(xs, xs, 10.0, 3)
        self.assertAlmostEqual(float(n.mean()), 0.0, delta=0.05)
        self.assertAlmostEqual(float(n.var()), 1.0, delta=0.08)

    def test_a_function_of_the_absolute_coordinates(self):
        xs = np.arange(0, 400, 2.0) + 1.0
        ys = np.arange(0, 200, 2.0) + 1.0
        whole = T.value_noise(xs, ys, 9.6, 5)
        left = T.value_noise(xs[:60], ys, 9.6, 5)
        right = T.value_noise(xs[60:], ys, 9.6, 5)
        self.assertTrue(np.array_equal(np.concatenate([left, right], axis=1), whole))
        self.assertTrue(np.array_equal(T.value_noise(xs, ys, 9.6, 5), whole))          # repeatable
        self.assertFalse(np.array_equal(T.value_noise(xs, ys, 9.6, 6), whole))         # the seed matters
        neg = T.value_noise(np.array([-3.0, -1.0]), np.array([-7.0]), 9.6, 5)           # across zero without a seam
        self.assertTrue(np.all(np.isfinite(neg)))

    def test_octave_variance_follows_the_energies(self):
        xs = np.arange(0, 6000, 2.0) + 1.0
        n = T.octave_noise(xs, xs, [0.0, 0.0, 0.0, 0.0004, 0.0], 2.0, 7)
        self.assertAlmostEqual(float(n.var()), 0.0004, delta=0.00006)
        none = T.octave_noise(xs[:50], xs[:50], [None, np.nan, 0.0, -1.0, 0.0], 2.0, 7)
        self.assertEqual(float(np.abs(none).max()), 0.0)

    def test_fine_octaves_are_skipped_on_coarse_levels(self):
        self.assertEqual(T.usable_octaves(0.5), [0, 1, 2, 3, 4])
        self.assertEqual(T.usable_octaves(2.0), [1, 2, 3, 4])          # 2.4 m lattice is finer than two 2 m cells
        self.assertEqual(T.usable_octaves(10.0), [4])
        self.assertEqual(T.usable_octaves(40.0), [])

    def test_add_texture_moves_l_and_chroma_not_hue(self):
        lab = np.full((4, 4, 3), (0.7, 0.03, 0.04), np.float32)
        out = T.add_texture(lab, np.full((4, 4), 0.02, np.float32), np.full((4, 4), 0.01, np.float32))
        self.assertTrue(np.allclose(out[..., 0], 0.72))
        hue = np.arctan2(out[..., 2], out[..., 1])
        self.assertTrue(np.allclose(hue, np.arctan2(0.04, 0.03), atol=1e-5))
        self.assertAlmostEqual(float(np.hypot(out[0, 0, 1], out[0, 0, 2])), 0.06, places=4)
        half = T.add_texture(lab, np.full((4, 4), 0.02, np.float32), np.zeros((4, 4), np.float32), weight=0.5)
        self.assertTrue(np.allclose(half[..., 0], 0.71))
        grey = T.add_texture(np.zeros((1, 1, 3), np.float32), np.zeros((1, 1)), np.full((1, 1), 0.01, np.float32))
        self.assertTrue(np.allclose(grey, 0.0))                      # no hue to push chroma along

    def test_noise_fields_are_clipped_and_weighted_per_cell(self):
        xs = np.arange(0, 100, 2.0) + 1.0
        e = np.zeros((50, 50, 5), np.float32)
        e[:, :25, 3] = 1.0                                           # left half: a huge energy
        dl, dc = T.noise_fields(xs, xs, e, np.zeros((50, 50, 5), np.float32), 2.0)
        self.assertLessEqual(float(np.abs(dl).max()), T.L_CLIP + 1e-7)
        self.assertEqual(float(np.abs(dl[:, 25:]).max()), 0.0)
        self.assertEqual(float(np.abs(dc).max()), 0.0)


@unittest.skipIf(np is None, "needs NumPy")
class TestLight(unittest.TestCase):
    def test_the_sun_over_boise(self):
        az, el = T.sun_position(T.parse_local("06/18/2025 13:30"))
        self.assertAlmostEqual(el, 69.5, delta=1.0)
        self.assertAlmostEqual(az, 169, delta=5)                      # near south, a little past noon
        az, el = T.sun_position(T.parse_local("06/18/2025 08:00"))
        self.assertAlmostEqual(el, 18.3, delta=1.0)
        self.assertTrue(60 < az < 90)                                 # in the east-northeast
        _, below = T.sun_position(T.parse_local("12/21/2025 01:00"))
        self.assertLess(below, 0)

    def test_local_times(self):
        self.assertEqual(T.parse_local("06/18/2025 13:30").hour, 19)   # MDT is UTC-6
        self.assertEqual(T.parse_local("2025-06-18").hour, 18)         # a day alone: local noon
        self.assertIsNone(T.parse_local("not a time"))
        self.assertIsNone(T.parse_local(None))

    def test_slope_and_aspect_of_a_plane(self):
        rows, cols = np.mgrid[0:20, 0:20]
        z = 100.0 - 0.5 * rows                         # falls to the south (rows run south) at 0.5 / m: faces south
        slope, aspect = T.slope_aspect(z, 1.0)
        self.assertAlmostEqual(float(np.tan(slope[10, 10])), 0.5, places=4)
        self.assertAlmostEqual(float(np.degrees(aspect[10, 10])), 180.0, places=3)
        east = 100.0 + 0.25 * cols                     # rises to the east: faces west
        slope, aspect = T.slope_aspect(east, 1.0)
        self.assertAlmostEqual(float(np.degrees(aspect[10, 10])), 270.0, places=3)
        flat_s, _ = T.slope_aspect(np.full((5, 5), 800.0), 2.0)
        self.assertEqual(float(flat_s.max()), 0.0)

    def test_illumination_gain(self):
        flat = np.zeros((1, 1), np.float32)
        g, ok = T.illumination_gain(flat, flat, 170.0, 60.0)
        self.assertAlmostEqual(float(g[0, 0]), 1.0, places=5)
        self.assertTrue(ok[0, 0])
        slope = np.full((1, 1), np.radians(20), np.float32)
        south = np.full((1, 1), np.pi, np.float32)
        north = np.zeros((1, 1), np.float32)
        gs, oks = T.illumination_gain(slope, south, 180.0, 40.0)       # facing the sun: lit more, gain under 1
        gn, okn = T.illumination_gain(slope, north, 180.0, 40.0)       # facing away: lit less, gain over 1
        self.assertLess(float(gs[0, 0]), 1.0)
        self.assertGreater(float(gn[0, 0]), 1.0)
        self.assertTrue(oks[0, 0] and okn[0, 0])
        # a pixel's brightness times its gain is the flat ground's, whichever side it faces
        el = np.radians(40)
        for aspect, g in ((south, gs), (north, gn)):
            cos_i = np.cos(slope) * np.sin(el) + np.sin(slope) * np.cos(el) * np.cos(np.radians(180.0) - aspect)
            self.assertAlmostEqual(float(cos_i[0, 0] * g[0, 0]), float(np.sin(el)), places=5)

    def test_unreliable_light_is_off(self):
        steep = np.full((1, 1), np.radians(50), np.float32)
        away = np.zeros((1, 1), np.float32)
        g, ok = T.illumination_gain(steep, away, 180.0, 30.0)          # turned from the sun
        self.assertFalse(ok[0, 0])
        self.assertEqual(float(g[0, 0]), 1.0)
        g, ok = T.illumination_gain(np.zeros((1, 1), np.float32), away, 180.0, -5.0)
        self.assertFalse(ok[0, 0])                                     # the sun below the horizon


@unittest.skipIf(np is None, "needs NumPy")
class TestVariation(unittest.TestCase):
    def setUp(self):
        self.cov = [0.0004, 0.0, 0.0, 0.0001, 0.0, 0.0001]            # sd 0.02 in L, 0.01 in a and b
        self.inv = T.inverse_covariance(T.cov_matrices([self.cov])[0])

    def test_matrices_and_distance(self):
        m = T.cov_matrices([self.cov, None, [1, 2], [np.nan] * 6])
        self.assertEqual(m[0].shape, (3, 3))
        self.assertEqual(m[1:], [None, None, None])
        self.assertIsNone(T.inverse_covariance(None))
        d = T.mahalanobis(np.array([[0.04, 0.0, 0.0], [0.0, 0.01, 0.01]]), self.inv)
        self.assertAlmostEqual(float(d[0]), 2.0, places=4)
        self.assertAlmostEqual(float(d[1]), np.sqrt(2), places=4)
        flat = T.inverse_covariance(np.zeros((3, 3)))                  # a zero spread: floored, finite
        self.assertTrue(np.all(np.isfinite(flat)))

    def test_the_weight_ramp(self):
        w = T.variation_weight(np.array([0.0, 2.5, 2.75, 3.0, 9.0]))
        self.assertTrue(np.allclose(w, [1, 1, 0.5, 0, 0]))

    def test_variation_is_kept_inside_2_5_and_gone_by_3(self):
        med = np.full((1, 4, 3), (0.7, 0.02, 0.04), np.float32)
        step = np.array([0.0, 0.04, 0.056, 0.2], np.float32)           # 0, 2, 2.8 and 10 sd in L
        photo = med + np.stack([step, 0 * step, 0 * step], axis=-1)[None]
        inv = np.broadcast_to(self.inv, (1, 4, 3, 3)).astype(np.float32)
        delta, w = T.photo_variation(photo, med, inv, np.ones((1, 4), bool))
        self.assertTrue(np.allclose(w[0], [1, 1, 0.4, 0], atol=1e-4))
        self.assertTrue(np.allclose(delta[0, :, 0], step))

    def test_off_where_not_ok_or_without_a_spread(self):
        med = np.full((1, 2, 3), 0.5, np.float32)
        inv = np.broadcast_to(self.inv, (1, 2, 3, 3)).astype(np.float32).copy()
        inv[0, 1] = np.nan
        _, w = T.photo_variation(med + 0.001, med, inv, np.array([[False, True]]))
        self.assertTrue(np.array_equal(w, np.zeros((1, 2), np.float32)))

    def test_cast_shadows_are_dark_blue_and_near_something_tall(self):
        med = np.full((9, 9, 3), (0.7, 0.02, 0.04), np.float32)
        photo = med.copy()
        photo[4, 4] = (0.5, 0.02, 0.02)                                # dark and bluer
        photo[1, 1] = (0.5, 0.02, 0.04)                                # dark, not blue (dark soil)
        photo[7, 7] = (0.7, 0.02, 0.02)                                # blue, not dark
        near = np.ones((9, 9), bool)
        s = T.shadow_cells(photo, med, near)
        self.assertTrue(s[4, 4] and s[3, 4] and s[4, 5])               # the cell and its penumbra
        self.assertFalse(s[1, 1] or s[7, 7])
        self.assertFalse(T.shadow_cells(photo, med, np.zeros((9, 9), bool))[4, 4])    # nothing tall near
        self.assertTrue(T.shadow_cells(photo, med, None)[4, 4])                       # the colour test alone

    def test_grow(self):
        m = np.zeros((5, 5), bool)
        m[2, 2] = True
        self.assertEqual(int(T.grow(m, 1).sum()), 5)
        self.assertEqual(int(T.grow(m, 0).sum()), 1)

    def test_ndvi_band_and_cluster_confirmation(self):
        ndvi, known = T.decode_ndvi(np.array([[0, 1, 128, 255]], np.uint8))
        self.assertTrue(np.array_equal(known, [[False, True, True, True]]))
        self.assertAlmostEqual(float(ndvi[0, 1]), -1.0, places=5)
        self.assertAlmostEqual(float(ndvi[0, 3]), 1.0, places=5)
        self.assertTrue(np.isnan(ndvi[0, 0]))
        ok = T.confirm_cluster(np.array([[0.5, 0.2, np.nan, 0.5]], np.float32), np.array([[True, True, True, False]]))
        self.assertTrue(np.array_equal(ok, [[True, False, False, False]]))


if __name__ == "__main__":
    unittest.main()
