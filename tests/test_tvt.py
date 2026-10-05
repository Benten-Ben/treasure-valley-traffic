"""Offline tests for the tvt package: robots rules, store lifecycle, geometry, parsers.

Run: python3 -m unittest discover tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tvt.geo import GridIndex, cluster_points, haversine_m  # noqa: E402
from tvt.http import Robots  # noqa: E402
from tvt.sources import weather  # noqa: E402
from tvt.store import Store, point  # noqa: E402


class RobotsTest(unittest.TestCase):
    def test_blank_line_between_agent_and_rule(self):  # ACHD more.achdidaho.org
        r = Robots("User-agent: *\n\nDisallow: /\n")
        self.assertFalse(r.allowed("https://more.achdidaho.org/ATIS/CCTV/CCTV_517.jpg"))

    def test_bom_wildcards_and_case(self):  # 511 Idaho
        r = Robots("﻿user-agent: *\r\ndisallow: /map/map*/\r\ndisallow: /list/GetData/\r\n")
        self.assertFalse(r.allowed("https://511.idaho.gov/map/mapIcons/Cameras"))
        self.assertFalse(r.allowed("https://511.idaho.gov/List/GetData/Cameras"))
        self.assertTrue(r.allowed("https://511.idaho.gov/map/Cctv/631"))
        self.assertTrue(r.allowed("https://511.idaho.gov/api/wzdx"))

    def test_rules_without_user_agent_and_crawl_delay(self):  # IEM
        r = Robots("# IEM\n\nCrawl-delay: 120\nDisallow: /usage/\n")
        self.assertEqual(r.crawl_delay(), 120.0)
        self.assertFalse(r.allowed("https://x/usage/a"))
        self.assertTrue(r.allowed("https://x/cgi-bin/request/asos.py"))

    def test_longest_match_and_allow_override(self):  # itd.idaho.gov
        r = Robots("User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n")
        self.assertFalse(r.allowed("https://x/wp-admin/x"))
        self.assertTrue(r.allowed("https://x/wp-admin/admin-ajax.php"))

    def test_end_anchor(self):
        r = Robots("User-agent: *\nDisallow: /*.pdf$\n")
        self.assertFalse(r.allowed("https://x/a/b.pdf"))
        self.assertTrue(r.allowed("https://x/a/b.pdf?download=1"))


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(os.path.join(tempfile.mkdtemp(), "t.sqlite"))

    def test_events_lifecycle(self):
        s = self.store
        s.sync_events("src", "work_zone", [("a", point(-116.2, 43.6), {}),
                                            ("b", point(-116.3, 43.6), {})], seen="t1")
        s.sync_events("src", "work_zone", [("b", point(-116.3, 43.6), {})], seen="t2")
        active = {e["eid"]: e for e in s.active_events("work_zone")}
        self.assertEqual(set(active), {"b"})
        self.assertEqual(active["b"]["first_seen"], "t1")  # lifetime preserved
        s.sync_events("src", "work_zone", [], seen="t3")
        self.assertEqual(list(s.active_events("work_zone")), [])

    def test_current_features_only_latest_load(self):
        s = self.store
        s.upsert_features("src", "camera", [(1, point(0, 0), {}), (2, point(0, 0), {})], seen="t1")
        s.upsert_features("src", "camera", [(2, point(0, 0), {})], seen="t2")
        self.assertEqual([f["fid"] for f in s.current_features(kind="camera")], ["2"])


class GeoTest(unittest.TestCase):
    def test_cluster_merges_close_points_only(self):
        pts = [(43.6, -116.2, "a"), (43.6003, -116.2, "b"), (43.61, -116.2, "c")]
        sizes = sorted(len(c) for c in cluster_points(pts, 60))
        self.assertEqual(sizes, [1, 2])

    def test_grid_near(self):
        idx = GridIndex(100)
        idx.add(43.6, -116.2, "x")
        self.assertEqual(idx.near(43.6005, -116.2, 100)[0][1], "x")
        self.assertEqual(idx.near(43.61, -116.2, 100), [])
        self.assertAlmostEqual(haversine_m(43.6, -116.2, 43.601, -116.2), 111.2, delta=1)


class WeatherParseTest(unittest.TestCase):
    def test_fog_and_visibility(self):
        text = ("station,valid,vsby,tmpf,sknt,wxcodes\n"
                "BOI,2026-01-10 14:53,0.25,28.0,3.0,FG\n"
                "BOI,2026-01-10 15:53,M,30.0,4.0,M\n")
        rows = {(ts, m): v for _, ts, m, v in weather.parse(text)}
        self.assertEqual(rows[("2026-01-10T14:53:00+00:00", "fog")], 1.0)
        self.assertEqual(rows[("2026-01-10T14:53:00+00:00", "visibility_mi")], 0.25)
        self.assertIsNone(rows[("2026-01-10T15:53:00+00:00", "visibility_mi")])


if __name__ == "__main__":
    unittest.main()
