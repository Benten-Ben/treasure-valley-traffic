-- 0011: the road network's own sources (owner, Oct 6, 2026): signalized
-- intersections and signal devices, rail crossings, and the per-source lane
-- inventories that the lanes rule picks from (docs/08 §8.9, docs/09 §9.3,
-- docs/12). 0008 stays reserved for UI v2's road-weather layer.
--
-- OpenStreetMap stays in its own tables (osm_*), so the other sources' tables
-- aren't pulled under the ODbL; anything that mixes it in is a derivative.

-- More kinds of things a source record can be linked to.
alter table core.source_link drop constraint source_link_entity_check;
alter table core.source_link add constraint source_link_entity_check check (entity in
  ('intersection', 'approach', 'camera', 'camera_view', 'count_station', 'road_segment', 'stop',
   'rail_crossing', 'signal_device'));

-- One row per signalized (or other controlled) intersection, built by
-- `python3 -m ingest match-intersections` from COMPASS's signals, ACHD's 2022
-- signal poles and OpenStreetMap's signal nodes. Rows are never deleted.
create table core.intersection (
  id               bigint generated always as identity primary key,
  name             text not null,                   -- 'Eagle Rd & Fairview Ave'
  geom             geometry(Point, 4326) not null,  -- the junction's centre
  control          text not null check (control in
                     ('signal', 'half_signal', 'signal_uturn', 'roundabout', 'unsignalized')),
  operator         text,                            -- who runs it: ACHD, ITD, Nampa, Caldwell, ...
  owner            text,
  county           text,
  city             text,
  achd_synchro_id  int unique,                      -- ACHD's signal ID (in COMPASS's layer)
  coord_group      text,                            -- coordination group, e.g. 'EAGLE RD/FAIRVIEW/CHERRY'
  evidence         text[] not null default '{}',    -- {'compass', 'achd_2022', 'osm'}
  confidence       real not null check (confidence between 0 and 1),
  status           text not null default 'active' check (status in ('active', 'candidate', 'retired')),
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now()
);
create index intersection_geom on core.intersection using gist (geom);

