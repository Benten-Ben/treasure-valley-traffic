"""Reclamation AgriMet: daily crop water use (ET) at the six AgriMet stations in the ring.

Static text files under www.usbr.gov/pn/agrimet/chart/, which robots.txt
allows (it disallows only /pn-bin and /gp-bin; /pn-bin is never used here).
Catalogs: docs/sources/farm.md ("USBR AgriMet crop water-use charts") and
docs/sources/gardening.md ("AgriMet crop water-use charts"); ch. 17 §17.2
(Farms and crops) and §17.6 C ("AgriMet history needs /pn-bin": false for ET).

Two files per station, both in inches of water a day:

- `<stn><yy>et.txt`, the year's ET summary: one row per day from Jan 2,
  with ETr (1982 Kimberly-Penman alfalfa reference ET, computed from the
  station's weather) all year and each crop's ET while its calendar runs.
  `--` means the crop isn't growing that day; days can be missing (Parma
  2026 has no 03/30 or 03/31). Cumulative, so every read covers the year.
- `<stn>ch.txt`, the crop chart, "Estimated Crop Water Use": per crop,
  Reclamation's assumed calendar (start, full cover, terminate), the last
  four days, a forecast for the next day, the season's total and 7- and
  14-day use. Columns "4,3,2,1" are the chart's date minus 3, 2, 1 and 0
  days: on Oct 7, 2026 the Oct 6 chart's columns 4-2 matched the year file's
  Oct 3-5 for every crop, and column 1 (Oct 6) wasn't in the year file yet.
  Published April to October.

Repeated crop names are separate calendars (Parma has BEET twice and FCRN
three times), so each file's columns are labelled by position: BEET, BEET#2.
Both files list them in the same order (the Oct 7 sample's BEET ends on the
chart's BEET terminate date, BEET#2 on BEET#2's).

What we keep, in raw.record (complete=False: readings, nothing is retired):
- `PMAI:2026-10-05`: a station-day from the year file,
  {"station", "date", "et_in": {label: inches}}; `--` columns are left out,
  and anything that isn't a number goes in "flags" as written.
- `PMAI:chart:2026-10-06`: a day's chart, {"station", "chart_date", "days"
  (the four dates), "crops": {label: {"start", "full_cover", "terminate",
  "et_in" (four values, oldest first), "forecast_in", "season_in",
  "use_7d_in", "use_14d_in"}}}.
Each record carries the station's point. A revised (provisional) value adds a
version; an unchanged day only moves last_seen.

April to October: every day, each station's chart and year file (12 GETs,
3 s apart). November to March: once a week, the year file only (no chart is
published; ETr runs all year, and the late-winter crop days that start before
April are in the same rows). In the first two weeks of January, last year's
file is read too, to close out December. The static files hold no
temperature, rain, wind or humidity: those are behind /pn-bin, which needs
Reclamation's OK (ch. 17 §17.7). So ETr is the only weather-derived value.

Provisional data: Reclamation's disclaimer says near-real-time values are
not reviewed. The files lag 1-3 days. www.usbr.gov resets HEAD requests, so
only GET is used.
"""

import csv
import io
import re
import urllib.error
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ingest import db, http

HOST = "www.usbr.gov"
CHARTS = f"https://{HOST}/pn/agrimet/chart/"
TZ = ZoneInfo("America/Boise")
http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), 3)    # robots.txt asks for no crawl-delay; 3 s apart

# The regional ring (DECISIONS, "How far the study area reaches"; ch. 17 Q19): west, south, east, north.
RING = (-117.30, 42.90, -115.60, 44.30)

