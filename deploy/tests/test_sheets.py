"""Tests for deploy/bin/sheets: the container's caps and mounts, what may be mounted, the quiet-hours rule (heavy's,
through heavy_harness's clock), and the command line. No docker needed.

    python3 -m unittest discover -s deploy/tests
"""
import contextlib
import datetime as dt
import importlib.machinery
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heavy_harness  # noqa: E402

SHEETS = os.path.join(os.path.dirname(HERE), "bin", "sheets")
REPO = os.path.dirname(os.path.dirname(HERE))
heavy = heavy_harness.load("heavy_for_sheets_test")
TZ = heavy.TZ


def load():
    loader = importlib.machinery.SourceFileLoader("sheets_under_test", SHEETS)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def boise(text):
    return dt.datetime.fromisoformat(text).replace(tzinfo=TZ)


def both(t, rolling=False, age=10):
    def st(cadence):
        return {"version": 1, "cadence_s": cadence, "heartbeat": t.timestamp() - age, "rolling_up": rolling}
    return [("key_cameras.json", st(50)), ("regional-cameras.json", st(600))]


class SheetsTest(unittest.TestCase):
    def setUp(self):
        self.sh = load()
        self.root = os.path.realpath(tempfile.mkdtemp())
        r = self.root
        for d in ("work/scratch/archive/tvt/soils/export", "work/scratch/secrets", "work/bin", "work/f8/in",
                  "work/landcover/naip2025", "work/landcover/naip2023", "archive/trees", "archive/osm",
                  "private/data/boise-trees-2026-10-08", "tiles", "work/sheets.slots"):
            os.makedirs(os.path.join(r, d))
        sh = self.sh
        sh.WORK, sh.TILES, sh.NAIP = f"{r}/work", f"{r}/tiles", f"{r}/work/landcover"
        sh.PROD_ARCHIVE, sh.PRIVATE, sh.SHEETS = f"{r}/archive", f"{r}/private", f"{r}/private/sheets"
        sh.SCRATCH_ARCHIVE, sh.SLOT_DIR = f"{r}/work/scratch/archive", f"{r}/work/sheets.slots"

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_main(self, argv, **kw):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.sh.main(argv, **kw)
        return code, out.getvalue(), err.getvalue()

    def test_the_container_is_capped_offline_and_reads_only(self):
        r = self.root
        cmd = self.sh.command("/srv/x", "p7", f"{r}/work/scratch/archive/tvt", [(f"{r}/work/f8/in", "f8")],
                              ["--places", "cameras"], uid=1001, gid=1001, name="n")
        s = " ".join(cmd)
        for want in ("--memory 1g", "--memory-swap 1g", "--cpus 1", "--network none", "--read-only",
                     "--user 1001:1001", "-v /srv/x:/repo:ro", f"-v {r}/work/scratch/archive/tvt:/srv/archive:ro",
                     f"-v {r}/tiles:/srv/tiles:ro", f"-v {r}/work/landcover/naip2025:/srv/naip/naip2025:ro",
                     f"-v {r}/work/f8/in:/in/f8:ro", f"-v {r}/private/sheets/p7:/out ",
                     "tvt-worker python -m basemap.sheets.sheet draw --out /out --places cameras"):
            self.assertIn(want, s)
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
        self.assertEqual([m for m in mounts if not m.endswith(":ro")], [f"{r}/private/sheets/p7:/out"])

    def test_what_may_be_mounted(self):
        r = self.root
        ok = [f"{r}/work/f8/in", f"{r}/work/scratch/archive/tvt", f"{r}/archive/osm"]
        for p in ok:
            self.assertEqual(self.sh.check_input(p), os.path.realpath(p))
        bad = {f"{r}/private/data/boise-trees-2026-10-08": "never mounted",
               f"{r}/work/scratch/secrets": "never mounted",
               f"{r}/work/scratch": "only a database's archive",
               f"{r}/work/scratch/archive": "only a database's archive",
               f"{r}/work/bin": "tools and state",
               f"{r}/archive/trees": "City's inventory",
               f"{r}/tiles": "only folders under",
               f"{r}/work": "only folders under",
               f"{r}/work/nope": "no such folder"}
        for p, msg in bad.items():
            with self.assertRaisesRegex(self.sh.Refused, msg, msg=p):
                self.sh.check_input(p)
        os.symlink(f"{r}/private/data", f"{r}/work/f8/link")       # a link is followed before it's checked
        with self.assertRaisesRegex(self.sh.Refused, "never mounted"):
            self.sh.check_input(f"{r}/work/f8/link")

    def test_quiet_hours_wait_for_the_rollup(self):
        may = self.sh.may_start
        t = boise("2026-10-11 14:00")
        self.assertIsNone(may(heavy, t, both(t), None, 60))
        t = boise("2026-10-11 23:30")
        self.assertIn("only unit tests and scratch queries", may(heavy, t, both(t), None, 60))
        t = boise("2026-10-11 00:02")
        self.assertIn("only unit tests", may(heavy, t, both(t), None, 60))
        t = boise("2026-10-11 00:30")
        self.assertIn("still rolling up", may(heavy, t, both(t, rolling=True), None, 60))
        t = boise("2026-10-11 02:30")
        self.assertIn("still rolling up", may(heavy, t, both(t, rolling=True), None, 60))
        self.assertIsNone(may(heavy, t, both(t), None, 60))           # finished: light runs may go
        t = boise("2026-10-11 05:50")
        self.assertIsNone(may(heavy, t, both(t), None, 60))

    def test_a_planned_restart(self):
        t = boise("2026-10-11 14:00")
        self.assertIn("restart is planned at 2026-10-11 14:45",
                      self.sh.may_start(heavy, t, both(t), ("restart", boise("2026-10-11 14:45")), 60))
        self.assertIsNone(self.sh.may_start(heavy, t, both(t), ("restart", boise("2026-10-11 16:00")), 60))
        self.assertIn("no time", self.sh.may_start(heavy, t, both(t), ("soon", None), 60))

    def test_the_command_line(self):
        r = self.root
        code, out, err = self.run_main(["-C", REPO, "--pkg", "f8", "--in", f"{r}/work/f8/in", "--dry-run", "--",
                                        "--places", "c"])
        self.assertEqual(code, 0, err)
        self.assertIn(f"-v {r}/work/f8/in:/in/in:ro", out)
        self.assertIn("draw --out /out --places c", out)
        for argv, msg in ((["-C", REPO, "--", "--places", "c"], "--pkg"),
                          (["-C", REPO, "--pkg", "F8!"], "--pkg"),
                          (["-C", self.root, "--pkg", "f8"], "not a checkout"),
                          (["-C", REPO, "--pkg", "f8", "--db", "tvt_s1"], "no archive"),
                          (["-C", REPO, "--pkg", "f8", "--", "--out", "/tmp"], "--out is given"),
                          (["-C", REPO, "--pkg", "f8", "--in", f"{r}/private/data"], "never mounted"),
                          (["-C", REPO, "--pkg", "f8", "--in", f"{r}/work/f8/in:a/b"], "plain, unused name"),
                          (["-C", REPO, "--pkg", "f8", "--timeout", "x"], "minutes")):
            code, _out, err = self.run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn(msg, err, argv)

    def test_refused_at_night_and_on_low_disk(self):
        t = boise("2026-10-11 23:40")
        heavy.read_statuses = lambda *_a: both(t)
        heavy.maintenance = lambda *_a: None
        code, _out, err = self.run_main(["-C", REPO, "--pkg", "f8"], heavy=heavy, now=t, free_gb=lambda _p: 50)
        self.assertEqual(code, 75)
        self.assertIn("not now", err)
        t = boise("2026-10-11 14:00")
        heavy.read_statuses = lambda *_a: both(t)
        code, _out, err = self.run_main(["-C", REPO, "--pkg", "f8"], heavy=heavy, now=t, free_gb=lambda _p: 12.5)
        self.assertEqual(code, 73)
        self.assertIn("12.5 GB free", err)

    def test_the_output_folder_is_private(self):
        path = self.sh.out_folder("p7")
        self.assertEqual(path, f"{self.root}/private/sheets/p7")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o750)

    def test_slots(self):
        fds = [self.sh.take_slot("a", 0), self.sh.take_slot("b", 0)]
        self.assertTrue(all(fd is not None for fd in fds))
        self.assertIsNone(self.sh.take_slot("c", 0))
        os.close(fds[0])
        fd = self.sh.take_slot("c", 1)
        self.assertIsNotNone(fd)
        os.close(fd)
        os.close(fds[1])


if __name__ == "__main__":
    unittest.main()
