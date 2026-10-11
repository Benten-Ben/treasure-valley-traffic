"""ACHD's Official Bicycle Facility Network (Ada County): ACHD's field-checked inventory of the
bike network, with the one curb-to-curb width source we have (landscape sprint, package P7b;
the owner brought it forward on Oct 8, 2026, decision 11).

Open GIS layer on gis.achdidaho.org (the host answers robots.txt with a 404: no rules,
re-checked through ingest/http.py on Oct 11, 2026; never more.achdidaho.org), listed in ACHD's
open-data hub. About 3,930 lines over 1,080 miles of arterials, collectors, local bikeways and
pathways, read with ingest/arcgis.py: the ID list, then two pages of 2,000 (the layer's
maxRecordCount), a pause between requests. No license is stated: the hub's licence field holds a
disclaimer ("general reference purposes only and should not be used for planning
determinations"), so the data is internal and credited to ACHD. Catalog: docs/sources/cycling.md,
"ACHD Official Bicycle Facility Network".

Per record: TotalPavement (curb to curb) and TotalROW, in feet; TotalLanes (both directions plus
centre turn lanes); ACHD's level of traffic stress (LTS, ACHD's assessment, never ours); and per
direction (ACHD's EBNB and WBSB sides) the facility and its width, the adjacent travel lane's
width, the lane count, the pavement edge, right-turn lanes, parking and its width, markings, and
the buffer and its width. Widths are text in the layer ('5', '.5', 'N/A', 'Varies'): they're read
as feet, 'N/A' and blanks as null, a 'Varies' buffer as null with a flag. ACHD's words become short
codes (roads 0004 lists them); a word we haven't seen becomes 'other' and is counted in the stats.
Volume and YrBuilt stay text ('+3000', '750 - 1500'; '2023', 'TBD'). The sides are the street's two
sides: on a one-way street the side against the traffic reads 'N/A' for its direction and lane
count (0 lanes here) but keeps its edge and parking.

Field notes, checked Oct 11, 2026 (3,932 records):
- No GlobalID, and OBJECTIDs ran 3929-7869: a reload renumbers them. Records are keyed by OBJECTID,
  and a run that finds most IDs new carries the rows over (by LocationID and street, then the line;
  arcgis.carry_over). LocationID ('BMP0458') repeats across pieces (3,148 values).
- The layer has no edit dates (no editingInfo). The hub's DCAT entry has a modified date, but the
  feed lists the whole hub on another host (Crawl-delay 60), so the change check is a content hash
  of the read itself: the whole layer is three requests (about 8 MB). An unchanged layer only
  confirms the versions it holds.
- 1,282 records have no per-direction data (not field-checked: FieldVerified 'N/A'); 1,429 have no
  TotalPavement. Pathways (FuncClass or Street 'Pathway': 183) and roads not built yet (Street or
  BMPStatus 'New Road': 348 more) are kept but never matched to ACHD's road segments.
- Lanes, bike lanes, buffers and parking add up to TotalPavement within 2 ft on most field-checked
  records, plus about 12 ft where TotalLanes counts a centre turn lane: TotalPavement is curb to
  curb, and bike lanes lie inside it; raised bike lanes, cycle tracks and multi-use paths don't.
- MarkingLocation's meaning is unclear ⚠️ (it isn't the bike lane plus parking): kept in attributes.
- Free text: Comments and FieldNotes go only to roads.bike_facility_note (and raw.record), never
  into roads.bike_facility, its views, exports, tiles or cards.

Each run (monthly) stores the versions in raw.record (without OBJECTID and Shape__Length; the
lengths rounded), the current state in roads.bike_facility, the notes, and then matches the street
records to ACHD's road segments with core's line matcher under roads' rule
(segment_match.METHODS["buffer15_bearing20"], loops off), dropping matches whose street names
disagree, into roads.bike_facility_match. The match reruns when the records change, and when
ACHD's segments have changed since the last match (also from achd_roads' run, through
segment_match.rematch_all). roads.segment_bike_xsection gives P7 each matched ACHD segment's
cross-section in metres, forward and backward as the segment is drawn.
"""

import hashlib
import json
import time
from collections import Counter

from ingest import arcgis, db, linematch
from .. import segment_match

