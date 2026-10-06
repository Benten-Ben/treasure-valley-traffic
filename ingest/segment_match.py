"""Which ACHD road segments a source's lines lie along (core.segment_match; docs/12).

Used by itd_hpms, achd_msm and compass_centerline after each run that changes
them, and meant for OpenStreetMap's ways too. One source line can lie along
many ACHD segments, and one segment can carry several lines: HPMS's A and D
routes and other divided carriageways are two lines along one ACHD
centerline, and both match it.

A segment matches a line when:

- **buffer15_bearing20:** at least 60% of the ACHD segment's length lies
  within 15 m of the line, and their bearings differ by at most 20° (either
  way along the line, so a D route drawn against the A route still matches).
- **buffer10_name:** at least 60% within 10 m, and the street names agree
  (Master Street Map). Names agree whatever the direction prefix, suffix,
  spacing or a small misspelling ('TENMILE RD' is 'N Ten Mile Rd'); route
  designations agree by number ('SH-16' is 'N Hwy 16'). Where the names
  can't be compared (a route designation facing a street name: 'SH-44' runs
  along 'W State St'), the bearing rule decides and the match is recorded as
  buffer10_bearing20. Names that disagree reject the match.

Geometry is measured in SQL in UTM 11N (EPSG:26911, metres). Buffers have
flat ends, so a short segment beyond the end of a line doesn't count as along
it. A segment's bearing is its end-to-end chord; the line's is the chord
between the points on it nearest those two ends. When that second chord is
less than half the first, the segment crosses the line rather than running
along it, and the bearing rule fails. Names that disagree halve a
bearing match's confidence (it isn't rejected: a frontage road 12 m from a
highway is the case this flags).

Rematching deletes and rewrites a source's matches in one transaction (the
caller commits). Canyon County has no ACHD segments, so its lines stay
unmatched and keep their own geometry; the stats say how many unmatched
lines lie away from ACHD's network (no segment within 50 m) and how many lie
near it (real misses).

By hand: python3 -m ingest.segment_match [itd_hpms|achd_msm|compass_centerline ...]
"""

import re
import sys
from difflib import SequenceMatcher

MIN_SHARE = 0.6
MAX_BEARING = 20.0
MIN_PROJECTED = 0.5
NEAR_NETWORK_M = 50
SRID = 26911

METHODS = {
    "buffer15_bearing20": {"near_m": 15, "check": "bearing"},
    "buffer10_name": {"near_m": 10, "check": "name"},
}


# --- the rules (pure functions) ----------------------------------------------

def bearing_diff(a, b):
    """Angle between two bearings in degrees, ignoring direction of travel (0-90)."""
    if a is None or b is None:
        return None
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "NORTH", "SOUTH", "EAST", "WEST", "EB", "WB", "NB", "SB"}
SUFFIXES = {"ROAD": "RD", "AVENUE": "AVE", "AV": "AVE", "BOULEVARD": "BLVD", "STREET": "ST", "HIGHWAY": "HWY",
            "PARKWAY": "PKWY", "LANE": "LN", "DRIVE": "DR", "PLACE": "PL", "COURT": "CT", "CIRCLE": "CIR",
            "TERRACE": "TER", "TRAIL": "TRL", "EXPRESSWAY": "EXPY", "FREEWAY": "FWY", "CROSSING": "XING"}
SUFFIX_ABBREVIATIONS = set(SUFFIXES.values()) | {"WAY", "LOOP", "CV", "SQ", "ALY", "PATH"}
# Route designations ('SH-44', 'I-84/I-184', HPMS's 'SH 55 Main', ACHD's 'N Hwy 16',
# 'WB Interstate 84') are compared by route number, never as street names.
ROUTE_NAME = re.compile(r"^(I|US|SH|SR|STATE HWY|HWY|INTERSTATE)[ -]?\d+\b")
ROUTE_NUMBER = re.compile(r"\b(?:I|US|SH|SR|HWY|HIGHWAY|INTERSTATE)[ -]?(\d{1,3})\b")
SIMILAR = 0.85          # difflib ratio for misspellings ('BROOKESIDE' / 'BROOKSIDE')


def normalize_name(name):
    """'W Fairview Ave.' -> 'FAIRVIEW AVE'; None for blanks and route designations."""
    if not name:
        return None
    s = " ".join(re.sub(r"[^A-Z0-9 ]", " ", str(name).upper()).split())
    tokens = [SUFFIXES.get(t, t) for t in s.split()]
    while len(tokens) > 1 and tokens[0] in DIRECTIONS:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in DIRECTIONS:
        tokens.pop()
    s = " ".join(tokens)
    if not s or ROUTE_NAME.match(s):
        return None
    return s


def route_numbers(name):
    return set(ROUTE_NUMBER.findall(str(name or "").upper().replace("-", " ")))


def _core(normalized):
    """The name without its suffix and spaces: 'TEN MILE RD' -> 'TENMILE'."""
    t = normalized.split()
    if len(t) > 1 and t[-1] in SUFFIX_ABBREVIATIONS:
        t = t[:-1]
    return "".join(t)


