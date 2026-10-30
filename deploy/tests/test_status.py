"""Tests for deploy/bin/status: the VM at a glance for the lead's session start (M1).

    python3 -m unittest discover -s deploy/tests

Against a made-up work folder, capture status files and camera archive, a fixed clock and fixed
free disk (heavy's own settings, which status reads), and a fake database: nothing here touches
docker, a database or the real /srv.
"""
import datetime as dt
import fcntl
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(os.path.dirname(HERE), "bin", "status")


def load():
    loader = importlib.machinery.SourceFileLoader("status_under_test", STATUS)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    now = "2026-10-11 08:30"           # Boise

    def setUp(self):
        self.st = load()
        self.heavy = h = self.st.heavy
        self.tmp = tempfile.mkdtemp(prefix="tvt-status-")
        self.work = os.path.join(self.tmp, "work")
        self.cameras = os.path.join(self.tmp, "archive", "cameras")
        os.makedirs(self.work)
        os.makedirs(os.path.join(self.cameras, "status"))
        h.WORK = self.work
        h.STATUS_DIR = os.path.join(self.cameras, "status")
        self.t = dt.datetime.fromisoformat(self.now).replace(tzinfo=h.TZ)
        h.OFFSET = self.t.timestamp() - time.time()
        self.free = {"/": 30.0}
        h.free_gb = lambda where: self.free.get(where, 1500.0)
        h.boot_time = lambda: self.t.timestamp() - h.OFFSET - 86400
        self.statuses()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def statuses(self, rolling=(False, False), ages=(10, 10), paused=False):
        for (name, cadence), roll, age in zip((("key_cameras", 50), ("regional-cameras", 600)), rolling, ages):
            with open(os.path.join(self.cameras, "status", name + ".json"), "w") as f:
                json.dump({"version": 1, "cadence_s": cadence, "heartbeat": self.t.timestamp() - age,
                           "rolling_up": roll, "paused_low_disk": paused}, f)

    def camera_day(self, cam, day, video=True, failed=False, jpegs=True, frames=True):
        """A camera-day in the archive: its JPEG folder (with frames, or empty), its video, its failure note."""
        if jpegs:
            jpeg = os.path.join(self.cameras, "jpeg", str(cam), day)
            os.makedirs(jpeg, exist_ok=True)
            if frames:
                with open(os.path.join(jpeg, "index.csv"), "w") as f:
                    f.write("fetched_at,file,bytes,sha256\n2026-10-10T14:00:00Z,140000.jpg,3,x\n")
                open(os.path.join(jpeg, "140000.jpg"), "w").close()
        folder = os.path.join(self.cameras, "video", str(cam), day[:4])
        os.makedirs(folder, exist_ok=True)
        if video:
            open(os.path.join(folder, f"{cam}-{day}.mp4"), "w").close()
        if failed:
            open(os.path.join(folder, f"{cam}-{day}.mp4.failed"), "w").close()

    def run_status(self, argv=("--no-db",), db=None):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = self.st.main(list(argv), run=db)
        return code, out.getvalue()


