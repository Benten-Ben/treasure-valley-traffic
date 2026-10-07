"""Tests for the Drought Monitor poller: the query, the CSV, the window, and drought episodes.

The fixture and the weeks below are synthetic (made-up percentages with NDMC's columns).
"""

import unittest
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from ingest import db, events
from plugins.water.ingest.sources import usdm_drought as usdm

from . import DB_URL, FakeConn, db_conn, fake_fetch, fixture

UTC = timezone.utc
NOW = datetime(2030, 7, 11, 18, tzinfo=UTC)


def week(fips, monday_after, d0=0.0, d1=0.0, d2=0.0, d3=0.0, d4=0.0):
    """A categorical row for the map valid from the Tuesday `monday_after` + 1 day."""
    start = monday_after + timedelta(days=1)
    none = round(100 - d0 - d1 - d2 - d3 - d4, 2)
    return {"MapDate": start.strftime("%Y%m%d"), "FIPS": fips, "County": f"{usdm.COUNTIES[fips]} County",
            "State": "OR" if fips.startswith("41") else "ID", "ValidStart": start.isoformat(),
            "ValidEnd": (start + timedelta(days=6)).isoformat(), "StatisticFormatID": "2",
            "None": none, "D0": d0, "D1": d1, "D2": d2, "D3": d3, "D4": d4}


MONDAYS = [date(2030, 6, 10) + timedelta(weeks=i) for i in range(5)]     # maps Jun 11 .. Jul 9, 2030


def all_counties(fips_weeks):
    """Every county dry-free for the five weeks, except the rows given for some."""
    rows = []
    for fips in usdm.COUNTIES:
        rows += fips_weeks.get(fips) or [week(fips, m) for m in MONDAYS]
    return rows


class QueryTest(unittest.TestCase):
    def test_the_query(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(usdm.query_url(date(2030, 6, 1), date(2030, 7, 11))).query)
        self.assertEqual(q["aoi"], [",".join(usdm.COUNTIES)])
        self.assertEqual((q["startdate"], q["enddate"], q["statisticsType"]), (["6/1/2030"], ["7/11/2030"], ["2"]))
        self.assertIn("aoi=16001,16015,", usdm.query_url(date(2030, 6, 1), date(2030, 7, 11)))
        self.assertEqual(len(usdm.COUNTIES), 10)

    def test_the_window(self):
        self.assertEqual(usdm.window_start(None), date(2000, 1, 4))           # the whole archive, once
        self.assertEqual(usdm.window_start("20300709"), date(2030, 6, 11))    # four weeks back
        self.assertEqual(usdm.window_start("20000111"), date(2000, 1, 4))

    def test_the_csv(self):
        rows = usdm.parse_csv("﻿" + fixture("usdm.csv"))
        self.assertEqual([(r["FIPS"], r["MapDate"]) for r in rows],
                         [("16001", "20300709"), ("16001", "20300702"), ("41045", "20300709")])   # not Twin Falls
        r = rows[0]
        self.assertEqual((r["None"], r["D0"], r["D1"], r["D2"], r["D4"]), (10.0, 20.0, 30.0, 40.0, 0.0))
        self.assertEqual((r["County"], r["State"], r["ValidStart"], r["ValidEnd"]),
                         ("Ada County", "ID", "2030-07-09", "2030-07-15"))
        self.assertEqual(usdm.records(rows)[0][0], "16001:20300709")
        self.assertEqual(usdm.parse_csv("MapDate,FIPS\nbad,16001\n"), [])

    def test_valid_dates_fall_back_to_the_map_date(self):
        r = week("16001", MONDAYS[0])
        self.assertEqual((usdm.valid_start(r), usdm.valid_until(r)),
                         (datetime(2030, 6, 11, tzinfo=UTC), datetime(2030, 6, 18, tzinfo=UTC)))
        r.update({"ValidStart": None, "ValidEnd": None})
        self.assertEqual((usdm.valid_start(r), usdm.valid_until(r)),
                         (datetime(2030, 6, 11, tzinfo=UTC), datetime(2030, 6, 18, tzinfo=UTC)))

    def test_or_worse(self):
        r = week("16001", MONDAYS[0], d0=31.76, d1=53.53, d2=14.71)
        self.assertEqual([usdm.or_worse(r, c) for c in usdm.CATEGORIES], [100.0, 68.24, 14.71, 0.0, 0.0])


