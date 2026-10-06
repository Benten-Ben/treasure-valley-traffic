"""Offline tests for the key-camera frame stream and the daily videos.

Run: python3 -m unittest discover -s ingest/tests -t .
The encode test needs ffmpeg with libsvtav1 and is skipped without it.
"""

import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from ingest import camera_video as cv
from ingest.sources import idaho511_frames as frames

UTC = timezone.utc


def fake_jpeg(width=768, height=466, payload=b""):
    """Headers only: SOI, an APP0 segment, a baseline frame header, EOI."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\0" + b"\x01\x01\0\0\x01\0\x01\0\0"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof0 + payload + b"\xff\xd9"


def row(ts, name="x.jpg"):
    return {"fetched_at": ts.strftime(cv.TS_FORMAT), "file": name, "bytes": "100", "sha256": "ab"}


class DayTest(unittest.TestCase):
    def test_local_day_follows_boise_time(self):
        self.assertEqual(cv.local_day(datetime(2026, 10, 6, 5, 59, tzinfo=UTC)), date(2026, 10, 5))   # 11:59 PM MDT
        self.assertEqual(cv.local_day(datetime(2026, 10, 6, 6, 0, tzinfo=UTC)), date(2026, 10, 6))

    def test_daylight_saving_days(self):
        lengths = {d: (lambda s, e: (e - s).total_seconds() / 3600)(*cv.day_bounds(d))
                   for d in (date(2026, 10, 5), date(2026, 11, 1), date(2026, 3, 8))}
        self.assertEqual(lengths, {date(2026, 10, 5): 24, date(2026, 11, 1): 25, date(2026, 3, 8): 23})

    def test_paths(self):
        self.assertEqual(cv.video_path("/a", 656, date(2026, 10, 5)),
                         os.path.join("/a", "cameras", "video", "656", "2026", "656-2026-10-05.mkv"))
        self.assertEqual(frames.frame_name(datetime(2026, 10, 6, 0, 15, 3, tzinfo=UTC)), "20261006T001503Z.jpg")


class PlanTest(unittest.TestCase):
    day = date(2026, 10, 5)
    midnight = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)          # local midnight in UTC

    def test_video_time_reads_as_clock_time(self):
        rows = [row(self.midnight + timedelta(hours=7, minutes=30, seconds=s)) for s in (0, 59, 118)]
        rows = [row(self.midnight + timedelta(seconds=30))] + rows
        entries = cv.plan(rows, self.day)
        frames_at = [round(e[0], 3) for e in entries if e[2] == "frame"]
        self.assertEqual(frames_at, [0.5, 450.0, 450.983, 451.967])            # 7:30 into the video = 7:30 AM

    def test_gaps_show_gray(self):
        rows = [row(self.midnight + timedelta(hours=19, minutes=m)) for m in (0, 1, 30)]
        kinds = [e[2] for e in cv.plan(rows, self.day)]
        # gray before the first frame, after the 29-minute gap, and after the last frame until midnight
        self.assertEqual(kinds, ["gap", "frame", "frame", "gap", "frame", "gap"])
        entries = cv.plan(rows, self.day)
        self.assertAlmostEqual(entries[2][1], 1.0)                              # frame 2 stays up 60 s (1 s of video)
        self.assertAlmostEqual(entries[-1][0] + entries[-1][1], 24 * 60)        # the video ends at midnight

    def test_slow_cameras_get_a_longer_gap_threshold(self):
        # a road-weather view: a frame every 15 minutes, then 2 hours with none
        minutes = list(range(0, 300, 15)) + [420, 435]
        rows = [row(self.midnight + timedelta(hours=8, minutes=m)) for m in minutes]
        kinds = [e[2] for e in cv.plan(rows, self.day)]
        self.assertEqual(kinds.count("gap"), 3)                                 # before, the 2-hour hole, after
        self.assertEqual(kinds[1:21], ["frame"] * 20)                           # 15-minute spacing isn't a gap

    def test_durations_add_up_to_the_day(self):
        rows = [row(self.midnight + timedelta(seconds=40 + 59 * i)) for i in range(1464)]
        entries = cv.plan(rows, self.day)
        self.assertAlmostEqual(entries[0][0] + sum(e[1] for e in entries), 24 * 60, places=6)
        self.assertTrue(all(e[1] > 0 for e in entries))

    def test_concat_list(self):
        rows = [row(self.midnight + timedelta(seconds=10), "a.jpg"), row(self.midnight + timedelta(seconds=70), "b.jpg")]
        text = cv.concat_list(cv.plan(rows, self.day), "/d", "/g.jpg")
        self.assertTrue(text.startswith("ffconcat version 1.0\nfile '/d/a.jpg'\nduration 1.000000\nfile '/d/b.jpg'\n"))


class FrameStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_jpeg_checks(self):
        path = os.path.join(self.root, "f.jpg")
        with open(path, "wb") as f:
            f.write(fake_jpeg(704, 426))
        self.assertEqual(cv.jpeg_size(path), (704, 426))
        self.assertTrue(frames.is_jpeg(fake_jpeg()))
        self.assertFalse(frames.is_jpeg(fake_jpeg()[:-2]))                      # cut off: no end marker
        self.assertFalse(frames.is_jpeg(b"<html>busy</html>"))

    def test_save_indexes_by_local_day_and_restart_knows_the_last_frame(self):
        late = datetime(2026, 10, 6, 5, 59, 30, tzinfo=UTC)                     # 11:59:30 PM MDT on Oct 5
        frames.save(self.root, 656, fake_jpeg(), late, "d1")
        frames.save(self.root, 656, fake_jpeg(), late + timedelta(seconds=59), "d2")   # Oct 6 locally
        oct5 = cv.read_index(os.path.join(cv.jpeg_dir(self.root, 656, date(2026, 10, 5)), cv.INDEX))
        self.assertEqual([(r["fetched_at"], r["file"], r["sha256"]) for r in oct5],
                         [("2026-10-06T05:59:30Z", "20261006T055930Z.jpg", "d1")])
        self.assertEqual(frames.last_digests(self.root, [(656, ""), (752, "")], date(2026, 10, 6)), {656: "d2"})

    def test_pending_and_prune(self):
        for d in (date(2026, 10, 1), date(2026, 10, 4), date(2026, 10, 5)):
            frames.save(self.root, 656, fake_jpeg(), datetime.combine(d, datetime.min.time(), UTC) + timedelta(hours=18), "x")
        today = date(2026, 10, 5)
        self.assertEqual(cv.pending(self.root, today), [("656", date(2026, 10, 1)), ("656", date(2026, 10, 4))])
        done = cv.video_path(self.root, "656", date(2026, 10, 1))
        os.makedirs(os.path.dirname(done))
        open(done, "w").close()
        open(cv.failed_path(self.root, "656", date(2026, 10, 4)), "w").close()
        self.assertEqual(cv.pending(self.root, today), [])                      # done, and failed (not retried)
        self.assertEqual(cv.pending(self.root, date(2026, 10, 6), {"752"}), [])  # another service's cameras
        self.assertEqual(cv.prune(self.root, today, 3), [("656", date(2026, 10, 1))])
        self.assertTrue(os.path.isdir(cv.jpeg_dir(self.root, "656", date(2026, 10, 4))))   # no video yet: kept

    def test_rollup_due_after_five_past_midnight(self):
        at = lambda h, m: datetime(2026, 10, 6, h, m, tzinfo=cv.TZ)
        self.assertFalse(frames.rollup_due(at(0, 4)))
        self.assertTrue(frames.rollup_due(at(0, 5)))

    def test_key_cameras_list(self):
        cams = frames.load_cameras()
        self.assertEqual(len(cams), len({c for c, _ in cams}))                # no duplicates
        self.assertTrue(30 <= len(cams) <= 40)
        self.assertIn((656, "Eagle & Fairview"), cams)


def _has_svtav1():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return "libsvtav1" in out


@unittest.skipUnless(_has_svtav1(), "needs ffmpeg with libsvtav1")
class EncodeTest(unittest.TestCase):
    def test_a_day_becomes_a_video_with_its_index(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        day = date(2026, 10, 5)
        start = datetime(2026, 10, 6, 1, 0, tzinfo=UTC)                         # 7 PM MDT
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=1",
                            "-frames:v", "5", os.path.join(tmp, "s%d.jpg")], check=True)
            for i in range(5):
                with open(os.path.join(tmp, f"s{i + 1}.jpg"), "rb") as f:
                    frames.save(root, 656, f.read(), start + timedelta(seconds=59 * i), f"h{i}")
        stats = cv.encode(root, "656", day)
        self.assertEqual((stats["frames"], stats["gaps"]), (5, 2))              # gray before 7 PM and after 7:05 PM
        video = cv.video_path(root, "656", day)
        self.assertEqual(cv.count_frames(video), 7)
        index = cv.read_index(video[:-4] + ".csv")
        self.assertEqual([r["kind"] for r in index], ["gap"] + ["frame"] * 5 + ["gap"])
        self.assertEqual(index[1]["video_s"], "1140.000")                        # 19:00 -> 19 min into the video
        self.assertEqual(cv.encode(root, "656", day), {"skipped": "video exists"})
        self.assertEqual(cv.pending(root, date(2026, 10, 6)), [])

    def test_odd_sized_frames_are_cropped_to_even(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root)
        start = datetime(2026, 10, 6, 1, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=329x339:rate=1",
                            "-frames:v", "3", os.path.join(tmp, "s%d.jpg")], check=True)
            for i in range(3):
                with open(os.path.join(tmp, f"s{i + 1}.jpg"), "rb") as f:
                    frames.save(root, 349, f.read(), start + timedelta(seconds=600 * i), f"o{i}")
        stats = cv.encode(root, "349", date(2026, 10, 5))
        self.assertEqual(stats["frames"], 3)
        size = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                               cv.video_path(root, "349", date(2026, 10, 5))], capture_output=True, text=True).stdout.strip()
        self.assertEqual(size, "328,338")


if __name__ == "__main__":
    unittest.main()
