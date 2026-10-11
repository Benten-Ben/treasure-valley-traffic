-- Soils: the NRCS soil survey (SSURGO) for the map units touching the map box, the base of the soil card, the Soils
-- layer and the ground's soil types (landscape sprint, Oct 2026: package P1-data; plugins/soils/README.md).
--
-- Licence (plan C3): SSURGO is a U.S. government work in the public domain ("Access_Constraints: None"); its use
-- constraints ask for USDA NRCS credit and say it isn't meant for regulatory decisions. Every table here is public
-- domain, republish yes, credit "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)", and photo_stats adds
-- NAIP's (public domain, credit USDA NAIP). Each build records its own licence, republish and credit (soils.build).
--
-- Loaded by hand (`python3 -m ingest soils-load --from DIR`, from a folder plugins/soils/build/prepare.py wrote),
-- whole survey areas at a time: a reload replaces an area's rows when its saverest changed. Polygons are kept whole,
-- not clipped to the box.
create schema if not exists soils;

-- One load or photo-statistics run: what it read (each input's sha256), its settings and counts, and the licence of
-- what it wrote: the strictest of its inputs, in the plugin manifests' terms (docs/15 §15.2).
create table soils.build (
  build_id    text primary key,                       -- 'load-20261011T1015Z', 'photo-...'
  kind        text not null check (kind in ('load', 'photo')),
  started_at  timestamptz not null,
  finished_at timestamptz,
  params      jsonb not null default '{}',
  counts      jsonb not null default '{}',
  inputs      jsonb not null default '{}',            -- {file: sha256}
  license     text not null check (btrim(license) <> ''),
  republish   text not null check (republish in ('yes', 'aggregates', 'internal', 'no')),
  credit      text not null check (btrim(credit) <> '')
);

-- The survey areas loaded (10 touch the box: ID001 Ada, ID665 Canyon, ID659, ID660, ID675, ID683, ID685, OR641,
-- OR644, OR645). saverest is when NRCS established the area's version, on NRCS's clock: a reload replaces an area
-- only when it changed (or with --force). geom is the area's boundary (soilsa_a), whole; geom_lo is simplified by
-- 20 m for the layer's survey bounds at z8-11, which explain the seams at county lines.
create table soils.survey_area (
  areasymbol  text primary key,
  areaname    text not null,
  saverest    timestamp not null,
  saversion   int,
  scale       int,                                    -- 24000 = 1:24,000
  source_url  text,                                   -- its Web Soil Survey package
  geom        geometry(MultiPolygon, 4326) not null,
  geom_lo     geometry(MultiPolygon, 4326),
  build_id    text not null references soils.build,
  loaded_at   timestamptz not null default now()
);
create index survey_area_geom_lo_idx on soils.survey_area using gist (geom_lo);

-- Ground types: a map unit's dominant component (its series) and that component's surface texture with modifier,
-- e.g. 'purdam:silt-loam'. The ground's colours are measured per type (soils.photo_stats).
--   A miscellaneous area is one type by its name alone, whatever texture NRCS gives it: 'water', 'urban-land',
--   'rock-outcrop', 'pits', 'badland'. So is a soil with no surface texture ('xeric-torriorthents'). Tell
--   miscellaneous areas apart by misc, never by the id's shape:
--     water, urban, rock (Rock outcrop), badland, rubble (Rubble land), pits (Pits, Pits and Dumps), other (Marsh,
--     Riverwash, Playas, Dune land, Dumps, ...), and nodata: NRCS's NOTCOM, "No Digital Data Available", which is
--     no survey at all (4,250 ha of Malheur's OR645 in the box). Not a soil: the ground paints it from the photo or
--     flat, and the card says it isn't surveyed.
--   gid is the type's integer key, for rasters and files (the ground export's ground_type, P2's palette): 1 and up,
--   kept while the type exists and never reused (a type dropped and found again gets a new one). 0 means none.
create table soils.ground_type (
  id             text primary key,
  gid            smallint generated always as identity unique,
  series         text not null,                       -- 'Purdam'
  texture        text,                                -- 'Gravelly silt loam' (chtexturegrp.texdesc); null for misc
  texcl          text,                                -- 'Silt loam'
  modifier       text,                                -- 'Gravelly'
  misc           text check (misc in ('water', 'urban', 'rock', 'badland', 'rubble', 'pits', 'other', 'nodata')),
  frag_cover_pct real,       -- surface fragment cover, area-weighted over its map units that report it
  albedo_dry     real,       -- the dominant components' dry albedo (albedodry_r), area-weighted likewise
  n_mapunits     int not null default 0,
  area_ha        double precision not null default 0  -- inside the box
);

-- Map units touching the box, with NRCS's map-unit summary (muaggatt) and our derived fields.
create table soils.map_unit (
  mukey          text primary key,
  areasymbol     text not null references soils.survey_area on delete cascade,
  musym          text,
  muname         text,
  mukind         text,                                -- Consociation, Complex, Association, ...
  farmlndcl      text,
  -- muaggatt: dominant condition (dcd), dominant component (dcp), weighted average (wta), presence (prs, percent)
  slopegraddcp   real,                                -- percent
  aws025wta      real,                                -- available water storage, cm, 0-25 cm
  aws050wta      real,
  aws0100wta     real,
  drclassdcd     text,
  hydgrpdcd      text,
  flodfreqdcd    text,
  pondfreqprs    smallint,
  brockdepmin    int,                                 -- cm
  wtdepannmin    int,                                 -- cm
  iccdcd         text,                                -- irrigated capability class
  niccdcd        text,
  hydclprs       smallint,
  -- derived from the dominant component (no foreign key: component references map_unit)
  dom_cokey      text,
  ground_type    text references soils.ground_type,
  restr_kind     text,       -- the dominant component's shallowest restrictive layer, of any kind
  restr_top_cm   smallint,
  restr_hard     text,
  -- the "Show by" codes: 0 is the palest step of the wash; darker means a shallower hardpan or bedrock, wetter, more
  -- water held, better farmland, more runoff. Null: not rated (a miscellaneous area, or NRCS gives no value).
  c_restr        smallint check (c_restr between 0 and 4),  -- shallowest hardpan or bedrock of the dominant
                             -- component: 0 none within 150 cm, 1 100-150, 2 50-100, 3 25-50, 4 under 25 cm
  pat            text check (pat in ('hardpan', 'bedrock', 'none')),  -- that layer's kind when within 50 cm
  c_drain        smallint check (c_drain between 0 and 4),  -- drclassdcd: excessively, well, moderately well,
                                                             -- somewhat poorly, poorly or very poorly drained
  c_aws          smallint check (c_aws between 0 and 4),    -- aws0100wta: under 5, 5-10, 10-15, 15-20, 20+ cm
  c_farm         smallint check (c_farm between 0 and 2),   -- not prime; statewide, local or unique; prime
  farm_cond      text check (farm_cond in ('irrigated', 'drained', 'reclaimed', 'protected', 'other')),
                             -- the condition farmlndcl adds ("if irrigated", ...); the wash hatches drained, reclaimed
  c_hsg          smallint check (c_hsg between 0 and 3),    -- hydgrpdcd A, B, C, D (a dual group by its first letter)
  hsg_dual       boolean,                                   -- A/D, B/D, C/D: D where undrained (hatched)
  area_in_box_ha double precision not null default 0,
  n_polygons     int not null default 0,                    -- its polygons touching the box
  -- Its polygons generalised for the valley zooms, in one MultiPolygon (no join for the wash's codes there):
  -- simplified in UTM 11N, parts that collapse dropped. Null when every part collapsed.
  geom_z8        geometry(MultiPolygon, 4326),              -- 100 m, for z8-9 (about 0.9 px at z9)
  geom_z10       geometry(MultiPolygon, 4326)               -- 25 m, for z10-11
);
create index map_unit_area_idx on soils.map_unit (areasymbol);
create index map_unit_ground_type_idx on soils.map_unit (ground_type);
create index map_unit_geom_z8_idx on soils.map_unit using gist (geom_z8);
create index map_unit_geom_z10_idx on soils.map_unit using gist (geom_z10);

-- Components of those map units: everything the card shows.
create table soils.component (
  cokey               text primary key,
  mukey               text not null references soils.map_unit on delete cascade,
  compname            text not null,
  compkind            text,                           -- Series, Miscellaneous area, Taxadjunct, ...
  comppct_r           smallint,
  majcomp             boolean,
  slope_l             real,
  slope_r             real,
  slope_h             real,
  drainagecl          text,
  hydgrp              text,
  hydricrating        text,
  irrcapcl            smallint,
  irrcapscl           text,
  nirrcapcl           smallint,
  nirrcapscl          text,
  taxclname           text,
  taxorder            text,
  earthcov            text,                           -- earthcovkind1
  landform            text,                           -- the representative landform, else the first listed
  pm_kind             text,                           -- parent material kinds, in order
  ffd_r               smallint,                       -- frost-free days
  albedodry_r         real,
  elev_r              real,                           -- m
  map_r               smallint,                       -- mean annual precipitation, mm
  surf_frag_cover_pct real,
  eco_id              text,                           -- ecological site, e.g. R011XY001ID
  eco_name            text,
  restrictions        jsonb not null default '[]',    -- [{kind, top_cm, bottom_cm, hard}] by depth
  crop_yields         jsonb not null default '[]'     -- [{crop, units, irr, nonirr}] (representative values)
);
create index component_mukey_idx on soils.component (mukey);

-- Horizons of those components.
create table soils.horizon (
  chkey      text primary key,
  cokey      text not null references soils.component on delete cascade,
  hzname     text,
  top_cm     smallint,
  bottom_cm  smallint,
  texture    text,                                    -- with modifier: 'Gravelly silt loam'
  texcl      text,
  sand       real,                                    -- percent
  silt       real,
  clay       real,
  om         real,                                    -- organic matter, percent
  ph         real,                                    -- 1:1 water
  caco3      real,                                    -- percent
  gypsum     real,
  ec         real,                                    -- dS/m
  sar        real,
  awc        real,                                    -- cm/cm
  ksat       real,                                    -- micrometres per second
  kwfact     real,
  frag_gt10  real,                                    -- percent by volume
  frag_3to10 real
);
create index horizon_cokey_idx on soils.horizon (cokey);

-- The map-unit polygons touching the box (21,999), kept whole. geom_lo is simplified by 5 m (for z12-13; z8-11 read
-- soils.map_unit's geom_z8 and geom_z10); label_pt is the centre of the largest circle inside the polygon. Areas
-- are on the ellipsoid. gid is an integer key for tiles' feature ids and files: unique, but new each time its survey
-- area is reloaded.
create table soils.polygon (
  id             text primary key,                    -- 'ID001:1234': area symbol and the shapefile's feature id
  gid            integer generated always as identity unique,
  areasymbol     text not null references soils.survey_area on delete cascade,
  mukey          text not null references soils.map_unit on delete cascade,
  geom           geometry(MultiPolygon, 4326) not null,
  geom_lo        geometry(MultiPolygon, 4326),
  label_pt       geometry(Point, 4326),
  area_m2        double precision,
  area_in_box_m2 double precision
);
create index polygon_geom_idx on soils.polygon using gist (geom);
create index polygon_geom_lo_idx on soils.polygon using gist (geom_lo);
create index polygon_label_idx on soils.polygon using gist (label_pt);
create index polygon_mukey_idx on soils.polygon (mukey);

-- Photo statistics (package P2): each ground type's and map unit's colour, spread and texture, measured from the
-- aerial photo over its uncovered ground. Stored as measured, never pre-styled. Old builds are kept.
--   level: 'mapunit' (key is a mukey) or 'ground_type' (key is a ground_type id)
--   photo: 'naip2025' or 'naip2023-tiles'; flight: the NAIP flight day, null when pooled over flights
--   mask: 'photo-v1' or 'classes-v1'
--   lab_med: OKLab median (L, a, b); lab_cov: the covariance's upper triangle (LL, La, Lb, aa, ab, bb)
--   oct_l, oct_c: texture energy of L and chroma at 1.2, 2.4, 4.8, 9.6 and 19.2 m
--   fallback: null when measured; else what it was borrowed from ('series', 'texture' or 'albedo')
create table soils.photo_stats (
  id          bigint generated always as identity primary key,
  build_id    text not null references soils.build on delete cascade,
  level       text not null check (level in ('mapunit', 'ground_type')),
  key         text not null,
  photo       text not null,
  flight      date,
  mask        text not null,
  n_px        bigint not null check (n_px >= 0),
  n_polygons  int,
  lab_med     real[] check (cardinality(lab_med) = 3),
  lab_cov     real[] check (cardinality(lab_cov) = 6),
  l_p10       real,
  l_p90       real,
  oct_l       real[] check (cardinality(oct_l) = 5),
  oct_c       real[] check (cardinality(oct_c) = 5),
  fallback    text check (fallback in ('series', 'texture', 'albedo')),
  unique nulls not distinct (build_id, level, key, photo, flight, mask)
);

-- Each ground type's colour, pooled over flights, from the newest finished photo build that has the type. A photo
-- build may hold only some types (a rerun for the map units a reload changed, or one photo's run): a build
-- supersedes older ones for every type it has a pooled row for, whichever photo or mask that row is from, and the
-- other types keep their older rows. Within one build: NAIP 2025 over the 2023 tiles, the class mask over the
-- photo mask. Types no longer in soils.ground_type drop out; gid is the type's integer key.
create view soils.ground_colour as
select distinct on (s.key)
  s.key as ground_type, g.gid, s.build_id, b.finished_at, s.photo, s.mask, s.n_px, s.n_polygons, s.lab_med,
  s.lab_cov, s.l_p10, s.l_p90, s.oct_l, s.oct_c, s.fallback
from soils.photo_stats s
join soils.build b on b.build_id = s.build_id and b.kind = 'photo' and b.finished_at is not null
join soils.ground_type g on g.id = s.key
where s.level = 'ground_type' and s.flight is null
order by s.key, b.finished_at desc, b.build_id desc, (s.photo = 'naip2025') desc, (s.mask = 'classes-v1') desc;

-- The map units in a shape, with their area shares, for the farm field card and later the gardening bed card:
-- "62% Purdam silt loam, 38% Power silt loam". g is in EPSG:4326 (another SRID is transformed; none is taken as
-- 4326). An invalid areal shape (a bow-tie field, a bed drawn crossing itself) is made valid first, keeping its
-- polygons. share is of the shape's own area, and a unit the shape only touches (a shared edge, under 0.01 m2)
-- isn't in it; a point or line gets equal shares among the units it touches. misc is the unit's ground type's
-- (soils.ground_type): 'nodata' means not surveyed.
create function soils.mapunit_shares(g geometry)
returns table (mukey text, musym text, muname text, ground_type text, misc text, farmlndcl text,
               area_m2 double precision, share double precision)
language sql stable parallel safe
as $$
  with given as (
    select case when ST_SRID(g) = 0 then ST_SetSRID(g, 4326)
                when ST_SRID(g) = 4326 then g
                else ST_Transform(g, 4326) end as g
  ), shape as (
    select case when ST_Dimension(given.g) = 2 and not (ST_IsValidDetail(given.g)).valid     -- no NOTICE
                then ST_CollectionExtract(ST_MakeValid(given.g), 3) else given.g end as g
    from given
  ), total as (
    select ST_Area(shape.g::geography) as m2, ST_Dimension(shape.g) = 2 and not ST_IsEmpty(shape.g) as areal
    from shape
  ), parts as (
    select p.mukey, sum(case when total.areal then ST_Area(ST_Intersection(p.geom, shape.g)::geography)
                             else 0 end) as m2
    from shape, total, soils.polygon p
    where p.geom && shape.g and ST_Intersects(p.geom, shape.g)
    group by p.mukey
  ), kept as (
    select parts.* from parts, total where not total.areal or parts.m2 >= 0.01
  )
  select m.mukey, m.musym, m.muname, m.ground_type, t.misc, m.farmlndcl, kept.m2,
         case when total.areal and total.m2 > 0 then kept.m2 / total.m2 else 1.0 / count(*) over () end
  from kept join soils.map_unit m using (mukey) left join soils.ground_type t on t.id = m.ground_type, total
  order by 8 desc, m.mukey
$$;

comment on schema soils is
  'The NRCS soil survey (SSURGO): public domain, republish yes, credit "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)"';
comment on table soils.polygon is
  'SSURGO map-unit polygons touching the map box, kept whole. Public domain; republish yes; credit USDA NRCS SSURGO';
comment on function soils.mapunit_shares(geometry) is
  'The map units in a shape (EPSG:4326) with their area shares, largest first';
comment on view soils.ground_colour is
  'Each ground type''s colour pooled over flights, from the newest finished photo build that has the type (a build '
  'supersedes older ones for the types it holds; the others keep their older rows); within a build NAIP 2025 over '
  'the 2023 tiles, the class mask over the photo mask';
