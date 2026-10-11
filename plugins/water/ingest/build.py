"""Build the water network: `python3 -m ingest water-build` (plan P4-data; the water design's build, decision 17).

One network for the map, rebuilt whole from what's loaded (nhd-load, hydroshare-load, osm-load's osm_waterways, the
IDWR sources), in one transaction, as a run of the build `water-build` (ingest/builds.py: it clears the marks the
loads left, and marks water-export). By hand, never inside `ingest serve`; a light job on the scratch database
(about a minute, under 1 GB).

    python3 -m ingest water-build [--dry-run]

Conflation, in PostGIS, in UTM 11N (EPSG:32611) metres:
1. NHD's flowlines are cut into equal pieces of 25 m or less. A piece is matched when its middle lies within 20 m of
   an OpenStreetMap waterway line (or inside 20 m of an OSM water area: a creek through a pond).
2. Every OSM waterway way (river, stream, canal, ditch, drain) is a reach, with OSM's geometry. It takes NHD's facts
   (GNIS name when OSM has none, perennial or intermittent when OSM doesn't say, Strahler order, reach code,
   visibility filter) from the NHD flowline that is 70% or more matched and covers half the way or more. A way half
   or more of whose length lies within 20 m of NHD is `confirmed`.
3. A run of unmatched NHD pieces 100 m or longer becomes an NHD-only reach (geometry_from 'nhd'), drawn lighter and
   a zoom later. Where it leaves or rejoins an OSM way it was matched to, its end is carried onto that way, so a
   lateral OSM lacks starts on the canal OSM draws. Artificial paths through lakes and rivers (the bodies draw those) and connectors are left out.
4. HydroShare's canal network names the reaches that OSM and NHD leave unnamed, where it runs along half of one
   within 20 m, and counts as evidence.
5. Kinds, flow, widths and first zooms come from rules.py. Named canal reaches that touch (within 50 m) form one
   canal (water.canal); a canal 20 km or longer is a main canal ⚠️.
6. Topology (water.reach_link): one reach's end at another's start, a reach starting on another (a lateral leaving
   its canal), a reach ending on another (a drain joining a canal), and NHDFlow between NHD-only runs. OSM draws
   waterways downstream; NHD's flowdir 1 says the same. Each canal's head is its most upstream reach (the one from
   which most of it is reached), and each reach gets its distance from it. Its source is the river, reservoir or
   canal it leaves, and its head structure the dam, weir or gate within 150 m.
7. Bodies: OSM's water areas, wetlands and pools; NHD's lakes, ponds, reservoirs, marshes, river and canal polygons
   where OSM water covers less than half of them (NHD-only). Structures: OSM's and NHD's dams, weirs, gates,
   waterfalls and springs (NHD's within 50 m of OSM's of the same kind dropped), and the NWPS gauges.
8. Gauges (water.gauge): each NWPS gauge in the box to the reach or body it measures, by the water named in the
   gauge's name within 1.5 km, else the nearest reach within 300 m.
9. INTERNAL side tables from IDWR, when loaded: the service areas each canal runs through (water.canal_org) and the
   legal season at its head (water.canal_season). Never exported.

Evidence for every reach is in water.reach_evidence: its geometry's source and every other that agrees.
"""

import argparse
import heapq
import json
import re
import sys
from collections import defaultdict

from . import rules

BUILD = "water-build"
THEN = ("water-export",)
PIECE_M = 25.0            # NHD and OSM lines are compared in pieces this long or shorter
MATCH_M = 20.0            # a piece within this of the other source's water is matched
NHD_SHARE = 0.7           # an NHD flowline this much matched passes its facts on (the design)
WAY_SHARE = 0.5           # ... to an OSM way it covers this much of
CONFIRMED_SHARE = 0.5     # an OSM way this much within MATCH_M of NHD is confirmed
NHD_RUN_M = 100.0         # an unmatched NHD run this long or longer is drawn
HS_SHARE = 0.5            # HydroShare names a reach it runs along this much of
CANAL_EPS_M = 500.0       # named canal reaches this close are one canal (across siphons and gaps)
OSM_SNAP_M = 0.5          # OSM ways meet at shared nodes
NHD_SNAP_M = 25.0         # NHD-only runs meet anything within a piece
HEAD_SOURCE_M = 50.0      # a canal's head this close to a river or reservoir leaves it
HEAD_STRUCTURE_M = 150.0  # a dam, weir or gate this close to a canal's head is its head structure
STRUCTURE_DEDUPE_M = 50.0
STRUCTURE_REACH_M = 30.0
GAUGE_NAME_M = 1500.0
GAUGE_NEAREST_M = 300.0
BOX = (-117.05, 43.00, -115.95, 43.85)
NHD_BASE = 2 ** 51        # NHD-only ids: 2^51 + a 48-bit hash
GAUGE_BASE = 2 ** 52
TEMP_BUFFERS = "160MB"

DRAWN_LINES = ("river", "stream", "canal", "ditch", "drain")
WATER_AREAS = ("lake", "reservoir", "pond", "river", "canal", "water", "basin", "wastewater", "dock")
BODY_KINDS = WATER_AREAS + ("wetland", "pool")
NHD_DRAWN = ("stream_river", "canal_ditch", "pipeline", "underground_conduit")


def h48(expr):
    """SQL for a stable 48-bit integer from a text expression."""
    return f"('x' || substr(md5({expr}), 1, 12))::bit(48)::bigint"


BOX_SQL = (f"ST_Transform(ST_Segmentize(ST_MakeEnvelope({BOX[0]}, {BOX[1]}, {BOX[2]}, {BOX[3]}, 4326), 0.01), "
           "32611)")

