"""Tests for deploy/scratch/scratchq.py: the light-job rules (quiet hours, the 23:15 stop, a
planned restart) on top of F7's heavy, and which folders a scratch job may mount.

    python3 -m unittest discover -s deploy/scratch/tests

They load heavy from deploy/bin/heavy (F7's), or from TVT_HEAVY (e.g. the copy installed on the
VM); without it they fail rather than skip.
"""
import datetime as dt
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SCRATCH))
sys.path.insert(0, SCRATCH)
import scratchq  # noqa: E402

HEAVY = os.environ.get("TVT_HEAVY") or os.path.join(REPO, "deploy", "bin", "heavy")
h = None


def setUpModule():
    global h, TZ
    if not os.path.isfile(HEAVY):
        raise RuntimeError(f"the scratch rules use F7's heavy, and there's none at {HEAVY}: "
                           "set TVT_HEAVY to a copy of deploy/bin/heavy")
    h = scratchq.load_heavy(HEAVY)
    h.boot_time = lambda: None          # no leftover-restart logic from this machine's boot
    TZ = h.TZ


def boise(text):
    return dt.datetime.fromisoformat(text).replace(tzinfo=h.TZ)


def status(t, rolling=False, cadence=50, age=10):
    beat = t.timestamp() - age
    return {"version": 1, "cadence_s": cadence, "heartbeat": beat, "rolling_up": rolling, "paused_low_disk": False,
            "heartbeat_at": dt.datetime.fromtimestamp(beat, dt.timezone.utc).isoformat()}


def both(t, rolling=(False, False), ages=(10, 10)):
    return [("key_cameras.json", status(t, rolling[0], 50, ages[0])),
            ("regional-cameras.json", status(t, rolling[1], 600, ages[1]))]


def light(t, mem=2048, runtime=10, limit=120, statuses=None, maint=None):
    return scratchq.light_job(h, t, mem, runtime, limit, both(t) if statuses is None else statuses, maint)


class QuietHours(unittest.TestCase):
    def test_quiet_hours_run_from_quarter_past_eleven_to_six(self):
        for clock in ("23:15", "23:59", "00:00", "03:00", "05:59"):
            self.assertTrue(scratchq.quiet(h, boise(f"2026-10-11 {clock}")), clock)
        for clock in ("06:00", "12:00", "23:14"):
            self.assertFalse(scratchq.quiet(h, boise(f"2026-10-11 {clock}")), clock)

    def test_one_gigabyte_jobs_run_in_quiet_hours(self):
        t = boise("2026-10-11 23:30")
        stop, _ = light(t, mem=1024, statuses=both(t, rolling=(True, True)))
        self.assertEqual(stop, t + dt.timedelta(minutes=120))

    def test_bigger_jobs_wait_for_the_roll_up(self):
        for clock, statuses in (("23:30", None), ("00:03", None), ("01:00", "rolling"), ("01:00", "stale")):
            t = boise(f"2026-10-12 {clock}")
            s = {None: both(t), "rolling": both(t, rolling=(False, True)),
                 "stale": both(t, ages=(10, 99999))}[statuses]
            with self.assertRaisesRegex(scratchq.Refused, "quiet hours"):
                light(t, mem=2048, statuses=s)

    def test_bigger_jobs_run_once_the_roll_up_has_finished(self):
        t = boise("2026-10-12 02:30")
        stop, _ = light(t, mem=2048)
        self.assertEqual(stop, t + dt.timedelta(minutes=120))

    def test_a_job_over_one_gigabyte_stops_at_quarter_past_eleven(self):
        t = boise("2026-10-11 22:00")
        stop, _ = light(t, mem=2048, runtime=30)
        self.assertEqual(stop, boise("2026-10-11 23:15"))
        with self.assertRaisesRegex(scratchq.Refused, "doesn't fit"):
            light(t, mem=2048, runtime=90)
        stop, _ = light(t, mem=1024, runtime=90)            # 1 GB: no 23:15 stop
        self.assertEqual(stop, boise("2026-10-12 00:00"))

    def test_the_limit_stops_a_light_job(self):
        t = boise("2026-10-11 09:00")
        self.assertEqual(light(t, limit=30)[0], boise("2026-10-11 09:30"))


class Restarts(unittest.TestCase):
    def test_a_job_stops_ten_minutes_before_a_planned_restart(self):
        t = boise("2026-10-11 12:00")
        stop, notes = light(t, runtime=10, limit=120, maint=("restart: 14:00", boise("2026-10-11 14:00")))
        self.assertEqual(stop, boise("2026-10-11 13:50"))
        self.assertTrue(any("13:50" in n for n in notes))

    def test_a_job_that_doesnt_fit_before_the_restart_is_refused(self):
        t = boise("2026-10-11 12:00")
        with self.assertRaisesRegex(scratchq.Refused, "doesn't fit"):
            light(t, runtime=115, maint=("restart 14:00", boise("2026-10-11 14:00")))

    def test_an_unreadable_note_refuses_jobs_that_may_run_over_ten_minutes(self):
        t = boise("2026-10-11 12:00")
        with self.assertRaisesRegex(scratchq.Refused, "--limit 120"):
            light(t, runtime=5, limit=120, maint=("sometime soon", None))
        stop, notes = light(t, runtime=5, limit=10, maint=("sometime soon", None))
        self.assertEqual(stop, t + dt.timedelta(minutes=10))
        self.assertTrue(notes)

    def test_heavys_reading_of_the_note_is_used_and_a_leftover_note_is_ignored(self):
        with tempfile.TemporaryDirectory() as work:
            with open(os.path.join(work, "MAINTENANCE"), "w") as f:
                f.write("VM restart for the cold drive\nrestart: 2026-10-11 14:00\n")
            t = boise("2026-10-11 12:00")
            maint = h.maintenance(t, work)
            self.assertEqual(maint[1], boise("2026-10-11 14:00"))
            self.assertEqual(scratchq.restart_cut(h, t, maint), boise("2026-10-11 13:50"))
            booted = boise("2026-10-11 14:02").timestamp()
            h.boot_time = lambda: booted                # the VM has restarted since: the note is left over
            try:
                self.assertIsNone(h.maintenance(boise("2026-10-11 14:30"), work))
            finally:
                h.boot_time = lambda: None
        self.assertIsNone(scratchq.restart_cut(h, t, None))


class Mounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = os.path.realpath(self.tmp.name)
        self.p = lambda *a: os.path.join(r, *a)
        for d in ("work/bin", "work/e2e/slots", "work/worker-test", "work/sources/cdl", "work/landcover/run1",
                  "work/scratch/archive/tvt/osm", "work/scratch/secrets", "work/scratch/trees/s1", "work/scratch/bin",
                  "cold/vm/scratch/20261011T0839Z", "cold/vm/lidar-work", "cold/lidar/laz", "prod/osm",
                  "srv/private/secrets", "srv/plugins-private/x"):
            os.makedirs(self.p(d))
        open(self.p("work", "heavy.lock"), "w").close()
        os.symlink(self.p("work/scratch/secrets"), self.p("work/landcover/sneaky"))
        self.roots = {"work": self.p("work"), "scratch_root": self.p("work/scratch"), "prod_archive": self.p("prod"),
                      "cold_mount": self.p("cold"), "dump_root": self.p("cold/vm/scratch"),
                      "private": [self.p("srv/private"), self.p("srv/plugins-private")]}

    def tearDown(self):
        self.tmp.cleanup()

    def ok(self, src, dst="/mnt/in", ro=False):
        spec = f"{self.p(src)}:{dst}" + (":ro" if ro else "")
        return scratchq.check_mount(spec, self.roots)

    def refused(self, src, dst="/mnt/in", ro=False, why=""):
        with self.assertRaisesRegex(scratchq.Refused, why):
            self.ok(src, dst, ro)

    def test_work_folders_mount_read_write(self):
        self.assertEqual(self.ok("work/landcover"), (self.p("work/landcover"), "/mnt/in", False))
        self.assertEqual(self.ok("work/landcover/run1", ro=True)[2], True)
        self.assertEqual(self.ok("cold/vm/lidar-work")[0], self.p("cold/vm/lidar-work"))

    def test_read_only_places(self):
        for src in ("work/sources/cdl", "prod/osm", "cold/lidar/laz", "work/scratch/archive/tvt"):
            self.assertTrue(self.ok(src, ro=True)[2], src)
            self.refused(src, why="read-only only")

    def test_the_tools_locks_and_secrets_never_mount(self):
        for src in ("work/bin", "work/e2e", "work/e2e/slots", "work/worker-test", "work/scratch", "work/scratch/bin",
                    "work/scratch/secrets", "work/scratch/trees/s1", "work/scratch/archive"):
            self.refused(src)
            self.refused(src, ro=True)

    def test_parents_of_protected_folders_never_mount(self):
        for src in ("work", ".", "cold", "cold/vm", "srv"):
            self.refused(src)
            self.refused(src, ro=True)
        self.refused("/", ro=True)

    def test_dumps_and_private_files_never_mount(self):
        for src in ("cold/vm/scratch", "cold/vm/scratch/20261011T0839Z", "srv/private", "srv/private/secrets",
                    "srv/plugins-private/x"):
            self.refused(src, ro=True)

    def test_symlinks_are_resolved_first(self):
        self.refused("work/landcover/sneaky", ro=True, why="secrets")

    def test_only_folders(self):
        self.refused("work/heavy.lock", ro=True, why="no such folder")
        self.refused("work/nothing-here", why="no such folder")

    def test_the_containers_own_paths_stay_its_own(self):
        for dst in ("/repo", "/repo/data", "/srv/archive", "/srv/archive/osm", "/tmp", "/", self.p("cold")):
            self.refused("work/landcover", dst=dst)
        for spec in ("relative:x", f"{self.p('work/landcover')}", f"{self.p('work/landcover')}:/x:rw",
                     f"{self.p('work/landcover')}:/x,y"):
            with self.assertRaises(scratchq.Refused):
                scratchq.check_mount(spec, self.roots)


class CommandLine(unittest.TestCase):
    def test_light_prints_the_stop_time_as_an_epoch(self):
        import contextlib
        import io
        out = io.StringIO()
        saved = h.OFFSET, h.read_statuses, h.maintenance
        t = boise("2026-10-11 12:00")
        h.OFFSET = t.timestamp() - dt.datetime.now().timestamp()
        h.read_statuses = lambda *_a: both(h.now())
        h.maintenance = lambda *_a: None
        try:
            with contextlib.redirect_stdout(out):
                code = scratchq.main(["light", "2048", "10", "30"], heavy=h)
        finally:
            h.OFFSET, h.read_statuses, h.maintenance = saved
        self.assertEqual(code, 0)
        self.assertAlmostEqual(int(out.getvalue()), dt.datetime.now().timestamp() + 30 * 60, delta=5)

    def test_unknown_questions_are_usage_errors(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(scratchq.main(["light", "x"], heavy=h), 2)
        self.assertIn("unknown question", err.getvalue())


if __name__ == "__main__":
    unittest.main()
