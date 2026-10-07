"""Tests for the side-by-side ribbons (docs/14 §14.4, "Side-by-side ribbons").

The synthetic tests are offline, in metres around a point in Boise. The
real-data tests run against a database only when TVT_TEST_DATABASE_URL names
one (a package clone such as tvt_wp6, never the server's): they read VRT's
shapes and write nothing that outlives the test (everything is rolled back).

Run: python3 -m unittest discover -s ingest/tests -t .
     TVT_TEST_DATABASE_URL=postgres://tvt:...@localhost/tvt_wp6 python3 -m unittest ingest.tests.test_transit_ribbons
"""

import math
import os
import random
import time
import unittest
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ingest import route_colors as rc
from ingest import transit_ribbons as tr

X0, Y0 = 560000.0, 4830000.0     # UTM 11N, west Boise
COVER_M = 45.0


def ll(pts):
    return [tr.from_utm(X0 + x, Y0 + y) for x, y in pts]


def shape(sid, route, pts):
    return {"shape_id": sid, "route_id": route, "coords": ll(pts)}


def xy(coords):
    return [(x - X0, y - Y0) for x, y in (tr.to_utm(*c) for c in coords)]


def run_build(shapes, order=None, stored=None, **kw):
    order = order or sorted({s["route_id"] for s in shapes})
    stored = stored if stored is not None else {r: rc.PALETTE[i % 13] for i, r in enumerate(order)}
    return tr.build(shapes, order, stored, **kw)


def segments_with(result, *routes):
    return [s for s in result["segments"] if set(routes) <= set(s["routes"])]


def coverage(result, shapes):
    """Per route: the share of its shapes' points (every 5 m) within COVER_M of a segment carrying it."""
    grids = defaultdict(lambda: tr._Grid(COVER_M))
    for s in result["segments"]:
        pts = tr.densify([tr.to_utm(*c) for c in s["coords"]], 2.0)
        for r in s["routes"]:
            for p in pts:
                grids[r].add(p[0], p[1], p)
    hit, total = defaultdict(int), defaultdict(int)
    for sh in shapes:
        r = sh["route_id"]
        for p in tr.densify([tr.to_utm(*c) for c in sh["coords"]]):
            total[r] += 1
            if any(tr._dist(p, q) <= COVER_M for q in grids[r].near(*p)):
                hit[r] += 1
    return {r: hit[r] / total[r] for r in total}


def end_gaps(result):
    """Distances between consecutive segments' touching ends along every shape's path."""
    seg = {s["id"]: [tr.to_utm(*c) for c in s["coords"]] for s in result["segments"]}
    out = []
    for path in result["paths"].values():
        for (s1, d1), (s2, d2) in zip(path, path[1:]):
            a = seg[s1][-1] if d1 == 1 else seg[s1][0]
            b = seg[s2][0] if d2 == 1 else seg[s2][-1]
            out.append(tr._dist(a, b))
    return out


class ProjectionTest(unittest.TestCase):
    # The UTM projection itself is tested in ingest/tests/test_utm.py.

    def test_densify_and_simplify(self):
        pts = tr.densify([(0, 0), (12, 0), (12, 7)])
        self.assertEqual(pts[0], (0, 0))
        self.assertEqual(pts[-1], (12, 7))
        self.assertTrue(all(abs(tr._dist(a, b) - 5) < 1e-9 for a, b in zip(pts[:3], pts[1:3])))
        self.assertEqual(tr.simplify([(0, 0), (5, 0.5), (10, 0)]), [(0, 0), (10, 0)])
        self.assertEqual(tr.simplify([(0, 0), (5, 2), (10, 0)]), [(0, 0), (5, 2), (10, 0)])


