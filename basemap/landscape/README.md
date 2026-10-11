# basemap/landscape: the base bake

Water, paving, road surfaces and markings, piece lines and paved paths draw for every viewer from z8 to z16, in both
looks. Cutting them live from PostGIS would put every first load on cold cuts through the app's small pool, so they're
**baked after each build into one versioned PMTiles file** of vector tiles, served from `/tiles/` like the buildings
([DECISIONS](../../docs/DECISIONS.md), Oct 8). The layers people switch on and off (soils, crop fields, trails, burn
scars) stay live, on core's tile route ([ch. 15 §15.2](../../docs/15-plugins.md#152-what-a-plugin-is)).

The bake reads the same export manifests as the ground ([`../ground/`](../ground/README.md#export-manifests)). Every
export layer marked `base: true` becomes one source-layer of `landscape-<digest>.pmtiles`. The file is checked, then
switched in with an atomic entry in `tiles/manifest.json`, keeping the file it replaces.

Built Oct 11 (landscape sprint package S5b). Package names and C numbers refer to the sprint plan (v3), which is
kept with the private files.

| Piece | File | Runs in |
|---|---|---|
| The spec: zooms, writer options, budget, how many files are kept | [`spec.json`](spec.json) | anywhere |
| What a bake reads, its rules, its entry, the tiles manifest | [`plan.py`](plan.py) | anywhere (standard library) |
| Reading a PMTiles file's header, metadata and tile sizes; new metadata | [`pmtiles.py`](pmtiles.py) | anywhere (standard library) |
| The commands, and the writer (GDAL's PMTiles driver) | [`bake.py`](bake.py) | `bake` in the worker image; `status`, `check` and `rollback` anywhere |

## For a plugin: exporting a base layer

A base layer is a FlatGeobuf layer of an export (`$TVT_ARCHIVE/<plugin>/export/<build>/`, written with
`manifest.write()`), with `"base": true`. The bake reads each plugin's **newest** export, so one export holds all of a
plugin's layers, base or not.

| Rule | Why |
|---|---|
| An integer `id` field, unique in the layer, from 0 to 2^53 − 1 | It becomes the feature id and stays a property, so MapLibre's `promoteId` finds it (the canal season's feature-state) |
| Fields are numbers, strings or booleans | What a vector tile holds: cast a date to text in the export |
| Every feature has a geometry of the layer's type or its multi form | A `LineString` layer takes LineStrings and MultiLineStrings; a GeometryCollection, a point or a polygon sliver from a clip refuses the bake. PostGIS's FlatGeobuf header says `Unknown`, so the bake checks each feature |
| Optional integer `minzoom` field: the feature's first zoom | e.g. water's main canals from z10 and ditches from z13 (plan §3.5). It's a directive, left out of the tiles. Past z16 means z16; the style does the rest |
| Optional `minzoom` and `maxzoom` on the layer's manifest entry | The layer's range, inside z8–16 (paving lots from z14) |
| Republish `yes` or `internal` | Sources published only as aggregates (Ridge to Rivers, the City's trails) and restricted data stay in side tables that cards read, never in the base (C17) |
| No input from a source on the bake's never list | IDWR's data (canal operators, the legal season window) and the City of Boise's layers stay in side tables that cards read, whatever their republish (C17). The list (`NEVER` in [`plan.py`](plan.py)) matches an input's `source`: `*/idwr*`, `*/boise_*` and `trails/r2r_*`. So an IDWR source is named `idwr_…`; a test fails if any plugin.json source credited to IDWR or the City doesn't match the list |
| A public plugin, with inputs from public plugins' sources only | Private plugins' data is never tiled ([ch. 15 §15.3](../../docs/15-plugins.md#153-private-plugins)) |

Only the fields the map needs go in: every byte is in every first load that shows the layer. Card details come from
the plugin's own API. The ground's products (`ground_mask`, `ground_classes`) are never read.

The source-layer is named **`<plugin>.<layer>`** (`water.reaches`, `roads.surfaces`), the same key core uses for the
toggled layers' versions. A base layer whose export holds no features isn't built: the file has no such source-layer,
and the entry lists it under `empty`, not `layers`.

## The file

| | |
|---|---|
| Format | PMTiles v3, gzipped Mapbox vector tiles, written by GDAL's PMTiles driver (3.13 in the worker image) |
| Zooms | z8 to z16. z16 tiles are about 440 m across here and 4,096 units wide, so about 0.11 m a unit; the app overzooms them for curbs, crosswalks and stalls. The header (and the entry) give the zooms that hold tiles, as the PMTiles spec has it, so the app never asks for empty ones: until water's z8 reaches are in, roads alone start at z14. go-pmtiles' `verify` passes |
| Writer | `EXTENT` 4096, `BUFFER` 80, `SIMPLIFICATION` 1 tile unit below z16 and none at z16 (real widths keep their shape). `MAX_SIZE` and `MAX_FEATURES` are set far out of reach, because past them GDAL quietly coarsens or drops features; the bake measures tiles itself instead |
| Name | `landscape-<digest>.pmtiles`. The digest covers the spec, the bake's own version, GDAL's version and every base layer's export, zooms and sha256. The same exports give the same name, and a bake with nothing new switches nothing. A file is never overwritten (`/tiles/` is cached for an hour, and PMTiles clients keep the header) |
| Metadata | GDAL's (`vector_layers`, bounds), plus `attribution` and `tvt.landscape`: the bake's entry, so each file says what it holds and who may see it |

**Budget.** Every z16 tile touching the downtown box (`../ground/spec.json`'s `downtown`, 2 × 2 km, 30 tiles) is at
most **60 KB as stored and sent** (gzip; 10^3 bytes, as `perf.mjs` counts). Downtown is where roads' surfaces and
markings are densest, so the budget binds once roads exports its base layers (P7). Every bake measures it from the
file's directory. **An over-budget bake isn't switched in** (exit 4, with the largest tiles named). The bake also
prints the largest tile and total per zoom.

**Size and time**, measured Oct 11 with synthetic exports at about the valley's scale: 150,000 road polygons from
z12 and 150,000 marking lines with per-feature zooms, 8% of them downtown. The file is 35 MB (14,773 tiles), and the
largest downtown z16 tile 21 KB. On the VM at the job table's caps (`--memory 2g --cpus 2`, `--threads 2`) it took
**2.6 minutes and under 100 MB** of memory, plus about 35 MB of temporary files. As a light job (1 CPU) it took 7.5
minutes: pass `--threads 1` there.

## Who may see it

The bake's `republish` is the strictest of its layers'. **While any layer is internal, the file is tailnet-only.**
Roads' widths come from ACHD and ITD, so the baked base is internal until a public variant is rebuilt from public
inputs (decision 4; `roads.xsection` keeps each piece's `lanes_source` for that).

That's machine-checkable in three places:
- the tiles-manifest entry's `republish` and `access` (`"tailnet"` or `"public"`), which `check_entry` keeps in step;
- each file's own metadata (`tvt.landscape`), so a file kept as `previous` still says what it is;
- **`bake.py check --tiles DIR --public`**, which exits 1 when the entry, or any landscape file in the folder (the
  previous one too: everything there is served), isn't public, or doesn't say, or when a stopped bake left its part
  file there (`.landscape-…part`, a full copy of that bake's tiles). A public deploy runs it and stops.

The site is reached only over the owner's LAN and tailnet today ([deploy](../../deploy/README.md#remote-access)), so
nothing serves the file further yet.

## The tiles-manifest entry

`tiles/manifest.json`'s `"landscape"`, written last and atomically (the app fetches the manifest with `no-cache`). The
app (S3a's base contributions) reads it; a contribution finds its source-layer in `layers`, and treats a missing
source-layer as not built (its `suppresses` only applies once it's built). `layers` lists exactly the file's
source-layers, each with at least one feature (`check_entry` and `check` hold both to that), so an empty water export
never hides Protomaps' water with nothing drawn in its place.

```json
"landscape": {
  "status": "baked",
  "file": "landscape-69f5a8c6bc10.pmtiles",
  "digest": "69f5a8c6bc10…",
  "format": "pbf", "minzoom": 8, "maxzoom": 16,
  "promoteId": "id",
  "layers": {
    "roads.surfaces": {"plugin": "roads", "layer": "surfaces", "build": "20261015T000000Z",
                       "geometry": "Polygon", "features": 150000,
                       "fields": {"id": "int", "surface": "string", "lanes": "int", "measured": "int"},
                       "minzoom": 12, "maxzoom": 16, "licence": "ODbL-1.0", "republish": "internal",
                       "credit": ["© OpenStreetMap contributors", "Ada County Highway District"]},
    "water.reaches": {…}
  },
  "empty": [],
  "attribution": "© OpenStreetMap contributors; Ada County Highway District; …",
  "licences": ["ODbL-1.0", "public-domain"],
  "republish": "internal", "access": "tailnet",
  "inputs": ["roads/surfaces@20261015T000000Z", "water/reaches@20261012T031500Z"],
  "budget": {"zoom": 16, "box": "downtown", "maxBytes": 60000, "tiles": 30, "largest": 21403,
             "at": "16/11616/23924", "roads": true},
  "writer": "GDAL 3.13.3",
  "built": "2026-10-20", "spec": 1,
  "previous": "landscape-0123456789ab.pmtiles"
}
```

| Field | What |
|---|---|
| `status` | `baked`, or `empty` (`{"status", "reason", "previous", "built", "spec"}`: nothing to bake yet, or every base layer is empty) |
| `file`, `digest` | the file under `/tiles/`, and the full digest its name is cut from |
| `minzoom`, `maxzoom` | the zooms the file holds tiles at, inside z8–16: the vector source's |
| `promoteId` | `"id"`, MapLibre's vector source option as it is (every source-layer has `id`) |
| `layers` | the built source-layers (each in the file, with at least one feature): its export (`plugin`, `layer`, `build`), geometry, features baked, the fields the tiles carry, its zoom range in the file, licence, republish and credits |
| `empty` | the base layers read whose export held no features, sorted: not built, so not in the file or in `layers` |
| `attribution` | every built layer's credit once, in layer order (the source's attribution; MapLibre shows it while one of its layers is visible) |
| `licences` | every built layer's licence, strictest first. An ODbL layer makes the tiles a derived database: published, they stay ODbL |
| `republish`, `access` | the strictest built layer's republish, and who may be served the file: `public` only when that's `yes` |
| `inputs` | every export layer read, `<plugin>/<layer>@<build>`, empty ones included |
| `budget` | the downtown z16 check: tiles with data, the largest and where, and whether roads was in |
| `previous` | the file switched out, kept for clients still reading it and for `rollback`; null when there's none |

## Switching in

1. Each plugin's newest export is read. A manifest that plainly holds no base layer (it parses, and every layer says
   `"base": false`) isn't the bake's business and isn't checked, so a broken export of another plugin, or one naming
   a private plugin's source the bake's container can't see, doesn't hold it up. Every other manifest is checked in
   full, and its base layers' files with their sha256: one that fails refuses the bake, rather than dropping a
   contribution from the map.
2. **Nothing served is dropped unasked.** If the file served now has a source-layer this bake wouldn't build (its
   plugin's newest export has no base layer, no longer has that one, or has it empty, or the plugin has no export at
   all, as with `--archive` pointing at the wrong folder), the bake is refused (exit 2), naming each and why. That
   includes switching a baked entry to empty. `--allow-drop` says it's meant; the served file is kept as `previous`,
   so `rollback` brings it back. `status` says the same beforehand.
3. GDAL writes the tiles in a work folder (a temporary folder unless `--work` says otherwise). Each feature is checked
   as it's copied: its id, its geometry and its type, its zoom. The bake also checks that the file holds as many
   features as the manifest says. A layer with no features gets no source-layer.
4. The file is read back: gzipped MVT at z8–16, exactly the source-layers built, and GDAL opens it. Then it's
   measured against the budget.
5. It's copied into the tiles folder under a hidden part name, with the bake's entry and credits in its metadata,
   fsynced, and renamed to `landscape-<digest>.pmtiles`.
6. The manifest's entry is replaced atomically. The file served until then becomes `previous`, even when the entry
   naming it is broken (another contract, say): clients may still be reading it.
7. Every other `landscape-*.pmtiles` is deleted, so **the last two are kept**.

A stopped bake leaves at most a part file, which the next bake removes (and `check --public` reports until then). Two
bakes can't overlap: each holds a lock file in the tiles folder. `rollback` switches the entry back to the previous
file, from that file's own metadata, and keeps both.

## Commands

```bash
python3 basemap/landscape/bake.py status --archive $TVT_ARCHIVE [--tiles DIR]   # what a bake would hold; exit 3: nothing
python3 basemap/landscape/bake.py bake --tiles DIR [--archive DIR] [--work DIR] [--threads N] [--allow-drop]  # worker image
python3 basemap/landscape/bake.py check --tiles DIR [--public]                   # the entry against the files
python3 basemap/landscape/bake.py rollback --tiles DIR
python3 -m unittest discover -s basemap/landscape -t .                          # the worker tests skip here
/srv/tvt/work/bin/worker-test -C <checkout on the VM> discover -s basemap/landscape -t .   # all of them
```

Exit codes: 0 done, or nothing to change; 1 `check` found a problem, or the writer failed; 2 refused (a missing
folder, a broken export, a layer or feature that may not be baked, a file already named for this bake that isn't
it, or a served source-layer this bake would drop, without `--allow-drop`); 3 nothing to bake (`status`); 4 over the
budget, nothing switched in.

**On the VM.** The bake is a heavy job in the sprint's table (`--memory 2g --cpus 2`, any window, after each build).
It's the last step of the refresh cascade after a new extract (osm-load, the builds, trails-match, the exports, then
the bake), and of the deploy runbook (bake, then `app-next`). On a branch it runs against the scratch archive, never
production's (`deploy/scratch/README.md`). Its build name for the staleness marks is `landscape-bake`.

```bash
/srv/tvt/work/bin/heavy --deadline 22:00 --runtime 20 --peak 1 "base bake (deploy)" \
  docker run --rm --memory 2g --memory-swap 2g --cpus 2 --network none --user "$(id -u):$(id -g)" \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e TZ=America/Boise -e TVT_ARCHIVE=/srv/archive \
    -v /srv/tvt/repo:/repo:ro -v /srv/tvt/archive:/srv/archive:ro -v /srv/tvt/tiles:/srv/tiles -w /repo \
    tvt-worker python basemap/landscape/bake.py bake --tiles /srv/tiles
```

The two host folders are `deploy/.env`'s `ARCHIVE_DIR` (Compose's default, `/srv/tvt/archive`, when the file doesn't
set it) and `TILES_DIR`: change them here if the file says otherwise. Both must exist (`docker run -v` would create a
missing one as root), and the tiles folder must be writable by the user the container runs as. GDAL writes in the
container's own `/tmp` (about the file's size; it goes with the container), so there's no work folder to make or
clean. The bake needs no network.

The tests' exports are synthetic: FlatGeobuf files around downtown written with GDAL, and copies of the ground's
PostGIS-written fixtures, with real manifests whose sources are checked against the repository's plugin.json files.
`tests/pmt.py` writes small PMTiles files (runs, leaf directories, uncompressed directories) with the standard
library, so the reader is tested apart from GDAL. The worker tests bake, read back with GDAL at several zooms, and
check the ids, the per-feature zooms, the geometry types, an empty layer left out, the swap and pruning, a broken
entry's file kept, the rollback, the budget (3,000 lots crowded into one downtown tile), the refused drops, and the
refusals.
