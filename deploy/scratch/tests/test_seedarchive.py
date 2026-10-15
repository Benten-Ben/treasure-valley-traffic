"""Tests for deploy/scratch/seedarchive.py: each scratch database's archive gets production's held
files and the load state as it was when its dump began, so a loader's "same as the last load"
gate agrees with the database beside it. And for refresh.sh and run.sh's use of it.

    python3 -m unittest discover -s deploy/scratch/tests

Synthetic folders only; no database, no heavy.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SCRATCH))
sys.path.insert(0, SCRATCH)
import seedarchive  # noqa: E402

OSM_VALLEY = os.path.join(REPO, "plugins", "roads", "ingest", "sources", "osm_valley.py")
EXTRACT = "idaho-261005-20261007-cd0984ee.osm.pbf"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def loaded(md5, name):
    """The OSM loader's last-loaded.json (osm_valley.mark_loaded's shape)."""
    return json.dumps({"md5": md5, "file": name, "loaded_at": "2026-10-07T04:11:00-06:00"})


def files(root):
    out = set()
    for path, dirs, names in os.walk(root):
        out |= {os.path.relpath(os.path.join(path, n), root) for n in names}
        out |= {os.path.relpath(os.path.join(path, d), root) + "/" for d in dirs}
    return out


class Folders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prod = os.path.join(self.tmp.name, "prod")
        osm = os.path.join(self.prod, "osm")
        write(os.path.join(osm, EXTRACT), "extract X")
        write(os.path.join(osm, EXTRACT + ".md5"), "cd0984ee...  idaho-latest.osm.pbf\n")
        write(os.path.join(osm, "last-loaded.json"), loaded("cd0984ee" * 4, EXTRACT))
        write(os.path.join(osm, "state", "osm_street.json"), '{"md5": "x"}')
        write(os.path.join(osm, "state", "water", "osm_waterways.json"), '{"md5": "x"}')
        write(os.path.join(osm, "inbox", "idaho-latest.osm.pbf"), "a download waiting")
        write(os.path.join(osm, "tmp-cut-123", "valley.osm.pbf"), "a loader's work")
        write(os.path.join(osm, "last-loaded.json.part"), "half written")
        write(os.path.join(osm, ".hidden"), "")
        write(os.path.join(osm, "state", "x.json.part"), "")
        write(os.path.join(self.prod, "cameras", "status", "x.json"), "not seeded")
        os.symlink(os.path.join(self.prod, "cameras"), os.path.join(osm, "linked.json"))

    def p(self, *parts):
        return os.path.join(self.tmp.name, *parts)


class Snapshot(Folders):
    def test_it_takes_only_the_load_state(self):
        got = seedarchive.snapshot(self.prod, self.p("dump", "archive-state"), ["osm"])
        self.assertEqual(got["osm"], ["last-loaded.json", "state/osm_street.json", "state/water/osm_waterways.json"])
        self.assertEqual(files(self.p("dump", "archive-state")),
                         {"osm/", "osm/last-loaded.json", "osm/state/", "osm/state/osm_street.json",
                          "osm/state/water/", "osm/state/water/osm_waterways.json"})

    def test_a_folder_production_lacks_gives_an_empty_snapshot(self):
        got = seedarchive.snapshot(self.prod, self.p("dump", "archive-state"), ["water"])
        self.assertEqual(got, {"water": []})
        self.assertTrue(os.path.isdir(self.p("dump", "archive-state")))

    def test_same_tells_a_load_that_finished_during_the_dump(self):
        before, after = self.p("before"), self.p("after")
        seedarchive.snapshot(self.prod, before, ["osm"])
        seedarchive.snapshot(self.prod, after, ["osm"])
        self.assertEqual(seedarchive.differences(before, after), [])
        write(os.path.join(self.prod, "osm", "last-loaded.json"), loaded("ab" * 16, "idaho-new.osm.pbf"))
        write(os.path.join(self.prod, "osm", "state", "trails.json"), "{}")
        seedarchive.snapshot(self.prod, self.p("again"), ["osm"])
        self.assertEqual(seedarchive.differences(before, self.p("again")),
                         ["osm/last-loaded.json", "osm/state/trails.json"])


class Stage(Folders):
    def test_held_files_now_and_the_state_from_the_dump(self):
        seedarchive.snapshot(self.prod, self.p("dump", "archive-state"), ["osm"])
        # After the dump, production loads extract Y: a new held file, and its state says Y.
        osm = os.path.join(self.prod, "osm")
        write(os.path.join(osm, "idaho-y.osm.pbf"), "extract Y")
        write(os.path.join(osm, "last-loaded.json"), loaded("ab" * 16, "idaho-y.osm.pbf"))
        write(os.path.join(osm, "state", "osm_street.json"), '{"md5": "y"}')
        out = self.p("archive", ".staged-tvt")
        got = seedarchive.stage(self.prod, self.p("dump", "archive-state"), out, ["osm", "water"])
        self.assertEqual(got["osm"][0], [EXTRACT, EXTRACT + ".md5", "idaho-y.osm.pbf"])
        self.assertEqual(files(out), {
            "osm/", "osm/inbox/", f"osm/{EXTRACT}", f"osm/{EXTRACT}.md5", "osm/idaho-y.osm.pbf",
            "osm/last-loaded.json", "osm/state/", "osm/state/osm_street.json",
            "osm/state/water/", "osm/state/water/osm_waterways.json"})
        # The dump's state (X), not production's now (Y): loading Y on the copy isn't skipped.
        self.assertEqual(json.loads(read(os.path.join(out, "osm", "last-loaded.json")))["md5"], "cd0984ee" * 4)
        self.assertEqual(read(os.path.join(out, "osm", "state", "osm_street.json")), '{"md5": "x"}')
        self.assertEqual(read(os.path.join(out, "osm", "idaho-y.osm.pbf")), "extract Y")
        self.assertNotIn("water", got)

    def test_times_are_kept_and_the_mode_follows_the_umask(self):
        extract = os.path.join(self.prod, "osm", EXTRACT)
        os.utime(extract, (1_760_000_000, 1_760_000_000))
        old = os.umask(0o077)
        try:
            seedarchive.stage(self.prod, None, self.p("staged"), ["osm"])
        finally:
            os.umask(old)
        st = os.stat(self.p("staged", "osm", EXTRACT))
        self.assertEqual(int(st.st_mtime), 1_760_000_000)
        self.assertEqual(st.st_mode & 0o777, 0o600)

    def test_no_snapshot_means_no_state(self):
        out = self.p("archive", ".staged-tvt_s1")
        got = seedarchive.stage(self.prod, None, out, ["osm"])
        self.assertEqual(got["osm"], ([EXTRACT, EXTRACT + ".md5"], []))
        self.assertEqual(files(out), {"osm/", "osm/inbox/", f"osm/{EXTRACT}", f"osm/{EXTRACT}.md5"})

    def test_production_without_load_state_gives_none(self):
        os.remove(os.path.join(self.prod, "osm", "last-loaded.json"))
        seedarchive.snapshot(self.prod, self.p("dump", "archive-state"), ["osm"])
        write(os.path.join(self.prod, "osm", "last-loaded.json"), loaded("ab" * 16, "idaho-y.osm.pbf"))
        out = self.p("archive", ".staged")
        seedarchive.stage(self.prod, self.p("dump", "archive-state"), out, ["osm"])
        self.assertFalse(os.path.exists(os.path.join(out, "osm", "last-loaded.json")))

    def test_the_command_line(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(SCRATCH, "seedarchive.py"), *a],
                                        capture_output=True, text=True)
        r = run("snapshot", self.prod, self.p("dump", "archive-state"), "osm")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(run("same", self.p("dump", "archive-state"), self.p("dump", "archive-state")).returncode, 0)
        run("snapshot", self.prod, self.p("other"), "osm")
        write(self.p("other", "osm", "last-loaded.json"), "{}")
        r = run("same", self.p("dump", "archive-state"), self.p("other"))
        self.assertEqual((r.returncode, r.stdout.strip()), (1, "osm/last-loaded.json"))
        r = run("stage", self.prod, "-", self.p("staged"), "osm")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("none (no snapshot)", r.stderr)
        r = run("stage", self.prod, self.p("missing"), self.p("staged2"), "osm")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(run("bogus").returncode, 2)


class TheLoadersStateIsSeeded(unittest.TestCase):
    """The state files the loaders write are what seedarchive takes as load state."""

    def test_osm_valleys_gate_file_is_load_state(self):
        text = read(OSM_VALLEY)
        names = set(re.findall(r'"([\w.-]+\.json)"', text))
        self.assertIn("last-loaded.json", names)
        for name in names:
            self.assertTrue(seedarchive.is_state_file(name), name)


class RefreshUsesIt(unittest.TestCase):
    text = read(os.path.join(SCRATCH, "refresh.sh"))

    def test_the_state_is_snapshotted_before_the_dump(self):
        t = self.text
        snap = t.index('seedarchive snapshot "$PROD_ARCHIVE" "$from/archive-state" ')
        self.assertLess(snap, t.index("copy (select * from raw.record"))
        self.assertLess(snap, t.index("pg_dump -U tvt"))
        self.assertGreater(t.index('"$from/archive-state.after"'), t.index("pg_dump -U tvt"))

    def test_the_archive_is_staged_from_the_dumps_snapshot(self):
        self.assertIn('state=$from/archive-state', self.text)
        self.assertIn('seedarchive stage "$PROD_ARCHIVE" "$state" "$staged"', self.text)
        self.assertNotIn("rsync", self.text)

    def test_a_fresh_dump_is_for_day_windows(self):
        dump = self.text.index('if [ -z "$from" ]; then\n\tday_only')
        self.assertLess(dump, self.text.index("pg_dump -U tvt"))

    def test_jobs_get_their_own_databases_archive(self):
        run = read(os.path.join(SCRATCH, "run.sh"))
        self.assertIn('-v "$ARCHIVES/$db":/srv/archive', run)
        self.assertIn("-e TVT_ARCHIVE=/srv/archive", run)

    def test_setup_installs_it(self):
        self.assertIn('"$HERE"/seedarchive.py', read(os.path.join(SCRATCH, "setup.sh")))


if __name__ == "__main__":
    unittest.main()
