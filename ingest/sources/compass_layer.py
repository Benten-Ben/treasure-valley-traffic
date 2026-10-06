"""Reading COMPASS's ArcGIS layers on swidrdc.org, shared by the compass_* sources.

swidrdc.org has no robots.txt (404: no rules, checked Oct 6, 2026), so
http.get adds no crawl delay; we pace ourselves instead: at least PAUSE_S
between one request's end and the next one's start, pages of 2,000 records
in OBJECTID order. Connections to it sometimes reset (a few percent of
requests from the cloud sandbox, Oct 6, 2026), so a page that fails on the
network is retried twice, 10 and 30 s later.

Each compass_* module is one scheduled source made of several layers. Every
layer has its own ops.source row (terms, notes) and its own ops.fetch row
inside the module's, and its record versions go to raw.record under that
layer's name.

For development, TVT_COMPASS_MAX_PAGES=N reads at most N pages per layer;
such a run is incomplete, so nothing is marked removed.
"""

import json
import os
import re
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from .. import db, http

BASE = "https://swidrdc.org/arcgis/rest/services/"
PAGE = 2000
PAUSE_S = 1.5
# Two retries a page: resets come a few percent of requests at a time, and one
# page failing throws away the whole layer's run (173 pages for the crash details).
RETRY_WAITS_S = (10, 30)
MAX_PAGES_ENV = "TVT_COMPASS_MAX_PAGES"

CREDIT = "COMPASS and COMPASS member agencies"
HUB_LICENSE = "none stated (COMPASS's disclaimer only: no warranty, no liability)"
HUB_NOTE = "On COMPASS's open-data hub. May be republished with credit."
INTERNAL_LICENSE = "none stated; not offered as open data (no hub entry)"
INTERNAL_NOTE = ("Only on swidrdc.org, not on COMPASS's hub: internal use until COMPASS answers "
                 "(docs/08 §8.9). Don't republish.")


# --- requests -----------------------------------------------------------------

class Pacer:
    """At least `gap` seconds from the end of one request to the start of the next."""

    def __init__(self, gap=PAUSE_S, clock=time.monotonic, sleep=time.sleep):
        self.gap, self.clock, self.sleep, self.last = gap, clock, sleep, None

    def wait(self):
        if self.last is not None:
            wait = self.last + self.gap - self.clock()
            if wait > 0:
                self.sleep(wait)

    def done(self):
        self.last = self.clock()


PACER = Pacer()


def paced_get(url, timeout=120):
    PACER.wait()
    try:
        return http.get(url, timeout=timeout)
    finally:
        PACER.done()


def get_retried(url, get=paced_get, sleep=time.sleep):
    """Network errors, server errors and an unreadable robots.txt are retried, after
    RETRY_WAITS_S. A real robots.txt disallow and other HTTP errors are not."""
    for wait in RETRY_WAITS_S + (None,):
        try:
            return get(url, timeout=120)
        except (http.RobotsUnavailable, OSError) as err:
            if wait is None or (isinstance(err, urllib.error.HTTPError) and err.code < 500):
                raise
            print(f"compass: {err}; retrying in {wait} s", flush=True)
            sleep(wait)


def max_pages():
    """The dev-only page cap from TVT_COMPASS_MAX_PAGES, or None."""
    value = os.environ.get(MAX_PAGES_ENV, "").strip()
    if not value:
        return None
    if not value.isdigit() or int(value) < 1:
        raise SystemExit(f"{MAX_PAGES_ENV} must be a whole number of pages (1 or more)")
    return int(value)


def query_url(path, fields, offset, geometry, page=PAGE):
    q = {"where": "1=1", "outFields": ",".join(fields), "orderByFields": "objectid",
         "resultOffset": offset, "resultRecordCount": page}
    if geometry:
        q.update(returnGeometry="true", outSR="4326", geometryPrecision="6", f="geojson")
    else:
        q.update(returnGeometry="false", f="json")
    return BASE + path + "/query?" + urllib.parse.urlencode(q, safe=",")


@dataclass
class Read:
    rows: list = field(default_factory=list)    # [(attributes dict, GeoJSON geometry or None)]
    pages: int = 0
    bytes: int = 0
    complete: bool = True                         # False when the page cap stopped it early
    robots: str = None
    status: int = None