SETUP = [
    ("osm lines", f"""
create temp table box on commit drop as select {BOX_SQL} g;
create temp table o_line on commit drop as
select osm_id, kind, name, intermittent, piped, width_m, geom, ST_Transform(geom, 32611) g
from water.osm_feature
where active and shape = 'line' and osm_type = 'w' and kind in {DRAWN_LINES!r}
  and GeometryType(geom) = 'LINESTRING' and ST_NPoints(geom) >= 2;
create index on o_line using gist (g);
analyze o_line;
create temp table o_sub on commit drop as
select osm_id, ST_Subdivide(ST_Segmentize(g, 200), 8) g from o_line;
create index on o_sub using gist (g);
analyze o_sub"""),
    ("osm water areas", f"""
create temp table o_area on commit drop as
select osm_type, osm_id, kind,
       ST_Subdivide(ST_Transform(ST_CollectionExtract(ST_MakeValid(geom), 3), 32611), 64) g
from water.osm_feature
where active and shape = 'area' and kind in {WATER_AREAS!r};
create index on o_area using gist (g);
analyze o_area"""),
    ("nhd parts", f"""
create temp table n_part on commit drop as
select f.permanent_identifier pid, coalesce(d.path[1], 1) part, f.class, f.gnis_name, f.hydrographiccategory, f.streamorder,
       f.visibilityfilter, f.reachcode, f.flowdir, f.wbarea_permanent_identifier wbarea,
       coalesce(wb.ftype_name = 'Canal/Ditch', false) in_canal, d.geom g, 0::real len, 1 n
from water.nhd_flowline f
left join water.nhd_polygon wb on wb.permanent_identifier = f.wbarea_permanent_identifier,
     box, ST_Dump(ST_Intersection(ST_Transform(f.geom, 32611), box.g)) d
where GeometryType(d.geom) = 'LINESTRING' and ST_NPoints(d.geom) >= 2;
update n_part set len = ST_Length(g), n = greatest(1, ceil(ST_Length(g) / {PIECE_M}))::int;
create index on n_part using gist (g);
create index on n_part (pid, part);
analyze n_part;
create temp table n_sub on commit drop as
select pid, ST_Subdivide(ST_Segmentize(g, 200), 8) g from n_part;
create index on n_sub using gist (g);
analyze n_sub"""),
    ("nhd pieces matched to osm", f"""
create temp table n_match on commit drop as
with piece as (
  select p.pid, p.part, i, ST_LineInterpolatePoint(p.g, (i + 0.5) / p.n) mid
  from n_part p, generate_series(0, p.n - 1) i)
select pc.pid, pc.part, pc.i, m.osm_id, m.d,
       (m.osm_id is null and exists (select 1 from o_area a where ST_DWithin(pc.mid, a.g, {MATCH_M}))) in_area
from piece pc
left join lateral (select o.osm_id, ST_Distance(pc.mid, o.g) d from o_sub o
                   where ST_DWithin(pc.mid, o.g, {MATCH_M}) order by pc.mid <-> o.g limit 1) m on true;
create index on n_match (pid, part, i)"""),
    ("nhd shares", """
create temp table n_share on commit drop as
select p.pid, sum(p.len) len,
       sum(p.len * m.on_line / p.n) / nullif(sum(p.len), 0) line_share,
       sum(p.len * m.covered / p.n) / nullif(sum(p.len), 0) share
from n_part p
join (select pid, part, count(osm_id) on_line, count(*) filter (where osm_id is not null or in_area) covered
      from n_match group by 1, 2) m using (pid, part)
group by p.pid;
create index on n_share (pid)"""),
    ("nhd-only runs", f"""
create temp table n_run on commit drop as
with m as (
  select pid, part, i, i - row_number() over (partition by pid, part order by i) grp
  from n_match where osm_id is null and not in_area),
runs as (select pid, part, min(i) i0, max(i) i1, count(*) k from m group by pid, part, grp)
select {NHD_BASE} + {h48("r.pid || ':' || r.part || ':' || r.i0")} rid, r.pid, r.part, r.i0, r.i1, p.class,
       p.gnis_name, p.hydrographiccategory, p.streamorder, p.visibilityfilter, p.reachcode, p.flowdir,
       r.i0 = 0 at_start, r.i1 = p.n - 1 at_end,
       (select x.osm_id from n_match x where x.pid = r.pid and x.part = r.part and x.i = r.i0 - 1) prev_osm,
       (select x.osm_id from n_match x where x.pid = r.pid and x.part = r.part and x.i = r.i1 + 1) next_osm,
       ST_LineSubstring(p.g, r.i0::float8 / p.n, (r.i1 + 1)::float8 / p.n) g
from runs r join n_part p using (pid, part)
where r.k * p.len / p.n >= {NHD_RUN_M}
  and (p.class in {NHD_DRAWN!r} or (p.class = 'artificial_path' and p.in_canal));
update n_run r set g = ST_AddPoint(r.g, ST_ClosestPoint(o.g, ST_StartPoint(r.g)), 0)
from o_line o where o.osm_id = r.prev_osm and ST_DWithin(o.g, ST_StartPoint(r.g), {MATCH_M + PIECE_M});
update n_run r set g = ST_AddPoint(r.g, ST_ClosestPoint(o.g, ST_EndPoint(r.g)))
from o_line o where o.osm_id = r.next_osm and ST_DWithin(o.g, ST_EndPoint(r.g), {MATCH_M + PIECE_M})"""),
    ("osm pieces matched to nhd", f"""
create temp table o_match on commit drop as
with o as (select osm_id, g, greatest(1, ceil(ST_Length(g) / {PIECE_M}))::int n from o_line),
piece as (select o.osm_id, o.n, i, ST_LineInterpolatePoint(o.g, (i + 0.5) / o.n) mid from o, generate_series(0, o.n - 1) i)
select pc.osm_id, pc.n, pc.i, m.pid, m.d
from piece pc
left join lateral (select np.pid, ST_Distance(pc.mid, np.g) d from n_sub np
                   where ST_DWithin(pc.mid, np.g, {MATCH_M}) order by pc.mid <-> np.g limit 1) m on true"""),
    ("osm ways' nhd facts", f"""
create temp table o_attr on commit drop as
with s as (select osm_id, max(n) n, count(pid)::real / max(n) share,
                  percentile_cont(0.5) within group (order by d) filter (where pid is not null) d
           from o_match group by osm_id),
best as (select distinct on (m.osm_id) m.osm_id, m.pid, count(*)::real / max(m.n) way_share,
                percentile_cont(0.5) within group (order by m.d) d
         from o_match m join n_share ns on ns.pid = m.pid and ns.line_share >= {NHD_SHARE}
         join o_line o on o.osm_id = m.osm_id
         join (select distinct on (pid) pid, class, in_canal from n_part order by pid, part) np on np.pid = m.pid
         where m.pid is not null and case
           when np.class in ('canal_ditch', 'pipeline', 'underground_conduit') or np.in_canal
             then o.kind in ('canal', 'ditch', 'drain')
           when np.class in ('stream_river', 'artificial_path') then o.kind in ('river', 'stream', 'drain')
           else false end
         group by m.osm_id, m.pid
         having count(*)::real / max(m.n) >= {WAY_SHARE}
         order by m.osm_id, count(*) desc, m.pid)
select s.osm_id, s.share, s.d, b.pid, b.way_share, b.d best_d
from s left join best b using (osm_id)"""),
    ("reaches assembled", f"""
create temp table r on commit drop as
select o.osm_id id, 'osm'::text geometry_from, o.kind src_kind, o.name, case when o.name is not null then 'osm' end
         name_from, o.intermittent osm_intermittent, o.piped, o.width_m osm_width, f.class nhd_class,
       f.gnis_name nhd_name, f.hydrographiccategory nhd_category, f.streamorder, f.visibilityfilter,
       f.reachcode, a.pid nhd_pid, coalesce(a.share, 0) >= {CONFIRMED_SHARE} confirmed, a.share nhd_share,
       a.d nhd_d, true flow_known, o.osm_id, o.geom, o.g,
       null::int hs_id, null::text hs_name, null::text hs_type, null::text hs_call, null::real hs_share,
       null::real hs_d
from o_line o left join o_attr a using (osm_id) left join water.nhd_flowline f on f.permanent_identifier = a.pid
union all
select r.rid, 'nhd', null, r.gnis_name,
       case when r.gnis_name is not null then 'nhd' end, null, r.class in ('pipeline', 'underground_conduit'), null,
       r.class, r.gnis_name, r.hydrographiccategory, r.streamorder, r.visibilityfilter, r.reachcode, r.pid, false,
       null, null, r.flowdir = 1, null, ST_Transform(r.g, 4326), r.g, null, null, null, null, null, null
from n_run r
where GeometryType(r.g) = 'LINESTRING' and ST_Length(r.g) > 0;
alter table r add primary key (id);
alter table r add column kind text, add column flow text, add column intermittent boolean,
  add column name_key text, add column canal_id bigint, add column width_m real, add column width_from text,
  add column minzoom smallint, add column length_m real;
update r set length_m = ST_Length(g);
update r set name = nhd_name, name_from = 'nhd' where name is null and nhd_name is not null;
create index on r using gist (g);
analyze r"""),
    ("hydroshare matched", f"""
create temp table hs on commit drop as
select id, call_number, name, type, ST_Subdivide(ST_Segmentize(ST_Transform(geom, 32611), 200), 8) g
from water.hydroshare_canal;
create index on hs using gist (g);
analyze hs;
with x as (select id, g, greatest(1, ceil(length_m / {PIECE_M}))::int n from r),
piece as (select x.id, x.n, i, ST_LineInterpolatePoint(x.g, (i + 0.5) / x.n) mid from x, generate_series(0, x.n - 1) i),
m as (select pc.id, pc.n, h.hid, h.d from piece pc
      join lateral (select hs.id hid, ST_Distance(pc.mid, hs.g) d from hs where ST_DWithin(pc.mid, hs.g, {MATCH_M})
                    order by pc.mid <-> hs.g limit 1) h on true),
best as (select distinct on (id) id, hid, count(*)::real / max(n) share, percentile_cont(0.5) within group (order by d) d
         from m group by id, hid order by id, count(*) desc, hid)
update r set hs_id = b.hid, hs_name = hs.name, hs_type = hs.type, hs_call = hs.call_number, hs_share = b.share,
             hs_d = b.d
from best b join hs on hs.id = b.hid
where r.id = b.id and b.share >= {HS_SHARE};
update r set name = hs_name, name_from = 'hydroshare' where name is null and hs_name is not null"""),
]

