"""Mask v0's rules (maskrules.py): what covers the ground, of what kind and how wide. Standard library only.

The partition test checks the rules against S1's (ingest/osm_extract.py owner()), over a grid of tag sets and over S1's
own synthetic fixture: every way the roads plugin's consumers own (osm_valley, osm_street, osm_paving) covers the
ground, and a path or track (osm_paths) does only when it's tagged paved.
"""

import importlib.util
import itertools
import os
import sys
import types
import unittest
import xml.etree.ElementTree as ET

from basemap.ground import fgb, maskrules as MR


def partition():
    """ingest.osm_extract, imported where psycopg isn't (the worker image, a bare python3): its db module needs
    psycopg only to connect, which the partition never does."""
    stub = "psycopg" not in sys.modules and importlib.util.find_spec("psycopg") is None
    if stub:
        sys.modules["psycopg"] = types.ModuleType("psycopg")
    try:
        from ingest import osm_extract
    finally:
        if stub:
            del sys.modules["psycopg"]
    return osm_extract


OX = partition()
FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                       "ingest", "tests", "fixtures", "osm_landscape.osm")


class TagsTest(unittest.TestCase):
    def test_surface_class(self):
        self.assertEqual(MR.surface_class({"surface": "asphalt"}), "paved")
        self.assertEqual(MR.surface_class({"surface": "Concrete"}), "paved")
        self.assertEqual(MR.surface_class({"surface": "gravel"}), "unpaved")
        self.assertEqual(MR.surface_class({}), "unknown")
        self.assertEqual(MR.surface_class({"surface": "paving_stones:30"}), "unknown")
        self.assertEqual(MR.surface_class({"highway": "track", "tracktype": "grade1"}), "paved")
        self.assertEqual(MR.surface_class({"highway": "track", "tracktype": "grade3"}), "unknown")
        self.assertFalse(MR.PAVED & MR.UNPAVED)

    def test_metres(self):
        for text, m in (("12", 12.0), ("12.5 m", 12.5), ("12m", 12.0), ("1,5", 1.5), ("7 metres", 7.0),
                        ("40 ft", 12.192), ("40'", 12.192), ("12'6\"", 3.81)):
            self.assertAlmostEqual(MR.metres(text), m, places=3, msg=text)
        for text in (None, "", "3;4", "wide", "2-3", "-4"):
            self.assertIsNone(MR.metres(text), text)

    def test_lanes(self):
        self.assertEqual(MR.lanes({"lanes": "2"}), 2)
        for v in ("2;3", "0", "13", "two", "", None):
            self.assertIsNone(MR.lanes({"lanes": v} if v is not None else {}), v)

    def test_oneway(self):
        self.assertTrue(MR.oneway({"highway": "primary", "oneway": "yes"}))
        self.assertTrue(MR.oneway({"highway": "primary", "oneway": "-1"}))
        self.assertTrue(MR.oneway({"highway": "secondary", "junction": "roundabout"}))
        self.assertTrue(MR.oneway({"highway": "motorway"}))                         # implied
        self.assertFalse(MR.oneway({"highway": "motorway", "oneway": "no"}))
        self.assertFalse(MR.oneway({"highway": "residential"}))

    def test_below_ground(self):
        self.assertTrue(MR.below_ground({"tunnel": "yes"}))
        self.assertTrue(MR.below_ground({"tunnel": "culvert"}))
        self.assertTrue(MR.below_ground({"location": "underground"}))
        self.assertTrue(MR.below_ground({"indoor": "yes"}))
        self.assertFalse(MR.below_ground({"tunnel": "building_passage"}))       # at ground level, under a roof
        self.assertFalse(MR.below_ground({"tunnel": "no", "layer": "-1"}))