def read(path, fields, geometry=True, limit=None, get=paced_get, sleep=time.sleep, page=PAGE):
    """Every record of a layer (or table), page by page. limit: at most this many pages."""
    out, offset = Read(), 0
    while True:
        if limit is not None and out.pages >= limit:
            out.complete = False
            break
        out.status, body, out.robots = get_retried(query_url(path, fields, offset, geometry, page), get, sleep)
        out.pages += 1
        out.bytes += len(body)
        data = json.loads(body)
        if "error" in data:
            raise RuntimeError(f"COMPASS GIS error on {path}: {data['error']}")
        batch = data.get("features") or []
        for f in batch:
            attrs = f.get("properties") if "properties" in f else f.get("attributes")
            out.rows.append((attrs or {}, f.get("geometry") if geometry else None))
        exceeded = data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit")
        if not batch or (len(batch) < page and not exceeded):
            break
        offset += len(batch)
    return out


# --- values -------------------------------------------------------------------

JUNK = {"", "#NAME?", "#N/A", "#VALUE!", "#REF!"}


def fix_mojibake(s):
    """Undo UTF-8 read as Windows-1252, once or twice ('Water Ã¢â‚¬â€œ standing' -> 'Water – standing')."""
    for _ in range(2):
        if not any(c in s for c in "ÃÂâ"):
            break
        try:
            s = s.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
    return s


def text(v):
    """Tidy text: whitespace collapsed, mojibake undone; None for blanks and spreadsheet errors."""
    if v is None:
        return None
    v = fix_mojibake(" ".join(str(v).split()))
    return None if v in JUNK else v


