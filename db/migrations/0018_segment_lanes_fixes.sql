-- 0018: the lanes views of 0017, corrected after review (Oct 7, 2026).
--
-- - HPMS: facility type no longer overrides the A/D reading. ITD codes a
--   divided highway's inventory direction as a two-way roadway (I-84's A route
--   carries 2 to 6 lanes one way and 0 the other on "two_way" for 281 miles), so
--   the override read every divided state route as undivided and halved it.
--   Only a one-way facility (one-way roadway, ramp) means there's no other
--   direction. An A row with lanes one way and no D row along leaves the other
--   direction unknown. Facility and turn-lane rows must be the chosen A route's.
-- - HPMS on one-way ACHD segments (a carriageway drawn on its own, a one-way
--   street): only the carriageway running the way of travel counts, the other
--   direction is 0, and a D route alone (no A row along) counts too. A total of
--   0 reads as unknown. Where routes share a stretch, the interstate, then the US,
--   then the state route wins a tie (US-26's 1-lane D placeholder on I-84 won
--   westbound I-84 by row order before).
-- - Master Street Map, COMPASS, OpenStreetMap: the odd-count centre-lane reading
--   applies from 3 lanes; 1 lane on a two-way road is 1 lane (a one-lane road or
--   a data error), flagged single_lane, at half confidence.
-- - Master Street Map on a one-way segment that is one carriageway of a divided
--   road (its line has one-way segments running both ways along it): each
--   carriageway gets half the cross-section, n / 2, without the centre lane
--   (lead, Oct 7); a one-way street still gets all n.
-- - core.segment_lanes gains flags (single_lane, carriageway_split, ad_conflict).

drop view core.segment_lanes;
drop view core.segment_lanes_hpms;
drop view core.segment_lanes_msm;
drop view core.segment_lanes_compass;
drop view core.segment_lanes_osm;

