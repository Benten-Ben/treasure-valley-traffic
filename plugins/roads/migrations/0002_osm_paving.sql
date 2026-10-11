-- roads 0002: OpenStreetMap's paving: service ways and walkways, parking lots and stalls, crossing
-- and kerb nodes (landscape sprint, Oct 2026: plan C1, C2, C10, C11, package P8-data).
--
-- The osm_paving consumer of core's OpenStreetMap loader (ingest/osm_extract.py,
-- plugins/roads/ingest/sources/osm_paving.py) writes all three tables, from one extract:
--
--   roads.osm_paving     the highway ways the partition gives it, by tags alone: every service way
--                        but alleys (driveways, parking aisles, drive-throughs, emergency access,
--                        untagged and other service ways), and footway=sidewalk, crossing,
--                        access_aisle or traffic_island on a footway, path or cycleway. Lines; a
--                        way drawn as an area (area=yes) keeps its outline, with area true (an
--                        alley drawn as one is the paving's too: osm_street takes lines only).
--   roads.osm_parking    parking lots (amenity=parking) and mapped stalls (amenity=parking_space)
--                        drawn as areas: closed ways and multipolygons, whole (the loader's smart
--                        cut keeps a multipolygon whole when any member is in the box).
--   roads.osm_walk_node  crossing nodes (highway=crossing, or any crossing=*) and kerb nodes
--                        (kerb=*), with the paving ways through each. Separate from core.osm_node,
--                        so osm_valley's node retiring isn't disturbed (a crossing at signals can
--                        be in both).
--
-- Approved by the owner, Oct 8 (the landscape sprint: parking lots, sidewalks, driveways, service
-- ways and crossings from the held extract). Stored, not drawn yet: kerbs and the stall estimate.
--
-- Material (plan C11). `material` comes from the surface tag where it reads as one of ours
-- (material_source 'surface'). Otherwise a kind's default (material_source 'default': the card
-- says "surface estimated"), but for service ways and lots only on developed land: at least half
-- of the way's length, or of the lot's area, on USDA's Cropland Data Layer 2025 developed classes
-- (122-124, low to high intensity; `developed` is that share). Off developed land an untagged
-- service way or lot is 'unknown' (material_source null): farm lanes, private roads and trailhead
-- lots are often gravel. Walkways take their kind's default anywhere. Widths: the width tag, else
-- a kind's default (width_source 'default', estimated ⚠️).
--
-- Versioned in place (plan C2): no raw.record copies. osm_version and osm_timestamp are
-- OpenStreetMap's; first_seen and last_seen the loads that first and last brought it; an object
-- missing from a load becomes inactive and is never deleted. The archive keeps the last two
-- extracts.
--
-- License ODbL (© OpenStreetMap contributors), republish yes: anything derived from it that we
-- publish stays ODbL. `developed` also reads the CDL (USDA NASS, public domain), which changes
-- neither. OpenStreetMap stays in tables of its own, so other sources' tables aren't pulled under
-- the ODbL.

create table roads.osm_paving (
  osm_id          bigint primary key,
  kind            text not null check (kind in ('service', 'driveway', 'parking_aisle', 'drive_through',
                                                'emergency_access', 'sidewalk', 'crossing', 'access_aisle',
                                                'traffic_island')),
  highway         text not null check (highway in ('service', 'footway', 'path', 'cycleway')),
  service         text,                              -- service=*, as tagged (alleys only as areas)
  footway         text,                              -- footway=*, as tagged
  name            text,
  area            boolean not null default false,    -- drawn as an area (area=yes): geom is its outline
  surface         text,                              -- the surface tag, as tagged
  material        text not null check (material in ('asphalt', 'concrete', 'gravel', 'dirt', 'unknown')),
  material_source text check (material_source in ('surface', 'default')),
  developed       real check (developed between 0 and 1),   -- service ways: share on CDL developed land
  width_m         real,                              -- the width tag in metres, when it reads as one
  width_est_m     real not null check (width_est_m > 0),
  width_source    text not null check (width_source in ('tagged', 'default')),
  oneway          text,                              -- yes, -1 or no, else as tagged
  access          text,
  crossing        text,                              -- crossing ways: crossing=*, as tagged
  crossing_markings text,                            -- crossing:markings, as tagged
  marked          boolean,                           -- crossing ways: marked, unmarked, or null (not known)
  marked_from     text check (marked_from in ('way', 'node')),
  layer           smallint,
  bridge          boolean not null default false,
  tunnel          boolean not null default false,
  tags            jsonb not null,                    -- every tag, as tagged
  geom            geometry(LineString, 4326) not null,
  osm_version     int,
  osm_timestamp   timestamptz,
  active          boolean not null default true,
  first_seen      timestamptz not null default now(),
  last_seen       timestamptz not null default now(),
  check ((highway = 'service') = (kind in ('service', 'driveway', 'parking_aisle', 'drive_through',
                                           'emergency_access'))),
  check (service is distinct from 'alley' or area),
  check ((material = 'unknown') = (material_source is null)),
  check (marked_from is null or marked is not null),
  check (kind = 'crossing' or marked is null)
);
create index osm_paving_geom on roads.osm_paving using gist (geom);
create index osm_paving_active on roads.osm_paving (kind) where active;

