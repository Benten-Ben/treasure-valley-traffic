"""Tests for roads' osm_paving consumer (plugins/roads/ingest/sources/osm_paving.py) and the
developed land it measures against (plugins/roads/ingest/developed.py).

Offline: the manifest entries (its tags take every way the partition gives it, and the partition
gives it exactly the shared fixture's paving ways; the CDL's source entry and command), the rules
(kinds, material and the land rule, widths, markings and rail crossings), the rows and their
links, measured shares applied to them, and reading a developed-land build (developed_build.py
writes synthetic ones). Database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (with roads 0005), inside a transaction that is rolled back: loading a
build, measuring in PostGIS, a load with and without developed land, measuring again after a new
build, and what the tables refuse. With osmium-tool, the synthetic fixture (fixtures/
osm_paving.osm: invented ids, names and coordinates) goes through the loader's smart cut and this
consumer's features, a lot across the box's edge and the alley cases included. The worker step
that makes builds from the CDL is tested in the worker image (test_developed_build.py).

Run: python3 -m unittest discover -s plugins -t .
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone
from unittest import mock

from ingest import manifest, osm_extract
from plugins.roads.ingest import developed
from plugins.roads.ingest.sources import osm_paving as pv
from plugins.roads.tests import developed_build

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "osm_paving.osm")
HAVE_OSMIUM = shutil.which("osmium") is not None
DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def consumer():
    return next(c for c in osm_extract.consumers() if c.id == "roads.osm_paving")


def way(osm_id, x=-116.30, **tags):
    return {"type": "w", "osm_id": osm_id, "geometry": "linestring", "tags": tags, "osm_version": 2,
            "osm_timestamp": T0, "geom": {"type": "LineString", "coordinates": [[x, 43.6], [x, 43.601]]},
            "way_nodes": [osm_id * 10 + 1, osm_id * 10 + 9]}


def node(osm_id, x=-116.30, y=43.6, **tags):
    return {"type": "n", "osm_id": osm_id, "geometry": "point", "tags": tags, "osm_version": 1,
            "osm_timestamp": T0, "geom": {"type": "Point", "coordinates": [x, y]}}


def square(osm_id, x0, x1, y0=43.6, y1=43.601, kind="w"):
    return {"type": "MultiPolygon", "coordinates": [[[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]]}


def area(osm_id, x0=-116.31, x1=-116.309, kind="w", **tags):
    return {"type": kind, "osm_id": osm_id, "geometry": "polygon", "tags": tags, "osm_version": 3,
            "osm_timestamp": T0, "geom": square(osm_id, x0, x1)}


def as_dict(row, columns):
    return dict(zip([c for c, _ in columns], row))


class ManifestTest(unittest.TestCase):
    def test_the_entry(self):
        c = consumer()
        self.assertEqual(c.tags, ("w/highway=service,footway,path,cycleway,raceway,escape", "a/amenity=parking,parking_space",
                                  "n/highway=crossing", "n/crossing", "n/kerb"))
        self.assertEqual(c.geometry, ("point", "linestring", "polygon"))
        self.assertEqual(c.tables, (pv.WAYS, pv.LOTS, pv.NODES))
        roads = next(p for p in manifest.find() if p.name == "roads")
        self.assertLessEqual(set(c.tables), set(roads.manifest["tables"]))
        self.assertEqual((c.source["license"], c.source["republish"], c.source["credit"]), ("ODbL", "yes", osm_extract.CREDIT))
        self.assertFalse(osm_extract.own_gate(pv))                          # its gate is ops.osm_consumer
        self.assertIsNone(pv.SOURCE["schedule"])
        self.assertIn("osm_paving", osm_extract.OWNERS)                     # it's a partition owner: it follows osm_valley

    def test_its_tags_take_every_way_the_partition_gives_it(self):
        f = osm_extract.TagFilter(consumer().tags)
        for tags in ({"highway": "service"}, {"highway": "service", "service": "driveway"},
                     {"highway": "service", "area": "yes"}, *({"highway": h, "footway": v}
                     for h in osm_extract.WALKWAYS for v in osm_extract.PAVING_FOOTWAYS)):
            with self.subTest(tags):
                self.assertEqual(osm_extract.owner(tags), "osm_paving")
                self.assertTrue(f.matches("w", tags))
        self.assertEqual(set(pv.WALKWAY_KINDS), osm_extract.PAVING_FOOTWAYS)

    def test_no_network_code_and_not_scheduled(self):
        for name in ("run", "download", "http", "urllib", "USER_AGENT"):
            self.assertFalse(hasattr(pv, name), name)
        for module in (pv, developed):
            with open(module.__file__, encoding="utf-8") as f:
                self.assertNotIn("urllib", f.read())
        from ingest.sources import SOURCES, STREAMS
        for name in ("osm_paving", "cdl_developed"):
            self.assertNotIn(name, SOURCES)
            self.assertNotIn(name, STREAMS)

    def test_the_cdl_is_a_source_of_its_own(self):
        """The developed land's licence and credit are listed in the manifest (a manual source) and
        in ops.source (developed.SOURCE), where the exports' inputs are looked up."""
        roads = next(p for p in manifest.find() if p.name == "roads")
        entry = next(e for e in roads.manifest["sources"] if e["name"] == "cdl_developed")
        self.assertEqual((entry["kind"], entry["module"], entry["license"], entry["credit"], entry["republish"]),
                         ("manual", "ingest.developed", developed.LICENSE, developed.SOURCE["credit"], "yes"))
        self.assertEqual(developed.SOURCE["name"], "cdl_developed")
        self.assertIsNone(developed.SOURCE["schedule"])
        self.assertEqual(developed.credit(2025), "USDA NASS Cropland Data Layer 2025")
        from ingest.sources import COMMANDS, command
        self.assertEqual(COMMANDS["roads-developed-load"][0].name, "roads")
        self.assertIs(command("roads-developed-load"), developed.main)
        self.assertLessEqual({"roads.developed_build", "roads.developed_land"}, set(roads.manifest["tables"]))

    def test_no_raster_is_read_in_the_ingest_image(self):
        """docs/17 §17.8 Q9: rasters are decoded in the worker. The ingest side reads polygons only."""
        for module in (pv, developed):
            with open(module.__file__, encoding="utf-8") as f:
                text = f.read()
            for word in ("zlib", "struct", "osgeo", "numpy", "basemap.ground"):
                self.assertNotIn(f"import {word}", text, (module.__name__, word))