CANALS = f"""
create temp table c_cluster on commit drop as
select id, name_key, ST_ClusterDBSCAN(g, eps := {CANAL_EPS_M}, minpoints := 1) over (partition by name_key) k
from r where name_key is not null and kind in {rules.CANAL_KINDS!r};
update r set canal_id = c.cid
from (select id, min(id) over (partition by name_key, k) cid from c_cluster) c where r.id = c.id;
select canal_id, kind, sum(length_m), count(*),
       mode() within group (order by name) filter (where name_from = 'osm'),
       mode() within group (order by name)
from r where canal_id is not null group by canal_id, kind"""

REACH_INSERT = """
insert into water.reach (id, kind, name, name_from, intermittent, flow, piped, width_m, width_from, stream_order, minzoom,
  geometry_from, confirmed, osm_id, nhd_pid, reachcode, canal_id, flow_known, length_m, geom, build_id)
select id, kind, name, name_from, intermittent, flow, piped, width_m, width_from,
       case when kind in ('river', 'stream') then streamorder end, minzoom, geometry_from,
       confirmed, osm_id, nhd_pid, reachcode, canal_id, flow_known, length_m, geom, %(build)s
from r"""

LINKS = [
    ("endpoints", f"""
create temp table re on commit drop as
select id, geometry_from = 'osm' osm, ST_StartPoint(g) s, ST_EndPoint(g) e, length_m from r;
create index on re using gist (s);
create index on re using gist (e);
analyze re"""),
    ("end", f"""
insert into water.reach_link (from_reach, to_reach, method, gap_m, at_m)
select a.id, b.id, 'end', ST_Distance(a.e, b.s), a.length_m
from re a join re b on a.id <> b.id and ST_DWithin(a.e, b.s, {NHD_SNAP_M})
where ST_Distance(a.e, b.s) <= case when a.osm and b.osm then {OSM_SNAP_M} else {NHD_SNAP_M} end
on conflict do nothing"""),
    ("nhdflow", """
insert into water.reach_link (from_reach, to_reach, method, at_m)
select ra.rid, rb.rid, 'nhdflow', a.length_m
from n_run ra join water.nhd_flow f on f.from_pid = ra.pid and ra.at_end
join n_run rb on rb.pid = f.to_pid and rb.at_start
join r a on a.id = ra.rid join r b on b.id = rb.rid
on conflict do nothing"""),
    ("branch", f"""
insert into water.reach_link (from_reach, to_reach, method, gap_m, at_m)
select a.id, b.id, 'branch', ST_Distance(b.s, a.g), ST_LineLocatePoint(a.g, b.s) * a.length_m
from re b join r a on a.id <> b.id and ST_DWithin(b.s, a.g, {NHD_SNAP_M})
join re ae on ae.id = a.id
where ST_Distance(b.s, a.g) <= case when ae.osm and b.osm then {OSM_SNAP_M} else {NHD_SNAP_M} end
  and not ST_DWithin(b.s, ae.e, {NHD_SNAP_M}) and not ST_DWithin(b.s, ae.s, {NHD_SNAP_M})
on conflict do nothing"""),
    ("joins", f"""
insert into water.reach_link (from_reach, to_reach, method, gap_m, at_m)
select a.id, b.id, 'joins', ST_Distance(a.e, b.g), a.length_m
from re a join r b on a.id <> b.id and ST_DWithin(a.e, b.g, {NHD_SNAP_M})
join re be on be.id = b.id
where ST_Distance(a.e, b.g) <= case when a.osm and be.osm then {OSM_SNAP_M} else {NHD_SNAP_M} end
  and not ST_DWithin(a.e, be.s, {NHD_SNAP_M}) and not ST_DWithin(a.e, be.e, {NHD_SNAP_M})
on conflict do nothing"""),
]

