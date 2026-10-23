-- 0022: the streaming sources get a 'stale after' value, and ops.source_status judges them (landscape sprint,
-- Oct 2026: issue 304, after migration 0021).
--
-- 0021's ops.source_status listed only sources with a schedule, so the streams (vrt_realtime, itd_wzdx,
-- idaho511_api) were never judged. A stream has no schedule; it runs all the time and logs a fetch for each poll
-- it takes. Its manifest entry (plugins/<name>/plugin.json) now says how long it may go without a good fetch:
--
--   stale_after     the longest age of the stream's last good fetch that still reads fresh. Past it, the
--                   stream is stale. There is no 'late' step for a stream: it polls every few seconds or
--                   minutes, so one missed poll says nothing, and the value is already a generous allowance.
--   fetch_sources   optional: the other sources whose fetches count as this stream's. idaho511_api logs each
--                   endpoint under its own source (idaho511_event, ...), never under its own name; its newest
--                   good fetch among them is its measure.
--
-- ingest/db.py's ensure_source copies both from the manifest into ops.source when the stream starts. A stream
-- that has never started has no row, so it isn't listed.
--
-- idaho511_frames is deliberately not judged here: it keeps no ops.fetch rows (it writes frames and a status
-- file), so its measure is its status file under cameras/status/ (coordinator, Oct 23).

alter table ops.source
  add column stale_after   interval check (stale_after > interval '0'),
  add column fetch_sources text[] check (fetch_sources is null or stale_after is not null),
  add check (stale_after is null or schedule is null);   -- a source is scheduled or a stream, not both

-- The view keeps 0021's columns, in their order, and appends stale_after. For a stream: schedule, due_at and
-- late_at are null, stale_at is its last good fetch plus stale_after, and state is fresh, stale or never.
create or replace view ops.source_status as
select s.name                                   as source,
       s.title,
       s.schedule,
       good.started_at                          as last_ok_at,
       now() - good.started_at                  as age,
       good.started_at + s.schedule             as due_at,
       good.started_at + s.schedule + g.grace   as late_at,
       case when s.stale_after is not null then good.started_at + s.stale_after
            else good.started_at + 3 * s.schedule + g.grace end as stale_at,
       case when good.started_at is null then 'never'
            when s.stale_after is not null then
              case when now() < good.started_at + s.stale_after then 'fresh' else 'stale' end
            when now() < good.started_at + s.schedule + g.grace then 'fresh'
            when now() < good.started_at + 3 * s.schedule + g.grace then 'late'
            else 'stale' end                    as state,
       tried.started_at                         as last_try_at,
       tried.ok                                 as last_try_ok,
       coalesce(failed.n, 0)                    as failures,
       failed.error                             as last_error,
       s.stale_after
from ops.source s
cross join lateral (select greatest(s.schedule / 4, interval '15 minutes') as grace) g
cross join lateral (select array[s.name] || coalesce(s.fetch_sources, '{}') as names) nm
left join lateral (
  select f.started_at from ops.fetch f
  where f.source = any(nm.names) and f.ok
  order by f.started_at desc, f.id desc limit 1) good on true
left join lateral (
  select f.started_at, f.ok from ops.fetch f
  where f.source = any(nm.names) and f.finished_at is not null
  order by f.started_at desc, f.id desc limit 1) tried on true
left join lateral (
  select count(*)::int as n, (array_agg(f.error order by f.started_at desc, f.id desc))[1] as error
  from ops.fetch f
  where f.source = any(nm.names) and not f.ok and f.finished_at is not null
    and f.started_at > coalesce(good.started_at, '-infinity')) failed on true
where s.schedule is not null or s.stale_after is not null;

comment on column ops.source.stale_after is
  'Streams only: the longest age of its last good fetch that still reads fresh (from its manifest); null for scheduled and manual sources';
comment on column ops.source.fetch_sources is
  'Streams only: other sources whose fetches count as this stream''s (idaho511_api logs each endpoint under its own name)';
comment on view ops.source_status is
  'Each scheduled source''s last good fetch against its schedule (fresh, late, stale or never), and each stream''s against its stale_after (fresh, stale or never). idaho511_frames keeps no fetch log: its status file is its measure.';
