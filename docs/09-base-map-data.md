# 9. Base-map data: building our own map of the valley

What's available to build a fully owned 2D/3D map of Ada and Canyon counties:
terrain, LiDAR, streets, lanes, buildings, imagery and parcels, along with
the licenses. Research as of Oct 5, 2026, with details added from the Oct
6–7 research on imagery, lanes and parcels. Items marked ✅ were
spot-checked directly; the rest come from the research pass and should be
re-checked before relying on them. The Oct 5 inventory used the box
−117.03, 43.0, −115.97, 43.81.

---

## 9.1 Summary

- **Everything needed for an open, key-free base map exists:** high-density
  LiDAR terrain (public domain), OpenStreetMap/Overture streets, buildings
  with heights (83%), lane counts, and NAIP imagery.
- **Paid or restricted, to avoid:**
  - Google Photorealistic 3D Tiles: billing; no caching or analysis; can't
    be used next to a non-Google map.
  - Esri and MapTiler basemaps: API keys and terms.
  - COMPASS's own LiDAR and orthophotos: $220–350 per grid cell.
- **Needs a terms check before redistributing:**
  - ACHD's 3-inch imagery: no license stated.
  - Boise's 3D buildings: no license stated.
  - Ada County Assessor data: "do not re-distribute".

## 9.2 Elevation, terrain and LiDAR

USGS 3D Elevation Program (3DEP) coverage, by the 3DEP index at each city
(the WESM index, with collection dates and quality levels:
`index.nationalmap.gov/.../3DEPElevationIndex/MapServer/24`):

| Area | LiDAR project | Quality | Flown | Published |
|---|---|---|---|---|
| Boise, Meridian, Eagle, Star, Kuna, Caldwell, Parma | `ID_SouthernGaps_2_D23` | QL1 (8+ points/m²) | 2023-09 to 2024-08 | Point cloud Dec 2025–Jan 2026; 1 m DEM Apr 2026 |
| Nampa, Melba | `ID_SouthernID_21_2018` | QL2 (2+ points/m²) | 2019-10 to 2020-08 | 1 m DEM May 2024 |
| Also present | `ID_FEMAHQ_2018` (partial Boise area), `NV_USFSR4_4_D23` (foothills), legacy 2003–2009 sets | | | |

| Product | Format | Size for the valley | License | Where |
|---|---|---|---|---|
| ✅ **1 m DEM** | Cloud-optimized GeoTIFF, 10 km tiles (sample tiles 20–83 MB) | About 168 tiles, about 32 GB | Public domain | `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/<project>/TIFF/` (public, no key) |
| 1/3 arc-second (about 10 m) DEM | COG | 411 MB per 1° tile (`n44w117`) | Public domain | `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/` |
| LiDAR point clouds | LAZ 1.4 (2023–24), **not COPC** (header checked); NAD83(2011) UTM 11N + NAVD88 (Geoid18). Streamable EPT on AWS for the 2018–20 project only | About 160 GB (2023–24 tiles in the box; details below) | Public domain | TNM downloader / `tnmaccess.nationalmap.gov` API; `rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/ID_SouthernGaps_D23/...`; `s3://usgs-lidar-public/ID_SouthernID_21_2018/ept.json` |
| 3DEP dynamic elevation service | Esri ImageServer | On demand | Public domain | `elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer` |
| Idaho LiDAR Consortium / ISU statewide DTM | Zipped rasters per 15′ quad | 3.6–4.7 GB per quad; 16 zips cover `Q43116`, dated 2024–2026 | Terms not found | idaholidar.org; files at `giscenter-sl.isu.edu/AOC/AOC_DEM/Idaho/LidarDTM/Q43/` |
| Ada County "Boise Foothills 2015" LiDAR (Quantum Spatial) | LAS, through ISU's Globus | Foothills only, 340 km²; flown Sep–Oct 2015 | No terms found | Ada County |
| COMPASS 2019 LiDAR | Point cloud + ground TIFF | — | **Paid** ($220 per cell) | compassidaho.org/orthophotography |

**Point-cloud details** (Oct 5 inventory):

- LiDAR point-cloud tiles in the box: `SouthernGaps` about 3,180 tiles,
  162 GB; `SouthernID_2018` about 2,458 tiles, 712 GB (the box overshoots
  the valley, so that's more than we'd need).
- AWS `usgs-lidar-public` EPT: the Nampa work unit alone holds 39.9 billion
  points; not requester-pays.
- Microsoft Planetary Computer's `3dep-lidar-copc` covers 2012–2022 only:
  `FEMAHQ_2018` is there, nothing from 2023–24. Its catalog entry says
  "proprietary", though the data is USGS public domain.

**Terrain tiles for the web map:**

- **Best:** build our own from the 1 m DEM (terrain-RGB for MapLibre, or
  quantized-mesh for Cesium). It's the most accurate and stays public
  domain.
- **Quick start:** AWS Terrain Tiles (free; last updated 2017; need the
  tilezen/joerd attribution) or Mapterhorn (open PMTiles; code BSD-3). Its
  `planet.pmtiles` is z0–12 and 355.6 GB (2026-09-11), with separate
  regional files for z13–17.
- ✅ **Built (Oct 5):** terrain-RGB from the 1 m DEM, as 512-px PNG tiles,
  z6–14 (`basemap/terrain.py`): 1,030 MB, 7,820 tiles.
