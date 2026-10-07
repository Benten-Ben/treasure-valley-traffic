"""ITD's HPMS road inventory in the valley: through and turn lanes, lane width,
median, shoulders, access control, peak lanes and facility type, with ITD's
road names (docs/09 §9.3).

Open GIS layers (the host has no robots.txt; no license stated; credit ITD),
read with ingest/arcgis.py in WGS84, 2,000 IDs a request, with a pause
between requests: every row whose line touches the valley box, plus the few
just outside it that the server's ID list includes. Plain queries only:
ITD's server times out on spatial statistics queries.

Each HPMS layer is its own raw source, itd_hpms_<kind>. One EventID can
cover several separate pieces of a route (same values, different measures),
so each piece is keyed '<EventID>@<RouteID>:<FromMeasure>' (to 4 decimals of
a mile; migration 0016). OBJECTID, GlobalID and Shape__Length are left out
of the stored record (a republish renumbers them; the length is derived),
and measures are rounded to 5 decimals of a mile (about 2 cm), so a
republish adds no versions. A fingerprint of the line (to about a metre) is
kept in the record instead, so a moved line does make a new version.

core.hpms_section gets one row per (kind, piece) with that layer's values,
coded fields as labels (turn-lane codes stay HPMS's 1-6), and the road name
whose route and measures overlap the row most. Every row a layer lists must
arrive before its rows are stored as a full snapshot.

Field notes, checked Oct 6, 2026:
- RouteID reads like '01990ASH055': the sixth character is the direction, A
  (ascending, the inventory direction) or D (descending), each with its own
  measures; a D row carries its lanes in Descending_Lanes and reads 0 in
  ThroughLanes. On a divided highway the A and D routes are the two
  carriageways. On an undivided one the D route lies on the A route's line
  and its rows are placeholders (SH-55's D row spans the whole highway with
  1 lane; facility type "non-inventory direction"). carriageway_lanes() reads
  the two cases apart.
- Where two routes share a stretch, one of them reads 0 through lanes (all
  three counts): those rows belong to the other route and are skipped in core
  (kept in raw).
- Through lanes look like defaults on ACHD's arterials (Fairview Ave reads
  1+1; it has 5 lanes), and HPMS calls Chinden undivided 1+1 west of Eagle
  Rd: use HPMS on state routes, and as a last resort elsewhere.
- ThroughLanesSource is "unknown" on nearly every row.
"""

import json
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .. import arcgis, db, segment_match

BASE = "https://gisp.itd.idaho.gov/server/rest/services/GDWarehouse"
HPMS = f"{BASE}/HPMS/FeatureServer"
NAMES_LAYER = f"{BASE}/RoadNetwork_Other/FeatureServer/3"
BOX = (-117.05, 43.00, -115.95, 43.85)          # west, south, east, north
BATCH = 2000                                    # IDs per request: ITD's page size

# kind -> HPMS layer id
LAYERS = {"through_lanes": 25, "turn_lanes": 27, "lane_width": 8, "median": 10, "shoulders": 19,
          "access_control": 0, "peak_lanes": 16, "facility_type": 5}

SOURCE = {
    "name": "itd_hpms",
    "title": "ITD HPMS road inventory (lanes, turn lanes, width, median, shoulders, access)",
    "url": HPMS,
    "access": "open",
    "schedule": "30 days",
    "license": "none stated",
    "credit": "Idaho Transportation Department",
    "notes": "Valley box only. Raw versions per layer in itd_hpms_<kind> and itd_hpms_road_names. "
             "Through lanes look like defaults on ACHD arterials.",
}
NAMES_SOURCE = "itd_hpms_road_names"


def layer_source(kind):
    """The raw source a layer's records are versioned under (fetched by itd_hpms)."""
    url = NAMES_LAYER if kind == "road_names" else f"{HPMS}/{LAYERS[kind]}"
    return {"name": f"itd_hpms_{kind}", "title": f"ITD HPMS: {kind.replace('_', ' ')}", "url": url,
            "access": "open", "schedule": None, "license": SOURCE["license"], "credit": SOURCE["credit"],
            "notes": "Collected by the itd_hpms source."}


