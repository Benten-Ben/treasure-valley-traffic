"""COMPASS's crash data (Ada and Canyon counties): crashes 2008 on, the people
in them (restricted), and the high-injury network.

Layers of COMPASSData/CrashData on swidrdc.org (on COMPASS's open-data hub;
its disclaimer only), monthly:

- 0 All Crash Locations (174,038 points, 2008-2025) -> obs.crash, keyed by
  ITD's serial number. The police agency's case number isn't fetched.
- 2 crash details (345,152 rows, one per person) -> restricted.crash_unit
  only (never raw.record), coded fields only and coarsened (age group, Idaho
  resident or not; sex isn't fetched: owner, Oct 6); obs.crash gets each
  crash's unit types from it (publishable: ITD publishes involvement per
  crash too).
- 3 HIN_Junctions (1,924) -> core.hin_junction; 4 HIN_Segments (14,487) ->
  core.hin_segment. Every field is listed except the editor's names and the
  spatial-join bookkeeping.

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

from ingest import db
from ingest import compass_layer as cl
from ingest.compass_layer import flag, integer, number, pm_id, text

SERVICE = "COMPASSData/CrashData/FeatureServer"
BOISE = ZoneInfo("America/Boise")

SOURCE = {
    "name": "compass_crashes",
    "title": "COMPASS crash data: crashes, the people in them (restricted), high-injury network",
    "url": cl.BASE + SERVICE,
    "access": "open",
    "schedule": "30 days",
    "retry_after": cl.RETRY_AFTER,
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
# Not sex (owner, Oct 6: not needed, so not collected), unitid (ITD's unit ID), person (a count),
# seating (always 'Y') or the crash-level fields.
UNIT_FIELDS = ["objectid", "serialnumber", "unitnumber", "unittype", "direction", "action_", "event", "location",
               "contributingfactors", "injury", "age", "residencestate", "protectiondevice", "ejection", "citation"]
# Every HIN field except objectid (always added), the editor's names, creation date and the
# spatial-join bookkeeping (join_count, target_fid, objectid_1).
JUNCTION_FIELDS = """
    int_type roundabout roundabout_status roundabout_control_type roundabout_other_control_type
    roundabout_previous_control_typ roundabout_approaches roundabout_driveways roundabout_functional_class
    roundabout_lane_type roundabout_year_completed roundabout_icd total_crash_count type_ its_device aadt_mean
    aadt_minor aadt_major lanes_minor lanes_major legs tpopcensus tazid_current high_risk_low_crashes
    low_risk_high_crashes serious_injury_crash_count si_non_motorized si_motorcycle_involved si_alcohol_involved
    si_drug_involved si_alcohol_drug_involved si_no_protection_device si_angle_event si_rear_end_event
    si_overturn_event si_angle_turning_event si_head_on_turning_event si_pedestrian_event si_head_on_event
    si_pedalcycle_event si_side_swipe_same_event fatal_crash_count fatal_non_motorized fatal_motorcycle_involved
    fatal_alcohol_involved fatal_drug_involved fatal_alcohol_drug_involved fatal_no_protection_device
    fatal_angle_event fatal_rear_end_event fatal_overturn_event fatal_angle_turning_event fatal_head_on_turning_event
    fatal_pedestrian_event fatal_head_on_event fatal_pedalcycle_event fatal_side_swipe_same_event non_motorized_sum
    motorcycle_involved_sum alcohol_involved_sum drug_involved_sum alcohol_drug_involved_sum no_protection_device_sum
    angle_event_sum rear_end_event_sum overturn_event_sum angle_turning_event_sum head_on_turning_event_sum
    pedestrian_event_sum head_on_event_sum pedalcycle_event_sum side_swipe_same_event_sum total_crash_rate
    serious_injury_crash_rate fatal_crash_rate fatal_group injury_group ka_crashes ka_crash_rate ka_group
    location_score risk_attr_score1 risk_attr_score2 risk_attr_score3 risk_attr_score4 risk_score equityscore_max
    hin_demographic hin_score hin funcclass state hin_non_state hin_non_motorized non_motorized_all_crashes
    non_motorized_k non_motorized_a location_score_nm risk_attr_score1_nm risk_attr_score2_nm risk_attr_score3_nm
    risk_attr_score4_nm risk_score_nm hin_score_nm globalid editdate""".split()
SEGMENT_FIELDS = """
    l_addfrom l_addto r_addfrom r_addto stpredir stprefix stname stsuffix stpostdir stpostmod strtconcat l_commname
    r_commname l_zip4 r_zip4 permid postspeed emergspeed oneway funcclass private county pm_id direction majorroad
    state lanes impact check_ city miles dup globalid aadt_mean avg_speed max_speed postspd bikefacility_type
    sidewalk_type excess_speed excess_speeding_corridor id_asc_pav_typ_id id_lane_wid id_med_type_name id_med_width
    id_shldr_type_name id_left_unpav_shldr_wid l_shoulder_width id_rgt_unpav_shldr_wid r_shoulder_width
    id_terr_type_name total_crash_count total_crash_rate high_risk_low_crashes low_risk_high_crashes
    serious_injury_crash_count si_non_motorized si_motorcycle_involved si_alcohol_involved si_drug_involved
    si_alcohol_drug_involved si_no_protection_device si_angle_event si_rear_end_event si_overturn_event
    si_angle_turning_event si_head_on_turning_event si_pedestrian_event si_head_on_event si_pedalcycle_event
    si_side_swipe_same_event fatal_crash_count fatal_non_motorized fatal_motorcycle_involved fatal_alcohol_involved
    fatal_drug_involved fatal_alcohol_drug_involved fatal_no_protection_device fatal_angle_event fatal_rear_end_event
    fatal_overturn_event fatal_angle_turning_event fatal_head_on_turning_event fatal_pedestrian_event
    fatal_head_on_event fatal_pedalcycle_event fatal_side_swipe_same_event non_motorized_sum motorcycle_involved_sum
    alcohol_involved_sum drug_involved_sum alcohol_drug_involved_sum no_protection_device_sum angle_event_sum
    rear_end_event_sum overturn_event_sum angle_turning_event_sum head_on_turning_event_sum pedestrian_event_sum
    head_on_event_sum pedalcycle_event_sum side_swipe_same_event_sum serious_injury_crash_rate fatal_crash_rate
    fatal_group injury_group ka_crashes ka_crash_rate ka_group expected_crashes excess excess_pct location_score
    risk_attr_score1 risk_attr_score2 risk_attr_score3 risk_attr_score4 risk_attr_score5 risk_attr_score6
    risk_attr_score7 risk_attr_score8 risk_attr_score9 risk_attr_score10 risk_attr_score11 risk_attr_score12
    risk_attr_score13 risk_attr_score14 risk_attr_score15 risk_score equityscore_max hin_demographic hin_score
    non_motorized_k non_motorized_a non_motorized_all_crashes location_score_nm risk_attr_score1_nm
    risk_attr_score2_nm risk_attr_score3_nm risk_attr_score4_nm risk_attr_score5_nm risk_attr_score6_nm
    risk_attr_score7_nm risk_attr_score8_nm risk_attr_score9_nm risk_attr_score10_nm risk_attr_score11_nm
    risk_attr_score12_nm risk_attr_score13_nm risk_attr_score14_nm risk_attr_score15_nm risk_score_nm hin_score_nm
    hin hin_non_state hin_non_motorized globalid_2 editdate""".split()

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
                                        content=lambda t: cl.content(t[0], t[1], got.oid))
    rows = [{**row, "serial_number": k} for k, (_, _, row) in pairs if row["crashed_at"]]
    cl.check_share(got, len(rows), cl.current_records(conn, CRASHES["name"]), "crashes")
    stats = cl.store_records(conn, CRASHES["name"], [(k, cl.without(p, got.oid), g) for k, (p, g, _) in pairs],
                             fetch_id, seen_at, got.complete)
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
    current = conn.execute("select count(*) from restricted.crash_unit").fetchone()[0]
    cl.check_share(got, len(people), current, "crash people")
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
    def store(conn, fetch_id, seen_at, got):
        drop = HIN_DROP | {id_field, got.oid}
        items = [(text(p.get(id_field)), p, g) for p, g in got.rows]
        no_id = sum(1 for k, _, _ in items if not k)
        pairs, repeats, suffixed = cl.keyed([i for i in items if i[0]], key=lambda i: i[0],
                                            content=lambda i: cl.content(i[1], i[2], *drop))
        cl.check_share(got, len(pairs), cl.current_records(conn, source["name"]), source["name"])
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
    cl.Layer("hin junctions", JUNCTIONS, SERVICE + "/3", JUNCTION_FIELDS,
             hin_store(JUNCTIONS, "core.hin_junction", "globalid", JUNCTION_COLUMNS, "point")),
    cl.Layer("hin segments", SEGMENTS, SERVICE + "/4", SEGMENT_FIELDS,
             hin_store(SEGMENTS, "core.hin_segment", "globalid_2", SEGMENT_COLUMNS, "multi")),
]


def run(conn):
    return cl.run(conn, SOURCE, LAYERS)
