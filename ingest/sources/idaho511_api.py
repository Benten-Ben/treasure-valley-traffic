"""The 511 Idaho API (key from ITD, Oct 6, 2026; ITD is fine with our use; owner OK to collect).

`python3 -m ingest stream idaho511_api` polls the 11 endpoints on their own
cadence, never more than 8 calls in any 60 s (511 allows 10), about 1.6 a
minute on average. The key comes from IDAHO511_API_KEY and is never logged:
errors are masked before they're printed or stored.

For each endpoint, a response whose content changed is archived
(TVT_ARCHIVE/idaho511/<endpoint>/<UTC date>/<endpoint>-<HHMMSS>Z.json.gz; kept
on the server, not published: the republishing OK covers WZDx only), then:

- events, advisories and truck restrictions: versions in raw.record and one
  row per item in evt.event (kinds roadwork, closure, incident, advisory,
  truck_restriction);
- message signs: core.message_sign, and evt.sign_message for what each shows;
- weather stations: core.weather_station, and a row in obs.weather_reading per
  new reading;
- the camera list: versions in raw.record, and the road-weather capture list
  rebuilt (TVT_ARCHIVE/lists/regional-cameras.csv, read by the `regional`
  service) when its views change;
- winter roads, mountain passes, rest areas, runaway-truck ramps and weigh
  stations: versions in raw.record.

Response formats: the API reference kept with the private files (docs/08 §8.6).
"""

import csv
import gzip
import hashlib
import io
import json
import math
import os
import sys
import time
import traceback
from collections import deque
from datetime import datetime, timezone

from .. import db, events, http

BASE = "https://511.idaho.gov/api/"
MAX_CALLS, PER_S = 8, 60
MIN_GAP_S = 2.0
LIST_FILE = os.path.join("lists", "regional-cameras.csv")
# The regional ring (DECISIONS, pending): Oregon DOT views inside it join the road-weather list.
RING = (-117.30, 42.90, -115.60, 44.30)

SOURCE = {
    "name": "idaho511_api",
    "title": "511 Idaho API (all endpoints; see the per-endpoint sources)",
    "url": BASE,
    "access": "api_key",
    "schedule": None,          # a stream: `python3 -m ingest stream idaho511_api`
    "license": "511 Idaho developer terms (key holder); not republished",
    "credit": "Idaho Transportation Department (511 Idaho)",
    "notes": "One service, at most 8 calls a minute; changed responses archived on the server.",
}

# (name, API path, seconds between polls), in priority order.
ENDPOINTS = [
    ("event", "v2/get/event", 120),
    ("messagesigns", "v2/get/messagesigns", 120),
    ("weatherstations", "v2/get/weatherstations", 300),
    ("alerts", "v2/get/alerts", 300),
    ("truckrestrictions", "v2/get/truckrestrictions", 900),
    ("winterroads", "v3/get/winterroads", 900),
    ("cameras", "v2/get/cameras", 3600),
    ("mountainpasses", "v2/get/mountainpasses", 86400),
    ("restareas", "v2/get/restareas", 86400),
    ("truckramps", "v2/get/truckramps", 86400),
    ("weighstations", "v2/get/weighstations", 86400),
]
# Fields that change on every poll without the content changing.
VOLATILE = {"messagesigns": ("LastUpdated",)}
KIND = {"roadwork": "roadwork", "closures": "closure", "accidentsAndIncidents": "incident",
        "generalInfo": "info"}
BLANK = {"", "NO_MESSAGE"}


def source_name(endpoint):
    return f"idaho511_{endpoint}"


def endpoint_source(endpoint):
    return {"name": source_name(endpoint), "title": f"511 Idaho API: {endpoint}", "url": BASE,
            "access": "api_key", "schedule": None, "license": SOURCE["license"], "credit": SOURCE["credit"],
            "notes": "Collected by the idaho511_api stream."}


# --- parsing ----------------------------------------------------------------