# Every AgriMet station in the ring, from Reclamation's location.csv (read once, Oct 7, 2026):
# code: (longitude, latitude, place, installed, crops). Boise and Boise Fairgrounds carry only ETr and LAWN.
STATIONS = {
    "BOII": (-116.17694, 43.60027, "Boise, Idaho", "1995-07-26", "lawn only"),
    "BFGI": (-116.27417, 43.65303, "Boise Fairgrounds, Idaho", "2013-08-15", "lawn only"),
    "NMPI": (-116.64527, 43.43722, "Nampa, Idaho", "1996-03-11", "crops"),
    "PMAI": (-116.93333, 43.80000, "Parma, Idaho", "1986-03-01", "crops"),
    "ONTO": (-117.01527, 43.97777, "Ontario, Oregon", "1992-04-30", "crops"),
    "GDVI": (-116.05611, 42.91250, "Grand View, Idaho", "1992-10-01", "crops"),
}

SEASON = ((4, 1), (10, 31))           # the charts run April to October (month, day), inclusive
OFF_SEASON_EVERY = timedelta(days=7)  # outside it, the year file once a week
JANUARY_CATCH_UP_DAYS = 14            # early January also reads last year's file, for late December

SOURCE = {
    "name": "agrimet_et",
    "title": "Reclamation AgriMet crop water use (ET), Treasure Valley stations",
    "url": "https://www.usbr.gov/pn/agrimet/h2ouse.html",
    "access": "open",
    "schedule": "1 day",
    "retry_after": "3 hours",
    "license": "U.S. Government work (public domain, inferred); provisional data",
    "credit": "U.S. Bureau of Reclamation, AgriMet",
    "notes": "Static files under /pn/agrimet/chart/ only (robots.txt disallows /pn-bin, never used). "
             "April-October: each station's crop chart and year ET summary daily; November-March: the year "
             "file weekly. Six stations (BOII, BFGI, NMPI, PMAI, ONTO, GDVI); inches a day; provisional.",
}

DAY = re.compile(r"^\d{2}/\d{2}$")
NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
CHART_TITLE = re.compile(r"^Estimated Crop Water Use\s*-\s*(\w+)\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"), start=1)}
# The chart's columns, by header text: our key and whether it's a number (inches) or a month/day.
CHART_FIELDS = {
    "start date": ("start", "md"), "full cover date": ("full_cover", "md"), "terminate date": ("terminate", "md"),
    "daily forecast": ("forecast_in", "num"), "sum et": ("season_in", "num"),
    "7 day use": ("use_7d_in", "num"), "14 day use": ("use_14d_in", "num"),
}


def in_ring(lon, lat):
    w, s, e, n = RING
    return w <= lon <= e and s <= lat <= n


def stations():
    """The station codes we read: every listed station inside the ring."""
    return [code for code, (lon, lat, *_) in STATIONS.items() if in_ring(lon, lat)]


def point(code):
    lon, lat = STATIONS[code][:2]
    return {"type": "Point", "coordinates": [lon, lat]}


def in_season(day):
    return SEASON[0] <= (day.month, day.day) <= SEASON[1]


def local_today(now=None):
    return (now or datetime.now(TZ)).astimezone(TZ).date()


def url(code, kind, year=None):
    if kind == "chart":
        return f"{CHARTS}{code.lower()}ch.txt"
    return f"{CHARTS}{code.lower()}{year % 100:02d}et.txt"


def plan(today):
    """[(station, kind, year)] to read on a run on `today` (America/Boise): in season each station's chart
    and year file; off season the year file only, plus last year's in the first days of January."""
    years = [today.year]
    if not in_season(today) and today.timetuple().tm_yday <= JANUARY_CATCH_UP_DAYS:
        years.insert(0, today.year - 1)
    out = []
    for code in stations():
        if in_season(today):
            out.append((code, "chart", today.year))
        out += [(code, "year", y) for y in years]
    return out


def labels(names):
    """Unique labels for columns by position: a repeated crop name is a separate calendar (BEET, BEET#2)."""
    seen, out = {}, []
    for name in names:
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}#{seen[name]}")
    return out


def number(token):
    token = token.strip()
    return float(token) if NUMBER.match(token) else None


