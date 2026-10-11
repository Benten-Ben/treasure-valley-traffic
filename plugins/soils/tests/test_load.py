"""soils-load and soils.mapunit_shares() against a database, on the synthetic survey.

These run only with TVT_TEST_DATABASE_URL: a test database with PostGIS, migrated (db/migrate.py; if the soils
migration isn't applied there, the test applies it inside its own transaction). Each test works in one transaction
and rolls it back, so it leaves nothing behind.

Run: TVT_TEST_DATABASE_URL=postgresql://... python3 -m unittest plugins.soils.tests.test_load
"""

import copy
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from plugins.soils.ingest import load, package
from plugins.soils.tests import synthetic

URL = os.environ.get("TVT_TEST_DATABASE_URL")
MIGRATION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations", "0001_soils.sql")
NOW = datetime(2026, 10, 11, 16, 0, tzinfo=timezone.utc)

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


@unittest.skipUnless(URL and psycopg, "set TVT_TEST_DATABASE_URL (and install psycopg) for the database tests")
class LoadTest(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(URL)
        if not self.conn.execute("select to_regclass('ops.source') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("the test database isn't migrated (db/migrate.py)")
        if not self.conn.execute("select to_regclass('soils.map_unit') is not null").fetchone()[0]:
            with open(MIGRATION, encoding="utf-8") as f:
                self.conn.execute(f.read())
        self.tmp = tempfile.TemporaryDirectory()
        synthetic.write_prepared(self.tmp.name)
        self.pkg = package.read(self.tmp.name)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()
        self.tmp.cleanup()

    def one(self, sql, params=None):
        return self.conn.execute(sql, params).fetchone()

    def test_loads_everything_and_derives_the_geometry(self):
        stats = load.load(self.conn, self.pkg, now=NOW)
        self.assertEqual(stats["loaded"], "ZZ001, ZZ002")
        self.assertEqual(self.one("select count(*) from soils.survey_area")[0], 2)
        self.assertEqual(self.one("select count(*) from soils.map_unit")[0], 6)
        self.assertEqual(self.one("select count(*) from soils.component")[0], 9)
        self.assertEqual(self.one("select count(*) from soils.horizon")[0], 9)
        self.assertEqual(self.one("select count(*) from soils.polygon")[0], 6)
        self.assertEqual(self.one("select saverest::text from soils.survey_area where areasymbol = 'ZZ001'")[0],
                         "2026-08-31 21:54:36")

        # Areas on the ellipsoid: a 0.01 x 0.01 degree square at 43.5 N is about 1.11 km x 0.81 km.
        area, inside = self.one("select area_m2, area_in_box_m2 from soils.polygon where id = 'ZZ001:0'")
        self.assertAlmostEqual(area / 1e6, 0.8963, delta=0.003)
        self.assertAlmostEqual(inside, area, delta=1)
        area, inside = self.one("select area_m2, area_in_box_m2 from soils.polygon where id = 'ZZ002:0'")
        self.assertAlmostEqual(inside / area, 0.5, delta=0.001)      # it crosses the box's west edge at its middle
        self.assertEqual(self.one("""select count(*) from soils.polygon where geom_lo is null or ST_IsEmpty(geom_lo)
                                       or not ST_IsValid(geom_lo) or not ST_Within(label_pt, geom)""")[0], 0)
        self.assertEqual(self.one("select ST_NumGeometries(geom_lo) from soils.polygon where id = 'ZZ001:2'")[0], 2)

        m = self.one("""select ground_type, c_restr, pat, c_farm, farm_cond, c_hsg, hsg_dual, n_polygons,
                               round(area_in_box_ha)::int
                        from soils.map_unit where mukey = '1002'""")
        self.assertEqual(m, ("chilcott:gravelly-silt-loam", 4, "bedrock", 1, "reclaimed", 2, True, 1, 90))
        gt = {r[0]: r[1:] for r in self.conn.execute(
            "select id, n_mapunits, round(area_ha)::int, misc, frag_cover_pct, albedo_dry from soils.ground_type")}
        self.assertEqual(sorted(gt), ["chilcott:gravelly-silt-loam", "notcom", "purdam:silt-loam", "rock-outcrop",
                                      "water"])
        self.assertEqual(gt["purdam:silt-loam"][:2], (2, 180))             # 1001's square and half of 2001's
        self.assertEqual((gt["water"][2], gt["notcom"][2], gt["rock-outcrop"][2]), ("water", "nodata", "rock"))
        self.assertAlmostEqual(gt["chilcott:gravelly-silt-loam"][3], 3.5)
        self.assertAlmostEqual(gt["purdam:silt-loam"][4], 0.23, places=5)
        self.assertIsNone(gt["notcom"][4])
        gids = [r[0] for r in self.conn.execute("select gid from soils.ground_type order by gid")]
        self.assertEqual(len(set(gids)), 5)
        self.assertTrue(all(0 < g < 65536 for g in gids))

        # The survey areas' boundaries: ZZ002's two pieces joined into one.
        b = {r[0]: r[1:] for r in self.conn.execute(
            """select areasymbol, ST_NumGeometries(geom), ST_IsValid(geom), ST_IsValid(geom_lo),
                      round(ST_XMin(geom)::numeric, 2)::float, round(ST_XMax(geom)::numeric, 2)::float
               from soils.survey_area""")}
        self.assertEqual(b["ZZ002"], (1, True, True, -117.1, -116.0))
        self.assertEqual(b["ZZ001"][:3], (1, True, True))
        self.assertEqual(self.one("""select count(*) from soils.polygon p join soils.survey_area a using (areasymbol)
                                     where not ST_CoveredBy(p.geom, a.geom)""")[0], 0)

        # Each map unit's valley geometry, one MultiPolygon per unit.
        z = self.one("""select ST_NumGeometries(geom_z8), ST_NumGeometries(geom_z10), ST_IsValid(geom_z8),
                               ST_IsValid(geom_z10), GeometryType(geom_z8) from soils.map_unit where mukey = '1003'""")
        self.assertEqual(z, (2, 2, True, True, "MULTIPOLYGON"))
        self.assertEqual(self.one("select count(*) from soils.polygon where gid is null")[0], 0)
        restrictions, yields = self.one("select restrictions, crop_yields from soils.component where cokey = '1001-1'")
        self.assertEqual(restrictions[0]["kind"], "Duripan")
        self.assertEqual([y["crop"] for y in yields], ["Alfalfa hay", "Wheat"])

        # finished_at is the wall clock's, not the transaction's start (now())
        b = self.one("select kind, license, republish, credit, counts, finished_at > now() from soils.build")
        self.assertEqual(b[:4], ("load", "public domain", "yes",
                                 "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)"))
        self.assertEqual((b[4]["polygons"], b[4]["ground_types"], b[4]["polygons_repaired"]), (6, 5, 0))
        self.assertEqual((b[4]["ground_types_misc"], b[4]["map_units_without_z8"]), (3, 0))
        self.assertAlmostEqual(b[4]["area_not_surveyed_ha"], 90, delta=1)
        self.assertTrue(b[5])
        if self.one("select to_regclass('core.layer_version') is not null")[0]:
            v = self.one("select version, license, republish, features, build from core.layer_version_current "
                         "where layer = 'soils.units'")
            self.assertEqual(v[1:], ("public domain", "yes", 6, stats["build"]))
            self.assertEqual(stats["tiles"], f"soils.units {v[0]}")

    def test_skips_what_it_has_and_force_reloads(self):
        load.load(self.conn, self.pkg, now=NOW)
        again = load.load(self.conn, self.pkg, now=NOW + timedelta(minutes=1))
        self.assertEqual(again["loaded"], "nothing")
        self.assertIn("ZZ001, ZZ002", again["skipped"])
        gids = dict(self.conn.execute("select id, gid from soils.ground_type").fetchall())
        forced = load.load(self.conn, self.pkg, areas=["ZZ002"], force=True, now=NOW + timedelta(minutes=2))
        self.assertEqual(forced["loaded"], "ZZ002")
        self.assertEqual(self.one("select count(*) from soils.build")[0], 2)
        self.assertEqual(self.one("select count(*) from soils.polygon")[0], 6)
        self.assertEqual(self.one("select count(*) from soils.survey_area")[0], 2)
        self.assertEqual(self.one("select n_mapunits from soils.ground_type where id = 'purdam:silt-loam'")[0], 2)
        self.assertEqual(dict(self.conn.execute("select id, gid from soils.ground_type").fetchall()), gids)

    def test_a_changed_area_replaces_its_rows_and_drops_unused_types(self):
        load.load(self.conn, self.pkg, now=NOW)
        top = self.one("select max(gid) from soils.ground_type")[0]
        tables = copy.deepcopy(synthetic.TABLES)
        for c in tables["component"]:
            if c["cokey"] == "1003-1":
                c["compname"] = "Pits, gravel"
        areas = copy.deepcopy(synthetic.AREAS)
        areas["ZZ001"]["saverest"] = "09/30/2027 10:00:00"
        with tempfile.TemporaryDirectory() as d:
            synthetic.write_prepared(d, tables=tables, areas=areas)
            stats = load.load(self.conn, package.read(d), now=NOW + timedelta(days=1))
        self.assertEqual((stats["loaded"], stats["skipped"]), ("ZZ001", "ZZ002"))
        types = {r[0]: r[1] for r in self.conn.execute("select id, misc from soils.ground_type")}
        self.assertEqual(types, {"chilcott:gravelly-silt-loam": None, "purdam:silt-loam": None, "pits-gravel": "pits",
                                 "notcom": "nodata", "rock-outcrop": "rock"})
        self.assertEqual(self.one("select ground_type from soils.map_unit where mukey = '1003'")[0], "pits-gravel")
        self.assertEqual(self.one("select count(*) from soils.polygon")[0], 6)
        # The one new type takes the next gid: reloading the others drew none from the sequence.
        self.assertEqual(self.one("select gid from soils.ground_type where id = 'pits-gravel'")[0], top + 1)

    def test_refuses_polygons_of_unknown_map_units(self):
        polygons = synthetic.POLYGONS + [("ZZ002", 7, "2999", "x", [synthetic.square(-116.1, 43.7, -116.09, 43.71)],
                                          True)]
        with tempfile.TemporaryDirectory() as d:
            synthetic.write_prepared(d, polygons=polygons)
            with self.assertRaisesRegex(package.PackageError, "2999"):
                load.load(self.conn, package.read(d), now=NOW)

    def test_tiny_parts_drop_out_of_the_valley_geometry(self):
        tiny = synthetic.square(-116.26, 43.50, -116.2595, 43.5004)          # about 40 x 45 m
        polygons = [p if p[1:3] != (2, "1003") else
                    (p[0], p[1], p[2], p[3], [synthetic.square(-116.27, 43.50, -116.268, 43.502), tiny], p[5])
                    for p in synthetic.POLYGONS]
        with tempfile.TemporaryDirectory() as d:
            synthetic.write_prepared(d, polygons=polygons)
            load.load(self.conn, package.read(d), now=NOW)
        self.assertEqual(self.one("""select ST_NumGeometries(geom_z8), ST_NumGeometries(geom_z10)
                                     from soils.map_unit where mukey = '1003'"""), (1, 2))

    def test_mapunit_shares(self):
        load.load(self.conn, self.pkg, now=NOW)
        field = "ST_MakeEnvelope(-116.2962, 43.502, -116.2862, 43.508, 4326)"
        rows = self.conn.execute(f"select mukey, ground_type, share, area_m2 from soils.mapunit_shares({field})").fetchall()
        self.assertEqual([r[0] for r in rows], ["1001", "1002"])
        self.assertAlmostEqual(rows[0][2], 0.62, delta=0.002)
        self.assertAlmostEqual(rows[1][2], 0.38, delta=0.002)
        self.assertEqual(rows[0][1], "purdam:silt-loam")
        point = self.conn.execute("select mukey, share from soils.mapunit_shares(ST_MakePoint(-116.295, 43.505))")
        self.assertEqual(point.fetchall(), [("1001", 1.0)])                  # SRID 0 taken as 4326
        utm = self.conn.execute("""select mukey from soils.mapunit_shares(
                                     ST_Transform(ST_SetSRID(ST_MakePoint(-116.285, 43.505), 4326), 32611))""")
        self.assertEqual(utm.fetchall(), [("1002",)])
        self.assertEqual(self.conn.execute(
            "select * from soils.mapunit_shares(ST_MakeEnvelope(-115.0, 44.0, -114.9, 44.1, 4326))").fetchall(), [])

    def test_mapunit_shares_edges_invalid_shapes_and_misc(self):
        load.load(self.conn, self.pkg, now=NOW)
        # A field whose edge lies on the 1001/1002 boundary: 1002 only touches it, so it isn't in it.
        edge = self.conn.execute("""select mukey, share from soils.mapunit_shares(
                                      ST_MakeEnvelope(-116.2962, 43.502, -116.29, 43.508, 4326))""").fetchall()
        self.assertEqual([r[0] for r in edge], ["1001"])
        self.assertAlmostEqual(edge[0][1], 1.0, places=6)
        # A bow-tie (self-crossing) field: made valid, not an error. Its two triangles lie in 1001 and 1002.
        bowtie = self.conn.execute("""select mukey, share from soils.mapunit_shares(ST_GeomFromText(
            'POLYGON((-116.295 43.502, -116.285 43.508, -116.285 43.502, -116.295 43.508, -116.295 43.502))', 4326))
            """).fetchall()
        self.assertEqual(sorted(r[0] for r in bowtie), ["1001", "1002"])
        self.assertAlmostEqual(sum(r[1] for r in bowtie), 1.0, places=3)
        # misc says what isn't soil: NOTCOM is not surveyed.
        nodata = self.conn.execute("""select mukey, ground_type, misc, muname from soils.mapunit_shares(
                                        ST_MakePoint(-116.095, 43.705))""").fetchall()
        self.assertEqual(nodata, [("2002", "notcom", "nodata", "No Digital Data Available")])
        self.assertEqual(self.one("select misc from soils.mapunit_shares(ST_MakePoint(-116.295, 43.505))")[0], None)

    def test_ground_colour_takes_each_type_from_its_newest_build(self):
        load.load(self.conn, self.pkg, now=NOW)

        def build(bid, minutes, rows, finished=True):
            self.conn.execute(
                """insert into soils.build (build_id, kind, started_at, finished_at, license, republish, credit)
                   values (%s, 'photo', %s, %s, 'public domain', 'yes', 'test')""",
                (bid, NOW + timedelta(minutes=minutes), NOW + timedelta(minutes=minutes + 1) if finished else None))
            for key, photo, mask, l in rows:
                self.conn.execute(
                    """insert into soils.photo_stats (build_id, level, key, photo, mask, n_px, lab_med)
                       values (%s, 'ground_type', %s, %s, %s, 100, array[%s, 0, 0]::real[])""",
                    (bid, key, photo, mask, l))

        build("photo-a", 10, [("purdam:silt-loam", "naip2025", "photo-v1", 0.6),
                              ("water", "naip2025", "photo-v1", 0.4),
                              ("water", "naip2023-tiles", "photo-v1", 0.45),
                              ("gone:loam", "naip2025", "photo-v1", 0.5)])
        build("photo-b", 20, [("purdam:silt-loam", "naip2023-tiles", "photo-v1", 0.7),     # a rerun of one type
                              ("purdam:silt-loam", "naip2023-tiles", "classes-v1", 0.71)])
        build("photo-c", 30, [("water", "naip2025", "photo-v1", 0.9)], finished=False)      # still running
        rows = {r[0]: r[1:] for r in self.conn.execute(
            "select ground_type, build_id, photo, mask, lab_med[1], gid is not null from soils.ground_colour")}
        self.assertEqual(sorted(rows), ["purdam:silt-loam", "water"])                       # 'gone:loam' isn't a type
        self.assertEqual(rows["purdam:silt-loam"][:3], ("photo-b", "naip2023-tiles", "classes-v1"))
        self.assertEqual(rows["water"][:3], ("photo-a", "naip2025", "photo-v1"))
        self.assertTrue(all(r[4] for r in rows.values()))


if __name__ == "__main__":
    unittest.main()
