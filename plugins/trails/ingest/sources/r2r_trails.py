"""Ridge to Rivers trails and their live condition (City of Boise Parks & Recreation).

The layer behind Ridge to Rivers' official map: 271 foothills trails (Oct 7, 2026),
each with R2R's own `Condition` (seven values: dry, frozen, three muddy ones, closed,
not evaluated), the date staff set it, and the trail's rules (uses, dogs, e-bikes,
horses). The layer keeps only the current state, so history exists only if we poll;
a wet season of these labels is the training set for the mud model (ch. 17 Q32).
Catalog: docs/sources/trails.md, "Ridge to Rivers trails and live conditions".

Every 30 minutes the layer's description (?f=json, about 36 KB) is read. If its edit
dates, fields and condition values match the last full read, and that read is under
FULL_READ_EVERY old, nothing else is fetched and the current versions are marked seen.
Otherwise every trail is read (two requests, about 1 MB with lines) and:

1. each trail's version goes to raw.record, keyed by GlobalID (TrailID repeats: 177
   distinct values over 271 rows, some blank), without the staff-name fields;
2. each trail's current condition is one evt.event row (kind trail_condition), keyed by
   trail, ConditionDate and state. When staff set a new status the old row ends (its
   `observed` closes) and a new one starts, so evt.event holds every trail's run of
   conditions: the muddy and closed intervals, and every label staff set.

ConditionDate is Boise wall-clock time stored as if it were UTC: on Oct 7, 227 of 271
rows had last_edited_date (editor tracking, true UTC) exactly 6.00 h after it (MDT), and
its "UTC" hours cluster at 7 and 15-16, office hours in Boise. The event's declared start
is the true time; attributes keep the raw value and the wall-clock reading.

R2R's condition is advice, not a closure order: label it as R2R's. Query only.
"""

import time
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

from ingest import arcgis, db, events

from .. import layers

LAYER = ("https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/"
         "Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer/2")
FULL_READ_EVERY = timedelta(days=1)     # read even when the edit date hasn't moved
MAX_TRAILS = 2000                       # the layer's maxRecordCount; more isn't the layer we know
PRECISION = 6                           # decimal degrees in the lines (0.1 m)
BOISE = ZoneInfo("America/Boise")

SOURCE = {
    "name": "r2r_trails",
    "title": "Ridge to Rivers trails and conditions (City of Boise)",
    "url": LAYER,
    "access": "open",
    "schedule": "30 minutes",
    "license": "none stated (City of Boise disclaimer only)",
    "credit": "City of Boise Parks & Recreation (Ridge to Rivers)",
    "notes": "Layer description every 30 min; the trails are read only when its edit dates or schema change "
             "(or daily). Versions in raw.record by GlobalID without staff names; each trail's condition runs "
             "in evt.event (kind trail_condition). Courtesy note to the City due before republishing rows.",
}

# Fields the parse depends on: a layer without them fails the fetch instead of reading as blanks.
REQUIRED = ("GlobalID", "TrailName", "Condition", "ConditionDate")
# Staff names (editor tracking and the Editor field) and the derived length: never stored.
DROP = layers.STAFF_FIELDS | {"objectid", "shape__length"}

# R2R's seven labels (the layer's 'BPR Trail Condition' domain, Oct 7, 2026) by how they start.
# Order matters: "frozen early" before "frozen", "dry at start" before "dry".
STATES = (
    ("closed", "closed"),
    ("not evaluated", "not_evaluated"),
    ("frozen early", "frozen_then_muddy"),     # "Frozen early then muddy - BE OFF THE TRAIL BEFORE IT THAWS ..."
    ("frozen", "frozen"),                      # "Frozen/snow covered - Enjoy"
    ("dry at start", "muddy_further_out"),     # "Dry at start but could be muddy further out - turn around ..."
    ("dry", "dry"),                            # "Dry / Tacky - Enjoy"
    ("muddy", "muddy"),                        # "Muddy - DO NOT USE"
)
# R2R's own advice in each label, as a level the map can use without knowing the labels.
SEVERITY = {"dry": "open", "frozen": "open", "muddy_further_out": "caution", "frozen_then_muddy": "caution",
            "muddy": "do_not_use", "closed": "closed"}


def condition_state(label):
    """R2R's label -> a short state; 'unset' for a blank, 'other' for a label we don't know."""
    t = " ".join((label or "").replace("–", "-").replace("—", "-").lower().split())
    if not t:
        return "unset"
    for prefix, state in STATES:
        if t.startswith(prefix):
            return state
    return "other"


def wall_time(ms):
    """ConditionDate (Boise wall-clock time stored as UTC) -> (true UTC datetime, the wall-clock
    reading as ISO text), or (None, None)."""
    stamp = arcgis.esri_date(ms)
    if stamp is None:
        return None, None
    wall = stamp.replace(tzinfo=None)
    return wall.replace(tzinfo=BOISE).astimezone(timezone.utc), wall.isoformat()


