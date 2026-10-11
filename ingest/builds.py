"""Build marks and build runs (ops.build_pending and ops.build_run, migration 0021; plan §0 item 27, M1).

Builds (roads-build, water-build, trails-match, the exports, the base bake, ...) never run inside
`ingest serve`: Run refuses there. A source whose new data a build should take in marks the build,
**in the same transaction as its data**, so the mark and the data appear together:

    builds.mark(conn, "roads-build", by="osm_street", reason="new extract 2026-10-12 (md5 3fa9...)")

The build runs by hand (under the VM's heavy when it's a heavy job) and logs its run. If it
succeeds, it clears the marks that were pending when it started, in the same transaction as its
data, and may mark the builds that follow it:

    with builds.Run(conn, "roads-build", then=["landscape-bake"]) as run:
        ...                              # the build; run.note = "41,203 pieces"

A mark made while the build ran stays for the next run (a run clears marks by id and count, as
it saw them when it started). A run that fails clears nothing; its error is logged. Only one run
of a build goes at a time in a database (an advisory lock), and a run stopped by SIGTERM (heavy's
deadline) is logged as stopped.

A build's name is the command that runs it (`roads-build`), or for a worker step its job
(`landscape-bake`): lower-case letters, digits, '.', '_' and '-'. `marked_by` names the source
or command that marked it, or 'by hand: <who>'.

From the command line (a worker step can't reach the database, so its run is logged around it):

  python3 -m ingest.builds                       # each build: state, pending marks, age
  python3 -m ingest.builds mark roads-build --by 'by hand: lead' --reason 'ACHD widths fixed'
  python3 -m ingest.builds run trails-match -- python3 -m ingest trails-match
  python3 -m ingest.builds start landscape-bake   # prints the run's id
  python3 -m ingest.builds finish 42 --ok --note 'landscape-3fa9c1.pmtiles' [--then ...]
  python3 -m ingest.builds done roads-build --note 'built by hand'   # covers what's marked now
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone

NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}")        # as ops.build_run's and ops.build_pending's checks
MARKED_BY_MAX = 120
REASON_MAX = 500
SERVE_ENV = "TVT_INGEST_SERVE"                      # set by `ingest serve` (ingest/__main__.py)
LOCK_KEY = "select hashtextextended('tvt build ' || %s, 0)"


class Busy(RuntimeError):
    """Another run of the build is going in this database."""


class CommandFailed(RuntimeError):
    """A build's command exited non-zero."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class Stopped(BaseException):
    """A build stopped by a signal (heavy's deadline sends SIGTERM). A BaseException, so a
    build's own `except Exception` doesn't swallow it."""


def check_name(build):
    if not isinstance(build, str) or not NAME.fullmatch(build):
        raise ValueError(f"a build's name is 1-64 lower-case letters, digits, '.', '_' or '-', "
                         f"starting with a letter: {build!r}")


def _marked_by(by):
    if not isinstance(by, str) or not by.strip() or len(by) > MARKED_BY_MAX:
        raise ValueError(f"marked_by names the source or command that marks (1-{MARKED_BY_MAX} characters): {by!r}")


def _reason(reason):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("a mark needs a reason (what changed)")
    return reason.strip()[:REASON_MAX]


def mark(conn, build, *, by, reason):
    """Mark build out of date because of `by` (a source, a command, 'by hand: <who>'). Doesn't
    commit: call it in the transaction that writes the data the build should take in."""
    check_name(build)
    _marked_by(by)
    reason = _reason(reason)
    conn.execute(
        """insert into ops.build_pending (build, marked_by, reason) values (%s, %s, %s)
           on conflict (build, marked_by) do update
             set marks = ops.build_pending.marks + 1,
                 first_at = least(ops.build_pending.first_at, excluded.first_at),
                 last_at = greatest(ops.build_pending.last_at, excluded.last_at),
                 reason = excluded.reason""",
        (build, by, reason))


def in_serve():
    return bool(os.environ.get(SERVE_ENV))


def start(conn, build):
    """Log the start of a run of build, noting the marks pending now (the ones it covers), and
    commit. Returns the run's id. Refuses inside `ingest serve`."""
    check_name(build)
    if in_serve():
        raise RuntimeError(f"{build}: builds never run inside `ingest serve` (plan §0 item 27): mark it "
                           "with builds.mark() and run it by hand")
    run_id = conn.execute(
        """insert into ops.build_run (build, covers)
           select %s, coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'marks', p.marks) order by p.id), '[]')
           from ops.build_pending p where p.build = %s
           returning id""",
        (build, build)).fetchone()[0]
    conn.commit()
    return run_id