LAYER = "https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Official_Bicycle_Facility_Network/FeatureServer/1"
HUB = "https://public-open-data-achd.hub.arcgis.com/"

SOURCE = {
    "name": "achd_bike_network",
    "title": "ACHD Official Bicycle Facility Network (curb-to-curb widths, bike facilities, ACHD's LTS)",
    "url": LAYER,
    "access": "open",
    "schedule": "30 days",
    "license": "none stated (disclaimer: general reference only, not for planning determinations)",
    "credit": "Ada County Highway District",
    "notes": f"Ada only; on ACHD's open-data hub ({HUB}). Internal use. Keyed by OBJECTID (renumbered by a "
             "reload: carried over). Widths in feet. Comments and FieldNotes stay internal.",
}

BATCH = 2000                  # the layer's maxRecordCount: two pages
MAX_FEATURES = 10000          # 3,932 on Oct 11, 2026; far more would be a different layer
PRECISION = 6                 # decimal degrees in the lines (0.1 m)
CONTENT_VERSION = 1           # bump when the parse changes, so the next run stores in full

SIDES = ("EBNB", "WBSB")
INTERNAL = ("Comments", "FieldNotes")              # free text: roads.bike_facility_note only
VOLATILE = {"OBJECTID", "Shape__Length"}            # the key, and the length the server derives
ROUNDED = {"LengthMiles": 5, "BikeLnMiles": 5, "Lengthft": 1}
# Fields the parse depends on: a layer without them fails the run instead of reading as blanks.
REQUIRED = ("OBJECTID", "LocationID", "Street", "FuncClass", "TotalPavement", "TotalROW", "TotalLanes",
            *(f"{f}{s}" for s in SIDES for f in ("FacilityDirection", "FacilityType", "FacilityWidth",
                                                 "AdjLaneWidth", "LaneCt", "ParkingWidth", "BufferWidth")))
# Carrying rows over a reload: records are told apart by these, then by their line.
REPUBLISH_KEY = ("LocationID", "Street")
NO_VALUE = {"", "n/a", "<null>", "null"}

# ACHD's words -> our codes (roads 0004). Matched case- and space-insensitively.
FACILITY = {"mixed traffic": "mixed_traffic", "no facility": "no_facility", "bike lane": "bike_lane",
            "buffered bike lane": "buffered_bike_lane", "protected bike lane": "protected_bike_lane",
            "protected bike lanes": "protected_bike_lane", "raised bike lane": "raised_bike_lane",
            "cycle track": "cycle_track", "multi-use path": "multi_use_path", "multi-use pathway": "multi_use_path"}
EDGE = {"curb & gutter": "curb_gutter", "curb no gutter": "curb", "shoulder": "shoulder"}
RIGHT_TURN = {"rt turn": "turn_lane", "thrurtoutside": "through_right_outside", "thrurtshared": "through_right_shared"}
PARKING = {"none": "none", "parallel": "parallel", "angled": "angled"}
MARKINGS = {"yes": "yes", "no": "no", "needs corrected": "needs_correcting", "ncorrect": "needs_correcting"}
BUFFER = {"none": "none", "painted": "painted", "landscaping": "landscaping", "extruded curb": "extruded_curb",
          "jersey barrier": "jersey_barrier", "delineator": "delineator", "parking": "parking", "other": "other"}
DIRECTION = {"EBNB": {"northbound": "N", "eastbound": "E"}, "WBSB": {"southbound": "S", "westbound": "W"}}

# Typed columns read these fields; every other field (but the internal and volatile ones) goes
# into attributes as published.
TYPED = {"LocationID", "Street", "City", "Agency", "FuncClass", "ExistingType", "LTS", "BikeLegend", "Speed",
         "SpeedField", "Volume", "YrBuilt", "YearAdded", "YearUpdated", "FieldVerified", "TotalLanes",
         "TotalPavement", "TotalROW",
         *(f"{f}{s}" for s in SIDES for f in ("FacilityDirection", "FacilityType", "FacilityWidth", "AdjLaneWidth",
                                              "LaneCt", "PavementEdge", "RightTurn", "Parking", "ParkingWidth",
                                              "PavementMarkings", "BufferType", "BufferWidth"))}


# --- cleaning ------------------------------------------------------------------------