def names_agree(a, b):
    """True or False, or None when they can't be compared (a name missing, or a route
    designation facing a street name).

    Street names agree when they're the same street whatever the direction prefix,
    suffix, spacing or a small misspelling: 'N Ten Mile Rd' and 'TENMILE RD',
    'W Linder Ave' and 'LINDER RD', 'Brookside Ln' and 'BROOKESIDE LN', 'Hill Road
    Pkwy' and 'HILL RD'. Route designations agree when they share a route number
    ('SH-16' and 'N Hwy 16')."""
    ra, rb = route_numbers(a), route_numbers(b)
    if ra and rb:
        return bool(ra & rb)
    na, nb = normalize_name(a), normalize_name(b)
    if na is None or nb is None:
        return None
    ca, cb = _core(na), _core(nb)
    if ca == cb:
        return True
    short, long = sorted((ca, cb), key=len)
    if len(short) >= 4 and long.startswith(short):
        return True
    return len(short) >= 6 and SequenceMatcher(None, ca, cb).ratio() >= SIMILAR


def decide(c, method):
    """Whether a candidate is a match, from its measurements.

    c: share (of the ACHD segment within the buffer), chord_m and seg_bearing
    (the segment's end-to-end chord), projected_m and src_bearing (the chord
    between the nearest points on the source line), seg_name, src_name.
    Returns (bearing_diff or None, confidence, method) for a match, else None.
    Under buffer10_name, names that can't be compared fall back to the bearing
    rule, and the match says so (method buffer10_bearing20); names that
    disagree reject it.
    """
    rule = METHODS[method]
    share = c.get("share") or 0.0
    if share < MIN_SHARE:
        return None
    diff = None
    chord, projected = c.get("chord_m") or 0.0, c.get("projected_m") or 0.0
    if chord > 0 and projected >= MIN_PROJECTED * chord:
        diff = bearing_diff(c.get("seg_bearing"), c.get("src_bearing"))
    names = names_agree(c.get("seg_name"), c.get("src_name"))
    bearing_ok = diff is not None and diff <= MAX_BEARING
    if rule["check"] == "bearing":
        if not bearing_ok:
            return None
        confidence = min(share, 1.0) * (1 - diff / 90.0) * (0.5 if names is False else 1.0)
    elif names is True:
        confidence = min(share, 1.0) * (1 - (diff or 0.0) / 90.0)
    elif names is None and bearing_ok:
        method = f"buffer{rule['near_m']}_bearing{int(MAX_BEARING)}"
        confidence = min(share, 1.0) * (1 - diff / 90.0)
    else:
        return None
    return (None if diff is None else round(diff, 1)), round(max(0.0, min(confidence, 1.0)), 3), method


# --- the measurements (SQL) --------------------------------------------------

_SETUP = """
drop table if exists pg_temp.sm_line, pg_temp.sm_buf, pg_temp.sm_seg;
"""

_CANDIDATES = f"""
with ov as (
  select s.id, b.source, b.source_id, sum(ST_Length(ST_Intersection(s.g, b.piece))) as overlap_m
  from sm_buf b join sm_seg s on s.g && b.piece and ST_Intersects(s.g, b.piece)
  group by 1, 2, 3
)
select ov.id, ov.source, ov.source_id, ov.overlap_m, s.len, s.name, l.name,
       degrees(ST_Azimuth(e.p1, e.p2)), ST_Distance(e.p1, e.p2),
       degrees(ST_Azimuth(q.q1, q.q2)), ST_Distance(q.q1, q.q2)
from ov
join sm_seg s on s.id = ov.id
join sm_line l on l.source = ov.source and l.source_id = ov.source_id
cross join lateral (select ST_StartPoint(ST_GeometryN(s.g, 1)) as p1,
                           ST_EndPoint(ST_GeometryN(s.g, ST_NumGeometries(s.g))) as p2) e
cross join lateral (select ST_ClosestPoint(l.g, e.p1) as q1, ST_ClosestPoint(l.g, e.p2) as q2) q
where s.len > 0 and ov.overlap_m >= %(min_share)s * s.len
"""


