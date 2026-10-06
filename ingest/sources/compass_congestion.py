"""COMPASS's congestion measures and commute travel times (internal use only).

Layers of COMPASSData/Traffic_Counts on swidrdc.org, monthly. Neither is on
COMPASS's open-data hub, so they aren't offered as open data: we use them
internally until COMPASS answers, and never republish them (ops.source says
so; so do the tables' comments).

- 8 CMP_Performance_Measures_Allyrs (47,293 rows, 2018-2025): travel-time
  index, reliability (LOTTR, TTTR), hours of delay, congested and free-flow
  speed per road segment and year -> obs.congestion_measure.
- 0 Commute_Travel_Times (32: 16 commutes, AM and PM, 2025) ->
  obs.commute_travel_time. Boise-Caldwell and Caldwell-Boise each come by two
  routes (I-84/I-184 and SH 20/26), so the route is part of the key.

Field notes, checked Oct 6, 2026:
- One row per segment and year. peaktimebin_tti ('AM', 'PM', 'Afternoon',
  'Weekend', 'No Data/Unclassified') is the period the index peaked in, not a
  key; the same holds for peaktimebin_lottr.
- roadway_id is a TMC code for tier 1 ('117-04109', '117+06460', '117N04167',
  '117P04162') and an XD segment number for tier 2 ('119084250',
  '1187379614'), except in 2025, where every row reads '1' or '2'. Those
  rows are keyed by their geometry, direction and road name instead.
- 'No Data/Low Sample Volume', 'N/A' and 'No Data/Unclassified' are stored
  as null. miles is text. The layer reaches beyond Ada and Canyon (Elmore,
  Boise counties).
- level_of_reliability in the commute layer is a number: the 80th over the
  50th percentile travel time (LOTTR).
"""

import re

from .. import db
from . import compass_layer as cl
from .compass_layer import integer, number, text

SERVICE = "COMPASSData/Traffic_Counts/FeatureServer"

SOURCE = {
    "name": "compass_congestion",
    "title": "COMPASS congestion measures and commute travel times (internal use)",
    "url": cl.BASE + SERVICE,
    "access": "open",
    "schedule": "30 days",
    "license": cl.INTERNAL_LICENSE,
    "credit": cl.CREDIT,
    "notes": cl.INTERNAL_NOTE,
}

MEASURES = cl.layer_source("compass_congestion_measure", "COMPASS CMP performance measures, all years",
                           SERVICE + "/8", license=cl.INTERNAL_LICENSE, notes=cl.INTERNAL_NOTE,
                           module="compass_congestion")
COMMUTES = cl.layer_source("compass_commute_time", "COMPASS commute travel times", SERVICE + "/0",
                           license=cl.INTERNAL_LICENSE, notes=cl.INTERNAL_NOTE, module="compass_congestion")

MEASURE_FIELDS = ["objectid", "roadway_id", "roadname", "roadnumber", "road_direction", "county", "miles", "tier",
                  "year", "tti", "peaktimebin_tti", "lottr_ma", "peaktimebin_lottr", "tttr_ma", "hrs_of_del",
                  "level_of_congestion", "level_of_reliability", "truck_reliability", "congested_speed",
                  "freeflow_speed"]
COMMUTE_FIELDS = ["objectid", "commute_name", "route_name", "peak_hour", "year", "freeflow_travel_time_min",
                  "average_travel_time_min", "pct_50_travel_time_min", "pct_80_travel_time_min",
                  "pct_95_travel_time_min", "travel_time_index", "level_of_reliability"]

TMC = re.compile(r"\d{3}[-+NP]\d{5}")
XD = re.compile(r"\d{6,}")
NO_DATA = {"no data/low sample volume", "no data/unclassified", "n/a", "no data"}


def label(v):
    v = text(v)
    return None if v is None or v.lower() in NO_DATA else v


def segment_id(props, geom):
    """(segment_id, id_kind): the source's TMC or XD ID, or, where it has none, a hash of
    the geometry, direction and road name ('g:' and 16 hex digits)."""
    rid = text(props.get("roadway_id"))
    if rid and TMC.fullmatch(rid):
        return rid, "tmc"
    if rid and XD.fullmatch(rid):
        return rid, "xd"
    basis = {"coordinates": (geom or {}).get("coordinates"), "direction": text(props.get("road_direction")),
             "road": text(props.get("roadname"))}
    return "g:" + db.version_hash(basis).hex()[:16], "geometry"