def parse_year(text, code, year):
    """A year's ET summary -> (column labels, {iso date: {"et_in": {...}, "flags"?: {...}}}, malformed rows).
    Refuses a file whose title doesn't name this station and year, or that has no header."""
    lines = text.splitlines()
    title = next((ln.split() for ln in lines if ln.strip()), [])
    if not title or title[0].upper() != code or title[-1] != str(year):
        raise ValueError(f"{code} {year}: the ET summary's title reads {' '.join(title)!r}")
    header = next((ln.split() for ln in lines if ln.split()[:1] == ["DATE"]), None)
    if not header or len(header) < 2:
        raise ValueError(f"{code} {year}: no DATE header in the ET summary")
    cols = labels(header[1:])
    days, malformed = {}, 0
    for ln in lines:
        tokens = ln.split()
        if not tokens or not DAY.match(tokens[0]):
            continue
        try:
            day = date(year, int(tokens[0][:2]), int(tokens[0][3:]))
        except ValueError:
            malformed += 1
            continue
        if len(tokens) != len(header):
            malformed += 1
            continue
        et, flags = {}, {}
        for label, token in zip(cols, tokens[1:]):
            if token == "--":
                continue
            value = number(token)
            if value is None:
                flags[label] = token
            else:
                et[label] = value
        days[day.isoformat()] = {"et_in": et, **({"flags": flags} if flags else {})}
    if malformed > len(days):
        raise ValueError(f"{code} {year}: {malformed} malformed rows against {len(days)} good ones; format changed?")
    return cols, days, malformed


def _month_day(token):
    token = token.strip()
    return token.replace("/", "-") if DAY.match(token) else (token or None)


def parse_chart(text, code):
    """A crop chart -> its payload. Refuses a chart for another station or without its title and header."""
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    title = ",".join(rows[0]).strip().rstrip(",").strip() if rows else ""
    m = CHART_TITLE.match(title)
    if not m or m[1].upper() != code or m[2][:3].lower() not in MONTHS:
        raise ValueError(f"{code}: the crop chart's title reads {title!r}")
    chart_date = date(int(m[4]), MONTHS[m[2][:3].lower()], int(m[3]))
    header = [h.strip() for h in rows[1]] if len(rows) > 1 else []
    if not header or header[0].lower() != "crop":
        raise ValueError(f"{code}: no Crop header in the crop chart")
    # "4,3,2,1": days back from the chart's date, oldest first.
    day_cols = sorted(((i, int(h)) for i, h in enumerate(header) if h.isdigit()), key=lambda c: -c[1])
    days = [(chart_date - timedelta(days=n - 1)).isoformat() for _, n in day_cols]
    body = [r for r in rows[2:] if r[0].strip()]
    crops = {}
    for label, row in zip(labels([r[0].strip() for r in body]), body):
        cells = row + [""] * (len(header) - len(row))
        crop = {"et_in": [number(cells[i]) for i, _ in day_cols]}
        for i, h in enumerate(header):
            if i == 0 or h.isdigit():
                continue
            key, kind = CHART_FIELDS.get(h.lower(), (re.sub(r"\W+", "_", h.lower()).strip("_"), "text"))
            cell = cells[i].strip()
            crop[key] = number(cell) if kind == "num" else _month_day(cell) if kind == "md" else (cell or None)
        crops[label] = crop
    return {"station": code, "chart_date": chart_date.isoformat(), "days": days, "crops": crops}


def check_year(conn, code, year, n):
    """Refuse a year file with far fewer days than we already hold for that station and year: the file is
    cumulative, so a short one is cut off or replaced (the check_snapshot rule, on raw.record)."""
    held = conn.execute(
        """select count(distinct source_id) from raw.record
           where source = %s and removed_at is null and source_id like %s""",
        (SOURCE["name"], f"{code}:{year}-%")).fetchone()[0]
    if held and n < db.SNAPSHOT_MIN_SHARE * held:
        raise RuntimeError(f"{SOURCE['name']} {code} {year}: only {n} days against {held} held; "
                           "not taken as the year's summary")