def value(v):
    """A field's text, whitespace collapsed; None for blanks, 'N/A' and '<Null>'."""
    t = arcgis.text(v)
    return None if t is None or t.lower() in NO_VALUE else t


def feet(v):
    """A width in feet: '5' -> 5.0, '.5' -> 0.5, 12 -> 12.0; None for blanks, 'N/A', 'Varies',
    zero, negatives and anything else."""
    t = value(v)
    if t is None:
        return None
    f = arcgis.to_float(t.rstrip("'").strip())
    return f if f is not None and 0 < f < 1000 else None


def unreadable_width(v):
    """True for a width that's there but isn't a number, 'N/A' or 'Varies' (counted in the stats)."""
    t = value(v)
    return t is not None and t.lower() != "varies" and feet(v) is None


def code(table, v, counts, field):
    """ACHD's word -> our code; None for blanks and 'N/A'; 'other' (counted) for a word we don't know."""
    t = value(v)
    if t is None:
        return None
    c = table.get(" ".join(t.lower().split()))
    if c is None:
        counts[f"unknown {field} values"] += 1
        return "other"
    return c


def small_int(v, lo=None, hi=None):
    n = arcgis.to_int(value(v) if isinstance(v, str) else v)
    if n is None or (lo is not None and n < lo) or (hi is not None and n > hi):
        return None
    return n


def kind(props):
    """'path' (FuncClass or Street 'Pathway'), 'planned' (a road not built yet: Street or BMPStatus
    'New Road'), else 'street'. Only streets are matched to ACHD's road segments."""
    words = {(value(props.get(k)) or "").lower() for k in ("FuncClass", "Street")}
    if "pathway" in words:
        return "path"
    if "new road" in words or (value(props.get("BMPStatus")) or "").lower() == "new road":
        return "planned"
    return "street"


def side(props, s, counts):
    """One direction's columns (prefix ebnb_ or wbsb_)."""
    g = props.get
    p = s.lower() + "_"
    direction_text = value(g(f"FacilityDirection{s}"))
    direction = DIRECTION[s].get((direction_text or "").lower())
    if direction_text and not direction:
        counts[f"unknown FacilityDirection{s} values"] += 1
    lanes = small_int(g(f"LaneCt{s}"), 0, 20)
    # 'N/A' for the direction (not a blank): no traffic that way, a one-way street's other side.
    if lanes is None and (arcgis.text(g(f"FacilityDirection{s}")) or "").lower() == "n/a":
        lanes = 0
    buffer_text = value(g(f"BufferWidth{s}"))
    for f in ("FacilityWidth", "AdjLaneWidth", "ParkingWidth", "BufferWidth"):
        if unreadable_width(g(f"{f}{s}")):
            counts["unreadable widths"] += 1
    return {
        p + "direction": direction,
        p + "facility": code(FACILITY, g(f"FacilityType{s}"), counts, "facility"),
        p + "facility_w_ft": feet(g(f"FacilityWidth{s}")),
        p + "lane_w_ft": feet(g(f"AdjLaneWidth{s}")),
        p + "lanes": lanes,
        p + "edge": code(EDGE, g(f"PavementEdge{s}"), counts, "edge"),
        p + "right_turn": code(RIGHT_TURN, g(f"RightTurn{s}"), counts, "right turn"),
        p + "parking": code(PARKING, g(f"Parking{s}"), counts, "parking"),
        p + "parking_w_ft": feet(g(f"ParkingWidth{s}")),
        p + "markings": code(MARKINGS, g(f"PavementMarkings{s}"), counts, "markings"),
        p + "buffer": code(BUFFER, g(f"BufferType{s}"), counts, "buffer"),
        p + "buffer_w_ft": feet(g(f"BufferWidth{s}")),
        p + "buffer_varies": (buffer_text or "").lower() == "varies",
    }


