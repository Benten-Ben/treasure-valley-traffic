-- grant-checks.sql: what tvt_build can and can't do in this database, checked as tvt_build
-- (landscape sprint plan, F6). deploy/tvt_build.sql is the policy and checks itself as it runs;
-- this checks it from the role's side, after any branch's edit:
--
--   run.sh <name> grants --check                 on the scratch database (or --db NAME)
--   psql -X -v ON_ERROR_STOP=1 -U tvt_build -d tvt -f deploy/scratch/grant-checks.sql   anywhere
--
-- It changes nothing: everything runs in a transaction it rolls back, its refusals are
-- checked with the privilege functions or with statements refused before they touch anything,
-- and the only things it makes are a temporary table and a role setting, both rolled back.
-- Tables that don't exist in the database (S2's, M1's, a plugin not migrated yet) are skipped.
-- It ends with one line: "grant checks: N passed" or the failures (and psql exits non-zero).

\set ON_ERROR_STOP on
BEGIN;
DO $checks$
DECLARE
  read_schemas constant text[] := ARRAY['core', 'obs', 'evt', 'raw', 'ops', 'public'];
  build_schemas constant text[] := ARRAY['roads', 'soils', 'farm', 'water', 'trails', 'fences', 'hazards', 'trees'];
  -- table, privileges it must have, privileges it must not have
  expect constant text[] := ARRAY[
    'ops.source',          'INSERT,UPDATE',                         'DELETE,TRUNCATE',
    'ops.fetch',           'INSERT,UPDATE',                         'DELETE,TRUNCATE',
    'ops.layer_signature', 'INSERT,UPDATE',                         'DELETE,TRUNCATE',
    'ops.schema_migration', '',                                     'INSERT,UPDATE,DELETE,TRUNCATE',
    'raw.record',          'INSERT,UPDATE',                         'DELETE,TRUNCATE',
    'evt.event',           'INSERT,UPDATE',                         'DELETE,TRUNCATE',
    'core.source_link',    'INSERT,UPDATE,DELETE',                  'TRUNCATE',
    'core.layer_version',  'INSERT',                                'UPDATE,DELETE,TRUNCATE,MAINTAIN',
    'ops.build_pending',   'INSERT,UPDATE,DELETE',                  'TRUNCATE',
    'core.intersection',   '',                                      'INSERT,UPDATE,DELETE,TRUNCATE,MAINTAIN',
    'trees.tree',          'INSERT,UPDATE,DELETE,TRUNCATE,MAINTAIN', 'REFERENCES,TRIGGER',
    'trees.build',         'INSERT,UPDATE,DELETE,TRUNCATE,MAINTAIN', 'REFERENCES,TRIGGER',
    'trees.tree_log',      'INSERT',                                'UPDATE,DELETE,TRUNCATE,MAINTAIN'
  ];
  passed int := 0;
  failures text[] := '{}';
  rel regclass;
  s text;
  p text;
  v text;
  n bigint;
  i int;
  seq text;
