"""Tests for what the water plugin's pollers share (ingest/common.py), and their SOURCE entries."""

import importlib
import json
import os
import re
import unittest
from datetime import datetime, timezone
from unittest import mock

from ingest import db
from plugins.water.ingest import common

from . import FakeConn

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = {"minute": 1, "minutes": 1, "hour": 60, "hours": 60, "day": 1440, "days": 1440}


def minutes(interval):
    n, unit = re.fullmatch(r"(\d+) (\w+)", interval).groups()
    return int(n) * UNITS[unit]


class CommonTest(unittest.TestCase):
    def test_the_ring(self):
        self.assertEqual(common.RING, (-117.30, 42.90, -115.60, 44.30))
        self.assertTrue(common.in_ring(-116.2, 43.6))          # Boise
        self.assertTrue(common.in_ring(-117.30, 44.30))        # edges count
        self.assertFalse(common.in_ring(-114.5, 43.6))         # Twin Falls side
        self.assertFalse(common.in_ring(None, 43.6))
        self.assertFalse(common.in_ring("x", "y"))

    def test_times(self):
        t = common.parse_time("2026-10-07T12:45:00Z")
        self.assertEqual(t, datetime(2026, 10, 7, 12, 45, tzinfo=timezone.utc))
        self.assertEqual(common.iso(t), "2026-10-07T12:45:00Z")
        self.assertEqual(common.parse_time("2026-10-07T06:45:00-06:00"), t)
        self.assertEqual(common.parse_time("2026-10-07T12:45:00"), t)   # no zone: UTC
        self.assertIsNone(common.parse_time(""))
        self.assertIsNone(common.parse_time("soon"))

    def test_point(self):
        self.assertEqual(common.point(-116.123456789, 43.5), {"type": "Point", "coordinates": [-116.123457, 43.5]})
        self.assertIsNone(common.point(None, 43.5))

    def test_store_readings_writes_only_what_we_dont_hold(self):
        held = {"a": 1}
        conn = FakeConn({"select source_id, version_hash": [("A", db.version_hash(held))]})
        records = [("A", held, None), ("A", {"a": 2}, None), ("B", {"b": 1}, None), ("B", {"b": 1}, None)]
        with mock.patch.object(db, "upsert_records", return_value=(2, 0, 0)) as up:
            new, already = common.store_readings(conn, "src", records, 7, "now")
        written = list(up.call_args.args[2])
        self.assertEqual([(i, p) for i, p, _ in written], [("A", {"a": 2}), ("B", {"b": 1})])
        self.assertIs(up.call_args.kwargs["complete"], False)
        self.assertEqual((new, already), (2, 2))
        self.assertEqual(conn.executed[0][1], ("src", ["A", "B"]))

    def test_store_readings_with_nothing(self):
        conn = FakeConn()
        self.assertEqual(common.store_readings(conn, "src", [], 1, "now"), (0, 0))
        self.assertEqual(conn.executed, [])

    def test_a_small_snapshot_is_refused(self):
        conn = FakeConn({"select count(*) from raw.record": [(100,)]})
        common.check_raw_snapshot(conn, "src", 60, "src")
        with self.assertRaisesRegex(RuntimeError, "only 40 records against 100"):
            common.check_raw_snapshot(conn, "src", 40, "src")
        with self.assertRaises(RuntimeError):
            common.check_raw_snapshot(FakeConn({"count(*)": [(0,)]}), "src", 0, "src")
        common.check_raw_snapshot(FakeConn({"count(*)": [(0,)]}), "src", 3, "src")     # the first snapshot


class SourcesTest(unittest.TestCase):
    """Every source in the manifest: polite schedules, open access, the manifest's license and credit."""

    def test_sources(self):
        with open(os.path.join(PLUGIN, "plugin.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["name"], "water")
        self.assertEqual((manifest["visibility"], manifest["depends"], manifest["order"]), ("public", [], 62))
        self.assertEqual(manifest["tables"], ["raw.record", "evt.event"])
        expected = {"nwps_gauges": "30 minutes", "nrcs_snotel": "1 hour", "boise_ecoli": "12 hours",
                    "boise_river_hazards": "1 hour", "usdm_drought": "12 hours"}
        self.assertEqual([e["name"] for e in manifest["sources"]], list(expected))
        for entry in manifest["sources"]:
            with self.subTest(entry["name"]):
                m = importlib.import_module(f"plugins.water.{entry['module']}")
                s = m.SOURCE
                self.assertEqual((s["name"], s["license"], s["credit"]), (entry["name"], entry["license"], entry["credit"]))
                self.assertEqual(s["access"], "open")
                self.assertEqual(s["schedule"], expected[s["name"]])
                self.assertGreaterEqual(minutes(s["schedule"]), 10)
                self.assertTrue(callable(m.run))
        republish = {e["name"]: e["republish"] for e in manifest["sources"]}
        self.assertEqual(republish["boise_ecoli"], "internal")           # City layers: no license stated
        self.assertEqual(republish["boise_river_hazards"], "internal")


if __name__ == "__main__":
    unittest.main()
