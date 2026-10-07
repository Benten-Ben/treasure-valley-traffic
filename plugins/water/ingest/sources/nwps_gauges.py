"""NOAA's National Water Prediction Service (NWPS): the river and reservoir gauges in the ring.

The NWPS API (api.water.noaa.gov/nwps/v1; robots.txt 404, so no rules) lists
37 gauges in the ring (Oct 7, 2026): the Boise, Payette, Snake, Malheur,
Owyhee and Weiser rivers, creeks, a canal, and three reservoir pools. Observations
are USGS's (Reclamation's at the dams), passed on by NWS; forecasts are the
Northwest River Forecast Center's. Not the USGS Water Data API: its
robots.txt disallows its data paths for us (docs/17 Q14).

NWPS keeps 30 days of observations per gauge and only the latest forecast, so
history exists only if we poll. Each run (every 30 minutes):

1. One list call for the ring's box: every gauge's latest observation and
   its flood category. The latest observation is stored as a reading.
2. A few per-gauge calls, at most MAX_CALLS a run, most urgent first:
   - in a flood (observed or forecast category action or above), the
     forecast every 3 hours;
   - every 7 days, the gauge's metadata (flood categories in stage and flow,
     historic crests, impact statements) and its whole 30-day series (about
     460 KB at a 15-minute gauge). The series fills in the readings between
     list calls: observations arrive in batches 2-3 hours late, so the list
     shows only the last of each batch;
   - otherwise the forecast once a day (a few KB).
   The gauge's metadata record and its forecast record are the clocks: their
   last_seen says when each was last fetched.
3. Flood lifecycles in evt.event: one event per gauge and episode at action
   stage or above, as NWPS categorizes the latest observation. A gauge whose
   category can't be read (not current, out of service, missing from the
   list) keeps its open event: missing data never ends a flood.

Records in raw.record (complete=False, nothing retired):
- `<LID>`: the gauge's metadata, a new version when NWS changes it (the live
  status and image links left out);
- `<LID>@<time>`: one observation, {lid, pe, t, primary, secondary, units}
  as NWPS gives it, whichever call brought it. The PEDTS code `pe` says what
  primary and secondary are (QR discharge, HG stage, HP reservoir pool
  elevation) and `units` in what (kcfs, ft). -999 and -9999 mean missing and
  become null. NWPS's per-value generatedTime is left out;
- `<LID>/forecast`: the latest forecast, a new version per issuance.
"""

import http.client as http_client
import json
import urllib.parse
from datetime import datetime, timedelta, timezone

from ingest import db, events, http

from ..common import RING, in_ring, iso, parse_time, point, store_readings

API = "https://api.water.noaa.gov/nwps/v1"
http.PACE_S.setdefault("api.water.noaa.gov", 2.0)     # robots.txt asks for nothing; we keep 2 s apart

SOURCE = {
    "name": "nwps_gauges",
    "title": "NOAA NWPS river and reservoir gauges in the ring: readings, flood categories, forecasts",
    "url": "https://water.noaa.gov/about/api",
    "access": "open",
    "schedule": "30 minutes",
    "license": "US government work (public domain)",
    "credit": "NOAA National Weather Service (NWPS; Northwest River Forecast Center); "
              "observations courtesy of the U.S. Geological Survey",
    "notes": "One list call for the ring each run, plus at most 4 per-gauge calls: forecasts daily "
             "(every 3 h in a flood), metadata and the 30-day series weekly. Readings and forecasts in "
             "raw.record; flood episodes (action stage and above) in evt.event. Not the USGS Water Data "
             "API, whose robots.txt disallows its data paths.",
}

FLOOD = ("action", "minor", "moderate", "major")              # NWPS's categories at or above action, mildest first
SETTLED = ("no_flooding", "not_defined", "low_threshold")     # categories that end a flood episode
LABEL = {"action": "action stage", "minor": "minor flooding", "moderate": "moderate flooding",
         "major": "major flooding"}
