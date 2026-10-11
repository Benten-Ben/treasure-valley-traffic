"""Tests for ingest/layer_version.py: the toggled layers' tile versions (core.layer_version, migration 0020).

The offline tests cover the checks, fresh versions and the insert. The database test runs only
against a scratch database named by TVT_TEST_DATABASE_URL (migrated through 0020); it works inside
one transaction and rolls it back, so it leaves nothing behind.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import re
import unittest
from datetime import datetime, timezone

from ingest import layer_version as lv


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))


class CheckTest(unittest.TestCase):
    def test_accepts_a_good_row(self):
        lv.check("soils.units", "20261011T0412Z-3fa9c1", "public domain", "yes", "USDA NRCS SSURGO", features=12)
        lv.check("farm.crop_fields", "b1.2_x", "ODbL + ACHD/ITD widths", "internal", "© OpenStreetMap contributors; ACHD; ITD")

    def test_refuses_what_the_table_would(self):
        for layer in ("soils", "Soils.units", "soils.units.x", "soils-x.units", "1soils.units", "", None,
                      "a" * 41 + ".x"):
            with self.subTest(layer=layer), self.assertRaises(ValueError):
                lv.check(layer, "v1", "ODbL", "yes", "OSM")
        for version in ("", "v 1", "v/1", "v?1", "a" * 65, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                lv.check("soils.units", version, "ODbL", "yes", "OSM")
        for license, republish, credit in ((" ", "yes", "OSM"), ("ODbL", "public", "OSM"), ("ODbL", "yes", ""),
                                           ("ODbL", "yes", " "), ("ODbL", "yes", None)):
            with self.subTest(license=license, republish=republish, credit=credit), self.assertRaises(ValueError):
                lv.check("soils.units", "v1", license, republish, credit)
        with self.assertRaises(ValueError):
            lv.check("soils.units", "v1", "ODbL", "yes", "OSM", features=-1)

    def test_fresh_versions_are_url_safe_and_differ(self):
        at = datetime(2026, 10, 11, 4, 12, 30, tzinfo=timezone.utc)
        a, b = lv.new_version(at), lv.new_version(at)
        self.assertRegex(a, r"^20261011T0412Z-[0-9a-f]{6}$")
        self.assertNotEqual(a, b)
        self.assertTrue(lv.VERSION.fullmatch(lv.new_version()))


class RecordTest(unittest.TestCase):
    def test_inserts_one_row_and_returns_the_version(self):
        conn = FakeConn()
        v = lv.record(conn, "trails.paths", license="ODbL", republish="yes", credit="© OpenStreetMap contributors",
                      build="trails-match 42", features=9)
        self.assertTrue(lv.VERSION.fullmatch(v))
        [(sql, params)] = conn.calls
        self.assertTrue(sql.startswith("insert into core.layer_version"))
        self.assertIn("(layer, version, build, features, license, republish, credit, note)", sql)
        self.assertEqual(params, ("trails.paths", v, "trails-match 42", 9, "ODbL", "yes", "© OpenStreetMap contributors", None))

    def test_keeps_a_given_version_and_checks_before_writing(self):
        conn = FakeConn()
        self.assertEqual(lv.record(conn, "soils.units", license="public domain", republish="yes", credit="USDA NRCS",
                                   version="ssurgo-2025"), "ssurgo-2025")
        with self.assertRaises(ValueError):
            lv.record(conn, "soils.units", license="public domain", republish="maybe", credit="USDA NRCS")
        with self.assertRaises(TypeError):   # the credit is required
            lv.record(conn, "soils.units", license="public domain", republish="yes")
        self.assertEqual(len(conn.calls), 1)

    def test_the_patterns_match_the_migration(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "..", "db", "migrations", "0020_layer_version.sql"), encoding="utf-8") as f:
            sql = f.read()
        self.assertIn(f"layer ~ '^{lv.NAME}\\.{lv.NAME}$'", sql)
        self.assertIn(f"version ~ '^{lv.VERSION.pattern}$'", sql)
        self.assertIn("republish in (" + ", ".join(f"'{r}'" for r in lv.REPUBLISH) + ")", sql)
        self.assertIn("unique (layer, version)", sql)
        # Spelled as ops.source and the manifests spell them.
        self.assertIn("license    text not null", sql)
        self.assertIn("credit     text not null", sql)
        self.assertNotIn("licence ", sql.split("create table", 1)[1])


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through 0020")
class DatabaseTest(unittest.TestCase):
    def test_the_newest_row_is_current(self):
        import psycopg
        with psycopg.connect(DB_URL) as conn:
            if not conn.execute("select to_regclass('core.layer_version') is not null").fetchone()[0]:
                self.skipTest("core.layer_version is missing: apply migration 0020")
            try:
                osm = {"license": "ODbL", "republish": "yes", "credit": "© OpenStreetMap contributors"}
                lv.record(conn, "tvt_test.alpha", version="a1", **osm)
                lv.record(conn, "tvt_test.alpha", version="a2", features=3, **osm)
                lv.record(conn, "tvt_test.beta", license="public domain", republish="internal", credit="USGS",
                          version="b1")
                now = {k: v for k, (v, _) in lv.current(conn).items() if k.startswith("tvt_test.")}
                self.assertEqual(now, {"tvt_test.alpha": "a2", "tvt_test.beta": "b1"})
                # A version is never used twice for a layer, so going back to earlier data takes a fresh one.
                with self.assertRaises(psycopg.errors.UniqueViolation), conn.transaction():
                    lv.record(conn, "tvt_test.alpha", version="a1", **osm)
                fresh = lv.record(conn, "tvt_test.alpha", **osm)
                self.assertEqual(lv.current(conn)["tvt_test.alpha"][0], fresh)
                lv.record(conn, "tvt_test.beta", version="a1", **osm)   # another layer may use the same name
                [(credit, license)] = conn.execute(
                    "select credit, license from core.layer_version_current where layer = 'tvt_test.beta'").fetchall()
                self.assertEqual((credit, license), ("© OpenStreetMap contributors", "ODbL"))
                for bad in (("tvt_test.alpha", "v 1", "ODbL", "yes", "OSM"), ("TVT.alpha", "v1", "ODbL", "yes", "OSM"),
                            ("tvt_test.alpha", "v1", "ODbL", "maybe", "OSM"), ("tvt_test.alpha", "v1", " ", "yes", "OSM"),
                            ("tvt_test.alpha", "v1", "ODbL", "yes", "")):
                    with self.subTest(bad=bad), self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                        conn.execute("insert into core.layer_version (layer, version, license, republish, credit) "
                                     "values (%s, %s, %s, %s, %s)", bad)
            finally:
                conn.rollback()


if __name__ == "__main__":
    unittest.main()
