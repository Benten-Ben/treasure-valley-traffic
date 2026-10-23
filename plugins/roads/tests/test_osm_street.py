"""Tests for roads' OpenStreetMap consumers in core's loader: osm_street
(plugins/roads/ingest/sources/osm_street.py) and osm_valley's place among them.

Offline: the manifest entries agree with the modules (osm_valley's tags are
its own filters, its keep rule is the partition's first rule), a way's row, and
that the source makes no requests and isn't scheduled. With osmium-tool, the
synthetic fixture (ingest/tests/fixtures/osm_landscape.osm: invented ids,
names and coordinates) goes through the loader's cut and this consumer's
features. Database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (with roads 0001), inside a transaction that is rolled
back.

Run: python3 -m unittest discover -s plugins -t .
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from ingest import manifest, osm_extract
from plugins.roads.ingest.sources import osm_street, osm_valley

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                       "ingest", "tests", "fixtures", "osm_landscape.osm")
HAVE_OSMIUM = shutil.which("osmium") is not None
DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def roads():
    return next(p for p in manifest.find() if p.name == "roads")


def consumer(name):
    return next(c for c in osm_extract.consumers() if c.id == f"roads.{name}")


class ManifestTest(unittest.TestCase):
    def test_osm_valley_s_entry_is_its_own_pipeline(self):
        c = consumer("osm_valley")
        self.assertEqual(list(c.tags), osm_valley.TAG_FILTERS)
        cmds, _ = osm_valley.osmium_commands("/c", "/w")
        self.assertEqual(cmds[2][cmds[2].index("--geometry-types") + 1], ",".join(c.geometry))
        self.assertEqual(set(c.tables), {"core.osm_way", "core.osm_lane", "core.osm_node", "core.segment_match"})
        self.assertIs(osm_valley.keep_way, osm_extract.keep_way)          # the partition's first rule is this rule
        self.assertEqual(osm_valley.BOX, osm_extract.BOX)
        self.assertTrue(osm_extract.own_gate(osm_valley))                  # last-loaded.json, as before

    def test_osm_street_s_entry(self):
        c = consumer("osm_street")
        self.assertEqual(c.tags, ("w/highway=residential,unclassified,unclassified_link,living_street,road,busway,service",))
        self.assertEqual((c.geometry, c.tables), (("linestring",), ("roads.osm_street",)))
        self.assertEqual(osm_street.TABLE, "roads.osm_street")
        self.assertIn("roads.osm_street", roads().manifest["tables"])
        # Every class the partition gives osm_street passes its filter (alleys through service).
        values = set(c.tags[0].split("=")[1].split(","))
        self.assertLessEqual(osm_extract.STREET_CLASSES | {"service"}, values)
        self.assertFalse(osm_extract.own_gate(osm_street))                 # its gate is ops.osm_consumer
        self.assertEqual(osm_street.SOURCE["license"], "ODbL")
        self.assertIsNone(osm_street.SOURCE["schedule"])

    def test_no_network_code_and_not_scheduled(self):
        for name in ("run", "download", "http", "urllib", "USER_AGENT"):
            self.assertFalse(hasattr(osm_street, name), name)
        with open(osm_street.__file__, encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("import urllib", source)
        from ingest.sources import SOURCES, STREAMS
        self.assertNotIn("osm_street", SOURCES)
        self.assertNotIn("osm_street", STREAMS)


class RowTest(unittest.TestCase):
    def feature(self, osm_id, **tags):
        return {"type": "w", "osm_id": osm_id, "geometry": "linestring", "tags": tags, "osm_version": 2,
                "osm_timestamp": T0, "geom": {"type": "LineString", "coordinates": [[-116.3, 43.6], [-116.3, 43.601]]}}

    def test_columns(self):
        row = osm_street.street_row(self.feature(227, highway="residential", name="  Bridge   Lane ", bridge="yes",
                                                 layer="1", width="8 m", oneway="-1", surface="concrete",
                                                 access="private", maxspeed="25 mph"))
        values = dict(zip([c for c, _ in osm_street.COLUMNS], row))
        self.assertEqual(values["name"], "Bridge Lane")
        self.assertEqual((values["highway"], values["service"], values["oneway"], values["width_m"], values["layer"],
                          values["bridge"], values["tunnel"], values["surface"], values["access"], values["maxspeed"]),
                         ("residential", None, "-1", 8.0, 1, True, False, "concrete", "private", "25 mph"))
        self.assertEqual(json.loads(values["tags"])["name"], "  Bridge   Lane ")        # tags as tagged
        self.assertEqual(json.loads(row[-1])["type"], "LineString")
        self.assertEqual(len(row), len(osm_street.COLUMNS) + 1)

    def test_an_unclassified_link_is_stored_as_unclassified(self):
        row = osm_street.street_row(self.feature(11, highway="unclassified_link", name="Ramp"))
        values = dict(zip([c for c, _ in osm_street.COLUMNS], row))
        self.assertEqual((values["highway"], values["service"]), ("unclassified", None))
        self.assertEqual(json.loads(values["tags"])["highway"], "unclassified_link")        # the raw value is kept
        plain = osm_street.street_row(self.feature(12, highway="unclassified"))
        self.assertEqual(plain[1], "unclassified")

    def test_alleys_and_tunnels(self):
        alley = dict(zip([c for c, _ in osm_street.COLUMNS],
                         osm_street.street_row(self.feature(208, highway="service", service="alley"))))
        self.assertEqual((alley["highway"], alley["service"]), ("service", "alley"))
        culvert = dict(zip([c for c, _ in osm_street.COLUMNS],
                           osm_street.street_row(self.feature(228, highway="unclassified", tunnel="culvert", layer="-1"))))
        self.assertEqual((culvert["tunnel"], culvert["layer"], culvert["oneway"]), (True, -1, "no"))
        roundabout = osm_street.street_row(self.feature(9, highway="residential", junction="roundabout"))
        self.assertEqual(roundabout[5], "yes")


class FakeRun:
    def __init__(self, features, seen_at=T0, allow_shrink=False):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, allow_shrink

    def features(self):
        return iter(self._features)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with roads 0001)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""
    BASE = 9_300_000_000

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('roads.osm_street') is not null").fetchone()[0]:
                raise unittest.SkipTest("roads.osm_street is missing: apply roads 0001")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        self.conn.execute("update roads.osm_street set active = false where active")          # rolled back

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def feature(self, n, x, **tags):
        return {"type": "w", "osm_id": self.BASE + n, "geometry": "linestring", "tags": tags, "osm_version": 1,
                "osm_timestamp": T0, "geom": {"type": "LineString", "coordinates": [[x, 43.6], [x, 43.601]]}}

    def test_consume(self):
        features = [self.feature(1, -116.30, highway="residential", name="Quiet Street"),
                    self.feature(2, -116.29, highway="service", service="alley"),
                    {**self.feature(3, -116.28, highway="road"), "geometry": "polygon"}]          # not a line: left out
        stats = osm_street.consume(self.conn, FakeRun(features))
        self.assertEqual((stats["objects"], stats["new"], stats["alleys"]), (2, 2, 1))
        rows = self.conn.execute("""select osm_id - %s, highway, service, name, active, first_seen
                                    from roads.osm_street where osm_id > %s order by 1""", (self.BASE, self.BASE)).fetchall()
        self.assertEqual(rows, [(1, "residential", None, "Quiet Street", True, T0), (2, "service", "alley", None, True, T0)])
        later = T0.replace(hour=13)
        stats = osm_street.consume(self.conn, FakeRun(features[:1], later))
        self.assertEqual((stats["unchanged"], stats["retired"]), (1, 1))
        self.assertEqual(self.conn.execute("select active from roads.osm_street where osm_id = %s",
                                           (self.BASE + 2,)).fetchone()[0], False)

    def test_an_unclassified_link_is_stored(self):
        osm_street.consume(self.conn, FakeRun([self.feature(5, -116.31, highway="unclassified_link")]))
        self.assertEqual(self.conn.execute("select highway, tags->>'highway' from roads.osm_street where osm_id = %s",
                                           (self.BASE + 5,)).fetchone(), ("unclassified", "unclassified_link"))

    def test_the_table_refuses_what_the_partition_never_gives_it(self):
        with self.assertRaises(self.psycopg.errors.CheckViolation):
            osm_street.consume(self.conn, FakeRun([self.feature(4, -116.3, highway="service", service="driveway")]))

    @unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool")
    def test_the_fixture_through_the_loader(self):
        with tempfile.TemporaryDirectory() as d:
            cut, _, _ = osm_extract.make_cut(FIXTURE, "f" * 32, "osm_landscape.osm", os.path.join(d, "cut"))
            run = osm_extract.Run(consumer("osm_street"), FIXTURE, "osm_landscape.osm", "f" * 32, cut, d, None, T0)
            with contextlib.redirect_stdout(io.StringIO()):
                stats = osm_street.consume(self.conn, run)
        self.assertEqual((stats["objects"], stats["alleys"]), (9, 1))
        got = dict(self.conn.execute("select osm_id, highway from roads.osm_street where active and osm_id < 1000").fetchall())
        self.assertEqual(sorted(got), [202, 204, 205, 206, 207, 208, 224, 227, 228])
        self.assertEqual(self.conn.execute("select name, bridge, width_m from roads.osm_street where osm_id = 227").fetchone(),
                         ("Bridge Lane", True, 8.0))


if __name__ == "__main__":
    unittest.main()
