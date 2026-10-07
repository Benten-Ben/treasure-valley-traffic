"""Reading COMPASS's ArcGIS layers on swidrdc.org, shared by the compass_* sources
(the safety, flow and development plugins; a second shared reader beside arcgis.py).

swidrdc.org has no robots.txt (404: no rules, checked Oct 6, 2026), so
http.get adds no crawl delay; we pace ourselves instead: at least PAUSE_S
between one request's end and the next one's start. Connections sometimes
reset (a few percent of requests from the cloud sandbox, Oct 6, 2026), so a
request that fails on the network, comes back truncated or garbled, or gets
an ArcGIS error of 500 or more is retried twice, 10 and 30 s later. A query
too long for a URL (the HIN layers name 106 and 158 fields; the server 404s
query strings over about 2,000 characters) goes as a form POST, with the same
robots check (ingest/http.py post()).

Each compass_* module is one scheduled source made of several layers. Every
layer has its own ops.source row (terms, notes), its own ops.fetch row inside
the module's, and its record versions in raw.record under its own name. A
module run reads, for each layer:

1. its description (?f=json): the OBJECTID field to page by, field names
   (a field we ask for that's gone fails the layer), the last edit date if
   the layer reports one (none did, Oct 6, 2026);
2. its row count; for a layer of more than CHECK_MIN_ROWS rows, also its
   highest OBJECTID. If count, highest OBJECTID and edit date match the last
   full read, the layer is logged as unchanged and not read (unless that read
   is older than FULL_READ_MAX_AGE: without edit dates, edits in place show
   no other way). Smaller layers are simply read: checking costs as much;
3. its rows, in pages of 2,000 ordered by the OBJECTID field. A read that
   ends with a different number of rows than the count fails the layer.

A layer that already succeeded since the module's last good run (and within
its schedule) is skipped, so after a failure only the failed layers are read
again; the modules ask the scheduler to wait 6 hours after a failure.
Removals are guarded: a layer whose parsed rows fall below 90% of its count,
or below half of what's current, fails instead of retiring anything.

Development: TVT_COMPASS_MAX_PAGES=N reads at most N pages per layer (such
runs are logged as failed, 'capped', and mark nothing removed);
TVT_COMPASS_FORCE=1 skips the freshness and change checks.
"""

import json
import os
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.client import HTTPException

from psycopg.types.json import Jsonb

from . import db, http

BASE = "https://swidrdc.org/arcgis/rest/services/"
PAGE = 2000
PAUSE_S = 1.5
RETRY_WAITS_S = (10, 30)
RETRY_AFTER = "6 hours"            # the modules' back-off after a failed run
CHECK_MIN_ROWS = 5000              # layers larger than this get the change check
FULL_READ_MAX_AGE = "180 days"
MIN_SHARE_OF_COUNT = 0.9
MIN_SHARE_OF_CURRENT = 0.5
MAX_PAGES_ENV = "TVT_COMPASS_MAX_PAGES"
FORCE_ENV = "TVT_COMPASS_FORCE"

CREDIT = "COMPASS and COMPASS member agencies"
HUB_LICENSE = "none stated (COMPASS's disclaimer only: no warranty, no liability)"
HUB_NOTE = "On COMPASS's open-data hub. May be republished with credit."
INTERNAL_LICENSE = "none stated; not offered as open data (no hub entry)"
INTERNAL_NOTE = ("Only on swidrdc.org, not on COMPASS's hub: internal use until COMPASS answers "
                 "(docs/08 §8.9). Don't republish.")


class ServerError(Exception):
    """An ArcGIS error of 500 or more in a 200 response: worth retrying."""


class IncompleteLayer(RuntimeError):
    """A layer read or parsed short: it fails, and nothing is marked removed."""


RETRYABLE = (http.RobotsUnavailable, OSError, HTTPException, json.JSONDecodeError, ServerError)


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


MAX_URL = 1800      # longer queries (the HIN layers' field lists) go as a form POST: IIS 404s long URLs


