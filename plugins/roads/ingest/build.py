"""Real-width roads: `python3 -m ingest roads-build` (landscape sprint package P7; plan C12, C17, §3.4; the
roads-real-width design; decision 10).

Builds roads 0003's tables (plugins/roads/migrations/0003_real_width.sql) from scratch, in one transaction, as a
build run (ingest/builds.py: it clears roads-build's marks and marks roads-export when it succeeds; never inside
`ingest serve`). A light job: standard-library Python running PostGIS SQL, as the capped tvt_build role. Steps:

1. **Pieces.** The road ways of core.osm_way (osm_valley's classes that are roads) and roads.osm_street, split at
   every node two of them share (OpenStreetMap shares a node only where roads meet, so a bridge over a road never
   splits it) and where a way touches itself. The three OpenStreetMap tables must hold one extract
   (osm_extract.check_partition, osm_paving included: sidewalks and crossings come from it).
2. **Matching.** Each piece's county (COMPASS's zones), the ACHD segment it lies along in Ada (core's line
   matcher, roads' rule: 15 m, bearings within 20°), ITD's HPMS sections along it, the parallel sidewalks either
   side (roads.osm_paving), and its share of developed land (the CDL, roads.developed_land).
3. **Cross-sections** by the rules in xsection.py, into roads.xsection.
4. **Junctions.** Nodes where three or more piece ends meet, clustered along short pieces between them (a divided
   road's crossing is one junction) and round roundabouts; each gets a curb-return radius by the classes that meet.
5. **Surfaces.** Each piece's carriageway (single-sided buffers, flat ends, mitred joins), a disc where two pieces
   meet at an angle, a curbed median strip where HPMS has one; bridges' carriageways are decks (drawn flat with a
   dark edge in v1: no 3D decks). Tunnels get none.
6. **Islands.** The road graph's enclosed faces (its centrelines polygonized) that are small (channelizing
   islands) or thin (medians, separators), less the carriageways, and roundabouts' centres.
7. **Closings.** In each junction's disc, its carriageways closed (buffered out by the radius and back in), less
   the islands: what that adds is the junction's fill (curb returns). Interchanges' freeway nodes get none.
8. **Edges:** every surface's outline less the surfaces it meets (no seams), as curb, shoulder or deck edges with
   the width's tier, so a crisp curb can be drawn only where the width is known.
9. **Crosswalks** at marked crossing nodes only (roads.osm_walk_node: marked true; decision 10): 3 m deep, across
   the road along the crossing way, clipped to the surfaces.
10. **Markings** where xsection says so: lines offset from the centreline, cut back from each junction (the
    crossing roads' surfaces plus the curb-return radius, plus 1 m) and 1 m from crosswalks; stop bars on
    signal approaches; turn arrows ahead of a junction.
11. **Generalised** surfaces for z15 (0.5 m), and the review list (roads.review).

The rules' numbers are xsection.DEFAULTS and the constants here; each build records them (roads.build.params).
Every input's source and version goes into roads.build.inputs, and the export reads them from there.
"""

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timezone

from ingest import builds, linematch, osm_extract

from . import developed as land
from . import xsection as X

COMMAND = "python3 -m ingest roads-build"
BUILD = "roads-build"
THEN = ("roads-export",)
SRID = 32611
OWNERS = ("osm_valley", "osm_street", "osm_paving")
CLASSES = sorted(X.ROAD_CLASSES)
ACHD_RULE = linematch.Rule(15, "bearing", loops=False)     # roads' rule (segment_match, Oct 6)
HPMS_KINDS = ("through_lanes", "lane_width", "shoulders", "median")

# Junctions ⚠️ (the design's numbers until the sheets say otherwise)
CLUSTER_EPS = {"major": 30.0, "collector": 22.0, "local": 15.0}   # nodes joined by a piece this short are one junction
CORNER_RADIUS = {("major", "major"): 10.5, ("major", "collector"): 9.0, ("collector", "collector"): 7.5,
                 ("major", "local"): 6.0, ("collector", "local"): 6.0, ("local", "local"): 4.5}
MINOR_RADIUS = 3.0                 # where an alley or a service way meets a street
ROUNDABOUT_RADIUS_MAX = 6.0
LARGE_JUNCTION = {"nodes": 12, "spread_m": 100.0}       # listed for review
ISLAND_MAX_M2 = 2000.0             # an enclosed face this small is a channelizing island (or a tiny block)
THIN_M = 15.0                      # a face this thin (2 x area / perimeter) is a median or a separator
ISLAND_MIN_M2 = 3.0
FILL_MIN_M2 = 0.5
CROSSWALK_DEPTH_M = 3.0            # ⚠️ ten feet
CROSSWALK_CLEAR_M = 1.0            # lines stop this far from a crosswalk
JUNCTION_CLEAR_M = 1.0             # and this far beyond a junction's curb returns
STOP_BAR_GAP_M = 1.2               # a stop bar this far before a crosswalk
ARROW_BACK_M = 8.0                 # an arrow this far before where the lines stop
DEAD_END_TRIM_M = 0.5
Z15_TOLERANCE_M = 0.5
Z15_MIN_M2 = 4.0
SIDEWALK_REACH_M = 15.0            # a parallel sidewalk this close counts
SIDEWALK_BEARING = 25.0
LICENSE = "ODbL-1.0 (© OpenStreetMap contributors) with ACHD's and ITD's layers (none stated)"
CREDIT = "© OpenStreetMap contributors; Ada County Highway District; Idaho Transportation Department; COMPASS; " \
         "USDA NASS Cropland Data Layer"

TABLES = ("roads.review", "roads.arrow", "roads.marking", "roads.edge", "roads.surface", "roads.xsection",
          "roads.junction", "roads.piece")


class BuildError(RuntimeError):
    pass


def ready(conn):
    """The tables this build reads and writes exist (roads 0001-0004 applied)."""
    need = ("roads.piece", "roads.osm_street", "roads.osm_paving", "roads.segment_bike_xsection",
            "core.segment_lanes", "ops.build_run")
    missing = [t for t in need if not conn.execute("select to_regclass(%s) is not null", (t,)).fetchone()[0]]
    return missing


def run_sql(conn, text, params=None):
    """Run a script of statements (separated by ';' at a line's end) one by one: psycopg binds parameters one
    statement at a time."""
    for stmt in re.split(r";\s*\n", text):
        if stmt.strip():
            conn.execute(stmt, params)


def _log(out, t0, text):
    out(f"  {time.monotonic() - t0:6.1f} s  {text}")


def say(text):
    print(text, flush=True)


# ---- 1. pieces -------------------------------------------------------------------------------------

_WAYS = """
create temp table rb_way on commit drop as
select 'osm_valley'::text as source, o.osm_id, o.highway, nullif(o.tags->>'service', '') as service, o.name, o.ref,
       o.oneway, o.tags, o.geom
from core.osm_way o where o.active and o.highway = any(%(classes)s)
union all
select 'osm_street', s.osm_id, s.highway, s.service, s.name, s.ref, s.oneway, s.tags, s.geom
from roads.osm_street s where s.active and s.highway = any(%(classes)s)
"""

_VERTICES = """
create temp table rb_vx on commit drop as
select w.osm_id, d.path[1] as i, ST_X(d.geom) as x, ST_Y(d.geom) as y
from rb_way w cross join lateral ST_DumpPoints(w.geom) d;
create temp table rb_key on commit drop as
select x, y, count(distinct osm_id)::int as ways, count(*)::int as n, (row_number() over (order by x, y))::int as node
from rb_vx group by x, y;
create index on rb_key (x, y);
analyze rb_vx;
analyze rb_key;
"""

# Each vertex belongs to the piece numbered by how many split vertices come before it on its way (inclusive);
# a split vertex inside a way also ends the piece before it.
_PIECE_VERTICES = """
create temp table rb_pv on commit drop as
with s as (
  select v.osm_id, v.i, v.x, v.y, k.node, max(v.i) over w as last,
         (v.i = 1 or v.i = max(v.i) over w or k.ways > 1 or k.n > 1) as split
  from rb_vx v join rb_key k using (x, y)
  window w as (partition by v.osm_id)
), c as (
  select s.*, sum(split::int) over (partition by osm_id order by i) as c from s
)
select osm_id, c as seq, i, x, y, node from c where i < last
union all
select osm_id, c - 1, i, x, y, node from c where split and i > 1
"""

_PIECES = """
insert into rb_piece (id, osm_id, seq, source, highway, service, name, ref, oneway, roundabout, bridge, tunnel,
                         layer, from_node, to_node, length_m, geom)
select row_number() over (order by g.osm_id, g.seq), g.osm_id, g.seq, w.source, w.highway, w.service, w.name, w.ref,
       case w.oneway when 'yes' then 1 when '-1' then -1 else 0 end,
       coalesce(w.tags->>'junction' in ('roundabout', 'circular'), false),
       coalesce(lower(trim(w.tags->>'bridge')) not in ('no', ''), false),
       coalesce(lower(trim(w.tags->>'tunnel')) not in ('no', ''), false),
       case when trim(w.tags->>'layer') ~ '^[+-]?[0-9]{1,2}$' then greatest(-10, least(10, (trim(w.tags->>'layer'))::int))
            else 0 end,
       g.from_node, g.to_node, ST_Length(g.geom), g.geom
from (select osm_id, seq,
             ST_Transform(ST_SetSRID(ST_MakeLine(ST_MakePoint(x, y) order by i), 4326), %(srid)s) as geom,
             (array_agg(node order by i))[1] as from_node, (array_agg(node order by i desc))[1] as to_node
      from rb_pv group by osm_id, seq) g
join rb_way w using (osm_id)
where ST_Length(g.geom) > 0.01
"""

