"""Tests for the staleness views of migration 0021: ops.source_status and ops.build_status.

Database only: they run against a test database named by TVT_TEST_DATABASE_URL (migrated through
0021), inside one transaction they roll back, with synthetic sources, fetches, runs and marks.
Against a copy of production (the scratch database) they also check the views over its real
fetch log: one row per scheduled source, and quick enough for /api/meta.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import time
import unittest

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a test database migrated through 0021")
class ViewsTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        if not self.conn.execute("select to_regclass('ops.source_status') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("ops.source_status is missing: apply migration 0021")
        self.p = "tvt_test_" + os.urandom(3).hex()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def source(self, name, schedule, fetches=(), access="open"):
        """A source and its fetches: (minutes ago, ok, finished, error)."""
        self.conn.execute(
            "insert into ops.source (name, title, url, access, schedule) values (%s, %s, 'https://example.test/', %s, %s)",
            (name, name.title(), access, schedule))
        for ago, ok, finished, error in fetches:
            self.conn.execute(
                """insert into ops.fetch (source, started_at, finished_at, ok, error)
                   values (%s, now() - make_interval(mins => %s),
                           case when %s then now() - make_interval(mins => %s) + interval '5 s' end, %s, %s)""",
                (name, ago, finished, ago, ok, error))

    def sources(self):
        cur = self.conn.execute(
            "select * from ops.source_status where source like %s order by source", (self.p + "%",))
        cols = [c.name for c in cur.description]
        return {r[0][len(self.p) + 1:]: dict(zip(cols, r)) for r in cur.fetchall()}

    def test_source_states(self):
        ok = (True, True, None)
        self.source(f"{self.p}_fresh", "10 minutes", [(3, *ok)])
        self.source(f"{self.p}_grace", "10 minutes", [(24, *ok)])             # 10 + 15 min grace
        self.source(f"{self.p}_late", "10 minutes", [(26, *ok)])
        self.source(f"{self.p}_stale", "10 minutes", [(46, *ok)])             # past 3 schedules + grace
        self.source(f"{self.p}_daily", "1 day", [(60 * 29, *ok)])              # 1 day + 6 h grace
        self.source(f"{self.p}_daily_late", "1 day", [(60 * 31, *ok)])
        self.source(f"{self.p}_never", "1 hour", [(5, False, True, "HTTPError: 503")])
        self.source(f"{self.p}_unscheduled", None, [(9999, *ok)])
        self.source(f"{self.p}_oneoff", None, [(9999, *ok)], access="one_off")
        s = self.sources()
        self.assertEqual({k: v["state"] for k, v in s.items()}, {
            "fresh": "fresh", "grace": "fresh", "late": "late", "stale": "stale",
            "daily": "fresh", "daily_late": "late", "never": "never"})
        self.assertEqual(s["never"]["failures"], 1)
        self.assertEqual(s["never"]["last_error"], "HTTPError: 503")
        self.assertIsNone(s["never"]["last_ok_at"])
        self.assertEqual(s["fresh"]["title"], f"{self.p}_fresh".title())
        self.assertEqual(round(s["fresh"]["age"].total_seconds() / 60), 3)
        self.assertEqual(s["late"]["due_at"] - s["late"]["last_ok_at"], s["late"]["schedule"])
        self.assertEqual((s["late"]["late_at"] - s["late"]["due_at"]).total_seconds(), 15 * 60)
        self.assertEqual((s["daily"]["late_at"] - s["daily"]["due_at"]).total_seconds(), 6 * 3600)
        self.assertEqual((s["daily"]["stale_at"] - s["daily"]["late_at"]).total_seconds(), 2 * 86400)

    def test_failures_count_finished_attempts_since_the_last_good_one(self):
        self.source(f"{self.p}_failing", "10 minutes", [
            (60, False, True, "old failure"), (50, True, True, None),
            (30, False, True, "URLError: timed out"), (20, False, True, "HTTPError: 502"),
            (10, False, False, None)])                                         # still going (or killed)
        self.source(f"{self.p}_recovered", "10 minutes", [(30, False, True, "HTTPError: 502"), (5, True, True, None)])
        self.source(f"{self.p}_running", "10 minutes", [(8, True, True, None), (1, False, False, None)])
        s = self.sources()
        f = s["failing"]
        self.assertEqual((f["state"], f["failures"], f["last_error"], f["last_try_ok"]),
                         ("stale", 2, "HTTPError: 502", False))
        self.assertEqual(round(f["age"].total_seconds() / 60), 50)
        r = s["recovered"]
        self.assertEqual((r["state"], r["failures"], r["last_error"], r["last_try_ok"]), ("fresh", 0, None, True))
        run = s["running"]
        self.assertEqual((run["state"], run["failures"], run["last_try_ok"]), ("fresh", 0, True))
        self.assertEqual(round((run["last_try_at"] - run["last_ok_at"]).total_seconds()), 0)

    def test_build_states(self):
        b = self.p.replace("_", "-")
        run = """insert into ops.build_run (build, started_at, finished_at, ok, note, error)
                 values (%s, now() - make_interval(hours => %s), now() - make_interval(hours => %s) + %s::interval, %s, %s, %s)"""
        # built: its newest run succeeded, nothing marked
        self.conn.execute(run, (f"{b}-built", 50, 50, "10 min", True, "41 pieces", None))
        self.conn.execute(run, (f"{b}-built", 30, 30, "12 min", True, "42 pieces", None))
        # failed: its newest run failed, nothing marked
        self.conn.execute(run, (f"{b}-failed", 30, 30, "1 min", True, "ok then", None))
        self.conn.execute(run, (f"{b}-failed", 3, 3, "1 min", False, None, "ValueError: bad geometry"))
        # pending: marked (never built), and marked after a good run
        self.conn.execute("insert into ops.build_pending (build, marked_by, reason, first_at, last_at, marks) "
                          "values (%s, 'osm_street', 'new extract', now() - interval '5 h', now() - interval '1 h', 2), "
                          "(%s, 'achd_roads', 'segments changed', now() - interval '2 h', now() - interval '2 h', 1)",
                          (f"{b}-never", f"{b}-never"))
        self.conn.execute(run, (f"{b}-again", 30, 30, "1 min", True, None, None))
        self.conn.execute("insert into ops.build_pending (build, marked_by, reason) values (%s, 'nhd', 'new NHD')",
                          (f"{b}-again",))
        # running: started, not finished (marked too)
        self.conn.execute("insert into ops.build_run (build, started_at) values (%s, now() - interval '20 min')",
                          (f"{b}-running",))
        self.conn.execute("insert into ops.build_pending (build, marked_by, reason) values (%s, 'x', 'y')",
                          (f"{b}-running",))
        cur = self.conn.execute("select * from ops.build_status where build like %s order by build", (b + "-%",))
        cols = [c.name for c in cur.description]
        s = {r[0][len(b) + 1:]: dict(zip(cols, r)) for r in cur.fetchall()}
        self.assertEqual({k: v["state"] for k, v in s.items()},
                         {"built": "built", "failed": "failed", "never": "pending", "again": "pending", "running": "running"})
        self.assertEqual(s["built"]["last_ok_note"], "42 pieces")
        self.assertEqual(round(s["built"]["age"].total_seconds() / 60), 30 * 60 - 12)
        self.assertIsNone(s["built"]["pending_since"])
        self.assertEqual(s["failed"]["last_error"], "ValueError: bad geometry")
        self.assertEqual(s["failed"]["last_ok_note"], "ok then")
        n = s["never"]
        self.assertEqual((n["pending_marks"], n["pending_by"], n["pending_reason"]), (3, ["osm_street", "achd_roads"], "new extract"))
        self.assertIsNone(n["last_ok_at"])
        self.assertIsNone(n["last_run_ok"])
        self.assertEqual(round(s["again"]["age"].total_seconds() / 60), 30 * 60 - 1)
        self.assertIsNone(s["running"]["last_run_finished_at"])
        self.assertIsNone(s["running"]["last_error"])

    def test_over_the_real_fetch_log(self):
        scheduled = self.conn.execute("select count(*) from ops.source where schedule is not null").fetchone()[0]
        rows = self.conn.execute("select source, state from ops.source_status").fetchall()
        self.assertEqual(len(rows), scheduled)
        self.assertEqual(len({r[0] for r in rows}), len(rows))
        self.assertTrue({r[1] for r in rows} <= {"fresh", "late", "stale", "never"})
        started = time.monotonic()
        for _ in range(3):
            self.conn.execute("select * from ops.source_status").fetchall()
            self.conn.execute("select * from ops.build_status").fetchall()
        each = (time.monotonic() - started) / 3
        self.assertLess(each, 0.5, f"the views took {each * 1000:.0f} ms")


if __name__ == "__main__":
    unittest.main()
