# Gardening sources (researched Oct 7, 2026)

Data for the proposed `gardening` plugin ([chapter 15](../15-plugins.md),
§15.7) and the gardener persona in
[chapter 16](../16-ideas-and-personas.md#gardener-new-oct-7): sun and shade
hours per spot (the sun's path plus buildings, lidar tree canopy and
terrain), frost dates and the growing season, hardiness zones, soils,
evapotranspiration (ET) and watering, irrigation-water seasons, heat and
smoke days, and a private "my yard" view of the owner's own place. Several
of these sources also serve other personas (shade at bus stops and on bike
routes, hazards, sky, farm). The overview of sources for all the new
plugins is in [chapter 17](../17-sources-for-new-plugins.md).

**Status: research only; nothing here is approved.** Each source goes to
the owner one at a time before anything is built
([SOURCES.md](../SOURCES.md), [DECISIONS.md](../DECISIONS.md)). On Oct 7,
2026 a second pass checked every entry against the publisher's official
pages, its robots.txt (fetched again with the project's User-Agent) and its
terms. The **Verified** column gives the result: confirmed (14), corrected
(17; the text below is the corrected version) or unverifiable (1). One
researcher claim was refuted outright: AgriMet's ET history does not need
the robots-disallowed `/pn-bin`. Web search wasn't available to the
checker, so facts that rest only on search snippets, secondary sites or
memory stay marked ⚠️. **Verdict** is the research recommendation (use,
avoid, or needs an owner action), not a decision.

How it was checked: the researcher's sample requests were all small,
keyless, allowed by robots.txt and spaced 2–3 s apart: 2 Planetary
Computer STAC searches, 1 ISU ImageServer catalog query, 2 ACIS `StnData`
calls, 2 Soil Data Access queries (one malformed, so no data), 2 HEAD
checks of the lidar EPT on S3, and 1 GET of an AgriMet chart plus 4 HEAD
and 2 GET checks of chart files. The checker re-fetched every robots.txt,
read the docs and terms pages, and made three small keyless requests (one
more than its brief's "one or two"): an S3 prefix listing of
`usgs-lidar-public` for `ID_`, one GET of the QL2 `ept.json` (2.5 KB) and
one STAC search over central Boise.

"The ring" below is the proposed regional ring around Ada and Canyon
([DECISIONS](../DECISIONS.md), "How far the study area reaches").

---

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| **Shade: lidar, canopy and the sun** | | | | | | | | |
| [USGS 3DEP lidar point clouds](https://s3-us-west-2.amazonaws.com/usgs-lidar-public/ID_SouthernID_21_2018/ept.json) (QL1 2023–24, QL2 2019–20) | USGS 3D Elevation Program | Classified points: canopy and roof heights, a surface model for shadows | QL2: streamable EPT on S3. QL1: LAZ tiles through TNM (about 162 GB) | None | Public domain | S3: none. rockyweb.usgs.gov unreachable, treated as disallowed | Use | Corrected |
| [Planetary Computer 3DEP height above ground and DSM](https://planetarycomputer.microsoft.com/api/stac/v1/collections/3dep-lidar-hag) | Microsoft Planetary Computer (from USGS 3DEP) | 2 m height above ground and DSM, 2012–2022 | STAC API | None | STAC says "proprietary"; the lidar itself is public domain | No rules | Avoid (no coverage over Boise) | Confirmed |
| [ISU lidar DSM ImageServer](https://giscenter.rdc.isu.edu/server/rest/services/Lidar/DigitalSurfaceModel_DSM/ImageServer) | ISU GIS Training and Research Center, Idaho Lidar Consortium | Statewide 1 m highest-hit surface model | Esri ImageServer, no tile export | None | None stated | 404 (no rules) | Avoid | Confirmed |
| [Meta/WRI Canopy Height Maps v2](https://registry.opendata.aws/dataforgood-fb-forestsv2) | Meta (Data for Good) and World Resources Institute | About 1 m canopy height predicted from satellite imagery | S3, unsigned | None | CC BY 4.0 | Not applicable (S3) | Use (gap fill) | Corrected |
| [City of Boise Tree Canopy Assessment 2013–2021](https://cityofboise.org/media/19160/boise-tree-canopy-assessment-2013-2021-final-20240910.pdf) | City of Boise, Treasure Valley Canopy Network | Canopy and 7-class land cover for Boise | Report PDF; the 2021 land cover isn't published | Unknown | Report: none stated; hub: city disclaimer | Allowed (open-data hub: Crawl-delay 60) | Needs owner action | Confirmed |
| [Sun-position algorithms](https://github.com/mourner/suncalc) (suncalc, NOAA equations, SPA) | suncalc, pvlib, NOAA, National Laboratory of the Rockies (formerly NREL) | Sun azimuth and elevation, sunrise and sunset | Libraries or our own port | None | suncalc BSD-2; NOAA public domain; SPA code can't be redistributed | Not applicable | Use | Corrected |
| [NSRDB](https://registry.opendata.aws/nrel-pds-nsrdb/) (National Solar Radiation Database) | National Laboratory of the Rockies (formerly NREL), DOE | Satellite irradiance, cloud type, typical years | S3 unsigned; API needs a free key | None (S3); free key (API) | CC BY 3.0 US | S3: none. API hosts: no rules | Use | Corrected |
| **Frost, growing season and hardiness** | | | | | | | | |
| [NCEI U.S. Climate Normals 1991–2020](https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals) | NOAA NCEI | Freeze probabilities, growing season, degree-day normals by station | Access Data Service; bulk CSVs by hand only | None | U.S. Government; no restrictions | `/data*` disallowed; the data service allowed | Use | Confirmed |
| [RCC-ACIS web services](https://www.rcc-acis.org/docs_webservices.html) | NOAA Regional Climate Centers | Station data, each year's freeze dates, degree days, PRISM grid | JSON POST | None | None stated; NOAA data U.S. Government | No rules | Use | Confirmed |
| [PRISM 1991–2020 normals](https://prism.oregonstate.edu/normals/) | PRISM Group, Oregon State University | 800 m and 4 km gridded normals and daily series | Normals by hand; daily grids one file per request (twice-in-24-h limit) | None | Free to reproduce and distribute, with credit | 404 (no rules) | Use | Corrected |
| [2023 USDA Plant Hardiness Zone Map](https://prism.oregonstate.edu/phzm/) | USDA-ARS and PRISM Group, OSU | Half-zone grid, shapefile, KML, ZIP-code table | One hand download | None | Free to redistribute with both logos; altered maps need a disclaimer and no logos | 404 (no rules) | Use | Confirmed |
| **Soils** | | | | | | | | |
| [NRCS SSURGO via Soil Data Access](https://sdmdataaccess.nrcs.usda.gov/WebServiceHelp.aspx) | USDA NRCS | Texture, pH, drainage, water capacity, depth to hardpan | SQL over REST; WFS and WMS; gSSURGO by hand | None | Public domain | SDA: 404. nrcs.usda.gov disallows query URLs | Use | Corrected |
| **Water: ET, rain and canal seasons** | | | | | | | | |
| [AgriMet crop water-use charts](https://www.usbr.gov/pn/agrimet/chart/pmaich.txt) | U.S. Bureau of Reclamation | Daily crop ET (with LAWN) at valley stations; yearly ET history | Static text files | None | U.S. Government; provisional | `/pn/agrimet/chart/` allowed | Use | Corrected |
| [AgriMet and Hydromet station data](https://www.usbr.gov/pn/agrimet/general.html) | U.S. Bureau of Reclamation | Weather, soil temperature, reservoir and canal history | `/pn-bin` CGI and the RISE API | None | U.S. Government; provisional | Disallowed | Needs owner action | Corrected |
| [gridMET](https://www.climatologylab.org/gridmet.html) | Climatology Lab (UC Merced; originally University of Idaho) | 4 km daily weather and reference ET from 1979 | NetCDF per variable and year | None | Copyright waived (CC0-style); cite Abatzoglou (2013) | File host: no rules. THREDDS: all disallowed | Use | Confirmed |
| [ET-IDWR](https://et-idwr.idaho.gov/) | Idaho Department of Water Resources with University of Idaho | ET and net irrigation need for 212 stations | Station pages; format unstated | None | IDWR disclaimer | Redirect to an error page (no rules) | Use | Corrected |
| [OpenET](https://etdata.org/terms-of-service/) | OpenET | 30 m field ET | API with account and key | Account | Personal, noncommercial; outputs claimed as OpenET's property | API: all disallowed | Avoid | Confirmed |
| [CoCoRaHS](https://www.cocorahs.org/) (through ACIS) | CoCoRaHS (Colorado State University) | Volunteer daily rain, snow and hail | Through ACIS | None | CC BY 4.0 | `/viewdata/` disallowed (we use ACIS) | Use | Corrected |
| [IDWR Irrigation Organizations](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/0) | Idaho Department of Water Resources | Service areas of irrigation districts and canal companies | ArcGIS FeatureServer | None | Credit IDWR; disclaimer | Redirect to an error page (no rules) | Use | Corrected |
| [Irrigation season announcements](https://nmid.org/2025-season-start-up/) | Irrigation districts and cities | Canal turn-on and shutoff dates | Read by hand, entered with the source | None | Public notices; we record dates with citations | Mostly allowed; Nampa by hand only | Use | Corrected |
| [Water District 63 diversions](https://idwr.idaho.gov/wr-administration/water-rights-accounting/wd63/) | Boise River watermaster; IDWR | Canal diversions; annual accounting reports | No public feed; PDFs by hand | Partnership | Telemetry unknown; PDFs none stated | idwr.idaho.gov allowed | Needs owner action | Unverifiable |
| **Phenology, pests and planting guides** | | | | | | | | |
| [USA National Phenology Network maps](https://usanpn.org/data/maps) | USA-NPN (USGS-supported) | Growing degree days, Spring Index, pest forecasts | GeoServer WMS/WCS | None | CC BY 4.0; terms ban automated access without written approval | GeoServer: 404 | Needs owner action | Corrected |
| [USPEST.org](https://uspest.org/) | OSU Integrated Plant Protection Center | Degree-day and pest models | Web calculators | None | Not checked | Model and data paths disallowed | Avoid | Confirmed |
| [ISDA Japanese beetle program](https://agri.idaho.gov/idaho-japanese-beetle/) | Idaho State Department of Agriculture | Caldwell program area and treatment dates | Web pages, PDFs, ArcGIS viewer; by hand | None | None stated | Empty (no rules) | Use | Corrected |
| [University of Idaho Extension publications](https://www.uidaho.edu/extension/publications/bul-0965) | University of Idaho Extension | Planting guide (BUL 965) | Link only | None | © University of Idaho; link, never copy | Allowed | Use | Confirmed |
| **Heat, smoke, air and alerts** | | | | | | | | |
| [NOAA Hazard Mapping System smoke](https://www.ospo.noaa.gov/products/land/hms.html) | NOAA NESDIS OSPO | Smoke polygons with density; fire points; since 2002 | Daily shapefile, KML, text | None | U.S. Government | 404 (no rules) | Use | Confirmed |
| [EPA AirData files](https://aqs.epa.gov/aqsweb/airdata/download_files.html) | U.S. EPA | Daily AQI by county; PM2.5 and ozone by monitor, 1980–2026 | Zipped CSV per year | None | U.S. Government | 404 (no rules) | Use | Corrected |
| [AirNow API](https://docs.airnowapi.org/) | U.S. EPA and partners | Current and forecast AQI | REST | Free key | Preliminary; not for trends | 4xx (no rules) | Needs owner action | Confirmed |
| [NWS API](https://api.weather.gov/robots.txt) (api.weather.gov) | NOAA National Weather Service | Alerts, forecasts, observations | REST | None | U.S. Government | `Disallow: /` for all | Avoid | Confirmed |
| [NWS text products on tgftp](https://tgftp.nws.noaa.gov/data/watches_warnings/) | NOAA National Weather Service | Frost, freeze and heat warnings as text | HTTPS directory | None | U.S. Government | No rules | Use | Confirmed |
| [Landsat Collection 2 surface temperature](https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2) | USGS, hosted by Microsoft Planetary Computer | Land surface temperature on a 30 m grid since 1982 | STAC plus signed COGs | None | Public domain (STAC says "proprietary") | No rules | Use | Corrected |
| [Boise urban heat studies](https://www.boisestatepublicradio.org/show/idaho-matters/2025-08-05/boise-urban-heat-treasure-valley-climate-change) | City of Boise Climate Action, TVCN, CAPA Strategies, Center for Regenerative Solutions | Neighborhood air-temperature studies (2019, 2024, 2025) | No data found | Unknown | Unknown | Not applicable yet | Needs owner action | Corrected |

Totals: 21 use, 6 need an owner action, 5 avoid.

---

## Shade: lidar, canopy and the sun

### USGS 3DEP lidar point clouds

Use · corrected · effort L · confidence high

- **Contents:** classified point clouds from two projects: QL1
  `ID_SouthernGaps_2_D23` (8+ points/m², flown Sep 2023 to Aug 2024) and
  QL2 `ID_SouthernID_21_2018` (2+ points/m², flown Oct 2019 to Aug 2020).
  The QL2 EPT holds 39,863,694,659 points; its schema includes
  `Classification`, `ClassFlags`, `ReturnNumber`/`NumberOfReturns` and
  `GpsTime`, so acquisition dates can be recovered per point. Gives canopy
  height, roof shape and height, and a surface model for shadows.
- **Classes delivered:** unverified. The claim that only the Lidar Base
  Specification's minimum classes exist (no vegetation or building
  classes) rests on report snippets ⚠️; the project report's host was
  unreachable. The base specification lists classes 3–6 (vegetation and
  buildings) as optional upgrades.
- **Coverage:** [chapter 9](../09-base-map-data.md)'s index puts QL1 over
  Boise, Meridian, Eagle, Star, Kuna, Caldwell and Parma, and QL2 over
  Nampa and Melba. The QL2 EPT's bounds (about −117.04 to −115.99,
  42.62 to 43.82) span the whole valley box, but bounds aren't coverage:
  whether QL2 also has points under the QL1 cities is unconfirmed. Check
  the WESM index polygons before planning a QL2-first pass or any change
  detection.
- **Endpoint:** QL2: Entwine Point Tiles at
  `s3://usgs-lidar-public/ID_SouthernID_21_2018/ept.json` (us-west-2,
  keyless; GET 200 on Oct 7). QL1 has no EPT copy: a prefix listing of the
  bucket for `ID_` shows 31 Idaho EPTs and no SouthernGaps. QL1 comes as
  LAZ 1.4 tiles through TNM.
- **Updates:** static per acquisition, years apart.
- **Size:** QL1 is about 3,180 tiles, 162 GB of LAZ for the box
  (chapter 9). Derived height-above-ground (nDSM) tiles for about
  1,000 km² of urban area: probably 1–4 GB rather than the first guess of
  0.5–1 GB ⚠️ (estimate; see [the review's corrections](#review-corrections-to-the-design)).
- **License:** public domain (USGS). A comment in
  api.waterdata.usgs.gov/robots.txt says USGS data "are considered to be in
  the U.S. Public Domain".
- **robots.txt:** none for the S3 bucket (object storage). rockyweb.usgs.gov
  refused connections again on Oct 7, so it's treated as disallowed for
  now.
- **Use cases:** a canopy height model for tree shade; building heights
  where Overture lacks them (17%; chapter 9 has 83% with heights) or has
  them wrong; surface-model tiles for shadows and sun hours in the browser;
  3D trees shared with the land-cover idea (chapter 16, §16.3); canopy
  change 2019–20 against 2023–24, only where both projects overlap and with
  error bars.
- **Personas:** gardener, homeowner, urban forester, transit rider,
  cyclist, sky watcher.
- **Core pieces:** surface-model tiles (proposed core, `basemap/`), the 3D
  engine, the layer system.
- **Effort and risks:** large. The QL1 download is a big run and needs the
  owner's OK. Both flights were partly leaf-off, so canopy is undercounted;
  check dates per tile from `GpsTime`. Comparing QL2 with QL1 mixes 2 and
  8 points/m²: sparse data misses treetops, which biases apparent growth
  upward. PDAL (BSD) would join the build tools. Point clouds show backyard
  structures in detail, so derived products are never joined to owners or
  addresses.
- **Verification:** confirmed the EPT (GET 200, point count, schema), the
  missing SouthernGaps EPT, the license and the unreachable rockyweb.
  Corrected: "QL2 covers Nampa and Melba only" describes the index's top
  project, not necessarily where the points are; added the leaf-off and
  density caveats. Unverifiable: the class list.
- **Evidence:** [QL2 ept.json](https://s3-us-west-2.amazonaws.com/usgs-lidar-public/ID_SouthernID_21_2018/ept.json),
  [bucket listing for `ID_`](https://s3-us-west-2.amazonaws.com/usgs-lidar-public/?list-type=2&prefix=ID_&delimiter=/),
  [Lidar Base Specification appendix 7](https://www.usgs.gov/ngp-standards-and-specifications/lidar-base-specification-appendix-7-common-data-upgrades),
  project report (unreachable on Oct 7:
  `rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/metadata/ID_SouthernID_2018_D19/USGS_ID_SouthernID_2018_D19_Project_Report.pdf`),
  [chapter 9](../09-base-map-data.md).

### Planetary Computer 3DEP height above ground and DSM

Avoid · confirmed · effort S · confidence high

- **Contents:** 2 m height-above-ground rasters (made from COPC with PDAL
  `filters.smrf` and `filters.hag_nn`) and a DSM, 2 m. Temporal extent
  2012-01-01 to 2022-01-01. The collection names Landrush, USGS and
  Microsoft as providers (the researcher had said Hobu).
- **Coverage:** none over central Boise. A STAC search of `3dep-lidar-hag`
  and `3dep-lidar-dsm` over −116.22, 43.58, −116.18, 43.63 returned 0 items
  on Oct 7, from both the researcher and the checker. The 2023–24 QL1
  flight is outside its time range.
- **Endpoint:** the STAC API, keyless search.
- **Updates and size:** static; not applicable.
- **License:** the STAC license field says "proprietary"; the source lidar
  is public domain USGS data. Not pursued.
- **robots.txt:** planetarycomputer.microsoft.com: `User-agent: *` with no
  rules (rechecked Oct 7).
- **Use case:** would have been a ready-made canopy height model.
  **Persona:** gardener. **Core pieces:** none.
- **Effort and risks:** small, but there's no useful coverage; build our
  own from the point clouds.
- **Verification:** collection metadata confirmed (license, extent, 2 m,
  `hag_nn`); the independent search agreed.
- **Evidence:** [collection](https://planetarycomputer.microsoft.com/api/stac/v1/collections/3dep-lidar-hag),
  [STAC search](https://planetarycomputer.microsoft.com/api/stac/v1/search),
  [robots.txt](https://planetarycomputer.microsoft.com/robots.txt).

### ISU lidar Digital Surface Model (ImageServer)

Avoid · confirmed · effort S · confidence medium

- **Contents:** a statewide assemblage of 1 m highest-hit surface models
  (the item info says it holds all lidar DSM data available in Idaho; last
  updated May 2026), in Idaho Transverse Mercator (WKID 102605 / 8826),
  NAVD88. The service metadata doesn't say which project or year each cell
  comes from.
- **Coverage:** statewide; vintage per cell unknown.
- **Endpoint:** Esri ImageServer with Image, Metadata, Catalog and
  Mensuration; maximum export 10,000 × 4,100 pixels; `exportTilesAllowed`
  false.
- **Updates:** irregular (last May 2026). **Size:** not applicable.
- **License:** none stated: `copyrightText`, `licenseInfo` and
  `accessInformation` are empty.
- **robots.txt:** giscenter.rdc.isu.edu returns 404 (no rules).
  giscenter.isu.edu blocks only named bots (Titan, EmailCollector,
  EmailSiphon and others).
- **Use case:** a quality check of our own surface model in a few cells.
  **Persona:** gardener. **Core pieces:** none.
- **Effort and risks:** small. Our own 3DEP-derived surface model (public
  domain, known dates) supersedes it, and it has no license.
- **Verification:** service JSON and item info re-read; limits,
  capabilities, no tile export, empty license fields and the May 2026
  update all match. The researcher's six quarter-quad catalog hits were not
  re-queried.
- **Evidence:** [service JSON](https://giscenter.rdc.isu.edu/server/rest/services/Lidar/DigitalSurfaceModel_DSM/ImageServer?f=pjson),
  [item info](https://giscenter.rdc.isu.edu/server/rest/services/Lidar/DigitalSurfaceModel_DSM/ImageServer/info/iteminfo?f=pjson),
  [robots.txt (rdc)](https://giscenter.rdc.isu.edu/robots.txt),
  [robots.txt (giscenter)](https://giscenter.isu.edu/robots.txt).

### Meta/WRI Canopy Height Maps v2 (and v1)

Use · corrected · effort M · confidence medium

- **Contents:** global canopy height at about 1 m, predicted from Vantor
  (formerly Maxar) satellite imagery with a DINOv3 model. Meta's blog gives
  R² 0.86 for v2 against 0.53 for v1. The registry says v2 ships GeoTIFFs
  and GeoJSON files with the observation date, so imagery dates are
  available per tile. The "© 2016 Vantor" line is a copyright notice, not
  the acquisition date.
- **Coverage:** global, including Ada, Canyon and the ring.
- **Endpoint:** v2:
  `s3://dataforgood-fb-data/forests/v2/global/dinov3_global_chm_v2_ml3/`
  (us-east-1, no AWS account, `--no-sign-request`). v1:
  `s3://dataforgood-fb-data/forests/v1/alsgedi_global_v6_float/`. Also on
  Google Earth Engine.
- **Updates:** versioned releases (v1 2024, v2 Mar 10, 2026); the registry
  says "TBD".
- **Size:** a clip of the box is probably a few GB ⚠️ (estimate).
- **License:** CC BY 4.0. Credit Meta and WRI, plus the Vantor imagery
  line.
- **robots.txt:** not applicable (S3 bucket).
- **Use cases:** fill canopy where QL1 was flown leaf-off; cross-check the
  lidar canopy; quick canopy for the ring outside QL1.
- **Personas:** gardener, urban forester, wildlife.
- **Core pieces:** surface-model tiles (proposed core).
- **Effort and risks:** medium. These are model predictions with errors of
  metres. Read the observation dates from the GeoJSON before use, and label
  fills as estimated. Secondary to lidar.
- **Verification:** confirmed the S3 paths, region, unsigned access,
  CC BY 4.0, the release date and the R² figures (Meta's blog). Corrected:
  v2 includes observation dates, so "dates per pixel uncertain" was too
  pessimistic; the imagery provider is Vantor.
- **Evidence:** [registry (v2)](https://registry.opendata.aws/dataforgood-fb-forestsv2),
  [registry (v1)](https://registry.opendata.aws/dataforgood-fb-forests/),
  [Land and Carbon Lab](https://landcarbonlab.org/data/global-tree-canopy-height),
  [Meta blog](https://ai.meta.com/blog/world-resources-institute-dino-canopy-height-maps-v2/).

### City of Boise Tree Canopy Assessment 2013–2021

Needs owner action · confirmed · effort S · confidence medium

- **Contents:** a report by Sanborn with the University of Vermont Spatial
  Analysis Lab and others. Canopy in the Boise Area of Impact rose from 10%
  (2013) to 11.7% (2021), about 630,000 trees. It used a seven-class land
  cover (tree canopy, grass/shrub, bare soil, water, buildings,
  roads/railroads, other impervious) built from 2013 and 2019 LiDAR plus
  2013 and 2021 imagery. The 2019 LiDAR isn't in 3DEP (chapter 9 suggests
  Ada County or COMPASS). Results are summarized down to the parcel.
- **What's open:** the city's open-data hub has only the 2013 Treasure
  Valley canopy polygons (from 2010 NAIP) as a vector tile service, a
  planting-site web map and the "It's Getting Hot!" story map. The 2021
  land cover isn't there (hub search for "canopy", Oct 7).
- **Coverage:** the Boise Area of Impact only.
- **Endpoint:** the report PDF is public; the 2021 land cover isn't
  published. Key or account: unknown.
- **Updates:** periodic assessments (2013, 2021); the report recommends
  every 3–5 years. **Size:** unknown.
- **License:** report: none stated. Hub items: the City of Boise's own
  disclaimer.
- **robots.txt:** www.cityofboise.org: `Allow: /`, with only `/city_clerk/`
  disallowed. opendata.cityofboise.org: Crawl-delay 60; disallows `/sites/`,
  `/admin/`, `/sessions/`, `/groups/`, `/people/`, `/workspace/`.
- **Use cases:** validated canopy and land cover for Boise to check our
  lidar classification; canopy change for tree-planting priorities.
- **Personas:** urban forester, gardener, transit rider.
  **Core pieces:** the layer system.
- **Effort and risks:** small once shared. It needs a courtesy request to
  the City or TVCN for the land cover and its terms. Take only the raster,
  never the per-parcel tables. The 2013 polygons are too old to use.
- **Verification:** PDF text extracted; the figures, partners, classes and
  inputs match. The hub search shows only the 2013 polygons. robots
  rechecked.
- **Evidence:** [report PDF](https://cityofboise.org/media/19160/boise-tree-canopy-assessment-2013-2021-final-20240910.pdf),
  [hub search](https://opendata.cityofboise.org/api/search/v1/collections/all/items?q=canopy),
  [robots.txt (hub)](https://opendata.cityofboise.org/robots.txt),
  [robots.txt (city)](https://www.cityofboise.org/robots.txt).

### Sun-position algorithms (suncalc, NOAA equations, SPA)

Use · corrected · effort S · confidence high

- **Contents:** sun azimuth and elevation, sunrise, sunset and twilight;
  suncalc also gives the moon's position and phase. suncalc's README states
  sun accuracy of about 0.08°, ample for shadows; NREL's SPA states
  ±0.0003°. pvlib's `spa_python` is a port of SPA built on numpy (numba
  optional), so it isn't standard-library Python.
- **Coverage:** everywhere.
- **Endpoint:** libraries, not a service: the suncalc npm package or a
  small port of the NOAA equations in TypeScript, and a standard-library
  Python port of the NOAA equations, which fits the ingest rule. pvlib
  (numpy, pandas) doesn't, so it's a test oracle only.
- **Updates:** not applicable. **Size:** under 20 KB of code.
- **License:** suncalc BSD-2-Clause (README); pvlib BSD-3-Clause ⚠️ (not
  shown on the docs page fetched); NOAA's equations are public domain.
  SPA's C code is for internal, noncommercial use and may not be
  redistributed (and needs accepting terms before download), so don't
  bundle it.
- **robots.txt:** not applicable (no fetching).
- **Use cases:** shadow direction for any moment on the replay clock;
  sun-hours integration; sun-path diagrams; shared with the sky plugin,
  the camera glare calendar ([chapter 11](../11-camera-validation-layer.md))
  and commuter glare.
- **Personas:** gardener, sky watcher, commuter, camera calibration.
- **Core pieces:** a sun ephemeris module (proposed core), full replay.
- **Effort and risks:** small. The TypeScript and Python versions must
  share the azimuth origin and refraction conventions, or cross-tests fail
  near sunrise and sunset (see [the review's corrections](#review-corrections-to-the-design)).
  The old NREL hosts (midcdmz.nrel.gov) no longer resolve.
- **Verification:** confirmed suncalc's license and accuracy, and SPA's
  accuracy and no-redistribution license. Corrected: NREL is now the
  National Laboratory of the Rockies and its SPA page moved to
  midcdmz.nlr.gov; pvlib's SPA is numpy-based, not pure Python.
- **Evidence:** [suncalc](https://github.com/mourner/suncalc),
  [pvlib spa_python](https://pvlib-python.readthedocs.io/en/latest/reference/generated/pvlib.solarposition.spa_python.html),
  [SPA](https://midcdmz.nlr.gov/spa/),
  [chapter 11](../11-camera-validation-layer.md).

### NSRDB (National Solar Radiation Database)

Use · corrected · effort M · confidence medium

- **Contents:** satellite-derived hourly and half-hourly global, direct and
  diffuse irradiance (GHI, DNI, DHI), cloud type and meteorology. v3 is
  4 km and 30 min for 1998–2018; the CONUS set is 2 km and 5 min from 2018;
  full disc is 2 km and 10 min from 2018. Typical years (TMY, TDY, TGY) are
  included.
- **Coverage:** the Americas, including the ring.
- **Endpoint:** `s3://nrel-pds-nsrdb/` (us-west-2, `--no-sign-request`) and
  HSDS. The NSRDB API needs a free developer key. On Oct 7 the old hosts
  nsrdb.nrel.gov and developer.nrel.gov didn't resolve; nsrdb.nlr.gov and
  developer.nlr.gov answer.
- **Updates:** a year added at a time. **Size:** clipped typical years for
  a few cells, a few MB.
- **License:** CC BY 3.0 US.
- **robots.txt:** not applicable for S3. developer.nlr.gov: 200 and empty
  (no rules). nsrdb.nlr.gov returns the app's HTML (no rules).
- **Use cases:** weight sun hours by typical cloudiness per month (actual
  against clear-sky sun); sunshine lost to winter fog and inversions.
- **Personas:** gardener, sky watcher, homeowner.
- **Core pieces:** the sun ephemeris module (proposed core).
- **Effort and risks:** medium. HSDS/HDF5 access adds a dependency.
  Probably shared with the sky plugin. Host names are changing after the
  rename.
- **Verification:** license, bucket and products confirmed. Corrected the
  publisher's new name, the dead nrel.gov hosts, and checked the new API
  host's robots.txt.
- **Evidence:** [registry](https://registry.opendata.aws/nrel-pds-nsrdb/),
  [nlr.gov](https://www.nlr.gov/),
  [robots.txt (developer)](https://developer.nlr.gov/robots.txt),
  [robots.txt (nsrdb)](https://nsrdb.nlr.gov/robots.txt).

---

## Frost, growing season and hardiness

### NOAA NCEI U.S. Climate Normals 1991–2020

Use · confirmed · effort S · confidence high

- **Contents:** station normals (annual and seasonal, monthly, daily,
  hourly; for 1991–2020 and 2006–2020), including frost and freeze dates,
  growing degree days (GDD) and heating and cooling degree days, for about
  15,000 stations. Gridded normals exist in netCDF (also in ACIS as
  `ncei-norm:91-20`). Field names such as `ANN-TMIN-PRBLST-T32FP50` are
  unconfirmed ⚠️ (secondary PDFs only).
- **Coverage:** valley stations (list to confirm with ACIS `StnMeta` ⚠️);
  the fixed period 1991–2020. NWS Boise's freeze-probability page confirms
  its tables use these normals.
- **Endpoint:** the Access Data Service,
  `https://www.ncei.noaa.gov/access/services/data/v1`, with
  `dataset=normals-annualseasonal-1991-2020`, `normals-daily-1991-2020`,
  `normals-monthly-1991-2020` or `normals-hourly-1991-2020` (IDs confirmed
  in NCEI's dataset search). No token is mentioned. The bulk CSV folders
  are under `/data*`, which robots.txt disallows, so those are a hand
  download only.
- **Updates:** every 10 years (static until about 2031). **Size:** a few KB
  per station.
- **License:** U.S. Government data; the product page states no
  restrictions.
- **robots.txt:** www.ncei.noaa.gov disallows `/data*`, `/orders*` and
  several `/access/crn/` paths; `/access/services/data/v1` is allowed.
- **Use cases:** last spring frost and first fall frost at 10, 50 and 90%
  probability; frost-free days; GDD normals to say whether this year is
  ahead or behind.
- **Personas:** gardener, farmer, homeowner.
- **Core pieces:** the readings contract, areas.
- **Effort and risks:** small. Station-based, so a yard differs from the
  airport. The next normals are due around 2031.
- **Verification:** dataset IDs confirmed through NCEI's search service;
  robots.txt rechecked. The data service's docs mention no token or rate
  limit. Field names stay ⚠️.
- **Evidence:** [product page](https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals),
  [Access Data Service docs](https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation),
  [dataset search](https://www.ncei.noaa.gov/access/services/search/v1/datasets?text=normals&limit=50),
  [robots.txt](https://www.ncei.noaa.gov/robots.txt),
  [NWS Boise freeze probabilities](https://www.weather.gov/boi/freezeprob).

### RCC-ACIS web services

Use · confirmed · effort S · confidence high

- **Contents:** the calls `StnMeta`, `StnData`, `MultiStnData`, `GridData`
  and `General`. Reduce codes include `cnt_xx_yyy`, `first_xx_yyy`,
  `last_xx_yyy` and `run_xx_yyy` (the docs' own example is `last_le_28`
  with duration `std` and season_start `7-1`); `gddXX` elements; `normal`
  `91` or `91departure` for 1991–2020; grid 21 is PRISM CONUS daily, 1981
  to the present; gridded NCEI normals are `ncei-norm:91-20`. Networks
  include CoCoRaHS (network code 10).
- **Sample (not re-run ⚠️):** the researcher's Boise Air Terminal pull gave
  last spring 32 °F freezes for 2016–2026 from Mar 28 to May 13, median
  Apr 17.
- **Coverage:** all COOP, GHCN and CoCoRaHS stations in Ada, Canyon and the
  ring; decades of history.
- **Endpoint:** JSON POST to `https://data.rcc-acis.org/StnData` and the
  other calls; the documentation loads from
  [ACISWSdoc.html](https://www.rcc-acis.org/ACISWSdoc.html).
- **Updates:** daily (station reports). **Size:** a few KB per call.
- **License:** the web-services docs state no terms. The NOAA station data
  are U.S. Government data; CoCoRaHS values are CC BY 4.0.
- **robots.txt:** data.rcc-acis.org: 404 (no rules). www.rcc-acis.org:
  `User-agent: *` with an empty Disallow (all allowed).
- **Use cases:** this year's and past years' freeze dates per station; heat
  days (95 °F and over, 100 °F and over) and warm nights per summer; GDD to
  date against normal; nearby rain totals, including CoCoRaHS.
- **Personas:** gardener, farmer, hazard watcher, landscaper.
- **Core pieces:** the readings contract, the time-series card.
- **Effort and risks:** small. Poll gently (a daily job of a few calls).
  Thresholds and periods differ between sources, so always show the
  station and the threshold. Secondary gardening sites quote a valley last
  frost near May 4 ⚠️.
- **Verification:** full documentation read: reduce syntax, `gddXX`,
  grid 21, `normal` 91 and the CoCoRaHS network confirmed. The Boise
  sample is unverified but plausible.
- **Evidence:** [web services](https://www.rcc-acis.org/docs_webservices.html),
  [documentation](https://www.rcc-acis.org/ACISWSdoc.html),
  [robots.txt (data)](https://data.rcc-acis.org/robots.txt),
  [robots.txt (www)](https://www.rcc-acis.org/robots.txt).

### PRISM 1991–2020 normals

Use · corrected · effort M · confidence high

- **Contents:** gridded 1991–2020 normals of tmin, tmax, tmean, ppt,
  tdmean, vpdmin, vpdmax and solar at 800 m and 4 km, including daily
  normals. Also daily, monthly and annual time series at 800 m and 4 km
  (daily from 1981).
- **Coverage:** the conterminous US, including Ada, Canyon and the ring.
- **Endpoint:** the normals aren't on the web service (per its March 2025
  documentation): download them by hand from the website or the PRISM FTP.
  Time series come one grid per request from
  `https://services.nacse.org/prism/data/get/us/{800m|4km}/{var}/{date}`
  (zipped COG; nc, asc or bil optional). A file downloaded twice in 24 h is
  blocked for the rest of that period, and excessive activity can get the
  IP blocked. The old web service was switched off Sep 30, 2025. PRISM
  daily also comes through ACIS grid 21.
- **Updates:** normals are static until the next period; time series are
  daily, final after six months.
- **Size:** daily normals for one variable over CONUS, a few GB before
  clipping ⚠️ (estimate); tens of MB clipped to the ring.
- **License:** PRISM's terms say the data may be freely reproduced and
  distributed. Credit the PRISM Group, the URL and the access date; OSU
  keeps ownership.
- **robots.txt:** prism.oregonstate.edu, services.nacse.org and
  ftp.prism.oregonstate.edu (over https) all return 404 (no rules).
- **Use cases:** shift a station's frost dates to a yard by the difference
  in normal minimum temperature; heat and growing-degree normals as a
  surface.
- **Personas:** gardener, farmer. **Core pieces:** the layer system.
- **Effort and risks:** medium. 800 m can't see yard-scale cold pockets, so
  combine it with terrain. PRISM advises against very long-term trends.
  Respect the twice-in-24-h file limit. A public-domain alternative: NCEI's
  gridded normals (ACIS `ncei-norm:91-20`).
- **Verification:** terms confirmed. Corrected access: the normals aren't
  on the web service, and the web service is on another host
  (services.nacse.org) with a per-file limit; that host's robots.txt was
  checked.
- **Evidence:** [normals](https://prism.oregonstate.edu/normals/),
  [terms](https://prism.oregonstate.edu/terms/),
  [downloads](https://prism.oregonstate.edu/downloads/),
  [web service PDF](https://prism.oregonstate.edu/documents/PRISM_downloads_web_service.pdf),
  [robots.txt (prism)](https://prism.oregonstate.edu/robots.txt),
  [robots.txt (nacse)](https://services.nacse.org/robots.txt).

### 2023 USDA Plant Hardiness Zone Map GIS data

Use · confirmed · effort S · confidence high

- **Contents:** the 1991–2020 mean annual extreme minimum temperature grid,
  a half-zone shapefile, KML and a ZIP-code CSV for CONUS, Alaska, Hawaii
  and Puerto Rico. Published by USDA-ARS and the PRISM Group at OSU.
- **Coverage:** CONUS, including the whole ring.
- **Endpoint:** direct links, no registration: `phzm_us_grid_2023.zip`,
  `phzm_us_zones_shp_2023.zip`, `phzm_us_zones_kml_2023.zip`,
  `phzm_us_zipcode_2023.csv`. One hand download.
- **Updates:** about every 10 years (2012, 2023). **Size:** tens of MB for
  the CONUS shapefile ⚠️ (estimate).
- **License:** may be freely reproduced and redistributed if derived maps
  show both the USDA-ARS and OSU logos. Altered data need a prominent
  disclaimer that it isn't the official USDA Plant Hardiness Zone Map, and
  no logos. OSU owns the data.
- **robots.txt:** prism.oregonstate.edu: 404 (no rules).
- **Use cases:** the hardiness half-zone at a yard; plant suggestions
  filtered by zone (links only).
- **Personas:** gardener, homeowner, native-plant gardener.
- **Core pieces:** the layer system.
- **Effort and risks:** small. A layer restyled in our palette counts as
  altered: it must carry the "not the official map" disclaimer and drop the
  logos.
- **Verification:** terms and file names confirmed word for word on the
  PHZM page; no registration.
- **Evidence:** [PHZM page](https://prism.oregonstate.edu/phzm/),
  [robots.txt](https://prism.oregonstate.edu/robots.txt).

---

## Soils

### NRCS SSURGO via Soil Data Access

Use · corrected · effort S · confidence high

- **Contents:** soil map units, components and horizons: texture, pH,
  organic matter, available water capacity, drainage class, hydrologic
  group, depth to a restrictive layer, salinity and sodicity, farmland
  class. The researcher's sample map unit, Paulmyers silt loam, matches a
  real series: mapped in Ada County, somewhat poorly drained, pH 7.8–8.3,
  no duripan (official series description).
- **Coverage:** Ada (survey area ID001), Canyon and the whole ring.
- **Endpoint:** tabular: POST
  `https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest` (SQL, JSON).
  Spatial: the WFS endpoints `SDMWGS84Geographic.wfs`,
  `SDMNAD83Geographic.wfs` and `SDMWM.wfs`, plus `SDM.wms`. Limits: at most
  100,000 rows per tabular query and a default `MAXFEATURES` of 250,000;
  GetFeature volume is limited by the filter's extent. Bulk gSSURGO (Web
  Soil Survey) is a hand download.
- **Updates:** an annual refresh, said to land Oct 1 ⚠️ (NRCS's refresh
  page timed out). **Size:** tens of MB for Ada and Canyon polygons and
  tables.
- **License:** public domain: the data.gov record carries the USA
  public-domain label.
- **robots.txt:** sdmdataaccess.sc.egov.usda.gov,
  sdmdataaccess.nrcs.usda.gov, websoilsurvey.nrcs.usda.gov and
  soilseries.sc.egov.usda.gov all return 404 (no rules). www.nrcs.usda.gov
  disallows `/core/`, `/profiles/`, `/search*`, `/admin/` and every URL
  with a query string (`/*?`). UC Davis SoilWeb
  (casoilresource.lawr.ucdavis.edu) blocks ClaudeBot, GPTBot, bingbot and
  other named crawlers; our User-Agent falls under `*`, which blocks only
  `/application/*`, but skip SoilWeb anyway, since it duplicates SDA.
- **Use cases:** a soil card per bed; hardpan-depth warnings for trees; a
  soils layer styled by drainage or pH; farmland class for the farm
  plugin.
- **Personas:** gardener, homeowner, farmer, community garden organizer.
- **Core pieces:** the layer system, areas.
- **Effort and risks:** small. Map units are 1:24,000, and urban fill often
  differs from the mapped soil.
- **Verification:** endpoints, limits and the public-domain license
  confirmed; the sample series is plausible. Corrected the
  www.nrcs.usda.gov rules (`/*?` and `/search*` too) and SoilWeb's
  AI-crawler block. Unverifiable: the Oct 1 refresh date.
- **Evidence:** [SDA help](https://sdmdataaccess.nrcs.usda.gov/WebServiceHelp.aspx),
  [robots.txt (sc.egov)](https://sdmdataaccess.sc.egov.usda.gov/robots.txt),
  [robots.txt (nrcs)](https://sdmdataaccess.nrcs.usda.gov/robots.txt),
  [robots.txt (Web Soil Survey)](https://websoilsurvey.nrcs.usda.gov/robots.txt),
  [robots.txt (www.nrcs)](https://www.nrcs.usda.gov/robots.txt),
  [robots.txt (SoilWeb)](https://casoilresource.lawr.ucdavis.edu/robots.txt),
  [data.gov record](https://catalog.data.gov/dataset/soil-survey-geographic-database-ssurgo),
  [Paulmyers series](https://soilseries.sc.egov.usda.gov/OSD_Docs/P/PAULMYERS.html).

---

## Water: ET, rain and canal seasons

### AgriMet crop water-use charts

Use · corrected · effort S · confidence high

- **Contents:** per-station crop water-use charts: 1982 Kimberly-Penman
  alfalfa reference ET (ETr) and crop ET, with crop codes including LAWN,
  PAST, ALFM/ALFP, POTA, ONYN, FCRN/SCRN and APPL. Historical ET summaries
  give daily crop ET for whole past seasons, and the chart key says the
  same crop codes apply to both. Valley stations: BOII Boise, BFGI Boise
  Fairgrounds, NMPI Nampa, PMAI Parma (soil temperature at 1, 4, 8 and
  20 in, plus leaf wetness) and ONTO Ontario (soil temperature at 4, 8 and
  20 in). PICI is Picabo, outside the valley. The researcher's Oct 5 Parma
  values were not re-read.
- **Coverage:** point stations in Boise, Nampa, Parma and Ontario,
  representative of the irrigated valley floor.
- **Endpoint:** current season:
  `https://www.usbr.gov/pn/agrimet/chart/{stn}ch.txt` (for example
  `pmaich.txt`), April through October. History:
  `/pn/agrimet/chart/{stn}{yy}et.txt`, the URL that `etsummary.html`'s own
  script builds (for example `pmai25et.txt`; not fetched). Annual ET totals
  for 1988–2015 are on `ETtotals.html`. All of these are under the allowed
  `/pn/agrimet/` path.
- **Updates:** daily, April to October: about 5:30 MT per the chart key, or
  by 6:30 am MDT per the crop water-use page, so schedule after 6:30 MT.
- **Size:** about 2 KB per station per day; one small file per
  station-year for history.
- **License:** U.S. Government data. The disclaimer calls near-real-time
  data provisional (not reviewed or edited).
- **robots.txt:** www.usbr.gov disallows only `/pn-bin` and `/gp-bin`;
  `/pn/agrimet/chart/` is allowed.
- **Use cases:** weekly lawn and garden water need; crop ET for the farm
  plugin; season-by-season ET history from the static yearly summaries.
- **Personas:** gardener, landscaper, farmer.
- **Core pieces:** the readings contract, the time-series card.
- **Effort and risks:** small. Provisional data. The charts use
  Kimberly-Penman alfalfa ETr, so don't mix them with ASCE ETo/ETr
  (gridMET) without converting. Charts run only April to October. Weather
  and soil-temperature history still needs the disallowed `/pn-bin` (next
  entry).
- **Verification:** **refuted** the claim that only the current season is
  available and history needs `/pn-bin`: `etsummary.html` builds static
  URLs for past seasons, and `ETtotals.html` has 1988–2015 totals, all on
  allowed paths. Corrected Parma's soil depths (20 in too), the update time
  and the season. Station codes and LAWN confirmed.
- **Evidence:** [robots.txt](https://www.usbr.gov/robots.txt),
  [crop water use](https://www.usbr.gov/pn/agrimet/h2ouse.html),
  [chart key](https://www.usbr.gov/pn/agrimet/chartkey.html),
  [crop key](https://www.usbr.gov/pn/agrimet/cropkey.html),
  [ET summaries](https://www.usbr.gov/pn/agrimet/etsummary.html),
  [ET totals](https://www.usbr.gov/pn/agrimet/ETtotals.html),
  [station parameters](https://www.usbr.gov/pn/agrimet/aginfo/station_params.html),
  [disclaimer](https://www.usbr.gov/pn/agrimet/disclaimer.html),
  [general](https://www.usbr.gov/pn/agrimet/general.html).

### AgriMet and Hydromet station data (dayfiles, archives, RISE API)

Needs owner action · corrected · effort S · confidence high

- **Contents:** hourly-collected weather, daily ET, soil temperature
  (Parma, Ontario), and Hydromet reservoir and canal data for the Boise
  River system, which IDWR's Water District 63 page links to for current
  operations.
- **Coverage:** the valley stations above; Boise River reservoirs and
  canals.
- **Endpoint:** CGI scripts under `www.usbr.gov/pn-bin/` and the RISE API
  at `data.usbr.gov/rise/api`.
- **Updates:** hourly to daily. **Size:** small (a few MB per
  station-decade).
- **License:** U.S. Government data; provisional.
- **robots.txt:** disallowed. www.usbr.gov: `Disallow: /pn-bin`.
  data.usbr.gov disallows `/rise/api`, `/time-series?`, its selection,
  output and search pages, `/catalog?` and the rise-map query URLs.
- **Use cases:** soil-temperature and weather history; soil warm-up for
  planting; reservoir and canal context.
- **Personas:** gardener, farmer, water watcher.
- **Core pieces:** the readings contract.
- **Owner action:** no automated collection. The owner can ask Reclamation
  (agrimet@usbr.gov) for permission or do a one-off hand download. ET
  history no longer depends on this (previous entry); only soil
  temperature, weather history and Hydromet do.
- **Verification:** both robots.txt files rechecked. The scope was narrowed
  as above.
- **Evidence:** [robots.txt (usbr)](https://www.usbr.gov/robots.txt),
  [robots.txt (data.usbr)](https://data.usbr.gov/robots.txt),
  [AgriMet general](https://www.usbr.gov/pn/agrimet/general.html),
  [IDWR WD63](https://idwr.idaho.gov/wr-administration/water-rights-accounting/wd63/).

### gridMET daily surface meteorology

Use · confirmed · effort M · confidence high

- **Contents:** about 4 km (1/24°) daily tmin, tmax, precipitation,
  radiation, wind, humidity, vapor-pressure deficit (VPD), ASCE
  Penman-Monteith reference ET, energy release component, burning index,
  fuel moisture and 10-day PDSI. CONUS from 1979, updated daily; recent
  days use PRISM/CFSv2 blends. From the Climatology Lab (John Abatzoglou),
  UC Merced, originally at the University of Idaho.
- **Coverage:** CONUS, including the ring; 4 km can't resolve yards.
- **Endpoint:** NetCDF per variable per year at
  `https://www.northwestknowledge.net/metdata/data/`. THREDDS is
  robots-disallowed. Also listed: Climate Engine and the USGS Geo Data
  Portal (zarr).
- **Updates:** daily. **Size:** roughly 0.1–1 GB per variable-year file
  before clipping ⚠️ (estimate).
- **License:** the creator "has waived all copyright and related or
  neighboring rights" (a CC0-style waiver). Cite Abatzoglou (2013).
- **robots.txt:** www.northwestknowledge.net: 404 (no rules).
  thredds.northwestknowledge.net: `Disallow: /` (don't use). climatologylab.org:
  `*` disallows `/ajax/` and `/apps/`; NerdyBot is blocked and dotbot gets
  Crawl-delay 10.
- **Use cases:** ET history and normals for watering advice; VPD and
  heat-stress days; gap-filling between stations.
- **Personas:** gardener, farmer, landscaper.
- **Core pieces:** the readings contract, the layer system.
- **Effort and risks:** medium. The current-year CONUS file is rewritten
  daily, so weekly re-downloads of a 100+ MB file for a few cells would be
  wasteful: pull completed years once for history and use AgriMet for the
  current season. Never use THREDDS.
- **Verification:** license wording, variables, hosts and all three
  robots.txt files confirmed.
- **Evidence:** [gridMET](https://www.climatologylab.org/gridmet.html),
  [robots.txt (climatologylab)](https://www.climatologylab.org/robots.txt),
  [robots.txt (THREDDS)](https://thredds.northwestknowledge.net/robots.txt),
  [robots.txt (northwestknowledge)](https://www.northwestknowledge.net/robots.txt).

### ET-IDWR (ETIdaho, updated 2025)

Use · corrected · effort S · confidence medium

- **Contents:** daily, monthly and annual ET, net irrigation requirement
  and effective precipitation by land cover for 212 stations in and around
  Idaho (208 in 2023, plus new ones in 2025). The land covers named on the
  home page are crops (alfalfa, winter wheat, canola, mustard), native
  systems and open water; turf or lawn isn't named ⚠️. From IDWR with the
  University of Idaho's Kimberly Research and Extension Center.
- **Coverage:** valley stations, with long records.
- **Endpoint:** station pages on et-idwr.idaho.gov; the download format
  isn't stated on the home page.
- **Updates:** occasional (2007, 2009, 2012, 2017, 2023, 2025).
  **Size:** small.
- **License:** an IDWR disclaimer of legal responsibility for accuracy and
  completeness.
- **robots.txt:** answers 302 to `https://error.idaho.gov/`, an HTML page
  with status 200 and no rules: effectively no rules, though not the 404
  first reported.
- **Use cases:** long-term crop (and, if present, turf) water-need normals
  per station; a sanity check for AgriMet-based advice.
- **Personas:** gardener, farmer, landscaper.
- **Core pieces:** the readings contract.
- **Effort and risks:** small. Confirm the format and whether there's a
  turf land cover before building.
- **Verification:** station count and update years confirmed; robots.txt
  corrected; turf still unconfirmed.
- **Evidence:** [ET-IDWR](https://et-idwr.idaho.gov/),
  [robots.txt](https://et-idwr.idaho.gov/robots.txt).

### OpenET

Avoid · confirmed · effort M · confidence high

- **Contents:** 30 m Landsat-based actual ET for fields, western US,
  monthly.
- **Endpoint:** an API at openet-api.org with an account and key.
- **License:** a revocable license for personal, noncommercial use; content
  made with OpenET data is deemed OpenET's intellectual property; scraping
  and robots are forbidden.
- **robots.txt:** openet-api.org and developer.openet-api.org:
  `Disallow: /`. etdata.org disallows only `/wp-admin/`.
- **Use case:** field ET for farms (would have been). **Persona:** farmer.
  **Core pieces:** none.
- **Risks:** the terms conflict with an open, MIT-licensed project, and the
  API disallows robots.
- **Verification:** terms and robots.txt rechecked; both match.
- **Evidence:** [terms](https://etdata.org/terms-of-service/),
  [robots.txt (API)](https://openet-api.org/robots.txt),
  [robots.txt (developer)](https://developer.openet-api.org/robots.txt),
  [robots.txt (etdata)](https://etdata.org/robots.txt).

### CoCoRaHS daily precipitation (through ACIS)

Use · corrected · effort S · confidence medium

- **Contents:** volunteers' daily rain, snow and hail reports, many in
  valley neighborhoods. From the Community Collaborative Rain, Hail and
  Snow Network (Colorado State University).
- **Coverage:** dense in Boise, Meridian and Nampa; sparse in rural Canyon
  ⚠️ (not re-checked).
- **Endpoint:** through ACIS (network code 10, `cocorahs`), not
  CoCoRaHS's own data pages.
- **Updates:** daily (morning reports). **Size:** a few KB per day.
- **License:** CC BY 4.0: the terms of use release all site content under
  it (the researcher had 3.0). Credit CoCoRaHS.
- **robots.txt:** www.cocorahs.org disallows `/admin/` and `/viewdata/`, so
  don't scrape its data views. data.cocorahs.org: 404.
- **Use case:** how much rain fell near the yard this week (the watering
  coach).
- **Personas:** gardener, landscaper.
- **Core pieces:** the readings contract.
- **Effort and risks:** small. Station coordinates are volunteers' homes:
  show totals smoothed or rounded to about 1 km, never as named pins. The
  separate data-usage and privacy policies weren't read.
- **Verification:** license corrected from the terms page; ACIS support
  confirmed from the ACIS docs; robots.txt confirmed.
- **Evidence:** [robots.txt](https://www.cocorahs.org/robots.txt),
  [terms of use](https://www.cocorahs.org/Content.aspx?page=termsofuse),
  [ACIS docs](https://www.rcc-acis.org/ACISWSdoc.html).

### IDWR Irrigation Organizations (service areas)

Use · corrected · effort S · confidence high

- **Contents:** polygons of the service areas within which an irrigation
  organization can deliver water rights (a Large Place of Use under Idaho
  Code 42-202B(2) where `LPOU` = YES). Fields: `NAME`, `Owner`,
  `PlaceOfUse`, `LPOU`, `PROCESS`, `PERIMETER`, `ACRES`. Updated May 7,
  2026. Not the irrigated area itself.
- **Coverage:** statewide, including Ada, Canyon and the ring.
- **Endpoint:** ArcGIS FeatureServer layer 0 (Query and Extract;
  `maxRecordCount` 2,000); fits the shared ArcGIS reader.
- **Updates:** when boundaries change (last May 7, 2026). **Size:** a few
  MB.
- **License:** credit IDWR (`copyrightText`); IDWR assumes no legal
  responsibility for accuracy.
- **robots.txt:** gis.idwr.idaho.gov answers 302 to `https://error.idaho.gov/`
  (HTML, 200, no rules): effectively no rules, not a 404. idwr.idaho.gov:
  `User-agent: *` with an empty Disallow. data-idwr.hub.arcgis.com:
  Crawl-delay 60.
- **Use cases:** which district or canal company serves a yard; linking a
  yard to this year's canal-season dates.
- **Personas:** gardener, homeowner, farmer, landscaper.
- **Core pieces:** the layer system, areas, search.
- **Effort and risks:** small. Service areas overlap (district, canal
  company and city pressurized irrigation): show all of them and say which
  one delivers to subdivisions.
- **Verification:** layer, fields, limit, description and update date
  confirmed; robots.txt corrected.
- **Evidence:** [layer JSON](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/0?f=pjson),
  [item info](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/info/iteminfo?f=pjson),
  [robots.txt (gis)](https://gis.idwr.idaho.gov/robots.txt),
  [robots.txt (idwr)](https://idwr.idaho.gov/robots.txt),
  [robots.txt (hub)](https://data-idwr.hub.arcgis.com/robots.txt).

### Irrigation season announcements

Use · corrected · effort S · confidence medium

- **Contents:** turn-on and shutoff dates that districts and cities post as
  news:
  - **Nampa & Meridian Irrigation District (NMID):** the page (its URL says
    2025) is about the 2026 season: Ridenbaugh Canal flows "as early as
    April 1 but not later than April 8", delivery mid-to-late April.
  - **Caldwell (CMID):** pumps on about Apr 15–30 and normally off Oct 1–15,
    but the 2026 shutdown was on Sep 24; odd/even watering days.
  - **City of Boise:** pressurized irrigation in 14 named subdivisions. A
    claim of 10 named supplying districts wasn't found on the page ⚠️.
  - **Boise Project Board of Control** (five districts: Big Bend,
    Boise-Kuna, Nampa & Meridian, New York, Wilder): 2026 releases began
    Apr 6, with delivery about mid-April in a shortened, low-water season
    (KIVI; the New York Canal takes a little over a week to fill).
  - **Pioneer Irrigation District** and **City of Nampa** pressurized
    irrigation: in scope; robots.txt checked, no dates recorded in this
    pass.
- **Coverage:** Ada and Canyon districts. Settlers, Farmers Union, Boise
  City Canal and others are still to find.
- **Endpoint:** by hand. Read each organization's page once or twice a
  season (one-off research checks) and enter the dates as lifecycle events
  with the source URL. No schedules or scrapers. The Boise Project's own
  site is www.boiseproject.net (linked from nyid.org), not boiseproject.org.
- **Updates:** twice a year (spring start, fall shutoff), plus drought
  notices. **Size:** a few rows per district per year.
- **License:** public notices. We record facts (dates) with citations, not
  page text.
- **robots.txt:** nmid.org disallows only `/wp-admin/`.
  pioneerirrigation.com disallows asset and system folders only.
  cityofboise.org allows all but `/city_clerk/`. cityofcaldwell.org
  disallows `/maps`, `/Recreation`, some portals and Economic Development
  pages, but not `/Departments/Irrigation`. nyid.org: `*` `Allow: /`.
  www.boiseproject.net: 404 (no rules). boiseproject.org still times out
  (treated as disallowed). cityofnampa.us answers 403 behind a Cloudflare
  challenge: under RFC 9309 a 4xx means no rules, but the challenge signals
  "no bots", so it's read by hand only.
- **Use cases:** canal water on or off for the yard's district; Valley Feed
  items and countdowns; season length year to year (drought years).
- **Personas:** gardener, landscaper, farmer, homeowner.
- **Core pieces:** the lifecycles contract, the Valley Feed, evidence and
  review.
- **Effort and risks:** small. Dates are announced late and change with the
  water supply (2026 was a shortened season), so keep the announcement
  date and source with each entry.
- **Verification:** NMID, Caldwell and KIVI facts confirmed. Corrected: the
  Boise Project's site is boiseproject.net (robots.txt 404), and delivery
  is about mid-April rather than "no earlier than Apr 10". The Boise
  supplier list is unverified.
- **Evidence:** [NMID](https://nmid.org/2025-season-start-up/),
  [robots.txt (NMID)](https://nmid.org/robots.txt),
  [robots.txt (Pioneer)](https://www.pioneerirrigation.com/robots.txt),
  [Boise pressure irrigation](https://www.cityofboise.org/departments/public-works/pressure-irrigation),
  [Caldwell irrigation](https://www.cityofcaldwell.org/Departments/Irrigation),
  [robots.txt (Caldwell)](https://www.cityofcaldwell.org/robots.txt),
  [robots.txt (Nampa)](https://www.cityofnampa.us/robots.txt),
  [robots.txt (NYID)](https://www.nyid.org/robots.txt),
  [Boise Project Board of Control](https://www.nyid.org/boise-project-board-of-control),
  [robots.txt (boiseproject.net)](https://www.boiseproject.net/robots.txt),
  [KIVI, Apr 2026](https://www.kivitv.com/news/local-news/in-your-neighborhood/ada-county/irrigation-releases-for-treasure-valley-farmers-and-homeowners-begin-on-april-6).

### Water District 63 (Boise River) diversion telemetry and accounting

Needs owner action · unverifiable · effort M · confidence low

- **Contents:** telemetry of Boise River canal diversions and pumps on Paige
  Wireless equipment (Boise State Public Radio, Sep 2022). The counts
  (64–69 canals, 25 pumps) and a login-only dashboard are unconfirmed ⚠️.
  A public alternative: IDWR's WD63 page posts annual water-rights
  accounting reports (1986–2026) and storage reports (1989–2026) as PDFs,
  which may hold per-canal diversions ⚠️ (not opened). Current daily
  operations link to Reclamation's Hydromet (`/pn-bin`, disallowed).
- **Coverage:** Boise River diversions (Ada, Canyon, Boise and Elmore
  counties).
- **Endpoint:** telemetry: no public feed found. Annual PDFs, by hand:
  `idwr.idaho.gov/wp-content/uploads/sites/2/water-rights-accounting/boiwra/{YEAR}-boise-wr-accounting-report.pdf`.
- **Updates:** telemetry hourly to daily; accounting PDFs yearly.
  **Size:** small. **Access:** telemetry would need a partnership.
- **License:** unknown for the telemetry. The IDWR PDFs are state public
  records with no license stated.
- **robots.txt:** telemetry: not applicable (no public endpoint).
  idwr.idaho.gov: all allowed (empty Disallow).
- **Use cases:** the real "canal water is on" signal per canal; early
  shutoff warnings; per-canal season history from the annual reports.
- **Personas:** gardener, farmer, water watcher.
- **Core pieces:** the readings contract.
- **Owner action:** live telemetry needs the watermaster's permission. The
  annual PDFs only tell us after the fact.
- **Verification:** the USBR WaterSMART PDF showed a maintenance page on
  Oct 7. Boise State Public Radio confirms Paige Wireless but says nothing
  about public or login access. The canal and pump counts are unconfirmed.
  The IDWR annual reports are a new lead.
- **Evidence:** [USBR WaterSMART PDF](https://usbr.gov/watersmart/swep/docs/2022/SWEP_064_Water_District_63_508.pdf)
  (under maintenance on Oct 7),
  [Boise State Public Radio, Sep 2022](https://www.boisestatepublicradio.org/news/2022-09-19/boise-river-could-soon-be-the-largest-us-surface-water-irrigation-system-to-belectronically-monitored),
  [IDWR water-rights accounting](https://idwr.idaho.gov/water-data/water-rights-accounting/),
  [IDWR WD63](https://idwr.idaho.gov/wr-administration/water-rights-accounting/wd63/).

---

## Phenology, pests and planting guides

### USA National Phenology Network gridded products

Needs owner action · corrected · effort M · confidence high

- **Contents:** accumulated growing degree days (AGDD), the Spring Index
  (first leaf and first bloom, with anomalies), thermal calendars, land
  surface phenology, and Pheno Forecasts (6-day forecasts of pest and
  invasive-plant stages). Resolution and base temperatures aren't stated on
  the maps page ⚠️.
- **Coverage:** CONUS, including the ring (grid resolution unconfirmed ⚠️).
- **Endpoint:** GeoServer WMS/WCS at geoserver.usanpn.org through the
  request builder. No account needed to fetch, but see the terms.
- **Updates:** daily. **Size:** a few MB per daily CONUS grid ⚠️
  (estimate); a few KB clipped.
- **License:** the data are CC BY 4.0, with a citation format for
  GeoServer rasters. But the site's terms of use (v2.5, Mar 2022) forbid
  automated access to any part of the site and its services unless
  approved in advance and in writing.
- **robots.txt:** geoserver.usanpn.org: 404 (no rules). www.usanpn.org
  disallows `/core/`, `/profiles/`, `/admin/`, `/search/`, and user and
  oembed paths. The terms are stricter than robots.txt.
- **Use cases:** is spring early or late this year; the leaf-out date to
  switch tree shade from leaf-off to leaf-on; pest timing alerts.
- **Personas:** gardener, native-plant gardener, farmer.
- **Core pieces:** the layer system, the readings contract.
- **Owner action:** a daily scripted pull needs NPN's written OK. Until
  then, use one-off manual views, or compute our own GDD and a leaf-out
  proxy from ACIS. Nature's Notebook sites are often volunteers' yards, so
  show only aggregates.
- **Verification:** license confirmed. Verdict changed from "use" to
  "needs owner action" because of the terms' automation clause.
- **Evidence:** [maps](https://usanpn.org/data/maps),
  [terms](https://www.usanpn.org/about/terms),
  [robots.txt (GeoServer)](https://geoserver.usanpn.org/robots.txt),
  [robots.txt (www)](https://www.usanpn.org/robots.txt).

### USPEST.org degree-day and pest models

Avoid · confirmed · effort S · confidence high

- **Contents:** degree-day models and pest-risk calculators fed by regional
  weather stations, from OSU's Integrated Plant Protection Center; Pacific
  Northwest stations; daily.
- **Endpoint:** web calculators under `/dd/`, `/risk/`, `/wea_dd` and
  others.
- **License:** not checked.
- **robots.txt:** for `*`, disallows `/dd/do_model`, `/risk/models`,
  `/wea_dd`, `/data/`, `/calc/`, `/current/`, `/fcst/`, `/histor_data/`,
  `/pnw/` and more. GPTBot, SemrushBot and others are blocked entirely.
- **Use case:** a reference for pest thresholds (link only).
  **Personas:** gardener, farmer. **Core pieces:** none.
- **Risks:** no automated use. Compute GDD ourselves from ACIS and link to
  published thresholds.
- **Verification:** robots.txt re-read; matches.
- **Evidence:** [robots.txt](https://uspest.org/robots.txt).

### Idaho State Department of Agriculture Japanese beetle program

Use · corrected · effort S · confidence medium

- **Contents:** eradication program areas and dates. In Caldwell, the
  official page describes a residential area bounded by Lincoln Rd (north),
  Franklin Rd (south), I-84 (west) and Smeed Pkwy (east). The plan on the
  page is for 2025: about 320 acres of treatable turf, with applications in
  May (Acelepryn G) and mid-July (imidacloprid). Figures for 2026 (85 acres,
  630 traps) came from search snippets and weren't found on the official
  page ⚠️. An ArcGIS web viewer is linked. The Pocatello program is outside
  our area.
- **Coverage:** the Caldwell area.
- **Endpoint:** web pages, PDF fact sheets and the ArcGIS viewer; area
  outlines and dates entered by hand.
- **Updates:** seasonal. **Size:** a few polygons per year.
- **License:** public notices; none stated.
- **robots.txt:** agri.idaho.gov: 200 and empty (no rules).
- **Use cases:** program and treatment-area outlines with dates; reminders
  not to move plants or soil out of the area (confirm the rule's wording
  first).
- **Personas:** gardener, native-plant gardener, farmer.
- **Core pieces:** the lifecycles contract, the layer system.
- **Effort and risks:** small. Privacy: treatment is per property (the page
  cites individual property treatments), so show the program area only,
  never treated properties. The page doesn't state quarantine rules on
  moving plants or soil, so confirm them before showing that reminder.
- **Verification:** corrected from the official page: the east boundary is
  Smeed Pkwy (not S Kcid Rd), and the plan is 2025's 320 acres. The
  researcher's 2026 figures don't match the page.
- **Evidence:** [ISDA Japanese beetle](https://agri.idaho.gov/idaho-japanese-beetle/),
  [robots.txt](https://agri.idaho.gov/robots.txt).

### University of Idaho Extension gardening publications

Use · confirmed · effort S · confidence high

- **Contents:** BUL 965, *Spring Vegetable Planting Guide for Idaho* (Mar 31,
  2020; Andres West): hardiness zones, growing seasons, frost-free days and
  a planting-date chart for cool- and warm-season crops.
- **Coverage:** Idaho-wide advice.
- **Endpoint:** web pages and PDFs; link only.
- **Updates:** occasional.
- **License:** copyrighted (© University of Idaho in the footer), with no
  reuse statement. We link; we never copy text or charts.
- **robots.txt:** www.uidaho.edu: `User-agent: *`, `Allow: /`.
- **Use cases:** a monthly reading list in the yard card; planting-window
  links next to our frost and GDD numbers.
- **Personas:** gardener, native-plant gardener, community garden
  organizer. **Core pieces:** none.
- **Risks:** link rot; keep a short curated list.
- **Verification:** publication page and robots.txt confirmed.
- **Evidence:** [BUL 965](https://www.uidaho.edu/extension/publications/bul-0965),
  [robots.txt](https://www.uidaho.edu/robots.txt).

---

## Heat, smoke, air and alerts

### NOAA Hazard Mapping System (HMS) smoke polygons

Use · confirmed · effort S · confidence high

- **Contents:** analyst-drawn smoke polygons with a density. The labels
  light, medium and heavy replaced the numbers 5, 16 and 27 on July 19,
  2022, so older files carry numbers. Also fire detections. Archive from
  2002.
- **Coverage:** North America, including the ring.
- **Endpoint:** daily shapefile, KML and text under
  `https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/` (`Smoke_Polygons/`,
  `Fire_Points/`, `Graphic/`; the exact sub-path and file pattern weren't
  re-opened ⚠️). First analysis 11 AM–12 PM ET, second 7–8 PM ET.
- **Updates:** twice daily. **Size:** about 0.1–1 MB per day.
- **License:** U.S. Government data. OSPO describes the products as general
  guidance for strategic planning.
- **robots.txt:** satepsanone.nesdis.noaa.gov: 404 (no rules).
  www.ospo.noaa.gov: `User-agent: *` with no rules.
- **Use cases:** smoke days per summer over the valley; today's smoke for
  outdoor work.
- **Personas:** gardener, hazard watcher, cyclist.
- **Core pieces:** the lifecycles contract, the layer system.
- **Effort and risks:** small. Polygons show smoke aloft, not at the
  ground, and clouds hide smoke, so pair them with AQI. Normalize the
  density field across the 2022 change. Shared with the hazards plugin.
- **Verification:** product page and directory index re-read; the density
  change date and analysis times match. Added the 2002 archive start and
  the numeric densities before July 2022.
- **Evidence:** [product page](https://www.ospo.noaa.gov/products/land/hms.html),
  [directory](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/),
  [robots.txt (satepsanone)](https://satepsanone.nesdis.noaa.gov/robots.txt),
  [robots.txt (OSPO)](https://www.ospo.noaa.gov/robots.txt).

### EPA AirData pre-generated files

Use · corrected · effort S · confidence high

- **Contents:** daily AQI by county and CBSA with the defining pollutant;
  daily PM2.5 (parameter 88101, FRM/FEM; 88502, non-FRM) and ozone by
  monitor; 1980–2026.
- **Coverage:** monitors in Ada, Canyon and the ring.
- **Endpoint:** a zipped CSV per year from the download page; the current
  year is partial.
- **Updates:** twice a year, in June and December (last June 25, 2026).
- **Size:** 88101 about 8–10 MB per national year, 88502 about 2 MB; the
  county AQI files are small.
- **License:** U.S. Government data.
- **robots.txt:** aqs.epa.gov: 404 (no rules).
- **Use cases:** smoke days (AQI over 100 defined by PM2.5) and ozone days
  per summer for Ada (16001) and Canyon (16027); a year-over-year heat and
  smoke calendar.
- **Personas:** gardener, hazard watcher, cyclist, parent.
- **Core pieces:** the readings contract, the time-series card.
- **Effort and risks:** small. It lags by months; use HMS (or AirNow, if
  keyed) for today. A PM2.5 data advisory accompanies recent 88101 files.
- **Verification:** schedule corrected from "late May and November" to
  June and December (the page's own wording).
- **Evidence:** [download page](https://aqs.epa.gov/aqsweb/airdata/download_files.html),
  [robots.txt](https://aqs.epa.gov/robots.txt).

### AirNow API

Needs owner action · confirmed · effort S · confidence medium

- **Contents:** current observations and AQI forecasts by reporting area.
- **Coverage:** the valley's reporting areas.
- **Endpoint:** a REST API with a free account and key (from its Log In
  page). Rate limits aren't stated on the docs home page.
- **Updates:** hourly. **Size:** small.
- **License:** the data are preliminary and shouldn't support regulation,
  trends, guidance or decisions; AQS/AirData are for those.
- **robots.txt:** www.airnowapi.org/robots.txt redirects (302) to
  `docs.airnowapi.org/robots.txt?robots.txt=`, which returns 403; a 4xx
  means no rules. docs.airnowapi.org/robots.txt returns the docs HTML (no
  rules). files.airnowtech.org: 404.
- **Use cases:** today's air for garden work; smoke alerts in the yard
  card.
- **Personas:** gardener, hazard watcher, cyclist.
- **Core pieces:** the readings contract.
- **Owner action:** getting the key. The terms rule out trends, so history
  stays with AirData. Best owned by the hazards plugin and shared.
- **Verification:** the key requirement and data-use wording confirmed on
  the docs page (added to the evidence); the robots.txt redirect chain
  confirmed.
- **Evidence:** [docs](https://docs.airnowapi.org/),
  [robots.txt (www)](https://www.airnowapi.org/robots.txt),
  [robots.txt (docs)](https://docs.airnowapi.org/robots.txt),
  [robots.txt (files)](https://files.airnowtech.org/robots.txt).

### NWS API (api.weather.gov)

Avoid · confirmed · effort S · confidence high

- **Contents:** alerts (Frost Advisory, Freeze Warning, Heat Advisory, Air
  Quality Alert), point forecasts and observations as JSON; US-wide;
  updated within minutes.
- **Endpoint:** REST, no key (a User-Agent is requested).
- **License:** U.S. Government data.
- **robots.txt:** api.weather.gov: `User-agent: *`, `Disallow: /`
  (everything; rechecked Oct 7). alerts.weather.gov was unreachable.
- **Use case:** frost and heat alerts for the yard.
  **Personas:** gardener, weather watcher. **Core pieces:** none.
- **Risks:** our robots.txt rule forbids automated use even though it's an
  API. This affects the weather and hazards plugins too. Use the tgftp text
  products or IEM instead, or the owner asks NWS.
- **Verification:** robots.txt re-read.
- **Evidence:** [robots.txt](https://api.weather.gov/robots.txt).

### NWS text products on tgftp (frost, freeze, heat)

Use · confirmed · effort M · confidence medium

- **Contents:** folders by product type: `fire_weather`, `flash_flood`,
  `flood`, `lake_shore`, `non_precip`, `severe_weather_stmt`,
  `special_marine`, `special_weather_stmt`, `thunderstorm`, `tornado`,
  `tsunami`, `tsunami_seismic_msg`, `urgent_weather_message`. Frost
  Advisory, Freeze Warning and Heat Advisory are non-precipitation (NPW)
  products by convention ⚠️; the folder contents weren't opened.
- **Coverage:** NWS Boise's zones covering Ada, Canyon and the ring.
- **Endpoint:** a plain HTTPS directory of current text products with VTEC
  codes; poll every 10–15 minutes in the growing season.
- **Updates:** as issued. **Size:** a few KB per product.
- **License:** U.S. Government data.
- **robots.txt:** tgftp.nws.noaa.gov/robots.txt answers 301 to
  `/robots.txt/`, which is a 404: no rules. IEM (mesonet.agron.iastate.edu)
  has rules without a User-agent line: Crawl-delay 120, and disallows
  `/usage/`, `/tmp/` and some `/data/` and `/archive/` paths.
  mapservices.weather.gov was unreachable, so it's treated as disallowed.
- **Use cases:** frost-tonight and heat alerts in the yard card and the
  Valley Feed; a history of first and last frost advisories (which shows
  NWS's issuing policy, not actual frost).
- **Personas:** gardener, farmer, weather watcher.
- **Core pieces:** the lifecycles contract, the Valley Feed.
- **Effort and risks:** medium (VTEC parsing). NWS issues frost and freeze
  products only within its defined growing season ⚠️. The hazards and
  weather plugins should own this.
- **Verification:** folder list confirmed. robots.txt detail corrected
  (a 301 to a 404 rather than a plain 404; same outcome).
- **Evidence:** [directory](https://tgftp.nws.noaa.gov/data/watches_warnings/),
  [robots.txt (tgftp)](https://tgftp.nws.noaa.gov/robots.txt),
  [robots.txt (IEM)](https://mesonet.agron.iastate.edu/robots.txt),
  [robots.txt (mapservices)](https://mapservices.weather.gov/robots.txt).

### Landsat Collection 2 Level-2 surface temperature (Planetary Computer)

Use · corrected · effort M · confidence medium

- **Contents:** surface temperature from Landsat 4, 5, 7, 8 and 9 since
  Aug 22, 1982. Assets: `lwir11` (TIRS band 10, 100 m native, Landsat 8
  and 9) and `lwir` (`ST_B6`: Landsat 4–5 at 120 m native, Landsat 7 at
  60 m), all delivered on a 30 m grid.
- **Coverage:** global, including the ring. A 16-day revisit per satellite
  (8 days with Landsat 8 and 9 together), with a morning overpass.
- **Endpoint:** STAC search plus cloud-optimized GeoTIFFs signed with
  Planetary Computer's anonymous SAS tokens.
- **Updates:** every 8–16 days. **Size:** tens of MB per clipped summer
  composite.
- **License:** public domain (USGS data policy); the STAC field says
  "proprietary".
- **robots.txt:** planetarycomputer.microsoft.com: no rules.
- **Use cases:** a summer heat map by neighborhood; hot playgrounds,
  parking lots and streets for tree-planting priority.
- **Personas:** urban forester, parent, gardener, cyclist.
- **Core pieces:** the layer system.
- **Effort and risks:** medium. The overpass is late morning, not the
  afternoon peak, and it measures the surface, not the air.
- **Verification:** collection metadata confirmed. Minor correction: 100 m
  native applies only to Landsat 8 and 9.
- **Evidence:** [collection](https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2),
  [robots.txt](https://planetarycomputer.microsoft.com/robots.txt).

### Boise urban heat studies

Needs owner action · corrected · effort S · confidence low

- **Contents:** three separate efforts, none with published data that we
  found:
  1. the Treasure Valley Urban Heat Watch report (CAPA Heat Watch),
     published 2019, from sensors on volunteers' cars during a one-day
     campaign;
  2. ground-level heat data in the Borah neighborhood in summer 2024
     (Community Forest Corps with the Center for Regenerative Solutions),
     with a report promised for late 2024;
  3. a City of Boise Climate Action volunteer campaign announced on Aug 5,
     2025 for the following week.
- **Coverage:** Boise (the 2019 traverse routes, the Borah neighborhood,
  the 2025 city campaign).
- **Endpoint:** none found; the canopy report and the 2025 article only
  describe the studies. Key or account, license: unknown.
- **robots.txt:** not applicable until a data endpoint is known.
- **Updates:** one-off campaigns. **Size:** small.
- **Use case:** an afternoon air-temperature map to calibrate heat-day
  estimates by neighborhood.
- **Personas:** urban forester, parent, gardener.
- **Core pieces:** the layer system.
- **Owner action:** ask TVCN or the City whether the data can be shared.
  Traverse data are one-day snapshots.
- **Verification:** the researcher's 2025 dates (Jul 8–Aug 13) and
  partners (CAPA) aren't supported: the Boise State Public Radio piece names
  only the city's Climate Action team and an August 2025 timing, and the
  canopy report documents the 2019 and 2024 efforts. The entry was
  rewritten to match.
- **Evidence:** [Boise State Public Radio, Aug 2025](https://www.boisestatepublicradio.org/show/idaho-matters/2025-08-05/boise-urban-heat-treasure-valley-climate-change),
  [canopy report](https://cityofboise.org/media/19160/boise-tree-canopy-assessment-2013-2021-final-20240910.pdf),
  [hub search](https://opendata.cityofboise.org/api/search/v1/collections/all/items?q=canopy).

---

## Ideas by persona

From the research pass, with the review's caveats added. None is approved;
see [chapter 16](../16-ideas-and-personas.md) for the wider persona list.
Short source names refer to the entries above.

### Gardener

1. **"My yard" card** (the owner's private `home` plugin). The owner draws
   beds on the map, stored only in the private schema. Each bed shows:
   - sun hours by month as 12 bars labeled full sun, part sun, part shade or
     shade (6+, 4–6, 2–4, under 2 h);
   - last spring frost at 10, 50 and 90%, first fall frost, frost-free
     days;
   - the hardiness half-zone, with the "not the official map" disclaimer;
   - the soil map unit, texture, pH, drainage, water-holding capacity and
     depth to hardpan;
   - the yard's irrigation organization with this year's canal on and off
     dates;
   - this week's lawn water need;
   - last summer's heat days and smoke days against normal.

   Sources: 3DEP lidar, sun algorithms, NCEI normals, ACIS, PHZM, SSURGO,
   AgriMet charts, IDWR organizations, canal announcements, HMS, AirData.
   Core: private plugins, sun ephemeris module, surface-model tiles,
   readings, lifecycles, layer system.
2. **Shadow scrubber in 3D.** Drag the replay clock and watch real shadows
   from buildings, trees and terrain sweep across the yard, with one-tap
   dates (Mar 20, Jun 21, Sep 22, Dec 21, today) and a leaf-off switch that
   thins deciduous shade from November to April. Timing it by this year's
   NPN leaf-out date needs NPN's written OK; until then, an ACIS GDD proxy.
   Sources: 3DEP lidar, CHMv2, sun algorithms, NPN. Core: 3D engine, full
   replay, sun ephemeris module, surface-model tiles.
3. **Digital solar site survey.** Click any spot for a polar sun-path
   diagram with the skyline drawn from the surface model (foothills, roofs,
   tree crowns), month arcs and hour marks, to read which obstacle blocks
   the sun at what time of year (a Solar Pathfinder on screen). The same
   horizon gives a sky-view factor for frost risk. Sources: 3DEP lidar, sun
   algorithms. Core: sun ephemeris module, surface-model tiles, 3D engine.
4. **Frost tonight, tuned to the yard.** When NWS issues a Frost Advisory
   or Freeze Warning for the zone, a toast and a Valley Feed item appear.
   Each bed also carries a cold-pocket rating from its sky-view factor
   (open beds radiate and frost first; beds under eaves or trees later)
   and cold-air drainage on the 1 m DEM (low spots near the river and
   canals pool cold air). Sources: tgftp text products, 3DEP lidar, ACIS,
   PRISM. Core: Valley Feed, lifecycles, surface-model tiles, private
   plugins.
5. **What can I plant this week.** Growing degree days since Jan 1 against
   normal, the chance of another freeze after today from the station's
   freeze probabilities, the bed's spring sun hours as a soil warm-up hint,
   and links to the UI Extension planting guide (links only). Sources:
   ACIS, NCEI normals, NPN (or ACIS GDD until NPN agrees), UI Extension.
   Core: readings, sun ephemeris module.
6. **Warm-wall finder.** The house's south- and west-facing walls ranked by
   sun hours and afternoon heat, for figs, tomatoes or espalier fruit, from
   facade orientation (footprint) and roof shape (lidar). Sources: 3DEP
   lidar, sun algorithms. Core: surface-model tiles, private plugins.
7. **Tree growth over time** for the owner's own trees: canopy height from
   the 2019–20 flight against 2023–24, and how that changed each bed's June
   sun hours. Caveats from the review: it works only where QL2 actually has
   points (unconfirmed under the QL1 cities); density and leaf state
   differ, so report only changes over about 2 m (an example like "gained
   about 1.8 m" is inside the error), compare same-season tiles, and show
   error bars. Sources: 3DEP lidar. Core: surface-model tiles, private
   plugins.

### Gardener or landscaper

8. **Watering coach.** "Water about 1.1 inches this week" (an example) from
   AgriMet's LAWN row at Nampa or Parma, minus rain measured nearby (COOP
   and CoCoRaHS through ACIS), shown with the district's rotation day and
   whether pressurized irrigation is on. A season chart compares this
   year's ET with history: AgriMet's own yearly ET summaries, or gridMET
   after converting between Kimberly-Penman ETr and ASCE ETo. Sources:
   AgriMet charts, ACIS, CoCoRaHS, gridMET, canal announcements. Core:
   readings, time-series card.

### Gardener or homeowner

9. **"Plant a tree here" what-if.** Drop a virtual tree (mature height,
   crown width, deciduous or evergreen) and see month by month how it would
   shade the west windows and patio in July and whether beds keep their
   winter sun; computed in the browser from the surface model, nothing
   saved outside the private plugin. Sources: 3DEP lidar, sun algorithms.
   Core: 3D engine, surface-model tiles, private plugins.

### Homeowner or land buyer (private, with parcels)

10. **"Garden potential" page** for a property the owner is considering:
    sun hours over the lot, soils and hardpan depth, the irrigation
    organization and whether pressurized irrigation serves it, frost dates,
    and heat and smoke statistics. Shown only to the owner, never saved into
    shared views or exports. Sources: 3DEP lidar, SSURGO, IDWR
    organizations, canal announcements, ACIS. Core: private plugins,
    search, areas.

### Community or school garden organizer

11. **Public garden layer.** Sun hours, soils and irrigation organization
    for community gardens, school gardens and parks (from OpenStreetMap),
    at full detail because it's public land. A "candidate site" mode ranks
    city-owned open land by sun, soil and canal access. Sources: 3DEP
    lidar, SSURGO, IDWR organizations. Core: regular OSM load, search,
    layer system, surface-model tiles.

### Urban forester or Treasure Valley Canopy Network volunteer

12. **Shade-gaps layer.** Sidewalks, bike lanes and bus stops in full sun at
    5 PM in July, over Landsat summer surface-temperature hot spots and the
    2019-to-2023 canopy change, ranking street-tree planting spots on
    public right-of-way only. Sources: 3DEP lidar, Landsat, Boise canopy
    assessment, CHMv2. Core: regular OSM load, layer system, surface-model
    tiles.

### Transit rider (transit plugin)

13. **Shade at every VRT stop** by month and hour, from real shadows, with
    the summer heat-day count: "stops with no shade at 5 PM in July". A
    better version of chapter 16 §16.3's canopy-over-stop idea. Sources:
    3DEP lidar, sun algorithms, ACIS. Core: surface-model tiles, layer
    system.

### Cyclist

14. **Coolest ride.** The share of the Greenbelt and bike routes in shade at
    your departure time, with heat-day and smoke warnings, so a July
    evening ride can pick the tree-lined path. Sources: 3DEP lidar, sun
    algorithms, AirData, HMS. Core: regular OSM load, surface-model tiles,
    sun ephemeris module.

### Parent

15. **Playground shade and surface heat** in public parks at 3 PM in July:
    which play areas are shaded and which sit on hot surfaces (Landsat's
    late-morning overpass makes the heat part a proxy). Sources: 3DEP
    lidar, Landsat. Core: regular OSM load, surface-model tiles.

### Farmer (farm plugin)

16. **Field card.** Crop ET from the nearest AgriMet chart, GDD for pest
    timing, freeze probabilities for orchards, the soil's farmland class,
    and the irrigation organization with its canal season. Sources: AgriMet
    charts, NPN (or ACIS GDD), NCEI normals, SSURGO, IDWR organizations,
    canal announcements. Core: readings, lifecycles, areas.

### Native-plant and pollinator gardener

17. **Is spring early this year.** The Spring Index leaf and bloom anomaly
    for the valley, AGDD against normal, Pheno Forecasts for pests, the
    hardiness zone, and the Japanese beetle program area in Caldwell with
    its treatment dates. A "don't move plants or soil" reminder waits until
    its wording is confirmed (ISDA's page doesn't state it). Sources: NPN
    (needs its written OK), PHZM, ISDA. Core: layer system, lifecycles.

### Landscaper or water-wise homeowner

18. **Canal season countdown** in the Valley Feed (for example "NMID:
    Ridenbaugh Canal on Apr 1–8", with the date it was announced), shutoff
    notices, and a per-district history of on and off dates that shows
    drought-shortened seasons. Sources: canal announcements, IDWR
    organizations, WD63 (needs the watermaster's permission). Core: Valley
    Feed, lifecycles, evidence and review.

### Hazard watcher (hazards plugin)

19. **Smoke and heat calendar.** Each summer as a strip of days colored by
    HMS smoke overhead, PM2.5 AQI over 100 in Ada and Canyon, and days at
    or above 95 and 100 °F, year over year. Sources: HMS, AirData, ACIS.
    Core: readings, time-series card.

### Sky watcher (sky plugin)

20. **Same shadow engine, sky questions:** when sunrise first clears the
    foothills at a spot, sunset shadows of downtown towers, and the camera
    glare calendar ([chapter 11](../11-camera-validation-layer.md)) from
    one shared sun module. Sources: sun algorithms, 3DEP lidar, NSRDB.
    Core: sun ephemeris module, 3D engine, full replay.

### Weather watcher

21. **Cloud-weighted sun.** Each bed's clear-sky sun hours scaled by typical
    cloud and winter fog per month, so December reads realistically low for
    valley inversions; later the live 3D weather (chapter 16, §16.5) can dim
    the shadow scrubber on cloudy days. Sources: NSRDB, sun algorithms.
    Core: sun ephemeris module, 3D engine.

---

## Design notes

The researcher's proposed design, with the review's corrections applied.
**Nothing here is decided.**

### Where it lives (proposal)

- **A public `gardening` plugin:** frost and growing-season statistics,
  hardiness, a soils layer, ET readings, canal-season lifecycles, heat and
  smoke statistics, phenology, and shade layers for public land only
  (streets, sidewalks, bike routes, bus stops, parks, school and community
  gardens).
- **The private `home` plugin** ([chapter 15](../15-plugins.md), §15.3 and
  §15.7) holds everything about the owner's place: the yard outline, beds,
  notes, the owner's sensors, per-bed results and any what-if trees. Its
  schema is private (`private_home`): never in this repo, published tiles,
  exports or screenshots. The owner's home location is private information
  in the same way as the network details in [CLAUDE.md](../../CLAUDE.md).
- **Two pieces should be core** by the §15.1 rule (several plugins need
  them):
  1. A **sun ephemeris module**: one implementation in TypeScript (suncalc,
     BSD-2, or a port of the NOAA/Meeus equations) and one in
     standard-library Python (NOAA equations), cross-tested, so the map,
     the server, the camera glare calendar, sky, commuter glare and
     gardening agree.
  2. **Surface-model tiles** in `basemap/`: heights above ground (nDSM) for
     canopy and structures, encoded like the terrain tiles (terrain-RGB as
     lossless WebP), plus a canopy-only and a structure-only mask.
     Gardening (shade), land cover (3D trees, chapter 16 §16.3), transit
     (stop shade), sky (shadows) and camera calibration all use it.

### Building the surface model (build time, `basemap/`)

- **Input:** 3DEP point clouds. QL2 (2019–20) streams from the EPT bucket,
  so a first pass could cover one neighborhood with no bulk download, but
  only if QL2 actually has points there: check the WESM index polygons
  first. QL1 (2023–24, 8+ points/m²) has no EPT copy and needs the roughly
  160 GB LAZ download (owner's OK).
- **Classes:** the delivered class list is unverified ⚠️. Sample one EPT
  node's class histogram before designing the tree/structure split; if
  classes 3–6 (vegetation, buildings) exist, use them. Otherwise: drop
  noise, take height above ground from class 2 (PDAL `filters.hag_nn`, or
  against our 1 m DEM), and rasterize the maximum height at 0.5 m (QL1) or
  1 m (QL2).
- **Trees against structures:** NAIP 2025 NDVI (from the near-infrared
  band) plus multiple returns mark vegetation; a lidar planarity test marks
  roofs; thin tall objects (poles, wires) are dropped. Overture footprints
  could also mark buildings, but see licensing below.
- **Building heights** from lidar replace Overture's where they're missing
  (17%) or wrong; roof shape comes for free.
- **Licensing:** a truly public-domain surface model has to split
  structures by lidar alone (planarity, returns) plus NAIP NDVI. Using
  Overture footprints as the building mask, or mixing in Overture heights,
  makes the result derived from ODbL data: a published raster would be a
  Produced Work needing OpenStreetMap/Overture credit, and published
  per-building tables would be an ODbL derivative database ⚠️. Boise's 3D
  buildings (2019 LiDAR, [chapter 9](../09-base-map-data.md)) are another
  height source, but their terms are unknown.
- **Leaf state:** QL1 was flown Sep 2023 to Aug 2024, so some tiles are
  leaf-off. Flag tiles by acquisition date (from the point timestamps).
  Where NDVI says tree but lidar height is low, fill from CHMv2
  (CC BY 4.0) and mark it estimated.
- **Tools:** PDAL (BSD) joins GDAL and numpy, which `basemap/` already uses
  (`terrain_reencode.py`). It's a build-time dependency, not an ingest one,
  so the standard-library-only ingest rule stands.
- **Size:** the urban area is about 1,000 km²; at 0.5 m that's about
  4 billion cells (the box is about 8,400 km² and could be 1–2 m outside
  town). An urban nDSM isn't mostly zeros (roofs and canopy cover much of
  town, and lidar leaves residual noise), so expect 1–4 GB of tiles ⚠️
  unless heights under about 1.5–2 m are zeroed and values quantized to
  0.1–0.25 m. 0.5 m needs z17 with 512-px tiles (about 0.43 m per pixel at
  43.6°N): roughly 2×10⁴ tiles for 1,000 km², plus overviews.

### Sun hours and shadows

- **In the browser** (no server work): the 3D engine treats terrain plus
  nDSM tiles as one heightfield and draws shadows for the sun at the replay
  clock's time. For sun hours it renders K sun positions (for example every
  15 minutes on the 21st of the month) into a float accumulation texture
  over the visible area (about 500 m square), which makes what-if edits
  (a virtual tree) instant.
  - A shadow-map pass from the sun's view is usually cheaper than
    ray-marching every pixel for each of about 50 sun positions × 12
    months.
  - Float accumulation needs WebGL2 with `EXT_color_buffer_float`.
  - Load an apron of surface tiles well beyond the view: at 43.6°N the noon
    sun on Dec 21 is only about 23° up, and at 5° elevation a 30 m
    building's shadow runs about 340 m.
- **On the server** (public layers and caching): a horizon-angle method
  (32–64 azimuths, a search radius of about 300 m in town; a terrain
  horizon from the 10 m DEM over the ring, which catches the foothills and
  the Owyhees), integrated over the sun's path per month. Horizons over the
  ring must correct for Earth's curvature and refraction: the drop is about
  d²/2R, roughly 8 m at 10 km and about 380 m at 70 km (the Owyhees),
  before refraction. Tools: WhiteboxTools `TimeInDaylight` (MIT, now legacy
  upstream ⚠️), GRASS `r.sun` or `r.sunhours` (GPL, fine to run as a tool
  ⚠️), or our own numpy code. Compute per tile on demand and cache; no
  valley-wide 0.5 m precompute.
- **Conventions:** suncalc returns azimuth in radians from south, positive
  toward west, while NOAA and SPA measure from north; suncalc's altitude
  omits atmospheric refraction, while NOAA's equations add it (about 0.5°
  at the horizon) ⚠️ (from memory of the suncalc source). Fix both in core.
- **Leaf-off:** bare deciduous canopy lets light through. A monthly
  transmissivity (leaf-on between this year's leaf-out and fall, leaf-off
  otherwise; roughly 50–70% transmission when bare ⚠️, a literature value
  to verify) keeps winter numbers honest. Leaf-out from NPN needs its
  written OK; otherwise an ACIS GDD proxy.
- **Checks:** predicted shadows against camera frames at known times
  (which also feeds the camera validation layer), and against NAIP 2025
  shadows. NAIP metadata give the date per quarter-quad but often not the
  time of day ⚠️, so infer the sun's azimuth from building shadows first.
- **Labels:** full sun 6+ h, part sun 4–6, part shade 2–4, shade under 2:
  the usual nursery thresholds.

### Frost and growing season

- **Station truth:** NCEI normals give freeze probabilities (36, 32 and
  28 °F at 10, 50 and 90%) and growing-season length for valley stations.
  ACIS gives each year's actual last and first freeze, keyless: reduce
  `last_le_32` with duration `std` and season_start `7-1`, plus `normal`
  `91` or `91departure` for 1991–2020. The researcher's Boise Air Terminal
  sample (last spring 32 °F freeze 2016–2026: Mar 28 to May 13, median
  Apr 17; not re-run ⚠️) against secondary sites' "about May 4" ⚠️ shows
  why the card must name the station and the threshold.
- **From station to yard:** shift by the difference in PRISM's 800 m daily
  normal minimum temperature between the yard and the station, then by a
  cold-pocket term from the DEM (topographic position, cold-air drainage
  toward the river and canal bottoms) and the bed's sky-view factor from
  the surface model. Show a range and the station used, through core's
  evidence and confidence. NCEI's gridded normals (ACIS `ncei-norm:91-20`)
  are a public-domain alternative to OSU-owned PRISM grids.
- **Hardiness:** the 2023 PHZM shapefile restyled in our palette counts as
  altered, so it needs the "not the official USDA Plant Hardiness Zone Map"
  disclaimer and no USDA or OSU logos. Credit OSU's PRISM Group and
  USDA-ARS.

### Soils

- Soil Data Access on demand for the owner's points (SQL over `post.rest`,
  keyless, public domain), and a public soils layer from map-unit polygons
  (SDA WFS, or gSSURGO by hand), styled by drainage, pH or texture, with
  the valley's alkaline, calcareous soils and duripans called out.
- Re-pull every October after the annual refresh (said to be Oct 1 ⚠️).
- Don't use UC Davis SoilWeb: it duplicates SDA, and its robots.txt blocks
  AI crawlers by name.

### Water

- **AgriMet charts:** one GET per station each morning after 6:30 MT
  (`nmpich`, `pmaich`; `boiich` is nearly empty), April to October, into
  `raw.record` and readings (one series per crop row, LAWN first). Past
  seasons come from the static yearly summaries (`{stn}{yy}et.txt`) and
  `ETtotals.html`, also allowed. Only weather and soil-temperature history
  and Hydromet sit under the disallowed `/pn-bin` and RISE API; for those,
  an owner request to Reclamation or a one-off hand download.
- **gridMET** reference ET (CC0-style; direct files, never THREDDS) fills
  longer history: pull completed years once. Its ASCE ETo/ETr isn't the
  charts' Kimberly-Penman ETr, so convert before comparing.
- **Canal seasons:** a lifecycle per organization per year (announced,
  water in canal, delivery, shutoff), entered by hand from each
  organization's page with the source URL and the date we read it. The yard
  maps to an organization through IDWR's polygons. No scrapers or
  schedules: these are seasonal one-off checks. The Boise Project's site is
  boiseproject.net (its pages are also on nyid.org); Nampa's site is
  behind a Cloudflare challenge (by hand only).
- **The real signal** would be Water District 63's diversion telemetry
  (said to be login-only ⚠️): an owner request. IDWR's annual WD63
  accounting PDFs (1986–2026) may give per-canal season history ⚠️ (not
  opened).
- **USGS canal gauges** belong to the water plugin: 13203200 (New York
  Canal at Cloverdale) is inactive. The new api.waterdata.usgs.gov
  disallows `/ogcapi/*/collections/*/items*` for robots; the legacy
  waterservices host has no robots.txt but is being retired ⚠️.

### Heat, smoke and alerts

- Heat days and warm nights from ACIS counts; spatial heat from PRISM
  normals and Landsat surface temperature (public domain, via Planetary
  Computer).
- Smoke days from HMS polygons (daily) and EPA AirData's daily AQI by
  county (Ada 16001, Canyon 16027; files refreshed in June and December).
  Live AQI needs AirNow's key, which the hazards plugin should own; its
  terms rule out trends, so history stays on AirData.
- api.weather.gov's robots.txt is `Disallow: /` for everyone, which under
  our rule blocks NWS alerts and forecasts for every plugin. Alternatives:
  the tgftp text products (no rules; the `non_precip` folder for Frost
  Advisory, Freeze Warning, Heat Advisory) or IEM's archive (Crawl-delay
  120). NWS renamed Excessive Heat products to Extreme Heat in 2025 ⚠️
  (from memory), so parse both VTEC codes. This is a cross-plugin decision
  for the owner.

### Privacy

- Per-house analysis is for the owner's own place, in the private plugin
  only. If the site ever has guests, they see residential sun hours only
  aggregated to block level or cells of 50 m or more (10 m cells are still
  yard-scale, since lots are about 15–25 m wide), full detail only on
  public land, and can't search an address into yard analysis.
- Never attach owners' names or Assessor attributes to shade, soil or tree
  results. Parcel lines come only from the private Assessor copy and only
  in the owner's view. The Boise canopy assessment summarizes to parcels:
  take only the raster, never parcel tables.
- Volunteer-site data (CoCoRaHS gauges, Nature's Notebook sites) are
  smoothed or rounded to about 1 km, never named pins. ISDA's beetle
  treatment is shown as the program area, never treated households.
- Lidar shows backyard structures. Derived layers are public-domain facts,
  but we don't join them to identities or publish yard-level products for
  other people's properties.

### robots.txt summary (checked Oct 7, 2026, with the project User-Agent)

| Result | Hosts |
|---|---|
| Allowed (no rules, or our paths allowed) | data.rcc-acis.org (404); www.rcc-acis.org (empty Disallow); www.ncei.noaa.gov `/access/services/data/v1`; sdmdataaccess (both hosts), websoilsurvey and soilseries (404); prism.oregonstate.edu, services.nacse.org, ftp.prism.oregonstate.edu (404); www.usbr.gov `/pn/agrimet/chart/`; www.northwestknowledge.net (404); gis.idwr.idaho.gov and et-idwr.idaho.gov (302 to an error page, no rules); idwr.idaho.gov (empty Disallow); data-idwr.hub.arcgis.com (Crawl-delay 60); nmid.org; pioneerirrigation.com; cityofboise.org; opendata.cityofboise.org (Crawl-delay 60); cityofcaldwell.org `/Departments/Irrigation`; nyid.org; www.boiseproject.net (404); geoserver.usanpn.org (404); satepsanone.nesdis.noaa.gov (404); www.ospo.noaa.gov; aqs.epa.gov (404); airnowapi.org (4xx); tgftp.nws.noaa.gov (301 to a 404); www.uidaho.edu; agri.idaho.gov (empty); planetarycomputer.microsoft.com; giscenter.rdc.isu.edu (404); developer.nlr.gov (empty); nsrdb.nlr.gov. S3 buckets: not applicable |
| Disallowed | www.usbr.gov `/pn-bin`; data.usbr.gov `/rise/api` and query pages; thredds.northwestknowledge.net (all); api.weather.gov (all); openet-api.org and developer.openet-api.org (all); api.waterdata.usgs.gov data items; www.ncei.noaa.gov `/data*` and `/orders*`; uspest.org model and data paths; www.cocorahs.org `/viewdata/`; www.nrcs.usda.gov query URLs and `/search*`; SoilWeb for named AI crawlers (our `*` group blocks only `/application/*`; skipped anyway) |
| With a crawl delay | IEM (mesonet.agron.iastate.edu): Crawl-delay 120, plus `/usage/`, `/tmp/` and some `/data/` and `/archive/` paths disallowed |
| Unreachable, treated as disallowed | rockyweb.usgs.gov, boiseproject.org, mapservices.weather.gov, alerts.weather.gov |
| By hand only | cityofnampa.us (403 behind a Cloudflare challenge) |

### Suggested order (not decided)

1. **(S) Yard card without shade:** ACIS and NCEI frost, SDA soil at a
   point, PHZM, the IDWR organization plus hand-entered canal dates,
   AgriMet chart readings and AgriMet's yearly ET summaries as history.
   Needs the readings and lifecycles displays and a skeleton of the private
   `home` plugin.
2. **(M) Core sun ephemeris** plus browser shadows from Overture buildings
   and terrain only (no trees yet) in the 3D engine, on the replay clock.
3. **(L) Surface model from lidar:** QL2 EPT for one neighborhood first,
   only if QL2 covers it; then QL1 tiles after the owner OKs the download;
   trees in shadows; sun-hours accumulation; leaf-off handling with an
   ACIS-GDD leaf-out proxy (NPN's leaf-out only after it approves automated
   access).
4. **(M) Public layers:** stop, sidewalk and park shade; the heat and smoke
   calendar; phenology; Landsat heat; CHMv2 gap fill.

---

## Review corrections to the design

What the Oct 7 check changed in the researcher's design (all applied
above):

1. **QL2 coverage:** the "QL2 first, one neighborhood" plan assumed QL2
   covers it. Chapter 9's index puts most cities under QL1; QL2's EPT
   bounds span the box, but bounds aren't coverage. Check the WESM polygons
   before promising a QL2-first pass, canopy change or tree growth.
2. **Change detection is biased:** 2 against 8 points/m² (sparse data
   misses treetops) and both flights partly leaf-off. Report only changes
   over about 2 m, compare same-season tiles (`GpsTime` is in the schema)
   and show error bars.
3. **Classes are unverifiable** (rockyweb refused connections): sample an
   EPT node's class histogram first.
4. **Public domain needs tightening:** Overture footprints as the building
   mask also make the structure mask ODbL-derived; split by lidar plus NAIP
   NDVI for a public-domain model. Boise's 3D buildings have unknown terms.
5. **Size was optimistic:** 1–4 GB ⚠️ rather than 0.5–1 GB, unless low
   heights are zeroed and values quantized; z17 512-px tiles, about 2×10⁴
   for 1,000 km². The cell math was right.
6. **Sun conventions:** suncalc's azimuth origin and missing refraction
   differ from NOAA/SPA ⚠️; fix them in core. pvlib is a test oracle only.
   SPA moved to midcdmz.nlr.gov and can't be redistributed.
7. **Horizons over the ring** need Earth-curvature and refraction
   corrections (about 8 m at 10 km, about 380 m at 70 km).
8. **Browser shadows:** WebGL2 with `EXT_color_buffer_float`; a wide tile
   apron for long winter shadows; a shadow-map pass is cheaper than
   ray-marching.
9. **NAIP validation:** acquisition time of day is often missing ⚠️; infer
   azimuth from building shadows or use camera frames.
10. **Frost:** the ACIS method is confirmed; NWS frost products follow its
    growing-season policy ⚠️; NCEI gridded normals avoid OSU-owned grids.
11. **PRISM:** normals by hand only; the daily service is on
    services.nacse.org with a twice-in-24-h per-file limit; the old service
    ended Sep 30, 2025.
12. **AgriMet (the most important correction):** history doesn't need
    `/pn-bin`; static yearly ET files and 1988–2015 totals are allowed. The
    owner request is only for weather, soil temperature and Hydromet.
    Schedule after 6:30 MT, April to October; Parma's soil depths include
    20 in; Kimberly-Penman ETr isn't ASCE ETo/ETr.
13. **gridMET:** pull completed years once, not weekly re-downloads of the
    current-year file.
14. **Canal seasons:** the Boise Project's site is boiseproject.net; IDWR's
    WD63 PDFs are a lead for per-canal history ⚠️; 2026 was a shortened
    season (Caldwell shut down Sep 24).
15. **USA-NPN:** its terms forbid automated access without written
    approval; use an ACIS GDD proxy until then.
16. **Air and alerts:** AirData refreshes in June and December; AirNow
    data aren't for trends; parse both Excessive and Extreme Heat VTEC
    codes ⚠️.
17. **Privacy:** 10 m cells are yard-scale, so guests get block level or
    50 m+; canopy assessment raster only; beetle program area only.
18. **robots.txt details:** IDWR hosts redirect to an error page (no
    rules); nrcs.usda.gov also disallows query URLs and `/search*`; tgftp
    is a 301 to a 404; SoilWeb blocks named AI crawlers; services.nacse.org,
    ftp.prism.oregonstate.edu and boiseproject.net are 404;
    developer.nlr.gov is empty; cityofnampa.us is 403 (by hand only);
    rockyweb.usgs.gov and mapservices.weather.gov are still unreachable;
    api.weather.gov is still `Disallow: /`.
19. **Other source fixes:** Boise urban heat (2019 Heat Watch, 2024 Borah,
    2025 city campaign); the beetle area's east bound is Smeed Pkwy, with a
    2025 plan of 320 acres; CoCoRaHS is CC BY 4.0; CHMv2 includes
    observation dates.
20. **Order:** step 1 stands, with AgriMet's yearly ET summaries added;
    step 3's QL2-first pass depends on coverage; ACIS GDD replaces NPN until
    NPN approves.

---

## Open questions for the owner

1. **Split:** a public `gardening` plugin plus the private `home` plugin
   for the yard, beds and per-bed results?
2. **Core:** make the sun ephemeris module and surface-model (nDSM) tiles
   core, since sky, land cover, transit, cameras and gardening all need
   them?
3. **Lidar:** start by streaming the 2019–20 QL2 point cloud for one
   neighborhood (only if the WESM polygons show QL2 covers it), and later
   approve the roughly 160 GB 2023–24 QL1 LAZ download for the box? OK to
   add PDAL to the basemap build tools?
4. **NWS alerts:** api.weather.gov disallows all robots. Accept the tgftp
   text products (and IEM's archive at its 120 s crawl delay) for frost,
   freeze and heat alerts across plugins, or write to NWS?
5. **AgriMet:** ET history is on allowed static paths, but weather and
   soil-temperature history and Hydromet are under the disallowed `/pn-bin`
   and RISE API. Ask Reclamation (agrimet@usbr.gov) for permission, or do a
   one-off hand download of past seasons?
6. **City of Boise / TVCN:** ask for the 2021 high-resolution land cover
   from the 2013–2021 canopy assessment, and for any urban heat study data
   (2019, 2024, 2025)?
7. **Water District 63:** ask for a public read of its canal diversion
   telemetry as the real "canal water is on" signal?
8. **Privacy for any future guest view:** aggregate residential sun hours
   to block level or 50 m+ (the review found 10 m still yard-scale), with
   full detail only on public land? Any stricter rule wanted?
9. **Hardiness zones:** restyle in our palette with the required "not the
   official USDA map" disclaimer and no logos, or show the official look
   with the USDA-ARS and OSU logos?
10. **The owner's own sensors** for the `home` plugin: soil temperature or
    moisture probes, a rain gauge, a weather station? They'd fill the gaps
    left by the robots-blocked AgriMet soil temperatures.
11. **AirNow:** get the free key now for hazards and gardening, or rely on
    HMS smoke and EPA history until the hazards plugin is built?
12. **USA-NPN:** ask for written approval of automated access (for leaf-out
    and Spring Index), or stay with an ACIS GDD proxy?
13. **CHMv2:** it ships observation dates per tile, but the imagery is
    satellite-based and of a different year than the lidar. Is a canopy gap
    filler marked "estimated" acceptable?
14. **Soil moisture:** is an NRCS SCAN or other soil-moisture station near
    the valley worth checking (none found in this pass), or leave soil
    moisture to the owner's sensors?

See also: [chapter 17](../17-sources-for-new-plugins.md) (sources for the
new plugins), [chapter 16](../16-ideas-and-personas.md) (ideas by persona),
[chapter 15](../15-plugins.md) (core and plugins), [SOURCES.md](../SOURCES.md)
(the source backlog).