def finish(conn, run_id, *, ok, note=None, error=None, then=()):
    """Log the end of run run_id and commit. If it succeeded: clear the marks it covers (a mark
    counted up since it started stays, dated no earlier than the run's start), and mark the
    builds in `then` (marked by this build). Uncommitted work on conn commits with it. Returns
    the number of marks cleared."""
    for b in then:
        check_name(b)
    row = conn.execute("select build, started_at, finished_at from ops.build_run where id = %s",
                       (run_id,)).fetchone()
    if row is None:
        raise ValueError(f"no build run {run_id}")
    build, started_at, finished_at = row
    if finished_at is not None:
        raise ValueError(f"build run {run_id} ({build}) has already finished")
    cleared = 0
    if ok:
        covered = """select (c->>'id')::bigint as id, (c->>'marks')::int as marks
                     from ops.build_run r, jsonb_array_elements(r.covers) c where r.id = %s"""
        cleared = conn.execute(
            f"""delete from ops.build_pending p using ({covered}) c
                where p.build = %s and p.id = c.id and p.marks <= c.marks""",
            (run_id, build)).rowcount
        conn.execute(
            f"""update ops.build_pending p set first_at = least(greatest(p.first_at, %s), p.last_at)
                from ({covered}) c where p.build = %s and p.id = c.id""",
            (started_at, run_id, build))
        for b in then:
            mark(conn, b, by=build, reason=f"{build} finished (run {run_id})")
    conn.execute(
        """update ops.build_run set finished_at = greatest(now(), started_at), ok = %s, note = %s, error = %s
           where id = %s""",
        (bool(ok), note, None if error is None else str(error)[:1000], run_id))
    conn.commit()
    return cleared


class Run:
    """A build run, as a context manager (like db.Fetch for a fetch). Set run.note as the build
    goes. On success its marks clear with its data, in one commit; on an exception (or SIGTERM)
    the build's uncommitted work is rolled back and the error logged. Only one run of a build
    goes at a time in a database (a session advisory lock, held until the run ends)."""

    def __init__(self, conn, build, then=(), note=None):
        check_name(build)
        for b in then:
            check_name(b)
        self.conn, self.build, self.then, self.note = conn, build, tuple(then), note
        self.id = None
        self.cleared = 0
        self._key = None
        self._old_term = None

    def __enter__(self):
        if in_serve():
            raise RuntimeError(f"{self.build}: builds never run inside `ingest serve` (plan §0 item 27): "
                               "mark it with builds.mark() and run it by hand")
        key = self.conn.execute(LOCK_KEY, (self.build,)).fetchone()[0]
        locked = self.conn.execute("select pg_try_advisory_lock(%s)", (key,)).fetchone()[0]
        self.conn.commit()
        if not locked:
            raise Busy(f"{self.build} is already running in this database")
        self._key = key
        try:
            self.id = start(self.conn, self.build)
        except BaseException:
            self._unlock()
            raise
        if threading.current_thread() is threading.main_thread() \
                and signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
            def stop(signum, _frame):
                raise Stopped(signal.Signals(signum).name)
            self._old_term = signal.signal(signal.SIGTERM, stop)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._old_term is not None:
                signal.signal(signal.SIGTERM, self._old_term)
                self._old_term = None
            if exc_type is None:
                try:
                    self.cleared = finish(self.conn, self.id, ok=True, note=self.note, then=self.then)
                except Exception as err:          # the build's own commit failed: log that, then raise it
                    self._failed(type(err), err)
                    raise
            else:
                self._failed(exc_type, exc)
        finally:
            self._unlock()
        return False

    def _failed(self, exc_type, exc):
        what = "stopped" if issubclass(exc_type, (Stopped, KeyboardInterrupt)) else exc_type.__name__
        try:
            self.conn.rollback()
            finish(self.conn, self.id, ok=False, note=self.note, error=f"{what}: {exc}")
        except Exception as err:
            print(f"{self.build}: run {self.id} couldn't be logged as failed ({err})", file=sys.stderr)

    def _unlock(self):
        if self._key is not None:
            try:
                self.conn.execute("select pg_advisory_unlock(%s)", (self._key,))
                self.conn.commit()
            except Exception:
                pass          # the lock goes with the connection
            self._key = None


def done(conn, build, note, then=()):
    """Log a build that ran some other way (by hand) as a run that just succeeded: it clears
    the marks pending now. Returns the number cleared."""
    with Run(conn, build, then=then, note=note) as run:
        pass
    return run.cleared


