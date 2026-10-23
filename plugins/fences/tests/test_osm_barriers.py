"""Tests for the fences plugin's OpenStreetMap consumer, osm_barriers (plugins/fences/ingest/sources/osm_barriers.py).

Offline: the manifest entry, the rules case by case, a fence's and a gate's rows, how the loader's features are
sorted, and that the source makes no requests and isn't scheduled. Synthetic ways only (invented ids and
coordinates). With osmium-tool (the ingest image), the synthetic fixture (tests/fixtures/osm_barriers.osm) goes
through the loader's cut and this consumer. Database tests run only against a scratch database named by
TVT_TEST_DATABASE_URL (with fences 0001), inside a transaction that is rolled back.

Run: python3 -m unittest discover -s plugins/fences -t .
"""

import json
import os
import shutil
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timezone

from ingest import manifest, osm_extract
from plugins.fences.ingest.sources import osm_barriers

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "osm_barriers.osm")
HAVE_OSMIUM = shutil.which("osmium") is not None
DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")
T0 = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
FENCE_NAMES = [c for c, _ in osm_barriers.FENCE_COLUMNS]
GATE_NAMES = [c for c, _ in osm_barriers.GATE_COLUMNS]


def consumer():
    return next(c for c in osm_extract.consumers() if c.id == "fences.osm_barriers")


def way(osm_id, coords=None, version=1, **tags):
    coords = coords or [[-116.2, 43.7], [-116.199, 43.7]]
    return {"type": "w", "osm_id": osm_id, "geometry": "linestring", "tags": tags, "osm_version": version,
            "osm_timestamp": T0, "geom": {"type": "LineString", "coordinates": coords}, "way_nodes": None}


def node(osm_id, **tags):
    return {"type": "n", "osm_id": osm_id, "geometry": "point", "tags": tags, "osm_version": 1,
            "osm_timestamp": T0, "geom": {"type": "Point", "coordinates": [-116.2, 43.7]}, "way_nodes": None}


def fence(row):
    return dict(zip(FENCE_NAMES, row))


class ManifestTest(unittest.TestCase):
    def test_the_manifest_is_found_and_valid(self):
        self.assertIn("fences", [p.name for p in manifest.find()])

    def test_the_consumer_s_entry(self):
        c = consumer()
        self.assertEqual(c.tags, ("nw/barrier",))
        self.assertEqual(c.geometry, ("point", "linestring"))
        self.assertEqual(c.tables, ("fences.fence", "fences.gate"))
        self.assertEqual((c.source["license"], c.source["credit"], c.source["republish"], c.source["kind"]),
                         ("ODbL", "© OpenStreetMap contributors", "yes", "manual"))
        self.assertEqual((osm_barriers.SOURCE["license"], osm_barriers.SOURCE["credit"]),
                         ("ODbL", osm_extract.CREDIT))
        self.assertIsNone(osm_barriers.SOURCE["schedule"])
        self.assertFalse(osm_extract.own_gate(osm_barriers))                # its gate is ops.osm_consumer
        self.assertNotIn("fences.osm_barriers", osm_extract.OWNERS)

    def test_no_network_code_and_not_scheduled(self):
        for name in ("run", "download", "http", "urllib", "USER_AGENT"):
            self.assertFalse(hasattr(osm_barriers, name), name)
        with open(osm_barriers.__file__, encoding="utf-8") as f:
            self.assertNotIn("import urllib", f.read())
        from ingest.sources import SOURCES, STREAMS
        self.assertNotIn("osm_barriers", SOURCES)
        self.assertNotIn("osm_barriers", STREAMS)


