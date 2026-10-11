"""Tests for deploy/tvt_build.sql (the build role's policy) and deploy/scratch/grant-checks.sql.

    python3 -m unittest discover -s deploy/scratch/tests

The policy's lists are checked as text always. With TVT_TEST_DATABASE_URL set to a database
on a test cluster, as a superuser (the laptop's: postgresql://postgres@127.0.0.1:5433/tvt_test_f6),
the SQL runs too: on synthetic schemas, inside a transaction that's rolled back, so the role
and everything else are gone afterwards. Needs psql.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
DEPLOY = os.path.dirname(SCRATCH)
POLICY = os.path.join(DEPLOY, "tvt_build.sql")
CHECKS = os.path.join(SCRATCH, "grant-checks.sql")
NEVER = re.compile(r"^(restricted|city_trees|private_.*)$")


def array(text, name):
    m = re.search(name + r"( constant)? text\[\] := ARRAY\[(.*?)\];", text, re.S)
    if not m:
        raise AssertionError(f"{name} not found")
    body = re.sub(r"--[^\n]*", "", m.group(2))
    return re.findall(r"'([^']*)'", body)


def read(path):
    with open(path) as f:
        return f.read()


class PolicyText(unittest.TestCase):
    text = read(POLICY)

    def test_no_schema_builds_must_never_read_is_listed(self):
        for name in ("read_schemas", "build_schemas"):
            for s in array(self.text, name):
                self.assertRegex(s, r"^[a-z_][a-z0-9_]*$")
                self.assertNotRegex(s, NEVER, f"{name} lists {s}")

    def test_shared_writes_are_the_least_each_needs(self):
        pairs = array(self.text, "shared_writes")
        writes = dict(zip(pairs[0::2], pairs[1::2]))
        self.assertEqual(len(pairs) % 2, 0)
        self.assertEqual(writes["core.layer_version"], "INSERT")    # append-only history (migration 0020)
        for table, privs in writes.items():
            self.assertNotRegex(table.split(".")[0], NEVER)
            got = {p.strip() for p in privs.split(",")}
            self.assertTrue(got <= {"INSERT", "UPDATE", "DELETE"}, f"{table}: {privs}")
            if table.split(".")[0] in ("raw", "ops", "evt") and table != "ops.build_pending":
                self.assertNotIn("DELETE", got, f"{table} keeps its history")
        self.assertEqual(writes["ops.build_run"], "INSERT, UPDATE")          # a build's log (migration 0021)
        self.assertEqual(writes["ops.build_pending"], "INSERT, UPDATE, DELETE")   # marks clear when built

    def test_append_only_tables_are_in_build_schemas(self):
        build = set(array(self.text, "build_schemas"))
        appended = array(self.text, "append_only")
        self.assertIn("trees.tree_log", appended)
        for t in appended:
            self.assertIn(t.split(".")[0], build)

    def test_it_takes_back_and_then_checks(self):
        self.assertIn("REVOKE %I FROM tvt_build GRANTED BY %I", self.text)          # memberships
        self.assertRegex(self.text, r"nspname IN \('restricted', 'city_trees'\) OR nspname LIKE 'private\\_%'")
        self.assertIn("RAISE EXCEPTION 'tvt_build is still a member of another role'", self.text)
        self.assertIn("has_database_privilege('tvt_build', current_database(), 'CREATE')", self.text)

    def test_the_checks_agree_with_the_policy(self):
        checks = read(CHECKS)
        self.assertEqual(array(checks, "build_schemas"), array(self.text, "build_schemas"))
        self.assertEqual(array(checks, "read_schemas"), array(self.text, "read_schemas"))
        pairs = array(self.text, "shared_writes")
        for table in pairs[0::2]:
            self.assertIn(f"'{table}'", checks, f"grant-checks.sql doesn't check {table}")


FIXTURE = """
CREATE SCHEMA core; CREATE SCHEMA obs; CREATE SCHEMA evt; CREATE SCHEMA raw; CREATE SCHEMA ops;
CREATE SCHEMA restricted; CREATE SCHEMA city_trees; CREATE SCHEMA private_parcels;
CREATE SCHEMA trees; CREATE SCHEMA roads;
CREATE TABLE core.intersection (id serial PRIMARY KEY, name text);
CREATE TABLE core.source_link (id bigserial PRIMARY KEY, note text);
CREATE TABLE core.layer_version (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, layer text);
CREATE TABLE obs.reading (at timestamptz, v real);
CREATE TABLE evt.event (id bigserial PRIMARY KEY);
CREATE TABLE raw.record (source text, first_fetch bigint);
CREATE TABLE ops.source (name text PRIMARY KEY);
CREATE TABLE ops.fetch (id bigserial PRIMARY KEY, source text);
CREATE TABLE ops.layer_signature (layer text PRIMARY KEY);
CREATE TABLE ops.osm_consumer (consumer text PRIMARY KEY, "user" text, "Mixed Case" text, "extract" text);
CREATE TABLE ops.schema_migration (name text PRIMARY KEY);
CREATE TABLE ops.build_run (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, build text);
CREATE TABLE ops.build_pending (id bigint GENERATED ALWAYS AS IDENTITY, build text, marked_by text,
                                PRIMARY KEY (build, marked_by));
