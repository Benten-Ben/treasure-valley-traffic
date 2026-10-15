"""The shrub rule, the crops, the cleaning and the split (docs/19 §19.8) on synthetic height grids. Needs NumPy and
SciPy: run it in the worker image, where a skip counts as a failure."""
import json
import math
import os
import sys
import unittest

try:
    import numpy as np
    from scipy import ndimage
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))


def model():
    import shrubs as S
    with open(os.path.join(os.path.dirname(HERE), "model", "shrub_model.json")) as f:
        return S.ShrubModel(json.load(f))


def dome(shape, cy, cx, H, W_m, a=0.6, n=2.0):
    """A shrub-shaped dome of height H and width W_m (metres) centred on cell (cy, cx)."""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    d = np.hypot(yy - cy, xx - cx) * 0.5 / (W_m / 2)
    return np.where(d <= 1, H * (1 - a * np.minimum(d, 1) ** n), 0.0).astype(np.float32)


@unittest.skipIf(np is None, "NumPy/SciPy not installed (run in the worker image)")
class ModelTest(unittest.TestCase):
    def test_the_widths_are_the_fitted_curves(self):
        m = model()
        self.assertAlmostEqual(float(m.width_m(1.0, "bush")), 1.478, places=3)
        self.assertAlmostEqual(float(m.width_m(2.0, "bush")), 1.478 * 2 ** 0.247, places=3)
        self.assertAlmostEqual(float(m.width_m(1.0, "sage")), 1.279, places=3)
        self.assertAlmostEqual(float(m.width_m(2.0, "sage")), 1.279 * 2 ** 0.154, places=3)
        self.assertEqual(float(m.width_m(0.1, "bush")), float(m.width_m(0.3, "bush")))   # held at the band's floor


@unittest.skipIf(np is None, "NumPy/SciPy not installed (run in the worker image)")
class NdviCutTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.shape = (100, 100)
        self.h = np.full(self.shape, 1.0, np.float32)
        self.ndvi = np.where(rng.random(self.shape) < 0.5, rng.normal(0.05, 0.02, self.shape),
                             rng.normal(0.45, 0.05, self.shape)).astype(np.float32)
        self.bld = np.zeros(self.shape, bool)
        self.bad = np.zeros(self.shape, bool)

    def test_otsu_splits_two_groups(self):
        import shrubs as S
        cut, d = S.ndvi_cut(self.ndvi, self.h, self.bld, self.bad)
        self.assertTrue(0.1 < cut < 0.35, cut)
        self.assertEqual(d["shrub_height_cells"], 10000)

    def test_held_between_the_roofs_and_the_canopy(self):
        import shrubs as S
        h, ndvi, bld = self.h.copy(), self.ndvi.copy(), self.bld.copy()
        h[:30], ndvi[:30] = 10.0, 0.30                 # canopy, median 0.30
        h[30:60, :50], bld[30:60, :50], ndvi[30:60, :50] = 5.0, True, 0.28   # roofs, median 0.28
        cut, d = S.ndvi_cut(ndvi, h, bld, self.bad)
        self.assertEqual((d["median_canopy"], d["median_roofs"]), (0.3, 0.28))
        self.assertTrue(0.28 <= cut <= 0.30, cut)

    def test_falls_back_with_too_few_cells(self):
        import shrubs as S
        h = np.zeros(self.shape, np.float32)
        h[:5, :5] = 1.0
        cut, d = S.ndvi_cut(self.ndvi, h, self.bld, self.bad)
        self.assertEqual(cut, S.NDVI_FALLBACK)
        self.assertIn("fallback", d["from"])