class CleanupTest(unittest.TestCase):
    def test_a_30_m_gap_between_runs_on_one_piece_is_bridged(self):
        labels = [(0, i) for i in range(30)] + [None] * 6 + [(0, 36 + i) for i in range(30)]
        tr._bridge(labels)
        self.assertTrue(all(lab and lab[0] == 0 for lab in labels))
        self.assertEqual([lab[1] for lab in labels[29:37]], list(range(29, 37)))

    def test_a_40_m_gap_or_a_gap_to_elsewhere_is_not(self):
        labels = [(0, i) for i in range(30)] + [None] * 8 + [(0, 38 + i) for i in range(30)]
        tr._bridge(labels)
        self.assertEqual(labels.count(None), 8)
        labels = [(0, i) for i in range(30)] + [None] * 6 + [(0, 200 + i) for i in range(30)]
        tr._bridge(labels)
        self.assertEqual(labels.count(None), 6)

    def test_matched_runs_under_80_m_become_unmatched(self):
        labels = [None] * 10 + [(0, i) for i in range(15)] + [None] * 10 + [(1, i) for i in range(16)]
        tr._drop_short(labels)
        self.assertTrue(all(lab is None for lab in labels[:35]))      # 15 points: 75 m
        self.assertTrue(all(lab for lab in labels[35:]))              # 16 points: 80 m


class CorridorTest(unittest.TestCase):
    def y_junction(self, a_goes_left=True):
        left, right = [(0, 0), (0, 1000), (-700, 1700)], [(0, 0), (0, 1000), (700, 1700)]
        return [shape("a", "A", left if a_goes_left else right), shape("b", "B", right if a_goes_left else left)]

    def test_y_junction_orders_the_trunk_by_turn_with_no_crossing(self):
        for a_left, expected in ((True, ["A", "B"]), (False, ["B", "A"])):
            res = run_build(self.y_junction(a_left), order=["A", "B"])
            trunk = segments_with(res, "A", "B")
            self.assertEqual(len(trunk), 1)
            pts = xy(trunk[0]["coords"])
            self.assertLess(pts[0][1], pts[-1][1])                   # digitized toward the fork
            self.assertAlmostEqual(trunk[0]["length_m"], 1000, delta=25)
            self.assertEqual(trunk[0]["routes"], expected)
            self.assertEqual(res["stats"]["cost"], 0)
            self.assertEqual(len(res["segments"]), 3)

    def test_antiparallel_lines_25_m_apart_merge_60_m_apart_dont(self):
        for gap, merged in ((25, True), (60, False)):
            res = run_build([shape("a", "A", [(0, 0), (2000, 0)]), shape("b", "B", [(2000, gap), (0, gap)])])
            both = segments_with(res, "A", "B")
            if merged:
                self.assertEqual(len(res["segments"]), 1)
                self.assertAlmostEqual(both[0]["length_m"], 2000, delta=1)
            else:
                self.assertEqual(both, [])

    def test_crossing_streets_dont_merge(self):
        res = run_build([shape("a", "A", [(-1000, 0), (1000, 0)]), shape("b", "B", [(0, -1000), (0, 1000)])])
        self.assertEqual(segments_with(res, "A", "B"), [])

    def test_an_overlap_under_80_m_doesnt_merge(self):
        res = run_build([shape("a", "A", [(0, 0), (2000, 0)]),
                         shape("b", "B", [(900, -1000), (900, 0), (960, 0), (960, 1000)])])
        self.assertEqual(segments_with(res, "A", "B"), [])
        res = run_build([shape("a", "A", [(0, 0), (2000, 0)]),
                         shape("b", "B", [(800, -1000), (800, 0), (1000, 0), (1000, 1000)])])
        self.assertEqual(len(segments_with(res, "A", "B")), 1)        # 200 m does

    def test_a_short_detour_inside_a_shared_run_is_bridged(self):
        # B leaves A's street for a stop bay (10 m out and back) halfway along: B makes no piece of its own.
        res = run_build([shape("a", "A", [(-100, 0), (2000, 0)]),
                         shape("b", "B", [(0, 5), (1000, 5), (1000, 15), (1000, 5), (2000, 5)])])
        self.assertEqual(len(segments_with(res, "B")), len(segments_with(res, "A", "B")))
        self.assertAlmostEqual(sum(s["length_m"] for s in segments_with(res, "B")), 2000, delta=10)
        self.assertAlmostEqual(sum(s["length_m"] for s in res["segments"]), 2100, delta=2)

    def test_a_loop_closes_on_one_node(self):
        res = run_build([shape("loop", "L", [(0, 0), (500, 0), (500, 500), (0, 500), (0, 10)])])
        segs = res["segments"]
        first, last = xy(segs[0]["coords"])[0], xy(segs[-1]["coords"])[-1]
        self.assertLess(tr._dist(first, last), 0.01)
        self.assertEqual(max(end_gaps(res) or [0]), 0)

    def test_a_route_running_back_over_its_own_street_shares_one_ribbon(self):
        # A lollipop: out along the street, round a block, back along the same street.
        out = [(0, 0), (1500, 0), (1500, 400), (1900, 400), (1900, -10), (1520, -10), (0, -10)]
        res = run_build([shape("p", "P", out)])
        stem = [s for s in res["segments"] if all(abs(y) < 20 for _, y in xy(s["coords"]))]
        self.assertAlmostEqual(sum(s["length_m"] for s in stem), 1500, delta=60)   # drawn once, not twice

    def test_same_input_gives_byte_identical_output(self):
        shapes = self.y_junction() + [shape("c", "C", [(-500, 500), (0, 500), (0, 900), (400, 1300)])]
        a = run_build(shapes)
        shuffled = shapes[:]
        random.Random(7).shuffle(shuffled)
        b = run_build(shuffled)
        self.assertEqual(tr.ribbons_json(a), tr.ribbons_json(b))
        self.assertEqual(a["build"], b["build"])


