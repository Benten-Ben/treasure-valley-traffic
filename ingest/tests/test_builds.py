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
        # ops.build_status looks for the lock Run holds, and words a killed run as the next Run does.
        self.assertIn("hashtextextended('tvt build ' || r.build, 0)", sql)
        self.assertIn("hashtextextended('tvt build ' || %s, 0)", builds.LOCK_KEY)
        self.assertIn(f"'{builds.KILLED}'", sql)

    def test_stored_text_loses_passwords_and_keys(self):
        self.assertEqual(builds.redact("connect to postgres://tvt_build:hunter2@db:5432/tvt failed"),
                         "connect to postgres://tvt_build:***@db:5432/tvt failed")
        self.assertEqual(builds.redact("GET https://x.test/a?api_key=abc123&y=1; PGPASSWORD=pw; token=t"),
                         "GET https://x.test/a?api_key=***&y=1; PGPASSWORD=***; token=***")
        self.assertEqual(builds.redact("41,203 pieces"), "41,203 pieces")
        self.assertIsNone(builds.redact(None))
        conn = FakeConn()
        builds.mark(conn, "roads-build", by="by hand: lead", reason="fixed, see https://x.test/?key=abc")
        self.assertEqual(conn.calls[0][1][2], "fixed, see https://x.test/?key=***")

    def test_a_command_is_shown_without_what_could_be_a_secret(self):
        self.assertEqual(builds.shown(["python3", "-m", "ingest", "segment-match"]), "python3 -m ingest segment-match")
        self.assertEqual(builds.shown(["python3", "-m", "ingest", "segment-match", "--day", "2026-10-12"]),
                         "python3 -m ingest segment-match ...")
        for command, expected in (
                (["env", "DATABASE_URL=postgres://tvt_build:pw@db/tvt", "python3"], "env ..."),
                (["docker", "run", "-e", "API_KEY=abc", "img"], "docker run -e ..."),
                (["psql", "postgres://u:pw@db/tvt"], "psql ..."),
                (["tool", "--password", "hunter2"], "tool ..."),
                (["tool", "--token=abc"], "tool ..."),
                (["ssh", "user@host"], "ssh ..."),
                (["PGPASSWORD=x"], "the command")):
            with self.subTest(command=command):
                self.assertEqual(builds.shown(command), expected)
                self.assertNotRegex(builds.shown(command), "pw|abc|hunter2|user@|PGPASSWORD")


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
    def test_a_run_of_the_same_build_refuses_inside_the_run_wrapper(self):
        conn = FakeConn()
        with mock.patch.dict(os.environ, {builds.RUN_ENV: "trails-match 42"}):
            with self.assertRaisesRegex(RuntimeError, r"already running as run 42 under `python3 -m ingest.builds "
                                                      r"run trails-match`.* is run plainly"):
                builds.Run(conn, "trails-match").__enter__()
            with self.assertRaisesRegex(RuntimeError, "already running as run 42"):
                builds.start(conn, "trails-match")
            self.assertEqual(conn.calls, [])
            builds._may_start("landscape-bake")          # another build may run inside it

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
        # Still marked, but its newest run failed: failed shows (the failure is what needs a look).
        s = self.status()
        self.assertEqual((s["state"], s["last_run_ok"]), ("failed", False))
        self.assertEqual(s["last_error"], "ValueError: bad geometry")
        self.assertIsNotNone(s["pending_since"])
        self.assertEqual(s["pending_by"], ["osm_street"])
        # Not marked (cleared by hand), its newest run failed: failed too.
        builds.done(self.conn, self.b, "by hand")
        self.assertEqual(self.status()["state"], "built")
        with self.assertRaises(RuntimeError), builds.Run(self.conn, self.b):
            raise RuntimeError("again")
        s = self.status()
        self.assertEqual((s["state"], s["pending_since"]), ("failed", None))

    def test_a_runs_note_and_error_are_stored_without_secrets(self):
        with self.assertRaises(ValueError), builds.Run(self.conn, self.b, note="from postgres://u:pw@db/x"):
            raise ValueError("connect to postgres://u:pw@db/x failed; key=abc")
        [(note, error)] = self.conn.execute(
            "select note, error from ops.build_run where build = %s", (self.b,)).fetchall()
        self.assertEqual(note, "from postgres://u:***@db/x")
        self.assertEqual(error, "ValueError: connect to postgres://u:***@db/x failed; key=***")

    def test_a_killed_run_reads_failed_and_the_next_run_closes_it(self):
        builds.mark(self.conn, self.b, by="osm_street", reason="new extract")
        # A Run's row whose process was killed outright: unfinished, and nothing holds the lock.
        killed = builds.start(self.conn, self.b, locked=True)
        s = self.status()
        self.assertEqual((s["state"], s["last_run_ok"], s["last_error"]), ("failed", False, builds.KILLED))
        self.assertIsNone(s["last_run_finished_at"])
        self.assertEqual(s["pending_by"], ["osm_street"])
        # A run from `start` holds no lock, so it can't be told from a live one: running.
        step = builds.start(self.conn, self.b + "-step")
        s = self.status(self.b + "-step")
        self.assertEqual((s["state"], s["last_run_ok"], s["last_error"]), ("running", None, None))
        # The build's next Run holds the lock (running, as this session holds it), and closes the old row.
        with builds.Run(self.conn, self.b) as again:
            s = self.status()
            self.assertEqual((s["state"], s["last_run_ok"], s["last_error"]), ("running", None, None))
        [(finished, ok, error)] = self.conn.execute(
            "select finished_at, ok, error from ops.build_run where id = %s", (killed,)).fetchall()
        self.assertEqual((finished is not None, ok, error), (True, False, builds.KILLED))
        self.assertNotEqual(again.id, killed)
        self.assertEqual(self.status()["state"], "built")
        self.assertEqual(self.pending(), {})
        builds.finish(self.conn, step, ok=True)
        self.assertEqual(self.status(self.b + "-step")["state"], "built")

    def test_the_view_finds_a_lock_by_its_key_whatever_its_sign(self):
        keys = [-2**63, -5_000_000_000, -1, 0, 1, 5_000_000_000, 2**63 - 1]
        try:
            for k in keys:
                self.conn.execute("select pg_advisory_lock(%s)", (k,))
            found = {r[0] for r in self.conn.execute(
                """select ((l.classid::bigint << 32) | l.objid::bigint) from pg_locks l
                   where l.locktype = 'advisory' and l.granted and l.objsubid = 1 and l.pid = pg_backend_pid()
                     and l.database = (select d.oid from pg_database d where d.datname = current_database())""").fetchall()}
        finally:
            for k in keys:
                self.conn.execute("select pg_advisory_unlock(%s)", (k,))
        self.assertTrue(set(keys) <= found, found)

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
        # A second SIGTERM while the run is being logged doesn't cut it short.
        real_finish = builds.finish

        def finish_under_fire(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGTERM)
            return real_finish(*args, **kwargs)
        with self.assertRaises(builds.Stopped), mock.patch.object(builds, "finish", finish_under_fire):
            with builds.Run(self.conn, self.b):
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(5)
        self.assertEqual((self.status()["state"], self.status()["last_error"]), ("failed", "stopped: SIGTERM"))
        self.assertEqual(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)
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
        self.assertEqual(builds.run_command(self.conn, self.b, ["true", "x"]), 0)
        self.assertEqual(self.pending(), {})
        self.assertEqual(self.status()["last_ok_note"], "true x")
        builds.mark(self.conn, self.b, by="osm_paths", reason="new paths")
        with self.assertRaises(builds.CommandFailed) as err:
            builds.run_command(self.conn, self.b, ["sh", "-c", "exit 3", "DATABASE_URL=postgres://u:pw@db/x"])
        self.assertEqual(err.exception.code, 3)
        self.assertEqual(self.status()["last_error"], "CommandFailed: sh -c ... exited 3")
        self.assertEqual(self.pending(), {"osm_paths": (1, "new paths")})
        self.assertEqual(self.status()["state"], "failed")

    def test_run_command_tells_its_command_and_a_run_inside_refuses(self):
        child = ("import os, sys\n"
                 "from ingest import builds\n"
                 "assert os.environ['PGAPPNAME'] == 'tvt-build-' + os.environ[builds.RUN_ENV].split()[1]\n"
                 "try:\n"
                 "    builds.Run(None, sys.argv[1]).__enter__()\n"
                 "except RuntimeError as err:\n"
                 "    sys.exit(9 if 'is run plainly' in str(err) else 8)\n")
        root = os.path.join(HERE, "..", "..")
        with mock.patch.dict(os.environ, {"PYTHONPATH": os.path.abspath(root)}):
            with self.assertRaises(builds.CommandFailed) as err:
                builds.run_command(self.conn, self.b, [sys.executable, "-c", child, self.b])
        self.assertEqual(err.exception.code, 9)
        self.assertNotIn(builds.RUN_ENV, os.environ)

    def stopped_command(self, query, ignore_sigint):
        """Run a command that sits in a query, stop the run with SIGTERM, and return its tag."""
        if signal.getsignal(signal.SIGTERM) != signal.SIG_DFL:
            self.skipTest("SIGTERM has a handler in this process")
        script = ("import os, signal, sys, psycopg\n"
                  + ("signal.signal(signal.SIGINT, signal.SIG_IGN)\n" if ignore_sigint else "")
                  + "c = psycopg.connect(os.environ['TVT_TEST_DATABASE_URL'])\n"
                  + "try:\n"
                  + f"    c.execute({query!r})\n"
                  + "except KeyboardInterrupt:\n"
                  + "    sys.exit(130)\n")
        signal.setitimer(signal.ITIMER_REAL, 1.5)
        old = signal.signal(signal.SIGALRM, lambda *_: os.kill(os.getpid(), signal.SIGTERM))
        started = time.monotonic()
        try:
            with mock.patch.object(builds, "STOP_STEPS", ((signal.SIGINT, 3.0), (signal.SIGTERM, 3.0),
                                                          (signal.SIGKILL, 3.0))), \
                    mock.patch("sys.stderr"), self.assertRaises(builds.Stopped):
                builds.run_command(self.conn, self.b, [sys.executable, "-c", script])
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
        self.assertLess(time.monotonic() - started, 12)
        s = self.status()
        self.assertEqual((s["state"], s["last_error"]), ("failed", "stopped: SIGTERM"))
        [(run_id,)] = self.conn.execute(
            "select id from ops.build_run where build = %s order by id desc limit 1", (self.b,)).fetchall()
        return f"tvt-build-{run_id}"

    def left(self, tag):
        """The sessions still running under tag, after a moment for the server to notice."""
        other = self.psycopg.connect(DB_URL, autocommit=True)
        try:
            for _ in range(20):
                n = other.execute("select count(*) from pg_stat_activity where application_name = %s",
                                  (tag,)).fetchone()[0]
                if n == 0:
                    return 0
                time.sleep(0.25)
            return n
        finally:
            other.close()

    def test_a_stopped_run_cancels_its_commands_query(self):
        # SIGINT alone: psycopg cancels the command's query (the run's own clean-up is off here).
        with mock.patch.object(builds, "_end_sessions", return_value=0) as end:
            tag = self.stopped_command("select pg_sleep(60)", ignore_sigint=False)
        self.assertEqual(end.call_count, 1)
        self.assertEqual(self.left(tag), 0)

    def test_a_stopped_run_ends_the_session_a_killed_command_left(self):
        # The command ignores SIGINT and dies by SIGTERM, without cancelling its query (as when
        # heavy's SIGTERM reaches the whole process group): the run ends the session it left.
        tag = self.stopped_command("select pg_sleep(60)", ignore_sigint=True)
        self.assertEqual(self.left(tag), 0)

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
