-- tvt_tiles: the role the app's tile pool reads as (landscape sprint plan C3 and C4, package S2).
--
-- Toggled layers' tiles (/api/<plugin>/tiles/<layer>/{z}/{x}/{y}, app/src/lib/server/mvt.ts) go
-- to anyone who can open the map, so their cuts may read only what a tile may show: each tile
-- plugin's own schema, and core. Never `restricted` (the people in crash records, docs/12 §12.8)
-- or a private plugin's schema (`private_<name>`, and `city_trees`: the City of Boise's trees,
-- which nothing in the landscape work may read). mvt.ts refuses a definition whose tables break
-- that rule; this role makes the database refuse it too, for a layer's own `cut` as well.
--
-- tvt_tiles can't log in. The app connects as its usual role and its tile connections switch to
-- tvt_tiles (TILES_DB_ROLE in deploy/docker-compose.yml). Before this file has run in a database,
-- those connections fail and the tile route answers 500; nothing else in the app uses the role.
--
-- Run it as a superuser (tvt on the server; postgres on a laptop's test cluster), in each
-- database the app uses:
--   psql -X -v ON_ERROR_STOP=1 -d tvt -f deploy/tvt_tiles.sql
-- It's idempotent: run it again after migrations that add a schema (the deploy runbook does,
-- beside deploy/tvt_build.sql). A table made later by the database owner in a schema that was
-- granted at the last run gets its grant on its own (default privileges); a new schema waits for
-- the next run, and until then its tiles answer empty with `x-tile-status: denied` (logged).
--
-- To serve tiles from a new plugin's schema, add it to tile_schemas below on your branch. The
-- app's unit tests check that every registered layer's schema is listed here, and that nothing
-- listed is one tiles must never read.

DO $tiles$
DECLARE
  -- Schemas tiles read: core, and the plugins' own schemas (plan C3).
  tile_schemas text[] := ARRAY['core', 'roads', 'soils', 'farm', 'water', 'trails', 'fences', 'hazards', 'trees'];
  db_owner text := (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database());
  s text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tvt_tiles') THEN
    CREATE ROLE tvt_tiles NOLOGIN;
  END IF;
  -- Nothing but reads: no login, no superuser, no new databases or roles, row security applies.
  ALTER ROLE tvt_tiles NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

  -- The app's own role (the database owner) may switch to it. A superuser may anyway.
  IF NOT pg_has_role(db_owner, 'tvt_tiles', 'MEMBER') THEN
    EXECUTE format('GRANT tvt_tiles TO %I', db_owner);
  END IF;

  FOREACH s IN ARRAY tile_schemas LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO tvt_tiles', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO tvt_tiles', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON TABLES TO tvt_tiles', db_owner, s);
  END LOOP;

  -- What tiles never read: take back anything granted there, by hand or by mistake.
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE nspname IN ('restricted', 'city_trees') OR nspname LIKE 'private\_%' LOOP
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM tvt_tiles', s);
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM tvt_tiles', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE ALL ON TABLES FROM tvt_tiles', db_owner, s);
  END LOOP;
END
$tiles$;
