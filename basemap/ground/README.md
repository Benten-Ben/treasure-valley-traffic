# basemap/ground: the ground's contract

The ground is the painted base of the Valley look: each soil type in its own colour and texture, measured from the
aerial photo over that type's uncovered ground, the photo's own colour where the ground departs from its type,
crops from the farm fields, and the land-cover classes in the ten test boxes
([DECISIONS](../../docs/DECISIONS.md), Oct 8). It is core, part of the base map ([ch. 15
§15.1](../../docs/15-plugins.md#151-whats-core)). Plugins feed it files, and it runs flat without them.

This folder holds the contract every piece of the ground shares:

| Piece | File | Runs in |
|---|---|---|
| The grid: one grid for every raster, with the ten class boxes | [`grid.py`](grid.py), [`spec.json`](spec.json) | anywhere (standard library) |
| Export manifests: what a plugin's export holds, under which licence | [`manifest.py`](manifest.py), [`fgb.py`](fgb.py) | the ingest image (writes), the worker image (reads) |
| What the ground reads, the republish rule and the flat fallback | [`inputs.py`](inputs.py) | anywhere |
| The tile writer's spec, the tiles-manifest entry and the first-load budget | [`tiles.py`](tiles.py), [`spec.json`](spec.json) | anywhere |
| The window-rasterising helper P2 and G1 share | [`rasterize.py`](rasterize.py) | the worker image |
| The contract on the command line | [`ground.py`](ground.py) | anywhere |

Built Oct 11 (sprint package S5a, first half). Still to come: mask v0 (S5a-2), the painter and its tiles (G1a),
texture and photo variation (G1b), and the base bake that reads the same exports (S5b, `basemap/landscape/`).

## The grid

One grid, so no step resamples another's output and nothing drifts by half a cell:

- **EPSG:32611** (WGS 84 / UTM 11N), on **Sentinel-2's own 10 m pixel edges** (multiples of 10 m in zone 11).
- Upper-left corner **E 495920, N 4855750**; 8,967 x 9,494 cells of 10 m; E 495920–585590, N 4760810–4855750.
  That's the map box (`basemap/build.sh`, lon −117.05 to −115.95, lat 43.00 to 43.85), projected with its edges
  densified and widened to whole 10 m cells. The July 2025 NDVI median is on exactly this grid.
- Two exact sub-grids with the same origin:

| Level | Cell | Cells | Used by |
|---|---|---|---|
| `sentinel2` | 10 m | 8,967 x 9,494 | Sentinel-2, farm's `crop_cover.tif` |
| `painter` | 2 m | 44,835 x 47,470 | the painter (G1), P2's NAIP COG |
| `classes` | 0.5 m | 179,340 x 189,880 | the land-cover classes in the ten boxes |

Rows count down from the north edge and columns east from the west edge, as in a GDAL raster. A `Window` is a
block of cells on one level, with its geotransform. A 10 m window is exactly 5 x 5 times as many 2 m cells, and
20 x 20 times as many 0.5 m cells. `grid.windows(res, size, halo_m=...)` walks a level in blocks. Each block comes
with a padded copy, so a buffer or feather of up to `halo_m` computed on the padded block and cut back
(`core.inner(padded)`) equals one computed on the whole grid. Each window has a stable `key`, so a long job can
record what it has done and resume.

```python
from basemap.ground import grid
for core, padded in grid.windows(grid.LEVELS["painter"], 2048, halo_m=20):
    ...                                         # padded.transform, padded.shape, core.inner(padded)
grid.box("d").window()                          # box d on the 0.5 m grid: 2,932 x 2,912 cells
grid.aligned(ds.GetGeoTransform(), 10)          # is a raster on the 10 m grid?
```

**Datum policy.** NAIP, 3DEP and the lidar products are in NAD83 (EPSG:26911 or 6340); CDL is NAD83 Albers. They are
read with the **null datum shift**: their coordinates are taken as WGS 84's, the way web maps and OpenStreetMap's
tracing imagery do. So OSM, Overture, NAIP and the lidar keep the agreement they were traced or measured with. The
true NAD83(2011)-to-WGS 84 offset here is about 1 m ⚠️, under the painter's 2 m cell. Never let PROJ choose a
grid-based NAD83 transform. The worker image sets `PROJ_NETWORK=ON`, so PROJ tries to download NOAA's HPGN grid from
cdn.proj.org; offline that transform returns inf or fails (checked Oct 10 in `tvt-worker`). `rasterize.py` switches
PROJ's network off and applies the policy: `rasterize.srs_of(crs)` for vectors, and `rasterize.warp_srs(crs)` as
`gdal.Warp`'s `srcSRS` for rasters (P2's NAIP to the 2 m COG). Code that uses pyproj directly calls
`pyproj.network.set_network_enabled(False)` first: `docker run -e PROJ_NETWORK=OFF` doesn't help, because the image's
conda activation sets it back to ON.

**The ten boxes** are the land-cover spike's test areas (agreed with the owner Oct 7;
[DECISIONS](../../docs/DECISIONS.md), Oct 8). They are in `spec.json`. Each box's
extent is its lon/lat box projected and widened to whole metres. That is exactly the extent of the spike's 0.5 m lidar
rasters, so every box lies on the 0.5 m class grid.

