"""Tests for core's OpenStreetMap loader (ingest/osm_extract.py).

Offline: the partition (plan C10) case by case and over the synthetic fixture
(ingest/tests/fixtures/osm_landscape.osm: invented ids, names and coordinates;
each way's comment names its owner), the tag expressions, the box, osmium's
command lines and output, the consumers in the manifests, the cut's reuse and
a whole load's gates, archive and failures (with osmium and the database faked).

With osmium-tool installed (the ingest image), the real pipeline runs over the
fixture: one smart cut, each consumer's features (lines, polygons and
multipolygons, route relations with their members), and the partition again,
with osm_valley's own pipeline over the cut.

Database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (with migration 0019 and roads 0001), inside a
transaction that is rolled back.

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
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from unittest import mock

from ingest import manifest
from ingest import osm_extract as ox

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "osm_landscape.osm")
HAVE_OSMIUM = shutil.which("osmium") is not None
DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)

V, S, P, T = "osm_valley", "osm_street", "osm_paving", "osm_paths"
# The fixture's highway ways in the box, and who owns each (the comments in the fixture say why).
EXPECTED = {201: V, 202: S, 203: V, 204: S, 205: S, 206: S, 207: S, 208: S, 209: P, 210: P, 211: P, 212: P,
            213: P, 214: T, 215: T, 216: T, 217: V, 218: V, 219: T, 220: T, 221: T, 222: None, 223: None,
            224: S, 226: V, 227: S, 228: S, 229: P, 231: P, 232: P, 233: None, 234: None}
EXCEPTIONS = {217, 218}           # lane-tagged non-road ways osm_valley keeps (the named exception)


def consumer(name, tags, geometry, plugin="test"):
    return ox.Consumer(plugin, {"name": name, "module": "ingest.sources.x", "kind": "manual", "license": "ODbL",
                                "credit": ox.CREDIT, "republish": "yes"}, tuple(tags), tuple(geometry), ("test.x",))


# Broad filters: the partition alone decides which highway ways each one gets.
BROAD = {name: consumer(name, ["w/highway", "a/highway"], ["linestring", "polygon"]) for name in (S, P, T)}


def fixture_features():
    """The fixture's ways as osmium export would give them (no osmium needed): every way as a line,
    except a closed way tagged area=yes, which is only a polygon."""
    root = ET.parse(FIXTURE).getroot()
    nodes = {n.get("id"): [float(n.get("lon")), float(n.get("lat"))] for n in root.iter("node")}
    for w in root.iter("way"):
        tags = {t.get("k"): t.get("v") for t in w.iter("tag")}
        coords = [nodes[nd.get("ref")] for nd in w.iter("nd")]
        if not tags:
            continue
        if tags.get("area") == "yes" and coords[0] == coords[-1]:
            geom, shape = {"type": "MultiPolygon", "coordinates": [[coords]]}, "polygon"
        else:
            geom, shape = {"type": "LineString", "coordinates": coords}, "linestring"
        yield {"type": "w", "osm_id": int(w.get("id")), "geometry": shape, "geom": geom, "tags": tags,
               "osm_version": 2, "osm_timestamp": None, "way_nodes": None}


def fixture_highway_ways_in_box():
    return {f["osm_id"]: f["tags"] for f in fixture_features()
            if "highway" in f["tags"] and ox.in_box(f["geom"]["coordinates"])}


class PartitionTest(unittest.TestCase):
    def test_rules_in_order(self):
        cases = [
            ({"highway": "primary"}, V), ({"highway": "motorway_link"}, V),
            ({"highway": "residential", "lanes": "2"}, V),                    # rule 1 before rule 2
            ({"highway": "service", "service": "alley", "turn:lanes": "left|through"}, V),
            ({"highway": "residential"}, S), ({"highway": "unclassified"}, S), ({"highway": "living_street"}, S),
            ({"highway": "road"}, S), ({"highway": "busway"}, S), ({"highway": "service", "service": "alley"}, S),
            ({"highway": "service"}, P), ({"highway": "service", "service": "driveway"}, P),
            ({"highway": "service", "service": "parking_aisle"}, P), ({"highway": "service", "area": "yes"}, P),
            ({"highway": "footway", "footway": "sidewalk"}, P), ({"highway": "path", "footway": "crossing"}, P),
            ({"highway": "cycleway", "footway": "access_aisle"}, P),
            ({"highway": "footway", "footway": "traffic_island"}, P),
            ({"highway": "footway"}, T), ({"highway": "footway", "footway": "link"}, T), ({"highway": "path"}, T),
            ({"highway": "track"}, T), ({"highway": "cycleway"}, T), ({"highway": "bridleway"}, T),
            ({"highway": "steps"}, T), ({"highway": "pedestrian"}, T), ({"highway": "pedestrian", "area": "yes"}, T),
            ({"highway": "cycleway", "lanes": "1"}, V), ({"highway": "track", "lanes": "2"}, V),
            ({"highway": "pedestrian", "lanes:forward": "1"}, V),
            ({"highway": "proposed", "proposed": "residential", "lanes": "2"}, None),
            ({"highway": "construction"}, None), ({"highway": "platform"}, None), ({"highway": "corridor"}, None),
            ({"highway": "residential", "area": "yes"}, None), ({"highway": "primary", "area": "yes"}, None),
            ({"highway": "steps", "footway": "sidewalk"}, T),       # the sidewalk rule is for footway, path, cycleway
            ({"building": "yes"}, None), ({}, None),
        ]
        for tags, want in cases:
            with self.subTest(tags):
                self.assertEqual(ox.owner(tags), want)

    def test_every_owner_is_named_and_left_overs_say_why(self):
        self.assertEqual(ox.OWNERS, (V, S, P, T))
        self.assertIn("not built", ox.unowned_reason({"highway": "proposed"}))
        self.assertIn("as an area", ox.unowned_reason({"highway": "residential", "area": "yes"}))
        self.assertIn("not drawn", ox.unowned_reason({"highway": "corridor"}))
        self.assertIsNone(ox.unowned_reason({"highway": "residential"}))
        self.assertIsNone(ox.unowned_reason({"waterway": "canal"}))

    def test_the_named_exception(self):
        self.assertTrue(ox.named_exception({"highway": "cycleway", "lanes": "1"}))
        self.assertTrue(ox.named_exception({"highway": "track", "lanes": "2"}))
        self.assertTrue(ox.named_exception({"highway": "pedestrian", "turn:lanes": "through"}))
        self.assertFalse(ox.named_exception({"highway": "service", "lanes": "1"}))      # a road class
        self.assertFalse(ox.named_exception({"highway": "raceway", "lanes": "2"}))      # osm_valley's, but no path
        self.assertFalse(ox.named_exception({"highway": "cycleway"}))                   # osm_paths'
        self.assertFalse(ox.named_exception({"highway": "proposed", "proposed": "cycleway", "lanes": "1"}))

    def test_the_fixture_partition_by_tags(self):
        ways = fixture_highway_ways_in_box()
        self.assertEqual(sorted(ways), sorted(EXPECTED))
        self.assertEqual({w: ox.owner(t) for w, t in ways.items()}, EXPECTED)
        self.assertEqual({w for w, t in ways.items() if ox.named_exception(t)}, EXCEPTIONS)
        for w, t in ways.items():
            self.assertEqual(EXPECTED[w] is None, ox.unowned_reason(t) is not None, w)

    def test_each_highway_way_has_exactly_one_owner_among_the_consumers(self):
        """The partition test (plan §5) on the synthetic fixture: osm_valley takes what its keep rule
        keeps, and each other consumer only what the partition gives it, even when its filter asks
        for every highway way."""
        features = list(fixture_features())
        taken = {V: {f["osm_id"] for f in features
                     if "highway" in f["tags"] and f["geometry"] == "linestring"
                     and ox.in_box(f["geom"]["coordinates"]) and ox.keep_way(f["tags"])}}
        for name, c in BROAD.items():
            taken[name] = {f["osm_id"] for f in ox.select_features(features, c, Counter())}
        owners = Counter(w for ids in taken.values() for w in ids)
        for w, want in EXPECTED.items():
            with self.subTest(way=w):
                self.assertEqual(owners[w], 0 if want is None else 1)
                if want:
                    self.assertIn(w, taken[want])
        self.assertLessEqual(EXCEPTIONS, taken[V])
        self.assertFalse({305, 307} & set().union(*taken.values()))       # outside the box (they complete the lake)


class TagFilterTest(unittest.TestCase):
    def test_types_keys_and_values(self):
        f = ox.TagFilter(["w/highway=residential,road", "n/crossing", "a/natural=water", "nwr/amenity=parking"])
        self.assertTrue(f.matches("w", {"highway": "road"}))
        self.assertFalse(f.matches("w", {"highway": "primary"}))
        self.assertFalse(f.matches("n", {"highway": "residential"}))        # a node isn't a way
        self.assertTrue(f.matches("n", {"crossing": "marked"}))
        self.assertTrue(f.matches("w", {"natural": "water"}, area=True))    # a closed way is an area
        self.assertFalse(f.matches("w", {"natural": "water"}, area=False))
        self.assertTrue(f.matches("r", {"type": "multipolygon", "natural": "water"}, area=True))
        self.assertTrue(f.matches("r", {"amenity": "parking"}))
        self.assertFalse(f.matches("w", {}))

    def test_a_first_look_and_osmium_export_s_settings(self):
        f = ox.TagFilter(["w/highway=residential,road", "a/natural=water", "nwr/amenity=parking", "r/route=hiking"])
        self.assertTrue(f.may_match('{"properties":{"highway":"primary"}}'))
        self.assertFalse(f.may_match('{"properties":{"building":"yes"}}'))
        self.assertEqual(f.export_tags("w"), ["highway=residential", "highway=road", "amenity=parking"])
        self.assertEqual(f.export_tags("a"), ["natural=water"])
        config = ox.export_config(consumer(S, ["w/highway=road", "n/crossing"], ["point", "linestring"]))
        self.assertEqual((config["linear_tags"], config["area_tags"]), (["highway=road"], False))
        self.assertTrue(all(config["attributes"][a] for a in ("type", "id", "version", "timestamp", "way_nodes")))

    def test_relation_expressions(self):
        self.assertEqual(ox.relation_expressions(["w/highway=path", "r/route=hiking,mtb", "nwr/x"]),
                         ["r/route=hiking,mtb", "nwr/x"])

    def test_bad_expressions_are_refused(self):
        for e in ("highway", "w/highway!=primary", "x/highway", "w/highway=*", "w/name=Main Street", "ww/highway"):
            with self.subTest(e):
                m = manifest.OSM_TAG_EXPRESSION.match(e)
                self.assertTrue(m is None or len(set(m["types"])) != len(m["types"]))


class GeometryTest(unittest.TestCase):
    def test_in_box(self):
        self.assertTrue(ox.in_box([-116.3, 43.6]))
        self.assertTrue(ox.in_box([[-117.06, 43.5], [-117.04, 43.5]]))          # across the west edge
        self.assertTrue(ox.in_box([-117.05, 43.0]))                              # on a corner
        self.assertFalse(ox.in_box([[-114.5, 42.6], [-114.5, 42.61]]))
        self.assertTrue(ox.in_box([[[[-116.5, 42.9], [-116.4, 43.1], [-116.3, 42.9], [-116.5, 42.9]]]]))
        self.assertFalse(ox.in_box([]))

    def test_closed(self):
        ring = [[0, 0], [1, 0], [1, 1], [0, 0]]
        self.assertTrue(ox.closed({"type": "LineString", "coordinates": ring}))
        self.assertFalse(ox.closed({"type": "LineString", "coordinates": ring[:3]}))
        self.assertFalse(ox.closed(None))


class OsmiumOutputTest(unittest.TestCase):
    def test_export_lines(self):
        line = json.dumps({"type": "Feature", "id": "w202", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                           "properties": {"@type": "way", "@id": 202, "@version": 2, "@timestamp": 1788307200,
                                          "@way_nodes": [1, 2], "highway": "residential"}})
        f = ox.parse_export_line("\x1e" + line)
        self.assertEqual((f["type"], f["osm_id"], f["geometry"], f["osm_version"], f["way_nodes"]),
                         ("w", 202, "linestring", 2, [1, 2]))
        self.assertEqual(f["tags"], {"highway": "residential"})
        self.assertEqual(f["osm_timestamp"], datetime(2026, 9, 2, tzinfo=timezone.utc))
        # osmium's area ids: 'a' + 2 x the way's id, or 2 x the relation's + 1; @type and @id say which.
        area = {"type": "Feature", "id": "a803", "geometry": {"type": "MultiPolygon", "coordinates": []},
                "properties": {"@type": "relation", "@id": 401, "@version": 3, "natural": "water"}}
        f = ox.parse_export_line(json.dumps(area))
        self.assertEqual((f["type"], f["osm_id"], f["geometry"]), ("r", 401, "polygon"))
        no_attrs = {"type": "Feature", "id": "n7", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}
        self.assertEqual(ox.parse_export_line(json.dumps(no_attrs))["osm_id"], 7)
        self.assertIsNone(ox.parse_export_line(""))
        odd = {"type": "Feature", "id": "a9", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}}
        self.assertIsNone(ox.parse_export_line(json.dumps(odd)))

    def test_relations(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.osm")
            with open(path, "w") as f:
                f.write('<?xml version="1.0"?><osm version="0.6"><bounds minlat="43" minlon="-117" maxlat="44" maxlon="-116"/>'
                        '<relation id="503" version="3" timestamp="2026-09-03T00:00:00Z">'
                        '<member type="way" ref="217" role="forward"/><member type="node" ref="9" role=""/>'
                        '<tag k="type" v="route"/><tag k="route" v="bicycle"/></relation></osm>')
            (r,) = list(ox.parse_relations(path))
        self.assertEqual((r["type"], r["osm_id"], r["geometry"], r["osm_version"], r["geom"]), ("r", 503, "relation", 3, None))
        self.assertEqual(r["members"], [{"type": "w", "ref": 217, "role": "forward"}, {"type": "n", "ref": 9, "role": ""}])
        self.assertEqual(r["tags"], {"type": "route", "route": "bicycle"})

    def test_command_lines(self):
        self.assertEqual(ox.cut_command("/a/idaho.osm.pbf", "/c/x.part"),
                         ["osmium", "extract", "--bbox", "-117.05,43.00,-115.95,43.85", "--strategy", "smart",
                          "--set-bounds", "--no-progress", "--overwrite", "--output-format", "pbf", "--output",
                          "/c/x.part", "/a/idaho.osm.pbf"])
        paths = consumer(T, ["w/highway=path,track", "r/route=hiking"], ["linestring", "relation"])
        cmds, config, lines, rels = ox.consumer_commands("/c/valley.osm.pbf", "/w", paths)
        self.assertEqual((config, lines, rels), ("/w/export.json", "/w/features.geojsonseq", "/w/relations.osm"))
        self.assertEqual(cmds[0], ["osmium", "export", "--config", "/w/export.json", "--output-format", "geojsonseq",
                                   "--format-option", "print_record_separator=false", "--geometry-types", "linestring",
                                   "--add-unique-id", "type_id", "--no-progress", "--overwrite", "--output",
                                   "/w/features.geojsonseq", "/c/valley.osm.pbf"])
        self.assertEqual(cmds[1], ["osmium", "cat", "--object-type", "relation", "--no-progress", "--overwrite",
                                   "--output-format", "xml", "--output", "/w/relations.osm", "/c/valley.osm.pbf"])
        self.assertFalse(any("tags-filter" in c for c in cmds))       # its id bitmap costs 1.9 GB on Idaho's ids
        cmds, _, _, rels = ox.consumer_commands("/c/v", "/w", consumer(S, ["w/highway=road"], ["linestring"]))
        self.assertEqual((len(cmds), rels), (1, None))


class ConsumersTest(unittest.TestCase):
    def test_the_repository_s_consumers(self):
        every = ox.consumers()
        ids = [c.id for c in every]
        self.assertEqual(ids[:2], ["roads.osm_valley", "roads.osm_street"])       # osm_valley first
        self.assertEqual(len(set(c.name for c in every)), len(every))
        for c in every:
            with self.subTest(c.id):
                m = c.module()
                self.assertEqual(m.SOURCE["name"], c.name)
                self.assertTrue(callable(m.consume))
                self.assertIsNone(m.SOURCE.get("schedule"))
                self.assertEqual((m.SOURCE["license"], c.source["license"]), ("ODbL", "ODbL"))
                self.assertEqual(c.source["credit"], ox.CREDIT)
        street = next(c for c in every if c.name == S)
        self.assertEqual(street.tables, ("roads.osm_street",))
        self.assertTrue(ox.own_gate(next(c for c in every if c.name == V).module()))
        self.assertFalse(ox.own_gate(street.module()))

    def test_select(self):
        every = [consumer(V, ["w/highway"], ["linestring"], "roads"), consumer(S, ["w/highway"], ["linestring"], "roads"),
                 consumer(T, ["w/highway"], ["linestring"], "trails")]
        self.assertEqual(ox.select(every, None), every)
        self.assertEqual([c.id for c in ox.select(every, ["trails.osm_paths", "osm_street"])],
                         ["roads.osm_street", "trails.osm_paths"])
        with self.assertRaises(SystemExit) as cm:
            ox.select(every, ["roads.osm_nothing"])
        self.assertIn("roads.osm_valley", str(cm.exception))

    def test_one_source_consumed_by_two_plugins_is_refused(self):
        from ingest.tests.test_manifest import Folder, entry, plugin
        folder = Folder(self)
        c = {"source": "osm_x", "tags": ["w/highway"], "geometry": ["linestring"], "tables": ["a.osm_x"]}
        folder.write(plugin("a", [entry("osm_x", kind="manual")], tables=["a.osm_x"], osm_consumers=[c]))
        folder.write(plugin("b", [entry("osm_x", kind="manual")], tables=["a.osm_x"], osm_consumers=[c]))
        with self.assertRaises(manifest.ManifestError):
            ox.consumers(manifest.find([folder.path]))


class CutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fake_osmium(self, cmd):
        with open(cmd[cmd.index("--output") + 1], "wb") as f:
            f.write(b"cut of " + cmd[-1].encode())
        self.calls.append(cmd)
        return ""

    def test_made_once_and_reused_while_the_extract_is_the_same(self):
        self.calls = []
        cut_dir = os.path.join(self.tmp.name, "cut")
        with mock.patch.object(ox, "osmium", self.fake_osmium):
            path, info, made = ox.make_cut("/a/one.osm.pbf", "a" * 32, "one-20261011-aaaaaaaa.osm.pbf", cut_dir, "2026-10-05T20:21:07Z")
            self.assertTrue(made)
            self.assertEqual(path, os.path.join(cut_dir, "valley.osm.pbf"))
            self.assertEqual(ox.read_json(os.path.join(cut_dir, "valley.json")), info)
            self.assertEqual((info["md5"], info["extract"], info["strategy"], info["box"], info["data_as_of"]),
                             ("a" * 32, "one-20261011-aaaaaaaa.osm.pbf", "smart", list(ox.BOX), "2026-10-05T20:21:07Z"))
            self.assertEqual(info["sha256"], hashlib.sha256(b"cut of /a/one.osm.pbf").hexdigest())
            self.assertEqual((info["license"], info["republish"]), ("ODbL", "yes"))
            self.assertIn("Malheur", info["coverage"])
            self.assertFalse(ox.make_cut("/a/one.osm.pbf", "a" * 32, "x", cut_dir)[2])          # reused
            self.assertTrue(ox.make_cut("/a/two.osm.pbf", "b" * 32, "y", cut_dir)[2])           # a new extract
            with open(path, "ab") as f:
                f.write(b"!")                                                               # a damaged cut
            self.assertTrue(ox.make_cut("/a/two.osm.pbf", "b" * 32, "y", cut_dir)[2])
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(sorted(os.listdir(cut_dir)), ["valley.json", "valley.osm.pbf"])        # no .part left

    def test_a_failed_cut_leaves_the_old_one(self):
        self.calls = []
        cut_dir = os.path.join(self.tmp.name, "cut")
        with mock.patch.object(ox, "osmium", self.fake_osmium):
            ox.make_cut("/a/one.osm.pbf", "a" * 32, "one", cut_dir)

        def broken(cmd):
            with open(cmd[cmd.index("--output") + 1], "wb") as f:
                f.write(b"half")
            raise RuntimeError("osmium extract failed (1)")

        with mock.patch.object(ox, "osmium", broken), self.assertRaises(RuntimeError):
            ox.make_cut("/a/two.osm.pbf", "b" * 32, "two", cut_dir)
        self.assertEqual(ox.read_json(os.path.join(cut_dir, "valley.json"))["md5"], "a" * 32)
        self.assertEqual(sorted(os.listdir(cut_dir)), ["valley.json", "valley.osm.pbf"])


# ---- a whole load, with osmium and the database faked -----------------------

class FakeConn:
    """Enough of a connection for the loader: ops.source, ops.fetch, ops.osm_consumer."""

    def __init__(self, state_table=True):
        self.sql, self.states, self.fetches, self.state_table = [], {}, 0, state_table
        self.result = None

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.sql.append((s, params))
        self.result = None
        if s.startswith("select to_regclass"):
            self.result = (self.state_table,)
        elif s.startswith("select md5, extract_file"):
            st = self.states.get(params[0])
            self.result = st and (st["md5"], st["extract_file"], None, None, st["fetch_id"], st["objects"], {})
        elif s.startswith("insert into ops.fetch"):
            self.fetches += 1
            self.result = (self.fetches,)
        elif s.startswith("insert into ops.osm_consumer"):
            cid, source, md5, extract_file, _, fetch_id, objects, _ = params
            self.states[cid] = {"md5": md5, "extract_file": extract_file, "fetch_id": fetch_id, "objects": objects}
        return self

    def fetchone(self):
        return self.result

    def commit(self):
        pass

    def rollback(self):
        pass

    def fetch_rows(self):
        return [p for s, p in self.sql if s.startswith("update ops.fetch")]


class FakeModule:
    def __init__(self, name, fail=False, own_gate=False):
        self.SOURCE = {"name": name, "title": name, "url": ox.PAGE, "access": "open", "schedule": None,
                       "license": "ODbL", "credit": ox.CREDIT}
        self.fail, self.runs, self.marked = fail, [], []
        if own_gate:
            self.state = {}
            self.loaded_md5 = lambda folder: self.state.get(folder)
            self.mark_loaded = lambda folder, md5, path: (self.state.__setitem__(folder, md5),
                                                          self.marked.append(os.path.basename(path)))

    def consume(self, conn, run):
        self.runs.append(run)
        if self.fail:
            raise RuntimeError("this consumer broke")
        run.counts["linestrings"] += 3
        return {"objects": 3, "new": 3}


class FakeConsumer(ox.Consumer):
    modules = {}

    def module(self):
        return self.modules[self.name]


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"TVT_ARCHIVE": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = ox.archive_dir()
        self.cuts = []

        def fake_cut(src, md5, name, cut_dir, data_as_of=None):
            os.makedirs(cut_dir, exist_ok=True)
            path = os.path.join(cut_dir, "valley.osm.pbf")
            with open(path, "w") as f:
                f.write(md5)
            self.cuts.append(name)
            return path, {"bytes": 32, "extract": name, "md5": md5}, True

        for name, value in (("make_cut", fake_cut), ("data_timestamp", lambda src: "2026-10-05T20:21:07Z")):
            p = mock.patch.object(ox, name, value)
            p.start()
            self.addCleanup(p.stop)

    def inbox(self, data=b"pbf bytes", name="idaho-latest.osm.pbf"):
        path = os.path.join(self.folder, "inbox", name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def consumers(self, *specs):
        FakeConsumer.modules = {}
        out = []
        for name, kw in specs:
            FakeConsumer.modules[name] = FakeModule(name, **kw)
            out.append(FakeConsumer("roads", {"name": name, "module": "x", "kind": "manual", "license": "ODbL",
                                              "credit": ox.CREDIT, "republish": "yes"}, ("w/highway",), ("linestring",),
                                    ("roads.x",)))
        return out

    def load(self, conn, path, chosen, **kw):
        lines = []
        result = ox.load_extract(conn, path, chosen, out=lines.append, **kw)
        return result, lines

    def test_a_new_extract_loads_every_consumer_then_is_archived(self):
        chosen = self.consumers((V, {"own_gate": True}), (S, {}))
        conn = FakeConn()
        src = self.inbox()
        md5 = hashlib.md5(b"pbf bytes").hexdigest()
        result, lines = self.load(conn, src, chosen)
        self.assertEqual(result, {"roads.osm_valley": "loaded", "roads.osm_street": "loaded"})
        self.assertEqual(len(self.cuts), 1)                                       # one cut for both
        kept = [n for n in os.listdir(self.folder) if n.endswith(".osm.pbf")]
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0].startswith("idaho-") and kept[0].endswith(f"-{md5[:8]}.osm.pbf"))
        self.assertFalse(os.path.exists(src))
        self.assertEqual(self.cuts, kept)                                         # the cut knows the archived name
        self.assertEqual(conn.states["roads.osm_street"]["md5"], md5)              # the database gate
        self.assertEqual(conn.states["roads.osm_street"]["extract_file"], kept[0])
        self.assertNotIn("roads.osm_valley", conn.states)                         # osm_valley keeps its own file
        self.assertEqual(FakeConsumer.modules[V].marked, kept)
        runs = FakeConsumer.modules[V].runs + FakeConsumer.modules[S].runs
        self.assertEqual({r.cut for r in runs}, {os.path.join(self.folder, "cut", "valley.osm.pbf")})
        self.assertEqual({r.work_parent for r in runs}, {self.folder})
        self.assertEqual({r.data_as_of for r in runs}, {"2026-10-05T20:21:07Z"})
        self.assertEqual(len(conn.fetch_rows()), 2)
        self.assertTrue(all(p[1] for p in conn.fetch_rows()))                       # both ok
        self.assertEqual([p[4] for p in conn.fetch_rows()], [3, 3])                 # records
        sources = [p["name"] for s, p in conn.sql if s.startswith("insert into ops.source")]
        self.assertEqual(sources, [V, S])
        self.assertIn(f"archived: {kept[0]}", lines)

        # The same extract again: nothing is due, so nothing runs and it stays in the inbox.
        again = self.inbox()
        result, lines = self.load(conn, again, chosen)
        self.assertEqual(set(result.values()), {"skipped"})
        self.assertEqual(len(self.cuts), 1)
        self.assertTrue(os.path.exists(again))
        self.assertIn("left in place", lines[-1])

    def test_a_consumer_added_later_loads_the_held_extract_alone(self):
        chosen = self.consumers((V, {"own_gate": True}), (S, {}))
        conn = FakeConn()
        self.load(conn, self.inbox(), chosen)
        held = ox.extracts(self.folder)[0]
        later = self.consumers((V, {"own_gate": True}), (S, {}), (P, {}))
        FakeConsumer.modules[V].state = {self.folder: hashlib.md5(b"pbf bytes").hexdigest()}
        result, _ = self.load(conn, held, ox.select(later, ["roads.osm_paving"]), keep=False)
        self.assertEqual(result, {"roads.osm_paving": "loaded"})
        self.assertEqual(FakeConsumer.modules[V].runs, [])
        self.assertEqual(ox.extracts(self.folder), [held])                          # not moved or copied
        # Without --only, the others are skipped by their gates and the new one is done already.
        result, _ = self.load(conn, held, later, keep=False)
        self.assertEqual(set(result.values()), {"skipped"})
        result, _ = self.load(conn, held, later, keep=False, force=True)
        self.assertEqual(set(result.values()), {"loaded"})

    def test_a_failed_consumer_is_logged_and_the_others_go_on(self):
        chosen = self.consumers((V, {"own_gate": True, "fail": True}), (S, {}))
        conn = FakeConn()
        src = self.inbox()
        result, lines = self.load(conn, src, chosen)
        self.assertEqual(result, {"roads.osm_valley": "failed", "roads.osm_street": "loaded"})
        self.assertTrue(any(l.startswith("roads.osm_valley: FAILED (RuntimeError: this consumer broke)") for l in lines))
        self.assertEqual([p[1] for p in conn.fetch_rows()], [False, True])
        self.assertIn("this consumer broke", conn.fetch_rows()[0][6])
        self.assertFalse(os.path.exists(src))                                      # archived: osm_street has it
        self.assertEqual(FakeConsumer.modules[V].marked, [])                      # not marked: it reruns next time

    def test_when_every_consumer_fails_the_file_stays_in_the_inbox(self):
        chosen = self.consumers((S, {"fail": True}))
        src = self.inbox()
        result, _ = self.load(FakeConn(), src, chosen)
        self.assertEqual(result, {"roads.osm_street": "failed"})
        self.assertTrue(os.path.exists(src))
        self.assertEqual(ox.extracts(self.folder), [])

    def test_a_bad_md5_or_a_missing_state_table_stops_it(self):
        chosen = self.consumers((S, {}))
        src = self.inbox()
        with open(src + ".md5", "w") as f:
            f.write("0" * 32 + "  idaho-latest.osm.pbf\n")
        with self.assertRaises(SystemExit):
            self.load(FakeConn(), src, chosen)
        os.remove(src + ".md5")
        with self.assertRaises(SystemExit) as cm:
            self.load(FakeConn(state_table=False), src, chosen)
        self.assertIn("0019", str(cm.exception))
        self.assertEqual(FakeConsumer.modules[S].runs, [])

    def test_archive_keeps_the_last_two(self):
        chosen = self.consumers((S, {}))
        conn = FakeConn()
        now = time.time()
        for i, data in enumerate([b"first", b"second", b"third"]):
            self.load(conn, self.inbox(data), chosen)
            for p in ox.extracts(self.folder):
                if p.endswith(f"{hashlib.md5(data).hexdigest()[:8]}.osm.pbf"):
                    os.utime(p, (now - 100 + i, now - 100 + i))
        names = [os.path.basename(p) for p in ox.extracts(self.folder)]
        self.assertEqual(len(names), 2)
        self.assertTrue(names[0].endswith(f"{hashlib.md5(b'third').hexdigest()[:8]}.osm.pbf"))


class MainTest(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = ox.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue() + err.getvalue()

    def test_it_needs_to_be_told_which_extract(self):
        code, text = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("--inbox", text)

    def test_only_without_an_archive(self):
        with mock.patch.dict(os.environ, {"TVT_ARCHIVE": ""}):
            code, text = self.run_main("--only", "osm_street")
        self.assertIn("TVT_ARCHIVE", str(code) + text)

    def test_list_without_a_database(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "", "TVT_ARCHIVE": ""}):
            code, text = self.run_main("--list")
        self.assertEqual(code, 0)
        self.assertIn("roads.osm_street", text)
        self.assertIn("w/highway=residential,unclassified,living_street,road,busway,service", text)


# ---- the real pipeline (osmium) --------------------------------------------

@unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool (the ingest image has it)")
class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cut, cls.info, _ = ox.make_cut(FIXTURE, "f" * 32, "osm_landscape.osm", os.path.join(cls.tmp.name, "cut"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def features(self, c):
        with tempfile.TemporaryDirectory() as work:
            run = ox.Run(c, FIXTURE, "osm_landscape.osm", "f" * 32, self.cut, work, None, T0)
            got = list(run.features())
        return got, run.counts

    def test_the_cut_holds_the_lake_across_the_edge(self):
        got, _ = self.features(consumer("osm_waterways", ["a/natural=water", "w/waterway"], ["linestring", "polygon"]))
        shapes = {(f["type"], f["osm_id"], f["geometry"]) for f in got}
        # The pond is closed and only an a/ expression takes it: an area, not a line.
        self.assertEqual(shapes, {("r", 401, "polygon"), ("w", 301, "polygon"), ("w", 302, "linestring")})
        lake = next(f for f in got if f["osm_id"] == 401)
        self.assertEqual(lake["tags"]["name"], "Fixture Lake")
        self.assertEqual(lake["osm_version"], 3)

    def test_paths_with_their_routes(self):
        got, counts = self.features(consumer(T, ["w/highway=track,path,footway,cycleway,bridleway,steps,pedestrian",
                                                 "a/highway=pedestrian", "r/route=hiking,mtb,bicycle,foot,horse"],
                                             ["linestring", "polygon", "relation"]))
        ways = {f["osm_id"] for f in got if f["geometry"] == "linestring"}
        self.assertEqual(ways, {214, 215, 216, 220, 221})                    # not 217, 218 (osm_valley's), not the sidewalks
        self.assertEqual({f["osm_id"] for f in got if f["geometry"] == "polygon"}, {219})
        routes = {f["osm_id"]: f for f in got if f["geometry"] == "relation"}
        self.assertEqual(sorted(routes), [501, 503])                         # not the bus route
        self.assertEqual(routes[503]["members"], [{"type": "w", "ref": 217, "role": "forward"},
                                                  {"type": "w", "ref": 224, "role": ""},
                                                  {"type": "w", "ref": 999999, "role": ""}])
        self.assertGreater(counts["dropped: the partition gives it to osm_valley"], 0)

    def test_paving_points_lines_and_lots(self):
        got, _ = self.features(consumer(P, ["w/highway=service,footway,path,cycleway", "a/amenity=parking",
                                            "n/highway=crossing"], ["point", "linestring", "polygon"]))
        self.assertEqual({f["osm_id"] for f in got if f["geometry"] == "linestring"},
                         {209, 210, 211, 212, 213, 229, 231, 232})
        self.assertEqual({(f["type"], f["osm_id"]) for f in got if f["geometry"] == "polygon"}, {("w", 701)})
        self.assertEqual({f["osm_id"] for f in got if f["geometry"] == "point"}, {801})
        crossing = next(f for f in got if f["osm_id"] == 212)
        self.assertEqual(crossing["way_nodes"], [2121, 801, 2122])

    def test_streets(self):
        street = next(c for c in ox.consumers() if c.name == S)
        got, counts = self.features(street)
        self.assertEqual({f["osm_id"] for f in got}, {202, 204, 205, 206, 207, 208, 224, 227, 228})
        edge = next(f for f in got if f["osm_id"] == 224)
        self.assertEqual(edge["geom"]["coordinates"][0], [-117.06, 43.5])          # kept whole across the edge
        self.assertEqual(counts["dropped: outside the box (completing a multipolygon)"], 1)   # way 307

    def test_the_partition_over_the_real_pipeline(self):
        from plugins.roads.ingest.sources import osm_valley
        ways, _, _ = osm_valley.extract_features(self.cut)
        taken = {V: {w["osm_id"] for w in ways}}
        for name, c in BROAD.items():
            taken[name] = {f["osm_id"] for f in self.features(c)[0]}
        owners = Counter(w for ids in taken.values() for w in ids)
        for w, want in EXPECTED.items():
            with self.subTest(way=w):
                self.assertEqual(owners[w], 0 if want is None else 1)
                if want:
                    self.assertIn(w, taken[want])
        self.assertEqual(set(owners) - set(EXPECTED), set())

    def test_osm_valley_reads_the_same_from_the_cut_as_from_the_whole_file(self):
        from plugins.roads.ingest.sources import osm_valley
        whole, cut = osm_valley.extract_features(FIXTURE), osm_valley.extract_features(self.cut)
        self.assertEqual(whole[0], cut[0])
        self.assertEqual(whole[1], cut[1])


# ---- the database ----------------------------------------------------------

@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (migration 0019 and roads 0001)")
class StoreTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""
    BASE = 9_200_000_000

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('roads.osm_street') is not null").fetchone()[0]:
                raise unittest.SkipTest("roads.osm_street is missing: apply roads 0001")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.conn.execute("update roads.osm_street set active = false where osm_id < %s", (self.BASE,))   # rolled back

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    COLUMNS = [("osm_id", "bigint"), ("highway", "text"), ("service", "text"), ("name", "text"), ("tags", "jsonb"),
               ("osm_version", "int"), ("osm_timestamp", "timestamptz")]

    def row(self, n, name="A Street", version=1, x=-116.3):
        tags = {"highway": "residential", "name": name}
        geom = {"type": "LineString", "coordinates": [[x, 43.6], [x, 43.601]]}
        return (self.BASE + n, "residential", None, name, json.dumps(tags), version, T0, json.dumps(geom))

    def store(self, rows, seen, **kw):
        return ox.store_objects(self.conn, "roads.osm_street", self.COLUMNS, rows, seen, **kw)

    def get(self, n):
        return self.conn.execute(
            """select name, osm_version, active, first_seen, last_seen, ST_X(ST_StartPoint(geom))
               from roads.osm_street where osm_id = %s""", (self.BASE + n,)).fetchone()

    def test_versioned_in_place(self):
        t1, t2, t3 = T0, T0.replace(hour=13), T0.replace(hour=14)
        stats = self.store([self.row(1), self.row(2), self.row(3)], t1)
        self.assertEqual(stats, {"objects": 3, "new": 3, "changed": 0, "unchanged": 0, "reactivated": 0, "retired": 0})
        self.assertEqual(self.get(1)[:5], ("A Street", 1, True, t1, t1))
        # 1 renamed (a new OSM version), 2 moved (a node moved: same version), 3 gone.
        stats = self.store([self.row(1, "B Street", 2), self.row(2, x=-116.2)], t2)
        self.assertEqual(stats, {"objects": 2, "new": 0, "changed": 2, "unchanged": 0, "reactivated": 0, "retired": 1})
        self.assertEqual(self.get(1)[:5], ("B Street", 2, True, t1, t2))         # first_seen kept
        self.assertAlmostEqual(self.get(2)[5], -116.2)
        self.assertEqual(self.get(3)[2:5], (False, t1, t1))                        # retired, never deleted
        # 3 comes back; 1 and 2 unchanged.
        stats = self.store([self.row(1, "B Street", 2), self.row(2, x=-116.2), self.row(3)], t3)
        self.assertEqual(stats, {"objects": 3, "new": 0, "changed": 0, "unchanged": 2, "reactivated": 1, "retired": 0})
        self.assertEqual(self.get(3)[2:5], (True, t1, t3))

    def test_shrink_guard_and_twice_in_one_load(self):
        self.store([self.row(i) for i in range(1000)], T0)
        with self.assertRaises(RuntimeError) as cm:
            self.store([self.row(i) for i in range(400)], T0.replace(hour=13))
        self.assertIn("--allow-shrink", str(cm.exception))
        self.assertEqual(self.conn.execute("select count(*) from roads.osm_street where active").fetchone()[0], 1000)
        stats = self.store([self.row(i) for i in range(400)], T0.replace(hour=13), allow_shrink=True)
        self.assertEqual(stats["retired"], 600)
        with self.assertRaises(RuntimeError) as cm:
            self.store([self.row(5), self.row(5)], T0.replace(hour=14))
        self.assertIn("twice", str(cm.exception))

    def test_state_rows(self):
        street = next(c for c in ox.consumers() if c.name == S)
        ox.db.ensure_source(self.conn, street.module().SOURCE)
        before = ox.db_state(self.conn, street.id)
        ox.set_db_state(self.conn, street, "c" * 32, "idaho-x.osm.pbf", None, None, 5, {"new": 5})
        self.assertEqual(ox.db_state(self.conn, street.id)["md5"], "c" * 32)
        ox.set_db_state(self.conn, street, "d" * 32, "idaho-y.osm.pbf", "2026-10-05T20:21:07Z", None, 6, {})
        st = ox.db_state(self.conn, street.id)
        self.assertEqual((st["md5"], st["extract_file"], st["objects"], st["data_as_of"]),
                         ("d" * 32, "idaho-y.osm.pbf", 6, "2026-10-05T20:21:07Z"))
        self.assertIsInstance(before, dict)


if __name__ == "__main__":
    unittest.main()