SWEEP_EVERY = timedelta(days=7)
FORECAST_EVERY = timedelta(days=1)
FLOOD_FORECAST_EVERY = timedelta(hours=3)
MAX_CALLS = 4             # per-gauge requests a run, on top of the list call
MISSING = -999            # NWPS writes -999 or -9999 for a missing value
GAUGE_DROP = ("status", "images", "ObservedFloodCategory", "ForecastFloodCategory")   # live or presentation only
CALL_ERRORS = (OSError, http_client.HTTPException, ValueError)    # network, HTTP and JSON errors


def list_url(box=RING):
    return f"{API}/gauges?" + urllib.parse.urlencode(
        {"bbox.xmin": box[0], "bbox.ymin": box[1], "bbox.xmax": box[2], "bbox.ymax": box[3], "srid": "EPSG_4326"})


def gauge_url(lid):
    return f"{API}/gauges/{urllib.parse.quote(lid)}"


def stageflow_url(lid, product=None):
    return gauge_url(lid) + "/stageflow" + (f"/{product}" if product else "")


# --- parsing --------------------------------------------------------------------------

def value(v):
    """A value as a float, or None for NWPS's missing markers (-999, -9999) and blanks."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f <= MISSING else f


def valid_time(text):
    """A validTime as UTC; None for blanks and NWPS's '0001-01-01T00:00:00Z' (no value)."""
    t = parse_time(text)
    return t if t and t.year >= 1900 else None


def reading(lid, pe, units, t, primary, secondary):
    """One observation as stored, the same whichever call brought it; None if it has no value."""
    p, s = value(primary), value(secondary)
    if t is None or (p is None and s is None):
        return None
    return {"lid": lid, "pe": pe or None, "t": iso(t), "primary": p, "secondary": s,
            "units": [(units[0] or None) if p is not None else None, (units[1] or None) if s is not None else None]}


def parse_list(data, box=RING):
    """{LID: gauge} for the listed gauges inside the ring."""
    out = {}
    for g in (data or {}).get("gauges") or []:
        lid = str(g.get("lid") or "").strip().upper()
        if lid and in_ring(g.get("longitude"), g.get("latitude"), box):
            out[lid] = g
    return out


def _status(g, which):
    return ((g or {}).get("status") or {}).get(which) or {}


def category(g, which="observed"):
    """The gauge's flood category as NWPS gives it ('no_flooding', 'minor', 'obs_not_current', ...), or None."""
    return str(_status(g, which).get("floodCategory") or "").strip().lower() or None


def latest_reading(lid, g):
    o = _status(g, "observed")
    return reading(lid, (g.get("pedts") or {}).get("observed"), (o.get("primaryUnit"), o.get("secondaryUnit")),
                   valid_time(o.get("validTime")), o.get("primary"), o.get("secondary"))


def series_readings(lid, product):
    """The readings in a stageflow 'observed' product."""
    product = product or {}
    units = (product.get("primaryUnits"), product.get("secondaryUnits"))
    out = []
    for d in product.get("data") or []:
        r = reading(lid, product.get("pedts"), units, valid_time(d.get("validTime")), d.get("primary"),
                    d.get("secondary"))
        if r:
            out.append(r)
    return out


def forecast_payload(lid, product):
    """A stageflow 'forecast' product as one record: issue time, units and [time, primary, secondary] points."""
    product = product or {}
    issued = valid_time(product.get("issuedTime"))
    points = []
    for d in product.get("data") or []:
        t = valid_time(d.get("validTime"))
        if t:
            points.append([iso(t), value(d.get("primary")), value(d.get("secondary"))])
    return {"lid": lid, "pe": product.get("pedts") or None, "issued": iso(issued) if issued else None,
            "units": [product.get("primaryUnits") or None, product.get("secondaryUnits") or None], "points": points}


def _without(obj, key):
    """obj with every `key` entry removed at any depth (the datums' boilerplate descriptions)."""
    if isinstance(obj, dict):
        return {k: _without(v, key) for k, v in obj.items() if k != key}
    if isinstance(obj, list):
        return [_without(v, key) for v in obj]
    return obj


