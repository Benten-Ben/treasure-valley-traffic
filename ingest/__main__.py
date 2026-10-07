"""python3 -m ingest sources | run NAME... | run all | serve | stream NAME | backfill NAME PATH | COMMAND ...

COMMAND is a plugin's own subcommand, registered in its plugin.json (e.g.
match-intersections, rollup, osm-load); `python3 -m ingest -h` lists them.
"""

import argparse
import sys
import time
import traceback

from . import db
from .sources import COMMANDS, SOURCES, STREAMS, command

BUILTINS = ("sources", "run", "serve", "stream", "backfill")


def due(conn, name, schedule, retry_after="1 hour"):
    """Due when the last good fetch is older than the schedule. After a failure,
    wait at least min(schedule, retry_after) before trying again (a source's
    SOURCE["retry_after"]; 1 hour unless it says otherwise)."""
    return conn.execute(
        """select (max(started_at) filter (where ok) is null
                   or max(started_at) filter (where ok) + %s::interval <= now())
              and (max(started_at) is null
                   or max(started_at) + least(%s::interval, %s::interval) <= now())
           from ops.fetch where source = %s""",
        (schedule, schedule, retry_after, name)).fetchone()[0]


def run_one(conn, name):
    stats = SOURCES[name].run(conn)
    conn.commit()
    print(f"{name}: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)


def serve(check_every_s):
    """Run scheduled sources when they're due. One-off and by-request sources
    have no schedule (the database refuses one), so they never run here."""
    print(f"ingest serve: checking every {check_every_s} s", flush=True)
    while True:
        try:
            with db.connect() as conn:
                for name, m in SOURCES.items():
                    s = m.SOURCE
                    if not s.get("schedule") or s["access"] in ("one_off", "request"):
                        continue
                    db.ensure_source(conn, s)
                    conn.commit()
                    if due(conn, name, s["schedule"], s.get("retry_after", "1 hour")):
                        try:
                            run_one(conn, name)
                        except Exception:
                            conn.rollback()
                            print(f"{name} failed (logged in ops.fetch):\n{traceback.format_exc()}", flush=True)
        except Exception:
            print(f"ingest serve: database unavailable:\n{traceback.format_exc()}", flush=True)
        time.sleep(check_every_s)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if clash := sorted(set(COMMANDS) & set(BUILTINS)):
        sys.exit(f"plugin command(s) {', '.join(clash)} clash with the built-in ones")
    if argv and argv[0] in COMMANDS:
        sys.exit(command(argv[0])(argv[1:]))

    ap = argparse.ArgumentParser(prog="python3 -m ingest", description="Run ingestors (docs/12).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources", help="list sources")
    run = sub.add_parser("run", help="run sources once")
    run.add_argument("names", nargs="+", help="source names, or 'all'")
    srv = sub.add_parser("serve", help="keep running scheduled sources when they're due")
    srv.add_argument("--check-every", type=int, default=300, help="seconds between checks")
    st = sub.add_parser("stream", help="run a streaming source continuously")
    st.add_argument("name", choices=sorted(STREAMS))
    st.add_argument("--every", type=int, help="seconds between polls (default: the stream's own)")
    bf = sub.add_parser("backfill", help="load a streaming source's raw archive into the database")
    bf.add_argument("name", choices=sorted(n for n, m in STREAMS.items() if hasattr(m, "backfill")))
    bf.add_argument("path", help="archive folder, e.g. $TVT_ARCHIVE/vrt-gtfs-rt")
    for name, (plugin, entry) in COMMANDS.items():
        sub.add_parser(name, help=f"{entry['help']} ({plugin.name})", add_help=False)
    args = ap.parse_args(argv)

    if args.cmd == "sources":
        for name, m in SOURCES.items():
            s = m.SOURCE
            print(f"{name:24} {s['access']:8} {s.get('schedule') or '-':8} {s['title']}")
        for name, m in STREAMS.items():
            s = m.SOURCE
            print(f"{name:24} {s['access']:8} {'stream':8} {s['title']}")
        return
    if args.cmd == "stream":
        if args.every:
            STREAMS[args.name].stream(args.every)
        else:
            STREAMS[args.name].stream()
        return
    if args.cmd == "backfill":
        with db.connect() as conn:
            stats = STREAMS[args.name].backfill(conn, args.path)
        print(f"{args.name} backfill: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
        return
    if args.cmd == "serve":
        serve(args.check_every)
        return

    names = list(SOURCES) if args.names == ["all"] else args.names
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        sys.exit(f"unknown source(s): {', '.join(unknown)}")
    with db.connect() as conn:
        for name in names:
            run_one(conn, name)


if __name__ == "__main__":
    main()
