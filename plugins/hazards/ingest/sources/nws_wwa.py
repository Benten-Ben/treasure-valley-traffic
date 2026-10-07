"""NWS watches, warnings and advisories in the ring, from the WWA map service
(docs/sources/hazards.md, "NWS watches, warnings and advisories map service").

Not api.weather.gov: its robots.txt disallows everything (ch. 17 Q13: off-limits). The
map service's layer 1, WatchesWarnings, holds every current alert polygon (111 product
types; layer 0 only five storm-based warnings), with prod_type, msg_type, VTEC's
phenom, sig, event (the event tracking number, ETN) and wfo, issuance, onset, ends and
expiration (ISO text; a blank is ' '), and cap_id. Its `url` points into
api.weather.gov and is never fetched (it's "https://api.weather.gov/alerts/" + cap_id,
so it isn't stored either). NWS reloads the layer every few minutes, renumbering
objectid and moving idp_filedate and idp_ingestdate, so those three aren't kept.

Every 10 minutes, one query of the ring's envelope. Alerts are grouped by VTEC event:
office, phenomenon, significance, ETN and year (cap_id changes with every update; the
year is the first issuance's, kept while the event stays active, since ETNs restart each
January). Products without VTEC (blank phenom) are keyed by product and cap_id. A
group's polygons (one per zone or storm polygon) are merged into one geometry.
- raw.record: one record per event: its products (msg_type, times, cap_id) and the
  merged geometry's fingerprint. A full snapshot (complete=True): an empty one is normal.
- evt.event: one lifecycle per event, `declared` from the earliest onset (or issuance)
  to the latest end (open when any part runs "until further notice").
When an active event vanishes before its expiration, the layer may have been read mid-
reload: it's read once more after 30 s and the second answer is used.

Alerts about people are dropped before anything is stored: Child Abduction Emergency,
Blue Alert, Law Enforcement Warning, Missing and Endangered Person (the catalog's IPAWS
rule, ch. 17 Q22). Civil Danger Warnings and Local Area Emergencies carry no text in
this service, only product, times and area. Public domain; credit the NWS.
mapservices.weather.noaa.gov's robots.txt redirects to an HTML page: no rules.
"""

import json
import time
from datetime import datetime, timezone

from ingest import arcgis, db, events
from .. import common

LAYER = "https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer/1"
PRECISION = 5
REREAD_S = 30
PERSON_RELATED = {"child abduction emergency", "blue alert", "law enforcement warning",
                  "missing and endangered person", "missing endangered person"}
SIGNIFICANCE = {"W": "warning", "A": "watch", "Y": "advisory", "S": "statement", "F": "forecast",
                "O": "outlook", "N": "synopsis"}
PRODUCT_FIELDS = ("prod_type", "msg_type", "issuance", "onset", "ends", "expiration", "cap_id")

SOURCE = {
    "name": "nws_wwa",
    "title": "NWS watches, warnings and advisories (WWA map service, the ring)",
    "url": LAYER,
    "access": "open",
    "schedule": "10 minutes",
    "license": "public domain",
    "credit": "NOAA National Weather Service",
    "notes": "WatchesWarnings layer (1) of the WWA MapServer, ring envelope, one query a run. Grouped by VTEC "
             "event; versions in raw.record (complete=True); lifecycles in evt.event. api.weather.gov is "
             "robots-disallowed and never fetched. Person-related alerts (CAE, Blue, LEW, MEP) dropped.",
}


def person_related(attrs):
    return (arcgis.text(attrs.get("prod_type")) or "").lower() in PERSON_RELATED


def vtec(attrs):
    """'KBOI.FW.W.0012' (office, phenomenon, significance, ETN), or None for a product without VTEC."""
    parts = [arcgis.text(attrs.get(k)) for k in ("wfo", "phenom", "sig", "event")]
    return ".".join(parts) if all(parts) else None


def event_key(attrs, active=()):
    """The event's key: VTEC plus the year of its first issuance (an active event with the
    same VTEC keeps its key across January), or product and cap_id without VTEC."""
    base = vtec(attrs)
    if base:
        for sid in active:
            if sid.rsplit(".", 1)[0] == base:
                return sid
        issued = common.parse_time(attrs.get("issuance")) or datetime.now(timezone.utc)
        return f"{base}.{issued.year}"
    prod = arcgis.text(attrs.get("prod_type")) or "alert"
    cap = arcgis.text(attrs.get("cap_id"))
    return f"{prod}|{cap}" if cap else f"{prod}|{arcgis.text(attrs.get('issuance')) or 'undated'}"


