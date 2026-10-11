"""Reading and loading a shrubs build (standard library; the database test needs psycopg and a PostGIS database named by
TVT_TEST_DATABASE_URL, and leaves nothing behind: it works inside one transaction and rolls it back)."""
import json
import os
import tempfile
import unittest

from plugins.trees.ingest import shrubs_load

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS = os.path.join(os.path.dirname(HERE), "migrations")
OUTLINE = {"type": "MultiPolygon", "coordinates": [[[[-116.21, 43.62], [-116.19, 43.62], [-116.19, 43.63],
                                                     [-116.21, 43.63], [-116.21, 43.62]]]]}
SHRUB = {"id": "x-5640001-48301002", "look": "bush", "height_m": 1.2, "width_m": 1.5, "ground_m": 820.5,
         "fit": {"cells": 9, "green": 0.9, "split": 1, "model_width_m": 1.55}}


def write(folder, shrubs, build_id="x-test", area="x", geom=OUTLINE, at=(-116.2, 43.625)):
    json.dump({"build_id": build_id, "area": area, "started_at": "2026-10-11T15:00:00Z",
               "finished_at": "2026-10-11T15:10:00Z", "geom": geom,
               "params": {"lidar": "USGS 3DEP QL1 lidar"}, "counts": {"shrubs": len(shrubs)}},
              open(os.path.join(folder, "build.json"), "w"))
    json.dump({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [at[0] + i * 1e-5, at[1]]}, "properties": s}
        for i, s in enumerate(shrubs)]}, open(os.path.join(folder, "shrubs.geojson"), "w"))


class ReadBuildTest(unittest.TestCase):
    def test_reads_the_build_and_its_shrubs(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [SHRUB, dict(SHRUB, id="x-2", look="sage", height_m=0.3, width_m=1.0, ground_m=None)])
            build, shrubs = shrubs_load.read_build(d)
            self.assertEqual((build["area"], build["build_id"]), ("x", "x-test"))
            self.assertEqual([s["id"] for s in shrubs], ["x-5640001-48301002", "x-2"])
            self.assertEqual((shrubs[0]["lon"], shrubs[0]["lat"]), (-116.2, 43.625))

    def test_refuses_bad_shrubs(self):
        for bad in (dict(SHRUB, look="tree"), dict(SHRUB, height_m=2.5), dict(SHRUB, height_m=0.2),
                    dict(SHRUB, width_m=0), dict(SHRUB, width_m=None), dict(SHRUB, id=None), dict(SHRUB, height_m="1")):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as d:
                write(d, [bad])
                with self.assertRaises(ValueError):
                    shrubs_load.read_build(d)

    def test_refuses_repeats_points_elsewhere_and_no_outline(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [SHRUB, SHRUB])
            with self.assertRaises(ValueError):
                shrubs_load.read_build(d)
        with tempfile.TemporaryDirectory() as d:
            write(d, [SHRUB], at=(564000.0, 4830000.0))         # UTM metres, not WGS84
            with self.assertRaises(ValueError):
                shrubs_load.read_build(d)
        for geom in (None, {"type": "Point", "coordinates": [0, 0]}):
            with tempfile.TemporaryDirectory() as d:
                write(d, [SHRUB], geom=geom)
                with self.assertRaises(ValueError):
                    shrubs_load.read_build(d)

    def test_copy_rows_escape_what_copy_would_misread(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [dict(SHRUB, fit={"note": "a\tb\\c\nd"}, ground_m=None)])
            build, shrubs = shrubs_load.read_build(d)
        [line] = list(shrubs_load.rows(build, shrubs))
        cols = line.rstrip("\n").split("\t")
        self.assertEqual(len(cols), len(shrubs_load.COLUMNS))
        row = dict(zip(shrubs_load.COLUMNS, cols))
        self.assertEqual(row["geom"], "SRID=4326;POINT(-116.2 43.625)")
        self.assertEqual(row["ground_m"], "\\N")
        self.assertEqual(row["lidar"], "USGS 3DEP QL1 lidar")
        self.assertEqual(json.loads(row["fit"].replace("\\\\", "\\")), {"note": "a\tb\\c\nd"})

    def test_the_band_matches_the_migration(self):
        with open(os.path.join(MIGRATIONS, "0002_shrubs.sql")) as f:
            sql = f.read()
        self.assertIn(f"height_m BETWEEN real '{shrubs_load.BAND_M[0]}' AND real '{shrubs_load.BAND_M[1]}'", sql)
        self.assertIn("look IN (" + ", ".join(f"'{k}'" for k in shrubs_load.LOOKS) + ")", sql)


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


