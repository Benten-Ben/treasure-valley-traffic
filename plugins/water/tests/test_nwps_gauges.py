"""Tests for the NWPS gauge poller: parsing, the ring, the per-gauge plan, flood episodes, the store."""

import contextlib
import copy
import io
import json
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db, events
from plugins.water.ingest.sources import nwps_gauges as nwps

from . import DB_URL, FakeConn, db_conn, fake_fetch, fixture

UTC = timezone.utc
NOW = datetime(2026, 10, 7, 14, 50, tzinfo=UTC)


def gauges():
    return nwps.parse_list(fixture("nwps_list.json"))


def with_category(g, cat, valid="2026-10-07T12:45:00Z", forecast=None):
    g = copy.deepcopy(g)
    g["status"]["observed"].update({"floodCategory": cat, "validTime": valid})
    if forecast:
        g["status"]["forecast"]["floodCategory"] = forecast
    return g


class ParseTest(unittest.TestCase):
    def test_the_list_asks_for_the_ring_in_wgs84(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(nwps.list_url()).query)
        self.assertEqual((q["bbox.xmin"], q["bbox.ymin"], q["bbox.xmax"], q["bbox.ymax"], q["srid"]),
                         (["-117.3"], ["42.9"], ["-115.6"], ["44.3"], ["EPSG_4326"]))
        self.assertEqual(nwps.stageflow_url("BIGI1", "forecast"),
                         "https://api.water.noaa.gov/nwps/v1/gauges/BIGI1/stageflow/forecast")

    def test_the_list_is_cut_to_the_ring(self):
        data = fixture("nwps_list.json")
        far = copy.deepcopy(data["gauges"][0])
        far.update({"lid": "FARI1", "longitude": -114.4})
        odd = copy.deepcopy(data["gauges"][0])
        odd.update({"lid": " tsti1"})                                  # case and spaces normalized
        nowhere = copy.deepcopy(data["gauges"][0])
        nowhere.update({"lid": "NOWI1", "latitude": None})
        data["gauges"] += [far, odd, nowhere]
        self.assertEqual(sorted(nwps.parse_list(data)), ["ARKI1", "BCJI1", "BIGI1", "EMMI1", "TSTI1"])
        self.assertEqual(nwps.parse_list({}), {})

    def test_a_listed_reading_is_the_same_record_as_the_series_one(self):
        g = gauges()["BIGI1"]
        latest = nwps.latest_reading("BIGI1", g)
        self.assertEqual(latest, {"lid": "BIGI1", "pe": "QRIRZ", "t": "2026-10-07T12:45:00Z", "primary": 0.379,
                                  "secondary": 3.6, "units": ["kcfs", "ft"]})
        series = nwps.series_readings("BIGI1", fixture("nwps_bigi1_stageflow.json")["observed"])
        same = [r for r in series if r["t"] == latest["t"]]
        self.assertEqual(same, [latest])
        self.assertEqual(db.version_hash(same[0]), db.version_hash(latest))

    def test_missing_values_are_null_and_empty_points_skipped(self):
        series = nwps.series_readings("BIGI1", fixture("nwps_bigi1_stageflow.json")["observed"])
        self.assertEqual([r["t"] for r in series], ["2026-09-07T14:45:00Z", "2026-09-07T15:00:00Z",
                                                    "2026-09-07T15:15:00Z", "2026-10-07T12:30:00Z",
                                                    "2026-10-07T12:45:00Z"])   # the -9999/-999 tail is dropped
        pool = nwps.latest_reading("ARKI1", gauges()["ARKI1"])              # a reservoir: pool elevation only
        self.assertEqual((pool["pe"], pool["primary"], pool["secondary"], pool["units"]),
                         ("HPIRG", 3126.26, None, ["ft", None]))
        self.assertIsNone(nwps.value(-9999))
        self.assertIsNone(nwps.value("n/a"))
        self.assertEqual(nwps.value(-12.5), -12.5)
        self.assertIsNone(nwps.reading("X", "HG", ("ft", "kcfs"), NOW, -999, -9999))
        self.assertIsNone(nwps.valid_time("0001-01-01T00:00:00Z"))

    def test_the_forecast_record(self):
        fc = nwps.forecast_payload("BIGI1", fixture("nwps_bigi1_stageflow.json")["forecast"])
        self.assertEqual((fc["issued"], fc["pe"], fc["units"]), ("2026-10-06T15:59:00Z", "QRIFZ", ["kcfs", "ft"]))
        self.assertEqual(fc["points"][0], ["2026-10-06T18:00:00Z", 0.4089, 3.7])
        self.assertEqual(len(fc["points"]), 4)
        self.assertEqual(nwps.forecast_payload("BCJI1", None),
                         {"lid": "BCJI1", "pe": None, "issued": None, "units": [None, None], "points": []})

    def test_the_gauge_record_keeps_flood_categories_and_drops_live_and_presentation_fields(self):
        p = nwps.gauge_payload(fixture("nwps_bigi1.json"))
        for gone in ("status", "images", "ObservedFloodCategory", "ForecastFloodCategory"):
            self.assertNotIn(gone, p)
        self.assertEqual(p["flood"]["categories"]["action"], {"stage": 9.7, "flow": 6500})
        self.assertEqual(p["flood"]["categories"]["major"]["flow"], 15000)
        self.assertTrue(p["flood"]["crests"]["historic"])
        self.assertNotIn("description", json.dumps(p["datums"]))
        self.assertEqual(set(p["inundation"]), {"enabled", "zeroDatum"})
        self.assertEqual((p["usgsId"], p["county"]), ("13206000", "Ada"))


