"""Daily camera videos: one camera's JPEGs for one local day, rolled up into
one AV1 video (docs/11 §11.5; format approved by the owner Oct 5).

- **Codec:** SVT-AV1, preset 6, crf30, a keyframe every 60 pictures, in MP4 (MKV until Oct 6, 2026: browsers
  don't play MKV, so the video library needs MP4; old MKVs are remuxed, losslessly).
- **Day:** local midnight to midnight (America/Boise), so a file is one
  calendar day as people read it. Daylight-saving days run 23 or 25 hours.
- **A 60x time-lapse with true spacing:** one minute of the day is one second
  of video, so the video's mm:ss reads as the clock's hh:mm (7:30 into the
  video is 7:30 AM). Gaps longer than 10 minutes, or 3 times the camera's
  usual spacing if that's longer (road-weather views change less often),
  show as plain gray.
- **A sidecar CSV** lists every frame: where it sits in the video, when it
  was fetched, and the original JPEG's size and SHA-256.

The frame stream (sources/idaho511_frames.py) runs this after midnight, and
keeps the video library's index (index-<list>.json, read by the page in
deploy/library/) up to date. By hand:
    python3 -m ingest rollup [--day YYYY-MM-DD] [--camera ID ...] [--force]

Layout under TVT_ARCHIVE:
    cameras/jpeg/<image_id>/<YYYY-MM-DD>/<UTC time>.jpg and index.csv
    cameras/video/<image_id>/<YYYY>/<image_id>-<YYYY-MM-DD>.mp4 and .csv
    cameras/video/index-<list>.json
"""

import argparse
import contextlib
import csv
import fcntl
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Boise")
SPEEDUP = 60          # one minute of the day per second of video
GAP_S = 600           # a gap longer than this (or 3x the day's median spacing) shows as gray
LAST_FRAME_S = 60     # how long a frame stays up before a gap turns gray
# A keyframe every 60 pictures (about an hour of a key camera's day) so the library can seek
# quickly; it cost nothing in a test on Oct 6 (1-2% smaller than every 600; docs/11 §11.5).
CODEC = ["-c:v", "libsvtav1", "-preset", "6", "-crf", "30", "-g", "60"]
WORKERS = 4            # encodes side by side, at most
# One encode's peak memory grows with the frame size (measured on the server Oct 7, SVT-AV1 1.7
# preset 6 on 8 cores): about 0.66 GB at 328x339, 0.9 GB at 800x486 and 2.3 GB at 1920x1166.
# Two roll-ups of four encodes each, next to a tile build, once filled the server's 16 GB
# (Oct 7), so encodes start only while their estimates fit this budget, and one roll-up
# runs at a time (LOCK).
MEMORY_MB = int(os.environ.get("TVT_ROLLUP_MEMORY_MB", "6000"))
LOCK = "rollup.lock"   # in TVT_ARCHIVE/cameras, held by whichever roll-up is running
INDEX = "index.csv"
INDEX_FIELDS = ["fetched_at", "file", "bytes", "sha256"]
VIDEO_FIELDS = ["video_s", "kind", "fetched_at", "local_time", "file", "bytes", "sha256"]
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def jpeg_dir(root, cam, day):
    return os.path.join(root, "cameras", "jpeg", str(cam), day.isoformat())


def video_path(root, cam, day):
    return os.path.join(root, "cameras", "video", str(cam), f"{day:%Y}", f"{cam}-{day.isoformat()}.mp4")


def legacy_path(root, cam, day):
    """Where a day's video was written before Oct 6, 2026 (MKV)."""
    return video_path(root, cam, day)[:-4] + ".mkv"


def failed_path(root, cam, day):
    return video_path(root, cam, day) + ".failed"


def local_day(ts):
    return ts.astimezone(TZ).date()


def day_bounds(day):
    """The local day's start and end, in UTC (so subtraction counts real seconds on DST days)."""
    start = datetime.combine(day, time(0), TZ).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time(0), TZ).astimezone(timezone.utc)
    return start, end


