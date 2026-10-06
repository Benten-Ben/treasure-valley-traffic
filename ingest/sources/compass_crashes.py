"""COMPASS's crash data (Ada and Canyon counties): crashes 2008 on, the people
in them (restricted), and the high-injury network.

Layers of COMPASSData/CrashData on swidrdc.org (on COMPASS's open-data hub;
its disclaimer only), monthly:

- 0 All Crash Locations (174,038 points, 2008-2025) -> obs.crash, keyed by
  ITD's serial number. The police agency's case number isn't fetched.
- 2 crash details (345,152 rows, one per person) -> restricted.crash_unit
  only (never raw.record), coded fields only and coarsened (age group, Idaho
  resident or not); obs.crash gets each crash's unit types from it.
- 3 HIN_Junctions (1,924) -> core.hin_junction; 4 HIN_Segments (14,487) ->
  core.hin_segment.

Field notes, checked Oct 6, 2026:
- accident_date holds the calendar day at midnight UTC; the time is in
  accidenttime ('16:45' in early years, '16:45:00' in recent ones; '-U' when
  unknown); accidentdate is the same as text ('6/1/2008 16:45',
  '2025-06-01 16:45:00'). 111 crashes have no accident_date; those without
  the text either (30 of the first 16,000, all 2008-2009) have only a year:
  they stay in raw.record but not in obs.crash, whose key includes the time.
- intersectiondistance is in feet ('500.0000 F') or miles ('0.2500 M').
- 9 serial numbers appear twice as exact copies (dropped).
- int_id is usually doubled ('ACHD_213ACHD_213') and often a placeholder
  ('_', '__', 'Non-IntersectionNon-Intersection', 'Off SystemOff System',
  'LocalLocal', state-plane coordinates); pmid has placeholders too
  ('Int-Related', 'Off-System', 'Intersection*', 'Local', '_').
- workzonerelated is Y, N, '-U', '#NAME?' or blank; roadsurfaceconditions has
  'Water standing/moving' three ways (two of them mojibake).
- In the details, `person` is the crash's person count, not a person number,
  so rows have no person ID; `citation` is mostly coded ('DRIVING Following
  too close') but has stray numbers (ticket numbers?), which aren't kept;
  age 999 means unknown.
- The HIN layers were published once (edit date Oct 9, 2024 on every row).
  Junctions have no int_id; HIN_Segments' pm_id and copied `globalid` repeat,
  so both layers are keyed by their own GlobalID.
"""

import re
from collections import defaultdict
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .. import db
from . import compass_layer as cl
from .compass_layer import flag, integer, number, pm_id, text

SERVICE = "COMPASSData/CrashData/FeatureServer"
BOISE = ZoneInfo("America/Boise")

SOURCE = {
    "name": "compass_crashes",
    "title": "COMPASS crash data: crashes, the people in them (restricted), high-injury network",
    "url": cl.BASE + SERVICE,
    "access": "open",
    "schedule": "30 days",
    "license": cl.HUB_LICENSE,
    "credit": cl.CREDIT,
    "notes": ("Ada and Canyon, 2008 on (ITD's crash reports). Person-level details go to the restricted "
              "schema only: aggregates only, never exported or tiled."),
}

CRASHES = cl.layer_source("compass_crash", "COMPASS All Crash Locations", SERVICE + "/0", module="compass_crashes")
UNITS = cl.layer_source(
    "compass_crash_unit", "COMPASS crash details (one row per person; restricted)", SERVICE + "/2",
    notes=("Person-level: kept only in restricted.crash_unit (no raw.record copy), coded fields only, "
           "coarsened; publish aggregates only."), module="compass_crashes")
JUNCTIONS = cl.layer_source("compass_hin_junction", "COMPASS high-injury network: junctions", SERVICE + "/3",
                            module="compass_crashes")
SEGMENTS = cl.layer_source("compass_hin_segment", "COMPASS high-injury network: segments", SERVICE + "/4",
                           module="compass_crashes")

