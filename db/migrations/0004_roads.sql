-- 0004: road segments with posted speeds, class and direction (Oct 5, 2026).
-- Ada County, from ACHD's open road centerline layer. Which network becomes
-- the long-term reference (Overture, OSM, ITD) is still open (docs/12
-- decision 5); ACHD's attributes can be attached to it later.

create table core.road_segment (
  id                   bigint generated always as identity primary key,
  achd_perm_id         bigint unique,              -- ACHD's PermID, stable across edits
  name                 text,                       -- 'W Fairview Ave'
  functional_class     text,                       -- ACHD FuncClass: Local, Collector, Minor/Principal Arterial, Interstate, Ramp, Driveway, Alley, Parks
  posted_speed_mph     smallint,                   -- ACHD PostSpeed
  emergency_speed_mph  smallint,                   -- ACHD EmergSpeed (emergency routing speed)
  one_way              text check (one_way in ('both', 'forward', 'backward')),  -- relative to the line's own direction
  private              boolean,
  from_level           smallint,                   -- ACHD FromElev/ToElev: 10 at grade, 20 elevated (bridges, overpasses)
  to_level             smallint,
  community            text,                       -- e.g. 'Boise', 'Meridian'
  geom                 geometry(MultiLineString, 4326) not null,
  active               boolean not null default true,  -- false once gone from ACHD's layer
  first_seen           timestamptz not null default now(),
  last_seen            timestamptz not null default now()
);
create index road_segment_geom on core.road_segment using gist (geom);
create index road_segment_class on core.road_segment (functional_class);