BODIES = f"""
create temp table b on commit drop as
select case when osm_type = 'r' then 2 * osm_id + 1 else 2 * osm_id end id, kind, name, coalesce(intermittent, false)
         intermittent, 'osm'::text geometry_from, osm_type, osm_id, null::text nhd_pid,
       ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) geom
from water.osm_feature
where active and shape = 'area' and kind in {BODY_KINDS!r} and osm_type in ('w', 'r');
delete from b where ST_IsEmpty(geom);
alter table b add column g geometry, add column area_m2 real, add column confirmed boolean default false,
  add column minzoom smallint, add column gauge_lid text;
update b set g = ST_Transform(geom, 32611);
update b set area_m2 = ST_Area(g);
create index on b using gist (g);
create temp table n_poly on commit drop as
select permanent_identifier pid, layer, ftype_name, gnis_name, hydrographiccategory, reservoirtype,
       ST_CollectionExtract(ST_Intersection(ST_Transform(ST_CollectionExtract(ST_MakeValid(geom), 3), 32611), box.g), 3) g
from water.nhd_polygon, box
where ftype_name in ('Lake/Pond', 'Reservoir', 'Swamp/Marsh', 'Playa', 'Stream/River', 'Canal/Ditch');
delete from n_poly where ST_IsEmpty(g);
create index on n_poly using gist (g);
create temp table b_sub on commit drop as select id, ST_Subdivide(g, 64) g from b;
create index on b_sub using gist (g);
create temp table n_cover on commit drop as
select n.pid, ST_Area(n.g) area,
       coalesce((select sum(ST_Area(ST_Intersection(n.g, bs.g))) from b_sub bs where ST_Intersects(bs.g, n.g)), 0)
         covered
from n_poly n;
update b set confirmed = true
where (select coalesce(ST_Area(ST_Intersection(b.g, ST_Union(n.g))), 0) from n_poly n where ST_Intersects(n.g, b.g))
      >= 0.5 * b.area_m2;
insert into b (id, kind, name, intermittent, geometry_from, nhd_pid, geom, g, area_m2)
select {NHD_BASE} + {h48("'body:' || n.pid")},
       case n.ftype_name
         when 'Swamp/Marsh' then 'wetland' when 'Stream/River' then 'river' when 'Canal/Ditch' then 'canal'
         when 'Reservoir' then case when n.reservoirtype ~* 'treatment|sewage|disposal|evapor' then 'wastewater'
                                    else 'reservoir' end
         else case when n.gnis_name ~* '\\mlake\\M' or ST_Area(n.g) >= 400000 then 'lake' else 'pond' end end,
       n.gnis_name, coalesce(n.hydrographiccategory = 'Intermittent', false) or n.ftype_name = 'Playa', 'nhd', n.pid,
       ST_Multi(ST_Transform(n.g, 4326)), n.g, ST_Area(n.g)
from n_poly n join n_cover c using (pid)
where c.covered < 0.5 * c.area and not ST_IsEmpty(n.g)"""

STRUCTURES = f"""
create temp table s on commit drop as
select 4 * osm_id + case osm_type when 'n' then 0 when 'w' then 1 else 2 end id, kind, name, 'osm_waterways'::text source,
       osm_type || osm_id source_id, null::text gauge_lid,
       case when shape = 'point' then geom else ST_PointOnSurface(ST_MakeValid(geom)) end geom
from (select distinct on (osm_type, osm_id) * from water.osm_feature
      where active and kind in ('dam', 'weir', 'lock_gate', 'sluice_gate', 'waterfall', 'spring')
        and (shape = 'point' or GeometryType(geom) in ('LINESTRING', 'POLYGON', 'MULTIPOLYGON'))
      order by osm_type, osm_id, case shape when 'point' then 0 when 'area' then 1 else 2 end) o;
insert into s
select {NHD_BASE} + {h48("'structure:' || n.permanent_identifier")}, n.kind, n.gnis_name, 'nhd_hr',
       n.permanent_identifier, null, n.geom
from (select permanent_identifier, gnis_name,
             case ftype_name when 'Spring/Seep' then 'spring' when 'Waterfall' then 'waterfall' end kind, geom
      from water.nhd_point where layer = 'point' and ftype_name in ('Spring/Seep', 'Waterfall')
      union all
      select permanent_identifier, gnis_name, case when gnis_name ~* '\\mweir\\M' then 'weir' else 'dam' end,
             ST_PointOnSurface(geom)
      from water.nhd_line where ftype_name = 'Dam/Weir') n
where not exists (select 1 from s o where o.source = 'osm_waterways' and o.kind = n.kind
                  and ST_DWithin(ST_Transform(o.geom, 32611), ST_Transform(n.geom, 32611), {STRUCTURE_DEDUPE_M}));
insert into s
select {GAUGE_BASE} + {h48("g.lid")}, 'gauge', g.name, 'nwps_gauges', g.lid, g.lid, g.geom
from gauges g;
alter table s add column reach_id bigint, add column minzoom smallint, add column on_river boolean default false,
  add column p geometry;
update s set p = ST_Transform(geom, 32611);
create temp table b_big on commit drop as
select id, ST_Subdivide(g, 64) g from b where kind in ('river', 'reservoir', 'lake');
create index on b_big using gist (g);
update s set reach_id = (select r.id from r where ST_DWithin(r.g, s.p, {STRUCTURE_REACH_M})
                         order by r.g <-> s.p limit 1);
update s set on_river = exists (select 1 from r where r.kind = 'river' and ST_DWithin(r.g, s.p, 100))
                        or exists (select 1 from b_big where ST_DWithin(b_big.g, s.p, 100))"""