| Box | Area | E (m) | N (m) | 0.5 m cells |
|---|---|---|---|---|
| a | Dry Creek at Bogus Basin Road | 566158–567624 | 4836992–4838452 | 2,932 x 2,920 |
| b | Barber Pool, Boise River | 570583–572053 | 4822376–4823836 | 2,940 x 2,920 |
| c | North End and Hyde Park | 563401–564868 | 4830190–4831649 | 2,934 x 2,918 |
| d | South Meridian | 550317–551783 | 4821527–4822983 | 2,932 x 2,912 |
| e | New York Canal south of Nampa | 534107–535570 | 4816761–4818213 | 2,926 x 2,904 |
| f | Initial Point butte | 548605–550075 | 4801301–4802756 | 2,940 x 2,910 |
| downtown | Downtown Boise row (four 1 km lidar tiles) | 564000–566000 | 4829000–4831000 | 4,000 x 4,000 |
| h | Bogus Basin | 571467–572933 | 4845378–4846838 | 2,932 x 2,920 |
| i | Owyhee front at Wilson Creek | 526046–527514 | 4790071–4791521 | 2,936 x 2,900 |
| j | Owyhee Mountains near Silver City | 521260–522732 | 4763513–4764962 | 2,944 x 2,898 |

## Export manifests

A plugin's export command writes its files to `$TVT_ARCHIVE/<plugin>/export/<build>/`, then `manifest.json`, last.
A folder without a manifest is unfinished, and readers skip it. `<build>` is the UTC time, `20261012T031500Z`, with
an optional `-suffix`. The ground and the base bake read exports only through `manifest.read()`, `latest()` and
`find()`. All three check the files, not only the manifest.

Exports are **vectors** (FlatGeobuf, in EPSG:32611). Everything that rasterises lives here, in `basemap/ground/`.
The two non-vector exports are soils' `palette.json` (a JSON table) and farm's `crop_cover.tif` (a GeoTIFF on the
10 m grid).

```json
{
 "contract": 1,
 "plugin": "soils",
 "build": "20261012T031500Z",
 "created": "2026-10-12T03:15:00Z",
 "command": "python3 -m ingest soils-export",
 "inputs": [
  {"name": "ssurgo", "licence": "public-domain", "republish": "yes",
   "credit": "USDA NRCS Soil Survey Geographic Database (SSURGO)", "version": "FY2027"}
 ],
 "layers": [
  {"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "crs": "EPSG:32611",
   "geometry": "MultiPolygon", "features": 21999, "fields": {"id": "int", "ground_type": "int", "misc": "string"},
   "bytes": 1234567, "sha256": "…", "inputs": ["ssurgo"], "licence": "public-domain", "republish": "yes",
   "credit": ["USDA NRCS Soil Survey Geographic Database (SSURGO)"], "base": false}
 ]
}
```

| Field | What |
|---|---|
| `contract` | 1 |
| `plugin`, `build`, `created` | the plugin's name; the folder's name; the UTC time it was written |
| `command`, `note` | optional |
| `inputs[]` | every source the layers were made from: `name`, `licence`, `republish`, `credit`, and optionally `version`, `url`, `doi`, `sha256`, `retrieved`, `note`. Every input must be used by a layer |
| `layers[]` (all) | `name`, `file` (a plain name in the folder), `format`, `bytes`, `sha256`, `inputs` (names), `licence`, `republish`, `credit` (a list), `base`; optionally `title`, `note` |
| FlatGeobuf | `crs` (EPSG:32611), `geometry` (Point, LineString, Polygon, or their Multi forms), `fields` (name: type), `features`; optionally `minzoom`, `maxzoom` |
| GeoTIFF | `crs` (EPSG:32611), `grid` (`res`, `west`, `north`, `width`, `height`, on the ground grid), `bands` (`name`, `type`, and optionally `nodata`, `values` (code: label), `about`) |
| JSON | `schema`: `<plugin>.<name>/<version>`, e.g. `soils.palette/1` |

