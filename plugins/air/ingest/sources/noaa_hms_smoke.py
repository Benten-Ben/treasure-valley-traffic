"""NOAA's Hazard Mapping System (HMS) smoke polygons that touch the ring (docs/17 §17.4, Wave A).

HMS analysts at NOAA NESDIS OSPO trace the smoke they see on satellite
imagery as polygons rated light, medium or heavy, each with its satellite and
the start and end of the imagery it was traced on. NOAA publishes one KML a
day, national, at
https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/KML/YYYY/MM/hms_smokeYYYYMMDD.kml.
The day's file exists from early morning (empty), is rewritten as each
analysis lands (the first 11 AM-12 PM ET, the second 7-8 PM ET) and is
finalised about 10:00 UTC the next morning. Only the current file says what
was drawn when, so the versions in between exist only if we poll them
(docs/sources/hazards.md, "NOAA Hazard Mapping System"; gardening.md, "Heat,
smoke, air and alerts").

Each run (every 30 minutes):
1. reads the month's directory listing (one ~2 KB request; two in a month's
   first days), whose times are UTC (they match each file's "Generated" stamp);
2. downloads a watched file (today, yesterday and the day before, UTC) only
   if the listing shows it changed since we last saw it, or we never have;
3. a file whose smoke is unchanged only moves last_seen. A changed one is
   archived as published, gzipped, when TVT_ARCHIVE is set
   ($TVT_ARCHIVE/air/hms/YYYY/MM/hms_smokeYYYYMMDD-<generated>-<digest>.kml.gz),
   then versioned in raw.record: one record for the product file (analysis
   date, when NOAA generated it, a digest of its smoke and national counts)
   and one per polygon that touches the ring, kept whole (not clipped).
   Records of that day that the new version no longer has get removed_at: each
   file is a full snapshot of its own day, so the latest version of every
   record of a day is the one with removed_at null.

A polygon's source_id is its day, satellite, imagery window, density and
ordinal among the ring's polygons with those four (e.g.
"20261006/GOES-WEST/20261006T1200Z-20261006T1500Z/light/1"), so a new
analysis later in the day doesn't renumber earlier ones. The file's record is
"20261006". Polygons are stored as published: HMS has zero-area slivers
(A, B, B, A) and self-touching rings, so use ST_MakeValid before area maths.

Care (hazards.md): HMS shows smoke anywhere in the column, not at the ground,
and only by day; NOAA says positions "may be slightly offset" and the
product isn't for tactical decisions. Densities were numbers (5, 16, 27)
before July 19, 2022; they're normalised to light, medium and heavy, and the
published value is kept.
"""

import gzip
import hashlib
import json
import math
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from ingest import db, http

HOST = "satepsanone.nesdis.noaa.gov"
BASE = f"https://{HOST}/pub/FIRE/web/HMS/Smoke_Polygons/KML/"
RING = (-117.30, 42.90, -115.60, 44.30)     # west, south, east, north: the regional ring (DECISIONS, Oct 5-6)
WATCH_DAYS = 3                              # today, yesterday (final about 10:00 UTC today), and a day's margin
CHANGE_MARGIN = timedelta(minutes=10)       # the listing's minute resolution plus clock skew
SNAPSHOT_MIN_SHARE = 0.5                    # a day's file may grow; one that loses half its polygons is refused
SNAPSHOT_GUARD_FROM = 5                     # ... once it has had this many (small counts are noise)
PACE_S = 3.0

# robots.txt answers 404 (no rules, re-checked Oct 7) and asks for no delay; keep 3 s between our requests.
http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), PACE_S)

SOURCE = {
    "name": "noaa_hms_smoke",
    "title": "NOAA HMS smoke polygons over the ring",
    "url": "https://www.ospo.noaa.gov/products/land/hms.html",
    "access": "open",
    "schedule": "30 minutes",
    "license": "public domain (U.S. Government work, NOAA)",
    "credit": "NOAA NESDIS OSPO Hazard Mapping System",
    "notes": "The month's listing every 30 min; today's, yesterday's and the day before's KML downloaded only when "
             "listed as changed; changed files archived in $TVT_ARCHIVE/air/hms/; per-day file records and the "
             "polygons touching the ring versioned in raw.record. Smoke in the column, not at the ground.",
}