class PartitionRowsTest(unittest.TestCase):
    """The partition's osm_paving rows: over core's shared fixture, this consumer (its real tags)
    gets exactly the highway ways the partition gives osm_paving, and none of another owner's."""

    def test_the_shared_fixture(self):
        from ingest.tests.test_osm_extract import EXPECTED, fixture_features
        counts = Counter()
        got = {f["osm_id"] for f in osm_extract.select_features(fixture_features(), consumer(), counts)
               if "highway" in f["tags"]}
        self.assertEqual(got, {w for w, owner in EXPECTED.items() if owner == "osm_paving"})
        self.assertGreater(counts["dropped: the partition gives it to osm_paths"], 0)
        self.assertGreater(counts["dropped: the partition gives it to osm_street"], 0)


class RulesTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(pv.way_kind({"highway": "service"}), "service")
        self.assertEqual(pv.way_kind({"highway": "service", "service": "spur"}), "service")
        self.assertEqual(pv.way_kind({"highway": "service", "service": "drive-through"}), "drive_through")
        self.assertEqual(pv.way_kind({"highway": "service", "service": "emergency_access"}), "emergency_access")
        self.assertEqual(pv.way_kind({"highway": "path", "footway": "sidewalk"}), "sidewalk")
        self.assertEqual(pv.way_kind({"highway": "cycleway", "footway": "crossing"}), "crossing")
        self.assertEqual(pv.way_kind({"highway": "raceway"}), "raceway")
        self.assertEqual(pv.way_kind({"highway": "escape"}), "escape")
        self.assertEqual(pv.lot_kind({"amenity": "parking"}), "lot")
        self.assertEqual(pv.lot_kind({"amenity": "parking_space"}), "space")
        self.assertIsNone(pv.lot_kind({"amenity": "bench"}))
        self.assertEqual(pv.node_kind({"highway": "crossing"}), "crossing")
        self.assertEqual(pv.node_kind({"crossing": "unmarked", "kerb": "lowered"}), "crossing")   # a crossing first
        self.assertEqual(pv.node_kind({"kerb": "flush"}), "kerb")
        self.assertIsNone(pv.node_kind({"highway": "traffic_signals"}))

    def test_raceways_and_escape_ramps_have_no_default_material(self):
        for kind in ("raceway", "escape"):
            self.assertEqual(pv.kind_default(kind), (None, False))
            self.assertEqual(pv.material(kind, {}, 1.0), ("unknown", None))          # even on developed land
            self.assertEqual(pv.material(kind, {"surface": "asphalt"}), ("asphalt", "surface"))
            self.assertEqual(pv.material(kind, {"surface": "paved"}), ("concrete", "surface"))

    def test_raceway_and_escape_rows(self):
        for n, hw, est in ((21, "raceway", 10.0), (22, "escape", 6.0)):
            row = as_dict(pv.way_row(way(n, highway=hw)), pv.WAY_COLUMNS)
            self.assertEqual((row["kind"], row["highway"], row["material"], row["material_source"], row["width_est_m"],
                              row["width_source"]), (hw, hw, "unknown", None, est, "default"))
            self.assertEqual(osm_extract.owner({"highway": hw}), "osm_paving")

    def test_material_from_the_surface_tag(self):
        for tags, want in [({"surface": "asphalt"}, "asphalt"), ({"surface": "Concrete"}, "concrete"),
                           ({"surface": "paving_stones"}, "concrete"), ({"surface": "compacted"}, "gravel"),
                           ({"surface": "unpaved"}, "gravel"), ({"surface": "dirt"}, "dirt"),
                           ({"surface": "asphalt;gravel"}, "asphalt")]:
            with self.subTest(tags):
                self.assertEqual(pv.material("service", tags, None), (want, "surface"))   # land doesn't matter
        self.assertEqual(pv.material("service", {"surface": "paved"}), ("asphalt", "surface"))
        self.assertEqual(pv.material("sidewalk", {"surface": "paved"}), ("concrete", "surface"))
        self.assertEqual(pv.material("driveway", {"surface": "paved"}), ("concrete", "surface"))

    def test_untagged_service_ways_and_lots_need_developed_land(self):
        """Plan C11: a kind's default only on CDL developed land, otherwise unknown."""
        for kind in ("service", "driveway", "parking_aisle", "drive_through", "emergency_access", "lot", "space"):
            with self.subTest(kind):
                default = pv.KIND_DEFAULTS[kind][0]
                self.assertEqual(pv.material(kind, {}, 0.5), (default, "default"))
                self.assertEqual(pv.material(kind, {}, 1.0), (default, "default"))
                self.assertEqual(pv.material(kind, {}, 0.49), ("unknown", None))
                self.assertEqual(pv.material(kind, {}, None), ("unknown", None))
                self.assertEqual(pv.material(kind, {"surface": "yes"}, None), ("unknown", None))   # not a value we read
                self.assertTrue(pv.kind_default(kind)[1])
        self.assertEqual(pv.material("driveway", {}, 0.9), ("concrete", "default"))

    def test_walkways_and_structures_take_their_default_anywhere(self):
        for kind, want in [("sidewalk", "concrete"), ("crossing", "asphalt"), ("access_aisle", "asphalt"),
                           ("traffic_island", "concrete")]:
            with self.subTest(kind):
                self.assertEqual(pv.material(kind, {}, None), (want, "default"))
                self.assertFalse(pv.kind_default(kind)[1])
        self.assertEqual(pv.material("lot", {"parking": "multi-storey"}, None), ("concrete", "default"))
        self.assertEqual(pv.material("lot", {"parking": "rooftop"}, 0.0), ("concrete", "default"))
        self.assertEqual(pv.material("lot", {"parking": "underground"}, 1.0), ("unknown", None))
        self.assertEqual(pv.kind_default("lot", "underground"), (None, False))

    def test_widths(self):
        self.assertEqual(pv.width("sidewalk", {}), (None, 1.5, "default"))
        self.assertEqual(pv.width("sidewalk", {"width": "2 m"}), (2.0, 2.0, "tagged"))
        self.assertEqual(pv.width("driveway", {"width": "12 ft"}), (3.66, 3.66, "tagged"))
        self.assertEqual(pv.width("parking_aisle", {}), (None, 7.0, "default"))
        self.assertEqual(pv.width("parking_aisle", {"oneway": "yes"}), (None, 4.5, "default"))
        self.assertEqual(pv.width("service", {"width": "wide"}), (None, 5.5, "default"))
        self.assertEqual(pv.width("raceway", {}), (None, 10.0, "default"))        # ⚠️ estimates
        self.assertEqual(pv.width("escape", {}), (None, 6.0, "default"))
        self.assertEqual(pv.width("raceway", {"width": "12"}), (12.0, 12.0, "tagged"))
        self.assertEqual(set(pv.WIDTHS), set(pv.KIND_DEFAULTS) - {"lot", "space"})

    def test_markings(self):
        for tags, want in [({"crossing": "marked"}, True), ({"crossing": "zebra"}, True),
                           ({"crossing": "uncontrolled"}, True), ({"crossing": "unmarked"}, False),
                           ({"crossing": "no"}, False), ({"crossing": "traffic_signals"}, True), ({}, None),
                           ({"crossing": "traffic_signals", "crossing:markings": "no"}, False),
                           ({"highway": "traffic_signals", "crossing": "unmarked"}, False),
                           ({"crossing:markings": "ladder"}, True), ({"crossing:markings": "yes"}, True),
                           ({"crossing:markings": "no", "crossing": "uncontrolled"}, False),
                           ({"crossing:markings": "zebra", "crossing": "unmarked"}, True),
                           ({"crossing_ref": "zebra"}, True),
                           ({"railway": "crossing", "crossing": "uncontrolled"}, None),
                           ({"railway": "level_crossing", "crossing:markings": "zebra"}, None),
                           ({"railway": "tram_crossing", "crossing": "marked"}, None),
                           ({"railway": "abandoned", "crossing": "marked"}, True),      # a rail trail
                           ({"railway": "crossing", "highway": "traffic_signals"}, None),   # a rail crossing at signals
                           ({"railway": "disused", "crossing": "unmarked"}, False)]:
            with self.subTest(tags):
                self.assertIs(pv.marked(tags), want)
        self.assertTrue(pv.rail_crossing({"railway": " Level_Crossing "}))
        self.assertFalse(pv.rail_crossing({"railway": "abandoned"}))
        self.assertFalse(pv.rail_crossing({}))
        self.assertTrue(pv.at_signals({"crossing": "traffic_signals"}))
        self.assertTrue(pv.at_signals({"highway": "traffic_signals", "crossing": "marked"}))
        self.assertFalse(pv.at_signals({"crossing": "marked"}))
        self.assertIsNone(pv.from_nodes([None, None]))
        self.assertIs(pv.from_nodes([False, None]), False)
        self.assertIs(pv.from_nodes([False, True]), True)

    def test_the_partition_s_alleys(self):
        """An alley is osm_street's only as a line exactly tagged service=alley and not area=yes:
        the table's check (roads 0002) tests the same raw tags."""
        self.assertEqual(osm_extract.owner({"highway": "service", "service": "alley"}), "osm_street")
        for tags in ({"highway": "service", "service": "alley", "area": "yes"},
                     {"highway": "service", "service": "alley "}, {"highway": "service", "service": "Alley"}):
            with self.subTest(tags):
                self.assertEqual(osm_extract.owner(tags), "osm_paving")


