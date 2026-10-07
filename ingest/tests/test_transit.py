"""Offline tests for the Valley Regional Transit sources.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import io
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone

from ingest import route_colors
from ingest.sources import vrt_gtfs, vrt_realtime


def tiny_gtfs():
    files = {
        "feed_info.txt": "feed_publisher_name,feed_version\nETA,457\n",
        "routes.txt": "route_id,route_short_name,route_long_name,route_color\n9,9,State Street,76C043\n7,7,Fairview,76C043\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id,block_id,shape_id\n"
                     "9,wk,t1,Downtown,0,b1,s9\n7,wk,t2,Towne Square,1,b2,s7\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nA,Main Street Station,43.6152,-116.2036\nB,State & 27th,43.6290,-116.2240\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                          "t1,08:00:00,08:00:00,B,1\nt1,08:10:00,08:10:00,A,2\nt2,09:00:00,09:00:00,A,1\n",
        "shapes.txt": "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                      "s9,43.6290,-116.2240,2\ns9,43.6152,-116.2036,1\ns7,43.6152,-116.2036,1\ns7,43.6100,-116.2700,2\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, "﻿" + text)                      # VRT's files start with a BOM
    return buf.getvalue()


class StaticFeedTest(unittest.TestCase):
    def test_parse(self):
        feed = vrt_gtfs.parse_feed(tiny_gtfs())
        self.assertEqual(feed["version"], "457")
        self.assertEqual({r["short_name"] for r in feed["routes"]}, {"9", "7"})
        self.assertEqual(feed["routes"][0]["gtfs_color"], "#76c043")
        stops = {s["stop_id"]: s for s in feed["stops"]}
        self.assertEqual(stops["A"]["route_ids"], ["7", "9"])        # served by both
        s9 = next(s for s in feed["shapes"] if s["shape_id"] == "s9")
        self.assertEqual(s9["route_id"], "9")
        self.assertEqual(s9["coords"][0], (-116.2036, 43.6152))      # sorted by sequence

    def test_route_order_puts_numbers_in_numeric_order(self):
        routes = [{"route_id": x, "short_name": x, "sort_order": None} for x in ("R1", "10", "2", "9")]
        self.assertEqual(vrt_gtfs.route_order(routes), ["2", "9", "10", "R1"])


class ColorTest(unittest.TestCase):
    """The route palette as vrt_gtfs uses it (ingest/route_colors.py; the rest is in test_route_colors.py)."""

    def test_neighbors_differ_and_existing_colors_stay(self):
        nb = {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b"}, "d": set()}
        colors, _ = route_colors.assign(["a", "b", "c", "d"], nb, {"a": "#e34948"})
        self.assertEqual(colors["a"], "#e34948")
        self.assertEqual(len({colors["a"], colors["b"], colors["c"]}), 3)
        self.assertEqual(set(colors), {"a", "b", "c", "d"})

    def test_neighbors_avoid_confusable_colors(self):
        orange = "#eb6834"
        colors, _ = route_colors.assign(["a", "b"], {"a": {"b"}, "b": {"a"}}, {"a": orange})
        self.assertFalse(route_colors.clash(colors["a"], colors["b"]))
        self.assertNotIn(colors["b"], {orange, "#eda100", "#e87ba4", "#008300", "#e34948"})

    def test_too_many_mutual_neighbors_still_colors_everyone(self):
        routes = [str(i) for i in range(13)]                     # 13 routes all sharing streets
        nb = {r: set(routes) - {r} for r in routes}
        colors, _ = route_colors.assign(routes, nb, {})
        self.assertEqual(len(colors), 13)
        self.assertEqual(len(set(colors.values())), 13)          # every color used

    def test_badge_text_reads_on_the_color(self):
        self.assertEqual(route_colors.badge_text_color("#4a3aa7"), "#ffffff")       # violet: white text
        self.assertEqual(route_colors.badge_text_color("#eda100"), route_colors.INK)  # yellow: ink text

    def test_vrt_gtfs_uses_the_13_slot_palette(self):
        self.assertIs(vrt_gtfs.route_colors, route_colors)
        self.assertEqual(len(route_colors.PALETTE), 13)
        for gone in ("CONFUSABLE", "clash", "assign_colors", "ROUTE_PALETTE"):
            self.assertFalse(hasattr(vrt_gtfs, gone), gone)


class RealtimeTest(unittest.TestCase):
    LOOKUP = {"trips": {"164422": "9"}, "short": {"9": "9", "3": "3"}}

    def test_resolve_route(self):
        r = vrt_realtime.resolve_route
        self.assertEqual(r("x", "7", self.LOOKUP), "7")                          # the feed's own route_id wins
        self.assertEqual(r("164422", "", self.LOOKUP), "9")                       # scheduled trip
        self.assertEqual(r("1_-_Regular_Service-Weekday-3-A-TO-1345-d2ecfe6", "", self.LOOKUP), "3")
        self.assertIsNone(r("182273", "", self.LOOKUP))                           # numeric live ID: unknown
        self.assertIsNone(r("", "", self.LOOKUP))

    def test_parse_positions(self):
        from google.transit import gtfs_realtime_pb2 as pb
        feed = pb.FeedMessage()
        feed.header.gtfs_realtime_version = "1.0"
        feed.header.timestamp = 1791229990
        e = feed.entity.add(id="1")
        v = e.vehicle
        v.vehicle.id, v.vehicle.label = "706", "706"
        v.trip.trip_id = "1_-_Regular_Service-Weekday-9-A-TO-1345-abc1234"
        v.position.latitude, v.position.longitude, v.position.bearing = 43.62143, -116.2149, 305.0
        v.timestamp = 1791229982
        v.stop_id, v.current_stop_sequence = "AB617", 12
        feed.entity.add(id="2").vehicle.vehicle.id = "707"                  # no position: skipped
        feed_ts, rows = vrt_realtime.parse_positions(feed.SerializeToString(), self.LOOKUP)
        self.assertEqual(feed_ts, datetime.fromtimestamp(1791229990, timezone.utc))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["vehicle_id"], row["route_id"], row["stop_sequence"]), ("706", "9", 12))
        self.assertEqual(row["ts"], datetime.fromtimestamp(1791229982, timezone.utc))
        self.assertAlmostEqual(row["bearing"], 305.0)
        self.assertIsNone(row["speed_ms"])                                      # not sent: stays null

    def test_archive_layout_matches_the_recorder(self):
        when = datetime(2026, 10, 5, 20, 0, 34, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            path = vrt_realtime.write_archive(root, "position_updates", b"x", when)
            self.assertEqual(os.path.relpath(path, root),
                             os.path.join("vrt-gtfs-rt", "2026-10-05", "position_updates-200034Z.pb"))
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"x")


if __name__ == "__main__":
    unittest.main()


class RouteMatchTest(unittest.TestCase):
    def test_clear_match(self):
        from ingest import transit_match as tm
        self.assertEqual(tm.decide(50, {"7": 45, "40": 15}), ("7", 0.9, "40", 0.3))

    def test_short_or_ambiguous_trips_stay_unlabeled(self):
        from ingest import transit_match as tm
        self.assertIsNone(tm.decide(8, {"7": 8}))                   # too few fixes
        self.assertIsNone(tm.decide(44, {"7": 25, "40": 22}))       # 57% vs 50%: routes share the street
        self.assertIsNone(tm.decide(40, {"7": 20}))                 # only half the trip is on any route
        self.assertIsNone(tm.decide(40, {}))

    def test_a_lone_route_needs_no_runner_up(self):
        from ingest import transit_match as tm
        self.assertEqual(tm.decide(20, {"28": 20}), ("28", 1.0, None, None))
