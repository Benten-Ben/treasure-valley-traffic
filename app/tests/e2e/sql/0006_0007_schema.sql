-- Test fixture, not a migration: the schema of migrations 0006 and 0007 as
-- docs/14 §14.8 ("Schema") specifies them, for checking that /api/meta works
-- after they exist. The harness spec applies the real files from
-- db/migrations/ instead once WP6 and WP7 have written them.

create table if not exists core.transit_ribbon (
  segment_id int primary key,
  geom geometry(LineString, 4326) not null,
  routes text[] not null,
  length_m real not null,
  hub boolean not null default false,
  build text not null);
alter table core.transit_route add column if not exists color_pinned boolean not null default false;

create table if not exists obs.vehicle_progress (
  vehicle_id text not null, ts timestamptz not null,
  shape_id text, m real, off_m real,
  route_id text, route_source text,
  step text, step_speed_ms real,
  method text not null default 'window_v1',
  seen_at timestamptz not null default now(),
  backfill boolean not null default false,
  primary key (vehicle_id, ts));
