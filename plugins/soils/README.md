# soils

The NRCS soil survey (SSURGO) for the map box: the soil card for gardeners and farmers, the Soils layer, and the base
of the ground's styling, where each soil type gets its own colour and texture measured from the aerial photo
([DECISIONS](../../docs/DECISIONS.md), Oct 8). A public plugin with no dependencies: the ground, farm and the coming
gardening plugin read it.

**Source.** SSURGO's FY2027 refresh, ten survey areas: ID001 Ada, ID665 Canyon, ID659 Payette, ID660 Gem, ID675
Owyhee, ID683 Boise County (west), ID685 Elmore, and Malheur's OR641, OR644 and OR645. Together they cover the whole
box (841,172 ha of 841,174) with no gaps. Public domain ("Access_Constraints: None"). NRCS asks for credit and says the
data isn't for regulatory decisions, so the card says "Mapped soil, not a site test; not for regulatory decisions".

- **Credit:** "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)". **Republish:** yes.
- **Refresh:** by hand each October after NRCS's yearly refresh, with the owner's OK for each download. Only survey
  areas whose version date (`saverest`) changed are reloaded. There's no collector and no schedule.

## Loading

The downloads are Web Soil Survey packages, unzipped into `$TVT_SOURCES/ssurgo/data/<AREA>/` (spatial and tabular;
the interpretations, `cinterp.txt`, were deleted as unused). Two steps, the trees pattern: the worker turns files into
files, and ingest stays standard library.

```bash
# 1. In the worker image (GDAL), about 0.5 GB of memory: polygons touching the box (whole) and their map units' rows
python plugins/soils/build/prepare.py --sources $TVT_SOURCES/ssurgo/data --out $TVT_ARCHIVE/soils/prepared/<stamp>
# 2. In the ingest image (standard library and psycopg), one transaction
python3 -m ingest soils-load --from $TVT_ARCHIVE/soils/prepared/<stamp>
python3 -m ingest soils-load --from DIR --areas ID001,ID665 --force    # reload some areas anyway
python3 -m ingest soils-load --from DIR --dry-run                      # check and derive only
```

On the scratch database (deploy/scratch): `scratch-run.sh <worktree> <name> worker python
plugins/soils/build/prepare.py --sources /srv/sources/ssurgo/data --out /srv/archive/soils/prepared/<stamp>`, then
`... ingest soils-load --from /srv/archive/soils/prepared/<stamp>`.

**The prepared folder** (`ingest/package.py`):

| File | What |
|---|---|
| `polygons.geojsonl` | one GeoJSON Feature per line, WGS 84 (7 decimals, about 1 cm): `{id, areasymbol, fid, mukey, musym}`, `id` = `<AREA>:<shapefile fid>` |
| `tabular/<table>.csv` | every column of `mapunit`, `muaggatt`, `component`, `corestrictions`, `cosurffrags`, `copmgrp`, `copm`, `cogeomordesc`, `coecoclass`, `cocropyld`, `chorizon`, `chtexturegrp`, `chtexture` and `chtexturemod`, for those map units only, with a header row (`areasymbol`, then SSURGO's column names) |
| `prepare.json` | the format (`tvt-soils-prepared/1`), the box, each survey area (name, `saverest`, version, scale, Web Soil Survey URL, counts), each file's sha256 and rows, each input file's sha256. Written last |

`soils-load` checks every file against its sha256 and refuses a package for another box. For each area to load it
replaces the area's rows (map units, components, horizons, polygons), then works out in PostGIS each polygon's area on
the ellipsoid and its area inside the box, `geom_lo` (simplified by 5 m in UTM 11N, for z12 and out), and `label_pt`
(the centre of the largest circle inside it). Invalid polygons are made valid and counted. It records the run in
`soils.build` (inputs' sha256, counts, licence), logs it in `ops.fetch` (source `ssurgo`), and gives the Soils layer's
tiles a new version (`core.layer_version`, layer `soils.units`) in the same transaction as the data. The load state
lives in the database (`soils.survey_area.saverest`), so it follows the database.

## Tables

Migration `0001_soils.sql`, schema `soils`. Only map units touching the box are kept; polygons stay whole, not clipped.

| Table | Rows (box) | What |
|---|---|---|
| `soils.survey_area` | 10 | symbol, name, `saverest`, version, scale, the package URL, the load that put it there |
| `soils.map_unit` | 1,038 | NRCS's map-unit fields and summary (`muaggatt`), and ours: the dominant component, the ground type, the shallowest restriction, the show-by codes, the area in the box and the polygon count |
| `soils.component` | 1,894 | every component of those map units: share, slope, drainage, hydrologic group, capability, taxonomy, landform, parent material, frost-free days, ecological site, restrictions and crop yields (JSON) |
| `soils.horizon` | 8,007 | depths, texture (with its modifier), sand, silt, clay, organic matter, pH, CaCO₃, gypsum, EC, SAR, AWC, Ksat, K factor, fragments |
| `soils.polygon` | 21,999 | `geom` (MultiPolygon, 4326), `geom_lo`, `label_pt`, `area_m2`, `area_in_box_m2` |
| `soils.ground_type` | 385 | the ground's soil types (below) |
| `soils.build` | per run | each load or photo run: inputs, settings, counts, licence, republish, credit |
| `soils.photo_stats`, view `soils.ground_colour` | (P2) | each ground type's measured colour, spread and texture; the view picks the newest photo build |

**The dominant component** has the largest share; ties go to a major component, then the lowest key. Its **surface
horizon** is the topmost mineral one (O horizons skipped).

**Ground types** (`soils.ground_type`): the dominant component's name plus its surface texture with modifier, as one
key, e.g. `purdam:silt-loam` or `chilcott:gravelly-silt-loam`. 385 in the box, 181 in Ada and Canyon. Per map unit
the same soil splits by slope phase and survey area, which would make colour seams at county lines; texture class alone
(about 12) is too coarse. Miscellaneous areas have no texture (`water`, `urban-land`), and `misc` says which kind
(`water`, `urban`, `rock`, `badland`, `rubble`, `pits`, `other`): water units yield to the water layer in the ground,
and rock gets a rock look. `frag_cover_pct` (gravel and stones on the surface) is area-weighted over the type's map
units that report it, for the ground's stones close up.

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
taken as 4326) with their area on the ellipsoid and their share of the shape's area, largest first. For the farm field
card and later the gardening bed card: "62% Purdam silt loam, 38% Power silt loam". A point gets the unit it falls in,
with share 1.

## Still to come

- The photo statistics (P2, `plugins/soils/build/photo_stats.py`): each ground type's colour, spread and texture from
  NAIP 2025 over its uncovered ground, into `soils.photo_stats`, and the ground export (`ground.fgb`, `palette.json`).
- The layer, card, legend and APIs (P1-app): `/api/soils/tiles/units/{z}/{x}/{y}` (MVT layers `soils` from
  `geom_lo` to z12 and `geom` beyond, `soil_labels` from `label_pt`), `/api/soils/at`, `/api/soils/mapunit/<mukey>`.

## Tests

- `python3 -m unittest plugins.soils.tests.test_package`: reading and deriving, on a synthetic survey
  (`tests/synthetic.py`; nothing in the repository is real SSURGO data).
- `TVT_TEST_DATABASE_URL=... python3 -m unittest plugins.soils.tests.test_load`: the load, the derived geometry and
  `mapunit_shares()` in a test database (each test rolls back).
- `prepare.py` needs GDAL: on the VM, `worker-test -C <checkout> plugins.soils.tests.test_prepare` (the worker image,
  where a skip counts as a failure).
