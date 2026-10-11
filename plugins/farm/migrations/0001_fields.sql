-- farm 0001: crop fields (landscape sprint, Oct 2026: package P3-data; decisions 14-15).
--
-- Every farm field in the map box as an "estimated field": USDA NASS's Crop Sequence Boundaries (CSB), one outline
-- per field with a crop code per year (eight years per edition), joined with the Cropland Data Layer (CDL) for how
-- sure USDA is, with Sentinel-2 for the field's state in July, and with COMPASS's permits and plats for growth.
-- Public domain (CSB, CDL), Copernicus (Sentinel-2) and COMPASS's none-stated data with republish yes
-- (development's sources), so everything here may be republished. CSB names no owners; it is never joined to the
-- Assessor's parcels in anything public. Each table's licence, republish and credit are in its comment (decision C3);
-- farm.edition, farm.cdl_year and farm.build also record them per row, and core.layer_version per tile version.
--
-- Loads, by hand (plugins/farm/README.md):
--   farm-csb-load     an edition's GeoPackage into farm.edition and farm.field
--   farm-cdl-load     farm.crop_class (codes, names, groups, accuracy) and farm.cdl_year (the rasters)
--   farm-fields-load  a worker build's per-field stats (agreement, July state) into farm.field
-- Each then works out the fields' growth, plats and letters, rebuilds the z8-10 dissolves (farm.field_lo) and gives
-- the crop-fields tiles a new version (core.layer_version 'farm.crop_fields'), in one transaction.
--   farm-derive       that last step again, by hand, after COMPASS's permits or plats change (no new data of ours)
--
-- Naming: core's "fields" are gridded frames (ch. 15); here it's always farm.field or "crop fields".

create schema if not exists farm;

-- One CSB edition per row: the build log of the outlines.
create table farm.edition (
  edition        text primary key check (edition ~ '^csb-[0-9]{4}-[0-9]{4}(-[a-z0-9]+)?$'),  -- 'csb-2018-2025-rev23'
  first_year     smallint not null,
  last_year      smallint not null check (last_year >= first_year),
  published      date,                      -- NASS's release date, when known
  source_url     text,
  last_modified  timestamptz,               -- the national file's Last-Modified
  file           text not null,             -- the GeoPackage loaded (path as the loader saw it)
  sha256         text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  loaded_at      timestamptz not null default now(),
  counts         jsonb not null default '{}',
  license        text not null,
  republish      text not null check (republish in ('yes', 'aggregates', 'internal', 'no')),
  credit         text not null
);

-- CDL class codes: NASS's names and colours, our crop groups, AgriMet's crops and NASS's Idaho accuracy.
create table farm.crop_class (
  code           smallint primary key check (code between 1 and 255),
  name           text not null,
  grp            text not null check (grp in ('corn', 'hay', 'grain', 'roots', 'specialty', 'pasture', 'fallow',
                                              'developed', 'other')),
  letter         text not null check (letter ~ '^[a-z-]$'),   -- the group's one-letter code (tiles' y string)
  nass_hex       text check (nass_hex ~ '^#[0-9A-Fa-f]{6}$'),
  agrimet        text[] not null default '{}',     -- AgriMet crops for its water use, e.g. {ALFP,ALFM} (ours ⚠️)
  accuracy       jsonb                              -- {"state": "ID", "year": 2025, "producer": 0.855, "user": 0.798, ...}
);

