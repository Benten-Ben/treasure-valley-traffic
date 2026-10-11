"""Tests for ACHD's Official Bicycle Facility Network (plugins/roads/ingest/sources/achd_bike_network.py).

The page is synthetic: made-up IDs, streets, widths and notes in the layer's own field names,
on lines far from the valley (UTM 11N x 300,000 is about 119.5 W). The parsing and run tests
are offline. The store, match and view tests run only against a scratch database named by
TVT_TEST_DATABASE_URL, migrated through roads 0004; each works inside one transaction and rolls
it back.

Run: python3 -m unittest discover -s plugins -t .
"""

import contextlib
import copy
import io
import json
import os
import re
import unittest
import urllib.parse
from datetime import datetime, timezone
from unittest import mock

from ingest import arcgis, db, utm
from ingest.db import version_hash
from plugins.roads.ingest import segment_match
from plugins.roads.ingest.sources import achd_bike_network as bn

X0, Y0 = 300000, 4800000
T1 = datetime(2026, 10, 6, 1, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)


def path(*pts):
    """Esri JSON polyline paths from (x, y) metres offsets, in WGS84, with an M value as ACHD's have."""
    return {"paths": [[[*utm.from_utm(X0 + x, Y0 + y), 0.0] for x, y in pts]]}


SIDE = {"FacilityDirection": None, "FacilityType": None, "FacilityWidth": None, "AdjLaneWidth": None,
        "LaneCt": None, "PavementEdge": None, "RightTurn": None, "Parking": None, "ParkingWidth": None,
        "PavementMarkings": None, "MarkingLocation": None, "BufferType": None, "BufferWidth": None}


def record(oid, *, ebnb=None, wbsb=None, geometry=None, **fields):
    """One Esri JSON feature with every field of the layer (as listed Oct 11, 2026), synthetic values."""
    a = {"OBJECTID": oid, "LocationID": f"BMP9{oid:03d}", "BMPLevel": "Level 1", "BuiltBMPLevel": "Yes",
         "PartofRLSBikeway": "No", "BkwyName": "N/A", "BuiltRLSBikeway": "N/A", "BMPStatus": "Complete",
         "RLSBikewayStatus": "N/A", "Comments": None, "ExistLevel": "Level 1", "FuncClass": "Collector",
         "Street": f"Sample {oid} Rd", "YrBuilt": "TBD", "ExistingType": "Bike Lane", "Speed": None,
         "LengthMiles": 0.186411358, "NoofLanes": 2, "BikeLnMiles": 0.372822717, "MarksOrSigns": None,
         "Plans": None, "YearAdded": 2018, "City": "Sampleton", "Volume": "1500 - 3000", "Experience": None,
         "Agency": "ACHD", "BikeLegend": "High Comfort for Adults", "YearUpdated": "2023",
         "FieldVerified": "Verified", "SpeedField": 35, "TotalLanes": 2, "TotalPavement": 40.0,
         "TotalROW": 66.0, "ManagementZone": "9", "NeighborhoodPlanning": "Sample North", "FieldNotes": None,
         "MaintZones": 9, "MaintZones_Notes": None, "Lengthft": 984.2519685, "LTS": 2,
         "Shape__Length": 984.25196852}
    for prefix, side in (("EBNB", ebnb), ("WBSB", wbsb)):
        for k, v in {**SIDE, **(side or {})}.items():
            a[k + prefix] = v
    a.update(fields)
    return {"attributes": a, "geometry": geometry or path((0, 0), (0, 300))}


def lanes_side(direction, lanes="1", lane_w="11", bike="Bike Lane", bike_w="5", parking="None", parking_w="N/A",
               buffer="None", buffer_w="N/A", edge="Curb & Gutter"):
    return {"FacilityDirection": direction, "FacilityType": bike, "FacilityWidth": bike_w, "AdjLaneWidth": lane_w,
            "LaneCt": lanes, "PavementEdge": edge, "RightTurn": "N/A", "Parking": parking, "ParkingWidth": parking_w,
            "PavementMarkings": "Yes", "MarkingLocation": "2", "BufferType": buffer, "BufferWidth": buffer_w}