GAUGES = f"""
create temp table gauges on commit drop as
select distinct on (source_id) source_id lid, payload->>'name' name, geom
from raw.record
where source = 'nwps_gauges' and source_id !~ '[@/]' and removed_at is null and geom is not null
  and ST_Intersects(geom, ST_MakeEnvelope({BOX[0]}, {BOX[1]}, {BOX[2]}, {BOX[3]}, 4326))
order by source_id, last_seen desc"""

EVIDENCE = """
insert into water.reach_evidence (reach_id, source, source_id, role, share, distance_m)
select id, 'osm_waterways', 'w' || osm_id, 'geometry', 1, 0 from r where geometry_from = 'osm'
union all
select id, 'nhd_hr', nhd_pid, 'geometry', 1, 0 from r where geometry_from = 'nhd'
union all
select id, 'nhd_hr', nhd_pid, 'attributes', nhd_share, nhd_d from r where geometry_from = 'osm' and nhd_pid is not null
union all
select id, 'hydroshare_canals', coalesce(hs_call, 'record ' || hs_id), case when name_from = 'hydroshare' then 'name'
       else 'agrees' end, hs_share, hs_d
from r where hs_id is not null
on conflict do nothing;
insert into water.reach_evidence (reach_id, source, source_id, role, share, distance_m)
select m.osm_id, 'nhd_hr', m.pid, 'agrees', count(*)::real / max(m.n), percentile_cont(0.5) within group (order by m.d)
from o_match m join r on r.id = m.osm_id
where m.pid is not null and m.pid is distinct from r.nhd_pid
group by m.osm_id, m.pid
having count(*)::real / max(m.n) >= 0.2
on conflict do nothing"""

IDWR = """
insert into water.canal_org (canal_id, objectid, name, share, at_head, build_id)
select c.id, o.objectid, o.name, least(1, sum(ST_Length(ST_Intersection(rr.geom, o.geom)::geography)) / c.length_m),
       bool_or(rr.id = c.head_reach_id and ST_Intersects(ST_StartPoint(rr.geom), o.geom)), %(build)s
from water.canal c join water.reach rr on rr.canal_id = c.id
join water.idwr_org o on ST_Intersects(rr.geom, o.geom)
group by c.id, o.objectid, o.name, c.length_m
having sum(ST_Length(ST_Intersection(rr.geom, o.geom)::geography)) / c.length_m >= 0.1
    or bool_or(rr.id = c.head_reach_id and ST_Intersects(ST_StartPoint(rr.geom), o.geom));
insert into water.canal_season (canal_id, objectid, season, start_month, start_day, end_month, end_day, build_id)
select distinct on (c.id) c.id, s.objectid, s.season, s.start_month, s.start_day, s.end_month, s.end_day, %(build)s
from water.canal c join water.reach rr on rr.id = c.head_reach_id
join water.idwr_season s on ST_Intersects(ST_StartPoint(rr.geom), s.geom)
order by c.id, s.objectid"""

DRAWN_TABLES = ("water.canal_season", "water.canal_org", "water.gauge", "water.reach_evidence", "water.reach_link",
                "water.structure", "water.body", "water.canal", "water.reach")


# ---- rules applied in Python ------------------------------------------------------------------------------------

def reach_rules(row, main_canals):
    """kind, flow, intermittent, name_key, width, width_from, minzoom for one reach row (a dict)."""
    if row["geometry_from"] == "osm":
        kind = rules.osm_kind(row["src_kind"], row["name"], row["hs_type"])
    else:
        kind = rules.nhd_kind(row["nhd_class"], row["name"], row["streamorder"])
        hs = rules.HYDROSHARE_KIND.get(row["hs_type"])
        if hs and kind in rules.CANAL_KINDS and hs in rules.CANAL_KINDS and not row["name"]:
            kind = hs
    fl = rules.flow(row["osm_intermittent"], row["nhd_category"] if kind in ("river", "stream") else None)
    intermittent = fl in ("intermittent", "ephemeral")
    main = row.get("canal_id") in main_canals and kind == "canal"
    named = bool(row["name"])
    order = row["streamorder"] if kind in ("river", "stream") else None
    w, how = rules.width(kind, intermittent=intermittent, order=order, osm_width=row["osm_width"], named=named,
                         main=main)
    z = rules.reach_minzoom(kind, intermittent=intermittent, order=order, visibility=row["visibilityfilter"],
                            named=named, main=main, nhd_only=row["geometry_from"] == "nhd", piped=row["piped"],
                            has_nhd=row["nhd_class"] is not None)
    return {"kind": kind, "flow": fl, "intermittent": intermittent, "name_key": rules.name_key(row["name"]),
            "width_m": w, "width_from": how, "minzoom": z}


def canal_kinds(rows):
    """{canal_id: (kind, name)} from CANALS' summary rows: (canal_id, reach kind, length, reaches, osm name, name)."""
    by = defaultdict(lambda: {"len": defaultdict(float), "osm": None, "name": None, "total": 0.0})
    for cid, kind, length, _, osm_name, name in rows:
        c = by[cid]
        c["len"][kind] += length
        c["total"] += length
        c["osm"] = c["osm"] or osm_name
        c["name"] = c["name"] or name
    out = {}
    for cid, c in by.items():
        kind = max(sorted(c["len"]), key=lambda k: c["len"][k])
        if kind == "canal" and c["total"] >= rules.MAIN_CANAL_M:
            kind = "main_canal"
        out[cid] = (kind, c["osm"] or c["name"], c["total"])
    return out


def heads_and_distances(members, edges, lengths):
    """For one canal: (head reach id, {reach id: metres from the head}). members: its reach ids; edges: [(from, to,
    at_m)] among them; lengths: {id: m}. The head is the upstream-most reach (no link into it from the canal) from
    which most of the canal's length is reached; ties go to the lowest id. A canal whose every reach has a link in
    (a loop) starts at its lowest id."""
    out_edges = defaultdict(list)
    has_in = set()
    for a, b, at in edges:
        out_edges[a].append((b, at if at is not None else lengths.get(a, 0.0)))
        has_in.add(b)
    heads = sorted(m for m in members if m not in has_in) or [min(members)]

    def walk(start):
        dist = {start: 0.0}
        todo = [(0.0, start)]
        while todo:
            d, a = heapq.heappop(todo)
            if d > dist.get(a, float("inf")):
                continue
            for b, at in out_edges[a]:
                nd = d + max(at, 0.0)
                if nd < dist.get(b, float("inf")):
                    dist[b] = nd
                    heapq.heappush(todo, (nd, b))
        return dist

    best, best_dist, best_len = None, {}, -1.0
    for h in heads:
        dist = walk(h)
        reached = sum(lengths.get(x, 0.0) for x in dist)
        if reached > best_len:
            best, best_dist, best_len = h, dist, reached
    return best, best_dist