-- The CDL rasters the builds read, copied into $TVT_ARCHIVE/farm/cdl/ (inputs, never tiles).
create table farm.cdl_year (
  year           smallint primary key,
  res_m          real not null,
  method         text not null,              -- '30m' (NASS's Landsat-era product) or '10m-2024' (the new method)
  path           text not null,              -- relative to $TVT_ARCHIVE
  bytes          bigint not null,
  sha256         text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  license        text not null,
  republish      text not null check (republish in ('yes', 'aggregates', 'internal', 'no')),
  credit         text not null,
  loaded_at      timestamptz not null default now()
);

-- Crop-fields builds (plugins/farm/build/build.py in the worker image), as loaded by farm-fields-load.
create table farm.build (
  build_id       text primary key,
  edition        text not null references farm.edition,
  started_at     timestamptz,
  finished_at    timestamptz,
  loaded_at      timestamptz not null default now(),
  params         jsonb not null default '{}',
  inputs         jsonb not null default '{}',      -- each input's path and sha256
  counts         jsonb not null default '{}',
  license        text not null,
  republish      text not null check (republish in ('yes', 'aggregates', 'internal', 'no')),
  credit         text not null
);

-- One CSB field. Fields that a newer edition no longer has stay, closed (valid_to): they're the farmland-loss record.
create table farm.field (
  field_id       text primary key,           -- CSBID: state FIPS, the window's years, a sequence number
  id             integer generated always as identity unique,   -- the tiles' feature id (feature-state, hover)
  edition        text not null references farm.edition,
  geom           geometry(MultiPolygon, 4326) not null,         -- made valid; NAD83 taken as WGS 84 (the null shift)
  label_pt       geometry(Point, 4326),      -- CSB's interior point
  acres          real,
  state_fips     text,
  county_fips    text,
  county         text,
  asd            text,                       -- NASS agricultural statistics district
  first_year     smallint not null,
  crops          smallint[] not null,        -- the CDL code per year, first_year on (0 = none)
  letters        text,                       -- one letter per year: the crop group (crop_class.letter)
  group_now      text,                       -- the newest year's crop group (crop_class.grp)
  bearing        real check (bearing >= 0 and bearing < 180),   -- the long axis, degrees clockwise from grid north (EPSG:32611)
  agree          jsonb,                      -- per CDL year held: the share of the field's pixels with its code
  july           jsonb,                      -- {"year": 2025, "ndvi": 0.85, "state": "green", "px": 120}
  build_id       text references farm.build, -- the build whose agree and july these are
  growth         text check (growth in ('farmed', 'built_over', 'being_built')),
  growth_detail  jsonb,                      -- the rule, the first developed year ("by"), permits, ... (as of the last derive)
  plat           jsonb,                      -- COMPASS plats over it: shares by status, the largest few (as of the last derive)
  valid_from     date not null,              -- the edition's release (or load) date
  valid_to       date,                       -- set when a newer edition no longer has the field
  successor      text[]                      -- the newer edition's fields covering most of it
);
create index field_geom on farm.field using gist (geom);
create index field_current on farm.field (group_now) where valid_to is null;
create index field_growth on farm.field (growth) where valid_to is null;
create index field_edition on farm.field (edition);

-- The z8-10 generalisation: current fields dissolved by crop group per year (and by growth state), closed and
-- simplified at each zoom's pixel (512 px tiles), cut to that zoom's tile grid. Web Mercator, so cuts don't transform.
create table farm.field_lo (
  z              smallint not null check (z between 0 and 12),
  x              integer not null,
  y              integer not null,
  yr             smallint,                   -- the crop year, or null for a growth row
  key            text not null,              -- a crop group, or built_over | being_built | plat
  now            boolean not null,           -- the current crop year's rows and the growth rows
  geom           geometry(MultiPolygon, 3857) not null
);
create index field_lo_geom on farm.field_lo using gist (geom);
create index field_lo_z on farm.field_lo (z, now);

-- The crop year the map shows: the newest year of the newest edition loaded, "2025 (USDA's newest)" (decision 14).
-- It moves on by itself when the next edition is loaded; a crop is never guessed for a year USDA hasn't published.
create view farm.crop_year as
select e.last_year as year, e.last_year || ' (USDA''s newest)' as label, e.edition, e.first_year
from farm.edition e
order by e.last_year desc, e.loaded_at desc
limit 1;

-- What the crop-fields tiles read (/api/farm/tiles/crop_fields, package P3-app; app/src/lib/server/mvt.ts).
-- z11 on: one feature per current field. a acres, g the crop group now, n the crop's name now (NASS's, for labels),
-- y one letter per year (first_year on), s growth, st the July state, p true when it's still farmed (a crop, fallow
-- or pasture in the newest year) and at least half under an approved or recorded plat.
create view farm.crop_fields as
select f.id, round(f.acres)::int as a, f.group_now as g, c.name as n, f.letters as y, f.growth as s,
       f.july ->> 'state' as st,
       coalesce(f.group_now in ('corn', 'hay', 'grain', 'roots', 'specialty', 'pasture', 'fallow')
                and (f.plat ->> 'approved')::real >= 0.5, false) as p, f.geom