@unittest.skipIf(np is None, "NumPy/SciPy not installed (run in the worker image)")
class ShrubCellsTest(unittest.TestCase):
    def test_green_or_a_plant_by_the_lidar(self):
        import shrubs as S
        shape = (40, 40)
        h = np.zeros(shape, np.float32)
        bld = np.zeros(shape, bool)
        bad = np.zeros(shape, bool)
        alive = np.zeros(shape, bool)
        n_ag = np.zeros(shape, np.uint16)
        scat = np.full(shape, np.nan, np.float32)
        h[5, 5] = 1.0; alive[5, 5] = True                                  # green: shrub
        h[5, 10] = 1.0; n_ag[5, 10] = 3; scat[5, 10] = 0.25               # a plant to the lidar: shrub
        h[5, 15] = 1.0; n_ag[5, 15] = 2; scat[5, 15] = 0.6                # too few returns: no
        h[5, 20] = 1.0; n_ag[5, 20] = 9; scat[5, 20] = 0.1                # flat (a hard thing): no
        h[5, 25] = 2.5; alive[5, 25] = True                               # a tree's height: no
        h[5, 30] = 0.2; alive[5, 30] = True                               # below the band: no
        h[5, 35] = 1.0; alive[5, 35] = True; bad[5, 35] = True            # no lidar: no
        bld[20:30, 20:30] = True; h[20:30, 20:30] = 1.0; alive[20:30, 20:30] = True   # a building: no
        h[25, 31] = 1.0; n_ag[25, 31] = 9; scat[25, 31] = 0.5             # its 1 m ring, not green: a roof sliver
        h[25, 18] = 1.0; alive[25, 18] = True                             # its ring, green: shrub
        shrub, band = S.shrub_cells(h, bld, bad, alive, n_ag, scat)
        self.assertEqual(set(zip(*np.nonzero(shrub))), {(5, 5), (5, 10), (25, 18)})
        self.assertTrue(band[5, 15] and band[25, 31] and not band[5, 25] and not band[22, 22])


@unittest.skipIf(np is None, "NumPy/SciPy not installed (run in the worker image)")
class CropTest(unittest.TestCase):
    def test_pieces_mostly_in_a_crop_field_are_crop(self):
        import shrubs as S
        seg = np.zeros((40, 40), np.int32)
        seg[2:10, 2:10] = 1                        # all inside
        seg[20:24, 10:20] = 2                      # 30% inside
        seg[30:34, 10:20] = 3                      # 60% inside
        seg[36:38, 30:32] = 4                      # none inside
        crop = np.zeros(seg.shape, bool)
        crop[0:12, 0:12] = True
        crop[20:24, 10:13] = True
        crop[30:34, 10:16] = True
        self.assertEqual(S.crop_pieces(seg, crop).tolist(), [False, True, False, True, False])
        self.assertFalse(S.crop_pieces(seg, None).any())

    def test_a_fields_fringe_goes_with_its_field(self):
        """Pieces just past the crop cover's edge go when their clump is mostly crop and they lie mostly within 10 m
        of it; farther out, or in a clump mostly not crop, they stay."""
        import shrubs as S
        seg = np.zeros((40, 120), np.int32)
        seg[10:30, 0:40] = 1                       # in the crop cover
        seg[15:25, 40:46] = 2                      # 0-3 m past it
        seg[15:25, 46:90] = 3                      # 3-25 m past it: a third within 10 m
        crop = np.zeros(seg.shape, bool)
        crop[:, 0:40] = True
        self.assertEqual(S.crop_pieces(seg, crop).tolist(), [False, True, True, False])
        seg[seg == 1] = 0
        seg[18:22, 30:40] = 1                      # a small field: the clump is mostly not crop
        self.assertEqual(S.crop_pieces(seg, crop).tolist(), [False, True, False, False])

    def crop_and_shrubs(self, crop_cols, shrub_rows, shrub_cols, cover_cols=None, seed=4):
        """An even crop 0.8 m tall over crop_cols (a field; the crop cover over cover_cols, crop_cols by default),
        joined into one clump with tall, uneven shrubs over shrub_rows x shrub_cols outside it. Returns (h, m, crop)."""
        rng = np.random.default_rng(seed)
        h = np.zeros((60, 220), np.float32)
        h[10:50, crop_cols] = 0.8 + rng.normal(0, 0.03, (40, crop_cols.stop - crop_cols.start))
        h[shrub_rows, shrub_cols] = rng.uniform(1.0, 1.8, (shrub_rows.stop - shrub_rows.start,
                                                           shrub_cols.stop - shrub_cols.start))
        crop = np.zeros(h.shape, bool)
        crop[:, cover_cols or crop_cols] = True
        m = (h >= 0.3) & (h < 2.4)
        self.assertEqual(ndimage.label(m, structure=np.ones((3, 3)))[1], 1)     # one clump
        return h, m, crop

    def test_the_crop_cut_follows_the_fields_edge(self):
        """A crop field whose outer 4 m fall outside the crop cover, and a hedgerow running on from it: the field goes
        with its fringe, and the hedgerow stays but for its first 10 m (a clump test called it all a crop)."""
        import shrubs as S
        h, m, crop = self.crop_and_shrubs(slice(0, 58), slice(27, 33), slice(58, 216), cover_cols=slice(0, 50))
        found, why, dropped = S.split(h, m, np.ones(h.shape, bool), h, model(), crop=crop)
        self.assertGreater(dropped["crop"], 20)
        self.assertGreater(float((why[12:48, 2:56] == S.WHY["crop"]).mean()), 0.98)    # the fringe too
        self.assertFalse([s for s in found if s["col"] < 66])
        self.assertGreaterEqual(len([s for s in found if s["col"] >= 74]), 25)
        self.assertFalse((why[27:33, 76:216] == S.WHY["crop"]).any())

    def test_a_small_field_next_to_big_shrubland_is_still_a_crop(self):
        """The other way round: a small crop field touching a large shrubland outside it goes (a clump test kept the
        crop as shrubs, the clump being mostly outside)."""
        import shrubs as S
        h, m, crop = self.crop_and_shrubs(slice(0, 20), slice(5, 55), slice(20, 110))
        found, why, dropped = S.split(h, m, np.ones(h.shape, bool), h, model(), crop=crop)
        self.assertGreater(float((why[12:48, 0:16] == S.WHY["crop"]).mean()), 0.98)
        self.assertFalse([s for s in found if s["col"] < 16])
        self.assertGreater(len([s for s in found if s["col"] >= 22]), 50)

    def test_the_field_rule_finds_an_even_green_crop(self):
        import shrubs as S
        rng = np.random.default_rng(2)
        shape = (200, 200)
        h = np.zeros(shape, np.float32)
        alive = np.zeros(shape, bool)
        bld = np.zeros(shape, bool)
        h[0:100, 0:100] = 0.8 + rng.normal(0, 0.05, (100, 100))   # four blocks of an even green crop
        alive[0:100, 0:100] = True
        h[120:170, 120:170] = rng.uniform(0.3, 2.3, (50, 50))     # uneven: shrubland
        alive[120:170, 120:170] = True
        h[150:200, 0:50] = 0.8 + rng.normal(0, 0.05, (50, 50))    # even and green, but a tree stands in it
        alive[150:200, 0:50] = True
        h[170, 20] = 6.0
        field, first, joined = S.field_rule(h, bld, alive)
        self.assertEqual(first, 4)
        self.assertTrue(field[0:100, 0:100].all())
        self.assertFalse(field[120:170, 120:170].any())
        self.assertFalse(field[150:200, 0:50].any())