LISTED = re.compile(r'href="(hms_smoke\d{8}\.kml)"', re.I)
LISTED_TIME = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
DENSITY = {"light": "light", "medium": "medium", "heavy": "heavy",
           "5": "light", "16": "medium", "27": "heavy"}         # numbers before July 19, 2022
HMS_TIME = re.compile(r"^\s*(\d{4})(\d{3})\s*(\d{2})(\d{2})\s*(?:UTC|Z|GMT)?\s*$", re.I)


# --- where and when -------------------------------------------------------------------------

def file_name(day):
    return f"hms_smoke{day:%Y%m%d}.kml"


def month_url(year, month):
    return f"{BASE}{year:04d}/{month:02d}/"


def file_url(day):
    return f"{month_url(day.year, day.month)}{file_name(day)}"


def watch_days(now):
    """The UTC days whose files may still change, oldest first."""
    today = now.astimezone(timezone.utc).date()
    return [today - timedelta(days=k) for k in range(WATCH_DAYS - 1, -1, -1)]


def parse_listing(body):
    """An Apache index page -> {file name: last modified (UTC datetime, or None)}."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    out = {}
    for row in re.split(r"<tr", text, flags=re.I):
        m = LISTED.search(row)
        if not m:
            continue
        t = LISTED_TIME.search(row[m.end():])
        out[m.group(1)] = (datetime.strptime(t.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                           if t else None)
    return out


def needs_download(listed_at, last_seen):
    """Download unless the listing's time is safely older than our last look at the file."""
    if last_seen is None or listed_at is None:
        return True
    return listed_at + CHANGE_MARGIN >= last_seen


# --- the KML ----------------------------------------------------------------------------------

def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def _child(el, name):
    for c in el:
        if _tag(c) == name:
            return c
    return None


def _children(el, name):
    return [c for c in el if _tag(c) == name]


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def hms_time(s):
    """'2026279 1200UTC' (year, day of year, HHMM) -> '2026-10-06T12:00:00Z', or None."""
    m = HMS_TIME.match(s or "")
    if not m:
        return None
    year, doy, hh, mm = (int(g) for g in m.groups())
    if not (1 <= doy <= 366 and hh <= 23 and mm <= 59):
        return None
    t = datetime(year, 1, 1, hh, mm, tzinfo=timezone.utc) + timedelta(days=doy - 1)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t.year == year else None


def density(fields, folder):
    """light, medium or heavy, from the published density (word or pre-2022 number), else the folder's name."""
    raw = (fields.get("Density") or "").strip().lower()
    try:
        raw = str(int(float(raw))) if raw and raw[0].isdigit() else raw
    except ValueError:
        pass
    if raw in DENSITY:
        return DENSITY[raw]
    m = re.search(r"\((\w+)\)", folder or "")
    return DENSITY.get(m.group(1).lower()) if m else None


def description_fields(html):
    """'<div>Start Time: 2026279 1200UTC<br>Density: Light</div>' -> {'Start Time': ..., 'Density': ...}."""
    fields = {}
    for part in re.split(r"<br\s*/?>|</?div[^>]*>|</?p[^>]*>|\n", html or "", flags=re.I):
        part = re.sub(r"<[^>]+>", "", part).strip()
        key, sep, value = part.partition(":")
        if sep and key.strip() and len(key) <= 40:
            fields[" ".join(key.split())] = value.strip()
    return fields


def _coords(el):
    """A <coordinates> element -> [[lon, lat], ...] (altitude dropped). Raises ValueError on junk."""
    out = []
    for token in _text(el).split():
        parts = token.split(",")
        lon, lat = (float(v) for v in parts[:2]) if len(parts) >= 2 else (math.nan, math.nan)
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):          # also NaN, which JSON can't carry
            raise ValueError(f"bad coordinate {token!r}")
        out.append([lon, lat])
    return out


def _ring(boundary, fixes):
    lr = _child(boundary, "LinearRing") if boundary is not None else None
    el = _child(lr, "coordinates") if lr is not None else None
    coords = _coords(el) if el is not None else []
    if coords and coords[0] != coords[-1]:
        coords.append(list(coords[0]))
        fixes.append("ring_closed")
    return coords if len(coords) >= 4 else None


