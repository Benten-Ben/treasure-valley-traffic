"""Key-camera frames from 511 Idaho (docs/11 §11.7, step 2: about 35 cameras).

511 republishes each ACHD camera's snapshot about every 59 s at
/map/Cctv/<image_id>, the allowed camera route (robots.txt permits it; no
key needed). Each key camera (ingest/key_cameras.csv) is fetched every 50 s,
a little faster than it changes, so no snapshot is missed. Repeats are
byte-identical and dropped. Requests are spread evenly over the cycle: for
34 cameras, about one every 1.5 s.

The camera list comes from TVT_CAMERAS (default: the key cameras). ITD's
road-weather (RWIS) views statewide, plus Oregon DOT views near Ontario, run
as a second service with their own list and a slower poll, since they change
about every 15 minutes. That list is built from 511's camera list, so it's
kept with the private files. Each service rolls up and prunes only its own
cameras.

Frames are saved as JPEGs by local day, with an index.csv per folder, and
each finished day is rolled up after midnight into one AV1 video per camera
(ingest/camera_video.py). JPEGs are deleted after KEEP_JPEG_DAYS, once
their video exists.

Each cycle also writes a status file, cameras/status/<list name>.json: the
cadence, the image IDs, a heartbeat, and whether capture is paused for low
disk or rolling up. The app reads it (read-only) to know which views are
recorded and whether capture is alive (docs/14 §14.6, "Live images").

The images are third-party copies: they stay on the server and are never
published or committed.
"""

import csv
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from .. import camera_video, http

URL = "https://511.idaho.gov/map/Cctv/{}"
CAMERAS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "key_cameras.csv")
POLL_S = 50
KEEP_JPEG_DAYS = 2         # today and yesterday (owner, Oct 5); the videos are kept
MIN_FREE_BYTES = 10 * 2**30          # below this, prune harder, then pause
ROLLUP_AFTER = timedelta(minutes=5)  # after local midnight, so the day's last fetches are in
REPORT_EVERY_S = 3600
ROBOTS_REFRESH_S = 24 * 3600

SOURCE = {
    "name": "idaho511_frames",
    "title": "511 Idaho camera frames (key cameras), rolled up into daily AV1 videos",
    "url": "https://511.idaho.gov/map/Cctv/<image_id>",
    "access": "open",
    "schedule": None,
    "license": "none stated; kept private on the server, never published",
    "credit": "Idaho Transportation Department (511 Idaho) and Ada County Highway District",
    "notes": "Fetched every 50 s per camera; repeats dropped. JPEGs kept 2 days, videos kept.",
}


def load_cameras(path=CAMERAS_FILE):
    with open(path, newline="") as f:
        return [(int(r["image_id"]), r["name"]) for r in csv.DictReader(f)]


def is_jpeg(body):
    """A complete JPEG: starts with SOI and has EOI near the end."""
    return body[:2] == b"\xff\xd8" and b"\xff\xd9" in body[-64:]


def frame_name(ts):
    return ts.strftime("%Y%m%dT%H%M%SZ.jpg")


