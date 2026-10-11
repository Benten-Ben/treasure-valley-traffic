-- hazards/0001: burn scars (landscape sprint, Oct 2026: plan C15 and §3.4 K10, package P13; decision 25).
--
-- Fires that burned after the ground's photo (NAIP 2025, whose last flight day in the map box was
-- Jul 24, 2025), drawn on the painted ground in Valley only, in a neutral char tone with a stipple,
-- fading over three growing seasons. Not clickable in v1. One row per fire, refreshed from
-- raw.record's perimeter versions (source nifc_wfigs_perimeters) by the derived source `burn_scars`
-- (hourly in `ingest serve`) and by hand with `python3 -m ingest burn-scars`
-- (plugins/hazards/ingest/burn_scars.py, which explains every rule). The refresh replaces what
-- changed in one transaction and, when anything did, records a new version of the tile layer
-- 'hazards.burn_scars' in core.layer_version (migration 0020).
--
-- The fade is data, not a client rule: `seasons` counts the whole growing seasons that have passed
-- since the fire, as of the refresh, and `fade` follows from it (1, 2/3, 1/3, then 0). The three
-- days it steps down are kept with it (fade_1_on, fade_2_on, gone_on), so a time bar can show any
-- date without the rule. A scar that's gone stays in the table; burn_scar_shown leaves it out.
--
-- Licence (plan C3): WFIGS states none (NIFC disclaimer only), republish yes, credit "National
-- Interagency Fire Center (WFIGS), from IRWIN"; the same in each core.layer_version row.

create schema if not exists hazards;

create table hazards.burn_scar (
  fire_id       text primary key,      -- raw.record's source_id: the fire's IRWIN ID (upper case), or 'sg:<GlobalID>'
  name          text,                  -- the incident's name, as published
  kind          text not null check (kind in ('wildfire', 'prescribed')),
  burned_on     date not null,         -- the fire's discovery day in Boise; else its perimeter's day (dated_by)
  dated_by      text not null check (dated_by in ('discovery', 'perimeter')),
  perimeter     text not null check (perimeter in ('final', 'daily')),   -- which kind of perimeter it's drawn from
  perimeter_at  timestamptz,           -- the perimeter's own time (poly_PolygonDateTime, else poly_DateCurrent)
  acres         double precision check (acres >= 0),     -- the whole fire's, as published (not the cut part's)
  map_method    text,                  -- how the line was mapped (GPS, infrared, hand sketch, ...)
  seasons       smallint not null check (seasons between 0 and 3),   -- whole growing seasons since the fire
  fade          real generated always as (((3 - seasons) / 3.0)::real) stored,   -- 1, 2/3, 1/3, 0 (gone)
  fade_1_on     date not null,         -- the day after its first whole growing season: fade 2/3
  fade_2_on     date not null,         -- after the second: fade 1/3
  gone_on       date not null,         -- after the third: off the map
  clipped       boolean not null,      -- cut at the map box's edge
  geom          geometry(MultiPolygon, 4326) not null,   -- made valid and cut to the map box
  geom_lo       geometry(MultiPolygon, 4326) not null,   -- the same, simplified at 10 m (for z8-12)
  record_hash   bytea not null,        -- the raw.record version it's made from (version_hash)
  content_hash  bytea not null,        -- what the refresh compares, so an unchanged scar isn't rewritten
  refreshed_at  timestamptz not null,  -- when this row last changed
  check (burned_on < fade_1_on and fade_1_on < fade_2_on and fade_2_on < gone_on)
);
create index burn_scar_geom on hazards.burn_scar using gist (geom);
create index burn_scar_geom_lo on hazards.burn_scar using gist (geom_lo);

-- What the map draws now: the scars that haven't faded away. The tile route reads this.
create view hazards.burn_scar_shown as
select fire_id, kind, burned_on, seasons, fade, geom, geom_lo
from hazards.burn_scar
where seasons < 3;

comment on table hazards.burn_scar is
  'Burn scars: fires after the ground''s July 2025 photo, from the WFIGS perimeters in raw.record, with their '
  'fade over three growing seasons. Licence none stated (NIFC disclaimer only); republish yes; credit National '
  'Interagency Fire Center (WFIGS), from IRWIN';
comment on view hazards.burn_scar_shown is
  'The burn scars the map draws now (seasons < 3): read by the tile layer hazards.burn_scars';
