"""Tests for deploy/bin/heavy: the rules on their own, and dry and real runs of the wrapper
against a scratch work folder, fake capture status files and a fake clock (through
heavy_harness.py: heavy itself has no test hooks).

    python3 -m unittest discover -s deploy/tests

The docker case runs only where docker and the debian:trixie-slim image are there (the VM).
"""
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heavy_harness  # noqa: E402

HEAVY = heavy_harness.HEAVY
HARNESS = os.path.join(HERE, "heavy_harness.py")
heavy = heavy_harness.load()
TZ = heavy.TZ


def boise(text):
    return dt.datetime.fromisoformat(text).replace(tzinfo=TZ)


def status(t, rolling=False, cadence=50, age=10):
    return {"version": 1, "cadence_s": cadence, "heartbeat": t.timestamp() - age, "rolling_up": rolling,
            "paused_low_disk": False}


def both(t, rolling=(False, False), ages=(10, 10)):
    return [("key_cameras.json", status(t, rolling[0], 50, ages[0])),
            ("regional-cameras.json", status(t, rolling[1], 600, ages[1]))]


class Windows(unittest.TestCase):
    def test_the_day_window_runs_from_six_to_quarter_past_eleven(self):
        for clock in ("06:00", "12:00", "23:14"):
            name, close = heavy.window(boise(f"2026-10-11 {clock}"), [])
            self.assertEqual((name, close), ("day", boise("2026-10-11 23:15")))
        for clock in ("05:59", "23:15", "23:59", "00:00", "00:04"):
            with self.assertRaises(heavy.Refused) as err:
                heavy.window(boise(f"2026-10-11 {clock}"), both(boise(f"2026-10-11 {clock}")))
            self.assertTrue(err.exception.waitable)

    def test_the_night_window_opens_once_both_services_finished_rolling_up(self):
        t = boise("2026-10-11 02:30")
        self.assertEqual(heavy.window(t, both(t)), ("night", boise("2026-10-11 05:45")))
        for rolling in ((True, False), (False, True)):
            with self.assertRaisesRegex(heavy.Refused, "still rolling up"):
                heavy.window(t, both(t, rolling))

    def test_the_night_window_needs_a_check_after_five_past_midnight(self):
        # regional reports every 10 min: at 00:08 its last status can't show a check after 00:05
        t = boise("2026-10-11 00:08")
        with self.assertRaisesRegex(heavy.Refused, "regional-cameras hasn't reported"):
            heavy.window(t, both(t))
        t = boise("2026-10-11 00:20")
        self.assertEqual(heavy.window(t, both(t))[0], "night")

    def test_stale_or_missing_status_keeps_the_night_closed(self):
        t = boise("2026-10-11 03:00")
        with self.assertRaisesRegex(heavy.Refused, "stale"):
            heavy.window(t, both(t, ages=(10, 3 * 600 + 120)))
        with self.assertRaisesRegex(heavy.Refused, "can't be read"):
            heavy.window(t, [("key_cameras.json", None), both(t)[1]])

    def test_the_night_window_closes_at_quarter_to_six(self):
        t = boise("2026-10-11 05:45")
        with self.assertRaisesRegex(heavy.Refused, "closed at 05:45"):
            heavy.window(t, both(t))

    def test_a_roll_up_still_going_after_six_holds_day_jobs(self):
        t = boise("2026-10-11 06:30")
        with self.assertRaisesRegex(heavy.Refused, "still going") as err:
            heavy.window(t, both(t, (True, False)))
        self.assertTrue(err.exception.waitable)
        # a stale "rolling_up" (a stopped service) doesn't hold the day
        self.assertEqual(heavy.window(t, both(t, (True, False), ages=(1000, 10)))[0], "day")