- ✅ **Re-encoded (Oct 6):** the same tiles as lossless WebP, with heights
  rounded by zoom: 1 m up to z10, 0.5 m at z11, 0.4 m at z12, 0.2 m at z13,
  none at z14 (`basemap/terrain_reencode.py`). 568 MB (−44.9%); the first
  load at the default view drops from 8.64 to 4.57 MB in the sandbox's
  measurement. Steps were tuned by before/after screenshots: larger ones
  (0.5 m at z13, 0.2 m at z14) drew contour lines across the flat valley
  floor. The rounding is on the encoded value, so no height moves more than
  half a step. Not on the server until the next deploy.

## 9.3 Streets, network and lanes

| Source | What | Format | License | Where |
|---|---|---|---|---|
| **OpenStreetMap** (Geofabrik Idaho) | Full street map with tags (lanes and turn lanes where mapped) | .osm.pbf, 123 MB | ODbL | download.geofabrik.de/north-america/us/idaho.html. Its robots.txt disallows automated downloads of every extract format, the update diffs and the checksums (checked Oct 6): loaded from a hand download until Geofabrik answers ([DECISIONS](DECISIONS.md)); first load Oct 7 ([SOURCES](SOURCES.md#openstreetmap-first-load-oct-7)) |
| **Overture Maps transportation** (release 2026-09-23.1) | 173,146 road segments in the valley box; speed limits on about 14k; stable IDs across releases; no lane-count field | GeoParquet (query in place) | ODbL | `s3://overturemaps-us-west-2/release/2026-09-23.1/theme=transportation/` |
| ✅ **ITD HPMS** (federal highway inventory) | **Through lanes** by direction (19,801 records in the box, Oct 6), turn lanes (637, samples), lane width (92% the 12 ft default), median, shoulders, access control. Good on state routes; looks like defaults on ACHD arterials (Fairview Ave reads 1+1; it has 5 lanes). HPMS calls Chinden undivided: 1+1 for 12.5 km, 2+2 for 11.6 km (an earlier reading of its A and D routes as two disagreeing carriageways was wrong: on an undivided state route the D route is a placeholder on the A route's line, Oct 6). Details below | Esri FeatureServer | Credit ITD | `gisp.itd.idaho.gov/server/rest/services/GDWarehouse/HPMS/FeatureServer/25` (through) and `/27` (turn) |
| ITD road network (linear referencing system, LRS) | State system plus local roads, interchanges; 56,464 features statewide | FeatureServer | Credit ITD | `.../GDWarehouse/RoadNetwork_Primary/FeatureServer` |
| ACHD Master Street Map | Arterials and collectors with **existing, funded and planned lanes**, typology, parking (1,049 arterial segments). Lanes count the whole cross-section (5 = 2+2 plus a centre turn lane ⚠️); blank on state routes. Details below | FeatureServer | None stated ("Created by Ada County Highway District, 2026") | `gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Master_Street_Map_Arterials/FeatureServer/1` |
| COMPASS RegionalCenterline | Ada + Canyon centerlines (62,213) with `pm_id`, which links to the travel model and crash data; posted speed and **lanes**, so it covers Canyon County (but see the filler 2s below) | FeatureServer (hub) | Disclaimer only | COMPASS open-data hub |
| Ada County Assessor centerlines | With address ranges; updated twice a month | Shapefile, 6.6 MB | **"Do not re-distribute"** | `adacountyassessor.org/public/roadcenterline.zip` |
| Canyon County roads | Street names and types only (6,206 features; fields `STREET` and `ROAD_TYPE`) | FeatureServer | Full data by records request | `maps.canyoncounty.id.gov/arcgisserver/.../CanyonCountyRoads/FeatureServer/0` |
| Census TIGER/Line 2025 | Roads with address ranges | Shapefile (2.4 + 1.5 MB) | Public domain | `www2.census.gov/geo/tiger/TIGER2025/ROADS/` (the `TIGER2026` folder returned 404 on Oct 5) |

ITD's traffic layer also holds 56,904 cumulative AADT records in the box
(Oct 5 inventory).

### Getting OpenStreetMap data

- OpenStreetMap already reaches us automatically through the Protomaps
  base-map tiles (§9.7), but those drop the lane and signal tags. Only the
  raw tagged data for our area needs a hand download or Geofabrik's
  permission.
- Geofabrik's Idaho extract is about 123 MB (the Oct 5 extract loaded on
  Oct 7 was 129 MB); the planet file, about 80 GB, would be no help even
  where allowed.
- The routes checked on Oct 6 and why each was refused are in
  [DECISIONS](DECISIONS.md) (Oct 6, "OpenStreetMap: no scripted download
  for now"). The pilot judged Geofabrik's blocks as aimed at crawlers, so
  asking for one scripted download a week should be easy; the request is
  among the unsent drafts.
- **Open option, not decided:** the Overpass mirror `overpass.private.coffee`
  has no robots.txt (404, which means no rules), so it's a possibly allowed
  route. It returns OSM XML; the same osmium pipeline runs on it, perhaps
  after an `osmium sort` step. overpass-api.de's robots.txt answered 503
  and still has to be read from a normal network (the pilot suspected it
  disallows the query path too).

### ITD HPMS in detail (Oct 6)

`gisp.itd.idaho.gov/server/rest/services/GDWarehouse/HPMS/FeatureServer`:
robots.txt 404 (no rules); 2,000 records a page; JSON, GeoJSON or PBF. No
license stated; copyright ITD, so credit ITD.

- **Edited continuously:** 19,728 of the 19,801 through-lane records were
  modified after 2025-01-01. The items were modified 2026-06-29, around the
  annual June 15 federal submittal ⚠️.
- **Queries:** spatial statistics queries time out (over 120 s); use plain
  paged queries.
- **Through Lanes (layer 25)** in the box: 19,801 records (444 on state, US
  or interstate routes; 19,357 local). By lane count: 2 lanes 18,885
  (default-like), 1 lane 166, 3 lanes 47, 4 lanes 176, 5 lanes 6, 6 or
  more 29. Data source "unknown" on all but 10.
- **Other layers** (records in the box): 27 Turn Lanes 637 (412 local),
  8 Lane Width 558 (92% 12 ft), 10 Median 738, 19 Shoulders 634, 0 Access
  Control 5,377, 16 Peak Lanes 1,384, 5 Facility Type 4,937, 12 Ownership
  20,353.
- **Location columns:** `EventID`, `RouteID`, from and to miles, from and
  to dates, `SystemModifyDate`.
- **Names and network:** names from `RoadNetwork_Other/3` Road Names
  (18,776). Network `RoadNetwork_Primary/7` (17,757); state highway system
  `/6` (216); `LocalRoadInventory/0–1` (3,573, no lanes).
- **Quirk:** stretches shared by two routes read 0 lanes on one of them;
  skip those.
- **Unreliable on ACHD arterials** (lanes build, Oct 6–7): where the Master
  Street Map says 5 lanes, HPMS reads 1 each way on 93 of 155 km.

### ACHD Master Street Map in detail (Oct 6)

`ArcGIS_Hub/Master_Street_Map_Arterials/FeatureServer/1`, "Created by Ada
County Highway District, 2026". All 1,049 segments are stamped 2026-08-20
(a bulk reload).

- **Fields:** `StreetCode`, `StreetName`, `StreetTypo`, `Typology` (AR, AT,
  STATE, APC, MA; an `N_` prefix means a new road), `ExistLane`,
  `PlanLane_C` (funded; 830 read "No Funded Improvement"), `PlanLane_P`
  (planned), `ROWProject`, `ROWPreserv`, `Parking`, `RelatStudy`,
  `Comments`, `GlobalID`.
- **`ExistLane`:** 2 on 414 segments, 5 on 189, blank on 153 (state routes
  and interstates), 3 on 150, 0 on 75 (planned roads), 4 on 49, 6–8 on 16.
- **Read as the whole cross-section** ⚠️: 5 = 2+2 plus a two-way left-turn
  lane; 3 = 1+1 plus one; 7 = 3+3 plus one.

### Lanes: which source wins where

Decided by the owner, Oct 6, 2026. No source is good everywhere:
OpenStreetMap has `lanes` on 72% of major roads in the box and `turn:lanes`
on about 40% of signal approaches (May 2026 data ⚠️), and no source has
widths worth using. Each source's values are kept per segment, and every
lane number shown says where it came from:

| Roads | Through lanes | Turn lanes at signals | Width |
|---|---|---|---|
| State, US and interstate routes | ITD HPMS; OpenStreetMap as a check, disagreements flagged | OpenStreetMap, then COMPASS's right-turn lanes and phasing, then HPMS | Class defaults, marked estimated |
| ACHD arterials (Ada) | Master Street Map; OpenStreetMap for the split by direction; HPMS last | OpenStreetMap, then COMPASS | Defaults |
| Canyon County arterials | OpenStreetMap, then COMPASS's centerline lanes, then HPMS | OpenStreetMap, then COMPASS | Defaults |
| Collectors and local streets | OpenStreetMap where tagged, otherwise assumed 1+1 | — | Defaults |
| Planned changes | Master Street Map funded and planned lanes; ACHD's 574 planned intersection projects | | |

OpenStreetMap stays in its own tables (ODbL); a combined lanes view that
uses it is a derivative database if it's ever published (§9.8).

Other lane facts we hold, used only as cross-checks: ITD's work-zone feed
gives lanes on 170 of the 239 valley work zones (1–5 lanes); 511's
`LanesAffected` is free text; COMPASS gives right-turn lanes per approach
at its 585 signals.

### Lanes on four corridors (research, Oct 6)

OpenStreetMap figures are km per carriageway, from Overpass data of May
2026 ⚠️.

| Corridor | ITD HPMS | Master Street Map | OpenStreetMap |
|---|---|---|---|
| Eagle Rd (SH-55, I-84 to SH-44) | 3+3 from I-84 to Ustick, 2+2 from Ustick to SH-44; turn lanes the full 6.8 mi; 12 ft lanes; curbed median 15 ft | Blank (state route) | `lanes` on 74% of 36 km; turn lanes on 52% of approaches (15 of 29) |
| Chinden Blvd (US-20/26) | First read as 2+2 from Eagle to Garden City, turn lanes for 22 mi; later read as undivided, 1+1 for 12.5 km and 2+2 for 11.6 km (table above) | Blank (state route) | `lanes` on 100% of 33 km, mostly divided 2+2; turn lanes 53% (9 of 17) |
| State St | 2+2 from SH-44 at Star to Glenwood; the Boise local part mostly 2 ⚠️ | Boise part 5 now; 7 planned and funded (6 km) | `lanes` on 77% of 31 km; turn lanes 34% (16 of 47) |
| Fairview Ave | Wrong: 1+1, with Peak Lanes 2 per peak direction; turn lanes on 3.6 of 26.7 mi | 5 now; 7 planned and funded (11 km) | `lanes=5` on 97% of 19 km; turn lanes 39% (11 of 28) |

Which source won on the same corridors in the lanes build before any
OpenStreetMap was loaded (Oct 7, km of ACHD segments):

| Corridor | Master Street Map | HPMS | Assumed 1+1 | COMPASS | Conflicts flagged |
|---|---|---|---|---|---|
| Eagle Rd | 12.8 | 11.9 | 5.5 | 0.3 | 1.9 |
| Chinden Blvd | — | 24.9 | — | 0.2 | 0.7 |
| State St | 13.4 | 14.8 | 3.2 | 0.1 | 4.5 |
| Fairview Ave | 14.6 | — | — | 0.4 | 0.8 |

### What the lanes builds found (Oct 6–7)

The rule above is built as `core.segment_lanes`
([ch. 12 §12.5](12-database-schema.md#125-core-our-entities)).

- **COMPASS's centerline uses "2 lanes" as a filler** on 99.6% of Ada
  local streets; values other than 2 look real. So a COMPASS 2 counts as
  unknown unless a trusted source agrees.
- **ITD codes a divided highway's inventory direction as facility type 2
  (two-way).** I-84's A route carries 2–6 lanes one way and 0 the other,
  coded two-way, for 281 miles. Migration 0017's facility-type override
  therefore halved divided state routes (147 segments, 51 km flagged
  `ad_conflict`) until 0018 fixed it. Afterwards 3 readings still carry
  `ad_conflict`: one-way facilities whose A row claims both directions.
- **`carriageway_split`** applies to 76 segments; the case that prompted it
  was about 0.4 km on Eagle Rd.
- **Ties between routes on the same road:** westbound I-84 read 1 lane for
  28.8 km because concurrent US-26's D route, a 1-lane placeholder, tied
  with I-84's own D route on share. Ties now go to the Interstate, then the
  US route, then the state route. Westbound I-84 now reads 2–5 lanes;
  3.1 km of Interstate (I-184 branches and ramps) still read 1.
- **First server load** (Oct 7, about 00:49 UTC), and after the first
  OpenStreetMap load later that day ([SOURCES](SOURCES.md#openstreetmap-first-load-oct-7)),
  in ACHD segments:

  | Source that sets the lanes | Before OpenStreetMap | After |
  |---|---|---|
  | OpenStreetMap | — | 7,636 |
  | ACHD Master Street Map | 3,776 | 3,776 |
  | ITD HPMS | 1,247 | 1,116 |
  | COMPASS centerline | 364 | 206 |
  | Assumed 1+1 (mostly local streets) | 33,023 | 25,699 |
  | Flagged where trusted sources disagree | 207 | 651 |

- The full view reads in about 4–5 s, so it stays a plain view rather than
  a materialized one.

## 9.4 Buildings

| Source | Count | Heights | License | Where |
|---|---|---|---|---|
| **Overture buildings** | 347,652 in the valley box: 281,713 from OSM, 65,939 from Microsoft's ML footprints | **83% have height** (mostly Microsoft ML); downtown Boise 1,741 buildings, 68% with height, 274 with `num_floors` | ODbL; upstream credits include Esri Community Maps and Google Open Buildings (both CC BY 4.0) | `s3://overturemaps-us-west-2/release/2026-09-23.1/theme=buildings/type=building/` |
| ✅ **Boise 3D Buildings** | 135,710 (Boise area) | Height, roof form, base elevation (from 2019 LiDAR) | **None stated**; ask the City | `services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Boise_Buildings_3D/FeatureServer/0` (3D multipatch) |
| Microsoft US footprints | 942,132 statewide (Idaho zip 34.4 MB; its README says 259 MiB) | Not in US release | ODbL | minedbuildings.z5.web.core.windows.net |
| OSM buildings | Included in Overture | Where tagged | ODbL | Geofabrik |

**Boise 3D Buildings in detail:** extent −116.375 to −116.094, 43.51 to
43.71; fields `BLDGHEIGHT`, `ROOFFORM`, `BASEELEV`, `ROOFDIR`. The layer
says it was "created by automated processing of Ada County's 2019 LiDAR"
and is "not regularly updated". Whether that is COMPASS's paid 2019 LiDAR
is unverified; no 2019 LiDAR for Boise is in the 3DEP index.

## 9.5 Imagery

| Source | Coverage | Resolution | License | Notes |
|---|---|---|---|---|
| **NAIP 2025** (found Oct 6) | Whole valley (270 quarter-quads in the box), flown May 25–Jul 24, 2025 | **0.3 m**, 4-band | Public domain; USDA asks to be credited in derived products | Not yet on Planetary Computer. USDA's image service `apps.geo.fpac.usda.gov/geo-imagery/rest/services/naip/conus_naip/ImageServer` (no key; `exportImage` up to 15000×4100), an Idaho State University mirror (`giscenter.rdc.isu.edu/server/rest/services/NAIP/NAIP/ImageServer`, 0.3 m, credited "USDA NAIP and the GIS TREC @ ISU"), and county mosaics on USDA NRCS's public Box share (`nrcs.app.box.com/v/naip`, 2025 → ID → id_m: Ada 4.8 GB, Canyon 4.3 GB; MrSID MG4 with red, green, blue, near-infrared and a county mask, confirmed Oct 7). Lane lines, stop bars and crosswalk bars are crisp; mast arms mostly as shadows; ±4 m absolute spec ⚠️ (about 1.5 m at one site; 0.85 m from NAIP 2023 at Eagle & Fairview). The sharpest free option. **In use since Oct 6** for the detail layer: 250 m around the 228 cameras and 150 m around COMPASS's 585 signals, z15–18, exported from USDA's image service (1,232 exports, one at a time, 2.5 s apart; `imagery.py --detail-source usda`). **Since Oct 7 the detail layer covers all of Ada and Canyon** at z15–17 (about 0.43 m per pixel) from the county mosaics, plus z18 around the cameras and signals: 154,338 tiles, 5.6 GB (`basemap/naip_ccm.py`, `basemap/imagery_county.py`). Our GDAL can't read MrSID, so the mosaics are decoded with LizardTech's free MrSID Decode SDK (closed source, internal use only, run in a container without network, never in this repo). The county files are kept for their near-infrared band (land cover, ch. 16 §16.3). The valley-wide layer (z8–14) is still NAIP 2023. |
| **NAIP 2023** | Whole valley | 0.6 m, 4-band | Public domain | Cloud-optimized GeoTIFFs on Microsoft Planetary Computer (free). AWS copy is requester-pays. Our base map's valley-wide aerial layer (to z14). |
| ACHD Ada County Imagery 2024/2025 | **Ada only**: 2024 the urban core (780 km², 3 inch, Apr 1–2, 2024); 2025 about 72% of Ada (3 inch in 267 sections, 6 inch in 500; undated, probably April 2025) | **3 inch** | **None stated**; really COMPASS's product (flown by GeoTerra "for use by the COMPASS members") | ImageServer; `exportImage` works, no tile cache. Shows lane arrows, stop bars and mast arms that NAIP doesn't. **View on request only** (owner, Oct 6); asked of ACHD and COMPASS. If they agree: a private copy of 300 m around signals and cameras only (about 95 km², 2–4 GB, one overnight fetch); not the whole county (50–120 GB, a product COMPASS sells). Details below. |
| COMPASS orthophotos 2025 | Ada + Canyon | 3–6 inch | **Paid** ($350 per section) | compassidaho.org |
| Ada County IT imagery caches 2019, 2022, 2024, 2025 | Ada | about 3 inch | None stated (2019 credits "Ada County IT") | `tiles.arcgis.com/tiles/dgGjZc6xAH5m5JyP/...`. Probably the same COMPASS program (same years and resolution; Meridian's 2019 imagery credits COMPASS) ⚠️, so treated like ACHD's: asked of COMPASS, not used meanwhile. |
| USGS High Resolution Orthoimagery, Boise and surrounding cities | Boise, Eagle, Meridian, Star, Kuna, Caldwell | 0.15 m | CC BY 4.0 (INSIDE Idaho) | June 2013: a historical layer only |
| Canyon County imagery | Canyon | — | Token required | — |
| Esri World Imagery | Everywhere | Sub-meter | Esri license; API key outside ArcGIS | Avoid for an open stack |

**Rule for imagery without a license** (owner, Oct 6, 2026): a city's or
county's imagery that states no license may be used, with credit and a
courtesy note asking the agency to confirm, unless there's reason to suspect
it's someone else's licensed or paid product being reshared. ACHD's and Ada
County's 3-inch imagery fall under that exception (probably COMPASS's paid
orthophotos), so they wait for COMPASS's answer.

### ACHD's 3-inch imagery in detail (Oct 6)

A research pass on Oct 6 made 36 requests, at least 3 s apart: 31 to
`gis.achdidaho.org`, 3 to ACHD's open-data hub and 2 to `compassidaho.org`
(none to `more.achdidaho.org`). Robots.txt: `gis.achdidaho.org` 404 (no
rules); the hub and `compassidaho.org` set Crawl-delay 60, and COMPASS's
orthophoto page answered 403.

| | 2025 service | 2024 service |
|---|---|---|
| Service | `gis.achdidaho.org/imagery/rest/services/Imagery/Ada_County_Imagery_2025/ImageServer` | `.../Imagery/Ada_County_Imagery_2024/ImageServer` |
| Title | "2025 COMPASS 3-Inch and 6-inch Orthophotography" | |
| Tiles | 767 section tiles: 267 at 0.25 ft, 500 at 0.5 ft; about 1,990 km², about 72% of Ada | 302 tiles, all 0.25 ft; about 780 km², the urban core |
| Date | Not stated: the item info copies the 2024 text | April 1–2, 2024, leaf-off |
| Accuracy | Not stated | 0.7 ft (0.21 m) horizontal RMSE |
| Storage on the server | Uncompressed | JPEG, quality 75 |
| Credit and license | `copyrightText`, `licenseInfo` and `accessInformation` all empty | "GeoTerra, Inc."; the license field is only a liability disclaimer |
| Capabilities | Image, Metadata, Catalog; **no Download** | The same plus Mensuration |

**Both services:** 0.0762 m RGB, 8-bit; native spatial reference wkid
102459 (NAD_1983_Idaho-Ada_County, transverse Mercator, US feet);
`exportImage` up to 15000×4100 as JPEG, LZ77, LERC or uncompressed. No tile
cache: no `tileInfo`, `exportTilesAllowed` false, and WMTS returns 400.
They're the only imagery on that server; its Testing and Utilities folders
need a token. ACHD's hub matches 0 of its 28 items for "imagery", and there
is no terms page (the server root is a bare IIS page).

**What 3 inches shows**, from comparison with NAIP:

- Lane-use arrows on every lane: on Chinden northbound left, left-through,
  bike and right; on Eagle southbound dual lefts with U-turn arrows.
- Stop bars, lane-line ends, turn-bay tapers, crosswalk bars and dotted
  left-turn guide lines.
- Mast-arm poles and arms; signal heads countable in the arm's shadow,
  clearest in 2024's low sun.
- Each vehicle with its type, so a per-lane queue snapshot.
- Both ACHD years are leaf-off; NAIP is flown in summer, in leaf.

**Accuracy and uses:**

- NAIP 2023 sits 0.6–1.2 m from ACHD 2025 (template matching at 3 sites);
  2024 lines up with 2025 by eye.
- Calibration points at the stated 0.21 m, about 5 times tighter than NAIP.
- Turn-bay lengths to about ±0.3 m, against ±2–3 m with NAIP.
- **Which year:** 2025 for current striping (and rural areas at 6 inches,
  but undated and uncredited); 2024 for change checks and mast arms (dated
  and credited; its long shadows hide some markings).
- OpenStreetMap doesn't allow tracing from imagery without explicit
  permission ⚠️, so OSM edits from it need ACHD's or COMPASS's OK.
- Under the view-on-request rule we store only our own measurements, each
  noting the source and the date viewed.

**Tile sizes** (2025 samples reprojected to Web Mercator, WebP quality 80,
256-px tiles):

| Zoom | Size per tile | Tiles per km² |
|---|---|---|
| z19 | 7.2 KB | 326 |
| z20 | 4.6 KB | 1,306 |
| z21 | 2.7 KB | 5,222 |

That's 22 MB per km² for z19–21. Plan on twice that: the samples were
mostly pavement and already JPEG-compressed.

**Pull options** if ACHD and COMPASS agree. One 2048×2048 export covers a
156 m square, about 0.65 MB; corridor options add 30% for edge waste.

| Option | km² | z19–21 tiles, GB measured / planned | Exports | Time at one request per 2 s |
|---|---|---|---|---|
| All of Ada at 3 inches | 2,745 | 62 / 123 | 112,700 | 63 h (about 73 GB downloaded) |
| What ACHD has (3 inch to z21, 6 inch to z20) | 1,987 | 26 / 53 | 43,800 | 24 h |
| 150 m either side of the arterials | about 250 | 5.6 / 11 | 13,300 | 7.4 h |
| 300 m around the 453 signals and 228 cameras | 95 | 2.1 / 4.3 | 5,100 | 2.8 h |
| 150 m around the same | 30 | 0.7 / 1.4 | 1,600 | 0.9 h |

The arterial area comes from the Master Street Map: 760 km of existing
arterials plus 318 km with no lane count, so 200–290 km².

**Load on ACHD's server:** a 2048×2048 export probably takes 1.5–3 s (a
1280×1280 one took 0.7–1.2 s), so one request every 2 s keeps one server
instance busy. Waiting 2 s after each response instead roughly doubles the
times (5–6 days for the county). A county-wide pull would copy a product
COMPASS sells, worth about $268k at its list price ⚠️ (from a search
snippet; COMPASS's page answered 403).

## 9.6 Parcels, zoning, land use, addresses

| Source | What | License |
|---|---|---|
| Ada County Assessor | Parcels (32.5 MB, 240k with condos), parcel points, zoning, subdivisions, and parcel characteristics (year built, dwelling units, commercial floor area, plat actions); updated twice a month. Address points come from County IT's hub (275,155) | Owner names removed; **"do not re-distribute"**, while County IT's hub labels the same layers CC0. We follow the stricter rule until the county answers: a private copy on the server (Oct 6, owner OK), aggregates only. |
| City of Boise open data (64 datasets) | Zoning, future land use, development tracker, new housing, pathways, street lights, floodplain | Disclaimer only |
| Canyon County | Tax parcels (110,890, refreshed daily; no year built or use), zoning, future land use 2030, building permits (unincorporated only) | Free to government; centerlines and addresses by records request |
| Idaho statewide public parcels | Ada 217,038 (stale: Apr 2025 extract), **Canyon 0** | Disclaimer and §74-120 (no mailing lists) |
| COMPASS open data | **TAZ demographics** (forecasts to 2055), current land use (305,838 parcels), building permits since 2000, preliminary plats, crash data, counts ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Disclaimer only |

Details below are from the parcels research of Oct 6: 83 requests, at
least 1.2 s apart, honoring Crawl-delay 60 on two hubs. Nampa's city site
blocked us with a Cloudflare page.

### Ada County in detail

**Assessor downloads** (`adacountyassessor.org/public/*.zip`), updated the
2nd and last Wednesday of each month:

- Parcels 32.5 MB, parcel points 10.8 MB, condos 2.1 MB, centerlines
  6.6 MB, subdivisions 3.0 MB, zoning 1.7 MB; also city limits, ZIP codes,
  mobile-home parks and surveys.
- `parcelCharacteristics.zip`, 21.7 MB: 7 DBF tables.
- Coordinates are in a modified Idaho State Plane West (US feet): multiply
  by 0.999820074 for sea-level coordinates.

**Parcel fields:** `PARCEL`, `PROPCODE` (R 182,257, L 36,007, C 11,922,
M 7,976, F 2,204), address parts, `ZONING`, `ACRES`, `TOTALVALUE`,
`HOMEEXEMPT`, `SUBNM`, `CODEAREA`. No year built or unit count; those are
only in the parcel-characteristics tables:

| Table | What it adds |
|---|---|
| `RESICHAR` | `YEARBUILT`, `OCCDATE`, `NOOFDWELLI` (for 1–4-plexes), `RESDESIGN` (condo or townhome), floor areas |
| `COMMCHAR` | `YRBLT`, `UNITS`, `STORIES`, `LEASABLESQ`, `TOTALSQFT`, `GROUP`/`TYPE`, `COMCATCODE`, `BUSNAME` |
| `LANDCHAR` | State category codes; `FRONTAGE`, `CORNER` and `SIDEWALKS`, flagged "may not be accurate" |
| `PARTRACK` | Plat, split and combination actions, with dates |

**Ada County IT's hub:** Parcels `FeatureServer/5` (240,389 with condos),
`Address_Points/21` (275,155), centerline, zoning and subdivisions; 2,000
records a page; refreshed weekly. Labeled CC0-1.0 (item
`c3c3a02008e7433a860938d693eba7b0`; its metadata was rewritten Aug 11,
2026). Boise's server mirrors the parcels and the address points (275,159
points on Oct 5); the parcels research saw no terms there, while the
second source review found the Assessor's notice on the City's "Ada County
Addresses" layer ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)).

**Terms as written:**

- Ada County's GIS User Guide: "for personal and business use in
  accordance with Idaho Code 31-875. This data may not be resold or further
  redistributed." (§31-875 only lets counties charge cost-based fees.)
- The Assessor's download page cites §74-120 (no marketing or mailing
  lists) and says "Do not re-distribute this record; further requests ...
  forwarded to the agency".

### Canyon County and elsewhere

- **Canyon County:** `Assessor/CCPublicTaxparcels` (110,890, daily) and
  `General/Canyon_County_Public_Tax_Parcels` (103,060, older). Fields:
  `PIN`, `ACRES`, `SiteAddress`, `SubName`, `Legal`, full cash values,
  `TaxCode`, `InCity`; no land use, year built or zoning. The full data
  goes by FTP with an emailed login "to domestic government agencies and
  their contractors at no cost".
- **Statewide public parcels:** 13 counties, 380,988 parcels (Ada 217,038,
  stale: Apr 16, 2025; Canyon 0). Its improvements table has 180,120 Ada
  rows with `YEAR_BLD`, `IMP_TYPE`, `TOT_SQFT` and `NUM_STORY`, plus
  `ASR_CATS` categories. Its owner and mailing fields are never to be used.
- **Idaho SSAP / NG911 address points:** none for Ada or Canyon.
- **Nampa's hub** (`gisdata-nampa.hub.arcgis.com`): 28 layers (zoning,
  comprehensive plan, active preliminary and final plats, subdivisions,
  functional class), no parcels; disclaimer only.
- **Caldwell:** no public parcel service found.

### What parcels give a traffic study

- **Trip generators along corridors:** dwelling units (`RESICHAR`, plus
  `COMMCHAR` `UNITS` for apartments) and commercial floor area and type,
  summed in a corridor buffer, give ITE-style trip estimates.
- **Growth:** `YEARBUILT`/`OCCDATE` and `PARTRACK` plat dates give new
  homes per corridor per year.
- **Access density:** parcels per mile addressed on the arterial (adjacency
  overcounts, so cross-check OpenStreetMap driveways).
- **Geocoding:** Ada's address points (CC0 on the hub) beat TIGER's address
  ranges. Canyon County has no public address points.
- **Against COMPASS** (traffic zones, permits, plats, current land use):
  COMPASS covers both counties but is coarser. Parcels add corridor-scale
  detail and built dates, for Ada only; Canyon's growth comes from COMPASS.
- Schools are easier from OpenStreetMap or state lists.

### Handling (proposed Oct 6)

The owner approved the private copy and the aggregates-only rule on Oct 6
([DECISIONS](DECISIONS.md)). The research proposed:

- Copies are dated, with their terms saved beside them; never in tiles,
  exports or git.
- The owner approves each whole-dataset run: at most one zip per needed
  layer, at most twice a month (gentler than the about 121 REST pages that
  240k parcels would take).
- REST only for corridor lookups and server-side `groupBy` statistics
  (aggregates).
- Publish only corridor- or traffic-zone-level aggregates credited
  "Source: Ada County Assessor": no parcel IDs, outlines or addresses, and
  only after the county answers or on the owner's call. If CC0 is
  confirmed, the hub layers are free to use. Owner fields never (§74-120).
- **Questions for the Assessor's Land Records office ((208) 287-7262) and
  AdaCountyGIS:** does CC0 cover the hub's parcel, address and centerline
  layers; does "do not re-distribute" cover published aggregates (for
  example new homes per corridor per year); and the same for the parcel
  characteristics.
- **Canyon County:** use the public REST service internally, and email
  `assr_platroom@canyoncounty.id.gov` about FTP access for non-government
  research (not done yet).
- **Statewide layer:** skip it (stale, and Ada County owns the data).

## 9.7 3D tiles and basemap tiles

| Option | Verdict |
|---|---|
| **Protomaps PMTiles** (OSM) | **Recommended.** Self-hosted single file, no key. Cut a valley extract from the daily planet build with `pmtiles extract --bbox` (the 20261004 planet build is 138.6 GB, v4.15.2, z0–15; builds at maps.protomaps.com/builds, mirrored on Source Cooperative). Attribution: "© OpenStreetMap contributors". |
| OpenMapTiles (Planetiler) | Open alternative; design is CC-BY and needs credit |
| MapTiler / Stadia free tiers | Keys required; non-commercial only; logo required |
| tile.openstreetmap.org | Light development use only; no bulk use |
| Google Photorealistic 3D Tiles | Billing; no caching, analysis or derived content; can't be used next to a non-Google map. **Avoid.** |
| Cesium ion free tier | Not for government projects or funded research. Use only if we stay unfunded. |

### Terms and prices behind the verdicts (Oct 5)

**Google Photorealistic 3D Tiles:**

- Needs billing and an API key. The first 1,000 root-tileset requests a
  month are free, then $6.00 per 1,000 up to 100k, falling to $5.10,
  $4.20, $3.30 and $2.40 per 1,000 above 5 million.
- At most 10,000 root queries a day; one root request opens a session of
  up to 3 hours.
- "must not pre-fetch, index, store, or cache any Content". Banned uses:
  image analysis, machine interpretation, object detection, geodata
  extraction, offline use.
- CesiumJS (with `showCreditsOnScreen`) and Cesium for Unreal are allowed
  renderers.
- Google Maps Platform terms §3.2.3(e): no use "with or near a non-Google
  Map". §3.2.3(c): no derived content (tracing, terrain).

**Cesium ion Community (free):**

- A paid plan is needed above $50K of revenue or funds raised, for a
  "government project", or for "funded educational research".
- Free limits: 10 GB storage, 15 GB a month of streaming, 1,000 Google 3D
  roots and 1,000 imagery sessions a month. Commercial plans from $149 a
  month.

**Others:**

- **MapTiler Free:** 5k sessions and 100k requests a month; for "testing,
  PoC, prototyping, personal, or non-commercial use"; logo required.
- **Stadia Free:** 200k credits a month; "Commercial use not allowed"; no
  satellite imagery.
- **tile.openstreetmap.org:** an identifiable User-Agent and Referer; no
  bulk download or prefetch; "No SLA"; can block without notice.
- **Esri World Imagery:** under Esri's Master License Agreement ("not
  intended to be used to export tiles for offline"); outside ArcGIS it
  needs a Location Platform key, with 2 million basemap tiles a month free,
  then $0.15 per 1,000.
- **OpenMapTiles:** the design is CC BY 4.0 and needs "© OpenMapTiles ©
  OpenStreetMap contributors".

## 9.8 Recommended open, key-free base stack

1. **Basemap:** a Protomaps PMTiles extract of the valley, self-hosted and
   rendered with MapLibre.
2. **Terrain:** terrain-RGB tiles built from the 3DEP 1 m DEM (public
   domain), served as lossless WebP with zoom-dependent rounding (§9.2).
3. **Imagery:** NAIP 2023 by default. ACHD 3-inch only as an on-request
   overlay until terms are confirmed.
4. **Buildings:** Overture with heights, extruded. Boise 3D buildings
   downtown if the City confirms terms.
5. **Network for joining data:** Overture or OSM topology, plus ITD HPMS
   lanes and ACHD Master Street Map lanes. Use COMPASS `pm_id` to tie into
   travel-model and crash data.
6. **Context:**
   - COMPASS TAZ and land use, Boise zoning, Census.
   - Ada Assessor data for internal use only.
7. **Later, for true 3D (not in v1):** stream 3DEP LiDAR point clouds
   (EPT/COPC) into Cesium or deck.gl. Version 1 is 2.5D (owner decision,
   Oct 5).

**License notes:**

- **ODbL (OSM and Overture):** credit OSM contributors. Any derived
  *database* we publish must also be ODbL. Maps and images we publish only
  need the credit. In more detail (Oct 5 terms research and the Oct 6
  ingestor plan):
  - §4.3: a publicly used Produced Work (maps, charts, papers, tiles) needs
    only a notice. Tiles we publish are Produced Works: credit, and offer
    the derivative database behind them.
  - §4.4: a publicly used Derivative Database must be ODbL.
  - §4.5(c): internal use is exempt. The plan's working rule: use only on
    the tailnet is not public use.
  - §4.6: we must offer the derivative database, or a description of the
    changes.
  - OpenStreetMap is kept in its own tables (`core.osm_way`,
    `core.osm_lane`, `core.osm_node`), so the ACHD, ITD and COMPASS tables
    beside it form a collective database and aren't pulled into ODbL.
  - "Best-of" tables that mix in OpenStreetMap (`core.segment_lanes`,
    `core.intersection`) are derivative databases: offer them under ODbL
    if used publicly.
  - The OSM Foundation's Collective Database guideline (2016): linking our
    own table to OSM IDs without copying OSM data into it doesn't trigger
    share-alike. That suits travel times keyed to OSM ways.
- **Overture's upstream credits** include Esri Community Maps and Google
  Open Buildings (both CC BY 4.0); our credits should carry them.
- **ITD:** credit ITD.
- **AWS Terrain Tiles,** if used: the tilezen/joerd attribution.
- **Public domain (USGS, NAIP, Census):** no conditions.

## 9.9 Not yet verified

- OSM lane and signal coverage quality.
- Terms for ACHD's hub, imagery and Master Street Map (none found: no terms
  page, and the imagery's license fields are empty or a disclaimer).
- Terms for Boise 3D Buildings, and whether they come from COMPASS's paid
  2019 LiDAR.
- ISU DTM resolution and terms.
- INSIDE Idaho's terms: `data.insideidaho.org` was blocked by the cloud
  sandbox's proxy (502) on Oct 5.
- Mapterhorn high-zoom coverage over Boise.
- Size of a valley PMTiles extract (since built: 38 MB, z0–15, Oct 5;
  [basemap/README](../basemap/README.md)).
- Whether the Overpass mirror `overpass.private.coffee` may be used for
  scripted OpenStreetMap pulls (§9.3).
