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