def geometry(placemark, fixes):
    """The placemark's polygons as GeoJSON (Polygon, or MultiPolygon for several), or None."""
    polygons = []
    for poly in (el for el in placemark.iter() if _tag(el) == "Polygon"):
        try:
            outer = _ring(_child(poly, "outerBoundaryIs"), fixes)
            if outer is None:
                fixes.append("polygon_without_ring")
                continue
            holes = [r for r in (_ring(b, fixes) for b in _children(poly, "innerBoundaryIs")) if r]
        except ValueError:
            fixes.append("bad_coordinates")
            continue
        polygons.append([outer] + holes)
    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def _placemark(pm, folder):
    fields = description_fields(_text(_child(pm, "description")))
    ext = _child(pm, "ExtendedData")
    if ext is not None:      # not in today's files; kept if NOAA adds it
        for el in ext.iter():
            if _tag(el) in ("Data", "SimpleData") and el.get("name"):
                v = _child(el, "value") if _tag(el) == "Data" else el
                fields[el.get("name")] = _text(v)
    fixes = []
    geom = geometry(pm, fixes)
    satellite = " ".join((fields.get("Satellite") or "").split()) or None
    return {
        "folder": folder,
        "fields": fields,
        "density": density(fields, folder),
        "satellite": satellite,
        "start": hms_time(fields.get("Start Time")),
        "end": hms_time(fields.get("End Time")),
        "geometry": geom,
        "fixes": fixes,
    }


def _walk(el, folder, out):
    for c in el:
        t = _tag(c)
        if t == "Placemark":
            out.append(_placemark(c, folder))
        elif t in ("Folder", "Document"):
            _walk(c, _text(_child(c, "name")) or folder, out)


def _overlay_text(root):
    """The overlays' names and decoded hrefs: where the analysis date and generation time are written."""
    parts = []
    for el in root.iter():
        if _tag(el) == "ScreenOverlay":
            icon = _child(el, "Icon")
            href = _text(_child(icon, "href")) if icon is not None else ""
            parts.append(f"{_text(_child(el, 'name'))} {urllib.parse.unquote(href)}")
    return "\n".join(parts)


