-- roads 0004: ACHD's Official Bicycle Facility Network (landscape sprint, Oct 2026: package P7b;
-- the owner brought it forward on Oct 8, decision 11: "wanna do bike network now too?").
--
-- Source achd_bike_network (plugins/roads/ingest/sources/achd_bike_network.py): ACHD's layer on
-- gis.achdidaho.org (never more.achdidaho.org), about 3,900 lines over 1,080 miles of Ada County's
-- arterials, collectors, bikeways and pathways, field-checked by ACHD. It is the one curb-to-curb
-- width source: TotalPavement, TotalROW, and per direction the lane, bike-lane, buffer and parking
-- widths, which the real-width roads build (P7) reads through roads.segment_bike_xsection below.
--
-- License: none stated (the hub's licence field holds a disclaimer: "general reference purposes only
-- and should not be used for planning determinations"). Credit "Ada County Highway District".
-- Republish: internal. Everything here, and anything built from it, stays on the owner's map until
-- ACHD is asked. ACHD's LTS is ACHD's assessment, never ours. ACHD's free-text Comments and
-- FieldNotes are kept apart, in roads.bike_facility_note, and stay out of every view, export, tile
-- and card.
--
-- Versioned as the other ACHD layers are: each record's versions in raw.record (by OBJECTID,
-- without Shape__Length), the current state here, rows never deleted (active false when gone). The
-- layer has no GlobalID and a reload renumbers OBJECTIDs (they ran 3929-7869 on Oct 11, 2026), so a
-- run that finds most IDs new carries rows over to the new IDs (ingest/arcgis.py carry_over).
--
-- Widths are kept in feet, as ACHD records them; the views give metres. Blank and 'N/A' are null.
-- The schema may already exist (roads 0001, S1): created here too, so this applies on its own.

create schema if not exists roads;

create table roads.bike_facility (
  object_id          bigint primary key,           -- ACHD's OBJECTID (renumbered by a reload: carried over)
  location_id        text,                         -- ACHD's LocationID, 'BMP0458'; repeats across pieces
  kind               text not null check (kind in ('street', 'path', 'planned')),
                                                   -- path: FuncClass or Street 'Pathway'; planned: a road not
                                                   -- built yet (Street or BMPStatus 'New Road'); else street
  street             text,
  city               text,
  agency             text,                         -- who owns the road: ACHD, ITD, Boise, ...
  func_class         text,                         -- Arterial, Collector, Local, Pathway, State
  existing_type      text,                         -- ACHD's words for what's there: 'Bike Lane', 'Mixed Traffic', ...
  lts                smallint check (lts between 1 and 4),   -- ACHD's level of traffic stress (ACHD's assessment)
  bike_legend        text,                         -- 'High Comfort for All', ...
  speed_mph          smallint,                     -- Speed (blank on most rows)
  speed_field_mph    smallint,                     -- SpeedField: the posted speed ACHD's field check saw
  volume             text,                         -- ACHD's traffic-volume range as text: '+3000', '750 - 1500'
  yr_built           text,                         -- as text: '2023', 'TBD'
  year_added         smallint,
  year_updated       text,
  field_verified     boolean,                      -- 'Verified' (true), 'N/A' (false)
  total_lanes        smallint,                     -- every lane: both directions plus centre turn lanes
  total_pavement_ft  real check (total_pavement_ft > 0),     -- curb to curb
  total_row_ft       real check (total_row_ft > 0),          -- right of way
  -- One side per direction of travel, as ACHD names them: EBNB is the eastbound or northbound side
  -- (direction 'E' or 'N'), WBSB the westbound or southbound one ('W' or 'S'). They're the two
  -- sides of the street: on a one-way street the side against the traffic has no direction ('N/A')
  -- and 0 lanes, but keeps its edge and any parking. Codes:
  --   facility: mixed_traffic, no_facility, bike_lane, buffered_bike_lane, protected_bike_lane,
  --             raised_bike_lane, cycle_track, multi_use_path, other
  --   edge: curb_gutter, curb, shoulder, other; parking: none, parallel, angled, other
  --   right_turn: turn_lane, through_right_outside, through_right_shared, other (null: 'N/A')
  --   markings: yes, no, needs_correcting, other
  --   buffer: none, painted, landscaping, extruded_curb, jersey_barrier, delineator, parking, other
  ebnb_direction     text check (ebnb_direction in ('N', 'E')),
  ebnb_facility      text,
  ebnb_facility_w_ft real check (ebnb_facility_w_ft > 0),
  ebnb_lane_w_ft     real check (ebnb_lane_w_ft > 0),        -- the travel lane next to the facility
  ebnb_lanes         smallint,
  ebnb_edge          text,
  ebnb_right_turn    text,
  ebnb_parking       text,
  ebnb_parking_w_ft  real check (ebnb_parking_w_ft > 0),
  ebnb_markings      text,
  ebnb_buffer        text,
  ebnb_buffer_w_ft   real check (ebnb_buffer_w_ft > 0),
  ebnb_buffer_varies boolean not null default false,       -- 'Varies'
  wbsb_direction     text check (wbsb_direction in ('S', 'W')),
  wbsb_facility      text,
  wbsb_facility_w_ft real check (wbsb_facility_w_ft > 0),
  wbsb_lane_w_ft     real check (wbsb_lane_w_ft > 0),
  wbsb_lanes         smallint,
  wbsb_edge          text,
  wbsb_right_turn    text,
  wbsb_parking       text,
  wbsb_parking_w_ft  real check (wbsb_parking_w_ft > 0),
  wbsb_markings      text,
  wbsb_buffer        text,
  wbsb_buffer_w_ft   real check (wbsb_buffer_w_ft > 0),
  wbsb_buffer_varies boolean not null default false,
  attributes         jsonb not null default '{}',  -- ACHD's other fields as published, blanks dropped;
                                                   -- never Comments or FieldNotes
  geom               geometry(MultiLineString, 4326),
  active             boolean not null default true,
  first_seen         timestamptz not null default now(),
  last_seen          timestamptz not null default now()
);
create index bike_facility_geom on roads.bike_facility using gist (geom);
create index bike_facility_kind on roads.bike_facility (kind) where active;