def facility(props, counts=None):
    """Our roads.bike_facility row (without geometry and object_id) for one record."""
    counts = Counter() if counts is None else counts
    g = props.get
    verified = (value(g("FieldVerified")) or "").lower()
    row = {
        "location_id": value(g("LocationID")),
        "kind": kind(props),
        "street": value(g("Street")),
        "city": value(g("City")),
        "agency": value(g("Agency")),
        "func_class": value(g("FuncClass")),
        "existing_type": value(g("ExistingType")),
        "lts": small_int(g("LTS"), 1, 4),
        "bike_legend": value(g("BikeLegend")),
        "speed_mph": small_int(g("Speed"), 1, 99),
        "speed_field_mph": small_int(g("SpeedField"), 1, 99),
        "volume": value(g("Volume")),
        "yr_built": value(g("YrBuilt")),
        "year_added": small_int(g("YearAdded"), 1900, 2100),
        "year_updated": value(g("YearUpdated")),
        "field_verified": True if verified == "verified" else (False if arcgis.text(g("FieldVerified")) else None),
        "total_lanes": small_int(g("TotalLanes"), 0, 30),
        "total_pavement_ft": feet(g("TotalPavement")),
        "total_row_ft": feet(g("TotalROW")),
    }
    for s in SIDES:
        row.update(side(props, s, counts))
    row["attributes"] = {k: v for k, v in ((k, attribute(k, v)) for k, v in props.items()
                                           if k not in TYPED and k not in INTERNAL and k not in VOLATILE)
                         if v is not None}
    return row


def attribute(k, v):
    """A field for attributes: text cleaned (blanks and '<Null>' dropped), the lengths rounded."""
    if isinstance(v, str):
        t = arcgis.text(v)
        return None if t is None or t.lower() == "<null>" else t
    if k in ROUNDED:
        return arcgis.to_float(v, ROUNDED[k])
    return v


def note(props):
    """(comments, field_notes), each None when blank: internal, roads.bike_facility_note only."""
    return value(props.get("Comments")), value(props.get("FieldNotes"))


def payload(props, geom):
    """What raw.record versions: every field but the key and the derived length, the lengths
    rounded, the free text included (raw.record is internal), and a fingerprint of the line."""
    p = {k: (arcgis.to_float(v, ROUNDED[k]) if k in ROUNDED else v) for k, v in props.items() if k not in VOLATILE}
    p["_geom"] = arcgis.geom_digest(geom)
    return p


def missing_fields(features):
    """REQUIRED fields absent from the layer's records (Esri JSON lists every field, null or not)."""
    present = set()
    for f in features[:50]:
        present |= set((f.get("properties") or {}).keys())
    return [k for k in REQUIRED if k not in present] if features else []


def parse(features):
    """GeoJSON features -> (records, rows, notes, counts). records: (OBJECTID as text, payload,
    geometry) for raw.record; rows: {OBJECTID: row incl. 'geom'}; notes: {OBJECTID: (comments,
    field_notes)} for the records that have any."""
    records, rows, notes, counts = [], {}, {}, Counter()
    for f in features:
        props, geom = f.get("properties") or {}, f.get("geometry")
        oid = arcgis.object_id(props, "OBJECTID")
        if oid is None:
            counts["no OBJECTID"] += 1
            continue
        if oid in rows:
            counts["duplicate OBJECTIDs skipped"] += 1
            continue
        if geom is None:
            counts["without a line"] += 1
        records.append((str(oid), payload(props, geom), geom))
        rows[oid] = {**facility(props, counts), "object_id": oid, "geom": geom}
        if any(note(props)):
            notes[oid] = note(props)
    return records, rows, notes, counts


def content_hash(records):
    """One digest of a whole read: every record's ID and version, in ID order."""
    h = hashlib.sha256(f"v{CONTENT_VERSION}".encode())
    for source_id, p, _ in sorted(records, key=lambda r: int(r[0])):
        h.update(source_id.encode() + b"\0" + db.version_hash(p))
    return h.hexdigest()[:32]


# --- storing ------------------------------------------------------------------------------

COLUMNS = ["object_id", "location_id", "kind", "street", "city", "agency", "func_class", "existing_type", "lts",
           "bike_legend", "speed_mph", "speed_field_mph", "volume", "yr_built", "year_added", "year_updated",
           "field_verified", "total_lanes", "total_pavement_ft", "total_row_ft",
           *(f"{s.lower()}_{c}" for s in SIDES for c in (
               "direction", "facility", "facility_w_ft", "lane_w_ft", "lanes", "edge", "right_turn", "parking",
               "parking_w_ft", "markings", "buffer", "buffer_w_ft", "buffer_varies")),
           "attributes"]

