"""Idaho Parks and Recreation's area restrictions in the ring (layer 123, polygons).

From the same service behind trails.idaho.gov as idpr_route_closures:
area closures and restrictions statewide, from the forests, BLM and IDPR
(docs/sources/trails.md, "IDPR Idaho Recreation Trails"). It carries orders
no other machine-readable source has, such as BLM's Big Grass Fire closure
(BLM Idaho publishes its orders only as web pages and PDFs, docs/sources/
lands.md). On Oct 7, 2026 the ring held 6 areas.

Keyed on GlobalID (one polygon per area, often with several outer rings
and holes). kind is "closure" when the type or name says closed or closure
(or "Public Use Exclusion"), else "restriction" (OHV exclusions, seasonal
parking restrictions). Dates are text, read as in idpr_route_closures; USFS
order numbers in the text are listed to link with usfs_r4_orders later.
Links are kept, never fetched.

IDPR's terms: not for commercial use, and no use in third-party apps
without attribution. Not republished raw (manifest: aggregates) until the
owner decides; a courtesy note to IDPR is due (docs/17 Q17). Read through
plugins/lands/ingest/closures.py (edit gate, ring cut, snapshot guard).
"""

from ingest import arcgis

from .. import closures

LAYER = ("https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/"
         "Idaho_Recreation_Trails/FeatureServer/123")
REQUIRED = ("Restricted_Area_Name", "Restricted_Area_Type", "Date_Start", "Date_End", "Date_Order_Expires",
            "Narrative", "GlobalID")

SOURCE = {
    "name": "idpr_area_restrictions",
    "title": "IDPR area closures and restrictions in the ring (trails.idaho.gov)",
    "url": LAYER,
    "access": "open",
    "schedule": "1 hour",
    "license": "IDPR terms: non-commercial use, attribution required (no licence stated)",
    "credit": "Idaho Department of Parks and Recreation (trails.idaho.gov), with the agencies it represents",
    "notes": "Layer metadata hourly; the ring is read in full only after an edit or once a day. One record "
             "and one evt.event row per area (GlobalID); links kept, never fetched. Not republished raw.",
}


def key(attrs):
    gid = (arcgis.text(attrs.get("GlobalID")) or "").strip("{}").lower()
    if gid:
        return gid
    return "name:" + " ".join((arcgis.text(attrs.get("Restricted_Area_Name")) or "").split()).casefold()


def event(sid, payload, geom):
    """The evt.event row for one restricted area."""
    def text(k):
        return arcgis.text(closures.pick(payload, k))

    start_day, end_day = closures.text_span(payload, ("Date_Start",), ("Date_End", "Date_Order_Expires"))
    start, end, fixes = closures.declared(start_day, end_day)
    return {
        "source_id": sid,
        "kind": closures.kind_of(text("Restricted_Area_Type"), text("Restricted_Area_Name")),
        "geom": geom,
        "start": start,
        "end": end,
        "severity": None,
        "description": closures.sentence(text("Restricted_Area_Name"), text("Narrative")),
        "attributes": {
            "name": text("Restricted_Area_Name"),
            "area_type": text("Restricted_Area_Type"),
            "jurisdiction": text("JURISDICTION"),
            "office": text("OFFICE"),
            "phone": text("OFFICE_PHONE"),
            "order_signed": text("Date_Order_Signed"),
            "order_expires": text("Date_Order_Expires"),
            "start_text": text("Date_Start"),
            "end_text": text("Date_End"),
            "start_date": closures.iso(start_day),
            "end_date": closures.iso(end_day),
            "links": [u for u in (text("URL_1"), text("URL_2")) if u],
            "orders_mentioned": closures.order_numbers(text("Restricted_Area_Name"), text("Narrative")),
            "acres": closures.total(payload, "Acres"),
            "edited": closures.latest_edit(payload),
            "fixes": fixes,
        },
    }


def run(conn):
    return closures.run_layer(conn, SOURCE, LAYER, required=REQUIRED, key=key, event=event)
