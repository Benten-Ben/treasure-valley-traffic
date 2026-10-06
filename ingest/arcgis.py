"""Reading ArcGIS feature layers (ArcGIS Online and ArcGIS Server) for ingestors.

A layer is read in two steps: first the IDs of all its features
(returnIdsOnly), then the features themselves in batches of BATCH by ID range
(where=OBJECTID >= a AND OBJECTID <= b), as Esri JSON in WGS84 (outSR=4326),
with a pause between requests. That doesn't depend on the server's default
order, its page size or whether it honours resultOffset, and it gives a check:
every listed ID must come back, exactly once. A layer that doesn't come back
whole fails the fetch instead of looking smaller (a smaller snapshot would
retire records). robots.txt and crawl-delay are handled by ingest/http.py.
Network errors, 5xx answers and an unreadable robots.txt are retried with
backoff (swidrdc.org sometimes resets connections).

A layer can be cut to a box (and a where clause). Then the ID list is coarser
than the features: on ITD's server, 67 of 19,801 through-lane rows it listed
lie up to 2.3 km outside the box and never come back from a box query (Oct 6,
2026). Listed IDs that a complete answer leaves out are fetched by ID, without
the box, before anything counts as missing; they're harmless extras.

Also here: Esri JSON to GeoJSON, small field cleaners, a line fingerprint for
record versions, and the republish guard (a layer overwritten under new IDs
keeps its rows).
"""

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from . import http

BATCH = 500          # features per request: under every server's maxRecordCount (1,000 or 2,000)
PAUSE_S = 2.0        # between requests to the same layer
RETRY_WAITS_S = (10, 30, 60)
MAX_FEATURES = 50000 # more IDs than this isn't a layer we expect: fail (callers can raise it)
BY_ID_CHUNK = 100    # IDs per by-ID request (keeps the URL short)


def _box(box):
    """Features whose geometry touches the box (west, south, east, north, in degrees); returned whole."""
    if not box:
        return {}
    return {"geometry": ",".join(str(v) for v in box), "geometryType": "esriGeometryEnvelope", "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects"}


def ids_url(layer, where="1=1", box=None):
    """Every object ID the query matches (not limited by the server's page size)."""
    return layer + "/query?" + urllib.parse.urlencode({"where": where, "returnIdsOnly": "true", "f": "json",
                                                        **_box(box)})


def query_url(layer, oid_field, lo, hi, where="1=1", box=None, precision=None):
    """Features with lo <= ID <= hi, every field, geometry in WGS84."""
    clause = f"{oid_field} >= {int(lo)} AND {oid_field} <= {int(hi)}"
    if where and where != "1=1":
        clause = f"({where}) AND {clause}"
    q = {"where": clause, "outFields": "*", "returnGeometry": "true", "outSR": "4326",
         "orderByFields": f"{oid_field} ASC", "f": "json", **_box(box)}
    if precision is not None:
        q["geometryPrecision"] = precision
    return layer + "/query?" + urllib.parse.urlencode(q)


def by_ids_url(layer, ids, precision=None):
    """Features by object ID, without any filter."""
    q = {"objectIds": ",".join(str(int(i)) for i in ids), "outFields": "*", "returnGeometry": "true",
         "outSR": "4326", "f": "json"}
    if precision is not None:
        q["geometryPrecision"] = precision
    return layer + "/query?" + urllib.parse.urlencode(q)


def get_with_retries(url, label, get=None, waits=RETRY_WAITS_S, sleep=time.sleep):
    """http.get, retried with backoff on a network error, a 5xx or an unreadable robots.txt.
    A real robots.txt disallow and other HTTP errors are not retried."""
    get = get or (lambda u: http.get(u, timeout=180))
    for wait in tuple(waits) + (None,):
        try:
            return get(url)
        except (http.RobotsUnavailable, OSError) as err:
            if wait is None or (isinstance(err, urllib.error.HTTPError) and err.code < 500):
                raise
            print(f"{label}: {err}; retrying in {wait} s", flush=True)
            sleep(wait)


def object_id(attrs, oid_field):
    """A feature's object ID (the field name's case varies: OBJECTID, objectid), or None."""
    v = attrs.get(oid_field)
    if v is None:
        v = next((val for k, val in attrs.items() if k.lower() == oid_field.lower()), None)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _exceeded(data):
    return bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))


