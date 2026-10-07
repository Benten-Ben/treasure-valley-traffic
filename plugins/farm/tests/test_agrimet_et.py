"""Tests for the AgriMet crop water-use source.

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL, inside a transaction that is rolled back.

The fixtures are trimmed real samples from Reclamation (a federal source), read
once on Oct 7, 2026: Parma's crop chart for Oct 6 (pmaich.txt), Boise's
(boiich.txt), and 13 of the 277 rows of Parma's 2026 ET summary (pmai26et.txt).

Run: python3 -m unittest discover -s plugins/farm/tests -t .
"""

import json
import os
import re
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from ingest import db, http, manifest
from ingest.db import version_hash
from plugins.farm.ingest.sources import agrimet_et as agrimet

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return f.read()


def interval(text):
    """A Postgres interval like '1 day' or '10 minutes' as a timedelta (the forms our sources use)."""
    n, unit = re.fullmatch(r"(\d+)\s+(minute|hour|day)s?", text.strip()).groups()
    return timedelta(**{unit + "s": int(n)})


class SourceTest(unittest.TestCase):
    def test_schedule_follows_the_daily_update_and_is_polite(self):
        s = agrimet.SOURCE
        self.assertEqual(s["access"], "open")
        self.assertEqual(interval(s["schedule"]), timedelta(days=1))
        self.assertGreaterEqual(interval(s["schedule"]), timedelta(minutes=10))
        self.assertEqual(interval(s["retry_after"]), timedelta(hours=3))
        self.assertEqual(agrimet.OFF_SEASON_EVERY, timedelta(days=7))
        self.assertGreaterEqual(http.PACE_S[agrimet.HOST], 2)

    def test_the_manifest_lists_it_with_the_same_license_and_credit(self):
        plugin = manifest.load(PLUGIN)
        self.assertEqual((plugin.name, plugin.order, plugin.visibility, plugin.depends), ("farm", 67, "public", []))
        [entry] = plugin.manifest["sources"]
        self.assertEqual((entry["name"], entry["kind"]), (agrimet.SOURCE["name"], "source"))
        self.assertEqual((entry["license"], entry["credit"]), (agrimet.SOURCE["license"], agrimet.SOURCE["credit"]))

    def test_every_station_is_in_the_ring_and_others_are_cut(self):
        self.assertEqual(agrimet.stations(), ["BOII", "BFGI", "NMPI", "PMAI", "ONTO", "GDVI"])
        self.assertFalse(agrimet.in_ring(-114.46, 42.56))           # Twin Falls: outside
        self.assertTrue(agrimet.in_ring(-116.05611, 42.9125))       # Grand View, just inside the south edge
        with mock.patch.dict(agrimet.STATIONS, {"TWFI": (-114.46, 42.56, "Twin Falls", "2000-01-01", "crops")}):
            self.assertNotIn("TWFI", agrimet.stations())

    def test_urls_are_the_static_files_robots_allows(self):
        self.assertEqual(agrimet.url("PMAI", "chart"), "https://www.usbr.gov/pn/agrimet/chart/pmaich.txt")
        self.assertEqual(agrimet.url("PMAI", "year", 2026), "https://www.usbr.gov/pn/agrimet/chart/pmai26et.txt")
        self.assertEqual(agrimet.url("GDVI", "year", 2030), "https://www.usbr.gov/pn/agrimet/chart/gdvi30et.txt")
        rules = http.Robots("User-agent: *\nDisallow: /pn-bin\nDisallow: /gp-bin\n")   # the rules the catalog records
        for code, kind, year in agrimet.plan(date(2027, 1, 5)) + agrimet.plan(date(2026, 7, 1)):
            self.assertTrue(rules.allowed(agrimet.url(code, kind, year)))
            self.assertNotIn("pn-bin", agrimet.url(code, kind, year))