def grid_network():
    """Six routes on a small street grid, sharing streets in different combinations."""
    s = []
    s.append(shape("1a", "1", [(0, 0), (3000, 0), (3000, 2000)]))
    s.append(shape("1b", "1", [(3000, 2000), (3000, 0), (0, 0)]))
    s.append(shape("2a", "2", [(0, 0), (2000, 0), (2000, 2000)]))
    s.append(shape("3a", "3", [(-1000, 0), (3000, 0), (3000, -1500)]))
    s.append(shape("4a", "4", [(1000, -1500), (1000, 0), (3000, 0), (3000, 2000)]))
    s.append(shape("5a", "5", [(2000, 2000), (2000, 0), (1000, 0), (1000, -1500)]))
    s.append(shape("6a", "6", [(0, 1000), (2000, 1000), (2000, 0), (3000, 0)]))
    s.append(shape("7a", "7", [(-2000, -1000), (-2000, 3000)]))           # alone
    return s


class NetworkTest(unittest.TestCase):
    def test_each_route_covers_its_shapes_and_ends_meet(self):
        shapes = grid_network()
        res = run_build(shapes)
        for r, share in coverage(res, shapes).items():
            self.assertGreaterEqual(share, 0.99, r)
        self.assertLessEqual(max(end_gaps(res)), 1.0)
        self.assertEqual(res["stats"]["node_gaps"], 0)

    def test_rebuilding_unchanged_input_changes_nothing(self):
        shapes = grid_network()
        order = ["1", "2", "3", "4", "5", "6"]
        clashing = {"1": rc.PALETTE[7], "2": rc.PALETTE[5], "3": rc.PALETTE[2], "4": rc.PALETTE[7],
                    "5": rc.PALETTE[1], "6": rc.PALETTE[3]}              # red, green, aqua, red, orange, yellow
        first = tr.build(shapes, order, clashing)
        self.assertEqual(first["clashes"], [])
        again = tr.build(shapes, order, first["colors"])
        self.assertEqual(again["assignment"]["changes"], [])            # 0 colors change
        self.assertEqual(again["colors"], first["colors"])
        self.assertEqual(tr.ribbons_json(again), tr.ribbons_json(first))   # byte-identical ribbons
        self.assertEqual(again["build"], first["build"])

    def test_neighbors_come_from_adjacent_slots_and_shared_streets(self):
        res = run_build(grid_network())
        nb = res["neighbors"]
        self.assertIn("3", nb["1"])                                    # 1, 3 and 4 share the x axis
        self.assertIn("4", nb["1"])
        self.assertIn("6", nb["3"])                                    # 1 km of it, from x 2000
        self.assertNotIn("7", nb)                                      # 7 shares nothing
        for s in res["segments"]:                                      # adjacent slots for 100 m or more
            if s["length_m"] >= tr.ADJACENT_M:
                for a, b in zip(s["routes"], s["routes"][1:]):
                    self.assertIn(b, nb[a])
        for a, ns in nb.items():
            for b in ns:
                self.assertFalse(rc.clash(res["colors"][a], res["colors"][b]), (a, b))

    def test_the_color_pass_keeps_the_cost(self):
        res = run_build(grid_network())
        self.assertEqual(res["stats"]["cost"], res["stats"]["cost_before_colors"])

    def test_dormant_routes_take_no_slot_keep_their_color_and_change_the_hash(self):
        shapes = grid_network()
        order = ["1", "2", "3", "4", "5", "6"]
        base = run_build(shapes, order)
        stored = base["colors"]
        dorm = tr.build(shapes, order, stored, dormant={"6"})
        self.assertNotEqual(dorm["input_hash"], base["input_hash"])
        self.assertNotEqual(dorm["build"], base["build"])
        self.assertFalse(any("6" in s["routes"] for s in dorm["segments"]))
        self.assertEqual(dorm["colors"]["6"], stored["6"])
        back = tr.build(shapes, order, dorm["colors"])
        self.assertEqual(back["input_hash"], base["input_hash"])
        self.assertEqual(back["build"], base["build"])
        self.assertEqual(tr.ribbons_json(back), tr.ribbons_json(base))

    def test_hub_segments(self):
        (lon, lat), = ll([(1500, 0)])
        res = run_build(grid_network(), hub_stops=[{"stop_id": "H", "lon": lon, "lat": lat}])
        for s in res["segments"]:
            mid = tr.point_at(xy(s["coords"]), 0.5)
            self.assertEqual(s["hub"], tr._dist(mid, (1500, 0)) <= tr.HUB_SEGMENT_M, s["id"])
        self.assertEqual([set(s["routes"]) for s in res["segments"] if s["hub"]], [{"1", "2", "3", "4", "5"}])


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a package clone (e.g. tvt_wp6) for the real-data checks")
class RealDataTest(unittest.TestCase):
    """docs/14 §14.4 on VRT's real shapes: build <= 30 s, cost <= 520, coverage, joined ends, no clash."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        assert DB_URL.rsplit("/", 1)[-1].startswith("tvt_"), "use a package clone (tvt_<wp>)"
        cls.conn = psycopg.connect(DB_URL)
        if cls.conn.execute("select to_regclass('core.transit_ribbon')").fetchone()[0] is None:
            raise unittest.SkipTest("migration 0006 isn't applied to this database")
        cls.inputs = tr.load_inputs(cls.conn)
        cls.dormant = tr.dormant_routes(cls.conn)
        t0 = time.monotonic()
        cls.res = tr.build(cls.inputs["shapes"], cls.inputs["order"], cls.inputs["stored"], cls.inputs["hubs"],
                           cls.dormant, cls.inputs["pinned"])
        cls.seconds = time.monotonic() - t0
        cls.conn.rollback()

    @classmethod
    def tearDownClass(cls):
        cls.conn.rollback()
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def test_limits(self):
        self.assertLessEqual(self.seconds, 30)
        self.assertLessEqual(self.res["stats"]["cost"], 520)
        self.assertEqual(self.res["clashes"], [])
        self.assertEqual(self.res["stats"]["node_gaps"], 0)

    def test_coverage_and_joined_ends(self):
        live = [s for s in self.inputs["shapes"] if s["route_id"] not in self.dormant]
        for r, share in coverage(self.res, live).items():
            self.assertGreaterEqual(share, 0.99, r)
        self.assertLessEqual(max(end_gaps(self.res)), 1.0)

    def test_routes_40_42_and_45(self):
        # On feed 457, 40 and 45 share I-84 between Nampa and Meridian, 40 and 42 share it east of
        # Meridian and in Caldwell, and all three meet (n >= 3) where 42 and 45 cross it at Garrity.
        segs = self.res["segments"]

        def shared(*routes):
            return sum(s["length_m"] for s in segs if set(routes) <= set(s["routes"]))

        self.assertGreaterEqual(shared("40", "45"), 5000)
        self.assertGreaterEqual(shared("40", "42"), 4000)
        self.assertTrue(any(len(s["routes"]) >= 3 and {"40", "42", "45"} <= set(s["routes"]) for s in segs))

    def test_byte_identical_and_stable_rebuild(self):
        again = tr.build(self.inputs["shapes"], self.inputs["order"], self.res["colors"], self.inputs["hubs"],
                         self.dormant, self.inputs["pinned"])
        self.assertEqual(again["assignment"]["changes"], [])
        self.assertEqual(tr.ribbons_json(again), tr.ribbons_json(self.res))

    def test_run_stores_skips_and_keeps_the_previous_build_on_failure(self):
        conn = self.conn
        dry = tr.run(conn, force=True, dry_run=True, log=lambda *_: None)
        self.assertEqual(dry["ribbons"], "dry run")
        self.assertEqual(conn.execute("select count(*) from core.transit_ribbon").fetchone()[0], 0)
        stats = tr.run(conn, log=lambda *_: None)
        self.assertEqual(stats["ribbons"], "built")
        n = conn.execute("select count(*), count(distinct build) from core.transit_ribbon").fetchone()
        self.assertEqual(n, (len(self.res["segments"]), 1))
        self.assertEqual(tr.run(conn, log=lambda *_: None)["ribbons"], "unchanged")
        # A store that fails half way keeps the previous ribbons (the savepoint rolls back).
        bad = dict(self.res, build="broken", segments=self.res["segments"][:3] + [dict(self.res["segments"][3],
                                                                                      coords=[[0, 0]])])
        with self.assertRaises(Exception):
            tr.store(conn, bad)
        self.assertEqual(conn.execute("select count(*), min(build) from core.transit_ribbon").fetchone(),
                         (len(self.res["segments"]), stats["build"]))
        colors = dict(conn.execute("select route_id, color from core.transit_route where active").fetchall())
        self.assertEqual(rc.clashes(colors, {r: set(v) for r, v in self.res["neighbors"].items()}), [])

    def test_the_daily_feed_load_builds_the_ribbons(self):
        from ingest.sources import vrt_gtfs
        from ingest.tests.test_transit import tiny_gtfs
        feed = dict(vrt_gtfs.parse_feed(tiny_gtfs()), version="tiny-test")   # retires every real route
        stats = vrt_gtfs.store(self.conn, feed)
        self.assertEqual(stats["ribbons"], "built")
        routes = {r for (rs,) in self.conn.execute("select routes from core.transit_ribbon") for r in rs}
        self.assertEqual(routes, {"7", "9"})
        for color, text in self.conn.execute(
                "select color, text_color from core.transit_route where route_id in ('7', '9')").fetchall():
            self.assertIn(color, rc.PALETTE)
            self.assertEqual(text, rc.badge_text_color(color))

    def test_a_failed_build_keeps_the_ribbons_and_still_colors_new_routes(self):
        from ingest.sources import vrt_gtfs
        from ingest.tests.test_transit import tiny_gtfs
        tr.run(self.conn, log=lambda *_: None)
        before = self.conn.execute("select count(*), min(build) from core.transit_ribbon").fetchone()
        self.conn.execute("update core.transit_route set color = null where route_id = '7'")
        real_build = tr.build
        tr.build = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            stats = vrt_gtfs.store(self.conn, vrt_gtfs.parse_feed(tiny_gtfs()))
        finally:
            tr.build = real_build
        self.assertEqual(stats["ribbons"], "failed")
        self.assertEqual(self.conn.execute("select count(*), min(build) from core.transit_ribbon").fetchone(), before)
        color = self.conn.execute("select color from core.transit_route where route_id = '7'").fetchone()[0]
        self.assertIn(color, rc.PALETTE)

    def test_dormancy_needs_seven_days_of_positions(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(tr.dormant_routes(self.conn, now), set())    # the clone holds hours, not days
        # Pretend the table spans 8 days and one route ran today: every other route is dormant.
        self.conn.execute("""insert into obs.vehicle_position (ts, vehicle_id, route_id, geom)
                             values (%s, 'test-old', null, ST_SetSRID(ST_MakePoint(-116.2, 43.6), 4326))""",
                          (now - timedelta(days=8),))
        recent = {r for (r,) in self.conn.execute(
            """select distinct route_id from obs.vehicle_position where route_id is not null and ts > %s
               union select route_id from obs.trip_route_match where service_date >= %s""",
            (now - timedelta(days=7), (now - timedelta(days=8)).date())).fetchall()}
        active = {r for (r,) in self.conn.execute("select route_id from core.transit_route where active")}
        self.assertEqual(tr.dormant_routes(self.conn, now), active - recent)


if __name__ == "__main__":
    unittest.main()
