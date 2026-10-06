-- 0012: COMPASS's crash, count, growth and congestion data (owner, Oct 6,
-- 2026; docs/08 §8.9), written by ingest/sources/compass_*.py. Every record
-- version as fetched stays in raw.record, except the person-level crash
-- details, which live only in the new `restricted` schema.
--
-- Terms (ops.source has them per layer): the hub layers carry COMPASS's
-- disclaimer only; credit "COMPASS and COMPASS member agencies". The
-- congestion measures and commute travel times aren't offered as open data:
-- internal use until COMPASS answers.
--
-- Join keys: pm_id is COMPASS's segment key (core.compass_segment, 0011);
-- int_id is its intersection key ('ACHD_213', 'INT_0605'). Both are null
-- where COMPASS has a placeholder ('#NYA', 'Int-Related', '_', ...).

-- Data we may keep but never publish, for aggregates only (docs/12 §12.8, which
-- foresaw it for Assessor data): from here, the people in crashes. Exports,
-- tiles and the app never read this schema, and no table outside it holds a
-- row per person.
create schema if not exists restricted;
comment on schema restricted is
  'Person-level data, for aggregates only. Never exported, tiled or served; nothing here is copied to raw.record.';

-- What a layer looked like at its last full read, so a run can skip a layer
-- that hasn't changed (ingest/sources/compass_layer.py).
create table ops.layer_signature (
  source        text primary key references ops.source,
  signature     jsonb not null,       -- {"count": .., "max_oid": .., "last_edit": ..}
  read_at       timestamptz not null, -- last full read
  checked_at    timestamptz not null  -- last check, read or not
);

-- Crashes ---------------------------------------------------------------------

-- One reported crash (ITD's crash reports as COMPASS publishes them: Ada and
-- Canyon counties, 2008 on), keyed by ITD's serial number.
create table obs.crash (
  crashed_at           timestamptz not null,     -- local date and time as reported (America/Boise); local midnight when the time is missing
  serial_number        text not null,            -- ITD's crash serial number: two-digit year, 'C', six digits
  time_known           boolean not null,
  severity             text check (severity in ('K', 'A', 'B', 'C', 'O')),  -- KABCO: fatal, serious, minor, possible injury, property damage only
  units                smallint,                 -- vehicles, pedestrians and cyclists involved
  persons              smallint,
  fatalities           smallint,
  injuries             smallint,
  light                text,                     -- 'Day', 'Dark, Street Lights On', ...
  weather              text,                     -- 'Clear', 'Rain', 'Snow', ...
  surface              text,                     -- 'Dry', 'Wet', 'Ice', ...
  road_condition       text,                     -- other road conditions as reported
  work_zone            boolean,                  -- null when not recorded ('-U', '#NAME?' or blank in the source)
  intersection_related boolean,
  street               text,
  cross_street         text,
  reference_street     text,
  distance_ft          real,                     -- from the reference point, as reported
  direction_from       text,                     -- from the reference point: N, S, E, W
  lane_of_impact       text,                     -- ITD code
  segment_code         text,                     -- ITD code
  milepost             real,
  state_highway        text,                     -- 'U.S. Highway', 'Not in State Highway System', ...
  county               text,
  city                 text,
  agency               text,                     -- the reporting police agency
  pm_id                text,                     -- COMPASS segment
  int_id               text,                     -- COMPASS intersection
  unit_types           text[],                   -- kinds of units involved ('Car', 'Pedestrian', 'Pedalcycle', ...), from restricted.crash_unit
  geom                 geometry(Point, 4326),    -- a few crashes have no coordinates
  active               boolean not null default true,   -- false once gone from COMPASS's layer
  first_seen           timestamptz not null,
  last_seen            timestamptz not null,
  primary key (serial_number, crashed_at)       -- includes the time, as a hypertable's key must
);
create index crash_geom on obs.crash using gist (geom);
create index crash_pm_id on obs.crash (pm_id);
create index crash_int_id on obs.crash (int_id);

