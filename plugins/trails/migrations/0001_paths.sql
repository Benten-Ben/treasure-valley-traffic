-- trails 0001: OpenStreetMap's paths, tracks and walking, cycling and riding routes, with Ridge
-- to Rivers' trails and the Greenbelt's closures linked onto them (landscape sprint, Oct 2026:
-- plan C1, C2, C10, C18, package P6-data).
--
-- The trails schema holds the plugin's own tables. Readings stay where they are: R2R's trails and
-- the Greenbelt's closures and detours are versions in raw.record and lifecycles in evt.event,
-- written by the plugin's two pollers. Nothing here copies them.
--
-- * The osm_paths consumer of core's OpenStreetMap loader (ingest/osm_extract.py,
--   plugins/trails/ingest/sources/osm_paths.py) writes trails.osm_path (the highway ways the
--   partition gives it: path, footway but sidewalks and crossings, cycleway, track, bridleway,
--   steps, pedestrian), trails.osm_area (pedestrian and footway areas) and trails.osm_route (the
--   hiking, mtb, bicycle, foot and horse route relations). Approved by the owner, Oct 8 (the
--   classes in the landscape row; decision 2c for the routes). Versioned in place (plan C2): no
--   raw.record copies; osm_version and osm_timestamp are OpenStreetMap's, first_seen and
--   last_seen the loads that first and last brought it, and an object missing from a load
--   becomes inactive and is never deleted. License ODbL (© OpenStreetMap contributors), republish
--   yes.
-- * The access rules (plan C18) are columns and views: a way tagged access=private or no (unless a
--   trail mode opens it: foot, bicycle or horse = yes, permissive, designated or official) isn't
--   a trail; informal=yes ways are drawn only close in, worded, and hidden near closures; tracks
--   along canal banks are irrigation access (trails.canal_track, written by trails-match once
--   water's reaches exist; cut-first).
-- * trails-match (plugins/trails/ingest/match.py) links the agencies' lines to OpenStreetMap's
--   ways with core's line matcher (ingest/linematch.py), in 150 m pieces: trails.link and
--   trails.matched_line, with each line's gap (where it draws itself). The pollers relink the
--   lines a poll changed, and the trails-match build everything. Links carry the City of Boise's
--   ids, so they're internal (republish aggregates, like their source).
--
-- The 12 lane-tagged cycleways, tracks and pedestrian ways osm_valley keeps (the partition's
-- named exception) stay in core.osm_way; trails reads them through trails.exception_way.

create schema if not exists trails;

-- ---- the access, surface and width rules, for the named exception's view ------------------
-- plugins/trails/ingest/sources/osm_paths.py applies the same rules when it loads a way, in
-- Python; a database test runs both over the same tags and asserts they agree.

-- OpenStreetMap's surface tag in four classes: paved, gravel, dirt, or unknown (a value none of
-- these name); null when untagged.
create function trails.surface_class(surface text) returns text
language sql immutable parallel safe as $$
  select case
    when surface is null then null
    when lower(btrim(surface)) in ('asphalt', 'paved', 'paving_stones', 'bricks', 'sett', 'wood', 'metal', 'chipseal')
      or lower(btrim(surface)) like 'concrete%' then 'paved'
    when lower(btrim(surface)) in ('gravel', 'fine_gravel', 'compacted', 'pebblestone') then 'gravel'
    when lower(btrim(surface)) in ('dirt', 'ground', 'earth', 'sand', 'grass', 'mud', 'rock', 'unpaved') then 'dirt'
    else 'unknown' end
$$;

-- The surface when untagged, by kind (marked default): cycleways paved, tracks dirt.
create function trails.surface_default(kind text) returns text
language sql immutable parallel safe as $$
  select case kind when 'cycleway' then 'paved' when 'track' then 'dirt' end
$$;

-- A way closed to the public (plan C18): access=private or no, unless foot, bicycle or horse is
-- opened (yes, permissive, designated or official).
create function trails.no_public_access(tags jsonb) returns boolean
language sql immutable parallel safe as $$
  select coalesce(lower(btrim(tags->>'access')) in ('private', 'no'), false)
     and not coalesce(lower(btrim(tags->>'foot')) in ('yes', 'permissive', 'designated', 'official')
                      or lower(btrim(tags->>'bicycle')) in ('yes', 'permissive', 'designated', 'official')
                      or lower(btrim(tags->>'horse')) in ('yes', 'permissive', 'designated', 'official'), false)
