"""The box classes' rules (classrules.py) on synthetic arrays. Needs the worker image (NumPy, SciPy, scikit-image): the
tests skip elsewhere, and in the worker image a skip counts as a failure."""

import unittest

try:
    import numpy as np
    from basemap.ground import classrules as CR
except ImportError:                                  # outside the worker image
    np = None


def features(shape=(80, 80)):
    """Flat, bare-free, not-green ground everywhere: every feature at its quiet value."""
    z = np.zeros(shape, bool)
    return {"h": np.zeros(shape, np.float32), "bld": z.copy(), "bad": z.copy(), "edge": z.copy(),
            "rough": np.zeros(shape, np.float32), "plant": z.copy(), "kept": z.copy(), "treecue": z.copy(),
            "field": z.copy(), "p": np.full(shape, 0.30, np.float32), "dark": z.copy()}


def finish(f):
    f["edge"] = CR.edge_ring(f["bld"])
    f["rough"] = CR.roughness(f["h"], f["bld"])
    return f


@unittest.skipIf(np is None, "needs the worker image (NumPy, SciPy, scikit-image)")
class TestScheme(unittest.TestCase):
    def test_each_class_from_its_cues(self):
        f = features()
        f["bld"][2:10, 2:10] = True
        f["h"][2:10, 2:10] = 6.0
        f["h"][20:26, 20:26] = 8.0                                    # a tree
        f["h"][40:42, 40:42] = 1.0
        f["kept"][40:42, 40:42] = True                                # a kept shrub
        f["h"][50:52, 10:12] = np.array([[0.5, 1.1], [0.8, 1.4]])     # uneven band cells: not a sheet
        f["h"][50:52, 30:32] = np.array([[0.5, 1.1], [0.8, 1.4]])
        f["plant"][50:52, 30:32] = True
        f["h"][60:62, 60:62] = np.array([[0.5, 1.1], [0.8, 1.4]])
        f["p"][70:78, 2:10] = 0.05                                    # bare, pale (8 x 8 >= 16 cells)
        f["p"][70:78, 20:28] = 0.05
        f["dark"][70:78, 20:28] = True                                # ... dark: asphalt
        f["bad"][0, :] = True
        f = finish(f)
        green = np.zeros(f["h"].shape, bool)
        green[50:52, 10:12] = True                                    # green band cells
        green[30:34, 60:64] = True                                    # green flat cells
        cls = CR.scheme(f, green)
        self.assertEqual(cls[5, 5], CR.ROOF)
        self.assertEqual(cls[22, 22], CR.TREE)
        self.assertEqual(cls[40, 40], CR.SHRUB)
        self.assertEqual(cls[50, 10], CR.TALL_GREEN)
        self.assertEqual(cls[50, 30], CR.TALL_DRY)
        self.assertEqual(cls[60, 60], CR.HARD)
        self.assertEqual(cls[31, 61], CR.SHORT_GREEN)
        self.assertEqual(cls[74, 5], CR.PALE)
        self.assertEqual(cls[74, 24], CR.DARK)
        self.assertEqual(cls[40, 70], CR.SHORT_DRY)
        self.assertEqual(cls[0, 40], CR.NODATA)

    def test_small_bare_patches_stay_dry_grass(self):
        f = features()
        f["p"][10:13, 10:13] = 0.05                                   # 9 cells: under 16 even after the median
        cls = CR.scheme(finish(f), np.zeros(f["h"].shape, bool))
        self.assertEqual(cls[11, 11], CR.SHORT_DRY)

    def test_a_sheet_is_tall_grass_not_shrub(self):
        f = features()
        f["h"][10:20, 10:20] = 0.8                                    # even, low, 100 cells
        f["kept"][10:20, 10:20] = True
        cls = CR.scheme(finish(f), np.zeros(f["h"].shape, bool))
        self.assertEqual(cls[15, 15], CR.HARD)                        # not green, not a plant: a hard thing
        self.assertNotIn(CR.SHRUB, np.unique(cls[11:19, 11:19]))
        f["plant"][10:20, 10:20] = True
        cls = CR.scheme(finish(f), np.zeros(f["h"].shape, bool))
        self.assertEqual(cls[15, 15], CR.TALL_DRY)

    def test_a_straight_thin_run_is_a_wall(self):
        f = features()
        f["h"][40, 10:60] = 1.5                                       # 50 cells, one wide
        cls = CR.scheme(finish(f), np.zeros(f["h"].shape, bool))
        self.assertTrue((cls[40, 12:58] == CR.WALL).all())

    def test_roof_slivers_in_the_ring(self):
        f = features()
        f["bld"][20:30, 20:30] = True
        f["h"][20:30, 20:30] = 5.0
        f["h"][30, 20:30] = 1.0                                       # just outside, in the ring, not green
        cls = CR.scheme(finish(f), np.zeros(f["h"].shape, bool))
        self.assertEqual(cls[30, 25], CR.ROOF)

    def test_browned_band_cells_are_tall_dry_grass(self):
        f = features()
        f["h"][10:12, 10:12] = np.array([[0.5, 1.1], [0.8, 1.4]])
        browned = np.zeros(f["h"].shape, bool)
        browned[10:12, 10:12] = True
        cls = CR.scheme(finish(f), np.zeros(f["h"].shape, bool), browned)
        self.assertEqual(cls[10, 10], CR.TALL_DRY)


