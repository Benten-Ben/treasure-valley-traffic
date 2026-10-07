"""Tests for the road-weather stations (plugins/cameras/ingest/sources/idaho511_rwis_sites.py).

The fixture (fixtures/rwis_sites_sample.json) is synthetic: made-up names, ids
and positions in the shape of 511's camera list. The parsing tests run
offline. The database tests run only with TVT_TEST_DATABASE_URL set to a
scratch database with core's migrations and this plugin's (cameras/0001),
inside a transaction that is rolled back, under a test-only source name.

Run: python3 -m unittest discover -s plugins -t .
     TVT_TEST_DATABASE_URL=... python3 -m unittest plugins.cameras.tests.test_rwis_sites
"""

import copy
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db
from plugins.cameras.ingest.sources import idaho511_rwis_sites as rwis

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "rwis_sites_sample.json")
T0 = datetime(2026, 10, 5, 6, tzinfo=timezone.utc)


def sample():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class ParseTest(unittest.TestCase):
    def test_road_weather_sites_statewide_and_odot_in_the_ring(self):
        stations, skipped = rwis.parse(sample())
        self.assertEqual([(s["key"], s["provider"]) for s in stations],
                         [("880001", "ITD RWIS"), ("880002", "ITD RWIS"), ("880003", "ODOT")])
        # ODOT outside the ring, ACHD's traffic camera (idaho511_views loads those), a site with no images.
        self.assertEqual(skipped, 3)
        self.assertEqual([len(s["views"]) for s in stations], [4, 2, 2])
        self.assertTrue(all(2 <= len(s["views"]) <= 4 for s in stations))

    def test_views_keep_511s_order_labels_and_disabled_images(self):
        stations, _ = rwis.parse(sample())
        a, b, c = stations
        self.assertEqual(a["name"], "Example Grade (synthetic)")
        self.assertEqual(a["roadway"], "I-84")
        self.assertEqual(a["at"], (-116.24, 43.56))
        self.assertEqual([(v["image_id"], v["direction"], v["status"]) for v in a["views"]],
                         [(990011, "Looking East", "Enabled"), (990012, "Looking West", "Enabled"),
                          (990013, "Pavement", "Enabled"), (990014, None, "Disabled")])
        # Sorted by sortOrder, not by the file's order; no description means no label.
        self.assertEqual([(v["image_id"], v["sort_order"], v["direction"]) for v in b["views"]],
                         [(990021, 0, None), (990022, 1, None)])
        self.assertEqual([v["status"] for v in c["views"]], ["Enabled", "Disabled"])   # blocked counts as disabled

    def test_points_and_the_ring(self):
        self.assertEqual(rwis.point({"latLng": {"geography": {"wellKnownText": "POINT (-116.5 43.6)"}}}), (-116.5, 43.6))
        self.assertEqual(rwis.point({"latLng": {"geography": {"wellKnownText": "POINT Z (-116.5 43.6 800)"}}}), (-116.5, 43.6))
        self.assertIsNone(rwis.point({"latLng": {"geography": {"wellKnownText": "LINESTRING (0 0, 1 1)"}}}))
        self.assertIsNone(rwis.point({}))
        self.assertIsNone(rwis.point({"latLng": {"geography": {"wellKnownText": "POINT (-416.5 43.6)"}}}))
        self.assertEqual(rwis.provider_of({"source": "RWIS"}, (-112.0, 47.9)), "ITD RWIS")   # statewide
        self.assertEqual(rwis.provider_of({"source": "ODOT"}, (-116.97, 44.02)), "ODOT")
        self.assertIsNone(rwis.provider_of({"source": "ODOT"}, (-117.40, 44.00)))            # west of the ring
        self.assertIsNone(rwis.provider_of({"source": "ITD"}, (-116.3, 43.6)))

    def test_a_bare_list_works_and_a_repeated_site_is_refused(self):
        rows = sample()["data"]
        self.assertEqual(len(rwis.parse(rows)[0]), 3)
        with self.assertRaises(ValueError):
            rwis.parse([rows[0], rows[0]])
        with self.assertRaises(ValueError):
            rwis.parse({"nothing": True})

    def test_a_site_without_an_id_is_keyed_by_its_images(self):
        site = copy.deepcopy(sample()["data"][1])
        del site["id"]
        (station,), _ = rwis.parse([site])
        self.assertEqual(station["key"], "images:990021-990022")

    def test_the_list_date_comes_from_the_file_name(self):
        t = rwis.taken_at("/private/511-camera-sites-statewide-2026-10-05.json")
        self.assertEqual(t.isoformat(), "2026-10-05T00:00:00-06:00")
        with self.assertRaises(ValueError):
            rwis.taken_at("cameras.json")

    def test_a_missing_private_file_says_so(self):
        with mock.patch.dict(os.environ, {"TVT_PRIVATE_DATA": ""}):
            with self.assertRaises(SystemExit) as cm:
                rwis.path()
        self.assertIn("TVT_PRIVATE_DATA", str(cm.exception))
        with mock.patch.dict(os.environ, {"TVT_PRIVATE_DATA": os.path.dirname(FIXTURE)}):
            with self.assertRaises(SystemExit) as cm:
                rwis.path()
        self.assertIn("private files", str(cm.exception))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (core migrations and cameras/0001)")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        has = self.conn.execute(
            """select exists(select 1 from information_schema.columns
                             where table_schema = 'core' and table_name = 'camera' and column_name = 'provider')""").fetchone()[0]
        if not has:
            self.conn.close()
            self.skipTest("core.camera.provider is missing: apply the cameras plugin's migration 0001")
        ids = [v["image_id"] for s in rwis.parse(sample())[0] for v in s["views"]]
        if self.conn.execute("select count(*) from core.camera_view where image_id = any(%s)", (ids,)).fetchone()[0]:
            self.conn.close()
            self.skipTest("the fixture's image ids are already in this database (an e2e seed?)")
        self.name = "test_" + rwis.SOURCE["name"]
        patch = mock.patch.dict(rwis.SOURCE, {"name": self.name})
        patch.start()
        self.addCleanup(patch.stop)
        db.ensure_source(self.conn, rwis.SOURCE)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def snapshot(self):
        cams = self.conn.execute(
            """select c.id, c.name, c.provider, c.active, round(ST_X(c.pole_geom)::numeric, 6), round(ST_Y(c.pole_geom)::numeric, 6),
                      c.first_seen, c.last_seen, l.source_id
               from core.camera c join core.source_link l on l.entity = 'camera' and l.entity_id = c.id and l.source = %s
               order by l.source_id""", (self.name,)).fetchall()
        views = self.conn.execute(
            """select id, camera_id, image_id, source, status, direction, sort_order from core.camera_view
               where source = %s order by image_id""", (self.name,)).fetchall()
        return cams, views

    def test_loads_three_stations_with_two_to_four_views_each_idempotently(self):
        stations, _ = rwis.parse(sample())
        stats = rwis.store(self.conn, None, T0, stations)
        self.assertEqual((stats["stations"], stats["stations new"], stats["views"], stats["views new"]), (3, 3, 8, 8))
        self.assertEqual((stats["provider ITD RWIS"], stats["provider ODOT"]), (2, 1))
        cams, views = self.snapshot()
        self.assertEqual([(c[1], c[2], c[3], float(c[4]), float(c[5]), c[8]) for c in cams],
                         [("Example Grade (synthetic)", "ITD RWIS", True, -116.24, 43.56, "880001"),
                          ("Test Summit (synthetic)", "ITD RWIS", True, -116.43, 43.69, "880002"),
                          ("Sample Bridge OR (synthetic)", "ODOT", True, -117.01, 43.72, "880003")])
        per_camera = {}
        for v in views:
            per_camera.setdefault(v[1], []).append(v)
        self.assertEqual(sorted(len(vs) for vs in per_camera.values()), [2, 2, 4])
        by_image = {v[2]: v for v in views}
        self.assertEqual((by_image[990011][5], by_image[990014][4], by_image[990032][4]), ("Looking East", "Disabled", "Disabled"))
        # A second run of the same list changes nothing.
        stats = rwis.store(self.conn, None, T0, rwis.parse(sample())[0])
        writes = ("record versions new", "removed", "stations new", "stations changed", "stations retired",
                  "views new", "views changed", "views removed")
        self.assertEqual({k: stats[k] for k in writes}, dict.fromkeys(writes, 0))
        self.assertEqual(stats["unchanged"], 3)
        self.assertEqual(self.snapshot(), (cams, views))
        # ACHD's traffic cameras keep their provider (the column's default).
        self.assertEqual(self.conn.execute("select count(*) from core.camera where achd_cam_id is not null "
                                           "and provider <> 'ACHD'").fetchone()[0], 0)

    def test_a_newer_list_retires_a_station_and_marks_a_dropped_view(self):
        rwis.store(self.conn, None, T0, rwis.parse(sample())[0])
        newer = sample()
        newer["data"] = [s for s in newer["data"] if s["id"] != 880003]
        newer["data"][0]["images"] = newer["data"][0]["images"][:3]
        newer["data"][1]["location"] = "Test Summit renamed (synthetic)"
        stats = rwis.store(self.conn, None, T0 + timedelta(days=1), rwis.parse(newer)[0])
        self.assertEqual((stats["stations retired"], stats["views removed"]), (1, 3))   # 990014, and the ODOT pair
        cams, views = self.snapshot()
        self.assertEqual([(c[1], c[3]) for c in cams],
                         [("Example Grade (synthetic)", True), ("Test Summit renamed (synthetic)", True),
                          ("Sample Bridge OR (synthetic)", False)])
        self.assertEqual(sorted(v[2] for v in views if v[4] == "Removed"), [990014, 990031, 990032])
        # A list far smaller than what's held is refused, not taken as a snapshot.
        with self.assertRaises(RuntimeError):
            rwis.store(self.conn, None, T0 + timedelta(days=2), [])


if __name__ == "__main__":
    unittest.main()