comment on table roads.osm_paving is
  'OpenStreetMap''s service ways and walkways (osm_paving consumer). License ODbL (© OpenStreetMap contributors); republish: yes';

create table roads.osm_parking (
  osm_type        char(1) not null check (osm_type in ('w', 'r')),   -- a closed way or a multipolygon
  osm_id          bigint not null,
  kind            text not null check (kind in ('lot', 'space')),   -- amenity=parking, amenity=parking_space
  parking         text,                              -- parking=* (surface, multi-storey, underground, ...)
  name            text,
  operator        text,
  access          text,
  fee             text,
  capacity        int check (capacity >= 0),         -- the capacity tag, when it's a whole number
  surface         text,
  material        text not null check (material in ('asphalt', 'concrete', 'gravel', 'dirt', 'unknown')),
  material_source text check (material_source in ('surface', 'default')),
  developed       real check (developed between 0 and 1),   -- share of its area on CDL developed land
  layer           smallint,
  building        text,                              -- building=*, when the lot is also a building
  area_m2         real not null check (area_m2 >= 0),
  tags            jsonb not null,
  geom            geometry(MultiPolygon, 4326) not null,
  osm_version     int,
  osm_timestamp   timestamptz,
  active          boolean not null default true,
  first_seen      timestamptz not null default now(),
  last_seen       timestamptz not null default now(),
  primary key (osm_type, osm_id),
  check ((material = 'unknown') = (material_source is null))
);
create index osm_parking_geom on roads.osm_parking using gist (geom);
create index osm_parking_active on roads.osm_parking (kind) where active;

comment on table roads.osm_parking is
  'OpenStreetMap''s parking lots and stalls (osm_paving consumer). License ODbL (© OpenStreetMap contributors); republish: yes';

create table roads.osm_walk_node (
  osm_id          bigint primary key,
  kind            text not null check (kind in ('crossing', 'kerb')),   -- a crossing that's also a kerb is a crossing
  crossing        text,                              -- crossing=*, as tagged
  crossing_markings text,                            -- crossing:markings, as tagged
  marked          boolean,                           -- marked, unmarked, or null (not known; rail crossings)
  signals         boolean not null default false,    -- at traffic signals
  kerb            text,                              -- kerb=* (flush, lowered, raised, rolled, ...)
  tactile_paving  text,
  railway         text,                              -- railway=* on a rail crossing: not a crosswalk
  ways            bigint[] not null default '{}',    -- the roads.osm_paving ways through it
  tags            jsonb not null,
  geom            geometry(Point, 4326) not null,
  osm_version     int,
  osm_timestamp   timestamptz,
  active          boolean not null default true,
  first_seen      timestamptz not null default now(),
  last_seen       timestamptz not null default now(),
  check (railway is null or marked is null)
);
create index osm_walk_node_geom on roads.osm_walk_node using gist (geom);
create index osm_walk_node_active on roads.osm_walk_node (kind) where active;

comment on table roads.osm_walk_node is
  'OpenStreetMap''s crossing and kerb nodes (osm_paving consumer). License ODbL (© OpenStreetMap contributors); republish: yes';
