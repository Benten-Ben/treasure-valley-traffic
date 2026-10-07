"""Tests for the Ridge to Rivers trails poller.

Offline: parsing, the condition states, ConditionDate's wall-clock reading, keys and episodes,
the ring, the edit-date gate, the snapshot guard, the schedule and a whole run against a fake
server. The database tests run only with TVT_TEST_DATABASE_URL (a scratch database migrated
through 0012), inside one transaction that is rolled back.

Run: python3 -m unittest discover -s plugins/trails/tests -t .
The fixtures are synthetic (the City's layer isn't ours to copy): see tests/fixtures/.
"""

import copy
import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db, events, manifest
from plugins.trails.ingest import layers
from plugins.trails.ingest.sources import r2r_trails as r2r
from plugins.trails.tests import PLUGIN, FakeFetch, FakeLayers, fixture, interval_s

UTC = timezone.utc


def features():
    return copy.deepcopy(fixture("r2r_trails.json")["features"])


def by_oid(oid):
    return next(f for f in features() if f["attributes"]["OBJECTID"] == oid)


class ConditionTest(unittest.TestCase):
    def test_the_seven_labels(self):
        labels = [c["code"] for f in fixture("r2r_layer.json")["fields"] if f["name"] == "Condition"
                  for c in f["domain"]["codedValues"]]
        self.assertEqual([r2r.condition_state(x) for x in labels],
                         ["frozen", "not_evaluated", "closed", "dry", "muddy", "frozen_then_muddy",
                          "muddy_further_out"])

    def test_blank_unknown_and_reworded_labels(self):
        self.assertEqual(r2r.condition_state(None), "unset")
        self.assertEqual(r2r.condition_state("  "), "unset")
        self.assertEqual(r2r.condition_state("Flooded - stay away"), "other")
        self.assertEqual(r2r.condition_state("MUDDY — do not use"), "muddy")
        self.assertEqual(r2r.condition_state("Closed for restoration"), "closed")

    def test_severity_follows_r2rs_advice(self):
        self.assertEqual(r2r.SEVERITY["muddy"], "do_not_use")
        self.assertEqual(r2r.SEVERITY["frozen_then_muddy"], "caution")
        self.assertNotIn("not_evaluated", r2r.SEVERITY)