-- With TimescaleDB (on the server): a hypertable in 1-year chunks (about
-- 11,000 crashes a year), not compressed, since monthly runs update old rows.
-- Without it (local tests): a plain table with its own time index.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'timescaledb') then
    create extension if not exists timescaledb;
    perform create_hypertable('obs.crash', 'crashed_at', chunk_time_interval => interval '365 days');
  else
    create index crash_crashed_at on obs.crash (crashed_at desc);
  end if;
end $$;

-- One person in a crash (a driver, passenger, pedestrian or cyclist), from
-- COMPASS's "crash details". Coded fields only, coarsened where a value could
-- single someone out: an age group rather than the age, Idaho resident or not
-- rather than the state or country, citation descriptions without numbers.
-- The source has no names; sex, free text and ITD's unit IDs aren't fetched.
create table restricted.crash_unit (
  serial_number        text not null,            -- obs.crash.serial_number
  unit_number          smallint not null,        -- the unit (vehicle, pedestrian, cyclist) within the crash
  seq                  smallint not null,        -- a person within the unit, ordered by content (the source has no person ID)
  unit_type            text,                     -- 'Car', 'Pickup', 'Pedestrian', 'Pedalcycle', ...
  direction            text,                     -- the unit's direction of travel
  action               text,                     -- 'Going Straight', 'Turning Left', ...
  event                text,                     -- 'Rear-End', 'Angle Turning', ...
  location             text,                     -- 'In Intersection', 'Nonjunction', ...
  contributing_factor  text,
  injury               text check (injury in ('K', 'A', 'B', 'C', 'O')),  -- KABCO
  age_group            text check (age_group in ('0-15', '16-20', '21-24', '25-34', '35-44', '45-54', '55-64', '65-74', '75+')),
  idaho_resident       boolean,
  protection_device    text,
  ejection             text,
  cited                boolean,
  citation             text,                     -- coded description, e.g. 'DRIVING Following too close'
  content_hash         bytea not null,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null,
  primary key (serial_number, unit_number, seq)
);