def decode_polyline(text, precision=5):
    """Google's encoded polyline -> [[lon, lat], ...]."""
    coords, i, lat, lon, factor = [], 0, 0, 0, 10 ** precision
    while i < len(text):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(text[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append([lon / factor, lat / factor])
    return coords


def point(lat, lon):
    if lat is None or lon is None or (lat == 0 and lon == 0):
        return None
    return {"type": "Point", "coordinates": [lon, lat]}


def geometry(item):
    """A line from EncodedPolyline (a string, or a list of strings), else the item's point."""
    enc = item.get("EncodedPolyline")
    parts = [p for p in (enc if isinstance(enc, list) else [enc]) if isinstance(p, str) and p]
    lines = []
    for p in parts:
        try:
            line = decode_polyline(p)
        except (IndexError, ValueError):
            continue
        if len(line) >= 2:
            lines.append(line)
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    if lines:
        return {"type": "MultiLineString", "coordinates": lines}
    return point(item.get("Latitude"), item.get("Longitude"))


def number(value):
    """511 sends readings as strings; anything that isn't a finite number becomes None."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def epoch(value):
    return datetime.fromtimestamp(value, timezone.utc) if isinstance(value, (int, float)) and value > 0 else None


def event_row(item, kind=None):
    """An event or truck restriction -> an evt.event row."""
    start, end = epoch(item.get("StartDate")), epoch(item.get("PlannedEndDate"))
    if start and end and end < start:
        end = None
    restrictions = {k: v for k, v in (item.get("Restrictions") or {}).items() if v is not None}
    return {
        "source_id": str(item["ID"]),
        "kind": kind or KIND.get(item.get("EventType"), item.get("EventType") or "unknown"),
        "geom": geometry(item),
        "start": start,
        "end": end,
        "severity": item.get("Severity"),
        "description": (item.get("Description") or "").strip() or None,
        "attributes": {
            "ers_id": item.get("SourceId"),          # the same number as WZDx's event IDs
            "organization": item.get("Organization"),
            "event_type": item.get("EventType"),
            "sub_type": item.get("EventSubType"),
            "cause": item.get("Cause"),
            "roadway": item.get("RoadwayName"),
            "direction": item.get("DirectionOfTravel"),
            "lanes_affected": item.get("LanesAffected"),
            "full_closure": item.get("IsFullClosure"),
            "restrictions": restrictions,              # width/height ft, weight tons, speed mph (511's docs)
            "comment": item.get("Comment"),
            "recurrence": item.get("RecurrenceSchedules"),
            "detour_instructions": item.get("DetourInstructions") or None,
            "detour_polyline": item.get("DetourPolyline") or None,
            "reported": epoch(item.get("Reported")),
            "source_updated": epoch(item.get("LastUpdated")),
        },
    }


def alert_row(item):
    return {
        "source_id": str(item["Id"]),
        "kind": "advisory",
        "geom": None,
        "start": epoch(item.get("StartTime")),
        "end": epoch(item.get("EndTime")),
        "severity": "high" if item.get("HighImportance") else None,
        "description": (item.get("Message") or "").strip() or None,
        "attributes": {"notes": item.get("Notes"), "regions": item.get("Regions"),
                       "high_importance": item.get("HighImportance"),
                       "send_notification": item.get("SendNotification"),
                       "source_updated": epoch(item.get("LastUpdated"))},
    }


def reading_row(item):
    """A weather station's current reading -> obs.weather_reading values."""
    n, t = number, lambda v: v if v not in (None, "", "N/A") else None
    return {
        "station_id": str(item["Id"]), "ts": epoch(item.get("LastUpdated")),
        "air_temp_f": n(item.get("AirTemperature")), "surface_temp_f": n(item.get("SurfaceTemperature")),
        "subsurface_temp_f": n(item.get("SubsurfaceTemperature")), "dewpoint_f": n(item.get("DewpointTemperature")),
        "relative_humidity": n(item.get("RelativeHumidity")),
        "wind_speed": n(item.get("WindSpeed")), "wind_direction": t(item.get("WindDirection")),
        "gust_speed": n(item.get("WindSpeedGust")), "gust_direction": t(item.get("WindDirectionGust")),
        "precip_rate": n(item.get("PrecipitationRate")), "precipitation": t(item.get("Precipitation")),
        "precip_1h": n(item.get("Precipitation1H")), "precip_3h": n(item.get("Precipitation3H")),
        "precip_6h": n(item.get("Precipitation6H")), "precip_12h": n(item.get("Precipitation12H")),
        "precip_24h": n(item.get("Precipitation24H")),
        "visibility": n(item.get("Visibility")), "pressure": n(item.get("AtmosphericPressure")),
        "surface_status": t(item.get("SurfaceStatus")), "surface_friction": t(item.get("SurfaceFriction")),
        "ice_percent": n(item.get("IcePercent")), "status": t(item.get("Status")),
    }


def sign_messages(item):
    """The sign's rotating messages, or None when it's blank."""
    msgs = [m.strip() for m in item.get("Messages") or [] if isinstance(m, str)]
    msgs = [m for m in msgs if m not in BLANK]
    return msgs or None


def regional_list(cameras):
    """The road-weather capture list: every enabled view of ITD's road-weather (RWIS)
    cameras statewide, plus Oregon DOT views inside the regional ring."""
    rows = []
    for c in sorted(cameras, key=lambda c: (c.get("SortOrder") or 0, c.get("Id") or 0)):
        lon, lat = c.get("Longitude"), c.get("Latitude")
        in_ring = lon is not None and lat is not None and RING[0] <= lon <= RING[2] and RING[1] <= lat <= RING[3]
        if c.get("Source") == "RWIS":
            why = "ITD road-weather station camera, statewide"
        elif c.get("Source") == "ODOT" and in_ring:
            why = "Oregon DOT camera in the regional ring (I-84 Caldwell-Ontario corridor)"
        else:
            continue
        views = c.get("Views") or []
        for n, v in enumerate(views, 1):
            if v.get("Status") != "Enabled":
                continue
            if c["Source"] == "ODOT":
                name = f"{c.get('Location')} (ODOT)"
            else:
                name = f"{c.get('Location')} (road weather view {n})"
            rows.append((int(v["Id"]), name, why))
    return rows


def list_csv(rows):
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["image_id", "name", "why"])
    w.writerows(rows)
    return out.getvalue().encode()


def content_digest(endpoint, data):
    drop = VOLATILE.get(endpoint, ())
    if drop and isinstance(data, list):
        data = [{k: v for k, v in x.items() if k not in drop} if isinstance(x, dict) else x for x in data]
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).digest()