class WallTimeTest(unittest.TestCase):
    def test_summer_is_six_hours_behind_utc(self):
        set_at, wall = r2r.wall_time(1782637200000)                  # stored as 2026-06-28 09:00 "UTC"
        self.assertEqual(set_at, datetime(2026, 6, 28, 15, 0, tzinfo=UTC))
        self.assertEqual(wall, "2026-06-28T09:00:00")

    def test_winter_is_seven_hours_behind_utc(self):
        set_at, _ = r2r.wall_time(1768464000000)                     # stored as 2026-01-15 08:00 "UTC"
        self.assertEqual(set_at, datetime(2026, 1, 15, 15, 0, tzinfo=UTC))

    def test_missing(self):
        self.assertEqual(r2r.wall_time(None), (None, None))


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.records, self.rows, self.stats = r2r.parse(features())
        self.by_key = {k: (p, g) for k, p, g in self.records}

    def test_keys_are_global_ids_or_object_ids(self):
        self.assertEqual(sorted(self.by_key), [
            "0a1b2c3d-0000-4000-8000-000000000001", "0a1b2c3d-0000-4000-8000-000000000002",
            "0a1b2c3d-0000-4000-8000-000000000003", "0a1b2c3d-0000-4000-8000-000000000004",
            "0a1b2c3d-0000-4000-8000-000000000007", "oid:906"])
        self.assertIsNone(r2r.trail_key({"GlobalID": None}))

    def test_cut_to_the_ring(self):
        self.assertEqual(self.stats, {"outside the ring": 1, "without a key": 0, "without a line": 1})
        self.assertNotIn("0a1b2c3d-0000-4000-8000-000000000005", self.by_key)       # near Twin Falls
        self.assertTrue(layers.in_ring({"type": "Point", "coordinates": [-116.2, 43.6]}))
        self.assertFalse(layers.in_ring({"type": "Point", "coordinates": [-114.4, 42.6]}))
        self.assertTrue(layers.in_ring({"type": "LineString", "coordinates": [[-117.5, 43.0], [-117.2, 43.1]]}))
        self.assertTrue(layers.in_ring(None))

    def test_payload_drops_staff_names_and_derived_fields(self):
        payload, geom = self.by_key["0a1b2c3d-0000-4000-8000-000000000001"]
        for gone in ("Editor", "created_user", "last_edited_user", "OBJECTID", "Shape__Length"):
            self.assertNotIn(gone, payload)
        self.assertNotIn("staff_a", str(payload))
        self.assertEqual((payload["Condition"], payload["last_edited_date"]), ("Dry / Tacky - Enjoy", 1782658800000))
        self.assertEqual(len(payload["_geom"]), 16)
        self.assertEqual(geom["type"], "MultiLineString")

    def test_editor_tracking_names_are_dropped_too(self):
        f = by_oid(902)
        f["attributes"].update(Creator="staff_c", Editor="staff_d")
        (_, payload, _), = r2r.parse([f])[0]
        self.assertFalse({"Creator", "Editor"} & set(payload))

    def test_a_moved_line_is_a_new_version(self):
        moved = by_oid(902)
        moved["geometry"]["paths"][0][0] = [-116.1485, 43.6525]
        (_, before, _), = r2r.parse([by_oid(902)])[0]
        (_, after, _), = r2r.parse([moved])[0]
        self.assertNotEqual(db.version_hash(before), db.version_hash(after))

    def test_condition_row(self):
        row = next(r for r in self.rows if r["attributes"]["trail"].endswith("0002"))
        self.assertEqual(row["source_id"], "0a1b2c3d-0000-4000-8000-000000000002/1789889400000/muddy")
        self.assertEqual((row["kind"], row["severity"]), ("trail_condition", "do_not_use"))
        self.assertEqual(row["start"], datetime(2026, 9, 20, 13, 30, tzinfo=UTC))
        self.assertIsNone(row["end"])
        self.assertEqual(row["description"], "Muddy – DO NOT USE")
        a = row["attributes"]
        self.assertEqual((a["trail_name"], a["trail_number"], a["state"], a["note"]),
                         ("Example Ridge", "1", "muddy", "Sample note: soft in the shade"))
        self.assertEqual((a["condition_date_raw"], a["condition_set_local"], a["all_weather"]),
                         (1789889400000, "2026-09-20T07:30:00", False))
        self.assertEqual(row["geom"]["type"], "LineString")

    def test_blank_trail_number_and_missing_line(self):
        rows = {r["attributes"]["trail"]: r for r in self.rows}
        self.assertIsNone(rows["0a1b2c3d-0000-4000-8000-000000000004"]["attributes"]["trail_number"])
        self.assertIsNone(rows["0a1b2c3d-0000-4000-8000-000000000007"]["geom"])
        self.assertEqual(rows["oid:906"]["attributes"]["state"], "frozen_then_muddy")


class EpisodeTest(unittest.TestCase):
    """Each status staff set is its own evt.event row; a note edit updates the row in place."""

    def row(self, **changes):
        f = by_oid(903)
        f["attributes"].update(changes)
        return r2r.parse([f])[1][0]

    def test_a_new_status_is_a_new_episode(self):
        self.assertNotEqual(self.row()["source_id"],
                            self.row(Condition="Dry / Tacky - Enjoy", ConditionDate=1791230400000)["source_id"])

    def test_the_same_status_set_again_is_a_new_label(self):
        self.assertNotEqual(self.row()["source_id"], self.row(ConditionDate=1791230400000)["source_id"])

    def test_a_status_changed_without_a_new_date_is_a_new_episode(self):
        self.assertNotEqual(self.row()["source_id"], self.row(Condition="Muddy – DO NOT USE")["source_id"])

    def test_a_note_edit_keeps_the_episode_and_changes_its_content(self):
        before, after = self.row(), self.row(ConditionNotes="Reopening soon")
        self.assertEqual(before["source_id"], after["source_id"])
        self.assertNotEqual(events.content_hash(before), events.content_hash(after))


