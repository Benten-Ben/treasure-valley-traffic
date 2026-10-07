"""Tests for the USFS Region 4 forest orders source (and the shared run, through it).

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL (a clone with migration 0009), inside a transaction
that is rolled back. The fixture is a trimmed real sample (US federal work,
public domain; see its _note); the run tests answer requests from it.

Run: python3 -m unittest discover -s plugins/lands/tests -t .
"""

import copy
import json
import os
import re
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db, events, http, manifest
from plugins.lands.ingest import closures
from plugins.lands.ingest.sources import usfs_r4_orders as r4

UTC = timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime(2026, 10, 7, 18, tzinfo=UTC)


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def answer(fx, calls):
    """A stand-in for http.get serving a layer from a fixture, the way ArcGIS answers the shared
    reader's requests (metadata, the ID list, ID ranges, IDs). It ignores the box, as the
    reader's by-ID fallback can: features outside the ring come back too."""
    feats, oid = fx["features"], fx["objectIdFieldName"]

    def get(url, timeout=None, compressed=False):
        calls.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if url.endswith("?f=json"):
            body = fx["layer"]
        elif q.get("returnIdsOnly") == ["true"]:
            body = {"objectIdFieldName": oid, "objectIds": [f["attributes"][oid] for f in feats]}
        elif "objectIds" in q:
            ids = {int(i) for i in q["objectIds"][0].split(",")}
            body = {"features": [f for f in feats if f["attributes"][oid] in ids]}
        else:
            lo, hi = map(int, re.search(r">= (\d+) AND \w+ <= (\d+)", q["where"][0]).groups())
            body = {"features": [f for f in feats if lo <= f["attributes"][oid] <= hi]}
        return 200, json.dumps(body).encode(), "no_rules"
    return get


class FakeFetch:
    last = None

    def __init__(self, conn, source):
        self.id, self.started_at = 77, NOW
        self.http_status = self.robots = self.records = self.bytes = None
        FakeFetch.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def run_offline(module, fx, last_read=None, drop_note=None):
    """module's run against a fixture, with the database calls stubbed. Returns
    (stats, requested URLs, upsert_records mock, events.upsert mock)."""
    calls = []
    with mock.patch.object(http, "get", answer(fx, calls)), \
            mock.patch.object(db, "ensure_source"), mock.patch.object(db, "Fetch", FakeFetch), \
            mock.patch.object(closures, "last_read", return_value=last_read), \
            mock.patch.object(closures, "check_drop", return_value=drop_note), \
            mock.patch.object(db, "upsert_records", return_value=(1, 2, 0)) as up, \
            mock.patch.object(events, "upsert", return_value={"new": 1, "changed": 0, "unchanged": 0, "gone": 0}) as ev:
        stats = closures.run_layer(None, module.SOURCE, module.LAYER, required=module.REQUIRED, key=module.key,
                                   event=module.event, sleep=lambda s: None)
    return stats, calls, up, ev


