-- roads 0003: real-width roads, the build's products (landscape sprint, Oct 2026: package P7; plan C12, C17,
-- §3.2-3.5; the roads-real-width design).
--
-- `python3 -m ingest roads-build` (plugins/roads/ingest/build.py; a light job: standard-library Python running
-- PostGIS SQL) makes every table here from:
--   core.osm_way (osm_valley: major roads and lane-tagged ways) and roads.osm_street (the other streets and
--     alleys): the carriageways, split into pieces at the nodes they share;
--   roads.osm_paving and roads.osm_walk_node (osm_paving): sidewalks (a road's edge stays 1 m inside a parallel
--     sidewalk) and marked crossings (crosswalks: only where `marked` is true, decision 10);
--   core.road_segment, core.segment_lanes and roads.segment_bike_xsection (ACHD), core.hpms_section (ITD): lane
--     counts, the measured curb-to-curb widths of ACHD's bike network, lane, shoulder and median widths, bridges;
--   core.intersection: signals (stop bars); core.taz (COMPASS): which county a piece is in;
--   roads.developed_land (USDA NASS's CDL): whether an untagged local street is in town (curbed) or rural.
-- The three OpenStreetMap tables must hold one extract (osm_extract.check_partition). Every table is replaced
-- whole by each build, in one transaction, and roads.build records it: so ids here are the build's own, and
-- anything kept across builds (cards, links) keys on the OpenStreetMap way (osm_id) and ACHD's segment, never
-- on a piece's id.
--
-- The tables reference each other by the build's ids (piece_id, junction_id) without foreign keys, but
-- roads.xsection's: they're replaced together, and a delete checking six tables for each of 70,000 pieces made
-- a rebuild's clearing take minutes.
--
-- Geometry is in EPSG:32611 (UTM 11N on WGS 84: the ground's grid and the export contract's CRS), in metres.
--
-- Licence: the geometry is OpenStreetMap's (ODbL: a derived database, credit "© OpenStreetMap contributors"),
-- and the widths and lane counts rest on ACHD's and ITD's layers, which state no licence (internal, credited).
-- So these tables are internal: shown only on the owner's map. roads.xsection keeps each piece's lane source
-- and every component's source (`sources`, `republish`), so a public variant is a rebuild from public inputs,
-- not a redesign (plan C17).

-- One row per build; the current one's rows are the tables below.
create table roads.build (
  id            text primary key,                  -- the build's UTC time, e.g. 20261012T031500Z
  started_at    timestamptz not null,
  finished_at   timestamptz not null,
  current       boolean not null default false,
  extract_md5   text not null,                     -- the extract core.osm_way, roads.osm_street and roads.osm_paving hold
  inputs        jsonb not null,                    -- [{name, source, version, licence, republish, credit}]
  params        jsonb not null,                    -- the rules' numbers (plugins/roads/ingest/xsection.py DEFAULTS)
  counts        jsonb not null,
  seconds       real not null,
  license       text not null,
  republish     text not null check (republish in ('yes', 'aggregates', 'internal', 'no')),
  credit        text not null
);
create unique index build_current on roads.build (current) where current;

comment on table roads.build is
  'Builds of the real-width roads (roads-build), one current. License ODbL (© OpenStreetMap contributors) with ACHD''s and ITD''s layers (none stated); republish: internal';

-- An OpenStreetMap way's stretch between the nodes it shares with other road ways (or its ends).
create table roads.piece (
  id              int primary key,
  osm_id          bigint not null,                 -- the way (core.osm_way or roads.osm_street)
  seq             smallint not null,               -- its place along the way, from 1
  source          text not null check (source in ('osm_valley', 'osm_street')),
  highway         text not null,
  service         text,                            -- 'alley', or a service way's service=* (osm_valley's lane-tagged ones)
  name            text,
  ref             text,
  oneway          smallint not null check (oneway in (-1, 0, 1)),   -- 1: travel along the line; -1: against it; 0: both
  roundabout      boolean not null default false,  -- junction=roundabout or circular
  bridge          boolean not null default false,
  tunnel          boolean not null default false,
  layer           smallint not null default 0,
  from_node       int not null,                    -- the build's node numbers: equal where pieces meet
  to_node         int not null,
  from_junction   int,                             -- roads.junction at its start and end
  to_junction     int,
  county          text,                            -- 'Ada', 'Canyon', or null (elsewhere in the box)
  road_segment_id bigint,                          -- ACHD's segment it lies along (core's line matcher), in Ada
  seg_same_way    boolean,                         -- drawn the same way as that segment
  seg_confidence  real,
  length_m        real not null,
  geom            geometry(LineString, 32611) not null
);
create index piece_geom on roads.piece using gist (geom);
create index piece_osm on roads.piece (osm_id);
create index piece_segment on roads.piece (road_segment_id);