Field types are FlatGeobuf's, in lower case: `byte`, `ubyte`, `bool`, `short`, `ushort`, `int`, `uint`, `long`,
`ulong`, `float`, `double`, `string`, `json`, `datetime`, `binary`. Raster band types: `uint8`, `int8`, `uint16`,
`int16`, `uint32`, `int32`, `float32`, `float64`.

**Licences and republish** (C3, C17). `republish` uses plugin.json's words, from loosest to strictest: `yes`,
`aggregates`, `internal`, `no` ([ch. 15 §15.2](../../docs/15-plugins.md#152-what-a-plugin-is)).
- Every input names a licence class from `manifest.LICENCES`, and a republish value no looser than that class allows:

| Licence | Loosest republish | For |
|---|---|---|
| `public-domain` | yes | USGS (3DEP, NHD), USDA (NAIP, NASS's CDL and CSB, NRCS's SSURGO) |
| `CC0-1.0` | yes | e.g. ITD's WZDx (owner, Oct 6) |
| `ODbL-1.0` | yes | OpenStreetMap; Overture's buildings. Share-alike |
| `CC-BY-4.0` | yes | e.g. the HydroShare canal network (cite its DOI) |
| `CDLA-Permissive-2.0` | yes | Overture's other themes |
| `Copernicus` | yes | Sentinel data ("Contains modified Copernicus Sentinel data 2025") |
| `none-stated` | aggregates | ACHD, ITD's tables, IDWR, Ridge to Rivers, the City's trails |
| `restricted` | no | data we may use but never publish |

- A layer's republish is at least as strict as each of its inputs': the strictest wins.
- Its `credit` carries every input's credit.
- A layer with an ODbL input is ODbL itself.
- A new licence class is added to `LICENCES` in review, before any export names it.

**`base: true`** marks a layer for the base bake (S5b). It must be a FlatGeobuf with an integer `id` field (the bake's
`promoteId`, for feature-state such as the canal season).

**Writing one** from a plugin's export command (the ingest image includes `basemap/ground` for this):

```python
from basemap.ground import manifest
folder = manifest.export_dir(archive, "soils", manifest.build_id())
os.makedirs(folder)
# ... write ground.fgb: SELECT ST_AsFlatGeobuf(q, true, 'geom') FROM (SELECT id, ground_type, misc,
#     ST_Transform(geom, 32611) AS geom FROM soils.ground) q   -- true writes the spatial index
manifest.write(folder, "soils",
               inputs=[{"name": "ssurgo", "licence": "public-domain", "republish": "yes",
                        "credit": "USDA NRCS Soil Survey Geographic Database (SSURGO)", "version": "FY2027"}],
               layers=[{"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf",
                        "inputs": ["ssurgo"], "base": False}])
```

`write()` fills in what the files say. That's bytes and sha256 for every layer. For a FlatGeobuf, it's the geometry
type, fields and feature count from the file's header. It also sets each layer's credit (every input's), republish
(the strictest input's) and licence (the share-alike input's, or the one licence all its inputs share). It checks the
result, and writes the manifest atomically.

Notes from the checks:
- `ST_AsFlatGeobuf` refuses `numeric` columns ("column type not supported"): cast them to `float8`.
- Without the spatial index (`ST_AsFlatGeobuf(q, false, …)`), the header has no feature count; pass `features`.
- A `date` column comes out as `datetime`.

**Checking one:** `python3 basemap/ground/ground.py check-export $TVT_ARCHIVE/soils/export/<build>`.

## What the ground reads

The ground is an **ODbL produced work built from public inputs only** (C17), so every input is republish `yes`.
`inputs.resolve()` refuses an export layer that isn't, or that reads anything that isn't, rather than quietly making
the ground internal. The roads build is never read: its widths come from ACHD and ITD (internal), so the ground keeps
OSM's class widths (C6).

Raw inputs, read from files (mask v0 and the painter):

| Input | Licence | What |
|---|---|---|
| `osm` | ODbL-1.0 | S1's cut of the held Idaho extract, through GDAL's OSM driver. The extract has no Oregon, so the box's Malheur slice has no OSM |
| `overture-buildings` | ODbL-1.0 | roof footprints |
| `nhd` | public domain | NHD HU4 1705, water until water's export lands |
| `cdl`, `csb` | public domain | CDL 2025 crop pixels and developed land; CSB 2025 fields, the crop fallback |
| `naip` | public domain | NAIP 2025 (0.3 m) for Ada and Canyon; NAIP 2023 (0.6 m) in boxes h–j |
| `3dep` | public domain | the 2023–24 QL1 lidar products in the boxes; the DEM for slope and aspect |
| `sentinel-2` | Copernicus | the July 2025 NDVI median, on the 10 m grid |

Plugin exports. The layer names and the fields marked here are what the ground looks for; a plugin that changes one
changes this table and `inputs.USES` in the same review.

| Export layer | Format | Needs | Without it | Made by |
|---|---|---|---|---|
| `soils/ground` | FlatGeobuf, polygons | integer `ground_type` | **the ground stays flat** | P1-data |
| `soils/palette` | JSON `soils.palette/1` | | flat colours per ground type, labelled | P2 |
| `farm/crop_cover` | GeoTIFF, 10 m grid | bands group, state, confidence | CSB 2025 plus CDL 2025 (C7) | P3-data |
| `farm/fields` | FlatGeobuf, polygons | numeric `bearing` (degrees from north) | CSB 2025, no row bearing | P3-data |
| `water/mask` | FlatGeobuf, polygons | | mask v0's NHD and OSM water | P4-data |

`python3 basemap/ground/ground.py status --archive $TVT_ARCHIVE` shows what the ground would read today, each
fallback and why, the credits, and whether it can be painted.

## The rasterising helper

`rasterize.py` (worker image) burns vectors into one window at a time, so no step holds a valley-wide raster:

```python
from basemap.ground import grid, rasterize as R
for core, padded in grid.windows(grid.LEVELS["painter"], 2048, halo_m=20):
    roofs = R.rasterize(padded, "mask_v0.fgb", "roofs")                    # 1 inside, 0 outside
    sample = ~R.grow(roofs, 1.0, padded.res)                                # leave roofs plus 1 m out of sampling
    types = R.rasterize(padded, soils_ground, attribute="ground_type", dtype="uint16")   # a manifest.Layer
    weight = R.feather(types == 7, 20.0, padded.res)[core.inner(padded)]   # 20 m soft edge, cut to the core
```

- `rasterize(target, source, layer=None, burn=1 | attribute=..., where=..., all_touched=False, dtype="uint8")`. The
  target is a `grid.Window`, or `R.target_of(path, window)` for a raster's own grid, such as NAIP's 0.6 m windows in
  P2. The source is a path any OGR driver reads (with a layer name), or a `manifest.Layer`. A cell is burned when its
  centre is inside, unless `all_touched`. Only features near the window are read, through the FlatGeobuf index.
  Later features win where they overlap.
- `grow(mask, metres, res)`: the mask's buffers, measured between cell centres. Paving and roads get their class width
  plus 2 m, roofs plus 1 m, water plus 5 m (C6).
- `feather(mask, width, res)`: a 0 to 1 weight, 0.5 on the edge, linear across `width` metres. It's for the soil
  types' 20 m edges and the class boxes' 50–100 m. Two regions sharing an edge sum to 1.
- `distance(mask, res)`, `signed_distance(mask, res)`: metres to the mask, or to its edge.

Pad each window by the largest buffer or feather you use (`halo_m`), and the windows join without seams.

## The flat fallback

Without soils' `ground` layer there's nothing to paint on. The ground then stays **today's flat ground**: Valley
`#EEE7DA`, Clay `#F3EDE2` (`app/src/lib/map/flavors.ts` `GROUND`; `spec.json` keeps a copy that a test compares). It
also **says so**:
- `inputs.resolve()` returns a flat plan with the reason in plain words ("Flat ground: the painted ground needs the
  soil survey's ground types, which isn't built yet.").
- `ground.py flat --tiles <dir> --archive $TVT_ARCHIVE` writes that reason into `tiles/manifest.json`'s `ground`
  entry (`{"status": "flat", "reason": …}`). With no entry at all, the ground hasn't been built.
- The app (G1a's wiring) keeps the flat ground and shows the reason, never another source in its place.

Clay is flat in v1 whatever the ground's state (decision 6).

## The tiles

What G1a's writer makes (`spec.json` "tiles", `tiles.py`):

| | Valley file | Detail file |
|---|---|---|
| Zooms | z8–z15 | z16–z17 |
| Where | the map box: 14,573 tiles (10,807 at z15) | the tiles touching the ten boxes: 797 (612 at z17) |
| Pixel at the valley's middle latitude | 1.73 m at z15, matching the 2 m painter | 0.43 m at z17, finer than the 0.5 m classes |
| Made from | the painter grid: each z15 tile from its own window (`tiles.tile_window`), never a full mosaic; z14 to z8 each from its four children (2 x 2 average), as `basemap/imagery.py` does | the 0.5 m classes, with the valley paint resampled outside each box; the class edge feathers inside the box |
| File | `ground-<digest>.pmtiles` | `ground-detail-<digest>.pmtiles` |

- **All tiles:** 512 px, lossy WebP (quality 80 to start; G1a may lower it per zoom to meet the budget), opaque, XYZ
  in Web Mercator. Pixels outside the grid are the flat Valley colour, so the ground's edge matches the flat ground
  beyond it.
- **Why z16 is in the detail file:** the plan says "a z17 detail source". z16 is added (185 tiles), so the boxes don't
  jump from overzoomed z15 straight to z17. Elsewhere, z16 and up overzoom z15.
- **Size:** about 0.6 GB valley-wide, about 40 KB a tile, and tens of MB for the detail file.
- **Versions:** `<digest>` is `tiles.digest(plan, painter_version)`: the spec, the painter's version and every input's
  sha256. The same inputs give the same name. Files are never overwritten, and the last two are kept.
- **Switching in:** `tiles.painted_entry(...)` is written last with `tiles.update_manifest()`, atomically:

```json
"ground": {"status": "painted", "file": "ground-0123456789ab.pmtiles", "tileSize": 512, "format": "webp",
           "minzoom": 8, "maxzoom": 15,
           "detail": {"file": "ground-detail-0123456789ab.pmtiles", "minzoom": 16, "maxzoom": 17,
                      "boxes": ["a", "b", "c", "d", "e", "f", "downtown", "h", "i", "j"]},
           "attribution": "© OpenStreetMap contributors; …", "licence": "ODbL-1.0", "republish": "yes",
           "inputs": ["soils/ground@20261012T031500Z"], "fallbacks": ["soils/palette: …"],
           "built": "2026-10-20", "spec": 1}
```

**First-load budget** (`spec.json` "budget"). Measured at the default view: z10, pitch 45, 1280 x 800, the perf
harness's S1.
- **Valley:** every request to the ground's files counts: the PMTiles header, its directories and its tiles. They
  total **at most 0.6 MB** (10^6 bytes, as `perf.mjs` counts) in **at most 14 requests**, inside the page's 6 MB.
- **Clay:** the ground never loads (none).
- `tiles.first_load(requests)` checks a run's request list. The whole map box has 20 tiles at z10, so the far half of
  a pitched view has to come from lower zooms. G1a measures the budget with the app.

## Commands and tests

```bash
python3 basemap/ground/ground.py spec                               # the grid, the boxes, tile counts, the budget
python3 basemap/ground/ground.py check-export DIR                   # one export folder
python3 basemap/ground/ground.py status --archive $TVT_ARCHIVE      # what the ground would read; exit 3 = flat
python3 basemap/ground/ground.py flat --tiles DIR --archive $TVT_ARCHIVE
python3 -m unittest discover -s basemap/ground -t .                 # standard-library tests; the worker's skip
docker run --rm --memory 1g --cpus 1 --network none -v "$PWD":/repo -w /repo tvt-worker \
  python -m unittest discover -s basemap/ground -t .                # all of them; a skip here is a failure
```

The fixtures are synthetic. `tests/fixtures/squares.fgb` and `lines-no-index.fgb` were written by PostGIS's
`ST_AsFlatGeobuf`, the exports' real writer. The worker tests make their own vectors with GDAL.