class Limiter:
    """At most n calls in any `per` seconds, and at least `gap` seconds apart."""

    def __init__(self, n=MAX_CALLS, per=PER_S, gap=MIN_GAP_S, clock=time.monotonic, sleep=time.sleep):
        self.n, self.per, self.gap, self.clock, self.sleep = n, per, gap, clock, sleep
        self.calls = deque()

    def wait(self):
        while True:
            now = self.clock()
            while self.calls and now - self.calls[0] >= self.per:
                self.calls.popleft()
            delay = 0.0
            if len(self.calls) >= self.n:
                delay = self.per - (now - self.calls[0])
            if self.calls:
                delay = max(delay, self.gap - (now - self.calls[-1]))
            if delay <= 0:
                self.calls.append(now)
                return
            self.sleep(delay)


# --- storing ----------------------------------------------------------------

def store_records(conn, endpoint, items, id_key, seen_at, fetch_id):
    new, _, removed = db.upsert_records(
        conn, source_name(endpoint), ((str(x[id_key]), x, geometry(x)) for x in items if x.get(id_key) is not None),
        fetch_id, seen_at)
    return {"versions_added": new, "versions_removed": removed}


def store_events(conn, endpoint, items, seen_at, fetch_id):
    key = "Id" if endpoint == "alerts" else "ID"
    counts = store_records(conn, endpoint, items, key, seen_at, fetch_id)
    if endpoint == "alerts":
        rows = [alert_row(x) for x in items if x.get("Id") is not None]
    else:
        kind = "truck_restriction" if endpoint == "truckrestrictions" else None
        rows = [event_row(x, kind) for x in items if x.get("ID") is not None]
    counts.update(events.upsert(conn, source_name(endpoint), rows, seen_at))
    return counts


