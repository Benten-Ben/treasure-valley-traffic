"""farm-csb-load, farm-fields-load, derive and farm-export against a database, on the synthetic three-field GeoPackage.

These run only with TVT_TEST_DATABASE_URL: a test database with PostGIS, migrated (db/migrate.py; if the farm
migration isn't applied there, the test applies it inside its own transaction). Each test works in one transaction
and rolls it back, so it leaves nothing behind but files in a temporary folder.

Run: TVT_TEST_DATABASE_URL=postgresql://... python3 -m unittest plugins.farm.tests.test_load
"""

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone

from basemap.ground import fgb, grid
from basemap.ground import inputs as GI
from basemap.ground import manifest as M
from basemap.ground.tests import tiffs
from plugins.farm.ingest import cdl_load, csb_load, derive, export, fields_load
from plugins.farm.tests import synthetic as S

URL = os.environ.get("TVT_TEST_DATABASE_URL")
MIGRATION = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "migrations", "0001_fields.sql")
NOW = datetime(2026, 10, 11, 16, 0, tzinfo=timezone.utc)
EDITION = "csb-2018-2025-rev23"

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


@unittest.skipUnless(URL and psycopg, "set TVT_TEST_DATABASE_URL (and install psycopg) for the database tests")
class DbTest(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(URL)
        if not self.conn.execute("select to_regclass('ops.source') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("the test database isn't migrated (db/migrate.py)")
        if not self.conn.execute("select to_regclass('farm.field') is not null").fetchone()[0]:
            with open(MIGRATION, encoding="utf-8") as f:
                self.conn.execute(f.read())
        self.tmp = tempfile.TemporaryDirectory()
        self.gpkg = S.write_gpkg(os.path.join(self.tmp.name, "csb.gpkg"), S.fields())

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()
        self.tmp.cleanup()

    def one(self, sql, params=None):
        return self.conn.execute(sql, params).fetchone()

    def load(self, path=None, edition=EDITION, **kw):
        return csb_load.load(self.conn, path or self.gpkg, edition, published=date(2026, 3, 27), now=NOW, **kw)

    def permit(self, x, y, year=2022, key=None):
        self.conn.execute(
            """insert into obs.building_permit (permit_key, city, year, month, work, geom, active, first_seen, last_seen)
               values (%s, 'Nampa', %s, 5, 'New Construction',
                       ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 5070), 4326), true, now(), now())""",
            (key or f"Nampa|{x}|{y}|{year}", year, x, y))


class CsbLoadTest(DbTest):
    def test_loads_the_fields(self):
        stats = self.load()
        self.assertEqual((stats["fields"], stats["repaired"], stats["closed"]), (3, 1, 0))
        self.assertEqual(self.one("select count(*) from farm.field where valid_to is null")[0], 3)
        ed = self.one("select first_year, last_year, published, sha256, counts from farm.edition where edition = %s",
                      (EDITION,))
        self.assertEqual(ed[:3], (2018, 2025, date(2026, 3, 27)))
        self.assertEqual(ed[3], csb_load.sha256_of(self.gpkg))
        self.assertEqual(ed[4]["fields"], 3)
        self.assertEqual(self.one("select license, republish, credit from farm.edition"),
                         ("public domain", "yes", "USDA NASS Crop Sequence Boundaries 2018-2025"))
        # outlines: valid MultiPolygons south of Nampa, label points inside, the bowtie made into two triangles
        bad = self.one("""select count(*) from farm.field where not ST_IsValid(geom) or GeometryType(geom) <> 'MULTIPOLYGON'
                          or not ST_Intersects(label_pt, geom)""")[0]
        self.assertEqual(bad, 0)
        lon, lat = self.one("select ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom)) from farm.field "
                            "where field_id = %s", (S.F1,))
        self.assertTrue(-117.0 < lon < -116.3 and 43.2 < lat < 43.8, (lon, lat))
        n, area = self.one("select ST_NumGeometries(geom), ST_Area(ST_Transform(geom, 32611)) from farm.field "
                           "where field_id = %s", (S.F3,))
        self.assertEqual(n, 2)
        self.assertAlmostEqual(area, 20000, delta=200)
        # codes, letters, groups
        row = self.one("select first_year, crops, letters, group_now from farm.field where field_id = %s", (S.F1,))
        self.assertEqual(row, (2018, [1, 1, 36, 36, 1, 24, 24, 1], "cchhcggc", "corn"))
        self.assertEqual(self.one("select letters, group_now from farm.field where field_id = %s", (S.F2,)),
                         ("hhch" + "pddd", "developed"))
        self.assertEqual(self.one("select count(*) from farm.crop_class")[0], 133)

    def test_null_shift(self):
        """NAD83 is taken as WGS 84: PostGIS's transform from the same Albers with WGS 84's datum, exactly."""
        self.load()
        d = self.one("""select ST_Distance(ST_PointN(ST_ExteriorRing(ST_GeometryN(geom, 1)), 1),
                                           ST_Transform(ST_MakePoint(%s, %s), %s, 4326))
                        from farm.field where field_id = %s""",
                     (S.X0, S.Y0, csb_load.source_proj(self.conn, 5070), S.F1))[0]
        self.assertLess(d, 1e-9)
        self.assertIn("+datum=WGS84", csb_load.source_proj(self.conn, 5070))
        self.assertIsNone(csb_load.source_proj(self.conn, 32611))

    def test_bearing_is_the_long_side(self):
        self.load()
        b1, b2 = (self.one("select bearing from farm.field where field_id = %s", (f,))[0] for f in (S.F1, S.F2))
        # F1 is long east-west in NASS's Albers, F2 north-south; in UTM 11N both turn by the projections' convergence
        expect = self.one(
            """select degrees(ST_Azimuth(ST_Transform(ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 5070), 32611),
                                         ST_Transform(ST_SetSRID(ST_MakePoint(%(x)s + 400, %(y)s), 5070), 32611)))""",
            {"x": S.X0, "y": S.Y0})[0] % 180
        self.assertAlmostEqual(b1, expect, delta=0.5)
        self.assertTrue(60 < b1 < 120, b1)
        self.assertAlmostEqual((b1 - b2) % 180, 90, delta=1)

    def test_growth_flags(self):
        self.load()
        g = dict(self.conn.execute("select field_id, growth from farm.field").fetchall())
        self.assertEqual(g, {S.F1: "farmed", S.F2: "built_over", S.F3: "farmed"})
        d = self.one("select growth_detail from farm.field where field_id = %s", (S.F2,))[0]
        self.assertEqual((d["developed_by"], d["permits"]), (2023, 0))
        self.assertIn("without permits", self.one("select growth_detail ->> 'unconfirmed' from farm.field "
                                                  "where field_id = %s", (S.F3,))[0])
        # three new-construction permits inside F3 (its west triangle) since 2018 make it being built
        for i, year in enumerate((2019, 2022, 2024)):
            self.permit(S.X0 + 1020 + i, S.Y0 + 100, year)
        self.permit(S.X0 + 1021, S.Y0 + 101, 2017)        # before the window: doesn't count
        self.permit(S.X0 + 2000, S.Y0 + 100, 2022)        # outside every field
        self.load()
        state, d = self.one("select growth, growth_detail from farm.field where field_id = %s", (S.F3,))
        self.assertEqual((state, d["permits"], d["permit_years"]), ("being_built", 3, [2019, 2024]))

    def test_plats(self):
        self.conn.execute(
            """insert into core.plat (object_id, name, status, applied_on, geom, active, first_seen, last_seen)
               values (990001, 'Synthetic Farms', 'Approved', '2021-03-02',
                       ST_Multi(ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 5070), 4326)), true, now(), now()),
                      (990002, 'Half Pending', 'Pending', '2024-01-01',
                       ST_Multi(ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 5070), 4326)), true, now(), now())""",
            (S.X0 - 50, S.Y0 - 50, S.X0 + 450, S.Y0 + 150, S.X0 + 500, S.Y0, S.X0 + 600, S.Y0 + 150))
        stats = self.load()
        self.assertEqual(stats["under a plat"], 2)
        p1 = self.one("select plat from farm.field where field_id = %s", (S.F1,))[0]
        self.assertAlmostEqual(p1["approved"], 1.0, places=2)
        self.assertEqual(p1["plats"][0]["name"], "Synthetic Farms")
        p2 = self.one("select plat from farm.field where field_id = %s", (S.F2,))[0]
        self.assertAlmostEqual(p2["pending"], 0.5, delta=0.02)
        self.assertEqual(p2["approved"], 0)
        self.assertIsNone(self.one("select plat from farm.field where field_id = %s", (S.F3,))[0])
        view = dict(self.conn.execute("select f.field_id, c.p from farm.crop_fields c join farm.field f using (id)"))
        self.assertEqual(view, {S.F1: True, S.F2: False, S.F3: False})
        self.assertGreater(self.one("select count(*) from farm.field_lo where key = 'plat'")[0], 0)

    def test_dissolves_and_the_tile_views(self):
        stats = self.load()
        self.assertRegex(stats["dissolved rows"], r"^z8 \d+/z9 \d+/z10 \d+$")
        rows = self.conn.execute("select z, yr, key, now from farm.field_lo order by z, yr nulls first, key").fetchall()
        z10 = {(yr, key, now) for z, yr, key, now in rows if z == 10}
        self.assertIn((2025, "corn", True), z10)          # F1 is corn in 2025
        self.assertIn((None, "built_over", True), z10)    # F2
        self.assertIn((2018, "hay", False), z10)          # F2 was alfalfa in 2018
        self.assertNotIn((2025, "developed", True), z10)  # developed isn't a crop group
        bad = self.one("""select count(*) from farm.field_lo where ST_SRID(geom) <> 3857 or not ST_IsValid(geom)
                          or not ST_CoveredBy(geom, ST_TileEnvelope(z, x, y))""")[0]
        self.assertEqual(bad, 0)
        self.assertEqual(self.one("select count(*) from farm.crop_fields_lo10 where g = 'corn'")[0] > 0, True)
        self.assertEqual(self.one("select count(*) from farm.crop_fields_lo10 where s = 'built_over'")[0] > 0, True)
        self.assertEqual(self.one("select count(*) from farm.crop_fields_lo10 where g = 'hay'")[0], 0)   # not 2025's
        self.assertGreater(self.one("select count(*) from farm.field_lo where z = 10 and yr = 2018")[0], 0)
        # z11 on: one feature per current field, with the tile properties
        f1 = self.one("""select c.a, c.g, c.n, c.y, c.s, c.st, c.p from farm.crop_fields c join farm.field f using (id)
                         where f.field_id = %s""", (S.F1,))
        self.assertEqual(f1, (10, "corn", "Corn", "cchhcggc", "farmed", None, False))
        self.assertEqual(self.one("select n from farm.crop_fields c join farm.field f using (id) where f.field_id = %s",
                                  (S.F2,))[0], "Developed/Med Intensity")
        self.assertEqual(self.one("select year, label, edition from farm.crop_year"),
                         (2025, "2025 (USDA's newest)", EDITION))
        # every crop-fields load gives the tiles a new version, with its licence
        v = self.one("select version, republish, license, credit, features from core.layer_version_current "
                     "where layer = 'farm.crop_fields'")
        self.assertEqual(v[1], "yes")
        self.assertIn("COMPASS", v[2])
        self.assertIn("Crop Sequence Boundaries", v[3])
        self.assertEqual(v[4], 3)
        self.load()
        self.assertNotEqual(self.one("select version from core.layer_version_current "
                                     "where layer = 'farm.crop_fields'")[0], v[0])

    def test_reloading_the_same_edition_changes_nothing(self):
        self.load()
        ids = dict(self.conn.execute("select field_id, id from farm.field"))
        stats = self.load()
        self.assertEqual((stats["upserted"], stats["closed"]), (3, 0))
        self.assertEqual(dict(self.conn.execute("select field_id, id from farm.field")), ids)

    def test_a_reload_without_a_field_closes_it(self):
        self.load()
        path = S.write_gpkg(os.path.join(self.tmp.name, "two.gpkg"), S.fields()[:2])
        stats = self.load(path)
        self.assertEqual(stats["closed"], 1)
        # closed on the edition's date (an empty interval: the edition as it stands never had it), and never its
        # own successor though it still carries this edition's name
        self.assertEqual(self.one("select valid_from, valid_to, successor from farm.field where field_id = %s",
                                  (S.F3,)), (date(2026, 3, 27), date(2026, 3, 27), None))
        self.assertEqual(self.one("select count(*) from farm.crop_fields")[0], 2)
        self.load()                                        # the full file again reopens it
        self.assertEqual(self.one("select valid_to, successor from farm.field where field_id = %s", (S.F3,)),
                         (None, None))

    def test_a_reload_that_renumbers_a_field_links_the_new_one(self):
        self.load()
        rows = S.fields()
        renumbered = dict(rows[2], CSBID="161825000000009")
        path = S.write_gpkg(os.path.join(self.tmp.name, "renumbered.gpkg"), rows[:2] + [renumbered])
        self.assertEqual(self.load(path)["closed"], 1)
        self.assertEqual(self.one("select successor from farm.field where field_id = %s", (S.F3,))[0],
                         ["161825000000009"])
        self.assertIsNone(self.one("select valid_to from farm.field where field_id = '161825000000009'")[0])

    def test_a_bearing_that_rounds_to_180_wraps_to_0(self):
        """mod() just under 180 rounds to 180 as a real, which farm.field's check refuses: the expression wraps it."""
        azimuth = "(2 * pi() - 1e-10)"
        self.assertEqual(self.one(f"select mod(degrees({azimuth})::numeric, 180)::real")[0], 180.0)
        self.assertEqual(self.one(f"select {csb_load.bearing_sql(azimuth)}")[0], 0.0)
        self.assertAlmostEqual(self.one(f"select {csb_load.bearing_sql('radians(271.5)')}")[0], 91.5, places=4)
        self.load()
        self.conn.execute(f"update farm.field set bearing = {csb_load.bearing_sql(azimuth)} where field_id = %s",
                          (S.F1,))
        self.assertEqual(self.one("select bearing from farm.field where field_id = %s", (S.F1,))[0], 0.0)

    def test_a_new_edition_closes_the_fields_it_lacks(self):
        self.load()
        years = list(range(2019, 2027))
        old = {r["CSBID"]: r for r in S.fields()}
        newer = [S.field("161926000000001", old[S.F1]["_polygons"], [1, 36, 36, 1, 24, 24, 1, 1], years=years),
                 S.field("161926000000003", old[S.F3]["_polygons"], [24, 24, 41, 41, 42, 1, 122, 122], years=years)]
        path = S.write_gpkg(os.path.join(self.tmp.name, "csb1926.gpkg"), newer, years=years)
        stats = self.load(path, "csb-2019-2026")
        self.assertEqual(stats["closed"], 3)
        rows = {r[0]: r[1:] for r in self.conn.execute("select field_id, valid_to, successor from farm.field")}
        self.assertEqual(rows[S.F1], (date(2026, 3, 27), ["161926000000001"]))
        self.assertEqual(rows[S.F2], (date(2026, 3, 27), None))       # vanished: kept, closed, no successor
        self.assertEqual(rows[S.F3], (date(2026, 3, 27), ["161926000000003"]))
        self.assertIsNone(rows["161926000000001"][0])
        self.assertEqual(self.one("select count(*) from farm.crop_fields")[0], 2)
        self.assertEqual(self.one("select label from farm.crop_year")[0], "2026 (USDA's newest)")
        with self.assertRaises(csb_load.CsbError):
            self.load()                                    # the older edition, now refused

    def test_a_file_that_isnt_the_editions_window_is_refused(self):
        with self.assertRaises(csb_load.CsbError):
            csb_load.read(self.gpkg, "csb-2019-2026")
        with self.assertRaises(csb_load.CsbError):
            csb_load.read(self.gpkg, "csb2018")
        info, rows = csb_load.read(self.gpkg, EDITION)
        self.assertEqual((info["epsg"], len(rows), rows[0]["crops"]), (5070, 3, [1, 1, 36, 36, 1, 24, 24, 1]))


class FieldsLoadTest(DbTest):
    GRID = {"crs": "EPSG:32611", "res": 10.0, "west": 495920.0 + 3000 * 10, "north": 4855750.0 - 6000 * 10,
            "width": 40, "height": 30}

    def make_build(self, archive, build_id="20261011T120000Z", csb_sha=None, rows=None, july_year=2025):
        folder = os.path.join(archive, "farm", "build", build_id)
        os.makedirs(folder)
        bands = [{"name": n, "type": "uint8"} for n in ("group", "state", "confidence")]
        tiffs.grid_tiff(os.path.join(folder, "crop_cover.tif"), self.GRID, bands)
        rows = rows if rows is not None else [
            {"field_id": S.F1, "agree": {"2019": 0.8, "2025": 0.82}, "px": {"2025": 400},
             "july": {"year": july_year, "ndvi": 0.85, "state": "green", "px": 4}},
            {"field_id": S.F2, "agree": {"2025": 0.1}, "px": {"2025": 300}, "july": None},
            {"field_id": S.F3, "agree": {}, "px": {},
             "july": {"year": july_year, "ndvi": 0.2, "state": "bare", "px": 2}}]
        with open(os.path.join(folder, "fields.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        files = {n: {"sha256": csb_load.sha256_of(os.path.join(folder, n)),
                     "bytes": os.path.getsize(os.path.join(folder, n))} for n in fields_load.FILES}
        doc = {"format": fields_load.FORMAT, "build_id": build_id, "started_at": "2026-10-11T12:00:00Z",
               "finished_at": "2026-10-11T12:03:00Z", "csb_years": [2018, 2025], "cover_year": 2025,
               "july_year": july_year, "grid": self.GRID, "params": {"green": 0.6},
               "inputs": {"csb": {"path": self.gpkg, "sha256": csb_sha or csb_load.sha256_of(self.gpkg)},
                          "cdl": {"2025": {"path": "/x/cdl_2025_10m.tif", "sha256": "a" * 64, "res_m": 10.0}},
                          "ndvi": {"path": "/x/ndvi_median.tif", "sha256": "b" * 64, "year": july_year,
                                   "acquired": [f"{july_year}-07-01", f"{july_year}-07-26"]}},
               "files": files, "counts": {"fields": len(rows)}}
        with open(os.path.join(folder, "build.json"), "w") as f:
            json.dump(doc, f)
        return folder

    def test_loads_a_build(self):
        self.load()
        folder = self.make_build(self.tmp.name)
        b, rows = fields_load.read_build(folder)
        stats = fields_load.load(self.conn, folder, b, rows)
        self.assertEqual(stats["fields updated"], 3)
        agree, july, bid = self.one("select agree, july, build_id from farm.field where field_id = %s", (S.F1,))
        self.assertEqual((agree, july["state"], bid), ({"2019": 0.8, "2025": 0.82}, "green", "20261011T120000Z"))
        self.assertIsNone(self.one("select july from farm.field where field_id = %s", (S.F2,))[0])
        self.assertIsNone(self.one("select agree from farm.field where field_id = %s", (S.F3,))[0])
        self.assertEqual(self.one("select edition, republish, credit from farm.build"),
                         (EDITION, "yes", "USDA NASS Crop Sequence Boundaries 2018-2025; USDA NASS Cropland Data "
                                          "Layer 2025; Contains modified Copernicus Sentinel data 2025"))
        st = dict(self.conn.execute("select f.field_id, c.st from farm.crop_fields c join farm.field f using (id)"))
        self.assertEqual(st, {S.F1: "green", S.F2: None, S.F3: "bare"})
        # a later CSB reload with the same outlines keeps the stats
        self.load()
        self.assertEqual(self.one("select build_id from farm.field where field_id = %s", (S.F1,))[0],
                         "20261011T120000Z")

    def test_refuses_a_build_of_another_file_or_other_fields(self):
        self.load()
        folder = self.make_build(self.tmp.name, csb_sha="c" * 64)
        b, rows = fields_load.read_build(folder)
        with self.assertRaises(fields_load.BuildError):
            fields_load.load(self.conn, folder, b, rows)
        folder = self.make_build(self.tmp.name, "20261011T130000Z",
                                 rows=[{"field_id": "169999000000009", "agree": {}, "july": None}])
        b, rows = fields_load.read_build(folder)
        with self.assertRaises(fields_load.BuildError):
            fields_load.load(self.conn, folder, b, rows)

    def test_the_july_year_is_the_builds_not_the_crop_years(self):
        """A 2025 crop year built on a July 2024 NDVI: the build's credit, the tiles' and the export's all say 2024."""
        self.load()
        license, credit = derive.terms(self.conn)
        self.assertNotIn("Sentinel", credit)               # no build loaded: no July state in the tiles yet
        self.assertNotIn("Copernicus", license)
        folder = self.make_build(self.tmp.name, july_year=2024)
        b, rows = fields_load.read_build(folder)
        fields_load.load(self.conn, folder, b, rows)
        self.assertTrue(self.one("select credit from farm.build")[0].endswith("Contains modified Copernicus Sentinel "
                                                                           "data 2024"))
        v = self.one("select license, credit from core.layer_version_current where layer = 'farm.crop_fields'")
        self.assertIn("Copernicus", v[0])
        self.assertIn("Contains modified Copernicus Sentinel data 2024", v[1])
        self.assertNotIn("2025;", v[1].split("Sentinel")[1])
        m = export.export(self.conn, self.tmp.name, build="20261011T140000Z")
        s2 = M.latest(self.tmp.name, "farm").inputs["sentinel-2"]
        self.assertEqual((s2["credit"], s2["version"]), ("Contains modified Copernicus Sentinel data 2024",
                                                         "July 2024 NDVI median (2024-07-01 to 2024-07-26)"))
        self.assertIn("Sentinel-2 July 2024", m.data["note"])

    def test_read_build_refuses_a_july_of_another_year(self):
        rows = [{"field_id": S.F1, "agree": {}, "july": {"year": 2025, "ndvi": 0.8, "state": "green", "px": 4}}]
        folder = self.make_build(self.tmp.name, rows=rows, july_year=2024)
        with self.assertRaises(fields_load.BuildError):
            fields_load.read_build(folder)

    def test_read_build_checks_the_files(self):
        folder = self.make_build(self.tmp.name)
        with open(os.path.join(folder, "crop_cover.tif"), "ab") as f:
            f.write(b"\0")
        with self.assertRaises(fields_load.BuildError):
            fields_load.read_build(folder)
        os.unlink(os.path.join(folder, "build.json"))
        with self.assertRaises(fields_load.BuildError):
            fields_load.read_build(folder)

    def test_exports_for_the_ground(self):
        self.load()
        folder = self.make_build(self.tmp.name)
        b, rows = fields_load.read_build(folder)
        fields_load.load(self.conn, folder, b, rows)
        m = export.export(self.conn, self.tmp.name, build="20261011T140000Z")
        self.assertEqual(m.folder, os.path.join(self.tmp.name, "farm", "export", "20261011T140000Z"))
        again = M.latest(self.tmp.name, "farm")           # read back with every check, files and sources included
        self.assertEqual(again.build, "20261011T140000Z")
        cover, fields = again.layer("crop_cover"), again.layer("fields")
        self.assertEqual((cover["licence"], cover["republish"], cover["base"]), ("Copernicus", "yes", False))
        self.assertEqual([x["name"] for x in cover["bands"]], ["group", "state", "confidence"])
        self.assertEqual(cover["bands"][0]["values"]["2"], "hay")
        self.assertIn("Contains modified Copernicus Sentinel data 2025", cover["credit"])
        self.assertEqual((fields["licence"], fields["geometry"], fields["features"]), ("public-domain",
                                                                                         "MultiPolygon", 3))
        self.assertEqual(fields["fields"]["bearing"], "double")
        self.assertEqual(fields["credit"], ["USDA NASS Crop Sequence Boundaries 2018-2025"])
        self.assertEqual(again.inputs["csb"]["source"], "farm/nass_csb")
        h = fgb.read_header(fields.path)
        self.assertEqual(dict(h.columns)["crop_group"], "short")
        # the ground reads both, not their fallbacks
        plan = GI.resolve({"farm": again})
        self.assertFalse(plan.choice("farm/crop_cover").fallback)
        self.assertFalse(plan.choice("farm/fields").fallback)
        self.assertEqual(plan.status, "flat")              # no soils or mask v0 here: flat, as it should be

    def test_a_null_cdl_and_acres_keep_the_export_columns(self):
        """A field with no crop code (cdl NULL) exports 0 and the acres NULL stays put, so no column shifts."""
        self.load()
        folder = self.make_build(self.tmp.name)
        b, rows = fields_load.read_build(folder)
        fields_load.load(self.conn, folder, b, rows)
        self.conn.execute("update farm.field set crops = '{}', acres = null where field_id = %s", (S.F2,))
        cases = " ".join(f"when '{g}' then {code}" for g, code in export.C.COVER_CODES.items() if code)
        inner = export.FIELDS_SQL.format(cases=cases).replace("select ST_AsFlatGeobuf(q, true, 'geom') from (",
                                                              "select q.* from (", 1)
        cols = [d.name for d in self.conn.execute(inner).description]
        self.assertEqual(cols, ["id", "csbid", "crop_group", "cdl", "bearing", "acres", "geom"])
        row = self.conn.execute(f"select csbid, cdl, acres from ({inner}) z where csbid = %s", (S.F2,)).fetchone()
        self.assertEqual((row[1], row[2]), (0, None))
        m = export.export(self.conn, self.tmp.name, build="20261011T140000Z")
        self.assertEqual(m.layer("fields")["features"], 3)

    def test_export_refuses_without_a_loaded_build(self):
        self.load()
        with self.assertRaises(fields_load.BuildError):
            export.export(self.conn, self.tmp.name)


class CdlLoadTest(DbTest):
    def test_indexes_the_rasters_and_keeps_accuracy(self):
        src = os.path.join(self.tmp.name, "out")
        os.makedirs(src)
        for name in ("cdl_2023_30m.tif", "cdl_2025_10m.tif", "ada_canyon_mask_30m.tif"):
            with open(os.path.join(src, name), "wb") as f:
                f.write(name.encode() * 10)
        archive = os.path.join(self.tmp.name, "archive")
        stats = cdl_load.load(self.conn, src, archive, accuracy={1: {"state": "ID", "year": 2025, "producer": 0.94,
                                                                     "user": 0.9}}, now=NOW)
        self.assertEqual(stats["rasters"], "2023 (30 m), 2025 (10 m)")
        rows = self.conn.execute("select year, res_m, method, path, sha256 from farm.cdl_year order by year").fetchall()
        self.assertEqual(self.one("select license, republish, credit from farm.cdl_year where year = 2025"),
                         ("public domain", "yes", "USDA NASS Cropland Data Layer 2025"))
        self.assertEqual([r[:4] for r in rows], [(2023, 30.0, "30m", "farm/cdl/cdl_2023_30m.tif"),
                                                 (2025, 10.0, "10m-2024", "farm/cdl/cdl_2025_10m.tif")])
        self.assertTrue(os.path.isfile(os.path.join(archive, "farm", "cdl", "cdl_2025_10m.tif")))
        self.assertEqual(self.one("select accuracy ->> 'producer' from farm.crop_class where code = 1")[0], "0.94")
        cdl_load.load(self.conn, src, archive, now=NOW)       # without a workbook, accuracy stays
        self.assertEqual(self.one("select accuracy ->> 'user' from farm.crop_class where code = 1")[0], "0.9")
        self.assertIsNone(self.one("select accuracy from farm.crop_class where code = 36")[0])


class DeriveTest(DbTest):
    def version(self):
        return self.one("select version from core.layer_version_current where layer = 'farm.crop_fields'")[0]

    def test_farm_derive_refreshes_growth_and_plats(self):
        self.load()
        v0 = self.version()
        stats = derive.refresh(self.conn, now=NOW)
        self.assertEqual((stats["fields changed"], stats["tiles"]), (0, "unchanged: no new version"))
        self.assertEqual(self.version(), v0)
        # COMPASS's monthly permits: three in F3 since 2018 make it being built
        for i, year in enumerate((2019, 2022, 2024)):
            self.permit(S.X0 + 1020 + i, S.Y0 + 100, year)
        # and its weekly plats: F1 now under an approved plat
        self.conn.execute(
            """insert into core.plat (object_id, name, status, applied_on, geom, active, first_seen, last_seen)
               values (990003, 'Later Farms', 'Approved', '2026-09-01',
                       ST_Multi(ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 5070), 4326)), true, now(), now())""",
            (S.X0 - 50, S.Y0 - 50, S.X0 + 450, S.Y0 + 150))
        with self.conn.transaction():                     # the command rolls a dry run back
            dry = derive.refresh(self.conn, now=NOW, dry_run=True)
            raise psycopg.Rollback()
        self.assertEqual(dry["fields changed"], 2)
        self.assertNotIn("dissolved rows", dry)
        self.assertEqual(self.version(), v0)
        stats = derive.refresh(self.conn, now=NOW)
        self.assertEqual(stats["fields changed"], 2)
        self.assertEqual(self.one("select growth from farm.field where field_id = %s", (S.F3,))[0], "being_built")
        self.assertEqual(self.one("select c.p from farm.crop_fields c join farm.field f using (id) "
                                  "where f.field_id = %s", (S.F1,))[0], True)
        self.assertGreater(self.one("select count(*) from farm.field_lo where key in ('plat', 'being_built')")[0], 1)
        v1 = self.one("select version, note, build from core.layer_version_current where layer = 'farm.crop_fields'")
        self.assertNotEqual(v1[0], v0)
        self.assertEqual(v1[1], "farm-derive: permits and plats as of 2026-10-11")
        self.assertEqual(v1[2], EDITION)                   # no build loaded: the edition names the version

    def test_farm_derive_needs_fields(self):
        with self.assertRaises(derive.DeriveError):
            derive.refresh(self.conn, now=NOW)

    def test_every_farm_table_says_its_licence(self):
        for name in ("farm.edition", "farm.crop_class", "farm.cdl_year", "farm.build", "farm.field", "farm.field_lo",
                     "farm.crop_year", "farm.crop_fields", "farm.crop_fields_lo8", "farm.crop_fields_lo9",
                     "farm.crop_fields_lo10"):
            with self.subTest(name):
                text = self.one("select obj_description(%s::regclass, 'pg_class')", (name,))[0] or ""
                self.assertTrue(("republish yes" in text and "ublic domain" in text)
                                or "core.layer_version" in text, text)
        self.assertIn("Copernicus", self.one("select obj_description('farm'::regnamespace, 'pg_namespace')")[0])

    def test_pixel_sizes(self):
        self.assertAlmostEqual(derive.pixel_m(10), 76.437, places=2)
        self.assertAlmostEqual(derive.pixel_m(8), 305.75, places=1)

    def test_no_fields_no_dissolves(self):
        self.assertEqual(derive.dissolves(self.conn), {10: 0, 9: 0, 8: 0})


if __name__ == "__main__":
    unittest.main()
