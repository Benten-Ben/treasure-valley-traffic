# trees

Every tree we can find in the lidar ([docs/19](../../docs/19-trees.md)), and the shrubs
([§19.8](../../docs/19-trees.md#198-shrubs)).

- `model/crown_model.json`: how wide a crown is for its height and type, and the shape of its top, fitted on the 137 lone
  trees the owner kept on Oct 8, 2026. `model/utd_boise.json`: height and crown width from trunk diameter for 16 genera,
  fitted here on the Boise trees in the US Forest Service's Urban Tree Database (McPherson, van Doorn & Peper 2016,
  RDS-2016-0005; "can be used without additional permissions or fees", with that citation).
- `build/place.py`: the crown placer. `build/build.py`: builds one area in the worker image (NumPy, SciPy, rasterio):
  the placer, then a repair pass, from the lidar alone; then, when an inventory's trunk points are given, they are matched
  to the crowns found (see "Anchors" below). A placed
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
  folder: crowns found in the lidar, nothing from an inventory (see "Anchors" below).
- `python3 -m ingest trees-load --build DIR` loads a build: the area's trees are replaced, its log events added. It takes
  a fixed set of fields and refuses a build that carries any other (`ingest/load.py`).
- Tables: `trees.build`, `trees.tree`, `trees.tree_log` (migrations/0001_trees.sql; 0003 removed the inventory's rows
  and emptied its fields: `trees.tree.catalogue` and `catalogue_id` stay as columns, NULL, behind a check that refuses
  any value, until a later migration drops them).
- Sources (`plugin.json`, each a manual source with a module stating its licence and credit, in `ingest/sources/`):
  the USGS 3DEP lidar (public domain), Sentinel-2 (Copernicus: "Contains modified Copernicus Sentinel data 2025"), USDA
  NAIP (public domain; the shrubs' near-infrared) and OpenStreetMap's hedges (ODbL; the shrubs' hedge check, docs/19
  §19.8). The build never reads an inventory unless
  `--anchors` names one.

## Anchors: what an inventory may and may not leave here

The public tables hold only trees found in the lidar (owner, Oct 22, 2026). An inventory's tree ids, trunk points,
genus, trunk diameters, planting dates and the link from a tree to its entry belong to the private plugin that owns the
inventory, never here. The inventory is an input to the build, not a source of rows:

- `--anchors FILE` is a CSV of trunk points (`source, source_id, lon, lat, genus, trunk_in, installed_ms`; the private
  plugin writes it) and goes with `--private-out DIR`. **Anchors play no part in finding crowns.** The placer and the
  repair run on the lidar alone, as they would without anchors, and the build writes the public files. Only then is each
  anchor planted before the flight, with lidar 3 m or taller within 1.5 m of its trunk point and not under a taller
  tree, matched to the nearest crown already found within 2.5 m of that point (one anchor to a crown, the nearer
  winning). So `trees.geojson` and `log.jsonl` are byte for byte those of a build without `--anchors` (the same crowns,
  ids, fits, types, events and order), and `build.json` differs only in its times. A test builds one area with and
  without anchors and compares them, and with a conifer genus and a broadleaf one, and with two anchors under one
  crown. Nothing in a public row, its order or its id tells a crown that has an anchor from one that has none.
- **The side file `anchors.jsonl`** is written to `--private-out`, never to the build folder. The build stops before any
  work when that folder, with symlinks resolved, is inside the build folder or holds it, is under production's archive
  (`/srv/tvt/archive`) or under `$TVT_ARCHIVE` or `$TVT_PROD_ARCHIVE` when those are set, or is outside the private
  root (`/srv/tvt/private`, or the folder `--private-root` names): scratch jobs mount production's archive, so a file
  there is readable by them. The guard names those paths itself and does not depend on the container's environment.
  Use the project's private files on the server. It holds what is the inventory's: for each matched crown its
  public tree id, the anchor's source and id, and the trunk-to-crown offset; for each anchor with no such crown (planted
  after the flight, under a taller crown, under 3 m, or with no crown near it) the whole estimated tree, sized from its
  genus and trunk diameter (`model/utd_boise.json`, the US Forest Service's Urban Tree Database). Format and checks:
  `build/anchors.py`. The public loader never reads it; the private plugin loads it after `trees-load` for the same
  build (its README gives the command).
- `build.json` records nothing about anchors, and its counts hold no anchor counts. The loader's field list
  (`TREE_FIELDS`, `FIT_FIELDS`, `EVENTS`) is the fence: an old-format build, or one that let anything else in, is refused
  whole, and the table's check (`kind = 'placed'`) refuses any other kind whatever loads it.

A consequence: a tree the lidar doesn't show is not in `trees.tree`, so the public layer and tiles show neither it nor
which crowns have an inventory entry; the owner's site shows a matched crown's entry (the app looks it up through the
private plugin's match table, keyed by the crown's id).

### Runbook: migration 0003 on production

`0003_no_city_rows.sql` deletes the trees that came from an inventory (the old `catalogued` and `estimated` kinds and
any tree with an entry), their log events and the diameter and offset keys, and adds the kind check. It also removes
`counts.types` from the build records that held such trees (it was a split over all their trees, the inventory's genus
typing included), so a build row no longer gives the inventory's count; a rebuild records a fresh one. It keeps the columns `catalogue` and
`catalogue_id`, empty, with a check that each is NULL, so an app image built before this change (the live app is
pinned) still runs its queries and gets nothing City-derived; a later migration drops them once every app image is past
this change. It is **not reversible**, and the `ingest` service applies it on start, so it runs as soon as the release that carries it is
deployed. Nothing is backed up today ([DECISIONS](../../docs/DECISIONS.md)). So, in this order. Every long command runs
under `/srv/tvt/work/bin/heavy` ([deploy/README.md](../../deploy/README.md), "Heavy jobs"), with a deadline inside the
day window (06:00-23:15 Boise, never in the nightly roll-up's hours) and a runtime that fits it; `heavy` refuses a
command outside the window. Compose runs from `/srv/tvt/repo/deploy` without `-f`, except the production load, which names its files as
deploy/README.md does. The order below is the recommended one. If 0003 is applied before the area rebuilds are loaded
(an early deploy), the only effect is transient gaps where matched inventory trees were; the step-3 rebuilds and the
step-4 load close them.

0. **Ordering with the private plugin.** Its match tables and loader (the private branch for #277, rebased on the private
   repository's `main`) go onto the server first: merged, copied to the private plugins' folder (readable by the
   group), and its manifest checked (a bad private manifest crash-loops `ingest`). Until the private tables exist the
   owner's site shows no inventory entries; the public site never does.
1. **Pick the window** as for any `ingest` restart ([deploy/README.md](../../deploy/README.md), "Updating"), in the day
   window above. In the VM's shell the archive is `/srv/tvt/archive` (`$TVT_ARCHIVE` is set only inside containers,
   where the archive is `/srv/archive`; the commands below use these paths, never the variable). List the trees builds
   that exist now: they are the old format, and step 7 moves exactly these. Leave out `shrubs/`, which holds the shrub
   builds (no inventory data in them): `ls /srv/tvt/archive/trees | grep -vx shrubs > <private files>/trees-builds-before-0003.txt`.
2. **Back up the trees schema** (check the free space first, `df -h`), under `heavy` with the dump under `timeout` (the
   deadline cannot reach a command run inside the database's container):
   `/srv/tvt/work/bin/heavy --deadline HH:MM --runtime 20 --peak 1 "trees dump (0003)" sh -c 'docker exec tvt-db-1 timeout -k 60 $((HEAVY_DEADLINE_EPOCH - $(date +%s))) pg_dump -U tvt -Fc -n trees tvt' > <private files>/tvt-before-trees-0003-$(date +%F).dump`.
   Keep it in the private files, not the archive: it holds the old inventory-derived rows. It is the only way back
   (reloading a build made before this change is not one, because the loader now refuses its fields).
3. **Push `main`, then rebuild each affected area's public trees with the new `build.py` and no `--anchors`.** Push `main`
   to the server's repository first: the worker container mounts `/srv/tvt/repo`, which changes only on a push, and the
   old `build.py` writes fields the new loader refuses. The push restarts nothing and applies no migration (that is
   step 4's rebuild of `ingest`). The rebuild needs neither the private plugin nor the inventory: the public files are
   byte for byte those of a build with anchors. One heavy job per area, a name no old build has (`<new build name>`; the
   area's lidar products and the options its earlier build used: `build.py --help`):
   `/srv/tvt/work/bin/heavy --deadline HH:MM --runtime MIN --peak 6 "trees <area> (0003)" docker run --rm --memory 6g --memory-swap 6g --cpus 2 --network none --user 1000:1000 -e PYTHONDONTWRITEBYTECODE=1 -v /srv/tvt/repo:/repo:ro -v /srv/tvt/archive:/srv/archive -v <the area's inputs>:/in:ro -w /repo tvt-worker python plugins/trees/build/build.py --area <area> --dsm /in/... --dtm /in/... --out /srv/archive/trees/<new build name>`.
   Check that `trees.geojson` is in the folder before the deploy. Do it before the deploy so the public layer never
   shows gaps where the City's crowns were.
4. **Deploy and load straight after.** Rebuild the services that carry this release:
   `cd /srv/tvt/repo/deploy && docker compose up -d --build ingest app` (and `app-next` as well when
   `compose.preview.yml` is switched on). No app image has to be rebuilt for the migration's sake: 0003 keeps the City
   columns, empty, so the pinned live app (`tvt-app:live`) keeps working. Check that the migration ran:
   `docker compose logs ingest | grep -F 'applied  trees/0003'` prints `applied  trees/0003_no_city_rows.sql` (two
   spaces, as `db/migrate.py` writes it). Then at once, for each build from step 3, in the day window (the deadline and runtime from `heavy`'s rules):
   `cd /srv/tvt/repo/deploy && /srv/tvt/work/bin/heavy --deadline HH:MM --runtime 30 --peak 1 "trees load <area> (0003)" docker compose -f docker-compose.yml -f compose.private.yml -f compose.load.yml run --rm --no-deps -e DATABASE_URL ingest python3 -m ingest trees-load --build /srv/archive/trees/<new build name>`
   (`DATABASE_URL`, the load's role, comes from the shell). Until a build is loaded, that area's trees are the migration's
   leftovers: the old lidar-found rows, with gaps where the matched inventory trees were. Keep that window as short as
   the steps allow (load straight after the deploy).
   Then check both apps against a placed tree (take one with
   `docker compose exec -T db psql -U tvt tvt -Atc "select tree_id from trees.tree limit 1"`): the live app,
   `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/trees/<id>`, and, when the preview is on,
   `app-next`, `http://localhost:8081/api/trees/<id>`, each answer `200`, and the tree's card opens on the map (the
   preview's, when on). Any other answer from either: stop and ask the owner before changing anything.
5. **Private matching, after, separately** (it changes nothing public). Rebuild each area again under `heavy` as in
   step 3 with the same options plus `--anchors FILE --private-out <private files>/trees/<new build name>` (the private
   plugin writes the CSV; add `--private-root` only if the private files are not at `/srv/tvt/private`; mount them in
   the container), and `--out` a scratch folder **named exactly `<new build name>`**, e.g.
   `/srv/tvt/work/trees-match/<new build name>`: the rows record the folder's name as their build id
   (`build_id = basename(--out)`), which must be the id of the build loaded in step 4. The public files are the same as
   step 3's, so `trees-load` is not run again; delete the scratch folder when the private load is done. Then the private
   plugin's load for that build, as a heavy job like step 4's. Until it is done the owner's site shows no inventory
   entries.
6. **Way back** (before step 7, if something is wrong): `git checkout` the previous release on the server and rebuild
   `ingest` and `app`, then in one transaction `delete from ops.schema_migration where name = 'trees/0003_no_city_rows.sql'`
   and `pg_restore -c -n trees` the dump from step 2 (it recreates `trees` as it was, shrubs included).
7. **Old-format builds out of the archive** (after the loads are checked): the dump, not these folders, is the way back.
   Move the folders listed in step 1 (not `shrubs/`, not step 3's builds) to the private files, creating the target
   first (`mv` into a missing folder renames the first build to it), and check that nothing old-format is left under the
   archive: `mkdir -p <private files>/trees-old-builds && while read b; do mv "/srv/tvt/archive/trees/$b" <private files>/trees-old-builds/; done < <private files>/trees-builds-before-0003.txt`,
   then `grep -rlE '"(catalogue|catalogue_id|dbh_in|trunk_to_crown_m)"|"kind": ?"(catalogued|estimated)"|boise-' /srv/tvt/archive/trees; echo "grep exit $?"`
   prints nothing before `grep exit 1` (`0` means files are listed, `2` an error such as a missing folder: neither is
   a pass). Scratch jobs also see an empty `trees/` in production's archive (`deploy/scratch/run.sh`).
8. **After production is migrated**: refresh the scratch database so it holds none of the old rows, and remove the two
   dumps made before (the coordinator's step, under the scratch rules).

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
`trees.shrub_build` and `trees.shrub_area`). Nothing here reads a tree inventory.

## Tests

`python3 -m unittest plugins.trees.tests.test_load plugins.trees.tests.test_anchors plugins.trees.tests.test_shrubs_load plugins.trees.tests.test_hedge_check`
(standard library; with `TVT_TEST_DATABASE_URL` naming a PostGIS database, the loading and the hedge check run too,
inside a transaction that is rolled back; `test_load` proves the loader refuses the inventory's fields and that the
migrated table holds no value in those fields and takes no other kind; `MigrationCleanUpTest` runs 0003 over rows in the old
formats and checks what it deletes, strips and keeps, that the City fields are NULL and refuse a value, and that an
old-style query naming them still runs). `test_build_anchors` runs the build end to end with anchors
(worker image): the public files are those of a build without anchors, and the side file is in its own folder. The placer's, the narrow rule's, the spring cue's and the shrubs' tests need
the worker image (NumPy, SciPy, rasterio, pyproj, PDAL, GDAL), where a skip counts as a failure. On the VM:
`worker-test -C <checkout> plugins.trees.tests.test_place plugins.trees.tests.test_narrow plugins.trees.tests.test_spring
plugins.trees.tests.test_shrubs plugins.trees.tests.test_cloud plugins.trees.tests.test_build_shrubs plugins.trees.tests.test_build_anchors`.
