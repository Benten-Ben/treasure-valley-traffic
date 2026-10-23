-- water 0004: vegetated wetlands (landscape sprint, Oct 2026: issue #309; the owner's answer 2 of Oct 22, the
-- end-of-wave-1 decisions; the wetlands review).
--
-- Inputs, as the National Wetlands Inventory has them (U.S. Fish and Wildlife Service, public domain, republish yes,
-- credit "U.S. Fish and Wildlife Service, National Wetlands Inventory"; kept apart from the ODbL drawn tables, as
-- NHD's copies are):
--   water.nwi_project   the mapping projects (the image year and source of each stretch of the map);
--   water.nwi_wetland   the vegetated palustrine wetlands (emergent, scrub-shrub, forested) and nothing else: NWI's
--                       ponds, lakes and riverine polygons are not drawn (Water's bodies and reaches cover them);
--   water.nwi_presence  the presence check's five shares for the polygons mapped from 1981-83 photos or the interim
--                       product, written by the worker step and loaded by `nwi-presence`.
-- Drawn: water.body gains the wetland columns (a wetland is a body of kind 'wetland'), and water.wetland_check keeps
-- every NWI polygon's outcome in each build, the retired ones included, with the reason and the shares (the QA
-- sheet's rows). Both are rebuilt by each water-build.
--
-- A wetland drawn from NWI alone is geometry_from 'nwi'; where OSM also outlines it, OSM's outline is drawn
-- (geometry_from 'osm') with NWI's class and regime. NWI is not a legal (regulatory) wetland boundary, and the card
-- says so.

create table water.nwi_project (
  id           bigint generated always as identity primary key,
  load_id      bigint not null references water.load,
  hu8          text,
  name         text not null,
  image_year   smallint,                     -- null for the interim "Scalable" product
  image_date   text,                         -- '07/81' as published
  image_scale  integer,
  source_type  text,                         -- 'CIR', 'TC', 'Scalable'
  geom         geometry(MultiPolygon, 4326) not null
);
create index nwi_project_geom on water.nwi_project using gist (geom);

create table water.nwi_wetland (
  key           text primary key,            -- NWI_ID, with '#2', '#3' for the further parts of a shared NWI_ID
  nwi_id        text not null,
  attribute     text not null,               -- the Cowardin code, e.g. 'PEM1C'
  wetland_type  text,                        -- FWS's plain group
  acres         real,
  hu8           text,
  project       text,                        -- the mapping project whose polygon holds its point
  image_year    smallint,
  era           text not null check (era in ('recent', 'old', 'interim', 'unknown')),
                                             -- recent: mapped from 1999 or later imagery; old: 1981 or 1983 photos;
                                             -- interim: the "Scalable" product; unknown: no project polygon found
  geom          geometry(MultiPolygon, 4326) not null,
  load_id       bigint not null references water.load
);
create index nwi_wetland_geom on water.nwi_wetland using gist (geom);

-- The presence check's inputs for one NWI polygon (shares of its area, 0 to 1), from the worker step.
create table water.nwi_presence (
  key              text primary key references water.nwi_wetland on delete cascade,
  built            real not null check (built between 0 and 1),         -- under roofs, roads and paving (mask v0)
  developed        real not null check (developed between 0 and 1),     -- CDL 122-124 in both 2024 and 2025
  cultivated       real not null check (cultivated between 0 and 1),    -- CSB fields cropped 6 of the 8 years 2018-2025
  hay_pasture      real not null check (hay_pasture between 0 and 1),   -- CSB fields in hay or pasture 4 of 8 years
  cdl_wetland      real not null check (cdl_wetland between 0 and 1),   -- CDL 190 or 195 in 2024 or 2025
  hydric           real check (hydric between 0 and 1),                 -- SSURGO hydric share: listed, decides nothing
  computed_on      date not null,
  inputs           jsonb not null default '{}'
);

-- The wetland columns of a drawn body. NWI-only wetlands are geometry_from 'nwi'.
alter table water.body drop constraint body_geometry_from_check;
alter table water.body add constraint body_geometry_from_check check (geometry_from in ('osm', 'nhd', 'nwi'));
alter table water.body
  add column wetland_class  text,            -- the Cowardin code of the NWI polygon behind it, if any
  add column water_regime   text,            -- the code's water regime letter
  add column modifiers      text,            -- the code's special modifiers (h, x, d, f, b, r, s)
  add column nwi_key        text,
  add column image_year     smallint,        -- NWI's mapping year
  add column thin           boolean not null default false,    -- the thinned tuft: older mapping (1981-83, interim,
                                                               -- or NHD's topo-era marsh alone)
  add column presence       text check (presence in ('kept', 'flagged')),
  add column presence_reason text check (presence_reason in ('hay_pasture', 'farmed_supported'));

create table water.wetland_check (
  key              text not null,
  build_id         bigint not null references water.build,
  era              text not null,
  presence         text not null check (presence in ('kept', 'flagged', 'retired', 'unchecked')),
  reason           text check (reason in ('built', 'farmed', 'farmed_supported', 'hay_pasture')),
  drawn            boolean not null,
  body_id          bigint,
  built            real,
  developed        real,
  cultivated       real,
  hay_pasture      real,
  cdl_wetland      real,
  support          text[] not null default '{}',   -- 'cdl', 'osm', 'nhd': what stood for a wetland here
  primary key (build_id, key)
);

comment on table water.nwi_wetland is
  'FWS National Wetlands Inventory, vegetated palustrine wetlands in the map box. Public domain; republish: yes; credit U.S. Fish and Wildlife Service, National Wetlands Inventory. Not a legal (regulatory) wetland boundary';
comment on table water.nwi_project is
  'NWI mapping projects (image year and source): public domain; republish: yes';
comment on table water.nwi_presence is
  'The presence check''s shares for old-mapped NWI polygons: derived from public inputs (mask v0, CDL, CSB); republish: yes';
comment on table water.wetland_check is
  'Every NWI polygon''s outcome in each water-build, retired ones included (the QA sheet''s rows). ODbL where OSM''s support counts; republish: yes';
