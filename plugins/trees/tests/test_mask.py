"""build.py records its building mask in build.json: the mask file's name, or null with --no-mask. A build given neither
(or both) is refused. Needs NumPy and rasterio: run it in the worker image, where a skip counts as a failure."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

try:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
except ImportError:  # pragma: no cover
    np = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "build"))


def cone(shape, cy, cx, H, R_m):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return np.clip(H * (1 - np.hypot(yy - cy, xx - cx) * 0.5 / R_m), 0, None)


@unittest.skipIf(np is None, "needs NumPy and rasterio (run in the worker image)")
class MaskRecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = self.tmp.name
        shape = (60, 60)
        ground = np.full(shape, 1800.0, np.float32)
        prof = dict(driver="GTiff", height=shape[0], width=shape[1], count=1, dtype="float32", crs="EPSG:32611",
                    transform=from_origin(560000.0, 4830000.0, 0.5, 0.5), nodata=-9999.0)
        for name, arr in (("dsm.tif", ground + cone(shape, 30, 30, 14.0, 5.0)), ("dtm.tif", ground)):
            with rasterio.open(os.path.join(d, name), "w", **prof) as ds:
                ds.write(arr.astype(np.float32), 1)
        self.mask_path = os.path.join(d, "zero_mask_t.npy")
        np.save(self.mask_path, np.zeros(shape, bool))
        self.n = 0

    def build(self, *extra):
        import build
        self.n += 1
        d = self.tmp.name
        out = os.path.join(d, f"out{self.n}")
        build.main(["--area", "t", "--dsm", os.path.join(d, "dsm.tif"), "--dtm", os.path.join(d, "dtm.tif"),
                    "--lidar", "synthetic", "--out", out, *extra])
        with open(os.path.join(out, "build.json")) as f:
            return json.load(f)

    def test_the_mask_file_name_is_recorded(self):
        rec = self.build("--mask", self.mask_path)
        self.assertEqual(rec["params"]["mask"], "zero_mask_t.npy")

    def test_no_mask_records_null(self):
        rec = self.build("--no-mask")
        self.assertIsNone(rec["params"]["mask"])

    def test_neither_mask_nor_no_mask_is_refused(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit):
            self.build()
        self.assertIn("--mask", err.getvalue())
        self.assertIn("--no-mask", err.getvalue())

    def test_both_mask_and_no_mask_is_refused(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit):
            self.build("--mask", self.mask_path, "--no-mask")
        self.assertIn("not both", err.getvalue())


if __name__ == "__main__":
    unittest.main()