class PlanTest(unittest.TestCase):
    def test_new_gauges_are_swept_oldest_first_within_the_budget(self):
        calls = nwps.plan(gauges(), {}, NOW, max_calls=4)
        self.assertEqual(calls, [("sweep", "ARKI1"), ("sweep", "BCJI1")])   # two requests each

    def test_a_flooding_gauge_gets_its_forecast_first(self):
        gs = gauges()
        gs["EMMI1"] = with_category(gs["EMMI1"], "no_flooding", forecast="minor")
        swept = {lid: NOW - timedelta(days=1) for lid in gs}
        clocks = {**swept, "EMMI1/forecast": NOW - timedelta(hours=4)}
        self.assertEqual(nwps.plan(gs, clocks, NOW)[0], ("forecast", "EMMI1"))
        clocks["EMMI1/forecast"] = NOW - timedelta(hours=1)
        self.assertNotIn(("forecast", "EMMI1"), nwps.plan(gs, clocks, NOW))

    def test_daily_forecasts_only_where_there_is_a_forecast_product(self):
        gs = gauges()
        clocks = {lid: NOW - timedelta(days=1) for lid in gs}
        clocks.update({f"{lid}/forecast": NOW - timedelta(hours=25) for lid in gs})
        self.assertEqual(sorted(nwps.plan(gs, clocks, NOW)),
                         [("forecast", "ARKI1"), ("forecast", "BIGI1"), ("forecast", "EMMI1")])  # not BCJI1

    def test_nothing_due(self):
        gs = gauges()
        clocks = {lid: NOW - timedelta(days=2) for lid in gs}
        clocks.update({f"{lid}/forecast": NOW - timedelta(hours=2) for lid in gs})
        self.assertEqual(nwps.plan(gs, clocks, NOW), [])

    def test_cheaper_calls_fill_what_a_sweep_leaves(self):
        gs = gauges()
        clocks = {"BIGI1": NOW - timedelta(days=8), "EMMI1": NOW - timedelta(days=9), "ARKI1": NOW, "BCJI1": NOW,
                  "ARKI1/forecast": NOW - timedelta(days=2)}
        self.assertEqual(nwps.plan(gs, clocks, NOW, max_calls=3), [("sweep", "EMMI1"), ("forecast", "ARKI1")])