-- ITD HPMS. The best-matching A-route through-lane row, and the best D row (of
-- the A route's route, when there's an A row). Ascending runs along the A line as
-- drawn ⚠️ (LRS events are drawn in measure order); the D carriageway runs the
-- other way. On a two-way ACHD segment: an A row with lanes both ways is the
-- whole road (a D row there is a placeholder, ignored); with lanes one way only
-- it's a divided road's carriageway, and the D row gives the other (none: unknown);
-- a one-way facility has no other direction. On a one-way ACHD segment: the A
-- carriageway when its ascending direction is the way of travel, else the D
-- carriageway, else the A row's other direction; 0 against the way of travel.
-- Turn-lane code 3 on the left ("continuous exclusive turning lanes") is read as a
-- centre turn lane ⚠️.
create view core.segment_lanes_hpms as
with t as (
  select m.road_segment_id, m.share, m.confidence, h.source_id, h.route_id, h.direction, h.through_lanes,
         h.lanes_ascending, h.lanes_descending, h.geom, substr(h.route_id, 1, 5) || substr(h.route_id, 7) as route_base,
         -- where routes share a stretch (US-26 on I-84), the interstate, then US, then state route is the
         -- one inventoried; the other's D route there is a 1-lane placeholder
         coalesce(array_position(array['IN', 'US', 'SH'], substr(h.route_id, 7, 2)), 9) as system_rank,
         coalesce(nullif(h.lanes_descending, 0), nullif(h.through_lanes, 0)) as d_lanes
  from core.segment_match m
  join core.hpms_section h on h.kind = 'through_lanes' and h.active and h.source_id = m.source_id
  where m.source = 'itd_hpms_through_lanes'
), a as (
  select distinct on (road_segment_id) * from t where direction is distinct from 'D'
  order by road_segment_id, round(share::numeric, 1) desc, system_rank, share desc, confidence desc, source_id
), d as (
  select distinct on (t.road_segment_id) t.road_segment_id, t.route_id, t.share, t.confidence, t.d_lanes as lanes
  from t left join a on a.road_segment_id = t.road_segment_id
  where t.direction = 'D' and (a.road_segment_id is null or a.route_base = t.route_base)
  order by t.road_segment_id, round(t.share::numeric, 1) desc, t.system_rank, t.d_lanes desc nulls last,
           t.share desc, t.source_id
), facility as (
  select distinct on (m.road_segment_id) m.road_segment_id, h.facility_type
  from core.segment_match m
  join core.hpms_section h on h.kind = 'facility_type' and h.active and h.source_id = m.source_id
  join a on a.road_segment_id = m.road_segment_id and a.route_id = h.route_id
  where m.source = 'itd_hpms_facility_type'
  order by m.road_segment_id, m.share desc, h.source_id
), turns as (
  select distinct on (m.road_segment_id) m.road_segment_id, h.turn_lanes_left, h.turn_lanes_right
  from core.segment_match m
  join core.hpms_section h on h.kind = 'turn_lanes' and h.active and h.source_id = m.source_id
  join a on a.road_segment_id = m.road_segment_id and a.route_id = h.route_id
  where m.source = 'itd_hpms_turn_lanes'
  order by m.road_segment_id, m.share desc, h.source_id
), r as (
  select s.id as road_segment_id, s.one_way, a.route_id, d.route_id as d_route, d.lanes as d_lanes,
         a.lanes_ascending as asc_lanes, a.lanes_descending as a_desc,
         coalesce(a.share, d.share) as share, coalesce(a.confidence, d.confidence) as confidence,
         f.facility_type, tu.turn_lanes_left, tu.turn_lanes_right,
         f.facility_type in ('one_way', 'ramp') as one_way_facility,
         coalesce(a.lanes_ascending, 0) > 0 and coalesce(a.lanes_descending, 0) = 0 as own_only,
         case when a.road_segment_id is not null then core.drawn_same_way(a.geom, s.geom) end as forward_is_ascending
  from a full join d using (road_segment_id)
  join core.road_segment s on s.id = coalesce(a.road_segment_id, d.road_segment_id)
  left join facility f on f.road_segment_id = s.id
  left join turns tu on tu.road_segment_id = s.id
), two_way as (
  select r.*,
         route_id is not null and not coalesce(one_way_facility, false) and own_only and d_lanes is not null as divided,
         case when route_id is null then null
              when one_way_facility then 0
              when own_only then d_lanes                 -- the D carriageway, or unknown
              else a_desc end as desc_lanes,
         case when one_way = 'both' then null
              when route_id is not null and forward_is_ascending = (one_way = 'forward') and asc_lanes > 0
                then 'A'
              when d_lanes is not null then 'D'
              when route_id is not null and a_desc > 0 then 'A against'
         end as carriageway
  from r
), v as (
  select two_way.*,
         case when one_way = 'both' then nullif(asc_lanes + desc_lanes, 0)
              else nullif(case carriageway when 'A' then asc_lanes when 'D' then d_lanes
                                           when 'A against' then a_desc end, 0) end as through
  from two_way
)
select road_segment_id,
       substr(coalesce(route_id, d_route), 7, 2) as route_system,
       through,
       case when through is null then null
            when one_way = 'forward' then through when one_way = 'backward' then 0
            when forward_is_ascending then asc_lanes else desc_lanes end as forward,
       case when through is null then null
            when one_way = 'forward' then 0 when one_way = 'backward' then through
            when forward_is_ascending then desc_lanes else asc_lanes end as backward,
       case when through is null then null when one_way <> 'both' then false
            when turn_lanes_left = 3 then true end as centre,
       false as single_lane,
       confidence,
       jsonb_build_object('route', route_id, 'd_route', d_route, 'ascending', asc_lanes, 'descending', desc_lanes,
                          'divided', divided, 'carriageway', carriageway,
                          'ad_conflict', coalesce(one_way_facility and a_desc > 0, false),
                          'facility', facility_type, 'turn_left', turn_lanes_left, 'turn_right', turn_lanes_right,
                          'share', share) as detail
from v;

