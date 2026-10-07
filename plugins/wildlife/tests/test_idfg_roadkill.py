"""Tests for the IDFG roadkill source (plugins/wildlife/ingest/sources/idfg_roadkill.py).

Offline, except DatabaseTest, which runs only against a scratch database named
by TVT_TEST_DATABASE_URL (migration 0001 applied), inside a transaction that is
rolled back. The fixture (fixtures/roadkill_query.json) is SYNTHETIC: the
layer's real field names and types as of Oct 7, 2026, with made-up reports,
places, dates, IDs and text.

Run: python3 -m unittest discover -s plugins/wildlife/tests -t .
"""

import copy
import json
import os
import re
import unittest
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from ingest import db, http, manifest
from ingest.db import version_hash
from plugins.wildlife.ingest.sources import idfg_roadkill as rk

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)


def answer():
    with open(os.path.join(HERE, "fixtures", "roadkill_query.json"), encoding="utf-8") as f:
        return json.load(f)


def features():
    return answer()["features"]


def by_oid(oid, feats=None):
    return next(f for f in (feats or features()) if f["attributes"]["OBJECTID"] == oid)


def parsed(feats=None):
    records, info = rk.parse(feats if feats is not None else features())
    return {sid: (payload, geom) for sid, payload, geom in records}, info


def interval(text):
    """A Postgres interval like '1 day' or '10 minutes' as a timedelta (the forms SOURCE uses)."""
    n, unit = re.fullmatch(r"(\d+) (minute|hour|day)s?", text).groups()
    return timedelta(**{unit + "s": int(n)})


class FakeServer:
    """The roadkill layer as ArcGIS Server answers it: IDs first, then features by OBJECTID range."""

    def __init__(self, feats):
        self.feats, self.urls, self.compressed = feats, [], []

    def get(self, url, timeout=90, compressed=False):
        self.urls.append(url)
        self.compressed.append(compressed)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        oids = sorted(f["attributes"]["OBJECTID"] for f in self.feats)
        if q.get("returnIdsOnly") == ["true"]:
            body = {"objectIdFieldName": "OBJECTID", "objectIds": oids}
        elif "objectIds" in q:
            want = {int(i) for i in q["objectIds"][0].split(",")}
            body = {"features": [f for f in self.feats if f["attributes"]["OBJECTID"] in want]}
        else:
            lo, hi = (int(t) for t in re.findall(r"(?:>=|<=) (\d+)", q["where"][0]))
            body = {**{k: v for k, v in answer().items() if k != "features"},
                    "features": [f for f in self.feats if lo <= f["attributes"]["OBJECTID"] <= hi]}
        return 200, json.dumps(body).encode(), "no_rules"


class FetchTest(unittest.TestCase):
    def test_the_ring_is_read_with_the_shared_reader_in_few_gzipped_requests(self):
        server = FakeServer(features())
        with mock.patch.object(http, "get", server.get):
            feats, nbytes, status, robots = rk.fetch(sleep=lambda s: None)
        self.assertEqual(len(feats), 7)
        self.assertEqual((status, robots), (200, "no_rules"))
        self.assertGreater(nbytes, 0)
        self.assertEqual(len(server.urls), 2)                   # the IDs, then one range query
        self.assertTrue(all(server.compressed))
        for url in server.urls:
            parts = urllib.parse.urlsplit(url)
            self.assertEqual(parts.netloc, rk.HOST)
            self.assertTrue(parts.path.endswith("/MapServer/1/query"), parts.path)
            self.assertNotRegex(parts.path.lower(), "applyedits|addfeatures|updatefeatures|deletefeatures")
            q = urllib.parse.parse_qs(parts.query)
            self.assertEqual(q["geometry"], ["-117.3,42.9,-115.6,44.3"])
            self.assertEqual(q["inSR"], ["4326"])
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(server.urls[1]).query)
        self.assertEqual((q["outSR"], q["outFields"], q["geometryPrecision"]), (["4326"], ["*"], ["6"]))

    def test_idfgs_server_is_paced(self):
        self.assertGreaterEqual(http.PACE_S[rk.HOST], 5)
        self.assertGreaterEqual(rk.PAUSE_S, 2)