def status(conn):
    """The rows of ops.build_status, as dicts, pending and running first."""
    cur = conn.execute(
        """select * from ops.build_status
           order by case state when 'running' then 0 when 'pending' then 1 when 'failed' then 2 else 3 end,
                    pending_since nulls last, build""")
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _ago(t, now):
    if t is None:
        return "never"
    s = (now - t).total_seconds()
    if s < 90:
        return f"{s:.0f} s ago"
    if s < 90 * 60:
        return f"{s / 60:.0f} min ago"
    if s < 36 * 3600:
        return f"{s / 3600:.0f} h ago"
    return f"{s / 86400:.0f} d ago"


def describe(row, now=None):
    """One line about a build_status row."""
    now = now or datetime.now(timezone.utc)
    parts = [f"{row['build']:24} {row['state']:8}"]
    if row["state"] == "running":
        parts.append(f"started {_ago(row['last_run_at'], now)}")
    if row["pending_since"] is not None:
        by = "; ".join(row["pending_by"] or [])
        parts.append(f"marked since {_ago(row['pending_since'], now)} ({by}), newest: {row['pending_reason']}")
    if row["last_error"]:
        parts.append(f"last run failed: {row['last_error'][:200]}")
    parts.append(f"last built {_ago(row['last_ok_at'], now)}")
    return "  ".join(parts[:1] + ["; ".join(parts[1:])])


def run_command(conn, build, command, then=(), note=None):
    """Run command (a list) as a run of build; its exit status decides ok. Returns that status.
    SIGTERM and SIGINT are passed on to the command, and the run is logged as stopped."""
    with Run(conn, build, then=then, note=note) as run:
        proc = subprocess.Popen(command)
        try:
            code = proc.wait()
        except BaseException:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise
        if code != 0:
            shown = " ".join(command[:3]) + (" ..." if len(command) > 3 else "")
            raise CommandFailed(f"{shown} exited {code}", code)
        if run.note is None:
            run.note = " ".join(command)[:300]
    return code


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    command = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="python3 -m ingest.builds", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="each build: state, pending marks, age (the default)")
    m = sub.add_parser("mark", help="mark a build out of date")
    m.add_argument("build")
    m.add_argument("--by", required=True, help="the source or command that marks it, or 'by hand: <who>'")
    m.add_argument("--reason", required=True, help="what changed")
    r = sub.add_parser("run", help="run a command as a build: BUILD [--then B ...] -- COMMAND ...")
    r.add_argument("build")
    r.add_argument("--then", nargs="+", default=[], help="builds to mark once it succeeds")
    r.add_argument("--note")
    s = sub.add_parser("start", help="log a build's start (for a step that can't reach the database); prints its id")
    s.add_argument("build")
    f = sub.add_parser("finish", help="log the end of a run started with `start`")
    f.add_argument("run_id", type=int)
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--ok", action="store_true")
    g.add_argument("--failed", metavar="ERROR")
    f.add_argument("--note")
    f.add_argument("--then", nargs="+", default=[])
    d = sub.add_parser("done", help="log a build done by hand: clears what's marked now")
    d.add_argument("build")
    d.add_argument("--note", required=True)
    d.add_argument("--then", nargs="+", default=[])
    args = ap.parse_args(argv)
    if args.cmd == "run" and not command:
        ap.error("run needs the command after --")
    if args.cmd != "run" and command:
        ap.error("only run takes a command after --")

    from . import db
    with db.connect() as conn:
        if args.cmd in (None, "list"):
            now = datetime.now(timezone.utc)
            rows = status(conn)
            for row in rows:
                print(describe(row, now))
            if not rows:
                print("no builds have run or been marked")
        elif args.cmd == "mark":
            mark(conn, args.build, by=args.by, reason=args.reason)
            conn.commit()
            print(f"{args.build}: marked by {args.by}")
        elif args.cmd == "run":
            try:
                return run_command(conn, args.build, command, then=args.then, note=args.note)
            except CommandFailed as err:
                print(f"{args.build}: {err}; logged as failed", file=sys.stderr)
                return err.code if 0 < err.code < 256 else 1
            except RuntimeError as err:          # refused: already running, or inside ingest serve
                print(f"{args.build}: {err}", file=sys.stderr)
                return 75
        elif args.cmd == "start":
            print(start(conn, args.build))
        elif args.cmd == "finish":
            n = finish(conn, args.run_id, ok=args.ok, note=args.note, error=args.failed, then=args.then)
            print(f"run {args.run_id}: {'ok' if args.ok else 'failed'}" + (f", {n} mark(s) cleared" if args.ok else ""))
        elif args.cmd == "done":
            n = done(conn, args.build, args.note, then=args.then)
            print(f"{args.build}: logged as built; {n} mark(s) cleared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
