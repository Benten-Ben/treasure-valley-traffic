# 11. Cameras as a validation layer

Traffic cameras won't drive our core analysis. They're a **validation
layer**: a way to confirm or challenge what volumes, transit GPS, crashes
and timing data suggest (for example, "this approach spills back at
5:15 pm").

Status: design agreed in principle with the owner. The code isn't built
yet; the prototype only reads the camera list.

**Owner direction (Oct 5):**

- Capture each camera at its real refresh rate (about once a minute).
- Run queue and traffic measurement automatically on every frame.
- **Store everything:** keep the frames, as compressed video, and every
  measurement until we have enough to draw conclusions.
- Heavy image pre-processing is welcome where it improves those
  measurements.

The pipeline is in [§11.7](#117-processing-pipeline-collect-everything-measure-every-frame).
Camera measurements stay a validation layer until we've checked their
accuracy against ground truth (manual counts); then they can graduate to a
core source.

---

## 11.1 The source

**ACHD operates 228 traffic cameras** in Ada County (none in Canyon
County). They're mostly at major intersections and I-84/I-184 interchanges.
Each publishes a **still image, not video**, refreshed about every 59
seconds and about a minute behind real time.

Coverage by corridor keyword:

| Corridor | Cameras |
|---|---|
| I-84 | 24 |
| Chinden | 21 |
| State | 21 |
| Eagle | 17 |
| Franklin | 14 |
| Overland | 14 |
| Fairview | 13 |
| Ustick | 11 |
| Meridian | 9 |
| I-184 | 6 |
| Hwy 69 | 6 |

244 of 453 signalized intersections have a camera within 150 m. The dated inventory
is kept with the project's private files (parts of it came from 511's
camera-list page); the cameras themselves are in the database.

**The camera list** is ACHD GIS "Traffic Cameras", layer 26 on
`gis.achdidaho.org`. Automated access is allowed. Fields:

| Field | Notes |
|---|---|
| `camID` | ACHD camera number, also used in the image link |
| `label` | e.g. "Broadway & Beacon"; a few have stray spaces |
| `Latitude`, `Longitude` | Missing on 2 duplicate records |
| `hyperlink` | `https://more.achdidaho.org/ATIS/CCTV/CCTV_<id>.jpg` |
| `camtimestamp` | **Layer-wide refresh time, identical on all records.** It can't tell us which cameras are dead. |
| `OBJECTID`, `GlobalID` | Internal |

**What we know about each camera's position and view (checked Oct 5):**

| Attribute | Have it? | Source and quality |
|---|---|---|
| Location | Yes, approximately | ACHD GIS lat/lon with 4–6 decimal places (4 places is about ±11 m). Points usually sit at an intersection corner: median 26 m from the intersection center, only 5 of 228 within 5 m. They mark the camera pole, roughly; the owner confirms most cameras sit on top of a corner pole. The point's direction from the intersection center tells us which corner, a good starting guess for calibration. |
| Name, ACHD camera number | Yes | ACHD GIS `label`, `camID` |
| Facing direction | **No**, then coarse | Not in ACHD's data. The 511 API has `Direction`, but only as a compass or travel direction, or "None"/"All Directions". We can't see ACHD cameras' values until the key arrives. |
| Pan-tilt-zoom (PTZ) | Probably ⚠️ | Intersection cameras like these are usually PTZ, so the view belongs to a *preset* and changes when operators move the camera (pipeline stage 4) |
| Exact heading, tilt, zoom, mounting height, presets, camera model | **No public source** | Measured by calibration (below), or ask ACHD |
| Snapshot time | Yes, to the second | 511 timestamp bar |
| Image size | Yes | Varies by camera (768×466, 704×426, …), a hint of different camera models |

**Calibration gives the exact geometry.** For each view, mark 4–6 points
visible in both the camera image and aerial imagery: stop bars, lane-line
ends, crosswalk corners, pole bases. Solving from those points gives:

- the camera's true position;
- its compass heading and tilt;
- its field of view and mounting height;
- the image-to-ground mapping.

That drives the map's view cones and turns queues into meters. It starts
by hand (a few minutes per view) and can be partly automated later. The
workbench UI is in [chapter 13](13-visual-design.md#133-a-walk-through-the-screen).

**Feasibility:**

- MapLibre 6 drapes raster imagery over terrain.
- It can render the 3D map from an exact camera position, height and
  rotation (`calculateCameraOptionsFromCameraLngLatAltRotation`).
- It can set the vertical field of view (`setVerticalFieldOfView`).

The pose solve itself is a standard camera-resection problem: 3D ground
points (map position plus DEM height) matched to image pixels, with the
corner-pole location as a starting guess.

**Imagery limits:**

- NAIP's 0.6 m pixels show stop bars and crosswalks but not crisp lane-line
  ends. ACHD's 3-inch imagery is far better but covers Ada only, and its
  terms are unconfirmed.
- Imagery is a snapshot in time, so striping may have changed since.

**Context we can compute per frame:**

- Sun position (azimuth and elevation, from a standard solar-position
  algorithm) relative to the calibrated heading and field of view:
  - **glare risk** when the sun is in or near the view, for example a
    west-facing camera at sunset from fall to winter;
  - **long shadows** that can confuse detection.
  - A **glare calendar** per camera: the dates and times when its
    measurements need care.
- Day, twilight or night.
- Weather at the Boise airport.
- The nearby intersection's volumes and crash history.
- **A research angle:** the same sun geometry applies to drivers. Crashes
  can be checked against whether the sun was low in front of the approach.

**Provenance:** two sets of facts in this chapter, and in the inventory
CSV, came from **one-off research checks** of endpoints whose robots.txt
asks crawlers to stay away. The owner considers one-off checks fine (Oct
5). Automated collection from these endpoints stays off-limits, so the
pipeline will never rely on them:

- **ACHD image-server headers (Oct 4):** the 59 s refresh, the 220
  live / 8 stale counts, and the CSV's `status_2026_10_05` and
  `last_image_age` columns.
- **511's website list, `/List/GetData/Cameras` (Oct 5):**
  - 511's image IDs, such as 656 and 752;
  - the "about 210 of 228 on 511" count and the list of missing IDs;
  - the CSV's `on_511_idaho` column;
  - the CSV's 20 non-ACHD rows (2 ITD cameras and 18 road-weather views),
    which came entirely from that list.

Since Oct 6, 2026 the camera list comes from the official API (hourly,
`idaho511_api`), which also rebuilds the road-weather capture list. Camera health comes from our own monitor reading the 511
timestamp bar.

**Quality notes:**

- 232 records cover 228 cameras (4 listed twice).
- On Oct 4–5, 2026, 220 were live and 8 stale. Two have been dead for
  years: I-84 & McDermott and I-84 & Northside.

## 11.2 Where the images come from (and why that's allowed)

| Path | Allowed for automated use? | Notes |
|---|---|---|
| ACHD's server, `more.achdidaho.org/ATIS/CCTV/...` | **No** | Its robots.txt disallows all automated access |
| **511 Idaho**, `511.idaho.gov/map/Cctv/<imageId>` | **Yes** ✅ (owner decision, Oct 5) | See below |

Why the 511 route counts as an authorized republisher serving its own
copies:

- **511 republishes its own copies**, served from its own AWS/CloudFront
  infrastructure. They aren't links to ACHD's server.
- Each image carries the **ITD logo** and a **511-added timestamp bar**
  (for example 768×466 vs ACHD's 768×432; sizes vary by camera).
- 511's About page lists ACHD as a data provider.
- 511's robots.txt allows `/map/Cctv/`, and its published pages contain no
  terms against reuse.

Rules for using the 511 route:

- Get the camera list from the **official 511 API**. The website's list
  endpoint is disallowed.
- 511 covers **about 210 of ACHD's 228 cameras**. About 18, mostly the
  newest (IDs 717–729) and a few I-184 cameras, aren't on 511. These
  numbers come from a one-off check of the website list (see Provenance in
  §11.1); the official API will confirm them.
- 511 stamps a fresh `Last-Modified` time on every response. So **health
  checks must use image content**: the timestamp bar, frozen-frame
  detection. See "What tells us how fresh an image is" below.
- We still send ACHD a courtesy note, plus the counts and turn-movement
  CSV request (the draft is kept privately until it's sent).

### What tells us how fresh an image is (checked Oct 5, 2026)

| Source | Per-camera freshness? | Notes |
|---|---|---|
| ACHD GIS layer, `camtimestamp` | **No** | One value shared by all 232 records ("Oct 4 2026 11:59PM" when checked at 12:06 AM): when the layer last refreshed |
| ACHD image server, `Last-Modified` header | Yes | Its robots.txt disallows automated access, so it's for one-off research checks only, never the pipeline. Oct 4 check: 59 s refresh; 220 live, 8 stale. |
| 511 API, `Views[].Status` | Coarse | Enabled or Disabled only |
| 511 HTTP headers | **No** | `Last-Modified` is just the response time; CloudFront caches for 15 s |
| 511 JPEG metadata | **No** | No EXIF or comment fields |
| **511 timestamp bar** | **Yes, to the second** | **ACHD's own image time:** it equals the `Last-Modified` time on ACHD's server exactly (checked below). It stays the same until the next image. |
| **Image content** | **Yes** | Between updates the picture is pixel-identical, so frozen or stale cameras are easy to detect |

**511 refresh measurement.** Cameras 656 and 752 were fetched every 15 s
for 7 minutes (Oct 5, 12:03–12:10 AM MDT):

- **Snapshots every 59 s per camera**, matching ACHD's own refresh.
  - Camera 656's bar read 12:02:22, 12:03:21, 12:04:20 and so on.
  - Camera 752's snapshots fall about 10 s later in each minute.
- **511 publishes in batches:** both cameras' pictures changed at the same
  fetch every time.
- **Age when first visible:** 25–85 s, varying from image to image.
- **Snapshots can be skipped:** 752's 12:03:30 image never appeared,
  leaving a 2-minute gap.
- **Between updates the scene is bit-for-bit identical** (zero pixel
  difference), even though 511 redraws the bar.

**ACHD vs 511, side by side** (one-off research check, Oct 5, 12:28–12:32
AM MDT). ACHD cameras 526 and 620, and their 511 copies 656 and 752, were
fetched about every 13 s. Results:

- **The 511 bar is ACHD's image time.** 511's four bars for camera 656 read
  12:26:57, 12:27:56, 12:29:54 and 12:30:53. These match ACHD's
  `Last-Modified` times to the second.
- **511 adds almost no delay.** Each new ACHD image appeared on 511 within
  0–15 s of appearing on ACHD's server (at our polling resolution).
- **The delay and the gaps happen upstream, at ACHD.** ACHD's own server
  shows each image 8–77 s after its timestamp. Camera 526's 12:28:55 image
  never appeared on either server.
- **Image sizes:** ACHD's originals are 768×432 (526) and 704×395 (620).
  511 adds a 34 px or 31 px timestamp bar below, plus the ITD logo.

So 511's copy is as fresh as ACHD's own. Going direct would gain nothing
on freshness.

**What this means for capture:**

- Fetch each camera **once per 59 s cycle, just after the batch lands**.
  Faster polling gains nothing.
- Store the bar time as the image's `taken_at`. It's ACHD's image time.
- Treat "bar didn't advance" as stale and "bar advanced but scene
  identical" as frozen.
- Read the bar automatically. Because it's clean rendered text, a small
  template matcher should do; no full OCR engine needed.

## 11.3 The 511 Idaho API

- **Signup:** create an account at https://511.idaho.gov/my511/register,
  then request a key at https://511.idaho.gov/developers/doc. Read the
  developer agreement shown at signup.
- **Limit:** "Throttling is enabled. Ten calls every 60 seconds" per key.
  Each call returns a whole resource (all cameras statewide, all events).
- **Budget:** about 2 of the 10 calls a minute.
  - events: every 1 min;
  - message signs: every 2 min;
  - weather and road conditions: every 5–10 min;
  - camera list: hourly.
- **Images:** `/map/Cctv/<id>` links carry no key, so they most likely don't
  count against the API limit. Confirm once we have a key.
- **Camera fields** (`/api/v2/get/cameras`, per
  [511's endpoint docs](https://511.idaho.gov/help/endpoint/cameras)):
  - `Id`, `Source`, `Location`, `Roadway`, `Latitude`, `Longitude`,
    `SortOrder`.
  - **`SourceId`:** the provider's own camera number. This should map 511
    cameras directly to ACHD camera IDs, replacing our location matching.
  - **`Direction`:** which way the camera faces. That's what the map's view
    cones need.
  - **`Views[]`:** each view has an `Id` (the image ID), `Url`, a
    `Description`, and a `Status` of Enabled or Disabled.
  - There are **no timestamps** and no refresh rate.
- **Don't use multiple keys** to get around the limit.

## 11.4 What we'll build (agreed scope: options C–E as validation)

| Piece | What it does | Buildable before images flow? |
|---|---|---|
| **1. Camera registry** | ACHD list + 511 list merged; history of cameras added, moved or removed; linked to intersections; later, which approaches each camera sees | Yes |
| **2. Capture service** | Fetches each camera at its real refresh rate (about 60 s). Keeps a frame only when the picture changed, using the timestamp bar plus a scene hash. Hourly AV1 roll-ups. Scales up in steps (see §11.7). | Yes (tested against fake images) |
| **3. Health monitor** | Stale or frozen frames (repeated content), blank or gray frames, re-aimed cameras (scene change against a reference). Uptime per camera. | Logic yes; tuning needs real frames |
| **4. Queue measurement** | Vehicle detection (permissive license) inside per-approach zones drawn by hand. Outputs queue presence and rough length over time. | Pipeline yes; calibration needs real frames |
| **5. Privacy rules** | Measurements of vehicles as traffic only: no plate or face recognition, no following a vehicle across cameras. The archive is kept long-term (owner, Oct 5) but stays private on the home server and is never published without permission. | Built into 2 and 4 |

## 11.5 Storage

| Capture plan | Images per day | JPEG at about 45 KB |
|---|---|---|
| All about 210 cameras, every minute, 24 h | about 302,000 | **about 13–14 GB/day**, more with ITD's HD cameras (below) |
| 40 key cameras, every minute, 9 peak hours | about 21,600 | about 1 GB/day |
| All cameras every 15 min, 24 h (health checks) | about 20,000 | about 0.9 GB/day |

**ITD's I-84 cameras are full HD.** The four I-84 interchange cameras among
the key cameras send 1920×1166 frames of about 400 KB, 8 times ACHD's
768×466 frames of about 45 KB, and take about 6 times longer to encode. So
the 34 key cameras download about 4 GB a day, not 2, and the 2 days of JPEGs
kept are about 8 GB. How many of the other 511 cameras are HD is unchecked, so the
all-camera figures above are a floor. ⚠️

**One angle per camera, checked Oct 5.** Every ACHD camera on 511 is a
single image stream: a pan-tilt-zoom camera that an operator can re-aim,
which stage 4 of the pipeline (§11.7) watches for. None of the key
intersections has a second ACHD camera on 511. Three things look like extra
angles but aren't, or aren't reachable:

- **I-84 & Eagle and I-84 & Meridian** also appear as ITD views (511 image
  IDs 1277 and 1163). They're the same cameras (ACHD 546 and 544) with
  ITD's caption, served as 1920×1166 PNGs of about 2.5 MB, with snapshots
  taken at different moments from ACHD's. Same angle, so not captured.
- **Chinden & SH-16** has a second ACHD camera on the southbound ramp (619)
  that 511 doesn't republish. It's one of the 18 ACHD cameras not on 511,
  reachable only from ACHD's image server, whose robots.txt disallows us. The
  draft note to ACHD asks about it.
- **Road-weather cameras** (ITD's RWIS) at the I-84 Wye (4 views) and I-84
  at Kuna/Meridian (3 views) are about 400 m from the nearest key cameras:
  different places, aimed at the pavement.

**Road-weather views, recorded since Oct 5** (owner: "useful data when we
have enough", wherever we have them). ITD's road-weather stations (RWIS)
carry 2–4 cameras each, one per direction: 385 views at 130 stations
statewide in 511's camera list (one-off copy, Oct 5), 30 of them at the 10
stations in our area. A second service (`regional`) captures all of them,
plus 4 Oregon DOT views near Ontario and Weiser, every 10 minutes into daily
videos. Its list is built from 511's camera list, so it's kept with the
private files.
- Their images are 800×486 JPEGs with ITD's own caption: station,
  milepost, elevation, which way the view faces, and the station's capture
  time. Caldwell's two views showed 511's "no live feed" image on Oct 5.
- **Cadence (Oct 5, 8:57 and 9:10 PM):** 511 refreshes its copies about
  every 15 minutes and re-stamps its own time bar each time, so all 28 live
  views changed bytes within 12 minutes. The stations' own pictures also
  update about every 15 minutes (the Wye: 8:49 → 9:04 PM), but some stall:
  Broadway's stayed at 8:19 PM. Unlike ACHD's cameras, a byte-level repeat
  check doesn't catch a stalled picture here; reading ITD's caption time
  will (stage 2 of the pipeline, §11.7).
- A gap counts as gray only beyond 3 times a view's usual spacing.
- **Volume:** about 37,000 new pictures a day (511 refreshes each view about
  every 15 minutes) of about 60 KB: about 2 GB of JPEGs a day, kept 2 days,
  plus the daily videos.
- The station sensors (pavement temperature, surface state, wind) come
  through the 511 API and are the measured road conditions; the images show
  what they look like.

### Video archive instead of JPEGs

Inter-frame video codecs store a full frame occasionally and only the
differences after that. Points that matter for 1-frame-per-minute traffic
images:

- **Frames are 60 s apart.** Cars, lighting and the timestamp bar change
  each frame, so savings are smaller than for normal video. Most of each
  image (road, buildings, sky) is static, though, so savings should still
  be large.
- **Codec:** H.265/HEVC and AV1 are roughly 30–50% smaller than H.264 at
  equal quality. They're slower to encode, which doesn't matter at
  1 frame/min.
- **Quality loss:** sources are already JPEGs, so re-encoding loses a little
  more. **Run detection on the original JPEG first**; the video is the
  archive.
- **Appending one frame at a time is the hard way.** It needs a long-running
  encoder per camera, because restarting forces a new full frame. Standard
  MP4 isn't appendable (the index is written at the end). Fragmented MP4,
  MKV/WebM and MPEG-TS are stream-friendly.
- **Recommended: batch roll-up.**
  1. Keep JPEGs for the current hour (or day) and run detection as frames
     arrive.
  2. Then encode that camera's batch into one video with real per-frame
     timestamps (MKV or fragmented MP4) plus a sidecar index of capture
     times.
  3. Delete the JPEGs.

  This compresses better (the encoder can look ahead), survives crashes,
  and needs no long-running processes.

### Measured results (night test, Oct 4–5, 2026)

**Test:** 26 frames, 1 per minute, from two cameras via 511 (about 11:15–11:42 PM MDT):

- **656, Eagle & Fairview:** 768×466, about 30 KB per JPEG. Clean picture,
  with some traffic.
- **752, Chinden & Cloverdale:** 704×426, about 43 KB per JPEG. An almost
  empty road, but heavy sensor grain from night-time gain. Note that 511
  frame sizes vary by camera.

**Measures:**

- **vs JPEG:** how many times smaller the video is than the original JPEGs.
- **SSIM:** similarity to the original JPEGs (1.0 means identical).

| Config | 656 (clean): vs JPEG | 656: SSIM | 752 (grainy): vs JPEG | 752: SSIM |
|---|---|---|---|---|
| H.264 all-intra (no inter-frame) crf23 | 1.0x | 0.997 | 1.0x | 0.994 |
| H.264 crf23 | 2.3x | 0.998 | 0.9x | 0.994 |
| H.264 crf28 | 3.2x | 0.994 | 1.1x | 0.987 |
| H.265 crf24 | 2.4x | 0.998 | 0.9x | 0.994 |
| **AV1 (SVT-AV1, preset 6) crf30** | **7.0x** | 0.989 | **2.1x** | 0.960 |
| AV1 crf38 | 11.8x | 0.985 | 5.1x | 0.864 |
| AV1 crf46 | 17.8x | 0.981 | 30x | 0.771 (smeared) |

Encoding took 1–2.5 s per 26-frame batch on 4 cores.

**What we learned:**

- **Image noise matters more than the codec.** Consecutive frames from
  camera 656 are very similar (median SSIM 0.95); camera 752's grain makes
  them only 0.62 similar, even though nothing moves. H.264 and H.265 spend
  their bits re-encoding that grain, so they save nothing on 752.
- **AV1 is the clear winner here**, about 3x better than H.264/H.265 on
  both cameras. On the grainy camera it smooths the grain away and keeps the
  lane markings and stop bars sharp; that's why its SSIM looks lower. That's
  fine for an archive people look at, since measurements run on the original
  JPEGs.
- **Denoising first didn't help.** We tried `hqdn3d` before encoding, and
  AV1's built-in film-grain modeling: at most 10% smaller, and worse for
  H.264.
- **Caveats:** this is night only, two cameras, and short batches (26
  frames; hourly or daily batches compress a bit better). We should repeat
  the test with a daytime capture before settling the settings.

### Measured results (midday, Oct 5, 2026)

**Test:** the same two cameras and method, in daylight: 26 changed frames
each, polled every 30 s via 511, 1:58–2:24 PM MDT. All 52 frames were
distinct. Frames: 656 about 44 KB per JPEG, 752 about 36 KB.

| Config | 656: vs JPEG | 656: SSIM | 752: vs JPEG | 752: SSIM |
|---|---|---|---|---|
| H.264 all-intra (no inter-frame) crf23 | 1.0x | 0.995 | 1.1x | 0.995 |
| H.264 crf23 | 1.7x | 0.997 | 1.8x | 0.997 |
| H.264 crf28 | 2.3x | 0.991 | 2.4x | 0.992 |
| H.265 crf24 | 1.8x | 0.997 | 1.9x | 0.997 |
| **AV1 (SVT-AV1, preset 6) crf30** | **3.9x** | 0.984 | **4.9x** | 0.984 |
| AV1 crf38 | 6.5x | 0.975 | 8.9x | 0.978 |
| AV1 crf46 | 10.7x | 0.965 | 13.5x | 0.972 |

Encoding took 1.6–3.3 s per 26-frame batch on 4 cores.

**What we learned:**

- **Daylight sits between the two night cases.** Camera 656 compresses less
  than at night (3.9x vs 7.0x), because there's more traffic moving.
  Camera 752 compresses far better (4.9x vs 2.1x), because daylight has no
  sensor grain.
- **AV1 crf30 stays about 2x ahead of H.264 and H.265**, at an SSIM of
  0.984 on both cameras.

### Measured results (evening rush, Oct 5, 2026)

**Test:** the same two cameras and method in the evening peak: 26 changed
frames each, 5:01–5:27 PM MDT, all distinct. Frames: 656 about 44 KB per
JPEG, 752 about 32 KB.

| Config | 656: vs JPEG | 656: SSIM | 752: vs JPEG | 752: SSIM |
|---|---|---|---|---|
| H.264 all-intra (no inter-frame) crf23 | 1.0x | 0.995 | 1.1x | 0.996 |
| H.264 crf23 | 1.4x | 0.996 | 1.6x | 0.997 |
| H.264 crf28 | 1.9x | 0.990 | 2.1x | 0.992 |
| H.265 crf24 | 1.5x | 0.997 | 1.7x | 0.997 |
| **AV1 (SVT-AV1, preset 6) crf30** | **3.5x** | 0.980 | **4.3x** | 0.982 |
| AV1 crf38 | 5.8x | 0.968 | 7.4x | 0.973 |
| AV1 crf46 | 9.9x | 0.954 | 11.3x | 0.966 |

**What the three tests show together:**

| AV1 crf30, vs JPEG | 656 Eagle & Fairview | 752 Chinden & Cloverdale |
|---|---|---|
| Night (Oct 4–5) | 7.0x | 2.1x (sensor grain) |
| Midday (Oct 5) | 3.9x | 4.9x |
| Evening rush (Oct 5) | 3.5x | 4.3x |

- **The busiest hour costs a little:** 10–12% less compression than
  midday, because more is moving.
- **AV1 crf30 is about 2x ahead of H.264 and H.265 in every test**, at an
  SSIM of 0.98 against the originals.
- **The 2–7x range used for storage holds.** Daytime sits at 3.5–4.9x.

**Storage at these ratios** (AV1 crf30, 2–7x):

| Plan | JPEG per day | Video per day | 90-day archive |
|---|---|---|---|
| 40 key cameras, 9 peak hours | about 1 GB | about 150–500 MB | about 15–45 GB |
| All about 210 cameras, 24 h | about 13–14 GB | about 2–7 GB | about 180–600 GB |

**The archive format (owner, Oct 5):**

- **Codec:** AV1 via SVT-AV1, preset 6, crf30.
- **Container:** MKV, one file per camera per day, rolled up from the
  JPEGs after midnight
  ([`ingest/camera_video.py`](../ingest/camera_video.py)).
- **Originals:** keep the JPEGs 2 days (today and yesterday), then delete
  them once their video exists (owner, Oct 5). Measuring needs 24–48 hours.
- **Getting a frame back:** every frame can be pulled out of the video as an
  image, and the CSV beside the video maps frame numbers to fetch times. The
  pictures aren't byte-identical to the originals, but they're close:
  across the 26 evening-rush frames of camera 656, SSIM 0.979 on average
  (lowest 0.973) and PSNR 41 dB (lowest 40 dB). At 2x zoom every vehicle is
  still distinct; fine texture such as lane-marking edges is slightly
  softer. (`ffmpeg -i day.mkv -fps_mode passthrough frame%04d.png` writes
  them all; frame 1 is the gray lead-in when the day starts with a gap.)

**The encoder version matters** (checked on the server, Oct 5, evening-rush
frames). Debian 13's newer SVT-AV1 needs 13–15% more space than the 1.7
release the benchmark used, at the same quality, so the cameras service
runs on Ubuntu 24.04 for SVT-AV1 1.7. Version 1.7 gave byte-identical files
on the server and on the benchmark machine, so the server's CPU changes
speed, not results.

| Encoder, preset, crf | 656: size, SSIM | 752: size, SSIM | Time for 26 frames |
|---|---|---|---|
| **SVT-AV1 1.7, preset 6, crf30** (chosen) | 335 KB, 0.980 | 199 KB, 0.982 | 10–11 s |
| SVT-AV1 2.3, preset 6, crf30 | 386 KB, 0.976 | 221 KB, 0.977 | 3–4 s |
| SVT-AV1 2.3, preset 4, crf30 | 384 KB, 0.980 | 231 KB, 0.981 | 9–11 s |
| SVT-AV1 2.3, preset 4, crf32 | 338 KB, 0.977 | 198 KB, 0.978 | 9–11 s |

None of 2.3's tuning options (`tune`, temporal filtering, variance boost,
quantization matrices) closed the gap.

**Speed on the server** (Oct 5, a frozen set of 320 frames: 20 from each of
16 key cameras, 4 of them full-HD I-84 cameras; 8 virtual CPUs):

| Encoder and preset | How run | Frames/s | Size | SSIM |
|---|---|---|---|---|
| SVT-AV1 1.7, preset 6 | one encode at a time | 1.6 | 11.18 MB | 0.9751 |
| **SVT-AV1 1.7, preset 6** (in use) | **4 side by side** | **5.1** | 11.18 MB (byte-identical) | 0.9751 |
| SVT-AV1 1.7, preset 8 | 4 side by side | 16.4 | 11.90 MB (+6%) | 0.9714 |
| SVT-AV1 2.3, preset 6 | 4 side by side | 13.8 | 13.29 MB (+19%) | 0.9712 |
| SVT-AV1 2.3, preset 8 | 4 side by side | 21.3 | 13.86 MB (+24%) | 0.9695 |

- **Four encodes side by side are about 3x faster** than one encode using
  every core, with byte-identical output, so the roll-up runs four at a time.
- **Version 1.7 at preset 8 beats 2.3 at preset 6** on speed, size and
  quality at once, so 2.3 is out.
- **Preset 8 is the lever for scale:** about 3x faster again, for 6% more
  space and slightly lower SSIM.
- **Time per day:** the 34 key cameras (about 49,600 frames) take about 2–3
  hours at preset 6. All about 210 cameras (about 300,000 frames) would take
  about 16 hours at preset 6 or about 5 at preset 8, on the same 8 CPUs. The
  roll-up runs at low priority until it's done, so no overnight window
  limits it, and the server has plenty of idle CPU around the clock.

**The first nightly roll-up** (Oct 5's partial day, 6:20 PM to midnight,
rolled up at 12:05 AM):

| | Frames | JPEGs | Videos | Smaller by |
|---|---|---|---|---|
| 30 ACHD key cameras (768×466) | about 9,800 | 432 MB | 121 MB | 3.6x |
| 4 ITD I-84 cameras (1920×1166) | about 1,000 | 511 MB | 265 MB | 1.9x |
| All 34 key cameras | 10,772 | 942 MB | 385 MB | 2.4x |

- **Night costs more, and the HD cameras most:** evening and night frames
  carry sensor grain. The four I-84 cameras are 54% of the JPEGs and 69% of
  the video. Downtown cameras with steady lighting reached 8–10x.
  Downscaling the HD cameras before encoding is an option for the storage
  decision.
- **Time:** the 34 camera days took 23 minutes with four encodes side by
  side, about 8 frames a second, so a full day should take under 2 hours.
  The 381 road-weather camera days (a few frames each) took 11 minutes.
- **Failures:** 4 of 415 camera days failed because their frames had an odd
  height (328×339, 1280×777); the encoder needs even sizes. Frames are now
  cropped by one pixel, and the four were redone.
- **Clock check:** 23:00 into camera 656's video shows its timestamp bar at
  10:59:05 PM.

**Why daily rather than hourly files.** Each file starts with a full frame,
which costs about 3.5–4.3 ordinary frames (evening rush, both cameras).
With 60 frames an hour, that's about 4–5% of an hourly file, so daily files
are about 4–5% smaller. The JPEGs are kept for days anyway, so a nightly
roll-up adds no risk: if it fails, it can run again from the JPEGs. Daily
files also mean 24 times fewer files (about 210 a day for every camera, not
about 5,000), and one video per camera per day to watch.

**How a daily video is laid out:**

- **The day runs from local midnight to midnight** (America/Boise, so it
  follows daylight saving). A file is one calendar day as people read it,
  traffic is near its lowest at midnight, and daily counts use calendar
  days too. Daylight-saving days run 23 or 25 hours. The roll-up starts at
  12:05 AM, once the day's last frames are in.
- **A 60x time-lapse with true spacing:** one minute of the day is one
  second of video, so the video's mm:ss reads as the clock's hh:mm. Seeking
  to 17:10 shows 5:10 PM. A full day plays in 24 minutes.
- **Gray where there are no frames:** a gap of more than 10 minutes (camera
  down, capture stopped) shows as plain gray instead of a stale picture.
- **A CSV beside each video** lists every frame: its time in the video, when
  it was fetched (UTC and local), and the original JPEG's size and SHA-256.
- **Playback speed costs nothing.** The same frames encoded at 1, 12, 24
  and 30 frames a second came out the same size, within 0.02% (evening
  rush, both cameras). Speed is only a timing label, so a faster copy can
  be made from the archive in a second without re-encoding, with
  bit-for-bit the same pictures (`ffmpeg -itsscale 0.0417 -i day.mkv -c
  copy fast.mkv` plays a day in about a minute). The archive keeps the 60x
  clock layout; faster viewing is a player setting or a quick copy.

## 11.6 Open questions for the owner

Answered Oct 5:

- **Capture plan:** all cameras, at their real refresh rate, scaled up in
  steps (§11.7).
- **Retention:** keep everything (video archive and measurements). Keep
  original JPEGs until they've been measured, or longer if disk allows.

- **Key cameras for step 2:** the suggested set (owner, Oct 5), 34
  cameras in [`ingest/key_cameras.csv`](../ingest/key_cameras.csv): the
  COMPASS most-congested segments on Chinden, Eagle Rd and I-84 (Karcher
  and Nampa-Caldwell are left out because Canyon County has no cameras);
  the COMPASS safety plan's high-crash intersections that have cameras;
  the starting list's Eagle & Fairview, Meridian & Overland, Chinden &
  Curtis/VMP and Cole & Overland; and every camera calibrated so far.
  Recording since 6:20 PM MDT, Oct 5.

Still open:

1. **Disk:** how much can the server give the archive? Everything needs
   about 1–2.5 TB a year (§11.7). This waits on the host inventory.
2. **Vehicle detector license:** permissive (recommended) or AGPL? See
   [DECISIONS.md](DECISIONS.md).

## 11.7 Processing pipeline (collect everything, measure every frame)

**Principle:** keep the archive so every measurement can be recomputed
when models or calibrations improve. Every measurement records the
pipeline version that produced it.

| Stage | What it does | Why |
|---|---|---|
| 1. Fetch and dedupe | Poll each camera in step with its about-60 s update cycle. Keep a frame only if the timestamp bar or the scene changed. | About one request per camera per update, and no duplicates |
| 2. Read the timestamp bar | The 511 bar gives the snapshot time to the second. Store it as `taken_at`, along with `fetched_at`. | Exact image times; staleness |
| 3. Quality checks | Frozen (scene identical while the bar advances), stale (bar stops advancing), blank or gray, too dark, blurred or obstructed (snow, raindrops), glare | Health monitor; bad frames are kept but flagged and not measured |
| 4. View check and alignment | Match against the camera's known views (pan-tilt-zoom presets). Small shifts are aligned; an unknown view raises "view changed" and pauses measurement until zones exist for it. | Operators re-aim cameras; zones must stay valid |
| 5. Masks | Blank out overlays (511 bar, ACHD label and logo) and everything outside the road | Prevents false detections |
| 6. Clean-up for measuring | Night denoising, contrast normalization, glare masking. Also a slowly updated "empty road" picture per camera and time of day. | Steadier detection at night, plus a second, model-free measure to cross-check the detector |
| 7. Vehicle detection | A permissively licensed detector, later fine-tuned on our own labeled frames (especially at night) | Vehicles per lane zone |
| 8. Map projection | Per view, an image-to-ground transform from 4 or more points matched against aerial imagery | Positions and queue lengths in meters, on our map |
| 9. Measurements | Per approach and lane zone: vehicles present, occupancy, back-of-queue distance. Where signal heads are visible: the color shown. | Queues over time, tied to signal state |
| 10. Store | Measurements go to TimescaleDB; frames to the daily AV1 archive with a frame index | Everything kept and reprocessable |

**What snapshots can't do:**

- At one frame a minute we see presence and queues, not speeds or
  vehicles passing. Counts need ACHD's detector data.
- **Signal colors from snapshots:**
  - Over many days, the share of snapshots showing green estimates the
    green share of the cycle, but only if snapshot times don't lock onto
    the cycle.
  - Snapshots come every 59 s, which drifts against typical 90–150 s
    cycles. The exact bar times let us check this. ⚠️ Unproven until we
    have data.

**Scaling up, politely:**

| Step | Cameras | Purpose |
|---|---|---|
| 1 | 2–5 | Daytime/night retest; tune stages 2–6 |
| 2 | 30–40 key cameras (34 recording since Oct 5) | First real measurements; check accuracy against manual counts |
| 3 | All about 210 | Full archive |

Before step 3:
- Read the 511 developer agreement for anything on image use or retention.
- Ideally give ITD a heads-up.

All cameras at one fetch per update is about 3.5 requests a second and
13–14 GB of downloads a day.

**Storage and compute for "everything"** (all about 210 cameras, 24 h):

| Item | Per day | Per year |
|---|---|---|
| Original JPEGs | 13–14 GB | About 5 TB |
| AV1 archive (2–7x smaller) | 2–7 GB | **About 0.7–2.5 TB** |
| Measurements | Under 100 MB | A few GB once compressed |

- **Detection:** about 3.5 frames a second on average. A small detector
  on CPU should keep up with about 8 cores. ⚠️ Estimate; measure it in
  step 1.
- **AV1 roll-ups:** about 15 CPU-minutes per hour for all cameras, from
  the benchmark above.
- **GPU:** optional. It mainly helps fine-tuning.
