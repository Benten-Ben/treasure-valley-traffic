"""Idaho Department of Lands fire-restriction stages, per zone, in the ring
(docs/sources/hazards.md and docs/sources/lands.md, "Idaho Department of Lands fire
restriction areas and zones").

Layer 1 of IDL's FireRestrictions MapServer, Fire Restriction Zones, backs IDL's Fire
Restrictions Finder: Name, Stage (None, Stage I, Stage II), Rstrct_Are (the restriction
area), DateEnacted, DateRescinded, UpcomingStage, Zones and last_edited_date. Six zones
touched the ring on Oct 7, 2026, all at Stage None. The service keeps only the current
state, so a stage's history exists only if we poll. (Layer 0, the restriction areas,
holds just the area names and outlines; the stages are per zone.)

Hourly: one attributes-only read (about 5 KB). Only when it differs from the current
versions (any field, including last_edited_date, which editor tracking moves on every
edit, geometry included) are the zones read again with their outlines (about 850 KB at
5 decimals for the six) and stored:
- raw.record: one record per zone, keyed by GlobalID, without OBJECTID, the shape
  statistics and last_edited_user (a person's login). A full snapshot (complete=True),
  refused if it has under half the zones we hold.
- evt.event: a restriction in force (any stage but None) is one lifecycle, keyed by zone,
  stage and DateEnacted, so Stage I then Stage II are two, and a zone back at None closes
  it. DateEnacted is when the current stage took effect, so it starts `declared`. An
  announced UpcomingStage is a lifecycle of its own (kind fire_restriction_announced).

No license stated: a state agency's public notice, used with credit to IDL and its
partners; internal until IDL answers a courtesy note (ch. 17 Q17). robots.txt on
gis1.idl.idaho.gov redirects to an HTML error page: no rules.
"""

import time

from ingest import arcgis, db, events
from .. import common

LAYER = "https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer/1"
PRECISION = 5
DROP = {"OBJECTID", "Shape.STArea()", "Shape.STLength()", "Shape__Area", "Shape__Length", "last_edited_user"}
NO_RESTRICTION = {"none", "no restrictions", "n/a", "na"}

SOURCE = {
    "name": "idl_fire_restrictions",
    "title": "IDL fire-restriction stages by zone (the ring)",
    "url": LAYER,
    "access": "open",
    "schedule": "1 hour",
    "license": "none stated",
    "credit": "Idaho Department of Lands and the Idaho Fire Restrictions Plan partners",
    "notes": "Zones layer of IDL's FireRestrictions MapServer, ring envelope. Hourly attributes-only check; "
             "outlines read only when a zone changed. Versions in raw.record (complete=True); stages in force "
             "as lifecycles in evt.event. Courtesy note to IDL due before republishing.",
}


def key(attrs):
    gid = arcgis.text(attrs.get("GlobalID"))
    return gid.upper() if gid else None


def clean(attrs):
    return common.clean_attributes(attrs, DROP)


def attributes_by_zone(features):
    """{GlobalID: cleaned attributes} (the attributes-only read)."""
    return {key(f.get("attributes") or {}): clean(f.get("attributes") or {})
            for f in features if key(f.get("attributes") or {})}


def parse(features):
    """-> {GlobalID: (payload, polygon)}; the payload carries the outline's fingerprint."""
    out = {}
    for f in features:
        attrs = f.get("attributes") or {}
        gid = key(attrs)
        if not gid:
            continue
        geom = common.esri_polygon(f.get("geometry"))
        payload = clean(attrs)
        payload["_geom"] = arcgis.geom_digest(geom)
        out[gid] = (payload, geom)
    return out


def unchanged(current, stored):
    """True when the attributes-only read matches the versions we hold (outlines aside)."""
    return bool(stored) and current == {sid: {k: v for k, v in p.items() if k != "_geom"}
                                        for sid, (p, _) in stored.items()}


def in_force(stage):
    s = arcgis.text(stage)
    return bool(s) and s.lower() not in NO_RESTRICTION


def rows(parsed):
    """evt.event rows: stages in force and announced stages."""
    out = []
    for gid, (p, geom) in parsed.items():
        name, area = arcgis.text(p.get("Name")), arcgis.text(p.get("Rstrct_Are"))
        enacted, rescinded = arcgis.esri_date(p.get("DateEnacted")), arcgis.esri_date(p.get("DateRescinded"))
        attributes = {"zone": name, "area": area, "zones": arcgis.text(p.get("Zones")),
                      "stage": arcgis.text(p.get("Stage")), "upcoming_stage": arcgis.text(p.get("UpcomingStage")),
                      "enacted": common.iso(enacted), "rescinded": common.iso(rescinded),
                      "edited": common.iso(arcgis.esri_date(p.get("last_edited_date"))), "zone_id": gid}
        stage = arcgis.text(p.get("Stage"))
        if in_force(stage):
            start, end = common.declared(enacted, rescinded)
            out.append({"source_id": f"{gid}|{stage}|{common.iso(enacted) or 'undated'}",
                        "kind": "fire_restriction", "geom": geom, "start": start, "end": end,
                        "severity": stage, "description": f"{stage} fire restrictions: {name}", "attributes": attributes})
        upcoming = arcgis.text(p.get("UpcomingStage"))
        if in_force(upcoming):
            out.append({"source_id": f"{gid}|upcoming|{upcoming}", "kind": "fire_restriction_announced",
                        "geom": geom, "start": None, "end": None, "severity": upcoming,
                        "description": f"{upcoming} fire restrictions announced: {name}", "attributes": attributes})
    for r in out:
        r["content_hash"] = common.event_hash(r)
    return out


def store(conn, fetch_id, seen_at, parsed):
    common.check_snapshot(conn, SOURCE["name"], len(parsed), SOURCE["name"])
    new, same, removed = db.upsert_records(conn, SOURCE["name"], ((gid, p, g) for gid, (p, g) in parsed.items()),
                                           fetch_id, seen_at, complete=True)
    counts = events.upsert(conn, SOURCE["name"], rows(parsed), seen_at)
    return {"zones": len(parsed), "record versions new": new, "unchanged": same, "removed": removed,
            "in force": sum(1 for p, _ in parsed.values() if in_force(p.get("Stage"))),
            **{f"events {k}": v for k, v in counts.items()}}


def run(conn, sleep=time.sleep):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, nbytes, f.http_status, f.robots = common.query_layer(LAYER, SOURCE["name"], geometry=False)
        current = attributes_by_zone(features)
        if unchanged(current, common.latest(conn, SOURCE["name"], current_only=True)):
            f.bytes, f.records = nbytes, len(current)
            return {"zones": len(current), "unchanged": common.heartbeat(conn, SOURCE["name"], f.started_at),
                    "outlines read": False}
        sleep(arcgis.PAUSE_S)
        features, n, f.http_status, f.robots = common.query_layer(LAYER, SOURCE["name"], geometry=True,
                                                                  precision=PRECISION)
        f.bytes = nbytes + n
        parsed = parse(features)
        f.records = len(parsed)
        stats = store(conn, f.id, f.started_at, parsed)
        stats["outlines read"] = True
    return stats
