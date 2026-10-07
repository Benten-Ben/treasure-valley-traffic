"""COMPASS's growth data: traffic-zone demographics and regional building permits.

On swidrdc.org (both on COMPASS's open-data hub; its disclaimer only), monthly:

- CompassMembers/TAZ_demographicsOpenData/0 (2,498 zones): the 2020 Census,
  COMPASS's estimates for 2022-2026 and forecasts for 2030-2055 of population,
  households and jobs -> core.taz and obs.taz_demographic (one row per zone,
  year, measure and kind).
- CompassMembers/Demographics_TAZForecast_Permits/0 (174,244 permits, 2000 on)
  -> obs.building_permit. Address, parcel number and comments aren't fetched.

Plats (weekly) are in compass_plats.

Field notes, checked Oct 6, 2026:
- TAZ fields: tpop = total population, pop = household population, gqr and
  grpqtr = group quarters, hh = households, jobs; '...census'/'...cens' are
  the 2020 Census, 'est' (before or after the year) an estimate, 'f' a
  forecast. rjobs25 (2025 jobs) has no marker: counted as an estimate ⚠️.
  The request names the zone's fields and every demographic field the layer
  describes, so a new estimate year is picked up without editing this file.
- Group quarters aren't given after 2024 (total minus household population
  gives them).
- Permits run through 2025 (9,150 that year), none yet for 2026: COMPASS adds
  a year at a time. Its statistics queries see only 97,684 of the rows, which
  is why the permits looked as if they stopped in 2023; plain counts and paging
  see them all. created_date and last_edited_date are empty.
- pnum (the permit number) is the agency's own, and isn't unique: agencies
  reuse numbers (one city's number in two months of 2003) and some permits
  have none (nine from one city in one month of 2000). The key is city,
  number, year and month; '#2', '#3' (in order of content) tell apart
  permits that still match.
- Units removed count negative (115 of the first 119 such permits are demolitions).
"""

import re

from .. import compass_layer as cl
from ..compass_layer import flag, integer, number, text

TAZ_PATH = "CompassMembers/TAZ_demographicsOpenData/FeatureServer/0"
PERMIT_PATH = "CompassMembers/Demographics_TAZForecast_Permits/FeatureServer/0"

SOURCE = {
    "name": "compass_growth",
    "title": "COMPASS growth: traffic-zone demographics and forecasts, building permits",
    "url": cl.BASE + "CompassMembers/",
    "access": "open",
    "schedule": "30 days",
    "retry_after": cl.RETRY_AFTER,
    "license": cl.HUB_LICENSE,
    "credit": cl.CREDIT,
    "notes": "Zones: 2020 Census, estimates 2022-2026, forecasts to 2055. Permits 2000 on, added a year at a time.",
}

TAZ = cl.layer_source("compass_taz", "COMPASS TAZ Demographics", TAZ_PATH, module="compass_growth")
PERMITS = cl.layer_source("compass_permit", "COMPASS Regional Building Permits", PERMIT_PATH,
                          notes=cl.HUB_NOTE + " Address, parcel number and comments not fetched.",
                          module="compass_growth")

# --- zones --------------------------------------------------------------------

TAZ_COLUMNS = {
    "name": "tazname", "county": "county", "demog_area": "demogarea", "general_area": "genarea",
    "general_city": "gencity", "fia_label": "fialabel", "fia_description": "fiadescrip",
    "highway_district": "hwydist", "zip_code": "zipcode", "notes": "notes_chg",
}
MEASURES = {"tpop": "population", "pop": "household_population", "gqr": "group_quarters",
            "grpqtr": "group_quarters", "hh": "households", "jobs": "jobs", "rjobs": "jobs"}
CENSUS = re.compile(r"(tpop|pop|hh|grpqtr|gqr)(?:census|cens)")
YEARLY = re.compile(r"(tpop|pop|hh|gqr|rjobs|jobs)(est)?(\d\d)(est|f)?")


def taz_field(name):
    """A demographic field's (year, measure, kind), or None for other fields.
    'tpopcensus' -> (2020, 'population', 'census'); 'hhest23' and 'hh25est' -> estimates;
    'jobs50f' -> (2050, 'jobs', 'forecast')."""
    n = name.lower()
    m = CENSUS.fullmatch(n)
    if m:
        return 2020, MEASURES[m[1]], "census"
    m = YEARLY.fullmatch(n)
    if not m or (m[2] and m[4]):
        return None
    return 2000 + int(m[3]), MEASURES[m[1]], "forecast" if m[4] == "f" else "estimate"


def zone_fields(meta):
    """The zone's own fields and every demographic field the layer has (so a new estimate year
    is picked up), named explicitly."""
    return ["tazid_curr", *TAZ_COLUMNS.values()] + sorted(f for f in meta.fields if taz_field(f))


