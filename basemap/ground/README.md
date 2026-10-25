# basemap/ground: the ground

The ground is the painted base of the Valley look: each soil type in its own colour and texture, measured from the
aerial photo over that type's uncovered ground, the photo's own colour where the ground departs from its type,
crops from the farm fields, and the land-cover classes in the ten test boxes
([DECISIONS](../../docs/DECISIONS.md), Oct 8). It is core, part of the base map ([ch. 15
§15.1](../../docs/15-plugins.md#151-whats-core)). Plugins feed it files, and it runs flat without them.

This folder holds the contract every piece of the ground shares, and the ground itself:

| Piece | File | Runs in |
|---|---|---|
| The grid: one grid for every raster, with the ten class boxes | [`grid.py`](grid.py), [`spec.json`](spec.json) | anywhere (standard library) |
| Export manifests: what a plugin's export holds, under which licence | [`manifest.py`](manifest.py), [`fgb.py`](fgb.py), [`tif.py`](tif.py) | the ingest image (writes), the worker image (reads) |
| What the ground reads, the republish rule and the flat fallback | [`inputs.py`](inputs.py) | anywhere |
| The tile writer's spec, the tiles-manifest entry and the first-load budget | [`tiles.py`](tiles.py), [`spec.json`](spec.json) | anywhere |
| The window-rasterising helper P2 and G1 share | [`rasterize.py`](rasterize.py) | the worker image |
| Mask v0: what covers the ground, from raw inputs | [`mask.py`](mask.py) (the build, and reading it back), [`maskrules.py`](maskrules.py) (the rules), [`osmconf.ini`](osmconf.ini) | the worker image (the rules anywhere) |
| The contract on the command line | [`ground.py`](ground.py) | anywhere |
| The land-cover classes in the ten boxes: the rules, and the step that builds them | [`classrules.py`](classrules.py), [`classes.py`](classes.py) | the worker image |
| The painter: the soil base, crops and the box classes on any window | [`paint.py`](paint.py), [`colour.py`](colour.py) | the worker image |
| Texture and the photo's variation (G1b): noise, the sun and the light, Mahalanobis, shadows | [`texture.py`](texture.py) (NumPy only) | anywhere NumPy is |
| The DEM: the map's own terrain-RGB tiles onto the painter's 2 m grid, for `--dem` | [`dem.py`](dem.py) | the worker image |
| The tile writer and its PMTiles writer | [`tilewrite.py`](tilewrite.py), [`pmtw.py`](pmtw.py) (standard library) | the worker image |

Built Oct 11 (sprint package S5a: the contract, then mask v0) and Oct 15 (G1a: the box classes, the painter and the
tiles) and Oct 24 (G1b's code: texture and the photo's variation, below). Still to come: the valley-wide runs and the
seam sheets (G1b, [below](#g1b-texture-and-the-photos-variation)); the app's ground source on the
first use of Valley (with S3a). The base bake, which reads the same exports, is in
[`../landscape/`](../landscape/README.md) (S5b).
Package names and C numbers refer to the landscape sprint plan (v3), which is kept with the private files.

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
grid-based NAD83 transform. conda's PROJ sets `PROJ_NETWORK=ON` when it is activated, so PROJ would try to download
NOAA's HPGN grid from cdn.proj.org; offline that transform returns inf or fails (checked Oct 10 in `tvt-worker`). The
worker image now ends its activation with an `activate.d` script that sets `PROJ_NETWORK=OFF` (`ingest/Dockerfile.worker`),
so `pyproj.network.is_network_enabled()` is False inside it. `rasterize.py` switches PROJ's network off again in
process, as a second guard, and applies the policy: `rasterize.srs_of(crs)` for vectors, and `rasterize.warp_srs(crs)` as
`gdal.Warp`'s `srcSRS` for rasters (P2's NAIP to the 2 m COG). A compound CRS keeps only its horizontal part: the
QL1 lidar is NAD83(2011) / UTM 11N + NAVD88 heights (EPSG:6340+5703), and a raster written with vertical GeoKeys opens
as compound, but the ground is 2D and heights are values, never coordinates. Code that uses pyproj directly outside
that image calls `pyproj.network.set_network_enabled(False)` first.

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
an optional `-suffix`. A build whose id ends in **`-part`** is partial: it covers only part of what the export covers
(a quick look at one box, say). `builds()`, `latest()` and `find()` skip it, so it's never read as the newest, and
`inputs.resolve()` refuses one handed to it; read it by its folder (`read()`, or the sheet tool's `@build`).

The ground and the base bake read exports only through `manifest.read()`, `latest()` and `find()`, and all three
check the files, not only the manifest:
- **every file:** its size and sha256;
- **FlatGeobuf:** the header's geometry type, fields, feature count and CRS (`fgb.py`);
- **GeoTIFF:** the size, the bands' count and sample types, the pixel corners and the EPSG code (`tif.py`, from the
  tags, never the pixels), so a raster half a cell off the grid, or the wrong size, is refused;
- **JSON:** that it parses, and that its `"schema"`, if it states one, is the manifest's.

The manifest's `plugin` must be its folder's (`<archive>/<plugin>/export/<build>`). The ground reads only the
plugins and products it uses (`inputs.exports()`), so a broken export of another plugin can't hold it up. The bake
reads the newest manifests that hold a base layer and checks only the base layers' files; one of those that's broken
refuses it, rather than dropping a layer from the map ([`../landscape/`](../landscape/README.md#switching-in)).

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
| `inputs[]` | every source the layers were made from: `name`, `licence`, `republish`, `credit`, and optionally `source` (the plugin source it came from, `<plugin>/<source>`), `version`, `url`, `doi`, `sha256`, `retrieved`, `note`. Every input must be used by a layer |
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
| `ODbL-1.0` | yes | OpenStreetMap; Overture's themes made from it: buildings, transportation, divisions, and the base theme's OSM types ⚠️. Share-alike |
| `CC-BY-4.0` | yes | e.g. the HydroShare canal network (cite its DOI) |
| `CDLA-Permissive-2.0` | yes | e.g. Overture's places ⚠️ |
| `Copernicus` | yes | Sentinel data ("Contains modified Copernicus Sentinel data 2025") |
| `none-stated` | per source | agency data with no licence grant. The owner decides per source, in its plugin.json: COMPASS's hub layers and NIFC's WFIGS are `yes`; ACHD's and ITD's tables `internal`; Ridge to Rivers `aggregates` |
| `restricted` | no | data we may use but never publish |

- Overture's licence differs by theme (and the base theme's land cover is ESA WorldCover's ⚠️): check the theme's
  before naming its class.
- An input taken from a plugin source names it in `source`, e.g. `"roads/achd_roads"`. A `none-stated` input must
  name one, because its republish is the owner's call for that source, not a licence's. `read()` and `write()` check
  each named source against plugin.json (this repository's plugins and `TVT_PLUGIN_PATH`'s): the source must exist,
  and the input is no looser than its republish there.
- A layer's republish is at least as strict as each of its inputs': the strictest wins.
- Its `credit` carries every input's credit.
- Its licence is one of its inputs'. A layer with an ODbL input is ODbL itself, and its republish carries any
  stricter input's limit. Otherwise it's the strictest input's: a layer made from public-domain and `restricted`
  data is `restricted`, and from public-domain and `none-stated` data, `none-stated`.
- A new licence class is added to `LICENCES` in review, before any export names it.

**`base: true`** marks a layer for the base bake (S5b). It must be a FlatGeobuf with an integer `id` field (the bake's
`promoteId`, for feature-state such as the canal season). The bake's own rules (unique ids, an optional per-feature
`minzoom`, republish yes or internal, public plugins only) are in
[`../landscape/`](../landscape/README.md#for-a-plugin-exporting-a-base-layer).

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
(the strictest input's) and licence (the share-alike input's, or else the strictest input's). It checks the result,
the inputs' sources and every file's header, and writes the manifest atomically.

Notes from the checks:
- **A null shifts the columns after it** (PostGIS 3.6.4's `ST_AsFlatGeobuf`, reproduced Oct 11): the next non-null
  value is written under the null's column index, so a null `misc` before `mukey` read back as `misc` = the mukey
  and `mukey` = null. Put every nullable column last (one at most), or `coalesce` it; soils' and water's exports do.
- `ST_AsFlatGeobuf` refuses `numeric` columns ("column type not supported"): cast them to `float8`.
- Without the spatial index (`ST_AsFlatGeobuf(q, false, …)`), the header has no feature count; pass `features`.
- A `date` column comes out as `datetime`.

**Checking one:** `python3 basemap/ground/ground.py check-export $TVT_ARCHIVE/soils/export/<build>`.

## What the ground reads

The ground is an **ODbL produced work built from public inputs only** (C17), so every input is republish `yes`.
`inputs.resolve()` refuses an export layer that isn't, or that reads anything that isn't, rather than quietly making
the ground internal. The roads build is never read: its widths come from ACHD and ITD (internal), so the ground keeps
OSM's class widths (C6). It reads three kinds of input.

**Plugin exports.** The layer names and the fields marked here are what the ground looks for. A plugin that changes
one changes this table and `inputs.USES` in the same review.

| Export layer | Format | Needs | Without it | Made by |
|---|---|---|---|---|
| `soils/ground` | FlatGeobuf, polygons | integer `ground_type` | **the ground stays flat** | P1-data |
| `soils/palette` | JSON `soils.palette/1` | per type `gid` (ground.fgb's `ground_type`): `status` (`measured`, or a fallback: `series`, `texture`, `albedo`; `none`), `lab_med`, `lab_cov`, `l_p10`, `l_p90`, `oct_l`, `oct_c` ([soils](../../plugins/soils/README.md#the-palette)) | flat colours per ground type, labelled | P2 |
| `farm/crop_cover` | GeoTIFF, 10 m grid | bands group, state, confidence | **the ground stays flat** | P3-data |
| `farm/fields` | FlatGeobuf, polygons | numeric `bearing` (degrees from north) | **the ground stays flat** | P3-data |

Farm's two layers had a fallback, CSB 2025 plus CDL 2025 (C7), for the weeks before farm's crop cover. It landed
(P3-data) before the painter was built, and the painter was never built to read CSB and CDL itself, so the fallback
was retired (fix round 1 of G1a): a Valley without its crops isn't painted, rather than painted with none under
another label.
| `water/mask` | FlatGeobuf, polygons | | mask v0's NHD and OSM water | P4-data |

**The ground's own products** are written through the same export contract, under `$TVT_ARCHIVE/<product>/export/
<build>/`, so their inputs, licences and sha256 are declared and checked like a plugin's. No plugin may take these
names. A product may be made from the raw inputs below only, each under its licence there, so nothing internal can
reach the ground through it, however it's labelled.

| Product | Format | Needs | Without it | Made by |
|---|---|---|---|---|
| `ground_mask` (mask v0) | FlatGeobuf, polygons: `roofs`, `roads`, `paving`, `water` and `covered` ([below](#mask-v0)) | every one of those layers | **the ground stays flat** | S5a-2 |
| `ground_classes` | one GeoTIFF per box on the 0.5 m grid, named by the box's id (`a`, …, `downtown`, …), exactly on its window | | the boxes show the valley paint | G1a |

The spike's classes didn't go in as they were: their road reference, and the rule that keeps cells within 2 m of a
mapped road from turning green, read ACHD's segments (internal). G1a rebuilt them with OpenStreetMap's roads only
([below](#the-box-classes)). RCMAP calibrated the spike's bare cut once (0.16, now a constant); the build doesn't read
it, and its copy's origin and version (v7 or v8) are still to be confirmed ⚠️.

**Raw inputs**, read from files: what the products are made from, and what the painter reads directly.

| Input | Licence | What |
|---|---|---|
| `osm` | ODbL-1.0 | S1's cut of the held Idaho extract, through GDAL's OSM driver. The extract has no Oregon, so the box's Malheur slice has no OSM |
| `overture-buildings` | ODbL-1.0 | roof footprints, as the map's `buildings.pmtiles` holds them at z15 (built by `basemap/buildings.py` from the Overture release it names) |
| `nhd` | public domain | NHD HU4 1705, water until water's export lands |
| `cdl`, `csb` | public domain | CDL 2025 (10 m) crop pixels and developed land; CSB 2025 fields, behind farm's crop cover (the box classes name them through the shrub builds) |
| `naip` | public domain | NAIP 2025 (0.3 m) for Ada and Canyon; NAIP 2023 (0.6 m) in boxes h–j |
| `naip-2m` | Copernicus | the 2 m COG P2 makes from NAIP 2025 in its decode pass (`naip2025_2m.tif`: red, green and blue on the June 18 flight's scale through same-day Sentinel-2, and the NDVI on Sentinel-2's scale, on the 2 m grid, with `flights.fgb`; [soils](../../plugins/soils/README.md#the-photo-statistics)). Public-domain NAIP carried through Copernicus-derived curves, so it credits both; its version is the sidecar's sha256 |
| `3dep` | public domain | the lidar products in the boxes, by vintage: 2023–24 QL1 in boxes b, c, d, downtown, f and h; 2019–20 QL2 in boxes a, e, i and j (e is on the 2019–20 QL2 survey, 2+ points/m²; [docs/09](../../docs/09-base-map-data.md)). Fits that need one vintage use the six 2023 boxes; a, e, i and j are held-out checks. The DEM for slope and aspect |
| `sentinel-2` | Copernicus | the July 2025 NDVI median, on the 10 m grid |
| `rcmap` | public domain | RCMAP fractional cover (30 m), which calibrates the classes' bare cut |

The painter names the raw inputs it reads directly, each with its **version**: a checksum, release or year, such as
the OSM cut's MD5, `"2025"` for CDL, or NAIP's release. A fallback that reads raw files (`Use.fallback_reads`; none
does today) needs their versions too. `tiles.digest()` refuses a plan that reads a raw input without one, so a new
release always gives a new tile name. The ground's attribution credits exactly what it reads: those raw inputs, then every export layer's
credits.

```python
from basemap.ground import inputs
plan = inputs.resolve(inputs.exports(archive), versions={"naip-2m": "<the 2 m COG's sidecar sha256>"})
```

`python3 basemap/ground/ground.py status --archive $TVT_ARCHIVE` shows what the ground would read today, each
fallback and why, the credits, and whether it can be painted. It opens only the exports above. A missing archive
folder is an error (exit 2), never "nothing exported yet".

## Mask v0

Mask v0 (C6) says what covers the ground. It holds exact areas for the painter (roofs, roads, paving and water,
which the photo's variation mustn't paint twice) and `covered` for the soil sampler (P2): everything that isn't
uncovered ground, grown so that an edge offset between the map and the photo doesn't leak pavement into a soil's
colour. It's the ground's own product, built on the server from raw inputs only, so it doesn't wait for any plugin
and nothing internal reaches the ground through it. Later masks come from plugin exports (water's `mask`, P4-data).

```bash
python basemap/ground/mask.py build --roofs <a copy of the map's buildings.pmtiles>    # into $TVT_ARCHIVE
python basemap/ground/mask.py build --roofs ... --box d --archive <another folder>     # one box, for a quick look
```

**Builds.** A build writes its files in `ground_mask/staging/<build>/`, `manifest.json` last, and then moves the
folder into `ground_mask/export/` in one rename, so `export/` only ever holds finished builds. One build runs at a
time (a lock in `ground_mask/`).
- **Stopped:** a build that fails, or is stopped with SIGTERM (`docker stop`, the scratch wrapper's limits and disk
  checks), removes its staging folder.
- **Killed:** one killed outright (out of memory) leaves the folder, and the next build sweeps it.
- **Pruned:** after a whole build, only the newest two whole builds are kept (`--keep`). The one just written is
  never removed, and neither is the one the ground tiles were painted from (`--tiles`, default `$TVT_TILES`: the
  builds `tiles/manifest.json`'s `ground` entry names).
- **Partial:** a `--box` or `--bounds` build is partial. Its id ends in `-part` (`<time>-box-d-part`), readers skip
  it, and it isn't pruned. The command line refuses to put one in `$TVT_ARCHIVE`, so give `--archive` another folder
  (on the server, a work folder mounted into the job); a partial id for a whole build, or a whole id for a partial
  one, is refused too. Look at one with the sheet tool's `ground_mask/<layer>@<build>`, or
  `mask.latest(folder, partial=True)`.

It's a light worker job (1 GB, 1 CPU). Valley-wide on Oct 11 it took **about 11 minutes** (670 s after review; the
first run peaked at 474 MB): reading the cut took about 3.5 minutes, the roofs 3 and dissolving `covered` 4. It's
**360 MB on disk**, so the two builds kept take about 0.7 GB. Run it
through the scratch wrapper with the roofs' folder mounted (`--mount <folder>:/mnt/in:ro`). The map's tiles folder
can't be mounted, so first copy `buildings.pmtiles`, and the tiles manifest's `buildings` entry as `buildings.json`,
into a work folder.

| Input | Read from | What's taken |
|---|---|---|
| `osm` | S1's valley cut, `$TVT_ARCHIVE/osm/cut/valley.osm.pbf`, through GDAL's OSM driver with [`osmconf.ini`](osmconf.ini) (every tag, as JSON) | highway ways and waterways; railway tracks, runways and taxiways drawn as lines (sampling only, owner Oct 22); parking, highway areas (plazas drawn as multipolygon relations included), water, and the soils design's rail and aeroway areas (aprons, runways, taxiways, helipads, `landuse=railway`). OSM's buildings aren't read: Overture's roofs hold them |
| `overture-buildings` | a copy of the map's `buildings.pmtiles` at z15, with `buildings.json` beside it | every footprint. One crossing a z15 tile's edge comes in two pieces, and the tiles' coordinates are good to about 0.2 m |
| `nhd` | `$TVT_SOURCES/nhd/nhd_mapbox.gpkg` (HU4 1705) | Lake/Pond and Reservoir waterbodies; Stream/River and Canal/Ditch areas; stream, river and canal flowlines (canal and ditch lines for sampling only) |
| `cdl` | `$TVT_SOURCES/cdl/out/cdl_2025_10m.tif` | developed land, classes 123 and 124 (medium and high intensity), polygonised on CDL's own 10 m grid |

Each input is named in the manifest with its version and sha256: the OSM extract's MD5 (from the `valley.json`
beside the cut, which must describe the file), Overture's release (from `buildings.json`, or `--roofs-release`),
NHD's `HU4 1705, published 2023-12-09`, and CDL's year (from the file's name). NHD and CDL are NAD83, read with the
null datum shift.

**The layers** (all MultiPolygon, EPSG:32611, with a spatial index and an integer `id`):

| Layer | For | What | Fields |
|---|---|---|---|
| `roofs` | painting | Overture's footprints | `id` |
| `roads` | painting | the highway ways that cover the ground, each centreline grown to half its width (round ends, mitred bends) | `ref` (`w<OSM id>`), `highway`, `kind` (`major`, `street`, `service`, `walkway`, `path`, `track`), `surface` (`paved`, `unpaved`, `unknown`), `width` (m), `width_from` (`width`, `lanes`, `class`), `bridge` |
| `paving` | painting | parking lots at ground level, and highways drawn as areas | `ref` (`w…`, `r…`), `kind` (`parking`, `highway_area`), `surface` |
| `water` | painting | NHD's and OSM's water: bodies, and waterways grown to half their width. NHD's canal and ditch lines aren't here. **Filter on `intermittent`** (`where="intermittent = 0"`): it marks water that may be dry, such as foothill draws and grassy detention basins | `source` (`nhd`, `osm`), `ref` (`nhd:<permanent_identifier>`, `w…`, `r…`), `kind`, `intermittent`, `width` (lines; null for areas) |
| `covered` | sampling | everything that isn't uncovered ground, each grown by its buffer, then dissolved by `what` in 1 km blocks of the grid (one piece per block and what) | `what`, `buffer` (m) |

| `covered`'s `what` | From | Grown by (C6) |
|---|---|---|
| `roof` | `roofs` | 1 m |
| `road` | `roads` | 2 m beyond half the width |
| `paving` | `paving` | 2 m |
| `water` | all water, intermittent included (C6 and the soils design put no condition on it), and NHD's canal and ditch lines | 5 m (beyond half a line's width) |
| `aeroway` | OSM's aprons, runways, taxiways and helipads drawn as areas; runway and taxiway lines (45 m and 23 m wide ⚠️, or their `width` tag) | 2 m (beyond half a line's width) |
| `rail` | OSM's rail yards (`landuse=railway`); railway track lines (`rail`, `light_rail`, `narrow_gauge`, `preserved`; sidings too, not trams or tunnels), a 5 m bed per track ⚠️ (times the `tracks` tag, 1 to 6, when a line stands for several) | 2 m (beyond half a line's width) |
| `developed` | CDL 2025 classes 123 and 124 | none |

Sampling buffers have square ends and mitred corners, a little more than round ones would cover. Aeroway and rail are
for sampling only: the map doesn't draw them as surfaces, so the painter leaves them to the photo.
The bed and runway widths are estimates ⚠️ (5 m per track, runway 45 m, taxiway 23 m, as before Oct 11) that wait for
calibration in the ten windows. The lines only keep ballast and runways out of the soil sample, so a width on the wide
side costs a few sample pixels and nothing else.

**The rules** ([`maskrules.py`](maskrules.py), standard library, tested case by case):
- **Which highway ways count.** Every road, street, service way, sidewalk and crossing counts, whatever its surface:
  these are the ways the roads plugin draws (S1's `osm_valley`, `osm_street` and `osm_paving`; a test checks the
  rules against S1's partition). Pedestrian streets, cycleways and steps count unless tagged unpaved. Footways,
  paths, bridleways and tracks count only when tagged paved: an unpaved path is trodden soil, so it stays ground.
  Ways under the ground or indoors (tunnels, culverts) don't count, and neither do ways drawn as areas, which are
  `paving`.
- **Widths** are OpenStreetMap's own ⚠️. They come from the `width` tag (1–80 m), else `lanes` x 3.6 m + 2 m on a road,
  else the class's default (`maskrules.CLASS_WIDTH`, two-way and one-way). For example, residential is 10.4 m and
  unclassified 7.3 m, decision 10's local defaults. The roads build's ACHD and ITD widths are internal and never
  read (C6, C17). The ten windows calibrate them later.
- **Water.** From OSM: natural=water, riverbanks, reservoirs and basins (a detention, infiltration or evaporation
  basin is intermittent), and outdoor swimming pools; also waterways (river 15 m, canal 6 m, drain 3 m, stream
  2.5 m, ditch 2 m ⚠️, or their width tag), except in culverts. From NHD: Lake/Pond and Reservoir; Stream/River and
  Canal/Ditch areas; streams by stream order (2, 4 or 8 m ⚠️) and canals (4 m ⚠️). These aren't water: wetlands
  (vegetation; P14 reviews them), NHD's swamps, playas, inundation areas and washes, and pipelines.
- **Sampling keeps out all water; painting is the painter's choice.** Intermittent water is in `covered` like any
  other: a pond that holds water in the June photo mustn't be sampled as soil, and over-covering only costs
  samples. The `water` layer flags it, and a painter that wants only standing and running water filters on
  `intermittent = 0`.
- **NHD's canal and ditch lines are sampled around, not painted.** Much of their geometry is 1:24,000-era, and some
  canals have since been piped or built over. On Oct 11, 46% of the painted NHD canal area lay more than 20 m from
  any OSM water, and 6.8 ha of it lay under roofs (0.07 ha for OSM's canals). OSM's canals are painted, NHD's canal
  polygons too, and water's conflated mask (P4-data) decides the rest.
- **Paving.** amenity=parking at ground level (not underground, multi-storey, rooftop or carports, which roofs or
  the ground hide), and highways drawn as areas unless they're unpaved: a closed way with area=yes, area:highway,
  or a multipolygon relation, which is an area by definition (downtown's plazas, such as Cecil D. Andrus Park Plaza,
  are relations without area=yes).

**Reading it** goes through the shared rasterising helper:

```python
from basemap.ground import grid, mask
m = mask.latest(archive)                                   # the newest whole mask v0, files checked; None if none
for core, padded in grid.windows(grid.LEVELS["painter"], 2048, halo_m=20):
    sample = ~mask.covered(padded, m)                      # uncovered ground (or what=("roof", "water"), ...)
    roofs = mask.exact(padded, m, "roofs")                 # one exact layer, as a bool array
    wet = mask.exact(padded, m, "water", where="intermittent = 0")   # leave out water that may be dry
```

P2 reads it at NAIP's own 0.6 m windows, `mask.covered(R.target_of(naip_path, window), m)`. Vectors are carried to
any grid, so the 1–5 m buffers hold at any cell size.

**What the valley's mask holds** (build `20261011T144701Z`, Oct 11, from the Oct 5 extract):

| Layer | Features | MB | Of which |
|---|---|---|---|
| `roofs` | 364,480 | 100 | |
| `roads` | 167,071 | 109 | 71,957 walkways, 53,738 service ways, 26,955 streets, 8,607 major roads, 5,771 paved paths, 43 paved tracks |
| `paving` | 2,464 | 1 | 2,163 parking lots, 301 highway areas (22 of them relations, such as downtown's seven plazas, 1.6 ha) |
| `water` | 18,647 | 22 | 7,328 streams, 2,398 canals, 4,795 pools, 2,766 lakes, 645 ditches, 390 reservoirs, 165 rivers, 160 basins; 5,849 of them intermittent (4,560 of those are NHD stream lines) |
| `covered` | 20,057 | 127 | 653,511 buffers dissolved in 8,043 blocks |

Kept as separate buffers with round corners, `covered` alone was 342 MB, and the whole mask 614 MB.

The share of each box that `covered` keeps out of sampling, burned at 0.5 m: c (North End) 81%, downtown 69%, d 47%,
b 33% (water 19%), e 18%, h 9%, a 4%, j 4%, i 2% and f 0.3%.

## The box classes

The land-cover classes in the ten boxes are the ground's own product `ground_classes` (G1a): one GeoTIFF per box, on
its exact 0.5 m window, with two bands, `class` (what covers each cell) and `floor` (the ground under it, which the
painter paints). They're the land-cover spike's rules ([`classrules.py`](classrules.py); the owner's scheme and its
season in [DECISIONS](../../docs/DECISIONS.md), Oct 8), as a worker step that reads raw public inputs only
([`classes.py`](classes.py)):

| Step | Spike | What |
|---|---|---|
| The scheme | exp26, variant B | Roof; tree (2.4 m and up, and a shrub-height crown's skirt or gap); shrub (the shrub rule's kept cells, [ch. 19 §19.8](../../docs/19-trees.md#198-shrubs)); crop (pieces the shrub rule gave to a crop field); the rest of the 0.3-2.4 m band is tall grass, green or dry, or a hard thing when it's neither green nor a plant to the lidar, or a wall or fence when that's a straight thin run; an even patch of the band is tall grass, not shrub; flat and green is short green grass |
| Surfaced ground | exp28b | flat, not green and below the bare cut on the photo's NDVI (a 2.5 m median, 4 m^2 patches): dark to the lidar (asphalt) or pale (dirt, gravel, concrete); the rest is short dry grass |
| As of July | exp31 | one green cut (0.45) and one bare cut (0.16) on Sentinel-2's NDVI scale for every box; per 10 m cell, July 2025's green share against the photo's, beyond a margin of 0.35, dries or greens that share of the cell's low cells; a cell never green in July dries all of them, one always green greens them. Roads (OpenStreetMap's, within 2 m) never green |
| The floor | exp27 | under trees, shrubs, hard things and walls, the nearest ground cell's class; under closed canopy (85% of the 30 m around), forest floor |
| Mapped tracks | new (owner, Oct 8) | short dry grass within 2 m of a mapped `highway=track` becomes pale surfaced ground where the photo is 4% brighter than the ground 6-20 m beside the track (box f's tracks, which the July rule's bare cut loses in its May photo) |

Every number is the spike's (its experiments' records are on the server with the spike), kept in `classrules.py` as
constants; nothing is re-fitted per box. Water isn't a class: it comes from map data.

**Inputs** (a recipe file on the server names them, since they're files, not exports): per box, the spike's 0.5 m
lidar products (DSM, DTM), the trees build's building mask (Overture's footprints aligned to the lidar), the shrub
build's `why.tif`, cue cache and photo shift (plugins/trees, P11), the box's NAIP crop (2025 in a-f and downtown,
2023 in h-j), its point cloud (each ground point's intensity over its flight line's median: dark ground), July 2025
from Sentinel-2 and the same-day normalisation's NDVI curve, and S1's OpenStreetMap cut (roads and tracks). The
manifest names them as RAW inputs only (`3dep`, `overture-buildings`, `naip`, `sentinel-2`, `osm`, and `csb` and
`cdl` through the shrub builds' crop cover), so it's ODbL, republish yes.

**Frames.** The rules run on the lidar's grid, the photo moved onto it, as the spike did; the classes are then placed
in the box's window and moved into the photo's frame by the photo shift (OpenStreetMap and the map are traced on the
photo). The shift is the shrub build's, measured on its trees, unless the recipe gives the box its own (`"shift":
[east, north]`, metres, multiples of 0.5 m), which the report records (`shift_from`). In the first build, box b
moves 2 m west, h 1 m east and 0.5 m north, downtown 0.5 m east; the rest not at all ⚠️. Box d's lidar sits about
2.3 m east of its photo at ground level, but the shift measured on its trees didn't earn its distance, so the recipe
gives d its own: `"shift": [-2.5, 0.0]` (owner, Oct 22, answer 11 of the end-of-wave-1 decisions; 2.5 m is the
spike's 2.3 m rounded to the class grid). Box a keeps the shrub build's shift (none). The class build of Oct 23
(#281) is the first with it: its `report.json` records `shift_from` "recipe" for d.

```bash
python basemap/ground/classes.py build --recipe recipe.json [--box f --archive <another folder>]
```

It's a heavy worker job (4-6 GB, 2 CPUs): about 2-8 minutes a box, most of it reading the point cloud. Every box's
inputs are checked before the first box starts (the preflight), and one build runs at a time (a lock). It writes
`<box>.tif` per box, `report.json` (each box's inputs, shift, the July rule's counts and the class shares) and
`manifest.json` last, through a staging folder and one rename. After a whole build it keeps the newest two whole
builds (`--keep`), and never prunes the build the switched-in ground tiles name (`--tiles`, default `$TVT_TILES`), so
the inputs behind the live ground stay checkable.

**The first build** (`20261016T002641Z`, Oct 15, on the scratch database's archive; 40 minutes for the ten boxes,
under 6 GB; 18 MB). Each box's classes as a share of its cells with data, %:

| Box | Roof | Tree | Shrub | Crop | Tall grass, green / dry | Short grass, green / dry | Surfaced, dark / pale | Hard thing | Track cells | Same as the spike's (central 500 m) |
|---|---|---|---|---|---|---|---|---|---|---|
| a | 0 | 5 | 5 | 0 | 1 / 1 | 3 / 74 | 0 / 2 | 8 | 0 | 94% |
| b | 4 | 22 | 2 | 0 | 3 / 1 | 20 / 35 | 4 / 7 | 2 | 253 | 97% |
| c | 24 | 35 | 1 | 0 | 1 / 0 | 12 / 16 | 4 / 6 | 2 | 0 | 98% |
| d | 12 | 5 | 1 | 0 | 0 / 0 | 29 / 22 | 13 / 16 | 1 | 550 | 80% |
| e | 3 | 3 | 0 | 10 | 3 / 0 | 30 / 19 | 7 / 21 | 4 | 343 | 69% |
| f | 0 | 0 | 0 | 0 | 0 / 0 | 0 / 99 | 0 / 1 | 0 | 87,633 | 97% |
| downtown | 20 | 22 | 1 | 0 | 0 / 0 | 10 / 22 | 9 / 13 | 3 | 194 | 96% |
| h | 0 | 46 | 6 | 0 | 10 / 1 | 12 / 7 | 3 / 8 | 6 | 9,112 | 98% |
| i | 0 | 0 | 0 | 0 | 0 / 0 | 0 / 70 | 7 / 22 | 1 | 13,756 | 97% |
| j | 0 | 42 | 2 | 0 | 2 / 1 | 13 / 22 | 2 / 12 | 5 | 4,105 | 90% |

- **Against the spike:** the last column compares each cell of the box's central 500 m with the spike's "as of July"
  classes there, in the lidar's frame (a one-off check on the server, not committed). Where they differ: e's crop
  (the spike took it from its own field rule, flat green fields included; here only the shrub rule's crop pieces are
  crop, and the painter paints the rest of the crop cover's fields as crop anyway); d and e, whose photo the spike
  moved 3 m onto the lidar where the shrub build measured no shift (a 0.7 m, j 0.5 m), so their green and dry edges
  move; and the July tree level, which now comes from the whole box (e 0.56 against the pooled 0.70, j 0.62 against
  0.50).
- **Box d with a recipe shift:** `"shift": [-2.5, 0.0]`, the spike's ground-level offset (its lidar about 2.3 m east
  of the photo) rounded to the class grid. A quick look on Oct 15 (a partial build outside the archive) found 91% of
  d's cells agreeing with the spike (80% without), and the owner decided on Oct 22 that d's recipe takes it. The
  class build of Oct 23 (all ten boxes, 36 minutes under heavy) confirms it: d agrees in 90.9% of cells (79.8%
  before), with short green grass 92% (81%), short dry grass 85% (66%), pale surfaced ground 91% (73%) and dark 97%
  (89%). The other nine boxes' agreement is unchanged. The spike check moves the classes back into the lidar's frame
  by the shift the build used, the recipe's where it gives one.
- **Box f's tracks** are back: 87,633 cells (2.2 ha) of mapped track turn pale where the photo shows them, 1% of the
  box, against none from the July rule; the rest of f stays short dry grass. Boxes h, i and j gain 4,000-14,000
  track cells each.
- Box i's dark surfaced ground (7%) is lidar-dark desert floor, not asphalt ⚠️ (the spike's central 500 m had 1%).

## The rasterising helper

`rasterize.py` (worker image) burns vectors into one window at a time, so no step holds a valley-wide raster:

```python
from basemap.ground import grid, rasterize as R
for core, padded in grid.windows(grid.LEVELS["painter"], 2048, halo_m=20):
    roofs = R.rasterize(padded, mask.layer("roofs"))                        # mask v0's roofs (a manifest.Layer)
    band = R.grow(roofs, 3.0, padded.res)                                   # a 3 m band around them
    types = R.rasterize(padded, soils_ground, attribute="ground_type", dtype="uint16")   # a manifest.Layer
    weight = R.feather(types == 7, 20.0, padded.res)[core.inner(padded)]   # 20 m soft edge, cut to the core
```

- `rasterize(target, source, layer=None, burn=1 | attribute=..., where=..., all_touched=False, dtype="uint8")`. The
  target is a `grid.Window`, or `R.target_of(path, window)` for a raster's own grid, such as NAIP's 0.6 m windows in
  P2. The source is a path any OGR driver reads (with a layer name), or a `manifest.Layer`. A cell is burned when its
  centre is inside, unless `all_touched`. Only features near the window are read, through the FlatGeobuf index.
  Later features win where they overlap.
- `grow(mask, metres, res)`: a mask grown by a distance, measured between cell centres (the painter's 3 m band
  around vector surfaces, C8). Mask v0's sampling buffers are vectors already ([`covered`](#mask-v0)), so they
  don't depend on the cell size.
- `feather(mask, width, res)`: a 0 to 1 weight, 0.5 on the edge, linear across `width` metres. It's for the soil
  types' 20 m edges and the class boxes' 50–100 m. Two regions sharing an edge sum to 1.
- `distance(mask, res)`, `signed_distance(mask, res)`: metres to the mask, or to its edge.

Pad each window by the largest buffer or feather you use (`halo_m`), and the windows join without seams.

## The flat fallback

Without soils' `ground` layer or mask v0 there's nothing to paint on. The ground then stays **today's flat ground**: Valley
`#EEE7DA`, Clay `#F3EDE2` (`app/src/lib/map/flavors.ts` `GROUND`; `spec.json` keeps a copy that a test compares). It
also **says so**:
- `inputs.resolve()` returns a flat plan with the reason in plain words ("Flat ground: the painted ground needs the
  soil survey's ground types and mask v0, which aren't built yet.").
- `ground.py flat --tiles <dir> --archive $TVT_ARCHIVE` writes that reason into `tiles/manifest.json`'s `ground`
  entry (`{"status": "flat", "reason": …}`). With no entry at all, the ground hasn't been built. A missing archive
  folder, or an export it would read that is broken or not public, is refused (exit 2), and the entry is left alone.
- The app (G1a's wiring) keeps the flat ground and shows the reason, never another source in its place.

Clay is flat in v1 whatever the ground's state ([DECISIONS](../../docs/DECISIONS.md), Oct 8).

## The painter

[`paint.py`](paint.py) paints any window of the grid, at any of its levels (2 m for the valley file, 0.5 m for the
detail file, 10-40 m for the low zooms), from what `inputs.resolve()` returns. Bottom to top:

1. **The soil base.** Each soil polygon in its ground type's colour from soils' palette: the measured OKLab median
   (`measured`), or the colour it borrowed (`series`, `texture`), as measured from NAIP 2025 over the type's
   uncovered ground on the June 18 flight's scale, painted as it is (the photo's own colours). A type with no colour
   (`none`: Dams, Mined land, Pits and dumps, NOTCOM) is a flat colour by its texture. The run's `run.json` counts and
   names them, and the PMTiles metadata and the tiles entry's `fallbacks` label them ("soils/palette: 4 ground types
   without a measured or borrowed colour, painted a flat colour by texture (Dams, Mined land, NOTCOM, Pits and
   Dumps)").
   SSURGO's Water units yield to the water layer: they take the nearest soil's colour within 50 m, never a "water"
   average. The types meet in a 20 m soft edge (a box blur in OKLab: a straight line between two types becomes a
   linear ramp 20 m wide).
2. **Crops**: farm's crop fields to their own edges (the field's 2025 group), and the crop cover's edge band where the
   CDL agrees, in the July state of the crop cover's 10 m cells (the nearest within 30 m where a field reaches past
   them): green fields a crop green (corn, hay, small grains, roots and vegetables, specialty; natural July colours,
   none darker than the ground band's lawn), growing ones 45% green over the soil, bare or harvested ones the soil,
   small grains straw. The states blend over 12 m inside the crop, and a field's edge softens over 12 m: the crop
   cover's 10 m cells, and CSB's edges (stepped on CDL's 30 m grid, 5-15 m off the photo), would otherwise show as
   blocks. Rows, a light and dark stripe along the field's bearing 8 m apart, give the direction (a texture: the real
   rows are 0.76 m), on levels fine enough to draw them. Never on mapped surfaces. Cropland clusters outside every
   field (the crop cover's confidence 3) are painted only where the photo's NDVI confirms them (G1b, below). Without farm's export the
   ground stays flat ([above](#what-the-ground-reads)).
3. **The box classes**, each cell's `floor` as tokens over the soil base (plan §3.4's ground band): short dry grass
   and roofs are the soil itself; pale surfaced ground the soil under 35% cream (the materials' gravel); dark surfaced
   ground the asphalt token `#989088`; short green grass the band's lawn `#748357`, tall green grass a lawn green of
   the same lightness; tall dry grass straw over the soil; forest floor the soil darkened. Where the crop cover says
   crop and the cell's `class` may be one (grass, pale ground, a hard thing, the shrub rule's crop), it's the crop.
   Painted at 0.5 m and averaged onto coarser cells, with the box's edge feathered over 75 m into the valley paint.
4. **The 3 m band (C8).** Surfaced classes on mapped surfaces (mask v0's roads, paving and roofs, and water's mask or
   mask v0's standing water) and within 3 m of them are painted from the soil base, so the photo's pavement doesn't
   show beside a vector road; G1b's photo variation keeps out of the same band.
5. **Texture and the photo's variation** (G1b, [below](#g1b-texture-and-the-photos-variation)).
6. Outside the grid, the flat Valley colour.

Each window is painted 64 m bigger and cut back, so windows meet without a seam (`test_paint.py`).

### G1b: texture and the photo's variation

[`texture.py`](texture.py) holds the rules (NumPy only, tested anywhere: `test_texture.py`); `paint.py` applies them.
`PAINTER_VERSION` is `g1b-1`. The inputs are optional and named on the command line (`tilewrite.py paint|assemble
--naip-2m DIR [--dem FILE]`, the same values for both, since they go into the run's digest as the raw inputs
`naip-2m`, named by the COG sidecar's sha256, and `3dep`, by the DEM's). Without `--naip-2m` the ground is G1a's plus the
noise.

- **Procedural noise** from each ground type's measured texture energy (soils' palette `oct_l` and `oct_c`, five
  octaves 1.2-19.2 m, for L and chroma). Value noise on a lattice (2 x the octave's metres) hashed from the absolute
  coordinates, with each octave's variance set to the type's energy (unit variance by `NOISE_NORM`, measured in
  `test_texture.py`), so every window and level samples one field and windows meet without a seam. An octave whose lattice is
  under two cells is skipped: 2 m cells draw the 2.4 m octave's lattice no finer than 4.8 m, z15's 1.73 m pixels the same,
  and a level of 40 m or coarser gets none. L moves at most 0.06 and chroma 0.025. A type with no measured energy takes
  the median of the measured types. Noise is off on mapped surfaces and fills in only the share of a cell the photo's
  variation does not carry.
- **The photo's variation** from the 2 m COG (`paint.Photo`): the colour on flat-ground light, less the type's median
  (the unfeathered soil colour), kept where it is within Mahalanobis 2.5 of the type in its own `lab_cov` spread and
  gone by 3.0 (a straight ramp between: beyond it the pixel is not this ground, and the base shows). It is added to the
  soil base, so the soil-coloured classes and crops that blend from the base carry it. Off in crop cells, on mapped
  surfaces and their 3 m band, in cast shadow, on slopes steeper than 30 degrees (`MAX_SLOPE_DEG`; the plan's cut-first
  fallback is 15), where the COG's mask has no photo, and for types without a spread (flat colours).
- **The DEM is the map's own terrain** ([`dem.py`](dem.py)). `terrain.pmtiles` (Mapbox terrain-RGB, 3DEP; z14 at 3.47 m
  at this latitude) is warped, bilinear, onto the painter's 2 m grid as a Float32 GeoTIFF (NaN for no data), a 4,096-cell
  block at a time with each block's tiles laid side by side in Web Mercator, so there is no seam between tiles or
  blocks (`test_dem.py`). The light is then normalised against the same surface the 3D map draws, with no new download.
  `dem.py build --terrain T --out DEM.tif` writes `DEM.tif.part` and renames it at the end, never overwrites, and
  writes `DEM.tif.json` (the source's sha256 and zoom, the grid, the file's own sha256). Pass `DEM.tif` as `--dem`; the
  run's digest takes its sha256 as `3dep`. `dem.py check` refuses a raster that isn't Float32 on the 2 m grid in
  EPSG:32611. Measured on the VM (Oct 24, under `heavy`, 3 GB cap, 2 CPUs): the whole map box (44,835 x 47,470 cells,
  132 blocks, all 4,171 z14 tiles it needs found) in **405 s, peak 539 MB**, a **3.23 GB** file on the cold drive; 100%
  of cells known, 662-2,456 m. Reading it back for the slope counts (below) peaked at 1.34 GB.
- **Illumination.** With `--dem`, each pixel's linear colour is multiplied by `sin(sun elevation) / cos(incidence)`,
  from the slope and aspect of the DEM at 2 m and the sun of the flight that took the pixel (the middle of the flight
  polygon's local start and end, read as MDT; `flights.fgb` beside the COG), kept between 1/2 and 2 and where the
  surface faces the sun. Without flights every pixel takes the reference day's sun (June 18, 13:00 local); without a DEM
  the colour is used as it is, and `run.json` says so (`paint.texture`).
- **Cast shadows** are dark (L at least 0.10 under the type's median), blue-shifted (b at least 0.01 under) and within
  40 m of a mapped roof, grown by one cell. They are treated as covered: the variation is off, the base shows. Outside the
  ten boxes the roofs are the only "something tall" the painter knows (no tree layer is an input), so a shadow beside a
  tree in open country is not recognised, but only a cell inside Mahalanobis 3.0 of the type is ever kept.
- **Crop clusters** (the crop cover's confidence 3, outside every field) are painted as crops where the photo covers the
  cell and its NDVI is at least 0.30. That reading of "the photo confirms" is the builder's; the plan does not give the number.
- **Seams.** Every field above is a function of absolute coordinates or of a window's own halo, so tiles of different
  runs meet like windows do (`test_paint.py` checks the noise and the photo across a window edge). The photo's own
  flight seams and the county line are in the COG already (soils' per-flight gains, one mosaic per place), and
  are for the seam sheets to judge.

**Tile size.** Measured on a synthetic tile (z15's 1.73 m pixel, WebP quality 80, L noise only): noise of sd 0.009
in L is 5.4 KB, 0.018 is 12 KB and 0.029 is 20 KB. The photo's variation carries finer detail than the noise and adds
to that. The real figure comes from the valley run, with `estimate --budget`; none has been made yet.

## The tiles

What G1a's writer makes (`spec.json` "tiles", `tiles.py`):

| | Valley file | Detail file |
|---|---|---|
| Zooms | z8–z15 | z17 |
| Where | the map box: 14,573 tiles (10,807 at z15) | the tiles touching the ten boxes: 612 |
| Pixel at the valley's middle latitude | 1.73 m at z15, matching the 2 m painter | 0.43 m at z17, finer than the 0.5 m classes |
| Made from | the painter grid, a z13 block at a time: the block's window (`tiles.tile_window`) painted at 2 m, warped onto its Web Mercator square at z15's pixel (2,048 px) and cut into 16 z15 tiles; its z14 and z13 tiles from 2 x 2 averages of those pixels; z12 to z8 each from its four children (kept losslessly), as `basemap/imagery.py` does. Never a full mosaic | the painter at 0.5 m, a z15 block at a time cut into 16 z17 tiles: the box classes inside each box, feathered in over 75 m, and the valley paint around them |
| File | `ground-<digest>.pmtiles` | `ground-detail-<digest>.pmtiles` |

- **All tiles:** 512 px, lossy WebP (quality 80 to start; G1a may lower it per zoom to meet the budget), opaque, XYZ
  in Web Mercator. Pixels outside the grid are the flat Valley colour, so the ground's edge matches the flat ground
  beyond it.
- **z16** overzooms z15 everywhere, the boxes included, as the plan's §3.5 has it. If the boxes' step from
  overzoomed z15 to the z17 classes looks abrupt, adding z16 to the detail file is 185 more tiles and one number in
  `spec.json` (`tiles.detail.minzoom`).
- **Size:** planned at about 0.6 GB valley-wide, about 40 KB a tile, and tens of MB for the detail file. G1a's flat
  paint is far smaller: the 558 valley tiles painted around the boxes and at the default view average 3.7 KB (2.1 MB),
  the 612 detail tiles 12 KB (7.4 MB). G1b's texture and photo variation set the real size (see its tile-size note above; no valley run yet).
- **Versions:** `<digest>` is `tiles.digest(plan, painter)`, where the writer's `painter` is `PAINTER_VERSION` and the
  sha256 of the painter's and writer's code (`tiles.code_digest`: `tilewrite.py` and every module of this folder it
  reads, in turn). It covers the spec, the painter and its code, the version of every raw input the plan reads, and
  the sha256 of every export layer, mask v0 and the classes included. A new OSM cut, NAIP release, CDL year, mask v0,
  class build or an edit to the painter gives a new name, and the same inputs and code give the same name. Files are
  never overwritten (`/tiles/` is cached for an hour, and PMTiles clients keep the header: switching in refuses a
  file of the same name with other bytes), and the last two are kept.
- **Blocks and resuming** ([`tilewrite.py`](tilewrite.py)): each finished block is a file of its WebP tiles with an
  index, written atomically into the run's folder (`<out>/blocks/`), so a stopped run picks up where it was, and the
  two PMTiles files are assembled from the blocks at the end, a block at a time ([`pmtw.py`](pmtw.py): clustered,
  identical tiles stored once, the header and root directory in the first 16 KiB, leaf directories when the tiles
  need them, with the tiles up to z12 kept in the root so a low-zoom first load reads no leaf). `--limit N` paints N
  more blocks and stops, for a run spread over several heavy windows.
- **One run, one digest.** The run's `run.json` records what it paints from: the digest, the inputs by name, the
  painter's version and code, and the painter's report (the soil types' colour sources). Every block records the
  digest too. A run resumes only while the archive's inputs and the code still give that digest; otherwise `paint`
  refuses and asks for a new folder, so a folder never mixes paint from two sets of inputs (a soils, farm, water,
  mask or class export made between two heavy windows, say). `assemble` refuses blocks painted for any other digest
  than the inputs give when it runs, so a file's name never claims inputs its tiles weren't painted from.
- **Whole or partial.** A whole pair of files (the one the manifest may switch in) must hold every tile of the spec:
  `assemble` without `--partial` refuses while any of the 14,573 valley tiles or 612 detail tiles is missing (it lists
  them by zoom), or while the pyramid was made before every z13 block was painted (each pyramid block records the
  children it lacked). The view tiles painted for the first-load estimate are left out of a whole file: its low
  zooms are the pyramid's. `--partial` takes whatever is painted, view tiles included, names the files `-partial`
  and gets no manifest entry; `--tiles` refuses it.
  Development runs go to the cold drive's ground folder, not the VM's disk, and their heavy jobs pass `heavy --cold`,
  so they don't start unless the drive is mounted with its room kept free.
- **Switching in:** `tiles.painted_entry(...)` is written last with `tiles.update_manifest()`, atomically:

```json
"ground": {"status": "painted", "file": "ground-0123456789ab.pmtiles", "tileSize": 512, "format": "webp",
           "minzoom": 8, "maxzoom": 15,
           "detail": {"file": "ground-detail-0123456789ab.pmtiles", "minzoom": 17, "maxzoom": 17,
                      "boxes": ["a", "b", "c", "d", "e", "f", "downtown", "h", "i", "j"]},
           "attribution": "© OpenStreetMap contributors; …", "licence": "ODbL-1.0", "republish": "yes",
           "inputs": ["soils/ground@20261012T031500Z", "ground_mask/roofs@20261011T040000Z", "raw/cdl@2025"],
           "fallbacks": ["soils/palette: …"],
           "built": "2026-10-20", "spec": 1}
```

**First-load budget** (`spec.json` "budget"). Measured at the default view: z10, pitch 45, 1280 x 800, the perf
harness's S1.
- **Valley:** every request to the ground's files counts: the PMTiles header, its directories and its tiles. They
  total **at most 0.6 MB** (10^6 bytes, as `perf.mjs` counts) in **at most 14 requests**, inside the page's 6 MB.
- **Clay:** the ground never loads (none).
- `tiles.first_load(requests)` checks a run's request list. For scale, the whole map box is 20 tiles at z10 and 9 at
  z9.
- **Measured** with the map library itself (`app/scripts/ground-firstload.mjs`: a bare page with the app's MapLibre
  and pmtiles, the ground as its only source, served by a local server that logs each range request): the default view
  draws **12 z10 tiles** (x 179-182, y 372-374) and nothing at other zooms. Their bytes come from G1a's paint
  (`tilewrite.py paint --view 10`: the default view's z10 tiles painted straight from the 10 m level and averaged onto
  the tile, as the pyramid's 2 x 2 averages of the 2 m paint would), and the full file's directory is laid out by
  `pmtw` with every valley tile (`tilewrite.py estimate`). On Oct 15 (painter g1a-3, scratch exports): **13 requests
  and 202,920 bytes** (the 16 KiB header and root directory, then 12 tiles of 1.0-54.6 KB, 186,536 bytes in all),
  against the budget's 14 and 600,000. G1b's texture and photo variation will add bytes to every tile: that leaves
  about 33 KB a tile of headroom on average. `tilewrite.py estimate --budget` exits 1 over the budget, so the same
  estimate is a check once G1b's tiles exist.
- **Why the valley run waits** (Oct 24). The DEM is built (above). The painter's other real inputs are not: the soils,
  farm and water exports don't exist yet (`ground.py status` on the production archive and on the scratch one says
  "no soils export", "no farm export", "no water export", "no ground_mask export", and the scratch database's
  `soils.polygon`, `soils.ground_type`, `soils.photo_stats`, `farm.field` and `water.body` hold no rows), because the
  production loads are still open (#42 soils, #44 water, and farm's). With no soil types and no palette spread, a run
  would paint the flat Valley colour plus noise: no photo variation to look at, no seam to judge, and no tile sizes to
  measure. So the valley-wide paint, the seam sheets and the first-load estimate on textured tiles stay to do, and
  start when those exports are built.
- **Still to do** (Oct 24). G1b's code and unit tests are in, and so is the DEM; what needs the real exports and the heavy window is not:
  - the valley-wide runs (at most two, under `heavy --deadline` with the cold-data drive) and the first-load estimate
    on textured tiles (`tilewrite.py estimate --budget`: 0.6 MB, 14 requests, tiles near 40 KB);
  - the seam sheets for the ten boxes and the county lines (private files), and the check of the per-flight colour
    gains at the flight seams (kept for now, owner Oct 22 answer 12);
  - the darkest soils (Boise Front north slopes) and box i's lidar-dark desert floor, which the classes may read as
    surfaced ground: the Mahalanobis, slope and shadow cuts above are set from the plan, not yet judged on them;
  - the slope cut (30 degrees now; 15 is the plan's fallback) and the NDVI cut for crop clusters (0.30), to be set
    from the sheets. The DEM gives the slope counts already (`dem.py slopes`, 2 m cells, Oct 24); the owner judges
    them with the sheets:

    | | over 15 degrees | over 30 degrees |
    |---|---|---|
    | whole map box (2,128 million cells) | 18.1% | 3.7% |
    | a Dry Creek | 74.7% | 24.5% |
    | b Barber Pool | 6.5% | 1.4% |
    | c North End | 1.5% | 0.2% |
    | d South Meridian | 1.9% | 0.006% |
    | e New York Canal | 1.0% | 0.009% |
    | f Initial Point | 3.4% | 0.3% |
    | downtown | 8.8% | 0.7% |
    | h Bogus Basin | 76.0% | 7.5% |
    | i Owyhee front | 25.4% | 0.5% |
    | j Owyhee Mountains | 66.8% | 9.5% |

    Moving the cut from 30 to 15 degrees takes the photo's variation off about 14 percent more of the box, and off
    50 to 69 percent more of boxes a, h and j (67 to 76 percent in all; the foothills and the mountains). Slope is of the map's own 3.5 m terrain
    resampled to 2 m, so it is smoother than the lidar's.
  - a sun from each flight's own place rather than the valley's middle (the DEM itself is done: `dem.py`, above);
  - repainting after the water and mask exports land, into new run folders (the digest takes care of the names);
  - the app wiring (S3a's follow-up, wave 2): the page's total at the default view (at most 6 MB) isn't measured with
    the ground in it yet, since the app doesn't load the ground until it's wired (the ground source on first Valley use,
    hidden under Aerial; Clay flat). Then the first load becomes a `perf.mjs` scenario with a budget that fails (the
    ground's 0.6 MB and 14 requests through `tiles.first_load`, and the page's 6 MB), measured on textured tiles rather
    than G1a's flat ones.

## Commands and tests

```bash
python3 basemap/ground/ground.py spec                               # the grid, the boxes, tile counts, the budget
python3 basemap/ground/ground.py check-export DIR                   # one export folder
python3 basemap/ground/ground.py status --archive $TVT_ARCHIVE      # what the ground would read; exit 3 = flat
python3 basemap/ground/ground.py flat --tiles DIR --archive $TVT_ARCHIVE
python basemap/ground/mask.py build --roofs DIR/buildings.pmtiles   # mask v0 (worker image), into $TVT_ARCHIVE
python basemap/ground/classes.py build --recipe R.json              # the box classes (worker image, heavy)
python basemap/ground/dem.py build --terrain terrain.pmtiles --out DEM.tif       # the map's terrain on the 2 m grid (worker image, heavy)
python basemap/ground/dem.py check DEM.tif ; python basemap/ground/dem.py slopes DEM.tif   # usable? and the share of cells over 15 and 30 degrees
python basemap/ground/tilewrite.py paint --out DIR --boxes --detail --view 8,9,10   # G1a's tiles, as blocks
python basemap/ground/tilewrite.py paint --out DIR --valley --pyramid --detail \
  --naip-2m COGDIR [--dem DEM.tif]                                  # every block (G1b; resumable); assemble takes the same
python basemap/ground/tilewrite.py assemble --out DIR [--partial | --tiles TILES]  # the PMTiles files (and switch in)
python basemap/ground/tilewrite.py readback --pmtiles F --zoom 15 --out DIR       # tiles around the boxes, for sheets
node app/scripts/ground-firstload.mjs --pmtiles F --out view.json   # the default view's requests (laptop)
python basemap/ground/tilewrite.py estimate --pmtiles F --view view.json [--budget]   # ... from a full file's directory
python3 -m unittest discover -s basemap/ground -t .                 # the worker tests skip here (test_texture.py needs only NumPy)
docker run --rm --memory 1g --cpus 1 --network none -v "$PWD":/repo -w /repo tvt-worker \
  python -m unittest discover -s basemap/ground -t .                # all of them; a skip here is a failure
```

`assemble --tiles` switches in under the manifest lock (`basemap/lock.py`). In a worker container on the VM, add
`-e TVT_TILES_LOCK_DIR=/srv/tvt/work/locks -v /srv/tvt/work/locks:/srv/tvt/work/locks` to the `docker run` (the same
path inside and out, so a host run locks the same files; [deploy/README.md](../../deploy/README.md#the-tiles-folders-locks)).
The paint and a `--partial` assemble write only under `--out` and take no tiles lock.

The fixtures are synthetic. `tests/fixtures/squares.fgb`, `lines-no-index.fgb` and `fields.fgb` (farm's fields, with
`crop_group` and `bearing`) were written by PostGIS's `ST_AsFlatGeobuf`, the exports' real writer. `tests/tiffs.py` writes small GeoTIFFs with the standard library, and
the worker tests check that `tif.py` reads GDAL's own (plain, COG, BigTIFF, big-endian, PixelIsPoint) the same way.
The worker tests make their own vectors with GDAL. Mask v0's (`test_mask.py`) make an OpenStreetMap file, an NHD
GeoPackage in NAD83, roofs in Web Mercator (also as a PMTiles file, with a roof across a z15 tile's edge) and a CDL
raster in Albers, build the mask and burn it through the rasterising helper; they also check partial builds,
staging, a stopped (SIGTERM) and a killed build, the lock and pruning. `test_maskrules.py` checks the rules
case by case, and against S1's partition (`ingest/osm_extract.py`) over a grid of tag sets and S1's own fixture. The
source checks read the repository's real plugin.json files.

G1a's: `test_classrules.py` checks each class from its cues, the sheet, wall and roof-sliver rules, the floor and
closed canopy, the July rule's drying, greening and margin, and the track rule, on small arrays. `test_classes.py`
moves classes into the photo's frame, places box h's narrower lidar grid in its window, maps cells onto July's 10 m
cells, burns lines, measures ground brightness from a synthetic point cloud (two flight lines, noise points) and writes
a box's GeoTIFF and manifest, which the ground's checks accept (and refuse with a non-raw input). It also runs the
build itself on a synthetic recipe for the ten boxes (a 20 m lidar grid in each, with a tree, a street and a mapped
track): the staging folder and the manifest's raw inputs, a partial build and the recipe's photo shift, the preflight
refusing before any box, a stopped build leaving nothing, the lock, pruning that spares the tiles' build, and the
command line refusing a partial build in `$TVT_ARCHIVE`. `test_paint.py`
paints a synthetic world: the 20 m ramp between two soil types, a Water unit taking the soil around it, a green corn
field in rows, box f's classes feathering in, paved classes beside a road painted from the soil, the flat Valley
outside the grid, seamless windows and coarse levels. `test_tilewrite.py` checks where a painted line lands in a
Web Mercator tile, a block's 21 tiles, the pyramid and its gaps, the assembled files (the run's digest and the flat
soil types in their metadata), a whole pair refused until every tile of the spec is there and then switched in, one
run per digest (a resume or an assemble after the inputs changed is refused, as are blocks of unknown origin), and
the first-load estimate; `test_tiles.py` the code digest and the builds the live tiles name; `test_pmtw.py`
(standard library) the PMTiles writer against the bake's reader, deduplication and leaf directories.

G1b's DEM: `test_dem.py` writes a synthetic terrain-RGB PMTiles file (a plane, four z14 tiles meeting at a corner, a z13 tile that must not be read) and checks the decode, the surface on the 2 m grid across the tile corner and between blocks, a missing tile, the sidecar, no overwriting, a stopped build, the files it refuses, `check`, the slope counts, and that `paint.Photo` reads the file.

G1b's: `test_texture.py` (NumPy only) checks the noise (unit variance, a function of the absolute coordinates, octaves
skipped on coarse levels), the sun over Boise, slope and aspect of planes, the illumination gain, the Mahalanobis
distance and its ramp, cast shadows and the NDVI band. `TestTexturePhoto` in `test_paint.py` paints the synthetic world
with a synthetic COG, DEM and no flights (the reference sun): the palette's spread and energies, noise energy and
seamless windows, the photo kept inside 2.5 sd and gone outside it or in the mask's hole, a coarse level, the band
beside a road, a shadow beside a roof, a north slope put back on flat light, a crop cluster confirmed or not by NDVI,
and a COG with the wrong shape refused; `test_tilewrite.py` checks the photo inputs' versions and that the digest
names them.