class SeasonTest(unittest.TestCase):
    def test_the_season_is_april_to_october(self):
        self.assertEqual([agrimet.in_season(date(2026, m, d)) for m, d in ((3, 31), (4, 1), (10, 31), (11, 1), (1, 1))],
                         [False, True, True, False, False])

    def test_in_season_each_station_gives_its_chart_and_year_file(self):
        p = agrimet.plan(date(2026, 7, 15))
        self.assertEqual(len(p), 12)
        self.assertEqual(p[:2], [("BOII", "chart", 2026), ("BOII", "year", 2026)])

    def test_off_season_only_the_year_file_and_last_years_in_early_january(self):
        self.assertEqual(agrimet.plan(date(2026, 11, 20)),
                         [(c, "year", 2026) for c in agrimet.stations()])
        early = agrimet.plan(date(2027, 1, 5))
        self.assertEqual(early[:2], [("BOII", "year", 2026), ("BOII", "year", 2027)])
        self.assertEqual(len(early), 12)
        self.assertEqual(len(agrimet.plan(date(2027, 1, 20))), 6)

    def test_today_is_the_boise_date(self):
        late = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)      # still Oct 31 in Boise
        self.assertEqual(agrimet.local_today(late), date(2026, 10, 31))


class ParseYearTest(unittest.TestCase):
    def setUp(self):
        self.cols, self.days, self.bad = agrimet.parse_year(fixture("pmai26et.txt"), "PMAI", 2026)

    def test_columns_are_labelled_by_position(self):
        self.assertEqual(self.cols[:9], ["ETr", "ALFP", "ALFM", "PAST", "LAWN", "WGRN", "SGRN", "BEET", "BEET#2"])
        self.assertEqual(self.cols[15:18], ["FCRN", "FCRN#2", "FCRN#3"])
        self.assertEqual(len(self.cols), 24)

    def test_days_keep_values_drop_dashes_and_invent_nothing(self):
        self.assertEqual(self.bad, 0)
        self.assertEqual(len(self.days), 13)
        self.assertEqual(self.days["2026-01-02"], {"et_in": {"ETr": 0.01}})        # winter: reference ET only
        self.assertNotIn("2026-03-30", self.days)                                  # missing in the file
        self.assertEqual(self.days["2026-09-20"]["et_in"]["BEET"], 0.0)            # its terminate day, kept
        self.assertNotIn("BEET", self.days["2026-09-21"]["et_in"])
        self.assertEqual(self.days["2026-10-05"]["et_in"],
                         {"ETr": 0.14, "ALFP": 0.14, "ALFM": 0.12, "PAST": 0.06, "LAWN": 0.11})

    def test_a_file_for_another_station_or_year_is_refused(self):
        with self.assertRaises(ValueError):
            agrimet.parse_year(fixture("pmai26et.txt"), "NMPI", 2026)
        with self.assertRaises(ValueError):
            agrimet.parse_year(fixture("pmai26et.txt"), "PMAI", 2025)
        with self.assertRaises(ValueError):
            agrimet.parse_year("PMAI - ET SUMMARY - 2026\n 01/02 0.01\n", "PMAI", 2026)   # no header

    def test_odd_tokens_are_flagged_and_broken_rows_counted(self):
        text = ("BOII - ET SUMMARY - 2026\n DATE ETr  LAWN\n ---- ---- ----\n 05/01 0.20 0.15\n"
                " 05/02 0.21 MISS\n 05/03 0.22\n 02/30 0.10 0.05\n")
        cols, days, bad = agrimet.parse_year(text, "BOII", 2026)
        self.assertEqual(cols, ["ETr", "LAWN"])
        self.assertEqual(days["2026-05-02"], {"et_in": {"ETr": 0.21}, "flags": {"LAWN": "MISS"}})
        self.assertEqual((sorted(days), bad), (["2026-05-01", "2026-05-02"], 2))
        with self.assertRaises(ValueError):                       # mostly broken: the format changed
            agrimet.parse_year("BOII - ET SUMMARY - 2026\n DATE ETr LAWN\n 05/01 0.2\n 05/02 0.2\n", "BOII", 2026)

    def test_a_new_years_empty_file_is_fine(self):
        self.assertEqual(agrimet.parse_year("BOII - ET SUMMARY - 2027\n DATE ETr  LAWN\n ---- ---- ----\n",
                                            "BOII", 2027), (["ETr", "LAWN"], {}, 0))


