"""Tests for the COMPASS sources (ingest/sources/compass_*.py), on small synthetic records
(made-up values in COMPASS's formats; no record is copied from its layers).

The offline tests cover paging, the dev page cap, retries and pacing, parsing
(ArcGIS dates, codes, placeholders), key stability, the restricted person
rows and the zones' census/estimate/forecast split. The database tests run
only against a scratch database named by TVT_TEST_DATABASE_URL (a clone with
migration 0012); they work inside one transaction and roll it back.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import os
import random
import unittest
import urllib.error
from datetime import date, datetime, timezone

from ingest import http
from ingest.sources import (compass_congestion, compass_counts, compass_crashes, compass_growth, compass_layer as cl,
                            compass_plats)

MS_2008_06_01 = 1212278400000          # 2008-06-01 00:00 UTC: how COMPASS stores the day
MS_2025_01_15 = 1736899200000
MS_2025_08_20 = 1755648000000


def page(n, start=0, exceeded=None, geojson=False):
    feats = [{"properties" if geojson else "attributes": {"objectid": start + i}, "geometry": None} for i in range(n)]
    data = {"features": feats}
    if exceeded is not None:
        if geojson:
            data["properties"] = {"exceededTransferLimit": exceeded}
        else:
            data["exceededTransferLimit"] = exceeded
    return json.dumps(data).encode()


class FakeServer:
    """Serves the given page bodies in order and records the requested URLs."""

    def __init__(self, *bodies):
        self.bodies, self.urls = list(bodies), []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        body = self.bodies.pop(0)
        if isinstance(body, Exception):
            raise body
        return 200, body, "no_rules"


def read(server, limit=None, page_size=3, geometry=False):
    return cl.read("X/FeatureServer/0", ["objectid"], geometry, limit=limit, get=server, sleep=lambda s: None,
                   page=page_size)


class PagingTest(unittest.TestCase):
    def test_stops_on_a_short_page(self):
        server = FakeServer(page(3, 0, exceeded=True), page(3, 3, exceeded=True), page(1, 6))
        got = read(server)
        self.assertEqual([p["objectid"] for p, _ in got.rows], list(range(7)))
        self.assertEqual((got.pages, got.complete), (3, True))
        self.assertIn("resultOffset=6", server.urls[-1])

    def test_a_full_page_without_the_flag_needs_one_more_look(self):
        got = read(FakeServer(page(3, 0), page(0)))
        self.assertEqual((len(got.rows), got.pages, got.complete), (3, 2, True))

    def test_the_flag_continues_even_on_a_short_page(self):
        # A server whose own limit is below our page size still says there's more.
        got = read(FakeServer(page(2, 0, exceeded=True), page(2, 2, exceeded=True, geojson=True), page(1, 4)))
        self.assertEqual(len(got.rows), 5)

    def test_server_error_in_the_body_raises(self):
        with self.assertRaises(RuntimeError):
            read(FakeServer(json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode()))

    def test_query_asks_for_pages_in_objectid_order(self):
        url = cl.query_url("A/FeatureServer/0", ["objectid", "pm_id"], 4000, True)
        self.assertIn("orderByFields=objectid", url)
        self.assertIn("resultOffset=4000", url)
        self.assertIn("outSR=4326", url)
        self.assertIn("f=geojson", url)
        self.assertIn("outFields=objectid,pm_id", url)
        self.assertIn("f=json", cl.query_url("A/FeatureServer/4", ["objectid"], 0, False))


class PageCapTest(unittest.TestCase):
    def test_the_cap_stops_early_and_marks_the_read_incomplete(self):
        server = FakeServer(*(page(3, 3 * i, exceeded=True) for i in range(5)))
        got = read(server, limit=2)
        self.assertEqual((got.pages, len(got.rows), got.complete), (2, 6, False))
        self.assertEqual(len(server.urls), 2)

    def test_a_layer_that_fits_under_the_cap_is_complete(self):
        got = read(FakeServer(page(2, 0)), limit=3)
        self.assertTrue(got.complete)

    def test_the_cap_comes_from_the_environment(self):
        old = os.environ.pop(cl.MAX_PAGES_ENV, None)
        try:
            self.assertIsNone(cl.max_pages())
            os.environ[cl.MAX_PAGES_ENV] = "3"
            self.assertEqual(cl.max_pages(), 3)
            for bad in ("0", "x", "-1"):
                os.environ[cl.MAX_PAGES_ENV] = bad
                with self.assertRaises(SystemExit):
                    cl.max_pages()
        finally:
            os.environ.pop(cl.MAX_PAGES_ENV, None)
            if old is not None:
                os.environ[cl.MAX_PAGES_ENV] = old

    def test_an_incomplete_run_marks_nothing_removed(self):
        seen = []

        def store(conn, fetch_id, seen_at, got):
            seen.append(got.complete)
            return {}

        class Conn:
            def execute(self, *a, **k):
                return self

            def fetchone(self):
                return (1,)

            def commit(self):
                pass

            def rollback(self):
                pass

        def reader(path, fields, geometry, limit=None):
            return read(FakeServer(*(page(3, 3 * i, exceeded=True) for i in range(5))), limit=limit)

        os.environ[cl.MAX_PAGES_ENV] = "2"
        try:
            stats = cl.run(Conn(), {"name": "m", "title": "t", "url": "u", "access": "open"},
                           [cl.Layer("l", {"name": "s", "title": "t", "url": "u", "access": "open"}, "p", [], store)],
                           reader=reader)
        finally:
            os.environ.pop(cl.MAX_PAGES_ENV, None)
        self.assertEqual(seen, [False])
        self.assertEqual(stats["l capped at pages"], 2)


class RetryTest(unittest.TestCase):
    def call(self, *responses):
        server, sleeps = FakeServer(*responses), []
        result = cl.get_retried("https://swidrdc.org/x", get=server, sleep=sleeps.append)
        return result, len(server.urls), sleeps

    def test_resets_are_retried_twice(self):
        result, calls, sleeps = self.call(ConnectionResetError("reset by peer"), b"{}")
        self.assertEqual((result[1], calls, sleeps), (b"{}", 2, [10]))
        result, calls, sleeps = self.call(ConnectionResetError("1"), ConnectionResetError("2"), b"{}")
        self.assertEqual((result[1], calls, sleeps), (b"{}", 3, [10, 30]))

    def test_an_unreadable_robots_txt_is_retried(self):
        _, calls, _ = self.call(http.RobotsUnavailable("couldn't read"), b"{}")
        self.assertEqual(calls, 2)

    def test_a_third_failure_gives_up(self):
        with self.assertRaises(OSError):
            self.call(ConnectionResetError("1"), ConnectionResetError("2"), ConnectionResetError("3"))

    def test_client_errors_and_disallows_are_not_retried(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.call(urllib.error.HTTPError("u", 404, "Not Found", {}, None))
        with self.assertRaises(http.RobotsDisallowed):
            self.call(http.RobotsDisallowed("no"))


class PacerTest(unittest.TestCase):
    def test_waits_the_gap_after_the_last_request_ended(self):
        now, slept = [100.0], []
        pacer = cl.Pacer(gap=1.5, clock=lambda: now[0], sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
        pacer.wait()                       # first request: no wait
        now[0] += 0.4                      # it takes 0.4 s
        pacer.done()
        pacer.wait()
        self.assertEqual(slept, [1.5])
        now[0] += 0.2
        pacer.done()
        now[0] += 2.0                      # slow processing in between: no extra wait
        pacer.wait()
        self.assertEqual(slept, [1.5])


class ValuesTest(unittest.TestCase):
    def test_text(self):
        self.assertEqual(cl.text("  Dark,  Street Lights On "), "Dark, Street Lights On")
        self.assertEqual(cl.text("Water Ã¢â‚¬â€œ standing/moving"), "Water – standing/moving")
        self.assertEqual(cl.text("Emotional â€“ Depressed"), "Emotional – Depressed")
        for blank in (None, "", " ", "#NAME?"):
            self.assertIsNone(cl.text(blank))

    def test_flags(self):
        self.assertEqual([cl.flag(v) for v in ("Y", "N", "-U", "#NAME?", "", None, 1.0, 0, "Yes")],
                         [True, False, None, None, None, None, True, False, True])

    def test_pm_id_placeholders_are_null(self):
        for placeholder in ("#NYA", "#nya", "01 needs PMID", "Int-Related", "Off-System", "Intersection*", "Local",
                            "_", "", None):
            self.assertIsNone(cl.pm_id(placeholder), placeholder)
        for real in ("A00000002000", "Int000000w01x", "10t000002", "CAL00000018", "000000001000"):
            self.assertEqual(cl.pm_id(real), real)

    def test_numbers(self):
        self.assertEqual(cl.number("9.502044"), 9.502044)
        self.assertIsNone(cl.number("n/a"))
        self.assertEqual(cl.integer(538.6), 539)
        self.assertIsNone(cl.integer(None))

    def test_arcgis_dates(self):
        self.assertEqual(cl.epoch_date(MS_2008_06_01), date(2008, 6, 1))
        self.assertEqual(cl.epoch_date(MS_2008_06_01 + 6 * 3600 * 1000), date(2008, 6, 1))   # stored as local midnight
        self.assertEqual(cl.epoch_ms(1728447611000), datetime(2024, 10, 9, 4, 20, 11, tzinfo=timezone.utc))
        self.assertIsNone(cl.epoch_date(None))


def crash(**over):
    props = {"serialnumber": "08C900001", "accident_date": MS_2008_06_01, "accidentdate": "6/1/2008 16:45",
             "accidenttime": "16:45", "severity": "Property Dmg Report", "units": 1, "person": 1, "fatalities": 0,
             "injuries": 0, "light": "Day", "weather": "Clear", "roadsurfaceconditions": "Dry",
             "workzonerelated": "N", "intersectionrelated": "N", "street1": "Example Blvd",
             "intersectiondistance": "5280.0000 F", "pmid": "CAL00000001", "int_id": "Non-IntersectionNon-Intersection",
             "latitude": 43.6, "longitude": -116.6}
    props.update(over)
    return props


class CrashParseTest(unittest.TestCase):
    def test_local_time_in_summer_and_winter(self):
        t, known = compass_crashes.crash_time(crash())
        self.assertTrue(known)
        self.assertEqual(t.astimezone(timezone.utc), datetime(2008, 6, 1, 22, 45, tzinfo=timezone.utc))   # MDT
        t, _ = compass_crashes.crash_time(crash(accident_date=MS_2025_01_15, accidentdate="2025-01-15 08:00:00",
                                                accidenttime="08:00:00"))
        self.assertEqual(t.astimezone(timezone.utc), datetime(2025, 1, 15, 15, 0, tzinfo=timezone.utc))    # MST

    def test_time_comes_from_the_text_when_the_time_field_is_missing(self):
        t, known = compass_crashes.crash_time(crash(accident_date=MS_2025_08_20, accidentdate="2025-08-20 05:10:00",
                                                    accidenttime=None))
        self.assertEqual((t.hour, t.minute, known), (5, 10, True))

    def test_missing_time_is_local_midnight_and_flagged(self):
        t, known = compass_crashes.crash_time(crash(accidentdate=None, accidenttime=""))
        self.assertEqual((t.date(), t.hour, known), (date(2008, 6, 1), 0, False))
        self.assertEqual(t.utcoffset().total_seconds(), -6 * 3600)
        _, known = compass_crashes.crash_time(crash(accidenttime="-U", accidentdate="6/1/2008 -U"))
        self.assertFalse(known)
        _, known = compass_crashes.crash_time(crash(accidenttime="99:99", accidentdate="6/1/2008"))
        self.assertFalse(known)

    def test_the_day_falls_back_to_the_text(self):
        t, known = compass_crashes.crash_time(crash(accident_date=None, accidentdate="12/20/2008 18:15",
                                                    accidenttime=None))
        self.assertEqual(t.astimezone(timezone.utc), datetime(2008, 12, 21, 1, 15, tzinfo=timezone.utc))
        self.assertTrue(known)
        self.assertEqual(compass_crashes.crash_time(crash(accident_date=None, accidentdate=None)), (None, False))

    def test_codes_and_placeholders(self):
        r = compass_crashes.crash_row(crash(severity="A Injury Accident", workzonerelated="#NAME?",
                                            roadsurfaceconditions="Water Ã¢â‚¬â€œ standing/moving"))
        self.assertEqual((r["severity"], r["work_zone"], r["surface"]), ("A", None, "Water standing/moving"))
        self.assertEqual((r["pm_id"], r["int_id"], r["distance_ft"]), ("CAL00000001", None, 5280.0))
        self.assertEqual(compass_crashes.crash_row(crash(severity="Fatal Accident", workzonerelated="-U"))["severity"],
                         "K")
        self.assertEqual(compass_crashes.distance_ft("0.2500 M"), 1320.0)
        self.assertEqual(r["geom"], {"type": "Point", "coordinates": [-116.6, 43.6]})

    def test_int_ids(self):
        f = compass_crashes.int_id
        self.assertEqual([f("ACHD_900ACHD_900"), f("INT_0900"), f("INT_ 9001"), f("ACHD_009")],
                         ["ACHD_900", "INT_0900", "INT_9001", "ACHD_009"])
        for placeholder in ("_", "__", "Off SystemOff System", "LocalLocal", "n_a", "S00000000001",
                            "2390000.5_720000.25", None):
            self.assertIsNone(f(placeholder), placeholder)


class KeyTest(unittest.TestCase):
    def test_keys_do_not_depend_on_order(self):
        items = [{"k": "a", "v": 1}, {"k": "a", "v": 1}, {"k": "a", "v": 2}, {"k": "a", "v": 3}, {"k": "b", "v": 1}]
        first, dropped, suffixed = cl.keyed(items, key=lambda i: i["k"])
        self.assertEqual((dropped, suffixed), (1, 2))
        self.assertEqual(sorted(k for k, _ in first), ["a", "a#2", "a#3", "b"])
        for _ in range(5):
            random.shuffle(items)
            again, _, _ = cl.keyed(items, key=lambda i: i["k"])
            self.assertEqual(sorted(map(repr, again)), sorted(map(repr, first)))

    def test_people_keep_their_seq_whatever_the_order(self):
        rows = [compass_crashes.unit_row({"serialnumber": "S1", "unitnumber": 1, "age": a, "sex": s,
                                          "unittype": "Car"}) for a, s in ((30, "M"), (8, "F"), (30, "M"), (70, "F"))]
        first = {(r["serial_number"], r["unit_number"], r["seq"]): r["content_hash"]
                 for r in compass_crashes.number_people(rows)}
        self.assertEqual(len(first), 4)                       # identical people still get their own rows
        for _ in range(5):
            random.shuffle(rows)
            again = {(r["serial_number"], r["unit_number"], r["seq"]): r["content_hash"]
                     for r in compass_crashes.number_people(rows)}
            self.assertEqual(again, first)

    def test_congestion_segments(self):
        sid = compass_congestion.segment_id
        line = {"type": "LineString", "coordinates": [[-116.25, 43.62], [-116.24, 43.62]]}
        self.assertEqual(sid({"roadway_id": "117-00001"}, line), ("117-00001", "tmc"))
        self.assertEqual(sid({"roadway_id": "117N00002"}, line), ("117N00002", "tmc"))
        self.assertEqual(sid({"roadway_id": "1100000001"}, line), ("1100000001", "xd"))
        east = sid({"roadway_id": "2", "road_direction": "E", "roadname": "W Example St"}, line)
        self.assertEqual(east[1], "geometry")
        self.assertEqual(east, sid({"roadway_id": "1", "road_direction": "E", "roadname": "W Example St"}, line))
        self.assertNotEqual(east, sid({"roadway_id": "2", "road_direction": "W", "roadname": "W Example St"}, line))

    def test_count_locations(self):
        placeholder = {"agency": "ACHD", "road": "Example  Rd", "location": "e/o Sample Ave ", "pm_id": "#NYA"}
        self.assertEqual(compass_counts.portable_key(placeholder), "loc:achd|example rd|e/o sample ave")
        self.assertEqual(compass_counts.portable_key({**placeholder, "pm_id": "#nya", "location": "E/O Sample Ave"}),
                         "loc:achd|example rd|e/o sample ave")
        # Portable counts: one per segment, whatever the location text says.
        self.assertEqual(compass_counts.portable_key({**placeholder, "pm_id": "000000001001"}), "pm:000000001001")
        # Permanent counters: one per direction on the interstate, two on some segments.
        east = {"agency": "ITD", "road": "I 84", "location": "0.5 miles w/o Example Rd", "pm_id": "Int000000e99"}
        self.assertEqual(compass_counts.atr_key(east), "loc:itd|i 84|0.5 miles w/o example rd|Int000000e99")
        self.assertNotEqual(compass_counts.atr_key(east), compass_counts.atr_key({**east, "pm_id": "Int000000w99"}))


class RestrictedTest(unittest.TestCase):
    PERSON = {"serialnumber": "TEST-S1", "unitnumber": 1, "unittype": "Pedestrian", "direction": "w",
              "action_": "Going Straight", "event": "Pedestrian", "location": "Nonjunction",
              "contributingfactors": ",Failed to Yield", "injury": "Suspected Serious Injury", "age": 37,
              "sex": "#NAME?", "residencestate": "Testlandia", "protectiondevice": "None", "ejection": "Not Ejected",
              "citation": "4242-ZZTEST"}

    def test_people_are_coded_and_coarsened(self):
        r = compass_crashes.unit_row(self.PERSON)
        self.assertEqual((r["age_group"], r["sex"], r["idaho_resident"], r["injury"]), ("35-44", None, False, "A"))
        self.assertEqual((r["cited"], r["citation"]), (None, None))       # a bare number: maybe a ticket number
        self.assertEqual((r["direction"], r["contributing_factor"]), ("W", "Failed to Yield"))
        self.assertNotIn("Testlandia", json.dumps(r))
        self.assertNotIn("37", json.dumps(r))
        self.assertNotIn("ZZTEST", json.dumps(r))

    def test_citations_ages_residence(self):
        c = compass_crashes.citation
        self.assertEqual(c("DRIVING Following too close"), (True, "DRIVING Following too close"))
        self.assertEqual(c("Not Cited"), (False, None))
        for junk in ("49-000", "1234567-01-01-01", "Starting in Traffic", "", None):
            self.assertEqual(c(junk), (None, None), junk)
        self.assertEqual([compass_crashes.age_group(a) for a in (0, 16, 20, 21, 74, 75, 999, None)],
                         ["0-15", "16-20", "16-20", "21-24", "65-74", "75+", None, None])
        self.assertEqual([compass_crashes.resident(v) for v in ("Idaho", "Oregon", "Unknown", None)],
                         [True, False, None, None])

    def test_identifying_fields_are_never_requested(self):
        self.assertNotIn("agencycaseid", compass_crashes.CRASH_FIELDS)
        for f in ("unitid", "person", "seating", "street1"):
            self.assertNotIn(f, compass_crashes.UNIT_FIELDS)
        for f in ("address", "parcel_no", "comment", "created_user", "last_edited_user"):
            self.assertNotIn(f, compass_growth.PERMIT_FIELDS)
        self.assertNotIn("comments", compass_plats.FIELDS)

    def test_person_rows_only_have_restricted_columns(self):
        r = compass_crashes.number_people([compass_crashes.unit_row(self.PERSON)])[0]
        self.assertEqual(set(r), {"serial_number", "unit_number", "seq", "unit_type", "direction", "action", "event",
                                  "location", "contributing_factor", "injury", "age_group", "sex", "idaho_resident",
                                  "protection_device", "ejection", "cited", "citation", "content_hash"})

    def test_terms(self):
        self.assertIn("restricted", compass_crashes.UNITS["notes"])
        for s in (compass_congestion.SOURCE, compass_congestion.MEASURES, compass_congestion.COMMUTES):
            self.assertEqual(s["license"], cl.INTERNAL_LICENSE)
            self.assertIn("internal use", s["notes"])
        for m in (compass_crashes, compass_counts, compass_growth, compass_plats, compass_congestion):
            self.assertEqual(m.SOURCE["credit"], "COMPASS and COMPASS member agencies")
        self.assertEqual(compass_plats.SOURCE["schedule"], "7 days")


# All demographic fields of TAZDemogDetail_Reconciled, as listed Oct 6, 2026.
TAZ_FIELDS = ("tpopcensus grpqtrcens popcensus hhcensus tpopest22 gqrest22 popest22 hhest22 tpopest23 gqrest23 "
              "hhest23 popest23 tpopest24 gqrest24 popest24 hhest24 tpopest25 rjobs25 pop25est hh25est pop30f hh30f "
              "tpop30f jobs30f tpop35f pop35f hh35f jobs35f tpop40f pop40f hh40f jobs40f tpop45f pop45f hh45f "
              "jobs45f tpop50f pop50f hh50f jobs50f tpop55f pop55f hh55f jobs55f tpop26est pop26est hh26est").split()
TAZ_OTHER = ("objectid tazid_curr tazname county demogarea genarea gencity fialabel fiadescrip hwydist zipcode "
             "notes_chg").split()


class TazTest(unittest.TestCase):
    def test_fields(self):
        f = compass_growth.taz_field
        self.assertEqual(f("tpopcensus"), (2020, "population", "census"))
        self.assertEqual(f("grpqtrcens"), (2020, "group_quarters", "census"))
        self.assertEqual(f("gqrest22"), (2022, "group_quarters", "estimate"))
        self.assertEqual(f("pop25est"), (2025, "household_population", "estimate"))
        self.assertEqual(f("rjobs25"), (2025, "jobs", "estimate"))
        self.assertEqual(f("tpop26est"), (2026, "population", "estimate"))
        self.assertEqual(f("jobs55f"), (2055, "jobs", "forecast"))
        for other in TAZ_OTHER:
            self.assertIsNone(f(other), other)

    def test_census_estimate_forecast_split(self):
        props = {**{n: 100 + i for i, n in enumerate(TAZ_FIELDS)}, "objectid": 2, "tazid_curr": 1212.0,
                 "tazname": "1212", "county": "Ada", "zipcode": "83642", "notes_chg": " "}
        zone, values, unknown = compass_growth.taz_rows(props)
        self.assertEqual((zone["taz_id"], zone["name"], zone["notes"]), (1212, "1212", None))
        self.assertEqual(unknown, [])
        kinds = {}
        for v in values:
            kinds.setdefault(v["kind"], set()).add(v["year"])
        self.assertEqual(kinds, {"census": {2020}, "estimate": {2022, 2023, 2024, 2025, 2026},
                                 "forecast": {2030, 2035, 2040, 2045, 2050, 2055}})
        self.assertEqual(len(values), len(TAZ_FIELDS))
        self.assertEqual(len({(v["year"], v["measure"], v["kind"]) for v in values}), len(values))
        zone, values, unknown = compass_growth.taz_rows({"tazid_curr": 1, "tpopest27": 5, "newfield": 1})
        self.assertEqual(unknown, ["newfield"])


class CountsTest(unittest.TestCase):
    def test_rows(self):
        r = compass_counts.count_row({"pm_id": "#NYA", "road": "Example Rd", "location": "e/o Sample Ave",
                                      "agency": "ACHD", "onetwoway": "2", "mon": "Nov", "month": 11.0,
                                      "year": 2025.0, "total": 499.6}, "short")
        self.assertEqual((r["pm_id"], r["counted_on"], r["period"], r["direction"], r["count_24h"]),
                         (None, date(2025, 11, 1), "month", "both", 500))
        r = compass_counts.count_row({"pm_id": "000000002000", "onetwoway": "1", "year": 2024.0,
                                      "avgtot": 20000.0, "month": 3}, "permanent")
        self.assertEqual((r["counted_on"], r["period"], r["direction"], r["count_24h"], r["pm_id"]),
                         (date(2024, 1, 1), "year", "one_direction", 20000, "000000002000"))
        self.assertIsNone(compass_counts.count_row({"total": 5}, "short"))


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0012)")
class DatabaseTest(unittest.TestCase):
    """Against a real (scratch) database, inside one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('restricted.crash_unit') is not null").fetchone()[0]:
                raise unittest.SkipTest("restricted.crash_unit is missing: apply migration 0012")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.seen = datetime.now(timezone.utc)
        for module in (compass_crashes, compass_counts, compass_growth):
            cl.db.ensure_source(self.conn, module.SOURCE)
            for layer in module.LAYERS:
                cl.db.ensure_source(self.conn, layer.source)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()

    def store_crashes(self, *crashes, complete=False):
        rows = [(c, {"type": "Point", "coordinates": [c["longitude"], c["latitude"]]}) for c in crashes]
        return compass_crashes.store_crashes(self.conn, None, self.seen, cl.Read(rows=rows, complete=complete))

    def test_people_stay_in_the_restricted_schema(self):
        stats = self.store_crashes(crash(serialnumber="TEST-C1"), crash(serialnumber="TEST-C1"),
                                   crash(serialnumber="TEST-C2", accidenttime="02:10"))
        self.assertEqual((stats["stored"], stats["exact repeats dropped"]), (2, 1))
        people = [{**RestrictedTest.PERSON, "serialnumber": "TEST-C1", "unitnumber": 2},
                  {"serialnumber": "TEST-C1", "unitnumber": 1, "unittype": "Car", "age": 52, "sex": "F",
                   "residencestate": "Idaho", "citation": "Not Cited"}]
        stats = compass_crashes.store_units(self.conn, None, self.seen, cl.Read(rows=[(p, None) for p in people],
                                                                                complete=False))
        self.assertEqual(stats["stored"], 2)
        self.assertEqual(self.one("select unit_types from obs.crash where serial_number = 'TEST-C1'")[0],
                         ["Car", "Pedestrian"])
        self.assertEqual(self.one("select count(*) from restricted.crash_unit where serial_number = 'TEST-C1'")[0], 2)
        self.assertEqual(self.one("select count(*) from raw.record where source = 'compass_crash_unit'")[0], 0)
        leaked = self.one("""select count(*) from raw.record where payload::text like '%%Testlandia%%'
                               or payload::text like '%%ZZTEST%%'""")[0]
        self.assertEqual(leaked, 0)
        # No table outside `restricted` has a person-level column.
        outside = self.one("""select string_agg(table_schema || '.' || table_name || '.' || column_name, ', ')
                              from information_schema.columns
                              where table_schema not in ('restricted', 'pg_catalog', 'information_schema')
                                and column_name in ('age_group', 'sex', 'idaho_resident', 'citation', 'cited',
                                                    'protection_device', 'ejection')""")[0]
        self.assertIsNone(outside)

    def test_a_changed_time_moves_the_crash(self):
        self.store_crashes(crash(serialnumber="TEST-C3", accidenttime="10:00"))
        stats = self.store_crashes(crash(serialnumber="TEST-C3", accidenttime="11:30"))
        self.assertEqual(stats["time moved"], 1)
        rows = self.conn.execute("""select crashed_at at time zone 'America/Boise' from obs.crash
                                    where serial_number = 'TEST-C3'""").fetchall()
        self.assertEqual([r[0].strftime("%H:%M") for r in rows], ["11:30"])

    def test_a_rerun_writes_no_new_versions(self):
        self.store_crashes(crash(serialnumber="TEST-C4"))
        again = self.store_crashes(crash(serialnumber="TEST-C4"))
        self.assertEqual((again["versions new"], again["unchanged"]), (0, 1))

    def test_counts_keep_earlier_counts_and_null_placeholders(self):
        store = compass_counts.count_store(compass_counts.PORTABLE, "short", compass_counts.portable_key)
        older = {"pm_id": "#NYA", "road": "Test Rd", "location": "e/o Nowhere", "agency": "TESTAGENCY",
                 "onetwoway": "2", "month": 5, "year": 2023, "total": 100}
        store(self.conn, None, self.seen, cl.Read(rows=[(older, None)], complete=False))
        store(self.conn, None, self.seen, cl.Read(rows=[({**older, "year": 2025, "total": 140}, None)], complete=False))
        rows = self.conn.execute("""select counted_on, count_24h, pm_id from obs.traffic_count
                                    where location_key = 'loc:testagency|test rd|e/o nowhere' order by 1""").fetchall()
        self.assertEqual(rows, [(date(2023, 5, 1), 100, None), (date(2025, 5, 1), 140, None)])

    def test_zone_values_are_replaced_by_the_current_release(self):
        poly = {"type": "Polygon", "coordinates": [[[-116.3, 43.6], [-116.29, 43.6], [-116.29, 43.61], [-116.3, 43.6]]]}
        zone = {"tazid_curr": 99999, "tazname": "99999", "tpopest24": 10, "jobs30f": 7, "hh30f": 5}
        compass_growth.store_taz(self.conn, None, self.seen, cl.Read(rows=[(zone, poly)], complete=False))
        compass_growth.store_taz(self.conn, None, self.seen,
                                 cl.Read(rows=[({**zone, "jobs30f": 9, "hh30f": None}, poly)], complete=False))
        rows = self.conn.execute("""select year, measure, kind, value from obs.taz_demographic
                                    where taz_id = 99999 order by 1, 2""").fetchall()
        self.assertEqual(rows, [(2024, "population", "estimate", 10), (2030, "jobs", "forecast", 9)])
        self.assertEqual(self.one("select GeometryType(geom) from core.taz where taz_id = 99999")[0], "MULTIPOLYGON")


if __name__ == "__main__":
    unittest.main()
