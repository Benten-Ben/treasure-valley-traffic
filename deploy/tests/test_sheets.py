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
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heavy_harness  # noqa: E402

SHEETS = os.path.join(os.path.dirname(HERE), "bin", "sheets")
REPO = os.path.dirname(os.path.dirname(HERE))
heavy = heavy_harness.load("heavy_for_sheets_test")
TZ = heavy.TZ
frees_last = [50.0]                  # what the fake free_gb gives once its list runs out


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
        for d in ("work/scratch/archive/tvt/soils/export", "work/scratch/archive/tvt/soils/prepared",
                  "work/scratch/archive/tvt/trees/export", "work/scratch/secrets", "work/bin", "work/f8/in",
                  "work/landcover/naip2025", "work/landcover/naip2023", "work/landcover/lidar/c",
                  "work/landcover/trees-out/c-20261008T1842", "work/landcover/exp", "archive/trees/builds",
                  "archive/trees/export", "archive/osm/export", "archive/osm/inbox", "archive/cameras",
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
        archive = self.sh.archive_mounts(f"{r}/work/scratch/archive/tvt", "--db")
        cmd = self.sh.command("/srv/x", "p7", archive, [(f"{r}/work/f8/in", "f8")],
                              ["--places", "cameras"], uid=1001, gid=1001, name="n")
        s = " ".join(cmd)
        for want in ("--memory 1g", "--memory-swap 1g", "--cpus 1", "--network none", "--read-only",
                     "--user 1001:1001", "-v /srv/x:/repo:ro", "-e TVT_SHEETS_MIN_FREE_GB=11",
                     "--mount type=tmpfs,destination=/srv/archive,tmpfs-size=1m,tmpfs-mode=0555",
                     f"-v {r}/work/scratch/archive/tvt/soils/export:/srv/archive/soils/export:ro",
                     f"-v {r}/tiles:/srv/tiles:ro", f"-v {r}/work/landcover/naip2025:/srv/naip/naip2025:ro",
                     f"-v {r}/work/f8/in:/in/f8:ro", f"-v {r}/private/sheets/p7:/out ",
                     "tvt-worker python -m basemap.sheets.sheet draw --out /out --places cameras"):
            self.assertIn(want, s)
        mounts = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-v"]
        self.assertEqual([m for m in mounts if not m.endswith(":ro")], [f"{r}/private/sheets/p7:/out"])
        self.assertNotIn("prepared", s)                                # only the exports

    def test_an_archive_is_mounted_one_plugins_exports_at_a_time(self):
        r = self.root
        prod = self.sh.archive_mounts(f"{r}/archive", "--archive")
        self.assertEqual(prod, [(f"{r}/archive/osm/export", "/srv/archive/osm/export")])   # never trees/
        scratch = self.sh.archive_mounts(f"{r}/work/scratch/archive/tvt", "--db")
        self.assertEqual([m for _src, m in scratch], ["/srv/archive/soils/export", "/srv/archive/trees/export"])
        # a plugin folder that's a link into production's trees archive is skipped, not followed
        os.makedirs(f"{r}/work/f8/archive")
        os.symlink(f"{r}/archive/trees", f"{r}/work/f8/archive/roads")
        os.makedirs(f"{r}/work/f8/archive/farm/export")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            mine = self.sh.archive_mounts(f"{r}/work/f8/archive", "--archive")
        self.assertEqual(mine, [(f"{r}/work/f8/archive/farm/export", "/srv/archive/farm/export")])
        self.assertIn("roads's exports aren't mounted", err.getvalue())
        for bad, msg in ((f"{r}/archive/trees", "trees archive"), (f"{r}/work/landcover", "land-cover"),
                         (f"{r}/private", "never mounted"), (f"{r}/work/nope", "no such folder")):
            with self.assertRaisesRegex(self.sh.Refused, msg, msg=bad):
                self.sh.archive_mounts(bad, "--archive")

    def test_what_may_be_mounted(self):
        r = self.root
        ok = [f"{r}/work/f8/in", f"{r}/work/scratch/archive/tvt", f"{r}/archive/osm", f"{r}/work/landcover/lidar/c",
              f"{r}/work/landcover/naip2025", f"{r}/work/scratch/archive/tvt/trees/export"]
        for p in ok:
            self.assertEqual(self.sh.check_input(p), os.path.realpath(p))
        bad = {f"{r}/private/data/boise-trees-2026-10-08": "never mounted",
               f"{r}/work/scratch/secrets": "never mounted",
               f"{r}/work/scratch": "only a database's archive",
               f"{r}/work/scratch/archive": "only a database's archive",
               f"{r}/work/bin": "tools and state",
               f"{r}/archive/trees": "City's inventory",
               f"{r}/archive/trees/builds": "City's inventory",
               f"{r}/archive": "nor a folder holding it",               # production's archive holds trees/
               f"{r}/work/landcover/trees-out": "land-cover spike",
               f"{r}/work/landcover/trees-out/c-20261008T1842": "land-cover spike",
               f"{r}/work/landcover/exp": "land-cover spike",
               f"{r}/work/landcover": "land-cover spike",
               f"{r}/tiles": "only folders under",
               f"{r}/work": "only folders under",
               f"{r}/work/nope": "no such folder"}
        for p, msg in bad.items():
            with self.assertRaisesRegex(self.sh.Refused, msg, msg=p):
                self.sh.check_input(p)
        os.symlink(f"{r}/private/data", f"{r}/work/f8/link")       # a link is followed before it's checked
        with self.assertRaisesRegex(self.sh.Refused, "never mounted"):
            self.sh.check_input(f"{r}/work/f8/link")
        os.symlink(f"{r}/work/landcover/trees-out", f"{r}/work/f8/link2")
        with self.assertRaisesRegex(self.sh.Refused, "land-cover spike"):
            self.sh.check_input(f"{r}/work/f8/link2")

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
        t = boise("2026-10-11 06:20")                                 # a roll-up running late holds day runs
        self.assertIn("still going", may(heavy, t, both(t, rolling=True), None, 60))

    def test_a_day_run_ends_by_2315(self):
        limit, may = self.sh.run_limit, self.sh.may_start
        t = boise("2026-10-11 14:00")
        self.assertEqual(limit(heavy, t, 60), 60)
        t = boise("2026-10-11 22:45")
        self.assertEqual(limit(heavy, t, 60), 30)                    # cut to 23:15
        self.assertIsNone(may(heavy, t, both(t), None, 60))
        t = boise("2026-10-11 23:14")
        self.assertIn("under 2 min before 23:15", may(heavy, t, both(t), None, 60))
        self.assertIsNone(may(heavy, t, both(t), None, 0.5))          # a short run still fits
        t = boise("2026-10-11 02:30")
        self.assertEqual(limit(heavy, t, 60), 60)                    # at night, once the roll-up is done
        # the restart check uses the cut time: a restart at 23:40 is past a run cut at 23:15
        t = boise("2026-10-11 22:45")
        self.assertIsNone(may(heavy, t, both(t), ("restart", boise("2026-10-11 23:40")), 60))

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
        code, out, err = self.run_main(["-C", REPO, "--pkg", "f8", "--archive", f"{r}/archive", "--dry-run"])
        self.assertEqual(code, 0, err)
        self.assertIn(f"-v {r}/archive/osm/export:/srv/archive/osm/export:ro", out)
        self.assertNotIn("/trees", out)
        for argv, msg in ((["-C", REPO, "--", "--places", "c"], "--pkg"),
                          (["-C", REPO, "--pkg", "F8!"], "--pkg"),
                          (["-C", self.root, "--pkg", "f8"], "not a checkout"),
                          (["-C", REPO, "--pkg", "f8", "--db", "tvt_s1"], "no archive"),
                          (["-C", REPO, "--pkg", "f8", "--", "--out", "/tmp"], "--out is given"),
                          (["-C", REPO, "--pkg", "f8", "--in", f"{r}/private/data"], "never mounted"),
                          (["-C", REPO, "--pkg", "f8", "--in", f"{r}/archive"], "trees archive"),
                          (["-C", REPO, "--pkg", "f8", "--in", f"{r}/work/landcover/trees-out"], "land-cover"),
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

    def run_fake(self, t, argv, frees, codes=()):
        """main() with a fake docker process: wait() times out until codes run out; returns (code, err, stops)."""
        codes, stops = list(codes), []

        class Proc:
            def __init__(self, cmd):
                self.cmd = cmd

            def wait(self, timeout=None):
                if timeout is None:
                    return 0
                if codes:
                    return codes.pop(0)
                raise subprocess.TimeoutExpired("docker", timeout)
        heavy.read_statuses = lambda *_a: both(t)
        heavy.maintenance = lambda *_a: None
        frees = iter(frees)
        with mock.patch.object(self.sh.subprocess, "Popen", Proc), \
                mock.patch.object(self.sh, "stop", lambda name, grace=10: stops.append(name)):
            code, _out, err = self.run_main(["-C", REPO, "--pkg", "f8", "--wait", "0"] + argv, heavy=heavy, now=t,
                                            free_gb=lambda _p: next(frees, frees_last[0]), mem=lambda: 8000)
        return code, err, stops

    def test_the_run_is_stopped_under_the_floor_at_its_time_and_says_when_killed(self):
        global frees_last
        t = boise("2026-10-11 14:00")
        frees_last[0] = 10.5
        code, err, stops = self.run_fake(t, [], [50.0, 50.0])         # 50 GB to start, then 10.5
        self.assertEqual(code, 123, err)
        self.assertIn("10.5 GB free on /, under 11 GB", err)
        self.assertEqual(len(stops), 1)
        frees_last[0] = 50.0
        code, err, stops = self.run_fake(t, ["--timeout", "0.002"], [])
        self.assertEqual(code, 124, err)
        self.assertIn("are up", err)
        code, err, _stops = self.run_fake(t, [], [], codes=[137])
        self.assertEqual(code, 137)
        self.assertIn("was killed (137", err)
        code, err, _stops = self.run_fake(t, [], [], codes=[0])
        self.assertEqual(code, 0, err)
        self.assertIn("at most 60 min", err)
        t = boise("2026-10-11 22:45")                                 # cut to end by 23:15
        code, err, _stops = self.run_fake(t, [], [], codes=[0])
        self.assertIn("at most 30 min", err)

    def test_the_output_folder_is_private(self):
        path = self.sh.out_folder("p7")
        self.assertEqual(path, f"{self.root}/private/sheets/p7")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o750)

    def test_memory(self):
        self.assertEqual(self.sh.memory_ok(lambda: 8000), (True, ""))
        ok, why = self.sh.memory_ok(lambda: 3500)
        self.assertFalse(ok)
        self.assertIn("3500 MB available, a run needs 1024 MB plus 3072 MB", why)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIsNone(self.sh.take_slot("a", 0, mem=lambda: 3500))
        self.assertIn("memory: 3500 MB", err.getvalue())
        fd = self.sh.take_slot("a", 0, mem=lambda: 8000)
        self.assertIsNotNone(fd)
        os.close(fd)
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("MemTotal:       16375612 kB\nMemAvailable:   13777912 kB\n")
        self.assertEqual(self.sh.mem_available_mb(f.name), 13454)
        os.unlink(f.name)

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
