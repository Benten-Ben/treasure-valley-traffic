"""bake.py's standard-library commands (status, check, rollback) and the tailnet-only check, against landscape
files written by tests/pmt.py with a bake entry in their metadata, as a real bake leaves them. test_bake.py runs the
same commands on GDAL's own files in the worker image."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from basemap.landscape import bake, plan as P, pmtiles
from basemap.landscape.tests import pmt
from basemap.landscape.tests.test_plan import PUBLIC, write_roads, write_water


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = bake.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CheckTest(unittest.TestCase):
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

    def fake_bake(self, roads=True, build="20261012T031500Z"):
        """A landscape file as the bake leaves it (tiles in the budget's area, the entry in its metadata), switched
        in like cmd_bake does."""
        shutil.rmtree(self.archive)
        os.makedirs(self.archive)
        write_water(self.archive, build=build)
        if roads:
            write_roads(self.archive)
        plan = P.resolve(P.exports(self.archive), visibility=PUBLIC)
        digest = P.digest(plan, "GDAL test")
        tiles = {t: bytes([i % 251]) * (100 + i) for i, t in enumerate(P.budget_tiles()[:6])}
        tiles[(8, 45, 93)] = b"z8"
        mine = {t: len(b) for t, b in tiles.items() if t[0] == 16}
        made = P.baked_entry(plan, digest, P.measure_budget(mine, plan.roads), "GDAL test")
        raw = pmt.write(os.path.join(self.dir, "raw.pmtiles"), tiles, {"vector_layers": []}, minzoom=8, maxzoom=16)
        pmtiles.write_with_metadata(raw, os.path.join(self.tiles, made["file"]), bake.metadata_with({}, made))
        old = P.current(self.tiles)
        entry = dict(made, previous=bake._previous(self.tiles, old, made["file"]))
        P.update_manifest(self.tiles, entry)
        P.prune(self.tiles, entry)
        return entry

    def test_nothing_yet(self):
        self.assertEqual(bake.check(self.tiles), [])
        self.assertEqual(bake.check(self.tiles, public=True), [])
        code, out, _ = run("check", "--tiles", self.tiles)
        self.assertEqual((code, out.strip()), (0, "no landscape entry yet"))
        self.assertEqual(bake.check(self.dir), [f"no {os.path.join(self.dir, 'manifest.json')}: build the basemap "
                                                "first (basemap/build.sh)"])

    def test_tailnet_only_is_machine_checkable(self):
        e = self.fake_bake(roads=True)
        self.assertEqual((e["republish"], e["access"]), ("internal", "tailnet"))
        meta = pmtiles.read_metadata(os.path.join(self.tiles, e["file"]))
        self.assertEqual(meta["tvt"]["landscape"]["access"], "tailnet")
        self.assertIn("served to the tailnet only", meta["description"])
        self.assertEqual(bake.check(self.tiles), [])
        problems = bake.check(self.tiles, public=True)
        self.assertEqual(problems, [f"{e['file']}: republish internal, tailnet only (the manifest serves it)",
                                    f"{e['file']}: republish internal, tailnet only (it's in the served folder)"])
        code, out, err = run("check", "--tiles", self.tiles, "--public")
        self.assertEqual(code, 1)
        self.assertIn("tailnet only", err)

        # A public bake switched in: the internal one is still kept (previous), and still served, so --public fails.
        p = self.fake_bake(roads=False, build="20261014T031500Z")
        self.assertEqual((p["access"], p["previous"]), ("public", e["file"]))
        self.assertEqual(bake.check(self.tiles), [])
        self.assertEqual(bake.check(self.tiles, public=True),
                         [f"{e['file']}: republish internal, tailnet only (it's in the served folder)"])
        os.unlink(os.path.join(self.tiles, e["file"]))
        self.assertEqual(bake.check(self.tiles), [f"{e['file']}: the previous file is missing"])
        P.update_manifest(self.tiles, dict(p, previous=None))
        self.assertEqual(bake.check(self.tiles, public=True), [])
        self.assertEqual(run("check", "--tiles", self.tiles, "--public")[0], 0)

    def test_files_without_an_entry_are_unknown(self):
        pmt.write(os.path.join(self.tiles, "landscape-0123456789ab.pmtiles"), {(8, 45, 93): b"x"}, {"name": "?"})
        self.assertEqual(bake.check(self.tiles, public=True),
                         ["landscape-0123456789ab.pmtiles: its metadata doesn't say who may see it"])
        with open(os.path.join(self.tiles, "landscape-0123456789ab.pmtiles"), "wb") as f:
            f.write(b"junk")
        self.assertIn("unreadable", bake.check(self.tiles, public=True)[0])

    def test_check_finds_disagreement(self):
        e = self.fake_bake()
        path = os.path.join(self.tiles, e["file"])
        bad = dict(e, budget=dict(e["budget"], largest=e["budget"]["largest"] + 1))
        P.update_manifest(self.tiles, bad)
        problems = bake.check(self.tiles)
        self.assertTrue(any("metadata's entry isn't the manifest's" in p for p in problems))
        self.assertTrue(any("its tiles measure" in p for p in problems))
        P.update_manifest(self.tiles, e)
        os.unlink(path)
        self.assertEqual(bake.check(self.tiles), [f"{e['file']}: the entry's file is missing"])
        with open(os.path.join(self.tiles, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        m["landscape"] = dict(e, access="public")
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(m, f)
        self.assertIn("access must be 'tailnet'", bake.check(self.tiles)[0])

    def test_rollback(self):
        code, _, err = run("rollback", "--tiles", self.tiles)
        self.assertEqual(code, 2)
        self.assertIn("no previous landscape file", err)
        a = self.fake_bake(roads=False)
        b = self.fake_bake(roads=True)
        self.assertEqual(b["previous"], a["file"])
        code, out, _ = run("rollback", "--tiles", self.tiles)
        self.assertEqual(code, 0, out)
        back = P.current(self.tiles)
        self.assertEqual((back["file"], back["previous"], back["access"]), (a["file"], b["file"], "public"))
        self.assertEqual(bake.check(self.tiles), [])
        code, _, _ = run("rollback", "--tiles", self.tiles)          # and forward again
        self.assertEqual(P.current(self.tiles)["file"], b["file"])
        with open(os.path.join(self.tiles, a["file"]), "wb") as f:
            f.write(b"junk")
        code, _, err = run("rollback", "--tiles", self.tiles)
        self.assertEqual(code, 2)
        self.assertIn("doesn't hold a bake entry", err)

    def test_status(self):
        code, _, err = run("status", "--archive", os.path.join(self.dir, "nowhere"))
        self.assertEqual(code, 2)
        self.assertIn("no archive folder", err)
        code, out, _ = run("status", "--archive", self.archive)
        self.assertEqual(code, 3)
        self.assertIn("no plugin exports a base layer yet", out)
        write_water(self.archive)
        write_roads(self.archive)
        code, out, _ = run("status", "--archive", self.archive, "--no-hash")
        self.assertEqual(code, 0)
        self.assertIn("roads.surfaces           roads/surfaces@20261013T031500Z (MultiPolygon, 3 features, z14-16)",
                      out)
        self.assertIn("Republish internal: served to the tailnet only", out)
        code, _, err = run("bake", "--tiles", os.path.join(self.dir, "none"), "--archive", self.archive)
        self.assertEqual(code, 2)
        self.assertIn("no tiles folder", err)


if __name__ == "__main__":
    unittest.main()