_NODES = """
create temp table rb_node on commit drop as
select k.node as id, ST_Transform(ST_SetSRID(ST_MakePoint(k.x, k.y), 4326), %(srid)s) as geom, e.degree::int
from rb_key k
join (select node, count(*) as degree
      from (select from_node as node from rb_piece union all select to_node from rb_piece) z
      group by 1) e on e.node = k.node;
create index on rb_node (id);
create index on rb_node using gist (geom);
analyze rb_node;
"""


def pieces(conn):
    # The pieces are staged in rb_piece while the matching steps fill their columns in, then written to
    # roads.piece once (junctions()): updating roads.piece in place would leave a dead copy of every row.
    conn.execute("create temp table rb_piece (like roads.piece including defaults) on commit drop")
    conn.execute("alter table rb_piece add primary key (id)")
    conn.execute("create index on rb_piece using gist (geom)")
    conn.execute(_WAYS, {"classes": CLASSES})
    dup = conn.execute("select count(*) from (select osm_id from rb_way group by 1 having count(*) > 1) d").fetchone()[0]
    if dup:
        raise BuildError(f"{dup} ways are in both core.osm_way and roads.osm_street: the partition is broken")
    run_sql(conn, _VERTICES)
    conn.execute(_PIECE_VERTICES)
    conn.execute(_PIECES, {"srid": SRID})
    conn.execute("analyze rb_piece")
    run_sql(conn, _NODES, {"srid": SRID})
    ways, n = conn.execute("select count(*), (select count(*) from rb_piece) from rb_way").fetchone()
    return {"ways": ways, "pieces": n}


# ---- 2. matching -----------------------------------------------------------------------------------

_COUNTY = """
create temp table rb_county on commit drop as
select county, ST_Subdivide(ST_CollectionExtract(ST_MakeValid(ST_Transform(geom, %(srid)s)), 3), 256) as g
from core.taz where active and county in ('Ada', 'Canyon');
create index on rb_county using gist (g);
update rb_piece p set county = c.county
from rb_county c where ST_Intersects(c.g, ST_LineInterpolatePoint(p.geom, 0.5));
"""


def counties(conn):
    run_sql(conn, _COUNTY, {"srid": SRID})
    return dict(conn.execute("select coalesce(county, 'other'), count(*) from rb_piece group by 1").fetchall())


def match_achd(conn):
    """The ACHD segment each Ada piece lies along: core's line matcher (lines: the pieces, targets: ACHD's active
    segments), the best match by confidence, then overlap."""
    found = linematch.match(
        conn,
        "select 'piece' as source, id::text as source_id, name, ST_Transform(geom, 4326) as geom "
        "from rb_piece where county = 'Ada'",
        "select id, name, geom from core.road_segment where active",
        rule=ACHD_RULE)
    best = {}
    for m in found:
        pid = int(m["source_id"])
        key = (m["confidence"], m["overlap_m"])
        if pid not in best or key > best[pid][0]:
            best[pid] = (key, m["target_id"], m["confidence"])
    conn.execute("create temp table rb_seg (piece_id int primary key, road_segment_id bigint, confidence real) "
                 "on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy rb_seg from stdin") as cp:
            for pid, (_, sid, conf) in best.items():
                cp.write_row((pid, sid, conf))
    conn.execute(
        """update rb_piece p set road_segment_id = m.road_segment_id, seg_confidence = m.confidence,
             seg_same_way = core.drawn_same_way(s.geom, ST_Transform(p.geom, 4326))
           from rb_seg m join core.road_segment s on s.id = m.road_segment_id
           where p.id = m.piece_id""")
    return {"ada pieces matched to ACHD": len(best)}


