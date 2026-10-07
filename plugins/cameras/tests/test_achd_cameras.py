"""Offline tests for ACHD's camera list (plugins/cameras/ingest/sources/achd_cameras.py).

Run: python3 -m unittest discover -s plugins -t .
"""

import unittest

from ingest.db import version_hash
from plugins.cameras.ingest.sources import achd_cameras


def feature(oid, cam, label, lon=-116.35, lat=43.62, ts="Oct  4 2026 11:59PM"):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"OBJECTID": oid, "GlobalID": f"g{oid}", "camID": cam, "label": label,
                           "camtimestamp": ts}}


class AchdCamerasTest(unittest.TestCase):
    def test_duplicates_merge_and_labels_are_tidied(self):
        records, cameras = achd_cameras.parse({"features": [
            feature(1, 526, "Eagle  &  Fairview "), feature(2, 526, "Eagle & Fairview"), feature(3, 620, "Chinden & Cloverdale")]})
        self.assertEqual(len(records), 3)
        self.assertEqual(sorted(cameras), [526, 620])
        self.assertEqual(cameras[526]["name"], "Eagle & Fairview")
        self.assertEqual(cameras[526]["source_ids"], ["g1", "g2"])

    def test_layer_wide_timestamp_does_not_create_new_versions(self):
        a, _ = achd_cameras.parse({"features": [feature(1, 526, "X", ts="Oct  4 2026 11:59PM")]})
        b, _ = achd_cameras.parse({"features": [feature(1, 526, "X", ts="Oct  5 2026 12:04AM")]})
        self.assertNotIn("camtimestamp", a[0][1])
        self.assertEqual(version_hash(a[0][1]), version_hash(b[0][1]))


if __name__ == "__main__":
    unittest.main()