class ParseTest(unittest.TestCase):
    def test_personal_and_undocumented_fields_are_dropped_and_new_ones_named(self):
        records, info = parsed()
        for payload, _ in records.values():
            self.assertLessEqual(set(payload), set(rk.KEEP))
            for gone in ("note", "path", "OBJECTID", "GlobalID", "observerName"):
                self.assertNotIn(gone, payload)
        blob = json.dumps(list(records.values()))
        for text in ("SYNTHETIC NOTE TEXT", "synthetic/path", "SYNTHETIC NAME", "00000000-0000-4000"):
            self.assertNotIn(text, blob)
        self.assertEqual(info["new fields left out"], "observerName")

    def test_cut_to_the_ring(self):
        records, info = parsed()
        self.assertEqual(info["reports in the ring"], 5)
        self.assertEqual(info["outside the ring (cut)"], 1)              # 9000004, east of the ring
        self.assertEqual(info["without a point"], 1)                     # 9000006
        self.assertEqual(info["in the valley box"], 4)                   # all but the Survey 123 elk
        for _, geom in records.values():
            lon, lat = geom["coordinates"]
            self.assertTrue(rk.inside(lon, lat, rk.RING))
        self.assertFalse(rk.inside(-114.4, 43.5, rk.RING))
        self.assertTrue(rk.inside(-115.6, 44.3, rk.RING))                # edges count

    def test_blanks_are_dropped_and_values_typed(self):
        records, _ = parsed()
        elk = next(p for p, _ in records.values() if p["source"] == "IDFG Survey 123")
        for blank in ("salvaged", "highway", "milepost"):
            self.assertNotIn(blank, elk)
        self.assertIsInstance(elk["observed"], int)
        self.assertIsInstance(elk["latitude"], float)
        pronghorn = next(p for p, _ in records.values() if p["source"].startswith("Big Game"))
        self.assertNotIn("highway", pronghorn)
        self.assertNotIn("milepost", pronghorn)

    def test_geometry_is_a_wgs84_point_and_falls_back_to_the_coordinates(self):
        f = by_oid(9000001)
        del f["geometry"]
        (sid, payload, geom), = rk.parse([f])[0]
        self.assertEqual(geom, {"type": "Point", "coordinates": [-116.2012345, 43.6012345]})


class IdTest(unittest.TestCase):
    def test_ids_survive_a_rebuild_that_renumbers_objectids_and_globalids(self):
        before, _ = parsed()
        rebuilt = features()
        for i, f in enumerate(reversed(rebuilt)):                    # a new order, new OBJECTIDs, new GlobalIDs
            f["attributes"]["OBJECTID"] = 150000000 + i
            f["attributes"]["GlobalID"] = "{11111111-1111-4111-8111-%012d}" % i
        after, _ = parsed(rebuilt)
        self.assertEqual(set(before), set(after))
        for sid in before:
            self.assertEqual(version_hash(before[sid][0]), version_hash(after[sid][0]), sid)

    def test_reports_alike_are_numbered_the_same_whatever_the_order(self):
        records, info = parsed()
        twins = sorted(sid for sid, (p, _) in records.items() if p["latitude"] == 43.6012345)   # 9000001 and 9000002
        self.assertEqual(twins, [rk.report_key(*records[twins[0]]), rk.report_key(*records[twins[0]]) + "#2"])
        self.assertEqual(info["alike (numbered #2 on)"], 1)
        flipped, _ = parsed(list(reversed(features())))
        self.assertEqual({k: version_hash(v[0]) for k, v in records.items()},
                         {k: version_hash(v[0]) for k, v in flipped.items()})

    def test_a_changed_field_is_a_new_version_and_a_moved_report_a_new_report(self):
        records, _ = parsed()
        edited = features()
        by_oid(9000007, edited)["attributes"]["disposition"] = "Buried"
        after, _ = parsed(edited)
        sid = next(k for k, (p, _) in records.items() if p["source"].startswith("Big Game"))
        self.assertIn(sid, after)
        self.assertNotEqual(version_hash(records[sid][0]), version_hash(after[sid][0]))
        moved = features()
        by_oid(9000007, moved)["attributes"]["latitude"] = 43.7112345
        by_oid(9000007, moved)["geometry"]["y"] = 43.7112345
        after, _ = parsed(moved)
        self.assertNotIn(sid, after)
        self.assertEqual(len(after), len(records))

    def test_id_shape(self):
        records, _ = parsed()
        for sid in records:
            self.assertRegex(sid, r"^[0-9a-f]{20}(#\d+)?$")


