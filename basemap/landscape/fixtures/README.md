# Synthetic landscape fixtures

Made-up tiles for the browser specs. The laptop holds neither the landscape bake nor the painted ground, and real
data is never committed, so a spec for a baked contribution or the ground runs on these instead (plan v3 §4.1:
fixtures are synthetic; §5: specs sample 3 or 4 layer stacks). Nothing here is copied from real data: one made-up
block (two crossing streets) and a few made-up water lines near the default view.

## Run a spec on them

```bash
cd app
TILES_DIR=$(node scripts/tiles-fixture.mjs --ground painted) npm run test:e2e -- --grep @water   # @water once #19 lands
```

`tiles-fixture.mjs` writes a work folder (`data/dev/<package>/tiles-fixture/<ground>/` in the main checkout (`local` outside the workflow), git-ignored) with
symlinks to every file in the harness's `TILES_DIR`, the fixture files, and a `manifest.json` that is the real one
plus the fixture's `landscape` and `ground` entries. `--ground` is `painted` (the default), `flat` (an entry with a
reason) or `none` (the real manifest's ground entry stays). Run it again after changing a file here.

To write only the files: `python3 -m basemap.landscape.fixture --out DIR [--ground painted|flat|none]`.

## What it writes

- `landscape-<digest>.pmtiles`: gzipped vector tiles (extent 4096), one source-layer per file below, from the layer's
  own zooms up to z16. The name follows the bake's rule, so `plan.check_entry` passes on the entry (the test runs it).
  Roads are `internal`, so the entry says `access: tailnet`, as the real bake's does.
- `ground-<digest>.pmtiles` and `ground-detail-<digest>.pmtiles`: 512 px lossless WebP tiles. The Valley tone
  `#EEE7DA` with a second tone `#E8E0D0` in a checker (by `x + y`), z8-12 over the default view and z13-15 over
  downtown; the detail file holds the downtown box's z17 tiles in a third tone. The tiles are three base64 constants
  in `fixture.py` (how they were made is in its comment), so the script needs no image library.
- `fixture-entries.json`: the two entries.

| File | Geometry | Zooms | What |
|---|---|---|---|
| `water.reaches` | LineString | 8-16, per feature from `minzoom` | a main canal (z10) and a lateral (z12), a ditch and a piped lateral (z13), an NHD-only line (id above 2^51) and an intermittent one |
| `water.bodies` | Polygon | 8-16 | a pond (z11) |
| `roads.lines` | LineString | 14-16, alleys and service ways from 15 | two streets, a service way and an alley |
| `roads.surfaces_z15`, `roads.surfaces` | MultiPolygon | 15 and 16 | carriageways, a junction, an island and a median |
| `roads.edges`, `roads.markings` | MultiLineString | 16 | curbs, a shoulder; edge, lane, centre, stop-bar and bike lines |
| `roads.crosswalks` | MultiPolygon | 16 | two crossings |
| `roads.arrows` | Point | 16 | three turn arrows |

## Add a layer

Add `<plugin>.<layer>.geojson` here (the source-layer's name). It is a GeoJSON FeatureCollection in EPSG:4326 with a
`tvt` member:

```json
{"type": "FeatureCollection",
 "tvt": {"geometry": "LineString", "fields": {"id": "int", "kind": "string", "minzoom": "int"},
         "minzoom": 8, "maxzoom": 16, "licence": "ODbL-1.0", "republish": "yes", "credit": ["© OpenStreetMap contributors"]},
 "features": [{"type": "Feature", "properties": {"id": 1, "kind": "x", "minzoom": 13}, "geometry": {...}}]}
```

- Every feature has a unique integer `id` (0 to 2^53 - 1) and the export's fields (see the plugin's README, "The
  export"). Field types are the export's: `int`, `double`, `string`, `bool`.
- An integer `minzoom` field is the feature's first zoom, left out of the tiles, as in the real bake.
- Keep it small and made up, near the block (about -116.200, 43.615) or the default view, and keep every layer's
  republish and credits honest to its real source: the entry's `republish` is the strictest of them.
- Add a test line in `tests/test_fixture.py` for what the new spec relies on, then run
  `python3 -m unittest basemap.landscape.tests.test_fixture`.
