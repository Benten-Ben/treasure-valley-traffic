# 9. Base-map data: building our own map of the valley

What's available to build a fully owned 2D/3D map of Ada and Canyon counties:
terrain, LiDAR, streets, lanes, buildings, imagery and parcels, along with
the licenses. Research as of Oct 5, 2026. Items marked ✅ were spot-checked
directly; the rest come from the research pass and should be re-checked
before relying on them.

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

USGS 3D Elevation Program (3DEP) coverage, by the 3DEP index at each city:

| Area | LiDAR project | Quality | Flown | Published |
|---|---|---|---|---|
| Boise, Meridian, Eagle, Star, Kuna, Caldwell, Parma | `ID_SouthernGaps_2_D23` | QL1 (8+ points/m²) | 2023-09 to 2024-08 | Point cloud Dec 2025–Jan 2026; 1 m DEM Apr 2026 |
| Nampa, Melba | `ID_SouthernID_21_2018` | QL2 (2+ points/m²) | 2019-10 to 2020-08 | 1 m DEM May 2024 |
| Also present | `ID_FEMAHQ_2018` (partial Boise area), `NV_USFSR4_4_D23` (foothills), legacy 2003–2009 sets | | | |

| Product | Format | Size for the valley | License | Where |
|---|---|---|---|---|
| ✅ **1 m DEM** | Cloud-optimized GeoTIFF, 10 km tiles (sample tiles 20–83 MB) | About 168 tiles, about 32 GB | Public domain | `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1m/Projects/<project>/TIFF/` (public, no key) |
| 1/3 arc-second (about 10 m) DEM | COG | 411 MB per 1° tile (`n44w117`) | Public domain | `prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/` |
| LiDAR point clouds | LAZ 1.4 (2023–24); streamable EPT on AWS for the 2018–20 project only | About 160 GB (2023–24 tiles in the box) | Public domain | TNM downloader / `tnmaccess.nationalmap.gov` API; `s3://usgs-lidar-public/ID_SouthernID_21_2018/ept.json` |
| 3DEP dynamic elevation service | Esri ImageServer | On demand | Public domain | `elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer` |
| Idaho LiDAR Consortium / ISU statewide DTM | Zipped rasters per 15′ quad | 3.6–4.7 GB per quad | Terms not found | idaholidar.org |
| COMPASS 2019 LiDAR | Point cloud + ground TIFF | — | **Paid** ($220 per cell) | compassidaho.org/orthophotography |

**Terrain tiles for the web map:**

- **Best:** build our own from the 1 m DEM (terrain-RGB for MapLibre, or
  quantized-mesh for Cesium). It's the most accurate and stays public
  domain.
