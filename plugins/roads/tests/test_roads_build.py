"""The real-width roads build (plugins/roads/ingest/build.py) on a synthetic town, in PostGIS.

Needs TVT_TEST_DATABASE_URL: a test database migrated through roads 0004 (its own: the test deletes the roads
and OpenStreetMap tables' rows inside one transaction and rolls it back). Coordinates are made up: a few streets
laid out in metres east and north of a point in Ada County.

    TVT_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/tvt_test_p7 \
        python3 -m unittest plugins.roads.tests.test_roads_build

The synthetic town (metres):
- Main St (primary, lanes=4) runs west-east along y = 0 from x = -300 to 300. A signal at (0, 0), where 1st St
  (residential) crosses; a right-turn slip lane from (40, 0) to (0, 40) leaves an island at the corner.
- A divided road (two one-way secondary carriageways, x = -160 northbound and x = -140 southbound) crosses Main:
  two nodes 20 m apart, one junction.
- Oak St (residential) meets Main at (150, 0): a T.
- 1st St continues north into a roundabout of radius 20 m centred (0, 350), with legs east, west and north.
- A secondary road on a bridge (layer 1) crosses 1st St at y = -100 without a shared node.
- Crossings on Main: marked at (10, 0) with a crossing way, unmarked at (-80, 0); on 1st St, marked at (0, -12).
- A sidewalk 6 m east of 1st St from y = 60 to 190.
"""

import math
import os
import unittest

from plugins.roads.ingest import build as B

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
LON0, LAT0 = -116.30, 43.60
KX = 1 / (111320 * math.cos(math.radians(LAT0)))
KY = 1 / 111132


def ll(x, y):
    return LON0 + x * KX, LAT0 + y * KY


def line(*pts):
    return "SRID=4326;LINESTRING(" + ", ".join("%.9f %.9f" % ll(x, y) for x, y in pts) + ")"


def point(x, y):
    return "SRID=4326;POINT(%.9f %.9f)" % ll(x, y)


def arc(cx, cy, r, a0, a1, n=6):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def ring_point(deg):
    return (round(20 * math.cos(math.radians(deg)), 9), round(350 + 20 * math.sin(math.radians(deg)), 9))


S, E, N, W = ring_point(-90), ring_point(0), ring_point(90), ring_point(180)


def osm_way(conn, osm_id, highway, pts, tags=None, oneway="no", name=None):
    tags = {"highway": highway, **(tags or {})}
    conn.execute(
        """insert into core.osm_way (osm_id, highway, name, oneway, tags, geom, bridge, layer)
           values (%s, %s, %s, %s, %s, ST_GeomFromEWKT(%s), %s, %s)""",
        (osm_id, highway, name, oneway, __import__("json").dumps(tags), line(*pts),
         tags.get("bridge") == "yes", int(tags.get("layer", 0)) or None))


def osm_street(conn, osm_id, highway, pts, tags=None, oneway="no", name=None):
    tags = {"highway": highway, **(tags or {})}
    conn.execute(
        """insert into roads.osm_street (osm_id, highway, name, oneway, tags, geom)
           values (%s, %s, %s, %s, %s, ST_GeomFromEWKT(%s))""",
        (osm_id, highway, name, oneway, __import__("json").dumps(tags), line(*pts)))


