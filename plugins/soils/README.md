# soils

The NRCS soil survey (SSURGO) for the map box: the soil card for gardeners and farmers, the Soils layer, and the base
of the ground's styling, where each soil type gets its own colour and texture measured from the aerial photo
([DECISIONS](../../docs/DECISIONS.md), Oct 8). A public plugin with no dependencies: the ground, farm and the coming
gardening plugin read it.

**Source.** SSURGO's FY2027 refresh, ten survey areas: ID001 Ada, ID665 Canyon, ID659 Payette, ID660 Gem, ID675
Owyhee, ID683 Boise County (west), ID685 Elmore, and Malheur's OR641, OR644 and OR645. Their boundaries cover the
whole box with no gaps, but not all of it is surveyed: 4,250 ha (0.5%) in OR645 is NRCS's NOTCOM, "No Digital Data
Available", loaded as not surveyed (misc `nodata`, below). Public domain ("Access_Constraints: None"). NRCS asks for
credit and says the data isn't for regulatory decisions, so the card says "Mapped soil, not a site test; not for
regulatory decisions".

- **Credit:** "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)". **Republish:** yes.
- **Refresh:** by hand each October after NRCS's yearly refresh, with the owner's OK for each download. Only survey
  areas whose version date (`saverest`) changed are reloaded. There's no collector and no schedule.

## Loading

The downloads are Web Soil Survey packages, unzipped into `$TVT_SOURCES/ssurgo/data/<AREA>/` (spatial and tabular;
the interpretations, `cinterp.txt`, were deleted as unused). Two steps, the trees pattern: the worker turns files into
files, and ingest stays standard library. A third writes the ground's export.

```bash
# 1. In the worker image (GDAL), about 0.5 GB of memory and half a minute: polygons touching the box (whole), the
#    survey areas' boundaries and those map units' rows
python plugins/soils/build/prepare.py --sources $TVT_SOURCES/ssurgo/data --out $TVT_ARCHIVE/soils/prepared/<stamp>
# 2. In the ingest image (standard library and psycopg), one transaction, about a minute and a half
python3 -m ingest soils-load --from $TVT_ARCHIVE/soils/prepared/<stamp>
python3 -m ingest soils-load --from DIR --areas ID001,ID665 --force    # reload some areas anyway
python3 -m ingest soils-load --from DIR --dry-run                      # check and derive only
# 3. The ground's export, a few seconds: $TVT_ARCHIVE/soils/export/<build>/
python3 -m ingest soils-export
```

On the scratch database (deploy/scratch): `scratch-run.sh <worktree> <name> worker python
plugins/soils/build/prepare.py --sources /srv/sources/ssurgo/data --out /srv/archive/soils/prepared/<stamp>`, then
`... ingest soils-load --from /srv/archive/soils/prepared/<stamp>` and `... ingest soils-export`.

**The prepared folder** (`ingest/package.py`):

