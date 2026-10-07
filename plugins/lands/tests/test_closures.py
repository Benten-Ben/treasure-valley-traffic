"""Offline tests for the lands plugin's shared closure helpers (ingest/closures.py).

Run: python3 -m unittest discover -s plugins/lands/tests -t .
Geometries here are made up.
"""

import types
import unittest
from datetime import date, datetime, timedelta, timezone

from ingest import arcgis, db, http
from plugins.lands.ingest import closures

UTC = timezone.utc


def square(x0, y0, x1, y1, clockwise=True):
    ring = [[x0, y0], [x0, y1], [x1, y1], [x1, y0], [x0, y0]]          # clockwise (x east, y north)
    return ring if clockwise else ring[::-1]


class FakeConn:
    """Answers execute() calls in order with the given fetchone() values."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        value = self.answers.pop(0)
        return types.SimpleNamespace(fetchone=lambda: value)


class PolygonTest(unittest.TestCase):
    def test_one_clockwise_ring_is_a_polygon_written_counter_clockwise(self):
        g = closures.esri_polygon({"rings": [square(-116.0, 43.0, -115.9, 43.1)]})
        self.assertEqual(g["type"], "Polygon")
        self.assertEqual(len(g["coordinates"]), 1)
        self.assertGreater(arcgis._area([tuple(p) for p in g["coordinates"][0]]), 0)   # RFC 7946: CCW outside

    def test_several_outer_rings_with_holes_become_a_multipolygon(self):
        big, small = square(-116.0, 43.0, -115.8, 43.2), square(-115.5, 43.0, -115.4, 43.1)
        hole = square(-115.95, 43.05, -115.9, 43.1, clockwise=False)
        g = closures.esri_polygon({"rings": [small, hole, big]})
        self.assertEqual(g["type"], "MultiPolygon")
        holes = sorted(len(p) - 1 for p in g["coordinates"])
        self.assertEqual(holes, [0, 1])
        with_hole = next(p for p in g["coordinates"] if len(p) == 2)
        self.assertEqual(with_hole[0][0], [-116.0, 43.0])                    # the hole went to the big ring
        self.assertLess(arcgis._area([tuple(p) for p in with_hole[1]]), 0)  # holes clockwise

    def test_a_hole_goes_to_the_smallest_ring_around_it(self):
        outer, island = square(-116.0, 43.0, -115.0, 44.0), square(-115.8, 43.2, -115.2, 43.8)
        lake = square(-115.9, 43.1, -115.1, 43.9, clockwise=False)
        pond = square(-115.6, 43.4, -115.4, 43.6, clockwise=False)
        g = closures.esri_polygon({"rings": [outer, lake, island, pond]})
        by_size = sorted(g["coordinates"], key=lambda p: abs(arcgis._area([tuple(c) for c in p[0]])))
        self.assertEqual([len(p) for p in by_size], [2, 2])              # island with pond, outer with lake
        self.assertEqual(by_size[0][1][0], [-115.6, 43.4])

    def test_a_hole_outside_every_outer_ring_keeps_its_area(self):
        g = closures.esri_polygon({"rings": [square(-116.0, 43.0, -115.9, 43.1),
                                             square(-115.0, 43.0, -114.9, 43.1, clockwise=False)]})
        self.assertEqual(g["type"], "MultiPolygon")
        self.assertEqual([len(p) for p in g["coordinates"]], [1, 1])

    def test_counter_clockwise_only_rings_are_outer_rings(self):
        g = closures.esri_polygon({"rings": [square(-116.0, 43.0, -115.9, 43.1, clockwise=False),
                                             square(-115.0, 43.0, -114.9, 43.1, clockwise=False)]})
        self.assertEqual((g["type"], len(g["coordinates"])), ("MultiPolygon", 2))

    def test_bad_rings_are_dropped_and_open_rings_closed(self):
        self.assertIsNone(closures.esri_polygon({"rings": []}))
        self.assertIsNone(closures.esri_polygon({"rings": [[[0, 0], [1, 1], [0, 0]]]}))   # no area
        self.assertIsNone(closures.esri_polygon(None))
        g = closures.esri_polygon({"rings": [square(-116.0, 43.0, -115.9, 43.1)[:-1] + [[float("nan"), 1.0]]]})
        ring = g["coordinates"][0]
        self.assertEqual((len(ring), ring[0]), (5, ring[-1]))

    def test_lines_and_points_use_the_shared_reader(self):
        self.assertEqual(closures.geojson({"paths": [[[-116.0, 43.0, 5], [-115.9, 43.1, 5]]]}),
                         {"type": "LineString", "coordinates": [[-116.0, 43.0], [-115.9, 43.1]]})
        self.assertEqual(closures.geojson({"x": -116.0, "y": 43.0})["type"], "Point")
        self.assertIsNone(closures.geojson(None))
        self.assertIsNone(closures.geojson({"curveRings": []}))


class CombineAndRingTest(unittest.TestCase):
    def test_combine(self):
        p = {"type": "Polygon", "coordinates": [square(0, 0, 1, 1)]}
        mp = {"type": "MultiPolygon", "coordinates": [[square(2, 2, 3, 3)], [square(4, 4, 5, 5)]]}
        self.assertEqual(closures.combine([p]), p)
        self.assertEqual(closures.combine([p, None, mp])["type"], "MultiPolygon")
        self.assertEqual(len(closures.combine([p, mp])["coordinates"]), 3)
        line = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
        self.assertEqual(closures.combine([line, line]),
                         {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[0, 0], [1, 1]]]})
        self.assertEqual(closures.combine([p, line])["type"], "GeometryCollection")
        self.assertIsNone(closures.combine([None]))

    def test_in_ring(self):
        inside = {"type": "Point", "coordinates": [-116.2, 43.6]}
        outside = {"type": "Point", "coordinates": [-114.5, 45.0]}
        straddles = {"type": "LineString", "coordinates": [[-115.7, 43.0], [-115.0, 43.0]]}
        self.assertTrue(closures.in_ring(inside))
        self.assertFalse(closures.in_ring(outside))
        self.assertTrue(closures.in_ring(straddles))
        self.assertFalse(closures.in_ring(None))
        self.assertTrue(closures.in_ring({"type": "GeometryCollection", "geometries": [outside, inside]}))
        self.assertEqual(closures.RING, (-117.30, 42.90, -115.60, 44.30))


class SnapshotTest(unittest.TestCase):
    def test_the_ring_cut_and_unreadable_geometries(self):
        features = [
            {"attributes": {"k": "a", "n": 2}, "geometry": {"x": -116.2, "y": 43.6}},
            {"attributes": {"k": "a", "n": 1}, "geometry": {"x": -116.1, "y": 43.6}},
            {"attributes": {"k": "far"}, "geometry": {"x": -110.0, "y": 40.0}},
            {"attributes": {"k": "curved"}, "geometry": {"curveRings": [[[-116.0, 43.0]]]}},
            {"attributes": {"k": "none"}, "geometry": None},
        ]
        counts = {}
        groups = closures.snapshot(features, lambda a: a["k"], counts)
        self.assertEqual(sorted(groups), ["a", "curved", "none"])
        self.assertEqual(counts, {"outside the ring": 1, "without a geometry": 2})
        self.assertEqual([p[0]["n"] for p in groups["a"]],
                         [p[0]["n"] for p in closures.snapshot(features[1::-1], lambda a: a["k"])["a"]])


class FieldTest(unittest.TestCase):
    def test_merge_keeps_shared_fields_once_and_the_rest_per_part(self):
        a = {"objectid": 1, "ordernum": "0402-01-122", "acres": 361, "Shape__Area": 1.5, "Creator": "someone",
             "Editor": "someone", "GlobalID": "x"}
        b = {"objectid": 2, "ordernum": "0402-01-122", "acres": 201, "Shape__Length": 2.5}
        ga = {"type": "Polygon", "coordinates": [square(0, 0, 1, 1)]}
        gb = {"type": "Polygon", "coordinates": [square(2, 2, 3, 3)]}
        payload = closures.merge([(a, ga), (b, gb)])
        self.assertEqual(payload["ordernum"], "0402-01-122")
        self.assertNotIn("acres", payload)
        self.assertEqual(sorted(p["acres"] for p in payload["_parts"]), [201, 361])
        flat = str(payload)
        for gone in ("objectid", "Shape__", "Creator", "Editor", "someone"):
            self.assertNotIn(gone, flat)
        self.assertTrue(all(p["_geom"] for p in payload["_parts"]))
        # The same features renumbered and in another order: the same version.
        again = closures.merge([({**b, "objectid": 9}, gb), ({**a, "objectid": 8}, ga)])
        self.assertEqual(db.version_hash(again), db.version_hash(payload))
        # A moved polygon: a new version.
        moved = {"type": "Polygon", "coordinates": [square(2, 2, 3.1, 3)]}
        self.assertNotEqual(db.version_hash(closures.merge([(a, ga), (b, moved)])), db.version_hash(payload))

    def test_pick_total_and_text_span(self):
        payload = {"x": 1, "_parts": [{"n": 2, "d": "8/1/2026", "e": "Indefinite"}, {"n": None, "d": None, "e": "9/1/2026"}]}
        self.assertEqual(closures.pick(payload, "x"), 1)
        self.assertEqual(closures.pick(payload, "n"), 2)
        self.assertEqual(closures.total(payload, "n"), 2)
        self.assertIsNone(closures.total(payload, "nothing"))
        self.assertEqual(closures.text_span(payload, ("d",), ("e",)), (date(2026, 8, 1), None))   # one end open
        closed = {"_parts": [{"e": "9/1/2026"}, {"e": "10/31/2026 unless rescinded"}]}
        self.assertEqual(closures.text_span(closed, ("d",), ("e",)), (None, date(2026, 10, 31)))
        self.assertEqual(closures.text_span({"d": "1/2/2026", "e": None, "f": "3/4/2026"}, ("d",), ("e", "f")),
                         (date(2026, 1, 2), date(2026, 3, 4)))

    def test_kind_and_order_numbers_and_sentences(self):
        self.assertEqual(closures.kind_of("Closure Order", "Safety Closure"), "closure")
        self.assertEqual(closures.kind_of("Restriction/Prohibition Order", "Recreation Restriction"), "restriction")
        self.assertEqual(closures.kind_of("Public Use Exclusion"), "closure")
        self.assertEqual(closures.kind_of("OHV Exclusion", "Example OHV Prohibition Areas"), "restriction")
        self.assertEqual(closures.kind_of(None, ""), "restriction")
        self.assertEqual(closures.order_numbers("Forest Order 0402-01-122", "replaces 0402-01-114, -115 and 0402-01-122"),
                         ["0402-01-122", "0402-01-114"])
        self.assertEqual(closures.sentence("Deer Point Closure (", " Purpose. ", None), "Deer Point Closure. Purpose.")
        self.assertIsNone(closures.sentence(None, " "))


class DateTest(unittest.TestCase):
    def test_text_days(self):
        self.assertEqual(closures.text_day("8/13/2026"), date(2026, 8, 13))
        self.assertEqual(closures.text_day(" 12/31/2026 unless rescinded"), date(2026, 12, 31))
        self.assertEqual(closures.text_day("3/26/2027 (annual renewal expected)"), date(2027, 3, 26))
        self.assertEqual(closures.text_day("9/1/26"), date(2026, 9, 1))
        self.assertEqual(closures.text_day("2026-09-19"), date(2026, 9, 19))
        for v in ("Indefinite", "Until Amended", "", None, "13/40/2026", "Dec. 1 - Apr. 1", "8/13/20261"):
            self.assertIsNone(closures.text_day(v), v)

    def test_utc_days(self):
        self.assertEqual(closures.utc_day(1789819200000), date(2026, 9, 19))      # 12:00 UTC, as USFS writes them
        self.assertEqual(closures.utc_day(1749686400000), date(2025, 6, 12))      # 00:00 UTC
        self.assertIsNone(closures.utc_day(None))

    def test_declared_runs_over_local_days_with_the_end_day_included(self):
        start, end, fixes = closures.declared(date(2026, 9, 19), date(2026, 12, 31))
        self.assertEqual(start, datetime(2026, 9, 19, 6, tzinfo=UTC))           # midnight MDT
        self.assertEqual(end, datetime(2027, 1, 1, 7, tzinfo=UTC))              # midnight MST after Dec 31
        self.assertEqual(fixes, [])
        self.assertEqual(closures.declared(None, date(2026, 12, 31))[0], None)
        self.assertEqual(closures.declared(date(2026, 9, 19), None)[1], None)

    def test_a_rescind_date_ends_it_early_and_a_bad_end_is_dropped(self):
        _, end, fixes = closures.declared(date(2026, 9, 19), date(2026, 12, 31), rescinded=date(2026, 10, 5))
        self.assertEqual((end, fixes), (datetime(2026, 10, 5, 6, tzinfo=UTC), ["ended_by_rescind_date"]))
        _, end, fixes = closures.declared(date(2026, 9, 19), date(2026, 12, 31), rescinded=date(2027, 2, 1))
        self.assertEqual((end, fixes), (datetime(2027, 1, 1, 7, tzinfo=UTC), []))
        _, end, fixes = closures.declared(date(2026, 9, 19), date(2026, 9, 1))
        self.assertEqual((end, fixes), (None, ["end_before_start"]))


class GateTest(unittest.TestCase):
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)

    def test_needs_read(self):
        last = self.now - timedelta(hours=3)
        self.assertTrue(closures.needs_read(self.now - timedelta(days=4), None, self.now))         # never read
        self.assertTrue(closures.needs_read(None, last, self.now))                                # no edit date
        self.assertTrue(closures.needs_read(self.now - timedelta(hours=1), last, self.now))       # edited since
        self.assertTrue(closures.needs_read(last - timedelta(minutes=5), last, self.now))         # within the skew
        self.assertFalse(closures.needs_read(last - timedelta(hours=1), last, self.now))          # unchanged
        self.assertTrue(closures.needs_read(last - timedelta(days=9), self.now - timedelta(hours=24), self.now))

    def test_layer_metadata(self):
        info = {"editingInfo": {"lastEditDate": 1791008460862, "dataLastEditDate": 1791008400000},
                "fields": [{"name": "OrderNum"}, {"name": "x"}]}
        self.assertEqual(closures.edited_at(info), datetime(2026, 10, 3, 6, 20, tzinfo=UTC))
        self.assertEqual(closures.edited_at({"editingInfo": {"lastEditDate": 1791008460000}}).minute, 21)
        self.assertIsNone(closures.edited_at({}))
        self.assertEqual(closures.missing_fields(info, ("ordernum", "y")), ["y"])

    def test_the_host_is_paced(self):
        self.assertGreaterEqual(http.PACE_S[closures.HOST], 2.0)


class GuardTest(unittest.TestCase):
    def test_a_full_or_growing_snapshot_passes(self):
        self.assertIsNone(closures.check_drop(FakeConn((4,)), "s", 10, 2))
        self.assertIsNone(closures.check_drop(FakeConn((0,)), "s", 10, 0))       # nothing active, nothing found
        self.assertIsNone(closures.check_drop(FakeConn((0,)), "s", 10, 7))

    def test_a_big_drop_is_refused_until_seen_twice(self):
        with self.assertRaises(RuntimeError):
            closures.check_drop(FakeConn((5,), None), "s", 10, 2)                # no earlier read
        with self.assertRaises(RuntimeError):
            closures.check_drop(FakeConn((5,), (True, 5)), "s", 10, 2)           # last read was fine
        with self.assertRaises(RuntimeError):
            closures.check_drop(FakeConn((5,), (False, 1)), "s", 10, 2)          # refused, another count
        with self.assertRaises(RuntimeError):
            closures.check_drop(FakeConn((1,), None), "s", 10, 0)                # emptied
        conn = FakeConn((5,), (False, 2))
        self.assertIn("seen twice", closures.check_drop(conn, "s", 10, 2))
        self.assertEqual(conn.calls[1][1], ("s", 10))


if __name__ == "__main__":
    unittest.main()