def paced_get(url, timeout=120):
    PACER.wait()
    try:
        if len(url) > MAX_URL:
            base, _, query = url.partition("?")
            return http.post(base, query.encode(), timeout=timeout)
        return http.get(url, timeout=timeout)
    finally:
        PACER.done()


def get_json(url, get=paced_get, sleep=time.sleep):
    """(status, parsed JSON, robots decision, bytes). Network errors, truncated or garbled
    bodies, server errors and an unreadable robots.txt are retried after RETRY_WAITS_S. A real
    robots.txt disallow, other HTTP errors and ArcGIS errors below 500 are not."""
    for wait in RETRY_WAITS_S + (None,):
        try:
            status, body, decision = get(url, timeout=120)
            data = json.loads(body)
            error = data.get("error") if isinstance(data, dict) else None
            if error:
                code = error.get("code") if isinstance(error.get("code"), int) else 0
                if code >= 500:
                    raise ServerError(f"COMPASS GIS error {code}: {error.get('message')}")
                raise RuntimeError(f"COMPASS GIS error: {error}")
            return status, data, decision, len(body)
        except RETRYABLE as err:
            if wait is None or (isinstance(err, urllib.error.HTTPError) and err.code < 500):
                raise
            print(f"compass: {type(err).__name__}: {err}; retrying in {wait} s", flush=True)
            sleep(wait)


def max_pages():
    """The dev-only page cap from TVT_COMPASS_MAX_PAGES, or None. ValueError if malformed."""
    value = os.environ.get(MAX_PAGES_ENV, "").strip()
    if not value:
        return None
    if not value.isdigit() or int(value) < 1:
        raise ValueError(f"{MAX_PAGES_ENV} must be a whole number of pages (1 or more), not {value!r}")
    return int(value)


def forced():
    return os.environ.get(FORCE_ENV, "").strip().lower() in ("1", "true", "yes")


def query_url(path, params):
    return BASE + path + "/query?" + urllib.parse.urlencode({"where": "1=1", **params, "f": params.get("f", "json")},
                                                             safe=",")


def page_url(path, fields, offset, geometry, oid="objectid", page=PAGE):
    q = {"outFields": ",".join(fields), "orderByFields": oid, "resultOffset": offset, "resultRecordCount": page}
    if geometry:
        q.update(returnGeometry="true", outSR="4326", geometryPrecision="6", f="geojson")
    else:
        q.update(returnGeometry="false", f="json")
    return query_url(path, q)


@dataclass
class Meta:
    oid: str = "objectid"          # the layer's OBJECTID field, lower case
    global_id: str = None
    fields: set = field(default_factory=set)   # lower case
    last_edit: int = None          # editingInfo's (data) last edit date, ms, when reported
    bytes: int = 0
    robots: str = None


def describe(path, get=paced_get, sleep=time.sleep):
    _, data, robots, nbytes = get_json(BASE + path + "?f=json", get, sleep)
    edit = data.get("editingInfo") or {}
    return Meta(oid=(data.get("objectIdField") or "objectid").lower(),
                global_id=(data.get("globalIdField") or "").lower() or None,
                fields={f["name"].lower() for f in data.get("fields") or []},
                last_edit=edit.get("dataLastEditDate") or edit.get("lastEditDate"),
                bytes=nbytes, robots=robots)


def count(path, get=paced_get, sleep=time.sleep):
    _, data, _, nbytes = get_json(query_url(path, {"returnCountOnly": "true"}), get, sleep)
    return int(data["count"]), nbytes


def max_oid(path, oid, get=paced_get, sleep=time.sleep):
    _, data, _, nbytes = get_json(query_url(path, {"outFields": oid, "orderByFields": f"{oid} DESC",
                                                   "resultRecordCount": 1, "returnGeometry": "false"}), get, sleep)
    feats = data.get("features") or []
    attrs = {k.lower(): v for k, v in (feats[0].get("attributes") or {}).items()} if feats else {}
    return attrs.get(oid), nbytes