def fetch_layer(layer, label, *, where="1=1", box=None, batch=BATCH, pause_s=PAUSE_S, precision=None,
                max_features=MAX_FEATURES, stats=None, get=None, sleep=time.sleep):
    """Every feature of a layer (or of its rows matching `where` and touching `box`), each
    once, in ID order, as Esri JSON. Returns (features, bytes, http status, robots decision).
    Raises RuntimeError if the layer doesn't come back whole. stats, if given, gets
    'listed' and 'by_id' (listed rows a range answer left out, fetched by ID)."""
    status, body, decision = get_with_retries(ids_url(layer, where, box), label, get, sleep=sleep)
    data = _parse(body, layer)
    nbytes = len(body)
    oid_field = data.get("objectIdFieldName") or "OBJECTID"
    ids = sorted({int(i) for i in data.get("objectIds") or []})
    if len(ids) > max_features:
        raise RuntimeError(f"{layer} lists {len(ids)} features, more than {max_features}")
    wanted = set(ids)
    got, by_id = {}, []
    pending = ids
    requests, max_requests = 0, 2 * (len(ids) // batch + 1) + 2
    while pending:
        requests += 1
        if requests > max_requests:
            raise RuntimeError(f"{layer}: {len(pending)} of {len(ids)} features still missing after "
                               f"{requests - 1} requests")
        chunk = pending[:batch]
        sleep(pause_s)
        status, body, decision = get_with_retries(
            query_url(layer, oid_field, chunk[0], chunk[-1], where, box, precision), label, get, sleep=sleep)
        data = _parse(body, layer)
        nbytes += len(body)
        for f in data.get("features") or []:
            oid = object_id(f.get("attributes") or {}, oid_field)
            if oid in wanted and oid not in got:
                got[oid] = f
        left = [i for i in chunk if i not in got]
        if left and (not _exceeded(data) or len(left) == len(chunk)):
            # A complete answer that leaves listed IDs out won't bring them next time (with a box,
            # they lie outside it); neither will a server that ignores the query. Try them by ID.
            by_id += left
        queued = set(by_id)
        pending = [i for i in pending if i not in got and i not in queued]
    for k in range(0, len(by_id), BY_ID_CHUNK):
        sleep(pause_s)
        status, body, decision = get_with_retries(by_ids_url(layer, by_id[k:k + BY_ID_CHUNK], precision), label,
                                                  get, sleep=sleep)
        data = _parse(body, layer)
        nbytes += len(body)
        for f in data.get("features") or []:
            oid = object_id(f.get("attributes") or {}, oid_field)
            if oid in wanted and oid not in got:
                got[oid] = f
    lost = [i for i in ids if i not in got]
    if lost:
        raise RuntimeError(f"{layer}: {len(lost)} of the {len(ids)} listed features never came back "
                           f"(e.g. {oid_field} {lost[:5]}); the server ignored the query, or the layer changed "
                           "while we read it")
    if stats is not None:
        stats["listed"] = stats.get("listed", 0) + len(ids)
        stats["by_id"] = stats.get("by_id", 0) + sum(1 for i in by_id if i in got)
    return [got[i] for i in ids], nbytes, status, decision


def _parse(body, layer):
    data = json.loads(body)
    if "error" in data:
        raise RuntimeError(f"ArcGIS error from {layer}: {data['error']}")
    return data


# --- geometry ------------------------------------------------------------------

def point_geojson(geometry):
    """An Esri JSON point ({"x": lon, "y": lat}) as a GeoJSON point, or None if it's
    missing, empty or not a number (Esri writes empty points as NaN or null)."""
    if not geometry:
        return None
    x, y = geometry.get("x"), geometry.get("y")
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isnan(y) or not (-180 <= x <= 180 and -90 <= y <= 90):
        return None
    return {"type": "Point", "coordinates": [round(x, 7), round(y, 7)]}


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
    if "x" in g or "y" in g:
        return point_geojson(g)
    if "rings" in g:
        return {"type": "Polygon", "coordinates": [[list(p[:2]) for p in ring] for ring in g["rings"]]}
    raise ValueError(f"unsupported Esri geometry with keys {sorted(g)}")


def esri_feature(f):
    """An Esri JSON feature as a GeoJSON one: {'type', 'properties', 'geometry'}."""
    return {"type": "Feature", "properties": f.get("attributes") or {}, "geometry": esri_geometry(f.get("geometry"))}


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


# --- field cleaners ----------------------------------------------------------------

def text(v):
    """A field's text with whitespace collapsed; None for blanks (Esri layers often hold ' ')."""
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def yes_no(v):
    """'Y', 'Yes', 'N', 'No' (any case) to True/False; anything else None."""
    t = (text(v) or "").lower()
    return {"y": True, "yes": True, "n": False, "no": False}.get(t)


def number(v):
    """A number field as int when whole, float otherwise; None for blanks."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return int(f) if f.is_integer() else f


def to_int(v):
    """'5' -> 5, 5.0 -> 5; blanks, words, fractions and None -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if not math.isnan(v) and v == int(v) else None
    s = str(v).strip()
    return int(s) if s.isdigit() else None


def to_float(v, places=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return f if places is None else round(f, places) + 0.0       # + 0.0 turns -0.0 into 0.0


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
