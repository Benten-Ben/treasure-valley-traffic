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
| Buildings with heights | Overture 2026-09-23.1 buildings | `buildings.pmtiles` (z14–15) | ✅ Built Oct 5: 351,776 buildings, 83% with heights, 14 MB |
| Imagery | USDA NAIP (Idaho 0.6 m, July 2023; the Oregon edge 0.3 m, 2022), from Microsoft Planetary Computer (anonymous token). Prefetched first: each image's ~2.4 m level for the valley, full-resolution windows around the cameras. | `imagery.pmtiles` (512-px WebP, z8–14, ~3.5 m at z14) and `imagery-detail.pmtiles` (z15–17, ~0.45 m at z17, within 250 m of each camera; drawn over the valley layer) | `imagery.py`: tested on a sample (full-resolution tiles checked against the source pixels). ✅ Built Oct 5 in about 7 minutes: 173 MB valley, 136 MB detail (228 cameras) |

Background on all of these: [docs/09](../docs/09-base-map-data.md).

## Build

```bash
basemap/build.sh                           # streets, fonts, icons → data/tiles/
python3.12 basemap/terrain.py              # terrain (about 5 GB of source tiles kept in data/terrain/src)
python3 basemap/camera_points.py           # camera locations, for the imagery detail areas
python3 basemap/buildings.py               # buildings (DuckDB reads Overture in place)
python3.12 basemap/imagery.py --detail data/cameras/cameras.geojson   # imagery
TILES_DIR=/srv/tvt/tiles basemap/build.sh  # on the server
```

Each step adds its entry to `manifest.json`, and the app shows whatever is
listed there. `python3.12` stands for whichever Python has GDAL's bindings
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
