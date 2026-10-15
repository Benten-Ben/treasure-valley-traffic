-- water 0001: the valley's water network (landscape sprint, Oct 2026: package P4-data; the water design, decisions
-- 17 and 19).
--
-- One network for the map: OpenStreetMap's geometry carrying NHD's facts, NHD-only pieces kept lighter, canals with
-- their topology and gauges. Three kinds of table, each with its own licence:
--   inputs, as each source has it, replaced or versioned by their loads:
--     water.nhd_*            USGS NHD HU4 1705 (public domain), replaced by each `nhd-load`;
--     water.hydroshare_canal the HydroShare canal network (CC BY 4.0, cite its DOI), replaced by `hydroshare-load`;
--     water.osm_feature      OpenStreetMap's water (ODbL), the osm_waterways consumer of core's loader, versioned
--                            in place (plan C2: no raw.record copies);
--     water.idwr_*           IDWR's irrigation organizations and season of use: no licence stated, so INTERNAL.
--                            Never in an export, a base tile or a public view; the Owner field is never fetched;
--   drawn tables, rebuilt by each `water-build` (water.build): reach, body, structure, canal, reach_link,
--     reach_evidence, gauge. They carry OSM's geometry, so they are ODbL (credit both sources, and HydroShare where
--     its names are used); republish yes;
--   side tables a card reads, rebuilt by water-build: water.canal_org and water.canal_season, from IDWR: INTERNAL.
--
-- Geometry is EPSG:4326. NHD is NAD83 (EPSG:4269), read with the null datum shift, as the ground does
-- (basemap/ground/README.md, "Datum policy"): NAD83 coordinates are taken as WGS 84's (about 1 m here ⚠️).
--
-- Evidence is kept in water.reach_evidence, not core.source_link: that table's key allows one entity per source
-- record, and one NHD flowline runs along several OpenStreetMap ways.

create schema if not exists water;

-- ---- loads of the files we hold ------------------------------------------------------------------------------

create table water.load (
  id          bigint generated always as identity primary key,
  source      text not null references ops.source,           -- 'nhd_hr' or 'hydroshare_canals'
  file        text not null,                                  -- the prepared file's name
  sha256      text not null,
  prepared    jsonb not null default '{}',                    -- prepare.json: the input's sha256, counts, product date
  counts      jsonb not null default '{}',
  loaded_at   timestamptz not null default now(),
  fetch_id    bigint references ops.fetch
);

-- ---- NHD HU4 1705 (USGS, public domain) -----------------------------------------------------------------------

create table water.nhd_flowline (
  permanent_identifier  text primary key,
  reachcode             text,
  gnis_id               text,
  gnis_name             text,
  ftype                 smallint,
  fcode                 integer,
  class                 text not null check (class in ('stream_river', 'canal_ditch', 'pipeline', 'artificial_path',
                                                          'connector', 'underground_conduit', 'other')),
  hydrographiccategory  text,                  -- Perennial, Intermittent, Ephemeral, or null
  canalditchtype        text,                  -- Aqueduct, Stormwater, ...
  pipelinetype          text,                  -- Siphon, ...
  relationshiptosurface text,
  flowdir               smallint,              -- 1 with digitized (drawn downstream), 0 uninitialized
  streamorder           smallint,              -- Strahler (NHDFlowlineVAA)
  startflag             smallint,
  terminalflag          smallint,
  divergenceflag        smallint,
  visibilityfilter      integer,               -- the scale NHD keeps it at: 1000000 = 1:1M, ...
  wbarea_permanent_identifier text,            -- the waterbody or area an artificial path runs through
  fdate                 timestamptz,
  lengthkm              real,
  geom                  geometry(MultiLineString, 4326) not null,
  load_id               bigint not null references water.load
);
create index nhd_flowline_geom on water.nhd_flowline using gist (geom);

-- NHDWaterbody (layer 'waterbody') and NHDArea (layer 'area').
create table water.nhd_polygon (
  permanent_identifier  text primary key,
  layer                 text not null check (layer in ('waterbody', 'area')),
  reachcode             text,
  gnis_id               text,
  gnis_name             text,
  ftype                 smallint,
  fcode                 integer,
  ftype_name            text,                  -- 'Lake/Pond', 'Reservoir', 'SwampMarsh', 'StreamRiver', ...
  hydrographiccategory  text,
  reservoirtype         text,
  visibilityfilter      integer,
  areasqkm              real,
  fdate                 timestamptz,
  geom                  geometry(MultiPolygon, 4326) not null,
  load_id               bigint not null references water.load
);
create index nhd_polygon_geom on water.nhd_polygon using gist (geom);