_GAUGE_SPLIT = re.compile(r"\s+(?:at|near|below|above|abv|blw)\s+", re.IGNORECASE)


def gauge_names(name):
    """The water a gauge's name says it measures: [(name key, 'body' or 'reach' first)], most specific first.
    'New York Canal Diversion at Boise' -> [('new york canal', 'reach')]; 'Southwest Idaho Reservoirs at Lake Lowell'
    -> [('lake lowell', 'body')]; 'Boise River above Lucky Peak Dam' -> [('lucky peak', 'body'), ('boise river',
    'reach')]."""
    if not name:
        return []
    out = []
    m = re.search(r"reservoirs? at (.+)$", name, re.IGNORECASE)
    if m:
        out.append((m.group(1), "body"))
    m = re.search(r"\babove (.+?) dam\b", name, re.IGNORECASE)
    if m:
        out.append((m.group(1), "body"))
    head = _GAUGE_SPLIT.split(name, maxsplit=1)[0]
    head = re.sub(r"\s+diversion$", "", head, flags=re.IGNORECASE)
    if not re.match(r"southwest idaho reservoirs?$", head, re.IGNORECASE):
        out.append((head, "reach"))
    keys, seen = [], set()
    for n, prefer in out:
        k = rules.name_key(n)
        if k and k not in seen:
            seen.add(k)
            keys.append((k, prefer))
    return keys


GAUGE_SQL = f"""
select kind, id, d from (
  select 'body' kind, b.id, ST_Distance(b.g, p.pt) d, trim(regexp_replace(lower(b.name), '[^a-z0-9]+', ' ', 'g')) k,
         b.kind in ('river', 'lake', 'reservoir') natural_kind
  from b, (select ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 32611) pt) p
  where b.name is not null and ST_DWithin(b.g, p.pt, {GAUGE_NAME_M})
  union all
  select 'reach', r.id, ST_Distance(r.g, p.pt), r.name_key, r.kind in ('river', 'stream')
  from r, (select ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 32611) pt) p
  where r.name_key is not null and ST_DWithin(r.g, p.pt, {GAUGE_NAME_M})) x
where k = %(key)s or k like %(key)s || ' %%' or k like '%% ' || %(key)s or k like '%% ' || %(key)s || ' %%'
order by (kind = %(prefer)s) desc, (natural_kind = %(natural)s) desc, d limit 1"""
GAUGE_NEAREST_SQL = f"""
select r.id, ST_Distance(r.g, p.pt) d from r, (select ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 32611) pt) p
where ST_DWithin(r.g, p.pt, {GAUGE_NEAREST_M}) order by r.g <-> p.pt limit 1"""


def link_gauge(conn, name, x, y):
    """(reach id, body id, method, metres) for a gauge at (x, y) in UTM 11N: the reach or body its name says,
    within 1.5 km, else the nearest reach within 300 m, else nothing."""
    for key, prefer in gauge_names(name):
        natural = bool(re.search(r"\b(river|creek|lake|reservoir)\b", key))      # not a canal: prefer natural water
        hit = conn.execute(GAUGE_SQL, {"x": x, "y": y, "key": key, "prefer": prefer, "natural": natural}).fetchone()
        if hit:
            return (hit[1], None, "name", hit[2]) if hit[0] == "reach" else (None, hit[1], "name", hit[2])
    hit = conn.execute(GAUGE_NEAREST_SQL, {"x": x, "y": y}).fetchone()
    if hit:
        return hit[0], None, "nearest", hit[1]
    return None, None, "none", None


# ---- the build ---------------------------------------------------------------------------------------------------

