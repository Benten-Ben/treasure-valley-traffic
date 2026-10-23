"""The approved backfills of fire perimeters after the ground's photo: Aug-Dec 2025 (landscape sprint, decision 25:
owner, Oct 8, 2026) and Jul 25-31, 2025 (owner, Oct 22, 2026): `python3 -m ingest wfigs-backfill`.

The perimeter poller (nifc_wfigs_perimeters) started on Oct 7, 2026, and its first run read what had changed in
2026. A fire from the second half of 2025 is in raw.record only if its record changed in 2026, but the burn scars
(burn_scars.py) draw every fire after the ground's photo, last flown on Jul 24, 2025. The owner approved one small
read of the same service for Aug-Dec 2025, and later (Oct 22) one for Jul 25-31, 2025. Each is a read in two steps, so
that one read can be loaded into more than one database (the scratch copy now, production at deploy) without asking
NIFC twice. **The Aug-Dec read was made on Oct 11, 2026 at 12:02 UTC** and the Jul 25-31 read on Oct 23, 2026 at
03:57 UTC; both are kept on the server (plugins/hazards/README.md, "The 2025 backfill"); every database loads each
kept folder with `--load`, and `--fetch` refuses to read a window again (see WINDOWS).

1. `--fetch --one-off --out DIR --window FIRST..LAST`: one count, then one read of the all-years perimeter service (a few more by ID
   only if the answer is cut at the server's page size): every perimeter touching the ring whose fire was
   discovered in the window (Aug 1 - Dec 31, 2025 or Jul 25 - 31, 2025), Boise time (or, with no discovery time,
   whose polygon is from then),
   geometry at the poller's precision. Every request goes through ingest/http.py: robots.txt first
   (services3.arcgis.com answers 403, so no rules), our User-Agent, and at least 2 s between requests. Over CAP
   features it stops before reading them (the read is meant to be small). It writes DIR/<UTC time>/features.json
   (the features as the service sent them) and provenance.json (what was asked, where, when, by whom, under which
   approval, how many requests including robots.txt, what came back, and the file's sha256). It touches no
   database. It refuses a window whose read is already made (recorded in WINDOWS, or a provenance.json for it under
   DIR) unless --read-again, which needs the owner's OK for a second read.
2. `--load DIR/<UTC time>`: checks features.json against its provenance and the provenance's window against the
   approved windows (so a window added later never strands an earlier read), keeps the window's features (in case
   the server ignored the filter), parses them exactly as the poller does (nifc_wfigs_perimeters.parse), and stores
   each fire's perimeter as a nifc_wfigs_perimeters version in raw.record. A version already held is left as it
   is. The read is logged once per database as a fetch of the one-off source nifc_wfigs_perimeters_backfill, with
   the read's own times, status and robots result, and every version it adds points at that fetch
   (raw.record.first_fetch): that's the provenance in the database. Loading the same read again adds nothing.
   The versions it adds mark the burn-scars build (burn_scars.mark), which then runs by hand. No lifecycles
   (evt.event): these fires are long out, and the poller keeps a fire first seen already out in raw.record only.

The windows are the approvals', fixed here rather than options (WINDOWS). A fire discovered from Jul 25 to Jul 31,
2025 is after the photo but was outside the first window; the owner approved that week too (Oct 22, 2026, item 3 of
the end-of-wave-1 decisions), so it's a second window beside the first. Each window has its own one read, made with
`--fetch --window FIRST..LAST` (with two windows, --window is required), and each read loads on its own; the
Aug-Dec read still loads as it was made. The RANGE fire (Jul 31, about 27,000 acres) was already held through the
poller: the week's read adds its versions beside that one and leaves it as it is.

    python3 -m ingest wfigs-backfill --fetch --one-off --out DIR --window 2025-07-25..2025-07-31
    python3 -m ingest wfigs-backfill --load /srv/sources/nifc-wfigs-backfill/20261011T1202Z --dry-run
    python3 -m ingest wfigs-backfill --load /srv/sources/nifc-wfigs-backfill/20261011T1202Z

Standard library plus psycopg.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
from collections import namedtuple
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest import USER_AGENT, arcgis, db, http
from . import burn_scars, common
from .sources import nifc_wfigs_perimeters as perimeters

BOISE = ZoneInfo("America/Boise")
CAP = 400                         # the most features a read may bring
FEATURES, PROVENANCE = "features.json", "provenance.json"
APPROVAL = ("owner, Oct 8, 2026: landscape sprint decision 25 ('one small backfill read of the same fire service "
            "for Aug-Dec 2025'); go-ahead to build, Oct 10")
APPROVAL_JULY = ("owner, Oct 22, 2026: item 3 of the end-of-wave-1 decisions (docs/DECISIONS.md): 'one more "
                 "fire-perimeter read, for Jul 25-31, 2025'")

# The approved windows, Boise days, both included, each with its approval and, once made, when its one read was made
# (UTC). A read is checked against the window its own provenance records, so a window approved later is added here
# beside the others, never in place of one.
Window = namedtuple("Window", "first_day last_day approval read_at")
WINDOWS = [
    Window(date(2025, 8, 1), date(2025, 12, 31), APPROVAL, "2026-10-11T12:02:07Z"),
    Window(date(2025, 7, 25), date(2025, 7, 31), APPROVAL_JULY, "2026-10-23T03:57:51Z"),
]
AUG_DEC_2025 = WINDOWS[0]
JUL_25_31_2025 = WINDOWS[1]

SOURCE = {
    "name": "nifc_wfigs_perimeters_backfill",
    "title": "NIFC WFIGS interagency fire perimeters: the approved backfill reads (Jul 25-31 and Aug-Dec 2025)",
    "url": perimeters.LAYER,
    "access": "one_off",
    "license": perimeters.SOURCE["license"],
    "credit": perimeters.SOURCE["credit"],
    "notes": "One read each of the all-years perimeter service for fires discovered Aug 1 - Dec 31, 2025 and "
             "Jul 25 - 31, 2025 (Boise), approved by the owner (Aug-Dec: " + APPROVAL + "; Jul 25-31: " + APPROVAL_JULY
             + "). Their records are stored as nifc_wfigs_perimeters versions; each version a read adds points "
             "(first_fetch) at its own fetch row of this source. plugins/hazards/ingest/wfigs_backfill.py.",
}


# --- the window ------------------------------------------------------------------------------------

def window_name(window):
    return f"{window.first_day.isoformat()}..{window.last_day.isoformat()}"


def find_window(first_day, last_day):
    """The approved window with these days (ISO strings or dates), or None."""
    days = (str(first_day), str(last_day))
    return next((w for w in WINDOWS if (w.first_day.isoformat(), w.last_day.isoformat()) == days), None)


def bounds(window=AUG_DEC_2025):
    """The window as UTC datetimes: (start, end), the end excluded."""
    start = datetime.combine(window.first_day, datetime.min.time(), tzinfo=BOISE)
    end = datetime.combine(date.fromordinal(window.last_day.toordinal() + 1), datetime.min.time(), tzinfo=BOISE)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def where(window=AUG_DEC_2025):
    """The service filter: discovered in the window, or with no discovery time, a polygon from the window.
    Absolute UTC times (NIFC asks for no relative dates)."""
    start, end = (f"TIMESTAMP '{t:%Y-%m-%d %H:%M:%S}'" for t in bounds(window))
    return (f"(attr_FireDiscoveryDateTime >= {start} AND attr_FireDiscoveryDateTime < {end}) OR "
            f"(attr_FireDiscoveryDateTime IS NULL AND poly_PolygonDateTime >= {start} AND poly_PolygonDateTime < {end})")


def in_window(attrs, window=AUG_DEC_2025):
    """Whether a feature's attributes (or a parsed payload) fall in the window, as where() asks."""
    start, end = bounds(window)
    t = arcgis.esri_date(attrs.get("attr_FireDiscoveryDateTime"))
    if t is None:
        t = arcgis.esri_date(attrs.get("poly_PolygonDateTime"))
    return t is not None and start <= t < end


