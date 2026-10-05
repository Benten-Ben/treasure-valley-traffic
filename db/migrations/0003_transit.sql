-- 0003: transit (docs/12; decided Oct 5, 2026). Valley Regional Transit's
-- routes, stops, shapes and trips from its static GTFS, and bus positions from
-- its GTFS-realtime feed. VRT licenses both CC BY 3.0 (credit Valley Regional
-- Transit). The raw feeds themselves are archived as files on disk, not here
-- (docs/12 decision 6).

create schema if not exists obs;

-- Routes as currently published. `color` is our map color: picked once so
-- routes that share streets differ, then kept, since a route's color follows
-- the route (ingest/sources/vrt_gtfs.py).
create table core.transit_route (
  route_id      text primary key,                 -- VRT's GTFS route_id
  short_name    text not null,                    -- '9'
  long_name     text,                             -- 'State Street'
  gtfs_color    text,                             -- VRT's own color (four shared tier colors)
  color         text,                             -- our map color, e.g. '#2a78d6'
  text_color    text,                             -- badge text on `color`: white or ink
  sort_order    int,
  active        boolean not null default true,    -- false once gone from the published feed
  feed_version  text not null,
  updated_at    timestamptz not null default now()
);

create table core.transit_stop (
  stop_id       text primary key,
  name          text,
  geom          geometry(Point, 4326) not null,
  route_ids     text[] not null default '{}',     -- routes serving it, from stop_times
  active        boolean not null default true,
  feed_version  text not null,
  updated_at    timestamptz not null default now()
);
create index transit_stop_geom on core.transit_stop using gist (geom);

create table core.transit_shape (
  shape_id      text primary key,
  route_id      text references core.transit_route,
  direction_id  smallint,
  geom          geometry(LineString, 4326) not null,
  active        boolean not null default true,
  feed_version  text not null,
  updated_at    timestamptz not null default now()
);
create index transit_shape_route on core.transit_shape (route_id);

-- Scheduled trips: for matching live trips, and for schedule adherence later.
create table core.transit_trip (
  trip_id       text primary key,
  route_id      text references core.transit_route,
  service_id    text not null,
  headsign      text,
  direction_id  smallint,
  block_id      text,
  shape_id      text,
  feed_version  text not null
);
create index transit_trip_route on core.transit_trip (route_id);

-- One GPS fix reported by a bus (a GTFS-realtime VehiclePosition). A fix
-- repeated in later snapshots is stored once.
create table obs.vehicle_position (
  ts             timestamptz not null,            -- the bus's own fix time
  vehicle_id     text not null,
  vehicle_label  text,
  trip_id        text,                            -- as the live feed gives it
  route_id       text,                            -- resolved by the recorder; null when unknown
  geom           geometry(Point, 4326) not null,
  bearing        real,
  speed_ms       real,                            -- only if the feed sends it (VRT's didn't, Oct 2026)
  stop_id        text,
  stop_sequence  int,
  status         smallint,                        -- GTFS-rt: 0 incoming at, 1 stopped at, 2 in transit to
  feed_ts        timestamptz,                     -- header time of the snapshot that carried it
  primary key (vehicle_id, ts)
);
create index vehicle_position_route_ts on obs.vehicle_position (route_id, ts desc);

-- With TimescaleDB (on the server): a hypertable in 1-day chunks, compressed
-- after 7 days and kept (docs/12 decision 7). Without it (local tests): a
-- plain table with its own time index.
do $$
begin
  if exists (select 1 from pg_available_extensions where name = 'timescaledb') then
    create extension if not exists timescaledb;
    perform create_hypertable('obs.vehicle_position', 'ts',
                              chunk_time_interval => interval '1 day');
    alter table obs.vehicle_position set (timescaledb.compress,
                                          timescaledb.compress_segmentby = 'vehicle_id',
                                          timescaledb.compress_orderby = 'ts');
    perform add_compression_policy('obs.vehicle_position', interval '7 days');
  else
    create index vehicle_position_ts on obs.vehicle_position (ts desc);
  end if;
end $$;