class RoadTest(unittest.TestCase):
    def road(self, **tags):
        return MR.road(tags)

    def test_streets_and_roads_by_class(self):
        self.assertEqual(self.road(highway="residential"), ("street", "unknown", 10.4, "class"))
        self.assertEqual(self.road(highway="residential", oneway="yes"), ("street", "unknown", 7.0, "class"))
        self.assertEqual(self.road(highway="unclassified", surface="gravel"), ("street", "unpaved", 7.3, "class"))
        self.assertEqual(self.road(highway="primary"), ("major", "unknown", 18.0, "class"))
        self.assertEqual(self.road(highway="motorway"), ("major", "unknown", 12.0, "class"))          # one way
        self.assertEqual(self.road(highway="motorway", oneway="no")[2], 24.0)
        self.assertEqual(self.road(highway="primary_link")[2], 8.0)
        self.assertEqual(self.road(highway="primary_link", oneway="yes")[2], 6.0)

    def test_width_then_lanes_then_class(self):
        self.assertEqual(self.road(highway="primary", width="20"), ("major", "unknown", 20.0, "width"))
        self.assertEqual(self.road(highway="primary", lanes="4"), ("major", "unknown", 16.4, "lanes"))
        self.assertEqual(self.road(highway="primary", lanes="4", width="21 m")[2:], (21.0, "width"))
        self.assertEqual(self.road(highway="primary", width="200")[2:], (18.0, "class"))   # out of range
        self.assertEqual(self.road(highway="primary", lanes="2;3")[2:], (18.0, "class"))
        self.assertEqual(self.road(highway="cycleway", lanes="2")[2:], (2.5, "class"))     # lanes: roads only

    def test_service_ways(self):
        self.assertEqual(self.road(highway="service"), ("service", "unknown", 5.5, "class"))
        self.assertEqual(self.road(highway="service", service="alley")[2], 5.0)
        self.assertEqual(self.road(highway="service", service="driveway")[2], 4.0)
        self.assertEqual(self.road(highway="service", service="parking_aisle")[2], 6.5)
        self.assertEqual(self.road(highway="service", surface="dirt")[:2], ("service", "unpaved"))

    def test_walkways(self):
        self.assertEqual(self.road(highway="footway", footway="sidewalk"), ("walkway", "unknown", 1.5, "class"))
        self.assertEqual(self.road(highway="footway", footway="crossing")[2], 3.0)
        self.assertEqual(self.road(highway="path", footway="sidewalk", surface="gravel")[:2],
                         ("walkway", "unpaved"))                       # the roads plugin draws it all the same
        self.assertEqual(self.road(highway="pedestrian"), ("walkway", "unknown", 6.0, "class"))
        self.assertIsNone(self.road(highway="pedestrian", surface="dirt"))

    def test_paths_count_only_when_paved(self):
        self.assertIsNone(self.road(highway="footway"))
        self.assertIsNone(self.road(highway="path"))
        self.assertIsNone(self.road(highway="path", surface="dirt"))
        self.assertEqual(self.road(highway="footway", surface="concrete"), ("path", "paved", 2.0, "class"))
        self.assertEqual(self.road(highway="path", surface="asphalt", width="3"), ("path", "paved", 3.0, "width"))
        self.assertEqual(self.road(highway="cycleway"), ("path", "unknown", 2.5, "class"))
        self.assertIsNone(self.road(highway="cycleway", surface="gravel"))
        self.assertEqual(self.road(highway="steps")[0], "path")
        self.assertIsNone(self.road(highway="track"))
        self.assertIsNone(self.road(highway="track", surface="gravel"))
        self.assertEqual(self.road(highway="track", tracktype="grade1"), ("track", "paved", 3.5, "class"))
        self.assertEqual(self.road(highway="bridleway", surface="asphalt")[0], "path")

    def test_what_never_counts(self):
        for tags in ({"highway": "primary", "tunnel": "yes"}, {"highway": "service", "location": "underground"},
                     {"highway": "pedestrian", "area": "yes"}, {"highway": "proposed"},
                     {"highway": "construction", "construction": "residential"}, {"highway": "corridor"},
                     {"highway": "raceway"}, {"highway": "platform"}, {"highway": "elevator"},
                     {"highway": "bus_stop"}, {"railway": "rail"}, {}):
            self.assertIsNone(MR.road(tags), tags)
        self.assertIsNotNone(MR.road({"highway": "service", "tunnel": "building_passage"}))

    def test_bridge(self):
        self.assertTrue(MR.bridge({"bridge": "yes"}))
        self.assertTrue(MR.bridge({"bridge": "viaduct"}))
        self.assertFalse(MR.bridge({"bridge": "no"}))
        self.assertFalse(MR.bridge({}))

    def test_every_class_has_a_width(self):
        for hw, (two, one) in MR.CLASS_WIDTH.items():
            self.assertTrue(0 < one <= two <= 30, hw)
        for v in list(MR.SERVICE_WIDTH.values()) + list(MR.FOOTWAY_WIDTH.values()):
            self.assertTrue(1 <= v <= 10)


