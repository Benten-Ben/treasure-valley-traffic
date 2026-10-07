"""Tests for the 1-minute Kp source (swpc_kp_1m).

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL, inside a transaction that is rolled back. The
fixture is a real SWPC file (public domain) trimmed to 81 minutes, 12:50 to
14:10 UTC on Oct 7, 2026: a partial hour, one complete hour and the start of
the next.

Run: python3 -m unittest discover -s plugins/sky/tests -t .
"""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import http
from ingest.db import version_hash
from plugins.sky.ingest.sources import swpc_kp_1m as kp
from plugins.sky.tests.test_swpc_ovation import interval

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
UTC = timezone.utc


def sample():
    with open(os.path.join(FIXTURES, "kp_1m.json"), encoding="utf-8") as f:
        return json.load(f)


def entry(t, e, index=None, label=None):
    n, lab = kp.derived(e)
    return {"time_tag": t.strftime("%Y-%m-%dT%H:%M:%S"), "kp_index": n if index is None else index,
            "estimated_kp": e, "kp": lab if label is None else label}


def run_of(start, n, e=2.0):
    return [entry(start + timedelta(minutes=i), e) for i in range(n)]


class DerivedTest(unittest.TestCase):
    def test_thirds_give_swpcs_integer_and_label(self):
        cases = {0.0: (0, "0Z"), 0.33: (0, "0P"), 0.67: (1, "1M"), 1.0: (1, "1Z"), 4.33: (4, "4P"),
                 6.67: (7, "7M"), 8.67: (9, "9M"), 9.0: (9, "9Z")}
        for e, want in cases.items():
            self.assertEqual(kp.derived(e), want, e)
        self.assertEqual(kp.derived(None), (None, None))
        self.assertEqual(kp.derived(2.5)[1], None)          # off the thirds: no label to derive

    def test_the_real_sample_is_all_derivable(self):
        for r in sample():
            self.assertEqual(kp.derived(r["estimated_kp"]), (r["kp_index"], r["kp"]), r["time_tag"])


class HoursTest(unittest.TestCase):
    def test_only_whole_hours_inside_the_file_are_kept(self):
        recs = kp.records(kp.minutes(sample()))
        self.assertEqual([r[0] for r in recs], ["2026-10-07T13:00:00Z"])
        source_id, payload, geom = recs[0]
        self.assertIsNone(geom)
        self.assertEqual(set(payload), {"start", "step_s", "estimated_kp"})      # labels all derivable
        self.assertEqual((payload["start"], payload["step_s"], len(payload["estimated_kp"])),
                         ("2026-10-07T13:00:00Z", 60, 60))
        by_time = {r["time_tag"]: r["estimated_kp"] for r in sample()}
        self.assertEqual(payload["estimated_kp"],
                         [by_time[f"2026-10-07T13:{m:02d}:00"] for m in range(60)])

    def test_a_window_starting_on_the_hour_keeps_that_hour(self):
        t = datetime(2026, 10, 7, 9, tzinfo=UTC)
        self.assertEqual([r[0] for r in kp.records(kp.minutes(run_of(t, 120)))],
                         ["2026-10-07T09:00:00Z", "2026-10-07T10:00:00Z"])
        self.assertEqual([r[0] for r in kp.records(kp.minutes(run_of(t, 119)))], ["2026-10-07T09:00:00Z"])
        self.assertEqual(kp.records(kp.minutes(run_of(t + timedelta(minutes=1), 60))), [])
        self.assertEqual(kp.records(kp.minutes([])), [])

    def test_a_missing_minute_is_null_and_an_empty_hour_is_skipped(self):
        t = datetime(2026, 10, 7, 9, tzinfo=UTC)
        rows = [r for r in run_of(t, 180) if not r["time_tag"].startswith("2026-10-07T10:")]
        rows = [r for r in rows if r["time_tag"] != "2026-10-07T09:17:00"]
        recs = dict((sid, p) for sid, p, _ in kp.records(kp.minutes(rows)))
        self.assertEqual(sorted(recs), ["2026-10-07T09:00:00Z", "2026-10-07T11:00:00Z"])
        self.assertIsNone(recs["2026-10-07T09:00:00Z"]["estimated_kp"][17])
        self.assertEqual(recs["2026-10-07T09:00:00Z"]["estimated_kp"].count(None), 1)

    def test_labels_kept_only_where_they_arent_derivable(self):
        rows = sample()
        odd = next(r for r in rows if r["time_tag"] == "2026-10-07T13:05:00")
        odd["kp"], odd["kp_index"] = "9Z", 9
        no_label = next(r for r in rows if r["time_tag"] == "2026-10-07T13:06:00")
        del no_label["kp"]
        payload = kp.records(kp.minutes(rows))[0][1]
        self.assertEqual(payload["labels"], {"5": [9, "9Z"], "6": [no_label["kp_index"], None]})

    def test_the_same_hour_from_overlapping_files_is_the_same_version(self):
        t = datetime(2026, 10, 7, 9, tzinfo=UTC)
        a = dict((s, p) for s, p, _ in kp.records(kp.minutes(run_of(t, 180))))
        b = dict((s, p) for s, p, _ in kp.records(kp.minutes(run_of(t + timedelta(hours=1), 180))))
        both = set(a) & set(b)
        self.assertEqual(both, {"2026-10-07T10:00:00Z", "2026-10-07T11:00:00Z"})
        for sid in both:
            self.assertEqual(version_hash(a[sid]), version_hash(b[sid]))

    def test_refuses_a_file_it_cant_trust(self):
        t = datetime(2026, 10, 7, 9, tzinfo=UTC)
        cases = {
            "bad time": [{"time_tag": "noon", "estimated_kp": 1.0}],
            "no time": [{"estimated_kp": 1.0}],
            "seconds": [{"time_tag": "2026-10-07T09:00:30", "estimated_kp": 1.0}],
            "above 9": [entry(t, 1.0) | {"estimated_kp": 9.33}],
            "negative": [entry(t, 1.0) | {"estimated_kp": -1}],
            "text": [entry(t, 1.0) | {"estimated_kp": "1.0"}],
            "repeated, different": [entry(t, 1.0), entry(t, 2.0)],
            "not an object": ["2026-10-07T09:00:00"],
        }
        for label, rows in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                kp.minutes(rows)
        with self.assertRaises(ValueError):
            kp.minutes({"time_tag": "2026-10-07T09:00:00"})
        self.assertEqual(len(kp.minutes([entry(t, 1.0), entry(t, 1.0)])), 1)     # repeated, identical
        self.assertIsNone(kp.minutes([entry(t, None)])[t]["estimated_kp"])