def trail_key(attrs):
    """GlobalID (lower case, no braces); 'oid:<OBJECTID>' for a row without one; None if neither."""
    gid = (arcgis.text(attrs.get("GlobalID")) or "").strip("{}").lower()
    if gid:
        return gid
    oid = arcgis.object_id(attrs, "OBJECTID")
    return None if oid is None else f"oid:{oid}"


def payload(attrs, geom):
    """The record as versioned: every field but staff names, OBJECTID and the derived length,
    plus a fingerprint of the line (raw.record hashes only the payload)."""
    out = {k: v for k, v in attrs.items() if k.lower() not in DROP}
    out["_geom"] = arcgis.geom_digest(geom)
    return out


def condition_row(key, attrs, geom):
    """The evt.event row for a trail's current condition."""
    label = arcgis.text(attrs.get("Condition"))
    state = condition_state(label)
    raw_ms = attrs.get("ConditionDate")
    set_at, wall = wall_time(raw_ms)
    attributes = {
        "trail": key,
        "trail_name": arcgis.text(attrs.get("TrailName")),
        "trail_number": arcgis.text(attrs.get("TrailID")),
        "name": arcgis.text(attrs.get("Name")),
        "system": arcgis.text(attrs.get("SystemName")),
        "area": arcgis.text(attrs.get("TrailSubSystem")),
        "state": state,
        "note": arcgis.text(attrs.get("ConditionNotes")),
        "condition_date_raw": raw_ms,
        "condition_set_local": wall,
        "all_weather": arcgis.yes_no(attrs.get("AllWeather")),
        "use": arcgis.text(attrs.get("R2R_Use")),
    }
    return {
        "source_id": f"{key}/{raw_ms if raw_ms is not None else '-'}/{state}",
        "kind": "trail_condition",
        "geom": geom,
        "start": set_at,
        "end": None,
        "severity": SEVERITY.get(state),
        "description": label,
        "attributes": attributes,
    }


def parse(features):
    """Esri JSON features -> (records, condition rows, stats). Rows wholly outside the ring are
    dropped; a GlobalID seen twice keeps the later row."""
    records, rows = {}, {}
    stats = {"outside the ring": 0, "without a key": 0, "without a line": 0}
    for f in features:
        attrs = f.get("attributes") or {}
        geom = arcgis.esri_geometry(f.get("geometry"))
        if not layers.in_ring(geom):
            stats["outside the ring"] += 1
            continue
        key = trail_key(attrs)
        if key is None:
            stats["without a key"] += 1
            continue
        if geom is None:
            stats["without a line"] += 1
        records[key] = (key, payload(attrs, geom), geom)
        rows[key] = condition_row(key, attrs, geom)
    return list(records.values()), list(rows.values()), stats


def store(conn, fetch_id, seen_at, records, rows):
    """Write one full read: versions (complete snapshot) and the condition runs."""
    layers.check_snapshot(conn, SOURCE["name"], len(records), SOURCE["name"])
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at, complete=True)
    counts = events.upsert(conn, SOURCE["name"], rows, seen_at)
    by_state = {}
    for r in rows:
        by_state[r["attributes"]["state"]] = by_state.get(r["attributes"]["state"], 0) + 1
    return {"trails": len(records), "versions new": new, "unchanged": unchanged, "removed": removed,
            "conditions new": counts["new"], "changed": counts["changed"], "ended": counts["gone"],
            **{f"now {k}": v for k, v in sorted(by_state.items())}}


def run(conn, get=layers.get, sleep=time.sleep):
    db.ensure_source(conn, SOURCE)
    name = SOURCE["name"]
    with db.Fetch(conn, name) as f:
        f.http_status, meta, f.robots, f.bytes = layers.describe(LAYER, name, get, sleep)
        if missing := layers.missing_fields(meta, REQUIRED):
            raise RuntimeError(f"{name}: fields no longer in the layer: {', '.join(missing)}")
        sig = layers.signature(meta, domains=("Condition",))
        if layers.unchanged(sig, layers.stored_signature(conn, name), f.started_at, FULL_READ_EVERY):
            layers.save_signature(conn, name, sig, read=False)
            f.records = 0
            seen = layers.heartbeat(conn, name, f.started_at)
            edited = arcgis.esri_date(sig["last_edit"])
            return {"unchanged since": edited.isoformat(timespec="minutes"), "versions confirmed": seen}
        features, nbytes, f.http_status, f.robots = arcgis.fetch_layer(
            LAYER, name, precision=PRECISION, max_features=MAX_TRAILS, get=get, sleep=sleep)
        f.bytes += nbytes
        records, rows, parse_stats = parse(features)
        f.records = len(records)
        stats = store(conn, f.id, f.started_at, records, rows)
        layers.save_signature(conn, name, sig, read=True)
    return {**stats, **{k: v for k, v in parse_stats.items() if v}}
