"""ground.py, the contract on the command line: standard library only."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from basemap.ground import ground, manifest as M
from basemap.ground.tests.test_inputs import fgb_layer, write_export
from basemap.ground.tests.test_manifest import SSURGO


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = ground.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.archive = os.path.join(self.dir, "archive")
        self.tiles = os.path.join(self.dir, "tiles")
        os.makedirs(self.archive)
        os.makedirs(self.tiles)
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"zoom": 10}, f)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_spec(self):
        code, out, _ = run("spec")
        self.assertEqual(code, 0)
        self.assertIn("E 495920 N 4855750", out)
        self.assertIn("179,340 x 189,880", out)
        self.assertIn("<= 0.6 MB and <= 14 requests", out)

    def test_status_flat_then_painted(self):
        code, out, _ = run("status", "--archive", self.archive)
        self.assertEqual(code, 3)
        self.assertIn("Flat ground", out)
        m = write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        code, out, _ = run("status", "--archive", self.archive)
        self.assertEqual(code, 0)
        self.assertIn(f"soils/ground@{m.build}", out)
        self.assertIn("fallback: CSB 2025 fields plus CDL 2025 crop pixels (C7)", out)
        code, out, _ = run("check-export", m.folder)
        self.assertEqual(code, 0)
        self.assertIn("ground: ground.fgb (FlatGeobuf; MultiPolygon, 3 features)", out)

    def test_status_refuses_internal(self):
        achd = {"name": "achd", "licence": "none-stated", "republish": "internal", "credit": "ACHD"}
        write_export(self.archive, "soils", [fgb_layer("ground", ["achd"])], [achd])
        code, _, err = run("status", "--archive", self.archive)
        self.assertEqual(code, 2)
        self.assertIn("public inputs only", err)

    def test_check_export_reports_problems(self):
        m = write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        os.remove(os.path.join(m.folder, "ground.fgb"))
        code, _, err = run("check-export", m.folder)
        self.assertEqual(code, 2)
        self.assertIn("not valid", err)

    def test_flat(self):
        code, out, _ = run("flat", "--tiles", self.tiles, "--archive", self.archive)
        self.assertEqual(code, 0)
        with open(os.path.join(self.tiles, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["zoom"], 10)
        self.assertEqual(m["ground"]["status"], "flat")
        self.assertIn("soil survey", m["ground"]["reason"])
        code, _, _ = run("flat", "--tiles", self.tiles, "--reason", "Flat ground: the painter is being rebuilt.")
        self.assertEqual(code, 0)
        write_export(self.archive, "soils", [fgb_layer("ground", ["ssurgo"])], [SSURGO])
        code, _, err = run("flat", "--tiles", self.tiles, "--archive", self.archive)
        self.assertEqual(code, 2)                                   # it could be painted: nothing to record
        self.assertTrue(M.find(self.archive))


if __name__ == "__main__":
    unittest.main()
