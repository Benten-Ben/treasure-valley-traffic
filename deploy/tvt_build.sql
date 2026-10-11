-- tvt_build: the capped database role that builds and loads run as (landscape sprint plan, F6).
--
-- Builds and loads run as tvt_build, on the scratch database while a branch is unmerged and on
-- production through the deploy runbook. The role exists so that a build can't take the
-- server down: production's own settings are statement_timeout 0 and temp_file_limit -1.
-- It's also the least a build needs: it reads the project's schemas except the private
-- ones, writes the plugin schemas builds fill, and writes the few shared tables the core
-- helpers log to. It can't change the schema: migrations run as the database owner.
--
-- Run it as the database owner (tvt) or a superuser, in each database it should reach:
--   psql -X -v ON_ERROR_STOP=1 [-v conn_limit=6] -d tvt -f deploy/tvt_build.sql
-- and set the password separately (never here):
--   ALTER ROLE tvt_build PASSWORD '...';
--
-- It's idempotent: run it again after migrations that add schemas or tables (the scratch
-- wrapper's `migrate` does; on production it's a step of the deploy runbook). A table made
-- later by tvt in a schema that already existed at the last run gets its grants on its own
-- (default privileges, below); a new schema waits for the next run.
--
-- To change the policy, edit the lists below on your branch: a plugin schema builds fill goes
-- in build_schemas; a shared table a build writes goes in shared_writes with the least it needs.
-- This file never revokes: to take a grant back, REVOKE it by hand and remove it here.
-- What tvt_build holds now: deploy/scratch/README.md, "What tvt_build can do".

\if :{?conn_limit}
\else
\set conn_limit 6
\endif

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tvt_build') AS tvt_build_missing \gset
\if :tvt_build_missing
CREATE ROLE tvt_build LOGIN;
\endif

-- A login, nothing more: no superuser, no new databases or roles, no replication, row
-- security applies. The connection limit keeps builds from taking the app's connections.
ALTER ROLE tvt_build LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT :conn_limit;

-- The caps (plan §4.4 and §6). temp_file_limit can only be changed by a superuser, so a build
-- can't lift it; the others are defaults a session could change, and builds don't.
ALTER ROLE tvt_build SET work_mem = '64MB';
ALTER ROLE tvt_build SET maintenance_work_mem = '512MB';
ALTER ROLE tvt_build SET max_parallel_workers_per_gather = 1;
ALTER ROLE tvt_build SET statement_timeout = '45min';
ALTER ROLE tvt_build SET temp_file_limit = '5GB';

-- Connect, and make temporary tables (builds stage their rows in them).
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO tvt_build', current_database()) \gexec

DO $grants$
DECLARE
  -- Schemas a build reads. Never restricted (people in crashes) or a private plugin's schema
  -- (city_trees: the City of Boise's trees, which builds must never read): a schema missing from
  -- both lists gets nothing.
  read_schemas text[] := ARRAY['core', 'obs', 'evt', 'raw', 'ops', 'public'];
  -- Plugin schemas builds fill: read, and write any table in them. (No CREATE: tables come from
  -- migrations, staging goes in temporary tables.)
  build_schemas text[] := ARRAY['roads', 'soils', 'farm', 'water', 'trails', 'fences', 'hazards', 'trees'];
  -- Shared tables a load or build writes through the core helpers, and only what each needs.
  shared_writes text[] := ARRAY[
    'ops.source',          'INSERT, UPDATE',           -- db.ensure_source: a source's registry row
    'ops.fetch',           'INSERT, UPDATE',           -- db.Fetch: one row per load
    'ops.layer_signature', 'INSERT, UPDATE',           -- compass_layer: a layer's change check
    'raw.record',          'INSERT, UPDATE',           -- db.store_records, removals: versions are never deleted
    'evt.event',           'INSERT, UPDATE',           -- ingest/events.py: lifecycles (the canal season)
    'core.source_link',    'INSERT, UPDATE, DELETE',   -- match evidence (water, trails)
    'core.layer_version',  'INSERT, UPDATE, DELETE',   -- S2: each build writes its row
    'ops.build_pending',   'INSERT, UPDATE, DELETE'    -- M1: a build clears its mark
  ];
  db_owner text := (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database());
  s text;
  rel regclass;
  seq text;
  i int;
BEGIN
  FOREACH s IN ARRAY read_schemas || build_schemas LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO tvt_build', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('GRANT SELECT ON ALL SEQUENCES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON TABLES TO tvt_build', db_owner, s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON SEQUENCES TO tvt_build', db_owner, s);
  END LOOP;

  FOREACH s IN ARRAY build_schemas LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s);
    -- MAINTAIN (PostgreSQL 17): ANALYZE, VACUUM and REFRESH MATERIALIZED VIEW after a build.
    EXECUTE format('GRANT INSERT, UPDATE, DELETE, TRUNCATE, MAINTAIN ON ALL TABLES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('GRANT USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT INSERT, UPDATE, DELETE, TRUNCATE, MAINTAIN ON TABLES TO tvt_build', db_owner, s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE, UPDATE ON SEQUENCES TO tvt_build', db_owner, s);
  END LOOP;

  FOR i IN 1 .. array_length(shared_writes, 1) / 2 LOOP
    rel := to_regclass(shared_writes[2 * i - 1]);
    CONTINUE WHEN rel IS NULL;                      -- not made yet (S2's and M1's tables)
    EXECUTE format('GRANT %s ON TABLE %s TO tvt_build', shared_writes[2 * i], rel);
    -- The sequences behind its serial and identity columns.
    FOR seq IN
      SELECT pg_get_serial_sequence(rel::text, quote_ident(a.attname))
        FROM pg_attribute a
       WHERE a.attrelid = rel AND a.attnum > 0 AND NOT a.attisdropped
         AND pg_get_serial_sequence(rel::text, quote_ident(a.attname)) IS NOT NULL
    LOOP
      EXECUTE format('GRANT USAGE ON SEQUENCE %s TO tvt_build', seq);
    END LOOP;
  END LOOP;
END
$grants$;
