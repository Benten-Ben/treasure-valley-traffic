"""The point cloud's cues for the shrub rule (cloud.py) on synthetic clouds: a scattered shrub, a flat roof, bare
ground and noise, written as a LAS file. Needs PDAL, NumPy and pyproj: run it in the worker image, where a skip counts
as a failure."""
import json
import os
import shutil
import sys
import tempfile
import unittest

try:
    import numpy as np
    import pdal
    import pyproj  # noqa: F401
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))

X0, Y1, PX, N = 500000.0, 4800040.0, 0.5, 80          # a 40 m square in EPSG:6340
GROUND = 100.0
DTYPE = [("X", "<f8"), ("Y", "<f8"), ("Z", "<f8"), ("Classification", "u1"), ("ReturnNumber", "u1"),
         ("NumberOfReturns", "u1")]


def synthetic_cloud(seed=3):
    """Ground every 0.25 m; a shrub (a scattered volume, 1 m across, 0.3-1.5 m up) centred 10 m east, 10 m south of
    the north-west corner; a flat roof 6 m square, 3 m up, at 25-31 m east and south; noise high over bare ground."""
    rng = np.random.default_rng(seed)
    g = np.arange(0.125, 40, 0.25)
    gx, gy = np.meshgrid(g, g)
    ground = np.zeros(gx.size, DTYPE)
    ground["X"], ground["Y"] = X0 + gx.ravel(), Y1 - gy.ravel()
    ground["Z"] = GROUND + rng.normal(0, 0.01, gx.size)
    ground["Classification"] = 2
    n = 3000
    u = rng.normal(size=(n, 3))
    u /= np.linalg.norm(u, axis=1)[:, None]
    r = rng.random(n) ** (1 / 3)
    shrub = np.zeros(n, DTYPE)
    shrub["X"] = X0 + 10 + 0.5 * r * u[:, 0]
    shrub["Y"] = Y1 - 10 + 0.5 * r * u[:, 1]
    shrub["Z"] = GROUND + 0.9 + 0.6 * r * u[:, 2]
    shrub["Classification"] = 1
    rg = np.arange(25.1, 31, 0.2)
    rx, ry = np.meshgrid(rg, rg)
    roof = np.zeros(rx.size, DTYPE)
    roof["X"], roof["Y"], roof["Z"] = X0 + rx.ravel(), Y1 - ry.ravel(), GROUND + 3.0
    roof["Classification"] = 6
    noise = np.zeros(50, DTYPE)
    noise["X"] = X0 + 30 + rng.random(50)
    noise["Y"] = Y1 - 10 - rng.random(50)
    noise["Z"] = GROUND + 50
    noise["Classification"] = 7
    pts = np.concatenate([ground, shrub, roof, noise])
    pts["ReturnNumber"] = 1
    pts["NumberOfReturns"] = 1
    return pts


def write_las(path, pts):
    p = pdal.Pipeline(json.dumps([{"type": "writers.las", "filename": path, "a_srs": "EPSG:6340",
                                   "scale_x": 0.001, "scale_y": 0.001, "scale_z": 0.001,
                                   "offset_x": "auto", "offset_y": "auto", "offset_z": "auto"}]), arrays=[pts])
    p.execute()


