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
import http.client as http_client
import json
import math
import time
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from . import http

BATCH = 500          # IDs per request; keep it at or under the layer's maxRecordCount
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


def _out_fields(fields, oid_field):
    """'*' (every field), or just the named fields plus the object ID (fetch_layer needs it)."""
    if not fields:
        return "*"
    return ",".join(dict.fromkeys([oid_field, *fields]))


def query_url(layer, oid_field, lo, hi, where="1=1", box=None, precision=None, fields=None):
    """Features with lo <= ID <= hi, every field (or only `fields`), geometry in WGS84."""
    clause = f"{oid_field} >= {int(lo)} AND {oid_field} <= {int(hi)}"
    if where and where != "1=1":
        clause = f"({where}) AND {clause}"
    q = {"where": clause, "outFields": _out_fields(fields, oid_field), "returnGeometry": "true", "outSR": "4326",
         "orderByFields": f"{oid_field} ASC", "f": "json", **_box(box)}
    if precision is not None:
        q["geometryPrecision"] = precision
    return layer + "/query?" + urllib.parse.urlencode(q)


def by_ids_url(layer, ids, precision=None, fields=None, oid_field="OBJECTID"):
    """Features by object ID, without any filter."""
    q = {"objectIds": ",".join(str(int(i)) for i in ids), "outFields": _out_fields(fields, oid_field), "returnGeometry": "true",
         "outSR": "4326", "f": "json"}
    if precision is not None:
        q["geometryPrecision"] = precision
    return layer + "/query?" + urllib.parse.urlencode(q)


# A cut-off body (IncompleteRead, or JSON that doesn't parse) is retried like a network error.
RETRYABLE = (http.RobotsUnavailable, OSError, http_client.IncompleteRead, json.JSONDecodeError)


