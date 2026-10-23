"""The real-width roads build (plugins/roads/ingest/build.py) on a synthetic town, in PostGIS.

Needs TVT_TEST_DATABASE_URL: a test database migrated through roads 0004 (its own: the test deletes the roads,
OpenStreetMap and intersections tables' rows inside one transaction and rolls it back). Coordinates are made up: a few streets
laid out in metres east and north of a point in Ada County.

    TVT_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/tvt_test_p7 \
        python3 -m unittest plugins.roads.tests.test_roads_build

The synthetic town (metres):
- Main St (primary, lanes=4) runs west-east along y = 0 from x = -300 to 220, then with 6 lanes to 300. A signal at (0, 0), where 1st St
  (residential) crosses; a right-turn slip lane from (40, 0) to (0, 40) leaves an island at the corner.
- A divided road (two one-way secondary carriageways, x = -160 northbound and x = -140 southbound) crosses Main:
  two nodes 20 m apart, one junction.
- Oak St (residential) meets Main at (150, 0): a T.
- 1st St continues north into a roundabout of radius 20 m centred (0, 350), with legs east, west and north.
- A secondary road on a bridge (layer 1) crosses 1st St at y = -100 without a shared node.
- Crossings on Main: marked at (10, 0) with a crossing way, unmarked at (-80, 0); on 1st St, marked at (0, -12).
- A sidewalk 5 m east of 1st St from y = 60 to 190.
- An alley 13 m south of Main from x = -120 to -30, beside ACHD's W Main St (a minor arterial): the line rule alone
  would put it on it.
- ACHD's segment along the highway's east piece is elevated (level 20) where OpenStreetMap draws no bridge.
- The town is developed land up to x = 400. Out in the fields, Farm Rd (unclassified, x = 470, y = -400 to 600)
  crosses Dixie Rd (unclassified, y = 450, x = 420 to 560) at (470, 450): the CDL's developed land covers only their
  own 20 m, as it does a farm road's cells.
"""

import contextlib
import io
import math
import os
import tempfile
import unittest
from unittest import mock

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
        """insert into roads.osm_street (osm_id, highway, service, name, oneway, tags, geom)
           values (%s, %s, %s, %s, %s, %s, ST_GeomFromEWKT(%s))""",
        (osm_id, highway, tags.get("service") if highway == "service" else None, name, oneway,
         __import__("json").dumps(tags), line(*pts)))