def taz_rows(props):
    """(zone row, [demographic rows], [fields not understood], conflicts). Two fields for the same
    year, measure and kind ('tpopest27' and 'tpop27est') give one value; if they disagree, the
    first by field name is kept and the conflict counted."""
    taz_id = integer(props.get("tazid_curr"))
    zone = {"taz_id": taz_id, **{col: text(props.get(f)) for col, f in TAZ_COLUMNS.items()}}
    values, unknown, conflicts = {}, [], 0
    for name, v in sorted(props.items()):
        parsed = taz_field(name)
        if parsed:
            if integer(v) is None:
                continue
            if parsed in values:
                conflicts += values[parsed]["value"] != integer(v)
                continue
            year, measure, kind = parsed
            values[parsed] = {"taz_id": taz_id, "year": year, "measure": measure, "kind": kind, "value": integer(v)}
        elif name.lower() not in ("objectid", "tazid_curr", "shape__area", "shape__length") \
                and name not in TAZ_COLUMNS.values():
            unknown.append(name)
    return zone, list(values.values()), unknown, conflicts


def store_taz(conn, fetch_id, seen_at, got):
    pairs, repeats, suffixed = cl.keyed(got.rows, key=lambda r: str(integer(r[0].get("tazid_curr")) or ""),
                                        content=lambda r: cl.content(r[0], r[1], got.oid))
    pairs = [(k, r) for k, r in pairs if k and "#" not in k]          # a zone ID must be a number, once
    cl.check_share(got, len(pairs), cl.current_records(conn, TAZ["name"]), "zones")
    stats = cl.store_records(conn, TAZ["name"], [(k, cl.without(p, got.oid), g) for k, (p, g) in pairs],
                             fetch_id, seen_at, got.complete)
    zones, values, unknown, conflicts = [], [], set(), 0
    for _, (p, g) in pairs:
        zone, vals, unk, conf = taz_rows(p)
        zones.append({**zone, "geom": g})
        values += vals
        unknown.update(unk)
        conflicts += conf
    cl.upsert(conn, "core.taz", ["taz_id"], zones, seen_at, geom="multi")
    # The current release replaces each fetched zone's values.
    conn.execute("delete from obs.taz_demographic where taz_id = any(%s)", ([z["taz_id"] for z in zones],))
    with conn.cursor() as cur:
        cur.executemany("""insert into obs.taz_demographic (taz_id, year, measure, kind, value)
                           values (%(taz_id)s, %(year)s, %(measure)s, %(kind)s, %(value)s)""", values)
    retired = cl.retire(conn, "core.taz", seen_at) if got.complete else 0
    out = {**stats, "stored": len(zones), "values": len(values), "conflicting values": conflicts,
           "repeats or bad ids": repeats + suffixed, "retired": retired}
    if unknown:
        out["fields not understood"] = ",".join(sorted(unknown))
    return out


# --- permits ------------------------------------------------------------------

PERMIT_FIELDS = ["objectid", "city", "pnum", "mon", "yr", "slu", "sqft", "units", "value", "work", "type",
                 "occupiable", "impact", "county", "demog19", "tazupdate", "hwy", "zip"]


def permit_key(props):
    """'<city>|<number>|2003-08': agencies reuse permit numbers, and some permits have none."""
    year, month = integer(props.get("yr")), integer(props.get("mon"))
    when = f"{year or ''}-{month:02d}" if month else f"{year or ''}"
    return f"{text(props.get('city')) or ''}|{text(props.get('pnum')) or ''}|{when}"


def permit_row(props):
    month = integer(props.get("mon"))
    return {
        "permit_number": text(props.get("pnum")),
        "city": text(props.get("city")),
        "county": text(props.get("county")),
        "year": integer(props.get("yr")),
        "month": month if month and 1 <= month <= 12 else None,
        "work": text(props.get("work")),
        "building_type": text(props.get("type")),
        "land_use_code": integer(props.get("slu")),
        "sq_ft": number(props.get("sqft")),
        "units": integer(props.get("units")),
        "value_usd": integer(props.get("value")),
        "occupiable": flag(props.get("occupiable")),
        "impact_area": text(props.get("impact")),
        "demog_area": text(props.get("demog19")),
        "taz_id": integer(props.get("tazupdate")),
        "highway_district": text(props.get("hwy")),
        "zip_code": text(integer(props.get("zip"))),
    }


def store_permits(conn, fetch_id, seen_at, got):
    pairs, repeats, suffixed = cl.keyed(got.rows, key=lambda r: permit_key(r[0]),
                                        content=lambda r: cl.content(r[0], r[1], got.oid))
    rows = [{"permit_key": k, **permit_row(p), "geom": g} for k, (p, g) in pairs]
    cl.check_share(got, sum(1 for r in rows if r["year"]), cl.current_records(conn, PERMITS["name"]), "permits")
    stats = cl.store_records(conn, PERMITS["name"], [(k, cl.without(p, got.oid), g) for k, (p, g) in pairs],
                             fetch_id, seen_at, got.complete)
    cl.upsert(conn, "obs.building_permit", ["permit_key"], rows, seen_at, geom="point")
    retired = cl.retire(conn, "obs.building_permit", seen_at) if got.complete else 0
    return {**stats, "stored": len(rows), "exact repeats dropped": repeats, "keys suffixed": suffixed,
            "without year": sum(1 for r in rows if r["year"] is None),
            "without point": sum(1 for r in rows if not r["geom"]), "retired": retired}


LAYERS = [
    cl.Layer("zones", TAZ, TAZ_PATH, zone_fields, store_taz),
    cl.Layer("permits", PERMITS, PERMIT_PATH, PERMIT_FIELDS, store_permits),
]


def run(conn):
    return cl.run(conn, SOURCE, LAYERS)