class GateTest(unittest.TestCase):
    def setUp(self):
        self.meta = fixture("r2r_layer.json")
        self.sig = layers.signature(self.meta, domains=("Condition",))
        self.now = datetime(2026, 10, 7, 12, tzinfo=UTC)

    def test_signature(self):
        self.assertEqual((self.sig["last_edit"], self.sig["data_last_edit"]), (1791230405000, 1791230400000))
        self.assertEqual(len(self.sig["Condition values"]), 7)

    def test_unchanged_and_fresh_is_skipped(self):
        self.assertTrue(layers.unchanged(self.sig, (dict(self.sig), self.now - timedelta(hours=3)), self.now,
                                         r2r.FULL_READ_EVERY))

    def test_an_edit_a_stale_read_or_no_history_reads(self):
        edited = copy.deepcopy(self.meta)
        edited["editingInfo"]["lastEditDate"] += 60000
        new = layers.signature(edited, domains=("Condition",))
        fresh = (dict(self.sig), self.now - timedelta(hours=1))
        self.assertFalse(layers.unchanged(new, fresh, self.now, r2r.FULL_READ_EVERY))
        self.assertFalse(layers.unchanged(self.sig, (dict(self.sig), self.now - timedelta(days=2)), self.now,
                                          r2r.FULL_READ_EVERY))
        self.assertFalse(layers.unchanged(self.sig, None, self.now, r2r.FULL_READ_EVERY))

    def test_a_new_condition_value_or_field_reads(self):
        changed = copy.deepcopy(self.meta)
        cond = next(f for f in changed["fields"] if f["name"] == "Condition")
        cond["domain"]["codedValues"].append({"name": "Flooded", "code": "Flooded"})
        self.assertNotEqual(layers.signature(changed, domains=("Condition",)), self.sig)
        changed["fields"].append({"name": "NewField", "type": "esriFieldTypeString"})
        self.assertNotEqual(layers.signature(changed)["fields"], layers.signature(self.meta)["fields"])

    def test_a_layer_without_edit_dates_is_always_read(self):
        meta = {k: v for k, v in self.meta.items() if k != "editingInfo"}
        sig = layers.signature(meta)
        self.assertFalse(layers.unchanged(sig, (dict(sig), self.now), self.now, r2r.FULL_READ_EVERY))

    def test_missing_fields(self):
        self.assertEqual(layers.missing_fields(self.meta, r2r.REQUIRED), [])
        meta = copy.deepcopy(self.meta)
        meta["fields"] = [f for f in meta["fields"] if f["name"] != "Condition"]
        self.assertEqual(layers.missing_fields(meta, r2r.REQUIRED), ["Condition"])


class SnapshotGuardTest(unittest.TestCase):
    def test_refusals(self):
        self.assertTrue(layers.refuse(0, 0))             # R2R is never empty, even on a first read
        self.assertFalse(layers.refuse(271, 0))
        self.assertTrue(layers.refuse(100, 271))
        self.assertFalse(layers.refuse(200, 271))
        self.assertTrue(layers.refuse(0, 271))

    def test_small_layers_may_shrink_below_the_floor(self):
        self.assertFalse(layers.refuse(0, 3, floor=5))
        self.assertTrue(layers.refuse(1, 10, floor=5))
        self.assertFalse(layers.refuse(5, 10, floor=5))


class RunTest(unittest.TestCase):
    """run() against a fake server, with the database calls stubbed."""

    def setUp(self):
        self.meta = fixture("r2r_layer.json")
        self.server = FakeLayers({r2r.LAYER: fixture("r2r_trails.json")}, {r2r.LAYER: self.meta})
        self.saved, self.stored = [], {}

    @contextmanager
    def stubs(self, stored=None):
        def save(conn, source, sig, read):
            self.saved.append(read)

        with mock.patch.object(db, "ensure_source"), mock.patch.object(db, "Fetch", FakeFetch), \
                mock.patch.object(layers, "stored_signature", return_value=stored), \
                mock.patch.object(layers, "save_signature", side_effect=save), \
                mock.patch.object(layers, "heartbeat", return_value=6) as beat, \
                mock.patch.object(r2r, "store", side_effect=self.store) as store:
            yield beat, store

    def store(self, conn, fetch_id, seen_at, records, rows):
        self.stored = {"records": records, "rows": rows}
        return {"trails": len(records)}

    def test_first_run_reads_everything(self):
        with self.stubs() as (beat, store):
            stats = r2r.run(None, get=self.server, sleep=lambda s: None)
        self.assertEqual(len(self.server.urls), 3)            # description, IDs, one range of rows
        self.assertEqual(stats, {"trails": 6, "outside the ring": 1, "without a line": 1})
        self.assertEqual(len(self.stored["rows"]), 6)
        self.assertEqual(self.saved, [True])
        beat.assert_not_called()

    def test_an_unchanged_layer_costs_one_request(self):
        sig = layers.signature(self.meta, domains=("Condition",))
        stored = (sig, datetime(2026, 10, 7, 9, tzinfo=UTC))
        with self.stubs(stored) as (beat, store):
            stats = r2r.run(None, get=self.server, sleep=lambda s: None)
        self.assertEqual(len(self.server.urls), 1)
        self.assertEqual(stats, {"unchanged since": "2026-10-05T20:00+00:00", "versions confirmed": 6})
        self.assertEqual(self.saved, [False])
        store.assert_not_called()

    def test_a_renamed_field_fails_before_reading(self):
        self.meta["fields"] = [f for f in self.meta["fields"] if f["name"] != "ConditionDate"]
        with self.stubs() as (beat, store), self.assertRaisesRegex(RuntimeError, "ConditionDate"):
            r2r.run(None, get=self.server, sleep=lambda s: None)
        self.assertEqual(len(self.server.urls), 1)
        store.assert_not_called()


