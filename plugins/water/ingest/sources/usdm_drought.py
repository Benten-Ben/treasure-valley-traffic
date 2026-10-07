"""The U.S. Drought Monitor's weekly county statistics for the ring's ten counties, with drought lifecycles.

NDMC's statistics service (usdmdataservices.unl.edu; robots.txt 404, so no
rules), percent of each county's area in each category, categorical
(statisticsType=2: None, D0, D1, D2, D3 and D4 add up to 100): Ada, Boise,
Canyon, Elmore, Gem, Owyhee, Payette, Valley and Washington in Idaho, and
Malheur in Oregon. Valley is in because the ring takes in its south-west
corner (Cozy Cove SNOTEL); whether Baker County, Oregon, touches the ring's
north edge wasn't checked. Maps are valid from Tuesday and released on
Thursday. docs/sources/farm.md and hazards.md, "U.S. Drought Monitor". The
polygons themselves aren't collected: the official files sit under a
robots-disallowed path, and county statistics are what the catalogs
recommend (docs/17, Farms and crops).

Twice a day, one call: from four weeks before the latest map we hold (a
revised map is caught) to today; the first run reads the whole archive
since Jan 4, 2000 (about 14,000 rows, one call). Each county and map is a
reading in raw.record, `<FIPS>:<MapDate>`, as published (percentages as
numbers); only new or changed versions are written.

Lifecycles in evt.event: one event per county, category and episode while
the county has any area in that category or worse ("D1 or worse": D1 + D2
+ D3 + D4, so an episode doesn't end when its area gets worse). Its id is
`<FIPS>:<category>:<first map>`; `declared` runs from the first map's valid
start to the latest map's valid end; area_pct and map_date are the latest
map's. A run refuses to update the lifecycles if the latest map doesn't
cover all ten counties.

Credit (required by NDMC's permission page): "The U.S. Drought Monitor is
jointly produced by the National Drought Mitigation Center at the University
of Nebraska-Lincoln, the United States Department of Agriculture, the
National Oceanic and Atmospheric Administration and the National Aeronautics
and Space Administration. Map courtesy of NDMC."
"""

import csv
import io
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from ingest import db, events, http

from ..common import store_readings

API = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"
http.PACE_S.setdefault("usdmdataservices.unl.edu", 2.0)

COUNTIES = {"16001": "Ada", "16015": "Boise", "16027": "Canyon", "16039": "Elmore", "16045": "Gem",
            "16073": "Owyhee", "16075": "Payette", "16085": "Valley", "16087": "Washington", "41045": "Malheur"}
CATEGORIES = ("D0", "D1", "D2", "D3", "D4")
LABELS = {"D0": "abnormally dry", "D1": "moderate drought", "D2": "severe drought", "D3": "extreme drought",
          "D4": "exceptional drought"}
FIRST_MAP = date(2000, 1, 4)
LOOKBACK = timedelta(weeks=4)

SOURCE = {
    "name": "usdm_drought",
    "title": "U.S. Drought Monitor weekly county statistics for the ring's ten counties",
    "url": "https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx",
    "access": "open",
    "schedule": "12 hours",
    "license": "free to reproduce with the required credit (NDMC permission page)",
    "credit": "U.S. Drought Monitor: National Drought Mitigation Center (University of Nebraska-Lincoln), "
              "USDA, NOAA and NASA; map courtesy of NDMC",
    "notes": "Categorical county statistics (statisticsType=2), one call per run from four weeks before the "
             "latest map held; the first run reads the archive since 2000. Episodes of 'Dn or worse' per "
             "county in evt.event.",
}


def query_url(start, end, counties=COUNTIES):
    q = {"aoi": ",".join(counties), "startdate": f"{start.month}/{start.day}/{start.year}",
         "enddate": f"{end.month}/{end.day}/{end.year}", "statisticsType": "2"}
    return API + "?" + urllib.parse.urlencode(q, safe=",/")


def _number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_csv(text, counties=COUNTIES):
    """The rows for our counties: MapDate (YYYYMMDD), FIPS, County, State, ValidStart and ValidEnd
    as published, the six percentages as numbers."""
    rows = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if r.get("FIPS") not in counties:
            continue
        try:
            datetime.strptime(r.get("MapDate", ""), "%Y%m%d")
        except ValueError:
            continue
        row = {k: r.get(k) or None for k in ("MapDate", "FIPS", "County", "State", "ValidStart", "ValidEnd",
                                              "StatisticFormatID")}
        row.update({k: _number(r.get(k)) for k in ("None",) + CATEGORIES})
        rows.append(row)
    return rows