@unittest.skipIf(np is None, "PDAL/NumPy/pyproj not installed (run in the worker image)")
class CuesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(dir="/tmp")
        cls.las = os.path.join(cls.tmp, "cloud.las")
        write_las(cls.las, synthetic_cloud())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def cues(self, work, chunk_m=10.0, **kw):
        import cloud
        grid = cloud.Grid(X0, Y1, PX, N, N)
        dtm = np.full((N, N), GROUND, np.float32)
        return cloud.cues([self.las], grid, "EPSG:6340", dtm, np.ones((N, N), bool), os.path.join(self.tmp, work),
                          chunk_m=chunk_m, pad_m=2.0, log=lambda m: None, **kw)

    def test_a_shrub_scatters_and_a_roof_doesnt(self):
        n_ag, scat, stats = self.cues("a")
        shrub = (slice(19, 21), slice(19, 21))           # the cells around 10 m east, 10 m south
        roof = (slice(52, 60), slice(52, 60))            # inside the roof
        self.assertTrue((n_ag[shrub] >= 3).all())
        self.assertGreaterEqual(float(np.median(scat[shrub])), 0.25)
        self.assertTrue((n_ag[roof] >= 3).all())
        self.assertLess(float(np.nanmax(scat[roof])), 0.1)
        self.assertEqual(int(n_ag[60:80, 0:40].sum()), 0)            # bare ground: nothing above it
        self.assertTrue(np.isnan(scat[70, 10]))
        self.assertEqual(int(n_ag[18:24, 58:64].sum()), 0)           # noise (class 7) over bare ground is dropped
        self.assertEqual(stats["above_ground"], 3000 + 900)           # the shrub and the roof; not the ground

    def test_chunks_dont_change_the_cues(self):
        a, sa, _ = self.cues("b", chunk_m=10.0)
        b, sb, _ = self.cues("c", chunk_m=40.0)
        np.testing.assert_array_equal(a, b)
        np.testing.assert_allclose(sa, sb, rtol=1e-6, equal_nan=True)

    def test_a_stopped_run_picks_up_and_other_inputs_are_refused(self):
        a, sa, _ = self.cues("d")
        done = os.path.join(self.tmp, "d", "chunks")
        os.remove(os.path.join(done, sorted(os.listdir(done))[3]))
        self.assertFalse(os.listdir(os.path.join(self.tmp, "d", "spool")))   # the spool went with the last chunk
        b, sb, _ = self.cues("d")
        np.testing.assert_array_equal(a, b)
        np.testing.assert_allclose(sa, sb, rtol=1e-6, equal_nan=True)
        with self.assertRaises(SystemExit):
            self.cues("d", chunk_m=20.0)


@unittest.skipIf(np is None, "PDAL/NumPy/pyproj not installed (run in the worker image)")
class PiecesTest(unittest.TestCase):
    def test_keep_mask_drops_noise_and_withheld(self):
        import cloud
        a = np.zeros(4, [("Classification", "u1"), ("Withheld", "u1")])
        a["Classification"] = [1, 7, 18, 2]
        a["Withheld"] = [0, 0, 0, 1]
        self.assertEqual(cloud.keep_mask(a).tolist(), [True, False, False, False])
        b = np.zeros(2, [("Classification", "u1"), ("ClassFlags", "u1")])
        b["ClassFlags"] = [0, 4]
        self.assertEqual(cloud.keep_mask(b).tolist(), [True, False])

    def test_chunks_cover_the_grid_once(self):
        import cloud
        g = cloud.Grid(X0, Y1, PX, 45, 30)
        wins = [w for _, w in cloud.chunks(g, 10.0)]
        cover = np.zeros((45, 30), int)
        for r0, r1, c0, c1 in wins:
            cover[r0:r1, c0:c1] += 1
        self.assertTrue((cover == 1).all())
        self.assertEqual(cloud.window_rect(g, (0, 45, 0, 30)), g.rect)

    def test_an_ept_is_read_in_its_own_crs(self):
        import cloud
        from pyproj import Transformer
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            path = os.path.join(d, "ept.json")
            with open(path, "w") as f:
                json.dump({"srs": {"horizontal": "3857"}}, f)
            rect = (566158.0, 4836992.0, 567624.0, 4838452.0)
            b = cloud._ept_bounds(path, rect, "EPSG:6340", None)
            tr = Transformer.from_crs("EPSG:6340", "EPSG:3857", always_xy=True)
            for x in (rect[0], rect[2]):
                for y in (rect[1], rect[3]):
                    X, Y = tr.transform(x, y)
                    self.assertTrue(b[0] < X < b[2] and b[1] < Y < b[3])
            self.assertEqual(cloud.source_kind(path), "ept")
            self.assertEqual(cloud.source_kind("a/B.LAZ"), "las")
            with self.assertRaises(ValueError):
                cloud.source_kind("a/b.tif")


if __name__ == "__main__":
    unittest.main()