def content_digest(day, placemarks):
    """Of the day's smoke as analysed (every polygon, nationally), so a file NOAA regenerates
    without changes (a new "Generated" stamp) counts as unchanged."""
    body = [{k: p[k] for k in ("folder", "fields", "geometry", "fixes")} for p in placemarks]
    text = json.dumps([day.isoformat(), body], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def parse_kml(body, day):
    """One day's smoke KML -> {analysis_date, generated, placemarks, content_sha256}. Raises ValueError
    for a broken file or one for another day (it isn't taken as this day's snapshot)."""
    if b"<!ENTITY" in body[:4096]:
        raise ValueError("entity declarations in the KML; refused")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise ValueError(f"not a complete KML: {err}") from None
    if _tag(root) != "kml":
        raise ValueError(f"not a KML document (root {_tag(root)!r})")
    doc = _child(root, "Document")
    if doc is None:
        raise ValueError("KML without a Document")
    ymd = f"{day:%Y%m%d}"
    name = _text(_child(doc, "name"))
    overlays = _overlay_text(root)
    stated = re.findall(r"(\d{8})\s*$", name) + re.findall(r"Analysis for:\s*(\d{8})", overlays)
    if any(s != ymd for s in stated):
        raise ValueError(f"file for {day} says it's for {', '.join(sorted(set(stated)))}")
    g = re.search(r"Generated:\s*(\d{2})(\d{2})\s*(?:GMT|UTC)\s*(\d{8})", overlays)
    generated = None
    if g:
        try:
            generated = datetime.strptime(g.group(3) + g.group(1) + g.group(2), "%Y%m%d%H%M").replace(
                tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            pass
    placemarks = []
    _walk(doc, None, placemarks)
    return {"analysis_date": day.isoformat(), "generated": generated, "placemarks": placemarks,
            "content_sha256": content_digest(day, placemarks)}


# --- the ring -----------------------------------------------------------------------------------

def _in_box(x, y, box):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _inside(x, y, rings):
    """Even-odd point in polygon (outer ring and holes)."""
    inside = False
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def _orient(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (v > 0) - (v < 0)


def _on_segment(a, b, p):
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def _cross(a, b, c, d):
    """Do segments ab and cd meet (touching counts)?"""
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return ((o1 == 0 and _on_segment(a, b, c)) or (o2 == 0 and _on_segment(a, b, d))
            or (o3 == 0 and _on_segment(c, d, a)) or (o4 == 0 and _on_segment(c, d, b)))


def touches_box(geom, box=RING):
    """Does a GeoJSON Polygon or MultiPolygon meet the box (west, south, east, north)?"""
    if not geom:
        return False
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    w, s, e, n = box
    corners = [(w, s), (e, s), (e, n), (w, n)]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    for rings in polys:
        xs = [x for ring in rings for x, _ in ring]
        ys = [y for ring in rings for _, y in ring]
        if not xs or max(xs) < w or min(xs) > e or max(ys) < s or min(ys) > n:
            continue
        if any(_in_box(x, y, box) for ring in rings for x, y in ring):
            return True
        if any(_inside(x, y, rings) for x, y in corners):
            return True
        if any(_cross(a, b, c, d) for ring in rings for a, b in zip(ring, ring[1:]) for c, d in edges):
            return True
    return False


# --- records ------------------------------------------------------------------------------------

def file_id(day):
    return f"{day:%Y%m%d}"


def _compact_time(iso, raw):
    if iso:
        return iso[:13].replace("-", "") + iso[14:16] + "Z"            # 2026-10-06T12:00:00Z -> 20261006T1200Z
    return re.sub(r"[^0-9A-Za-z]+", "", raw or "") or "unknown"


def records(day, parsed, box=RING):
    """-> (file record, [(source_id, payload, geometry)] for the polygons touching the box)."""
    name = file_name(day)
    ring, ordinal = [], {}
    for p in parsed["placemarks"]:
        if not touches_box(p["geometry"], box):
            continue
        sat = re.sub(r"\s+", "_", p["satellite"] or "unknown")
        window = (f"{_compact_time(p['start'], p['fields'].get('Start Time'))}-"
                  f"{_compact_time(p['end'], p['fields'].get('End Time'))}")
        key = f"{file_id(day)}/{sat}/{window}/{p['density'] or 'unknown'}"
        ordinal[key] = ordinal.get(key, 0) + 1
        payload = {"analysis_date": parsed["analysis_date"], "file": name, **p}
        ring.append((f"{key}/{ordinal[key]}", payload, p["geometry"]))
    by_density, by_satellite = {}, {}
    for p in parsed["placemarks"]:
        by_density[p["density"] or "unknown"] = by_density.get(p["density"] or "unknown", 0) + 1
        by_satellite[p["satellite"] or "unknown"] = by_satellite.get(p["satellite"] or "unknown", 0) + 1
    file_payload = {
        "file": name,
        "url": file_url(day),
        "analysis_date": parsed["analysis_date"],
        "generated": parsed["generated"],
        "content_sha256": parsed["content_sha256"],
        "polygons": len(parsed["placemarks"]),
        "without_geometry": sum(1 for p in parsed["placemarks"] if p["geometry"] is None),
        "by_density": by_density,
        "by_satellite": by_satellite,
        "ring": list(box),
        "in_ring": len(ring),
    }
    return (file_id(day), file_payload, None), ring


def check_file_snapshot(previous, n, label):
    """Refuse a day's file that lost most of the polygons its last version had: a day's analysis
    grows, so that looks like a cut-off file. The fetch fails and nothing is stored (the file is
    already archived)."""
    if previous is not None and previous >= SNAPSHOT_GUARD_FROM and n < SNAPSHOT_MIN_SHARE * previous:
        raise RuntimeError(f"{label}: only {n} polygons against {previous} in its last version; "
                           f"not taken as the day's snapshot")


def current(conn, day):
    """(payload, last_seen) of the day's file record as we hold it, or None."""
    return conn.execute(
        """select payload, last_seen from raw.record
           where source = %s and source_id = %s and removed_at is null
           order by last_seen desc limit 1""", (SOURCE["name"], file_id(day))).fetchone()


def heartbeat(conn, day, seen_at):
    """The day's file is unchanged: its records were seen again."""
    return conn.execute(
        """update raw.record set last_seen = %s
           where source = %s and removed_at is null and (source_id = %s or left(source_id, 9) = %s)""",
        (seen_at, SOURCE["name"], file_id(day), file_id(day) + "/")).rowcount


def store(conn, fetch_id, seen_at, day, parsed):
    """Version a changed day's file. Returns counts."""
    file_record, ring = records(day, parsed)
    new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], [file_record] + ring, fetch_id, seen_at,
                                          complete=False)
    removed = conn.execute(
        """update raw.record set removed_at = %s
           where source = %s and removed_at is null and last_seen < %s
             and (source_id = %s or left(source_id, 9) = %s)""",
        (seen_at, SOURCE["name"], seen_at, file_id(day), file_id(day) + "/")).rowcount
    return {"new": new, "unchanged": unchanged, "removed": removed, "in_ring": len(ring)}


# --- the archive --------------------------------------------------------------------------------

def archive_path(root, day, parsed):
    stamp = (parsed["generated"] or "unknown").replace("-", "").replace(":", "")[:13]
    if stamp != "unknown":
        stamp += "Z"
    return os.path.join(root, "air", "hms", f"{day:%Y}", f"{day:%m}",
                        f"hms_smoke{day:%Y%m%d}-{stamp}-{parsed['content_sha256'][:12]}.kml.gz")


def archive(root, day, parsed, body):
    """Keep the file as published, once per distinct content. Returns the path if written now."""
    if not root:
        return None
    path = archive_path(root, day, parsed)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    suffix = f"-{parsed['content_sha256'][:12]}.kml.gz"
    if any(f.startswith(f"hms_smoke{day:%Y%m%d}-") and f.endswith(suffix) for f in os.listdir(folder)):
        return None
    tmp = path + ".part"
    with gzip.open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, path)
    return path