MATCH_SOURCES = [f"itd_hpms_{k}" for k in LAYERS]

# HPMS coded values -> our labels (HPMS Field Manual; the layers' own domains).
VALUE_SOURCE = {0: "unknown", 1: "windshield_survey", 2: "imagery_manual", 3: "imagery_automatic", 4: "vendor",
                5: "other_agency", 6: "other"}
MEDIAN_TYPE = {1: "none", 2: "unprotected", 3: "curbed", 4: "barrier", 5: "barrier_flexible",
               6: "barrier_semi_rigid", 7: "barrier_rigid"}
SHOULDER_TYPE = {1: "none", 2: "surfaced_asphalt", 3: "surfaced_concrete", 4: "stabilized", 5: "combination",
                 6: "earth", 7: "barrier_curb"}
ACCESS_CONTROL = {1: "full", 2: "partial", 3: "none"}
FACILITY_TYPE = {1: "one_way", 2: "two_way", 4: "ramp", 5: "non_mainline", 6: "non_inventory_direction",
                 7: "planned"}
# Turn lanes stay codes in core.hpms_section (smallint); these are their meanings.
TURN_LANES = {1: "no_intersections", 2: "multiple_exclusive", 3: "continuous_exclusive", 4: "single_exclusive",
              5: "no_exclusive", 6: "no_turns_at_peak"}

VOLATILE = {"OBJECTID", "GlobalID", "Shape__Length"}
MEASURES = ("FromMeasure", "ToMeasure")


def label(codes, value):
    """A code's label; an unknown code keeps its number ('code_9') so nothing is lost."""
    n = arcgis.to_int(value)
    if n is None:
        return None
    return codes.get(n, f"code_{n}")


def payload(props, geom):
    """What's versioned in raw.record: the fields minus renumbered and derived ones,
    measures rounded, plus the line's fingerprint."""
    p = {k: v for k, v in props.items() if k not in VOLATILE}
    for k in MEASURES:
        if k in p:
            p[k] = arcgis.to_float(p[k], 5)
    p["_geom"] = arcgis.geom_digest(geom)
    return p


def piece_key(props):
    """'<EventID>@<RouteID>:<FromMeasure>': one piece of an HPMS event."""
    frm = arcgis.to_float(props.get("FromMeasure"), 4)
    return (f"{arcgis.text(props.get('EventID')) or ''}@{arcgis.text(props.get('RouteID')) or ''}:"
            f"{'' if frm is None else f'{frm:.4f}'}")


def direction(route_id):
    d = (route_id or "")[5:6]
    return d if d in ("A", "D") else None


def expired(props, now):
    to = arcgis.esri_date(props.get("ToDate"))
    return to is not None and to <= now


def zero_lanes(props):
    """A through-lane row with no lanes either way: a stretch shared with another route, which carries them."""
    return not any(arcgis.to_int(props.get(k)) for k in ("ThroughLanes", "Ascending_Lanes", "Descending_Lanes"))


