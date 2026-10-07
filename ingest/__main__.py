"""python3 -m ingest sources | run NAME... | run all | serve | stream NAME | backfill NAME PATH | match-routes |
match-intersections | rollup"""

import argparse
import os
import sys
import time
import traceback
from datetime import date, datetime

from . import camera_video, db
from .sources import SOURCES, STREAMS


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


def main():
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
    mr = sub.add_parser("match-routes", help="put unlabeled bus trips on routes by their path (the transit stream does this)")
    mr.add_argument("--hours", type=int, default=24, help="how far back to look (default 24)")
    mi = sub.add_parser("match-intersections",
                        help="rebuild core.intersection from the signal sources (the 'intersections' source does this daily)")
    mi.add_argument("--dry-run", action="store_true", help="build and report, then roll back")
    ru = sub.add_parser("rollup", help="roll camera JPEGs into daily videos (the frame stream does this nightly)")
    ru.add_argument("--day", type=date.fromisoformat, help="local day, YYYY-MM-DD (default: every finished day not yet done)")
    ru.add_argument("--camera", nargs="+", help="511 image IDs (default: all with frames that day)")
    ru.add_argument("--force", action="store_true", help="redo existing or failed videos")
    args = ap.parse_args()

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
    if args.cmd == "match-routes":
        from . import transit_match
        with db.connect() as conn:
            stats = transit_match.run(conn, args.hours)
        print("match-routes: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
        return
    if args.cmd == "match-intersections":
        from plugins.intersections.ingest import intersections
        with db.connect() as conn:
            if args.dry_run:
                stats, details = intersections.build(conn, db.now())
                intersections.report(conn, stats, details)
                conn.rollback()
                print("\n(dry run: nothing written)", flush=True)
            else:
                db.ensure_source(conn, intersections.SOURCE)
                with db.Fetch(conn, intersections.SOURCE["name"]) as f:
                    stats, details = intersections.build(conn, f.started_at)
                    f.records = stats["intersections"]
                intersections.report(conn, stats, details)       # after the commit: printing can't undo the build
        return
    if args.cmd == "rollup":
        root = os.environ.get("TVT_ARCHIVE") or sys.exit("set TVT_ARCHIVE")
        today = datetime.now(camera_video.TZ).date()
        if args.day:
            cams = args.camera or sorted(os.listdir(os.path.join(root, "cameras", "jpeg")))
            items = [(cam, args.day) for cam in cams]
        else:
            items = [(c, d) for c, d in camera_video.pending(root, today) if not args.camera or c in args.camera]
        done, failed = camera_video.rollup(root, items, force=args.force)
        print(f"rollup: {done} videos, {failed} failed", flush=True)
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
