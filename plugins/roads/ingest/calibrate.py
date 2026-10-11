"""The local streets' default widths, checked against measurements: `python3 -m ingest roads-build --calibrate`
(landscape sprint P7: "local streets default to 10.4 m curbed and 7.3 m rural ⚠️, calibrated in the test windows
first"). Read only; run it after a build.

Two measures, in the ten test windows (basemap/ground/spec.json's boxes) first, then valley-wide:

1. **ACHD's bike network** (roads.segment_bike_xsection): the curb-to-curb width ACHD measured (`total_pavement_m`)
   on local and collector streets, by the build's own reading of each piece's edges (curbed, rural or mixed), for
   the two-way pieces along two-way segments. The build takes those widths as they are; the defaults are for the
   streets ACHD hasn't measured, read the same way. Internal data: the numbers it prints are aggregates, for
   setting a default.
2. **Sidewalk spacing** (OpenStreetMap only, so a public variant can be calibrated too): on residential pieces with
   a parallel sidewalk mapped on both sides, the distance between the two sidewalks' centre lines less twice
   ATTACHED_OFFSET_M (a sidewalk's centre to the curb's face, for sidewalks along the curb ⚠️). Planter strips make
   this an upper bound.

The defaults live in xsection.DEFAULTS["local_pavement"]; the README records the numbers each calibration gave.
"""

import json
import os

from . import build as B

ATTACHED_OFFSET_M = 0.9        # a 1.5 m sidewalk along a 0.15 m curb: its centre is 0.9 m from the curb's face ⚠️
SPEC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "basemap", "ground", "spec.json")


def boxes():
    """The ten test windows: [(id, [west, south, east, north] in EPSG:32611)]."""
    with open(SPEC, encoding="utf-8") as f:
        return [(b["id"], b["utm"]) for b in json.load(f)["boxes"]]


_BOXES = """(select * from unnest(%(ids)s::text[], %(w)s::float8[], %(s)s::float8[], %(e)s::float8[],
                  %(n)s::float8[]) as t(id, w, s, e, n))"""

# Two-way pieces along two-way ACHD segments of a class, with ACHD's measured width, that the build didn't
# already take it from; by box (or the whole valley) and by how the build read their edges.
_ACHD = """
with d as (
  select {box} as box,
         case when x.edge_l = 'curb' and x.edge_r = 'curb' then 'curbed'
              when x.edge_l = 'shoulder' and x.edge_r = 'shoulder' then 'rural' else 'mixed' end as edges,
         p.road_segment_id, k.total_pavement_m as achd, x.total_w_m as ours
  from roads.piece p
  join roads.xsection x on x.piece_id = p.id
  join core.road_segment s on s.id = p.road_segment_id
  join roads.segment_bike_xsection k on k.road_segment_id = p.road_segment_id
  {join}
  where p.oneway = 0 and s.one_way = 'both' and s.functional_class = %(fclass)s and k.total_pavement_m is not null
    and not p.bridge and p.length_m >= 30
)
select box, edges, count(distinct road_segment_id),
       percentile_cont(array[0.1, 0.25, 0.5, 0.75, 0.9]) within group (order by achd)
from d group by 1, 2 order by 1, 2
"""

_SIDEWALK = """
select {box} as box, count(*) as pieces,
       percentile_cont(array[0.1, 0.25, 0.5, 0.75, 0.9]) within group (order by k.left_m + k.right_m - 2 * %(off)s)
from rb_walk k
join roads.piece p on p.id = k.piece_id
{join}
where p.highway = 'residential' and k.left_m is not null and k.right_m is not null and p.oneway = 0
group by 1 order by 1
"""

_IN_BOX = f"join {_BOXES} b on ST_Intersects(p.geom, ST_MakeEnvelope(b.w, b.s, b.e, b.n, 32611))"


def _q(values):
    return " / ".join(f"{v:.2f}" for v in values) if values else "-"


def measure(conn):
    """{'achd': {fclass: [(box, edges, segments, [p10, p25, p50, p75, p90], our median)]}, 'sidewalks': [...]}."""
    bx = boxes()
    params = {"ids": [b[0] for b in bx], "w": [b[1][0] for b in bx], "s": [b[1][1] for b in bx],
              "e": [b[1][2] for b in bx], "n": [b[1][3] for b in bx]}
    out = {"achd": {}}
    for fclass in ("Local", "Collector"):
        out["achd"][fclass] = [row for box, join in (("b.id", _IN_BOX), ("'valley'", ""))
                               for row in conn.execute(_ACHD.format(box=box, join=join),
                                                       {**params, "fclass": fclass}).fetchall()]
    B.run_sql(conn, B._SIDEWALKS, {"srid": B.SRID, "reach": B.SIDEWALK_REACH_M, "bearing": B.SIDEWALK_BEARING})
    conn.execute("update rb_walk set left_m = null where n_left < 2")
    conn.execute("update rb_walk set right_m = null where n_right < 2")
    out["sidewalks"] = [row for box, join in (("b.id", _IN_BOX), ("'valley'", ""))
                        for row in conn.execute(_SIDEWALK.format(box=box, join=join),
                                                {**params, "off": ATTACHED_OFFSET_M}).fetchall()]
    conn.rollback()
    return out


def report(conn, out=print):
    if conn.execute("select count(*) from roads.build where current").fetchone()[0] == 0:
        raise B.BuildError("no current roads build to calibrate against (roads-build first)")
    got = measure(conn)
    from .xsection import DEFAULTS
    out(f"The defaults now: {DEFAULTS['local_pavement']}")
    for fclass, rows in got["achd"].items():
        out(f"ACHD bike network, {fclass} streets: curb-to-curb (m) p10 / p25 / p50 / p75 / p90")
        for box, edges, segments, q in rows:
            out(f"  {box:9} {edges:7} {segments:5} segments  {_q(q)}")
    out(f"Sidewalk spacing on residential pieces, less 2 x {ATTACHED_OFFSET_M} m (m): p10 / p25 / p50 / p75 / p90")
    for box, n, q in got["sidewalks"]:
        out(f"  {box:9} {n:6} pieces  {_q(q)}")
    return got