-- ACHD's Master Street Map: ExistLane counts the whole cross-section. On a
-- two-way segment an odd count of 3 or more is read as a centre turn lane and
-- the rest split evenly (5 = 2+2+1), an even count as an even split ⚠️, and 1 as
-- one lane (single_lane). On a one-way segment that is one carriageway of a
-- divided road (the line has one-way segments running both ways along it), the
-- carriageway gets n / 2 (lead, Oct 7) ⚠️; on a one-way street, all n. 0 (not
-- built yet) reads as unknown.
create view core.segment_lanes_msm as
with best as (
  select distinct on (m.road_segment_id) m.road_segment_id, m.share, m.confidence, a.global_id, a.existing_lanes as n,
         a.funded_lanes, a.planned_lanes, a.typology_code
  from core.segment_match m
  join core.msm_arterial a on a.active and a.global_id = m.source_id
  where m.source = 'achd_msm'
  order by m.road_segment_id, m.share desc, m.confidence desc, a.global_id
), runs as (
  -- which ways one-way segments run along each line
  select m.source_id as global_id,
         bool_or(core.drawn_same_way(a.geom, s.geom) = (s.one_way = 'forward')) as along,
         bool_or(core.drawn_same_way(a.geom, s.geom) <> (s.one_way = 'forward')) as against
  from core.segment_match m
  join core.msm_arterial a on a.active and a.global_id = m.source_id and a.geom is not null
  join core.road_segment s on s.id = m.road_segment_id and s.active and s.one_way <> 'both'
  where m.source = 'achd_msm'
  group by 1
), x as (
  select b.*, s.one_way,
         s.one_way <> 'both' and coalesce(r.along and r.against, false) as carriageway_split,
         case when b.n > 0 then b.n end as k
  from best b
  join core.road_segment s on s.id = b.road_segment_id
  left join runs r on r.global_id = b.global_id
), y as (
  select x.*,
         case when k is null then null
              when one_way = 'both' then case when k = 1 then 1 when k % 2 = 1 then k - 1 else k end
              when carriageway_split then nullif(k / 2, 0)
              else k end as through
  from x
)
select road_segment_id, through,
       case when through is null or (one_way = 'both' and k = 1) then null
            when one_way = 'forward' then through when one_way = 'backward' then 0 else through / 2 end as forward,
       case when through is null or (one_way = 'both' and k = 1) then null
            when one_way = 'forward' then 0 when one_way = 'backward' then through else through / 2 end as backward,
       case when through is not null then one_way = 'both' and k >= 3 and k % 2 = 1 end as centre,
       coalesce(one_way = 'both' and k = 1, false) as single_lane,
       carriageway_split,
       confidence,
       jsonb_build_object('existing', n, 'funded', funded_lanes, 'planned', planned_lanes, 'typology', typology_code,
                          'global_id', global_id, 'carriageway_split', carriageway_split, 'share', share) as detail
from y;

-- COMPASS's RegionalCenterline: lanes read like the Master Street Map's (whole
-- cross-section on two-way pieces, 1 = one lane); a one-way piece counts its own
-- carriageway. 2 is mostly a default: core.segment_lanes uses it only when a
-- trusted source agrees.
create view core.segment_lanes_compass as
with best as (
  select distinct on (m.road_segment_id) m.road_segment_id, m.share, m.confidence, c.global_id, c.pm_id, c.lanes as n
  from core.segment_match m
  join core.compass_segment c on c.active and c.global_id = m.source_id
  where m.source = 'compass_centerline'
  order by m.road_segment_id, m.share desc, m.confidence desc, c.global_id
), y as (
  select b.*, s.one_way,
         case when n > 0 then case when s.one_way = 'both' and n >= 3 and n % 2 = 1 then n - 1 else n end end as through
  from best b join core.road_segment s on s.id = b.road_segment_id
)
select road_segment_id, n as lanes, through,
       case when through is null or (one_way = 'both' and n = 1) then null
            when one_way = 'forward' then through when one_way = 'backward' then 0 else through / 2 end as forward,
       case when through is null or (one_way = 'both' and n = 1) then null
            when one_way = 'forward' then 0 when one_way = 'backward' then through else through / 2 end as backward,
       case when through is not null then one_way = 'both' and n >= 3 and n % 2 = 1 end as centre,
       coalesce(one_way = 'both' and n = 1, false) as single_lane,
       confidence,
       jsonb_build_object('lanes', n, 'pm_id', pm_id, 'global_id', global_id, 'share', share) as detail
