"""Tests for the Greenbelt closures poller.

Offline: what counts as in effect, parsing both layers, ids, the ring, the guard for a tiny
layer, the schedule and a whole run against a fake server (including an emptied layer). The
database tests run only with TVT_TEST_DATABASE_URL, inside one transaction that is rolled back.

Run: python3 -m unittest discover -s plugins/trails/tests -t .
The fixtures are synthetic (the City's layers aren't ours to copy): see tests/fixtures/.
"""

import copy
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db, manifest
from plugins.trails.ingest import layers
from plugins.trails.ingest.sources import boise_greenbelt_closures as gb
from plugins.trails.tests import PLUGIN, FakeFetch, FakeLayers, fixture, interval_s

UTC = timezone.utc


def read():
    """The fixture as fetch_layer would return it, per layer."""
    data = fixture("greenbelt_closures.json")
    return [(part, kind, copy.deepcopy(data[str(layer_id)]["features"])) for layer_id, part, kind in gb.LAYERS]


def server(empty=()):
    data = fixture("greenbelt_closures.json")
    answers = {}
    for layer_id, _, _ in gb.LAYERS:
        answer = copy.deepcopy(data[str(layer_id)])
        if layer_id in empty:
            answer["features"] = []
        answers[gb.layer_url(layer_id)] = answer
    return FakeLayers(answers)


class InEffectTest(unittest.TestCase):
    def test_status(self):
        self.assertTrue(gb.in_effect({"STATUS": "Active"}))
        self.assertFalse(gb.in_effect({"STATUS": "Inactive"}))
        self.assertFalse(gb.in_effect({"STATUS": " INACTIVE "}))
        self.assertFalse(gb.in_effect({"STATUS": "Completed"}))
        self.assertTrue(gb.in_effect({"STATUS": None}))              # still on the City's map
        self.assertTrue(gb.in_effect({"STATUS": "Closed"}))          # a closure that says closed is in effect

    def test_a_detours_project_status(self):
        self.assertFalse(gb.in_effect({"STATUS": "Active", "Project_Status": "Inactive"}))
        self.assertTrue(gb.in_effect({"STATUS": "Active", "Project_Status": "Active"}))


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.records, self.rows, self.stats = gb.parse(read())
        self.payloads = {k: p for k, p, _ in self.records}
        self.events = {r["source_id"]: r for r in self.rows}

    def test_ids_and_the_ring(self):
        self.assertEqual(sorted(self.payloads), ["construction:501", "construction:502", "construction:503",
                                                 "construction:504", "detour:601", "detour:602"])
        self.assertEqual(self.stats, {"outside the ring": 1, "without an id": 0, "inactive rows": 2})

    def test_only_rows_in_effect_are_events(self):
        self.assertEqual(sorted(self.events), ["construction:501", "construction:502", "construction:504",
                                               "detour:601"])
        self.assertEqual({r["kind"] for r in self.rows if r["source_id"].startswith("construction")}, {"closure"})
        self.assertEqual(self.events["detour:601"]["kind"], "detour")

    def test_payload(self):
        p = self.payloads["construction:502"]
        self.assertEqual((p["layer"], p["STATUS"], p["GREENBELT_MILE"]), ("construction", "Active", "3.4"))
        self.assertNotIn("OBJECTID", p)
        self.assertNotIn("SHAPE__Length", p)
        self.assertEqual(len(p["_geom"]), 16)
        self.assertEqual(self.payloads["construction:503"]["STATUS"], "Inactive")     # kept as a version

    def test_staff_names_are_never_kept(self):
        layers_read = read()
        layers_read[0][2][0]["attributes"].update(Creator="staff_a", Editor="staff_b", EditDate=1791230400000)
        layers_read[1][2][0]["attributes"].update(created_user="staff_a", last_edited_user="staff_b")
        payloads = {k: p for k, p, _ in gb.parse(layers_read)[0]}
        for p in payloads.values():
            self.assertFalse({"Creator", "Editor", "created_user", "last_edited_user"} & set(p))
        self.assertEqual(payloads["construction:501"]["EditDate"], 1791230400000)   # a date, not a person

    def test_event_row(self):
        r = self.events["construction:502"]
        self.assertEqual(r["description"], "Example section replacement")
        self.assertEqual(r["attributes"], {"layer": "construction", "project": "Example Island Path Repair",
                                           "work": "Example section replacement", "season": "Summer",
                                           "updates": "Sample update text", "river_mile": "50.1",
                                           "greenbelt_mile": "3.4", "status": "Active", "location": "X",
                                           "latitude": "43.6", "longitude": "-116.2"})
        self.assertIsNone(r["start"])
        self.assertEqual(r["geom"]["type"], "LineString")
        self.assertEqual(self.events["construction:504"]["description"], "Unlabelled Sample Closure")
        self.assertEqual(self.events["detour:601"]["attributes"]["project_status"], "Active")


