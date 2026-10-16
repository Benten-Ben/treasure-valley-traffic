"""Tests for deploy/scratch/lib.sh's memory admission: what a heavy job holding heavy.lock counts for.

    python3 -m unittest discover -s deploy/scratch/tests

Runs lib.sh's functions in bash with a scratch root and a work folder of its own. Needs Linux (/proc, bash 4):
the server's. Skipped elsewhere.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "lib.sh")


@unittest.skipUnless(os.path.isdir("/proc/self") and shutil.which("bash"), "needs Linux (/proc) and bash")
class OtherHeavy(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.work = os.path.join(self.dir, "work")
        self.root = os.path.join(self.dir, "scratch")
        os.makedirs(self.work)
        os.makedirs(os.path.join(self.root, "slots"))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def other(self, **env):
        e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "WORK": self.work, "SCRATCH_ROOT": self.root,
             "HEAVY_OTHER_MB": "6144"}
        e.update(env)
        p = subprocess.run(["bash", "-c", f'. "{LIB}"; other_heavy_mb'], env=e, capture_output=True, text=True,
                           check=True)
        return int(p.stdout.strip())

    def holder(self, hid, pid):
        with open(os.path.join(self.work, "heavy.id"), "w") as f:
            f.write(f"{hid} {pid}\n")

    def test_no_heavy_job(self):
        self.assertEqual(self.other(), 0)

    def test_a_heavy_job_outside_scratch_counts(self):
        self.holder("1792115761-376930", os.getpid())
        self.assertEqual(self.other(), 6144)

    def test_a_heavy_scratch_job_doesnt_count_its_own_heavy(self):
        # run.sh inside heavy, before it has its slot: the holder is its own heavy (heavy.id names HEAVY_ID)
        self.holder("1792115761-376930", os.getpid())
        self.assertEqual(self.other(SCRATCH_IN_HEAVY="1", HEAVY_ID="1792115761-376930"), 0)
        self.assertEqual(self.other(SCRATCH_IN_HEAVY="1", HEAVY_ID="1792115000-111111"), 6144)   # another's
        self.assertEqual(self.other(HEAVY_ID="1792115761-376930"), 6144)                        # not a scratch job

    def test_a_dead_holder_counts_nothing(self):
        p = subprocess.Popen(["true"])
        p.wait()
        self.holder("1792115761-376930", p.pid)
        self.assertEqual(self.other(), 0)


if __name__ == "__main__":
    unittest.main()