def ensure_tables(conn):
    """The trees schema and its shrub tables, inside the caller's transaction (rolled back by the test)."""
    if conn.execute("select to_regclass('trees.shrub')").fetchone()[0] is None:
        if conn.execute("select to_regclass('trees.tree')").fetchone()[0] is None:
            with open(os.path.join(MIGRATIONS, "0001_trees.sql")) as f:
                conn.execute(f.read())
        with open(os.path.join(MIGRATIONS, "0002_shrubs.sql")) as f:
            conn.execute(f.read())


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a PostGIS database (trees migrations applied or not)")
class DatabaseTest(unittest.TestCase):
    def test_a_rebuild_replaces_the_areas_shrubs(self):
        import psycopg
        with psycopg.connect(DB_URL) as conn:
            try:
                ensure_tables(conn)
                with tempfile.TemporaryDirectory() as d:
                    write(d, [SHRUB, dict(SHRUB, id="tvt-test-2", look="sage")], build_id="tvt-test-1", area="tvt_test")
                    s1 = shrubs_load.load(conn, *shrubs_load.read_build(d))
                with tempfile.TemporaryDirectory() as d:
                    write(d, [dict(SHRUB, id="tvt-test-3")], build_id="tvt-test-2", area="tvt_test")
                    conn.execute("select pg_sleep(0.01)")
                    s2 = shrubs_load.load(conn, *shrubs_load.read_build(d))
                self.assertEqual((s1["shrubs"], s1["bush"], s1["sage"], s1["replaced"]), (2, 1, 1, 0))
                self.assertEqual((s2["shrubs"], s2["replaced"]), (1, 2))
                rows = conn.execute("select shrub_id, look, height_m, width_m, lidar, fit, ST_AsText(geom)"
                                    " from trees.shrub where area = 'tvt_test'").fetchall()
                self.assertEqual(len(rows), 1)
                sid, look, hgt, w, lidar, fit, wkt = rows[0]
                self.assertEqual((sid, look, lidar, fit["cells"]), ("tvt-test-3", "bush", "USGS 3DEP QL1 lidar", 9))
                self.assertAlmostEqual(hgt, 1.2, places=5)
                self.assertEqual(wkt, "POINT(-116.2 43.625)")
                [(build_id, shrubs, gtype)] = conn.execute(
                    "select build_id, shrubs, GeometryType(geom) from trees.shrub_area where area = 'tvt_test'").fetchall()
                self.assertEqual((build_id, shrubs, gtype), ("tvt-test-2", 1, "MULTIPOLYGON"))
                self.assertEqual(conn.execute("select count(*) from trees.shrub_build where area = 'tvt_test'")
                                 .fetchone()[0], 2)
                with self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                    conn.execute("insert into trees.shrub (shrub_id, area, look, geom, height_m, width_m, build_id)"
                                 " values ('tvt-x', 'tvt_test', 'bush', 'SRID=4326;POINT(0 0)', 2.41, 1, 'tvt-test-2')")
                with conn.transaction():         # the band's ends, as a real stores them
                    conn.execute("insert into trees.shrub (shrub_id, area, look, geom, height_m, width_m, build_id)"
                                 " values ('tvt-y', 'tvt_test', 'bush', 'SRID=4326;POINT(0 0)', 2.4, 1, 'tvt-test-2'),"
                                 " ('tvt-z', 'tvt_test', 'sage', 'SRID=4326;POINT(0 0)', 0.3, 1, 'tvt-test-2')")
            finally:
                conn.rollback()


if __name__ == "__main__":
    unittest.main()
