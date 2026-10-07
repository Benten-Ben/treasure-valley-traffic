"""NIFC WFIGS wildland fire incidents in the ring (docs/sources/hazards.md, "NIFC WFIGS fire
incidents and perimeters"; docs/17 §17.2 "Fire and hazards").

Points for wildfires (WF), prescribed fires (RX) and complexes (CX) from IRWIN, 97
fields, refreshed from IRWIN every 5 minutes. The `_Current` view drops a fire once it's
contained, controlled or out, and applies fall-off rules to stale ones, so containment
can't be watched there: we read the all-years service with an absolute filter,
`ModifiedOnDateTime_dt >= TIMESTAMP '<time>'` (NIFC asks clients not to query with
relative dates), cut to the ring's envelope. The time is the newest ModifiedOn we hold
less two hours (WFIGS shows IRWIN's changes with a lag), floored to the hour so
successive polls ask the same question; the first run reads the year so far.

- raw.record: every version of every incident record, keyed by IrwinID, without the
  hosting artefacts (OBJECTID, GlobalID, SourceOID) and empty fields. Reads are
  incremental, so complete=False: nothing is retired.
- evt.event: one lifecycle per fire, `declared` from discovery to out. It stays open
  through containment and control, and closes when the fire is declared out, withdrawn
  (IsValid 0), or its record goes quiet longer than NIFC's own fall-off window for its
  size (3, 8 or 14 days); a later update reopens it. Fires first seen already out are
  kept in raw.record only. See common.update_lifecycles.

Disclaimer only (no reuse restriction); credit NIFC/WFIGS and the IRWIN agencies.
services3.arcgis.com answers robots.txt with 403: no rules. Cause fields give a class,
never a person.
"""

from datetime import datetime, timedelta, timezone

from ingest import arcgis, db, http
from .. import common

LAYER = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
         "WFIGS_Incident_Locations/FeatureServer/0")
OVERLAP = timedelta(hours=2)
DROP = {"OBJECTID", "GlobalID", "SourceOID"}       # hosting artefacts: they change if NIFC reloads the layer
KIND = {"WF": "wildfire", "RX": "prescribed_fire", "CX": "fire_complex"}

# Our two WFIGS sources run back to back; keep 2 s between any two requests to NIFC's host.
http.PACE_S.setdefault("services3.arcgis.com", 2.0)

SOURCE = {
    "name": "nifc_wfigs_incidents",
    "title": "NIFC WFIGS wildland fire incidents (the ring)",
    "url": LAYER,
    "access": "open",
    "schedule": "10 minutes",
    "license": "none stated (NIFC disclaimer only)",
    "credit": "National Interagency Fire Center (WFIGS), from IRWIN",
    "notes": "All-years incident service, ring envelope, absolute ModifiedOnDateTime_dt filter (newest held "
             "less 2 h); versions in raw.record (complete=False); fire lifecycles in evt.event, closed only "
             "when out, withdrawn or quiet past NIFC's fall-off window.",
}


def since(watermark, now):
    """Where the next read starts: the newest ModifiedOn we hold (never later than now) less
    OVERLAP, floored to the hour; Jan 1 of this year on the first run."""
    if watermark is None:
        start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    else:
        start = min(watermark, now) - OVERLAP
    return start.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def where(start):
    return f"ModifiedOnDateTime_dt >= TIMESTAMP '{start:%Y-%m-%d %H:%M:%S}'"


def watermark(conn):
    ms = conn.execute("""select max((payload->>'ModifiedOnDateTime_dt')::bigint) from raw.record
                         where source = %s""", (SOURCE["name"],)).fetchone()[0]
    return arcgis.esri_date(ms)


def key(attrs):
    irwin = arcgis.text(attrs.get("IrwinID"))
    return irwin.upper() if irwin else None


def parse(features):
    """-> {IrwinID: (payload, point)}. Records without an IrwinID are skipped; if one comes
    twice, the later ModifiedOn wins."""
    out = {}
    for f in features:
        attrs = f.get("attributes") or {}
        sid = key(attrs)
        if not sid:
            continue
        payload = common.clean_attributes(attrs, DROP)
        if sid in out and (out[sid][0].get("ModifiedOnDateTime_dt") or 0) > (payload.get("ModifiedOnDateTime_dt") or 0):
            continue
        out[sid] = (payload, arcgis.point_geojson(f.get("geometry")))
    return out


def row_of(sid, p, geom, at):
    """(evt.event row, open?) for one incident record."""
    t = arcgis.esri_date
    discovered, out = t(p.get("FireDiscoveryDateTime")), t(p.get("FireOutDateTime"))
    acres = arcgis.number(p.get("IncidentSize"))
    modified = t(p.get("ModifiedOnDateTime_dt"))
    valid = p.get("IsValid", 1) not in (0, "0")
    start, end = common.declared(discovered, out)
    row = {
        "source_id": sid,
        "kind": KIND.get(arcgis.text(p.get("IncidentTypeCategory")), "fire"),
        "geom": geom,
        "start": start,
        "end": end,
        "severity": common.size_class(acres),
        "description": arcgis.text(p.get("IncidentName")),
        "attributes": {
            "acres": acres,
            "percent_contained": arcgis.number(p.get("PercentContained")),
            "discovered": common.iso(discovered),
            "contained": common.iso(t(p.get("ContainmentDateTime"))),
            "controlled": common.iso(t(p.get("ControlDateTime"))),
            "out": common.iso(out),
            "modified": common.iso(modified),
            "unique_fire_id": arcgis.text(p.get("UniqueFireIdentifier")),
            "cause": arcgis.text(p.get("FireCause")),
            "county": arcgis.text(p.get("POOCounty")),
            "state": arcgis.text(p.get("POOState")),
            "protecting_agency": arcgis.text(p.get("POOProtectingAgency")),
            "landowner": arcgis.text(p.get("POOLandownerCategory")),
            "personnel": arcgis.number(p.get("TotalIncidentPersonnel")),
            "complex": arcgis.text(p.get("CpxName")),
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
    stats["active fires"] = conn.execute("select count(*) from evt.event where source = %s and active",
                                         (SOURCE["name"],)).fetchone()[0]
    return stats


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        start = since(watermark(conn), f.started_at)
        features, f.bytes, f.http_status, f.robots = common.query_layer(
            LAYER, SOURCE["name"], where=where(start), geometry=True, page_by_id=True)
        parsed = parse(features)
        f.records = len(parsed)
        stats = {"since": common.iso(start), **store(conn, f.id, f.started_at, parsed)}
    return stats