class FloodTest(unittest.TestCase):
    def test_a_new_episode(self):
        gs = gauges()
        gs["BIGI1"] = with_category(gs["BIGI1"], "minor")
        rows = nwps.flood_rows(gs, {}, NOW)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["source_id"], r["kind"], r["severity"]), ("BIGI1:2026-10-07T12:45:00Z", "river_flood", "minor"))
        self.assertEqual(r["start"], datetime(2026, 10, 7, 12, 45, tzinfo=UTC))
        self.assertEqual(r["attributes"], {"lid": "BIGI1", "name": "Boise River at Boise (Glenwood Bridge)",
                                           "category": "minor", "peak_category": "minor"})
        self.assertEqual(r["geom"]["type"], "Point")
        self.assertIn("minor flooding", r["description"])

    def test_an_episode_continues_with_its_id_start_and_peak(self):
        gs = gauges()
        gs["BIGI1"] = with_category(gs["BIGI1"], "moderate", valid="2026-10-07T10:00:00Z")
        first = nwps.flood_rows(gs, {}, NOW)[0]
        stored = {**first, "content_hash": events.content_hash(first)}
        gs["BIGI1"] = with_category(gs["BIGI1"], "action", valid="2026-10-07T14:00:00Z")
        later = nwps.flood_rows(gs, {"BIGI1": stored}, NOW)[0]
        self.assertEqual((later["source_id"], later["start"]), (first["source_id"], first["start"]))
        self.assertEqual((later["severity"], later["attributes"]["peak_category"]), ("action", "moderate"))
        gs["BIGI1"] = with_category(gs["BIGI1"], "moderate", valid="2026-10-07T10:00:00Z")
        again = nwps.flood_rows(gs, {"BIGI1": stored}, NOW)[0]
        self.assertEqual(events.content_hash(again), events.content_hash(first))    # unchanged: nothing written

    def test_a_settled_category_ends_it_and_an_unreadable_one_keeps_it(self):
        gs = gauges()
        prev = {"source_id": "BIGI1:2026-10-07T10:00:00Z", "kind": "river_flood", "geom": None,
                "start": datetime(2026, 10, 7, 10, tzinfo=UTC), "end": None, "severity": "minor",
                "description": "x", "attributes": {"lid": "BIGI1", "peak_category": "minor"}, "content_hash": b"h"}
        self.assertEqual(nwps.flood_rows(gs, {"BIGI1": prev}, NOW), [])                 # no_flooding
        for cat in ("obs_not_current", "out_of_service", None):
            gs2 = dict(gs, BIGI1=with_category(gs["BIGI1"], cat))
            self.assertEqual(nwps.flood_rows(gs2, {"BIGI1": prev}, NOW), [prev], cat)
        del gs["BIGI1"]                                                                     # missing from the list
        self.assertEqual(nwps.flood_rows(gs, {"BIGI1": prev}, NOW), [prev])


