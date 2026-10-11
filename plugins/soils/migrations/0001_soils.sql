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
-- only when it changed (or with --force).
create table soils.survey_area (
  areasymbol  text primary key,
  areaname    text not null,
  saverest    timestamp not null,
  saversion   int,
  scale       int,                                    -- 24000 = 1:24,000
  source_url  text,                                   -- its Web Soil Survey package
  build_id    text not null references soils.build,
  loaded_at   timestamptz not null default now()
);

-- Ground types: a map unit's dominant component (its series) and that component's surface texture with modifier,
-- e.g. 'purdam:silt-loam' (385 in the box, 181 in Ada and Canyon). The ground's colours are measured per type
-- (soils.photo_stats). Miscellaneous areas have no texture ('water', 'urban-land'); misc says which kind.
create table soils.ground_type (
  id             text primary key,
  series         text not null,                       -- 'Purdam'
  texture        text,                                -- 'Gravelly silt loam' (chtexturegrp.texdesc)
  texcl          text,                                -- 'Silt loam'
  modifier       text,                                -- 'Gravelly'
  misc           text check (misc in ('water', 'urban', 'rock', 'badland', 'rubble', 'pits', 'other')),
  frag_cover_pct real,       -- surface fragment cover, area-weighted over its map units that report it
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
  n_polygons     int not null default 0                     -- its polygons touching the box
);
create index map_unit_area_idx on soils.map_unit (areasymbol);
create index map_unit_ground_type_idx on soils.map_unit (ground_type);

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

-- The map-unit polygons touching the box (21,999), kept whole. geom_lo is simplified by 5 m (for z12 and out);
-- label_pt is the centre of the largest circle inside the polygon. Areas are on the ellipsoid.
create table soils.polygon (
  id             text primary key,                    -- 'ID001:1234': area symbol and the shapefile's feature id
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

-- Each ground type's colour from the newest finished photo build, pooled over flights: NAIP 2025 where measured
-- there, the 2023 tiles otherwise; the class mask over the photo mask when a build has both.
create view soils.ground_colour as
with current_build as (
  select build_id from soils.build
  where kind = 'photo' and finished_at is not null
  order by finished_at desc, build_id desc limit 1
)
select distinct on (s.key)
  s.key as ground_type, s.build_id, s.photo, s.mask, s.n_px, s.n_polygons, s.lab_med, s.lab_cov, s.l_p10, s.l_p90,
  s.oct_l, s.oct_c, s.fallback
from soils.photo_stats s join current_build using (build_id)
where s.level = 'ground_type' and s.flight is null
order by s.key, (s.photo = 'naip2025') desc, (s.mask = 'classes-v1') desc;

-- The map units in a shape, with their area shares, for the farm field card and later the gardening bed card:
-- "62% Purdam silt loam, 38% Power silt loam". g is in EPSG:4326 (another SRID is transformed; none is taken as
-- 4326). share is of g's own area; a point or line gets equal shares among the units it touches.
create function soils.mapunit_shares(g geometry)
returns table (mukey text, musym text, muname text, ground_type text, farmlndcl text, area_m2 double precision,
               share double precision)
language sql stable parallel safe
as $$
  with shape as (
    select case when ST_SRID(g) = 0 then ST_SetSRID(g, 4326)
                when ST_SRID(g) = 4326 then g
                else ST_Transform(g, 4326) end as g
  ), total as (
    select ST_Area(shape.g::geography) as m2 from shape
  ), parts as (
    select p.mukey, sum(case when ST_Dimension(shape.g) = 2
                             then ST_Area(ST_Intersection(p.geom, shape.g)::geography) else 0 end) as m2
    from shape, soils.polygon p
    where p.geom && shape.g and ST_Intersects(p.geom, shape.g)
    group by p.mukey
  )
  select m.mukey, m.musym, m.muname, m.ground_type, m.farmlndcl, parts.m2,
         case when total.m2 > 0 then parts.m2 / total.m2 else 1.0 / count(*) over () end
  from parts join soils.map_unit m using (mukey), total
  order by 7 desc, m.mukey
$$;

comment on schema soils is
  'The NRCS soil survey (SSURGO): public domain, republish yes, credit "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)"';
comment on table soils.polygon is
  'SSURGO map-unit polygons touching the map box, kept whole. Public domain; republish yes; credit USDA NRCS SSURGO';
comment on function soils.mapunit_shares(geometry) is
  'The map units in a shape (EPSG:4326) with their area shares, largest first';
