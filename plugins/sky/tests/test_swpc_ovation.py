"""Tests for the OVATION aurora source (swpc_ovation).

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL, inside a transaction that is rolled back. The
fixture is a real SWPC file (public domain, Oct 7, 2026, forecast 16:00 UTC)
trimmed to the slice plus a one-degree border: 23 × 33 of its 65,160 points.

Run: python3 -m unittest discover -s plugins/sky/tests -t .
"""

import json
import os
import random
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import http
from ingest.db import version_hash
from plugins.sky.ingest.sources import swpc_ovation as ovation

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def sample():
    with open(os.path.join(FIXTURES, "ovation_slice.json"), encoding="utf-8") as f:
        return json.load(f)


def interval(text):
    """A Postgres interval as written in SOURCE ('30 minutes', '1 hour') -> timedelta."""
    n, unit = re.fullmatch(r"(\d+) (minute|hour|day)s?", text).groups()
    return timedelta(**{unit + "s": int(n)})


class CutTest(unittest.TestCase):
    def test_the_slice_is_651_values_in_rows_south_to_north(self):
        s = ovation.cut(sample())
        self.assertEqual((len(s["aurora"]), {len(r) for r in s["aurora"]}), (31, {21}))
        self.assertEqual(s["grid"], {"west": -125, "south": 35, "step_deg": 1, "columns": 21, "rows": 31})
        self.assertEqual((s["observation_time"], s["forecast_time"]), ("2026-10-07T14:45:00Z", "2026-10-07T16:00:00Z"))
        # Values read from the real file: 65°N runs 7 at 125°W to 9 at 105°W; at 54°N the oval's
        # edge reaches 112°W but not 113°W; the valley's latitudes are all zero.
        self.assertEqual((ovation.value(s, -125, 65), ovation.value(s, -105, 65)), (7, 9))
        self.assertEqual((ovation.value(s, -112, 54), ovation.value(s, -113, 54)), (1, 0))
        self.assertEqual(ovation.value(s, -117, 57), 2)
        self.assertEqual(s["aurora"][0], [0] * 21)
        self.assertEqual(s["aurora"][43 - 35], [0] * 21)

    def test_cells_outside_the_slice_are_ignored(self):
        doc = sample()
        for p in doc["coordinates"]:
            if p[0] in (234, 256) or p[1] in (34, 66):
                p[2] = 99
        doc["coordinates"] += [[0, -90, 50], [116, 43, 100], [244, -43, 100]]
        self.assertEqual(ovation.cut(doc), ovation.cut(sample()))

    def test_longitudes_east_or_signed_give_the_same_slice(self):
        doc = sample()
        for p in doc["coordinates"]:
            p[0] -= 360
        self.assertEqual(ovation.cut(doc), ovation.cut(sample()))

    def test_point_order_doesnt_change_the_record(self):
        doc = sample()
        random.Random(7).shuffle(doc["coordinates"])
        a, b = ovation.record(ovation.cut(sample())), ovation.record(ovation.cut(doc))
        self.assertEqual((a[0], version_hash(a[1])), (b[0], version_hash(b[1])))

    def test_refuses_a_file_it_cant_trust(self):
        def broken(change):
            doc = sample()
            change(doc)
            return doc

        def first_in_slice(doc):
            return next(p for p in doc["coordinates"] if p[0] == 235 and p[1] == 35)

        cases = {
            "missing cell": lambda d: d["coordinates"].remove(first_in_slice(d)),
            "out of range": lambda d: first_in_slice(d).__setitem__(2, 101),
            "negative": lambda d: first_in_slice(d).__setitem__(2, -1),
            "not a number": lambda d: first_in_slice(d).__setitem__(2, "3"),
            "a bool": lambda d: first_in_slice(d).__setitem__(2, True),
            "a null": lambda d: first_in_slice(d).__setitem__(2, None),
            "repeated, different": lambda d: d["coordinates"].append([235, 35, 4]),
            "half-degree grid": lambda d: d["coordinates"].append([240.5, 50, 0]),
            "short point": lambda d: d["coordinates"].append([240, 50]),
            "new format": lambda d: d.__setitem__("Data Format", "[Latitude, Longitude, Aurora]"),
            "no format": lambda d: d.pop("Data Format"),
            "bad time": lambda d: d.__setitem__("Forecast Time", "soon"),
            "no time": lambda d: d.pop("Observation Time"),
            "no coordinates": lambda d: d.pop("coordinates"),
        }
        for label, change in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                ovation.cut(broken(change))
        with self.assertRaises(ValueError):
            ovation.cut([])

    def test_a_repeated_identical_cell_is_fine(self):
        doc = sample()
        doc["coordinates"].append([235, 35, 0])
        self.assertEqual(ovation.cut(doc), ovation.cut(sample()))

    def test_format_check_ignores_spaces_and_case(self):
        doc = sample()
        doc["Data Format"] = "[longitude,latitude, aurora]"
        self.assertEqual(ovation.cut(doc), ovation.cut(sample()))