class OrdersTest(unittest.TestCase):
    def setUp(self):
        self.fx = fixture("usfs_r4_orders")
        self.groups = closures.snapshot(self.fx["features"], r4.key)

    def test_polygons_are_grouped_by_order_number(self):
        self.assertEqual(sorted(self.groups), ["0402-01-122", "0402-03-134", "0402-05-101"])
        self.assertEqual(len(self.groups["0402-01-122"]), 2)            # Deer Point: two polygons, one order

    def test_the_record_is_compact_and_lossless(self):
        payload = closures.merge(self.groups["0402-01-122"])
        self.assertEqual(payload["ordername"], "Deer Point Area, Road, and Trail Closure")
        self.assertEqual(payload["hyperlink"],
                         "https://www.fs.usda.gov/r04/boise/alerts/deer-point-road-trail-and-area-closure-aug-17-nov-30-2026")
        self.assertEqual(sorted(p["acres"] for p in payload["_parts"]), [201, 361])
        self.assertEqual(len({p["crc"] for p in payload["_parts"]}), 2)
        for gone in ("objectid", "Shape__Area", "Shape__Length"):
            self.assertNotIn(gone, json.dumps(payload))
        # Renumbered object IDs and another feature order: the same version.
        shuffled = copy.deepcopy(self.fx["features"])[::-1]
        for i, f in enumerate(shuffled):
            f["attributes"]["objectid"] = 90000 + i
        again = closures.snapshot(shuffled, r4.key)
        self.assertEqual(db.version_hash(closures.merge(again["0402-01-122"])), db.version_hash(payload))

    def test_geometry_keeps_every_outer_ring_and_its_holes(self):
        geom = closures.combine([g for _, g in self.groups["0402-01-122"]])
        self.assertEqual(geom["type"], "MultiPolygon")
        self.assertEqual(sorted(len(p) - 1 for p in geom["coordinates"]), [0, 0, 4])   # 3 outer rings, 4 holes
        camping = closures.combine([g for _, g in self.groups["0402-05-101"]])
        self.assertEqual(sorted(len(p) - 1 for p in camping["coordinates"]), [0, 0, 0, 3])
        # Features touching the ring come back whole: some of Lowman's camping areas lie east of it.
        inside = [closures.in_ring({"type": "Polygon", "coordinates": p}) for p in camping["coordinates"]]
        self.assertTrue(any(inside) and not all(inside))
        self.assertTrue(closures.in_ring(camping))

    def test_the_event_row(self):
        payload = closures.merge(self.groups["0402-01-122"])
        geom = closures.combine([g for _, g in self.groups["0402-01-122"]])
        row = r4.event("0402-01-122", payload, geom)
        self.assertEqual((row["source_id"], row["kind"]), ("0402-01-122", "closure"))
        self.assertEqual(row["start"], datetime(2026, 8, 17, 6, tzinfo=UTC))       # Aug 17, local midnight
        self.assertEqual(row["end"], datetime(2026, 12, 1, 7, tzinfo=UTC))         # through Nov 30
        a = row["attributes"]
        self.assertEqual((a["order_number"], a["forest"], a["acres"], a["polygons"]),
                         ("0402-01-122", "Boise National Forest", 562, 2))
        self.assertEqual((a["signed"], a["start_date"], a["end_date"], a["rescinded"]),
                         ("2026-08-13", "2026-08-17", "2026-11-30", None))
        self.assertTrue(a["link"].startswith("https://www.fs.usda.gov/"))
        self.assertIn("timber harvest", row["description"])
        restriction = r4.event("0402-05-101", closures.merge(self.groups["0402-05-101"]), None)
        self.assertEqual(restriction["kind"], "restriction")
        self.assertIsNotNone(events.content_hash(row))

    def test_a_rescinded_order_ends_on_its_rescind_date(self):
        attrs = dict(self.fx["features"][1]["attributes"], rescinddate=1790078400000)    # Sep 22, 2026
        row = r4.event("x", closures.merge([(attrs, None)]), None)
        self.assertEqual(row["end"], datetime(2026, 9, 22, 6, tzinfo=UTC))
        self.assertEqual(row["attributes"]["fixes"], ["ended_by_rescind_date"])

    def test_an_order_without_a_number_gets_a_stable_key(self):
        attrs = dict(self.fx["features"][0]["attributes"], ordernum=" ")
        k = r4.key(attrs)
        self.assertTrue(k.startswith("unnumbered:"))
        self.assertEqual(k, r4.key(dict(attrs, objectid=1)))
        self.assertEqual(r4.key({"ordernum": " 0402-01-122 "}), "0402-01-122")

    def test_the_source_and_its_manifest_entry(self):
        self.assertEqual(r4.SOURCE["schedule"], "1 hour")
        self.assertEqual(r4.SOURCE["access"], "open")
        m = manifest.load(os.path.dirname(HERE))
        entry = next(e for e in m.manifest["sources"] if e["name"] == "usfs_r4_orders")
        self.assertEqual((entry["license"], entry["credit"], entry["republish"]),
                         (r4.SOURCE["license"], r4.SOURCE["credit"], "yes"))
        self.assertEqual(closures.missing_fields(self.fx["layer"], r4.REQUIRED), [])