class SourceTest(unittest.TestCase):
    def test_schedule_and_registry_entry(self):
        s = kp.SOURCE
        self.assertEqual((s["name"], s["access"]), ("swpc_kp_1m", "open"))
        self.assertGreaterEqual(interval(s["schedule"]), timedelta(minutes=10))
        # The file holds about six hours: an hourly run leaves room for several failures in a row.
        self.assertLessEqual(interval(s["schedule"]), timedelta(hours=2))
        self.assertTrue(s["url"].startswith("https://services.swpc.noaa.gov/json/"))
        self.assertGreaterEqual(http.PACE_S[kp.HOST], 2)

    def test_run_stores_whole_hours_never_as_a_full_snapshot(self):
        with open(os.path.join(FIXTURES, "kp_1m.json"), "rb") as f:
            body = f.read()
        fetch = mock.MagicMock(id=51, started_at=datetime(2026, 10, 7, 14, 11, tzinfo=UTC))
        fetch.__enter__.return_value = fetch
        with mock.patch.object(kp.http, "get", return_value=(200, body, "no_rules")) as get, \
                mock.patch.object(kp.db, "ensure_source"), \
                mock.patch.object(kp.db, "Fetch", return_value=fetch), \
                mock.patch.object(kp.db, "upsert_records", return_value=(1, 0, 0)) as upsert:
            stats = kp.run(mock.sentinel.conn)
        self.assertEqual(get.call_args.args[0], kp.URL)
        (conn, source, records, fetch_id, seen), kw = upsert.call_args
        self.assertEqual((source, fetch_id, kw), ("swpc_kp_1m", 51, {"complete": False}))
        self.assertEqual([r[0] for r in records], ["2026-10-07T13:00:00Z"])
        self.assertEqual((fetch.records, fetch.bytes), (1, len(body)))
        self.assertEqual((stats["minutes"], stats["hours"], stats["latest"]), (81, 1, "2026-10-07T14:10:00Z"))


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
                                 (kp.SOURCE["name"], at)).fetchone()[0]

    def test_overlapping_files_add_only_new_hours(self):
        from ingest import db
        c, name = self.conn, kp.SOURCE["name"]
        db.ensure_source(c, kp.SOURCE)
        c.execute("delete from raw.record where source = %s", (name,))       # rolled back
        t = datetime(2026, 10, 7, 9, tzinfo=UTC)
        t0, t1 = t + timedelta(hours=3), t + timedelta(hours=4)
        first = kp.records(kp.minutes(run_of(t, 180)))
        self.assertEqual(db.upsert_records(c, name, first, self.fetch(t0), t0, complete=False), (3, 0, 0))
        second = kp.records(kp.minutes(run_of(t + timedelta(hours=1), 180)))
        self.assertEqual(db.upsert_records(c, name, second, self.fetch(t1), t1, complete=False), (1, 2, 0))
        rows = c.execute("""select source_id, removed_at is null, jsonb_array_length(payload->'estimated_kp')
                            from raw.record where source = %s order by source_id""", (name,)).fetchall()
        self.assertEqual([r[0] for r in rows], ["2026-10-07T09:00:00Z", "2026-10-07T10:00:00Z",
                                                "2026-10-07T11:00:00Z", "2026-10-07T12:00:00Z"])
        self.assertTrue(all(r[1] and r[2] == 60 for r in rows))


if __name__ == "__main__":
    unittest.main()
