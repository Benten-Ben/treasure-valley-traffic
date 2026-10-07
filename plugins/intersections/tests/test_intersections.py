"""Tests for the intersection build (plugins/intersections/ingest/intersections.py).

The plan tests are offline, on a synthetic layout in metres. The database test
builds in a synthetic area outside the valley (around 42.5 N, 115.5 W), inside
one transaction that is rolled back, against a scratch database named by
TVT_TEST_DATABASE_URL (a clone with migration 0011). Streets, IDs and points
are all made up.

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from ingest import db
from plugins.intersections.ingest import intersections as ix

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def seg(i, name, *pts, cls="Minor Arterial"):
    return ix.Segment(i, name, cls, [list(pts)])


def dev(i, source, kind, x, y, name=None, **attrs):
    return ix.Device(i, source, f"{source}:{i}", kind, name, x, y, -115.5 + x / 1e5, 42.5 + y / 1e5, attrs)


def seed(i, location, x, y, synchro=None, **attrs):
    return dev(i, ix.SEED_SOURCE, "signal_intersection", x, y, location,
               location=location, synchro_id=synchro, control=attrs.pop("control", "signal"),
               operator=attrs.pop("operator", "Testtown"), county="Testco", **attrs)


def pole(i, x, y):
    return dev(i, ix.ACHD_SOURCE, "signal_pole", x, y)


def regional(i, x, y, location=None):
    return dev(i, ix.REGIONAL_SOURCE, "signal_intersection", x, y, location, location=location, operator="TESTTOWN")


def osm(i, x, y):
    return ix.OsmNode(i, x, y, -115.5 + x / 1e5, 42.5 + y / 1e5)


ROADS = ix.Roads([
    seg(1, "W Alpha Ave", (-500, 0), (0, 0)), seg(2, "E Alpha Ave", (0, 0), (500, 0)),
    seg(3, "N Beta St", (0, 0), (0, 500)), seg(4, "S Beta St", (0, -500), (0, 0)),
    seg(5, "N Gamma Rd", (300, -500), (300, 500)),                      # crosses Alpha on a bridge: no vertex there
    seg(6, "Delta Rd", (1500, 0), (2000, 0), (2500, 0)), seg(7, "Epsilon Rd", (2000, 0), (2000, 400)),
])


def layout():
    seeds = [
        seed(1, "ALPHA & BETA ST", 12, 9, synchro=901, approaches={"NB": {"leg": "S", "right_turn_lanes": 1}}),
        seed(2, "ALPHA & GAMMA", 300, 5),                  # only a bridge there: not snapped, no penalty
        seed(3, "DELTA & EPSILON", 2000, 90),              # its named junction is 90 m away
        seed(4, "ZETA & ETA", 5000, 5000),                 # no centerlines (like Canyon County)
        seed(5, "OMEGA SPUI", 9000, 0),
        seed(6, "THETA & IOTA", 10000, 0),
        seed(7, "KAPPA & LAMBDA", 11000, 0, synchro=950), seed(8, "MU & NU", 12000, 0, synchro=950),
    ]
    poles = [pole(101, 20, 20), pole(102, -20, 20), pole(103, -20, -20), pole(104, 20, -20),
             pole(111, 1000, 0), pole(112, 1030, 0), pole(113, 1015, 25),          # 3 leftover poles: a candidate
             pole(121, 3000, 0), pole(122, 3020, 0),                               # 2 leftover poles: nothing
             pole(131, 6010, 0), pole(132, 6000, 15),                              # with a Regional point: old pair
             pole(141, 8000, 0), pole(142, 8030, 0), pole(143, 8015, 20),          # + an OSM node: two sources
             pole(151, 9100, 0),                                                   # 100 m from the SPUI: attaches
             pole(161, 10100, 0)]                                                  # 100 m from a plain seed: doesn't
    regionals = [regional(201, 3, -3, "ALPHA & BETA"), regional(202, 4000, 0), regional(203, 6000, 0)]
    others = [dev(301, ix.ACHD_SOURCE, "rrfb", 25, 0), dev(302, ix.REGIONAL_SOURCE, "school_flasher", 4030, 0),
              dev(303, ix.ACHD_SOURCE, "fire_signal", 4500, 0)]
    nodes = [osm(1, 5, 5), osm(2, 7000, 0), osm(3, 7020, 10), osm(4, 8005, 5)]
    return seeds, poles, regionals, others, nodes


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.built, self.details = ix.plan(*layout(), ROADS)
        self.at = lambda x, y: min(self.built, key=lambda b: ix.dist(x, y, b.x, b.y))

    def test_seed_snaps_to_its_named_junction_and_three_sources_score_one(self):
        b = self.at(0, 0)
        self.assertEqual((b.x, b.y, b.snapped, b.snap_m), (0, 0, True, 15.0))
        self.assertEqual(b.name, "Alpha Ave & Beta St")
        self.assertEqual(b.evidence, {"compass", "compass_regional", "achd_2022", "osm"})
        self.assertEqual((b.confidence, b.status, b.synchro), (1.0, "active", 901))
        kinds = sorted(d.kind for d, _ in b.devices)
        self.assertEqual(kinds, ["rrfb", "signal_intersection", "signal_intersection"] + ["signal_pole"] * 4)
        self.assertEqual([round(d) for p, d in b.devices if p.kind == "signal_pole"], [28] * 4)

    def test_a_bridge_is_not_a_junction(self):
        b = self.at(300, 5)
        self.assertEqual((b.snapped, b.snap_m, b.confidence), (False, None, 0.7))

    def test_a_point_far_from_its_named_junction_stays_and_loses_confidence(self):
        b = self.at(2000, 90)
        self.assertEqual((b.x, b.y, b.snapped, b.snap_m, b.penalized), (2000, 90, False, 90.0, True))
        self.assertEqual((b.confidence, b.status), (0.6, "active"))

    def test_compass_alone_without_centerlines(self):
        b = self.at(5000, 5000)
        self.assertEqual((b.name, b.confidence, b.status, b.evidence), ("Zeta & Eta", 0.7, "active", {"compass"}))

    def test_leftover_poles_become_candidates_only_in_threes(self):
        b = self.at(1015, 8)
        self.assertEqual((b.evidence, b.confidence, b.status), ({"achd_2022"}, 0.5, "candidate"))
        self.assertTrue(b.name.startswith("Signal near "))
        self.assertGreater(min(ix.dist(3000, 0, x.x, x.y) for x in self.built), 900)
        self.assertEqual(self.details["counts"]["poles unattached"], 3)            # the pair, and the one by Theta

    def test_achd_and_osm_agree_without_compass(self):
        b = self.at(8015, 6)
        self.assertEqual((b.evidence, b.confidence, b.status), ({"achd_2022", "osm"}, 0.85, "active"))

    def test_regional_points(self):
        alone = self.at(4000, 0)
        self.assertEqual((alone.evidence, alone.confidence, alone.status), ({"compass_regional"}, 0.5, "candidate"))
        old = self.at(6000, 0)
        self.assertEqual((old.evidence, old.confidence, old.status),
                         ({"compass_regional", "achd_2022"}, 0.55, "candidate"))
        self.assertEqual(self.details["regional_by_operator"], {"TESTTOWN": (1, 3)})

    def test_osm_leftovers_cluster_into_a_candidate(self):
        b = self.at(7010, 5)
        self.assertEqual((b.evidence, b.confidence, b.status, len(b.osm)), ({"osm"}, 0.4, "candidate", 2))

    def test_spui_reaches_farther(self):
        self.assertIn(151, [d.id for d, _ in self.at(9000, 0).devices])
        self.assertNotIn(161, [d.id for d, _ in self.at(10000, 0).devices])

    def test_a_shared_synchro_id_identifies_neither(self):
        self.assertIsNone(self.at(11000, 0).synchro)
        self.assertIsNone(self.at(12000, 0).synchro)
        self.assertEqual(self.details["shared_synchro"], [950])

    def test_other_devices_link_within_60_m_but_are_not_evidence(self):
        self.assertEqual(self.at(4000, 0).evidence, {"compass_regional"})
        self.assertEqual([(d.id, dd) for d, dd in self.at(4000, 0).devices], [(202, 0.0), (302, 30.0)])
        self.assertNotIn(303, [d.id for b in self.built for d, _ in b.devices])
        self.assertEqual(self.details["counts"]["other devices linked"], 2)


class StableIdTest(unittest.TestCase):
    def test_synchro_first_then_nearest_within_30_m_and_leftovers_retire(self):
        built, _ = ix.plan(*layout(), ROADS)
        existing = [ix.Existing(11, 901, 50, 0, "active"), ix.Existing(12, None, 1020, 10, "candidate"),
                    ix.Existing(13, None, 20000, 0, "active"), ix.Existing(14, None, 1010, 40, "retired")]
        retire = ix.assign_ids(built, existing)
        at = lambda x, y: min(built, key=lambda b: ix.dist(x, y, b.x, b.y))
        self.assertEqual(at(0, 0).id, 11)                    # by Synchro ID, though 50 m away
        self.assertEqual(at(1015, 8).id, 12)                 # nearest within 30 m
        self.assertEqual(sorted(e.id for e in retire), [13, 14])
        self.assertEqual(sum(b.id is not None for b in built), 2)

    def test_nearest_wins_when_two_compete(self):
        a = ix.Built(0, 0, 0, 0, name="a")
        b = ix.Built(20, 0, 0, 0, name="b")
        retire = ix.assign_ids([a, b], [ix.Existing(7, None, 15, 0, "active")])
        self.assertEqual((a.id, b.id, retire), (None, 7, []))


class LinkTest(unittest.TestCase):
    def setUp(self):
        self.built, _ = ix.plan(*layout(), ROADS)

    def test_cameras_need_a_shared_street_within_80_m(self):
        links = ix.link_cameras(self.built, [(1, "Alpha & Beta", 30, 40), (2, "Beta & Kappa", 10, 10),
                                             (3, "Lambda & Mu", 5, 5), (4, "Alpha & Beta", 90, 0)])
        self.assertEqual(sorted(links), [1, 2])
        self.assertEqual(links[1][0].name, "Alpha Ave & Beta St")
        self.assertEqual(links[1][1:], (50.0, 1.0, "nearest_80m_street"))
        self.assertEqual(links[2][2], 0.8)

    def test_freeway_cameras_reach_their_interchange_signal_within_150_m(self):
        links = ix.link_cameras(self.built, [(5, "I-99 & Omega", 9120, 0),       # 120 m from the Omega SPUI
                                             (6, "I-99 & Theta", 10120, 0),      # 120 m, but not an interchange
                                             (7, "Omega & Rho", 9120, 0),        # not a freeway camera
                                             (8, "I-99 & Omega", 9160, 0)])      # 160 m: too far
        self.assertEqual(sorted(links), [5])
        self.assertEqual((links[5][0].name, links[5][1:]), ("Omega Spui", (120.0, 0.7, "interchange_150m")))

    def test_crossings_link_to_the_nearest_active_signal_within_300_m(self):
        links = ix.link_crossings(self.built, [(1, 150, 0), (2, 250, 0), (3, 1015, 150), (4, 0, 400), (5, 0, 280)])
        self.assertEqual({k: (b.name, d) for k, (b, d) in links.items()},
                         {1: ("Alpha Ave & Beta St", 150.0), 2: ("Alpha & Gamma", 50.2),
                          5: ("Alpha Ave & Beta St", 280.0)})


class ReviewTest(unittest.TestCase):
    def plan(self, *reviews):
        return ix.plan(*layout(), ROADS, reviews=list(reviews))

    def test_a_review_retires_its_intersection_and_nothing_links_to_it(self):
        built, details = self.plan(
            ix.Review("t1", "Pole group", "retired", "a roundabout now", 1012, 10, {"compass"}, ["achd_2022"]),
            ix.Review("t2", "Regional point", "retired", "no type", 4005, 0, {"compass", "achd_2022", "osm"},
                      ["compass_regional"]))
        at = lambda x, y: min(built, key=lambda b: ix.dist(x, y, b.x, b.y))
        self.assertEqual((at(1015, 8).status, at(1015, 8).reviewed_out), ("retired", True))
        self.assertEqual(at(4000, 0).status, "retired")
        self.assertNotIn(302, [d.id for b in built for d, _ in b.devices])     # the flasher by the retired point
        self.assertEqual(details["counts"]["retired by review"], 2)
        self.assertEqual([r.key for r, _ in details["reviews"]["applied"]], ["t1", "t2"])
        self.assertEqual(ix.link_crossings(built, [(1, 1015, 100)]), {})

    def test_new_evidence_from_a_reopen_source_lifts_the_review(self):
        built, details = self.plan(
            ix.Review("t3", "Poles and OSM", "candidate", "awaiting OSM", 8010, 5, {"compass", "osm"}, ["achd_2022"]),
            ix.Review("t4", "Nowhere", "retired", "gone", 50000, 50000))
        self.assertEqual(min(built, key=lambda b: ix.dist(8015, 6, b.x, b.y)).status, "active")
        (r, b, gained), = details["reviews"]["reopened"]
        self.assertEqual((r.key, gained), ("t3", ["osm"]))
        self.assertEqual([r.key for r in details["reviews"]["unmatched"]], ["t4"])

    def test_the_reviews_file_parses(self):
        reviews = ix.load_reviews()
        self.assertTrue(reviews)
        for r in reviews:
            self.assertIn(r.status, ("retired", "candidate", "active"))
            self.assertTrue(r.reason)
            self.assertTrue(400000 < r.x < 700000 and 4700000 < r.y < 4900000, r.key)     # in the valley, UTM 11N


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
AREA = (-115.6, 42.4, -115.4, 42.6)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0011)")
class DatabaseTest(unittest.TestCase):
    """The build against a real (scratch) database, in a synthetic area, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        if not self.conn.execute("select to_regclass('core.intersection') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("core.intersection is missing: apply migration 0011")
        self.x0, self.y0 = self.conn.execute(
            "select ST_X(p), ST_Y(p) from ST_Transform(ST_SetSRID(ST_MakePoint(-115.5, 42.5), 4326), 26911) p").fetchone()
        for name in (ix.SEED_SOURCE, ix.REGIONAL_SOURCE, ix.ACHD_SOURCE, ix.CAMERA_SOURCE, ix.OSM_SOURCE, "fra_crossings"):
            db.ensure_source(self.conn, {"name": name, "title": "test", "url": "https://example.test/", "access": "open"})

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def pt(self, x, y):
        return f"ST_Transform(ST_SetSRID(ST_MakePoint({self.x0 + x}, {self.y0 + y}), 26911), 4326)"

    def road(self, name, a, b):
        self.conn.execute(f"""insert into core.road_segment (name, functional_class, one_way, geom)
                              values (%s, 'Minor Arterial', 'both', ST_Multi(ST_MakeLine({self.pt(*a)}, {self.pt(*b)})))""",
                          (name,))

    def device(self, source, source_id, kind, x, y, name=None, attrs=None):
        return self.conn.execute(
            f"""insert into core.signal_device (source, source_id, kind, name, geom, attributes)
                values (%s, %s, %s, %s, {self.pt(x, y)}, %s) returning id""",
            (source, source_id, kind, name, json.dumps(attrs or {}))).fetchone()[0]

    def intersections(self):
        return self.conn.execute(
            f"""select id, name, status, evidence, confidence, achd_synchro_id,
                       round(ST_X(ST_Transform(geom, 26911))::numeric - {self.x0}), round(ST_Y(ST_Transform(geom, 26911))::numeric - {self.y0})
                from core.intersection where geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326) order by id""", AREA).fetchall()

    def test_build_links_and_reruns(self):
        c = self.conn
        self.road("W Alpha Ave", (-300, 0), (0, 0))
        self.road("E Alpha Ave", (0, 0), (300, 0))
        self.road("N Beta St", (0, 0), (0, 300))
        attrs = {"location": "ALPHA & BETA", "synchro_id": 99901, "control": "signal", "operator": "Testtown",
                 "county": "Testco", "coord_group": "TEST GROUP",
                 "approaches": {"NB": {"leg": "S", "right_turn_lanes": 1, "left_turn_phasing": "protected",
                                       "right_turn_phasing": None, "volumes": {"L": 5, "T": 50, "R": 7}},
                                "WB": {"leg": "E", "right_turn_lanes": 0, "left_turn_phasing": "permitted",
                                       "right_turn_phasing": None, "volumes": None}}}
        seed_id = self.device(ix.SEED_SOURCE, "synchro:99901", "signal_intersection", 6, 8, "Alpha & Beta", attrs)
        poles = [self.device(ix.ACHD_SOURCE, f"Test_Signals:{i}", "signal_pole", x, y)
                 for i, (x, y) in enumerate([(20, 20), (-20, 20), (20, -20)])]
        lone = [self.device(ix.ACHD_SOURCE, f"Test_Signals:{10 + i}", "signal_pole", x, y)
                for i, (x, y) in enumerate([(2000, 0), (2025, 0), (2010, 20)])]
        reg = self.device(ix.REGIONAL_SOURCE, "loc:test:signal_intersection:alpha & beta", "signal_intersection", 2, 2,
                          attrs={"operator": "TESTTOWN", "location": "ALPHA & BETA"})
        c.execute(f"""insert into core.osm_node (osm_id, kind, tags, geom)
                      values (990000000001, 'traffic_signals', '{{"highway": "traffic_signals"}}', {self.pt(4, -4)})""")
        cam = c.execute(f"""insert into core.camera (name, pole_geom, achd_cam_id) values ('Beta & Alpha', {self.pt(30, 30)}, 990001)
                            returning id""").fetchone()[0]
        c.execute("""insert into core.source_link (source, source_id, entity, entity_id, method, confidence)
                     values (%s, 'test-cam-guid', 'camera', %s, 'achd_cam_id', 1)""", (ix.CAMERA_SOURCE, cam))
        crossing = c.execute(f"""insert into core.rail_crossing (crossing_id, geom) values ('TEST01X', {self.pt(120, 0)})
                                 returning id""").fetchone()[0]

        stats, _ = ix.build(c, T0, AREA, reviews=[])
        rows = self.intersections()
        self.assertEqual(len(rows), 2)
        main, cand = rows
        self.assertEqual(main[1:], ("Alpha Ave & Beta St", "active", ["achd_2022", "compass", "compass_regional", "osm"],
                                    1.0, 99901, 0, 0))
        self.assertEqual(cand[2:5], ("candidate", ["achd_2022"], 0.5))
        self.assertEqual((stats["active"], stats["candidate"], stats["new"], stats["cameras linked"],
                          stats["crossings near signals"]), (1, 1, 2, 1, 1))
        linked = dict(c.execute("select id, intersection_id from core.signal_device where id = any(%s)",
                                (poles + [seed_id],)).fetchall())
        self.assertEqual(set(linked.values()), {main[0]})
        self.assertEqual(c.execute("select leg, right_turn_lanes, left_turn_phasing, peak_volumes from core.approach "
                                   "where intersection_id = %s order by leg", (main[0],)).fetchall(),
                         [("E", 0, "permitted", None), ("S", 1, "protected", {"L": 5, "T": 50, "R": 7})])
        self.assertEqual(c.execute("""select entity_id, method, round(distance_m) from core.source_link
                                      where source = %s and source_id = 'test-cam-guid' and entity = 'intersection'""",
                                   (ix.CAMERA_SOURCE,)).fetchone(), (main[0], "nearest_80m_street", 42))
        self.assertEqual(c.execute("select entity_id from core.source_link where source = %s and source_id = 'n990000000001'",
                                   (ix.OSM_SOURCE,)).fetchone(), (main[0],))
        self.assertEqual(c.execute("select intersection_id, round(signal_distance_m) from core.rail_crossing where id = %s",
                                   (crossing,)).fetchone(), (main[0], 120))

        # A review retires the candidate: its row stays (same ID), its poles are unlinked, and reruns keep it so.
        review = ix.Review("test", "Lone poles", "retired", "a roundabout now", self.x0 + 2010, self.y0 + 7,
                           {"compass"}, ["achd_2022"])
        for hour in (1, 2):
            stats, _ = ix.build(c, T0 + timedelta(hours=hour), AREA, reviews=[review])
            self.assertEqual([(r[0], r[2]) for r in self.intersections()], [(main[0], "active"), (cand[0], "retired")])
            self.assertEqual((stats["new"], stats["retired"], stats["retired by review"]), (0, 0, 1))
        self.assertEqual(c.execute("select count(*) from core.signal_device where id = any(%s) and intersection_id is not null",
                                   (lone,)).fetchone(), (0,))
        # Without the review it's scored as before.
        ix.build(c, T0 + timedelta(hours=3), AREA, reviews=[])
        self.assertEqual([r[2] for r in self.intersections()], ["active", "candidate"])

        # Rerun: the seed moves 5 m and the lone poles disappear. IDs hold; the candidate is retired, not deleted.
        c.execute(f"update core.signal_device set geom = {self.pt(10, 11)} where id = %s", (seed_id,))
        c.execute("update core.signal_device set active = false where id = any(%s)", (lone,))
        stats, _ = ix.build(c, T0 + timedelta(days=1), AREA, reviews=[])
        rows2 = self.intersections()
        self.assertEqual([r[0] for r in rows2], [main[0], cand[0]])
        self.assertEqual((rows2[0][2], rows2[1][2]), ("active", "retired"))
        self.assertEqual((stats["new"], stats["retired"]), (0, 1))

        # The poles come back: the retired row is reused, found within 30 m.
        c.execute("update core.signal_device set active = true where id = any(%s)", (lone,))
        stats, _ = ix.build(c, T0 + timedelta(days=2), AREA, reviews=[])
        rows3 = self.intersections()
        self.assertEqual([(r[0], r[2]) for r in rows3], [(main[0], "active"), (cand[0], "candidate")])
        self.assertEqual(stats["new"], 0)

        # Without its Synchro ID, the seed keeps its row by distance.
        c.execute("update core.signal_device set attributes = attributes - 'synchro_id' where id = %s", (seed_id,))
        ix.build(c, T0 + timedelta(days=3), AREA, reviews=[])
        self.assertEqual(self.intersections()[0][0], main[0])
        self.assertIsNone(self.intersections()[0][5])

        # Every source empty at once (a failed fetch, a withdrawn layer): refused, nothing retired.
        c.execute("update core.signal_device set active = false where id = any(%s)", ([seed_id, reg] + poles + lone,))
        c.execute("update core.osm_node set active = false where osm_id = 990000000001")
        with self.assertRaises(RuntimeError):
            ix.build(c, T0 + timedelta(days=4), AREA, reviews=[])
        self.assertEqual([r[2] for r in self.intersections()], ["active", "candidate"])


if __name__ == "__main__":
    unittest.main()