def page():
    """The synthetic page: a few records covering the cases, as Esri JSON."""
    return [
        # 1: a two-way collector drawn northward, with bike lanes, parking on one side and a centre
        # turn lane: 11 + 5 + 8 (NB) + 11 + 5 (SB) + 12 (centre) = 52 ft curb to curb.
        record(1, ebnb=lanes_side("Northbound", parking="Parallel", parking_w="8"), wbsb=lanes_side("Southbound"),
               TotalLanes=3, TotalPavement=52.0, TotalROW=80.0,
               Comments="Synthetic comment.", FieldNotes="Synthetic field note."),
        # 2: a one-way eastbound street: the other side has no direction ('N/A') but parking.
        record(2, ebnb=lanes_side("Eastbound", lanes="2", bike="Buffered Bike Lane", bike_w="6", buffer="Painted",
                                  buffer_w=".5"),
               wbsb={"FacilityDirection": "N/A", "FacilityType": "No Facility", "FacilityWidth": "N/A",
                     "AdjLaneWidth": "N/A", "LaneCt": "N/A", "PavementEdge": "Curb No Gutter", "RightTurn": "N/A",
                     "Parking": "Parallel", "ParkingWidth": "8", "PavementMarkings": "N/A",
                     "BufferType": "N/A", "BufferWidth": "N/A"},
               TotalLanes=2, TotalPavement=36.5, TotalROW=60.0, Street="02nd St", geometry=path((1000, 0), (1300, 0))),
        # 3: a pathway, 4: a road not built yet, 5: not field-checked (no sides), with odd words.
        record(3, FuncClass="Pathway", Street="Pathway ", ExistingType="Pathway", TotalPavement=None, TotalROW=None,
               TotalLanes=None, FieldVerified="N/A", LTS=1, geometry=path((4000, 10), (4000, 290))),
        record(4, Street="New Road ", BMPStatus="New Road", ExistingType=None, TotalPavement=None, TotalROW=None,
               FieldVerified="N/A", LTS=None, BikeLegend="<Null>", geometry=path((2000, 0), (2000, 300))),
        record(5, ebnb=lanes_side("Northbound", bike="Bike Boulevard", bike_w="Wide", buffer="Landscaping",
                                  buffer_w="Varies", lane_w="10.5"),
               wbsb=lanes_side("Southbound", lane_w="10.5", bike="Mixed Traffic", bike_w="N/A"),
               FieldVerified="N/A", Volume="+3000", YrBuilt="2023", FuncClass="Local ",
               geometry=path((3000, 0), (3000, 300))),
    ]


