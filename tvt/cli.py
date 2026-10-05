"""Command line: python3 -m tvt <command>

  sources                 list sources, intervals and last fetch result
  ingest [names|all]      fetch sources once (default: all)
  run [--only a,b]        keep fetching each source on its own interval
  build                   aggregate into site/data/*.geojson for the map
  serve [--port 8000]     serve site/ locally (open http://localhost:8000)
  status                  row counts per table and source
"""

import argparse
import functools
import http.server
import os
import sys
import time
import traceback

from . import DB_PATH, SITE_DIR
from .store import Store, now_iso
from .sources import SOURCES


def ingest_one(store, src):
    started, t0 = now_iso(), time.time()
    try:
        n = src.run(store)
        store.log_fetch(src.name, started, True, n, None, time.time() - t0)
        print(f"[{src.name}] {n} records ({time.time() - t0:.1f}s)")
        return True
    except Exception as err:
        msg = f"{type(err).__name__}: {err}"
        store.log_fetch(src.name, started, False, 0, msg[:500], time.time() - t0)
        print(f"[{src.name}] FAILED {msg}", file=sys.stderr)
        if os.environ.get("TVT_DEBUG"):
            traceback.print_exc()
        return False


def pick(names):
    if not names or names == ["all"]:
        return list(SOURCES.values())
    unknown = [n for n in names if n not in SOURCES]
    if unknown:
        sys.exit(f"unknown source(s): {', '.join(unknown)}; see `python3 -m tvt sources`")
    return [SOURCES[n] for n in names]


def cmd_sources(store, args):
    for s in SOURCES.values():
        last = store.last_fetch(s.name)
        state = "never fetched" if not last else (
            f"last {last[0]} {'ok' if last[1] else 'FAILED'} ({last[2]} records)")
        print(f"{s.name:20} every {s.interval_s:>7}s  {s.description}\n{'':20} {state}")


def cmd_ingest(store, args):
    ok = all([ingest_one(store, s) for s in pick(args.names)])
    sys.exit(0 if ok else 1)


def cmd_run(store, args):
    chosen = pick(args.only.split(",") if args.only else [])
    due = {s.name: 0.0 for s in chosen}
    print(f"running {len(chosen)} sources; Ctrl+C to stop")
    try:
        while True:
            now = time.time()
            for s in chosen:
                if now >= due[s.name]:
                    ok = ingest_one(store, s)
                    # back off on failure, but retry sooner than a long interval
                    due[s.name] = time.time() + (s.interval_s if ok else min(s.interval_s, 600))
            time.sleep(max(1.0, min(due.values()) - time.time()))
    except KeyboardInterrupt:
        print("stopped")


def cmd_build(store, args):
    from .aggregate import build
    build(store, os.path.join(SITE_DIR, "data"))


def cmd_serve(store, args):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=SITE_DIR)
    print(f"serving {SITE_DIR} at http://localhost:{args.port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()


def cmd_status(store, args):
    q = store.db.execute
    print("features:")
    for row in q("SELECT source, kind, COUNT(*), MAX(last_seen) FROM features GROUP BY 1, 2"):
        print("  {:20} {:16} {:>8}  last seen {}".format(*row))
    print("events (active / total):")
    for row in q("SELECT source, kind, SUM(active), COUNT(*) FROM events GROUP BY 1, 2"):
        print("  {:20} {:16} {:>5} / {}".format(*row))
    print("observations:")
    for row in q("SELECT source, metric, COUNT(*), MIN(ts), MAX(ts) FROM observations GROUP BY 1, 2"):
        print("  {:20} {:16} {:>8}  {} .. {}".format(*row))
    n, first, last, veh = q("SELECT COUNT(*), MIN(ts), MAX(ts), COUNT(DISTINCT vehicle) "
                            "FROM vehicle_positions").fetchone()
    print(f"vehicle positions: {n} from {veh} vehicles"
          + (f", {time.strftime('%Y-%m-%d %H:%M', time.gmtime(first))} .. "
             f"{time.strftime('%Y-%m-%d %H:%M', time.gmtime(last))} UTC" if n else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m tvt", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB_PATH)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources")
    p = sub.add_parser("ingest")
    p.add_argument("names", nargs="*")
    p = sub.add_parser("run")
    p.add_argument("--only")
    sub.add_parser("build")
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8000)
    sub.add_parser("status")
    args = ap.parse_args(argv)
    store = Store(args.db)
    try:
        globals()[f"cmd_{args.cmd}"](store, args)
    finally:
        store.close()
