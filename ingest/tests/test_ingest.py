"""Offline tests for the ingest core: the robots.txt parser and polite HTTP.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import unittest

from ingest.http import Robots


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

    def test_groups_for_us_are_merged_and_ties_disallow(self):     # ScienceBase's two * groups
        r = Robots("User-agent: Claude-User\nDisallow: /\n\nUser-agent: *\nAllow: /\n\n"
                   "User-agent: *\nDisallow: /\nCrawl-delay: 5\n")
        self.assertFalse(r.allowed("https://x/catalog/item/1"))   # Allow: / and Disallow: / tie
        self.assertEqual(r.crawl_delay(), 5)

    def test_every_group_naming_us_applies(self):
        r = Robots("User-agent: treasure-valley-traffic\nDisallow: /a/\n\n"
                   "User-agent: other\nDisallow: /\n\n"
                   "User-agent: treasure-valley-traffic\nDisallow: /b/\nCrawl-delay: 2\n\n"
                   "User-agent: *\nDisallow: /c/\nCrawl-delay: 9\n")
        self.assertFalse(r.allowed("https://x/a/1"))
        self.assertFalse(r.allowed("https://x/b/1"))
        self.assertTrue(r.allowed("https://x/c/1"))                # a group names us, so * doesn't apply
        self.assertEqual(r.crawl_delay(), 2)


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


class EditGuardTest(unittest.TestCase):
    def test_arcgis_edits_are_refused_before_any_request(self):
        from ingest import http
        for url in ["https://x/arcgis/rest/services/Parks/FeatureServer/0/applyEdits",
                    "https://x/server/rest/services/a/FeatureServer/applyedits?f=json",
                    "https://x/arcgis/rest/services/a/MapServer/3/deleteFeatures"]:
            with self.assertRaises(http.EditRefused):
                http.get(url)
            with self.assertRaises(http.EditRefused):
                http.post(url, b"edits=[]")
        self.assertIsNone(http.EDIT_OPS.search("/arcgis/rest/services/a/FeatureServer/0/query"))
