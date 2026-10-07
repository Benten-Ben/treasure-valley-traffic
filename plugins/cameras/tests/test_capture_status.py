"""The capture services' status file (docs/14 §14.6, "Live images"): written each
cycle by plugins/cameras/ingest/sources/idaho511_frames.py, read by the app (archive.ts).

Offline: a fake 511 and a fake clock, in a temporary archive.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from collections import namedtuple
from unittest import mock

from plugins.cameras.ingest.sources import idaho511_frames

# A synthetic flat-gray 16x8 JPEG (ffmpeg), not a camera image.
JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010200000100010000fffe00104c61766336302e33312e31303200ffdb0043000828282f28"
    "2f373737373737413c414343434141414143434348484855555548484843434848505055555c5f5c575755575f5f6464"
    "64787873738c8c91acaccfffc4004c000101000000000000000000000000000000030101010000000000000000000000"
    "0000000203100100000000000000000000000000000000110100000000000000000000000000000000ffc00011080008"
    "001003012200021100031100ffda000c03010002110311003f00b0089bffd9")

Usage = namedtuple("Usage", "total used free")


class StopLoop(Exception):
    pass


class FakeTime:
    """time.time/monotonic/sleep for the stream: sleeping moves the clock. Stops the loop
    once `limit` seconds have passed."""

    def __init__(self, start, limit):
        self.t, self.m, self.start, self.limit = start, 1000.0, start, limit

    def time(self):
        return self.t

    def monotonic(self):
        return self.m

    def sleep(self, s):
        self.t += s
        self.m += s
        if self.t - self.start >= self.limit:
            raise StopLoop


class WriteStatusTest(unittest.TestCase):
    def test_writes_the_fields_the_app_reads_atomically(self):
        with tempfile.TemporaryDirectory() as root:
            out = idaho511_frames.write_status(root, "key_cameras", 50, [656, "674"], now=1791309375.25)
            path = os.path.join(root, "cameras", "status", "key_cameras.json")
            with open(path) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk, out)
            self.assertEqual(on_disk, {
                "version": 1, "tag": "key_cameras", "cadence_s": 50, "image_ids": [656, 674],
                "heartbeat": 1791309375.25, "heartbeat_at": "2026-10-06T17:56:15Z",
                "paused_low_disk": False, "rolling_up": False})
            self.assertEqual(os.listdir(os.path.dirname(path)), ["key_cameras.json"])   # no .part left

            idaho511_frames.write_status(root, "key_cameras", 50, [656], paused_low_disk=True, now=1791309425.0)
            with open(path) as f:
                again = json.load(f)
            self.assertEqual((again["image_ids"], again["paused_low_disk"], again["heartbeat"]), ([656], True, 1791309425.0))

    def test_tags_are_kept_to_safe_file_names(self):
        self.assertTrue(idaho511_frames.status_path("/a", "../x y").endswith(os.path.join("cameras", "status", ".._x_y.json")))
        self.assertEqual(os.path.dirname(idaho511_frames.status_path("/a", "../x")), os.path.join("/a", "cameras", "status"))


class StreamStatusTest(unittest.TestCase):
    def run_stream(self, free, limit, every=50):
        """Run the stream on two cameras until the fake clock has moved `limit` seconds."""
        root = self.enterContext(tempfile.TemporaryDirectory())
        cams = os.path.join(root, "regional-cameras.csv")
        with open(cams, "w") as f:
            f.write("image_id,name\n9001,Station A\n9002,Station B\n")
        clock = FakeTime(1791309375.0, limit)
        fetched = []

        def fake_get(url, timeout=90, compressed=False):
            fetched.append(url)
            return 200, JPEG + str(len(fetched)).encode() + b"\xff\xd9", "allowed"

        env = {"TVT_ARCHIVE": root, "TVT_CAMERAS": cams}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(idaho511_frames, "time", clock), \
                mock.patch.object(idaho511_frames.http, "get", fake_get), \
                mock.patch.object(idaho511_frames.shutil, "disk_usage", lambda p: Usage(1, 0, free)), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(StopLoop):
                idaho511_frames.stream(every)
        with open(os.path.join(root, "cameras", "status", "regional-cameras.json")) as f:
            return json.load(f), fetched, clock

    def test_each_cycle_writes_a_fresh_status(self):
        status, fetched, clock = self.run_stream(free=100 * 2**30, limit=120, every=50)
        self.assertEqual(status["tag"], "regional-cameras")
        self.assertEqual(status["cadence_s"], 50)
        self.assertEqual(status["image_ids"], [9001, 9002])
        self.assertFalse(status["paused_low_disk"])
        self.assertGreater(len(fetched), 2)                                # more than one cycle ran
        self.assertEqual(status["heartbeat"], clock.start + 100)           # the third cycle, at 100 s
        self.assertLessEqual(clock.t - status["heartbeat"], 3 * status["cadence_s"])

    def test_a_low_disk_pause_shows_in_the_status(self):
        status, fetched, _ = self.run_stream(free=1 * 2**30, limit=60)
        self.assertTrue(status["paused_low_disk"])
        self.assertEqual(fetched, [])


if __name__ == "__main__":
    unittest.main()
