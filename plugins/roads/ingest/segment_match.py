"""Which ACHD road segments a source's lines lie along (core.segment_match; docs/12).

Used by itd_hpms, achd_msm, compass_centerline and osm_valley after each run
that changes them, and for all of them after achd_roads changes ACHD's
segments (rematch_all). One source line can lie along many ACHD segments,
and one segment can carry several lines: HPMS's A and D routes and other
divided carriageways are two lines along one ACHD centerline, and both match
it.

A segment and a line match on one of two shares, tried in this order:

- **the segment's:** at least 60% of the ACHD segment lies within the buffer
  of the line (15 m; 10 m for the Master Street Map);
- **the line's** (owner, Oct 6): otherwise, at least 60% of a line of 20 m
  or more lies within the buffer of the segment. This catches lines shorter
  than ACHD's segments: an OpenStreetMap turn bay split off a block, a
  COMPASS piece of a split segment. Its methods start with 'way_in_'.

and on one of two checks:

- **bearing:** the bearings differ by at most 20° (either way along the
  line, so a D route drawn against the A route still matches). Methods
  buffer15_bearing20 and way_in_buffer15_bearing20.
- **name** (Master Street Map): the street names agree whatever the
  direction prefix, suffix, spacing or a small misspelling ('TENMILE RD' is
  'N Ten Mile Rd'); route designations agree by number ('SH-16' is 'N Hwy
  16'). Methods buffer10_name and way_in_buffer10_name (the line's share also
  needs the bearing). Where the names can't be compared (a route designation
  facing a street name: 'SH-44' runs along 'W State St'), the bearing decides
  and the method says so: buffer10_bearing20, way_in_buffer10_bearing20.
  Names that disagree reject the match.

share and overlap_m always measure the ACHD segment (0011): the length of it
within the line's buffer, and that as a share of it. confidence is the
matched rule's share (the segment's or the line's, at most 1) times the
cosine of the bearing difference, halved under the bearing check when both
lines have names and they disagree (a frontage road 12 m from a highway is
the case this flags).

Geometry is measured in SQL in UTM 11N (EPSG:26911, metres), with round-ended
buffers, so a stretch just past a line's end counts too. The bearing is the
matched line's end-to-end chord (the segment's under the segment's share,
the line's under the line's) against the chord between the nearest points on
the other line. When that second chord is less than half the first, one line
crosses the other rather than running along it, and the bearing check fails.

Rematching deletes and rewrites a source's matches in one transaction (the
caller commits). Canyon County has no ACHD segments, so its lines stay
unmatched and keep their own geometry; the stats say how many unmatched
lines lie away from ACHD's network (no segment within 50 m) and how many lie
near it (real misses).

By hand: python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley]
"""

import math
import re
import sys
import traceback
from difflib import SequenceMatcher