class EpisodeTest(unittest.TestCase):
    def test_new_episodes_start_where_their_run_of_weeks_starts(self):
        ada = [week("16001", MONDAYS[0]), week("16001", MONDAYS[1], d0=20),
               week("16001", MONDAYS[2], d0=10, d1=10), week("16001", MONDAYS[3], d0=5, d2=15),
               week("16001", MONDAYS[4], d0=5, d2=15)]
        rows = usdm.drought_rows(all_counties({"16001": ada}), {})
        got = {r["source_id"]: r for r in rows}
        self.assertEqual(sorted(got), ["16001:D0:2030-06-18", "16001:D1:2030-06-25", "16001:D2:2030-07-02"])
        d1 = got["16001:D1:2030-06-25"]                     # D1 became D2: "D1 or worse" goes on
        self.assertEqual((d1["kind"], d1["severity"], d1["geom"]), ("drought", "D1", None))
        self.assertEqual(d1["start"], datetime(2030, 6, 25, tzinfo=UTC))
        self.assertEqual(d1["end"], datetime(2030, 7, 16, tzinfo=UTC))      # the latest map's valid end, inclusive
        self.assertEqual(d1["attributes"], {"fips": "16001", "county": "Ada County", "state": "ID", "category": "D1",
                                            "or_worse": True, "area_pct": 15.0, "map_date": "2030-07-09",
                                            "since": "2030-06-25", "since_is_lower_bound": False})
        self.assertEqual(d1["description"], "Ada County, ID: D1 (moderate drought) or worse")

    def test_a_run_reaching_the_window_start_continues_the_open_episode(self):
        canyon = [week("16027", m, d0=50, d1=10) for m in MONDAYS]
        prev = {"source_id": "16027:D1:2029-08-07", "start": datetime(2029, 8, 7, tzinfo=UTC),
                "attributes": {"since": "2029-08-07", "since_is_lower_bound": False}}
        rows = usdm.drought_rows(all_counties({"16027": canyon}), {("16027", "D1"): prev})
        got = {r["severity"]: r for r in rows}
        self.assertEqual((got["D1"]["source_id"], got["D1"]["start"]), ("16027:D1:2029-08-07", prev["start"]))
        self.assertEqual(got["D1"]["attributes"]["since"], "2029-08-07")
        self.assertEqual(got["D0"]["source_id"], "16027:D0:2030-06-11")    # no open D0 episode: a lower bound
        self.assertTrue(got["D0"]["attributes"]["since_is_lower_bound"])

    def test_a_gap_inside_the_window_starts_a_new_episode(self):
        gem = [week("16045", MONDAYS[0], d1=5), week("16045", MONDAYS[1]), week("16045", MONDAYS[2], d1=5),
               week("16045", MONDAYS[3], d1=5), week("16045", MONDAYS[4], d1=5)]
        prev = {"source_id": "16045:D1:2030-01-01", "start": datetime(2030, 1, 1, tzinfo=UTC), "attributes": {}}
        rows = usdm.drought_rows(all_counties({"16045": gem}), {("16045", "D1"): prev})
        self.assertEqual([r["source_id"] for r in rows if r["severity"] == "D1"], ["16045:D1:2030-06-25"])

    def test_no_drought_anywhere_means_no_rows(self):
        self.assertEqual(usdm.drought_rows(all_counties({}), {}), [])

    def test_an_incomplete_latest_map_is_refused(self):
        rows = [r for r in all_counties({}) if not (r["FIPS"] == "41045" and r["MapDate"] == "20300709")]
        with self.assertRaisesRegex(RuntimeError, "lacks counties 41045"):
            usdm.drought_rows(rows, {})
        with self.assertRaisesRegex(RuntimeError, "no drought statistics"):
            usdm.drought_rows([], {})

    def test_an_unchanged_week_writes_nothing(self):
        canyon = [week("16027", m, d0=50, d1=10) for m in MONDAYS]
        first = {r["source_id"]: r for r in usdm.drought_rows(all_counties({"16027": canyon}), {})}
        active = {("16027", r["severity"]): {"source_id": r["source_id"], "start": r["start"],
                                             "attributes": r["attributes"]} for r in first.values()}
        again = {r["source_id"]: r for r in usdm.drought_rows(all_counties({"16027": canyon}), active)}
        self.assertEqual({k: events.content_hash(v) for k, v in first.items()},
                         {k: events.content_hash(v) for k, v in again.items()})


class RunTest(unittest.TestCase):
    def test_run_reads_from_the_latest_map_held(self):
        body = "\n".join(["MapDate,FIPS,County,State,None,D0,D1,D2,D3,D4,ValidStart,ValidEnd,StatisticFormatID"] + [
            ",".join([r["MapDate"], r["FIPS"], r["County"], r["State"]] + [str(r[c]) for c in ("None",) +
                     usdm.CATEGORIES] + [r["ValidStart"], r["ValidEnd"], "2"]) for r in all_counties({})]).encode()
        conn = FakeConn({"insert into ops.fetch": [(1,)], "max(payload->>'MapDate')": [("20300702",)]})
        with mock.patch.object(usdm.http, "get", return_value=(200, body, "no_rules")) as get, \
                mock.patch.object(db, "upsert_records", return_value=(50, 0, 0)), \
                mock.patch.object(events, "upsert", return_value={"new": 0, "changed": 0, "unchanged": 0,
                                                                  "gone": 0}):
            stats = usdm.run(conn)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(get.call_args.args[0]).query)
        self.assertEqual(q["startdate"], ["6/4/2030"])
        self.assertEqual((stats["from"], stats["rows"], stats["latest map"]), ("2030-06-04", 50, "20300709"))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.conn = db_conn(self, "raw.record", "evt.event")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_an_episode_continues_across_runs_and_ends(self):
        c = self.conn
        db.ensure_source(c, usdm.SOURCE)
        canyon = [week("16027", m, d0=50, d1=10) for m in MONDAYS]
        s1 = usdm.store(c, fake_fetch(c, "usdm_drought", NOW), NOW, all_counties({"16027": canyon}))
        self.assertEqual((s1["versions new"], s1["episodes new"]), (50, 2))
        self.assertEqual(usdm.latest_held(c), "20300709")
        nxt = MONDAYS[-1] + timedelta(weeks=1)
        rows = all_counties({"16027": canyon[1:] + [week("16027", nxt, d0=60)]})
        rows = [r for r in rows if r["FIPS"] == "16027"] + [week(f, m) for f in usdm.COUNTIES if f != "16027"
                                                              for m in MONDAYS[1:] + [nxt]]
        later = NOW + timedelta(days=7)
        s2 = usdm.store(c, fake_fetch(c, "usdm_drought", later), later, rows)
        self.assertEqual((s2["episodes changed"], s2["episodes gone"]), (1, 1))    # D0 goes on, D1 ends
        d0 = c.execute("select source_id, lower(declared) from evt.event where source = 'usdm_drought' and active"
                       ).fetchall()
        self.assertEqual([r[0] for r in d0], ["16027:D0:2030-06-11"])


if __name__ == "__main__":
    unittest.main()