class RunTest(unittest.TestCase):
    def setUp(self):
        self.stored = None

    def run_with(self, srv):
        def store(conn, fetch_id, seen_at, records, rows):
            self.stored = (records, rows)
            return {"rows": len(records), "ended": 0}         # events that ended (store's count)

        with mock.patch.object(db, "ensure_source"), mock.patch.object(db, "Fetch", FakeFetch), \
                mock.patch.object(gb, "store", side_effect=store):
            return gb.run(None, get=srv, sleep=lambda s: None)

    def test_both_layers_are_read_whole(self):
        srv = server()
        stats = self.run_with(srv)
        self.assertEqual(len(srv.urls), 4)                   # IDs and rows for each layer
        self.assertTrue(all("/FeatureServer/0/" in u for u in srv.urls[:2]))
        self.assertEqual(stats, {"rows": 6, "ended": 0, "outside the ring": 1, "inactive rows": 2})
        self.assertEqual(len(self.stored[1]), 4)

    def test_an_emptied_layer_is_taken(self):
        srv = server(empty=(0, 1))
        stats = self.run_with(srv)
        self.assertEqual(len(srv.urls), 2)                   # an empty ID list needs no row request
        self.assertEqual(stats, {"rows": 0, "ended": 0})
        self.assertEqual(self.stored, ([], []))
        self.assertFalse(layers.refuse(0, 3, floor=gb.GUARD_FLOOR))     # store's guard, holding three rows

    def test_schedule(self):
        plugin = manifest.load(PLUGIN)
        self.assertIn(gb.SOURCE["name"], [e["name"] for e in plugin.entries("source")])
        self.assertEqual(interval_s(gb.SOURCE["schedule"]), 3600)
        self.assertEqual(gb.SOURCE["access"], "open")


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a clone migrated through 0012)")
class DatabaseTest(unittest.TestCase):
    """store() against a real (scratch) database, inside one transaction rolled back."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        self.t0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
        self.name = gb.SOURCE["name"]
        db.ensure_source(self.conn, gb.SOURCE)
        for table in ("evt.event", "raw.record"):
            self.conn.execute(f"delete from {table} where source = %s", (self.name,))   # rolled back after

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def store(self, layers_read, seen):
        records, rows, _ = gb.parse(layers_read)
        return gb.store(self.conn, None, seen, records, rows)

    def test_a_status_flip_ends_the_closure(self):
        first = self.store(read(), self.t0)
        self.assertEqual((first["rows"], first["closures"], first["detours"], first["events new"]), (6, 3, 1, 4))
        flipped = read()
        flipped[0][2][1]["attributes"]["STATUS"] = "Inactive"                       # construction:502
        t1 = self.t0 + timedelta(hours=1)
        second = self.store(flipped, t1)
        self.assertEqual((second["versions new"], second["ended"], second["closures"]), (1, 1, 2))
        active, upper = self.conn.execute(
            "select active, upper(observed) from evt.event where source = %s and source_id = 'construction:502'",
            (self.name,)).fetchone()
        self.assertEqual((active, upper), (False, t1))

    def test_an_emptied_layer_ends_everything(self):
        few = [(part, kind, feats[:2] if part == "construction" else feats[:1]) for part, kind, feats in read()]
        self.store(few, self.t0)                                    # 3 rows, as on Oct 7: under the floor
        out = self.store([("construction", "closure", []), ("detour", "detour", [])], self.t0 + timedelta(hours=1))
        self.assertEqual((out["rows"], out["removed"], out["ended"]), (0, 3, 3))

    def test_an_empty_answer_is_refused_once_we_hold_the_floor(self):
        self.store(read(), self.t0)                                 # 6 rows
        with self.assertRaisesRegex(RuntimeError, "not taken as a full snapshot"):
            self.store([("construction", "closure", []), ("detour", "detour", [])], self.t0 + timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