@unittest.skipIf(np is None, "needs the worker image (NumPy, SciPy, scikit-image)")
class TestFloor(unittest.TestCase):
    def test_under_a_tree_the_ground_around_it(self):
        cls = np.full((60, 60), CR.SHORT_GREEN, np.uint8)
        cls[:, 40:] = CR.SHORT_DRY
        cls[20:26, 20:26] = CR.TREE
        cls[10, 45] = CR.HARD
        fl = CR.floor(cls)
        self.assertEqual(fl[22, 22], CR.SHORT_GREEN)
        self.assertEqual(fl[10, 45], CR.SHORT_DRY)
        self.assertEqual(fl[0, 0], CR.SHORT_GREEN)

    def test_closed_canopy_is_forest_floor(self):
        cls = np.full((200, 200), CR.SHORT_GREEN, np.uint8)
        cls[20:180, 20:180] = CR.TREE
        fl = CR.floor(cls)
        self.assertEqual(fl[100, 100], CR.FOREST_FLOOR)
        self.assertEqual(fl[21, 100], CR.SHORT_GREEN)                 # the canopy's edge isn't closed
        self.assertEqual(CR.floor(np.full((5, 5), CR.ROOF, np.uint8))[2, 2], CR.ROOF)


@unittest.skipIf(np is None, "needs the worker image (NumPy, SciPy, scikit-image)")
class TestJuly(unittest.TestCase):
    def july(self, shape, med, mx, mn, n=6):
        return {"med": np.full(shape, med, np.float32), "max": np.full(shape, mx, np.float32),
                "min": np.full(shape, mn, np.float32), "n": np.full(shape, n, np.uint8)}

    def cells(self, shape):
        r, c = np.indices(shape)
        return (r // CR.S2_CELL) * (shape[1] // CR.S2_CELL) + c // CR.S2_CELL

    def test_a_cell_never_green_in_july_dries(self):
        shape = (40, 40)
        f = features(shape)
        f["p"][:] = 0.6                                               # green in the photo (May)
        green, browned, greened, st = CR.july_rule(finish(f), self.cells(shape), self.july(shape, 0.15, 0.18, 0.1),
                                                   np.zeros(shape, bool), T=0.7)
        self.assertFalse(green.any())
        self.assertTrue(browned.all())
        self.assertEqual(st["cells_dry_all_july"], 4)

    def test_a_cell_always_green_in_july_greens(self):
        shape = (40, 40)
        f = features(shape)
        f["p"][:] = 0.25                                              # not green in the photo
        road = np.zeros(shape, bool)
        road[5, :] = True
        green, browned, greened, st = CR.july_rule(finish(f), self.cells(shape), self.july(shape, 0.8, 0.85, 0.7),
                                                   road, T=0.7)
        self.assertTrue(green[10:, :].all())
        self.assertFalse(green[5, :].any())                           # a mapped road never greens
        self.assertFalse(browned.any())

    def test_within_the_margin_nothing_changes(self):
        shape = (40, 40)
        f = features(shape)
        f["p"][:20] = 0.6
        f["p"][20:] = 0.2
        j = self.july(shape, 0.5, 0.6, 0.4)
        j["med"][20:], j["max"][20:], j["min"][20:] = 0.35, 0.45, 0.3      # within the margin of not green
        green, browned, greened, _ = CR.july_rule(finish(f), self.cells(shape), j, np.zeros(shape, bool), T=0.7)
        self.assertTrue((green == (f["p"] >= CR.GREEN_CUT)).all())

    def test_ranked_takes_the_least_green_first(self):
        cand = np.ones((2, 4), bool)
        cell = np.array([[0, 0, 1, 1], [0, 0, 1, 1]])
        key = np.array([[4, 1, 9, 8], [3, 2, 7, 6]], float)
        out = CR.ranked(cand, cell, key, np.array([2, 1]))
        self.assertEqual(out.tolist(), [[False, True, False, False], [False, True, False, True]])

    def test_to_s2_through_the_curve(self):
        curve = {"lut_x": [-1.0, 0.0, 1.0], "lut_y": [-1.0, 0.2, 1.0]}
        out = CR.to_s2(np.array([0.0, 0.5, np.nan], np.float32), curve)
        self.assertAlmostEqual(float(out[0]), 0.2, places=6)
        self.assertAlmostEqual(float(out[1]), 0.6, places=6)
        self.assertAlmostEqual(float(out[2]), 0.2, places=6)          # no photo: the curve at 0


@unittest.skipIf(np is None, "needs the worker image (NumPy, SciPy, scikit-image)")
class TestTracks(unittest.TestCase):
    def test_a_bright_mapped_track_comes_back(self):
        cls = np.full((120, 120), CR.SHORT_DRY, np.uint8)
        line = np.zeros(cls.shape, bool)
        line[60, :] = True
        lum = np.full(cls.shape, 150.0, np.float32)
        lum[57:64, :] = 170.0                                         # the tread: brighter than the ground beside it
        out, n = CR.tracks(cls, line, lum)
        self.assertEqual(out[60, 60], CR.PALE)
        self.assertEqual(out[30, 60], CR.SHORT_DRY)
        self.assertGreater(n, 0)

    def test_an_unseen_track_stays_ground(self):
        cls = np.full((120, 120), CR.SHORT_DRY, np.uint8)
        line = np.zeros(cls.shape, bool)
        line[60, :] = True
        out, n = CR.tracks(cls, line, np.full(cls.shape, 150.0, np.float32))
        self.assertEqual(n, 0)
        self.assertTrue((out == CR.SHORT_DRY).all())

    def test_green_or_built_cells_are_left_alone(self):
        cls = np.full((120, 120), CR.SHORT_DRY, np.uint8)
        cls[55:66, 40:50] = CR.SHORT_GREEN
        line = np.zeros(cls.shape, bool)
        line[60, :] = True
        lum = np.full(cls.shape, 150.0, np.float32)
        lum[57:64, :] = 170.0
        out, _ = CR.tracks(cls, line, lum)
        self.assertEqual(out[60, 45], CR.SHORT_GREEN)


@unittest.skipIf(np is None, "needs the worker image (NumPy, SciPy, scikit-image)")
class TestCodes(unittest.TestCase):
    def test_codes_are_stable(self):
        self.assertEqual(CR.CLASSES[9], "surfaced, dark")
        self.assertEqual(CR.C["forest floor"], 13)
        self.assertNotIn(CR.ROOF, CR.CROP_MAY_BE)
        self.assertNotIn(CR.DARK, CR.CROP_MAY_BE)
        self.assertNotIn(CR.TREE, CR.CROP_MAY_BE)
        self.assertTrue(set(CR.GROUND).isdisjoint(CR.COVER))

    def test_classify_runs_end_to_end(self):
        shape = (40, 40)
        f = finish(features(shape))
        r, c = np.indices(shape)
        cell = (r // 20) * 2 + c // 20
        j = {"med": np.full(shape, 0.2, np.float32), "max": np.full(shape, 0.25, np.float32),
             "min": np.full(shape, 0.15, np.float32), "n": np.full(shape, 6, np.uint8)}
        cls, fl, st = CR.classify(f, cell, j, np.zeros(shape, bool), np.zeros(shape, bool),
                                  np.zeros(shape, np.float32))
        self.assertEqual(st["shares"], {"short dry grass": 100.0})
        self.assertTrue((fl == cls).all())


if __name__ == "__main__":
    unittest.main()
