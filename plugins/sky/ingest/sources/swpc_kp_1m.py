"""NOAA SWPC's estimated planetary Kp, every minute, kept by the UTC hour.

One GET of services.swpc.noaa.gov/json/planetary_k_index_1m.json per run:
about the last six hours of SWPC's real-time estimate of the planetary K
index, one entry a minute ({"time_tag", "kp_index", "estimated_kp", "kp"};
about 28 KB, 1.3 KB gzipped). The estimate as it stood in real time isn't kept
anywhere we can read later, so history exists only if we poll (docs/17 §17.4).
The definitive 3-hourly Kp since 1932 is GFZ's (CC BY), which can be fetched
any time; it isn't needed to start a clock.

Each complete UTC hour is ONE raw.record, its source_id the hour's start,
holding the 60 estimated_kp values as one array (null for a minute the file
lacks): 24 rows a day rather than 1,440 (sky.md correction 6: Kp kept
compactly). An hour is stored only once the file holds both its first and its
last minute, so a record never gets a partial version; the hour in progress
waits for the next run. With a six-hour window and an hourly schedule, about
five runs in a row can fail before a minute is lost.

kp_index and kp are SWPC's integer and its label in thirds ("2P" is 2+,
"3M" is 3-) of estimated_kp; both are dropped when they're exactly what
estimated_kp gives, and kept under "labels" for any minute where they aren't.
complete=False: hours are never retired.
"""

import json
import math
from datetime import timedelta

from ingest import db, http

from .swpc_ovation import HOST, iso, utc

URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)

http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), 2)

SOURCE = {
    "name": "swpc_kp_1m",
    "title": "NOAA SWPC estimated planetary Kp, 1-minute",
    "url": URL,
    "access": "open",
    "schedule": "1 hour",
    "license": "public domain (US government work; no explicit statement)",
    "credit": "NOAA Space Weather Prediction Center",
    "notes": "One GET per run of about the last six hours, one value a minute; kept: one raw.record per "
             "complete UTC hour (60 values, complete=False). kp_index and the kp label are kept only "
             "where they differ from what estimated_kp gives.",
}


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def derived(kp):
    """(kp_index, kp label) as SWPC derives them from estimated_kp in thirds: 0.33 -> (0, "0P"),
    0.67 -> (1, "1M"), 1.0 -> (1, "1Z"). (None, None) for None; label None off the thirds."""
    if kp is None:
        return None, None
    n = math.floor(kp + 0.5)
    d = round(kp - n, 2)
    suffix = "Z" if d == 0 else "P" if abs(d - 0.33) < 0.005 else "M" if abs(d + 0.33) < 0.005 else None
    return n, (f"{n}{suffix}" if suffix else None)


def minutes(rows):
    """{minute (aware UTC): entry} from the file. Raises ValueError on an unreadable time, an
    estimate outside 0-9, or the same minute twice with different values."""
    if not isinstance(rows, list):
        raise ValueError("Kp: not a JSON list")
    out = {}
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError(f"Kp: bad entry {r!r}")
        t = utc(r.get("time_tag"))
        if t.second or t.microsecond:
            raise ValueError(f"Kp: {r.get('time_tag')!r} isn't on a whole minute")
        e = r.get("estimated_kp")
        if e is not None and (not _number(e) or not 0 <= e <= 9):
            raise ValueError(f"Kp: estimated_kp {e!r} at {r.get('time_tag')} is out of range")
        entry = {"estimated_kp": e, "kp_index": r.get("kp_index"), "kp": r.get("kp")}
        if out.get(t, entry) != entry:
            raise ValueError(f"Kp: two different entries at {r.get('time_tag')}")
        out[t] = entry
    return out


def hours(by_minute):
    """[(hour start, payload)] for every UTC hour the file holds from its first to its last minute,
    oldest first. Hours with no value at all (an outage) are skipped."""
    if not by_minute:
        return []
    first, last = min(by_minute), max(by_minute)
    start = first.replace(minute=0)
    if start < first:
        start += HOUR
    out = []
    while start + HOUR - MINUTE <= last:
        entries = [by_minute.get(start + i * MINUTE) for i in range(60)]
        if any(e is not None for e in entries):
            values = [e["estimated_kp"] if e else None for e in entries]
            payload = {"start": iso(start), "step_s": 60, "estimated_kp": values}
            labels = {str(i): [e["kp_index"], e["kp"]] for i, e in enumerate(entries)
                      if e and derived(e["estimated_kp"]) != (e["kp_index"], e["kp"])}
            if labels:
                payload["labels"] = labels
            out.append((start, payload))
        start += HOUR
    return out


def records(by_minute):
    """(source_id, payload, geometry) for raw.record: one per complete hour; Kp is planetary, no geometry."""
    return [(iso(start), payload, None) for start, payload in hours(by_minute)]


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.http_status, body, f.robots = http.get(URL, timeout=60, compressed=True)
        f.bytes = len(body)
        by_minute = minutes(json.loads(body))
        recs = records(by_minute)
        f.records = len(recs)
        new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], recs, f.id, f.started_at, complete=False)
    values = [e["estimated_kp"] for e in by_minute.values() if e["estimated_kp"] is not None]
    latest = max(by_minute) if by_minute else None
    return {"minutes": len(by_minute), "hours": len(recs), "new": new, "unchanged": unchanged,
            "latest": iso(latest) if latest else None,
            "latest kp": by_minute[latest]["estimated_kp"] if latest else None,
            "max kp": max(values) if values else None}