def store_signs(conn, items, seen_at):
    shown = changed = 0
    for x in items:
        sid = str(x.get("Id") or "")
        if not sid:
            continue
        geom = point(x.get("Latitude"), x.get("Longitude"))
        conn.execute(
            """insert into core.message_sign (source_id, name, roadway, direction, location, geom, first_seen, last_seen)
               values (%s, %s, %s, %s, %s, case when %s::text is null then null
                                                else ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) end, %s, %s)
               on conflict (source_id) do update set name = excluded.name, roadway = excluded.roadway,
                 direction = excluded.direction, location = excluded.location, geom = excluded.geom,
                 last_seen = excluded.last_seen""",
            (sid, x.get("Name"), x.get("Roadway"), x.get("DirectionOfTravel"), x.get("LocationDescription"),
             json.dumps(geom) if geom else None, json.dumps(geom) if geom else None, seen_at, seen_at))
        msgs = sign_messages(x)
        row = conn.execute(
            "select messages from evt.sign_message where sign_id = %s and upper_inf(observed)", (sid,)).fetchone()
        current = row[0] if row else None
        if current != msgs:
            if current:
                conn.execute("""update evt.sign_message set observed = tstzrange(lower(observed), %s, '[)')
                                where sign_id = %s and upper_inf(observed)""", (seen_at, sid))
            if msgs:
                conn.execute("""insert into evt.sign_message (sign_id, observed, messages)
                                values (%s, tstzrange(%s, null, '[)'), %s)""", (sid, seen_at, msgs))
            changed += 1
        shown += 1 if msgs else 0
    gone = conn.execute(
        """update evt.sign_message m set observed = tstzrange(lower(m.observed), %s, '[)')
           where upper_inf(m.observed) and not (m.sign_id = any(%s))""",
        (seen_at, [str(x.get("Id")) for x in items])).rowcount
    return {"signs": len(items), "showing": shown, "changes": changed + gone}


def store_weather(conn, items, seen_at):
    added = 0
    for x in items:
        if x.get("Id") is None:
            continue
        geom = point(x.get("Latitude"), x.get("Longitude"))
        conn.execute(
            """insert into core.weather_station (source_id, name, geom, camera_source_id, status, first_seen, last_seen)
               values (%s, %s, case when %s::text is null then null
                                    else ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) end, %s, %s, %s, %s)
               on conflict (source_id) do update set name = excluded.name, geom = excluded.geom,
                 camera_source_id = excluded.camera_source_id, status = excluded.status,
                 last_seen = excluded.last_seen""",
            (str(x["Id"]), x.get("Name"), json.dumps(geom) if geom else None, json.dumps(geom) if geom else None,
             x.get("CameraSourceId"), x.get("Status"), seen_at, seen_at))
        r = reading_row(x)
        if r["ts"] is None:
            continue
        cols = list(r)
        added += conn.execute(
            f"insert into obs.weather_reading ({', '.join(cols)}) values ({', '.join('%(' + c + ')s' for c in cols)}) "
            "on conflict (station_id, ts) do nothing", r).rowcount
    return {"stations": len(items), "new_readings": added}


def write_list(root, rows):
    """Rewrite the road-weather capture list if its content changed. Returns True if it did."""
    path = os.path.join(root, LIST_FILE)
    data = list_csv(rows)
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return True


def store(conn, endpoint, data, seen_at, fetch_id=None, root=None):
    items = data if isinstance(data, list) else []
    if endpoint in ("event", "alerts", "truckrestrictions"):
        return store_events(conn, endpoint, items, seen_at, fetch_id)
    if endpoint == "messagesigns":
        return store_signs(conn, items, seen_at)
    if endpoint == "weatherstations":
        return store_weather(conn, items, seen_at)
    counts = store_records(conn, endpoint, items, "Id", seen_at, fetch_id)
    if endpoint == "cameras" and root and items:
        rows = regional_list(items)
        counts["capture_list_views"] = len(rows)
        counts["capture_list_rewritten"] = write_list(root, rows)
    return counts


def heartbeat(conn, endpoint, seen_at):
    """An unchanged response: the current versions were seen again."""
    if endpoint in ("messagesigns", "weatherstations"):
        return 0
    return conn.execute("update raw.record set last_seen = %s where source = %s and removed_at is null",
                        (seen_at, source_name(endpoint))).rowcount