comment on table roads.bike_facility is
  'ACHD''s Official Bicycle Facility Network (achd_bike_network). License none stated (ACHD disclaimer: '
  'not for planning determinations); credit Ada County Highway District; republish: internal';

-- INTERNAL. ACHD's free-text Comments and FieldNotes (its field crews' remarks, mostly on widths),
-- for reading by hand while checking widths. No view, export, tile set or card reads this table,
-- and the tile login can't: deploy/tvt_tiles.sql takes back the grant roads' default privileges
-- give it, and checks (its never_tables list).
create table roads.bike_facility_note (
  object_id    bigint primary key references roads.bike_facility on update cascade on delete cascade,
  comments     text,
  field_notes  text,
  check (comments is not null or field_notes is not null)
);

comment on table roads.bike_facility_note is
  'INTERNAL: ACHD''s free-text Comments and FieldNotes for roads.bike_facility. Never in a view, export, '
  'tile set or card. License none stated; credit Ada County Highway District; republish: no';

-- Which ACHD road segments each street record lies along: core's line matcher
-- (ingest/linematch.py) with ACHD's active segments as the targets, under roads' rule
-- (plugins/roads/ingest/segment_match.py; the method says which). Rewritten as a whole after each
-- run that changes the records, and after ACHD's segments change. Paths and planned roads aren't
-- matched. Kept here rather than in core.segment_match, so the build role can write it and the
-- lane sources' matches are untouched. share and overlap_m measure the ACHD segment.
create table roads.bike_facility_match (
  road_segment_id  bigint not null references core.road_segment,
  object_id        bigint not null references roads.bike_facility on update cascade,
  overlap_m        real,
  share            real,                           -- of the ACHD segment's length
  bearing_diff     real,                           -- degrees
  method           text not null,                  -- 'buffer15_bearing20', 'way_in_buffer15_bearing20', ...
  confidence       real check (confidence between 0 and 1),
  matched_at       timestamptz not null default now(),
  primary key (road_segment_id, object_id)
);
create index bike_facility_match_object on roads.bike_facility_match (object_id);

