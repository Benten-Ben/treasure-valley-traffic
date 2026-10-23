"""Reading a trees build folder (standard library only; the database test needs psycopg and a PostGIS database named by
TVT_TEST_DATABASE_URL, and leaves nothing behind: it works inside one transaction and rolls it back).

The public tables hold only trees found in the lidar: a build that carries the private fields (the inventory's source
and id, a trunk diameter, a trunk-to-crown offset), or any tree kind but 'placed', is refused whole."""
import json
import os
import tempfile
import unittest

from plugins.trees.ingest import load


def write(folder, trees, log=()):
    json.dump({"build_id": "c-test", "area": "c", "started_at": "2026-10-08T15:00:00Z", "params": {}, "counts": {}},
              open(os.path.join(folder, "build.json"), "w"))
    json.dump({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-116.2, 43.63]}, "properties": t} for t in trees]},
        open(os.path.join(folder, "trees.geojson"), "w"))
    with open(os.path.join(folder, "log.jsonl"), "w") as f:
        for e in log:
            f.write(json.dumps(e) + "\n")


HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS = os.path.join(os.path.dirname(HERE), "migrations")
TREE = {"id": "c-1-2", "kind": "placed", "type": "broadleaf", "height_m": 12.0, "crown_radius_m": 4.0,
        "fit": {"width_vs_typical_sd": 0.1, "crowded": False, "width_curve": "broadleaf", "profile": None, "spring": None}}
EVENT = {"tree_id": "c-1-2", "at": "2023-10-24T12:00:00Z", "event": "placed",
         "detail": {"lidar": "USGS 3DEP QL1 lidar", "height_m": 12.0, "crown_width_m": 8.0, "theta": 0.2}}
# the private fields, named once here: what a public build must never carry
PRIVATE_TREE = {"catalogue": "boise", "catalogue_id": "x"}
PRIVATE_FIT = {"dbh_in": 14, "trunk_to_crown_m": 0.8}


class ReadBuildTest(unittest.TestCase):
    def test_reads_trees_and_log(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [TREE, dict(TREE, id="c-3-4")], [EVENT])
            build, trees, log = load.read_build(d)
            self.assertEqual(build["area"], "c")
            self.assertEqual([t["id"] for t in trees], ["c-1-2", "c-3-4"])
            self.assertEqual(trees[0]["lon"], -116.2)
            self.assertEqual(len(log), 1)

    def test_rejects_bad_rows(self):
        bad = [dict(TREE, kind="maybe"), dict(TREE, height_m=0), dict(TREE, crown_radius_m=None),
               dict(TREE, type="oak")]
        for t in bad:
            with tempfile.TemporaryDirectory() as d:
                write(d, [t])
                with self.assertRaises(ValueError):
                    load.read_build(d)

    def test_rejects_repeated_ids(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [TREE, TREE])
            with self.assertRaises(ValueError):
                load.read_build(d)

    def test_refuses_a_tree_that_is_not_one_found_in_the_lidar(self):
        # the old kinds, and a placed tree that still carries the inventory's source and id
        bad = [dict(TREE, kind="catalogued"), dict(TREE, kind="estimated"), dict(TREE, **PRIVATE_TREE),
               dict(TREE, kind="catalogued", **PRIVATE_TREE), dict(TREE, catalogue_id="x")]
        for t in bad:
            with tempfile.TemporaryDirectory() as d:
                write(d, [t])
                with self.assertRaises(ValueError, msg=str(t)):
                    load.read_build(d)

    def test_refuses_a_fit_with_a_trunk_diameter_or_offset(self):
        for extra in (PRIVATE_FIT, {"dbh_in": 14}, {"trunk_to_crown_m": 0.8}, {"from": "Urban Tree Database"}):
            with tempfile.TemporaryDirectory() as d:
                write(d, [dict(TREE, fit=dict(TREE["fit"], **extra))])
                with self.assertRaises(ValueError, msg=str(extra)):
                    load.read_build(d)

    def test_refuses_a_log_event_with_private_content(self):
        bad = [dict(EVENT, event="estimated"), dict(EVENT, event="measured"),
               dict(EVENT, detail=dict(EVENT["detail"], **PRIVATE_FIT)), dict(EVENT, detail=dict(EVENT["detail"], dbh_in=7)),
               dict(EVENT, catalogue_id="x")]
        for e in bad:
            with tempfile.TemporaryDirectory() as d:
                write(d, [TREE], [e])
                with self.assertRaises(ValueError, msg=str(e)):
                    load.read_build(d)

    def test_an_anchors_file_beside_the_build_is_never_read(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [TREE], [EVENT])
            with open(os.path.join(d, "anchors.jsonl"), "w") as f:
                f.write("this is not even json\n")
            build, trees, log = load.read_build(d)
            self.assertEqual((len(trees), len(log)), (1, 1))


DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


def ensure_tables(conn):
    """The trees schema as the migrations leave it, inside the caller's transaction (rolled back by the test)."""
    if conn.execute("select to_regclass('trees.tree')").fetchone()[0] is None:
        for name in sorted(os.listdir(MIGRATIONS)):
            if name[:4] in ("0001", "0003"):
                with open(os.path.join(MIGRATIONS, name)) as f:
                    conn.execute(f.read())


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a PostGIS database")
class DatabaseTest(unittest.TestCase):
    def test_the_public_build_writes_no_inventory_rows_or_diameters(self):
        import psycopg
        with psycopg.connect(DB_URL) as conn:
            try:
                ensure_tables(conn)
                cols = {r[0] for r in conn.execute(
                    "select column_name from information_schema.columns where table_schema = 'trees' and table_name = 'tree'")}
                self.assertFalse(cols & set(PRIVATE_TREE), "the migration leaves no private column")
                with tempfile.TemporaryDirectory() as d:
                    write(d, [dict(TREE, id="tvt-test-1"), dict(TREE, id="tvt-test-2")],
                          [dict(EVENT, tree_id="tvt-test-1")])
                    stats = load.load(conn, *load.read_build(d))
                self.assertEqual((stats["trees"], stats["log events"]), (2, 1))
                self.assertEqual(conn.execute("select count(*) from trees.tree where area = 'c'"
                                              " and tree_id like 'tvt-test-%'").fetchone()[0], 2)
                self.assertEqual(conn.execute(
                    "select count(*) from trees.tree where fit ? 'dbh_in' or fit ? 'trunk_to_crown_m'").fetchone()[0], 0)
                self.assertEqual(conn.execute(
                    "select count(*) from trees.tree_log where detail ? 'dbh_in' or detail ? 'trunk_to_crown_m'").fetchone()[0], 0)
                # the table itself refuses any other kind, whatever loads it
                for kind in ("catalogued", "estimated"):
                    with self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                        conn.execute("insert into trees.tree (tree_id, area, kind, type, geom, height_m, crown_radius_m, build_id)"
                                     " values ('tvt-test-k', 'c', %s, 'broadleaf', ST_SetSRID(ST_MakePoint(-116.2, 43.6), 4326),"
                                     " 5, 2, 'c-test')", (kind,))
            finally:
                conn.rollback()


