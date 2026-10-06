"""ACHD's Master Street Map arterials (Ada County): existing, funded and planned
lanes, typology, right-of-way and parking (docs/09 §9.3).

Open GIS layer (the host has no robots.txt; no license stated: "Created by
Ada County Highway District, 2026"), about 1,050 segments in one request.
Records are keyed by GlobalID. OBJECTID, Shape__Length and the edit dates
are left out of the stored record: every row was stamped 2026-08-20 by a bulk
reload, so the dates would make each reload a "new version" of everything. A
fingerprint of the line (to about a metre) goes in instead.

If most GlobalIDs change in one run, ACHD has republished the layer rather
than replaced its streets: the run logs a republish and carries our rows
over to the new IDs (same street code and line, or a unique street code, or
a unique line), so their ids and first_seen survive; matches are redone.

Lanes count the whole cross-section ⚠️: 5 is 2+2 plus a centre turn lane,
3 is 1+1 plus one, 7 is 3+3 plus one. ExistLane is blank on state routes
and interstates (ITD's roads), and 0 on planned roads not built yet.
PlanLane_C (funded) reads "No Funded Improvement" on most rows; that and
blanks become null.

Master_Street_Map_Collectors (2,879 segments, checked Oct 6, 2026) carries
street codes, names and typology but no lanes, so it isn't read.
"""

import json
from collections import Counter

from .. import arcgis, db, segment_match

LAYER = "https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Master_Street_Map_Arterials/FeatureServer/1"

SOURCE = {
    "name": "achd_msm",
    "title": "ACHD Master Street Map arterials (existing, funded and planned lanes)",
    "url": LAYER,
    "access": "open",
    "schedule": "30 days",
    "license": "none stated",
    "credit": "Ada County Highway District",
    "notes": "Ada only. Lanes count the whole cross-section (5 = 2+2 plus a centre turn lane); "
             "blank on state routes. Edit dates are bulk-stamped and left out of versions.",
}

VOLATILE = {"OBJECTID", "Shape__Length", "created_date", "last_edited_date"}
NO_VALUE = {"no funded improvement", "no planned improvement"}

# Typology codes -> names. StreetTypo carries the names, with typos and spelling
# variants ('Trasitional/Commercial', 'ResidentialMobility'); N_ marks a new road.
TYPOLOGY = {
    "AR": "Residential Arterial",
    "ANR": "Neighborhood Residential Arterial",
    "AT": "Town Center Arterial",
    "ATC": "Transitional/Commercial Arterial",
    "APC": "Planned Commercial Arterial",
    "AI": "Industrial Arterial",
    "AU": "Rural Arterial",
    "MA": "Mobility Arterial",
    "MAR": "Residential Mobility Arterial",
    "MS": "Mobility Corridor (under study)",
    "STATE": "State Highway",
    "INTERSTATE": "Interstate",
    "TBD": "To Be Decided",
    "STUDY": "Under Study",
}


def value(v):
    """Text, with blanks and 'No ... Improvement' as null."""
    t = arcgis.text(v)
    return None if t is None or t.lower() in NO_VALUE else t


def lanes(v):
    """'5' -> 5, ' 3 ' -> 3, '0' -> 0; blank, 'No Funded Improvement' and other words -> None."""
    t = value(v)
    return arcgis.to_int(t) if t is not None else None


def typology(code, street_typo=None):
    """'AR' -> 'Residential Arterial'; 'N_AR' -> 'Residential Arterial (new road)'.
    An unknown code falls back to the row's own StreetTypo text."""
    c = (arcgis.text(code) or "").upper()
    if not c:
        return arcgis.text(street_typo)
    new = c.startswith("N_")
    base = c[2:] if new else c
    name = TYPOLOGY.get(base) or arcgis.text(street_typo) or base
    return f"{name} (new road)" if new else name


