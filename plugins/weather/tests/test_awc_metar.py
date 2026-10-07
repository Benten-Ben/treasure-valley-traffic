"""Tests for the Aviation Weather Center METAR source.

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL, inside a transaction that is rolled back. The
fixture is six real reports from AWC's answer for the ring on Oct 7, 2026
(NOAA data, a US Government work), trimmed from 27; the variants built below
(a station outside the ring, broken rows, a corrected report) are made up.

Run: python3 -m unittest discover -s plugins/weather/tests -t .
"""

import copy
import json
import os
import re
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import db, manifest
from ingest.db import version_hash
from plugins.weather.ingest.sources import awc_metar as awc

UTC = timezone.utc
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
T0 = datetime(2026, 10, 7, 14, 30, tzinfo=UTC)


def fixture():
    with open(os.path.join(HERE, "fixtures", "awc_metar_ring.json"), encoding="utf-8") as f:
        return json.load(f)


def by_station(rows, icao, kind="METAR"):
    return next(r for r in rows if r["icaoId"] == icao and r["metarType"] == kind)


class QueryTest(unittest.TestCase):
    def test_one_bounding_box_request_over_the_ring_in_json(self):
        url = awc.query_url(7)
        parts = urllib.parse.urlsplit(url)
        self.assertEqual(f"{parts.scheme}://{parts.netloc}{parts.path}", "https://aviationweather.gov/api/data/metar")
        self.assertIn("bbox=42.90,-117.30,44.30,-115.60", url)      # lat0,lon0,lat1,lon1, commas as AWC shows them
        self.assertEqual(urllib.parse.parse_qs(parts.query),
                         {"bbox": ["42.90,-117.30,44.30,-115.60"], "format": ["json"], "hours": ["7"]})

    def test_the_lookback_covers_the_gap_since_the_last_good_fetch(self):
        self.assertEqual(awc.lookback_hours(None, T0), 24)                         # first run: a day
        self.assertEqual(awc.lookback_hours(T0 - timedelta(minutes=10), T0), 7)    # the usual poll
        self.assertEqual(awc.lookback_hours(T0, T0), 6)
        self.assertEqual(awc.lookback_hours(T0 - timedelta(hours=3, minutes=1), T0), 10)
        self.assertEqual(awc.lookback_hours(T0 - timedelta(days=3), T0), 24)       # capped; IEM has the rest
        self.assertEqual(awc.lookback_hours(T0 + timedelta(hours=1), T0), 6)       # a clock that ran ahead

    def test_a_day_at_the_ring_stays_well_under_awcs_cap(self):
        # About 9 reports an hour on Oct 7 (27 in 3 h, during a haze episode with 6 specials).
        self.assertLess(9 * awc.MAX_HOURS, awc.MAX_ENTRIES * 0.6)