def reads_in(out_dir, window):
    """The read folders under out_dir whose provenance is for this window."""
    found = []
    for name in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
        path = os.path.join(out_dir, name, PROVENANCE)
        try:
            with open(path, encoding="utf-8") as f:
                w = json.load(f).get("window") or {}
        except (OSError, ValueError):
            continue
        if (w.get("first_day"), w.get("last_day")) == (window.first_day.isoformat(), window.last_day.isoformat()):
            found.append(os.path.dirname(path))
    return found


def count_url(window=AUG_DEC_2025):
    q = {"where": where(window), "returnCountOnly": "true", "f": "json",
         "geometry": ",".join(str(v) for v in common.RING), "geometryType": "esriGeometryEnvelope",
         "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"}
    return perimeters.LAYER + "/query?" + urllib.parse.urlencode(q)


# --- step 1: the read --------------------------------------------------------------------------------

def stamp(t):
    return t.astimezone(timezone.utc).strftime("%Y%m%dT%H%MZ")


def _robots_held(url):
    """Whether ingest/http.py holds robots.txt for url's host (it reads it once a process, before the first request)."""
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" in http._robots


def fetch(out_dir, get=None, sleep=None, now=None, cap=CAP, window=AUG_DEC_2025):
    """A window's one read. Writes out_dir/<UTC time>/{features.json, provenance.json}; returns that folder.
    (main() refuses a window already read; this doesn't check.)"""
    label = SOURCE["name"]
    calls = []

    def counted(url):
        calls.append(url)
        return (get or (lambda u: http.get(u, timeout=180)))(url)

    kw = {} if sleep is None else {"sleep": sleep}
    started = now or datetime.now(timezone.utc)
    robots_before = get is not None or _robots_held(perimeters.LAYER)
    _, _, decision, data = arcgis.get_with_retries(count_url(window), label, counted, parse=json.loads, **kw)
    if "error" in data or not isinstance(data.get("count"), int):
        raise RuntimeError(f"{label}: the count came back without a count: {str(data)[:200]}")
    if data["count"] > cap:
        raise RuntimeError(f"{label}: the service counts {data['count']} perimeters in the window, over the cap of "
                           f"{cap}; nothing read (the approval is for a small read)")
    features, nbytes, status, decision = common.query_layer(
        perimeters.LAYER, label, where=where(window), box=common.RING, geometry=True, precision=perimeters.PRECISION,
        page_by_id=True, get=counted, **kw)
    finished = datetime.now(timezone.utc) if now is None else now
    robots_requests = 0 if robots_before or not _robots_held(perimeters.LAYER) else 1
    if len(features) > cap:
        raise RuntimeError(f"{label}: {len(features)} features came back, over the cap of {cap}; nothing kept")
    folder = os.path.join(out_dir, stamp(started))
    os.makedirs(folder, exist_ok=False)
    body = json.dumps(features, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(folder, FEATURES), "wb") as f:
        f.write(body)
    start, end = bounds(window)
    provenance = {
        "what": f"NIFC WFIGS interagency fire perimeters: the backfill read of {window_name(window)} (wfigs_backfill.py)",
        "approval": window.approval,
        "service": perimeters.LAYER,
        "where": where(window),
        "window": {"first_day": window.first_day.isoformat(), "last_day": window.last_day.isoformat(),
                   "time_zone": "America/Boise", "utc": [common.iso(start), common.iso(end)]},
        "box": list(common.RING),
        "precision": perimeters.PRECISION,
        "user_agent": USER_AGENT,
        "robots": decision,
        "http_status": status,
        "requests": len(calls) + robots_requests,     # to the service's host, robots.txt included
        "robots_txt_requests": robots_requests,
        "started_at": common.iso(started),
        "finished_at": common.iso(finished),
        "count": data["count"],
        "features": len(features),
        "bytes_read": nbytes,
        "license": perimeters.SOURCE["license"],
        "credit": perimeters.SOURCE["credit"],
        "file": FEATURES,
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    with open(os.path.join(folder, PROVENANCE), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=2, sort_keys=True)
        f.write("\n")
    return folder, provenance


# --- step 2: the load -------------------------------------------------------------------------------

def read(folder):
    """(provenance, features, window) from a read's folder: the file checked against its sha256, and the read
    against the approved window its provenance names (its filter must be that window's)."""
    with open(os.path.join(folder, PROVENANCE), encoding="utf-8") as f:
        provenance = json.load(f)
    with open(os.path.join(folder, provenance.get("file") or FEATURES), "rb") as f:
        body = f.read()
    if hashlib.sha256(body).hexdigest() != provenance.get("sha256"):
        raise ValueError(f"{folder}: {FEATURES} doesn't match the sha256 in {PROVENANCE}")
    w = provenance.get("window") or {}
    window = find_window(w.get("first_day"), w.get("last_day"))
    if window is None:
        raise ValueError(f"{folder}: its window ({w.get('first_day')} to {w.get('last_day')}) isn't an approved one")
    if provenance.get("service") != perimeters.LAYER or provenance.get("where") != where(window):
        raise ValueError(f"{folder}: not this backfill's read (service or filter differ)")
    features = json.loads(body)
    if not isinstance(features, list):
        raise ValueError(f"{folder}: {FEATURES} isn't a list of features")
    return provenance, features, window


def prepare(features, window=AUG_DEC_2025):
    """The poller's parse of the window's features -> ({source_id: (payload, geometry)}, stats)."""
    kept = [f for f in features if in_window((f or {}).get("attributes") or {}, window)]
    parsed, duplicates = perimeters.parse(kept)
    return parsed, {"features": len(features), "outside the window": len(features) - len(kept),
                    "fires": len(parsed), "duplicates": duplicates}


def fetch_row(conn, provenance):
    """The read's ops.fetch row (made once per database), as a fetch of the one-off source. Returns its id."""
    db.ensure_source(conn, SOURCE)
    started = common.parse_time(provenance["started_at"])
    row = conn.execute("select id from ops.fetch where source = %s and started_at = %s and ok",
                       (SOURCE["name"], started)).fetchone()
    if row:
        return row[0], False
    return conn.execute(
        """insert into ops.fetch (source, started_at, finished_at, http_status, robots, ok, records, bytes)
           values (%s, %s, %s, %s, %s, true, %s, %s) returning id""",
        (SOURCE["name"], started, common.parse_time(provenance["finished_at"]), provenance.get("http_status"),
         provenance.get("robots"), provenance.get("features"), provenance.get("bytes_read"))).fetchone()[0], True


def store(conn, provenance, parsed, source=perimeters.SOURCE["name"], build=burn_scars.BUILD):
    """Add the read's versions to raw.record (as the poller's source); a version already held is left as it is.
    New versions mark the burn-scars build."""
    fetch_id, logged = fetch_row(conn, provenance)
    seen = common.parse_time(provenance["started_at"])
    new = 0
    for sid, (payload, geom) in sorted(parsed.items()):
        row = conn.execute(
            """insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen, first_fetch)
               values (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s)
               on conflict (source, source_id, version_hash) do nothing
               returning 1""",
            (source, sid, db.version_hash(payload), json.dumps(payload), json.dumps(geom), seen, seen,
             fetch_id)).fetchone()
        new += 1 if row else 0
    return {"fetch": fetch_id, "fetch logged": "now" if logged else "before", "record versions new": new,
            "already held": len(parsed) - new, **burn_scars.mark(conn, SOURCE["name"], new=new, name=build)}


def load(conn, folder, source=perimeters.SOURCE["name"], build=burn_scars.BUILD):
    provenance, features, window = read(folder)
    parsed, stats = prepare(features, window)
    stats = {"window": window_name(window), **stats}
    stats.update(store(conn, provenance, parsed, source, build))
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python3 -m ingest wfigs-backfill",
        description="The approved backfill reads of NIFC's fire perimeters (Aug-Dec 2025, made on Oct 11, 2026; "
                    "Jul 25-31, 2025), and their load into raw.record. A read already made is kept on the server: "
                    "load its folder (--load); don't read again.")
    step = ap.add_mutually_exclusive_group(required=True)
    step.add_argument("--fetch", action="store_true",
                      help="read the service once for an approved window not yet read (needs --one-off, --out and "
                           "--window; both approved reads are done)")
    step.add_argument("--load", metavar="DIR", help="load a read's folder (DIR/<UTC time>) into raw.record")
    ap.add_argument("--one-off", action="store_true",
                    help="confirm this is the one approved read, run by hand (required with --fetch)")
    ap.add_argument("--out", metavar="DIR", help="where --fetch writes its folder")
    ap.add_argument("--window", metavar="FIRST..LAST", help="with --fetch: the approved window to read "
                    f"(required while more than one is approved: {', '.join(window_name(w) for w in WINDOWS)})")
    ap.add_argument("--read-again", action="store_true",
                    help="with --fetch: read a window whose read is already made (only with the owner's OK)")
    ap.add_argument("--dry-run", action="store_true", help="with --load: check and report, then roll back")
    args = ap.parse_args(argv)
    if args.fetch:
        if args.dry_run:
            ap.error("--dry-run is for --load; --fetch has no dry run (it reads NIFC's service)")
        if not args.one_off:
            ap.error("--fetch reads NIFC's service: pass --one-off to confirm it's the one approved read")
        if not args.out:
            ap.error("--fetch needs --out DIR")
        if args.window:
            first, _, last = args.window.partition("..")
            window = find_window(first, last)
            if window is None:
                ap.error(f"--window {args.window} isn't an approved window")
        elif len(WINDOWS) == 1:
            window = WINDOWS[0]
        else:
            ap.error("--fetch needs --window: " + ", ".join(window_name(w) for w in WINDOWS))
        done = ([f"made at {window.read_at}"] if window.read_at else []) + reads_in(args.out, window)
        if done and not args.read_again:
            ap.error(f"the approved read of {window_name(window)} is already made ({'; '.join(done)}): load the kept "
                     "folder with --load. A second read needs the owner's OK (--read-again).")
        folder, p = fetch(args.out, window=window)
        print(f"wfigs-backfill: {p['features']} features ({p['count']} counted) in {p['requests']} requests "
              f"({p['robots_txt_requests']} for robots.txt), {p['bytes_read']} bytes, robots {p['robots']}: {folder}",
              flush=True)
        return 0
    if args.one_off or args.out or args.window or args.read_again:
        ap.error("--load takes a read's folder and --dry-run only")
    with db.connect() as conn:
        stats = load(conn, args.load)
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    print("wfigs-backfill: " + ", ".join(f"{k} {v}" for k, v in stats.items())
          + (" (dry run: nothing written)" if args.dry_run else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