def get_with_retries(url, label, get=None, waits=RETRY_WAITS_S, sleep=time.sleep, parse=None):
    """http.get, retried with backoff on a network error, a 5xx, an unreadable robots.txt or
    a cut-off body. A real robots.txt disallow and other HTTP errors are not retried. With
    parse, returns (status, body, decision, parse(body)), parsing inside the retry."""
    get = get or (lambda u: http.get(u, timeout=180))
    for wait in tuple(waits) + (None,):
        try:
            status, body, decision = get(url)
            if parse is None:
                return status, body, decision
            return status, body, decision, parse(body)
        except RETRYABLE as err:
            if wait is None or (isinstance(err, urllib.error.HTTPError) and err.code < 500):
                raise
            print(f"{label}: {type(err).__name__}: {err}; retrying in {wait} s", flush=True)
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
                max_features=MAX_FEATURES, stats=None, get=None, sleep=time.sleep, fields=None):
    """Every feature of a layer (or of its rows matching `where` and touching `box`), each
    once, in ID order, as Esri JSON. Returns (features, bytes, http status, robots decision).
    Raises RuntimeError if the layer doesn't come back whole. stats, if given, gets
    'listed' and 'by_id' (listed rows a range answer left out, fetched by ID). fields, if
    given, asks for only those fields (plus the object ID): fields we don't keep aren't fetched.

    Answers come in ID order, so a listed ID below the highest one an answer brings
    was left out of it (with a box, it lies outside): it's fetched by ID. IDs above
    it stay pending, since the answer may have been cut at the server's page size;
    a cut answer shrinks the batch to that size. An answer with none of its range's
    IDs sends the range to be fetched by ID, and a by-ID request that brings none of
    its IDs fails the fetch."""
    nbytes, status, decision = 0, None, None

    def fetch(url):
        nonlocal nbytes, status, decision
        status, body, decision, data = get_with_retries(url, label, get, sleep=sleep,
                                                        parse=lambda b: _parse(b, layer))
        nbytes += len(body)
        return data

    data = fetch(ids_url(layer, where, box))
    oid_field = data.get("objectIdFieldName") or "OBJECTID"
    ids = sorted({int(i) for i in data.get("objectIds") or []})
    if len(ids) > max_features:
        raise RuntimeError(f"{layer} lists {len(ids)} features, more than {max_features}")
    wanted = set(ids)
    got, by_id = {}, []
    pending = ids
    requests = 0
    max_requests = 2 * (len(ids) // batch + 1) + 2
    while pending:
        requests += 1
        if requests > max_requests:
            raise RuntimeError(f"{layer}: {len(pending)} of {len(ids)} features still missing after "
                               f"{requests - 1} requests")
        chunk = pending[:batch]
        sleep(pause_s)
        data = fetch(query_url(layer, oid_field, chunk[0], chunk[-1], where, box, precision, fields))
        features = data.get("features") or []
        answered = []
        for f in features:
            oid = object_id(f.get("attributes") or {}, oid_field)
            if oid in wanted:
                got.setdefault(oid, f)
                if chunk[0] <= oid <= chunk[-1]:
                    answered.append(oid)
        if not answered:
            by_id += chunk                       # outside the box, or the server ignored the query
        else:
            top = max(answered)
            by_id += [i for i in chunk if i < top and i not in got]
            if _exceeded(data) and 0 < len(features) < batch:
                batch = len(features)            # the server's page size is smaller: ask for that many
                max_requests = requests + 2 * (len(pending) // batch + 1) + 2
        queued = set(by_id)
        pending = [i for i in pending if i not in got and i not in queued]
    for k in range(0, len(by_id), BY_ID_CHUNK):
        chunk = by_id[k:k + BY_ID_CHUNK]
        sleep(pause_s)
        data = fetch(by_ids_url(layer, chunk, precision, fields, oid_field))
        arrived = 0
        for f in data.get("features") or []:
            oid = object_id(f.get("attributes") or {}, oid_field)
            if oid in chunk and oid not in got:
                got[oid] = f
                arrived += 1
        if not arrived:
            raise RuntimeError(f"{layer}: none of IDs {chunk[:5]}... came back by ID (the server ignored "
                               "the query, or the layer changed while we read it)")
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


def _area(ring):
    """Signed area (shoelace) of a closed ring: negative for a clockwise ring, as Esri writes outer rings."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def _inside(pt, ring):
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _closed_ring(points):
    """A ring's points as (x, y), closed, NaNs and short or flat rings dropped (None)."""
    out = []
    for p in points or []:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        if x == x and y == y:                 # not NaN
            out.append((x, y))
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 and _area(out) != 0 else None


def esri_polygon(rings):
    """Esri polygon rings -> GeoJSON Polygon, or MultiPolygon when there are several outer rings; None if
    no ring is usable.

    Esri lists every ring of a multipart polygon in one array, outer rings clockwise and holes
    counter-clockwise, in any order (forest orders, IDPR areas and fire perimeters all have several
    outer rings with holes). Each hole goes to the smallest outer ring that contains it, tested on a
    few of its own vertices (its middle may hold an island). A "hole" outside every outer ring is kept
    as a polygon of its own, and a layer with no clockwise ring is read as outer rings only. Rings come
    out the RFC 7946 way round (outer rings counter-clockwise). Ported from plugins/lands (Oct 7)."""
    rings = [r for r in (_closed_ring(r) for r in rings or []) if r]
    if not rings:
        return None
    outers = [r for r in rings if _area(r) < 0]
    holes = [r for r in rings if _area(r) > 0]
    if not outers:
        outers, holes = holes, []
    polygons = [[o] for o in outers]
    sizes = [abs(_area(o)) for o in outers]
    for h in holes:
        probes = h[:-1][::max(1, (len(h) - 1) // 8)]
        inside = [i for i, o in enumerate(outers) if any(_inside(p, o) for p in probes)]
        if inside:
            polygons[min(inside, key=lambda i: sizes[i])].append(h)
        else:
            polygons.append([h])
    coords = []
    for poly in polygons:
        outer = poly[0] if _area(poly[0]) > 0 else poly[0][::-1]
        inner = [h if _area(h) < 0 else h[::-1] for h in poly[1:]]
        coords.append([[[x, y] for x, y in r] for r in [outer] + inner])
    return {"type": "Polygon", "coordinates": coords[0]} if len(coords) == 1 else \
        {"type": "MultiPolygon", "coordinates": coords}


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
        return esri_polygon(g["rings"])
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