def match_hpms(conn):
    """ITD HPMS sections along each piece: through lanes where no ACHD segment gives a count, and lane widths,
    shoulders and medians everywhere. rb_hpms: (piece_id, kind, source_id, confidence, overlap_m, same_way)."""
    conn.execute("""create temp table rb_hpms (piece_id int, kind text, source_id text, confidence real,
                      overlap_m real, same_way boolean) on commit drop""")
    rows = []
    for kinds, where in ((("through_lanes",), "road_segment_id is null"),
                         (("lane_width", "shoulders", "median"), "true")):
        found = linematch.match(
            conn,
            "select h.kind as source, h.source_id, h.road_name as name, h.geom from core.hpms_section h "
            "where h.active and h.kind = any(%(kinds)s) and h.geom is not null",
            f"select id, name, ST_Transform(geom, 4326) as geom from rb_piece where not tunnel and {where}",
            rule=ACHD_RULE, params={"kinds": list(kinds)})
        rows += [(int(m["target_id"]), m["source"], m["source_id"], m["confidence"], m["overlap_m"]) for m in found]
    with conn.cursor() as cur:
        with cur.copy("copy rb_hpms (piece_id, kind, source_id, confidence, overlap_m) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
    conn.execute(
        """update rb_hpms m set same_way = core.drawn_same_way(h.geom, ST_Transform(p.geom, 4326))
           from core.hpms_section h, rb_piece p
           where h.kind = m.kind and h.source_id = m.source_id and p.id = m.piece_id""")
    conn.execute("create index on rb_hpms (piece_id)")
    return {"hpms matches": len(rows)}


# A parallel sidewalk either side: at a quarter, half and three quarters along the piece, the nearest sidewalk
# way within reach that runs within SIDEWALK_BEARING of the piece, on each side; a side counts where two of the
# three samples find one, at their median distance.
_SIDEWALKS = """
create temp table rb_sw on commit drop as
select osm_id, ST_Transform(geom, %(srid)s) as g from roads.osm_paving where active and kind = 'sidewalk';
create index on rb_sw using gist (g);
analyze rb_sw;
create temp table rb_walk on commit drop as
with s as (
  select p.id, k, ST_LineInterpolatePoint(p.geom, k / 4.0) as pt,
         ST_Azimuth(ST_LineInterpolatePoint(p.geom, greatest(0, k / 4.0 - 2 / p.length_m)),
                    ST_LineInterpolatePoint(p.geom, least(1, k / 4.0 + 2 / p.length_m))) as az
  from rb_piece p cross join generate_series(1, 3) k
  where p.length_m >= 10 and not p.bridge and not p.tunnel
), n as (
  select s.id, s.k, s.pt, s.az, w.g, ST_ClosestPoint(w.g, s.pt) as c
  from s join rb_sw w on ST_DWithin(w.g, s.pt, %(reach)s)
), a as (
  select n.*, ST_Distance(n.pt, n.c) as d,
         ST_Azimuth(ST_LineInterpolatePoint(n.g, greatest(0, ST_LineLocatePoint(n.g, n.c) - 2 / ST_Length(n.g))),
                    ST_LineInterpolatePoint(n.g, least(1, ST_LineLocatePoint(n.g, n.c) + 2 / ST_Length(n.g)))) as waz,
         sin(ST_Azimuth(n.pt, n.c) - n.az) as side
  from n where ST_Length(n.g) > 0 and ST_Distance(n.pt, n.c) > 0.5
), par as (
  select id, k, case when side > 0 then 'right' else 'left' end as side, min(d) as d
  from a
  where waz is not null and az is not null
    and abs(sin(waz - az)) <= sin(radians(%(bearing)s))
    and abs(side) > 0.7
  group by 1, 2, 3
)
select id as piece_id,
       percentile_cont(0.5) within group (order by d) filter (where side = 'left') as left_m,
       percentile_cont(0.5) within group (order by d) filter (where side = 'right') as right_m,
       count(*) filter (where side = 'left') as n_left, count(*) filter (where side = 'right') as n_right
from par group by 1
"""


def sidewalks(conn):
    run_sql(conn, _SIDEWALKS, {"srid": SRID, "reach": SIDEWALK_REACH_M, "bearing": SIDEWALK_BEARING})
    conn.execute("update rb_walk set left_m = null where n_left < 2")
    conn.execute("update rb_walk set right_m = null where n_right < 2")
    conn.execute("create index on rb_walk (piece_id)")
    n = conn.execute("select count(*) filter (where left_m is not null or right_m is not null) from rb_walk").fetchone()[0]
    return {"pieces with a parallel sidewalk": n}


def developed(conn):
    """Each piece's share of developed land (the CDL's 122-124), or none when no developed build is loaded."""
    conn.execute("create temp table rb_dev (piece_id int primary key, share real) on commit drop")
    current = land.current(conn)
    if current is None:
        return {"developed land": "none loaded: local streets off sidewalks count as rural"}, None
    shares = land.measure(conn, query="select 'p'::char(1) as t, id::bigint as id, ST_Transform(geom, 4326) as geom "
                                      "from rb_piece")
    with conn.cursor() as cur:
        with cur.copy("copy rb_dev from stdin") as cp:
            for (_, pid), share in shares.items():
                cp.write_row((pid, share))
    return {"developed land": f"{current['id']} (CDL {current['cdl_year']})"}, current


# ---- 3. cross-sections -----------------------------------------------------------------------------

_INPUT_TABLES = """
create temp table rb_lanes on commit drop as
select l.* from core.segment_lanes l
where l.road_segment_id in (select road_segment_id from rb_piece where road_segment_id is not null);
create index on rb_lanes (road_segment_id);
create temp table rb_bike on commit drop as
select b.* from roads.segment_bike_xsection b
where b.road_segment_id in (select road_segment_id from rb_piece where road_segment_id is not null);
create index on rb_bike (road_segment_id);
create temp table rb_hpms_piece on commit drop as
select h.piece_id,
       jsonb_agg(jsonb_build_object('kind', h.kind, 'direction', hs.direction, 'through_lanes', hs.through_lanes,
                                    'lanes_ascending', hs.lanes_ascending, 'lanes_descending', hs.lanes_descending,
                                    'lane_width_ft', hs.lane_width_ft, 'shoulder_type', hs.shoulder_type,
                                    'shoulder_left_ft', hs.shoulder_width_left_ft,
                                    'shoulder_right_ft', hs.shoulder_width_right_ft,
                                    'median_type', hs.median_type, 'median_width_ft', hs.median_width_ft,
                                    'same_way', h.same_way, 'source_id', h.source_id, 'route_id', hs.route_id)
                 order by h.confidence desc, h.overlap_m desc) as hpms
from rb_hpms h join core.hpms_section hs on hs.kind = h.kind and hs.source_id = h.source_id
group by h.piece_id;
create index on rb_hpms_piece (piece_id);
analyze rb_lanes;
analyze rb_bike;
analyze rb_hpms_piece
"""

_INPUTS = """
select p.id, p.highway, p.service, w.oneway, p.roundabout, p.county, w.tags,
       p.road_segment_id, s.functional_class, s.one_way, p.seg_same_way, p.seg_confidence,
       to_jsonb(l) as lanes, to_jsonb(b) as bike, k.left_m, k.right_m, d.share, h.hpms
from rb_piece p
join rb_way w using (osm_id)
left join core.road_segment s on s.id = p.road_segment_id
left join rb_lanes l on l.road_segment_id = p.road_segment_id
left join rb_bike b on b.road_segment_id = p.road_segment_id
left join rb_hpms_piece h on h.piece_id = p.id
left join rb_walk k on k.piece_id = p.id
left join rb_dev d on d.piece_id = p.id
order by p.id
"""


def hpms_input(rows):
    """rb_hpms' rows for one piece (best first) as cross_section()'s hpms."""
    if not rows:
        return None
    out = {"through": []}
    for r in rows:
        k = r["kind"]
        if k == "through_lanes":
            out["through"].append(r)
        elif k == "lane_width" and "lane_width_ft" not in out and r.get("lane_width_ft"):
            out["lane_width_ft"] = r["lane_width_ft"]
        elif k == "shoulders" and "shoulder" not in out and r.get("shoulder_type"):
            out["shoulder"] = {"type": r["shoulder_type"], "left_ft": r.get("shoulder_left_ft"),
                               "right_ft": r.get("shoulder_right_ft")}
        elif k == "median" and "median" not in out and r.get("median_type"):
            out["median"] = {"type": r["median_type"], "width_ft": r.get("median_width_ft")}
    return out


def piece_input(row):
    (pid, highway, service, oneway, roundabout, county, tags, seg_id, fclass, seg_one_way, same_way, seg_conf,
     lanes, bike, left_m, right_m, share, hpms) = row
    seg = None
    if seg_id is not None:
        seg = {"id": seg_id, "functional_class": fclass, "one_way": seg_one_way, "same_way": same_way,
               "confidence": seg_conf}
    return {"id": pid, "highway": highway, "service": service, "oneway": oneway, "roundabout": roundabout,
            "county": county, "tags": tags, "seg": seg, "lanes": lanes if seg else None, "bike": bike if seg else None,
            "hpms": hpms_input(hpms), "sidewalk": {"left": left_m, "right": right_m}, "developed": share}


XS_COLUMNS = ("piece_id", "lanes_fwd", "lanes_bwd", "centre_turn", "turn_fwd", "turn_bwd", "lanes_source", "lanes_conf",
              "lane_w_m", "bike_l_m", "bike_r_m", "park_l_m", "park_r_m", "shoulder_l_m", "shoulder_r_m", "edge_l",
              "edge_r", "median_kind", "median_w_m", "width_left_m", "width_right_m", "total_w_m", "width_tier",
              "width_source", "material", "material_source", "markings", "sources", "republish", "flags")


def cross_sections(conn):
    """Compute and store every piece's cross-section. Returns (stats, {piece id: (xs, way, highway)}, reviews)."""
    run_sql(conn, _INPUT_TABLES)
    out, reviews, tiers, sources = {}, [], {}, {}
    with conn.cursor() as cur:
        cur.execute(_INPUTS)
        rows = cur.fetchall()
    with conn.cursor() as cur:
        with cur.copy(f"copy roads.xsection ({', '.join(XS_COLUMNS)}) from stdin") as cp:
            for row in rows:
                p = piece_input(row)
                xs = X.cross_section(p)
                way = X.travel(p["oneway"])
                out[p["id"]] = (xs, way, p["highway"])
                for kind, detail in xs["reviews"]:
                    reviews.append((kind, p["id"], detail))
                tiers[xs["width_tier"]] = tiers.get(xs["width_tier"], 0) + 1
                sources[xs["lanes_source"]] = sources.get(xs["lanes_source"], 0) + 1
                cp.write_row([p["id"]] + [json.dumps(xs[c]) if c == "sources" else xs[c] for c in XS_COLUMNS[1:]])
    conn.execute("analyze roads.xsection")
    stats = {"tiers": tiers, "lane sources": sources,
             "markings": sum(1 for xs, _, _ in out.values() if xs["markings"])}
    return stats, out, reviews


# ---- 4. junctions ----------------------------------------------------------------------------------

_RANK = {"major": 3, "collector": 2, "local": 1}


def _rank(highway):
    return _RANK[X.road_class(highway)]


def corner_radius(highways):
    """The curb-return radius where these classes meet: by the two highest (CORNER_RADIUS) ⚠️; MINOR_RADIUS where
    an alley or a service way meets a single street."""
    named = [h for h in highways if h != "service"]
    if len(named) < 2:
        return MINOR_RADIUS
    classes = sorted((X.road_class(h) for h in named), key=lambda c: -_RANK[c])
    top, second = classes[0], classes[1]
    return CORNER_RADIUS[(top, second)] if (top, second) in CORNER_RADIUS else CORNER_RADIUS[(second, top)]


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, a):
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def cluster(nodes, pieces):
    """Junction clusters. nodes: {node id: (x, y)} of nodes where three or more piece ends meet. pieces: [(id,
    from_node, to_node, length_m, highway, roundabout, deck)]. Two junction nodes are one junction when a piece
    joins them that's shorter than the eps of the higher class at either node, or when both are on one
    roundabout. Returns [[node ids]]."""
    best = {}
    for pid, a, b, length, hw, rb, deck in pieces:
        for n in (a, b):
            if n in nodes:
                best[n] = max(best.get(n, 0), _rank(hw))
    eps_of = {3: CLUSTER_EPS["major"], 2: CLUSTER_EPS["collector"], 1: CLUSTER_EPS["local"]}
    uf = UnionFind()
    for n in nodes:
        uf.find(n)
    for pid, a, b, length, hw, rb, deck in pieces:
        if a in nodes and b in nodes and a != b and not deck:
            if rb or length <= eps_of[max(best[a], best[b])]:
                uf.union(a, b)
    groups = {}
    for n in nodes:
        groups.setdefault(uf.find(n), []).append(n)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


