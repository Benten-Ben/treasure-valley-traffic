"""Tests for deploy/bin/worker-test: the container's caps, the runner where a skip is a
failure (run here with this Python), and the real thing in the worker image where docker
and tvt-worker are there (the VM).

    python3 -m unittest discover -s deploy/tests
"""
import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER_TEST = os.path.join(os.path.dirname(HERE), "bin", "worker-test")


def load():
    loader = importlib.machinery.SourceFileLoader("worker_test_under_test", WORKER_TEST)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


wt = load()

CASES = {
    "passes": """
        import unittest
        class T(unittest.TestCase):
            def test_one(self):
                self.assertEqual(1 + 1, 2)
    """,
    "skips": """
        import unittest
        class T(unittest.TestCase):
            def test_one(self):
                pass
            @unittest.skip("rasterio missing")
            def test_two(self):
                pass
    """,
    "fails": """
        import unittest
        class T(unittest.TestCase):
            def test_one(self):
                self.assertEqual(1, 2)
    """,
    "unexpected": """
        import unittest
        class T(unittest.TestCase):
            @unittest.expectedFailure
            def test_one(self):
                pass
    """,
    "empty": "",
}


def make_checkout(root):
    """A folder per case, each a package of tests."""
    for name, body in CASES.items():
        os.makedirs(os.path.join(root, name))
        open(os.path.join(root, name, "__init__.py"), "w").close()
        if body:
            with open(os.path.join(root, name, "test_case.py"), "w") as f:
                f.write(textwrap.dedent(body))


EXPECTED = {"passes": 0, "skips": 1, "fails": 1, "unexpected": 1, "empty": 1}


class Command(unittest.TestCase):
    def test_the_container_is_capped_and_offline(self):
        cmd = wt.command("/srv/x", ["discover", "-s", "basemap/ground", "-t", "."], uid=1001, gid=1001, name="n")
        joined = " ".join(cmd)
        for words in ("docker run --rm --init", "--memory 1g --memory-swap 1g", "--cpus 1", "--network none",
                      "--read-only", "--user 1001:1001", "-v /srv/x:/repo:ro -w /repo", "tvt-worker python -c"):
            self.assertIn(words, joined)
        self.assertEqual(cmd[-5:], ["discover", "-s", "basemap/ground", "-t", "."])

    def test_usage(self):
        self.assertEqual(wt.main([]), 2)
        self.assertEqual(wt.main(["-C"]), 2)
        self.assertEqual(wt.main(["-C", "/no/such/folder", "discover"]), 2)


class Slots(unittest.TestCase):
    """At most two runs at once: a third waits for a slot, or gives up."""

    def test_a_third_run_waits_for_a_slot(self):
        with tempfile.TemporaryDirectory() as d:
            a = wt.take_slot("run a", 0, folder=d)
            b = wt.take_slot("run b", 0, folder=d)
            self.assertIsNotNone(a)
            self.assertIsNotNone(b)
            started = time.monotonic()
            self.assertIsNone(wt.take_slot("run c", 0.3, folder=d, poll_s=0.1))
            self.assertGreaterEqual(time.monotonic() - started, 0.3)
            os.close(a)
            c = wt.take_slot("run c", 0, folder=d)
            self.assertIsNotNone(c)
            with open(os.path.join(d, "1")) as f:
                self.assertEqual(f.read(), "run c\n")
            os.close(b)
            os.close(c)

    def test_a_slot_held_by_another_process_counts(self):
        with tempfile.TemporaryDirectory() as d:
            hold = ("import os, sys, time; sys.path.insert(0, %r); import test_worker_test as t; "
                    "fd = t.wt.take_slot('other process', 0, folder=%r); print('held', flush=True); time.sleep(30)"
                    % (HERE, d))
            p = subprocess.Popen([sys.executable, "-c", hold], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(p.stdout.readline(), "held\n")
                mine = wt.take_slot("mine", 0, folder=d, slots=1)
                self.assertIsNone(mine)
            finally:
                p.kill()
                p.wait()
                p.stdout.close()
            mine = wt.take_slot("mine", 1, folder=d, slots=1, poll_s=0.1)
            self.assertIsNotNone(mine)
            os.close(mine)


class Runner(unittest.TestCase):
    """The in-container runner, with this Python."""

    def test_a_skip_or_an_empty_run_fails(self):
        with tempfile.TemporaryDirectory() as root:
            make_checkout(root)
            for name, code in EXPECTED.items():
                r = subprocess.run([sys.executable, "-c", wt.RUNNER, "discover", "-s", name, "-t", "."],
                                   cwd=root, capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, code, (name, r.stderr))
            r = subprocess.run([sys.executable, "-c", wt.RUNNER, "skips.test_case"], cwd=root,
                               capture_output=True, text=True, timeout=60)
            self.assertIn("SKIPPED (a failure here): skips.test_case.T.test_two: rasterio missing", r.stderr)
            self.assertIn("2 tests, 0 failures, 0 errors, 1 skipped: FAILED", r.stderr)


def have_worker_image():
    if not (shutil.which("docker") and sys.platform.startswith("linux")):
        return False
    return subprocess.run(["docker", "image", "inspect", wt.IMAGE], capture_output=True).returncode == 0


@unittest.skipUnless(have_worker_image(), "needs docker and the tvt-worker image (the VM)")
class InTheWorkerImage(unittest.TestCase):
    def test_codes_in_the_container(self):
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root, 0o755)
            make_checkout(root)
            for name, code in EXPECTED.items():
                r = subprocess.run([sys.executable, WORKER_TEST, "-C", root, "discover", "-s", name, "-t", "."],
                                   capture_output=True, text=True, timeout=300)
                self.assertEqual(r.returncode, code, (name, r.stderr))

    def test_no_network_and_a_read_only_checkout(self):
        with tempfile.TemporaryDirectory() as root:
            os.chmod(root, 0o755)
            os.makedirs(os.path.join(root, "probe"))
            open(os.path.join(root, "probe", "__init__.py"), "w").close()
            with open(os.path.join(root, "probe", "test_probe.py"), "w") as f:
                f.write(textwrap.dedent("""
                    import os, socket, tempfile, unittest
                    class Probe(unittest.TestCase):
                        def test_no_network(self):
                            with self.assertRaises(OSError):
                                socket.create_connection(("1.1.1.1", 53), timeout=3)
                        def test_checkout_is_read_only(self):
                            with self.assertRaises(OSError):
                                open("/repo/probe/written", "w")
                        def test_tmp_is_writable(self):
                            with tempfile.NamedTemporaryFile() as f:
                                f.write(b"x")
                        def test_the_worker_tools_import(self):
                            import numpy, rasterio, pdal  # noqa: F401
                """))
            r = subprocess.run([sys.executable, WORKER_TEST, "-C", root, "probe.test_probe"],
                               capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("4 tests, 0 failures, 0 errors, 0 skipped: OK", r.stderr)


if __name__ == "__main__":
    unittest.main()