def town(conn):
    """Fill the input tables with the synthetic town (inside the caller's transaction)."""
    # The rows that point at intersections and segments go first, so a seeded copy works too.
    for t in ("roads.review", "roads.arrow", "roads.marking", "roads.edge", "roads.surface", "roads.xsection",
              "roads.junction", "roads.piece", "roads.build", "roads.osm_walk_node", "roads.osm_paving",
              "roads.osm_parking", "roads.osm_street", "core.osm_lane", "core.osm_way", "core.segment_match", "roads.bike_facility_match",
              "core.approach", "core.signal_device", "core.rail_crossing", "core.intersection",
              "roads.developed_land", "roads.developed_build"):
        conn.execute(f"delete from {t}")
    conn.execute("delete from core.road_segment")
    conn.execute("delete from obs.taz_demographic")
    conn.execute("delete from core.taz")
    four = {"lanes": "4", "lanes:forward": "2", "lanes:backward": "2", "surface": "asphalt"}
    osm_way(conn, 1001, "primary", [(-300, 0), (-160, 0), (-140, 0), (-80, 0), (0, 0), (10, 0), (40, 0), (150, 0),
                                    (220, 0)], four, name="Main St")
    six = {"lanes": "6", "lanes:forward": "3", "lanes:backward": "3", "surface": "asphalt"}
    osm_way(conn, 1008, "primary", [(220, 0), (300, 0)], six, name="Main St")
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
    osm_street(conn, 2020, "service", [(-120, -13), (-30, -13)], {"service": "alley"})
    osm_street(conn, 2030, "unclassified", [(470, -400), (470, 450), (470, 600)], name="Farm Rd")
    osm_street(conn, 2031, "unclassified", [(420, 450), (470, 450), (560, 450)], name="Dixie Rd")
    # The paving: a crossing way and a sidewalk; crossing nodes.
    conn.execute(
        """insert into roads.osm_paving (osm_id, kind, highway, footway, material, material_source, width_est_m,
                                         width_source, marked, marked_from, tags, geom)
           values (3001, 'crossing', 'footway', 'crossing', 'asphalt', 'default', 3.0, 'default', true, 'way',
                   '{"highway": "footway", "footway": "crossing"}', ST_GeomFromEWKT(%s)),
                  (3002, 'sidewalk', 'footway', 'sidewalk', 'concrete', 'default', 1.5, 'default', null, null,
                   '{"highway": "footway", "footway": "sidewalk"}', ST_GeomFromEWKT(%s))""",
        (line((10, -12), (10, 0), (10, 12)), line((5, 60), (5, 190))))
    # An inactive way, and one with no layer; lots and stalls (one a multipolygon relation, one with no parking tag).
    conn.execute(
        """insert into roads.osm_paving (osm_id, kind, highway, material, material_source, width_est_m, width_source,
                                         layer, active, tags, geom)
           values (3003, 'driveway', 'service', 'asphalt', 'default', 4.0, 'default', null, true,
                   '{"highway": "service"}', ST_GeomFromEWKT(%s)),
                  (3004, 'service', 'service', 'gravel', 'surface', 3.0, 'default', 1, false,
                   '{"highway": "service"}', ST_GeomFromEWKT(%s))""",
        (line((100, 30), (100, 60)), line((200, 30), (200, 60))))
    for osm_type, osm_id, kind, parking, layer, active, x in (
            ("w", 4001, "lot", "surface", None, True, 60), ("r", 4001, "lot", None, 1, True, 100),
            ("w", 4002, "lot", "surface", None, False, 140), ("w", 4003, "space", None, None, True, 180)):
        conn.execute(
            """insert into roads.osm_parking (osm_type, osm_id, kind, parking, material, material_source, layer,
                                              area_m2, active, tags, geom)
               values (%s, %s, %s, %s, 'asphalt', 'default', %s, 100, %s, '{"amenity": "parking"}',
                       ST_Multi(ST_GeomFromEWKT(%s)))""",
            (osm_type, osm_id, kind, parking, layer, active,
             "SRID=4326;POLYGON((" + ", ".join("%.9f %.9f" % ll(x + dx, 30 + dy)
                                               for dx, dy in ((0, 0), (10, 0), (10, 10), (0, 10), (0, 0))) + "))"))
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
        """insert into core.road_segment (name, functional_class, one_way, from_level, to_level, geom) values
           ('Hwy', 'Minor Arterial', 'both', 20, 20, ST_Multi(ST_GeomFromEWKT(%s)))""", (line((60, -100), (200, -100)),))
    conn.execute(
        """insert into core.taz (taz_id, county, geom, first_seen, last_seen)
           values (1, 'Ada', ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 4326)), now(), now())""",
        (*ll(-500, -500), *ll(600, 700)))
    # Developed land over the town (the CDL), so its local streets read as curbed; out in the fields only the farm
    # roads' own cells.
    conn.execute(
        """insert into roads.developed_build (id, cdl_file, cdl_year, cdl_res_m, cdl_sha256, classes, srid, license,
             credit, republish, pieces, parts, area_km2, made_at, loaded_at, current)
           values ('test', 'cdl_2025_10m.tif', 2025, 10, repeat('0', 64), '{122,123,124}', 5070, 'public domain',
                   'USDA NASS Cropland Data Layer 2025', 'yes', 1, 1, 1, now(), now(), true)""")
    conn.execute(
        """insert into roads.developed_land (id, piece, geom)
           values (1, 1, ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 5070))""",
        (*ll(-500, -500), *ll(400, 700)))
    for i, pts in ((2, [(470, -400), (470, 600)]), (3, [(420, 450), (560, 450)])):
        conn.execute(
            """insert into roads.developed_land (id, piece, geom)
               values (%s, 1, ST_Transform(ST_Buffer(ST_Transform(ST_GeomFromEWKT(%s), 32611), 10, 'endcap=flat'),
                                           5070))""", (i, line(*pts)))


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
        # The roundabout (its nodes 20 m from its centre) is listed as a large junction too.
        with mock.patch.dict(B.LARGE_JUNCTION, {"spread_m": 15.0}):
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

    def test_a_lane_added_tapers_over_30_m(self):
        paved = lambda x, y: self.one(f"select bool_or(ST_Intersects(geom, {self.at(x, y)})) from roads.surface "  # noqa
                                      "where kind = 'carriageway'")[0]
        # Six lanes are 11.6 m a side, four 7.9: 5 m past the change the wider pavement isn't there yet, 40 m on it is.
        self.assertFalse(paved(225, 10.5))
        self.assertTrue(paved(225, 7.5))
        self.assertTrue(paved(260, 10.5))
        self.assertEqual(self.stats["surfaces"]["tapers"], 1)

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
        self.assertAlmostEqual(right, 4.0, delta=0.3)

    def test_the_build_row(self):
        bid, current, inputs, started, finished = self.one(
            "select id, current, inputs, started_at, finished_at from roads.build")
        self.assertTrue(current)
        names = [i["name"] for i in inputs]
        for name in ("osm", "achd_roads", "achd_msm", "achd_bike_network", "itd_hpms", "compass_centerline",
                     "intersections", "compass_zones", "cdl"):
            self.assertIn(name, names)
        self.assertEqual({i["name"]: i["republish"] for i in inputs}["intersections"], "internal")
        self.assertEqual(self.stats["build"], bid)
        self.assertGreaterEqual(finished, started)             # the clock's, not the transaction's start
        # Every surface is valid, and z15's copies exist for the big ones.
        bad = self.one("select count(*) from roads.surface where not ST_IsValid(geom)")[0]
        self.assertEqual(bad, 0)
        self.assertGreater(self.one("select count(*) from roads.surface where geom_z15 is not null")[0], 0)

    def test_the_review_list(self):
        rows = self.q("select r.kind, p.osm_id, r.road_segment_id, r.detail from roads.review r "
                      "left join roads.piece p on p.id = r.piece_id order by r.id")
        kinds = {k for k, *_ in rows}
        # A major road in Ada along no ACHD segment (the divided road's carriageways, the highway's west piece).
        self.assertIn(1002, [o for k, o, *_ in rows if k == "unmatched"])
        # The highway's east piece lies along an elevated ACHD segment, and OpenStreetMap draws no bridge.
        self.assertEqual([o for k, o, *_ in rows if k == "deck_mismatch"], [1006])
        # The roundabout, over the (lowered) spread.
        self.assertIn("junction_large", kinds)
        # The alley beside W Main St: kept off ACHD's arterial and listed.
        (osm_id, seg, detail), = [(o, s, d) for k, o, s, d in rows if k == "class_mismatch"]
        self.assertEqual((osm_id, detail["achd_class"], detail["source"], detail["names_agree"]),
                         (2020, "Minor Arterial", "achd_roads", None))
        self.assertIsNotNone(seg)
        self.assertIsNone(self.one("select road_segment_id from roads.piece where osm_id = 2020")[0])
        self.assertEqual(self.stats["review"], {k: sum(1 for r in rows if r[0] == k) for k in kinds})
        # The listing, by kind and for one kind.
        out = []
        B.show_review(self.conn, out=out.append)
        self.assertTrue(any(line.startswith("class_mismatch") for line in out))
        out = []
        B.show_review(self.conn, "deck_mismatch", out=out.append)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("w1006"))

    def test_the_review_queries_for_invalid_surfaces_and_bike_conflicts(self):
        # Neither happens in the town: their queries, on a bowtie surface and a flagged bike row.
        sid = self.one("select max(id) + 1 from roads.surface")[0]
        self.conn.execute("""insert into roads.surface (id, kind, junction_id, material, tier, geom)
                             values (%s, 'junction', 1, 'asphalt', 'estimated',
                                     ST_Multi(ST_GeomFromText('POLYGON((0 0, 10 10, 10 0, 0 10, 0 0))', 32611)))""",
                          (sid,))
        got = self.q(B._REVIEW_SQL["geometry"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][3]["surface"], sid)
        seg = self.one("select road_segment_id from roads.piece where osm_id = 1001 and seq = 3")[0]
        self.conn.execute("alter view roads.segment_bike_xsection rename to segment_bike_xsection_real")
        self.conn.execute(f"""create view roads.segment_bike_xsection as
                              select {int(seg)}::bigint as road_segment_id,
                                     array['direction_conflicts_one_way'] as flags""")
        got = self.q(B._REVIEW_SQL["bike_other_carriageway"])
        self.assertEqual([(r[1], r[2]) for r in got], [(1001, seg)])

    def test_farm_roads_are_rural_though_their_own_cells_read_developed(self):
        rows = self.q("""select x.edge_l, x.edge_r, x.total_w_m, x.sources->>'edge', x.material
                         from roads.xsection x join roads.piece p on p.id = x.piece_id
                         where p.osm_id in (2030, 2031)""")
        self.assertEqual(len(rows), 4)          # Farm Rd's two pieces and Dixie Rd's, split where they cross
        for edge_l, edge_r, total, source, material in rows:
            self.assertEqual((edge_l, edge_r, source), ("shoulder", "shoulder", "class"))
            self.assertEqual(total, B.X.DEFAULTS["local_pavement"]["rural"])
            self.assertEqual(material, "asphalt")         # the material follows the line, on developed cells
        # The streets in town are still curbed by the land either side.
        self.assertEqual(self.one("""select x.edge_l, x.edge_r, x.sources->>'edge' from roads.xsection x
                                     join roads.piece p on p.id = x.piece_id where p.osm_id = 2002""")[0:3],
                         ("curb", "curb", "developed"))
        # Where the farm roads cross, the corners' edges are shoulders, not curbs.
        kinds = self.q(f"""select distinct e.kind from roads.edge e join roads.junction j on j.id = e.junction_id
                           where ST_DWithin(j.geom, {self.at(470, 450)}, 2)""")
        self.assertEqual(kinds, [("shoulder",)])
        # And in town, where every street is curbed, they're curbs.
        kinds = self.q(f"""select distinct e.kind from roads.edge e join roads.junction j on j.id = e.junction_id
                           where ST_DWithin(j.geom, {self.at(150, 0)}, 2)""")
        self.assertEqual(kinds, [("curb",)])

    def test_the_calibration_reads_the_build(self):
        from plugins.roads.ingest import calibrate
        got = calibrate.measure(self.conn)
        self.assertEqual(set(got), {"achd", "sidewalks"})
        self.assertEqual(set(got["achd"]), {"Local", "Collector"})
        # Its own tables went with its savepoint; the build's are still there.
        self.assertIsNone(self.one("select to_regclass('pg_temp.cal_walk')")[0])
        self.assertGreater(self.one("select count(*) from roads.piece")[0], 0)
        out = []
        calibrate.report(self.conn, out=out.append)
        self.assertTrue(out[0].startswith("The defaults now:"))

    def test_the_command_line(self):
        @contextlib.contextmanager
        def connect():
            yield self.conn                     # the build's own transaction, never committed here
        with mock.patch("ingest.db.connect", connect):
            for argv, want in ((["--review"], "deck_mismatch"), (["--review", "class_mismatch"], "w2020"),
                               (["--calibrate"], "The defaults now")):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(B.main(argv), 0)
                self.assertIn(want, buf.getvalue())

    def test_an_export_waits_for_a_build_in_progress(self):
        import psycopg
        from plugins.roads.ingest import export as E
        # This connection's build holds its tables (TRUNCATE) until it commits: an export elsewhere waits for it
        # (here it gives up after 0.3 s), so it never reads half a build.
        with psycopg.connect(DB_URL) as other, tempfile.TemporaryDirectory() as archive:
            other.execute("set lock_timeout = '300ms'")
            other.commit()
            with self.assertRaises(psycopg.errors.LockNotAvailable):
                E.export(other, archive, build="20261011T000000Z")
            self.assertEqual(os.listdir(archive), [])

    def test_a_changed_source_marks_the_build(self):
        from plugins.roads.ingest import marks
        self.assertFalse(marks.mark(self.conn, "osm_street", 0))
        self.assertTrue(marks.mark(self.conn, "osm_street", 3, "ways"))
        self.assertEqual(self.one("select reason from ops.build_pending where build = 'roads-build' "
                                  "and marked_by = 'osm_street'")[0], "osm_street: 3 ways changed")

    def test_the_export_is_a_bakeable_internal_base(self):
        import tempfile
        from basemap.landscape import plan as LP
        from plugins.roads.ingest import export as E
        with tempfile.TemporaryDirectory() as archive:
            m = E.export(self.conn, archive, build="20261011T000000Z")
            names = [lay.name for lay in m.layers]
            self.assertEqual(names, ["lines", "surfaces_z15", "surfaces", "edges", "markings", "crosswalks",
                                     "paving_lots", "paving_ways", "paving_stalls"])
            self.assertEqual(m.republish, "internal")
            for lay in m.layers:
                self.assertTrue(lay["base"])
                self.assertIn("id", lay["fields"])
                # The road layers rest on ACHD's and ITD's widths (internal); the paving is OpenStreetMap's (yes).
                self.assertEqual((lay["licence"], lay["republish"]),
                                 ("ODbL-1.0", "yes" if lay.name.startswith("paving_") else "internal"))
            lines = next(lay for lay in m.layers if lay.name == "lines")
            self.assertEqual(lines["features"], self.one("select count(*) from roads.piece")[0])
            self.assertIn("minzoom", lines["fields"])
            self.assertIn("off", lines["fields"])
            self.assertLessEqual({"intersections", "compass_centerline"}, set(m.inputs))
            plan = LP.resolve({"roads": m})
            self.assertTrue(plan.roads)
            self.assertEqual(plan.republish, "internal")

    def test_the_paving_layers_hold_active_rows_without_nulls(self):
        import tempfile
        from plugins.roads.ingest import export as E
        with tempfile.TemporaryDirectory() as archive:
            m = E.export(self.conn, archive, build="20261011T000000Z")
            by = {lay.name: lay for lay in m.layers}
            # Only OpenStreetMap, and the CDL its default materials rest on: no ACHD or ITD input, so republish yes.
            for name in ("paving_lots", "paving_ways", "paving_stalls"):
                self.assertEqual(by[name]["inputs"], ["osm", "cdl"])
                self.assertEqual(by[name]["credit"], ["© OpenStreetMap contributors",
                                                      "USDA NASS Cropland Data Layer 2025"])
                self.assertEqual(by[name]["crs"], "EPSG:32611")
            self.assertEqual(by["lines"]["republish"], "internal")
            self.assertIn("achd_roads", by["lines"]["inputs"])
            self.assertEqual((by["paving_lots"]["features"], by["paving_ways"]["features"],
                              by["paving_stalls"]["features"]), (2, 3, 1))     # the inactive rows are left out
            self.assertEqual(by["paving_lots"]["fields"],
                             {"id": "long", "material": "string", "parking": "string", "layer": "int"})
            self.assertEqual((by["paving_lots"]["minzoom"], by["paving_lots"]["maxzoom"]), (14, 16))
            self.assertEqual((by["paving_ways"]["minzoom"], by["paving_ways"]["maxzoom"]), (15, 16))
            self.assertEqual((by["paving_stalls"]["minzoom"], by["paving_stalls"]["maxzoom"]), (16, 16))
        for lay in E.LAYERS:
            if lay.name.startswith("paving_"):
                rows = self.q(f"select * from ({lay.sql}) q")
                for row in rows:
                    self.assertNotIn(None, row, lay.name)
                self.assertEqual(self.one(f"select ST_SRID(geom) from ({lay.sql}) q limit 1")[0], 32611)
        lots = dict(self.q(f"select id, parking from ({next(l for l in E.LAYERS if l.name == 'paving_lots').sql}) q"))
        # A way's lot and a relation's with the same OpenStreetMap id get different ids; no tag reads 'unknown'.
        self.assertEqual(lots, {8002: "surface", 8003: "unknown"})
        ways = self.q(f"select id, layer from ({next(l for l in E.LAYERS if l.name == 'paving_ways').sql}) q order by 1")
        self.assertEqual(ways, [(3001, 0), (3002, 0), (3003, 0)])

    def test_the_lines_carry_the_width_the_surface_is_drawn_at(self):
        from plugins.roads.ingest import export as E
        lines = next(lay for lay in E.LAYERS if lay.name == "lines")
        # 1st St beside its sidewalk: the cap cut its right side to 4.0 m; the line is as wide as what's drawn,
        # and its middle lies left of the line.
        w, off, total, left, right = self.one(
            f"""select l.w, l.off, x.total_w_m, x.width_left_m, x.width_right_m from ({lines.sql}) l
                join roads.xsection x on x.piece_id = l.id
                where l.id = (select id from roads.piece where osm_id = 2001 and ST_DWithin(geom, {self.at(0, 120)}, 1))""")
        self.assertAlmostEqual(w, left + right, delta=0.06)
        self.assertLess(w, total)
        self.assertAlmostEqual(off, (right - left) / 2, delta=0.06)
        self.assertLess(off, 0)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a test database migrated through roads 0004")