def junctions(conn, xsections):
    """Cluster the junction nodes, write roads.junction and the pieces' from/to junctions, and rb_junc (each
    junction's radius and disc for its closing)."""
    nodes = {n: (x, y) for n, x, y in conn.execute(
        "select id, ST_X(geom), ST_Y(geom) from rb_node where degree >= 3").fetchall()}
    plist = conn.execute("select id, from_node, to_node, length_m, highway, roundabout, bridge or tunnel "
                         "from rb_piece").fetchall()
    groups = cluster(nodes, plist)
    at = {}
    for pid, a, b, *_ in plist:
        for n in (a, b):
            if n in nodes:
                at.setdefault(n, set()).add(pid)
    info = {pid: (hw, rb, deck) for pid, _, _, _, hw, rb, deck in plist}
    signals = conn.execute(
        """select i.id, ST_X(g), ST_Y(g) from core.intersection i
           cross join lateral ST_Transform(i.geom, %(srid)s) g
           where i.status = 'active' and i.control in ('signal', 'half_signal', 'signal_uturn')""",
        {"srid": SRID}).fetchall()
    rows, node_junction, discs = [], {}, []
    for jid, g in enumerate(groups, start=1):
        xs_ = [nodes[n][0] for n in g]
        ys_ = [nodes[n][1] for n in g]
        cx, cy = sum(xs_) / len(g), sum(ys_) / len(g)
        spread = max(math.hypot(x - cx, y - cy) for x, y in zip(xs_, ys_))
        ps = sorted(set().union(*(at[n] for n in g)))
        grade = [p for p in ps if not info[p][2]]
        hws = [info[p][0] for p in grade] or [info[p][0] for p in ps]
        roundabout = any(info[p][1] for p in ps)
        if any(h == "motorway" for h in hws):
            kind, r = "interchange", 0.0
        else:
            r = corner_radius(hws) if len(hws) > 1 else MINOR_RADIUS
            kind = "roundabout" if roundabout else "plain"
            if roundabout:
                r = min(r, ROUNDABOUT_RADIUS_MAX)
        sig = None
        if kind != "interchange":
            near = [(math.hypot(sx - cx, sy - cy), sid) for sid, sx, sy in signals
                    if abs(sx - cx) < 40 + spread and abs(sy - cy) < 40 + spread]
            near = [t for t in near if t[0] <= 30 + spread]
            if near:
                sig = min(near)[1]
                if kind == "plain":
                    kind = "signal"
        half = max((max(xsections[p][0]["width_left_m"], xsections[p][0]["width_right_m"]) for p in grade
                    if p in xsections), default=5.0)
        disc = min(90.0, spread + 2 * half + 1.5 * r + 2.0)
        rows.append((jid, kind, len(g), ps, r, sig, cx, cy, spread))
        discs.append((jid, r, disc))
        for n in g:
            node_junction[n] = jid
    with conn.cursor() as cur:
        with cur.copy("copy roads.junction (id, kind, nodes, pieces, radius_m, intersection_id, geom) from stdin") as cp:
            for jid, kind, n, ps, r, sig, cx, cy, _ in rows:
                cp.write_row((jid, kind, n, ps, r, sig, f"SRID={SRID};POINT({cx} {cy})"))
    conn.execute("create temp table rb_nj (node int primary key, junction int) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy rb_nj from stdin") as cp:
            for n, j in node_junction.items():
                cp.write_row((n, j))
    conn.execute("""update rb_piece p set from_junction = a.junction from rb_nj a where a.node = p.from_node""")
    conn.execute("""update rb_piece p set to_junction = b.junction from rb_nj b where b.node = p.to_node""")
    conn.execute("create temp table rb_junc (id int primary key, r real, disc_r real, geom geometry) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy rb_junc (id, r, disc_r) from stdin") as cp:
            for d in discs:
                cp.write_row(d)
    conn.execute("analyze roads.junction")
    conn.execute("insert into roads.piece select * from rb_piece")      # the pieces, final, written once
    conn.execute("analyze roads.piece")
    conn.execute("update rb_junc r set geom = ST_Buffer(j.geom, r.disc_r, 'quad_segs=8') from roads.junction j "
                 "where j.id = r.id")
    conn.execute("create index on rb_junc using gist (geom)")
    large = [(jid, n, spread) for jid, kind, n, ps, r, sig, cx, cy, spread in rows
             if n > LARGE_JUNCTION["nodes"] or spread > LARGE_JUNCTION["spread_m"]]
    kinds = {}
    for row in rows:
        kinds[row[1]] = kinds.get(row[1], 0) + 1
    return {"junctions": len(rows), "junction kinds": kinds}, large


# ---- 5. surfaces -----------------------------------------------------------------------------------

def z15(g):
    """SQL: geometry g generalised for z15 (Z15_TOLERANCE_M), or null when it's under Z15_MIN_M2."""
    return (f"(case when ST_Area({g}) >= {Z15_MIN_M2} then ST_Multi(ST_CollectionExtract(ST_MakeValid("
            f"ST_SimplifyPreserveTopology({g}, {Z15_TOLERANCE_M})), 3)) end)")


# Where two pieces meet end to end at an angle, their flat ends leave a wedge open on the outside of the bend: a
# disc of the narrower half-width closes it (joined to the lower-numbered piece's surface).
_JOINTS = """
create temp table rb_joint on commit drop as
with ends as (
  select id as piece, from_node as node from roads.piece where not tunnel
  union all select id, to_node from roads.piece where not tunnel
), j as (
  select e.node, min(e.piece) as piece, min(least(x.width_left_m, x.width_right_m)) as r,
         bool_and(p.bridge) = bool_or(p.bridge) as same_deck
  from ends e join roads.xsection x on x.piece_id = e.piece join roads.piece p on p.id = e.piece
  join rb_node n on n.id = e.node and n.degree = 2
  group by e.node having count(*) = 2
)
select j.piece, ST_Union(ST_Buffer(n.geom, j.r, 'quad_segs=8')) as g
from j join rb_node n on n.id = j.node where j.same_deck and j.r > 0
group by j.piece;
create index on rb_joint (piece);
analyze rb_joint
"""

_CARRIAGEWAYS = """
insert into roads.surface (id, kind, piece_id, material, tier, layer, geom, geom_z15)
select c.id, c.kind, c.piece_id, c.material, c.tier, c.layer, c.g, {z15}
from (
  select row_number() over (order by p.id) as id, case when p.bridge then 'deck' else 'carriageway' end as kind,
         p.id as piece_id, x.material, x.width_tier as tier, p.layer,
         ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Union(
           ST_Difference(
             ST_Union(ST_Buffer(p.geom, x.width_left_m, 'side=left join=mitre mitre_limit=2'),
                      ST_Buffer(p.geom, x.width_right_m, 'side=right join=mitre mitre_limit=2')),
             case when x.median_w_m > 0
                  then ST_Buffer(p.geom, x.median_w_m / 2, 'endcap=flat join=mitre mitre_limit=2')
                  else ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611) end),
           coalesce(jt.g, ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611)))), 3)) as g
  from roads.piece p join roads.xsection x on x.piece_id = p.id
  left join rb_joint jt on jt.piece = p.id
  where not p.tunnel
) c
where not ST_IsEmpty(c.g)
""".format(z15=z15("c.g"))

_MEDIANS = """
insert into roads.surface (id, kind, piece_id, material, tier, layer, geom, geom_z15)
select m.id, 'median', m.piece_id, 'concrete', m.tier, m.layer, m.g, {z15}
from (
  select (select coalesce(max(id), 0) from roads.surface) + row_number() over (order by p.id) as id, p.id as piece_id,
         x.width_tier as tier, p.layer,
         ST_Multi(ST_CollectionExtract(ST_MakeValid(
           ST_Buffer(p.geom, x.median_w_m / 2, 'endcap=flat join=mitre mitre_limit=2')), 3)) as g
  from roads.piece p join roads.xsection x on x.piece_id = p.id
  where not p.tunnel and x.median_w_m > 0 and x.median_kind in ('curbed', 'barrier')
) m
where not ST_IsEmpty(m.g)
""".format(z15=z15("m.g"))


def surfaces(conn):
    run_sql(conn, _JOINTS)
    conn.execute(_CARRIAGEWAYS)
    conn.execute(_MEDIANS)
    conn.execute("analyze roads.surface")
    return dict(conn.execute("select kind, count(*) from roads.surface group by 1").fetchall())


# ---- 6. islands ------------------------------------------------------------------------------------

_FACES = """
create temp table rb_face on commit drop as
select row_number() over () as id, f.g, ST_Area(f.g) as a, 2 * ST_Area(f.g) / nullif(ST_Perimeter(f.g), 0) as thin,
       false as roundabout
from (select (ST_Dump(ST_Polygonize(geom))).geom as g
      from roads.piece where not bridge and not tunnel) f;
insert into rb_face (id, g, a, thin, roundabout)
select (select max(id) from rb_face) + row_number() over (), f.g, ST_Area(f.g), null, true
from (select (ST_Dump(ST_Polygonize(geom))).geom as g from roads.piece where roundabout and not bridge and not tunnel) f;
create index on rb_face using gist (g);
delete from rb_face f using rb_face r
where r.roundabout and not f.roundabout and f.g && r.g and abs(f.a - r.a) < 0.01 * r.a
  and ST_Area(ST_SymDifference(f.g, r.g)) < 1;
analyze rb_face;
"""

# A face that's small, thin or a roundabout's centre, near a junction, less every at-grade carriageway over it.
_ISLANDS = """
create temp table rb_island on commit drop as
with f as (
  select f.* from rb_face f
  where (f.roundabout or f.a <= %(island_max)s or f.thin <= %(thin)s)
    and exists (select 1 from rb_junc j where j.geom && f.g and ST_Intersects(j.geom, f.g))
), d as (
  select f.id, f.a, f.roundabout,
         ST_CollectionExtract(ST_MakeValid(ST_Difference(f.g, coalesce(
           (select ST_Union(s.geom) from roads.surface s
            where s.geom && f.g and s.kind = 'carriageway' and ST_Intersects(s.geom, f.g)),
           ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611)))), 3) as g
  from f
)
select d.id, d.a, d.roundabout, (ST_Dump(d.g)).geom as g from d where not ST_IsEmpty(d.g);
delete from rb_island where ST_Area(g) < %(island_min)s;
create index on rb_island using gist (g);
analyze rb_island;
"""


