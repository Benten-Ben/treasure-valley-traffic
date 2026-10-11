-- tvt_build: the capped database role that builds and loads run as (landscape sprint plan, F6).
--
-- Builds and loads run as tvt_build, on the scratch database while a branch is unmerged and on
-- production through the deploy runbook. The role exists so that a build can't take the
-- server down: production's own settings are statement_timeout 0 and temp_file_limit -1.
-- It's also the least a build needs: it reads the project's schemas except the private
-- ones, writes the plugin schemas builds fill, and writes the few shared tables the core
-- helpers log to. It can't change the schema: migrations run as the database owner.
--
-- Run it as the database owner (tvt, a superuser) in each database it should reach:
--   psql -X -v ON_ERROR_STOP=1 [-v conn_limit=6] -d tvt -f deploy/tvt_build.sql
-- and set the password separately (never here):
--   ALTER ROLE tvt_build PASSWORD '...';
--
-- It's idempotent, and the lists below are the whole policy: each run grants what they say
-- and takes back what they don't (a table narrowed or dropped from a list, a grant made by
-- hand), all in one transaction. Run it again after migrations that add schemas or tables (the
-- scratch wrapper's `migrate` does; on production it's a step of the deploy runbook). A table
-- made later by tvt in a schema that already existed at the last run gets its read (and, in a
-- build schema, write) grants on its own (default privileges); anything else waits for the
-- next run. It ends by checking what tvt_build can reach, PUBLIC's grants included, and fails
-- (changing nothing) if that's more than the lists allow.
--
-- To change the policy, edit the lists on your branch: a plugin schema builds fill goes in
-- build_schemas; a table there that builds may only add to goes in append_only; a shared table
-- a build writes goes in shared_writes with the least it needs. deploy/scratch/tests check the
-- lists; `run.sh <name> grants --check` (deploy/scratch/grant-checks.sql) checks a database.
-- What tvt_build holds now: deploy/scratch/README.md, "What tvt_build can do".
--
-- Not private, but internal: trees.tree and trees.tree_log hold rows derived from the City of
-- Boise's inventory (catalogue 'boise': its ids, trunk points, and `dbh_in` in fit and detail).
-- Builds may read them; nothing built from them may be marked republish yes.

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

-- Connect, and make temporary tables (builds stage their rows in them); never CREATE.
SELECT format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO tvt_build', current_database()) \gexec
SELECT format('REVOKE CREATE ON DATABASE %I FROM tvt_build', current_database()) \gexec

DO $grants$
DECLARE
  -- Schemas a build reads. Never restricted (people in crashes) or a private plugin's schema
  -- (private_<name>, and city_trees: the City of Boise's tree inventory, which builds must
  -- never read): a schema missing from both lists gets nothing.
  read_schemas text[] := ARRAY['core', 'obs', 'evt', 'raw', 'ops', 'public'];
  -- Plugin schemas builds fill: read, and write any table in them. (No CREATE: tables come from
  -- migrations, staging goes in temporary tables.)
  build_schemas text[] := ARRAY['roads', 'soils', 'farm', 'water', 'trails', 'fences', 'hazards', 'trees'];
  -- Tables in those schemas that builds only add to: INSERT, nothing else.
  append_only text[] := ARRAY[
    'trees.tree_log'                                -- a tree's history; survives rebuilds (plugins/trees)
  ];
  -- Shared tables a load or build writes through the core helpers, and only what each needs.
  shared_writes text[] := ARRAY[
    'ops.source',          'INSERT, UPDATE',           -- db.ensure_source: a source's registry row
    'ops.fetch',           'INSERT, UPDATE',           -- db.Fetch: one row per load
    'ops.layer_signature', 'INSERT, UPDATE',           -- compass_layer: a layer's change check
    'raw.record',          'INSERT, UPDATE',           -- db.store_records, removals: versions are never deleted
    'evt.event',           'INSERT, UPDATE',           -- ingest/events.py: lifecycles (the canal season)
    'core.source_link',    'INSERT, UPDATE, DELETE',   -- match evidence (water, trails)
    'core.layer_version',  'INSERT',                   -- S2: append-only history; each build adds its row
    'ops.build_pending',   'INSERT, UPDATE, DELETE'    -- M1: a build clears its mark
  ];
  table_writes constant text := 'INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN';
  build_writes constant text := 'INSERT, UPDATE, DELETE, TRUNCATE, MAINTAIN';
  privs constant text[] := ARRAY['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN'];
  db_owner text := (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database());
  s text;
  t text;
  p text;
  rel regclass;
  seq text;
  r record;
  i int;
  allowed text[];
  shared regclass[] := '{}';                       -- the shared tables that exist, and what each may do
  shared_privs text[] := '{}';
  appended regclass[] := '{}';