class Deadlines(unittest.TestCase):
    def plan(self, now, deadline, runtime, statuses=None, maint=None):
        t = boise(now)
        d = heavy.resolve_deadline(t, heavy.parse_hhmm(deadline))
        return heavy.plan(t, d, runtime, statuses if statuses is not None else both(t), maint)

    def test_a_job_that_fits_gets_its_deadline(self):
        self.assertEqual(self.plan("2026-10-11 14:00", "15:30", 60), ("day", boise("2026-10-11 15:30")))
        self.assertEqual(self.plan("2026-10-11 14:00", "23:15", 0)[1], boise("2026-10-11 23:15"))

    def test_past_the_deadline_it_refuses(self):
        with self.assertRaisesRegex(heavy.Refused, "past the deadline") as err:
            self.plan("2026-10-11 14:00", "13:59", 1)
        self.assertEqual(err.exception.code, heavy.EX_LATER)
        self.assertFalse(err.exception.waitable)

    def test_a_runtime_that_doesnt_fit_is_refused(self):
        with self.assertRaisesRegex(heavy.Refused, "don't fit"):
            self.plan("2026-10-11 22:30", "23:15", 46)
        self.plan("2026-10-11 22:30", "23:15", 45)

    def test_a_deadline_past_the_window_is_a_usage_error(self):
        with self.assertRaises(heavy.Refused) as err:
            self.plan("2026-10-11 22:00", "23:30", 10)
        self.assertEqual(err.exception.code, heavy.EX_USAGE)
        t = "2026-10-11 02:00"
        with self.assertRaises(heavy.Refused) as err:
            self.plan(t, "06:30", 10)
        self.assertIn("05:45", str(err.exception))

    def test_late_evening_an_early_deadline_means_the_coming_night(self):
        t = boise("2026-10-11 23:30")
        self.assertEqual(heavy.resolve_deadline(t, heavy.parse_hhmm("05:45")), boise("2026-10-12 05:45"))
        self.assertEqual(heavy.resolve_deadline(t, heavy.parse_hhmm("22:00")), boise("2026-10-11 22:00"))
        self.assertEqual(heavy.resolve_deadline(boise("2026-10-11 14:00"), heavy.parse_hhmm("05:45")),
                         boise("2026-10-11 05:45"))

    def test_bad_deadlines_are_usage_errors(self):
        for text in ("24:00", "7", "7:5", "", "noon"):
            with self.assertRaises(heavy.Refused) as err:
                heavy.parse_hhmm(text)
            self.assertEqual(err.exception.code, heavy.EX_USAGE)
        self.assertEqual(heavy.parse_hhmm("7:05"), dt.time(7, 5))

    def test_a_planned_restart_brings_the_deadline_forward(self):
        t = boise("2026-10-11 14:00")
        maint = ("VM restart 2026-10-11 15:00 for the cold drive", boise("2026-10-11 15:00"))
        self.assertEqual(self.plan("2026-10-11 14:00", "18:00", 30, maint=maint)[1], boise("2026-10-11 14:50"))
        with self.assertRaisesRegex(heavy.Refused, "don't fit"):
            self.plan("2026-10-11 14:00", "18:00", 60, maint=maint)
        with self.assertRaisesRegex(heavy.Refused, "no one time I can read"):
            self.plan("2026-10-11 14:00", "18:00", 30, maint=("restart soon", None))
        self.assertEqual(self.plan("2026-10-11 14:00", "14:30", 10, maint=maint)[1], boise("2026-10-11 14:30"))
        del t

    def test_maintenance_times_are_read_from_the_text(self):
        t = boise("2026-10-11 14:00")
        self.assertEqual(heavy.parse_maintenance("restart at 2026-10-11 16:30 (A1)", t), boise("2026-10-11 16:30"))
        self.assertEqual(heavy.parse_maintenance("restart 2026-10-11T22:30Z", t), boise("2026-10-11 16:30"))
        self.assertEqual(heavy.parse_maintenance("restart at 16:30 Boise", t), boise("2026-10-11 16:30"))
        self.assertEqual(heavy.parse_maintenance("restart at 01:30", boise("2026-10-11 23:00")),
                         boise("2026-10-12 01:30"))
        self.assertIsNone(heavy.parse_maintenance("restart soon", t))

    def test_the_restart_line_wins_and_several_times_without_it_are_refused(self):
        t = boise("2026-10-12 12:00")
        note = "written 2026-10-12 13:00 by the lead\nrestart: 2026-10-12 23:30\nback by 2026-10-13 00:30"
        self.assertEqual(heavy.parse_maintenance(note, t), boise("2026-10-12 23:30"))
        self.assertEqual(heavy.parse_maintenance("Restart: 14:30 (back by 15:00)", t), boise("2026-10-12 14:30"))
        # without a restart: line, which of two times is the restart? Neither: every job is refused
        for note in ("written 2026-10-12 13:00 by the lead: restart at 2026-10-12 23:30",
                     "restart at 14:30 (back by 2026-10-12 15:00)"):
            self.assertIsNone(heavy.parse_maintenance(note, t), note)
            with self.assertRaisesRegex(heavy.Refused, "restart: YYYY-MM-DD HH:MM"):
                heavy.plan(t, boise("2026-10-12 16:00"), 10, both(t), (note, None))
        self.assertEqual(heavy.parse_maintenance("restart at 14:30, really 14:30", t), boise("2026-10-12 14:30"))

    def test_a_bare_time_is_the_next_one_or_a_restart_running_late(self):
        t = boise("2026-10-12 14:00")
        # written in the afternoon for tonight: the next 03:00, not this morning's
        self.assertEqual(heavy.parse_maintenance("restart: 03:00 tonight", t), boise("2026-10-13 03:00"))
        self.assertEqual(heavy.plan(t, boise("2026-10-12 15:00"), 30, both(t),
                                    ("restart: 03:00", boise("2026-10-13 03:00")))[1], boise("2026-10-12 15:00"))
        # 13:00 is an hour ago and the VM hasn't restarted: still to come, so nothing starts
        self.assertEqual(heavy.parse_maintenance("restart: 13:00", t), boise("2026-10-12 13:00"))
        self.assertEqual(heavy.parse_maintenance("restart: 11:30", t), boise("2026-10-13 11:30"))
        self.assertEqual(heavy.parse_maintenance("restart: 23:30", boise("2026-10-13 00:30")),
                         boise("2026-10-12 23:30"))

    def test_a_restart_that_already_happened_is_ignored(self):
        restart = boise("2026-10-11 14:00")
        self.assertTrue(heavy.restart_done(restart, booted=restart.timestamp() + 120 - heavy.OFFSET))
        self.assertFalse(heavy.restart_done(restart, booted=restart.timestamp() - 86400 - heavy.OFFSET))


