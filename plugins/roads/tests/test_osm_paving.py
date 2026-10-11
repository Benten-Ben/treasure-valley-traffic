"""Tests for roads' osm_paving consumer (plugins/roads/ingest/sources/osm_paving.py) and its
developed-land reader (plugins/roads/ingest/cdl.py).

Offline: the manifest entry (its tags take every way the partition gives it, and the partition
gives it exactly the shared fixture's paving ways), the rules (kinds, material and the CDL rule,
widths, markings), the rows and their links, the Albers projection against PROJ's, and the
raster reader on synthetic GeoTIFFs (cdl_tiff.py). With osmium-tool, the synthetic fixture
(fixtures/osm_paving.osm: invented ids, names and coordinates) goes through the loader's smart
cut and this consumer's features, a lot across the box's edge included. Database tests run only
against a scratch database named by TVT_TEST_DATABASE_URL (with roads 0002), inside a transaction
that is rolled back.

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
from plugins.roads.ingest import cdl
from plugins.roads.ingest.sources import osm_paving as pv
from plugins.roads.tests import cdl_tiff

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
        self.assertEqual(c.tags, ("w/highway=service,footway,path,cycleway", "a/amenity=parking,parking_space",
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
        for module in (pv, cdl):
            with open(module.__file__, encoding="utf-8") as f:
                self.assertNotIn("urllib", f.read())
        from ingest.sources import SOURCES, STREAMS
        self.assertNotIn("osm_paving", SOURCES)
        self.assertNotIn("osm_paving", STREAMS)


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
        self.assertEqual(pv.lot_kind({"amenity": "parking"}), "lot")
        self.assertEqual(pv.lot_kind({"amenity": "parking_space"}), "space")
        self.assertIsNone(pv.lot_kind({"amenity": "bench"}))
        self.assertEqual(pv.node_kind({"highway": "crossing"}), "crossing")
        self.assertEqual(pv.node_kind({"crossing": "unmarked", "kerb": "lowered"}), "crossing")   # a crossing first
        self.assertEqual(pv.node_kind({"kerb": "flush"}), "kerb")
        self.assertIsNone(pv.node_kind({"highway": "traffic_signals"}))

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
                self.assertTrue(pv.needs_land(kind, {}))
                self.assertFalse(pv.needs_land(kind, {"surface": "gravel"}))
        self.assertEqual(pv.material("driveway", {}, 0.9), ("concrete", "default"))

    def test_walkways_and_structures_take_their_default_anywhere(self):
        for kind, want in [("sidewalk", "concrete"), ("crossing", "asphalt"), ("access_aisle", "asphalt"),
                           ("traffic_island", "concrete")]:
            with self.subTest(kind):
                self.assertEqual(pv.material(kind, {}, None), (want, "default"))
                self.assertFalse(pv.needs_land(kind, {}))
        self.assertEqual(pv.material("lot", {"parking": "multi-storey"}, None), ("concrete", "default"))
        self.assertEqual(pv.material("lot", {"parking": "rooftop"}, 0.0), ("concrete", "default"))
        self.assertEqual(pv.material("lot", {"parking": "underground"}, 1.0), ("unknown", None))
        self.assertFalse(pv.needs_land("lot", {"parking": "underground"}))

    def test_widths(self):
        self.assertEqual(pv.width("sidewalk", {}), (None, 1.5, "default"))
        self.assertEqual(pv.width("sidewalk", {"width": "2 m"}), (2.0, 2.0, "tagged"))
        self.assertEqual(pv.width("driveway", {"width": "12 ft"}), (3.66, 3.66, "tagged"))
        self.assertEqual(pv.width("parking_aisle", {}), (None, 7.0, "default"))
        self.assertEqual(pv.width("parking_aisle", {"oneway": "yes"}), (None, 4.5, "default"))
        self.assertEqual(pv.width("service", {"width": "wide"}), (None, 5.5, "default"))
        self.assertEqual(set(pv.WIDTHS), set(pv.KIND_DEFAULTS) - {"lot", "space"})

    def test_markings(self):
        for tags, want in [({"crossing": "marked"}, True), ({"crossing": "zebra"}, True),
                           ({"crossing": "uncontrolled"}, True), ({"crossing": "unmarked"}, False),
                           ({"crossing": "no"}, False), ({"crossing": "traffic_signals"}, None), ({}, None),
                           ({"crossing:markings": "ladder"}, True), ({"crossing:markings": "yes"}, True),
                           ({"crossing:markings": "no", "crossing": "uncontrolled"}, False),
                           ({"crossing:markings": "zebra", "crossing": "unmarked"}, True),
                           ({"crossing_ref": "zebra"}, True),
                           ({"railway": "crossing", "crossing": "uncontrolled"}, None)]:
            with self.subTest(tags):
                self.assertIs(pv.marked(tags), want)
        self.assertTrue(pv.at_signals({"crossing": "traffic_signals"}))
        self.assertTrue(pv.at_signals({"highway": "traffic_signals", "crossing": "marked"}))
        self.assertFalse(pv.at_signals({"crossing": "marked"}))
        self.assertIsNone(pv.from_nodes([None, None]))
        self.assertIs(pv.from_nodes([False, None]), False)
        self.assertIs(pv.from_nodes([False, True]), True)

    def test_the_cdl_is_found_or_the_load_says_how(self):
        with tempfile.TemporaryDirectory() as d:
            sources = os.path.join(d, "sources", "cdl", "out")
            archive = os.path.join(d, "archive", "roads", "cdl")
            os.makedirs(sources)
            os.makedirs(archive)
            env = {"TVT_SOURCES": os.path.join(d, "sources"), "TVT_ARCHIVE": os.path.join(d, "archive")}
            with self.assertRaises(RuntimeError) as cm:
                pv.cdl_path(env)
            self.assertIn("TVT_CDL=none", str(cm.exception))
            open(os.path.join(sources, pv.CDL_NAME), "wb").close()
            self.assertEqual(pv.cdl_path(env), os.path.join(sources, pv.CDL_NAME))
            open(os.path.join(archive, pv.CDL_NAME), "wb").close()
            self.assertEqual(pv.cdl_path(env), os.path.join(archive, pv.CDL_NAME))        # production's copy first
            self.assertEqual(pv.cdl_path({**env, "TVT_CDL": os.path.join(sources, pv.CDL_NAME)}),
                             os.path.join(sources, pv.CDL_NAME))
            self.assertIsNone(pv.cdl_path({**env, "TVT_CDL": "none"}))
            with self.assertRaises(RuntimeError):
                pv.cdl_path({"TVT_CDL": os.path.join(d, "missing.tif")})


class RowsTest(unittest.TestCase):
    """rows_from over synthetic features, with a synthetic CDL (developed west of -116.275)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "cdl.tif")
        cdl_tiff.synthetic_cdl(cls.path)
        cls.raster = cdl.Raster(cls.path)
        cls.land = cdl.Developed(cls.raster)

    @classmethod
    def tearDownClass(cls):
        cls.raster.close()
        cls.tmp.cleanup()

    def rows(self, features, land="cdl"):
        counts = Counter()
        ways, lots, nodes = pv.rows_from(features, self.land if land == "cdl" else land, counts)
        return ({r[0]: as_dict(r, pv.WAY_COLUMNS) for r in ways}, {(r[0], r[1]): as_dict(r, pv.LOT_COLUMNS) for r in lots},
                {r[0]: as_dict(r, pv.NODE_COLUMNS) for r in nodes}, counts, (ways, lots, nodes))

    def test_ways(self):
        ways, _, _, _, (raw, _, _) = self.rows([
            way(1, highway="service", service="driveway"),
            way(2, -116.27, highway="service"),
            way(3, -116.27, highway="service", surface="asphalt"),
            way(4, highway="footway", footway="sidewalk", name="  Fixture   Walk ", layer="1", bridge="yes"),
            way(5, -116.27, highway="footway", footway="sidewalk")])
        self.assertEqual((ways[1]["kind"], ways[1]["material"], ways[1]["material_source"], ways[1]["developed"]),
                         ("driveway", "concrete", "default", 1.0))
        self.assertEqual((ways[2]["material"], ways[2]["material_source"], ways[2]["developed"]), ("unknown", None, 0.0))
        self.assertEqual((ways[3]["material"], ways[3]["material_source"]), ("asphalt", "surface"))
        self.assertEqual(ways[3]["developed"], 0.0)                         # measured for every service way
        self.assertEqual((ways[4]["material"], ways[4]["developed"], ways[4]["name"], ways[4]["layer"], ways[4]["bridge"]),
                         ("concrete", None, "Fixture Walk", 1, True))
        self.assertEqual(ways[5]["material"], "concrete")                   # walkways: anywhere
        self.assertEqual((ways[4]["width_est_m"], ways[4]["width_source"], ways[4]["oneway"]), (1.5, "default", "no"))
        self.assertEqual(json.loads(raw[0][-1])["type"], "LineString")
        self.assertEqual(len(raw[0]), len(pv.WAY_COLUMNS) + 1)

    def test_without_the_cdl_untagged_service_ways_are_unknown(self):
        ways, lots, _, _, _ = self.rows([way(1, highway="service", service="driveway"),
                                         way(2, highway="footway", footway="sidewalk"),
                                         area(3, amenity="parking")], land=None)
        self.assertEqual((ways[1]["material"], ways[1]["developed"]), ("unknown", None))
        self.assertEqual(ways[2]["material"], "concrete")
        self.assertEqual(lots[("w", 3)]["material"], "unknown")

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
        self.assertEqual((ways[3]["marked"], ways[3]["marked_from"]), (None, None))       # at signals: not known
        self.assertEqual((ways[4]["marked"], ways[4]["crossing"]), (None, None))            # not a crossing
        self.assertEqual(nodes[11]["ways"], [1])
        self.assertEqual(nodes[19]["ways"], [1])
        self.assertEqual(nodes[21]["ways"], [2])
        self.assertEqual(nodes[41]["ways"], [4])
        self.assertTrue(nodes[21]["marked"])
        self.assertEqual((nodes[31]["marked"], nodes[31]["signals"]), (None, True))
        self.assertEqual((nodes[19]["kind"], nodes[19]["kerb"], nodes[19]["marked"], nodes[19]["signals"]),
                         ("kerb", "lowered", None, False))

    def test_lots(self):
        _, lots, _, counts, (_, raw, _) = self.rows([
            area(1, amenity="parking", parking="surface", capacity="40", name="Fixture Lot"),
            area(2, -116.26, -116.259, amenity="parking"),
            area(3, -116.26, -116.259, kind="r", type="multipolygon", amenity="parking", surface="gravel"),
            area(4, amenity="parking_space"),
            area(5, amenity="parking", parking="underground", layer="-1", capacity="many"),
            node(6, amenity="parking")])
        one = lots[("w", 1)]
        self.assertEqual((one["kind"], one["material"], one["material_source"], one["developed"], one["capacity"]),
                         ("lot", "asphalt", "default", 1.0, 40))
        self.assertAlmostEqual(one["area_m2"], 80.74 * 111.10, delta=5)    # 0.001 x 0.001 degrees at 43.6 N
        self.assertEqual((lots[("w", 2)]["material"], lots[("w", 2)]["developed"]), ("unknown", 0.0))
        self.assertEqual((lots[("r", 3)]["material"], lots[("r", 3)]["material_source"]), ("gravel", "surface"))
        self.assertEqual(lots[("w", 4)]["kind"], "space")
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

    def test_summary(self):
        ways, lots, nodes = pv.rows_from([way(1, highway="service"), way(2, highway="footway", footway="crossing",
                                                                         crossing="marked"),
                                          node(3, kerb="flush"), area(4, amenity="parking")], self.land)
        s = pv.summary(ways, lots, nodes)
        self.assertEqual(s["ways by kind"], "service 1 / crossing 1")
        self.assertEqual(s["crossing ways marked"], "True:way 1")
        self.assertEqual(s["lots by material"], "asphalt:default 1")


