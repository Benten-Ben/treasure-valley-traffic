"""Tests for trails' OpenStreetMap consumer, osm_paths (plugins/trails/ingest/sources/osm_paths.py),
and the access, surface and width rules (plan C18).

Offline: the manifest entry, the rules case by case, a way's, an area's and a
route's rows, how the loader's features are sorted, and that the source makes
no requests and isn't scheduled. Synthetic ways only (invented ids, names and
coordinates). With osmium-tool (the ingest image), the synthetic fixture
(ingest/tests/fixtures/osm_landscape.osm) goes through the loader's cut and
this consumer. Database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (with trails 0001), inside a transaction that is rolled
back: the load, the table's guards, the rules' SQL twins agreeing with these,
the named exception's view and the Trails layer's view.

Run: python3 -m unittest discover -s plugins -t .
"""

import contextlib
import io
import itertools
import json
import os
import shutil
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone

from ingest import manifest, osm_extract
from plugins.trails.ingest.sources import osm_paths

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                       "ingest", "tests", "fixtures", "osm_landscape.osm")
HAVE_OSMIUM = shutil.which("osmium") is not None
DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
COLUMNS = [c for c, _ in osm_paths.PATH_COLUMNS]


def consumer():
    return next(c for c in osm_extract.consumers() if c.id == "trails.osm_paths")


def way(osm_id, coords=None, version=1, **tags):
    coords = coords or [[-116.2, 43.7], [-116.2, 43.701]]
    return {"type": "w", "osm_id": osm_id, "geometry": "linestring", "tags": tags, "osm_version": version,
            "osm_timestamp": T0, "geom": {"type": "LineString", "coordinates": coords}, "way_nodes": None}


def area(osm_id, kind="w", **tags):
    ring = [[-116.2, 43.7], [-116.199, 43.7], [-116.199, 43.7008], [-116.2, 43.7008], [-116.2, 43.7]]
    return {"type": kind, "osm_id": osm_id, "geometry": "polygon", "tags": tags, "osm_version": 1,
            "osm_timestamp": T0, "geom": {"type": "MultiPolygon", "coordinates": [[ring]]}, "way_nodes": None}


def relation(osm_id, members, **tags):
    return {"type": "r", "osm_id": osm_id, "geometry": "relation", "geom": None, "tags": {"type": "route", **tags},
            "osm_version": 3, "osm_timestamp": T0,
            "members": [{"type": t, "ref": ref, "role": role} for t, ref, role in members]}


def values(row):
    return dict(zip(COLUMNS, row))