_UPSERT = f"""
insert into roads.bike_facility ({", ".join(COLUMNS)}, geom, active, first_seen, last_seen)
values ({", ".join(f"%({c})s" for c in COLUMNS)},
        case when %(geom)s::text is null then null
             else ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) end, true, %(seen)s, %(seen)s)
on conflict (object_id) do update set
  {", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c != "object_id")},
  geom = excluded.geom, active = true, last_seen = excluded.last_seen
"""


def store(conn, fetch_id, seen_at, features, parsed=None):
    """Write one full read (parsed: parse(features), when the caller has it). Returns (stats,
    changed: versions added or removed plus rows retired)."""
    records, rows, notes, counts = parsed or parse(features)
    # An empty or cut-off layer would retire most rows (and could pass for a reload): refuse it.
    db.check_snapshot(conn, "roads.bike_facility", "true", (), len(rows), SOURCE["name"])
    republish, carried = arcgis.carry_over(conn, label=SOURCE["name"], source=SOURCE["name"],
                                           table="roads.bike_facility", id_column="object_id", records=records,
                                           key_fields=REPUBLISH_KEY)
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    with conn.cursor() as cur:
        cur.executemany(_UPSERT, [{**r, "attributes": json.dumps(r["attributes"]),
                                   "geom": json.dumps(r["geom"]) if r["geom"] else None, "seen": seen_at}
                                  for r in rows.values()])
        cur.executemany("""insert into roads.bike_facility_note (object_id, comments, field_notes)
                           values (%s, %s, %s)
                           on conflict (object_id) do update set comments = excluded.comments,
                             field_notes = excluded.field_notes""",
                        [(oid, c, n) for oid, (c, n) in notes.items()])
    conn.execute("delete from roads.bike_facility_note where object_id = any(%s) and not (object_id = any(%s))",
                 (list(rows), list(notes)))
    retired = conn.execute("update roads.bike_facility set active = false where active and last_seen < %s",
                           (seen_at,)).rowcount
    by_kind = Counter(r["kind"] for r in rows.values())
    stats = {"record versions new": new, "unchanged": unchanged, "removed": removed, "records": len(rows),
             "streets": by_kind["street"], "pathways": by_kind["path"], "planned roads": by_kind["planned"],
             "with curb-to-curb width": sum(1 for r in rows.values() if r["total_pavement_ft"]),
             "field-verified": sum(1 for r in rows.values() if r["field_verified"]),
             "with notes (internal)": len(notes), "retired": retired, **counts}
    if republish:
        stats["reload: rows carried over"] = carried
    return stats, new + removed + retired


# --- the change check -----------------------------------------------------------------

def stored_signature(conn):
    row = conn.execute("select signature from ops.layer_signature where source = %s", (SOURCE["name"],)).fetchone()
    return row[0] if row else None


def save_signature(conn, sig, read):
    """As the other layers' change checks: checked_at always moves, read_at only after a full store."""
    conn.execute(
        """insert into ops.layer_signature (source, signature, read_at, checked_at) values (%s, %s, now(), now())
           on conflict (source) do update set signature = excluded.signature, checked_at = excluded.checked_at,
             read_at = case when %s then excluded.read_at else ops.layer_signature.read_at end""",
        (SOURCE["name"], json.dumps(sig), read))


def unchanged(conn, sig):
    """The read is the one last stored, and every record of it is still here and active."""
    stored = stored_signature(conn)
    if not stored or stored.get("content") != sig["content"]:
        return False
    active = conn.execute("select count(*) from roads.bike_facility where active").fetchone()[0]
    return active == sig["records"]


def heartbeat(conn, seen_at):
    """An unchanged layer: every current version and row was seen again."""
    seen = conn.execute("update raw.record set last_seen = %s where source = %s and removed_at is null",
                        (seen_at, SOURCE["name"])).rowcount
    conn.execute("update roads.bike_facility set last_seen = %s where active", (seen_at,))
    return seen


# --- matching to ACHD's road segments --------------------------------------------------