def section(kind, props):
    """Our core.hpms_section row (without geometry and name) for one HPMS record."""
    g = props.get
    row = dict.fromkeys(COLUMNS)
    row.update({
        "kind": kind, "source_id": piece_key(props), "event_id": arcgis.text(g("EventID")),
        "route_id": arcgis.text(g("RouteID")),
        "direction": direction(g("RouteID")),
        "from_mi": arcgis.to_float(g("FromMeasure"), 5), "to_mi": arcgis.to_float(g("ToMeasure"), 5),
        "source_modified": arcgis.esri_date(g("SystemModifyDate")),
    })
    if kind == "through_lanes":
        row.update(through_lanes=arcgis.to_int(g("ThroughLanes")), lanes_ascending=arcgis.to_int(g("Ascending_Lanes")),
                   lanes_descending=arcgis.to_int(g("Descending_Lanes")),
                   value_source=label(VALUE_SOURCE, g("ThroughLanesSource")))
    elif kind == "turn_lanes":
        row.update(turn_lanes_left=arcgis.to_int(g("TurnLanesLeft")), turn_lanes_right=arcgis.to_int(g("TurnLanesRight")))
    elif kind == "lane_width":
        row.update(lane_width_ft=arcgis.to_float(g("LaneWidth")))
    elif kind == "median":
        row.update(median_type=label(MEDIAN_TYPE, g("MedianType")), median_width_ft=arcgis.to_float(g("MedianWidth")),
                   value_source=label(VALUE_SOURCE, g("MedianTypeSource")))
    elif kind == "shoulders":
        row.update(shoulder_type=label(SHOULDER_TYPE, g("ShoulderType")),
                   shoulder_width_left_ft=arcgis.to_float(g("ShoulderWidthLeft")),
                   shoulder_width_right_ft=arcgis.to_float(g("ShoulderWidthRight")))
    elif kind == "access_control":
        row.update(access_control=label(ACCESS_CONTROL, g("AccessControl")))
    elif kind == "peak_lanes":
        row.update(peak_lanes=arcgis.to_int(g("PeakLanes")), counter_peak_lanes=arcgis.to_int(g("CounterPeakLanes")))
    elif kind == "facility_type":
        row.update(facility_type=label(FACILITY_TYPE, g("FacilityType")))
    return row


COLUMNS = ["kind", "source_id", "event_id", "route_id", "direction", "from_mi", "to_mi", "road_name", "through_lanes",
           "lanes_ascending", "lanes_descending", "turn_lanes_left", "turn_lanes_right", "lane_width_ft",
           "median_type", "median_width_ft", "shoulder_type", "shoulder_width_left_ft", "shoulder_width_right_ft",
           "access_control", "peak_lanes", "counter_peak_lanes", "facility_type", "value_source", "source_modified"]


def parse_layer(kind, features, now=None):
    """-> (records, rows, counts). records: (piece key, payload, geometry) for raw.record,
    every piece fetched. rows: {piece key: core row incl. 'geom'} for current, non-zero rows."""
    now = now or datetime.now(timezone.utc)
    records, rows, counts, events, seen = [], {}, Counter(), Counter(), set()
    for f in features:
        props, geom = f.get("properties") or {}, f.get("geometry")
        key = piece_key(props)
        if key in seen:
            counts["duplicate pieces skipped"] += 1
            continue
        seen.add(key)
        if not arcgis.text(props.get("EventID")):
            counts["no EventID"] += 1
        else:
            events[arcgis.text(props.get("EventID"))] += 1
        records.append((key, payload(props, geom), geom))
        if expired(props, now):
            counts["expired"] += 1
            continue
        if kind == "through_lanes" and zero_lanes(props):
            counts["zero-lane rows skipped"] += 1
            continue
        rows[key] = {**section(kind, props), "geom": geom}
    split = sum(1 for n in events.values() if n > 1)
    if split:
        counts["events in several pieces"] = split
    return records, rows, counts


def parse_names(features, now=None):
    """-> (records, index). index: {RouteID: [(from_mi, to_mi, name), ...]}."""
    now = now or datetime.now(timezone.utc)
    records, index, seen = [], defaultdict(list), set()
    for f in features:
        props, geom = f.get("properties") or {}, f.get("geometry")
        key = piece_key(props)
        if key in seen:
            continue
        seen.add(key)
        records.append((key, payload(props, geom), geom))
        name = arcgis.text(props.get("FullRoadName"))
        route = arcgis.text(props.get("RouteID"))
        if name and route and not expired(props, now):
            index[route].append((arcgis.to_float(props.get("FromMeasure"), 5) or 0.0,
                                 arcgis.to_float(props.get("ToMeasure"), 5) or 0.0, name))
    return records, dict(index)


def road_name(index, route_id, from_mi, to_mi):
    """The name on the same route whose measures overlap [from_mi, to_mi] the most
    (or that contains it, for a zero-length row)."""
    lo, hi = sorted((from_mi or 0.0, to_mi or 0.0))
    best, best_overlap = None, None
    for a, b, name in index.get(route_id, ()):
        a, b = sorted((a, b))
        if hi > lo:
            overlap = min(hi, b) - max(lo, a)
            if overlap <= 0:
                continue
        elif a <= lo <= b:
            overlap = 0.0
        else:
            continue
        if best_overlap is None or overlap > best_overlap:
            best, best_overlap = name, overlap
    return best


