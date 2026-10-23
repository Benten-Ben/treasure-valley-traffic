"""Tests for the Aug-Dec 2025 and Jul 25-31, 2025 perimeter backfills (wfigs_backfill.py): the windows, each one's
read (with a fake server: no network), the file and its provenance, the refusal to read a window twice, and the load
into raw.record.

The features are synthetic, with WFIGS's field names. The database test runs only with TVT_TEST_DATABASE_URL set to a
scratch database with core's migration 0001, inside a transaction that's rolled back, under a test-only source name.

Run: python3 -m unittest discover -s plugins/hazards/tests -t .
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.parse
from datetime import date, datetime, timezone
from unittest import mock

from ingest import USER_AGENT, http
from plugins.hazards.ingest import wfigs_backfill as wb
from plugins.hazards.ingest.sources import nifc_wfigs_perimeters as per

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
UTC = timezone.utc
READ_AT = datetime(2026, 10, 11, 13, 5, tzinfo=UTC)
JULY_READ_AT = datetime(2026, 10, 22, 18, 0, tzinfo=UTC)


def ms(t):
    return int(t.timestamp() * 1000)


def feature(oid, irwin, discovered, final=True, **kw):
    attrs = {"OBJECTID": oid, "poly_IRWINID": irwin, "poly_IncidentName": f"SYNTH {oid}",
             "poly_FeatureCategory": "Wildfire Final Fire Perimeter" if final else "Wildfire Daily Fire Perimeter",
             "attr_IncidentTypeCategory": "WF", "attr_FireDiscoveryDateTime": ms(discovered) if discovered else None,
             "poly_PolygonDateTime": ms(datetime(2025, 9, 1, tzinfo=UTC)), "poly_GISAcres": 10.0 + oid}
    attrs.update(kw)
    lon, lat = -116.5 + oid * 0.01, 43.5
    return {"attributes": attrs,
            "geometry": {"rings": [[[lon, lat], [lon, lat + 0.005], [lon + 0.005, lat + 0.005], [lon + 0.005, lat],
                                    [lon, lat]]]}}


IN_WINDOW = [feature(1, "{00000000-0000-4000-8000-0000000000B1}", datetime(2025, 8, 1, 6, 0, tzinfo=UTC)),
             feature(2, "{00000000-0000-4000-8000-0000000000B2}", datetime(2025, 12, 15, tzinfo=UTC)),
             feature(3, "{00000000-0000-4000-8000-0000000000B2}", datetime(2025, 12, 15, tzinfo=UTC), final=False)]
OUTSIDE = [feature(4, "{00000000-0000-4000-8000-0000000000B4}", datetime(2025, 8, 1, 5, 59, tzinfo=UTC))]
# The week of Jul 25-31: a range fire like the held RANGE fire (the last evening of the week), another one on the
# 26th, and one just after the week (the first Aug-Dec instant), which the week's filter would not bring.
RANGE_LIKE = feature(5, "{00000000-0000-4000-8000-0000000000B5}", datetime(2025, 7, 31, 20, tzinfo=UTC))
LATE_JULY = [RANGE_LIKE, feature(6, "{00000000-0000-4000-8000-0000000000B6}", datetime(2025, 7, 26, 15, tzinfo=UTC))]


class FakeServer:
    """Answers the count, then the features, as the service would; records each URL."""

    def __init__(self, features, count=None):
        self.features, self.count, self.urls = features, count, []

    def __call__(self, url):
        self.urls.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        if q.get("returnCountOnly") == ["true"]:
            body = {"count": len(self.features) if self.count is None else self.count}
        else:
            body = {"features": self.features}
        return 200, json.dumps(body).encode(), "no_rules"


class WindowTest(unittest.TestCase):
    def test_the_window_is_aug_through_dec_2025_in_boise(self):
        self.assertEqual(wb.bounds(), (datetime(2025, 8, 1, 6, tzinfo=UTC), datetime(2026, 1, 1, 7, tzinfo=UTC)))
        w = wb.where()
        self.assertIn("attr_FireDiscoveryDateTime >= TIMESTAMP '2025-08-01 06:00:00'", w)
        self.assertIn("attr_FireDiscoveryDateTime < TIMESTAMP '2026-01-01 07:00:00'", w)
        self.assertIn("attr_FireDiscoveryDateTime IS NULL AND poly_PolygonDateTime >= TIMESTAMP '2025-08-01 06:00:00'", w)
        for relative in ("CURRENT_TIMESTAMP", "CURRENT_DATE", "INTERVAL", "NOW("):
            self.assertNotIn(relative, w.upper())

    def test_in_window(self):
        a = lambda **kw: {k: ms(v) for k, v in kw.items()}
        self.assertFalse(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 8, 1, 5, 59, tzinfo=UTC))))
        self.assertTrue(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 8, 1, 6, tzinfo=UTC))))
        self.assertTrue(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2026, 1, 1, 6, 59, tzinfo=UTC))))
        self.assertFalse(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2026, 1, 1, 7, tzinfo=UTC))))
        self.assertTrue(wb.in_window(a(poly_PolygonDateTime=datetime(2025, 9, 1, tzinfo=UTC))))
        # A discovery time outside the window wins over a polygon inside it, as in the filter.
        self.assertFalse(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 7, 1, tzinfo=UTC),
                                        poly_PolygonDateTime=datetime(2025, 9, 1, tzinfo=UTC))))
        self.assertFalse(wb.in_window({}))

    def test_the_july_window_is_jul_25_through_31_in_boise_and_touches_the_first_at_one_instant(self):
        jul = wb.JUL_25_31_2025
        self.assertEqual((jul.first_day, jul.last_day, jul.approval), (date(2025, 7, 25), date(2025, 7, 31),
                                                                      wb.APPROVAL_JULY))
        self.assertEqual(wb.bounds(jul), (datetime(2025, 7, 25, 6, tzinfo=UTC), datetime(2025, 8, 1, 6, tzinfo=UTC)))
        self.assertEqual(wb.bounds(jul)[1], wb.bounds(wb.AUG_DEC_2025)[0])             # no gap, no overlap
        w = wb.where(jul)
        self.assertIn("attr_FireDiscoveryDateTime >= TIMESTAMP '2025-07-25 06:00:00'", w)
        self.assertIn("attr_FireDiscoveryDateTime < TIMESTAMP '2025-08-01 06:00:00'", w)
        self.assertIn("attr_FireDiscoveryDateTime IS NULL AND poly_PolygonDateTime >= TIMESTAMP '2025-07-25 06:00:00'", w)
        for relative in ("CURRENT_TIMESTAMP", "CURRENT_DATE", "INTERVAL", "NOW("):
            self.assertNotIn(relative, w.upper())
        self.assertNotEqual(w, wb.where(wb.AUG_DEC_2025))
        self.assertEqual(wb.count_url(jul).count("returnCountOnly=true"), 1)
        self.assertIs(wb.find_window("2025-07-25", "2025-07-31"), jul)
        self.assertIsNone(wb.find_window("2025-07-24", "2025-07-31"))

    def test_in_window_for_the_july_week(self):
        jul = wb.JUL_25_31_2025
        a = lambda **kw: {k: ms(v) for k, v in kw.items()}
        self.assertFalse(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 7, 25, 5, 59, tzinfo=UTC)), jul))
        self.assertTrue(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 7, 25, 6, tzinfo=UTC)), jul))
        self.assertTrue(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 8, 1, 5, 59, tzinfo=UTC)), jul))
        self.assertFalse(wb.in_window(a(attr_FireDiscoveryDateTime=datetime(2025, 8, 1, 6, tzinfo=UTC)), jul))
        # Each instant is in one window only.
        for t in (datetime(2025, 8, 1, 5, 59, tzinfo=UTC), datetime(2025, 8, 1, 6, tzinfo=UTC)):
            self.assertEqual([wb.in_window(a(attr_FireDiscoveryDateTime=t), w) for w in wb.WINDOWS].count(True), 1)


class FetchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_one_count_then_one_read_written_with_provenance(self):
        server = FakeServer(IN_WINDOW + OUTSIDE)
        folder, p = wb.fetch(self.tmp.name, get=server, sleep=lambda s: None, now=READ_AT)
        self.assertEqual(os.path.basename(folder), "20261011T1305Z")
        self.assertEqual(len(server.urls), 2)
        count, read = (urllib.parse.parse_qs(urllib.parse.urlsplit(u).query) for u in server.urls)
        self.assertEqual(count["returnCountOnly"], ["true"])
        for q in (count, read):
            self.assertEqual(q["where"], [wb.where()])
            self.assertEqual(q["geometry"], [",".join(str(v) for v in wb.common.RING)])
        self.assertEqual(read["geometryPrecision"], [str(per.PRECISION)])
        self.assertTrue(all(u.startswith(per.LAYER + "/query?") for u in server.urls))
        self.assertEqual((p["count"], p["features"], p["requests"], p["robots_txt_requests"], p["robots"],
                          p["http_status"]), (4, 4, 2, 0, "no_rules", 200))
        self.assertEqual((p["user_agent"], p["service"], p["approval"]), (USER_AGENT, per.LAYER, wb.APPROVAL))
        self.assertEqual(p["window"]["first_day"], "2025-08-01")
        self.assertEqual(p["window"]["last_day"], "2025-12-31")
        provenance, features, window = wb.read(folder)
        self.assertEqual((provenance, window), (p, wb.AUG_DEC_2025))
        self.assertEqual(len(features), 4)

    def test_robots_txt_is_counted_among_the_requests(self):
        server = FakeServer(IN_WINDOW)
        host = "https://" + urllib.parse.urlsplit(per.LAYER).netloc

        def get(url, timeout=None):          # http.get, which reads robots.txt once before the first request
            http._robots.setdefault(host, None)
            return server(url)

        with mock.patch.dict(http._robots, clear=True), mock.patch.object(wb.http, "get", side_effect=get):
            _, p = wb.fetch(self.tmp.name, sleep=lambda s: None, now=READ_AT)
        self.assertEqual((p["requests"], p["robots_txt_requests"]), (3, 1))

    def test_over_the_cap_nothing_is_read(self):
        server = FakeServer(IN_WINDOW, count=401)
        with self.assertRaises(RuntimeError):
            wb.fetch(self.tmp.name, get=server, sleep=lambda s: None, now=READ_AT)
        self.assertEqual(len(server.urls), 1)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def refused(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm, \
                mock.patch.object(wb, "fetch", side_effect=AssertionError("no read in tests")):
            wb.main(list(argv))
        self.assertEqual(cm.exception.code, 2)
        return err.getvalue()

    def test_the_read_needs_one_off(self):
        self.assertIn("--one-off", self.refused("--fetch", "--out", self.tmp.name))

    def test_fetch_has_no_dry_run(self):
        self.assertIn("--dry-run is for --load", self.refused("--fetch", "--one-off", "--out", self.tmp.name, "--dry-run"))
        self.assertIn("--load takes", self.refused("--load", self.tmp.name, "--one-off"))

    def test_a_window_already_read_isnt_read_again(self):
        # With two windows, --window is required; the Aug-Dec read (recorded in WINDOWS) is refused without --read-again.
        out = self.refused("--fetch", "--one-off", "--out", self.tmp.name)
        self.assertIn("--fetch needs --window", out)
        self.assertIn("2025-07-25..2025-07-31", out)
        self.assertIn("2025-08-01..2025-12-31", out)
        argv = ["--fetch", "--one-off", "--out", self.tmp.name, "--window", "2025-08-01..2025-12-31"]
        out = self.refused(*argv)
        self.assertIn("already made (made at 2026-10-11T12:02:07Z)", out)
        self.assertIn("--read-again", out)
        self.assertIn("isn't an approved window",
                      self.refused("--fetch", "--one-off", "--out", self.tmp.name, "--window", "2025-07-24..2025-07-31"))
        # The week's read, once made (its read_at is set, as it is in the code), is refused the same way.
        self.assertTrue(wb.JUL_25_31_2025.read_at)
        out = self.refused("--fetch", "--one-off", "--out", self.tmp.name, "--window", "2025-07-25..2025-07-31")
        self.assertIn(f"already made (made at {wb.JUL_25_31_2025.read_at})", out)
        self.assertIn("--read-again", out)

    def test_a_window_not_yet_recorded_as_read_is_refused_once_a_read_is_under_out(self):
        # The refusal checks the read_at first, then a provenance.json for the window under --out; --read-again takes it.
        week = wb.JUL_25_31_2025._replace(read_at=None)
        argv = ["--fetch", "--one-off", "--out", self.tmp.name, "--window", "2025-07-25..2025-07-31"]
        with mock.patch.object(wb, "WINDOWS", [wb.AUG_DEC_2025, week]):
            wb.fetch(self.tmp.name, get=FakeServer(LATE_JULY), sleep=lambda s: None, now=READ_AT, window=week)
            self.assertIn("already made (" + os.path.join(self.tmp.name, "20261011T1305Z"), self.refused(*argv))
            with mock.patch.object(wb, "fetch", return_value=("f", {"features": 0, "count": 0, "requests": 3,
                                                                    "robots_txt_requests": 1, "bytes_read": 0,
                                                                    "robots": "no_rules"})) as read, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(wb.main(argv + ["--read-again"]), 0)
            self.assertEqual(read.call_args.kwargs["window"], week)

    def test_an_unread_window_is_read_once_with_its_own_filter_and_provenance(self):
        week = wb.JUL_25_31_2025._replace(read_at=None)
        argv = ["--fetch", "--one-off", "--out", self.tmp.name, "--window", "2025-07-25..2025-07-31"]
        server = FakeServer(LATE_JULY)
        real_fetch = wb.fetch                    # main() calls fetch(out, window=...); the fake server stands in for NIFC
        with mock.patch.object(wb, "WINDOWS", [wb.AUG_DEC_2025, week]), \
                mock.patch.object(wb, "fetch", side_effect=lambda out, window: real_fetch(
                    out, get=server, sleep=lambda s: None, now=JULY_READ_AT, window=window)) as read, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wb.main(argv), 0)
        self.assertEqual(read.call_args.kwargs["window"], week)
        self.assertEqual(len(server.urls), 2)
        for u in server.urls:
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)["where"], [wb.where(week)])
        (name,) = os.listdir(self.tmp.name)
        with open(os.path.join(self.tmp.name, name, wb.PROVENANCE), encoding="utf-8") as f:
            p = json.load(f)
        self.assertEqual((p["window"]["first_day"], p["window"]["last_day"], p["approval"], p["features"]),
                         ("2025-07-25", "2025-07-31", wb.APPROVAL_JULY, 2))

    def test_a_changed_file_is_refused(self):
        folder, _ = wb.fetch(self.tmp.name, get=FakeServer(IN_WINDOW), sleep=lambda s: None, now=READ_AT)
        with open(os.path.join(folder, wb.FEATURES), "ab") as f:
            f.write(b" ")
        with self.assertRaises(ValueError):
            wb.read(folder)

    def test_the_kept_read_still_loads(self):
        # The filter recorded in the read made on Oct 11, 2026 (its provenance.json on the server), character for
        # character: a change to where() must not strand it.
        self.assertEqual(wb.where(wb.AUG_DEC_2025),
                         "(attr_FireDiscoveryDateTime >= TIMESTAMP '2025-08-01 06:00:00' AND attr_FireDiscoveryDateTime "
                         "< TIMESTAMP '2026-01-01 07:00:00') OR (attr_FireDiscoveryDateTime IS NULL AND "
                         "poly_PolygonDateTime >= TIMESTAMP '2025-08-01 06:00:00' AND poly_PolygonDateTime < "
                         "TIMESTAMP '2026-01-01 07:00:00')")
        self.assertEqual((wb.AUG_DEC_2025.read_at, wb.WINDOWS[0]), ("2026-10-11T12:02:07Z", wb.AUG_DEC_2025))
        self.assertEqual(wb.WINDOWS, [wb.AUG_DEC_2025, wb.JUL_25_31_2025])      # the week is beside it, never in place

    def test_the_july_window_goes_beside_the_first(self):
        aug_dec, _ = wb.fetch(os.path.join(self.tmp.name, "a"), get=FakeServer(IN_WINDOW), sleep=lambda s: None,
                              now=READ_AT)
        july, p = wb.fetch(os.path.join(self.tmp.name, "b"), get=FakeServer(LATE_JULY + IN_WINDOW),
                           sleep=lambda s: None, now=JULY_READ_AT, window=wb.JUL_25_31_2025)
        self.assertEqual(os.path.basename(july), "20261022T1800Z")
        self.assertEqual((p["window"]["first_day"], p["approval"]), ("2025-07-25", wb.APPROVAL_JULY))
        self.assertEqual(p["where"], wb.where(wb.JUL_25_31_2025))
        _, features, window = wb.read(july)
        self.assertEqual(window, wb.JUL_25_31_2025)
        self.assertEqual(wb.prepare(features, window)[1]["fires"], 2)             # the week's fires only
        self.assertEqual(wb.prepare(features, window)[1]["outside the window"], 3)
        self.assertEqual(wb.read(aug_dec)[2], wb.AUG_DEC_2025)                    # the first read still loads
        # A read is checked against the window its own provenance names: one whose filter was changed is refused.
        path = os.path.join(july, wb.PROVENANCE)
        with open(path, encoding="utf-8") as f:
            changed = json.load(f)
        changed["where"] = wb.where(wb.AUG_DEC_2025)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(changed, f)
        with self.assertRaises(ValueError):
            wb.read(july)

    def test_a_window_no_one_approved_is_refused_on_load(self):
        folder, _ = wb.fetch(os.path.join(self.tmp.name, "c"), get=FakeServer(LATE_JULY), sleep=lambda s: None,
                             now=JULY_READ_AT, window=wb.JUL_25_31_2025)
        with mock.patch.object(wb, "WINDOWS", wb.WINDOWS[:1]):
            with self.assertRaises(ValueError):
                wb.read(folder)

    def test_prepare_keeps_the_window_and_parses_as_the_poller(self):
        parsed, stats = wb.prepare(IN_WINDOW + OUTSIDE)
        self.assertEqual(stats, {"features": 4, "outside the window": 1, "fires": 2, "duplicates": 1})
        final, _ = parsed["{00000000-0000-4000-8000-0000000000B2}"]
        self.assertEqual(final["poly_FeatureCategory"], "Wildfire Final Fire Perimeter")   # the final one wins
        self.assertEqual(parsed, per.parse([IN_WINDOW[0], IN_WINDOW[1], IN_WINDOW[2]])[0])


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (core migration 0001)")
class LoadDatabaseTest(unittest.TestCase):
    SOURCE = "test_nifc_wfigs_perimeters"
    BUILD = "test-burn-scars"

    def setUp(self):
        import psycopg
        from ingest import db
        self.conn = psycopg.connect(DB_URL)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db.ensure_source(self.conn, {**per.SOURCE, "name": self.SOURCE, "schedule": None})
        self.marks = self.conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]
        if self.conn.execute("select to_regclass('hazards.burn_scar') is not null").fetchone()[0]:
            self.conn.execute("delete from hazards.burn_scar")      # no real scar's step marks (rolled back)
        self.folder, _ = wb.fetch(self.tmp.name, get=FakeServer(IN_WINDOW + OUTSIDE), sleep=lambda s: None,
                                  now=READ_AT)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_load_once_with_provenance_then_nothing_new(self):
        stats = wb.load(self.conn, self.folder, source=self.SOURCE, build=self.BUILD)
        self.assertEqual((stats["fires"], stats["record versions new"], stats["already held"], stats["fetch logged"]),
                         (2, 2, 0, "now"))
        if self.marks:                                               # the new versions mark the burn-scars build
            self.assertEqual(stats[f"{self.BUILD} marked"], "2 new perimeter versions")
            self.assertEqual(self.conn.execute("select marked_by, marks from ops.build_pending where build = %s",
                                               (self.BUILD,)).fetchall(), [(wb.SOURCE["name"], 1)])
        fetch = self.conn.execute(
            """select f.source, f.started_at, f.ok, f.robots, f.http_status, f.records, s.access, s.schedule
               from ops.fetch f join ops.source s on s.name = f.source where f.id = %s""",
            (stats["fetch"],)).fetchone()
        self.assertEqual(fetch, (wb.SOURCE["name"], READ_AT, True, "no_rules", 200, 4, "one_off", None))
        rows = self.conn.execute("""select first_fetch, first_seen, last_seen from raw.record where source = %s""",
                                 (self.SOURCE,)).fetchall()
        self.assertEqual(set(rows), {(stats["fetch"], READ_AT, READ_AT)})
        again = wb.load(self.conn, self.folder, source=self.SOURCE, build=self.BUILD)
        self.assertEqual((again["fetch"], again["fetch logged"], again["record versions new"], again["already held"]),
                         (stats["fetch"], "before", 0, 2))
        self.assertNotIn(f"{self.BUILD} marked", again)

    def test_a_version_the_poller_holds_is_left_as_it_is(self):
        from ingest import db
        parsed, _ = wb.prepare(IN_WINDOW)
        sid, (payload, geom) = sorted(parsed.items())[0]
        later = datetime(2026, 10, 12, tzinfo=UTC)
        db.upsert_records(self.conn, self.SOURCE, [(sid, payload, geom)], None, later, complete=False)
        stats = wb.load(self.conn, self.folder, source=self.SOURCE, build=self.BUILD)
        self.assertEqual((stats["record versions new"], stats["already held"]), (1, 1))
        seen = self.conn.execute("select first_seen, last_seen, first_fetch from raw.record where source = %s "
                                 "and source_id = %s", (self.SOURCE, sid)).fetchone()
        self.assertEqual(seen, (later, later, None))

    def test_the_july_read_loads_beside_the_aug_dec_read_and_a_held_range_version(self):
        from ingest import db
        # The poller already holds the RANGE-like fire (as RANGE is held), from an earlier poll.
        parsed_range, _ = wb.prepare([RANGE_LIKE], wb.JUL_25_31_2025)
        (range_id, (payload, geom)), = parsed_range.items()
        polled = datetime(2026, 10, 8, tzinfo=UTC)
        db.upsert_records(self.conn, self.SOURCE, [(range_id, payload, geom)], None, polled, complete=False)
        first = wb.load(self.conn, self.folder, source=self.SOURCE, build=self.BUILD)
        held = self.conn.execute("select source_id, version_hash, first_seen, last_seen, first_fetch from raw.record "
                                 "where source = %s order by source_id, version_hash", (self.SOURCE,)).fetchall()
        july_folder, _ = wb.fetch(os.path.join(self.tmp.name, "july"), get=FakeServer(LATE_JULY), sleep=lambda s: None,
                                  now=JULY_READ_AT, window=wb.JUL_25_31_2025)
        july = wb.load(self.conn, july_folder, source=self.SOURCE, build=self.BUILD)
        self.assertEqual((july["window"], july["fires"], july["record versions new"], july["already held"],
                          july["fetch logged"]), ("2025-07-25..2025-07-31", 2, 1, 1, "now"))
        self.assertNotEqual(july["fetch"], first["fetch"])               # its own fetch row, beside the first read's
        after = self.conn.execute("select source_id, version_hash, first_seen, last_seen, first_fetch from raw.record "
                                  "where source = %s order by source_id, version_hash", (self.SOURCE,)).fetchall()
        self.assertEqual([r for r in after if r in held], held)          # nothing already held was touched
        self.assertEqual(len(after), len(held) + 1)
        self.assertEqual(self.conn.execute(
            "select first_seen, last_seen, first_fetch from raw.record where source = %s and source_id = %s",
            (self.SOURCE, range_id)).fetchone(), (polled, polled, None))   # the held version is left as it is
        self.assertEqual(self.conn.execute("select count(*) from ops.fetch where id = any(%s)",
                                           ([first["fetch"], july["fetch"]],)).fetchone()[0], 2)
        again = wb.load(self.conn, july_folder, source=self.SOURCE, build=self.BUILD)
        self.assertEqual((again["fetch"], again["record versions new"], again["already held"]), (july["fetch"], 0, 2))


if __name__ == "__main__":
    unittest.main()
