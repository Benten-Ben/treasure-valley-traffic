# basemap/sheets: image sheets for review

The landscape sprint checks its work by eye: masks, soils, crop fields, water, road surfaces, paths, fences and the
painted ground, each drawn over the aerial photo at the same places every time, and two batches go to the owner
(around days 9 and 15). This folder draws those sheets. It came out of sprint package F8 (Oct 11, 2026).

| Piece | File | Runs in |
|---|---|---|
| The places: ten test boxes, 34 key-camera intersections, two corridors, three spots | [`places.py`](places.py), [`places.json`](places.json) | anywhere (standard library) |
| A PMTiles v3 reader (and a small writer, for tests) | [`pmtiles.py`](pmtiles.py) | anywhere |
| The drawing: photo, overlays, legend, contact sheets, index | [`sheet.py`](sheet.py) | the worker image |
| The VM's runner, into the private files | [`../../deploy/bin/sheets`](../../deploy/bin/sheets) | the VM |
| Map sheets of the app itself (Playwright) | [`../../app/scripts/map-sheets.mjs`](../../app/scripts/map-sheets.mjs) | the laptop |

**Sheets are private.** They show places at full resolution and may draw internal layers (the base bake's ACHD
widths), so they go to the VM's private files, `/srv/tvt/private/sheets/<package>/<run>/`, and are never committed or
published. Each says so in its footer, with the strictest `republish` of what it draws. The City of Boise's tree
data is never read for them: the VM's runner won't mount it, nor production's trees archive, which holds rows derived
from it. The tests use synthetic data only.

## The places

```bash
python3 -m basemap.sheets.places                    # every frame: 94 today
python3 -m basemap.sheets.places cameras eagle-rd   # some sets or places
```

| Set | Ids | Frame | Where the centre comes from |
|---|---|---|---|
| `boxes` | `box-a` ... `box-j`, `box-downtown` (or just `a`, `downtown`) | the whole box at 1 m (1.47 km; downtown 2 km) | `basemap/ground/spec.json` |
| `cameras` | `cam-<image id>` (or the id) | 240 m at 0.25 m; the five interchanges 400 m at 0.5 m, the I-84/I-184 wye 1.4 km at 1 m | the two roads' crossing in OpenStreetMap |
| `corridors` | `eagle-rd-01` ... `-14`, `chinden-blvd-01` ... `-33` (or `eagle-rd`, `chinden-blvd`), south to north and west to east | 600 m at 0.5 m, every 580 m | the road's OSM centreline |
| `spots` | `table-rock`, `airport`, `industrial` | 2 km at 1 m; 5 km at 2.5 m; 1.8 km at 1 m | the OSM feature (peak, aerodrome, landuse) |

- The cameras are `plugins/cameras/ingest/key_cameras.csv`'s 34, by name; `places.json` holds only their centres. Those
  centres were derived from OpenStreetMap (ODbL, the Oct 5 extract), by [`derive_places.sql`](derive_places.sql) on
  the scratch database: each camera's own position only picked which crossing it watches. A test checks that every
  key camera has a centre.
- **Eagle and Chinden** are the two divided-road corridors the roads build is checked on (Eagle Road from Overland
  to Chinden, 8 km; Chinden Boulevard from SH-16 to Veterans Memorial Parkway, 19 km). The Eagle and Chinden
  intersection itself is `cam-655`.
- The industrial area is the Amalgamated Sugar Company in Nampa (Canyon County), so the spots have a Canyon frame
  too. Another is one line in `places.json`.
- An ad-hoc frame: `at:LON,LAT[,SIZE_M[,RES_M]]`, default 500 m at 0.5 m.
- `--res` and `--size` override every frame's. A resolution must be a level of the ground grid (it divides 10 m or
  is a multiple of it: 0.25, 0.5, 1, 2, 2.5, 5, 10 ...), so every frame lies on the grid, and exports on the grid
  (`crop_cover.tif`, the box classes) draw cell for cell.

## The photo

- **In the ten boxes:** the land-cover spike's NAIP crops on the VM (`/srv/tvt/work/landcover/naip2025/<box>.tif`,
  NAIP 2025 at 0.3 m; `naip2023/` for h, i and j at 0.6 m), the newest one covering at least 99% of the frame.
  The crops are cut to the box give or take a metre; the map's tiles fill the edge.
- **Elsewhere:** the map's own imagery tiles (`/srv/tvt/tiles`): `imagery.pmtiles` (NAIP 2023, to z14) and
  `imagery-detail.pmtiles` (NAIP 2025 county mosaics, z15–z17 across Ada and Canyon, z18 around cameras and
  signals). Each zoom up to the frame's resolution is laid over the one below, so a missing detail tile shows the
  coarser photo, never a hole. GDAL's PMTiles driver doesn't read WebP tiles, hence `pmtiles.py`.
- The photo isn't stretched: its colours are NAIP's own, as on the map, so the ground's colours can be compared with
  it. The MrSID decoding SDK that made the 2025 mosaics stays on the VM and out of the repository.
- With no photo the frame shows the flat Valley ground colour and says so.

Credit: USDA NAIP (public domain).

## Overlays