$$;

-- The width estimate by kind and surface class (⚠️ estimates, as for lanes): dirt or unknown path
-- 0.8 m, gravel path or bridleway 1.5 m, footway 1.8 m, paved path or cycleway 3.0 m, track
-- 3.0 m; steps 1.5 m and pedestrian ways 4.0 m (ours, not the design's).
create function trails.width_estimate(kind text, surface text) returns real
language sql immutable parallel safe as $$
  select (case kind
    when 'path' then case surface when 'paved' then 3.0 when 'gravel' then 1.5 else 0.8 end
    when 'bridleway' then 1.5
    when 'footway' then 1.8
    when 'cycleway' then 3.0
    when 'track' then 3.0
    when 'steps' then 1.5
    when 'pedestrian' then 4.0 end)::real
$$;

-- ---- what the osm_paths consumer loads -------------------------------------------------------

create table trails.osm_path (
  osm_id         bigint primary key,
  kind           text not null check (kind in ('path', 'footway', 'cycleway', 'track', 'bridleway', 'steps',
                                               'pedestrian')),
  name           text,
  ref            text,
  surface_tag    text,                              -- the surface tag as tagged
  surface        text not null check (surface in ('paved', 'gravel', 'dirt', 'unknown')),
  surface_from   text not null check (surface_from in ('osm', 'default', 'none')),
  width_m        real,                              -- the width tag in metres, when it reads as one
  width_est_m    real not null,                     -- the estimate by kind and surface (used without width_m) ⚠️
  access         text,
  foot           text,
  bicycle        text,
  horse          text,
  motor_vehicle  text,
  no_access      boolean not null,                  -- plan C18: closed to the public, so never a trail
  informal       boolean not null,                  -- informal=yes: drawn only close in, worded
  mtb_scale      text,
  sac_scale      text,
  tracktype      text,
  smoothness     text,
  oneway         text,
  bridge         boolean not null default false,
  tunnel         boolean not null default false,
  layer          smallint,
  conditional    jsonb,                             -- every *:conditional tag (seasons), or null
  tags           jsonb not null,                    -- every tag, as tagged
  geom           geometry(LineString, 4326) not null,
  length_m       real generated always as (ST_Length(geom::geography)) stored,
  osm_version    int,
  osm_timestamp  timestamptz,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  check (surface_from <> 'none' or surface = 'unknown'),
  check (not (kind in ('footway', 'path', 'cycleway')
              and coalesce(tags->>'footway', '') in ('sidewalk', 'crossing', 'access_aisle', 'traffic_island')))
);
create index osm_path_geom on trails.osm_path using gist (geom);
create index osm_path_kind on trails.osm_path (kind) where active;
create index osm_path_name on trails.osm_path (name) where active and name is not null;

comment on table trails.osm_path is
  'OpenStreetMap''s paths, tracks, footways, cycleways, bridleways, steps and pedestrian ways (osm_paths consumer). License ODbL (© OpenStreetMap contributors); republish: yes';

-- Pedestrian and footway areas (a closed way tagged area=yes, or a multipolygon): plazas and
-- squares. Kept for the paved-path base (plan C9); never a trail line.
create table trails.osm_area (
  osm_type       char(1) not null check (osm_type in ('w', 'r')),
  osm_id         bigint not null,
  kind           text not null check (kind in ('pedestrian', 'footway')),
  name           text,
  surface_tag    text,
  surface        text not null check (surface in ('paved', 'gravel', 'dirt', 'unknown')),
  access         text,
  no_access      boolean not null,
  tags           jsonb not null,
  geom           geometry(MultiPolygon, 4326) not null,
  area_m2        real generated always as (ST_Area(geom::geography)) stored,
  osm_version    int,
  osm_timestamp  timestamptz,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now(),
  primary key (osm_type, osm_id)
);
create index osm_area_geom on trails.osm_area using gist (geom);

comment on table trails.osm_area is
  'OpenStreetMap''s pedestrian and footway areas (osm_paths consumer). License ODbL (© OpenStreetMap contributors); republish: yes';

-- Hiking, mountain-bike, bicycle, foot and horse routes (relations), with their members in
-- order. Their ways are in whichever partition owner's table holds them (core.osm_way,
-- roads.osm_street, roads.osm_paving, trails.osm_path); trails-match draws each route's line
-- from them into trails.route_line.
create table trails.osm_route (
  osm_id         bigint primary key,
  route          text not null check (route in ('hiking', 'mtb', 'bicycle', 'foot', 'horse')),
  name           text,
  ref            text,
  network        text,
  operator       text,
  members        jsonb not null check (jsonb_typeof(members) = 'array'),   -- [{type, ref, role}] in order
  way_ids        bigint[] not null,                 -- its ways, in member order
  tags           jsonb not null,
  osm_version    int,
  osm_timestamp  timestamptz,
  active         boolean not null default true,
  first_seen     timestamptz not null default now(),
  last_seen      timestamptz not null default now()
);
create index osm_route_ways on trails.osm_route using gin (way_ids);