class RuleTest(unittest.TestCase):
    def test_types(self):
        for kind in osm_barriers.NAMED_TYPES:
            self.assertEqual(osm_barriers.fence_type_of(kind), kind)
        for kind in osm_barriers.OTHER_LINES:
            self.assertEqual(osm_barriers.fence_type_of(kind), "other")
        for kind in ("kerb", "ditch", "gate", "bollard", None):
            self.assertIsNone(osm_barriers.fence_type_of(kind))

    def test_heights_as_tagged(self):
        h = osm_barriers.parse_height
        self.assertEqual([h("1.8"), h("1.8 m"), h("6 ft"), h("6'"), h("6'6\""), h(" 2 METRES")],
                         [1.8, 1.8, 1.83, 1.83, 1.98, 2.0])
        for bad in ("tall", "1,8", "0", "40", "1;2", "", None, "-1"):
            self.assertIsNone(h(bad), bad)

    def test_height_tagged_or_default(self):
        self.assertEqual(osm_barriers.height("fence", {"height": "2"}), (2.0, "tagged"))
        self.assertEqual(osm_barriers.height("fence", {"height": "tall"}), (1.5, "default"))
        self.assertEqual(osm_barriers.height("fence", {"fence_type": "barbed_wire"}), (1.2, "default"))
        self.assertEqual(osm_barriers.height("fence", {"fence_type": "Privacy"}), (1.8, "default"))
        self.assertEqual(osm_barriers.height("wall", {}), (1.8, "default"))
        self.assertEqual(osm_barriers.height("hedge", {"fence_type": "wood"}), (1.5, "default"))
        self.assertEqual(osm_barriers.height("retaining_wall", {"height": "1.2"}), (1.2, "tagged"))
        for t in ("fence", "wall", "retaining_wall", "guard_rail", "jersey_barrier", "hedge", "other"):
            self.assertGreater(osm_barriers.height(t, {})[0], 0)

    def test_looks(self):
        look = osm_barriers.look
        for t in ("wall", "retaining_wall", "jersey_barrier", "hedge"):
            self.assertEqual(look(t, {}), "solid", t)
        self.assertEqual(look("guard_rail", {}), "open")
        self.assertEqual(look("other", {}), "open")
        self.assertEqual(look("other", {"barrier": "city_wall"}), "solid")
        self.assertEqual(look("other", {"barrier": "cable_barrier"}), "open")
        self.assertEqual(look("fence", {}), "open")
        self.assertEqual(look("fence", {"fence_type": "chain_link"}), "open")
        self.assertEqual(look("fence", {"fence_type": "wood"}), "solid")
        self.assertEqual(look("fence", {"material": "Brick"}), "solid")
        self.assertEqual(look("fence", {"fence_type": "chain_link", "material": "metal"}), "open")


class RowTest(unittest.TestCase):
    def test_a_fence_row(self):
        row = osm_barriers.fence_row(way(7, barrier="fence", fence_type="wood", height="6 ft", material="wood",
                                         name="  Fixture   Fence "))
        got = fence(row[:-1])
        self.assertEqual((got["fence_id"], got["kind"], got["type"], got["look"], got["height_m"], got["height_source"]),
                         ("osm:w7", "fence", "fence", "solid", 1.83, "tagged"))
        self.assertEqual((got["material"], got["fence_type"], got["name"], got["osm_id"]),
                         ("wood", "wood", "Fixture Fence", 7))
        self.assertEqual(json.loads(row[-1])["type"], "LineString")
        self.assertEqual(json.loads(got["tags"])["fence_type"], "wood")

    def test_a_hedge_is_stored_as_a_hedge(self):
        row = osm_barriers.fence_row(way(8, barrier="hedge"))
        self.assertEqual((row[1], row[2], row[3]), ("hedge", "hedge", "solid"))

    def test_other_kinds_keep_the_tag_as_kind(self):
        row = osm_barriers.fence_row(way(9, barrier="cable_barrier"))
        self.assertEqual((row[1], row[2], row[3]), ("cable_barrier", "other", "open"))

    def test_gate_rows(self):
        n = osm_barriers.gate_row(node(5, barrier="gate", access="Private"))
        self.assertEqual(dict(zip(GATE_NAMES, n[:-1]))["gate_id"], "osm:n5")
        self.assertEqual((n[1], n[2], n[5], n[6]), ("gate", "Private", "n", 5))
        self.assertEqual(json.loads(n[-1]), {"type": "Point", "coordinates": [-116.2, 43.7]})
        w = osm_barriers.gate_row(way(6, [[-116.2, 43.7], [-116.1995, 43.7], [-116.199, 43.7]], barrier="lift_gate"))
        self.assertEqual((w[0], w[5]), ("osm:w6", "w"))
        self.assertEqual(json.loads(w[-1])["coordinates"], [-116.1995, 43.7])