def islands(conn):
    run_sql(conn, _FACES)
    run_sql(conn, _ISLANDS, {"island_max": ISLAND_MAX_M2, "thin": THIN_M, "island_min": ISLAND_MIN_M2})
    return dict(zip(("faces", "island parts"), conn.execute(
        "select (select count(*) from rb_face), (select count(*) from rb_island)").fetchone()))


# ---- 7. closings -----------------------------------------------------------------------------------

# The arms of each junction: its pieces that leave it (a piece with both ends in it is inside it), with the
# direction each leaves in (over its first 15 m) and where it lies around the junction's centre (bearing to a point
# 20 m out, or its far end).
_ARMS = """
create temp table rb_arm on commit drop as
select j.id as junction_id, p.id as piece_id, e.at_end,
       degrees(ST_Azimuth(ST_StartPoint(e.g), ST_LineInterpolatePoint(e.g, least(1, 15 / p.length_m)))) as dir,
       degrees(ST_Azimuth(j.geom, ST_LineInterpolatePoint(e.g, least(1, 20 / p.length_m)))) as pos
from roads.junction j
join roads.piece p on p.id = any(j.pieces)
cross join lateral (values ('from', p.from_junction = j.id, p.geom), ('to', p.to_junction = j.id, ST_Reverse(p.geom)))
  e(at_end, here, g)
where e.here and p.from_junction is distinct from p.to_junction and not p.bridge and not p.tunnel
"""

# Each junction's carriageways, cut to its disc's box once: the closings, the lines' trims and the fills' cut read
# these small parts, never the pieces' whole surfaces (a rural piece can run for kilometres).
_JCLIP = """
create temp table rb_jclip on commit drop as
select j.id as junction_id, p.id as piece_id, p.from_junction = p.to_junction as inner_, rj.r,
       ST_CollectionExtract(ST_MakeValid(ST_ClipByBox2D(s.geom, ST_Envelope(rj.geom))), 3) as g
from roads.junction j join rb_junc rj on rj.id = j.id
join roads.piece p on p.id = any(j.pieces)
join roads.surface s on s.piece_id = p.id and s.kind = 'carriageway';
delete from rb_jclip where g is null or ST_IsEmpty(g);
create index on rb_jclip (junction_id);
analyze rb_jclip
"""

# The curb returns: for each pair of arms side by side around a junction (not parallel: a divided road's two
# carriageways leave the same way, and the median between them stays open), their carriageways and the junction's
# inner pieces', cut to its disc, closed by its radius. What the closings add, less the junction's carriageways and
# the islands, is its fill.
_FILLS = """
create temp table rb_fill on commit drop as
with u as (
  select pr.junction_id as id, pr.a, pr.b, rj.r, rj.geom as disc,
         ST_Union(ST_Intersection(c.g, rj.geom)) as g
  from rb_pair pr join rb_junc rj on rj.id = pr.junction_id
  join rb_jclip c on c.junction_id = pr.junction_id and (c.piece_id in (pr.a, pr.b) or c.inner_)
  group by pr.junction_id, pr.a, pr.b, rj.r, rj.geom
), c as (
  select u.id, ST_Difference(ST_Buffer(ST_Buffer(u.g, u.r, 'quad_segs=4'), -u.r, 'quad_segs=4'), u.g) as added
  from u
), j as (
  select c.id, ST_Union(c.added) as added from c where not ST_IsEmpty(c.added) group by c.id
), k as (
  select j.id,
         ST_Difference(j.added, ST_Union(
           coalesce((select ST_Union(c.g) from rb_jclip c where c.junction_id = j.id),
                    ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611)),
           coalesce((select ST_Union(i.g) from rb_island i join rb_junc rj on rj.id = j.id
                     where i.g && rj.geom and ST_Intersects(i.g, rj.geom)),
                    ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611)))) as g
  from j
)
select k.id as junction_id, (ST_Dump(ST_CollectionExtract(ST_MakeValid(k.g), 3))).geom as g from k
"""

_FILL_SURFACES = """
delete from rb_fill where ST_Area(g) < %(min)s or 2 * ST_Area(g) / nullif(ST_Perimeter(g), 0) < 0.15;
insert into roads.surface (id, kind, junction_id, material, tier, layer, geom, geom_z15)
select q.id, 'junction', q.junction_id, q.material, q.tier, 0, q.g, {z15}
from (
  select (select coalesce(max(id), 0) from roads.surface) + row_number() over (order by f.junction_id) as id,
         f.junction_id, m.material, m.tier, ST_Multi(ST_Union(f.g)) as g
  from rb_fill f
  cross join lateral (
    select mode() within group (order by x.material) as material,
           (array['estimated', 'counted', 'measured', 'inventoried'])[min(array_position(
             array['estimated', 'counted', 'measured', 'inventoried'], x.width_tier))] as tier
    from roads.junction j join roads.xsection x on x.piece_id = any(j.pieces)
    join roads.piece p on p.id = x.piece_id and not p.bridge and not p.tunnel
    where j.id = f.junction_id) m
  group by f.junction_id, m.material, m.tier
) q
""".format(z15=z15("q.g"))

_ISLAND_SURFACES = """
insert into roads.surface (id, kind, junction_id, material, tier, layer, geom, geom_z15)
select (select coalesce(max(id), 0) from roads.surface) + row_number() over (order by i.id),
       'island', j.id, 'concrete', 'estimated', 0, ST_Multi(i.g), {z15}
from rb_island i
cross join lateral (select rj.id from rb_junc rj where rj.geom && i.g and ST_Intersects(rj.geom, i.g)
                    order by ST_Distance(rj.geom, ST_PointOnSurface(i.g)) limit 1) j
where i.roundabout or i.a <= %(island_max)s
""".format(z15=z15("i.g"))


PARALLEL_DEG = 25.0         # arms leaving within this of each other are parallel: no curb return between them
STRAIGHT_DEG = 170.0        # nor between arms this far apart around the junction (a straight road through it)


def arm_pairs(arms):
    """The pairs of arms side by side around a junction that get a curb return between them. arms: [(piece_id,
    at_end, dir, pos)] (degrees). Sorted round by position; each arm with the next, but not when they leave in
    nearly the same direction (a divided road's carriageways) or lie nearly opposite. Returns [(a, b)]."""
    if len(arms) < 2:
        return []
    ring = sorted(arms, key=lambda a: a[3] % 360)
    out = []
    for i, a in enumerate(ring):
        b = ring[(i + 1) % len(ring)]
        if b is a or (len(ring) == 2 and i == 1):
            continue
        gap = (b[3] - a[3]) % 360
        turn = abs((b[2] - a[2] + 180) % 360 - 180)
        if gap >= STRAIGHT_DEG or turn < PARALLEL_DEG:
            continue
        if a[0] != b[0]:
            out.append((a[0], b[0]))
    return out


def closings(conn):
    run_sql(conn, _JCLIP)
    run_sql(conn, _ARMS)
    arms = {}
    for jid, pid, at_end, d, pos in conn.execute(
            """select a.junction_id, a.piece_id, a.at_end, a.dir, a.pos from rb_arm a
               join rb_junc r on r.id = a.junction_id where r.r > 0""").fetchall():
        arms.setdefault(jid, []).append((pid, at_end, d, pos))
    conn.execute("create temp table rb_pair (junction_id int, a int, b int) on commit drop")
    n = 0
    with conn.cursor() as cur:
        with cur.copy("copy rb_pair from stdin") as cp:
            for jid, a in arms.items():
                for x, y in arm_pairs(a):
                    cp.write_row((jid, x, y))
                    n += 1
    conn.execute(_FILLS)
    run_sql(conn, _FILL_SURFACES, {"min": FILL_MIN_M2})
    conn.execute(_ISLAND_SURFACES, {"island_max": ISLAND_MAX_M2})
    conn.execute("analyze roads.surface")
    return dict(conn.execute("select kind, count(*) from roads.surface where kind in ('junction', 'island') "
                             "group by 1").fetchall()) | {"corner pairs": n}


# ---- 8. edges --------------------------------------------------------------------------------------

# Each surface's outline, less every surface it meets (2 cm), so a seam between two surfaces isn't an edge.
# Meets: at grade, two at-grade surfaces that touch; a deck, the decks and surfaces of pieces sharing its nodes.
_EDGES = """
create temp table rb_surf on commit drop as
select s.id, s.kind, s.piece_id, s.junction_id, s.tier, s.layer, s.geom, s.kind = 'deck' as deck,
       p.from_node, p.to_node
from roads.surface s left join roads.piece p on p.id = s.piece_id
where s.kind in ('carriageway', 'deck', 'junction');
create index on rb_surf using gist (geom);
analyze rb_surf;
create temp table rb_edge on commit drop as
select s.id, s.kind, s.piece_id, s.junction_id, s.tier, s.layer,
       ST_CollectionExtract(ST_MakeValid(ST_Difference(ST_Boundary(s.geom), coalesce(
         (select ST_Union(ST_Buffer(ST_ClipByBox2D(o.geom, ST_Expand(ST_Envelope(s.geom), 1)), 0.02, 'quad_segs=2'))
          from rb_surf o
          where o.id <> s.id and o.geom && s.geom and ST_Intersects(o.geom, s.geom)
            and ((not s.deck and not o.deck)
                 or (s.from_node is not null and o.from_node is not null
                     and (o.from_node in (s.from_node, s.to_node) or o.to_node in (s.from_node, s.to_node)))
                 or (s.deck and o.deck and o.layer = s.layer))),
         ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611)))), 2) as g
from rb_surf s
"""

