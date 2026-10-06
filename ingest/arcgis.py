"""Reading ArcGIS feature layers (ArcGIS Online and ArcGIS Server) for ingestors.

Queries ask for Esri JSON in WGS84 (outSR=4326), every field, in pages of the
layer's maximum record count, with a pause between requests. robots.txt and
crawl-delay are handled by ingest/http.py. A network error or a 5xx is retried
once after a pause (swidrdc.org sometimes resets connections).
"""

import json
import math
import time
import urllib.error
import urllib.parse

from . import http

PAGE = 2000          # the maxRecordCount of every layer we read
PAUSE_S = 2.0        # between requests to the same layer
RETRY_WAIT_S = 10


def query_url(layer, offset=None, page=PAGE, order_by="OBJECTID", where="1=1"):
    q = {"where": where, "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"}
    if offset is not None:          # paging only when the first answer was cut off
        q.update({"orderByFields": order_by, "resultOffset": offset, "resultRecordCount": page})
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


def fetch_layer(layer, label, order_by="OBJECTID", page=PAGE, pause_s=PAUSE_S):
    """Every feature of a layer. Returns (features, bytes, http status, robots decision).

    The first request asks for everything; only if the server says the answer
    was cut off (exceededTransferLimit) does it page through by offset."""
    status, body, decision = get_once_retried(query_url(layer), label)
    data = _parse(body, layer)
    features, nbytes = list(data.get("features") or []), len(body)
    offset = len(features)
    while data.get("exceededTransferLimit"):
        time.sleep(pause_s)
        status, body, decision = get_once_retried(query_url(layer, offset, page, order_by), label)
        data = _parse(body, layer)
        batch = data.get("features") or []
        nbytes += len(body)
        features += batch
        offset += len(batch)
        if not batch:
            break
    return features, nbytes, status, decision


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