| File | What |
|---|---|
| `polygons.geojsonl` | one GeoJSON Feature per line, WGS 84 (7 decimals, about 1 cm): `{id, areasymbol, fid, mukey, musym}`, `id` = `<AREA>:<shapefile fid>` |
| `survey_areas.geojsonl` | each survey area's boundary (`soilsa_a`), whole, one Feature per piece: `{areasymbol, fid}` |
| `tabular/<table>.csv` | every column of `mapunit`, `muaggatt`, `component`, `corestrictions`, `cosurffrags`, `copmgrp`, `copm`, `cogeomordesc`, `coecoclass`, `cocropyld`, `chorizon`, `chtexturegrp`, `chtexture` and `chtexturemod`, for those map units only, with a header row (`areasymbol`, then SSURGO's column names) |
| `prepare.json` | the format (`tvt-soils-prepared/2`; 1 had no boundaries), the box, each survey area (name, `saverest`, version, scale, Web Soil Survey URL, counts), each file's sha256 and rows, each input file's sha256. Written last |

`soils-load` checks every file against its sha256 and refuses a package for another box. For each area to load it
replaces the area's rows (its boundary, map units, components, horizons, polygons), then works out in PostGIS:
- each polygon's area on the ellipsoid and its area inside the box, `geom_lo` (simplified by 5 m in UTM 11N) and
  `label_pt` (the centre of the largest circle inside it). Invalid polygons are made valid and counted;
- each map unit's geometry for the valley zooms, its polygons simplified and joined into one MultiPolygon: `geom_z8`
  (100 m) and `geom_z10` (25 m). Parts that collapse at that tolerance, under a pixel there, are dropped;
- the boundary's copy simplified by 20 m;
- each ground type's map units, area in the box, surface fragment cover and dry albedo. A new ground type gets the
  next integer key (`gid`); a type already there keeps its own.

It records the run in `soils.build` (inputs' sha256, counts, licence), logs it in `ops.fetch` (source `ssurgo`), and
gives the Soils layer's tiles a new version (`core.layer_version`, layer `soils.units`) in the same transaction as the
data. The load state lives in the database (`soils.survey_area.saverest`), so it follows the database.

**Zoom bands for the Soils layer's tiles**, measured on scratch Oct 11 (raw MVT, warm, the busiest tiles over Nampa
and Boise; plan §3.5 has the survey bounds and the wash on demand at z8–11, outlines from z12):

| Zooms | Geometry | Tile |
|---|---|---|
| z8–9 | `soils.map_unit.geom_z8` | 319 KB for the whole valley at z8 (852 map units); 151–163 KB at z9 |
| z10–11 | `soils.map_unit.geom_z10` | 21–167 KB at z10; 31–69 KB at z11 |
| z12–13 | `soils.polygon.geom_lo` | 23–44 KB at z12 |
| z14 on | `soils.polygon.geom` | |
| z8–11 survey bounds | `soils.survey_area.geom_lo` | 2–12 KB |

At z8 the 5 m polygons were 1.6 MB (15,315 features), and 445 KB at z10 over Nampa.

## Tables

Migration `0001_soils.sql`, schema `soils`. Only map units touching the box are kept; polygons stay whole, not clipped.

| Table | Rows (box) | What |
|---|---|---|
| `soils.survey_area` | 10 | symbol, name, `saverest`, version, scale, the package URL, the load that put it there; its boundary `geom` (whole) and `geom_lo` (20 m) |
| `soils.map_unit` | 1,038 | NRCS's map-unit fields and summary (`muaggatt`), and ours: the dominant component, the ground type, the shallowest restriction, the show-by codes, the area in the box, the polygon count, and `geom_z8` and `geom_z10` for the valley zooms |
| `soils.component` | 1,894 | every component of those map units: share, slope, drainage, hydrologic group, capability, taxonomy, landform, parent material, frost-free days, ecological site, restrictions and crop yields (JSON) |
| `soils.horizon` | 8,007 | depths, texture (with its modifier), sand, silt, clay, organic matter, pH, CaCO₃, gypsum, EC, SAR, AWC, Ksat, K factor, fragments |
| `soils.polygon` | 21,999 | `gid` (an integer key, new when its area is reloaded), `geom` (MultiPolygon, 4326), `geom_lo`, `label_pt`, `area_m2`, `area_in_box_m2` |
| `soils.ground_type` | 380 | the ground's soil types (below) |
| `soils.build` | per run | each load or photo run: inputs, settings, counts, licence, republish, credit |
| `soils.photo_stats`, view `soils.ground_colour` | about 2,000 per photo build | each map unit's and ground type's measured colour, spread and texture, per flight day and pooled ([below](#the-photo-statistics)); the view below |

**The dominant component** has the largest share; ties go to a major component, then the lowest key. Its **surface
horizon** is the topmost mineral one (O horizons skipped).

**Ground types** (`soils.ground_type`): the dominant component's name plus its surface texture with modifier, as one
key, e.g. `purdam:silt-loam` or `chilcott:gravelly-silt-loam`. 380 in the box: 364 soils (167 of them in Ada and
Canyon; the median covers 589 ha) and 16 miscellaneous areas. Per map unit the same soil splits by slope phase and
survey area, which would make colour seams at county lines; texture class alone (about 12) is too coarse.
- **Miscellaneous areas** are one type by name alone, whatever texture NRCS gives them: `water`, `urban-land`,
  `rock-outcrop`, `badland`, `pits`, `rubble-land`, `riverwash`. `misc` says which kind: `water`, `urban`, `rock`,
  `badland`, `rubble`, `pits` (Pits, Pits and Dumps), `other` (Marsh, Riverwash, Playas, Dune land, Dumps, ...).
  Water units yield to the water layer in the ground, and rock gets a rock look. Tell them apart by `misc`, never by
  the key's shape: a soil with no surface texture has no colon either (`xeric-torriorthents`).
- **`nodata`** is NRCS's NOTCOM, "No Digital Data Available" (`notcom`, one map unit in OR645): no survey at all. Its
  codes are all null; the ground paints it from the photo or flat, and the card says it isn't surveyed.
- **`gid`** is the type's integer key (1 and up; 0 means none), for files and rasters: the ground export's
  `ground_type`, and P2's palette. It's kept while the type exists and never reused, so a type dropped and found
  again gets a new one.
- `frag_cover_pct` (gravel and stones on the surface) and `albedo_dry` (the dominant components' dry albedo, P2's last
  fallback) are area-weighted over the type's map units that report them.

**The "Show by" codes** (`soils.map_unit.c_*`), for the layer's one-property wash: 0 is the palest step, and darker means
a shallower hardpan or bedrock, wetter, more water held, better farmland or more runoff. Null means not rated (a
miscellaneous area, or NRCS gives no value), drawn with no fill.

| Code | From | Steps |
|---|---|---|
| `c_restr` | the dominant component's shallowest hardpan (duripan, petrocalcic, cemented, ...) or bedrock (lithic, paralithic, densic) | 0 none within 150 cm, 1 at 100–150, 2 at 50–100, 3 at 25–50, 4 under 25 cm (NRCS's depth classes) |
| `pat` | that layer, when within 50 cm | `hardpan` (hatched), `bedrock` (stippled), `none` |
| `c_drain` | `drclassdcd` | 0 excessively, 1 well, 2 moderately well, 3 somewhat poorly, 4 poorly or very poorly drained |
| `c_aws` | `aws0100wta`, cm in the top metre | 0 under 5, 1 5–10, 2 10–15, 3 15–20, 4 20 or more ⚠️ (the Soil Survey Manual's classes for 150 cm, scaled to 100 cm) |
| `c_farm`, `farm_cond` | `farmlndcl` | 0 not prime, 1 statewide, local or unique importance, 2 prime; the condition `irrigated`, `drained`, `reclaimed` (of salts and sodium), `protected` (from flooding) or `other`. Drained and reclaimed are hatched |
| `c_hsg`, `hsg_dual` | `hydgrpdcd` | A 0, B 1, C 2, D 3; a dual group (A/D, B/D, C/D) by its drained letter, hatched because it's D where undrained |

`restr_kind`, `restr_top_cm` and `restr_hard` are the dominant component's shallowest restriction of any kind (an
abrupt textural change or a natric horizon counts there, not in `c_restr`); every restriction is in
`soils.component.restrictions`.

**`soils.mapunit_shares(g geometry)`**: the map units in a shape (EPSG:4326; another SRID is transformed, none is
taken as 4326) with their ground type and its `misc`, their area on the ellipsoid and their share of the shape's area,
largest first. For the farm field card and later the gardening bed card: "62% Purdam silt loam, 38% Power silt
loam". An invalid shape (a bow-tie field, a bed drawn crossing itself) is made valid first, and a unit the shape only
touches along an edge isn't in it. A point gets the unit it falls in, with share 1.

**`soils.ground_colour`** (for P2 and the card): each ground type's pooled colour from the newest finished photo build
that has the type. A photo build may hold only some types, such as a rerun for the map units a reload changed: it
supersedes older builds for the types it holds, whichever photo or mask, and the others keep their older rows. Within
one build, NAIP 2025 comes before the 2023 tiles and the class mask before the photo mask. Types no longer in
`soils.ground_type` drop out.

## The ground's export

`python3 -m ingest soils-export` writes `$TVT_ARCHIVE/soils/export/<build>/` through the ground's export contract
([basemap/ground](../../basemap/ground/README.md)), with `manifest.json` last, from one snapshot of the database:

| Layer | File | What |
|---|---|---|
| `ground` | `ground.fgb` (EPSG:32611) | every polygon, whole: `id` (`soils.polygon.gid`), `ground_type` (`soils.ground_type.gid`; 0 for none), `mukey`, `misc` (in that order). 21,999 features, 46 MB |
| `ground_types` | `ground_types.json` (`soils.ground_types/1`) | each ground type by its `gid`: its key, series, texture, `misc`, `landform`, fragment cover, dry albedo, map units and area |
| `palette` | `palette.json` (`soils.palette/1`) | once a photo build is loaded: each ground type's measured colour, spread and texture ([below](#the-palette)) |

The ground reads `soils/ground` (without it the ground stays flat) and rasterises `ground_type`, and reads
`soils/palette` for the colours (without it, flat colours per type, labelled). Take the palette and the ground from one
export: both are keyed by the same `gid`. The ground layers are public domain, republish yes, credit "Soils: USDA
NRCS, Soil Survey Geographic Database (SSURGO)"; the palette is ODbL-1.0 (it was measured through mask v0, made from
OpenStreetMap and Overture), republish yes, with every input's credit (NAIP, SSURGO, OSM, Overture, NHD, CDL, CSB,
Copernicus). None is a base layer. The command checks the export against the ground's rules (`inputs.resolve`)
before it leaves it in place.