class ParseChartTest(unittest.TestCase):
    def setUp(self):
        self.chart = agrimet.parse_chart(fixture("pmaich.txt"), "PMAI")

    def test_the_four_days_count_back_from_the_charts_date(self):
        self.assertEqual(self.chart["chart_date"], "2026-10-06")
        self.assertEqual(self.chart["days"], ["2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06"])
        self.assertEqual(self.chart["crops"]["ETr"]["et_in"], [0.15, 0.13, 0.14, 0.19])

    def test_crops_keep_their_calendars_and_totals(self):
        crops = self.chart["crops"]
        self.assertEqual(len(crops), 24)
        self.assertEqual(crops["BEET#2"], {"et_in": [0.0, 0.0, 0.0, 0.0], "start": "04-05", "full_cover": "07-05",
                                           "terminate": "10-01", "forecast_in": 0.0, "season_in": 30.9,
                                           "use_7d_in": 0.1, "use_14d_in": 1.0})
        self.assertEqual(crops["LAWN"]["season_in"], 39.1)
        self.assertEqual(crops["FCRN#3"]["start"], "05-10")

    def test_the_chart_agrees_with_the_year_file(self):
        """The evidence for the column order: the chart's older days are the year file's, and each repeated
        crop's last day in the year file is its own calendar's terminate date."""
        _, days, _ = agrimet.parse_year(fixture("pmai26et.txt"), "PMAI", 2026)
        for label, crop in self.chart["crops"].items():
            for d, v in zip(self.chart["days"][:3], crop["et_in"][:3]):
                self.assertEqual(days[d]["et_in"].get(label, 0.0), v, (label, d))
        self.assertEqual(self.chart["crops"]["BEET"]["terminate"], "09-20")
        self.assertEqual(days["2026-09-20"]["et_in"]["BEET"], 0.0)
        self.assertEqual(self.chart["crops"]["BEET#2"]["terminate"], "10-01")
        self.assertEqual(days["2026-10-01"]["et_in"]["BEET#2"], 0.0)
        self.assertNotIn("BEET#2", days["2026-10-02"]["et_in"])

    def test_the_boise_charts_are_lawn_only(self):
        boii = agrimet.parse_chart(fixture("boiich.txt"), "BOII")
        self.assertEqual(sorted(boii["crops"]), ["ETr", "LAWN"])
        self.assertEqual(boii["crops"]["LAWN"]["et_in"], [0.07, 0.07, 0.06, 0.07])

    def test_another_stations_chart_or_a_strange_title_is_refused(self):
        with self.assertRaises(ValueError):
            agrimet.parse_chart(fixture("pmaich.txt"), "NMPI")
        with self.assertRaises(ValueError):
            agrimet.parse_chart("Something else\nCrop,4,3,2,1\n", "PMAI")
        with self.assertRaises(ValueError):
            agrimet.parse_chart("Estimated Crop Water Use - PMAI October 06 2026\n", "PMAI")   # no header
        comma = fixture("boiich.txt").replace("October 06 2026", "October 6, 2026")
        self.assertEqual(agrimet.parse_chart(comma, "BOII")["chart_date"], "2026-10-06")


class RecordsTest(unittest.TestCase):
    def test_ids_payloads_and_points(self):
        _, days, _ = agrimet.parse_year(fixture("pmai26et.txt"), "PMAI", 2026)
        chart = agrimet.parse_chart(fixture("pmaich.txt"), "PMAI")
        recs = agrimet.records({("PMAI", 2026): days}, {"PMAI": chart})
        ids = [r[0] for r in recs]
        self.assertEqual(ids[0], "PMAI:2026-01-02")
        self.assertEqual(ids[-2:], ["PMAI:2026-10-05", "PMAI:chart:2026-10-06"])
        self.assertEqual(len(ids), len(set(ids)))
        sid, payload, geom = recs[-2]
        self.assertEqual(payload, {"station": "PMAI", "date": "2026-10-05",
                                   "et_in": {"ETr": 0.14, "ALFP": 0.14, "ALFM": 0.12, "PAST": 0.06, "LAWN": 0.11}})
        self.assertEqual(geom, {"type": "Point", "coordinates": [-116.93333, 43.8]})
        self.assertNotIn("--", json.dumps([r[1] for r in recs]))

    def test_a_revised_value_is_a_new_version(self):
        a = {"station": "PMAI", "date": "2026-10-05", "et_in": {"ETr": 0.14}}
        b = {"station": "PMAI", "date": "2026-10-05", "et_in": {"ETr": 0.15}}
        self.assertNotEqual(version_hash(a), version_hash(b))


