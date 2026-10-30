"""Tests for deploy/bin/cold-videos: finished camera days older than a few days go to off-site storage, read
back before off-site links take their place (decision A1, as changed on Oct 30, 2026).

    python3 -m unittest discover -s deploy/tests

Against synthetic trees: a made-up camera archive, capture status files and work folder (heavy's settings, which
cold-videos reads), a fixed clock and fixed free disk. The off-site storage is offsite_double.py over a temporary
folder, reached through OFFSITE_SSH as the real one is. Nothing here touches the real /srv, docker or the network.
"""
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import cold_harness  # noqa: E402

HARNESS = os.path.join(HERE, "cold_harness.py")
DOUBLE = os.path.join(HERE, "offsite_double.py")


def boise(text, tz):
    return dt.datetime.fromisoformat(text).replace(tzinfo=tz)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Base(unittest.TestCase):
    now = "2026-10-16 02:30"           # Boise: tonight's roll-up finished; days up to Oct 8 go

    def setUp(self):
        self.cv = cold_harness.load()
        self.h = h = self.cv.heavy
        self.tmp = tempfile.mkdtemp(prefix="tvt-cold-videos-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.work = os.path.join(self.tmp, "work")
        self.cameras = os.path.join(self.tmp, "archive", "cameras")
        self.offsite = os.path.join(self.tmp, "offsite")
        self.store = os.path.join(self.offsite, "store")
        for d in (self.work, os.path.join(self.cameras, "status"), os.path.join(self.cameras, "video"), self.store):
            os.makedirs(d, exist_ok=True)
        self.conf()
        h.WORK = self.work
        h.STATUS_DIR = os.path.join(self.cameras, "status")
        self.set_clock(self.now)
        self.free = 40.0
        h.free_gb = lambda where: self.free
        self.statuses()

    def set_clock(self, text):
        self.t = boise(text, self.h.TZ)
        self.h.OFFSET = self.t.timestamp() - time.time()
        self.h.boot_time = lambda: self.t.timestamp() - self.h.OFFSET - 86400

    def conf(self, **extra):
        command = " ".join(shlex.quote(a) for a in (sys.executable, DOUBLE, self.offsite))
        values = {"OFFSITE_SSH": command, **extra}
        with open(os.path.join(self.work, "heavy.conf"), "w") as f:
            f.write("# the VM's own settings\n")
            for key, value in values.items():
                if value is not None:
                    f.write(f"{key}={value}\n")

    def faults(self, **faults):
        with open(os.path.join(self.offsite, "faults.json"), "w") as f:
            json.dump(faults, f)

    def calls(self, verb=None):
        try:
            with open(os.path.join(self.offsite, "calls.log")) as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            return []
        return [line for line in lines if verb is None or line.split()[0] == verb]

    def statuses(self, rolling=(False, False), ages=(10, 10)):
        for (name, cadence), roll, age in zip((("key_cameras", 50), ("regional-cameras", 600)), rolling, ages):
            with open(os.path.join(self.cameras, "status", name + ".json"), "w") as f:
                json.dump({"version": 1, "cadence_s": cadence, "heartbeat": self.t.timestamp() - age,
                           "rolling_up": roll, "paused_low_disk": False}, f)

    def day(self, back):
        return self.t.date() - dt.timedelta(days=back)

    def rel(self, cam, day, ext="mp4"):
        return f"video/{cam}/{day:%Y}/{cam}-{day.isoformat()}.{ext}"

    def camera_day(self, cam, day, video=True, csv=True, size=1000, written=None):
        """A finished camera-day: its video and CSV, written an hour after the day ended (or at written)."""
        folder = os.path.join(self.cameras, "video", str(cam), f"{day:%Y}")
        os.makedirs(folder, exist_ok=True)
        when = written or (dt.datetime.combine(day + dt.timedelta(days=1), dt.time(1), self.h.TZ).timestamp())
        paths = []
        for ext, wanted in (("mp4", video), ("csv", csv)):
            if not wanted:
                continue
            path = os.path.join(self.cameras, self.rel(cam, day, ext))
            seed = f"{cam} {day} {ext} ".encode()
            with open(path, "wb") as f:
                f.write((seed * (size // len(seed) + 1))[:size if ext == "mp4" else size // 10])
            os.utime(path, (when, when))
            paths.append(path)
        return paths

    def archive(self, cams=(656, 752), days=range(1, 11)):
        for cam in cams:
            for back in days:
                self.camera_day(cam, self.day(back))

    def run_cv(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.cv.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def state(self):
        with open(os.path.join(self.cameras, "cold-videos.json")) as f:
            return json.load(f)

    def log(self):
        with open(os.path.join(self.cameras, "cold-videos.log")) as f:
            return f.read()

    def assertSent(self, rel, digest=None):
        """rel is an off-site link recording its bytes and sha256, and the storage holds those bytes."""
        path = os.path.join(self.cameras, rel)
        self.assertTrue(os.path.islink(path), f"{rel} isn't a link")
        target = os.readlink(path)
        self.assertRegex(target, r"^offsite:\d+:[0-9a-f]{64}$")
        _, size, digest_in_link = target.split(":")
        copy = os.path.join(self.store, rel)
        self.assertEqual((int(size), digest_in_link), (os.path.getsize(copy), sha(copy)))
        if digest is not None:
            self.assertEqual(digest_in_link, digest)

    def assertStays(self, rel):
        path = os.path.join(self.cameras, rel)
        self.assertTrue(os.path.isfile(path) and not os.path.islink(path), f"{rel} went")

    def assertNoHiddenFiles(self):
        for folder, _, names in os.walk(self.cameras):
            self.assertFalse([n for n in names if n.endswith((".cold-link", ".cold-back"))], folder)

    def snapshot(self):
        out = {}
        for root in (self.cameras, self.store):
            for folder, dirs, names in os.walk(root):
                for n in dirs + names:
                    p = os.path.join(folder, n)
                    if n in ("cold-videos.log", "cold-videos.json"):
                        continue
                    out[p] = (os.path.islink(p), os.readlink(p) if os.path.islink(p) else None,
                              None if os.path.isdir(p) or os.path.islink(p) else sha(p))
        return out


class SendTest(Base):
    def test_days_older_than_the_kept_ones_go_off_site_and_links_take_their_place(self):
        self.archive()
        before = {rel: sha(os.path.join(self.cameras, rel))
                  for cam in (656, 752) for back in range(1, 11) for rel in
                  (self.rel(cam, self.day(back)), self.rel(cam, self.day(back), "csv"))}
        st = os.stat(os.path.join(self.cameras, self.rel(656, self.day(8))))
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        for cam in (656, 752):
            for back in range(1, 11):
                for ext in ("mp4", "csv"):
                    rel = self.rel(cam, self.day(back), ext)
                    if back >= 8:
                        self.assertSent(rel, before[rel])        # the storage holds the very bytes
                    else:
                        self.assertStays(rel)
                        self.assertEqual(sha(os.path.join(self.cameras, rel)), before[rel])
        copy = os.stat(os.path.join(self.store, self.rel(656, self.day(8))))
        self.assertEqual(copy.st_mtime_ns, st.st_mtime_ns)       # the copy keeps the original's time

        state = self.state()
        self.assertEqual((state["version"], state["result"], state["code"], state["moved"], state["left"],
                          state["failed"]), (2, "done", 0, 12, 0, 0))
        self.assertEqual(state["bytes"], 6 * 1000 + 6 * 100)
        self.assertEqual(state["cutoff"], self.day(8).isoformat())
        self.assertEqual(state["last_done"], state["finished"])
        self.assertEqual((state["relinked"], state["old_left"], state["old_bad"]), (0, 0, 0))
        log = self.log()
        self.assertEqual(log.count(" sent video/"), 12)
        rel = self.rel(752, self.day(10))
        self.assertIn(f"sent {rel} (1000 bytes, sha256 {before[rel]})", log)
        # Each day's video goes before its CSV, oldest day first.
        order = [line.split()[2] for line in log.splitlines() if " sent video/" in line]
        self.assertEqual(order[:4], [self.rel(656, self.day(10)), self.rel(656, self.day(10), "csv"),
                                     self.rel(752, self.day(10)), self.rel(752, self.day(10), "csv")])
        self.assertEqual((state["offsite_links"], state["offsite_missing"]), (12, 0))
        self.assertNoHiddenFiles()

    def test_a_second_run_sends_nothing(self):
        self.archive()
        self.assertEqual(self.run_cv()[0], 0)
        before, puts = self.snapshot(), len(self.calls("put"))
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.state()["moved"], 0)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.calls("put")), puts)

    def test_each_file_is_read_back_as_soon_as_it_is_sent(self):
        self.archive(cams=(656, 752, 801), days=(8, 9))         # 12 files
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        verbs = [c.split()[0] for c in self.calls()]
        self.assertEqual(verbs, ["ping"] + ["put", "verify"] * 12 + ["list"])

    def test_keep_days_and_the_files_that_always_stay(self):
        self.archive(cams=(656,), days=range(0, 6))
        busy = self.day(5)
        open(os.path.join(self.cameras, self.rel(656, busy)) + ".part", "w").close()       # an encode going
        self.camera_day(752, self.day(4), video=False)                                    # a CSV alone
        self.camera_day(801, self.day(4))                                                 # JPEGs still there
        os.makedirs(os.path.join(self.cameras, "jpeg", "801", self.day(4).isoformat()))
        self.camera_day(802, self.day(4), written=self.t.timestamp() - 60)                # just written
        self.assertEqual(self.run_cv("--keep-days", "1")[0], 2)
        code, out = self.run_cv("--keep-days", "2")
        self.assertEqual(code, 0, out)
        for back in (0, 1, 2):
            self.assertStays(self.rel(656, self.day(back)))
        self.assertSent(self.rel(656, self.day(3)))
        self.assertSent(self.rel(656, self.day(4), "csv"))
        for rel in (self.rel(656, busy), self.rel(656, busy, "csv"), self.rel(752, self.day(4), "csv"),
                    self.rel(801, self.day(4)), self.rel(802, self.day(4))):
            self.assertStays(rel)
        self.assertEqual(self.state()["kept"], {"its encode is going": 2, "a CSV without its video": 1,
                                                "its JPEGs are still in the buffer": 2,
                                                "written in the last 10 minutes": 2})

    def test_keep_days_from_heavy_conf(self):
        self.archive(cams=(656,), days=range(1, 6))
        self.conf(COLD_VIDEO_KEEP_DAYS="3")
        self.assertEqual(self.run_cv()[0], 0)
        self.assertStays(self.rel(656, self.day(3)))
        self.assertSent(self.rel(656, self.day(4)))

    def test_limit_sends_the_oldest_files_first(self):
        self.archive(cams=(656, 752), days=(8, 9))
        code, out = self.run_cv("--limit", "2")
        self.assertEqual(code, 0, out)
        self.assertSent(self.rel(656, self.day(9)))
        self.assertSent(self.rel(656, self.day(9), "csv"))
        for rel in (self.rel(752, self.day(9)), self.rel(656, self.day(8)), self.rel(752, self.day(8))):
            self.assertStays(rel)
        self.assertEqual(self.state()["moved"], 2)

    def test_dry_run_changes_nothing(self):
        self.archive()
        before = self.snapshot()
        code, out = self.run_cv("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"would send {self.rel(656, self.day(8))} (1000 bytes)", out)
        self.assertNotIn(f"would send {self.rel(656, self.day(7))}", out)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls("put"))
        self.assertFalse(os.path.exists(os.path.join(self.cameras, "cold-videos.json")))

    def test_reads_are_paced(self):
        slept = []
        with mock.patch.object(self.cv.time, "sleep", slept.append):
            pace = self.cv.Pace(1)                       # 1 MB/s
            pace(500_000)
            pace(500_000)                                # (the fake sleep takes no time)
            self.cv.Pace(0)(10**9)                       # 0: no limit
        self.assertEqual(len(slept), 2)
        self.assertAlmostEqual(slept[-1], 1.0, delta=0.1)


class CheckTest(Base):
    """Nothing becomes a link until its copy, read back from the storage, is the original."""

    def setUp(self):
        super().setUp()
        self.archive(cams=(656,), days=(9, 10))

    def assertAllStay(self):
        for back in (9, 10):
            self.assertStays(self.rel(656, self.day(back)))
            self.assertStays(self.rel(656, self.day(back), "csv"))
        self.assertNoHiddenFiles()

    def test_a_copy_that_reads_back_wrong_keeps_the_original(self):
        self.faults(corrupt=[self.rel(656, self.day(9))])
        code, out = self.run_cv()
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAILED {self.rel(656, self.day(9))}: the copy read back from the off-site storage doesn't "
                      "match the original's sha256 (the original stays)", out)
        self.assertStays(self.rel(656, self.day(9)))
        self.assertSent(self.rel(656, self.day(10)))
        self.assertEqual((self.state()["result"], self.state()["failed"], self.state()["left"], self.state()["moved"]),
                         ("failed", 1, 1, 3))
        self.faults()
        self.assertEqual(self.run_cv()[0], 0)                               # the next run sends it again
        self.assertSent(self.rel(656, self.day(9)))
        self.assertEqual(self.state()["last_done"], self.state()["finished"])

    def test_what_arrives_off_site_must_be_what_was_sent(self):
        self.faults(put_answers="0" * 64)
        code, out = self.run_cv()
        self.assertEqual(code, 1, out)
        self.assertIn("what arrived off-site isn't what was sent", out)
        self.assertAllStay()
        self.assertFalse(self.calls("verify"))
        self.assertEqual(self.state()["failed"], 4)

    def test_a_copy_the_storage_doesnt_keep_leaves_the_original(self):
        self.faults(lose=[self.rel(656, self.day(10), "csv")])
        code, out = self.run_cv()
        self.assertEqual(code, 1, out)
        self.assertIn("it couldn't be read back from the off-site storage after it was sent", out)
        self.assertStays(self.rel(656, self.day(10), "csv"))
        self.assertSent(self.rel(656, self.day(10)))

    def test_a_read_back_that_fails_leaves_the_originals(self):
        self.faults(verify_down=True)
        code, out = self.run_cv()
        self.assertEqual(code, 1, out)
        self.assertIn(f"FAILED {self.rel(656, self.day(10))}: verify: exit 1: read-back failed (the original stays)",
                      out)
        self.assertAllStay()

    def test_an_original_that_changes_while_sent_stays(self):
        video = os.path.join(self.cameras, self.rel(656, self.day(9)))
        real = self.cv.Offsite.put

        def put_then_change(offsite, path, rel, st, *args):
            digest = real(offsite, path, rel, st, *args)
            if path == video:
                with open(path + ".new", "wb") as f:
                    f.write(b"encoded again")
                os.replace(path + ".new", path)                             # a roll-up's rename
            return digest

        with mock.patch.object(self.cv.Offsite, "put", put_then_change):
            code, out = self.run_cv()
        self.assertEqual(code, 1, out)
        self.assertIn("the original changed while it was sent", out)
        self.assertStays(self.rel(656, self.day(9)))
        with open(video, "rb") as f:
            self.assertEqual(f.read(), b"encoded again")
        os.utime(video, (self.t.timestamp() - 3600,) * 2)
        code, out = self.run_cv()                                           # next time: the storage holds the
        self.assertEqual(code, 1, out)                                      # old one, and doesn't replace it
        self.assertIn("isn't replaced (the original stays)", out)
        self.assertStays(self.rel(656, self.day(9)))

    def test_a_day_encoded_again_doesnt_replace_its_copy_off_site(self):
        self.assertEqual(self.run_cv()[0], 0)
        rel = self.rel(656, self.day(9))
        path = os.path.join(self.cameras, rel)
        first = os.readlink(path)
        os.remove(path)                                                     # ingest rollup --force
        with open(path, "wb") as f:
            f.write(b"a better encode")
        os.utime(path, (self.t.timestamp() - 3600,) * 2)
        code, out = self.run_cv()
        self.assertEqual(code, 1, out)                                      # loud, never silent
        self.assertIn("isn't replaced", out)
        self.assertStays(rel)
        self.assertEqual(sha(os.path.join(self.store, rel)), first.split(":")[2])

    def test_stopped_by_sigterm_leaves_the_original(self):
        self.camera_day(801, self.day(9), size=6 * 2**20)
        rel = self.rel(801, self.day(9))
        free = os.path.join(self.tmp, "free")
        with open(free, "w") as f:
            f.write("40")
        env = dict(os.environ, HEAVY_HARNESS=json.dumps({
            "work": self.work, "status": os.path.join(self.cameras, "status"), "now": self.now, "free_file": free}))
        proc = subprocess.Popen([sys.executable, HARNESS, "--max-mb-s", "2"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        give_up = time.monotonic() + 30
        while time.monotonic() < give_up and not any(c.startswith(f"put {rel} ") for c in self.calls("put")):
            time.sleep(0.05)
        time.sleep(0.3)                                                     # into the 6 MB file's 3 s read
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130, out)
        self.assertIn("interrupted", out)
        self.assertStays(rel)
        self.assertFalse(os.path.exists(os.path.join(self.store, rel)))
        self.assertNoHiddenFiles()
        self.assertEqual(self.state()["result"], "interrupted")


class RefuseTest(Base):
    def setUp(self):
        super().setUp()
        self.d8, self.d9 = self.day(8), self.day(9)          # Oct 8 and Oct 7, whatever the clock says later
        self.archive(cams=(656,), days=(8, 9))

    def assertNothingSent(self):
        for d in (self.d8, self.d9):
            self.assertStays(self.rel(656, d))
            self.assertStays(self.rel(656, d, "csv"))

    def test_no_off_site_storage(self):
        self.faults(down=True)
        code, out = self.run_cv()
        self.assertEqual(code, 69, out)
        self.assertIn("the off-site storage can't be reached (ping: exit 255: ssh: connect to host", out)
        self.assertNothingSent()
        self.assertEqual(self.state()["result"], "off-site storage unreachable")

    def test_the_storage_going_away_stops_the_run(self):
        real = self.cv.send

        def send_then_go_away(*args):
            done = real(*args)
            self.faults(down=True)
            return done

        with mock.patch.object(self.cv, "send", send_then_go_away):
            code, out = self.run_cv()
        self.assertEqual(code, 69, out)
        self.assertSent(self.rel(656, self.d9))                  # the first, read back before it went away
        for rel in (self.rel(656, self.d9, "csv"), self.rel(656, self.d8), self.rel(656, self.d8, "csv")):
            self.assertStays(rel)
        self.assertEqual((self.state()["moved"], self.state()["left"]), (1, 3))

    def test_the_roll_up_comes_first(self):
        self.statuses(rolling=(False, True))
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("still going (regional-cameras)", out)
        self.statuses(ages=(10, 3 * 3600))                     # regional hasn't reported since 23:30
        self.assertEqual(self.run_cv()[0], 75)
        self.set_clock("2026-10-16 00:07")                     # just after 00:05: regional not checked yet
        self.statuses(ages=(10, 300))
        self.assertEqual(self.run_cv()[0], 75)
        self.assertNothingSent()
        self.assertEqual((self.state()["result"], self.state()["last_done"]), ("not now", None))

    def test_a_roll_up_holding_its_lock(self):
        fd = os.open(os.path.join(self.cameras, "rollup.lock"), os.O_RDONLY | os.O_CREAT)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("a camera roll-up holds rollup.lock", out)
        self.assertNothingSent()

    def test_another_run_going(self):
        fd = os.open(os.path.join(self.cameras, "cold-videos.lock"), os.O_RDONLY | os.O_CREAT)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertFalse(os.path.exists(os.path.join(self.cameras, "cold-videos.json")))   # its own to write
        self.assertNothingSent()

    def test_in_the_day_a_quiet_capture_service_doesnt_hold_it_back(self):
        self.set_clock("2026-10-16 09:00")
        self.statuses(ages=(10, 5 * 3600))
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertSent(self.rel(656, self.d8))

    def test_not_near_midnight(self):
        self.set_clock("2026-10-15 23:57")
        self.statuses()
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("tonight's camera roll-up", out)
        self.assertNothingSent()

    def test_a_run_stops_at_23_55(self):
        self.set_clock("2026-10-15 23:54")
        self.statuses()
        real = self.cv.send

        def slow_send(*args):
            self.h.OFFSET += 120                               # each file "takes" two minutes
            return real(*args)

        with mock.patch.object(self.cv, "send", slow_send):
            code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("stopped at 23:56 Boise", out)
        self.assertEqual((self.state()["moved"], self.state()["left"]), (0, 2))   # days up to Oct 7 here
        self.assertNothingSent()                               # sent, not read back: they go again

    def test_a_step_that_runs_past_midnight_still_stops(self):
        self.set_clock("2026-10-15 23:50")
        self.statuses()
        real = self.cv.send

        def slow_send(*args):
            self.h.OFFSET += 11 * 60                           # past 23:55, and past midnight
            return real(*args)

        with mock.patch.object(self.cv, "send", slow_send):
            code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("stopped at 00:01 Boise", out)
        self.assertNothingSent()

    def test_not_before_a_planned_restart(self):
        with open(os.path.join(self.work, "MAINTENANCE"), "w") as f:
            f.write("restart: 2026-10-16 02:40\n")
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("a VM restart is planned at 02:40", out)
        with open(os.path.join(self.work, "MAINTENANCE"), "w") as f:
            f.write("restart: 2026-10-16 10:00\n")
        self.assertEqual(self.run_cv()[0], 0)

    def test_settings(self):
        self.conf(OFFSITE_SSH=None)
        code, out = self.run_cv()
        self.assertEqual(code, 2, out)
        self.assertIn("(OFFSITE_SSH)", out)
        self.conf(OFFSITE_SSH="ssh -o 'unclosed")
        code, out = self.run_cv()
        self.assertEqual(code, 2, out)
        self.assertIn("OFFSITE_SSH in heavy.conf can't be read", out)
        self.conf(COLD_VIDEO_KEEP_DAYS="three")
        self.assertEqual(self.run_cv()[0], 2)
        self.conf()
        self.assertEqual(self.run_cv("--limit", "-1")[0], 2)
        self.assertNothingSent()


class OldLinksTest(Base):
    """The cold drive's links, from before Oct 30: each becomes an off-site link once its copy off-site reads
    back with the sha256 logged when it moved."""

    def setUp(self):
        super().setUp()
        self.drive = os.path.join(self.tmp, "drive", "vm", "cameras")          # gone: never made
        self.moved = {}
        lines = []
        for cam in (656, 752):
            for back in (20, 21):
                for path in self.camera_day(cam, self.day(back)):
                    rel = os.path.relpath(path, self.cameras)
                    digest, size = sha(path), os.path.getsize(path)
                    self.moved[rel] = (size, digest)
                    lines.append(f"2026-10-15T23:38:15Z moved {rel} ({size} bytes, sha256 {digest})")
                    stored = os.path.join(self.store, rel)                 # its copy, uploaded from the drive
                    os.makedirs(os.path.dirname(stored), exist_ok=True)
                    shutil.copy2(path, stored)
                    os.remove(path)
                    os.symlink(os.path.join(self.drive, rel), path)
        with open(os.path.join(self.cameras, "cold-videos.log"), "w") as f:
            f.write("\n".join(lines) + "\n")
        self.old = sorted(self.moved)

    def assertOldLink(self, rel):
        self.assertEqual(os.readlink(os.path.join(self.cameras, rel)), os.path.join(self.drive, rel))

    def test_old_links_become_off_site_links_once_read_back(self):
        missing, bad = self.old[0], self.old[1]
        os.remove(os.path.join(self.store, missing))                       # not uploaded yet
        self.faults(corrupt=[bad])
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        for rel in self.old[2:]:
            self.assertSent(rel, self.moved[rel][1])
        self.assertOldLink(missing)
        self.assertOldLink(bad)
        self.assertIn("8 files still link to the cold drive: 7 held off-site, to read back now; 1 not off-site yet",
                      out)
        self.assertIn(f"old link {bad}: its copy off-site doesn't match", out)
        self.assertIn(f"relinked {self.old[2]} ({self.moved[self.old[2]][0]} bytes, sha256 "
                      f"{self.moved[self.old[2]][1]}): its copy off-site, read back", out)
        state = self.state()
        self.assertEqual((state["relinked"], state["old_left"], state["old_bad"], state["code"]), (6, 2, 1, 0))
        self.assertFalse(self.calls("put"))                                # nothing sent for them
        self.assertNoHiddenFiles()

        with open(os.path.join(self.store, missing), "wb") as f:           # arrives, but not the logged size
            f.write(b"x" * 7)
        self.faults()
        verifies = len(self.calls("verify"))
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertIn("1 that didn't match lately", out)                    # not read back again so soon
        self.assertEqual(len(self.calls("verify")), verifies)
        self.assertOldLink(bad)
        self.assertOldLink(missing)
        self.assertEqual((self.state()["relinked"], self.state()["old_left"], self.state()["old_bad"]), (0, 2, 1))
        self.set_clock("2026-10-24 02:30")                                  # a week later: checked again
        self.statuses()
        self.assertEqual(self.run_cv()[0], 0)
        self.assertSent(bad, self.moved[bad][1])
        self.assertOldLink(missing)
        self.assertEqual((self.state()["relinked"], self.state()["old_left"], self.state()["old_bad"]), (1, 1, 0))

    def test_one_copy_that_cant_be_read_doesnt_hold_back_the_rest(self):
        self.faults(unreadable=[self.old[4]])
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertOldLink(self.old[4])
        for rel in self.old[:4] + self.old[5:]:
            self.assertSent(rel, self.moved[rel][1])
        self.assertIn("old links: 1 couldn't be read back this time", out)
        self.assertEqual((self.state()["relinked"], self.state()["old_left"], self.state()["old_bad"]), (7, 1, 0))

    def test_a_link_with_no_logged_sha256_keeps_its_old_link(self):
        with open(os.path.join(self.cameras, "cold-videos.log"), "w") as f:
            f.write("")
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertIn("8 with no sha256 in cold-videos.log", out)
        for rel in self.old:
            self.assertOldLink(rel)
        self.assertFalse(self.calls("verify"))

    def test_the_last_logged_move_counts(self):
        rel = self.old[3]
        with open(os.path.join(self.cameras, "cold-videos.log"), "a") as f:
            f.write(f"2026-10-16T08:00:00Z moved {rel} (5 bytes, sha256 {'0' * 64})\n")    # moved again since
        self.assertEqual(self.run_cv()[0], 0)
        self.assertOldLink(rel)
        self.assertEqual(self.state()["old_left"], 1)

    def test_limit_and_dry_run(self):
        before = self.snapshot()
        code, out = self.run_cv("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("8 files still link to the cold drive: 8 held off-site, to read back now", out)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.calls("verify"))
        self.assertEqual(self.run_cv("--limit", "3")[0], 0)                # a careful first run: none
        self.assertEqual((self.state()["relinked"], self.state()["old_left"]), (0, 8))
        self.cv.OLD_BATCH = 3
        self.assertEqual(self.run_cv()[0], 0)
        self.assertEqual((self.state()["relinked"], self.state()["old_left"]), (8, 0))
        self.assertEqual(len(self.calls("verify")), 3)                     # 3 + 3 + 2


class AuditTest(Base):
    def test_an_off_site_copy_that_goes_missing_is_flagged(self):
        self.archive(cams=(656,), days=(8, 9))
        self.assertEqual(self.run_cv()[0], 0)
        gone, shrunk = self.rel(656, self.day(9)), self.rel(656, self.day(8), "csv")
        os.remove(os.path.join(self.store, gone))
        with open(os.path.join(self.store, shrunk), "wb") as f:
            f.write(b"short")
        code, out = self.run_cv()
        self.assertEqual(code, 1, out)
        self.assertIn(f"MISSING off-site: {gone}: its link says offsite:1000:", out)
        self.assertIn(f"MISSING off-site: {shrunk}: its link says offsite:100:", out)
        self.assertIn("the storage holds 5 bytes", out)
        state = self.state()
        self.assertEqual((state["offsite_links"], state["offsite_missing"], state["result"]), (4, 2, "failed"))


class BringBackTest(Base):
    def setUp(self):
        super().setUp()
        self.archive(cams=(656,), days=(9,))
        self.video = self.rel(656, self.day(9))
        self.path = os.path.join(self.cameras, self.video)
        self.digest = sha(self.path)
        self.assertEqual(self.run_cv()[0], 0)
        self.assertSent(self.video, self.digest)

    def test_a_day_comes_back_checked(self):
        csv = os.path.join(self.cameras, self.rel(656, self.day(9), "csv"))
        code, out = self.run_cv("--bring-back", self.video, csv)
        self.assertEqual(code, 0, out)
        self.assertStays(self.video)
        self.assertEqual(sha(self.path), self.digest)
        self.assertIn(f"brought back {self.video} (1000 bytes, sha256 {self.digest})", self.log())
        self.assertTrue(os.path.isfile(csv) and not os.path.islink(csv))
        self.assertNoHiddenFiles()
        for path in (self.path, csv):
            os.utime(path, (self.t.timestamp() - 3600,) * 2)
        self.assertEqual(self.run_cv()[0], 0)                               # older than kept: it goes again
        self.assertSent(self.video, self.digest)

    def test_a_camera_day_comes_back_whole(self):
        code, out = self.run_cv("--bring-back", self.video)
        self.assertEqual(code, 0, out)
        self.assertStays(self.video)
        self.assertStays(self.rel(656, self.day(9), "csv"))

    def test_bytes_that_come_back_wrong_leave_the_link(self):
        self.faults(corrupt=[self.video])
        code, out = self.run_cv("--bring-back", self.video)
        self.assertEqual(code, 1, out)
        self.assertIn("isn't what was sent (its link stays)", out)
        self.assertSent(self.video, self.digest)
        self.assertNoHiddenFiles()

    def test_only_off_site_links_come_back(self):
        self.camera_day(752, self.day(2))
        code, out = self.run_cv("--bring-back", self.rel(752, self.day(2)), "video/656/2026/nothing.mp4")
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("not an off-site link"), 2)
        os.remove(os.path.join(self.store, self.video))                     # the storage lost it
        code, out = self.run_cv("--bring-back", self.video)
        self.assertEqual(code, 1, out)
        self.assertIn("(0 bytes, sha256", out)
        self.assertTrue(os.path.islink(self.path))
        self.assertNoHiddenFiles()

    def test_not_without_room(self):
        self.free = self.h.FLOOR_GB + 0.5
        code, out = self.run_cv("--bring-back", self.video)
        self.assertEqual(code, 1, out)
        self.assertIn("no room", out)
        self.assertTrue(os.path.islink(self.path))


class ReadersTest(Base):
    """The camera roll-up and the library index read the links (plugins/cameras)."""

    def test_the_library_index_marks_off_site_days_and_the_roll_up_counts_them_done(self):
        sys.path.insert(0, REPO)
        try:
            from plugins.cameras.ingest import camera_video
        finally:
            sys.path.remove(REPO)
        root = os.path.dirname(self.cameras)
        for back in (8, 9):
            self.camera_day(656, self.day(back))
        cams = [(656, "Eagle & Fairview")]
        camera_video.write_index(root, cams, "key_cameras", "Key cameras")
        self.assertEqual(self.run_cv()[0], 0)
        self.assertEqual(camera_video.write_index(root, cams, "key_cameras", "Key cameras"), 2)
        index = os.path.join(self.cameras, "video", "index-key_cameras.json")
        with open(index) as f:
            days = json.load(f)["cameras"][0]["days"]
        self.assertEqual([(d["day"], d["bytes"], d.get("offsite"), d.get("cold")) for d in days],
                         [(self.day(9).isoformat(), 1000, True, None), (self.day(8).isoformat(), 1000, True, None)])
        for back in (8, 9):                                                 # a JPEG folder left behind
            os.makedirs(os.path.join(self.cameras, "jpeg", "656", self.day(back).isoformat()))
        self.assertEqual(camera_video.pending(root, self.t.date()), [])    # the link counts as done
        os.remove(index)                                                    # an index made afresh
        self.assertEqual(camera_video.write_index(root, cams, "key_cameras", "Key cameras"), 2)
        with open(index) as f:
            days = json.load(f)["cameras"][0]["days"]
        self.assertEqual([(d["bytes"], d.get("offsite")) for d in days], [(1000, True), (1000, True)])
        path = os.path.join(self.cameras, self.rel(656, self.day(8)))
        os.remove(path)
        os.symlink("offsite:not-a-size", path)                              # a link it can't read
        os.remove(index)
        self.assertEqual(camera_video.write_index(root, cams, "key_cameras", "Key cameras"), 2)


if __name__ == "__main__":
    unittest.main()