class ManifestTest(unittest.TestCase):
    def test_the_consumer_s_entry(self):
        c = consumer()
        self.assertEqual(c.tags, ("w/highway=path,footway,cycleway,track,bridleway,steps,pedestrian",
                                  "a/highway=pedestrian,footway", "r/route=hiking,mtb,bicycle,foot,horse"))
        self.assertEqual(c.geometry, ("linestring", "polygon", "relation"))
        self.assertEqual(c.tables, ("trails.osm_path", "trails.osm_area", "trails.osm_route"))
        self.assertEqual(c.source["republish"], "yes")
        self.assertFalse(osm_extract.own_gate(osm_paths))                   # its gate is ops.osm_consumer
        self.assertEqual((osm_paths.SOURCE["license"], osm_paths.SOURCE["credit"]), ("ODbL", osm_extract.CREDIT))
        self.assertIsNone(osm_paths.SOURCE["schedule"])

    def test_every_class_the_partition_gives_it_passes_its_filter(self):
        values_ = set(consumer().tags[0].split("=")[1].split(","))
        self.assertEqual(values_, osm_extract.PATH_CLASSES)
        self.assertEqual(set(osm_paths.PATH_KINDS), osm_extract.PATH_CLASSES)
        self.assertEqual(set(consumer().tags[2].split("=")[1].split(",")), set(osm_paths.ROUTES))
        self.assertIn("osm_paths", osm_extract.OWNERS)

    def test_no_network_code_and_not_scheduled(self):
        for name in ("run", "download", "http", "urllib", "USER_AGENT"):
            self.assertFalse(hasattr(osm_paths, name), name)
        with open(osm_paths.__file__, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        from ingest.sources import SOURCES, STREAMS
        self.assertNotIn("osm_paths", SOURCES)
        self.assertNotIn("osm_paths", STREAMS)


class RuleTest(unittest.TestCase):
    def test_surface_classes(self):
        for value, want in [("asphalt", "paved"), ("concrete", "paved"), ("concrete:plates", "paved"),
                            ("paving_stones", "paved"), ("wood", "paved"), (" Asphalt ", "paved"),
                            ("gravel", "gravel"), ("fine_gravel", "gravel"), ("compacted", "gravel"),
                            ("dirt", "dirt"), ("ground", "dirt"), ("unpaved", "dirt"), ("grass", "dirt"),
                            ("rock", "dirt"), ("asphalt;gravel", "unknown"), ("woodchips", "unknown"),
                            ("", "unknown"), (None, None)]:
            with self.subTest(value):
                self.assertEqual(osm_paths.surface_class(value), want)

    def test_surface_with_its_source_and_defaults(self):
        self.assertEqual(osm_paths.surface("path", {"surface": "dirt"}), ("dirt", "osm"))
        self.assertEqual(osm_paths.surface("cycleway", {"surface": "gravel"}), ("gravel", "osm"))   # the tag wins
        self.assertEqual(osm_paths.surface("cycleway", {}), ("paved", "default"))
        self.assertEqual(osm_paths.surface("track", {}), ("dirt", "default"))
        self.assertEqual(osm_paths.surface("path", {}), ("unknown", "none"))
        self.assertEqual(osm_paths.surface("footway", {}), ("unknown", "none"))
        self.assertEqual(osm_paths.surface("track", {"surface": "woodchips"}), ("unknown", "osm"))   # tagged, unplaced

    def test_access_rule(self):
        """Plan C18: private or no access isn't a trail, unless a trail mode is opened."""
        for tags, closed in [({}, False), ({"access": "private"}, True), ({"access": "no"}, True),
                             ({"access": "Private "}, True), ({"access": "yes"}, False),
                             ({"access": "permissive"}, False), ({"access": "customers"}, False),
                             ({"access": "agricultural"}, False),
                             ({"access": "no", "foot": "designated", "bicycle": "designated"}, False),
                             ({"access": "private", "bicycle": "yes"}, False),
                             ({"access": "private", "horse": "permissive"}, False),
                             ({"access": "no", "foot": "official"}, False),
                             ({"access": "private", "foot": "private"}, True),
                             ({"access": "private", "foot": "destination"}, True),       # not a way through
                             ({"access": "private", "motor_vehicle": "yes"}, True),      # not a trail mode
                             ({"foot": "private"}, False)]:                              # only the access tag
            with self.subTest(tags):
                self.assertEqual(osm_paths.no_public_access(tags), closed)

    def test_informal(self):
        self.assertTrue(osm_paths.informal({"informal": "yes"}))
        self.assertTrue(osm_paths.informal({"informal": " YES"}))
        self.assertFalse(osm_paths.informal({"informal": "no"}))
        self.assertFalse(osm_paths.informal({}))

    def test_width_estimates(self):
        cases = [("path", "dirt", 0.8), ("path", "unknown", 0.8), ("path", "gravel", 1.5), ("path", "paved", 3.0),
                 ("bridleway", "dirt", 1.5), ("footway", "paved", 1.8), ("footway", "unknown", 1.8),
                 ("cycleway", "paved", 3.0), ("track", "dirt", 3.0), ("steps", "paved", 1.5),
                 ("pedestrian", "paved", 4.0)]
        for kind, cls, want in cases:
            with self.subTest((kind, cls)):
                self.assertEqual(osm_paths.width_estimate(kind, cls), want)
        self.assertEqual({k for k, _, _ in cases}, set(osm_paths.PATH_KINDS))

    def test_widths_as_tagged(self):
        for value, want in [("2", 2.0), ("1.5 m", 1.5), ("4 ft", 1.22), ("4'", 1.22), ("4'6\"", 1.37),
                            ("narrow", None), ("1,5", None), ("0", None), (None, None), ("2;3", None)]:
            with self.subTest(value):
                self.assertEqual(osm_paths.parse_width(value), want)


class RowTest(unittest.TestCase):
    def test_a_path_s_columns(self):
        row = osm_paths.path_row(way(5, name="  Fixture   Ridge ", surface="ground", width="1 m", access="no",
                                     foot="designated", informal="yes", bridge="boardwalk", layer="1",
                                     **{"mtb:scale": "2", "sac_scale": "hiking",
                                        "motor_vehicle:conditional": "no @ (Nov-Apr)", "highway": "path"}))
        v = values(row)
        self.assertEqual((v["kind"], v["name"], v["surface_tag"], v["surface"], v["surface_from"], v["width_m"],
                          v["width_est_m"], v["access"], v["foot"], v["no_access"], v["informal"], v["mtb_scale"],
                          v["sac_scale"], v["bridge"], v["tunnel"], v["layer"]),
                         ("path", "Fixture Ridge", "ground", "dirt", "osm", 1.0, 0.8, "no", "designated", False, True,
                          "2", "hiking", True, False, 1))
        self.assertEqual(json.loads(v["conditional"]), {"motor_vehicle:conditional": "no @ (Nov-Apr)"})
        self.assertEqual(json.loads(v["tags"])["name"], "  Fixture   Ridge ")          # tags as tagged
        self.assertEqual(json.loads(row[-1])["type"], "LineString")
        self.assertEqual(len(row), len(COLUMNS) + 1)

    def test_defaults_and_a_closed_track(self):
        v = values(osm_paths.path_row(way(6, highway="track", access="private", tracktype="grade4")))
        self.assertEqual((v["surface"], v["surface_from"], v["width_est_m"], v["no_access"], v["tracktype"],
                          v["conditional"], v["width_m"]), ("dirt", "default", 3.0, True, "grade4", None, None))
        v = values(osm_paths.path_row(way(7, highway="cycleway")))
        self.assertEqual((v["surface"], v["surface_from"], v["width_est_m"]), ("paved", "default", 3.0))

    def test_an_area_and_a_route(self):
        row = osm_paths.area_row(area(9, highway="pedestrian", area="yes", name="Fixture Plaza", surface="paving_stones"))
        self.assertEqual(row[:8], ("w", 9, "pedestrian", "Fixture Plaza", "paving_stones", "paved", None, False))
        self.assertEqual(json.loads(row[-1])["type"], "MultiPolygon")
        route = osm_paths.route_row(relation(501, [("w", 215, ""), ("n", 7, "guidepost"), ("w", 214, "forward"),
                                                   ("r", 9, "")], route="hiking", name="Fixture Loop",
                                             network="lwn"))
        r = dict(zip([c for c, _ in osm_paths.ROUTE_COLUMNS], route))
        self.assertEqual((r["route"], r["name"], r["network"], r["way_ids"]), ("hiking", "Fixture Loop", "lwn", [215, 214]))
        self.assertEqual([m["ref"] for m in json.loads(r["members"])], [215, 7, 214, 9])      # every member, in order
        self.assertEqual(len(route), len(osm_paths.ROUTE_COLUMNS))                             # no geometry


class SortTest(unittest.TestCase):
    def test_lines_areas_and_routes(self):
        ring = [[-116.2, 43.7], [-116.199, 43.7], [-116.199, 43.701], [-116.2, 43.7]]
        features = [
            way(1, highway="path"),
            way(2, ring, highway="footway", name="Park Loop"),                     # a loop: a line
            area(2, highway="footway"),                                             # ... which osmium also makes an area
            way(3, ring, highway="pedestrian", area="yes"),                        # an area drawn as a line: not a line
            area(3, highway="pedestrian", area="yes"),                              # ... it's this area
            area(4, "r", highway="pedestrian", type="multipolygon"),                # a multipolygon is an area
            way(5, highway="residential"),                                          # not ours (the filter wouldn't pass it)
            relation(501, [("w", 1, "")], route="hiking"),
            relation(502, [("w", 1, "")], route="bus"),                             # not a trail route
        ]
        counts = Counter()
        paths, areas, routes = osm_paths.sort_features(features, counts)
        self.assertEqual([r[0] for r in paths], [1, 2])
        self.assertEqual([(r[0], r[1]) for r in areas], [("w", 3), ("r", 4)])
        self.assertEqual([r[0] for r in routes], [501])
        self.assertEqual(counts, Counter({"left out: a closed way that's a loop, not an area": 1,
                                          "left out: an area drawn as a closed line": 1,
                                          "left out: linestring highway=residential": 1}))


class FakeRun:
    def __init__(self, features, seen_at=T0, allow_shrink=False):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, allow_shrink
        self.extract_name, self.md5 = "fixture-20261011-ffffffff.osm.pbf", "f" * 32

    def features(self):
        return iter(self._features)


def tag_grid():
    """Tag sets covering every branch of the rules, for the SQL twins."""
    surfaces = [None, "asphalt", "concrete:lanes", "fine_gravel", "earth", "woodchips", " Dirt"]
    accesses = [{}, {"access": "private"}, {"access": "no", "foot": "yes"}, {"access": "no", "bicycle": "Designated"},
                {"access": "private", "horse": "official"}, {"access": "permissive"}, {"access": "no", "foot": "no"}]
    for kind, surface, access, informal in itertools.product(osm_paths.PATH_KINDS, surfaces, accesses,
                                                             (None, "yes", "no")):
        tags = {"highway": kind, **access}
        if surface is not None:
            tags["surface"] = surface
        if informal is not None:
            tags["informal"] = informal
        yield tags


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with trails 0001)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""
    BASE = 9_400_000_000

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('trails.osm_path') is not null").fetchone()[0]:
                raise unittest.SkipTest("trails.osm_path is missing: apply trails 0001")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        for table in ("trails.osm_path", "trails.osm_area", "trails.osm_route"):
            self.conn.execute(f"update {table} set active = false where active")          # rolled back

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def features(self):
        b = self.BASE
        return [way(b + 1, highway="path", name="Fixture Ridge", surface="dirt"),
                way(b + 2, [[-116.21, 43.7], [-116.21, 43.71]], highway="track", access="private"),
                way(b + 3, highway="cycleway"),
                way(b + 4, highway="path", informal="yes"),
                area(b + 5, highway="pedestrian", area="yes", name="Fixture Plaza"),
                relation(b + 6, [("w", b + 1, ""), ("w", b + 3, "forward")], route="bicycle", name="Fixture Ride")]

    def test_consume(self):
        stats = osm_paths.consume(self.conn, FakeRun(self.features()))
        self.assertEqual((stats["objects"], stats["paths"], stats["areas"], stats["routes"], stats["paths new"],
                          stats["no public access"], stats["informal"]), (6, 4, 1, 1, 4, 1, 1))
        rows = self.conn.execute(
            """select osm_id - %s, kind, surface, surface_from, no_access, informal, round(length_m)
               from trails.osm_path where osm_id > %s order by 1""", (self.BASE, self.BASE)).fetchall()
        self.assertEqual(rows, [(1, "path", "dirt", "osm", False, False, 111), (2, "track", "dirt", "default", True, False, 1111),
                                (3, "cycleway", "paved", "default", False, False, 111),
                                (4, "path", "unknown", "none", False, True, 111)])
        self.assertEqual(self.conn.execute(
            "select osm_type, name, round(area_m2 / 100) from trails.osm_area where osm_id = %s",
            (self.BASE + 5,)).fetchone(), ("w", "Fixture Plaza", 72))
        self.assertEqual(self.conn.execute("select way_ids, members->1->>'role' from trails.osm_route where osm_id = %s",
                                           (self.BASE + 6,)).fetchone(), ([self.BASE + 1, self.BASE + 3], "forward"))
        # The load marks trails-match and gives the Trails layer's tiles a new version.
        self.assertIn("trails-match", [r[0] for r in self.conn.execute(
            "select build from ops.build_pending where marked_by = 'osm_paths'").fetchall()])
        self.assertEqual(self.conn.execute(
            "select version, license, republish, features from core.layer_version_current where layer = 'trails.paths'"
        ).fetchone(), (stats["version"], "ODbL", "yes", 4))
        # Next extract: one way gone, a route edited.
        later = self.features()[:-1] + [relation(self.BASE + 6, [("w", self.BASE + 1, "")], route="bicycle",
                                                 name="Fixture Ride")]
        stats = osm_paths.consume(self.conn, FakeRun([f for f in later if f["osm_id"] != self.BASE + 4],
                                                     T0.replace(hour=13)))
        self.assertEqual((stats["paths retired"], stats["routes changed"]), (1, 1))
        self.assertFalse(self.conn.execute("select active from trails.osm_path where osm_id = %s",
                                           (self.BASE + 4,)).fetchone()[0])

    def test_the_table_refuses_what_the_partition_never_gives_it(self):
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            osm_paths.consume(self.conn, FakeRun([way(self.BASE + 9, highway="footway", footway="sidewalk")]))

    def test_the_sql_twins_agree_with_the_rules(self):
        """The named exception's view computes the rules in SQL (trails 0001); they must agree."""
        checked = 0
        for tags in tag_grid():
            kind = tags["highway"]
            cls, came_from = osm_paths.surface(kind, tags)
            want = (cls, came_from, osm_paths.no_public_access(tags), osm_paths.width_estimate(kind, cls),
                    osm_paths.informal(tags))
            got = self.conn.execute(
                """select coalesce(trails.surface_class(t->>'surface'), trails.surface_default(t->>'highway'), 'unknown'),
                          case when t ? 'surface' then 'osm' when trails.surface_default(t->>'highway') is not null
                               then 'default' else 'none' end,
                          trails.no_public_access(t),
                          trails.width_estimate(t->>'highway', coalesce(trails.surface_class(t->>'surface'),
                                                trails.surface_default(t->>'highway'), 'unknown')),
                          coalesce(lower(btrim(t->>'informal')) = 'yes', false)
                   from (select %s::jsonb as t) x""", (json.dumps(tags),)).fetchone()
            self.assertEqual((got[0], got[1], got[2], round(got[3], 2), got[4]), want, tags)
            checked += 1
        self.assertGreater(checked, 1000)

    def test_the_named_exception_s_view(self):
        b = self.BASE
        geom = json.dumps({"type": "LineString", "coordinates": [[-116.3, 43.65], [-116.3, 43.651]]})
        for osm_id, tags in ((b + 11, {"highway": "cycleway", "lanes": "1", "access": "no", "bicycle": "designated"}),
                             (b + 12, {"highway": "track", "lanes": "2", "access": "private"}),
                             (b + 13, {"highway": "footway", "footway": "sidewalk", "lanes": "1"}),   # osm_paving's kind
                             (b + 14, {"highway": "residential", "lanes": "2"})):                     # a road
            self.conn.execute(
                """insert into core.osm_way (osm_id, highway, tags, geom)
                   values (%s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))""",
                (osm_id, tags["highway"], json.dumps(tags), geom))
        rows = self.conn.execute(
            """select osm_id - %s, kind, surface, surface_from, no_access, width_est_m from trails.exception_way
               where osm_id > %s order by 1""", (b, b)).fetchall()
        self.assertEqual(rows, [(11, "cycleway", "paved", "default", False, 3.0),
                                (12, "track", "dirt", "default", True, 3.0)])
        drawn = dict(self.conn.execute("select osm_id - %s, drawn from trails.path where osm_id > %s", (b, b)).fetchall())
        self.assertEqual(drawn, {11: True, 12: False})

    def test_the_trails_layer_s_view(self):
        osm_paths.consume(self.conn, FakeRun(self.features()))
        rows = {r[0] - self.BASE: r[1:] for r in self.conn.execute(
            """select osm_id, drawn, not_drawn, informal, minzoom, surface, width_from, width_m, held_in
               from trails.path where osm_id > %s""", (self.BASE,)).fetchall()}
        self.assertEqual(rows[1], (True, None, False, 10, "dirt", "estimated", 0.8, "osm_path"))        # named
        self.assertEqual(rows[2], (False, "private, no public access", False, 13, "dirt", "estimated", 3.0, "osm_path"))
        self.assertEqual(rows[3][:4], (True, None, False, 10))                                           # cycleway
        self.assertEqual(rows[4][:4], (True, None, True, 16))                                            # informal

    @unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool (the ingest image)")
    def test_the_fixture_through_the_loader(self):
        with tempfile.TemporaryDirectory() as d:
            cut, _, _ = osm_extract.make_cut(FIXTURE, "f" * 32, "osm_landscape.osm", os.path.join(d, "cut"))
            run = osm_extract.Run(consumer(), FIXTURE, "osm_landscape.osm", "f" * 32, cut, d, None, T0)
            with contextlib.redirect_stdout(io.StringIO()):
                stats = osm_paths.consume(self.conn, run)
        self.assertEqual((stats["paths"], stats["areas"], stats["routes"]), (5, 1, 2))
        got = dict(self.conn.execute("select osm_id, kind from trails.osm_path where active and osm_id < 1000").fetchall())
        self.assertEqual(got, {214: "footway", 215: "path", 216: "track", 220: "steps", 221: "bridleway"})
        self.assertEqual(self.conn.execute("select osm_type, osm_id, name from trails.osm_area where active and osm_id < 1000")
                         .fetchall(), [("w", 219, "Fixture Plaza")])
        routes = dict(self.conn.execute("select osm_id, way_ids from trails.osm_route where active and osm_id < 1000")
                      .fetchall())
        self.assertEqual(routes, {501: [215, 214, 202], 503: [217, 224, 999999]})


if __name__ == "__main__":
    unittest.main()