class Result:
    def __init__(self, row=None, rowcount=0):
        self.row, self.rowcount = row, rowcount

    def fetchone(self):
        return self.row


class FakeConn:
    """Just enough of a psycopg connection for run(): the fetch log, the guard's count and the upserts."""

    def __init__(self, last_read=None, held=0):
        self.last_read, self.held = last_read, held
        self.fetch_log, self.upserts, self.commits = None, [], 0

    def execute(self, sql, params=()):
        if sql.lstrip().startswith("insert into ops.fetch"):
            return Result((1,))
        if sql.lstrip().startswith("update ops.fetch"):
            self.fetch_log = params
            return Result()
        if "max(started_at)" in sql:
            return Result((self.last_read,))
        if "count(distinct source_id)" in sql:
            return Result((self.held,))
        if sql.lstrip().startswith("insert into raw.record"):
            self.upserts.append(params[1])
            return Result((True,))
        return Result()                                   # ensure_source

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def server(files, fail=None):
    """A stand-in for http.get serving fixture files by name; anything else is a 404."""
    calls = []

    def get(link, timeout=None, compressed=False):
        name = link.rsplit("/", 1)[1]
        calls.append(name)
        if fail and name in fail:
            raise fail[name]
        if name not in files:
            raise urllib.error.HTTPError(link, 404, "Not Found", {}, None)
        body = files[name].encode()
        return 200, body, "allowed"
    return get, calls


