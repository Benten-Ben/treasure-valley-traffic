"""Tests for COMPASS's counts and congestion measures (plugins/flow/ingest/sources/compass_counts.py
and compass_congestion.py), on small synthetic records (made-up values; nothing copied from COMPASS).

The store test runs only against a scratch database named by
TVT_TEST_DATABASE_URL (a clone with migration 0012), inside one transaction
that is rolled back. The shared reader's tests are in ingest/tests/test_compass_layer.py.

Run: python3 -m unittest discover -s plugins -t .
"""

import os
import unittest
from datetime import date, datetime, timezone

from ingest import compass_layer as cl
from plugins.flow.ingest.sources import compass_congestion, compass_counts


class KeyTest(unittest.TestCase):
    def test_congestion_segments(self):
        sid = compass_congestion.segment_id
        line = {"type": "LineString", "coordinates": [[-116.25, 43.62], [-116.24, 43.62]]}
        self.assertEqual(sid({"roadway_id": "117-00001"}, line), ("117-00001", "tmc"))
        self.assertEqual(sid({"roadway_id": "117N00002"}, line), ("117N00002", "tmc"))
        self.assertEqual(sid({"roadway_id": "1100000001"}, line), ("1100000001", "xd"))
        east = sid({"roadway_id": "2", "road_direction": "E", "roadname": "W Example St"}, line)
        self.assertEqual(east[1], "geometry")
        self.assertEqual(east, sid({"roadway_id": "1", "road_direction": "E", "roadname": "W Example St"}, line))
        self.assertNotEqual(east, sid({"roadway_id": "2", "road_direction": "W", "roadname": "W Example St"}, line))


    def test_count_locations(self):
        placeholder = {"agency": "ACHD", "road": "Example  Rd", "location": "e/o Sample Ave ", "pm_id": "#NYA"}
        self.assertEqual(compass_counts.portable_key(placeholder), "loc:achd|example rd|e/o sample ave")
        self.assertEqual(compass_counts.portable_key({**placeholder, "pm_id": "#nya", "location": "E/O Sample Ave"}),
                         "loc:achd|example rd|e/o sample ave")
        # Portable counts: one per segment, whatever the location text says.
        self.assertEqual(compass_counts.portable_key({**placeholder, "pm_id": "000000001001"}), "pm:000000001001")
        # Permanent counters: one per direction on the interstate, two on some segments.
        east = {"agency": "ITD", "road": "I 84", "location": "0.5 miles w/o Example Rd", "pm_id": "Int000000e99"}
        self.assertEqual(compass_counts.atr_key(east), "loc:itd|i 84|0.5 miles w/o example rd|Int000000e99")
        self.assertNotEqual(compass_counts.atr_key(east), compass_counts.atr_key({**east, "pm_id": "Int000000w99"}))


class CountsTest(unittest.TestCase):
    def test_rows(self):
        r = compass_counts.count_row({"pm_id": "#NYA", "road": "Example Rd", "location": "e/o Sample Ave",
                                      "agency": "ACHD", "onetwoway": "2", "mon": "Nov", "month": 11.0,
                                      "year": 2025.0, "total": 499.6}, "short")
        self.assertEqual((r["pm_id"], r["counted_on"], r["period"], r["direction"], r["count_24h"]),
                         (None, date(2025, 11, 1), "month", "both", 500))
        r = compass_counts.count_row({"pm_id": "000000002000", "onetwoway": "1.0", "year": 2024.0,
                                      "avgtot": 20000.0, "month": 3}, "permanent")
        self.assertEqual((r["counted_on"], r["period"], r["direction"], r["count_24h"], r["pm_id"]),
                         (date(2024, 1, 1), "year", "one_direction", 20000, "000000002000"))
        self.assertIsNone(compass_counts.count_row({"total": 5}, "short"))
        self.assertEqual([compass_counts.count_row({"year": 2024, "onetwoway": v}, "short")["direction"]
                          for v in (2.0, "1", "3", "x", None)], ["both", "one_direction", None, None, None])


class TermsTest(unittest.TestCase):
    def test_terms_and_schedules(self):
        for s in (compass_congestion.SOURCE, compass_congestion.MEASURES, compass_congestion.COMMUTES):
            self.assertEqual(s["license"], cl.INTERNAL_LICENSE)
            self.assertIn("internal use", s["notes"])
        for m in (compass_counts, compass_congestion):
            self.assertEqual(m.SOURCE["credit"], "COMPASS and COMPASS member agencies")
            self.assertEqual(m.SOURCE["retry_after"], "6 hours")


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
SKIP_DB = "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0012)"


def _db_ready():
    import psycopg
    with psycopg.connect(DB_URL) as c:
        if not c.execute("select to_regclass('ops.layer_signature') is not null").fetchone()[0]:
            raise unittest.SkipTest("ops.layer_signature is missing: apply migration 0012")
    return psycopg


@unittest.skipUnless(DB_URL, SKIP_DB)
class DatabaseTest(unittest.TestCase):
    """Store functions against a real (scratch) database, inside one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        cls.psycopg = _db_ready()

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.seen = datetime.now(timezone.utc)
        for module in (compass_counts,):
            cl.db.ensure_source(self.conn, module.SOURCE)
            for layer in module.LAYERS:
                cl.db.ensure_source(self.conn, layer.source)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()

    def test_counts_keep_earlier_counts_and_null_placeholders(self):
        store = compass_counts.count_store(compass_counts.PORTABLE, "short", compass_counts.portable_key)
        older = {"pm_id": "#NYA", "road": "Test Rd", "location": "e/o Nowhere", "agency": "TESTAGENCY",
                 "onetwoway": "2", "month": 5, "year": 2023, "total": 100}
        store(self.conn, None, self.seen, cl.Read(rows=[(older, None)], complete=False))
        stats = store(self.conn, None, self.seen,
                      cl.Read(rows=[({**older, "year": 2025, "total": 140, "onetwoway": "9"}, None)], complete=False))
        self.assertEqual(stats["direction unknown"], 1)
        rows = self.conn.execute("""select counted_on, count_24h, pm_id, direction from obs.traffic_count
                                    where location_key = 'loc:testagency|test rd|e/o nowhere' order by 1""").fetchall()
        self.assertEqual(rows, [(date(2023, 5, 1), 100, None, "both"), (date(2025, 5, 1), 140, None, None)])


if __name__ == "__main__":
    unittest.main()
