"""IDWR season of use: the legal irrigation season's zones (decision 19d), the period during which water may be
appropriated for irrigation, set by IDWR from a 45 °F mean daily temperature. It's the legal window, not when canals
deliver water, and the canal card says so ("IDWR legal season Apr 1-Oct 31, not delivery dates").

Four zones touch the map box (Oct 11, 2026): Mar 1-Nov 15, Mar 15-Oct 31, Mar 15-Nov 15 and Apr 1-Oct 31. Fields:
SPRING, FALL, STARTMONTH, STARTDAY, ENDMONTH, ENDDAY, SEASON. Regulatory, so it rarely changes: every 90 days, two
small requests.

INTERNAL (no licence stated; IDWR's disclaimer only), credited to IDWR. See ../idwr.py for the checks.
"""

import json

from ingest import arcgis, db
from .. import idwr

LAYER = "https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/SeasonOfUse/FeatureServer/0"
FIELDS = ("SPRING", "FALL", "STARTMONTH", "STARTDAY", "ENDMONTH", "ENDDAY", "SEASON")
TABLE = "water.idwr_season"

SOURCE = {
    "name": "idwr_season_of_use",
    "title": "IDWR season of use (the legal irrigation season) in the map box",
    "url": LAYER,
    "access": "open",
    "schedule": "90 days",
    "license": "none stated (IDWR disclaimer: made available as a public service)",
    "credit": "Idaho Department of Water Resources",
    "notes": "Internal: canal cards only, never exported or tiled. The legal season, not delivery dates. A courtesy "
             "note to IDWR is the owner's to send.",
}

INSERT = """insert into water.idwr_season (objectid, season, spring, fall, start_month, start_day, end_month, end_day,
              geom, fetched_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)"""


def _day(v, top):
    n = arcgis.to_int(v)
    return n if n is not None and 1 <= n <= top else None


def parse(attrs):
    return {"season": arcgis.text(attrs.get("SEASON")), "spring": arcgis.text(attrs.get("SPRING")),
            "fall": arcgis.text(attrs.get("FALL")), "start_month": _day(attrs.get("STARTMONTH"), 12),
            "start_day": _day(attrs.get("STARTDAY"), 31), "end_month": _day(attrs.get("ENDMONTH"), 12),
            "end_day": _day(attrs.get("ENDDAY"), 31)}


def rows(features, seen_at):
    return [(oid, p, geom, (oid, p["season"], p["spring"], p["fall"], p["start_month"], p["start_day"],
                            p["end_month"], p["end_day"], json.dumps(geom), seen_at))
            for oid, p, geom in idwr.records(features, parse)]


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = idwr.fetch(LAYER, SOURCE["name"], FIELDS)
        got = rows(features, f.started_at)
        stats = idwr.store(conn, SOURCE["name"], TABLE, INSERT, got, f.id, f.started_at, "IDWR season of use")
        f.records = len(got)
    return stats
