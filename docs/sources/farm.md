# Farm sources (researched Oct 7, 2026)

Sources for a `farm` plugin: crop type by field, irrigation and canal water,
water rights, field burning, drought, farm weather and crop water use, and
farmland turning into subdivisions. The study area is the valley box
(W −117.05, S 43.00, E −115.95, N 43.85) and the proposed regional ring
(about W −117.30, S 42.90, E −115.60, N 44.30, roughly 21,300 km²;
[DECISIONS](../DECISIONS.md)); national sources reach Malheur County,
Oregon, while IDWR's layers stop at the Idaho line. This page belongs to
[chapter 17](../17-sources-for-new-plugins.md) (sources for the new
plugins); the ideas behind it are in
[chapter 16](../16-ideas-and-personas.md#farmer-farm).

**Status: research only; nothing here is approved.** Each source goes to
the owner one at a time before anything is built. Every entry was checked
against its official pages, robots.txt and terms on Oct 7, 2026: of the 29
sources, 17 were confirmed and 12 corrected; none was refuted outright or
left unverifiable. One claim was refuted: that Source Cooperative's copy of
the Crop Sequence Boundaries can stand in for NASS's 8-year crop history.
"Not re-run" marks figures from the research pass that verification didn't
repeat; ⚠️ marks anything resting on secondary sources, memory, or not
checked at all. One research request touched a robots-disallowed page (DEQ's
burn map); it is recorded under
[Requests made during the research](#requests-made-during-the-research).

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| **Crops and fields** | | | | | | | | |
| [Cropland Data Layer (CDL)](https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php) | USDA NASS | Crop type per pixel, yearly (Idaho since 2005); 30 m to 2023, 10 m from 2024; cultivated, frequency and confidence layers | CropScape services and WCS, national zips, SCINet ImageServer | None | Public domain; cite NASS | CropScape and SCINet no rules; nass.usda.gov allowed | Use | Corrected |
| [Crop Sequence Boundaries (CSB)](https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/index.php) | USDA NASS, with ERS | Synthetic field polygons with 8 years of crops (2018–2025 edition) | National zip, 3.76 GB | None | Public domain | Allowed | Use | Corrected |
| [Crop Progress Gridded Layers](https://www.nass.usda.gov/Research_and_Science/Crop_Progress_Gridded_Layers/index.php) | USDA NASS | Weekly progress and condition for corn, soybeans, cotton, winter wheat; 9 km; 2015 on | Yearly zips (46 MB for 2026) | None | Public domain | Allowed | Use (valley-wide timing only) | Corrected |
| [Sentinel-2 L2A on AWS](https://registry.opendata.aws/sentinel-2-l2a-cogs/) | ESA Copernicus; Element 84 and AWS | 10–20 m imagery every few days since mid-2015, for per-field NDVI | STAC API, then COGs on S3, unsigned | None | Copernicus "free, full and open"; credit | STAC 403, no rules; S3 not applicable | Use | Corrected |
| [FSA Common Land Units (CLU)](https://www.law.cornell.edu/uscode/text/7/8791) | USDA FSA | Official farm-field and tract boundaries | Not public | Partnership | Restricted by 7 U.S.C. 8791 | Unreadable (network error) | Avoid | Confirmed |
| **Farm statistics** | | | | | | | | |
| [Quick Stats bulk files and Census of Agriculture profiles](https://www.nass.usda.gov/datasets/) | USDA NASS | Every NASS statistic as gzipped text; county farms, acres, irrigation, sales, livestock | Static files (up to 1.05 GB each); PDFs | None | Public domain ⚠️ (no license text) | Allowed | Use | Confirmed |
| [Quick Stats API](https://quickstats.nass.usda.gov/api) | USDA NASS | The same statistics by query | REST, 50,000 records a request | Free key | API terms and a required attribution line | `Disallow: /` | Avoid | Confirmed |
| **Irrigation, canals and water rights** | | | | | | | | |
| [IDWR irrigation organizations](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/0) | IDWR | Service areas (59 organizations in the box); 1941 Boise Valley districts | FeatureServer; small zip | None | Disclaimer only; credit IDWR | No rules | Use | Confirmed |
| [IDWR season of use](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/SeasonOfUse/FeatureServer/0) | IDWR | Legal irrigation-season zones, plus headgate and consumptive-use maps | FeatureServer | None | Disclaimer only; credit IDWR | No rules | Use | Confirmed |
| [Irrigation district announcements](https://nmid.org/2025-season-start-up/) | Irrigation districts | Canal turn-on and shut-off dates | Read by hand twice a year | None | Facts; cite each district | nmid.org allowed (others not checked) | Use, by hand | Confirmed |
| [Treasure Valley Irrigation System](https://hydroshare.org/resource/24a5f761bf4f41fb9b872b130d9d1a3f) | HydroShare resource (network built at Idaho DEQ) | Named canal, lateral and drain network, 2022 | One 1.3 MB download behind a license click | None | CC BY 4.0 | Download path disallowed | Needs owner action | Confirmed |
| [IDWR water district diversions](https://gis.idwr.idaho.gov/hosting/rest/services/Compliance/DiversionDataSites/FeatureServer/0) | IDWR and watermasters | Diversion sites (WD 63, WD 65); daily diversion records; Aqua Info | FeatureServer; guest-login app; PDFs | None (guest login) | Disclaimer; provisional data | Allowed | Needs owner action | Corrected |
| [IDWR water rights](https://gis.idwr.idaho.gov/hosting/rest/services/Allocation/WaterRightPods/FeatureServer/0) | IDWR | Points of diversion and places of use: priority dates, uses, rates | FeatureServer; hub downloads | None | Disclaimer only; credit IDWR | No rules | Use (no owner names) | Confirmed |
| [IDWR wells](https://gis.idwr.idaho.gov/hosting/rest/services/Groundwater/Wells/FeatureServer/0) | IDWR | Well reports since July 1987: depth, water level, use | FeatureServer; hub downloads | None | Disclaimer only; credit IDWR | No rules | Internal only | Confirmed |
| **Crop water use, weather and drought** | | | | | | | | |
| [AgriMet crop water-use charts](https://www.usbr.gov/pn/agrimet/h2ouse.html) | Bureau of Reclamation | Daily ET by crop at 6 stations (the two Boise stations: lawn only) | Static text files | None | Federal ⚠️; provisional; credit Reclamation | Allowed | Use | Corrected |
| [AgriMet, Hydromet and RISE data services](https://www.usbr.gov/pn/agrimet/webarcread.html) | Bureau of Reclamation | Full weather archives; reservoir, river and canal flows | Form posts; RISE API | None | Federal; provisional | `/pn-bin` and `/rise/api` disallowed | Needs owner action | Confirmed |
| [IDWR METRIC ET](https://gis.idwr.idaho.gov/hosting/rest/services/ScientificRasters/ETData/MapServer) | IDWR, University of Idaho | Landsat ET, monthly and seasonal; Treasure Valley 1987–2015 only | MapServer; yearly zips | None | Disclaimer only; credit both | Allowed | Use | Corrected |
| [OpenET](https://etdata.org/terms-of-service/) | OpenET, Inc. | 30 m field ET, monthly from 2000, daily from 2016 | Data Explorer; API | Free key ⚠️ | Personal, noncommercial; no apps or robots without written consent | Only `/wp-admin/` disallowed, but the terms forbid scripts | Needs owner action | Confirmed |
| [U.S. Drought Monitor](https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx) | NDMC (UNL), USDA, NOAA, NASA | Weekly drought categories by county since 2000 | Statistics API; polygons under a disallowed path | None | Required credit line | API host no rules; `/data/` disallowed | Use (county statistics) | Corrected |
| [OSU IPPC degree-day models](https://uspest.org/robots.txt) | Oregon State University IPPC | Insect and disease degree-day models | Model pages | None | Not checked | Model paths disallowed | Avoid | Confirmed |
| [Plant Hardiness Zone Map service](https://pdi.scinet.usda.gov/image/rest/services?f=pjson) | USDA ARS; SCINet; PRISM (OSU) | Hardiness zones, about 326 m pixels, edition unknown | ImageServer | None | Not stated ⚠️ | No rules | Use (low confidence) | Corrected |
| **Farmland change and soils** | | | | | | | | |
| [IDWR irrigated lands](https://gis.idwr.idaho.gov/hosting/rest/services/IrrigatedLands) | IDWR | Irrigated, semi-irrigated and non-irrigated polygons for 8 years 1987–2015; a 2023 raster | MapServer per year; zip | None | Disclaimer only; credit IDWR | No rules; hub Crawl-delay 60 | Use | Corrected |
| [IDWR land use 1939, 1994, 2000](https://data-idwr.hub.arcgis.com/documents/IDWR::land-use-boise-river-basin-lower-1939) | IDWR | Land use from 1938/39 and later airphotos, with change layers | Static zips | None | Disclaimer; 1:24,000 or smaller | Allowed | Use | Confirmed |
| [Annual NLCD](https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database) | USGS EROS and MRLC; USFS (tree canopy) | Yearly 30 m land cover, change and impervious surface, 1985–2025 | MRLC viewer clips; ScienceBase | None | Public domain ⚠️ (not re-read) | Allowed | Use | Confirmed |
| [SSURGO via Soil Data Access](https://sdmdataaccess.nrcs.usda.gov/WebServiceHelp.aspx) | USDA NRCS | Soil map units with farmland class and soil properties | SQL REST; WFS and WMS | None | Federal ⚠️ (no license text checked) | No rules | Use | Confirmed |
| [AFT Farms Under Threat 2040](https://farmlandinfo.org/publications/farms-under-threat-2040/) | American Farmland Trust | Farmland conversion scenarios to 2040 | Report; data by request form | Account | Not stated ⚠️ | Allowed | Needs owner action | Confirmed |
| **Burning, livestock and range** | | | | | | | | |
| [DEQ crop residue burning](https://www.deq.idaho.gov/air-quality/smoke-and-burning/crop-residue-burning/) | Idaho DEQ | Daily burn decisions; field registrations; annual reports | Map (disallowed), email, phone | Account (email subscription) | None stated | `/air/crb/` disallowed | Needs owner action | Corrected |
| [ISDA herd districts](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer) | ISDA | Herd districts against open range, by county | ArcGIS Online FeatureServer | None | None stated; the Ada layer credits the Ada County Assessor's Office | 403, no rules | Use | Corrected |
| [ISDA dairies and CAFOs; EPA ECHO](https://agri.idaho.gov/animals/dairies-milk/) | ISDA; US EPA | No public ISDA list; ECHO holds only federally permitted CAFOs ⚠️ | Records request; ECHO bulk zips | Unknown | EPA public domain | `echodata` disallows all | Avoid | Confirmed |

**Verdicts:** 18 use, 1 internal only, 6 need an owner action, 4 avoid.

## Crops and fields

### USDA NASS Cropland Data Layer (CDL)

Use · verified: corrected · confidence high · effort M

- **Contents:** a yearly crop-specific land-cover raster with about 130
  classes (corn, alfalfa, sugarbeets, onions, mint, hops, dry beans, sweet
  corn, potatoes, winter and spring wheat, grass/pasture, fallow/idle), with
  the non-farm classes taken from NLCD. 30 m for 2008–2023 and 10 m from
  2024 (NASS also publishes 30 m resampled copies). From 2024 the classifier
  is Google Earth Engine's smileRandomForest. Idaho's CDL starts in 2005
  ([FAQ](https://www.nass.usda.gov/Research_and_Science/Cropland/sarsfaqs2.php)).
- **Companion layers:** the 2025 Cultivated layer (30 m, 300 MB, based on
  2021–2025); Crop Frequency 2008–2025 (corn, cotton, soybeans and wheat
  only; 2.0 GB); Confidence layers at 30 m for 2017–2023 and a 10 m one for
  2024 (linked from the release page on storage.googleapis.com).
- **Idaho 2023 accuracy**
  ([metadata](https://www.nass.usda.gov/Research_and_Science/Cropland/metadata/metadata_id23.htm)):
  FSA crops overall 82.7%, kappa 0.803. The overall figure excludes the
  classes sampled from NLCD, including Grass/Pasture, Canyon County's
  largest class, which has no accuracy figure at all.

  | Crop | Producer's | User's |
  |---|---|---|
  | Corn | 88.2% | 89.6% |
  | Alfalfa | 89.5% | 86.7% |
  | Sugarbeets | 92.1% | 93.9% |
  | Potatoes | 93.0% | 93.1% |
  | Hops | 81.5% | 89.6% |
  | Onions | 84.1% | 73.3% |
  | Mint | 70.9% | 83.7% |
  | Dry beans | 76.3% | 79.2% |
  | Sweet corn | 40.4% | 54.2% |

- **Canyon County 2025** (CropScape GetCDLStat, re-run Oct 7): corn
  43,553.1 ac, alfalfa 28,989.6, winter wheat 24,385.1, sugarbeets
  10,925.4, mint 9,086.2, dry beans 8,261.3, sweet corn 6,991.9, potatoes
  4,381.4. The research also gave onions 9,918 ac and hops 6,852 ac (not
  re-run). These statistics are computed on 30 m pixels: corn is 195,837
  pixels × 900 m² = 43,553 ac.
- **Access, five keyless routes:**
  1. **CropScape web services**,
     `nassgeodata.gmu.edu/axis2/services/CDLService/`: GetCDLStat,
     GetCDLValue, GetCDLFile and GetCDLComp, by FIPS code, bounding box,
     points or an uploaded area. Boxes and points are in EPSG:5070 metres,
     not longitude and latitude. Responses are XML holding a `returnURL`
     under `/webservice/nass_data_cache/`, and the JSON there has unquoted
     keys. Since the 2025 statistics are computed at 30 m, GetCDLFile
     probably returns the 30 m copy ⚠️ (inferred, not tested).
  2. **CropScape WMS and WCS** at
     `nassgeodata.gmu.edu/CropScapeService/wms_cdlall.cgi` (WCS 1.0.0 and
     2.0.1, coverage `cdl_<year>`, EPSG:5070). DescribeCoverage for
     `cdl_2025` reports a native 10 m grid, so this is the only keyless
     route to a 10 m clip found.
  3. **National zips** under
     `www.nass.usda.gov/Research_and_Science/Cropland/Release/datasets/`:
     2025 at 10 m 9.8 GB and at 30 m 1.9 GB; 2024 at 10 m 9.0 GB and at
     30 m 1.6 GB; earlier years about 1.8 GB.
  4. **USDA SCINet ImageServer**,
     `pdi.scinet.usda.gov/image/rest/services/CDL_WM/ImageServer`: 30 Web
     Mercator units (about 22 m on the ground here), so a resampled copy;
     `maxImage` 4097 × 4097; time extent 1997 to 2025-01-01.
  5. **CroplandCROS viewer** at `croplandcros.scinet.usda.gov`.
- **Coverage:** the lower 48 states, so both counties and the whole ring,
  including Malheur County, Oregon. Idaho from 2005, yearly to 2025.
- **License and terms:** public domain. The NASS FAQ calls it "considered
  public domain and free to redistribute"; cite it as the FAQ asks (USDA
  NASS, 20260227, Cropland Data Layer). The FAQ also says no farmer-reported
  data can be derived from it.
- **robots.txt:** `nassgeodata.gmu.edu` 404 (no rules);
  `www.nass.usda.gov` disallows only `/Quick_Stats/CDQT/`;
  `croplandcros.scinet.usda.gov` and `pdi.scinet.usda.gov` 404 (no rules).
  All re-checked Oct 7.
- **Updates and size:** yearly. The 2025 CDL came out Feb 27, 2026 and the
  2024 CDL Feb 27, 2025, so the 2026 CDL is likely around late February
  2027. A ring clip is about 213 million pixels at 10 m (an estimated
  20–40 MB compressed a year) and about 24 million at 30 m (about 3–5 MB);
  all 21 years come to roughly 150–300 MB before tiling (estimates).
- **Use cases:** crop type by field and year; a year slider of crops;
  per-field crop history (the majority class inside each CSB polygon);
  irrigated-crop context for ET and water use; harvest-season traffic
  context; farmland-loss checks against NLCD.
- **For:** farmers, history buffs, civic users and planners, gardeners (for
  neighbourhood context), 3D and weather viewers, commuters. **Needs:** the
  layer system, a raster tile pipeline in `basemap/` for categorical data
  (lossless, downsampled by mode or nearest), the year slider, legend and
  hover picking.
- **Risks:** resolution and method both break at 2024 (30 m to 10 m, and a
  new classifier), so a 2023-to-2024 change can be an artifact; use NASS's
  own 30 m copies for time series. Non-farm classes come from NLCD, so use
  NLCD for "developed", as the FAQ advises. Grass/Pasture has no accuracy
  figure; sweet corn and mint are weak. Colours must not rely on red and
  green alone ([ch. 13](../13-visual-design.md)). CropScape has been flaky
  (one earlier socket hang-up) but answered normally on Oct 7.
- **Verification:** confirmed the public-domain wording, the Idaho start
  in 2005, the 10 m change from 2024, the Feb 27, 2026 release, the Idaho
  2023 accuracy table, every robots.txt result and the Canyon 2025
  statistics (re-run). Corrected: CropScape boxes are EPSG:5070 metres (per
  the developer guide); CropScape's 2025 statistics are on 30 m pixels, so
  its files are probably not 10 m; the WCS route, with its native 10 m grid,
  was added; CDL_WM is a Web Mercator resample; a 2024 10 m confidence layer
  exists, so "confidence at 30 m to 2023" was incomplete; the overall
  accuracy excludes Grass/Pasture.
- **Evidence:** [FAQ](https://www.nass.usda.gov/Research_and_Science/Cropland/sarsfaqs2.php),
  [release page](https://www.nass.usda.gov/Research_and_Science/Cropland/Release/index.php),
  [Idaho 2023 metadata](https://www.nass.usda.gov/Research_and_Science/Cropland/metadata/metadata_id23.htm),
  CropScape developer pages ([examples](https://nassgeodata.gmu.edu/CropScape/devhelp/getexamples.html),
  [WMS](https://nassgeodata.gmu.edu/CropScape/devhelp/cdlwms.html),
  [web services](https://nassgeodata.gmu.edu/CropScape/devhelp/cropscapews.html)),
  [GetCDLStat for Canyon 2025](https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLStat?year=2025&fips=16027&format=json)
  and [its cached JSON](https://nassgeodata.gmu.edu/webservice/nass_data_cache/byfips/CDL_2025_16027.json),
  [WCS DescribeCoverage](https://nassgeodata.gmu.edu/CropScapeService/wms_cdlall.cgi?SERVICE=wcs&VERSION=1.0.0&REQUEST=DescribeCoverage&COVERAGE=cdl_2025),
  [SCINet services](https://pdi.scinet.usda.gov/image/rest/services?f=pjson),
  [CDL_WM](https://pdi.scinet.usda.gov/image/rest/services/CDL_WM/ImageServer?f=pjson),
  robots.txt for [nassgeodata](https://nassgeodata.gmu.edu/robots.txt),
  [NASS](https://www.nass.usda.gov/robots.txt),
  [CroplandCROS](https://croplandcros.scinet.usda.gov/robots.txt) and
  [SCINet](https://pdi.scinet.usda.gov/robots.txt).

### USDA NASS Crop Sequence Boundaries (CSB)

Use · verified: corrected · confidence high · effort M

- **Contents:** fully synthetic field polygons derived from the CDL stack,
  not from FSA's Common Land Units. The CDL is resampled to 10 m, road and
  rail lines are re-imposed, and polygons are simplified at a 60 m
  tolerance (Wang–Müller). Fields: `CSBID` (which encodes the window's start
  and end years), `CSBACRES`, `CDL2018`…`CDL2025`, `STATEFIPS`, `ASD`,
  `CNTY`, `CNTYFIPS`, `INSIDE_X`, `INSIDE_Y`. The 2018–2025 edition (rev23,
  released Mar 27, 2026) has 15,973,106 polygons. Size rule, per the
  metadata: polygons under 1 ha with two or more crop years are merged into
  their largest neighbour, and polygons over 1 ha need only one cropland year
  to be kept. NASS says the polygons hold no personal information,
  ownership boundaries or tax parcels. Earlier 8-year windows go back to
  2008–2015.
- **NASS's code** ([USDA-REE-NASS/crop-sequence-boundaries](https://github.com/USDA-REE-NASS/crop-sequence-boundaries))
  needs ArcGIS Pro 3.1, so we can't rebuild CSB from our own CDL clips.
- **Source Cooperative's copy is not equivalent.** Its
  `fiboa/us-usda-cropland` dataset is the 2016–2023 edition with adjacent
  polygons that share a 2023 crop dissolved (16,194,865 polygons). Its
  columns are only `id`, `crop:code`, `crop:name`,
  `administrative_area_level_2`, `determination_datetime` and
  `crop:code_list`, so it has no per-year crop history. GeoParquet 4.03 GB
  plus PMTiles 929.2 MB, EPSG:5070.
- **Access:** the national zip,
  [`NationalCSB_2018-2025_rev23.zip`](https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/datasets/NationalCSB_2018-2025_rev23.zip)
  (HEAD on Oct 7: 3,758,027,335 bytes, Last-Modified May 15, 2026): a file
  geodatabase in NLCD Albers, which needs GDAL's `ogr2ogr` to clip. Source
  Cooperative's GeoParquet
  (`data.source.coop/fiboa/us-usda-cropland/us_usda_cropland.parquet`) can be
  range-read, but gives only 2023 crops on dissolved outlines; whether its
  row groups are spatially sorted for efficient box reads is unverified ⚠️.
- **Coverage:** the lower 48 states, so all of Ada, Canyon and the ring,
  including Oregon. Crop years 2008–2025 across the editions.
- **License and terms:** public domain. The CSB 2025 metadata's use
  constraints say "considered public domain and free to redistribute";
  Source Cooperative's README and LICENSE.txt repeat NASS's statement.
- **robots.txt:** `www.nass.usda.gov` disallows only `/Quick_Stats/CDQT/`,
  so `/Research_and_Science/` is allowed. `source.coop` allows `/` but
  disallows `/api/` and `/*/*/`; the dataset page's path matches `/*/*/`, so
  don't script it. `data.source.coop/robots.txt` returns 404 (an S3-style
  "NoSuchBucket" XML), so no rules.
- **Updates and size:** yearly. The latest edition followed the CDL by
  about four weeks (Mar 27 against Feb 27), and the zip was re-issued
  May 15, so check Last-Modified before each pull. 3.76 GB national zip; a
  ring clip is probably 40–80k polygons and tens of MB in PostGIS
  (estimate, unverified).
- **Use cases:** clickable fields with crop history; per-field crop
  rotation; the unit of analysis for ET, NDVI and burn statistics; geometry
  for 3D "living fields"; fields lost to development (polygons that stop
  being cropped).
- **For:** farmers, history buffs, 3D and weather viewers, civic users and
  planners. **Needs:** the layer system, selection and picking, panels,
  PostGIS vector tiles through `/api/`.
- **Risks:** boundaries are modelled and generalized at 60 m, not legal
  fields, so label them "estimated field". IDs aren't stable across
  editions, so join editions spatially. Downloading the 3.76 GB national zip
  needs the owner's OK for that run; the Source Cooperative copy is no
  substitute for history.
- **Verification:** confirmed the zip size and date, the polygon count, the
  public-domain wording, the fields and every robots.txt result. Corrected:
  the minimum-polygon rule (the research said polygons were dropped unless
  they held at least two crop years). Refuted: that the Source Cooperative
  copy can stand in for the 8-year history. Added: the 60 m simplification,
  the 10 m resampling, and the ArcGIS Pro dependency of NASS's code.
- **Evidence:** [CSB page](https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/index.php),
  [CSB 2025 metadata](https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/metadata_Crop-Sequence-Boundaries-2025.htm),
  the national zip (HEAD only),
  [Source Cooperative dataset](https://source.coop/fiboa/us-usda-cropland),
  its [README](https://data.source.coop/fiboa/us-usda-cropland/README.md)
  and [LICENSE.txt](https://data.source.coop/fiboa/us-usda-cropland/LICENSE.txt),
  robots.txt for [source.coop](https://source.coop/robots.txt) and
  [data.source.coop](https://data.source.coop/robots.txt),
  [NASS's code](https://github.com/USDA-REE-NASS/crop-sequence-boundaries).

### USDA NASS Crop Progress Gridded Layers

Use (valley-wide timing only) · verified: corrected · confidence medium ·
effort S

- **Contents:** weekly gridded layers of crop progress (planting,
  emergence, harvest stages) and condition for corn, soybeans, cotton and
  winter wheat, 2015 to now. Fully synthetic representations of
  confidential county-level survey data. 9 km cells: 32-bit float GeoTIFF in
  CONUS Albers, snapped to NASA's SMAP grid (per the metadata). Weekly,
  April–November.
- **Access:** yearly zips at
  `www.nass.usda.gov/Research_and_Science/Crop_Progress_Gridded_Layers/datasets/cpc<year>.zip`
  (`cpc2026.zip`: 46,031,675 bytes, modified Oct 5, 2026), plus HTML
  metadata (`metadata_CropProgress.htm`, `metadata_CropCondition.htm`) and
  description PDFs.
- **Coverage:** the lower 48 states; Idaho is in the metadata's place
  keywords. Which of the four crops are covered in Idaho is unconfirmed: the
  national weekly report tracks winter wheat but probably not corn in Idaho
  ⚠️ (from memory). At 9 km the valley is only a few dozen cells.
- **License and terms:** stated in the metadata's use constraints:
  "considered public domain and free to redistribute".
- **robots.txt:** allowed (`www.nass.usda.gov` disallows only
  `/Quick_Stats/CDQT/`).
- **Updates and size:** weekly, April–November; about 46 MB per national
  year zip, and a ring clip is tiny.
- **Use cases:** a valley-wide planting and harvest timing curve for winter
  wheat (and corn, if covered); a harvest-season farm-traffic calendar.
- **For:** 3D and weather viewers, farmers, commuters. **Needs:** the time
  and replay clock.
- **Risks:** 9 km synthetic cells can't describe individual fields, so they
  must not drive per-field 3D state. Only four crops: the valley's staples
  (beets, onions, alfalfa, mint, hops) aren't covered, so per-field state
  needs Sentinel-2 NDVI.
- **Verification:** corrected: the license is stated (public domain, free
  to redistribute); the resolution is 9 km; Idaho is in the place keywords;
  the research's "3D per field" use is technically wrong, so it was
  downgraded to a regional timing curve.
- **Evidence:** [Crop Progress Gridded Layers page](https://www.nass.usda.gov/Research_and_Science/Crop_Progress_Gridded_Layers/index.php),
  [progress metadata](https://www.nass.usda.gov/Research_and_Science/Crop_Progress_Gridded_Layers/metadata/metadata_CropProgress.htm),
  `cpc2026.zip` (HEAD only).

### Sentinel-2 L2A cloud-optimized GeoTIFFs on AWS (Earth Search)

Use · verified: corrected · confidence medium · effort L

- **Contents:** 10–20 m multispectral surface reflectance every few days,
  with STAC metadata. Earth Search v1 includes `sentinel-2-c1-l2a`
  ("Sentinel-2 Collection 1 Level-2A", from 2015-06-27) as well as the older
  `sentinel-2-l2a`, which the registry page shows being succeeded by
  Collection 1. Per-field NDVI gives green-up, peak and harvest in season for
  every crop.
- **Access:** the STAC API at `earth-search.aws.element84.com/v1` (collection
  `sentinel-2-c1-l2a`), then COGs read by HTTP range from the
  `e84-earth-search-sentinel-data` bucket (Collection 1) or `sentinel-cogs`
  (older), both in us-west-2; the registry says no AWS account is required.
- **Coverage:** global, so the whole ring from mid-2015 (Collection 1).
- **License and terms:** Copernicus Sentinel data terms; the registry calls
  access "free, full and open". The STAC collection's license is listed as
  "proprietary", linking to the Sentinel Data Legal Notice. Credit: "Contains
  modified Copernicus Sentinel data [year]".
- **robots.txt:** `earth-search.aws.element84.com/robots.txt` returns 403
  (a JSON "Forbidden"), a 4xx, so no rules. The S3 buckets are anonymous
  object storage, where robots.txt doesn't apply.
- **Updates and size:** usually within hours of availability on
  Copernicus. Keeping only per-field NDVI statistics is a few MB a season.
- **Use cases:** growing-season curves per CSB field; crop height and colour
  for 3D; harvest and burn scars; fields going fallow before they're
  developed.
- **For:** 3D and weather viewers, farmers, history buffs. **Needs:** the
  time and replay clock, the 3D engine, and a processing job: outside the
  standard-library-only ingest rule, or numpy and rasterio as a new
  dependency.
- **Risks:** clouds and the processing load. Use Collection 1, since the
  older collection is superseded. From memory, not re-checked ⚠️:
  older-collection scenes processed with baseline 04.00 or later (from
  January 2022) carry a reflectance offset that biases NDVI unless removed.
  The ingest code is standard library only, so numpy or rasterio is an
  owner decision.
- **Verification:** confirmed no AWS account is needed, the "free, full and
  open" wording and the 403 robots.txt. Corrected: point at
  `sentinel-2-c1-l2a`, since the registry dataset the research cited is
  superseded; coverage starts in 2015, not 2017.
- **Evidence:** [registry page](https://registry.opendata.aws/sentinel-2-l2a-cogs/),
  [robots.txt](https://earth-search.aws.element84.com/robots.txt),
  [collections](https://earth-search.aws.element84.com/v1/collections),
  [`sentinel-2-c1-l2a`](https://earth-search.aws.element84.com/v1/collections/sentinel-2-c1-l2a).

### USDA FSA Common Land Units (avoid)

Avoid · verified: confirmed · confidence high

- **Contents:** the authoritative farm-field and tract boundaries, tied to
  USDA program participants.
- **Access:** not public; released only to cooperating agencies, or with
  the producer's consent. `www.fsa.usda.gov` was unreachable from the
  research sandbox (robots.txt fetch failed with curl error 92, an HTTP/2
  stream error), on Oct 7 as before.
- **License and terms:** restricted by
  [7 U.S.C. 8791(b)](https://www.law.cornell.edu/uscode/text/7/8791): the
  Secretary "shall not disclose" geospatial information about agricultural
  land or operations. Exceptions: aggregate or statistical form without
  naming any owner, operator or producer; cooperating agencies; producer
  consent.
- **robots.txt:** unreadable (network error), so treat it as disallowed for
  now; moot anyway.
- **Coverage:** national.
- **Use cases:** none. CSB is NASS's non-confidential substitute.
- **Risks:** a legal restriction. Old leaked or third-party copies
  circulate; don't use them. IDWR's irrigated-lands polygons cite 2014 CLU
  lineage; using IDWR's published derivative is fine.
- **Verification:** the statute's wording and exceptions are confirmed, and
  FSA was unreachable again on Oct 7.
- **Evidence:** [7 U.S.C. 8791](https://www.law.cornell.edu/uscode/text/7/8791),
  `www.fsa.usda.gov/robots.txt` (unreachable).

## Farm statistics

### USDA NASS Quick Stats bulk files and the 2022 Census of Agriculture

Use · verified: confirmed · confidence high · effort S

- **Contents:** the full Quick Stats database as gzipped text. Files dated
  Oct 6, 2026: `qs.crops` 1.05 GB, `qs.animals_products` 442.4 MB,
  `qs.economics` 557.33 MB, `qs.demographics` 444.94 MB,
  `qs.environmental` 71.77 MB. Census files `qs.census2002`, `2007`, `2012`,
  `2017` and `2022` (2022: 294.87 MB), plus ZIP-code census files for 2007
  and 2017.
- **County profiles, 2022** (re-read Oct 7):

  | | Canyon | Ada |
  |---|---|---|
  | Farms | 2,311 (+1% since 2017) | 1,142 (−12%) |
  | Land in farms | 277,388 ac (+1%) | 112,556 ac (0%) |
  | Irrigated | 207,577 ac (75% of land in farms) | 35,479 ac (32%) |
  | Sales | $829.4 M (+44%) | $191.3 M (+45%) |
  | Crops / livestock share of sales | 55% / 45% | 21% / 79% |
  | Cropland | 228,177 ac | 42,862 ac (plus 63,578 ac pastureland) |

- **Access:** static HTTPS under `www.nass.usda.gov/datasets/`, and the
  profiles at
  `/Publications/AgCensus/2022/Online_Resources/County_Profiles/Idaho/cp16001.pdf`
  (Ada) and `cp16027.pdf` (Canyon). Download, then filter to Idaho, Oregon
  and the ring counties.
- **Coverage:** national, with county detail for Ada, Canyon, Payette, Gem,
  Owyhee, Elmore, Boise, Washington and Malheur (Oregon). Census 2002–2022
  in the files; survey series go back further (not re-checked).
- **License and terms:** federal statistics, public domain ⚠️ (no license
  text on the datasets page). The API's attribution line applies only to the
  API.
- **robots.txt:** allowed (`www.nass.usda.gov` disallows only
  `/Quick_Stats/CDQT/`, so `/datasets/` and `/Publications/` are open).
- **Updates and size:** the bulk files are regenerated daily (dates are in
  the file names); county estimates yearly; a census every five years (the
  2027 census's results arrive around 2029 ⚠️). Up to 1.05 GB per file
  compressed; an Idaho and Oregon county extract is a few MB.
- **Use cases:** farms and farmland acres by county over time; milk-cow and
  cattle inventories in aggregate, instead of point data on dairies; Idaho's
  weekly crop progress for the harvest calendar; headline numbers for the
  farmland-loss story.
- **For:** farmers, civic users and planners, history buffs. **Needs:** the
  readings contract (time-series card), areas (counties).
- **Risks:** the files are large, so pull them once or twice a year, by
  hand, with the owner's OK (whole-file downloads). County data has (D)
  suppressions to avoid disclosing individual operations.
- **Verification:** every file size and date and every county-profile
  number re-checked Oct 7; they match. The land-use split and the sales
  changes were added.
- **Evidence:** [datasets page](https://www.nass.usda.gov/datasets/),
  [Canyon profile](https://www.nass.usda.gov/Publications/AgCensus/2022/Online_Resources/County_Profiles/Idaho/cp16027.pdf),
  [Ada profile](https://www.nass.usda.gov/Publications/AgCensus/2022/Online_Resources/County_Profiles/Idaho/cp16001.pdf),
  [robots.txt](https://www.nass.usda.gov/robots.txt).

### USDA NASS Quick Stats API (avoid)

Avoid · verified: confirmed · confidence high

- **Contents:** every NASS survey and census statistic by state, county and
  agricultural statistics district: acreage, yield and production by crop,
  livestock inventories (milk cows), weekly crop progress and condition, and
  the Census of Agriculture.
- **Access:** REST at `quickstats.nass.usda.gov/api/`: `api_GET`,
  `get_param_values` and `get_counts`; JSON, CSV or XML; at most 50,000
  records a request. A free key from an email form.
- **License and terms:** public data under the API terms. Required line:
  "This product uses the NASS API but is not endorsed or certified by
  NASS." The terms forbid modifying content while still presenting NASS as
  the source; they don't forbid modifying it outright. NASS may block users
  who try to exceed the limits.
- **robots.txt:** `quickstats.nass.usda.gov/robots.txt` is
  `User-agent: *` / `Disallow: /` (re-checked Oct 7), so no automated access
  to this host.
- **Coverage:** national, with county detail for Ada, Canyon and the ring
  counties. Continuous updates (weekly progress, yearly estimates, a census
  every five years).
- **Use cases:** county crop and livestock statistics and crop progress, all
  of which the bulk files above give without a key. One-off lookups by the
  owner by hand are fine.
- **For:** farmers, civic users and planners.
- **Verification:** confirmed the key requirement (email form), the
  attribution line, the 50,000-record cap, the three endpoints and the
  disallow-all robots.txt. Corrected (minor): the modification term only
  forbids modifying content while still citing NASS as the source.
- **Evidence:** [API page](https://quickstats.nass.usda.gov/api),
  [robots.txt](https://quickstats.nass.usda.gov/robots.txt).

## Irrigation, canals and water rights

### IDWR irrigation organizations (today, and circa 1941)

Use · verified: confirmed · confidence high · effort S

- **Contents:** polygons of each irrigation organization's service area
  (fields `NAME`, `Owner`, `PlaceOfUse`, `LPOU`, `PROCESS`, `PERIMETER`,
  `ACRES`). A count query on Oct 7 returned 59 organizations intersecting
  the valley box. The research's per-organization acreages (the Boise
  Project Board of Control at 243,432 ac, and others) were not re-run.
  Historical: IDWR's catalog lists "Irrigation Organizations: Boise Valley
  1941 - 1998", irrigation districts in Ada and Canyon counties circa 1941
  with corrections from individual districts.
- **Access:** FeatureServer queries (`maxRecordCount` 2000; Query and
  Extract). The 1941 layer is a zip:
  `research.idwr.idaho.gov/gis/Spatial/Irrigation/IrrigationCompanies/irgdist41.zip`
  (929,306 bytes, Last-Modified May 27, 2026).
- **Coverage:** statewide, so all of Ada, Canyon and the Idaho part of the
  ring.
- **License and terms:** disclaimer only: IDWR makes its data available as
  a public service under the Idaho Public Records Act, without warranty.
  Credit IDWR.
- **robots.txt:** `gis.idwr.idaho.gov/robots.txt` redirects (302) to an
  HTML error page on `error.idaho.gov` that returns 200, which the lenient
  parse reads as no rules. `research.idwr.idaho.gov` allows `/gis/Spatial/`.
- **Updates and size:** irregular. The layer's editing info shows no last
  edit date, so the research's "May 2026" edit date is unverified; the 1941
  zip was re-uploaded May 27, 2026. About 60 polygons in the box, under
  10 MB.
- **Use cases:** "which irrigation district am I in" for the owner's own
  place; canal water dates attached to the right district; who runs each
  canal crossing; urban irrigation inside city limits.
- **For:** gardeners, homeowners, farmers, civic users and planners.
  **Needs:** the shared ArcGIS reader, places and search, areas.
- **Risks:** these are service areas, not irrigated acres. The `Owner`
  field names organizations, not people.
- **Verification:** confirmed the 59-organization count, the fields and the
  zip size. Unverified: the May 2026 edit date and the per-organization
  acres.
- **Evidence:** [Irrigation folder](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation?f=json),
  [layer 0](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/0?f=json),
  one count query on the valley box, `irgdist41.zip` (HEAD),
  [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json).

### IDWR season of use, headgate requirement and consumptive use

Use · verified: confirmed · confidence high · effort S

- **Contents:** IDWR's standard irrigation-season zones, based on the 45 °F
  mean-daily-temperature threshold. Fields `SPRING`, `FALL`, `STARTMONTH`,
  `STARTDAY`, `ENDMONTH`, `ENDDAY`, `SEASON`. The valley box has four zones
  (re-queried Oct 7): Mar 1–Nov 15, Mar 15–Oct 31, Mar 15–Nov 15 and
  Apr 1–Oct 31. Companion services: `Irrigation/HeadgateRequirement` and
  `Irrigation/ConsumptiveUse` (both Feature and MapServer).
- **Access:** FeatureServer queries (Query and Extract; `maxRecordCount`
  2000). Hub CSV and shapefile downloads also exist, under the hub's 60 s
  Crawl-delay.
- **Coverage:** statewide.
- **License and terms:** disclaimer only (the hub's text: made available as
  a public service). Credit IDWR.
- **robots.txt:** `gis.idwr.idaho.gov`: no rules.
- **Updates and size:** rare (regulatory); under 5 MB.
- **Use cases:** the legal irrigation window around the owner's yard or a
  field; context for canal turn-on and shut-off dates; a frost-season proxy
  for gardeners.
- **For:** gardeners, farmers, homeowners. **Needs:** the shared ArcGIS
  reader, lifecycles (season windows).
- **Risks:** this is the legal allowable season, not actual delivery
  dates; label it that way.
- **Verification:** the four zones, the fields and the companion services
  all match.
- **Evidence:** [layer 0](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/SeasonOfUse/FeatureServer/0?f=json),
  one attributes-only query on the valley box,
  [Irrigation folder](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation?f=json),
  [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json).

### Irrigation district season announcements

Use, by hand · verified: confirmed · confidence medium · effort S

- **Contents:** start-up and shut-off notices from each district (Nampa &
  Meridian Irrigation District, the Boise Project Board of Control and
  others). NMID's page at the `/2025-season-start-up/` slug now carries its
  2026 start-up text: Ridenbaugh Canal flows could start as early as April 1
  and no later than April 8, and about two weeks to fill means delivery to
  patrons in mid-to-late April. The slug is reused across years. A news
  report says the Boise Project started its canal on Apr 6, 2026 ⚠️
  (secondary, not re-checked).
- **Access:** read district websites by hand twice a year (March and
  October) and enter the dates as a manual lifecycle source. `nmid.org` has
  no RSS feed (`/feed/` returns 404).
- **Coverage:** the districts serving Ada and Canyon.
- **License and terms:** facts (dates); no data license. Cite each
  district.
- **robots.txt:** `nmid.org` disallows only `/wp-admin/` (allowing
  `admin-ajax.php`). Other districts' sites weren't checked.
- **Updates and size:** twice a year; a few rows a year.
- **Use cases:** canal water on and off as lifecycles per district in the
  Valley Feed; a gardener's reminder; canal-safety season (swift water).
- **For:** gardeners, farmers, homeowners, parents (safety). **Needs:**
  lifecycles (`evt`) and the Valley Feed, the manual source kind, areas
  (district polygons from IDWR).
- **Risks:** no machine feed, so it's manual. The URL slug doesn't match
  the year. Dates are announcements; the WD 63 diversion records would
  confirm them.
- **Verification:** confirmed the NMID text and dates, robots.txt and the
  feed's 404. Added: the slug and year mismatch. Not re-checked: the Boise
  Project date.
- **Evidence:** [NMID start-up page](https://nmid.org/2025-season-start-up/),
  [robots.txt](https://nmid.org/robots.txt), `nmid.org/feed/` (404),
  [KIVI news report](https://www.kivitv.com/news/local-news/in-your-neighborhood/ada-county/irrigation-releases-for-treasure-valley-farmers-and-homeowners-begin-on-april-6)
  ⚠️ (secondary, not re-checked).

### Treasure Valley Irrigation System (HydroShare canal network)

Needs owner action · verified: confirmed · confidence high · effort S

- **Contents:** Treasure Valley irrigation canals with names, diversion
  links and feature classes. Built from an initial canal coverage, aerial
  imagery, discussions with the irrigation entities and field checks; named
  features were updated from diversion data, and more were added by remote
  sensing. The network was built by Hawk Stone (Idaho DEQ) and updated by
  Taylor Tatum and Bridget Bittmann (the page doesn't show their affiliation;
  the research's "University of Idaho" is ⚠️). 1.3 MB. Created Sep 21, 2022;
  published Oct 18, 2022. Bounds 43.3066–43.8359 N, 115.7828–116.9912 W.
  DOI [10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f](https://doi.org/10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f).
- **Access:** one small download from the resource page. The page asks the
  user to accept the license before downloading, and robots.txt disallows
  the file path `/django_irods/download/`, so the owner downloads it by hand
  once.
- **Coverage:** the irrigated Treasure Valley in Ada and Canyon.
- **License and terms:** CC BY 4.0, per the resource page. Cite the
  HydroShare resource and its DOI; republishable with credit.
- **robots.txt:** `www.hydroshare.org`: Crawl-delay 5; allows `/search/`;
  disallows `/hsapi`, `/o/`, `/accounts/login/`, `/django_irods/download/`,
  `/sign-up/` and `/tracking/applaunch/`. `hydroshare.org/robots.txt`
  returns 200.
- **Updates and size:** static (2022); 1.3 MB.
- **Use cases:** a named canal network on the map; canal and road crossings
  (the bridges and culverts that limit widening); which canal serves which
  district; a canal water-on animation in season.
- **For:** farmers, gardeners, commuters, cyclists and hikers, civic users
  and planners. **Needs:** the layer system, places and search (canal
  names), the manual source kind.
- **Risks:** it's a 2022 snapshot. Reconcile it with OpenStreetMap's
  `waterway=canal` and `ditch` (ODbL) and NHD (public domain), keeping each
  in its own table. Accepting the license click-through is the owner's
  action.
- **Verification:** confirmed the license, size, dates, bounds, DOI and
  robots.txt. Corrected: the publisher attribution (DEQ's Hawk Stone built
  the network; the University of Idaho affiliation isn't shown). Added: the
  license click-through.
- **Evidence:** [resource page](https://www.hydroshare.org/resource/24a5f761bf4f41fb9b872b130d9d1a3f/),
  robots.txt for [www.hydroshare.org](https://www.hydroshare.org/robots.txt)
  and [hydroshare.org](https://hydroshare.org/robots.txt).

### IDWR water district diversions (WD 63 and WD 65), diversion data and Aqua Info

Needs owner action · verified: corrected · confidence medium · effort M

- **Contents:** locations of the measurement points used in IDWR's Water
  District Diversion Database. Fields `ID`, `HydrologyID`,
  `WaterDistrictNumber`, `DiversionTypeDescription`, `DiversionName`,
  `ReachDescription`, `Inactive`, `PodSpatialDataID`. WD 63 (Boise River),
  re-queried Oct 7: 78 active diversions, 6 flow or gage stations, 4 drains,
  4 combined-use, 2 non-consumptive and 3 inactive diversions. The
  research's count of 109 for WD 65 (Payette) wasn't re-checked. Daily
  diversion records are in the Diversion Data application. Aqua Info warns
  that not all data is public and all of it is provisional; it offers a
  chart and CSV export per measurement site. Yearly Boise River water-rights
  accounting reports are PDFs.
- **Access:**
  - Site locations: the FeatureServer.
  - Daily data: `research.idwr.idaho.gov/apps/watermanagement/diversiondataapplication/`,
    an ASP.NET login form with a "guest (read only access)" checkbox that
    needs no user name or password.
  - Aqua Info: `research.idwr.idaho.gov/apps/hydrologic/aquainfo`. CSV
    export is confirmed; a JSON export and 15-minute data weren't seen, and
    the endpoints weren't inspected.
  - Accounting PDFs:
    `idwr.idaho.gov/wp-content/uploads/sites/2/water-rights-accounting/boiwra/<year>-boise-wr-accounting-report.pdf`
    (2024: 3.59 MB; 2025: 3.73 MB, modified Dec 31, 2025).
- **Coverage:** WD 63 (Boise River, Ada and Canyon) and WD 65 (Payette, in
  the ring).
- **License and terms:** disclaimer only; Aqua Info's data is provisional
  and subject to change. Credit IDWR and the watermasters.
- **robots.txt:** `research.idwr.idaho.gov` allows `/apps/`;
  `idwr.idaho.gov` has an empty Disallow (all allowed); `gis.idwr.idaho.gov`
  has no rules.
- **Updates and size:** daily in season (telemetry frequency unconfirmed).
- **Use cases:** when each canal actually starts and stops diverting each
  year (the true "canal water on and off"); seasonal diversion curves per
  canal; a canal-water lifecycle in the Valley Feed.
- **For:** gardeners, farmers, civic users and planners, 3D and weather
  viewers. **Needs:** the readings contract, lifecycles, the shared ArcGIS
  reader.
- **Risks:** no credentials are needed, but the daily database sits behind
  a session login form, and scripting a login form isn't appropriate without
  IDWR's OK. Aqua Info's endpoints need inspecting, and IDWR's OK, before any
  automation. The accounting PDFs need extracting.
- **Verification:** confirmed the WD 63 counts (adding the 2
  non-consumptive and 3 inactive diversions), the guest login, the PDF URL
  pattern and robots.txt. Corrected: access from "account" to "none", since
  the guest login needs no credentials; the verdict stays "needs owner
  action" because it's still a session form. Not confirmed: Aqua Info's JSON
  export and 15-minute data, and the WD 65 count.
- **Evidence:** [diversion sites layer](https://gis.idwr.idaho.gov/hosting/rest/services/Compliance/DiversionDataSites/FeatureServer/0?f=json),
  one grouped count query for WD 63,
  [Diversion Data application](https://research.idwr.idaho.gov/apps/watermanagement/diversiondataapplication/),
  [Aqua Info](https://research.idwr.idaho.gov/apps/hydrologic/aquainfo),
  the 2024 and 2025 accounting PDFs (HEAD only), robots.txt for
  [idwr.idaho.gov](https://idwr.idaho.gov/robots.txt) and
  [research.idwr.idaho.gov](https://research.idwr.idaho.gov/robots.txt).

### IDWR water rights: points of diversion and places of use

Use (no owner names) · verified: confirmed · confidence high · effort M

- **Contents:** points of diversion (PODs) for active licensed or decreed
  rights: `WaterRightNumber`, `Status`, `Basis`, `PriorityDate`, `Owner`,
  `OverallMaxDiversionRate` and `Volume`, `Source`, `TributaryOf`,
  `WaterDistrictNumber`, `DiversionName`, `DiversionType`, `Uses`,
  `MetalTagNumber`, `WRReport`, `WRDocs`, `WRMap`. IDWR says POD points were
  first placed at the centroid of the legal (PLSS) description and are
  refined over time, so many are approximate. Places of use (POUs) are
  polygons with `WaterUse`, `WaterUseCode`, `TotalAcres`, `AcreLimit`,
  `PriorityDate`, `DecreedDate`, `Owner`, `LargePOU`. The `Allocation`
  folder also holds adjudication claims and recommendations, applications
  and permits, and Water Supply Bank lease and rental layers.
- **Access:** FeatureServer queries under `Allocation/`
  (`WaterRightPods`, `WaterRightPous`). Hub CSV and shapefile downloads
  exist (item `f0b37d653f8249a4945d61bdb98dc4a7` for PODs).
- **Coverage:** statewide.
- **License and terms:** disclaimer only (public records). Credit IDWR.
- **robots.txt:** `gis.idwr.idaho.gov`: no rules.
- **Updates and size:** continuous (the hub item was modified June 17,
  2026). Tens of thousands of points and polygons in the box (not counted).
- **Use cases:** a priority-date map (who gets cut first in a dry year);
  the Boise River's diversions and their uses; how irrigation rights convert
  to municipal use as farms urbanize (aggregates).
- **For:** farmers, civic users and planners, history buffs. **Needs:** the
  shared ArcGIS reader, the `restricted` schema for personal fields.
- **Risks:** owner names on PODs and POUs include private individuals:
  drop the `Owner` field, or keep it only in `restricted`, and publish only
  uses, priority dates and aggregates. No index searchable by owner. Many POD
  locations are PLSS centroids, so don't show them as exact diversion
  points.
- **Verification:** the fields and service list match. Added: POD
  locations derive from PLSS centroids.
- **Evidence:** [Allocation folder](https://gis.idwr.idaho.gov/hosting/rest/services/Allocation?f=json),
  [PODs](https://gis.idwr.idaho.gov/hosting/rest/services/Allocation/WaterRightPods/FeatureServer/0?f=json),
  [POUs](https://gis.idwr.idaho.gov/hosting/rest/services/Allocation/WaterRightPous/FeatureServer/0?f=json),
  [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json).

### IDWR wells (well-log database)

Internal only · verified: confirmed · confidence high · effort S

- **Contents:** permitted wells: `WellID`, `PermitID`, `ConstructionDate`,
  `WellUse`, `ProductionRate`, `StaticWaterLevel`, `Casing`, `TotalDepth`,
  `PLSS`, latitude and longitude, `WellDocs`, and also `Owner`,
  `WellAddress`, `Lot`, `Block` and subdivision. The hub says the database
  holds most well reports back to July 1987.
- **Access:** FeatureServer queries; hub CSV and shapefile downloads (item
  `9167ab2d41334b1d8d437e126fc10c1f`).
- **Coverage:** statewide.
- **License and terms:** disclaimer only. Credit IDWR.
- **robots.txt:** `gis.idwr.idaho.gov`: no rules.
- **Updates:** continuous (the hub item was modified Mar 3, 2026).
- **Use cases:** depth to water and new-well density aggregated by section
  (domestic wells follow rural subdivisions); a groundwater story beside the
  surface canals.
- **For:** homeowners, farmers, civic users and planners. **Needs:** the
  shared ArcGIS reader, the `restricted` schema.
- **Risks:** personal data: owner names and well addresses at homes.
  Aggregate to section or hex only, never show wells house by house, and
  don't store the personal fields (or keep them in `restricted`).
- **Verification:** the fields, including the personal ones, and the July
  1987 note match.
- **Evidence:** [wells layer](https://gis.idwr.idaho.gov/hosting/rest/services/Groundwater/Wells/FeatureServer/0?f=json),
  [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json).

## Crop water use, weather and drought

### USBR AgriMet crop water-use charts (static files)

Use · verified: corrected · confidence high · effort S

- **Contents:** daily ET (inches a day) for the current year by station.
  Columns differ by station, and repeated names are separate crop calendars,
  so decode them by position against the station's `<station>ch.txt`. That
  file is a 5-day CSV, "Estimated Crop Water Use", giving each column's
  start, full-cover and terminate dates, the last four days, a daily
  forecast, the season's total ET and 7- and 14-day use. On Oct 7 the ET
  files ended at 10/04 and `pmaich.txt` was dated Oct 5: a lag of 2–3 days.

  | Station | Code | Since | Columns |
  |---|---|---|---|
  | Parma | `pmai` | Mar 1, 1986 | ETr, ALFP, ALFM, PAST, LAWN, WGRN, SGRN, BEET ×2, ONYN ×2, POTS, POTA ×2, BEAN, FCRN ×3, SCRN ×2, PEAS, PPMT, WGRP, APPL |
  | Boise | `boii` | Jul 26, 1995 | ETr and LAWN only |
  | Nampa | `nmpi` | Mar 11, 1996 | Crops; adds ALFN, ASPA and NMNT |
  | Boise Fairgrounds | `bfgi` | Aug 15, 2013 | ETr and LAWN only |
  | Ontario, Oregon | `onto` | Apr 30, 1992 | Crops; adds POP1–3 and more onion and potato variants |
  | Grand View | `gdvi` | Oct 1, 1992 | Crops; no onions |

- **Access:** static text at
  `www.usbr.gov/pn/agrimet/chart/<station><yy>et.txt` and
  `chart/<station>ch.txt` (patterns confirmed in `CropCharts.html`'s
  script). Station list: `/pn/agrimet/location.csv` (its first line is a
  stray `Content-disposition` header; skip it) and
  `/pn/agrimet/agrimetmap/usbr_map.json`. `www.usbr.gov` reset HEAD requests
  (curl error 56), so use GET.
- **Coverage:** six point stations in or near the ring. Crop ET only at
  Parma, Nampa, Ontario and Grand View; the Boise stations are lawn only.
- **License and terms:** a federal work (public domain ⚠️, inferred).
  Reclamation's disclaimer says the site's information is provided as a
  courtesy and near-real-time data are provisional. Credit Reclamation
  AgriMet.
- **robots.txt:** `www.usbr.gov` disallows only `/pn-bin` and `/gp-bin`,
  so `/pn/agrimet/chart/` is allowed.
- **Updates and size:** daily, 1–3 days behind; 5–41 KB per station a year.
- **Use cases:** "crop water use today" per crop (four stations); lawn
  water use for gardeners (the LAWN column: ET only, not irrigation need);
  colouring fields by ET (CDL crop × the nearest station that has that
  crop); Reclamation's assumed crop calendars (start, full cover, terminate).
- **For:** farmers, gardeners, 3D and weather viewers. **Needs:** the
  readings contract (time-series card), places (stations).
- **Risks:** only ET is in the static files: no precipitation,
  temperature, wind, solar or humidity (those are behind the disallowed
  `/pn-bin`). So "lawn needs X inches" can't subtract rain, and degree-days
  can't be computed. Column sets differ by station and repeat names; parse
  by position using `ch.txt`. The calendar dates are assumptions, not
  observed planting. Poll once a day, gently.
- **Verification:** confirmed the six stations and their install dates,
  the URL patterns, the disclaimer and robots.txt. Corrected: the Boise
  stations are lawn only; column sets differ by station; `ch.txt` is a 5-day
  CSV of crop calendars and recent ET, not just a crop chart; the files lag
  2–3 days; HEAD fails on this host.
- **Evidence:** [crop water use page](https://www.usbr.gov/pn/agrimet/h2ouse.html),
  [CropCharts.html](https://www.usbr.gov/pn/agrimet/CropCharts.html),
  2026 ET files for [Parma](https://www.usbr.gov/pn/agrimet/chart/pmai26et.txt),
  [Boise](https://www.usbr.gov/pn/agrimet/chart/boii26et.txt),
  [Boise Fairgrounds](https://www.usbr.gov/pn/agrimet/chart/bfgi26et.txt),
  [Nampa](https://www.usbr.gov/pn/agrimet/chart/nmpi26et.txt),
  [Ontario](https://www.usbr.gov/pn/agrimet/chart/onto26et.txt) and
  [Grand View](https://www.usbr.gov/pn/agrimet/chart/gdvi26et.txt),
  [`pmaich.txt`](https://www.usbr.gov/pn/agrimet/chart/pmaich.txt),
  [location.csv](https://www.usbr.gov/pn/agrimet/location.csv),
  [disclaimer](https://www.usbr.gov/pn/agrimet/disclaimer.html),
  [robots.txt](https://www.usbr.gov/robots.txt).

### USBR AgriMet and Hydromet data services, and Reclamation's RISE API

Needs owner action · verified: confirmed · confidence high · effort S

- **Contents:** AgriMet's full weather archives (15-minute or hourly, and
  daily: air temperature, humidity, wind, solar radiation, precipitation,
  soil temperature, ET) for the six stations. Hydromet: Boise and Payette
  reservoir and river data, and some canal diversions (for example the New
  York Canal ⚠️, secondary). RISE: Reclamation-wide time series.
- **Access:** form posts to `www.usbr.gov/pn-bin/daily.pl` and
  `/pn-bin/instant.pl`; RISE at `data.usbr.gov/rise/api/…`.
- **Coverage:** the Pacific Northwest, including every ring station.
- **License and terms:** a federal work; the provisional-data disclaimer
  applies.
- **robots.txt:** `www.usbr.gov` disallows `/pn-bin` (and `/gp-bin`).
  `data.usbr.gov` disallows `/rise/api`, `/time-series?` and its selection,
  output and search paths, `/catalog?` and the RISE map query paths. Both
  rule out automated collection (re-checked Oct 7).
- **Updates:** 15-minute to daily.
- **Use cases:** AgriMet weather as extra ground truth for the 3D weather
  work (humidity, fog, radiation); canal and reservoir flows; frost dates;
  precipitation to turn lawn ET into irrigation need (if permitted).
- **For:** 3D and weather viewers, farmers, gardeners. **Needs:** the
  readings contract.
- **Risks:** robots-disallowed, so only one-off lookups by hand at the
  owner's request. Ask Reclamation (agrimet@usbr.gov) for permission to
  script a few gentle calls a day. Don't use third-party mirrors of RISE to
  get around it.
- **Verification:** the robots.txt rules match on both hosts;
  `data.usbr.gov`'s disallow list is fuller than the research reported. The
  archives' contents weren't re-checked.
- **Evidence:** [AgriMet archive page](https://www.usbr.gov/pn/agrimet/webarcread.html),
  robots.txt for [www.usbr.gov](https://www.usbr.gov/robots.txt) and
  [data.usbr.gov](https://data.usbr.gov/robots.txt).

### IDWR METRIC evapotranspiration rasters

Use · verified: corrected · confidence high · effort M

- **Contents:** Landsat-based METRIC ET, monthly and seasonal, as ERDAS
  `.img` files; METRIC uses AgriMet weather as input. In the MapServer, the
  Treasure Valley (Landsat path 42) has groups for 1987, 1994, 2000, 2004,
  2007, 2010 and 2015 only: monthly grids for March–October plus a seasonal
  Mar 1–Oct 31 grid. Every later group (2016–2023) is for the Eastern Snake
  Plain (ESPA, paths 39 and 40, Apr 1–Oct 31). There is also a "2000 Western
  Snake Plain" group (p41r30) in the ring. Hub items run from 1985 to 2024;
  the 2024 item's file-name example is `p3940` (ESPA), and its keywords are
  ESPA and Snake Plain.
- **Access:** the MapServer (Query, Map, Data) for viewing and identify;
  zips at `research.idwr.idaho.gov/GIS/Spatial/METRIC/<year>.zip`
  (`2024.zip`: 1,603,537,619 bytes, modified Sep 15, 2026).
- **Coverage:** the Treasure Valley for seven years, 1987–2015 only. The
  MapServer groups and the 2024 item's naming show no Treasure Valley ET
  after 2015.
- **License and terms:** disclaimer only. Credit IDWR and the University
  of Idaho.
- **robots.txt:** `gis.idwr.idaho.gov`: no rules.
  `research.idwr.idaho.gov` allows `/GIS/Spatial/METRIC/`.
- **Updates and size:** irregular for the Treasure Valley (none since
  2015); yearly for ESPA. ESPA zips run up to 1.6 GB and aren't needed; the
  Treasure Valley seasonal grids are much smaller (not measured).
- **Use cases:** "the valley breathing": water use by field, irrigated
  against desert (1987–2015); the drop in ET where farms became subdivisions
  (up to 2015); humidity and cooling context for the 3D weather work.
- **For:** 3D and weather viewers, farmers, civic users and planners,
  history buffs. **Needs:** the raster tile pipeline, the year slider.
- **Risks:** no current-year Treasure Valley ET. Different seasonal windows
  (Treasure Valley March–October against ESPA April–October). Fetch only the
  Treasure Valley grids (by MapServer identify, or a hand download with the
  owner's OK); skip the ESPA zips.
- **Verification:** confirmed the seven Treasure Valley years and the 2024
  zip size. Corrected: Treasure Valley coverage after 2015, which the
  research left unconfirmed, now looks absent, since all later groups are
  ESPA; added the 2000 Western Snake Plain group and the window difference.
- **Evidence:** [ETData MapServer](https://gis.idwr.idaho.gov/hosting/rest/services/ScientificRasters/ETData/MapServer?f=json),
  [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json),
  `2024.zip` (HEAD only).

### OpenET (field-scale satellite ET)

Needs owner action · verified: confirmed · confidence medium

- **Contents:** a 30 m ET ensemble: monthly from 2000 and daily from 2016
  in the API, with per-field summaries. That its field boundaries include
  2008 CLU wasn't re-checked ⚠️. IDWR used OpenET's eeMETRIC as an input to
  its 2023 Treasure Valley irrigated-lands raster.
- **Access:** the Data Explorer (free to view, limited downloads) and an
  API. The terms don't say whether the API needs an account or key; that
  comes from the research's reading of the API docs ⚠️.
- **Coverage:** the western US, including Idaho. Monthly to daily.
- **License and terms** ([terms of service](https://etdata.org/terms-of-service/)):
  a limited, revocable, non-transferable license for personal,
  noncommercial use; no apps that interact with the services without
  OpenET's prior written consent; no data mining, robots or similar data
  gathering; no commercial use; visible attribution required.
- **robots.txt:** `etdata.org` disallows only `/wp-admin/`, but the terms
  forbid automated extraction without written consent whatever robots.txt
  says.
- **Use cases:** current-year ET per field (IDWR's METRIC has no Treasure
  Valley year after 2015).
- **For:** farmers, 3D and weather viewers.
- **Risks:** restrictive terms and an account. Only with OpenET's written
  OK; otherwise use IDWR METRIC (1987–2015) and AgriMet's static ET.
- **Verification:** every quoted term is confirmed; the grant is limited to
  personal, noncommercial use. The key requirement isn't in the terms (the
  API docs weren't re-checked).
- **Evidence:** [terms of service](https://etdata.org/terms-of-service/),
  [robots.txt](https://etdata.org/robots.txt).

### U.S. Drought Monitor (USDM)

Use (county statistics) · verified: corrected · confidence high · effort S

- **Contents:** weekly drought categories D0–D4. The data services API
  gives percent area or population by county, state, HUC and more, plus the
  DSCI index. `statisticsType=1` is "traditional", which is cumulative (D0
  means D0–D4, D1 means D1–D4); `statisticsType=2` is categorical (one
  category at a time). Columns: `MapDate`, `FIPS`, `County`, `State`,
  `None`, `D0`–`D4`, `ValidStart`, `ValidEnd`, `StatisticFormatID`. Weekly
  polygons come as shapefile, GeoJSON, KMZ, GML and WMS.
- **Sample, re-run Oct 7:** Canyon County (16027), maps from Jul 28 to
  Sep 29, 2026: every week read None 0.00, D0 100.00, D1 11.28, D2–D4 0
  (cumulative), so all of the county was in D0 or worse and 11.28% in D1 or
  worse.
- **Access:** statistics at
  `usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent?aoi=16001,16027&startdate=M/D/YYYY&enddate=M/D/YYYY&statisticsType=2`;
  CSV by default, JSON or XML through the Accept header. Polygons are under
  `droughtmonitor.unl.edu/data/…` (robots-disallowed) and on a WMS at
  `ndmcgeodata.unl.edu` (TLS error).
- **Coverage:** national, so every ring county (Ada 16001, Canyon 16027,
  Payette, Gem, Owyhee, Elmore, Boise, Washington, Malheur in Oregon).
  Weekly since 2000.
- **License and terms:** the
  [Permission page](https://droughtmonitor.unl.edu/About/Permission.aspx)
  requires a credit line naming the joint producers (the National Drought
  Mitigation Center at the University of Nebraska-Lincoln, USDA, NOAA and
  NASA) and "Map courtesy of NDMC". No other restrictions are stated.
- **robots.txt:** `usdmdataservices.unl.edu` 404, no rules (allowed).
  `droughtmonitor.unl.edu` (a file with a byte-order mark) disallows
  `/data/`, `/nadmdata/`, `/webfiles/` and `/DmData/DataArchive.aspx`, which
  covers all the polygon files. `ndmcgeodata.unl.edu/robots.txt` failed with
  a TLS certificate error (curl 60), so treat it as disallowed for now.
- **Updates and size:** weekly (maps valid Tuesday, released Thursday);
  tiny (rows per county per week).
- **Use cases:** a drought strip and time-series card per county
  (categorical statistics); dry-year context for canal shut-offs and fire.
- **For:** farmers, gardeners, fire and hazards watchers, civic users and
  planners. **Needs:** the readings contract, areas (counties).
- **Risks:** don't stack the cumulative values (type 1), which
  double-counts; use type 2. Polygons can't be collected automatically: ask
  NDMC (DroughtMonitor@unl.edu), or show county statistics only.
- **Verification:** confirmed the sample values and robots.txt. Corrected:
  the license now carries the required credit line; type 1 statistics are
  cumulative; the `ndmcgeodata` failure is a TLS error.
- **Evidence:** [web service info](https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx),
  [Permission page](https://droughtmonitor.unl.edu/About/Permission.aspx),
  [statistics explanation](https://droughtmonitor.unl.edu/About/AbouttheData/StatisticsExplanation.aspx),
  [Canyon sample query](https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent?aoi=16027&startdate=8/1/2026&enddate=10/6/2026&statisticsType=1),
  robots.txt for [droughtmonitor](https://droughtmonitor.unl.edu/robots.txt)
  and [usdmdataservices](https://usdmdataservices.unl.edu/robots.txt);
  `ndmcgeodata.unl.edu/robots.txt` (TLS error).

### Oregon State IPPC degree-day and pest models (avoid)

Avoid · verified: confirmed · confidence high

- **Contents:** insect and disease degree-day models run on Pacific
  Northwest weather stations, including AgriMet's (linked from AgriMet's
  growing-degree-day page).
- **Access:** model pages under `/dd/do_model`, `/risk/models`, `/wea_dd`
  and `/data/`.
- **License and terms:** not checked.
- **robots.txt:** `uspest.org` disallows `/data/`, `/dd/do_model`,
  `/risk/models`, `/wea_dd`, `/histor_data/`, `/histor_data2/`,
  `/current/`, `/fcst/`, `/calc/` and more for every agent, and blocks named
  bots entirely. `pnwpest.org` has the same structure (its named-bot section
  confirmed; its `*` section not re-read).
- **Coverage:** the Pacific Northwest.
- **Use cases:** none directly; compute degree-days ourselves from other
  weather sources instead. AgriMet's static files hold no temperature, so
  that needs another source (511 road-weather stations or IEM's ASOS
  history).
- **For:** farmers, gardeners.
- **Verification:** the `uspest.org` rules match. Corrected: the use case,
  since AgriMet's ET charts can't yield degree-days.
- **Evidence:** robots.txt for [uspest.org](https://uspest.org/robots.txt)
  and [pnwpest.org](https://pnwpest.org/robots.txt).

### USDA Plant Hardiness Zone Map image service

Use · verified: corrected · confidence low · effort S

- **Contents:** SCINet ImageServer services `PHZM` and `PHZM_Recolor`,
  with pixels of about 450 Web Mercator units (about 326 m on the ground at
  43.6° N). The edition (2012 or 2023) isn't stated in the service metadata.
  They sit beside `CDL_WM`, `Cultivated`, `Crop_Mask`, the crop frequency
  layers and soil-property rasters (pH, clay, carbon and others). The
  official 2023 map uses 1991–2020 normals on cells about half a mile on a
  side; its GIS data (grid, shapefile, by ZIP code) comes from the PRISM
  Climate Group at Oregon State University.
- **Access:** ArcGIS ImageServer (Image, Metadata, Mensuration, Catalog;
  `exportImage`, `identify`). The PRISM GIS downloads weren't checked.
- **Coverage:** the lower 48 states (the service extent is wider).
- **License and terms:** not stated on the pages checked ⚠️ (a USDA
  federal work; PRISM's terms not checked).
- **robots.txt:** `pdi.scinet.usda.gov` 404, no rules.
  `planthardiness.ars.usda.gov` disallows only `/core/`, `/profiles/` and
  `README.md` (with Allow rules for static assets).
  `prism.oregonstate.edu/robots.txt` answered with an HTML page, which the
  lenient parser reads as no rules.
- **Updates:** rare (the 2023 map).
- **Use cases:** the hardiness zone on the gardener's yard card (a
  cross-reference to the gardening sources).
- **For:** gardeners. **Needs:** the layer system.
- **Risks:** unknown edition and resampled pixels on SCINet; prefer
  PRISM's official GIS data once its terms are checked.
- **Verification:** confirmed that the services exist. Added: the pixel
  size, the unknown edition, PRISM as the official GIS source, and the
  official map's resolution and normals period. The license is still
  unchecked.
- **Evidence:** [SCINet services](https://pdi.scinet.usda.gov/image/rest/services?f=pjson),
  [PHZM ImageServer](https://pdi.scinet.usda.gov/image/rest/services/PHZM/ImageServer?f=pjson),
  [SCINet robots.txt](https://pdi.scinet.usda.gov/robots.txt),
  [map creation](https://planthardiness.ars.usda.gov/pages/map-creation),
  [how to use the maps](https://planthardiness.ars.usda.gov/pages/how-to-use-the-maps),
  robots.txt for [planthardiness](https://planthardiness.ars.usda.gov/robots.txt)
  and [PRISM](https://prism.oregonstate.edu/robots.txt).

## Farmland change and soils

### IDWR irrigated lands, Treasure Valley (1987–2023), plus Mountain Home and Bruneau-Grandview

Use · verified: corrected · confidence high · effort S

- **Contents:** polygons for the Treasure Valley model boundary classed
  irrigated, non-irrigated or semi-irrigated (IDWR: semi-irrigated
  "typically depicts residential land"). Fields `Acres` and
  `STATUS_<year>`. CRS NAD83 Idaho Transverse Mercator (wkid 102605 /
  EPSG:8826). The line work comes from FSA's 2014 CLU, refined on NAIP and
  DOQQ orthophotos, with status read from Landsat. Hand-digitized years:
  1987, 1994, 1997, 2000, 2004, 2007, 2010, 2015.
- **2023 is a different product:** a random-forest **raster**
  (`TV_2023_RandomForest.tif` with a `.vat`, seen in the zip's central
  directory), not polygons, and not in the MapServer. Its inputs were HLS
  Landsat and Sentinel-2, a 10 m DEM, HAND, OpenET eeMETRIC and PRISM. IDWR
  notes misclassification near rivers (the Boise near Garden City and Nyssa,
  the Payette near Emmett) and at urban and rural edges.
- **Research figures, not re-run:** 433,692 ac irrigated in 1987 against
  372,173 ac in 2015; semi-irrigated 107,167 against 175,579 ac. The study
  boundaries differ between years.
- **Access:** a MapServer per year,
  `gis.idwr.idaho.gov/hosting/rest/services/IrrigatedLands/<year>TreasureValley/MapServer/0`
  for each hand-digitized year (Query; `maxRecordCount` 2000); the folder
  also has `2010MountainHome`. Hub items (data-idwr.hub.arcgis.com) cover
  the Mountain Home Plateau (1987, 2004, 2010, 2015 and a 2023
  machine-learning year, plus a 2010 hand-digitized one) and
  Bruneau-Grandview (1986, 2000, 2007 and a 2010 machine-learning year). The
  2023 Treasure Valley raster is a zip:
  `research.idwr.idaho.gov/GIS/Spatial/LandCover_Vegetation/BoiseValley/RF_IrrigatedLands_2023_TV.zip`
  (880,645 bytes, modified Apr 1, 2026).
- **Coverage:** the Treasure Valley model boundary (nearly all irrigated
  land in Ada and Canyon, plus the edges of Payette and Gem). Mountain Home
  and Bruneau-Grandview are in the ring.
- **License and terms:** no open license. Disclaimer: IDWR makes the data
  available as a public service under the Idaho Public Records Act, without
  warranty. Credit IDWR.
- **robots.txt:** `gis.idwr.idaho.gov`: no rules (the 302 to an HTML error
  page). `data-idwr.hub.arcgis.com`: Crawl-delay 60 for every agent, which
  applies to every path including `/api/download/`; `/sites/`, `/admin/`,
  `/sessions/`, `/groups/`, `/people/` and `/workspace/` are disallowed.
  `research.idwr.idaho.gov`: allows `/`, disallowing only `/assets/*`,
  `/gis/Imagery/delete*`, `empty*`, `AerialPhotos/zold*`,
  `/gis/Spatial/z_Special/*` and `/files/projects/espam/browse/*`.
- **Updates and size:** irregular (every few years); 2023 is the latest for
  the Treasure Valley. About 48–53k polygons per hand-digitized year
  (estimate); the 2023 raster zip is 0.9 MB.
- **Use cases:** farmland-to-subdivision history 1987–2023 (irrigated
  turning semi-irrigated or residential); the year slider; "what was here"
  for a subdivision; water-budget context.
- **For:** history buffs, civic users and planners, farmers, homeowners.
  **Needs:** the shared ArcGIS reader, the layer system, the year slider,
  areas, raster handling for 2023.
- **Risks:** the line work derives from FSA's 2014 CLU, which 7 U.S.C. 8791
  restricts; IDWR publishes this derived product, so using it is fine, but
  note the lineage. The model boundary changes between years, so compare
  inside a common footprint. 2023 is a different method and data type, so
  don't splice it in as another polygon year. "Semi-irrigated" isn't
  strictly "residential".
- **Verification:** confirmed the service list, the 2015 fields and
  description, the hub items for Mountain Home and Bruneau-Grandview, and
  robots.txt. Corrected: 2023 is a raster GeoTIFF, not polygons, and isn't
  in the MapServer; the Mountain Home and Bruneau years are now exact; the
  CRS was added. Not re-checked: the 1987 and 2015 acreages.
- **Evidence:** [IrrigatedLands folder](https://gis.idwr.idaho.gov/hosting/rest/services/IrrigatedLands?f=json),
  [2015 layer](https://gis.idwr.idaho.gov/hosting/rest/services/IrrigatedLands/2015TreasureValley/MapServer/0?f=json),
  [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json),
  the 2023 zip (HEAD, plus one 4 KB range read of its directory),
  robots.txt for [gis.idwr](https://gis.idwr.idaho.gov/robots.txt) (and
  the [error page](https://error.idaho.gov/) it redirects to),
  [the hub](https://data-idwr.hub.arcgis.com/robots.txt) and
  [research.idwr](https://research.idwr.idaho.gov/robots.txt).

### IDWR land use and land-use change, lower Boise River basin (1939, 1994, 2000)

Use · verified: confirmed · confidence high · effort S

- **Contents:** land use interpreted from scanned, geocorrected 1938–39
  black-and-white airphotos (1939) and from colour-infrared airphotos (1994,
  2000), with change layers for 1939–1994, 1994–2000 and 1939–2000. For the
  lower Payette: land use 1992 and change 1949–1997. Related: IDWR's hub also
  lists the 1939 Boise Valley airphoto mosaics themselves (1:20,000
  black-and-white, Soil Conservation Service, mosaicked by township) at
  `research.idwr.idaho.gov/gis/Imagery/AerialPhotos/TreasureValley/TreasureValley_1939/TreasureValley1939.zip`
  (size not checked).
- **Access:** static zips under
  `research.idwr.idaho.gov/gis/Spatial/LandCover_Vegetation/BoiseValley/`:
  `bv_39landcov.zip` (3,631,848 bytes, modified Nov 19, 2014),
  `bv_00landcov.zip` (not checked), `LuChange/bv3900.zip` (9,878,480 bytes,
  Nov 19, 2014).
- **Coverage:** the lower Boise River basin (Ada and Canyon) for 1939, 1994
  and 2000; the lower Payette in the ring.
- **License and terms:** disclaimer only, no warranty. IDWR: use at
  1:24,000 scale or smaller. Credit IDWR.
- **robots.txt:** `research.idwr.idaho.gov` allows `/gis/Spatial/` (only
  `z_Special` is disallowed under it) and
  `/gis/Imagery/AerialPhotos/TreasureValley/` (only `zold*` is disallowed
  under `AerialPhotos`).
- **Updates and size:** static (historical); about 4–10 MB per zip.
- **Use cases:** an 87-year farmland story (1939 to 2025, with Annual NLCD
  and the CDL); the History lens's year slider, with the 1939 airphoto
  mosaic; where irrigation came and went.
- **For:** history buffs, civic users and planners, farmers. **Needs:** the
  year slider, the layer system.
- **Risks:** classes differ between 1939 and the later colour-infrared
  interpretations, so map them to a common legend. The 1:24,000 scale
  limit.
- **Verification:** sizes, the scale note, the catalog titles and
  robots.txt all match. Added: the 1939 airphoto mosaic, which matters for
  the History lens.
- **Evidence:** [IDWR hub catalog](https://data-idwr.hub.arcgis.com/api/feed/dcat-us/1.1.json),
  `bv_39landcov.zip` and `bv3900.zip` (HEAD only),
  [robots.txt](https://research.idwr.idaho.gov/robots.txt).

### USGS Annual NLCD, Collection 1.2 (1985–2025)

Use · verified: confirmed · confidence high · effort M

- **Contents:** six 30 m yearly products for 1985–2025: Land Cover, Land
  Cover Change, Land Cover Confidence, Fractional Impervious Surface,
  Impervious Descriptor and Spectral Change Day of Year. Collection 1.2,
  published Jun 10, 2026 (MRLC), added 2025. National Tree Canopy Cover
  1985–2025 for the lower 48 (published Aug 4, 2026) is made by the USDA
  Forest Service at 30 m from Landsat and Sentinel-2 with Forest Inventory
  and Analysis data. The research's "8,360 validation plots" wasn't
  re-checked.
- **Access:** MRLC's data page and viewer (clip by area; only C1.2 is
  offered there); the full archive on ScienceBase (item
  `655ceb8ad34ee4b6e05cc51a`, not re-checked); a WMS per product on
  `dmsdata.cr.usgs.gov/geoserver` (not re-checked).
- **Coverage:** the lower 48 states, so all of the ring every year since
  1985.
- **License and terms:** public domain (USGS) ⚠️: the USGS page timed out
  (504), so this wasn't re-read. Credit USGS and MRLC, and the USDA Forest
  Service for tree canopy.
- **robots.txt:** `www.mrlc.gov` allows the data pages (it disallows
  `/core/`, `/profiles/`, `/admin/`, `/search/`, user pages, facet query
  strings `/*?f[*` and the NLCD 1992 page). `dmsdata.cr.usgs.gov` 404, no
  rules. `www.sciencebase.gov` allows `/` for every agent, with a
  content-signal line (`search=yes,ai-train=no,use=reference`); it blocks
  some AI crawlers by name (ClaudeBot, anthropic-ai, Claude-Web, GPTBot and
  others), while our own User-Agent falls under `*`.
- **Updates and size:** yearly (around June). A ring clip of about 24
  million pixels per product a year is roughly 3–5 MB compressed; 41 years
  of land cover come to about 150–200 MB (estimate).
- **Use cases:** the core farmland-to-developed measure (the last year in
  class 81 or 82 before the first persistent year in 21–24); impervious
  growth; tree canopy for gardening and shade.
- **For:** history buffs, civic users and planners, farmers, gardeners.
  **Needs:** the raster tile pipeline (categorical encoding), the year
  slider, PostGIS raster or hex aggregation.
- **Risks:** 30 m misses small infill. Year-to-year class flicker needs a
  persistence rule. A new collection may revise earlier years, so keep
  versions. The clip download is by hand.
- **Verification:** confirmed on MRLC: C1.2 (Jun 10, 2026), the six
  products, 1985–2025 coverage, and tree canopy 1985–2025 (Aug 4, 2026;
  USFS). The robots.txt results match. Not re-read (the USGS page timed
  out): the license and the plot count.
- **Evidence:** [MRLC data](https://www.mrlc.gov/data), robots.txt for
  [MRLC](https://www.mrlc.gov/robots.txt),
  [dmsdata](https://dmsdata.cr.usgs.gov/robots.txt) and
  [ScienceBase](https://www.sciencebase.gov/robots.txt),
  [USGS Annual NLCD page](https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database)
  (504 on Oct 7).

### USDA NRCS SSURGO soils: farmland classification (Soil Data Access)

Use · verified: confirmed · confidence high · effort S

- **Contents:** soil map units with their farmland class
  (`mapunit.farmlndcl`) and every soil property and interpretation. One
  query on Oct 7 (`mapunit.muacres` by survey area):

  | Farmland class | Ada County (ID001) | Canyon Area (ID665) |
  |---|---|---|
  | Prime farmland if irrigated | 175,412 ac | 253,994 ac |
  | Prime if irrigated and drained | 12,368 ac | 21,522 ac |
  | Prime if irrigated and reclaimed of excess salts and sodium | 90,941 ac | 15,941 ac |

  The research's Ada "not prime" figure of 238,103 ac wasn't re-checked.
  Survey-area acres aren't county acres: "Canyon Area" isn't exactly Canyon
  County.
- **Access:** tabular SQL by POST to
  `SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest` (JSON, up to 100,000
  rows). Spatial: SDA's WFS and WMS, or gSSURGO state downloads (not
  re-checked).
- **Coverage:** Ada (ID001), Canyon Area (ID665) and every survey area in
  the ring.
- **License and terms:** a federal work (USDA); no license text checked ⚠️.
  Treat it as public domain and credit NRCS.
- **robots.txt:** `sdmdataaccess.sc.egov.usda.gov` and
  `sdmdataaccess.nrcs.usda.gov`: 404, no rules. Web Soil Survey on both
  hosts: 404.
- **Updates and size:** a yearly refresh (October ⚠️, not re-checked).
  Map-unit polygons for two counties are tens of MB.
- **Use cases:** acres of prime-if-irrigated farmland converted to
  development each year (with NLCD and IDWR); a soil card for a field or the
  owner's own yard.
- **For:** civic users and planners, farmers, gardeners, history buffs.
  **Needs:** the layer system, PostGIS overlay.
- **Risks:** survey scale is 1:24,000, so it's not lot-precise. Survey
  areas don't match counties; clip by county. Decide whether the "drained"
  and "reclaimed" variants count as prime.
- **Verification:** confirmed the prime-if-irrigated acres and robots.txt.
  Added: the variant classes and the survey-area caveat. The license is
  still unchecked.
- **Evidence:** [Soil Data Access help](https://sdmdataaccess.nrcs.usda.gov/WebServiceHelp.aspx),
  one farmland-class query on Oct 7, robots.txt for
  [sc.egov](https://sdmdataaccess.sc.egov.usda.gov/robots.txt),
  [nrcs](https://sdmdataaccess.nrcs.usda.gov/robots.txt) and
  [Web Soil Survey](https://websoilsurvey.nrcs.usda.gov/robots.txt).

### American Farmland Trust: Farms Under Threat 2040

Needs owner action · verified: confirmed · confidence medium

- **Contents:** national projections of how development and climate change
  affect farmland to 2040, under three development scenarios (2016–2040),
  with a web mapping tool, state summaries and a storymap. No Treasure
  Valley detail seen.
- **Access:** the report PDF (15.07 MB) and an executive summary (4.15 MB);
  the underlying data through a "Farms Under Threat 2040 Data Request Form"
  (an owner action).
- **Coverage:** national, including Idaho.
- **License and terms:** not stated on the publication page ⚠️.
- **robots.txt:** `farmland.org`: `User-agent: *` with an empty Disallow
  (all allowed), with GPTBot blocked. `farmlandinfo.org`: all allowed.
- **Updates:** static (released June 29, 2022).
- **Use cases:** a "which farmland goes next" overlay beside COMPASS's 2055
  forecasts.
- **For:** civic users and planners, farmers.
- **Risks:** terms unknown, and it's an advocacy product, so label it as
  such.
- **Verification:** confirmed the June 29, 2022 release, the PDF size and
  the data request form. `farmlandinfo.org`'s robots.txt, which the research
  hadn't checked, allows all. Terms still unknown.
- **Evidence:** [publication page](https://farmlandinfo.org/publications/farms-under-threat-2040/),
  robots.txt for [farmland.org](https://farmland.org/robots.txt) and
  [farmlandinfo.org](https://farmlandinfo.org/robots.txt).

## Burning, livestock and range

### Idaho DEQ crop residue burning

Needs owner action · verified: corrected · confidence high · effort M

- **Contents:** daily burn decisions for lands other than Indian
  reservations in Idaho; DEQ runs the program for the Kootenai Tribe of Idaho
  under an MOU. Channels: the Crop Residue Burning Map
  (`www2.deq.idaho.gov/air/CRB/BurnDecisionMap/index`), an email
  subscription on the program page, and a phone line, (800) 345-1007. The
  research reports that the map lists individual registered fields
  (registration and permit numbers, field name, crop, acres); that wasn't
  re-viewed, because the path is disallowed. Annual program reports are in
  DEQ's document library (not re-checked). The "11:00 local" decision time
  wasn't confirmed on the program page.
- **Access:** the map path is robots-disallowed. Email decisions need a
  subscription (an owner action). Annual reports through the advisory
  committee's page (not re-checked).
- **Coverage:** statewide, excluding reservations. Whether Ada or Canyon
  fields appear in a typical season isn't confirmed ⚠️.
- **License and terms:** none stated.
- **robots.txt:** `www2.deq.idaho.gov/robots.txt` has `Disallow: /air/crb/`;
  we match paths case-insensitively, so `/air/CRB/BurnDecisionMap` is
  disallowed. It also disallows `/waste/`, `/water/BurpViewer/` and one
  `/air/<token>/` path. `www.deq.idaho.gov` disallows only `/wp-admin/` and
  `/events/`.
- **Updates:** daily in the burn seasons.
- **Use cases:** "burn day" context; smoke against road-weather visibility
  and crashes on I-84 and rural roads; seasonal burn counts by county.
- **For:** farmers, commuters, fire and hazards watchers, 3D and weather
  viewers. **Needs:** lifecycles, the Valley Feed.
- **Risks:** robots-disallowed for automation. Per the research, the map
  names growers' fields and permits, so even with permission show only zone
  or county decisions and counts. During the research one WebFetch view of
  the disallowed map page was made, not at the owner's request; the
  one-off-checks rule doesn't cover that, so don't repeat it.
- **Verification:** corrected: the program excludes all Indian reservations
  (the Kootenai covered by MOU), not only the Coeur d'Alene and Nez Perce.
  Confirmed: robots.txt and the channels. Unconfirmed: the 11:00 timing and
  the map's contents, which the verifier deliberately didn't fetch.
- **Evidence:** [program page](https://www.deq.idaho.gov/air-quality/smoke-and-burning/crop-residue-burning/),
  robots.txt for [www2](https://www2.deq.idaho.gov/robots.txt) and
  [www](https://www.deq.idaho.gov/robots.txt).

### ISDA county herd districts (open range)

Use · verified: corrected · confidence medium · effort S

- **Contents:** one layer per county (25 layers, including `IDCounties`
  and `IDBoundary`), published from ISDA's ArcGIS Online account. Ada
  (layer 0): districts from a georeferenced historical map of districts set
  up 1908–1966, prepared by the Ada County Planning and Zoning Commission and
  revised June 22, 1971; its copyright text is "Ada County Assessor's
  Office". Canyon (layer 22) has 1 polygon (the research's count), and its
  fields are census and election attributes with no district name. Payette
  is layer 14 and Owyhee layer 17. The layers' data was last edited Aug 4,
  2022. Idaho Code 25-2118, quoted on
  [ISDA's page](https://agri.idaho.gov/plant-industries/range-program/open-range-in-idaho/),
  defines open range as all unenclosed lands outside cities, villages and
  herd districts.
- **Access:** ArcGIS Online FeatureServer queries. ISDA's open-range page
  embeds an Idaho open range and herd district map.
- **Coverage:** Ada, Canyon, Payette and Owyhee in the ring.
- **License and terms:** none stated (empty copyright on most layers); the
  Ada layer credits the Ada County Assessor's Office. ISDA says to check
  herd-district status on the map or with the county commissioners' office.
  Credit ISDA and Ada County.
- **robots.txt:** `services1.arcgis.com/robots.txt` returns 403 ("Invalid
  URL"), a 4xx, so no rules. `agri.idaho.gov/robots.txt` is 200 and empty,
  so no rules.
- **Updates and size:** rare (data last edited August 2022); under 1 MB.
- **Use cases:** an "open range" warning on rural roads (outside herd
  districts and outside city limits); livestock–vehicle crash context with
  the crash and wildlife layers.
- **For:** commuters, cyclists, farmers, wildlife watchers. **Needs:** the
  shared ArcGIS reader, areas, city limits.
- **Risks:** historical and unofficial, so label it "confirm with the
  county". The open-range overlay must also exclude cities and villages. The
  Ada layer credits the Assessor's Office, and the project rule says not to
  redistribute Ada County Assessor data; it looks like a public 1971 map
  rather than parcel data, but the owner should decide before it's
  republished. Canyon's single polygon with census fields is doubtful.
- **Verification:** confirmed the layers, the Ada description and
  robots.txt. Corrected: the data edit date is August 2022; the legal
  definition also excludes cities and villages; the Ada layer is credited to
  the Assessor's Office, so it needs checking against the project's Assessor
  rule. Not re-checked: the "October 2023 item" date and the web app's ID.
- **Evidence:** [ISDA open range page](https://agri.idaho.gov/plant-industries/range-program/open-range-in-idaho/),
  [ISDA robots.txt](https://agri.idaho.gov/robots.txt),
  [FeatureServer](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer?f=json),
  layers [0 (Ada)](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer/0?f=json),
  [22 (Canyon)](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer/22?f=json),
  [14 (Payette)](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer/14?f=json),
  [17 (Owyhee)](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer/17?f=json),
  [services1 robots.txt](https://services1.arcgis.com/robots.txt).

### ISDA dairies, CAFOs and feedlots; EPA ECHO (avoid)

Avoid · verified: confirmed · confidence medium

- **Contents:** ISDA licenses dairies and requires nutrient management
  plans, but publishes no list or map of facilities on its dairy page. EPA's
  ECHO has NPDES permit data, which would include only the few CAFOs with
  federal permits ⚠️ (not verified for Idaho).
- **Access:** ISDA: a public-records request only (linked from the site
  footer). ECHO: the REST API on `echodata.epa.gov` is robots-disallowed;
  bulk zips under `echo.epa.gov/files/echodownloads/` are not (Crawl-delay
  10).
- **License and terms:** ISDA: not applicable. EPA: federal public domain.
- **robots.txt:** `echodata.epa.gov`: `User-agent: *` / `Disallow: *`, so
  everything is disallowed. `echo.epa.gov`: Crawl-delay 10; disallows
  `/detailed-facility-report/`, `/effluent-charts/`,
  `/enforcement-case-report/`, `/facilities/facility-search/results/`,
  `/search/`, `/user/` and others, but not `/files/`.
- **Coverage:** statewide, where anything exists.
- **Use cases:** none. Point maps of farms are what this entry avoids.
- **For:** civic users and planners.
- **Risks:** the facilities are family farms and homes, so point maps would
  track people and businesses. Use NASS's county milk-cow and cattle
  inventories (bulk files) instead.
- **Verification:** no list or map on ISDA's page (confirmed); robots.txt
  on both EPA hosts matches.
- **Evidence:** [ISDA dairy page](https://agri.idaho.gov/animals/dairies-milk/),
  robots.txt for [echodata](https://echodata.epa.gov/robots.txt) and
  [echo](https://echo.epa.gov/robots.txt).

## Ideas by persona

From the research pass, adjusted where verification changed a fact (noted
in each). None is approved. "Correction n" refers to the list under
[What verification changed](#what-verification-changed-in-the-design).

### Farmers and growers

- **Field card.** Click any field (a CSB polygon, labelled "estimated
  field") to see its 8-year crop history (CDL 2018–2025 as a strip of
  labelled crop chips, never colour alone), acres, irrigated status from
  1987 to 2023 (IDWR; 2023 read from the raster, correction 5), its
  irrigation district and canal, the soil's farmland class (SSURGO), IDWR's
  legal season of use, and today's ET for that crop from the nearest
  AgriMet station that carries the crop, not simply the nearest station
  (correction 7). *Sources:* CSB, CDL, IDWR irrigated lands, IDWR irrigation
  organizations, SSURGO, AgriMet charts. *Needs:* layer system, selection and
  picking, panels, readings contract.
- **"Crop water use today."** A daily card per AgriMet station with ET in
  inches by crop at Parma, Nampa, Ontario and Grand View; the Boise and
  Boise Fairgrounds stations give only reference ET and lawn (correction 7).
  Optionally a valley map shading each field by today's ET for its CDL crop,
  from the nearest station that has that crop. Read once a day from the
  static chart files, which run 2–3 days behind. *Sources:* AgriMet charts,
  CDL, CSB. *Needs:* readings contract (time-series card), places
  (stations), layer system.
- **County farm dashboard** (also for civic users). Farms, land in farms,
  irrigated acres, sales, and milk-cow and cattle inventories for Ada,
  Canyon and the ring counties from every census (2002–2022) and the yearly
  surveys. Examples: Ada lost 12% of its farms from 2017 to 2022; Canyon had
  207,577 irrigated acres and $829 M in sales in 2022. Aggregate livestock
  numbers take the place of mapping dairies. *Sources:* NASS bulk files and
  census profiles. *Needs:* readings contract, areas (counties).
- **Dry-year view** (also for civic users). A weekly drought strip per
  county (USDM percent area by category, from the categorical statistics,
  correction 8), next to water-right priority dates along the Boise River
  (who gets cut first). Owner names never appear: only uses and priority
  years, as a cumulative "acres by priority decade" chart per diversion.
  Diversion points that began as PLSS centroids aren't shown as exact
  locations. *Sources:* USDM, IDWR water rights, IDWR diversions.
  *Needs:* readings contract, areas, `restricted` schema.

### Farmers and gardeners: canal water

- **Canal water season as lifecycles.** Each district's announced turn-on
  and shut-off dates appear in the Valley Feed ("NMID: Ridenbaugh Canal
  water on, Apr 1–8; patrons mid-to-late April"). The canal network
  animates in season (water flowing out from the diversion over the fill
  period), with IDWR's legal season-of-use window beside it. The WD 63
  diversion records would confirm the actual dates if IDWR agrees to
  scripted access. *Sources:* district announcements, HydroShare canal
  network, IDWR irrigation organizations, IDWR season of use, IDWR
  diversions. *Needs:* lifecycles and the Valley Feed, manual source kind,
  time and replay clock, areas.

### Gardeners (the owner's own place only)

- **My yard's water.** The AgriMet LAWN column as "lawn water use (ET)
  this week". The research proposed "your lawn needs about X inches", but
  the static files carry no precipitation, so rain can't be subtracted
  (correction 7). Plus when my district's canal water comes on and goes
  off, IDWR's legal season window for my spot, the soil's farmland class and
  texture (SSURGO), and the hardiness zone. Only for the owner's own place,
  never other people's lots. *Sources:* AgriMet charts, district
  announcements, IDWR irrigation organizations, IDWR season of use, SSURGO,
  hardiness zone service. *Needs:* the private home plugin, readings
  contract, lifecycles.

### History buffs

- **An 87-year farmland slider.** 1939 land use (IDWR, from the 1938–39
  airphotos, with the 1939 mosaic itself), then IDWR's irrigated lands for
  1987, 1994, 1997, 2000, 2004, 2007, 2010 and 2015, Annual NLCD every year
  1985–2025, and CDL crops from 2005; swipe against the historic NAIP years.
  2023's irrigated lands are a raster from a different method, compared by
  zonal statistics inside a common footprint, not shown as another polygon
  year (correction 5). A headline counter from IDWR's own layers: irrigated
  land in the Treasure Valley model area went from about 433,700 ac (1987)
  to 372,200 ac (2015), while semi-irrigated (mostly residential) grew from
  about 107,200 to 175,600 ac. Those figures weren't re-run and the
  boundaries differ, so recompute them inside a common footprint before
  publishing. *Sources:* IDWR land use, IDWR irrigated lands, Annual NLCD,
  CDL. *Needs:* year slider, raster tile pipeline, layer system.
- **Irrigation districts then and now** (also for civic users). The 1941
  Boise Valley district map against today's service areas, with each
  district's farmed share (CSB and CDL acres inside) against its urban share
  (NLCD developed), showing districts turning into "urban irrigation"
  suppliers for subdivisions. *Sources:* IDWR irrigation organizations,
  Annual NLCD, CSB. *Needs:* year slider, areas, PostGIS overlay.

### Civic users and planners

- **"Where did the farm go?"** For each subdivision plat or permit cluster
  from COMPASS, show what the land was the year before (CDL crop, IDWR
  irrigated status, NLCD class) and its soil class; per city and per year,
  count acres of "prime farmland if irrigated" converted. Check NLCD's
  conversion year (correction 11) against the plat dates. The research
  called COMPASS's plats and permits already loaded; per
  [SOURCES](../SOURCES.md) they were approved on Oct 6 and haven't been
  built yet. Whether the "drained" and "reclaimed" soil variants count as
  prime is open (smaller corrections). *Sources:* Annual NLCD, SSURGO, CDL,
  IDWR irrigated lands. *Needs:* the development plugin (COMPASS plats and
  permits), PostGIS overlay and hex aggregation, year slider.
- **Farmland pressure ahead.** COMPASS's 2055 household and job forecasts
  (also approved Oct 6 and not yet built) over today's cropped fields and
  irrigation-district service areas, showing which districts' farms sit
  inside growth zones. AFT's 2040 conversion scenarios could join if the data
  request succeeds, labelled as an advocacy model. *Sources:* CSB, IDWR
  irrigation organizations, AFT Farms Under Threat. *Needs:* development
  plugin, areas, layer system.

### Researchers (one-off analysis)

- **Water budget of urbanization.** Irrigated acres (IDWR) × seasonal ET
  (METRIC) for 1987–2015 on the farms that became subdivisions. Do lawns use
  more or less water than the fields they replaced? IDWR has no Treasure
  Valley ET after 2015 (correction 6), so the "today" side needs OpenET
  (only with its written consent) or AgriMet's LAWN point values; otherwise
  the comparison stops at 2015. Published as a chapter with charts.
  *Sources:* IDWR irrigated lands, IDWR METRIC, Annual NLCD, AgriMet charts.
  *Needs:* PostGIS raster and zonal statistics, a one-off script in
  `tools/`.

### Commuters and drivers

- **Harvest-season roads.** From early September to November, flag rural
  arterials that border large fields of late-harvest crops (beets, corn,
  onions, potatoes) as "farm equipment and truck season". Timing comes from
  Idaho's weekly crop progress (NASS bulk files) and, valley-wide only, the
  gridded winter-wheat progress; Idaho corn may not be covered ⚠️
  (correction 4). Check against seasonal crash patterns with farm equipment
  and slow vehicles, and against counter volumes. Haul routes to processing
  plants are a guess ⚠️ until checked. *Sources:* CDL, CSB, NASS bulk files,
  Crop Progress layers. *Needs:* roads plugin (segments), safety plugin
  (crashes), time and replay clock, lifecycles.
- **Open range on the map** (also for cyclists). Outside ISDA's herd
  districts and outside city and village limits (correction 12), livestock
  may legally be on the road. Shade those rural roads with a "confirm with
  the county" note, and link to livestock- and wildlife-vehicle crashes. The
  Ada layer waits on the owner's ruling under the Assessor rule; Canyon's
  layer is unverified. *Sources:* ISDA herd districts. *Needs:* areas (with
  city limits), roads plugin, safety plugin.
- **Smoke and visibility** (also for hazards watchers). If DEQ agrees to a
  feed, daily crop-residue burn decisions by zone (never individual field
  registrations) next to 511 road-weather visibility and crashes on I-84 and
  rural highways, to test whether burn days line up with low-visibility
  incidents. *Sources:* DEQ crop residue burning. *Needs:* lifecycles,
  conditions plugin (511 road weather), safety plugin.
- **Canal crossings** (also for civic users). Intersect the named canal
  network with ACHD and COMPASS road segments to list every canal crossing
  and its irrigation district: the narrow bridges and culverts that limit
  road widening (the [ch. 16](../16-ideas-and-personas.md) idea), useful for
  before-and-after work on ACHD's Five-Year Plan. *Sources:* HydroShare canal
  network, IDWR irrigation organizations. *Needs:* roads plugin (segment
  matcher), places and search, evidence and review (OpenStreetMap,
  HydroShare and NHD canals side by side).

### Hikers and cyclists

- **Canal banks aren't paths.** Draw canal maintenance roads as
  irrigation-district access, not public access, unless a city pathway runs
  along them. Show which district runs each canal (whom to ask).
  Canal-safety season (swift water) switches on with the turn-on dates. The
  legal specifics need checking ⚠️. *Sources:* HydroShare canal network,
  IDWR irrigation organizations, district announcements. *Needs:* lands and
  trails plugins, lifecycles.

### 3D and weather viewers

- **Living fields in 3D.** CSB polygons filled with low-poly instanced
  crops by CDL class (tall corn, knee-high beets, flat alfalfa, trellised
  hops), whose height and colour follow the time and replay clock through
  the season: bare in March, green-up from Sentinel-2 NDVI per field,
  harvested and brown afterwards. Per-field state comes only from NDVI; the
  9 km Crop Progress cells can at most set a valley-wide timing curve
  (correction 4), and AgriMet's crop calendars are assumptions, labelled as
  such if used (correction 7). CSB edges are simplified at 60 m, so clip the
  crops by road buffers from OpenStreetMap (correction 3). Use Collection 1
  Sentinel-2 scenes (correction 13). Scrub the clock from April to October
  and the valley grows and is cut. *Sources:* CSB, CDL, Sentinel-2, Crop
  Progress layers. *Needs:* 3D engine (instancing, levels of detail), time
  and replay clock, layer system.
- **The valley breathing.** An ET layer (IDWR METRIC seasonal grids for
  1987–2015, plus today's AgriMet ET at its stations) showing evaporative
  cooling over irrigated fields against the dry desert benches, feeding the
  3D weather reconstruction as a moisture source for low cloud and valley
  fog in the shoulder seasons. No IDWR grid covers the Treasure Valley after
  2015 (correction 6). If Reclamation allows scripted AgriMet weather, its
  humidity, radiation and wind add ground truth. *Sources:* IDWR METRIC,
  AgriMet charts, AgriMet and Hydromet services. *Needs:* raster tile
  pipeline, 3D engine (volumetric weather), readings contract.

### Wildlife watchers

- **Farm habitat in aggregate.** Harvested-corn and alfalfa areas (CDL),
  plus wetlands and pasture, as winter waterfowl and pheasant habitat
  context by hex, never pointing at private farms. Link to wildlife-vehicle
  crash hot spots on roads between the fields and the river (see the
  [wildlife sources](wildlife.md)). *Sources:* CDL, ISDA herd districts.
  *Needs:* hex aggregation, wildlife plugin, safety plugin.

### Fire and hazards watchers

- **Dry-fuel edge.** Where fallow and idle cropland and grass/pasture
  (CDL) meet subdivisions and sagebrush (NLCD), shown with the weekly
  drought category: context for the fire layer, not a prediction.
  *Sources:* CDL, Annual NLCD, USDM. *Needs:* hazards plugin, layer system.

## Design notes

The research pass's proposal, with verification's changes folded in where
they apply. The full list of changes follows in the next section.

### What exists for the valley

- **Crops and fields are well covered by open federal data.** The CDL
  (public domain, Idaho since 2005), NASS's synthetic field polygons with
  8-year histories (CSB), Annual NLCD back to 1985, and SSURGO's farmland
  classes all reach the whole ring, Oregon included, with no key. No farmer
  is identifiable in any of them by design. FSA's real field boundaries are
  closed by law and not needed.
- **IDWR is the strongest local source.** Irrigated lands since 1987,
  land use back to 1939, irrigation districts today and in 1941, season of
  use, water rights, wells and diversion sites, all disclaimer-only public
  records with no robots.txt rules on its GIS host.
- **The gaps are current water use and canal timing.** IDWR has no
  Treasure Valley ET after 2015; OpenET's terms forbid apps without written
  consent; AgriMet's open static files carry ET only, at six stations (two
  of them lawn only). Canal on and off dates have no machine feed: district
  announcements are read by hand, and the true diversion records sit behind
  a guest login.
- **Several obvious routes are closed by robots.txt:** the Quick Stats API,
  AgriMet's and Hydromet's data scripts, Reclamation's RISE API, DEQ's burn
  map, the Drought Monitor's polygons and OSU's pest models. Each has an open
  alternative or needs a request, listed under
  [Robots and terms findings](#robots-and-terms-findings-that-change-plans).

### Plugin shape (a proposal for the owner)

- **A public `farm` plugin** (`plugins/farm/`), under the Land lens or a
  new Farm grouping. It depends on nothing for ingest; its app layers use
  `development` (COMPASS plats and permits) and `roads` for the crossing
  and harvest-road ideas.
- **Sources by kind:**
  - Scheduled: `agrimet_et_charts` (daily, six small static files);
    `usdm_county` (weekly, the statistics API); `idwr_irrigation_orgs`,
    `idwr_season_of_use` and `idwr_diversion_sites` (monthly, through the
    shared ArcGIS reader); `herd_districts` (yearly).
  - Manual, loaded by hand: `cdl_clip` (yearly, after the February
    release); `csb_clip` (yearly); `nlcd_annual_clip` (yearly, after June);
    `idwr_irrigated_lands` and `idwr_land_use` (once, plus new editions);
    `idwr_metric_et`; `tv_canals_hydroshare` (once; the owner downloads it,
    since HydroShare's download path is robots-disallowed);
    `canal_season_dates` (twice a year); `nass_bulk` (once or twice a year);
    `ssurgo_farmland` (yearly).
- **Republishing**, as the research proposes it (the owner decides):
  - yes: CDL, CSB, NLCD, NASS, SSURGO, the HydroShare network (CC BY, with
    credit);
  - yes, with credit: IDWR's layers and AgriMet (disclaimer only, public
    records);
  - as aggregates, with the required credit line: USDM;
  - never: well and water-right owner fields, which go to `restricted` or
    aren't stored.

### Tables

Following [ch. 12](../12-database-schema.md)'s kinds and
[ch. 15](../15-plugins.md)'s rule that public plugins keep their tables in
the shared schemas, owned through the plugin's manifest (correction 10):

- `core.field`: CSB polygons, with `csbid`, acres, `crop_by_year` (jsonb)
  and the edition.
- `core.irrigation_org`: IDWR service areas, with the 1941 layer as a
  separate edition.
- `core.canal`: the HydroShare geometry, with OpenStreetMap and NHD kept as
  separate evidence; the evidence and review core picks the display
  geometry.
- `obs.crop_et`: AgriMet daily ET by station, crop and date; a few thousand
  rows a year, so a plain table like `obs.traffic_count` rather than a
  hypertable (correction 10).
- `obs.drought_county`: USDM weekly by FIPS code.
- `evt.event` lifecycles for canal seasons, and later for burn decisions if
  DEQ allows.
- A land-change table owned by the farm plugin in `core` (the research
  proposed `farm.land_change`, a schema public plugins don't get;
  correction 10): per hex, the conversion year from NLCD's
  agricultural-to-developed rule (correction 11), joined to IDWR's irrigated
  status, SSURGO's farmland class and COMPASS's plat dates as evidence. The
  per-pixel result stays a COG, not a 24-million-row table.
- **Rasters** (CDL and NLCD by year, METRIC ET, the IDWR 2023 raster):
  built by `basemap/` into `/tiles/farm/<product>/<year>/` as paletted,
  lossless PNG or WebP, never lossy, with overviews by mode or nearest, not
  averaging as for terrain (correction 9). Our own palette follows
  [ch. 13](../13-visual-design.md): crops told apart by label or pattern on
  hover, never red and green alone.
- **Storage, rough:** CDL about 21 yearly ring clips, 150–300 MB; NLCD 41
  years of land cover plus change, about 200 MB; CSB tens of MB; IDWR
  polygons a few hundred MB at most; METRIC only the Treasure Valley
  seasonal grids (the yearly ESPA zips run to 1.6 GB and aren't needed);
  everything else tiny.

### Processing

- **CDL resolution break.** 30 m to 2023, 10 m from 2024, with a new
  classifier. For time series use NASS's own 30 m releases of 2024 and 2025
  rather than our own resample, and flag the break in the interface
  (correction 2). 10 m for display needs the CropScape WCS or the 9–10 GB
  national zips; CropScape's other services work at 30 m, and their boxes
  are in EPSG:5070 metres, so project the valley box and ring first and clip
  afterwards (correction 1).
- **Per-field crop by year:** the majority CDL class inside each CSB
  polygon for years outside CSB's 8-year window (editions go back to
  2008–2015). Join CSB editions spatially, since IDs encode the window
  (correction 3).
- **IDWR irrigated lands:** "semi-irrigated" is IDWR's residential proxy.
  Compare years only inside the intersection of the yearly model boundaries,
  and bring in 2023 by zonal statistics, not as polygons (correction 5).
  Reproject from EPSG:8826.
- **1939 land use** needs a class crosswalk to the later legends.
- **Land-change rule:** the conversion year is the first year of a
  persistent developed run (for example two or more years in 21–24), with
  the last agricultural year (81 or 82) before it recorded, so class flicker
  and construction-time grassland, barren or fallow years don't count
  (correction 11).
- **Sentinel-2 NDVI per field** needs numpy or rasterio, which breaks the
  standard-library-only ingest rule: an owner decision, or a `tools/` job
  that writes small per-field statistics.

### Rendering

- **2D:** a fields layer (CSB outlines tinted by crop); a farmland-change
  layer (year converted, as a sequential ramp); canals (blue lines that
  animate in season); district areas; an open-range road overlay.
- Every year layer hangs off the shared year slider in the History lens.
- **3D "living fields":** per-crop instanced low-poly meshes inside CSB
  polygons, with levels of detail, clipped by road buffers (correction 3).
  Height and colour follow a per-field season curve from Sentinel-2 NDVI;
  NASS's gridded progress only as a valley-wide timing curve for winter
  wheat (correction 4); AgriMet's crop start dates as labelled assumptions.
  Driven by the time and replay clock, which needs instancing support in our
  own WebGL engine.

### Ethics and privacy

- No farmer is identified: CSB and CDL are non-confidential by design.
- FSA's CLU is restricted by law and avoided.
- DEQ's burn map reportedly lists individual growers' field registrations,
  so show zone decisions and counts only, even with permission.
- IDWR's wells and water rights carry owner names and well addresses:
  aggregate them, or keep those fields in `restricted`.
- No dairy or CAFO point maps; NASS's county inventories instead.
- The gardener views apply only to the owner's own place.

### Robots and terms findings that change plans

| Host or source | Finding | What to use instead |
|---|---|---|
| `quickstats.nass.usda.gov` | `Disallow: /` | NASS bulk files on `www.nass.usda.gov` |
| `www.usbr.gov/pn-bin` (AgriMet and Hydromet scripts) | Disallowed | AgriMet's static ET chart files; ask Reclamation |
| `data.usbr.gov/rise/api` | Disallowed | Ask Reclamation; no third-party mirrors |
| `www2.deq.idaho.gov/air/crb/` (burn decisions) | Disallowed | Ask DEQ, or the email subscription |
| `droughtmonitor.unl.edu/data/` (USDM polygons) | Disallowed | County statistics from `usdmdataservices.unl.edu`; ask NDMC |
| HydroShare `/django_irods/download/` | Disallowed | One hand download by the owner |
| `echodata.epa.gov` | Everything disallowed | NASS county livestock inventories |
| `uspest.org` model paths | Disallowed | Our own degree-days from other temperature sources |
| OpenET | Terms forbid apps and scraping without written consent | IDWR METRIC (to 2015) and AgriMet ET |
| `ndmcgeodata.unl.edu`, `www.fsa.usda.gov` | Unreachable (TLS error, network error) | Treat as disallowed for now |

### Licensing summary

| Terms | Sources |
|---|---|
| Public domain, stated | CDL, CSB, Crop Progress layers (NASS); EPA ECHO |
| Public domain, inferred ⚠️ | NASS bulk files, Annual NLCD (not re-read), SSURGO, AgriMet |
| CC BY 4.0 | HydroShare canal network (cite the DOI) |
| Free and open, with credit | Sentinel-2 ("Contains modified Copernicus Sentinel data") |
| Required credit line | U.S. Drought Monitor |
| Disclaimer only (public records): credit IDWR | IDWR irrigated lands, land use, irrigation organizations, season of use, water rights, wells, diversions, METRIC |
| None stated | ISDA herd districts (Ada layer credits the Assessor's Office), DEQ burn program, hardiness zone service ⚠️, AFT ⚠️ |
| Facts plus a citation | Irrigation district announcements |
| Restricted by law | FSA Common Land Units |
| Restrictive terms | OpenET (personal, noncommercial; written consent for apps); Quick Stats API (key and attribution line) |

### Numbers worth keeping

From official pages and queries on Oct 7, 2026, except where marked:

- **CDL, Canyon County 2025:** corn 43,553 ac; alfalfa 28,990; winter wheat
  24,385; sugarbeets 10,925; mint 9,086; onions 9,918 and hops 6,852 (both
  not re-run).
- **Census of Agriculture 2022:** Canyon 2,311 farms, 277,388 ac in farms,
  207,577 irrigated, $829 M in sales. Ada 1,142 farms (−12% since 2017),
  112,556 ac, 35,479 irrigated.
- **IDWR Treasure Valley irrigated:** 433,692 ac (1987) to 372,173 ac
  (2015); semi-irrigated 107,167 to 175,579 ac (boundaries differ; not
  re-run).
- **SSURGO "prime farmland if irrigated":** Ada 175,412 ac, Canyon Area
  253,994 ac (map-unit acres by survey area).
- **Irrigation organizations:** 59 in the valley box; the Boise Project
  Board of Control has 243,432 ac of service area (not re-run).
- **WD 63:** 78 active canal diversions in IDWR's site layer.
- **USDM, Canyon County, Aug–Sep 2026:** 100% in D0 or worse, 11.28% in D1
  or worse.

## What verification changed in the design

Verification on Oct 7 of the design as well as the sources. Numbers are
referred to above.

**Technical errors that change the plan**

1. **CDL at 10 m.** CropScape's 2025 statistics are computed on 30 m
   pixels (Canyon corn: 195,837 pixels = 43,553.1 ac, 900 m² each), and
   SCINet's CDL_WM is a Web Mercator resample at 30 m. The only keyless
   route to a 10 m clip found is CropScape's WCS (`wms_cdlall.cgi`, whose
   DescribeCoverage for `cdl_2025` reports a 10 m grid in EPSG:5070);
   otherwise it's the 9.0–9.8 GB national zips. CropScape's box and point
   parameters are EPSG:5070 metres, not longitude and latitude: project the
   valley box and the ring first (the ring's projected envelope is larger
   than its longitude-latitude box), then clip.
2. **CDL time series.** Both the classifier and the resolution change in
   2024, so 2023-to-2024 changes can be artifacts. Use NASS's own 30 m 2024
   and 2025 releases for series rather than our own majority resample, and
   flag the break in the interface.
3. **CSB.** Source Cooperative's copy is no alternative for history: it
   has only the 2023 crop, with neighbouring polygons of the same crop
   dissolved, so it can't fill `crop_by_year`; drop it from the
   bulk-download question, or offer it only as 2023 outlines. CSB polygons
   are simplified at 60 m from a 10 m stack, so 3D crops will spill over
   field edges and roads; clip them by OpenStreetMap road buffers. CSBIDs
   encode the window years, so join editions spatially, not by ID.
   Rebuilding CSB from a CDL clip needs ArcGIS Pro (NASS's code), so it isn't
   an option.
4. **Crop Progress layers are 9 km synthetic cells.** They can't set
   per-field 3D state; use them at most as a valley-wide timing curve (winter
   wheat; Idaho corn probably absent ⚠️). Per-field state comes only from
   Sentinel-2 NDVI.
5. **IDWR's 2023 Treasure Valley irrigated lands is a raster**
   (`TV_2023_RandomForest.tif`, seen in the zip's central directory by one
   4 KB range read), not polygons, and isn't in the MapServer. The
   1987–2023 slider and "Where did the farm go?" must compare 2023 by zonal
   statistics inside a common footprint. IDWR documents misclassification
   along rivers and at urban and rural edges, which is exactly where
   conversions happen.
6. **METRIC ET.** The Treasure Valley has only 1987, 1994, 2000, 2004,
   2007, 2010 and 2015; every later group, the 2024 zip included, is ESPA.
   So "the valley breathing" and the water budget of urbanization have no
   IDWR data after 2015. The Treasure Valley window (Mar 1–Oct 31) differs
   from ESPA's (Apr 1–Oct 31). Don't download ESPA zips (1.6 GB) for this
   theme.
7. **AgriMet static files.** Boise and Boise Fairgrounds carry only ETr
   and LAWN; crop ET exists only at Parma, Nampa, Ontario and Grand View,
   each with its own column set and repeated names for different crop
   calendars. Parse by position and map to the rows of `<station>ch.txt`.
   The field card and "crop water use today" must pick the nearest station
   that has the crop. The `ch.txt` dates are Reclamation's assumed
   calendars, not observed planting, so label them if they drive the 3D
   season. The files lagged 2–3 days on Oct 7. `www.usbr.gov` resets HEAD
   requests (use GET), and `location.csv` starts with a stray
   `Content-disposition` line. The gardener's "your lawn needs about X
   inches" can't subtract rain (precipitation is only behind the disallowed
   `/pn-bin`), so call it "lawn water use (ET)". Degree-days can't come from
   these files either.
8. **USDM.** `statisticsType=1` is cumulative (D0 includes D1–D4), so
   stacking it double-counts; use `statisticsType=2` for the drought strip.
   The license should carry NDMC's required credit line from the Permission
   page.
9. **Raster tiles.** CDL classes, NLCD classes and the IDWR 2023 raster are
   categorical: encode them losslessly (PNG or lossless WebP, never lossy)
   and build overviews by mode or nearest, not by averaging as for terrain,
   or class codes and colours break.
10. **Schema.** [Ch. 15](../15-plugins.md) keeps public plugins' tables in
    the shared schemas by kind (`core`, `obs`, `evt`; `restricted` for
    personal fields); only private plugins get their own schema. So
    `farm.land_change` becomes a `core` table owned by the farm plugin's
    manifest, and `obs.crop_et` (a few thousand rows a year) can be a plain
    table like `obs.traffic_count` rather than a hypertable.
11. **Land-change rule.** Annual NLCD pixels flicker between classes, and
    conversions in the valley often pass through grassland, barren or
    fallow during construction. Define the conversion year as the first
    year of a persistent developed run (for example two or more years in
    21–24) and record the last agricultural year (81 or 82) before it.
    Store per-pixel results as a COG, not a 24-million-row per-cell table,
    and aggregate to PostGIS hexes.
12. **Open range.** Idaho Code 25-2118 (quoted by ISDA) excludes cities and
    villages as well as herd districts, so the overlay needs city limits
    too. The Ada herd-district layer's copyright is the Ada County Assessor's
    Office, and the project rule says not to redistribute Assessor data, so
    the owner should rule on it before it's tiled. Canyon's single polygon
    carries only census and election fields; treat it as unverified.
13. **Sentinel-2.** Use Earth Search's `sentinel-2-c1-l2a` (Collection 1,
    bucket `e84-earth-search-sentinel-data`, from 2015-06-27); the registry
    dataset the research cited is superseded. From memory ⚠️: older-collection
    scenes after the January 2022 processing-baseline change carry a
    reflectance offset that biases NDVI.
14. **DEQ.** The burn program covers lands other than Indian reservations
    (the Kootenai by MOU), not lands excluding only the Coeur d'Alene and
    Nez Perce reservations.
15. **HydroShare.** The download requires accepting the CC BY 4.0 license
    on the page. Accepting is the owner's action, along with the hand
    download.

**Smaller corrections**

- IDWR's hub has a 60 s Crawl-delay for every path, including
  `/api/download/`: space hub downloads at least 60 s apart, and prefer the
  FeatureServers.
- IDWR's layers are in NAD83 Idaho Transverse Mercator (EPSG:8826);
  reproject.
- Water-right POD points began as PLSS centroids; don't present them as
  exact diversion locations in the priority-date view.
- SSURGO survey areas (ID001 "Ada County", ID665 "Canyon Area") aren't
  counties; clip by county. The "prime if irrigated and drained" and
  "reclaimed of salts" variants add 103,309 ac in Ada and 37,463 ac in
  Canyon Area; decide whether the farmland-loss measure counts them.
- The CDL's overall accuracy excludes classes sampled from NLCD, including
  Grass/Pasture (Canyon's largest class), which has no reported accuracy.
- The CSB national zip was re-issued May 15, 2026 (the edition came out
  Mar 27), and `irgdist41.zip` was re-uploaded May 27, 2026. Check
  Last-Modified before each pull and keep versions.
- Annual NLCD Tree Canopy Cover is made by the USDA Forest Service; credit
  it separately.
- The research gave the diversion database's access as "account"; the
  guest login needs no credentials, but it's still a session form, and
  scripting it needs IDWR's OK. The verdict stays "needs owner action".
- The 2027 Census of Agriculture's results arrive around 2029 ⚠️.
- Worth adding for the History lens: IDWR's 1939 Boise Valley airphoto
  mosaics (`TreasureValley1939.zip`, under an allowed path; size not
  checked).
- The Quick Stats API terms forbid modifying content only while still
  presenting NASS as the source, not modifying it outright. Moot, since the
  host disallows all robots.

## Requests made during the research

For transparency. All requests used the project's honest User-Agent,
paced 1–3 seconds apart (verification: 1.5–2 s with curl, and WebFetch for
documentation pages). No accounts were created, no keys requested, no forms
submitted and no datasets downloaded.

- **Research pass:** robots.txt for every host above; about 25 ArcGIS
  metadata reads and 6 small attribute or statistics queries on
  `gis.idwr.idaho.gov`, across 6 services; 1 catalog read on IDWR's hub
  (Crawl-delay 60; a single request); 2 CropScape requests (statistics and
  the cached JSON); 1 Soil Data Access query (an earlier attempt returned
  nothing); 1 USDM statistics request; 1 AgriMet chart file, plus
  `location.csv` and three AgriMet pages; 2 herd-district counts and 2 layer
  metadata reads; HEAD-only size checks on 5 IDWR zips and 2 NASS CSB zips;
  2 Census of Agriculture county profile PDFs; 1 probe of `nmid.org/feed/`
  (404).
- **One request to a disallowed path.** The research made one WebFetch
  view of `www2.deq.idaho.gov/air/CRB/BurnDecisionMap`, after reading a
  robots.txt that disallows it, to see what the page shows. It wasn't
  requested by the owner, so the one-off-checks rule doesn't cover it.
  Nothing was stored and it wasn't repeated; verification didn't fetch it.
  Flagged for the owner to judge.
- **Verification pass:** robots.txt for about 30 hosts; about 20 ArcGIS
  metadata reads plus 4 small attribute or count queries on
  `gis.idwr.idaho.gov`; 1 IDWR hub catalog read; HEAD requests on 5 IDWR
  zips, the CSB zip and `cpc2026.zip`; one 4 KB range read of the IDWR 2023
  zip's directory; CropScape's GetCDLStat and its cached JSON, 1 WCS
  DescribeCoverage and 4 developer-guide pages; 1 Soil Data Access query and
  1 USDM query; 2 Source Cooperative files (README, LICENSE); 2 Census of
  Agriculture PDFs; the NMID, HydroShare and ISDA landing pages.
- **More than the usual sample on one host.** On `www.usbr.gov`,
  verification read `location.csv`, six 2026 ET chart files (5–41 KB each),
  `pmaich.txt`, and the disclaimer and CropCharts pages: more than the one or
  two samples usually taken from a host. All are allowed static files, and
  nothing was stored in the repository.
- The session's web-search budget ran out partway, so every check was a
  direct read of an official page or endpoint; items still resting on
  secondary sources or memory are marked ⚠️.

## Open questions

For the owner, one at a time; none is decided.

1. **Plugin and display:** is there a `farm` plugin, with a Farm lens or
   under Land? Should CDL and NLCD be raster tiles built by `basemap/`, or
   only per-field and per-hex vector summaries?
2. **Bulk downloads** need the owner's OK for each run: the NASS CSB
   2018–2025 national zip (3.76 GB) once a year (Source Cooperative's copy is
   no substitute for its history; at most 2023 outlines, correction 3); a
   CDL clip, either 30 m through CropScape or 10 m through its WCS, rather
   than the 9.8 GB national 10 m zip (correction 1); Annual NLCD clips from
   the MRLC viewer or ScienceBase; the NASS bulk files once or twice a year.
3. **Reclamation:** should the owner ask agrimet@usbr.gov for permission to
   script AgriMet and Hydromet (`/pn-bin` is robots-disallowed, and RISE's
   `/rise/api` too)? Until then, only the static ET chart files, and weather
   values only through one-off lookups by hand.
4. **DEQ crop residue burning:** `/air/crb/` is robots-disallowed and the
   map reportedly names growers' fields. Ask DEQ for a zone-level feed or
   permission, or have the owner subscribe to the email decisions (an owner
   action) and show zone-level decisions only? And how does the owner judge
   the one WebFetch view of that page during the research?
5. **IDWR Water District 63:** ask IDWR or the watermaster whether daily
   canal diversion data (the Diversion Data app behind a guest login, or
   Aqua Info's CSV) may be fetched by a script, for true canal on and off
   dates?
6. **USDM polygons** sit under the disallowed `/data/`. Ask NDMC
   (DroughtMonitor@unl.edu), or show county statistics only (allowed)?
7. **HydroShare canal network** (CC BY 4.0, 1.3 MB): OK for the owner to
   accept the license and download it by hand? And which canal geometry wins
   on the map: HydroShare, OpenStreetMap, or NHD/3DHP?
8. **Dependencies:** should ingest stay standard-library only? Sentinel-2
   NDVI per field and raster zonal statistics want numpy, rasterio or GDAL
   (a new dependency, or a `tools/` job).
9. **Personal fields:** confirm that water rights and wells drop or
   restrict `Owner` and `WellAddress` and publish only aggregates and uses.
10. **OpenET** (current-year field ET) needs an account and written consent
    for apps. Ask, or rely on IDWR METRIC (Treasure Valley 1987–2015) plus
    AgriMet?
11. **AFT Farms Under Threat:** the data comes by request form with unknown
    terms. Worth asking?
12. **Quick Stats API:** its host disallows all robots and the bulk files
    are fine; does the owner also want a key for one-off hand lookups?
13. **Scope:** how far into the regional ring should farm layers go? CDL,
    CSB, NLCD and USDM cover Malheur County, Oregon too; IDWR's layers stop
    at the Idaho line.
14. **Ada herd districts:** the layer credits the Ada County Assessor's
    Office. Does the project's rule against redistributing Assessor data
    apply to this 1971 planning map (correction 12)?
15. **Prime farmland:** should the farmland-loss measure count SSURGO's
    "prime if irrigated and drained" and "reclaimed of salts" variants
    (103,309 ac more in Ada, 37,463 ac in Canyon Area)?
16. **Disclaimer-only layers:** the research proposes republishing IDWR's
    layers, AgriMet's ET and the herd districts with credit, on the strength
    of their public-records disclaimers. Is that enough, or should the
    Oct 6 "no license: use it and send a courtesy note" rule (stated for
    city and county imagery, [DECISIONS](../DECISIONS.md)) be extended to
    them, as the [wildlife sources](wildlife.md) page asks for IDFG?