-- COMPASS's high-injury network (published Oct 2024): junctions and road
-- segments with crash counts, rates and risk scores. Commonly used fields are
-- columns; the rest (crash counts by type, risk-attribute scores, roundabout
-- details, lane widths, shoulders, bike and sidewalk facilities) are in
-- `attributes`. Crash counts cover COMPASS's analysis period (⚠️ not stated).
create table core.hin_junction (
  global_id            text primary key,         -- the layer's GlobalID
  int_type             text,                     -- 'Signal', 'Stop', 'Ped', 'RAB', ... (null for most)
  legs                 smallint,
  lanes_major          smallint,
  lanes_minor          smallint,
  aadt_major           int,
  aadt_minor           int,
  total_crashes        int,
  fatal_crashes        int,
  serious_injury_crashes int,
  ka_crashes           int,                      -- fatal plus serious injury
  non_motorized_crashes int,
  crash_rate           real,
  ka_crash_rate        real,
  risk_score           real,
  hin_score            real,
  hin                  boolean,                  -- on the high-injury network
  hin_non_motorized    boolean,                  -- on its walking and cycling network
  functional_class     text,
  taz_id               int,                      -- core.taz
  attributes           jsonb not null,
  source_edited        timestamptz,
  geom                 geometry(Point, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null
);
create index hin_junction_geom on core.hin_junction using gist (geom);

create table core.hin_segment (
  global_id            text primary key,         -- the layer's GlobalID (its copied `globalid` field repeats)
  pm_id                text,                     -- COMPASS segment (not unique here)
  achd_perm_id         bigint,                   -- core.road_segment.achd_perm_id (Ada only)
  name                 text,
  county               text,
  functional_class     text,
  posted_speed_mph     smallint,
  lanes                smallint,
  length_mi            real,
  aadt                 int,
  avg_speed_mph        real,
  max_speed_mph        real,
  total_crashes        int,
  fatal_crashes        int,
  serious_injury_crashes int,
  ka_crashes           int,
  non_motorized_crashes int,
  crash_rate           real,
  ka_crash_rate        real,
  risk_score           real,
  hin_score            real,
  hin                  boolean,
  hin_non_motorized    boolean,
  attributes           jsonb not null,
  source_edited        timestamptz,
  geom                 geometry(MultiLineString, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null
);
create index hin_segment_geom on core.hin_segment using gist (geom);
create index hin_segment_pm_id on core.hin_segment (pm_id);

-- Counts ----------------------------------------------------------------------

-- One traffic count: a location's daily volume for a period (docs/12 §12.6,
-- with a source-side location key until core.count_station exists, and the
-- precision of the date). COMPASS's tables hold each location's latest count
-- from every agency; runs keep the earlier counts as newer ones replace them.
-- Counts in different directions at one place have different location keys,
-- so `direction` isn't part of the key and may be unknown (null).
create table obs.traffic_count (
  source               text not null references ops.source,
  location_key         text not null,            -- the source's location: 'pm:<pm_id>', or 'loc:<agency>|<road>|<location>' (lower case)
  counted_on           date not null,            -- first day of the period counted
  period               text not null check (period in ('day', 'month', 'year')),  -- what counted_on stands for
  direction            text check (direction in ('both', 'one_direction')),  -- both summed, or one only (a one-way street, one side of a divided highway)
  count_type           text not null check (count_type in ('short', 'permanent')),  -- portable short count, or a permanent counter (ATR)
  count_24h            int,                      -- vehicles a day: ADT for a short count, AADT for a permanent counter
  am_peak              int,                      -- not in COMPASS's tables
  pm_peak              int,
  agency               text,                     -- who counted: 'ACHD', 'ITD', 'NHD', ...
  road                 text,
  location             text,                     -- e.g. 'e/o <cross street>'
  pm_id                text,                     -- COMPASS segment; COMPASS's tables have no coordinates
  first_seen           timestamptz not null,
  last_seen            timestamptz not null,
  primary key (source, location_key, counted_on)
);
create index traffic_count_pm_id on obs.traffic_count (pm_id);

-- Growth ----------------------------------------------------------------------

-- COMPASS's traffic analysis zones (its travel model's zones), current set.
create table core.taz (
  taz_id               int primary key,          -- COMPASS tazid_curr
  name                 text,
  county               text,
  demog_area           text,                     -- e.g. 'Meridian-West'
  general_area         text,
  general_city         text,
  fia_label            text,                     -- COMPASS's future-impact-area label, e.g. 'UM1'
  fia_description      text,
  highway_district     text,
  zip_code             text,
  notes                text,                     -- COMPASS's note on the zone
  geom                 geometry(MultiPolygon, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null
);
create index taz_geom on core.taz using gist (geom);

-- A zone's population, households and jobs by year: the 2020 Census, COMPASS's
-- yearly estimates and its forecasts. Values are the current release; earlier
-- releases stay in raw.record.
create table obs.taz_demographic (
  taz_id               int not null references core.taz,
  year                 smallint not null,
  measure              text not null check (measure in
                         ('population', 'household_population', 'group_quarters', 'households', 'jobs')),
  kind                 text not null check (kind in ('census', 'estimate', 'forecast')),
  value                int,
  primary key (taz_id, year, measure, kind)
);

-- A building permit (COMPASS's regional permits, 2000 on). The address, parcel
-- number and comments aren't fetched: the point places the permit, and the
-- rest isn't needed for traffic.
create table obs.building_permit (
  permit_key           text primary key,         -- '<city>|<permit number>|<yyyy-mm>'; '#2', '#3' when that repeats
  permit_number        text,
  city                 text,                     -- the issuing jurisdiction
  county               text,
  year                 smallint,
  month                smallint,
  work                 text,                     -- 'New Construction', 'Demolition', 'Addition', ...
  building_type        text,                     -- 'Single-Family', 'Multi-Family', 'Townhome', ...
  land_use_code        int,                      -- COMPASS slu
  sq_ft                real,
  units                int,                      -- dwelling units; negative for units removed (mostly demolitions)
  value_usd            bigint,
  occupiable           boolean,
  impact_area          text,
  demog_area           text,
  taz_id               int,                      -- core.taz
  highway_district     text,
  zip_code             text,
  geom                 geometry(Point, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null
);
create index building_permit_geom on obs.building_permit using gist (geom);
create index building_permit_month on obs.building_permit (year, month);
create index building_permit_taz on obs.building_permit (taz_id);

-- A development application: mostly preliminary plats, also PUDs, conditional
-- uses, rezones (COMPASS's "Preliminary Plats (Entitlements)"), with the
-- homes planned, already permitted and still to build, and expected jobs.
-- Comments aren't fetched.
create table core.plat (
  object_id            int primary key,          -- COMPASS's OBJECTID: the layer is edited in place and ProjectID isn't unique
  project_id           text,                     -- the agency's case number(s)
  name                 text,                     -- development name
  agency               text,
  kind                 text,                     -- 'Preliminary Plat', 'PUD', 'CUP', 'Rezone', ...
  status               text,                     -- 'Pending', 'Approved', 'In Progress', 'Built', ...
  land_use             text,                     -- 'Single Family', 'Multifamily', 'Mixed Use', ...
  applied_on           date,
  units_total          int,
  units_single_family  int,
  units_multifamily    int,
  units_townhome       int,
  units_duplex         int,
  permitted_single_family int,
  permitted_multifamily int,
  permitted_townhome   int,
  permitted_duplex     int,
  units_remaining      int,                      -- still to be built
  total_lots           int,
  commercial_lots      int,
  commercial_sq_ft     real,
  employment           int,                      -- expected jobs
  creates_jobs         boolean,
  school               text,
  taz_id               int,                      -- core.taz
  geom                 geometry(MultiPolygon, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null
);
create index plat_geom on core.plat using gist (geom);

-- Congestion (internal use until COMPASS answers) -----------------------------

-- Congestion and reliability by road segment and year, 2018 on (the federal
-- performance measures; probably from NPMRDS ⚠️). One row per segment and
-- year: the peak periods are the periods the index peaked in, not keys.
create table obs.congestion_measure (
  year                 smallint not null,
  segment_id           text not null,            -- a TMC code ('117-04109'), an XD segment number, or 'g:<hash>' of the geometry when the source's ID is missing (2025)
  id_kind              text not null check (id_kind in ('tmc', 'xd', 'geometry')),
  tier                 smallint,                 -- COMPASS's tier: 1 TMC network, 2 XD network
  road_name            text,
  road_number          text,
  direction            text,                     -- N, S, E, W
  county               text,
  length_mi            real,
  tti                  real,                     -- travel-time index (peak over free-flow)
  tti_peak_period      text,                     -- 'AM', 'PM', 'Afternoon', 'Weekend'
  lottr                real,                     -- level of travel-time reliability (80th / 50th percentile)
  lottr_peak_period    text,
  tttr                 real,                     -- truck travel-time reliability
  delay_hours          real,                     -- hours of delay (⚠️ unit of time not stated)
  congestion_level     text,                     -- 'Low', 'Medium', 'High'
  reliability          text,                     -- 'Reliable', 'Unreliable'
  truck_reliability    text,                     -- 'Good', 'Fair', 'Poor'
  congested_speed_mph  real,
  freeflow_speed_mph   real,
  geom                 geometry(MultiLineString, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null,
  primary key (year, segment_id)
);
create index congestion_measure_geom on obs.congestion_measure using gist (geom);
comment on table obs.congestion_measure is
  'COMPASS; not offered as open data. Internal use until COMPASS answers: do not republish.';

-- Travel times of COMPASS's 16 regional commutes (14 trips, two of them by two
-- routes), AM and PM peak.
create table obs.commute_travel_time (
  commute              text not null,            -- 'Caldwell to Boise'
  route                text not null,            -- 'I-84/I-184' or 'SH 20/26'
  period               text not null,            -- 'AM', 'PM'
  year                 smallint not null,
  freeflow_min         real,
  average_min          real,
  median_min           real,
  p80_min              real,
  p95_min              real,
  travel_time_index    real,
  lottr                real,                     -- 80th / 50th percentile (COMPASS's "level of reliability")
  geom                 geometry(MultiLineString, 4326),
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null,
  primary key (commute, route, period, year)
);
comment on table obs.commute_travel_time is
  'COMPASS; not offered as open data. Internal use until COMPASS answers: do not republish.';