class DateTest(unittest.TestCase):
    def test_dates_are_mountain_standard_time(self):
        midnight_mst = int(datetime(2025, 11, 3, 7, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(rk.local_date(midnight_mst), date(2025, 11, 3))
        self.assertFalse(rk.has_time(midnight_mst))
        evening = int(datetime(2026, 9, 21, 2, 30, tzinfo=timezone.utc).timestamp() * 1000)   # 19:30 MST on the 20th
        self.assertEqual(rk.local_date(evening), date(2026, 9, 20))
        self.assertTrue(rk.has_time(evening))
        self.assertEqual(rk.local_date(-86400000 + 7 * 3600000), date(1969, 12, 31))          # before 1970
        self.assertIsNone(rk.local_date(None))
        self.assertFalse(rk.has_time(None))

    def test_the_runs_date_stats(self):
        _, info = parsed()
        self.assertEqual(info["with a time of day"], 1)                  # the Survey 123 elk
        self.assertEqual(info["observed before 1977 (suspect)"], 1)
        self.assertEqual(info["newest observed"], "2026-10-05")
        self.assertEqual(info["newest reported"], "2026-10-06")
        self.assertEqual(rk.SUSPECT_BEFORE_MS, int(datetime(1977, 1, 1, tzinfo=timezone.utc).timestamp() * 1000))


class CheckTest(unittest.TestCase):
    def test_a_first_run_and_ordinary_growth_pass(self):
        rk.check(set(), {"a"})
        last = {f"r{i}" for i in range(100)}
        rk.check(last, last | {"new1", "new2"})
        rk.check(last, set(list(last)[:95]))                         # IDFG removed a few duplicates

    def test_an_empty_or_much_smaller_answer_is_refused(self):
        last = {f"r{i}" for i in range(100)}
        for current in (set(), set(list(last)[:89])):
            with self.assertRaises(RuntimeError):
                rk.check(last, current)
        with self.assertRaises(RuntimeError):
            rk.check(set(), set())

    def test_an_answer_keyed_afresh_is_refused(self):
        last = {f"r{i}" for i in range(100)}
        with self.assertRaises(RuntimeError) as cm:
            rk.check(last, {f"shifted{i}" for i in range(100)})
        self.assertIn("served differently", str(cm.exception))


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.plugin = manifest.load(PLUGIN)
        self.entry, = self.plugin.manifest["sources"]

    def test_schedule_and_registration(self):
        s = rk.SOURCE
        self.assertGreaterEqual(interval(s["schedule"]), timedelta(minutes=10))
        self.assertEqual(interval(s["schedule"]), timedelta(days=1))
        self.assertLessEqual(interval(s["retry_after"]), interval(s["schedule"]))
        self.assertEqual(s["access"], "open")
        self.assertEqual(s["url"], rk.LAYER)
        self.assertEqual((self.entry["name"], self.entry["kind"]), (s["name"], "source"))
        self.assertEqual(self.entry["module"], "ingest.sources.idfg_roadkill")
        self.assertEqual((self.entry["license"], self.entry["credit"]), (s["license"], s["credit"]))
        self.assertEqual(self.entry["republish"], "aggregates")       # no licence: internal or aggregates (Q17)
        self.assertEqual((self.plugin.visibility, self.plugin.depends, self.plugin.order), ("public", [], 66))


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (migration 0001 applied)")
class DatabaseTest(unittest.TestCase):
    """store() against a real (scratch) database, rolled back afterwards."""

    def setUp(self):
        import psycopg
        self.conn = psycopg.connect(DB_URL)
        self.source = dict(rk.SOURCE, name="test_idfg_roadkill_x")
        patcher = mock.patch.dict(rk.SOURCE, {"name": self.source["name"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        db.ensure_source(self.conn, self.source)

    def tearDown(self):
        if not self.conn.closed:
            self.conn.rollback()
            self.conn.close()

    def fetch(self, at):
        return self.conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, true) returning id",
                                 (self.source["name"], at)).fetchone()[0]

    def rows(self):
        return self.conn.execute("""select source_id, count(*), max(last_seen), bool_or(removed_at is not null)
                                    from raw.record where source = %s group by source_id""",
                                 (self.source["name"],)).fetchall()

    def test_reports_are_versioned_and_never_marked_removed(self):
        t0 = datetime(2026, 10, 7, 9, tzinfo=timezone.utc)
        records, _ = rk.parse(features())
        stats = rk.store(self.conn, self.fetch(t0), t0, records)
        self.assertEqual((stats["record versions new"], stats["unchanged"]), (5, 0))
        # A day later IDFG has rebuilt the layer: one report edited, one gone, one new.
        edited = features()
        by_oid(9000007, edited)["attributes"]["disposition"] = "Buried"
        edited = [f for f in edited if f["attributes"]["OBJECTID"] != 9000003]
        extra = copy.deepcopy(by_oid(9000001))
        extra["attributes"].update(OBJECTID=9000010, observed=extra["attributes"]["observed"] + 86400000)
        t1 = t0 + timedelta(days=1)
        records, _ = rk.parse(edited + [extra])
        stats = rk.store(self.conn, self.fetch(t1), t1, records)
        self.assertEqual((stats["record versions new"], stats["unchanged"], stats["last run's reports not seen"]),
                         (2, 3, 1))
        rows = self.rows()
        self.assertEqual(len(rows), 6)
        self.assertFalse(any(r[3] for r in rows))                    # nothing marked removed
        self.assertEqual(sum(1 for r in rows if r[1] == 2), 1)       # the edited report has two versions
        self.assertEqual(sum(1 for r in rows if r[2] == t0), 1)      # the gone one stays at t0
        self.assertEqual(rk.last_run_ids(self.conn), {sid for sid, _, _ in records})
        payloads = [r[0] for r in self.conn.execute("select payload from raw.record where source = %s",
                                                    (self.source["name"],)).fetchall()]
        self.assertFalse(any("note" in p or "path" in p for p in payloads))

    def test_a_refused_answer_stores_nothing(self):
        t0 = datetime(2026, 10, 7, 9, tzinfo=timezone.utc)
        records, _ = rk.parse(features())
        rk.store(self.conn, self.fetch(t0), t0, records)
        t1 = t0 + timedelta(days=1)
        with self.assertRaises(RuntimeError):
            rk.store(self.conn, self.fetch(t1), t1, records[:2])
        self.assertEqual(max(r[2] for r in self.rows()), t0)


if __name__ == "__main__":
    unittest.main()