- **`misc` comes last in `ground.fgb`.** PostGIS's `ST_AsFlatGeobuf` (3.6.4 on the VM) writes the column after a null
  under the null's index, a running count rather than the column's own. With `misc` (null for every soil) before
  `mukey`, the first export read back `misc` = the map unit's key and `mukey` = null for 20,835 of the 21,999
  polygons (found Oct 11 by P2, and fixed by putting `misc` last; `test_photo_load` decodes the file's bytes to check
  it). Any export through `ST_AsFlatGeobuf` with a nullable column before another has the same fault.
- **`landform`**: the landform of the type's map units' dominant components, the one covering most of the box. P2's
  texture fallback matches types by texture class and landform.

## The photo statistics

Each ground type's colour, spread and texture, measured from NAIP 2025 over its uncovered ground (plan P2; the soils
design, build step 3). They give the ground its soil colours and the card its "bare ground in July" swatch.

```bash
# 1. The decode pass, in the worker image with the MrSID SDK mounted (heavy: 3 GB, 3 CPUs, no network; resumable
#    by window, so a chunk at a time is fine: --limit N)
python plugins/soils/build/photo_stats.py run --out $TVT_ARCHIVE/soils/photo/photo-<UTC stamp> --cog <a cold-drive folder> \
    --naip ada=.../ortho_1-1_hm_s_id001_2025_1.sid --naip canyon=.../ortho_1-1_hm_s_id027_2025_1.sid --dsdk /dsdk
# 2. The ten-box calibration (light: 1 GB, under a minute), into the same folder
python plugins/soils/build/photo_stats.py calibrate --out <the build> --naip ada=... --naip canyon=...
# 3. Pool, check and assemble the 2 m COG (stats.json, report.json; the COG beside its parts)
python plugins/soils/build/photo_stats.py finish --out <the build>
# 4. Load and export (ingest image)
python3 -m ingest soils-photo-load --build $TVT_ARCHIVE/soils/photo/<build>
python3 -m ingest soils-export
```