CRASH_FIELDS = ["objectid", "serialnumber", "accident_date", "accidentdate", "accidenttime", "year", "severity",
                "units", "person", "fatalities", "injuries", "numberofinjuries", "light", "weather",
                "roadsurfaceconditions", "roadconditionsother", "workzonerelated", "intersectionrelated",
                "street1", "street2", "referencestreet", "intersectiondistance", "directionfromintersection",
                "laneofimpact", "segmentcode", "milepost", "statehighway", "countyname", "cityname", "agency",
                "latitude", "longitude", "pmid", "int_id"]          # not agencycaseid (the police case number)
# Not unitid (ITD's unit ID), person (a count), seating (always 'Y') or the crash-level fields.
UNIT_FIELDS = ["objectid", "serialnumber", "unitnumber", "unittype", "direction", "action_", "event", "location",
               "contributingfactors", "injury", "age", "sex", "residencestate", "protectiondevice", "ejection",
               "citation"]

# --- crashes ------------------------------------------------------------------

SEVERITY = {"fatal accident": "K", "a injury accident": "A", "b injury accident": "B",
            "c injury accident": "C", "property dmg report": "O"}
SURFACE = {"Water – standing/moving": "Water standing/moving"}
CLOCK = re.compile(r"(\d{1,2}):?(\d{2})(?::(\d{2}))?")
STAMP_FORMATS = ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%m/%d/%Y", "%Y-%m-%d")
INT_ID = re.compile(r"(ACHD|INT)_\d+")
DISTANCE = re.compile(r"([0-9]*\.?[0-9]+)\s*([A-Za-z]*)")


def clock(v):
    """'16:45', '16:45:00' or '1645' -> a time; None if missing or impossible ('-U', '99:99')."""
    m = CLOCK.fullmatch(text(v) or "")
    if not m:
        return None
    h, mi, s = int(m[1]), int(m[2]), int(m[3] or 0)
    return time(h, mi, s) if h < 24 and mi < 60 and s < 60 else None


def crash_time(props):
    """(crashed_at in America/Boise, time known?). The day comes from accident_date (or the
    accidentdate text), the time from accidenttime (or the text). (None, False) without a day."""
    day = cl.epoch_date(props.get("accident_date"))
    stamp, parsed, stamp_has_time = text(props.get("accidentdate")), None, False
    for fmt in STAMP_FORMATS if stamp else ():
        try:
            parsed, stamp_has_time = datetime.strptime(stamp, fmt), "%H" in fmt
            break
        except ValueError:
            continue
    if day is None and parsed:
        day = parsed.date()
    if day is None:
        return None, False
    t = clock(props.get("accidenttime"))
    if t is None and stamp_has_time and parsed.date() == day:
        t = parsed.time()
    return datetime.combine(day, t or time(0), BOISE), t is not None


def int_id(v):
    """COMPASS's intersection key: 'ACHD_213ACHD_213' -> 'ACHD_213', 'INT_ 3811' -> 'INT_3811';
    None for placeholders ('_', 'Non-IntersectionNon-Intersection', 'Off SystemOff System', ...)."""
    v = (text(v) or "").replace(" ", "")
    half = len(v) // 2
    if v and len(v) % 2 == 0 and v[:half] == v[half:]:
        v = v[:half]
    return v if INT_ID.fullmatch(v) else None


def distance_ft(v):
    """'5280.0000 F' -> 5280.0 (feet); 'M' means miles. None if unreadable."""
    m = DISTANCE.fullmatch(text(v) or "")
    if not m:
        return None
    unit = m[2].upper()
    if unit in ("", "F", "FT"):
        return float(m[1])
    if unit in ("M", "MI"):
        return float(m[1]) * 5280
    return None


