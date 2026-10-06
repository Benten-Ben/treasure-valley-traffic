-- 0010: from the 511 Idaho API (docs/12): message signs and what they show,
-- road-weather stations and their readings. The API's events, advisories and
-- truck restrictions go to evt.event (0009); everything else is versioned in
-- raw.record only.

-- A dynamic message sign, as 511 lists it.
create table core.message_sign (
  source_id     text primary key,               -- 511's sign Id ('ID-DMS--<n>')
  name          text,
  roadway       text,
  direction     text,
  location      text,
  geom          geometry(Point, 4326),
  first_seen    timestamptz not null,
  last_seen     timestamptz not null
);
create index message_sign_geom on core.message_sign using gist (geom);

-- What a sign showed, and when: one row per distinct set of rotating messages.
-- Blank periods (511's "NO_MESSAGE") have no row.
create table evt.sign_message (
  sign_id       text not null references core.message_sign,
  observed      tstzrange not null,             -- first seen showing it .. changed, blanked or gone (open while showing)
  messages      text[] not null,                -- in 511's order
  primary key (sign_id, observed)
);
create index sign_message_showing on evt.sign_message (sign_id) where upper_inf(observed);

-- A road-weather (RWIS) station, as 511 lists it.
create table core.weather_station (
  source_id        text primary key,            -- 511's weather station Id
  name             text,
  geom             geometry(Point, 4326),
  camera_source_id text,                        -- its camera's SourceId in 511's camera list
  status           text,                        -- latest: Normal, Alert, Freezing, ...
  first_seen       timestamptz not null,
  last_seen        timestamptz not null
);
create index weather_station_geom on core.weather_station using gist (geom);

-- One reading per station per LastUpdated. Temperatures are °F and humidity
-- is percent (511's docs); 511 doesn't state the other units (wind looks like
-- mph, visibility miles, precipitation inches, pressure inHg).
create table obs.weather_reading (
  station_id        text not null references core.weather_station,
  ts                timestamptz not null,       -- the station's LastUpdated
  air_temp_f        real,
  surface_temp_f    real,
  subsurface_temp_f real,
  dewpoint_f        real,
  relative_humidity real,
  wind_speed        real,
  wind_direction    text,
  gust_speed        real,
  gust_direction    text,
  precip_rate       real,
  precipitation     text,                       -- e.g. 'No Precipitation', 'Light Precipitation'
  precip_1h         real,
  precip_3h         real,
  precip_6h         real,
  precip_12h        real,
  precip_24h        real,
  visibility        real,
  pressure          real,
  surface_status    text,                       -- e.g. 'Dry', 'Moist', 'Wet', 'Ice'
  surface_friction  text,                       -- e.g. 'Good'
  ice_percent       real,
  status            text,
  primary key (station_id, ts)
);

-- With TimescaleDB (on the server): a hypertable in 7-day chunks (about 18,000
-- readings a day), compressed after 14 days and kept. Without it: a time index.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'timescaledb') then
    create extension if not exists timescaledb;
    perform create_hypertable('obs.weather_reading', 'ts',
                              chunk_time_interval => interval '7 days');
    alter table obs.weather_reading set (timescaledb.compress,
                                         timescaledb.compress_segmentby = 'station_id',
                                         timescaledb.compress_orderby = 'ts');
    perform add_compression_policy('obs.weather_reading', interval '14 days');
  else
    create index weather_reading_ts on obs.weather_reading (ts desc);
  end if;
end $$;
