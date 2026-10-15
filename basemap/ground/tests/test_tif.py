"""The GeoTIFF header reader (tif.py): standard library only. test_rasterize.py checks it against GDAL's own files in
the worker image (GTiff, COG, BigTIFF, PixelIsPoint)."""

import os
import shutil
import struct
import tempfile
import unittest

from basemap.ground import tif
from basemap.ground.tests.tiffs import write_geotiff

GT = (495920.0, 10.0, 0.0, 4855750.0, 0.0, -10.0)


class TiffHeaderTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def path(self, name):
        return os.path.join(self.dir, name)

    def test_every_layout_reads_the_same(self):
        for big in (False, True):
            for order in ("<", ">"):
                for point in (False, True):
                    for matrix in (False, True):
                        label = f"big={big} order={order} point={point} matrix={matrix}"
                        p = write_geotiff(self.path("t.tif"), 7, 5, GT, types=("uint8", "uint8", "float32"),
                                          big=big, order=order, point=point, matrix=matrix)
                        h = tif.read_header(p)
                        self.assertEqual((h.width, h.height, h.bands), (7, 5, 3), label)
                        self.assertEqual(h.sample_types, ("uint8", "uint8", "float32"), label)
                        self.assertEqual(h.transform, GT, label)
                        self.assertEqual(h.epsg, 32611, label)
                        self.assertEqual(h.pixel_is_point, point, label)
                        self.assertEqual(h.bigtiff, big, label)

    def test_half_a_cell_off_is_seen(self):
        p = write_geotiff(self.path("t.tif"), 4, 4, (495925.0, 10.0, 0.0, 4855750.0, 0.0, -10.0))
        self.assertEqual(tif.read_header(p).transform[0], 495925.0)

    def test_a_large_grid_without_pixels(self):
        p = write_geotiff(self.path("big.tif"), 8967, 9494, GT, types=("uint8",) * 3, data=False)
        self.assertLess(os.path.getsize(p), 1000)
        h = tif.read_header(p)
        self.assertEqual((h.width, h.height), (8967, 9494))

    def test_not_georeferenced_or_not_a_tiff(self):
        p = self.path("plain.tif")
        with open(p, "wb") as f:                     # a TIFF with a size and nothing else
            f.write(b"II" + struct.pack("<HI", 42, 8) + struct.pack("<H", 2)
                    + struct.pack("<HHI", 256, 4, 1) + struct.pack("<I", 3)
                    + struct.pack("<HHI", 257, 4, 1) + struct.pack("<I", 2) + struct.pack("<I", 0))
        h = tif.read_header(p)
        self.assertIsNone(h.transform)
        self.assertEqual((h.width, h.height, h.bands, h.epsg), (3, 2, 1, 0))
        for name, data in (("json.tif", b'{"a": 1}'), ("short.tif", b"II*\x00"),
                           ("cut.tif", b"II*\x00\x08\x00\x00\x00\x05\x00")):
            with open(self.path(name), "wb") as f:
                f.write(data)
            with self.assertRaises(tif.TiffError, msg=name):
                tif.read_header(self.path(name))
        with self.assertRaises(tif.TiffError):
            tif.read_header(self.path("missing.tif"))


if __name__ == "__main__":
    unittest.main()