class TheVm(Base):
    def test_all_fine(self):
        for cam in (652, 656, 674):
            self.camera_day(cam, "2026-10-10")
        self.camera_day(652, "2026-10-11", video=False)        # today: still collecting
        open(os.path.join(self.work, "heavy.lock"), "w").close()
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("2026-10-11 08:30 MDT in Boise (14:30 UTC)", out)
        self.assertIn("  disk:     30.0 GB free on /", out)
        self.assertIn("  heavy:    heavy.lock is free", out)
        self.assertIn("  roll-up:  finished: 3 of 3 camera-day videos made for 2026-10-10", out)
        self.assertIn("  restart:  none planned", out)
        self.assertTrue(out.rstrip().endswith("nothing to look at"))

    def test_low_disk_a_missing_video_and_a_planned_restart_need_a_look(self):
        self.free["/"] = 13.5
        self.camera_day(652, "2026-10-10")
        self.camera_day(656, "2026-10-10", video=False)
        self.camera_day(674, "2026-10-10", video=False, failed=True)
        with open(os.path.join(self.work, "MAINTENANCE"), "w") as f:
            f.write("restart: 2026-10-11 23:30\nA1 cold drive\n")
        code, out = self.run_status()
        self.assertEqual(code, 1)
        self.assertIn("! disk:     13.5 GB free", out)
        self.assertIn("! roll-up:  not going, and 1 of 3 camera-day videos made for 2026-10-10, 1 failed, 1 missing", out)
        self.assertIn("! restart:  planned 2026-10-11 23:30 Boise", out)
        self.assertIn("3 things to look at", out)

    def test_videos_count_after_their_jpegs_are_deleted(self):
        # Low disk: the capture deleted yesterday's JPEGs once their videos were made (prune with
        # one day kept); a failure note stays; an empty JPEG folder rolls up to nothing.
        self.camera_day(652, "2026-10-10", jpegs=False)
        self.camera_day(656, "2026-10-10", jpegs=False)
        self.camera_day(674, "2026-10-10", video=False, failed=True, jpegs=False)
        self.camera_day(680, "2026-10-10", video=False, frames=False)
        self.camera_day(652, "2026-10-09", jpegs=False)                 # another day: not counted
        with open(os.path.join(self.cameras, "video", "index-key.json"), "w") as f:
            f.write("{}")
        code, out = self.run_status()
        self.assertIn("! roll-up:  not going, and 2 of 3 camera-day videos made for 2026-10-10, 1 failed\n", out)
        self.assertNotIn("missing", out)
        os.remove(os.path.join(self.cameras, "video", "674", "2026", "674-2026-10-10.mp4.failed"))
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("  roll-up:  finished: 2 of 2 camera-day videos made for 2026-10-10", out)

    def test_an_empty_archive_needs_a_look(self):
        code, out = self.run_status()
        self.assertEqual(code, 1)
        self.assertIn("! roll-up:  no camera videos or JPEGs for 2026-10-10 in the archive", out)

    def test_a_roll_up_still_going_after_six_holds_day_jobs(self):
        self.statuses(rolling=(True, False))
        self.camera_day(652, "2026-10-10", video=False)
        code, out = self.run_status()
        self.assertEqual(code, 1)
        self.assertIn("! roll-up:  going (key_cameras): 0 of 1 camera-day videos made for 2026-10-10; "
                      "it holds heavy jobs until it ends", out)

    def test_a_silent_or_paused_capture_needs_a_look(self):
        self.camera_day(652, "2026-10-10")
        self.statuses(ages=(10, 3600))
        code, out = self.run_status()
        self.assertEqual(code, 1)
        self.assertIn("!            regional-cameras last reported 60 min ago", out)
        self.statuses(paused=True)
        code, out = self.run_status()
        self.assertIn("key_cameras has paused for low disk", out)

    def test_the_cold_drive(self):
        self.camera_day(652, "2026-10-10")
        cold = os.path.join(self.tmp, "cold")
        os.makedirs(cold)
        with open(os.path.join(self.work, "heavy.conf"), "w") as f:
            f.write(f"COLD_MOUNT={cold}\nCOLD_MARKER={cold}/.tvt-cold-drive\nCOLD_KEEP_GB=200\n")
        code, out = self.run_status()
        self.assertIn(f"! cold:     not mounted ({cold}/.tvt-cold-drive is missing)", out)
        open(os.path.join(cold, ".tvt-cold-drive"), "w").close()
        self.free[cold] = 1582.4
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn(f"  cold:     1582 GB free on {cold} (kept free: 200 GB)", out)

    def test_the_cold_videos_last_run(self):
        self.camera_day(652, "2026-10-10")
        state = os.path.join(self.cameras, "cold-videos.json")
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("  cold-vid: no run yet", out)
        run = {"finished": "2026-10-11T08:05:00Z", "result": "done", "code": 0, "why": "", "moved": 830,
               "bytes": 2.1 * 2**30, "left": 0, "cold_free_gb": 1498.4, "last_done": "2026-10-11T08:05:00Z"}
        with open(state, "w") as f:
            json.dump(run, f)
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("  cold-vid: last run 6 h ago, done: moved 830 files (2.1 GB)\n", out)   # the cold drive's state
        # Not now (the roll-up ran late) is fine for a day; two days without a finished run isn't.
        with open(state, "w") as f:
            json.dump(dict(run, result="not now", code=75, why="the camera roll-up is still going (key_cameras)",
                           moved=0, bytes=0, last_done="2026-10-09T08:05:00Z"), f)
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("! cold-vid: last run 6 h ago, not now: the camera roll-up is still going (key_cameras); "
                      "moved 0 files (0.0 GB); last finished run: 2 d ago", out)
        # Off-site (version 2): what was sent, and the cold drive's old links still to prove.
        run = dict(run, version=2, moved=830, left=0, relinked=0, old_left=0, old_bad=0)
        run.pop("cold_free_gb")
        with open(state, "w") as f:
            json.dump(run, f)
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("  cold-vid: last run 6 h ago, done: sent 830 files (2.1 GB)\n", out)
        with open(state, "w") as f:
            json.dump(dict(run, relinked=9000, old_left=40, old_bad=2, old_unknown=1), f)
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("! cold-vid: last run 6 h ago, done: sent 830 files (2.1 GB); 9000 old cold-drive links now "
                      "off-site; 40 files still link to the cold drive (2 don't match their off-site copies, "
                      "1 have no logged sha256)\n", out)
        with open(state, "w") as f:
            json.dump(dict(run, code=1, result="failed", offsite_links=5000, offsite_missing=3), f)
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("! cold-vid: last run 6 h ago, failed: sent 830 files (2.1 GB); 3 of 5000 off-site copies "
                      "missing\n", out)
        with open(state, "w") as f:
            json.dump(dict(run, result="off-site storage unreachable", code=69, moved=0, bytes=0,
                           why="the off-site storage can't be reached (ping: exit 255: no route)"), f)
        code, out = self.run_status()
        self.assertEqual(code, 1, out)
        self.assertIn("! cold-vid: last run 6 h ago, off-site storage unreachable: the off-site storage can't be "
                      "reached (ping: exit 255: no route); sent 0 files", out)
        with open(state, "w") as f:
            f.write("{")
        self.assertIn("! cold-vid: its state file can't be read", self.run_status()[1])

    def test_the_lock_holder_and_its_age(self):
        self.camera_day(652, "2026-10-10")
        with open(os.path.join(self.work, "heavy.owner"), "w") as f:
            f.write("P2 decode (B2) (pid 4242, since 2026-10-11 07:48:00 MDT; deadline 22:30, runtime 150 min)\n")
        past = time.time() - 42 * 60
        os.utime(os.path.join(self.work, "heavy.owner"), (past, past))
        # flock locks belong to the open file description, so status's own open() sees this one.
        fd = os.open(os.path.join(self.work, "heavy.lock"), os.O_WRONLY | os.O_CREAT, 0o664)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            code, out = self.run_status()
            fcntl.flock(fd, fcntl.LOCK_UN)
            fcntl.flock(fd, fcntl.LOCK_SH)
            with open(os.path.join(self.work, "heavy.wait.%d" % os.getpid()), "w") as f:
                f.write("G1 paint (B1) (pid 1, waiting since 08:20)\n")
            _, shared = self.run_status()
        finally:
            os.close(fd)
        self.assertEqual(code, 0, out)
        self.assertIn("  heavy:    heavy.lock is held: P2 decode (B2) (pid 4242", out)
        self.assertIn("for 42 min", out)
        self.assertIn("  heavy:    heavy.lock is shared: ", shared)
        self.assertIn("waiting: G1 paint (B1)", shared)

    def test_before_tonights_roll_up_it_reports_the_night_before(self):
        self.t = dt.datetime.fromisoformat("2026-10-12 00:02").replace(tzinfo=self.heavy.TZ)
        self.heavy.OFFSET = self.t.timestamp() - time.time()
        self.statuses()
        self.camera_day(652, "2026-10-10")
        self.camera_day(652, "2026-10-11", video=False)
        code, out = self.run_status()
        self.assertIn("finished: 1 of 1 camera-day videos made for 2026-10-10", out)

    def test_just_after_five_past_midnight_the_roll_up_is_only_due(self):
        self.t = dt.datetime.fromisoformat("2026-10-12 00:07").replace(tzinfo=self.heavy.TZ)
        self.heavy.OFFSET = self.t.timestamp() - time.time()
        self.statuses(ages=(10, 200))                   # regional's last check was before 00:05
        self.camera_day(652, "2026-10-11", video=False)
        code, out = self.run_status()
        self.assertEqual(code, 0, out)
        self.assertIn("  roll-up:  tonight's hasn't finished yet (regional-cameras hasn't reported since its first "
                      "roll-up check after 00:05", out)
        self.assertIn("0 of 1 camera-day videos made for 2026-10-11", out)

    def test_usage(self):
        code, _ = self.run_status(["--bogus"])
        self.assertEqual(code, 2)


