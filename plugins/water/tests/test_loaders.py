"""The water loaders on synthetic files: the GeoPackage reader (gpkg.py), nhd-load (nhd.py) and hydroshare-load
(hydroshare.py). Standard library; the database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (with water 0001 applied), each inside a transaction that is rolled back.

Run: python3 -m unittest discover -s plugins -t .
"""

import os
import struct
import tempfile
import unittest

from plugins.water.ingest import gpkg, hydroshare, nhd
from plugins.water.tests import synthetic as S

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


def sample_nhd(path):
    S.nhd(path,
          flowlines=[S.flowline("{A-001}", [(0, 0), (1000, 0)], name="Test Main Canal"),
                     S.flowline("{A-002}", [(1000, 0), (1000, 800)], cls="stream_river", category="Intermittent",
                                order=2, ftype=460)],
          polygons=[{"layer": "waterbody", "permanent_identifier": "{W-001}", "gnis_name": "Test Pond",
                     "ftype": 390, "fcode": 39004, "ftype_name": "Lake/Pond", "hydrographiccategory": "Perennial",
                     "areasqkm": 0.01, "geom": S.gp(S.wkb_multipolygon([S.box_square(200, 200, 100)]))},
                    {"layer": "area", "permanent_identifier": "{R-001}", "ftype": 460, "fcode": 46006,
                     "ftype_name": "Stream/River", "geom": S.gp(S.wkb_multipolygon([S.box_square(2000, 0, 300)]))}],
          lines=[{"permanent_identifier": "{L-001}", "gnis_name": "Test Dam", "ftype": 343, "fcode": 34300,
                  "ftype_name": "Dam/Weir", "geom": S.gp(S.wkb_multilinestring([[S.at(500, -20), S.at(500, 20)]]))}],
          points=[{"permanent_identifier": "{P-001}", "ftype": 458, "fcode": 45800, "ftype_name": "Spring/Seep",
                   "geom": S.gp(S.wkb_point(S.at(300, 900)), envelope=None)}],
          events=[{"permanent_identifier": "{E-001}", "eventtype": 57001, "source_featureid": "13000000",
                   "geom": S.gp(S.wkb_point(S.at(100, 0)), big_endian=True)}],
          flow=[("{A-001}", "{A-002}")])


