"""Water's new sources: the osm_waterways consumer of core's OpenStreetMap loader, IDWR's two layers, and the manual
NHD and HydroShare entries. Offline, but for the database cases, which run only against a scratch database named by
TVT_TEST_DATABASE_URL (with water 0001), inside a transaction that is rolled back. Fixtures are invented.

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import unittest
from datetime import datetime, timezone

from ingest import manifest, osm_extract
from plugins.water.ingest import idwr
from plugins.water.ingest.sources import (hydroshare_canals, idwr_irrigation_orgs, idwr_season_of_use, nhd_hr,
                                          osm_waterways)

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
LINE = {"type": "LineString", "coordinates": [[-116.5, 43.4], [-116.49, 43.4]]}
AREA = {"type": "Polygon", "coordinates": [[[-116.5, 43.4], [-116.49, 43.4], [-116.49, 43.41], [-116.5, 43.4]]]}
POINT = {"type": "Point", "coordinates": [-116.5, 43.4]}


def water():
    return next(p for p in manifest.find() if p.name == "water")


def feature(kind, osm_id, geometry, geom, **tags):
    return {"type": kind, "osm_id": osm_id, "geometry": geometry, "geom": geom, "tags": tags, "osm_version": 3,
            "osm_timestamp": T0}


class ManifestTest(unittest.TestCase):
    def test_consumer_entry(self):
        c = next(c for c in osm_extract.consumers() if c.id == "water.osm_waterways")
        self.assertEqual(c.tables, (osm_waterways.TABLE,))
        self.assertEqual(c.geometry, ("point", "linestring", "polygon"))
        self.assertFalse(osm_extract.own_gate(osm_waterways))          # its gate is ops.osm_consumer
        self.assertNotIn("osm_waterways", osm_extract.OWNERS)           # not part of the highway partition
        # The approved tag set (decision 2b), and nothing else.
        self.assertEqual(set(c.tags), {"nw/waterway", "a/waterway=riverbank,dock,boatyard,dam,weir",
                                       "n/natural=spring", "a/natural=water,wetland,spring", "a/water",
                                       "a/landuse=reservoir,basin", "a/leisure=swimming_pool"})
        cfg = osm_extract.export_config(c)
        self.assertEqual(cfg["linear_tags"], ["waterway"])
        self.assertIn("leisure=swimming_pool", cfg["area_tags"])

    def test_sources_and_licences(self):
        entries = {e["name"]: e for e in water().manifest["sources"]}
        self.assertEqual((entries["nhd_hr"]["kind"], entries["nhd_hr"]["republish"]), ("manual", "yes"))
        self.assertEqual((entries["hydroshare_canals"]["kind"], entries["hydroshare_canals"]["republish"]),
                         ("manual", "yes"))
        self.assertIn("10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f", entries["hydroshare_canals"]["credit"])
        for name in ("idwr_irrigation_orgs", "idwr_season_of_use"):
            self.assertEqual((entries[name]["kind"], entries[name]["republish"]), ("source", "internal"))
            self.assertIn("Idaho Department of Water Resources", entries[name]["credit"])
        for module in (nhd_hr, hydroshare_canals, osm_waterways):
            self.assertIsNone(module.SOURCE["schedule"])
            self.assertEqual(module.SOURCE["credit"], entries[module.SOURCE["name"]]["credit"])

    def test_manual_sources_make_no_requests(self):
        for module in (nhd_hr, hydroshare_canals, osm_waterways):
            with open(module.__file__, encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("import urllib", text)
            self.assertNotIn("ingest import http", text)
            self.assertFalse(hasattr(module, "run"))
        from ingest.sources import SOURCES
        self.assertIn("idwr_irrigation_orgs", SOURCES)
        self.assertNotIn("nhd_hr", SOURCES)

    def test_the_bake_never_reads_idwr(self):
        from basemap.landscape import plan
        for name in ("idwr_irrigation_orgs", "idwr_season_of_use"):
            self.assertTrue(plan.never(f"water/{name}"))
        for name in ("osm_waterways", "nhd_hr", "hydroshare_canals"):
            self.assertFalse(plan.never(f"water/{name}"))


class KindTest(unittest.TestCase):
    def test_lines(self):
        k = osm_waterways.kind_of
        self.assertEqual(k("line", {"waterway": "canal"}), "canal")
        self.assertEqual(k("line", {"waterway": "brook"}), "stream")
        self.assertEqual(k("line", {"waterway": "pressurised"}), "canal")
        self.assertEqual(k("line", {"waterway": "dam"}), "dam")
        self.assertIsNone(k("line", {"waterway": "riverbank"}))              # an area's outline
        self.assertEqual(k("line", {"waterway": "link"}), "other")

    def test_areas(self):
        k = osm_waterways.kind_of
        self.assertEqual(k("area", {"leisure": "swimming_pool"}), "pool")
        self.assertEqual(k("area", {"natural": "water", "water": "reservoir"}), "reservoir")
        self.assertEqual(k("area", {"landuse": "reservoir"}), "reservoir")
        self.assertEqual(k("area", {"landuse": "basin", "basin": "detention"}), "basin")
        self.assertEqual(k("area", {"natural": "water", "water": "wastewater"}), "wastewater")
        self.assertEqual(k("area", {"natural": "water"}), "water")
        self.assertEqual(k("area", {"natural": "wetland", "wetland": "marsh"}), "wetland")
        self.assertEqual(k("area", {"waterway": "riverbank"}), "river")
        self.assertEqual(k("area", {"natural": "water", "water": "fountain"}), "fountain")
        self.assertEqual(k("area", {"waterway": "dam"}), "dam")

    def test_points(self):
        k = osm_waterways.kind_of
        self.assertEqual(k("point", {"natural": "spring"}), "spring")
        self.assertEqual(k("point", {"waterway": "weir"}), "weir")
        self.assertEqual(k("point", {"waterway": "lock_gate"}), "lock_gate")
        self.assertEqual(k("point", {"waterway": "turning_point"}), "other")

    def test_flags_and_width(self):
        w = osm_waterways
        self.assertTrue(w.intermittent({"intermittent": "yes"}))
        self.assertTrue(w.intermittent({"seasonal": "summer"}))
        self.assertFalse(w.intermittent({"intermittent": "no"}))
        self.assertIsNone(w.intermittent({}))
        self.assertTrue(w.piped({"tunnel": "culvert"}))
        self.assertTrue(w.piped({"covered": "yes"}))
        self.assertTrue(w.piped({"waterway": "pressurised"}))
        self.assertFalse(w.piped({"tunnel": "no"}))
        self.assertEqual(w.width_m("5"), 5.0)
        self.assertEqual(w.width_m("4.5 m"), 4.5)
        self.assertEqual(w.width_m("10 ft"), 3.05)
        self.assertIsNone(w.width_m("wide"))
        self.assertIsNone(w.width_m("0"))
        self.assertEqual(w.layer("-1"), -1)
        self.assertIsNone(w.layer("x"))

    def test_rows(self):
        row = osm_waterways.feature_row(feature("w", 7, "linestring", LINE, waterway="canal", name="  Test   Canal ",
                                                tunnel="culvert", width="6", layer="-1"))
        values = dict(zip([c for c, _ in osm_waterways.COLUMNS], row))
        self.assertEqual((values["osm_type"], values["shape"], values["kind"], values["name"], values["piped"],
                          values["width_m"], values["layer"]), ("w", "line", "canal", "Test Canal", True, 6.0, -1))
        self.assertEqual(json.loads(values["tags"])["name"], "  Test   Canal ")
        self.assertEqual(json.loads(row[-1])["type"], "LineString")
        self.assertIsNone(osm_waterways.feature_row(feature("w", 8, "linestring", LINE, waterway="riverbank")))
        area = osm_waterways.feature_row(feature("r", 9, "polygon", AREA, natural="water", water="pond"))
        self.assertEqual(area[:4], ("r", 9, "area", "pond"))


class IdwrTest(unittest.TestCase):
    def test_owner_is_never_asked_for_or_kept(self):
        self.assertNotIn("Owner", idwr_irrigation_orgs.FIELDS)
        attrs = {"OBJECTID": 4, "NAME": " Test  Irrigation District ", "Owner": "A Person", "PlaceOfUse": -999,
                 "LPOU": "YES", "PROCESS": "SRBA", "ACRES": 1234.567}
        p = idwr_irrigation_orgs.parse(attrs)
        self.assertNotIn("Owner", json.dumps(p))
        self.assertNotIn("A Person", json.dumps(p))
        self.assertEqual(p, {"name": "Test Irrigation District", "place_of_use": -999.0, "lpou": True,
                             "process": "SRBA", "acres": 1234.57})

    def test_rows(self):
        f = {"attributes": {"OBJECTID": 4, "NAME": "Test District", "Owner": "A Person", "LPOU": "NO"},
             "geometry": {"rings": [[[-116.5, 43.4], [-116.5, 43.41], [-116.49, 43.41], [-116.5, 43.4]]]}}
        rows = idwr_irrigation_orgs.rows([f, {"attributes": {"OBJECTID": 5, "NAME": " "}, "geometry": f["geometry"]}],
                                         T0)
        self.assertEqual(len(rows), 1)                   # a nameless organization isn't kept
        oid, payload, geom, values = rows[0]
        self.assertEqual((oid, values[1], values[3]), (4, "Test District", False))
        self.assertIn("geom_digest", payload)
        self.assertNotIn("A Person", json.dumps(rows, default=str))

    def test_season(self):
        p = idwr_season_of_use.parse({"SEASON": "4/1 - 10/31", "SPRING": "4/1", "FALL": "10/31", "STARTMONTH": 4,
                                      "STARTDAY": 1, "ENDMONTH": 10, "ENDDAY": 31})
        self.assertEqual((p["start_month"], p["start_day"], p["end_month"], p["end_day"]), (4, 1, 10, 31))
        self.assertIsNone(idwr_season_of_use.parse({"STARTMONTH": 13})["start_month"])

    def test_the_box(self):
        self.assertEqual(idwr.BOX, osm_extract.BOX)


class FakeRun:
    def __init__(self, features, seen_at=T0):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, False
        self.extract_name, self.md5 = "idaho-test.osm.pbf", "0" * 32

    def features(self):
        return iter(self._features)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with water 0001)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def test_consume_versions_in_place(self):
        feats = [feature("w", 9_100_000_001, "linestring", LINE, waterway="canal", name="Test Canal"),
                 feature("w", 9_100_000_001, "polygon", AREA, waterway="riverbank"),
                 feature("w", 9_100_000_002, "polygon", AREA, leisure="swimming_pool"),
                 feature("n", 9_100_000_003, "point", POINT, waterway="weir"),
                 feature("w", 9_100_000_004, "linestring", LINE, waterway="riverbank")]
        stats = osm_waterways.consume(self.conn, FakeRun(feats))
        self.assertEqual((stats["objects"], stats["new"], stats["pools"]), (4, 4, 1))
        rows = self.conn.execute("""select osm_type, osm_id, shape, kind from water.osm_feature
                                    where osm_id between 9100000000 and 9100000099 order by 2, 3""").fetchall()
        self.assertEqual(rows, [("w", 9_100_000_001, "area", "river"), ("w", 9_100_000_001, "line", "canal"),
                                ("w", 9_100_000_002, "area", "pool"), ("n", 9_100_000_003, "point", "weir")])
        mark = self.conn.execute("select reason from ops.build_pending where build = 'water-build' and "
                                 "marked_by = 'osm_waterways'").fetchone()
        self.assertIn("idaho-test.osm.pbf", mark[0])
        stats = osm_waterways.consume(self.conn, FakeRun(feats[:3], seen_at=T0.replace(day=12)))
        self.assertEqual((stats["unchanged"], stats["retired"]), (3, 1))
        self.assertFalse(self.conn.execute("select active from water.osm_feature where osm_id = 9100000003"
                                           ).fetchone()[0])

    def test_idwr_store_replaces_and_refuses_a_shrunken_snapshot(self):
        self.conn.execute("delete from water.idwr_org")
        from ingest import db
        db.ensure_source(self.conn, idwr_irrigation_orgs.SOURCE)
        fid = self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, true) returning id",
                                (idwr_irrigation_orgs.SOURCE["name"], T0)).fetchone()[0]
        ring = {"rings": [[[-116.5, 43.4], [-116.5, 43.41], [-116.49, 43.41], [-116.5, 43.4]]]}
        feats = [{"attributes": {"OBJECTID": i, "NAME": f"District {i}"}, "geometry": ring} for i in range(1, 5)]
        stats = idwr.store(self.conn, idwr_irrigation_orgs.SOURCE["name"], idwr_irrigation_orgs.TABLE,
                           idwr_irrigation_orgs.INSERT, idwr_irrigation_orgs.rows(feats, T0), fid, T0, "test")
        self.assertEqual((stats["features"], stats["versions new"]), (4, 4))
        self.assertEqual(self.conn.execute("select count(*) from water.idwr_org").fetchone()[0], 4)
        with self.assertRaisesRegex(RuntimeError, "not taken as a full snapshot"):
            idwr.store(self.conn, idwr_irrigation_orgs.SOURCE["name"], idwr_irrigation_orgs.TABLE,
                       idwr_irrigation_orgs.INSERT, idwr_irrigation_orgs.rows(feats[:1], T0), fid, T0, "test")


if __name__ == "__main__":
    unittest.main()