-- An approach (leg) of an intersection, as one source describes it. COMPASS
-- names approaches by travel direction: its northbound approach is the south leg.
create table core.approach (
  intersection_id  bigint not null references core.intersection,
  leg              text not null check (leg in ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')),
  source           text not null references ops.source,
  right_turn_lanes smallint,
  left_turn_phasing  text,                          -- protected, permitted, protected-permitted
  right_turn_phasing text,
  peak_volumes     jsonb,                           -- modelled turn volumes {"L":..,"T":..,"R":..}, year unknown
  updated_at       timestamptz not null default now(),
  primary key (intersection_id, leg, source)
);

-- A signal device as one (non-OpenStreetMap) source lists it: COMPASS's
-- intersection points, ACHD's 2022 poles, beacons and flashers.
create table core.signal_device (
  id               bigint generated always as identity primary key,
  source           text not null references ops.source,
  source_id        text not null,
  kind             text not null check (kind in
                     ('signal_intersection', 'signal_pole', 'ped_hybrid', 'rrfb', 'ped_conventional',
                      'warning_beacon', 'school_flasher', 'fire_signal')),
  name             text,
  geom             geometry(Point, 4326) not null,
  attributes       jsonb,                           -- the source's own fields, cleaned
  intersection_id  bigint references core.intersection,
  distance_m       real,                            -- to its intersection
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now(),
  unique (source, source_id)
);
create index signal_device_geom on core.signal_device using gist (geom);
create index signal_device_intersection on core.signal_device (intersection_id);

-- A highway-rail crossing (FRA's inventory, public domain).
create table core.rail_crossing (
  id               bigint generated always as identity primary key,
  crossing_id      text not null unique,            -- FRA/USDOT crossing number, e.g. '807452X'
  railroad         text,
  railroad_code    text,
  street           text,
  city             text,
  county_fips      text,
  position         text,                            -- At Grade, RR Under, RR Over
  public           boolean,
  closed           boolean not null default false,
  warning          text,                            -- gates, flashing_lights, crossbucks, stop_signs, ...
  gate_arms        smallint,
  ped_gate_arms    smallint,
  signal_controlled boolean,                        -- FRA: highway traffic signals control the crossing
  signal_nearby    boolean,
  interconnected   boolean,
  preemption       text,                            -- Simultaneous, Advance
  presignals       boolean,
  storage_distance_ft real,
  stop_line_distance_ft real,
  day_through_trains   smallint,
  night_through_trains smallint,
  switching_trains     smallint,
  max_timetable_mph    smallint,
  main_tracks      smallint,
  other_tracks     smallint,
  road_lanes       smallint,
  fra_aadt         int,
  fra_aadt_year    smallint,
  revision_date    date,
  geom             geometry(Point, 4326),           -- null for some closed or private crossings
  intersection_id  bigint references core.intersection,  -- nearest signalized intersection within 200 m
  signal_distance_m real,
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now()
);
create index rail_crossing_geom on core.rail_crossing using gist (geom);

-- Which of a source's lines lie along an ACHD road segment. One source record
-- can cover many segments, which core.source_link's key doesn't allow.
create table core.segment_match (
  road_segment_id  bigint not null references core.road_segment,
  source           text not null references ops.source,
  source_id        text not null,
  overlap_m        real,
  share            real,                            -- of the ACHD segment's length
  bearing_diff     real,                            -- degrees
  method           text not null,                   -- 'buffer15_bearing20', 'buffer10_name', ...
  confidence       real check (confidence between 0 and 1),
  matched_at       timestamptz not null default now(),
  primary key (road_segment_id, source, source_id)
);
create index segment_match_source on core.segment_match (source, source_id);

-- ITD's HPMS inventory: one row per HPMS record (layer kind + EventID), with
-- the value its layer carries. Sparse: most columns are null on any one row.
create table core.hpms_section (
  id               bigint generated always as identity primary key,
  kind             text not null,                   -- through_lanes, turn_lanes, lane_width, median, shoulders,
                                                    -- access_control, peak_lanes, facility_type
  event_id         text not null,
  route_id         text not null,                   -- e.g. '01990ASH055'
  direction        text,                            -- A (ascending) or D (descending) route
  from_mi          real,
  to_mi            real,
  road_name        text,
  through_lanes    smallint,
  lanes_ascending  smallint,
  lanes_descending smallint,
  turn_lanes_left  smallint,                        -- HPMS codes 1-6
  turn_lanes_right smallint,
  lane_width_ft    real,
  median_type      text,
  median_width_ft  real,
  shoulder_type    text,
  shoulder_width_left_ft  real,
  shoulder_width_right_ft real,
  access_control   text,
  peak_lanes       smallint,
  counter_peak_lanes smallint,
  facility_type    text,
  value_source     text,
  source_modified  timestamptz,
  geom             geometry(MultiLineString, 4326),
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now(),
  unique (kind, event_id)
);
create index hpms_section_geom on core.hpms_section using gist (geom);

-- ACHD's Master Street Map arterials (Ada only). Lanes count the whole
-- cross-section: 5 = 2+2 plus a centre turn lane (docs/09 §9.3).
create table core.msm_arterial (
  id               bigint generated always as identity primary key,
  global_id        text not null unique,
  street_code      text,
  street_name      text,
  typology_code    text,                            -- AR, AT, STATE, APC, MA; N_ = a new road
  typology         text,
  existing_lanes   smallint,
  funded_lanes     smallint,
  planned_lanes    smallint,
  row_project      text,
  row_preservation text,
  parking          text,
  comments         text,
  source_edited    timestamptz,
  geom             geometry(MultiLineString, 4326),
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now()
);
create index msm_arterial_geom on core.msm_arterial using gist (geom);

-- COMPASS's RegionalCenterline (Ada and Canyon): pm_id is the key COMPASS's
-- counts, crashes and travel model use.
create table core.compass_segment (
  id               bigint generated always as identity primary key,
  pm_id            text not null unique,
  name             text,
  county           text,
  functional_class text,
  posted_speed_mph smallint,
  lanes            smallint,
  one_way          text,
  attributes       jsonb,
  geom             geometry(MultiLineString, 4326),
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now()
);
create index compass_segment_geom on core.compass_segment using gist (geom);

-- OpenStreetMap (ODbL), from the weekly Geofabrik extract processed on the
-- server: highway ways, their lanes, and signal and crossing nodes.
create table core.osm_way (
  osm_id           bigint primary key,
  highway          text not null,
  name             text,
  ref              text,
  oneway           text,
  lanes            smallint,
  lanes_forward    smallint,
  lanes_backward   smallint,
  turn_lanes       text,                            -- raw turn:lanes values as tagged
  turn_lanes_forward  text,
  turn_lanes_backward text,
  width_m          real,
  maxspeed         text,
  layer            smallint,
  bridge           boolean,
  tags             jsonb not null,
  geom             geometry(LineString, 4326) not null,
  osm_version      int,
  osm_timestamp    timestamptz,
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now()
);
create index osm_way_geom on core.osm_way using gist (geom);

-- One lane of a way, counted from 1 at the left in the direction of travel
-- (as WZDx does), with the turns tagged for it.
create table core.osm_lane (
  osm_id           bigint not null references core.osm_way on delete cascade,
  direction        text not null check (direction in ('forward', 'backward', 'both')),
  lane             smallint not null,
  turns            text[],                          -- {left, through}, {right}, ... ({} when untagged)
  primary key (osm_id, direction, lane)
);

create table core.osm_node (
  osm_id           bigint primary key,
  kind             text not null check (kind in ('traffic_signals', 'crossing_signals', 'level_crossing')),
  tags             jsonb not null,
  geom             geometry(Point, 4326) not null,
  osm_version      int,
  osm_timestamp    timestamptz,
  active           boolean not null default true,
  first_seen       timestamptz not null default now(),
  last_seen        timestamptz not null default now()
);
create index osm_node_geom on core.osm_node using gist (geom);
