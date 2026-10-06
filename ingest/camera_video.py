"""Daily camera videos: one camera's JPEGs for one local day, rolled up into
one AV1 video (docs/11 §11.5; format approved by the owner Oct 5).

- **Codec:** SVT-AV1, preset 6, crf30, in MKV.
- **Day:** local midnight to midnight (America/Boise), so a file is one
  calendar day as people read it. Daylight-saving days run 23 or 25 hours.
- **A 60x time-lapse with true spacing:** one minute of the day is one second
  of video, so the video's mm:ss reads as the clock's hh:mm (7:30 into the
  video is 7:30 AM). Gaps of more than 10 minutes show as plain gray.
- **A sidecar CSV** lists every frame: where it sits in the video, when it
  was fetched, and the original JPEG's size and SHA-256.

The frame stream (sources/idaho511_frames.py) runs this after midnight. By hand:
    python3 -m ingest rollup [--day YYYY-MM-DD] [--camera ID ...] [--force]

Layout under TVT_ARCHIVE:
    cameras/jpeg/<image_id>/<YYYY-MM-DD>/<UTC time>.jpg and index.csv
    cameras/video/<image_id>/<YYYY>/<image_id>-<YYYY-MM-DD>.mkv and .csv
"""

import csv
import os
import shutil
import struct
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Boise")
SPEEDUP = 60          # one minute of the day per second of video
GAP_S = 600           # a gap longer than this shows as gray
LAST_FRAME_S = 60     # how long a frame stays up before a gap turns gray
CODEC = ["-c:v", "libsvtav1", "-preset", "6", "-crf", "30", "-g", "600"]
WORKERS = 4            # encodes side by side
INDEX = "index.csv"
INDEX_FIELDS = ["fetched_at", "file", "bytes", "sha256"]
VIDEO_FIELDS = ["video_s", "kind", "fetched_at", "local_time", "file", "bytes", "sha256"]
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def jpeg_dir(root, cam, day):
    return os.path.join(root, "cameras", "jpeg", str(cam), day.isoformat())


def video_path(root, cam, day):
    return os.path.join(root, "cameras", "video", str(cam), f"{day:%Y}", f"{cam}-{day.isoformat()}.mkv")


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
    stays up until the next one; if that's more than GAP_S away, it stays up for
    LAST_FRAME_S and a gray gap fills the rest. Likewise before the first frame
    and after the last."""
    start, end = day_bounds(day)
    rows = sorted(rows, key=lambda r: r["fetched_at"])
    times = [parse_ts(r["fetched_at"]) for r in rows]
    at = lambda t: (t - start).total_seconds() / SPEEDUP
    entries = []
    if times and (times[0] - start).total_seconds() > GAP_S:
        entries.append((0.0, "gap", None))
    for i, (t, row) in enumerate(zip(times, rows)):
        entries.append((at(t), "frame", row))
        following = times[i + 1] if i + 1 < len(times) else end
        if (following - t).total_seconds() > GAP_S:
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


def encode(root, cam, day, force=False):
    """Roll one camera's day into a video. Returns stats, or None if there were no frames."""
    src = jpeg_dir(root, cam, day)
    out = video_path(root, cam, day)
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
              "-vf", f"scale={width}:{height},format=yuv420p", "-fps_mode", "vfr", *CODEC,
              "-metadata", f"title=511 Idaho camera {cam}, {day.isoformat()} (America/Boise)",
              "-metadata", "comment=One second of video is one minute of the day: mm:ss reads as hh:mm. "
                           "Gray means no frames. Frame times are in the .csv beside this file.",
              "-f", "matroska", part])
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
    jpeg_bytes = sum(int(r["bytes"]) for r in rows)
    video_bytes = os.path.getsize(out)
    return {"frames": len(rows), "gaps": len(entries) - len(rows), "jpeg_bytes": jpeg_bytes,
            "video_bytes": video_bytes, "ratio": round(jpeg_bytes / video_bytes, 1)}


def _days(root):
    """(camera, day) for every JPEG day folder."""
    base = os.path.join(root, "cameras", "jpeg")
    if not os.path.isdir(base):
        return
    for cam in sorted(os.listdir(base)):
        for name in sorted(os.listdir(os.path.join(base, cam))):
            try:
                yield cam, date.fromisoformat(name)
            except ValueError:
                continue


def pending(root, today):
    """(camera, day) pairs before today with JPEGs but no video yet (and no recorded failure)."""
    return [(cam, day) for cam, day in _days(root)
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


def rollup(root, items, force=False, log=print, workers=WORKERS):
    """Encode each (camera, day), WORKERS at a time: on the server, four encodes
    side by side run about 3x faster than one using every core, with
    byte-identical output (docs/11). A failure is recorded beside the video's
    path and not retried automatically; `python3 -m ingest rollup --day ...
    --force` retries."""
    done = failed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_encode_one, root, cam, day, force): (cam, day) for cam, day in items}
        for future in as_completed(futures):
            cam, day = futures[future]
            outcome, message = future.result()
            done += outcome == "done"
            failed += outcome == "failed"
            if message:
                log(f"camera video {cam} {day}: {message}")
    return done, failed


def prune(root, today, keep_days):
    """Delete JPEG day folders older than keep_days whose video is done."""
    removed = []
    for cam, day in list(_days(root)):
        if day <= today - timedelta(days=keep_days) and os.path.exists(video_path(root, cam, day)):
            shutil.rmtree(jpeg_dir(root, cam, day))
            removed.append((cam, day))
    return removed
