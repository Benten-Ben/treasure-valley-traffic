"""Tests for the OpenStreetMap source (ingest/sources/osm_valley.py).

Offline: tag values, lane expansion, what we keep, the osmium command lines,
the archive (MD5 skip, pruning, the download's checks) and the robots refusal.
With osmium installed, the real pipeline runs over a synthetic fixture
(ingest/tests/fixtures/osm_valley.osm: invented IDs, names and coordinates).

Database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (a package clone with migration 0011), inside a
transaction that is rolled back. The matching layout sits 45 km from any
ACHD segment.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

from ingest import http
from ingest.sources import osm_valley as osm

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "osm_valley.osm")
HAVE_OSMIUM = shutil.which("osmium") is not None
T0 = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def rows(tags):
    return osm.expand_lanes(tags)[0]


def issue_kinds(tags):
    return [k for k, _ in osm.expand_lanes(tags)[1]]


class TagValuesTest(unittest.TestCase):
    def test_lane_counts_tolerate_odd_values(self):
        self.assertEqual(osm.parse_count("3"), 3)
        self.assertEqual(osm.parse_count(" 2 "), 2)
        for odd in ("2;3", "2.5", "none", "", "0", "-1", "two", None, "100"):
            self.assertIsNone(osm.parse_count(odd), odd)

    def test_widths_in_metres(self):
        self.assertEqual(osm.parse_width("7.5"), 7.5)
        self.assertEqual(osm.parse_width("12 m"), 12.0)
        self.assertEqual(osm.parse_width("24 ft"), 7.32)
        self.assertEqual(osm.parse_width("24'"), 7.32)
        self.assertEqual(osm.parse_width("12'6\""), 3.81)
        for odd in ("7,5", "narrow", "5;7", "", None):
            self.assertIsNone(osm.parse_width(odd), odd)

    def test_layer_bridge_oneway(self):
        self.assertEqual(osm.parse_layer("-1"), -1)
        self.assertEqual(osm.parse_layer("1"), 1)
        self.assertIsNone(osm.parse_layer("1;2"))
        self.assertTrue(osm.parse_bridge("viaduct"))
        self.assertFalse(osm.parse_bridge("no"))
        self.assertFalse(osm.parse_bridge(None))
        self.assertEqual(osm.effective_oneway({"highway": "primary"}), "no")
        self.assertEqual(osm.effective_oneway({"highway": "primary", "oneway": "true"}), "yes")
        self.assertEqual(osm.effective_oneway({"highway": "primary", "oneway": "-1"}), "-1")
        self.assertEqual(osm.effective_oneway({"highway": "motorway"}), "yes")
        self.assertEqual(osm.effective_oneway({"highway": "secondary", "junction": "roundabout"}), "yes")
        self.assertEqual(osm.effective_oneway({"highway": "primary", "oneway": "reversible"}), "reversible")

    def test_turn_slots(self):
        self.assertEqual(osm.turn_slots("left|through;right||none"), [["left"], ["through", "right"], [], []])
        self.assertEqual(osm.turn_slots(" Left ; slight_left |through"), [["left", "slight_left"], ["through"]])
        self.assertIsNone(osm.turn_slots(None))

    def test_way_row_keeps_raw_tags_for_odd_values(self):
        tags = {"highway": "secondary", "lanes": "2;3", "width": "wide", "maxspeed": "35 mph", "name": " Odd  Road "}
        w = osm.way_row(7, {"@version": 2, "@timestamp": 1788220800}, tags,
                        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
        self.assertIsNone(w["lanes"])
        self.assertIsNone(w["width_m"])
        self.assertEqual(w["tags"]["lanes"], "2;3")
        self.assertEqual((w["name"], w["maxspeed"], w["osm_version"]), ("Odd Road", "35 mph", 2))
        self.assertEqual(w["osm_timestamp"], datetime(2026, 9, 1, tzinfo=timezone.utc))


class LaneExpansionTest(unittest.TestCase):
    def test_one_way_lanes_count_from_the_left(self):
        self.assertEqual(rows({"highway": "primary", "oneway": "yes", "lanes": "3",
                               "turn:lanes": "left|through|through;right"}),
                         [("forward", 1, ["left"]), ("forward", 2, ["through"]), ("forward", 3, ["through", "right"])])

    def test_oneway_minus_one_runs_backward(self):
        self.assertEqual(rows({"highway": "primary", "oneway": "-1", "lanes": "2", "turn:lanes": "left|right"}),
                         [("backward", 1, ["left"]), ("backward", 2, ["right"])])

    def test_both_directions_and_a_centre_turn_lane(self):
        tags = {"highway": "primary", "lanes": "5", "lanes:forward": "2", "lanes:backward": "2", "lanes:both_ways": "1",
                "turn:lanes:forward": "left|through", "turn:lanes:backward": "through|through;right",
                "turn:lanes:both_ways": "left"}
        self.assertEqual(rows(tags), [("forward", 1, ["left"]), ("forward", 2, ["through"]),
                                      ("backward", 1, ["through"]), ("backward", 2, ["through", "right"]),
                                      ("both", 1, ["left"])])
        self.assertEqual(issue_kinds(tags), [])

    def test_even_count_splits_evenly_and_odd_count_is_left_alone(self):
        self.assertEqual(rows({"highway": "residential", "lanes": "4"}),
                         [("forward", 1, []), ("forward", 2, []), ("backward", 1, []), ("backward", 2, [])])
        odd = {"highway": "primary", "lanes": "5"}
        self.assertEqual(rows(odd), [])
        self.assertEqual(issue_kinds(odd), ["unsplit"])

    def test_turn_slots_give_a_direction_its_count(self):
        # lanes=4 with three forward slots: 3 forward, so 1 backward (not an even 2 + 2).
        tags = {"highway": "secondary", "lanes": "4", "turn:lanes:forward": "left|through|through"}
        self.assertEqual([(d, i) for d, i, _ in rows(tags)],
                         [("forward", 1), ("forward", 2), ("forward", 3), ("backward", 1)])
        self.assertEqual(rows({"highway": "service", "turn:lanes:forward": "right"}), [("forward", 1, ["right"])])
        self.assertEqual(rows({"highway": "primary", "oneway": "yes", "turn:lanes": "left|through"}),
                         [("forward", 1, ["left"]), ("forward", 2, ["through"])])

    def test_slots_that_disagree_are_logged_and_the_lanes_get_no_turns(self):
        tags = {"highway": "primary", "oneway": "yes", "lanes": "3", "turn:lanes": "left|left|through|right"}
        self.assertEqual(rows(tags), [("forward", 1, []), ("forward", 2, []), ("forward", 3, [])])
        self.assertEqual(issue_kinds(tags), ["turn_slots"])
        two_way = {"highway": "primary", "lanes:forward": "2", "lanes:backward": "2",
                   "turn:lanes:backward": "left|through|right"}
        self.assertEqual([t for d, _, t in rows(two_way) if d == "backward"], [[], []])
        self.assertEqual(issue_kinds(two_way), ["turn_slots"])

    def test_inconsistent_totals_and_plain_turn_lanes_on_two_way_roads_are_flagged(self):
        self.assertEqual(issue_kinds({"highway": "primary", "lanes": "5", "lanes:forward": "2", "lanes:backward": "2"}),
                         ["lanes_total"])
        self.assertIn("turn_two_way", issue_kinds({"highway": "primary", "lanes": "2", "turn:lanes": "left|through"}))
        self.assertEqual(issue_kinds({"highway": "primary", "oneway": "reversible", "lanes": "3"}), ["not_expanded"])
        self.assertEqual(rows({"highway": "primary", "oneway": "reversible", "lanes": "3"}), [])

    def test_motorways_are_one_way_without_a_tag(self):
        self.assertEqual([d for d, _, _ in rows({"highway": "motorway", "lanes": "2"})], ["forward", "forward"])


class KeepFilterTest(unittest.TestCase):
    def test_ways(self):
        keep = [{"highway": "primary"}, {"highway": "tertiary_link"}, {"highway": "motorway"},
                {"highway": "residential", "lanes": "2"}, {"highway": "service", "turn:lanes:forward": "right"},
                {"highway": "unclassified", "lanes:backward": "1"}, {"highway": "residential", "turn:lanes": "left|through"}]
        drop = [{"highway": "residential"}, {"highway": "footway"}, {"highway": "proposed", "lanes": "4"},
                {"highway": "construction", "construction": "primary"}, {"highway": "pedestrian", "area": "yes", "lanes": "1"},
                {"railway": "rail"}, {"highway": "residential", "lanes:psv": "1"}]
        for tags in keep:
            self.assertTrue(osm.keep_way(tags), tags)
        for tags in drop:
            self.assertFalse(osm.keep_way(tags), tags)

    def test_node_kinds(self):
        self.assertEqual(osm.node_kind({"highway": "traffic_signals"}), "traffic_signals")
        self.assertEqual(osm.node_kind({"highway": "traffic_signals", "crossing": "traffic_signals"}), "traffic_signals")
        self.assertEqual(osm.node_kind({"highway": "traffic_signals", "traffic_signals": "crossing"}), "crossing_signals")
        self.assertEqual(osm.node_kind({"highway": "crossing", "crossing": "traffic_signals"}), "crossing_signals")
        self.assertEqual(osm.node_kind({"highway": "crossing", "crossing:signals": "yes"}), "crossing_signals")
        self.assertEqual(osm.node_kind({"railway": "level_crossing"}), "level_crossing")
        for tags in ({"highway": "stop"}, {"highway": "crossing", "crossing": "marked"}, {"railway": "crossing"}):
            self.assertIsNone(osm.node_kind(tags), tags)

    def test_parse_features(self):
        lines = [
            "\x1e" + json.dumps({"type": "Feature", "id": "w5", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0]]},
                                 "properties": {"@id": 5, "@version": 3, "@timestamp": "2026-09-01T00:00:00Z",
                                                "highway": "primary", "lanes": "2"}}),
            json.dumps({"type": "Feature", "id": "w6", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0]]},
                        "properties": {"highway": "footway"}}),
            json.dumps({"type": "Feature", "id": "n7", "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "properties": {"@version": 1, "@timestamp": 1788220800, "highway": "traffic_signals"}}),
            json.dumps({"type": "Feature", "id": "n8", "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "properties": {"highway": "stop"}}),
            "",
        ]
        ways, nodes, counts = osm.parse_features(lines)
        self.assertEqual([w["osm_id"] for w in ways], [5])
        self.assertEqual(ways[0]["tags"], {"highway": "primary", "lanes": "2"})
        self.assertEqual(ways[0]["osm_timestamp"], datetime(2026, 9, 1, tzinfo=timezone.utc))
        self.assertEqual([(n["osm_id"], n["kind"]) for n in nodes], [(7, "traffic_signals")])
        self.assertEqual(counts, {"ways skipped": 1, "nodes skipped": 1})

    def test_record_payload_is_tags_and_a_geometry_hash(self):
        a = osm.geometry_hash({"type": "LineString", "coordinates": [[-116.39, 43.4], [-116.38, 43.4]]})
        b = osm.geometry_hash({"type": "LineString", "coordinates": [[-116.39, 43.4], [-116.38, 43.4001]]})
        self.assertEqual(len(a), 16)
        self.assertNotEqual(a, b)


class OsmiumCommandsTest(unittest.TestCase):
    def test_command_lines(self):
        cmds, out = osm.osmium_commands("/a/idaho.osm.pbf", "/w")
        self.assertEqual(out, "/w/valley.geojsonseq")
        self.assertEqual(cmds[0], ["osmium", "extract", "--bbox", "-117.05,43.00,-115.95,43.85", "--strategy",
                                   "complete_ways", "--no-progress", "--overwrite", "--output", "/w/valley.osm.pbf",
                                   "/a/idaho.osm.pbf"])
        self.assertEqual(cmds[1], ["osmium", "tags-filter", "--no-progress", "--overwrite", "--output",
                                   "/w/filtered.osm.pbf", "/w/valley.osm.pbf", "w/highway",
                                   "n/highway=traffic_signals", "n/crossing=traffic_signals",
                                   "n/crossing:signals=yes", "n/railway=level_crossing"])
        self.assertEqual(cmds[2], ["osmium", "export", "--output-format", "geojsonseq", "--format-option",
                                   "print_record_separator=false", "--geometry-types", "point,linestring",
                                   "--attributes", "id,version,timestamp", "--add-unique-id", "type_id",
                                   "--no-progress", "--overwrite", "--output", "/w/valley.geojsonseq",
                                   "/w/filtered.osm.pbf"])

    @unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool")
    def test_pipeline_on_the_fixture(self):
        ways, nodes, counts = osm.extract_features(FIXTURE)
        by_id = {w["osm_id"]: w for w in ways}
        # 104 (residential, no lanes), 105 (footway), 109 (proposed) dropped; 110 is outside the box.
        self.assertEqual(sorted(by_id), [101, 102, 103, 106, 107, 108, 111, 112])
        self.assertEqual({n["osm_id"]: n["kind"] for n in nodes},
                         {1001: "traffic_signals", 1002: "crossing_signals", 1003: "level_crossing",
                          1004: "crossing_signals", 1007: "crossing_signals"})       # 1006 is outside the box
        self.assertEqual(by_id[112]["geom"]["coordinates"][0], [-117.06, 43.5])    # kept whole across the edge
        self.assertEqual((by_id[101]["osm_version"], by_id[101]["osm_timestamp"]),
                         (4, datetime(2026, 9, 4, tzinfo=timezone.utc)))
        self.assertEqual(by_id[102]["lane_rows"][0], ("forward", 1, ["left"]))
        self.assertEqual((by_id[106]["width_m"], by_id[106]["layer"], by_id[106]["bridge"], by_id[106]["oneway"]),
                         (12.0, 1, True, "yes"))
        self.assertEqual(counts["nodes skipped"], 1)                                  # the stop sign


GEOFABRIK_ROBOTS = ("User-agent: *\nDisallow: *.osm.pbf\nDisallow: *.osm.bz2\nDisallow: *.osc.gz\n"
                    "Disallow: *.shp.zip\nDisallow: state.txt\nDisallow: *.state.txt\nDisallow: *updates*\n"
                    "Disallow: *.md5\n")      # download.geofabrik.de/robots.txt as read on Oct 6, 2026


class FakeConn:
    """Enough of a connection for db.ensure_source and db.Fetch."""

    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))
        return self

    def fetchone(self):
        return (1,)

    def commit(self):
        pass

    def rollback(self):
        pass


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.dict(os.environ, {"TVT_ARCHIVE": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.folder = osm.archive_dir()

    def write(self, path, data=b"x"):
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_geofabrik_robots_disallow_the_extract_and_its_md5(self):
        r = http.Robots(GEOFABRIK_ROBOTS)
        self.assertFalse(r.allowed(osm.URL))
        self.assertFalse(r.allowed(osm.MD5_URL))
        self.assertTrue(r.allowed("https://download.geofabrik.de/north-america/us/idaho.html"))

    def test_a_robots_refusal_is_logged_and_returned(self):
        conn = FakeConn()
        with mock.patch.object(osm.http, "get", side_effect=http.RobotsDisallowed("robots.txt disallows it")), \
             mock.patch.object(osm, "download") as download:
            stats = osm.run(conn)
        self.assertEqual(stats, {"refused": "robots.txt disallows it"})
        download.assert_not_called()
        update = [p for s, p in conn.sql if s.startswith("update ops.fetch")][0]
        self.assertFalse(update[1])                                              # ok = false
        self.assertIn("RobotsDisallowed", update[6])

    def test_unchanged_md5_skips_the_download(self):
        md5 = "0123456789abcdef0123456789abcdef"
        osm.mark_loaded(self.folder, md5, os.path.join(self.folder, "idaho-20261001-01234567.osm.pbf"))
        conn = FakeConn()
        body = f"{md5}  idaho-latest.osm.pbf\n".encode()
        with mock.patch.object(osm.http, "get", return_value=(200, body, "allowed")), \
             mock.patch.object(osm, "download") as download:
            stats = osm.run(conn)
        self.assertEqual(stats["skipped"], "extract unchanged since the last load")
        download.assert_not_called()

    def test_a_changed_md5_downloads_and_loads(self):
        conn = FakeConn()
        body = b"fedcba9876543210fedcba9876543210  idaho-latest.osm.pbf\n"
        path = os.path.join(self.folder, "idaho-20261006-fedcba98.osm.pbf")
        with mock.patch.object(osm.http, "get", return_value=(200, body, "allowed")), \
             mock.patch.object(osm, "download", return_value=(self.write(path), 200, 1)) as download, \
             mock.patch.object(osm, "load", return_value={"ways": 3}) as load:
            stats = osm.run(conn)
        download.assert_called_once_with(osm.URL, self.folder, "fedcba9876543210fedcba9876543210")
        self.assertEqual(load.call_args.args[2], path)
        self.assertEqual(stats["ways"], 3)
        self.assertEqual(osm.last_loaded(self.folder)["md5"], "fedcba9876543210fedcba9876543210")

    def test_inbox_file_is_loaded_archived_and_skipped_next_time(self):
        src = self.write(os.path.join(self.folder, "inbox", "idaho-latest.osm.pbf"), b"pbf bytes")
        md5 = hashlib.md5(b"pbf bytes").hexdigest()
        self.assertEqual(osm.inbox_file(self.folder), src)
        with mock.patch.object(osm, "load", return_value={"ways": 1}):
            stats = osm.load_file(FakeConn(), src)
        self.assertFalse(os.path.exists(src))
        self.assertTrue(stats["archived"].startswith("idaho-") and stats["archived"].endswith(f"-{md5[:8]}.osm.pbf"))
        self.assertTrue(os.path.exists(os.path.join(self.folder, stats["archived"])))
        again = self.write(os.path.join(self.folder, "inbox", "idaho-latest.osm.pbf"), b"pbf bytes")
        with mock.patch.object(osm, "load") as load:
            self.assertEqual(osm.load_file(FakeConn(), again)["skipped"], "same extract as the last load")
        load.assert_not_called()

    def test_a_published_md5_beside_the_file_is_checked(self):
        src = self.write(os.path.join(self.folder, "inbox", "idaho-latest.osm.pbf"), b"pbf bytes")
        self.write(src + ".md5", b"00000000000000000000000000000000  idaho-latest.osm.pbf\n")
        with self.assertRaises(SystemExit):
            osm.load_file(FakeConn(), src)

    def test_prune_keeps_the_last_two(self):
        now = time.time()
        for i, name in enumerate(["a-1.osm.pbf", "a-2.osm.pbf", "a-3.osm.pbf"]):
            p = self.write(os.path.join(self.folder, name))
            os.utime(p, (now - 100 + i, now - 100 + i))
        self.write(os.path.join(self.folder, "a-1.osm.pbf.md5"))
        self.assertEqual(osm.prune(self.folder), ["a-1.osm.pbf"])
        self.assertEqual(sorted(os.listdir(self.folder)), ["a-2.osm.pbf", "a-3.osm.pbf", "inbox"])

    def test_names_and_md5_files(self):
        self.assertEqual(osm.archive_name(osm.URL, "fedcba98" + "0" * 24, T0), "idaho-20261006-fedcba98.osm.pbf")
        self.assertEqual(osm.archive_name("/x/my extract.osm", "12345678" + "0" * 24, T0),
                         "my extract-20261006-12345678.osm")
        self.assertEqual(osm.parse_md5("ABCDEF0123456789abcdef0123456789  idaho-latest.osm.pbf\n"),
                         "abcdef0123456789abcdef0123456789")
        with self.assertRaises(ValueError):
            osm.parse_md5("<html>not found</html>")

    def test_download_checks_robots_and_the_md5(self):
        data = b"an extract"

        class Response(io.BytesIO):
            status = 200

        with mock.patch.object(osm, "check_robots", return_value=("allowed", 0)) as robots, \
             mock.patch.object(osm, "PAUSE_S", 0), \
             mock.patch.object(osm.urllib.request, "urlopen", side_effect=lambda *a, **k: Response(data)):
            with self.assertRaises(RuntimeError):
                osm.download(osm.URL, self.folder, "0" * 32)
            self.assertEqual([f for f in os.listdir(self.folder) if f != "inbox"], [])   # no .part left behind
            path, status, size = osm.download(osm.URL, self.folder, hashlib.md5(data).hexdigest())
        robots.assert_called_with(osm.URL)
        self.assertEqual((status, size), (200, len(data)))
        self.assertTrue(os.path.exists(path))
        with mock.patch.object(osm, "check_robots") as robots:          # the same extract again: reused
            self.assertEqual(osm.download(osm.URL, self.folder, hashlib.md5(data).hexdigest())[0], path)
        robots.assert_not_called()


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
BASE_ID = 9_100_000_000          # far above anything a test would collide with


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (a package clone with migration 0011)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('core.osm_way') is not null").fetchone()[0]:
                raise unittest.SkipTest("core.osm_way is missing: apply migration 0011")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        osm.db.ensure_source(self.conn, osm.SOURCE)
        # The layout's origin, in UTM 11N: an empty spot 45 km from the nearest ACHD segment.
        self.x0, self.y0 = self.conn.execute(
            "select ST_X(p), ST_Y(p) from (select ST_Transform(ST_SetSRID(ST_MakePoint(-116.95, 43.05), 4326), 26911) p) q"
        ).fetchone()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def line(self, *pts):
        """A GeoJSON LineString through points given in metres from the origin."""
        wkt = "LINESTRING(" + ",".join(f"{self.x0 + x} {self.y0 + y}" for x, y in pts) + ")"
        return json.loads(self.conn.execute(
            "select ST_AsGeoJSON(ST_Transform(ST_GeomFromText(%s, 26911), 4326), 9)", (wkt,)).fetchone()[0])

    def way(self, n, tags, *pts):
        return osm.way_row(BASE_ID + n, {"@version": 1, "@timestamp": 1788220800}, tags, self.line(*pts))

    def node(self, n, kind, tags, x, y):
        pt = self.line((x, y), (x, y))["coordinates"][0]
        return {"osm_id": BASE_ID + n, "kind": kind, "tags": tags, "geom": {"type": "Point", "coordinates": pt},
                "osm_version": 1, "osm_timestamp": T0}

    def segment(self, *pts):
        geom = self.line(*pts)
        return self.conn.execute(
            """insert into core.road_segment (name, functional_class, geom)
               values ('Synthetic Segment', 'Minor Arterial', ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))
               returning id""", (json.dumps(geom),)).fetchone()[0]

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(*args)

    def test_store_versions_lanes_and_retiring(self):
        arterial = {"highway": "primary", "oneway": "yes", "lanes": "3", "turn:lanes": "left|through|through;right"}
        a = self.way(1, arterial, (0, 0), (300, 0))
        b = self.way(2, {"highway": "residential", "lanes": "2"}, (0, 50), (300, 50))
        signal = self.node(3, "traffic_signals", {"highway": "traffic_signals"}, 300, 0)
        t1, t2, t3 = T0, T0.replace(hour=13), T0.replace(hour=14)
        stats = self.quiet(osm.store, self.conn, None, t1, [a, b], [signal])
        self.assertEqual((stats["ways"], stats["lane rows"], stats["nodes traffic_signals"], stats["record versions new"]),
                         (2, 5, 1, 3))
        lanes = self.conn.execute("select direction, lane, turns from core.osm_lane where osm_id = %s order by lane",
                                  (BASE_ID + 1,)).fetchall()
        self.assertEqual(lanes, [("forward", 1, ["left"]), ("forward", 2, ["through"]),
                                 ("forward", 3, ["through", "right"])])
        self.assertEqual(self.conn.execute("select turns from core.osm_lane where osm_id = %s and lane = 1",
                                           (BASE_ID + 2,)).fetchone()[0], [])

        # b and the signal are gone from the next extract; a is unchanged.
        stats = self.quiet(osm.store, self.conn, None, t2, [a], [])
        self.assertEqual((stats["record versions new"], stats["unchanged"], stats["removed"],
                          stats["ways retired"], stats["nodes retired"]), (0, 1, 2, 1, 1))
        active = dict(self.conn.execute("select osm_id - %s, active from core.osm_way where osm_id > %s",
                                        (BASE_ID, BASE_ID)).fetchall())
        self.assertEqual(active, {1: True, 2: False})
        self.assertIsNotNone(self.conn.execute(
            "select removed_at from raw.record where source = 'osm_valley' and source_id = %s",
            (f"w{BASE_ID + 2}",)).fetchone()[0])

        # b comes back, and a gains a lane: a new version, b active again.
        a2 = self.way(1, {**arterial, "lanes": "4", "turn:lanes": "left|left|through|through;right"}, (0, 0), (300, 0))
        stats = self.quiet(osm.store, self.conn, None, t3, [a2, b], [])
        self.assertEqual((stats["record versions new"], stats["unchanged"]), (1, 1))
        self.assertEqual(self.conn.execute("select lanes, active from core.osm_way where osm_id = %s",
                                           (BASE_ID + 1,)).fetchone(), (4, True))
        self.assertTrue(self.conn.execute("select active from core.osm_way where osm_id = %s", (BASE_ID + 2,)).fetchone()[0])
        self.assertEqual(self.conn.execute("select count(*) from core.osm_lane where osm_id = %s",
                                           (BASE_ID + 1,)).fetchone()[0], 4)

    def test_shrink_guard(self):
        ways = [self.way(i, {"highway": "primary"}, (0, i), (10, i)) for i in range(1000)]
        self.quiet(osm.store, self.conn, None, T0, ways, [])
        with self.assertRaises(RuntimeError):
            osm.store(self.conn, None, T0.replace(hour=13), ways[:400], [])

    def test_matching(self):
        seg = self.segment((0, 0), (300, 0))             # an ACHD centerline, 300 m east-west
        stub = self.segment((150, 8), (150, 20))         # a 12 m side-street stub off it, going north
        ways = [
            self.way(1, {"highway": "primary", "oneway": "yes"}, (-20, 6), (320, 6)),        # carriageway 6 m north
            self.way(2, {"highway": "primary", "oneway": "yes"}, (320, -6), (-20, -6)),      # and 6 m south, drawn the other way
            self.way(3, {"highway": "secondary"}, (150, -200), (150, 200)),                  # perpendicular street
            self.way(4, {"highway": "primary"}, (0, 6), (60, 6)),                            # alongside only 20% of it
            self.way(5, {"highway": "tertiary"}, (-20, 25), (320, 25)),                      # 25 m away
            self.way(6, {"highway": "tertiary"}, (0, -40), (300, 70)),                       # crossing at about 20°
        ]
        self.quiet(osm.store, self.conn, None, T0, ways, [])
        stats = osm.match_achd_segments(self.conn)

        def matches(segment_id):
            return self.conn.execute(
                """select source_id, round(share::numeric, 2), round(bearing_diff::numeric, 1), method, confidence > 0.9
                   from core.segment_match where road_segment_id = %s order by source_id""", (segment_id,)).fetchall()

        # Both carriageways match the centerline; the cross street, the short way, the far way and the
        # diagonal don't.
        self.assertEqual(matches(seg), [(f"w{BASE_ID + 1}", 1, 0, "buffer15_bearing20", True),
                                        (f"w{BASE_ID + 2}", 1, 0, "buffer15_bearing20", True)])
        # Ways 1, 5 and 6 lie within 15 m of the whole stub, but only way 3 runs along it: the bearing gate.
        self.assertEqual(matches(stub), [(f"w{BASE_ID + 3}", 1, 0, "buffer15_bearing20", True)])
        self.assertEqual(stats, {"segment matches": 3, "ACHD segments matched": 2, "ways matched": 3})
        # Re-running replaces the rows rather than adding to them.
        self.assertEqual(osm.match_achd_segments(self.conn)["segment matches"], 3)

    @unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool")
    def test_loading_the_fixture(self):
        class Fetch:
            id, started_at, records = None, T0, None

        f = Fetch()
        stats = self.quiet(osm.load, self.conn, f, FIXTURE)
        self.assertEqual((stats["ways"], stats["nodes traffic_signals"], stats["nodes crossing_signals"],
                          stats["nodes level_crossing"], f.records), (8, 1, 3, 1, 13))
        self.assertEqual(self.conn.execute("select count(*) from core.osm_lane where osm_id in (101, 102)").fetchone()[0], 8)
        self.assertEqual(self.conn.execute("select maxspeed, oneway from core.osm_way where osm_id = 101").fetchone(),
                         ("35 mph", "no"))


if __name__ == "__main__":
    unittest.main()