- **Quick start:** AWS Terrain Tiles (free; last updated 2017) or Mapterhorn
  (open PMTiles).
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
| **OpenStreetMap** (Geofabrik Idaho) | Full street map with tags (lanes and turn lanes where mapped) | .osm.pbf, 123 MB | ODbL | download.geofabrik.de/north-america/us/idaho.html. Its robots.txt disallows automated downloads of every extract format, the update diffs and the checksums (checked Oct 6): loaded from a hand download until Geofabrik answers ([DECISIONS](DECISIONS.md)) |
| **Overture Maps transportation** (release 2026-09-23.1) | 173,146 road segments in the valley box; speed limits on about 14k; stable IDs across releases; no lane-count field | GeoParquet (query in place) | ODbL | `s3://overturemaps-us-west-2/release/2026-09-23.1/theme=transportation/` |
| ✅ **ITD HPMS** (federal highway inventory) | **Through lanes** by direction (19,801 records in the box, Oct 6), turn lanes (637, samples), lane width (92% the 12 ft default), median, shoulders, access control. Good on state routes; looks like defaults on ACHD arterials (Fairview Ave reads 1+1; it has 5 lanes). HPMS calls Chinden undivided: 1+1 for 12.5 km, 2+2 for 11.6 km (an earlier reading of its A and D routes as two disagreeing carriageways was wrong: on an undivided state route the D route is a placeholder on the A route's line, Oct 6) | Esri FeatureServer | Credit ITD | `gisp.itd.idaho.gov/server/rest/services/GDWarehouse/HPMS/FeatureServer/25` (through) and `/27` (turn) |
| ITD road network (linear referencing system, LRS) | State system plus local roads, interchanges | FeatureServer | Credit ITD | `.../GDWarehouse/RoadNetwork_Primary/FeatureServer` |
| ACHD Master Street Map | Arterials and collectors with **existing, funded and planned lanes**, typology, parking (1,049 arterial segments). Lanes count the whole cross-section (5 = 2+2 plus a centre turn lane ⚠️); blank on state routes | FeatureServer | None stated | `gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Master_Street_Map_Arterials/FeatureServer/1` |
| COMPASS RegionalCenterline | Ada + Canyon centerlines (62,213) with `pm_id`, which links to the travel model and crash data; posted speed and **lanes**, so it covers Canyon County | FeatureServer (hub) | Disclaimer only | COMPASS open-data hub |
| Ada County Assessor centerlines | With address ranges; updated twice a month | Shapefile, 6.6 MB | **"Do not re-distribute"** | `adacountyassessor.org/public/roadcenterline.zip` |
| Canyon County roads | Street names and types only | FeatureServer | Full data by records request | `maps.canyoncounty.id.gov/arcgisserver/.../CanyonCountyRoads/FeatureServer/0` |
| Census TIGER/Line 2025 | Roads with address ranges | Shapefile (2.4 + 1.5 MB) | Public domain | `www2.census.gov/geo/tiger/TIGER2025/ROADS/` |

**Lanes: which source wins where** (owner, Oct 6, 2026). No source is good
everywhere: OpenStreetMap has `lanes` on 72% of major roads in the box and
`turn:lanes` on about 40% of signal approaches (May 2026 data ⚠️), and no
source has widths worth using. Each source's values are kept per segment,
and every lane number shown says where it came from:

| Roads | Through lanes | Turn lanes at signals | Width |
|---|---|---|---|
| State, US and interstate routes | ITD HPMS; OpenStreetMap as a check, disagreements flagged | OpenStreetMap, then COMPASS's right-turn lanes and phasing, then HPMS | Class defaults, marked estimated |
| ACHD arterials (Ada) | Master Street Map; OpenStreetMap for the split by direction; HPMS last | OpenStreetMap, then COMPASS | Defaults |
| Canyon County arterials | OpenStreetMap, then COMPASS's centerline lanes, then HPMS | OpenStreetMap, then COMPASS | Defaults |
| Collectors and local streets | OpenStreetMap where tagged, otherwise assumed 1+1 | — | Defaults |
| Planned changes | Master Street Map funded and planned lanes; ACHD's 574 planned intersection projects | | |

OpenStreetMap stays in its own tables (ODbL); a combined lanes view that
uses it is a derivative database if it's ever published.

## 9.4 Buildings

| Source | Count | Heights | License | Where |
|---|---|---|---|---|
| **Overture buildings** | 347,652 in the valley box | **83% have height** (mostly Microsoft ML) | ODbL | `s3://overturemaps-us-west-2/release/2026-09-23.1/theme=buildings/type=building/` |
| ✅ **Boise 3D Buildings** | 135,710 (Boise area) | Height, roof form, base elevation (from 2019 LiDAR) | **None stated**; ask the City | `services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Boise_Buildings_3D/FeatureServer/0` (3D multipatch) |
| Microsoft US footprints | 942,132 statewide | Not in US release | ODbL | minedbuildings.z5.web.core.windows.net |
| OSM buildings | Included in Overture | Where tagged | ODbL | Geofabrik |

## 9.5 Imagery

| Source | Coverage | Resolution | License | Notes |
|---|---|---|---|---|
| **NAIP 2025** (found Oct 6) | Whole valley (270 quarter-quads in the box), flown May 25–Jul 24, 2025 | **0.3 m**, 4-band | Public domain; USDA asks to be credited in derived products | Not yet on Planetary Computer. USDA's image service `apps.geo.fpac.usda.gov/geo-imagery/rest/services/naip/conus_naip/ImageServer` (no key; `exportImage` up to 15000×4100), an Idaho State University mirror, and county mosaics on USDA's Box (Ada 4.8 GB, Canyon 4.3 GB; probably MrSID). Lane lines, stop bars and crosswalk bars are crisp; mast arms mostly as shadows; ±4 m absolute spec ⚠️ (about 1.5 m at one site; 0.85 m from NAIP 2023 at Eagle & Fairview). The sharpest free option. **In use since Oct 6** for the detail layer: 250 m around the 228 cameras and 150 m around COMPASS's 585 signals, z15–18, exported from USDA's image service (1,232 exports, one at a time, 2.5 s apart; `imagery.py --detail-source usda`). The whole valley at 0.3 m waits for the county files (see Pending in DECISIONS). |
| **NAIP 2023** | Whole valley | 0.6 m, 4-band | Public domain | Cloud-optimized GeoTIFFs on Microsoft Planetary Computer (free). AWS copy is requester-pays. Our base map's valley-wide aerial layer (to z14). |
| ACHD Ada County Imagery 2024/2025 | **Ada only**: 2024 the urban core (780 km², 3 inch, Apr 1–2, 2024); 2025 about 72% of Ada (3 inch in 267 sections, 6 inch in 500; undated, probably April 2025) | **3 inch** | **None stated**; really COMPASS's product (flown by GeoTerra "for use by the COMPASS members") | ImageServer; `exportImage` works, no tile cache. Shows lane arrows, stop bars and mast arms that NAIP doesn't. **View on request only** (owner, Oct 6); asked of ACHD and COMPASS. If they agree: a private copy of 300 m around signals and cameras only (about 95 km², 2–4 GB, one overnight fetch); not the whole county (50–120 GB, a product COMPASS sells). |
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

## 9.6 Parcels, zoning, land use, addresses

| Source | What | License |
|---|---|---|
| Ada County Assessor | Parcels (32.5 MB, 240k with condos), parcel points, zoning, subdivisions, and parcel characteristics (year built, dwelling units, commercial floor area, plat actions); updated twice a month. Address points come from County IT's hub (275,155) | Owner names removed; **"do not re-distribute"**, while County IT's hub labels the same layers CC0. We follow the stricter rule until the county answers: a private copy on the server (Oct 6, owner OK), aggregates only. |
| City of Boise open data (64 datasets) | Zoning, future land use, development tracker, new housing, pathways, street lights, floodplain | Disclaimer only |
| Canyon County | Tax parcels (110,890, refreshed daily; no year built or use), zoning, future land use 2030, building permits (unincorporated only) | Free to government; centerlines and addresses by records request |
| Idaho statewide public parcels | Ada 217,038 (stale: Apr 2025 extract), **Canyon 0** | Disclaimer and §74-120 (no mailing lists) |
| COMPASS open data | **TAZ demographics** (forecasts to 2055), current land use (305,838 parcels), building permits since 2000, preliminary plats, crash data, counts ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Disclaimer only |

## 9.7 3D tiles and basemap tiles

| Option | Verdict |
|---|---|
| **Protomaps PMTiles** (OSM) | **Recommended.** Self-hosted single file, no key. Cut a valley extract from the daily planet build with `pmtiles extract --bbox`. Attribution: "© OpenStreetMap contributors". |
| OpenMapTiles (Planetiler) | Open alternative; design is CC-BY and needs credit |
| MapTiler / Stadia free tiers | Keys required; non-commercial only; logo required |
| tile.openstreetmap.org | Light development use only; no bulk use |
| Google Photorealistic 3D Tiles | Billing; no caching, analysis or derived content; can't be used next to a non-Google map. **Avoid.** |
| Cesium ion free tier | Not for government projects or funded research. Use only if we stay unfunded. |

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
  need the credit.
- **ITD:** credit ITD.
- **Public domain (USGS, NAIP, Census):** no conditions.

## 9.9 Not yet verified

- OSM lane and signal coverage quality.
- Terms for ACHD's hub, imagery and Master Street Map.
- Terms for Boise 3D Buildings.
- ISU DTM resolution and terms.
- Mapterhorn high-zoom coverage over Boise.
- Size of a valley PMTiles extract.
