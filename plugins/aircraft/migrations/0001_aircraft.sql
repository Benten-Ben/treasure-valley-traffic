-- aircraft/0001: aircraft positions from adsb.lol's open API, and the FAA's
-- aircraft registry (plugins/aircraft; owner approved Oct 7, 2026).
--
-- adsb.lol's data is ODbL 1.0 (credit "© adsb.lol contributors"; derived
-- databases we publish stay ODbL). The FAA registry is a US government work,
-- so public domain.
--
-- Vehicles, not owners (plugins/aircraft/README.md):
--   - aircraft flagged LADD or PIA are stored without identity: their key is
--     'anon:' plus 12 hex characters of a per-day hash, with no callsign, and
--     they never enter core.aircraft_seen (the checks below hold that);
--   - the registry keeps no names or addresses: the parser drops them as the
--     file is read, and these tables have no columns for them.

create schema if not exists obs;

-- One position report: a new position since the aircraft's previous row.
-- adsb.lol's dbFlags 1 (military) goes in extra as "mil".
create table obs.aircraft_position (
  observed_at       timestamptz not null,       -- the position's own time: the response's `now` minus `seen_pos`
  aircraft_key      text not null,              -- ICAO hex ('a1b2c3'; '~' first for a non-ICAO address), or 'anon:<12 hex>'
  geom              geometry(Point, 4326) not null,
  alt_baro_ft       int,                        -- barometric altitude; null on the ground
  alt_geom_ft       int,                        -- geometric (GNSS) altitude
  on_ground         boolean,                    -- null when the report doesn't say
  gs_kt             real,                       -- ground speed, knots
  track_deg         real,                       -- over the ground, degrees true
  true_heading_deg  real,
  baro_rate_fpm     int,
  geom_rate_fpm     int,
  squawk            text,
  emergency         text,                       -- 'general', 'lifeguard', 'minfuel', ...; null for 'none'
  category          text,                       -- emitter category 'A0'..'D7' (A7: rotorcraft)
  icao_type         text,                       -- type designator from adsb.lol's database ('C172', 'B407')
  callsign          text,                       -- null for anonymous aircraft
  position_source   text not null check (position_source in ('adsb', 'mlat', 'adsr', 'tisb', 'other')),
  extra             jsonb,                      -- the raw source type, position quality, selected altitude, "mil"
  primary key (aircraft_key, observed_at),
  check (aircraft_key ~ '^(~?[0-9a-f]{6}|anon:[0-9a-f]{12})$'),
  check (aircraft_key not like 'anon:%' or callsign is null)
);
-- "Tracks between t0 and t1 in a bbox": time picks the chunks (or the time
-- index below), the spatial index the box; the primary key serves one aircraft.
create index aircraft_position_geom on obs.aircraft_position using gist (geom);

-- With TimescaleDB (on the server): a hypertable in 1-day chunks (about
-- 100,000 positions a day), compressed after 7 days and kept. Without it
-- (local tests): a plain table with its own time index.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'timescaledb') then
    create extension if not exists timescaledb;
    perform create_hypertable('obs.aircraft_position', 'observed_at',
                              chunk_time_interval => interval '1 day');
    alter table obs.aircraft_position set (timescaledb.compress,
                                           timescaledb.compress_segmentby = 'aircraft_key',
                                           timescaledb.compress_orderby = 'observed_at');
    perform add_compression_policy('obs.aircraft_position', interval '7 days');
  else
    create index aircraft_position_time on obs.aircraft_position (observed_at desc);
  end if;
end $$;

-- What each identified aircraft last said about itself: the latest of each
-- field seen (a field missing from a report keeps its last value).
-- Registration and type come from adsb.lol's aircraft database. Anonymous
-- aircraft never have a row: an aircraft seen flagged LADD or PIA has its
-- row deleted.
create table core.aircraft_seen (
  hex           text primary key check (hex ~ '^[0-9a-f]{6}$'),
  icao_type     text,
  category      text,
  callsign      text,
  registration  text,
  military      boolean not null default false,   -- adsb.lol's dbFlags 1
  first_seen    timestamptz not null,
  last_seen     timestamptz not null
);

-- The FAA's registry, one row per N-number, from its weekly download. Only
-- what the aircraft is: never a registrant's name or address (dropped as the
-- file is read). Rows gone from the latest file are kept with active = false.
create table core.aircraft_registry (
  n_number             text primary key,            -- 'N12345' (the file writes it without the N)
  mode_s_hex           text,                        -- lowercase: the join key to adsb.lol's hex
  mfr_mdl_code         text,                        -- the FAA's code: manufacturer (3), model (2), series (2)
  manufacturer         text,
  model                text,                        -- the FAA's model name, series included ('172S')
  year_mfr             smallint,
  type_aircraft        text,                        -- 'fixed wing single engine', 'rotorcraft', 'glider', ...
  type_engine          text,                        -- 'reciprocating', 'turbo-shaft', 'turbo-fan', ...
  engine_count         smallint,
  engine_mfr           text,
  engine_model         text,
  seats                smallint,
  weight_class         smallint,                    -- 1: up to 12,499 lb; 2: 12,500-19,999; 3: 20,000 and over; 4: UAV up to 55 lb
  registrant_type      text,                        -- 'individual', 'partnership', 'corporation', 'co-owned', 'government', 'llc', ...
  status_code          text,                        -- the FAA's registration status code ('V': valid)
  airworthiness_class  text,                        -- 'standard', 'experimental', 'light sport', ...
  certification        text,                        -- the full code: the class, then its operation codes
  last_action_date     date,                        -- the registry's last activity on this record
  active               boolean not null default true,
  first_seen           timestamptz not null,
  last_seen            timestamptz not null
);
create index aircraft_registry_hex on core.aircraft_registry (mode_s_hex) where active;

-- One row per identified aircraft we've seen, with what the FAA registry says
-- about it (US aircraft; null elsewhere). Never anonymous aircraft: they have
-- no row in core.aircraft_seen.
create view core.aircraft as
select s.hex, s.icao_type, s.category, s.callsign, s.registration, s.military, s.first_seen, s.last_seen,
       r.n_number, r.manufacturer, r.model, r.year_mfr, r.type_aircraft, r.type_engine, r.engine_count,
       r.seats, r.weight_class, r.registrant_type, r.status_code, r.airworthiness_class
from core.aircraft_seen s
left join lateral (
  select * from core.aircraft_registry r
  where r.mode_s_hex = s.hex and r.active
  order by r.last_action_date desc nulls last
  limit 1) r on true;