class TheDatabase(Base):
    def setUp(self):
        super().setUp()
        self.camera_day(652, "2026-10-10")

    def fake(self, data, ready=True, fail=None):
        calls = []

        def run(sql):
            calls.append(sql)
            if fail:
                raise self.st.DbError(fail)
            if "to_regclass" in sql and "json" not in sql:
                return "t" if ready else "f"
            return json.dumps(data)
        run.calls = calls
        return run

    def test_fresh_sources_and_built_builds(self):
        data = {"sources": [{"source": "awc_metar", "state": "fresh", "every_s": 600, "age_s": 120, "failures": 0,
                             "last_error": None}],
                "builds": [{"build": "water-build", "state": "built", "age_s": 7200, "pending_s": None,
                            "pending_by": None, "pending_reason": None, "run_s": 9000, "last_error": None}]}
        code, out = self.run_status([], db=self.fake(data))
        self.assertEqual(code, 0, out)
        self.assertIn("  sources:  1 sources in tvt (tvt-db-1): 1 fresh", out)
        self.assertIn("  builds:   1 built", out)
        self.assertIn("water-build: last built 2 h ago", out)

    def test_late_failing_and_pending_need_a_look(self):
        data = {"sources": [
            {"source": "awc_metar", "state": "fresh", "every_s": 600, "age_s": 120, "failures": 0, "last_error": None},
            {"source": "nws_wwa", "state": "fresh", "every_s": 600, "age_s": 300, "failures": 2,
             "last_error": "HTTPError: 503 for https://api.example.test/x?key=abc123&y=1"},
            {"source": "achd_roads", "state": "late", "every_s": 604800, "age_s": 9 * 86400, "failures": 0,
             "last_error": None},
            {"source": "new_one", "state": "never", "every_s": 3600, "age_s": None, "failures": 1,
             "last_error": "URLError: postgres://u:pw@host/db refused"}],
            "builds": [
                {"build": "roads-build", "state": "pending", "age_s": 9 * 86400, "pending_s": 5 * 3600,
                 "pending_by": ["osm_street", "achd_roads"], "pending_reason": "new extract", "run_s": None,
                 "last_error": None},
                {"build": "landscape-bake", "state": "running", "age_s": None, "pending_s": None, "pending_by": None,
                 "pending_reason": None, "run_s": 1200, "last_error": None},
                {"build": "soils-build", "state": "failed", "age_s": 3 * 86400, "pending_s": None, "pending_by": None,
                 "pending_reason": None, "run_s": 4000, "last_error": "ValueError: bad geometry"},
                {"build": "farm-build", "state": "failed", "age_s": None, "pending_s": 7200, "pending_by": ["osm_landuse"],
                 "pending_reason": "new extract", "run_s": 3600,
                 "last_error": "ended without logging its end (killed, or its connection was lost)"},
                {"build": "water-build", "state": "running", "age_s": 86400, "pending_s": None, "pending_by": None,
                 "pending_reason": None, "run_s": 20 * 3600, "last_error": None}]}
        code, out = self.run_status(["--db-container", "tvt-scratch-db"], db=self.fake(data))
        self.assertEqual(code, 1)
        self.assertIn("! sources:  4 sources in tvt (tvt-scratch-db): 2 fresh, 1 late, 1 never", out)
        lines = out.splitlines()
        i = next(n for n, line in enumerate(lines) if "sources:" in line)
        self.assertIn("new_one: never (every 60 min); 1 failed try since: URLError: postgres://u:***@host/db refused",
                      lines[i + 1])
        self.assertIn("achd_roads: late, last good fetch 9 d ago (every 7 d)", lines[i + 2])
        self.assertIn("nws_wwa: failing, last good fetch 5 min ago (every 10 min); 2 failed tries since: "
                      "HTTPError: 503 for https://api.example.test/x?key=***&y=1", lines[i + 3])
        self.assertNotIn("abc123", out)
        self.assertIn("! builds:   2 failed, 2 running, 1 pending", out)
        builds = lines[next(n for n, line in enumerate(lines) if "builds:" in line) + 1:-1]
        self.assertEqual([b.split(":")[0].strip() for b in builds],
                         ["farm-build", "soils-build", "landscape-bake", "water-build", "roads-build"])
        self.assertIn("landscape-bake: running for 20 min; never built", out)
        self.assertIn("water-build: running for 20 h, longer than a run should take; last built 24 h ago", out)
        self.assertIn("roads-build: marked 5 h ago (osm_street; achd_roads), newest: new extract; last built 9 d ago", out)
        self.assertIn("soils-build: its last run failed: ValueError: bad geometry; last built 3 d ago", out)
        self.assertIn("farm-build: its last run failed: ended without logging its end (killed, or its connection "
                      "was lost); still marked, since 2 h ago (osm_landuse); never built", out)

    def test_before_the_migration_and_when_it_doesnt_answer(self):
        code, out = self.run_status([], db=self.fake({}, ready=False))
        self.assertEqual(code, 0, out)
        self.assertIn("the staleness views aren't there yet (migrations 0021, 0022)", out)
        code, out = self.run_status([], db=self.fake({}, fail="psql: error: connection to server failed"))
        self.assertEqual(code, 1)
        self.assertIn("! sources:  tvt (tvt-db-1) didn't answer: psql: error", out)

    def test_it_reads_the_database_read_only(self):
        self.assertIn("default_transaction_read_only=on", self.st.PGOPTIONS)
        self.assertIn("statement_timeout=10s", self.st.PGOPTIONS)
        run = self.fake({"sources": [], "builds": []})
        self.run_status([], db=run)
        self.assertEqual(len(run.calls), 2)
        self.assertNotRegex(" ".join(run.calls).lower(), r"\b(insert|update|delete|create|drop|alter)\b")


if __name__ == "__main__":
    unittest.main()
