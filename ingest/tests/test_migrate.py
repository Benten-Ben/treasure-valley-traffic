"""Tests for db/migrate.py: core's migrations first, then each plugin's, recorded as '<plugin>/<file>'.

The ordering tests use made-up plugins in temporary folders. The database
test runs only against a scratch database named by TVT_TEST_DATABASE_URL
(migrated through core's migrations); it applies a made-up plugin migration
inside one transaction and rolls it back, so it leaves nothing behind.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import importlib.util
import json
import os
import tempfile
import unittest

from ingest import manifest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("tvt_db_migrate", os.path.join(REPO, "db", "migrate.py"))
migrate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrate)

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
TEST_PLUGIN = "tvt_test_migrations"
TEST_SCHEMA = "tvt_test_plugin_migration"


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def add_plugin(folder, name, depends=(), files=(), order=None):
    m = {"name": name, "title": name, "depends": list(depends), "visibility": "public", "sources": [], "tables": [],
         "storage": "none", "ethics": "none"}
    if order is not None:
        m["order"] = order
    write(os.path.join(folder, name, manifest.FILE), json.dumps(m))
    for f, sql in files:
        write(os.path.join(folder, name, "migrations", f), sql)


class OrderTest(unittest.TestCase):
    def test_core_first_then_plugins_by_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            core = os.path.join(tmp, "core")
            write(os.path.join(core, "0002_b.sql"), "")
            write(os.path.join(core, "0001_a.sql"), "")
            write(os.path.join(core, "README.md"), "")
            folder = os.path.join(tmp, "plugins")
            add_plugin(folder, "alpha", depends=["zeta"], files=[("0001_x.sql", ""), ("0002_y.sql", "")], order=1)
            add_plugin(folder, "zeta", files=[("0001_z.sql", ""), ("notes.sql", "")], order=99)
            add_plugin(folder, "empty")
            plugins = manifest.plugin_order(manifest.find([folder]))
            names = [n for n, _ in migrate.migrations(core, plugins)]
        self.assertEqual(names, ["0001_a.sql", "0002_b.sql", "zeta/0001_z.sql", "alpha/0001_x.sql", "alpha/0002_y.sql"])

    def test_this_repository(self):
        names = [n for n, _ in migrate.migrations()]
        core = sorted(os.path.basename(p) for p in os.listdir(os.path.join(REPO, "db", "migrations"))
                      if p.endswith(".sql"))
        self.assertEqual(names[:len(core)], core)          # core's files keep their names (the server has them)
        self.assertIn("0001_foundation.sql", names)
        self.assertTrue(all("/" in n for n in names[len(core):]))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through db/migrations")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.psycopg = psycopg
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        add_plugin(self.tmp.name, TEST_PLUGIN, files=[
            ("0001_first.sql", f"create schema {TEST_SCHEMA}; create table {TEST_SCHEMA}.thing (id int primary key);"),
        ])
        self.plugins = manifest.plugin_order(manifest.find([self.tmp.name]))
        self.assertFalse(self.leftovers(), "a previous run left rows behind")

    def leftovers(self):
        with self.psycopg.connect(DB_URL) as c:
            rows = c.execute("select name from ops.schema_migration where name like %s", (TEST_PLUGIN + "/%",)).fetchall()
            schema = c.execute("select to_regnamespace(%s)", (TEST_SCHEMA,)).fetchone()[0]
        return rows or schema

    def test_a_plugin_migration_applies_after_cores_and_is_recorded_by_plugin(self):
        files = migrate.migrations(plugins=self.plugins)
        self.assertEqual(files[-1][0], f"{TEST_PLUGIN}/0001_first.sql")
        said = []
        conn = self.psycopg.connect(DB_URL)
        try:
            conn.execute("select 1")                      # one outer transaction: each migration is a savepoint
            migrate.apply(conn, files, out=said.append)
            self.assertEqual(said, [f"applied  {TEST_PLUGIN}/0001_first.sql"])    # core's were all applied already
            self.assertEqual(conn.execute("select count(*) from ops.schema_migration where name = %s",
                                          (f"{TEST_PLUGIN}/0001_first.sql",)).fetchone()[0], 1)
            conn.execute(f"insert into {TEST_SCHEMA}.thing values (1)")
            said.clear()
            migrate.apply(conn, files, out=said.append)   # nothing left to do
            self.assertEqual(said, [])
            migrate.apply(conn, files, status=True, out=said.append)
            self.assertIn(f"applied  {TEST_PLUGIN}/0001_first.sql", said)
            write(files[-1][1], "-- edited after it was applied\n")
            with self.assertRaises(SystemExit) as cm:      # the same checksum rule as core's
                migrate.apply(conn, files, out=said.append)
            self.assertIn("changed after it was applied", str(cm.exception))
        finally:
            conn.rollback()
            conn.close()
        self.assertFalse(self.leftovers())


if __name__ == "__main__":
    unittest.main()
