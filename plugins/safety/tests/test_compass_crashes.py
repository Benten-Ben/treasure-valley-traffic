"""Tests for COMPASS's crash data (plugins/safety/ingest/sources/compass_crashes.py), on
small synthetic records (made-up values in COMPASS's formats; no record is copied from its layers).

The offline tests cover parsing (local times, codes, placeholders), how the
people in crashes are coded and coarsened, and the long junction query. The
store tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (a clone with migration 0012), inside one transaction
that is rolled back. The shared reader's tests are in ingest/tests/test_compass_layer.py.

Run: python3 -m unittest discover -s plugins -t .
"""

import json
import os
import random
import unittest
from datetime import date, datetime, timezone

from ingest import compass_layer as cl
from plugins.safety.ingest.sources import compass_crashes


MS_2008_06_01 = 1212278400000          # 2008-06-01 00:00 UTC: how COMPASS stores the day
MS_2025_01_15 = 1736899200000
MS_2025_08_20 = 1755648000000


class LongQueryTest(unittest.TestCase):
    def test_long_queries_go_as_a_form_post(self):
        calls = []
        saved = cl.http.get, cl.http.post, cl.PACER
        cl.http.get = lambda url, timeout=None: calls.append(("get", url)) or (200, b"{}", "no_rules")
        cl.http.post = lambda url, data, timeout=None: calls.append(("post", url, data)) or (200, b"{}", "no_rules")
        cl.PACER = cl.Pacer(gap=0)
        try:
            short = cl.page_url("A/FeatureServer/3", ["objectid", "int_type"], 0, True)
            long = cl.page_url("A/FeatureServer/3", ["objectid"] + compass_crashes.JUNCTION_FIELDS, 0, True)
            cl.paced_get(short)
            cl.paced_get(long)
        finally:
            cl.http.get, cl.http.post, cl.PACER = saved
        self.assertEqual(calls[0], ("get", short))
        self.assertEqual(calls[1][:2], ("post", cl.BASE + "A/FeatureServer/3/query"))
        self.assertIn(b"outFields=objectid,int_type,roundabout", calls[1][2])


def crash(**over):
    props = {"serialnumber": "TEST-C1", "accident_date": MS_2008_06_01, "accidentdate": "6/1/2008 16:45",
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
    def test_people_keep_their_seq_whatever_the_order(self):
        rows = [compass_crashes.unit_row({"serialnumber": "S1", "unitnumber": 1, "age": a, "unittype": t})
                for a, t in ((30, "Car"), (8, "Car"), (30, "Car"), (70, "Pickup"))]
        first = {(r["serial_number"], r["unit_number"], r["seq"]): r["content_hash"]
                 for r in compass_crashes.number_people(rows)}
        self.assertEqual(len(first), 4)                       # identical people still get their own rows
        for _ in range(5):
            random.shuffle(rows)
            again = {(r["serial_number"], r["unit_number"], r["seq"]): r["content_hash"]
                     for r in compass_crashes.number_people(rows)}
            self.assertEqual(again, first)


class RestrictedTest(unittest.TestCase):
    PERSON = {"serialnumber": "TEST-S1", "unitnumber": 1, "unittype": "Pedestrian", "direction": "w",
              "action_": "Going Straight", "event": "Pedestrian", "location": "Nonjunction",
              "contributingfactors": ",Failed to Yield", "injury": "Suspected Serious Injury", "age": 37,
              "sex": "F", "residencestate": "Testlandia", "protectiondevice": "None", "ejection": "Not Ejected",
              "citation": "4242-ZZTEST"}

    def test_people_are_coded_and_coarsened(self):
        r = compass_crashes.unit_row(self.PERSON)
        self.assertEqual((r["age_group"], r["idaho_resident"], r["injury"]), ("35-44", False, "A"))
        self.assertEqual((r["cited"], r["citation"]), (None, None))       # not a coded citation: maybe a ticket number
        self.assertEqual((r["direction"], r["contributing_factor"]), ("W", "Failed to Yield"))
        text = json.dumps(r)
        for kept_out in ("Testlandia", "37", "ZZTEST", '"F"', "sex"):
            self.assertNotIn(kept_out, text)


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
        for f in ("sex", "unitid", "person", "seating", "street1"):
            self.assertNotIn(f, compass_crashes.UNIT_FIELDS)
        for fields in (compass_crashes.JUNCTION_FIELDS, compass_crashes.SEGMENT_FIELDS):
            self.assertNotIn("*", fields)
            self.assertFalse({"creator", "editor"} & set(fields))

    def test_person_rows_only_have_restricted_columns(self):
        r = compass_crashes.number_people([compass_crashes.unit_row(self.PERSON)])[0]
        self.assertEqual(set(r), {"serial_number", "unit_number", "seq", "unit_type", "direction", "action", "event",
                                  "location", "contributing_factor", "injury", "age_group", "idaho_resident",
                                  "protection_device", "ejection", "cited", "citation", "content_hash"})


    def test_terms_and_schedules(self):
        self.assertIn("restricted", compass_crashes.UNITS["notes"])
        self.assertEqual(compass_crashes.SOURCE["credit"], "COMPASS and COMPASS member agencies")
        self.assertEqual(compass_crashes.SOURCE["retry_after"], "6 hours")


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
SKIP_DB = "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0012)"


def _db_ready():
    import psycopg
    with psycopg.connect(DB_URL) as c:
        if not c.execute("select to_regclass('ops.layer_signature') is not null").fetchone()[0]:
            raise unittest.SkipTest("ops.layer_signature is missing: apply migration 0012")
    return psycopg


@unittest.skipUnless(DB_URL, SKIP_DB)
class DatabaseTest(unittest.TestCase):
    """Store functions against a real (scratch) database, inside one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        cls.psycopg = _db_ready()

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.seen = datetime.now(timezone.utc)
        for module in (compass_crashes,):
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
        # No table outside `restricted` has a person-level column, and no table has sex at all.
        outside = self.one("""select string_agg(table_schema || '.' || table_name || '.' || column_name, ', ')
                              from information_schema.columns
                              where table_schema not in ('pg_catalog', 'information_schema')
                                and (column_name = 'sex' or (table_schema <> 'restricted' and column_name in
                                     ('age_group', 'idaho_resident', 'citation', 'cited', 'protection_device',
                                      'ejection')))""")[0]
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


if __name__ == "__main__":
    unittest.main()