def gauge_payload(meta):
    """A gauge's metadata as versioned: no live status or image links; the datums without their
    paragraph-long definitions; inundation mapping as a flag and its zero datum, not its links."""
    p = {k: v for k, v in (meta or {}).items() if k not in GAUGE_DROP}
    if "datums" in p:
        p["datums"] = _without(p["datums"], "description")
    if isinstance(p.get("inundation"), dict):
        p["inundation"] = {k: v for k, v in p["inundation"].items() if k in ("enabled", "zeroDatum")}
    return p


# --- what to fetch this run -------------------------------------------------------------

def has_forecast(g):
    return bool(((g or {}).get("pedts") or {}).get("forecast"))


def flooding(g):
    return category(g) in FLOOD or category(g, "forecast") in FLOOD


def plan(gauges, clocks, now, max_calls=MAX_CALLS):
    """This run's per-gauge calls, most urgent first, within max_calls requests:
    [("sweep" | "forecast", LID)]. A sweep (metadata and the 30-day series, with the
    forecast) costs two requests, a forecast one. clocks: {source_id: last_seen} of the
    gauges' metadata (LID) and forecast (LID/forecast) records; the longest-waiting go first."""
    never = datetime.min.replace(tzinfo=timezone.utc)

    def stale(sid, every):
        return clocks.get(sid) is None or now - clocks[sid] >= every

    wanted = []
    for lid, g in gauges.items():
        fc = f"{lid}/forecast"
        if has_forecast(g) and flooding(g) and stale(fc, FLOOD_FORECAST_EVERY):
            wanted.append((0, clocks.get(fc) or never, lid, "forecast"))
        if stale(lid, SWEEP_EVERY):
            wanted.append((1, clocks.get(lid) or never, lid, "sweep"))
        elif has_forecast(g) and stale(fc, FORECAST_EVERY):
            wanted.append((2, clocks.get(fc) or never, lid, "forecast"))
    calls, planned, left = [], set(), max_calls
    for _, _, lid, kind in sorted(wanted):
        cost = 2 if kind == "sweep" else 1
        if lid in planned or cost > left:
            continue
        calls.append((kind, lid))
        planned.add(lid)
        left -= cost
    return calls


def clocks(conn, lids):
    ids = [i for lid in lids for i in (lid, f"{lid}/forecast")]
    return dict(conn.execute(
        """select source_id, max(last_seen) from raw.record
           where source = %s and source_id = any(%s) group by source_id""", (SOURCE["name"], ids)).fetchall())


# --- flood episodes -----------------------------------------------------------------------

def _rank(cat):
    return FLOOD.index(cat) if cat in FLOOD else -1


def flood_row(lid, g, prev, seen_at):
    """The open flood episode at one gauge: continuing `prev` (its id and start) if there is one."""
    cat = category(g)
    start = prev["start"] if prev else (valid_time(_status(g, "observed").get("validTime")) or seen_at)
    peak = max(cat, (prev or {}).get("attributes", {}).get("peak_category"), key=_rank)
    name = g.get("name")
    return {"source_id": prev["source_id"] if prev else f"{lid}:{iso(start)}", "kind": "river_flood",
            "geom": point(g.get("longitude"), g.get("latitude")), "start": start, "end": None, "severity": cat,
            "description": f"{name}: {LABEL[cat]} (NWPS's category for the latest observation)",
            "attributes": {"lid": lid, "name": name, "category": cat, "peak_category": peak}}


def flood_rows(gauges, active, seen_at):
    """evt.event rows for this run. active: {LID: stored row} of open episodes. An episode
    continues while the gauge is at action or above, ends when NWPS gives a settled
    category, and is carried over unchanged when the category can't be read."""
    rows = []
    for lid, prev in active.items():
        g = gauges.get(lid)
        cat = category(g)
        if cat in FLOOD:
            rows.append(flood_row(lid, g, prev, seen_at))
        elif cat not in SETTLED:
            rows.append(prev)
    for lid, g in gauges.items():
        if lid not in active and category(g) in FLOOD:
            rows.append(flood_row(lid, g, None, seen_at))
    return rows


