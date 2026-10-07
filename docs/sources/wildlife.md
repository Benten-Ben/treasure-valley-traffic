# Wildlife sources (researched Oct 7, 2026)

Sources for a `wildlife` plugin: animals on our roads, wildlife habitat and
the seasonal rules that protect it, hunting and fishing land, biodiversity
observations, bird migration (including weather radar), and how to show
sensitive species safely. The study area is the valley box (W −117.05,
S 43.00, E −115.95, N 43.85) and the proposed regional ring (about
W −117.30, S 42.90, E −115.60, N 44.30; [DECISIONS](../DECISIONS.md)).
This page belongs to [chapter 17](../17-sources-for-new-plugins.md)
(sources for the new plugins); the ideas behind it are in
[chapter 16](../16-ideas-and-personas.md#wildlife-wildlife).

**Status: research only; nothing here is approved.** Each source goes to
the owner one at a time before anything is built. Every entry was checked
against its official pages, robots.txt and terms on Oct 7, 2026: of the 28
sources, 13 were confirmed, 14 corrected and 1 is unverifiable (the FAA
strike database's download). None was refuted outright, but two claims
were: that IDFG's hunting layers need a token, and that IDFG's conflict
service exposes its records. "Not re-run" marks figures from the research
pass that verification didn't repeat; ⚠️ marks anything resting on
secondary sources or not checked at all.

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| **Animals on roads** | | | | | | | | |
| [IDFG Roadkill Observations](https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer/1) | IDFG, with ITD | One point per carcass or salvage report, 1977 on; 5,841 in the box; updated near-daily | ArcGIS MapServer and FeatureServer, 100,000 records a query | None | No license; disclaimer only. Credit IDFG; courtesy note (owner to confirm the rule applies) | 404, no rules | Use | Corrected |
| [ITD crash units, animal events](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35) | ITD | Police-reported crash units whose most harmful event is an animal, 2005–2023, with time of day | ArcGIS MapServer, 70,000 a query | None | Credit ITD | 404, no rules | Use | Confirmed |
| [SH-21 wildlife crossings](https://www.fws.gov/story/2024-03/idahos-new-wildlife-overpass-improves-public-safety-and-wildlife-migration) | USFWS; IDFG | Cervidae Peak overpass (2024) and Robie Creek underpass (2010): place, cost, collision figures | Facts entered by hand | None | Facts and links (IDFG pages may not be mirrored) | `/story/` and `/press/` allowed | Use | Corrected |
| [511 Idaho message signs](https://511.idaho.gov/) | ITD | Wildlife warnings on message signs; already recorded | Already ingested | Free key (we have one) | Not republished; only WZDx may be | Covered by the 511 API approval | Internal only | Confirmed |
| **IDFG layers and requests** | | | | | | | | |
| [IDFG open-data hub](https://data-idfggis.opendata.arcgis.com/) | IDFG | 37 layers: WMAs, GMUs, controlled hunts, hunting restrictions, access sites, birding trail, species ranges, conservation sites | Hub search API; FeatureServers on two hosts | None | Per-item disclaimers; some "free, unrestricted access and use"; credit IDFG | Hub: Crawl-delay 60, `/api/` allowed; data hosts no rules | Use | Corrected |
| [IDFG GIS portal services](https://gisportal-idfg.idaho.gov/hosting/rest/services) | IDFG | Species hex grid with a sensitive flag, monarch model, pheasant stocking, CWD results, public Hunting map (closures, Access Yes!) | ArcGIS REST | None | Mostly unstated; Hunting map "CC-BY Idaho Fish and Game" | 404, no rules | Use | Corrected |
| [IDFG token-only layers](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Mule_Deer_Seasonal_Ranges/MapServer) | IDFG | Mule deer seasonal ranges, fishing rules, AccessYes, Fire and Conservation folders | 499 "Token Required" | Partnership | Unknown | 404, but not open | Needs owner action | Corrected |
| [IDFG website apps](https://idfg.idaho.gov/fish/stocking) | IDFG | Over 100,000 fish stocking events since 1967, weekly schedules, Hunt Planner | Website only | None | Viewing only; no copying, display or mirroring | Drupal defaults; `/fish/` allowed | Needs owner action | Confirmed |
| [IDFG data requests](https://idfg.idaho.gov/data/request) | IDFG | Exact locations of species with special conservation status | Request form, 1–3 weeks | Paid (free, $200 or $500) | Discretionary, per request | Not applicable | Needs owner action | Corrected |
| [IDFG Wildlife_Conflicts_public](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Wildlife_Conflicts_public/FeatureServer/0) | IDFG | Intake for conflict reports; personal contact fields | Write-only FeatureServer | None | None stated | 404 | Avoid | Corrected |
| **Habitat, lands and seasonal rules** | | | | | | | | |
| [USFWS Critical Habitat](https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/USFWS_Critical_Habitat/FeatureServer) | USFWS | Final and proposed ESA critical habitat units (slickspot peppergrass in south Ada) | ArcGIS FeatureServer, 1,000 a query | None | Public domain | 403, no rules | Use | Confirmed |
| [USFWS ECOS and IPaC](https://ecos.fws.gov/ecp/services) | USFWS | Listing status; ESA species and birds of concern that may occur in an area | REST pull reports; IPaC POST API | None (IPaC announces a future key) | Public domain | 404, no rules | Use | Corrected |
| [USFWS refuge boundaries](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer) | USFWS | Deer Flat NWR outlines (Lake Lowell, Snake River Islands) | ArcGIS FeatureServer, 2,000 a query | None | Federal; "not all areas are open to the public" | 403, no rules | Use | Confirmed |
| [Deer Flat NWR rules](https://www.fws.gov/refuge/deer-flat/visit-us/rules-policies) | USFWS | Boating, island, off-trail, swimming, cycling, dog and drone rules | Facts entered by hand | None | Public domain | `/refuge/` allowed | Use | Confirmed |
| [Birds of Prey NCA shooting map](https://www.blm.gov/documents/idaho/public-room/map/morley-nelson-snake-river-birds-prey-safe-shooting-map) | BLM Boise District | Firearm zones and the Feb 15–Aug 31 canyon closure | PDF, entered by hand | None | Public domain | `/documents/` allowed | Use | Confirmed |
| [Boise River WMA rules](https://idfg.idaho.gov/wma/boise-river) | IDFG | Seasonal closures, dog-leash season, road seasons | Facts entered by hand | None | Facts and links only | `/wma/`, `/press/` allowed | Use | Confirmed |
| [USGS ungulate migrations](https://www.sciencebase.gov/catalog/item/6729962bd34e338a476a38ef) | USGS | Elk routes and stopovers; Idaho only south of the ring | ScienceBase API, zip, WMS and WFS | None | CC0 | Allowed (ai-train=no signal) | Use (context) | Corrected |
| **Observations and tracks** | | | | | | | | |
| [GBIF occurrence API](https://api.gbif.org/v1/occurrence/search) | GBIF | 2.87 million occurrences in the box (eBird, iNaturalist, herbaria and more) | REST; offset + limit ≤ 100,000; facets | None | Per record: CC0, CC BY 4.0 or CC BY-NC 4.0 | Allowed (one image path disallowed) | Use | Corrected |
| [GBIF snapshot on AWS](https://registry.opendata.aws/gbif/) | GBIF | The whole occurrence table as Parquet, monthly, about 180 GB | S3, unsigned | None | Listed as CC BY-NC; per-record licenses kept | Not applicable (S3) | Use | Corrected |
| [NatureServe Explorer API](https://explorer.natureserve.org/api-docs/) | NatureServe | Global and state conservation ranks; sensitivity categories | REST JSON | None | CC BY 4.0 (Explorer); cite NatureServe Explorer | Allowed | Use | Corrected |
| [Breeding Bird Survey](https://www.sciencebase.gov/catalog/item/6a0b0b0ab66b0188da36aedd) | USGS | Roadside point counts every June, 1966–2025 | ScienceBase files, yearly | None | CC0 | Allowed | Use | Corrected |
| [eBird direct](https://www.birds.cornell.edu/home/ebird-api-terms-of-use/) | Cornell Lab of Ornithology | API, raw dataset (EBD), Status & Trends | Key, account or request ⚠️ | Free key | Terms unreadable to us (403) ⚠️ | `Disallow: /` on all three hosts | Avoid | Confirmed |
| [iNaturalist API and photo bucket](https://api.inaturalist.org/v1/docs) | iNaturalist | Observations (API); CC or CC0 photos (bucket) | API; S3 unsigned | None | Per observation and photo | API `Disallow: /`; bucket none | Avoid (API) | Confirmed |
| [Movebank](https://www.movebank.org/cms/movebank-content/general-movebank-terms-of-use) | Max Planck Institute of Animal Behavior | Individual animal GPS tracks | Download | Account ⚠️ | Data owner's permission unless CC0, CC BY or CC BY-NC | 404, no rules | Avoid | Confirmed |
| **Bird migration and the sky** | | | | | | | | |
| [NEXRAD Level II, KCBX](https://registry.opendata.aws/noaa-nexrad/) | NOAA NWS; bioRad and vol2birdR | Nightly bird density, speed and direction by altitude near Boise | S3, unsigned (push needs an AWS account) | None | Open; credit NOAA | Not applicable (S3) | Use | Corrected |
| [BirdCast](https://birdcast.org/migration-tools/migration-dashboard/) | Cornell, Colorado State, UMass Amherst | Nightly radar migration estimates by county | Web only | None | No data license; citation forms only | Crawl-delay 10; dashboard 404 | Needs owner action | Confirmed |
| [IBO Lucky Peak and HawkCount](https://www.boisestate.edu/ibo/science/lucky/) | Boise State IBO; HMANA | Hawkwatch and banding seasons; daily raptor counts | Pages read by hand | None | Not stated | boisestate.edu allowed; hawkcount.org `Disallow: /` | Needs owner action | Confirmed |
| [FAA Wildlife Strike Database](https://wildlife.faa.gov/home) | FAA | About 344,000 civil-aircraft strikes, 1990–2025 | Web app; download unconfirmed ⚠️ | Unknown | US government data ⚠️ | No valid rules (HTML shell) | Use, by hand | Unverifiable |

**Verdicts:** 18 use, 1 internal only, 5 need an owner action, 4 avoid.

## Animals on roads

### IDFG roadkill observations

Use · verified: corrected · confidence high · effort S

- **Endpoint:** `gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer/1`;
  the FeatureServer answers too. IDFG's open-data hub lists it as
  "Roadkill Observations", pointing to the FeatureServer.
- **Contents:** one point per carcass report. Fields (checked Oct 7):
  `OBJECTID`, `species`, `source`, `observed`, `salvaged`, `sex`,
  `lifeStage`, `lifeState`, `disposition`, `decomposition`, `latitude`,
  `longitude`, `highway`, `milepost`, `note`, `reported`, `county`,
  `region`, `gmu`, `path`, `Shape`, `GlobalID`. No reporter name, email or
  phone fields. What `path` means is unknown; it may point to an
  attachment or photo.
- **Dates:** the service says the data starts in 1977, but the earliest
  `observed` in the box is 1970-04-02, so pre-1977 dates look like entry
  errors. Dates are stored at 00:00 UTC, so they are calendar dates with no
  time of day (converted to Boise time they would fall at 18:00 the day
  before).
- **Coverage:** statewide, the box and the ring. 5,841 records in the box
  (re-counted Oct 7); about 9,267 in the ring and 70,442 statewide
  (researcher; not re-run, nor were the species and source breakdowns).
  Uneven sampling: it's driven by salvage reports (the salvage law took
  effect in 2012, per [IDFG](https://idfg.idaho.gov/species/roadkill)), so
  deer and elk are over-represented and small animals under-represented.
- **Access:** capabilities Map, Query and Data; `maxRecordCount` 100,000;
  JSON, GeoJSON or PBF; `outStatistics` works. The service description
  warns that the hub's filters don't update correctly and recommends
  downloading the full CSV. The core ArcGIS reader can page by `OBJECTID`.
- **License and terms:** none. The description is a disclaimer only
  ("Idaho Fish and Game does not assume liability") and warns of duplicate
  reports. IDFG's [website terms](https://idfg.idaho.gov/terms) define
  "our Websites" as idfg.idaho.gov, gooutdoorsidaho.com, gofishidaho.org
  and gohuntidaho.org, so their no-mirroring clause doesn't reach the GIS
  portal. The owner's Oct 6 "no license: use it and send a courtesy note"
  rule was stated for city and county imagery
  ([DECISIONS](../DECISIONS.md)); applying it to IDFG needs the owner's OK.
- **robots.txt:** `gisportal-idfg.idaho.gov/robots.txt` returns 404 (an
  IIS error page): no rules. Re-checked Oct 7.
- **Updates and size:** near-daily (the latest observed and reported dates
  were Oct 6, 2026 when checked Oct 7); a daily or weekly poll is plenty.
  About 9.3k rows in the ring (researcher), about 70k statewide; under
  10 MB.
- **Use cases:** deer-strike risk per road segment by month (seasonal only,
  since there is no time of day); before and after the SH-21 underpass
  (2010) and the Cervidae Peak overpass (2024); carcass reports beside
  police-reported animal crashes, labelled as a reporting-channel ratio; a
  Valley Feed card for a new carcass on my route.
- **For:** commuters and drivers, traffic safety researchers, hunters,
  wildlife watchers. **Needs:** the shared ArcGIS reader, the segment
  matcher (roads plugin), a display for point events in time, the Valley
  Feed, areas (box and ring).
- **Risks:** reporting bias toward salvage reports; IDFG warns of
  duplicates. The free-text `note` may hold personal details: drop it at
  ingest rather than keep it internally, since nothing uses it. Don't fetch
  or publish whatever `path` points to until it's understood. Publish taxa
  IDFG flags as sensitive only as aggregates. Treat pre-1977 dates as
  suspect. Send a courtesy note before republishing.
- **Verification:** confirmed the fields, the absence of reporter
  identity, the disclaimer, the CSV advice, `maxRecordCount` 100,000, the
  FeatureServer, the hub listing, robots.txt and the box count. Corrected:
  the latest record is Oct 6, not Oct 3, so it updates almost daily; dates
  are calendar dates; the 1970 minimum is suspect.
- **Evidence:** [robots.txt](https://gisportal-idfg.idaho.gov/robots.txt),
  [MapServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer?f=pjson),
  [layer 1](https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer/1?f=pjson),
  [FeatureServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/FeatureServer?f=pjson),
  one `outStatistics` query on the box (count, minimum and maximum of
  `observed` and `reported`) at `.../MapServer/1/query`,
  [hub search](https://data-idfggis.opendata.arcgis.com/api/search/v1/collections/dataset/items?limit=100),
  [IDFG roadkill page](https://idfg.idaho.gov/species/roadkill),
  [highway–wildlife collisions](https://idfg.idaho.gov/wildlife/highway-wildlife-collisions),
  [IDFG terms](https://idfg.idaho.gov/terms),
  [IDFG GIS data](https://idfg.idaho.gov/data/gis).

### ITD crash units with animal events

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35`,
  "Crash Unit 2005 to Present". Already in [SOURCES](../SOURCES.md) as
  "ITD crash points" (not started).
- **Contents:** a point layer, "2005 thru previous complete year", one
  record per unit. Fields checked: `Severity`, `Serial_Number`,
  `Mile_Point`, `Accident_Year`, `Latitude`, `Longitude`, `County`,
  `Number_Of_Fatalities`, `Number_Of_Injuries`, `Contrib_Circ_1`–`3`,
  `Most_Harmful_Event`, `Unit_Number`, `IntersectionRelated`, `Events`,
  `Vehicle_Type`, `Accident_Date_Time`, `fldFullSegmentCode`, `fldAscDesc`,
  `LatDD`, `LonDD`, `LOC_ERROR2`, `RouteID`, `Measure`.
  `Accident_Date_Time` gives the hour of day. The year layers end at 2023.
- **Coverage:** statewide, 2005–2023. `Most_Harmful_Event` "Animal - Wild"
  on 521 unit rows in Ada and 321 in Canyon; "Animal - Domestic" on 293
  and 372 (researcher; not re-run).
- **COMPASS through 2025:** the claim that COMPASS's
  `restricted.crash_unit.event` carries the same flag is unverified ⚠️:
  [migration 0012](../../db/migrations/0012_compass_data.sql) documents
  that column with collision-manner values ("Rear-End", "Angle Turning").
  One SQL query on the server would settle it.
- **Access:** query and statistics; `maxRecordCount` 70,000.
- **License and terms:** copyright text "ITD"; credit ITD, as for ITD's
  other open GIS.
- **robots.txt:** `gis.itd.idaho.gov/robots.txt` 404: no rules. Re-checked
  Oct 7.
- **Updates and size:** yearly (the layer stops at 2023). About 1.5k
  animal-unit rows in Ada and Canyon (researcher).
- **Use cases:** a crash-level "animal involved" flag, which isn't personal
  and can be published; police-reported animal crashes beside IDFG
  carcasses per segment, as a reporting-channel ratio; animal crashes by
  time of day against sunset and sunrise.
- **For:** traffic safety researchers, commuters and drivers. **Needs:**
  the safety plugin, the segment matcher.
- **Risks:** the person layers (12–23, 40, 44, 52, 53, 60, 67, 72, 73)
  hold person-level data: don't use them. Take only the event and
  vehicle-type flags into public tables, as the safety plugin already does.
- **Verification:** confirmed the layer, its fields, the years through
  2023, robots.txt and the "ITD" credit. Added: `Accident_Date_Time` gives
  time of day; `maxRecordCount` is 70,000. Not re-run: the animal-event
  counts.
- **Evidence:** [robots.txt](https://gis.itd.idaho.gov/robots.txt),
  [CrashLayers](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer?f=json),
  [layer 35](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35?f=json),
  [migration 0012](../../db/migrations/0012_compass_data.sql).

### SH-21 wildlife crossings

Use · verified: corrected · confidence high · effort S

- **Pages:** the [USFWS story](https://www.fws.gov/story/2024-03/idahos-new-wildlife-overpass-improves-public-safety-and-wildlife-migration)
  on the Cervidae Peak overpass (Mar 2024) and an
  [IDFG press release](https://idfg.idaho.gov/press/wildlife-public-safety-projects-highway-21)
  on the Robie Creek underpass (Jan 11, 2010).
- **Overpass (USFWS):** "approximately 150 ft wide", at "mile post 19.3"
  on SH-21, about 10 miles east of Boise. About $6.5M: a Federal Lands
  Access Program grant plus IDFG Wildlife Restoration matching funds.
  Expected to cut collisions by 80%. SH-21 averages 14,000 vehicles a day
  (from this 2024 story, not IDFG). IDFG monitors it with cameras.
- **Underpass (IDFG, 2010):** near Robie Creek, "scheduled" for summer
  2010, $550,000 of federal stimulus enhancement funds; the first
  underpass added to an existing Idaho highway. The release predates
  construction, so the completion date needs another source.
- **Collision figures (IDFG, 2010):** between Warm Springs Ave and Robie
  Creek, 75–100 mule deer and 5–10 elk collisions a year, at about $8,000
  per deer and $18,500 per elk collision; two "Give Deer and Elk a Brake"
  tally signs. "MP 10–21" for that stretch is our own mapping and needs
  checking against ITD's linear referencing.
- **Not checked:** the claim that the stretch is a Secretarial Order 3362
  priority area ⚠️.
- **Coverage:** SH-21 at the east edge of the box.
- **Access and license:** facts read from the pages and entered by hand as
  point features and events, with links. USFWS pages are federal works;
  IDFG's website terms forbid mirroring pages, so we store facts and links
  only.
- **robots.txt:** www.fws.gov disallows `/admin/`, `/search/`, `/search*`,
  `*page=`, `*f[`, user paths and README files; `/story/` is allowed.
  idfg.idaho.gov allows `/press/`. Re-checked Oct 7.
- **Updates and size:** static; a handful of features.
- **Use cases:** 3D models of the crossings on our terrain; before and
  after with IDFG carcasses on the Warm Springs–Robie Creek stretch;
  migration-season Valley Feed cards.
- **For:** commuters and drivers, traffic safety researchers, 3D map
  viewers, wildlife watchers. **Needs:** the 3D engine (models), the manual
  source kind, lifecycles.
- **Risks:** check milepost positions against ITD's LRS; the underpass
  milepost and completion date are unconfirmed.
- **Evidence:** the two pages above,
  [fws.gov robots.txt](https://www.fws.gov/robots.txt),
  [idfg.idaho.gov robots.txt](https://idfg.idaho.gov/robots.txt).

### 511 Idaho message signs and events

Use internally only · verified: confirmed · confidence high · effort S

- **What:** already recorded by the `idaho511` service: message signs in
  `evt.sign_message`, every 2 minutes. Of 21 valley signs, some show
  wildlife warnings ([ch. 8](../08-data-inventory.md)). Whether 511's
  events include animal-on-road reports is unverified.
- **Access, key and license:** already ingested with the project's free
  511 key. 511 data isn't republished; only WZDx may be
  ([DECISIONS](../DECISIONS.md), Oct 6). robots.txt doesn't apply: it's
  covered by the existing 511 API approval.
- **Use cases:** "wildlife warning signs lit right now" next to roadkill
  risk, for the owner only; text matching sign messages for DEER, ELK or
  WILDLIFE.
- **For:** commuters and drivers. **Needs:** the conditions plugin,
  lifecycles.
- **Risks:** internal only, so it can't appear in published tiles or in the
  public "Deer hour" and Valley Feed cards.
- **Evidence:** [DECISIONS](../DECISIONS.md) (Oct 6 rows on the 511 API
  and WZDx); [ch. 8](../08-data-inventory.md) (message-sign table).

## IDFG layers and requests

### IDFG open-data hub

Use · verified: corrected · confidence high · effort S

- **Endpoint:** [data-idfggis.opendata.arcgis.com](https://data-idfggis.opendata.arcgis.com/);
  discovery through its OGC Records API
  (`/api/search/v1/collections/dataset/items`).
- **Contents:** 37 items (Oct 7), including Controlled Hunts - All Species,
  Game Management Units, Areas With Hunting Restrictions, GMUs with
  Motorized Hunting Rules, Furbearer - Beaver Controlled Trapping Units,
  Access Agreements, Family Fishing Waters, Fishing and Boating Access
  Sites, Species Ranges (1:100,000), Sage-grouse Zones and Task Force
  areas, Idaho Birding Trail Routes and Sites, Mule Deer and White-tailed
  Deer Data Analysis Units, Elk Management Zones, Bighorn Sheep
  Distribution, Fish Hatcheries, Conservation Sites, the wetland and
  hydric-soil layers, Generalized Fish Distribution and Roadkill
  Observations. **No winter range or migration layer** (checked against the
  full list).
- **In the ring:** 5 Wildlife Management Areas (re-queried): Boise River
  40,520 acres, CJ Strike 11,363, Fort Boise 1,630, Montour 1,561, Payette
  River 1,260. Not re-checked: 7 hunting-restriction areas in the ring and
  over 750 Conservation Sites.
- **Two hosts:** most services are on
  `services.arcgis.com/FjJI5xHF2dUPVrgK/arcgis/rest/services/<name>/FeatureServer`,
  but Access Agreements, Family Fishing Waters, Fishing and Boating Access
  Sites and Roadkill are on `gisportal-idfg.idaho.gov/hosting/rest/services/...`.
  The reader must handle both, each with its own politeness budget.
- **License and terms:** per-item disclaimers in the hub's `licenseInfo`.
  Hunt layers: "Refer to the boundaries published in the current IDFG
  regulation booklets". Species Ranges, Elk Zones, Bighorn and Areas With
  Hunting Restrictions: "intended for public-use for informational purposes
  only". Conservation Sites, Hydric Soils and the Wetland Prioritization
  layers: IDFG "offers free, unrestricted access and use". Some are blank.
  Credit IDFG.
- **robots.txt:** the hub: `User-agent: *`, Crawl-delay 60, disallows
  `/sites/`, `/admin/`, `/sessions/`, `/groups/`, `/people/` and
  `/workspace/` (`/api/` allowed). `services.arcgis.com/robots.txt` 403
  "Invalid URL" (4xx, so no rules). `gisportal-idfg.idaho.gov` 404 (no
  rules). Re-checked Oct 7.
- **Updates and size:** mixed. Most items were modified 2025-10-03;
  Controlled Hunts 2026-09-18; Areas With Hunting Restrictions 2026-01-12;
  WMAs and GMUs mid-2026. A monthly check is enough. Tens of MB at most for
  the ring.
- **Use cases:** "who manages this wildlife land and what's allowed" cards;
  GMU and controlled-hunt boundaries for hunters; fishing access and family
  fishing waters; Idaho Birding Trail stops; no-hunting zones for hikers and
  cyclists.
- **For:** hunters and anglers, hikers, cyclists, birders, land explorers,
  campers. **Needs:** the shared ArcGIS reader, the layer system, places and
  search, areas.
- **Risks:** hunt boundaries carry a "check the regulations" warning: show
  it. WMAs may belong in the coming `lands` plugin.
- **Verification:** confirmed the 37 items, the 5 WMAs and their acreages,
  the absence of winter range or migration layers, the license phrases and
  robots.txt. Corrected: not every service is on services.arcgis.com (four
  are on IDFG's own server).
- **Evidence:** [IDFG GIS data](https://idfg.idaho.gov/data/gis),
  [hub robots.txt](https://data-idfggis.opendata.arcgis.com/robots.txt),
  [services.arcgis.com robots.txt](https://services.arcgis.com/robots.txt),
  [hub search](https://data-idfggis.opendata.arcgis.com/api/search/v1/collections/dataset/items?limit=100),
  a names-only WMA query on the ring at
  `services.arcgis.com/FjJI5xHF2dUPVrgK/arcgis/rest/services/WildlifeManagementAreas/FeatureServer/0/query`.

### IDFG GIS portal public services

Use · verified: corrected · confidence high · effort S

- **Endpoint:** [gisportal-idfg.idaho.gov/hosting/rest/services](https://gisportal-idfg.idaho.gov/hosting/rest/services)
  (folder listing checked Oct 7).
- **Contents by folder:**
  - Species: `Distribution_HEXGRID`, `Distribution`,
    `Monarch_Milkweed_Predicted_Distribution` (three layers, citing
    Svancara, Abatzoglou & Waterbury 2019) and `Taxonomy_Table` (may help
    the sensitivity table).
  - Wildlife: `CWD_Samples` (layer 0: positive and negative counts per GMU
    for moose, elk, mule deer and white-tailed deer),
    `Greater_Sage_grouse_Habitat` (BLM and IDFG), `Pheasant_Stocking`,
    `Wildlife_Conflicts_public` (avoid, below).
  - Access: `Wildlife_Habitat_Areas`, `Managed_Hunts`,
    `Large_Tracts_Access_Agreements`, fishing and boating sites.
  - SWAP: `SWAP_layers`, `Conservation_Targets`.
  - Root: a public `Hunting/MapServer` with 14 layers: All Hunt Areas, Elk
    Zones, Wolf Zones, Game Units, Controlled Hunts, Closed to Big Game /
    Upland / Upland Gamebird and Turkey / Waterfowl / Furbearer Hunting,
    Motorized Vehicle Hunting Rule, Wilderness and AccessYes! (layer 13).
- **Species hex grid:** layer 2, "Species Occurrence": `GRID_ID`,
  `TaxonID`, `Common_Name`, `Scientific_Name`, `count_all`,
  `count_trusted` and `sensitive`. One non-sensitive hex near Boise (DD-81)
  measured 0.135° × 0.117°, about 106 km². The grid is regular in degrees,
  so true area changes slightly with latitude. About 40k taxon-hex rows in
  the box (researcher's 37,429 and 2,360; not re-run).
- **Access:** ArcGIS REST, MapServer and FeatureServer; `maxRecordCount`
  2,000 on the hex layer and the Hunting service, 1,000 on
  Species/Distribution.
- **License and terms:** mostly unstated; copyright text credits "IDFG
  IFWIS" or the paper. The exception is the root Hunting MapServer, whose
  copyright text reads "CC-BY Idaho Fish and Game": the clearest license
  IDFG publishes. Credit IDFG; where no license is stated, the
  courtesy-note rule would apply (owner to confirm).
- **robots.txt:** 404, no rules (re-checked Oct 7).
- **Updates and size:** unknown; check monthly. A few MB.
- **Use cases:** "what lives here" species lists per hex that respect
  IDFG's sensitive flag; monarch and milkweed suitability for gardeners;
  pheasant release areas each fall; CWD status by hunt unit; hunting
  closures and Access Yes! lands.
- **For:** birders and naturalists, gardeners, hunters, farmers.
  **Needs:** the shared ArcGIS reader, the layer system, sensitivity rules
  (design notes).
- **Risks:** IDFG itself publishes `Common_Name` for `sensitive=1` rows;
  our rule (show only a count of sensitive taxa) is stricter, which is
  fine. AccessYes! (layer 13) carries staff user fields (`Aud_NUser`,
  `created_user`, `last_edited_user`): drop them. `Pheasant_Stocking`'s
  FeatureServer advertises Create, Update and Delete, so it may be publicly
  editable: version what we read, sanity-check changes, never write to it.
  The meaning of `count_trusted` is a question for IDFG.
- **Verification:** confirmed the services, the hex fields including
  `sensitive`, `maxRecordCount` 2,000, the CWD fields and the monarch
  citation. The hex size is now measured rather than inferred. Added: the
  public Hunting MapServer with its CC BY text, the sage-grouse habitat
  service and the taxonomy table.
- **Evidence:** [service root](https://gisportal-idfg.idaho.gov/hosting/rest/services?f=pjson),
  [Species](https://gisportal-idfg.idaho.gov/hosting/rest/services/Species?f=pjson),
  [Wildlife](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife?f=pjson),
  [hex grid](https://gisportal-idfg.idaho.gov/hosting/rest/services/Species/Distribution_HEXGRID/MapServer?f=pjson),
  [hex layer 2](https://gisportal-idfg.idaho.gov/hosting/rest/services/Species/Distribution_HEXGRID/MapServer/2?f=pjson)
  (plus one query for a non-sensitive hex, `outSR=4326`),
  [Distribution](https://gisportal-idfg.idaho.gov/hosting/rest/services/Species/Distribution/MapServer?f=pjson),
  [monarch](https://gisportal-idfg.idaho.gov/hosting/rest/services/Species/Monarch_Milkweed_Predicted_Distribution/MapServer?f=pjson),
  [pheasant stocking](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Pheasant_Stocking/FeatureServer?f=pjson),
  [CWD samples](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/CWD_Samples/MapServer/0?f=pjson),
  [Wildlife Habitat Areas](https://gisportal-idfg.idaho.gov/hosting/rest/services/Access/Wildlife_Habitat_Areas/MapServer?f=pjson),
  [Hunting](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hunting/MapServer?f=pjson),
  [Hunting layer 5](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hunting/MapServer/5?f=pjson),
  [Hunting layer 13](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hunting/MapServer/13?f=pjson),
  [sage-grouse habitat](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Greater_Sage_grouse_Habitat/MapServer?f=pjson).

### IDFG token-only layers

Needs owner action · verified: corrected · confidence high · effort M

- **What answers 499 "Token Required":**
  `Wildlife/Mule_Deer_Seasonal_Ranges/MapServer` (hidden from the public
  Wildlife listing); `Fisheries/Idaho_Fishing_Seasons_and_Rules` (listed
  publicly, but both its MapServer and FeatureServer answer 499); the
  AccessYes, Fire and Conservation folders.
- **Mule deer layer:** described elsewhere as preliminary winter and summer
  range models from GPS-collar data ⚠️ (secondary; couldn't be checked).
- **Correction:** there is no secured Hunting folder. The public root
  `Hunting/MapServer` carries the closure layers and AccessYes! (layer 13),
  so drop Access Yes! from any token request.
- **Access, key and license:** partnership (a token from IDFG); license
  unknown. robots.txt is 404 (no rules), but a token means they aren't
  open.
- **Updates and size:** unknown.
- **Use cases:** winter range for "drive carefully here in winter" zones
  and garden deer-browse risk (only if IDFG shares it, and generalized);
  fishing rules per water.
- **For:** commuters and drivers, gardeners, anglers, hikers. **Needs:**
  the shared ArcGIS reader.
- **Risks:** fine-scale winter range invites harassment of wintering
  animals; show only generalized zones and closures, if at all.
- **A public partial substitute:** IDFG's
  [highway–wildlife collisions page](https://idfg.idaho.gov/wildlife/highway-wildlife-collisions)
  links "wildlife linkage" reports (PDFs) for ITD Districts 3, 4 and 5,
  readable by hand.
- **Evidence:** [mule deer ranges](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Mule_Deer_Seasonal_Ranges/MapServer?f=pjson),
  [Fisheries folder](https://gisportal-idfg.idaho.gov/hosting/rest/services/Fisheries?f=pjson),
  [fishing rules MapServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Fisheries/Idaho_Fishing_Seasons_and_Rules/MapServer?f=pjson)
  and [FeatureServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Fisheries/Idaho_Fishing_Seasons_and_Rules/FeatureServer?f=pjson),
  [AccessYes](https://gisportal-idfg.idaho.gov/hosting/rest/services/AccessYes?f=pjson),
  [Fire](https://gisportal-idfg.idaho.gov/hosting/rest/services/Fire?f=pjson),
  [Conservation](https://gisportal-idfg.idaho.gov/hosting/rest/services/Conservation?f=pjson),
  [Hunting layer 13](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hunting/MapServer/13?f=pjson).

### IDFG website apps: stocking, Fishing Planner, Hunt Planner

Needs owner action · verified: confirmed · confidence high · effort M

- **What:** the [stocking page](https://idfg.idaho.gov/fish/stocking)
  offers "over 100,000 fish stocking events statewide since 1967" through
  the Fishing Planner, plus weekly schedules for seven regions (Southwest
  included). Also the Hunt Planner, the Access Yes! guide, the Species
  Catalog, and roadkill and observation reporting.
- **Access:** website only; no export or API documented.
- **Terms:** IDFG's [terms](https://idfg.idaho.gov/terms) (updated May 16,
  2025) grant viewing "for personal, non-commercial transitory viewing
  only", and forbid modifying or copying, any "public display", and
  mirroring "on any other server". They cover idfg.idaho.gov,
  gooutdoorsidaho.com, gofishidaho.org and gohuntidaho.org.
- **robots.txt:** idfg.idaho.gov (Drupal defaults): `User-agent: *`
  disallows `/admin/`, `/comment/reply/`, `/filter/tips`, `/node/add/`,
  `/search/`, `/user/register`, `/user/password`, `/user/login`,
  `/user/logout`, `/media/oembed`, `/web.config` and the README files.
  `/ifwis/`, `/species/`, `/fish/`, `/wma/`, `/press/` and `/article/` are
  not disallowed. Re-checked Oct 7.
- **Updates and size:** weekly in season; about 100k stocking rows
  statewide, if IDFG grants permission.
- **Use cases:** stocking events as a "fish just stocked here" lifecycle,
  only with IDFG's permission; hunting season dates checked by hand
  (facts) for a "season open here" layer.
- **For:** anglers, hunters, families outdoors. **Needs:** lifecycles
  (`evt.event`), the manual source kind.
- **Risks:** the terms forbid mirroring or displaying the content: ask IDFG
  before storing stocking records. Dates entered by hand must link to the
  official regulations.
- **Verification:** the terms quotes, date and scope, the 100,000-events
  statement and robots.txt are confirmed. The `/ifwis/fishingplanner/stocking`
  page itself wasn't re-fetched.
- **Evidence:** [stocking](https://idfg.idaho.gov/fish/stocking),
  [terms](https://idfg.idaho.gov/terms),
  [robots.txt](https://idfg.idaho.gov/robots.txt).

### IDFG data requests (Species Diversity Database)

Needs owner action · verified: corrected · confidence high · effort M

- **What:** "Site-specific information on observed locations of species
  with special conservation status", from the Idaho Species Diversity
  Database (Natural Heritage Program). The relevant Technical Assistance
  Manager decides how to fulfil each request.
- **Access:** a [request form](https://idfg.idaho.gov/data/request);
  usually 1 to 3 weeks.
- **Fees and terms:** free for individual, bibliographic and openly
  available data; $200 for small projects (under 50% of a county's area);
  $500 for large ones (over 50%). Citation guidance is given; no sharing
  terms are stated, so use is discretionary per request. robots.txt
  doesn't apply (a human request).
- **Use cases:** only if a specific research question needs exact
  rare-species locations; they would live in a private plugin and never be
  shown.
- **For:** researchers. **Needs:** private plugins, a restricted schema.
- **Risks:** sensitive locations: private and aggregate-only. The public
  hex grid probably covers our needs, so not recommended now.
- **Verification:** confirmed the contents, turnaround and the Technical
  Assistance Manager. Corrected: the fee tiers depend on the share of a
  county's area (not "multi-county"), and openly available data is free.

### IDFG Wildlife_Conflicts_public (avoid)

Avoid · verified: corrected · confidence high

- **What:** `gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Wildlife_Conflicts_public/FeatureServer/0`,
  layer "ConflictReport", with response point, line and polygon layers
  alongside. Its schema has reporter and landowner contact fields (name,
  email, phone, address), plus parcel, city, ZIP code, status and assignee.
- **Access:** FeatureServer/0 offers Create, Uploads, Editing and
  ChangeTracking, with no Query; the MapServer lists no capabilities and
  `maxRecordCount` 0. That's the usual setup for a public report form, so
  records are probably not readable. No records were requested, by design.
- **License:** none stated (copyright text "Idaho Department of Fish and
  Game"). robots.txt 404, which doesn't matter: this must not be collected.
- **Rule:** never query it or write to it, and never probe it to find out
  what's readable.
- **Verification:** the schema is confirmed. The research's implied
  exposure was overstated: it's a write-only intake.
- **Evidence:** [Wildlife folder](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife?f=pjson),
  [FeatureServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Wildlife_Conflicts_public/FeatureServer?f=pjson),
  [layer 0](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Wildlife_Conflicts_public/FeatureServer/0?f=pjson),
  [MapServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Wildlife/Wildlife_Conflicts_public/MapServer?f=pjson)
  (service descriptions only).

## Habitat, lands and seasonal rules

### USFWS critical habitat

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/USFWS_Critical_Habitat/FeatureServer`:
  layer 0 "Final Critical Habitat Features", layer 2 "Proposed Critical
  Habitat Features". Tile services for both on tiles.arcgis.com.
- **Fields:** `comname`, `sciname`, `spcode`, `unit`, `subunit`,
  `unitname`, `status`, `leadoffice`, `fedreg`, `pubdate`, `effectdate`,
  `vacatedate`, `accuracy`, `listing_status`.
- **Locally:** slickspot peppergrass. The final rule (published
  2023-05-04, effective 2023-06-05) covers about 31,569 ha (78,009 acres)
  in Ada, Elmore, Gem, Payette and Owyhee counties, per the Federal
  Register API; units lie in south Ada (box) and the ring. Not checked:
  that the units are on federal land only, bull trout units in the ring,
  and the absence of proposed units in the ring. One spatial query will
  settle them when the ingestor is built.
- **Access:** capabilities Query, Extract and Sync; `maxRecordCount` 1,000.
- **License:** federal, public domain; copyright text "U.S. Fish and
  Wildlife Service".
- **robots.txt:** services.arcgis.com 403 "Invalid URL" (no rules);
  tiles.arcgis.com 404; ecos.fws.gov 404. Re-checked Oct 7.
  www.federalregister.gov's document page redirects bots to an "unblock"
  page, so we used its JSON API (robots.txt allows `/api/`).
- **Updates and size:** when rules change (rare); a few MB.
- **Use cases:** where fires and development meet ESA habitat (hazards and
  development plugins); land cards ("ESA critical habitat: slickspot
  peppergrass").
- **For:** land explorers, fire and hazards watchers, hikers, gardeners
  (native plants). **Needs:** the shared ArcGIS reader, the layer system.
- **Risks:** critical habitat is published at unit scale, so it's fine to
  show; never add point occurrences of the plant, including herbarium
  records from GBIF.
- **Evidence:** [FeatureServer](https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/USFWS_Critical_Habitat/FeatureServer?f=json),
  [layer 0](https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/USFWS_Critical_Habitat/FeatureServer/0?f=json),
  [Federal Register 2023-09219](https://www.federalregister.gov/api/v1/documents/2023-09219.json),
  [Federal Register robots.txt](https://www.federalregister.gov/robots.txt),
  [ECOS services](https://ecos.fws.gov/ecp/services),
  [ECOS robots.txt](https://ecos.fws.gov/robots.txt).

### USFWS ECOS species reports and IPaC

Use · verified: corrected · confidence medium · effort S

- **What:** species listing status, taxonomy and Federal Register history
  from ECOS pull reports (HTML, XML, JSON or CSV). The IPaC Location API
  1.1.1 (`POST /resources`) returns ESA species, migratory birds of concern
  and other resources for an area.
- **Endpoints:** the [services page](https://ecos.fws.gov/ecp/services)
  points pull reports at `ecp.ecosphere.fws.gov/report/adhocCreator?...`,
  but that host didn't resolve; the same path on ecos.fws.gov answered 200
  ([example](https://ecos.fws.gov/ecp/report/adhocCreator?catalogId=species&reportId=species)).
  IPaC: [ipac.ecosphere.fws.gov/location/api](https://ipac.ecosphere.fws.gov/location/api)
  (OpenAPI docs).
- **Key:** none today, but IPaC's docs warn it "WILL EVENTUALLY REQUIRE AN
  API KEY" (probably a free-key owner action later).
- **License:** federal, public domain (no terms stated on the services
  page).
- **robots.txt:** ecos.fws.gov 404 (no rules); ipac.ecosphere.fws.gov 404
  (no rules); ecp.ecosphere.fws.gov doesn't resolve, so treat it as
  disallowed for now. Checked Oct 7.
- **Updates and size:** as listings change; tiny.
- **Use cases:** federal status on species cards; "listed species and
  birds of concern that may occur in this area" for any drawn area.
- **For:** land explorers, birders, researchers. **Needs:** places and
  search, areas.
- **Risks:** IPaC lists possible presence, not observations: label it so.
  Call it per user-drawn area, on demand and cached. Response formats
  weren't tested.
- **Evidence:** [services page](https://ecos.fws.gov/ecp/services),
  [ECOS robots.txt](https://ecos.fws.gov/robots.txt),
  [IPaC robots.txt](https://ipac.ecosphere.fws.gov/robots.txt),
  [IPaC API](https://ipac.ecosphere.fws.gov/location/api),
  [pull report](https://ecos.fws.gov/ecp/report/adhocCreator?catalogId=species&reportId=species).

### USFWS refuge boundaries (Deer Flat NWR)

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer`,
  layer 0 "FWSBoundaries"; also a zip on ServCat (iris.fws.gov).
- **What:** the external boundary of lands and waters USFWS administers
  (refuges, hatcheries, administrative sites, other conservation areas),
  simplified, with interior parcels dissolved; inholdings inside an
  outline may not be USFWS land. data.gov title "FWS National Realty
  Boundaries", metadata updated Aug 10, 2026. Deer Flat (Lake Lowell and
  the Snake River Islands) lies in the box and the ring.
- **Access:** Query, Extract, Sync; `maxRecordCount` 2,000.
- **License:** federal; data.gov lists no license. Use constraint: "not
  all areas are open to the public."
- **robots.txt:** services.arcgis.com 403 "Invalid URL" (no rules);
  catalog.data.gov `User-agent: *` with Crawl-Delay 10. Checked Oct 7.
- **Updates and size:** a few times a year; small.
- **Use cases:** refuge outlines with the seasonal rules below; probably
  shared with the coming `lands` plugin.
- **For:** land explorers, birders, boaters and anglers, cyclists.
  **Needs:** the layer system; the `lands` plugin is the likely owner.
- **Risks:** decide which plugin owns it; don't present the outline as
  "all public land".
- **Evidence:** [data.gov](https://catalog.data.gov/dataset/fws-national-realty-boundaries),
  [data.gov robots.txt](https://catalog.data.gov/robots.txt),
  [FeatureServer](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer?f=json).

### Deer Flat NWR rules and seasonal closures

Use · verified: confirmed · confidence high · effort S

- **Page:** [Deer Flat rules and policies](https://www.fws.gov/refuge/deer-flat/visit-us/rules-policies).
- **Rules (all match the page):**

  | Rule | When |
  |---|---|
  | Lake Lowell boating, daylight only | Apr 15–Sep 30 |
  | Human-powered boats and float tubes only, within 200 yards in front of the Upper and Lower Dams | Oct 1–Apr 14 |
  | All Snake River Islands closed | Feb 1–Jun 14 |
  | A few heron and gull nesting islands closed | Through Jun 30 |
  | Off-trail hiking, Gotts Point | Feb 1–Sep 30 |
  | Off-trail hiking, Murphy's Neck | Mar 15–Sep 30 |
  | Off-trail hiking, North Side Recreation Area | Aug 1–Jan 31 |
  | Swimming | Apr 15–Sep 30 |
  | Groups of more than ten cyclists need a Special Use Permit | Always |
  | Dogs on a leash of 6 ft or less; no drones | Always |

- **Access and license:** facts read by hand, entered as recurring
  lifecycle events with a link; a federal work (public domain). robots.txt:
  www.fws.gov allows `/refuge/` (re-checked Oct 7).
- **Updates and size:** seasonal; re-check yearly. About 10 rules.
- **Use cases:** "what's open at Lake Lowell today" for boaters, cyclists,
  hikers and birders; nesting-season island closures in the Valley Feed.
- **For:** hikers, cyclists, boaters and anglers, birders, campers.
  **Needs:** lifecycles with yearly recurrence, the manual source kind, the
  Valley Feed.
- **Risks:** rules change, so re-check each season and show a "last
  checked" date. The North Side window crosses New Year, so the recurrence
  model must handle wrap-around.
- **Evidence:** the page above, [fws.gov robots.txt](https://www.fws.gov/robots.txt).

### Birds of Prey NCA shooting map

Use · verified: confirmed · confidence high · effort S

- **Source:** BLM's [safe shooting map](https://www.blm.gov/documents/idaho/public-room/map/morley-nelson-snake-river-birds-prey-safe-shooting-map)
  for the Morley Nelson Snake River Birds of Prey National Conservation
  Area ([PDF](https://www.blm.gov/sites/default/files/documents/files/Media-Center_Public-Room_Idaho_MorleyNelson-SafeShootingMap.pdf),
  dated June 2, 2017; text read).
- **Rules:**
  - Snake River Plateau: open to shotguns and muzzleloaders; closed to
    rifles and pistols year-round.
  - Snake River Canyon: closed year-round to rifles and pistols, and to
    all firearms Feb 15–Aug 31. The closed area is one-half mile each side
    of the river from Grand View down to the old Guffey Bridge.
  - Exception: rifle hunting in Unit 40 during the established deer
    season.
  - About 10% of the NCA is a Safety Zone; about 450,000 acres remain open
    for safe shooting.
- **Boundary:** from BLM's National Conservation Lands data or PAD-US
  (lands plugin).
- **Coverage:** south of Kuna and Melba to Grand View (box and ring).
- **License:** federal (public domain).
- **robots.txt:** www.blm.gov (Drupal defaults) disallows `/admin/`,
  `/search/`, `/search?`, user paths, `/media/oembed` and the README files;
  `/documents/` and `/sites/default/files/` are allowed.
  gbp-blm-egis.hub.arcgis.com: Crawl-delay 60, disallows `/sites/`,
  `/admin/`, `/sessions/`, `/groups/`, `/people/` and `/workspace/`.
  gis.blm.gov: 404. Re-checked Oct 7.
- **Updates and size:** rare; a few polygons.
- **Use cases:** the raptor-nesting firearm closure as a yearly lifecycle;
  canyon and plateau shooting zones for hikers, cyclists and hunters.
- **For:** hikers, cyclists, hunters, birders, land explorers. **Needs:**
  lifecycles with recurrence, the manual source kind, the lands plugin
  (boundary).
- **Risks:** the map is from 2017; confirm with BLM that it's current. The
  half-mile canyon zone has to be drawn from the river centerline, as an
  approximation labelled as such. Never map raptor nest sites.
- **Evidence:** the page and PDF above,
  [blm.gov robots.txt](https://www.blm.gov/robots.txt),
  [BLM hub robots.txt](https://gbp-blm-egis.hub.arcgis.com/robots.txt),
  [gis.blm.gov robots.txt](https://gis.blm.gov/robots.txt).

### Boise River WMA rules and closures

Use · verified: confirmed · confidence high · effort S

- **Pages:** IDFG's [WMA page](https://idfg.idaho.gov/wma/boise-river) and
  the [Jan 13, 2026 release](https://idfg.idaho.gov/article/fish-and-game-will-restrict-access-boise-river-wma-second-winter).
- **Facts:**
  - 41,500 acres in Ada, Boise and Elmore counties (IDFG's GIS says
    40,520).
  - Part of the newly acquired Cornell Segment is closed to public access
    Feb 1–Apr 14. Which part isn't published as GIS; "north of Mayfield
    Road" didn't appear in what was read.
  - Dogs on leash Nov 16–Apr 30.
  - Boise Front segment roads open May 1–Nov 15 (about 10 mi); Charcoal
    segment roads Sep 1–Dec 31 (about 7 mi).
  - The Charcoal Segment closes for about three days in the week of Sep 21
    for aerial herbicide spraying (no year given; presumably 2026).
  - 5,000–8,000 mule deer and 1,800 elk winter on the WMA.
  - The 2024 Valley Fire burn area west of SH-21 is closed Feb 1–Apr 14,
    2026, the second winter in a row, for about 2,400 mule deer and 650 elk
    (Jan 13, 2026 release).
- **Access and license:** facts entered by hand with links; no
  machine-readable feed. IDFG's website terms forbid mirroring pages, so we
  store dates and links, not page text.
- **robots.txt:** idfg.idaho.gov allows `/wma/`, `/press/` and `/article/`
  (re-checked Oct 7).
- **Updates and size:** seasonal; about 10 rules a year.
- **Use cases:** "closed for wildlife today" on the Boise Front; post-fire
  closures linked to the hazards plugin's fire perimeters; dog-leash season
  alerts for hikers.
- **For:** hikers, cyclists, dog walkers, hunters, fire and hazards
  watchers. **Needs:** lifecycles with recurrence, the manual source kind,
  the Valley Feed, the hazards plugin (fire link).
- **Risks:** temporary closures change every year, so this needs a
  seasonal review step. Draw the Cornell closure by hand and label it
  approximate. The leash season crosses New Year.
- **Evidence:** the pages above, [robots.txt](https://idfg.idaho.gov/robots.txt).

### USGS ungulate migrations (Volumes 1–6)

Use, for regional context · verified: corrected · confidence high · effort S

- **Source:** [Ungulate Migrations of the Western United States](https://www.sciencebase.gov/catalog/item/6729962bd34e338a476a38ef),
  by USGS's Corridor Mapping Team with state agencies.
- **Idaho items:** only in Volume 5 (published 2025-02-06; 66 child items;
  one 135.8 MB zip): six Idaho–Nevada elk items, routes and stopovers for
  the Bruneau-Diamond A Desert, Inside Desert and Y P Desert herds. Y P
  Desert routes come from 59 migration sequences of 15 animals, 2014–2020;
  Bruneau-Diamond A runs 2015–2022. Y P Desert reaches 42.61°N and
  Bruneau-Diamond A 42.83°N, both south of the ring's 42.90°N. Volume 6
  (2026-03-24, 30 items) has no item titled Idaho. **Nothing for Ada or
  Canyon.**
- **Herd sizes on SH-21:** the research's 8,000–9,000 deer and 1,800–2,400
  elk are unsourced. Use IDFG's figures: 5,000–8,000 mule deer and 1,800
  elk winter on the Boise River WMA.
- **Access:** ScienceBase JSON API (`catalog/item`,
  `catalog/items?parentId`). Each herd item has shapefile parts in its
  `facets`, a "Download Attached Files" zip, and ScienceBase WMS, WFS and
  KML services; the child items' plain `files` list shows only
  `desktop.ini`.
- **License:** Volume 5's rights field: "This work is marked with Creative
  Commons Zero v1.0 Universal". Child items leave it empty, so the parent's
  CC0 applies.
- **robots.txt:** www.sciencebase.gov: `User-agent: *`, `Allow: /`, with
  a Content-Signal of search=yes, ai-train=no, use=reference; named AI or
  training crawlers are disallowed. Re-checked Oct 7.
- **Updates and size:** about yearly (Volume 6 came out Mar 2026); a few
  MB for the Idaho items.
- **Use cases:** regional context only, Owyhee elk migrations on a
  zoomed-out map; a template for showing a future Idaho mule deer release.
- **For:** wildlife watchers, hunters, land explorers. **Needs:** the
  layer system, areas (the layer reaches beyond the ring).
- **Risks:** low local value. Don't imply corridors exist only where
  they're mapped.
- **Verification:** confirmed CC0, Idaho in Volume 5 only, all south of
  the ring, and the 136 MB zip. Corrected: the Y P Desert sample (not 35
  elk, 2015–2022) and the per-herd download route.
- **Evidence:** [robots.txt](https://www.sciencebase.gov/robots.txt),
  [Volume 5](https://www.sciencebase.gov/catalog/item/6729962bd34e338a476a38ef?format=json),
  child listings ([series](https://www.sciencebase.gov/catalog/items?parentId=66dee5dcd34eef5af66da144&format=json),
  [Volume 5](https://www.sciencebase.gov/catalog/items?parentId=6729962bd34e338a476a38ef&format=json),
  [Volume 6](https://www.sciencebase.gov/catalog/items?parentId=68dbf660d4be0204610b5ed7&format=json)),
  herd items [6791758e…](https://www.sciencebase.gov/catalog/item/6791758ed34ea6a4002bfab0?format=json)
  and [6791756b…](https://www.sciencebase.gov/catalog/item/6791756bd34ea6a4002bfaa7?format=json),
  [IDFG Boise River WMA](https://idfg.idaho.gov/wma/boise-river).

## Observations and tracks

### GBIF occurrence API

Use · verified: corrected · confidence high · effort M

- **Endpoint:** [api.gbif.org/v1/occurrence/search](https://api.gbif.org/v1/occurrence/search).
- **In the box (re-run Oct 7):** 2,872,794 occurrences. By dataset: eBird
  Observation Dataset (EOD) 2,660,301; iNaturalist Research-grade 102,174;
  VectorBase 46,524; Great Backyard Bird Count 10,942; USGS Nonindigenous
  Aquatic Species 6,764; Snake River Plain Herbarium 4,980; College of
  Idaho Herbarium 4,580; Birda 3,104. By license: CC BY 4.0 2,676,546;
  CC BY-NC 4.0 149,774; CC0 46,474. Yearly counts not re-run.
- **Fields:** species, `eventDate`, coordinates,
  `coordinateUncertaintyInMeters`, `informationWithheld`, a per-record
  license, and `recordedBy` (personal names or usernames).
- **Access:** REST JSON with geometry (WKT), date, taxon, dataset and
  license filters, and facets. The paging cap is exact: offset + limit may
  not exceed 100,000 (the API answered "Max offset of 100001 exceeded").
  Larger pulls need the download API (an account) or the AWS snapshot.
  Faceted counts (`limit=0`, `facet=speciesKey`) give aggregates without
  fetching points; see the design notes.
- **Licenses:** per record, CC0, CC BY 4.0 or CC BY-NC 4.0. EOD
  (`4fa7b334…`) is CC BY 4.0. iNaturalist Research-grade (`50c9509d…`) is
  CC BY-NC 4.0 overall and includes only CC0, CC BY and CC BY-NC
  observations. GBIF's data-user terms and citation pages return 403 to
  us, so its guidance on derived-dataset DOIs stays ⚠️.
- **robots.txt:** api.gbif.org: `User-agent: *` disallows only
  `/v1/image/unsafe`. www.gbif.org returns 403 (Cloudflare) to our clients:
  4xx, so no rules, but we can't read its terms there.
  Re-checked Oct 7.
- **Obscured records:** iNaturalist obscures to a 0.2° × 0.2° cell and sets
  the uncertainty to the cell's diagonal, about 27.4 km at 43.5°N (27,474 m
  seen). About 4,180 obscured records in the box (not re-counted).
- **Updates and size:** EOD yearly, last published 2025-08-08, so over a
  year old; iNaturalist weekly (published 2026-09-29); others vary. About
  3–4 million rows for the ring ⚠️ (estimate): 1–2 GB as raw points, or
  tens of MB as species × cell × month counts.
- **Use cases:** species-by-cell-by-month counts ("what's here this
  week"); bird seasonality from eBird's CC BY copy; native plant records
  (herbaria) for gardeners, after the sensitivity filter; invasive aquatic
  species in canals and reservoirs.
- **For:** birders and naturalists, gardeners, farmers, hikers, sky
  watchers. **Needs:** areas, a display for point events in time, places
  and search (species names), licensing and visibility (per-record
  license), sensitivity rules.
- **Risks:** drop `recordedBy` and `identifiedBy` at ingest. Never plot
  obscured records as points or put them in cells smaller than their
  obscuring cell. Republished BY-NC material keeps NC and attribution.
  Herbarium records can include rare plants at exact localities (for
  example slickspot peppergrass): filter them before any display. Whether
  eBird's sensitive species are excluded from EOD is ⚠️ (the dataset
  description doesn't say).
- **Verification:** the counts and the dataset and license facets match
  exactly. Corrected: the paging cap is exactly 100,000 (not "100–200k");
  EOD's age.
- **Evidence:** [robots.txt](https://api.gbif.org/robots.txt),
  the box query
  `https://api.gbif.org/v1/occurrence/search?geometry=POLYGON((-117.05 43.00,-115.95 43.00,-115.95 43.85,-117.05 43.85,-117.05 43.00))&limit=0&facet=datasetKey&facet=license`,
  the paging-cap probe
  `https://api.gbif.org/v1/occurrence/search?offset=100001&limit=1&datasetKey=4fa7b334-ce0d-4e88-aaae-2e0c138d049e&year=1800`,
  [EOD dataset](https://api.gbif.org/v1/dataset/4fa7b334-ce0d-4e88-aaae-2e0c138d049e),
  [iNaturalist dataset](https://api.gbif.org/v1/dataset/50c9509d-22c7-4a22-a47d-8c48425ef4a7),
  `https://www.gbif.org/terms/data-user` (403),
  [iNaturalist geoprivacy help](https://help.inaturalist.org/support/solutions/articles/151000169938).

### GBIF monthly snapshot on AWS

Use · verified: corrected · confidence medium · effort M

- **What:** the full GBIF occurrence table as Parquet, one snapshot a
  month, about 180 GB each. Per GBIF's README it includes "all CC0, CC-BY
  and CC-BY-NC licensed data" with a license column. Columns are mostly
  lower-case Darwin Core names (`recordedBy` included, as an array). Each
  snapshot carries a `citation.txt`; the registry asks for the snapshot's
  DOI in citations.
- **Path:** `s3://gbif-open-data-<region>/occurrence/YYYY-MM-DD/occurrence.parquet/*`,
  in buckets `gbif-open-data-us-east-1`, `-eu-central-1`, `-sa-east-1`,
  `-af-south-1` and `-ap-southeast-2`; unsigned access
  (`--no-sign-request`), no key.
- **License:** the registry lists "CC-BY-NC" under GBIF's terms (the most
  restrictive license present); per-record licenses are kept.
- **robots.txt:** not applicable (S3). registry.opendata.aws/robots.txt
  returns 404; the registry page was read by hand.
- **Size:** the snapshot isn't partitioned by space, so even reading only
  the coordinate and filter columns pulls several GB across the internet to
  the server per bootstrap ⚠️ (estimate). Output as for the API.
- **Use cases:** a one-time bootstrap of ring occurrences without paging
  the API; yearly rebuilds of aggregates.
- **For:** birders and naturalists, researchers. **Needs:** the ingest
  framework with a Parquet reader (a new dependency), the archive.
- **Risks:** pyarrow or duckdb would break the standard-library ingest
  rule (owner decision). Bandwidth and disk space on the server during a
  scan. Drop `recordedBy`.
- **Verification:** confirmed the monthly snapshots, buckets, unsigned
  access and license listing. Corrected: a "filtered scan" isn't cheap
  (above). The faceted-count route (design notes) is a keyless,
  dependency-free alternative for the bootstrap.
- **Evidence:** [registry](https://registry.opendata.aws/gbif/),
  [GBIF's README](https://github.com/gbif/occurrence/blob/master/aws-public-data.md).

### NatureServe Explorer API

Use · verified: corrected · confidence high · effort S

- **What:** global and state conservation ranks (G and S), taxonomy,
  distribution by state and county, and data-sensitivity categories
  ("Proprietary Data", "Poaching/Collection Threat", "Land Owner
  Restrictions") for US and Canadian species.
- **Access:** REST JSON (`/api/data/taxon/{uid}`, species, ecosystem and
  combined search); the [API docs](https://explorer.natureserve.org/api-docs/)
  mention no key.
- **License:** NatureServe's data-use page: NatureServe Explorer data are
  CC BY 4.0; Explorer Pro and Open Data Portal public-level data are CC
  BY-NC 4.0. The API docs make use subject to the Explorer Terms of Use and
  require citing NatureServe Explorer. The terms page itself wasn't found
  at the guessed URLs (404).
- **robots.txt:** explorer.natureserve.org: `User-agent: *`, empty
  `Disallow:`, `Allow: /`. www.natureserve.org: Drupal defaults.
  Re-checked Oct 7.
- **Updates and size:** occasional; tiny (only species we show).
- **Use cases:** Idaho S-rank on species cards; part of the sensitivity
  rules.
- **For:** birders and naturalists, gardeners. **Needs:** places and
  search (species).
- **Risks:** use the API (CC BY), not Explorer Pro (BY-NC), for anything
  republished. Honor the sensitivity categories in our sensitivity table.
- **Verification:** the license is now confirmed on NatureServe's own page
  (⚠️ removed; confidence raised to high); no key, per the docs.
- **Evidence:** [robots.txt](https://explorer.natureserve.org/robots.txt),
  [API docs](https://explorer.natureserve.org/api-docs/),
  [data-use page](https://www.natureserve.org/node/1635),
  [natureserve.org robots.txt](https://www.natureserve.org/robots.txt).

### North American Breeding Bird Survey

Use · verified: corrected · confidence medium · effort S

- **What:** roadside point counts every June for more than 700 taxa. The
  current release is the "2026 Release - North American Breeding Bird
  Survey Dataset (1966 - 2025)", published 2026-05-28
  ([ScienceBase](https://www.sciencebase.gov/catalog/item/6a0b0b0ab66b0188da36aedd)).
  The research cited the 2025 release (`691cfb53…`, 1966–2024), which is
  now filed under Historic Data Releases as superseded.
- **Files** (2025 release; the 2026 one likely matches ⚠️): `Routes.csv`
  (0.4 MB), `Weather.csv` (14 MB), `States.zip` (63 MB),
  `50-StopData.zip` (65 MB), `VehicleData.csv` (61 MB), `SpeciesList.csv`,
  `MigrantNonBreeder.zip`.
- **Coverage:** US and Canada routes; how many lie in the ring is
  unverified.
- **License:** CC0 1.0 (the 2025 release's ScienceBase rights field). The
  2026 item's rights and files weren't opened, only its listing.
- **robots.txt:** www.sciencebase.gov `User-agent: *`, `Allow: /`
  (re-checked Oct 7).
- **Updates and size:** yearly (late spring); small for Idaho once
  extracted, but getting Idaho means fetching the 63 MB `States.zip`.
- **Use cases:** long-term breeding-bird trends on routes near the valley.
- **For:** birders, researchers. **Needs:** readings.
- **Risks:** route stop locations are coarse, which is fine. Low priority.
- **Evidence:** [2025 release](https://www.sciencebase.gov/catalog/item/691cfb53d4be021d1d89b482?format=json),
  [BBS parent](https://www.sciencebase.gov/catalog/item/5af45ecee4b0da30c1b448db?format=json),
  [release listing](https://www.sciencebase.gov/catalog/items?parentId=52b1dfa8e4b0d9b325230cd9&format=json),
  [robots.txt](https://www.sciencebase.gov/robots.txt).

### eBird direct (avoid)

Avoid · verified: confirmed · confidence high

- **What:** recent observations, hotspots and checklists (API 2.0); the
  full raw dataset with effort (eBird Basic Dataset, on request); modelled
  abundance rasters (Status & Trends). Sensitive species are blurred or
  hidden ⚠️ (secondary).
- **Access:** the API needs a key tied to an eBird account ⚠️; the EBD a
  request form ⚠️; Status & Trends an access key ⚠️.
- **Terms:** not readable by us: www.birds.cornell.edu and
  confluence.cornell.edu both return 403. The research's summary
  (non-commercial, revocable, no passing data to third parties, no EBD
  redistribution) stays ⚠️ secondary.
- **robots.txt (settles it):** api.ebird.org `User-agent: *`
  `Disallow: /`. ebird.org and science.ebird.org: long named-bot lists,
  then `User-agent: *` `Disallow: /`. Re-checked Oct 7.
- **Instead:** use eBird's CC BY copy on GBIF; link out to eBird hotspot
  pages. Only the owner could ask Cornell for an exception.
- **Evidence:** [api.ebird.org robots.txt](https://api.ebird.org/robots.txt),
  [ebird.org robots.txt](https://ebird.org/robots.txt),
  [science.ebird.org robots.txt](https://science.ebird.org/robots.txt),
  [API terms](https://www.birds.cornell.edu/home/ebird-api-terms-of-use/)
  (403), [Confluence terms](https://confluence.cornell.edu/display/CLOISAPI/eBird+API+Terms+of+Use)
  (403).

### iNaturalist API and open-data bucket

Avoid the API · verified: confirmed · confidence high · effort S (photos)

- **What:** observations, taxa and places through the
  [API](https://api.inaturalist.org/v1/docs). The S3 bucket
  `inaturalist-open-data` (us-east-1) holds CC-licensed or CC0 images,
  "posted in real time", with metadata refreshed monthly (observations,
  photos, taxa and observers tables; the observers table likely holds
  logins and names ⚠️).
- **Access:** API rate guidance of about 60 requests a minute and 10k a
  day ⚠️ (secondary). The bucket allows `--no-sign-request` (confirmed on
  the registry).
- **License:** per observation and per photo: CC0, CC BY, CC BY-NC or all
  rights reserved (the bucket holds only CC or CC0 images). Obscured
  locations use a 0.2° × 0.2° cell with a random point inside it.
- **robots.txt:** api.inaturalist.org: `User-agent: *` allows
  `/favicon.ico`, `/v1/docs` and `/v2/docs`, then `Disallow: /*?` and
  `Disallow: /`. www.inaturalist.org disallows `/observations/*`,
  `/photos` and many `/taxa/` and `/places/` paths. The bucket has no
  robots.txt. Re-checked Oct 7.
- **Use:** not the API; research-grade iNaturalist data comes through GBIF.
  Optional and separate: CC0 or CC BY photos from the bucket for species
  cards, crediting each photographer.
- **For:** birders and naturalists, gardeners.
- **Risks:** if bucket metadata is used, load the observers table only as
  far as photo credit needs; never build observer profiles.
- **Evidence:** [API robots.txt](https://api.inaturalist.org/robots.txt),
  [www robots.txt](https://www.inaturalist.org/robots.txt),
  [registry](https://registry.opendata.aws/inaturalist-open-data/),
  [geoprivacy help](https://help.inaturalist.org/support/solutions/articles/151000169938).

### Movebank (avoid)

Avoid · verified: confirmed · confidence high

- **What:** individual animal tracks. Public studies may be CC0, CC BY or
  CC BY-NC; others need the data owner's permission.
- **Terms** ([general terms](https://www.movebank.org/cms/movebank-content/general-movebank-terms-of-use)):
  users must "obtain permission from the data owner" before downloading,
  except for CC0, CC BY and CC BY-NC studies (contact is still
  encouraged); BY and BY-NC need citation. Whether every download needs an
  account isn't stated ⚠️ (login is offered).
- **robots.txt:** www.movebank.org 404 (no rules); irrelevant.
- **Why avoid:** our own rule against live or recent positions of
  individual animals, not access. Recent positions of collared game animals
  or predators could enable harassment or poaching.
- **Evidence:** [terms](https://www.movebank.org/cms/movebank-content/general-movebank-terms-of-use),
  [robots.txt](https://www.movebank.org/robots.txt).

## Bird migration and the sky

### NEXRAD Level II radar (KCBX) for night migration

Use · verified: corrected · confidence medium · effort L

- **What:** dual-polarization volume scans from KCBX, Boise (antenna
  elevation 3,172 ft per NWS's WSR-88D list, updated Aug 18, 2026).
  vol2bird turns each volume into a vertical profile of bird density,
  speed and direction in altitude bins, for a single column about 5–35 km
  around the radar.
- **Scan cadence:** every 4–6 min in precipitation modes; about every
  10 min in clear-air modes, which migration nights usually use ⚠️
  (WSR-88D scan-pattern knowledge, not checked here). So "every 5–10 min".
- **Software:** [bioRad](https://cran.r-project.org/web/packages/bioRad/index.html)
  0.12.0 (2026-06-13), MIT; [vol2birdR](https://cran.r-project.org/web/packages/vol2birdR/index.html)
  1.3.2 (2026-09-16), LGPL ≥ 3, needing GNU make, GSL, HDF5 and PROJ.
- **Coverage:** KCBX covers the valley; profiles describe only the
  5–35 km ring around the radar. Low beams toward the mountains may be
  blocked ⚠️ (not checked).
- **Access:** S3 buckets `unidata-nexrad-level2` (archive),
  `unidata-nexrad-level2-chunks` (real time) and `unidata-nexrad-level3`
  (selected Level III products), all us-east-1, unsigned. SNS topics
  (NewNEXRADLevel2ObjectFilterable, NewNEXRADLevel2Archive,
  NewNEXRADLevel3Object) announce new files, but subscribing needs an AWS
  account (an owner action); polling bucket listings works without one.
  The older archive bucket and its SNS topic stopped on Sep 1, 2025.
- **License:** NOAA (registry): NODD data "are open to the public and can
  be used as desired". Credit NOAA for unaltered data; don't present
  changed data as original or imply endorsement.
- **robots.txt:** not applicable to S3. registry.opendata.aws 404.
  cran.r-project.org disallows only per-package DESCRIPTION paths; the
  index pages were read. Checked Oct 7.
- **Updates and size:** a volume every 5–10 min (night hours for
  biology). Profiles about 1–5 MB a night; don't archive raw volumes
  (roughly 1–3 GB a day ⚠️).
- **Use cases:** "birds in the sky tonight", a migration layer at real
  altitudes; separating biological echoes from rain in the weather
  renderer; migration intensity beside FAA bird strikes and "lights out"
  nights.
- **For:** sky watchers, 3D weather viewers, birders, aircraft watchers.
  **Needs:** the 3D engine (volumetric rendering shared with clouds),
  readings (vertical profiles), the time and replay clock, the weather
  plugin's radar pipeline.
- **Risks:** new dependencies (R and C, or a Python radar stack) break the
  standard-library ingest rule: an owner decision. Dual-pol thresholds
  separate biology from weather but can't reliably tell birds from
  insects; that needs airspeed against a wind model. Raw Level II is large:
  fetch on demand and keep only profiles and maps.
- **Verification:** confirmed the buckets, SNS topics, NOAA's usage
  statement, and both packages' versions, dates, licenses and system
  requirements. Corrected: the antenna elevation (now from the official
  list); SNS needs an AWS account; the cadence.
- **Evidence:** [registry](https://registry.opendata.aws/noaa-nexrad/),
  [WSR-88D list](https://www.weather.gov/media/tg/wsr88d-radar-list.pdf),
  [bioRad](https://cran.r-project.org/web/packages/bioRad/index.html),
  [vol2birdR](https://cran.r-project.org/web/packages/vol2birdR/index.html),
  [CRAN robots.txt](https://cran.r-project.org/robots.txt).

### BirdCast

Needs owner action · verified: confirmed · confidence medium · effort S

- **What:** nightly radar-based estimates per county or state from the
  [Migration Dashboard](https://birdcast.org/migration-tools/migration-dashboard/):
  birds that crossed since the start of the night, direction, speed,
  altitude over time, and the species most likely moving. Live Mar 1–Jun 15
  and Aug 1–Nov 15; history 2013–2021; contiguous US, Ada and Canyon
  included. By Cornell, Colorado State and UMass Amherst.
- **Access:** web only (dashboard.birdcast.org); no documented API or
  downloads. Undocumented backend endpoints would need permission anyway.
- **License:** no data license. The [how to cite](https://birdcast.org/how-to-cite/)
  page gives only citation formats (for example "BirdCast, Migration
  Dashboard; state/or county, date and time"). The site links Cornell's
  general terms, which return 403 to us.
- **robots.txt:** birdcast.org: `User-agent: *` disallows `/wp-admin/`
  (allows `admin-ajax.php`), Crawl-delay 10. dashboard.birdcast.org 404.
  Re-checked Oct 7.
- **Use cases:** a link out ("Tonight's migration forecast for Ada
  County") with the citation; if Cornell agrees, nightly county totals as a
  reading.
- **For:** sky watchers, birders, gardeners. **Needs:** readings
  (time-series card).
- **Risks:** no license and no API: don't scrape. Our own radar processing
  is the open route.
- **Evidence:** [robots.txt](https://birdcast.org/robots.txt),
  [dashboard robots.txt](https://dashboard.birdcast.org/robots.txt), and
  the two pages above.

### Intermountain Bird Observatory, Lucky Peak, and HawkCount

Needs owner action · verified: confirmed · confidence medium · effort S

- **What:** Boise State's [Lucky Peak station](https://www.boisestate.edu/ibo/science/lucky/)
  on the Boise Ridge, inside the Boise River WMA above Lucky Peak
  reservoir, running since 1993. Raptor monitoring Aug 25 to the end of
  October (peaks in September and early October); songbird banding
  Jul 16–Oct 15, mornings; owl banding Sep 1–Oct 28. Songbird data goes to
  an eBird hotspot, raptor data to an HMANA (HawkCount) site profile. A
  fall 2019 total of 6,844 raptors in 563 hours is unverified ⚠️.
- **Access and license:** IBO's pages and annual reports, read by hand;
  HawkCount is a website. No license stated.
- **robots.txt:** www.boisestate.edu: `User-agent: *` with an empty
  `Disallow:` (all allowed). hawkcount.org: `User-agent: *` `Disallow: /`
  (plus `/ftp/`, summary pages and named AI bots). Re-checked Oct 7.
- **Updates and size:** daily in season; tiny.
- **Use cases:** the hawkwatch season as a lifecycle with a link; if IBO
  agrees, daily counts for a "raptors passing Lucky Peak" card.
- **For:** birders, sky watchers, hikers. **Needs:** readings,
  lifecycles, the manual source kind.
- **Risks:** HawkCount disallows all robots: no automated collection. Ask
  IBO.
- **Evidence:** [station page](https://www.boisestate.edu/ibo/science/lucky/),
  [boisestate.edu robots.txt](https://www.boisestate.edu/robots.txt),
  [hawkcount.org robots.txt](https://hawkcount.org/robots.txt).

### FAA Wildlife Strike Database

Use, by hand · verified: unverifiable · confidence low · effort S

- **What:** per the FAA FAQ (read Oct 7), about 344,000 reported strikes
  with civil aircraft in the US, 1990–2025 (about 24,500 at 870 airports in
  2025). About 54% of bird strikes happen July–October and about 70%
  between 0 and 500 ft above ground. The FAA wildlife page links the
  database app and an annual report for 1990–2025 (added Aug 4, 2026).
  Per-strike fields (airport, date, time, phase, height, species, damage)
  weren't seen directly ⚠️.
- **BOI:** a joint-use airport with Gowen Field (Idaho Air National
  Guard); military strikes are not in the civil database ⚠️.
- **Access:** an Angular web app ([wildlife.faa.gov](https://wildlife.faa.gov/home))
  with search; a whole-database download, its format and whether it needs
  a password are unconfirmed ⚠️ (the claim rests on press coverage). No
  documented API. Don't call its backend.
- **License:** US government data, public ⚠️. That reporting is voluntary
  is ⚠️ unconfirmed here (the FAQ doesn't say).
- **robots.txt:** wildlife.faa.gov/robots.txt returns 200 with the app's
  HTML shell (no valid rules, so effectively none); the page carries meta
  robots "noindex,nofollow", an indexing hint rather than robots.txt.
  www.faa.gov allows `/airports/`. Re-checked Oct 7.
- **Updates and size:** continuous at the FAA; load by hand a few times a
  year. A few hundred records for ring airports ⚠️ (unchecked).
- **Use cases:** bird strikes at BOI by month and altitude beside radar
  migration altitude; species and season risk around the airport in the
  aircraft plugin.
- **For:** aircraft watchers, sky watchers, birders. **Needs:** the manual
  source kind (hand download), the aircraft plugin, a display for readings
  or point events.
- **Risks:** reporting completeness varies, so don't rank airports by
  safety. BOI's military traffic is excluded. Drop free-text remarks if
  present (they may name people).
- **Verification:** the FAQ figures are confirmed; the download route and
  per-record fields couldn't be, because the app renders in the browser.
  It stays a manual source until the owner or the local helper looks at
  the app's download feature.
- **Evidence:** [wildlife.faa.gov robots.txt](https://wildlife.faa.gov/robots.txt),
  [faa.gov robots.txt](https://www.faa.gov/robots.txt),
  [FAA wildlife page](https://www.faa.gov/airports/airport_safety/wildlife),
  [FAQ](https://www.faa.gov/airports/airport_safety/wildlife/faq).

## Ideas by persona

From the research pass, adjusted where verification changed a fact (noted
in each). None is approved. "Correction n" refers to the list under
[What verification changed](#what-verification-changed-in-the-design).

### Commuters and drivers

- **"Deer hour" risk ribbon on roads.** Each segment shaded by carcass
  reports per km per year (IDFG roadkill matched to our segments), with a
  value per month. It brightens from 30 minutes before sunset to 2 hours
  after, and around sunrise, using the sky core's sun times. Expected to
  peak in the migration months (Oct–Dec, Apr–May) on SH-21, SH-55, SH-16,
  US-95 and SH-78 ⚠️ (not yet checked against the data). Tapping a segment
  shows the species mix, counts per year and a "last reported" date.
  Carcass dates have no time of day, so the dusk and dawn weighting has to
  come from ITD's crash times (correction 10).
  *Sources:* IDFG roadkill, ITD crash units. *Needs:* segment matcher, sky
  core (sun times), time and replay clock, layer system.
- **Valley Feed cards in season.** For example: "Mule deer migration on
  SH-21 MP 10–21: about 75–100 deer were hit each year before the
  crossings; slow down at dusk", plus new carcass reports on my saved route
  in the last 7 days. MP 10–21 is our own mapping, to check against ITD's
  LRS. A lit 511 wildlife-warning sign can join the card only in the
  owner's internal view, since 511 data isn't republished (correction 35).
  *Sources:* SH-21 crossings, IDFG roadkill, 511 signs (internal).
  *Needs:* Valley Feed, lifecycles, places and search (my route).

### Traffic safety researchers

- **Crossing before/after on the time slider.** Carcasses per year for
  SH-21 MP 10–21 and for control stretches, with the 2010 underpass and the
  March 2024 overpass marked as events; bars grow year by year and a 3D
  camera flies to each structure. The underpass's completion date still
  needs a source. *Sources:* IDFG roadkill, SH-21 crossings. *Needs:* time
  and replay clock, 3D engine, readings (time-series card).
- **Reporting-channel map** (first proposed as an "under-reporting map";
  renamed, correction 14). Per segment, police-reported "Animal - Wild"
  crashes (ITD units 2005–2023; COMPASS through 2025 only if its `event`
  column carries animal events, correction 16) beside IDFG carcass
  reports, as a ratio badge. A data-quality note explains that the two
  count different events and that most carcass rows have been salvage
  reports since the 2012 salvage law. *Sources:* ITD crash units, IDFG
  roadkill. *Needs:* safety plugin, segment matcher, evidence and review
  (confidence badges).

### 3D map viewers

- **The SH-21 crossings in 3D.** Model the Cervidae Peak overpass (about
  150 ft wide) at MP 19.3 and the Robie Creek underpass on the 1 m terrain,
  with OpenStreetMap fences if mapped. In migration season a schematic
  "herd flow" of soft particles moves between the Boise River WMA and the
  Boise Ridge through the crossings, clearly labelled illustrative, not
  tracked animals. Size it by IDFG's figures (5,000–8,000 mule deer and
  1,800 elk wintering on the WMA), not the unsourced 8–9k and 1.8–2.4k
  (correction 31). *Sources:* SH-21 crossings, IDFG hub (WMAs, deer
  units). *Needs:* 3D engine (models, particles), time and replay clock.

### Hikers, dog walkers and cyclists

- **"Closed for wildlife today."** Clock-driven shading on trails and land:
  the Boise River WMA Cornell segment (Feb 1–Apr 14), the Valley Fire burn
  closure west of SH-21 (winters of 2025 and 2026), the Deer Flat islands
  (Feb 1–Jun 14, some to Jun 30), the Gotts Point and Murphy's Neck
  off-trail windows, and the Birds of Prey canyon firearm closure
  (Feb 15–Aug 31). Each card cites its rule, links the official page and
  shows "last checked". *Sources:* Boise River WMA rules, Deer Flat rules,
  Birds of Prey NCA map, IDFG hub. *Needs:* lifecycles with yearly
  recurrence, manual source kind, lands and trails plugins, Valley Feed.
- **Seasonal reminders on a planned route.** "Dogs must be leashed on the
  Boise River WMA until Apr 30"; "No big game hunting in this zone" (the
  research placed one between SH-21, Warm Springs and the city limits ⚠️,
  not re-checked); "Hunting season may be open in GMU 39: wear orange"
  (the GMU is an example ⚠️; season dates entered by hand from IDFG's
  rules, with the regulation link). *Sources:* Boise River WMA rules, IDFG
  hub (hunting restrictions, GMUs), IDFG website (season dates, facts
  only). *Needs:* lifecycles, trails plugin, places and search.
- **Greenbelt and foothills wildlife layer for cyclists.** Recent
  carcasses on roads near bike routes, Deer Flat's bike rules (designated
  roads and trails; groups over ten need a permit), and a "rattlesnake
  season" card from monthly observations aggregated per cell (GBIF), never
  points. *Sources:* IDFG roadkill, Deer Flat rules, GBIF. *Needs:* roads
  plugin, sensitivity rules, layer system.

### Hunters and anglers

- **A "Hunt & fish" lens.** GMUs, controlled hunt areas, restricted zones,
  WMAs and Wildlife Habitat Areas, fall pheasant stocking areas, CWD
  results by GMU, fishing and boating access sites and family fishing
  waters. A day card says which rules and closures apply here today. The
  closure and Access Yes! layers can come from the public Hunting map under
  its CC BY text (correction 2). Stocking events only if IDFG grants
  permission. *Sources:* IDFG hub, IDFG portal, IDFG website. *Needs:*
  layer system, lifecycles, places and search.

### Birders and naturalists

- **"What's here this week."** A species card for any place: eBird's CC BY
  copy and iNaturalist on GBIF, aggregated to cell × week of year. GBIF
  gives record counts, not complete-checklist effort, so show "records per
  cell-week" rather than eBird-style frequency (correction 25), and show
  how current the data is, since EOD was last published Aug 2025
  (correction 26). IDFG's hex grid adds trusted species lists. Sensitive
  taxa show only as "n sensitive species recorded in this area", never as
  points. Every card lists its datasets and licenses. *Sources:* GBIF API,
  GBIF snapshot, IDFG portal, NatureServe. *Needs:* areas, places and
  search (species), sensitivity rules, licensing and visibility.
- **Birding trail and hotspots.** Idaho Birding Trail routes and sites,
  IDFG Conservation Sites (the research equated them with Important Bird
  Areas ⚠️), Deer Flat and Fort Boise WMA, and the Lucky Peak hawkwatch as
  a season (Aug 25–Oct 31) linking to IBO; daily counts only if IBO agrees.
  *Sources:* IDFG hub, IBO and HawkCount, Deer Flat rules. *Needs:* layer
  system, lifecycles, places and search.

### Sky watchers and 3D weather viewers

- **"Birds in the sky tonight."** From KCBX, profiles every 5–10 minutes
  become a translucent 3D band of migrating birds at their real altitudes,
  with drift arrows for direction and speed, and a dashboard line such as
  "Tonight: heavy migration, peak about 600 m AGL, heading SSW". A profile
  describes one column near the radar, so the valley-wide band takes its
  horizontal structure from per-scan density maps and is labelled a model
  (correction 28). Replay any night in season on the game-speed clock.
  *Sources:* NEXRAD KCBX with bioRad and vol2birdR; BirdCast as a link
  only. *Needs:* 3D engine (volumetric, shared with clouds), readings, time
  and replay clock, the weather plugin's radar pipeline.
- **Rain, snow or birds?** The weather renderer splits hydrometeors from
  biological echoes in the same KCBX scans, so birds and insects go to the
  wildlife layer instead of being drawn as phantom drizzle on clear
  September nights. NEXRAD Level III hydrometeor classification, which has
  a biological class, may save reimplementing it (correction 29).
  *Sources:* NEXRAD KCBX. *Needs:* 3D engine (volumetric), the weather
  plugin's radar pipeline.
- **"Lights out tonight"** (also for gardeners). Alerts on peak migration
  nights from our own radar profiles; Overture building heights show which
  tall, lit downtown buildings matter most, so their owners can dim lights
  on those nights. *Sources:* NEXRAD KCBX. *Needs:* 3D engine (buildings),
  readings, Valley Feed.

### Aircraft watchers

- **Bird-strike context panel** in the aircraft plugin. FAA strike history
  at BOI and other ring airports by month and altitude, beside tonight's
  radar migration profile; aircraft on approach tinted when migration is
  heavy at their altitude band. Labelled context, not a safety rating.
  Beside any BOI chart, say that military strikes at the joint-use field
  are missing ⚠️ (correction 34); that reporting is voluntary is itself ⚠️.
  *Sources:* FAA strikes, NEXRAD KCBX. *Needs:* aircraft plugin (tracks),
  readings, 3D engine.

### Gardeners

- **Garden wildlife card** for a home location: IDFG's monarch and
  milkweed suitability; pollinator and butterfly records nearby,
  aggregated per cell, CC0 and CC BY only for display; native plants
  recorded within a few km (Snake River Plain and College of Idaho herbaria
  on GBIF), passed through the sensitivity filter (correction 21); birds
  likely at feeders this month. For foothills homes, a deer-browse hint
  from distance to the WMA and carcass density, labelled a rough
  heuristic. *Sources:* IDFG portal, GBIF, IDFG roadkill, IDFG hub (WMAs).
  *Needs:* areas, sensitivity rules, sky core (pairs with the sun and shade
  garden tool).

### Farmers

- **Farm and wildlife layer.** Fall pheasant release areas and Access Yes!
  and access-agreement lands (where landowners have opened land); winter
  waterfowl concentrations at Deer Flat and Fort Boise (aggregated eBird
  counts per cell); invasive aquatic species records in canals and
  reservoirs (USGS NAS via GBIF). *Sources:* IDFG portal, IDFG hub, GBIF.
  *Needs:* layer system, areas.

### Fire and hazards watchers

- **Fire meets habitat.** When the hazards plugin draws a fire perimeter,
  the wildlife layer lists what it overlaps: slickspot peppergrass critical
  habitat, sage-grouse zones, the Birds of Prey NCA, WMAs. (The research
  also listed WMA winter range; that layer is token-only.) Later closures,
  such as the Valley Fire WMA closure, link back to the fire as follow-on
  events. *Sources:* USFWS critical habitat, IDFG hub (sage-grouse zones,
  WMAs), Boise River WMA rules, Birds of Prey NCA map. *Needs:* hazards
  plugin, lifecycles (linked events), areas.

### Land explorers and campers

- **"Who manages this, and what's allowed for wildlife."** On tap: refuge,
  WMA, Wildlife Habitat Area, NCA or critical habitat, with today's rules
  (boating, dogs, drones, firearms, entry) and the federally listed species
  that may occur here (IPaC), as a list labelled "may occur", never a map
  of where they are. *Sources:* USFWS refuge boundaries, IDFG hub, USFWS
  critical habitat, ECOS and IPaC, Deer Flat rules, Birds of Prey NCA map.
  *Needs:* lands plugin, lifecycles, places and search.

## Design notes

The research pass's proposal, with verification's changes folded in where
they apply. The full list of changes follows in the next section.

### What exists for the valley

- **IDFG's roadkill database is the strongest local source:** public,
  near-daily (latest record Oct 6, 2026), 5,841 records in the box and
  about 9,267 in the ring, no reporter identities. It needs nothing but the
  core ArcGIS reader.
- **Winter range and migration corridors for the Boise River herds aren't
  public.** USGS's corridor series holds only three Owyhee-desert elk herds
  for Idaho, all south of the ring; IDFG's mule deer seasonal-ranges
  service needs a token. So we can show the crossings, the closures and the
  carcasses, but not the corridors themselves, unless IDFG shares them.
  IDFG's "wildlife linkage" PDFs for ITD Districts 3–5 are the nearest
  public thing, for reading by hand.
- **eBird and iNaturalist both disallow automated access** in robots.txt.
  Their data reaches us legally through GBIF, whose API robots.txt allows
  us: eBird's GBIF copy is CC BY 4.0 (2.66 million records in the box);
  iNaturalist's is per-record CC0, CC BY or CC BY-NC.

### Plugin shape (a proposal for the owner)

- **`wildlife`** (public, small): IDFG roadkill; the animal crash flag
  (read from the safety plugin's tables); the SH-21 crossings; IDFG hub and
  portal layers; USFWS critical habitat; the seasonal rules (manual
  source); FAA strikes (manual); later, the radar biology profiles. It
  depends on `roads` (segment matching) and `safety` (the animal flag).
  WMAs, refuges and the NCA boundary may sit in `lands`, with `wildlife`
  adding only their rules.
- **`nature`** (public, the large one): GBIF occurrences or their
  aggregates, the IDFG hex grid, NatureServe ranks. Split from `wildlife`
  for the same reason cameras stand alone: storage and switching it off.
- **Private:** nothing needed now. IDFG data-request products, if ever
  bought, would go to a private plugin with restricted storage.

### Time shapes

- **Point events.** Roadkill, bird strikes and species observations (and
  crashes, already) happen at an instant: they aren't tracks, readings or
  lifecycles. Option (a) is a fourth core shape, "occurrences" (id, time,
  point, kind, attributes), with a shared heat or grid display filtered by
  the clock window; option (b) is zero-length lifecycles in `evt.event`.
  Verification favours (a): crashes already sit in `obs.crash`, a
  Timescale hypertable, and zero-length lifecycles would never be "active"
  at a sampled instant, so they'd need window queries anyway
  (correction 17).
- **Seasonal rules** (closures, leash, boating, hunting and nesting
  seasons) are lifecycles that recur every year: either a `manual` source
  (YAML in the plugin, each rule with its citation URL, last-checked date
  and an RRULE-like recurrence) or one `evt.event` generated per year ahead
  of time. The Valley Feed and "what was active at this moment" then work
  unchanged. Windows that wrap across New Year (Deer Flat North Side
  Aug 1–Jan 31; WMA dog leash Nov 16–Apr 30) must be handled
  (correction 18).
- **Radar biology profiles** are readings: a station × altitude × time
  series at KCBX.

### Sensitive species and people (a proposed extension of licensing and visibility)

- **Two mechanisms, not one table** (correction 19):
  - `taxon_sensitivity`, per taxon: IDFG's hex `sensitive=1`; ESA-listed
    taxa and eagles (Bald and Golden Eagle Protection Act); NatureServe
    S1–S2 and its sensitivity categories; iNaturalist taxon geoprivacy;
    eBird's sensitive list if it can be had ⚠️; and an owner list.
  - A per-record "obscured" flag (GBIF `informationWithheld`, or
    `coordinateUncertaintyInMeters` of 10 km or more) that keeps a record
    out of any cell finer than its obscuring cell. The first proposal
    merged these into the taxon table, which would have marked common
    species sensitive whenever an observer chose to obscure them.
- **Public rule:** never draw points for sensitive taxa. Aggregate to at
  least IDFG's hex (about 106 km²) or a 0.2° cell (about 357 km² at
  43.5°N), and where IDFG flags a taxon show "n sensitive taxa recorded"
  rather than names. Align our grid to 0.2° multiples so iNaturalist's
  obscured records fall in the right cell instead of smearing across
  neighbours (correction 20).
- **Never store or draw** nest, den, roost, lek, hibernaculum, rookery or
  colony features, whatever the source, including raptor nests in the NCA
  and heron islands at Deer Flat. Closures can be shown; the points behind
  them can't.
- **Optional delay:** show owl, raptor and rare-vagrant observations only
  after 30 days.
- **No live or recent positions of individual animals** (no Movebank or
  collar data); the 3D herd flow is schematic.
- **People:** drop GBIF `recordedBy` and `identifiedBy` and iNaturalist
  usernames at ingest; drop IDFG roadkill's `note` at ingest (correction
  13); never query IDFG's `Wildlife_Conflicts_public` service.
- **Aggregate-only storage is the default for GBIF:** species × cell ×
  week counts plus per-dataset and per-license tallies for attribution,
  with no raw points kept. That cuts storage from about 1–2 GB to tens of
  MB. Exact points for non-sensitive taxa only if the owner wants them.

### Ingest and matching

- **IDFG roadkill:** page by `OBJECTID` with the shared ArcGIS reader;
  keep raw versions in `raw.record`, without `note`. Store `observed` as a
  date. Match to roads by ITD route and milepost where `highway` and
  `milepost` are present (LRS measure through ITD's road network service),
  after checking the free-text milepost against the coordinates; otherwise
  by nearest segment. The research proposed 50 m; verification suggests
  testing 100–150 m with a road-class tie-break, since locations are
  phone-reported, and reporting the share left unmatched (flagged
  off-road). Rates per km, and per vehicle-km where AADT exists, before
  Empirical-Bayes smoothing; seasonal and yearly profiles only, with the
  diel profile from ITD's `Accident_Date_Time` or COMPASS's `crashed_at`
  (corrections 10 and 15).
- **Animal crash flag:** crash-level `animal_wild` and `animal_domestic`
  booleans from ITD units, and from COMPASS units (restricted) if its
  `event` column turns out to carry them. Publish only the crash-level
  flag, which isn't personal.
- **GBIF, four routes:**
  1. Faceted counts (`limit=0`, `facet=speciesKey`, a large `facetLimit`)
     per 0.2° cell and month or week: keyless, no new dependency, and no
     raw points or names ever stored. The ring is about 9 × 7 cells, so a
     bootstrap by month of year is roughly 750 requests, then small
     increments. Added by verification (correction 23).
  2. The search API for monthly increments, filtered by geometry and
     month and split to stay under the 100,000 paging cap.
  3. The AWS Parquet snapshot for a bootstrap: no account, but a new
     dependency and several GB transferred.
  4. The download API with an owner GBIF account: a DOI per download, the
     cleanest for citation.

  The research recommended (4) monthly if the owner makes an account, else
  (3) plus (2); verification prefers (1) over (3) for the bootstrap.
- **Radar:** KCBX Level II from the archive or chunks bucket, polled
  unsigned (SNS push needs an AWS account); vol2bird profiles at night;
  keep profiles and density maps only. Share the weather plugin's radar
  fetch and classification. Dependency choice: bioRad (R, MIT) with
  vol2birdR (LGPL-3, C libraries), or a Python implementation on Py-ART ⚠️:
  an owner decision under the standard-library rule.
- **IDFG hub layers:** monthly. The hub's 60 s Crawl-delay applies to the
  hub host; the services on services.arcgis.com and IDFG's own server each
  get their own gentle pacing (correction 5).

### 3D and visual

- Crossings as small models.
- Closures as hatched land with a clock icon.
- Roadkill risk as a glowing ribbon, not red/green alone: a sand-to-violet
  ramp with a pattern, per [ch. 13](../13-visual-design.md).
- Radar migration as a translucent band of particles, density from the
  profile and drift from its speed and direction, labelled a model.
- The species hex grid as soft hexes, never points.
- All wildlife layers in a "Nature" lens beside Land and Sky; the radar
  layer is shared with Sky.

### Licensing summary

| Terms | Sources |
|---|---|
| Public domain | USFWS, USGS (except as below), NOAA, FAA ⚠️ |
| CC0 | USGS ungulate migrations; Breeding Bird Survey |
| CC BY 4.0 | eBird's EOD on GBIF; NatureServe Explorer; IDFG's public Hunting map ("CC-BY Idaho Fish and Game") |
| Per record (CC0, CC BY, CC BY-NC) | GBIF; iNaturalist |
| No license: credit and a courtesy note, if the owner extends the Oct 6 rule | IDFG GIS (roadkill, hub, portal) |
| Facts plus a link (website terms forbid mirroring) | IDFG website pages |
| Avoid | eBird direct, the iNaturalist API, HawkCount automation, Movebank, IDFG's conflicts service |
| Needs the owner | IDFG token layers and stocking permission, IDFG data requests, BirdCast data, IBO counts, an optional GBIF account, an AWS account for radar push |

## What verification changed in the design

Verification on Oct 7 of the design as well as the sources. Numbers are
referred to above.

**Licensing and access**

1. **IDFG's website terms don't cover its GIS.** They define "our
   Websites" as idfg.idaho.gov, gooutdoorsidaho.com, gofishidaho.org and
   gohuntidaho.org, so the no-mirroring clause covers the web pages
   (stocking, WMA pages, press releases) but not gisportal-idfg.idaho.gov
   or the hub. Keep "facts plus a link" for the pages.
2. **IDFG publishes one explicit license:** the public root
   `Hunting/MapServer`'s copyright text, "CC-BY Idaho Fish and Game". Use
   it for hunting closures, GMUs, controlled hunts and Access Yes! lands,
   crediting IDFG under CC BY, and drop Access Yes! from the token
   request.
3. **The owner's no-license rule was set narrower than the research
   assumed.** The Oct 6 rule ("assume it's fair, send a courtesy message")
   was stated for city and county imagery. Applying it to IDFG's roadkill,
   hex grid and other unlicensed layers is a new owner decision, to record
   in [DECISIONS](../DECISIONS.md).
4. **Licenses confirmed:** NatureServe CC BY 4.0 on its own page; the
   Breeding Bird Survey CC0 (the research cited a superseded release); USGS
   migrations CC0.
5. **IDFG's hub data lives on two hosts.** Roadkill, Access Agreements,
   Family Fishing Waters and Fishing and Boating Access Sites are on
   gisportal-idfg.idaho.gov, the rest on services.arcgis.com. The hub's
   60 s Crawl-delay applies only to the hub; give IDFG's own IIS server its
   own gentle pacing.
6. **`Wildlife_Conflicts_public` is a write-only intake** (Create,
   Uploads, Editing, ChangeTracking; no Query; MapServer `maxRecordCount`
   0). The personal fields are in the schema, but records are probably not
   readable, so the question of warning IDFG is largely moot. Keep "avoid"
   and never probe it.
7. **`Pheasant_Stocking` may be publicly editable** (its FeatureServer
   advertises Create, Update and Delete). Version everything read from it,
   flag sudden geometry changes, never write to it.
8. **Other hosts:** ECOS pull reports' listed host,
   ecp.ecosphere.fws.gov, doesn't resolve, so treat it as disallowed and
   use ecos.fws.gov/ecp/report/... (200; robots.txt 404). IPaC "WILL
   EVENTUALLY REQUIRE AN API KEY": plan a free-key owner action. The
   Federal Register's HTML pages send bots to an unblock page; use its
   `/api/v1/` JSON (allowed by robots.txt) for facts.
9. **NEXRAD push needs an AWS account** (an owner action); unsigned
   polling of `unidata-nexrad-level2-chunks` is the keyless route.

**Roadkill and crashes**

10. **Roadkill dates are calendar dates** stored at 00:00 UTC; converting
    them to America/Boise moves every record to 18:00 the day before.
    Store them as dates. They can't support time of day or "deer hour"
    calibration: use ITD's `Accident_Date_Time` (crash units, layer 35) or
    COMPASS's `crashed_at` for the diel profile, and carcasses only for
    seasonal and yearly patterns.
11. **Records start in 1977** per the service, but the box minimum is
    1970-04-02: flag pre-1977 dates as suspect.
12. **The `path` field is undocumented** and may point to a photo; don't
    fetch or publish it until its meaning is known.
13. **Drop `note` at ingest** rather than keep it internally: nothing uses
    it, and that's privacy by default.
14. **"Under-reporting ratio" was mislabelled.** Carcass reports and
    police crashes are different events: animals die off-road after
    crashes, carcasses are found without a crash report, and since the 2012
    salvage law most reports are salvage permits. Call it a
    "reporting-channel ratio" with a data-quality note.
15. **Segment matching:** mileposts are free text, so validate them
    against the coordinates before trusting the LRS route; 50 m is tight
    for phone-reported locations, so test 100–150 m with a road-class
    tie-break and report the unmatched share; normalise per km and, where
    AADT exists, per vehicle-km before Empirical-Bayes smoothing.
16. **COMPASS's `restricted.crash_unit.event`** is documented with
    collision-manner values; check with one SQL query whether animal events
    appear there before relying on it through 2025.
17. **Time shapes:** crashes already live in `obs.crash`, a Timescale
    hypertable, so instants are being stored like readings; zero-length
    lifecycles would need window queries anyway. That strengthens a core
    "occurrences" shape with clock-window aggregation.
18. **Seasonal recurrence must wrap across New Year** (Deer Flat North
    Side Aug 1–Jan 31; WMA dog leash Nov 16–Apr 30).

**Sensitivity and aggregation**

19. **The proposed `taxon_sensitivity` table mixed two things:** per-taxon
    sensitivity and per-record geoprivacy. GBIF `informationWithheld` or a
    coordinate uncertainty of 10 km or more often means an observer chose
    to obscure a common species; unioning those into a taxon table would
    wrongly mark common species sensitive. Keep (a) a taxon table (IDFG's
    hex flag, ESA and the Bald and Golden Eagle Protection Act, NatureServe
    S1–S2 and its categories, iNaturalist taxon geoprivacy, an owner list)
    and (b) a per-record "obscured" flag that keeps a record out of any
    cell finer than its obscuring cell.
20. **Measured cell sizes:** IDFG's hex is about 106 km² (0.135° × 0.117°;
    regular in degrees, not equal-area). A 0.2° cell at 43.5°N is about
    357 km². iNaturalist obscures within a fixed 0.2° grid, so align ours
    to 0.2° multiples.
21. **Herbarium records on GBIF** (Snake River Plain, College of Idaho) can
    hold exact localities of rare plants such as slickspot peppergrass; the
    gardener card's "native plants within a few km" must pass the
    sensitivity filter.

**GBIF**

22. **The paging cap is exactly offset + limit ≤ 100,000.**
23. **A keyless, dependency-free, privacy-preserving route was missed:**
    faceted counts per 0.2° cell and month (or week), about 750 requests
    for a bootstrap over the ring. Prefer it to the AWS snapshot for the
    bootstrap; keep the download API (account) as the citation-clean
    option.
24. **The AWS snapshot** is about 180 GB a month and not partitioned by
    space: a filtered scan still transfers several GB to the server and
    needs pyarrow or duckdb.
25. **Frequency like eBird's bar charts needs effort data** (the share of
    complete checklists). GBIF's EOD copy gives record counts; without a
    complete-checklist flag ⚠️, show "records per cell-week" (or distinct
    events as a rough denominator), not true frequency.
26. **EOD was last published 2025-08-08,** already over a year old: show
    data currency on the card.

**Radar**

27. **Scan cadence:** clear-air modes, usual on migration nights, give
    volumes about every 10 min; 4–6 min is precipitation mode ⚠️. Say
    "every 5–10 min".
28. **vol2bird gives one profile** for a column about 5–35 km around KCBX,
    not a 3D field. For a valley-wide layer, take horizontal structure from
    per-scan vertically integrated density maps (bioRad's PPI integration)
    and vertical structure from the profile; label the result a model.
29. **Birds versus insects** needs airspeed against a wind model (for
    example RAP or HRRR); dual-pol thresholds alone can't do it. The
    weather renderer can reuse NEXRAD Level III hydrometeor classification
    (in `unidata-nexrad-level3`), which has a biological class.
30. **KCBX's antenna elevation** is 3,172 ft (official list).

**Ideas and open questions**

31. **Herd sizes on SH-21:** "8–9k deer and 1.8–2.4k elk" is unsourced. Use
    IDFG's: 5,000–8,000 mule deer and 1,800 elk wintering on the WMA (WMA
    page); about 2,400 deer and 650 elk in the Valley Fire area (Jan 13,
    2026 release); about 7,500 deer (2010 release).
32. **SH-21 crossings:** the underpass was "scheduled" for summer 2010, so
    confirm completion; MP 10–21 for Warm Springs Ave to Robie Creek is our
    own mapping, to check against ITD's LRS; the 14,000 vehicles a day is
    from the 2024 USFWS story.
33. **Y P Desert elk:** 15 animals and 59 migration sequences, 2014–2020
    (not 35 elk, 2015–2022). All of USGS's Idaho corridor items lie south
    of 42.90°N.
34. **BOI is joint-use with Gowen Field,** so military strikes are missing
    from the FAA's civil database ⚠️; say so beside any BOI strike chart.
35. **511 wildlife-sign data is internal only,** so it can't appear in the
    public "Deer hour" or Valley Feed cards; keep that part owner-only.
36. **Local sources worth a hand look** (no new automated access
    proposed): the IDFG/ITD "wildlife linkage" reports for ITD Districts 3,
    4 and 5 (PDFs linked from
    [IDFG's collisions page](https://idfg.idaho.gov/wildlife/highway-wildlife-collisions)),
    the nearest public thing to corridor maps for the valley;
    `Wildlife/Greater_Sage_grouse_Habitat` (public, BLM and IDFG);
    `Species/Taxonomy_Table`, which may supply status ranks for the
    sensitivity table.
37. **Updates to the open questions,** applied below: drop Access Yes!
    from the IDFG token request and add `count_trusted`, the `path` field
    and `Pheasant_Stocking`'s editability to the IDFG note; the conflicts
    question is largely moot; add the facet route to the GBIF question;
    two new questions (extending the no-license rule to IDFG, and IPaC's
    coming key).

## Open questions

For the owner, one at a time; none is decided.

1. **Plugin split:** one `wildlife` plugin, or `wildlife` (roads, habitat,
   rules: small) plus `nature` (GBIF and species aggregates: larger)? And
   do WMAs, refuges and the Birds of Prey NCA boundary belong to the coming
   `lands` plugin, with `wildlife` adding only their rules?
2. **Point events:** should instants (crashes, roadkill, bird strikes,
   species observations) become a fourth core time shape, "occurrences",
   with a shared clock-window heat or grid display, or be stored as
   zero-length lifecycles? Verification leans to occurrences
   (correction 17).
3. **Seasonal rules:** keep WMA closures, dog-leash season, Deer Flat
   boating and island closures, the NCA canyon firearm closure and hunting
   seasons as a hand-maintained `manual` source with yearly recurrence and
   a seasonal re-check? Who reviews them each year?
4. **Sensitive-species and people rules:** approve the rules in the design
   notes (no points for sensitive taxa; cell or hex aggregation; never
   nests, dens, leks or roosts; an optional 30-day delay; drop observer
   names; aggregate-only GBIF storage by default), with the taxon table and
   per-record flag kept separate?
5. **GBIF:** faceted counts through the public API (keyless, no new
   dependency); an owner GBIF account for the download API (a DOI per
   download, and derived-dataset DOIs for citation); or a bootstrap from
   the AWS Parquet snapshot, which needs pyarrow or duckdb in the ingest
   image, against the standard-library rule?
6. **Radar biology:** allow a radar dependency (bioRad in R with
   vol2birdR, LGPL-3, plus GSL, HDF5 and PROJ; or a Python radar stack) in
   a worker image, shared with the weather plugin's 3D precipitation work?
   And an AWS account for SNS push, or polling only?
7. **One courtesy note to IDFG** asking for: (a) access to the token-only
   Mule Deer Seasonal Ranges and Fishing Seasons and Rules layers (not
   Access Yes!, which is public); (b) permission to store and show stocking
   records; (c) confirmation that republishing roadkill and hex-grid
   aggregates with credit is fine; (d) the meaning of `count_trusted` and
   of roadkill's `path` field, and the hex size; (e) whether
   `Pheasant_Stocking` is meant to be publicly editable.
8. **No-license rule:** should the Oct 6 "no license, courtesy note" rule
   extend from city and county imagery to all unlicensed state-agency GIS,
   such as IDFG's?
9. **IDFG's conflicts service:** its schema has reporter and landowner
   contact fields, but it's write-only (no Query), so records are probably
   not readable. Does the owner still want to mention it to IDFG
   privately? Largely moot.
10. **BirdCast and Cornell:** ask for nightly county migration values for
    Ada and Canyon, or rely on our own KCBX processing and link out to
    BirdCast?
11. **Intermountain Bird Observatory:** ask for Lucky Peak's daily raptor
    counts (HawkCount's robots.txt disallows all automated access)?
12. **FAA strikes:** should the owner or the local helper look at the
    app's download feature and download the full database by hand a few
    times a year (format and size unchecked)?
13. **Hunting seasons by GMU:** worth entering season dates by hand from
    IDFG's rules (facts, with a "check the regulations" link) so hikers see
    "hunting season open here"?
14. **Winter range:** should it ever be drawn, even generalized, given that
    showing where wintering deer and elk concentrate can invite
    disturbance? The alternative is to show only the closures and
    crossings.
15. **Checks on what we already hold:** does our OpenStreetMap load (on the
    server) have wildlife-crossing and fence tags along SH-21? Do any of
    the 385 road-weather camera views watch SH-21 or SH-55 crossing zones,
    for research-only animal detection with no images republished?
16. **Not checked in depth:** the Audubon Christmas Bird Count (Boise,
    Nampa) and eBird Status & Trends rasters, both with restrictive terms or
    keys. Worth an owner request later?
17. **IPaC's coming API key:** register for it when announced (a likely
    free-key owner action)?