BEGIN
  -- A member of no other role: it holds nobody else's privileges and can't SET ROLE to anyone.
  FOR r IN SELECT g.rolname AS role, pg_get_userbyid(m.grantor) AS grantor
             FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
            WHERE m.member = 'tvt_build'::regrole LOOP
    EXECUTE format('REVOKE %I FROM tvt_build GRANTED BY %I', r.role, r.grantor);
  END LOOP;

  -- Read: usage and SELECT, now and for tables tvt makes later. No CREATE in any of them.
  FOREACH s IN ARRAY read_schemas || build_schemas LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s);
    EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM tvt_build', s);
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO tvt_build', s);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('GRANT SELECT ON ALL SEQUENCES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON TABLES TO tvt_build', db_owner, s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT SELECT ON SEQUENCES TO tvt_build', db_owner, s);
  END LOOP;

  -- The read schemas: no writes but the shared tables below. Everything is taken back first, so
  -- a table narrowed or dropped from shared_writes loses what it no longer has.
  FOREACH s IN ARRAY read_schemas LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s);
    EXECUTE format('REVOKE %s ON ALL TABLES IN SCHEMA %I FROM tvt_build', table_writes, s);
    EXECUTE format('REVOKE USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA %I FROM tvt_build', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE %s ON TABLES FROM tvt_build', db_owner, s, table_writes);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE USAGE, UPDATE ON SEQUENCES FROM tvt_build', db_owner, s);
  END LOOP;

  -- The build schemas: writes on every table, now and later. (MAINTAIN, PostgreSQL 17: ANALYZE,
  -- VACUUM and REFRESH MATERIALIZED VIEW after a build.)
  FOREACH s IN ARRAY build_schemas LOOP
    CONTINUE WHEN NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s);
    EXECUTE format('REVOKE REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA %I FROM tvt_build', s);
    EXECUTE format('GRANT %s ON ALL TABLES IN SCHEMA %I TO tvt_build', build_writes, s);
    EXECUTE format('GRANT USAGE, UPDATE ON ALL SEQUENCES IN SCHEMA %I TO tvt_build', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT %s ON TABLES TO tvt_build', db_owner, s, build_writes);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I GRANT USAGE, UPDATE ON SEQUENCES TO tvt_build', db_owner, s);
  END LOOP;

  -- Append-only tables: INSERT only.
  FOREACH t IN ARRAY append_only LOOP
    rel := to_regclass(t);
    CONTINUE WHEN rel IS NULL;
    EXECUTE format('REVOKE %s ON TABLE %s FROM tvt_build', table_writes, rel);
    EXECUTE format('GRANT INSERT ON TABLE %s TO tvt_build', rel);
    appended := appended || rel;
  END LOOP;

  -- Shared tables: what each needs, and the sequences behind its serial and identity columns.
  FOR i IN 1 .. array_length(shared_writes, 1) / 2 LOOP
    rel := to_regclass(shared_writes[2 * i - 1]);
    CONTINUE WHEN rel IS NULL;                      -- not made yet (S2's and M1's tables)
    EXECUTE format('GRANT %s ON TABLE %s TO tvt_build', shared_writes[2 * i], rel);
    shared := shared || rel;
    shared_privs := shared_privs || shared_writes[2 * i];
    FOR seq IN
      SELECT pg_get_serial_sequence(rel::text, quote_ident(a.attname))
        FROM pg_attribute a
       WHERE a.attrelid = rel AND a.attnum > 0 AND NOT a.attisdropped
         AND pg_get_serial_sequence(rel::text, quote_ident(a.attname)) IS NOT NULL
    LOOP
      EXECUTE format('GRANT USAGE ON SEQUENCE %s TO tvt_build', seq);
    END LOOP;
  END LOOP;

  -- What builds never read: take back anything granted there, by hand or by mistake.
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE nspname IN ('restricted', 'city_trees') OR nspname LIKE 'private\_%' LOOP
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM tvt_build', s);
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM tvt_build', s);
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM tvt_build', s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE ALL ON TABLES FROM tvt_build', db_owner, s);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM tvt_build', db_owner, s);
  END LOOP;

  -- The check: what the role can do now, through PUBLIC too (which the revokes above can't take
  -- back). Any of these stops the run, and the deploy, until it's fixed by hand.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tvt_build'
              AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)) THEN
    RAISE EXCEPTION 'tvt_build must be a plain login';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = 'tvt_build'::regrole) THEN
    RAISE EXCEPTION 'tvt_build is still a member of another role';
  END IF;
  IF NOT (SELECT rolconfig @> ARRAY['work_mem=64MB', 'maintenance_work_mem=512MB', 'max_parallel_workers_per_gather=1',
                                    'statement_timeout=45min', 'temp_file_limit=5GB']
            FROM pg_roles WHERE rolname = 'tvt_build') THEN
    RAISE EXCEPTION 'tvt_build is missing one of its caps';
  END IF;
  IF has_database_privilege('tvt_build', current_database(), 'CREATE') THEN
    RAISE EXCEPTION 'tvt_build can create schemas in % (granted to PUBLIC?): revoke it there', current_database();
  END IF;
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE nspname NOT IN ('pg_catalog', 'information_schema') AND nspname NOT LIKE 'pg\_%'
              AND has_schema_privilege('tvt_build', oid, 'CREATE') LOOP
    RAISE EXCEPTION 'tvt_build can create objects in schema % (granted to PUBLIC?): revoke it there', s;
  END LOOP;
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE (nspname IN ('restricted', 'city_trees') OR nspname LIKE 'private\_%')
              AND has_schema_privilege('tvt_build', oid, 'USAGE') LOOP
    RAISE EXCEPTION 'tvt_build can still use schema % (granted to PUBLIC?): revoke it there', s;
  END LOOP;
  -- Writes: a build schema's tables, the append-only tables' INSERT, the shared tables' list.
  FOR r IN SELECT c.oid::regclass AS rel, n.nspname
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\_%'
              AND n.nspname NOT LIKE '\_timescaledb%' AND n.nspname NOT LIKE 'timescaledb\_%' LOOP
    IF r.rel = ANY (appended) THEN
      allowed := ARRAY['INSERT'];
    ELSIF r.rel = ANY (shared) THEN
      allowed := string_to_array(replace(shared_privs[array_position(shared, r.rel)], ' ', ''), ',');
    ELSIF r.nspname = ANY (build_schemas) THEN
      allowed := string_to_array(replace(build_writes, ' ', ''), ',');
    ELSE
      allowed := '{}';
    END IF;
    FOREACH p IN ARRAY privs LOOP
      IF NOT p = ANY (allowed) AND has_table_privilege('tvt_build', r.rel, p) THEN
        RAISE EXCEPTION 'tvt_build has % on % (granted to PUBLIC?), which the policy doesn''t allow', p, r.rel;
      END IF;
    END LOOP;
  END LOOP;
END
$grants$;