class SortTest(unittest.TestCase):
    def test_fences_gates_and_what_is_left_out(self):
        counts = Counter()
        fences, gates = osm_barriers.sort_features(
            [way(1, barrier="fence"), way(2, barrier="hedge"), way(3, barrier="kerb"), way(4, barrier="ditch"),
             way(5, barrier="gate"), node(6, barrier="bollard"), node(7, barrier="cattle_grid"),
             node(8, barrier="fence"), node(9, barrier="wall"), node(10, barrier="kerb")], counts)
        self.assertEqual([r[0] for r in fences], ["osm:w1", "osm:w2"])
        self.assertEqual([r[0] for r in gates], ["osm:w5", "osm:n6", "osm:n7"])
        self.assertEqual(counts, {"left out: linestring barrier=kerb": 1, "left out: linestring barrier=ditch": 1,
                                  "left out: point barrier=fence": 1, "left out: point barrier=wall": 1,
                                  "left out: point barrier=kerb": 1})

    def test_every_kind_the_consumer_names_is_sorted_somewhere(self):
        self.assertFalse(set(osm_barriers.LINE_KINDS) & set(osm_barriers.GATE_KINDS))


@unittest.skipUnless(HAVE_OSMIUM, "needs osmium-tool (the ingest image)")
class PipelineTest(unittest.TestCase):
    """The synthetic fixture through the loader's cut and osmium export, as this consumer gets it."""

    def test_the_fixture_s_fences_and_gates(self):
        with tempfile.TemporaryDirectory() as d:
            cut, _, _ = osm_extract.make_cut(FIXTURE, "f" * 32, "osm_barriers.osm", os.path.join(d, "cut"))
            work = os.path.join(d, "work")
            os.makedirs(work)
            run = osm_extract.Run(consumer(), FIXTURE, "osm_barriers.osm", "f" * 32, cut, work, None, T0)
            counts = Counter()
            fences, gates = osm_barriers.sort_features(run.features(), counts)
        got = {r[0]: (r[2], r[3]) for r in fences}
        self.assertEqual(got, {"osm:w9301": ("hedge", "solid"),          # a closed hedge way comes as a line
                               "osm:w9302": ("fence", "solid"),
                               "osm:w9303": ("retaining_wall", "solid")})
        self.assertEqual({r[0]: r[1] for r in gates}, {"osm:n9201": "gate", "osm:n9202": "bollard"})
        self.assertEqual(counts["left out: linestring barrier=kerb"], 1)
        self.assertEqual(counts["left out: point barrier=fence"], 1)


