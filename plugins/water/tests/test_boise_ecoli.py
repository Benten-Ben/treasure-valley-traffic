"""Tests for the E. coli poller: sample keys, dates, the ring, and that a replaced round is kept.

The fixture is synthetic (made-up sites and results with the City layer's field names).
"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ingest import arcgis, db
from plugins.water.ingest import common
from plugins.water.ingest.sources import boise_ecoli as ecoli

from . import DB_URL, FakeConn, db_conn, fake_fetch, fixture

UTC = timezone.utc
NOW = datetime(2030, 7, 3, 12, tzinfo=UTC)


def features():
    return fixture("ecoli.json")["features"]


class EcoliTest(unittest.TestCase):
    def test_samples_are_keyed_by_site_date_and_lab_number(self):
        parsed = ecoli.parse(features())
        self.assertEqual(sorted(parsed), ["TESTPOND1A|2030-07-01|XX00001-01", "TESTPOND1B|2030-07-01|XX00001-02",
                                          "TESTRIVER1|2030-07-01|XX00001-03"])   # no lab number; outside the ring
        payload, geom = parsed["TESTPOND1B|2030-07-01|XX00001-02"]
        self.assertNotIn("OBJECTID", payload)
        self.assertEqual((payload["FinalResultNumeric"], payload["Units"], payload["SampleDescription"]),
                         (456.7, "MPN/100 mL", "Example Pond Site 2"))
        self.assertEqual(geom, {"type": "Point", "coordinates": [-116.2002, 43.6102]})

    def test_dates_stay_days(self):
        river = ecoli.parse(features())["TESTRIVER1|2030-07-01|XX00001-03"][0]
        self.assertEqual((river["SampleDatetime"], river["AnalysisDatetime"]), ("2030-07-01", None))  # an Esri date
        self.assertEqual(ecoli.day("2030-07-01"), "2030-07-01")
        self.assertEqual(ecoli.day(int(datetime(2030, 7, 1, tzinfo=UTC).timestamp() * 1000)), "2030-07-01")

    def test_a_renumbered_reload_is_the_same_reading(self):
        a = ecoli.parse(features())
        reloaded = json.loads(json.dumps(features()))
        for f in reloaded:
            f["attributes"]["OBJECTID"] += 1000
        b = ecoli.parse(reloaded)
        self.assertEqual({k: db.version_hash(p) for k, (p, _) in a.items()},
                         {k: db.version_hash(p) for k, (p, _) in b.items()})

    def test_run_reads_the_layer_and_stores_readings(self):
        conn = FakeConn({"insert into ops.fetch": [(1,)]})
        with mock.patch.object(arcgis, "fetch_layer", return_value=(features(), 1234, 200, "no_rules")) as fl, \
                mock.patch.object(db, "upsert_records", return_value=(3, 0, 0)) as up:
            stats = ecoli.run(conn)
        self.assertEqual(fl.call_args.args[0], ecoli.LAYER)
        self.assertIs(up.call_args.kwargs["complete"], False)        # a replaced round is never retired
        self.assertEqual((stats["samples"], stats["listed"], stats["versions new"], stats["latest round"]),
                         (3, 5, 3, "2030-07-01"))


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database")
class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.conn = db_conn(self, "raw.record")

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_the_last_round_stays_when_the_next_replaces_it(self):
        c = self.conn
        db.ensure_source(c, ecoli.SOURCE)
        first = [(k, p, g) for k, (p, g) in ecoli.parse(features()).items()]
        common.store_readings(c, "boise_ecoli", first, fake_fetch(c, "boise_ecoli", NOW), NOW)
        later = NOW + timedelta(days=7)
        nxt = json.loads(json.dumps(features()))
        for f in nxt:
            f["attributes"]["SampleDatetime"] = "2030-07-08"
        second = [(k, p, g) for k, (p, g) in ecoli.parse(nxt).items()]
        common.store_readings(c, "boise_ecoli", second, fake_fetch(c, "boise_ecoli", later), later)
        n = c.execute("select count(*) from raw.record where source = 'boise_ecoli' and removed_at is null"
                      ).fetchone()[0]
        self.assertEqual(n, 6)


if __name__ == "__main__":
    unittest.main()
