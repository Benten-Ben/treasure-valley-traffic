"""IDWR irrigation organizations: the service areas within which each irrigation organization (a district, canal
company or city system) can deliver its water rights (decision 19b). Not the irrigated area, and not proof of who
runs a canal: water-build records which service areas each canal runs through (water.canal_org), and the canal card
says it that way.

59 polygons touch the map box (Oct 11, 2026). Fields kept: NAME, PlaceOfUse (-999 a combination of rights; 0 none,
I.C. Title 43), LPOU (a Large Place of Use), PROCESS, ACRES. The `Owner` field is never requested or stored. Data
updated 2026-05-07 by IDWR. Monthly: three or four small requests.

INTERNAL (no licence stated; IDWR's disclaimer only), credited to IDWR. See ../idwr.py for the checks.
"""

import json

from ingest import arcgis, db
from .. import idwr

LAYER = "https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/0"
FIELDS = ("NAME", "PlaceOfUse", "LPOU", "PROCESS", "ACRES")          # never Owner
TABLE = "water.idwr_org"

SOURCE = {
    "name": "idwr_irrigation_orgs",
    "title": "IDWR irrigation organizations (service areas) in the map box",
    "url": LAYER,
    "access": "open",
    "schedule": "30 days",
    "license": "none stated (IDWR disclaimer: made available as a public service)",
    "credit": "Idaho Department of Water Resources",
    "notes": "Internal: canal cards only, never exported or tiled. The Owner field is never fetched. A courtesy note "
             "to IDWR is the owner's to send.",
}

INSERT = """insert into water.idwr_org (objectid, name, place_of_use, lpou, process, acres, geom, fetched_at)
            values (%s, %s, %s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)"""


def parse(attrs):
    """The fields we keep, cleaned. Anything else in attrs (Owner, if a server sent it anyway) is dropped."""
    return {"name": arcgis.text(attrs.get("NAME")), "place_of_use": arcgis.to_float(attrs.get("PlaceOfUse")),
            "lpou": arcgis.yes_no(attrs.get("LPOU")), "process": arcgis.text(attrs.get("PROCESS")),
            "acres": arcgis.to_float(attrs.get("ACRES"), 2)}


def rows(features, seen_at):
    out = []
    for oid, p, geom in idwr.records(features, parse):
        if not p["name"]:
            continue
        out.append((oid, p, geom, (oid, p["name"], p["place_of_use"], p["lpou"], p["process"], p["acres"],
                                   json.dumps(geom), seen_at)))
    return out


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = idwr.fetch(LAYER, SOURCE["name"], FIELDS)
        got = rows(features, f.started_at)
        stats = idwr.store(conn, SOURCE["name"], TABLE, INSERT, got, f.id, f.started_at,
                           "IDWR irrigation organizations")
        f.records = len(got)
    return stats