def save(root, cam, body, ts, digest):
    """Write the frame, then add it to its day's index. Returns the frame's path."""
    folder = camera_video.jpeg_dir(root, cam, camera_video.local_day(ts))
    os.makedirs(folder, exist_ok=True)
    name = frame_name(ts)
    path = os.path.join(folder, name)
    with open(path + ".part", "wb") as f:
        f.write(body)
    os.replace(path + ".part", path)
    index = os.path.join(folder, camera_video.INDEX)
    new = not os.path.exists(index)
    with open(index, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(camera_video.INDEX_FIELDS)
        w.writerow([ts.strftime(camera_video.TS_FORMAT), name, len(body), digest])
    return path


def last_digests(root, cams, day):
    """Each camera's last saved frame on that day, so a restart doesn't save a repeat."""
    out = {}
    for cam, _ in cams:
        try:
            rows = camera_video.read_index(os.path.join(camera_video.jpeg_dir(root, cam, day), camera_video.INDEX))
        except FileNotFoundError:
            continue
        if rows:
            out[cam] = rows[-1]["sha256"]
    return out


def rollup_due(now_local):
    midnight = datetime.combine(now_local.date(), datetime.min.time(), camera_video.TZ)
    return now_local - midnight >= ROLLUP_AFTER


STATUS_VERSION = 1


def status_path(root, tag):
    """cameras/status/<tag>.json; the tag is the camera list's name, kept to safe characters."""
    return os.path.join(root, "cameras", "status", re.sub(r"[^A-Za-z0-9_.-]", "_", tag) + ".json")


def write_status(root, tag, cadence_s, image_ids, paused_low_disk=False, rolling_up=False, now=None):
    """Write this capture service's status file atomically. Returns what was written.

    The app reads these (app/src/lib/server/archive.ts): which images are recorded,
    how often, and whether capture is alive (a heartbeat within 3 cadences)."""
    now = time.time() if now is None else now
    status = {
        "version": STATUS_VERSION,
        "tag": tag,
        "cadence_s": cadence_s,
        "image_ids": [int(i) for i in image_ids],
        "heartbeat": round(now, 3),
        "heartbeat_at": datetime.fromtimestamp(now, timezone.utc).strftime(camera_video.TS_FORMAT),
        "paused_low_disk": bool(paused_low_disk),
        "rolling_up": bool(rolling_up),
    }
    path = status_path(root, tag)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w") as f:
        json.dump(status, f, separators=(",", ":"))
    os.replace(path + ".part", path)
    return status


# Headings for each capture list in the video library (deploy/library/).
LIBRARY_TITLES = {"key_cameras": "Key cameras", "regional-cameras": "Road weather and Oregon"}


def update_library(root, cams, list_name, log):
    try:
        camera_video.write_index(root, cams, list_name, LIBRARY_TITLES.get(list_name, list_name))
    except Exception as err:
        log(f"video library index not written: {err}")


def _rollup_and_prune(root, items, today, own, log, library=None):
    try:
        done, failed = camera_video.rollup(root, items, log=log)
        removed = camera_video.prune(root, today, KEEP_JPEG_DAYS, own)
        log(f"roll-up finished: {done} videos, {failed} failed; {len(removed)} old JPEG days deleted")
    except Exception as err:
        log(f"roll-up stopped: {err}")
    if library:
        update_library(root, *library, log)


def stream(every=POLL_S):
    """Fetch the key cameras forever. Network errors are counted and logged
    hourly; the loop carries on."""
    root = os.environ.get("TVT_ARCHIVE")
    if not root:
        sys.exit("set TVT_ARCHIVE: camera frames and videos are kept there")
    path = os.environ.get("TVT_CAMERAS") or CAMERAS_FILE
    cams = load_cameras(path)
    own = {str(cam) for cam, _ in cams}
    list_mtime = os.stat(path).st_mtime
    tag = f"idaho511_frames[{os.path.splitext(os.path.basename(path))[0]}]"

    def log(message):
        print(f"{tag}: {message}", flush=True)

    log(f"{len(cams)} cameras every {every} s, saving to {root}/cameras")
    list_name = os.path.splitext(os.path.basename(path))[0]
    update_library(root, cams, list_name, log)
    last = last_digests(root, cams, camera_video.local_day(datetime.now(timezone.utc)))
    counts, new_per_cam, samples = Counter(), Counter(), []
    report_at = time.time() + REPORT_EVERY_S
    robots_at = time.time() + ROBOTS_REFRESH_S
    worker, paused = None, False
    while True:
        started = time.monotonic()
        today = datetime.now(camera_video.TZ).date()

        # The road-weather list is rebuilt from 511's camera list (idaho511_api); pick up changes.
        try:
            mtime = os.stat(path).st_mtime
            if mtime != list_mtime:
                fresh = load_cameras(path)
                added = sorted({c for c, _ in fresh} - {c for c, _ in cams})
                dropped = sorted({c for c, _ in cams} - {c for c, _ in fresh})
                if fresh:
                    cams = fresh
                    own |= {str(cam) for cam, _ in cams}     # dropped cameras' days still get rolled up
                    if added or dropped:
                        log(f"camera list changed: {len(cams)} cameras; added {added}, dropped {dropped}")
                list_mtime = mtime
        except (OSError, ValueError, KeyError) as err:
            log(f"camera list unreadable, keeping the old one: {err}")

        if shutil.disk_usage(root).free < MIN_FREE_BYTES:
            camera_video.prune(root, today, 1, own)
        if shutil.disk_usage(root).free < MIN_FREE_BYTES:
            if not paused:
                log(f"PAUSED: under {MIN_FREE_BYTES / 2**30:.0f} GB free in {root}")
            paused = True
        elif paused:
            log("resumed: disk space is back")
            paused = False

        try:
            write_status(root, list_name, every, [cam for cam, _ in cams], paused,
                         rolling_up=worker is not None and worker.is_alive())
        except OSError as err:
            counts["status write errors"] += 1
            if len(samples) < 3:
                samples.append(f"status file: {err}")

        for i, (cam, _) in enumerate(cams if not paused else []):
            wait = started + i * every / len(cams) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                _, body, _ = http.get(URL.format(cam), timeout=20)
            except http.RobotsUnavailable:
                counts["robots.txt unreadable"] += 1
                continue
            except http.RobotsDisallowed as err:
                counts["disallowed by robots.txt"] += 1
                if len(samples) < 3:
                    samples.append(str(err))
                continue
            except Exception as err:
                counts["fetch errors"] += 1
                if len(samples) < 3:
                    samples.append(f"{cam}: {err}")
                continue
            if not is_jpeg(body):
                counts["not a complete JPEG"] += 1
                continue
            digest = hashlib.sha256(body).hexdigest()
            if last.get(cam) == digest:
                counts["repeats"] += 1
                continue
            try:
                save(root, cam, body, datetime.now(timezone.utc), digest)
            except OSError as err:
                counts["write errors"] += 1
                if len(samples) < 3:
                    samples.append(f"{cam}: {err}")
                continue
            last[cam] = digest
            counts["frames"] += 1
            counts["MB"] += len(body) / 1e6
            new_per_cam[cam] += 1

        if (worker is None or not worker.is_alive()) and rollup_due(datetime.now(camera_video.TZ)):
            due = camera_video.pending(root, today, own)
            if due:
                log(f"rolling up {len(due)} camera days")
                worker = threading.Thread(target=_rollup_and_prune, daemon=True,
                                          args=(root, due, today, own, log, (cams, list_name)))
                worker.start()

        if time.time() >= robots_at:
            http.forget_robots()
            robots_at = time.time() + ROBOTS_REFRESH_S
        if time.time() >= report_at:
            quiet = [cam for cam, _ in cams if not new_per_cam[cam]]
            free = shutil.disk_usage(root).free / 2**30
            log("last hour: "
                + ", ".join(f"{k} {v:.0f}" for k, v in counts.items())
                + f"; {free:.0f} GB free"
                + (f"; no new frames from {quiet}" if quiet else "")
                + (f"; e.g. {samples}" if samples else ""))
            counts, new_per_cam, samples = Counter(), Counter(), []
            report_at = time.time() + REPORT_EVERY_S

        rest = started + every - time.monotonic()
        if rest > 0:
            time.sleep(rest)
