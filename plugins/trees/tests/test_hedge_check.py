"""The hedge check (standard library; the database test needs psycopg and a PostGIS database named by
TVT_TEST_DATABASE_URL, and leaves nothing behind: it works inside one transaction and rolls it back)."""
import json
import math
import os
import tempfile
import unittest

from plugins.trees.ingest import hedge_check
from plugins.trees.tests.test_shrubs_load import ensure_tables

HEDGE = {"type": "Feature", "properties": {"@id": "w1"},
         "geometry": {"type": "LineString", "coordinates": [[-116.2, 43.62], [-116.1999, 43.62]]}}


class ReadTest(unittest.TestCase):
    def test_a_feature_collection(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.geojson")
            json.dump({"type": "FeatureCollection", "features": [
                HEDGE, {"type": "Feature", "properties": {"id": 7},
                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0]}},
                {"type": "Feature", "properties": {}, "geometry": HEDGE["geometry"]}]}, open(p, "w"))
            got = hedge_check.read_hedges(p)
        self.assertEqual([i for i, _ in got], ["w1", "7", "hedge-4"])
        self.assertEqual(got[1][1]["type"], "Polygon")

    def test_a_geojson_sequence(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "h.geojsonseq")
            with open(p, "w") as f:
                f.write("\x1e" + json.dumps(HEDGE) + "\n")
                f.write("\x1e" + json.dumps(dict(HEDGE, properties={"osm_id": "w2"})) + "\n\n")
            self.assertEqual([i for i, _ in hedge_check.read_hedges(p)], ["w1", "w2"])

    def test_verdicts(self):
        v = hedge_check.verdict
        self.assertEqual(v(0.6, 0.9, 1.0), "shrubs")
        self.assertEqual(v(0.1, 0.5, 0.55), "trees")
        self.assertEqual(v(0.3, 0.3, 0.55), "shrubs and trees")
        self.assertEqual(v(0.1, 0.1, 0.2), "partly")
        self.assertEqual(v(0.0, 0.0, 0.19), "not found")

    def test_the_summary_adds_up(self):
        rows = [{"verdict": "shrubs", "length_m": 20.0, "shrubs": 12, "bushes": 12},
                {"verdict": "not found", "length_m": 5.5, "shrubs": 0, "bushes": 0}]
        s = hedge_check.summary(rows, 3, "test")
        self.assertEqual((s["hedges_read"], s["hedges_in_shrub_areas"], s["length_m"]), (3, 2, 25.5))
        self.assertEqual(s["by_verdict"]["shrubs"], {"hedges": 1, "length_m": 20.0})
        self.assertEqual(s["bush_share"], 1.0)


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
LON0, LAT0 = -116.2, 43.62
M_LON = 1 / (111320 * math.cos(math.radians(LAT0)))     # degrees per metre, roughly
M_LAT = 1 / 110950


def at(e, n):
    return LON0 + e * M_LON, LAT0 + n * M_LAT


def line(e0, n0, e1, n1):
    return {"type": "LineString", "coordinates": [list(at(e0, n0)), list(at(e1, n1))]}


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a PostGIS database (trees migrations applied or not)")
class DatabaseTest(unittest.TestCase):
    def test_hedges_found_as_shrubs_as_trees_or_not_at_all(self):
        import psycopg
        with psycopg.connect(DB_URL) as conn:
            try:
                ensure_tables(conn)
                ring = [list(at(e, n)) for e, n in ((0, 0), (200, 0), (200, 200), (0, 200), (0, 0))]
                conn.execute("insert into trees.shrub_build (build_id, area, started_at, geom) values"
                             " ('tvt-test-1', 'tvt_test', now(), ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))",
                             (json.dumps({"type": "Polygon", "coordinates": [ring]}),))
                conn.execute("insert into trees.build (build_id, area, started_at) values ('tvt-test-t', 'tvt_test', now())")
                for i in range(20):                  # a row of bushes along the first hedge, 1 m apart
                    lon, lat = at(20 + i + 0.5, 50.3)
                    conn.execute("insert into trees.shrub (shrub_id, area, look, geom, height_m, width_m, build_id)"
                                 " values (%s, 'tvt_test', 'bush', ST_SetSRID(ST_MakePoint(%s, %s), 4326), 1.4, 1.3,"
                                 " 'tvt-test-1')", (f"tvt-s{i}", lon, lat))
                for i in range(5):                   # trees along the second: a hedge taller than 2.4 m
                    lon, lat = at(20 + 4 * i + 2, 100)
                    conn.execute("insert into trees.tree (tree_id, area, kind, type, geom, height_m, crown_radius_m,"
                                 " build_id) values (%s, 'tvt_test', 'placed', 'broadleaf',"
                                 " ST_SetSRID(ST_MakePoint(%s, %s), 4326), 4, 2.2, 'tvt-test-t')",
                                 (f"tvt-t{i}", lon, lat))
                hedges = [("h-shrubs", line(20, 50, 40, 50)), ("h-trees", line(20, 100, 40, 100)),
                          ("h-nothing", line(20, 150, 40, 150)), ("h-outside", line(300, 50, 320, 50))]
                got = {r["hedge"]: r for r in hedge_check.check(conn, hedges)}
                self.assertEqual(set(got), {"h-shrubs", "h-trees", "h-nothing"})
                self.assertEqual(got["h-shrubs"]["verdict"], "shrubs")
                self.assertEqual((got["h-shrubs"]["shrubs"], got["h-shrubs"]["bushes"]), (20, 20))
                self.assertGreater(got["h-shrubs"]["shrub_cover"], 0.9)
                self.assertAlmostEqual(got["h-shrubs"]["length_m"], 20, delta=0.5)
                self.assertAlmostEqual(got["h-shrubs"]["median_height_m"], 1.4, places=2)
                self.assertEqual(got["h-trees"]["verdict"], "trees")
                self.assertEqual(got["h-trees"]["shrubs"], 0)
                self.assertEqual(got["h-nothing"]["verdict"], "not found")
                s = hedge_check.summary(list(got.values()), len(hedges), "test")
                self.assertEqual((s["hedges_read"], s["hedges_in_shrub_areas"]), (4, 3))
            finally:
                conn.rollback()


if __name__ == "__main__":
    unittest.main()
