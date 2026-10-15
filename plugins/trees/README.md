# trees

Every tree we can find in the lidar, catalogued trees first ([docs/19](../../docs/19-trees.md)), and the shrubs
([§19.8](../../docs/19-trees.md#198-shrubs)).

- `model/crown_model.json`: how wide a crown is for its height and type, and the shape of its top, fitted on the 137 lone
  trees the owner kept on Oct 8, 2026. `model/utd_boise.json`: height and crown width from trunk diameter for 16 genera,
  fitted here on the Boise trees in the US Forest Service's Urban Tree Database (McPherson, van Doorn & Peper 2016,
  RDS-2016-0005; "can be used without additional permissions or fees", with that citation).
- `build/place.py`: the crown placer. `build/build.py`: builds one area in the worker image (NumPy, SciPy, rasterio):
  catalogued trees first (from a catalogue's trunk points, when given), then the placer, then a repair pass. A placed
  tree is narrow by the narrow rule, not by the width curve that sized it: its crown falls 45-95% of its height within
  3 m of an even top that is its own (under 2 m above its height) and 8.3 m or higher (docs/19 §19.3). Otherwise it is
  a conifer when the spring cue sees an evergreen crown: with `--spring` and `--summer` (the early-April and July 2025
  Sentinel-2 NDVI on the ground's 10 m grid), a crown of 50 m² or more whose April NDVI is 0.2 or more where at least
  half the April views around it were snow. In the valley the April lawns are as green as an evergreen at 10 m, so the
  cue only tells in the mountains, and it types trees only in areas where its calls were checked against the owner's
  labels (`SPRING_CHECKED_AREAS`: Bogus Basin, `h`, so far); elsewhere it is kept in the fit but types nothing. Otherwise
  it is broadleaf, or conifer where the conifer curve sized it
  (`KEEP_WIDTH_CONIFER`, pending the owner). The fit keeps the curve, the crown's profile and its spring cue. It writes
  `trees.geojson`, `log.jsonl` and `build.json` (with the Sentinel-2 files' sha256 and the sources it read) to a build
  folder.
- `python3 -m ingest trees-load --build DIR` loads a build: the area's trees are replaced, its log events added.
- Tables: `trees.build`, `trees.tree`, `trees.tree_log` (migrations/0001_trees.sql).
- Sources (`plugin.json`, each a manual source with a module stating its licence and credit, in `ingest/sources/`):
  the USGS 3DEP lidar (public domain), Sentinel-2 (Copernicus: "Contains modified Copernicus Sentinel data 2025"), USDA
  NAIP (public domain; the shrubs' near-infrared) and OpenStreetMap's hedges (ODbL; the shrubs' hedge check, docs/19
  §19.8). The build never reads a catalogue unless
  `--anchors` names one.

The settings were calibrated on the North End's city street trees on Oct 8 (overlap limit 0.2: 76% of 941 street trees
found within 3 m, the fewest extra trees, and a closer rebuild of the lidar than any height-only rule).

## Shrubs

Woody plants 0.3-2.4 m tall, one row each: a centre, height, width and look, **bush** (green in the summer photo) or
**sage** (not green: a plant by its lidar scatter). The rule, the cleaning and the width curves are docs/19 §19.8's,
from the land-cover spike's experiments on the ten test areas (Oct 8).

- `model/shrub_model.json`: width for height, bush 1.478 x H^0.247 and sage 1.279 x H^0.154 (m), with their spread.
- `build/shrubs.py`: the rule and what follows it, on arrays (NumPy, SciPy): shrub cells, the area's own green cut,
  crops, the cleaning (speck, skirt, gap), the split into shrubs and the score. `build/cloud.py`: the point cloud's
  cues per 0.5 m cell (returns above the ground, and their scatter by PDAL's covariance features), chunk by chunk.
- `build/build_shrubs.py`: builds one area in the worker image, a heavy job (`--memory 6g`, a day window). It reads the
  area's lidar products (the trees build's DSM, DTM and building mask), its point cloud (LAS/LAZ tiles or an EPT), the
  summer photo (NAIP) and crop fields, and writes `shrubs.geojson`, `build.json` and `why.tif` (why each shrub-height
  cell is or isn't a shrub) to a build folder. Its `--help` lists the inputs.
  - **The photo** is moved onto the lidar by a shift measured on the area (where its green best meets the lidar's
    trees, kept only when it gains 0.004 of overlap over none for each metre moved: a shift has to earn its
    distance), and read in the lidar's frame: NAIP's NAD83 and the lidar's NAD83(2011) differ by well under a metre
    here, which the shift takes up, and doing it properly needs grids PROJ would fetch. Only NAD83's realisations and WGS 84 are read that way; a source
    on another datum (NAD27, say) stops the build. So does a photo that gives an NDVI on less than 95% of the lidar's
    cells (`params.photo_cover`).
  - **Crops** come from farm's crop cover (decision 15, Oct 8: its export's `crop_cover.tif`, band 1 the crop group,
    which must cover the whole area; `--crop` also takes a vector of crop fields). A watershed piece with half its
    cells or more in it is a crop, and so is one mostly within 10 m of it (the cover's own cells) when its clump is
    mostly crop: a field's fringe that the 10 m cells leave out. So the cut follows the field's edge: a small field
    touching shrubland goes, and a hedgerow touching a field keeps all but its first 10 m. The spike's own crop-field rule runs as a
    check: `crop_check` in `build.json` says how its fields and farm's agree, and `rule_shrubs` how many shrubs stand
    in its fields.
  - **Licence** (plan C3): the build takes each input's licence class, republish and credit (the lidar and NAIP from
    this plugin's sources, the crop cover from its export manifest, which it reads and checks: sizes, sha256,
    licences), and records the strictest in `build.json` (`license`, `republish`, `credit`) with every input's files,
    sizes and sha256 (`inputs`; the crop cover's export build too). An input that may not be republished stops the
    build before any work; a crop file without a manifest needs `--crop-licence`, `--crop-republish` and
    `--crop-credit`.
  - **Overlapping areas**: `--skip-rect` leaves another area's part out (downtown's box overlaps the North End's).
  - A stopped build picks up where it was: the point cloud's finished chunks are kept in the build folder's `work/`,
    tied to the point files, the grid, the settings and the bare earth's values (a rebuilt DTM isn't met with them).
- `python3 -m ingest shrubs-load --build DIR` loads a build: the area's shrubs are replaced, the build recorded.
- `python3 -m ingest shrubs-hedge-check [--hedges FILE | --extract PBF] [--json OUT]`: are OpenStreetMap's hedges
  rows of bushes? A report only (plan C14): hedges are a check, never a source of shrubs, and nothing is written.
  Hedges come from `fences.fence` once the fences plugin is built (rows of type `hedge`, by the approved osm-landscape
  design's `fence_id`, `type`, `geom` and `active`; a table without the first three stops the check and says so);
  until then from a GeoJSON file or the held extract (filtered with osmium). The report is OSM-derived: keep it in the
  archive.
- Tables (migrations/0002_shrubs.sql): `trees.shrub` (one row per shrub: `shrub_id`, `area`, `look`, `geom` (the
  centre, WGS84), `ground_m`, `height_m`, `width_m` (crown diameter), `lidar`, `fit`, `build_id`), `trees.shrub_build`
  (each build: its outline `geom`, `inputs`, `license`, `republish`, `credit`, `params` and `counts`) and the view
  `trees.shrub_area` (each area's current build, outline, shrub count, licence, republish and credit: where shrubs are
  built, and the credit to show with them).
- **Rolling back migration 0002** (it adds to the trees schema, so dropping the schema isn't the way): in one
  transaction, `drop view trees.shrub_area; drop table trees.shrub; drop table trees.shrub_build; delete from
  ops.schema_migration where name = 'trees/0002_shrubs.sql';`. The trees (`trees.build`, `trees.tree`,
  `trees.tree_log`) stay as they were.

Licence: our own data, from public inputs only (USGS 3DEP lidar, USDA NAIP, and farm's crop cover: USDA NASS CSB and
CDL, public domain, and Sentinel-2, Copernicus): licence Copernicus, republish yes, credited to the U.S. Geological
Survey's 3D Elevation Program and USDA NAIP plus the crop cover's credits (each build's `credit`, in
`trees.shrub_build` and `trees.shrub_area`). Nothing here reads a tree catalogue.

## Tests

`python3 -m unittest plugins.trees.tests.test_load plugins.trees.tests.test_shrubs_load plugins.trees.tests.test_hedge_check`
(standard library; with `TVT_TEST_DATABASE_URL` naming a PostGIS database, the loading and the hedge check run too,
inside a transaction that is rolled back). The placer's, the narrow rule's, the spring cue's and the shrubs' tests need
the worker image (NumPy, SciPy, rasterio, pyproj, PDAL, GDAL), where a skip counts as a failure. On the VM:
`worker-test -C <checkout> plugins.trees.tests.test_place plugins.trees.tests.test_narrow plugins.trees.tests.test_spring
plugins.trees.tests.test_shrubs plugins.trees.tests.test_cloud plugins.trees.tests.test_build_shrubs`.
