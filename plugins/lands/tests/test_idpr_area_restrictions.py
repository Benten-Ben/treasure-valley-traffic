"""Offline tests for IDPR's area restrictions (layer 123).

The fixture is SYNTHETIC (IDPR is a state agency with non-commercial terms):
the layer's real structure and field names with made-up areas.

Run: python3 -m unittest discover -s plugins/lands/tests -t .
"""

import os
import unittest
from datetime import datetime, timezone

from ingest import manifest
from plugins.lands.ingest import closures
from plugins.lands.ingest.sources import idpr_area_restrictions as ar
from plugins.lands.tests.test_usfs_r4_orders import fixture, run_offline

UTC = timezone.utc
G = "00000000-0000-4000-8000-0000000000"


class AreaRestrictionsTest(unittest.TestCase):
    def setUp(self):
        self.fx = fixture("idpr_area_restrictions")
        self.groups = closures.snapshot(self.fx["features"], ar.key)
        self.rows = {sid: ar.event(sid, closures.merge(parts), closures.combine([g for _, g in parts]))
                     for sid, parts in self.groups.items()}

    def test_areas_are_keyed_on_global_id_and_cut_to_the_ring(self):
        self.assertEqual(sorted(self.groups), [G + "21", G + "22", G + "23", G + "24"])
        self.assertEqual(ar.key({"GlobalID": "{ABC}", "Restricted_Area_Name": "x"}), "abc")
        self.assertEqual(ar.key({"GlobalID": None, "Restricted_Area_Name": " Some  Area "}), "name:some area")

    def test_two_outer_rings_and_a_hole(self):
        geom = self.rows[G + "21"]["geom"]
        self.assertEqual(geom["type"], "MultiPolygon")
        self.assertEqual(sorted(len(p) for p in geom["coordinates"]), [1, 2])
        big = next(p for p in geom["coordinates"] if len(p) == 2)
        self.assertEqual(big[0][0], [-116.6, 43.4])

    def test_kinds(self):
        kinds = {sid[-2:]: r["kind"] for sid, r in self.rows.items()}
        self.assertEqual(kinds, {"21": "restriction", "22": "closure", "23": "restriction", "24": "closure"})

    def test_dates(self):
        ohv = self.rows[G + "21"]
        self.assertEqual((ohv["start"], ohv["end"]), (datetime(2023, 8, 17, 6, tzinfo=UTC), None))   # Until Amended
        creek = self.rows[G + "22"]
        self.assertEqual(creek["end"], datetime(2027, 3, 27, 6, tzinfo=UTC))
        self.assertEqual(creek["attributes"]["order_expires"], "3/26/2027 (annual renewal expected)")
        self.assertEqual(creek["attributes"]["orders_mentioned"], ["0499-03-002"])
        fire = self.rows[G + "24"]
        self.assertEqual((fire["end"], fire["attributes"]["fixes"]), (None, ["end_before_start"]))

    def test_attributes(self):
        a = self.rows[G + "21"]["attributes"]
        self.assertEqual((a["name"], a["area_type"], a["acres"], a["jurisdiction"]),
                         ("Example Butte OHV Prohibition Areas", "OHV Exclusion", 1500.25, "Bureau of Land Management"))
        self.assertEqual(a["links"], ["https://example.test/plan/1"])

    def test_the_run_cuts_what_the_server_sends_from_outside_the_ring(self):
        stats, calls, up, _ = run_offline(ar, self.fx)
        self.assertEqual((stats["features"], stats["records"]), (5, 4))
        self.assertTrue(up.call_args.kwargs["complete"])

    def test_the_source_and_its_manifest_entry(self):
        self.assertEqual((ar.SOURCE["schedule"], ar.SOURCE["access"]), ("1 hour", "open"))
        m = manifest.load(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        entry = next(e for e in m.manifest["sources"] if e["name"] == "idpr_area_restrictions")
        self.assertEqual((entry["license"], entry["credit"], entry["republish"]),
                         (ar.SOURCE["license"], ar.SOURCE["credit"], "aggregates"))
        self.assertEqual(closures.missing_fields(self.fx["layer"], ar.REQUIRED), [])


if __name__ == "__main__":
    unittest.main()
