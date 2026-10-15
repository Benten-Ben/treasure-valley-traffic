"""Tests for deploy/bin/cold-videos: finished camera days older than a week move to the cold drive,
with symlinks left in their place (decision A1).

    python3 -m unittest discover -s deploy/tests

Against synthetic trees: a made-up camera archive, capture status files and work folder (heavy's
settings, which cold-videos reads), a fixed clock and fixed free disk. Nothing here touches the
real /srv or docker. On the VM, set COLD_VIDEOS_TEST_COLD to a scratch folder on the cold drive to
make the copies there (through the VM's share of the drive) instead of in a temporary folder.
"""
import datetime as dt
import fcntl
import hashlib
import io
import json
import os
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


def boise(text, tz):
    return dt.datetime.fromisoformat(text).replace(tzinfo=tz)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Base(unittest.TestCase):
    now = "2026-10-16 02:30"           # Boise: tonight's roll-up finished; days up to Oct 8 move

    def setUp(self):
        self.cv = cold_harness.load()
        self.h = h = self.cv.heavy
        self.tmp = tempfile.mkdtemp(prefix="tvt-cold-videos-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        base = os.environ.get("COLD_VIDEOS_TEST_COLD")
        self.mount = tempfile.mkdtemp(prefix="drive-", dir=base) if base else os.path.join(self.tmp, "cold")
        os.makedirs(self.mount, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.mount, True)
        self.work = os.path.join(self.tmp, "work")
        self.cameras = os.path.join(self.tmp, "archive", "cameras")
        self.marker = os.path.join(self.mount, ".tvt-cold-drive")
        self.folder = os.path.join(self.mount, "vm", "cameras")
        for d in (self.work, os.path.join(self.cameras, "status"), os.path.join(self.cameras, "video"), self.folder):
            os.makedirs(d, exist_ok=True)
        open(self.marker, "w").close()
        self.conf()
        h.WORK = self.work
        h.STATUS_DIR = os.path.join(self.cameras, "status")
        self.set_clock(self.now)
        self.cold_free_gb = 1500.0
        h.free_gb = lambda where: self.cold_free() if where == self.mount else 40.0
        self.statuses()

    def set_clock(self, text):
        self.t = boise(text, self.h.TZ)
        self.h.OFFSET = self.t.timestamp() - time.time()
        self.h.boot_time = lambda: self.t.timestamp() - self.h.OFFSET - 86400

    def conf(self, **extra):
        values = {"COLD_MOUNT": self.mount, "COLD_MARKER": self.marker, "COLD_KEEP_GB": "200",
                  "COLD_CAMERAS": self.folder, **extra}
        with open(os.path.join(self.work, "heavy.conf"), "w") as f:
            f.write("# the VM's own paths\n")
            for key, value in values.items():
                if value is not None:
                    f.write(f"{key}={value}\n")

    def cold_free(self):
        """What's free on the made-up drive: the starting figure less what the copies took."""
        used = 0
        for folder, _, names in os.walk(self.folder):
            used += sum(os.path.getsize(os.path.join(folder, n)) for n in names)
        return self.cold_free_gb - used / self.h.GB

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

    def assertMoved(self, rel):
        path = os.path.join(self.cameras, rel)
        self.assertTrue(os.path.islink(path), f"{rel} isn't a link")
        self.assertEqual(os.readlink(path), os.path.join(self.folder, rel))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, rel)))

    def assertStays(self, rel):
        path = os.path.join(self.cameras, rel)
        self.assertTrue(os.path.isfile(path) and not os.path.islink(path), f"{rel} moved")

    def snapshot(self):
        out = {}
        for root in (self.cameras, self.mount):
            for folder, dirs, names in os.walk(root):
                for n in dirs + names:
                    p = os.path.join(folder, n)
                    out[p] = (os.path.islink(p), os.readlink(p) if os.path.islink(p) else None,
                              None if os.path.isdir(p) or os.path.islink(p) else sha(p))
        return out


