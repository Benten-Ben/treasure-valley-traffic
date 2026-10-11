"""water-build's conflation on synthetic lines, and water-export on its result (plugins/water/ingest/build.py,
export.py). Runs only against a scratch database named by TVT_TEST_DATABASE_URL (PostGIS, with water 0001 and core's
migrations), in one transaction that is rolled back: the build doesn't commit.

The scene is invented, in metres east and north of a corner near Kuna (synthetic.at): an OSM canal with NHD's
named canal 5 m beside it; an NHD lateral leaving the canal that OSM lacks; an NHD desert wash; an 80 m NHD ditch
(too short to draw); an NHD ditch only half along an OSM ditch; an OSM drain HydroShare names; an OSM pond NHD also
maps and an NHD-only pond; an OSM dam with NHD's dam 10 m off; a gauge named for the canal; and IDWR polygons, one
of them a bow tie as served. Added in review: OSM ways that leave and join a canal 10 m from its ends; an unnamed
OSM canal and an OSM stream along HydroShare's placeholders ('Unnamed Supply', 'Unnamed Drain'); an OSM dam drawn
as a long area with NHD's dam line at one end (its middle far from NHD's), and an OSM weir beside NHD's named dam.

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


def polygon(*points):
    return json.dumps({"type": "Polygon", "coordinates": [[list(S.at(*p)) for p in points]]})


def point(x, y):
    return json.dumps({"type": "Point", "coordinates": list(S.at(x, y))})


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
        for hid, call, name, kind, y in ((1, "N1", "Test Drain", "Drain", -1003),
                                         (2, "N2", "Unnamed Supply", "Field Supply", -3003),
                                         (3, "N3", "Unnamed Drain", "Drain", -3503)):
            c.execute("""insert into water.hydroshare_canal (id, call_number, name, type, geom, load_id)
                         values (%s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                      (hid, call, name, kind, line((0, y), (500, y)), load))
        # OSM splits canals at culverts and roads: a lateral leaves 10 m before the canal's end, a drain joins 10 m
        # after its start, each on a node of the canal's way.
        osm("w", BASE + 6, "line", "canal", line((0, -2000), (10, -2000), (990, -2000), (1000, -2000)),
            waterway="canal")
        osm("w", BASE + 7, "line", "canal", line((990, -2000), (990, -1700)), waterway="canal")
        osm("w", BASE + 8, "line", "drain", line((10, -2300), (10, -2000)), waterway="drain")
        # Unnamed in OSM, and HydroShare's line beside each has a placeholder for a name.
        osm("w", BASE + 9, "line", "canal", line((0, -3000), (500, -3000)), waterway="canal")
        osm("w", BASE + 10, "line", "stream", line((0, -3500), (500, -3500)), waterway="stream")
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
        # A dam OSM draws as a long area, NHD's line at its west end (Barber Dam: 208 m between their middles, 1 m
        # between the shapes); an unnamed OSM weir 10 m from NHD's named Dam/Weir line.
        osm("w", BASE + 11, "area", "dam", polygon((4000, -10), (4300, -10), (4300, 0), (4000, 0), (4000, -10)),
            name="Test River Dam", waterway="dam")
        osm("n", BASE + 12, "point", "weir", point(5000, 0), waterway="weir")
        for pid, name, geom in (("{L-002}", "Test River Dam", line((4000, 2), (4040, 2))),
                                ("{L-003}", "Test Check Dam", line((5000, 10), (5000, 20)))):
            c.execute("""insert into water.nhd_line (permanent_identifier, gnis_name, ftype, ftype_name, geom, load_id)
                         values (%s, %s, 343, 'Dam/Weir', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                      (pid, name, geom, load))
        x, y = S.at(50, 2)
        c.execute("""insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen)
                     values ('nwps_gauges', 'TSTI1', '\\x00', %s::jsonb, ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                             %s, %s)""",
                  (json.dumps({"lid": "TSTI1", "name": "Test Main Canal Diversion at Nowhere"}), x, y, T0, T0))
        c.execute("""insert into water.idwr_org (objectid, name, geom, fetched_at)
                     values (1, 'TEST IRRIGATION DISTRICT', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (square(-100, -100, 1300), T0))
        # As IDWR serves some: a ring crossing itself (a bow tie whose waist is on the canal at x 500), stored as is.
        c.execute("""insert into water.idwr_org (objectid, name, geom, fetched_at)
                     values (3, 'TEST BOWTIE DISTRICT', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s)""",
                  (polygon((400, -50), (600, 50), (600, -50), (400, 50), (400, -50)), T0))
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

    def test_hydroshare_placeholders_are_no_name(self):
        # 'Unnamed Supply' on a field supply: no name, so an unnamed ditch (1.5 m, z13), not a named canal (5 m, z11).
        self.assertEqual(self.q("select name, name_from, kind, width_m, minzoom, canal_id from water.reach "
                                "where id = %s", BASE + 9), [(None, None, "ditch", 1.5, 13, None)])
        # 'Unnamed Drain' doesn't turn an OSM stream into a drain.
        self.assertEqual(self.q("select name, kind from water.reach where id = %s", BASE + 10), [(None, "stream")])
        self.assertEqual(self.q("""select reach_id, role from water.reach_evidence
                                   where source = 'hydroshare_canals' and reach_id in (%s, %s) order by 1""",
                                BASE + 9, BASE + 10), [(BASE + 9, "agrees"), (BASE + 10, "agrees")])
        self.assertEqual(self.q("select count(*) from water.reach where name ~* 'unnamed|supply'"), [(0,)])
        self.assertEqual(self.q("select count(*) from water.canal where name ~* 'unnamed|supply'"), [(0,)])
        self.assertEqual((self.counts["named_by_hydroshare"], self.counts["kinds_from_hydroshare"]), (1, 1))

    def test_osm_ways_meeting_near_a_ways_end(self):
        self.assertEqual(self.q("select method, round(at_m) from water.reach_link "
                                "where from_reach = %s and to_reach = %s", BASE + 6, BASE + 7), [("branch", 990)])
        self.assertEqual(self.q("select method from water.reach_link where from_reach = %s and to_reach = %s",
                                BASE + 8, BASE + 6), [("joins",)])

    def test_bodies(self):
        self.assertEqual(self.q("select id, kind, geometry_from, confirmed from water.body where osm_id = %s",
                                BASE + 4), [(2 * (BASE + 4), "pond", "osm", True)])
        self.assertEqual(self.q("select geometry_from, kind, minzoom from water.body where nhd_pid is not null"),
                         [("nhd", "pond", 11)])                    # {W-002} only: {W-001} lies under the OSM pond

    def test_structures_dedupe_and_gauges(self):
        # NHD's dams are OSM's: by their shapes (the area dam's middle is 130 m from NHD's), a dam and a weir alike;
        # the unnamed weir takes NHD's name.
        self.assertEqual(self.q("select source, kind, name from water.structure where kind in ('dam', 'weir') "
                                "order by name"),
                         [("osm_waterways", "weir", "Test Check Dam"), ("osm_waterways", "dam", "Test Dam"),
                          ("osm_waterways", "dam", "Test River Dam")])
        self.assertEqual(self.q("select count(*) from water.structure where source = 'nhd_hr'"), [(0,)])
        gauge = self.q("select method, reach_id, canal_id is not null from water.gauge where lid = 'TSTI1'")
        self.assertEqual(gauge, [("name", BASE + 1, True)])
        canal = self.q("select name, kind, gauge_lid, head_reach_id, head_structure_id is not null from water.canal "
                       "where id = (select canal_id from water.reach where id = %s)", BASE + 1)
        self.assertEqual(canal, [("Test Main Canal", "canal", "TSTI1", BASE + 1, True)])

    def test_idwr_side_tables(self):
        cid = self.q("select canal_id from water.reach where id = %s", BASE + 1)[0][0]
        org = self.q("select name, round(share::numeric, 2)::float8, at_head from water.canal_org where canal_id = %s "
                     "order by name", cid)
        # The bow tie, made valid: two triangles meeting on the canal, 200 m of its 1,000.
        self.assertEqual(org, [("TEST BOWTIE DISTRICT", 0.2, False), ("TEST IRRIGATION DISTRICT", 1, True)])
        self.assertEqual(self.q("select season, start_month, end_month from water.canal_season where canal_id = %s",
                                cid), [("4/1 - 10/31", 4, 10)])

    def test_counts_and_ids(self):
        self.assertEqual(self.counts["reaches_osm"], 8)
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
            # ... whose width (3 m, a drain) the mask buffers it to: HydroShare is the mask's input too.
            self.assertEqual(layers["mask"]["inputs"], ["osm", "nhd", "hydroshare"])
            self.assertEqual(layers["bodies"]["inputs"], ["osm", "nhd"])
            again = M.read(m.folder)                                # the files check against the manifest
            self.assertEqual(again.build, "20261011T120000Z")


class ExportInputsTest(unittest.TestCase):
    def test_the_hash_beside_the_url_is_the_downloads(self):
        from plugins.water.ingest import export
        entries = {e["name"]: e for e in export.input_entries({
            "nhd_hr": {"file": "nhd.gpkg", "sha256": "a" * 64, "download": "NHD_H_1705_HU4_GDB.zip",
                       "download_sha256": "b" * 64},
            "hydroshare_canals": {"file": "hydroshare.gpkg", "sha256": "c" * 64}})}
        self.assertEqual(entries["nhd"]["sha256"], "b" * 64)
        self.assertIn("nhd.gpkg (sha256 " + "a" * 64 + ")", entries["nhd"]["note"])
        self.assertIn("NHD_H_1705_HU4_GDB.zip", entries["nhd"]["note"])
        self.assertNotIn("sha256", entries["hydroshare"])         # no download hash recorded: none given
        self.assertNotIn("sha256", entries["osm"])


if __name__ == "__main__":
    unittest.main()