class RecordTest(unittest.TestCase):
    def test_one_compact_record_per_forecast_time(self):
        source_id, payload, geom = ovation.record(ovation.cut(sample()))
        self.assertEqual(source_id, "2026-10-07T16:00:00Z")
        self.assertEqual(set(payload), {"observation_time", "forecast_time", "grid", "aurora"})
        self.assertLess(len(json.dumps(payload, separators=(",", ":"))), 2000)
        ring = geom["coordinates"][0]
        self.assertEqual((geom["type"], ring[0], ring[-1]), ("Polygon", [-125, 35], [-125, 35]))
        self.assertEqual({tuple(p) for p in ring}, {(-125, 35), (-105, 35), (-105, 65), (-125, 65)})

    def test_another_forecast_is_another_record_and_new_values_a_new_version(self):
        a = ovation.record(ovation.cut(sample()))
        doc = sample()
        doc["Forecast Time"] = "2026-10-07T16:30:00Z"
        self.assertEqual(ovation.record(ovation.cut(doc))[0], "2026-10-07T16:30:00Z")
        doc = sample()
        next(p for p in doc["coordinates"] if p[0] == 245 and p[1] == 60)[2] = 40
        b = ovation.record(ovation.cut(doc))
        self.assertEqual(a[0], b[0])
        self.assertNotEqual(version_hash(a[1]), version_hash(b[1]))


class SourceTest(unittest.TestCase):
    def test_schedule_and_registry_entry(self):
        s = ovation.SOURCE
        self.assertEqual((s["name"], s["access"]), ("swpc_ovation", "open"))
        self.assertEqual(interval(s["schedule"]), timedelta(minutes=30))
        self.assertGreaterEqual(interval(s["retry_after"]), timedelta(minutes=10))
        self.assertTrue(s["url"].startswith("https://services.swpc.noaa.gov/json/"))
        self.assertGreaterEqual(http.PACE_S[ovation.HOST], 2)

    def test_run_stores_one_record_never_as_a_full_snapshot(self):
        with open(os.path.join(FIXTURES, "ovation_slice.json"), "rb") as f:
            body = f.read()
        fetch = mock.MagicMock(id=41, started_at=datetime(2026, 10, 7, 15, tzinfo=timezone.utc))
        fetch.__enter__.return_value = fetch
        with mock.patch.object(ovation.http, "get", return_value=(200, body, "no_rules")) as get, \
                mock.patch.object(ovation.db, "ensure_source"), \
                mock.patch.object(ovation.db, "Fetch", return_value=fetch), \
                mock.patch.object(ovation.db, "upsert_records", return_value=(1, 0, 0)) as upsert:
            stats = ovation.run(mock.sentinel.conn)
        get.assert_called_once()
        self.assertEqual(get.call_args.args[0], ovation.URL)
        (conn, source, records, fetch_id, seen), kw = upsert.call_args
        self.assertEqual((source, fetch_id, seen, kw), ("swpc_ovation", 41, fetch.started_at, {"complete": False}))
        self.assertEqual([r[0] for r in records], ["2026-10-07T16:00:00Z"])
        self.assertEqual((fetch.records, fetch.http_status, fetch.robots, fetch.bytes), (1, 200, "no_rules", len(body)))
        self.assertEqual((stats["cells"], stats["max"], stats["new"]), (651, 9, 1))

    def test_a_bad_file_fails_the_fetch_and_stores_nothing(self):
        doc = sample()
        doc["coordinates"] = doc["coordinates"][:100]
        fetch = mock.MagicMock(id=42, started_at=datetime(2026, 10, 7, 15, tzinfo=timezone.utc))
        fetch.__enter__.return_value = fetch
        with mock.patch.object(ovation.http, "get", return_value=(200, json.dumps(doc).encode(), "no_rules")), \
                mock.patch.object(ovation.db, "ensure_source"), \
                mock.patch.object(ovation.db, "Fetch", return_value=fetch), \
                mock.patch.object(ovation.db, "upsert_records") as upsert, self.assertRaises(ValueError):
            ovation.run(mock.sentinel.conn)
        upsert.assert_not_called()


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with migration 0001)")
class DatabaseTest(unittest.TestCase):
    """The store step against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, at):
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, true) returning id",
                                 (ovation.SOURCE["name"], at)).fetchone()[0]

    def test_snapshots_accumulate_and_none_is_retired(self):
        from ingest import db
        c, name = self.conn, ovation.SOURCE["name"]
        db.ensure_source(c, ovation.SOURCE)
        c.execute("delete from raw.record where source = %s", (name,))       # rolled back
        t0 = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
        first = ovation.record(ovation.cut(sample()))
        self.assertEqual(db.upsert_records(c, name, [first], self.fetch(t0), t0, complete=False), (1, 0, 0))
        t1 = t0 + timedelta(minutes=30)
        self.assertEqual(db.upsert_records(c, name, [first], self.fetch(t1), t1, complete=False), (0, 1, 0))
        doc = sample()
        doc["Forecast Time"] = "2026-10-07T16:30:00Z"
        t2 = t1 + timedelta(minutes=30)
        db.upsert_records(c, name, [ovation.record(ovation.cut(doc))], self.fetch(t2), t2, complete=False)
        rows = c.execute("""select source_id, removed_at is null, payload->'aurora'->30->0, ST_Area(geom)
                            from raw.record where source = %s order by source_id""", (name,)).fetchall()
        self.assertEqual(rows, [("2026-10-07T16:00:00Z", True, 7, 600.0), ("2026-10-07T16:30:00Z", True, 7, 600.0)])


if __name__ == "__main__":
    unittest.main()