@unittest.skipIf(np is None, "NumPy/SciPy not installed (run in the worker image)")
class SplitTest(unittest.TestCase):
    def run_split(self, h, alive=None, bld=None):
        import shrubs as S
        alive = np.ones(h.shape, bool) if alive is None else alive
        bld = np.zeros(h.shape, bool) if bld is None else bld
        m = (h >= 0.3) & (h < 2.4) & ~bld
        treeh = np.where(bld, 0, h)
        return S.split(h, m, alive, treeh, model())

    def test_one_bush_is_one_shrub(self):
        h = dome((40, 40), 20, 20, 1.2, 1.6)
        found, why, dropped = self.run_split(h)
        self.assertEqual(len(found), 1)
        s = found[0]
        self.assertEqual(s["look"], "bush")
        self.assertAlmostEqual(s["height_m"], 1.2, places=2)
        self.assertAlmostEqual(s["row"], 20, delta=0.5)
        self.assertAlmostEqual(s["col"], 20, delta=0.5)
        w0 = float(model().width_m(s["height_m"], "bush"))
        self.assertTrue(w0 * math.exp(-2 * 0.179) - 1e-6 <= s["width_m"] <= w0 * math.exp(2 * 0.179) + 1e-6)
        self.assertEqual(dropped, {"crop": 0, "speck": 0, "skirt": 0, "gap": 0})

    def test_not_green_is_sage(self):
        h = dome((40, 40), 20, 20, 0.9, 1.4)
        found, _, _ = self.run_split(h, alive=np.zeros(h.shape, bool))
        self.assertEqual([s["look"] for s in found], ["sage"])

    def test_specks_go(self):
        import shrubs as S
        h = np.zeros((20, 20), np.float32)
        h[3, 3] = 1.0                       # one cell
        h[10, 10:12] = 0.5                  # two cells under 0.6 m
        h[15, 10:12] = 0.8                  # two cells, taller: kept
        found, why, dropped = self.run_split(h)
        self.assertEqual(dropped["speck"], 2)
        self.assertEqual(len(found), 1)
        self.assertEqual(why[3, 3], S.WHY["speck"])
        self.assertEqual(why[15, 10], S.WHY["shrub"])

    def test_a_crowns_skirt_goes(self):
        import shrubs as S
        h = dome((60, 60), 30, 30, 12.0, 10.0, a=0.95)    # a tree whose edge falls into the shrub band
        found, why, dropped = self.run_split(h)
        self.assertEqual(found, [])
        self.assertGreaterEqual(dropped["skirt"], 1)
        self.assertTrue(np.isin(why[(h >= 0.3) & (h < 2.4)], [S.WHY["skirt"], S.WHY["speck"]]).all())

    def test_a_gap_in_a_crown_goes(self):
        import shrubs as S
        h = np.full((40, 40), 8.0, np.float32)            # closed canopy
        hole = dome((40, 40), 20, 20, 1.6, 8.0, a=0.5)    # a 5 m hole where the lidar saw lower leaves, one top
        h[15:25, 15:25] = hole[15:25, 15:25]
        found, why, dropped = self.run_split(h)
        self.assertEqual(found, [])
        self.assertEqual(dropped, {"crop": 0, "speck": 0, "skirt": 0, "gap": 1})
        self.assertEqual(why[20, 20], S.WHY["gap"])

    def test_a_hedge_is_a_row_of_bushes(self):
        h = np.zeros((30, 120), np.float32)
        for c in range(12, 110, 3):                       # 50 m of 1.5 m bumps, 1.0-1.3 m tall
            h = np.maximum(h, dome(h.shape, 15, c, 1.0 + 0.3 * ((c // 3) % 2), 1.8))
        found, why, dropped = self.run_split(h)
        self.assertTrue(20 <= len(found) <= 60, len(found))
        self.assertTrue(all(s["look"] == "bush" for s in found))
        self.assertTrue(all(13 <= s["row"] <= 17 for s in found))
        self.assertLess(max(np.diff(sorted(s["col"] for s in found))), 8)   # no gap along the hedge over 4 m

    def test_two_touching_bushes_are_two_shrubs(self):
        h = np.maximum(dome((40, 50), 20, 20, 1.6, 1.7), dome((40, 50), 20, 23, 1.0, 1.45))   # model-sized
        found, _, _ = self.run_split(h)
        self.assertEqual(len(found), 2)
        self.assertEqual(sorted(round(s["height_m"], 1) for s in found), [1.0, 1.6])
        self.assertLess(abs(min(s["col"] for s in found) - 20), 1.5)

    def test_wide_clumps_split_into_model_sized_shrubs(self):
        h = np.zeros((80, 80), np.float32)
        h[20:60, 20:60] = 0.6                             # a 20 m square of low, flat shrubs
        found, _, _ = self.run_split(h, alive=np.zeros(h.shape, bool))
        self.assertGreater(len(found), 50)
        w = float(model().width_m(0.6, "sage"))
        for s in found:
            self.assertLessEqual(s["width_m"], w * math.exp(2 * 0.167) + 1e-6)

    def test_the_score_rebuilds_the_shrubs(self):
        import shrubs as S
        h = np.maximum(dome((60, 60), 15, 15, 1.2, 1.6), dome((60, 60), 40, 40, 0.8, 1.3))
        found, why, _ = self.run_split(h)
        sc = S.score(h, why == S.WHY["shrub"], found, model())
        self.assertGreater(sc["kept_cells_covered"], 0.6)
        self.assertLess(sc["height_error_m"], 0.5)
        counts = S.summarise(found, 0.09)
        self.assertEqual(counts["shrubs"], 2)
        self.assertEqual(counts["bush"], 2)


if __name__ == "__main__":
    unittest.main()