class ParseTest(unittest.TestCase):
    def test_reports_are_keyed_by_station_and_observation_time(self):
        records, counts = awc.parse(fixture())
        self.assertEqual([sid for sid, _, _ in records], [
            "KBOI 2026-10-07T13:53Z", "KONO 2026-10-07T13:53Z", "KEUL 2026-10-07T13:29Z",
            "KEUL 2026-10-07T12:56Z", "KMUO 2026-10-07T12:55Z", "KMAN 2026-10-07T11:55Z"])
        self.assertEqual(counts, {"outside the ring": 0, "unusable": 0})

    def test_routine_reports_and_specials_are_both_kept_with_their_raw_text(self):
        records, _ = awc.parse(fixture())
        kinds = {sid: p["metarType"] for sid, p, _ in records}
        self.assertEqual(kinds["KEUL 2026-10-07T13:29Z"], "SPECI")
        self.assertEqual(kinds["KEUL 2026-10-07T12:56Z"], "METAR")
        payload = dict((sid, p) for sid, p, _ in records)["KEUL 2026-10-07T12:56Z"]
        self.assertEqual(payload["rawOb"], "METAR KEUL 071256Z AUTO 00000KT 3/4SM HZ CLR 07/03 A3013 RMK AO2 "
                                           "VIS 1/4V5 SLP192 T00670028 $")

    def test_the_payload_is_awcs_record_without_the_display_name(self):
        rows = fixture()
        records, _ = awc.parse(rows)
        for (sid, payload, geom), row in zip(records, rows):
            self.assertNotIn("name", payload)
            self.assertEqual(payload, {k: v for k, v in row.items() if k != "name"})
            self.assertEqual(geom, {"type": "Point", "coordinates": [row["lon"], row["lat"]]})
        payloads = {sid: p for sid, p, _ in records}
        self.assertEqual(payloads["KBOI 2026-10-07T13:53Z"]["visib"], "10+")      # text, left as AWC gives it
        self.assertEqual(payloads["KEUL 2026-10-07T12:56Z"]["visib"], 0.75)
        self.assertEqual(payloads["KMAN 2026-10-07T11:55Z"]["pcp24hr"], 0.005)
        self.assertEqual(payloads["KMUO 2026-10-07T12:55Z"]["receiptTime"], "2026-10-07T14:18:17.557Z")  # 83 min late

    def test_cloud_layers_are_kept(self):
        row = copy.deepcopy(by_station(fixture(), "KBOI"))
        row.update(cover="BKN", clouds=[{"cover": "FEW", "base": 4500}, {"cover": "BKN", "base": 9000}])
        (_, payload, _), = awc.parse([row])[0]
        self.assertEqual(payload["clouds"], [{"cover": "FEW", "base": 4500}, {"cover": "BKN", "base": 9000}])

    def test_reports_outside_the_ring_are_dropped(self):
        far = dict(by_station(fixture(), "KBOI"), icaoId="KXYZ", lat=44.89, lon=-116.10)   # north of the ring
        zero = dict(by_station(fixture(), "KBOI"), icaoId="KXYW", lat=0, lon=0)            # AWC's default position
        records, counts = awc.parse(fixture() + [far, zero])
        self.assertEqual(len(records), 6)
        self.assertEqual(counts, {"outside the ring": 2, "unusable": 0})
        self.assertTrue(awc.in_ring(-117.30, 42.90) and awc.in_ring(-115.60, 44.30))     # edges are in

    def test_unusable_rows_are_counted_not_stored(self):
        good = by_station(fixture(), "KBOI")
        bad = [
            "not a report",
            {k: v for k, v in good.items() if k != "obsTime"},
            dict(good, obsTime=True),
            dict(good, obsTime=10 ** 12),
            dict(good, icaoId="boi airport"),
            dict(good, rawOb="  "),
            {k: v for k, v in good.items() if k != "lat"},
        ]
        records, counts = awc.parse(bad + [good])
        self.assertEqual([sid for sid, _, _ in records], ["KBOI 2026-10-07T13:53Z"])
        self.assertEqual(counts["unusable"], len(bad))

    def test_a_corrected_report_is_a_new_version_of_the_same_record(self):
        row = by_station(fixture(), "KBOI")
        cor = dict(row, rawOb=row["rawOb"].replace("071353Z", "071353Z COR").replace("13004KT", "13005KT"), wspd=5,
                   receiptTime="2026-10-07T14:05:00.000Z")
        (a, pa, _), = awc.parse([row])[0]
        (b, pb, _), = awc.parse([cor])[0]
        self.assertEqual(a, b)
        self.assertNotEqual(version_hash(pa), version_hash(pb))

    def test_decode(self):
        self.assertEqual(awc.decode(b""), [])                  # HTTP 204: no data
        self.assertEqual(awc.decode(b"[]\n"), [])
        self.assertEqual(len(awc.decode(json.dumps(fixture()).encode())), 6)
        with self.assertRaises(RuntimeError):
            awc.decode(b'{"status": "error", "error": "Invalid bbox"}')


class FakeFetch:
    """Stands in for db.Fetch: records what run() set on it."""
    last = None

    def __init__(self, conn, source):
        self.source, self.id, self.started_at = source, 41, T0
        self.http_status = self.robots = self.records = self.bytes = None

    def __enter__(self):
        FakeFetch.last = self
        return self

    def __exit__(self, *exc):
        return False