def candidates(conn, lines_sql, params=None, near_m=15, segments_sql=None):
    """Measure every (ACHD segment, source line) pair whose share passes MIN_SHARE.

    lines_sql selects source, source_id, geom (SRID 4326) and name, one row per
    (source, source_id). segments_sql (for tests) replaces the ACHD segments: it
    selects id, name, geom. Leaves temp tables sm_line and sm_seg for the stats.
    """
    params = dict(params or {})
    conn.execute(_SETUP)
    conn.execute(
        f"""create temp table sm_line on commit drop as
            select source::text, source_id::text, name::text, ST_Transform(geom, {SRID}) as g
            from ({lines_sql}) l where geom is not null and not ST_IsEmpty(geom)""", params)
    conn.execute("create index on sm_line (source, source_id)")
    conn.execute("create index on sm_line using gist (g)")
    conn.execute(
        f"""create temp table sm_buf on commit drop as
            select source, source_id,
                   ST_Subdivide(ST_Buffer(g, %(near)s, 'endcap=flat join=round quad_segs=4'), 64) as piece
            from sm_line""", {"near": near_m})
    conn.execute("create index on sm_buf using gist (piece)")
    seg_sql = segments_sql or "select id, name, geom from core.road_segment where active"
    conn.execute(
        f"""create temp table sm_seg on commit drop as
            select id, name, g, ST_Length(g) as len
            from (select id, name, ST_Transform(geom, {SRID}) as g from ({seg_sql}) s0) s""")
    conn.execute("create index on sm_seg using gist (g)")
    conn.execute("analyze sm_line")
    conn.execute("analyze sm_buf")
    conn.execute("analyze sm_seg")
    out = []
    for row in conn.execute(_CANDIDATES, {"min_share": MIN_SHARE}).fetchall():
        seg_id, source, source_id, overlap, seg_len, seg_name, src_name, seg_b, chord, src_b, projected = row
        out.append({"road_segment_id": seg_id, "source": source, "source_id": source_id, "overlap_m": overlap,
                    "share": overlap / seg_len if seg_len else 0.0, "seg_name": seg_name, "src_name": src_name,
                    "seg_bearing": seg_b, "chord_m": chord, "src_bearing": src_b, "projected_m": projected})
    return out


def rematch(conn, sources, lines_sql, params=None, method="buffer15_bearing20", segments_sql=None):
    """Delete and rewrite the matches of `sources` (a list of source names) from
    the lines lines_sql selects. Doesn't commit: the caller does, so the delete
    and the rewrite land together. Returns stats per source."""
    rule = METHODS[method]
    found = candidates(conn, lines_sql, params, rule["near_m"], segments_sql)
    rows = []
    for c in found:
        result = decide(c, method)
        if result:
            diff, confidence, how = result
            rows.append((c["road_segment_id"], c["source"], c["source_id"], round(c["overlap_m"], 1),
                         round(min(c["share"], 1.0), 3), diff, how, confidence))
    conn.execute("delete from core.segment_match where source = any(%s)", (list(sources),))
    with conn.cursor() as cur:
        cur.executemany(
            """insert into core.segment_match (road_segment_id, source, source_id, overlap_m, share, bearing_diff,
                 method, confidence, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, now())""", rows)
    stats = {}
    for source, lines, matched, matches, near, away in conn.execute(
            f"""select l.source, count(*),
                       count(*) filter (where m.n is not null),
                       coalesce(sum(m.n), 0),
                       count(*) filter (where m.n is null and exists (
                         select 1 from sm_seg s where ST_DWithin(s.g, l.g, {NEAR_NETWORK_M}))),
                       count(*) filter (where m.n is null and not exists (
                         select 1 from sm_seg s where ST_DWithin(s.g, l.g, {NEAR_NETWORK_M})))
                from sm_line l
                left join (select source, source_id, count(*) as n from core.segment_match
                           where source = any(%s) group by 1, 2) m
                  on m.source = l.source and m.source_id = l.source_id
                group by 1""", (list(sources),)).fetchall():
        stats[source] = {"lines": lines, "matched lines": matched, "matches": int(matches),
                         "unmatched near ACHD": near, "unmatched away from ACHD": away}
    for source, segments in conn.execute(
            """select source, count(distinct road_segment_id) from core.segment_match
               where source = any(%s) group by 1""", (list(sources),)).fetchall():
        stats.setdefault(source, {})["ACHD segments"] = segments
    return stats


def summary(stats):
    """Per-source stats added up, for a one-line report."""
    keys = ("lines", "matched lines", "matches", "ACHD segments", "unmatched near ACHD", "unmatched away from ACHD")
    total = {k: sum(s.get(k, 0) for s in stats.values()) for k in keys}
    total["match rate"] = f"{100 * total['matched lines'] / total['lines']:.1f}%" if total["lines"] else "-"
    return total


def stale(conn, sources):
    """True when a source has no matches yet, or ACHD's segments have changed since its last match."""
    last = conn.execute("select min(matched_at) from (select max(matched_at) as matched_at from core.segment_match "
                        "where source = any(%s) group by source) s", (list(sources),)).fetchone()[0]
    if last is None:
        return True
    newer = conn.execute("""select exists (select 1 from raw.record where source = 'achd_roads'
                              and (first_seen > %s or removed_at > %s))""", (last, last)).fetchone()[0]
    return bool(newer)


def main(argv):
    from . import db
    from .sources import achd_msm, compass_centerline, itd_hpms
    modules = {m.SOURCE["name"]: m for m in (itd_hpms, achd_msm, compass_centerline)}
    names = argv or list(modules)
    unknown = [n for n in names if n not in modules]
    if unknown:
        sys.exit(f"unknown source(s): {', '.join(unknown)} (choose from {', '.join(modules)})")
    with db.connect() as conn:
        for name in names:
            stats = modules[name].match(conn)
            conn.commit()
            print(f"{name} matching: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