# Roads' bearing rule (a 15 m buffer, bearings within 20 degrees, closed lines failing), and then
# the names: a match whose street names disagree is dropped (core's names_agree; names that can't
# be compared, a route number facing a street name, stay). The widths are for one street, and on
# Oct 11, 2026 the 150 disagreeing matches (of 8,478) were mostly another street's segments
# alongside or at a junction: a frontage road beside State St, Overland Rd's at Cloverdale Rd,
# Amity Rd's at Black Cat Rd. A few were ACHD's misspellings ('Tast St' for Taft St), lost with
# them. The name check alone (check='name') isn't used: it also takes a same-named segment the
# line crosses or a closed one (188 on Oct 11). ACHD writes '08th St' and '02nd St': the leading
# zeros go before the names are compared.
RULE = linematch.Rule(**segment_match.METHODS["buffer15_bearing20"], loops=False)
LINES_SQL = r"""select 'achd_bike_network' as source, object_id::text as source_id, geom,
                      regexp_replace(street, '(^|\s)0+([1-9])', '\1\2', 'g') as name
               from roads.bike_facility where active and kind = 'street' and geom is not null"""


def match(conn):
    """Rewrite roads.bike_facility_match from the street records (the caller commits)."""
    found = linematch.match(conn, LINES_SQL, segment_match.SEGMENTS_SQL, RULE)
    kept = [m for m in found if linematch.names_agree(m["line_name"], m["target_name"]) is not False]
    conn.execute("delete from roads.bike_facility_match")
    with conn.cursor() as cur:
        cur.executemany(
            """insert into roads.bike_facility_match (road_segment_id, object_id, overlap_m, share, bearing_diff,
                 method, confidence, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, now())""",
            [(m["target_id"], int(m["source_id"]), round(m["overlap_m"], 1), round(min(m["share"], 1.0), 3),
              m["bearing_diff"], m["method"], m["confidence"]) for m in kept])
    s = linematch.coverage(conn, kept, segment_match.NEAR_NETWORK_M).get(SOURCE["name"], {})
    lines = s.get("lines", 0)
    return {"street records": lines, "matched": s.get("matched lines", 0), "matches": s.get("matches", 0),
            "ACHD segments": s.get("targets", 0), "matches on the line's share": s.get("matches on the line's share", 0),
            "dropped: street names disagree": len(found) - len(kept),
            "unmatched near ACHD": s.get("unmatched near", 0), "unmatched away from ACHD": s.get("unmatched away", 0),
            "match rate": f"{100 * s.get('matched lines', 0) / lines:.1f}%" if lines else "-"}


def stale(conn):
    """True when the matches are out of date: street records but no matches, or the records or
    ACHD's segments have changed (raw.record) since the last match."""
    if not conn.execute("select exists (select 1 from roads.bike_facility where active and kind = 'street')").fetchone()[0]:
        return False
    last = conn.execute("select max(matched_at) from roads.bike_facility_match").fetchone()[0]
    if last is None:
        return True
    return bool(conn.execute(
        """select exists (select 1 from raw.record where source = any(%s)
                            and (first_seen > %s or removed_at > %s))""",
        ([SOURCE["name"], "achd_roads"], last, last)).fetchone()[0])


# --- the run ------------------------------------------------------------------------------

def run(conn, get=None, sleep=time.sleep):
    db.ensure_source(conn, SOURCE)
    name = SOURCE["name"]
    with db.Fetch(conn, name) as f:
        esri, f.bytes, f.http_status, f.robots = arcgis.fetch_layer(
            LAYER, name, batch=BATCH, precision=PRECISION, max_features=MAX_FEATURES, get=get, sleep=sleep)
        features = [arcgis.esri_feature(x) for x in esri]
        if missing := missing_fields(features):
            raise RuntimeError(f"{name}: fields no longer in the layer: {', '.join(missing)}")
        parsed = parse(features)
        records = parsed[0]
        sig = {"content": content_hash(records), "records": len(records)}
        f.records = len(records)
        if unchanged(conn, sig):
            save_signature(conn, sig, read=False)
            stats, changed = {"unchanged": True, "versions confirmed": heartbeat(conn, f.started_at)}, 0
        else:
            stats, changed = store(conn, f.id, f.started_at, features, parsed)
            save_signature(conn, sig, read=True)
        # Inside the fetch: if matching fails, the store rolls back with it and the run is retried.
        if changed or stale(conn):
            stats.update({f"match {k}": v for k, v in match(conn).items()})
    return stats