def measure_row(props, geom):
    sid, kind = segment_id(props, geom)
    return {
        "year": integer(props.get("year")),
        "segment_id": sid,
        "id_kind": kind,
        "tier": integer(props.get("tier")),
        "road_name": text(props.get("roadname")),
        "road_number": text(props.get("roadnumber")),
        "direction": text(props.get("road_direction")),
        "county": text(props.get("county")),
        "length_mi": number(props.get("miles")),
        "tti": number(props.get("tti")),
        "tti_peak_period": label(props.get("peaktimebin_tti")),
        "lottr": number(props.get("lottr_ma")),
        "lottr_peak_period": label(props.get("peaktimebin_lottr")),
        "tttr": number(props.get("tttr_ma")),
        "delay_hours": number(props.get("hrs_of_del")),
        "congestion_level": label(props.get("level_of_congestion")),
        "reliability": label(props.get("level_of_reliability")),
        "truck_reliability": label(props.get("truck_reliability")),
        "congested_speed_mph": number(props.get("congested_speed")),
        "freeflow_speed_mph": number(props.get("freeflow_speed")),
    }


def store_measures(conn, fetch_id, seen_at, got):
    parsed = [(p, g, measure_row(p, g)) for p, g in got.rows]
    no_year = sum(1 for _, _, r in parsed if r["year"] is None)
    pairs, repeats, suffixed = cl.keyed([t for t in parsed if t[2]["year"] is not None],
                                        key=lambda t: f"{t[2]['year']}:{t[2]['segment_id']}",
                                        content=lambda t: cl.without(t[0]))
    stats = cl.store_records(conn, MEASURES["name"], [(k, cl.without(p), g) for k, (p, g, _) in pairs],
                             fetch_id, seen_at, got.complete)
    rows = [{**r, "segment_id": k.split(":", 1)[1], "geom": g} for k, (_, g, r) in pairs]
    cl.upsert(conn, "obs.congestion_measure", ["year", "segment_id"], rows, seen_at, geom="multi")
    retired = cl.retire(conn, "obs.congestion_measure", seen_at) if got.complete else 0
    kinds = {}
    for r in rows:
        kinds[r["id_kind"]] = kinds.get(r["id_kind"], 0) + 1
    return {**stats, "stored": len(rows), **{f"keyed by {k}": n for k, n in sorted(kinds.items())},
            "without year": no_year, "exact repeats dropped": repeats, "keys suffixed": suffixed,
            "retired": retired}


def commute_row(props):
    return {
        "commute": text(props.get("commute_name")),
        "route": text(props.get("route_name")),
        "period": text(props.get("peak_hour")),
        "year": integer(props.get("year")),
        "freeflow_min": number(props.get("freeflow_travel_time_min")),
        "average_min": number(props.get("average_travel_time_min")),
        "median_min": number(props.get("pct_50_travel_time_min")),
        "p80_min": number(props.get("pct_80_travel_time_min")),
        "p95_min": number(props.get("pct_95_travel_time_min")),
        "travel_time_index": number(props.get("travel_time_index")),
        "lottr": number(props.get("level_of_reliability")),
    }


COMMUTE_KEY = ("commute", "route", "period", "year")


def store_commutes(conn, fetch_id, seen_at, got):
    parsed = [(p, g, commute_row(p)) for p, g in got.rows]
    usable = [t for t in parsed if all(t[2][k] for k in COMMUTE_KEY)]
    pairs, repeats, suffixed = cl.keyed(usable, key=lambda t: "|".join(str(t[2][k]) for k in COMMUTE_KEY),
                                        content=lambda t: cl.without(t[0]))
    pairs = [(k, t) for k, t in pairs if "#" not in k]          # one row per commute, route, period and year
    stats = cl.store_records(conn, COMMUTES["name"], [(k, cl.without(p), g) for k, (p, g, _) in pairs],
                             fetch_id, seen_at, got.complete)
    rows = [{**r, "geom": g} for _, (_, g, r) in pairs]
    cl.upsert(conn, "obs.commute_travel_time", list(COMMUTE_KEY), rows, seen_at, geom="multi")
    retired = cl.retire(conn, "obs.commute_travel_time", seen_at) if got.complete else 0
    return {**stats, "stored": len(rows), "incomplete keys": len(parsed) - len(usable),
            "conflicting repeats skipped": suffixed, "retired": retired}


LAYERS = [
    cl.Layer("segments", MEASURES, SERVICE + "/8", MEASURE_FIELDS, store_measures),
    cl.Layer("commutes", COMMUTES, SERVICE + "/0", COMMUTE_FIELDS, store_commutes),
]


def run(conn):
    return cl.run(conn, SOURCE, LAYERS)