ONE_WAY_FACILITIES = {"one_way", "ramp"}


def carriageway_lanes(rows, facility=None):
    """Through lanes each way on one stretch, from the HPMS through-lane rows along it
    (dicts with route_id, direction, through_lanes, lanes_ascending, lanes_descending and,
    optionally, share: the best-matching row of each direction wins). facility: the A
    route's facility type there, if known.

    Every state route has a D route in ITD's network, but on an undivided road it's
    drawn on the A route's own line, and its HPMS rows are placeholders for the
    non-inventory direction (SH-55's D row spans the whole highway with 1 lane). So:
    - an A row with lanes both ways describes the whole road, and a D row there is
      ignored;
    - an A row with lanes in its own direction only is one carriageway of a divided
      road, and the D row of the same route gives the other carriageway's lanes; with
      no D row along, the other direction is unknown;
    - on a one-way facility (facility type one-way roadway, or a ramp) there is no
      other direction: 0. A one-way facility whose A row has lanes both ways sets
      conflict.
    Facility type can't tell a divided highway from an undivided one: ITD codes I-84's
    inventory direction, which carries one direction, as a two-way roadway (Oct 6).
    Returns {"ascending", "descending", "divided", "conflict"}.
    """
    def base(r):
        rid = r.get("route_id") or ""
        return rid[:5] + rid[6:]

    def best(rs):
        return sorted(rs, key=lambda r: -(r.get("share") or 0.0))[0] if rs else None

    a = best([r for r in rows if r.get("direction") != "D"])
    ds = [r for r in rows if r.get("direction") == "D"]
    if a is not None:
        ds = [r for r in ds if base(r) == base(a)]
    d = best(ds)
    out = {"ascending": None, "descending": None, "divided": False, "conflict": False}
    d_lanes = (d.get("lanes_descending") or d.get("through_lanes")) if d is not None else None
    if a is None:
        out.update(descending=d_lanes, divided=d is not None)
        return out
    own_only = bool(a.get("lanes_ascending")) and not a.get("lanes_descending")
    out["ascending"] = a.get("lanes_ascending")
    if facility in ONE_WAY_FACILITIES:
        out.update(descending=0, conflict=not own_only)
    elif own_only and d is not None:
        out.update(descending=d_lanes, divided=True)
    elif own_only:
        out["descending"] = None
    else:
        out["descending"] = a.get("lanes_descending")
    return out


# --- fetch and store -----------------------------------------------------------

def _read(layer, label, counts, get, sleep):
    features, nbytes, status, decision = arcgis.fetch_layer(layer, label, box=BOX, batch=BATCH, precision=6,
                                                            stats=counts, get=get, sleep=sleep)
    return [arcgis.esri_feature(f) for f in features], nbytes, status, decision


def fetch_all(fetch, get=None, sleep=time.sleep):
    """Every layer inside the box. Returns ({kind: features}, name features, rows fetched by ID);
    sets fetch.bytes etc."""
    layers, total, counts = {}, 0, {}
    for kind, layer_id in LAYERS.items():
        layers[kind], nbytes, fetch.http_status, fetch.robots = _read(f"{HPMS}/{layer_id}", f"itd_hpms {kind}",
                                                                      counts, get, sleep)
        total += nbytes
    names, nbytes, fetch.http_status, fetch.robots = _read(NAMES_LAYER, "itd_hpms names", counts, get, sleep)
    fetch.bytes = total + nbytes
    return layers, names, counts.get("by_id", 0)


_UPSERT = f"""
insert into core.hpms_section ({", ".join(COLUMNS)}, geom, active, first_seen, last_seen)
values ({", ".join(f"%({c})s" for c in COLUMNS)},
        case when %(geom)s::text is null then null
             else ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) end, true, %(seen)s, %(seen)s)
on conflict (kind, source_id) do update set
  {", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c not in ("kind", "source_id"))},
  geom = excluded.geom, active = true, last_seen = excluded.last_seen
"""