def records(rows):
    return [(f"{r['FIPS']}:{r['MapDate']}", r, None) for r in rows]


def window_start(latest_held):
    """Four weeks before the latest map held (YYYYMMDD), or the archive's first map."""
    if not latest_held:
        return FIRST_MAP
    return max(FIRST_MAP, datetime.strptime(latest_held, "%Y%m%d").date() - LOOKBACK)


def or_worse(row, category):
    """Percent of the area in `category` or worse."""
    return round(sum(row.get(c) or 0 for c in CATEGORIES[CATEGORIES.index(category):]), 2)


def _day(text):
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _map_day(map_date):
    return f"{map_date[:4]}-{map_date[4:6]}-{map_date[6:]}"


def valid_start(row):
    """The map's valid start as UTC midnight (the map date if the column is blank)."""
    return _day(row.get("ValidStart") or _map_day(row["MapDate"]))


def valid_until(row):
    """The day after the map's valid end, as UTC midnight: the end of a half-open range."""
    end = _day(row["ValidEnd"]) if row.get("ValidEnd") else valid_start(row) + timedelta(days=6)
    return end + timedelta(days=1)


def drought_rows(rows, active, counties=COUNTIES):
    """evt.event rows for the latest map. rows: the window read this run; active: {(FIPS,
    category): {"source_id", "start", "attributes"}} of open episodes. An episode whose run of
    weeks reaches back to the window's first week continues the open one (keeping its id and
    start); without one, its start is a lower bound."""
    if not rows:
        raise RuntimeError("no drought statistics in the window")
    latest = max(r["MapDate"] for r in rows)
    weeks = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["MapDate"]):
        weeks[r["FIPS"]].append(r)
    missing = sorted(f for f in counties if not weeks[f] or weeks[f][-1]["MapDate"] != latest)
    if missing:
        raise RuntimeError(f"the latest map ({latest}) lacks counties {', '.join(missing)}; lifecycles not updated")
    out = []
    for fips in sorted(counties):
        series, last = weeks[fips], weeks[fips][-1]
        for cat in CATEGORIES:
            pct = or_worse(last, cat)
            if pct <= 0:
                continue
            i = len(series) - 1
            while i > 0 and or_worse(series[i - 1], cat) > 0:
                i -= 1
            prev = active.get((fips, cat))
            if i == 0 and prev:
                source_id, start = prev["source_id"], prev["start"]
                since = prev["attributes"].get("since")
                bound = bool(prev["attributes"].get("since_is_lower_bound"))
            else:
                since, start, bound = _map_day(series[i]["MapDate"]), valid_start(series[i]), i == 0
                source_id = f"{fips}:{cat}:{since}"
            out.append({"source_id": source_id, "kind": "drought", "geom": None, "start": start,
                        "end": valid_until(last), "severity": cat,
                        "description": f"{last['County']}, {last['State']}: {cat} ({LABELS[cat]}) or worse",
                        "attributes": {"fips": fips, "county": last["County"], "state": last["State"],
                                       "category": cat, "or_worse": True, "area_pct": pct,
                                       "map_date": _map_day(latest), "since": since,
                                       "since_is_lower_bound": bound}})
    return out


def active_droughts(conn):
    out = {}
    for sid, start, attributes in conn.execute(
            "select source_id, lower(declared), attributes from evt.event where source = %s and active",
            (SOURCE["name"],)).fetchall():
        a = attributes or {}
        out[(a.get("fips"), a.get("category"))] = {"source_id": sid, "attributes": a,
                                                   "start": start.astimezone(timezone.utc) if start else None}
    return out


def latest_held(conn):
    return conn.execute("select max(payload->>'MapDate') from raw.record where source = %s",
                        (SOURCE["name"],)).fetchone()[0]


def store(conn, fetch_id, seen_at, rows):
    new, held = store_readings(conn, SOURCE["name"], records(rows), fetch_id, seen_at)
    out = drought_rows(rows, active_droughts(conn))
    counts = events.upsert(conn, SOURCE["name"], out, seen_at)
    return {"rows": len(rows), "versions new": new, "held": held,
            "latest map": max(r["MapDate"] for r in rows), "episodes open": len(out),
            **{f"episodes {k}": v for k, v in counts.items()}}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        start = window_start(latest_held(conn))
        f.http_status, body, f.robots = http.get(query_url(start, f.started_at.date()), timeout=180, compressed=True)
        f.bytes = len(body)
        rows = parse_csv(body.decode("utf-8", "replace"))
        f.records = len(rows)
        stats = store(conn, f.id, f.started_at, rows)
    return {"from": start.isoformat(), **stats}