class Disk(unittest.TestCase):
    def test_twelve_gb_plus_the_peak(self):
        self.assertEqual(heavy.disk_problems(5, None, free=lambda p: 17.0), [])
        self.assertRegex(heavy.disk_problems(5, None, free=lambda p: 16.9)[0], "12 GB \\+ its peak 5 GB = 17 GB")

    def test_the_cold_drive_must_be_set_up_there_and_have_room(self):
        with tempfile.TemporaryDirectory() as d:
            work, cold = os.path.join(d, "work"), os.path.join(d, "cold")
            os.makedirs(work)
            os.makedirs(cold)
            old = heavy.WORK
            heavy.WORK = work
            try:
                self.assertRegex(heavy.disk_problems(0, 50, free=lambda p: 500.0)[0], "names no cold drive")
                self.assertEqual(heavy.disk_problems(0, None, free=lambda p: 500.0), [])
                marker = os.path.join(cold, ".marker")
                with open(os.path.join(work, "heavy.conf"), "w") as f:
                    f.write(f"# the VM's own\nCOLD_MOUNT={cold}\nCOLD_MARKER='{marker}'\n")
                self.assertRegex(heavy.disk_problems(0, 50, free=lambda p: 500.0)[0], "isn't mounted")
                open(marker, "w").close()
                self.assertEqual(heavy.disk_problems(0, 50, free=lambda p: 250.0), [])
                self.assertRegex(heavy.disk_problems(0, 51, free=lambda p: 250.0)[0], "200 GB \\+ 51 GB")
                with open(os.path.join(work, "heavy.conf"), "a") as f:
                    f.write("COLD_KEEP_GB=100\n")
                self.assertEqual(heavy.disk_problems(0, 150, free=lambda p: 250.0), [])
            finally:
                heavy.WORK = old


