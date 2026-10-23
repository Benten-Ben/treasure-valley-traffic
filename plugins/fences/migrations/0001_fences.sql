-- fences (landscape sprint, plan C1, C3, C10, C14; package P10): OpenStreetMap's mapped fences, walls,
-- retaining walls, guard rails, jersey barriers, hedges and a few other barrier lines, and its gates,
-- lift gates, bollards, blocks and cattle grids, cut to the valley box.
--
-- * plugins/fences/ingest/sources/osm_barriers.py (a consumer of core's OpenStreetMap loader,
--   ingest/osm_extract.py) writes both tables from the Idaho extract the owner downloads by hand.
--   Versioned in place (plan C2): no raw.record copies; osm_version and osm_timestamp are
--   OpenStreetMap's, first_seen and last_seen the loads that first and last brought the object, and
--   an object missing from a load becomes inactive and is never deleted.
-- * Mapped fences only. Most backyard fences are not in OpenStreetMap, and a mapped fence never
--   says where a lot ends (owner's decision, Oct 8, 2026).
-- * Hedges are stored here (plan C14) so the shrubs' hedge check (plugins/trees/ingest/hedge_check.py)
--   can read them: it reads fence_id, type, geom and active. They are not drawn as fences.
--
-- License ODbL (© OpenStreetMap contributors), republish yes: the tables hold OpenStreetMap's
-- objects and what is derived from them by tag rules alone (plan C3). Anything published from them
-- stays ODbL.

create schema if not exists fences;

create table fences.fence (
  fence_id       text primary key check (fence_id ~ '^osm:w[0-9]+$'),
  kind           text not null,                       -- the barrier tag as mapped (fence, wall, hedge, ...)
  type           text not null check (type in ('fence', 'wall', 'retaining_wall', 'guard_rail', 'jersey_barrier',
                                               'hedge', 'other')),
  look           text not null check (look in ('solid', 'open')),   -- from the tags (⚠️ a reading, not a survey)
  height_m       real not null check (height_m > 0),
  height_source  text not null check (height_source in ('tagged', 'default')),   -- default: an estimate by type ⚠️
  material       text,
  fence_type     text,                                -- the fence_type tag (chain_link, wood, ...)
  name           text,
  tags           jsonb not null,                      -- every tag, as tagged
  osm_id         bigint not null,
  osm_version    int,
  osm_timestamp  timestamptz,
  geom           geometry(LineString, 4326) not null,
  length_m       real generated always as (ST_Length(geom::geography)) stored,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  check (fence_id = 'osm:w' || osm_id)
);
create index fence_geom on fences.fence using gist (geom);
create index fence_type on fences.fence (type) where active;

comment on table fences.fence is
  'OpenStreetMap''s mapped fences, walls, retaining walls, guard rails, jersey barriers, hedges and other barrier lines (osm_barriers consumer). Mapped ones only: most backyard fences are not in OpenStreetMap, and a fence never says where a lot ends. License ODbL (© OpenStreetMap contributors); republish: yes';

create table fences.gate (
  gate_id        text primary key check (gate_id ~ '^osm:[nw][0-9]+$'),
  kind           text not null check (kind in ('gate', 'lift_gate', 'bollard', 'block', 'cattle_grid')),
  access         text,                                -- the access tag as tagged
  name           text,
  tags           jsonb not null,
  osm_type       char(1) not null check (osm_type in ('n', 'w')),   -- a gate mapped as a way is stored at its middle vertex
  osm_id         bigint not null,
  osm_version    int,
  osm_timestamp  timestamptz,
  geom           geometry(Point, 4326) not null,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  check (gate_id = 'osm:' || osm_type || osm_id)
);
create index gate_geom on fences.gate using gist (geom);

comment on table fences.gate is
  'OpenStreetMap''s gates, lift gates, bollards, blocks and cattle grids (osm_barriers consumer). License ODbL (© OpenStreetMap contributors); republish: yes';
