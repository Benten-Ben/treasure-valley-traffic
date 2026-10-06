-- 0006: side-by-side transit ribbons (docs/14 §14.4 "Side-by-side ribbons",
-- §14.8 "Schema"; approved by the owner Oct 6, 2026, Q4).
--
-- Routes that share a street are drawn side by side. The corridor graph is
-- built from VRT's own shapes by ingest/transit_ribbons.py whenever the
-- shapes or the set of dormant routes change: each row is one atomic piece of
-- shared centreline with the routes on it, left to right looking along geom.
-- A rebuild replaces every row inside a savepoint, so a failed build keeps the
-- previous ribbons. Until the first build, /api/transit/network serves each
-- route's plain shapes instead.

create table core.transit_ribbon (
  segment_id int primary key,
  geom       geometry(LineString, 4326) not null,  -- shared centreline piece
  routes     text[] not null,                      -- left to right, looking along geom; dormant routes take no slot
  length_m   real not null,
  hub        boolean not null default false,       -- midpoint within 300 m of a stop served by 6 or more routes
  build      text not null                         -- sha of shapes + dormant set + parameters, then of the colors
);
create index transit_ribbon_geom on core.transit_ribbon using gist (geom);

-- The owner can lock a route's color; the assignment never changes a pinned one.
alter table core.transit_route add column color_pinned boolean not null default false;
