"""Tests for COMPASS's growth data and plats (plugins/development/ingest/sources/compass_growth.py
and compass_plats.py), on small synthetic records (made-up values; nothing copied from COMPASS).

The store test runs only against a scratch database named by
TVT_TEST_DATABASE_URL (a clone with migration 0012), inside one transaction
that is rolled back. The shared reader's tests are in ingest/tests/test_compass_layer.py.

Run: python3 -m unittest discover -s plugins -t .
"""

import os
import unittest
from datetime import datetime, timezone

from ingest import compass_layer as cl
from plugins.development.ingest.sources import compass_growth, compass_plats


class GuardTest(unittest.TestCase):
    def test_rows_without_their_key_retire_nothing(self):
        class Conn:                                   # 5 plats current; nothing may be written
            def execute(self, sql, args=None):
                if not sql.lstrip().startswith("select"):
                    raise AssertionError(f"wrote before the check: {sql[:40]}")
                return self

            def fetchone(self):
                return (5,)

        # The reviewed case: an answer whose rows lack the key field (e.g. renamed) stores nothing.
        with self.assertRaises(cl.IncompleteLayer):
            compass_plats.store(Conn(), None, None, cl.Read(rows=[({"projectid": "x"}, None)], complete=True,
                                                            expected=1))


class RestrictedTest(unittest.TestCase):
    def test_identifying_fields_are_never_requested(self):
        for f in ("address", "parcel_no", "comment", "created_user", "last_edited_user"):
            self.assertNotIn(f, compass_growth.PERMIT_FIELDS)
        self.assertNotIn("comments", compass_plats.FIELDS)
        fields = compass_growth.zone_fields(cl.Meta(fields={"tazid_curr", "creator", "editor", "hh30f"}))
        self.assertNotIn("*", fields)
        self.assertFalse({"creator", "editor"} & set(fields))

    def test_terms_and_schedules(self):
        for m in (compass_growth, compass_plats):
            self.assertEqual(m.SOURCE["credit"], "COMPASS and COMPASS member agencies")
            self.assertEqual(m.SOURCE["retry_after"], "6 hours")
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

    def test_requested_fields_follow_the_layer(self):
        meta = cl.Meta(fields=set(TAZ_OTHER + TAZ_FIELDS + ["tpopest27", "creator"]))
        fields = compass_growth.zone_fields(meta)
        self.assertIn("tpopest27", fields)                 # a new estimate year is picked up
        self.assertEqual(set(fields), set(TAZ_OTHER + TAZ_FIELDS + ["tpopest27"]) - {"objectid"})

    def test_census_estimate_forecast_split(self):
        props = {**{n: 100 + i for i, n in enumerate(TAZ_FIELDS)}, "objectid": 2, "tazid_curr": 1212.0,
                 "tazname": "1212", "county": "Ada", "zipcode": "83642", "notes_chg": " "}
        zone, values, unknown, conflicts = compass_growth.taz_rows(props)
        self.assertEqual((zone["taz_id"], zone["name"], zone["notes"], unknown, conflicts), (1212, "1212", None, [], 0))
        kinds = {}
        for v in values:
            kinds.setdefault(v["kind"], set()).add(v["year"])
        self.assertEqual(kinds, {"census": {2020}, "estimate": {2022, 2023, 2024, 2025, 2026},
                                 "forecast": {2030, 2035, 2040, 2045, 2050, 2055}})
        self.assertEqual(len(values), len(TAZ_FIELDS))
        self.assertEqual(len({(v["year"], v["measure"], v["kind"]) for v in values}), len(values))

    def test_two_fields_for_one_value(self):
        _, values, unknown, conflicts = compass_growth.taz_rows({"tazid_curr": 1, "tpopest27": 5, "tpop27est": 6,
                                                                 "hhest27": 2, "hh27est": 2, "newfield": 1})
        self.assertEqual((len(values), conflicts, unknown), (2, 1, ["newfield"]))
        self.assertEqual([v["value"] for v in values if v["measure"] == "population"], [6])   # first by name


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
        for module in (compass_growth,):
            cl.db.ensure_source(self.conn, module.SOURCE)
            for layer in module.LAYERS:
                cl.db.ensure_source(self.conn, layer.source)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def one(self, sql, *args):
        return self.conn.execute(sql, args).fetchone()

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
