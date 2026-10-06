-- 0005: routes inferred for live bus trips the feed doesn't label (Oct 5, 2026).
-- Since VRT's Oct 1 service changes, about a quarter of live trips carry a
-- numeric trip ID that names no route and isn't in the static schedule. Such a
-- trip is matched to the route whose shapes its fixes follow. Matches live here,
-- beside the fixes, so obs.vehicle_position stays exactly as the feed reported.

create table obs.trip_route_match (
  trip_id          text not null,
  service_date     date not null,         -- local (America/Boise) date of the trip's first fix
  route_id         text not null,
  share            real not null,         -- share of the trip's fixes within near_m of this route's shapes
  runner_up        text,                  -- the next-best route, and its share
  runner_up_share  real,
  fixes            int not null,
  method           text not null,         -- e.g. 'shape_40m'
  matched_at       timestamptz not null default now(),
  primary key (trip_id, service_date)
);
