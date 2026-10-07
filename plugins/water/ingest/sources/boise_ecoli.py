"""Boise Parks & Recreation's E. coli results: the latest sampling round only, so we keep the history.

The City's "E. coli Testing Sites" layer (services1.arcgis.com, BPR_EColi_Testing
FeatureServer layer 0; robots.txt 403, so no rules) holds one row per sample of
the latest round and is overwritten by the next: on Oct 7, 2026, 7 rows sampled
Sep 28, at the City's swimming ponds by the Boise River (Quinn's, Esther
Simplot, Veterans). docs/sources/trails.md, "Boise River E. coli results".

Twice a day, the whole layer through the shared ArcGIS reader (an ID list and
one page: two small requests). Each sample is a reading, kept for good in
raw.record (complete=False, so a round replaced by the next stays):
`<SampleName>|<SampleDatetime>|<LabNumber>`, the key the catalog gives,
with every field as published except OBJECTID (the layer's row number,
renumbered when the City reloads it). A date-only field comes as
'YYYY-MM-DD'; should it ever come as an Esri date, it's turned into one.

No license is stated (the City's disclaimer only): used internally with
credit, not republished, until the City answers a courtesy note
(docs/17 Q17). Shown with the City's or DEQ's thresholds and wording only;
we make no swim or no-swim call of our own.
"""

from ingest import arcgis, db

from ..common import in_ring, store_readings

LAYER = "https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/BPR_EColi_Testing/FeatureServer/0"
KEY = ("SampleName", "SampleDatetime", "LabNumber")
DATES = ("SampleDatetime", "AnalysisDatetime")

SOURCE = {
    "name": "boise_ecoli",
    "title": "Boise E. coli results at the City's swimming ponds and river sites (history kept from the latest round)",
    "url": LAYER,
    "access": "open",
    "schedule": "12 hours",
    "license": "none stated (City of Boise layer, disclaimer only)",
    "credit": "City of Boise Parks and Recreation",
    "notes": "The layer keeps only the latest sampling round; each sample is kept in raw.record (complete=False). "
             "Internal use with credit until the City answers a courtesy note.",
}


def day(v):
    """A date field as 'YYYY-MM-DD': date-only fields come that way; an Esri date (ms) is converted."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        dt = arcgis.esri_date(v)
        return dt.date().isoformat() if dt else None
    return arcgis.text(v)


def parse(features):
    """{source_id: (payload, point)} for the samples inside the ring with a complete key."""
    out = {}
    for f in features:
        payload = {k: v for k, v in (f.get("attributes") or {}).items() if k.upper() != "OBJECTID"}
        for k in DATES:
            if k in payload:
                payload[k] = day(payload[k])
        geom = arcgis.point_geojson(f.get("geometry"))
        if geom and not in_ring(*geom["coordinates"]):
            continue
        key = [arcgis.text(payload.get(k)) for k in KEY]
        if None in key:
            continue
        out["|".join(key)] = (payload, geom)
    return out


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = arcgis.fetch_layer(LAYER, SOURCE["name"], max_features=5000)
        parsed = parse(features)
        f.records = len(parsed)
        new, held = store_readings(conn, SOURCE["name"], [(k, p, g) for k, (p, g) in parsed.items()],
                                   f.id, f.started_at)
    return {"samples": len(parsed), "listed": len(features), "versions new": new, "held": held,
            "latest round": max((p.get("SampleDatetime") or "" for p, _ in parsed.values()), default=None)}
