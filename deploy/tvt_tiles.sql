-- tvt_tiles: the login the app's tile pool connects as (landscape sprint plan C3 and C4, package S2).
--
-- Toggled layers' tiles (/api/<plugin>/tiles/<layer>/{z}/{x}/{y}, app/src/lib/server/mvt.ts) go to
-- anyone who can open the map, so their cuts may read only what a tile may show: each tile
-- plugin's own schema, and core. Never `restricted` (the people in crash records, docs/12 §12.8)
-- or a private plugin's schema (`private_<name>`, and `city_trees`: the City of Boise's trees,
-- which nothing in the landscape work may read). mvt.ts refuses a definition whose tables break
-- that rule; this login makes the database refuse it too, for a layer's own `cut` as well.
-- Inside the schemas it reads, a few tables stay out too (never_tables below): internal free
-- text a plugin keeps beside its tile data, such as ACHD's field notes in roads.bike_facility_note.
--
-- It's a login of its own, not a role the app's connections switch to: the app's role (tvt) is a
-- superuser, and a superuser's session can always SET ROLE back. tvt_tiles is no superuser and a
-- member of no other role, so a session that logged in as it stays it. It can't write, and it can
-- read only the schemas below. The app's tile pool connects with TILES_DATABASE_URL, which
-- deploy/docker-compose.yml builds from TILES_DB_PASSWORD in deploy/.env. Until this file has run
-- and the password is set, those connections fail and the tile route answers 500; nothing else
-- in the app uses the login.
--
-- Run it as a superuser (tvt on the server; postgres on a laptop's test cluster), in each
-- database the app uses:
--   psql -X -v ON_ERROR_STOP=1 [-v conn_limit=10] -d tvt -f deploy/tvt_tiles.sql
-- and set the password separately (never here), the same as TILES_DB_PASSWORD in deploy/.env:
--   ALTER ROLE tvt_tiles PASSWORD '...';
--
-- It's idempotent: run it again after migrations that add a schema or a table on never_tables
-- (a deploy step after the migrations, beside deploy/tvt_build.sql). A table made later by the
-- database owner in a schema that was granted at the last run gets its grant on its own (default
-- privileges), and so does a table on never_tables, until this runs again; a new schema waits for
-- the next run, and until then its tiles answer empty with `x-tile-status: denied` (logged).
-- It ends by checking what tvt_tiles can reach, PUBLIC's grants included, and fails if that's
-- more than it should be.
--
-- To serve tiles from a new plugin's schema, add it to tile_schemas below on your branch. The
-- app's unit tests check that every registered layer's schema is listed here, and that nothing
-- listed is one tiles must never read.

\if :{?conn_limit}
\else
\set conn_limit 10
\endif

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tvt_tiles') AS tvt_tiles_missing \gset
\if :tvt_tiles_missing
CREATE ROLE tvt_tiles LOGIN;
\endif

-- A login, nothing more: no superuser, no new databases or roles, no replication, row security
-- applies. The app and the preview's app-next hold 3 connections each; the limit leaves the rest
-- of the server's connections to everyone else.
ALTER ROLE tvt_tiles LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT :conn_limit;

-- What the tile pool sets for itself, as the defaults for any session of this login too.
ALTER ROLE tvt_tiles SET default_transaction_read_only = on;
ALTER ROLE tvt_tiles SET statement_timeout = '3s';

SELECT format('GRANT CONNECT ON DATABASE %I TO tvt_tiles', current_database()) \gexec

DO $tiles$
DECLARE
  -- Schemas tiles read: core, and the plugins' own schemas (plan C3).
  tile_schemas text[] := ARRAY['core', 'roads', 'soils', 'farm', 'water', 'trails', 'fences', 'hazards', 'trees'];
  -- Tables in those schemas that tiles never read: internal free text, republish no. A plugin
  -- that keeps such a table beside its tile data adds it here on its branch.
  never_tables text[] := ARRAY[
    'roads.bike_facility_note'   -- ACHD's free-text Comments and FieldNotes (roads 0004)
  ];
  t text;
  db_owner text := (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database());
  s text;
  r record;
BEGIN
  -- A member of no other role, so it holds nobody else's privileges and can't SET ROLE to anyone.
  FOR r IN SELECT g.rolname AS role, pg_get_userbyid(m.grantor) AS grantor
             FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
            WHERE m.member = 'tvt_tiles'::regrole LOOP
    EXECUTE format('REVOKE %I FROM tvt_tiles GRANTED BY %I', r.role, r.grantor);
  END LOOP;

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
  -- And the tables tiles never read in the schemas they do (the grants above gave them back).
  FOREACH t IN ARRAY never_tables LOOP
    CONTINUE WHEN to_regclass(t) IS NULL;
    EXECUTE format('REVOKE ALL ON TABLE %s FROM tvt_tiles', to_regclass(t));
  END LOOP;

  -- The check: what the login can reach now, through PUBLIC too (which the revokes above can't
  -- take back). Any of these stops the run, and the deploy, until it's fixed by hand.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tvt_tiles' AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb)) THEN
    RAISE EXCEPTION 'tvt_tiles must be a plain login';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = 'tvt_tiles'::regrole) THEN
    RAISE EXCEPTION 'tvt_tiles is still a member of another role';
  END IF;
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE (nspname IN ('restricted', 'city_trees') OR nspname LIKE 'private\_%')
              AND has_schema_privilege('tvt_tiles', oid, 'USAGE') LOOP
    RAISE EXCEPTION 'tvt_tiles can still use schema % (granted to PUBLIC?): revoke it there', s;
  END LOOP;
  FOREACH t IN ARRAY never_tables LOOP
    IF to_regclass(t) IS NOT NULL AND has_any_column_privilege('tvt_tiles', to_regclass(t), 'SELECT') THEN
      RAISE EXCEPTION 'tvt_tiles can still read % (granted to PUBLIC?): revoke it there', t;
    END IF;
  END LOOP;
END
$tiles$;
