"""basemap/lock.py, and the writers of tiles/manifest.json that take it: ground/tiles.py, landscape/plan.py, build.sh."""
import fcntl
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from basemap import lock
from basemap.ground import tiles as ground_tiles
from basemap.landscape import plan as P

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WAIT = 0.4


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.locks = os.path.join(self.dir, "locks")
        self.tiles = os.path.join(self.dir, "tiles")
        os.makedirs(self.tiles)
        self.write_manifest({"zoom": 10, "basemap": {"file": "valley.pmtiles"}})
        env = mock.patch.dict(os.environ, {lock.ENV: self.locks})
        env.start()
        self.addCleanup(env.stop)

    def write_manifest(self, m):
        with open(os.path.join(self.tiles, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(m, f)

    def manifest(self):
        with open(os.path.join(self.tiles, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def hold(self, name):
        """Hold the lock `name` from outside the code under test; returns a release function."""
        os.makedirs(self.locks, exist_ok=True)
        fd = os.open(os.path.join(self.locks, name), os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)

        def release():
            os.close(fd)
        return release

    def assertWaits(self, name, work):
        """work() must not finish while `name` is held, and must finish once it is released."""
        release = self.hold(name)
        done = threading.Event()
        errors = []

        def run():
            try:
                work()
            except BaseException as err:          # noqa: BLE001 - reported below
                errors.append(err)
            finally:
                done.set()
        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.assertFalse(done.wait(WAIT), "the write didn't wait for the lock")
        release()
        self.assertTrue(done.wait(10), "the write never finished after the lock was released")
        t.join()
        self.assertEqual(errors, [])

    def assertNoLockInTiles(self):
        self.assertEqual(sorted(f for f in os.listdir(self.tiles) if f.endswith(".lock")), [])


class LockTest(Base):
    def test_lock_dir_setting_and_default(self):
        self.assertEqual(lock.lock_dir(), self.locks)
        with mock.patch.dict(os.environ):
            del os.environ[lock.ENV]
            d = lock.lock_dir()
        self.assertEqual(os.path.basename(d), "locks")
        self.assertEqual(os.path.basename(os.path.dirname(d)), "data")

    def test_a_worktree_uses_its_main_checkouts_folder(self):
        main = os.path.join(self.dir, "main")
        wt = os.path.join(self.dir, "wt")
        gitdir = os.path.join(main, ".git", "worktrees", "wt")
        os.makedirs(gitdir)
        os.makedirs(wt)
        with open(os.path.join(gitdir, "commondir"), "w") as f:
            f.write("../..\n")
        with open(os.path.join(wt, ".git"), "w") as f:
            f.write(f"gitdir: {gitdir}\n")
        self.assertEqual(lock._main_checkout(wt), main)
        self.assertEqual(lock._main_checkout(main), main)

    def test_locked_creates_the_folder_and_waits(self):
        with lock.locked("a.lock"):
            self.assertTrue(os.path.isfile(os.path.join(self.locks, "a.lock")))
        self.assertWaits("a.lock", lambda: lock.locked("a.lock").__enter__())

    def test_an_unusable_folder_fails_with_the_variable_named(self):
        blocker = os.path.join(self.dir, "file")
        open(blocker, "w").close()
        with mock.patch.dict(os.environ, {lock.ENV: os.path.join(blocker, "sub")}):
            with self.assertRaises(OSError) as cm:
                lock.ensure()
        self.assertIn(lock.ENV, str(cm.exception))

    def test_a_new_lock_file_is_group_writable_whatever_the_umask(self):
        old = os.umask(0o022)
        try:
            with lock.locked("new.lock"):
                pass
        finally:
            os.umask(old)
        for name in ("new.lock", "landscape.lock", "manifest.lock"):
            mode = stat.S_IMODE(os.stat(os.path.join(self.locks, name)).st_mode)
            self.assertEqual(mode, 0o664, name)

    def test_a_leftover_temporary_file_does_not_block_a_new_lock(self):
        # Worker containers often run the job as pid 1, so a pid-named temporary file would be shared between them,
        # and one left by a killed run would stop every later one.
        os.makedirs(self.locks)
        for pid in (1, os.getpid()):
            open(os.path.join(self.locks, f"{lock.MANIFEST}.{pid}.tmp"), "w").close()
        lock.ensure()
        self.assertTrue(os.path.isfile(os.path.join(self.locks, lock.MANIFEST)))
        left = sorted(n for n in os.listdir(self.locks) if n.endswith(".tmp"))
        self.assertEqual(left, sorted(f"{lock.MANIFEST}.{pid}.tmp" for pid in (1, os.getpid())))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can open any file")
    def test_ensure_fails_at_the_start_on_a_lock_file_it_cannot_open(self):
        os.makedirs(self.locks)
        bad = os.path.join(self.locks, lock.MANIFEST)
        open(bad, "w").close()
        os.chmod(bad, 0o444)
        with self.assertRaises(OSError) as cm:
            lock.ensure()
        self.assertIn(bad, str(cm.exception))
        self.assertIn("chmod", str(cm.exception))

    def test_a_name_is_a_bare_file_name(self):
        for bad in ("", "../x.lock", "a/b.lock"):
            with self.assertRaises(ValueError):
                with lock.locked(bad):
                    pass

    def test_command_form_runs_and_passes_the_status_on(self):
        env = dict(os.environ)
        for code in (0, 3):
            r = subprocess.run([sys.executable, "-m", "basemap.lock", "x.lock", "--", sys.executable, "-c",
                                f"import sys; sys.exit({code})"], cwd=ROOT, env=env)
            self.assertEqual(r.returncode, code)
        self.assertTrue(os.path.isfile(os.path.join(self.locks, "x.lock")))
        r = subprocess.run([sys.executable, "-m", "basemap.lock", "x.lock"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)

    def test_command_form_waits_for_the_lock(self):
        release = self.hold("y.lock")
        p = subprocess.Popen([sys.executable, "-m", "basemap.lock", "y.lock", "--", sys.executable, "-c", "pass"],
                             cwd=ROOT, env=dict(os.environ))
        time.sleep(WAIT)
        self.assertIsNone(p.poll(), "the command ran while the lock was held")
        release()
        self.assertEqual(p.wait(10), 0)


class ManifestWriterTest(Base):
    def test_ground_update_manifest_waits_for_the_lock(self):
        entry = ground_tiles.flat_entry("Flat ground: not built yet.")
        self.assertWaits(lock.MANIFEST, lambda: ground_tiles.update_manifest(self.tiles, entry))
        m = self.manifest()
        self.assertEqual(m["basemap"], {"file": "valley.pmtiles"})
        self.assertEqual(m[ground_tiles.ENTRY]["status"], "flat")
        self.assertNoLockInTiles()
        self.assertEqual([f for f in os.listdir(self.tiles) if f.startswith(".manifest-")], [])

    def test_landscape_update_manifest_waits_for_the_lock(self):
        entry = P.empty_entry("nothing to bake")
        self.assertWaits(lock.MANIFEST, lambda: P.update_manifest(self.tiles, dict(entry, previous=None)))
        self.assertIn(P.ENTRY, self.manifest())
        self.assertNoLockInTiles()

    def test_the_landscape_lock_is_not_the_manifest_lock(self):
        # a bake holds .landscape for its whole run and takes the manifest lock inside it
        with P.locked():
            P.update_manifest(self.tiles, dict(P.empty_entry("x"), previous=None))
        names = sorted(os.listdir(self.locks))
        self.assertEqual(names, [lock.LANDSCAPE, lock.MANIFEST])
        self.assertNoLockInTiles()


def _stubs(bin_dir):
    """Stand-ins for pmtiles, git and curl, so build.sh runs offline."""
    def tool(name, body):
        path = os.path.join(bin_dir, name)
        with open(path, "w") as f:
            f.write("#!/usr/bin/env bash\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    tool("pmtiles", 'echo tiles > "$3"\n')        # pmtiles extract SRC OUT --bbox=... --maxzoom=...
    tool("curl", "exit 1\n")                      # BUILD is given, so this is never asked
    tool("git", '''
if [ "$1" = clone ]; then mkdir -p "${@: -1}"; exit 0; fi
if [ "$1" = -C ] && [ "$3" = checkout ]; then
	mkdir -p "$2/fonts/Noto Sans Regular" "$2/sprites/v4"
	echo x > "$2/fonts/Noto Sans Regular/0-255.pbf"
fi
exit 0
''')


class BuildShTest(Base):
    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.dir, "out")
        os.makedirs(self.out)
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin)
        _stubs(self.bin)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"], TILES_DIR=self.out,
                        BUILD="20261012.pmtiles", PYTHONPATH=ROOT)
        with open(os.path.join(self.out, "manifest.json"), "w") as f:
            json.dump({"landscape": {"file": "kept"}}, f)

    def build(self):
        return subprocess.Popen(["bash", os.path.join(ROOT, "basemap", "build.sh")], cwd=self.dir, env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def test_the_manifest_write_waits_for_the_lock_and_keeps_other_entries(self):
        release = self.hold(lock.MANIFEST)
        p = self.build()
        deadline = time.time() + 20
        while time.time() < deadline and not os.path.exists(os.path.join(self.out, "valley.pmtiles")):
            time.sleep(0.05)
        self.assertTrue(os.path.exists(os.path.join(self.out, "valley.pmtiles")))
        time.sleep(WAIT)
        self.assertIsNone(p.poll(), "build.sh wrote the manifest while the lock was held")
        with open(os.path.join(self.out, "manifest.json")) as f:
            self.assertNotIn("basemap", json.load(f))
        release()
        out, _ = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 0, out)
        with open(os.path.join(self.out, "manifest.json")) as f:
            m = json.load(f)
        self.assertEqual(m["landscape"], {"file": "kept"})
        self.assertEqual(m["basemap"]["file"], "valley.pmtiles")
        self.assertEqual(sorted(f for f in os.listdir(self.out) if f.endswith(".lock")), [])

    def test_atomic_writes_leave_no_partial_files(self):
        out, _ = self.build().communicate(timeout=30)
        names = os.listdir(self.out)
        self.assertNotIn("valley.pmtiles.part", names)
        self.assertEqual([n for n in names if n.startswith(".manifest-")], [])
        self.assertIn("valley.pmtiles", names)

    def test_a_failing_manifest_step_leaves_the_old_manifest_and_no_temp_file(self):
        with open(os.path.join(self.out, "manifest.json"), "w") as f:
            f.write("{not json")
        p = self.build()
        p.communicate(timeout=30)
        self.assertNotEqual(p.returncode, 0)
        with open(os.path.join(self.out, "manifest.json")) as f:
            self.assertEqual(f.read(), "{not json")
        self.assertEqual([n for n in os.listdir(self.out) if n.startswith(".manifest-")], [])


if __name__ == "__main__":
    unittest.main()
