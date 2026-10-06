"""Tests for the signal and rail-crossing ingestors and the street-name helpers.

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL (a clone with migration 0011), inside a transaction
that is rolled back. All records below are synthetic: made-up crossing
numbers, streets and points.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone

from ingest import arcgis, db, signal_devices, streets
from ingest.db import version_hash
from ingest.sources import achd_signal_points as achd
from ingest.sources import compass_regional_signals as regional
from ingest.sources import compass_signals as compass
from ingest.sources import fra_crossings as fra


def fra_row(cid="999001A", **kw):
    row = {
        "crossingid": cid, "statecode": "16", "countycode": "16001", "revisiondate": "2025-03-01T00:00:00.000",
        "railroadname": "Example Valley Railroad", "railroadcode": "EXVR", "street": "TEST AVE", "cityname": "TESTVILLE",
        "crossingtype": "Public", "crossingposition": "At Grade", "crossingclosed": "No",
        "wdcode": "All other Gates", "countroadwaygatearms": "2", "countpedestriangatearms": "0",
        "highwaytrafficsignal": "No", "nearbyhighwaytrafficsignals": "Yes",
        "hwytrafficsgnlinterconncode": "2", "hwytrafficsgnlinterconn": "For Traffic Signals",
        "hwytrafficsgnlprecode": "2", "hwytrafficsgnlpre": "Advanced", "highwaytrafficpresignals": "No",
        "totaldaylightthrutrains": "3", "totalnighttimethrutrains": "1", "totalswitchingtrains": "0",
        "maximumtimetablespeed": "25", "numberofmaintracks": "1", "numberofsidingtracks": "1",
        "numberofyardtracks": "0", "trafficlane": "4", "annualaveragedailytrafficcount": "12000",
        "annualaveragedailytrafficyear": "2023", "latitude": "43.5", "longitude": "-116.4",
        "geocoded_lat_long": {"type": "Point", "coordinates": [-116.4, 43.5]},
        ":@computed_region_aaaa_1111": "7", ":@computed_region_bbbb_2222": "1234",
    }
    row.update(kw)
    return row


class FraTest(unittest.TestCase):
    def test_query_asks_for_ada_and_canyon_in_one_call(self):
        url = fra.query_url()
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(q["$where"], ["statecode='16' AND countycode in('16001','16027')"])
        self.assertEqual(q["$order"], ["crossingid"])
        self.assertNotIn(" ", url)

    def test_other_counties_and_states_are_dropped_closed_crossings_kept(self):
        parsed = fra.parse([fra_row("999001A"), fra_row("999002B", countycode="16055"),
                            fra_row("999003C", statecode="41", countycode="41045"),
                            fra_row("999004D", countycode="16027", crossingclosed="Yes", wdcode=None,
                                    countroadwaygatearms="0")])
        self.assertEqual(sorted(parsed), ["999001A", "999004D"])
        closed = fra.crossing(parsed["999004D"][0])
        self.assertTrue(closed["closed"])
        self.assertFalse(fra.crossing(parsed["999001A"][0])["closed"])

    def test_computed_region_columns_are_not_versioned(self):
        a = fra.parse([fra_row()])["999001A"][0]
        b = fra.parse([fra_row(**{":@computed_region_aaaa_1111": "8", ":@computed_region_cccc_3333": "5"})])["999001A"][0]
        self.assertFalse(any(k.startswith(":@computed_region") for k in a))
        self.assertEqual(version_hash(a), version_hash(b))
        self.assertNotEqual(version_hash(a), version_hash(fra.parse([fra_row(street="OTHER ST")])["999001A"][0]))

    def test_fields_become_typed_values(self):
        c = fra.crossing(fra.clean(fra_row()))
        self.assertEqual((c["warning"], c["gate_arms"], c["ped_gate_arms"]), ("gates", 2, 0))
        self.assertEqual((c["signal_controlled"], c["signal_nearby"], c["interconnected"], c["preemption"]),
                         (False, True, True, "Advance"))
        self.assertEqual((c["day_through_trains"], c["night_through_trains"], c["max_timetable_mph"]), (3, 1, 25))
        self.assertEqual((c["main_tracks"], c["other_tracks"], c["road_lanes"]), (1, 1, 4))
        self.assertEqual((c["fra_aadt"], c["fra_aadt_year"], c["revision_date"]), (12000, 2023, "2025-03-01"))
        self.assertTrue(c["public"])
        self.assertIsNone(fra.crossing(fra_row(hwytrafficsgnlprecode=None, hwytrafficsgnlpre=None))["preemption"])
        self.assertEqual(fra.crossing(fra_row(hwytrafficsgnlprecode="1", hwytrafficsgnlpre="Simultaneous"))["preemption"],
                         "Simultaneous")
        self.assertFalse(fra.crossing(fra_row(hwytrafficsgnlinterconncode="1",
                                              hwytrafficsgnlinterconn="Not Interconnected"))["interconnected"])
        self.assertIsNone(fra.crossing(fra_row(hwytrafficsgnlinterconncode=None, hwytrafficsgnlinterconn=None))["interconnected"])

    def test_warning_device_codes_and_labels(self):
        cases = {"Crossbucks": "crossbucks", "Stop signs": "stop_signs", "Flashing lights": "flashing_lights",
                 "Highway signals, bells": "highway_signals", "No signs or signals": "none", "8": "gates",
                 "9": "four_quad_gates", "Four Quad (Full Barrier) Gates": "four_quad_gates", "3": "crossbucks"}
        for code, want in cases.items():
            self.assertEqual(fra.warning({"wdcode": code}), want, code)
        self.assertEqual(fra.warning({"wdcode": None, "countroadwaygatearms": "2"}), "gates")
        self.assertEqual(fra.warning({"wdcode": None, "countflashinglightpair": "2"}), "flashing_lights")
        self.assertIsNone(fra.warning({"wdcode": None}))

    def test_geometry_falls_back_from_the_geocoded_point_to_lat_long_to_none(self):
        self.assertEqual(fra.geometry(fra_row())["coordinates"], [-116.4, 43.5])
        self.assertEqual(fra.geometry(fra_row(geocoded_lat_long=None, latitude="43.6", longitude="-116.2"))["coordinates"],
                         [-116.2, 43.6])
        self.assertIsNone(fra.geometry(fra_row(geocoded_lat_long=None, latitude="0", longitude="0")))
        self.assertIsNone(fra.geometry(fra_row(geocoded_lat_long=None, latitude=None, longitude=None)))

    def test_a_crossing_listed_twice_keeps_the_later_revision(self):
        parsed = fra.parse([fra_row(street="NEW NAME", revisiondate="2025-06-01T00:00:00.000"),
                            fra_row(street="OLD NAME", revisiondate="2024-01-01T00:00:00.000")])
        self.assertEqual(parsed["999001A"][0]["street"], "NEW NAME")


def esri(attrs, x=-116.3, y=43.6):
    return {"attributes": attrs, "geometry": {"x": x, "y": y} if x is not None else None}


class AchdSignalPointsTest(unittest.TestCase):
    def test_purpose_to_kind(self):
        cases = [("Traffic_Signals", "Traffic Signal", "signal_pole"), ("Traffic_Signals", "TS", "signal_pole"),
                 ("Pedestrian_Signals", "Hybrid Pedestrian Crossing", "ped_hybrid"),
                 ("Pedestrian_Signals", "Rectangular Rapid Flashing Beacon", "rrfb"),
                 ("Pedestrian_Signals", "Conventional Pedestrian Crossing", "ped_conventional"),
                 ("Pedestrian_Signals", "Advanced Warning Flashing Beacon", "warning_beacon"),
                 ("Pedestrian_Signals", None, "ped_conventional"),
                 ("School_Flasher_Signal", "SF", "school_flasher"), ("Fire_Signals", "Fire", "fire_signal")]
        for layer, purpose, want in cases:
            self.assertEqual(achd.kind(layer, purpose), want, (layer, purpose))

    def test_records_are_keyed_by_layer_and_objectid_and_points_converted(self):
        records, devices = achd.parse("Pedestrian_Signals", [
            esri({"OBJECTID": 7, "Purpose": "Hybrid Pedestrian Crossing"}, -116.30001234, 43.6),
            esri({"OBJECTID": 8, "Purpose": "RRFB"}, None),
            esri({"OBJECTID": 9, "Purpose": "RRFB"}, float("nan"), 43.6)])
        self.assertEqual([r[0] for r in records], ["Pedestrian_Signals:7"])
        self.assertEqual(records[0][2], {"type": "Point", "coordinates": [-116.3000123, 43.6]})
        self.assertEqual(devices[0]["kind"], "ped_hybrid")
        self.assertEqual(devices[0]["attributes"], {"layer": "Pedestrian_Signals", "purpose": "Hybrid Pedestrian Crossing"})

    def test_esri_points(self):
        self.assertEqual(arcgis.point_geojson({"x": -116.0, "y": 43.0}), {"type": "Point", "coordinates": [-116.0, 43.0]})
        for g in (None, {}, {"x": None, "y": 43}, {"x": "NaN", "y": 43}, {"x": 500, "y": 43}):
            self.assertIsNone(arcgis.point_geojson(g))

    def test_only_cut_off_answers_are_paged(self):
        self.assertNotIn("resultOffset", arcgis.query_url("https://x/FeatureServer/0"))
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(arcgis.query_url("https://x/MapServer/3", 2000, 2000, "objectid")).query)
        self.assertEqual((q["resultOffset"], q["orderByFields"], q["outSR"], q["f"]), (["2000"], ["objectid"], ["4326"], ["json"]))


def compass_feature(oid, location, operator="Testtown", synchro=None, x=-116.5, y=43.6, **kw):
    attrs = {"OBJECTID": oid, "jurisdicti": operator, "owner": operator, "city": "TESTTOWN", "county": "TESTCO",
             "location": location, "coordinated": "Y", "Coordinate": "Yes", "coor_group": "TEST GROUP",
             "CrossingTy": "Full Signal", "LPI_Status": "None", "APS": "Complete", "ACHD_Synchro_ID": synchro,
             "Skew": "No", "five_legged": "No", "TEV": 1000,
             "NBL_Vol": 10, "NBT_Vol": 200, "NBR_Vol": 30, "NB_RT_Lanes": 1, "NB_LT_Phasing": "Prot", "NB_RT_Phasing": "Perm",
             "SBL_Vol": 11, "SBT_Vol": 210, "SBR_Vol": None, "SB_RT_Lanes": 0, "SB_LT_Phasing": "pm+pt",
             "EB_LT_Phasing": "D.P+P", "WB_LT_Phasing": "Split", "WB_RT_Phasing": "NA",
             "Street_View": '=HYPERLINK("https://maps.example/?q=1", "Street View")',
             "Google_Earth": '=HYPERLINK("https://maps.example/?q=2", "Map View")', "LatLong": f"{y}, {x}"}
    attrs.update(kw)
    return esri(attrs, x, y)


class CompassTest(unittest.TestCase):
    def test_keys_and_versions_survive_new_objectids(self):
        before = [compass_feature(1, "ALPHA AVE & BETA ST", synchro=901), compass_feature(2, "GAMMA RD & DELTA LN")]
        after = [compass_feature(51, "ALPHA AVE & BETA ST", synchro=901), compass_feature(77, "GAMMA RD & DELTA LN")]
        ra, _ = compass.parse(before)
        rb, _ = compass.parse(after)
        self.assertEqual([r[0] for r in ra], ["synchro:901", "loc:testtown:delta ln & gamma rd"])
        self.assertEqual([(r[0], version_hash(r[1])) for r in ra], [(r[0], version_hash(r[1])) for r in rb])
        self.assertNotIn("OBJECTID", ra[0][1])
        self.assertNotIn("Street_View", ra[0][1])
        self.assertNotIn("Google_Earth", ra[0][1])

    def test_location_normalization(self):
        self.assertEqual(streets.location_key("ALPHA AVE & BETA ST"), streets.location_key("Beta Street & Alpha Avenue"))
        self.assertEqual(streets.location_key("I-99B & 11TH AVENUE S."), "11th ave s & i 99b")
        self.assertEqual(streets.location_key("Gamma Rd. @ Delta"), "delta & gamma rd")

    def test_repeated_keys_get_ordinals_west_to_east_and_shared_synchro_ids_get_locations(self):
        records, _ = compass.parse([
            compass_feature(1, "EPSILON RD", x=-116.40), compass_feature(2, "EPSILON RD", x=-116.45),
            compass_feature(3, "ALPHA & BETA", synchro=905), compass_feature(4, "GAMMA & DELTA", synchro=905)])
        keys = {r[1]["LatLong"]: r[0] for r in records}
        self.assertEqual(keys["43.6, -116.45"], "loc:testtown:epsilon rd")
        self.assertEqual(keys["43.6, -116.4"], "loc:testtown:epsilon rd#2")
        self.assertEqual(sorted(r[0] for r in records if r[0].startswith("synchro")),
                         ["synchro:905:alpha & beta", "synchro:905:delta & gamma"])

    def test_approaches_are_legs_the_traffic_comes_from(self):
        _, devices = compass.parse([compass_feature(1, "ALPHA & BETA", synchro=902)])
        a = devices[0]["attributes"]
        self.assertEqual(a["approaches"]["NB"], {"leg": "S", "right_turn_lanes": 1, "left_turn_phasing": "protected",
                                                 "right_turn_phasing": "permitted",
                                                 "volumes": {"L": 10, "T": 200, "R": 30}})
        self.assertEqual(a["approaches"]["SB"]["leg"], "N")
        self.assertEqual(a["approaches"]["SB"]["volumes"], {"L": 11, "T": 210})
        self.assertEqual(a["approaches"]["SB"]["left_turn_phasing"], "protected-permitted")
        self.assertEqual(a["approaches"]["EB"], {"leg": "W", "right_turn_lanes": None, "left_turn_phasing": "protected-permitted",
                                                 "right_turn_phasing": None, "volumes": None})
        self.assertEqual(a["approaches"]["WB"]["leg"], "E")
        self.assertEqual(a["approaches"]["WB"]["left_turn_phasing"], "split")
        self.assertIsNone(a["approaches"]["WB"]["right_turn_phasing"])
        self.assertEqual((a["synchro_id"], a["coordinated"], a["skew"], a["control"], a["city"]), (902, True, False, "signal", "Testtown"))
        self.assertEqual(devices[0]["name"], "Alpha & Beta")

    def test_control_from_type(self):
        self.assertEqual(compass.control("Half Signal"), "half_signal")
        self.assertEqual(compass.control("U-Turn"), "signal_uturn")
        self.assertEqual(compass.control("Full Signal"), "signal")


class RegionalTest(unittest.TestCase):
    def test_device_kinds(self):
        cases = {"TRAFFIC SIGNAL": "signal_intersection", "HAWK": "ped_hybrid", "SCHOOL FLASHER": "school_flasher",
                 "RECTANGULAR RAPID FLASHING BEACON (RRFB)": "rrfb", "PEDX - CONVENTIONAL": "ped_conventional",
                 "PEDX WITH YELLOW FLASHING BEACON": "warning_beacon", "INTERSECTION FLASHING BEACON": "warning_beacon",
                 "ADVANCED WARNING FLASHING BEACON": "warning_beacon", "FIRE": "fire_signal",
                 "EMERGENCY SIGNAL": "fire_signal", None: "signal_intersection"}
        for device, want in cases.items():
            self.assertEqual(regional.kind(device), want, device)

    def test_keys_carry_the_kind_and_skip_objectid(self):
        feats = [esri({"objectid": 1, "jurisdicti": "TESTTOWN", "location": "ALPHA & BETA", "its_device": "TRAFFIC SIGNAL"}),
                 esri({"objectid": 2, "jurisdicti": "TESTTOWN", "location": "ALPHA & BETA", "its_device": "HAWK"}),
                 esri({"objectid": 3, "jurisdicti": "TESTTOWN", "location": "ZETA AVE", "its_device": "SCHOOL FLASHER"}, -116.6),
                 esri({"objectid": 4, "jurisdicti": "TESTTOWN", "location": "ZETA AVE", "its_device": "SCHOOL FLASHER"}, -116.5)]
        records, devices = regional.parse(feats)
        self.assertEqual([r[0] for r in records], [
            "loc:testtown:signal_intersection:alpha & beta", "loc:testtown:ped_hybrid:alpha & beta",
            "loc:testtown:school_flasher:zeta ave", "loc:testtown:school_flasher:zeta ave#2"])
        self.assertNotIn("objectid", records[0][1])
        self.assertEqual([d["kind"] for d in devices], ["signal_intersection", "ped_hybrid", "school_flasher", "school_flasher"])


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0011)")
class DatabaseTest(unittest.TestCase):
    """The ingestors' store steps against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        if not self.conn.execute("select to_regclass('core.rail_crossing') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("core.rail_crossing is missing: apply migration 0011")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, source, at):
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, true) returning id",
                                 (source, at)).fetchone()[0]

    def test_fra_store_keeps_closed_crossings_flagged(self):
        c = self.conn
        db.ensure_source(c, fra.SOURCE)
        c.execute("update core.rail_crossing set active = false")    # set real rows aside (rolled back)
        t0 = datetime(2026, 10, 6, tzinfo=timezone.utc)
        parsed = fra.parse([fra_row("999001A"), fra_row("999004D", crossingclosed="Yes", wdcode="Crossbucks",
                                                        geocoded_lat_long=None, latitude=None, longitude=None)])
        stats = fra.store(c, self.fetch("fra_crossings", t0), t0, parsed)
        self.assertEqual((stats["crossings"], stats["closed"], stats["without a point"]), (2, 1, 1))
        rows = dict((r[0], r[1:]) for r in c.execute(
            """select crossing_id, closed, active, warning, geom is null from core.rail_crossing
               where crossing_id in ('999001A', '999004D')""").fetchall())
        self.assertEqual(rows, {"999001A": (False, True, "gates", False), "999004D": (True, True, "crossbucks", True)})
        payload = c.execute("select payload from raw.record where source = 'fra_crossings' and source_id = '999001A'").fetchone()[0]
        self.assertFalse(any(k.startswith(":@computed_region") for k in payload))
        # A later snapshot without one: it's kept, marked inactive.
        t1 = t0 + timedelta(days=7)
        fra.store(c, self.fetch("fra_crossings", t1), t1, {"999001A": parsed["999001A"]})
        self.assertEqual(c.execute("select active from core.rail_crossing where crossing_id = '999004D'").fetchone(), (False,))

    def test_device_upserts_keep_the_builds_links_and_retire_missing_ones(self):
        c = self.conn
        db.ensure_source(c, compass.SOURCE)
        t0 = datetime(2026, 10, 6, tzinfo=timezone.utc)
        _, devices = compass.parse([compass_feature(1, "ALPHA & BETA", synchro=99902, x=-115.5, y=42.5),
                                    compass_feature(2, "GAMMA & DELTA", x=-115.49, y=42.5)])
        signal_devices.store(c, compass.SOURCE["name"], devices, t0)
        iid = c.execute("""insert into core.intersection (name, geom, control, confidence)
                           values ('Test', ST_SetSRID(ST_MakePoint(-115.5, 42.5), 4326), 'signal', 0.7) returning id""").fetchone()[0]
        c.execute("update core.signal_device set intersection_id = %s, distance_m = 3 where source = %s and source_id = 'synchro:99902'",
                  (iid, compass.SOURCE["name"]))
        stats = signal_devices.store(c, compass.SOURCE["name"], devices[:1], t0 + timedelta(days=7))
        rows = dict((r[0], r[1:]) for r in c.execute(
            """select source_id, intersection_id, active from core.signal_device
               where source = %s and source_id in ('synchro:99902', 'loc:testtown:delta & gamma')""",
            (compass.SOURCE["name"],)).fetchall())
        self.assertEqual(rows, {"synchro:99902": (iid, True), "loc:testtown:delta & gamma": (None, False)})
        self.assertGreaterEqual(stats["retired"], 1)

    def test_an_emptied_or_cut_off_layer_is_refused(self):
        c = self.conn
        db.ensure_source(c, {"name": "test_signals_x", "title": "test", "url": "https://example.test/", "access": "open"})
        for i in range(4):
            c.execute("""insert into core.signal_device (source, source_id, kind, geom)
                         values ('test_signals_x', %s, 'signal_pole', ST_SetSRID(ST_MakePoint(-115.5, 42.5), 4326))""", (str(i),))
        signal_devices.check(c, "test_signals_x", 2)
        for n in (0, 1):
            with self.assertRaises(RuntimeError):
                signal_devices.check(c, "test_signals_x", n)
        with self.assertRaises(RuntimeError):
            signal_devices.check(c, "test_signals_never_seen", 0)
        signal_devices.check(c, "test_signals_never_seen", 5)


