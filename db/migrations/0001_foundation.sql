-- 0001: sources, the fetch log, and raw record versions (docs/12 §12.2-12.4).

create extension if not exists postgis;

create schema if not exists ops;
create schema if not exists raw;
create schema if not exists core;

-- Every source we read, and how we're allowed to read it.
create table ops.source (
  name          text primary key,                 -- 'achd_cameras', 'wzdx', ...
  title         text not null,
  url           text not null,
  access        text not null check (access in ('open', 'api_key', 'one_off', 'request')),
  schedule      interval,                         -- null: not scheduled
  license       text,                             -- 'ODbL', 'public domain', 'none stated', ...
  credit        text,                             -- attribution to show
  notes         text,
  -- One-off and by-request sources can never be put on a schedule.
  check (access not in ('one_off', 'request') or schedule is null)
);

-- One row per fetch attempt, so gaps and failures stay visible.
create table ops.fetch (
  id            bigint generated always as identity primary key,
  source        text not null references ops.source,
  started_at    timestamptz not null,
  finished_at   timestamptz,
  http_status   int,
  robots        text check (robots in ('allowed', 'no_rules', 'one_off')),
  ok            boolean not null,
  records       int,
  bytes         bigint,
  error         text
);
create index fetch_source_started on ops.fetch (source, started_at desc);

-- Every version of every source record, as fetched. A changed record adds a
-- row; an unchanged one only moves last_seen; one missing from a complete
-- snapshot gets removed_at.
create table raw.record (
  source        text not null references ops.source,
  source_id     text not null,
  version_hash  bytea not null,
  payload       jsonb not null,
  geom          geometry(Geometry, 4326),
  first_seen    timestamptz not null,
  last_seen     timestamptz not null,
  removed_at    timestamptz,
  first_fetch   bigint references ops.fetch,
  primary key (source, source_id, version_hash)
);
create index record_current on raw.record (source, source_id, last_seen desc);
