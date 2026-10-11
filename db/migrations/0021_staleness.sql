-- 0021: staleness and build marks (landscape sprint, Oct 2026: plan §0 items 27-28, package M1).
-- Numbered 0021 because the sprint gave 0019 to the core OSM loader (S1) and 0020 to the
-- toggled layers' versions (S2); db/migrate.py applies any file not yet applied, in name order.
--
-- Until now nothing watched scheduled work: /api/health always says ok. This adds:
--
-- * ops.build_run: one row per build run, as ops.fetch has one per fetch, so each build's age
--   and failures stay visible.
-- * ops.build_pending: marks saying a build is out of date. Builds (roads-build, water-build,
--   trails-match, the exports, the base bake, ...) never run inside `ingest serve`: a source
--   whose new data a build should take in marks it, in the same transaction as its data, and the
--   build runs by hand (under heavy when it's heavy). A mark stays until a build run that saw it
--   succeeds (ingest/builds.py).
-- * ops.source_status: each scheduled source's last good fetch against its schedule.
-- * ops.build_status: each build's age, and whether it's marked, running or failed.
--
-- /api/meta reports the two views' gist for a status chip, and the VM's bin/status prints them
-- at the start of each session.

-- A build's name is the command that runs it (roads-build, water-build, trails-match), or for a
-- worker step its job (landscape-bake).

create table ops.build_run (
  id           bigint generated always as identity primary key,
  build        text not null check (build ~ '^[a-z][a-z0-9_.-]{0,63}$'),
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,            -- null while it runs (or if it was killed)
  ok           boolean not null default false,
  -- The marks pending when it started, as [{"id": <ops.build_pending.id>, "marks": <its count>}]:
  -- the ones it clears if it succeeds. A mark made after it started stays for the next run.
  covers       jsonb not null default '[]' check (jsonb_typeof(covers) = 'array'),
  note         text,                   -- what it built: counts, versions, an export folder
  error        text,
  check (finished_at is null or finished_at >= started_at)
);
create index build_run_build_started on ops.build_run (build, started_at desc, id desc);

-- One row per build and marker (a source, a command, or 'by hand: <who>'). Marking again moves
-- last_at and counts up; a build run clears the rows it covered, by id and count, so a mark made
-- while it ran survives it.
create table ops.build_pending (
  id         bigint generated always as identity,
  build      text not null check (build ~ '^[a-z][a-z0-9_.-]{0,63}$'),
  marked_by  text not null check (btrim(marked_by) <> '' and length(marked_by) <= 120),
  first_at   timestamptz not null default now(),   -- its oldest mark no build has covered
  last_at    timestamptz not null default now(),   -- its newest mark
  marks      int not null default 1 check (marks >= 1),
  reason     text not null check (btrim(reason) <> ''),   -- the newest mark's reason
  primary key (build, marked_by),
  unique (id),
  check (first_at <= last_at)
);

-- Each scheduled source against its schedule, in the UI's words (docs/14 §14.4: ● fresh,
-- ▲ late, ■ stale, ◌ none yet):
--   fresh  its last good fetch is less than a schedule plus a grace old (a quarter of the
--          schedule, at least 15 minutes: `ingest serve` checks every 5 minutes, runs one source
--          after another, and retries a failure after min(schedule, 1 hour));
--   late   past that, by up to two more schedules;
--   stale  later still;
--   never  no good fetch yet.
-- failures counts finished attempts that failed since the last good one; a fetch still going
-- (finished_at null) counts as neither. last_error is the newest failure's, while it's newer
-- than the last good fetch. Unscheduled sources (streams, one-off, by hand) aren't listed.
create view ops.source_status as
select s.name                                   as source,
       s.title,
       s.schedule,
       good.started_at                          as last_ok_at,
       now() - good.started_at                  as age,
       good.started_at + s.schedule             as due_at,
       good.started_at + s.schedule + g.grace   as late_at,
       good.started_at + 3 * s.schedule + g.grace as stale_at,
       case when good.started_at is null then 'never'
            when now() < good.started_at + s.schedule + g.grace then 'fresh'
            when now() < good.started_at + 3 * s.schedule + g.grace then 'late'
            else 'stale' end                    as state,
       tried.started_at                         as last_try_at,
       tried.ok                                 as last_try_ok,
       coalesce(failed.n, 0)                    as failures,
       failed.error                             as last_error
from ops.source s
cross join lateral (select greatest(s.schedule / 4, interval '15 minutes') as grace) g
left join lateral (
  select f.started_at from ops.fetch f
  where f.source = s.name and f.ok
  order by f.started_at desc, f.id desc limit 1) good on true
left join lateral (
  select f.started_at, f.ok from ops.fetch f
  where f.source = s.name and f.finished_at is not null
  order by f.started_at desc, f.id desc limit 1) tried on true
left join lateral (
  select count(*)::int as n, (array_agg(f.error order by f.started_at desc, f.id desc))[1] as error
  from ops.fetch f
  where f.source = s.name and not f.ok and f.finished_at is not null
    and f.started_at > coalesce(good.started_at, '-infinity')) failed on true
where s.schedule is not null;

-- Each build that has run or is marked:
--   running  its newest run hasn't finished (or was killed: see last_run_at);
--   pending  marked, and no run going;
--   failed   its newest run failed and nothing is marked;
--   built    its newest run succeeded and nothing is marked since.
-- age is the time since its last good run finished; pending_since its oldest uncovered mark.
create view ops.build_status as
select b.build,
       case when last.started_at is not null and last.finished_at is null then 'running'
            when p.since is not null then 'pending'
            when not last.ok then 'failed'
            else 'built' end                    as state,
       good.finished_at                         as last_ok_at,
       now() - good.finished_at                 as age,
       good.note                                as last_ok_note,
       last.started_at                          as last_run_at,
       last.finished_at                         as last_run_finished_at,
       last.ok                                  as last_run_ok,
       case when last.finished_at is not null and not last.ok then last.error end as last_error,
       p.since                                  as pending_since,
       p.marks                                  as pending_marks,
       p.marked_by                              as pending_by,
       p.reason                                 as pending_reason
from (select build from ops.build_run union select build from ops.build_pending) b
left join lateral (
  select r.finished_at, r.note from ops.build_run r
  where r.build = b.build and r.ok
  order by r.started_at desc, r.id desc limit 1) good on true
left join lateral (
  select r.started_at, r.finished_at, r.ok, r.error from ops.build_run r
  where r.build = b.build
  order by r.started_at desc, r.id desc limit 1) last on true
left join lateral (
  select min(m.first_at) as since, sum(m.marks)::int as marks,
         array_agg(m.marked_by order by m.first_at, m.marked_by) as marked_by,
         (array_agg(m.reason order by m.last_at desc, m.id desc))[1] as reason
  from ops.build_pending m
  where m.build = b.build
  having count(*) > 0) p on true;

comment on table ops.build_run is
  'One row per build run (ingest/builds.py), like ops.fetch for sources: each build''s age and failures';
comment on table ops.build_pending is
  'Builds marked out of date by a source or command; a build run that saw a mark clears it when it succeeds';
comment on view ops.source_status is
  'Each scheduled source''s last good fetch against its schedule: fresh, late, stale or never';
comment on view ops.build_status is
  'Each build''s age, and whether it is marked (pending), running or failed';