MIN_SHARE = 0.6
MIN_LINE_M = 20         # a line shorter than this can't match on its own share
MAX_BEARING = 20.0
MIN_PROJECTED = 0.5
NEAR_NETWORK_M = 50
SRID = 26911
WAY_IN = "way_in_"
BUFFER = "quad_segs=4"  # round ends and joins

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

    c: share (of the ACHD segment within the line's buffer), line_len and
    line_share (of the line within the segment's buffer; None when the
    segment's share passed), chord_m and chord_bearing (the matched line's
    end-to-end chord: the segment's under the segment's share, the line's
    under the line's), projected_m and projected_bearing (the chord between
    the nearest points on the other line), seg_name, src_name.
    Returns (bearing_diff or None, confidence, method) for a match, else None.
    """
    rule = METHODS[method]
    share = c.get("share") or 0.0
    if share >= MIN_SHARE:
        prefix, rule_share = "", share
    elif (c.get("line_len") or 0.0) >= MIN_LINE_M and (c.get("line_share") or 0.0) >= MIN_SHARE:
        prefix, rule_share = WAY_IN, c["line_share"]
    else:
        return None
    diff = None
    chord, projected = c.get("chord_m") or 0.0, c.get("projected_m") or 0.0
    if chord > 0 and projected >= MIN_PROJECTED * chord:
        diff = bearing_diff(c.get("chord_bearing"), c.get("projected_bearing"))
    bearing_ok = diff is not None and diff <= MAX_BEARING
    names = names_agree(c.get("seg_name"), c.get("src_name"))
    if rule["check"] == "bearing":
        if not bearing_ok:
            return None
        how, factor = method, (0.5 if names is False else 1.0)
    elif names is False or (prefix and not bearing_ok):
        return None
    elif names is True:
        how, factor = method, 1.0
    elif bearing_ok:
        how, factor = f"buffer{rule['near_m']}_bearing{int(MAX_BEARING)}", 1.0
    else:
        return None
    confidence = min(rule_share, 1.0) * math.cos(math.radians(diff or 0.0)) * factor
    return (None if diff is None else round(diff, 1)), round(max(0.0, min(confidence, 1.0)), 3), prefix + how


# --- the measurements (SQL) --------------------------------------------------

_SETUP = """
drop table if exists pg_temp.sm_line, pg_temp.sm_buf, pg_temp.sm_seg;
"""

# Pairs within the line's buffer, then the rule: the segment's share, else (a line of
# 20 m or more, short enough to lie 60% along the segment) the line's share. The chord
# is the matched line's; the projected chord joins the nearest points on the other.
_CANDIDATES = """
with ov as (
  select s.id, b.source, b.source_id, sum(ST_Length(ST_Intersection(s.g, b.piece))) as overlap_m
  from sm_buf b join sm_seg s on s.g && b.piece and ST_Intersects(s.g, b.piece)
  group by 1, 2, 3
), pair as (
  select ov.*, s.len as seg_len, l.len as line_len, s.name as seg_name, l.name as line_name,
         s.g as sg, l.g as lg, s.b as sb, ov.overlap_m >= %(share)s * s.len as seg_rule
  from ov
  join sm_seg s on s.id = ov.id
  join sm_line l on l.source = ov.source and l.source_id = ov.source_id
  where s.len > 0
    and (ov.overlap_m >= %(share)s * s.len
         or (l.len >= %(min_line)s and %(share)s * l.len <= s.len + 2 * %(near)s))
), rule as (
  select pair.*, case when not seg_rule then ST_Length(ST_Intersection(lg, sb)) / line_len end as line_share
  from pair
)
select id, source, source_id, overlap_m, seg_len, line_len, line_share, seg_name, line_name,
       degrees(ST_Azimuth(e.p1, e.p2)), ST_Distance(e.p1, e.p2),
       degrees(ST_Azimuth(q.q1, q.q2)), ST_Distance(q.q1, q.q2)
from rule
cross join lateral (select case when seg_rule then sg else lg end as a,
                           case when seg_rule then lg else sg end as other) x
cross join lateral (select ST_StartPoint(ST_GeometryN(x.a, 1)) as p1,
                           ST_EndPoint(ST_GeometryN(x.a, ST_NumGeometries(x.a))) as p2) e
cross join lateral (select ST_ClosestPoint(x.other, e.p1) as q1, ST_ClosestPoint(x.other, e.p2) as q2) q
where seg_rule or line_share >= %(share)s
"""


def candidates(conn, lines_sql, params=None, near_m=15, segments_sql=None):
    """Measure every (ACHD segment, source line) pair that passes either share.

    lines_sql selects source, source_id, geom (SRID 4326) and name, one row per
    (source, source_id). segments_sql (for tests) replaces the ACHD segments: it
    selects id, name, geom. Leaves temp tables sm_line and sm_seg for the stats.
    """
    params = dict(params or {})
    conn.execute(_SETUP)
    conn.execute(
        f"""create temp table sm_line on commit drop as
            select source, source_id, name, g, ST_Length(g) as len
            from (select source::text, source_id::text, name::text, ST_Transform(geom, {SRID}) as g
                  from ({lines_sql}) l0 where geom is not null and not ST_IsEmpty(geom)) l""", params)
    conn.execute("create index on sm_line (source, source_id)")
    conn.execute("create index on sm_line using gist (g)")
    conn.execute(
        f"""create temp table sm_buf on commit drop as
            select source, source_id, ST_Subdivide(ST_Buffer(g, %(near)s, '{BUFFER}'), 64) as piece
            from sm_line where len > 0""", {"near": near_m})
    conn.execute("create index on sm_buf using gist (piece)")
    seg_sql = segments_sql or "select id, name, geom from core.road_segment where active"
    conn.execute(
        f"""create temp table sm_seg on commit drop as
            select id, name, g, ST_Length(g) as len, ST_Buffer(g, %(near)s, '{BUFFER}') as b
            from (select id, name, ST_Transform(geom, {SRID}) as g from ({seg_sql}) s0) s""", {"near": near_m})
    conn.execute("create index on sm_seg using gist (g)")
    conn.execute("analyze sm_line")
    conn.execute("analyze sm_buf")
    conn.execute("analyze sm_seg")
    out = []
    for row in conn.execute(_CANDIDATES, {"share": MIN_SHARE, "min_line": MIN_LINE_M, "near": near_m}).fetchall():
        (seg_id, source, source_id, overlap, seg_len, line_len, line_share, seg_name, src_name,
         chord_bearing, chord, projected_bearing, projected) = row
        out.append({"road_segment_id": seg_id, "source": source, "source_id": source_id, "overlap_m": overlap,
                    "share": overlap / seg_len if seg_len else 0.0, "line_len": line_len, "line_share": line_share,
                    "seg_name": seg_name, "src_name": src_name, "chord_bearing": chord_bearing, "chord_m": chord,
                    "projected_bearing": projected_bearing, "projected_m": projected})
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
    for source, segments, way_in in conn.execute(
            """select source, count(distinct road_segment_id), count(*) filter (where method like 'way\\_in\\_%%')
               from core.segment_match where source = any(%s) group by 1""", (list(sources),)).fetchall():
        stats.setdefault(source, {}).update({"ACHD segments": segments, "matches on the line's share": way_in})
    return stats


def summary(stats):
    """Per-source stats added up, for a one-line report."""
    keys = ("lines", "matched lines", "matches", "matches on the line's share", "ACHD segments",
            "unmatched near ACHD", "unmatched away from ACHD")
    total = {k: sum(s.get(k, 0) for s in stats.values()) for k in keys}
    total["match rate"] = f"{100 * total['matched lines'] / total['lines']:.1f}%" if total["lines"] else "-"
    return total


def stale(conn, sources, raw_sources=None):
    """True when a source's matches are out of date: it has records (raw_sources, by default
    `sources`) but no matches, or its records or ACHD's segments have changed since its
    oldest last match. A source with no records at all has nothing to match."""
    raw_sources = list(raw_sources or sources)
    if not conn.execute("select exists (select 1 from raw.record where source = any(%s) and removed_at is null)",
                        (raw_sources,)).fetchone()[0]:
        return False
    last = conn.execute(
        """select min(m.last) from unnest(%s::text[]) s(source)
           left join lateral (select max(matched_at) as last from core.segment_match where source = s.source) m on true""",
        (list(sources),)).fetchone()[0]
    if last is None:
        return True
    return bool(conn.execute(
        """select exists (select 1 from raw.record where source = any(%s)
                            and (first_seen > %s or removed_at > %s))""",
        (raw_sources + ["achd_roads"], last, last)).fetchone()[0])


def matchers():
    """{source name: (match(conn) -> stats, the match sources it writes, its raw sources)}
    for every source matched to ACHD's segments."""
    from .sources import achd_msm, compass_centerline, itd_hpms, osm_valley
    return {
        "itd_hpms": (itd_hpms.match, itd_hpms.MATCH_SOURCES, itd_hpms.MATCH_SOURCES + [itd_hpms.NAMES_SOURCE]),
        "achd_msm": (achd_msm.match, ["achd_msm"], ["achd_msm"]),
        "compass_centerline": (compass_centerline.match, ["compass_centerline"], ["compass_centerline"]),
        "osm_valley": (osm_valley.match_achd_segments, ["osm_valley"], ["osm_valley"]),
    }


def rematch_all(conn, names=None, only_stale=False):
    """Rematch every source (or the named ones; with only_stale, those whose matches are out
    of date), committing after each. A matcher that fails is rolled back and logged, and the
    rest still run; the failures are in the result. Returns {name: stats or {"failed": error}}."""
    found = matchers()
    unknown = [n for n in names or () if n not in found]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)} (choose from {', '.join(found)})")
    out = {}
    for name in names or list(found):
        match, sources, raw_sources = found[name]
        try:
            if only_stale and not stale(conn, sources, raw_sources):
                continue
            out[name] = match(conn)
            conn.commit()
        except Exception as err:
            conn.rollback()
            print(f"segment_match: {name} failed:\n{traceback.format_exc()}", flush=True)
            out[name] = {"failed": f"{type(err).__name__}: {err}"[:300]}
    return out


def main(argv):
    from ingest import db
    with db.connect() as conn:
        try:
            results = rematch_all(conn, argv or None)
        except ValueError as err:
            sys.exit(str(err))
    for name, stats in results.items():
        print(f"{name} matching: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    if any("failed" in s for s in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