from y;

-- OpenStreetMap: lanes each way from core.osm_lane (counted per direction of the
-- way, then turned to the segment's direction), or, for a two-way way with an odd
-- lanes tag and no split, the Master Street Map's reading (from 3 lanes; 1 is one
-- lane) ⚠️. The best way by share among those with lane information; when it's
-- one way of a divided road, the best one-way way running the other way along the
-- segment is the other carriageway. A lone carriageway on a two-way segment gives
-- one direction only.
create view core.segment_lanes_osm as
with w as (
  select m.road_segment_id, m.share, m.confidence, m.method, o.osm_id, o.lanes, o.oneway, s.one_way as seg_one_way,
         coalesce(l.f, 0) as f, coalesce(l.b, 0) as b, coalesce(l.c, 0) as c, l.osm_id is not null as has_rows,
         core.drawn_same_way(o.geom, s.geom) as same_way
  from core.segment_match m
  join core.osm_way o on o.active and 'w' || o.osm_id = m.source_id
  join core.road_segment s on s.id = m.road_segment_id
  left join (select osm_id, count(*) filter (where direction = 'forward') as f,
                    count(*) filter (where direction = 'backward') as b,
                    count(*) filter (where direction = 'both') as c
             from core.osm_lane group by 1) l on l.osm_id = o.osm_id
  where m.source = 'osm_valley'
), x as (
  select w.*,
         case when has_rows then case when same_way then f else b end end as fwd,
         case when has_rows then case when same_way then b else f end end as bwd,
         has_rows and (f = 0 or b = 0) and c = 0 as one_way_way
  from w
  where has_rows or lanes > 0
), best as (
  select distinct on (road_segment_id) * from x order by road_segment_id, share desc, confidence desc, osm_id
), pair as (
  select distinct on (x.road_segment_id) x.road_segment_id, x.osm_id, x.fwd, x.bwd
  from x join best b on b.road_segment_id = x.road_segment_id
  where b.one_way_way and x.one_way_way and x.osm_id <> b.osm_id
    and ((b.fwd > 0 and x.bwd > 0) or (b.bwd > 0 and x.fwd > 0))
  order by x.road_segment_id, x.share desc, x.osm_id
), v as (
  select b.*, p.osm_id as pair_osm_id,
         case when not b.has_rows then null
              when p.osm_id is not null then b.fwd + p.fwd
              when b.one_way_way and b.seg_one_way = 'both' then nullif(b.fwd, 0)
              else b.fwd end as fwd_n,
         case when not b.has_rows then null
              when p.osm_id is not null then b.bwd + p.bwd
              when b.one_way_way and b.seg_one_way = 'both' then nullif(b.bwd, 0)
              else b.bwd end as bwd_n,
         not b.has_rows and b.seg_one_way = 'both' and b.lanes = 1 as single
  from best b left join pair p using (road_segment_id)
)
select road_segment_id,
       case when has_rows then nullif(fwd_n + bwd_n, 0)
            when single then 1
            when lanes >= 3 and lanes % 2 = 1 then lanes - 1 else lanes end as through,
       case when has_rows then fwd_n when single then null when seg_one_way = 'both' then lanes / 2 end as forward,
       case when has_rows then bwd_n when single then null when seg_one_way = 'both' then lanes / 2 end as backward,
       case when has_rows then c > 0 when single then false else lanes >= 3 and lanes % 2 = 1 end as centre,
       coalesce(single, false) as single_lane,
       not has_rows as split_estimated,
       confidence,
       jsonb_build_object('way', 'w' || osm_id, 'other_carriageway', 'w' || pair_osm_id, 'lanes', lanes,
                          'oneway', oneway, 'method', method, 'share', share) as detail