def town(conn):
    """Fill the input tables with the synthetic town (inside the caller's transaction)."""
    for t in ("roads.review", "roads.arrow", "roads.marking", "roads.edge", "roads.surface", "roads.xsection",
              "roads.junction", "roads.piece", "roads.build", "roads.osm_walk_node", "roads.osm_paving",
              "roads.osm_street", "core.osm_lane", "core.osm_way", "core.segment_match", "core.intersection",
              "roads.developed_land", "roads.developed_build"):
        conn.execute(f"delete from {t}")
    conn.execute("delete from core.road_segment")
    conn.execute("delete from obs.taz_demographic")
    conn.execute("delete from core.taz")
    four = {"lanes": "4", "lanes:forward": "2", "lanes:backward": "2", "surface": "asphalt"}
    osm_way(conn, 1001, "primary", [(-300, 0), (-160, 0), (-140, 0), (-80, 0), (0, 0), (10, 0), (40, 0), (150, 0),
                                    (300, 0)], four, name="Main St")
    osm_way(conn, 1002, "secondary", [(-140, 200), (-140, 0), (-140, -200)], {"lanes": "2", "oneway": "yes"},
            "yes", "Eagle Rd")
    osm_way(conn, 1003, "secondary", [(-160, -200), (-160, 0), (-160, 200)], {"lanes": "2", "oneway": "yes"},
            "yes", "Eagle Rd")
    osm_way(conn, 1004, "secondary", [(-200, -100), (-60, -100)], {"lanes": "2"}, name="Hwy")
    osm_way(conn, 1005, "secondary", [(-60, -100), (60, -100)], {"lanes": "2", "bridge": "yes", "layer": "1"},
            name="Hwy")
    osm_way(conn, 1006, "secondary", [(60, -100), (200, -100)], {"lanes": "2"}, name="Hwy")
    osm_way(conn, 1007, "primary_link", [(40, 0), (28, 12), (12, 28), (0, 40)], {"oneway": "yes"}, "yes")
    osm_street(conn, 2001, "residential", [(0, -200), (0, -12), (0, 0), (0, 40), (0, 200)], name="1st St")
    osm_street(conn, 2002, "residential", [(150, 0), (150, 200)], name="Oak St")
    osm_street(conn, 2003, "residential", [(0, 200), S], name="1st St")
    ring = {"junction": "roundabout"}
    osm_street(conn, 2010, "residential", arc(0, 350, 20, -90, 0), ring, "yes")
    osm_street(conn, 2011, "residential", arc(0, 350, 20, 0, 90), ring, "yes")
    osm_street(conn, 2012, "residential", arc(0, 350, 20, 90, 180), ring, "yes")
    osm_street(conn, 2013, "residential", arc(0, 350, 20, 180, 270), ring, "yes")
    osm_street(conn, 2004, "residential", [E, (120, 350)])
    osm_street(conn, 2005, "residential", [W, (-120, 350)])
    osm_street(conn, 2006, "residential", [N, (0, 470)])
    # The paving: a crossing way and a sidewalk; crossing nodes.
    conn.execute(
        """insert into roads.osm_paving (osm_id, kind, highway, footway, material, material_source, width_est_m,
                                         width_source, marked, marked_from, tags, geom)
           values (3001, 'crossing', 'footway', 'crossing', 'asphalt', 'default', 3.0, 'default', true, 'way',
                   '{"highway": "footway", "footway": "crossing"}', ST_GeomFromEWKT(%s)),
                  (3002, 'sidewalk', 'footway', 'sidewalk', 'concrete', 'default', 1.5, 'default', null, null,
                   '{"highway": "footway", "footway": "sidewalk"}', ST_GeomFromEWKT(%s))""",
        (line((10, -12), (10, 0), (10, 12)), line((6, 60), (6, 190))))
    conn.execute(
        """insert into roads.osm_walk_node (osm_id, kind, marked, ways, tags, geom)
           values (5001, 'crossing', true, '{3001}', '{"crossing": "marked"}', ST_GeomFromEWKT(%s)),
                  (5002, 'crossing', false, '{}', '{"crossing": "unmarked"}', ST_GeomFromEWKT(%s)),
                  (5003, 'crossing', true, '{}', '{"crossing": "zebra"}', ST_GeomFromEWKT(%s))""",
        (point(10, 0), point(-80, 0), point(0, -12)))
    conn.execute(
        """insert into core.intersection (name, geom, control, confidence) values
           ('Main St & 1st St', ST_GeomFromEWKT(%s), 'signal', 1)""", (point(0, 0),))
    conn.execute(
        """insert into core.road_segment (name, functional_class, one_way, geom) values
           ('W Main St', 'Minor Arterial', 'both', ST_Multi(ST_GeomFromEWKT(%s)))""", (line((-140, 0), (0, 0)),))
    conn.execute(
        """insert into core.taz (taz_id, county, geom, first_seen, last_seen)
           values (1, 'Ada', ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326)), now(), now())""",
        (*ll(-500, -500), *ll(500, 700)))
    # Developed land over the whole town (the CDL), so the local streets read as curbed.
    conn.execute(
        """insert into roads.developed_build (id, cdl_file, cdl_year, cdl_res_m, cdl_sha256, classes, srid, license,
             credit, republish, pieces, parts, area_km2, made_at, loaded_at, current)
           values ('test', 'cdl_2025_10m.tif', 2025, 10, repeat('0', 64), '{122,123,124}', 5070, 'public domain',
                   'USDA NASS Cropland Data Layer 2025', 'yes', 1, 1, 1, now(), now(), true)""")
    conn.execute(
        """insert into roads.developed_land (id, piece, geom)
           values (1, 1, ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 5070))""",
        (*ll(-500, -500), *ll(500, 700)))