class AlbersTest(unittest.TestCase):
    # PROJ's EPSG:4269 -> EPSG:5070 (pyproj in the worker image, Oct 11, 2026)
    REFERENCE = [((-116.3, 43.6), (-1619433.451846304, 2463320.1230126396)),
                 ((-117.05, 43.0), (-1693019.0811799911, 2410975.971675459)),
                 ((-115.95, 43.85), (-1586114.5536070275, 2484687.6847388907)),
                 ((-116.2023, 43.615), (-1611404.3015286708, 2463295.4776527914)),
                 ((-96.0, 23.0), (0.0, 0.0)),
                 ((-120.0, 50.0), (-1731861.3844999608, 3217670.2851711377))]

    def test_matches_proj_to_a_millimetre(self):
        for (lon, lat), (x, y) in self.REFERENCE:
            with self.subTest((lon, lat)):
                gx, gy = cdl.to_albers(lon, lat)
                self.assertAlmostEqual(gx, x, delta=0.001)
                self.assertAlmostEqual(gy, y, delta=0.001)

    def test_area(self):
        # 0.01 x 0.01 degrees at 43.6 N on GRS 80: 807.4 m (the parallel) x 1111.0 m (the meridian)
        self.assertAlmostEqual(cdl.area_m2(square(0, -116.31, -116.30, 43.6, 43.61)["coordinates"]), 897_020, delta=200)
        hole = [[[-116.31, 43.6], [-116.30, 43.6], [-116.30, 43.61], [-116.31, 43.61], [-116.31, 43.6]],
                [[-116.306, 43.604], [-116.304, 43.604], [-116.304, 43.606], [-116.306, 43.606], [-116.306, 43.604]]]
        self.assertAlmostEqual(cdl.area_m2([hole]), 897_020 * 0.96, delta=200)


class RasterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def raster(self, rows, **kwargs):
        path = os.path.join(self.tmp.name, f"r{len(os.listdir(self.tmp.name))}.tif")
        cdl_tiff.write(path, rows, -1000.0, 2000.0, 10.0, **kwargs)
        r = cdl.Raster(path)
        self.addCleanup(r.close)
        return r

    def pattern(self, width=300, height=270):
        return [bytes((r * 7 + c * 3) % 250 + 1 for c in range(width)) for r in range(height)]

    def test_every_layout_reads_the_same(self):
        rows = self.pattern()
        layouts = [{}, {"tile": 64}, {"tile": 64, "predictor": 2}, {"tile": None, "rows_per_strip": 16},
                   {"tile": None, "deflate": False}, {"tile": 128, "deflate": False, "big": True},
                   {"tile": 64, "order": ">"}, {"tile": None, "rows_per_strip": 7, "predictor": 2, "order": ">"}]
        for kwargs in layouts:
            with self.subTest(kwargs):
                r = self.raster(rows, **kwargs)
                self.assertEqual((r.width, r.height, r.epsg, r.x0, r.y0, r.sx, r.sy), (300, 270, 5070, -1000, 2000, 10, 10))
                for col, row in [(0, 0), (299, 0), (0, 269), (299, 269), (150, 133), (63, 64), (64, 63), (255, 256)]:
                    self.assertEqual(r.at(col, row), rows[row][col])
                self.assertEqual(r.value(-1000 + 10 * 150 + 5, 2000 - 10 * 133 - 5), rows[133][150])

    def test_outside_and_no_data(self):
        rows = [b"\x00\x7a", b"\x01\x7c"]
        r = self.raster(rows, tile=None)
        self.assertIsNone(r.value(-1000 + 1, 2000 - 1))                    # no data
        self.assertEqual(r.value(-1000 + 15, 2000 - 1), 122)
        self.assertEqual(r.value(-1000 + 19.99, 2000 - 19.99), 124)
        self.assertIsNone(r.value(-1000 - 0.01, 2000 - 1))
        self.assertIsNone(r.value(-1000 + 20, 2000 - 1))
        self.assertIsNone(r.value(-1000 + 1, 2000 - 20))

    def test_refused(self):
        path = os.path.join(self.tmp.name, "two.tif")
        cdl_tiff.write(path, [b"\x01\x02"] * 3, 0.0, 30.0, 10.0, tile=None, bands=2)
        with self.assertRaises(cdl.RasterError):
            cdl.Raster(path)
        r = self.raster([b"\x01"], epsg=32611)
        with self.assertRaises(cdl.RasterError):
            cdl.Developed(r)

    def test_shares(self):
        path = os.path.join(self.tmp.name, "cdl.tif")
        split = cdl_tiff.synthetic_cdl(path, res=10.0, split_lon=-116.30, bounds=(-116.32, 43.595, -116.28, 43.61))
        with cdl.Raster(path) as r:
            land = cdl.Developed(r)
            self.assertEqual(land.line_share([[-116.31, 43.6], [-116.31, 43.601]]), 1.0)
            self.assertEqual(land.line_share([[-116.29, 43.6], [-116.29, 43.601]]), 0.0)
            # east-west across the split: a quarter west of it
            share = land.line_share([[-116.3010, 43.6], [-116.2970, 43.6]])
            self.assertAlmostEqual(share, 0.25, delta=0.04)
            self.assertEqual(land.line_share([[-116.31, 43.6], [-116.31, 43.6]]), 1.0)          # a point: one sample
            self.assertEqual(land.line_share([[-116.31, 43.6]]), 1.0)
            self.assertIsNone(land.line_share([[-100.0, 40.0], [-100.0, 40.001]]))              # off the raster
            self.assertEqual(land.area_share(square(0, -116.312, -116.311)["coordinates"]), 1.0)
            self.assertAlmostEqual(land.area_share(square(0, -116.302, -116.298)["coordinates"]), 0.5, delta=0.05)
            tiny = square(0, -116.31, -116.30997, 43.6, 43.60002)["coordinates"]                 # no cell centre inside
            self.assertEqual(land.area_share(tiny), 1.0)
            self.assertIsNone(land.area_share([]))
        self.assertLess(cdl.to_albers(-116.3001, 43.6)[0], split)

    def test_inside(self):
        ring = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
        self.assertTrue(cdl.inside(1, 1, [ring]))
        self.assertFalse(cdl.inside(5, 5, [ring, hole]))
        self.assertFalse(cdl.inside(11, 5, [ring]))