def active_floods(conn):
    """{LID: row as events.upsert takes it, with its stored content_hash} for the open episodes."""
    out = {}
    for sid, kind, geom, start, end, severity, description, attributes, h in conn.execute(
            """select source_id, kind, ST_AsGeoJSON(geom), lower(declared), upper(declared), severity,
                      description, attributes, content_hash
               from evt.event where source = %s and active""", (SOURCE["name"],)).fetchall():
        attributes = attributes or {}
        out[attributes.get("lid") or sid.split(":")[0]] = {
            "source_id": sid, "kind": kind, "geom": json.loads(geom) if geom else None,
            "start": start.astimezone(timezone.utc) if start else None,
            "end": end.astimezone(timezone.utc) if end else None, "severity": severity,
            "description": description, "attributes": attributes, "content_hash": bytes(h)}
    return out


# --- fetching and storing -------------------------------------------------------------

def get_json(url):
    status, body, decision = http.get(url, timeout=90, compressed=True)
    return json.loads(body), len(body), status, decision


def fetch_calls(calls):
    """Run the planned calls. A call that fails (HTTP or network error, bad JSON) is skipped
    and counted, so one broken gauge doesn't cost the run's list readings; a robots.txt
    refusal is not caught. Returns ([(kind, LID, data...)], bytes, errors)."""
    got, nbytes, errors = [], 0, []
    for kind, lid in calls:
        try:
            if kind == "sweep":
                meta, n1, _, _ = get_json(gauge_url(lid))
                series, n2, _, _ = get_json(stageflow_url(lid))
                got.append((kind, lid, meta, series))
                nbytes += n1 + n2
            else:
                fc, n, _, _ = get_json(stageflow_url(lid, "forecast"))
                got.append((kind, lid, fc))
                nbytes += n
        except CALL_ERRORS as err:
            errors.append(f"{kind} {lid}: {type(err).__name__}: {err}"[:200])
    return got, nbytes, errors


def records(gauges, got):
    """(readings, clock records): readings from the list and the series; gauge metadata and
    forecasts, whose upserts move last_seen (the plan's clocks)."""
    geoms = {lid: point(g.get("longitude"), g.get("latitude")) for lid, g in gauges.items()}
    found = [r for r in (latest_reading(lid, g) for lid, g in gauges.items()) if r]
    clock = []
    for item in got:
        lid = item[1]
        if item[0] == "sweep":
            meta, series = item[2], item[3] or {}
            clock.append((lid, gauge_payload(meta), geoms[lid]))
            found += series_readings(lid, series.get("observed"))
            fc = forecast_payload(lid, series.get("forecast"))
            if fc["issued"] or fc["points"]:
                clock.append((f"{lid}/forecast", fc, geoms[lid]))
        else:
            clock.append((f"{lid}/forecast", forecast_payload(lid, item[2]), geoms[lid]))
    return [(f"{r['lid']}@{r['t']}", r, geoms[r["lid"]]) for r in found], clock


def store(conn, fetch_id, seen_at, gauges, got):
    readings, clock = records(gauges, got)
    new, held = store_readings(conn, SOURCE["name"], readings, fetch_id, seen_at)
    clock_new, clock_same, _ = db.upsert_records(conn, SOURCE["name"], clock, fetch_id, seen_at, complete=False)
    floods = events.upsert(conn, SOURCE["name"], flood_rows(gauges, active_floods(conn), seen_at), seen_at)
    return {"gauges": len(gauges), "records": len(readings) + len(clock),
            "reading versions new": new, "readings held": held,
            "gauge and forecast versions new": clock_new, "unchanged": clock_same,
            "in flood": sum(1 for g in gauges.values() if category(g) in FLOOD),
            **{f"floods {k}": v for k, v in floods.items()}}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        data, f.bytes, f.http_status, f.robots = get_json(list_url())
        gauges = parse_list(data)
        if not gauges:
            raise RuntimeError("NWPS listed no gauges in the ring")
        calls = plan(gauges, clocks(conn, gauges), f.started_at)
        got, nbytes, errors = fetch_calls(calls)
        f.bytes += nbytes
        stats = store(conn, f.id, f.started_at, gauges, got)
        f.records = stats["records"]
    stats.update({"calls": len(calls), "call errors": len(errors)})
    for e in errors:
        print(f"nwps_gauges: {e}", flush=True)
    return stats