def records(years, charts):
    """years: {(station, year): days from parse_year}; charts: {station: payload from parse_chart}
    -> [(source_id, payload, geometry)]."""
    out = []
    for (code, _), days in sorted(years.items()):
        out += [(f"{code}:{d}", {"station": code, "date": d, **row}, point(code)) for d, row in sorted(days.items())]
    for code, chart in sorted(charts.items()):
        out.append((f"{code}:chart:{chart['chart_date']}", chart, point(code)))
    return out


def store(conn, fetch_id, seen_at, years, charts):
    """Upsert the records (run() has already checked each year file with check_year)."""
    recs = records(years, charts)
    new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], recs, fetch_id, seen_at, complete=False)
    dates = [d for days in years.values() for d in days]
    return {"record versions new": new, "unchanged": unchanged, "station-days": len(dates),
            "charts": len(charts), "latest day": max(dates) if dates else None}


def last_read(conn):
    """When the files were last actually read (a run that skipped off season logs no HTTP status)."""
    return conn.execute(
        "select max(started_at) from ops.fetch where source = %s and ok and http_status is not null",
        (SOURCE["name"],)).fetchone()[0]


def fetch_text(link, get):
    """(text or None if the file isn't there, status, robots decision, bytes). A 404 (or an HTML error page
    served as 200) counts as missing; any other failure, a robots.txt refusal included, raises."""
    try:
        status, body, decision = get(link, timeout=60, compressed=True)
    except urllib.error.HTTPError as err:
        if err.code in (404, 410):
            err.close()
            return None, err.code, None, 0
        raise
    text = body.decode("utf-8", "replace")
    if "<html" in text[:1000].lower():
        return None, status, decision, len(body)
    return text, status, decision, len(body)


def read(today, get):
    """Read and parse today's files. Returns (years, charts, notes, problems, (status, robots, bytes)).
    A missing file (404) is a note: a station's file may not exist yet (a new year's in early January).
    A file that doesn't parse is a problem; the other stations' files are still kept."""
    years, charts, columns, notes, problems = {}, {}, {}, [], []
    status = decision = None
    nbytes = 0
    for code, kind, year in plan(today):
        text, st, dec, n = fetch_text(url(code, kind, year), get)
        nbytes += n
        if text is None:
            notes.append(f"{code} {kind} {year} missing")
            continue
        status, decision = st, dec
        try:
            if kind == "chart":
                charts[code] = parse_chart(text, code)
            else:
                columns[code], years[(code, year)], bad = parse_year(text, code, year)
                if bad:
                    notes.append(f"{code} {year}: {bad} malformed rows skipped")
        except ValueError as err:
            problems.append(str(err))
    differ = [code for code, chart in charts.items() if code in columns and set(chart["crops"]) != set(columns[code])]
    if differ:
        notes.append("chart and year columns differ at " + ", ".join(differ))
    return years, charts, notes, problems, (status, decision, nbytes)


def run(conn, today=None, get=None):
    get = get or http.get
    today = today or local_today()
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.records = f.bytes = 0
        season = "April-October" if in_season(today) else "off season"
        if not in_season(today):
            last = last_read(conn)
            if last is not None and last + OFF_SEASON_EVERY > db.now():
                return {"season": season, "skipped": f"read weekly; last read {last:%Y-%m-%d}"}
        years, charts, notes, problems, (f.http_status, f.robots, f.bytes) = read(today, get)
        for key in sorted(years):
            try:
                check_year(conn, *key, len(years[key]))
            except RuntimeError as err:
                problems.append(str(err))
                del years[key]
        if not years and not charts:
            raise RuntimeError("no AgriMet file could be read: " + "; ".join(problems + notes))
        f.records = sum(len(d) for d in years.values()) + len(charts)
        stats = store(conn, f.id, f.started_at, years, charts)
        if problems:
            conn.commit()       # keep the stations that were fine; log the run as failed so it's seen
            raise RuntimeError(f"stored {stats['record versions new']} new versions, but: " + "; ".join(problems))
    return {"season": season, **stats, **({"notes": "; ".join(notes)} if notes else {})}