@dataclass
class Read:
    rows: list = field(default_factory=list)    # [(attributes with lower-case names, GeoJSON geometry or None)]
    pages: int = 0
    bytes: int = 0
    complete: bool = True                         # False when the page cap stopped it early
    expected: int = None                          # the layer's count, when known
    oid: str = "objectid"
    robots: str = None
    status: int = None


def read(path, fields, geometry=True, limit=None, get=paced_get, sleep=time.sleep, page=PAGE, oid="objectid",
         expected=None):
    """Every record of a layer (or table), page by page in OBJECTID order. limit: at most this
    many pages. With `expected` (the layer's count), a full read of another size fails."""
    out, offset = Read(expected=expected, oid=oid), 0
    while True:
        if limit is not None and out.pages >= limit:
            out.complete = False
            break
        out.status, data, out.robots, nbytes = get_json(page_url(path, fields, offset, geometry, oid, page), get, sleep)
        out.pages += 1
        out.bytes += nbytes
        batch = data.get("features") or []
        for f in batch:
            attrs = f.get("properties") if "properties" in f else f.get("attributes")
            out.rows.append(({k.lower(): v for k, v in (attrs or {}).items()},
                             f.get("geometry") if geometry else None))
        exceeded = data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit")
        if not batch or (len(batch) < page and not exceeded):
            break
        offset += len(batch)
    if out.complete and expected is not None and len(out.rows) != expected:
        raise IncompleteLayer(f"{path}: read {len(out.rows)} rows, the layer counts {expected}")
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


def pm_id(v):
    """COMPASS's segment key, or None for its placeholders ('#NYA', '#nya', '01 needs PMID',
    'Int-Related', 'Off-System', 'Intersection*', 'Local', '_', ''): real keys are letters and
    digits with at least one digit ('A01300002000', 'Int001010w01x', '10t100002')."""
    v = text(v)
    return v if v and v.isascii() and v.isalnum() and any(c.isdigit() for c in v) else None


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


def content(props, geom, *names):
    """What makes two records the same: attributes without IDs, and geometry."""
    return [without(props, *names), geom]


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


def current_records(conn, source):
    """How many of a source's records are current in raw.record."""
    return conn.execute("select count(distinct source_id) from raw.record where source = %s and removed_at is null",
                        (source,)).fetchone()[0]


def check_share(got, parsed, current, what):
    """Before anything is marked removed: a complete read must have parsed at least 90% of the
    layer's count and at least half of what's current. Otherwise the layer fails (a renamed
    field, an empty answer) rather than retiring good rows."""
    if not got.complete:
        return
    if got.expected and parsed < MIN_SHARE_OF_COUNT * got.expected:
        raise IncompleteLayer(f"{what}: parsed {parsed} of the layer's {got.expected} rows")
    if current and parsed < MIN_SHARE_OF_CURRENT * current:
        raise IncompleteLayer(f"{what}: parsed {parsed} rows, but {current} are current")


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
    fields: object       # requested fields, or fields(meta) -> list (the OBJECTID field is always added)
    store: object        # store(conn, fetch_id, seen_at, Read) -> stats dict
    geometry: bool = True


def layer_source(name, title, path, license=HUB_LICENSE, notes=HUB_NOTE, module=None):
    return {"name": name, "title": title, "url": BASE + path, "access": "open", "schedule": None,
            "license": license, "credit": CREDIT,
            "notes": f"{notes} Collected by {module}." if module else notes}


def layer_done(conn, layer, module, schedule):
    """True if the layer succeeded after the module's last good run ended, and within the schedule:
    a module run that failed part-way doesn't read its finished layers again."""
    return conn.execute(
        """select coalesce(max(started_at) filter (where ok), '-infinity') >
                    greatest(now() - %s::interval,
                             coalesce((select max(finished_at) from ops.fetch where source = %s and ok), '-infinity'))
           from ops.fetch where source = %s""", (schedule, module, layer)).fetchone()[0]


def signature_unchanged(conn, source, signature):
    return conn.execute(
        """select signature = %s and read_at > now() - %s::interval
           from ops.layer_signature where source = %s""",
        (Jsonb(signature), FULL_READ_MAX_AGE, source)).fetchone() in ((True,),)