class RowsTest(unittest.TestCase):
    """rows_from over synthetic features, and measured shares applied with with_land()."""

    def rows(self, features, way_shares=None, lot_measures=None, measured=True):
        counts = Counter()
        ways, lots, nodes = pv.rows_from(features, counts)
        if measured:
            pv.with_land(ways, lots, way_shares, lot_measures)
        return ({r[0]: as_dict(r, pv.WAY_COLUMNS) for r in ways}, {(r[0], r[1]): as_dict(r, pv.LOT_COLUMNS) for r in lots},
                {r[0]: as_dict(r, pv.NODE_COLUMNS) for r in nodes}, counts, (ways, lots, nodes))

    def test_ways(self):
        ways, _, _, _, (raw, _, _) = self.rows([
            way(1, highway="service", service="driveway"),
            way(2, -116.27, highway="service"),
            way(3, -116.27, highway="service", surface="asphalt"),
            way(4, highway="footway", footway="sidewalk", name="  Fixture   Walk ", layer="1", bridge="yes"),
            way(5, -116.27, highway="footway", footway="sidewalk"),
            way(6, highway="service", service="parking_aisle")],
            way_shares={1: 1.0, 2: 0.0, 3: 0.0, 4: 1.0, 6: 0.49})
        self.assertEqual((ways[1]["kind"], ways[1]["material"], ways[1]["material_source"], ways[1]["developed"]),
                         ("driveway", "concrete", "default", 1.0))
        self.assertEqual((ways[2]["material"], ways[2]["material_source"], ways[2]["developed"]), ("unknown", None, 0.0))
        self.assertEqual((ways[3]["material"], ways[3]["material_source"]), ("asphalt", "surface"))
        self.assertEqual(ways[3]["developed"], 0.0)                         # measured for every service way
        self.assertEqual((ways[4]["material"], ways[4]["developed"], ways[4]["name"], ways[4]["layer"], ways[4]["bridge"]),
                         ("concrete", None, "Fixture Walk", 1, True))      # walkways aren't measured
        self.assertEqual(ways[5]["material"], "concrete")                   # walkways: anywhere
        self.assertEqual((ways[6]["material"], ways[6]["developed"]), ("unknown", 0.49))
        self.assertEqual((ways[4]["width_est_m"], ways[4]["width_source"], ways[4]["oneway"]), (1.5, "default", "no"))
        self.assertEqual(json.loads(raw[0][-1])["type"], "LineString")
        self.assertEqual(len(raw[0]), len(pv.WAY_COLUMNS) + 1)
        self.assertEqual([pv.needs_land(r) for r in raw], [True, True, True, False, False, True])

    def test_without_land_untagged_service_ways_and_lots_are_unknown(self):
        ways, lots, _, _, _ = self.rows([way(1, highway="service", service="driveway"),
                                         way(2, highway="footway", footway="sidewalk"),
                                         area(3, amenity="parking"), area(4, amenity="parking", parking="rooftop")],
                                        lot_measures={("w", 3): (None, 8970.0), ("w", 4): (None, 10.0)})
        self.assertEqual((ways[1]["material"], ways[1]["developed"]), ("unknown", None))
        self.assertEqual(ways[2]["material"], "concrete")
        self.assertEqual((lots[("w", 3)]["material"], lots[("w", 3)]["area_m2"]), ("unknown", 8970.0))
        self.assertEqual(lots[("w", 4)]["material"], "concrete")          # a structure: anywhere
        unmeasured, lots, _, _, _ = self.rows([way(1, highway="service"), area(3, amenity="parking")], measured=False)
        self.assertEqual((unmeasured[1]["material"], unmeasured[1]["developed"], lots[("w", 3)]["area_m2"]),
                         ("unknown", None, None))                         # rows_from leaves the land to measure()

    def test_crossings_take_their_nodes_markings_and_nodes_their_ways(self):
        ways, _, nodes, _, _ = self.rows([
            node(11, highway="crossing", crossing="unmarked"), node(19, kerb="lowered"),
            node(21, highway="crossing", crossing="marked"), node(29, kerb="raised"),
            node(31, highway="crossing", crossing="traffic_signals"),
            node(41, crossing="zebra"),
            way(1, highway="footway", footway="crossing"),
            way(2, highway="footway", footway="crossing", crossing="unmarked", **{"crossing:markings": "no"}),
            way(3, highway="footway", footway="crossing"),
            way(4, highway="footway", footway="sidewalk")])
        self.assertEqual((ways[1]["marked"], ways[1]["marked_from"]), (False, "node"))
        self.assertEqual((ways[2]["marked"], ways[2]["marked_from"], ways[2]["crossing_markings"]), (False, "way", "no"))
        self.assertEqual((ways[3]["marked"], ways[3]["marked_from"]), (True, "node"))      # at signals: a stated exception, painted from its node
        self.assertEqual((ways[4]["marked"], ways[4]["crossing"]), (None, None))            # not a crossing
        self.assertEqual(nodes[11]["ways"], [1])
        self.assertEqual(nodes[19]["ways"], [1])
        self.assertEqual(nodes[21]["ways"], [2])
        self.assertEqual(nodes[41]["ways"], [4])
        self.assertTrue(nodes[21]["marked"])
        self.assertEqual((nodes[31]["marked"], nodes[31]["signals"]), (True, True))
        self.assertEqual((nodes[19]["kind"], nodes[19]["kerb"], nodes[19]["marked"], nodes[19]["signals"]),
                         ("kerb", "lowered", None, False))

    def test_rail_crossings_and_rail_trails(self):
        """A rail crossing is never a crosswalk, and a rail crossing way doesn't take its nodes'
        marking; a rail trail's crossing (railway=abandoned) is an ordinary crossing."""
        ways, _, nodes, _, _ = self.rows([
            node(11, highway="crossing", crossing="marked"),
            node(21, highway="crossing", crossing="marked", railway="abandoned"),
            node(31, railway="level_crossing", crossing="uncontrolled"),
            way(1, highway="footway", footway="crossing", railway="crossing"),             # mistagged, through 11
            way(2, highway="footway", footway="crossing", crossing="marked", railway="abandoned"),
            way(3, highway="footway", footway="crossing", railway="disused")])             # through 31
        ways_nodes = {1: [11], 2: [21], 3: [31]}
        self.assertEqual((ways[1]["marked"], ways[1]["marked_from"]), (None, None))
        self.assertEqual((ways[2]["marked"], ways[2]["marked_from"]), (True, "way"))
        self.assertEqual((ways[3]["marked"], ways[3]["marked_from"]), (None, None))        # its node: a rail crossing
        self.assertEqual((nodes[21]["marked"], nodes[21]["railway"]), (True, "abandoned"))
        self.assertEqual((nodes[31]["marked"], nodes[31]["railway"]), (None, "level_crossing"))
        self.assertEqual(ways_nodes, {w: [n for n in nodes if w in nodes[n]["ways"]] for w in ways_nodes})

    def test_lots(self):
        _, lots, _, counts, (_, raw, _) = self.rows([
            area(1, amenity="parking", parking="surface", capacity="40", name="Fixture Lot"),
            area(2, -116.26, -116.259, amenity="parking"),
            area(3, -116.26, -116.259, kind="r", type="multipolygon", amenity="parking", surface="gravel"),
            area(4, amenity="parking_space"),
            area(5, amenity="parking", parking="underground", layer="-1", capacity="many"),
            node(6, amenity="parking")],
            lot_measures={("w", 1): (1.0, 8970.4), ("w", 2): (0.0, 8970.4), ("r", 3): (0.0, 8970.4),
                          ("w", 4): (0.5, 8970.4), ("w", 5): (1.0, 8970.4)})
        one = lots[("w", 1)]
        self.assertEqual((one["kind"], one["material"], one["material_source"], one["developed"], one["capacity"],
                          one["area_m2"]), ("lot", "asphalt", "default", 1.0, 40, 8970.4))
        self.assertEqual((lots[("w", 2)]["material"], lots[("w", 2)]["developed"]), ("unknown", 0.0))
        self.assertEqual((lots[("r", 3)]["material"], lots[("r", 3)]["material_source"]), ("gravel", "surface"))
        self.assertEqual((lots[("w", 4)]["kind"], lots[("w", 4)]["material"]), ("space", "asphalt"))
        self.assertEqual((lots[("w", 5)]["material"], lots[("w", 5)]["capacity"], lots[("w", 5)]["layer"]),
                         ("unknown", None, -1))
        self.assertEqual(len(lots), 5)                                      # the point lot isn't kept
        self.assertEqual(counts["skipped: points that aren't crossings or kerbs"], 1)
        self.assertEqual(json.loads(raw[0][-1])["type"], "MultiPolygon")

    def test_a_way_drawn_as_an_area_keeps_its_outline_once(self):
        ring = area(7, highway="service", area="yes")
        ways, lots, _, _, _ = self.rows([ring])
        self.assertTrue(ways[7]["area"])
        self.assertEqual(lots, {})
        both, _, _, _, (raw, _, _) = self.rows([{**ring, "geometry": "polygon"}, way(7, highway="service")])
        self.assertFalse(both[7]["area"])                                  # the line, when osmium gave both
        self.assertEqual(len(raw), 1)
        lot_too, lots, _, _, _ = self.rows([area(8, highway="service", amenity="parking"), way(8, highway="service")])
        self.assertEqual((list(lot_too), list(lots)), ([8], [("w", 8)]))    # a service way that's also a lot: both

    def test_alleys_as_the_partition_gives_them(self):
        """What osmium gives this consumer for the alleys the partition sends it: a closed line
        (its export makes areas only of lots), an open one, a stray space in the value."""
        ring = [[-116.30, 43.603], [-116.299, 43.603], [-116.299, 43.604], [-116.30, 43.604], [-116.30, 43.603]]
        closed = {**way(21, highway="service", service="alley", area="yes"),
                  "geom": {"type": "LineString", "coordinates": ring}}
        ways, _, _, _, _ = self.rows([closed, way(22, highway="service", service="alley", area="yes"),
                                      way(23, highway="service", service="alley ")])
        self.assertEqual((ways[21]["area"], ways[22]["area"], ways[23]["service"]), (True, False, "alley"))

    def test_summary(self):
        ways, lots, nodes = pv.rows_from([way(1, highway="service"), way(2, highway="footway", footway="crossing",
                                                                         crossing="marked"),
                                          node(3, kerb="flush"), area(4, amenity="parking")])
        pv.with_land(ways, lots, {1: 1.0}, {("w", 4): (1.0, 100.0)})
        s = pv.summary(ways, lots, nodes)
        self.assertEqual(s["ways by kind"], "service 1 / crossing 1")
        self.assertEqual(s["crossing ways marked"], "True:way 1")
        self.assertEqual(s["lots by material"], "asphalt:default 1")


