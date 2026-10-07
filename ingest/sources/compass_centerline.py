"""COMPASS's RegionalCenterline: Ada and Canyon street centerlines with lanes,
posted speed, functional class and one-way (docs/09 §9.3).

Open GIS layer on swidrdc.org (no robots.txt rules; the COMPASS open-data
hub lists it with a disclaimer only; credit COMPASS), about 62,200 pieces
read with ingest/arcgis.py, 1,000 IDs a request, with a pause between
requests. The server sometimes resets a connection: requests are retried
with backoff.

Pieces are keyed by globalid, the only unique field (migration 0016):
pm_id, the key COMPASS's counts, crashes and travel model use, names a model
link of several pieces (26,912 pm_ids on 62,213 pieces, Oct 6, 2026), and
ACHD's PermID repeats too, since COMPASS splits ACHD's segments where its
links end. pm_id is kept on every row for those joins. objectid and
Shape__Length are left out of the stored record (a republish renumbers
them; the length is derived), a fingerprint of the line goes in, and if most
globalids change at once the run treats it as a republish and carries rows
over (by pm_id, PermID and address range, then by line).

Field notes: lanes vary between the pieces of one link, so they're per
piece; Canyon pieces read 0 for PermID and often for posted speed (both
"not recorded" here). It's the one lanes source that covers Canyon County,
where ACHD has no segments: Canyon lines stay unmatched and keep their own
geometry. In Ada the pieces are ACHD's own lines, so matching them is also a
check on the matcher.
"""

import json
from collections import Counter

from .. import arcgis, db, segment_match, signal_devices

LAYER = "https://swidrdc.org/arcgis/rest/services/COMPASSData/CommonFeatures/FeatureServer/0"
HUB = "https://share-open-data-compassidaho.hub.arcgis.com/datasets/compassidaho::regionalcenterline-2"

SOURCE = {
    "name": "compass_centerline",
    "title": "COMPASS RegionalCenterline (Ada and Canyon: lanes, posted speed, class)",
    "url": LAYER,
    "access": "open",
    "schedule": "30 days",
    "license": "none stated (disclaimer only)",
    "credit": "COMPASS (Community Planning Association of Southwest Idaho) and its member agencies",
    "notes": f"Listed on the COMPASS open-data hub ({HUB}). Keyed by globalid; pm_id is a model link of several pieces.",
}

MAX_PIECES = 100000          # the layer had 62,213 (Oct 6, 2026); far more would be a different layer
BATCH = 1000                 # IDs per request: within swidrdc.org's page size
VOLATILE = {"objectid", "globalid", "Shape__Length"}
# Our columns; every other field goes into attributes.
CORE_FIELDS = {"pm_id", "strtconcat", "county", "funcclass", "postspeed", "lanes", "oneway"}
ONE_WAY = {"B": "both", "F": "forward", "FT": "forward", "T": "backward", "TF": "backward"}
# Carrying rows over a republish: pieces are told apart by these, then by their line.
REPUBLISH_KEY = ("pm_id", "permid", "l_addfrom", "l_addto", "r_addfrom", "r_addto")


def one_way(v):
    """ACHD's and Esri's one-way codes -> both / forward / backward; blank -> both;
    anything else kept as written."""
    t = (arcgis.text(v) or "B").upper()
    return ONE_WAY.get(t, t)


def pm_id(v):
    t = arcgis.text(v)
    return None if not t or t.startswith("#") else t      # '#NYA': not yet assigned


def segment(props):
    """Our core.compass_segment row (without geometry) for one piece."""
    g = props.get
    name = arcgis.text(g("strtconcat")) or " ".join(
        filter(None, (arcgis.text(g(k)) for k in ("stpredir", "stprefix", "stname", "stsuffix", "stpostdir")))) or None
    attributes = {k: v for k, v in props.items()
                  if k not in CORE_FIELDS and k not in VOLATILE and v not in (None, "", " ")}
    if not arcgis.to_int(attributes.get("permid")):
        attributes.pop("permid", None)                     # Canyon pieces read 0
    if "miles" in attributes:
        attributes["miles"] = arcgis.to_float(attributes["miles"], 5)
    return {
        "global_id": arcgis.text(g("globalid")),
        "pm_id": pm_id(g("pm_id")),
        "name": name,
        "county": arcgis.text(g("county")),
        "functional_class": arcgis.text(g("funcclass")),
        "posted_speed_mph": arcgis.to_int(g("postspeed")) or None,
        "lanes": arcgis.to_int(g("lanes")) or None,          # 0 reads as "not recorded"
        "one_way": one_way(g("oneway")),
        "attributes": attributes,
    }


def payload(props, geom):
    p = {k: v for k, v in props.items() if k not in VOLATILE}
    if "miles" in p:
        p["miles"] = arcgis.to_float(p["miles"], 5)
    p["_geom"] = arcgis.geom_digest(geom)
    return p


