-- 0019: what each OpenStreetMap consumer loaded last (landscape sprint, Oct 2026: plan C1 and
-- C2, package S1). Numbered 0019 by the sprint (0020 is S2's core.layer_version, 0021 M1's
-- staleness view); db/migrate.py applies any file not yet applied, in name order.
--
-- One extract, downloaded by hand, is read by several plugins' consumers (their plugin.json's
-- osm_consumers; ingest/osm_extract.py): roads.osm_valley, roads.osm_street, and later
-- roads.osm_paving, trails.osm_paths, water.osm_waterways and fences.osm_barriers. Each keeps
-- its own MD5 gate, so a consumer added later loads the extract we already hold
-- (`python3 -m ingest osm-load --only <consumer>`) without reloading the others. This table is
-- that gate: one row per consumer, the extract it loaded last. Kept in the database, it
-- follows its database (a scratch copy's state is its own). osm_valley keeps its own gate in
-- $TVT_ARCHIVE/osm/last-loaded.json, as before, and has no row here.
--
-- Each load is also an ops.fetch row under the consumer's source name (fetch_id is the last).

create table ops.osm_consumer (
  consumer     text primary key check (consumer ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'),  -- '<plugin>.<source>'
  source       text not null references ops.source,   -- its ops.source row (the consumer's source name)
  md5          text not null check (md5 ~ '^[0-9a-f]{32}$'),
  extract_file text not null,                         -- the extract's name in $TVT_ARCHIVE/osm/
  data_as_of   text,                                  -- the extract's own timestamp (Geofabrik's header), if any
  loaded_at    timestamptz not null default now(),
  fetch_id     bigint references ops.fetch,
  objects      bigint check (objects >= 0),           -- objects in that load
  counts       jsonb not null default '{}'            -- what the load did: new, changed, retired, dropped ...
);

comment on table ops.osm_consumer is
  'Each OpenStreetMap consumer''s last load (its MD5 gate): python3 -m ingest osm-load (ingest/osm_extract.py)';
