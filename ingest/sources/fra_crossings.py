"""FRA's highway-rail crossing inventory (Form 6180.71, "Current" dataset) for Ada and Canyon.

One Socrata (SODA) call to data.transportation.gov, dataset m2f8-22s6, filtered
to Idaho's Ada (16001) and Canyon (16027) counties: about 433 crossings, open
and closed, 265 columns, refreshed daily. Public domain (FRA). robots.txt
allows /resource/ with Crawl-delay 1. FRA's history dataset is not loaded
(owner, Oct 6).

Each crossing's record is versioned in raw.record by its DOT crossing number,
without Socrata's ":@computed_region_*" columns (map-region lookups Socrata
adds and recomputes, not FRA data). core.rail_crossing keeps closed crossings,
flagged. Its intersection_id and signal_distance_m are set by the intersection
build (ingest/intersections.py).

Field notes (docs/08 §8.9): FRA's signal, interconnection and preemption
fields are filled only for Boise Valley Railroad crossings; Union Pacific
leaves them blank. FRA's AADT is old on many crossings (years 1970-2024).
"""

import json
import urllib.parse

from .. import db, http, signal_devices

DATASET = "https://data.transportation.gov/resource/m2f8-22s6.json"
COUNTIES = ("16001", "16027")        # Ada, Canyon
LIMIT = 5000

SOURCE = {
    "name": "fra_crossings",
    "title": "FRA highway-rail crossing inventory (Ada and Canyon)",
    "url": "https://data.transportation.gov/Railroads/Crossing-Inventory-Data-Form-71-Current/m2f8-22s6",
    "access": "open",
    "schedule": "7 days",
    "license": "public domain",
    "credit": "Federal Railroad Administration",
    "notes": "One SODA call per run; closed crossings kept and flagged; Socrata's computed-region columns "
             "left out of versioning. FRA's history (vhwz-raag) not loaded.",
}

# wdcode: the highest level of warning device at the crossing. The dataset gives
# FRA's label ('All other Gates', 'Highway signals, bells', ...); FRA's data
# dictionary numbers them 1-9, which older extracts use.
WARNING = {
    "1": "none", "no signs or signals": "none", "none": "none",
    "2": "other_signs", "other signs or signals": "other_signs", "other signs": "other_signs",
    "3": "crossbucks", "crossbucks": "crossbucks",
    "4": "stop_signs", "stop signs": "stop_signs",
    "5": "special", "special active warning devices": "special", "special": "special",
    "6": "highway_signals", "highway signals, bells": "highway_signals",   # highway signals, wigwags, bells
    "7": "flashing_lights", "flashing lights": "flashing_lights",
    "8": "gates", "all other gates": "gates",
    "9": "four_quad_gates", "four quad (full barrier) gates": "four_quad_gates",
}

PREEMPTION = {"1": "Simultaneous", "2": "Advance"}       # the dataset's labels: 'Simultaneous', 'Advanced'


def query_url(offset=0):
    where = f"statecode='16' AND countycode in({','.join(repr(c) for c in COUNTIES)})"
    q = {"$where": where, "$limit": LIMIT, "$offset": offset, "$order": "crossingid"}
    return DATASET + "?" + urllib.parse.urlencode(q, quote_via=urllib.parse.quote, safe="$")


def clean(row):
    """The record as versioned: Socrata's computed-region columns dropped."""
    return {k: v for k, v in row.items() if not k.startswith(":@computed_region")}