_EDGE_ROWS = """
insert into roads.edge (id, kind, tier, layer, piece_id, junction_id, geom)
select row_number() over (order by e.id), e.kind_, e.tier, e.layer, e.piece_id, e.junction_id, ST_Multi(e.g)
from (
  select e.id, e.tier, e.layer, e.piece_id, e.junction_id, d.geom as g,
         case when e.kind = 'deck' then 'deck'
              when e.kind = 'junction' then 'curb'
              when x.edge_l = x.edge_r then x.edge_l
              when ST_Distance(ST_LineInterpolatePoint(d.geom, 0.5), ST_OffsetCurve(p.geom, x.width_left_m))
                   < ST_Distance(ST_LineInterpolatePoint(d.geom, 0.5), ST_OffsetCurve(p.geom, -x.width_right_m))
                then x.edge_l
              else x.edge_r end as kind_
  from rb_edge e
  cross join lateral ST_Dump(ST_LineMerge(e.g)) d
  left join roads.piece p on p.id = e.piece_id
  left join roads.xsection x on x.piece_id = e.piece_id
  where not ST_IsEmpty(e.g) and ST_Length(d.geom) >= 0.2
) e
"""


def edges(conn):
    run_sql(conn, _EDGES)
    conn.execute(_EDGE_ROWS)
    return dict(conn.execute("select kind, count(*) from roads.edge group by 1").fetchall())


# ---- 9. crosswalks ---------------------------------------------------------------------------------

# A marked crossing node on a piece (within 0.5 m of its line): a rectangle CROSSWALK_DEPTH_M deep, across the
# road along its crossing way's chord (else square to the piece), as long as the road is wide and more, clipped
# to the surfaces there. Rail crossings are never marked (P8).
_CROSSWALKS = """
create temp table rb_xwalk on commit drop as
with n as (
  select w.osm_id, ST_Transform(w.geom, %(srid)s) as g, w.ways
  from roads.osm_walk_node w where w.active and w.kind = 'crossing' and w.marked
), on_piece as (
  select distinct on (n.osm_id) n.osm_id, n.g, n.ways, p.id as piece_id, p.geom as pg, p.layer, x.total_w_m
  from n join roads.piece p on ST_DWithin(p.geom, n.g, 0.5) and not p.tunnel
  join roads.xsection x on x.piece_id = p.id
  order by n.osm_id, ST_Distance(p.geom, n.g), p.id
), dir as (
  select o.*,
         coalesce(
           (select ST_Azimuth(ST_StartPoint(c.g), ST_EndPoint(c.g))
            from (select ST_Transform(v.geom, %(srid)s) as g from roads.osm_paving v
                  where v.osm_id = any(o.ways) and v.active and v.kind = 'crossing') c
            where ST_Length(c.g) > 1
            order by ST_Distance(c.g, o.g) limit 1),
           ST_Azimuth(ST_LineInterpolatePoint(o.pg, greatest(0, ST_LineLocatePoint(o.pg, o.g) - 1 / ST_Length(o.pg))),
                      ST_LineInterpolatePoint(o.pg, least(1, ST_LineLocatePoint(o.pg, o.g) + 1 / ST_Length(o.pg))))
             + pi() / 2) as az
  from on_piece o
), r as (
  select d.*, greatest(d.total_w_m * 2.5, 12) as len from dir d
)
select r.osm_id, r.piece_id, r.layer,
       ST_Buffer(ST_MakeLine(ST_Translate(r.g, -sin(r.az) * r.len / 2, -cos(r.az) * r.len / 2),
                             ST_Translate(r.g, sin(r.az) * r.len / 2, cos(r.az) * r.len / 2)),
                 %(half)s, 'endcap=flat') as rect, r.g
from r
"""

_CROSSWALK_ROWS = """
insert into roads.marking (id, kind, dash, piece_id, node_osm_id, geom)
select (select coalesce(max(id), 0) from roads.marking) + row_number() over (order by c.osm_id), 'crosswalk', 'solid',
       c.piece_id, c.osm_id, ST_Multi(c.cw)
from (
  select x.osm_id, x.piece_id,
         (select d.geom from ST_Dump(ST_CollectionExtract(ST_MakeValid(ST_Intersection(x.rect, u.g)), 3)) d
          order by ST_Distance(d.geom, x.g) limit 1) as cw
  from rb_xwalk x
  cross join lateral (select ST_Union(s.geom) as g from roads.surface s
                      where s.geom && x.rect and ST_Intersects(s.geom, x.rect) and s.layer = x.layer
                        and s.kind in ('carriageway', 'junction', 'deck')) u
  where u.g is not null
) c
where c.cw is not null and ST_Area(c.cw) >= 1
"""


def crosswalks(conn):
    conn.execute(_CROSSWALKS, {"srid": SRID, "half": CROSSWALK_DEPTH_M / 2})
    conn.execute(_CROSSWALK_ROWS)
    n, nodes = conn.execute("select (select count(*) from roads.marking where kind = 'crosswalk'), "
                            "(select count(*) from rb_xwalk)").fetchone()
    return {"crosswalks": n, "marked crossing nodes on pieces": nodes}


# ---- 10. markings ----------------------------------------------------------------------------------

# How far a piece's lines stop short of each end: at a junction, the length of the piece's line inside the
# other pieces' carriageways there, plus the curb-return radius and JUNCTION_CLEAR_M; at a dead end a little;
# where it continues into one other piece, nothing.
_TRIMS = """
create temp table rb_trim on commit drop as
with e as (
  select p.id, 'from'::text as at_end, p.from_junction as j, p.geom, p.length_m,
         (select degree from rb_node n where n.id = p.from_node) as degree
  from roads.piece p
  union all
  select p.id, 'to', p.to_junction, ST_Reverse(p.geom), p.length_m,
         (select degree from rb_node n where n.id = p.to_node)
  from roads.piece p
), k as (
  select e.*, rj.r,
         (select ST_Union(c.g) from rb_jclip c where c.junction_id = e.j and c.piece_id <> e.id) as other
  from e left join rb_junc rj on rj.id = e.j
)
select k.id, k.at_end,
       case when k.j is not null then
              coalesce((select max(ST_Length(d.geom)) from ST_Dump(ST_Intersection(
                          ST_LineSubstring(k.geom, 0, least(1, 80 / k.length_m)), k.other)) d
                        where ST_DWithin(ST_StartPoint(d.geom), ST_StartPoint(k.geom), 0.05)), 0)
              + coalesce(k.r, 0) + %(clear)s
            when k.degree = 1 then %(dead)s
            else 0 end as trim_m
from k
"""

# A crosswalk at a junction end (within its trim and 8 m more): the lines, and a stop bar, stop just before it.
_TRIM_TO_CROSSWALKS = """
update rb_trim t set trim_m = greatest(t.trim_m, c.d + %(half)s + %(gap)s)
from (
  select m.piece_id, e.at_end, min(e.d) as d
  from roads.marking m join roads.piece p on p.id = m.piece_id
  cross join lateral (select ST_LineLocatePoint(p.geom, ST_Centroid(m.geom)) * p.length_m as along) a
  cross join lateral (values ('from', a.along), ('to', p.length_m - a.along)) e(at_end, d)
  where m.kind = 'crosswalk'
  group by 1, 2
) c
where c.piece_id = t.id and c.at_end = t.at_end and t.trim_m > 0 and c.d <= t.trim_m + %(reach)s
"""

_LINES = """
insert into roads.marking (id, kind, dash, piece_id, geom)
select (select coalesce(max(id), 0) from roads.marking) + row_number() over (order by l.piece_id, l.n), l.kind, l.dash,
       l.piece_id, ST_Multi(l.g)
from (
  select m.piece_id, m.n, m.kind, m.dash,
         ST_CollectionExtract(ST_Difference(
           ST_OffsetCurve(ST_LineSubstring(p.geom, a.f0, a.f1), -m.offset_m, 'join=mitre mitre_limit=2'),
           coalesce((select ST_Union(ST_Buffer(c.geom, %(clear)s)) from roads.marking c
                     where c.kind = 'crosswalk' and c.geom && ST_Expand(p.geom, 30)
                       and ST_DWithin(c.geom, p.geom, 1)), ST_GeomFromText('GEOMETRYCOLLECTION EMPTY', 32611))), 2) as g
  from rb_lines m
  join roads.piece p on p.id = m.piece_id
  cross join lateral (select tf.trim_m / p.length_m as f0, 1 - tt.trim_m / p.length_m as f1
                      from rb_trim tf, rb_trim tt
                      where tf.id = p.id and tf.at_end = 'from' and tt.id = p.id and tt.at_end = 'to') a
  where a.f1 - a.f0 > 0.05 and (a.f1 - a.f0) * p.length_m >= 3
) l
where not ST_IsEmpty(l.g) and ST_Length(l.g) >= 1
"""