class Commands(unittest.TestCase):
    def test_a_docker_run_without_memory_is_refused(self):
        for cmd in (["docker", "run", "--rm", "img", "python", "x.py", "--memory", "3g"],
                    ["docker", "run", "--rm", "-v", "/a:/b", "img"],
                    ["docker", "container", "run", "img"]):
            with self.assertRaises(heavy.Refused) as err:
                heavy.prepare(cmd, "id")
            self.assertEqual(err.exception.code, heavy.EX_USAGE)

    def test_memory_in_any_spelling_passes_and_the_label_goes_after_run(self):
        for opts in (["--memory", "3g"], ["--memory=3g"], ["-m", "3g"], ["-m3g"], ["-it", "-m", "1g"]):
            cmd, notes = heavy.prepare(["docker", "run", "--rm", *opts, "--memory-swap=3g", "--cpus", "2", "img",
                                        "cmd"], "7-1")
            self.assertEqual(cmd[:4], ["docker", "run", "--label", "tvt.heavy=7-1"])
            self.assertEqual(notes, [])
        cmd, notes = heavy.prepare(["docker", "run", "-m", "1g", "img"], "7-1")
        self.assertIn("no --memory-swap", notes[0])
        self.assertIn("no --cpus", notes[1])

    def test_compose_run_and_container_run_are_labelled_too(self):
        asked = []

        def capped(prefix, service):
            asked.append((prefix, service))
            return {"mem_limit": "2147483648", "memswap_limit": "2147483648", "cpus": 2}

        cmd, notes = heavy.prepare(["docker", "compose", "-f", "a.yml", "--profile", "run", "run", "--rm",
                                    "-e", "X=run", "ingest", "python3", "-m", "ingest", "run", "x"], "9", capped)
        self.assertEqual(cmd[:8], ["docker", "compose", "-f", "a.yml", "--profile", "run", "run", "--label"])
        self.assertEqual(cmd[8:], ["tvt.heavy=9", "--rm", "-e", "X=run", "ingest", "python3", "-m", "ingest",
                                   "run", "x"])
        self.assertEqual(asked, [(["docker", "compose", "-f", "a.yml", "--profile", "run"], "ingest")])
        self.assertEqual(notes, [])
        cmd, _ = heavy.prepare(["docker", "container", "run", "--memory", "1g", "img"], "9")
        self.assertEqual(cmd[:5], ["docker", "container", "run", "--label", "tvt.heavy=9"])

    def test_a_compose_run_needs_a_memory_cap_in_the_compose_files(self):
        for service in ({}, {"cpus": 2}, {"deploy": {"resources": {"limits": {"cpus": "2"}}}}):
            with self.assertRaisesRegex(heavy.Refused, "has no memory cap") as err:
                heavy.prepare(["docker", "compose", "run", "--rm", "ingest", "x"], "9", lambda p, s: service)
            self.assertEqual(err.exception.code, heavy.EX_USAGE)
            self.assertIn("compose.load.yml", str(err.exception))
        _, notes = heavy.prepare(["docker", "compose", "run", "ingest", "x"], "9",
                                 lambda p, s: {"deploy": {"resources": {"limits": {"memory": "2g"}}}})
        self.assertEqual(len(notes), 2)
        self.assertIn("no memswap_limit", notes[0])
        self.assertIn("no cpus", notes[1])

    def test_docker_options_before_run_dont_hide_it(self):
        with self.assertRaises(heavy.Refused):
            heavy.prepare(["docker", "--context", "default", "run", "img"], "9")
        cmd, _ = heavy.prepare(["docker", "-H", "unix:///x", "run", "-m", "1g", "img"], "9")
        self.assertEqual(cmd[:6], ["docker", "-H", "unix:///x", "run", "--label", "tvt.heavy=9"])

    def test_exec_is_never_labelled_and_gets_its_own_note(self):
        for cmd in (["docker", "compose", "-f", "deploy/docker-compose.yml", "exec", "-T", "ingest",
                     "python3", "-m", "ingest", "run", "osm_valley"],
                    ["docker", "exec", "tvt-db-1", "pg_dump", "-U", "tvt", "-d", "tvt"],
                    ["docker", "container", "exec", "tvt-db-1", "psql", "-c", "select 1"]):
            out, notes = heavy.prepare(cmd, "9", lambda p, s: self.fail("no compose config for exec"))
            self.assertEqual(out, cmd)
            self.assertEqual(len(notes), 1)
            self.assertIn("can't stop what docker exec runs", notes[0])

    def test_other_commands_run_as_given_with_a_note(self):
        cmd, notes = heavy.prepare(["docker", "build", "-t", "x", "."], "9")
        self.assertEqual(cmd, ["docker", "build", "-t", "x", "."])
        self.assertIn("HEAVY_LABEL", notes[0])
        cmd, notes = heavy.prepare(["./run.sh", "--memory", "1g"], "9")
        self.assertEqual(cmd, ["./run.sh", "--memory", "1g"])
        self.assertIn("docker exec", notes[0])

    def test_passwords_in_urls_stay_out_of_the_log(self):
        self.assertEqual(heavy.redact("docker run -e DATABASE_URL=postgres://tvt_build:s3cr:et@db:5432/tvt img"),
                         "docker run -e DATABASE_URL=postgres://tvt_build:***@db:5432/tvt img")
        self.assertEqual(heavy.redact("https://example.org/a:b@c"), "https://example.org/a:b@c")

    def test_heavy_reads_no_test_hooks_from_the_environment(self):
        with open(HEAVY) as f:
            source = f.read()
        names = set(re.findall(r"""os\.environ(?:\.get)?[\[(]\s*["'](\w+)""", source))
        self.assertEqual(names, {"HEAVY_ID", "HEAVY_DEADLINE"})
        self.assertNotIn("HEAVY_TEST", source)


