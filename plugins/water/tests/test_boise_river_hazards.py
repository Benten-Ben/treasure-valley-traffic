"""Tests for the river-hazards poller: mixed codes, dropped people fields, lifecycles, the snapshot guard.

The fixture is synthetic (made-up names, people, text and points with the Boise Fire layer's fields and codes).
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import arcgis, db, events
from plugins.water.ingest.sources import boise_river_hazards as hz

from . import DB_URL, FakeConn, db_conn, fake_fetch, fixture

UTC = timezone.utc
NOW = datetime(2030, 7, 3, 12, tzinfo=UTC)


def features():
    return fixture("hazards.json")["features"]


class HazardsTest(unittest.TestCase):
    def test_points_outside_the_ring_are_dropped_and_people_fields_never_kept(self):
        parsed = hz.parse(features())
        self.assertEqual(sorted(parsed), list(range(1, 10)))              # OBJECTID 10 lies outside the ring
        payload, geom = parsed[1]
        for gone in ("OBJECTID", "Creator", "Editor", "Comments"):
            self.assertNotIn(gone, payload)
        self.assertNotIn("Example Person", json.dumps(payload))
        self.assertEqual((payload["Type"], payload["Status"], payload["Marker"]), ("T", "A", "1.0"))  # as published
        self.assertEqual(payload["_geom"], arcgis.geom_digest(geom))

    def test_mixed_codes_are_normalized(self):
        parsed = hz.parse(features())
        got = {oid: (hz.hazard_type(p), hz.status(p)) for oid, (p, _) in parsed.items()}
        self.assertEqual(got, {1: ("temporary", "active"), 2: ("permanent", "active"), 3: ("extreme", "potential"),
                               4: ("temporary", "remediated"), 5: ("temporary", "remediated"),
                               6: ("rapid", "active"), 7: ("put_in", "active"), 8: ("temporary", None),
                               9: ("extreme", "inactive")})
        self.assertEqual(hz.hazard_type({"Type": "Extreme hazard"}), "extreme")
        self.assertEqual(hz.status({"Status": " active "}), "active")

    def test_only_live_hazards_are_events(self):
        rows = hz.hazard_rows(hz.parse(features()))
        self.assertEqual([r["source_id"] for r in rows], ["1", "2", "3"])
        r = rows[0]
        self.assertEqual((r["kind"], r["severity"]), ("river_hazard", "temporary"))
        self.assertEqual(r["start"], arcgis.esri_date(1900000000000))
        self.assertEqual(r["description"], "Test strainer: A made-up tree across the left channel.")
        self.assertEqual(r["attributes"], {"type": "temporary", "status": "active", "name": "Test strainer",
                                           "mile_marker": "1.0", "edited": "2030-03-17T18:46:40Z"})
        self.assertEqual(rows[2]["attributes"]["status"], "potential")

    def test_a_moved_point_is_a_new_version(self):
        a = hz.parse(features())[2][0]
        moved = json.loads(json.dumps(features()))
        moved[1]["geometry"]["x"] += 0.001
        b = hz.parse(moved)[2][0]
        self.assertNotEqual(db.version_hash(a), db.version_hash(b))

    def test_a_small_snapshot_is_refused_before_anything_is_written(self):
        conn = FakeConn({"select count(*) from raw.record": [(119,)]})
        with mock.patch.object(db, "upsert_records") as up, mock.patch.object(events, "upsert") as ev:
            with self.assertRaisesRegex(RuntimeError, "not taken as a full snapshot"):
                hz.store(conn, 1, NOW, hz.parse(features()))
        up.assert_not_called()
        ev.assert_not_called()

    def test_run_stores_a_full_snapshot_and_the_lifecycles(self):
        conn = FakeConn({"insert into ops.fetch": [(1,)], "select count(*) from raw.record": [(9,)]})
        with mock.patch.object(arcgis, "fetch_layer", return_value=(features(), 999, 200, "no_rules")), \
                mock.patch.object(db, "upsert_records", return_value=(9, 0, 0)) as up, \
                mock.patch.object(events, "upsert", return_value={"new": 3, "changed": 0, "unchanged": 0,
                                                                  "gone": 0}) as ev:
            stats = hz.run(conn)
        self.assertIs(up.call_args.kwargs["complete"], True)
        self.assertEqual(len(ev.call_args.args[2]), 3)
        self.assertEqual((stats["points"], stats["live hazards"], stats["hazards new"]), (9, 3, 3))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.conn = db_conn(self, "raw.record", "evt.event")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_a_remediated_hazard_leaves_and_a_deleted_point_is_retired(self):
        c = self.conn
        db.ensure_source(c, hz.SOURCE)
        s1 = hz.store(c, fake_fetch(c, "boise_river_hazards", NOW), NOW, hz.parse(features()))
        self.assertEqual((s1["versions new"], s1["hazards new"]), (9, 3))
        nxt = json.loads(json.dumps(features()))
        nxt[0]["attributes"]["Status"] = "R"                     # the strainer is remediated
        del nxt[6]                                               # the put-in is deleted
        later = NOW + timedelta(hours=1)
        s2 = hz.store(c, fake_fetch(c, "boise_river_hazards", later), later, hz.parse(nxt))
        self.assertEqual((s2["versions new"], s2["removed"]), (1, 2))   # the strainer's old version and the put-in
        self.assertEqual((s2["hazards unchanged"], s2["hazards gone"]), (2, 1))
        with self.assertRaises(RuntimeError):
            hz.store(c, fake_fetch(c, "boise_river_hazards", later), later, dict(list(hz.parse(nxt).items())[:3]))


if __name__ == "__main__":
    unittest.main()
