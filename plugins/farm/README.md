# farm

Farms and crops
([ch. 16](../../docs/16-ideas-and-personas.md#farmer-farm);
[ch. 17 §17.2](../../docs/17-sources-for-new-plugins.md#farms-and-crops)).
Two parts:

- **Crop water use:** Reclamation's AgriMet crop water use (ET) at the six
  AgriMet stations in the ring. It's part of Wave A, "start the clocks"
  ([ch. 17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)):
  the daily crop charts keep only their last four days, so their history
  exists only if we read them.
- **Crop fields** (landscape sprint, Oct 2026; [below](#crop-fields)):
  every farm field in the map box as an "estimated field", with its crop
  in 2025 (USDA's newest) and the seven years before, how sure USDA is,
  whether it was green in July, and whether it has been built over. The
  same data gives the painted ground its crop class, valley-wide
  ([DECISIONS](../../docs/DECISIONS.md), Oct 8: decisions 14 and 15).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `agrimet_et` | daily April to October; weekly November to March | U.S. Government work (public domain, inferred ⚠️); provisional data | U.S. Bureau of Reclamation, AgriMet | yes, labelled provisional |
| `nass_csb` | by hand, each yearly edition with the owner's OK (manual) | public domain | USDA NASS Crop Sequence Boundaries | yes |
| `nass_cdl` | by hand, each year's map with the owner's OK (manual) | public domain | USDA NASS Cropland Data Layer | yes |

**Tables:** AgriMet keeps none of its own. Everything goes to core's
`raw.record` until core's `met_station` and readings tables land
([ch. 17 §17.8](../../docs/17-sources-for-new-plugins.md#178-decisions-on-the-open-questions-oct-7),
Q8); its stations will then be the `agrimet` network. The crop fields are in
schema `farm` (migration `0001_fields.sql`, [below](#tables)).

## `agrimet_et`: AgriMet crop water use

Catalog entries: [farm.md](../../docs/sources/farm.md#usbr-agrimet-crop-water-use-charts-static-files),
[gardening.md](../../docs/sources/gardening.md#agrimet-crop-water-use-charts).

- **What:** daily evapotranspiration in inches of water a day: ETr (1982
  Kimberly-Penman alfalfa reference ET) all year, and each crop's ET while
  Reclamation's crop calendar for it runs. Parma, Nampa, Ontario and Grand
  View carry crops (alfalfa, pasture, lawn, grains, beets, onions,
  potatoes, beans, corn, peas, peppermint, grapes, apples and more); Boise
  and Boise Fairgrounds carry only ETr and lawn.
- **Stations** (Reclamation's `location.csv`, read Oct 7, 2026; all inside
  the ring, four of them in the valley box):

  | Code | Place | Since |
  |---|---|---|
  | BOII | Boise | 1995 |
  | BFGI | Boise Fairgrounds | 2013 |
  | NMPI | Nampa | 1996 |
  | PMAI | Parma | 1986 |
  | ONTO | Ontario, Oregon | 1992 |
  | GDVI | Grand View | 1992 |

- **Endpoints:** static text files on `www.usbr.gov`:
  - `/pn/agrimet/chart/<stn><yy>et.txt`, the year's ET summary, one row per
    day (cumulative, so each read covers the year so far; 5–41 KB);
  - `/pn/agrimet/chart/<stn>ch.txt`, the day's crop chart, "Estimated Crop
    Water Use" (CSV, about 1.6 KB): each crop's assumed calendar (start,
    full cover, terminate), the last four days, a forecast for the next
    day, the season's total and 7- and 14-day use. April to October only.
- **robots.txt:** `www.usbr.gov` disallows only `/pn-bin` and `/gp-bin`,
  so `/pn/agrimet/chart/` is allowed (checked Oct 7, 2026, and on every
  run through `ingest/http.py`). No crawl-delay; we space requests 3 s
  apart. `/pn-bin` (AgriMet's weather archives) and `data.usbr.gov`'s RISE
  API are disallowed and never used. GET only: the host resets HEAD.
- **Cadence:** Reclamation updates the files once a day (about 5:30–6:30
  MT), 1–3 days behind. April to October we read each station's chart and
  year file once a day (12 requests). November to March no chart is
  published, so we read only the year files, once a week (6 requests; 12 in
  the first two weeks of January, to close out December from last year's
  file).
- **What we keep** (`raw.record`, as readings: nothing is ever retired):
  - `PMAI:2026-10-05`, one station-day from the year file:
    `{"station", "date", "et_in": {"ETr": 0.14, "ALFP": 0.14, ...}}`.
    Crops not growing that day (`--`) are left out; anything that isn't a
    number is kept as written under `flags`.
  - `PMAI:chart:2026-10-06`, one day's chart: `{"station", "chart_date",
    "days", "crops": {label: {"start", "full_cover", "terminate", "et_in"
    (four days, oldest first), "forecast_in", "season_in", "use_7d_in",
    "use_14d_in"}}}`.
  - Each with the station's point. A value Reclamation revises adds a
    version; an unchanged day only moves `last_seen`.
- **Column labels:** repeated crop names are separate crop calendars
  (Parma has BEET twice and FCRN three times), so both files' columns are
  labelled by position: `BEET`, `BEET#2`. On the Oct 7 sample the chart's
  older days matched the year file for every crop, and each repeated
  crop's last day in the year file was its own calendar's terminate date.
- **Guards:** a file whose title names another station or year is refused;
  so is a year file with fewer than half the days we already hold for it
  (the file only grows during a year, so a short one is cut off). Other
  stations' files are still kept, and the run is logged as failed so it's
  seen. A missing file (404) is noted, not an error.
- **Limits:** the static files hold no temperature, rain, wind or
  humidity, so "lawn water use (ET)" can't subtract rain and degree-days
  can't come from here (farm.md, "Risks"). ETr is the only
  weather-derived value. Its Kimberly-Penman ETr isn't gridMET's ASCE
  ETr: convert before comparing. The crop calendars are Reclamation's
  assumptions, not observed planting. Past seasons are in the same static
  files (`<stn><yy>et.txt` for earlier years) but aren't loaded yet; that
  would be a one-off backfill.
- **Storage:** a station-day is about 80–350 bytes, a chart 0.5 KB (Boise)
  to 4 KB (Parma): roughly 30 KB a day in season, 6 MB a season; under
  1 KB a day off season.

**Commands:**

```bash
python3 -m ingest run agrimet_et
python3 -m unittest discover -s plugins/farm/tests -t .
```

**Ethics:** a federal agency's weather stations, nothing about people.
Values are provisional (Reclamation's
[disclaimer](https://www.usbr.gov/pn/agrimet/disclaimer.html)) and are
labelled so wherever we show them, credited to Reclamation AgriMet.
Collecting AgriMet's weather archives under `/pn-bin` would need
Reclamation's OK, an owner action
([ch. 17 §17.7](../../docs/17-sources-for-new-plugins.md#177-owner-actions-consolidated)).

## Crop fields

Built Oct 11, 2026 (landscape sprint, package P3-data; the farm design and
plan C5, C7). The layer, its card and the year switcher are P3-app's.

**Sources**, both public domain, downloaded by hand with the owner's OK (Oct
8) and kept with their provenance in `$TVT_SOURCES` (`/srv/tvt/work/sources`
on the VM):

- **CSB 2018-2025, rev23** (USDA NASS Crop Sequence Boundaries, released
  March 27, 2026, re-issued May 15): `csb/csb_mapbox.gpkg`, the 21,460 fields
  touching the map box, whole, in NASS's Albers (EPSG:5070), each with its
  CDL code for each of the eight years. The outlines are modelled from 30 m
  CDL pixels: edges are typically 5-15 m off, some fields are split or
  merged, so the map always says "estimated field". 803 rings cross
  themselves, as in NASS's file, and are made valid.
- **CDL** (USDA NASS Cropland Data Layer): `cdl/out/cdl_<year>_<res>m.tif`
  for 2019, 2020, 2023 (30 m) and 2024, 2025 (10 m, NASS's new method), cut
  from NASS's own grid; the legend; and NASS's Idaho 2025 accuracy workbook.
  The 2024 method change moves hay into grass/pasture and developed land up:
  don't read 2023-to-2024 changes as real.
- **Sentinel-2's July 2025 NDVI median** on the ground's 10 m grid
  (`sentinel2/july2025/ndvi_median.tif`; "Contains modified Copernicus
  Sentinel data 2025"). Its tags list the views it's the median of
  (`ACQUISITIONS`, July 1-26, 2025); the build takes the July state's year
  from them, never from the crop year.
- **COMPASS's permits and plats** (`obs.building_permit`, `core.plat`: the
  development plugin's sources, republish yes), joined at each farm load and
  by `farm-derive` for the growth flags and plats ([below](#growth-and-plats-between-loads)).

**The crop year** is CSB's newest, read as "2025 (USDA's newest)" (view
`farm.crop_year`). It moves on only when the next edition is loaded (CSB
2019-2026, about late March 2027); a crop is never guessed from Sentinel-2.

### Loading

Four steps, by hand, the trees pattern: the worker turns files into files, and
ingest stays standard library. On the scratch database (deploy/scratch;
`TVT_SOURCES` is `/srv/sources` there, `TVT_ARCHIVE` `/srv/archive`):

```bash
# 1. CDL classes (names, our crop groups, AgriMet crops, Idaho accuracy) and the rasters, into $TVT_ARCHIVE/farm/cdl/
python3 -m ingest farm-cdl-load --cdl $TVT_SOURCES/cdl/out --accuracy $TVT_SOURCES/cdl/docs/NASS_CDL_ID25_accuracy.xlsx
# 2. the CSB edition (stdlib GeoPackage reader, WKB to PostGIS)
python3 -m ingest farm-csb-load --gpkg $TVT_SOURCES/csb/csb_mapbox.gpkg --edition csb-2018-2025-rev23 \
    --published 2026-03-27 --last-modified 2026-05-15T17:58:04Z
# 3. the worker build (GDAL, NumPy, SciPy), about 70 s and under 1 GB: a light job. The July year is the NDVI's
#    own, from its tags (--july-year only for a raster without them, and it must agree with any it has)
python -m plugins.farm.build.build --csb $TVT_SOURCES/csb/csb_mapbox.gpkg --cdl $TVT_ARCHIVE/farm/cdl \
    --ndvi $TVT_SOURCES/sentinel2/july2025/ndvi_median.tif --out $TVT_ARCHIVE/farm/build/<UTC stamp>
python3 -m ingest farm-fields-load --build $TVT_ARCHIVE/farm/build/<UTC stamp>
# 4. the export the ground reads
python3 -m ingest farm-export
```

Each load runs in one transaction, then works out the derived columns
(`ingest/derive.py`): each field's letters and crop group now, its growth,
its plats, the z8-10 dissolves, and a new version of the crop-fields tiles
(`core.layer_version`, layer `farm.crop_fields`, with its licence and
credit, built from what's loaded: CSB's window, the July year of the fields'
states, COMPASS). A CSB or fields load takes about three minutes on the
scratch database, mostly the dissolves. Every command has `--dry-run` but the
export.
`farm-csb-load` and `farm-cdl-load` are logged in `ops.fetch` (sources
`nass_csb`, `nass_cdl`; no request is made).

**Editions.** `farm-csb-load` upserts by CSBID. Current fields the file
lacks, of an older edition, another revision of this one or this one's
earlier load, are closed (`valid_to`), never deleted, and linked to the new
fields covering at least a tenth of them (`successor`): a field that vanished
is part of the farmland record. Only the file's own fields can succeed one,
never the field itself. One of this edition's own fields that a reload drops
closes on the edition's date, so its `valid_from` and `valid_to` are equal:
as the edition now stands, it never had the field. Loading it again with the
field reopens it. Loading an edition older than the newest one loaded is
refused.
CSBIDs carry the window's years, so a new edition's ids are all new; its
fields get the new build's stats once it's built and loaded.

**Datum.** CSB and CDL are NAD83. They're taken as WGS 84 (the null shift,
basemap/ground/grid.py), in PostGIS (`ST_Transform` from the same Albers with
WGS 84's datum) and in the worker (`rasterize.srs_of`), so the fields, the
crop cover and the ground agree.

### The build

`build/build.py` (worker image), from the CSB GeoPackage, the CDL rasters and
the NDVI median:

1. **Agreement:** on each CDL raster's own grid, the share of a field's pixels
   (centres inside) with its CSB code that year. CSB's code is a smoothed
   majority: it matches the field's majority pixel in 97% of fields, and 78%
   of the pixels (2025).
2. **July state:** each field's median NDVI over the 10 m cells whose centres
   are inside it: **green** from 0.6, **growing** from 0.3, **bare or
   harvested** below. Its year (`july.year`, the credit's "Sentinel data
   <year>") is the NDVI's own, from the raster's `ACQUISITIONS` tag (else its
   `CREDIT`'s year). A raster with views outside July, or from two years, is
   refused, and so is `--july-year` when it disagrees with the tags.
3. **`crop_cover.tif`**, on the ground's 10 m grid (EPSG:32611 from E 495920
   N 4855750, 8,967 x 9,494 cells, exactly the NDVI's), three uint8 bands:

| Band | Values |
|---|---|
| `group` | 0 none, 1 corn, 2 hay, 3 grain, 4 roots, 5 specialty, 6 fallow: the field's 2025 code inside fields, the CDL pixel's in clusters. Pasture isn't crop (the scheme paints it as grass, decision 15), nor is a built-over field (its 2025 code is developed) |
| `state` | 0 none, 1 green, 2 growing, 3 bare or harvested: the NDVI median averaged over 3 x 3 cells (valid ones), where `group` > 0 |
| `confidence` | 1 **field interior** (the cell and its eight neighbours inside one field); 2 the **edge band** (cells a field touches that aren't interior), kept only where the CDL 2025 pixel (nearest, on the grid) is the field's group; 3 **CDL crop clusters** outside every field, 8-connected, at least 0.5 ha (50 cells) |

It works window by window (2,048 cells) with a 500 m halo, which makes every
cluster's size exact in the window's core: the test checks that 7-cell windows
give the same file. The build writes `fields.jsonl` (per field: agreement and
pixels per CDL year, the July state), `crop_cover.tif`, then `build.json` (its
inputs' sha256, parameters and counts) last. A folder without `build.json` is
unfinished; a finished one is never overwritten. `farm-fields-load` refuses a
build made from another GeoPackage than the edition loaded.

**Growth** isn't in the build: it needs COMPASS's permits, which are in the
database, so every load works it out (`ingest/growth.py`, rule `growth/1`):

- **built_over:** farmed (a crop, hay, fallow or pasture) in at least 2 of the
  window's first four years, developed (CDL 121-124) in its last two, and low,
  medium or high intensity (122-124) in the last;
- **being_built:** not built over, developed in the last year, farmed in at
  least one of the first four, and three or more new-construction permits
  inside it since the window began;
- **farmed:** the rest. A field developed in 2025 without the permits isn't
  flagged; `growth_detail.unconfirmed` says so, for the card.

The CDL's developed classes come from NLCD, so they step with NLCD's editions:
`growth_detail.developed_by` (the start of the last run of developed years) is
a "by" year, never a build date. **Plats** (`plat`): the share of each field
under COMPASS's approved or recorded, pending and built plats, and the largest
three by name. A field still farmed in 2025 and at least half under an
approved or recorded plat is the layer's "approved plat" (`p`).

#### Growth and plats between loads

Growth and plats are worked out at each farm load from development's tables
as they are then, and stored: the z8-10 dissolves (`built_over`,
`being_built`, `plat`) and the tiles' `s` and `p` need them precomputed. The
farm design had permits and plats joined at query time; at z11 that would
intersect every field in a tile with the plats on each request. Development's
sources update them (plats weekly, permits monthly), so between yearly farm
loads they drift: a plat approved, withdrawn or built, or new permits, show
only after

```bash
python3 -m ingest farm-derive              # letters, growth, plats; the dissolves and a new tile version if a field changed
python3 -m ingest farm-derive --dry-run    # how many fields would change (no dissolves); rolls back
```

It reads no new farm data. With nothing changed it writes nothing and takes
seconds; otherwise about three minutes on the scratch database (the
dissolves), a light job. Like the loads, it runs by hand, never inside
`ingest serve` (plan item 27). Run it after development's weekly plats run,
and before a review or a deploy. Once M1's `ops.build_pending` is on main,
development's sources should mark it (`farm-derive`) when they change. The
card can still read a field's plats live from `core.plat`, as the design had
it; the stored `plat` and `growth_detail` are as of the last load or derive
(the tile version's note names the day). This choice is pending with the
owner ([DECISIONS](../../docs/DECISIONS.md#pending-owner-to-decide)).

**Crop groups** (`ingest/crop_classes.csv`): NASS's legend (names, colours)
with our group and the AgriMet crops whose water use the card can show (our
mapping ⚠️). The groups are the farm design's: corn and sorghum; hay and
alfalfa; small grains; roots, vegetables and beans (oilseeds too); specialty
(mint, hops, seed, orchards, vineyards); pasture; fallow; developed; other.
The codes the Oct 8 analysis grouped are as it had them; NASS's other crop
codes are placed by kind (none is in the box's 2025 fields).

### Tables

| Table | Rows (Oct 11) | What |
|---|---|---|
| `farm.edition` | 1 | each CSB edition: its window, release, the file's sha256, counts, licence, republish, credit |
| `farm.crop_class` | 133 | CDL codes: name, group, letter, NASS colour, AgriMet crops, Idaho 2025 accuracy (76 codes) |
| `farm.cdl_year` | 5 | the CDL rasters in `$TVT_ARCHIVE/farm/cdl/`, with sha256, method, licence, republish, credit |
| `farm.build` | 1 | each loaded build: its inputs, parameters and counts, licence, republish, credit (with the July NDVI's year) |
| `farm.field` | 21,460 | the fields: outline (4326), CSB's interior point, acres, county, codes per year (`crops`), `letters`, `group_now`, `bearing`, `agree`, `july`, `growth` (+ detail), `plat`, `valid_from`/`valid_to`, `successor`; `id` is the tiles' feature id |
| `farm.field_lo` | 1,386 | the z8-10 dissolves: by crop group per year and by growth state (`built_over`, `being_built`, `plat`), closed across gaps under a pixel, simplified by half a pixel, parts under half a square pixel dropped, cut to each zoom's tile grid (EPSG:3857) |

Every table and view says its licence, republish and credit in its comment
(`\d+ farm.field`; plan C3): CSB and CDL public domain, Sentinel-2
Copernicus, COMPASS none stated (development: republish yes); all republish
yes. The tile views point at their `core.layer_version` row.

Views for the tiles (`/api/farm/tiles/crop_fields`, P3-app), read by
mvt.ts as one table per zoom band:

| View | Zooms | Columns |
|---|---|---|
| `farm.crop_fields_lo8`, `_lo9`, `_lo10` | z8, z9, z10 | `g` (crop group, 2025) or `s` (growth state or `plat`), `geom` (3857). About 41-74 KB a tile at the densest |
| `farm.crop_fields` | z11 on | `id`, `a` acres, `g` group now, `n` crop name now, `y` one letter per year from 2018 (`c` corn, `h` hay, `g` grain, `r` roots, `s` specialty, `p` pasture, `f` fallow, `d` developed, `o` other, `-` none), `s` growth, `st` July state, `p` approved plat, `geom` (4326). About 181 KB a tile at the densest z11, 55 KB at z12 |
| `farm.crop_year` | | the crop year and its label, "2025 (USDA's newest)" |

`farm.field_lo` also has every other year's dissolves (`yr`, `now` false),
for a year switcher at valley zoom with a cut of its own per year: one year is
about 75 KB at the densest z10 tile, all eight together about 630 KB. The
cuts took 0.1-0.6 s on the scratch database (Oct 11), well under the tile
pool's 3 s.

### The export for the ground

`farm-export` writes `$TVT_ARCHIVE/farm/export/<build>/` through the ground's
contract ([basemap/ground](../../basemap/ground/README.md)), checked against
the ground's own rules before it's left there:

| Layer | Format | Licence | What |
|---|---|---|---|
| `crop_cover` | GeoTIFF, 10 m grid, bands `group`, `state`, `confidence` | Copernicus (public domain CSB and CDL, Copernicus Sentinel-2), republish yes | the build's file (4.5 MB) |
| `fields` | FlatGeobuf, MultiPolygon, EPSG:32611 | public domain, republish yes | every current field: `id` (farm.field's), `csbid`, `crop_group` (crop_cover's codes), `cdl` (the 2025 code), `bearing` (the long side of its minimum-area rectangle, degrees clockwise from grid north, 0-180: the row direction), `acres` (15 MB) |

Credits: "USDA NASS Crop Sequence Boundaries 2018-2025", "USDA NASS Cropland
Data Layer 2025", "Contains modified Copernicus Sentinel data 2025" (the
build's July year). Neither layer is a base layer. `python3 basemap/ground/ground.py status --archive
$TVT_ARCHIVE` shows the ground reading both.

### Measured on the scratch database (Oct 11)

- 21,460 fields, 369,858 acres. 2025 groups (fields, acres): corn 4,861
  (119,531), hay 4,479 (74,024), small grains 3,181 (55,205), roots 2,871
  (53,284), specialty 1,625 (25,625), pasture 1,555 (16,005), fallow 278
  (3,429), developed 1,733, other 877.
- Built over: 621 fields, 5,680 acres (developed by 2021: 286, by 2024: 316);
  530 of them have a new-construction permit since 2018. Being built: 406
  (5,066 acres). Still farmed and at least half under an approved plat: 491
  fields, 8,138 acres.
- July 2025: corn 95% green, sugarbeets 95%, mint 80%, alfalfa 74%; winter
  wheat 84% bare or harvested, fallow 71%; pasture split (48% bare).
- crop_cover: 1,094 km² of field interiors, 170 km² of edge band where the
  CDL agrees, and 60.6 km² of CDL clusters outside every field: fallow
  (9.3 km²), alfalfa and other hay (13.5 km²), corn (4.5 km²) and orchards
  (peaches, grapes, apples, cherries, plums: about 13 km²) the most. Some
  clusters will be lawns, lots or misclassified trees; the painter keeps
  only those the photo confirms.

### Refresh

Yearly and by hand, each download with the owner's OK: CDL about late
February, CSB about late March. Load the new CDL year (`farm-cdl-load`), the
new edition (`farm-csb-load`), rebuild, load the build and export. A new July
state needs a new Sentinel-2 run, or the landscape's July drifts from the crop
year shown. Until then a rebuild under the 2026 crop year still says July
2025 (and credits Sentinel data 2025), from the NDVI's tags.

Between those: `farm-derive` after development's plats and permits change
([above](#growth-and-plats-between-loads)).

### Tests

```bash
python3 -m unittest discover -s plugins/farm -t .        # stdlib: the GeoPackage reader, classes, growth
TVT_TEST_DATABASE_URL=postgresql://... python3 -m unittest plugins.farm.tests.test_load    # the loads, the export
data/dev/worker-test-remote.sh <worktree> p3-data plugins.farm.tests.test_build             # the build, worker image
```

The fixtures are synthetic: `tests/synthetic.py` writes a three-field
GeoPackage with the standard library (a corn field, a built-over field, and a
"bowtie" ring that crosses itself), and the worker test paints CDL and NDVI
rasters around it with GDAL.

**Ethics (crop fields):** CSB has no owners; fields are never joined to the
Assessor's parcels in anything public, and the outlines are always called
estimated. Growth joins COMPASS's permits and plats, which are already
public (development: republish yes).