# Stop bars: on a signal junction's approaches, across the lanes coming in, where the lines stop (or just
# before a crosswalk there).
_STOP_BARS = """
insert into roads.marking (id, kind, dash, piece_id, junction_id, geom)
select (select coalesce(max(id), 0) from roads.marking) + row_number() over (order by b.piece_id, b.at_end), 'stop_bar',
       'solid', b.piece_id, b.j, ST_Multi(b.g)
from (
  select s.piece_id, s.at_end, s.j,
         ST_MakeLine(ST_Translate(c.pt, s.a * cos(c.az), -s.a * sin(c.az)),
                     ST_Translate(c.pt, s.b * cos(c.az), -s.b * sin(c.az))) as g
  from rb_stop s
  join roads.piece p on p.id = s.piece_id
  join rb_trim t on t.id = s.piece_id and t.at_end = s.at_end
  cross join lateral (
    select least(greatest(case when s.at_end = 'to' then 1 - t.trim_m / p.length_m else t.trim_m / p.length_m end,
                          0.02), 0.98) as f) q
  cross join lateral (
    select ST_LineInterpolatePoint(p.geom, q.f) as pt,
           ST_Azimuth(ST_LineInterpolatePoint(p.geom, greatest(0, q.f - 1 / p.length_m)),
                      ST_LineInterpolatePoint(p.geom, least(1, q.f + 1 / p.length_m))) as az) c
  where p.length_m > t.trim_m + 3
) b
"""

_ARROWS = """
insert into roads.arrow (id, piece_id, direction, lane, turns, bearing, geom)
select row_number() over (order by a.piece_id, a.direction, a.lane), a.piece_id, a.direction, a.lane, a.turns,
       mod((degrees(c.az) + case when a.direction = 'backward' then 180 else 0 end)::numeric + 360, 360)::real,
       ST_Translate(c.pt, a.offset_m * cos(c.az), -a.offset_m * sin(c.az))
from rb_arrow a
join roads.piece p on p.id = a.piece_id
join rb_trim t on t.id = a.piece_id and t.at_end = case when a.direction = 'forward' then 'to' else 'from' end
cross join lateral (
  select case when a.direction = 'forward' then 1 - (t.trim_m + %(back)s) / p.length_m
              else (t.trim_m + %(back)s) / p.length_m end as f) q
cross join lateral (
  select ST_LineInterpolatePoint(p.geom, q.f) as pt,
         ST_Azimuth(ST_LineInterpolatePoint(p.geom, greatest(0, q.f - 1 / p.length_m)),
                    ST_LineInterpolatePoint(p.geom, least(1, q.f + 1 / p.length_m))) as az) c
where q.f between 0.05 and 0.95
"""


def markings(conn, xsections):
    """Lines, stop bars and arrows from each piece's cross-section."""
    conn.execute(_TRIMS, {"clear": JUNCTION_CLEAR_M, "dead": DEAD_END_TRIM_M})
    conn.execute("create index on rb_trim (id, at_end)")
    conn.execute(_TRIM_TO_CROSSWALKS, {"half": CROSSWALK_DEPTH_M / 2, "gap": STOP_BAR_GAP_M, "reach": 8.0})
    conn.execute("create temp table rb_lines (piece_id int, n int, kind text, dash text, offset_m real) on commit drop")
    conn.execute("create temp table rb_stop (piece_id int, at_end text, j int, a real, b real) on commit drop")
    conn.execute("create temp table rb_arrow (piece_id int, direction text, lane int, offset_m real, turns text[]) "
                 "on commit drop")
    ends = {pid: (fj, tj) for pid, fj, tj in conn.execute(
        "select id, from_junction, to_junction from roads.piece").fetchall()}
    kinds = {j: k for j, k in conn.execute("select id, kind from roads.junction").fetchall()}
    with conn.cursor() as cur:
        with cur.copy("copy rb_lines from stdin") as cp:
            for pid, (xs, way, hw) in xsections.items():
                fj, tj = ends[pid]
                if fj is not None and fj == tj:
                    continue                  # inside one junction: no lines
                for n, (kind, dash, off) in enumerate(X.marking_lines(xs, way, hw)):
                    cp.write_row((pid, n, kind, dash, off))
    with conn.cursor() as cur:
        with cur.copy("copy rb_stop from stdin") as cp:
            for pid, (xs, way, hw) in xsections.items():
                if not xs["markings"]:
                    continue
                fj, tj = ends[pid]
                if fj is not None and fj == tj:
                    continue
                spans = xs["spans"]
                if tj is not None and kinds.get(tj) == "signal" and "fwd" in spans:
                    cp.write_row((pid, "to", tj, *spans["fwd"]))
                if fj is not None and kinds.get(fj) == "signal" and "bwd" in spans:
                    cp.write_row((pid, "from", fj, *spans["bwd"]))
    with conn.cursor() as cur:
        with cur.copy("copy rb_arrow from stdin") as cp:
            for pid, (xs, way, hw) in xsections.items():
                fj, tj = ends[pid]
                if fj is not None and fj == tj:
                    continue
                for direction, lane, off, turns in X.lane_centres(xs, way):
                    if (tj if direction == "forward" else fj) is not None:
                        cp.write_row((pid, direction, lane, off, turns))
    conn.execute(_LINES, {"clear": CROSSWALK_CLEAR_M})
    conn.execute(_STOP_BARS)
    conn.execute(_ARROWS, {"back": ARROW_BACK_M})
    return dict(conn.execute("select kind, count(*) from roads.marking group by 1").fetchall()) | \
        {"arrows": conn.execute("select count(*) from roads.arrow").fetchone()[0]}


# ---- 11. generalising and the review list ----------------------------------------------------------

def generalise(conn):
    """The surfaces' z15 copies are made as they're stored (z15()): here, what they come to."""
    a, b, n = conn.execute("select sum(ST_NPoints(geom)), sum(ST_NPoints(geom_z15)), count(*) filter (where geom_z15 "
                           "is null) from roads.surface").fetchone()
    return {"surface vertices": a, "z15 vertices": b, "surfaces left out at z15": n}


_REVIEW_SQL = {
    # A major or collector piece in Ada, 50 m or longer, that lies along no ACHD segment.
    "unmatched": """
      select p.id, p.osm_id, null::bigint, jsonb_build_object('highway', p.highway, 'name', p.name,
             'length_m', round(p.length_m)), ST_LineInterpolatePoint(p.geom, 0.5)
      from roads.piece p
      where p.county = 'Ada' and p.road_segment_id is null and p.length_m >= 50 and not p.tunnel
        and p.highway = any(%(ranked)s)""",
    # A piece along an elevated ACHD segment (level 20 at both ends: an overpass) that OpenStreetMap doesn't draw
    # as a bridge: no deck there. (OpenStreetMap's bridges over canals and creeks are at ACHD's level 10.)
    "deck_mismatch": """
      select p.id, p.osm_id, p.road_segment_id,
             jsonb_build_object('osm_bridge', p.bridge, 'achd_levels', array[s.from_level, s.to_level]),
             ST_LineInterpolatePoint(p.geom, 0.5)
      from roads.piece p join core.road_segment s on s.id = p.road_segment_id
      where p.length_m >= 15 and not p.bridge and s.from_level = 20 and s.to_level = 20""",
    # ACHD's bike network row whose other carriageway's sides are hidden, on a one-way piece.
    "bike_other_carriageway": """
      select p.id, p.osm_id, p.road_segment_id, jsonb_build_object('flags', b.flags),
             ST_LineInterpolatePoint(p.geom, 0.5)
      from roads.piece p join roads.segment_bike_xsection b on b.road_segment_id = p.road_segment_id
      where 'direction_conflicts_one_way' = any(b.flags)""",
    # A surface the geometry steps left invalid.
    "geometry": """
      select s.piece_id, p.osm_id, null::bigint, jsonb_build_object('surface', s.id, 'kind', s.kind,
             'reason', ST_IsValidReason(s.geom)), ST_PointOnSurface(s.geom)
      from roads.surface s left join roads.piece p on p.id = s.piece_id
      where not ST_IsValid(s.geom)""",
}