def features(esri=None):
    return [arcgis.esri_feature(f) for f in (esri if esri is not None else page())]


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.records, self.rows, self.notes, self.counts = bn.parse(features())

    def test_widths_codes_and_sides(self):
        r = self.rows[1]
        self.assertEqual((r["kind"], r["street"], r["func_class"], r["lts"], r["field_verified"]),
                         ("street", "Sample 1 Rd", "Collector", 2, True))
        self.assertEqual((r["total_lanes"], r["total_pavement_ft"], r["total_row_ft"]), (3, 52.0, 80.0))
        self.assertEqual((r["ebnb_direction"], r["ebnb_facility"], r["ebnb_facility_w_ft"], r["ebnb_lane_w_ft"],
                          r["ebnb_lanes"], r["ebnb_edge"], r["ebnb_parking"], r["ebnb_parking_w_ft"],
                          r["ebnb_markings"], r["ebnb_buffer"], r["ebnb_buffer_w_ft"], r["ebnb_right_turn"]),
                         ("N", "bike_lane", 5.0, 11.0, 1, "curb_gutter", "parallel", 8.0, "yes", "none", None, None))
        self.assertEqual((r["wbsb_direction"], r["wbsb_parking"], r["wbsb_parking_w_ft"]), ("S", "none", None))
        two = self.rows[2]
        self.assertEqual((two["ebnb_direction"], two["ebnb_facility"], two["ebnb_buffer"], two["ebnb_buffer_w_ft"]),
                         ("E", "buffered_bike_lane", "painted", 0.5))
        self.assertEqual(r["geom"]["type"], "LineString")
        self.assertEqual(len(r["geom"]["coordinates"][0]), 2)                 # the M value is dropped

    def test_a_one_way_streets_other_side_has_no_lanes_but_keeps_its_parking(self):
        two = self.rows[2]
        self.assertEqual((two["wbsb_direction"], two["wbsb_lanes"], two["wbsb_facility"], two["wbsb_edge"],
                          two["wbsb_parking"], two["wbsb_parking_w_ft"]),
                         (None, 0, "no_facility", "curb", "parallel", 8.0))
        # A side with nothing at all (not field-checked) stays unknown, not 0.
        three = self.rows[3]
        self.assertEqual((three["ebnb_lanes"], three["wbsb_lanes"], three["ebnb_facility"]), (None, None, None))

    def test_kinds(self):
        self.assertEqual({oid: r["kind"] for oid, r in self.rows.items()},
                         {1: "street", 2: "street", 3: "path", 4: "planned", 5: "street"})

    def test_text_fields_stay_text_and_blanks_become_null(self):
        five = self.rows[5]
        self.assertEqual((five["volume"], five["yr_built"], five["func_class"]), ("+3000", "2023", "Local"))
        self.assertEqual((self.rows[1]["volume"], self.rows[1]["yr_built"]), ("1500 - 3000", "TBD"))
        self.assertIsNone(self.rows[4]["bike_legend"])                       # '<Null>'
        self.assertEqual((self.rows[3]["field_verified"], self.rows[3]["total_pavement_ft"]), (False, None))

    def test_unknown_words_become_other_and_are_counted(self):
        five = self.rows[5]
        self.assertEqual((five["ebnb_facility"], five["ebnb_facility_w_ft"]), ("other", None))
        self.assertEqual((five["ebnb_buffer"], five["ebnb_buffer_w_ft"], five["ebnb_buffer_varies"]),
                         ("landscaping", None, True))
        self.assertEqual((five["wbsb_facility"], five["wbsb_facility_w_ft"]), ("mixed_traffic", None))
        self.assertEqual(self.counts["unknown facility values"], 1)
        self.assertEqual(self.counts["unreadable widths"], 1)                # 'Wide'; 'Varies' is a flag

    def test_feet(self):
        for text, ft in (("5", 5.0), (".5", 0.5), ("5'", 5.0), (" 12 ", 12.0), (32, 32.0), (31.7, 31.7),
                         ("N/A", None), ("Varies", None), ("", None), (None, None), ("0", None), ("-3", None),
                         ("Other", None)):
            self.assertEqual(bn.feet(text), ft, text)

    def test_free_text_stays_out_of_the_row_and_its_attributes(self):
        r = self.rows[1]
        blob = json.dumps({k: v for k, v in r.items() if k != "geom"})
        self.assertNotIn("Synthetic", blob)
        self.assertFalse({"Comments", "FieldNotes"} & set(r["attributes"]))
        self.assertEqual(self.notes, {1: ("Synthetic comment.", "Synthetic field note.")})
        # raw.record keeps them (internal): a changed note is a new version.
        payload = {sid: p for sid, p, _ in self.records}["1"]
        self.assertEqual(payload["FieldNotes"], "Synthetic field note.")
        # The columns the views and P7 read can't carry them either.
        self.assertFalse(any("comment" in c or "note" in c for c in bn.COLUMNS))

    def test_attributes_keep_the_rest_as_published(self):
        a = self.rows[1]["attributes"]
        self.assertEqual((a["BMPLevel"], a["MarkingLocationEBNB"], a["LengthMiles"], a["Lengthft"]),
                         ("Level 1", "2", 0.18641, 984.3))
        self.assertNotIn("Shape__Length", a)
        self.assertNotIn("OBJECTID", a)
        self.assertNotIn("TotalPavement", a)                                  # typed, not repeated
        self.assertEqual(a["BMPStatus"], "Complete")                          # read for the kind, kept

    def test_versions_leave_out_the_key_and_the_derived_length(self):
        a, b = page()[0], page()[0]
        b["attributes"]["OBJECTID"] = 5001
        b["attributes"]["Shape__Length"] = 984.25196853                      # a reload's float noise
        b["attributes"]["LengthMiles"] = 0.1864113581
        pa, pb = (bn.parse(features([x]))[0][0][1] for x in (a, b))
        self.assertEqual(version_hash(pa), version_hash(pb))
        self.assertIn("_geom", pa)

    def test_the_content_hash_sees_every_change_and_not_the_order(self):
        recs = bn.parse(features())[0]
        h = bn.content_hash(recs)
        self.assertEqual(h, bn.content_hash(list(reversed(recs))))
        changed = page()
        changed[0]["attributes"]["FieldNotes"] = "Another synthetic note."
        self.assertNotEqual(h, bn.content_hash(bn.parse(features(changed))[0]))
        moved = page()
        moved[1]["geometry"] = path((1000, 0), (1300, 20))
        self.assertNotEqual(h, bn.content_hash(bn.parse(features(moved))[0]))

    def test_missing_fields_fail(self):
        esri = page()
        for f in esri:
            del f["attributes"]["TotalPavement"]
        self.assertEqual(bn.missing_fields(features(esri)), ["TotalPavement"])
        self.assertEqual(bn.missing_fields(features()), [])


