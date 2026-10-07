"""NOAA SWPC's OVATION aurora nowcast, cut to the sky north of the valley.

One GET of services.swpc.noaa.gov/json/ovation_aurora_latest.json per run.
OVATION Prime 2020 (JHU/APL's empirical model) is driven by the solar wind
measured at L1, so it leads by 30-90 minutes; when solar-wind data are
missing it falls back to Kp, with no lead. The file is the whole globe on a
1° grid: 360 × 181 points of [longitude 0-359 east, latitude, aurora 0-100],
about 900 KB (about 145 KB gzipped), remade every few minutes. SWPC keeps only
the latest file, so history exists only if we poll (docs/17 §17.4, Wave A).

We keep the slice that matters to the valley, 125°W to 105°W and 35°N to
65°N: 21 × 31 = 651 values (docs/sources/sky.md, "NOAA SWPC data service").
The aurora seen from Boise sits overhead hundreds of kilometres to the north
(SWPC: bright aurora can often be seen from as much as 1000 km away), so the
slice reaches well past the ring; cut to the ring it would hold two or three
rows that are nearly always zero.

Each snapshot is ONE raw.record, its source_id the forecast time, holding the
651 values as one array of rows (never one row per value: sky.md correction 6).
complete=False: every forecast time is its own record and none is retired.
The slice is refused whole if a cell is missing or out of range, or the file's
format changes, so a partial grid is never stored as if it were the forecast.
"""

import json
from datetime import datetime, timezone

from ingest import db, http

URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
HOST = "services.swpc.noaa.gov"
WEST, EAST, SOUTH, NORTH = -125, -105, 35, 65        # the slice, whole degrees (grid points)
COLUMNS, ROWS = EAST - WEST + 1, NORTH - SOUTH + 1    # 21 longitudes × 31 latitudes = 651
FORMAT = "[longitude,latitude,aurora]"                # SWPC's "Data Format", spaces and case ignored

# At least 2 s between requests to SWPC (our two sources share the host). robots.txt asks for nothing.
http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), 2)

SOURCE = {
    "name": "swpc_ovation",
    "title": "NOAA SWPC OVATION aurora nowcast (125-105°W, 35-65°N)",
    "url": URL,
    "access": "open",
    "schedule": "30 minutes",
    "retry_after": "10 minutes",      # a missed snapshot is gone for good; one 145 KB request to retry
    "license": "public domain (US government work; no explicit statement)",
    "credit": "NOAA Space Weather Prediction Center (OVATION Prime)",
    "notes": "One GET of the global 1° grid per run; kept: the 651-value slice 125-105°W, 35-65°N, as one "
             "raw.record per forecast time (complete=False). Values are OVATION's 0-100 aurora "
             "probability overhead, not the chance of seeing it from the valley.",
}

GEOMETRY = {"type": "Polygon", "coordinates": [[[WEST, SOUTH], [EAST, SOUTH], [EAST, NORTH], [WEST, NORTH],
                                                [WEST, SOUTH]]]}
GRID = {"west": WEST, "south": SOUTH, "step_deg": 1, "columns": COLUMNS, "rows": ROWS}


def utc(text):
    """SWPC's ISO time ('2026-10-07T14:45:00Z'; naive means UTC) -> aware datetime. ValueError if not one."""
    if not isinstance(text, str):
        raise ValueError(f"not a time: {text!r}")
    t = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _degree(v, what):
    """A whole-degree coordinate; ValueError for anything else (the grid changed)."""
    if not _number(v) or v != int(v):
        raise ValueError(f"OVATION {what} {v!r} isn't a whole degree: the grid has changed")
    return int(v)


def cut(doc):
    """The slice from one OVATION file: {"observation_time", "forecast_time", "grid", "aurora"}, where
    aurora is ROWS lists from 35°N north to 65°N, each COLUMNS values from 125°W east to 105°W.
    Raises ValueError for a file we can't trust: another format, a bad time, a missing,
    repeated-but-different or out-of-range cell in the slice."""
    if not isinstance(doc, dict):
        raise ValueError("OVATION: not a JSON object")
    fmt = "".join(str(doc.get("Data Format", "")).split()).lower()
    if fmt != FORMAT:
        raise ValueError(f"OVATION: unexpected Data Format {doc.get('Data Format')!r}")
    observed, forecast = utc(doc.get("Observation Time")), utc(doc.get("Forecast Time"))
    points = doc.get("coordinates")
    if not isinstance(points, list):
        raise ValueError("OVATION: no coordinates list")
    cells = {}
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) < 3 or not _number(p[0]) or not _number(p[1]):
            raise ValueError(f"OVATION: bad point {p!r}")
        lon = (p[0] + 180) % 360 - 180          # 0-359 east (or already -180-180) -> -180-180
        lat = p[1]
        if not (WEST - 1 < lon < EAST + 1 and SOUTH - 1 < lat < NORTH + 1):
            continue
        lon, lat = _degree(lon, "longitude"), _degree(lat, "latitude")
        if not (WEST <= lon <= EAST and SOUTH <= lat <= NORTH):
            continue
        v = p[2]
        if not _number(v) or not 0 <= v <= 100:
            raise ValueError(f"OVATION: value {v!r} at {lon}, {lat} is out of range")
        if cells.get((lon, lat), v) != v:
            raise ValueError(f"OVATION: two different values at {lon}, {lat}")
        cells[(lon, lat)] = v
    if len(cells) != COLUMNS * ROWS:
        raise ValueError(f"OVATION: {COLUMNS * ROWS - len(cells)} of {COLUMNS * ROWS} cells missing from the slice")
    aurora = [[cells[(lon, lat)] for lon in range(WEST, EAST + 1)] for lat in range(SOUTH, NORTH + 1)]
    return {"observation_time": iso(observed), "forecast_time": iso(forecast), "grid": GRID, "aurora": aurora}


def value(snapshot, lon, lat):
    """One cell of a stored snapshot, by whole-degree longitude (negative west) and latitude."""
    return snapshot["aurora"][lat - SOUTH][lon - WEST]


def record(snapshot):
    """(source_id, payload, geometry) for raw.record: one per forecast time."""
    return snapshot["forecast_time"], snapshot, GEOMETRY


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.http_status, body, f.robots = http.get(URL, timeout=60, compressed=True)
        f.bytes = len(body)
        snapshot = cut(json.loads(body))
        f.records = 1
        new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], [record(snapshot)], f.id, f.started_at,
                                              complete=False)
    flat = [v for row in snapshot["aurora"] for v in row]
    return {"forecast": snapshot["forecast_time"], "observed": snapshot["observation_time"],
            "cells": len(flat), "max": max(flat), "new": new, "unchanged": unchanged}
