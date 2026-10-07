# Weather sources (researched Oct 7, 2026)

Weather data for the Treasure Valley: radar, satellite, forecast models and
analyses, airport and other station observations, weather balloons,
warnings, and climate records. It's the source research for a proposed
`weather` plugin that would record the weather, replay it next to traffic,
buses and cameras, and draw real weather in 3D (the owner's idea,
[chapter 16 §16.5](../16-ideas-and-personas.md#165-weather-in-3d-the-owners-idea-oct-7)).
Two areas matter: the valley box around Ada and Canyon counties, and the
proposed regional ring around it ([DECISIONS](../DECISIONS.md), "How far
the study area reaches"). Sources for drawing weather in 3D are also in
[weather-3d.md](weather-3d.md). How the new plugins' sources fit together
is in [chapter 17](../17-sources-for-new-plugins.md); the ideas they serve
are in [chapter 16](../16-ideas-and-personas.md).

**Status: research only. Nothing here is approved.** Each source goes to
the owner one at a time before we commit to how it's used. A researcher
catalogued 30 sources; a verifier then re-checked each one against its
official pages, its robots.txt and its terms on Oct 7, 2026, with our
honest User-Agent. Of the 30, 14 were confirmed as written and 16
corrected; one correction (IGRA) overturned the researcher's verdict. None was refuted
outright, but some figures inside entries couldn't be re-checked: those
are labelled as the researcher's, and anything resting on secondary or
unverified sources carries ⚠️. The checks made only small requests: S3
listings, a few model index files (KB each), one METAR sample, AgriMet's
station list, and five IEM pages 125 s apart. No dataset was downloaded
and nothing was sent to api.weather.gov.

License and terms below paraphrase each publisher (apart from one short
quote of NOAA's NODD wording); the evidence links hold the exact wording.

## Summary

Verdicts: 21 use, 1 internal only, 5 need an owner action, 3 avoid. "None"
under key/account means anonymous access. "NODD" is NOAA Open Data
Dissemination, the program that hosts NOAA data on AWS: open to any use,
credit requested for unaltered data, no implied endorsement, and modified
data mustn't be passed off as NOAA's.

| Source | Publisher | What it gives | Access | Key/account | License or terms | robots.txt (Oct 7) | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| [NEXRAD Level II, KCBX](https://registry.opendata.aws/noaa-nexrad/) | NOAA NWS; NSF Unidata on AWS | Full Boise radar volumes, dual-pol; live chunks | S3 `unidata-nexrad-level2`, `-chunks` | None (SNS push needs an AWS account) | NODD; credit NOAA/NWS and Unidata | 404 (no rules) | Use | Corrected |
| [NEXRAD Level III, KCBX](https://registry.opendata.aws/noaa-nexrad/) | NOAA NWS; NSF Unidata on AWS | About 100 radar products (reflectivity, hydrometeor class, storm tracks, wind profile), from Mar 2022 | S3 `unidata-nexrad-level3` | None | NODD | 404 | Use | Confirmed |
| [MRMS](https://registry.opendata.aws/noaa-mrms-pds/) | NOAA NSSL / NCEP | 2-min radar mosaics: 3D reflectivity, precipitation type and rate, rainfall, hail, lightning odds | S3 `noaa-mrms-pds`; live at `mrms.ncep.noaa.gov` | None | NODD; NLDN grids ⚠️ | 404; NCEP 301 then 404 | Use | Corrected |
| [GOES-18 ABI (GOES-19 second)](https://registry.opendata.aws/noaa-goes/) | NOAA NESDIS | Satellite imagery every 5 min; cloud mask and heights, fire, smoke, surface temperature | S3 `noaa-goes18`, `noaa-goes19` | None | NODD | 404 | Use | Corrected |
| [GOES-18 GLM](https://registry.opendata.aws/noaa-goes/) | NOAA NESDIS | Total lightning flashes, 20-s files | S3 `noaa-goes18` | None | NODD | 404 | Use | Confirmed |
| [NOAA STAR GOES sector imagery](https://www.star.nesdis.noaa.gov/GOES/sector.php?sat=G18&sector=pnw) | NOAA NESDIS STAR | Ready-made Pacific Northwest images and loops | Web pages, CDN | None | No terms found | CDN 404; `/GOES/` allowed | Internal only | Confirmed |
| [Blitzortung.org](https://www.blitzortung.org/en/cover_your_area.php) | Volunteer network | Lightning strokes from volunteer receivers | Raw data only for station operators | Station operator | Non-commercial, operators only | Only `/Languages/` disallowed; no open feed | Owner action | Corrected |
| [HRRR](https://registry.opendata.aws/noaa-hrrr-pds/) | NOAA NCEP / GSL; Univ. of Utah Zarr copy | 3 km hourly model: 3D clouds, visibility, smoke, winds | S3 `noaa-hrrr-bdp-pds` (Range via `.idx`); `hrrrzarr` | None | NODD; Zarr copy: no license found ⚠️ | 404 | Use | Corrected |
| [NOMADS grib filter](https://nomads.ncep.noaa.gov/) | NOAA NCEP Central Operations | Server-side ring subsets of HRRR 2D, RTMA, NBM, RAP | HTTPS CGI; 120 hits/min per IP | None | US Government, public; no license page | 404 | Use | Corrected |
| [RAP](https://registry.opendata.aws/noaa-rap/) | NOAA NCEP / GSL | 13 km hourly model, to 51 h at four cycles | S3 `noaa-rap-pds`; NOMADS | None | NODD | 404 | Use | Corrected |
| [RRFS v1 and REFS](https://www.weather.gov/media/notification/pdf_2026/scn26-048_Updated_RRFS_and_REFS_Implementation_aae.pdf) | NOAA NWS NCEP | New 3 km model and ensemble; 1.5 km fire-weather run; production from Nov 3, 2026 | NOMADS HTTPS (no filter); S3 `noaa-rrfs-pds`, `noaa-rrfs-ops` | None | US Government; registry says CC0 | NOMADS 404 | Use | Corrected |
| [NBM v5.0](https://registry.opendata.aws/noaa-nbm/) | NOAA NWS MDL | 2.5 km blended forecast, 589 elements (frost, heat stress, mixing height, fog) | S3 COGs `noaa-nbm-pds`; GRIB2 | None | NODD | 404 | Use | Confirmed |
| [RTMA, URMA, RTMA-RU](https://registry.opendata.aws/noaa-rtma/) | NOAA NCEP / EMC | 2.5 km surface analyses; visibility, ceiling, gusts every 15 min | S3; NOMADS filters | None | NODD | 404 | Use | Confirmed |
| [NDFD](https://registry.opendata.aws/noaa-ndfd/) | NOAA NWS / MDL | Official NWS forecast grids, with history | S3 `noaa-ndfd-pds` | None | NODD | 404 | Use | Confirmed |
| [Open-Meteo](https://api.open-meteo.com/robots.txt) | Open-Meteo | Repackaged model forecasts | JSON API | None | Not reviewed | `Disallow: /` (whole host) | Avoid | Confirmed |
| [NWS API](https://www.weather.gov/documentation/services-web-api) | NOAA NWS | Forecasts, gridpoints, observations, alerts | HTTPS JSON; User-Agent required | None (keys planned) | Open, free for any purpose | `Disallow: /` (whole host) | Owner action | Corrected |
| [Iowa Environmental Mesonet (IEM)](https://mesonet.agron.iastate.edu/request/download.phtml) | Iowa State University | Airport weather history (BOI from 1929; 1-minute at BOI), warnings, storm reports, NWS text | CGI and JSON | None | Public domain; credit appreciated | Crawl-delay 120; our paths allowed | Use | Corrected |
| [Boise soundings (IEM RAOB)](https://mesonet.agron.iastate.edu/archive/raob/) | NWS Boise; IEM archive | Twice-daily balloon profiles since 1948 | CSV CGI | None | Public domain (IEM) | Crawl-delay 120; allowed | Use | Confirmed |
| [IGRA v2](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive) | NOAA NCEI | Sounding archive (backup) | HTTPS `/pub/data/igra/` | None | NOAA public; no license stated | `/data*` disallowed, `/pub/` allowed | Use (optional backup) | Corrected |
| [SPC and Univ. of Wyoming pages](https://weather.uwyo.edu/robots.txt) | NOAA SPC; Univ. of Wyoming | Sounding plots, mesoanalysis | Web pages | None | SPC public; Wyoming not stated | SPC `Disallow: /`; Wyoming `/cgi-bin`, `/wsgi` | Avoid | Confirmed |
| [Aviation Weather Center Data API](https://aviationweather.gov/data/api/) | NOAA NWS AWC | METAR, TAF, PIREP, SIGMET; last 30 days | HTTPS JSON; 100 requests/min | None (custom User-Agent) | US Government; no statement ⚠️ | 404 | Use | Confirmed |
| [RAWS via FEMS](https://www-wfweb.fs2c.usda.gov/page/access) | USDA Forest Service and partners; WRCC (DRI) | Backcountry hourly weather, fuel moisture, fire danger | FEMS web UI | Login.gov for history | Federal; no license text | Allowed; WRCC archive Crawl-delay 5 | Owner action | Confirmed |
| [Synoptic Data API](https://synopticdata.com/pricing/open-access-pricing/) | Synoptic Data PBC | Aggregated station networks | REST with token | Token; free only for .edu | Credit and share results ⚠️ | 401 (no rules) | Avoid | Corrected |
| [MADIS](https://madis.ncep.noaa.gov/madis_datasets.shtml) | NOAA NWS / NCEP | Integrated observations; mesonets restricted | netCDF; text/XML viewer | Application for restricted sets | Restricted sets: no redistribution without notifying NOAA | 404 | Owner action | Corrected |
| [USBR AgriMet](https://www.usbr.gov/pn/agrimet/) | Bureau of Reclamation, PN Region | Farm weather, evapotranspiration, soil temperature; 6 stations | Form pages over CGI; RISE API | None | Federal; no license text | `/pn-bin` and `/rise/api` disallowed | Owner action | Corrected |
| [CoCoRaHS](https://www.cocorahs.org/Content.aspx?page=datausagepolicy) | CoCoRaHS (Colorado State) | Volunteer daily rain, snow and hail | Export form | None | Data CC BY 3.0; site CC BY 4.0 | `/admin/`, `/viewdata/` disallowed; data host 404 | Use | Confirmed |
| [PRISM](https://prism.oregonstate.edu/terms/) | PRISM Group, Oregon State | Daily, monthly and normal climate grids at 800 m | HTTPS, FTP, web service | None | Free to reproduce; cite with access date | 404 | Use | Corrected |
| [U.S. Climate Normals 1991–2020](https://registry.opendata.aws/noaa-climate-normals/) | NOAA NCEI | Station normals, including hourly | S3 `noaa-normals-pds` | None | NODD | S3 404; NCEI `/data*` disallowed | Use | Confirmed |
| [GHCN-Daily](https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation) | NOAA NCEI | Daily station records over decades | NCEI `/pub/` per station; data service; S3 (stale) | None | NOAA public | `/pub/` and `/access/services/` allowed | Use | Corrected |
| [NCEI Storm Events](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/) | NOAA NCEI | Storm events 1950–2026 | Yearly gzip CSVs | None | NOAA public | `/pub/` allowed | Use | Confirmed |

Effort below is the researcher's rough size: S, M or L. The core pieces
named under "Needs" are those of [chapter 15](../15-plugins.md) (§15.1),
plus a proposed fourth time shape, **fields**, for gridded frames over
time ([design notes](#a-fourth-time-shape-fields)).

## Radar

### NEXRAD Level II: Boise radar KCBX

NOAA NWS Radar Operations Center; distributed by NSF Unidata through NODD
on AWS.

- **Contents:** full volume scans: every elevation sweep of reflectivity,
  radial velocity, spectrum width and the dual-pol fields (differential
  reflectivity ZDR, correlation coefficient CC, differential phase and
  KDP). Low tilts are super-resolution (0.5° × 250 m gates). Files since
  about 2008 are Archive II Message 31 with bzip2-compressed records; older
  KCBX volumes use the legacy Message 1 format, and some older archive
  files are gzip-compressed, so a backfill reader needs both.
- **Coverage:** KCBX is inside the valley box, south of the Boise airport
  (about 43.49 N, −116.24 W ⚠️ not re-verified); its range covers the
  whole ring. Beam blockage toward the foothills comes from a local TV
  weather blog ⚠️. Archive back to the 1990s ⚠️.
- **Endpoint:** anonymous HTTPS/S3, no account.
  - Archive: `s3://unidata-nexrad-level2/YYYY/MM/DD/KCBX/KCBXYYYYMMDD_HHMMSS_V06`
    (plus `_MDM` files).
  - Real time: `s3://unidata-nexrad-level2-chunks/KCBX/<volume number, cycling 0–999>/YYYYMMDD-HHMMSS-NNN-{S|I|E}`.
  - Poll ListObjectsV2 over HTTPS, or subscribe to SNS
    `arn:aws:sns:us-east-1:684042711724:NewNEXRADLevel2ObjectFilterable`
    (real time) or `...:NewNEXRADLevel2Archive` (archive); SNS needs an
    AWS account, an owner action.
  - The legacy `noaa-nexrad-level2` bucket stopped updating Sept 1, 2025.
- **Updates:** continuous: chunks every 6–12 s within a volume, volumes
  every 4–7 min. Clear-air volumes come about every 7 min (Oct 5 had 202,
  one every 7.1 min); precipitation scan strategies are faster, about
  4–6 min ⚠️. Timings are the researcher's, from key times against
  LastModified, not repeated.
- **Size** (researcher, Oct 5, a quiet day, not repeated ⚠️): 202 volumes,
  1.22 GB (0.6–8.7 MB each), plus 24 MDM files (15 MB); wet days an
  estimated 2–3 GB ⚠️. One real-time volume: 55 chunks, 4.1 MB. Raw
  volumes come to 1.2–3 GB a day, 0.45–1 TB a year.
- **Uses:** super-resolution sweeps as translucent cones on the 3D terrain;
  dual-pol rain, snow, hail and melting-layer detection over the valley;
  precipitation cores and virga in the 3D weather volume; nocturnal bird
  and insect migration over Boise (biological echoes have low CC); storm
  replay synced with traffic, buses and cameras; live radar about 15 s
  behind, but only if the chunk prefix is polled every 5–10 s.
- **Personas:** weather enthusiast, traffic researcher, wildlife watcher,
  fire and hazards watcher, commuter.
- **Needs:** fields (polar frames over time, with valid start and end), the
  3D engine's volume and sweep pass, full replay, the time bar, areas.
  Effort L.
- **Risks:** bucket names changed in 2025, so keep them in config. Prefer
  derived products and re-fetch raw volumes from AWS. Message 31 parses
  with `bz2` and `struct`, and numpy makes it practical; Message 1 and
  `.gz` files need a second code path for backfills before about 2008.
  Maintenance outages. Biological echoes must be filtered out before any
  precipitation use. Free hosting depends on NOAA's NODD agreements ⚠️.
- **License:** NODD terms: the data are "open to the public and can be used
  as desired". Credit is requested for unaltered data, there's no implied
  endorsement, and modified data mustn't be passed off as original NOAA
  data. Credit NOAA/NWS and NSF Unidata.
- **robots.txt:** re-fetched Oct 7: `unidata-nexrad-level2` and
  `unidata-nexrad-level2-chunks` both return 404 NoSuchKey (no rules).
- **Verified: corrected** (confidence high). The registry confirms three
  us-east-1 buckets (level2, level2-chunks, level3), both Level II SNS
  topics, the license and Unidata as manager. Unidata's notice confirms
  the rename, the end of legacy updates on Sept 1, 2025, and that the chunk
  and Level III buckets were unaffected. Corrected: chunk volume numbers
  cycle 0–999 (not 1–999), and Message 31 is only the modern format. Not
  re-checked: KCBX's coordinates and the researcher's listings and sizes
  (the arithmetic holds: 1,440 ÷ 202 = 7.1 min).
- **Evidence:** [registry](https://registry.opendata.aws/noaa-nexrad/),
  [Unidata's notice](https://www.unidata.ucar.edu/blogs/news/entry/important-changes-to-noaa-nexrad),
  [AWS open-data docs](https://github.com/awslabs/open-data-docs/tree/main/docs/noaa/noaa-nexrad),
  robots.txt for [level2](https://unidata-nexrad-level2.s3.amazonaws.com/robots.txt)
  and [chunks](https://unidata-nexrad-level2-chunks.s3.amazonaws.com/robots.txt),
  the researcher's [Oct 5 listing](https://unidata-nexrad-level2.s3.amazonaws.com/?list-type=2&prefix=2026/10/05/KCBX/)
  (not repeated), and a [KMVT blog post on the radar hole](https://www.kmvt.com/2022/02/06/weekend-weather-blog-southern-idaho-radar-hole/)
  ⚠️ (search result only).

### NEXRAD Level III products: KCBX

NOAA NWS (the radar product generator); distributed by NSF Unidata through
NODD on AWS.

- **Contents:** about 100 product codes for CBX (the researcher's Oct 2026
  listing), including N0B super-resolution base reflectivity, N0G
  velocity, N0C/N0X/N0K (CC, ZDR, KDP), N0H/HHC hydrometeor
  classification, DPR instantaneous precipitation rate, the accumulations
  DAA, DTA, DSD, DOD, DU3, DU6, OHA and PTA, EET echo tops, DVL digital
  VIL, NML melting layer, NVW VAD wind profile, NST storm tracking, NMD
  mesocyclones, NSS storm structure, NHI hail index, plus upper tilts.
- **Coverage:** the same radar as Level II. CBX N0B in the bucket starts
  2022-03-02 16:30:01 UTC (confirmed), so Level III replay reaches back
  only to March 2022; earlier days need Level II.
- **Endpoint:** `s3://unidata-nexrad-level3/CBX_<PRODUCT>_YYYY_MM_DD_HH_MM_SS`
  (flat keys, one object per volume per product; confirmed). SNS
  `arn:aws:sns:us-east-1:684042711724:NewNEXRADLevel3Object` needs an AWS
  account; polling works without.
- **Updates:** one file per product per volume (about 4–7 min).
- **Size:** N0B on Oct 5: 202 files, 34 MB (researcher); the first 2022
  files were 92 KB each (checked). Eight products together, an estimated
  0.2–0.4 GB a day.
- **Uses:** a cheap live radar layer (N0B) without decoding Level II;
  storm-cell tracks (NST) drawn through the tracks contract, like buses;
  hydrometeor class and melting-layer height for precipitation type over
  roads; echo tops and VIL for the 3D view; the VAD wind profile above
  Boise every volume (inversions and wind shear).
- **Personas:** weather enthusiast, commuter, traffic researcher, cyclist,
  fire and hazards watcher.
- **Needs:** fields, tracks, full replay, lifecycles (storm-cell events).
  Effort M.
- **Risks:** several packet types (8-bit and 16-bit radial and raster,
  symbology, some bzip2-compressed), so parsing is moderate work. Not every
  product exists for every volume. The archive starts in 2022 in this
  bucket. The same NODD continuity caveat as Level II.
- **License:** NODD, as for Level II.
- **robots.txt:** `unidata-nexrad-level3` returns 404 NoSuchKey
  (re-fetched Oct 7).
- **Verified: confirmed** (high). The key format and the March 2, 2022
  start were re-confirmed with one listing; the SNS topic and license on
  the registry; robots.txt re-fetched. The product-code list wasn't
  re-listed.
- **Evidence:** [first CBX N0B keys](https://unidata-nexrad-level3.s3.amazonaws.com/?list-type=2&prefix=CBX_N0B_&max-keys=2)
  (Oct 7: 2022-03-02, 92 KB),
  [robots.txt](https://unidata-nexrad-level3.s3.amazonaws.com/robots.txt),
  [registry](https://registry.opendata.aws/noaa-nexrad/),
  [Unidata's notice](https://www.unidata.ucar.edu/blogs/news/entry/important-changes-to-noaa-nexrad),
  the researcher's [product list](https://unidata-nexrad-level3.s3.amazonaws.com/?list-type=2&prefix=CBX_&delimiter=_2)
  (not repeated).

### MRMS (Multi-Radar Multi-Sensor) mosaics and rainfall

NOAA NSSL and NCEP; NODD on AWS.

- **Contents:** 244 CONUS product prefixes (listed Oct 7), including:
  - MergedReflectivityQC at 33 heights from 0.5 to 19 km above sea level
    (0.25 km apart to 3 km, 0.5 km to 9 km, 1 km above: 11 + 12 + 10 =
    33); 3D MergedRhoHV and MergedZdr at the same heights;
  - PrecipFlag, PrecipRate, SyntheticPrecipRateID, SeamlessHSR and
    SeamlessHSRHeight;
  - RadarOnly and MultiSensor rainfall (QPE, Pass1 and Pass2);
  - EchoTop 18/30/50/60, VIL, VIL_Density and VIL maxima, MESH hail size
    and its maxima (30 to 1,440 min);
  - BrightBand top and bottom heights, Model_0degC_Height,
    Model_WetBulbTemp;
  - LightningProbabilityNext30/60min, and
    `NLDN_CG_{001,005,015,030}min_AvgDensity`: gridded average
    cloud-to-ground flash density, not strike locations.
- **Coverage:** CONUS; the ring is 170 × 140 cells at 0.01°. Blends KCBX
  with neighbouring radars. The AWS archive starts 2020-10-14
  (researcher's listing, not repeated).
- **Endpoint:** `s3://noaa-mrms-pds/CONUS/<Product>_<level>/<YYYYMMDD>/MRMS_<Product>_<level>_<YYYYMMDD-HHMMSS>.grib2.gz`;
  SNS `arn:aws:sns:us-east-1:123901341784:NewMRMSObject` (an AWS account to
  subscribe). NCEP's live copy is at `https://mrms.ncep.noaa.gov/`, in
  folders `2D/`, `3DRefl/`, `3DRhoHV/`, `3DZdr/`, `ProbSevere/` and
  `RIDGEII/` (the old `/data/` path redirects to the root). Gzipped GRIB2
  allows no byte-range subsetting: each CONUS file is fetched whole.
- **Updates:** every 2 min for the radar mosaics (registry); hourly
  gauge-corrected rainfall (Pass1 about 1 h later, Pass2 about 2 h ⚠️).
- **Size** (researcher, not repeated ⚠️): MergedReflectivityQC_03.00 about
  1.1 MB per 2-min file; PrecipFlag 0.2 MB; MultiSensor_QPE_01H_Pass2
  0.8 MB an hour. Ring crops: a 2D field is 48 KB raw a frame (34 MB a
  day raw per field at the 2-min cadence, before compression); the 3D cube
  about 0.8 MB raw a frame. Full 3D CONUS every 2 min is about 36 MB
  (26 GB a day).
- **Uses:** a 3D precipitation volume every 2 min (rain shafts, snow, virga
  aloft); precipitation type and rate on every road segment;
  gauge-adjusted rainfall for yards and fields (MultiSensor QPE); hail
  swaths on fields and roofs (MESH maxima); snow level and melting layer
  from the bright-band heights; lightning odds for hikers (densities only,
  no individual strikes).
- **Personas:** traffic researcher, commuter, weather enthusiast, gardener,
  farmer, hiker and camper, cyclist.
- **Needs:** fields, the 3D volume pass, full replay, areas. Effort M.
- **Risks:** heights are above sea level and the valley floor is at about
  0.75–0.85 km, so the 0.50 and 0.75 km levels are underground. Gate the
  full 3D downloads on precipitation in the ring. GRIB2 needs GDAL,
  eccodes or wgrib2. PrecipFlag has no freezing-rain class ⚠️; pair it
  with HRRR and 511's pavement status. The NLDN products are densities on
  a grid and can't place individual ground strikes.
- **License:** NODD. The NLDN density grids derive from Vaisala's network
  ⚠️: confirm there's no extra restriction before republishing them.
- **robots.txt:** re-fetched Oct 7: `noaa-mrms-pds` 404 NoSuchKey;
  `mrms.ncep.noaa.gov/robots.txt` redirects (301) to `/robots.txt/`, which
  is 404. No rules.
- **Verified: corrected** (high). The registry confirms bucket, region, SNS
  topic and license. The product list was re-listed: the entry's names
  exist (NLDN products are AvgDensity grids; 3D RhoHV and Zdr have 33
  levels). Corrected: NCEP's live copy is at the site root, not `/data/`,
  and the prefix count is 244. Archive start and file sizes not re-checked.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-mrms-pds/),
  [Oct 7 prefix listing](https://noaa-mrms-pds.s3.amazonaws.com/?list-type=2&prefix=CONUS/&delimiter=/)
  (244 prefixes, not truncated), robots.txt for
  [S3](https://noaa-mrms-pds.s3.amazonaws.com/robots.txt) and
  [NCEP](https://mrms.ncep.noaa.gov/robots.txt), the
  [`/data/` redirect](https://mrms.ncep.noaa.gov/data/), and an
  [EOL dataset page](https://data.eol.ucar.edu/dataset/570.058) for the
  vertical spacing ⚠️ (search result).

## Satellite and lightning

### GOES-18 ABI (GOES-West), with GOES-19 (East) as a second view

NOAA NESDIS; NODD on AWS.

- **Contents:**
  - Per-band imagery (L1b RadC/F/M and L2 CMIP, 16 bands: band 2 at
    0.5 km, bands 1, 3 and 5 at 1 km, infrared at 2 km nominal, coarser at
    our viewing angle) and MCMIP.
  - L2 products confirmed in the bucket: ACM, ACHA and ACHA2KM, ACHP2KM,
    ACHT, ACTP, ADP, AOD, BRF, CCL, CMIP, COD (CODC; COD2KMF full disk),
    CPS, CTP, DMW/DMWV, DSI, FDC, FSC, LSA, LST, LVMP/LVTP, MCMIP, RSR,
    TPW; RRQPE and SST full disk only; PAR full disk; new ABI-Flood
    products.
  - Downward solar radiation (DSR): the CONUS product (ABI-L2-DSRC) has
    year folders only for 2022–2024; 2026 data exist only as full disk
    (ABI-L2-DSRF). Land-surface temperature (LST) for CONUS is hourly.
  - No fog/low-stratus (IFR probability) folder exists (confirmed by
    listing), so fog detection would be ours to build.
- **Coverage:** GOES-18's CONUS sector is PACUS (the western US and the
  northeast Pacific), every 5 min; full disk every 10 min; 1-min mesoscale
  sectors only where placed. GOES-19 has been the operational GOES-East
  since April 4, 2025 (registry); GOES-16 distribution ended after that
  transition, and GOES-17 went into storage in January 2023. Viewing
  geometry at Boise (computed): GOES-West's satellite zenith is about
  54–55° (parallax about 1.4 × the cloud height), GOES-East's about 65°
  (about 2.1 ×).
- **Endpoint:** `s3://noaa-goes18/<product>/<YYYY>/<DOY>/<HH>/OR_<product>-M6..._G18_s<start>_e<end>_c<created>.nc`
  (NetCDF4/HDF5); SNS `arn:aws:sns:us-east-1:123901341784:NewGOES18Object`
  (an AWS account to subscribe). The same layout is in `noaa-goes19`
  (NewGOES19Object).
- **Updates:** every 5 min for PACUS imagery and most L2 products (ACM,
  ACHA, FDC, ADP); LST hourly; DSR full disk only (cadence ⚠️); RRQPE full
  disk every 10 min.
- **Size** (researcher, Oct 5 at 18 UTC, not repeated ⚠️): CMIP band 2
  66 MB, band 13 3.6 MB, MCMIP 54 MB, ACM 3.8 MB, ACHA 0.32 MB; LSTC
  1.4 MB per hourly file (checked). The suggested set: an estimated
  4–8 GB a day downloaded (less with ranged chunk reads) and 20–40 MB a day
  stored after cropping (band 2 at 0.5 km over the ring is about 170 KB a
  frame).
- **Uses:** valley fog and low stratus at night (the 10.3 minus 3.9 µm
  difference) and by day (visible), every 5 min; a clear-sky mask and
  cloud-top heights to correct the model's 3D clouds; cloud shadows on the
  3D map, and sunshine for gardens from DSR (hourly, full disk only); fire
  hot spots (FDC) and smoke (ADP); frost pockets and urban heat from
  land-surface temperature (hourly); snow cover in the foothills (FSC).
- **Personas:** weather enthusiast, sky watcher, traffic researcher,
  gardener, farmer, fire and hazards watcher.
- **Needs:** fields, the 3D engine (the cloud mask and tops feed the
  volume), full replay, areas. Effort M.
- **Risks:** band 2 is 66 MB per 5-min PACUS file. The NetCDF4 files are
  HDF5-chunked, so an HDF5-aware ranged reader (h5py with fsspec, or GDAL
  over `/vsis3/`) may fetch only the chunks over the ring ⚠️ (chunk layout
  not checked). Reading needs GDAL's netCDF/HDF5 drivers or h5py. Parallax
  displaces cloud tops by about 1.4 × their height from GOES-West; correct
  it with ACHA. DSR for CONUS stopped after 2024: use DSRF and check its
  cadence. The fog product is ours to build and validate. Replays before
  2023 need GOES-17 (the `noaa-goes17` archive ⚠️).
- **License:** NODD; credit NOAA/NESDIS.
- **robots.txt:** `noaa-goes18` and `noaa-goes19` both 404 NoSuchKey
  (re-fetched Oct 7).
- **Verified: corrected** (high). The registry confirms buckets, SNS
  topics, license, GOES-19's operational date and GOES-16/17 status. One
  product listing plus three small ones corrected DSR (no CONUS files
  after 2024; full disk continues), the LST cadence (hourly) and RRQPE
  (full disk only), and confirmed there's no fog product in the bucket.
  ACHA2KM's start (March 2023) and the PACUS details remain secondary ⚠️.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-goes/),
  [Oct 7 product list](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/),
  [one hourly LST file](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-LSTC/2026/278/18/),
  [DSRC years](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-DSRC/&delimiter=/)
  (2022–2024 only), [DSRF 2026](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-DSRF/2026/&delimiter=/),
  robots.txt for [GOES-18](https://noaa-goes18.s3.amazonaws.com/robots.txt)
  and [GOES-19](https://noaa-goes19.s3.amazonaws.com/robots.txt), and a
  [CIMSS blog post](https://cimss.ssec.wisc.edu/satellite-blog/archives/49676)
  on how the IFR-probability product is distributed ⚠️ (researcher).

### GOES-18 GLM lightning (Geostationary Lightning Mapper)

NOAA NESDIS; NODD on AWS.

- **Contents:** GLM-L2-LCFA: optical lightning events, groups and flashes
  (time, latitude and longitude, energy, area, quality). Total lightning:
  in-cloud and cloud-to-ground aren't separated. Pixels about 8 km at
  nadir, larger here ⚠️.
- **Coverage:** GOES-West's field of view, so the valley and the ring.
- **Endpoint:** `s3://noaa-goes18/GLM-L2-LCFA/<YYYY>/<DOY>/<HH>/OR_GLM-L2-LCFA_G18_s..._e..._c....nc`
  (NetCDF4), one file per 20 s; SNS NewGOES18Object.
- **Updates:** 20-s files, available within about 20 s of the window's end
  (researcher, from file names).
- **Size** (researcher ⚠️): about 0.17 MB per 20-s file, so 4,320 files and
  about 0.7 GB a day downloaded; the flashes stored for the ring are KB on
  most days.
- **Uses:** flashes lighting up the 3D clouds in replay; dry lightning
  (flashes where MRMS shows no rain) for fire starts; thunderstorm alerts
  for hikers and cyclists; lightning history per area (km-scale, not per
  trail or campsite).
- **Personas:** weather enthusiast, fire and hazards watcher, hiker and
  camper, cyclist.
- **Needs:** readings or lifecycles (point events), full replay, the 3D
  engine (flash pulses). Effort S.
- **Risks:** 0.7 GB a day to find a handful of flashes: gate the download
  on MRMS lightning odds or HRRR's LTNG, or accept the bandwidth in summer.
  Locations are good to several km, so never snap a flash to a house or a
  trail. GLM doesn't separate ground strikes.
- **License:** NODD.
- **robots.txt:** `noaa-goes18` 404 NoSuchKey (re-fetched Oct 7).
- **Verified: confirmed** (high). The product folder is in the Oct 7
  listing; license, SNS and robots.txt confirmed. File size and latency
  are the researcher's figures, not repeated, but match the documented
  20-s product.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-goes/),
  [Oct 7 product list](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/)
  (GLM-L2-LCFA present), [robots.txt](https://noaa-goes18.s3.amazonaws.com/robots.txt),
  the researcher's [sample listing](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=GLM-L2-LCFA/2026/278/18/&max-keys=2)
  (not repeated).

### NOAA STAR GOES sector imagery

NOAA NESDIS Center for Satellite Applications and Research. Verdict:
**internal only**.

- **Contents:** ready-made images and loops for a Pacific Northwest
  sector: GeoColor, Air Mass, Sandwich, Day-Night Cloud Micro Combo, Dust
  and Fire Temperature RGBs, and all 16 bands.
- **Coverage:** the Pacific Northwest sector, including southwest Idaho.
- **Endpoint:** web pages, with images from `cdn.star.nesdis.noaa.gov`
  (exact paths not read).
- **Updates:** every 5–10 min ⚠️. **Size:** hundreds of KB an image ⚠️.
- **Uses:** a quick-look "satellite now" image for the owner until our own
  GOES pipeline exists; a visual check of our own fog and cloud composites.
- **Personas:** weather enthusiast, sky watcher.
- **Needs:** the layer system. Effort S.
- **Risks:** terms unclear for republishing; the images are pixels, not
  data, and aren't aligned to our grid. Prefer composites built from the
  AWS data.
- **License:** no usage or credit statement on the sector page; GeoColor is
  a CIRA algorithm (terms unconfirmed).
- **robots.txt:** `cdn.star.nesdis.noaa.gov` 404 (no rules);
  `www.star.nesdis.noaa.gov` disallows `/cgi-bin/`, `/thredds/`, `/tst/`,
  `/intranet/` and many staff paths, but not `/GOES/`.
- **Verified: confirmed** (low). The sector page and both robots files
  match the catalog; no terms were found, as the catalog said.
- **Evidence:** [sector page](https://www.star.nesdis.noaa.gov/GOES/sector.php?sat=G18&sector=pnw),
  robots.txt for the [CDN](https://cdn.star.nesdis.noaa.gov/robots.txt)
  and [www](https://www.star.nesdis.noaa.gov/robots.txt).

### Blitzortung.org community lightning network

A volunteer network. Verdict: **needs an owner action**.

- **Contents:** lightning stroke locations from volunteer VLF receivers;
  public real-time maps.
- **Coverage:** depends on receivers near Idaho (unchecked).
- **Endpoint:** raw positions go only to people who run a station and send
  data; the public maps aren't a data feed.
- **Updates:** seconds. **Size:** small.
- **Uses:** a lightning receiver run by the owner for the private `home`
  plugin, adding strokes beside GLM.
- **Personas:** weather enthusiast, fire and hazards watcher.
- **Needs:** readings or lifecycles (point events), private plugins.
  Effort M.
- **Risks:** needs a receiver the owner would run and agreement to
  Blitzortung's terms. Not needed for lightning as such: GLM is open.
- **License:** station operators may use the raw data for any
  non-commercial purpose; redistribution to third parties isn't
  addressed.
- **robots.txt:** `www.blitzortung.org/robots.txt` disallows only
  `/Languages/` for all agents (and everything for several named SEO
  bots). No data endpoints are open to non-operators, and scraping the map
  would sidestep the participation terms.
- **Verified: corrected** (medium). Participation terms confirmed;
  robots.txt, "not checked" in the catalog, is now checked and recorded.
- **Evidence:** [cover your area](https://www.blitzortung.org/en/cover_your_area.php),
  [robots.txt](https://www.blitzortung.org/robots.txt).

## Models and analyses

### HRRR (High-Resolution Rapid Refresh), including HRRR-Smoke

NOAA NCEP and GSL; NODD on AWS; also the University of Utah's HRRR-Zarr
copy.

- **Contents:** a 3 km CONUS model (1799 × 1059), run hourly to 18 h, and
  to 48 h at 00, 06, 12 and 18 UTC. Files each hour:
  - `wrfsfc` (2D): visibility, ceiling, cloud base and top, cloud layers,
    precipitation rate (PRATE), precipitation type, composite reflectivity
    (REFC), lightning (LTNG), gusts, downward solar radiation (DSWRF),
    smoke (MASSDEN) at 8 m, column smoke (COLMD), AOTK, boundary-layer
    height (HPBL), 0 °C height, snow depth;
  - `wrfnat` (50 hybrid levels): cloud water (CLMR), cloud ice (CIMIXR),
    rain (RWMR), snow (SNMR), graupel (GRLE), cloud fraction (FRACCC), 3D
    MASSDEN, TMP, SPFH, U/V, VVEL, TKE, HGT, PRES;
  - `wrfprs` (708 messages at 12Z Oct 5, f00): 40 isobaric levels with
    CLMR, CIMIXR, RWMR, SNMR, GRLE, TMP, SPFH, RH, DPT, U/V, VVEL, ABSV
    and HGT, but no FRACCC and no 3D MASSDEN; smoke only at 8 m;
  - `wrfsubh`: 15-min 2D output to 18 h.
- **Coverage:** CONUS; the ring is about 46 × 52 columns, the valley box
  about 30 × 31. Archive since 2014 (registry).
- **Endpoint:** `s3://noaa-hrrr-bdp-pds/hrrr.YYYYMMDD/conus/hrrr.tHHz.wrf{sfc,prs,nat,subh}fFF.grib2`,
  with a `.idx` per file for fetching single fields by HTTP Range; SNS
  `arn:aws:sns:us-east-1:123901341784:NewHRRRObject`. HRRR-Zarr,
  `s3://hrrrzarr` (us-west-1), has only `grid/`, `prs/` and `sfc/` groups
  (no native levels). The 12Z Oct 5, 2026 analysis is there, with
  isobaric levels 25 hPa apart (50–1000 hPa, plus 1013.2) and named
  levels (`cloud_base`, `cloud_top`, `0C_isotherm`, `8m_above_ground` and
  others), in 150 × 150 chunks, so the ring needs one to four chunks a
  field.
- **Updates:** hourly runs; f00 usually about an hour after the cycle ⚠️.
- **Size:** the researcher measured 12Z Oct 5 f00: `wrfnat` 680 MB,
  `wrfprs` 391 MB, `wrfsfc` 139 MB, `wrfsubh` 47 MB. The verifier, from the
  `wrfprs` index: isobaric fields total 254 MB; the cloud set plus HGT is
  about 38 MB an hour (about 0.9 GB a day), or about 110 MB an hour with
  TMP and winds. Stored after cropping: 50–150 MB a day.
- **Uses:** the cloud skeleton for 3D weather (hydrometeors on 40 pressure
  levels from `wrfprs` or Zarr, or 50 hybrid levels from `wrfnat`),
  nudged by GOES and METARs; fog and visibility forecasts for the morning
  commute (visibility, ceiling, 15-min output); smoke in 3D (MASSDEN on
  native levels, `wrfnat` only) and near-surface smoke for cyclists; wind
  fields for headwind maps and for moving precipitation particles;
  precipitation type at the ground (CRAIN, CSNOW, CFRZR, CICEP); "what
  was forecast against what happened" replay for any past day.
- **Personas:** weather enthusiast, commuter, cyclist, traffic researcher,
  fire and hazards watcher, sky watcher, hiker and camper.
- **Needs:** fields, with an issue time for forecasts; the 3D volume pass;
  full replay; areas. Effort L.
- **Risks:**
  - GRIB2 messages cover all of CONUS, so a Range fetch still pulls the
    whole field.
  - A 3D hour from `wrfnat` is 130–380 MB (researcher: HGT 113 MB, PRES
    122 MB). From `wrfprs` it's far less (from the index: CLMR 2.4,
    CIMIXR 1.4, RWMR 1.4, SNMR 2.5, GRLE 0.7 MB, 8.4 MB together, plus
    isobaric HGT 29.8, TMP 22.5 and U+V 48 MB), and HRRR-Zarr cuts it to a
    few chunks.
  - Isobaric levels below the ground (about 1013–925 hPa over the valley)
    must be masked with the surface pressure. FRACCC and 3D smoke exist
    only in `wrfnat`.
  - Decoding needs GDAL, eccodes or wgrib2 (Zarr needs a zarr/Blosc
    reader).
  - HRRR's replacement by RRFS v2 around 2027–28 is secondary ⚠️.
- **License:** NODD. HRRR-Zarr: no license text found on its documentation
  pages ⚠️; credit NOAA and the University of Utah.
- **robots.txt:** `noaa-hrrr-bdp-pds` and `hrrrzarr` both 404 NoSuchKey
  (re-fetched Oct 7). `mesowest.utah.edu` was read as documentation only.
- **Verified: corrected** (high). The registry confirms both buckets,
  regions, SNS, license and the 2014 start. Corrected: the HRRR-Zarr
  question is answered (`prs` and `sfc` only, no native levels, current
  to Oct 5, 2026), and `wrfprs` carries all five hydrometeors on 40
  isobaric levels at a fraction of `wrfnat`'s cost, though without FRACCC
  or 3D smoke. No Zarr license was found.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-hrrr-pds/),
  [`wrfprs` index, 12Z Oct 5](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20261005/conus/hrrr.t12z.wrfprsf00.grib2.idx)
  (field list and sizes), [Zarr groups](https://hrrrzarr.s3.us-west-1.amazonaws.com/?list-type=2&delimiter=/),
  [Zarr levels](https://hrrrzarr.s3.us-west-1.amazonaws.com/?list-type=2&prefix=prs/20261005/20261005_12z_anl.zarr/&delimiter=/),
  robots.txt for [AWS](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/robots.txt)
  and [Zarr](https://hrrrzarr.s3.amazonaws.com/robots.txt),
  [Utah's HRRR pages](https://mesowest.utah.edu/html/hrrr/) and
  [Zarr variables](https://mesowest.utah.edu/html/hrrr/zarr_documentation/html/zarr_variables.html).

### NOMADS grib filter (NCEP)

NOAA NWS NCEP Central Operations.

- **Contents:** recent model and analysis files (about two days ⚠️), each
  dataset with a grib-filter CGI that cuts variables, levels and a
  latitude/longitude box on the server. Filters listed Oct 7: HRRR
  (`hrrr_2d`, the `wrfsfc` file) and HRRR Sub Hourly (`hrrr_sub`), RAP
  (13 km, 32 km and two others), RTMA2.5 CONUS (`rtma2p5`), RTMA CONUS
  Rapid Updates (`rtma_ru`), National Blend (`blend`). URMA, RRFS and REFS
  are HTTPS-only, without a filter; RRFS and REFS are under
  `/pub/data/nccf/com/{rrfs,refs}/para`.
- **Coverage:** CONUS models; we'd ask for the ring's box only.
- **Endpoint:** HTTPS GET to `gribfilter.php?ds=<dataset>` (or the filter
  script) with file, variable, level and box (`leftlon`, `rightlon`,
  `toplat`, `bottomlat`). Usage policy (SCN 21-32, effective on or about
  April 20, 2021): 120 hits a minute per user IP, summed across
  `nomads.ncep.noaa.gov`, `ftp.ncep.noaa.gov` and `ftpprd.ncep.noaa.gov`.
- **Updates:** as runs complete: hourly for HRRR, RAP, NBM and RTMA; every
  15 min for RTMA-RU.
- **Size:** a ring subset of a few fields is KB to tens of KB a request;
  tens of MB a day at most.
- **Uses:** tiny live downloads of RTMA rapid-update visibility, ceiling
  and gusts every 15 min for the ring; HRRR 2D forecast hours (f01–f18)
  for commuter and cyclist cards without pulling 140 MB files; RRFS's
  1.5 km fire-weather run after Nov 3, 2026, but only as whole files or
  `.idx` Range requests until NCEP adds a filter.
- **Personas:** commuter, cyclist, traffic researcher, fire and hazards
  watcher.
- **Needs:** the ingest framework (polite HTTP, pacing), fields. Effort S.
- **Risks:** only about two days are kept, so backfills come from AWS. The
  120 hits a minute is per IP across NOMADS and NCEP's FTP hosts, so
  everything the server sends to them counts. No filter for HRRR's 3D
  files, URMA, RRFS or REFS.
- **License:** US Government data; NWS products are public (no license
  page found).
- **robots.txt:** `nomads.ncep.noaa.gov/robots.txt` 404 (re-fetched
  Oct 7). We'd need a few hits an hour, well under the limit.
- **Verified: corrected** (high). SCN 21-32 read (it doesn't spell out
  blocking). The front page was parsed: corrected the catalog's claim that
  the filter covers RRFS (RRFS and REFS have HTTPS links only); the HRRR
  filters are 2D and sub-hourly only, as the researcher suspected.
- **Evidence:** [NOMADS front page](https://nomads.ncep.noaa.gov/)
  (dataset table), [SCN 21-32](https://www.weather.gov/media/notification/pdf2/scn21-32nomad_changes.pdf),
  [robots.txt](https://nomads.ncep.noaa.gov/robots.txt), the
  [HRRR 2D filter](https://nomads.ncep.noaa.gov/gribfilter.php?ds=hrrr_2d)
  (researcher).

### RAP (Rapid Refresh), 13 km

NOAA NCEP and GSL; NODD on AWS.

- **Contents:** an hourly 13 km North America model with 50 vertical layers
  (WRF-ARW core; GSI analysis with cloud and hydrometeor assimilation):
  temperature, humidity and winds aloft, clouds, precipitation. Forecasts
  run to 51 h at 03, 09, 15 and 21 UTC and to 21 h at the other cycles.
- **Coverage:** North America: the ring and the far approaches for storms
  and smoke.
- **Endpoint:** `s3://noaa-rap-pds` (GRIB2 with `.idx`); SNS
  `arn:aws:sns:us-east-1:123901341784:NewRAPObject`; NOMADS grib filters
  (`rap`, `rap32` and regional variants) for live subsets.
- **Updates:** hourly. **Size:** not measured; a few upper-level fields an
  hour by Range are a few MB an hour.
- **Uses:** contrail forecasts at flight levels for the aircraft plugin
  (temperature and humidity at 200–300 hPa); regional context and the
  longest hourly-model reach; a fallback when HRRR is late.
- **Personas:** sky watcher, weather enthusiast.
- **Needs:** fields. Effort M.
- **Risks:** coarse for the valley itself; low priority behind HRRR. RRFS
  v2 replacing RAP around 2027–28 is secondary ⚠️ (SCN 26-48 says RRFS v1
  replaces NAM, HREF, SREF and HiresW, not RAP).
- **License:** NODD.
- **robots.txt:** `noaa-rap-pds` 404 NoSuchKey; NOMADS 404 (re-fetched
  Oct 7).
- **Verified: corrected** (high). The registry confirms bucket, SNS,
  license, 13 km and 50 layers. Corrected the vague "longer reach at some
  cycles" to 51 h at 03/09/15/21 UTC and 21 h otherwise; the bucket's
  robots.txt is now actually checked.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-rap/),
  [robots.txt](https://noaa-rap-pds.s3.amazonaws.com/robots.txt),
  [NOMADS](https://nomads.ncep.noaa.gov/) (RAP filters listed).

### RRFS v1 and REFS (Rapid Refresh Forecast System and its ensemble)

NOAA NWS NCEP, with OAR GSL.

- **Contents:** a 3 km North America model, hourly to 18 h (84 h at 00,
  06, 12 and 18 UTC), with 3 km CONUS and 13 km North America output; a
  relocatable 1.5 km fire-weather run over a 5° × 5° region
  (`firewx.YYYYMMDD/CC/rrfs.tCCz.{prslev,2dfld}.1p5km.fFFF.firewx_lcc.grib2`);
  5 ensemble members to 60 h; REFS ensemble products (mean, spread,
  probability-matched mean, probabilities, flash-flood `ffri`), with two
  HRRR members for CONUS.
- **Coverage:** North America and CONUS; the 1.5 km fire-weather nest only
  where NWS places it.
- **Endpoint:** NOMADS parallel since Aug 12, 2026
  (`/pub/data/nccf/com/rrfs/para/`, `/refs/para/`); production at
  `/rrfs/prod/` and `/refs/prod/` from Nov 3, 2026 (SCN 26-48, updated
  Oct 2, 2026). GRIB2 with `.idx`. No NOMADS grib filter yet (Oct 7). AWS:
  `s3://noaa-rrfs-pds` (prototype, not monitored around the clock) and
  `s3://noaa-rrfs-ops` (operational, for after October 2026), per the
  registry.
- **Updates:** hourly deterministic runs; the ensemble and REFS four times
  a day. **Size:** not measured.
- **Uses:** 1.5 km fire-weather forecasts when a fire burns in the ring;
  ensemble spread for "how sure is the forecast" cards; future-proofing
  the model reader.
- **Personas:** fire and hazards watcher, weather enthusiast, hiker and
  camper.
- **Needs:** fields, with an issue time. Effort M.
- **Risks:** a new system, so names and fields may change. The date slips
  if Nov 3 is a critical weather day (then 12 UTC on the next suitable
  weekday). Without a grib filter, ring subsets mean `.idx` Range requests
  (counted against NOMADS' 120 hits a minute) or the AWS ops bucket. RRFS
  v2 (MPAS) replacing HRRR and RAP is secondary ⚠️.
- **License:** US Government data. The AWS registry's page describes NODD
  data as a CC0-1.0 public-domain dedication, with credit requested but
  not required.
- **robots.txt:** NOMADS 404 (re-fetched Oct 7). The AWS buckets follow
  the S3 404 pattern (`noaa-rrfs-ops` not fetched individually).
- **Verified: corrected** (high). SCN 26-48 (updated Oct 2, 2026) read in
  full: dates, paths, domains, the 1.5 km fire run, 5 members to 60 h, and
  that RRFS and REFS replace NAM, HREF, SREF and HiresW (Guam's HiresW
  stays). Corrected: AWS copies exist, and NOMADS has no RRFS filter yet.
- **Evidence:** [SCN 26-48](https://www.weather.gov/media/notification/pdf_2026/scn26-048_Updated_RRFS_and_REFS_Implementation_aae.pdf),
  [registry](https://registry.opendata.aws/noaa-rrfs/),
  [NOMADS](https://nomads.ncep.noaa.gov/) (RRFS and REFS without a
  filter), a [LuckGrib post](https://luckgrib.com/blog/2026/08/25/rrfs.html)
  ⚠️ (secondary).

### National Blend of Models (NBM v5.0)

NOAA NWS Meteorological Development Laboratory; NODD on AWS.

- **Contents:** a 2.5 km CONUS blended forecast, hourly. The v5.0 12Z
  Oct 5 run has 589 element folders (researcher), including visibility,
  ceiling, sky cover, precipitation-type probabilities, snow level,
  precipitation amounts and exceedance probabilities, thunder,
  maximum/minimum temperature and frost probabilities, apparent
  temperature, wet-bulb globe temperature (WBGT), solar radiation (DSWRF),
  mixing height, transport wind, ventilation rate, fire-weather humidity
  and wind combinations, gusts, turbulence, cloud layers, SPC
  probabilities and snow depth.
- **Coverage:** CONUS at 2.5 km; the ring is about 55 × 62 cells.
- **Endpoint:** Cloud-Optimized GeoTIFFs at
  `s3://noaa-nbm-pds/blendv5.0/conus/YYYY/MM/DD/HH00/<element>/blendv5.0_conus_<element>_<run>_<valid>.tif`
  (confirmed, e.g. `blendv5.0_conus_sky_2026-10-05T12:00_2026-10-05T13:00.tif`);
  version folders `blendv3.2` to `blendv5.0` sit side by side. GRIB2 in
  `s3://noaa-nbm-grib2-pds`. SNS NewNBMCOGObject and NewNBMGRIBObject
  (account 123901341784). Also the NOMADS `blend` filter.
- **Updates:** hourly runs.
- **Size:** the sky-cover COG is about 1.6 MB per forecast hour for CONUS
  (checked); visibility about 0.4 MB (researcher). For the ring, about
  7 KB per field raw, so 20 elements × 36 h × 4 runs come to about 20 MB a
  day raw, a few MB compressed.
- **Uses:** frost-tonight and last-frost cards for gardeners and farmers;
  burn-day and smoke-dispersion checks (mixing height, ventilation rate);
  snow level and thunderstorm chances for hikers; heat stress (WBGT) and
  wind for cyclists; morning fog odds (visibility, ceiling) for commuters.
- **Personas:** gardener, farmer, hiker and camper, cyclist, commuter, fire
  and hazards watcher.
- **Needs:** fields, with an issue time; the time-series card. Effort S.
- **Risks:** version folders change, so find the newest at run time. Needs
  GDAL (already used by `basemap/imagery.py`). The COGs' internal tiling
  wasn't inspected ⚠️.
- **License:** NODD.
- **robots.txt:** `noaa-nbm-pds` and `noaa-nbm-grib2-pds` 404 NoSuchKey;
  NOMADS 404 (re-fetched Oct 7).
- **Verified: confirmed** (high). The registry confirms both buckets, SNS
  topics, license and the hourly cadence; one listing confirmed that v5.0
  is current alongside older versions, and the COG naming. The element
  count wasn't re-listed.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-nbm/),
  [versions](https://noaa-nbm-pds.s3.amazonaws.com/?list-type=2&delimiter=/),
  [sky-cover files, 12Z Oct 5](https://noaa-nbm-pds.s3.amazonaws.com/?list-type=2&prefix=blendv5.0/conus/2026/10/05/1200/sky/&max-keys=3),
  [robots.txt](https://noaa-nbm-pds.s3.amazonaws.com/robots.txt).

### RTMA, URMA and RTMA rapid update (surface analyses)

NOAA NCEP / EMC; NODD on AWS.

- **Contents:** 2.5 km analyses of observed surface weather (CONUS, Hawaii,
  Puerto Rico, Guam; 3 km for Alaska). The RTMA-RU index (researcher)
  lists HGT, PRES, 2 m TMP/DPT/SPFH, 10 m U/V/WDIR/WIND/GUST, visibility
  (VIS), ceiling (CEIL) and cloud cover (TCDC). RTMA is hourly; URMA is a
  later rerun with more observations; RTMA-RU comes every 15 min.
- **Coverage:** CONUS at 2.5 km; the ring is about 55 × 62 cells. Archive
  from the start of 2019 (registry).
- **Endpoint:** `s3://noaa-rtma-pds/rtma2p5_ru.YYYYMMDD/rtma2p5_ru.tHHMMz.2dvaranl_ndfd.grb2`
  (plus `.idx` for Range); `s3://noaa-urma-pds`; SNS NewNCEPRTMAObject and
  NewNCEPURMAObject; live ring subsets through the NOMADS filters
  `rtma_ru` and `rtma2p5` (URMA has no filter).
- **Updates:** every 15 min (RU); hourly (RTMA); URMA later (about 6 h ⚠️).
- **Size** (researcher): the RTMA-RU analysis is 84 MB per 15 min for
  CONUS; by Range, VIS 6.6 MB and CEIL 8.4 MB. A NOMADS ring subset is KB
  per 15 min. Stored: about 4 MB a day raw for 6 fields (1–3 MB
  compressed).
- **Uses:** visibility and ceiling every 15 min for the fog study; gust and
  wind maps for cyclists; cold-air pooling on frost nights; haze in the
  Normal lens driven by real visibility.
- **Personas:** traffic researcher, commuter, cyclist, gardener, weather
  enthusiast.
- **Needs:** fields, full replay. Effort S.
- **Risks:** an analysis, not a measurement, and fog visibility is hard to
  analyse: validate it against METARs and the cameras. RTMA-RU's start on
  AWS wasn't checked separately ⚠️. Backfilling many days by Range is
  heavy (about 7 MB per field per 15 min).
- **License:** NODD.
- **robots.txt:** `noaa-rtma-pds` and `noaa-urma-pds` 404 NoSuchKey;
  NOMADS 404 (re-fetched Oct 7).
- **Verified: confirmed** (high). The registry confirms buckets, SNS, the
  2019 start and license; the NOMADS listing confirms both RTMA filters.
  File naming and sizes are the researcher's (not repeated).
- **Evidence:** [registry](https://registry.opendata.aws/noaa-rtma/),
  [NOMADS](https://nomads.ncep.noaa.gov/) (`rtma_ru` and `rtma2p5`),
  robots.txt for [RTMA](https://noaa-rtma-pds.s3.amazonaws.com/robots.txt)
  and [URMA](https://noaa-urma-pds.s3.amazonaws.com/robots.txt), the
  researcher's [RTMA-RU index](https://noaa-rtma-pds.s3.amazonaws.com/rtma2p5_ru.20261005/rtma2p5_ru.t1200z.2dvaranl_ndfd.grb2.idx).

### NDFD (National Digital Forecast Database)

NOAA NWS / MDL; NODD on AWS. The official NWS forecast grids.

- **Contents:** forecaster-edited gridded forecasts behind
  forecast.weather.gov and the NWS API's gridpoints: temperature, sky
  cover, weather type, precipitation amounts and chances, wind, gusts and
  more, in GRIB2.
- **Coverage:** CONUS (2.5 km ⚠️), covering the ring.
- **Endpoint:** `s3://noaa-ndfd-pds`. `opnl/` and `expr/` hold the latest
  files only (`opnl/AR.conus/`, `AR.alaska/` and other areas, overwritten
  as forecasts update); `wmo/<parameter>/<year>/<month>/<day>/<wmo-file>`
  holds the history; `NDFDelem_fullres_*.xls` in the root decodes the WMO
  names. SNS NewNDFDObject (Lambda and SQS only). NOAA recommends degrib,
  wgrib2 or grib2io, because some decoders mishandle NDFD's scan order.
- **Updates:** as often as every 30 min, varying by element, projection
  and domain (registry). **Size:** not measured.
- **Uses:** the official NWS Boise forecast on our map without using
  api.weather.gov; forecast-against-actual replay ("what NWS said at
  6 am", from the `wmo/` history).
- **Personas:** commuter, weather enthusiast, gardener.
- **Needs:** fields, with an issue time. Effort M.
- **Risks:** the latest-only folders are overwritten, so a live recorder
  must poll and keep its own copies, or rebuild from `wmo/`. Overlaps NBM,
  which is NDFD's usual starting point.
- **License:** NODD.
- **robots.txt:** `noaa-ndfd-pds` 404 NoSuchKey (re-fetched Oct 7).
- **Verified: confirmed** (high). The registry and two listings confirm the
  bucket, prefixes, SNS, decoder advice and cadence; the verifier added
  that `opnl/` and `expr/` are latest-only and `wmo/` is the history. The
  grid spacing isn't stated on the registry page (kept ⚠️).
- **Evidence:** [registry](https://registry.opendata.aws/noaa-ndfd/),
  [bucket root](https://noaa-ndfd-pds.s3.amazonaws.com/?list-type=2&delimiter=/),
  [`opnl/`](https://noaa-ndfd-pds.s3.amazonaws.com/?list-type=2&prefix=opnl/&delimiter=/),
  [robots.txt](https://noaa-ndfd-pds.s3.amazonaws.com/robots.txt).

### Open-Meteo forecast API

Open-Meteo. Verdict: **avoid**.

- **What:** a convenience JSON API repackaging national weather models,
  worldwide.
- **robots.txt:** `api.open-meteo.com/robots.txt` is `User-agent: *` with
  `Disallow: /` (re-fetched Oct 7). License not reviewed, given that.
- **Uses:** none: the same NOAA models are available directly. Persona:
  weather enthusiast.
- **Verified: confirmed** (high): robots.txt re-fetched and matches.
- **Evidence:** [robots.txt](https://api.open-meteo.com/robots.txt).

## Forecasts, warnings and airport observations

### NWS API (api.weather.gov)

NOAA National Weather Service. Verdict: **needs an owner action**
([open question 1](#open-questions)).

- **Contents:** `/points` to find the office and grid;
  `/gridpoints/{office}/{x},{y}` raw forecast data, `/forecast` and
  `/forecast/hourly`; `/stations` and observations; `/alerts` and
  `/alerts/active?area=`; radar status.
- **Coverage:** the whole US; the Boise office (BOI) covers the valley and
  the ring.
- **Endpoint:** HTTPS JSON (GeoJSON or JSON-LD). Requires a User-Agent
  that identifies the application; NWS says it will eventually move to API
  keys. The rate limit isn't published (the docs call it generous); retry
  after about 5 s when limited.
- **Updates:** alerts within minutes; forecasts hourly or better.
  **Size:** KB a call.
- **Uses:** active alerts (winter storm, dense fog, red flag, heat) as
  lifecycles in the Valley Feed; official point forecasts for cards; the
  latest observations at NWS stations.
- **Personas:** commuter, fire and hazards watcher, hiker and camper,
  weather enthusiast.
- **Needs:** lifecycles (`evt.event`) and the Valley Feed, readings.
  Effort S.
- **Risks:** a policy conflict: robots.txt disallows everything while the
  docs invite apps. Until the owner decides, forecasts come from NDFD and
  NBM on AWS, observations from AWC and IEM, and warnings from IEM's VTEC
  service. A future API key would be an owner action.
- **License:** open data, free for any purpose, no fees (from the docs).
- **robots.txt:** `api.weather.gov/robots.txt` is `User-agent: *` with
  `Disallow: /` (the whole host; re-fetched Oct 7), so under our rules
  it's off-limits to automated collection. `alerts.weather.gov` returns
  NXDOMAIN: the host no longer exists, so it isn't an alternative. No
  sample request was made.
- **Verified: corrected** (high). Docs and robots.txt confirmed.
  Corrected: `alerts.weather.gov` isn't a passing network error but a
  retired host, so CAP alerts now come only from api.weather.gov. Added
  the docs' note that API keys are planned.
- **Evidence:** [docs](https://www.weather.gov/documentation/services-web-api),
  [robots.txt](https://api.weather.gov/robots.txt),
  [alerts.weather.gov](https://alerts.weather.gov/robots.txt) (NXDOMAIN on
  Oct 7).

### Iowa Environmental Mesonet (IEM)

Iowa State University. Airport weather history (including 1-minute data),
NWS warnings (VTEC), storm reports, NWS text and radar mosaics. Already in
[SOURCES](../SOURCES.md) as "Boise airport weather history (IEM ASOS)",
not started.

- **Contents:**
  - ASOS/AWOS history: temperature, dew point, wind, gusts, visibility, sky
    cover and cloud bases, present weather, precipitation, ice accretion
    and the raw METAR; report types 1 (HFMETAR, 5-min), 3 (routine) and 4
    (specials).
  - 1-minute ASOS data, which come from NCEI about 24 h late
    (`asos1min.py`).
  - NWS warnings by VTEC with polygons, Local Storm Reports, NWS text
    products, MOS, and US NEXRAD composites ⚠️ (dates not re-checked).
- **Coverage:** the ring's stations in IEM's ID_ASOS network (checked):

  | Station | Place | Archive from | 1-minute data |
  |---|---|---|---|
  | BOI | Boise | Jan 1, 1929 | Yes: the only ring station flagged |
  | EUL | Caldwell | Apr 9, 1992 | Not flagged |
  | MAN | Nampa (an AWOS) | May 14, 2010 | Not flagged |
  | MUO | Mountain Home AFB | Jan 1, 1932 | Not flagged |

  ONO (Ontario) isn't in ID_ASOS (Oregon's network ⚠️).
- **Endpoint:** CGI and JSON:
  - `/cgi-bin/request/asos.py`: at most 1,000 station-years per request
    since Jan 23, 2026 (HTTP 422 beyond); an IP rate limit (HTTP 429); a
    1-s per-IP throttle since Apr 21, 2026;
  - `/cgi-bin/request/asos1min.py`;
  - `/api/1/` (vtec, lsr, nwstext and others ⚠️ not re-checked);
  - `/archive/data/YYYY/MM/DD/GIS/uscomp/` for mosaics.
- **Updates:** near real time for METARs and warnings; 1-minute ASOS about
  24 h behind; archives go back decades.
- **Size:** a year of 1-minute data for one ASOS is tens of MB of CSV ⚠️;
  routine METARs a few MB per station-decade; warnings, reports and text
  KB a day.
- **Uses:** backfill BOI's 1-minute visibility for the fog study
  ([ch. 2](../02-treasure-valley-signal-system.md),
  [ch. 8](../08-data-inventory.md)), with routine and 5-minute METARs at
  EUL, MAN and MUO; the fog chip's history (live from AWC, history from
  IEM); warnings as lifecycles while api.weather.gov is unresolved;
  spotter reports in the Valley Feed; radar composites for chosen event
  days.
- **Personas:** traffic researcher, commuter, weather enthusiast, fire and
  hazards watcher.
- **Needs:** readings, lifecycles and the Valley Feed, full replay, the
  ingest framework (crawl delay; one shared queue per host). Effort S.
- **Risks:** little quality control on the ASOS archive. The 120-s crawl
  delay is a whole-host budget of at most 720 requests a day, shared by
  every IEM use (warnings, storm reports, text, soundings, backfills), so
  polling warnings every 2 min would use all of it. Mosaic backfills are
  practical only for a few event days. 1-minute data lag about a day.
- **License:** public domain: free for any lawful purpose; credit to IEM is
  appreciated (from the disclaimer).
- **robots.txt:** re-fetched Oct 7: Crawl-delay 120, and Disallow
  `/usage/`, `/tmp/`, `/data/NIDS/`, `/data/nexrd2/`, `/data/model/`,
  `/archive/nexrad/` and `/archive/raw/snet/`, with no User-agent line
  (our lenient parser applies them to everyone). The CGI, API and
  `/archive/data/` paths are allowed, at one request every 120 s across
  the host. CLAUDE.md already requires honoring this delay.
- **Verified: corrected** (high). Five IEM pages were fetched with our
  User-Agent, 125 s apart. Confirmed: the robots rules, the public-domain
  disclaimer, the stations' archive starts and the 1,000 station-year
  limit. Corrected: only BOI is flagged for 1-minute data among the ring's
  stations, so the planned BOI, MAN and EUL 1-minute backfill is BOI only;
  1-minute data arrive about 24 h late; `asos.py` now has its own IP
  throttle. API endpoints and mosaic dates not re-checked.
- **Evidence:** [robots.txt](https://mesonet.agron.iastate.edu/robots.txt),
  [disclaimer](https://mesonet.agron.iastate.edu/disclaimer.php),
  [ID_ASOS stations](https://mesonet.agron.iastate.edu/sites/networks.php?network=ID_ASOS),
  [`asos.py` help](https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?help),
  [`asos1min.py` help](https://mesonet.agron.iastate.edu/cgi-bin/request/asos1min.py?help),
  and, from the researcher, not re-checked: [mosaic docs](https://mesonet.agron.iastate.edu/docs/nexrad_mosaic/),
  [API docs](https://mesonet.agron.iastate.edu/api/1/docs).

### Aviation Weather Center Data API

NOAA NWS Aviation Weather Center. METAR, TAF, PIREP, SIGMET and AIRMET.

- **Contents:** METARs, TAFs, PIREPs and AIREPs, SIGMETs, G-AIRMETs, CWAs
  and station info, as raw text, JSON, GeoJSON, CSV, XML or IWXXM. The
  researcher's sample METAR JSON includes cloud cover and bases,
  visibility, flight category and the raw text. Bulk gzip cache files are
  recommended for large pulls.
- **Coverage:** KBOI, KMAN, KEUL and KMUO in Idaho, plus KONO (Ontario,
  OR).
- **Endpoint:** `https://aviationweather.gov/api/data/metar?ids=...&format=json&hours=N`
  (most endpoints return at most 400 entries, from the last 30 days at
  most), or cache files under `/data/cache/` (METARs and AIRMETs every
  minute, TAFs every 10 min, stations daily). At most 100 requests a
  minute; set a custom User-Agent.
- **Updates:** routine METARs hourly, plus specials; AWOS sites more often
  (about every 20 min ⚠️).
- **Size:** about 1 KB a METAR; under 2 MB a day for the ring's airports
  at 5-minute polling.
- **Uses:** live visibility, ceiling and weather codes for the fog chip
  ([ch. 13](../13-visual-design.md)) and feed cards; cloud bases for the
  bottom of the 3D cloud layer; TAFs for "fog likely at BOI tomorrow
  morning"; PIREPs (turbulence, icing, cloud tops) for the aircraft plugin.
- **Personas:** commuter, traffic researcher, weather enthusiast, sky
  watcher.
- **Needs:** readings, the Valley Feed, the ingest framework. Effort S.
- **Risks:** only 30 days are kept, so history comes from IEM. BOI's fog
  isn't the whole valley's fog.
- **License:** US Government (NWS) data; there's no license statement on
  the API page, so we assume public domain ⚠️. The site carries the
  standard US-government authorized-use banner.
- **robots.txt:** `aviationweather.gov/robots.txt` 404 (re-fetched Oct 7).
- **Verified: confirmed** (high). The API page confirms the 100
  requests/min limit, the 400-row cap, the 30-day window, the cache files
  and cadence, and the User-Agent advice; no key is mentioned.
- **Evidence:** [API page](https://aviationweather.gov/data/api/),
  [robots.txt](https://aviationweather.gov/robots.txt), the researcher's
  one [sample request](https://aviationweather.gov/api/data/metar?ids=KBOI,KMAN,KEUL,KONO,KMUO&format=json&hours=1)
  (not repeated).

## Upper air

### Boise weather balloons (BOI, WMO 72681) via IEM's RAOB archive

Launched by NWS Boise; archived by IEM (from SPC in near real time,
backfilled from NCEI's IGRA).

- **Contents:** twice-daily balloon profiles (00 and 12 UTC): pressure,
  height, temperature, dew point, wind, and the balloon's bearing and
  range, with level codes (mandatory, significant, wind, tropopause,
  maximum wind, surface). IEM's site list has KBOI (Boise Arpt) from 1948.
- **Coverage:** one point, launched inside the valley box.
- **Endpoint:** CSV from `/cgi-bin/request/raob.py` (the form on the
  archive page). The JSON routes (`/json/raob.py`, `/api/1/raob`) weren't
  re-checked ⚠️. Near real time since March 2025 (from SPC), after NOAA's
  rucsoundings site shut down in September 2024.
- **Updates:** twice daily, within hours. **Size:** about 20–50 KB a
  sounding; under 0.1 MB a day.
- **Uses:** winter inversion strength and depth; freezing and snow levels
  for hikers; the fog layer's top for the 3D fog; upper winds for a "wind
  above Boise" card and smoke direction; contrail likelihood at flight
  levels.
- **Personas:** weather enthusiast, traffic researcher, hiker and camper,
  sky watcher, fire and hazards watcher.
- **Needs:** readings, with a vertical-profile variant; the time-series
  card. Effort S.
- **Risks:** only two profiles a day, and balloons drift downwind. SPC,
  IEM's real-time source, disallows robots, so IEM is our only real-time
  route; IGRA under NCEI's `/pub/` is an allowed backup.
- **License:** IEM's public domain; the soundings are NWS observations.
- **robots.txt:** IEM's Crawl-delay 120 applies; the RAOB paths aren't
  disallowed (re-fetched Oct 7).
- **Verified: confirmed** (high). The archive page was read: KBOI from
  1948, near real time since March 2025 from SPC with IGRA backfill, and
  the columns and level codes match.
- **Evidence:** [archive page](https://mesonet.agron.iastate.edu/archive/raob/),
  [robots.txt](https://mesonet.agron.iastate.edu/robots.txt).

### IGRA v2 (Integrated Global Radiosonde Archive)

NOAA NCEI. Verdict: **use, as an optional backup**.

- **Contents:** radiosonde and pilot-balloon profiles from more than 2,800
  stations (about 800 reporting now), the earliest from 1905: sounding
  data by station, monthly means and derived parameters, all plain text.
- **Coverage:** includes Boise (`USM00072681` ⚠️: the file name wasn't
  listed).
- **Endpoint:** the product page links
  `https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/access/`
  (robots-disallowed) and the legacy FTP path `/pub/data/igra/`. The same
  tree is served over HTTPS at `https://www.ncei.noaa.gov/pub/data/igra/`
  (`data/data-por/` for the period of record, `data/data-y2d/` for the
  year to date, `derived/`, `monthly/`), updated Oct 6, 2026, and `/pub/`
  isn't disallowed.
- **Updates:** daily (the data folders were modified Oct 6). **Size:** one
  station's period-of-record file is tens of MB ⚠️.
- **Uses:** quality-controlled history to check or fill IEM's copy; a
  backup route for Boise soundings if IEM is unavailable.
- **Personas:** weather enthusiast.
- **Needs:** readings. Effort S.
- **Risks:** low priority, since IEM has the same soundings in real time.
  Anyone computing trends should mind instrument changes (NCEI's caution).
- **License:** NOAA public data; no explicit license on the product page.
- **robots.txt:** `www.ncei.noaa.gov/robots.txt` (User-agent `*`)
  disallows only `/data*` and `/orders*`: the `/data/...` copy is
  off-limits, `/pub/data/igra/` is allowed (re-fetched Oct 7).
- **Verified: corrected** (high). This refutes the researcher's
  "robots-disallowed, owner only" verdict: the HTTPS `/pub/data/igra/`
  copy is allowed by NCEI's robots.txt and current, so the verdict changed
  from needs-owner-action to use (optional backup). The station count and
  start year are confirmed on the product page.
- **Evidence:** [product page](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive),
  [robots.txt](https://www.ncei.noaa.gov/robots.txt),
  [`/pub/data/igra/`](https://www.ncei.noaa.gov/pub/data/igra/) and
  [`data/`](https://www.ncei.noaa.gov/pub/data/igra/data/) (Oct 7
  listings).

### SPC and University of Wyoming sounding and analysis pages

NOAA Storm Prediction Center; University of Wyoming Department of
Atmospheric Science. Verdict: **avoid**.

- **What:** sounding plots and text (Wyoming); mesoanalysis, storm reports
  and outlooks (SPC). National, including Boise. Web pages and CGI.
- **robots.txt** (re-fetched Oct 7): `www.spc.noaa.gov/robots.txt` has a
  `User-agent: *` group with Crawl-delay 10 and `Disallow: /` (the whole
  site); `weather.uwyo.edu/robots.txt` disallows `/cgi-bin`, `/wsgi` and
  `/upperair/imgs` for all agents.
- **License:** SPC is NOAA (public); Wyoming's isn't stated. Moot, given
  robots.txt.
- **Uses:** nothing automated: IEM provides the soundings, storm reports
  and SPC outlooks. Persona: weather enthusiast.
- **Verified: confirmed** (high): both robots files re-fetched and match.
- **Evidence:** robots.txt for [SPC](https://www.spc.noaa.gov/robots.txt)
  and [Wyoming](https://weather.uwyo.edu/robots.txt).

## Other station networks

### RAWS fire-weather stations via FEMS (and WRCC's RAWS pages)

USDA Forest Service and interagency wildland fire (FEMS); Western Regional
Climate Center, Desert Research Institute (WRCC). Verdict: **needs an owner
action** (an account for history).

- **Contents:** Remote Automated Weather Stations: hourly temperature,
  humidity, wind, gusts, precipitation, fuel temperature and moisture,
  solar radiation; NFDRS fire-danger outputs; national fuel-moisture
  samples.
- **Coverage:** backcountry stations around the ring; the exact station
  list isn't verified.
- **Endpoint:** the FEMS web UI. Without a login: RAWS hourly observations
  and NFDRS outputs for the last 2 weeks plus a 7-day forecast, and the
  full fuel-moisture history. With Login.gov/eAuth: the full RAWS and
  NFDRSv4 history. A public REST API is announced, with details still to
  come. WRCC has HTML station pages.
- **Updates:** hourly. **Size:** small, about 24 rows per station-day.
- **Uses:** ridge and canyon conditions where there's no airport; fire
  danger and fuel dryness for the hazards board; ground truth for HRRR and
  NBM winds in the foothills.
- **Personas:** hiker and camper, fire and hazards watcher, weather
  enthusiast.
- **Needs:** readings, areas. Effort M.
- **Risks:** history needs an account (an owner action). The public API
  isn't documented, so don't build against unpublished endpoints. WRCC's
  future is unclear.
- **License:** federal data; FEMS links privacy and disclaimer pages but no
  license text was seen. WRCC shows only a copyright line.
- **robots.txt** (re-fetched Oct 7): `fems.fs2c.usda.gov` allows
  everything (empty Disallow); `raws.dri.edu` has `Allow: /`;
  `wrcc-archive.dri.edu` sets Crawl-delay 5 and disallows `/research`;
  `wrcc.dri.edu` has an empty Disallow.
- **Verified: confirmed** (medium, raised from low). The FEMS access page
  and all four robots files confirm the catalog; the station list is still
  unverified.
- **Evidence:** [FEMS access](https://www-wfweb.fs2c.usda.gov/page/access),
  robots.txt for [FEMS](https://fems.fs2c.usda.gov/robots.txt),
  [raws.dri.edu](https://raws.dri.edu/robots.txt),
  [wrcc-archive](https://wrcc-archive.dri.edu/robots.txt) and
  [wrcc](https://wrcc.dri.edu/robots.txt).

### Synoptic Data (MesoWest) API

Synoptic Data PBC. Verdict: **avoid**.

- **Contents:** surface observations aggregated from many networks (RAWS,
  DOTs, mesonets, ASOS), with a time-series API. Dense in Idaho, including
  the valley.
- **Endpoint:** a REST API with a token. Its Open Access program is for
  members of accredited US educational institutions with a .edu address,
  for non-commercial research or coursework: up to 1 year of history for
  an approved region, renewed yearly. Otherwise commercial plans (with a
  14-day trial); there's no free tier for non-academic users.
- **License:** Open Access requires crediting Synoptic and sharing results
  in two or more public ways. Redistribution rules for restricted
  providers, and rules on showing tokens, weren't found on the pages
  checked ⚠️.
- **robots.txt:** `api.synopticdata.com/robots.txt` returned 401 on Oct 7
  (4xx means no rules), but a token is still required.
- **Uses:** one API for RAWS and mesonet stations. **Personas:** weather
  enthusiast, hiker and camper, fire and hazards watcher. **Needs:**
  readings. Effort S.
- **Risks:** we don't qualify for Open Access, and paid plans don't suit a
  public non-commercial project. IEM, AWC and FEMS cover the essentials.
- **Verified: corrected** (high). Eligibility, history and renewal terms
  confirmed. The catalog's statements about restricted-provider
  redistribution and hiding tokens couldn't be found on the pages read and
  are now marked ⚠️. Verdict unchanged.
- **Evidence:** [Open Access pricing](https://synopticdata.com/pricing/open-access-pricing/),
  [pricing](https://synopticdata.com/pricing/),
  [robots.txt](https://api.synopticdata.com/robots.txt) (401).

### MADIS (Meteorological Assimilation Data Ingest System)

NOAA NWS / NCEP. Verdict: **needs an owner action** (an application for
the restricted sets).

- **Contents:** integrated surface observations (non-mesonet and mesonet,
  including RAWS and CWOP citizen stations ⚠️), upper-air, profiler,
  satellite and aircraft observations, in netCDF, plus a text/XML viewer.
- **Coverage:** worldwide, densest over North America.
- **Endpoint:** the unrestricted datasets (non-mesonet surface, radiosonde,
  profilers, satellite winds and soundings, snow, RSAS) are open,
  including through the text/XML viewer web service. The restricted ones
  (mesonet surface, hydrological surface, aircraft, radiometer) need a
  Data Application Form and are offered to government, research and
  education users (category 2).
- **Updates:** minutes. **Size:** not estimated.
- **Uses:** a single feed for RAWS and mesonets, if the owner applies.
- **Personas:** weather enthusiast, fire and hazards watcher.
- **Needs:** readings. Effort M.
- **Risks:** the useful part (the mesonets, including RAWS) is restricted
  and needs an application. CWOP stations are personal home stations
  (privacy: aggregate only).
- **License:** restricted data mustn't be redistributed or put on web pages
  without notifying NOAA; displayed mesonet data must name the source,
  with a disclaimer; NOAA-only mesonet data may never appear on public
  pages.
- **robots.txt:** `madis.ncep.noaa.gov` and `madis-data.ncep.noaa.gov`
  both 404 (re-fetched Oct 7).
- **Verified: corrected** (medium). Corrected "everything needs a Data
  Application Form": only the restricted sets do; the public, non-mesonet
  ones are open. Redistribution rules taken from the restrictions page.
  Whether RAWS is in the restricted mesonet set isn't stated there ⚠️.
- **Evidence:** [datasets](https://madis.ncep.noaa.gov/madis_datasets.shtml),
  [restrictions](https://madis.ncep.noaa.gov/madis_restrictions.shtml),
  robots.txt for [madis](https://madis.ncep.noaa.gov/robots.txt) and
  [madis-data](https://madis-data.ncep.noaa.gov/robots.txt).

### USBR AgriMet (Pacific Northwest agricultural weather network)

US Bureau of Reclamation, Pacific Northwest Region. Verdict: **needs an
owner action** (ask Reclamation before any collector).

- **Contents:** agricultural weather: air and soil temperature, humidity,
  wind, solar radiation, precipitation, reference evapotranspiration and
  crop water-use charts.
- **Coverage:** stations in the valley box and the ring, from
  Reclamation's `location.csv`:

  | Station | Place | Installed | Area |
  |---|---|---|---|
  | BOII | Boise | 1995 | Valley box |
  | BFGI | Boise Fairgrounds | 2013 | Valley box |
  | NMPI | Nampa | 1996 | Valley box |
  | PMAI | Parma | 1986 | Valley box |
  | ONTO | Ontario, OR | 1992 | Ring |
  | GDVI | Grand View | 1992 | Ring |

  The file's active flag is blank, so whether each still reports is
  unconfirmed.
- **Endpoint:** form pages under `/pn/agrimet/` (8-day instantaneous,
  10-day daily, daily and hourly/15-min archives, water-year reports)
  whose data come from CGI under `/pn-bin/`; the station list at
  `/pn/agrimet/location.csv` and `agrimetmap/usbr_map.json` (both
  allowed); Reclamation's RISE API at `data.usbr.gov/rise/api`. AgriMet
  links a Word document on automated data collection
  (`HydrometWebService.doc`, not read).
- **Updates:** 15-min and daily. **Size:** KB per station-day.
- **Uses:** crop water use and evapotranspiration for farmers and
  gardeners; soil temperature for planting dates; solar radiation to check
  GOES and NBM sunshine.
- **Personas:** farmer, gardener.
- **Needs:** readings. Effort S.
- **Risks:** the data CGI and the API are robots-disallowed. Reclamation's
  own automated-collection document suggests they expect scripts, but
  robots.txt says otherwise, so ask Reclamation before building any
  collector.
- **License:** federal data; no license text on the pages.
- **robots.txt** (re-fetched Oct 7): `www.usbr.gov/robots.txt` disallows
  `/pn-bin` and `/gp-bin`; `data.usbr.gov/robots.txt` disallows
  `/rise/api` and several time-series and map query paths. Automated
  collection is off-limits; one-off lookups at the owner's request are
  fine.
- **Verified: corrected** (high). Robots rules confirmed. Corrected the
  station list: a Parma station (PMAI, since 1986) exists, plus Boise
  Fairgrounds, and Ontario and Grand View in the ring; Boise and Nampa
  confirmed from Reclamation's own CSV rather than search results.
- **Evidence:** [AgriMet](https://www.usbr.gov/pn/agrimet/),
  [weather data page](https://www.usbr.gov/pn/agrimet/wxdata.html),
  [`location.csv`](https://www.usbr.gov/pn/agrimet/location.csv) (one
  small request), robots.txt for [www.usbr.gov](https://www.usbr.gov/robots.txt)
  and [data.usbr.gov](https://data.usbr.gov/robots.txt).

### CoCoRaHS volunteer precipitation reports

Community Collaborative Rain, Hail and Snow Network (Colorado State
University, Colorado Climate Center).

- **Contents:** daily 24-h precipitation (rain and snow water, new snow,
  snow depth), multi-day reports, hail reports and significant-weather
  reports; station IDs like `ID-AD-xx` (Ada) and `ID-CN-xx` (Canyon).
- **Coverage:** volunteer stations across Ada, Canyon and the ring's
  counties (density unchecked).
- **Endpoint:** the export manager at `data.cocorahs.org`: Daily,
  Multi-Day, Hail and SigWx reports, as XML, XML Compact, CSV, SHEF or SHEF
  Snow, by state, filtered by report date or report timestamp (GMT). No
  documented URL parameters for scripts.
- **Updates:** daily (morning reports). **Size:** KB a day for the state.
- **Uses:** "rain in my yard" ground truth next to MRMS gauge-corrected
  rainfall; hail reports on fields and roofs; snowfall totals across the
  valley after a storm.
- **Personas:** gardener, farmer, weather enthusiast, commuter.
- **Needs:** readings, the Valley Feed. Effort S.
- **Risks:** stations are at volunteers' homes and exports include
  observer-linked station names: show values on a grid or at rounded
  locations, never names. Morning-reading days differ from midnight days.
  The export is an ASP.NET form, so a script would depend on undocumented
  parameters. One request a day is plenty.
- **License:** data under Creative Commons Attribution 3.0, the website
  under CC BY 4.0; acknowledge CoCoRaHS when displaying; available to
  governments, academia and the private sector.
- **robots.txt** (re-fetched Oct 7): `www.cocorahs.org/robots.txt` (with a
  BOM) disallows `/admin/` and `/viewdata/`; `data.cocorahs.org/robots.txt`
  is 404 (no rules).
- **Verified: confirmed** (medium). License, export options and both
  robots files confirmed.
- **Evidence:** [data usage policy](https://www.cocorahs.org/Content.aspx?page=datausagepolicy),
  [export manager](https://data.cocorahs.org/cocorahs/export/exportmanager.aspx),
  robots.txt for [www](https://www.cocorahs.org/robots.txt) and
  [data](https://data.cocorahs.org/robots.txt).

## Climate and history

### PRISM climate grids (daily, monthly, 1991–2020 normals)

PRISM Group, Oregon State University.

- **Contents:** gridded precipitation, minimum, maximum and mean
  temperature, dew point, vapour-pressure deficit and more: daily and
  monthly series and 1991–2020 normals at 4 km and 800 m (800 m free since
  March 27, 2025). Cloud-Optimized GeoTIFFs since Oct 1, 2025 (BIL
  dropped), with a 400 m (15 arc-second) level added to the directory
  structure. Daily grids are revised as more data arrive; the "up to 8
  times over 6 months" figure wasn't found on the pages read ⚠️.
- **Coverage:** CONUS. At 800 m (30 arc-seconds) the ring is about
  204 × 168 cells.
- **Endpoint:** HTTPS at `https://data.prism.oregonstate.edu`, anonymous
  FTP at `prism.oregonstate.edu`, and one consolidated web service
  (documented in PDFs, not read). PRISM describes FTP and the web services
  as meant for automated fetching.
- **Updates:** daily (provisional) and monthly; normals static.
- **Size:** an 800 m CONUS daily COG is tens of MB ⚠️; ring reads by range
  request are KB. Normals: a one-time few MB for the ring.
- **Uses:** microclimate maps for gardeners (the normal frost-free season
  by neighbourhood); last night's low and yesterday's rain by field;
  climate context cards ("a typical October 7").
- **Personas:** gardener, farmer, weather enthusiast, hiker and camper.
- **Needs:** fields, areas. Effort S.
- **Risks:** provisional daily values change for months, so store the
  version or stability flag the site now shows. Download limits aren't
  stated; keep to one pass a day.
- **License:** all data may be freely reproduced and distributed; cite
  PRISM's name, URL and date of access. PRISM advises against very
  long-term trend calculations.
- **robots.txt:** `prism.oregonstate.edu`, `data.prism.oregonstate.edu` and
  `services.nacse.org` all 404 (re-fetched Oct 7). robots.txt doesn't
  cover FTP.
- **Verified: corrected** (high). Terms, the 800 m free date, the COG
  switch and the access routes confirmed. Corrected the ring's grid size
  (30 arc-second cells give about 204 × 168, not 175 × 200), added the new
  400 m level, and marked the revision count unconfirmed.
- **Evidence:** [terms](https://prism.oregonstate.edu/terms/),
  [downloads](https://prism.oregonstate.edu/downloads/),
  [what's new](https://prism.oregonstate.edu/whatsnew),
  [Oct 1, 2025 notice](https://prism.oregonstate.edu/notices/notice_20251001.php),
  robots.txt for [prism](https://prism.oregonstate.edu/robots.txt),
  [data.prism](https://data.prism.oregonstate.edu/robots.txt) and
  [services.nacse.org](https://services.nacse.org/robots.txt).

### NOAA U.S. Climate Normals 1991–2020

NOAA NCEI; NODD on AWS.

- **Contents:** hourly, daily, monthly and annual/seasonal normals of
  temperature, precipitation and other variables from about 15,000
  stations (cloudiness, degree days, freeze-date probabilities and similar
  elements ⚠️, from a catalog search).
- **Coverage:** by station: the Boise airport, `USW00024131` (hourly
  6.4 MB CSV, daily 0.67 MB, from the researcher's listing), plus other
  valley stations ⚠️.
- **Endpoint:** `s3://noaa-normals-pds/normals-{hourly,daily,monthly,annualseasonal}/{1991-2020,2006-2020,1981-2010}/access/<station>.csv`.
  NCEI's own `/data/` copy is robots-disallowed and there's no
  `/pub/data/normals/` (404); `/access/services/data/v1` is allowed.
- **Updates:** every 10 years, or on corrections (registry). **Size:**
  about 7 MB one time for Boise (hourly and daily).
- **Uses:** "normal for today" on every weather card; expected sunshine by
  hour and month (the cloudiness normals) for the garden sun planner;
  freeze-date odds for planting.
- **Personas:** gardener, farmer, weather enthusiast, commuter.
- **Needs:** the time-series card, readings. Effort S.
- **Risks:** station normals, not gridded (PRISM is for maps). Check which
  hourly cloudiness elements Boise has, in the CSV header, before building
  the sun planner on them.
- **License:** NODD.
- **robots.txt:** `noaa-normals-pds` 404 NoSuchKey; NCEI disallows
  `/data*` and `/orders*` (re-fetched Oct 7).
- **Verified: confirmed** (high). The registry confirms the bucket, the
  folder layout (it adds 1981–2010), license and update cycle. The element
  list stays ⚠️.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-climate-normals/),
  robots.txt for [S3](https://noaa-normals-pds.s3.amazonaws.com/robots.txt)
  and [NCEI](https://www.ncei.noaa.gov/robots.txt),
  [`/pub/data/normals/`](https://www.ncei.noaa.gov/pub/data/normals/)
  (404), the researcher's [Boise listing](https://noaa-normals-pds.s3.amazonaws.com/?list-type=2&prefix=normals-hourly/1991-2020/access/USW00024131).

### GHCN-Daily station records

NOAA NCEI.

- **Contents:** daily maximum and minimum temperature, precipitation,
  snowfall, snow depth and more from airport, COOP and other stations;
  Boise `USW00024131` back to the 1940s ⚠️.
- **Coverage:** every GHCN station in the ring (Boise, Nampa, Caldwell,
  Parma, Emmett, Mountain Home and others ⚠️).
- **Endpoint:** three routes:
  1. NCEI's Access Data Service:
     `https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries&stations=...&startDate=...&endDate=...&format=csv|json`
     (no token mentioned; limits not documented);
  2. per-station gzip CSVs at
     `https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/`
     (modified Oct 6, 2026; robots-allowed), and `.dly` files under
     `/pub/data/ghcn/daily/all/`;
  3. AWS `s3://noaa-ghcn-pds`, with `by_year` CSVs (daily), but its
     `by_station` files are stale (`USW00024131.csv` last modified Feb 9,
     2025, re-checked).
- **Updates:** daily. **Size:** a station's full daily history is a few MB
  compressed (the stale S3 Boise CSV is 14 MB uncompressed).
- **Uses:** "this day in Boise weather" records; long snow and heat
  histories next to traffic growth; validating PRISM and MRMS rainfall.
- **Personas:** weather enthusiast, gardener, farmer, traffic researcher.
- **Needs:** readings, the time-series card. Effort S.
- **Risks:** don't pull the `by_year` files (worldwide, about 1 GB each).
  The service's row and rate limits are undocumented, so prefer the
  per-station `/pub/` file for full histories.
- **License:** NOAA public data (NODD terms for the AWS copy).
- **robots.txt:** NCEI disallows only `/data*` and `/orders*`, so
  `/access/services/...` and `/pub/data/ghcn/...` are allowed;
  `noaa-ghcn-pds` is 404 NoSuchKey (re-fetched Oct 7).
- **Verified: corrected** (high). Confirmed that the S3 `by_station` copy
  is stale. Corrected the access advice: NCEI's `/pub/` per-station copy is
  current and robots-allowed, which beats both the stale S3 copy and the
  service with undocumented limits.
- **Evidence:** [Access Data Service docs](https://www.ncei.noaa.gov/support/access-data-service-api-user-documentation),
  [`/pub/data/ghcn/daily/`](https://www.ncei.noaa.gov/pub/data/ghcn/daily/),
  [`by_station/`](https://www.ncei.noaa.gov/pub/data/ghcn/daily/by_station/)
  (first 3 KB of the listing),
  [S3 Boise file](https://noaa-ghcn-pds.s3.amazonaws.com/?list-type=2&prefix=csv/by_station/USW00024131),
  robots.txt for [NCEI](https://www.ncei.noaa.gov/robots.txt) and
  [S3](https://noaa-ghcn-pds.s3.amazonaws.com/robots.txt).

### NCEI Storm Events Database (bulk CSV)

NOAA NCEI, from NWS Storm Data.

- **Contents:** storm events from 1950 to 2026, by year: details (type,
  begin and end, county or zone, damage, narratives), locations (points)
  and fatalities; format PDFs and a README sit in the folder.
- **Coverage:** national, including Ada, Canyon and the ring's counties and
  zones.
- **Endpoint:** yearly gzip CSVs,
  `StormEvents_{details,locations,fatalities}-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz`.
  The latest 2026 files are dated Sept 18, 2026 (2025's Aug 19, 2026;
  2024's July 28, 2026), so older years are re-issued too.
- **Updates:** re-issued roughly monthly, with a lag. **Size:** about 10 MB
  a year compressed nationally; a few hundred rows a year for our counties.
- **Uses:** the valley's history of snowstorms, floods, wind and hail as
  lifecycles on the timeline; context for crash spikes and traffic
  disruptions.
- **Personas:** weather enthusiast, traffic researcher, fire and hazards
  watcher.
- **Needs:** lifecycles (`evt.event`), the Valley Feed, full replay.
  Effort S.
- **Risks:** the fatalities file describes people (age, sex, place of
  death): don't load it, or keep it to aggregates only. Reporting lags by
  months and past years are revised, so reload by the c-date.
- **License:** NOAA public data.
- **robots.txt:** NCEI disallows `/data*` and `/orders*`; this path is
  under `/pub/`, so it's allowed (re-fetched Oct 7).
- **Verified: confirmed** (high, raised). The listing confirms the file
  naming and the Sept 18, 2026 date; the verifier added that past years
  are re-issued.
- **Evidence:** [CSV folder](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/),
  [robots.txt](https://www.ncei.noaa.gov/robots.txt).

## Ideas by persona

From the research catalog; none is approved. The wider catalog of ideas
is [chapter 16](../16-ideas-and-personas.md). Where the verifier's
findings change an idea, the change is noted.

### Traffic researcher

- **Fog mornings and the recall theory** ([ch. 2](../02-treasure-valley-signal-system.md):
  in fog, video detection falls back to recall). Take every foggy morning
  since 2019 and replay the RTMA rapid-update visibility field, airport
  visibility and the GOES night-fog layer over the map, next to bus travel
  times and the key-camera videos. A card shows corridor minutes under
  1/4 mile and the bus delay against clear mornings at the same hour.
  *Corrected:* 1-minute visibility exists at BOI only; EUL and MAN give
  routine and 5-minute METARs. RTMA's archive starts in 2019, but
  RTMA-RU's start on AWS wasn't checked ⚠️. Sources: IEM, RTMA, GOES ABI,
  AWC. Needs: full replay, fields, readings, tracks (buses), the
  time-series card.
- **Weather at every crash, and sun glare.** Each COMPASS crash gets its
  precipitation type and rate (MRMS), visibility (RTMA), wind gust, and
  whether the sun was in the driver's eyes (the computed sun azimuth and
  elevation against the segment's bearing, counted only when GOES says the
  sky was clear). A Streets view colors segments by glare minutes per
  commute and overlays glare-time crashes. Sources: MRMS, RTMA, GOES ABI.
  Needs: fields, full replay, the layer system, evidence and review.

### Transit rider and traffic researcher

- **Snow-day replay.** The timeline highlights snow and freezing-rain hours
  (MRMS precipitation type, HRRR freezing rain, 511's pavement status);
  scrubbing through one shows snow falling over the 3D valley, buses
  slowing on their ribbons, and work zones, with a "route delay against a
  dry weekday" panel. Sources: MRMS, HRRR, NEXRAD Level III. Needs: full
  replay, tracks, fields, the 3D volume pass.

### Commuter

- **"Leave now?" card for a saved route.** Precipitation arriving in the
  next two hours (MRMS motion plus HRRR's 15-minute output), fog odds for
  tomorrow morning (NBM visibility, the TAF at BOI), and our own
  travel-time history under similar weather ("rainy weekday mornings add
  6 min on Eagle Rd"). Sources: MRMS, HRRR, NBM, AWC, the NOMADS filter.
  Needs: fields with an issue time, places and search (saved routes), the
  time-series card.

### Weather enthusiast (including the owner)

- **A living 3D sky.** Volumetric clouds over the 3D valley rebuilt each
  hour from HRRR cloud water and ice, moved to where GOES sees cloud, with
  tops from GOES cloud-top heights and bases from METAR ceilings. Rain and
  snow shafts and virga come from MRMS 3D reflectivity every 2 min; fog is
  a height-limited layer whose density comes from visibility; GLM flashes
  light the clouds from inside. Every element carries a badge (observed,
  analysed or model-reconstructed) with its age. Any past day can be
  replayed by fetching it from AWS on demand. *Corrected:* "any day since
  Oct 2020" holds for MRMS and HRRR, but GOES-West before January 2023
  means GOES-17 and other file names. Sources: HRRR, GOES ABI, MRMS, GLM,
  AWC, RTMA, the Boise soundings. Needs: the 3D volume pass (WebGL2 3D
  textures, ray-marching against the terrain), fields, full replay, the
  time bar.
- **KCBX scan scrubber.** Step sweep by sweep through the Boise radar's
  live volume as translucent cones over the terrain, switching between
  reflectivity, velocity, correlation coefficient and ZDR. Storm cells
  from the radar's storm-tracking product move along as tracks with ETA
  cards ("cell reaches downtown at 17:42"). *Corrected:* staying about
  15 s behind needs the current chunk prefix polled every 5–10 s; a 30–60 s
  poll gives 30–60 s latency. Sources: NEXRAD Level II and III. Needs: the
  3D engine (sweep meshes), tracks, fields, the Valley Feed.
- **Inversion and smog-season explorer.** A winter timeline of inversion
  strength and depth from the 12Z Boise sounding and HRRR, the KCBX wind
  profile, the fog top drawn in 3D as a lid over the valley, and counts of
  "valley under the lid" days each season. Sources: Boise soundings, HRRR,
  NEXRAD Level III, GOES ABI. Needs: readings (profiles), the 3D volume
  pass, the time-series card.
- **This day in valley weather** (also for local historians). Each day's
  card compares today with normal and with records (GHCN-Daily, back to
  the 1940s ⚠️) and lists past storm events on this date (NCEI Storm
  Events, IEM storm reports), with links to replay those since Oct 2020 in
  3D. Sources: GHCN-Daily, Climate Normals, Storm Events, IEM. Needs:
  lifecycles, the Valley Feed, full replay, the time-series card.

### Sky watcher

- **Tonight's sky.** A clear-sky outlook by hour for dark-sky spots in the
  ring (NBM sky cover, HRRR cloud layers, the GOES clear-sky mask right
  now), smoke in the column (HRRR-Smoke), and the moon's phase and
  position (computed), with a one-tap 3D view of the sky over the chosen
  spot at that hour. Sources: NBM, HRRR, GOES ABI. Needs: areas, places
  and search, fields.
- **Sky-phenomena alerts.** "Rainbow likely now" when the sun is under 42°
  and MRMS shows rain on the opposite side of the sky; "virga over the
  valley" when radar echoes aloft don't reach the ground; and, with the
  aircraft plugin, contrail forecasts at flight levels from RAP and HRRR
  humidity, checked against GOES. Sources: MRMS, RAP, HRRR, GOES ABI.
  Needs: the Valley Feed, fields, tracks (aircraft).

### Gardener

- **Sun-and-shade planner for a yard.** Hour-by-hour sun and shade through
  the year from the computed sun path, Overture building heights and lidar
  tree canopy, weighted by Boise's hourly cloudiness normals into expected
  sun hours per bed per month. A live layer shows real cloud shadows now,
  from GOES clouds traced toward the sun. Check first that Boise's normals
  have the hourly cloudiness elements ⚠️. Sources: Climate Normals, GOES
  ABI, HRRR. Needs: the 3D engine (shadow casting), the base map
  (buildings, terrain, canopy), places and search ("my yard").
- **Frost and rain for my yard.** A "frost tonight?" card (NBM odds of a
  low under 32 °F and 28 °F, RTMA cold pooling at dawn), first- and
  last-freeze odds (normals), a neighbourhood microclimate map (PRISM's
  800 m normals: bench against river bottom), and this week's rain in the
  yard (MRMS gauge-corrected rainfall next to nearby CoCoRaHS gauges).
  Sources: NBM, RTMA, Climate Normals, PRISM, MRMS, CoCoRaHS. Needs:
  fields, the time-series card, places and search.

### Farmer

- **Field weather board.** Rainfall per field from MRMS (checked against
  CoCoRaHS), hail swaths drawn over fields after storms (MRMS maximum hail
  size), frost and heat odds (NBM), a burn-day check (NBM mixing height
  and ventilation rate), land-surface temperature at dawn (GOES), and crop
  water use from AgriMet if Reclamation allows a collector. Sources: MRMS,
  CoCoRaHS, NBM, GOES ABI, AgriMet, PRISM. Needs: fields, areas, the layer
  system (field boundaries would come from a future farm plugin).

### Cyclist

- **Ride window for a saved route** (the Greenbelt or the foothills).
  Headwind and crosswind arrows along the route from RTMA and HRRR winds,
  rain timing from MRMS and HRRR's 15-minute output, heat stress (NBM
  WBGT), smoke at breathing height (HRRR-Smoke at 8 m), wet or icy
  pavement from 511's stations, then the best 2-hour window today.
  Sources: RTMA, HRRR, MRMS, NBM, the NOMADS filter. Needs: places and
  search (saved routes), fields, readings (511's road weather, from the
  `conditions` plugin).

### Hiker and camper

- **Trailhead and ridge outlook** (with the lands and trails plugins).
  Snow and freezing levels (NBM, the Boise sounding), thunderstorm and
  lightning odds (NBM, MRMS lightning probability), recent lightning near
  the trail (GLM, at km scale), and the nearest backcountry station's last
  two weeks (FEMS RAWS). A 3D view shows cloud bases against the
  ridgelines for the hike's hours. Sources: NBM, Boise soundings, MRMS,
  GLM, RAWS, HRRR. Needs: areas (the ring and the national forest), places
  and search (trailheads), the 3D volume pass.

### Fire and hazards watcher

- **Fire-weather board** (shared with a hazards plugin). Red-flag-style
  wind and humidity odds (NBM), dry lightning (GLM flashes where MRMS shows
  no rain), GOES fire detections every 5 min, the HRRR smoke plume in 3D,
  warnings as lifecycles (IEM VTEC, or the NWS API if the owner decides),
  and RRFS's 1.5 km fire-weather runs from Nov 3, 2026. Sources: NBM,
  GLM, GOES ABI, HRRR, IEM, RRFS, RAWS. Needs: lifecycles and the Valley
  Feed, the 3D volume pass, fields, areas.

### Wildlife watcher

- **Night migration over the valley.** From KCBX's dual-pol volumes,
  separate birds and insects (low correlation coefficient, clear air) from
  rain and show the nightly migration's intensity, direction and height
  above Boise each spring and fall, as a 3D "river of birds" in replay. A
  seasonal chart compares nights, with weather fronts marked. Later, a
  wildlife plugin could add deer-crossing risk when snow pushes mule deer
  down. Sources: NEXRAD Level II and III, HRRR. Needs: fields, the 3D
  volume pass, full replay, the time-series card.

### The owner (private `home` plugin)

- The owner's own weather station and an optional lightning receiver feed
  the private `home` plugin; the map compares the owner's readings with
  the nearest airport, RTMA and MRMS. Sources: Blitzortung, RTMA, MRMS.
  Needs: private plugins, readings.

## Design notes

The researcher's proposed design, with the verifier's corrections of
Oct 7 folded in and marked **Corrected**. Every structural choice here is
the owner's to make.

### How this fits what we have

- The `conditions` plugin already records readings from 511's 127
  road-weather stations (pavement, air, dew point, wind, precipitation,
  visibility, surface status) into `core.weather_station` and
  `obs.weather_reading`. Those tables are keyed by 511's station id, and
  the data stays internal.
- A `weather` plugin would add the atmosphere above and between those
  stations: radar, satellite, model and analysis grids, airport and other
  station observations, soundings, warnings and climate context.
- The "Fog at BOI" chip and the foggy-morning haze of
  [ch. 13](../13-visual-design.md) would get real inputs: METARs for the
  chip, the RTMA visibility field for the haze.
- **Proposed manifest:** `weather`, public. Republish: yes for
  NOAA-derived products (credit NOAA/NWS/NESDIS/NCEP and NSF Unidata, and
  label anything we modify as derived), IEM (public domain), PRISM (cite
  with the access date) and CoCoRaHS (CC BY 3.0, aggregated, no observer
  names). It depends on nothing; `conditions` is optional, to show 511's
  stations alongside. Lens: Sky (with aircraft) or a new Weather lens. For
  the owner to decide.

### Robots.txt and access (checked Oct 6–7, 2026)

The verifier re-fetched every robots.txt in the theme with our
User-Agent.

| Rule | Hosts |
|---|---|
| No rules (404) | Every NOAA S3 bucket tried (`unidata-nexrad-level2`, `unidata-nexrad-level3`, `noaa-mrms-pds`, `noaa-goes18`, `noaa-hrrr-bdp-pds` and the rest named above); `nomads.ncep.noaa.gov`; `mrms.ncep.noaa.gov` (after a redirect); `aviationweather.gov`; `data.cocorahs.org`; `prism.oregonstate.edu` and its data hosts; `www.weather.gov`; `forecast.weather.gov`; `radar.weather.gov`; `opengeo.ncep.noaa.gov`; `cdn.star.nesdis.noaa.gov`; MADIS; `wcc.sc.egov.usda.gov`. `api.synopticdata.com` answers 401, which also means no rules |
| Allowed, with conditions | IEM: Crawl-delay 120, and `/data/NIDS/`, `/data/nexrd2/`, `/data/model/`, `/archive/nexrad/`, `/archive/raw/snet/`, `/usage/`, `/tmp/` disallowed. NCEI: `/data*` disallowed (its normals, IGRA and GHCN trees), `/access/services/data/v1` and `/pub/` allowed. `wrcc-archive.dri.edu`: Crawl-delay 5. `www.star.nesdis.noaa.gov`: `/GOES/` allowed. `fems.fs2c.usda.gov` and `raws.dri.edu`: allow all |
| Disallowed | `api.weather.gov` (whole host); `www.spc.noaa.gov` (whole site); `weather.uwyo.edu` `/wsgi` and `/cgi-bin`; `www.usbr.gov` `/pn-bin` (AgriMet's data); `data.usbr.gov` `/rise/api`; `api.open-meteo.com` (whole host); `www.nohrsc.noaa.gov` (many paths, including `/products` and `*.nc`) |
| Gone | `alerts.weather.gov`: NXDOMAIN, a retired host. **Corrected:** the researcher had it as a network error |
| Unclear | `mapservices.weather.noaa.gov/robots.txt` redirects to an HTML page on weather.gov. That gives no parseable rules (our lenient parser would allow), but flag it before using those ArcGIS services |

**Corrected (NCEI):** `/pub/` is allowed and current, so IGRA
(`/pub/data/igra/`, updated Oct 6) and GHCN-Daily by station
(`/pub/data/ghcn/daily/by_station/`, updated Oct 6) can both be fetched by
script; IGRA's verdict changes to use (optional). The S3 GHCN by-station
copy is stale (Feb 9, 2025). There's no `/pub/data/normals/` (404), so
normals stay on S3.

**Corrected (MRMS):** NCEP's live copy moved from `/data/` to the site
root, in `/2D/`, `/3DRefl/`, `/3DRhoHV/`, `/3DZdr/`, `/ProbSevere/` and
`/RIDGEII/`. ProbSevere (storm objects) is worth a look for the
storm-cell tracks idea.

### A fourth time shape: fields

A structural proposal. Core has tracks, readings and lifecycles
([ch. 15 §15.1](../15-plugins.md#151-whats-core)). Weather is mostly
gridded frames over time (radar, satellite, model, analysis), sometimes
3D, sometimes forecasts with an issue time. The proposed contract:

- **`core.field_frame`** (metadata only, a hypertable): source, variable,
  level or levels, grid (CRS, origin, spacing, dimensions), valid start
  and valid end, issue time (null for observations), quantization (scale,
  offset, nodata), byte size and an archive path. **Corrected:** the
  researcher had a single valid time. Radar volumes span 4–7 min (their
  sweeps are at different times), GOES files carry a scan start and end,
  and accumulations (rainfall, MESH maxima) are windows; replay at
  one-second resolution next to buses needs the interval.
- **Payload files:** `$TVT_ARCHIVE/weather/<source>/<var>/YYYY/MM/DD/<time>.bin(.zst)`,
  or PNG-packed like terrain-RGB.
- **API:** `/api/<plugin>/fields?var&from&to&bbox` lists frames;
  `/api/<plugin>/field/<id>` returns the binary with a JSON header, or
  z/x/y PNG tiles for 2D drapes.
- **Player:** the same clock, with cross-fades or advection between frames.
  Forecasts replay as known at the time, by issue time.

How the rest of the weather data fits the existing shapes:
- readings: METARs, RAWS, AgriMet, CoCoRaHS; soundings are a profile
  variant of readings;
- lifecycles: warnings, storm events, storm reports;
- tracks: radar storm cells;
- point events: lightning flashes (readings, or zero-length lifecycles).

Other plugins would use fields too: smoke and air-quality grids (hazards),
snow (water), imagery years (history).

Separately, `core.weather_station` is keyed by 511's ids. Proposal:
`weather` owns a generic `core.met_station` (network, station id) and
`obs.met_reading` in SI units, with a view that merges 511's road stations
for display. The owner's decision.

### Ingest

- **No push needed:** poll anonymous S3 ListObjectsV2 for new keys (Level
  II chunks, Level III, MRMS, GOES). SNS push would need an AWS account
  (an owner action) and isn't necessary. **Corrected:** polling every
  30–60 s gives 30–60 s radar latency, not the 15 s promised for the scan
  scrubber. Poll only the current KCBX chunk prefix every 5–10 s (cheap),
  and everything else every 60 s.
- **Libraries beyond the standard library:**
  - GRIB2 (MRMS, HRRR, RAP, RTMA, NDFD) and NetCDF4/HDF5 (GOES, GLM) are
    impractical in standard-library Python.
  - Proposal: a separate weather ingest image with GDAL (already used by
    `basemap/imagery.py`) and numpy, or eccodes or wgrib2: an exception to
    the standard-library rule, like `gtfs-realtime-bindings`. Ranged GOES
    reads would add h5py and fsspec.
  - NEXRAD Level II and III parse with `bz2` and `struct`, but numpy makes
    them practical.
- **Subsetting:**
  - HRRR, RTMA and RAP have an `.idx` per file, so standard-library
    `urllib` Range requests can fetch single fields, then decoded from
    GDAL's `/vsimem/`.
  - NBM and PRISM are COGs: GDAL `/vsicurl/` or `/vsis3/` reads only the
    tiles over the ring.
  - The NOMADS grib filter cuts the ring on the server for HRRR 2D,
    RTMA-RU, NBM and RAP, at KB a request, within 120 hits a minute per
    IP. **Corrected:** not for RRFS, REFS or URMA. RRFS subsets mean
    `.idx` Range requests, which count toward the same 120 hits a minute
    (shared with `ftp.ncep` and `ftpprd`), or the AWS buckets
    `noaa-rrfs-pds` (prototype) and `noaa-rrfs-ops` (operational).
  - MRMS (`.grib2.gz`) really is whole files only: gate MRMS 3D on
    precipitation in the ring, using the 0.2 MB PrecipFlag or composite.
  - GOES: the researcher planned whole files, taking band 2 only by day
    every 10–15 min and leaning on the 2 km bands and L2 products.
    **Corrected:** the files are HDF5-chunked, so h5py with fsspec, or
    GDAL over `/vsis3/` with HDF5 support, may read only the chunks over
    the ring ⚠️ (chunk layout not inspected). Test that before accepting
    66 MB per band-2 frame.
  - **Corrected (HRRR 3D):** don't default to `wrfnat`. `wrfprs` has the
    five hydrometeors on 40 isobaric levels, 25 hPa apart (about 250 m near
    the ground): about 38–110 MB an hour by Range, against 130–380 MB from
    `wrfnat`, and HRRR-Zarr's `prs` makes it one to four chunks per field.
    The costs: no FRACCC, no 3D smoke, and below-ground levels (about
    1013–925 hPa over the valley) to mask with the surface pressure.
    Suggested split: clouds and winds from `prs` or Zarr hourly, `wrfnat`
    only on smoke days. That cuts HRRR's 3–9 GB a day to about 1–3 GB.
- **Grids:** crop each source on its own grid and keep its grid metadata,
  rather than reprojecting at ingest. For 3D, build one weather cube per
  time step in UTM 11N (`ingest/utm.py` exists), e.g. the ring at 1 km ×
  250 m up to 12 km above sea level: about 140 × 155 × 48 cells (the
  verifier's figure: 137 × 156 × 48, about 1 MB as R8).
- **Lazy archive:** NOAA's buckets already hold the history (NEXRAD from
  the 1990s ⚠️, HRRR from 2014, MRMS from Oct 14, 2020, RTMA from 2019,
  GOES-18 from 2022). Record compact derived frames live, and add a
  by-hand `python3 -m ingest weather-backfill --day` that re-fetches raw
  files for an older day. Keep our derived frames permanently: bucket
  names change (NEXRAD Level II moved in 2025) and NODD hosting depends on
  NOAA's agreements ⚠️. **Corrected:** Level II backfills before about
  2008 need a Message 1 decoder and `.gz` handling, and chunk volume
  numbers cycle 0–999; Level III starts March 2, 2022 for CBX; GOES-West
  before January 2023 means GOES-17 (`noaa-goes17` ⚠️) and other file
  names; RTMA-RU's start on AWS wasn't checked.
- **Model reader:** keep it abstract: HRRR now; RRFS v1 from Nov 3, 2026
  for the 1.5 km fire nest and the ensembles; RRFS v2 (MPAS) expected to
  replace HRRR and RAP around 2027–28 ⚠️.
- **Corrected (IEM's budget):** Crawl-delay 120 allows at most 720
  requests a day for every IEM use together, so the researcher's plan of
  warnings, storm reports and forecast discussions every 2–5 min can't
  all fit. One IEM queue with a fixed plan, for example:
  - warnings every 5 min (288 a day);
  - storm reports every 15 min (96);
  - forecast discussions hourly (24);
  - soundings twice a day;
  - the rest left for backfills.

  `asos.py` also has its own limits: a per-IP throttle (HTTP 429), a 1-s
  throttle since April 2026, and 1,000 station-years per request (HTTP
  422).
- **Corrected (quirks to model):** NDFD's `opnl/` and `expr/` are
  latest-only, so record them or rebuild from `wmo/`; NBM's version
  folders change (v3.2 to v5.0 side by side); PRISM's daily values are
  revised; Storm Events re-issues past years (reload by the c-date).

### What the plugin would record (proposal)

| Cadence | What | Stored |
|---|---|---|
| About 15 s to 7 min | KCBX Level II volumes, decoded live into derived products: low-level reflectivity, hydrometeor class, a biology mask, a 3D reflectivity cube. Raw kept only if the owner wants; otherwise re-fetched from AWS | Raw, if kept: 1.2–3 GB/day |
| Every volume (about 4–7 min) | Level III N0B, N0G, HHC, DPR, EET, DVL, NML, NVW, NST, kept raw | 0.2–0.4 GB/day |
| 2 min | MRMS 2D cropped to the ring: PrecipRate, PrecipFlag, SeamlessHSR, QPE 15-min and 1-h, EchoTop, MESH, bright-band heights, LightningProbability | 10–50 MB/day. **Corrected:** 34 MB/day raw per field, so this assumes heavy compression on dry days |
| 2–10 min, only while it's precipitating in the ring | MRMS 3D reflectivity | 0–300 MB/day |
| 5 min | GOES-18 cropped: bands 7 and 13, ACM, ACHA2KM, FDC, ADP; band 2 by day and COD as the researcher planned. **Corrected:** LST hourly; DSR from the full-disk DSRF | 10–20 MB/day. **Corrected:** nearer 20–40 MB/day if band 2 is kept |
| 20 s | GLM flashes in the ring | KB |
| 15 min | RTMA-RU (VIS, CEIL, TMP, DPT, WIND, GUST, TCDC) through the NOMADS filter | About 1–3 MB/day |
| Hourly | HRRR f00 3D cloud set (CLMR, CIMIXR, RWMR, SNMR, GRLE, FRACCC, MASSDEN, U/V, TMP, plus heights) by Range from AWS. With the corrected split, FRACCC and 3D MASSDEN come only from `wrfnat` on smoke days | 50–150 MB/day stored; 3–9 GB/day downloaded from `wrfnat`, about 1–3 GB/day with the `wrfprs` split |
| Hourly | HRRR f01–f18 2D (visibility, ceiling, precipitation type, PRATE, gust, smoke) through the NOMADS filter | Small |
| Hourly, 4 runs a day kept | NBM, about 20 elements × 36 h, by COG tile reads | About 20 MB/day raw, a few MB compressed (**corrected** from "a few MB/day") |
| 5 min | METARs for KBOI, KMAN, KEUL, KMUO and KONO (AWC), into readings | Under 2 MB/day |
| Twice a day | The Boise sounding (IEM) | Under 0.1 MB/day |
| Within IEM's budget | Warnings as lifecycles (IEM VTEC, unless the owner OKs api.weather.gov), storm reports, forecast discussions | KB/day |
| Daily | CoCoRaHS, GHCN-Daily (NCEI), PRISM daily (provisional versions tracked) | Small |
| Once, then yearly | Normals and Storm Events history | Small |

**Derived, to join with traffic:** per-corridor (not per-segment) exposure
aggregates, every 15 min and per hour. Examples: minutes under 1/4-mile
visibility; snow and freezing-rain minutes; glare minutes (the sun's
azimuth within about 25° of the segment's bearing, the sun under about
20°, GOES clear; thresholds to tune ⚠️); maximum gust; smoke. Per-segment
values come on demand from the fields: storing all 38,727 segments every
5 min would be about 11 million rows a day.

**Totals (estimates):** about 10–25 GB a day downloaded on a typical day
(40+ on stormy days with frequent 3D), or roughly 5–15 GB with the
corrected HRRR split; about 0.2–0.7 GB a day stored (70–250 GB a year)
without raw Level II, plus 0.45–1 TB a year if raw Level II is kept. This
needs the owner's disk and bandwidth plan.

### Drawing real weather in 3D

It would use the WebGL2 custom layer `#lib/scene` (renderingMode `'3d'`).
The 3D sources are also in [weather-3d.md](weather-3d.md).

- **Volume:** WebGL2 3D textures (R8 or RG8) per field per frame, about
  1 MB raw for the ring's cube, 50–300 KB compressed, ray-marched in the
  fragment shader at half resolution and upsampled, with heights scaled by
  the live terrain exaggeration (the `exaggeration()` hook in
  [ch. 14](../14-ui-v2.md)), lazy-loaded like the rest of the scene
  engine, aiming at a few ms a frame ⚠️. WebGL2 guarantees 3D textures of
  at least 256 a side, so the cube fits.
- **Corrected (depth):** a MapLibre custom layer in `'3d'` mode shares the
  depth buffer for depth testing but can't sample it as a texture, so
  "stop at the terrain or building" needs either marching against the DEM
  heightfield in the shader (sampling the terrain-RGB tiles already
  loaded, scaled by `exaggeration()`) or our own depth pre-pass into an
  offscreen framebuffer. Budget for it: it's the main technical risk of
  the volume pass.
- **Clouds:**
  - Start from HRRR cloud water plus ice, turned into extinction with
    assumed effective radii (about 10 µm for water, 30 µm for ice ⚠️).
  - Correct the horizontal mask with GOES ACM: drop model cloud where GOES
    is clear; add a thin layer where GOES is cloudy but the model is
    clear, using ACHA tops.
  - Set bases from METAR ceilings and RTMA's CEIL.
  - Add procedural detail noise for looks, badged "reconstructed".
  - Light with a Henyey-Greenstein phase function and Beer-Lambert
    extinction, the sun from a computed solar position (NOAA SPA-style)
    and a simple Rayleigh/Mie sky; march toward the sun into a 2D
    cloud-shadow texture draped on the terrain, which gives gardeners real
    cloud shadows.
  - **Corrected:** COD is optical depth, not thickness; turning it into a
    geometric depth needs an assumed water content, so badge those layers
    "reconstructed". ABI's COD is mainly a daytime retrieval ⚠️. From
    GOES-West, cloud tops appear displaced about 1.4 × their height (about
    7 km for a 5 km top); from GOES-East about 2.1 ×. East–West stereo
    heights at 2 km pixels would be coarse: a stretch goal.
- **Precipitation:** MRMS 3D reflectivity turned into rates with Z-R and
  Z-S relations; type from PrecipFlag, the bright-band heights and HRRR's
  wet-bulb 0 °C height; particle streaks or flakes near the camera,
  carried by HRRR winds; virga where echoes aloft don't reach the ground;
  KCBX Level II sweeps as optional translucent cones.
- **Fog:** when RTMA or a METAR shows fog, a height-limited layer with
  extinction σ = 3.0 / visibility. **Corrected:** the researcher used
  Koschmieder's 3.912 / V (a 2% contrast threshold); ASOS and RTMA report
  the meteorological optical range (5%), and 3.912 would make fog about
  30% denser than observed. The top comes from the 12Z sounding's
  inversion, HRRR's low-level cloud water or the GOES fog area. Boise's
  winter valley fog is often a few hundred metres thick ⚠️.
- **Smoke:** HRRR's 3D MASSDEN (`wrfnat`) as a brown haze, plus GOES ADP
  outlines.
- **Lightning:** GLM flashes as brief glowing pulses inside the cloud
  volume. **Corrected:** MRMS's NLDN products are gridded average flash
  densities over 1, 5, 15 or 30 min, and GLM's flashes are total
  lightning with several km of uncertainty, so neither places a ground
  strike. Draw strikes as density-weighted random bolts badged
  "reconstructed", or not at all. NLDN redistribution is still ⚠️
  (Vaisala-derived).
- **Honesty:** every weather element shows its source, age and kind
  (observed, analysed, model, reconstructed), and there's no silent
  fallback between sources, in line with the rule that if a layer isn't
  built, the app says so.

### Licensing additions (verifier)

- The AWS registry's RRFS page now describes NODD data as a CC0-1.0
  dedication; the other NOAA pages use the older wording (open, credit
  requested). Both allow republishing with credit.
- MADIS: only the mesonet, hydrological, aircraft and radiometer sets are
  restricted. Showing them publicly needs NOAA's notification and source
  credit, and NOAA-only mesonet data may never be public.
- Synoptic's redistribution and token claims weren't found on its pages
  ⚠️; the verdict (avoid) is unchanged.
- The NWS API docs say API keys are planned; getting one would be an owner
  action if the owner ever opts in.
- CoCoRaHS: CC BY 3.0 for the data, CC BY 4.0 for the site; keep observer
  names out.

### Ethics and privacy

Weather is about the environment, not people, with these exceptions:
- CoCoRaHS stations are at volunteers' homes: no observer names, and
  rounded or aggregated locations.
- CWOP and other personal weather stations: avoid, or aggregate only.
  Weather Underground- and Ambient-type networks are off-limits by their
  terms (⚠️ not re-read in this pass).
- The Storm Events fatalities file describes people: skip it, or
  aggregate only.
- Radar biology is birds and insects, never people.
- No Google, Waze, TomTom, HERE or Mapbox weather or traffic products are
  needed.

### Suggested order (for the owner to choose)

1. Airport observations: AWC live, plus an IEM backfill for the fog study
   (the researcher proposed back to 2000; the 1-minute archive's start
   wasn't checked ⚠️). **Corrected:** 1-minute visibility at BOI only;
   routine and 5-minute METARs at EUL, MAN and MUO. Decide the warnings
   route.
2. The fields contract, with MRMS 2D (rate, type, rainfall, SeamlessHSR) as
   the first gridded layer and replay.
3. RTMA-RU visibility and ceiling, plus the GOES fog and clear-sky
   composites (the fog study and the Normal lens's haze).
4. KCBX Level III live; Level II decoded on demand (sweeps, biology).
5. HRRR 3D plus the volumetric renderer (clouds, precipitation, fog,
   smoke, lightning).
6. NBM persona cards (frost, burn day, ride window, trail outlook).
7. Climate context: normals, GHCN, PRISM, CoCoRaHS, Storm Events.

## Open questions

For the owner, one at a time. Updated with the verifier's findings.

1. **api.weather.gov:** its robots.txt disallows the whole host for every
   agent, but NWS's docs invite applications. Should we (a) treat it as
   off-limits and use NDFD and NBM on AWS for forecasts, plus IEM for
   warnings and forecast discussions; (b) ask NWS whether robots.txt is
   meant for API clients; or (c) write an explicit API-client exception
   into CLAUDE.md? Our rules currently mean (a). Since `alerts.weather.gov`
   is retired, CAP alerts exist only on api.weather.gov.
2. **Libraries:** may the weather plugin have its own ingest image with
   dependencies beyond the standard library (GDAL and numpy, perhaps
   eccodes or wgrib2) to decode GRIB2, NetCDF4 and COGs? The basemap tools
   already use GDAL. *Added by the verifier:* should GOES be fetched by
   ranged HDF5 chunk reads, which would add h5py and fsspec?
3. **Fields:** should core gain a fourth time shape, fields (gridded 2D or
   3D frames over time, with valid start and end and an issue time for
   forecasts), or should gridded data stay private to the plugin?
4. **Disk and bandwidth:** about 10–25 GB a day downloaded (roughly 5–15
   with the HRRR `wrfprs` split) and 0.2–0.7 GB a day stored (70–250 GB a
   year), plus 0.45–1 TB a year if raw KCBX Level II is kept. A lazy
   archive (re-fetch raw from NOAA's buckets on demand), or keep raw?
5. **Areas:** the valley box for 1 km products and the regional ring for
   radar, satellite and models. Do we also want a larger "weather context"
   area (e.g. 300 km) so replay can show storms and smoke approaching?
6. **IEM's budget** (added by the verifier): how to split IEM's at most 720
   requests a day between warnings, storm reports, forecast discussions,
   soundings and backfills.
7. **AgriMet:** robots.txt disallows `/pn-bin` and the RISE API. Should the
   owner ask Reclamation for permission to collect the Boise, Boise
   Fairgrounds, Nampa and Parma stations (and Ontario and Grand View in
   the ring)? *Answered on verification:* a Parma station exists (PMAI,
   since 1986).
8. **RAWS history:** does the owner want a FEMS (Login.gov) account for the
   full RAWS history, or are the public last two weeks enough? Synoptic's
   free tier needs a .edu address, and its paid tiers suit us poorly.
9. **Stations:** should 511's road stations and the new stations share one
   readings table with a network column (`core.weather_station` is keyed
   by 511's id today)?
10. **Republishing:** is a public weather layer wanted now (NOAA-derived
    data may be republished with credit), or tailnet-only like the rest
    for the moment?
11. **Private `home` plugin:** is the owner interested in a personal
    weather station, a Blitzortung lightning receiver, or both?
12. **Wildlife:** should we derive bird migration ourselves from KCBX Level
    II, or should someone ask Cornell's BirdCast about using its county
    migration data (terms not found)?
13. **Theme boundaries:** who owns smoke and air quality (HRRR-Smoke, GOES
    ADP, AirNow), fire detections (GOES FDC, FIRMS) and snow (SNOTEL,
    NOHRSC): weather, a hazards plugin or a water plugin?
14. **Fog study:** which threshold and corridors define it (e.g. visibility
    under 1/4 mile at BOI, or in RTMA cells along the key corridors,
    6–9 am)?
15. **HRRR-Zarr:** *answered on verification:* the University of Utah's
    copy holds only the `prs` and `sfc` groups (no native levels), current
    to Oct 5, 2026, in 150 × 150 chunks. What's left is its terms: no
    license text was found ⚠️.

No longer open: IGRA doesn't need the owner, since NCEI's `/pub/` copy is
robots-allowed.

### Still unverified after the Oct 7 check

KCBX's coordinates; the researcher's byte sizes and timings for Level II,
GOES, GLM and MRMS (listings not repeated); IEM's API endpoint names and
mosaic start dates; PRISM's revision count; NDFD's grid spacing; whether
RAWS is in MADIS's restricted mesonet set.
