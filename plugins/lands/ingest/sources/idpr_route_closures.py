"""Idaho Parks and Recreation's emergency route closures in the ring (layer 127, lines).

From the service behind trails.idaho.gov (Idaho_Recreation_Trails, ArcGIS
Online): road and trail closures IDPR keeps for the whole state, its own
parks' (Eagle Island's construction closures) and the forests' and BLM's
as it represents them (docs/sources/trails.md, "IDPR Idaho Recreation
Trails"; IDPR calls other agencies' content "representative", authoritative
only at its source). On Oct 7, 2026 the ring held 9 segments: 4 closures.

Keyed on IDPR's `ID` field, which names a closure and repeats on each of
its segments ("Eagle Island Construction" has 6); a segment without one is
keyed on its GlobalID. Dates are text ("8/13/2026", "11/30/2026 unless
rescinded", "Indefinite"): a leading date is read as a local day and kept
with the text; anything else leaves the end open. USFS order numbers in
the text are listed (attributes.orders_mentioned) to link with usfs_r4_orders
later. Links (URL_1, URL_2) are kept, never fetched.

IDPR's terms: not for commercial use, and no use in third-party apps
without attribution. Not republished raw (manifest: aggregates) until the
owner decides; a courtesy note to IDPR is due (docs/17 Q17). Read through
plugins/lands/ingest/closures.py (edit gate, ring cut, snapshot guard).
"""

from ingest import arcgis

from .. import closures

LAYER = ("https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/"
         "Idaho_Recreation_Trails/FeatureServer/127")
REQUIRED = ("ID", "NAME", "DateStart", "DateEnd", "Date_Order_Expires", "Narrative", "GlobalID")

SOURCE = {
    "name": "idpr_route_closures",
    "title": "IDPR emergency road and trail closures in the ring (trails.idaho.gov)",
    "url": LAYER,
    "access": "open",
    "schedule": "1 hour",
    "license": "IDPR terms: non-commercial use, attribution required (no licence stated)",
    "credit": "Idaho Department of Parks and Recreation (trails.idaho.gov), with the agencies it represents",
    "notes": "Layer metadata hourly; the ring is read in full only after an edit or once a day. One record "
             "and one evt.event row per closure (IDPR's ID); links kept, never fetched. Not republished raw.",
}


def key(attrs):
    name = " ".join((arcgis.text(attrs.get("ID")) or "").split()).casefold()
    if name:
        return name
    gid = (arcgis.text(attrs.get("GlobalID")) or "").strip("{}").lower()
    return f"globalid:{gid}" if gid else "unnamed"


def event(sid, payload, geom):
    """The evt.event row for one closure (one or more segments)."""
    def text(k):
        return arcgis.text(closures.pick(payload, k))

    start_day, end_day = closures.text_span(payload, ("DateStart",), ("DateEnd", "Date_Order_Expires"))
    start, end, fixes = closures.declared(start_day, end_day)
    return {
        "source_id": sid,
        "kind": "closure",
        "geom": geom,
        "start": start,
        "end": end,
        "severity": None,
        "description": closures.sentence(text("NAME") or text("ID"), text("Narrative")),
        "attributes": {
            "closure_id": text("ID"),
            "name": text("NAME"),
            "jurisdiction": text("JURISDICTION"),
            "office": text("OFFICE"),
            "phone": text("PHONE"),
            "order_signed": text("Date_Order_Signed"),
            "order_expires": text("Date_Order_Expires"),
            "start_text": text("DateStart"),
            "end_text": text("DateEnd"),
            "start_date": closures.iso(start_day),
            "end_date": closures.iso(end_day),
            "links": [u for u in (text("URL_1"), text("URL_2")) if u],
            "orders_mentioned": closures.order_numbers(text("ID"), text("NAME"), text("Narrative")),
            "miles": closures.total(payload, "MILES"),
            "segments": len(payload.get("_parts") or []),
            "edited": closures.latest_edit(payload),
            "fixes": fixes,
        },
    }


def run(conn):
    return closures.run_layer(conn, SOURCE, LAYER, required=REQUIRED, key=key, event=event)