class Wrapper(unittest.TestCase):
    """The wrapper as a program, against a scratch work folder and a fake clock."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="heavy-test-")
        self.work = os.path.join(self.dir, "work")
        self.status = os.path.join(self.dir, "status")
        os.makedirs(self.work)
        os.makedirs(self.status)
        self.free = os.path.join(self.dir, "free")
        self.set_free(50)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def set_free(self, gb):
        with open(self.free + ".part", "w") as f:
            f.write(str(gb))
        os.replace(self.free + ".part", self.free)

    def write_status(self, t, rolling=(False, False)):
        for (name, d) in both(t, rolling):
            with open(os.path.join(self.status, name), "w") as f:
                json.dump(d, f)

    def env(self, now, **extra):
        env = dict(os.environ, HEAVY_HARNESS=json.dumps({"work": self.work, "status": self.status, "now": now,
                                                         "free_file": self.free, "grace_s": 3}), **extra)
        if "HEAVY_ID" not in extra:
            env.pop("HEAVY_ID", None)
        return env

    def run_heavy(self, now, *args, timeout=120, **extra):
        return subprocess.run([sys.executable, HARNESS, *args], env=self.env(now, **extra), capture_output=True,
                              text=True, timeout=timeout)

    def start_heavy(self, now, *args):
        return subprocess.Popen([sys.executable, HARNESS, *args], env=self.env(now), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def log(self):
        with open(os.path.join(self.work, "heavy.log")) as f:
            return f.read()

    def test_dry_runs_say_what_would_happen(self):
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "30", "--peak", "2",
                           "--dry-run", "P2 decode", "docker", "run", "--rm", "--memory", "3g", "--cpus", "3",
                           "tvt-worker", "python", "x.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would run in the day window: deadline 15:00, runtime 30 min, peak 2 GB", r.stdout)
        self.assertIn("docker run --label tvt.heavy=", r.stdout)
        self.assertIn("the lock is free", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.work, "heavy.log")))   # dry runs leave no log
        cases = [("2026-10-11 23:30", "23:59", "10", "50", heavy.EX_LATER, "no heavy jobs from 23:15"),
                 ("2026-10-11 14:00", "13:00", "10", "50", heavy.EX_LATER, "past the deadline"),
                 ("2026-10-11 14:00", "14:05", "10", "50", heavy.EX_LATER, "don't fit"),
                 ("2026-10-11 14:00", "23:30", "10", "50", heavy.EX_USAGE, "after the day window closes"),
                 ("2026-10-11 14:00", "15:00", "10", "13", heavy.EX_DISK, "not enough free disk")]
        for now, deadline, runtime, free, code, words in cases:
            self.set_free(free)
            r = self.run_heavy(now, "--deadline", deadline, "--runtime", runtime, "--peak", "2", "--dry-run",
                               "job", "true")
            self.assertEqual(r.returncode, code, (now, deadline, r.stderr))
            self.assertIn(words, r.stderr)

    def test_the_night_window_after_the_roll_up(self):
        t = boise("2026-10-11 02:00")
        self.write_status(t, (False, True))
        args = ("--deadline", "05:45", "--runtime", "60", "--peak", "0", "--dry-run", "G1 paint", "true")
        r = self.run_heavy("2026-10-11 02:00", *args)
        self.assertEqual(r.returncode, heavy.EX_LATER)
        self.assertIn("regional-cameras is still rolling up", r.stderr)
        self.write_status(t)
        r = self.run_heavy("2026-10-11 02:00", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("night window", r.stdout)

    def test_usage_errors(self):
        r = self.run_heavy("2026-10-11 14:00", "job", "true")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--deadline HH:MM, --runtime MIN, --peak GB", r.stderr)
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "5", "--peak", "0", "job",
                           "docker", "run", "img")
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs --memory", r.stderr)

    def test_a_job_runs_with_its_environment_and_exit_code_and_is_logged(self):
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "1",
                           "test job", "sh", "-c", 'echo "$HEAVY_LABEL $HEAVY_DEADLINE"; '
                           f'cat {self.work}/heavy.owner; exit 3')
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertRegex(r.stdout, r"^tvt\.heavy=\d+-\d+ 2026-10-11T15:00-06:00\n")
        self.assertIn("test job (pid", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.work, "heavy.owner")))
        self.assertRegex(self.log(), r"start\ttest job\tdeadline 15:00, runtime 1 min, peak 1 GB")
        self.assertRegex(self.log(), r"end\ttest job\texit 3 after")

    def test_the_job_is_stopped_at_its_deadline_with_its_children(self):
        pids = os.path.join(self.dir, "pids")
        started = time.monotonic()
        r = self.run_heavy("2026-10-11 14:59:55", "--deadline", "15:00", "--runtime", "0", "--peak", "0",
                           "sleeper", "sh", "-c", f"sleep 300 & echo $! > {pids}; sleep 300")
        took = time.monotonic() - started
        self.assertEqual(r.returncode, heavy.EX_DEADLINE, r.stderr)
        self.assertIn("deadline 15:00 reached", r.stderr)
        self.assertLess(took, 30)
        with open(pids) as f:
            child = int(f.read())
        time.sleep(0.5)
        self.assertFalse(heavy._alive(child) and not self._zombie(child), "the background sleep survived")
        self.assertIn("(deadline 15:00 reached)", self.log())

    def _zombie(self, pid):
        try:
            with open(f"/proc/{pid}/stat") as f:
                return f.read().split(") ")[1][0] == "Z"
        except OSError:
            return False

    def test_the_job_is_stopped_when_the_disk_runs_low(self):
        p = self.start_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "1",
                             "writer", "sleep", "300")
        time.sleep(2)
        self.set_free(10.5)
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, heavy.EX_FLOOR, err)
        self.assertIn("10.5 GB free", err)

    def test_an_interrupt_stops_the_job(self):
        p = self.start_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                             "sleeper", "sleep", "300")
        time.sleep(2)
        p.send_signal(signal.SIGINT)
        out, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, heavy.EX_INT, err)
        self.assertIn("interrupted (SIGINT)", err)

    def test_a_busy_lock_waits_and_leaves_a_wait_file_or_refuses_with_n(self):
        lock = os.open(os.path.join(self.work, "heavy.lock"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664)
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(os.path.join(self.work, "heavy.owner"), "w") as f:
            f.write("trees build (lead) (pid 1, since then)\n")
        try:
            r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0", "-n",
                               "job", "true")
            self.assertEqual(r.returncode, heavy.EX_LATER)
            self.assertIn("busy (trees build (lead)", r.stderr)
            r = self.run_heavy("2026-10-11 14:00", "--status")
            self.assertIn("lock:     held (trees build (lead) (pid 1, since then), for 0 min)", r.stdout)
            p = self.start_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                                 "-w", "2", "queued job", "echo", "ran")
            for _ in range(50):
                waits = [n for n in os.listdir(self.work) if n.startswith("heavy.wait.")]
                if waits:
                    break
                time.sleep(0.1)
            self.assertEqual(waits, [f"heavy.wait.{p.pid}"])
            os.remove(os.path.join(self.work, "heavy.owner"))
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)
        out, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, err)
        self.assertEqual(out, "ran\n")
        self.assertEqual([n for n in os.listdir(self.work) if n.startswith("heavy.wait.")], [])

    def test_browser_runs_holding_the_lock_shared_make_it_wait(self):
        lock = os.open(os.path.join(self.work, "heavy.lock"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664)
        fcntl.flock(lock, fcntl.LOCK_SH)
        try:
            r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                               "-w", "0", "job", "true")
        finally:
            os.close(lock)
        self.assertEqual(r.returncode, heavy.EX_LATER)
        self.assertIn("giving up", r.stderr)

    def test_with_w_it_waits_for_the_window(self):
        # 00:10, the roll-up going: with -w 0 it gives up at once, saying why
        self.write_status(boise("2026-10-11 00:10"), (True, False))
        r = self.run_heavy("2026-10-11 00:10", "--deadline", "05:45", "--runtime", "60", "--peak", "0",
                           "-w", "0", "G1 paint", "true")
        self.assertEqual(r.returncode, heavy.EX_LATER)
        self.assertIn("key_cameras is still rolling up", r.stderr)

    def test_the_job_holds_the_lock_and_a_heavy_inside_runs_at_once(self):
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "outer", sys.executable, HARNESS, "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "inner", "sh", "-c", "echo inner ran")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "inner ran\n")
        self.assertIn("inside heavy job", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.work, "heavy.id")))

    def test_a_heavy_inside_still_checks_the_caps(self):
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "outer", sys.executable, HARNESS, "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "inner", "docker", "run", "--rm", "img")
        self.assertEqual(r.returncode, heavy.EX_USAGE, r.stderr)
        self.assertIn("needs --memory", r.stderr)
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "outer", sys.executable, HARNESS, "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "--dry-run", "inner", "docker", "run", "-m", "1g", "img")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"would run at once: docker run --label tvt\.heavy=\d+-\d+ -m 1g img")

    def test_a_stray_heavy_id_bypasses_nothing(self):
        for hid in ("1-1", "garbage"):
            r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                               "job", "echo", "ran", HEAVY_ID=hid)
            self.assertEqual(r.returncode, heavy.EX_USAGE, r.stderr)
            self.assertIn("no heavy job is running: unset HEAVY_ID", r.stderr)
            self.assertEqual(r.stdout, "")
        # a job that has ended leaves no way in either: its id file is gone, or names a dead pid
        with open(os.path.join(self.work, "heavy.id"), "w") as f:
            f.write("5-1 999999\n")
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "job", "echo", "ran", HEAVY_ID="5-1")
        self.assertEqual(r.returncode, heavy.EX_USAGE, r.stderr)
        self.assertIn("heavy job 5-1 has ended", r.stderr)
        # the id names a live process, but nobody holds the lock
        open(os.path.join(self.work, "heavy.lock"), "w").close()
        with open(os.path.join(self.work, "heavy.id"), "w") as f:
            f.write(f"5-1 {os.getpid()}\n")
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "15:00", "--runtime", "1", "--peak", "0",
                           "job", "echo", "ran", HEAVY_ID="5-1")
        self.assertEqual(r.returncode, heavy.EX_USAGE, r.stderr)
        self.assertIn("doesn't hold heavy.lock", r.stderr)

    def test_maintenance_moves_the_deadline_and_a_vague_note_refuses(self):
        def note(text):
            with open(os.path.join(self.work, "MAINTENANCE"), "w") as f:
                f.write(text)
        note("restart: 2026-10-11 15:00 (A1, the video move)\nwritten 2026-10-11 13:00")
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "16:00", "--runtime", "30", "--peak", "0", "--dry-run",
                           "job", "true")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("deadline 14:50", r.stdout)
        note("restart at 14:30 (back by 2026-10-11 15:00)")
        r = self.run_heavy("2026-10-11 14:00", "--deadline", "16:00", "--runtime", "10", "--peak", "0", "--dry-run",
                           "job", "true")
        self.assertEqual(r.returncode, heavy.EX_LATER, r.stderr)
        self.assertIn("restart: YYYY-MM-DD HH:MM", r.stderr)
        r = self.run_heavy("2026-10-11 14:00", "--status")
        self.assertIn("every job is refused", r.stdout)

    def test_status_reports_the_state(self):
        self.write_status(boise("2026-10-11 14:00"))
        r = self.run_heavy("2026-10-11 14:00", "--status")
        self.assertEqual(r.returncode, 0, r.stderr)
        for words in ("lock:     no heavy.lock yet", "window:   day, open until 23:15",
                      "capture:  key_cameras: rolling_up false", "disk:     50.0 GB free", "cold:     none set"):
            self.assertIn(words, r.stdout)


@unittest.skipUnless(shutil.which("docker") and sys.platform.startswith("linux"), "needs docker (the VM)")
class Containers(unittest.TestCase):
    """A container started by the job is stopped at the deadline, by its label."""

    IMAGE = "debian:trixie-slim"

    def test_the_deadline_stops_a_labelled_container(self):
        have = subprocess.run(["docker", "image", "inspect", self.IMAGE], capture_output=True)
        self.assertEqual(have.returncode, 0, f"{self.IMAGE} isn't on this host")
        with tempfile.TemporaryDirectory() as d:
            free = os.path.join(d, "free")
            with open(free, "w") as f:
                f.write("50")
            now = dt.datetime.now(TZ).replace(hour=14, minute=59, second=52).isoformat()
            env = dict(os.environ, HEAVY_HARNESS=json.dumps({"work": d, "status": d, "free_file": free, "now": now,
                                                             "grace_s": 5}))
            env.pop("HEAVY_ID", None)
            r = subprocess.run([sys.executable, HARNESS, "--deadline", "15:00", "--runtime", "0", "--peak", "0",
                                "container test", "docker", "run", "--rm", "--memory", "64m", "--cpus", "0.2",
                                self.IMAGE, "sleep", "300"], env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, heavy.EX_DEADLINE, r.stderr)
            self.assertIn("stopping 1 container(s) labelled tvt.heavy=", r.stderr)
            hid = r.stderr.split("labelled tvt.heavy=")[1].split()[0]
            left = subprocess.run(["docker", "ps", "-aq", "--filter", f"label=tvt.heavy={hid}"],
                                  capture_output=True, text=True).stdout.split()
            self.assertEqual(left, [], f"containers labelled tvt.heavy={hid} left running")


if __name__ == "__main__":
    unittest.main()