comment on table trails.osm_route is
  'OpenStreetMap''s hiking, mtb, bicycle, foot and horse route relations (osm_paths consumer). License ODbL (© OpenStreetMap contributors); republish: yes';

-- ---- built by trails-match --------------------------------------------------------------------

-- Each route's line, from its member ways in the partition owners' tables (the build's run).
create table trails.route_line (
  osm_id         bigint primary key,                -- the route relation's
  ways           int not null,                      -- member ways
  ways_found     int not null,                      -- of them, in our tables (the rest lie outside the box)
  geom           geometry(MultiLineString, 4326),
  length_m       real,
  built_at       timestamptz not null
);
create index route_line_geom on trails.route_line using gist (geom);

comment on table trails.route_line is
  'Each OpenStreetMap route''s line, from its member ways (trails-match). License ODbL (© OpenStreetMap contributors); republish: yes';

-- How an agency's line (an R2R trail, a Greenbelt closure or detour) lies on OpenStreetMap's
-- ways: one row per way, from core's line matcher run on the line's pieces of at most 150 m
-- (buffer 15 m, bearing 20°, a 60% share of the way or of the piece). overlap_m and share measure
-- the way: how much of it lies within 15 m of the pieces that matched it; line_share how much of
-- the line those pieces are. A full link (method pieces150_buffer15_bearing20): 60% of the way
-- lies along the line. A partial one (way_in_pieces150_...): 20 m or more of it does, but less,
-- since the way is longer than the line or runs on past it. A way takes its line's state only on
-- a full link; elsewhere the line draws itself (its gap, in trails.matched_line).
create table trails.link (
  source         text not null references ops.source,
  source_id      text not null,
  osm_id         bigint not null,                   -- in trails.osm_path or the named exception (core.osm_way)
  overlap_m      real,
  share          real,
  line_share     real,
  bearing_diff   real,
  confidence     real check (confidence between 0 and 1),
  method         text not null,
  matched_at     timestamptz not null,
  primary key (source, source_id, osm_id)
);
create index link_osm on trails.link (osm_id);

comment on table trails.link is
  'Agency trail lines (Ridge to Rivers, Greenbelt closures) linked to OpenStreetMap ways (trails-match). Internal: the City''s ids; republish: aggregates';

-- Each agency line's last match: the line as matched (its fingerprint) and the extract
-- osm_paths held, so a poll rematches only the lines it changed. line_id is a stable number for
-- the line (a map feature's id is -line_id where the line draws itself). The gap is where it
-- does: its stretches of 20 m or more farther than 15 m from every way it's fully linked to (the
-- whole line when it has none). So every metre of an agency's line shows its state, on a way that
-- lies along it or drawn as itself, and no way shows a state beyond the line.
create table trails.matched_line (
  line_id        bigint generated always as identity unique,
  source         text not null references ops.source,
  source_id      text not null,
  line_fp        text,                              -- raw.record payload's _geom when it was matched
  osm_md5        text,                              -- the extract osm_paths held then
  line_m         real,
  covered_m      real,                              -- of the line, within 15 m of the ways it's fully linked to
  gap            geometry(MultiLineString, 4326),   -- where the line draws itself, or null
  gap_m          real not null default 0,
  links          int not null check (links >= 0),
  matched_at     timestamptz not null,
  matched_by     text not null check (matched_by in ('poll', 'trails-match')),
  fetch_id       bigint references ops.fetch,       -- the poll's trails_match fetch, or null
  primary key (source, source_id)
);

create index matched_line_gap on trails.matched_line using gist (gap);

comment on table trails.matched_line is
  'Each agency trail line''s last match and where it draws itself (trails-match). Internal: the City''s ids and lines; republish: aggregates';

-- Tracks along a canal bank: irrigation access, not trails (plan C18; cut-first). 60% or more of
-- the track within 15 m of canal, lateral, ditch or drain reaches of water's build that match it
-- (bearing within 20°), and no access=yes|permissive. line_share is that share; reach_id the reach
-- most of it lies along.
create table trails.canal_track (
  osm_id         bigint primary key,
  reach_id       text not null,
  line_share     real,
  bearing_diff   real,
  built_at       timestamptz not null
);

comment on table trails.canal_track is
  'OpenStreetMap tracks along canal banks, taken as irrigation access (trails-match). License ODbL (© OpenStreetMap contributors); republish: yes';

-- The valley-zoom network (z10-12): the drawn ways with minzoom 10 (linked, the Greenbelt,
-- cycleways, named ways), simplified once per build (plan C4). fid is the map feature's id, the
-- way's osm_id. The agencies' own lines are in trails.agency_gap, at every zoom.
create table trails.path_lo (
  fid            bigint primary key,
  network        text not null check (network in ('r2r', 'greenbelt', 'cycleway', 'named')),
  kind           text not null,                     -- the OSM kind
  name           text,
  surface        text,
  geom           geometry(Geometry, 4326) not null,
  built_at       timestamptz not null
);
create index path_lo_geom on trails.path_lo using gist (geom);

comment on table trails.path_lo is
  'The trails network at valley zoom (trails-match). License ODbL (© OpenStreetMap contributors); republish: yes';

-- ---- views ------------------------------------------------------------------------------------

-- The partition's named exception: path-class ways osm_valley keeps (tagged with lanes), read
-- from core.osm_way, with the same columns as trails.osm_path computes on load.
create view trails.exception_way as
select w.osm_id, w.highway as kind, w.name, w.ref,
       w.tags->>'surface' as surface_tag,
       coalesce(trails.surface_class(w.tags->>'surface'), trails.surface_default(w.highway), 'unknown') as surface,
       case when w.tags ? 'surface' then 'osm' when trails.surface_default(w.highway) is not null then 'default'
            else 'none' end as surface_from,
       w.width_m,
       trails.width_estimate(w.highway, coalesce(trails.surface_class(w.tags->>'surface'),
                                                 trails.surface_default(w.highway), 'unknown')) as width_est_m,
       w.tags->>'access' as access,
       trails.no_public_access(w.tags) as no_access,
       coalesce(lower(btrim(w.tags->>'informal')) = 'yes', false) as informal,
       coalesce(w.bridge, false) as bridge, w.layer, w.tags, w.geom, ST_Length(w.geom::geography)::real as length_m,
       w.osm_version, w.osm_timestamp
from core.osm_way w
where w.active
  and w.highway in ('track', 'path', 'footway', 'cycleway', 'bridleway', 'steps', 'pedestrian')
  and not (w.highway in ('footway', 'path', 'cycleway')
           and coalesce(w.tags->>'footway', '') in ('sidewalk', 'crossing', 'access_aisle', 'traffic_island'));

-- Every way that could be a trail, from both tables: osm_path's active ways and the exception.
create view trails.any_way as
select osm_id, kind, name, ref, surface_tag, surface, surface_from, width_m, width_est_m, access, no_access,
       informal, bridge, layer, tags, geom, length_m, osm_version, osm_timestamp, 'osm_path'::text as held_in
from trails.osm_path where active
union all
select osm_id, kind, name, ref, surface_tag, surface, surface_from, width_m, width_est_m, access, no_access,
       informal, bridge, layer, tags, geom, length_m, osm_version, osm_timestamp, 'core.osm_way'::text
from trails.exception_way;

-- The ways an agency's line may be linked to: public ways that aren't irrigation access.
create view trails.target_way as
select osm_id, name, geom from trails.any_way a
where not a.no_access and not exists (select 1 from trails.canal_track c where c.osm_id = a.osm_id);

-- The agencies' current lines, from the pollers' versions in raw.record: Ridge to Rivers' trails
-- (keyed by GlobalID) and the Greenbelt's closures and detours ('construction:<id>',
-- 'detour:<id>'). line_fp is the version's line fingerprint. Internal: the City's rows.
create view trails.agency_line as
select distinct on (r.source, r.source_id)
       r.source, r.source_id,
       case when r.source = 'r2r_trails' then 'trail'
            when r.payload->>'layer' = 'detour' then 'detour' else 'closure' end as kind,
       case when r.source = 'r2r_trails' then coalesce(r.payload->>'TrailName', r.payload->>'Name')
            else coalesce(r.payload->>'PROJECT', r.payload->>'WORK_DESCRIPTION', r.payload->>'LOCATION') end as name,
       case when r.source = 'r2r_trails' then r.payload->>'SystemName' end as system,
       r.payload->>'_geom' as line_fp,
       r.geom, r.payload - '_geom' as attributes, r.first_seen, r.last_seen