comment on table roads.piece is
  'Real-width roads: OpenStreetMap ways split where they meet (roads-build). License ODbL (© OpenStreetMap contributors); road_segment_id links ACHD (none stated); republish: internal';

-- The cross-section of a piece, by the rules in plugins/roads/ingest/xsection.py. Left and right are as the
-- line is drawn (OpenStreetMap's way direction); forward lanes run along it. Widths in metres.
create table roads.xsection (
  piece_id        int primary key references roads.piece on delete cascade,
  lanes_fwd       smallint not null check (lanes_fwd >= 0),
  lanes_bwd       smallint not null check (lanes_bwd >= 0),
  centre_turn     boolean not null,                -- a two-way centre turn lane
  turn_fwd        text[],                          -- each lane's turns, left to right as it travels ('left;through'), null: untagged
  turn_bwd        text[],
  lanes_source    text not null check (lanes_source in ('osm', 'itd_hpms', 'achd_msm', 'osm_valley',
                                                         'compass_centerline', 'default')),
  lanes_conf      real,
  lane_w_m        real not null check (lane_w_m > 0),
  bike_l_m        real not null default 0,
  bike_r_m        real not null default 0,
  park_l_m        real not null default 0,
  park_r_m        real not null default 0,
  shoulder_l_m    real not null default 0,         -- a shoulder, or a curbed road's gutter
  shoulder_r_m    real not null default 0,
  edge_l          text not null check (edge_l in ('curb', 'shoulder')),
  edge_r          text not null check (edge_r in ('curb', 'shoulder')),
  median_kind     text check (median_kind in ('curbed', 'barrier', 'unprotected')),
  median_w_m      real not null default 0,
  width_left_m    real not null check (width_left_m > 0),   -- centreline to the left edge
  width_right_m   real not null check (width_right_m > 0),
  total_w_m       real not null check (total_w_m > 0),
  width_tier      text not null check (width_tier in ('inventoried', 'measured', 'counted', 'estimated')),
  width_source    text not null,                   -- achd_bike_network, osm_width, itd_hpms, lanes, class_default
  material        text not null check (material in ('asphalt', 'concrete', 'gravel', 'dirt', 'unknown')),
  material_source text check (material_source in ('surface', 'default')),
  markings        boolean not null,                -- lane lines drawn: only where a source gives the lane count
  sources         jsonb not null,                  -- every component's source: {"lanes": "achd_msm", "width": ...}
  republish       text not null check (republish in ('yes', 'internal')),   -- internal: an ACHD or ITD input
  flags           text[] not null default '{}',
  check ((material = 'unknown') = (material_source is null))
);

comment on table roads.xsection is
  'Real-width roads: each piece''s lanes and widths, with every component''s source. License ODbL with ACHD''s and ITD''s layers (none stated); republish: internal (per row: republish)';

-- Where pieces meet: one or more nodes of three or more piece ends, clustered (divided roads' crossings,
-- roundabouts). Its closing makes the curb returns.
create table roads.junction (
  id              int primary key,
  kind            text not null check (kind in ('signal', 'roundabout', 'interchange', 'plain')),
  nodes           smallint not null,
  pieces          int[] not null,
  radius_m        real not null,                   -- the curb-return radius of its closing; 0: none (interchanges)
  intersection_id bigint,                          -- core.intersection, at signals
  geom            geometry(Point, 32611) not null  -- the centre of its nodes
);
create index junction_geom on roads.junction using gist (geom);

comment on table roads.junction is
  'Real-width roads: junctions (roads-build). License ODbL (© OpenStreetMap contributors); republish: internal (built with ACHD''s and ITD''s widths)';

-- Surfaces: a piece's carriageway (or its deck on a bridge, or a median strip inside it), a junction's
-- curb-return fill (what its closing adds outside its pieces' carriageways), and islands (found from the
-- road graph's small enclosed faces and roundabouts' centres). Carriageways overlap where they meet: draw
-- them as one opaque fill, and the edges from roads.edge.
create table roads.surface (
  id              int primary key,
  kind            text not null check (kind in ('carriageway', 'junction', 'deck', 'median', 'island')),
  piece_id        int,                             -- roads.piece
  junction_id     int,                             -- roads.junction
  material        text not null check (material in ('asphalt', 'concrete', 'gravel', 'dirt', 'unknown')),
  tier            text not null check (tier in ('inventoried', 'measured', 'counted', 'estimated')),
  layer           smallint not null default 0,
  geom            geometry(MultiPolygon, 32611) not null,
  geom_z15        geometry(MultiPolygon, 32611),   -- generalised for z15 (0.5 m); null where it's too small to show
  check ((kind in ('carriageway', 'deck', 'median')) = (piece_id is not null)),
  check (kind <> 'junction' or junction_id is not null)
);
create index surface_geom on roads.surface using gist (geom);
create index surface_piece on roads.surface (piece_id);
create index surface_junction on roads.surface (junction_id);

comment on table roads.surface is
  'Real-width roads: surfaces (roads-build). License ODbL (© OpenStreetMap contributors) with ACHD''s and ITD''s widths (none stated); republish: internal';

-- The surfaces' outer edges, without the seams where surfaces meet: curbs, unkerbed pavement edges, deck
-- sides and island curbs. tier: the width's certainty, so the app can draw a crisp curb only where it's known.
create table roads.edge (
  id              int primary key,
  kind            text not null check (kind in ('curb', 'shoulder', 'deck', 'island')),
  tier            text not null check (tier in ('inventoried', 'measured', 'counted', 'estimated')),
  layer           smallint not null default 0,
  piece_id        int,                             -- roads.piece
  junction_id     int,                             -- roads.junction
  geom            geometry(MultiLineString, 32611) not null
);
create index edge_geom on roads.edge using gist (geom);
create index edge_piece on roads.edge (piece_id);

comment on table roads.edge is
  'Real-width roads: surface edges (roads-build). License ODbL (© OpenStreetMap contributors) with ACHD''s and ITD''s widths (none stated); republish: internal';

-- Markings: lane, centre, edge and bike-lane lines (offset from the centreline; only on pieces whose lane
-- count comes from a source), trimmed 1 m back from junctions and crosswalks; stop bars on signal approaches;
-- crosswalks (polygons) on marked crossings only.
create table roads.marking (
  id              int primary key,
  kind            text not null check (kind in ('edge', 'lane', 'centre_double', 'twltl', 'bike', 'stop_bar',
                                                'crosswalk')),
  dash            text not null check (dash in ('solid', 'dashed', 'double', 'solid_dashed')),
  piece_id        int,                             -- roads.piece
  junction_id     int,                             -- roads.junction
  node_osm_id     bigint,                          -- a crosswalk's crossing node (roads.osm_walk_node)
  geom            geometry(Geometry, 32611) not null,
  check ((kind = 'crosswalk') = (GeometryType(geom) in ('POLYGON', 'MULTIPOLYGON'))),
  check (kind = 'crosswalk' or GeometryType(geom) in ('LINESTRING', 'MULTILINESTRING'))
);
create index marking_geom on roads.marking using gist (geom);
create index marking_piece on roads.marking (piece_id);

comment on table roads.marking is
  'Real-width roads: markings and crosswalks (roads-build). License ODbL (© OpenStreetMap contributors) with ACHD''s and ITD''s lane counts (none stated); republish: internal';

-- Turn arrows from turn:lanes: one per lane with turns, ahead of where its lane lines stop.
create table roads.arrow (
  id              int primary key,
  piece_id        int not null,                    -- roads.piece
  direction       text not null check (direction in ('forward', 'backward')),
  lane            smallint not null,               -- from 1 at the left as it travels
  turns           text[] not null,
  bearing         real not null,                   -- degrees clockwise from grid north, the way it travels
  geom            geometry(Point, 32611) not null
);
create index arrow_geom on roads.arrow using gist (geom);

comment on table roads.arrow is
  'Real-width roads: turn arrows (roads-build). License ODbL (© OpenStreetMap contributors); republish: internal (placed with ACHD''s and ITD''s widths)';

-- The mismatch review list: where the sources disagree or a rule couldn't be applied cleanly. Never silent
-- (the design's rule): each row names the piece (and its way and ACHD segment) and what disagreed.
create table roads.review (
  id              int primary key,
  kind            text not null,                   -- lanes_conflict, direction, other_direction_assumed, components_exceed,
                                                   -- sidewalk_close, unmatched, deck_mismatch, turn_slots, junction_large,
                                                   -- geometry, bike_other_carriageway
  piece_id        int,                             -- roads.piece
  junction_id     int,                             -- roads.junction
  osm_id          bigint,
  road_segment_id bigint,
  detail          jsonb not null default '{}',
  geom            geometry(Point, 32611)
);
create index review_kind on roads.review (kind);
create index review_piece on roads.review (piece_id);

comment on table roads.review is
  'Real-width roads: the mismatch review list (roads-build). License ODbL (© OpenStreetMap contributors) with ACHD''s and ITD''s values (none stated); republish: internal';