def point(geom, props):
    if geom and geom.get("coordinates"):
        return geom
    lon, lat = number(props.get("longitude")), number(props.get("latitude"))
    return {"type": "Point", "coordinates": [lon, lat]} if lon and lat else None


def crash_row(props, geom=None):
    """Our obs.crash row for one COMPASS crash (serial_number None if it has none)."""
    crashed_at, known = crash_time(props)
    surface = text(props.get("roadsurfaceconditions"))
    return {
        "serial_number": text(props.get("serialnumber")),
        "crashed_at": crashed_at,
        "time_known": known,
        "severity": SEVERITY.get((text(props.get("severity")) or "").lower()),
        "units": integer(props.get("units")),
        "persons": integer(props.get("person")),
        "fatalities": integer(props.get("fatalities")),
        "injuries": integer(props.get("injuries")),
        "light": text(props.get("light")),
        "weather": text(props.get("weather")),
        "surface": SURFACE.get(surface, surface),
        "road_condition": text(props.get("roadconditionsother")),
        "work_zone": flag(props.get("workzonerelated")),
        "intersection_related": flag(props.get("intersectionrelated")),
        "street": text(props.get("street1")),
        "cross_street": text(props.get("street2")),
        "reference_street": text(props.get("referencestreet")),
        "distance_ft": distance_ft(props.get("intersectiondistance")),
        "direction_from": text(props.get("directionfromintersection")),
        "lane_of_impact": text(props.get("laneofimpact")),
        "segment_code": text(props.get("segmentcode")),
        "milepost": number(props.get("milepost")),
        "state_highway": text(props.get("statehighway")),
        "county": text(props.get("countyname")),
        "city": text(props.get("cityname")),
        "agency": text(props.get("agency")),
        "pm_id": pm_id(props.get("pmid")),
        "int_id": int_id(props.get("int_id")),
        "geom": point(geom, props),
    }


def store_crashes(conn, fetch_id, seen_at, got):
    parsed, no_id = [], 0
    for props, geom in got.rows:
        row = crash_row(props, geom)
        if row["serial_number"]:
            parsed.append((props, geom, row))
        else:
            no_id += 1
    pairs, repeats, suffixed = cl.keyed(parsed, key=lambda t: t[2]["serial_number"],
                                        content=lambda t: cl.without(t[0]))
    stats = cl.store_records(conn, CRASHES["name"], [(k, cl.without(p), g) for k, (p, g, _) in pairs],
                             fetch_id, seen_at, got.complete)
    rows = [{**row, "serial_number": k} for k, (_, _, row) in pairs if row["crashed_at"]]
    # The time is part of the key: a crash whose reported time changed loses its old row first.
    moved = conn.execute(
        """delete from obs.crash c using unnest(%s::text[], %s::timestamptz[]) as n(serial, t)
           where c.serial_number = n.serial and c.crashed_at <> n.t""",
        ([r["serial_number"] for r in rows], [r["crashed_at"] for r in rows])).rowcount
    cl.upsert(conn, "obs.crash", ["serial_number", "crashed_at"], rows, seen_at, geom="point")
    retired = cl.retire(conn, "obs.crash", seen_at) if got.complete else 0
    return {**stats, "stored": len(rows), "exact repeats dropped": repeats, "keys suffixed": suffixed,
            "without serial": no_id, "without date": len(pairs) - len(rows),
            "without time": sum(1 for r in rows if not r["time_known"]),
            "without point": sum(1 for r in rows if not r["geom"]), "time moved": moved, "retired": retired}


# --- people (restricted) ------------------------------------------------------

INJURY = {"fatal injury": "K", "suspected serious injury": "A", "suspected minor injury": "B",
          "possible injury": "C", "no apparent injury": "O"}
AGE_GROUPS = ((15, "0-15"), (20, "16-20"), (24, "21-24"), (34, "25-34"), (44, "35-44"), (54, "45-54"),
              (64, "55-64"), (74, "65-74"))
DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
# A coded citation: an upper-case category, then words, no digits ('DRIVING Following too close').
CITATION = re.compile(r"[A-Z]{3,}(?: [A-Z]{2,})* [A-Za-z][^0-9]*")
UNKNOWN = {"unknown", "none", "-u"}


def age_group(v):
    a = number(v)
    if a is None or a < 0 or a > 120:            # 999: unknown
        return None
    for top, label in AGE_GROUPS:
        if a <= top:
            return label
    return "75+"


def resident(v):
    v = (text(v) or "").lower()
    return None if not v or v in UNKNOWN else v == "idaho"


def citation(v):
    """(cited, coded description). Stray numbers and misplaced values give (None, None)."""
    v = text(v)
    if not v:
        return None, None
    if v.lower() in ("not cited", "none"):
        return False, None
    if CITATION.fullmatch(v):
        return True, v
    return None, None


def unit_row(props):
    """One person, coded and coarsened. Nothing here is free text or an identifier."""
    cited, cite = citation(props.get("citation"))
    sex = (text(props.get("sex")) or "").upper()
    direction = (text(props.get("direction")) or "").upper()
    return {
        "serial_number": text(props.get("serialnumber")),
        "unit_number": integer(props.get("unitnumber")),
        "unit_type": text(props.get("unittype")),
        "direction": direction if direction in DIRECTIONS else None,
        "action": text(props.get("action_")),
        "event": text(props.get("event")),
        "location": text(props.get("location")),
        "contributing_factor": text((text(props.get("contributingfactors")) or "").lstrip(", ")),
        "injury": INJURY.get((text(props.get("injury")) or "").lower()),
        "age_group": age_group(props.get("age")),
        "sex": sex if sex in ("M", "F") else None,
        "idaho_resident": resident(props.get("residencestate")),
        "protection_device": text(props.get("protectiondevice")),
        "ejection": text(props.get("ejection")),
        "cited": cited,
        "citation": cite,
    }


def number_people(rows):
    """Give each person a seq within their unit, in order of content, so an unchanged set of
    people keeps its keys whatever order the source lists them in."""
    units = defaultdict(list)
    for r in rows:
        units[(r["serial_number"], r["unit_number"])].append(r)
    out = []
    for group in units.values():
        for i, r in enumerate(sorted(group, key=db.version_hash), 1):
            out.append({**r, "seq": i, "content_hash": db.version_hash(r)})
    return out


def store_units(conn, fetch_id, seen_at, got):
    rows, skipped = [], 0
    for props, _ in got.rows:
        r = unit_row(props)
        if r["serial_number"] and r["unit_number"] is not None:
            rows.append(r)
        else:
            skipped += 1
    people = number_people(rows)
    cl.upsert(conn, "restricted.crash_unit", ["serial_number", "unit_number", "seq"], people, seen_at, active=False)
    deleted = 0
    if got.complete:
        deleted = conn.execute("delete from restricted.crash_unit where last_seen < %s", (seen_at,)).rowcount
    # The public crash table gets only a crash-level aggregate: the kinds of units involved.
    typed = conn.execute(
        """update obs.crash c set unit_types = u.types
           from (select serial_number, array_agg(distinct unit_type order by unit_type) as types
                 from restricted.crash_unit where unit_type is not null group by serial_number) u
           where c.serial_number = u.serial_number and c.unit_types is distinct from u.types""").rowcount
    return {"stored": len(people), "skipped": skipped, "deleted": deleted, "crashes given unit types": typed}


# --- high-injury network ------------------------------------------------------

def _plain(v):
    return integer(v) or None


