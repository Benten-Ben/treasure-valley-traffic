# basemap: our own map of the valley

Builds every static map layer the app shows underneath the live data. The
output goes to `data/tiles/` (git-ignored), or wherever `TILES_DIR` points.
The app serves it at `/tiles/`: Caddy does this on the server, and a small
Vite plugin does it in development. There are no third-party tile hosts and
no API keys ([decision log](../docs/DECISIONS.md)).

The app reads `manifest.json` and shows exactly the layers listed there.
The contract is `BasemapManifest` in
[`app/src/lib/map/style.ts`](../app/src/lib/map/style.ts).

| Layer | Source | Output | Status |
|---|---|---|---|
| Streets, water, land use, labels | Protomaps daily OpenStreetMap build, cut to Ada + Canyon | `valley.pmtiles` | ✅ Built Oct 5 from the 2026-10-05 build: 38 MB, 14,228 tiles, zooms 0–15, downloaded in 8 s |
| Fonts, icons | `protomaps/basemaps-assets` | `fonts/`, `sprites/` | ✅ Built Oct 5 (14 MB of fonts, plus their OFL license) |
| Terrain (2.5D) | USGS 3DEP 1 m DEM (read at its 2 m level), newest survey wins; a 0.2° ring of the ~10 m 3DEP DEM around it; the ~30 m 1 arc-second DEM for z6–10 across the whole z6 tile (about 5.6° × 4.1°), so the zoomed-out view has no edge in sight | `terrain.pmtiles` (terrain-RGB, 512-px PNG, z6–14, about 3.5 m per pixel at z14) | ✅ Built Oct 5: 1,030 MB, 7,820 tiles (z6–10 from the wide layer). Re-tiling from the kept elevation rasters (`--skip-warp`) takes about 18 minutes on 4 cores. |
| Terrain, re-encoded | `terrain.pmtiles`, tile for tile (`terrain_reencode.py`): heights rounded to 1 m up to z10, 0.5 m at z11, 0.4 m at z12, 0.2 m at z13 and not at all at z14 (never more than half a step off), then lossless WebP | `terrain-webp-YYYYMMDD.pmtiles` (the same 7,820 tiles and zooms, `format: webp`), plus a copy of `manifest.json` that points at it | ✅ Built locally Oct 6 in 7 minutes on 3 cores: 1,030 → 568 MB (−44.9%); first load at the default view 8.64 → 4.57 MB (terrain 7.69 → 3.63 MB). Every tile decoded and checked. The steps were tuned by before/after screenshots: coarser ones drew contour lines across flat ground. Not on the server yet: the lead runs it at deploy. |
| Buildings with heights | Overture 2026-09-23.1 buildings | `buildings.pmtiles` (z14–15) | ✅ Built Oct 5: 351,776 buildings, 83% with heights, 14 MB |
| Imagery | USDA NAIP. Valley-wide: Idaho 0.6 m, July 2023 (the Oregon edge 0.3 m, 2022), from Microsoft Planetary Computer (anonymous token), each image's ~2.4 m level. Detail: **NAIP 2025 at 0.3 m** from USDA's image service (`--detail-source usda`), one export per zoom-16 block, one at a time, 2.5 s apart. | `imagery.pmtiles` (512-px WebP, z8–14, ~3.5 m at z14) and `imagery-detail.pmtiles` (z15–18, ~0.22 m at z18, within 250 m of the 228 cameras and 150 m of COMPASS's 585 signals, so around 813 points; drawn over the valley layer) | `imagery.py`: tested on a sample (full-resolution tiles checked against the source pixels). ✅ Valley built Oct 5 in about 7 minutes (173 MB). ✅ Detail rebuilt Oct 7 from NAIP 2025: 1,232 exports in about 95 minutes, 13,958 tiles, 398 MB; 0.85 m from NAIP 2023 at Eagle & Fairview. Its absolute position is still unchecked ([below](#naip-2025-detail-layer-oct-67)). |

Background on all of these: [docs/09](../docs/09-base-map-data.md).

## Build

```bash
basemap/build.sh                           # streets, fonts, icons → data/tiles/
python3.12 basemap/terrain.py              # terrain (about 5 GB of source tiles kept in data/terrain/src)
python3.12 basemap/terrain_reencode.py data/tiles/terrain.pmtiles --manifest-out data/tiles/manifest-webp.json
                                           # terrain as lossless WebP, about 45% smaller (see below)
python3 basemap/camera_points.py           # camera locations, for the imagery detail areas
python3 basemap/buildings.py               # buildings (DuckDB reads Overture in place)
python3 basemap/camera_points.py --signals # COMPASS's signal locations (kept locally only)
python3.12 basemap/imagery.py --detail-source usda --detail-maxzoom 18 \
    --detail data/cameras/cameras.geojson@250 \
    --detail data/imagery/points/compass-signals.geojson@150   # imagery (NAIP 2025 detail)
TILES_DIR=/srv/tvt/tiles basemap/build.sh  # on the server
```

Each step adds its entry to `manifest.json`, and the app shows whatever is
listed there. The app needs no change when a layer gains zooms: when the
NAIP 2025 detail layer went from z17 to z18, the map picked up the extra
zoom by itself.

### Switching terrain to WebP

The terrain re-encode is the exception: it writes a new, versioned file
(`terrain-webp-<date>.pmtiles`, never overwritten) and, with
`--manifest-out`, a manifest copy that uses it, and leaves `manifest.json`
alone. It prints the size per zoom and the largest height error, and fails
if any tile is more than half a step off. To switch the app over, keep the
old manifest and move the copy into place (the app fetches `manifest.json`
with `no-cache`); to go back, restore the old one:

```bash
cp data/tiles/manifest.json data/tiles/manifest-png.json
mv data/tiles/manifest-webp.json data/tiles/manifest.json
python3.12 basemap/terrain_reencode.py data/tiles/terrain.pmtiles --check data/tiles/terrain-webp-<date>.pmtiles --sample 0
                                           # compare every tile again, any time
```

Before/after screenshots of the hillshade and the app (foothills and valley
floor at z10, z13 and z15) come from `app/scripts/terrain-compare.mjs`.

### Tools

`python3.12` stands for whichever Python has GDAL's bindings
(`python3-gdal` on Ubuntu matches the system Python).

`pmtiles` (build it from source: `git clone https://github.com/protomaps/go-pmtiles`,
then `go build -o /usr/local/bin/pmtiles .`, or use a release binary where
GitHub releases are reachable), `git`, `curl`, `python3`. Later steps will also need
`gdal-bin` and `tippecanoe`, both from apt.

- **Terrain and imagery:** `gdal-bin`, `python3-gdal`, `python3-numpy`.
- **Buildings:** `pip install duckdb`, which fetches its spatial and httpfs
  extensions itself, plus `tippecanoe`.

The extract reads only the byte ranges it needs from the planet file
(about 140 GB), so the download is far smaller than the planet.

### Where it runs, and how often

The Oct 5 plan: the heavy builds (the OpenStreetMap/Protomaps extract, the
3DEP elevation turned into terrain tiles, Overture buildings) and history
loads such as crashes run **on the server, not in a development sandbox**,
"refreshed monthly or so". Continuous ingestion is separate.

**Open question:** how often to rebuild the base map. No refresh cadence
has been decided or recorded yet.

### Disk space

Measured from the Oct 5 cloud builds, to size the server VM:

| What | Size | After the build |
|---|---|---|
| Terrain: source tiles (`data/terrain/src`) | 5.1 GB | Deletable |
| Terrain: merged elevation raster | 5.0 GB | Deletable, though keeping it lets `--skip-warp` re-tile in about 18 minutes |
| Terrain: tile scratch | 0.8 GB | Deletable |
| Imagery: downloads plus scratch | About 1 GB | Deletable |
| Buildings: scratch | 0.1 GB | Deletable |
| Finished tiles | 1.2 GB at first; about 1.4 GB once the wide terrain layer was added | Kept |
| Go toolchain, to build `pmtiles` | 2.1 GB | Deletable |
| Docker images | About 3–4 GB, mostly TimescaleDB (estimate) | Kept |
| Ubuntu, build packages, database and camera frames | About 4 GB | Kept |

So terrain alone peaks at about 11 GB. Building everything on the server
peaks at **about 25 GB**; the steady state is **about 10 GB**, less if the
tiles are built elsewhere and copied in. That is why a 100 GB VM disk was
judged enough (the first suggestion had been 150 GB; the original sizing is
in [ch. 10 §10.4](../docs/10-architecture.md#104-server-plan)). The first
few archive cameras fit on that disk for some months; the full camera
archive doesn't.

Added since: the NAIP 2025 detail layer (398 MB) and the WebP terrain
(568 MB). The whole-valley NAIP 2025 layer chosen Oct 7 adds about 10 GB of
tiles and needs about 15–20 GB of extra working space while converting
([decision log](../docs/DECISIONS.md)).

## Lessons from the builds (Oct 5–7)

What went wrong, and what the scripts do now.

**Terrain** (`terrain.py`)

| Problem | Fix |
|---|---|
| Tile workers that read full-detail windows grew to about 5.5 GB each and were killed for running out of memory. | Each zoom reads small windows from the matching overview level, and each worker's GDAL block cache is capped (256 MB). |
| The first build ended about 20 km past the valley, with horizontal streaks where edge tiles had been extrapolated outward. | The wide ~30 m layer: terrain now runs to the horizon (the hills past Emmett), and the fine raster's edges are filled from it instead of smeared. The 1 arc-second DEM's overview 0 (about 2 arc-seconds, 45–60 m) is enough for z10. |
| GDAL's scratch files briefly landed in the repo root. | They now go in the build's work folder (`CPL_TMPDIR`). |

**Imagery** (`imagery.py`)

| Problem | Fix |
|---|---|
| Rendering straight from the remote NAIP images (cloud-optimized GeoTIFFs) took about 7 s a tile. | Prefetch the source images in parallel first, then render from the local copies: 610 files in 259 s instead of hours, then 2,754 valley and 3,119 detail tiles in 154 s (a small test area: 47 tiles in 1 s). |
| One fixed overview level doesn't suit every image: the Oregon strip is 0.3 m, Idaho 0.6 m. | Each image's overview is chosen by resolution (the coarsest still as sharp as the target). |
| Parts of the detail mosaic with no image coverage rendered black (24% of a North End z15 tile). | Uncovered areas are transparent, so the valley layer shows through. |
| ArcGIS adds a validity mask to its exported JPEGs that GDAL can't decode (NAIP 2025 from USDA's image service). | The mask is turned off in `imagery.py`'s GDAL config (`JPEG_READ_MASK=NO`). |
| The first NAIP 2025 dry run planned 1,232 exports at 1536 × 1536, about twice the pixels needed. | Each export is trimmed to the tiles it covers: about 1.4 gigapixels in all. |

**Small gotchas**

- `argparse` reads a `--bbox` value that starts with a minus sign as a
  flag: write `--bbox=-116.37,...`.
- GDAL picks the output format from the file extension, so `.part` outputs
  need `format="GTiff"` spelled out.
- Delete stale partial rasters before a rerun, or GDAL updates them in
  place.
- A full 512-px imagery tile can look flat, like an illustration, in an
  image viewer; at 2× it is a normal photo. Check crops before suspecting
  the pipeline.

**Checks that passed**

- A decoded terrain test tile matched the source exactly: 801.5 m at
  Eagle & Fairview.
- Full-resolution imagery tiles matched the source pixels (the sample test
  above).

## NAIP 2025 detail layer (Oct 6–7)

- **Real pace:** 3.7–4.7 s per export, not the 2.5 s planned, so the 1,232
  exports took about 95 minutes. USDA returned one 502, which the pull
  waited out and retried by itself.
- **Coverage:** z15–18 around about 813 points (the 228 cameras and
  COMPASS's 585 signals).
- **Spot check** of a z18 tile at Eagle & Fairview: Eagle Rd's lane lines,
  crosswalks, cars and a mast-arm shadow are sharp.
- **Fallback:** the old NAIP 2023 detail file was kept as a backup outside
  the served tiles folder.
- **To do: check its absolute position.** NAIP's guaranteed absolute
  accuracy is only ±4 m ⚠️ (about 1.5 m at the one site checked; it sits
  0.85 m from NAIP 2023 at Eagle & Fairview). Before NAIP 2025 positions are
  trusted for camera calibration, check them against our lidar terrain.
  Not done yet.

## Licenses and credit

- **OpenStreetMap data** (ODbL): the map must show "© OpenStreetMap". The
  manifest's attribution string does this.
- **Protomaps style and assets:** BSD/OFL; see the license copied into
  `fonts/`.
- **USGS 3DEP, NAIP:** public domain.
- **Overture buildings:** ODbL. Credit "Overture Maps Foundation, © OpenStreetMap contributors".
- **Overture:** ODbL for the OSM-derived parts.
