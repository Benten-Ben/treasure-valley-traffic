"""Wetlands (issue #309): the Cowardin decoder, the presence check's rules, the generalisation, nwi-load and
nwi-presence on synthetic files, and the build's conflation of NWI with OSM and NHD on synthetic polygons.

The first classes are standard library only. The database classes run only against a scratch database named by
TVT_TEST_DATABASE_URL (PostGIS, with water 0004 and core's migrations): the build runs in a transaction that is rolled
back; nwi-load commits, so its test cleans up after itself.

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from plugins.water.ingest import gpkg, rules, wetlands
from plugins.water.tests import synthetic as S

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
BASE = 9_400_000_000

# The 73 vegetated palustrine codes in the box (the NWI cut of Oct 23, 2026): every one must decode.
CODES = """PEM1/FO1A PEM1/FOC PEM1/SS1Ch PEM1/SSA PEM1/SSC PEM1/UBF PEM1/UBFh PEM1/UBFx PEM1/USC PEM1A PEM1Ad PEM1Af
PEM1Ah PEM1Ax PEM1B PEM1Bh PEM1C PEM1Cb PEM1Cd PEM1Cf PEM1Ch PEM1Cx PEM1D PEM1F PEM1Fd PEM1Fh PEM1Fr PEM1Fx PEM1J
PEM1K PEM1Kx PEM2F PEM2Fh PFO/USC PFO1/EM1C PFO1/SS1A PFO1/SS1C PFO1/USA PFO1/USC PFO1A PFO1Ah PFO1Ax PFO1B PFO1C
PFO1Ch PFO1Cx PFO1Fh PFOA PFOC PSS/EM1C PSS1/EM1Ch PSS1/EM1F PSS1/FO1Ch PSS1/USA PSS1/USC PSS1A PSS1Ah PSS1Ax PSS1B
PSS1C PSS1Cb PSS1Ch PSS1Cx PSS1D PSS1F PSS1Fh PSS1Fx PSS1J PSSA PSSB PSSC PSSCh PSSCx""".split()


class CodeTest(unittest.TestCase):
    def test_every_code_in_the_box_decodes(self):
        self.assertEqual(len(CODES), 73)
        for code in CODES:
            with self.subTest(code=code):
                self.assertTrue(wetlands.is_vegetated(code))
                text = wetlands.describe(code)
                self.assertTrue(text.startswith("Freshwater "), text)

    def test_parts(self):
        self.assertEqual(wetlands.parse_code("PEM1C"), {"cls": "EM", "sub": "1", "cls2": None, "sub2": None,
                                                        "regime": "C", "modifiers": ""})
        p = wetlands.parse_code("PEM1/SS1Ch")
        self.assertEqual((p["cls"], p["cls2"], p["sub2"], p["regime"], p["modifiers"]), ("EM", "SS", "1", "C", "h"))
        p = wetlands.parse_code("PFO/USC")
        self.assertEqual((p["cls"], p["sub"], p["cls2"], p["regime"]), ("FO", None, "US", "C"))
        self.assertEqual(wetlands.parse_code("PSSCx")["modifiers"], "x")

    def test_words(self):
        self.assertEqual(wetlands.describe("PEM1C"),
                         "Freshwater emergent wetland (marsh or wet meadow), seasonally flooded")
        self.assertEqual(wetlands.describe("PSS1Ch"),
                         "Freshwater scrub-shrub wetland, broad-leaved deciduous, seasonally flooded (diked or "
                         "impounded)")
        self.assertEqual(wetlands.describe("PEM1/SSA"),
                         "Freshwater emergent wetland (marsh or wet meadow), mixed with scrub-shrub wetland, "
                         "temporarily flooded")
        self.assertIn("non-persistent", wetlands.describe("PEM2F"))
        self.assertTrue(wetlands.describe("PFOA").startswith("Freshwater forested wetland, temporarily"))

    def test_only_vegetated_palustrine_counts(self):
        for code in ("PUBHx", "PUSCx", "PAB4/UBF", "R4SBC", "L2UBH", "", None, "pem1c", "PEM1Cz"):
            with self.subTest(code=code):
                self.assertFalse(wetlands.is_vegetated(code))
        with self.assertRaises(wetlands.CodeError):
            wetlands.parse_code("R4SBC")
        with self.assertRaises(wetlands.CodeError):
            wetlands.describe("PEM1Cq")


class EraAndPresenceTest(unittest.TestCase):
    def test_era(self):
        self.assertEqual(wetlands.era_of(1981, "CIR"), "old")
        self.assertEqual(wetlands.era_of(1983, "CIR"), "old")
        self.assertEqual(wetlands.era_of(2009, "CIR"), "recent")
        self.assertEqual(wetlands.era_of(2017, "TC"), "recent")
        self.assertEqual(wetlands.era_of(None, "Scalable"), "interim")
        self.assertEqual(wetlands.era_of(2017, "Scalable"), "interim")

    def test_recent_and_unknown_are_kept_as_mapped(self):
        for era in ("recent", "unknown"):
            self.assertEqual(wetlands.presence(era, built=0.9, cultivated=0.9), ("kept", None))

    def test_built(self):
        p = wetlands.presence
        self.assertEqual(p("old", built=0.5), ("retired", "built"))
        self.assertEqual(p("old", built=0.49), ("kept", None))
        # A quarter built with developed at half, and nothing standing for a wetland
        self.assertEqual(p("old", built=0.25, developed=0.5), ("retired", "built"))
        self.assertEqual(p("old", built=0.25, developed=0.5, support=True), ("kept", None))
        self.assertEqual(p("old", built=0.25, developed=0.49), ("kept", None))
        # CDL's developed classes never retire a polygon on their own
        self.assertEqual(p("old", developed=1.0), ("kept", None))
        self.assertEqual(p("interim", built=0.6), ("retired", "built"))

    def test_farmed(self):
        p = wetlands.presence
        self.assertEqual(p("old", cultivated=0.5), ("retired", "farmed"))
        self.assertEqual(p("old", cultivated=0.5, support=True), ("flagged", "farmed_supported"))
        self.assertEqual(p("old", cultivated=0.49), ("kept", None))

    def test_hay_pasture_and_order(self):
        p = wetlands.presence
        self.assertEqual(p("old", hay_pasture=0.5), ("flagged", "hay_pasture"))
        self.assertEqual(p("old", hay_pasture=0.4), ("kept", None))
        # built wins over farmed, farmed over hay
        self.assertEqual(p("old", built=0.6, cultivated=0.9), ("retired", "built"))
        self.assertEqual(p("old", cultivated=0.6, hay_pasture=0.6), ("retired", "farmed"))

    def test_verdict_uses_support_and_leaves_unchecked_alone(self):
        row = {"key": "k", "attribute": "PEM1Ch", "era": "old", "checked": True, "built": 0.0, "developed": 0.0,
               "cultivated": 0.8, "hay_pasture": 0.0, "cdl_wetland": 0.3, "osm": False, "nhd": False}
        v = wetlands.verdict(row)
        self.assertEqual((v["presence"], v["reason"], v["drawn"], v["thin"]), ("flagged", "farmed_supported", True, True))
        self.assertEqual((v["support"], v["regime"], v["modifiers"]), (["cdl"], "C", "h"))
        v = wetlands.verdict({**row, "cdl_wetland": 0.1})
        self.assertEqual((v["presence"], v["reason"], v["drawn"]), ("retired", "farmed", False))
        v = wetlands.verdict({**row, "cdl_wetland": 0.1, "nhd": True, "osm": True})   # only USDA land cover supports
        self.assertEqual((v["presence"], v["reason"], v["support"]), ("retired", "farmed", ["osm", "nhd"]))
        v = wetlands.verdict({**row, "checked": False})
        self.assertEqual((v["presence"], v["drawn"]), ("unchecked", False))
        v = wetlands.verdict({**row, "era": "recent", "checked": False})
        self.assertEqual((v["presence"], v["drawn"], v["thin"]), ("kept", True, False))


class ZoomTest(unittest.TestCase):
    def test_tufts_and_thinned_tufts(self):
        self.assertEqual(wetlands.wetland_minzoom(1e5), 14)
        self.assertEqual(wetlands.wetland_minzoom(1e5, thin=True), 15)

    def test_small_ones_wait_for_the_zoom_they_can_be_read_at(self):
        zs = [wetlands.wetland_minzoom(a) for a in (1e5, 5000, 1500, 400, 100, 61)]
        self.assertEqual(zs, sorted(zs))
        self.assertEqual(zs[0], 14)
        self.assertEqual(zs[-1], 16)
        self.assertLessEqual(max(wetlands.wetland_minzoom(a, True) for a in (1, 1e6)), 16)

    def test_rules_hands_wetlands_to_it(self):
        self.assertEqual(rules.body_minzoom("wetland", 1e6), 14)
        self.assertEqual(rules.body_minzoom("wetland", 1e6, thin=True), 15)
        self.assertEqual(rules.body_minzoom("pond", 1e6, thin=True), 8)


def albers_gpkg(path, wetland_rows, project_rows, srs=100001):
    """An nwi_mapbox.gpkg as the cut on the server has it (layers wetlands and project_metadata). Geometries are given
    as WKB bytes already in Albers."""
    g = S.Gpkg(path)
    g.table("wetlands", [("ATTRIBUTE", "text"), ("WETLAND_TYPE", "text"), ("QAQC_CODE", "text"), ("ACRES", "real"),
                         ("NWI_ID", "text"), ("hu8", "text")], "geom", "MULTIPOLYGON", srs=srs)
    g.table("project_metadata", [("PROJECT_NAME", "text"), ("IMAGE_YR", "integer"), ("IMAGE_DATE", "text"),
                                 ("IMAGE_SCALE", "integer"), ("SOURCE_TYPE", "text"), ("hu8", "text")],
            "geom", "MULTIPOLYGON", srs=srs)
    for r in wetland_rows:
        g.insert("wetlands", r)
    for r in project_rows:
        g.insert("project_metadata", r)
    g.close()


def wetland(nwi_id, code, wkb, kind="Freshwater Emergent Wetland"):
    return {"ATTRIBUTE": code, "WETLAND_TYPE": kind, "QAQC_CODE": "NNNNNN", "ACRES": 1.0, "NWI_ID": nwi_id,
            "hu8": "17050114", "geom": S.gp(wkb, srs=100001)}


class ReadTest(unittest.TestCase):
    def test_keeps_only_vegetated_palustrine_and_numbers_shared_ids(self):
        sq = S.wkb_multipolygon([S.box_square(0, 0, 50)])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nwi.gpkg")
            albers_gpkg(path, [wetland("A", "PEM1C", sq), wetland("A", "PEM1Cx", sq), wetland("B", "PSS1A", sq),
                               wetland("C", "PUBHx", sq, "Freshwater Pond"), wetland("D", "R4SBC", sq, "Riverine"),
                               wetland("E", "PAB4/UBF", sq, "Freshwater Pond"), wetland("F", "PFO1A", sq)],
                        [{"PROJECT_NAME": "Test", "IMAGE_YR": 1981, "IMAGE_DATE": "07/81", "IMAGE_SCALE": 58000,
                          "SOURCE_TYPE": "CIR", "hu8": "17050114", "geom": S.gp(sq, srs=100001)}])
            wets, projects, skipped = wetlands.read(path)
        self.assertEqual([w[0] for w in wets], ["A", "A#2", "B", "F"])
        self.assertEqual([w[2] for w in wets], ["PEM1C", "PEM1Cx", "PSS1A", "PFO1A"])
        self.assertEqual(skipped["not vegetated palustrine"], 3)
        self.assertEqual(len(projects), 1)

    def test_refuses_what_it_does_not_read(self):
        sq = S.wkb_multipolygon([S.box_square(0, 0, 50)])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nwi.gpkg")
            albers_gpkg(path, [wetland("A", "PEM1C", sq)], [], srs=4326)
            with self.assertRaises(wetlands.LoadError):
                wetlands.read(path)
            albers_gpkg(path, [wetland("C", "PUBHx", sq)], [])
            with self.assertRaises(wetlands.LoadError):
                wetlands.read(path)                    # no vegetated wetland at all
            g = S.Gpkg(path)
            g.table("other", [("a", "text")])
            g.close()
            with self.assertRaises(wetlands.LoadError):
                wetlands.read(path)


class SharesFileTest(unittest.TestCase):
    def write(self, doc):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        path = os.path.join(d, "shares.json")
        with open(path, "w") as f:
            json.dump(doc, f)
        return path

    ROW = {"key": "A", "built": 0.1, "developed": 0.0, "cultivated": 0.2, "hay_pasture": 0.0, "cdl_wetland": 0.3}

    def test_reads(self):
        on, inputs, rows = wetlands.read_shares(self.write({"computed_on": "2026-10-24", "inputs": {"cdl": "2025"},
                                                            "polygons": [{**self.ROW, "hydric": 0.5}]}))
        self.assertEqual((str(on), inputs["cdl"], rows[0][0], rows[0][-1]), ("2026-10-24", "2025", "A", 0.5))

    def test_refuses_bad_files(self):
        for doc in ({"polygons": [self.ROW]},                                                  # no date
                    {"computed_on": "2026-10-24", "polygons": []},
                    {"computed_on": "2026-10-24", "polygons": [{**self.ROW, "built": 1.5}]},
                    {"computed_on": "2026-10-24", "polygons": [{**self.ROW, "cultivated": None}]},
                    {"computed_on": "2026-10-24", "polygons": [{**self.ROW, "hydric": -0.1}]},
                    {"computed_on": "2026-10-24", "polygons": [self.ROW, self.ROW]},
                    {"computed_on": "2026-10-24", "polygons": [{"built": 0}]}):
            with self.subTest(doc=doc), self.assertRaises(wetlands.LoadError):
                wetlands.read_shares(self.write(doc))


def need_db(cls):
    return unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with water 0003)")(cls)


def gj_square(x, y, size):
    return json.dumps({"type": "Polygon", "coordinates": [[list(p) for p in S.box_square(x, y, size)[0]]]})


def gj_rect(x, y, w, h):
    return json.dumps({"type": "Polygon", "coordinates": [[list(S.at(*p)) for p in
                                                           ((x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y))]]})


def gj_poly(points):
    return json.dumps({"type": "Polygon", "coordinates": [[list(S.at(*p)) for p in points]]})


@need_db
class LoadTest(unittest.TestCase):
    """nwi-load and nwi-presence, with real Albers coordinates from PostGIS. nwi-load commits, so this cleans up."""

    def clean(self):
        c = self.conn
        c.rollback()
        for t in ("water.nwi_presence", "water.nwi_wetland", "water.nwi_project"):
            c.execute(f"delete from {t}")
        c.execute("delete from water.load where source = 'nwi'")
        c.commit()

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        self.clean()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.clean)

    def albers(self, x, y, size):
        return bytes(self.conn.execute(
            "select ST_AsBinary(ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 5070)))",
            (gj_square(x, y, size),)).fetchone()[0])

    def test_load_eras_keys_and_reload(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nwi.gpkg")
            albers_gpkg(path, [
                wetland("W1", "PEM1C", self.albers(100, 100, 80)),                # in the 1981 stretch
                wetland("W2", "PSS1A", self.albers(2100, 100, 80)),               # in the 2017 stretch
                wetland("W2", "PSS1Ax", self.albers(2300, 100, 80)),              # a second part of W2
                wetland("W3", "PEM1B", self.albers(4100, 100, 80)),               # in the interim stretch
                wetland("W4", "PEM1A", self.albers(9000, 9000, 80)),              # in no project
                wetland("P1", "PUBHx", self.albers(100, 100, 40), "Freshwater Pond")],
                [{"PROJECT_NAME": "Test Quad", "IMAGE_YR": 1981, "IMAGE_DATE": "07/81", "IMAGE_SCALE": 58000,
                  "SOURCE_TYPE": "CIR", "hu8": "17050114", "geom": S.gp(self.albers(0, 0, 1000), srs=100001)},
                 {"PROJECT_NAME": "Test BLM", "IMAGE_YR": 2017, "IMAGE_DATE": "xx/17", "IMAGE_SCALE": 1,
                  "SOURCE_TYPE": "TC", "hu8": "17050114", "geom": S.gp(self.albers(2000, 0, 1000), srs=100001)},
                 {"PROJECT_NAME": "ID_Scalable", "IMAGE_YR": None, "IMAGE_DATE": "<Null>", "IMAGE_SCALE": None,
                  "SOURCE_TYPE": "Scalable", "hu8": "17050112", "geom": S.gp(self.albers(4000, 0, 1000), srs=100001)}])
            dry = wetlands.load(self.conn, path, dry_run=True)
            self.assertEqual(dry["would load"]["wetlands"], 5)
            stats = wetlands.load(self.conn, path)
            rows = dict((k, (e, y, p)) for k, e, y, p in self.conn.execute(
                "select key, era, image_year, project from water.nwi_wetland"))
            self.assertEqual(rows, {"W1": ("old", 1981, "Test Quad"), "W2": ("recent", 2017, "Test BLM"),
                                    "W2#2": ("recent", 2017, "Test BLM"), "W3": ("interim", None, "ID_Scalable"),
                                    "W4": ("unknown", None, None)})
            self.assertEqual(stats["era old"], 1)
            # In Boise, not where Albers coordinates read as degrees would put it
            lon, lat = self.conn.execute("select ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom)) "
                                         "from water.nwi_wetland where key = 'W1'").fetchone()
            self.assertAlmostEqual(lon, S.at(140, 140)[0], places=5)
            self.assertAlmostEqual(lat, S.at(140, 140)[1], places=5)
            self.assertTrue(self.conn.execute("select count(*) from water.load where source = 'nwi'").fetchone()[0])
            again = wetlands.load(self.conn, path)
            self.assertEqual(again["loaded"], "nothing")
            # Shares: stored, replaced, and dropped when the outline changes
            sp = os.path.join(d, "shares.json")
            with open(sp, "w") as f:
                json.dump({"computed_on": "2026-10-24", "polygons": [
                    {"key": "W1", "built": 0.6, "developed": 0.0, "cultivated": 0.0, "hay_pasture": 0.0,
                     "cdl_wetland": 0.0}]}, f)
            self.assertEqual(wetlands.load_shares(self.conn, sp, dry_run=True), {"would store": 1})
            self.assertEqual(wetlands.load_shares(self.conn, sp)["stored"], 1)
            self.conn.commit()
            with open(sp, "w") as f:
                json.dump({"computed_on": "2026-10-24", "polygons": [
                    {"key": "NOPE", "built": 0, "developed": 0, "cultivated": 0, "hay_pasture": 0,
                     "cdl_wetland": 0}]}, f)
            with self.assertRaises(wetlands.LoadError):
                wetlands.load_shares(self.conn, sp)
            self.conn.rollback()
            albers_gpkg(path, [wetland("W1", "PEM1C", self.albers(100, 100, 90))], [
                {"PROJECT_NAME": "Test Quad", "IMAGE_YR": 1981, "IMAGE_DATE": "07/81", "IMAGE_SCALE": 58000,
                 "SOURCE_TYPE": "CIR", "hu8": "17050114", "geom": S.gp(self.albers(0, 0, 1000), srs=100001)}])
            wetlands.load(self.conn, path)
            self.assertEqual(self.conn.execute("select count(*) from water.nwi_presence").fetchone()[0], 0)
            self.assertEqual(self.conn.execute("select count(*) from water.nwi_wetland").fetchone()[0], 1)


@need_db
class ConflationTest(unittest.TestCase):
    """water-build's wetlands, on invented polygons (metres from a corner near Kuna), in a transaction rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        from ingest import db
        from plugins.water.ingest import build
        from plugins.water.ingest.sources import nhd_hr, nwi
        cls.conn = c = psycopg.connect(DB_URL)
        for t in ("water.nwi_presence", "water.nwi_wetland", "water.nwi_project", "water.osm_feature",
                  "water.nhd_flowline", "water.nhd_polygon", "water.nhd_line", "water.nhd_point", "water.nhd_flow",
                  "water.hydroshare_canal", "water.idwr_org", "water.idwr_season"):
            c.execute(f"delete from {t}")
        db.ensure_source(c, nhd_hr.SOURCE)
        db.ensure_source(c, nwi.SOURCE)
        load = c.execute("insert into water.load (source, file, sha256) values ('nwi', 'nwi.gpkg', 'x') "
                         "returning id").fetchone()[0]
        nhd_load = c.execute("insert into water.load (source, file, sha256) values ('nhd_hr', 'nhd.gpkg', 'x') "
                             "returning id").fetchone()[0]

        def osm(osm_id, geom, **tags):
            c.execute("""insert into water.osm_feature (osm_type, osm_id, shape, kind, name, tags, geom, first_seen,
                           last_seen) values ('w', %s, 'area', 'wetland', null, %s::jsonb,
                             ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s)""",
                      (osm_id, json.dumps(tags), geom, T0, T0))

        def nwi_poly(key, code, era, geom, year=None):
            c.execute("""insert into water.nwi_wetland (key, nwi_id, attribute, era, image_year, geom, load_id)
                         values (%s, %s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                      (key, key, code, era, year, geom, load))

        def shares(key, built=0.0, developed=0.0, cultivated=0.0, hay=0.0, cdl=0.0):
            c.execute("""insert into water.nwi_presence (key, built, developed, cultivated, hay_pasture, cdl_wetland,
                           computed_on) values (%s, %s, %s, %s, %s, %s, '2026-10-24')""",
                      (key, built, developed, cultivated, hay, cdl))

        def marsh(pid, geom):
            c.execute("""insert into water.nhd_polygon (permanent_identifier, layer, ftype, ftype_name, geom, load_id)
                         values (%s, 'waterbody', 466, 'Swamp/Marsh', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                                 %s)""", (pid, geom, nhd_load))

        # A: OSM and NWI outline one wetland (NWI's 10 m off: 19% of it is left, under 2,000 m2); B: NWI alone,
        # 2017; C: 1981, mostly roofs and paving; D: 1981, in a field but with wetland on the land cover; E: 1981,
        # not checked yet; F: 1981 hay; G: 1981, nothing against it; H: NWI's marsh with an NHD marsh on it; I: NWI
        # too small to draw; J: NWI overlapping an OSM wetland a little (30%: not absorbed, so it draws what OSM's
        # outline leaves); K: NHD's marsh alone
        osm(BASE + 1, gj_square(0, 0, 100), natural="wetland")
        nwi_poly("A", "PEM1Ch", "recent", gj_square(10, 10, 100), 2017)
        nwi_poly("B", "PSS1A", "recent", gj_square(500, 0, 80), 2017)
        nwi_poly("C", "PEM1C", "old", gj_square(1000, 0, 80), 1981)
        shares("C", built=0.6, developed=0.7)
        nwi_poly("D", "PEM1F", "old", gj_square(1500, 0, 80), 1981)
        shares("D", cultivated=0.8, cdl=0.5)
        nwi_poly("E", "PEM1A", "old", gj_square(2000, 0, 80), 1981)
        nwi_poly("F", "PEM1B", "old", gj_square(2500, 0, 80), 1981)
        shares("F", hay=0.7)
        nwi_poly("G", "PSS1C", "interim", gj_square(3000, 0, 80))
        shares("G")
        nwi_poly("H", "PEM1C", "recent", gj_square(3500, 0, 80), 2017)
        marsh("{M-H}", gj_square(3505, 5, 70))
        nwi_poly("I", "PEM1C", "recent", gj_square(4000, 0, 6), 2017)
        osm(BASE + 2, gj_square(4570, 0, 100), natural="wetland")
        nwi_poly("J", "PEM1C", "recent", gj_square(4500, 0, 100), 2017)
        marsh("{M-K}", gj_square(5000, 0, 100))
        # L: 1981, retired as built, with an NHD marsh on it; M: a big NWI polygon with a small OSM wetland inside;
        # N: an NHD pond with an NWI wetland over most of it
        nwi_poly("L", "PEM1C", "old", gj_square(6000, 0, 100), 1981)
        shares("L", built=0.9, developed=0.9)
        marsh("{M-L}", gj_square(6000, 0, 100))
        nwi_poly("M", "PEM1C", "recent", gj_square(7000, 0, 300), 2017)
        osm(BASE + 4, gj_square(7100, 100, 40), natural="wetland")
        nwi_poly("N", "PEM1C", "recent", gj_square(8000, 0, 80), 2017)
        c.execute("""insert into water.nhd_polygon (permanent_identifier, layer, ftype, ftype_name, geom, load_id)
                     values ('{P-N}', 'waterbody', 390, 'Lake/Pond',
                             ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (gj_square(8000, 0, 100), nhd_load))
        # S1-S5: one OSM wetland (250 x 200 m) tiled by five NWI class polygons; P: a 100 m OSM wetland and NWI's
        # outline of it 15 m off (an L-shaped strip 15 m wide is left); Q: a 100 m OSM wetland inside NWI's 116 m
        # outline (a frame 8 m wide); W: NWI's outline 25 m longer on one side (a real piece); R: a 400 m NWI polygon
        # with a 310 x 400 m OSM wetland on it (16 ha, 3.6 ha left); V: NWI's outline 3 m wider along one side of a
        # 1 km OSM wetland; T: an OSM wetland drawn as a bow tie (self-intersecting), with NWI over it; Z, X1, X2,
        # X4: NWI polygons that only touch an OSM wetland (80 m2 of a 40 m square; 100 m2 of 30 x 50 m; 10 m2 of a
        # 5 x 1,000 m strip; 24% of a 50 m square): less than half inside, so they draw all but OSM's outline
        osm(BASE + 5, gj_rect(9000, 0, 250, 200), natural="wetland")
        for key, code, x, w in (("S1", "PEM1C", 9000, 40), ("S2", "PSS1C", 9040, 40), ("S3", "PEM1A", 9080, 80),
                                ("S4", "PFO1A", 9160, 40), ("S5", "PEM1F", 9200, 50)):
            nwi_poly(key, code, "recent", gj_rect(x, 0, w, 200), 2017)
        osm(BASE + 6, gj_square(10000, 0, 100), natural="wetland")
        nwi_poly("P", "PEM1C", "recent", gj_square(10015, 15, 100), 2017)
        osm(BASE + 7, gj_square(11008, 8, 100), natural="wetland")
        nwi_poly("Q", "PEM1C", "recent", gj_square(11000, 0, 116), 2017)
        osm(BASE + 8, gj_rect(12000, 0, 310, 400), natural="wetland")
        nwi_poly("R", "PEM1C", "recent", gj_rect(12000, 0, 400, 400), 2017)
        osm(BASE + 9, gj_rect(13000, 0, 1000, 100), natural="wetland")
        nwi_poly("V", "PEM1C", "recent", gj_rect(13000, -3, 1000, 103), 2017)
        osm(BASE + 10, gj_poly(((16000, 0), (16100, 100), (16100, 0), (16000, 100), (16000, 0))), natural="wetland")
        nwi_poly("T", "PSS1C", "recent", gj_square(16000, 0, 100), 2017)
        osm(BASE + 11, gj_square(17000, 0, 200), natural="wetland")
        nwi_poly("Z", "PEM1C", "recent", gj_square(17198, 80, 40), 2017)
        nwi_poly("X1", "PEM1C", "recent", gj_rect(16972, 50, 30, 50), 2017)
        nwi_poly("X2", "PEM1C", "recent", gj_rect(17195, 198, 1000, 5), 2017)
        osm(BASE + 12, gj_square(19000, 0, 100), natural="wetland")
        nwi_poly("X4", "PEM1C", "recent", gj_square(19088, 0, 50), 2017)
        osm(BASE + 13, gj_square(20000, 0, 100), natural="wetland")
        nwi_poly("W", "PEM1C", "recent", gj_rect(20000, 0, 100, 125), 2017)
        c.execute("""insert into water.osm_feature (osm_type, osm_id, shape, kind, name, tags, geom, first_seen,
                       last_seen) values ('w', %s, 'line', 'canal', null, '{}'::jsonb,
                         ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s)""",
                  (BASE + 3, json.dumps({"type": "LineString", "coordinates": [list(S.at(0, -500)),
                                                                                list(S.at(2000, -500))]}), T0, T0))
        cls.build_id, cls.counts = build.build(c, out=lambda msg: None)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def body(self, key):
        return self.q("""select geometry_from, wetland_class, water_regime, modifiers, confirmed, thin, presence,
                                presence_reason, minzoom, image_year, round(area_m2::numeric)
                         from water.body where nwi_key = %s order by geometry_from desc""", key)

    def test_osm_outline_with_nwi_class(self):
        row = self.body("A")
        self.assertEqual(len(row), 1)
        src, cls, regime, mods, confirmed, thin, pres, reason, z, year, area = row[0]
        self.assertEqual((src, cls, regime, mods, confirmed, thin, pres), ("osm", "PEM1Ch", "C", "h", True, False, None))
        self.assertEqual((z, year), (14, 2017))
        self.assertAlmostEqual(float(area), 10000, delta=20)   # OSM's 100 m square, not NWI's offset one
        self.assertEqual(self.q("select count(*) from water.body where osm_id = %s", BASE + 1), [(1,)])

    def test_nwi_alone_draws_from_nwi(self):
        src, cls, _, _, confirmed, thin, pres, _, z, _, area = self.body("B")[0]
        self.assertEqual((src, cls, confirmed, thin, pres, z), ("nwi", "PSS1A", False, False, None, 14))
        self.assertAlmostEqual(float(area), 6400, delta=100)  # simplified, but the same square

    def test_old_mapping_after_the_presence_check(self):
        self.assertEqual(self.body("C"), [])
        self.assertEqual(self.body("E"), [])
        d = self.body("D")[0]
        self.assertEqual((d[0], d[5], d[6], d[7]), ("nwi", True, "flagged", "farmed_supported"))
        self.assertGreaterEqual(d[8], 15)
        f = self.body("F")[0]
        self.assertEqual((f[5], f[6], f[7]), (True, "flagged", "hay_pasture"))
        g = self.body("G")[0]
        self.assertEqual((g[5], g[6], g[7]), (True, None, None))
        self.assertGreaterEqual(g[8], 15)

    def test_every_polygon_keeps_its_outcome(self):
        rows = {k: (p, r, d) for k, p, r, d in self.q(
            "select key, presence, reason, drawn from water.wetland_check where build_id = %s", self.build_id)}
        self.assertEqual(rows["C"], ("retired", "built", False))
        self.assertEqual(rows["D"], ("flagged", "farmed_supported", True))
        self.assertEqual(rows["E"], ("unchecked", None, False))
        self.assertEqual(rows["G"], ("kept", None, True))
        self.assertEqual(rows["A"], ("kept", None, True))
        self.assertEqual(len(rows), 28)
        shares = self.q("select built, developed, support from water.wetland_check where key = 'C' and build_id = %s",
                        self.build_id)
        self.assertEqual((round(shares[0][0], 1), round(shares[0][1], 1)), (0.6, 0.7))
        self.assertEqual(self.q("select support from water.wetland_check where key = 'D' and build_id = %s",
                                self.build_id), [(["cdl"],)])
        # an absorbed polygon points at the body that drew it
        self.assertIsNotNone(self.q("select body_id from water.wetland_check where key = 'A' and build_id = %s",
                                    self.build_id)[0][0])

    def test_nhd_marsh_is_evidence_where_nwi_has_it(self):
        self.assertEqual(self.q("select count(*) from water.body where nhd_pid = '{M-H}'"), [(0,)])
        self.assertEqual(self.q("select confirmed from water.body where nwi_key = 'H'"), [(True,)])
        row = self.q("select geometry_from, thin, minzoom, kind from water.body where nhd_pid = '{M-K}'")
        self.assertEqual(row, [("nhd", True, 15, "wetland")])

    def test_retired_nwi_is_not_redrawn_by_nhd(self):
        self.assertEqual(self.body("L"), [])
        self.assertEqual(self.q("select count(*) from water.body where nhd_pid = '{M-L}'"), [(0,)])

    def test_small_osm_wetland_inside_a_big_nwi_polygon(self):
        # the OSM wetland lies wholly in NWI's polygon, so it takes the class and is confirmed; the polygon, less
        # than half inside it, is not absorbed and still draws everything but OSM's outline
        m = [r for r in self.body("M") if r[0] == "nwi"][0]
        self.assertAlmostEqual(float(m[10]), 90000 - 1600, delta=500)
        self.assertEqual(self.q("select wetland_class, confirmed from water.body where osm_id = %s", BASE + 4),
                         [("PEM1C", True)])

    def check_row(self, key):
        return self.q("select body_id, drawn from water.wetland_check where key = %s and build_id = %s",
                      key, self.build_id)[0]

    def osm_body(self, n):
        return self.q("select id, wetland_class, confirmed, nwi_key from water.body where osm_id = %s", BASE + n)[0]

    def test_nwi_class_parts_under_one_osm_wetland(self):
        # NWI splits a wetland by class and regime: the OSM wetland takes the largest part's class, is confirmed, and
        # every part's check row points at it
        oid, cls, confirmed, key = self.osm_body(5)
        self.assertEqual((cls, confirmed, key), ("PEM1A", True, "S3"))
        self.assertEqual(self.q("select count(*) from water.body where geometry_from = 'nwi' and nwi_key ~ '^S[1-5]$'"),
                         [(0,)])
        for k in ("S1", "S2", "S3", "S4", "S5"):
            self.assertEqual(self.check_row(k), (oid, True), k)

    def test_shifted_outline_leaves_no_strip(self):
        # 100 m squares 15 m off: the L-shaped strip left (2,775 m2, 15 m wide) is above the area floor
        oid, cls, confirmed, _ = self.osm_body(6)
        self.assertEqual((cls, confirmed), ("PEM1C", True))
        self.assertEqual(self.q("select count(*) from water.body where nwi_key = 'P'"), [(1,)])
        self.assertEqual(self.check_row("P"), (oid, True))

    def test_wider_outline_leaves_no_frame(self):
        # a 100 m square inside NWI's 116 m one: a frame 8 m wide, 3,456 m2
        oid, cls, confirmed, _ = self.osm_body(7)
        self.assertEqual((cls, confirmed), ("PEM1C", True))
        self.assertEqual(self.q("select count(*) from water.body where nwi_key = 'Q'"), [(1,)])
        self.assertEqual(self.check_row("Q"), (oid, True))

    def test_a_leftover_25_m_wide_is_a_real_piece(self):
        # 100 x 125 m NWI over a 100 m OSM wetland: 80% inside, 2,500 m2 left and 5 m of it survives the 10 m inset
        w = [r for r in self.body("W") if r[0] == "nwi"]
        self.assertEqual(len(w), 1)
        self.assertAlmostEqual(float(w[0][10]), 2500, delta=100)
        self.assertEqual(self.check_row("W")[1], True)
        self.assertEqual(self.check_row("W")[0], self.q("select id from water.body where nwi_key = 'W' and "
                                                         "geometry_from = 'nwi'")[0][0])

    def test_a_polygon_that_only_touches_an_osm_wetland_still_draws(self):
        # less than half inside OSM's wetlands: all of it but OSM's outline draws, however small the piece or thin the
        # shape, and its check row points at the body that draws it, not at the OSM wetland
        for key, area, delta in (("Z", 1520, 40), ("X1", 1400, 40), ("X2", 4990, 100), ("X4", 1900, 60)):
            rows = [r for r in self.body(key) if r[0] == "nwi"]
            self.assertEqual(len(rows), 1, key)
            self.assertAlmostEqual(float(rows[0][10]), area, delta=delta, msg=key)
            drawn = self.q("select id from water.body where nwi_key = %s and geometry_from = 'nwi'", key)[0][0]
            self.assertEqual(self.check_row(key), (drawn, True), key)
        # and they lend nothing to the large OSM wetland they touch
        self.assertEqual(self.osm_body(11)[1:], (None, False, None))

    def test_thin_leftover_is_dropped_however_large(self):
        # 3,000 m2 of leftover, but only 3 m wide
        oid = self.osm_body(9)[0]
        self.assertEqual(self.q("select count(*) from water.body where nwi_key = 'V'"), [(1,)])
        self.assertEqual(self.check_row("V"), (oid, True))

    def test_a_large_leftover_draws_even_when_a_small_share(self):
        oid, cls, confirmed, _ = self.osm_body(8)
        self.assertEqual((cls, confirmed), ("PEM1C", True))
        r = [x for x in self.body("R") if x[0] == "nwi"]
        self.assertEqual(len(r), 1)
        self.assertAlmostEqual(float(r[0][10]), 36000, delta=300)       # 22% of the polygon
        drawn = self.q("select id from water.body where nwi_key = 'R' and geometry_from = 'nwi'")[0][0]
        self.assertEqual(self.check_row("R"), (drawn, True))

    def test_self_intersecting_osm_wetland(self):
        # a bow tie is valid once repaired: its two triangles are wetland (half of NWI's square, so it is confirmed),
        # and NWI's polygon draws the other two
        oid, cls, confirmed, _ = self.osm_body(10)
        self.assertEqual((cls, confirmed), ("PSS1C", True))
        self.assertAlmostEqual(self.q("select area_m2 from water.body where id = %s", oid)[0][0], 5000, delta=100)
        t = [r for r in self.body("T") if r[0] == "nwi"]
        self.assertAlmostEqual(float(t[0][10]), 5000, delta=100)

    def test_nwi_wetland_does_not_suppress_an_nhd_pond(self):
        self.assertEqual(self.q("select kind, geometry_from from water.body where nhd_pid = '{P-N}'"),
                         [("pond", "nhd")])

    def test_small_and_partly_overlapping(self):
        self.assertEqual(self.body("I"), [])                  # 36 m2: under the drawing minimum
        self.assertEqual(self.q("select count(*) from water.body where osm_id = %s", BASE + 2), [(1,)])
        # J overlaps OSM's wetland by 30%: drawn, but only the part OSM doesn't outline
        j = self.body("J")[0]
        self.assertEqual(j[0], "nwi")
        self.assertAlmostEqual(float(j[10]), 7000, delta=200)

    def test_counts(self):
        c = self.counts
        self.assertEqual((c["nwi_polygons"], c["nwi_retired"], c["nwi_unchecked"], c["nwi_flagged"], c["nwi_kept"]),
                         (28, 2, 1, 2, 23))
        # by polygon: A, B, D, F, G, H, J, M, N, then S3 (the strips' class), P, Q, R, V, T, then Z, X1, X2, X4, W
        self.assertEqual(c["wetlands_nwi"], 20)
        self.assertEqual(c["wetlands"], 28)                  # 12 OSM, 15 NWI (R, T and W draw a leftover too), NHD's K
        self.assertEqual(c["wetlands_thin"], 4)              # D, F, G and NHD's marsh K

    def test_export_rows_have_the_wetland_columns(self):
        from plugins.water.ingest import export
        cur = self.conn.execute(export.BODIES_ROWS, {"build": self.build_id})
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
        self.assertIn("thin", cols)
        self.assertTrue(rows and all(r[cols.index("thin")] is not None for r in rows))
        thin = {r[cols.index("id")] for r in rows if r[cols.index("thin")]}
        self.assertEqual(len(thin), 4)

    def test_qa_rows_and_box_counts(self):
        import csv
        with tempfile.TemporaryDirectory() as d:
            path, n = wetlands.write_qa(self.conn, self.build_id, d)
            with open(path, newline="") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(n, 6)                                    # C, D, E, F, G, L
        self.assertEqual([(r["key"], r["presence"], r["reason"]) for r in rows[:2]],
                         [("C", "retired", "built"), ("L", "retired", "built")])
        self.assertEqual(rows[0]["support"], "")
        x, y = (lambda p: (p[0], p[1]))(__import__("ingest.utm", fromlist=["to_utm"]).to_utm(*S.at(1040, 40)))
        counts = wetlands.box_counts(self.conn, self.build_id, {"hit": (x - 100, y - 100, x + 100, y + 100),
                                                               "miss": (x + 20000, y, x + 20200, y + 100)})
        self.assertEqual(counts, {"hit": {"retired": 1}, "miss": {}})

    def test_export_credits_nwi_and_carries_thin(self):
        from plugins.water.ingest import export
        with tempfile.TemporaryDirectory() as archive:
            m, _ = export.export(self.conn, archive, build="20261024T120000Z", min_features={})
            bodies = {lay.name: lay for lay in m.layers}["bodies"]
            self.assertEqual(bodies["inputs"], ["osm", "nhd", "nwi"])
            self.assertIn("thin", bodies["fields"])
            self.assertEqual(bodies["republish"], "yes")
            self.assertIn("U.S. Fish and Wildlife Service, National Wetlands Inventory", " ".join(bodies["credit"]))
            self.assertIn("nwi", m.inputs)
            layers = {lay.name: lay for lay in m.layers}
            self.assertNotIn("nwi", layers["reaches"]["inputs"])      # NWI is in the bodies layer only
            self.assertNotIn("nwi", layers["mask"]["inputs"])


if __name__ == "__main__":
    unittest.main()
