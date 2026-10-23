"""trails-export on synthetic ways (plugins/trails/ingest/export.py): the paved-path base layers.

Offline: the manifest's input, the SQL's inputs and the command. Database tests run only against a scratch database
named by TVT_TEST_DATABASE_URL (with trails 0001 and core's migrations), inside a transaction that is rolled back:
the synthetic ways go through the osm_paths consumer, then the export reads them and its manifest is checked and
read back.

Run: python3 -m unittest discover -s plugins/trails -t .
"""

import json
import os
import re
import tempfile
import unittest

from plugins.trails.tests.test_osm_paths import FakeRun, area, way

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
BASE = 9_500_000_000


def seg(n):
    """Two points on their own, 100 m or so apart in longitude/latitude, so ways never share geometry."""
    return [[-116.2 + n * 0.001, 43.7], [-116.2 + n * 0.001, 43.701]]


class OfflineTest(unittest.TestCase):
    def test_the_input_is_osm_paths_alone(self):
        from plugins.trails.ingest import export
        e = export.input_entry("osm_paths abcd1234")
        self.assertEqual((e["licence"], e["republish"], e["source"], e["credit"]),
                         ("ODbL-1.0", "yes", "trails/osm_paths", "© OpenStreetMap contributors"))
        self.assertEqual(e["version"], "osm_paths abcd1234")

    def test_it_reads_only_osm_tables(self):
        """Never trails_match, Ridge to Rivers' or the City's tables or sources (the bake refuses them)."""
        from plugins.trails.ingest import export
        sql = " ".join((export.PATHS_ROWS, export.AREAS_ROWS)).lower()
        self.assertEqual(sorted(set(re.findall(r"\b(?:trails|core|raw|evt)\.\w+", sql))),
                         ["trails.osm_area", "trails.osm_path"])
        with open(os.path.join(PLUGIN, "ingest", "export.py"), encoding="utf-8") as f:
            code = f.read().split('"""', 2)[2]                   # past the docstring
        for name in ("trails_match", "r2r_", "boise_", "idwr", "agency", "matched_line", "path_lo"):
            self.assertNotIn(name, code)

    def test_filters_are_in_the_rows(self):
        from plugins.trails.ingest import export
        for needle in ("active", "surface = 'paved'", "not no_access", "sidewalk", "crossing"):
            self.assertIn(needle, export.PATHS_ROWS)
        for needle in ("active", "not no_access"):
            self.assertIn(needle, export.AREAS_ROWS)

    def test_the_command_is_in_plugin_json(self):
        with open(os.path.join(PLUGIN, "plugin.json"), encoding="utf-8") as f:
            cmds = {c["name"]: c for c in json.load(f)["commands"]}
        self.assertEqual(cmds["trails-export"]["module"], "ingest.export")
        self.assertTrue(os.path.isfile(os.path.join(PLUGIN, "ingest", "export.py")))

    def test_the_run_marks_the_bake(self):
        from plugins.trails.ingest import export
        self.assertEqual((export.BUILD, export.THEN), ("trails-export", ("landscape-bake",)))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with trails 0001)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('trails.osm_path') is not null").fetchone()[0]:
                raise unittest.SkipTest("trails.osm_path is missing: apply trails 0001")

    def setUp(self):
        from plugins.trails.ingest.sources import osm_paths
        self.conn = self.psycopg.connect(DB_URL)
        for table in ("trails.osm_path", "trails.osm_area"):
            self.conn.execute(f"update {table} set active = false where active")          # rolled back
        b = BASE
        osm_paths.consume(self.conn, FakeRun([
            way(b + 1, seg(1), highway="path", surface="asphalt", name="Fixture Pathway"),
            way(b + 2, seg(2), highway="cycleway"),                                      # paved by default
            way(b + 3, seg(3), highway="footway", surface="concrete:plates", width="2.5"),
            way(b + 4, seg(4), highway="footway", surface="paving_stones"),
            way(b + 5, seg(5), highway="path", surface="gravel"),                        # unpaved
            way(b + 6, seg(6), highway="path", surface="dirt"),
            way(b + 7, seg(7), highway="path"),                                          # unknown
            way(b + 8, seg(8), highway="track", surface="asphalt", access="private"),    # closed
            way(b + 9, seg(9), highway="cycleway", access="no"),                         # closed
            way(b + 10, seg(10), highway="footway", surface="asphalt", access="no", foot="yes"),   # opened for foot
            way(b + 11, seg(11), highway="steps", surface="concrete"),
            area(b + 20, highway="pedestrian", area="yes", surface="paving_stones", name="Fixture Plaza"),
            area(b + 20, "r", highway="pedestrian", area="yes"),                         # untagged, same id
            area(b + 21, highway="footway", area="yes", surface="gravel"),
            area(b + 22, highway="pedestrian", area="yes", surface="asphalt", access="private"),
        ]))

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def mine(self, sql, key="id"):
        cur = self.conn.execute(f"select * from ({sql}) q")
        cols = [c.name for c in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall() if r[0] >= BASE}

    def test_paths_and_their_filters(self):
        from plugins.trails.ingest import export
        rows = self.mine(export.PATHS_ROWS)
        self.assertEqual(sorted(i - BASE for i in rows), [1, 2, 3, 4, 10, 11])
        self.assertEqual({i - BASE: (r["kind"], r["material"]) for i, r in rows.items()},
                         {1: ("path", "asphalt"), 2: ("cycleway", "paved"), 3: ("footway", "concrete"),
                          4: ("footway", "paving_stones"), 10: ("footway", "asphalt"), 11: ("steps", "concrete")})
        self.assertEqual(rows[BASE + 3]["w"], 2.5)                      # tagged
        self.assertEqual(rows[BASE + 1]["w"], 3.0)                      # estimated: a paved path
        self.assertEqual(rows[BASE + 4]["w"], 1.8)                      # a footway

    def test_areas_and_their_filters(self):
        from plugins.trails.ingest import export
        rows = self.mine(export.AREAS_ROWS)
        # the way's id doubled; the relation's with the same OSM id doubled plus one; gravel and private left out
        self.assertEqual(sorted(rows), [2 * (BASE + 20), 2 * (BASE + 20) + 1])
        self.assertEqual(rows[2 * (BASE + 20)]["material"], "paving_stones")
        self.assertEqual(rows[2 * (BASE + 20) + 1]["material"], "paved")

    def test_no_nulls(self):
        # PostGIS's ST_AsFlatGeobuf shifts the column after a NULL into the NULL's place.
        from plugins.trails.ingest import export
        for rows in (export.PATHS_ROWS, export.AREAS_ROWS):
            cur = self.conn.execute(f"select * from ({rows}) q")
            for row in cur.fetchall():
                self.assertNotIn(None, row)

    def test_export(self):
        from basemap.ground import manifest as M
        from plugins.trails.ingest import export
        with tempfile.TemporaryDirectory() as archive:
            m, load = export.export(self.conn, archive, build="20261022T120000Z", min_features={})
            layers = {lay.name: lay for lay in m.layers}
            self.assertEqual(sorted(layers), ["paved_areas", "paved_paths"])
            for name, geometry in (("paved_paths", "LineString"), ("paved_areas", "MultiPolygon")):
                lay = layers[name]
                self.assertEqual((lay["base"], lay["minzoom"], lay["geometry"], lay["inputs"]),
                                 (True, 15, geometry, ["osm"]))
                self.assertEqual((lay["licence"], lay["republish"]), ("ODbL-1.0", "yes"))
                self.assertEqual(lay["credit"], ["© OpenStreetMap contributors"])
                self.assertEqual(lay["fields"]["id"], "long")
            self.assertEqual(set(layers["paved_paths"]["fields"]), {"id", "kind", "material", "w"})
            self.assertEqual(m.inputs["osm"]["source"], "trails/osm_paths")
            self.assertEqual(M.read(m.folder).build, "20261022T120000Z")      # the files check against the manifest

    def test_too_few_paths_is_a_broken_load(self):
        from plugins.trails.ingest import export
        with tempfile.TemporaryDirectory() as archive:
            with self.assertRaises(export.ExportError):
                export.export(self.conn, archive, build="20261022T120001Z", min_features={"paved_paths": 10 ** 9})
            self.assertEqual(os.listdir(archive), [])


if __name__ == "__main__":
    unittest.main()
