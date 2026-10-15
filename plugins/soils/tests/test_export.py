"""soils-export against a database, on the synthetic survey: the ground's export contract (basemap/ground).

Runs only with TVT_TEST_DATABASE_URL (a migrated test database with PostGIS 3.2 or later, for ST_AsFlatGeobuf); each
test rolls back, and its export goes to a temporary archive.

Run: TVT_TEST_DATABASE_URL=postgresql://... python3 -m unittest plugins.soils.tests.test_export
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from basemap.ground import fgb
from basemap.ground import inputs as GI
from basemap.ground import manifest as M
from plugins.soils.ingest import export, load, package
from plugins.soils.tests import synthetic
from plugins.soils.tests.test_load import MIGRATION, NOW, URL, psycopg


@unittest.skipUnless(URL and psycopg, "set TVT_TEST_DATABASE_URL (and install psycopg) for the database tests")
class ExportTest(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(URL)
        if not self.conn.execute("select to_regclass('ops.source') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("the test database isn't migrated (db/migrate.py)")
        if not self.conn.execute("select to_regclass('soils.map_unit') is not null").fetchone()[0]:
            with open(MIGRATION, encoding="utf-8") as f:
                self.conn.execute(f.read())
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = os.path.join(self.tmp.name, "archive")
        os.makedirs(self.archive)
        prepared = os.path.join(self.tmp.name, "prepared")
        synthetic.write_prepared(prepared)
        load.load(self.conn, package.read(prepared), now=NOW)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()
        self.tmp.cleanup()

    def test_writes_the_ground_and_its_types(self):
        m = export.export(self.conn, self.archive, build="20261011T160000Z")
        self.assertEqual(m.folder, os.path.join(self.archive, "soils", "export", "20261011T160000Z"))
        again = M.read(m.folder)                                    # checks every file, header and the source
        ground = again.layer("ground")
        self.assertEqual((ground["format"], ground["geometry"], ground["features"], ground["crs"]),
                         ("FlatGeobuf", "MultiPolygon", 6, "EPSG:32611"))
        self.assertEqual(ground["fields"], {"id": "int", "ground_type": "int", "misc": "string", "mukey": "string"})
        self.assertEqual((ground["licence"], ground["republish"], ground["base"]), ("public-domain", "yes", False))
        self.assertEqual(ground["credit"], ["Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)"])
        self.assertEqual(again.inputs["ssurgo"]["source"], "soils/ssurgo")
        h = fgb.read_header(ground.path)
        self.assertEqual(h.features_count, 6)

        # The ground reads it (the rest of its plan falls back or stays flat).
        self.assertFalse(GI.resolve({"soils": again}).choice("soils/ground").fallback)

        with open(os.path.join(m.folder, "ground_types.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["schema"], "soils.ground_types/1")
        self.assertEqual(again.layer("ground_types")["schema"], "soils.ground_types/1")
        types = {t["id"]: t for t in doc["types"]}
        self.assertEqual(sorted(types), ["chilcott:gravelly-silt-loam", "notcom", "purdam:silt-loam",
                                         "rock-outcrop", "water"])
        self.assertEqual(dict(self.conn.execute("select id, gid from soils.ground_type").fetchall()),
                         {k: t["gid"] for k, t in types.items()})
        self.assertEqual((types["notcom"]["misc"], types["rock-outcrop"]["misc"], types["purdam:silt-loam"]["misc"]),
                         ("nodata", "rock", None))
        self.assertEqual(types["purdam:silt-loam"]["albedo_dry"], 0.23)
        self.assertEqual(len(doc["loads"]), 1)

    def test_its_snapshot_is_the_callers_when_one_is_open(self):
        # The load above is uncommitted: the export reads it in the caller's transaction and leaves that open.
        export.export(self.conn, self.archive, build="20261011T160000Z")
        self.assertEqual(self.conn.execute("select count(*) from soils.polygon").fetchone()[0], 6)

    def test_refuses_an_empty_survey_and_leaves_no_folder(self):
        self.conn.execute("delete from soils.survey_area")
        with self.assertRaisesRegex(export.ExportError, "no survey areas"):
            export.export(self.conn, self.archive, build="20261011T160000Z")
        self.assertFalse(os.path.exists(os.path.join(self.archive, "soils")))

    def test_command_needs_an_archive(self):
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"TVT_ARCHIVE": os.path.join(self.tmp.name, "nowhere")}), \
                contextlib.redirect_stderr(err):
            self.assertEqual(export.main([]), 1)
        self.assertIn("TVT_ARCHIVE", err.getvalue())


if __name__ == "__main__":
    unittest.main()
