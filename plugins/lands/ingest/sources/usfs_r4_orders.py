"""USDA Forest Service Intermountain Region (R4) forest orders in the ring.

The region's public view of its "ForestOrder" polygons (ArcGIS Online,
R04_Forest_Orders_PUBLIC_VIEW, layer 0): closures and restrictions under
36 CFR 261 Subpart B for every R4 forest, Boise, Payette and Sawtooth
included. The region rebuilds it daily from the forests' own layers, driven
by each order's dates, so it holds only current and coming orders
(docs/sources/trails.md, "USFS Region 4 forest orders"). On Oct 7, 2026 the
ring held 7 polygons that are 5 Boise NF orders; the Payette's and the
Sawtooth's orders (23 and 5 polygons) lay outside it, and are kept whenever
one reaches it.

Keyed on the order number (`ordernum`), not on polygons: one order can
have several (Deer Point and Crooked Fire have two each). The record keeps
the order's text fields (description, statement, exemption, CFR) and its
link (`hyperlink`, the alert page or the signed order's PDF); the PDF itself
is never fetched. Forest-wide orders with no polygon, such as Boise NF's
14-days-in-30 stay limit (0402-00-62), aren't in the layer.

Federal work, public domain; the Forest Service says the data "are not
legal documents": the signed order is the authority. Read through
plugins/lands/ingest/closures.py (edit gate, ring cut, snapshot guard).
"""

import hashlib

from ingest import arcgis

from .. import closures

LAYER = ("https://services1.arcgis.com/gGHDlz6USftL5Pau/arcgis/rest/services/"
         "R04_Forest_Orders_PUBLIC_VIEW/FeatureServer/0")
REQUIRED = ("ordernum", "ordername", "ordertype", "forest_order", "startdate", "enddate", "rescinddate", "hyperlink")

SOURCE = {
    "name": "usfs_r4_orders",
    "title": "USFS Intermountain Region forest orders (closures and restrictions) in the ring",
    "url": LAYER,
    "access": "open",
    "schedule": "1 hour",
    "license": "public domain (US federal work); USFS: not legal documents",
    "credit": "USDA Forest Service, Intermountain Region",
    "notes": "Layer metadata hourly; the ring is read in full only after an edit (the region rebuilds the "
             "layer daily) or once a day. One record and one evt.event row per order number; order PDFs "
             "are linked, never fetched.",
}


def key(attrs):
    """The order number; an order without one gets a stable stand-in from its forest, name and start."""
    num = (arcgis.text(attrs.get("ordernum")) or "").upper()
    if num:
        return num
    basis = "|".join(str(attrs.get(k)) for k in ("unitid", "ordername", "startdate"))
    return "unnumbered:" + hashlib.sha256(basis.encode()).hexdigest()[:12]


def event(sid, payload, geom):
    """The evt.event row for one order."""
    def text(k):
        return arcgis.text(closures.pick(payload, k))

    start, end, fixes = closures.declared(closures.utc_day(closures.pick(payload, "startdate")),
                                          closures.utc_day(closures.pick(payload, "enddate")),
                                          closures.utc_day(closures.pick(payload, "rescinddate")))
    published = arcgis.esri_date(closures.pick(payload, "pub_date"))
    return {
        "source_id": sid,
        "kind": closures.kind_of(text("forest_order"), text("ordertype")),
        "geom": geom,
        "start": start,
        "end": end,
        "severity": None,
        "description": closures.sentence(text("ordername"), text("description")),
        "attributes": {
            "order_number": text("ordernum"),
            "name": text("ordername"),
            "forest": text("forestname"),
            "unit_id": text("unitid"),
            "order_type": text("ordertype"),
            "order_form": text("forest_order"),
            "temporal_type": text("temporaltype"),
            "approval": text("approvaltype"),
            "signed": closures.iso(closures.utc_day(closures.pick(payload, "signeddate"))),
            "start_date": closures.iso(closures.utc_day(closures.pick(payload, "startdate"))),
            "end_date": closures.iso(closures.utc_day(closures.pick(payload, "enddate"))),
            "rescinded": closures.iso(closures.utc_day(closures.pick(payload, "rescinddate"))),
            "link": text("hyperlink"),
            "statement": text("statement"),
            "exemption": text("exemption"),
            "cfr": text("cfr"),
            "acres": closures.total(payload, "acres"),
            "polygons": len(payload.get("_parts") or []),
            "published": published.isoformat() if published else None,
            "fixes": fixes,
        },
    }


def run(conn):
    return closures.run_layer(conn, SOURCE, LAYER, required=REQUIRED, key=key, event=event)