class AreasTest(unittest.TestCase):
    def test_paving(self):
        self.assertEqual(MR.paving_area({"amenity": "parking"}), ("parking", "unknown"))
        self.assertEqual(MR.paving_area({"amenity": "parking", "surface": "gravel"}), ("parking", "unpaved"))
        self.assertEqual(MR.paving_area({"amenity": "parking", "parking": "surface"}), ("parking", "unknown"))
        for parking in ("underground", "multi-storey", "rooftop", "carports"):
            self.assertIsNone(MR.paving_area({"amenity": "parking", "parking": parking}), parking)
        self.assertIsNone(MR.paving_area({"amenity": "parking", "building": "yes"}))
        self.assertIsNone(MR.paving_area({"amenity": "parking_space"}))
        self.assertEqual(MR.paving_area({"highway": "pedestrian", "area": "yes"}), ("highway_area", "unknown"))
        self.assertEqual(MR.paving_area({"area:highway": "service"}), ("highway_area", "unknown"))
        self.assertIsNone(MR.paving_area({"highway": "pedestrian"}))                     # a closed line
        # A multipolygon relation is an area by definition, and seldom says area=yes: a plaza (seven downtown
        # on Oct 11, Cecil D. Andrus Park Plaza among them).
        self.assertEqual(MR.paving_area({"highway": "pedestrian"}, relation=True), ("highway_area", "unknown"))
        self.assertEqual(MR.paving_area({"highway": "pedestrian", "type": "multipolygon", "surface": "paving_stones"}),
                         ("highway_area", "paved"))
        self.assertIsNone(MR.paving_area({"highway": "pedestrian", "surface": "grass"}, relation=True))
        self.assertIsNone(MR.paving_area({"highway": "primary"}, relation=True))         # not a highway area
        self.assertIsNone(MR.paving_area({"highway": "pedestrian", "area": "no"}, relation=True))
        self.assertIsNone(MR.paving_area({"highway": "footway", "area": "yes", "surface": "dirt"}))
        self.assertIsNone(MR.paving_area({"landuse": "retail"}))

    def test_water(self):
        self.assertEqual(MR.water_area({"natural": "water"}), ("lake", False))
        self.assertEqual(MR.water_area({"natural": "water", "water": "river"}), ("river", False))
        self.assertEqual(MR.water_area({"natural": "water", "water": "canal"}), ("canal", False))
        self.assertEqual(MR.water_area({"natural": "water", "water": "pond", "intermittent": "yes"}), ("lake", True))
        self.assertEqual(MR.water_area({"natural": "water", "seasonal": "yes"}), ("lake", True))
        self.assertEqual(MR.water_area({"natural": "water", "seasonal": "no"}), ("lake", False))
        self.assertEqual(MR.water_area({"waterway": "riverbank"}), ("river", False))
        self.assertEqual(MR.water_area({"landuse": "reservoir"}), ("reservoir", False))
        self.assertEqual(MR.water_area({"landuse": "basin"}), ("basin", False))
        self.assertEqual(MR.water_area({"landuse": "basin", "basin": "detention"}), ("basin", True))
        self.assertEqual(MR.water_area({"landuse": "basin", "basin": "infiltration"}), ("basin", True))
        self.assertEqual(MR.water_area({"leisure": "swimming_pool"}), ("pool", False))
        for tags in ({"leisure": "swimming_pool", "indoor": "yes"}, {"leisure": "swimming_pool", "location": "indoor"},
                     {"leisure": "swimming_pool", "building": "yes"}, {"leisure": "swimming_pool", "covered": "yes"},
                     {"natural": "wetland"}, {"natural": "wetland", "wetland": "marsh"}, {"landuse": "grass"}):
            self.assertIsNone(MR.water_area(tags), tags)

    def test_sampling_only_areas(self):
        self.assertEqual(MR.other_area({"aeroway": "apron"}), ("aeroway", "apron"))
        self.assertEqual(MR.other_area({"aeroway": "runway", "area": "yes"}), ("aeroway", "runway"))
        self.assertIsNone(MR.other_area({"aeroway": "aerodrome"}))                       # the whole airport
        self.assertIsNone(MR.other_area({"aeroway": "hangar"}))
        self.assertEqual(MR.other_area({"landuse": "railway"}), ("rail", "rail_yard"))
        self.assertIsNone(MR.other_area({"landuse": "industrial"}))


