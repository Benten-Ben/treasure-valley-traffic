"""Reading Esri ArcGIS FeatureServer layers: paged queries with retries.

Shared by the lane-inventory ingestors (itd_hpms, achd_msm, compass_centerline).
Pages are keyed by the layer's object ID (`where OBJECTID > last`, ordered),
which, unlike offsets, can't skip or repeat rows if the layer changes between
pages. Every request goes through ingest.http (robots.txt, our User-Agent,
crawl-delay), with a pause between pages. Pages are read as Esri JSON and
turned into GeoJSON features here.

The callers store full snapshots, where a row missing from a fetch would
read as removed, so the list of object IDs is asked for first and every one
must arrive. With a box, the ID list (like the server's counts) is coarser
than the pages: on ITD's server, 67 of 19,801 through-lane rows it listed
never came in the pages (Oct 6, 2026), lines up to 2.3 km outside the box
that the coarser test lets in. Listed rows the pages miss are fetched by ID,
without the box; they're harmless extras (they match nothing).
"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from . import http

RETRY_WAITS_S = (5, 15, 45)
BY_ID_CHUNK = 100            # IDs per by-ID request (keeps the URL short)


def _box(box):
    """Rows whose line touches the box (west, south, east, north, in degrees); returned whole."""
    if not box:
        return {}
    return {"geometry": ",".join(str(v) for v in box), "geometryType": "esriGeometryEnvelope", "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects"}


def _fields(fields):
    return fields if isinstance(fields, str) else ",".join(fields)


def query_url(layer, *, where="1=1", fields="*", oid_field="OBJECTID", after=None, page=2000, box=None,
              precision=6):
    """A query for one page: rows with object ID above `after`, in object ID order, in WGS84 (Esri JSON)."""
    clause = where if after is None else f"({where}) AND {oid_field} > {int(after)}"
    q = {"where": clause, "outFields": _fields(fields), "returnGeometry": "true", "outSR": "4326",
         "geometryPrecision": precision, "orderByFields": f"{oid_field} ASC", "resultRecordCount": page, "f": "json",
         **_box(box)}
    return f"{layer}/query?{urllib.parse.urlencode(q)}"


def ids_url(layer, *, where="1=1", box=None):
    """Every object ID the query matches (not limited by the server's page size)."""
    return f"{layer}/query?{urllib.parse.urlencode({'where': where, 'returnIdsOnly': 'true', 'f': 'json', **_box(box)})}"


def by_ids_url(layer, ids, *, fields="*", precision=6):
    q = {"objectIds": ",".join(str(i) for i in ids), "outFields": _fields(fields), "returnGeometry": "true",
         "outSR": "4326", "geometryPrecision": precision, "f": "json"}
    return f"{layer}/query?{urllib.parse.urlencode(q)}"


def get_with_retries(url, label, get=None, waits=RETRY_WAITS_S):
    """GET, retrying network errors (resets, timeouts), server errors and an unreadable
    robots.txt with backoff. A real robots.txt disallow and other HTTP errors are not retried."""
    get = get or (lambda u: http.get(u, timeout=180))
    for wait in tuple(waits) + (None,):
        try:
            return get(url)
        except (http.RobotsUnavailable, OSError) as err:
            if wait is None or (isinstance(err, urllib.error.HTTPError) and err.code < 500):
                raise
            print(f"{label}: {err}; retrying in {wait} s", flush=True)
            time.sleep(wait)


def _exceeded(page):
    return bool(page.get("exceededTransferLimit") or (page.get("properties") or {}).get("exceededTransferLimit"))


def esri_geometry(g):
    """Esri JSON geometry -> GeoJSON (polylines, points and polygons; z and m dropped)."""
    if not g:
        return None
    if "paths" in g:
        paths = [[list(p[:2]) for p in path] for path in g["paths"] if path]
        if not paths:
            return None
        return ({"type": "LineString", "coordinates": paths[0]} if len(paths) == 1
                else {"type": "MultiLineString", "coordinates": paths})
    if "x" in g and "y" in g:
        return None if g["x"] is None or g["y"] is None else {"type": "Point", "coordinates": [g["x"], g["y"]]}
    if "rings" in g:
        return {"type": "Polygon", "coordinates": [[list(p[:2]) for p in ring] for ring in g["rings"]]}
    raise ValueError(f"unsupported Esri geometry with keys {sorted(g)}")


def esri_feature(f):
    """An Esri JSON feature as a GeoJSON one: {'type', 'properties', 'geometry'}."""
    return {"type": "Feature", "properties": f.get("attributes") or {}, "geometry": esri_geometry(f.get("geometry"))}


def _json(get, url, label, out):
    status, body, decision = get_with_retries(url, label, get)
    out["status"], out["robots"] = status, decision
    out["bytes"] += len(body)
    data = json.loads(body)
    if "error" in data:
        raise RuntimeError(f"{label}: server error: {data['error']}")
    return data


def fetch_layer(layer, *, label, where="1=1", fields="*", oid_field="OBJECTID", box=None, page=2000, pause_s=1.5,
                get=None, sleep=time.sleep, check_ids=True):
    """Every feature of a layer (inside `box`, if given), page by page.

    Stops on an empty page, or on a short page the server doesn't flag as cut
    off (a server whose own limit is below `page` returns short pages flagged
    exceededTransferLimit, and paging goes on). With check_ids, it first lists
    the object IDs to expect; listed rows the pages missed are fetched by ID,
    and if any still don't arrive it raises rather than return a short
    snapshot. Returns a dict: features, expected, by_id (rows fetched by ID),
    bytes, requests, robots (decision), status (last HTTP status).
    """
    out = {"features": [], "expected": None, "by_id": 0, "bytes": 0, "requests": 0, "robots": None, "status": None}
    expected = None
    if check_ids:
        data = _json(get, ids_url(layer, where=where, box=box), label, out)
        out["requests"] += 1
        if not isinstance(data.get("objectIds", []), list):
            raise RuntimeError(f"{label}: no object ID list from the server: {str(data)[:300]}")
        expected = set(data.get("objectIds") or [])
        out["expected"] = len(expected)
        sleep(pause_s)
    after = None
    while True:
        url = query_url(layer, where=where, fields=fields, oid_field=oid_field, after=after, page=page, box=box)
        data = _json(get, url, label, out)
        out["requests"] += 1
        batch = [esri_feature(f) for f in data.get("features") or []]
        out["features"] += batch
        if not batch or (len(batch) < page and not _exceeded(data)):
            break
        oids = [(f.get("properties") or {}).get(oid_field) for f in batch]
        oids = [o for o in oids if o is not None]
        if not oids:
            raise RuntimeError(f"{label}: features carry no {oid_field}; can't page")
        last = max(oids)
        if after is not None and last <= after:
            raise RuntimeError(f"{label}: object IDs didn't advance past {after}; stopping")
        after = last
        sleep(pause_s)
    if expected is not None:
        got = {f["properties"].get(oid_field) for f in out["features"]}
        missing = sorted(expected - got)
        for i in range(0, len(missing), BY_ID_CHUNK):
            sleep(pause_s)
            data = _json(get, by_ids_url(layer, missing[i:i + BY_ID_CHUNK], fields=fields), label, out)
            out["requests"] += 1
            batch = [esri_feature(f) for f in data.get("features") or []]
            out["features"] += batch
            out["by_id"] += len(batch)
            got |= {f["properties"].get(oid_field) for f in batch}
        lost = expected - got
        if lost:
            raise RuntimeError(f"{label}: {len(lost)} of the {len(expected)} listed rows never arrived "
                               f"(e.g. {oid_field} {sorted(lost)[:5]}); not storing a short snapshot")
    return out


# --- small cleaners shared by the parsers ------------------------------------

def to_int(v):
    """'5' -> 5, 5.0 -> 5; blanks, words and None -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if v == int(v) else None
    s = str(v).strip()
    return int(s) if s.isdigit() else None


def to_float(v, places=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if places is None else round(f, places) + 0.0       # + 0.0 turns -0.0 into 0.0


def text(v):
    """Trimmed text with inner runs of spaces collapsed; blank -> None."""
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def esri_date(ms):
    """Esri date (milliseconds since 1970, UTC) -> datetime, or None."""
    if ms is None or isinstance(ms, bool):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# --- republished layers ------------------------------------------------------
#
# Overwriting a hosted layer renumbers OBJECTIDs and can regenerate GlobalIDs.
# A source keyed by GlobalID would then see every record "removed" and as many
# "new", and retire all its rows. These pair the new IDs with the old ones
# instead, so core rows keep their ids and first_seen.

REPUBLISH_SHARE = 0.5


def is_republish(known, snapshot):
    """Most of the snapshot's IDs are new to us and most of ours are gone from it."""
    known, snapshot = set(known), set(snapshot)
    if not known or not snapshot:
        return False
    return (len(snapshot - known) > REPUBLISH_SHARE * len(snapshot)
            and len(known - snapshot) > REPUBLISH_SHARE * len(known))


def pair_republished(old, new):
    """{new ID: old ID} for new records that are old ones under a new ID.

    old, new: {ID: (code, line fingerprint)}, only the IDs on one side. Pairs
    by code and line first, then by a code found once on each side, then by a
    line found once on each side. A missing code or line never pairs.
    """
    pairs, old_left, new_left = {}, dict(old), dict(new)
    for key in (lambda v: v if None not in v else None, lambda v: v[0], lambda v: v[1]):
        by_old, by_new = {}, {}
        for i, v in old_left.items():
            by_old.setdefault(key(v), []).append(i)
        for i, v in new_left.items():
            by_new.setdefault(key(v), []).append(i)
        for k, new_ids in by_new.items():
            old_ids = by_old.get(k, [])
            if k is not None and len(new_ids) == 1 and len(old_ids) == 1:
                pairs[new_ids[0]] = old_ids[0]
                del new_left[new_ids[0]], old_left[old_ids[0]]
    return pairs


def _code(values):
    values = [v for v in values]
    return None if all(v in (None, "", " ") for v in values) else "|".join(str(v) for v in values)


def carry_over(conn, *, label, source, table, id_column, records, key_fields):
    """If this snapshot looks like a republish, move `table`'s rows to the new IDs before
    they're stored. records: (ID, payload, geometry) as stored in raw.record, whose
    payloads carry key_fields and the '_geom' fingerprint. Returns (republish?, rows carried)."""
    fields = ", ".join(f"payload->'{f}'" for f in key_fields)
    known = {row[0]: (_code(row[2:]), row[1]) for row in conn.execute(
        f"""select source_id, payload->>'_geom', {fields} from raw.record
            where source = %s and removed_at is null""", (source,)).fetchall()}
    snapshot = {i: (_code([p.get(f) for f in key_fields]), p.get("_geom")) for i, p, _ in records}
    if not is_republish(known, snapshot):
        return False, 0
    pairs = pair_republished({i: v for i, v in known.items() if i not in snapshot},
                             {i: v for i, v in snapshot.items() if i not in known})
    for new_id, old_id in pairs.items():
        conn.execute(f"""update {table} set {id_column} = %s where {id_column} = %s
                         and not exists (select 1 from {table} where {id_column} = %s)""", (new_id, old_id, new_id))
    print(f"{label}: republish: {len(set(snapshot) - set(known))} of {len(snapshot)} IDs are new; "
          f"carried {len(pairs)} rows over to their new IDs", flush=True)
    return True, len(pairs)


def geom_digest(geom, places=5):
    """A short fingerprint of a geometry's coordinates rounded to `places` decimals
    (5 is about a metre), so a moved line makes a new record version while a
    republish's float noise doesn't. raw.record hashes only the payload, so the
    parsers put this in it."""
    if not geom:
        return None

    def walk(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            return [round(float(x), places) + 0.0 for x in c[:2]]
        return [walk(x) for x in c]

    blob = json.dumps([geom.get("type"), walk(geom.get("coordinates") or [])], separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