def _text(v):
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def _int(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else None


def _real(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _small(v, negative_is_null=True):
    n = _int(v)
    if n is None or (negative_is_null and n < 0) or n > 32767:
        return None
    return n


def _yes(v):
    return {"yes": True, "no": False}.get((_text(v) or "").lower())


def _date(v):
    t = _text(v)
    return t[:10] if t and len(t) >= 10 else None


def plausible(lon, lat):
    """A point near the valley (FRA has a few zero or misplaced coordinates)."""
    return lon is not None and lat is not None and -118.0 <= lon <= -114.0 and 42.0 <= lat <= 45.0


def geometry(row):
    """The geocoded point, else latitude/longitude, else None. Implausible points are dropped."""
    g = row.get("geocoded_lat_long")
    if isinstance(g, dict) and g.get("type") == "Point":
        try:
            lon, lat = float(g["coordinates"][0]), float(g["coordinates"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            lon = lat = None
        if plausible(lon, lat):
            return {"type": "Point", "coordinates": [lon, lat]}
    lon, lat = _real(row.get("longitude")), _real(row.get("latitude"))
    if plausible(lon, lat):
        return {"type": "Point", "coordinates": [lon, lat]}
    return None


def warning(row):
    """FRA's warning-device code as a plain category; from the device counts when the code is blank."""
    code = (_text(row.get("wdcode")) or "").lower()
    if code in WARNING:
        return WARNING[code]
    if "four quad" in code:
        return "four_quad_gates"
    if "gate" in code:
        return "gates"
    if code.startswith("highway signal"):
        return "highway_signals"
    if (_int(row.get("countroadwaygatearms")) or 0) > 0:
        return "gates"
    if (_int(row.get("countflashinglightpair")) or 0) > 0 or (_int(row.get("countmastmountedflashinglight")) or 0) > 0:
        return "flashing_lights"
    if (_int(row.get("numberstopsigns")) or 0) > 0:
        return "stop_signs"
    if (_int(row.get("numbercrossbuckassemblies")) or 0) > 0:
        return "crossbucks"
    return None


def interconnected(row):
    """FRA box III.4.B: 1 not interconnected, 2 for traffic signals, 3 for warning signs.
    True only when tied to traffic signals (what matters for signal preemption)."""
    code = _text(row.get("hwytrafficsgnlinterconncode"))
    label = (_text(row.get("hwytrafficsgnlinterconn")) or "").lower()
    if code == "2" or "traffic signal" in label:
        return True
    if code in ("1", "3") or "not interconnected" in label or "warning sign" in label:
        return False
    return None


def preemption(row):
    code = _text(row.get("hwytrafficsgnlprecode"))
    if code in PREEMPTION:
        return PREEMPTION[code]
    label = (_text(row.get("hwytrafficsgnlpre")) or "").lower()
    if label.startswith("advance"):
        return "Advance"
    if label.startswith("simultaneous"):
        return "Simultaneous"
    return None


def crossing(row):
    """Our row for one FRA record."""
    other = [_int(row.get(k)) for k in ("numberofsidingtracks", "numberofyardtracks", "numberoftransittracks",
                                         "numberofindustrytracks")]
    other = [n for n in other if n is not None and n >= 0]
    aadt_year = _small(row.get("annualaveragedailytrafficyear"))
    return {
        "crossing_id": _text(row.get("crossingid")),
        "railroad": _text(row.get("railroadname")),
        "railroad_code": _text(row.get("railroadcode")),
        "street": _text(row.get("street")),
        "city": _text(row.get("cityname")),
        "county_fips": _text(row.get("countycode")),
        "position": _text(row.get("crossingposition")),
        "public": {"public": True, "private": False}.get((_text(row.get("crossingtype")) or "").lower()),
        "closed": _yes(row.get("crossingclosed")) is True,
        "warning": warning(row),
        "gate_arms": _small(row.get("countroadwaygatearms")),
        "ped_gate_arms": _small(row.get("countpedestriangatearms")),
        "signal_controlled": _yes(row.get("highwaytrafficsignal")),
        "signal_nearby": _yes(row.get("nearbyhighwaytrafficsignals")),
        "interconnected": interconnected(row),
        "preemption": preemption(row),
        "presignals": _yes(row.get("highwaytrafficpresignals")),
        "storage_distance_ft": _real(row.get("storagedistance")),
        "stop_line_distance_ft": _real(row.get("stoplinedistance")),
        "day_through_trains": _small(row.get("totaldaylightthrutrains")),
        "night_through_trains": _small(row.get("totalnighttimethrutrains")),
        "switching_trains": _small(row.get("totalswitchingtrains")),
        "max_timetable_mph": _small(row.get("maximumtimetablespeed")),
        "main_tracks": _small(row.get("numberofmaintracks")),
        "other_tracks": sum(other) if other else None,
        "road_lanes": _small(row.get("trafficlane")),
        "fra_aadt": _int(row.get("annualaveragedailytrafficcount")),
        "fra_aadt_year": aadt_year if aadt_year and aadt_year >= 1900 else None,
        "revision_date": _date(row.get("revisiondate")),
    }


def parse(rows):
    """-> {crossing_id: (record payload, geometry)} for Ada and Canyon rows. If a crossing
    appears twice, the later revision wins."""
    out = {}
    for row in rows:
        if _text(row.get("statecode")) != "16" or _text(row.get("countycode")) not in COUNTIES:
            continue
        cid = _text(row.get("crossingid"))
        if not cid:
            continue
        payload = clean(row)
        if cid in out and (_text(out[cid][0].get("revisiondate")) or "") > (_text(row.get("revisiondate")) or ""):
            continue
        out[cid] = (payload, geometry(row))
    return out


def fetch_rows():
    """All rows, paging only if a page comes back full. Returns (rows, bytes, status, robots)."""
    rows, nbytes, offset = [], 0, 0
    while True:
        status, body, decision = http.get(query_url(offset), timeout=120, compressed=True)
        page = json.loads(body)
        if isinstance(page, dict):
            raise RuntimeError(f"SODA error: {str(page)[:300]}")
        rows += page
        nbytes += len(body)
        if len(page) < LIMIT:
            return rows, nbytes, status, decision
        offset += LIMIT


def store(conn, fetch_id, seen_at, parsed):
    signal_devices.check_snapshot(conn, "core.rail_crossing", "true", (), len(parsed), SOURCE["name"])
    records = [(cid, payload, geom) for cid, (payload, geom) in parsed.items()]
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    cols = list(crossing({}).keys())
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "crossing_id")
    for cid, (payload, geom) in parsed.items():
        row = crossing(payload)
        row_id = conn.execute(
            f"""insert into core.rail_crossing ({', '.join(cols)}, geom, active, first_seen, last_seen)
                values ({', '.join(f'%({c})s' for c in cols)},
                        case when %(geom)s::text is null then null else ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326) end,
                        true, %(seen)s, %(seen)s)
                on conflict (crossing_id) do update set {updates}, geom = excluded.geom, active = true,
                  last_seen = excluded.last_seen
                returning id""",
            {**row, "geom": json.dumps(geom) if geom else None, "seen": seen_at}).fetchone()[0]
        conn.execute(
            """insert into core.source_link (source, source_id, entity, entity_id, method, confidence)
               values (%s, %s, 'rail_crossing', %s, 'fra_crossing_id', 1)
               on conflict (source, source_id, entity) do update set entity_id = excluded.entity_id""",
            (SOURCE["name"], cid, row_id))
    retired = conn.execute("update core.rail_crossing set active = false where active and last_seen < %s",
                           (seen_at,)).rowcount
    rows = [crossing(p) for p, _ in parsed.values()]
    return {"record versions new": new, "unchanged": unchanged, "removed": removed, "crossings": len(parsed),
            "closed": sum(r["closed"] for r in rows),
            "open public at grade": sum(1 for r in rows if not r["closed"] and r["public"]
                                        and r["position"] == "At Grade"),
            "without a point": sum(1 for _, g in parsed.values() if g is None), "retired": retired}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        rows, f.bytes, f.http_status, f.robots = fetch_rows()
        parsed = parse(rows)
        f.records = len(parsed)
        stats = store(conn, f.id, f.started_at, parsed)
    return stats