def number(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(str(v).strip())
    except ValueError:
        return None
    return x if x == x else None          # NaN -> None


def integer(v):
    x = number(v)
    return None if x is None else int(round(x))


YES = {"Y", "YES", "TRUE", "T", "1"}
NO = {"N", "NO", "FALSE", "F", "0"}


def flag(v):
    """Y/N, Yes/No, 1/0 -> bool; anything else ('-U', '#NAME?', blank) -> None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return {1: True, 0: False}.get(v)
    v = (text(v) or "").upper()
    return True if v in YES else False if v in NO else None


PM_ID = re.compile(r"[A-Za-z0-9]*[0-9][A-Za-z0-9]*")


def pm_id(v):
    """COMPASS's segment key, or None for its placeholders ('#NYA', '#nya', '01 needs PMID',
    'Int-Related', 'Off-System', 'Intersection*', 'Local', '_', ''): real keys are letters and
    digits with at least one digit ('A01300002000', 'Int001010w01x', '10t100002')."""
    v = text(v)
    return v if v and PM_ID.fullmatch(v) else None


def epoch_ms(v):
    """An ArcGIS date (milliseconds since 1970, UTC) as an aware datetime, or None."""
    x = number(v)
    if x is None:
        return None
    try:
        return datetime.fromtimestamp(x / 1000, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def epoch_date(v):
    """An ArcGIS date-only value. COMPASS stores the calendar day at midnight UTC, so the
    UTC date is the day (a value stored as local midnight, 06:00 or 07:00 UTC, gives the same day)."""
    t = epoch_ms(v)
    return t.date() if t else None


def without(props, *names):
    """A payload without the fields that change without the record changing (OBJECTID, shape lengths)."""
    drop = {n.lower() for n in names} | {"objectid", "shape__length", "shape__area"}
    return {k: v for k, v in props.items() if k.lower() not in drop}


def keyed(items, key, content=lambda item: item):
    """[(key, item)] with stable keys: exact repeats (same key, same content) are dropped;
    different items sharing a key get '#2', '#3', ... in order of their content hash, so the
    same set of items always gets the same keys. Returns (pairs, repeats dropped, keys suffixed)."""
    groups = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    pairs, dropped, suffixed = [], 0, 0
    for k, group in groups.items():
        unique = {}
        for item in group:
            unique.setdefault(db.version_hash(content(item)), item)
        dropped += len(group) - len(unique)
        for i, h in enumerate(sorted(unique)):
            if i:
                suffixed += 1
            pairs.append((k if i == 0 else f"{k}#{i + 1}", unique[h]))
    return pairs, dropped, suffixed


# --- storing ------------------------------------------------------------------

GEOM_SQL = {
    "point": "ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)",
    "multi": "ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326))",
}


def upsert(conn, table, key, rows, seen_at, geom=None, active=True):
    """Insert or update typed rows (dicts of column -> value; a 'geom' entry holds GeoJSON).
    Sets first_seen on insert and last_seen (and active) always."""
    if not rows:
        return 0
    cols = [c for c in rows[0] if c != "geom"]
    names, values = list(cols), [f"%({c})s" for c in cols]
    if geom:
        names.append("geom")
        values.append(GEOM_SQL[geom])
    names += ["first_seen", "last_seen"]
    values += ["%(_seen)s", "%(_seen)s"]
    if active:
        names.append("active")
        values.append("true")
    updates = ", ".join(f"{c} = excluded.{c}" for c in names if c not in key and c != "first_seen")
    sql = (f"insert into {table} ({', '.join(names)}) values ({', '.join(values)}) "
           f"on conflict ({', '.join(key)}) do update set {updates}")
    params = []
    for r in rows:
        p = {k: (Jsonb(v) if isinstance(v, dict) else v) for k, v in r.items() if k != "geom"}
        if geom:
            p["geom"] = json.dumps(r["geom"]) if r.get("geom") else None
        p["_seen"] = seen_at
        params.append(p)
    with conn.cursor() as cur:
        cur.executemany(sql, params)
    return len(rows)


def retire(conn, table, seen_at):
    """Mark rows not seen in a complete snapshot as inactive."""
    return conn.execute(f"update {table} set active = false where active and last_seen < %s",
                        (seen_at,)).rowcount


def store_records(conn, source, records, fetch_id, seen_at, complete):
    """raw.record versions; returns stats."""
    new, unchanged, removed = db.upsert_records(conn, source, records, fetch_id, seen_at, complete=complete)
    return {"versions new": new, "unchanged": unchanged, "removed": removed}


# --- running ------------------------------------------------------------------

@dataclass
class Layer:
    name: str            # short name for stats ('crashes')
    source: dict         # this layer's ops.source row
    path: str            # e.g. 'COMPASSData/CrashData/FeatureServer/0'
    fields: list
    store: object        # store(conn, fetch_id, seen_at, Read) -> stats dict
    geometry: bool = True


def layer_source(name, title, path, license=HUB_LICENSE, notes=HUB_NOTE, module=None):
    return {"name": name, "title": title, "url": BASE + path, "access": "open", "schedule": None,
            "license": license, "credit": CREDIT,
            "notes": f"{notes} Collected by {module}." if module else notes}


def run(conn, module, layers, reader=read):
    """Fetch and store each layer; one ops.fetch row for the module, one per layer inside it."""
    db.ensure_source(conn, module)
    for layer in layers:
        db.ensure_source(conn, layer.source)
    conn.commit()
    limit = max_pages()
    if limit:
        print(f"{module['name']}: {MAX_PAGES_ENV}={limit}: at most {limit} pages per layer (dev only); "
              "capped layers are incomplete, so nothing is marked removed", flush=True)
    stats = {}
    with db.Fetch(conn, module["name"]) as run_fetch:
        run_fetch.records = run_fetch.bytes = 0
        for layer in layers:
            with db.Fetch(conn, layer.source["name"]) as f:
                got = reader(layer.path, layer.fields, layer.geometry, limit=limit)
                f.http_status, f.robots, f.bytes, f.records = got.status, got.robots, got.bytes, len(got.rows)
                layer_stats = layer.store(conn, f.id, f.started_at, got)
            run_fetch.http_status, run_fetch.robots = got.status, got.robots
            run_fetch.records += len(got.rows)
            run_fetch.bytes += got.bytes
            stats[layer.name] = len(got.rows)
            if not got.complete:
                stats[f"{layer.name} capped at pages"] = got.pages
            stats.update({f"{layer.name} {k}": v for k, v in layer_stats.items()})
    return stats
