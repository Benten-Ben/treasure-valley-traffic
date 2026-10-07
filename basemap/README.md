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
| Imagery | USDA NAIP. Valley-wide: Idaho 0.6 m, July 2023 (the Oregon edge 0.3 m, 2022), from Microsoft Planetary Computer (anonymous token), each image's ~2.4 m level. Detail: **NAIP 2025 at 0.3 m** from USDA's image service (`--detail-source usda`), one export per zoom-16 block, one at a time, 2.5 s apart. | `imagery.pmtiles` (512-px WebP, z8–14, ~3.5 m at z14) and `imagery-detail.pmtiles` (z15–18, ~0.22 m at z18, within 250 m of the 228 cameras and 150 m of COMPASS's 585 signals; drawn over the valley layer) | `imagery.py`: tested on a sample (full-resolution tiles checked against the source pixels). ✅ Valley built Oct 5 in about 7 minutes (173 MB). ✅ Detail rebuilt Oct 7 from NAIP 2025: 1,232 exports in about 95 minutes, 13,958 tiles, 398 MB; 0.85 m from NAIP 2023 at Eagle & Fairview |

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
listed there.

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
floor at z10, z13 and z15) come from `app/scripts/terrain-compare.mjs`. `python3.12` stands for whichever Python has GDAL's bindings
(`python3-gdal` on Ubuntu matches the system Python).

Tools: `pmtiles` (build it from source: `git clone https://github.com/protomaps/go-pmtiles`,
then `go build -o /usr/local/bin/pmtiles .`, or use a release binary where
GitHub releases are reachable), `git`, `curl`, `python3`. Later steps will also need
`gdal-bin` and `tippecanoe`, both from apt.

- **Terrain and imagery:** `gdal-bin`, `python3-gdal`, `python3-numpy`.
- **Buildings:** `pip install duckdb`, which fetches its spatial and httpfs
  extensions itself, plus `tippecanoe`.

The extract reads only the byte ranges it needs from the planet file
(about 140 GB), so the download is far smaller than the planet.

## Licenses and credit

- **OpenStreetMap data** (ODbL): the map must show "© OpenStreetMap". The
  manifest's attribution string does this.
- **Protomaps style and assets:** BSD/OFL; see the license copied into
  `fonts/`.
- **USGS 3DEP, NAIP:** public domain.
- **Overture buildings:** ODbL. Credit "Overture Maps Foundation, © OpenStreetMap contributors".
- **Overture:** ODbL for the OSM-derived parts.
