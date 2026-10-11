"""water-build's conflation on synthetic lines, and water-export on its result (plugins/water/ingest/build.py,
export.py). Runs only against a scratch database named by TVT_TEST_DATABASE_URL (PostGIS, with water 0001 and core's
migrations), in one transaction that is rolled back: the build doesn't commit.

The scene is invented, in metres east and north of a corner near Kuna (synthetic.at): an OSM canal with NHD's
named canal 5 m beside it; an NHD lateral leaving the canal that OSM lacks; an NHD desert wash; an 80 m NHD ditch
(too short to draw); an NHD ditch only half along an OSM ditch; an OSM drain HydroShare names; an OSM pond NHD also
maps and an NHD-only pond; an OSM dam with NHD's dam 10 m off; a gauge named for the canal; and IDWR polygons.

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from plugins.water.tests import synthetic as S

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
BASE = 9_300_000_000


def line(*points):
    return json.dumps({"type": "LineString", "coordinates": [list(S.at(*p)) for p in points]})


def square(x, y, size):
    return json.dumps({"type": "Polygon", "coordinates": [[list(p) for p in S.box_square(x, y, size)[0]]]})


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with water 0001)")
class ConflationTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import psycopg
        from plugins.water.ingest import build
        cls.build = build
        cls.conn = psycopg.connect(DB_URL)
        c = cls.conn
        for t in ("water.osm_feature", "water.nhd_flowline", "water.nhd_polygon", "water.nhd_line", "water.nhd_point",
                  "water.nhd_flow", "water.hydroshare_canal", "water.idwr_org", "water.idwr_season"):
            c.execute(f"delete from {t}")
        from ingest import db
        from plugins.water.ingest.sources import nhd_hr, nwps_gauges
        db.ensure_source(c, nhd_hr.SOURCE)
        db.ensure_source(c, nwps_gauges.SOURCE)
        load = c.execute("insert into water.load (source, file, sha256) values ('nhd_hr', 'nhd.gpkg', 'x') "
                         "returning id").fetchone()[0]

        def osm(osm_type, osm_id, shape, kind, geom, name=None, **tags):
            c.execute("""insert into water.osm_feature (osm_type, osm_id, shape, kind, name, tags, geom, first_seen,
                           last_seen) values (%s, %s, %s, %s, %s, %s::jsonb, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                           %s, %s)""", (osm_type, osm_id, shape, kind, name, json.dumps(tags), geom, T0, T0))

        def flowline(pid, geom, cls_, name=None, category=None, order=None):
            c.execute("""insert into water.nhd_flowline (permanent_identifier, gnis_name, class, hydrographiccategory,
                           streamorder, flowdir, visibilityfilter, geom, load_id)
                         values (%s, %s, %s, %s, %s, 1, 24000,
                                 ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                      (pid, name, cls_, category, order, geom, load))

        osm("w", BASE + 1, "line", "canal", line((0, 0), (500, 0), (1000, 0)), waterway="canal")
        flowline("{F-001}", line((0, 5), (1000, 5)), "canal_ditch", "Test Main Canal")
        flowline("{F-002}", line((500, 5), (500, 600)), "canal_ditch", "Test Lateral")
        flowline("{F-003}", line((2000, 0), (2000, 400)), "stream_river", None, "Intermittent", 1)
        flowline("{F-004}", line((3000, 0), (3000, 80)), "canal_ditch")
        flowline("{F-005}", line((0, -500), (800, -500)), "canal_ditch", "Half Ditch")
        osm("w", BASE + 2, "line", "ditch", line((0, -505), (400, -505)), waterway="ditch")
        osm("w", BASE + 3, "line", "drain", line((0, -1000), (500, -1000)), waterway="drain")
        c.execute("""insert into water.hydroshare_canal (id, call_number, name, type, geom, load_id)
                     values (1, 'N1', 'Test Drain', 'Drain', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (line((0, -1003), (500, -1003)), load))
        osm("w", BASE + 4, "area", "pond", square(2000, 1000, 100), natural="water", water="pond")
        for pid, x in (("{W-001}", 2000), ("{W-002}", 3000)):
            c.execute("""insert into water.nhd_polygon (permanent_identifier, layer, ftype, ftype_name,
                           hydrographiccategory, geom, load_id)
                         values (%s, 'waterbody', 390, 'Lake/Pond', 'Perennial',
                                 ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                      (pid, square(x + 2, 1002, 100), load))
        osm("n", BASE + 5, "point", "dam", json.dumps({"type": "Point", "coordinates": list(S.at(100, 0))}),
            name="Test Dam", waterway="dam")
        c.execute("""insert into water.nhd_line (permanent_identifier, gnis_name, ftype, ftype_name, geom, load_id)
                     values ('{L-001}', 'Test Dam', 343, 'Dam/Weir',
                             ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (line((100, 5), (100, 15)), load))
        x, y = S.at(50, 2)
        c.execute("""insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
                     values ('nwps_gauges', 'TSTI1', '\\x00', %s::jsonb, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                             %s, %s)""",
                  (json.dumps({"lid": "TSTI1", "name": "Test Main Canal Diversion at Nowhere"}), x, y, T0, T0))
        c.execute("""insert into water.idwr_org (objectid, name, geom, fetched_at)
                     values (1, 'TEST IRRIGATION DISTRICT', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (square(-100, -100, 1300), T0))
        c.execute("""insert into water.idwr_season (objectid, season, start_month, start_day, end_month, end_day, geom,
                       fetched_at)
                     values (2, '4/1 - 10/31', 4, 1, 10, 31, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (square(-3000, -3000, 9000), T0))
        cls.build_id, cls.counts = build.build(c, out=lambda msg: None)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def reach_on(self, pid):
        return self.q("""select id, kind, name, name_from, round(length_m), minzoom, width_m, intermittent, confirmed
                         from water.reach where geometry_from = 'nhd' and nhd_pid = %s""", pid)

    def test_osm_geometry_carries_nhd_facts(self):
        row = self.q("""select geometry_from, kind, name, name_from, confirmed, nhd_pid, width_m, minzoom, flow_known
                        from water.reach where id = %s""", BASE + 1)
        self.assertEqual(row, [("osm", "canal", "Test Main Canal", "nhd", True, "{F-001}", 5.0, 11, True)])
        self.assertEqual(self.q("select source, role from water.reach_evidence where reach_id = %s order by 1",
                                BASE + 1), [("nhd_hr", "attributes"), ("osm_waterways", "geometry")])

    def test_nhd_only_lateral_and_its_link(self):
        rows = self.reach_on("{F-002}")
        self.assertEqual(len(rows), 1)
        rid, kind, name, name_from, length, minzoom, width, _, confirmed = rows[0]
        self.assertEqual((kind, name, name_from, minzoom, width, confirmed),
                         ("lateral", "Test Lateral", "nhd", 13, 2.5, False))
        # The pieces within 20 m of the canal are matched; the run's start is carried onto the OSM canal.
        self.assertTrue(595 <= length <= 605, length)
        start = self.q("""select round(ST_Distance(ST_Transform(ST_StartPoint(n.geom), 32611),
                                                ST_Transform(o.geom, 32611)))
                          from water.reach n, water.reach o where n.id = %s and o.id = %s""", rid, BASE + 1)
        self.assertEqual(start, [(0,)])
        self.assertGreaterEqual(rid, 2 ** 51)
        link = self.q("select method, round(at_m) from water.reach_link where from_reach = %s and to_reach = %s",
                      BASE + 1, rid)
        self.assertEqual(len(link), 1)
        self.assertEqual(link[0][0], "branch")
        self.assertTrue(490 <= link[0][1] <= 510, link)

    def test_desert_wash_and_short_ditch(self):
        rows = self.reach_on("{F-003}")
        self.assertEqual([(r[1], r[5], r[6], r[7]) for r in rows], [("stream", 13, 0.75, True)])
        self.assertEqual(self.reach_on("{F-004}"), [])              # 80 m: under the 100 m floor

    def test_half_matched_line_passes_nothing_but_its_free_half_draws(self):
        osm_ditch = self.q("select name, nhd_pid, confirmed from water.reach where id = %s", BASE + 2)
        self.assertEqual(osm_ditch, [(None, None, True)])           # agrees with NHD, but F-005 is only half on OSM
        rows = self.reach_on("{F-005}")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:4], ("ditch", "Half Ditch", "nhd"))
        self.assertTrue(370 <= rows[0][4] <= 410, rows[0])

    def test_hydroshare_names_an_unnamed_drain(self):
        self.assertEqual(self.q("select name, name_from, confirmed, kind, width_m from water.reach where id = %s",
                                BASE + 3), [("Test Drain", "hydroshare", False, "drain", 3.0)])
        self.assertEqual(self.q("""select source_id, role from water.reach_evidence
                                   where reach_id = %s and source = 'hydroshare_canals'""", BASE + 3), [("N1", "name")])

    def test_bodies(self):
        self.assertEqual(self.q("select id, kind, geometry_from, confirmed from water.body where osm_id = %s",
                                BASE + 4), [(2 * (BASE + 4), "pond", "osm", True)])
        self.assertEqual(self.q("select geometry_from, kind, minzoom from water.body where nhd_pid is not null"),
                         [("nhd", "pond", 11)])                    # {W-002} only: {W-001} lies under the OSM pond

    def test_structures_dedupe_and_gauges(self):
        self.assertEqual(self.q("select source, name from water.structure where kind = 'dam'"),
                         [("osm_waterways", "Test Dam")])
        gauge = self.q("select method, reach_id, canal_id is not null from water.gauge where lid = 'TSTI1'")
        self.assertEqual(gauge, [("name", BASE + 1, True)])
        canal = self.q("select name, kind, gauge_lid, head_reach_id, head_structure_id is not null from water.canal "
                       "where id = (select canal_id from water.reach where id = %s)", BASE + 1)
        self.assertEqual(canal, [("Test Main Canal", "canal", "TSTI1", BASE + 1, True)])

    def test_idwr_side_tables(self):
        cid = self.q("select canal_id from water.reach where id = %s", BASE + 1)[0][0]
        org = self.q("select name, round(share::numeric, 2), at_head from water.canal_org where canal_id = %s", cid)
        self.assertEqual(org, [("TEST IRRIGATION DISTRICT", 1, True)])
        self.assertEqual(self.q("select season, start_month, end_month from water.canal_season where canal_id = %s",
                                cid), [("4/1 - 10/31", 4, 10)])

    def test_counts_and_ids(self):
        self.assertEqual(self.counts["reaches_osm"], 3)
        self.assertEqual(self.counts["gauges_linked"], 1)
        self.assertEqual(self.q("select count(*) from water.reach where id >= 2 ^ 53"), [(0,)])

    def test_exported_rows_have_no_nulls(self):
        # PostGIS 3.6.4's ST_AsFlatGeobuf shifts the column after a NULL into the NULL's place.
        from plugins.water.ingest import export
        for rows in (export.REACHES_ROWS, export.BODIES_ROWS):
            cur = self.conn.execute(f"select * from ({rows}) q", {"build": self.build_id})
            cols = [c.name for c in cur.description]
            for row in cur.fetchall():
                self.assertNotIn(None, row, dict(zip(cols, row)))

    def test_export(self):
        from basemap.ground import manifest as M
        from plugins.water.ingest import export
        with tempfile.TemporaryDirectory() as archive:
            m, build_id = export.export(self.conn, archive, build="20261011T120000Z", min_features={})
            self.assertEqual(build_id, self.build_id)
            layers = {lay.name: lay for lay in m.layers}
            self.assertEqual({k: v["base"] for k, v in layers.items()}, {"reaches": True, "bodies": True,
                                                                         "mask": False})
            self.assertEqual(layers["reaches"]["fields"]["id"], "long")
            self.assertIn("minzoom", layers["reaches"]["fields"])
            self.assertEqual(layers["reaches"]["features"], self.counts["reaches"])
            for lay in m.layers:
                self.assertEqual((lay["licence"], lay["republish"]), ("ODbL-1.0", "yes"))
                self.assertNotIn("Idaho Department of Water Resources", " ".join(lay["credit"]))
            self.assertIn("hydroshare", m.inputs)                  # its name is on the drain
            self.assertEqual(layers["mask"]["inputs"], ["osm", "nhd"])
            again = M.read(m.folder)                                # the files check against the manifest
            self.assertEqual(again.build, "20261011T120000Z")


if __name__ == "__main__":
    unittest.main()