class BuildFileTest(unittest.TestCase):
    """Reading a developed-land build (developed.read_build, pieces) as the worker writes it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def folder(self, name="20261011T120000Z"):
        return os.path.join(self.tmp.name, name)

    def test_a_build_reads_back(self):
        squares = [developed_build.square(-1619500, 2463300, 100), developed_build.square(-1619300, 2463300, 30)]
        doc = developed_build.write(self.folder(), squares)
        self.assertEqual(developed.read_build(self.folder())["counts"], doc["counts"])
        self.assertEqual(doc["counts"]["area_km2"], 0.0109)
        got = list(developed.pieces(self.folder()))
        self.assertEqual([n for n, _ in got], [1, 2])
        self.assertEqual(json.loads(got[0][1]), squares[0])

    def test_refused(self):
        sq = [developed_build.square(0, 0, 10)]
        cases = [({"format": "tvt-roads-developed/0"}, "format"), ({"classes": [121, 122, 123, 124]}, "classes"),
                 ({"srid": 32611}, "srid"), ({"build_id": "another"}, "build_id"),
                 ({"cdl": {"file": "x.tif", "year": 2025, "res_m": 10, "sha256": "c" * 64, "license": "CC0",
                           "credit": "USDA NASS Cropland Data Layer 2025"}}, "licence"),
                 ({"counts": {"pieces": 0}}, "no pieces")]
        for i, (override, words) in enumerate(cases):
            with self.subTest(override):
                folder = self.folder(f"b{i}")
                developed_build.write(folder, sq, **override)
                with self.assertRaises(developed.BuildError) as cm:
                    developed.read_build(folder)
                self.assertIn(words, str(cm.exception))
        folder = self.folder("changed")
        developed_build.write(folder, sq)
        with open(os.path.join(folder, developed.LAND_FILE), "ab") as f:
            f.write(b"\0")
        with self.assertRaises(developed.BuildError):
            developed.read_build(folder)                                     # not the file build.json describes
        with self.assertRaises(developed.BuildError):
            developed.read_build(self.folder("missing"))                     # unfinished: no build.json
        folder = self.folder("line")
        developed_build.write(folder, [{"type": "LineString", "coordinates": [[0, 0], [1, 1]]}])
        with self.assertRaises(developed.BuildError):
            list(developed.pieces(folder))

    def test_describe(self):
        self.assertIn("none loaded", developed.describe(None))
        line = developed.describe({"id": "b1", "credit": "USDA NASS Cropland Data Layer 2025",
                                   "cdl_file": "cdl_2025_10m.tif", "license": "public domain", "cdl_sha256": "f" * 64})
        self.assertIn("USDA NASS Cropland Data Layer 2025", line)
        self.assertIn("f" * 64, line)                                       # the whole sha256

    def test_dry_run(self):
        developed_build.write(self.folder(), [developed_build.square(0, 0, 10)])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(developed.main(["--build", self.folder(), "--dry-run"]), 0)
        self.assertIn("1 pieces", out.getvalue())
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(developed.main(["--build", self.folder("missing"), "--dry-run"]), 1)


class FakeRun:
    def __init__(self, features, seen_at=T0, allow_shrink=False):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, allow_shrink
        self.md5, self.counts = "f" * 32, Counter()

    def features(self):
        return iter(self._features)


# The tests' developed land: everything west of this meridian (at the fixture's latitudes), none east of it.
LAND_WEST, LAND_SOUTH, LAND_SPLIT, LAND_NORTH = -116.62, 42.99, -116.275, 43.62


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with roads 0005)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back. Every active row is retired
    first (rolled back too), so a load's rows are the active ones; synthetic ids start far above
    OpenStreetMap's (Idaho's node ids run past 13 billion). The developed land is a synthetic build
    loaded in the same transaction: the envelope from LAND_WEST to LAND_SPLIT, on NASS's grid."""
    BASE = 900_000_000_000

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('roads.developed_land') is not null").fetchone()[0]:
                raise unittest.SkipTest("roads.osm_paving and friends are missing: apply roads 0002")
            land = json.loads(c.execute(
                "select ST_AsGeoJSON(ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), 5070), 6)",
                (LAND_WEST, LAND_SOUTH, LAND_SPLIT, LAND_NORTH)).fetchone()[0])
        cls.tmp = tempfile.TemporaryDirectory()
        cls.land = os.path.join(cls.tmp.name, "20261011T120000Z")
        developed_build.write(cls.land, [land])
        cls.other = os.path.join(cls.tmp.name, "20270301T120000Z")         # the next year's: no developed land
        developed_build.write(cls.other, [developed_build.square(0, 0, 10)], year=2026, cdl_sha256="d" * 64)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        for table in (pv.WAYS, pv.LOTS, pv.NODES):
            self.conn.execute(f"update {table} set active = false where active")          # rolled back
        self.loaded = developed.load(self.conn, self.land)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def marks(self, by):
        if not self.conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
            return None
        return self.conn.execute("select coalesce(sum(marks), 0) from ops.build_pending "
                                 "where build = 'roads-build' and marked_by = %s", (by,)).fetchone()[0]

    def features(self):
        b = self.BASE
        return [node(b + 11, highway="crossing", crossing="marked"), node(b + 12, kerb="lowered"),
                {**way(1, highway="footway", footway="crossing"), "osm_id": b + 1, "way_nodes": [b + 11, b + 12]},
                {**way(2, -116.27, highway="service"), "osm_id": b + 2},
                {**way(3, highway="service", service="driveway"), "osm_id": b + 3},
                {**area(4, amenity="parking"), "osm_id": b + 4},
                {**area(5, kind="r", type="multipolygon", amenity="parking", surface="gravel"), "osm_id": b + 4}]

    def test_a_build_loads_as_the_current_land(self):
        self.assertEqual((self.loaded["pieces"], self.loaded["build"]), (1, "20261011T120000Z"))
        row = self.conn.execute("""select cdl_year, cdl_sha256, credit, license, republish, pieces, parts >= 1,
                                          area_km2 > 1000, current
                                     from roads.developed_build where id = '20261011T120000Z'""").fetchone()
        self.assertEqual(row, (2025, "c" * 64, "USDA NASS Cropland Data Layer 2025", "public domain", "yes", 1, True,
                               True, True))
        self.assertEqual(self.conn.execute("select max(ST_NPoints(geom)) <= %s, min(ST_SRID(geom)) from "
                                           "roads.developed_land", (developed.SUBDIVIDE,)).fetchone(), (True, 5070))
        self.assertEqual(developed.current(self.conn)["id"], "20261011T120000Z")
        self.assertIn("skipped", developed.load(self.conn, self.land))     # already current
        stats = developed.load(self.conn, self.other)
        self.assertEqual((stats["pieces"], stats["replaced"]), (1, "20261011T120000Z"))
        self.assertEqual(self.conn.execute("select id from roads.developed_build where current").fetchall(),
                         [("20270301T120000Z",)])
        self.assertEqual(self.conn.execute("select count(*) from roads.developed_land").fetchone()[0], 1)

    def test_measure(self):
        b = 'ST_GeomFromText(%s, 4326)'
        got = developed.measure(self.conn, query=f"""
            select 'w'::char(1) as t, 1::bigint as id, {b} as geom union all
            select 'w', 2, {b} union all select 'w', 3, {b} union all select 'w', 4, {b}""",
            params=("LINESTRING(-116.30 43.6, -116.30 43.601)", "LINESTRING(-116.27 43.6, -116.27 43.601)",
                    "LINESTRING(-116.2775 43.6, -116.2725 43.6)", "LINESTRING(-116.30 43.6, -116.30 43.6)"))
        self.assertEqual((got[("w", 1)], got[("w", 2)], got[("w", 4)]), (1.0, 0.0, None))
        self.assertAlmostEqual(got[("w", 3)], 0.5, delta=0.01)              # across the split
        lots = developed.measure(self.conn, [("w", 1, json.dumps(square(1, -116.2785, -116.2715)))], area=True)
        share, m2 = lots[("w", 1)]
        self.assertAlmostEqual(share, 0.5, delta=0.01)
        self.assertAlmostEqual(m2, 0.007 * 80740 * 0.001 * 111100, delta=60)   # 0.007 x 0.001 degrees at 43.6 N
        unmeasured = developed.measure(self.conn, [("w", 1, json.dumps(square(1, -116.30, -116.29)))], area=True,
                                       land=False)
        self.assertIsNone(unmeasured[("w", 1)][0])
        self.assertGreater(unmeasured[("w", 1)][1], 0)

    def test_consume(self):
        b = self.BASE
        before = self.marks("osm_paving")
        stats = pv.consume(self.conn, FakeRun(self.features()))
        self.assertEqual((stats["objects"], stats["new"], stats["osm_paving new"], stats["osm_parking new"],
                          stats["osm_walk_node new"]), (7, 7, 3, 2, 2))
        self.assertIn("USDA NASS Cropland Data Layer 2025", stats["developed land"])
        self.assertIn("c" * 64, stats["developed land"])
        rows = self.conn.execute("""select osm_id - %s, kind, material, material_source, developed, marked, marked_from
                                    from roads.osm_paving where active order by 1""", (b,)).fetchall()
        self.assertEqual(rows, [(1, "crossing", "asphalt", "default", None, True, "node"),
                                (2, "service", "unknown", None, 0.0, None, None),
                                (3, "driveway", "concrete", "default", 1.0, None, None)])
        lots = self.conn.execute("""select osm_type, material, material_source, developed, ST_GeometryType(geom),
                                           area_m2 between 8900 and 9050
                                    from roads.osm_parking where osm_id = %s order by 1""", (b + 4,)).fetchall()
        self.assertEqual(lots, [("r", "gravel", "surface", 1.0, "ST_MultiPolygon", True),
                                ("w", "asphalt", "default", 1.0, "ST_MultiPolygon", True)])
        nodes = self.conn.execute("select osm_id - %s, kind, marked, ways from roads.osm_walk_node where active "
                                  "order by 1", (b,)).fetchall()
        self.assertEqual(nodes, [(11, "crossing", True, [b + 1]), (12, "kerb", None, [b + 1])])
        if before is not None:
            self.assertEqual(self.marks("osm_paving"), before + 1)
        # Again, an hour on, without the lot relation and the kerb: unchanged, retired, and versioned in place.
        later = T0.replace(hour=13)
        stats = pv.consume(self.conn, FakeRun(self.features()[:1] + self.features()[2:6], later))
        self.assertEqual((stats["new"], stats["retired"], stats["osm_paving unchanged"], stats["osm_parking unchanged"]),
                         (0, 2, 3, 1))
        self.assertEqual(self.conn.execute("select active, first_seen from roads.osm_parking where osm_type = 'r' and "
                                           "osm_id = %s", (b + 4,)).fetchone(), (False, T0))
        self.assertEqual(self.conn.execute("select ways from roads.osm_walk_node where osm_id = %s", (b + 11,)).fetchone()[0],
                         [b + 1])

    def test_without_land_then_a_build_measures_them(self):
        """No current build: the load runs and says so, untagged service ways and lots unknown. Loading
        a build measures them and marks roads-build; a build without that land unmarks them again."""
        self.conn.execute("update roads.developed_build set current = false")
        stats = pv.consume(self.conn, FakeRun(self.features()))
        self.assertIn("none loaded", stats["developed land"])
        q = "select material, material_source, developed from roads.osm_paving where osm_id = %s"
        self.assertEqual(self.conn.execute(q, (self.BASE + 3,)).fetchone(), ("unknown", None, None))
        self.assertEqual(self.conn.execute("select material, area_m2 > 8900 from roads.osm_parking where osm_type = 'w' "
                                           "and osm_id = %s", (self.BASE + 4,)).fetchone(), ("unknown", True))
        before = self.marks("cdl_developed")
        stats = developed.load(self.conn, self.land)
        self.assertEqual((stats["osm_paving remeasured"], stats["osm_parking remeasured"]), (2, 2))
        self.assertEqual(self.conn.execute(q, (self.BASE + 3,)).fetchone(), ("concrete", "default", 1.0))
        self.assertEqual(self.conn.execute(q, (self.BASE + 2,)).fetchone(), ("unknown", None, 0.0))
        if before is not None:
            self.assertEqual(self.marks("cdl_developed"), before + 1)
        stats = pv.consume(self.conn, FakeRun(self.features(), T0.replace(hour=13)))
        self.assertEqual(stats["changed"], 0)                              # measured the same way at load time
        stats = developed.load(self.conn, self.other)
        self.assertEqual((stats["osm_paving remeasured"], stats["osm_parking remeasured"]), (1, 2))   # way 2 was 0 already
        self.assertEqual(self.conn.execute(q, (self.BASE + 3,)).fetchone(), ("unknown", None, 0.0))
        self.assertEqual(developed.load(self.conn, self.other, force=True)["osm_paving remeasured"], 0)

    def test_the_tables_refuse_what_the_partition_never_gives_them(self):
        for tags in ({"highway": "service", "service": "alley"},              # osm_street's
                     {"highway": "track", "footway": "sidewalk"}):            # osm_paths'
            with self.subTest(tags):
                self.conn.execute("savepoint s")
                with self.assertRaises(self.psycopg.errors.CheckViolation):
                    pv.consume(self.conn, FakeRun([{**way(6, **tags), "osm_id": self.BASE + 6}]))
                self.conn.execute("rollback to savepoint s")

    def test_raceways_and_escape_ramps_are_stored(self):
        """The two highway values 0005 added: rows load, and the service-kinds check still holds."""
        features = [{**way(31, highway="raceway", surface="asphalt"), "osm_id": self.BASE + 31},
                    {**way(32, highway="escape"), "osm_id": self.BASE + 32}]
        pv.consume(self.conn, FakeRun(features))
        self.assertEqual(self.conn.execute("""select osm_id - %s, kind, highway, material, material_source, width_est_m
                                              from roads.osm_paving where active order by 1""", (self.BASE,)).fetchall(),
                         [(31, "raceway", "raceway", "asphalt", "surface", 10.0),
                          (32, "escape", "escape", "unknown", None, 6.0)])
        self.conn.execute("savepoint s")
        with self.assertRaises(self.psycopg.errors.CheckViolation):          # a raceway is not a service way
            self.conn.execute("update roads.osm_paving set kind = 'service' where osm_id = %s", (self.BASE + 31,))
        self.conn.execute("rollback to savepoint s")

    def test_the_alleys_the_partition_gives_the_paving(self):
        """An alley tagged area=yes, closed (as osmium gives it: a closed line) or not, and one whose
        value has a stray space: the partition gives them to osm_paving, and the table takes them."""
        ring = [[-116.30, 43.603], [-116.299, 43.603], [-116.299, 43.604], [-116.30, 43.604], [-116.30, 43.603]]
        tags = ({"highway": "service", "service": "alley", "area": "yes"},
                {"highway": "service", "service": "alley", "area": "yes"},
                {"highway": "service", "service": "alley "})
        features = [{**way(7 + i, **t), "osm_id": self.BASE + 7 + i} for i, t in enumerate(tags)]
        features[0]["geom"] = {"type": "LineString", "coordinates": ring}
        for f in features:
            self.assertEqual(osm_extract.owner(f["tags"]), "osm_paving")
        pv.consume(self.conn, FakeRun(features))
        self.assertEqual(self.conn.execute("select osm_id - %s, service, area, ST_IsClosed(geom) from roads.osm_paving "
                                           "where active order by 1", (self.BASE,)).fetchall(),
                         [(7, "alley", True, True), (8, "alley", False, False), (9, "alley", False, False)])

    def test_a_rail_trail_crossing_node_may_be_marked(self):
        b = self.BASE
        pv.consume(self.conn, FakeRun([node(b + 21, highway="crossing", crossing="marked", railway="abandoned"),
                                       node(b + 22, railway="level_crossing", crossing="marked")]))
        self.assertEqual(self.conn.execute("select osm_id - %s, marked, railway from roads.osm_walk_node where active "
                                           "order by 1", (b,)).fetchall(),
                         [(21, True, "abandoned"), (22, None, "level_crossing")])
        self.conn.execute("savepoint s")
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            self.conn.execute("update roads.osm_walk_node set marked = true where osm_id = %s", (b + 22,))
        self.conn.execute("rollback to savepoint s")

    @unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool")
    def test_the_fixture_through_the_loader(self):
        with tempfile.TemporaryDirectory() as d:
            cut, _, _ = osm_extract.make_cut(FIXTURE, "e" * 32, "osm_paving.osm", os.path.join(d, "cut"))
            run = osm_extract.Run(consumer(), FIXTURE, "osm_paving.osm", "e" * 32, cut, d, None, T0)
            with contextlib.redirect_stdout(io.StringIO()):
                stats = pv.consume(self.conn, run)
        ways = {r[0]: r[1:] for r in self.conn.execute(
            """select osm_id, kind, material, material_source, marked, marked_from, area, width_est_m, service
               from roads.osm_paving where active""").fetchall()}
        self.assertEqual(sorted(ways), [601, 602, 603, 604, 605, 608, 609, 611, 612, 613, 614, 615, 616, 617, 618,
                                        621, 622, 623, 624])
        self.assertEqual(ways[601][:3], ("driveway", "concrete", "default"))
        self.assertEqual(ways[602][:3] + ways[602][-2:-1], ("parking_aisle", "asphalt", "surface", 4.5))
        self.assertEqual(ways[604][:3], ("service", "unknown", None))
        self.assertEqual(ways[605][-2], 6.0)
        self.assertEqual(ways[608][:3], ("service", "gravel", "surface"))
        self.assertTrue(ways[609][5])                                       # drawn as an area
        self.assertEqual(ways[612][3:5], (True, "way"))
        self.assertEqual(ways[613][3:5], (False, "node"))
        self.assertEqual(ways[614][3:5], (None, None))
        self.assertEqual(ways[616][3:5], (False, "node"))
        self.assertEqual((ways[621][5], ways[621][-1]), (True, "alley"))     # an alley drawn as an area: a closed line
        self.assertEqual((ways[622][5], ways[622][-1]), (False, "alley"))    # area=yes on an open way
        self.assertEqual((ways[623][5], ways[623][-1]), (False, "alley"))    # "alley " with a stray space
        self.assertEqual(ways[624][3:5], (True, "way"))                      # a rail trail's crossing
        lots = {(r[0], r[1]): r[2:] for r in self.conn.execute(
            """select osm_type, osm_id, kind, material, material_source, ST_YMin(geom) < 43.0, ST_NumInteriorRings(
                 ST_GeometryN(geom, 1)) from roads.osm_parking where active""").fetchall()}
        self.assertEqual(sorted(lots), [("r", 761), ("w", 701), ("w", 702), ("w", 703), ("w", 704), ("w", 705),
                                        ("w", 706)])
        self.assertEqual(lots[("r", 761)], ("lot", "asphalt", "default", True, 1))     # whole across the edge, with its hole
        self.assertEqual(lots[("w", 701)][:3], ("lot", "asphalt", "default"))
        self.assertEqual(lots[("w", 702)][:3], ("lot", "concrete", "default"))
        self.assertEqual(lots[("w", 703)][:3], ("space", "asphalt", "default"))
        self.assertEqual(lots[("w", 704)][:3], ("lot", "gravel", "surface"))
        self.assertEqual(lots[("w", 705)][:3], ("lot", "unknown", None))
        self.assertEqual(lots[("w", 706)][:3], ("lot", "unknown", None))
        nodes = {r[0]: r[1:] for r in self.conn.execute(
            "select osm_id, kind, marked, signals, kerb, railway, ways from roads.osm_walk_node where active"
        ).fetchall()}
        self.assertEqual(sorted(nodes), [6119, 6122, 6132, 6142, 6162, 6242, 6902, 6903, 6904, 6906])
        self.assertEqual(nodes[6119], ("kerb", None, False, "lowered", None, [611]))
        self.assertEqual(nodes[6122][:2] + nodes[6122][-1:], ("crossing", True, [612]))
        self.assertEqual(nodes[6142][1:3], (None, True))
        self.assertEqual(nodes[6242][1:2] + nodes[6242][4:], (True, "abandoned", [624]))   # a rail trail: may be marked
        self.assertEqual(nodes[6903][1:2] + nodes[6903][4:5], (None, "crossing"))   # a rail crossing: never marked
        self.assertEqual(nodes[6904][:2] + nodes[6904][3:4], ("crossing", True, "flush"))
        self.assertEqual(nodes[6906][1], True)
        self.assertEqual(stats["objects"], len(ways) + len(lots) + len(nodes))
        self.assertGreater(run.counts["dropped: the partition gives it to osm_street"], 0)
        self.assertGreater(run.counts["dropped: the partition gives it to osm_paths"], 0)


if __name__ == "__main__":
    unittest.main()
