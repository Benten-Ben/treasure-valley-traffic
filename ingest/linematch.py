"""Which lines of a network a source's lines lie along: the buffer-and-bearing line matcher.

Core since the landscape sprint (Oct 2026), by docs/15's rule that a piece
becomes core once two plugins need it: `roads` matches its lane sources and
OpenStreetMap to ACHD's segments with it (plugins/roads/ingest/segment_match.py,
which writes core.segment_match), `trails` links Ridge to Rivers' and the
Greenbelt's lines to OpenStreetMap's paths, and `water` will link NHD's lines
to OpenStreetMap's waterways.

Two sets of lines go in: the **targets**, the network being matched to (ACHD's
segments, OSM's paths), and the **lines**, a source's lines to place on it.
One line can lie along many targets, and one target can carry several lines:
HPMS's A and D routes and other divided carriageways are two lines along one
ACHD centerline, and both match it.

A target and a line match on one of two shares, tried in this order:

- **the target's:** at least 60% of the target lies within the buffer of the
  line (the rule's buffer: 15 m, or 10 m for the Master Street Map);
- **the line's** (owner, Oct 6): otherwise, at least 60% of a line of 20 m
  or more lies within the buffer of the target. This catches lines shorter
  than the targets: an OpenStreetMap turn bay split off a block, a COMPASS
  piece of a split segment. Its methods start with 'way_in_'.

and on one of two checks, the rule's:

- **bearing:** the bearings differ by at most 20° (either way along the
  line, so a D route drawn against the A route still matches). Methods
  buffer15_bearing20 and way_in_buffer15_bearing20.
- **name:** the names agree whatever the direction prefix, suffix, spacing
  or a small misspelling ('TENMILE RD' is 'N Ten Mile Rd'); route
  designations agree by number ('SH-16' is 'N Hwy 16'). Methods
  buffer10_name and way_in_buffer10_name (the line's share also needs the
  bearing). Where the names can't be compared (a route designation facing a
  street name: 'SH-44' runs along 'W State St'), the bearing decides and the
  method says so: buffer10_bearing20, way_in_buffer10_bearing20. Names that
  disagree reject the match.

A rule is `Rule(near_m, check)`, and its method name comes from them
('buffer15_bearing20', 'buffer10_name'), so the names stored in
core.segment_match since Oct 6 stay as they are.

`share` and `overlap_m` always measure the target: the length of it within
the line's buffer, and that as a share of it. `confidence` is the matched
share (the target's or the line's, at most 1) times the cosine of the
bearing difference, halved under the bearing check when both lines have
names and they disagree (a frontage road 12 m from a highway is the case
this flags).

Geometry is measured in SQL in UTM 11N (EPSG:26911, metres), with
round-ended buffers, so a stretch just past a line's end counts too. The
bearing is the matched line's end-to-end chord (the target's under the
target's share, the line's under the line's) against the chord between the
nearest points on the other line. When that second chord is less than half
the first, one line crosses the other rather than running along it, and the
bearing check fails.

The functions don't write anything: `match()` returns the matches and the
caller stores them where its plugin keeps them, in the same transaction.
`candidates()` leaves the temporary tables lm_line and lm_target (dropped at
commit) for `coverage()`, which says how many lines matched and how many of
the rest lie near the network or away from it.

Standard library plus psycopg (the connection is the caller's).
"""

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

MIN_SHARE = 0.6
MIN_LINE_M = 20         # a line shorter than this can't match on its own share
MAX_BEARING = 20.0
MIN_PROJECTED = 0.5     # the projected chord, as a share of the matched chord, below which the lines cross
NEAR_NETWORK_M = 50     # an unmatched line within this of a target is a miss; farther, it's off the network
SRID = 26911
WAY_IN = "way_in_"
BUFFER = "quad_segs=4"  # round ends and joins
CHECKS = ("bearing", "name")


@dataclass(frozen=True)
class Rule:
    """How close and by which check a target and a line match. The defaults are roads' (Oct 6)."""
    near_m: float = 15
    check: str = "bearing"
    min_share: float = MIN_SHARE
    min_line_m: float = MIN_LINE_M
    max_bearing: float = MAX_BEARING
    min_projected: float = MIN_PROJECTED

    def __post_init__(self):
        if self.check not in CHECKS:
            raise ValueError(f"unknown check {self.check!r} (choose from {', '.join(CHECKS)})")
        if not self.near_m > 0:
            raise ValueError(f"the buffer must be more than 0 m, not {self.near_m!r}")

    @property
    def method(self):
        """'buffer15_bearing20' or 'buffer10_name' (without the 'way_in_' prefix)."""
        return f"buffer{self.near_m:g}_name" if self.check == "name" else self.fallback

    @property
    def fallback(self):
        """The bearing check at this buffer: what the name check falls back to when names can't be compared."""
        return f"buffer{self.near_m:g}_bearing{self.max_bearing:g}"


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


