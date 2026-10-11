"""The approved backfill of fire perimeters for Aug-Dec 2025 (landscape sprint, decision 25: owner, Oct 8, 2026):
`python3 -m ingest wfigs-backfill`.

The perimeter poller (nifc_wfigs_perimeters) started on Oct 7, 2026, and its first run read what had changed in
2026. A fire from the second half of 2025 is in raw.record only if its record changed in 2026, but the burn scars
(burn_scars.py) draw every fire after the ground's photo, last flown on Jul 24, 2025. The owner approved one small
read of the same service for Aug-Dec 2025. This is that read, in two steps, so that one read can be loaded into more
than one database (the scratch copy now, production at deploy) without asking NIFC twice:

1. `--fetch --one-off --out DIR`: one count, then one read of the all-years perimeter service (a few more by ID
   only if the answer is cut at the server's page size): every perimeter touching the ring whose fire was
   discovered from Aug 1 through Dec 31, 2025, Boise time (or, with no discovery time, whose polygon is from then),
   geometry at the poller's precision. Every request goes through ingest/http.py: robots.txt first
   (services3.arcgis.com answers 403, so no rules), our User-Agent, and at least 2 s between requests. Over CAP
   features it stops before reading them (the read is meant to be small). It writes DIR/<UTC time>/features.json
   (the features as the service sent them) and provenance.json (what was asked, where, when, by whom, under which
   approval, what came back, and the file's sha256). It touches no database.
2. `--load DIR/<UTC time>`: checks features.json against its provenance, keeps the window's features (in case
   the server ignored the filter), parses them exactly as the poller does (nifc_wfigs_perimeters.parse), and stores
   each fire's perimeter as a nifc_wfigs_perimeters version in raw.record. A version already held is left as it
   is. The read is logged once per database as a fetch of the one-off source nifc_wfigs_perimeters_backfill, with
   the read's own times, status and robots result, and every version it adds points at that fetch
   (raw.record.first_fetch): that's the provenance in the database. Loading the same read again adds nothing.
   No lifecycles (evt.event): these fires are long out, and the poller keeps a fire first seen already out in
   raw.record only.

The window is the approval's, fixed here rather than an option. A fire discovered from Jul 25 to Jul 31, 2025 is
after the photo but outside the approved window: it's drawn only if the poller holds it (the RANGE fire, Jul 31,
is held).

    python3 -m ingest wfigs-backfill --fetch --one-off --out /srv/out
    python3 -m ingest wfigs-backfill --load /srv/out/20261011T1300Z --dry-run
    python3 -m ingest wfigs-backfill --load /srv/out/20261011T1300Z

Standard library plus psycopg.
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest import USER_AGENT, arcgis, db, http
from . import common
from .sources import nifc_wfigs_perimeters as perimeters

BOISE = ZoneInfo("America/Boise")
FIRST_DAY, LAST_DAY = date(2025, 8, 1), date(2025, 12, 31)     # the approved window, Boise days, both included
CAP = 400                         # the most features the read may bring
FEATURES, PROVENANCE = "features.json", "provenance.json"
APPROVAL = ("owner, Oct 8, 2026: landscape sprint decision 25 ('one small backfill read of the same fire service "
            "for Aug-Dec 2025'); go-ahead to build, Oct 10")

SOURCE = {
    "name": "nifc_wfigs_perimeters_backfill",
    "title": "NIFC WFIGS interagency fire perimeters: the one backfill read of Aug-Dec 2025",
    "url": perimeters.LAYER,
    "access": "one_off",
    "license": perimeters.SOURCE["license"],
    "credit": perimeters.SOURCE["credit"],
    "notes": "One read of the all-years perimeter service for fires discovered Aug 1 - Dec 31, 2025 (Boise), "
             f"approved by the owner ({APPROVAL}). Its records are stored as nifc_wfigs_perimeters versions; each "
             "version it added points (first_fetch) at this source's fetch row. "
             "plugins/hazards/ingest/wfigs_backfill.py.",
}


# --- the window ------------------------------------------------------------------------------------

def bounds():
    """The window as UTC datetimes: (start, end), the end excluded."""
    start = datetime.combine(FIRST_DAY, datetime.min.time(), tzinfo=BOISE)
    end = datetime.combine(date.fromordinal(LAST_DAY.toordinal() + 1), datetime.min.time(), tzinfo=BOISE)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def where():
    """The service filter: discovered in the window, or with no discovery time, a polygon from the window.
    Absolute UTC times (NIFC asks for no relative dates)."""
    start, end = (f"TIMESTAMP '{t:%Y-%m-%d %H:%M:%S}'" for t in bounds())
    return (f"(attr_FireDiscoveryDateTime >= {start} AND attr_FireDiscoveryDateTime < {end}) OR "
            f"(attr_FireDiscoveryDateTime IS NULL AND poly_PolygonDateTime >= {start} AND poly_PolygonDateTime < {end})")


def in_window(attrs):
    """Whether a feature's attributes (or a parsed payload) fall in the window, as where() asks."""
    start, end = bounds()
    t = arcgis.esri_date(attrs.get("attr_FireDiscoveryDateTime"))
    if t is None:
        t = arcgis.esri_date(attrs.get("poly_PolygonDateTime"))
    return t is not None and start <= t < end


