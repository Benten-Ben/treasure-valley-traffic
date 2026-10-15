-- roads 0001: the roads schema, and OpenStreetMap's other streets and alleys (landscape sprint,
-- Oct 2026: plan C1, C2, C10, package S1).
--
-- The schema holds roads' own tables from now on: OpenStreetMap inputs named osm_* (this one,
-- and osm_paving in 0002), then the real-width build (pieces, cross-sections, surfaces,
-- markings: 0003). Core's road tables (core.road_segment, core.osm_way, core.segment_match,
-- the lane inventories) stay where they are.
--
-- roads.osm_street is the osm_street consumer of core's OpenStreetMap loader
-- (ingest/osm_extract.py, plugins/roads/ingest/sources/osm_street.py): the highway ways the
-- partition gives it, by tags alone: residential, unclassified, living_street, road and
-- busway, and alleys (highway=service + service=alley), that osm_valley doesn't keep
-- (osm_valley keeps the major roads and any way tagged with lanes, in core.osm_way, unchanged).
-- With core.osm_way it gives the real-width build every carriageway. Approved by the owner,
-- Oct 8 (decision 2a).
--
-- Versioned in place (plan C2): no raw.record copies. osm_version and osm_timestamp are
-- OpenStreetMap's; first_seen and last_seen the loads that first and last brought it; a way
-- missing from a load becomes inactive and is never deleted. The archive keeps the last two
-- extracts.
--
-- License ODbL (© OpenStreetMap contributors), republish yes: anything derived from it that we
-- publish stays ODbL. OpenStreetMap stays in tables of its own, so other sources' tables aren't
-- pulled under the ODbL.

create schema if not exists roads;

create table roads.osm_street (
  osm_id         bigint primary key,
  highway        text not null check (highway in ('residential', 'unclassified', 'living_street', 'road',
                                                   'busway', 'service')),
  service        text,                              -- 'alley' on alleys (highway=service), else null
  name           text,
  ref            text,
  oneway         text,                              -- yes, -1 or no (implied yes on roundabouts), else as tagged
  width_m        real,                              -- the width tag in metres, when it reads as one
  surface        text,
  access         text,
  maxspeed       text,
  layer          smallint,
  bridge         boolean not null default false,
  tunnel         boolean not null default false,
  tags           jsonb not null,                    -- every tag, as tagged
  geom           geometry(LineString, 4326) not null,
  osm_version    int,
  osm_timestamp  timestamptz,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  check ((highway = 'service') = (service is not null)),
  check (service is null or service = 'alley')
);
create index osm_street_geom on roads.osm_street using gist (geom);
create index osm_street_active on roads.osm_street (highway) where active;

comment on table roads.osm_street is
  'OpenStreetMap''s other streets and alleys (osm_street consumer). License ODbL (© OpenStreetMap contributors); republish: yes';