comment on table roads.bike_facility_match is
  'ACHD road segments each roads.bike_facility street record lies along (core line matcher). Derived from '
  'ACHD layers: license none stated; credit Ada County Highway District; republish: internal';

-- One row per direction of each record, in metres: the parts of the cross-section P7 builds from.
-- bike_w_m, buffer_w_m and parking_w_m are 0 where ACHD says there's none (mixed traffic or no
-- facility; buffer 'None'; parking 'None'), null where unknown. bike_in_roadway: whether the
-- facility lies between the curbs, so inside total_pavement: bike lanes, buffered and protected
-- bike lanes do (on Oct 11, 2026, ACHD's lanes, bike lanes, buffers and parking add up to
-- TotalPavement within 2 ft, plus about 12 ft where there's a centre turn lane); raised bike lanes,
-- cycle tracks and multi-use paths don't (they add up without them) ⚠️ protected bike lanes are
-- few and mixed. roadway_m is this side's share of the pavement: lanes times the lane width, plus
-- parking, plus the bike facility and its buffer when they're in the roadway; null when a part is
-- unknown (on most mixed-traffic sides: ACHD records the lane width almost only beside a bike
-- facility). A one-way street's other side has no direction and 0 lanes, but keeps its edge and any
-- parking (ACHD writes 'N/A' for its direction). present: the side has a direction, lanes or a
-- facility (records ACHD hasn't checked in the field have neither side).
create view roads.bike_facility_side as
with s as (
  select object_id, 'ebnb' as side, ebnb_direction as direction, ebnb_lanes as lanes,
         ebnb_lane_w_ft as lane_w_ft, ebnb_facility as bike, ebnb_facility_w_ft as bike_w_ft,
         ebnb_buffer as buffer, ebnb_buffer_w_ft as buffer_w_ft, ebnb_buffer_varies as buffer_varies,
         ebnb_parking as parking, ebnb_parking_w_ft as parking_w_ft, ebnb_edge as edge,
         ebnb_right_turn as right_turn, ebnb_markings as markings
  from roads.bike_facility where active
  union all
  select object_id, 'wbsb', wbsb_direction, wbsb_lanes, wbsb_lane_w_ft, wbsb_facility, wbsb_facility_w_ft,
         wbsb_buffer, wbsb_buffer_w_ft, wbsb_buffer_varies, wbsb_parking, wbsb_parking_w_ft, wbsb_edge,
         wbsb_right_turn, wbsb_markings
  from roads.bike_facility where active
), m as (
  select s.*,
         round((lane_w_ft * 0.3048)::numeric, 2) as lane_w_m,
         case when bike in ('mixed_traffic', 'no_facility') then 0
              else round((bike_w_ft * 0.3048)::numeric, 2) end as bike_w_m,
         bike in ('bike_lane', 'buffered_bike_lane', 'protected_bike_lane') as bike_in_roadway,
         case when buffer = 'none' then 0 when buffer_varies then null
              else round((buffer_w_ft * 0.3048)::numeric, 2) end as buffer_w_m,
         case when parking = 'none' then 0 else round((parking_w_ft * 0.3048)::numeric, 2) end as parking_w_m,
         direction is not null or lanes is not null or bike is not null as present
  from s
)
select object_id, side, present, direction, lanes, lane_w_m, bike, bike_w_m, bike_in_roadway, buffer,
       buffer_w_m, buffer_varies, parking, parking_w_m, edge, right_turn, markings,
       case when present then
         case when lanes = 0 then 0 else lanes * lane_w_m end + parking_w_m
         + case when bike_in_roadway then bike_w_m + coalesce(buffer_w_m, case when buffer_varies then null else 0 end)
                when bike in ('mixed_traffic', 'no_facility', 'raised_bike_lane', 'cycle_track', 'multi_use_path')
                  then 0 end
       end as roadway_m
from m;

comment on view roads.bike_facility_side is
  'Each roads.bike_facility record''s two directions in metres (no free text). License none stated; '
  'credit Ada County Highway District; republish: internal';

-- THE INTERFACE FOR P7 (the real-width roads build): ACHD's bike-network cross-section on each ACHD
-- road segment it lies along, with its two sides turned to the segment's drawn direction, as
-- core.segment_lanes' forward and backward are. One row per matched segment: the best record by
-- share (to 0.1), then field-verified first, then confidence.
--
-- forward_side says which of ACHD's sides runs the way the segment is drawn: the record names its
-- sides on one axis (Northbound/Southbound or Eastbound/Westbound), and the segment's end-to-end
-- bearing decides, when it runs within 75 degrees of that axis; otherwise forward_side is null and
-- flags has direction_unclear. fwd_* and bwd_* are bike_facility_side's columns for the forward and
-- backward sides. Totals: total_pavement_m (curb to curb) and total_row_m are the record's, the
-- whole road's: on a one-way ACHD segment (one carriageway of a divided road) they span both
-- carriageways (flag one_way_segment). centre_lanes: total_lanes minus both directions' lanes (a
-- centre turn lane on most rows that have one), null when they disagree (flag lanes_disagree).
-- unassigned_m: the pavement left after both sides' roadway_m: the centre turn lane, a median, gutters;
-- under -0.5 m flags components_exceed_pavement. centre_lanes and unassigned_m are the record's
-- too, from both its sides, whichever of them the row shows.
--
-- On a one-way ACHD segment the record's two sides don't always both belong to it:
-- - a one-way record (the side against the traffic has 0 lanes, ACHD's 'N/A'): both sides are this
--   carriageway's, the other one holding only its edge and any parking or bike lane. Both shown;
-- - lanes on both sides (a two-way record over one carriageway of a divided road, or over a couplet
--   or slip piece): the side against the segment's traffic is another carriageway's, so it's left
--   out (its bwd_* or fwd_* null) and flagged other_carriageway;
-- - no lanes on the side the segment's traffic runs (0, or unknown with lanes on the other): the
--   match or ACHD's directions are wrong there, so neither side is shown; flag
--   direction_conflicts_one_way (9 segments on Oct 11, 2026).
create view roads.segment_bike_xsection as
with best as (
  select distinct on (m.road_segment_id) m.road_segment_id, m.object_id, m.share, m.confidence, m.method
  from roads.bike_facility_match m
  join roads.bike_facility b on b.object_id = m.object_id and b.active
  order by m.road_segment_id, round(m.share::numeric, 1) desc, b.field_verified desc nulls last,
           m.confidence desc, m.object_id
), x as (
  select best.*, b.location_id, b.street, b.existing_type, b.lts, b.field_verified, b.year_updated,
         b.total_lanes, b.total_pavement_ft, b.total_row_ft, s.one_way as seg_one_way,
         coalesce(b.ebnb_direction, case b.wbsb_direction when 'S' then 'N' when 'W' then 'E' end) as axis,
         degrees(ST_Azimuth(ST_StartPoint(ST_GeometryN(s.geom, 1))::geography,
                            ST_EndPoint(ST_GeometryN(s.geom, ST_NumGeometries(s.geom)))::geography)) as az
  from best
  join roads.bike_facility b on b.object_id = best.object_id
  join core.road_segment s on s.id = best.road_segment_id
), d as (
  select x.*,
         case when along >= 0.26 then 'ebnb' when along <= -0.26 then 'wbsb' end as forward_side
  from x
  cross join lateral (select case axis when 'N' then cos(radians(az)) when 'E' then sin(radians(az)) end as along) a
), t as (
  select d.*, e.present as e_present, e.lanes as e_lanes, e.roadway_m as e_roadway,
         w.present as w_present, w.lanes as w_lanes, w.roadway_m as w_roadway,
         round((d.total_pavement_ft * 0.3048)::numeric, 2) as total_pavement_m,
         round((d.total_row_ft * 0.3048)::numeric, 2) as total_row_m
  from d
  join roads.bike_facility_side e on e.object_id = d.object_id and e.side = 'ebnb'
  join roads.bike_facility_side w on w.object_id = d.object_id and w.side = 'wbsb'
), c as (
  select t.*,
         case when e_present and w_present then total_lanes - e_lanes - w_lanes end as lanes_left,
         case when e_present and w_present then total_pavement_m - e_roadway - w_roadway end as unassigned,
         -- On a one-way segment: the lanes on the side its traffic runs, and on the other side.
         case seg_one_way when 'forward' then fl when 'backward' then bl end as with_lanes,
         case seg_one_way when 'forward' then bl when 'backward' then fl end as against_lanes
  from t
  cross join lateral (
    select case forward_side when 'ebnb' then e_lanes when 'wbsb' then w_lanes end as fl,
           case forward_side when 'ebnb' then w_lanes when 'wbsb' then e_lanes end as bl) l
), o as (
  select c.*,
         coalesce(with_lanes = 0 or (with_lanes is null and against_lanes > 0), false) as conflicts,
         coalesce(with_lanes > 0 and against_lanes > 0, false) as other_carriageway
  from c
)
select c.road_segment_id, c.object_id, c.location_id, c.street, c.existing_type, c.lts, c.field_verified,
       c.year_updated, c.share, c.confidence, c.method, c.seg_one_way,
       c.total_pavement_m, c.total_row_m, c.total_lanes,
       case when c.lanes_left >= 0 then c.lanes_left end as centre_lanes,
       c.unassigned as unassigned_m,
       c.forward_side,
       f.lanes as fwd_lanes, f.lane_w_m as fwd_lane_w_m, f.bike as fwd_bike, f.bike_w_m as fwd_bike_w_m,
       f.bike_in_roadway as fwd_bike_in_roadway, f.buffer as fwd_buffer, f.buffer_w_m as fwd_buffer_w_m,
       f.buffer_varies as fwd_buffer_varies, f.parking as fwd_parking, f.parking_w_m as fwd_parking_w_m,
       f.edge as fwd_edge, f.right_turn as fwd_right_turn, f.roadway_m as fwd_roadway_m,
       r.lanes as bwd_lanes, r.lane_w_m as bwd_lane_w_m, r.bike as bwd_bike, r.bike_w_m as bwd_bike_w_m,
       r.bike_in_roadway as bwd_bike_in_roadway, r.buffer as bwd_buffer, r.buffer_w_m as bwd_buffer_w_m,
       r.buffer_varies as bwd_buffer_varies, r.parking as bwd_parking, r.parking_w_m as bwd_parking_w_m,
       r.edge as bwd_edge, r.right_turn as bwd_right_turn, r.roadway_m as bwd_roadway_m,
       array_remove(array[
         case when c.forward_side is null and (c.e_present or c.w_present) then 'direction_unclear' end,
         case when c.conflicts then 'direction_conflicts_one_way' end,
         case when c.other_carriageway then 'other_carriageway' end,
         case when c.lanes_left < 0 then 'lanes_disagree' end,
         case when c.unassigned < -0.5 then 'components_exceed_pavement' end,
         case when c.total_pavement_ft > c.total_row_ft then 'pavement_exceeds_row' end,
         case when c.seg_one_way <> 'both' then 'one_way_segment' end], null) as flags
from o c
left join roads.bike_facility_side f on f.object_id = c.object_id and f.side = c.forward_side and f.present
  and not c.conflicts and not (c.other_carriageway and c.seg_one_way = 'backward')
left join roads.bike_facility_side r on r.object_id = c.object_id and r.present
  and r.side = case c.forward_side when 'ebnb' then 'wbsb' when 'wbsb' then 'ebnb' end
  and not c.conflicts and not (c.other_carriageway and c.seg_one_way = 'forward');

comment on view roads.segment_bike_xsection is
  'ACHD''s bike-network cross-section per ACHD road segment, forward and backward as drawn (P7''s input). '
  'License none stated; credit Ada County Highway District; republish: internal';
