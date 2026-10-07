# cameras

Traffic and road-weather cameras
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have),
[docs/11](../../docs/11-camera-validation-layer.md)): ACHD's camera list,
511 Idaho's views linked to it, the frame streams for the key cameras and the
regional road-weather views, and the daily AV1 videos rolled up from them.
Later in this plugin: the video library and calibration (in `app/` today).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `achd_cameras` | daily | none stated | Ada County Highway District | internal |
| `idaho511_views_oneoff` | once, by hand (a dated private file) | none stated | ITD (511 Idaho) | internal |
| `idaho511_rwis_sites_oneoff` | once, by hand (a dated private file: ITD's road-weather stations statewide and Oregon DOT cameras in the regional ring) | none stated | ITD (511 Idaho) | internal |
| `idaho511_frames` | stream (key cameras every 50 s; road-weather views every 10 min) | none stated | ITD (511 Idaho) and ACHD | no: images stay on the server |

Details of each source: [ingest/README.md](../../ingest/README.md).

**Tables:** `core.camera`, `core.camera_view`, `core.camera_calibration`
(migration 0002 in `db/migrations/`). `core.camera.provider` (this plugin's
`migrations/0001_camera_provider.sql`) tells ACHD's traffic cameras from ITD's
road-weather stations (`ITD RWIS`) and Oregon DOT's cameras (`ODOT`): the map's
Cameras layer shows ACHD's, its Road weather layer the others (docs/14 §14.6).
The frames and videos live in `$TVT_ARCHIVE/cameras/`, not in the database.

**Code:** `ingest/sources/` (the sources and the frame stream),
`ingest/camera_video.py` (daily videos and the video library's index),
`ingest/key_cameras.csv` (the key cameras; `TVT_CAMERAS` names another list).
The `cameras` and `regional` services run this plugin from
`ingest/Dockerfile.cameras`.

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest stream idaho511_frames
TVT_ARCHIVE=data/archive python3 -m ingest rollup --day 2026-10-05   # by hand (the stream does it nightly)
TVT_PRIVATE_DATA=<private data folder> python3 -m ingest run idaho511_rwis_sites_oneoff   # road-weather stations, by hand
python3 -m unittest discover -s plugins/cameras -t .
```

**Ethics:** the road network, not people: no plate or face recognition, no
tracking of individuals. Images come only from 511 Idaho's republished copies
(`/map/Cctv/<id>`, IDs from the official API); ACHD's image host and 511's
list pages are off-limits for automated collection (CLAUDE.md).