def arterial(props):
    """Our core.msm_arterial row (without geometry) for one MSM record."""
    g = props.get
    return {
        "global_id": arcgis.text(g("GlobalID")),
        "street_code": arcgis.text(g("StreetCode")),
        "street_name": arcgis.text(g("StreetName")),
        "typology_code": (arcgis.text(g("Typology")) or "").upper() or None,
        "typology": typology(g("Typology"), g("StreetTypo")),
        "existing_lanes": lanes(g("ExistLane")),
        "funded_lanes": lanes(g("PlanLane_C")),
        "planned_lanes": lanes(g("PlanLane_P")),
        "row_project": value(g("ROWProject")),
        "row_preservation": value(g("ROWPreserv")),
        "parking": value(g("Parking")),
        "comments": value(g("Comments")),
        "source_edited": arcgis.esri_date(g("last_edited_date")),
    }


def payload(props, geom):
    p = {k: v for k, v in props.items() if k not in VOLATILE}
    p["_geom"] = arcgis.geom_digest(geom)
    return p


def parse(features):
    """-> (records, rows, counts). records: (GlobalID, payload, geometry); rows: {GlobalID: row incl. 'geom'}."""
    records, rows, counts = [], {}, Counter()
    for f in features:
        props, geom = f.get("properties") or {}, f.get("geometry")
        gid = arcgis.text(props.get("GlobalID"))
        if not gid:
            counts["no GlobalID"] += 1
            continue
        if gid in rows:
            counts["duplicate GlobalIDs"] += 1
            continue
        records.append((gid, payload(props, geom), geom))
        rows[gid] = {**arterial(props), "geom": geom}
    return records, rows, counts


COLUMNS = ["global_id", "street_code", "street_name", "typology_code", "typology", "existing_lanes", "funded_lanes",
           "planned_lanes", "row_project", "row_preservation", "parking", "comments", "source_edited"]

_UPSERT = f"""
insert into core.msm_arterial ({", ".join(COLUMNS)}, geom, active, first_seen, last_seen)
values ({", ".join(f"%({c})s" for c in COLUMNS)},
        case when %(geom)s::text is null then null
             else ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) end, true, %(seen)s, %(seen)s)
on conflict (global_id) do update set
  {", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c != "global_id")},
  geom = excluded.geom, active = true, last_seen = excluded.last_seen
"""


def store(conn, fetch_id, seen_at, features):
    records, rows, counts = parse(features)
    republish, carried = arcgis.carry_over(conn, label="achd_msm", source=SOURCE["name"], table="core.msm_arterial",
                                           id_column="global_id", records=records, key_fields=("StreetCode",))
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    with conn.cursor() as cur:
        cur.executemany(_UPSERT, [{**r, "geom": json.dumps(r["geom"]) if r["geom"] else None, "seen": seen_at}
                                  for r in rows.values()])
    retired = conn.execute("update core.msm_arterial set active = false where active and last_seen < %s",
                           (seen_at,)).rowcount
    stats = {"record versions new": new, "unchanged": unchanged, "removed": removed, "arterials": len(rows),
             "with existing lanes": sum(1 for r in rows.values() if r["existing_lanes"] is not None),
             "retired": retired, **counts}
    if republish:
        stats["republish: rows carried over"] = carried
    return stats, new + removed + retired


LINES_SQL = """select 'achd_msm' as source, global_id as source_id, geom, street_name as name
               from core.msm_arterial where active"""


def match(conn):
    """Rewrite the arterials' matches to ACHD segments (the caller commits)."""
    stats = segment_match.rematch(conn, [SOURCE["name"]], LINES_SQL, method="buffer10_name")
    return segment_match.summary(stats)


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        out = arcgis.fetch_layer(LAYER, label="achd_msm")
        f.http_status, f.robots, f.bytes = out["status"], out["robots"], out["bytes"]
        stats, changed = store(conn, f.id, f.started_at, out["features"])
        f.records = stats["arterials"]
    if changed or segment_match.stale(conn, [SOURCE["name"]]):
        stats.update({f"match {k}": v for k, v in match(conn).items()})
        conn.commit()
    return stats