COMMON = {
    "total_crashes": ("total_crash_count", integer),
    "fatal_crashes": ("fatal_crash_count", integer),
    "serious_injury_crashes": ("serious_injury_crash_count", integer),
    "ka_crashes": ("ka_crashes", integer),
    "non_motorized_crashes": ("non_motorized_all_crashes", integer),
    "crash_rate": ("total_crash_rate", number),
    "ka_crash_rate": ("ka_crash_rate", number),
    "risk_score": ("risk_score", number),
    "hin_score": ("hin_score", number),
    "hin": ("hin", flag),
    "hin_non_motorized": ("hin_non_motorized", flag),
    "functional_class": ("funcclass", text),
}
JUNCTION_COLUMNS = {
    "int_type": ("int_type", text),
    "legs": ("legs", integer),
    "lanes_major": ("lanes_major", integer),
    "lanes_minor": ("lanes_minor", integer),
    "aadt_major": ("aadt_major", integer),
    "aadt_minor": ("aadt_minor", integer),
    "taz_id": ("tazid_current", integer),
    **COMMON,
}
SEGMENT_COLUMNS = {
    "pm_id": ("pm_id", pm_id),
    "achd_perm_id": ("permid", _plain),          # 0 outside Ada
    "name": ("strtconcat", text),
    "county": ("county", text),
    "posted_speed_mph": ("postspeed", _plain),
    "lanes": ("lanes", integer),
    "length_mi": ("miles", number),
    "aadt": ("aadt_mean", integer),
    "avg_speed_mph": ("avg_speed", number),
    "max_speed_mph": ("max_speed", number),
    **COMMON,
}
# Bookkeeping fields (plus each layer's own GlobalID): not attributes, and not part of a
# record's content. The layer-wide edit date would otherwise version every row on a republish.
HIN_DROP = {"objectid", "objectid_1", "join_count", "target_fid", "creationdate", "creator", "editdate",
            "editor", "shape__length", "shape__area"}


def hin_row(props, columns, drop=HIN_DROP):
    used = {f for f, _ in columns.values()}
    row = {col: conv(props.get(f)) for col, (f, conv) in columns.items()}
    row["attributes"] = {k: v for k, v in props.items()
                         if k.lower() not in drop and k not in used and text(v) is not None}
    row["source_edited"] = cl.epoch_ms(props.get("editdate"))
    return row


def hin_store(source, table, id_field, columns, geom_kind):
    drop = HIN_DROP | {id_field}

    def store(conn, fetch_id, seen_at, got):
        items = [(text(p.get(id_field)), p, g) for p, g in got.rows]
        no_id = sum(1 for k, _, _ in items if not k)
        pairs, repeats, suffixed = cl.keyed([i for i in items if i[0]], key=lambda i: i[0],
                                            content=lambda i: cl.without(i[1], *drop))
        stats = cl.store_records(conn, source["name"], [(k, cl.without(p, *drop), g) for k, (_, p, g) in pairs],
                                 fetch_id, seen_at, got.complete)
        rows = [{"global_id": k, **hin_row(p, columns, drop), "geom": g} for k, (_, p, g) in pairs]
        cl.upsert(conn, table, ["global_id"], rows, seen_at, geom=geom_kind)
        retired = cl.retire(conn, table, seen_at) if got.complete else 0
        return {**stats, "stored": len(rows), "without id": no_id, "exact repeats dropped": repeats,
                "keys suffixed": suffixed, "retired": retired}
    return store


LAYERS = [
    cl.Layer("crashes", CRASHES, SERVICE + "/0", CRASH_FIELDS, store_crashes),
    cl.Layer("people", UNITS, SERVICE + "/2", UNIT_FIELDS, store_units, geometry=False),
    cl.Layer("hin junctions", JUNCTIONS, SERVICE + "/3", ["*"],
             hin_store(JUNCTIONS, "core.hin_junction", "globalid", JUNCTION_COLUMNS, "point")),
    cl.Layer("hin segments", SEGMENTS, SERVICE + "/4", ["*"],
             hin_store(SEGMENTS, "core.hin_segment", "globalid_2", SEGMENT_COLUMNS, "multi")),
]


def run(conn):
    return cl.run(conn, SOURCE, LAYERS)
