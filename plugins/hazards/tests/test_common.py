"""Tests for the hazards plugin's shared pieces (ingest/common.py) and its manifest. Offline.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import importlib
import json
import os
import re
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import manifest
from plugins.hazards.ingest import common

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
UTC = timezone.utc


def area2(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))


def cw(w, s, e, n):
    return [[w, s], [w, n], [e, n], [e, s], [w, s]]


def ccw(w, s, e, n):
    return [[w, s], [e, s], [e, n], [w, n], [w, s]]


class RingTest(unittest.TestCase):
    def test_the_ring_and_its_edges(self):
        self.assertEqual(common.RING, (-117.30, 42.90, -115.60, 44.30))
        self.assertTrue(common.in_ring(-116.2, 43.6))
        self.assertTrue(common.in_ring("-117.30", "42.90"))          # edges count
        self.assertTrue(common.in_ring(-115.60, 44.30))
        self.assertFalse(common.in_ring(-117.31, 43.6))
        self.assertFalse(common.in_ring(-116.2, 44.31))
        self.assertFalse(common.in_ring(None, 43.6))
        self.assertFalse(common.in_ring("x", "y"))


class TimeTest(unittest.TestCase):
    def test_iso_text_with_offsets_and_blanks(self):
        self.assertEqual(common.parse_time("2026-10-07T12:00:00-04:00"), datetime(2026, 10, 7, 16, tzinfo=UTC))
        self.assertEqual(common.parse_time("2026-10-07T16:00:00Z"), datetime(2026, 10, 7, 16, tzinfo=UTC))
        self.assertIsNone(common.parse_time(" "))
        self.assertIsNone(common.parse_time("soon"))
        self.assertEqual(common.iso(datetime(2026, 10, 7, 10, tzinfo=timezone(timedelta(hours=-6)))),
                         "2026-10-07T16:00:00Z")

    def test_an_end_before_the_start_is_dropped(self):
        a, b = datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC)
        self.assertEqual(common.declared(a, b), (a, b))
        self.assertEqual(common.declared(b, a), (b, None))
        self.assertEqual(common.declared(None, b), (None, None))


class PolygonTest(unittest.TestCase):
    def test_one_clockwise_ring_becomes_a_counter_clockwise_polygon(self):
        g = common.polygon_geojson([cw(-116.6, 43.4, -116.4, 43.5)])
        self.assertEqual(g["type"], "Polygon")
        self.assertEqual(len(g["coordinates"]), 1)
        self.assertGreater(area2(g["coordinates"][0]), 0)          # RFC 7946: exterior counter-clockwise

    def test_parts_and_a_hole_listed_last(self):
        g = common.polygon_geojson([cw(-116.6, 43.0, -116.4, 43.2), cw(-116.3, 43.0, -116.2, 43.1),
                                    ccw(-116.55, 43.05, -116.45, 43.15)])
        self.assertEqual(g["type"], "MultiPolygon")
        self.assertEqual([len(p) for p in g["coordinates"]], [2, 1])   # the hole went to the part around it
        shell, hole = g["coordinates"][0]
        self.assertGreater(area2(shell), 0)
        self.assertLess(area2(hole), 0)                                # holes clockwise
        self.assertEqual(hole[0][0], -116.55)

    def test_a_hole_goes_to_the_smallest_shell_around_it(self):
        g = common.polygon_geojson([cw(-117, 43, -116, 44), cw(-116.8, 43.2, -116.2, 43.8),
                                    ccw(-116.6, 43.4, -116.4, 43.6)])
        self.assertEqual([len(p) for p in g["coordinates"]], [1, 2])

    def test_rings_without_esri_winding_are_parts(self):
        g = common.polygon_geojson([ccw(-116.6, 43.4, -116.4, 43.5), ccw(-116.3, 43.4, -116.2, 43.5)])
        self.assertEqual(g["type"], "MultiPolygon")
        self.assertEqual([len(p) for p in g["coordinates"]], [1, 1])

    def test_unclosed_and_degenerate_rings(self):
        open_ring = cw(-116.6, 43.4, -116.4, 43.5)[:-1]
        g = common.polygon_geojson([open_ring, [[-116, 43], [-116, 43.1], [-116, 43]]])
        self.assertEqual(g["type"], "Polygon")
        self.assertEqual(g["coordinates"][0][0], g["coordinates"][0][-1])
        self.assertIsNone(common.polygon_geojson([]))
        self.assertIsNone(common.polygon_geojson(None))
        self.assertIsNone(common.esri_polygon({}))

    def test_merging_dedupes_and_keeps_a_stable_order(self):
        a = common.polygon_geojson([cw(-116.6, 43.4, -116.4, 43.5)])
        b = common.polygon_geojson([cw(-116.3, 43.4, -116.2, 43.5)])
        self.assertEqual(common.merge_polygons([a, b]), common.merge_polygons([b, a, a]))
        self.assertEqual(common.merge_polygons([a, a, None]), a)
        self.assertEqual(common.merge_polygons([a, b])["type"], "MultiPolygon")
        self.assertIsNone(common.merge_polygons([None]))


class ArcgisTest(unittest.TestCase):
    LAYER = "https://example.test/arcgis/rest/services/X/MapServer/1"

    def test_query_url_cuts_to_the_ring(self):
        q = dict(p.split("=", 1) for p in common.query_url(self.LAYER, geometry=False).split("?", 1)[1].split("&"))
        self.assertEqual(q["geometry"], "-117.3%2C42.9%2C-115.6%2C44.3")
        self.assertEqual((q["geometryType"], q["inSR"], q["outSR"], q["returnGeometry"]),
                         ("esriGeometryEnvelope", "4326", "4326", "false"))
        self.assertNotIn("geometryPrecision", q)
        self.assertIn("geometryPrecision=5", common.query_url(self.LAYER, precision=5))

    def answer(self, data):
        body = json.dumps(data).encode()
        return lambda url: (200, body, "no_rules")

    def test_one_request_whole(self):
        feats = [{"attributes": {"OBJECTID": 1}}]
        got = common.query_layer(self.LAYER, "t", get=self.answer({"features": feats}), sleep=lambda s: None)
        self.assertEqual(got[0], feats)
        self.assertEqual(got[2:], (200, "no_rules"))

    def test_a_cut_answer_fails_or_is_paged_by_id(self):
        cut = self.answer({"features": [{"attributes": {}}], "exceededTransferLimit": True})
        with self.assertRaises(RuntimeError):
            common.query_layer(self.LAYER, "t", get=cut, sleep=lambda s: None)
        with mock.patch("ingest.arcgis.fetch_layer", return_value=(["f1", "f2"], 10, 200, "no_rules")) as fl:
            got = common.query_layer(self.LAYER, "t", where="x = 1", get=cut, sleep=lambda s: None, page_by_id=True)
        self.assertEqual(got[0], ["f1", "f2"])
        self.assertEqual(fl.call_args.kwargs["where"], "x = 1")

    def test_an_arcgis_error_fails(self):
        with self.assertRaises(RuntimeError):
            common.query_layer(self.LAYER, "t", get=self.answer({"error": {"code": 400}}), sleep=lambda s: None)
        with self.assertRaises(RuntimeError):
            common.query_layer(self.LAYER, "t", get=self.answer({"count": 3}), sleep=lambda s: None)

    def test_clean_attributes(self):
        self.assertEqual(common.clean_attributes({"OBJECTID": 4, "a": None, "b": 0, "c": ""}, {"OBJECTID"}),
                         {"b": 0, "c": ""})


class FakeConn:
    def __init__(self, value):
        self.value = value

    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return (self.value,)


class SnapshotTest(unittest.TestCase):
    def test_a_small_or_empty_snapshot_is_refused(self):
        common.check_snapshot(FakeConn(6), "s", 3, "s")
        common.check_snapshot(FakeConn(0), "s", 1, "s")
        for n in (0, 2):
            with self.assertRaises(RuntimeError):
                common.check_snapshot(FakeConn(6), "s", n, "s")


class FireTest(unittest.TestCase):
    AT = datetime(2026, 10, 7, 12, tzinfo=UTC)

    def test_quiet_windows_and_size_classes(self):
        self.assertEqual([common.quiet_days(a) for a in (None, 0, 9.9, 10, 99, 100, 50000)], [3, 3, 3, 8, 8, 14, 14])
        self.assertEqual([common.size_class(a) for a in (None, 0.1, 0.25, 9.9, 10, 299, 300, 999, 1000, 4999, 5000)],
                         [None, "A", "B", "B", "C", "D", "E", "E", "F", "F", "G"])

    def test_open_until_out_withdrawn_or_quiet(self):
        recent = self.AT - timedelta(days=2)
        self.assertTrue(common.fire_open(None, True, recent, 1, self.AT))
        self.assertFalse(common.fire_open(self.AT, True, recent, 1, self.AT))          # out
        self.assertFalse(common.fire_open(None, False, recent, 1, self.AT))            # withdrawn
        self.assertFalse(common.fire_open(None, True, None, 1, self.AT))
        ten_days = self.AT - timedelta(days=10)
        self.assertFalse(common.fire_open(None, True, ten_days, 50, self.AT))          # 8-day window
        self.assertTrue(common.fire_open(None, True, ten_days, 400, self.AT))          # contained, still not out

    def row(self, sid, h=b"1"):
        return {"source_id": sid, "content_hash": h}

    def test_plan_new_fires(self):
        first, second = common.plan_lifecycles({}, {"a": (self.row("a"), True)})
        self.assertEqual(([r["source_id"] for r in first], [r["source_id"] for r in second]), (["a"], ["a"]))
        self.assertIsNone(common.plan_lifecycles({}, {"b": (self.row("b"), False)}))   # first seen already out

    def test_plan_nothing_changed(self):
        self.assertIsNone(common.plan_lifecycles({"a": (True, b"1")}, {"a": (self.row("a"), True)}))
        self.assertIsNone(common.plan_lifecycles({"a": (False, b"1")}, {"a": (self.row("a"), False)}))

    def test_plan_closing_and_reopening(self):
        first, second = common.plan_lifecycles({"a": (True, b"1"), "b": (True, b"1")},
                                               {"a": (self.row("a"), True), "b": (self.row("b", b"2"), False)})
        self.assertEqual(sorted(r["source_id"] for r in first), ["a", "b"])            # b's final state written
        self.assertEqual([r["source_id"] for r in second], ["a"])                      # then b closed
        first, second = common.plan_lifecycles({"c": (False, b"1")}, {"c": (self.row("c", b"2"), False)})
        self.assertEqual(([r["source_id"] for r in first], second), (["c"], []))      # out date learned late
        first, second = common.plan_lifecycles({"d": (False, b"1")}, {"d": (self.row("d", b"2"), True)})
        self.assertEqual([r["source_id"] for r in second], ["d"])                      # live again

    def test_an_active_event_without_a_row_is_closed(self):
        self.assertEqual(common.plan_lifecycles({"a": (True, b"1")}, {}), ([], []))

    def test_event_hash_ignores_sub_metre_noise(self):
        row = {"source_id": "x", "kind": "k", "geom": {"type": "Point", "coordinates": [-116.1234561, 43.1]},
               "start": None, "attributes": {"a": 1}}
        same = {**row, "geom": {"type": "Point", "coordinates": [-116.1234559, 43.1]}}
        moved = {**row, "geom": {"type": "Point", "coordinates": [-116.1244, 43.1]}}
        self.assertEqual(common.event_hash(row), common.event_hash(same))
        self.assertNotEqual(common.event_hash(row), common.event_hash(moved))
        self.assertNotEqual(common.event_hash(row), common.event_hash({**row, "attributes": {"a": 2}}))


class ManifestTest(unittest.TestCase):
    def test_the_manifest_loads_and_matches_its_modules(self):
        plugin = manifest.load(PLUGIN)
        self.assertEqual((plugin.name, plugin.visibility, plugin.order, plugin.depends), ("hazards", "public", 60, []))
        self.assertEqual(plugin.manifest["tables"], ["raw.record", "evt.event"])
        names = []
        for entry in plugin.manifest["sources"]:
            m = importlib.import_module(f"plugins.hazards.{entry['module']}")
            self.assertEqual((m.SOURCE["name"], m.SOURCE["license"], m.SOURCE["credit"], entry["kind"]),
                             (entry["name"], entry["license"], entry["credit"], "source"))
            self.assertEqual(m.SOURCE["access"], "open")
            self.assertTrue(callable(m.run))
            names.append(entry["name"])
        self.assertEqual(names, ["idl_fire_restrictions", "nifc_wfigs_incidents", "nifc_wfigs_perimeters",
                                 "nasa_firms", "nws_wwa", "usgs_quakes"])

    def test_schedules_are_ten_minutes_or_more(self):
        units = {"minute": 1, "minutes": 1, "hour": 60, "hours": 60, "day": 1440, "days": 1440}
        for entry in manifest.load(PLUGIN).manifest["sources"]:
            s = importlib.import_module(f"plugins.hazards.{entry['module']}").SOURCE["schedule"]
            n, unit = re.fullmatch(r"(\d+) (\w+)", s).groups()
            self.assertGreaterEqual(int(n) * units[unit], 10, entry["name"])

    def test_no_source_points_at_a_disallowed_host(self):
        """Every URL a source module holds (its constants and SOURCE['url']): never api.weather.gov
        (robots.txt Disallow: /, ch. 17 Q13) nor USGS's new Water Data API (Q14)."""
        for entry in manifest.load(PLUGIN).manifest["sources"]:
            m = importlib.import_module(f"plugins.hazards.{entry['module']}")
            urls = [v for v in vars(m).values() if isinstance(v, str) and v.startswith("http")]
            urls += [m.SOURCE["url"]] + [f"{getattr(m, 'BASE', '')}/{p}" for _, p in getattr(m, "FILES", ())]
            self.assertTrue(urls)
            for url in urls:
                self.assertNotIn("api.weather.gov", url, entry["name"])
                self.assertNotIn("api.waterdata.usgs.gov", url, entry["name"])


if __name__ == "__main__":
    unittest.main()