class RunTest(unittest.TestCase):
    """The shared run (edit gate, read, ring cut, store) with the database stubbed."""

    def setUp(self):
        self.fx = fixture("usfs_r4_orders")

    def test_a_first_run_reads_the_ring_query_only(self):
        stats, calls, up, ev = run_offline(r4, self.fx)
        self.assertTrue(calls[0].endswith("/FeatureServer/0?f=json"))
        ids_query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[1]).query)
        self.assertEqual((ids_query["geometry"], ids_query["geometryType"], ids_query["spatialRel"]),
                         (["-117.3,42.9,-115.6,44.3"], ["esriGeometryEnvelope"], ["esriSpatialRelIntersects"]))
        features_query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[2]).query)
        self.assertEqual((features_query["geometryPrecision"], features_query["outSR"]), (["6"], ["4326"]))
        self.assertEqual(len(calls), 3)
        self.assertFalse(any(http.EDIT_OPS.search(urllib.parse.urlsplit(u).path) for u in calls))
        records = list(up.call_args.args[2])
        self.assertEqual(sorted(r[0] for r in records), ["0402-01-122", "0402-03-134", "0402-05-101"])
        self.assertTrue(up.call_args.kwargs["complete"])
        self.assertEqual(sorted(r["source_id"] for r in ev.call_args.args[2]),
                         ["0402-01-122", "0402-03-134", "0402-05-101"])
        self.assertEqual((FakeFetch.last.records, stats["features"], stats["records"]), (3, 4, 3))
        self.assertGreater(FakeFetch.last.bytes, 0)

    def test_an_unedited_layer_is_not_read_again(self):
        last = datetime(2026, 10, 7, 12, tzinfo=UTC)          # after the fixture's last edit (Oct 3)
        stats, calls, up, ev = run_offline(r4, self.fx, last_read=last)
        self.assertEqual(len(calls), 1)
        self.assertIn("skipped", stats["read"])
        self.assertIsNone(FakeFetch.last.records)
        up.assert_not_called()
        ev.assert_not_called()
        # A day later it is read anyway.
        stats, calls, _, _ = run_offline(r4, self.fx, last_read=NOW - timedelta(hours=25))
        self.assertEqual(len(calls), 3)

    def test_a_changed_schema_fails_the_run(self):
        fx = copy.deepcopy(self.fx)
        fx["layer"]["fields"] = [f for f in fx["layer"]["fields"] if f["name"] != "ordernum"]
        with self.assertRaises(RuntimeError):
            run_offline(r4, fx)


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0009)")
class DatabaseTest(unittest.TestCase):
    """The store, guard and gate against a real (scratch) database, rolled back afterwards."""
    SOURCE = {"name": "test_lands_orders", "title": "test", "url": "https://example.test/", "access": "open"}

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        if not self.conn.execute("select to_regclass('evt.event') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("evt.event is missing: apply migration 0009")
        db.ensure_source(self.conn, self.SOURCE)
        self.groups = closures.snapshot(fixture("usfs_r4_orders")["features"], r4.key)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, at, ok=True, records=None):
        return self.conn.execute("""insert into ops.fetch (source, started_at, ok, records)
                                    values (%s, %s, %s, %s) returning id""",
                                 (self.SOURCE["name"], at, ok, records)).fetchone()[0]

    def test_orders_are_stored_and_end_when_they_leave_the_layer(self):
        c, name = self.conn, self.SOURCE["name"]
        t0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
        stats = closures.store(c, name, self.fetch(t0, records=3), t0, self.groups, r4.event)
        self.assertEqual((stats["record versions new"], stats["events new"]), (3, 3))
        kinds = dict(c.execute("select source_id, kind from evt.event where source = %s", (name,)).fetchall())
        self.assertEqual(kinds, {"0402-01-122": "closure", "0402-03-134": "closure", "0402-05-101": "restriction"})
        shapes = c.execute("""select bool_and(GeometryType(geom) in ('POLYGON', 'MULTIPOLYGON')),
                                     bool_and(lower(declared) is not null and upper(declared) is not null)
                              from evt.event where source = %s""", (name,)).fetchone()
        self.assertEqual(shapes, (True, True))
        # An hour later, unchanged: nothing new.
        t1 = t0 + timedelta(hours=1)
        stats = closures.store(c, name, self.fetch(t1, records=3), t1, self.groups, r4.event)
        self.assertEqual((stats["record versions new"], stats["events unchanged"]), (0, 3))
        # Grimes Creek leaves the layer.
        t2 = t1 + timedelta(hours=1)
        left = {k: v for k, v in self.groups.items() if k != "0402-03-134"}
        stats = closures.store(c, name, self.fetch(t2, records=2), t2, left, r4.event)
        self.assertEqual((stats["removed"], stats["events gone"]), (1, 1))
        row = c.execute("""select active, upper(observed) from evt.event
                           where source = %s and source_id = '0402-03-134'""", (name,)).fetchone()
        self.assertEqual(row, (False, t2))
        self.assertEqual(closures.last_read(c, name), t2)

    def test_a_big_drop_is_taken_only_when_seen_twice(self):
        c, name = self.conn, self.SOURCE["name"]
        t0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
        closures.store(c, name, self.fetch(t0, records=3), t0, self.groups, r4.event)
        first = self.fetch(t0 + timedelta(hours=1), ok=False, records=1)
        with self.assertRaises(RuntimeError):
            closures.check_drop(c, name, first, 1)
        second = self.fetch(t0 + timedelta(hours=2), records=1)
        self.assertIn("seen twice", closures.check_drop(c, name, second, 1))
        self.assertIsNone(closures.check_drop(c, name, second, 3))


if __name__ == "__main__":
    unittest.main()
