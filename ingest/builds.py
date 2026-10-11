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
it saw them when it started). A run that fails clears nothing; its error is logged, and the
build reads 'failed' in ops.build_status until a run succeeds, marked or not. Only one Run of a
build goes at a time in a database (an advisory lock; `start` and `finish`, split across
processes, can't hold it). A run stopped by SIGTERM (heavy's deadline) is logged as stopped, the
query in flight on its own connection is cancelled (psycopg does that on SystemExit), and the
process exits 143. A run killed outright (SIGKILL, the OOM killer) can't log anything, but it
no longer holds the lock, so ops.build_status reads it as failed, and the build's next Run
closes its row.

A build's name is the command that runs it (`roads-build`), or for a worker step its job
(`landscape-bake`): lower-case letters, digits, '.', '_' and '-'. `marked_by` names the source
or command that marked it, or 'by hand: <who>'.

A command logs its run one way or the other, never both. A command that uses Run (the plugin's
README says so) is run plainly. `run` is for one that doesn't log itself: it runs the command as
a run of the build, and a Run of the same build inside it refuses (TVT_BUILD_RUN says why). When
`run` is stopped, it stops its command (SIGINT first, so a Python command's psycopg cancels its
query; then SIGTERM; then SIGKILL; 35 s at most, inside heavy's 60 s grace), and when the command
fails or is stopped it ends any database session the command left: the command's sessions carry
the run's tag (PGAPPNAME=tvt-build-<run id>), and a query goes on on the server after its client
dies. A worker step can't reach the database, so its run is logged around it (`start`, `finish`).

  python3 -m ingest.builds                       # each build: state, pending marks, age
  python3 -m ingest.builds mark roads-build --by 'by hand: lead' --reason 'ACHD widths fixed'
  python3 -m ingest.builds run segment-match -- python3 -m ingest segment-match
  python3 -m ingest.builds start landscape-bake   # prints the run's id
  python3 -m ingest.builds finish 42 --ok --note 'landscape-3fa9c1.pmtiles' [--then ...]
  python3 -m ingest.builds done roads-build --note 'built by hand'   # covers what's marked now
"""

import argparse
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
RUN_ENV = "TVT_BUILD_RUN"                           # set by run_command for its command: "<build> <run id>"
LOCK_KEY = "select hashtextextended('tvt build ' || %s, 0)"   # ops.build_status reads the same key in pg_locks
# What ops.build_status says of a run that ended without logging its end, and what the build's
# next Run writes in its row.
KILLED = "ended without logging its end (killed, or its connection was lost)"
# How run_command stops its command: each signal, then how long to wait for it (s). 35 s in all,
# so the run is logged as stopped well inside heavy's grace (GRACE_S, 60 s: then SIGKILL, and
# `docker stop -t 60` for a container).
STOP_STEPS = ((signal.SIGINT, 20.0), (signal.SIGTERM, 10.0), (signal.SIGKILL, 5.0))
# A run's default note and a failed command's message show at most the command's first words,
# stopping at one that could carry a secret (a URL, key=value, user@host, a password option).
_PLAIN = re.compile(r"[A-Za-z0-9_./:,+-]+")
_SECRETISH = re.compile(r"(?i)pass|pwd|key|token|secret|auth|cred|sig|://")
# The text a run or a mark stores (its note, error or reason) loses the passwords in URLs and the
# values of key=, token=, password= and the like, as deploy/bin/status shows them: the tables go
# into dumps and every scratch copy.
_URL_PASSWORD = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")
_KEY_VALUE = re.compile(r"(?i)\b(\w*(?:key|token|secret|passw(?:or)?d|pwd|sig))=([^&;,\s\"']+)")


def redact(text):
    """text without passwords in URLs or the values of key=..., token=..., password=... (None stays None)."""
    if text is None:
        return None
    return _KEY_VALUE.sub(r"\1=***", _URL_PASSWORD.sub(r"\1***@", str(text)))


class Busy(RuntimeError):
    """Another run of the build is going in this database."""


class CommandFailed(RuntimeError):
    """A build's command exited non-zero."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class Stopped(SystemExit):
    """A build stopped by a signal (heavy's deadline sends SIGTERM). A SystemExit (status 128 +
    the signal), so psycopg cancels a query in flight and a build's own `except Exception`
    doesn't swallow it."""

    def __init__(self, signum):
        super().__init__(128 + signum)
        self.signame = signal.Signals(signum).name

    def __str__(self):
        return self.signame


def check_name(build):
    if not isinstance(build, str) or not NAME.fullmatch(build):
        raise ValueError(f"a build's name is 1-64 lower-case letters, digits, '.', '_' or '-', "
                         f"starting with a letter: {build!r}")


def _check_then(build, then):
    for b in then:
        check_name(b)
        if b == build:
            raise ValueError(f"{build} can't mark itself when it finishes: it would never be built")


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
    reason = redact(_reason(reason))
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


def _may_start(build):
    """Refuse a run inside `ingest serve`, or inside `python3 -m ingest.builds run` of the same build."""
    if in_serve():
        raise RuntimeError(f"{build}: builds never run inside `ingest serve` (plan §0 item 27): mark it "
                           "with builds.mark() and run it by hand")
    outer = os.environ.get(RUN_ENV, "").split()
    if outer and outer[0] == build:
        raise RuntimeError(
            f"{build} is already running as run {' '.join(outer[1:2]) or '?'} under `python3 -m ingest.builds "
            f"run {build}`, which logs it. A command that logs its own run (builds.Run) is run plainly, "
            "without the wrapper")


def start(conn, build, *, locked=False):
    """Log the start of a run of build, noting the marks pending now (the ones it covers), and
    commit. Returns the run's id. Refuses inside `ingest serve`, or inside `run` of the same
    build. locked: the caller holds the build's advisory lock (Run does), so the run's row says
    so, and any older unfinished run that held it is dead: its row is closed as KILLED."""
    check_name(build)
    _may_start(build)
    if locked:
        conn.execute(
            """update ops.build_run set finished_at = greatest(clock_timestamp(), started_at), ok = false,
                 error = %s
               where build = %s and finished_at is null and locked""",
            (KILLED, build))
    run_id = conn.execute(
        """insert into ops.build_run (build, started_at, covers, locked)
           select %s, clock_timestamp(),
                  coalesce(jsonb_agg(jsonb_build_object('id', p.id, 'marks', p.marks) order by p.id), '[]'), %s
           from ops.build_pending p where p.build = %s
           returning id""",
        (build, bool(locked), build)).fetchone()[0]
    conn.commit()
    return run_id


def finish(conn, run_id, *, ok, note=None, error=None, then=()):
    """Log the end of run run_id and commit. If it succeeded: clear the marks it covers (a mark
    counted up since it started stays, dated no earlier than the run's start), and mark the
    builds in `then` (marked by this build). Uncommitted work on conn commits with it. Returns
    the number of marks cleared."""
    row = conn.execute("select build, started_at, finished_at from ops.build_run where id = %s for update",
                       (run_id,)).fetchone()
    if row is None:
        raise ValueError(f"no build run {run_id}")
    build, started_at, finished_at = row
    _check_then(build, then)
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
        """update ops.build_run set finished_at = greatest(clock_timestamp(), started_at), ok = %s, note = %s,
             error = %s
           where id = %s""",
        (bool(ok), redact(note), None if error is None else redact(error)[:1000], run_id))
    conn.commit()
    return cleared