from v;

-- The lanes rule (docs/09 §9.3), one row per active ACHD segment; as in 0017,
-- with flags and the single-lane confidence:
--   state, US and interstate routes: HPMS, then OpenStreetMap, the Master Street Map, COMPASS;
--   ACHD arterials: the Master Street Map, then OpenStreetMap, COMPASS, HPMS last
--     (OpenStreetMap's split by direction is used when its total agrees);
--   collectors and local streets: OpenStreetMap, then COMPASS, else 1+1 assumed ('default');
--   anything else (driveways, alleys, parks): OpenStreetMap, the Master Street Map, COMPASS, HPMS.
-- A segment is a state route when ACHD calls it an interstate or ramp, or an
-- arterial whose best HPMS match is an SH, US or IN route. The sources trusted
-- for a class are HPMS and OpenStreetMap on state routes, and the Master Street
-- Map and OpenStreetMap elsewhere: HPMS's values off state routes look like
-- defaults, so they're shown but don't count. COMPASS's 2 is unknown unless a
-- trusted source also says 2 through lanes (owner, Oct 6). conflict: the
-- trusted sources and a usable COMPASS value differ by more than one through
-- lane. confidence is the winning source's match confidence (0.2 for an
-- assumed 1+1), halved for a single-lane reading. flags: single_lane (one lane
-- on a two-way road), carriageway_split (the Master Street Map's cross-section
-- halved for one carriageway), ad_conflict (HPMS's one-way facility with lanes
-- both ways).
create view core.segment_lanes as
with c as (
  select s.id as road_segment_id, s.functional_class, s.one_way,
         h.route_system, h.through as h_through, h.forward as h_fwd, h.backward as h_bwd, h.centre as h_centre,
         h.confidence as h_conf, h.detail as h_detail,
         m.through as m_through, m.forward as m_fwd, m.backward as m_bwd, m.centre as m_centre,
         m.single_lane as m_single, m.carriageway_split as m_split, m.confidence as m_conf, m.detail as m_detail,
         o.through as o_through, o.forward as o_fwd, o.backward as o_bwd, o.centre as o_centre,
         o.single_lane as o_single, o.split_estimated as o_estimated, o.confidence as o_conf, o.detail as o_detail,
         p.lanes as p_lanes, p.through as p_through, p.forward as p_fwd, p.backward as p_bwd, p.centre as p_centre,
         p.single_lane as p_single, p.confidence as p_conf, p.detail as p_detail
  from core.road_segment s
  left join core.segment_lanes_hpms h on h.road_segment_id = s.id
  left join core.segment_lanes_msm m on m.road_segment_id = s.id
  left join core.segment_lanes_osm o on o.road_segment_id = s.id
  left join core.segment_lanes_compass p on p.road_segment_id = s.id
  where s.active
), k as (
  select c.*,
         case when functional_class in ('Interstate', 'Ramp')
                or (functional_class in ('Principal Arterial', 'Minor Arterial') and route_system in ('SH', 'US', 'IN'))
              then 'state'
              when functional_class in ('Principal Arterial', 'Minor Arterial') or m_through is not null then 'arterial'
              when functional_class in ('Collector', 'Local') then 'local'
              else 'other' end as road_class
  from c
), kp as (
  select k.*,
         coalesce(p_through is not null
                  and (p_lanes <> 2 or 2 in (case when road_class = 'state' then h_through else m_through end, o_through)),
                  false) as p_ok
  from k
), w as (
  select kp.*,
         (select u.src from unnest(case road_class
                   when 'state' then array['itd_hpms', 'osm_valley', 'achd_msm', 'compass_centerline']
                   when 'arterial' then array['achd_msm', 'osm_valley', 'compass_centerline', 'itd_hpms']
                   when 'local' then array['osm_valley', 'compass_centerline', 'default']
                   else array['osm_valley', 'achd_msm', 'compass_centerline', 'itd_hpms'] end)
                 with ordinality u(src, n)
          where case u.src when 'itd_hpms' then h_through is not null
                           when 'achd_msm' then m_through is not null
                           when 'osm_valley' then o_through is not null
                           when 'compass_centerline' then p_ok
                           else true end
          order by u.n limit 1) as source,
         case road_class when 'state' then array[h_through, o_through, case when p_ok then p_through end]
                         when 'arterial' then array[m_through, o_through, case when p_ok then p_through end]
                         else array[o_through, m_through, case when p_ok then p_through end] end as trusted
  from kp
), v as (
  select w.*,
         source = 'achd_msm' and o_fwd is not null and o_bwd is not null and o_fwd + o_bwd = m_through
           and not coalesce(o_estimated, true) as osm_split,
         coalesce(case source when 'achd_msm' then m_single when 'osm_valley' then o_single
                              when 'compass_centerline' then p_single end, false) as single
  from w
)
select road_segment_id,
       road_class,
       source,
       case source when 'itd_hpms' then h_through when 'achd_msm' then m_through when 'osm_valley' then o_through
                   when 'compass_centerline' then p_through
                   when 'default' then case when one_way = 'both' then 2 else 1 end end as lanes_total,
       case when osm_split then o_fwd
            else case source when 'itd_hpms' then h_fwd when 'achd_msm' then m_fwd when 'osm_valley' then o_fwd
                             when 'compass_centerline' then p_fwd
                             when 'default' then case when one_way = 'backward' then 0 else 1 end end end as lanes_forward,
       case when osm_split then o_bwd
            else case source when 'itd_hpms' then h_bwd when 'achd_msm' then m_bwd when 'osm_valley' then o_bwd
                             when 'compass_centerline' then p_bwd
                             when 'default' then case when one_way = 'forward' then 0 else 1 end end end as lanes_backward,
       case when osm_split then o_centre
            else case source when 'itd_hpms' then h_centre when 'achd_msm' then m_centre when 'osm_valley' then o_centre
                             when 'compass_centerline' then p_centre end end as centre_turn_lane,
       case when osm_split then 'osm_valley' else source end as split_from,
       case when osm_split then false
            else source in ('achd_msm', 'compass_centerline', 'default')
                 or (source = 'osm_valley' and coalesce(o_estimated, false)) end as split_estimated,
       round(((case source when 'itd_hpms' then h_conf when 'achd_msm' then m_conf when 'osm_valley' then o_conf
                           when 'compass_centerline' then p_conf when 'default' then 0.2 end)
              * case when single then 0.5 else 1 end)::numeric, 3)::double precision as confidence,
       coalesce((select max(t) - min(t) > 1 from unnest(trusted) t where t is not null), false) as conflict,
       array_remove(array[case when single then 'single_lane' end,
                          case when source = 'achd_msm' and m_split then 'carriageway_split' end,
                          case when source = 'itd_hpms' and (h_detail->>'ad_conflict')::boolean
                               then 'ad_conflict' end], null) as flags,
       jsonb_strip_nulls(jsonb_build_object(
         'itd_hpms', case when h_detail is not null then h_detail || jsonb_build_object(
           'through', h_through, 'forward', h_fwd, 'backward', h_bwd, 'centre', h_centre, 'confidence', h_conf) end,
         'achd_msm', case when m_detail is not null then m_detail || jsonb_build_object(
           'through', m_through, 'forward', m_fwd, 'backward', m_bwd, 'centre', m_centre, 'confidence', m_conf) end,
         'osm_valley', case when o_detail is not null then o_detail || jsonb_build_object(
           'through', o_through, 'forward', o_fwd, 'backward', o_bwd, 'centre', o_centre, 'confidence', o_conf) end,
         'compass_centerline', case when p_detail is not null then p_detail || jsonb_build_object(
           'through', p_through, 'forward', p_fwd, 'backward', p_bwd, 'centre', p_centre, 'usable', p_ok,
           'confidence', p_conf) end)) as candidates
from v;