-- NHDLine: dams and weirs, flumes, tunnels, shorelines.
create table water.nhd_line (
  permanent_identifier  text primary key,
  gnis_name             text,
  ftype                 smallint,
  fcode                 integer,
  ftype_name            text,
  geom                  geometry(MultiLineString, 4326) not null,
  load_id               bigint not null references water.load
);

-- NHDPoint (springs and seeps, waterfalls, wells, gaging stations, ...) and NHDPointEventFC (layer 'event':
-- streamgages, dams, ... on the network).
create table water.nhd_point (
  permanent_identifier  text primary key,
  layer                 text not null check (layer in ('point', 'event')),
  gnis_name             text,
  ftype                 smallint,
  fcode                 integer,
  ftype_name            text,
  eventtype             integer,
  reachcode             text,
  source_featureid      text,                  -- e.g. a USGS streamgage's id (events)
  geom                  geometry(Point, 4326) not null,
  load_id               bigint not null references water.load
);
create index nhd_point_geom on water.nhd_point using gist (geom);

-- NHDFlow: what each flowline flows into (the rows touching the kept flowlines).
create table water.nhd_flow (
  from_pid    text not null,
  to_pid      text not null,
  direction   smallint,
  deltalevel  smallint,
  load_id     bigint not null references water.load,
  primary key (from_pid, to_pid)
);
create index nhd_flow_to on water.nhd_flow (to_pid);

-- ---- the HydroShare canal network (CC BY 4.0) -----------------------------------------------------------------

create table water.hydroshare_canal (
  id          integer primary key,               -- the shapefile's record number (0-based)
  call_number text,                              -- 'Call_Numbe' ('N1', ...)
  name        text,
  type        text,                              -- Canal, Lateral, Drain, Creek, ...
  geom        geometry(MultiLineString, 4326) not null,
  load_id     bigint not null references water.load
);
create index hydroshare_canal_geom on water.hydroshare_canal using gist (geom);

-- ---- OpenStreetMap's water (ODbL), the osm_waterways consumer --------------------------------------------------

-- A closed way can come as a line and as an area (a riverbank, a dam), so the key includes the shape.
create table water.osm_feature (
  osm_type       text not null check (osm_type in ('n', 'w', 'r')),
  osm_id         bigint not null,
  shape          text not null check (shape in ('point', 'line', 'area')),
  kind           text not null,                  -- plugins/water/ingest/sources/osm_waterways.py KINDS
  name           text,
  intermittent   boolean,                        -- intermittent=yes or seasonal=yes; null when untagged
  piped          boolean not null default false, -- tunnel=*, covered=yes, location=underground, waterway=pressurised
  width_m        real,                           -- the width tag in metres, when it reads as one
  layer          smallint,
  tags           jsonb not null,                 -- every tag, as tagged
  geom           geometry(Geometry, 4326) not null,
  osm_version    int,
  osm_timestamp  timestamptz,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  primary key (osm_type, osm_id, shape)
);
create index osm_feature_geom on water.osm_feature using gist (geom);
create index osm_feature_kind on water.osm_feature (shape, kind) where active;

-- ---- IDWR (no licence stated): INTERNAL --------------------------------------------------------------------------

-- Irrigation organizations' service areas: where each can deliver its water rights (not where it irrigates). The
-- layer's Owner field is never fetched or stored.
create table water.idwr_org (
  objectid      integer primary key,
  name          text not null,
  place_of_use  double precision,               -- PlaceOfUse: -999 a combination of rights, 0 none (I.C. Title 43)
  lpou          boolean,                        -- a Large Place of Use (I.C. 42-202B(2))
  process       text,
  acres         double precision,
  geom          geometry(MultiPolygon, 4326) not null,
  fetched_at    timestamptz not null
);
create index idwr_org_geom on water.idwr_org using gist (geom);

