"""The standard-library GeoPackage reader (plugins/farm/ingest/gpkg.py) on the synthetic three-field file.

Run: python3 -m unittest discover -s plugins/farm/tests -t .
"""

import os
import sqlite3
import struct
import tempfile
import unittest

from plugins.farm.ingest import gpkg
from plugins.farm.tests import synthetic as S


class ReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = S.write_gpkg(os.path.join(self.tmp.name, "csb.gpkg"), S.fields())

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_the_layer_and_its_crs(self):
        with gpkg.open(self.path) as gp:
            self.assertEqual(gp.layers(), ["csb_mapbox"])
            self.assertEqual(gp.application_id, gpkg.GPKG_APPLICATION_ID)
            layer = gp.layer()
            self.assertEqual((layer.name, layer.geometry_column, layer.fid_column), ("csb_mapbox", "Shape", "OBJECTID"))
            self.assertEqual((layer.geometry_type, layer.epsg), ("MULTIPOLYGON", 5070))
            self.assertEqual(layer.count(), 3)
            self.assertEqual(dict(layer.columns)["CDL2025"].lower(), "integer")
            self.assertNotIn("Shape", dict(layer.columns))

    def test_features_give_attributes_and_plain_wkb(self):
        with gpkg.open(self.path) as gp:
            rows = list(gp.layer().features(["CSBID", "CDL2018", "CDL2025", "CSBACRES"]))
        self.assertEqual([r[1]["CSBID"] for r in rows], [S.F1, S.F2, S.F3])
        self.assertEqual(rows[1][1]["CDL2025"], 123)
        fid, attrs, wkb = rows[0]
        self.assertEqual(fid, 1)
        self.assertAlmostEqual(attrs["CSBACRES"], 40000 / S.ACRE_M2, places=3)
        # standard little-endian WKB: a MultiPolygon of one polygon with one five-point ring
        self.assertEqual(struct.unpack("<BII", wkb[:9]), (1, 6, 1))
        self.assertEqual(struct.unpack("<BIII", wkb[9:22]), (1, 3, 1, 5))
        self.assertEqual(struct.unpack("<dd", wkb[22:38]), (S.X0, S.Y0))

    def test_an_unknown_column_is_refused(self):
        with gpkg.open(self.path) as gp, self.assertRaises(gpkg.GpkgError):
            list(gp.layer().features(["CSBID", "NOPE"]))

    def test_headers(self):
        polys = S.rect(0, 0, 1, 1)
        blob = S.gpkg_geometry([polys], 5070)
        srs, wkb, empty = gpkg.strip_header(blob)
        self.assertEqual((srs, empty), (5070, False))
        self.assertEqual(wkb, S.wkb_multipolygon([polys]))
        # no envelope, big-endian header
        bare = b"GP" + bytes([0, 0]) + struct.pack(">i", 4326) + S.wkb_multipolygon([polys])
        self.assertEqual(gpkg.strip_header(bare)[:2], (4326, S.wkb_multipolygon([polys])))
        self.assertTrue(gpkg.strip_header(S.gpkg_geometry([polys], 5070, empty=True))[2])
        self.assertEqual(gpkg.strip_header(None), (None, None, True))
        for bad in (b"XX" + blob[2:], blob[:2] + bytes([1]) + blob[3:], blob[:3] + bytes([0b00100011]) + blob[4:],
                    blob[:3] + bytes([0b00001111]) + blob[4:], blob[:40], b"GP"):
            with self.subTest(bad=bad[:4]), self.assertRaises(gpkg.GpkgError):
                gpkg.strip_header(bad)

    def test_not_a_geopackage(self):
        plain = os.path.join(self.tmp.name, "plain.sqlite")
        db = sqlite3.connect(plain)
        db.execute("create table t (a)")
        db.commit()
        db.close()
        for path in (plain, os.path.join(self.tmp.name, "missing.gpkg")):
            with self.subTest(path=path), self.assertRaises(gpkg.GpkgError):
                gpkg.open(path)
        text = os.path.join(self.tmp.name, "text.gpkg")
        with open(text, "w") as f:
            f.write("not sqlite" * 100)
        with self.assertRaises(gpkg.GpkgError):
            gpkg.open(text)

    def test_a_named_layer_must_exist(self):
        with gpkg.open(self.path) as gp:
            with self.assertRaises(gpkg.GpkgError):
                gp.layer("other")
            self.assertEqual(gp.layer("csb_mapbox").name, "csb_mapbox")

    def test_reads_a_read_only_file(self):
        os.chmod(self.path, 0o444)
        with gpkg.open(self.path) as gp:
            self.assertEqual(gp.layer().count(), 3)


if __name__ == "__main__":
    unittest.main()