# --- the loop ---------------------------------------------------------------

def archive_path(root, endpoint, when):
    return os.path.join(root, "idaho511", endpoint, when.strftime("%Y-%m-%d"),
                        when.strftime(f"{endpoint}-%H%M%SZ.json.gz"))


def write_archive(root, endpoint, body, when):
    path = archive_path(root, endpoint, when)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, path)


def stream(every=None):
    """Poll the endpoints forever, each on its own cadence (`every` isn't used: the
    cadences are per endpoint). Never raises; errors are logged with the key masked."""
    root = os.environ.get("TVT_ARCHIVE")
    key = os.environ.get("IDAHO511_API_KEY", "").strip()
    if not root:
        sys.exit("set TVT_ARCHIVE: changed responses are archived there")
    if not key:
        sys.exit("set IDAHO511_API_KEY (in deploy/.env on the server; never in the repository)")

    def mask(text):
        return str(text).replace(key, "<key>")

    def fetch(path):
        try:
            return http.get(f"{BASE}{path}?key={key}&format=json", timeout=60, compressed=True)
        except Exception as err:
            raise RuntimeError(mask(f"{type(err).__name__}: {err}")) from None

    print(f"idaho511_api: {len(ENDPOINTS)} endpoints, at most {MAX_CALLS} calls a minute, "
          f"archiving changes to {root}/idaho511", flush=True)
    limiter = Limiter()
    next_due = {name: 0.0 for name, _, _ in ENDPOINTS}
    last, archived, conn = {}, {}, None      # digests stored / archived, per endpoint
    calls = failures = 0
    changed = {}
    report_at = time.time() + 3600
    robots_at = time.time() + 86400
    while True:
        now = time.time()
        due = [e for e in ENDPOINTS if next_due[e[0]] <= now]
        if not due:
            time.sleep(max(1.0, min(next_due.values()) - now))
            continue
        name, path, cadence = due[0]
        limiter.wait()
        next_due[name] = time.time() + cadence
        seen_at = db.now()
        calls += 1
        try:
            status, body, decision = fetch(path)
            data = json.loads(body)
        except Exception as err:
            failures += 1
            print(f"idaho511_api: {name} fetch failed: {mask(err)}", flush=True)
            continue
        digest = content_digest(name, data)
        is_new = last.get(name) != digest
        try:
            if archived.get(name) != digest:
                write_archive(root, name, body, seen_at)
                archived[name] = digest
            if conn is None:
                conn = db.connect()
                db.ensure_source(conn, SOURCE)
                for n, _, _ in ENDPOINTS:
                    db.ensure_source(conn, endpoint_source(n))
                conn.commit()
            with db.Fetch(conn, source_name(name)) as f:
                f.http_status, f.robots, f.bytes = status, decision, len(body)
                f.records = len(data) if isinstance(data, list) else None
                try:
                    if is_new:
                        counts = store(conn, name, data, seen_at, f.id, root)
                        changed[name] = changed.get(name, 0) + 1
                        if name not in last or any(counts.get(k) for k in ("new", "changed", "gone", "changes",
                                                                             "capture_list_rewritten")):
                            print(f"idaho511_api: {name}: " + ", ".join(f"{k} {v}" for k, v in counts.items()),
                                  flush=True)
                    else:
                        heartbeat(conn, name, seen_at)
                except Exception as err:
                    raise RuntimeError(mask(f"{type(err).__name__}: {err}")) from None
            last[name] = digest
        except Exception:
            print(f"idaho511_api: {name}: storing failed (archived):\n{mask(traceback.format_exc())}", flush=True)
            try:
                conn and conn.close()
            except Exception:
                pass
            conn = None
        if time.time() >= report_at:
            print(f"idaho511_api: last hour: {calls} calls, {failures} failed; changed responses: "
                  + (", ".join(f"{k} {v}" for k, v in sorted(changed.items())) or "none"), flush=True)
            calls = failures = 0
            changed = {}
            report_at = time.time() + 3600
        if time.time() >= robots_at:
            http.forget_robots()
            robots_at = time.time() + 86400
