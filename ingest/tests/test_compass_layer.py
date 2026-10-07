"""Tests for COMPASS's layer reader (ingest/compass_layer.py), on small synthetic records
(made-up values in COMPASS's formats; no record is copied from its layers).

The offline tests cover paging, retries and pacing, the dev page cap, value
parsing (ArcGIS dates, codes, placeholders), key stability and the removal
guard. The run tests (fetch logging, per-layer skips, change checks, the
back-off) run only against a scratch database named by TVT_TEST_DATABASE_URL
(a clone with migration 0012); they commit rows for sources named
test_compass_* and delete them afterwards. The COMPASS sources' own tests are
with their plugins: safety (crashes), flow (counts, congestion) and
development (growth, plats).

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import os
import random
import unittest
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone
from http.client import IncompleteRead

from ingest import compass_layer as cl
from ingest import http

MS_2008_06_01 = 1212278400000          # 2008-06-01 00:00 UTC: how COMPASS stores the day


def page(n, start=0, exceeded=None, geojson=False, oid="objectid"):
    feats = [{"properties" if geojson else "attributes": {oid: start + i}, "geometry": None} for i in range(n)]
    data = {"features": feats}
    if exceeded is not None:
        if geojson:
            data["properties"] = {"exceededTransferLimit": exceeded}
        else:
            data["exceededTransferLimit"] = exceeded
    return json.dumps(data).encode()


class FakeServer:
    """Serves the given bodies in order (raising any that are exceptions) and records the URLs."""

    def __init__(self, *bodies):
        self.bodies, self.urls = list(bodies), []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        body = self.bodies.pop(0)
        if isinstance(body, Exception):
            raise body
        return 200, body, "no_rules"


def read(server, limit=None, page_size=3, geometry=False, **kw):
    return cl.read("X/FeatureServer/0", ["objectid"], geometry, limit=limit, get=server, sleep=lambda s: None,
                   page=page_size, **kw)


class PagingTest(unittest.TestCase):
    def test_stops_on_a_short_page(self):
        server = FakeServer(page(3, 0, exceeded=True), page(3, 3, exceeded=True), page(1, 6))
        got = read(server, expected=7)
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

    def test_a_read_that_disagrees_with_the_count_fails(self):
        with self.assertRaises(cl.IncompleteLayer):
            read(FakeServer(page(3, 0, exceeded=True), page(1, 3)), expected=5)

    def test_pages_go_by_the_layers_objectid_field_and_names_are_read_in_lower_case(self):
        server = FakeServer(page(2, 0, oid="OBJECTID_1"))
        got = read(server, oid="objectid_1")
        self.assertIn("orderByFields=objectid_1", server.urls[0])
        self.assertEqual([p["objectid_1"] for p, _ in got.rows], [0, 1])

    def test_client_side_gis_errors_raise_without_retrying(self):
        server = FakeServer(json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode())
        with self.assertRaises(RuntimeError):
            read(server)
        self.assertEqual(len(server.urls), 1)

    def test_page_urls(self):
        url = cl.page_url("A/FeatureServer/0", ["objectid", "pm_id"], 4000, True)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual((q["orderByFields"], q["resultOffset"], q["outSR"], q["f"], q["outFields"]),
                         (["objectid"], ["4000"], ["4326"], ["geojson"], ["objectid,pm_id"]))
        self.assertIn("f=json", cl.page_url("A/FeatureServer/4", ["objectid"], 0, False))


class PageCapTest(unittest.TestCase):
    def test_the_cap_stops_early_and_marks_the_read_incomplete(self):
        server = FakeServer(*(page(3, 3 * i, exceeded=True) for i in range(5)))
        got = read(server, limit=2, expected=15)          # no count check on a capped read
        self.assertEqual((got.pages, len(got.rows), got.complete), (2, 6, False))
        self.assertEqual(len(server.urls), 2)

    def test_a_layer_that_fits_under_the_cap_is_complete(self):
        self.assertTrue(read(FakeServer(page(2, 0)), limit=3).complete)

    def test_the_cap_comes_from_the_environment(self):
        old = os.environ.pop(cl.MAX_PAGES_ENV, None)
        try:
            self.assertIsNone(cl.max_pages())
            os.environ[cl.MAX_PAGES_ENV] = "3"
            self.assertEqual(cl.max_pages(), 3)
            for bad in ("0", "x", "-1"):
                os.environ[cl.MAX_PAGES_ENV] = bad
                with self.assertRaises(ValueError):
                    cl.max_pages()
        finally:
            os.environ.pop(cl.MAX_PAGES_ENV, None)
            if old is not None:
                os.environ[cl.MAX_PAGES_ENV] = old


class RetryTest(unittest.TestCase):
    def call(self, *responses):
        server, sleeps = FakeServer(*responses), []
        result = cl.get_json("https://swidrdc.org/x", get=server, sleep=sleeps.append)
        return result, len(server.urls), sleeps

    def test_resets_are_retried_twice(self):
        result, calls, sleeps = self.call(ConnectionResetError("reset by peer"), b"{}")
        self.assertEqual((result[1], calls, sleeps), ({}, 2, [10]))
        result, calls, sleeps = self.call(ConnectionResetError("1"), ConnectionResetError("2"), b"{}")
        self.assertEqual((result[1], calls, sleeps), ({}, 3, [10, 30]))

    def test_truncated_garbled_and_server_error_bodies_are_retried(self):
        for bad in (IncompleteRead(b'{"feat'), b'{"features": [', http.RobotsUnavailable("couldn't read"),
                    json.dumps({"error": {"code": 500, "message": "Unable to complete operation."}}).encode()):
            _, calls, _ = self.call(bad, b'{"count": 3}')
            self.assertEqual(calls, 2, bad)

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


class GuardTest(unittest.TestCase):
    def test_removals_need_most_of_the_layer_and_half_of_whats_current(self):
        complete = cl.Read(complete=True, expected=100)
        cl.check_share(complete, 90, 100, "x")
        with self.assertRaises(cl.IncompleteLayer):
            cl.check_share(complete, 89, 0, "x")                  # under 90% of the count
        with self.assertRaises(cl.IncompleteLayer):
            cl.check_share(cl.Read(complete=True), 40, 100, "x")  # under half of what's current
        cl.check_share(cl.Read(complete=False, expected=100), 0, 100, "x")   # capped: removes nothing anyway


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


    def test_a_repeat_must_match_in_geometry_too(self):
        here = {"type": "Point", "coordinates": [-116.6, 43.6]}
        there = {"type": "Point", "coordinates": [-116.5, 43.6]}
        rows = [({"objectid": 1, "k": "a"}, here), ({"objectid": 2, "k": "a"}, here), ({"objectid": 3, "k": "a"}, there)]
        pairs, dropped, suffixed = cl.keyed(rows, key=lambda r: r[0]["k"], content=lambda r: cl.content(*r))
        self.assertEqual((len(pairs), dropped, suffixed), (2, 1, 1))     # OBJECTID alone doesn't make a record new


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
SKIP_DB = "set TVT_TEST_DATABASE_URL to a scratch database (a clone with migration 0012)"


def _db_ready():
    import psycopg
    with psycopg.connect(DB_URL) as c:
        if not c.execute("select to_regclass('ops.layer_signature') is not null").fetchone()[0]:
            raise unittest.SkipTest("ops.layer_signature is missing: apply migration 0012")
    return psycopg


class FakeLayers:
    """A fake swidrdc.org for whole runs: layer descriptions, counts, highest OBJECTIDs and pages."""

    def __init__(self, layers):
        self.layers, self.urls, self.fail = layers, [], set()   # path -> list of attribute dicts

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        parts = urllib.parse.urlsplit(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        path = parts.path.split("/rest/services/", 1)[1].removesuffix("/query")
        rows = self.layers[path]
        if not parts.path.endswith("/query"):
            body = {"objectIdField": "objectid", "fields": [{"name": "objectid"}, {"name": "v"}]}
        elif q.get("returnCountOnly") == "true":
            body = {"count": len(rows)}
        elif q.get("orderByFields", "").endswith(" DESC"):
            body = {"features": [{"attributes": {"objectid": max(r["objectid"] for r in rows)}}]}
        else:
            if path in self.fail:
                raise urllib.error.HTTPError(url, 404, "gone", {}, None)
            start, n = int(q["resultOffset"]), int(q["resultRecordCount"])
            body = {"features": [{"attributes": r} for r in rows[start:start + n]]}
        return 200, json.dumps(body).encode(), "no_rules"

    def pages_read(self, path):
        return sum(1 for u in self.urls if path + "/query" in u and "resultOffset" in u)


@unittest.skipUnless(DB_URL, SKIP_DB)
class RunTest(unittest.TestCase):
    """Whole module runs against a fake server: fetch logging, per-layer skips, change checks, the
    dev cap and the back-off. These commit rows for test_compass_* sources and remove them after."""

    MODULE = {"name": "test_compass_module", "title": "test", "url": "u", "access": "open", "schedule": "30 days",
              "retry_after": "6 hours"}

    @classmethod
    def setUpClass(cls):
        cls.psycopg = _db_ready()

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.cleanup()
        self.saved = cl.CHECK_MIN_ROWS, os.environ.pop(cl.MAX_PAGES_ENV, None), os.environ.pop(cl.FORCE_ENV, None)
        cl.CHECK_MIN_ROWS = 2                              # so a 3-row layer gets the change check

    def tearDown(self):
        cl.CHECK_MIN_ROWS = self.saved[0]
        os.environ.pop(cl.MAX_PAGES_ENV, None)
        self.cleanup()
        self.conn.close()

    def cleanup(self):
        self.conn.rollback()
        for sql in ("delete from raw.record where source like 'test_compass_%%'",
                    "delete from ops.layer_signature where source like 'test_compass_%%'",
                    "delete from ops.fetch where source like 'test_compass_%%'",
                    "delete from ops.source where name like 'test_compass_%%'"):
            self.conn.execute(sql)
        self.conn.commit()

    @staticmethod
    def layer(name, path):
        def store(conn, fetch_id, seen_at, got):
            cl.check_share(got, len(got.rows), cl.current_records(conn, f"test_compass_{name}"), name)
            return cl.store_records(conn, f"test_compass_{name}", [(str(p["objectid"]), cl.without(p), None)
                                                                   for p, _ in got.rows], fetch_id, seen_at,
                                    got.complete)
        return cl.Layer(name, cl.layer_source(f"test_compass_{name}", name, path), path, ["v"], store, geometry=False)

    def run_module(self, server, *layers):
        return cl.run(self.conn, self.MODULE, list(layers), get=server, sleep=lambda s: None)

    def fetches(self, source):
        return self.conn.execute("select ok, error, records from ops.fetch where source = %s order by id",
                                 (source,)).fetchall()

    def test_an_unchanged_layer_is_not_read_again(self):
        server = FakeLayers({"A/0": [{"objectid": i, "v": i} for i in range(3)]})
        a = self.layer("a", "A/0")
        self.assertEqual(self.run_module(server, a)["a rows"], 3)
        self.assertEqual(self.run_module(server, a), {"a unchanged": "count 3, highest OBJECTID 2"})
        self.assertEqual(server.pages_read("A/0"), 1)
        server.layers["A/0"].append({"objectid": 7, "v": 7})       # a new row: read again
        self.assertEqual(self.run_module(server, a)["a rows"], 4)
        self.assertEqual(server.pages_read("A/0"), 2)

    def test_after_a_failure_only_the_failed_layer_is_read_again(self):
        server = FakeLayers({"A/0": [{"objectid": 1, "v": 1}], "B/0": [{"objectid": 1, "v": 2}]})
        a, b = self.layer("a", "A/0"), self.layer("b", "B/0")
        server.fail.add("B/0")
        with self.assertRaises(urllib.error.HTTPError):
            self.run_module(server, a, b)
        self.assertEqual([r[0] for r in self.fetches("test_compass_module")], [False])
        server.fail.clear()
        stats = self.run_module(server, a, b)
        self.assertEqual((stats["a"], stats["b rows"]), ("done earlier", 1))
        self.assertEqual((server.pages_read("A/0"), server.pages_read("B/0")), (1, 2))   # B: the failed try, then this
        # After a good module run, the next one checks every layer again.
        stats = self.run_module(server, a, b)
        self.assertEqual((stats["a rows"], stats["b rows"]), (1, 1))

    def test_a_capped_run_is_logged_as_failed_and_saves_no_signature(self):
        server = FakeLayers({"A/0": [{"objectid": i, "v": i} for i in range(3)]})
        os.environ[cl.MAX_PAGES_ENV] = "1"
        old_page, cl.PAGE = cl.PAGE, 2
        try:
            stats = self.run_module(server, self.layer("a", "A/0"))
        finally:
            cl.PAGE = old_page
        self.assertEqual(stats["a capped at pages"], 1)
        for source in ("test_compass_module", "test_compass_a"):
            ok, error, _ = self.fetches(source)[-1]
            self.assertFalse(ok)
            self.assertIn("capped", error)
        self.assertIsNone(self.conn.execute("select 1 from ops.layer_signature where source = 'test_compass_a'")
                          .fetchone())

    def test_an_empty_answer_fails_and_removes_nothing(self):
        server = FakeLayers({"A/0": [{"objectid": i, "v": i} for i in range(3)]})
        a = self.layer("a", "A/0")
        self.run_module(server, a)
        server.layers["A/0"] = [{"objectid": 9, "v": 9}]          # a layer suddenly a third of its size
        with self.assertRaises(cl.IncompleteLayer):
            self.run_module(server, a)
        self.assertEqual(cl.current_records(self.conn, "test_compass_a"), 3)

    def test_a_failed_source_waits_its_retry_after(self):
        from ingest.__main__ import due
        cl.db.ensure_source(self.conn, self.MODULE)
        self.conn.execute("""insert into ops.fetch (source, started_at, finished_at, ok)
                             values ('test_compass_module', now() - interval '2 hours', now(), false)""")
        self.conn.commit()
        self.assertFalse(due(self.conn, "test_compass_module", "30 days", "6 hours"))
        self.assertTrue(due(self.conn, "test_compass_module", "30 days"))          # the default: 1 hour


if __name__ == "__main__":
    unittest.main()