def _fetch_dicts(conn, sql, params=None):
    cur = conn.execute(sql, params or {})
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _set(conn, table, key, columns, rows):
    """Update a temp table from rows [(key, values...)], through a staging table and COPY."""
    stage = f"set_{table}"
    conn.execute(f"drop table if exists pg_temp.{stage}")
    conn.execute(f"create temp table {stage} ({key} bigint primary key, "
                 + ", ".join(f"{c} {t}" for c, t in columns) + ") on commit drop")
    with conn.cursor() as cur:
        with cur.copy(f"copy {stage} ({key}, {', '.join(c for c, _ in columns)}) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
    conn.execute(f"update {table} t set " + ", ".join(f"{c} = s.{c}" for c, _ in columns)
                 + f" from {stage} s where t.{key} = s.{key}")


def inputs(conn):
    """What this build reads: each load's sha256 and the OSM extract's MD5."""
    loads = {s: {"load": i, "sha256": h, "file": f, "loaded_at": str(t)} for s, i, h, f, t in conn.execute(
        """select distinct on (source) source, id, sha256, file, loaded_at from water.load
           order by source, id desc""").fetchall()}
    osm = conn.execute("""select md5, extract_file, data_as_of, loaded_at from ops.osm_consumer
                          where consumer = 'water.osm_waterways'""").fetchone() \
        if conn.execute("select to_regclass('ops.osm_consumer') is not null").fetchone()[0] else None
    idwr = {s: str(t) for s, t in conn.execute(
        """select source, max(finished_at) from ops.fetch where ok and source like 'idwr_%%' group by source""")}
    return {**loads, "osm_waterways": ({"md5": osm[0], "extract": osm[1], "data_as_of": str(osm[2]),
                                       "loaded_at": str(osm[3])} if osm else None), "idwr": idwr}


def build(conn, out=None):
    """Rebuild the drawn tables in the caller's transaction (no commit). Returns the build id and its counts."""
    import time
    out = out or (lambda msg: print(msg, flush=True))
    # The build's temporary tables hold tens of MB of geometry: keep them in memory rather than re-reading them
    # from disk in every join. Settable only before the session's first temporary table; otherwise left as it is.
    try:
        with conn.transaction():
            conn.execute(f"set temp_buffers = '{TEMP_BUFFERS}'")
    except Exception:
        pass
    have = conn.execute("select (select count(*) from water.nhd_flowline), "
                        "(select count(*) from water.osm_feature where active)").fetchone()
    if not have[0] and not have[1]:
        raise RuntimeError("nothing to build: load NHD (nhd-load) or OpenStreetMap's water (osm-load) first")
    build_id = conn.execute("insert into water.build (inputs, settings) values (%s::jsonb, %s::jsonb) returning id",
                            (json.dumps(inputs(conn), default=str), json.dumps({
                                **rules.settings(), "piece_m": PIECE_M, "match_m": MATCH_M, "nhd_share": NHD_SHARE,
                                "way_share": WAY_SHARE, "confirmed_share": CONFIRMED_SHARE, "nhd_run_m": NHD_RUN_M,
                                "hydroshare_share": HS_SHARE, "canal_eps_m": CANAL_EPS_M}))).fetchone()[0]
    conn.execute("set local work_mem = '64MB'")
    for t in DRAWN_TABLES:
        conn.execute(f"delete from {t}")

    def step(label, sql, params=None):
        t0 = time.monotonic()
        for stmt in [s for s in sql.split(";\n") if s.strip()]:
            if params:
                conn.execute(stmt, params)
            else:
                conn.execute(stmt)
        out(f"water-build: {label} ({time.monotonic() - t0:.1f} s)")

    for label, sql in SETUP:
        step(label, sql)

    # Kinds, flow and names first (the canals group by name), then the canals, then widths and zooms.
    rows = _fetch_dicts(conn, """select id, geometry_from, src_kind, name, osm_intermittent, piped, osm_width, nhd_class,
                                        nhd_category, streamorder, visibilityfilter, hs_type from r""")
    first = {r["id"]: reach_rules(r, set()) for r in rows}
    _set(conn, "r", "id", [("kind", "text"), ("flow", "text"), ("intermittent", "boolean"), ("name_key", "text")],
         [(i, v["kind"], v["flow"], v["intermittent"], v["name_key"]) for i, v in first.items()])
    t0 = time.monotonic()
    *setup, summary = [s for s in CANALS.split(";\n") if s.strip()]
    for stmt in setup:
        conn.execute(stmt)
    canals = canal_kinds(conn.execute(summary).fetchall())
    out(f"water-build: canals ({time.monotonic() - t0:.1f} s)")
    main = {cid for cid, (kind, _, _) in canals.items() if kind == "main_canal"}
    rows = _fetch_dicts(conn, """select id, geometry_from, src_kind, name, osm_intermittent, piped, osm_width, nhd_class,
                                        nhd_category, streamorder, visibilityfilter, hs_type, canal_id from r""")
    final = {r["id"]: reach_rules(r, main) for r in rows}
    _set(conn, "r", "id", [("kind", "text"), ("width_m", "real"), ("width_from", "text"), ("minzoom", "smallint")],
         [(i, v["kind"], v["width_m"], v["width_from"], v["minzoom"]) for i, v in final.items()])
    step("reaches stored", REACH_INSERT, {"build": build_id})
    conn.execute("analyze r")
    conn.execute("analyze water.reach")

    for label, sql in LINKS:
        step(f"links: {label}", sql)

    # Each canal: its row, its head, each reach's distance from the head.
    t0 = time.monotonic()
    members = defaultdict(list)
    lengths = {}
    for rid, cid, length in conn.execute("select id, canal_id, length_m from r where canal_id is not null"):
        members[cid].append(rid)
        lengths[rid] = length
    edges = defaultdict(list)
    for a, b, at, ca in conn.execute(
            """select l.from_reach, l.to_reach, l.at_m, a.canal_id from water.reach_link l
               join r a on a.id = l.from_reach join r b on b.id = l.to_reach
               where a.canal_id is not null and a.canal_id = b.canal_id and l.method <> 'joins'"""):
        edges[ca].append((a, b, at))
    canal_rows, dist_rows = [], []
    for cid, ids in members.items():
        head, dist = heads_and_distances(ids, edges[cid], lengths)
        kind, name, total = canals[cid]
        canal_rows.append((cid, name, kind, total, len(ids), head))
        dist_rows += [(rid, d) for rid, d in dist.items()]
    with conn.cursor() as cur:
        with cur.copy("copy water.canal (id, name, kind, length_m, reaches, head_reach_id, sources, build_id) "
                      "from stdin") as cp:
            for cid, name, kind, total, n, head in canal_rows:
                cp.write_row((cid, name, kind, total, n, head, "{}", build_id))
    conn.execute("create temp table c_dist (id bigint primary key, d real) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy c_dist (id, d) from stdin") as cp:
            for r in dist_rows:
                cp.write_row(r)
    conn.execute("update water.reach w set dist_from_head_m = c.d from c_dist c where w.id = c.id")
    conn.execute("""update water.canal c set piped_m = coalesce(x.piped, 0), sources = x.sources
                    from (select r.canal_id, sum(r.length_m) filter (where r.piped) piped,
                                 array_remove(array[case when bool_or(r.geometry_from = 'osm') then 'osm_waterways' end,
                                   case when bool_or(r.nhd_pid is not null) then 'nhd_hr' end,
                                   case when bool_or(r.hs_id is not null) then 'hydroshare_canals' end], null) sources
                          from r where r.canal_id is not null group by r.canal_id) x
                    where x.canal_id = c.id""")
    conn.execute("analyze water.reach_link")
    conn.execute("analyze water.canal")
    out(f"water-build: canal heads ({time.monotonic() - t0:.1f} s)")

    step("gauges read", GAUGES)
    step("bodies", BODIES)
    conn.execute("analyze b")
    bodies = conn.execute("select id, kind, area_m2 from b").fetchall()
    _set(conn, "b", "id", [("minzoom", "smallint")], [(i, rules.body_minzoom(k, a)) for i, k, a in bodies])
    step("structures", STRUCTURES)
    conn.execute("analyze s")
    srows = conn.execute("select id, kind, name, on_river from s").fetchall()
    _set(conn, "s", "id", [("minzoom", "smallint")],
         [(i, rules.structure_minzoom(k, named=bool(n), on_river=bool(o))) for i, k, n, o in srows])

    # Gauges: by the water their names say, else the nearest reach.
    t0 = time.monotonic()
    gauge_rows = []
    for lid, name, x, y in conn.execute(
            "select lid, name, ST_X(p), ST_Y(p) from (select lid, name, ST_Transform(geom, 32611) p from gauges) g "
            "order by lid").fetchall():
        gauge_rows.append((lid, name, *link_gauge(conn, name, x, y)))
    conn.execute("create temp table g_link (lid text primary key, name text, reach_id bigint, body_id bigint, "
                 "method text, distance_m real) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy g_link (lid, name, reach_id, body_id, method, distance_m) from stdin") as cp:
            for r in gauge_rows:
                cp.write_row(r)
    conn.execute("""insert into water.gauge (lid, name, reach_id, body_id, canal_id, method, distance_m, geom, build_id)
                    select l.lid, coalesce(l.name, l.lid), l.reach_id, l.body_id, r.canal_id, l.method, l.distance_m,
                           g.geom, %s
                    from g_link l join gauges g using (lid) left join r on r.id = l.reach_id""", (build_id,))
    conn.execute("update b set gauge_lid = l.lid from g_link l where l.body_id = b.id")
    conn.execute("update water.canal c set gauge_lid = g.lid from water.gauge g where g.canal_id = c.id")
    out(f"water-build: gauges ({time.monotonic() - t0:.1f} s)")

    step("bodies stored", """
insert into water.body (id, kind, name, intermittent, area_m2, minzoom, geometry_from, confirmed, osm_type, osm_id,
  nhd_pid, gauge_lid, geom, build_id)
select id, kind, name, intermittent, area_m2, minzoom, geometry_from, confirmed, osm_type, osm_id, nhd_pid, gauge_lid,
       geom, %(build)s
from b""", {"build": build_id})
    step("structures stored", """
insert into water.structure (id, kind, name, source, source_id, reach_id, gauge_lid, minzoom, geom, build_id)
select id, kind, name, source, source_id, reach_id, gauge_lid, minzoom, geom, %(build)s from s""", {"build": build_id})

    # Each canal's source and head structure.
    step("canal sources", f"""
update water.canal c set source_kind = x.kind, source_reach_id = x.reach_id, source_canal_id = x.canal_id
from (select distinct on (c.id) c.id, case when a.kind = 'river' or a.kind = 'stream' then 'river' else 'canal' end kind,
             a.id reach_id, a.canal_id
      from water.canal c join water.reach_link l on l.to_reach = c.head_reach_id
      join r a on a.id = l.from_reach and a.canal_id is distinct from c.id
      order by c.id, (a.kind = 'river') desc, l.gap_m nulls last) x
where x.id = c.id;
update water.canal c set source_kind = x.kind, source_reach_id = x.reach_id
from (select distinct on (c.id) c.id, x.kind, x.reach_id
      from water.canal c join r h on h.id = c.head_reach_id
      join lateral (select 'river' kind, r2.id reach_id, ST_Distance(r2.g, ST_StartPoint(h.g)) d from r r2
                    where r2.kind = 'river' and ST_DWithin(r2.g, ST_StartPoint(h.g), {HEAD_SOURCE_M})
                    union all
                    select case when b.kind = 'river' then 'river' else 'reservoir' end, null,
                           ST_Distance(bb.g, ST_StartPoint(h.g)) from b_big bb join b on b.id = bb.id
                    where ST_DWithin(bb.g, ST_StartPoint(h.g), {HEAD_SOURCE_M})
                    order by d limit 1) x on true
      where c.source_kind = 'unknown') x
where x.id = c.id;
update water.canal c set head_structure_id = (
  select s.id from s join r h on h.id = c.head_reach_id
  where s.kind in ('dam', 'weir', 'sluice_gate', 'lock_gate') and ST_DWithin(s.p, ST_StartPoint(h.g), {HEAD_STRUCTURE_M})
  order by s.p <-> ST_StartPoint(h.g) limit 1)""")
    step("evidence", EVIDENCE)

    idwr = conn.execute("select (select count(*) from water.idwr_org), (select count(*) from water.idwr_season)"
                        ).fetchone()
    if idwr[0] or idwr[1]:
        step("IDWR side tables (internal)", IDWR, {"build": build_id})

    counts = dict(zip(
        ("reaches", "reaches_osm", "reaches_nhd_only", "reaches_confirmed", "reaches_named", "named_by_hydroshare",
         "km_osm", "km_nhd_only", "km_nhd_only_canals", "links", "canals", "main_canals", "canals_with_head_source",
         "bodies", "bodies_nhd_only", "structures", "gauges", "gauges_linked", "canal_org_rows", "canal_season_rows"),
        conn.execute("""select (select count(*) from water.reach),
                           (select count(*) from water.reach where geometry_from = 'osm'),
                           (select count(*) from water.reach where geometry_from = 'nhd'),
                           (select count(*) from water.reach where confirmed),
                           (select count(*) from water.reach where name is not null),
                           (select count(*) from water.reach where name_from = 'hydroshare'),
                           (select round(sum(length_m) / 1000) from water.reach where geometry_from = 'osm'),
                           (select round(sum(length_m) / 1000) from water.reach where geometry_from = 'nhd'),
                           (select round(sum(length_m) / 1000) from water.reach
                            where geometry_from = 'nhd' and kind in ('canal', 'lateral', 'ditch', 'drain')),
                           (select count(*) from water.reach_link),
                           (select count(*) from water.canal),
                           (select count(*) from water.canal where kind = 'main_canal'),
                           (select count(*) from water.canal where source_kind <> 'unknown'),
                           (select count(*) from water.body),
                           (select count(*) from water.body where geometry_from = 'nhd'),
                           (select count(*) from water.structure),
                           (select count(*) from water.gauge),
                           (select count(*) from water.gauge where method <> 'none'),
                           (select count(*) from water.canal_org),
                           (select count(*) from water.canal_season)""").fetchone()))
    counts = {k: (float(v) if hasattr(v, "is_integer") and not isinstance(v, int) else v) for k, v in counts.items()}
    conn.execute("update water.build set finished_at = clock_timestamp(), counts = %s::jsonb where id = %s",
                 (json.dumps(counts, default=float), build_id))
    return build_id, counts


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest water-build", description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="build, report, and roll back")
    args = ap.parse_args(argv)
    from ingest import builds, db
    with db.connect() as conn:
        if args.dry_run:
            build_id, counts = build(conn)
            conn.rollback()
            print(f"water-build: dry run, rolled back: {json.dumps(counts, default=float)}")
            return 0
        with builds.Run(conn, BUILD, then=THEN) as run:
            build_id, counts = build(conn)
            run.note = (f"build {build_id}: {counts['reaches']} reaches ({counts['reaches_nhd_only']} NHD-only), "
                        f"{counts['bodies']} bodies, {counts['canals']} canals")
    print(f"water-build: build {build_id}: {json.dumps(counts, default=float)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