class StreetsTest(unittest.TestCase):
    def test_core_names(self):
        cases = {"W Alpha Ave": "ALPHA", "ALPHA": "ALPHA", "11TH AVENUE S.": "11", "N 11th Ave": "11",
                 "WB Interstate 99 Off Exit 50B": "I 99 OFF EXIT 50B", "Hwy 99": "SH 99", "SH-99": "SH 99",
                 "US HWY 98/99": "US 98/99", "US 98-99": "US 98/99", "Ave (b)": "AVENUE B", 'AVE. "A"': "AVENUE A",
                 "N Avenue B Ave": "AVENUE B", "5 Mile Rd": "FIVE MILE", "GAMMA ST (OLD NAME)": "GAMMA"}
        for name, want in cases.items():
            self.assertEqual(streets.core(name), want, name)

    def test_same_street(self):
        same = [("I 84", "I 84 OFF EXIT 50B"), ("I 84 N RAMP", "I 84 ON EXIT 46"), ("BROADWAY", "BROADWAY RAMP"),
                ("PARK CENTER", "PARKCENTER"), ("KOOTENIA", "KOOTENAI"), ("STATE", "SH 44"), ("VMP", "VETERANS MEMORIAL")]
        differ = [("I 84", "I 84B"), ("I 84", "I 184"), ("STATE", "STATESBORO"), ("EAGLE", "KARCHER"),
                  ("COLUMBIA", "COLUMBUS"), ("FIVE MILE", "TEN MILE"), ("23", "25")]
        for a, b in same:
            self.assertTrue(streets.same_street(a, b), (a, b))
        for a, b in differ:
            self.assertFalse(streets.same_street(a, b), (a, b))

    def test_display(self):
        self.assertEqual(streets.display_location("ALPHA-BETA BLVD & 11TH AVENUE S."), "Alpha-Beta Blvd & 11th Ave S")
        self.assertEqual(streets.display("W ParkCenter Blvd"), "ParkCenter Blvd")
        self.assertEqual(streets.display("I-99B"), "I-99B")
        self.assertEqual(streets.display("Avenue B"), "Avenue B")


if __name__ == "__main__":
    unittest.main()