from farm.field f
left join farm.crop_class c on c.code = f.crops[cardinality(f.crops)]
where f.valid_to is null;

-- z8-10: the dissolves of the current crop year (g) and the growth states (s). farm.field_lo also holds every
-- other year's dissolves (yr), for a year switcher's own cut per year: one year is about the size of these (75 KB at
-- the densest z10 tile on Oct 11), all eight together about 630 KB, too much for one tile.
create view farm.crop_fields_lo8 as
select case when yr is null then null else key end as g, case when yr is null then key end as s, geom
from farm.field_lo where z = 8 and now;
create view farm.crop_fields_lo9 as
select case when yr is null then null else key end as g, case when yr is null then key end as s, geom
from farm.field_lo where z = 9 and now;
create view farm.crop_fields_lo10 as
select case when yr is null then null else key end as g, case when yr is null then key end as s, geom
from farm.field_lo where z = 10 and now;

comment on schema farm is
  'Farms and crops. Crop fields: USDA NASS Crop Sequence Boundaries and Cropland Data Layer (public domain), '
  'Copernicus Sentinel-2 (Copernicus licence), COMPASS permits and plats (none stated; development: republish yes). '
  'Republish yes throughout; each table''s comment names its own';
comment on table farm.edition is
  'CSB editions loaded. Public domain; republish yes; credit USDA NASS Crop Sequence Boundaries <first>-<last> '
  '(per row)';
comment on table farm.crop_class is
  'CDL class codes: NASS''s names and colours, NASS''s Idaho accuracy, our crop groups and AgriMet crops. Public '
  'domain (USDA NASS Cropland Data Layer legend and accuracy); republish yes; credit USDA NASS Cropland Data Layer';
comment on table farm.cdl_year is
  'The CDL rasters the builds read (inputs, never tiles). Public domain; republish yes; credit USDA NASS Cropland '
  'Data Layer <year> (per row)';
comment on table farm.build is
  'Crop-fields builds loaded (agreement, July state, crop_cover.tif). Public domain (CSB, CDL) and Copernicus '
  '(Sentinel-2); republish yes; credit per row, with the July NDVI''s own year';
comment on table farm.field is
  'Crop fields: estimated outlines with eight years of crops (USDA NASS CSB, public domain), CDL agreement (public '
  'domain), July state (Copernicus Sentinel-2), growth and plats (COMPASS permits and plats, none stated); republish '
  'yes; credit USDA NASS Crop Sequence Boundaries and Cropland Data Layer, Contains modified Copernicus Sentinel '
  'data <july.year>, COMPASS. growth, growth_detail and plat are as of the last load or farm-derive';
comment on table farm.field_lo is
  'Crop fields dissolved by group (per year) and growth state for z8-10 tiles, cut to each zoom''s tile grid '
  '(EPSG:3857). From farm.field: public domain (CSB) and COMPASS (growth, plats; none stated); republish yes; credit '
  'as the tiles'' core.layer_version row';
comment on view farm.crop_year is
  'The crop year the map shows: the newest year of the newest CSB edition loaded (public domain; republish yes)';
comment on view farm.crop_fields is
  'Crop-fields tiles, z11 on (one feature per current field). Licence, republish and credit: core.layer_version '
  '''farm.crop_fields''';
comment on view farm.crop_fields_lo8 is
  'Crop-fields tiles, z8 (dissolves). Licence, republish and credit: core.layer_version ''farm.crop_fields''';
comment on view farm.crop_fields_lo9 is
  'Crop-fields tiles, z9 (dissolves). Licence, republish and credit: core.layer_version ''farm.crop_fields''';
comment on view farm.crop_fields_lo10 is
  'Crop-fields tiles, z10 (dissolves). Licence, republish and credit: core.layer_version ''farm.crop_fields''';