class RunTest(unittest.TestCase):
    FILES = {"pmaich.txt": fixture("pmaich.txt"), "pmai26et.txt": fixture("pmai26et.txt"),
             "boiich.txt": fixture("boiich.txt")}

    def test_in_season_it_reads_charts_and_year_files_and_notes_what_is_missing(self):
        conn = FakeConn()
        get, calls = server(self.FILES)
        stats = agrimet.run(conn, today=date(2026, 10, 7), get=get)
        self.assertEqual(len(calls), 12)
        self.assertEqual(stats["station-days"], 13)
        self.assertEqual(stats["charts"], 2)
        self.assertEqual(stats["latest day"], "2026-10-05")
        self.assertIn("BOII year 2026 missing", stats["notes"])
        self.assertEqual(len(conn.upserts), 15)
        self.assertIn("PMAI:chart:2026-10-06", conn.upserts)
        finished_ok, status = conn.fetch_log[1], conn.fetch_log[2]
        self.assertEqual((finished_ok, status), (True, 200))

    def test_off_season_it_waits_a_week_between_reads(self):
        recent = db.now() - timedelta(days=3)
        get, calls = server(self.FILES)
        stats = agrimet.run(FakeConn(last_read=recent), today=date(2026, 12, 1), get=get)
        self.assertEqual(calls, [])
        self.assertIn("skipped", stats)
        old = db.now() - timedelta(days=8)
        conn = FakeConn(last_read=old)
        stats = agrimet.run(conn, today=date(2026, 12, 1), get=get)
        self.assertEqual(calls, [f"{c.lower()}26et.txt" for c in agrimet.stations()])     # no charts
        self.assertEqual(stats["charts"], 0)

    def test_a_cut_off_year_file_is_refused_but_the_rest_is_kept(self):
        conn = FakeConn(held=200)            # we hold 200 days of 2026 for each station; the file has 13
        get, _ = server(self.FILES)
        with self.assertRaisesRegex(RuntimeError, "only 13 days against 200"):
            agrimet.run(conn, today=date(2026, 10, 7), get=get)
        self.assertEqual(sorted(conn.upserts), ["BOII:chart:2026-10-06", "PMAI:chart:2026-10-06"])
        self.assertGreaterEqual(conn.commits, 2)          # the charts were committed before the failure was logged
        self.assertFalse(conn.fetch_log[1])

    def test_a_file_that_does_not_parse_fails_the_run_after_keeping_the_others(self):
        files = dict(self.FILES, **{"nmpich.txt": fixture("pmaich.txt")})     # Parma's chart served as Nampa's
        conn = FakeConn()
        get, _ = server(files)
        with self.assertRaisesRegex(RuntimeError, "NMPI"):
            agrimet.run(conn, today=date(2026, 10, 7), get=get)
        self.assertIn("PMAI:2026-10-05", conn.upserts)

    def test_nothing_readable_fails_and_server_errors_are_not_swallowed(self):
        get, _ = server({})
        with self.assertRaisesRegex(RuntimeError, "no AgriMet file"):
            agrimet.run(FakeConn(), today=date(2026, 10, 7), get=get)
        boom = urllib.error.HTTPError("x", 503, "Unavailable", {}, None)
        get, _ = server(self.FILES, fail={"boiich.txt": boom})
        with self.assertRaises(urllib.error.HTTPError):
            agrimet.run(FakeConn(), today=date(2026, 10, 7), get=get)
        get, _ = server(self.FILES, fail={"boiich.txt": http.RobotsDisallowed("no")})
        with self.assertRaises(http.RobotsDisallowed):
            agrimet.run(FakeConn(), today=date(2026, 10, 7), get=get)

    def test_an_html_error_page_counts_as_missing(self):
        get, _ = server({"pmaich.txt": "<!DOCTYPE html><html><body>Page not found</body></html>"})
        self.assertEqual(agrimet.fetch_text(agrimet.url("PMAI", "chart"), get)[0], None)


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    """store() and the year-file guard against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        db.ensure_source(self.conn, agrimet.SOURCE)
        self.conn.execute("delete from raw.record where source = 'agrimet_et'")      # set real rows aside (rolled back)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, at):
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values ('agrimet_et', %s, true) "
                                 "returning id", (at,)).fetchone()[0]

    def test_store_versions_revisions_and_the_guard_counts_what_is_held(self):
        c = self.conn
        _, days, _ = agrimet.parse_year(fixture("pmai26et.txt"), "PMAI", 2026)
        chart = agrimet.parse_chart(fixture("pmaich.txt"), "PMAI")
        t0 = datetime(2026, 10, 7, 14, tzinfo=timezone.utc)
        stats = agrimet.store(c, self.fetch(t0), t0, {("PMAI", 2026): days}, {"PMAI": chart})
        self.assertEqual((stats["record versions new"], stats["unchanged"]), (14, 0))
        revised = {d: (dict(row, et_in=dict(row["et_in"], ETr=0.99)) if d == "2026-10-05" else row)
                   for d, row in days.items()}
        t1 = t0 + timedelta(days=1)
        stats = agrimet.store(c, self.fetch(t1), t1, {("PMAI", 2026): revised}, {})
        self.assertEqual((stats["record versions new"], stats["unchanged"]), (1, 12))
        self.assertEqual(c.execute("select count(*) from raw.record where source = 'agrimet_et' "
                                   "and source_id = 'PMAI:2026-10-05'").fetchone()[0], 2)
        geom = c.execute("select ST_AsText(geom) from raw.record where source_id = 'PMAI:chart:2026-10-06' "
                         "and source = 'agrimet_et'").fetchone()[0]
        self.assertEqual(geom, "POINT(-116.93333 43.8)")
        agrimet.check_year(c, "PMAI", 2026, 7)                    # 13 held: 7 is over half
        with self.assertRaises(RuntimeError):
            agrimet.check_year(c, "PMAI", 2026, 6)
        agrimet.check_year(c, "PMAI", 2025, 0)                    # nothing held for 2025


if __name__ == "__main__":
    unittest.main()
