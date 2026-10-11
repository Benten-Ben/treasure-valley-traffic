-- 0020: versions of the toggled layers' vector tiles (landscape sprint, Oct 2026: plan C4,
-- package S2). Numbered 0020 because the sprint gave 0019 to the core OSM loader (S1) and
-- 0021 to the staleness view (M1); db/migrate.py applies any file not yet applied, in name
-- order, so these can land in any order.
--
-- Toggled layers (soils, crop fields, trails, burn scars, ...) are cut by PostGIS on request
-- at /api/<plugin>/tiles/<layer>/{z}/{x}/{y}?v= (app/src/lib/server/mvt.ts). Each build that
-- changes what a layer's tiles show adds a row here, in the same transaction as its data
-- (ingest/layer_version.py). The newest row of a layer (the highest id) is its current
-- version: /api/meta reports it as versions.layers['<plugin>.<layer>'], and the tile route
-- caches tiles per version, immutable while the client asks with it. A version names content,
-- so it's never reused for different data; going back to an earlier build's data adds a row
-- with that build's version again. Older rows stay as the layer's build history (a few a year
-- per layer), and their built_at gives each build's age (M1).
--
-- Every tile set records its licence class and whether it may be republished (plan C3): the
-- strictest of its inputs, in the plugin manifests' terms (docs/15 §15.2).

create table core.layer_version (
  id         bigint generated always as identity primary key,
  layer      text not null check (layer ~ '^[a-z][a-z0-9_]{0,39}\.[a-z][a-z0-9_]{0,39}$'),  -- '<plugin>.<layer>'
  version    text not null check (version ~ '^[A-Za-z0-9._-]{1,64}$'),  -- sent as ?v=, so URL-safe
  built_at   timestamptz not null default now(),
  build      text,             -- what wrote it: a build id or a command, for the record
  features   bigint check (features >= 0),
  licence    text not null,    -- 'public domain', 'ODbL', 'ODbL + ACHD/ITD widths', ...
  republish  text not null check (republish in ('yes', 'aggregates', 'internal', 'no')),
  note       text
);
create index layer_version_newest on core.layer_version (layer, id desc);

-- Each layer's current version: its newest row.
create view core.layer_version_current as
select distinct on (layer) layer, version, built_at, build, features, licence, republish, note
from core.layer_version
order by layer, id desc;

comment on table core.layer_version is
  'Versions of the toggled layers'' vector tiles (/api/<plugin>/tiles/<layer>): one row per build; the newest per layer is current';
