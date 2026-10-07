"""Tests for the lanes rule (core.segment_lanes and its per-source views, migration 0017).

Database only: they run against a scratch database named by
TVT_TEST_DATABASE_URL (a clone migrated through 0018), inside one transaction
that is rolled back. Every row is synthetic: made-up segments, routes, ways
and lines in UTM 11N far from the valley, with their matches written directly
(the matcher has its own tests).

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import unittest

from ingest import db
from plugins.roads.ingest.sources import achd_msm, compass_centerline, itd_hpms, osm_valley

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
X0, Y0 = 300000, 4790000


def wkt(*pts):
    return "LINESTRING(" + ", ".join(f"{X0 + x} {Y0 + y}" for x, y in pts) + ")"


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through 0018")
class SegmentLanesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)
        if not cls.conn.execute("select to_regclass('core.segment_lanes') is not null").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("core.segment_lanes is missing: apply migrations 0017 and 0018")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        for s in (achd_msm.SOURCE, compass_centerline.SOURCE, osm_valley.SOURCE, itd_hpms.SOURCE):
            db.ensure_source(self.conn, s)
        for kind in ("through_lanes", "facility_type", "turn_lanes"):
            db.ensure_source(self.conn, itd_hpms.layer_source(kind))
        self.n = 0

    def tearDown(self):
        self.conn.rollback()

    def geom(self, *pts):
        return self.conn.execute("select ST_Transform(ST_GeomFromText(%s, 26911), 4326)", (wkt(*pts),)).fetchone()[0]

    def segment(self, x, functional_class, one_way="both"):
        """A 300 m ACHD segment drawn north at x."""
        self.n += 1
        return self.conn.execute(
            """insert into core.road_segment (achd_perm_id, name, functional_class, one_way, geom)
               values (%s, 'Test Rd', %s, %s, ST_Multi(%s::geometry)) returning id""",
            (-880000 - self.n, functional_class, one_way, self.geom((x, 0), (x, 300)))).fetchone()[0]

    def match(self, seg, source, source_id, share=1.0, confidence=1.0, method="buffer15_bearing20"):
        self.conn.execute(
            """insert into core.segment_match (road_segment_id, source, source_id, overlap_m, share, bearing_diff,
                 method, confidence) values (%s, %s, %s, 300 * %s, %s, 0, %s, %s)""",
            (seg, source, source_id, share, share, method, confidence))

    def hpms(self, seg, kind, route, x, south=False, **values):
        self.n += 1
        sid = f"test-{self.n}@{route}:0.0000"
        pts = [(x, 400), (x, -100)] if south else [(x, -100), (x, 400)]
        cols = ", ".join(values)
        self.conn.execute(
            f"""insert into core.hpms_section (kind, source_id, event_id, route_id, direction, geom
                  {', ' + cols if cols else ''})
                values (%s, %s, %s, %s, %s, ST_Multi(%s::geometry) {', %s' * len(values)})""",
            (kind, sid, f"test-{self.n}", route, route[5], self.geom(*pts), *values.values()))
        self.match(seg, f"itd_hpms_{kind}", sid)

    def msm(self, seg, lanes, x=None, also=(), **kw):
        """A Master Street Map line (drawn north at x, if given) matched to seg and the also segments."""
        self.n += 1
        gid = f"{{TEST-MSM-{self.n}}}"
        geom = self.geom((x, -50), (x, 350)) if x is not None else None
        self.conn.execute("""insert into core.msm_arterial (global_id, existing_lanes, funded_lanes, geom)
                             values (%s, %s, %s, ST_Multi(%s::geometry))""", (gid, lanes, kw.get("funded"), geom))
        for s in (seg, *also):
            self.match(s, "achd_msm", gid, method="buffer10_name")

    def compass(self, seg, lanes):
        self.n += 1
        gid = f"{{TEST-COMPASS-{self.n}}}"
        self.conn.execute("insert into core.compass_segment (global_id, pm_id, lanes, geom) values (%s, 'Tst1', %s, null)",
                          (gid, lanes))
        self.match(seg, "compass_centerline", gid)

    def way(self, seg, x, lanes=None, rows=(), south=False, oneway="no", share=1.0):
        """An OpenStreetMap way along the segment; rows: (direction, count) lane rows."""
        self.n += 1
        osm_id = -880000 - self.n
        pts = [(x, 300), (x, 0)] if south else [(x, 0), (x, 300)]
        self.conn.execute(
            """insert into core.osm_way (osm_id, highway, oneway, lanes, tags, geom)
               values (%s, 'primary', %s, %s, '{}', %s)""", (osm_id, oneway, lanes, self.geom(*pts)))
        for direction, count in rows:
            for i in range(count):
                self.conn.execute("insert into core.osm_lane (osm_id, direction, lane, turns) values (%s, %s, %s, '{}')",
                                  (osm_id, direction, i + 1))
        self.match(seg, "osm_valley", f"w{osm_id}", share=share)
        return osm_id

    def lanes(self, seg):
        cur = self.conn.execute("select * from core.segment_lanes where road_segment_id = %s", (seg,))
        names = [d.name for d in cur.description]
        return dict(zip(names, cur.fetchone()))

    def test_drawn_same_way(self):
        same, opposite = self.conn.execute(
            "select core.drawn_same_way(ST_Multi(%s::geometry), ST_Multi(%s::geometry)), "
            "core.drawn_same_way(%s::geometry, ST_Multi(%s::geometry))",
            (self.geom((0, -50), (0, 400)), self.geom((5, 0), (5, 300)),
             self.geom((0, 400), (0, -50)), self.geom((5, 0), (5, 300)))).fetchone()
        self.assertEqual((same, opposite), (True, False))

    def test_a_state_route_takes_hpms_turned_to_the_segments_direction(self):
        seg = self.segment(0, "Principal Arterial")
        # The A route is drawn south (against the segment): its ascending lanes run backward here.
        self.hpms(seg, "through_lanes", "09990ASH099", 7, south=True, through_lanes=5, lanes_ascending=3,
                  lanes_descending=2)
        self.hpms(seg, "through_lanes", "09990DSH099", 7, through_lanes=0, lanes_ascending=0, lanes_descending=1)
        self.hpms(seg, "facility_type", "09990ASH099", 7, facility_type="two_way")
        self.hpms(seg, "turn_lanes", "09990ASH099", 7, turn_lanes_left=3, turn_lanes_right=4)
        self.way(seg, 0, lanes=5, rows=[("forward", 2), ("backward", 2), ("both", 1)])
        r = self.lanes(seg)
        self.assertEqual((r["road_class"], r["source"], r["lanes_total"], r["lanes_forward"], r["lanes_backward"],
                          r["centre_turn_lane"], r["conflict"]), ("state", "itd_hpms", 5, 2, 3, True, False))
        h = r["candidates"]["itd_hpms"]
        self.assertEqual((h["route"], h["divided"], h["facility"]), ("09990ASH099", False, "two_way"))   # D ignored
        self.assertEqual(r["candidates"]["osm_valley"]["through"], 4)

    def test_a_divided_hpms_road_pairs_its_a_and_d_routes(self):
        seg = self.segment(1000, "Principal Arterial")
        self.hpms(seg, "through_lanes", "08880AUS088", 1007, through_lanes=2, lanes_ascending=2, lanes_descending=0)
        self.hpms(seg, "through_lanes", "08880DUS088", 993, south=True, through_lanes=0, lanes_ascending=0,
                  lanes_descending=2)
        r = self.lanes(seg)
        self.assertEqual((r["source"], r["lanes_total"], r["lanes_forward"], r["lanes_backward"]), ("itd_hpms", 4, 2, 2))
        self.assertTrue(r["candidates"]["itd_hpms"]["divided"])

    def test_an_arterial_takes_the_master_street_map_with_osms_split(self):
        seg = self.segment(2000, "Minor Arterial")
        self.msm(seg, 5, funded=7)
        self.hpms(seg, "through_lanes", "07770AOH000", 2000, through_lanes=2, lanes_ascending=1, lanes_descending=1)
        self.way(seg, 2000, lanes=4, rows=[("forward", 3), ("backward", 1)], south=True)   # drawn against the segment
        r = self.lanes(seg)
        self.assertEqual((r["road_class"], r["source"], r["lanes_total"], r["lanes_forward"], r["lanes_backward"],
                          r["centre_turn_lane"], r["split_from"], r["split_estimated"], r["conflict"]),
                         ("arterial", "achd_msm", 4, 1, 3, False, "osm_valley", False, False))   # HPMS's 1+1 doesn't count
        self.assertEqual((r["candidates"]["achd_msm"]["existing"], r["candidates"]["achd_msm"]["funded"]), (5, 7))

    def test_sources_more_than_a_lane_apart_conflict(self):
        seg = self.segment(3000, "Minor Arterial")
        self.msm(seg, 5)                                                   # 2+2 and a centre lane
        self.way(seg, 3000, lanes=3, rows=[("forward", 1), ("backward", 1), ("both", 1)])   # 1+1 and a centre lane
        r = self.lanes(seg)
        self.assertEqual((r["source"], r["lanes_forward"], r["lanes_backward"], r["centre_turn_lane"],
                          r["split_from"], r["split_estimated"], r["conflict"]),
                         ("achd_msm", 2, 2, True, "achd_msm", True, True))

    def test_compass_2_counts_only_when_a_trusted_source_agrees(self):
        alone = self.segment(4000, "Local")
        self.compass(alone, 2)
        self.hpms(alone, "through_lanes", "06660AOH000", 4000, through_lanes=2, lanes_ascending=1, lanes_descending=1)
        r = self.lanes(alone)                                             # HPMS off state routes doesn't corroborate
        self.assertEqual((r["source"], r["lanes_total"], r["lanes_forward"], r["confidence"]), ("default", 2, 1, 0.2))
        self.assertFalse(r["candidates"]["compass_centerline"]["usable"])
        agreed = self.segment(4100, "Local")
        self.compass(agreed, 2)
        self.way(agreed, 4100, lanes=2, rows=[("forward", 1), ("backward", 1)])
        r = self.lanes(agreed)
        self.assertEqual((r["source"], r["lanes_total"]), ("osm_valley", 2))
        self.assertTrue(r["candidates"]["compass_centerline"]["usable"])
        three = self.segment(4200, "Collector")
        self.compass(three, 3)
        r = self.lanes(three)
        self.assertEqual((r["source"], r["lanes_total"], r["centre_turn_lane"]), ("compass_centerline", 2, True))

    def test_osm_carriageways_of_a_divided_road_pair(self):
        seg = self.segment(5000, "Principal Arterial")
        one = self.way(seg, 5007, rows=[("forward", 2)], oneway="yes")
        other = self.way(seg, 4993, rows=[("forward", 2)], oneway="yes", south=True, share=0.95)
        r = self.lanes(seg)
        self.assertEqual((r["source"], r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["centre_turn_lane"]),
                         ("osm_valley", 4, 2, 2, False))
        self.assertEqual((r["candidates"]["osm_valley"]["way"], r["candidates"]["osm_valley"]["other_carriageway"]),
                         (f"w{one}", f"w{other}"))

    def test_a_one_way_segment_puts_every_lane_one_way(self):
        seg = self.segment(6000, "Minor Arterial", one_way="backward")
        self.msm(seg, 3)
        r = self.lanes(seg)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["centre_turn_lane"]),
                         (3, 0, 3, False))

    def test_a_divided_highway_coded_two_way_keeps_both_carriageways(self):
        # ITD codes a divided highway's inventory direction as a two-way roadway (I-84): no halving.
        seg = self.segment(8000, "Interstate")
        self.hpms(seg, "through_lanes", "07070AIN077", 8007, through_lanes=3, lanes_ascending=3, lanes_descending=0)
        self.hpms(seg, "through_lanes", "07070DIN077", 7993, south=True, through_lanes=0, lanes_ascending=0,
                  lanes_descending=3)
        self.hpms(seg, "facility_type", "07070AIN077", 8007, facility_type="two_way")
        r = self.lanes(seg)
        self.assertEqual((r["source"], r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["flags"]),
                         ("itd_hpms", 6, 3, 3, []))
        self.assertTrue(r["candidates"]["itd_hpms"]["divided"])

    def test_facility_and_turn_rows_must_be_the_a_routes(self):
        seg = self.segment(8500, "Principal Arterial")
        self.hpms(seg, "through_lanes", "06060ASH066", 8507, through_lanes=2, lanes_ascending=2, lanes_descending=0)
        self.hpms(seg, "through_lanes", "06060DSH066", 8493, south=True, through_lanes=0, lanes_ascending=0,
                  lanes_descending=2)
        self.hpms(seg, "facility_type", "05550AUS055", 8500, facility_type="one_way")      # another route's
        self.hpms(seg, "turn_lanes", "05550AUS055", 8500, turn_lanes_left=3, turn_lanes_right=3)
        r = self.lanes(seg)
        self.assertEqual((r["lanes_total"], r["centre_turn_lane"]), (4, None))
        self.assertNotIn("facility", r["candidates"]["itd_hpms"])

    def test_a_one_way_carriageway_takes_only_its_own_direction(self):
        # Both carriageways lie within 15 m of each one-way segment; only the one running its way counts.
        north = self.segment(9000, "Interstate", one_way="forward")
        south = self.segment(9100, "Interstate", one_way="backward")
        for seg, x in ((north, 9000), (south, 9100)):
            self.hpms(seg, "through_lanes", "04040AIN044", x + 5, through_lanes=3, lanes_ascending=3,
                      lanes_descending=0)
            self.hpms(seg, "through_lanes", "04040DIN044", x - 5, south=True, through_lanes=0, lanes_ascending=0,
                      lanes_descending=2)
        r = self.lanes(north)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["centre_turn_lane"]),
                         (3, 3, 0, False))
        self.assertEqual(r["candidates"]["itd_hpms"]["carriageway"], "A")
        r = self.lanes(south)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"]), (2, 0, 2))
        self.assertEqual(r["candidates"]["itd_hpms"]["carriageway"], "D")
        # A carriageway only the D route runs along, shared with a US route whose D row there is a 1-lane
        # placeholder: the interstate's wins.
        alone = self.segment(9200, "Interstate", one_way="forward")
        self.hpms(alone, "through_lanes", "02020DUS022", 9200, south=True, through_lanes=0, lanes_ascending=0,
                  lanes_descending=1)
        self.hpms(alone, "through_lanes", "04040DIN044", 9200, south=True, through_lanes=0, lanes_ascending=0,
                  lanes_descending=2)
        r = self.lanes(alone)
        self.assertEqual((r["source"], r["lanes_total"], r["lanes_forward"], r["lanes_backward"]), ("itd_hpms", 2, 2, 0))
        self.assertEqual(r["candidates"]["itd_hpms"]["d_route"], "04040DIN044")

    def test_an_hpms_total_of_0_is_unknown(self):
        seg = self.segment(9500, "Principal Arterial")
        self.hpms(seg, "through_lanes", "03030ASH033", 9500, through_lanes=0, lanes_ascending=0, lanes_descending=0)
        self.way(seg, 9500, lanes=4, rows=[("forward", 2), ("backward", 2)])
        r = self.lanes(seg)
        self.assertEqual((r["road_class"], r["source"], r["lanes_total"]), ("state", "osm_valley", 4))

    def test_one_lane_on_a_two_way_road_is_one_lane_flagged(self):
        seg = self.segment(10500, "Minor Arterial")
        self.msm(seg, 1)
        r = self.lanes(seg)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["centre_turn_lane"],
                          r["flags"], r["confidence"]), (1, None, None, False, ["single_lane"], 0.5))
        local = self.segment(10600, "Local")
        self.compass(local, 1)
        r = self.lanes(local)
        self.assertEqual((r["source"], r["lanes_total"], r["flags"], r["confidence"]),
                         ("compass_centerline", 1, ["single_lane"], 0.5))

    def test_a_divided_roads_carriageways_split_the_master_street_maps_cross_section(self):
        north = self.segment(9993 + 1000, "Minor Arterial", one_way="forward")       # x 10993, runs north
        south = self.segment(10007 + 1000, "Minor Arterial", one_way="backward")     # x 11007, runs south
        self.msm(north, 5, x=11000, also=[south])
        r = self.lanes(north)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["centre_turn_lane"],
                          r["flags"], r["split_estimated"]), (2, 2, 0, False, ["carriageway_split"], True))
        r = self.lanes(south)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"]), (2, 0, 2))
        # A one-way street (its line has segments running one way only) keeps every lane.
        street = self.segment(12000, "Minor Arterial", one_way="forward")
        self.msm(street, 3, x=12000)
        r = self.lanes(street)
        self.assertEqual((r["lanes_total"], r["lanes_forward"], r["lanes_backward"], r["flags"]), (3, 3, 0, []))

    def test_every_active_segment_has_a_row(self):
        seg = self.segment(7000, "Driveway")
        r = self.lanes(seg)
        self.assertEqual((r["road_class"], r["source"], r["lanes_total"], r["conflict"], r["candidates"]),
                         ("other", None, None, False, {}))
        json.dumps(r["candidates"])


if __name__ == "__main__":
    unittest.main()