def decide(c, rule=Rule()):
    """Whether a candidate is a match under `rule`, from its measurements.

    c: share (of the target within the line's buffer), line_len and line_share
    (of the line within the target's buffer; None when the target's share
    passed), chord_m and chord_bearing (the matched line's end-to-end chord:
    the target's under the target's share, the line's under the line's),
    projected_m and projected_bearing (the chord between the nearest points on
    the other line), target_name, line_name.
    Returns (bearing_diff or None, confidence, method) for a match, else None.
    """
    share = c.get("share") or 0.0
    if share >= rule.min_share:
        prefix, rule_share = "", share
    elif (c.get("line_len") or 0.0) >= rule.min_line_m and (c.get("line_share") or 0.0) >= rule.min_share:
        prefix, rule_share = WAY_IN, c["line_share"]
    else:
        return None
    diff = None
    chord, projected = c.get("chord_m") or 0.0, c.get("projected_m") or 0.0
    if chord > 0 and projected >= rule.min_projected * chord:
        diff = bearing_diff(c.get("chord_bearing"), c.get("projected_bearing"))
    bearing_ok = diff is not None and diff <= rule.max_bearing
    names = names_agree(c.get("target_name"), c.get("line_name"))
    if rule.check == "bearing":
        if not bearing_ok:
            return None
        how, factor = rule.method, (0.5 if names is False else 1.0)
    elif names is False or (prefix and not bearing_ok):
        return None
    elif names is True:
        how, factor = rule.method, 1.0
    elif bearing_ok:
        how, factor = rule.fallback, 1.0
    else:
        return None
    confidence = min(rule_share, 1.0) * math.cos(math.radians(diff or 0.0)) * factor
    return (None if diff is None else round(diff, 1)), round(max(0.0, min(confidence, 1.0)), 3), prefix + how


# --- the measurements (SQL) --------------------------------------------------

_SETUP = """
drop table if exists pg_temp.lm_line, pg_temp.lm_buf, pg_temp.lm_target;
"""

# Pairs within the line's buffer, then the rule: the target's share, else (a line of
# 20 m or more, short enough to lie 60% along the target) the line's share. The chord
# is the matched line's; the projected chord joins the nearest points on the other.
_CANDIDATES = """
with ov as (
  select t.id, b.source, b.source_id, sum(ST_Length(ST_Intersection(t.g, b.piece))) as overlap_m
  from lm_buf b join lm_target t on t.g && b.piece and ST_Intersects(t.g, b.piece)
  group by 1, 2, 3
), pair as (
  select ov.*, t.len as target_len, l.len as line_len, t.name as target_name, l.name as line_name,
         t.g as tg, l.g as lg, t.b as tb, ov.overlap_m >= %(share)s * t.len as target_rule
  from ov
  join lm_target t on t.id = ov.id
  join lm_line l on l.source = ov.source and l.source_id = ov.source_id
  where t.len > 0
    and (ov.overlap_m >= %(share)s * t.len
         or (l.len >= %(min_line)s and %(share)s * l.len <= t.len + 2 * %(near)s))
), rule as (
  select pair.*, case when not target_rule then ST_Length(ST_Intersection(lg, tb)) / line_len end as line_share
  from pair
)
select id, source, source_id, overlap_m, target_len, line_len, line_share, target_name, line_name,
       degrees(ST_Azimuth(e.p1, e.p2)), ST_Distance(e.p1, e.p2),
       degrees(ST_Azimuth(q.q1, q.q2)), ST_Distance(q.q1, q.q2)
from rule
cross join lateral (select case when target_rule then tg else lg end as a,
                           case when target_rule then lg else tg end as other) x
cross join lateral (select ST_StartPoint(ST_GeometryN(x.a, 1)) as p1,
                           ST_EndPoint(ST_GeometryN(x.a, ST_NumGeometries(x.a))) as p2) e
cross join lateral (select ST_ClosestPoint(x.other, e.p1) as q1, ST_ClosestPoint(x.other, e.p2) as q2) q
where target_rule or line_share >= %(share)s
"""


