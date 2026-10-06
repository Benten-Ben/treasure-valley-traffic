"""COMPASS's count tables: the latest count at every location, from every agency.

Tables of COMPASSData/Traffic_Counts on swidrdc.org (on COMPASS's open-data
hub; its disclaimer only), monthly:

- 4 Portable_Latest (4,387): each location's latest short count, 2002-2025,
  by ACHD (3,093), Nampa Highway District, Canyon Highway District, Nampa,
  Golden Gate HD, ITD and others: ADT for a month and year.
- 5 ATR_Latest (115): ITD's permanent counters, the latest year's AADT.

Both go to obs.traffic_count, keyed by location and the counted month or
year. Each run adds the counts newer than those already kept; earlier ones
stay. The tables have no location ID:

- Portable_Latest holds one count per segment (its 4,371 real pm_ids are
  unique), so its key is the pm_id ('pm:<pm_id>'). The same location text
  can name two segments of one road. Rows with a placeholder pm_id are keyed
  by agency, road and location text instead ('loc:<agency>|<road>|<location>').
- ATR_Latest has two counters on each of 4 segments, and one row per direction
  on the interstates (same location text, pm_ids '...e08' and '...w08'), so
  its key is agency, road, location text and pm_id.

Field notes, checked Oct 6, 2026:
- pm_id has placeholders: '#NYA', '#nya', '01 needs PMID' (16 rows; null).
- onetwoway is '2' (both directions summed) or '1' (one direction: one side
  of a divided highway, or a one-way street); read as a number, and anything
  else is stored as null and reported. Counts in different directions at one
  place differ in their location key (the ATRs' pm_id), not in `direction`.
- No coordinates: join to core.compass_segment by pm_id.
"""

from datetime import date

from . import compass_layer as cl
from .compass_layer import integer, pm_id, text

SERVICE = "COMPASSData/Traffic_Counts/FeatureServer"

SOURCE = {
    "name": "compass_counts",
    "title": "COMPASS traffic counts: latest short count per location, permanent counters",
    "url": cl.BASE + SERVICE,
    "access": "open",
    "schedule": "30 days",
    "retry_after": cl.RETRY_AFTER,
    "license": cl.HUB_LICENSE,
    "credit": cl.CREDIT,
    "notes": "Every agency's latest count, Canyon County's included. ACHD's rows overlap our private copy of its tables.",
}

PORTABLE = cl.layer_source("compass_count_portable", "COMPASS Portable Latest Table Data", SERVICE + "/4",
                           module="compass_counts")
ATR = cl.layer_source("compass_count_atr", "COMPASS ATR Latest Table Count Data", SERVICE + "/5",
                      module="compass_counts")

PORTABLE_FIELDS = ["objectid", "pm_id", "road", "location", "agency", "onetwoway", "mon", "month", "year", "total"]
ATR_FIELDS = ["objectid", "pm_id", "road", "location", "agency", "onetwoway", "year", "avgtot"]
DIRECTION = {1: "one_direction", 2: "both"}       # onetwoway, read as a number ('2', '2.0', 2)


def location_text(props):
    """'ACHD', 'Example Rd', 'e/o  Sample Ave' -> 'achd|example rd|e/o sample ave'."""
    return "|".join((text(props.get(f)) or "").lower() for f in ("agency", "road", "location"))


def portable_key(props):
    """By segment; by location text where the pm_id is a placeholder."""
    seg = pm_id(props.get("pm_id"))
    return f"pm:{seg}" if seg else f"loc:{location_text(props)}"


def atr_key(props):
    return f"loc:{location_text(props)}|{pm_id(props.get('pm_id')) or ''}"


def count_row(props, count_type):
    """Our obs.traffic_count row (without source and key); None without a year."""
    year = integer(props.get("year"))
    if not year:
        return None
    month = integer(props.get("month")) if count_type == "short" else None
    monthly = month is not None and 1 <= month <= 12
    return {
        "counted_on": date(year, month if monthly else 1, 1),
        "period": "month" if monthly else "year",
        "direction": DIRECTION.get(integer(props.get("onetwoway"))),        # None when unknown
        "count_type": count_type,
        "count_24h": integer(props.get("total" if count_type == "short" else "avgtot")),
        "agency": text(props.get("agency")),
        "road": text(props.get("road")),
        "location": text(props.get("location")),
        "pm_id": pm_id(props.get("pm_id")),
    }


def count_store(source, count_type, location_key):
    def store(conn, fetch_id, seen_at, got):
        pairs, repeats, suffixed = cl.keyed([p for p, _ in got.rows], key=location_key,
                                            content=lambda p: cl.content(p, None, got.oid))
        rows, no_year = [], 0
        for k, p in pairs:
            row = count_row(p, count_type)
            if row:
                rows.append({"source": source["name"], "location_key": k, **row})
            else:
                no_year += 1
        cl.check_share(got, len(rows), cl.current_records(conn, source["name"]), source["name"])
        stats = cl.store_records(conn, source["name"], [(k, cl.without(p, got.oid), None) for k, p in pairs],
                                 fetch_id, seen_at, got.complete)
        cl.upsert(conn, "obs.traffic_count", ["source", "location_key", "counted_on"], rows, seen_at, active=False)
        unknown = sum(1 for r in rows if r["direction"] is None)
        if unknown:
            print(f"{source['name']}: {unknown} counts with an unknown onetwoway (direction stored as null)",
                  flush=True)
        return {**stats, "stored": len(rows), "without year": no_year, "direction unknown": unknown,
                "exact repeats dropped": repeats, "keys suffixed": suffixed, "pm_id placeholders": sum(
                    1 for p, _ in got.rows if text(p.get("pm_id")) and not pm_id(p.get("pm_id")))}
    return store


LAYERS = [
    cl.Layer("portable", PORTABLE, SERVICE + "/4", PORTABLE_FIELDS, count_store(PORTABLE, "short", portable_key),
             geometry=False),
    cl.Layer("atr", ATR, SERVICE + "/5", ATR_FIELDS, count_store(ATR, "permanent", atr_key), geometry=False),
]


def run(conn):
    return cl.run(conn, SOURCE, LAYERS)