class ManifestTest(unittest.TestCase):
    def test_manifest_and_schedules(self):
        plugin = manifest.load(PLUGIN)
        entries = {e["name"]: e for e in plugin.entries("source")}
        self.assertEqual((plugin.name, plugin.order, plugin.visibility), ("trails", 63, "public"))
        self.assertEqual(entries[r2r.SOURCE["name"]]["module"], "ingest.sources.r2r_trails")
        self.assertEqual(r2r.SOURCE["access"], "open")
        self.assertEqual(interval_s(r2r.SOURCE["schedule"]), 30 * 60)
        self.assertGreaterEqual(interval_s(r2r.SOURCE["schedule"]), 600)
        self.assertEqual(plugin.manifest["tables"], [])        # raw.record and evt.event are core's


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
SKIP_DB = "set TVT_TEST_DATABASE_URL to a scratch database (a clone migrated through 0012)"


@unittest.skipUnless(DB_URL, SKIP_DB)
class DatabaseTest(unittest.TestCase):
    """store() and the gate against a real (scratch) database, inside one transaction rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('ops.layer_signature') is not null").fetchone()[0]:
                raise unittest.SkipTest("ops.layer_signature is missing: apply migration 0012")
        cls.psycopg = psycopg

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.t0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
        db.ensure_source(self.conn, r2r.SOURCE)
        self.name = r2r.SOURCE["name"]
        for table, col in (("evt.event", "source"), ("raw.record", "source"), ("ops.layer_signature", "source")):
            self.conn.execute(f"delete from {table} where {col} = %s", (self.name,))   # rolled back after

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def store(self, feats, seen):
        records, rows, _ = r2r.parse(feats)
        return r2r.store(self.conn, None, seen, records, rows)

    def test_conditions_run_as_episodes(self):
        first = self.store(features(), self.t0)
        self.assertEqual((first["trails"], first["conditions new"]), (6, 6))
        changed = features()
        for f in changed:
            if f["attributes"]["OBJECTID"] == 903:
                f["attributes"].update(Condition="Dry / Tacky - Enjoy", ConditionDate=1791230400000)
        t1 = self.t0 + timedelta(hours=1)
        second = self.store(changed, t1)
        self.assertEqual((second["versions new"], second["conditions new"], second["ended"]), (1, 1, 1))
        rows = self.conn.execute(
            """select attributes->>'state', active, upper(observed) from evt.event
               where source = %s and attributes->>'trail' like '%%0003' order by lower(observed), active""",
            (self.name,)).fetchall()
        self.assertEqual(sorted(rows, key=lambda r: r[1]), [("closed", False, t1), ("dry", True, None)])
        declared = self.conn.execute(
            "select lower(declared) from evt.event where source = %s and active and attributes->>'trail' like '%%0003'",
            (self.name,)).fetchone()[0]
        self.assertEqual(declared, datetime(2026, 10, 6, 2, 0, tzinfo=UTC))          # 20:00 MDT on Oct 5

    def test_a_small_snapshot_is_refused(self):
        self.store(features(), self.t0)
        with self.assertRaisesRegex(RuntimeError, "not taken as a full snapshot"):
            self.store(features()[:2], self.t0 + timedelta(hours=1))

    def test_gate_round_trip_and_heartbeat(self):
        self.store(features(), self.t0)
        sig = layers.signature(fixture("r2r_layer.json"), domains=("Condition",))
        layers.save_signature(self.conn, self.name, sig, read=True)
        saved, read_at = layers.stored_signature(self.conn, self.name)
        self.assertEqual(saved, sig)
        self.assertTrue(layers.unchanged(sig, (saved, read_at), read_at + timedelta(hours=1), r2r.FULL_READ_EVERY))
        t1 = self.t0 + timedelta(minutes=30)
        self.assertEqual(layers.heartbeat(self.conn, self.name, t1), 6)
        self.assertEqual(self.conn.execute("select max(last_seen) from raw.record where source = %s",
                                           (self.name,)).fetchone()[0], t1)


if __name__ == "__main__":
    unittest.main()