class ExportSnapshotTest(unittest.TestCase):
    def test_an_export_reads_in_its_own_read_only_snapshot(self):
        import psycopg
        from psycopg import pq
        from plugins.roads.ingest import export as E
        with psycopg.connect(DB_URL) as conn, tempfile.TemporaryDirectory() as archive:
            if not conn.execute("select to_regclass('roads.piece') is not null").fetchone()[0]:
                self.skipTest("roads.piece is missing: apply roads 0003")
            conn.rollback()
            # The test database has no committed build: the export says so, and leaves no transaction open.
            with self.assertRaises(E.ExportError):
                E.export(conn, archive)
            self.assertEqual(conn.info.transaction_status, pq.TransactionStatus.IDLE)
            self.assertEqual(os.listdir(archive), [])


class ExportPruneTest(unittest.TestCase):
    def test_the_newest_two_exports_stay(self):
        from basemap.ground import manifest as M
        from plugins.roads.ingest import export as E
        with tempfile.TemporaryDirectory() as archive:
            for b in ("20261009T000000Z", "20261010T000000Z", "20261011T000000Z", "20261011T120000Z"):
                os.makedirs(M.export_dir(archive, "roads", b))
                with open(os.path.join(M.export_dir(archive, "roads", b), M.FILE), "w") as f:
                    f.write("{}")
            os.makedirs(M.export_dir(archive, "roads", "20261012T000000Z"))      # unfinished: no manifest yet
            self.assertEqual(E.prune(archive), ["20261009T000000Z", "20261010T000000Z"])
            self.assertEqual(sorted(os.listdir(os.path.join(archive, "roads", "export"))),
                             ["20261011T000000Z", "20261011T120000Z", "20261012T000000Z"])
            self.assertEqual(E.prune(archive), [])


