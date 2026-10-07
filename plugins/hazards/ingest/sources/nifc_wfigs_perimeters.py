"""NIFC WFIGS interagency fire perimeters in the ring (docs/sources/hazards.md, "NIFC WFIGS
fire incidents and perimeters").

The all-years perimeter service (certified perimeters plus new ones since 2021): 120
fields, poly_* for the polygon and attr_* copied from the incident. Like the incidents,
it's read incrementally with an absolute filter, `attr_ModifiedOnDateTime_dt >= T OR
poly_DateCurrent >= T` (a new polygon moves poly_DateCurrent; an incident change moves
attr_ModifiedOnDateTime_dt; a final perimeter's attr_ fields can be months old), with T
the newest of either we hold less two hours, floored to the hour. Perimeter changes "may
take up to 15 minutes to display", hence the schedule.

- raw.record: every version of each fire's perimeter, keyed by poly_IRWINID (final fire
  perimeters leave attr_IrwinID empty), geometry at 5 decimals (about a metre) with its
  fingerprint in the payload, so a moved line makes a new version. complete=False.
  If one read brings two polygons for a fire, a Final Fire Perimeter wins over a daily
  one, then the newer poly_DateCurrent.
- evt.event: the fire's current perimeter as a lifecycle, with the incidents' rules
  (common.update_lifecycles): open until out, withdrawn or quiet.

Multipart polygons are kept as MultiPolygons (common.polygon_geojson). Disclaimer only;
credit NIFC/WFIGS and the IRWIN agencies. robots.txt: 403, no rules.
"""

from ingest import arcgis, db, http
from .. import common
from . import nifc_wfigs_incidents as incidents

LAYER = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
         "WFIGS_Interagency_Perimeters/FeatureServer/0")
OVERLAP = incidents.OVERLAP
PRECISION = 5
DROP = {"OBJECTID", "GlobalID", "poly_SourceOID", "attr_SourceOID", "Shape__Area", "Shape__Length"}

http.PACE_S.setdefault("services3.arcgis.com", 2.0)

SOURCE = {
    "name": "nifc_wfigs_perimeters",
    "title": "NIFC WFIGS interagency fire perimeters (the ring)",
    "url": LAYER,
    "access": "open",
    "schedule": "15 minutes",
    "license": "none stated (NIFC disclaimer only)",
    "credit": "National Interagency Fire Center (WFIGS), from IRWIN",
    "notes": "All-years perimeter service, ring envelope, absolute filter on attr_ModifiedOnDateTime_dt or "
             "poly_DateCurrent (newest held less 2 h); every perimeter version in raw.record (complete=False), "
             "keyed by poly_IRWINID; the current perimeter as a lifecycle in evt.event.",
}


def since(watermark, now):
    return incidents.since(watermark, now)


def where(start):
    ts = f"TIMESTAMP '{start:%Y-%m-%d %H:%M:%S}'"
    return f"attr_ModifiedOnDateTime_dt >= {ts} OR poly_DateCurrent >= {ts}"


def watermark(conn):
    ms = conn.execute("""select max(greatest((payload->>'attr_ModifiedOnDateTime_dt')::bigint,
                                             (payload->>'poly_DateCurrent')::bigint))
                         from raw.record where source = %s""", (SOURCE["name"],)).fetchone()[0]
    return arcgis.esri_date(ms)


def key(attrs):
    """The fire's IRWIN ID (poly_IRWINID, else attr_IrwinID), else the polygon's source GlobalID."""
    irwin = arcgis.text(attrs.get("poly_IRWINID")) or arcgis.text(attrs.get("attr_IrwinID"))
    if irwin:
        return irwin.upper()
    sg = arcgis.text(attrs.get("poly_SourceGlobalID"))
    return f"sg:{sg.upper()}" if sg else None


def _rank(p):
    final = "final" in (arcgis.text(p.get("poly_FeatureCategory")) or "").lower()
    return (final, p.get("poly_DateCurrent") or 0, p.get("attr_ModifiedOnDateTime_dt") or 0, p.get("_geom") or "")


def parse(features):
    """-> ({key: (payload, polygon)}, duplicates). Features without a key or a polygon are skipped."""
    out, duplicates = {}, 0
    for f in features:
        attrs = f.get("attributes") or {}
        sid = key(attrs)
        geom = common.esri_polygon(f.get("geometry"))
        if not sid or geom is None:
            continue
        payload = common.clean_attributes(attrs, DROP)
        payload["_geom"] = arcgis.geom_digest(geom)
        if sid in out:
            duplicates += 1
            if _rank(out[sid][0]) >= _rank(payload):
                continue
        out[sid] = (payload, geom)
    return out, duplicates


def row_of(sid, p, geom, at):
    t = arcgis.esri_date
    discovered, out = t(p.get("attr_FireDiscoveryDateTime")), t(p.get("attr_FireOutDateTime"))
    acres = arcgis.number(p.get("poly_GISAcres"))
    if acres is None:
        acres = arcgis.number(p.get("attr_IncidentSize"))
    stamps = [d for d in (t(p.get("attr_ModifiedOnDateTime_dt")), t(p.get("poly_DateCurrent"))) if d]
    modified = max(stamps) if stamps else None
    valid = (p.get("attr_IsValid", 1) not in (0, "0")
             and (arcgis.text(p.get("poly_DeleteThis")) or "").lower() != "yes"
             and (arcgis.text(p.get("poly_IsVisible")) or "").lower() != "no")
    start, end = common.declared(discovered, out)
    row = {
        "source_id": sid,
        "kind": "fire_perimeter",
        "geom": geom,
        "start": start,
        "end": end,
        "severity": common.size_class(acres),
        "description": arcgis.text(p.get("poly_IncidentName")) or arcgis.text(p.get("attr_IncidentName")),
        "attributes": {
            "acres": acres,
            "feature_category": arcgis.text(p.get("poly_FeatureCategory")),
            "map_method": arcgis.text(p.get("poly_MapMethod")),
            "polygon_time": common.iso(t(p.get("poly_PolygonDateTime"))),
            "date_current": common.iso(t(p.get("poly_DateCurrent"))),
            "polygon_source": arcgis.text(p.get("poly_Source")),
            "percent_contained": arcgis.number(p.get("attr_PercentContained")),
            "unique_fire_id": arcgis.text(p.get("attr_UniqueFireIdentifier")),
            "incident_type": arcgis.text(p.get("attr_IncidentTypeCategory")),
            "out": common.iso(out),
            "modified": common.iso(modified),
            "valid": valid,
        },
    }
    row["content_hash"] = common.event_hash(row)
    return row, common.fire_open(out, valid, modified, acres, at)


def store(conn, fetch_id, seen_at, parsed):
    new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], ((sid, p, g) for sid, (p, g) in parsed.items()),
                                          fetch_id, seen_at, complete=False)
    stats = {"read": len(parsed), "record versions new": new, "unchanged": unchanged}
    stats.update(common.update_lifecycles(conn, SOURCE["name"], parsed, seen_at, row_of))
    stats["active perimeters"] = conn.execute("select count(*) from evt.event where source = %s and active",
                                              (SOURCE["name"],)).fetchone()[0]
    return stats


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        start = since(watermark(conn), f.started_at)
        features, f.bytes, f.http_status, f.robots = common.query_layer(
            LAYER, SOURCE["name"], where=where(start), geometry=True, precision=PRECISION, page_by_id=True)
        parsed, duplicates = parse(features)
        f.records = len(parsed)
        stats = {"since": common.iso(start), **store(conn, f.id, f.started_at, parsed),
                 "duplicates": duplicates}
    return stats