class StoreTest(unittest.TestCase):
    def test_records_from_the_list_and_a_sweep(self):
        gs = gauges()
        got = [("sweep", "BIGI1", fixture("nwps_bigi1.json"), fixture("nwps_bigi1_stageflow.json")),
               ("forecast", "EMMI1", {})]
        readings, clock = nwps.records(gs, got)
        ids = [i for i, _, _ in readings]
        self.assertEqual(len(ids), 4 + 5)                      # four listed latest values, five series values
        self.assertIn("BIGI1@2026-10-07T12:45:00Z", ids)
        self.assertEqual(ids.count("BIGI1@2026-10-07T12:45:00Z"), 2)   # stored once: same payload
        self.assertEqual([i for i, _, _ in clock], ["BIGI1", "BIGI1/forecast", "EMMI1/forecast"])
        self.assertTrue(all(g and g["type"] == "Point" for _, _, g in readings + clock))

    def test_run_lists_plans_fetches_and_stores(self):
        bodies = {nwps.list_url(): fixture("nwps_list.json"),
                  nwps.gauge_url("ARKI1"): fixture("nwps_bigi1.json"),
                  nwps.stageflow_url("ARKI1"): fixture("nwps_bigi1_stageflow.json")}
        asked = []

        def get(url, timeout=90, compressed=False):
            asked.append(url)
            if url not in bodies:
                raise OSError("no route in this test")
            return 200, json.dumps(bodies[url]).encode(), "no_rules"

        conn = FakeConn({"insert into ops.fetch": [(1,)]})
        with mock.patch.object(nwps.http, "get", get), \
                mock.patch.object(db, "upsert_records", return_value=(1, 0, 0)) as up, \
                mock.patch.object(events, "upsert", return_value={"new": 0, "changed": 0, "unchanged": 0,
                                                                  "gone": 0}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            stats = nwps.run(conn)
        self.assertIn("sweep BCJI1: OSError", out.getvalue())
        self.assertEqual(asked, [nwps.list_url(), nwps.gauge_url("ARKI1"), nwps.stageflow_url("ARKI1"),
                                 nwps.gauge_url("BCJI1")])          # BCJI1's failure is counted, not fatal
        self.assertEqual((stats["gauges"], stats["calls"], stats["call errors"]), (4, 2, 1))
        self.assertEqual(up.call_count, 2)                            # readings, then the clock records
        fetch_update = [p for sql, p in conn.executed if sql.lstrip().startswith("update ops.fetch")][0]
        self.assertIs(fetch_update[1], True)                          # the fetch is logged as good

    def test_no_gauges_fails_the_fetch(self):
        conn = FakeConn({"insert into ops.fetch": [(1,)]})
        with mock.patch.object(nwps.http, "get", return_value=(200, b'{"gauges": []}', "no_rules")):
            with self.assertRaisesRegex(RuntimeError, "no gauges"):
                nwps.run(conn)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    """The store step against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        self.conn = db_conn(self, "raw.record", "evt.event")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_readings_once_clocks_move_and_floods_open_and_close(self):
        c = self.conn
        db.ensure_source(c, nwps.SOURCE)
        gs = gauges()
        gs["BIGI1"] = with_category(gs["BIGI1"], "minor")
        got = [("sweep", "BIGI1", fixture("nwps_bigi1.json"), fixture("nwps_bigi1_stageflow.json"))]
        s1 = nwps.store(c, fake_fetch(c, "nwps_gauges", NOW), NOW, gs, got)
        self.assertEqual((s1["reading versions new"], s1["readings held"]), (8, 1))
        self.assertEqual((s1["gauge and forecast versions new"], s1["floods new"]), (2, 1))
        later = NOW + timedelta(minutes=30)
        s2 = nwps.store(c, fake_fetch(c, "nwps_gauges", later), later, gs, got)
        self.assertEqual((s2["reading versions new"], s2["gauge and forecast versions new"]), (0, 0))
        self.assertEqual(s2["floods unchanged"], 1)
        self.assertEqual(nwps.clocks(c, ["BIGI1"])["BIGI1"], later)
        gs["BIGI1"] = with_category(gs["BIGI1"], "obs_not_current")
        s3 = nwps.store(c, fake_fetch(c, "nwps_gauges", later), later + timedelta(minutes=30), gs, [])
        self.assertEqual((s3["floods unchanged"], s3["floods gone"]), (1, 0))
        gs["BIGI1"] = with_category(gs["BIGI1"], "no_flooding")
        s4 = nwps.store(c, fake_fetch(c, "nwps_gauges", later), later + timedelta(hours=1), gs, [])
        self.assertEqual(s4["floods gone"], 1)


if __name__ == "__main__":
    unittest.main()