def parse(features):
    """-> (records, rows, counts). records: (globalid, payload, geometry); rows: {globalid: row incl. 'geom'}."""
    records, rows, counts = [], {}, Counter()
    for f in features:
        props, geom = f.get("properties") or {}, f.get("geometry")
        gid = arcgis.text(props.get("globalid"))
        if not gid:
            counts["no globalid"] += 1
            continue
        if gid in rows:
            counts["duplicate globalids skipped"] += 1
            continue
        records.append((gid, payload(props, geom), geom))
        rows[gid] = {**segment(props), "geom": geom}
        if rows[gid]["pm_id"] is None:
            counts["no pm_id"] += 1
    return records, rows, counts


COLUMNS = ["global_id", "pm_id", "name", "county", "functional_class", "posted_speed_mph", "lanes", "one_way",
           "attributes"]

_UPSERT = f"""
insert into core.compass_segment ({", ".join(COLUMNS)}, geom, active, first_seen, last_seen)
values ({", ".join(f"%({c})s" for c in COLUMNS)},
        case when %(geom)s::text is null then null
             else ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)) end, true, %(seen)s, %(seen)s)
on conflict (global_id) do update set
  {", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c != "global_id")},
  geom = excluded.geom, active = true, last_seen = excluded.last_seen
"""


def store(conn, fetch_id, seen_at, features):
    records, rows, counts = parse(features)
    # An empty or cut-off layer would retire most rows (and could pass for a republish): refuse it.
    signal_devices.check_snapshot(conn, "core.compass_segment", "true", (), len(rows), SOURCE["name"])
    republish, carried = arcgis.carry_over(conn, label="compass_centerline", source=SOURCE["name"],
                                           table="core.compass_segment", id_column="global_id", records=records,
                                           key_fields=REPUBLISH_KEY)
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    with conn.cursor() as cur:
        cur.executemany(_UPSERT, [{**r, "attributes": json.dumps(r["attributes"]),
                                   "geom": json.dumps(r["geom"]) if r["geom"] else None, "seen": seen_at}
                                  for r in rows.values()])
    retired = conn.execute("update core.compass_segment set active = false where active and last_seen < %s",
                           (seen_at,)).rowcount
    stats = {"record versions new": new, "unchanged": unchanged, "removed": removed, "pieces": len(rows),
             "pm_ids": len({r["pm_id"] for r in rows.values() if r["pm_id"]}),
             "with lanes": sum(1 for r in rows.values() if r["lanes"]), "retired": retired, **counts}
    if republish:
        stats["republish: rows carried over"] = carried
    return stats, new + removed + retired


LINES_SQL = """select 'compass_centerline' as source, global_id as source_id, geom, name
               from core.compass_segment where active"""


def match(conn):
    """Rewrite the centerline's matches to ACHD segments (the caller commits)."""
    stats = segment_match.rematch(conn, [SOURCE["name"]], LINES_SQL)
    total = segment_match.summary(stats)
    for county, lines, unmatched in conn.execute(
            """select coalesce(c.county, '?'), count(*), count(*) filter (where not exists (
                 select 1 from core.segment_match m where m.source = 'compass_centerline' and m.source_id = c.global_id))
               from core.compass_segment c where c.active and c.county in ('Ada', 'Canyon')
               group by 1 order by 1""").fetchall():
        total[f"{county} unmatched"] = f"{unmatched} of {lines}"
    # In Ada the pieces are ACHD's own lines: does the matcher find each one's own segment?
    # (Canyon pieces carry other numbers in permid, so Ada only.)
    own, found = conn.execute(
        """select count(*), count(*) filter (where exists (
             select 1 from core.segment_match m where m.source = 'compass_centerline'
               and m.source_id = c.global_id and m.road_segment_id = r.id))
           from core.compass_segment c
           join core.road_segment r on r.active and r.achd_perm_id = (c.attributes->>'permid')::bigint
           where c.active and c.county = 'Ada' and c.attributes->>'permid' ~ '^[0-9]+$'""").fetchone()
    total["pieces with an ACHD PermID matched to that segment"] = f"{found} of {own}"
    return total


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = arcgis.fetch_layer(LAYER, SOURCE["name"], batch=BATCH,
                                                                        precision=6, max_features=MAX_PIECES)
        stats, changed = store(conn, f.id, f.started_at, [arcgis.esri_feature(x) for x in features])
        f.records = stats["pieces"]
        # Inside the fetch: if matching fails, the store rolls back with it and the run is retried.
        if changed or segment_match.stale(conn, [SOURCE["name"]]):
            stats.update({f"match {k}": v for k, v in match(conn).items()})
    return stats