class Run:
    """A build run, as a context manager (like db.Fetch for a fetch). Set run.note as the build
    goes. On success its marks clear with its data, in one commit; on an exception (or SIGTERM)
    the build's uncommitted work is rolled back and the error logged. Only one run of a build
    goes at a time in a database (a session advisory lock, held until the run ends; while its
    row is unfinished and nothing holds the lock, ops.build_status reads the run as killed)."""

    def __init__(self, conn, build, then=(), note=None):
        check_name(build)
        _check_then(build, then)
        self.conn, self.build, self.then, self.note = conn, build, tuple(then), note
        self.id = None
        self.cleared = 0
        self._key = None
        self._old_term = None

    def __enter__(self):
        _may_start(self.build)
        key = self.conn.execute(LOCK_KEY, (self.build,)).fetchone()[0]
        locked = self.conn.execute("select pg_try_advisory_lock(%s)", (key,)).fetchone()[0]
        self.conn.commit()
        if not locked:
            raise Busy(f"{self.build} is already running in this database")
        self._key = key
        try:
            self.id = start(self.conn, self.build, locked=True)
        except BaseException:
            self._unlock()
            raise
        if threading.current_thread() is threading.main_thread() \
                and signal.getsignal(signal.SIGTERM) == signal.SIG_DFL:
            def stop(signum, _frame):
                # Once is enough: a second SIGTERM (docker stop and the docker CLI's own, say)
                # mustn't cut the run's logging short. __exit__ puts the old handler back.
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                raise Stopped(signum)
            self._old_term = signal.signal(signal.SIGTERM, stop)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                try:
                    self.cleared = finish(self.conn, self.id, ok=True, note=self.note, then=self.then)
                except BaseException as err:      # the build's own commit failed (or it was stopped then)
                    self._failed(type(err), err)
                    raise
            else:
                self._failed(exc_type, exc)
        finally:
            self._unlock()
            if self._old_term is not None:
                signal.signal(signal.SIGTERM, self._old_term)
                self._old_term = None
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
    """The rows of ops.build_status, as dicts: failed, running, pending (oldest mark first), built."""
    cur = conn.execute(
        """select * from ops.build_status
           order by case state when 'failed' then 0 when 'running' then 1 when 'pending' then 2 else 3 end,
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


def shown(command, words=4):
    """The command's first words (at most `words`), up to the first that could carry a secret."""
    out = []
    for w in command[:words]:
        if not _PLAIN.fullmatch(w) or _SECRETISH.search(w):
            break
        out.append(w)
    return " ".join(out) + (" ..." if len(out) < len(command) else "") if out else "the command"


def _stop(proc):
    """Stop the command (STOP_STEPS): SIGINT first, as a Python command with psycopg cancels its
    query in flight on KeyboardInterrupt, then SIGTERM, then SIGKILL. Another Ctrl-C meanwhile
    is ignored, so the stop and the run's log go through."""
    old_int = None
    if threading.current_thread() is threading.main_thread() and signal.getsignal(signal.SIGINT) is not None:
        old_int = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        for sig, wait in STOP_STEPS:
            if proc.poll() is not None:
                return
            try:
                proc.send_signal(sig)
            except OSError:
                pass
            try:
                proc.wait(timeout=wait)
                return
            except subprocess.TimeoutExpired:
                continue
    finally:
        if old_int is not None:
            signal.signal(signal.SIGINT, old_int)


def _end_sessions(conn, build, tag):
    """End the database sessions a failed or stopped command left (application_name `tag`, this
    role's): a query goes on on the server after its client is gone, until it finishes or runs
    into statement_timeout. Returns how many were ended."""
    try:
        ended = conn.execute(
            """select count(*) filter (where pg_terminate_backend(pid, 5000))::int from pg_stat_activity
               where application_name = %s and usename = current_user and pid <> pg_backend_pid()""",
            (tag,)).fetchone()[0]
    except Exception as err:
        print(f"{build}: couldn't look for database sessions the command left ({err})", file=sys.stderr)
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    if ended:
        print(f"{build}: ended {ended} database session(s) the command left", file=sys.stderr)
    return ended


def run_command(conn, build, command, then=(), note=None):
    """Run command (a list) as a run of build; its exit status decides ok. Returns that status.

    The command gets TVT_BUILD_RUN, so a Run of the same build inside it refuses (a command that
    logs its own run is run plainly), and PGAPPNAME=tvt-build-<run id>, so its database sessions
    carry the run's tag. If the run is stopped (SIGTERM, Ctrl-C), the command is stopped too
    (_stop), and the run is logged as stopped. If the command fails or is stopped, the sessions
    it left are ended. The note defaults to the command's first words (shown)."""
    with Run(conn, build, then=then, note=note) as run:
        tag = f"tvt-build-{run.id}"
        env = {**os.environ, RUN_ENV: f"{build} {run.id}", "PGAPPNAME": tag}
        proc = subprocess.Popen(command, env=env)
        try:
            code = proc.wait()
        except BaseException:
            _stop(proc)
            _end_sessions(conn, build, tag)
            raise
        if code != 0:
            _end_sessions(conn, build, tag)
            raise CommandFailed(f"{shown(command)} exited {code}", code)
        if run.note is None:
            run.note = shown(command)
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
    r = sub.add_parser("run", help="run a command that doesn't log its own run as a build: "
                                   "BUILD [--then B ...] -- COMMAND ...")
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
            except OSError as err:               # the command couldn't start (logged as failed)
                print(f"{args.build}: {err}", file=sys.stderr)
                return 127
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
