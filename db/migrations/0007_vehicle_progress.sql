-- 0007: where each bus fix lies along its route, for playback (docs/14 §14.4
-- "Playback", §14.8 "Schema"; approved by the owner Oct 6, 2026, Q4).
--
-- ingest/transit_progress.py writes one row per fix in obs.vehicle_position:
-- the transit stream right after each stored batch, and a backfill by hand.
-- Each row says which shape the fix was matched to and how far along it, how
-- the bus's route is known, and how the bus got to its next fix (the step).
-- The tracks API (/api/transit/tracks) replays buses from these. A fix with no
-- row yet still plays, as a straight step, so playback never waits for this.
--
-- obs.vehicle_position stays exactly as the feed reported it; nothing here
-- changes it.

create table obs.vehicle_progress (
  vehicle_id     text not null,
  ts             timestamptz not null,               -- the fix (obs.vehicle_position's key)
  shape_id       text,                               -- null: off every shape (more than 40 m from all)
  m              real,                               -- metres along the shape (UTM 11N), from its start
  off_m          real,                               -- metres from the fix to that point on the shape
  route_id       text,                               -- the route as known when matched (null: unknown)
  route_source   text,                               -- feed | trip | matched (trip_route_match) | path (provisional)
  step           text,                               -- to the vehicle's next fix: along | still | straight | gap
  step_speed_ms  real,                               -- along: dm/dt; straight: chord/dt; still: 0; gap: null
  method         text not null default 'window_v1',  -- or 'late': arrived after a newer fix; stored with no step
  seen_at        timestamptz not null default now(), -- when the stream's matcher wrote it (about its arrival)
  backfill       boolean not null default false,     -- true: seen_at isn't its arrival (written by the backfill,
                                                     -- or caught up by the stream after a skipped batch)
  primary key (vehicle_id, ts)
);

-- With TimescaleDB (on the server): a hypertable in 1-day chunks, compressed
-- after 7 days, like obs.vehicle_position (0003). Each step is written within a
-- minute of its fix, well inside the uncompressed window. Without it (local
-- tests): a plain table with its own time index.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'timescaledb') then
    create extension if not exists timescaledb;
    perform create_hypertable('obs.vehicle_progress', 'ts',
                              chunk_time_interval => interval '1 day');
    alter table obs.vehicle_progress set (timescaledb.compress,
                                          timescaledb.compress_segmentby = 'vehicle_id',
                                          timescaledb.compress_orderby = 'ts');
    perform add_compression_policy('obs.vehicle_progress', interval '7 days');
  else
    create index vehicle_progress_ts on obs.vehicle_progress (ts desc);
  end if;
end $$;