class RunTest(unittest.TestCase):
    def run_with(self, status, body, last_good=T0 - timedelta(minutes=10)):
        with mock.patch.object(awc.db, "Fetch", FakeFetch), mock.patch.object(awc.db, "ensure_source"), \
                mock.patch.object(awc.db, "now", return_value=T0), \
                mock.patch.object(awc, "last_good_fetch", return_value=last_good), \
                mock.patch.object(awc.http, "get", return_value=(status, body, "no_rules")) as get, \
                mock.patch.object(awc.db, "upsert_records", return_value=(5, 1, 0)) as upsert:
            stats = awc.run(object())
        return stats, get, upsert

    def test_a_run_stores_every_report_as_a_reading_not_a_snapshot(self):
        body = json.dumps(fixture()).encode()
        stats, get, upsert = self.run_with(200, body)
        self.assertEqual(get.call_count, 1)
        self.assertIn("hours=7", get.call_args.args[0])
        args, kwargs = upsert.call_args
        self.assertEqual((args[1], args[3], args[4]), ("awc_metar", 41, T0))
        self.assertEqual(len(args[2]), 6)
        self.assertIs(kwargs["complete"], False)
        self.assertEqual(stats, {"hours asked": 7, "reports": 6, "record versions new": 5, "unchanged": 1,
                                 "stations": 5, "specials": 1, "outside the ring": 0, "unusable": 0,
                                 "at AWC's cap": False})
        f = FakeFetch.last
        self.assertEqual((f.http_status, f.robots, f.records, f.bytes), (200, "no_rules", 6, len(body)))

    def test_the_first_run_asks_for_a_day(self):
        _, get, _ = self.run_with(200, json.dumps(fixture()).encode(), last_good=None)
        self.assertIn("hours=24", get.call_args.args[0])

    def test_an_empty_answer_fails_the_fetch(self):
        with self.assertRaises(RuntimeError):
            self.run_with(204, b"")
        self.assertEqual(FakeFetch.last.http_status, 204)
        with self.assertRaises(RuntimeError):         # answered, but nothing inside the ring
            self.run_with(200, json.dumps([dict(by_station(fixture(), "KBOI"), lat=0, lon=0)]).encode())

    def test_an_http_error_is_logged_with_its_status(self):
        err = urllib.error.HTTPError(awc.API, 429, "Too Many Requests", None, None)
        with mock.patch.object(awc.db, "Fetch", FakeFetch), mock.patch.object(awc.db, "ensure_source"), \
                mock.patch.object(awc, "last_good_fetch", return_value=None), \
                mock.patch.object(awc.http, "get", side_effect=err), self.assertRaises(urllib.error.HTTPError):
            awc.run(object())
        self.assertEqual(FakeFetch.last.http_status, 429)

    def test_an_answer_at_awcs_cap_is_stored_and_flagged(self):
        rows = []
        start = by_station(fixture(), "KMAN")
        for i in range(awc.MAX_ENTRIES):
            rows.append(dict(start, obsTime=start["obsTime"] - 60 * i))
        stats, _, upsert = self.run_with(200, json.dumps(rows).encode())
        self.assertEqual(len(upsert.call_args.args[2]), awc.MAX_ENTRIES)
        self.assertTrue(stats["at AWC's cap"])


class ManifestTest(unittest.TestCase):
    def test_the_manifest_loads_and_agrees_with_the_module(self):
        plugin = manifest.load(PLUGIN)
        self.assertEqual((plugin.name, plugin.visibility, plugin.depends, plugin.order), ("weather", "public", [], 65))
        entry, = plugin.manifest["sources"]
        self.assertEqual((entry["name"], entry["module"], entry["kind"]),
                         (awc.SOURCE["name"], "ingest.sources.awc_metar", "source"))
        self.assertEqual((entry["license"], entry["credit"]), (awc.SOURCE["license"], awc.SOURCE["credit"]))
        self.assertEqual(entry["republish"], "yes")

    def test_the_schedule_is_an_interval_of_at_least_ten_minutes(self):
        m = re.fullmatch(r"(\d+) (minute|hour|day)s?", awc.SOURCE["schedule"])
        self.assertIsNotNone(m)
        minutes = int(m.group(1)) * {"minute": 1, "hour": 60, "day": 1440}[m.group(2)]
        self.assertGreaterEqual(minutes, 10)
        self.assertEqual(awc.SOURCE["access"], "open")


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    """store() and the lookback query against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, at, ok=True):
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, %s) returning id",
                                 (awc.SOURCE["name"], at, ok)).fetchone()[0]

    def test_reports_are_versioned_and_never_retired(self):
        c = self.conn
        db.ensure_source(c, awc.SOURCE)
        t0 = datetime(2099, 1, 1, tzinfo=UTC)     # later than any real fetch in the scratch database
        records, _ = awc.parse(fixture())
        self.assertEqual(awc.store(c, self.fetch(t0), t0, records), (6, 0))
        # Ten minutes later: one report corrected, the rest unchanged, one gone from the answer.
        row = by_station(fixture(), "KBOI")
        cor = dict(row, rawOb=row["rawOb"].replace("071353Z", "071353Z COR"))
        later, _ = awc.parse([cor] + fixture()[1:5])
        t1 = t0 + timedelta(minutes=10)
        self.assertEqual(awc.store(c, self.fetch(t1), t1, later), (1, 4))
        versions = c.execute("""select count(*), count(distinct version_hash) from raw.record
                                where source = 'awc_metar' and source_id = 'KBOI 2026-10-07T13:53Z'""").fetchone()
        self.assertEqual(versions, (2, 2))
        self.assertEqual(c.execute("""select count(*) from raw.record where source = 'awc_metar'
                                      and first_seen >= %s and removed_at is not null""", (t0,)).fetchone()[0], 0)
        geom = c.execute("""select ST_X(geom), ST_Y(geom) from raw.record
                            where source = 'awc_metar' and source_id = 'KMUO 2026-10-07T12:55Z'""").fetchone()
        self.assertEqual(geom, (-115.859, 43.03))
        # A failed fetch afterwards doesn't count as the last good one.
        self.fetch(t1 + timedelta(minutes=10), ok=False)
        self.assertEqual(awc.last_good_fetch(c), t1)


if __name__ == "__main__":
    unittest.main()