class FakeRun:
    def __init__(self, features, seen_at=T0, allow_shrink=False):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, allow_shrink
        self.md5, self.counts = "f" * 32, Counter()

    def features(self):
        return iter(self._features)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with roads 0002)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""
    BASE = 9_400_000_000

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('roads.osm_walk_node') is not null").fetchone()[0]:
                raise unittest.SkipTest("roads.osm_paving and friends are missing: apply roads 0002")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cdl = os.path.join(cls.tmp.name, "cdl.tif")
        cdl_tiff.synthetic_cdl(cls.cdl)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        for table in (pv.WAYS, pv.LOTS, pv.NODES):
            self.conn.execute(f"update {table} set active = false where active")          # rolled back
        self.env = mock.patch.dict(os.environ, {pv.CDL_ENV: self.cdl})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.conn.rollback()
        self.conn.close()

    def features(self):
        b = self.BASE
        return [node(b + 11, highway="crossing", crossing="marked"), node(b + 12, kerb="lowered"),
                {**way(1, highway="footway", footway="crossing"), "osm_id": b + 1, "way_nodes": [b + 11, b + 12]},
                {**way(2, -116.27, highway="service"), "osm_id": b + 2},
                {**way(3, highway="service", service="driveway"), "osm_id": b + 3},
                {**area(4, amenity="parking"), "osm_id": b + 4},
                {**area(5, kind="r", type="multipolygon", amenity="parking", surface="gravel"), "osm_id": b + 4}]

    def test_consume(self):
        b = self.BASE
        if self.conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
            before = self.conn.execute("select coalesce(sum(marks), 0) from ops.build_pending "
                                       "where build = 'roads-build' and marked_by = 'osm_paving'").fetchone()[0]
        stats = pv.consume(self.conn, FakeRun(self.features()))
        self.assertEqual((stats["objects"], stats["new"], stats["osm_paving new"], stats["osm_parking new"],
                          stats["osm_walk_node new"]), (7, 7, 3, 2, 2))
        self.assertIn("USDA NASS Cropland Data Layer 2025", stats["developed land"])
        rows = self.conn.execute("""select osm_id - %s, kind, material, material_source, developed, marked, marked_from
                                    from roads.osm_paving where osm_id > %s order by 1""", (b, b)).fetchall()
        self.assertEqual(rows, [(1, "crossing", "asphalt", "default", None, True, "node"),
                                (2, "service", "unknown", None, 0.0, None, None),
                                (3, "driveway", "concrete", "default", 1.0, None, None)])
        lots = self.conn.execute("""select osm_type, material, material_source, ST_GeometryType(geom), area_m2 > 8000
                                    from roads.osm_parking where osm_id = %s order by 1""", (b + 4,)).fetchall()
        self.assertEqual(lots, [("r", "gravel", "surface", "ST_MultiPolygon", True),
                                ("w", "asphalt", "default", "ST_MultiPolygon", True)])
        nodes = self.conn.execute("select osm_id - %s, kind, marked, ways from roads.osm_walk_node where osm_id > %s "
                                  "order by 1", (b, b)).fetchall()
        self.assertEqual(nodes, [(11, "crossing", True, [b + 1]), (12, "kerb", None, [b + 1])])
        if self.conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
            after = self.conn.execute("select sum(marks) from ops.build_pending "
                                      "where build = 'roads-build' and marked_by = 'osm_paving'").fetchone()[0]
            self.assertEqual(after, before + 1)
        # Again, an hour on, without the lot relation and the kerb: unchanged, retired, and versioned in place.
        later = T0.replace(hour=13)
        stats = pv.consume(self.conn, FakeRun(self.features()[:1] + self.features()[2:6], later))
        self.assertEqual((stats["new"], stats["retired"], stats["osm_paving unchanged"]), (0, 2, 3))
        self.assertEqual(self.conn.execute("select active, first_seen from roads.osm_parking where osm_type = 'r' and "
                                           "osm_id = %s", (b + 4,)).fetchone(), (False, T0))
        self.assertEqual(self.conn.execute("select ways from roads.osm_walk_node where osm_id = %s", (b + 11,)).fetchone()[0],
                         [b + 1])

    def test_without_the_cdl(self):
        with mock.patch.dict(os.environ, {pv.CDL_ENV: "none"}):
            stats = pv.consume(self.conn, FakeRun(self.features()))
        self.assertIn("none", stats["developed land"])
        self.assertEqual(self.conn.execute("select material, developed from roads.osm_paving where osm_id = %s",
                                           (self.BASE + 3,)).fetchone(), ("unknown", None))

    def test_the_tables_refuse_what_the_partition_never_gives_them(self):
        alley = {**way(6, highway="service", service="alley"), "osm_id": self.BASE + 6}
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            pv.consume(self.conn, FakeRun([alley]))

    @unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool")
    def test_the_fixture_through_the_loader(self):
        with tempfile.TemporaryDirectory() as d:
            cut, _, _ = osm_extract.make_cut(FIXTURE, "e" * 32, "osm_paving.osm", os.path.join(d, "cut"))
            run = osm_extract.Run(consumer(), FIXTURE, "osm_paving.osm", "e" * 32, cut, d, None, T0)
            with contextlib.redirect_stdout(io.StringIO()):
                stats = pv.consume(self.conn, run)
        ways = {r[0]: r[1:] for r in self.conn.execute(
            """select osm_id, kind, material, material_source, marked, marked_from, area, width_est_m
               from roads.osm_paving where active and osm_id < 1000""").fetchall()}
        self.assertEqual(sorted(ways), [601, 602, 603, 604, 605, 608, 609, 611, 612, 613, 614, 615, 616, 617, 618])
        self.assertEqual(ways[601][:3], ("driveway", "concrete", "default"))
        self.assertEqual(ways[602][:3] + ways[602][-1:], ("parking_aisle", "asphalt", "surface", 4.5))
        self.assertEqual(ways[604][:3], ("service", "unknown", None))
        self.assertEqual(ways[605][-1], 6.0)
        self.assertEqual(ways[608][:3], ("service", "gravel", "surface"))
        self.assertTrue(ways[609][5])                                       # drawn as an area
        self.assertEqual(ways[612][3:5], (True, "way"))
        self.assertEqual(ways[613][3:5], (False, "node"))
        self.assertEqual(ways[614][3:5], (None, None))
        self.assertEqual(ways[616][3:5], (False, "node"))
        lots = {(r[0], r[1]): r[2:] for r in self.conn.execute(
            """select osm_type, osm_id, kind, material, material_source, ST_YMin(geom) < 43.0, ST_NumInteriorRings(
                 ST_GeometryN(geom, 1)) from roads.osm_parking where active and osm_id < 1000""").fetchall()}
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
            "select osm_id, kind, marked, signals, kerb, railway, ways from roads.osm_walk_node where active and osm_id < 10000"
        ).fetchall()}
        self.assertEqual(sorted(nodes), [6119, 6122, 6132, 6142, 6162, 6902, 6903, 6904, 6906])
        self.assertEqual(nodes[6119], ("kerb", None, False, "lowered", None, [611]))
        self.assertEqual(nodes[6122][:2] + nodes[6122][-1:], ("crossing", True, [612]))
        self.assertEqual(nodes[6142][1:3], (None, True))
        self.assertEqual(nodes[6903][1:2] + nodes[6903][4:5], (None, "crossing"))   # a rail crossing: never marked
        self.assertEqual(nodes[6904][:2] + nodes[6904][3:4], ("crossing", True, "flush"))
        self.assertEqual(nodes[6906][1], True)
        self.assertEqual(stats["objects"], len(ways) + len(lots) + len(nodes))
        self.assertGreater(run.counts["dropped: the partition gives it to osm_street"], 0)
        self.assertGreater(run.counts["dropped: the partition gives it to osm_paths"], 0)


if __name__ == "__main__":
    unittest.main()