def parse_ts(text):
    return datetime.strptime(text, TS_FORMAT).replace(tzinfo=timezone.utc)


def read_index(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def jpeg_size(path):
    """(width, height) from a JPEG's frame header."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"not a JPEG: {path}")
    i = 2
    while i + 9 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:                                   # fill byte
            i += 1
            continue
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    raise ValueError(f"no frame header in {path}")


def plan(rows, day):
    """The video's entries as (video_s, duration_s, kind, row), kind 'frame' or 'gap'.

    A frame fetched at local time T sits at (T - midnight) / 60 seconds. A frame
    stays up until the next one; if that's more than the gap threshold away
    (GAP_S, or 3 times the day's median spacing if longer), it stays up for
    LAST_FRAME_S and a gray gap fills the rest. Likewise before the first frame
    and after the last."""
    start, end = day_bounds(day)
    rows = sorted(rows, key=lambda r: r["fetched_at"])
    times = [parse_ts(r["fetched_at"]) for r in rows]
    at = lambda t: (t - start).total_seconds() / SPEEDUP
    spacings = sorted((b - a).total_seconds() for a, b in zip(times, times[1:]))
    gap_s = max(GAP_S, 3 * spacings[(len(spacings) - 1) // 2]) if spacings else GAP_S   # lower median
    entries = []
    if times and (times[0] - start).total_seconds() > gap_s:
        entries.append((0.0, "gap", None))
    for i, (t, row) in enumerate(zip(times, rows)):
        entries.append((at(t), "frame", row))
        following = times[i + 1] if i + 1 < len(times) else end
        if (following - t).total_seconds() > gap_s:
            entries.append((at(t + timedelta(seconds=LAST_FRAME_S)), "gap", None))
    ends = [e[0] for e in entries[1:]] + [at(end)]
    return [(s, e - s, kind, row) for (s, kind, row), e in zip(entries, ends)]


def _quote(path):
    return "'" + path.replace("'", "'\\''") + "'"


def concat_list(entries, src_dir, gray):
    lines = ["ffconcat version 1.0"]
    for _, duration, kind, row in entries:
        lines.append("file " + _quote(gray if kind == "gap" else os.path.join(src_dir, row["file"])))
        lines.append(f"duration {duration:.6f}")
    return "\n".join(lines) + "\n"


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        tail = [ln for ln in r.stderr.splitlines() if not ln.startswith("Svt[")][-3:]
        tool = next((c for c in cmd if c in ("ffmpeg", "ffprobe")), cmd[0])
        raise RuntimeError(f"{tool} failed: {' / '.join(tail)}")
    return r.stdout


def count_frames(path):
    return int(_run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                     "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", path]).strip())


def remux(src, out):
    """Copy a video into MP4 without re-encoding, checking every frame made it."""
    part = out + ".part"
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", src,
          "-map", "0", "-c", "copy", "-movflags", "+faststart", "-f", "mp4", part])
    want, got = count_frames(src), count_frames(part)
    if want != got:
        os.remove(part)
        raise RuntimeError(f"remux of {src} has {got} frames, expected {want}")
    os.replace(part, out)
    return got


def encode(root, cam, day, force=False):
    """Roll one camera's day into a video. Returns stats, or None if there were no frames.
    A day that already has an MKV from before Oct 6, 2026 is remuxed into MP4 instead."""
    src = jpeg_dir(root, cam, day)
    out = video_path(root, cam, day)
    legacy = legacy_path(root, cam, day)
    if os.path.exists(legacy) and not os.path.exists(out) and not force:
        frames = remux(legacy, out)
        os.remove(legacy)
        return {"remuxed": frames, "video_bytes": os.path.getsize(out)}
    index = os.path.join(src, INDEX)
    if not os.path.exists(index):
        return None
    if os.path.exists(out) and not force:
        return {"skipped": "video exists"}
    rows = [r for r in read_index(index) if os.path.exists(os.path.join(src, r["file"]))]
    if not rows:
        return None
    width, height = Counter(jpeg_size(os.path.join(src, r["file"])) for r in rows).most_common(1)[0][0]
    entries = plan(rows, day)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        gray = os.path.join(tmp, "gray.jpg")                  # a JPEG too: the concat input can't switch codecs
        if any(kind == "gap" for _, _, kind, _ in entries):
            _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi",
                  "-i", f"color=c=0x808080:s={width}x{height}", "-frames:v", "1", "-c:v", "mjpeg", gray])
        listing = os.path.join(tmp, "frames.ffconcat")
        with open(listing, "w") as f:
            f.write(concat_list(entries, src, gray))
        part = out + ".part"
        _run(["nice", "-n", "10", "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
              "-f", "concat", "-safe", "0", "-i", listing,
              # Odd sizes (e.g. 328x339) are cropped by one pixel: the encoder needs even ones.
              "-vf", f"scale={width}:{height},crop={width - width % 2}:{height - height % 2}:0:0,format=yuv420p",
              "-fps_mode", "vfr", *CODEC,
              "-metadata", f"title=511 Idaho camera {cam}, {day.isoformat()} (America/Boise)",
              "-metadata", "comment=One second of video is one minute of the day: mm:ss reads as hh:mm. "
                           "Gray means no frames. Frame times are in the .csv beside this file.",
              "-movflags", "+faststart", "-f", "mp4", part])
        frames = count_frames(part)
        if frames != len(entries):
            os.remove(part)
            raise RuntimeError(f"video has {frames} frames, expected {len(entries)}")
    sidecar = out[:-4] + ".csv"
    with open(sidecar + ".part", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(VIDEO_FIELDS)
        for video_s, _, kind, row in entries:
            if kind == "gap":
                w.writerow([f"{video_s:.3f}", "gap", "", "", "", "", ""])
            else:
                local = parse_ts(row["fetched_at"]).astimezone(TZ)
                w.writerow([f"{video_s:.3f}", "frame", row["fetched_at"], local.isoformat(),
                            row["file"], row["bytes"], row["sha256"]])
    os.replace(sidecar + ".part", sidecar)
    os.replace(part, out)                                    # the video appears last: it marks the day done
    if os.path.exists(legacy):
        os.remove(legacy)
    jpeg_bytes = sum(int(r["bytes"]) for r in rows)
    video_bytes = os.path.getsize(out)
    return {"frames": len(rows), "gaps": len(entries) - len(rows), "jpeg_bytes": jpeg_bytes,
            "video_bytes": video_bytes, "ratio": round(jpeg_bytes / video_bytes, 1)}


def _days(root, cams=None):
    """(camera, day) for every JPEG day folder, optionally only for some cameras."""
    base = os.path.join(root, "cameras", "jpeg")
    if not os.path.isdir(base):
        return
    for cam in sorted(os.listdir(base)):
        if cams is not None and cam not in cams:
            continue
        for name in sorted(os.listdir(os.path.join(base, cam))):
            try:
                yield cam, date.fromisoformat(name)
            except ValueError:
                continue


def _legacy_days(root, cams=None):
    """(camera, day) for every MKV still waiting to be remuxed into MP4."""
    base = os.path.join(root, "cameras", "video")
    if not os.path.isdir(base):
        return
    for cam in sorted(os.listdir(base)):
        if (cams is not None and cam not in cams) or not os.path.isdir(os.path.join(base, cam)):
            continue
        for year in sorted(os.listdir(os.path.join(base, cam))):
            for name in sorted(os.listdir(os.path.join(base, cam, year))):
                if name.endswith(".mkv") and name.startswith(f"{cam}-"):
                    try:
                        yield cam, date.fromisoformat(name[len(cam) + 1:-4])
                    except ValueError:
                        continue


def pending(root, today, cams=None):
    """(camera, day) pairs before today with JPEGs or an old MKV but no MP4 yet
    (and no recorded failure)."""
    days = sorted(set(_days(root, cams)) | set(_legacy_days(root, cams)))
    return [(cam, day) for cam, day in days
            if day < today and not os.path.exists(video_path(root, cam, day))
            and not os.path.exists(failed_path(root, cam, day))]


def _encode_one(root, cam, day, force):
    """Encode one camera-day; a failure is recorded beside the video's path."""
    try:
        stats = encode(root, cam, day, force)
    except Exception as err:
        os.makedirs(os.path.dirname(failed_path(root, cam, day)), exist_ok=True)
        with open(failed_path(root, cam, day), "w") as f:
            f.write(f"{datetime.now(timezone.utc):{TS_FORMAT}} {err}\n")
        return "failed", f"FAILED: {err}"
    if not stats:
        return "empty", None
    if force and os.path.exists(failed_path(root, cam, day)):
        os.remove(failed_path(root, cam, day))
    return "done", ", ".join(f"{k} {v}" for k, v in stats.items())


def memory_mb(width, height):
    """One encode's peak memory in MB, estimated from its frame size (fitted to the measurements above)."""
    return round(600 + 760 * width * height / 1e6)


def estimate_mb(root, cam, day):
    """The memory one camera-day's encode should need, from its first frame's size. A remux,
    or a day whose frames can't be read, counts as the smallest encode."""
    src = jpeg_dir(root, cam, day)
    try:
        first = read_index(os.path.join(src, INDEX))[0]["file"]
        return memory_mb(*jpeg_size(os.path.join(src, first)))
    except (OSError, IndexError, KeyError, ValueError):
        return memory_mb(0, 0)


class Budget:
    """Memory and slots shared by the encodes running side by side. take() waits until an
    encode's estimate fits; one bigger than the whole budget runs alone."""

    def __init__(self, memory_mb, slots):
        self.total = self.free = memory_mb
        self.slots = slots
        self.cond = threading.Condition()

    def take(self, mb):
        with self.cond:
            self.cond.wait_for(lambda: self.slots > 0 and (mb <= self.free or self.free == self.total))
            self.free -= mb
            self.slots -= 1

    def give(self, mb):
        with self.cond:
            self.free += mb
            self.slots += 1
            self.cond.notify_all()


@contextlib.contextmanager
def one_at_a_time(root, log=print):
    """Hold TVT_ARCHIVE/cameras/rollup.lock while rolling up. The key-camera and regional
    services (and a roll-up by hand) share the server's memory, so a second roll-up waits for
    the first. The lock goes with the process, so a crash can't leave it stuck."""
    path = os.path.join(root, "cameras", LOCK)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("another roll-up is running; waiting for it to finish")
            fcntl.flock(f, fcntl.LOCK_EX)
        yield


def rollup(root, items, force=False, log=print, workers=WORKERS, memory=MEMORY_MB):
    """Encode each (camera, day): up to `workers` at a time, while their estimated memory fits
    `memory` MB, biggest first so the long HD encodes don't finish last. On the server, four
    encodes side by side run about 3x faster than one using every core, with byte-identical
    output (docs/11). One roll-up runs at a time. A failure is recorded beside the video's
    path and not retried automatically; `python3 -m ingest rollup --day ... --force` retries."""
    sized = sorted(((estimate_mb(root, cam, day), cam, day) for cam, day in items), key=lambda t: -t[0])
    budget = Budget(memory, workers)

    def finished(future, mb, cam, day):
        budget.give(mb)
        outcome, message = future.result()
        if message:
            log(f"camera video {cam} {day}: {message}")

    futures = []
    with one_at_a_time(root, log), ThreadPoolExecutor(max_workers=workers) as pool:
        for mb, cam, day in sized:
            budget.take(mb)
            future = pool.submit(_encode_one, root, cam, day, force)
            future.add_done_callback(lambda f, mb=mb, cam=cam, day=day: finished(f, mb, cam, day))
            futures.append(future)
    outcomes = Counter(f.result()[0] for f in futures)
    return outcomes["done"], outcomes["failed"]


def prune(root, today, keep_days, cams=None):
    """Delete JPEG day folders older than keep_days whose video is done."""
    removed = []
    for cam, day in list(_days(root, cams)):
        if day <= today - timedelta(days=keep_days) and os.path.exists(video_path(root, cam, day)):
            shutil.rmtree(jpeg_dir(root, cam, day))
            removed.append((cam, day))
    return removed


def _day_summary(csv_path):
    """Frames, first and last frame times and the usual spacing (in video seconds) of one day's video."""
    rows = [r for r in read_index(csv_path) if r["kind"] == "frame"]
    if not rows:
        return {"frames": 0}
    at = [float(r["video_s"]) for r in rows]
    gaps = sorted(b - a for a, b in zip(at, at[1:]))
    return {"frames": len(rows), "first": rows[0]["local_time"], "last": rows[-1]["local_time"],
            "first_s": at[0], "spacing_s": round(gaps[(len(gaps) - 1) // 2], 3) if gaps else None}


def write_index(root, cams, name, title):
    """Write cameras/video/index-<name>.json for the video library: this list's cameras
    and, for each, every finished day (video and CSV paths relative to cameras/video,
    sizes, frame counts, first and last frame). Days already summarized are reused.
    cams: [(image_id, camera name)]. Returns the number of days listed."""
    base = os.path.join(root, "cameras", "video")
    path = os.path.join(base, f"index-{name}.json")
    known = {}
    try:
        with open(path) as f:
            for cam in json.load(f).get("cameras", []):
                for d in cam.get("days", []):
                    known[d["video"]] = d
    except (OSError, ValueError):
        pass
    cameras, total = [], 0
    for cam, label in cams:
        days = []
        cam_dir = os.path.join(base, str(cam))
        for year in sorted(os.listdir(cam_dir)) if os.path.isdir(cam_dir) else []:
            for fname in sorted(os.listdir(os.path.join(cam_dir, year))):
                if not fname.endswith(".mp4"):
                    continue
                rel = f"{cam}/{year}/{fname}"
                size = os.path.getsize(os.path.join(base, rel))
                old = known.get(rel)
                if old and old.get("bytes") == size:
                    days.append(old)
                    continue
                csv_rel = rel[:-4] + ".csv"
                try:
                    summary = _day_summary(os.path.join(base, csv_rel))
                except (OSError, KeyError, ValueError):
                    summary = {}
                days.append({"day": fname[len(str(cam)) + 1:-4], "video": rel, "csv": csv_rel, "bytes": size, **summary})
        total += len(days)
        cameras.append({"id": str(cam), "name": label, "days": days})
    os.makedirs(base, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w") as f:
        json.dump({"list": name, "title": title, "timezone": "America/Boise", "speedup": SPEEDUP,
                   "updated": datetime.now(timezone.utc).strftime(TS_FORMAT), "cameras": cameras}, f,
                  separators=(",", ":"))
    os.replace(tmp, path)
    return total


def main(argv=None):
    """`python3 -m ingest rollup` (registered in ../plugin.json)."""
    ap = argparse.ArgumentParser(prog="python3 -m ingest rollup",
                                 description="Roll camera JPEGs into daily videos (the frame stream does this nightly).")
    ap.add_argument("--day", type=date.fromisoformat, help="local day, YYYY-MM-DD (default: every finished day not yet done)")
    ap.add_argument("--camera", nargs="+", help="511 image IDs (default: all with frames that day)")
    ap.add_argument("--force", action="store_true", help="redo existing or failed videos")
    args = ap.parse_args(argv)
    root = os.environ.get("TVT_ARCHIVE") or sys.exit("set TVT_ARCHIVE")
    today = datetime.now(TZ).date()
    if args.day:
        cams = args.camera or sorted(os.listdir(os.path.join(root, "cameras", "jpeg")))
        items = [(cam, args.day) for cam in cams]
    else:
        items = [(c, d) for c, d in pending(root, today) if not args.camera or c in args.camera]
    done, failed = rollup(root, items, force=args.force)
    print(f"rollup: {done} videos, {failed} failed", flush=True)