BEGIN
  IF current_user <> 'tvt_build' THEN
    RAISE EXCEPTION 'run this as tvt_build (this session is %)', current_user;
  END IF;

  -- The caps: the role's defaults, and what this session has from them when it logged in as
  -- tvt_build (a superuser's session that SET ROLE to it keeps its own settings).
  FOR s, v IN VALUES ('work_mem', '64MB'), ('maintenance_work_mem', '512MB'),
                     ('max_parallel_workers_per_gather', '1'), ('statement_timeout', '45min'),
                     ('temp_file_limit', '5GB') LOOP
    IF (SELECT format('%s=%s', s, v) = ANY (rolconfig) FROM pg_roles WHERE rolname = current_user)
       AND (session_user <> current_user OR current_setting(s) = v) THEN
      passed := passed + 1;
    ELSE
      failures := failures || format('%s is %s, not %s', s, current_setting(s), v);
    END IF;
  END LOOP;
  -- temp_file_limit can't be lifted (only a superuser can set it).
  BEGIN
    PERFORM set_config('temp_file_limit', '50GB', true);
    failures := failures || 'temp_file_limit could be raised';
  EXCEPTION WHEN insufficient_privilege THEN passed := passed + 1;
  END;

  -- A plain login: no superuser, no other role's privileges, can't switch to the owner.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user
              AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
    failures := failures || 'tvt_build has a role attribute it shouldn''t';
  ELSE passed := passed + 1; END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member = current_user::regrole) THEN
    failures := failures || 'tvt_build is a member of another role';
  ELSE passed := passed + 1; END IF;
  -- (Only when logged in as tvt_build: a superuser's session that SET ROLE to it may switch back.)
  IF session_user = current_user THEN
    BEGIN
      EXECUTE format('SET LOCAL ROLE %I', (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()));
      failures := failures || 'tvt_build could SET ROLE to the database owner';
      RESET ROLE;
    EXCEPTION WHEN insufficient_privilege THEN passed := passed + 1;
    END;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class WHERE relowner = current_user::regrole) THEN
    failures := failures || 'tvt_build owns a table (it may then alter or drop it)';
  ELSE passed := passed + 1; END IF;

  -- No CREATE: no schema, and no table in any schema (both refused before anything is made).
  BEGIN
    EXECUTE 'CREATE SCHEMA tvt_build_check';
    failures := failures || 'CREATE SCHEMA worked';
  EXCEPTION WHEN insufficient_privilege THEN passed := passed + 1;
  END;
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE nspname NOT IN ('pg_catalog', 'information_schema') AND nspname NOT LIKE 'pg\_%' LOOP
    IF has_schema_privilege(s, 'CREATE') THEN failures := failures || format('CREATE in schema %s', s);
    ELSE passed := passed + 1; END IF;
  END LOOP;
  BEGIN
    EXECUTE 'CREATE TABLE public.tvt_build_check (x int)';
    failures := failures || 'CREATE TABLE in public worked';
  EXCEPTION WHEN insufficient_privilege THEN passed := passed + 1;
  END;
  -- Temporary tables work (staging).
  CREATE TEMP TABLE tvt_build_check (x int) ON COMMIT DROP;
  INSERT INTO tvt_build_check VALUES (1);
  passed := passed + 1;

  -- Reads: every table in the read and build schemas.
  FOR rel IN SELECT c.oid::regclass FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
              WHERE ns.nspname = ANY (read_schemas || build_schemas) AND c.relkind IN ('r', 'p', 'v', 'm', 'f') LOOP
    IF has_table_privilege(rel, 'SELECT') THEN passed := passed + 1;
    ELSE failures := failures || format('no SELECT on %s', rel); END IF;
  END LOOP;
  -- A real read of each hypertable (its chunks, compressed ones too), one row.
  IF to_regclass('timescaledb_information.hypertables') IS NOT NULL THEN
    FOR rel IN EXECUTE $q$SELECT format('%I.%I', hypertable_schema, hypertable_name)::regclass
                           FROM timescaledb_information.hypertables
                          WHERE hypertable_schema = ANY ($1)$q$ USING read_schemas || build_schemas LOOP
      BEGIN
        EXECUTE format('SELECT count(*) FROM (SELECT 1 FROM %s LIMIT 1) x', rel) INTO n;
        passed := passed + 1;
      EXCEPTION WHEN insufficient_privilege THEN failures := failures || format('can''t read hypertable %s', rel);
      END;
    END LOOP;
  END IF;

  -- Never: restricted, city_trees, private_* (no USAGE, so no table there can be read).
  FOR s IN SELECT nspname FROM pg_namespace
            WHERE nspname IN ('restricted', 'city_trees') OR nspname LIKE 'private\_%' LOOP
    IF has_schema_privilege(s, 'USAGE') THEN failures := failures || format('USAGE on schema %s', s);
    ELSE passed := passed + 1; END IF;
    FOR rel IN SELECT c.oid::regclass FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
                WHERE ns.nspname = s AND c.relkind IN ('r', 'p', 'v', 'm') LIMIT 1 LOOP
      BEGIN
        EXECUTE format('SELECT 1 FROM %s LIMIT 0', rel);
        failures := failures || format('could read %s', rel);
      EXCEPTION WHEN insufficient_privilege THEN passed := passed + 1;
      END;
    END LOOP;
  END LOOP;

  -- Writes: the shared and plugin tables, each as the policy says (skipped where not made yet).
  FOR i IN 1 .. array_length(expect, 1) / 3 LOOP
    rel := to_regclass(expect[3 * i - 2]);
    CONTINUE WHEN rel IS NULL;
    FOREACH p IN ARRAY string_to_array(expect[3 * i - 1], ',') LOOP
      IF has_table_privilege(rel, p) THEN passed := passed + 1;
      ELSE failures := failures || format('no %s on %s', p, rel); END IF;
    END LOOP;
    FOREACH p IN ARRAY string_to_array(expect[3 * i], ',') LOOP
      IF has_table_privilege(rel, p) THEN failures := failures || format('%s on %s', p, rel);
      ELSE passed := passed + 1; END IF;
    END LOOP;
  END LOOP;
  -- No writes anywhere in the read schemas but the shared tables.
  FOR rel IN SELECT c.oid::regclass FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
              WHERE ns.nspname = ANY (read_schemas) AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                AND ns.nspname || '.' || c.relname <> ALL (ARRAY['ops.source', 'ops.fetch', 'ops.layer_signature', 'raw.record',
                                                        'evt.event', 'core.source_link', 'core.layer_version', 'ops.build_pending']) LOOP
    IF has_table_privilege(rel, 'INSERT') OR has_table_privilege(rel, 'UPDATE')
       OR has_table_privilege(rel, 'DELETE') OR has_table_privilege(rel, 'TRUNCATE') THEN
      failures := failures || format('a write on %s', rel);
    ELSE passed := passed + 1; END IF;
  END LOOP;
  -- The shared tables' id sequences can be drawn from.
  FOREACH v IN ARRAY ARRAY['ops.fetch', 'core.source_link', 'core.layer_version', 'ops.build_pending'] LOOP
    CONTINUE WHEN to_regclass(v) IS NULL;
    FOR seq IN SELECT pg_get_serial_sequence(v, a.attname) FROM pg_attribute a
                WHERE a.attrelid = to_regclass(v) AND a.attnum > 0 AND NOT a.attisdropped
                  AND pg_get_serial_sequence(v, a.attname) IS NOT NULL LOOP
      IF has_sequence_privilege(seq, 'USAGE') THEN passed := passed + 1;
      ELSE failures := failures || format('no USAGE on sequence %s', seq); END IF;
    END LOOP;
  END LOOP;

  IF array_length(failures, 1) > 0 THEN
    RAISE EXCEPTION 'grant checks: % failed (% passed): %', array_length(failures, 1), passed, array_to_string(failures, '; ');
  END IF;
  RAISE NOTICE 'grant checks: % passed', passed;
END
$checks$;
ROLLBACK;