def candidates(conn, lines_sql, targets_sql, params=None, rule=Rule()):
    """Measure every (target, line) pair that passes either share under `rule`.

    lines_sql selects source, source_id, geom (SRID 4326) and name, one row per
    (source, source_id). targets_sql selects id, name and geom (SRID 4326), one
    row per id. params fill both queries' %(name)s placeholders. Returns dicts
    with target_id, source, source_id, overlap_m, share, line_len, line_share,
    target_name, line_name, chord_bearing, chord_m, projected_bearing and
    projected_m. Leaves the temporary tables lm_line and lm_target until commit.
    """
    params = dict(params or {})
    near = rule.near_m
    conn.execute(_SETUP)
    conn.execute(
        f"""create temp table lm_line on commit drop as
            select source, source_id, name, g, ST_Length(g) as len
            from (select source::text, source_id::text, name::text, ST_Transform(geom, {SRID}) as g
                  from ({lines_sql}) l0 where geom is not null and not ST_IsEmpty(geom)) l""", params)
    conn.execute("create index on lm_line (source, source_id)")
    conn.execute("create index on lm_line using gist (g)")
    conn.execute(
        f"""create temp table lm_buf on commit drop as
            select source, source_id, ST_Subdivide(ST_Buffer(g, %(near)s, '{BUFFER}'), 64) as piece
            from lm_line where len > 0""", {"near": near})
    conn.execute("create index on lm_buf using gist (piece)")
    conn.execute(
        f"""create temp table lm_target on commit drop as
            select id, name, g, ST_Length(g) as len, ST_Buffer(g, %(near)s, '{BUFFER}') as b
            from (select id, name::text, ST_Transform(geom, {SRID}) as g from ({targets_sql}) t0) t""",
        {**params, "near": near})
    conn.execute("create index on lm_target using gist (g)")
    conn.execute("analyze lm_line")
    conn.execute("analyze lm_buf")
    conn.execute("analyze lm_target")
    out = []
    for row in conn.execute(_CANDIDATES, {"share": rule.min_share, "min_line": rule.min_line_m,
                                          "near": near}).fetchall():
        (target_id, source, source_id, overlap, target_len, line_len, line_share, target_name, line_name,
         chord_bearing, chord, projected_bearing, projected) = row
        out.append({"target_id": target_id, "source": source, "source_id": source_id, "overlap_m": overlap,
                    "share": overlap / target_len if target_len else 0.0, "line_len": line_len,
                    "line_share": line_share, "target_name": target_name, "line_name": line_name,
                    "chord_bearing": chord_bearing, "chord_m": chord,
                    "projected_bearing": projected_bearing, "projected_m": projected})
    return out


def match(conn, lines_sql, targets_sql, rule=Rule(), params=None):
    """The matches between the lines lines_sql selects and the targets targets_sql
    selects (see candidates()), under `rule`: each candidate that passes, with its
    bearing_diff, confidence and method added. Writes nothing."""
    out = []
    for c in candidates(conn, lines_sql, targets_sql, params, rule):
        result = decide(c, rule)
        if result:
            diff, confidence, method = result
            out.append({**c, "bearing_diff": diff, "confidence": confidence, "method": method})
    return out


_COVERAGE = """
with m as (
  select source, source_id, count(*) as n
  from unnest(%(sources)s::text[], %(source_ids)s::text[]) as k(source, source_id)
  group by 1, 2
)
select l.source, count(*),
       count(*) filter (where m.n is not null),
       coalesce(sum(m.n), 0),
       count(*) filter (where m.n is null and exists (
         select 1 from lm_target t where ST_DWithin(t.g, l.g, %(near)s))),
       count(*) filter (where m.n is null and not exists (
         select 1 from lm_target t where ST_DWithin(t.g, l.g, %(near)s)))
from lm_line l
left join m on m.source = l.source and m.source_id = l.source_id
group by 1
order by 1
"""


def coverage(conn, matches, near_m=NEAR_NETWORK_M):
    """Per source, after candidates() or match() in the same transaction: its lines,
    how many matched, the matches, the targets they reach, how many matched on the
    line's share, and the unmatched lines near the network (a target within near_m:
    real misses) and away from it. `matches` are match()'s, or any dicts with
    source, source_id, target_id and method."""
    keys = [(m["source"], m["source_id"]) for m in matches]
    out = {}
    for source, lines, matched, n, near, away in conn.execute(
            _COVERAGE, {"sources": [k[0] for k in keys], "source_ids": [k[1] for k in keys],
                        "near": near_m}).fetchall():
        mine = [m for m in matches if m["source"] == source]
        out[source] = {"lines": lines, "matched lines": matched, "matches": int(n),
                       "targets": len({m["target_id"] for m in mine}),
                       "matches on the line's share": sum(1 for m in mine if m["method"].startswith(WAY_IN)),
                       "unmatched near": near, "unmatched away": away}
    return out
