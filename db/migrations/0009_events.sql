-- 0009: things with lifecycles, starting with work zones (docs/12 §12.7).
-- Numbered 0009 because 0006-0008 are taken by the UI v2 plan (docs/14);
-- db/migrate.py applies any file not yet applied, so the gap is harmless.

create schema if not exists evt;

-- One row per event as its source names it, cleaned for use. Every version
-- as published stays in raw.record (same source and source_id).
create table evt.event (
  id            bigint generated always as identity primary key,
  source        text not null references ops.source,
  source_id     text not null,
  kind          text not null,             -- 'work_zone', 'detour', 'incident', 'closure', ...
  geom          geometry(Geometry, 4326),  -- as published: WZDx mixes lines and single points
  declared      tstzrange,                 -- start .. end as published (after the fixes in attributes.fixes)
  observed      tstzrange not null,        -- first seen .. gone from the feed (open while it's there)
  active        boolean not null,          -- in the source's latest snapshot
  severity      text,
  description   text,
  attributes    jsonb,
  content_hash  bytea not null,            -- of the cleaned row, so unchanged polls write nothing
  updated_at    timestamptz not null,      -- when this row's content last changed
  unique (source, source_id)
);

create index event_geom on evt.event using gist (geom);
create index event_declared on evt.event using gist (declared);
create index event_observed on evt.event using gist (observed);
create index event_active on evt.event (source, kind) where active;