class MoveTest(Base):
    def test_days_older_than_a_week_move_and_links_take_their_place(self):
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
                    (self.assertMoved if back >= 8 else self.assertStays)(rel)
                    # Every reader keeps the same path and the same bytes.
                    self.assertEqual(sha(os.path.join(self.cameras, rel)), before[rel])
        copy = os.stat(os.path.join(self.folder, self.rel(656, self.day(8))))
        self.assertEqual((copy.st_size, copy.st_mtime_ns, copy.st_mode & 0o777),
                         (st.st_size, st.st_mtime_ns, st.st_mode & 0o777))       # same size, time and mode

        state = self.state()
        self.assertEqual((state["result"], state["code"], state["moved"], state["left"], state["failed"]),
                         ("done", 0, 12, 0, 0))
        self.assertEqual(state["cutoff"], self.day(8).isoformat())
        self.assertEqual(state["last_done"], state["finished"])
        log = self.log()
        self.assertEqual(log.count(" moved video/"), 12)
        rel = self.rel(752, self.day(10))
        self.assertIn(f"moved {rel} (1000 bytes, sha256 {before[rel]})", log)
        # Each day's CSV goes before its video, oldest day first.
        order = [line.split()[2] for line in log.splitlines() if " moved video/" in line]
        self.assertEqual(order[:4], [self.rel(656, self.day(10), "csv"), self.rel(656, self.day(10)),
                                     self.rel(752, self.day(10), "csv"), self.rel(752, self.day(10))])
        # No hidden part files or links left behind.
        for root in (self.cameras, self.mount):
            for folder, _, names in os.walk(root):
                self.assertFalse([n for n in names if n.endswith((".cold-part", ".cold-link"))])

    def test_a_second_run_moves_nothing(self):
        self.archive()
        self.assertEqual(self.run_cv()[0], 0)
        before = self.snapshot()
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.state()["moved"], 0)
        after = self.snapshot()
        after.pop(os.path.join(self.cameras, "cold-videos.log"))
        before.pop(os.path.join(self.cameras, "cold-videos.log"))
        after.pop(os.path.join(self.cameras, "cold-videos.json"))
        before.pop(os.path.join(self.cameras, "cold-videos.json"))
        self.assertEqual(before, after)

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
        self.assertMoved(self.rel(656, self.day(3)))
        self.assertMoved(self.rel(656, self.day(4), "csv"))
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
        self.assertMoved(self.rel(656, self.day(4)))

    def test_dry_run_changes_nothing(self):
        self.archive()
        before = self.snapshot()
        code, out = self.run_cv("--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"would move {self.rel(656, self.day(8))} (1000 bytes)", out)
        self.assertNotIn(f"would move {self.rel(656, self.day(7))}", out)
        self.assertEqual(self.snapshot(), before)

    def test_reads_are_paced(self):
        slept = []
        with mock.patch.object(self.cv.time, "sleep", slept.append):
            pace = self.cv.Pace(1)                       # 1 MB/s
            pace(500_000)
            pace(500_000)                                # (the fake sleep takes no time)
            self.cv.Pace(0)(10**9)                       # 0: no limit
        self.assertEqual(len(slept), 2)
        self.assertAlmostEqual(slept[-1], 1.0, delta=0.1)


class ResumeTest(Base):
    def test_a_copy_already_on_the_drive_is_checked_and_used(self):
        [video, csv] = self.camera_day(656, self.day(9))
        rel = self.rel(656, self.day(9))
        os.makedirs(os.path.dirname(os.path.join(self.folder, rel)))
        shutil.copy2(video, os.path.join(self.folder, rel))                 # the run before stopped here
        with open(os.path.join(os.path.dirname(os.path.join(self.folder, rel)),
                               "." + os.path.basename(csv) + ".cold-part"), "w") as f:
            f.write("half a copy")                                          # and a copy cut short
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertMoved(rel)
        self.assertMoved(self.rel(656, self.day(9), "csv"))
        self.assertIn(f"moved {rel} (1000 bytes, sha256 {sha(os.path.join(self.folder, rel))}): "
                      "its copy was already on the cold drive", out)
        self.assertEqual(sha(os.path.join(self.cameras, self.rel(656, self.day(9), "csv"))), sha(
            os.path.join(self.folder, self.rel(656, self.day(9), "csv"))))
        self.assertFalse([n for n in os.listdir(os.path.dirname(os.path.join(self.folder, rel)))
                          if n.endswith(".cold-part")])

    def test_a_different_copy_on_the_drive_is_replaced_by_the_one_readers_saw(self):
        [video, _] = self.camera_day(656, self.day(9))
        rel = self.rel(656, self.day(9))
        os.makedirs(os.path.dirname(os.path.join(self.folder, rel)))
        for stale in (b"y" * 1000, b"y" * 10):                              # same size, then another size
            with open(os.path.join(self.folder, rel), "wb") as f:
                f.write(stale)
            want = sha(video)
            code, out = self.run_cv()
            self.assertEqual(code, 0, out)
            self.assertMoved(rel)
            self.assertEqual(sha(os.path.join(self.folder, rel)), want)
            self.assertIn("replaced a different copy", out)
            os.remove(os.path.join(self.cameras, rel))                      # back as it was, for the second round
            shutil.copy2(os.path.join(self.folder, rel), os.path.join(self.cameras, rel))

    def test_a_copy_that_reads_back_wrong_keeps_the_original(self):
        self.archive(cams=(656,), days=(9, 10))
        real = self.cv.sha256_of
        self.cv.sha256_of = lambda path, pace, from_drive=False: "0" * 64 if from_drive else real(path, pace)
        try:
            code, out = self.run_cv()
        finally:
            self.cv.sha256_of = real
        self.assertEqual(code, 1, out)
        self.assertIn("doesn't match the original's sha256 (the original stays)", out)
        for back in (9, 10):
            self.assertStays(self.rel(656, self.day(back)))
        for folder, _, names in os.walk(self.folder):
            self.assertFalse(names, "nothing is left on the drive")
        self.assertEqual((self.state()["result"], self.state()["failed"], self.state()["left"]), ("failed", 4, 4))
        self.assertEqual(self.run_cv()[0], 0)                               # the next run moves them
        self.assertMoved(self.rel(656, self.day(9)))
        self.assertEqual(self.state()["last_done"], self.state()["finished"])

    def test_an_original_that_changes_while_copied_stays(self):
        [video, _] = self.camera_day(656, self.day(9))
        real = self.cv.copy_to

        def copy_then_change(src, tmp, st, pace):
            digest = real(src, tmp, st, pace)
            if src == video:
                with open(src + ".new", "wb") as f:
                    f.write(b"encoded again")
                os.replace(src + ".new", src)                               # a roll-up's rename
            return digest

        self.cv.copy_to = copy_then_change
        try:
            code, out = self.run_cv()
        finally:
            self.cv.copy_to = real
        self.assertEqual(code, 1, out)
        self.assertIn("the original changed while it was copied", out)
        self.assertStays(self.rel(656, self.day(9)))
        with open(video, "rb") as f:
            self.assertEqual(f.read(), b"encoded again")
        os.utime(video, (self.t.timestamp() - 3600,) * 2)
        self.assertEqual(self.run_cv()[0], 0)                               # next time: the new one moves
        with open(os.path.join(self.folder, self.rel(656, self.day(9))), "rb") as f:
            self.assertEqual(f.read(), b"encoded again")

    def test_stopped_by_sigterm_leaves_the_original_and_no_part_file(self):
        self.camera_day(656, self.day(9), size=6 * 2**20)
        free = os.path.join(self.tmp, "free")
        with open(free, "w") as f:
            f.write("1500")
        env = dict(os.environ, HEAVY_HARNESS=json.dumps({
            "work": self.work, "status": os.path.join(self.cameras, "status"), "now": self.now, "free_file": free}))
        proc = subprocess.Popen([sys.executable, HARNESS, "--max-mb-s", "2"], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        part = os.path.join(self.folder, "video", "656", f"{self.day(9):%Y}", f".656-{self.day(9)}.csv.cold-part")
        give_up = time.monotonic() + 20
        while time.monotonic() < give_up and not os.path.exists(part.replace(".csv.", ".mp4.")):
            time.sleep(0.05)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130, out)
        self.assertIn("interrupted", out)
        self.assertStays(self.rel(656, self.day(9)))
        for folder, _, names in os.walk(self.folder):
            self.assertFalse([n for n in names if n.endswith(".cold-part")], names)
        self.assertEqual(self.state()["result"], "interrupted")


class RefuseTest(Base):
    def setUp(self):
        super().setUp()
        self.d8, self.d9 = self.day(8), self.day(9)          # Oct 8 and Oct 7, whatever the clock says later
        self.archive(cams=(656,), days=(8, 9))

    def assertNothingMoved(self):
        for d in (self.d8, self.d9):
            self.assertStays(self.rel(656, d))
            self.assertStays(self.rel(656, d, "csv"))

    def test_no_cold_drive(self):
        os.remove(self.marker)
        code, out = self.run_cv()
        self.assertEqual(code, 69, out)
        self.assertIn("the cold drive isn't mounted", out)
        self.assertNothingMoved()
        self.assertEqual(self.state()["result"], "no cold drive")

    def test_the_drive_keeps_its_free_space(self):
        self.cold_free_gb = 200.0
        code, out = self.run_cv()
        self.assertEqual(code, 73, out)
        self.assertNothingMoved()
        # Room for exactly three of the four files: the oldest day, then the next day's CSV.
        self.cold_free_gb = 200.0 + (1000 + 100 + 100) / self.h.GB + 1e-12
        code, out = self.run_cv()
        self.assertEqual(code, 73, out)
        self.assertMoved(self.rel(656, self.d9))
        self.assertMoved(self.rel(656, self.d8, "csv"))
        self.assertStays(self.rel(656, self.d8))
        self.assertEqual((self.state()["moved"], self.state()["left"]), (3, 1))

    def test_the_drive_going_away_stops_the_run(self):
        real = self.cv.move

        def move_then_unplug(rel, cameras, cold, pace):
            done = real(rel, cameras, cold, pace)
            os.remove(self.marker)
            return done

        self.cv.move = move_then_unplug
        try:
            code, out = self.run_cv()
        finally:
            self.cv.move = real
        self.assertEqual(code, 69, out)
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
        self.assertNothingMoved()
        self.assertEqual((self.state()["result"], self.state()["last_done"]), ("not now", None))

    def test_a_roll_up_holding_its_lock(self):
        fd = os.open(os.path.join(self.cameras, "rollup.lock"), os.O_RDONLY | os.O_CREAT)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("a camera roll-up holds rollup.lock", out)
        self.assertNothingMoved()

    def test_another_run_going(self):
        fd = os.open(os.path.join(self.cameras, "cold-videos.lock"), os.O_RDONLY | os.O_CREAT)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertFalse(os.path.exists(os.path.join(self.cameras, "cold-videos.json")))   # its own to write

    def test_in_the_day_a_quiet_capture_service_doesnt_hold_it_back(self):
        self.set_clock("2026-10-16 09:00")
        self.statuses(ages=(10, 5 * 3600))
        code, out = self.run_cv()
        self.assertEqual(code, 0, out)
        self.assertMoved(self.rel(656, self.d8))

    def test_not_near_midnight(self):
        self.set_clock("2026-10-15 23:57")
        self.statuses()
        code, out = self.run_cv()
        self.assertEqual(code, 75, out)
        self.assertIn("tonight's camera roll-up", out)
        self.assertNothingMoved()

    def test_a_run_stops_at_23_55(self):
        self.set_clock("2026-10-15 23:54")
        self.statuses()
        real = self.cv.move

        def slow_move(*args):
            self.h.OFFSET += 120                               # each file "takes" two minutes
            return real(*args)

        self.cv.move = slow_move
        try:
            code, out = self.run_cv()
        finally:
            self.cv.move = real
        self.assertEqual(code, 75, out)
        self.assertIn("stopped at 23:56 Boise", out)
        self.assertEqual((self.state()["moved"], self.state()["left"]), (1, 1))   # days up to Oct 7 here

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
        self.conf(COLD_CAMERAS=None)
        self.assertEqual(self.run_cv()[0], 2)
        self.conf(COLD_CAMERAS=os.path.join(self.tmp, "elsewhere"))
        code, out = self.run_cv()
        self.assertEqual(code, 2)
        self.assertIn("inside COLD_MOUNT", out)
        self.conf(COLD_CAMERAS=os.path.join(self.mount, "vm", "nothing-here"))
        code, out = self.run_cv()
        self.assertEqual(code, 2)
        self.assertIn("make it first", out)
        self.conf(COLD_MOUNT=None)
        self.assertEqual(self.run_cv()[0], 2)
        self.assertNothingMoved()

    def test_the_camera_folder_on_the_drive_cant_be_the_archive(self):
        before = {rel: sha(os.path.join(self.cameras, rel)) for d in (self.d8, self.d9)
                  for rel in (self.rel(656, d), self.rel(656, d, "csv"))}
        self.h.free_gb = lambda where: 1500.0                               # room enough, wherever it looks
        archive = os.path.dirname(self.cameras)
        drive = os.path.join(self.tmp, "drive2")                           # beside the archive, never on
        os.makedirs(drive)                                                  # the real cold drive
        os.symlink(self.cameras, os.path.join(drive, "cameras"))
        for mount, folder in ((archive, self.cameras),                     # the archive itself
                              (drive, os.path.join(drive, "cameras")),      # reached through a link
                              (self.tmp, archive),                          # around it
                              (self.cameras, os.path.join(self.cameras, "video"))):   # inside it
            with self.subTest(folder=folder):
                marker = os.path.join(mount, ".tvt-cold-drive")
                open(marker, "w").close()
                self.conf(COLD_MOUNT=mount, COLD_MARKER=marker, COLD_CAMERAS=folder)
                code, out = self.run_cv()
                self.assertEqual(code, 2, out)
                self.assertIn("the camera archive", out)
                self.assertNothingMoved()
        for rel, digest in before.items():
            self.assertEqual(sha(os.path.join(self.cameras, rel)), digest)

    def test_a_file_that_is_its_own_copy_stays(self):
        """However the drive's folder reaches the archive (a bind mount, a hard link), a file is never
        replaced by a link to itself."""
        rel = self.rel(656, self.d9)
        src = os.path.join(self.cameras, rel)
        digest = sha(src)
        alias = os.path.join(self.tmp, "alias")                             # a hard link beside the archive,
        os.makedirs(os.path.dirname(os.path.join(alias, rel)))              # never on the real cold drive
        os.link(src, os.path.join(alias, rel))
        for folder in (self.cameras, alias):                                # past cold_settings' checks
            with self.subTest(folder=folder):
                cold = self.cv.Cold(self.mount, self.marker, 200.0, folder)
                with self.assertRaises(self.cv.Stop) as caught:
                    self.cv.move(rel, self.cameras, cold, self.cv.Pace(0))
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("is the file itself", str(caught.exception))
                self.assertStays(rel)
                self.assertEqual(sha(src), digest)
                self.assertFalse([n for n in os.listdir(os.path.dirname(src)) if n.startswith(".")])


class ReadersTest(Base):
    """The camera roll-up and the library index read through the links (plugins/cameras)."""

    def test_the_library_index_marks_moved_days_and_keeps_them_while_the_drive_is_away(self):
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
        self.assertEqual([(d["day"], d["bytes"], d.get("cold")) for d in days],
                         [(self.day(9).isoformat(), 1000, True), (self.day(8).isoformat(), 1000, True)])
        self.assertEqual(camera_video.pending(root, self.t.date()), [])
        shutil.rmtree(self.folder)                                          # the drive away
        self.assertEqual(camera_video.write_index(root, cams, "key_cameras", "Key cameras"), 2)
        self.assertEqual(camera_video.pending(root, self.t.date()), [])


if __name__ == "__main__":
    unittest.main()
