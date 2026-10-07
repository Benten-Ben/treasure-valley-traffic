# 17. Sources for new plugins (Oct 7 research)

Where the data could come from for the plugins that the owner's Oct 7
interests point to ([chapter 16 §16.1](16-ideas-and-personas.md#beyond-traffic-oct-7)):
wildlife, the sky, gardening, weather (including real weather drawn in 3D),
farms and crops, hiking, camping and land permissions, cycling and walking,
and fires and hazards. The plugin model is in [chapter 15](15-plugins.md)
and the ideas by persona are in [chapter 16](16-ideas-and-personas.md).
This chapter is the overview: the best sources and a first thing to build
for each persona, the core pieces the sources keep asking for, a proposed
order, a phased design for 3D weather, what to avoid, and the owner's
actions and open questions. Every source's details (endpoints, licenses,
robots.txt results, sizes and evidence links) are in the ten theme
catalogs under [docs/sources/](sources/).

**Status: research only; nothing here is decided.** Each source still goes
to the owner one at a time before we commit to how it's used
([SOURCES](SOURCES.md), [DECISIONS](DECISIONS.md)). The order in §17.4 and
the 3D weather design in §17.5 are proposals. ⚠️ marks anything resting on
secondary or unverified sources, or a figure the verification didn't re-run.

**How it was checked.** For each theme, a researcher catalogued sources on
Oct 6–7, 2026. A second agent then re-checked every entry against the
publisher's official pages, its robots.txt (fetched again with our honest
User-Agent) and its terms. Each entry came out **confirmed** (as written),
**corrected** (the catalog gives the corrected version) or
**unverifiable**. Claims that turned out false are listed as refuted in
§17.6. The verdicts are the research's recommendation, not a decision:
**use**; **internal only** (use, but don't republish the data itself);
**needs owner action** (an account, a request, a hand download or a
dependency decision comes first); **avoid**.

| Theme | Catalog | Persona (ch. 16) and plugin (ch. 15) | Entries | Confirmed / corrected / unverifiable | Use / internal only / owner action / avoid |
|---|---|---|---|---|---|
| Weather | [sources/weather.md](sources/weather.md) | [Fire and weather watcher](16-ideas-and-personas.md#fire-and-weather-watcher-hazards-weather); `weather` | 30 | 14 / 16 / 0 | 21 / 1 / 5 / 3 |
| Weather in 3D | [sources/weather-3d.md](sources/weather-3d.md) | [§16.5](16-ideas-and-personas.md#165-weather-in-3d-the-owners-idea-oct-7); `weather` | 31 | 16 / 15 / 0 | 23 / 2 / 2 / 4 |
| Fire and hazards | [sources/hazards.md](sources/hazards.md) | [Fire and weather watcher](16-ideas-and-personas.md#fire-and-weather-watcher-hazards-weather); `hazards` | 34 | 20 / 13 / 1 | 23 / 0 / 6 / 5 |
| Wildlife | [sources/wildlife.md](sources/wildlife.md) | [Wildlife](16-ideas-and-personas.md#wildlife-wildlife); `wildlife` | 28 | 13 / 14 / 1 | 18 / 1 / 5 / 4 |
| Sky | [sources/sky.md](sources/sky.md) | [Sky watcher and photographer](16-ideas-and-personas.md#sky-watcher-and-photographer-sky); `sky` | 43 | 27 / 14 / 2 | 28 / 1 / 6 / 8 |
| Gardening | [sources/gardening.md](sources/gardening.md) | [Gardener](16-ideas-and-personas.md#gardener-new-oct-7); `gardening`, private `home` | 32 | 14 / 17 / 1 | 21 / 0 / 6 / 5 |
| Farms and crops | [sources/farm.md](sources/farm.md) | [Farmer](16-ideas-and-personas.md#farmer-farm); `farm` | 29 | 17 / 12 / 0 | 18 / 1 / 6 / 4 |
| Land ownership and permissions | [sources/lands.md](sources/lands.md) | [Hiker, camper, hunter](16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water); `lands` | 22 | 12 / 9 / 1 | 15 / 4 / 1 / 2 |
| Trails and recreation | [sources/trails.md](sources/trails.md) | [Hiker, angler, floater](16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water); `trails`, water | 29 | 16 / 13 / 0 | 22 / 1 / 3 / 3 |
| Cycling and walking | [sources/cycling.md](sources/cycling.md) | [Cyclist and pedestrian](16-ideas-and-personas.md#cyclist-and-pedestrian-safety-roads); `safety`, `roads` or a new `active` | 28 | 17 / 11 / 0 | 13 / 8 / 3 / 4 |
| **All ten** | | | **306** | **166 / 134 / 6** | **202 / 19 / 43 / 42** |

Some sources appear in more than one catalog (HRRR, GOES, HMS smoke,
AirNow, the Greenbelt closures, among others), so the totals count entries,
not distinct sources. The six that couldn't be verified: USGS post-fire
debris-flow assessments (www.usgs.gov was unreachable), the FAA wildlife
strike database's download route, NREL's solar-position code (its host
doesn't resolve), the American Meteor Society's API terms, Water District
63's diversion telemetry, and IDPR's state-park boundaries (host
unreachable).

**Already in hand, so not repeated here:** 3DEP 1 m terrain, NAIP 2023 and
2025 with near-infrared, Overture buildings, the Oct 7 OpenStreetMap Idaho
extract, ACHD speeds and lanes, COMPASS crashes, the 511 API (127
road-weather stations), ITD's work-zone feed, VRT, and the camera archive
([SOURCES](SOURCES.md#in-use)).

**Areas.** "The valley box" is the Ada and Canyon box. "The ring" is the
regional ring proposed, not yet decided, in [DECISIONS](DECISIONS.md) ("How
far the study area reaches"): about 117.30° W to 115.60° W and 42.90° N to
44.30° N, taking in Emmett, Mountain Home and Ontario.

---

## 17.1 At a glance

1. **Most of what the owner's interests need is open, keyless and allowed
   by robots.txt.** That covers NOAA's open-data buckets on AWS (radar,
   satellite, models), federal and state ArcGIS services, and static agency
   files. The costs are elsewhere:
   - a few new core pieces;
   - a decoder image beyond the standard library, needed for GRIB2, NetCDF
     and rasters;
   - disk and bandwidth for gridded data.
2. **Start polling now.** Several sources keep only their current state, so
   history exists only if we poll:
   - Ridge to Rivers trail conditions;
   - IDL fire-restriction stages;
   - Boise River E. coli (latest round only);
   - Greenbelt closures;
   - NIFC WFIGS "Current" (contained fires drop out);
   - NDFD's latest-only folders;
   - AirNow's rolling 72-hour revisions.

   These are cheap standard-library pollers.
3. **Six new core pieces recur across almost every theme** (§17.3):
   - a gridded **fields** contract;
   - **recurring lifecycles with a rules-by-date evaluator**;
   - a **sun and moon ephemeris with lighting state**;
   - **surface-model (nDSM) tiles**, heights of buildings and trees above
     the ground;
   - a **routing graph**;
   - **point occurrences plus versioned geometry**.

   Two ingest fixes go with them: merging robots.txt groups, and a
   query-only ArcGIS client.
4. **3D weather MVP: an MRMS radar volume, fetched only when it's
   raining.** Next come HRRR clouds on pressure levels (not native levels)
   checked against GOES, then fog, inversion and smoke, then particles and
   lightning (§17.5).
5. **Corrections that change plans:**
   - OSM paths, footways and the Greenbelt are *not* loaded; the roads
     loader drops them.
   - RRFS goes operational Nov 3, 2026 and does *not* replace HRRR.
   - The 2023–24 QL1 lidar has *no* streamable EPT copy.
   - IDWR's 2023 irrigated lands is a *raster*.
   - IDWR's Treasure Valley METRIC ET *ends in 2015*.
   - BLM GTLF has *no season dates*, only a yes/no flag.
   - Source Cooperative's Crop Sequence Boundaries copy has *no crop
     history*.
   - 1-minute ASOS data exists at *BOI only*.
6. **There's a coverage gap.** The ring's Oregon strip (Malheur County:
   Ontario, Nyssa, Vale, Leslie Gulch) gets nothing from Idaho-only
   sources, including BLM's Idaho surface management (SMA) and GTLF layers,
   IDL, IDFG, the PAD-US Idaho file and Idaho statutes.

---

## 17.2 Recommendations by persona

Each persona covers its best sources (with the verdict), the first concrete
thing to build, what follows, owner actions, and watch-outs. Effort: S is
about 1–2 days, M about a week, L 2–3 weeks or more.

### Wildlife

Catalog: [sources/wildlife.md](sources/wildlife.md). Persona:
[ch. 16](16-ideas-and-personas.md#wildlife-wildlife).

**Best sources**
- **Use:**
  - [IDFG Roadkill Observations](https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer/1):
    public, updated almost daily, 5,841 records in the valley box, no
    reporter identity, no license.
  - [ITD crash units](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35)
    whose `Most_Harmful_Event` is "Animal – Wild/Domestic": 2005–2023, with
    time of day.
  - IDFG's public Hunting MapServer on its
    [GIS portal](https://gisportal-idfg.idaho.gov/hosting/rest/services),
    the one IDFG layer with an explicit license (**CC BY**).
  - IDFG [hub](https://data-idfggis.opendata.arcgis.com/) and portal
    layers: wildlife management areas (WMAs), game management units (GMUs),
    the species hex grid with IDFG's own `sensitive` flag (cells of about
    106 km²), monarch and milkweed suitability.
  - [USFWS Critical Habitat](https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/USFWS_Critical_Habitat/FeatureServer):
    slickspot peppergrass, 78,009 ac in Ada, Elmore, Gem, Payette and
    Owyhee counties.
  - [USFWS refuge boundaries](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer)
    and the [Deer Flat rules](https://www.fws.gov/refuge/deer-flat/visit-us/rules-policies).
  - [Boise River WMA rules](https://idfg.idaho.gov/wma/boise-river) and the
    [Birds of Prey NCA shooting rules](https://www.blm.gov/documents/idaho/public-room/map/morley-nelson-snake-river-birds-prey-safe-shooting-map),
    entered by hand.
  - [NatureServe](https://explorer.natureserve.org/api-docs/) ranks
    (CC BY 4.0).
  - The [Breeding Bird Survey](https://www.sciencebase.gov/catalog/item/6a0b0b0ab66b0188da36aedd)
    (CC0; on ScienceBase, so by hand: §17.6 B).
  - [GBIF](https://api.gbif.org/v1/occurrence/search) through **faceted
    counts**.
  - [NEXRAD Level II](https://registry.opendata.aws/noaa-nexrad/) from the
    Boise radar (KCBX) with vol2bird or bioRad, later.
- **Avoid:** the eBird and iNaturalist APIs (robots.txt), Movebank,
  automating HawkCount, and IDFG's Wildlife_Conflicts_public.
- **Needs owner action:** IDFG's token-only layers (mule deer seasonal
  ranges, fishing rules), BirdCast data, the Intermountain Bird
  Observatory's (IBO) Lucky Peak counts, and fish stocking records.

**First thing to build: "Animals on the road"** (M, mostly keyless)
- Match IDFG carcasses to road segments, giving carcasses per km per year by
  month (about 9.3k in the ring ⚠️, figure not re-run).
- Carcass dates are date-only, stored at 00:00 UTC, so treat them as
  calendar dates. They can't give time of day.
- The dusk and dawn profile comes from the ITD crash units'
  `Accident_Date_Time`.
- Mark the SH-21 crossings as hand-entered events:
  - Cervidae Peak overpass: MP 19.3, about 150 ft wide, about $6.5M, March
    2024;
  - Robie Creek underpass: scheduled for summer 2010 (completion date ⚠️).
- Label the carcass-to-crash comparison a "reporting-channel ratio", not
  under-reporting. Since the 2012 salvage law, most carcass rows are salvage
  permits.
- Herd sizes: cite IDFG's figures (5,000–8,000 mule deer and 1,800 elk
  winter on the WMA). The "8–9k deer" figure is unsourced.

**Next**
- Seasonal wildlife closures as recurring lifecycles (§17.3):
  - Boise River WMA: part of the Cornell segment closed Feb 1–Apr 14; dogs
    leashed Nov 16–Apr 30;
  - Deer Flat islands closed Feb 1–Jun 14 (some to Jun 30);
  - the Birds of Prey NCA canyon closed to all firearms Feb 15–Aug 31.
- "What's here this week" from GBIF faceted counts
  (`limit=0&facet=speciesKey`) per 0.2° cell × month. That's about 750
  keyless requests to bootstrap, with no raw points or observer names
  stored.
- Later: KCBX night migration profiles (5–35 km around the radar), shared
  with the weather radar pipeline.

**Owner actions**
- Decide whether the "no license: use it and send a courtesy note" rule
  (set Oct 6 for city and county imagery) extends to IDFG GIS (Q17).
- One note to IDFG IFWIS covering:
  - token access to mule deer ranges and fishing rules;
  - permission for stocking records;
  - republishing roadkill and hex aggregates;
  - what `count_trusted` and the `path` field mean;
  - whether Pheasant_Stocking is meant to be publicly editable.
- Optional: a GBIF account (download DOIs).
- Asks to Cornell (BirdCast) and IBO.
- A hand download of the FAA strike database (the local helper looks at
  the app first).
- The radar dependency decision (the worker image, Q9).

**Watch-outs**
- Never query Wildlife_Conflicts_public. It's a write-only intake form
  whose schema holds reporter and landowner contact details.
- IDFG's "Big Game Winter Range and Migration Priority Areas" layer is five
  coarse statewide complexes, not mapped winter range.
- There are no USGS migration corridors inside the ring; all Idaho herds
  are south of 42.90° N.
- 511's wildlife-sign data is internal only.
- Boise airport strike data excludes military aircraft (Gowen Field) ⚠️.
- Drop the carcass `note` and `path`, and GBIF's `recordedBy` and
  `identifiedBy`, at ingest.
- Sensitivity needs **two** mechanisms (§17.3). Never store or draw nests,
  dens, leks or roosts.

### Sky

Catalog: [sources/sky.md](sources/sky.md). Persona:
[ch. 16](16-ideas-and-personas.md#sky-watcher-and-photographer-sky).

**Best sources (use)**
- [Astronomy Engine](https://github.com/cosinekitty/astronomy) (MIT):
  lazy-loaded in JavaScript, plus a single-file Python with no
  dependencies.
- [SunCalc](https://github.com/mourner/suncalc) (BSD-2), or our own port of
  the [NOAA/Meeus equations](https://gml.noaa.gov/grad/solcalc/calcdetails.html).
- The [USNO API](https://aa.usno.navy.mil/data/api) and
  [JPL Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) as test
  fixtures. USNO has no lunar-eclipse endpoint; check those against
  [NASA/Espenak](https://eclipse.gsfc.nasa.gov/eclipse.html).
- NASA's [ISS ephemeris](https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.txt)
  (OEM, public domain).
- [SatNOGS](https://db.satnogs.org/api/tle/) TLEs (CC BY-SA, TLE only).
- [HYG v4.4](https://codeberg.org/astronexus/hyg) (CC BY-SA; clone by hand
  from Codeberg).
- [d3-celestial](https://github.com/ofrohn/d3-celestial) (BSD-3).
- NASA SVS [Deep Star Maps](https://svs.gsfc.nasa.gov/4851) (public domain;
  the Gaia part needs ESA credit and non-commercial use).
- SWPC [OVATION aurora](https://services.swpc.noaa.gov/json/) and
  [GFZ Kp](https://kp.gfz.de/en/data) (CC BY).
- [IMO](https://www.imo.net/) calendar facts, the
  [IAU Meteor Data Center](https://www.ta3.sk/IAUC22DB/MDC2022/),
  [Global Meteor Network](https://globalmeteornetwork.org/data/)
  trajectories (CC BY) and [CNEOS fireballs](https://ssd-api.jpl.nasa.gov/doc/fireball.html).
- HRRR cloud and smoke fields.
- [ECCC seeing and transparency](https://weather.gc.ca/astro/index_e.html)
  (open licence).
- [Bruneton precomputed scattering](https://github.com/ebruneton/precomputed_atmospheric_scattering)
  (BSD-3).
- MapLibre [sky, light and hillshade](https://maplibre.org/maplibre-style-spec/sky/).

**Needs owner action:** Space-Track (account), CelesTrak (robots.txt), EOG
VIIRS lights (registration ⚠️), the Falchi atlas (CC BY-NC, hand download),
Skyfield (dependencies and an ephemeris file).

**First thing to build: real-sun lighting** (S–M)
- Use a core sun and moon module on the replay clock to drive:
  - MapLibre `light`: anchor `map`, azimuthal angle = sun azimuth, polar
    angle = 90° − elevation, clamped at night; it lights extrusions only;
  - hillshade direction;
  - sky and fog colours.
- Commit a few dozen USNO and Horizons answers as test fixtures.

**Then a "Glare now" street layer** (M)
- Thresholds: sun 0–25° up and within ±25° of the heading; keep both as
  settings.
- Verified Boise windows (eastbound):
  - Mar 15: 7:59–10:03;
  - Oct 1: 7:44–9:38 (westbound 17:31–19:24);
  - Oct 15: 8:01–9:16;
  - none from **Nov 14 to Jan 28**.
- Store a horizon profile per segment (72 bins, about 2.8 MB) in a data
  texture. Ray-march at least 100 km with Earth curvature and refraction,
  because the Owyhee crest is about 60–80 km away. Use the 10–30 m DEM for
  the far field.
- Update once a minute or on scrub, not every frame.

**Next**
- A "Tonight" panel and Valley Feed items: planets and moon, ISS bright
  passes, aurora odds, meteor showers, cloud and transparency.
- ISS passes from the OEM: fetch at most daily, and only when
  Last-Modified changes. Convert J2000 to of-date coordinates plus Earth
  rotation, and interpolate with Hermite, never linearly.
- A night-sky dome:
  - HYG to magnitude 6.5 (about 9k stars) plus d3-celestial lines;
  - an SVS map at 8K at most (KTX2), with stars brighter than the sprite
    cutoff masked out;
  - each object faded by the computed sky brightness: twilight, moon,
    Falchi artificial brightness plus about 22 mag/arcsec² natural, and
    HRRR cloud.
- A light-pollution year slider (EOG VNL).
- A replay of the 2017 eclipse (Boise saw magnitude 0.994, 24 km outside
  totality).

**Owner actions**
- Approve putting the ephemeris in core (Q3). That moves it off the `sky`
  list in [§15.7](15-plugins.md#157-ideas-for-later-plugins).
- A Space-Track account.
- Ask CelesTrak, or skip it (Q15).
- Hand downloads: EOG, the GFZ Falchi atlas, the SVS 8K map, HYG.
- Confirm Bruneau Dunes' Dark Sky Park status (June 2024 per Idaho
  Business Review and Visit Idaho ⚠️) on darksky.org in a browser.

**Watch-outs**
- **5-digit catalog numbers ran out on 2026-07-11.** New objects (most new
  Starlinks) have no TLE, so use OMM via `json2satrec`.
- SatNOGS declares token auth on its TLE endpoints, even though anonymous
  reads work today.
- CelesTrak's robots.txt disallows `gp*.php` and blocks claudebot.
- Never mirror Global Meteor Network station field-of-view KMLs.
- Aggregate Globe at Night to about 2 km cells.
- A 16K sky texture is about 512 MB of GPU memory.
- NREL hosts no longer resolve; it appears to have been renamed the
  National Laboratory of the Rockies (NLR).

### Gardening

Catalog: [sources/gardening.md](sources/gardening.md). Persona:
[ch. 16](16-ideas-and-personas.md#gardener-new-oct-7).

**Best sources (use)**
- [RCC-ACIS](https://www.rcc-acis.org/docs_webservices.html) (keyless):
  freeze dates by year, growing degree days, the PRISM daily grid (grid
  21), CoCoRaHS.
- [NCEI 1991–2020 normals](https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals)
  via `/access/services/data/v1` (allowed).
- [PRISM 800 m normals](https://prism.oregonstate.edu/normals/) (hand
  download; the web service blocks a file after two downloads in 24 h).
- The [2023 Plant Hardiness Zone Map](https://prism.oregonstate.edu/phzm/)
  (hand download, with a "not the official USDA map" disclaimer and no
  logos).
- SSURGO via [Soil Data Access](https://sdmdataaccess.nrcs.usda.gov/WebServiceHelp.aspx)
  (public domain).
- **AgriMet's static ET charts**, including past seasons'
  `{stn}{yy}et.txt`; the Boise stations carry LAWN only.
- IDWR [Irrigation Organizations](https://gis.idwr.idaho.gov/hosting/rest/services/Irrigation/IrrigationOrganizations/FeatureServer/0)
  (59 in the box) and Season of Use.
- Canal dates entered by hand.
- [gridMET](https://www.climatologylab.org/gridmet.html) (CC0; direct files
  only, not THREDDS).
- [HMS smoke](https://www.ospo.noaa.gov/products/land/hms.html), EPA
  [AirData](https://aqs.epa.gov/aqsweb/airdata/download_files.html), and NWS
  non-precipitation alerts from [tgftp](https://tgftp.nws.noaa.gov/data/watches_warnings/).
- Landsat surface temperature.
- Lidar: the [QL2 EPT](https://s3-us-west-2.amazonaws.com/usgs-lidar-public/ID_SouthernID_21_2018/ept.json)
  on S3; QL1 as LAZ.
- [CHMv2 canopy](https://registry.opendata.aws/dataforgood-fb-forestsv2)
  (CC BY 4.0).
- [NSRDB](https://registry.opendata.aws/nrel-pds-nsrdb/) (CC BY 3.0 US).

**Needs owner action:** USA-NPN (its terms forbid automated access),
AgriMet weather and soil temperature (behind `/pn-bin`), Boise's 2021
canopy land cover, Water District 63 telemetry.

**First thing to build: a "My yard" card, without shade** (S–M, in the
private `home` plugin)
- Frost odds: station data shifted to the yard by the PRISM normal minimum
  and a cold-pocket term from the DEM.
- The hardiness half-zone.
- Soil at the point: texture, pH, drainage, depth to hardpan.
- The yard's irrigation organization and this year's canal dates.
- "Lawn water use (ET) this week". It can't subtract rain: precipitation
  exists only behind the disallowed `/pn-bin`.
- Heat days and smoke days against normal.

All of it is keyless and standard library.

**Next**
- Browser shadows from Overture buildings and terrain on the replay clock,
  using the core sun module.
- Then an nDSM from lidar for the owner's neighbourhood, only if the WESM
  index shows QL2 points there. The QL2 EPT's bounding box spans the
  valley, but bounds aren't coverage.
- Then sun hours by month weighted by NSRDB cloudiness, with CHMv2 filling
  leaf-off gaps (labelled estimated).

**Owner actions**
- Keep the home location and beds private.
- Approve PDAL in the basemap build (Q4).
- The QL1 download (about 162 GB; see the disk question, Q10).
- Ask the City for the canopy land cover and heat-study data.
- Ask NPN for written approval, or accept our own degree-day proxy from
  ACIS.
- Decide which sensors the owner wants.

**Watch-outs**
- SunCalc measures azimuth from south and leaves out refraction; NOAA
  measures from north and includes it. Fix the conventions in core.
- 10 m cells are still yard-scale, so guests should see 50 m or block
  aggregates (Q23).
- The lidar was partly flown leaf-off.
- Mixing in Overture heights makes the result an ODbL Produced Work; a
  lidar-only split stays public domain.
- NWS issues frost and freeze advisories only within its growing season ⚠️.

### Weather

Catalog: [sources/weather.md](sources/weather.md). Persona:
[ch. 16](16-ideas-and-personas.md#fire-and-weather-watcher-hazards-weather).

**Best sources (use; all keyless)**
- On NOAA's open-data buckets on AWS (NODD):
  - [MRMS](https://registry.opendata.aws/noaa-mrms-pds/);
  - [HRRR](https://registry.opendata.aws/noaa-hrrr-pds/) (the `wrfprs`
    file, or the HRRR-Zarr `prs` store);
  - [NBM v5.0](https://registry.opendata.aws/noaa-nbm/) Cloud-Optimized
    GeoTIFFs;
  - [RTMA](https://registry.opendata.aws/noaa-rtma/) rapid update;
  - [GOES-18](https://registry.opendata.aws/noaa-goes/) Level 2 products
    and GLM lightning;
  - [NEXRAD](https://registry.opendata.aws/noaa-nexrad/) Level II and III
    for KCBX;
  - [NDFD](https://registry.opendata.aws/noaa-ndfd/);
  - [normals](https://registry.opendata.aws/noaa-climate-normals/) and
    GHCN.
- [NOMADS](https://nomads.ncep.noaa.gov/) grib filters (`hrrr_2d`,
  `rtma_ru`, `blend`); the limit is 120 hits a minute per IP across NCEP
  hosts.
- [AWC METAR](https://aviationweather.gov/data/api/) (100 requests a
  minute).
- [IEM](https://mesonet.agron.iastate.edu/request/download.phtml): ASOS
  history, RAOB, VTEC, local storm reports (LSRs) (Crawl-delay 120).
- The NWS watches, warnings and advisories
  ([WWA](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer))
  map service.
- [IGRA](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive)
  (`/pub` allowed).
- PRISM, [CoCoRaHS](https://www.cocorahs.org/Content.aspx?page=datausagepolicy)
  (CC BY 3.0 data), [Storm Events](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/).
- **Avoid:** api.weather.gov (robots.txt `Disallow: /`), the SPC site,
  UWyo soundings, Open-Meteo, the nowCOAST geoserver, Synoptic (we don't
  qualify), and GOES fog/low-stratus products (SBN only).

**First thing to build: airport observations, a fog chip and warnings** (S)
- AWC METAR by bbox every 5 min: 5 stations (KBOI, KMAN, KEUL, KMUO, KONO),
  under 2 MB a day. Parse `visib` as text.
- Live warnings from the NWS WWA map service by envelope: key on
  wfo/phenom/sig/event-number/year, and show `url` only as a link.
- IEM for history:
  - BOI 1-minute visibility (BOI is the only ring station with 1-minute
    data; about 24 h lag);
  - routine and 5-minute METARs at EUL, MAN and MUO;
  - yearly WWA zips;
  - the BOI sounding twice a day.
- Feed the [ch. 2](02-treasure-valley-signal-system.md) fog-morning study,
  with RTMA-RU visibility and ceiling via the NOMADS `rtma_ru` subregion
  filter (KB per request). On S3 the same data costs about 15 MB per
  15-minute analysis.
- **IEM budget:** one shared queue, at most 720 requests a day. With live
  warnings from the NWS WWA service, IEM handles only LSRs (about 96 a day),
  RAOB (2), discussions (24) and backfill.

**Next** (after the fields and worker-image decisions)
- MRMS 2D cropped to the ring every 2 min (about 34 MB a day raw per
  field).
- NBM elements (frost, WBGT, mixing height, snow level; about 20 MB a day
  raw).
- HRRR 2D forecasts via NOMADS.
- GOES-18: ACM, ACHA2KM, FDC and ADP every 5 min; LST hourly; DSR only as
  full disk (DSRF).
- GLM, fetched only when lightning is likely.
- Climate cards: normals from S3; GHCN per station from NCEI `/pub` (the S3
  per-station copy is stale since Feb 2025); PRISM; CoCoRaHS daily; Storm
  Events (skip the fatalities file).

**Owner actions:** open questions 1, 9–11, 13 and 19–20 (§17.8), and for
3D weather and the fog study also 26, 27 and 29. An optional FEMS account
(RAWS history, fire danger). A private home weather station or a
Blitzortung receiver, if wanted.

**Watch-outs**
- Bucket names change (NEXRAD Level II moved in 2025), so keep them in
  config.
- GOES-West before 2023 is GOES-17. Level III for KCBX starts Mar 2, 2022.
- Keep our derived frames permanently; NODD hosting depends on NOAA
  agreements ⚠️.
- NDFD's `opnl` folder is latest-only; NBM version folders shift.
- RWIS data is internal, so build the public fog layer from NOAA inputs
  only.

### Farms and crops

Catalog: [sources/farm.md](sources/farm.md). Persona:
[ch. 16](16-ideas-and-personas.md#farmer-farm).

**Best sources**
- **Use:**
  - The [Cropland Data Layer](https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php)
    (CDL; public domain). CropScape statistics are on 30 m pixels and its
    bbox is in EPSG:5070 metres; 10 m only via the WCS.
  - [Crop Sequence Boundaries](https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/index.php)
    (CSB) 2018–2025 (public domain; the national zip is 3.76 GB).
  - [Annual NLCD](https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database)
    Collection 1.2 (1985–2025).
  - IDWR [irrigated lands](https://gis.idwr.idaho.gov/hosting/rest/services/IrrigatedLands):
    polygons for 1987–2015 and a 2023 raster.
  - IDWR [1939 land use](https://data-idwr.hub.arcgis.com/documents/IDWR::land-use-boise-river-basin-lower-1939)
    plus the 1939 airphoto mosaics.
  - IDWR [METRIC ET](https://gis.idwr.idaho.gov/hosting/rest/services/ScientificRasters/ETData/MapServer)
    for the Treasure Valley, 1987–2015.
  - AgriMet [static charts](https://www.usbr.gov/pn/agrimet/h2ouse.html):
    crop ET at Parma, Nampa, Ontario and Grand View.
  - SSURGO farmland class.
  - The [USDM statistics API](https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx).
  - NASS [bulk files](https://www.nass.usda.gov/datasets/) and the Census
    of Agriculture.
  - IDWR [water rights](https://gis.idwr.idaho.gov/hosting/rest/services/Allocation/WaterRightPods/FeatureServer/0):
    uses and priority dates only.
  - ISDA [herd districts](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_County_Herd_Districts/FeatureServer).
  - [Sentinel-2](https://registry.opendata.aws/sentinel-2-l2a-cogs/)
    Collection 1 (later).
- **Needs owner action:** the HydroShare canal network (CC BY, hand
  download), Water District 63 diversion data, DEQ burn decisions, OpenET,
  American Farmland Trust's Farms Under Threat 2040.
- **Avoid:** the Quick Stats API (robots.txt), FSA Common Land Units (7
  U.S.C. 8791), OpenET without written consent, and dairy and CAFO point
  maps.

**First thing to build: farm water today** (S, keyless)
- A daily AgriMet crop-ET card. Parse columns by position against
  `<stn>ch.txt`, use GET (HEAD resets on that host), and expect a 2–3 day
  lag.
- Past seasons from the static yearly ET files.
- A USDM county drought strip using `statisticsType=2` (categorical). Type
  1 is cumulative and double-counts if stacked.
- Canal-season lifecycles, entered by hand.
- IDWR irrigation organizations, season of use, and Water District 63
  diversion sites (78 active).

**Next: the field card** (M)
- CSB polygons clipped to the ring, labelled "estimated field" (60 m
  simplification), with 8-year crop chips.
- CDL 2025 for display from a WCS 10 m clip.
- NASS's own 30 m copies for time series, because the method and
  resolution changed in 2024.
- Categorical tiles must be lossless, with mode downsampling.

**Then: the 87-year farmland story on the History year slider**
- 1939 → IDWR 1987–2015 → the 2023 raster (compared by zonal statistics
  inside a common footprint) → Annual NLCD with a persistent-developed rule
  → SSURGO "prime if irrigated" acres converted.
- Example acreages:
  - prime if irrigated: Ada 175,412 ac; Canyon Area 253,994 ac;
  - Census 2022: Canyon 2,311 farms and $829.4M in sales; Ada 1,142 farms,
    down 12%.
- Later: Sentinel-2 NDVI per field for 3D "living fields".

**Owner actions**
- Approve the CSB zip and the CDL and NLCD clips, and GDAL on a build
  machine.
- Reclamation, and the Water District 63 watermaster (the diversion app's
  guest login is a form, so scripting it needs IDWR's OK).
- A hand download of HydroShare (accepting the CC BY click-through).
- Pull the NASS bulk files once or twice a year.
- The Ada herd-district layer is credited to the Ada County Assessor's
  Office; decide it against the project's Assessor rule.

**Watch-outs**
- Grass/Pasture, Canyon's largest class, has no reported accuracy.
- Drop owner names from water rights and wells (wells also carry
  addresses).
- AgriMet's static files have no temperature, so no degree-days from them.

### Hiker, camper and land permissions

Catalogs: [sources/lands.md](sources/lands.md) and
[sources/trails.md](sources/trails.md). Persona:
[ch. 16](16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water).

**Best sources**
- **Use:**
  - Ridge to Rivers (R2R) per-trail
    [Condition](https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer)
    (271 trails, seven states).
  - [Greenbelt closures](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer).
  - USFS Region 4 [forest orders](https://services1.arcgis.com/gGHDlz6USftL5Pau/arcgis/rest/services/R04_Forest_Orders_PUBLIC_VIEW/FeatureServer/0)
    (5 orders, 7 polygons in the ring).
  - Boise NF [alerts](https://www.fs.usda.gov/r04/boise/alerts) (by hand).
  - USFS [MVUM](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_02/MapServer),
    [NFS trails](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer/0)
    and [INFRA recreation sites](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_InfraRecreationSites_01/MapServer/0);
    exclude the 5 "recreation residence" private cabins.
  - BLM [SMA](https://gis.blm.gov/idarcgis/rest/services/lands/BLM_ID_Surface_Management_Agency/FeatureServer)
    (Idaho only), [GTLF](https://gis.blm.gov/idarcgis/rest/services/transportation/BLM_ID_Ground_Transportation_Linear_Features_GTLF/FeatureServer/0),
    [PLAD/MAPLand easements](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_PLAD/MapServer),
    [allotments](https://gis.blm.gov/arcgis/rest/services/range/BLM_Natl_Grazing_Allotment/MapServer/12),
    [mining claims](https://gis.blm.gov/nlsdb/rest/services/HUB/BLM_Natl_MLRS_Mining_Claims_Not_Closed/FeatureServer/0)
    and [special designations](https://gis.blm.gov/idarcgis/rest/services/special_designations?f=json).
  - IDL [ownership](https://services2.arcgis.com/1cvrwLhZRFh3okEF/arcgis/rest/services/State_Ownership/FeatureServer)
    and IDL [fire restrictions](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer).
  - [PAD-US 4.1](https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-download),
    by hand download.
  - FWS refuges and the Deer Flat rules.
  - The IDFG Hunting MapServer (CC BY).
  - IDPR [Idaho Recreation Trails](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer)
    (non-commercial, attribution).
  - The NWPS gauge [BIGI1](https://api.water.noaa.gov/nwps/v1/gauges/BIGI1);
    Boise Fire [river hazards](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_River_Hazards_and_Access_-_VIEW/FeatureServer/10);
    [E. coli](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/BPR_EColi_Testing/FeatureServer/0);
    [Barber Park](https://gisprodapi.adacounty.id.gov/arcgis/rest/services/ParksAndWaterways/Barber_Park_Floater_Information/FeatureServer);
    [SNOTEL](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:ID:SNTL)
    (4 stations in the ring).
  - The [Idaho statutes](https://legislature.idaho.gov/statutesrules/idstat/Title6/T6CH2/SECT6-202/),
    as help text.
- **Use internal only:** IDFG Access Yes! (drop `contactname`), Canyon
  County parcels (a private plugin).
- **Avoid:** Reclamation Land Ownership (its terms forbid downloads and
  derived products), NCED (frozen since Jan 2025), Recreation.gov
  availability and the RIDB API (robots.txt), getoutside.idaho.gov (a
  bot-detection challenge), and Trailforks, AllTrails and Strava.

**First thing to build: start the closure and condition clocks** (S each,
ingest only)
- R2R Condition: attributes every 30 min, gated on `dataLastEditDate`.
- Greenbelt closures.
- IDL fire stages: hourly June–October, daily otherwise. The layer is
  current-state only: "Stage None" with a DateEnacted marks the *end* of a
  restriction.
- R4 orders, keyed on `ordernum`.
- IDPR emergency closures and area restrictions.
- River hazards. Their codes are mixed with free text and nulls, so
  normalise them.
- E. coli, daily.
- Barber Park in season: one query per 10 min, query-only.

**Next: a "Can I be here?" panel** (M)
- Stacked evidence with citations and a "not a legal determination"
  banner:
  - PAD-US Fee and Easement, never Proclamation, which includes private
    inholdings;
  - SMA, IDL, refuges, USFS surface ownership;
  - active orders and today's fire stage;
  - stay limits (Boise NF: 14 days in any 30, order 0402-00-62; the BLM
    limit ⚠️);
  - statutes (36-1601 navigable streams; 6-202 posting; 18-7008).
- In Oregon the panel says "no data", never "private".

**Then**
- "What can I ride on date X" (needs the rules-by-date evaluator):
  - MVUM `*_datesopen` across all 14 vehicle classes plus the e-bike
    classes, filtered by SYMBOL;
  - GTLF designation, where an undesignated route isn't permission and the
    seasonal flag links to the travel plan;
  - IDPR `Season_*` fields;
  - forest orders override everything.
- The OSM paths pass, then trail conflation.
- Campgrounds. BLM's national recreation service is already a nightly RIDB
  copy.
- The landlocked-public-land analysis: graph adjacency, "no known legal
  access", and never drawn corner-crossing routes.
- The float panel:
  - NWPS flow every 30–60 min (observations arrive about 2–3 h late);
  - the agencies' typical 500–1,500 cfs range and their wording ("never
    deemed completely safe");
  - the 2026 season was Jun 20–Sep 7.

**Owner actions**
- Oregon scope (Q18).
- A PAD-US hand download (Idaho 150 MB, Oregon 291 MB), or the Source
  Cooperative GeoParquet.
- Courtesy notes to the City of Boise (R2R), Ada County (Barber Park), IDFG
  and IDL.
- The IDL camping stay limit, which wasn't found.
- Canyon County's FTP, if parcels are wanted.
- The RIDB export decision (248 MB; it mainly adds USACE at Lucky Peak and
  Reclamation).
- Ask Ridge to Rivers where its Foothills imagery came from.
- Local helper: check gis2.idaho.gov (IDPR parks), landfoliogis.idl.idaho.gov
  and rockyweb.usgs.gov from the owner's network.

**Watch-outs**
- R2R sets statuses in batches; ConditionDate is when staff updated the
  status.
- The Hulls Gulch even/odd rule uses day-of-month parity in Boise local
  time; the 31st and the 1st are both odd.
- The Barber Park and IDFG access-site services advertise public edit
  capabilities. Query only, and treat their values as unverified.
- Drop PLAD's `APRSD_VALUE` and `PYMNT_MADE`.
- Show mining-claim names on click only.

### Cycling and walking

Catalog: [sources/cycling.md](sources/cycling.md). Persona:
[ch. 16](16-ideas-and-personas.md#cyclist-and-pedestrian-safety-roads).

**Best sources** (internal until ACHD and COMPASS answer, except where
noted)
- ACHD has already scored level of traffic stress (LTS):
  - the [Official Bicycle Facility Network](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Official_Bicycle_Facility_Network/FeatureServer/1):
    1,080 mi with an LTS field. LTS 1 = 260 mi, 2 = 194, 3 = 152, 4 = 223,
    blank = 251;
  - Alta's bicycle LTS (BLTS) 2023 in the
    [Master Bicycle Map](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer):
    4,584 segments plus intersections;
  - Alta's pedestrian LTS (PLTS) 2023 in the
    [Master Pedestrian Map](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer):
    34,771 segments plus intersections, with lighting and accessibility
    flags;
  - ACHD [sidewalks](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Sidewalks/FeatureServer/1):
    45,047.
- COMPASS [ExistingBikeAndPed](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer)
  and Pathways_Master: the only Canyon County coverage, routable, with
  grade-separation z-levels.
- COMPASS crashes (already loaded; road-user types may be published as
  aggregates).
- [ITD crash units](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35)
  (ring, 2005–2023).
- Boise's [Pathways Master Plan](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Pathways_Master_Plan/FeatureServer)
  and Greenbelt closures.
- Nampa's current [Bike Routes & Pathways](https://www.arcgis.com/sharing/rest/content/items/1920988890154b77ba46c8bde9dac469)
  (Sep 2026).
- OSM active-transport tags.
- The [LTS method](https://transweb.sjsu.edu/research/Low-Stress-Bicycling-and-Network-Connectivity)
  (Mekuria, Furth and Nixon 2012).
- The PeopleForBikes [BNA analyzer](https://github.com/PeopleForBikes/brokenspoke-analyzer)
  (MIT).
- EPA [Walkability](https://www.epa.gov/smartgrowth/smart-location-mapping)
  (CC0, hand download).
- [FARS](https://crashviewer.nhtsa.dot.gov/CrashAPI) (by hand).
- **Avoid:** Strava, Lime GBFS (robots.txt), BikeMaps.org JSON
  (robots.txt), Boise's copy of ACHD's Regional Low-Stress layer (its terms
  forbid sharing).
- **Private schema only:** Meridian pathways (no redistribution).

**First thing to build: a cyclist and walker map** (S–M)
- ACHD LTS and Alta BLTS/PLTS in Ada; COMPASS facilities and pathways in
  Canyon.
- The Greenbelt closures lifecycle.
- Bike and pedestrian crashes aggregated by LTS class.
- The colour ramp follows [ch. 13](13-visual-design.md)'s five-step data
  ramp with monotone lightness, plus width and dash; the safety view
  inverts the emphasis.

**Next** (M)
- The `osm_active` change: widen `keep_way()`
  (`plugins/roads/ingest/sources/osm_valley.py`) and add node filters for
  crossings, kerbs, barriers, bike parking and repair stations, plus a ring
  extract.
- Our own LTS engine, storing the method version with each score,
  calibrated against Alta in Ada with a published agreement matrix, then
  Canyon County LTS.
- BNA runs per city, with every input pre-placed so it never downloads
  anything.

**Then** (L): the routing graph, a low-stress planner, safe routes to
school, first and last mile to VRT stops, and a step-free router.

**Owner actions**
- Where it lives: a new `active` plugin (the pilot's lean) or spread across
  existing ones (Q7).
- One note to ACHD: republishing, what sidewalk Category 1–4 and ramp
  Category 1–5 mean, counter data.
- To COMPASS: hourly counter data (28 location rows: 16 COMPASS, 12 ACHD),
  Data Bike, republishing.
- Through the City: Ride Report and Lime.
- Check that the database image has pgRouting (Q12).
- Census: hand tables, or a free key.

**Watch-outs**
- ACHD's `YearAdded` probably isn't the build year, and COMPASS calls its
  own year fields unreliable. Check against imagery before any before/after
  study.
- ITD's Ada 2023 counts (60 pedestrian, 91 bicycle units) need comparing
  with COMPASS's on the server.
- Skip `PAG_Comments` and the public-input layers.
- Only Boise has walk-zone polygons; the West Ada and Kuna layers are
  attendance areas.
- Never copy agency data into OSM.

### Fire and hazards

Catalog: [sources/hazards.md](sources/hazards.md). Persona:
[ch. 16](16-ideas-and-personas.md#fire-and-weather-watcher-hazards-weather).

**Best sources**
- **Use:**
  - NIFC [WFIGS](https://data-nifc.opendata.arcgis.com/) all-years and
    year-to-date services.
  - NIFC [perimeter history](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0):
    the 1908–2019 view plus the 2020–2024 view (2,157 + 248 in the ring;
    there is no 2020 gap).
  - [FIRMS](https://firms.modaps.eosdis.nasa.gov/) keyless CONUS CSVs
    (hourly).
  - [HMS](https://www.ospo.noaa.gov/products/land/hms.html) smoke and fire
    KML.
  - GOES-18 FDC fire detection and the ADP smoke mask.
  - IDL [fire stages](https://www.idl.idaho.gov/fire-restrictions-finder/)
    and USFS [R4 orders](https://apps.fs.usda.gov/fsgisx02/rest/services/r04/R04_Alerts_And_Closures_01/MapServer).
  - The NWS WWA map service, plus IEM's
    [WWA archive](https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml)
    zips.
  - [IPAWS archived alerts](https://www.fema.gov/openfema-data-page/ipaws-archived-alerts-v1)
    (24-hour delay).
  - [NWPS](https://water.noaa.gov/about/api) flood categories; USGS
    [earthquakes](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php).
  - [USDM](https://droughtmonitor.unl.edu/) via NDMC's own ArcGIS service
    plus the statistics API.
  - [Storm Events](https://www.ncei.noaa.gov/stormevents/ftp.jsp).
  - [HeatRisk](https://www.wpc.ncep.noaa.gov/heatrisk/) (experimental).
  - [AirNow](https://docs.airnowapi.org/) file products (after the
    guidelines form).
  - [AQS](https://aqs.epa.gov/aqsweb/documents/data_api.html) AirData.
  - HRRR-Smoke.
  - The [NAQFC](https://noaa-nws-naqfc-pds.s3.amazonaws.com/) ImageServer
    `identify`, which needs no decoding.
  - [FPA FOD](https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.7)
    7th edition (SQLite, 220 MB); [MTBS](https://burnseverity.cr.usgs.gov/direct-download);
    [Wildfire Risk to Communities](https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2)
    (Idaho 6.56 GB ⚠️).
- **Needs owner action:** FEMS (account), FEMA NFHL (hand download; the
  services are robots-disallowed), Genasys (agreement), Idaho Power's PSPS
  layers, the USGS Water Data API.
- **Avoid:** InciWeb and NGFS (robots.txt), DEQ burn decisions (robots.txt
  and per-grower data), PurpleAir (robots.txt, paid, terms that conflict
  with MIT), the GSL HRRR-Smoke site (robots.txt).

**First thing to build: a fire board and the Valley Feed** (S–M; keyless,
standard library: JSON, CSV, KML)
- Poll WFIGS with an absolute filter: `ModifiedOnDateTime_dt > TIMESTAMP
  '<last seen>'`. NIFC asks clients not to use relative dates.
  - `_Current` drops fires once they're contained, so read state changes
    from the all-years or year-to-date service.
  - Close a lifecycle only on `FireOutDateTime`, and version every
    perimeter change.
- FIRMS: filter rows to the ring and dedupe by content, since the files are
  rewritten hourly. Draw hotspots as 375 m pixels, never as pins on houses.
- HMS: version same-day files; the next morning's file is final.
- Join fires and hotspot clusters within 2 km of state routes to 511
  closures.

**Next**
- History: perimeters, FPA FOD (`sqlite3` is in the standard library), IEM
  WWA zips, IPAWS (drop AMBER, Blue, law-enforcement and missing-person
  alerts; for civil-danger and local-emergency alerts keep only the event,
  time and area), Storm Events counts, and an AQS-based smoke-day
  classification (AirNow's terms bar using its data for trends).
- With the fields pipeline: GOES FDCC 5-minute fire power, ADP, HRRR smoke
  along I-84 (8 m smoke and column smoke are about 0.9 MB an hour by byte
  range), HeatRisk.

**Owner actions**
- Return the AirNow Data Exchange Guidelines form to dmc@airnowtech.org and
  notify Idaho DEQ.
- Optional: a FIRMS MAP_KEY, an AQS key, a FEMS account.
- A FEMA NFHL hand download (Ada 16001, Canyon 16027).
- Approve the Wildfire Risk to Communities download.
- Ask Ada County Emergency Management about Genasys (the county's alert
  sign-up runs on Genasys).
- Ask Idaho Power about its PSPS areas.
- Decide whether the camera haze index may be published (Q25).

**Watch-outs**
- HMS smoke is the whole column, not ground level.
- GLM is total lightning at about 8–14 km resolution, not ground strikes.
- AirNow's guidelines bar using its data to "act as guidance", which
  constrains ride-window and burn-day advice.
- The required AQI colours include red and green, so always add the
  category word and number (Q24).
- www.usgs.gov was unreachable, so the debris-flow source is low
  confidence.

### Weather in 3D

Catalog: [sources/weather-3d.md](sources/weather-3d.md). The owner's idea:
[ch. 16 §16.5](16-ideas-and-personas.md#165-weather-in-3d-the-owners-idea-oct-7).
The design is in §17.5.

---

## 17.3 Shared core pieces and what they unlock

**Already on the core list** ([ch. 15 §15.1](15-plugins.md#151-whats-core),
[ch. 16 §16.4](16-ideas-and-personas.md#164-shared-core-pieces-serve-almost-every-persona))

| Core piece | Plugins it unlocks (from this research) | Note |
|---|---|---|
| Full replay (time bar, 60×/600×, scrub) | weather, hazards (fire growth), trails (wet-season replay), sky (eclipse, aurora), wildlife (migration nights), farm and history (year slider) | Replay works only for what we archived: start pollers early |
| Places and search | trails and trailheads, lands, campgrounds, Greenbelt mileposts, species names, farm fields, the owner's yard (private) | One index across plugins |
| Valley Feed | hazards, weather warnings, lands closures, trail conditions, sky "tonight", canal season, wildlife migration nights | Needs lifecycles that carry their source |
| 3D engine ([UI v2](14-ui-v2.md) WP9) | weather volumes, sky dome and shadows, trail fly-alongs, farm living fields, radar migration, river ribbon | No depth texture from MapLibre; see §17.5 |
| Regular OSM load | cycling, trails, gardening public layers, the lands access graph | **Gap:** paths and points of interest aren't loaded; needs a ring box and Geofabrik's Oregon extract |
| Layer system | every plugin | Uses toolbar groups, not lenses (UI v2 decision) |
| Readings and lifecycles displays | weather, water, gardening, hazards, trails, farm | The time-series card and "what was active" |
| Evidence and review | lands ownership, trail conflation, LTS provenance | Same pattern as lanes |
| Areas | every plugin | Add the ring, an Oregon-strip flag, and possibly a 300 km weather-context area |

**New core pieces proposed by this research** (not decided; Q1–Q6, Q16,
Q21)

| New core piece | Plugins it unlocks | Why core |
|---|---|---|
| **Fields contract**: gridded 2D/3D frames with `valid_start`/`valid_end`, `issue_time`, quantization and an archive path | weather, hazards (smoke, GOES fire, HeatRisk), sky (clouds), gardening (PRISM, NBM frost), wildlife (radar biology), farm (ET) | Radar volumes span 4–7 min, GOES scans have a start and an end, accumulations are windows, and forecasts need an issue time |
| **Recurring lifecycles plus a rules-by-date evaluator**: an RFC 5545 subset (yearly windows, weekday sets, hours), Boise local time, windows that wrap past New Year, override precedence, raw text kept | trails (direction, even/odd days, e-bikes), lands (MVUM, IDPR seasons, stay limits), wildlife closures, water (float season), farm (canal seasons), cycling | At least four plugins need it |
| **Sun and moon ephemeris plus lighting state**: TypeScript and Python twins with shared conventions | sky, gardening, the camera glare calendar ([ch. 11](11-camera-validation-layer.md)), commuter glare, weather lighting, trail thaw and shade, cycling shade walk | Every plugin with sun or shade needs it. [§15.7](15-plugins.md#157-ideas-for-later-plugins) currently lists it under `sky` |
| **Surface-model (nDSM) tiles** in `basemap/` | gardening, sky shadows, land cover and 3D trees, transit stop shade, trail and walk shade | Same pipeline as terrain-RGB |
| **Point occurrences and versioned geometry** | occurrences: wildlife roadkill, lightning, FIRMS detections, quakes, bird strikes (crashes already behave this way); versioned geometry: fire perimeters, IDL zones, trails, lanes | Zero-length lifecycles are never "active" at an instant |
| **Routing graph** (pgRouting first, or a self-hosted BRouter or Valhalla) | cycling, trails, safe routes, transit first and last mile, the landlocked analysis | Five personas need it |
| **Sensitivity and privacy rules** | wildlife and nature, crashes, CoCoRaHS, wells and water rights, IPAWS | Two separate mechanisms: (a) a per-taxon sensitivity table (IDFG flag, ESA and eagles, NatureServe S1–S2, an owner list); (b) a per-record "obscured" flag that keeps a record out of any cell finer than its obscuring cell. Align grids to 0.2° multiples. Field-drop lists at ingest |
| **Ingest framework fixes** | everything | (1) Merge same-agent robots.txt groups, as RFC 9309 §2.2.1 requires (`_group()` in `ingest/http.py` returns only the first). Resolve exact ties as disallow, since we're already deliberately strict (Canyon County and ScienceBase both have two `*` groups). (2) A **query-only** ArcGIS client that never calls `applyEdits`, reads each layer's own maxRecordCount, pages by objectIds or resultOffset, and dedupes on GlobalID. (3) Change gating on `lastEditDate`, DCAT `modified` or a content hash. (4) Per-host budgets (the IEM queue). (5) Treat a WAF challenge as disallowed |

---

## 17.4 Proposed order with rough effort

**Not decided.** Effort: S is about 1–2 days, M about a week, L 2–3 weeks
or more. The proposal is consistent with
[ch. 16 §16.4](16-ideas-and-personas.md#164-shared-core-pieces-serve-almost-every-persona):
after UI v2, hazards and water first as the cheapest, then lands and
trails. Each source still goes to the owner one at a time.

**Wave A: start the clocks** (about 1–2 weeks; ingest only, keyless,
standard library, no UI)
- Prerequisites (S): the robots group-merge fix, the query-only ArcGIS
  guard, per-host budgets.
- Pollers that save history we can't get back:
  - R2R conditions and Greenbelt closures;
  - IDL fire stages, R4 forest orders, IDPR closures;
  - WFIGS (absolute ModifiedOn filter), FIRMS CSV, HMS KML, NWS WWA;
  - AWC METAR and NWPS gauges;
  - E. coli and river hazards;
  - IDFG roadkill;
  - AgriMet ET (April–October), USDM weekly;
  - USGS quakes, SNOTEL hourly;
  - SWPC OVATION, stored as one array per snapshot (at about 650 values
    every 30 min, one row per value would be about 11 M rows a year).
- Total stored: well under 50 MB a day, all into `raw.record` and
  `obs`/`evt`.

**Wave B: reference layers** (about 2–3 weeks, mostly S each through the
ArcGIS reader; refreshed monthly)
- Federal and state: BLM (SMA, GTLF, PLAD/MAPLand, allotments, mining
  claims, designations), USFS (MVUM, trails, INFRA, boundaries, roadless),
  IDL ownership, FWS refuges and critical habitat, the IDFG Hunting
  MapServer.
- IDWR: irrigation organizations, season of use, diversion sites, irrigated
  lands 1987–2015.
- Local: ACHD bike and pedestrian LTS layers, COMPASS bike and pedestrian
  layers, Boise parks and pathways, IDPR trails.
- SSURGO; NIFC perimeter history.
- Hand downloads: PAD-US, HydroShare canals, the hardiness zone map,
  normals and IGRA.

**Wave C: core pieces and the first user-facing features** (after UI v2)
- Core:
  - full replay, search, the Valley Feed and the time-series card (per
    ch. 16 §16.4);
  - the rules-by-date evaluator (M), sun ephemeris and lighting (M),
    `osm_active` (M), occurrences and versioned geometry (S–M), areas
    including the Oregon flag (S).
- Features:
  - the fire board and closures feed (M), "Can I be here?" (M), the cyclist
    and walker map (S–M);
  - the "My yard" card (M), the glare layer (M), the Tonight panel (M);
  - animals on the road (M), farm water today (S).

**Wave D: decoders and gridded data** (about 1 week for the worker image
and the contract, then S–M per source)
- The worker image and the fields contract.
- MRMS 2D; RTMA via NOMADS; NBM COGs; GOES L2 (test HDF5 chunked reads
  before accepting 4.5–66 MB per file); HRRR `prs` or Zarr.
- CDL, NLCD and IDWR rasters as categorical tiles; PRISM; VIIRS lights.
- Then 3D weather phases 1–4 (§17.5; about 10–14 weeks).

**Wave E: heavy and research work** (L each unless noted)
- Lidar nDSM and sun hours.
- CSB field cards and Sentinel-2.
- The LTS engine, BNA and the routing graph.
- The night dome and satellites.
- Radar biology.
- The landlocked analysis (M).
- GBIF aggregates (M).
- The mud and thaw model, once a wet season of R2R labels exists (M).

---

## 17.5 Weather in 3D: a phased design

A proposal, not decided. The sources and rendering references are in
[sources/weather-3d.md](sources/weather-3d.md) and
[sources/weather.md](sources/weather.md).

**Principles**
- Keyless NODD inputs only.
- Raw files are cropped and deleted; derived "bricks" are kept
  permanently.
- Raw Level II is re-fetched from AWS on demand (a lazy archive).
- Every element carries a source, its age, and a kind chip: observed,
  analysed, model, reconstructed, or texture. No silent fallbacks.
- Credit "NOAA MRMS/HRRR/GOES (derived)". The public layer uses NOAA inputs
  only; RWIS stays internal.

**Phase 0: groundwork** (about 1 week)
- METAR, RTMA-RU (via NOMADS) and the BOI sounding as readings.
- Core sun position.
- MapLibre `sky` fog driven by visibility. Fog extinction is
  **σ = 3.0 / visibility**, the 5% meteorological optical range that ASOS
  and RTMA report; Koschmieder's 3.912/V makes fog about 30% too dense.
- Decisions needed: the fields contract and the worker image (numpy,
  eccodes, pyproj, h5py).

**Phase 1, MVP: radar in 3D** (2–3 weeks)
- Data:
  - MRMS MergedReflectivityQC, whole-CONUS gzipped GRIB2 at about 1.10 MB
    per level.
  - Fetch about 26 levels up to 12 km MSL only when the 0.2 MB PrecipFlag
    shows echoes in the ring. Cost: about 30 MB a day dry, about 4 GB a day
    at 10 min while wet, about 20 GB a day at 2 min.
  - The 0.50 and 0.75 km MSL levels sit below the valley floor.
  - Nodata codes: 3D uses −99 for missing and −999 for no coverage; 2D
    uses −1 and −3.
  - Encode as uint8 with 5–80 dBZ over codes 1–254, 0 = missing, 255 = no
    coverage. The ring crop is 170 × 140 × 26, about 619 KB raw.
- Renderer: a `weather-3d` custom layer in our engine, with its own anchor
  slot below points and labels.
  - Ray-march against the loaded terrain-RGB heightfield at roughly screen
    resolution, because MapLibre doesn't expose depth as a texture. A coarse
    256² ring DEM bleeds through hills.
  - Skip empty space with an occupancy brick.
  - Retina: render at a quarter of device resolution per axis, or budget 4×
    the GPU time.
  - Heights at the terrain's exaggeration. Per-sample latitude scale (about
    2.3% across the ring).
  - A colour-blind-safe ramp.
  - A radar-blind mask from RadarQualityIndex. Later, per-volume coverage
    pattern (VCP): KCBX is about 14 km **south** of downtown (bearing 191°,
    coordinates ⚠️). The top tilt reaches about 6.0 km over downtown only in
    precipitation scan modes; in clear air the hole starts near 2.5 km.
- Exit: a real storm or snow event replays at 60 fps at z10 on the owner's
  laptop and matches the camera frames and RWIS.

**Phase 2: clouds** (3–4 weeks)
- HRRR cloud water, ice, rain, snow and graupel mixing ratios plus HGT, TMP
  and U/V from `wrfprs` byte ranges (about 38–110 MB an hour) or the
  HRRR-Zarr `prs` store. HRRR-Zarr has no license text, and only its
  analysis hours were verified ⚠️.
- Mask isobaric levels below ground (about 1013–925 hPa) with surface
  pressure.
- Extinction: σ = 3·LWC / (2ρ·r_e), with ρ_ice ≈ 917 kg/m³ for ice.
- GOES-18 ACM clips model cloud where GOES sees clear sky. ACHA2KM sets
  tops after parallax correction: the satellite zenith angle is 54.5°, so
  tops are displaced about 1.4 × height toward the NE.
- Bases from METAR and RTMA ceilings.
- A light volume rebuilt only on a new frame or a sun move; cloud shadows
  draped on the ground; noise detail badged "texture".
- An observation-only slab fallback, ported from three-clouds' layered
  technique rather than its data model.
- `wrfnat` only if cloud fraction (FRACCC) is wanted.

**Phase 3: fog, inversion and smoke** (2–3 weeks)
- An analytic height-fog integral, not stacked planes (no banding).
- Fog top from the 12Z sounding and HRRR low-level cloud. GOES cloud-cover
  layers are too coarse for this.
- Night fog extent from our own GOES band 7 minus band 14 difference (night
  only; FLS isn't openly distributed).
- An inversion lid plane.
- 3D smoke from HRRR `wrfnat` MASSDEN (53.5 MB an hour), fetched only on
  HMS smoke days. RRFS has no 3D smoke.
- GOES ADP outlines; AirNow as ground truth once the form is returned.
- Vertical resolution near the ground (25 hPa is about 250 m) is too coarse
  for 100–300 m fog. That's why fog is analytic here.

**Phase 4: particles, lightning and wind** (2–3 weeks)
- Particles near the camera.
- Precipitation phase from HRRR temperature and wet-bulb profiles
  (warm-nose freezing rain), the CFRZR and CICEP flags, and MRMS surface
  PrecipFlag. Bright-band heights are in m above MRMS terrain.
- Lightning:
  - GLM flashes as glows, not bolts (several-km offset);
  - MRMS NLDN density as shading only, or bolts badged "reconstructed".
    NLDN redistribution terms are ⚠️ (Vaisala-derived).
- 10 m wind streaks using the webgl-wind technique.

**Phase 5: later**
- KCBX Level II sweeps and dual-pol. Two decoders are needed: Message 31,
  plus legacy Message 1 and .gz files from before about 2008.
- Level III classes (from Mar 2022) and bird migration (vol2bird).
- An RRFS adapter (operational Nov 3, 2026; 3 km pressure levels; a 1.5 km
  fire nest, which NCO lists as 1.27 km ⚠️; NOMADS has no grib filter for
  it).
- A crash-weather backfill: MRMS from Oct 2020, HRRR from 2014.

**Budgets**
- GPU: 4 ms or less per frame while moving, near zero when idle
  (accumulate jittered frames), 64 MB or less of GPU memory.
- Storage: about 30 MB a day dry, 150–400 MB a day stormy.
- Downloads for the full set with the `prs` route: about 5–15 GB a day
  typical.

---

## 17.6 Refuted and risky sources

### A. Avoid (robots.txt, terms, or they describe people)

| Source | Why |
|---|---|
| api.weather.gov | robots.txt `Disallow: /` (alerts.weather.gov returns NXDOMAIN). Use the NWS WWA map service, tgftp and IEM instead |
| SPC site, UWyo soundings, nowCOAST geoserver, NCEI `/data*`, Open-Meteo, the GSL HRRR-Smoke site, IEM's NEXRAD and model mirrors | robots.txt; equivalents exist on allowed paths |
| GOES fog/low stratus (FLS) | SBN/AWIPS only |
| Synoptic; MADIS restricted sets; CWOP and personal stations | eligibility, an application, or private homes |
| InciWeb, NOAA NGFS, DEQ burn decisions (`/air/crb/`) | robots.txt; DEQ's map also names growers' fields |
| PurpleAir | robots.txt, paid, no redistribution, conflicts with an MIT repo, sensors at homes |
| Quick Stats API, uspest.org models, OpenET | robots.txt or terms (NASS bulk files are fine) |
| FSA CLU; Reclamation Land Ownership; NCED | law (7 U.S.C. 8791); terms forbid derived products and dissemination; frozen since Jan 2025 |
| CelesTrak GP (automated), the Gaia archive, lightpollutionmap, the NASA POWER API, the Recreation.gov and RIDB APIs, getoutside.idaho.gov | robots.txt or a bot challenge |
| eBird and iNaturalist APIs, HawkCount, BikeMaps.org JSON, Lime GBFS | robots.txt (eBird and iNaturalist reach us via GBIF) |
| Strava (including Metro), Trailforks, AllTrails, social media | project rule; terms; activity heatmaps track people |
| IDFG Wildlife_Conflicts_public; Movebank; ISDA and EPA ECHO dairy points | personal data or tracking individual animals |
| Boise's copy of ACHD's Regional Low-Stress layer; Shadertoy and Mapbox GL v2+ code | terms forbid sharing; licence contamination |
| NREL SPA C code; Planetary Computer height above ground; the ISU DSM; 7Timer; Clear Sky Chart | licence; no coverage; no licence; redundant; link only |

### B. Usable with care

| Source | The care needed |
|---|---|
| ScienceBase | Its robots.txt has two `User-agent: *` groups. Cloudflare's managed block comes first: `Allow: /` for everyone else, while named AI agents, Claude-User among them, are disallowed. The operator's own section follows and blocks all bots (`Disallow: /`). Hand download in the owner's browser only |
| Geofabrik | Serves its disallowing robots.txt only to browser user-agents; keep downloads by hand |
| Unreachable hosts, treated as disallowed | rockyweb.usgs.gov (QL1 lidar), gis2.idaho.gov, landfoliogis.idl.idaho.gov, www.fsa.usda.gov, ndmcgeodata.unl.edu, www.usgs.gov |
| Services advertising public edits (Barber Park, IDFG access sites, Pheasant_Stocking) | Query only; values unverified |
| IDPR trails | Non-commercial use, with attribution |
| AirNow | Preliminary, unaltered, not for trends or guidance; the guidelines form is required |
| ACHD layers | Disclaimer only |
| HRRR-Zarr | No licence text |
| Ada herd districts | Credited to the Assessor |
| NLDN density | Vaisala-derived |
| USA-NPN | The data is CC BY 4.0, but its terms forbid automated access |

### C. Refuted claims (don't build on these)

| Claim | What's true |
|---|---|
| "RRFS replaces HRRR / HRRR is frozen" and "RRFS operational Oct 14" | RRFS goes live Nov 3, 2026 and replaces NAM, HREF, SREF and HiresW. REFS uses HRRR members |
| "NOMADS filters RRFS" | It doesn't |
| "MRMS live at /data/" | It redirects to the root |
| "Treasure Valley 1-minute ASOS at BOI, MAN and EUL" | BOI only |
| GOES product cadences and folders | LST is hourly, not every 5 min; CONUS DSR has no data after 2024; RRQPE is full disk only; there is no FLS folder |
| "IGRA needs the owner" | No: `/pub` is allowed |
| "2020 fire perimeter gap" | There is none |
| "WFIGS history since 2008" | Documented from 2014 |
| "OSM trails and bike tags loaded Oct 7" | Paths, footways and the Greenbelt are dropped. On-street bike tags on major ways are in `raw.record` |
| "QL1 lidar has an EPT copy" | It doesn't |
| "IDWR 2023 irrigated lands is polygons" | It's a raster |
| "Treasure Valley METRIC after 2015" | There is none |
| "AgriMet history needs `/pn-bin`" | False for ET |
| "GTLF season dates" | A yes/no flag only |
| "Source Cooperative CSB holds history" | 2023 crop only, dissolved |
| "No BLM WSA in the ring" | 5 polygons in the Oregon strip |
| "IDFG winter range layer" | Priority complexes only |
| "API key needed for USGS" | Optional; the blocker is robots.txt |
| "Idaho Centennial Trail in the ring" | 0 segments |

### D. Process notes for the record

The research made small, paced metadata, listing and count queries and a
few small sample reads; each catalog's status note lists the requests its
passes made. No account was created, no dataset was downloaded, and nothing
went into the repository, the server or the database.

Four rule slips by the research agents:
1. A researcher fetched Idaho DEQ's crop-residue burn decision map (with
   the WebFetch tool) after reading a robots.txt that disallows it.
2. One metadata request reached `hazards.fema.gov/arcgis` before its
   robots.txt result was read; that path is disallowed.
3. A verifier fetched one ScienceBase page before reading robots.txt, which
   disallows Claude-User.
4. Researchers made more AgriMet static reads than the one-or-two-sample
   guideline (on allowed paths).

None will be repeated, and nothing from them was downloaded or stored.

A related note on ScienceBase: our parser reads only the first of its two
`*` groups (Cloudflare's `Allow: /`), so the research's catalog-metadata
requests there with our User-Agent (item records and listings, no data
files) passed our robots check. Merged as RFC 9309 requires, the two `*`
rules tie. RFC 9309 says a tie should go to allow, but the proposed merge
fix resolves ties as disallow (§17.3, Q16), and on that reading ScienceBase
is hand download only (B above).

The claim that "idahofireinfo.com and firerestrictions.us now serve
gambling content" is unverified and was deliberately not fetched.

---

## 17.7 Owner actions, consolidated

| Type | Action | For |
|---|---|---|
| Account or key (optional unless noted) | A Space-Track account | sky (Starlink, history) |
| | A FIRMS MAP_KEY; an EPA AQS key; a GBIF account; an Earthdata Login; EOG registration ⚠️; a Census key (or hand tables) | hazards, wildlife, sky, cycling |
| | A FEMS account with the API role | fire danger, RAWS history |
| | **AirNow: return the guidelines form and notify DEQ (required before using it)** | hazards, gardening, cycling |
| | An AWS account: not needed (polling S3 works); only for SNS push | weather |
| Hand download | PAD-US Idaho (150 MB) and Oregon (291 MB); HydroShare canals (accept CC BY); FEMA NFHL (Ada, Canyon); IEM yearly zips | lands, farm, hazards |
| | The Falchi atlas; VIIRS VNL; the SVS 8K map; a HYG clone; the FAA strike database | sky, wildlife |
| | Big runs that wait on the disk decision (Q10): QL1 lidar (162 GB), Wildfire Risk to Communities for Idaho (6.56 GB), CSB national (3.76 GB), CDL and NLCD clips, FPA FOD (220 MB), Geofabrik's Oregon extract (weekly) | gardening, hazards, farm, trails |
| Notes and asks | City of Boise: republishing R2R conditions and trails, the 2021 canopy land cover, heat data, Ride Report and Lime | trails, gardening, cycling |
| | Ada County Parks: what the Barber Park sensors mean, republishing, a heads-up about its public edit capabilities | water |
| | ACHD: republishing the bike and pedestrian layers, category codes, counters | cycling |
| | COMPASS: hourly counter data, Data Bike, republishing the swidrdc layers | cycling |
| | IDFG IFWIS (see Wildlife in §17.2); IDL (a courtesy note, the camping stay limit); IDWR and the Water District 63 watermaster; Reclamation (`/pn-bin`) | wildlife, lands, farm, gardening |
| | NWS (API robots.txt); USGS (water API robots.txt); CelesTrak; Cornell BirdCast; IBO; Idaho Power; Ada County Emergency Management (Genasys); DEQ (a zone-level burn feed); Ridge to Rivers (its imagery source) | various |
| Local helper | Check gis2.idaho.gov, landfoliogis, rockyweb.usgs.gov and conservationeasement.us from the owner's network; WESM lidar coverage at the owner's location; pgRouting in the database image | lands, gardening, cycling |
| Queries on our database | ITD versus COMPASS bike and pedestrian counts; COMPASS `crash_unit.event` animal values; crash direction of travel; OSM wildlife-crossing tags on SH-21 | cycling, wildlife, sky |

---

## 17.8 Open questions

**Structure**

1. Add **fields** as a fourth core time shape?
2. Put **recurring lifecycles and the rules-by-date evaluator** in core?
3. Move the **sun and moon ephemeris and lighting** into core (this changes
   §15.7)?
4. Add **nDSM surface tiles** to the core basemap, with PDAL as a build
   tool?
5. Add **point occurrences** as a shape, plus **versioned geometry**?
6. A **routing graph**: pgRouting on our own graph, or BRouter or Valhalla?
7. Plugin boundaries:
   - who owns smoke and air quality, fire detections, snow and gauges
     (weather, hazards or water);
   - `hazards` with or without a separate `air`;
   - `wildlife` with or without a separate `nature`;
   - the float season in `water`;
   - `active` as its own plugin or spread across existing ones;
   - WMAs and refuges in `lands`.
8. One `core.met_station` table with a network column, replacing today's
   511-keyed station table?

**Infrastructure** (decisions about the server)

9. A **worker image** beyond the standard library (numpy, eccodes, GDAL,
   h5py, pyproj; later Py-ART, a Parquet reader, R with vol2bird)? One
   image or several? The prebuilt wheels need checking against the server
   first (see the private notes).
10. **Disk:** about 80 GB was free on Oct 6 ([DECISIONS](DECISIONS.md)).
    Agree on weather retention (full cadence for 14 days, then thinned), a
    lazy NEXRAD archive (no raw Level II, which is 0.45–1 TB a year), and
    whether the big one-offs wait on the disk decision.
11. **Bandwidth:** does the server's internet connection have a data cap?
    Weather is about 5–15 GB a day typical and 20+ GB on 2-minute storm
    days.
12. Adding pgRouting changes the database image; approve?

**Policy and robots.txt**

13. Treat api.weather.gov as off-limits (recommended), ask NWS, or write an
    exception?
14. USGS Water Data API: ask USGS. Use NWPS meanwhile, and decide whether
    to run a one-off legacy backfill before the planned outages start in
    January 2027 (shutdown Feb 22, 2027).
15. CelesTrak: ask for written permission, or skip it?
16. Approve the robots.txt group-merge fix, with disallow on exact ties?
17. Extend "no license: use it and send a courtesy note" from city and
    county imagery to state agency GIS (IDFG, IDL, IDWR)?

**Scope**

18. The Oregon strip: clip to Idaho with "no data", or add Oregon sources
    (the national SMA, PAD-US Oregon, BLM Vale, ODFW, Oregon law)?
19. Larger areas: a roughly 300 km weather-context area, the whole Boise NF
    and the Owyhee wilderness for lands, and a terrain build for the ring
    (only 10–30 m there today)?
20. Public weather and hazard layers now, or tailnet-only for the moment?

**Privacy and display**

21. Approve the sensitive-species rules, and the rule that winter range is
    never drawn?
22. Drop person-related IPAWS alerts at ingest?
23. Aggregate yard-scale results for any guest view?
24. Keep the mandated AQI and HeatRisk colours, always with the word and
    number?
25. May the camera haze index be published?
26. Weather drawn below labels? The atmosphere at the terrain's
    exaggeration, with an optional labelled stretch?

**Research choices**

27. The fog-study definition: for example, under ¼ mile at BOI or in RTMA
    cells along key corridors, 6–9 am?
28. Glare thresholds, and do COMPASS crash records carry each vehicle's
    direction of travel?
29. After Nov 3: stay on HRRR (still the only 3D smoke source) behind a
    model adapter, or add RRFS forecasts and its fire nest?
30. Night dome scope: magnitude 6.5 or 9?
31. Which lidar area first?
32. Start collecting R2R labels this wet season for the mud model?
33. Publish the landlocked-land results, or keep them owner-only?
34. Optional asks that are worth it: American Farmland Trust's Farms Under
    Threat 2040, OpenET, Audubon's Christmas Bird Count?