from raw.record r
where r.source in ('r2r_trails', 'boise_greenbelt_closures') and r.removed_at is null
order by r.source, r.source_id, r.last_seen desc, r.first_seen desc;

-- Each agency line's state now, its match and the ways it's on: R2R's condition (state,
-- severity: open, caution, do_not_use, closed; null when not evaluated) from its active
-- trail_condition event; a Greenbelt closure in effect is 'closed', a detour 'detour', and a row
-- the City has set inactive 'ended'. `ways` are the ways the line runs along (each way's own
-- share passed), `partial` those it covers only part of (the line's share passed): a closure
-- 125 m long on a 1 km way. Internal: the City's rows (republish aggregates).
create view trails.agency_state as
with ev as (    -- each line's event in effect, found once: R2R's by trail, the Greenbelt's by row
  select distinct on (e.source, k.key) e.source, k.key, e.id, e.attributes, e.severity, e.description, e.declared,
         e.observed
  from evt.event e
  cross join lateral (select case when e.source = 'r2r_trails' then e.attributes->>'trail' else e.source_id end
                      as key) k
  where e.active and ((e.source = 'r2r_trails' and e.kind = 'trail_condition')
                      or e.source = 'boise_greenbelt_closures')
  order by e.source, k.key, lower(e.observed) desc, e.id desc)
select l.source, l.source_id, l.kind, l.name, l.system,
       case when l.source = 'r2r_trails' then coalesce(e.attributes->>'state', 'unset')
            when e.id is null then 'ended' else l.kind end as state,
       case when l.source = 'r2r_trails' then e.severity
            when e.id is null then null when l.kind = 'detour' then 'detour' else 'closed' end as severity,
       e.description as label,
       lower(e.declared) as set_at,
       lower(e.observed) as since,
       m.line_id, m.links, m.line_m, m.covered_m, m.gap_m, m.matched_at, m.osm_md5,
       coalesce(k.ways, '{}') as ways, coalesce(k.partial, '{}') as partial
from trails.agency_line l
left join ev e on e.source = l.source and e.key = l.source_id
left join trails.matched_line m on m.source = l.source and m.source_id = l.source_id
left join lateral (
  select array_agg(k.osm_id order by k.osm_id) filter (where not starts_with(k.method, 'way_in_')) as ways,
         array_agg(k.osm_id order by k.osm_id) filter (where starts_with(k.method, 'way_in_')) as partial
  from trails.link k where k.source = l.source and k.source_id = l.source_id) k on true;

-- Where the agencies' lines draw themselves (the 'trails.agency' tiles): each line's gap, with
-- fid -line_id, its feature-state key in /api/trails/status. Internal: the City's lines.
create view trails.agency_gap as
select -m.line_id as fid, m.line_id, m.source, m.source_id, l.kind, l.name, m.gap as geom, m.gap_m
from trails.matched_line m
join trails.agency_line l on l.source = m.source and l.source_id = m.source_id
where m.gap is not null;

-- The Trails layer's ways (plan C18), for the tiles and the card: every way that could be a
-- trail, with its effective surface (a path that R2R's trail runs along is dirt by default:
-- OpenStreetMap says unpaved for 94% of that length), whether it's drawn and why not, whether
-- it reads as informal (informal=yes, unless an agency's line runs along it), what links it to
-- the agencies and the Greenbelt (r2r: an R2R trail runs along it, a full link; on_r2r: any link;
-- greenbelt: a Greenbelt closure or detour on it, or a route named for the Greenbelt), and the
-- zoom it comes in at: 10 for the named network (R2R's trails, the Greenbelt, cycleways and named
-- ways), 13 for the rest, 16 for informal ways.
create view trails.path as
select a.osm_id, a.kind, a.name, a.ref, a.held_in,
       case when a.surface_from = 'none' and lk.r2r then 'dirt' else a.surface end as surface,
       case when a.surface_from = 'none' and lk.r2r then 'default' else a.surface_from end as surface_from,
       case when a.surface_from = 'none' and lk.r2r then 'Ridge to Rivers trail'
            when a.surface_from = 'default' then a.kind end as surface_default,
       coalesce(a.width_m, a.width_est_m) as width_m,
       case when a.width_m is not null then 'osm' else 'estimated' end as width_from,
       a.access, a.no_access,
       a.informal and not coalesce(lk.on_r2r or lk.closure, false) as informal,
       (c.osm_id is not null) as canal_track,
       not a.no_access and c.osm_id is null as drawn,
       case when a.no_access then 'private, no public access'
            when c.osm_id is not null then 'irrigation access along a canal' end as not_drawn,
       coalesce(lk.r2r, false) as r2r, coalesce(lk.on_r2r, false) as on_r2r,
       coalesce(lk.closure, false) or gb.on_greenbelt as greenbelt,
       case when a.informal and not coalesce(lk.on_r2r or lk.closure, false) then 16
            when coalesce(lk.on_r2r or lk.closure, false) or gb.on_greenbelt or a.kind = 'cycleway'
                 or a.name is not null then 10
            else 13 end as minzoom,
       a.bridge, a.layer, a.length_m, a.tags, a.geom, a.osm_version, a.osm_timestamp
from trails.any_way a
left join trails.canal_track c on c.osm_id = a.osm_id
left join lateral (
  select bool_or(k.source = 'r2r_trails' and not starts_with(k.method, 'way_in_')) as r2r,
         bool_or(k.source = 'r2r_trails') as on_r2r, bool_or(k.source = 'boise_greenbelt_closures') as closure
  from trails.link k where k.osm_id = a.osm_id) lk on true
cross join lateral (
  select exists (select 1 from trails.osm_route r
                 where r.active and r.way_ids @> array[a.osm_id] and r.name ilike '%greenbelt%') as on_greenbelt) gb;

-- Informal ways near a closure (plan C18: hidden inside closures): within near_m of an agency
-- line that's closed now (an R2R trail CLOSED, a Greenbelt closure in effect). R2R closes
-- trails, not areas, and we hold no land manager's area closures yet, so "inside" is "near".
create function trails.hidden_informal(near_m double precision default 100)
returns table (osm_id bigint, source text, source_id text)
language sql stable as $$
  with closed as materialized (
    select s.source, s.source_id, l.geom
    from trails.agency_state s
    join trails.agency_line l on l.source = s.source and l.source_id = s.source_id
    where s.severity = 'closed' and l.geom is not null),
  informal as materialized (
    select p.osm_id, p.geom from trails.any_way p
    where p.informal and not exists (select 1 from trails.link k where k.osm_id = p.osm_id))
  select distinct on (i.osm_id) i.osm_id, c.source, c.source_id
  from informal i
  join closed c on i.geom && ST_Expand(c.geom, near_m / 75000.0)   -- a box first: 75 km a degree or more here
                and ST_DWithin(i.geom::geography, c.geom::geography, near_m)
  order by i.osm_id, c.source, c.source_id
$$;
