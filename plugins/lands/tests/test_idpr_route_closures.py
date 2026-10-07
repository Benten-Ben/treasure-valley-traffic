"""Offline tests for IDPR's emergency route closures (layer 127).

The fixture is SYNTHETIC (IDPR is a state agency with non-commercial terms):
the layer's real structure and field names with made-up closures.

Run: python3 -m unittest discover -s plugins/lands/tests -t .
"""

import os
import unittest
from datetime import datetime, timezone

from ingest import manifest
from plugins.lands.ingest import closures
from plugins.lands.ingest.sources import idpr_route_closures as rc
from plugins.lands.tests.test_usfs_r4_orders import FakeFetch, fixture, run_offline

UTC = timezone.utc


class RouteClosuresTest(unittest.TestCase):
    def setUp(self):
        self.fx = fixture("idpr_route_closures")
        self.groups = closures.snapshot(self.fx["features"], rc.key)

    def rows(self):
        return {sid: rc.event(sid, closures.merge(parts), closures.combine([g for _, g in parts]))
                for sid, parts in self.groups.items()}

    def test_segments_are_grouped_by_closure_and_cut_to_the_ring(self):
        self.assertEqual(sorted(self.groups), [
            "example park construction", "example trail private land closure", "forest order 0499-01-001",
            "globalid:00000000-0000-4000-8000-0000000000ab"])                    # the far-away one is dropped
        self.assertEqual(len(self.groups["example park construction"]), 2)

    def test_a_closure_with_two_segments(self):
        row = self.rows()["example park construction"]
        self.assertEqual((row["kind"], row["geom"]["type"], len(row["geom"]["coordinates"])),
                         ("closure", "MultiLineString", 2))
        a = row["attributes"]
        self.assertEqual((a["segments"], a["miles"], a["start_date"], a["end_date"]), (2, 0.65, None, None))
        self.assertEqual(a["links"], ["https://example.test/parks/example/maps/", "https://example.test/parks/example/"])
        self.assertIsNone(row["start"])
        payload = closures.merge(self.groups["example park construction"])
        self.assertEqual(sorted(p["GlobalID"] for p in payload["_parts"]),
                         ["00000000-0000-4000-8000-000000000011", "00000000-0000-4000-8000-000000000012"])
        self.assertNotIn("OBJECTID", payload)

    def test_dates_order_numbers_and_description(self):
        row = self.rows()["forest order 0499-01-001"]
        self.assertEqual(row["start"], datetime(2026, 8, 3, 6, tzinfo=UTC))
        self.assertEqual(row["end"], datetime(2026, 12, 1, 7, tzinfo=UTC))
        a = row["attributes"]
        self.assertEqual((a["start_text"], a["end_text"]), ("8/3/2026", "11/30/2026 unless rescinded"))
        self.assertEqual(a["orders_mentioned"], ["0499-01-001", "0499-01-000"])
        self.assertEqual(a["phone"], "(208) 555-0100")
        self.assertTrue(row["description"].startswith("Example Ridge Area, Road, & Trail Closure. Forest Order"))
        self.assertEqual(a["edited"], datetime.fromtimestamp(1786000000, UTC).isoformat())

    def test_an_indefinite_closure_stays_open(self):
        row = self.rows()["example trail private land closure"]
        self.assertEqual((row["start"], row["end"], row["attributes"]["end_text"]), (None, None, "Indefinite"))

    def test_a_segment_without_an_id_is_keyed_on_its_global_id(self):
        row = self.rows()["globalid:00000000-0000-4000-8000-0000000000ab"]
        self.assertEqual((row["attributes"]["start_date"], row["attributes"]["end_date"]), ("2026-09-01", "2026-10-31"))
        self.assertEqual(rc.key({"ID": None, "GlobalID": None}), "unnamed")

    def test_the_run_cuts_what_the_server_sends_from_outside_the_ring(self):
        stats, calls, up, ev = run_offline(rc, self.fx)
        self.assertEqual(len(calls), 3)
        self.assertEqual((stats["features"], stats["records"], FakeFetch.last.records), (6, 4, 4))
        self.assertEqual(stats["outside the ring"], 1)
        self.assertNotIn("example far away closure", [r[0] for r in up.call_args.args[2]])

    def test_the_source_and_its_manifest_entry(self):
        self.assertEqual((rc.SOURCE["schedule"], rc.SOURCE["access"]), ("1 hour", "open"))
        m = manifest.load(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        entry = next(e for e in m.manifest["sources"] if e["name"] == "idpr_route_closures")
        self.assertEqual((entry["license"], entry["credit"], entry["republish"]),
                         (rc.SOURCE["license"], rc.SOURCE["credit"], "aggregates"))
        self.assertEqual(closures.missing_fields(self.fx["layer"], rc.REQUIRED), [])


if __name__ == "__main__":
    unittest.main()
