"""python3 -m ingest sources | run NAME... | run all | serve"""

import argparse
import sys
import time
import traceback

from . import db
from .sources import SOURCES


def due(conn, name, schedule):
    """Due when the last good fetch is older than the schedule. After a failure,
    wait at least min(schedule, 1 hour) before trying again."""
    return conn.execute(
        """select (max(started_at) filter (where ok) is null
                   or max(started_at) filter (where ok) + %s::interval <= now())
              and (max(started_at) is null
                   or max(started_at) + least(%s::interval, interval '1 hour') <= now())
           from ops.fetch where source = %s""",
        (schedule, schedule, name)).fetchone()[0]


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
                    if due(conn, name, s["schedule"]):
                        try:
                            run_one(conn, name)
                        except Exception:
                            conn.rollback()
                            print(f"{name} failed (logged in ops.fetch):\n{traceback.format_exc()}", flush=True)
        except Exception:
            print(f"ingest serve: database unavailable:\n{traceback.format_exc()}", flush=True)
        time.sleep(check_every_s)


def main():
    ap = argparse.ArgumentParser(prog="python3 -m ingest", description="Run ingestors (docs/12).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources", help="list sources")
    run = sub.add_parser("run", help="run sources once")
    run.add_argument("names", nargs="+", help="source names, or 'all'")
    srv = sub.add_parser("serve", help="keep running scheduled sources when they're due")
    srv.add_argument("--check-every", type=int, default=300, help="seconds between checks")
    args = ap.parse_args()

    if args.cmd == "sources":
        for name, m in SOURCES.items():
            s = m.SOURCE
            print(f"{name:24} {s['access']:8} {s.get('schedule') or '-':8} {s['title']}")
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