def run_migration(conn, prefix):
    for name in sorted(os.listdir(MIGRATIONS)):
        if name[:4] == prefix:
            with open(os.path.join(MIGRATIONS, name)) as f:
                conn.execute(f.read())


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a PostGIS database")
class MigrationCleanUpTest(unittest.TestCase):
    """0003 on a schema as 0001 made it, holding rows in the old formats (invented ids and values): only the clean
    lidar-found trees and their clean events remain, with the inventory's keys stripped, and the build records lose the
    inventory's counts and sources. The schema is dropped and rebuilt inside the transaction, which is rolled back."""

    OLD_POINT = "ST_SetSRID(ST_MakePoint(-116.2, 43.6), 4326)"

    def old_tree(self, conn, tree_id, kind="placed", catalogue=None, fit=None, build="c-old"):
        conn.execute(
            f"insert into trees.tree (tree_id, area, kind, type, geom, height_m, crown_radius_m, catalogue, catalogue_id, fit, build_id)"
            f" values (%s, 'c', %s, 'broadleaf', {self.OLD_POINT}, 9, 3, %s, %s, %s, %s)",
            (tree_id, kind, catalogue, "x-1" if catalogue else None, json.dumps(fit or {}), build))

    def old_event(self, conn, tree_id, event, detail):
        conn.execute("insert into trees.tree_log (tree_id, at, event, detail, build_id) values (%s, '2023-10-24T12:00:00Z', %s, %s, 'c-old')",
                     (tree_id, event, json.dumps(detail)))

    def test_it_deletes_what_came_from_an_inventory_and_strips_what_remains(self):
        import psycopg
        with psycopg.connect(DB_URL) as conn:
            try:
                conn.execute("drop schema if exists trees cascade")
                run_migration(conn, "0001")
                conn.execute("insert into trees.build (build_id, area, started_at, params, counts) values ('c-old', 'c', now(), %s, %s)",
                             (json.dumps({"theta": 0.2, "sources": [{"source": "trees/usgs_3dep_lidar"}, {"source": "catalogue"},
                                                                     {"source": "urban_tree_database"}, {"source": "trees/sentinel2"}]}),
                              json.dumps({"trees": 5, "catalogued": 2, "estimated": 1, "placed": 2})))
                conn.execute("insert into trees.build (build_id, area, started_at, params, counts) values ('c-bare', 'c', now(), '{}', '{}')")
                self.old_tree(conn, "c-1-1", fit={"crowded": False, "dbh_in": 14, "trunk_to_crown_m": 0.8})   # keeps, minus the keys
                self.old_tree(conn, "c-2-2", fit={"crowded": True})                                           # keeps as it is
                self.old_tree(conn, "c-3-3", kind="catalogued", catalogue="boise")                            # goes
                self.old_tree(conn, "boise-fake-1", kind="estimated", catalogue="boise")                                      # goes
                self.old_tree(conn, "c-9-9", kind="catalogued", catalogue="boise")                            # goes, with its log
                self.old_event(conn, "c-1-1", "placed", {"height_m": 12, "dbh_in": 14, "trunk_to_crown_m": 0.8})   # goes (carries both)
                self.old_event(conn, "c-1-1", "measured", {"height_m": 12})                                   # stays
                self.old_event(conn, "c-2-2", "placed", {"height_m": 8, "theta": 0.2})                        # stays
                self.old_event(conn, "c-2-2", "estimated", {"why": "x"})                                      # goes: an estimated event
                self.old_event(conn, "c-2-2", "remeasured", {"dbh_in": 3, "height_m": 8})                     # goes: a diameter
                self.old_event(conn, "c-2-2", "moved", {"trunk_to_crown_m": 1.1})                             # goes: an offset
                self.old_event(conn, "boise-fake-1", "placed", {})                                            # goes: an inventory id
                self.old_event(conn, "boise-orphan", "placed", {})                                            # goes: orphan of the form
                self.old_event(conn, "c-9-9", "placed", {"height_m": 9})                                      # goes with its tree
                self.old_event(conn, "c-8-8", "placed", {"height_m": 9, "dbh_in": 5, "x": 1})                 # goes (carries a diameter)
                self.old_event(conn, "c-7-7", "placed", {"height_m": 9})                                      # stays: a tree not in the table now
                run_migration(conn, "0003")

                got = {r[0]: r[1] for r in conn.execute("select tree_id, fit from trees.tree")}
                self.assertEqual(got, {"c-1-1": {"crowded": False}, "c-2-2": {"crowded": True}})
                events = sorted((r[0], r[1]) for r in conn.execute("select tree_id, event from trees.tree_log"))
                self.assertEqual(events, [("c-1-1", "measured"), ("c-2-2", "placed"), ("c-7-7", "placed")])
                self.assertEqual(conn.execute("select count(*) from trees.tree_log where detail ? 'dbh_in' or detail ? 'trunk_to_crown_m'").fetchone()[0], 0)
                cols = {r[0] for r in conn.execute("select column_name from information_schema.columns where table_schema = 'trees' and table_name = 'tree'")}
                self.assertFalse(cols & {"catalogue", "catalogue_id"})
                self.assertEqual(conn.execute("select count(*) from pg_indexes where schemaname = 'trees' and indexname = 'tree_catalogue_idx'").fetchone()[0], 0)
                b = conn.execute("select counts, params from trees.build where build_id = 'c-old'").fetchone()
                self.assertEqual(b[0], {"trees": 5, "placed": 2})
                self.assertEqual([x["source"] for x in b[1]["sources"]], ["trees/usgs_3dep_lidar", "trees/sentinel2"])
                self.assertEqual(b[1]["theta"], 0.2)
                self.assertEqual(conn.execute("select counts, params from trees.build where build_id = 'c-bare'").fetchone(), ({}, {}))
                with self.assertRaises(psycopg.errors.CheckViolation), conn.transaction():
                    conn.execute(f"insert into trees.tree (tree_id, area, kind, type, geom, height_m, crown_radius_m, build_id)"
                                 f" values ('c-5-5', 'c', 'catalogued', 'broadleaf', {self.OLD_POINT}, 9, 3, 'c-old')")
            finally:
                conn.rollback()