The pass reads the newest soils export, mask v0 and farm export in `$TVT_ARCHIVE` (or `--soils`, `--mask`,
`--farm`), the July 2025 Sentinel-2 median, the same-day normalisation and the colour gains (`--july`, `--norm`,
`--gains`; `$TVT_SOURCES`), and the two county mosaics, each window decoded at 0.6 m (`mrsiddecode -s 1`) into the
container's tmpfs and deleted. `calibrate` in a build folder uses the run's own inputs and rules (`run.json`), refuses a
flag that says otherwise (a sweep goes in a folder of its own), and records them in `calibration.json`; `finish`
takes a calibration only when they match.

**One mosaic per place.** The county mosaics reach a few kilometres past their county lines: Ada's mask covers about
3,630 km² (the county 2,747), Canyon's 2,143, and they overlap by about 390 km² along the county line. Each pixel is
served by one of them: inside a county's survey area (the export's `areasymbol`: ID001 is Ada County, ID665 Canyon)
by that county's mosaic, and elsewhere by the nearest county's (a 20 m grid of the nearest county, `owner_grid`); the
other mosaic serves it only where the first doesn't cover it. So nothing is counted twice, and in the COG the two
mosaics' balancing meets at the county line, where G1b's seam handling looks for it.

**Colour on one flight day's scale** (`--gains`, `photo.Gains`). NAIP 2025 was flown on four days in Ada and Canyon,
and the first build's flight-day check fired (median 3.15 against the design's 3), so the conditional Sentinel-2 read
the owner approved (decision 22) was made: Sentinel-2 L2A blue, green and red on each flight day (the same scenes as
the NDVI curves; 63 range reads, 389 MB, nothing kept but the fits). Per day and band a monotone curve takes NAIP's DN
(10 m means of the 2 m COG) to same-day reflectance, and each day's table puts its DNs on the June 18 flight's scale
(June 18 is 63% of the photo): the reference curve inverted at that day's reflectance. The pass applies the table
before anything else reads the colour, so the statistics, the dark rule and the COG's colour bands are all on June
18's scale; the NDVI keeps its own curves. The fit, its checks and the scripts are with the server's sources
(`sentinel2/naip_colour/`: `gains.json`, `PROVENANCE.md`), as naip_norm's are.
LizardTech's SDK is for internal use only: it's mounted read-only at run time and never committed, as in
[basemap](../../basemap/README.md#county-wide-detail-from-the-naip-county-mosaics-oct-7).

**Uncovered ground, `photo-v1`** (`build/photo.py`). A 0.6 m pixel is sampled when it is
- inside a soil polygon and at least 10 m from its edge (SSURGO's lines are about ±12 m; slivers give nothing);
- outside mask v0's `covered`: roofs + 1 m, roads + 2 m beyond half their width, paving + 2 m, water + 5 m
  (intermittent too), rail yards, aeroways and CDL 2025's developed land (classes 123-124);
- not green: the photo's NDVI, put on Sentinel-2's scale by its flight day's curve (naip_norm's "band 4"), under
  **0.45** (the land-cover spike's one green cut), and the July 2025 Sentinel-2 median under **0.30**;
- not shadow or asphalt: not dark (OKLab L under **0.50**) and neutral (chroma under 0.025) or blue-shifted (b under
  0) ⚠️. The ten-box calibration chose these cuts: raising L to 0.6-0.7 made every box worse (the class mask's soils
  are darker than the photo mask's), and in this bright photo they only bite in the mountain boxes' shade;
- inside crop fields, only row crops and fallow: farm's `crop_cover` group none, corn, roots or fallow, and the
  pixel's CSB field (farm's `fields.fgb`) isn't hay, small grains, specialty or pasture. Stubble isn't soil.

**What's kept**, per (map unit, flight day) and summed over the windows (`photo.Accumulator`): the pixel count, the
OKLab sums and cross-products (the mean and covariance), 256-bin histograms of L, a and b (the median and L's 10th and
90th percentiles), and the texture energy of L and chroma in five octaves, 1.2-19.2 m: the mean square of the masked
difference of Gaussians S(s/2) − S(s), where S is the Gaussian blur of the uncovered pixels only, counted where 75% of
the blur's support is uncovered (`photo.octave_energy` measures any array the same way, for G1b's noise). Per soil
polygon: the count, sums and histograms, for the outlier check.

**Pooling** (`build/pool.py`). A ground type is its map units summed. It's **measured** with at least 20,000 pixels
(0.72 ha) in at least 3 polygons that each gave 500. Otherwise it borrows, in order:
1. `series`: every type of its series, any texture;
2. `texture`: every soil type with its texture class and landform;
3. `albedo`: L from a straight fit of the measured types' L on their dry albedo, chroma, hue, spread and texture from
   its texture class's measured types (or every measured soil). Only when the fit has some skill (r of 0.5 or more):
   otherwise the type takes those peers' colour as it is, L included, labelled `texture` with a note that says so.
   The first build's fit had r 0.28, which put every such type at L 0.75-0.80, the mean.

A miscellaneous area borrows nothing (water, urban land, rock outcrop and the like have no series, texture or albedo
of their own), and NOTCOM isn't a soil. A type with nothing to borrow gets no row: the palette says `none` and the
ground paints it flat. **Beyond the mosaics** there's no NAIP 2025. The county mosaics reach a few kilometres past
Ada and Canyon (into Owyhee, Elmore, Boise, Gem and Payette counties and a strip of Malheur, Oregon: about a fifth of
the sampled pixels), so a type there is measured from what those strips hold, and borrows only where it has too
little. The line between measured and flat colours follows the mosaics' edges, not the county lines. A type found
only beyond them is a flat type colour, labelled by its fallback; the 2023 tiles' colour fit is cut (plan §0's
cut-first list).