def group(features, active=()):
    """-> ({event key: [features]}, alerts dropped as person-related)."""
    groups, dropped = {}, 0
    for f in features:
        attrs = f.get("attributes") or {}
        if person_related(attrs):
            dropped += 1
            continue
        groups.setdefault(event_key(attrs, active), []).append(f)
    return groups, dropped


def record(features):
    """One event's (payload, merged geometry)."""
    products = {}
    for f in features:
        a = f.get("attributes") or {}
        p = {k: arcgis.text(a.get(k)) for k in PRODUCT_FIELDS if arcgis.text(a.get(k))}
        products.setdefault(json.dumps(p, sort_keys=True), p)
    first = (features[0].get("attributes") or {})
    geom = common.merge_polygons(common.esri_polygon(f.get("geometry")) for f in features)
    payload = {k: arcgis.text(first.get(k)) for k in ("wfo", "phenom", "sig", "event") if arcgis.text(first.get(k))}
    payload["products"] = [products[k] for k in sorted(products)]
    payload["parts"] = len(features)
    payload["_geom"] = arcgis.geom_digest(geom)
    return payload, geom


def parse(features, active=()):
    """-> ({event key: (payload, geometry)}, dropped)."""
    groups, dropped = group(features, active)
    return {k: record(fs) for k, fs in groups.items()}, dropped


def row_of(sid, payload, geom):
    products = payload.get("products") or []
    t = common.parse_time
    issued = [t(p.get("issuance")) for p in products if t(p.get("issuance"))]
    starts = [t(p.get("onset")) or t(p.get("issuance")) for p in products]
    starts = [s for s in starts if s]
    ends = [t(p.get("ends")) for p in products]
    expires = [t(p.get("expiration")) for p in products if t(p.get("expiration"))]
    never = datetime.min.replace(tzinfo=timezone.utc)
    latest = max(products, key=lambda p: (t(p.get("issuance")) or never, p.get("prod_type") or "")) if products else {}
    start, end = common.declared(min(starts) if starts else None,
                                 max(ends) if ends and all(ends) else None)
    sig = payload.get("sig")
    row = {
        "source_id": sid,
        "kind": "weather_alert",
        "geom": geom,
        "start": start,
        "end": end,
        "severity": SIGNIFICANCE.get(sig, sig),
        "description": latest.get("prod_type"),
        "attributes": {
            "prod_type": latest.get("prod_type"),
            "wfo": payload.get("wfo"), "phenom": payload.get("phenom"), "sig": sig, "etn": payload.get("event"),
            "msg_types": sorted({p["msg_type"] for p in products if p.get("msg_type")}),
            "issued": common.iso(max(issued)) if issued else None,
            "expires": common.iso(max(expires)) if expires else None,
            "cap_ids": sorted({p["cap_id"] for p in products if p.get("cap_id")}),
            "parts": payload.get("parts"),
        },
    }
    row["content_hash"] = common.event_hash(row)
    return row


def active_events(conn):
    """{source_id: expiration} of this source's active events."""
    return {sid: common.parse_time(exp) for sid, exp in conn.execute(
        "select source_id, attributes->>'expires' from evt.event where source = %s and active",
        (SOURCE["name"],)).fetchall()}


def vanished_early(active, keys, now):
    """Active events missing from a snapshot although they haven't expired yet."""
    return sorted(sid for sid, exp in active.items() if sid not in keys and exp is not None and exp > now)


def store(conn, fetch_id, seen_at, parsed):
    new, same, removed = db.upsert_records(conn, SOURCE["name"], ((k, p, g) for k, (p, g) in parsed.items()),
                                           fetch_id, seen_at, complete=True)
    counts = events.upsert(conn, SOURCE["name"], [row_of(k, p, g) for k, (p, g) in parsed.items()], seen_at)
    return {"alerts": len(parsed), "record versions new": new, "unchanged": same, "removed": removed,
            **{f"events {k}": v for k, v in counts.items()}}


def run(conn, sleep=time.sleep):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        active = active_events(conn)
        features, f.bytes, f.http_status, f.robots = common.query_layer(LAYER, SOURCE["name"], geometry=True,
                                                                        precision=PRECISION)
        parsed, dropped = parse(features, active)
        reread = False
        if vanished_early(active, parsed, f.started_at):
            sleep(REREAD_S)
            features, n, f.http_status, f.robots = common.query_layer(LAYER, SOURCE["name"], geometry=True,
                                                                      precision=PRECISION)
            f.bytes += n
            parsed, dropped = parse(features, active)
            reread = True
        f.records = len(parsed)
        stats = store(conn, f.id, f.started_at, parsed)
        stats.update({"person-related dropped": dropped, "read twice": reread})
    return stats