class Server:
    """The layer as gis.achdidaho.org serves it: an ID list, then features by OBJECTID range in ID
    order, at most 2,000 an answer."""

    def __init__(self, esri, cap=2000):
        self.by_id = {f["attributes"]["OBJECTID"]: f for f in esri}
        self.cap, self.asked = cap, []

    def get(self, url):
        self.asked.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if q.get("returnIdsOnly") == ["true"]:
            body = {"objectIdFieldName": "OBJECTID", "objectIds": list(self.by_id)}
        else:
            lo, hi = (int(t) for t in re.findall(r"(?:>=|<=) (\d+)", q["where"][0]))
            sel = [self.by_id[i] for i in sorted(self.by_id) if lo <= i <= hi]
            body = {"exceededTransferLimit": len(sel) > self.cap, "features": sel[:self.cap]}
        return 200, json.dumps(body).encode(), "no_rules"


class FakeFetch:
    def __init__(self, conn, source):
        self.id, self.started_at = 1, T1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RunTest(unittest.TestCase):
    def big_page(self, n=2500):
        """n records renumbered from 3929, as the layer's IDs ran on Oct 11, 2026."""
        base = page()
        out = []
        for i in range(n):
            f = copy.deepcopy(base[i % len(base)])
            f["attributes"]["OBJECTID"] = 3929 + i
            out.append(f)
        return out

    def run_with(self, server, unchanged=False, stale=False):
        stored = []
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(db, "ensure_source"))
            stack.enter_context(mock.patch.object(db, "Fetch", FakeFetch))
            stack.enter_context(mock.patch.object(bn, "unchanged", return_value=unchanged))
            stack.enter_context(mock.patch.object(bn, "heartbeat", return_value=7))
            stack.enter_context(mock.patch.object(bn, "save_signature"))
            stack.enter_context(mock.patch.object(bn, "stale", return_value=stale))
            stack.enter_context(mock.patch.object(bn, "store", side_effect=lambda c, i, t, f, p: (
                stored.append(len(f)) or ({"records": len(f)}, len(f)))))
            match = stack.enter_context(mock.patch.object(bn, "match", return_value={"matched": 2}))
            stats = bn.run(object(), get=server.get, sleep=lambda s: None)
        return stats, stored, match

    def test_the_layer_comes_in_two_pages_of_2000(self):
        server = Server(self.big_page())
        stats, stored, match = self.run_with(server)
        self.assertEqual(stored, [2500])
        ranges = [u for u in server.asked if "returnIdsOnly" not in u]
        self.assertEqual(len(server.asked), 3)                                  # the IDs, then two pages
        self.assertEqual(len(ranges), 2)
        for u in server.asked:
            self.assertTrue(u.startswith(bn.LAYER + "/query?"), u)
            self.assertNotIn("more.achdidaho.org", u)
        self.assertEqual(stats["match matched"], 2)                           # stored something: rematched

    def test_an_unchanged_layer_only_confirms_its_versions(self):
        stats, stored, match = self.run_with(Server(page()), unchanged=True)
        self.assertEqual((stored, stats), ([], {"unchanged": True, "versions confirmed": 7}))
        match.assert_not_called()
        stats, stored, match = self.run_with(Server(page()), unchanged=True, stale=True)  # ACHD's segments moved
        match.assert_called_once()

    def test_a_layer_missing_a_field_fails(self):
        esri = page()
        for f in esri:
            del f["attributes"]["BufferWidthWBSB"]
        with self.assertRaises(RuntimeError):
            self.run_with(Server(esri))

    def test_a_failing_match_fails_the_fetch_so_the_store_rolls_back(self):
        exits = []

        class Fetch(FakeFetch):
            def __exit__(self, exc_type, *rest):
                exits.append(exc_type)
                return False

        with mock.patch.object(db, "ensure_source"), mock.patch.object(db, "Fetch", Fetch), \
                mock.patch.object(bn, "unchanged", return_value=False), mock.patch.object(bn, "save_signature"), \
                mock.patch.object(bn, "store", return_value=({"records": 5}, 5)), \
                mock.patch.object(bn, "match", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                bn.run(object(), get=Server(page()).get, sleep=lambda s: None)
        self.assertEqual(exits, [RuntimeError])

    def test_rematched_with_the_other_sources_when_achds_segments_change(self):
        self.assertIs(segment_match.matchers()["achd_bike_network"][3], bn.stale)
        self.assertEqual(bn.RULE.method, "buffer15_bearing20")
        self.assertFalse(bn.RULE.loops)


# --- storing, matching and the views (database) -------------------------------------------

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database migrated through roads 0004")
class StoreTest(unittest.TestCase):
    """Each test runs in one transaction that's rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.conn = psycopg.connect(DB_URL)
        if not cls.conn.execute("select to_regclass('roads.bike_facility') is not null").fetchone()[0]:
            cls.conn.close()
            raise unittest.SkipTest("roads.bike_facility is missing: apply roads 0004")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def tearDown(self):
        self.conn.rollback()

    def fresh(self):
        """No bike-network rows at all (rolled back), and a fetch to log them under."""
        c = self.conn
        c.execute("delete from roads.bike_facility_match")
        c.execute("delete from roads.bike_facility_note")
        c.execute("delete from roads.bike_facility")
        c.execute("delete from raw.record where source = 'achd_bike_network'")
        db.ensure_source(c, bn.SOURCE)
        return c.execute("insert into ops.fetch (source, started_at, ok) values (%s, now(), true) returning id",
                         (bn.SOURCE["name"],)).fetchone()[0]

    def test_store_notes_and_a_reload(self):
        c = self.conn
        fid = self.fresh()
        stats, changed = bn.store(c, fid, T1, features())
        self.assertEqual((stats["records"], stats["streets"], stats["pathways"], stats["planned roads"],
                          stats["record versions new"], changed), (5, 3, 1, 1, 5, 5))
        self.assertEqual(c.execute("select object_id, comments, field_notes from roads.bike_facility_note").fetchall(),
                         [(1, "Synthetic comment.", "Synthetic field note.")])
        geom = c.execute("select ST_GeometryType(geom), attributes->>'BMPLevel' from roads.bike_facility "
                         "where object_id = 1").fetchone()
        self.assertEqual(geom, ("ST_MultiLineString", "Level 1"))
        # The same layer again: nothing new.
        stats, changed = bn.store(c, fid, T2, features())
        self.assertEqual((stats["record versions new"], stats["unchanged"], changed), (0, 5, 0))
        # ACHD reloads the layer: every OBJECTID new. The rows (and the note) move to the new IDs.
        esri = page()
        for f in esri:
            f["attributes"]["OBJECTID"] += 5000
        t3 = datetime(2026, 10, 8, 1, tzinfo=timezone.utc)
        stats, changed = bn.store(c, fid, t3, features(esri))
        self.assertEqual((stats["reload: rows carried over"], stats["retired"]), (5, 0))
        self.assertEqual(c.execute("select array_agg(object_id order by object_id) from roads.bike_facility "
                                   "where active").fetchone()[0], [5001, 5002, 5003, 5004, 5005])
        self.assertEqual(c.execute("select object_id from roads.bike_facility_note").fetchall(), [(5001,)])
        # A note cleared at ACHD goes; a short layer is refused.
        esri[0]["attributes"]["Comments"] = esri[0]["attributes"]["FieldNotes"] = " "
        bn.store(c, fid, datetime(2026, 10, 9, 1, tzinfo=timezone.utc), features(esri))
        self.assertEqual(c.execute("select count(*) from roads.bike_facility_note").fetchone()[0], 0)
        with self.assertRaises(RuntimeError):
            bn.store(c, fid, datetime(2026, 10, 10, 1, tzinfo=timezone.utc), features(esri[:1]))

    def test_the_change_check(self):
        c = self.conn
        fid = self.fresh()
        c.execute("delete from ops.layer_signature where source = 'achd_bike_network'")
        parsed = bn.parse(features())
        sig = {"content": bn.content_hash(parsed[0]), "records": 5}
        self.assertFalse(bn.unchanged(c, sig))                                 # never read
        bn.store(c, fid, T1, features(), parsed)
        bn.save_signature(c, sig, read=True)
        self.assertTrue(bn.unchanged(c, sig))
        self.assertEqual(bn.heartbeat(c, T2), 5)
        self.assertFalse(bn.unchanged(c, {**sig, "content": "other"}))
        c.execute("update roads.bike_facility set active = false where object_id = 5")
        self.assertFalse(bn.unchanged(c, sig))                                 # a row went missing: store again

    def segments(self):
        """Stand-ins for ACHD segments along the synthetic records (ids returned by name)."""
        c = self.conn
        ids = {}
        for key, (name, one_way, pts) in {
                "north": ("N Sample 1 Rd", "both", [(0, 0), (0, 150)]),      # along record 1, drawn northward
                "south": ("S Sample 1 Rd", "both", [(0, 300), (0, 150)]),    # along record 1, drawn southward
                "east1": ("E 2nd St", "forward", [(1000, 0), (1300, 0)]),    # record 2 ('02nd St'), one-way
                "frontage": ("W Frontage St", "both", [(3008, 0), (3008, 300)]),   # 8 m beside record 5
                "path": ("N Sample 3 Rd", "both", [(4005, 50), (4005, 250)]),    # a road beside the pathway
                "far": ("N Far Rd", "both", [(9000, 0), (9000, 300)])}.items():
            wkt = "LINESTRING(" + ", ".join(f"{X0 + x} {Y0 + y}" for x, y in pts) + ")"
            ids[key] = c.execute(
                """insert into core.road_segment (achd_perm_id, name, one_way, geom)
                   values (%s, %s, %s, ST_Multi(ST_Transform(ST_GeomFromText(%s, 32611), 4326))) returning id""",
                (-990300 - len(ids), name, one_way, wkt)).fetchone()[0]
        return ids

    def test_match_and_the_cross_section_view(self):
        c = self.conn
        fid = self.fresh()
        bn.store(c, fid, T1, features())
        ids = self.segments()
        with mock.patch.object(segment_match, "SEGMENTS_SQL",
                               "select id, name, geom from core.road_segment where achd_perm_id between -990399 and -990300"):
            stats = bn.match(c)
        # 5 lies along another street only: its names disagree, so it isn't matched.
        self.assertEqual((stats["street records"], stats["matched"], stats["dropped: street names disagree"]),
                         (3, 2, 1))
        rows = dict(c.execute("select road_segment_id, object_id from roads.bike_facility_match").fetchall())
        self.assertEqual(rows, {ids["north"]: 1, ids["south"]: 1, ids["east1"]: 2})   # never the pathway
        x = {r[0]: r for r in c.execute(
            """select road_segment_id, forward_side, fwd_lanes, fwd_lane_w_m::float8, fwd_bike, fwd_bike_w_m::float8,
                      fwd_parking_w_m::float8, bwd_bike, bwd_parking_w_m::float8, total_pavement_m::float8,
                      total_row_m::float8, centre_lanes, unassigned_m::float8, flags, fwd_roadway_m::float8,
                      bwd_roadway_m::float8, bwd_lanes
               from roads.segment_bike_xsection""").fetchall()}
        north, south, east = x[ids["north"]], x[ids["south"]], x[ids["east1"]]
        # Drawn northward, the forward side is ACHD's northbound one, with the parking.
        self.assertEqual(north[1:9], ("ebnb", 1, 3.35, "bike_lane", 1.52, 2.44, "bike_lane", 0))
        self.assertEqual((north[9], north[10], north[11]), (15.85, 24.38, 1))
        self.assertAlmostEqual(north[12], 3.66, delta=0.02)                     # 12 ft left: the centre turn lane
        self.assertEqual(north[13], [])
        # Drawn southward, the same record turns round.
        self.assertEqual((south[1], south[6], south[8]), ("wbsb", 0, 2.44))
        # The one-way street: forward has the lanes, backward only the parking; flagged one-way.
        self.assertEqual((east[1], east[2], east[4], east[16], east[8]), ("ebnb", 2, "buffered_bike_lane", 0, 2.44))
        self.assertEqual((east[14], east[15]), (8.68, 2.44))                  # 2 x 11 ft + 6 ft + 0.5 ft; parking
        self.assertAlmostEqual(east[12], 0.0, delta=0.02)
        self.assertEqual(east[13], ["one_way_segment"])
        self.assertEqual(c.execute("select count(*) from roads.bike_facility_side").fetchone()[0], 10)
        # The views carry no free text.
        for view in ("segment_bike_xsection", "bike_facility_side"):
            cols = [r[0] for r in c.execute("""select column_name from information_schema.columns
                                               where table_schema = 'roads' and table_name = %s""", (view,))]
            self.assertFalse([col for col in cols if "comment" in col or "note" in col], view)

    def test_stale(self):
        c = self.conn
        self.fresh()
        self.assertFalse(bn.stale(c))                                           # nothing to match
        bn.store(c, self.fresh(), T1, features())
        self.assertTrue(bn.stale(c))                                            # records, no matches
        ids = self.segments()
        c.execute("""insert into roads.bike_facility_match (road_segment_id, object_id, method, matched_at)
                     values (%s, 1, 'buffer15_bearing20', now() + interval '1 hour')""", (ids["north"],))
        self.assertFalse(bn.stale(c))
        db.ensure_source(c, {"name": "achd_roads", "title": "t", "url": "https://example.invalid", "access": "open"})
        c.execute("""insert into raw.record (source, source_id, version_hash, payload, first_seen, last_seen)
                     values ('achd_roads', '-990399', '\\x01', '{}', now() + interval '2 hours', now())""")
        self.assertTrue(bn.stale(c))                                            # ACHD's segments changed since


if __name__ == "__main__":
    unittest.main()