```bash
--layer soils/ground,by=ground_type          # an export layer: the plugin's newest export
--layer roads/surfaces@20261020T031500Z      # a given build
--layer ground_classes/*,kind=cat            # every layer of one export, as one overlay (the box classes)
--vector /in/f8/check.fgb,by=kind,where=n > 1
--raster /in/lidar-c/chm.tif,min=2,max=25,clip=1,credit=USGS 3DEP
```

- **Exports** are read through the ground's contract ([`../ground/README.md`](../ground/README.md)): `manifest.read()`
  and `latest()` check every file (size, sha256, header) and the inputs' licences, and each overlay carries its
  layers' credit, licence and `republish` onto the sheet and into `index.json`. `--no-verify` skips the file checks
  for a quick look at an export being written. FlatGeobuf layers draw as vectors, GeoTIFFs as rasters; JSON tables
  (soils' `palette.json`) aren't maps and are refused.
- **Any file** GDAL reads, in any CRS: NAD83 is read with the ground's null datum shift (`rasterize.srs_of`). Give its
  credit with `credit=`.
- Vectors draw polygons as a fill (holes cut) with an outline, lines, and points as dots, supersampled two times.
  `by=FIELD` colours by value, with the same colour for a value on every frame of the run. `label=FIELD` writes
  values (at most 300 a frame, no overlaps).
- Rasters with value labels in their manifest (`bands[].values`), or of an integer type, are categorical; others get a
  viridis ramp from `min` to `max` (default: the frame's 2nd to 98th percentile), `clip=1` clears values outside it.
- Colours: Okabe-Ito first, never red against green alone, and every colour is named in the legend.

The style options are in `python -m basemap.sheets.sheet draw -h`.

## What a run writes

`<out>/<UTC time>[-label]/`:
- `<frame id>.png` (or `.jpg` with `--format jpg`): the title, the photo beside the photo with the overlays
  (`--panels overlay` for the second alone), a scale bar and north mark, the legend with what each overlay drew in
  that frame, and the credits;
- `contact-<group>.png`: every frame of a set (or corridor) as a thumbnail;
- `index.json`: the arguments, every overlay's files with their sha256, builds, licences and credits, and per frame
  its bounds, photo source (crop or tile zooms), counts and seconds; a frame that failed has its error and the run
  exits 1;
- `index.html`, linking the lot.

Sizes and times, measured on the VM Oct 11: a camera frame with both panels is about 1.2 MB, a box about 9 MB; all
94 frames with one panel each took 2.3 minutes and 0.23 GB. The VM's disk is tight: draw the sets a review needs,
use `--panels overlay` or `--format jpg` for wide runs, and delete runs once reviewed.

## Running it

On the VM, through `/srv/tvt/work/bin/sheets` ([deploy/README.md](../../deploy/README.md#review-sheets-on-the-vm)):
light (1 GB, 1 CPU, no network, the checkout read-only), the exports of a scratch database's archive at
`$TVT_ARCHIVE`, other inputs read-only under `/in/`, and the sheets written to the private files.

```bash
/srv/tvt/work/bin/sheets -C <checkout> --pkg p7 -- --places cameras corridors \
  --layer roads/surfaces,by=material --layer roads/markings,color=#FFFFFF,width=1 --label review-1
/srv/tvt/work/bin/sheets -C <checkout> --pkg s5a --db tvt_s5a --in /srv/tvt/work/s5a/masks:masks -- \
  --places boxes --raster /in/masks/roofs_c.tif,kind=cat --label mask-v0
```

From the laptop the git-ignored `data/dev/sheets-remote.sh <worktree> <pkg> [options] -- <draw args>` copies the
worktree to `/srv/tvt/work/sheets-src/<pkg>/` and runs it (`data/dev/README-sheets.md`).

## Map sheets (the app)

The worker sheets show data; the map sheets show the map as people see it. `app/scripts/map-sheets.mjs` drives
Playwright on the laptop against the preview (`app-next`) and screenshots a list of views: the same places, each in
the looks and layer sets a review asks for. It's a script only for now; it runs once the landscape layers are on
the preview.

```bash
cd app && node scripts/map-sheets.mjs --url "$TVT_SHEETS_URL" --places cameras,spots --looks valley,clay \
  --layers ,trees --label review-1                      # writes data/sheets/<label>/ (git-ignored)
node scripts/map-sheets.mjs --list --places boxes        # the shot list, no browser
```

The preview's address isn't in the repository: pass `--url` or set `TVT_SHEETS_URL`. The screenshots stay on the
laptop until they're copied to the VM's private files (`data/dev/README-sheets.md`).

## Tests

```bash
python3 -m unittest discover -s basemap/sheets -t .          # places and PMTiles; the drawing tests skip here
/srv/tvt/work/bin/worker-test -C <checkout> discover -s basemap/sheets -t .   # all of them; a skip fails
python3 -m unittest discover -s deploy/tests                 # the VM runner (test_sheets.py) with heavy's
```

The drawing tests make a synthetic NAIP crop, synthetic WebP imagery tiles in a PMTiles archive, and synthetic
exports (a FlatGeobuf of squares, one with a hole, and a 10 m GeoTIFF on the grid with value labels) written through
`manifest.write()`, then check the pixels, the legend counts, the photo's sources and `index.json`.