CREATE TABLE restricted.crash_unit (id int);
CREATE TABLE city_trees.tree (id int);
CREATE TABLE private_parcels.parcel (id int);
CREATE TABLE trees.build (build_id text PRIMARY KEY);
CREATE TABLE trees.tree (tree_id text PRIMARY KEY);
CREATE TABLE trees.tree_log (tree_id text, at timestamptz, event text);
CREATE TABLE roads.osm_street (id bigserial PRIMARY KEY);
"""


@unittest.skipUnless(os.environ.get("TVT_TEST_DATABASE_URL"), "set TVT_TEST_DATABASE_URL (a superuser, on a test cluster)")
class OnADatabase(unittest.TestCase):
    url = os.environ.get("TVT_TEST_DATABASE_URL")

    def setUp(self):
        self.psql = shutil.which("psql")
        if not self.psql:
            self.fail("no psql on PATH")
        with subprocess.Popen([self.psql, self.url, "-X", "-At", "-c",
                               "select rolsuper from pg_roles where rolname = current_user"],
                              stdout=subprocess.PIPE, text=True) as p:
            if p.stdout.read().strip() != "t":
                self.fail("TVT_TEST_DATABASE_URL must log in as a superuser (the test makes the role)")

    def run_sql(self, body):
        """Run the fixture, then body, in one transaction that's rolled back. (stdout+stderr, code)"""
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
            f.write("\\set ON_ERROR_STOP on\nBEGIN;\n" + FIXTURE + body + "\nROLLBACK;\n")
        try:
            p = subprocess.run([self.psql, self.url, "-X", "-q", "-f", f.name], capture_output=True, text=True,
                               timeout=120)
            return p.stdout + p.stderr, p.returncode
        finally:
            os.unlink(f.name)

    def policy(self):
        return f"\\i {POLICY}\n"

    def checks_as_the_role(self):
        # grant-checks.sql begins its own transaction (a warning here) and rolls everything back.
        return f"SET ROLE tvt_build;\n\\i {CHECKS}\n"

    def privileges(self):
        return """
SELECT 'PRIVS ' || string_agg(t || ':' || p, ' ' ORDER BY t, p)
  FROM unnest(ARRAY['core.layer_version', 'trees.tree_log', 'trees.tree', 'core.intersection', 'ops.fetch',
                    'ops.osm_consumer', 'roads.osm_street', 'restricted.crash_unit', 'ops.build_run',
                    'ops.build_pending']) t,
       unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'MAINTAIN']) p
 WHERE has_table_privilege('tvt_build', t, p);
"""

    def test_the_policy_applies_and_the_role_passes_its_checks(self):
        out, code = self.run_sql(self.policy() + self.policy() + self.privileges() + self.checks_as_the_role())
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"grant checks: \d+ passed")
        privs = set(re.search(r"PRIVS (.*)", out).group(1).split())
        self.assertIn("core.layer_version:INSERT", privs)
        self.assertNotIn("core.layer_version:UPDATE", privs)
        self.assertNotIn("core.layer_version:DELETE", privs)
        self.assertIn("trees.tree_log:INSERT", privs)
        self.assertNotIn("trees.tree_log:TRUNCATE", privs)
        self.assertNotIn("trees.tree_log:DELETE", privs)
        self.assertIn("trees.tree:TRUNCATE", privs)
        self.assertIn("trees.tree:MAINTAIN", privs)
        self.assertIn("core.intersection:SELECT", privs)
        self.assertNotIn("core.intersection:INSERT", privs)
        self.assertLessEqual({"ops.osm_consumer:INSERT", "ops.osm_consumer:UPDATE"}, privs)    # S1's gate (0019)
        self.assertNotIn("ops.osm_consumer:DELETE", privs)
        self.assertLessEqual({"roads.osm_street:INSERT", "roads.osm_street:UPDATE", "roads.osm_street:DELETE"}, privs)
        self.assertFalse(any(p.startswith("restricted.") for p in privs))
        self.assertTrue({"ops.build_run:INSERT", "ops.build_run:UPDATE", "ops.build_pending:INSERT",
                         "ops.build_pending:UPDATE", "ops.build_pending:DELETE"} <= privs)
        self.assertNotIn("ops.build_run:DELETE", privs)
        self.assertNotIn("ops.build_pending:TRUNCATE", privs)

    def test_a_rerun_takes_back_what_the_lists_dont_give(self):
        stray = """
GRANT UPDATE, DELETE, TRUNCATE ON core.layer_version TO tvt_build;
GRANT UPDATE, DELETE, TRUNCATE ON trees.tree_log TO tvt_build;
GRANT INSERT, DELETE ON core.intersection, raw.record TO tvt_build;
GRANT USAGE ON SCHEMA restricted, private_parcels TO tvt_build;
GRANT SELECT ON restricted.crash_unit TO tvt_build;
GRANT CREATE ON SCHEMA roads TO tvt_build;
GRANT pg_read_all_data TO tvt_build;
"""
        out, code = self.run_sql(self.policy() + stray + self.policy() + self.privileges() + self.checks_as_the_role())
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"grant checks: \d+ passed")
        privs = set(re.search(r"PRIVS (.*)", out).group(1).split())
        for p in ("core.layer_version:UPDATE", "core.layer_version:DELETE", "trees.tree_log:TRUNCATE",
                  "core.intersection:INSERT", "restricted.crash_unit:SELECT"):
            self.assertNotIn(p, privs)

    def test_what_public_holds_stops_the_run(self):
        for stray, why in (("GRANT INSERT ON core.intersection TO PUBLIC;", "INSERT on core.intersection"),
                           ("GRANT USAGE ON SCHEMA restricted TO PUBLIC;", "can still use schema restricted"),
                           ("GRANT CREATE ON SCHEMA ops TO PUBLIC;", "create objects in schema ops")):
            out, code = self.run_sql(self.policy() + stray + self.policy())
            self.assertNotEqual(code, 0, stray)
            self.assertIn(why, out, stray)

    def test_the_checks_catch_a_wider_role(self):
        out, code = self.run_sql(self.policy() + "GRANT DELETE ON raw.record TO tvt_build;\n" + self.checks_as_the_role())
        self.assertNotEqual(code, 0, out)
        self.assertIn("DELETE on raw.record", out)


if __name__ == "__main__":
    unittest.main()
