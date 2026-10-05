"""Offline tests for the ingest package.

Run: python3 -m unittest discover ingest
"""

import unittest

from ingest.db import version_hash
from ingest.http import Robots
from ingest.sources import achd_cameras


class RobotsTest(unittest.TestCase):
    def test_blank_line_inside_group_still_applies(self):          # ACHD's file
        self.assertFalse(Robots("User-agent: *\n\nDisallow: /\n").allowed("https://x/ATIS/CCTV/1.jpg"))

    def test_bom_crlf_and_case_insensitive(self):                   # 511 Idaho's file
        r = Robots("﻿user-agent: *\r\ndisallow: /map/map*/\r\ndisallow: /list/GetData/\r\n")
        self.assertFalse(r.allowed("https://511.idaho.gov/list/getdata/Cameras"))
        self.assertFalse(r.allowed("https://511.idaho.gov/Map/MapIcons/x"))
        self.assertTrue(r.allowed("https://511.idaho.gov/map/Cctv/656"))

    def test_rules_without_user_agent_apply_to_all(self):          # IEM's file
        r = Robots("# IEM\n\nCrawl-delay: 120\nDisallow: /usage/\n")
        self.assertFalse(r.allowed("https://x/usage/a"))
        self.assertEqual(r.crawl_delay(), 120)

    def test_longest_match_and_anchor(self):
        r = Robots("User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\nDisallow: /*.pdf$\n")
        self.assertTrue(r.allowed("https://x/wp-admin/admin-ajax.php"))
        self.assertFalse(r.allowed("https://x/wp-admin/edit.php"))
        self.assertFalse(r.allowed("https://x/a/b.pdf"))
        self.assertTrue(r.allowed("https://x/a/b.pdf?page=2"))


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


class RobotsUnavailableTest(unittest.TestCase):
    def test_unreadable_robots_is_retryable_not_a_disallow(self):
        from ingest import http

        def broken(url, data=None, timeout=90):
            raise OSError("connection reset by peer")

        real, http._open = http._open, broken
        try:
            http._robots.pop("https://flaky.example", None)
            with self.assertRaises(http.RobotsUnavailable):
                http.get("https://flaky.example/data.json")
            self.assertNotIn("https://flaky.example", http._robots)   # not cached: retried next time
        finally:
            http._open = real

    def test_unavailable_still_counts_as_disallowed(self):
        from ingest import http
        self.assertTrue(issubclass(http.RobotsUnavailable, http.RobotsDisallowed))