-- The legal irrigation season's zones (45 °F threshold): the season water may be appropriated in, not delivery dates.
create table water.idwr_season (
  objectid      integer primary key,
  season        text,
  spring        text,
  fall          text,
  start_month   smallint check (start_month between 1 and 12),
  start_day     smallint check (start_day between 1 and 31),
  end_month     smallint check (end_month between 1 and 12),
  end_day       smallint check (end_day between 1 and 31),
  geom          geometry(MultiPolygon, 4326) not null,
  fetched_at    timestamptz not null
);
create index idwr_season_geom on water.idwr_season using gist (geom);

-- ---- the drawn network, rebuilt by water-build ------------------------------------------------------------------

create table water.build (
  id           bigint generated always as identity primary key,
  started_at   timestamptz not null default clock_timestamp(),
  finished_at  timestamptz,
  inputs       jsonb not null default '{}',     -- each input's load: NHD and HydroShare sha256, the OSM extract's MD5
  settings     jsonb not null default '{}',     -- the build's thresholds and tables
  counts       jsonb not null default '{}',
  note         text
);

-- A drawn line: an OpenStreetMap way (geometry_from 'osm'), or a run of an NHD flowline OpenStreetMap lacks
-- ('nhd'). Ids are stable across builds (the canal season's feature-state): an OSM way's id is its own; an NHD
-- run's is 2^51 plus a 50-bit hash of its flowline and its place along it.
create table water.reach (
  id               bigint primary key check (id between 0 and 9007199254740991),
  kind             text not null check (kind in ('river', 'stream', 'canal', 'lateral', 'ditch', 'drain')),
  name             text,
  name_from        text check (name_from in ('osm', 'nhd', 'hydroshare')),
  intermittent     boolean not null default false,
  flow             text not null default 'unknown' check (flow in ('perennial', 'intermittent', 'ephemeral',
                                                                   'unknown')),
  piped            boolean not null default false,
  width_m          real not null check (width_m > 0),
  width_from       text not null check (width_from in ('osm_tag', 'order', 'kind', 'measured')),
  stream_order     smallint,
  minzoom          smallint not null check (minzoom between 0 and 22),
  geometry_from    text not null check (geometry_from in ('osm', 'nhd')),
  confirmed        boolean not null default false,  -- OSM and NHD agree on it (half its length within 20 m)
  osm_id           bigint,
  nhd_pid          text,                            -- the NHD flowline whose facts it carries, or whose run it is
  reachcode        text,
  canal_id         bigint,                          -- water.canal.id
  dist_from_head_m real,                            -- along its canal, from the canal's head
  flow_known       boolean not null default false,  -- drawn downstream: OSM's convention, NHD's flowdir 1
  length_m         real not null,
  geom             geometry(LineString, 4326) not null,
  build_id         bigint not null references water.build
);
create index reach_geom on water.reach using gist (geom);
create index reach_canal on water.reach (canal_id);

-- Which reach flows into which, as drawn (OpenStreetMap draws waterways downstream; NHD's flowdir 1 says the same):
-- 'end' (one's end is the other's start), 'branch' (the other starts on it: a lateral leaving its canal), 'joins'
-- (it ends on the other: a drain or creek running into a canal or river), 'nhdflow' (NHD's own connectivity between
-- NHD-only runs). at_m: how far along from_reach the water leaves it.
create table water.reach_link (
  from_reach  bigint not null,
  to_reach    bigint not null,
  method      text not null check (method in ('end', 'branch', 'joins', 'nhdflow')),
  gap_m       real,
  at_m        real,
  primary key (from_reach, to_reach)
);
create index reach_link_to on water.reach_link (to_reach);

-- How we know each reach: its geometry's source and every other source that agrees with it.
create table water.reach_evidence (
  reach_id    bigint not null,
  source      text not null check (source in ('osm_waterways', 'nhd_hr', 'hydroshare_canals')),
  source_id   text not null,                  -- 'w123' (OSM), a permanent identifier (NHD), a call number (HydroShare)
  role        text not null check (role in ('geometry', 'attributes', 'agrees', 'name')),
  share       real check (share between 0 and 1),   -- the share of the reach's length within 20 m of it
  distance_m  real,                                  -- the median distance, for 'agrees' and 'attributes'
  primary key (reach_id, source, source_id)
);

-- A drawn area. Ids: an OSM way's 2 x id, a relation's 2 x id + 1 (osmium's area ids); NHD-only 2^51 + a hash.
create table water.body (
  id             bigint primary key check (id between 0 and 9007199254740991),
  kind           text not null check (kind in ('lake', 'reservoir', 'pond', 'river', 'canal', 'basin', 'wastewater',
                                               'wetland', 'pool', 'water', 'dock')),
  name           text,
  intermittent   boolean not null default false,
  area_m2        real not null,
  minzoom        smallint not null check (minzoom between 0 and 22),
  geometry_from  text not null check (geometry_from in ('osm', 'nhd')),
  confirmed      boolean not null default false,   -- NHD and OSM overlap over half of it
  osm_type       text,
  osm_id         bigint,
  nhd_pid        text,
  gauge_lid      text,
  geom           geometry(MultiPolygon, 4326) not null,
  build_id       bigint not null references water.build
);
create index body_geom on water.body using gist (geom);

create table water.structure (
  id          bigint primary key check (id between 0 and 9007199254740991),
  kind        text not null check (kind in ('dam', 'weir', 'lock_gate', 'sluice_gate', 'waterfall', 'spring',
                                            'gauge')),
  name        text,
  source      text not null check (source in ('osm_waterways', 'nhd_hr', 'nwps_gauges')),
  source_id   text not null,
  reach_id    bigint,                             -- the reach it sits on (within 30 m)
  gauge_lid   text,
  minzoom     smallint not null check (minzoom between 0 and 22),
  geom        geometry(Point, 4326) not null,
  build_id    bigint not null references water.build
);
create index structure_geom on water.structure using gist (geom);

-- One row per named canal (its connected reaches of one name). Its id is its lowest reach id.
create table water.canal (
  id                 bigint primary key,
  name               text not null,
  kind               text not null check (kind in ('main_canal', 'canal', 'lateral', 'ditch', 'drain')),
  length_m           real not null,
  piped_m            real not null default 0,
  reaches            integer not null,
  head_reach_id      bigint,
  head_structure_id  bigint,
  source_kind        text not null default 'unknown' check (source_kind in ('river', 'canal', 'reservoir', 'unknown')),
  source_reach_id    bigint,                       -- the river or canal reach it leaves
  source_canal_id    bigint,
  gauge_lid          text,
  sources            text[] not null,              -- {'osm_waterways', 'nhd_hr', 'hydroshare_canals'}
  build_id           bigint not null references water.build
);

-- NWPS gauges in the box and what each measures.
create table water.gauge (
  lid         text primary key,
  name        text not null,
  reach_id    bigint,
  body_id     bigint,
  canal_id    bigint,
  method      text not null check (method in ('name', 'nearest', 'none')),
  distance_m  real,
  geom        geometry(Point, 4326) not null,
  build_id    bigint not null references water.build
);

-- INTERNAL (IDWR): the irrigation organizations whose service areas a canal runs through, by share of its length.
-- A service area is where an organization may deliver its water rights; it doesn't say who runs the canal, and the
-- card says so.
create table water.canal_org (
  canal_id   bigint not null,
  objectid   integer not null,                  -- water.idwr_org.objectid
  name       text not null,
  share      real not null check (share between 0 and 1),
  at_head    boolean not null default false,    -- the canal's head lies in it
  build_id   bigint not null references water.build,
  primary key (canal_id, objectid)
);

-- INTERNAL (IDWR): the legal season of use at each canal's head (not delivery dates).
create table water.canal_season (
  canal_id     bigint primary key,
  objectid     integer not null,                -- water.idwr_season.objectid
  season       text,
  start_month  smallint,
  start_day    smallint,
  end_month    smallint,
  end_day      smallint,
  build_id     bigint not null references water.build
);

comment on schema water is
  'Hydrography. nhd_* public domain; hydroshare_canal CC BY 4.0; osm_feature and the drawn tables ODbL (republish yes, credit both); idwr_*, canal_org and canal_season INTERNAL (IDWR, no licence stated)';
comment on table water.osm_feature is
  'OpenStreetMap''s water (osm_waterways consumer). License ODbL (© OpenStreetMap contributors); republish: yes';
comment on table water.idwr_org is
  'IDWR irrigation organizations (service areas), without the Owner field. No licence stated: INTERNAL, credit IDWR';
comment on table water.idwr_season is
  'IDWR season of use (the legal irrigation season, not delivery dates). No licence stated: INTERNAL, credit IDWR';
comment on table water.canal_org is 'From IDWR: INTERNAL, cards only, never exported or tiled';
comment on table water.canal_season is 'From IDWR: INTERNAL, cards only, never exported or tiled';
