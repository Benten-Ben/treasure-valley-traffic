"""Offline tests for the 511 Idaho API stream. Every record here is made up,
in the shapes 511's API documents (no 511 data in the repository).

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import csv
import io
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from ingest.sources import idaho511_api as api

UTC = timezone.utc


def event(**kw):
    e = {"ID": 101, "SourceId": "9001", "Organization": "ERS", "RoadwayName": "Test Rd",
         "DirectionOfTravel": "Both Directions", "Description": " Road construction on Test Rd. ",
         "Reported": 1791000000, "LastUpdated": 1791300000, "StartDate": 1791000000, "PlannedEndDate": None,
         "LanesAffected": "All lanes closed", "Latitude": 43.6, "Longitude": -116.2,
         "LatitudeSecondary": None, "LongitudeSecondary": None, "EventType": "closures",
         "EventSubType": "roadConstruction", "IsFullClosure": True, "Severity": "Major", "Comment": None,
         "EncodedPolyline": None, "Restrictions": {"Width": None, "Height": None, "Length": 65.0, "Weight": None,
                                                   "Speed": None},
         "DetourPolyline": "", "DetourInstructions": "", "Recurrence": None, "RecurrenceSchedules": [],
         "Cause": "roadwork"}
    e.update(kw)
    return e


def camera(cid, source, lat, lon, views, location="Test Site", sort=1):
    return {"Id": cid, "Source": source, "SourceId": f"{cid}.C1", "Roadway": "SH-0", "Direction": "Unknown",
            "Latitude": lat, "Longitude": lon, "Location": location, "SortOrder": sort,
            "Views": [{"Id": vid, "Url": f"https://example.invalid/{vid}", "Status": st, "Description": ""}
                      for vid, st in views]}


class ParseTest(unittest.TestCase):
    def test_polyline_decodes_googles_example(self):
        self.assertEqual(api.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@"),
                         [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]])

    def test_geometry_prefers_the_line_and_falls_back_to_the_point(self):
        self.assertEqual(api.geometry(event())["type"], "Point")
        self.assertEqual(api.geometry(event(EncodedPolyline="_p~iF~ps|U_ulLnnqC"))["type"], "LineString")
        multi = api.geometry({"EncodedPolyline": ["_p~iF~ps|U_ulLnnqC", "_ulLnnqC_mqNvxq`@"]})
        self.assertEqual(multi["type"], "MultiLineString")
        self.assertIsNone(api.geometry({"Latitude": 0, "Longitude": 0}))

    def test_event_row(self):
        r = api.event_row(event())
        self.assertEqual((r["source_id"], r["kind"], r["severity"]), ("101", "closure", "Major"))
        self.assertEqual(r["start"], datetime.fromtimestamp(1791000000, UTC))
        self.assertIsNone(r["end"])
        self.assertEqual(r["description"], "Road construction on Test Rd.")
        self.assertEqual(r["attributes"]["restrictions"], {"Length": 65.0})
        self.assertEqual(r["attributes"]["ers_id"], "9001")
        self.assertEqual(api.event_row(event(EventType="accidentsAndIncidents"))["kind"], "incident")
        self.assertEqual(api.event_row(event(), "truck_restriction")["kind"], "truck_restriction")
        self.assertIsNone(api.event_row(event(PlannedEndDate=1700000000))["end"])        # ends before it starts

    def test_alert_row(self):
        r = api.alert_row({"Id": 7, "Message": "Chain law in effect", "Notes": None, "StartTime": 1791000000,
                           "EndTime": 1791100000, "LastUpdated": 1791000000, "Regions": ["North"],
                           "HighImportance": True, "SendNotification": False})
        self.assertEqual((r["kind"], r["severity"], r["description"]), ("advisory", "high", "Chain law in effect"))

    def test_readings_parse_and_tolerate_gaps(self):
        r = api.reading_row({"Id": 5, "LastUpdated": 1791301500, "AirTemperature": "51.3", "SurfaceTemperature": None,
                             "WindSpeed": "7.6", "WindDirection": "N", "RelativeHumidity": "44",
                             "Precipitation": "No Precipitation", "Visibility": "N/A", "IcePercent": "0",
                             "SurfaceStatus": "Dry", "Status": "Normal"})
        self.assertEqual((r["station_id"], r["air_temp_f"], r["wind_speed"], r["relative_humidity"]), ("5", 51.3, 7.6, 44.0))
        self.assertEqual((r["surface_temp_f"], r["visibility"], r["ice_percent"]), (None, None, 0.0))
        self.assertEqual((r["wind_direction"], r["precipitation"], r["surface_status"]), ("N", "No Precipitation", "Dry"))
        self.assertIsNone(api.number("NaN"))

    def test_blank_signs(self):
        self.assertIsNone(api.sign_messages({"Messages": ["NO_MESSAGE"]}))
        self.assertIsNone(api.sign_messages({"Messages": []}))
        self.assertEqual(api.sign_messages({"Messages": [" CRASH AHEAD ", "NO_MESSAGE", "USE CAUTION"]}),
                         ["CRASH AHEAD", "USE CAUTION"])

    def test_sign_timestamps_dont_count_as_a_change(self):
        a = [{"Id": "S1", "Messages": ["NO_MESSAGE"], "LastUpdated": 1}]
        b = [{"Id": "S1", "Messages": ["NO_MESSAGE"], "LastUpdated": 2}]
        self.assertEqual(api.content_digest("messagesigns", a), api.content_digest("messagesigns", b))
        self.assertNotEqual(api.content_digest("event", a), api.content_digest("event", b))


class CaptureListTest(unittest.TestCase):
    cams = [
        camera(1, "RWIS", 44.9, -114.0, [(11, "Enabled"), (12, "Enabled"), (13, "Disabled")], "Far Pass", sort=2),
        camera(2, "RWIS", 43.5, -116.5, [(21, "Enabled")], "Valley Station", sort=1),
        camera(3, "ODOT", 44.0, -116.9, [(31, "Enabled")], "Inside Ring, OR"),
        camera(4, "ODOT", 42.4, -117.9, [(41, "Enabled")], "Outside Ring, OR"),
        camera(5, "ACHD", 43.6, -116.2, [(51, "Enabled")], "City Camera"),
    ]

    def test_road_weather_views_statewide_and_oregon_views_in_the_ring(self):
        rows = api.regional_list(self.cams)
        self.assertEqual([(i, n) for i, n, _ in rows],
                         [(21, "Valley Station (road weather view 1)"), (31, "Inside Ring, OR (ODOT)"),
                          (11, "Far Pass (road weather view 1)"), (12, "Far Pass (road weather view 2)")])

    def test_the_list_is_rewritten_only_when_it_changes(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        rows = api.regional_list(self.cams)
        self.assertTrue(api.write_list(root, rows))
        self.assertFalse(api.write_list(root, rows))
        with open(os.path.join(root, api.LIST_FILE), newline="") as f:
            parsed = list(csv.DictReader(f))
        self.assertEqual(parsed[0], {"image_id": "21", "name": "Valley Station (road weather view 1)",
                                     "why": "ITD road-weather station camera, statewide"})
        self.assertTrue(api.write_list(root, rows[:2]))


class LimiterTest(unittest.TestCase):
    def test_never_more_than_n_calls_a_minute(self):
        clock = [0.0]
        lim = api.Limiter(n=8, per=60, gap=2, clock=lambda: clock[0], sleep=lambda s: clock.__setitem__(0, clock[0] + s))
        times = []
        for _ in range(20):
            lim.wait()
            times.append(clock[0])
        self.assertTrue(all(b - a >= 2 - 1e-9 for a, b in zip(times, times[1:])))
        self.assertTrue(all(sum(1 for t in times if s <= t < s + 60) <= 8 for s in times))


class ArchiveTest(unittest.TestCase):
    def test_path(self):
        self.assertEqual(api.archive_path("/a", "event", datetime(2026, 10, 6, 16, 30, 5, tzinfo=UTC)),
                         os.path.join("/a", "idaho511", "event", "2026-10-06", "event-163005Z.json.gz"))


if __name__ == "__main__":
    unittest.main()
