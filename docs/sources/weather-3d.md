# weather-3d sources (researched Oct 7, 2026)

What it would take to draw the valley's real weather in 3D: clouds, fog,
precipitation, lightning and smoke reconstructed as volumes and geometry
over our MapLibre 6 map, in our own WebGL2 scene engine, synced to the
replay clock. The area is Ada and Canyon counties plus the proposed regional
ring, for storms and smoke that come from around the valley. This file
covers the data (radar, models, satellite, ground observations, smoke), the
code and rendering references that would turn it into pictures, and the
design the research proposed. It is the 3D slice of the weather research:
the wider weather sources (stations, forecasts, climate) are in
[weather.md](weather.md). The owner's idea is in [chapter 16
§16.5](../16-ideas-and-personas.md#165-weather-in-3d-the-owners-idea-oct-7),
and the sources for all the new plugins are summarised in [chapter
17](../17-sources-for-new-plugins.md).

**Status:** research only. Nothing here is approved or decided; sources go
to the owner one at a time ([SOURCES.md](../SOURCES.md)). Every entry was
checked on Oct 7 against the publisher's own pages, bucket listings,
robots.txt and terms (a few file sizes and robots results date from Oct
5–6): 16 entries were confirmed as researched and 15 corrected, and each
entry says which. ⚠️ marks anything resting on general knowledge, memory, an
estimate or a secondary source. Effort is the research's rough size: S, M or
L.

**Terms used here:**

- **NODD:** NOAA Open Data Dissemination, which publishes NOAA data in
  public AWS buckets. Its registry pages say the data are "open to the
  public and can be used as desired"; attribution is requested, and data
  we've changed must not be presented as the original.
- **The ring:** the regional ring proposed, not yet decided, in
  [DECISIONS](../DECISIONS.md): about 117.30° W to 115.60° W and 42.90° N to
  44.30° N (about 140 × 155 km), taking in Emmett, Mountain Home and
  Ontario. The research used it as its box.
- **Verdicts:** **use** (fits our rules as described), **internal only**
  (use, but don't republish), **needs owner action** (a key, a request or a
  decision comes first), **avoid**.
- **Core pieces:** the shared platform parts from [chapter
  15](../15-plugins.md) and [chapter 16
  §16.4](../16-ideas-and-personas.md#164-shared-core-pieces-serve-almost-every-persona)
  (readings, lifecycles and tracks contracts, the 3D engine, full replay,
  the layer system). The **fields contract** (gridded 2D and 3D data over
  time) is new: the research proposes it as a fourth time shape (open
  questions).
- **Weather worker image:** a proposed separate container with scientific
  Python (numpy, ecCodes and so on), which would be an exception to the
  ingest's standard-library-only rule (open questions).
- **Bricks:** our own cropped, encoded volume frames for the browser.
- **VCP:** a radar's volume coverage pattern, the set of tilts it scans; it
  changes with the weather.

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| [MRMS](https://registry.opendata.aws/noaa-mrms-pds/) | NOAA NSSL and NCEP, on AWS (NODD) | Observed 3D radar on 33 levels, dual-pol, precipitation type, melting layer, echo tops, hail, lightning density; about 1 km, 2 min | S3 HTTPS; one whole-CONUS GRIB2 file per level | None | NODD: "can be used as desired"; credit, label as derived | No rules | Use | Corrected |
| [NEXRAD Level II, KCBX](https://registry.opendata.aws/noaa-nexrad/) | NWS Radar Operations Center, on AWS (NODD, Unidata) | The Boise radar's full polar volumes, dual-pol, birds and insects | S3; about 6 MB a volume | None | NODD | No rules on AWS; IEM's mirror disallowed | Use | Corrected |
| [NEXRAD Level 3, KCBX](https://registry.opendata.aws/noaa-nexrad/) | NWS, on AWS (NODD, Unidata) | Hydrometeor classes, melting layer, echo tops, VIL, VAD winds | S3; files of a few KB | None | NODD | No rules | Use | Confirmed |
| [HRRR native levels](https://registry.opendata.aws/noaa-hrrr-pds/) | NOAA NCEP and GSL, on AWS (NODD) | Model 3D cloud water, ice, rain, snow, graupel, cloud fraction, smoke, wind; 3 km, hourly, to 48 h | S3 byte ranges from the `.idx` | None | NODD; modified data not presented as original | No rules; NOMADS 120 hits a minute | Use | Corrected |
| [hrrrzarr](https://mesowest.utah.edu/html/hrrr/) | University of Utah MesoWest, on AWS | HRRR on pressure levels (clouds, wind, temperature) in small Zarr chunks | S3 chunk GETs | None | Listed on NODD's HRRR page; MesoWest states none | No rules | Use | Corrected |
| [RRFS v1](https://registry.opendata.aws/noaa-rrfs-ops/) | NOAA NCEP | HRRR's successor, operational Oct 14, 2026: pressure-level clouds to 84 h, a fire-weather nest; no 3D smoke | S3 or NOMADS; byte ranges | None | CC0 (NODD registry) | No rules | Use | Corrected |
| [RTMA rapid update](https://registry.opendata.aws/noaa-rtma/) | NOAA NCEP, on AWS (NODD) | 2.5 km surface analysis with visibility, ceiling and cloud cover every 15 min | S3 byte ranges | None | NODD | No rules | Use | Corrected |
| [GOES-18 ABI Level 2](https://registry.opendata.aws/noaa-goes/) | NOAA NESDIS, on AWS (NODD) | Cloud-top height, clear-sky mask, phase, cloud layers, smoke and dust, fire, surface sunshine; 5 min | S3 NetCDF | None | NODD (data.gov's CC0 record has contradictory flags) | No rules | Use | Corrected |
| [GOES-18 ABI imagery](https://registry.opendata.aws/noaa-goes/) | NOAA NESDIS, on AWS (NODD) | 16 bands: cloud-top texture and our own night-fog product | S3 NetCDF; about 54 MB a file | None | NODD; credit NOAA/NESDIS | No rules | Use | Confirmed |
| [GOES-18 GLM](https://registry.opendata.aws/noaa-goes/) | NOAA NESDIS, on AWS (NODD) | Total lightning (in-cloud and ground) every 20 s | S3 NetCDF | None | NODD | No rules | Use | Confirmed |
| [AWC Data API](https://aviationweather.gov/data/api/) | NWS Aviation Weather Center | METAR cloud layers, ceiling and visibility at 5 airports | Keyless JSON; 100 requests a minute | None | None stated; US government work ⚠️; "keep requests limited" | No rules | Use | Confirmed |
| [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/json/) | Iowa State University | ASOS history (and 1-minute), satellite cloud product, Boise soundings, NWS warning archive | Keyless HTTP; one request per 120 s | None | "Any lawful purpose", as-is | Crawl-delay 120; these paths allowed | Use | Corrected |
| [511 road-weather stations](../SOURCES.md) | ITD, via the 511 Idaho API | Already collected: visibility, precipitation, road state at 127 stations | In hand | Free key | Not republished | Not applicable (keyed API) | Internal only | Confirmed |
| [Our camera archive](../11-camera-validation-layer.md) | Our recordings of ACHD and ITD cameras via 511 | A visual check of rendered fog, rain and snow | In hand | None | Images not republished | Not applicable | Internal only | Confirmed |
| [HMS smoke and fire](https://www.ospo.noaa.gov/products/land/hms.html) | NOAA NESDIS OSPO | Analyst-drawn smoke outlines in 3 densities, fire points; twice a day | Keyless HTTPS directory | None | None stated ⚠️; disclaimer | No rules | Use | Corrected |
| [AirNow](https://docs.airnowapi.org/faq) | US EPA and partners | Ground PM2.5 and AQI | API with a key, or hourly files | Free key | EPA guidelines: preliminary, not altered, signed form | No rules | Needs owner action | Corrected |
| [GOES fog and low stratus](https://vlab.noaa.gov/web/towr-s/goes-16-fog-and-low-stratus) | NOAA NESDIS (CIMSS algorithm) | Fog and low-cloud probabilities and depth | Satellite broadcast (SBN) and AWIPS only | Partnership | Not checked | No public endpoint | Avoid | Confirmed |
| [NWS API](https://api.weather.gov/) | NWS | Forecasts, gridpoints, alerts | Keyless JSON | None | US government (not examined) | `Disallow: /` | Needs owner action | Confirmed |
| [nowCOAST, SPC, UWyo, NCEI](https://nowcoast.noaa.gov/) | NOAA; University of Wyoming | Map services, outlooks, soundings, data paths | Web | None | Not examined | Disallowed on the paths we'd use | Avoid | Confirmed |
| [GSL HRRR-Smoke site](https://rapidrefresh.noaa.gov/hrrr/HRRRsmoke/) | NOAA GSL | Smoke forecast graphics | Web | None | None stated | Disallows `/hrrr/HRRRsmoke/` | Avoid | Corrected |
| [ecCodes, cfgrib, xarray](https://github.com/ecmwf/eccodes) | ECMWF; xarray developers | GRIB2 decoding | PyPI, conda-forge | None | Apache-2.0 | Not applicable | Use | Confirmed |
| [Herbie](https://github.com/blaylockbk/Herbie) | Brian Blaylock and contributors | Model subsets by `.idx` byte ranges | PyPI | None | MIT | Not applicable | Use | Confirmed |
| [Py-ART, xradar, MetPy](https://github.com/ARM-DOE/pyart) | ARM/DOE; openradar; Unidata | Radar reading, QC and gridding; Level 2 and 3 readers | PyPI, conda | None | BSD-style (Argonne); MIT; BSD-3-Clause | Not applicable | Use | Corrected |
| [vol2bird, bioRad](https://github.com/adokter/vol2bird) | Adriaan Dokter and contributors | Bird-migration profiles from radar | Source; CRAN | None | MIT (linked libraries may differ ⚠️) | Not applicable | Use | Confirmed |
| [Satpy, Supercell Wx](https://github.com/pytroll/satpy) | Pytroll; Dan Paulat | GOES parallax correction; a radar decoding reference | PyPI; GitHub | None | Apache-2.0; MIT | Not applicable | Use | Corrected |
| [three-geospatial](https://github.com/takram-design-engineering/three-geospatial) | Takram | Cloud and atmosphere rendering techniques to port | GitHub, npm | None | MIT | Not applicable | Use (techniques) | Corrected |
| [Rendering references](https://github.com/sebh/UnrealEngineSkyAtmosphere) | three.js; Cesium; Sébastien Hillaire; NCAR | Volume ray-marching, voxels, sky lookup tables, offline checks | GitHub | None | MIT; Apache-2.0; MIT; BSD-3-Clause | Not applicable | Use | Confirmed |
| [webgl-wind](https://github.com/mapbox/webgl-wind) | Mapbox (Vladimir Agafonkin) | The GPU particle-wind technique | GitHub | None | ISC | Not applicable | Use | Confirmed |
| [SunCalc](https://github.com/mourner/suncalc) | Vladimir Agafonkin and contributors | Sun and moon position | npm | None | BSD-2-Clause | Not applicable | Use | Corrected |
| [MapLibre sky and fog](https://maplibre.org/maplibre-style-spec/sky/) | MapLibre | Sky and distance-fog style properties | Already a dependency | None | BSD-3-Clause | Not applicable | Use | Confirmed |
| [Shadertoy; Mapbox GL JS v2+](https://github.com/mapbox/mapbox-gl-js/blob/main/LICENSE.txt) | Shadertoy authors; Mapbox | Cloud and rain shaders and effects | Web | None | Mapbox proprietary; Shadertoy CC BY-NC-SA 3.0 ⚠️ | Shadertoy: Cloudflare challenge | Avoid (never copy) | Confirmed |

## Radar

### MRMS (Multi-Radar Multi-Sensor)

NOAA NSSL and NWS NCEP, distributed by NODD on AWS
([registry](https://registry.opendata.aws/noaa-mrms-pds/)). **Use**;
confidence high; effort M. Verified: **corrected**.

- **Contents** (CONUS):
  - 3D: `MergedReflectivityQC` on 33 constant-altitude levels from 0.50 to
    19.00 km MSL (0.25 km steps to 3 km, 0.5 km to 9 km, 1 km to 19 km), in
    dBZ, every 2 min. `MergedRhoHV` and `MergedZdr` on the same 33 levels
    every 5 min, CONUS only.
  - 2D on the same 0.01° grid (about 1.11 × 0.81 km at 43.6° N):
    `PrecipFlag` (2 min), `PrecipRate` (mm/h), `BrightBandTopHeight` and
    `BrightBandBottomHeight` (m above ground, 2 min), `Model_0degC_Height`
    (m MSL, hourly), `EchoTop_18/30/50/60` (km MSL), MESH (mm) with
    `MESHMax30min` to `1440min` swaths, POSH, VIL, composites,
    `RadarQualityIndex`, QPE, NLDN cloud-to-ground density
    `NLDN_CG_001/005/015/030min_AvgDensity` (flashes/km²/min; the 1-minute
    product updates every minute) and `LightningProbabilityNext30minGrid`
    and `Next60minGrid` (%, 2 min).
  - `PrecipFlag` codes: −3 no coverage, 0 none, 1 warm stratiform rain, 3
    snow, 6 convection, 7 hail, 10 cool stratiform rain, 91 and 96 tropical;
    2, 4, 5, 8 and 9 are unused. There's no freezing-rain or sleet class.
  - Nodata (corrected): 3D products use −99 for missing and −999 for no
    coverage; 2D products use −1 and −3 ([NSSL
    table](https://www.nssl.noaa.gov/projects/mrms/operational/tables.php)).
  - The 0.50 and 0.75 km levels sit at or below the valley floor (about
    0.66–0.85 km MSL), so they're effectively empty here.
- **Coverage:** CONUS, so Ada, Canyon and the whole ring. The AWS archive
  starts 2020-10-14 (first date folder confirmed). Over the valley the data
  come essentially from the Boise radar KCBX, about 14 km south of downtown
  (bearing 191°; the research had said south-southeast). KCBX's coordinates
  were taken from memory ⚠️.
- **Endpoint:** keyless HTTPS GET from `s3://noaa-mrms-pds` (us-east-1):
  `CONUS/<Product>_<HH.HH>/<YYYYMMDD>/MRMS_<Product>_<HH.HH>_<YYYYMMDD-HHMMSS>.grib2.gz`
  (confirmed). Each file is one gzipped whole-CONUS level, so there's no
  byte-range subsetting. New files are announced on the SNS topic
  `arn:aws:sns:us-east-1:123901341784:NewMRMSObject`. The same files are on
  `mrms.ncep.noaa.gov/data`; AWS is preferred. Decoding needs ecCodes; MRMS
  uses local GRIB discipline 209, so parameter names come from the filename
  or NSSL's tables on GitHub
  (`NOAA-National-Severe-Storms-Laboratory/mrms-support`) ⚠️ (decoding
  details unverified).
- **Updates:** 2 min (reflectivity, flags, rates, bright band, echo tops,
  MESH, lightning probability); 1 min (NLDN 1-minute density); 5 min (3D
  RhoHV and Zdr); hourly (model freezing level).
- **Size** (measured Oct 5): a 3D level is about 1.10 MB gzipped
  (1,095,288–1,104,093 bytes), a composite 1.42 MB, `PrecipFlag` 0.20 MB. A
  26-level volume up to 12 km is about 28 MB. Cropped to the ring, 170 × 140
  × 26 bytes is 619 KB raw (arithmetic confirmed), about 50–200 KB
  compressed with echoes ⚠️ (estimate); empty frames are skipped.
- **License:** NODD: "open to the public and can be used as desired".
  Attribution requested; label our renders as derived.
- **robots.txt** (Oct 6–7): `noaa-mrms-pds.s3.amazonaws.com` 404 NoSuchKey,
  so no rules (re-checked); `mrms.ncep.noaa.gov` 301 to `/robots.txt/`, then
  404 (no rules); `www.nssl.noaa.gov` `User-agent: *` with an empty Disallow
  (all allowed).
- **Use cases:** the MVP's observed 3D precipitation volume, ray-marched;
  rain, snow and mixed phase by height (`PrecipFlag`, bright band, 0 °C
  height, with HRRR temperature in inversions); hail cores (MESH, Zdr and
  RhoHV); echo-top shells for storms; ground lightning from NLDN density
  cells; a radar-blind and low-quality mask, for honesty; a rain-arrival
  nowcast by advection; weather history for crash replay since Oct 2020.
- **Personas:** fire and weather watcher, commuter, cyclist, hiker and
  camper, farmer, traffic researcher, sky watcher.
- **Core pieces:** fields contract, 3D engine, full replay, layer system,
  weather worker image (ecCodes, numpy).
- **Risks:**
  - Bandwidth: about 4 GB a day at 10-minute frames and 20 GB a day at 2
    minutes while echoes are present. Gating on `PrecipFlag` every 10 min
    costs about 30 MB a day.
  - MRMS's quality control removes biological echoes; use Level II for
    birds.
  - What the radar sees (4/3-earth model, KCBX antenna at 3,172 ft from the
    NWS list): the 0.5° beam centre is 1.10 km MSL over downtown, 1.15 over
    Meridian, 1.25 Nampa, 1.43 Caldwell, 1.52 Emmett, 1.69 Mountain Home and
    2.10 Ontario (confirmed).
  - The gap aloft (corrected): the 19.5° top tilt reaches about 6.0 km MSL
    over downtown and 7.5 km over Meridian (the research's 5.7 and 7.1 used
    slant range as ground range), and only in precipitation VCPs. Clear-air
    and light-precipitation VCPs top out around 4.5–6.4° ⚠️ (general
    knowledge), which puts the floor of the blind cone near 2.5 km MSL over
    downtown. Neighbouring radars' 0.5° beam centres over Boise are about
    8.9 km (KSFX), 8.9 (KPDT) and 11.1 km MSL (KLRX), with lower beam edges
    at 6.3–8.4 km (coordinates from memory ⚠️). Model the gap from each
    volume's VCP rather than as a fixed shape.
  - NLDN density derives from Vaisala's network; NODD's terms cover the MRMS
    product, and we'd never hold raw strokes ⚠️.
- **Verification:** confirmed the bucket path, the archive start, the
  2-minute cadence, the 33 levels and their spacing, the units (bright band
  m above ground, 0 °C m MSL, echo tops km MSL, NLDN flashes/km²/min), the
  `PrecipFlag` codes, 5-minute RhoHV and Zdr, NODD's wording, all three
  robots results and the 0.5° beam heights. Corrected the nodata codes, the
  lightning-probability product names (`…minGrid`), KCBX's bearing, the
  top-tilt heights and the VCP dependence of the gap. Unverified: the radar
  coordinates (from memory) and GRIB decoding specifics.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-mrms-pds/),
  [NSSL product
  table](https://www.nssl.noaa.gov/projects/mrms/operational/tables.php),
  [first archive
  folders](https://noaa-mrms-pds.s3.amazonaws.com/?list-type=2&prefix=CONUS/MergedReflectivityQC_03.00/&delimiter=/&max-keys=3),
  [Oct 5
  files](https://noaa-mrms-pds.s3.amazonaws.com/?list-type=2&prefix=CONUS/MergedReflectivityQC_03.00/20261005/&max-keys=4),
  robots.txt for [the
  bucket](https://noaa-mrms-pds.s3.amazonaws.com/robots.txt),
  [mrms.ncep](https://mrms.ncep.noaa.gov/robots.txt) and
  [NSSL](https://www.nssl.noaa.gov/robots.txt), [NWS radar list
  (PDF)](https://www.weather.gov/media/tg/wsr88d-radar-list.pdf).

### NEXRAD Level II, Boise radar KCBX

NOAA NWS Radar Operations Center, distributed by NODD in Unidata-managed
buckets on AWS ([registry](https://registry.opendata.aws/noaa-nexrad/)).
**Use**; confidence high; effort L. Verified: **corrected**.

- **Contents:** full polar volumes for KCBX: reflectivity, radial velocity,
  spectrum width, Zdr, correlation coefficient and PhiDP, with
  super-resolution on the low tilts ⚠️ (general knowledge). Antenna
  elevation 3,172 ft (NWS WSR-88D list, Aug 18, 2026 update). Each day also
  has `_MDM` metadata files.
- **Coverage:** about 230 km of reflectivity range, so all of Ada, Canyon
  and the ring. Real time plus a long archive (start year not checked ⚠️).
  KCBX at 43.491° N, 116.234° W per the research ⚠️ (not verified).
- **Endpoint:** keyless S3:
  `unidata-nexrad-level2/<YYYY>/<MM>/<DD>/KCBX/KCBX<YYYYMMDD_HHMMSS>_V06`
  for the archive (confirmed) and `unidata-nexrad-level2-chunks` in real
  time; SNS topics `NewNEXRADLevel2ObjectFilterable` and
  `NewNEXRADLevel2Archive`. The old `noaa-nexrad-level2` bucket was
  deprecated Sep 1, 2025 (registry; its robots.txt now returns 403). Read
  with Py-ART, xradar or MetPy.
- **Updates:** a volume every 4–10 min, depending on the VCP.
- **Size** (corrected): on Oct 5, in clear air, 226 objects: 202 volumes
  (mean 6.04 MB, largest 8.68, smallest 3.47) plus 24 `_MDM` files; 1.22 GB
  a day, about one volume every 7 min. In precipitation mode, an estimated
  2–4 GB a day ⚠️.
- **License:** NODD: "open to the public and can be used as desired";
  managed by Unidata.
- **robots.txt:** `unidata-nexrad-level2.s3.amazonaws.com` 404 NoSuchKey (no
  rules). IEM's `/data/nexrd2/` and `/archive/nexrad/` mirrors are
  disallowed by its robots.txt (re-checked), so AWS only.
- **Use cases:** high-detail radar near Boise (polar, or gridded at 250–500
  m); biological echoes (bird and insect migration) that MRMS removes;
  weather volumes for crash dates before MRMS's AWS archive; each volume's
  VCP, to model the gap aloft.
- **Personas:** wildlife, fire and weather watcher, traffic researcher.
- **Core pieces:** fields contract, weather worker image (Py-ART or xradar),
  3D engine.
- **Risks:** one radar: terrain blocking (the Boise Front, the Owyhees), a
  VCP-dependent blind cone over Boise, lower quality at long range. Gridding
  costs CPU. Volume rate and size rise in precipitation mode (not measured).
- **Verification:** re-listed Oct 5: the research's "226 volumes" counted
  the 24 metadata files, so 202 volumes (matching Level 3's 202 files a
  day); the 1.22 GB total is right. The bucket move and deprecation date
  come from the registry. The radar coordinates remain unverified.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-nexrad/), [Oct
  5
  listing](https://unidata-nexrad-level2.s3.amazonaws.com/?list-type=2&prefix=2026/10/05/KCBX/),
  robots.txt for [the Unidata
  bucket](https://unidata-nexrad-level2.s3.amazonaws.com/robots.txt) and
  [the old bucket](https://noaa-nexrad-level2.s3.amazonaws.com/robots.txt),
  [NWS radar list
  (PDF)](https://www.weather.gov/media/tg/wsr88d-radar-list.pdf).

### NEXRAD Level 3, Boise radar KCBX

NOAA NWS, distributed by NODD (Unidata) on AWS
([registry](https://registry.opendata.aws/noaa-nexrad/)). **Use**;
confidence medium; effort S. Verified: **confirmed**.

- **Contents:** 100 KCBX product codes in the bucket (Oct 7), including
  `N0H`–`N3H` plus `NAH` and `NBH` (hydrometeor class per tilt), `HHC`
  (hybrid hydrometeor class), `EET` (enhanced echo tops), `DVL` (digital
  VIL), `NML` (melting layer), `NVW` (VAD wind profile), the `DPR`, `DAA`
  and `DTA` precipitation products, `NMD` and others. Class meanings need
  checking against the interface control document ⚠️.
- **Coverage:** about 230 km around Boise.
- **Endpoint:** keyless S3:
  `unidata-nexrad-level3/CBX_<PRODUCT>_<YYYY_MM_DD_HH_MM_SS>` (confirmed,
  e.g. `CBX_HHC_2026_10_05_00_03_11`); SNS `NewNEXRADLevel3Object`. Read
  with MetPy's `Level3File`.
- **Updates:** every volume scan.
- **Size:** `HHC` about 3.8 KB a file (re-measured; the research said 4.6);
  per the research, `N0H` about 14 KB, `EET` 2.1 KB, `DVL` 7.2 KB; about 202
  files a day each.
- **License:** NODD: "open to the public and can be used as desired".
- **robots.txt:** `unidata-nexrad-level3.s3.amazonaws.com` 404 NoSuchKey (no
  rules; fetched Oct 7).
- **Use cases:** particle type aloft (snow, graupel, hail); a
  biological-echo flag for the wildlife layer; the radar's melting layer
  (`NML`) to check MRMS's bright band; the VAD wind profile (`NVW`) over the
  radar, for birds and advection; cheap echo tops.
- **Personas:** wildlife, fire and weather watcher.
- **Core pieces:** fields contract.
- **Risks:** per-tilt products are a coarse 3D picture; class meanings must
  be checked against the ICD.
- **Verification:** key format, products and robots.txt confirmed (the
  research had inferred robots; it was fetched this time). `NML` and `NVW`
  added.
- **Evidence:** [product
  codes](https://unidata-nexrad-level3.s3.amazonaws.com/?list-type=2&prefix=CBX_&delimiter=_&max-keys=300),
  [HHC
  files](https://unidata-nexrad-level3.s3.amazonaws.com/?list-type=2&prefix=CBX_HHC_2026_10_05&max-keys=3),
  [robots.txt](https://unidata-nexrad-level3.s3.amazonaws.com/robots.txt),
  [registry](https://registry.opendata.aws/noaa-nexrad/).

## Models and analyses

### HRRR native levels (operational v4)

NOAA NCEP and GSL, distributed by NODD on AWS
([registry](https://registry.opendata.aws/noaa-hrrr-pds/)). **Use**;
confidence high; effort M. Verified: **corrected**.

- **Contents:** the `wrfnat` file (the 2026-10-05 12Z f00 `.idx` re-fetched:
  1,133 GRIB2 messages, last offset 678.6 MB). On 50 hybrid levels: PRES,
  CLMR, CIMIXR, RWMR, SNMR, GRLE, NCONCD, NCCICE, SPNCR, PMTF, PMTC, FRACCC,
  HGT, TMP, SPFH, UGRD, VGRD, VVEL, TKE and MASSDEN (confirmed in the idx).
  2D fields include VIS, LCDC, MCDC, HCDC, TCDC, COLMD, AOTK, REFC, RETOP,
  CRAIN, CSNOW, CFRZR, CICEP, LTNG, HPBL, DSWRF, HAIL and the 2 m and 10 m
  fields (confirmed). A 3 km Lambert conformal grid; forecasts hourly to 18
  h, and to 48 h at 00, 06, 12 and 18Z.
- **Coverage:** CONUS, so the whole ring (about 46 × 52 HRRR cells;
  arithmetic confirmed). Archive from 2014-07-30 (the research's bucket
  listing; not re-checked).
- **Endpoint:** keyless S3
  `s3://noaa-hrrr-bdp-pds/hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfnatfFF.grib2`,
  with HTTP Range requests from the `.idx` offsets (idx path confirmed); SNS
  `NewHRRRObject`. NOMADS has `hrrr_2d` and `hrrr_sub` grib-filter datasets
  for server-side 2D cuts; its usage policy caps 120 hits a minute per IP,
  summed across the NOMADS and FTP hosts (SCN 21-32). For pressure-level
  clouds and winds, hrrrzarr (next) is far cheaper.
- **Updates:** hourly (f00 analysis plus forecasts).
- **Size** (corrected): per-variable totals over all 50 levels, from the
  same idx: PRES 117.1 MB, HGT 94.0 (the research said 113.1), SPFH 59.9,
  MASSDEN 53.5, UGRD 40.8, VGRD 39.9, TMP 39.1, PMTF 36.9, PMTC 30.1, VVEL
  25.0, FRACCC 9.7, RWMR 3.7, CLMR 2.0, SNMR 1.9, CIMIXR 1.0, GRLE 0.5. HGT
  on every fifth level plus the top is about 20.5 MB an hour (1.3–2.5 MB a
  level). The proposed pull (5 hydrometeors 9.1 MB, FRACCC 9.7, HGT on 10–11
  levels about 19–20.5, U and V on 3 levels about 5) is about 43 MB an hour,
  not 35–40, plus 53.5 MB an hour for MASSDEN when gated: about 1.0–2.3 GB a
  day. Moving clouds and winds to hrrrzarr would leave only FRACCC and
  MASSDEN to take from `wrfnat`. A ring brick is 57 × 47 × 48: 514 KB as
  RGBA8, 129 KB as R8 (arithmetic confirmed).
- **License:** NODD: "open to the public and can be used as desired".
  Attribution requested; modified data not to be presented as original.
- **robots.txt** (re-checked Oct 7): `noaa-hrrr-bdp-pds.s3.amazonaws.com`
  404 NoSuchKey (no rules); `nomads.ncep.noaa.gov` 404 (no rules), with
  NCEP's 120 hits a minute policy.
- **Use cases:** 3D clouds (extinction from the mixing ratios); 3D smoke
  plumes (MASSDEN, on native levels only); winds for advecting frames and
  for particles; the inversion profile (TMP); icing layers for aircraft; the
  freezing-rain and sleet flags MRMS lacks; forecast frames for the clock
  (next 18 h).
- **Personas:** fire and weather watcher, sky watcher, gardener, hiker and
  camper, aviation, cyclist, commuter.
- **Core pieces:** fields contract, 3D engine, full replay, weather worker
  image (ecCodes, numpy, pyproj).
- **Risks:** hybrid-level heights change slowly, so fetching full HGT once
  per run or per day and reusing it is worth measuring ⚠️. Hydrometeor sizes
  grow on cloudy days. It's a model, not an observation: 3 km cells can't
  resolve cumulus. RRFS goes operational Oct 14, 2026; SCN 26-48 says REFS
  still uses HRRR members, so HRRR continues for now (no retirement date
  found). GSL's HRRR-Smoke website is robots-disallowed (below); use NCEP's
  output on AWS only.
- **Verification:** re-fetched the idx and recomputed message sizes from
  consecutive offsets: the HGT, PRES, UGRD, VGRD and MASSDEN totals were too
  high; the hydrometeor and FRACCC totals were right. NOMADS's 120 hits a
  minute per IP confirmed in SCN 21-32 (effective Apr 20, 2021). Bucket
  names, region, SNS topic and license wording confirmed on the registry.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-hrrr-pds/),
  [the
  idx](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20261005/conus/hrrr.t12z.wrfnatf00.grib2.idx),
  [bucket
  robots.txt](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/robots.txt),
  [NOMADS](https://nomads.ncep.noaa.gov/) and [its
  robots.txt](https://nomads.ncep.noaa.gov/robots.txt), [SCN 21-32
  (PDF)](https://www.weather.gov/media/notification/pdf2/scn21-32nomad_changes.pdf).

### hrrrzarr (HRRR in Zarr)

University of Utah MesoWest, on AWS Open Data and listed on NOAA's HRRR
registry page ([MesoWest page](https://mesowest.utah.edu/html/hrrr/)).
**Use**; confidence medium; effort S. Verified: **corrected**.

- **Contents** (bucket listing, Oct 7): the top level holds only `grid/`,
  `prs/` and `sfc/`, so there are no native levels.
  `prs/<YYYYMMDD>/<YYYYMMDD>_<HH>z_anl.zarr/` holds groups for pressure
  levels from 50 to 1000 mb every 25 mb (plus 1013.2 mb), heights above
  ground (2, 8, 10, 80, 1000 and 4000 m), `cloud_base`, `cloud_ceiling`,
  `cloud_top`, the low, middle and high cloud layers, `0C_isotherm`,
  `surface` and others. At 850 mb the variables are ABSV, CIMIXR, CLMR, DPT,
  GRLE, HGT, RH, RWMR, SNMR, SPFH, TMP, UGRD, VGRD and VVEL, so the
  hydrometeor mixing ratios are there on pressure levels. Chunks are indexed
  `0.0` to `0.11` per row (12 columns; 8 × 12 = 96 per CONUS grid, which
  matches 150 × 150 chunks ⚠️, chunk shape not read from `.zarray`). An 850
  mb TMP chunk is 9–17 KB. MASSDEN and FRACCC weren't seen at 850 mb.
- **Coverage:** CONUS. The ring probably falls in 1–4 chunks per level ⚠️
  (not computed). Current: `prs/` has dates through 2026-10-07, with 281
  date folders in 2026.
- **Endpoint:** keyless S3 `s3://hrrrzarr` (us-west-1, per the registry),
  read with zarr, xarray and s3fs, or plain HTTPS GETs of the chunk keys;
  only the chunks over the ring are fetched.
- **Updates:** near real time.
- **Size:** about 10 variables × 40 levels × 1–4 chunks × 10–17 KB, so well
  under 25 MB an hour, likely much less since hydrometeors are mostly zero
  ⚠️ (estimate).
- **License:** listed on NODD's HRRR registry page ("open to the public and
  can be used as desired"); the MesoWest page states no license. Contact
  `atmos-mesowest@lists.utah.edu` (registry).
- **robots.txt:** `hrrrzarr.s3.amazonaws.com` 404 NoSuchKey (no rules;
  re-checked).
- **Use cases:** cheap region-only pressure-level clouds (CLMR, CIMIXR,
  RWMR, SNMR, GRLE), winds and temperature; inversion profiles; history
  without byte-range bookkeeping.
- **Personas:** fire and weather watcher, sky watcher, cyclist, aviation.
- **Core pieces:** weather worker image (zarr, xarray) or a small chunk
  reader of our own.
- **Risks:** a third-party conversion with no service guarantee. Only the
  analysis store (`_anl`) was inspected; whether forecast hours are there is
  unverified. No native levels and no MASSDEN or FRACCC seen, so smoke and
  cloud fraction still need `wrfnat`. 25 mb spacing is about 200–250 m near
  the ground, coarse for valley fog.
- **Verification:** the research's variable list was unconfirmed; the
  listing now confirms pressure-level hydrometeors, HGT, TMP and winds,
  confirms there are no native levels, and shows the archive is current.
  Bucket region and contact confirmed on the registry. Chunk shape and the
  ring's chunk count not verified.
- **Evidence:** [MesoWest page](https://mesowest.utah.edu/html/hrrr/),
  [registry](https://registry.opendata.aws/noaa-hrrr-pds/),
  [robots.txt](https://hrrrzarr.s3.amazonaws.com/robots.txt), listings of
  [the top
  level](https://hrrrzarr.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=10),
  [2026
  dates](https://hrrrzarr.s3.amazonaws.com/?list-type=2&prefix=prs/2026&delimiter=/&max-keys=400)
  and [850 mb on Oct
  5](https://hrrrzarr.s3.amazonaws.com/?list-type=2&prefix=prs/20261005/20261005_12z_anl.zarr/850mb/&delimiter=/&max-keys=100).

### RRFS v1 (Rapid Refresh Forecast System)

NOAA NCEP; operational from Oct 14, 2026 ([SCN 26-48,
PDF](https://www.weather.gov/media/notification/pdf_2026/scn26-048_Updated_RRFS_and_REFS_Implementation_aad.pdf)).
**Use**; confidence medium; effort M. Verified: **corrected**.

- **Contents:** per SCN 26-48 (updated Sep 9, 2026): a 3 km North America
  domain with CONUS and Alaska subsets; hourly cycles to 18 h, and to 84 h
  at 00, 06, 12 and 18Z; 13 km North America output; a relocatable 1.5 km
  fire-weather run over a 5 × 5° region (NCO's product page says 1.27 km;
  not resolved); BUFR soundings; 5 ensemble members, with REFS to 60 h. It
  replaces NAM, HREF, SREF and HiresW (Guam's HiresW stays). Files:
  `prslev.3km`, `2dfld.3km`, `2dfld.3km.subh`, `prslev` and `2dfld` at 13 km
  for North America, and the fire-weather `prslev` and `2dfld`. From the
  operational bucket's real idx (2026-10-05 12Z f000, CONUS): `prslev` has
  675 messages on 45 pressure levels (2–1000 mb), including CLMR, ICMR
  (cloud ice), RWMR, SNMR, GRLE, HGT, TMP, UGRD, VGRD, SPFH, RH and DZDT,
  and no smoke. `2dfld` has smoke near the ground only (MASSDEN at 8 m, for
  particulate organic matter and dust), column COLMD, AOTK, VIS, CEIL, HGT
  at cloud base, top and ceiling, LCDC and TCDC.
- **Coverage:** North America, so the ring.
- **Endpoint:** after implementation, NOMADS `/pub/data/nccf/com/rrfs/prod/`
  (SCN). The operational AWS bucket `noaa-rrfs-ops-pds` (us-east-1) already
  holds the parallel feed (date folders from 2026-08-13). The prototype
  bucket `noaa-rrfs-pds` stopped updating Aug 12, 2026 (registry). NOMADS
  lists no grib filter for RRFS. The whole `prslev` CONUS f000 is 590.8 MB,
  so use idx byte ranges.
- **Updates:** hourly (84 h at 00, 06, 12 and 18Z).
- **Size** (from the idx): `prslev.3km` CONUS f000 is 590.8 MB; hydrometeors
  on 45 levels about 11 MB, HGT 76 MB, U and V about 66 MB each.
- **License:** NODD registry: "made available under ... (CC0-1.0)".
- **robots.txt** (Oct 7): `nomads.ncep.noaa.gov` 404 (no rules; 120 hits a
  minute policy); `noaa-rrfs-pds` and `noaa-rrfs-ops-pds` 404 NoSuchKey (no
  rules).
- **Use cases:** forecast frames to 84 h on the clock; 3D clouds from
  pressure-level hydrometeors (a model adapter shared with HRRR and
  hrrrzarr); the fire-weather nest; an adapter so HRRR's eventual retirement
  doesn't break the plugin.
- **Personas:** fire and weather watcher, hiker and camper, farmer.
- **Core pieces:** fields contract, weather worker image.
- **Risks:** no native levels and no 3D smoke, so HRRR `wrfnat` stays the
  only 3D smoke source. NCO's inventories still say "coming soon" and
  "actual parameters may differ"; the parallel feed may change before Oct
  14, and Herbie's RRFS template uses a NOMADS path under `rrfs/v1.0/`,
  while the SCN gives `rrfs/prod/`; check before relying on it. HRRR has no
  announced retirement date (REFS uses HRRR members).
- **Verification:** SCN 26-48 read in full: date, products, paths and
  replacements confirmed. Corrected: hydrometeors on pressure levels
  confirmed from a real idx (the research had them unconfirmed); no 3D
  smoke; near-surface and column smoke in `2dfld`; the operational bucket is
  `noaa-rrfs-ops-pds` and already populated; the prototype bucket stopped
  Aug 12; no NOMADS grib filter.
- **Evidence:** [SCN 26-48
  (PDF)](https://www.weather.gov/media/notification/pdf_2026/scn26-048_Updated_RRFS_and_REFS_Implementation_aad.pdf),
  registry pages for [the
  prototype](https://registry.opendata.aws/noaa-rrfs/) and
  [operations](https://registry.opendata.aws/noaa-rrfs-ops/), [NCO product
  page](https://www.nco.ncep.noaa.gov/pmb/products/rrfs/),
  [NOMADS](https://nomads.ncep.noaa.gov/), [bucket
  listing](https://noaa-rrfs-ops-pds.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=20),
  idx for
  [prslev](https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.20261005/12/rrfs.t12z.prslev.3km.f000.conus.grib2.idx)
  and
  [2dfld](https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.20261005/12/rrfs.t12z.2dfld.3km.f000.conus.grib2.idx).

### RTMA and RTMA rapid update

NOAA NCEP, distributed by NODD on AWS
([registry](https://registry.opendata.aws/noaa-rtma/)). **Use**; confidence
high; effort S. Verified: **corrected**.

- **Contents:** the rapid update (`rtma2p5_ru`) `2dvaranl_ndfd` file every
  15 min holds 13 messages (idx, Oct 5 00Z): HGT, PRES, 2 m TMP, DPT and
  SPFH, 10 m UGRD, VGRD, WDIR, WIND and GUST, VIS (m), CEIL (m) and TCDC
  (total cloud; not in the research's list). NCO's inventory lists VIS and
  CEIL in metres. Also the hourly RTMA, and URMA as a time-lagged version.
- **Coverage:** the CONUS 2.5 km NDFD grid, so the ring.
- **Endpoint:** keyless S3 `noaa-rtma-pds`:
  `rtma2p5_ru.YYYYMMDD/rtma2p5_ru.tHHMMz.2dvaranl_ndfd.grb2` plus `.idx`
  (also `2dvarges` first-guess files); layout confirmed. Fetch VIS and CEIL
  by idx byte ranges (Herbie supports RTMA and URMA). URMA is in
  `noaa-urma-pds`. SNS `NewNCEPRTMAObject`.
- **Updates:** 15 min (rapid update), hourly (RTMA).
- **Size** (corrected, from idx offsets): every message is whole-CONUS: VIS
  6.55 MB, CEIL 8.43 MB, the whole file 84.26 MB. VIS and CEIL every 15 min
  is about 15 MB, about 1.4 GB a day (the research had guessed a few MB per
  15 min). Hourly frames would be about 360 MB a day. The ring crop is a few
  KB.
- **License:** NODD: "open to the public and can be used as desired".
- **robots.txt:** `noaa-rtma-pds` and `noaa-urma-pds` 404 NoSuchKey (no
  rules).
- **Use cases:** gridded fog extinction from visibility; a gridded cloud
  base for slabs and for "summit in the clouds"; a check on total cloud
  cover; the analysis of record for fog-day history.
- **Personas:** commuter, traffic researcher, hiker and camper, sky watcher.
- **Core pieces:** fields contract, weather worker image.
- **Risks:** cost, as above: use hourly frames by default and 15-minute ones
  only when METAR or road-weather stations show fog. Visibility and ceiling
  are smooth analyses that can miss shallow fog banks.
- **Verification:** bucket layout and per-message sizes measured from a real
  idx; the research's size guess was low by a factor of about 5. TCDC added.
  The registry describes RTMA and URMA as hourly; the listing shows the
  rapid-update files every 15 min.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-rtma/), [NCO
  product page](https://www.nco.ncep.noaa.gov/pmb/products/rtma/), [NCO
  inventory](https://www.nco.ncep.noaa.gov/pmb/products/rtma/rtma2p5_ru.t1645z.2dvaranl_ndfd.grb2.shtml),
  [Oct 5
  listing](https://noaa-rtma-pds.s3.amazonaws.com/?list-type=2&prefix=rtma2p5_ru.20261005/&max-keys=12),
  [the
  idx](https://noaa-rtma-pds.s3.amazonaws.com/rtma2p5_ru.20261005/rtma2p5_ru.t0000z.2dvaranl_ndfd.grb2.idx),
  [robots.txt](https://noaa-rtma-pds.s3.amazonaws.com/robots.txt).

## Satellite

### GOES-18 ABI Level 2: cloud, aerosol, fire and radiation

NOAA NESDIS, distributed by NODD on AWS
([registry](https://registry.opendata.aws/noaa-goes/)). **Use**; confidence
high; effort M. Verified: **corrected**.

- **Contents** (bucket listing, Oct 7, 106 prefixes): ACHA2KMC (cloud-top
  height, 2 km), ACHAC, ACHP2KMC, ACMC (clear-sky mask), ACTPC (phase),
  CODC, CPSC, CCLC (Cloud Cover Layers), ADPC (aerosol detection: smoke and
  dust), AODC, FDCC (fire), DSRC (surface shortwave), DMWC and DMWVC, CTPC,
  plus LVTPC and LVMPC (legacy clear-sky temperature and moisture profiles;
  not in the research's list). Cloud Cover Layers, per NOAA VLab: surface to
  FL050, FL050–100, FL100–180, FL180–240 and FL240 to top; 10 km at nadir;
  CONUS every 5 min; a layer-classification accuracy requirement of 60%. No
  fog and low stratus (FLS) product in the bucket (confirmed).
- **Coverage:** the CONUS sector, so the ring. The viewing zenith angle over
  Boise from GOES-18 (137.0° W) is 54.5° (recomputed), so cloud tops appear
  displaced about 1.40 × their height toward the northeast (confirmed).
  GOES-East is now GOES-19 (since Apr 4, 2025, per the registry), at about
  64.7° over Boise. ACHA2KMC on GOES-18 starts 2023 day 086 (Mar 27, 2023;
  the research said Mar 24).
- **Endpoint:** keyless S3
  `s3://noaa-goes18/ABI-L2-<product>/<YYYY>/<DOY>/<HH>/` (NetCDF4/HDF5);
  ranged chunk reads with h5py or fsspec are probably possible ⚠️ (chunk
  layout not inspected); SNS `NewGOES18Object`.
- **Updates:** 5 min (CONUS).
- **Size** (re-measured, 2026-10-05 18Z, per 5-minute file): ACHA2KMC
  4.49–4.50 MB, CCLC 0.41 MB; ACMC 3.76 MB and ADPC 0.56 MB per the
  research. Whole ACHA2KMC files come to about 1.3 GB a day. The ring at
  0.02° is 85 × 70 cells, about 50 KB per derived frame.
- **License:** NODD: "can be used as desired". data.gov lists CC0 for the
  ACHA record but also "Access Level: non-public" and "otherRestrictions"
  (NCEI archive metadata), so rely on the NODD statement.
- **robots.txt:** `noaa-goes18.s3.amazonaws.com` 404 NoSuchKey (no rules;
  re-checked).
- **Use cases:** observed cloud tops and the clear-sky mask to clip or nudge
  model clouds; observation-only cloud slabs (top from ACHA, base from the
  RTMA ceiling); cloud layers for slab height bands; a check on smoke extent
  (ADP); fire hotspots (FDC); observed sunshine for gardeners (DSR).
- **Personas:** fire and weather watcher, sky watcher, gardener, hiker and
  camper, aviation.
- **Core pieces:** fields contract, weather worker image (h5py or netCDF4).
- **Risks:** parallax must be corrected before tops meet the terrain. The
  60% figure for Cloud Cover Layers is a requirement, not a measured skill;
  the claims "full validation since May 2025" and "can't see low cloud under
  high cloud" weren't found on the VLab page (unverified). The flight-level
  boundaries are pressure altitudes, not fixed heights above sea level.
  Native pixels over Boise are larger than nominal (54.5° zenith), so a
  0.02° grid oversamples.
- **Verification:** product names, sizes, sector cadence, the missing FLS
  product and NODD's wording confirmed; GOES-19 is now GOES-East; zenith
  angles recomputed and confirmed. Corrected the ACHA2KMC start date,
  qualified the CC0 claim by the contradictory data.gov metadata, marked the
  Cloud Cover Layers maturity and limitation claims unverified, and added
  LVTPC and LVMPC.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-goes/),
  listings of [all
  products](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=200),
  [ACHA2KMC](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-ACHA2KMC/2026/278/18/&max-keys=2),
  [CCLC](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-CCLC/2026/278/18/&max-keys=2)
  and [ACHA2KMC in
  2023](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-ACHA2KMC/2023/&delimiter=/&max-keys=3),
  [data.gov
  record](https://catalog.data.gov/dataset/noaa-goes-r-series-advanced-baseline-imager-abi-level-2-cloud-top-height-acha),
  [VLab Cloud Cover Layers](https://vlab.noaa.gov/web/towr-s/goes-ccl),
  [robots.txt](https://noaa-goes18.s3.amazonaws.com/robots.txt).

### GOES-18 ABI imagery (CMIP and MCMIP bands)

NOAA NESDIS, distributed by NODD on AWS
([registry](https://registry.opendata.aws/noaa-goes/)). **Use**; confidence
high; effort L. Verified: **confirmed**.

- **Contents:** 16 ABI bands, 0.5 km (band 2) to 2 km at nadir, CONUS every
  5 min. MCMIPC holds all bands at 2 km in one file; CMIPC is one file per
  band. Over Boise the effective pixels are larger than nominal because of
  the 54.5° viewing angle.
- **Coverage:** CONUS, so the ring.
- **Endpoint:** keyless S3 `s3://noaa-goes18/ABI-L2-CMIPC/` and
  `ABI-L2-MCMIPC/`; ring-only HDF5 chunk reads ⚠️ (chunking not inspected).
- **Updates:** 5 min.
- **Size:** MCMIPC 54.4–54.5 MB a file (re-measured), about 655 MB an hour
  and 15.7 GB a day; CMIPC 192 files an hour, about 1.78 GB an hour (per the
  research, not re-measured). Band 2 over the ring at 0.005° is 340 × 280
  cells, about 0.1–0.3 MB per range read ⚠️ (estimate).
- **License:** NODD: "can be used as desired"; credit NOAA/NESDIS.
- **robots.txt:** `noaa-goes18.s3.amazonaws.com` 404 NoSuchKey (no rules).
- **Use cases:** daytime visible texture draped on cloud tops (after
  parallax correction); night fog extent from band 7 minus band 14 (3.9 −
  11.2 µm), a night-only product; validating rendered cloud cover.
- **Personas:** sky watcher, commuter, fire and weather watcher.
- **Core pieces:** fields contract, weather worker image (h5py, fsspec).
- **Risks:** whole files are large, so only chunked range reads make this
  practical. The 3.9 µm band carries reflected sunlight by day, so the fog
  difference works only at night, and its thresholds need local tuning.
- **Verification:** MCMIPC sizes re-measured (54.37 and 54.46 MB at
  2026-10-05 18Z). CMIPC sizes and the chunk layout weren't checked.
- **Evidence:** [MCMIPC
  listing](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-MCMIPC/2026/278/18/&max-keys=2),
  [all
  products](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=200),
  [registry](https://registry.opendata.aws/noaa-goes/).

### GOES-18 GLM lightning (Level 2 LCFA)

NOAA NESDIS, distributed by NODD on AWS
([registry](https://registry.opendata.aws/noaa-goes/)). **Use**; confidence
high; effort S. Verified: **confirmed**.

- **Contents:** total lightning (in-cloud and cloud-to-ground) as flashes,
  groups and events, with location, time, area and energy. Pixels are about
  8 km at nadir to 14 km at the edge ⚠️ (general knowledge).
- **Coverage:** GOES-West's lightning-mapper view, so the ring.
- **Endpoint:** keyless S3
  `s3://noaa-goes18/GLM-L2-LCFA/<YYYY>/<DOY>/<HH>/`, one NetCDF file every
  20 s (confirmed: `OR_GLM-L2-LCFA_G18_s…_e…_c….nc` at 20 s spacing).
- **Updates:** 20 s.
- **Size** (re-measured 2026-10-05 18Z): 180 files an hour of about 0.166 MB
  each (165,038–167,165 bytes), about 30 MB an hour. Flashes kept for the
  ring: a few KB a day.
- **License:** NODD: "can be used as desired".
- **robots.txt:** `noaa-goes18.s3.amazonaws.com` 404 NoSuchKey (no rules).
- **Use cases:** flashes glowing inside the cloud volume; lightning counts
  around trailheads and ridges; storm replay.
- **Personas:** fire and weather watcher, hiker and camper, sky watcher.
- **Core pieces:** fields contract or a point-events table, full replay.
- **Risks:** every file covers the whole view, so filtering to the ring
  costs about 0.7 GB a day (165–167 KB × 4,320 files); gate on MRMS
  convection or lightning density. Positions are 8–14 km pixels navigated to
  an assumed lightning-altitude ellipsoid, so expect several km of offset
  ⚠️: draw glows, not bolts.
- **Verification:** file cadence and sizes re-measured. The data.gov page
  the research cited wasn't re-opened; pixel sizes are general knowledge.
- **Evidence:** [GLM
  listing](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=GLM-L2-LCFA/2026/278/18/&max-keys=4),
  [registry](https://registry.opendata.aws/noaa-goes/), [data.gov
  record](https://catalog.data.gov/dataset/noaa-goes-r-series-geostationary-lightning-mapper-glm-level-2-lightning-detection-events-g).

## Ground and column observations

### Aviation Weather Center Data API (METAR)

NOAA NWS Aviation Weather Center ([API
docs](https://aviationweather.gov/data/api/)). **Use**; confidence high;
effort S. Verified: **confirmed**.

- **Contents:** METAR JSON fields (sample Oct 7, 05:35Z): `icaoId`,
  `receiptTime`, `obsTime`, `reportTime`, `temp`, `dewp`, `wdir`, `wspd`,
  `visib`, `altim`, `qcField`, `metarType`, `rawOb`, `lat`, `lon`, `elev`,
  `name`, `cover`, `clouds` and `fltCat`. `visib` is a number or a string
  such as `10+`.
- **Coverage:** point stations; one request over the ring returned 5: KMAN,
  KEUL, KMUO, KBOI and KONO.
- **Endpoint:** `GET
  https://aviationweather.gov/api/data/metar?bbox=minLat,minLon,maxLat,maxLon&format=json`,
  keyless (the bbox order confirmed by the sample). Cache files under
  `/data/cache/` (`metars.cache.xml.gz`, updated once a minute).
- **Updates:** hourly reports, plus specials.
- **Size:** about 2 KB a poll.
- **License:** none stated on the page; NWS products are US government works
  ⚠️. The page asks: "Please keep requests limited in scope and frequency".
- **robots.txt:** `aviationweather.gov/robots.txt` 404 (no rules). The API
  is "rate limited to 100 requests per minute" and asks for a custom
  User-Agent.
- **Use cases:** observed cloud bases to anchor slabs; visibility points for
  fog; flight category on airport labels.
- **Personas:** aviation, commuter, sky watcher, traffic researcher.
- **Core pieces:** readings contract.
- **Risks:** sparse (5 stations). ASOS ceilometers report cloud only up to
  about 12,000 ft ⚠️ (general knowledge). Parse `visib` as text.
- **Verification:** rate limit, the User-Agent request and the usage wording
  confirmed on the docs page; one sample request with our User-Agent
  confirmed the bbox order, the field names and the same 5 stations.
- **Evidence:** [API docs](https://aviationweather.gov/data/api/), [sample
  request](https://aviationweather.gov/api/data/metar?bbox=42.90,-117.30,44.30,-115.60&format=json),
  [robots.txt](https://aviationweather.gov/robots.txt).

### Iowa Environmental Mesonet (IEM)

Iowa State University ([JSON services
index](https://mesonet.agron.iastate.edu/json/)). **Use**; confidence high;
effort S. Verified: **corrected**. Already in [SOURCES.md](../SOURCES.md) as
"Boise airport weather history (IEM ASOS)", not started.

- **Contents:** `/cgi-bin/request/asos.py` (METAR history);
  `/cgi-bin/request/asos1min.py` (NCEI's 1-minute ASOS; its visibility
  fields unverified ⚠️); `/cgi-bin/request/scp.py` (the ASOS Satellite Cloud
  Product; output fields not documented on its help page);
  `/json/raob.py?station=&ts=&pressure=` (soundings as JSON). The `/json/`
  index also lists VTEC warning services, storm-based warnings (GeoJSON) and
  SPC and WPC outlooks, which can stand in for api.weather.gov for warning
  history. Boise's upper-air station is WMO 72681, KBOI (SCN 18-86),
  launching at 00Z and 12Z ⚠️ (standard practice, not stated in the notice).
- **Coverage:** BOI and the other ring airports; many years of history.
- **Endpoint:** keyless HTTP GET, one request per 120 s (Crawl-delay).
- **Updates:** hourly (ASOS); 00Z and 12Z (soundings).
- **License:** free to use "for any lawful purpose", provided as-is without
  warranty.
- **robots.txt** (re-checked): Crawl-delay 120; Disallow `/usage/`, `/tmp/`,
  `/data/NIDS/`, `/data/nexrd2/`, `/data/model/`, `/archive/nexrad/` and
  `/archive/raw/snet/`. There's no User-agent line, so under our lenient
  parse it applies to all. The `/cgi-bin/request/` and `/json/` paths are
  allowed.
- **Use cases:** the list of fog days for [chapter
  2](../02-treasure-valley-signal-system.md)'s fog → detector fallback →
  long greens theory; the inversion base and top for the fog top and lid;
  satellite cloud layers above the ceilometer's reach at airports; NWS
  warning and advisory history (VTEC) instead of api.weather.gov.
- **Personas:** traffic researcher, commuter, fire and weather watcher, sky
  watcher.
- **Core pieces:** readings contract, lifecycles contract (warnings).
- **Risks:** pace to one request every 120 s; soundings only twice a day
  from one site.
- **Verification:** robots.txt confirmed. License corrected to IEM's own
  wording. WMO 72681 and KBOI confirmed in SCN 18-86 (which is about the
  2019 radiosonde change, not launch times). The VTEC warnings archive
  added. The cloud product's fields and the 1-minute visibility fields
  weren't checked, to save requests under the crawl delay.
- **Evidence:** [robots.txt](https://mesonet.agron.iastate.edu/robots.txt),
  [JSON index](https://mesonet.agron.iastate.edu/json/), [sounding
  help](https://mesonet.agron.iastate.edu/json/raob.py?help), [cloud product
  help](https://mesonet.agron.iastate.edu/cgi-bin/request/scp.py?help), [SCN
  18-86
  (PDF)](https://www.weather.gov/media/notification/pdfs/scn18-86boise_upper_air_aaa.pdf).

### 511 Idaho road-weather stations (already collected)

ITD, through the 511 Idaho API ([SOURCES.md](../SOURCES.md)). **Internal
only**; confidence high; effort S. Verified: **confirmed**.

- **Contents:** `obs.weather_reading` at 127 stations statewide every 5 min:
  visibility, precipitation rate and type, totals, air, surface and dewpoint
  temperatures, wind and gust, surface status and friction.
- **Coverage:** statewide; the ring's subset hasn't been counted.
- **Endpoint:** already ingested by the `idaho511` service; the key is kept
  on the server, never in the repo.
- **Updates:** 5 min.
- **License:** 511 data aren't republished ([DECISIONS](../DECISIONS.md),
  Oct 6): internal use only.
- **robots.txt:** not applicable: an official keyed API whose use ITD agreed
  to (DECISIONS, Oct 6).
- **Use cases:** ground-truth visibility for fog density; precipitation at
  the ground for particles; icy-road badges under snow volumes.
- **Personas:** commuter, traffic researcher, cyclist.
- **Core pieces:** readings contract.
- **Risks:** any fog layer computed with these values becomes internal too.
  Proposed: build the public fog layer from NOAA inputs only, with
  road-weather readings as internal points and checks.
- **Verification:** checked against SOURCES.md and DECISIONS.md: 127
  stations, 5-minute polling, not republished.

### Our camera archive (already collected)

Our recordings of ACHD and ITD cameras through 511 ([chapter
11](../11-camera-validation-layer.md)). **Internal only**; confidence high;
effort M. Verified: **confirmed**.

- **Contents:** 34 key cameras every 50 s and 389 road-weather views (385
  ITD views at 130 stations plus 4 Oregon DOT views) every 10 min, in daily
  videos.
- **Coverage:** key cameras in Ada and Canyon; road-weather views statewide
  and along the Oregon end of the corridor.
- **Endpoint:** in hand (the archive is mounted read-only in the app).
- **License:** the images aren't republished.
- **robots.txt:** not applicable: collected through the allowed 511 route.
- **Use cases:** a visual check of the rendered fog, snow and rain in
  look-through; a contrast-based visibility estimate (no people or plates).
- **Personas:** traffic researcher, commuter.
- **Core pieces:** 3D engine (the look-through photo plane), full replay.
- **Risks:** must stay road-network only: no plate or face recognition.
- **Verification:** counts and cadences match SOURCES.md.

## Smoke and air quality

### NOAA Hazard Mapping System (HMS): smoke and fire

NOAA NESDIS Office of Satellite and Product Operations ([HMS
page](https://www.ospo.noaa.gov/products/land/hms.html)). **Use**;
confidence medium; effort S. Verified: **corrected**.

- **Contents:** analyst-drawn smoke polygons (densities light, medium and
  heavy since July 2022) and fire detection points. The first smoke analysis
  is about 11 am to noon Eastern, the second about 7–8 pm Eastern (OSPO
  page). The directory has `Smoke_Polygons/` in Shapefile, KML and GeoTIFF,
  `Fire_Points/` and `Graphic/`.
- **Coverage:** North America, so the ring.
- **Endpoint** (corrected): keyless HTTPS directory
  `https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/`. The OSPO page
  points to `/pub/FIRE/web/HMS2/`, which now returns 404, and the research's
  "HMS2 is testing" is out of date. ArcGIS feature services also exist (OSPO
  page; not inspected).
- **Updates:** smoke twice a day, plus fire updates.
- **Size:** KB to a few MB a day.
- **License:** a US government product; no license stated ⚠️. The disclaimer
  says locations "may be slightly offset" and the product isn't for tactical
  decisions.
- **robots.txt** (re-checked Oct 7): `satepsanone.nesdis.noaa.gov` returns
  an HTML not-found page (404), so no rules; `www.ospo.noaa.gov` has
  `User-agent: *` with only a Sitemap line (all allowed).
- **Use cases:** observed smoke extent to check and shape HRRR's smoke
  volumes; gating the smoke ingest; field-burning smoke for farmers.
- **Personas:** fire and weather watcher, farmer, gardener, cyclist.
- **Core pieces:** lifecycles contract, fields contract.
- **Risks:** 2D and daytime only; the density classes are qualitative; the
  OSPO page's links are stale.
- **Verification:** directory structure checked: `HMS/` is live, `HMS2/` is
  404; analysis times, density classes and disclaimers confirmed on the OSPO
  page.
- **Evidence:** [OSPO
  page](https://www.ospo.noaa.gov/products/land/hms.html), [HMS
  directory](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/), [smoke
  polygons](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/),
  [the dead HMS2
  link](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS2/), robots.txt
  for [satepsanone](https://satepsanone.nesdis.noaa.gov/robots.txt) and
  [OSPO](https://www.ospo.noaa.gov/robots.txt).

### AirNow (PM2.5 and AQI)

US EPA and partners ([FAQ](https://docs.airnowapi.org/faq)). **Needs owner
action**; confidence medium; effort S. Verified: **corrected**.

- **Contents:** current and forecast AQI and PM2.5 at monitors (API), plus
  hourly file products, which the FAQ recommends for bulk use.
- **Coverage:** monitors in Ada and Canyon (count not checked).
- **Endpoint:** the API needs a key and has hourly per-key limits (FAQ). The
  FAQ steers bulk users to the file products instead of repeated API calls;
  `files.airnowtech.org` serves an S3 file browser without a key ⚠️ (no data
  file fetched).
- **Updates:** hourly.
- **License:** EPA's "AirNow Data Exchange Guidelines" (Aug 2025, read): the
  data "should be considered preliminary" and displays must say so; values
  "should not be altered"; not for trends or regulation; credit the
  reporting agencies and AirNow; show AQI in EPA's standard colours; a
  signed agreement form is part of the guidelines.
- **robots.txt:** `docs.airnowapi.org/robots.txt` returns an HTML page (200,
  text/html), not a robots file, so no rules under our lenient parse;
  `www.airnowapi.org/robots.txt` 302 to a 403 (4xx means no rules);
  `files.airnowtech.org/robots.txt` 404 NoSuchKey (no rules).
- **Use cases:** checking smoke volumes against ground PM2.5; air quality
  under the inversion lid in winter.
- **Personas:** fire and weather watcher, cyclist, gardener.
- **Core pieces:** readings contract.
- **Risks:** owner decisions: whether to sign and return the guidelines
  form, and an API key or the file products. "Not altered" and "not for
  trends" limit derived products. EPA's AQI colours (green to maroon) clash
  with our never-red-or-green-alone rule unless labelled. The data are
  preliminary.
- **Verification:** the guidelines are now read (the research hadn't). The
  FAQ confirms the key, hourly limits and the file-product route. Robots
  results added. Keyless file access is likely but unconfirmed (only the
  browser page was seen).
- **Evidence:** [FAQ](https://docs.airnowapi.org/faq), [Data Exchange
  Guidelines (PDF)](https://docs.airnowapi.org/docs/DataUseGuidelines.pdf),
  robots.txt for [docs](https://docs.airnowapi.org/robots.txt), [the API
  host](https://www.airnowapi.org/robots.txt) and
  [files](https://files.airnowtech.org/robots.txt), [file
  listing](https://files.airnowtech.org/?list-type=2&prefix=airnow/today/&max-keys=8).

## Not usable now

### GOES fog and low stratus (FLS) and IFR probability

NOAA NESDIS, CIMSS algorithm ([VLab
page](https://vlab.noaa.gov/web/towr-s/goes-16-fog-and-low-stratus)).
**Avoid**; confidence medium; effort L. Verified: **confirmed**.

- **Contents:** MVFR, IFR and LIFR probabilities and fog depth (single-layer
  water clouds); CONUS at 2 km at nadir, every 5 min, files of about 3.2 MB.
  It would be the best fog-extent and fog-thickness product.
- **Access:** only over the satellite broadcast network (GRE and GRW) and
  AWIPS, per VLab; not in the NODD GOES-18 bucket (listing, Oct 7). Getting
  it would need a partnership or an SBN/LDM feed arrangement.
- **License and robots.txt:** not checked, since there's no open
  distribution and no public HTTP endpoint.
- **Personas:** commuter, traffic researcher.
- **Substitute:** RTMA visibility and ceiling, METAR, our own night band 7 −
  band 14 difference, and model low cloud.
- **Verification:** VLab confirms the distribution and specs; the bucket
  listing confirms there's no FLS prefix.
- **Evidence:** [VLab
  page](https://vlab.noaa.gov/web/towr-s/goes-16-fog-and-low-stratus),
  [GOES-18
  products](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/&max-keys=200).

### NWS API (api.weather.gov)

NOAA National Weather Service ([api.weather.gov](https://api.weather.gov/)).
**Needs owner action**; confidence high; effort S. Verified: **confirmed**.

- **Contents:** forecasts, gridded forecast data, observations and alerts
  (CAP), US-wide, as keyless JSON.
- **License:** US government data (not examined further).
- **robots.txt:** `User-agent: *`, `Disallow: /` (re-fetched Oct 7), so it's
  off-limits for automated collection under our rules.
- **Would serve:** warnings such as severe thunderstorm warnings and dense
  fog advisories, and point forecasts, for the fire and weather watcher and
  the commuter.
- **Options:** take warnings from IEM's VTEC services within its 120 s crawl
  delay (confirmed on IEM's `/json/` index), or the owner asks NWS whether
  scheduled API use is welcome despite the robots.txt.
- **Evidence:** [robots.txt](https://api.weather.gov/robots.txt), [IEM's
  JSON index](https://mesonet.agron.iastate.edu/json/).

### Robots-disallowed weather services: nowCOAST, SPC, University of Wyoming, NCEI

NOAA nowCOAST, NOAA Storm Prediction Center, University of Wyoming, NOAA
NCEI. **Avoid**; confidence high; effort S. Verified: **confirmed**.

- **Contents:** nowCOAST's WMS and WFS of radar, satellite and analyses;
  SPC's outlooks; Wyoming's sounding text and plots; NCEI's data paths.
- **robots.txt** (re-checked Oct 7): `nowcoast.noaa.gov` Disallow
  `/geoserver/` (Allow `/`); `www.spc.noaa.gov` `User-agent: *`, Crawl-delay
  10, Disallow `/`; `weather.uwyo.edu` Disallow `/cgi-bin`, `/wsgi` and
  `/upperair/imgs` (the last added by the check); `www.ncei.noaa.gov`
  Disallow `/data*` and `/orders*` (`/pub/data/igra/` isn't covered).
- **License:** not examined, since robots.txt blocks us.
- **Would serve:** nothing we need (fire and weather watcher). Instead:
  MRMS, GOES and HRRR directly; IEM for soundings and the SPC and WPC
  outlooks. Nothing is lost by avoiding these.
- **Evidence:** robots.txt for
  [nowCOAST](https://nowcoast.noaa.gov/robots.txt),
  [SPC](https://www.spc.noaa.gov/robots.txt),
  [UWyo](https://weather.uwyo.edu/robots.txt) and
  [NCEI](https://www.ncei.noaa.gov/robots.txt).

### NOAA GSL HRRR-Smoke website

NOAA Global Systems Laboratory
([HRRR-Smoke](https://rapidrefresh.noaa.gov/hrrr/HRRRsmoke/)). **Avoid**;
confidence high; effort S. Verified: **corrected**.

- **Contents:** smoke forecast graphics (near-surface, vertically integrated
  and 3D smoke; 48 h forecasts at 00, 06, 12 and 18Z), CONUS.
- **License:** no terms stated; the research reported it as marked for
  research purposes only ⚠️ (not re-read).
- **robots.txt** (corrected; fetched Oct 7): `rapidrefresh.noaa.gov` has
  `User-agent: *` with Disallow `/hrrr/HRRRsmoke/` (and `/hrrr/HRRR/`,
  `/RAP/` and others). So the site is robots-disallowed as well as asking
  scrapers to stay away.
- **Instead:** the same model's smoke (MASSDEN) from NCEP's HRRR on AWS; the
  site is a reference only (fire and weather watcher).
- **Evidence:** [the site](https://rapidrefresh.noaa.gov/hrrr/HRRRsmoke/),
  [robots.txt](https://rapidrefresh.noaa.gov/robots.txt).

## Code libraries (server)

These all run in the proposed weather worker image, so they wait on that
decision (open questions). None collects data on its own; robots.txt doesn't
apply.

### ecCodes, cfgrib and xarray (GRIB2 decoding)

ECMWF ([ecCodes](https://github.com/ecmwf/eccodes),
[eccodes-python](https://github.com/ecmwf/eccodes-python),
[cfgrib](https://github.com/ecmwf/cfgrib)) and the
[xarray](https://github.com/pydata/xarray) developers. **Use**; confidence
high; effort S. Verified: **confirmed**.

- **What:** a C library with Python bindings (pip `eccodes`; on Linux and
  macOS the binary library comes from the `eccodeslib` wheel); cfgrib maps
  GRIB to xarray. From PyPI or conda-forge.
- **License:** Apache-2.0 for all four (GitHub license API).
- **Use:** decoding MRMS, HRRR, RTMA and RRFS on the server, for every
  weather persona.
- **Risks:** breaks the ingest's standard-library-only rule, hence the
  separate worker image (owner decision); check that the wheels run on the
  server. cfgrib's features are labelled Beta. MRMS's local discipline-209
  parameters may decode without names ⚠️.
- **Verification:** licenses confirmed (xarray's too, which the research had
  marked ⚠️); the eccodes-python README confirms the bundled binaries; the
  cfgrib README marks features Beta.

### Herbie (model downloads by byte range)

Brian Blaylock and contributors
([GitHub](https://github.com/blaylockbk/Herbie)). **Use**; confidence high;
effort S. Verified: **confirmed**.

- **What:** downloads GRIB2 subsets by `.idx` byte ranges from AWS, Google,
  Azure and NOMADS. Templates include hrrr, rap, rtma, urma, rrfs, refs,
  nexrad, gfs and others. PyPI `herbie-data`.
- **License:** MIT (GitHub license API).
- **Use:** HRRR native-level and RTMA subsets without whole files; RRFS once
  its operational layout settles. Personas: every weather persona.
- **Risks:** a larger dependency tree; our own idx-range client (about 150
  lines) is an option. The README still marks RRFS "(prototype)"; [its
  template](https://github.com/blaylockbk/Herbie/blob/main/src/herbie/models/rrfs.py)
  points at `noaa-rrfs-ops-pds` and a NOMADS `rrfs/v1.0/` path, while SCN
  26-48 gives `rrfs/prod/`.
- **Verification:** license, RTMA/URMA and RRFS support confirmed; the RRFS
  path discrepancy noted.

### Radar toolkits: Py-ART, xradar, MetPy

ARM/DOE ([Py-ART](https://github.com/ARM-DOE/pyart)), openradar
([xradar](https://github.com/openradar/xradar)) and Unidata
([MetPy](https://github.com/Unidata/MetPy)). **Use**; confidence high;
effort M. Verified: **corrected**.

- **What:** Py-ART reads, quality-controls and grids radar data; xradar
  reads NEXRAD Level 2 into xarray (its README lists NexradLevel2); MetPy
  does meteorological calculations and has NEXRAD Level 2 and 3 readers
  (`src/metpy/io/nexrad.py`). PyPI or conda.
- **License** (corrected): Py-ART is a BSD-style Argonne licence, not plain
  BSD-3 (GitHub reports NOASSERTION; the text asks that modified derivative
  works be clearly marked). xradar: MIT code, CC BY-SA 4.0 docs. MetPy:
  BSD-3-Clause.
- **Use:** gridding KCBX Level II; decoding Level 3; inversion and fog-top
  calculations from the Boise soundings. Personas: wildlife, fire and
  weather watcher, sky watcher.
- **Risks:** heavy dependencies (SciPy and others). Mark any modified Py-ART
  code as modified.
- **Verification:** MetPy's NEXRAD reader confirmed (the research had marked
  it ⚠️).

### vol2bird and bioRad (bird migration from radar)

Adriaan Dokter and contributors
([vol2bird](https://github.com/adokter/vol2bird),
[bioRad](https://github.com/adokter/bioRad)). **Use**; confidence medium;
effort L. Verified: **confirmed**.

- **What:** vol2bird (C) computes vertical profiles of birds; `rsl2odim`
  converts NEXRAD to the ODIM format; installation goes through the
  `vol2birdinstall` repository. bioRad (R, on CRAN) wraps and analyses the
  profiles.
- **License:** vol2bird MIT; bioRad MIT (CRAN-style licence file). Linked
  libraries may carry other licences (GSL, for example, is GPL) ⚠️; the
  dependency licences weren't inspected.
- **Use:** the wildlife layer: migration density, speed and direction by
  height over the valley at night. Persona: wildlife.
- **Core pieces:** weather worker image, fields contract.
- **Risks:** needs a C toolchain and libraries: run it as a separate tool
  and don't vendor it into this MIT repo. Needs tuning for S-band NEXRAD.
  Aggregate data only.
- **Verification:** licences confirmed from the LICENSE files.

### Satpy and Supercell Wx

Pytroll ([Satpy](https://github.com/pytroll/satpy)) and Dan Paulat
([Supercell Wx](https://github.com/dpaulat/supercell-wx)). **Use**;
confidence medium; effort M. Verified: **corrected**.

- **What:** Satpy reads and resamples satellite data and has a
  parallax-correction modifier
  ([`satpy/modifiers/parallax.py`](https://github.com/pytroll/satpy/blob/main/satpy/modifiers/parallax.py)).
  Supercell Wx is an open-source NEXRAD Level 2 and 3 viewer in C++.
- **License:** Satpy Apache-2.0; Supercell Wx MIT.
- **Use:** GOES parallax correction and resampling (or a small formula of
  our own); a reference for Level 2 and 3 decoding. Personas: fire and
  weather watcher, sky watcher.
- **Risks:** Satpy is a large dependency; a small parallax function of our
  own may be enough.
- **Verification:** the parallax module confirmed (the research had marked
  it ⚠️); licences confirmed.

## Rendering code and references (browser)

The renderer would be our own WebGL2 engine ([chapter 14](../14-ui-v2.md)),
so these are techniques to port, keeping each licence notice on ported code.

### three-geospatial clouds and atmosphere

Takram
([GitHub](https://github.com/takram-design-engineering/three-geospatial);
`@takram/three-clouds`, `@takram/three-atmosphere`). **Use (techniques)**;
confidence high; effort M. Verified: **corrected**.

- **What:** three.js and React Three Fiber geospatial clouds: Beer shadow
  maps, temporal upscaling (ray-marched texels reduced to 1/16), light
  shafts, haze, quality presets; precomputed atmospheric scattering in
  three-atmosphere. Corrected: the clouds are a layered model of up to 4
  layers whose coverage is packed in one 2D "local weather" texture, with 3D
  noise for shape and detail and an STBN texture; it doesn't take an
  arbitrary gridded 3D density volume. A WebGPU node-based rewrite is in
  progress; the WebGL fallback stays, with an incompatible API.
- **License:** MIT.
- **Use:** port Beer shadow maps, temporal upscaling, STBN jitter and the
  phase functions into our engine; a model for the observation-only slab
  fallback (layers with coverage); a benchmark for quality presets.
  Personas: sky watcher, fire and weather watcher.
- **Risks:** built on three.js and postprocessing, so port techniques, not
  packages, and keep the MIT notice. Its README lists ghosting and smearing
  through sparse clouds and mean-depth aerial-perspective artefacts.
- **Verification:** features, the 4-layer limit, 1/16 upscaling, WebGPU
  status and known issues confirmed in the READMEs ([clouds
  package](https://github.com/takram-design-engineering/three-geospatial/tree/main/packages/clouds)).

### Rendering references: three.js, CesiumJS, Hillaire's sky, NCAR VAPOR

three.js authors, Cesium GS, Sébastien Hillaire and NCAR. **Use**;
confidence high; effort M. Verified: **confirmed**.

- **What:** three.js
  [`webgl_volume_cloud`](https://github.com/mrdoob/three.js/blob/dev/examples/webgl_volume_cloud.html):
  a 128³ RedFormat `Data3DTexture`, hit-box intersection, a fixed-step march
  with threshold and step uniforms, WebGL2. CesiumJS
  [`VoxelPrimitive.js`](https://github.com/CesiumGS/cesium/blob/main/packages/engine/Source/Scene/VoxelPrimitive.js).
  [Hillaire's sky
  atmosphere](https://github.com/sebh/UnrealEngineSkyAtmosphere) (EGSR 2020
  lookup tables, HLSL). [VAPOR](https://github.com/NCAR/VAPOR), desktop 3D
  visualization.
- **License:** three.js MIT; CesiumJS Apache-2.0
  ([LICENSE.md](https://github.com/CesiumGS/cesium/blob/main/LICENSE.md));
  UnrealEngineSkyAtmosphere MIT; VAPOR BSD-3-Clause.
- **Use:** voxel ray-march structure and exaggeration handling (Cesium); sky
  and aerial-perspective lookup tables (Hillaire); offline checks of
  regridded model volumes (VAPOR). Personas: sky watcher, fire and weather
  watcher.
- **Risks:** Hillaire's code is HLSL, to be ported to GLSL ES 3.0.

### webgl-wind (GPU particle wind)

Mapbox, by Vladimir Agafonkin
([GitHub](https://github.com/mapbox/webgl-wind)). **Use**; confidence high;
effort S. Verified: **confirmed**.

- **What:** the wind field in a texture and particle state in textures
  updated on the GPU, "up to 1 million wind particles at 60fps" (README);
  its data script uses ecCodes on GFS.
- **License:** ISC, unlike Mapbox GL JS v2+.
- **Use:** 10 m wind streaks over the terrain for cyclists, fire watchers
  and farmers; particle drift for rain and snow.
- **Core pieces:** 3D engine, fields contract.
- **Risks:** an old WebGL1 demo: port the technique.

### SunCalc (sun and moon position)

Vladimir Agafonkin and contributors
([GitHub](https://github.com/mourner/suncalc)). **Use**; confidence high;
effort S. Verified: **corrected**.

- **What:** sun azimuth and altitude, sunlight phases, moon position,
  moonrise and moonset, and phase, from Meeus's formulas. Corrected: the
  README claims it matches the accuracy of timeanddate.com and the US Naval
  Observatory (no "0.08°" figure found). The altitude is now apparent
  (refraction-corrected), and the README shows an ES-module API (updated Oct
  5, 2026).
- **License:** BSD-2-Clause.
- **Use:** the sun's direction for cloud lighting, shadows, sunshine hours,
  rainbows and glare. Personas: gardener, sky watcher, commuter.
- **Core pieces:** sky context (shared with camera calibration's sun
  context).
- **Risks:** refraction-corrected altitude differs from geometric altitude
  near the horizon, so use the right one for shadows and for sky colour. Pin
  the version after the recent API change.

### MapLibre GL JS sky and fog (already in our stack)

MapLibre ([sky spec](https://maplibre.org/maplibre-style-spec/sky/)).
**Use**; confidence high; effort S. Verified: **confirmed**.

- **What:** `sky-color`, `horizon-color`, `fog-color`, `fog-ground-blend`,
  `horizon-fog-blend`, `sky-horizon-blend` and `atmosphere-blend`, all since
  GL JS 4.5.0, interpolatable and transitionable. `fog-color` needs 3D
  terrain; the sky spec is marked experimental. Already a dependency
  (`maplibre-gl` ^6.12.0 in `app/package.json`).
- **License:** BSD-3-Clause ([LICENSE.txt
  read](https://github.com/maplibre/maplibre-gl-js); GitHub reports
  NOASSERTION because it bundles notices).
- **Use:** Phase 0: distance haze and fog colour from visibility and the
  sun. Personas: commuter, sky watcher.
- **Core pieces:** layer system.
- **Risks:** an experimental spec, and a global effect, not local fog banks.

### Do not copy: Shadertoy shaders and Mapbox GL JS v2+ effects

Shadertoy authors; Mapbox. **Avoid**; confidence medium; effort S. Verified:
**confirmed**.

- **What:** volumetric cloud and rain shaders on Shadertoy; Mapbox GL JS's
  built-in rain ("available in Mapbox GL JS v3.9",
  [docs](https://docs.mapbox.com/mapbox-gl-js/example/rain/));
  [nagix/mapbox-gl-rain-layer](https://github.com/nagix/mapbox-gl-rain-layer)
  (MIT), which draws rain from RainViewer only ("Currently, only rainviewer
  is supported").
- **License:** Mapbox GL JS v2+ is proprietary, "licensed under the Mapbox
  TOS" for use with Mapbox products and an active account
  ([LICENSE.txt](https://github.com/mapbox/mapbox-gl-js/blob/main/LICENSE.txt)).
  Shadertoy's default licence is CC BY-NC-SA 3.0 ⚠️, unverified:
  shadertoy.com sits behind a Cloudflare challenge that we didn't bypass
  ([terms](https://www.shadertoy.com/terms)). The rain layer is MIT but
  needs RainViewer, a third-party aggregator we don't need.
- **robots.txt:** nothing is collected; `shadertoy.com/robots.txt` returned
  the Cloudflare challenge (403).
- **Rule:** ideas only (fire and weather watcher); never copy their code
  into this MIT repository, to avoid licence contamination.

## Ideas by persona

From the research, Oct 7; none chosen. They build on [chapter 16
§16.2](../16-ideas-and-personas.md#162-ideas-by-persona).

### Fire and weather watcher

- **Storm in 3D:** orbit a thunderstorm over the Owyhees or the Boise Front,
  drawn as an MRMS reflectivity volume in a colour-blind-safe palette, with
  translucent 18 and 50 dBZ echo-top shells, a hail core from MESH plus 3D
  Zdr and RhoHV, flashes glowing inside the cloud (GLM) and ground-strike
  marks (MRMS NLDN density). Drag the time bar back two hours to watch it
  grow and drift. A hatched "radar can't see here" zone shows the gap aloft
  over Boise. Sources: MRMS, GLM. Needs: fields contract, 3D engine, full
  replay, layer system.
- **Slice tool:** draw a line on the map and get a vertical curtain standing
  on the terrain: reflectivity, model cloud water and ice, the 0 °C line and
  bright band, temperature, and the terrain profile from the 1 m DEM. A
  forecaster's cross-section, in place on the 3D map. Sources: MRMS, HRRR.
  Needs: fields contract, 3D engine.
- **Virga and dry microbursts:** highlight echoes aloft that never reach the
  ground (MRMS echoes at 3–5 km, no rain rate at the surface, dry METAR and
  road-weather readings), drawn as fading shafts with a gust-risk ring. The
  research calls this a common Boise summer hazard for fire starts and dust
  ⚠️. Sources: MRMS, AWC, 511 road-weather stations, HRRR. Needs: fields
  contract, 3D engine, readings contract.
- **Smoke in 3D** (with the hazards plugin): HRRR-Smoke plumes rising from
  Idaho and Oregon fires and pooling under the valley's inversion lid (drawn
  from the Boise sounding). HMS outlines and the GOES smoke mask check the
  model, FDC hotspots glow, and AirNow PM2.5 gives ground truth if the owner
  gets a key. Sources: HRRR, HMS, GOES Level 2, IEM, AirNow. Needs: fields
  contract, 3D engine, lifecycles contract, Valley Feed.

### Commuter and traffic researcher

- **Fog mornings, measured:** valley-floor fog drawn as translucent layers
  that the foothills poke through, with visibility per road segment and per
  signalized intersection (RTMA rapid update, METAR; road-weather stations
  internally). Replay any fog morning beside the key-camera frames, and list
  fog days from IEM history to test [chapter
  2](../02-treasure-valley-signal-system.md)'s fog → detector fallback →
  long greens theory. Sources: RTMA, AWC, IEM, 511 road-weather stations,
  our camera archive. Needs: fields contract, 3D engine, full replay,
  readings contract.
- **Snow line on my route** (commuter): the melting layer (MRMS bright-band
  top and bottom, the model 0 °C height) drawn where it meets the terrain
  and along I-84, I-184 and SH-55, so you can see where rain turns to snow.
  Particle type switches at that height, freezing-rain areas come from
  HRRR's flags, and road-weather "Ice" badges sit on the roads. Sources:
  MRMS, HRRR, 511 road-weather stations. Needs: fields contract, 3D engine.
- **Weather at the moment of a crash** (safety): for any crash in COMPASS's
  records, replay that hour's weather (MRMS since Oct 2020, HRRR since 2014,
  KCBX Level II for older years, IEM ASOS for visibility), then aggregate
  crash rates by fog, snow, wet roads and low-sun glare. Aggregates only.
  Sources: MRMS, HRRR, NEXRAD Level II, IEM. Needs: fields contract, full
  replay, evidence and review.

### Cyclist

- **Wet or dry ride:** the radar volume pushed forward 0–60 min with HRRR
  winds (later HRRR and RRFS forecast frames) shows when rain reaches the
  Greenbelt; 10 m wind streaks show head- or tailwind along a chosen route,
  with smoke when present. Sources: MRMS, HRRR, HMS, webgl-wind. Needs:
  fields contract, 3D engine, places and search.

### Hiker and camper

- **Summit in the clouds:** shade the terrain that's inside cloud by
  comparing the cloud base (RTMA ceiling, HRRR) with the 1 m DEM: Bogus
  Basin, Shafer Butte, the Owyhees. Add recent lightning near ridges and
  trailheads (GLM, MRMS NLDN density, lightning probability) and the snow
  level on the peaks. Sources: RTMA, HRRR, MRMS, GLM. Needs: fields
  contract, 3D engine, areas.

### Sky watcher and photographer

- **Sea of fog and sunset forecast:** winter inversion fog tops seen from
  the foothills, with the fog-top plane from the Boise sounding and HRRR; a
  chance of sunset and sunrise colour from HRRR cloud layers by height (high
  cloud lit, a clear western horizon) at the real sun position; clear-sky
  hours for stargazing. Sources: HRRR, IEM, GOES Level 2, SunCalc. Needs:
  fields contract, 3D engine, sky context.
- **Rainbow chance:** where the sun is under 42°, the sky toward the sun is
  clear (GOES clear-sky mask) and rain is falling on the opposite side
  within 10–30 km (MRMS), the map marks where to stand and which way to
  face. Sources: MRMS, GOES Level 2, SunCalc. Needs: fields contract, sky
  context.

### Gardener

- **Real sunshine hours for the owner's own yard** (private): cloud
  transmittance toward the sun, summed through the day from HRRR clouds and
  checked against GOES's observed shortwave (DSR), combined with building
  and tree shadows. Also frost nights under clear skies and cold-air pooling
  under the inversion. Sources: HRRR, GOES Level 2, SunCalc. Needs: fields
  contract, sky context, 3D engine.

### Farmer

- **Storms over the fields:** hail swaths (MESH maximum over 24 h) and MRMS
  rainfall totals per field (with the Cropland Data Layer from the farm
  research), hail cores in 3D for the storm that did it, and field-burning
  smoke (HMS) drifting with HRRR winds. Sources: MRMS, HMS, HRRR. Needs:
  fields contract, 3D engine, full replay.

### Wildlife

- **Night migration on radar:** spring and fall nights over the valley show
  bands of birds and insects by altitude, as moving sparkles with direction
  and speed, from KCBX Level II biological echoes (vol2bird profiles, the
  Level 3 biological class), with HRRR winds at those heights to show
  tailwind nights. Aggregate only; radar can't identify individuals.
  Sources: NEXRAD Level II and Level 3, vol2bird and bioRad, HRRR. Needs:
  fields contract, 3D engine, full replay.

### Aviation (the aircraft plugin)

- **Through the clouds:** aircraft tracks drawn through the 3D cloud volume,
  with "in cloud" stretches highlighted. Icing layers come from HRRR
  supercooled cloud water (cloud water where the temperature is below 0 °C),
  ceilings from Boise's METAR and tops from GOES. Sources: HRRR, AWC, GOES
  Level 2. Needs: tracks contract, fields contract, 3D engine.

### Camera validation

- **Does the rendered weather match the camera?** In look-through, the
  rendered fog, rain or snow is drawn over the camera's photo plane, and a
  contrast-based visibility score is read from the image (no people, no
  plates). Disagreements flag bad data or a bad render, and it's a tuning
  loop for the fog and snow constants. Sources: our camera archive, 511
  road-weather stations, RTMA, MRMS. Needs: 3D engine, full replay.

## Design notes (proposed, not decided)

The research's design, with the technical review's corrections folded in;
items the review changed are marked with its numbers (A1 and so on, listed
under [Technical review](#technical-review-oct-67)).

**In short:** every input needed for real 3D weather over the valley is
open, keyless and on AWS through NODD: MRMS gives observed 3D radar; HRRR
gives modelled 3D clouds, smoke and wind; GOES-18 gives observed cloud tops
and lightning; and RTMA, METAR and the Boise sounding pin down the ground
and the fog. The costs are on the server: whole-CONUS GRIB2 files to
download and a scientific Python stack to decode them. In the browser the
volumes are small (under 1 MB a frame for the whole ring), so a laptop GPU
can ray-march them in our own engine. Proposed order: "radar in 3D" from
MRMS, then clouds (HRRR checked against GOES), then fog, inversion and
smoke, then particles, lightning and wind, and finally radar-native detail
and wildlife.

### What gives 3D structure here, and how good it is

- **Observed 3D precipitation:** MRMS, 33 levels on a 0.01° grid every 2
  min, with 3D RhoHV and Zdr every 5 min. Over the valley it's essentially
  KCBX, about 14 km south of downtown (B6). Low down the view is excellent:
  the 0.5° beam centre is 1.10–1.69 km MSL from downtown out to Mountain
  Home and 2.10 km over Ontario, above a valley floor of about 0.66–0.85 km.
  Aloft there's a hole over the city whose floor depends on the scan
  pattern: about 6.0 km MSL over downtown in precipitation VCPs, near 2.5 km
  in clear-air ones ⚠️, with the neighbouring radars' lowest beams 8.9–11.1
  km up (B6). Draw the hole, built per volume from the VCP plus
  `RadarQualityIndex`.
- **Radar-native 3D:** KCBX Level II for detail near Boise and for the
  biological echoes MRMS removes. Level 3 hydrometeor classes per tilt
  (`HHC`, `N0H`–`N3H`) are tiny files.
- **Modelled 3D:** HRRR `wrfnat`, 50 hybrid levels hourly at 3 km: cloud
  water, ice, rain, snow, graupel, cloud fraction, smoke, wind, temperature
  and height (confirmed from a real idx). hrrrzarr has the hydrometeors,
  winds and temperature on 25 mb pressure levels in small chunks (A1). RRFS
  v1 publishes pressure levels only.
- **Satellite 2.5D:** GOES-18 cloud-top height (2 km, 5 min), clear-sky
  mask, phase, optical depth, Cloud Cover Layers (5 flight-level bands at 10
  km), smoke and dust detection, fire, surface shortwave, and GLM flashes
  every 20 s. Parallax: the viewing zenith angle over Boise is 54.5°, so
  tops shift about 1.4 × their height toward the northeast (8.4 km for a 6
  km top); correct this before tops touch the terrain. GOES-East (now
  GOES-19) is at 64.7°, worse. Native pixels over Boise are larger than
  nominal, so the 0.02° grid oversamples about 2× and isn't "2 km data"
  (B11).
- **Ground and column anchors:** METAR cloud layers and visibility (5
  stations in the ring), RTMA rapid-update visibility and ceiling (2.5 km),
  road-weather visibility, precipitation and road state (internal), Boise
  radiosondes at 00Z and 12Z ⚠️ (inversion base and top), and HMS smoke
  polygons (2D).

What each phenomenon is built from:

- **Precipitation:** shape from MRMS 3D reflectivity. Phase by height (B7):
  the bright-band heights are metres above MRMS's own terrain while the 0 °C
  height is above sea level, so convert with MRMS's terrain, not our 1 m
  DEM. "Snow above the band, mixed in it, rain below" fails in the valley's
  winter cold pools, where a warm nose sits over sub-freezing air, which is
  exactly when it matters. So phase comes from HRRR or RRFS temperature
  profiles (ideally wet-bulb), a surface `PrecipFlag` of 3 (snow) overrides,
  and Level 3 `NML` near KCBX is the check. Freezing rain and sleet come
  from HRRR's CFRZR and CICEP flags, since MRMS has no class for them.
- **Clouds:** HRRR mixing ratios converted to extinction. The GOES clear-sky
  mask removes model cloud where GOES sees clear sky, ACHA tops clip or
  extend the tops, and RTMA and METAR ceilings fix the base. The
  observation-only fallback is slabs between a base field (RTMA ceiling) and
  a top field (parallax-corrected ACHA), shaped by the GOES mask and the
  Cloud Cover Layers.
- **Fog:** extinction from visibility (RTMA rapid update, METAR;
  road-weather stations internally). The fog top comes first from the Boise
  sounding's inversion, HRRR low-level cloud water and METAR ceilings. The
  Cloud Cover Layers' lowest band (surface to FL050) is a weak guide (B9):
  it's a pressure altitude, 10 km at nadir and coarser over Boise, and can't
  tell 100 m fog from 700 m stratus. Night extent comes from our own GOES
  band 7 − band 14 difference, since FLS isn't openly distributed.
- **Smoke:** HRRR MASSDEN in 3D, its extent checked by HMS polygons and the
  GOES smoke mask, and by AirNow if the owner gets a key.
- **Lightning:** GLM flashes glow in the cloud; MRMS NLDN density cells (1
  km, 1 min) mark ground strikes; MRMS lightning probability adds a soft
  halo.
- **Wind:** HRRR 10 m wind (NOMADS grib-filter subsets are tiny) and wind on
  levels, for advection and particles.

### From data to optical properties

One documented mapping per product:

- **Light transport:** Beer–Lambert transmittance T = exp(−∫σ ds); single
  scattering with a two-lobe Henyey–Greenstein phase function (artist values
  to tune, such as g = 0.8 and −0.3), sun transmittance from a light volume
  and an ambient term by height. Optionally Schneider's "powder" term and a
  few multiple-scattering octaves.
- **Cloud water and ice:** σ = 3·LWC / (2·ρ·r_e), with LWC = q·ρ_air and ρ
  the density of the condensate: water for liquid, about 917 kg/m³ for ice
  (B10). r_e about 10 µm for liquid and about 30 µm for ice ⚠️ (tunable);
  snow and graupel get much larger r_e, so they stay visually thin and show
  as particles. Check: q = 0.3 g/kg at ρ_air of about 0.9 kg/m³ gives σ ≈ 40
  per km, an in-cloud visibility of about 75 m, which is realistic
  (confirmed by the review).
- **Fog:** σ = −ln(0.05)/MOR ≈ 3.0/MOR (the WMO 5% contrast threshold), or
  3.912/V with Koschmieder's 2%. Pick one and use it everywhere (B10).
- **Rain and snow shafts:** rate from MRMS `PrecipRate`, which is already
  type-aware; Z = 300·R^1.4 is only the convective default (B10). Then an
  empirical visibility (heavy rain about 1–2 km, heavy snow about 0.2–0.5 km
  ⚠️, tunable) and σ = 3/V. Grey for rain, white for snow.
- **Smoke:** σ = mass extinction efficiency (about 4–5 m²/g ⚠️) ×
  concentration. HRRR's MASSDEN is in kg/m³ (× 10⁹ for µg/m³) (B10). 100
  µg/m³ gives σ ≈ 4.5 × 10⁻⁴ per metre, a visibility of 6.7 km at the 5%
  threshold or 8.7 km at 2%. Brown-grey and absorbing (single-scattering
  albedo about 0.9).
- **Radar colours:** a colour-blind-safe sequential ramp (no red–green
  pair), with precipitation type shown by particle shape (streak, flake,
  hail sphere), never by colour alone. The classic NWS palette only with
  labels.

### Server pipeline

A new `weather` plugin with its own worker image:

- **Sources** in `plugins/weather/ingest/`:
  - `mrms_volume`: a stream, 10 min by default and 2 min when convective;
    gated.
  - `mrms_surface`: flag, rate, bright band, echo tops, quality, NLDN
    density, MESH.
  - `hrrr_native`: hourly f00 plus f01–f18 of the latest run. Per A1,
    clouds, winds and temperature come from hrrrzarr's chunks, and `wrfnat`
    byte ranges only for MASSDEN, FRACCC and perhaps the near-surface hybrid
    levels for fog, behind one model adapter for `wrfnat`, hrrrzarr and RRFS
    `prslev`.
  - `goes_clouds`: ACHA2KM, ACM, CCL and ADP every 10 min, by chunk reads.
  - `glm_flashes`: gated by MRMS.
  - `rtma_ru`: visibility and ceiling, hourly by default, every 15 min only
    when METAR or road-weather stations report fog (A2).
  - `metar` every 5 min; `raob_boi` at 00Z and 12Z through IEM, one request
    per 120 s; `hms_smoke` twice a day.
  - Later: `nexrad_l2_kcbx` and `nexrad_l3_kcbx`.
- **Worker image** `weather-worker`: Python 3.11 plus numpy, eccodes (the
  pip wheel bundles the C library), pyproj, h5py or netCDF4, and later
  Py-ART or xradar. It breaks the ingest's standard-library-only rule, so
  it's the owner's decision; check that the wheels run on the server. Raw
  downloads go to a scratch directory and are deleted after cropping; only
  bricks are kept.
- **Politeness:** an honest User-Agent everywhere. The NODD buckets have no
  robots rules; NOMADS gets at most about 10 hits a minute against its limit
  of 120; IEM one request per 120 s; AWC well under 100 a minute.
- **Grids:**
  - Latitude and longitude aligned to MRMS, so the shader maps exactly:
    radar 0.01° (170 × 140 for the ring), model 0.03° (57 × 47), GOES 0.02°.
    HRRR's Lambert grid is resampled with a precomputed index map. GOES is
    parallax-corrected per pixel using its own top height.
  - Vertical: MRMS keeps its native levels up to 12 km (26 levels, mapped
    through a 1D z-lookup texture). The draft resampled model fields to 48
    levels of 250 m from 0.25 to 12 km MSL, using HGT on every fifth hybrid
    level. That puts about 2 levels underground and is too coarse for fog
    and smoke pooling, which are often 100–300 m deep (B8): add
    terrain-following near-surface levels (for example 25–50 m apart in the
    lowest 600 m above ground, from HRRR's lowest hybrid levels), or render
    fog analytically and keep the coarse grid for clouds aloft.
- **Encoding:** uint8 per channel, with a scale and offset in the header.
  - Reflectivity: a 5–80 dBZ ramp over codes 1–254, with missing → 0 and no
    coverage → 255, mapping MRMS's two nodata pairs explicitly (A3). The
    draft's round((dBZ + 32)·2) wasted codes 1–73.
  - Mixing ratios and smoke: log-scaled (for example q from 10⁻⁷ to 10⁻²
    kg/kg onto 1–254).
  - Related fields share channels: RGBA8 for cloud liquid, cloud ice, snow
    plus graupel, and rain; R8 for cloud fraction and for smoke.
- **Header JSON:** product, valid time, run, lead, dimensions,
  lat0/lon0/dlat/dlon, z levels, encoding, nodata, an occupancy summary (the
  maximum per 8 × 8 × 4 brick, for skipping empty space) and the credit
  line.
- **Files:** `.bin`, precompressed (gzip or brotli), under immutable
  content-hashed names (`/fields/<product>/<yyyymmdd>/<hhmm>.<sha>.bin`),
  served by Caddy like the camera frames. Raw bytes plus HTTP compression
  beat KTX2 or Basis here: WebGL2 can't upload compressed 3D textures
  portably, and our volumes are under 1 MB. A PNG slice atlas only as a
  debugging view.
- **Database:** `obs.field_frame` (product, valid_time, run_time, lead_min,
  path, bytes, sha, dims, stats jsonb) as a hypertable. Flashes go to a
  small `obs.lightning_flash` table (time, lat, lon, area, energy).
- **API:** `GET /api/weather/frames?product&from&to` gives the frame list
  and the availability strip for the time bar; bricks are fetched from their
  immutable URLs.
- **Retention** (proposed): MRMS at full cadence for 14 days, then thinned
  to 10 min; HRRR f00 kept indefinitely, forecasts 7 days; derived GOES
  slabs 30 days.

### Sizes

Measured where marked; otherwise estimates ⚠️.

- **Downloads:**
  - MRMS: a 3D level about 1.10 MB (measured), so about 28 MB per 12 km
    volume; about 4 GB a day at 10 min while echoes are present and 20 GB a
    day at 2 min. The gate (`PrecipFlag` every 10 min, 0.2 MB each) costs
    about 30 MB a day.
  - HRRR `wrfnat` per hour, all 50 levels (measured): hydrometeors about 9
    MB, cloud fraction 9.7, smoke 53.5, HGT 94.0, PRES 117.1, U 40.8, V
    39.9. The proposed pull is about 43 MB an hour, plus smoke when gated
    (A1). With clouds and winds from hrrrzarr instead, well under 25 MB an
    hour ⚠️ plus FRACCC and MASSDEN.
  - RTMA rapid update: about 15 MB per analysis, so 1.4 GB a day at 15 min
    or about 360 MB a day hourly (A2).
  - GOES: ACHA2KMC 4.5 MB, ACMC 3.8 MB and CCLC 0.4 MB every 5 min
    (measured), with chunk reads much smaller. GLM is 30 MB an hour
    unfiltered (measured), so it's gated.
  - KCBX Level II: 1.22 GB a day in clear air (measured).
- **Stored bricks:** radar 619 KB raw, about 50–200 KB compressed with
  echoes; HRRR clouds 514 KB raw an hour; a GOES slab about 50 KB; the
  static ring heightfield 512 × 512 at 16 bits, about 0.5 MB. Expect under
  30 MB a day on dry days and about 150–400 MB a day on stormy days with
  2-minute radar.
- **GPU memory:** a 1-hour radar window at 2 min (30 frames × 0.62 MB) is
  about 19 MB; 24 hours of HRRR about 20 MB. Keep weather under 64 MB in
  total.

### Browser renderer

In our own engine, not deck.gl or three.js:

- **Packaging:** a lazy chunk (`plugins/weather/app`, using the `#lib/gl`
  helpers), loaded only when a weather layer is turned on, 30 KB gzipped or
  less. One custom layer, `weather-3d`, in a new slot between the scene and
  points slots so points and labels stay readable above the weather. In code
  (`app/src/lib/map/order.ts`) those slots are `anchor:scene` and
  `anchor:points` (the "9" and "10" came from [chapter 14](../14-ui-v2.md)'s
  table): add an `anchor:weather` to `ANCHORS` (C19). A custom layer after
  the draped block won't change the `rttStacks` test, but any new 2D drape
  (composite radar far out, cloud shadows) must sit inside the draped block
  so the test still finds one draped run.
- **Projection,** by the scene engine's rules: MapLibre's
  `defaultProjectionData.mainMatrix`, with the matrix built relative to the
  centre in float64 on the CPU. The fragment shader rebuilds each ray from
  the inverse matrix and marches in local metres. Texture coordinates are
  exact: u = (lon − lon0)/dlon from Mercator x; v from lat = 2·atan(exp(y))
  − π/2, computed per sample, where y must be in radians, y = π·(1 −
  2·y_norm) from MapLibre's normalized y (C15); w through the z-lookup
  texture. The metres-to-Mercator scale changes by about 2.3% across the
  ring, so a single centre scale gives about 1% height error at the edges
  (about 100 m at 10 km): apply the per-sample latitude scale, or accept and
  document it (C15). If globe projection is ever enabled, `mainMatrix` alone
  isn't enough.
- **Heights and exaggeration:** atmosphere heights render as z_rendered =
  exaggeration × z_MSL, so a fog top at 1,000 m MSL meets the hillside
  exactly where the drawn terrain is at 1,000 m. This deliberately differs
  from the rule for buses and poles, which sit at a height above the drawn
  ground. An optional "atmosphere stretch" (2–5×) for reading 10 km storms
  at valley scale is always labelled when on.
- **Occlusion:** MapLibre doesn't expose its depth buffer as a texture, so:
  - our own half-resolution depth pre-pass draws the terrain (later building
    boxes) and rays stop at that depth. The draft's 256² DEM over the ring
    has cells of about 0.55 × 0.6 km, far too coarse at zoom 12–15, where
    volumes would bleed through hills: use a view-dependent heightfield
    instead, such as the terrain tiles already loaded, at about screen
    resolution (C13);
  - ground-hugging fog: the draft drew 16–32 stacked horizontal planes,
    depth-tested against MapLibre's depth buffer so hills pierce them. They
    band at grazing angles and overdraw the whole valley, so the review
    prefers an analytic height-fog integral (closed form for slab or
    exponential profiles) evaluated per pixel against the pre-pass depth;
    keep planes only if buildings must pierce the fog and the pre-pass can't
    provide that (C14);
  - the main volume renders at half resolution into our own framebuffer
    (saving and restoring `FRAMEBUFFER_BINDING`), then composites with a
    depth-aware upsample.
- **Ray-march per pixel:**
  - intersect the ring box and clip to the pre-pass depth;
  - step through an occupancy brick texture (about 22 × 18 × 7) to skip
    empty space; weather volumes are mostly empty, so this is the main
    speed-up;
  - march from a blue-noise offset with step max(half a voxel, k ×
    distance), where half a voxel is the smallest extent along the ray: MRMS
    voxels are about 1.1 × 0.8 km across and 0.25–0.5 km tall, so thin
    layers alias otherwise (C17);
  - sample density (hardware trilinear), apply the transfer function (σ,
    albedo and colour per type) and the lighting;
  - accumulate front to back and stop once transmittance drops below 0.01.
- **Light volume:** a half-resolution 3D texture of transmittance toward the
  sun, rendered layer by layer with `framebufferTextureLayer` (24–32 steps
  per texel), rebuilt only on a new data frame or when the sun moves more
  than 0.5°, so per-frame lighting is one lookup. R8 and RGBA8 are
  renderable in core WebGL2; R16F layers need `EXT_color_buffer_float` or
  its half-float variant (C16). The sun comes from SunCalc, shared with the
  sky and gardener features and with camera calibration's sun context.
- **Detail below the model's 3 km:** a 64³ Worley-Perlin noise generated in
  code (no asset licence) erodes cloud edges where cloud fraction is
  0.2–0.8. The UI calls it texture, not data, and a toggle turns it off.
- **Fallback cloud slabs:** a ray-march between two height-field textures
  (base and top), with coverage and noise.
- **Inversion lid:** one translucent plane at the inversion base or top,
  labelled with temperatures from the sounding.
- **Particles:** instanced quads in a box that follows the camera (about 400
  m wide, 200 m tall), animated in the vertex shader from a seed, time, fall
  speed (rain 4–9 m/s, snow about 1 m/s) and HRRR 10 m wind. Count follows
  the rain rate; type follows the flag and the height relative to the bright
  band. Only at zoom 14 and above, or in look-through. Budget 5k–40k
  instances in 1 ms or less.
- **Lightning:** GLM flashes become emissive points at the flash centroid,
  at about 0.6 × the echo top, sized from the flash area and decaying over
  200–400 ms. NLDN density cells get a stylized bolt from cloud base to
  ground, labelled "strike density cell, about 1 km". In replay, 5-minute
  afterglow dots stay on the ground.
- **Wind:** webgl-wind's technique (particle state in textures) for 10 m
  wind on the terrain at zoom 8–12; 3D streamlines aloft are optional.
- **Cloud shadows:** transmittance projected along the sun onto a draped 2D
  texture, updated at most once per data frame or sun step, within the
  render-loop rule of no per-frame source changes.
- **Sky:** Phase 0 drives MapLibre's fog properties (`fog-color`,
  `horizon-fog-blend`, `fog-ground-blend`) from visibility and the sun.
  Later, Hillaire-style lookup tables (MIT, ported from HLSL) give correct
  aerial perspective and sunlit clouds.
- **Time:**
  - radar and GOES (2–10 min apart): blend two frames;
  - hourly model fields: interpolate along the wind, sampling x − u·τ·Δt in
    one frame and x + u·(1 − τ)·Δt in the next (Δt added by C18). This
    reduces ghosting but doesn't remove it, since clouds grow and decay;
  - replay at 60× or 600× steps through frames with a prefetch window of
    about ±5 frames.
- **By zoom:** at zoom 8 and below, 2D draped composite radar and cloud-top
  imagery, no volumes; zoom 8–13, volumes (mipmapped 3D textures,
  `textureLod` by distance), fog and lightning; zoom 14 and above or
  look-through, particles and dense near-ground fog too. KCBX Level II
  detail later, near Boise only.
- **Render loop:** weather asks for a repaint only when the camera, the
  clock or a flash animation changes. While the camera is still, jittered
  frames accumulate for about 8 frames and then stop, so idle cost is close
  to zero.

### Performance budgets

- **Targets:** the weather pass at 4 ms of GPU time or less per frame while
  moving, about 0 when idle (accumulated and cached); 64 MB of GPU memory or
  less; 300 KB or less per data frame; no `setData` per frame and no Svelte
  state writes per frame.
- **Ray budget:** the draft counted half resolution of a 1440 × 900 view as
  about 324k rays × at most 64 effective steps after skipping, about 20
  million samples, or 2–4 ms on a recent integrated GPU ⚠️ (estimate). On a
  high-density display (devicePixelRatio 2), half resolution in device
  pixels is 1.3 million rays, 4× that (C12): either render at a quarter of
  device resolution per axis (half of CSS pixels) with depth-aware
  upsampling, or budget about 4× the GPU time. Measure with the perf harness
  and in the owner's browser; the owner's GPU isn't known yet.
- **Quality presets:** low, medium and high vary the resolution scale, step
  count, light-volume resolution and noise. If frame time stays above 20 ms,
  the renderer drops a preset by itself.
- **WebGL2 limits:** `MAX_3D_TEXTURE_SIZE` is at least 256 everywhere (all
  our dimensions are 170 or less); R8, RG8 and RGBA8 filter linearly; R16F
  filters in core WebGL2; R32F linear filtering needs
  `OES_texture_float_linear`, so avoid it. R16 unorm needs
  `EXT_texture_norm16` and R16UI doesn't filter, so the heightfield is R16F
  (about a 1 m step at valley heights) or R32F with manual bilinear
  filtering (C16). Rebuild everything on `webglcontextrestored`.

### Honesty and UI

- Every weather layer shows its source and valid time, plus a chip saying
  "observed", "model" or "derived", and "texture" when the noise is on.
- The radar-blind volume is hatched.
- Where HRRR has cloud but GOES says clear, a small mismatch marker appears.
- "No echoes in the area" is said, not left blank.
- The time bar shows an availability strip per product.
- Credits read "NOAA MRMS/HRRR/GOES (derived)". Road-weather data stay
  internal.
- Where weather sits in the UI: the draft offered the Sky lens or a new
  Weather lens, but UI v2 replaced lenses with combinable toolbar layers
  ([DECISIONS](../DECISIONS.md), Oct 6), so the question is which toolbar
  group (D20).

### Phases

MVP first; each phase ends with screenshots and performance numbers.

- **Phase 0, groundwork** (about 1 week): the plugin manifest; METAR, RTMA
  rapid-update visibility and ceiling, and Boise soundings as readings; sun
  position; MapLibre's sky fog driven by visibility; the decisions on the
  fields contract and the worker image.
- **Phase 1, MVP "radar in 3D"** (2–3 weeks): MRMS gated ingest at 10 min,
  plus `PrecipFlag`, bright band, quality and echo tops; bricks, the frames
  API and the replay blend; the `weather-3d` layer with the ray-march, the
  terrain pre-pass, the colour-blind-safe transfer function and the
  radar-blind mask. Done when a real storm or snow event replays at 60 fps
  at zoom 10 in the owner's browser and matches the camera frames and
  road-weather precipitation.
- **Phase 2, clouds** (3–4 weeks): HRRR ingest (hrrrzarr plus `wrfnat` byte
  ranges, per A1) and resampling to the model grid; extinction, the light
  volume, noise detail and shadows; GOES ACHA, ACM and CCL with parallax
  correction; the observation-only slab fallback.
- **Phase 3, fog, inversion and smoke** (2–3 weeks): fog from visibility
  (RTMA, METAR; road-weather internally) with tops from the sounding and
  HRRR; night fog extent from the GOES band difference; the inversion lid;
  HRRR smoke gated by HMS, with GOES smoke-mask overlays.
- **Phase 4, particles, lightning and wind** (2–3 weeks).
- **Phase 5, later:** KCBX Level II detail and dual-pol; Level 3 classes;
  the wildlife migration layer (vol2bird); RRFS forecasts and the
  fire-weather nest; a crash-weather history backfill (MRMS from Oct 2020,
  HRRR from 2014, Level II before that).

### Risks and mitigations

1. **Bandwidth:** MRMS files cover all of CONUS (about 28 MB per volume).
   Gate on `PrecipFlag`, default to 10 min, use 2 min only for convection,
   and fetch levels only up to 12 km. RTMA hourly by default.
2. **Scientific dependencies** break the standard-library-only rule: a
   separate worker image; check its wheels and disk use on the server.
3. **Disk:** keep bricks, not raw files; set retention; about 30–400 MB a
   day.
4. **Unknown GPU:** presets, automatic downgrade, half resolution plus
   accumulation; quarter resolution on high-density displays (C12).
5. **Integration:** no depth texture from MapLibre (our own pre-pass,
   analytic fog); label order; the one-draped-run rule; context loss.
6. **Truthfulness:** model clouds aren't observations; 3 km can't make
   cumulus (the texture is labelled); the radar gap aloft over Boise
   (VCP-dependent) and terrain blocking; GOES parallax of about 1.4 × top
   height; the empirical constants for rain, snow and smoke visibility are
   tunable ⚠️.
7. **Sources that change:** RRFS becomes operational on Oct 14, 2026 and
   will eventually replace HRRR, so ingest goes through a model adapter;
   GOES-West could change satellite.
8. **Terms:** NODD data may be used freely, but derived products must be
   labelled as derived; road-weather data stay internal; api.weather.gov's
   robots.txt disallows all, so no warnings from it; no Shadertoy or Mapbox
   GL v2+ code; keep MIT, Apache, BSD and ISC notices on ported code.
9. **Replay cost:** at 600×, about 5 radar frames a second. Prefetch, and
   drop to 10-minute frames at high speeds.

### Not used, and why

- deck.gl and Cesium as runtimes: deck.gl crashes on MapLibre 6, and the
  owner chose our own WebGL layer ([DECISIONS](../DECISIONS.md), Oct 6).
- GOES FLS: distributed only over the satellite broadcast network.
- The NWS API, nowCOAST's geoserver, the SPC site and Wyoming's soundings:
  robots.txt disallows us.
- GSL's HRRR-Smoke site: robots.txt disallows it, and it asks scrapers to
  stay away.
- IEM's NEXRAD and model mirrors: disallowed; use AWS.
- RainViewer, Windy and commercial lightning networks: not needed (their
  terms weren't checked in this research).
- Mapbox GL effects code: proprietary.

### Technical review (Oct 6–7)

The verifier's review of the design, ordered by how much each item changes
the plan. Figures were re-measured on Oct 6–7; the evidence is in each
source entry above.

**A. Data cost and pipeline**

1. **HRRR sizes:** HGT is 94.0 MB, not 113.1; PRES 117.1 (not 121.7), UGRD
   40.8 (not 44.3), VGRD 39.9 (not 43.5), MASSDEN 53.5 (not 54.3).
   Hydrometeors, FRACCC and "HGT every fifth level ≈ 20 MB" were right. The
   pull is about 43 MB an hour, not 35–40. Bigger change: hrrrzarr's `prs`
   store has the clouds, HGT, TMP, winds and VVEL on 25 mb levels, current
   to Oct 7, in chunks of about 10–17 KB, so take those from 1–4 chunks per
   level and keep `wrfnat` byte ranges for MASSDEN, FRACCC and perhaps
   near-surface levels, behind a model adapter for `wrfnat`, hrrrzarr and
   RRFS `prslev`. Only the analysis store was checked.
2. **RTMA rapid update isn't cheap:** about 15 MB per 15-minute analysis
   (VIS 6.55 MB, CEIL 8.43 MB), about 1.4 GB a day. Default to hourly (about
   360 MB a day); 15-minute only when METAR or road-weather stations report
   fog, or crop on NOAA's side if NOMADS offers an RTMA filter (unverified).
3. **MRMS nodata:** −99 missing and −999 no coverage in 3D; −1 and −3 in 2D;
   the notes conflated them. Map both explicitly (missing → 0, no coverage →
   255), and use a 5–80 dBZ ramp over 1–254. The 0.50 and 0.75 km levels are
   effectively always empty here.
4. **RRFS:** pressure-level hydrometeors confirmed in `noaa-rrfs-ops-pds`
   (populated since Aug 13); no 3D smoke, only MASSDEN at 8 m and column
   COLMD, so HRRR `wrfnat` stays the only 3D smoke source. The prototype
   bucket stopped Aug 12; no NOMADS grib filter; Herbie's `rrfs/v1.0/` path
   differs from the SCN's `rrfs/prod/`.
5. **KCBX Level II:** 202 volumes plus 24 `_MDM` files on Oct 5, not 226
   volumes; 1.22 GB is right.

**B. Physics and geometry**

6. **Radar position and the gap aloft:** KCBX is south of downtown (bearing
   191°), not south-southeast. The 19.5° tilt reaches about 6.0 km MSL over
   downtown and 7.5 over Meridian, not 5.7 and 7.1, and exists only in
   precipitation VCPs; clear-air and light-precipitation VCPs put the gap's
   floor near 2.5 km over downtown ⚠️, common in winter stratiform snow.
   Neighbours' 0.5° beams: about 8.9 (KSFX), 8.9 (KPDT) and 11.1 km (KLRX),
   lower edges 6.3–8.4 km (coordinates from memory ⚠️). Build the mask per
   volume from the VCP in Level II metadata.
7. **Precipitation phase:** bright band in m above MRMS's terrain, 0 °C
   height in m MSL; convert with MRMS's terrain. The simple layering fails
   in winter cold pools with a warm nose (freezing rain, sleet); use HRRR or
   RRFS (wet-bulb) temperature profiles, let a surface `PrecipFlag` of 3
   override, and check against Level 3 `NML`.
8. **Vertical grid:** 48 × 250 m from 0.25 km puts about 2 levels
   underground and is too coarse for 100–300 m fog and smoke; add
   terrain-following levels 25–50 m apart in the lowest 600 m, or render fog
   analytically.
9. **Fog top from Cloud Cover Layers is weak:** a pressure altitude, 10 km
   at nadir, can't separate 100 m fog from 700 m stratus; VLab gives only a
   60% requirement, and the "full validation May 2025" and "can't see low
   under high" claims weren't found. Use the sounding, HRRR low-level cloud
   water and METAR ceilings first.
10. **Optics:** ice density about 917 kg/m³ for ice; MASSDEN in kg/m³; be
    consistent between 3.0/V and 3.912/V (the smoke example gives 6.7 or 8.7
    km); Z = 300·R^1.4 is the convective default only, so prefer
    `PrecipRate`; the rain and snow constants stay ⚠️ tunable.
11. **GOES:** the 0.02° grid oversamples about 2× over Boise; the band 7 −
    band 14 fog difference is night-only; GOES-East is now GOES-19; GLM
    positions can be several km off ⚠️; NLDN cells are averages, not strikes
    (already labelled).

**C. Renderer**

12. **High-density displays:** at devicePixelRatio 2, "half resolution of
    1440 × 900" in device pixels is 1.3 million rays, 4× the estimate;
    render at a quarter of device resolution per axis with depth-aware
    upsampling, or budget about 4× the GPU time. Measure with the perf
    harness.
13. **Pre-pass resolution:** a 256² DEM over the ring (about 140 × 155 km)
    has 0.55 × 0.6 km cells, too coarse at zoom 12–15; use a view-dependent
    heightfield such as the loaded terrain tiles.
14. **Stacked fog planes** band at grazing views and overdraw heavily; an
    analytic height-fog integral against the pre-pass depth is cheaper and
    band-free.
15. **Mercator scale** changes about 2.3% across the ring (sec 42.9° to sec
    44.3°), about 1% height error at the edges with a centre scale; apply
    the per-sample scale or document it. The latitude formula needs y in
    radians; globe projection would need more than `mainMatrix`.
16. **WebGL2 formats:** R16 unorm needs `EXT_texture_norm16` and R16UI
    doesn't filter, so use R16F (about 1 m steps at valley heights) or R32F
    with manual bilinear; rendering the light volume into R16F needs
    `EXT_color_buffer_float`. The other limits in the notes are right.
17. **Anisotropic voxels:** the half-voxel step must use the smallest extent
    along the ray.
18. **Time interpolation:** displacements need Δt; advection reduces
    ghosting but doesn't avoid it.
19. **Layer slots:** in `order.ts` the slots are `anchor:scene` and
    `anchor:points`; add `anchor:weather`. A custom layer after the draped
    block doesn't change `rttStacks`, but new 2D drapes must sit inside the
    draped block.

**D. Terms and policy**

20. **Lenses:** UI v2 replaced lenses with combinable toolbar layers, so ask
    "which toolbar group".
21. **NWS warnings:** api.weather.gov is still `Disallow: /`; IEM's VTEC,
    storm-based warning and SPC/WPC outlook services are allowed, within its
    120 s crawl delay.
22. **AirNow:** preliminary data, labelled as such; values "should not be
    altered" and not for trends; credit the reporting agencies and AirNow;
    EPA's AQI colours clash with our colour rule unless labelled; a signed
    agreement form. Files appear keyless ⚠️. The owner decides on the form
    and on a key versus files.
23. **HMS:** the OSPO page's `HMS2` link is 404; the live data are under
    `/pub/FIRE/web/HMS/`.
24. **GSL HRRR-Smoke:** robots.txt disallows `/hrrr/HRRRsmoke/`, so "avoid"
    rests on robots.txt as well as the site's own warning.
25. **Code licences:** Py-ART is BSD-style (Argonne) and asks that modified
    derivatives be marked; three-clouds is a coverage model of up to 4
    layers, not a gridded-volume renderer (port its lighting, upscaling and
    noise, not its data model; it suits the slab fallback); SunCalc claims
    parity with USNO and timeanddate.com, not 0.08°, and its altitude is
    refraction-corrected; Shadertoy's default licence is still unverifiable.

**E. Confirmed as written:** KCBX's 0.5° beam heights; GOES-18's 54.5°
viewing angle and 1.4× parallax, and GOES-East's 64.7°; MRMS cadence,
levels, units and `PrecipFlag` codes, and its archive from 2020-10-14;
NOMADS's 120 hits a minute per IP; the sizes of GLM, GOES Level 2, MCMIPC
and the MRMS levels; the cloud extinction check (about 40 per km, about 75
m); the ring-crop and occupancy-grid arithmetic (22 × 18 × 7); NODD's
licence wording; RRFS on Oct 14 replacing NAM, HREF, SREF and HiresW; the
robots.txt results for every NODD bucket, NOMADS, AWC, IEM, nowCOAST, SPC,
Wyoming, NCEI and api.weather.gov.

## Open questions for the owner

1. **Worker image:** may the weather plugin have its own image with
   scientific Python (numpy, ecCodes and cfgrib, pyproj, h5py, later
   Py-ART)? It would be an exception to the ingest's standard-library-only
   rule. Do those wheels run on the server (checked against the private
   server notes)?
2. **Bandwidth:** what's the budget on the server's internet connection, and
   is there a data cap? Radar comes only as whole-CONUS files: about 4 GB a
   day at 10-minute frames on days with rain, about 20 GB a day at 2
   minutes; dry days cost about 30 MB.
3. **Disk and retention for weather bricks:** estimated under 30 MB a day
   dry and 150–400 MB a day stormy. Proposed: full cadence for 14 days, then
   thinned.
4. **Fields as a core time shape:** should gridded 2D and 3D data over time
   become a fourth core time shape beside tracks, readings and lifecycles?
   Weather, smoke, snow, land cover over time and imagery years would all
   use it.
5. **Plugin split:** one `weather` plugin owning MRMS, HRRR, GOES and the
   observations, with `hazards` (smoke, lightning, fire) and `sky` (sun,
   atmosphere) using it, or one combined plugin? And which toolbar group:
   Sky, or a new Weather group (D20)?
6. **Drawing order:** should weather draw under the labels and point symbols
   (proposed), or over them as real clouds would?
7. **Atmosphere heights:** render at the terrain's exaggeration so fog and
   cloud meet the hillsides correctly (proposed), with an optional labelled
   2–5× atmosphere stretch?
8. **GPU target:** which GPU should the quality presets and the 4 ms budget
   be tuned for?
9. **NWS API:** api.weather.gov's robots.txt disallows everything. Treat it
   as off-limits, ask NWS, or take warning history from IEM within its crawl
   delay?
10. **Fog layer:** build the public layer from NOAA inputs only and keep
    road-weather stations as internal points (proposed), or blend them in
    and make the fog layer internal?
11. **Forecasts:** stay on HRRR until it retires, or add RRFS (operational
    Oct 14, 2026; pressure levels only) for 84-hour forecasts and its
    fire-weather nest?
12. **AirNow:** would the owner register for a key for smoke ground truth?
    The data-use guidelines, with their signed form, need reading first.
13. **History for crash research:** how far back? MRMS from Oct 2020 and
    HRRR from 2014 are on AWS; KCBX Level II goes back further.
