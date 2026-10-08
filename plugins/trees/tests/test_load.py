"""Reading a trees build folder (standard library only)."""
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


TREE = {"id": "c-1-2", "kind": "placed", "type": "broadleaf", "height_m": 12.0, "crown_radius_m": 4.0,
        "catalogue": None, "catalogue_id": None}


class ReadBuildTest(unittest.TestCase):
    def test_reads_trees_and_log(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, [TREE, dict(TREE, id="boise-x", kind="catalogued", catalogue="boise", catalogue_id="x")],
                  [{"tree_id": "c-1-2", "at": "2023-10-24T12:00:00Z", "event": "placed", "detail": {}}])
            build, trees, log = load.read_build(d)
            self.assertEqual(build["area"], "c")
            self.assertEqual([t["id"] for t in trees], ["c-1-2", "boise-x"])
            self.assertEqual(trees[0]["lon"], -116.2)
            self.assertEqual(len(log), 1)

    def test_rejects_bad_rows(self):
        bad = [dict(TREE, kind="maybe"), dict(TREE, height_m=0), dict(TREE, catalogue="boise"),
               dict(TREE, kind="catalogued")]
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
