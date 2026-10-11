-- water 0002: the canal season's district dates (landscape sprint, Oct 2026: package P5, data side; the owner's
-- decision 18, Oct 8).
--
-- Each canal's water season is a lifecycle in evt.event (source 'canal_season', kind 'canal_season'), derived each
-- hour by the canal_season source (plugins/water/ingest/season.py) from, strongest first:
--   the New York Canal's gauge BSEI1 (NWPS readings in raw.record: stage and flow), "unknown" after 48 hours
--   without a reading;
--   the districts' announced dates, from the versioned file plugins/water/ingest/canal_dates.json, which
--   `python3 -m ingest canal-dates-load` loads into the table below (the file is the record: the server keeps no
--   backups);
--   IDWR's legal season of use at the canal's head (water.canal_season, INTERNAL), labelled as the legal window,
--   not delivery dates.
-- Nothing here is drawn: the app reads the lifecycles and sets feature-state on the baked reaches (wave 2).

-- One row per entry of canal_dates.json, replaced whole by each canal-dates-load. Facts (dates) from each district's
-- own page, cited with the date we read it. Canals are named, not numbered: water.canal's ids follow its builds. A
-- name selects every canal of that name in the valley, unless head_in or canal_ids narrow it (the load lists names
-- that select several).
create table water.canal_date (
  entry_id   text primary key check (entry_id ~ '^[a-z0-9][a-z0-9._-]*$'),
  position   integer not null unique,                   -- its place in the file: a later entry wins on a canal
  district   text not null check (btrim(district) <> ''),   -- who announced it, as it names itself
  canals     text[] not null check (cardinality(canals) > 0),   -- water.canal names, as the district names them
  branches   boolean not null default false,            -- also the canals fed from them (water.canal.source_canal_id)
  head_in    text[] check (cardinality(head_in) > 0),   -- only the named canals whose head lies in one of these IDWR
                                                        -- service areas (water.canal_org.at_head); null: anywhere
  canal_ids  bigint[] check (cardinality(canal_ids) > 0),   -- only these of the named canals (ids follow the builds)
  season     smallint not null check (season between 1900 and 2200),   -- the calendar year its dates fall in
  on_at      timestamptz,                               -- water on from (a date: that day's start, Boise time)
  off_at     timestamptz,                               -- off from (likewise)
  on_given   text,                                      -- each as the file gives it ('2027-04-06', '...T08:00')
  off_given  text,
  words      text,                                      -- the district's own words, quoted
  source     text not null check (source ~ '^https?://'),   -- the page
  read_on    date not null,                             -- when we read it
  republish  text not null default 'yes' check (republish in ('yes', 'aggregates', 'internal', 'no')),
  load_id    bigint not null references water.load,
  check (on_at is not null or off_at is not null),
  check (on_at is null or off_at is null or on_at < off_at)
);

comment on table water.canal_date is
  'The districts'' canal dates as loaded from plugins/water/ingest/canal_dates.json (canal-dates-load); each cites its page';