class RunTest(unittest.TestCase):
    def test_a_run_checks_the_partition_builds_and_marks_the_export(self):
        seen = {}

        class FakeRun:
            def __init__(self, conn, build, then=()):
                seen["run"] = (conn, build, tuple(then))
                self.note = None

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                seen["note"] = self.note
                return False

        stats = {"build": "20261011T000000Z", "pieces": 3, "junctions": 1, "seconds": 1.5,
                 "surfaces": {"carriageway": 3, "junction": 1, "tapers": 1}}
        with mock.patch.object(B.builds, "Run", FakeRun), \
                mock.patch.object(B.osm_extract, "check_partition", return_value="abc123") as partition, \
                mock.patch.object(B, "make", return_value=stats) as make:
            self.assertEqual(B.run("conn"), stats)
        self.assertEqual(seen["run"], ("conn", "roads-build", ("roads-export",)))
        partition.assert_called_once_with("conn", ("osm_valley", "osm_street", "osm_paving"))
        self.assertEqual(make.call_args[0][:2], ("conn", "abc123"))
        self.assertEqual(seen["note"], "build 20261011T000000Z: 3 pieces, 1 junctions, 4 surfaces, 1.5 s")


class ClassRuleTest(unittest.TestCase):
    def test_a_target_far_above_the_piece_needs_the_names(self):
        rank = B.ACHD_RANK
        self.assertFalse(B.class_fits("service", rank["Interstate"], None))          # an alley by the interstate
        self.assertFalse(B.class_fits("tertiary", rank["Interstate"], False))        # a street beside it
        self.assertFalse(B.class_fits("residential", rank["Minor Arterial"], False))
        self.assertTrue(B.class_fits("residential", rank["Minor Arterial"], True))   # OSM calls an arterial residential
        self.assertTrue(B.class_fits("unclassified", rank["Collector"], None))
        self.assertTrue(B.class_fits("service", rank["Alley"], None))
        self.assertTrue(B.class_fits("service", rank["Local"], None))
        self.assertTrue(B.class_fits("motorway_link", rank["Interstate"], None))
        self.assertTrue(B.class_fits("residential", None, None))                     # a class we don't know
        # HPMS: interstate, US and state routes by their system; any other route a local street's (Boise's alleys
        # are HPMS routes: '32nd Alley St N').
        self.assertEqual((B.hpms_rank("01990ASH055"), B.hpms_rank("02070AUS020"), B.hpms_rank("00084AIN084"),
                          B.hpms_rank("12785AOH000")), (4, 4, 5, 1))
        self.assertFalse(B.class_fits("residential", B.hpms_rank("02070AUS020"), None))   # 'US 20 Main'
        self.assertFalse(B.class_fits("service", B.hpms_rank("02070AUS020"), None))
        self.assertTrue(B.class_fits("residential", B.hpms_rank("12785AOH000"), False))
        self.assertTrue(B.class_fits("service", B.hpms_rank("48503AOH000"), None))      # an alley on HPMS's alley
        self.assertTrue(B.class_fits("primary_link", B.hpms_rank("43906AIN084"), None))  # a ramp on the interstate's
        # A state route OpenStreetMap tags as a lesser road agrees by its ref.
        self.assertTrue(B.names_agree("SH 45 Main", "12th Avenue Road", "ID 45"))
        self.assertTrue(B.names_agree("US 20 Main", "Chinden Boulevard", "US 20;US 26"))
        self.assertIsNone(B.names_agree("SH 45 Main", "12th Avenue Road", None))
        self.assertFalse(B.names_agree("W Victory Rd", "South Milwaukee Lane", None))
        self.assertTrue(B.names_agree("N Ten Mile Rd", "North Ten Mile Road", None))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a test database migrated through 0021")
class MarksTest(unittest.TestCase):
    def test_a_segment_match_by_hand_marks_the_build(self):
        import psycopg
        from plugins.roads.ingest import segment_match

        class NoCommit:
            def __init__(self, conn):
                self.conn, self.commits = conn, 0

            def execute(self, *a, **k):
                return self.conn.execute(*a, **k)

            def commit(self):
                self.commits += 1

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with psycopg.connect(DB_URL) as conn:
            try:
                wrapped = NoCommit(conn)
                results = {"itd_hpms": {"lines": 1}, "achd_msm": {"failed": "ValueError: test"}}
                with mock.patch("ingest.db.connect", return_value=wrapped), \
                        mock.patch.object(segment_match, "rematch_all", return_value=results), \
                        contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    segment_match.main([])
                self.assertEqual(wrapped.commits, 1)
                self.assertEqual(conn.execute("""select reason from ops.build_pending
                                                 where build = 'roads-build' and marked_by = 'segment-match'""").fetchone(),
                                 ("rematched by hand: itd_hpms",))
            finally:
                conn.rollback()


if __name__ == "__main__":
    unittest.main()
