"""Tests for the SNOTEL poller: the query window, station-hour records in UTC, element keys, the ring."""

import json
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db
from plugins.water.ingest import common
from plugins.water.ingest.sources import nrcs_snotel as snotel

from . import DB_URL, FakeConn, db_conn, fake_fetch, fixture

UTC = timezone.utc
NOW = datetime(2026, 10, 7, 14, 43, tzinfo=UTC)


class SnotelTest(unittest.TestCase):
    def test_the_four_stations_are_in_the_ring(self):
        self.assertEqual(sorted(snotel.STATIONS), ["2029:ID:SNTL", "423:ID:SNTL", "637:ID:SNTL", "978:ID:SNTL"])
        for triplet, (name, county, elev, lat, lon, tz) in snotel.STATIONS.items():
            self.assertTrue(common.in_ring(lon, lat), name)
            self.assertEqual(tz, -8.0)

    def test_the_query_asks_for_the_last_48_hours_in_station_time(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(snotel.query_url(NOW)).query)
        self.assertEqual(q["stationTriplets"], ["978:ID:SNTL,423:ID:SNTL,637:ID:SNTL,2029:ID:SNTL"])
        self.assertEqual((q["elements"], q["duration"], q["returnFlags"]), (["*"], ["HOURLY"], ["true"]))
        self.assertEqual(q["beginDate"], ["2026-10-05 06:43"])      # 14:43 UTC is 06:43 at UTC-8
        self.assertEqual(q["endDate"], ["2026-10-07 08:43"])

    def test_records_are_station_hours_in_utc(self):
        parsed = snotel.parse(fixture("snotel.json"))
        self.assertEqual(sorted(parsed)[:3], [("637:ID:SNTL", "2026-10-07T12:00:00Z"),
                                              ("637:ID:SNTL", "2026-10-07T13:00:00Z"),
                                              ("637:ID:SNTL", "2026-10-07T14:00:00Z")])
        r = parsed[("978:ID:SNTL", "2026-10-07T14:00:00Z")]
        self.assertEqual((r["local"], r["utc_offset"]), ("2026-10-07 06:00", -8.0))
        self.assertEqual(r["values"]["TOBS"], {"v": 48.6, "u": "degF", "qc": "V", "qa": "R"})
        self.assertEqual(sorted(r["values"]), ["BATT", "TOBS", "WTEQ"])
        early = parsed[("637:ID:SNTL", "2026-10-07T12:00:00Z")]     # only snow depth had reported 04:00
        self.assertEqual(list(early["values"]), ["SNWD"])
        recs = snotel.records(parsed)
        ids = [i for i, _, _ in recs]
        self.assertIn("978:ID:SNTL@2026-10-07T14:00:00Z", ids)
        self.assertEqual(dict((i, g) for i, _, g in recs)["978:ID:SNTL@2026-10-07T14:00:00Z"],
                         {"type": "Point", "coordinates": [-116.09685, 43.76377]})

    def test_unknown_stations_missing_values_and_bad_dates_are_skipped(self):
        data = [{"stationTriplet": "999:ID:SNTL", "data": fixture("snotel.json")[0]["data"]},
                {"stationTriplet": "978:ID:SNTL", "data": [
                    {"stationElement": {"elementCode": "TOBS", "ordinal": 1, "storedUnitCode": "degF"},
                     "values": [{"date": "2026-10-07 06:00", "value": None}, {"date": "06:00", "value": 1.0}]}]}]
        self.assertEqual(snotel.parse(data), {})

    def test_element_keys(self):
        self.assertEqual(snotel.element_key({"elementCode": "TOBS", "ordinal": 1}), "TOBS")
        self.assertEqual(snotel.element_key({"elementCode": "SMS", "ordinal": 2}), "SMS:2")
        self.assertEqual(snotel.element_key({"elementCode": "SMS", "ordinal": 1,
                                             "heightDepth": {"value": -8, "unitCode": "in"}}), "SMS@-8in")

    def test_a_revised_value_is_a_new_version(self):
        a = snotel.parse(fixture("snotel.json"))[("978:ID:SNTL", "2026-10-07T14:00:00Z")]
        data = fixture("snotel.json")
        data[0]["data"][1]["values"][-1]["qcFlag"] = "E"            # NRCS edits the flag later
        b = snotel.parse(data)[("978:ID:SNTL", "2026-10-07T14:00:00Z")]
        self.assertNotEqual(db.version_hash(a), db.version_hash(b))

    def test_run_stores_readings_and_refuses_an_empty_answer(self):
        body = json.dumps(fixture("snotel.json")).encode()
        conn = FakeConn({"insert into ops.fetch": [(1,)]})
        with mock.patch.object(snotel.http, "get", return_value=(200, body, "no_rules")) as get, \
                mock.patch.object(db, "upsert_records", return_value=(7, 0, 0)):
            stats = snotel.run(conn)
        self.assertTrue(get.call_args.args[0].startswith(snotel.API))
        self.assertEqual((stats["stations"], stats["station hours"], stats["versions new"]), (2, 5, 7))
        with mock.patch.object(snotel.http, "get", return_value=(200, b"[]", "no_rules")):
            with self.assertRaisesRegex(RuntimeError, "no SNOTEL values"):
                snotel.run(FakeConn({"insert into ops.fetch": [(1,)]}))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.conn = db_conn(self, "raw.record")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_a_window_read_twice_is_written_once(self):
        c = self.conn
        db.ensure_source(c, snotel.SOURCE)
        recs = snotel.records(snotel.parse(fixture("snotel.json")))
        self.assertEqual(common.store_readings(c, "nrcs_snotel", recs, fake_fetch(c, "nrcs_snotel", NOW), NOW),
                         (len(recs), 0))
        later = NOW + timedelta(hours=1)
        self.assertEqual(common.store_readings(c, "nrcs_snotel", recs, fake_fetch(c, "nrcs_snotel", later), later),
                         (0, len(recs)))


if __name__ == "__main__":
    unittest.main()