def check_snapshot(conn, layers, name_records):
    """Refuse a snapshot that would retire most of what we hold: an empty layer, or one with
    under half the rows now active (a layer mid-overwrite, a box that stops matching), the
    road names included. layers: {kind: (records, rows, counts)}. Raises before anything
    is written, so the fetch is logged as failed and nothing is retired."""
    for kind, (records, rows, counts) in layers.items():
        db.check_snapshot(conn, "core.hpms_section", "kind = %s", (kind,), len(rows), f"itd_hpms {kind}")
    held = conn.execute("select count(*) from raw.record where source = %s and removed_at is null",
                        (NAMES_SOURCE,)).fetchone()[0]
    if not name_records or len(name_records) < db.SNAPSHOT_MIN_SHARE * held:
        raise RuntimeError(f"itd_hpms names: only {len(name_records)} records against {held} held; "
                           "not taken as a full snapshot")


def store(conn, fetch_id, seen_at, layers, name_features):
    """Raw versions for every layer and the names; core rows; retire rows gone from the box.
    Returns (stats, number of changes)."""
    stats, changed = Counter(), 0
    name_records, index = parse_names(name_features, seen_at)
    parsed = {kind: parse_layer(kind, features, seen_at) for kind, features in layers.items()}
    check_snapshot(conn, parsed, name_records)
    new, unchanged, removed = db.upsert_records(conn, NAMES_SOURCE, name_records, fetch_id, seen_at)
    changed += new + removed
    stats["road names"] = len(name_records)
    all_rows = []
    for kind, (records, rows, counts) in parsed.items():
        new, unchanged, removed = db.upsert_records(conn, f"itd_hpms_{kind}", records, fetch_id, seen_at)
        changed += new + removed
        stats["record versions new"] += new
        stats["unchanged"] += unchanged
        stats["removed"] += removed
        stats[kind] = len(rows)
        stats.update(counts)
        for row in rows.values():
            row["road_name"] = road_name(index, row["route_id"], row["from_mi"], row["to_mi"])
            row["geom"] = json.dumps(row["geom"]) if row["geom"] else None
            row["seen"] = seen_at
            all_rows.append(row)
    with conn.cursor() as cur:
        cur.executemany(_UPSERT, all_rows)
    stats["sections"] = len(all_rows)
    stats["named"] = sum(1 for r in all_rows if r["road_name"])
    stats["retired"] = conn.execute("update core.hpms_section set active = false where active and last_seen < %s",
                                    (seen_at,)).rowcount
    return dict(stats), changed + stats["retired"]


LINES_SQL = """select 'itd_hpms_' || kind as source, source_id, geom, road_name as name
               from core.hpms_section where active"""


def match(conn):
    """Rewrite every HPMS layer's matches to ACHD segments (the caller commits)."""
    stats = segment_match.rematch(conn, MATCH_SOURCES, LINES_SQL)
    total = segment_match.summary(stats)
    through = stats.get("itd_hpms_through_lanes", {})
    total["through-lane lines matched"] = f"{through.get('matched lines', 0)} of {through.get('lines', 0)}"
    return total


def run(conn):
    db.ensure_source(conn, SOURCE)
    for kind in [*LAYERS, "road_names"]:
        db.ensure_source(conn, layer_source(kind))
    with db.Fetch(conn, SOURCE["name"]) as f:
        layers, names, by_id = fetch_all(f)
        stats, changed = store(conn, f.id, f.started_at, layers, names)
        stats["rows just outside the box (fetched by ID)"] = by_id
        f.records = stats["sections"]
        # Inside the fetch: if matching fails, the store rolls back with it and the run is retried.
        if changed or segment_match.stale(conn, MATCH_SOURCES, MATCH_SOURCES + [NAMES_SOURCE]):
            stats.update({f"match {k}": v for k, v in match(conn).items()})
    return stats