# --- a run ----------------------------------------------------------------------------------------

def poll(conn, fetch, seen_at, root):
    days = watch_days(seen_at)
    stats = {"files watched": len(days), "not listed yet": 0, "unchanged per listing": 0, "downloaded": 0,
             "unchanged": 0, "changed": 0, "archived": 0 if root else "off (TVT_ARCHIVE not set)",
             "record versions new": 0, "removed": 0, "polygons in ring": 0}
    listing, nbytes, touched = {}, 0, 0
    for year, month in sorted({(d.year, d.month) for d in days}):
        status, body, decision = http.get(month_url(year, month), timeout=60, compressed=True)
        nbytes += len(body)
        fetch.http_status, fetch.robots, fetch.bytes = status, decision, nbytes
        listing.update(parse_listing(body))
    for day in days:
        name = file_name(day)
        if name not in listing:
            stats["not listed yet"] += 1
            continue
        held = current(conn, day)
        if held and not needs_download(listing[name], held[1]):
            touched += heartbeat(conn, day, seen_at)
            stats["unchanged per listing"] += 1
            stats["polygons in ring"] += held[0].get("in_ring", 0)
            continue
        status, body, decision = http.get(file_url(day), timeout=120, compressed=True)
        nbytes += len(body)
        fetch.http_status, fetch.robots, fetch.bytes = status, decision, nbytes
        stats["downloaded"] += 1
        parsed = parse_kml(body, day)
        if held and held[0].get("content_sha256") == parsed["content_sha256"]:
            touched += heartbeat(conn, day, seen_at)
            stats["unchanged"] += 1
            stats["polygons in ring"] += held[0].get("in_ring", 0)
            continue
        if archive(root, day, parsed, body):
            stats["archived"] += 1
        check_file_snapshot(held[0].get("polygons") if held else None, len(parsed["placemarks"]),
                            f"{SOURCE['name']} {name}")
        counts = store(conn, fetch.id, seen_at, day, parsed)
        touched += counts["new"] + counts["unchanged"]
        stats["changed"] += 1
        stats["record versions new"] += counts["new"]
        stats["removed"] += counts["removed"]
        stats["polygons in ring"] += counts["in_ring"]
    fetch.records = touched
    return stats


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        stats = poll(conn, f, f.started_at, os.environ.get("TVT_ARCHIVE"))
    return stats