**Checks** (`report.json`, and the build's counts):
- the same type on different flight days: per-flight colour gains are needed when the median type's largest dE
  between days is over 3 (the design's rule). With the gains applied, `flight_days` reports what's left
  (`gains_applied`, `over_rule`), mostly each type's spread over the valley, and `pair_offsets` the flights' own
  offsets (per pair of days, the median paired difference over the types on both);
- the share of colour variance the types explain; Spearman's rho of type L against dry albedo;
- polygons whose median lies more than 3 (Mahalanobis, in the type's own spread) from their type, with 2,000 pixels
  or more: a list for review;
- the ten-box calibration (`calibration.json`): in each box's 500 m class window (the spike's "as of July" classes,
  shifted onto the photo by the spike's NAIP-to-lidar offsets), each type's photo-v1 median against its median under
  the class mask (short dry grass, flat not green, pale surfaced). It passes at a median dE of 3 or less over the
  (box, type) pairs with 2,000 pixels under both. Boxes h, i and j have no NAIP 2025; they're measured on their NAIP
  2023 crops with the 2023 curve.

**The 2 m NAIP COG** for G1b (`finish`, beside its parts on the cold drive): `naip2025_2m.tif`, 4 bands, uint8, on the
ground's 2 m grid, the extent of Ada and Canyon, DEFLATE, 512 px tiles, with an internal mask (cells at least half
covered by a county mosaic). Bands 1-3 are the area means of the 0.6 m red, green and blue on the June 18 flight's
scale (the colour gains); band 4, `ndvi`, is the photo's NDVI on Sentinel-2's scale by its flight day's curve, coded
1..255 for −1..+1 (`(code − 128) / 127`; 0 where no flight polygon covers it). Both are per-day normalised. Each cell
comes from its own county's mosaic (above). It's Copernicus-derived public-domain NAIP: the ground reads it as the raw
input `naip-2m` (basemap/ground/inputs.py), crediting both. `naip2025_2m.json` beside it says what it is (bands,
coding, grid, colour, sources, credits, sha256), and
`flights.fgb` holds USDA's seamline polygons with their days and local times, for the sun angle G1b normalises by
(C8).

### The first build (Oct 11, on the scratch database)

`photo-20261011T1600Z`, from soils export `20261011T153514Z`, mask v0 `20261011T144701Z` and farm export
`20261011T130710Z`:
- **The pass:** 5,159 windows (452 in both counties) in three chunks under `heavy`, 2.8 hours with three workers
  (about 1.9 s a window), 1.84 GB at most of its 3 GB. 7.0 billion pixels sampled, 45% of the valid pixels: the rest
  were green (28%), within 10 m of a polygon's edge (14%), covered (10.5%), crop stubble or hay (1.5%), outside the
  flight polygons (0.6%) or dark (0.3%).
- **Ground types:** 211 measured, 38 from their series, 72 from texture class and landform, 55 from dry albedo, and 4
  with no colour (Dams, Mined land, Pits and dumps, and NOTCOM). 2,572 rows, 1.5 MB in PostGIS. `finish` took
  5.5 minutes, 4 of them the COG.
- **The ten boxes:** 24 (box, type) pairs, median dE **1.36** (90th percentile 5.76): **pass**. By box: a 1.09, b 1.01,
  c 13.0, d 1.73, e 0.85, f 0.13, downtown 14.9, h 2.18, i 0.12, j 1.25. The two misses are urban land in town, where
  the class mask is mostly dry lawn and sidewalk, which isn't soil either, and photo-v1 keeps only vacant lots. The
  valley-wide palette colour against the class mask's in the boxes is 3.76 (spatial spread plus the mask's bias).
- **Flight days:** 91 types were measured on two days or more. The median type's largest dE between its days is
  **3.15**, just over the rule's 3, so `gains_needed` is true. Most of that is the type's spread over the valley, not
  the flight: per pair of days, the flights' own offset (the median paired difference over the types on both) is dE
  0.8 for June 18/July 24 (53 types), 2.2 for May 25/June 18 (53), 1.3 for May 25/July 24 (18), 2.0 for May 30/June 18
  (15) and 3.3 for May 25/May 30 (14; May 30 is 0.6% of the photo's area), almost all of it in L, with L's
  interquartile ranges crossing 0 for all but the May 30 pairs. Whether to make the approved Sentinel-2 read for
  per-flight gains is the lead's call (it would mean a second pass); the COG's colour isn't normalised.
- **The rest:** the types explain 15% of the pixels' colour variance; type L against dry albedo, Spearman's rho 0.27
  (199 types; the fit's slope 0.19); 136 of 14,371 polygons are listed as far from their type (water, pits and
  playas lead the list).
- **The COG:** 3.35 GB (its 2 m parts, 2.7 GB, are deleted once it's checked).

### The palette

`palette.json` (`soils.palette/1`), from `soils.ground_colour` and each type's own rows:

```json
{"schema": "soils.palette/1", "colour_space": "OKLab", "about": {"...": "what each field is"},
 "builds": [{"build": "photo-...", "finished": "...", "photo": "naip2025", "mask": "photo-v1", "octaves_m": [1.2, ...],
             "rules": {...}, "calibration": "pass", "flight_days": {...}}],
 "types": [{"gid": 12, "id": "colthorp:silt-loam", "status": "measured", "misc": null, "modifier": null,
            "frag_cover_pct": null, "build": "photo-...", "photo": "naip2025", "mask": "photo-v1",
            "flights": ["2025-06-18"], "n_px": 3430045, "n_polygons": 9, "lab_med": [0.804, 0.005, 0.039],
            "lab_cov": [...6], "l_p10": 0.71, "l_p90": 0.90, "oct_l": [...5], "oct_c": [...5]}]}
```

`status` is `measured`, `series`, `texture`, `albedo` (borrowed: a flat type colour, labelled) or `none` (no colour:
paint it flat and say so). Every type in `soils.ground_type` is listed. The numbers are as measured, never styled: the
ground's look is the ground's job. The colours are on the June 18 flight's scale when the build had the colour gains
(`builds[].flight_days.gains_applied`).

**Licence.** The palette was measured through mask v0 (OpenStreetMap, Overture), farm's crop cover and fields (CSB,
CDL, Sentinel-2) and Sentinel-2's July median, NDVI curves and colour gains. A photo build carries every input of
each export layer it reads, whole (`photo_stats.inputs_of`), so the palette's licence is the share-alike one,
ODbL-1.0, and it credits all of them; an input that may not be republished would make `soils-export` refuse it.
`soils.build` records the same licence for the build (`photo_load.licence_of`, the ground's export rule), and
plugin.json lists the photo statistics as a derived source, `naip_photo`. (Migration 0001's header still says
photo_stats adds only NAIP's licence; it's applied, so the comment is left for a later migration.)

**On production** (the deploy runbook): run the pass there, on production's soils export, mask v0 and farm export,
rather than copying a scratch build: a build names the exports it read (`stats.json` `soils_export`, its inputs'
notes, `soils.build.params`), and its polygon outliers use `soils.polygon` gids, which are new whenever an area is
reloaded. Then `soils-photo-load` as tvt_build, and `soils-export`.

## Still to come

- The layer, card, legend and APIs (P1-app): `/api/soils/tiles/units/{z}/{x}/{y}` (MVT layers `soils` from the zoom
  bands above, `soil_labels` from `label_pt`, the survey bounds), `/api/soils/at`, `/api/soils/mapunit/<mukey>`.
- When soils-load reloads an area, the photo statistics and the export after them go stale (M1's
  `ops.build_pending`, once it lands): a photo build for the changed map units, then soils-export.
- When the land-cover classes run valley-wide, the photo statistics become their by-product (mask `classes-v1`), with
  no second decode pass.

## Tests

- `python3 -m unittest plugins.soils.tests.test_package`: reading and deriving, on a synthetic survey
  (`tests/synthetic.py`; nothing in the repository is real SSURGO data).
- `TVT_TEST_DATABASE_URL=... python3 -m unittest plugins.soils.tests.test_load plugins.soils.tests.test_export
  plugins.soils.tests.test_photo_load`: the load, the derived geometry, `mapunit_shares()`, `ground_colour`, the
  photo-statistics load and the export with its palette in a test database (each test rolls back; exports go to a
  temporary archive).
- The worker's code needs the worker image: on the VM, `worker-test -C <checkout> plugins.soils.tests.test_prepare
  plugins.soils.tests.test_photo plugins.soils.tests.test_pool plugins.soils.tests.test_photo_stats` (a skip counts
  as a failure). `test_photo` and `test_pool` need only NumPy and SciPy; `test_photo_stats` runs the decode pass,
  calibration and finish end to end on a synthetic county (a 0.6 m GeoTIFF read as NAIP 2023's crops are; the SDK
  isn't in the image) with synthetic copies of every other input.
