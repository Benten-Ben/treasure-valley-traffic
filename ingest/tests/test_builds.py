"""Tests for ingest/builds.py: build marks and build runs (ops.build_pending, ops.build_run; migration 0021).

The offline tests cover the names, the SQL a mark sends, the refusal inside `ingest serve` and the
command line's arguments. The database tests run only against a test database named by
TVT_TEST_DATABASE_URL (migrated through 0021). They work inside one transaction that they roll
back: Run's commits become savepoints (Tx below), so they leave nothing behind.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import signal
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import builds

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATION = os.path.join(HERE, "..", "..", "db", "migrations", "0021_staleness.sql")


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))

    def commit(self):
        self.calls.append(("commit", None))


class NamesTest(unittest.TestCase):
    def test_accepts_command_and_job_names(self):
        for name in ("roads-build", "water-build", "trails-match", "landscape-bake", "soils.export", "g1_paint", "a"):
            builds.check_name(name)

    def test_refuses_others(self):
        for name in ("", "Roads-build", "1build", "-x", "roads build", "roads/build", "a" * 65, None, 3):
            with self.subTest(name=name), self.assertRaises(ValueError):
                builds.check_name(name)

    def test_the_pattern_matches_the_migration(self):
        with open(MIGRATION, encoding="utf-8") as f:
            sql = f.read()
        self.assertEqual(sql.count(f"build ~ '^{builds.NAME.pattern}$'"), 2)
        self.assertIn(f"length(marked_by) <= {builds.MARKED_BY_MAX}", sql)


class MarkTest(unittest.TestCase):
    def test_upserts_one_row_and_counts_up(self):
        conn = FakeConn()
        builds.mark(conn, "roads-build", by="osm_street", reason="  new extract 2026-10-12  ")
        [(sql, params)] = conn.calls
        self.assertTrue(sql.startswith("insert into ops.build_pending (build, marked_by, reason)"))
        self.assertIn("on conflict (build, marked_by) do update set marks = ops.build_pending.marks + 1", sql)
        self.assertIn("first_at = least(", sql)
        self.assertIn("last_at = greatest(", sql)
        self.assertEqual(params, ("roads-build", "osm_street", "new extract 2026-10-12"))

    def test_checks_before_writing_and_never_commits(self):
        conn = FakeConn()
        for kwargs in ({"by": "", "reason": "x"}, {"by": "x" * 121, "reason": "x"}, {"by": "osm", "reason": " "},
                       {"by": None, "reason": "x"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                builds.mark(conn, "roads-build", **kwargs)
        with self.assertRaises(ValueError):
            builds.mark(conn, "Roads", by="osm", reason="x")
        with self.assertRaisesRegex(ValueError, "can't mark itself"):
            builds.Run(conn, "roads-build", then=["landscape-bake", "roads-build"])
        self.assertEqual(conn.calls, [])
        builds.mark(conn, "roads-build", by="osm", reason="r" * 600)
        self.assertEqual(len(conn.calls[0][1][2]), builds.REASON_MAX)
        self.assertNotIn(("commit", None), conn.calls)


class ServeTest(unittest.TestCase):
    def test_builds_refuse_inside_ingest_serve(self):
        conn = FakeConn()
        with mock.patch.dict(os.environ, {builds.SERVE_ENV: "1"}):
            with self.assertRaisesRegex(RuntimeError, "never run inside `ingest serve`"):
                builds.Run(conn, "roads-build").__enter__()
            with self.assertRaisesRegex(RuntimeError, "never run inside `ingest serve`"):
                builds.start(conn, "roads-build")
            builds.mark(conn, "roads-build", by="achd_roads", reason="segments changed")   # marking is fine
        self.assertEqual(len(conn.calls), 1)

    def test_serve_sets_the_flag_before_its_loop(self):
        from ingest import __main__ as cli
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(builds.SERVE_ENV, None)
            with mock.patch.object(cli.db, "connect", side_effect=RuntimeError("no database")), \
                    mock.patch.object(cli.time, "sleep", side_effect=KeyboardInterrupt), \
                    mock.patch("builtins.print"):
                with self.assertRaises(KeyboardInterrupt):
                    cli.serve(300)
            self.assertEqual(os.environ.get(builds.SERVE_ENV), "1")
            self.assertTrue(builds.in_serve())


class CommandLineTest(unittest.TestCase):
    def test_run_needs_a_command_and_only_run_takes_one(self):
        with mock.patch("sys.stderr"):
            for argv in (["run", "roads-build"], ["mark", "roads-build", "--by", "x", "--reason", "y", "--", "ls"],
                         ["finish", "3"], ["mark", "roads-build", "--by", "x"]):
                with self.subTest(argv=argv), self.assertRaises(SystemExit) as err:
                    builds.main(argv)
                self.assertEqual(err.exception.code, 2)

    def test_describes_a_row(self):
        now = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
        row = {"build": "roads-build", "state": "pending", "last_ok_at": now - timedelta(days=9),
               "last_run_at": now - timedelta(days=9), "pending_since": now - timedelta(hours=5),
               "pending_by": ["osm_street", "achd_roads"], "pending_reason": "new extract", "last_error": None}
        line = builds.describe(row, now)
        self.assertIn("roads-build", line)
        self.assertIn("marked since 5 h ago (osm_street; achd_roads), newest: new extract", line)
        self.assertIn("last built 9 d ago", line)
        self.assertIn("last built never", builds.describe({**row, "last_ok_at": None}, now))


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


class Tx:
    """A connection whose commit() and rollback() stay inside one outer transaction (as
    savepoints), so the test can roll everything back."""

    def __init__(self, conn):
        self.conn = conn
        conn.execute("savepoint tvt_test")

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.execute("release savepoint tvt_test")
        self.conn.execute("savepoint tvt_test")

    def rollback(self):
        self.conn.execute("rollback to savepoint tvt_test")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a test database migrated through 0021")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.psycopg = psycopg
        self.raw = psycopg.connect(DB_URL)
        if not self.raw.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
            self.raw.close()
            self.skipTest("ops.build_pending is missing: apply migration 0021")
        self.conn = Tx(self.raw)
        self.b = "tvt-test-" + os.urandom(3).hex()

    def tearDown(self):
        self.raw.rollback()
        self.raw.close()

    def pending(self, build=None):
        return {r[0]: r[1:] for r in self.conn.execute(
            "select marked_by, marks, reason from ops.build_pending where build = %s order by marked_by",
            (build or self.b,)).fetchall()}

    def status(self, build=None):
        cur = self.conn.execute("select * from ops.build_status where build = %s", (build or self.b,))
        row = cur.fetchone()
        return None if row is None else dict(zip([c.name for c in cur.description], row))

    def test_a_run_clears_what_it_saw_and_keeps_what_came_while_it_ran(self):
        builds.mark(self.conn, self.b, by="osm_street", reason="new extract")
        builds.mark(self.conn, self.b, by="osm_street", reason="new extract again")
        builds.mark(self.conn, self.b, by="achd_roads", reason="segments changed")
        self.assertEqual(self.pending(), {"achd_roads": (1, "segments changed"), "osm_street": (2, "new extract again")})
        self.assertEqual(self.status()["state"], "pending")
        self.assertEqual(self.status()["pending_marks"], 3)
        self.assertEqual(self.status()["pending_by"], ["achd_roads", "osm_street"])
        self.assertIsNone(self.status()["last_ok_at"])
        with builds.Run(self.conn, self.b, then=[self.b + "-next"]) as run:
            self.assertEqual(self.status()["state"], "running")
            builds.mark(self.conn, self.b, by="osm_street", reason="a mark while it runs")
            builds.mark(self.conn, self.b, by="nhd", reason="a new marker while it runs")
            run.note = "12 pieces"
        self.assertEqual(run.cleared, 1)     # achd_roads; osm_street counted up, nhd is new
        self.assertEqual(self.pending(), {"nhd": (1, "a new marker while it runs"),
                                          "osm_street": (3, "a mark while it runs")})
        s = self.status()
        self.assertEqual((s["state"], s["last_ok_note"], s["last_run_ok"]), ("pending", "12 pieces", True))
        self.assertIsNotNone(s["last_ok_at"])
        self.assertEqual(self.pending(self.b + "-next"), {self.b: (1, f"{self.b} finished (run {run.id})")})
        [(covers,)] = self.conn.execute("select covers from ops.build_run where id = %s", (run.id,)).fetchall()
        self.assertEqual(len(covers), 2)
        # The next run sees the rest and clears it.
        with builds.Run(self.conn, self.b):
            pass
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.status()["state"], "built")

    def test_a_failed_run_clears_nothing_and_rolls_its_work_back(self):
        builds.mark(self.conn, self.b, by="osm_street", reason="new extract")
        with self.assertRaisesRegex(ValueError, "bad geometry"):
            with builds.Run(self.conn, self.b, then=[self.b + "-next"]):
                builds.mark(self.conn, self.b + "-side", by="x", reason="written by the failed build")
                raise ValueError("bad geometry")
        self.assertEqual(self.pending(), {"osm_street": (1, "new extract")})
        self.assertEqual(self.pending(self.b + "-side"), {})
        self.assertEqual(self.pending(self.b + "-next"), {})
        s = self.status()
        self.assertEqual((s["state"], s["last_run_ok"]), ("pending", False))
        self.assertEqual(s["last_error"], "ValueError: bad geometry")
        # Not marked any more (cleared by hand), its newest run failed: failed.
        builds.done(self.conn, self.b, "by hand")
        with self.assertRaises(RuntimeError), builds.Run(self.conn, self.b):
            raise RuntimeError("again")
        self.assertEqual(self.status()["state"], "failed")

    def test_sigterm_is_logged_as_stopped(self):
        if signal.getsignal(signal.SIGTERM) != signal.SIG_DFL:
            self.skipTest("SIGTERM has a handler in this process")
        with self.assertRaises(builds.Stopped) as stopped:
            with builds.Run(self.conn, self.b):
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(5)
                self.fail("SIGTERM didn't stop the build")
        self.assertEqual(stopped.exception.code, 128 + signal.SIGTERM)
        self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)
        self.assertEqual(self.status()["last_error"], "stopped: SIGTERM")
        # A query in flight is cancelled, and the connection stays usable.
        with self.assertRaises(builds.Stopped):
            with builds.Run(self.conn, self.b):
                self.conn.execute("select pg_sleep(0)")
                signal.setitimer(signal.ITIMER_REAL, 0.2)
                old = signal.signal(signal.SIGALRM, lambda *_: os.kill(os.getpid(), signal.SIGTERM))
                try:
                    self.conn.execute("select pg_sleep(5)")
                finally:
                    signal.signal(signal.SIGALRM, old)
        self.assertEqual(self.status()["last_error"], "stopped: SIGTERM")

    def test_one_run_of_a_build_at_a_time(self):
        other = self.psycopg.connect(DB_URL)
        try:
            with builds.Run(self.conn, self.b):
                with self.assertRaisesRegex(builds.Busy, "already running"):
                    builds.Run(other, self.b).__enter__()
                other.rollback()
                with builds.Run(Tx(other), self.b + "-other"):     # another build may run
                    pass
                other.rollback()
            key = other.execute(builds.LOCK_KEY, (self.b,)).fetchone()[0]
            self.assertTrue(other.execute("select pg_try_advisory_lock(%s)", (key,)).fetchone()[0])
            other.execute("select pg_advisory_unlock(%s)", (key,))
        finally:
            other.rollback()
            other.close()

    def test_start_and_finish_for_a_step_outside(self):
        builds.mark(self.conn, self.b, by="roads-build", reason="roads built")
        run_id = builds.start(self.conn, self.b)
        self.assertEqual(self.status()["state"], "running")
        builds.mark(self.conn, self.b, by="water-build", reason="water built")
        self.assertEqual(builds.finish(self.conn, run_id, ok=True, note="landscape-3fa9c1.pmtiles"), 1)
        self.assertEqual(self.pending(), {"water-build": (1, "water built")})
        [(started, finished)] = self.conn.execute(
            "select started_at, finished_at from ops.build_run where id = %s", (run_id,)).fetchall()
        self.assertGreater(finished, started)          # clock times, not the transaction's
        with self.assertRaisesRegex(ValueError, "already finished"):
            builds.finish(self.conn, run_id, ok=True)
        with self.assertRaisesRegex(ValueError, "no build run"):
            builds.finish(self.conn, -1, ok=True)
        run_id = builds.start(self.conn, self.b)
        self.assertEqual(builds.finish(self.conn, run_id, ok=False, error="worker exited 1"), 0)
        self.assertEqual(self.status()["last_error"], "worker exited 1")
        self.assertEqual(self.pending(), {"water-build": (1, "water built")})

    def test_run_command(self):
        builds.mark(self.conn, self.b, by="osm_paths", reason="new paths")
        self.assertEqual(builds.run_command(self.conn, self.b, [sys.executable, "-c", "pass"]), 0)
        self.assertEqual(self.pending(), {})
        self.assertIn("-c pass", self.status()["last_ok_note"])
        builds.mark(self.conn, self.b, by="osm_paths", reason="new paths")
        with self.assertRaises(builds.CommandFailed) as err:
            builds.run_command(self.conn, self.b, [sys.executable, "-c", "import sys; sys.exit(3)"])
        self.assertEqual(err.exception.code, 3)
        self.assertRegex(self.status()["last_error"], r"^CommandFailed: .* exited 3$")
        self.assertEqual(self.pending(), {"osm_paths": (1, "new paths")})

    def test_the_tables_refuse_bad_rows(self):
        for sql in ("insert into ops.build_pending (build, marked_by, reason) values ('Bad', 'x', 'y')",
                    "insert into ops.build_pending (build, marked_by, reason) values ('ok', ' ', 'y')",
                    "insert into ops.build_pending (build, marked_by, reason) values ('ok', 'x', '')",
                    "insert into ops.build_pending (build, marked_by, reason, first_at, last_at) "
                    "values ('ok', 'x', 'y', now(), now() - interval '1 s')",
                    "insert into ops.build_run (build) values ('a b')",
                    "insert into ops.build_run (build, covers) values ('ok', '{}')",
                    "insert into ops.build_run (build, started_at, finished_at) values ('ok', now(), now() - interval '1 s')"):
            with self.subTest(sql=sql), self.assertRaises(self.psycopg.errors.CheckViolation):
                self.conn.execute(sql)
            self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