def utm(conn, x, y):
    return conn.execute("select ST_Transform(ST_GeomFromEWKT(%s), 32611)", (point(x, y),)).fetchone()[0]


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a test database migrated through roads 0004")
class BuildTest(unittest.TestCase):
    """One build of the town, checked piece by piece. Everything is rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)
        if not cls.conn.execute("select to_regclass('roads.piece') is not null").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("roads.piece is missing: apply roads 0003")
        town(cls.conn)
        cls.log = []
        cls.stats = B.make(cls.conn, "test", out=cls.log.append)

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def setUp(self):
        self.conn.execute("savepoint each_test")

    def tearDown(self):
        self.conn.execute("rollback to savepoint each_test")

    def q(self, sql, *args):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()

    def at(self, x, y):
        return "ST_Transform(ST_GeomFromEWKT('%s'), 32611)" % point(x, y)

    def test_pieces_split_where_roads_meet_and_not_under_a_bridge(self):
        main = self.q("select seq, round(length_m) from roads.piece where osm_id = 1001 order by seq")
        # Split at the divided road's two nodes, 1st St, the slip lane and Oak St; not at the crossing nodes.
        self.assertEqual(len(main), 6)
        first = self.q("select count(*) from roads.piece where osm_id = 2001")[0][0]
        self.assertEqual(first, 3)      # at Main and at the slip lane; the bridge over it at y = -100 doesn't split it
        self.assertEqual(self.one("select bridge, layer from roads.piece where osm_id = 1005"), (True, 1))
        # The ACHD segment lies along Main between the divided road and 1st St: that piece, and only it.
        self.assertEqual(self.q("select seq from roads.piece where osm_id = 1001 and road_segment_id is not null"),
                         [(3,)])
        self.assertTrue(self.one("select seg_same_way from roads.piece where osm_id = 1001 and seq = 3")[0])

    def test_the_divided_roads_crossing_is_one_junction(self):
        j = self.one(f"""select kind, nodes from roads.junction
                         where ST_DWithin(geom, {self.at(-150, 0)}, 3)""")
        self.assertEqual(j, ("plain", 2))
        n = self.one(f"""select count(*) from roads.junction where ST_DWithin(geom, {self.at(-150, 0)}, 30)""")[0]
        self.assertEqual(n, 1)
        # Its corners are filled, but the median between the carriageways stays open beside the junction.
        paved = lambda x, y: self.one(f"select bool_or(ST_Intersects(geom, {self.at(x, y)})) from roads.surface "  # noqa
                                      "where kind in ('carriageway', 'junction')")[0]
        self.assertTrue(paved(-167.5, 9.5))         # the north-west corner
        self.assertFalse(paved(-150, 20))
        self.assertFalse(paved(-150, -20))

    def test_the_signal(self):
        kind, iid = self.one(f"select kind, intersection_id from roads.junction where ST_DWithin(geom, {self.at(0, 0)}, 2)")
        self.assertEqual(kind, "signal")
        self.assertIsNotNone(iid)
        bars = self.q("select piece_id, ST_Length(geom) from roads.marking where kind = 'stop_bar'")
        self.assertEqual(len(bars), 2)                              # Main's two approaches; 1st St has no lines
        for _, length in bars:
            self.assertAlmostEqual(length, 2 * 3.66, delta=0.3)    # across two lanes
        # Each stop bar is before the junction, on its own side of the centreline.
        for (d,) in self.q(f"select ST_Distance(geom, {self.at(0, 0)}) from roads.marking where kind = 'stop_bar'"):
            self.assertGreater(d, 5)

    def test_curb_returns_fill_the_corners(self):
        fill = self.one(f"""select sum(ST_Area(s.geom)) from roads.surface s join roads.junction j on j.id = s.junction_id
                            where s.kind = 'junction' and ST_DWithin(j.geom, {self.at(150, 0)}, 2)""")[0]
        self.assertGreater(fill, 5)                                # Oak St's two corners
        # The corner itself is paved now: just off both carriageways' edges.
        covered = self.one(f"""select bool_or(ST_Intersects(geom, {self.at(156.5, 9.5)})) from roads.surface""")[0]
        self.assertTrue(covered)

    def test_roundabouts_centre_stays_an_island(self):
        j = self.one(f"select kind, nodes from roads.junction where ST_DWithin(geom, {self.at(0, 350)}, 5)")
        self.assertEqual(j, ("roundabout", 4))
        paved = self.one(f"""select bool_or(ST_Intersects(geom, {self.at(0, 350)})) from roads.surface
                             where kind in ('carriageway', 'junction')""")[0]
        self.assertFalse(paved)
        island = self.one(f"select count(*) from roads.surface where kind = 'island' and ST_Intersects(geom, {self.at(0, 350)})")
        self.assertEqual(island[0], 1)

    def test_the_slip_lanes_island(self):
        island = self.one(f"""select count(*) from roads.surface where kind = 'island'
                              and ST_Intersects(geom, {self.at(14, 14)})""")[0]
        paved = self.one(f"""select bool_or(ST_Intersects(geom, {self.at(14, 14)})) from roads.surface
                             where kind in ('carriageway', 'junction')""")[0]
        self.assertEqual((island, paved), (1, False))

    def test_the_bridge_is_a_deck(self):
        deck = self.q("select s.layer from roads.surface s join roads.piece p on p.id = s.piece_id "
                      "where p.osm_id = 1005 and s.kind = 'deck'")
        self.assertEqual(deck, [(1,)])
        # 1st St's surface runs on under it, unbroken.
        under = self.one(f"""select count(*) from roads.surface s join roads.piece p on p.id = s.piece_id
                             where p.osm_id = 2001 and ST_Intersects(s.geom, {self.at(0, -100)})""")[0]
        self.assertEqual(under, 1)
        # The deck's sides are edges over 1st St.
        sides = self.one(f"""select count(*) from roads.edge where kind = 'deck'
                             and ST_DWithin(geom, {self.at(0, -100)}, 6)""")[0]
        self.assertGreaterEqual(sides, 1)

    def test_crosswalks_only_where_marked(self):
        walks = self.q("select node_osm_id, ST_Area(geom) from roads.marking where kind = 'crosswalk' order by 1")
        self.assertEqual([w[0] for w in walks], [5001, 5003])
        main = self.one("select ST_Area(geom) from roads.marking where node_osm_id = 5001")[0]
        # Across Main's pavement (about 15.8 m) and 3 m deep.
        self.assertAlmostEqual(main, 3.0 * 15.84, delta=6)

    def test_lines_stop_short_of_crosswalks_and_junctions(self):
        near = self.one("""select count(*) from roads.marking l, roads.marking c
                           where l.kind in ('lane', 'centre_double', 'edge', 'bike', 'twltl') and c.kind = 'crosswalk'
                             and ST_DWithin(l.geom, c.geom, 0.99)""")[0]
        self.assertEqual(near, 0)
        inside = self.one(f"""select count(*) from roads.marking where kind in ('lane', 'centre_double')
                              and ST_DWithin(geom, {self.at(0, 0)}, 6)""")[0]
        self.assertEqual(inside, 0)
        kinds = dict(self.q("select kind, count(*) from roads.marking group by 1"))
        self.assertGreater(kinds.get("lane", 0), 0)
        self.assertGreater(kinds.get("centre_double", 0), 0)
        # The residential streets carry none.
        res = self.one("""select count(*) from roads.marking m join roads.piece p on p.id = m.piece_id
                          where p.highway = 'residential' and m.kind <> 'crosswalk'""")[0]
        self.assertEqual(res, 0)

    def test_no_edge_runs_inside_a_carriageway(self):
        # Main's centreline, away from junctions, has no edge within 3 m.
        bad = self.one(f"""select count(*) from roads.edge
                           where ST_DWithin(geom, ST_MakeLine({self.at(-120, 0)}, {self.at(-90, 0)}), 3)""")[0]
        self.assertEqual(bad, 0)
        # And Main's curb runs along both sides there.
        sides = self.one(f"""select count(*) from roads.edge
                             where ST_DWithin(geom, {self.at(-100, 8)}, 1.5) or ST_DWithin(geom, {self.at(-100, -8)}, 1.5)""")[0]
        self.assertGreaterEqual(sides, 2)

    def test_the_sidewalk_caps_1st_st(self):
        flags, right = self.one(f"""select x.flags, x.width_right_m from roads.xsection x join roads.piece p
                                    on p.id = x.piece_id where p.osm_id = 2001
                                    and ST_DWithin(p.geom, {self.at(0, 120)}, 1)""")
        self.assertIn("sidewalk_cap", flags)
        self.assertAlmostEqual(right, 5.0, delta=0.3)

    def test_the_build_row_and_review(self):
        bid, current, inputs = self.one("select id, current, inputs from roads.build")
        self.assertTrue(current)
        self.assertIn("osm", [i["name"] for i in inputs])
        self.assertIn("cdl", [i["name"] for i in inputs])
        self.assertEqual(self.stats["build"], bid)
        # Every surface is valid, and z15's copies exist for the big ones.
        bad = self.one("select count(*) from roads.surface where not ST_IsValid(geom)")[0]
        self.assertEqual(bad, 0)
        self.assertGreater(self.one("select count(*) from roads.surface where geom_z15 is not null")[0], 0)


if __name__ == "__main__":
    unittest.main()
