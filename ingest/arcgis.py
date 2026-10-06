"""Reading ArcGIS feature layers (ArcGIS Online and ArcGIS Server) for ingestors.

A layer is read in two steps: first the IDs of all its features
(returnIdsOnly), then the features themselves in batches of BATCH by ID range
(where=OBJECTID >= a AND OBJECTID <= b), as Esri JSON in WGS84 (outSR=4326),
with a pause between requests. That doesn't depend on the server's default
order, its page size or whether it honours resultOffset, and it gives a check:
every listed ID must come back, exactly once. A layer that doesn't come back
whole fails the fetch instead of looking smaller (a smaller snapshot would
retire records). robots.txt and crawl-delay are handled by ingest/http.py. A
network error or a 5xx is retried once after a pause (swidrdc.org sometimes
resets connections).
"""

import json
import math
import time
import urllib.error
import urllib.parse

from . import http

BATCH = 500          # features per request: under every server's maxRecordCount (1,000 or 2,000)
PAUSE_S = 2.0        # between requests to the same layer
RETRY_WAIT_S = 10
MAX_FEATURES = 50000 # more IDs than this isn't a layer we expect: fail


def ids_url(layer):
    return layer + "/query?" + urllib.parse.urlencode({"where": "1=1", "returnIdsOnly": "true", "f": "json"})


def query_url(layer, oid_field, lo, hi):
    """Features with lo <= ID <= hi, every field, points in WGS84."""
    q = {"where": f"{oid_field} >= {int(lo)} AND {oid_field} <= {int(hi)}", "outFields": "*",
         "returnGeometry": "true", "outSR": "4326", "orderByFields": f"{oid_field} ASC", "f": "json"}
    return layer + "/query?" + urllib.parse.urlencode(q)


def get_once_retried(url, label, retry_wait_s=RETRY_WAIT_S):
    """http.get, retried once on a network error, a 5xx or an unreadable robots.txt."""
    try:
        return http.get(url, timeout=120)
    except (http.RobotsUnavailable, OSError) as err:
        if isinstance(err, urllib.error.HTTPError) and err.code < 500:
            raise
        print(f"{label}: {err}; retrying once in {retry_wait_s} s", flush=True)
        time.sleep(retry_wait_s)
        return http.get(url, timeout=120)


def object_id(attrs, oid_field):
    """A feature's object ID (the field name's case varies: OBJECTID, objectid), or None."""
    v = attrs.get(oid_field)
    if v is None:
        v = next((val for k, val in attrs.items() if k.lower() == oid_field.lower()), None)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def fetch_layer(layer, label, batch=BATCH, pause_s=PAUSE_S):
    """Every feature of a layer, each once, in ID order. Returns (features, bytes, http status,
    robots decision). Raises RuntimeError if the layer doesn't come back whole."""
    status, body, decision = get_once_retried(ids_url(layer), label)
    data = _parse(body, layer)
    nbytes = len(body)
    oid_field = data.get("objectIdFieldName") or "OBJECTID"
    ids = sorted({int(i) for i in data.get("objectIds") or []})
    if len(ids) > MAX_FEATURES:
        raise RuntimeError(f"{layer} lists {len(ids)} features, more than {MAX_FEATURES}")
    wanted = set(ids)
    got = {}
    pending = ids
    requests, max_requests = 0, 2 * (len(ids) // batch + 1) + 2
    while pending:
        requests += 1
        if requests > max_requests:
            raise RuntimeError(f"{layer}: {len(pending)} of {len(ids)} features still missing after "
                               f"{requests - 1} requests")
        chunk = pending[:batch]
        time.sleep(pause_s)
        status, body, decision = get_once_retried(query_url(layer, oid_field, chunk[0], chunk[-1]), label)
        data = _parse(body, layer)
        nbytes += len(body)
        for f in data.get("features") or []:
            oid = object_id(f.get("attributes") or {}, oid_field)
            if oid in wanted and oid not in got:
                got[oid] = f
        if not any(i in got for i in chunk):
            raise RuntimeError(f"{layer}: none of IDs {chunk[0]}..{chunk[-1]} came back "
                               "(the server ignored the query, or the layer changed while we read it)")
        pending = [i for i in pending if i not in got]
    return [got[i] for i in ids], nbytes, status, decision


def _parse(body, layer):
    data = json.loads(body)
    if "error" in data:
        raise RuntimeError(f"ArcGIS error from {layer}: {data['error']}")
    return data


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