class GpkgTest(unittest.TestCase):
    def test_header_forms(self):
        wkb = S.wkb_point((1.0, 2.0))
        self.assertEqual(gpkg.wkb(S.gp(wkb)), wkb)
        self.assertEqual(gpkg.wkb(S.gp(wkb, envelope=(1, 1, 2, 2))), wkb)
        self.assertEqual(gpkg.wkb(S.gp(wkb, big_endian=True, envelope=(1, 1, 2, 2))), wkb)
        self.assertEqual(gpkg.srs_id(S.gp(wkb, srs=4326, big_endian=True)), 4326)
        self.assertEqual(gpkg.srs_id(S.gp(wkb, srs=4269)), 4269)
        self.assertIsNone(gpkg.wkb(S.gp(b"", empty=True)))
        self.assertIsNone(gpkg.wkb(None))

    def test_refuses_what_it_cant_read(self):
        wkb = S.wkb_point((1.0, 2.0))
        with self.assertRaises(gpkg.GpkgError):
            gpkg.wkb(b"XY" + bytes(6) + wkb)                       # no magic
        blob = bytearray(S.gp(wkb))
        blob[3] |= 0x20                                            # extended geometry type
        with self.assertRaises(gpkg.GpkgError):
            gpkg.wkb(bytes(blob))
        blob = bytearray(S.gp(wkb))
        blob[3] = (blob[3] & 0xF1) | (7 << 1)                      # envelope code 7
        with self.assertRaises(gpkg.GpkgError):
            gpkg.wkb(bytes(blob))
        with self.assertRaises(gpkg.GpkgError):
            gpkg.wkb(S.gp(b"\x07\x01"))                            # WKB cut short / no byte order

    def test_tables_and_rows(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nhd.gpkg")
            sample_nhd(path)
            with gpkg.open_ro(path) as g:
                self.assertEqual(gpkg.tables(g)["flow"], "attributes")
                self.assertEqual(gpkg.feature_tables(g)["flowline"], ("geom", "MULTILINESTRING", 4269))
                rows = list(gpkg.rows(g, "flowline", ["permanent_identifier", "geom"]))
                self.assertEqual([r["permanent_identifier"] for r in rows], ["{A-001}", "{A-002}"])
                self.assertEqual(struct.unpack("<BI", rows[0]["geom"][:5]), (1, 5))     # little-endian MultiLineString
                event = next(gpkg.rows(g, "point_event"))
                self.assertEqual(struct.unpack("<BI", event["geom"][:5]), (1, 1))     # big-endian header, WKB kept
                with self.assertRaises(gpkg.GpkgError):
                    list(gpkg.rows(g, "flowline", ["no_such_column"]))
                with self.assertRaises(gpkg.GpkgError):
                    list(gpkg.rows(g, "flowline; drop table flow", None))
            self.assertTrue(os.path.exists(path))

    def test_not_a_geopackage(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.gpkg")
            with open(path, "wb") as f:
                f.write(b"not sqlite at all" * 100)
            with self.assertRaises(gpkg.GpkgError):
                with gpkg.open_ro(path):
                    pass
            with self.assertRaises(gpkg.GpkgError):
                with gpkg.open_ro(os.path.join(d, "missing.gpkg")):
                    pass


class NhdReadTest(unittest.TestCase):
    def test_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nhd.gpkg")
            sample_nhd(path)
            data, skipped = nhd.read(path)
        self.assertEqual({k: len(v) for k, v in data.items()},
                         {"flowline": 2, "waterbody": 1, "area": 1, "line": 1, "point": 1, "point_event": 1,
                          "flow": 1})
        row = dict(zip(nhd.FLOWLINE, data["flowline"][1][:-1]))
        self.assertEqual((row["class"], row["hydrographiccategory"], row["streamorder"]),
                         ("stream_river", "Intermittent", 2))
        event = dict(zip(nhd.POINT, data["point_event"][0][:-1]))
        self.assertEqual((event["eventtype"], event["source_featureid"], event["gnis_name"]), (57001, "13000000", None))
        self.assertEqual(sum(skipped.values()), 0)

    def test_refuses_another_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "other.gpkg")
            g = S.Gpkg(path)
            g.table("flowline", S.FLOWLINE_COLUMNS, "geom", "MULTILINESTRING")
            g.close()
            with self.assertRaisesRegex(nhd.LoadError, "no area, flow, waterbody"):
                nhd.read(path)

    def test_refuses_unknown_classes(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nhd.gpkg")
            S.nhd(path, flowlines=[S.flowline("{X-001}", [(0, 0), (10, 0)], cls="coastline")])
            with self.assertRaisesRegex(nhd.LoadError, "unknown class"):
                nhd.read(path)


class HydroshareReadTest(unittest.TestCase):
    def test_read(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "hs.gpkg")
            S.hydroshare(path, [(0, "N1", "11.5 Lateral", "Lateral", [(0, 0), (100, 0)]),
                                (1, "N2", None, "Field Supply", [(0, 10), (100, 10)])])
            rows = hydroshare.read(path)
        self.assertEqual([r[:4] for r in rows], [(0, "N1", "11.5 Lateral", "Lateral"), (1, "N2", None, "Field Supply")])

    def test_refuses_repeated_ids(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "hs.gpkg")
            S.hydroshare(path, [(3, "N1", "A", "Canal", [(0, 0), (1, 0)]), (3, "N2", "B", "Canal", [(0, 1), (1, 1)])])
            with self.assertRaisesRegex(nhd.LoadError, "twice"):
                hydroshare.read(path)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with water 0001)")
class LoadDatabaseTest(unittest.TestCase):
    """nhd-load and hydroshare-load commit through db.Fetch, so these run on a database of their own: each test
    clears what it wrote."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        self.tmp = tempfile.TemporaryDirectory()
        self.clean()

    def tearDown(self):
        self.clean()
        self.conn.close()
        self.tmp.cleanup()

    def clean(self):
        self.conn.rollback()
        for t in ("water.nhd_flow", "water.nhd_point", "water.nhd_line", "water.nhd_polygon", "water.nhd_flowline",
                  "water.hydroshare_canal", "water.load"):
            self.conn.execute(f"delete from {t}")
        self.conn.execute("delete from ops.build_pending where build = 'water-build'")
        self.conn.commit()

    def test_nhd_load_replace_and_skip(self):
        path = os.path.join(self.tmp.name, "nhd.gpkg")
        sample_nhd(path)
        stats = nhd.load(self.conn, path)
        self.assertEqual((stats["flowlines"], stats["polygons"], stats["lines"], stats["points"], stats["flow"]),
                         (2, 2, 1, 2, 1))
        geom = self.conn.execute("""select ST_SRID(geom), GeometryType(geom), ST_NDims(geom), class, fdate
                                    from water.nhd_flowline where permanent_identifier = '{A-001}'""").fetchone()
        self.assertEqual(geom[:4], (4326, "MULTILINESTRING", 2, "canal_ditch"))
        self.assertEqual(geom[4].year, 2015)
        self.assertEqual(self.conn.execute("""select layer, ftype_name from water.nhd_point
                                              order by permanent_identifier""").fetchall(),
                         [("event", None), ("point", "Spring/Seep")])
        self.assertEqual(nhd.load(self.conn, path)["loaded"], "nothing")             # same file: skipped
        mark = self.conn.execute("select marked_by from ops.build_pending where build = 'water-build'").fetchall()
        self.assertEqual(mark, [("nhd_hr",)])
        S.nhd(path, flowlines=[S.flowline("{B-001}", [(0, 0), (10, 0)])])            # a new file replaces the old
        stats = nhd.load(self.conn, path)
        self.assertEqual((stats["flowlines"], stats["polygons"], stats["flow"]), (1, 0, 0))
        self.assertEqual(self.conn.execute("select count(*) from water.load where source = 'nhd_hr'").fetchone()[0], 2)

    def test_hydroshare_load(self):
        path = os.path.join(self.tmp.name, "hs.gpkg")
        S.hydroshare(path, [(0, "N1", "11.5 Lateral", "Lateral", [(0, 0), (100, 0)])])
        self.assertEqual(hydroshare.load(self.conn, path)["canals"], 1)
        self.assertEqual(self.conn.execute("select name, ST_SRID(geom) from water.hydroshare_canal").fetchall(),
                         [("11.5 Lateral", 4326)])
        self.assertEqual(hydroshare.load(self.conn, path)["loaded"], "nothing")
        self.assertEqual(hydroshare.load(self.conn, path, force=True)["canals"], 1)


if __name__ == "__main__":
    unittest.main()