class FakeRun:
    def __init__(self, features, seen_at=T0, allow_shrink=False):
        self._features, self.seen_at, self.allow_shrink = features, seen_at, allow_shrink
        self.extract_name, self.md5 = "fixture-20261011-ffffffff.osm.pbf", "f" * 32

    def features(self):
        return iter(self._features)


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a scratch database (with fences 0001)")
class DatabaseTest(unittest.TestCase):
    """Everything here runs in one transaction that is rolled back."""
    BASE = 9_500_000_000

    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        with psycopg.connect(DB_URL) as c:
            if not c.execute("select to_regclass('fences.fence') is not null").fetchone()[0]:
                raise unittest.SkipTest("fences.fence is missing: apply fences 0001")

    def setUp(self):
        self.conn = self.psycopg.connect(DB_URL)
        for table in ("fences.fence", "fences.gate"):
            self.conn.execute(f"update {table} set active = false where active")          # rolled back

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    def features(self):
        b = self.BASE
        return [way(b + 1, barrier="fence", fence_type="chain_link"),
                way(b + 2, [[-116.21, 43.7], [-116.21, 43.71]], barrier="wall", height="2"),
                way(b + 3, barrier="hedge"),
                way(b + 4, barrier="guard_rail"),
                node(b + 5, barrier="gate", access="private"),
                node(b + 6, barrier="bollard")]

    def test_consume(self):
        stats = osm_barriers.consume(self.conn, FakeRun(self.features()))
        self.assertEqual((stats["objects"], stats["fences"], stats["gates"], stats["fences new"], stats["hedges"]),
                         (6, 4, 2, 4, 1))
        rows = self.conn.execute(
            """select fence_id, type, look, height_m, height_source, round(length_m)
               from fences.fence where osm_id > %s order by osm_id""", (self.BASE,)).fetchall()
        b = self.BASE
        self.assertEqual(rows, [(f"osm:w{b + 1}", "fence", "open", 1.5, "default", 81),
                                (f"osm:w{b + 2}", "wall", "solid", 2.0, "tagged", 1111),
                                (f"osm:w{b + 3}", "hedge", "solid", 1.5, "default", 81),
                                (f"osm:w{b + 4}", "guard_rail", "open", 0.8, "default", 81)])
        self.assertEqual(self.conn.execute("select gate_id, kind, access from fences.gate where osm_id > %s"
                                           " order by osm_id", (b,)).fetchall(),
                         [(f"osm:n{b + 5}", "gate", "private"), (f"osm:n{b + 6}", "bollard", None)])
        # The fences layer gets a new version (OpenStreetMap's alone: ODbL, republish yes).
        self.assertEqual(self.conn.execute(
            "select version, license, republish, credit, features from core.layer_version_current"
            " where layer = 'fences.lines'").fetchone(),
            (stats["version"], "ODbL", "yes", "© OpenStreetMap contributors", 4))
        # The tables carry the licence in their comments.
        for table in ("fences.fence", "fences.gate"):
            comment = self.conn.execute("select obj_description(%s::regclass)", (table,)).fetchone()[0]
            self.assertIn("ODbL", comment)
            self.assertIn("republish: yes", comment)
        # Next extract: one fence gone, one edited.
        later = [f for f in self.features() if f["osm_id"] != b + 4]
        later[0] = way(b + 1, version=2, barrier="fence", fence_type="wood")
        stats = osm_barriers.consume(self.conn, FakeRun(later, T0.replace(hour=13)))
        self.assertEqual((stats["fences retired"], stats["fences changed"]), (1, 1))
        self.assertFalse(self.conn.execute("select active from fences.fence where osm_id = %s", (b + 4,)).fetchone()[0])
        self.assertEqual(self.conn.execute("select look from fences.fence where osm_id = %s", (b + 1,)).fetchone()[0],
                         "solid")

    def test_the_shrink_guard_refuses_to_retire_most_of_the_fences(self):
        osm_barriers.consume(self.conn, FakeRun(self.features()))
        with self.assertRaisesRegex(RuntimeError, "fences.fence: only 1 objects"):
            osm_barriers.consume(self.conn, FakeRun(self.features()[:1] + self.features()[-1:], T0.replace(hour=13)))
        self.assertEqual(self.conn.execute("select count(*) from fences.fence where active and osm_id > %s",
                                           (self.BASE,)).fetchone()[0], 4)            # nothing retired
        stats = osm_barriers.consume(self.conn, FakeRun(self.features()[:1] + self.features()[-1:], T0.replace(hour=14), True))
        self.assertEqual(stats["fences retired"], 3)                                  # allow_shrink lifts it

    def test_the_table_refuses_a_mismatched_id_and_an_unknown_type(self):
        for sql in ("insert into fences.fence (fence_id, kind, type, look, height_m, height_source, tags, osm_id, geom)"
                    " values ('osm:w1', 'fence', 'fence', 'open', 1, 'default', '{}', 2, 'SRID=4326;LINESTRING(0 0,1 1)')",
                    "insert into fences.fence (fence_id, kind, type, look, height_m, height_source, tags, osm_id, geom)"
                    " values ('osm:w1', 'fence', 'kerb', 'open', 1, 'default', '{}', 1, 'SRID=4326;LINESTRING(0 0,1 1)')"):
            with self.assertRaises(self.psycopg.errors.CheckViolation):
                self.conn.execute(sql)
            self.conn.rollback()

    def test_the_hedge_check_reads_the_table(self):
        from plugins.trees.ingest import hedge_check
        osm_barriers.consume(self.conn, FakeRun(self.features()))
        got = hedge_check.hedges_from_fences(self.conn)
        self.assertEqual([i for i, _ in got], [f"osm:w{self.BASE + 3}"])          # setUp made the real hedges inactive
        mine = [(i, g) for i, g in got if i == f"osm:w{self.BASE + 3}"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0][1]["type"], "LineString")
        self.assertNotIn(f"osm:w{self.BASE + 1}", [i for i, _ in got])         # only hedges, and only active ones


if __name__ == "__main__":
    unittest.main()