class LinesTest(unittest.TestCase):
    def test_waterways(self):
        self.assertEqual(MR.waterway({"waterway": "canal"}), ("canal", False, 6.0))
        self.assertEqual(MR.waterway({"waterway": "canal", "width": "12"}), ("canal", False, 12.0))
        self.assertEqual(MR.waterway({"waterway": "river"}), ("river", False, 15.0))
        self.assertEqual(MR.waterway({"waterway": "stream", "intermittent": "yes"}), ("stream", True, 2.5))
        self.assertEqual(MR.waterway({"waterway": "drain"}), ("ditch", False, 3.0))
        for tags in ({"waterway": "canal", "tunnel": "culvert"}, {"waterway": "ditch", "covered": "yes"},
                     {"waterway": "canal", "location": "underground"}, {"waterway": "dam"},
                     {"waterway": "riverbank"}, {"waterway": "weir"}, {"highway": "residential"}):
            self.assertIsNone(MR.waterway(tags), tags)

    def test_rail_runway_and_taxiway_lines(self):
        # The owner's answer 4 (Oct 22): lines, sampled around only. Widths are estimates until calibration.
        self.assertEqual(MR.other_line({"railway": "rail"}), ("rail", "rail", 5.0))
        self.assertEqual(MR.other_line({"railway": "light_rail", "service": "siding"}), ("rail", "light_rail", 5.0))
        self.assertEqual(MR.other_line({"aeroway": "runway"}), ("aeroway", "runway", 45.0))
        self.assertEqual(MR.other_line({"aeroway": "taxiway"}), ("aeroway", "taxiway", 23.0))
        self.assertEqual(MR.other_line({"aeroway": "runway", "width": "30"}), ("aeroway", "runway", 30.0))
        self.assertEqual(MR.other_line({"aeroway": "taxiway", "width": "900"}), ("aeroway", "taxiway", 23.0))
        for tags in ({"railway": "tram"}, {"railway": "abandoned"}, {"railway": "rail", "tunnel": "yes"},
                     {"railway": "rail", "location": "underground"}, {"aeroway": "runway", "area": "yes"},
                     {"aeroway": "apron"}, {"aeroway": "taxilane"}, {"highway": "residential"}, {}):
            self.assertIsNone(MR.other_line(tags), tags)
        for tags in ({"railway": "rail"}, {"aeroway": "runway"}, {"aeroway": "taxiway"}):
            self.assertIsNone(MR.road(tags), tags)
            self.assertIsNone(MR.waterway(tags), tags)


class NhdTest(unittest.TestCase):
    def test_waterbodies(self):
        self.assertEqual(MR.nhd_waterbody({"ftype_name": "Lake/Pond", "hydrographiccategory": "Perennial"}),
                         ("lake", False))
        self.assertEqual(MR.nhd_waterbody({"ftype_name": "Lake/Pond", "hydrographiccategory": "Intermittent"}),
                         ("lake", True))
        self.assertEqual(MR.nhd_waterbody({"ftype_name": "Lake/Pond", "hydrographiccategory": None}),
                         ("lake", False))
        self.assertEqual(MR.nhd_waterbody({"ftype_name": "Reservoir"}), ("reservoir", False))
        self.assertIsNone(MR.nhd_waterbody({"ftype_name": "Swamp/Marsh"}))
        self.assertIsNone(MR.nhd_waterbody({"ftype_name": "Playa"}))

    def test_areas(self):
        self.assertEqual(MR.nhd_area({"ftype_name": "Stream/River", "hydrographiccategory": "Perennial"}),
                         ("river", False))
        self.assertEqual(MR.nhd_area({"ftype_name": "Canal/Ditch"}), ("canal", False))
        for t in ("Inundation Area", "Wash", "Dam/Weir", "Spillway"):
            self.assertIsNone(MR.nhd_area({"ftype_name": t}), t)

    def test_flowlines(self):
        self.assertEqual(MR.nhd_flowline({"class": "stream_river", "hydrographiccategory": "Perennial",
                                          "streamorder": 1}), ("stream", False, 2.0, True))
        self.assertEqual(MR.nhd_flowline({"class": "stream_river", "streamorder": 3})[2], 4.0)
        self.assertEqual(MR.nhd_flowline({"class": "stream_river", "streamorder": 6})[2], 8.0)
        self.assertEqual(MR.nhd_flowline({"class": "stream_river", "streamorder": None})[2], 2.0)
        self.assertEqual(MR.nhd_flowline({"class": "stream_river", "hydrographiccategory": "Intermittent"})[1], True)
        # Canal and ditch lines: kept out of sampling, not painted (1:24,000-era, some piped or built over)
        self.assertEqual(MR.nhd_flowline({"class": "canal_ditch"}), ("canal", False, MR.NHD_CANAL_WIDTH, False))
        for c in ("pipeline", "connector", "artificial_path"):
            self.assertIsNone(MR.nhd_flowline({"class": c}), c)
        self.assertIsNone(MR.nhd_flowline({"class": "canal_ditch", "relationshiptosurface": "Underground"}))