def review(conn, reviews, large):
    conn.execute("create temp table rb_review (kind text, piece_id int, junction_id int, osm_id bigint, "
                 "road_segment_id bigint, detail jsonb, geom geometry) on commit drop")
    ranked = sorted(X.MAJOR | X.COLLECTOR)
    for kind, sql in _REVIEW_SQL.items():
        conn.execute(f"""insert into rb_review (kind, piece_id, osm_id, road_segment_id, detail, geom)
                         select %(kind)s, q.* from ({sql}) q""", {"kind": kind, "ranked": ranked})
    with conn.cursor() as cur:
        with cur.copy("copy rb_review (kind, piece_id, detail) from stdin") as cp:
            for kind, pid, detail in reviews:
                cp.write_row((kind, pid, json.dumps(detail, default=str)))
        with cur.copy("copy rb_review (kind, junction_id, detail) from stdin") as cp:
            for jid, n, spread in large:
                cp.write_row(("junction_large", jid, json.dumps({"nodes": n, "spread_m": round(spread, 1)})))
    conn.execute(
        """update rb_review r set osm_id = p.osm_id, road_segment_id = coalesce(r.road_segment_id, p.road_segment_id),
             geom = coalesce(r.geom, ST_LineInterpolatePoint(p.geom, 0.5))
           from roads.piece p where p.id = r.piece_id""")
    conn.execute("update rb_review r set geom = j.geom from roads.junction j where j.id = r.junction_id "
                 "and r.geom is null")
    conn.execute(
        """insert into roads.review (id, kind, piece_id, junction_id, osm_id, road_segment_id, detail, geom)
           select row_number() over (order by kind, piece_id, junction_id), kind, piece_id, junction_id, osm_id,
                  road_segment_id, detail, geom
           from rb_review""")
    return dict(conn.execute("select kind, count(*) from roads.review group by 1 order by 1").fetchall())


# ---- the build -------------------------------------------------------------------------------------

def inputs(conn, md5, developed_build):
    """Every input's name, source, version, licence and republish, for roads.build and the export."""
    def last_fetch(source):
        row = conn.execute("select max(finished_at) from ops.fetch where source = %s and ok", (source,)).fetchone()
        return row[0].isoformat() if row and row[0] else None

    consumers = dict(conn.execute("select consumer, md5 from ops.osm_consumer").fetchall()) \
        if conn.execute("select to_regclass('ops.osm_consumer') is not null").fetchone()[0] else {}
    out = [{"name": "osm", "source": "roads/osm_valley", "licence": "ODbL-1.0", "republish": "yes",
            "credit": "© OpenStreetMap contributors", "version": md5,
            "note": "core.osm_way, roads.osm_street and roads.osm_paving from one extract: " +
                    ", ".join(f"{k} {v[:8]}" for k, v in sorted(consumers.items()))}]
    for name, source, credit in (
            ("achd_roads", "roads/achd_roads", "Ada County Highway District"),
            ("achd_msm", "roads/achd_msm", "Ada County Highway District"),
            ("achd_bike_network", "roads/achd_bike_network", "Ada County Highway District"),
            ("itd_hpms", "roads/itd_hpms", "Idaho Transportation Department")):
        out.append({"name": name, "source": source, "licence": "none-stated", "republish": "internal",
                    "credit": credit, "version": last_fetch(name)})
    out.append({"name": "compass_zones", "source": "development/compass_growth", "licence": "none-stated",
                "republish": "yes", "credit": "COMPASS and COMPASS member agencies",
                "version": last_fetch("compass_growth"), "note": "core.taz: which county a piece is in"})
    if developed_build:
        out.append({"name": "cdl", "source": "roads/cdl_developed", "licence": "public-domain", "republish": "yes",
                    "credit": developed_build["credit"],
                    "version": f"{developed_build['cdl_year']} {developed_build['cdl_sha256']}",
                    "note": f"roads.developed_build {developed_build['id']}"})
    return out


def clear(conn):
    for t in TABLES:
        conn.execute(f"delete from {t}")


def make(conn, md5, out=say, now=None):
    """The whole build on conn, without committing. Returns its stats."""
    if missing := ready(conn):
        raise BuildError(f"missing: {', '.join(missing)} (apply the migrations: python3 db/migrate.py)")
    t0 = time.monotonic()
    started = now or datetime.now(timezone.utc)
    stats = {}
    clear(conn)
    for name, fn in (("pieces", pieces), ("ACHD", match_achd), ("HPMS", match_hpms), ("sidewalks", sidewalks)):
        if name == "ACHD":
            stats["counties"] = counties(conn)
            _log(out, t0, f"counties: {stats['counties']}")
        got = fn(conn)
        stats.update(got)
        _log(out, t0, f"{name}: {json.dumps(got, default=str)}")
    dev_stats, dev_build = developed(conn)
    stats.update(dev_stats)
    _log(out, t0, f"developed land: {dev_stats['developed land']}")
    xs_stats, xsections, reviews = cross_sections(conn)
    stats.update(xs_stats)
    _log(out, t0, f"cross-sections: {json.dumps(xs_stats)}")
    j_stats, large = junctions(conn, xsections)
    stats.update(j_stats)
    _log(out, t0, f"junctions: {json.dumps(j_stats)}")
    stats["surfaces"] = surfaces(conn)
    _log(out, t0, f"surfaces: {stats['surfaces']}")
    stats.update(islands(conn))
    _log(out, t0, f"islands: faces {stats['faces']}, parts {stats['island parts']}")
    stats["junction surfaces"] = closings(conn)
    _log(out, t0, f"closings: {stats['junction surfaces']}")
    stats["edges"] = edges(conn)
    _log(out, t0, f"edges: {stats['edges']}")
    stats.update(crosswalks(conn))
    _log(out, t0, f"crosswalks: {stats['crosswalks']}")
    stats["markings"] = markings(conn, xsections)
    _log(out, t0, f"markings: {stats['markings']}")
    stats.update(generalise(conn))
    stats["review"] = review(conn, reviews, large)
    _log(out, t0, f"review: {stats['review']}")
    build_id = started.strftime("%Y%m%dT%H%M%SZ")
    seconds = round(time.monotonic() - t0, 1)
    params = {"xsection": X.DEFAULTS, "cluster_eps": CLUSTER_EPS,
              "corner_radius": {f"{a}/{b}": r for (a, b), r in CORNER_RADIUS.items()},
              "minor_radius": MINOR_RADIUS, "island_max_m2": ISLAND_MAX_M2, "thin_m": THIN_M,
              "crosswalk_depth_m": CROSSWALK_DEPTH_M, "crosswalk_clear_m": CROSSWALK_CLEAR_M,
              "junction_clear_m": JUNCTION_CLEAR_M, "z15_tolerance_m": Z15_TOLERANCE_M, "srid": SRID}
    conn.execute("update roads.build set current = false where current")
    conn.execute(
        """insert into roads.build (id, started_at, finished_at, current, extract_md5, inputs, params, counts, seconds,
                                    license, republish, credit)
           values (%s, %s, now(), true, %s, %s, %s, %s, %s, %s, 'internal', %s)""",
        (build_id, started, md5, json.dumps(inputs(conn, md5, dev_build)), json.dumps(params),
         json.dumps(stats, default=str), seconds, LICENSE, CREDIT))
    stats["build"] = build_id
    stats["seconds"] = seconds
    return stats


def run(conn, out=say, check=True):
    """roads-build as a build run: the partition checked, the build made, its marks cleared and roads-export
    marked in one commit."""
    with builds.Run(conn, BUILD, then=THEN) as r:
        md5 = osm_extract.check_partition(conn, OWNERS) if check else "unchecked"
        stats = make(conn, md5, out)
        r.note = (f"build {stats['build']}: {stats['pieces']:,} pieces, {stats['junctions']:,} junctions, "
                  f"{sum(stats['surfaces'].values()):,} surfaces, {stats['seconds']} s")
    return stats


def show_review(conn, kind="", out=say, limit=500):
    """The review list: counts by kind, or one kind's rows (way, ACHD segment, where, what disagreed)."""
    if not kind:
        for k, n in conn.execute("select kind, count(*) from roads.review group by 1 order by 1").fetchall():
            out(f"{k:28} {n:7,}")
        return
    rows = conn.execute(
        """select r.osm_id, r.road_segment_id, r.junction_id,
                  round(ST_X(ST_Transform(r.geom, 4326))::numeric, 6), round(ST_Y(ST_Transform(r.geom, 4326))::numeric, 6),
                  r.detail
           from roads.review r where r.kind = %s order by r.id limit %s""", (kind, limit)).fetchall()
    for osm_id, seg, jid, lon, lat, detail in rows:
        where = f"w{osm_id}" if osm_id else f"junction {jid}"
        out(f"{where:14} seg {seg or '-':>8}  {lat},{lon}  {json.dumps(detail, default=str)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog=COMMAND, description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="build in a transaction that's rolled back")
    ap.add_argument("--calibrate", action="store_true",
                    help="report the local streets' widths in the ten test windows and valley-wide (read only)")
    ap.add_argument("--review", nargs="?", const="", metavar="KIND",
                    help="list the current build's review list: counts by kind, or one kind's rows (read only)")
    args = ap.parse_args(argv)
    from ingest import db
    with db.connect() as conn:
        try:
            if args.calibrate:
                from . import calibrate
                calibrate.report(conn)
                return 0
            if args.review is not None:
                show_review(conn, args.review)
                return 0
            if args.dry_run:
                md5 = osm_extract.check_partition(conn, OWNERS)
                stats = make(conn, md5)
                conn.rollback()
            else:
                stats = run(conn)
        except (BuildError, RuntimeError) as err:
            print(f"roads-build: {err}", file=sys.stderr, flush=True)
            return 1
    print(json.dumps(stats, default=str, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