def save_signature(conn, source, signature, read):
    conn.execute(
        """insert into ops.layer_signature (source, signature, read_at, checked_at) values (%s, %s, now(), now())
           on conflict (source) do update set signature = excluded.signature, checked_at = excluded.checked_at,
             read_at = case when %s then excluded.read_at else ops.layer_signature.read_at end""",
        (source, Jsonb(signature), read))


def mark_capped(conn, fetch_ids):
    conn.execute("update ops.fetch set ok = false, error = %s where id = any(%s)",
                 (f"capped by {MAX_PAGES_ENV} (dev run): incomplete", list(fetch_ids)))
    conn.commit()


def run_layer(conn, module, layer, limit, force, get, sleep):
    """Check and (if needed) read and store one layer. Returns (stats, fetch id, complete)."""
    name = layer.source["name"]
    with db.Fetch(conn, name) as f:
        meta = describe(layer.path, get, sleep)
        wanted = layer.fields(meta) if callable(layer.fields) else layer.fields
        missing = sorted({x.lower() for x in wanted} - meta.fields - {"objectid", meta.oid})
        if missing:
            raise RuntimeError(f"{layer.path}: fields no longer in the layer: {', '.join(missing)}")
        n, nbytes = count(layer.path, get, sleep)
        signature = {"count": n, "max_oid": None, "last_edit": meta.last_edit}
        f.bytes, f.robots, f.http_status = meta.bytes + nbytes, meta.robots, 200
        if n > CHECK_MIN_ROWS:
            signature["max_oid"], nbytes = max_oid(layer.path, meta.oid, get, sleep)
            f.bytes += nbytes
            if not force and limit is None and signature_unchanged(conn, name, signature):
                save_signature(conn, name, signature, read=False)
                f.records = 0
                return {"unchanged": f"count {n}, highest OBJECTID {signature['max_oid']}"}, f.id, True
        fields = [meta.oid] + [x for x in wanted if x.lower() not in ("objectid", meta.oid)]
        got = read(layer.path, fields, layer.geometry, limit=limit, get=get, sleep=sleep, page=PAGE, oid=meta.oid,
                   expected=n)
        f.http_status, f.bytes, f.records = got.status, f.bytes + got.bytes, len(got.rows)
        stats = layer.store(conn, f.id, f.started_at, got)
        if got.complete:
            save_signature(conn, name, signature, read=True)
    return {"rows": len(got.rows), **({} if got.complete else {"capped at pages": got.pages}), **stats}, f.id, \
        got.complete


def run(conn, module, layers, get=paced_get, sleep=time.sleep):
    """Check, read and store each layer; one ops.fetch row for the module, one per layer inside it."""
    db.ensure_source(conn, module)
    for layer in layers:
        db.ensure_source(conn, layer.source)
    conn.commit()
    limit, force = max_pages(), forced()
    if limit:
        print(f"{module['name']}: {MAX_PAGES_ENV}={limit}: at most {limit} pages per layer (dev only); "
              "logged as failed ('capped'), and nothing is marked removed", flush=True)
    stats, capped = {}, []
    with db.Fetch(conn, module["name"]) as run_fetch:
        run_fetch.records = run_fetch.bytes = 0
        for layer in layers:
            if not force and layer_done(conn, layer.source["name"], module["name"], module["schedule"]):
                stats[layer.name] = "done earlier"
                continue
            layer_stats, fetch_id, complete = run_layer(conn, module["name"], layer, limit, force, get, sleep)
            if not complete:
                capped.append(fetch_id)
            row = conn.execute("select http_status, robots, records, bytes from ops.fetch where id = %s",
                               (fetch_id,)).fetchone()
            run_fetch.http_status, run_fetch.robots = row[0], row[1]
            run_fetch.records += row[2] or 0
            run_fetch.bytes += row[3] or 0
            stats.update({f"{layer.name} {k}": v for k, v in layer_stats.items()})
    if capped:
        mark_capped(conn, capped + [run_fetch.id])
    return stats
