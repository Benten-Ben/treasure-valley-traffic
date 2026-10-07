"""Tests for the lane-inventory ingestors: itd_hpms, achd_msm, compass_centerline,
and the ArcGIS pager they share (ingest/arcgis.py).

Fixtures are synthetic: made-up IDs, names and coordinates. The parsing tests
are offline. The store tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (a clone migrated through 0011); each works inside one
transaction and rolls it back.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import contextlib
import json
import os
import re
import unittest
import urllib.parse
from datetime import datetime, timezone
from unittest import mock

import http.client

from ingest import arcgis, db
from ingest.db import version_hash
from ingest.sources import achd_msm, achd_roads, compass_centerline, itd_hpms

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def geojson_line(x0=-119.5, y0=43.3, dx=0.0, dy=0.003):
    return {"type": "LineString", "coordinates": [[x0, y0], [x0 + dx, y0 + dy]]}


# --- the pager ---------------------------------------------------------------

class BoxServer:
    """A layer cut to a box, as ITD's server serves it: the ID list (by extent) includes
    `outside`, rows the box query itself never returns; by ID, every row comes back.
    Answers at most `cap` features, in ID order; `lose` drops rows altogether."""

    def __init__(self, ids, outside=(), cap=4, lose=(), oid_field="OBJECTID", flag=True):
        self.ids, self.outside, self.cap, self.lose = list(ids), set(outside), cap, set(lose)
        self.oid_field, self.asked, self.flag = oid_field, [], flag      # flag: say when an answer is cut

    def get(self, url):
        self.asked.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if q.get("returnIdsOnly") == ["true"]:
            body = {"objectIdFieldName": self.oid_field, "objectIds": self.ids[::-1]}
        else:
            if "objectIds" in q:
                listed = {int(i) for i in q["objectIds"][0].split(",")}
                sel = [i for i in sorted(self.ids) if i in listed]
            else:
                lo, hi = (int(t) for t in re.findall(r"(?:>=|<=) (\d+)", q["where"][0]))
                sel = [i for i in sorted(self.ids) if lo <= i <= hi and i not in self.outside]
            sel = [i for i in sel if i not in self.lose]
            body = {"exceededTransferLimit": self.flag and len(sel) > self.cap,
                    "features": [{"attributes": {self.oid_field: i},
                                  "geometry": {"paths": [[[-119.5, 43.3], [-119.5, 43.301]]]}} for i in sel[:self.cap]]}
        return 200, json.dumps(body).encode(), "no_rules"


def query(url):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


class PagerTest(unittest.TestCase):
    def fetch(self, server, **kw):
        stats = {}
        out = arcgis.fetch_layer("https://example.invalid/FeatureServer/9", "test", get=server.get,
                                 sleep=lambda s: None, stats=stats, **kw)
        return out, stats

    def test_a_box_layer_comes_whole_with_the_rows_outside_fetched_by_id(self):
        server = BoxServer(range(1, 10), outside=[3, 9], cap=4)
        (features, nbytes, status, robots), stats = self.fetch(server, box=itd_hpms.BOX, batch=4, precision=6,
                                                              where="Kind = 'x'")
        self.assertEqual([f["attributes"]["OBJECTID"] for f in features], list(range(1, 10)))
        self.assertEqual(stats, {"listed": 9, "by_id": 2})
        q = [query(u) for u in server.asked]
        self.assertEqual((q[0]["returnIdsOnly"], q[0]["geometry"], q[0]["spatialRel"], q[0]["where"]),
                         (["true"], ["-117.05,43.0,-115.95,43.85"], ["esriSpatialRelIntersects"], ["Kind = 'x'"]))
        self.assertEqual(q[1]["where"], ["(Kind = 'x') AND OBJECTID >= 1 AND OBJECTID <= 4"])
        self.assertEqual((q[1]["geometry"], q[1]["outSR"], q[1]["geometryPrecision"], q[1]["f"]),
                         (["-117.05,43.0,-115.95,43.85"], ["4326"], ["6"], ["json"]))
        by_id = q[-1]                                         # by ID, without the box
        self.assertEqual((by_id["objectIds"], "geometry" in by_id, "where" in by_id), (["3,9"], False, False))
        line = arcgis.esri_feature(features[0])
        self.assertEqual((line["properties"], line["geometry"]["type"]), ({"OBJECTID": 1}, "LineString"))

    def test_paging_stops_once_every_listed_id_is_in(self):
        server = BoxServer(range(1, 10), cap=4)
        (features, *_), stats = self.fetch(server, batch=4)
        self.assertEqual((len(features), len(server.asked), stats["by_id"]), (9, 1 + 3, 0))

    def test_listed_rows_that_never_arrive_fail_the_fetch(self):
        with self.assertRaises(RuntimeError):
            self.fetch(BoxServer(range(1, 10), outside=[9], lose=[9]), box=itd_hpms.BOX, batch=4)

    def test_too_many_ids_and_server_errors_fail(self):
        with self.assertRaises(RuntimeError):
            self.fetch(BoxServer(range(1, 10)), max_features=8)

        def broken(url):
            return 200, json.dumps({"error": {"code": 400, "message": "bad"}}).encode(), "no_rules"
        with self.assertRaises(RuntimeError):
            arcgis.fetch_layer("https://example.invalid/0", "test", get=broken, sleep=lambda s: None)

    def test_answers_cut_at_the_servers_page_size_shrink_the_batch(self):
        # The server answers at most 1,000 rows; we asked for 2,000. Nothing should go by ID.
        for flag in (True, False):
            server = BoxServer(range(1, 12151), cap=1000, flag=flag)
            (features, *_), stats = self.fetch(server, batch=2000)
            self.assertEqual((len(features), stats["by_id"], len(server.asked)), (12150, 0, 1 + 13), msg=flag)
            self.assertFalse([u for u in server.asked if "objectIds" in u])

    def test_a_cut_off_answer_is_retried(self):
        for broken in (b'{"features": [{"attri', http.client.IncompleteRead(b"")):
            server, calls = BoxServer(range(1, 4)), []

            def flaky(url):
                calls.append(url)
                if len(calls) == 2:
                    if isinstance(broken, Exception):
                        raise broken
                    return 200, broken, "no_rules"
                return server.get(url)
            features, *_ = arcgis.fetch_layer("https://example.invalid/0", "test", get=flaky, sleep=lambda s: None)
            self.assertEqual((len(features), len(calls)), (3, 3))

    def test_esri_geometry_becomes_geojson(self):
        g = arcgis.esri_geometry
        self.assertEqual(g({"paths": [[[1, 2, 9], [3, 4, 9]]]}), {"type": "LineString", "coordinates": [[1, 2], [3, 4]]})
        self.assertEqual(g({"paths": [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]}),
                         {"type": "MultiLineString", "coordinates": [[[1, 2], [3, 4]], [[5, 6], [7, 8]]]})
        self.assertEqual(g({"x": 1, "y": 2}), {"type": "Point", "coordinates": [1.0, 2.0]})
        self.assertIsNone(g({"x": None, "y": None}))
        self.assertIsNone(g({"paths": []}))
        self.assertIsNone(g(None))

    def test_a_reset_connection_is_retried(self):
        calls = []

        def flaky(url):
            calls.append(url)
            if len(calls) == 1:
                raise ConnectionResetError("reset by peer")
            return 200, b"{}", "no_rules"
        self.assertEqual(arcgis.get_with_retries("https://example.invalid", "test", flaky, waits=(0,),
                                                 sleep=lambda s: None)[0], 200)
        self.assertEqual(len(calls), 2)

    def test_cleaners(self):
        self.assertEqual([arcgis.to_int(v) for v in ("5", " 3 ", 4.0, "", " ", "No Funded Improvement", None, 2.5)],
                         [5, 3, 4, None, None, None, None, None])
        self.assertEqual(arcgis.to_float(-3e-08, 5), 0.0)
        self.assertEqual(str(arcgis.to_float(-3e-08, 5)), "0.0")                     # not -0.0
        self.assertEqual(arcgis.esri_date(1767225600000), datetime(2026, 1, 1, tzinfo=timezone.utc))
        a = geojson_line()
        b = {"type": "LineString", "coordinates": [[-119.5000001, 43.3], [-119.5, 43.3030000004]]}
        self.assertEqual(arcgis.geom_digest(a), arcgis.geom_digest(b))              # float noise
        self.assertNotEqual(arcgis.geom_digest(a), arcgis.geom_digest(geojson_line(dx=0.001)))


# --- ITD HPMS ----------------------------------------------------------------

def hpms(event_id, route="09990AOH000", frm=0.0, to=1.0, oid=1, geom=None, **values):
    props = {"OBJECTID": oid, "EventID": event_id, "RouteID": route, "FromDate": 1483228800000, "ToDate": None,
             "FromMeasure": frm, "ToMeasure": to, "EstablishedDate": None, "SystemModifyDate": 1735689600000,
             "LocError": "NO ERROR", "GlobalID": f"{{G-{oid}}}", "RouteSystemCode": "OH", "RouteSystemNumber": 0,
             "Shape__Length": 1609.3 * (to - frm), **values}
    return {"type": "Feature", "geometry": geom or geojson_line(), "properties": props}


def through(event_id, total, asc, desc, **kw):
    return hpms(event_id, ThroughLanes=total, Ascending_Lanes=asc, Descending_Lanes=desc, ThroughLanesSource=0, **kw)


class HpmsTest(unittest.TestCase):
    def test_codes_become_labels(self):
        row = itd_hpms.section("median", {"EventID": "e1", "RouteID": "09990AOH000", "FromMeasure": 1.25,
                                          "MedianType": 3, "MedianWidth": 15, "MedianTypeSource": 2})
        self.assertEqual((row["source_id"], row["event_id"], row["from_mi"]), ("e1@09990AOH000:1.2500", "e1", 1.25))
        self.assertEqual((row["median_type"], row["median_width_ft"], row["value_source"]),
                         ("curbed", 15.0, "imagery_manual"))
        self.assertEqual(itd_hpms.section("access_control", {"AccessControl": 1})["access_control"], "full")
        self.assertEqual(itd_hpms.section("facility_type", {"FacilityType": 6})["facility_type"],
                         "non_inventory_direction")
        self.assertEqual(itd_hpms.section("shoulders", {"ShoulderType": 7, "ShoulderWidthLeft": 2,
                                                        "ShoulderWidthRight": 8})["shoulder_type"], "barrier_curb")
        self.assertEqual(itd_hpms.section("facility_type", {"FacilityType": 9})["facility_type"], "code_9")
        turns = itd_hpms.section("turn_lanes", {"TurnLanesLeft": 2, "TurnLanesRight": 4})
        self.assertEqual((turns["turn_lanes_left"], turns["turn_lanes_right"]), (2, 4))   # HPMS codes kept
        self.assertEqual(itd_hpms.TURN_LANES[turns["turn_lanes_left"]], "multiple_exclusive")
        lanes = itd_hpms.section("through_lanes", {"RouteID": "09990DSH099", "ThroughLanes": 0,
                                                   "Ascending_Lanes": 0, "Descending_Lanes": 2,
                                                   "ThroughLanesSource": 0})
        self.assertEqual((lanes["direction"], lanes["lanes_descending"], lanes["value_source"]), ("D", 2, "unknown"))

    def test_zero_lane_rows_on_shared_stretches_are_skipped(self):
        records, rows, counts = itd_hpms.parse_layer("through_lanes", [
            through("shared", 0, 0, 0), through("both", 2, 1, 1),
            through("d-route", 0, 0, 2, route="09990DUS099")], NOW)
        self.assertEqual(len(records), 3)                                 # all kept in raw
        self.assertEqual(sorted(r["event_id"] for r in rows.values()), ["both", "d-route"])   # a D row's 0 total
        self.assertEqual(counts["zero-lane rows skipped"], 1)                                # isn't "zero lanes"
        # Other layers keep their zeros.
        _, rows, _ = itd_hpms.parse_layer("peak_lanes", [hpms("p", PeakLanes=0, CounterPeakLanes=0)], NOW)
        self.assertEqual([r["event_id"] for r in rows.values()], ["p"])

    def test_an_event_in_several_pieces_keeps_every_piece(self):
        records, rows, counts = itd_hpms.parse_layer("turn_lanes", [
            hpms("ev", frm=10.1234567, to=12.3456789, oid=1, TurnLanesLeft=3, TurnLanesRight=4),
            hpms("ev", frm=13.5555555, to=15.7777777, oid=2, TurnLanesLeft=3, TurnLanesRight=4),
            hpms(None, frm=2.0, to=3.0, oid=3, TurnLanesLeft=5, TurnLanesRight=5)], NOW)
        self.assertEqual(sorted(rows), ["@09990AOH000:2.0000", "ev@09990AOH000:10.1235", "ev@09990AOH000:13.5556"])
        self.assertEqual((counts["events in several pieces"], counts["no EventID"]), (1, 1))
        self.assertIsNone(rows["@09990AOH000:2.0000"]["event_id"])

    def test_expired_and_duplicate_rows(self):
        old = through("old", 2, 1, 1)
        old["properties"]["ToDate"] = 1700000000000
        records, rows, counts = itd_hpms.parse_layer("through_lanes", [old, through("x", 2, 1, 1),
                                                                       through("x", 4, 2, 2, oid=2)], NOW)
        self.assertEqual((len(records), [r["event_id"] for r in rows.values()]), (2, ["x"]))
        self.assertEqual((counts["expired"], counts["duplicate pieces skipped"]), (1, 1))

    def test_a_and_d_routes_read_as_a_divided_road(self):
        a = {"route_id": "09990AUS099", "direction": "A", "through_lanes": 2, "lanes_ascending": 2,
             "lanes_descending": 0, "share": 1.0}
        d = {"route_id": "09990DUS099", "direction": "D", "through_lanes": 0, "lanes_ascending": 0,
             "lanes_descending": 2, "share": 0.9}
        self.assertEqual(itd_hpms.carriageway_lanes([a, d]),
                         {"ascending": 2, "descending": 2, "divided": True, "conflict": False})
        # ITD codes a divided highway's inventory direction as a two-way roadway (I-84): it still pairs.
        self.assertEqual(itd_hpms.carriageway_lanes([a, d], facility="two_way"),
                         {"ascending": 2, "descending": 2, "divided": True, "conflict": False})
        # An A row with lanes both ways is an undivided road: the D row on its line is a placeholder.
        a_both = {**a, "lanes_ascending": 1, "lanes_descending": 1}
        placeholder = {**d, "lanes_descending": 2}
        for facility in (None, "two_way"):
            self.assertEqual(itd_hpms.carriageway_lanes([a_both, placeholder], facility),
                             {"ascending": 1, "descending": 1, "divided": False, "conflict": False})
        # A one-way facility has no other direction; one whose row claims both ways is a conflict.
        self.assertEqual(itd_hpms.carriageway_lanes([a, d], facility="ramp"),
                         {"ascending": 2, "descending": 0, "divided": False, "conflict": False})
        self.assertEqual(itd_hpms.carriageway_lanes([a_both], facility="one_way"),
                         {"ascending": 1, "descending": 0, "divided": False, "conflict": True})
        # A D route of another highway never pairs: the other direction is unknown.
        other_d = {**d, "route_id": "08880DSH088"}
        self.assertEqual(itd_hpms.carriageway_lanes([a, other_d]),
                         {"ascending": 2, "descending": None, "divided": False, "conflict": False})
        self.assertEqual(itd_hpms.carriageway_lanes([d]),
                         {"ascending": None, "descending": 2, "divided": True, "conflict": False})

    def test_a_republish_with_new_object_ids_adds_no_versions(self):
        first = through("e1", 4, 2, 2, oid=11, frm=3.14159265, to=4.27182818)
        again = through("e1", 4, 2, 2, oid=987, frm=3.1415926, to=4.271828181)       # renumbered, measure noise
        again["properties"]["Shape__Length"] = 1812.3457
        again["properties"]["GlobalID"] = "{G-NEW}"
        (r1,), _, _ = itd_hpms.parse_layer("through_lanes", [first], NOW)
        (r2,), _, _ = itd_hpms.parse_layer("through_lanes", [again], NOW)
        self.assertEqual(r1[0], r2[0])
        self.assertEqual(version_hash(r1[1]), version_hash(r2[1]))
        self.assertNotIn("OBJECTID", r1[1])
        changed = through("e1", 6, 3, 3, oid=987)
        moved = through("e1", 4, 2, 2, oid=11, frm=3.14159265, to=4.27182818, geom=geojson_line(dx=0.001))
        self.assertNotEqual(version_hash(r1[1]), version_hash(itd_hpms.parse_layer("through_lanes", [changed], NOW)[0][0][1]))
        self.assertNotEqual(version_hash(r1[1]), version_hash(itd_hpms.parse_layer("through_lanes", [moved], NOW)[0][0][1]))

    def test_road_names_join_by_route_and_measure_overlap(self):
        def name(eid, route, frm, to, text):
            return {"type": "Feature", "geometry": geojson_line(),
                    "properties": {"OBJECTID": 1, "EventID": eid, "RouteID": route, "FromMeasure": frm,
                                   "ToMeasure": to, "ToDate": None, "FullRoadName": text}}
        _, index = itd_hpms.parse_names([name("n1", "09990AOH000", 0, 0.3, "Sample Ave"),
                                         name("n2", "09990AOH000", 0.3, 2.0, "N 9th Ave"),
                                         name("n3", "09990DOH000", 0, 5, "Other Rd")], NOW)
        self.assertEqual(itd_hpms.road_name(index, "09990AOH000", 0.2, 1.5), "N 9th Ave")
        self.assertEqual(itd_hpms.road_name(index, "09990AOH000", 0.0, 0.25), "Sample Ave")
        self.assertEqual(itd_hpms.road_name(index, "09990AOH000", 0.1, 0.1), "Sample Ave")     # zero-length row
        self.assertIsNone(itd_hpms.road_name(index, "09990AOH000", 3.0, 4.0))
        self.assertIsNone(itd_hpms.road_name(index, "07770AOH000", 0.0, 1.0))


# --- ACHD Master Street Map ----------------------------------------------------

def msm(gid, code="SA1", name="SAMPLE RD", exist="5", funded="No Funded Improvement", planned="7", typ="AR",
        typo="Residential Arterial", oid=1, edited=1767225600000, geom=None, **extra):
    props = {"OBJECTID": oid, "StreetCode": code, "StreetName": name, "StreetTypo": typo, "ExistLane": exist,
             "PlanLane_C": funded, "PlanLane_P": planned, "ROWProject": "No Planned Improvement",
             "ROWPreserv": "100", "Parking": " ", "Typology": typ, "RelatStudy": " ", "Other_Rela": None,
             "Comments": " ", "GlobalID": gid, "created_date": edited, "last_edited_date": edited,
             "Shape__Length": 1234.5, **extra}
    return {"type": "Feature", "geometry": geom or geojson_line(), "properties": props}


class MsmTest(unittest.TestCase):
    def test_blanks_and_no_improvement_become_null(self):
        row = achd_msm.arterial(msm("g1")["properties"])
        self.assertIsNone(row["funded_lanes"])
        self.assertIsNone(row["row_project"])
        self.assertIsNone(row["parking"])
        self.assertIsNone(row["comments"])
        self.assertEqual(row["row_preservation"], "100")
        self.assertEqual(achd_msm.arterial(msm("g2", exist=" ")["properties"])["existing_lanes"], None)

    def test_lane_strings_become_integers(self):
        self.assertEqual([achd_msm.lanes(v) for v in ("5", " 3 ", "0", " ", "", None, "No Funded Improvement",
                                                       "TBD")],
                         [5, 3, 0, None, None, None, None, None])
        row = achd_msm.arterial(msm("g1", exist="5", funded="7", planned="7")["properties"])
        self.assertEqual((row["existing_lanes"], row["funded_lanes"], row["planned_lanes"]), (5, 7, 7))

    def test_typology_codes_become_names(self):
        self.assertEqual(achd_msm.typology("AR"), "Residential Arterial")
        self.assertEqual(achd_msm.typology("ATC", "Trasitional/Commercial Arterial"), "Transitional/Commercial Arterial")
        self.assertEqual(achd_msm.typology("N_MA", "Mobility Arterial(New)"), "Mobility Arterial (new road)")
        self.assertEqual(achd_msm.typology("STATE", "STATE"), "State Highway")
        self.assertEqual(achd_msm.typology("ZZ", "Some  New Kind"), "Some New Kind")     # unknown: the row's own text
        self.assertEqual(achd_msm.typology(" ", "Under Study"), "Under Study")
        row = achd_msm.arterial(msm("g1", typ="n_anr")["properties"])
        self.assertEqual((row["typology_code"], row["typology"]), ("N_ANR", "Neighborhood Residential Arterial (new road)"))

    def test_bulk_stamped_dates_are_not_versioned(self):
        (a,), _, _ = achd_msm.parse([msm("g1", oid=1, edited=1767225600000)])
        (b,), rows, _ = achd_msm.parse([msm("g1", oid=77, edited=1798761600000)])
        self.assertEqual(version_hash(a[1]), version_hash(b[1]))
        self.assertEqual(rows["g1"]["source_edited"], arcgis.esri_date(1798761600000))   # still kept in core
        (c,), _, _ = achd_msm.parse([msm("g1", exist="7")])
        self.assertNotEqual(version_hash(a[1]), version_hash(c[1]))

    def test_the_many_new_ids_guard(self):
        old = {f"old{i}" for i in range(10)}
        self.assertFalse(arcgis.is_republish(set(), {"a"}))                             # first run
        self.assertFalse(arcgis.is_republish(old, old | {"new1"}))                      # one new street
        self.assertFalse(arcgis.is_republish(old, {f"old{i}" for i in range(6)} | {f"new{i}" for i in range(4)}))
        self.assertTrue(arcgis.is_republish(old, {"old0"} | {f"new{i}" for i in range(9)}))

    def test_republished_rows_pair_with_their_old_ids(self):
        old = {"o1": ("SA1", "line1"), "o2": ("SA2", "line2"), "o3": ("SA3", "line3"), "o4": ("DUP", "line4"),
               "o5": ("DUP", "line5"), "o6": (None, "line6")}
        new = {"n1": ("SA1", "line1"),           # same code and line
               "n2": ("SA2", "line2-moved"),     # unique code, line edited
               "n3": ("SA3-X", "line3"),         # code renamed, same line
               "n4": ("DUP", "line4b"),          # code used twice on each side, line changed: can't tell
               "n5": ("DUP", "line5b"),
               "n6": (None, "line6")}            # no code, same line
        self.assertEqual(arcgis.pair_republished(old, new), {"n1": "o1", "n2": "o2", "n3": "o3", "n6": "o6"})


# --- COMPASS RegionalCenterline ----------------------------------------------

def centerline(pm_id, oid=1, **over):
    props = {"objectid": oid, "l_addfrom": 101, "l_addto": 199, "r_addfrom": 100, "r_addto": 198, "stpredir": "N",
             "stprefix": None, "stname": "Sample", "stsuffix": "Rd", "stpostdir": None, "stpostmod": None,
             "strtconcat": "N Sample Rd", "l_commname": "XYZ", "r_commname": "XYZ", "l_zip4": "00000",
             "r_zip4": "00000", "permid": 4242, "postspeed": 35, "emergspeed": 35, "oneway": None,
             "funcclass": "Minor Arterial", "private": None, "county": "Canyon", "pm_id": pm_id, "direction": None,
             "majorroad": "Y", "state": 0, "lanes": 3, "impact": "Sampletown", "check_": None, "city": "Sampletown",
             "miles": 0.051234567, "dup": None, "globalid": f"{{C-{oid}}}", "Shape__Length": 300.12,
             "jurisd": "City of Sampletown"}
    props.update(over)
    return {"type": "Feature", "geometry": geojson_line(), "properties": props}


class CompassTest(unittest.TestCase):
    def test_parsing(self):
        records, rows, counts = compass_centerline.parse([
            centerline("Sam100001", oid=1),
            centerline("Sam100001", oid=2, permid=0, lanes=2),                    # another piece of the same link
            centerline("Sam100002", oid=3, strtconcat=" ", lanes=0, oneway="F", postspeed=0),
            centerline("#NYA", oid=4),
            centerline("Sam100009", oid=1),                                        # the same globalid again
            centerline("Sam100010", oid=5, globalid=None)])
        self.assertEqual(sorted(rows), ["{C-1}", "{C-2}", "{C-3}", "{C-4}"])
        self.assertEqual(len(records), 4)
        self.assertEqual((counts["duplicate globalids skipped"], counts["no globalid"], counts["no pm_id"]), (1, 1, 1))
        r = rows["{C-1}"]
        self.assertEqual((r["global_id"], r["pm_id"], r["name"], r["county"], r["functional_class"],
                          r["posted_speed_mph"], r["lanes"], r["one_way"]),
                         ("{C-1}", "Sam100001", "N Sample Rd", "Canyon", "Minor Arterial", 35, 3, "both"))
        self.assertEqual(r["attributes"]["permid"], 4242)
        self.assertEqual(r["attributes"]["miles"], 0.05123)
        for gone in ("objectid", "globalid", "Shape__Length", "lanes", "pm_id", "stprefix"):
            self.assertNotIn(gone, r["attributes"])
        self.assertEqual((rows["{C-2}"]["pm_id"], rows["{C-2}"]["lanes"]), ("Sam100001", 2))
        self.assertNotIn("permid", rows["{C-2}"]["attributes"])                     # 0 means none
        r3 = rows["{C-3}"]
        self.assertEqual((r3["name"], r3["lanes"], r3["one_way"], r3["posted_speed_mph"]),
                         ("N Sample Rd", None, "forward", None))                  # name rebuilt from its parts
        self.assertIsNone(rows["{C-4}"]["pm_id"])
        self.assertEqual([compass_centerline.one_way(v) for v in ("T", "TF", "FT", "B", " ", "N")],
                         ["backward", "backward", "forward", "both", "both", "N"])

    def test_a_renumbered_piece_adds_no_versions(self):
        (a,), _, _ = compass_centerline.parse([centerline("Sam1", oid=1)])
        (b,), _, _ = compass_centerline.parse([centerline("Sam1", oid=5, globalid="{C-1}", Shape__Length=300.13,
                                                          miles=0.0512345671)])
        self.assertEqual(version_hash(a[1]), version_hash(b[1]))


# --- ACHD roads changing: rematch everything ------------------------------------

class FakeFetch:
    def __init__(self, conn, source):
        self.id, self.started_at = 1, NOW

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class MatchInsideFetchTest(unittest.TestCase):
    def test_a_failing_match_fails_the_fetch_so_the_store_rolls_back(self):
        exits = []

        class Fetch(FakeFetch):
            def __exit__(self, exc_type, *rest):
                exits.append(exc_type)
                return False

        for module, stored in ((achd_msm, {"arterials": 1}), (compass_centerline, {"pieces": 1}),
                               (itd_hpms, {"sections": 1})):
            with contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(arcgis, "fetch_layer", return_value=([], 0, 200, "no_rules")))
                stack.enter_context(mock.patch.object(itd_hpms, "fetch_all", return_value=({}, [], 0)))
                stack.enter_context(mock.patch.object(module, "store", return_value=(stored, 1)))
                stack.enter_context(mock.patch.object(db, "ensure_source"))
                stack.enter_context(mock.patch.object(db, "Fetch", Fetch))
                stack.enter_context(mock.patch.object(module, "match", side_effect=RuntimeError("boom")))
                with self.assertRaises(RuntimeError):
                    module.run(object())
        self.assertEqual(exits, [RuntimeError] * 3)


class AchdRoadsRematchTest(unittest.TestCase):
    def run_roads(self, stats):
        with mock.patch.object(achd_roads, "fetch_all", return_value=([], 0, "no_rules")), \
                mock.patch.object(achd_roads, "store", return_value=dict(stats)), \
                mock.patch.object(achd_roads.db, "ensure_source"), mock.patch.object(achd_roads.db, "Fetch", FakeFetch), \
                mock.patch.object(achd_roads.segment_match, "rematch_all",
                                  return_value={"itd_hpms": {"matched lines": 3}, "osm_valley": {"ways matched": 2}}) as rm:
            return achd_roads.run(object()), rm

    def test_a_run_that_changes_the_segments_rematches_every_source(self):
        stats, rm = self.run_roads({"segments": 5, "record versions new": 1, "removed": 0, "retired": 0})
        self.assertEqual(rm.call_args.kwargs, {"only_stale": False})
        self.assertEqual((stats["itd_hpms rematched"], stats["osm_valley rematched"]), (3, 2))
        for change in ("removed", "retired"):
            self.assertTrue(achd_roads.changed({change: 2}))

    def test_an_unchanged_run_rematches_only_what_is_out_of_date(self):
        stats, rm = self.run_roads({"segments": 5, "record versions new": 0, "unchanged": 5, "removed": 0, "retired": 0})
        self.assertEqual(rm.call_args.kwargs, {"only_stale": True})


# --- storing (database) --------------------------------------------------------

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through 0011")
class StoreTest(unittest.TestCase):
    """Each test runs in one transaction that's rolled back. Stores retire rows they
    don't see, so real rows in the clone are retired too until the rollback."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)
        if not cls.conn.execute("select to_regclass('core.hpms_section') is not null").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("core.hpms_section is missing: apply migration 0011")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def fetch_row(self, source):
        from ingest import db
        db.ensure_source(self.conn, source)
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, now(), true) returning id",
                                 (source["name"],)).fetchone()[0]

    def empty_hpms(self):
        """Start from no HPMS rows at all (rolled back), and a fetch to log them under."""
        c = self.conn
        for kind in [*itd_hpms.LAYERS, "road_names"]:
            db.ensure_source(c, itd_hpms.layer_source(kind))
        c.execute(r"delete from raw.record where source like 'itd\_hpms\_%%'")
        c.execute("delete from core.hpms_section")
        return self.fetch_row(itd_hpms.SOURCE)

    LAYER_VALUES = {"turn_lanes": {"TurnLanesLeft": 2, "TurnLanesRight": 4}, "lane_width": {"LaneWidth": 12},
                    "median": {"MedianType": 3}, "shoulders": {"ShoulderType": 2}, "access_control": {"AccessControl": 3},
                    "peak_lanes": {"PeakLanes": 2}, "facility_type": {"FacilityType": 2}}

    def hpms_layers(self, through_rows=1):
        layers = {k: [hpms(f"test-{k}", route="09990AUS099", oid=10 + i, **v)]
                  for i, (k, v) in enumerate(self.LAYER_VALUES.items())}
        layers["through_lanes"] = [through(f"test-e{i}", 4, 2, 2, route="09990AUS099", oid=100 + i, frm=i, to=i + 1)
                                   for i in range(through_rows)]
        names = [{"type": "Feature", "geometry": geojson_line(),
                  "properties": {"EventID": "test-n1", "RouteID": "09990AUS099", "FromMeasure": 0, "ToMeasure": 9,
                                 "ToDate": None, "FullRoadName": "Sample Blvd"}}]
        return layers, names

    def test_hpms_store_and_a_republish(self):
        c = self.conn
        fid = self.empty_hpms()
        layers, names = self.hpms_layers()
        layers["through_lanes"].append(through("test-zero", 0, 0, 0, route="09990AUS099", oid=2, frm=5, to=6))
        t1 = datetime(2026, 10, 6, 1, tzinfo=timezone.utc)
        stats, changed = itd_hpms.store(c, fid, t1, layers, names)
        self.assertEqual((stats["sections"], stats["zero-lane rows skipped"], stats["record versions new"]), (8, 1, 9))
        row = c.execute("""select route_id, direction, through_lanes, lanes_ascending, road_name, ST_GeometryType(geom)
                           from core.hpms_section where kind = 'through_lanes' and event_id = 'test-e0'""").fetchone()
        self.assertEqual(row, ("09990AUS099", "A", 4, 2, "Sample Blvd", "ST_MultiLineString"))
        # The same records renumbered: no new versions, rows kept.
        for features in layers.values():
            for f in features:
                f["properties"]["OBJECTID"] += 1000
        t2 = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)
        stats, changed = itd_hpms.store(c, fid, t2, layers, names)
        self.assertEqual((stats["record versions new"], stats["unchanged"], changed), (0, 9, 0))
        self.assertEqual(c.execute("""select count(*) from core.hpms_section
                                      where event_id like 'test-%%' and active and last_seen = %s""", (t2,)).fetchone()[0], 8)

    def test_a_short_or_empty_hpms_layer_is_refused(self):
        c = self.conn
        fid = self.empty_hpms()
        layers, names = self.hpms_layers(through_rows=4)
        itd_hpms.store(c, fid, datetime(2026, 10, 6, 1, tzinfo=timezone.utc), layers, names)
        t2 = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)
        for cut in ("short", "empty", "no names"):
            layers, names = self.hpms_layers(through_rows=1 if cut == "short" else 4)
            if cut == "empty":
                layers["median"] = []
            if cut == "no names":
                names = []
            with self.assertRaises(RuntimeError, msg=cut):
                itd_hpms.store(c, fid, t2, layers, names)
        self.assertEqual(c.execute("select count(*) from core.hpms_section where active").fetchone()[0], 4 + 7)

    def test_a_short_or_empty_msm_or_compass_layer_is_refused(self):
        c = self.conn
        c.execute("delete from raw.record where source in ('achd_msm', 'compass_centerline')")
        c.execute("delete from core.msm_arterial")
        c.execute("delete from core.segment_match where source = 'compass_centerline'")
        c.execute("delete from core.compass_segment")
        t1, t2 = datetime(2026, 10, 6, 1, tzinfo=timezone.utc), datetime(2026, 10, 7, 1, tzinfo=timezone.utc)
        fid = self.fetch_row(achd_msm.SOURCE)
        feats = [msm(f"{{M-{i}}}", code=f"SA{i}") for i in range(4)]
        achd_msm.store(c, fid, t1, feats)
        for cut in ([], feats[:1]):
            with self.assertRaises(RuntimeError):
                achd_msm.store(c, fid, t2, cut)
        fid = self.fetch_row(compass_centerline.SOURCE)
        pieces = [centerline(f"Sam{i}", oid=i) for i in range(4)]
        compass_centerline.store(c, fid, t1, pieces)
        with self.assertRaises(RuntimeError):
            compass_centerline.store(c, fid, t2, pieces[:1])
        self.assertEqual(c.execute("select count(*) from core.msm_arterial where active").fetchone()[0], 4)

    def test_msm_republish_carries_rows_over(self):
        c = self.conn
        c.execute("delete from raw.record where source = 'achd_msm'")       # start from an empty layer (rolled back)
        c.execute("delete from core.msm_arterial")
        fid = self.fetch_row(achd_msm.SOURCE)
        feats = [msm(f"{{OLD-{i}}}", code=f"SA{i}", geom=geojson_line(x0=-119.5 + i * 0.01)) for i in range(4)]
        t1 = datetime(2026, 10, 6, 1, tzinfo=timezone.utc)
        achd_msm.store(c, fid, t1, feats)
        ids = dict(c.execute("select street_code, id from core.msm_arterial").fetchall())
        for i, f in enumerate(feats):                                        # ACHD republishes: every GlobalID new
            f["properties"]["GlobalID"] = f"{{NEW-{i}}}"
            f["properties"]["OBJECTID"] += 100
        t2 = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)
        stats, changed = achd_msm.store(c, fid, t2, feats)
        self.assertEqual((stats["republish: rows carried over"], stats["retired"]), (4, 0))
        after = dict(c.execute("select street_code, id from core.msm_arterial where active").fetchall())
        self.assertEqual(after, ids)                                         # same rows, new keys
        self.assertEqual(c.execute("select count(*) from core.msm_arterial where global_id like '{NEW-%'").fetchone()[0], 4)

    def test_compass_pieces_of_one_link_are_separate_rows(self):
        c = self.conn
        if not c.execute("""select exists (select 1 from information_schema.columns where table_schema = 'core'
                            and table_name = 'compass_segment' and column_name = 'global_id')""").fetchone()[0]:
            self.skipTest("core.compass_segment.global_id is missing: apply migration 0016")
        c.execute("delete from raw.record where source = 'compass_centerline'")     # an empty layer (rolled back)
        c.execute("delete from core.segment_match where source = 'compass_centerline'")
        c.execute("delete from core.compass_segment")
        fid = self.fetch_row(compass_centerline.SOURCE)
        feats = [centerline("Sam100001", oid=1, lanes=3), centerline("Sam100001", oid=2, lanes=2)]
        stats, _ = compass_centerline.store(c, fid, datetime(2026, 10, 6, 1, tzinfo=timezone.utc), feats)
        self.assertEqual((stats["pieces"], stats["pm_ids"]), (2, 1))
        rows = c.execute("""select global_id, lanes from core.compass_segment where pm_id = 'Sam100001'
                            order by global_id""").fetchall()
        self.assertEqual(rows, [("{C-1}", 3), ("{C-2}", 2)])


if __name__ == "__main__":
    unittest.main()