class LayersTest(unittest.TestCase):
    def test_layers(self):
        self.assertEqual(list(MR.LAYERS), ["roofs", "roads", "paving", "water", "covered"])
        self.assertEqual(MR.PAINT_LAYERS, ("roofs", "roads", "paving", "water"))
        self.assertEqual(MR.SAMPLE_LAYER, "covered")
        for name, (use, about, fields) in MR.LAYERS.items():
            self.assertIn(use, ("paint", "sample"))
            self.assertTrue(about)
            self.assertEqual(fields[0], ("id", "int"), name)
            for fname, ftype in fields:
                self.assertIn(ftype, fgb.COLUMN_TYPES, (name, fname))

    def test_the_plan_s_buffers(self):
        # C6: paving and roads by class width plus 2 m, roofs plus 1 m, water plus 5 m.
        self.assertEqual((MR.SAMPLE_BUFFER["road"], MR.SAMPLE_BUFFER["paving"], MR.SAMPLE_BUFFER["roof"],
                          MR.SAMPLE_BUFFER["water"]), (2.0, 2.0, 1.0, 5.0))
        self.assertEqual(MR.CDL_DEVELOPED, {123: "developed_medium", 124: "developed_high"})
        self.assertEqual(MR.COVER_BLOCK_M % 10, 0)                    # blocks on the 10 m grid's edges


def tag_grid():
    """Highway tag sets across the partition's cases: every class, the footway and service subtypes, surfaces,
    lanes, areas and tunnels."""
    classes = sorted(set(MR.CLASS_WIDTH) | OX.ROADS | OX.PATH_CLASSES | OX.NOT_ROADS | {"corridor", "raceway"})
    for hw, footway, service, surface, lanes, area, tunnel in itertools.product(
            classes, (None, "sidewalk", "crossing", "access_aisle", "traffic_island", "link"),
            (None, "alley", "driveway"), (None, "asphalt", "gravel"), (None, "2"), (None, "yes"), (None, "yes")):
        tags = {"highway": hw}
        for k, v in (("footway", footway), ("service", service), ("surface", surface), ("lanes", lanes),
                     ("area", area), ("tunnel", tunnel)):
            if v is not None:
                tags[k] = v
        yield tags


def fixture_ways():
    """The tags of S1's synthetic fixture's highway ways."""
    for way in ET.parse(FIXTURE).getroot().iter("way"):
        tags = {t.get("k"): t.get("v") for t in way.iter("tag")}
        if "highway" in tags:
            yield tags


class PartitionTest(unittest.TestCase):
    """The rules against S1's partition (plan C10): the roads plugin's ways all cover the ground; paths and tracks
    only when paved; ways nobody owns never."""

    def check(self, tags):
        owner = OX.owner(tags)
        got = MR.road(tags)
        if tags.get("area") == "yes" or MR.below_ground(tags):
            self.assertIsNone(got, tags)                              # an area, or out of the photo's sight
            return owner
        if owner in ("osm_valley", "osm_street", "osm_paving") and not OX.named_exception(tags):
            if tags["highway"] in MR.CLASS_WIDTH:
                self.assertIsNotNone(got, (owner, tags))
            else:                                   # osm_valley keeps any class with lanes: a raceway, a corridor
                self.assertIsNone(got, (owner, tags))
        elif owner == "osm_paths" or OX.named_exception(tags):
            # Paved paths and tracks cover the ground and unpaved ones are trodden soil (a sidewalk aside, which
            # the roads plugin draws); untagged ones go by class (RoadTest).
            surf = MR.surface_class(tags)
            sidewalk = tags["highway"] in MR.WALK_CLASSES and tags.get("footway") in MR.SIDEWALKS
            if surf == "paved" or sidewalk:
                self.assertIsNotNone(got, tags)
            elif surf == "unpaved":
                self.assertIsNone(got, tags)
        else:
            self.assertIsNone(got, (owner, tags))
        return owner

    def test_a_grid_of_tag_sets(self):
        owners = {self.check(tags) for tags in tag_grid()}
        self.assertEqual(owners, {"osm_valley", "osm_street", "osm_paving", "osm_paths", None})

    def test_s1_s_fixture(self):
        owners = [self.check(tags) for tags in fixture_ways()]
        self.assertGreater(len(owners), 20)
        self.assertTrue({"osm_valley", "osm_street", "osm_paving", "osm_paths"} <= set(owners))

    def test_the_same_major_classes(self):
        self.assertEqual(MR.MAJOR | MR.MAJOR_LINKS, OX.MAJOR)
        self.assertEqual(MR.STREETS, OX.STREET_CLASSES)
        self.assertEqual(MR.SIDEWALKS, OX.PAVING_FOOTWAYS)
        self.assertEqual(MR.WALK_CLASSES, OX.WALKWAYS)


if __name__ == "__main__":
    unittest.main()