def count_url():
    q = {"where": where(), "returnCountOnly": "true", "f": "json",
         "geometry": ",".join(str(v) for v in common.RING), "geometryType": "esriGeometryEnvelope",
         "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"}
    return perimeters.LAYER + "/query?" + urllib.parse.urlencode(q)


# --- step 1: the read --------------------------------------------------------------------------------

def stamp(t):
    return t.astimezone(timezone.utc).strftime("%Y%m%dT%H%MZ")


def fetch(out_dir, get=None, sleep=None, now=None, cap=CAP):
    """The one read. Writes out_dir/<UTC time>/{features.json, provenance.json}; returns that folder."""
    label = SOURCE["name"]
    calls = []

    def counted(url):
        calls.append(url)
        return (get or (lambda u: http.get(u, timeout=180)))(url)

    kw = {} if sleep is None else {"sleep": sleep}
    started = now or datetime.now(timezone.utc)
    _, _, decision, data = arcgis.get_with_retries(count_url(), label, counted, parse=json.loads, **kw)
    if "error" in data or not isinstance(data.get("count"), int):
        raise RuntimeError(f"{label}: the count came back without a count: {str(data)[:200]}")
    if data["count"] > cap:
        raise RuntimeError(f"{label}: the service counts {data['count']} perimeters in the window, over the cap of "
                           f"{cap}; nothing read (the approval is for a small read)")
    features, nbytes, status, decision = common.query_layer(
        perimeters.LAYER, label, where=where(), box=common.RING, geometry=True, precision=perimeters.PRECISION,
        page_by_id=True, get=counted, **kw)
    finished = datetime.now(timezone.utc) if now is None else now
    if len(features) > cap:
        raise RuntimeError(f"{label}: {len(features)} features came back, over the cap of {cap}; nothing kept")
    folder = os.path.join(out_dir, stamp(started))
    os.makedirs(folder, exist_ok=False)
    body = json.dumps(features, separators=(",", ":"), sort_keys=True).encode()
    with open(os.path.join(folder, FEATURES), "wb") as f:
        f.write(body)
    start, end = bounds()
    provenance = {
        "what": "NIFC WFIGS interagency fire perimeters: the backfill read of Aug-Dec 2025 (wfigs_backfill.py)",
        "approval": APPROVAL,
        "service": perimeters.LAYER,
        "where": where(),
        "window": {"first_day": FIRST_DAY.isoformat(), "last_day": LAST_DAY.isoformat(), "time_zone": "America/Boise",
                   "utc": [common.iso(start), common.iso(end)]},
        "box": list(common.RING),
        "precision": perimeters.PRECISION,
        "user_agent": USER_AGENT,
        "robots": decision,
        "http_status": status,
        "requests": len(calls),
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
    """(provenance, features) from a read's folder, the file checked against its sha256."""
    with open(os.path.join(folder, PROVENANCE), encoding="utf-8") as f:
        provenance = json.load(f)
    with open(os.path.join(folder, provenance.get("file") or FEATURES), "rb") as f:
        body = f.read()
    if hashlib.sha256(body).hexdigest() != provenance.get("sha256"):
        raise ValueError(f"{folder}: {FEATURES} doesn't match the sha256 in {PROVENANCE}")
    if provenance.get("service") != perimeters.LAYER or provenance.get("where") != where():
        raise ValueError(f"{folder}: not this backfill's read (service or filter differ)")
    features = json.loads(body)
    if not isinstance(features, list):
        raise ValueError(f"{folder}: {FEATURES} isn't a list of features")
    return provenance, features


def prepare(features):
    """The poller's parse of the window's features -> ({source_id: (payload, geometry)}, stats)."""
    kept = [f for f in features if in_window((f or {}).get("attributes") or {})]
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


def store(conn, provenance, parsed, source=perimeters.SOURCE["name"]):
    """Add the read's versions to raw.record (as the poller's source); a version already held is left as it is."""
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
            "already held": len(parsed) - new}


def load(conn, folder, source=perimeters.SOURCE["name"]):
    provenance, features = read(folder)
    parsed, stats = prepare(features)
    stats.update(store(conn, provenance, parsed, source))
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest wfigs-backfill",
                                 description="The approved one read of NIFC's fire perimeters for Aug-Dec 2025, and "
                                             "its load into raw.record.")
    step = ap.add_mutually_exclusive_group(required=True)
    step.add_argument("--fetch", action="store_true", help="read the service once (needs --one-off and --out)")
    step.add_argument("--load", metavar="DIR", help="load a read's folder (DIR/<UTC time>) into raw.record")
    ap.add_argument("--one-off", action="store_true",
                    help="confirm this is the one approved read, run by hand (required with --fetch)")
    ap.add_argument("--out", metavar="DIR", help="where --fetch writes its folder")
    ap.add_argument("--dry-run", action="store_true", help="with --load: check and report, then roll back")
    args = ap.parse_args(argv)
    if args.fetch:
        if not args.one_off:
            ap.error("--fetch reads NIFC's service: pass --one-off to confirm it's the one approved read")
        if not args.out:
            ap.error("--fetch needs --out DIR")
        folder, p = fetch(args.out)
        print(f"wfigs-backfill: {p['features']} features ({p['count']} counted) in {p['requests']} requests, "
              f"{p['bytes_read']} bytes, robots {p['robots']}: {folder}", flush=True)
        return 0
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
