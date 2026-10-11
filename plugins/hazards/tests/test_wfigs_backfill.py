"""Tests for the Aug-Dec 2025 perimeter backfill (wfigs_backfill.py): its window, the one read (with a fake
server: no network), the file and its provenance, and the load into raw.record.

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
from datetime import datetime, timezone

from ingest import USER_AGENT
from plugins.hazards.ingest import wfigs_backfill as wb
from plugins.hazards.ingest.sources import nifc_wfigs_perimeters as per

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
UTC = timezone.utc
READ_AT = datetime(2026, 10, 11, 13, 5, tzinfo=UTC)


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
        self.assertEqual((p["count"], p["features"], p["requests"], p["robots"], p["http_status"]),
                         (4, 4, 2, "no_rules", 200))
        self.assertEqual((p["user_agent"], p["service"], p["approval"]), (USER_AGENT, per.LAYER, wb.APPROVAL))
        self.assertEqual(p["window"]["first_day"], "2025-08-01")
        self.assertEqual(p["window"]["last_day"], "2025-12-31")
        provenance, features = wb.read(folder)
        self.assertEqual(provenance, p)
        self.assertEqual(len(features), 4)

    def test_over_the_cap_nothing_is_read(self):
        server = FakeServer(IN_WINDOW, count=401)
        with self.assertRaises(RuntimeError):
            wb.fetch(self.tmp.name, get=server, sleep=lambda s: None, now=READ_AT)
        self.assertEqual(len(server.urls), 1)
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_the_read_needs_one_off(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            wb.main(["--fetch", "--out", self.tmp.name])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("--one-off", err.getvalue())

    def test_a_changed_file_is_refused(self):
        folder, _ = wb.fetch(self.tmp.name, get=FakeServer(IN_WINDOW), sleep=lambda s: None, now=READ_AT)
        with open(os.path.join(folder, wb.FEATURES), "ab") as f:
            f.write(b" ")
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

    def setUp(self):
        import psycopg
        from ingest import db
        self.conn = psycopg.connect(DB_URL)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db.ensure_source(self.conn, {**per.SOURCE, "name": self.SOURCE, "schedule": None})
        self.folder, _ = wb.fetch(self.tmp.name, get=FakeServer(IN_WINDOW + OUTSIDE), sleep=lambda s: None,
                                  now=READ_AT)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def test_load_once_with_provenance_then_nothing_new(self):
        stats = wb.load(self.conn, self.folder, source=self.SOURCE)
        self.assertEqual((stats["fires"], stats["record versions new"], stats["already held"], stats["fetch logged"]),
                         (2, 2, 0, "now"))
        fetch = self.conn.execute(
            """select f.source, f.started_at, f.ok, f.robots, f.http_status, f.records, s.access, s.schedule
               from ops.fetch f join ops.source s on s.name = f.source where f.id = %s""",
            (stats["fetch"],)).fetchone()
        self.assertEqual(fetch, (wb.SOURCE["name"], READ_AT, True, "no_rules", 200, 4, "one_off", None))
        rows = self.conn.execute("""select first_fetch, first_seen, last_seen from raw.record where source = %s""",
                                 (self.SOURCE,)).fetchall()
        self.assertEqual(set(rows), {(stats["fetch"], READ_AT, READ_AT)})
        again = wb.load(self.conn, self.folder, source=self.SOURCE)
        self.assertEqual((again["fetch"], again["fetch logged"], again["record versions new"], again["already held"]),
                         (stats["fetch"], "before", 0, 2))

    def test_a_version_the_poller_holds_is_left_as_it_is(self):
        from ingest import db
        parsed, _ = wb.prepare(IN_WINDOW)
        sid, (payload, geom) = sorted(parsed.items())[0]
        later = datetime(2026, 10, 12, tzinfo=UTC)
        db.upsert_records(self.conn, self.SOURCE, [(sid, payload, geom)], None, later, complete=False)
        stats = wb.load(self.conn, self.folder, source=self.SOURCE)
        self.assertEqual((stats["record versions new"], stats["already held"]), (1, 1))
        seen = self.conn.execute("select first_seen, last_seen, first_fetch from raw.record where source = %s "
                                 "and source_id = %s", (self.SOURCE, sid)).fetchone()
        self.assertEqual(seen, (later, later, None))


if __name__ == "__main__":
    unittest.main()
