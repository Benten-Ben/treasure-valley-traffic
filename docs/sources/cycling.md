# Cycling sources (researched Oct 7, 2026)

Sources for cycling and walking: the bike and pedestrian networks, Level of
Traffic Stress (LTS), sidewalks, curb ramps and crossings, bike and
pedestrian counts, bike and pedestrian crashes, scooters and bike share, and
safe routes to school and to the bus. The study area is the valley box
(W −117.05, S 43.00, E −115.95, N 43.85) and, for corridors and road rides,
the proposed regional ring (about W −117.30, S 42.90, E −115.60, N 44.30;
[DECISIONS](../DECISIONS.md)). This page belongs to
[chapter 17](../17-sources-for-new-plugins.md) (sources for the new
plugins); the ideas behind it are in
[chapter 16](../16-ideas-and-personas.md#cyclist-and-pedestrian-safety-roads).

**Status: research only; nothing here is approved.** Each source goes to
the owner one at a time before anything is built
([SOURCES](../SOURCES.md)). Every entry was checked against its official
pages, robots.txt and terms on Oct 7, 2026: of the 28 sources, 17 were
confirmed and 11 corrected (the text below is the corrected version). None
was refuted outright, but some claims were: that Nampa's layers are stale
since 2021, that West Ada and Kuna publish school walk zones (theirs are
attendance areas), and that an ACHD layer of "suggested new crossings" is
usable (it holds advisory-group members' names and comments). The
**Verdict** column is the research recommendation, not a decision. ⚠️ marks
anything resting on secondary sources, an estimate or something not
checked.

**Requests made.** The research pass made two statistics queries on ACHD's
bike network (gis.achdidaho.org), one count on ACHD's bike LTS layer
(services2.arcgis.com), one attribute-only query on COMPASS's counter
locations (swidrdc.org), one grouped query on ITD's crash units, small reads
of compassidaho.org pages (the first few closer together than its 60 s
Crawl-delay, the rest at least 60 s apart), and one read of MobilityData's
`systems.csv` catalog, searched and not saved. Several of its numbers came
from a small model summarising JSON; the totals were re-added by hand (the
bike-network rows sum to 3,932 features and 1,080 mi), epoch dates were
recomputed by hand, and per-class counts for ACHD's 2023 bike LTS were left
out because they looked inconsistent. The verification pass made metadata
reads, two grouped queries on gis.achdidaho.org, two count-only queries on
services2.arcgis.com, one attribute-only query on swidrdc.org, one grouped
query on gis.itd.idaho.gov, two HEAD requests on static.nhtsa.gov and two
compassidaho.org page reads well over 60 s apart, and read robots.txt for
every host named. Neither pass used an account or key or downloaded a
dataset. The web-search budget ran out before every check was done (one
gap: whether COMPASS has a public Eco-Visio counter page ⚠️).

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| **ACHD layers (Ada County)** | | | | | | | | |
| [ACHD Official Bicycle Facility Network](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Official_Bicycle_Facility_Network/FeatureServer/1) | ACHD | 3,932 bike-network segments (1,080 mi), facility details per direction, and ACHD's own LTS | ArcGIS FeatureServer, 2,000 a query | None | No license; disclaimer ("not for planning determinations"); credit ACHD | 404, no rules | Internal only | Confirmed |
| [ACHD Master Bicycle Map](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer) | ACHD; scored by Alta Planning + Design | Bike LTS 2023 for 4,584 segments and for intersections; low-stress routes | ArcGIS Online FeatureServer, 1,000 a query | None | None stated; credit ACHD | 403, no rules | Internal only | Confirmed |
| [ACHD Master Pedestrian Map](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer) | ACHD; scored by Alta | Walking LTS 2023 for 34,771 segments and for intersections | ArcGIS Online FeatureServer, 1,000 a query | None | None stated; credit ACHD | 403, no rules | Internal only | Corrected |
| [ACHD sidewalks, ramps and sidewalk projects](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Sidewalks/FeatureServer/1) | ACHD | 45,047 sidewalk lines (width, buffer, condition category), curb ramps, Five-Year Plan sidewalk projects | ArcGIS FeatureServer, 2,000 a query | None | Disclaimer ("general reference purposes only"); credit ACHD | 404, no rules | Internal only | Corrected |
| [ACHD ArcGIS Online active-transport layers](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Sidewalk_Gap_Map_WFL1/FeatureServer) | ACHD (some from COMPASS or consultants) | Sidewalk gaps, enhanced crossings, micro-paths, safe-routes walking layers, Boise walk zones, LTS street trees | ArcGIS Online FeatureServers, 2,000 a query | None | Mostly blank; Boise school zones "not intended for use in commercial transactions" | services2 403, maps.achdidaho.org 404: no rules | Internal only | Corrected |
| **COMPASS layers (Ada and Canyon)** | | | | | | | | |
| [COMPASS ExistingBikeAndPed](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer) | COMPASS | Pathways, bike facilities and sidewalks for both counties; a routable walking network; regional routes | ArcGIS FeatureServer, 2,000 a query | None | Disclaimer only; internal until COMPASS answers | 404, no rules | Internal only | Confirmed |
| [COMPASS bike and pedestrian counters](https://compassidaho.org/bicycle-and-pedestrian-counter-data/) | COMPASS, with ACHD | 28 counter locations; annual PDF reports for 2020–2023; earlier years on request | One layer query; PDFs by hand; data by request | Partnership | "General planning purposes only" | compassidaho.org Crawl-delay 60; swidrdc.org 404 | Needs owner action | Corrected |
| [COMPASS Walkability web map and Data Bike](https://swidrdc.org/arcgis/rest/services/COMPASSData/WalkabilityWebmap/FeatureServer) | COMPASS | School and bus-stop walksheds, sidewalk-gap markers; pathway roughness reports | ArcGIS FeatureServer; Data Bike PDFs, data by request | None | No terms; internal until COMPASS answers | swidrdc.org 404; compassidaho.org Crawl-delay 60 | Internal only | Confirmed |
| **City layers** | | | | | | | | |
| [Boise Pathways Master Plan](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Pathways_Master_Plan/FeatureServer) | City of Boise Parks and Recreation | Existing and proposed paved pathways | ArcGIS Online FeatureServer, 2,000 a query | None | Disclaimer only; credit City of Boise | 403, no rules | Use | Confirmed |
| [Boise Greenbelt closures](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer/0) | City of Boise Parks and Recreation | Current Greenbelt construction closures (no dates) | ArcGIS Online FeatureServer view | None | Disclaimer; credit City of Boise Parks and Recreation | 403, no rules | Use | Confirmed |
| [Boise Greenbelt markers, repair stations, trees and trails](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/GreenbeltDOTSMileMarkers/FeatureServer) | City of Boise | DOTS mile markers, bike air and repair stations, park and street trees, Ridge to Rivers trail lines, canopy tiles | ArcGIS Online FeatureServers; canopy as tile services | None | Disclaimer; fire-GIS markers may be redistributed with metadata or credit | 403, no rules (tiles host not checked) | Use | Corrected |
| [Boise's copy of ACHD's low-stress bikeways](https://www.arcgis.com/sharing/rest/content/items/b10f49d12f97407796643136d021fa24) | City of Boise (ACHD data) | ACHD's Regional Low-Stress Bikeway Network | ArcGIS Online, publicly readable | None | "Not to be shared beyond those with whom ACHD has provided" it | 403, but the terms forbid sharing | Avoid | Confirmed |
| [Meridian Pathways Network](https://services1.arcgis.com/AutSHdEbRDZToajo/arcgis/rest/services/Meridian_Pathways_Network/FeatureServer) | City of Meridian Parks and Recreation | Existing, micro- and planned pathways, many along canals | ArcGIS Online FeatureServer | None | "Please do not re-distribute this record"; Idaho Code 74-120 | 403, no rules | Internal only (private) | Confirmed |
| [Nampa bike routes and pathways](https://www.arcgis.com/sharing/rest/content/items/1920988890154b77ba46c8bde9dac469) | City of Nampa | Current bike routes, pathways and pathway markers (Sep 2026); 2019–2021 plan layers | MapServer through a proxy; ArcGIS Online FeatureServers | None | Disclaimer ("reference purposes only"); credit City of Nampa | services7 403; proxy host no valid rules | Use | Corrected |
| [Ridge to Rivers condition reports](https://www.ridgetorivers.org/condition-reports/) | Ridge to Rivers partnership | Foothills trail condition and closure posts | HTML posts, indexed by the sitemap | None | City of Boise copyright: summarize, don't republish | `Allow: /` | Use | Corrected |
| **Crashes** | | | | | | | | |
| [COMPASS crash data, road-user types](https://swidrdc.org/arcgis/rest/services/COMPASSData/CrashData/FeatureServer) | COMPASS (from ITD records) | 174,038 crashes 2008–2025 with pedestrian and bike types; already built | Loaded monthly (`compass_crashes`) | None | Disclaimer; credit COMPASS; road-user types publishable (Oct 6) | 404 (already collected) | Use | Confirmed |
| [ITD crash units](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35) | ITD | Pedestrian, pedalcycle, scooter and moped units statewide, 2005–2023 | ArcGIS MapServer, 70,000 a query | None | No license; credit ITD | 404, no rules | Use | Confirmed |
| [NHTSA FARS](https://crashviewer.nhtsa.dot.gov/CrashAPI) | NHTSA | Every fatal crash since 1975, with pedestrian and bicyclist person types | Yearly national CSV zips, by hand | None | Public domain | static.nhtsa.gov 404; other hosts 403 to our client | Use | Confirmed |
| **OpenStreetMap, methods and benchmarks** | | | | | | | | |
| [OpenStreetMap active-transport tags](https://wiki.openstreetmap.org/wiki/Key:cycleway) | OpenStreetMap contributors (via Geofabrik) | Cycleways, paths, footways, crossings, bike parking and their tags, from the extract already on the server | A wider filter over the hand-downloaded extract | None | ODbL | Geofabrik disallows scripted downloads (we download by hand) | Use | Corrected |
| [Level of Traffic Stress method](https://transweb.sjsu.edu/research/Low-Stress-Bicycling-and-Network-Connectivity) | Mineta Transportation Institute; Peter Furth | The LTS 1–4 criteria we'd implement | Free PDFs | None | Method free to implement | Not applicable | Use | Confirmed |
| [PeopleForBikes Bicycle Network Analysis](https://github.com/PeopleForBikes/brokenspoke-analyzer) | PeopleForBikes | Connectivity scores from an analyzer we run on our own inputs; City Ratings | Docker, run by us | None | Analyzer MIT; City Ratings data terms not found ⚠️ | Allow all (both hosts) | Use | Confirmed |
| [EPA National Walkability Index and Smart Location Database](https://www.epa.gov/smartgrowth/smart-location-mapping) | US EPA | Walkability by block group (2021, on 2019 geography) | Zip or CSV, by hand | None | CC0 | edg.epa.gov 404; geodata.epa.gov disallows `/arcgis/` | Use | Corrected |
| [Census ACS commute mode](https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html) | US Census Bureau | Bike and walk commute shares by tract and block group (B08301) | API with a key, or tables by hand | Free key (none by hand) | Public domain; API terms apply | api.census.gov unknown (WAF page); data.census.gov and www2 allowed | Needs owner action | Confirmed |
| **Micromobility and crowdsourced data** | | | | | | | | |
| [Lime GBFS](https://data.lime.bike/robots.txt) | Lime | Live scooters and e-bikes; no public Boise feed | None | Partnership | Not reached | `Disallow: /` | Avoid | Confirmed |
| [Ride Report dashboard for Boise](https://public.ridereport.com/boise) | City of Boise, via Ride Report | Quarterly scooter and e-bike trips since Q2 2019 | Web dashboard; download by hand | None | No terms found | 404, no rules | Needs owner action | Confirmed |
| [Boise bike-share history](https://www.valleyregionaltransit.org/news/bike-share-vall-ebike-pilot-ends-october-31st/) | Valley Regional Transit | Boise GreenBike (2015–2020), the Vall-eBike pilot (2022), secure bike parking | News pages, by hand | None | Facts with a citation | Only `/wp-admin/` disallowed | Use | Corrected |
| [Strava Metro and heatmaps](https://metro.strava.com/) | Strava | Aggregated activity data for planners | Partnership | Partnership | Strava Metro Terms (not read); excluded by project rule | strava.com blocks ClaudeBot entirely | Avoid | Corrected |
| [BikeMaps.org](https://bikemaps.org/about/) | BikeMaps.org (UC Santa Barbara, Simon Fraser University) | Crowdsourced collisions, near misses, hazards, thefts | JSON endpoints disallowed | Unknown ⚠️ | Not stated | JSON endpoints disallowed | Avoid | Confirmed |

**Verdicts:** 13 use, 8 internal only, 3 need an owner action, 4 avoid.

## ACHD layers (Ada County)

### ACHD Official Bicycle Facility Network

Internal only · verified: confirmed · confidence high · effort S

- **Endpoint:** `gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Official_Bicycle_Facility_Network/FeatureServer/1`,
  listed in ACHD's open-data hub. A twin MapServer sits on
  maps.achdidaho.org (`GisData_Planning`); use the hub copy.
- **Contents:** 3,932 polylines, 1,080 mi. Per segment: `Street`, `City`,
  `Agency`, `FuncClass`, `Speed` and `SpeedField` (field-checked),
  `NoofLanes` and `TotalLanes`, `Volume` (a text field, not a numeric ADT),
  `Experience`, `ExistingType`. Per direction (`EBNB`, `WBSB`): facility
  direction, type and width, adjacent lane width, lane count, pavement edge,
  right turn, parking and its width, markings and their location, buffer
  type and width. Also `BMPLevel`, `BuiltBMPLevel`, `BMPStatus`; the
  Regional Low-Stress flags (`PartofRLSBikeway`, `BuiltRLSBikeway`,
  `RLSBikewayStatus`, `BkwyName`); `YrBuilt` (text), `YearAdded` (integer),
  `YearUpdated`, `FieldVerified`, `TotalPavement`, `TotalROW`,
  `MaintZones`; free-text `Comments` and `FieldNotes`; and an integer
  `LTS`.
- **ACHD's LTS** (reproduced Oct 7):

  | LTS | Segments | Miles |
  |---|---|---|
  | 1 | 1,249 | 260 |
  | 2 | 985 | 194 |
  | 3 | 650 | 152 |
  | 4 | 554 | 223 |
  | Blank | 494 | 251 |

- **Coverage:** Ada County only (ACHD's jurisdiction); nothing in Canyon
  County or the ring.
- **Access:** no key; JSON, GeoJSON or PBF; `maxRecordCount` 2,000, so two
  pages. The layer has no `editingInfo.lastEditDate`, so change checks use
  the hub's DCAT `modified` date or a content hash.
- **License and terms:** none. The DCAT license field holds a disclaimer:
  "general reference purposes only and should not be used for planning
  determinations". Copyright text: "Created by Ada County Highway District,
  2026." Internal use, credited; ask ACHD before republishing.
- **robots.txt:** gis.achdidaho.org returns 404 (an IIS page): no rules
  (re-checked Oct 7). The hub host has Crawl-delay 60 and doesn't disallow
  `/api/`.
- **Updates and size:** edited periodically (hub entry modified
  2026-05-05); check monthly by the DCAT date and skip unchanged versions.
  About 4k lines, under 10 MB as GeoJSON.
- **Use cases:** the official bike-facility layer for the cyclist's map;
  ACHD's own LTS as the Ada baseline for our LTS engine; inputs for our LTS
  (facility width, buffer, parking, lanes and speed per direction); a
  network-growth year slider, only after `YearAdded` and `YrBuilt` are
  checked against imagery (correction 3); spotting OpenStreetMap gaps where
  ACHD has a bike lane and OSM doesn't (hints only, never imported).
- **For:** everyday cyclists, bike advocates and planners, safety
  researchers, history buffs. **Needs:** layer system, the shared ArcGIS
  reader, evidence and review (LTS provenance, as `core.segment_lanes`
  keeps for lanes).
- **Risks:** the disclaimer rules out planning determinations, so label the
  LTS as ACHD's assessment. 494 segments (251 mi) have no LTS; that they're
  mostly off-street is unverified ⚠️. Field-checked speeds and lanes may
  disagree with `core.segment_lanes`: flag conflicts, don't overwrite.
  Don't publish `Comments` or `FieldNotes` verbatim.
- **Verification:** fields, `maxRecordCount`, formats and copyright
  confirmed from the layer metadata. One grouped statistics query
  reproduced 3,932 features, 1,080.3 mi and the LTS split exactly. The DCAT
  entry was modified 2026-05-05T21:18Z, with the disclaimer as its license.
  Not re-checked: the mileage per `ExistingType` class. New caveats:
  `YrBuilt` and `Volume` are text, the layer has no `lastEditDate`, and the
  free-text fields shouldn't be published.
- **Evidence:**
  [layer](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Official_Bicycle_Facility_Network/FeatureServer/1?f=json),
  one grouped LTS statistics query at `.../FeatureServer/1/query`,
  [hub DCAT feed](https://public-open-data-achd.hub.arcgis.com/api/feed/dcat-us/1.1.json),
  [robots.txt](https://gis.achdidaho.org/robots.txt),
  [hub robots.txt](https://public-open-data-achd.hub.arcgis.com/robots.txt),
  the arcgis.com search API (ACHD's organisation, bike titles).

### ACHD Master Bicycle Map: bike LTS 2023 and low-stress routes

Internal only · verified: confirmed · confidence high · effort S

- **Endpoint:** `services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer`
  (ACHD's ArcGIS Online organisation).
- **Contents:**

  | Layer | What | Last edited |
  |---|---|---|
  | 0 Master Bike Map Bike Levels | The master bike map | — |
  | 1 `Low_Stress_Routes` | `BkwyName`, `BkwyLength`, `Status`, `BikeProj`, `CNYear` (construction year) | 2026-03-24 |
  | 2 BLTS Segment Scores 2023 | 4,584 polylines: `Bike_LTS_AdaCounty` ("Updated LTS Score"), `LTS_Alta`, `aadt_field`, `lanes_field`, `speed_field`, `Bike_Facility_Width`, `OneWay`, `centerline_pres_field`, `PCI_Score`, `ExistingBikeType`, facility type, width, buffer type and width per direction, `FuncClass`, `Agency`, `ACHD_Owned` | 2025-12-12 |
  | 3 BLTS Intersection Scores 2023 | Polygons: `BLTS_Intersection_Alta`, most lanes crossed, highest posted speed, floating and non-floating bike-lane flags, enhanced-crossing, signalized and RRFB flags, right-turn bike lane per direction | 2025-12-12 |

  ACHD's "Bicycle and Pedestrian LTS" web map calls this the "Livable
  Street Performance Measure developed in 2023".
- **Coverage:** Ada County. Scored in 2023, edited Dec 2025 (low-stress
  routes Mar 2026).
- **Access:** public, no key; JSON, GeoJSON or PBF; `maxRecordCount` 1,000
  (five pages for the segments). `editingInfo.lastEditDate` allows cheap
  change checks.
- **License and terms:** none stated: the item's `licenseInfo` and the
  service's copyright are blank. Credit ACHD; internal until ACHD confirms.
- **robots.txt:** services2.arcgis.com answers 403 "Invalid URL"
  (re-checked Oct 7), and a 4xx means no rules under RFC 9309.
  www.arcgis.com's robots.txt has no `Disallow` lines.
- **Updates and size:** irregular (2023 scoring, edits Dec 2025 and Mar
  2026); check monthly by `lastEditDate`. 4,584 segments plus intersection
  polygons: a few MB.
- **Use cases:** ground truth for validating our own LTS engine in Ada (an
  agreement matrix by class); intersection-level stress, which segment-only
  LTS misses; AADT and centerline-presence inputs we don't otherwise have
  on local streets; pavement condition (PCI) for ride comfort.
- **For:** everyday cyclists, bike advocates and planners, parents (safe
  routes). **Needs:** layer system, the shared ArcGIS reader, evidence and
  review.
- **Risks:** a staff account owns the hosted service, so it could move or
  vanish: keep versions in `raw.record`. `Low_Stress_Routes` carries
  `created_user` and `last_edited_user` (staff accounts): drop them at
  ingest. Per-class counts weren't re-checked.
- **Verification:** the layer list, every named field, `maxRecordCount`
  1,000, the formats and the Dec 2025 edit dates confirmed; a count-only
  query gave 4,584. The item's `licenseInfo` is blank. Added by
  verification: the `Low_Stress_Routes` fields and its Mar 2026 edit date.
- **Evidence:**
  [service](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer?f=json),
  [layer 1](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer/1?f=json),
  [layer 2](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer/2?f=json),
  [layer 3](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer/3?f=json),
  [segment count](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Bicycle_Map/FeatureServer/2/query?where=1%3D1&returnCountOnly=true&f=json),
  web map item [a9dd0fcd…](https://www.arcgis.com/sharing/rest/content/items/a9dd0fcd76da47d2854c833511c50cd8?f=json)
  and [its data](https://www.arcgis.com/sharing/rest/content/items/a9dd0fcd76da47d2854c833511c50cd8/data?f=json),
  item [a0ee002f…](https://www.arcgis.com/sharing/rest/content/items/a0ee002f60864324b66ec578aa92f00a?f=json),
  [services2 robots.txt](https://services2.arcgis.com/robots.txt),
  [arcgis.com robots.txt](https://www.arcgis.com/robots.txt).

### ACHD Master Pedestrian Map: walking LTS 2023

Internal only · verified: corrected · confidence high · effort S

- **Endpoint:** `services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer`.
- **Contents:** layer 0 Master Pedestrian Map; layer 1
  `PLTS_Intersection_Alta_2023` (polygons: `PLTS_Intersection_Alta`, lanes,
  speed, signalized, enhanced-crossing, RRFB and PHB flags, `Lamp_Count`,
  `InaccessibleButton_flag`, `InaccessibleRamp_flag`, `Type`); layer 2
  `PLTS_Segment_Alta_2023` (34,771 polylines: `Alta_PLTS_Score_PerTables`,
  `Alta_PLTS_Score_NoSidewalks`, subscores for sidewalk presence, buffer and
  width or condition, `SidewalkSides`, `MAX_lanes_field`,
  `MIN_Sidewalk_Width`, `SidewalkBufferWidth`, `MIN_Bike_Facility_Width`,
  `MIN_ParkingLaneWidth`, `MIN_PlantingStripWidth`,
  `MIN_ACHDSidewalk_ADACategory`, `LowVolume_Flag`, `PostedSpeedLimit`,
  `FunctionalClass`, `ACHD_Owned`, `Miles`). Both layers last edited
  2026-03-18.
- **Coverage:** Ada County.
- **Access:** public, no key; `maxRecordCount` 1,000 (about 35 pages for
  the segments).
- **License and terms:** none stated on the service or the item. Credit
  ACHD; internal.
- **robots.txt:** services2.arcgis.com 403 (no rules), re-checked Oct 7.
- **Updates and size:** irregular (edited Mar 2026); check monthly by
  `lastEditDate`. 34,771 segments plus intersection polygons, roughly
  15–30 MB as GeoJSON ⚠️ (estimate).
- **Use cases:** a walking-stress map and pedestrian gap analysis; safe
  routes to school and to bus stops; planting-strip and buffer widths for
  the shade walk; intersection lighting (`Lamp_Count`) and inaccessible
  buttons and ramps for the accessibility view.
- **For:** pedestrians and wheelchair users, parents (safe routes), bike
  advocates and planners. **Needs:** layer system, the shared ArcGIS reader.
- **Risks:** two score variants (per the tables, and with no-sidewalk
  residential roads left unscored), so the display must say which it
  shows. A staff account owns the service.
- **Verification:** layers and segment fields confirmed. Corrected: the
  last edit is 2026-03-18 (the item was modified the same day), not
  2025-03-21. Counted 34,771 segments (the research hadn't counted them).
  Added the intersection fields the research missed (`PHB_flag`,
  `Lamp_Count`, the inaccessible button and ramp flags).
- **Evidence:**
  [service](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer?f=json),
  [layer 1](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer/1?f=json),
  [layer 2](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer/2?f=json),
  [segment count](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Master_Pedestrian_Map/FeatureServer/2/query?where=1%3D1&returnCountOnly=true&f=json),
  [LTS web map data](https://www.arcgis.com/sharing/rest/content/items/a9dd0fcd76da47d2854c833511c50cd8/data?f=json),
  the arcgis.com search API (ACHD's organisation, "Master Pedestrian").

### ACHD sidewalks, curb ramps and Five-Year Plan sidewalk projects

Internal only · verified: corrected · confidence high · effort S

- **Endpoints:** `gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Sidewalks/FeatureServer/1`,
  `.../ArcGIS_Hub/Ped_Ramps/FeatureServer/1` and
  `.../ArcGIS_Hub/FYP_Sidewalk_Projects/FeatureServer/1`, all in ACHD's
  open-data hub.
- **Contents:**
  - **Sidewalks:** 45,047 polylines with `Width`, `Material`, `Buffer`
    (TRUE, FALSE or MEANDERING), `Category` (coded 1–4; meanings
    undocumented ⚠️), `Year_CategoryUpdated`, `Year_Mapped`,
    `Year_Assessed`, `Proj_Type` (ACHD project, subdivision, aerial
    inventory, inventory, partner agency and others), `Proj_Description`,
    `Notes`, `AssetID`, `Current_Priority`, `Current_Rank`, `MaintArea`,
    `Location` (A–E, Z), and created and edited dates. By category
    (reproduced Oct 7): 1 = 1,361; 2 = 5,897; 3 = 3,633; 4 = 34,156.
  - **Ped_Ramps:** points with `Ramp_Count`, `Category` coded 1–5,
    `Year_Assessed`, priority and rank.
  - **FYP_Sidewalk_Projects:** polygons with `ProjectName`, `ProjDesc`,
    design, right-of-way and construction years, `Program`,
    `TotalProjectCost` and `PrjMgr` (a staff name).
- **Coverage:** ACHD right-of-way in Ada County.
- **Access:** no key; JSON, GeoJSON or PBF; `maxRecordCount` 2,000 (about
  23 pages for sidewalks). Sidewalks carry `last_edited_date`, so its
  maximum plus a count works as a change check.
- **License and terms:** the DCAT license field is the disclaimer
  ("general reference purposes only"); copyright "Created by Ada County
  Highway District, 2026." Internal, credited.
- **robots.txt:** gis.achdidaho.org 404: no rules (re-checked Oct 7).
- **Updates and size:** hub entries modified 2026-05-05 (sidewalks) and
  2026-05-07 (ramps and projects); check monthly. Sidewalks are 45k lines,
  20–40 MB as GeoJSON; ramps not counted ⚠️.
- **Use cases:** sidewalk presence, width and buffer for walking stress and
  gaps; curb-ramp condition for an accessibility view (after ACHD explains
  the codes); planned sidewalk projects for before and after, and a "gap
  being fixed" status.
- **For:** pedestrians and wheelchair users, parents (safe routes), bike
  advocates and planners. **Needs:** layer system, the shared ArcGIS reader.
- **Risks:** the category codes aren't explained, so ask ACHD before
  labelling any as good or poor. Sidewalks on private or state land may be
  missing. Drop `PrjMgr` and the free-text `Notes` from anything
  published.
- **Verification:** the sidewalk total and per-category counts reproduced
  exactly; fields, `maxRecordCount` and the disclaimer confirmed.
  Corrected: ramp categories run 1–5, not 1–4, so the question to ACHD
  covers both code sets; the sidewalk projects are polygons and carry
  staff names.
- **Evidence:**
  [sidewalks](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Sidewalks/FeatureServer/1?f=json),
  one grouped category count at `.../Sidewalks/FeatureServer/1/query`,
  [ramps](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/Ped_Ramps/FeatureServer/1?f=json),
  [sidewalk projects](https://gis.achdidaho.org/server/rest/services/ArcGIS_Hub/FYP_Sidewalk_Projects/FeatureServer/1?f=json),
  [hub DCAT feed](https://public-open-data-achd.hub.arcgis.com/api/feed/dcat-us/1.1.json),
  [robots.txt](https://gis.achdidaho.org/robots.txt).

### ACHD ArcGIS Online active-transport layers

Internal only · verified: corrected · confidence medium · effort M

Sidewalk gaps, enhanced crossings, micro-paths, safe-routes walking layers
and school zones, found through the arcgis.com search API in ACHD's
organisation (`9rTo9NcUHIKASKwi`).

- **Endpoints and contents:**

  | Service | Dated | What |
  |---|---|---|
  | [`Sidewalk_Gap_Map_WFL1`](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Sidewalk_Gap_Map_WFL1/FeatureServer) | Dec 2023 | ADA push buttons (safety crossings), pedestrian ramps, public sidewalks, sidewalk on both, one or no sides, major and minor roadways, chip-seal zones |
  | [`Enhanced_Ped_Crossings_For_PAGEdits_WFL1`](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Enhanced_Ped_Crossings_For_PAGEdits_WFL1/FeatureServer) | May 2025 | Completed and programmed crossings, `NPAColored_2022`; layer 0 `PAG_Comments` holds advisory-group comments with a `PAGMember` name field: **skip it** |
  | [`Micro_Pathways`](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Micro_Pathways/FeatureServer) and Pathways | Feb 2023 | From COMPASS |
  | [`Valley_Regional_Transit_SRTS_Walking3`](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Valley_Regional_Transit_SRTS_Walking3/FeatureServer) | Mar 2025 | Pedestrian and bike LTS at intersections, ramps, sidewalks, Five-Year Plan points, lines and polygons |
  | [Boise school "Bus and NonBus Zones"](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Boise_Elementary_School_Bus_and_NonBus_Zones/FeatureServer/18) | Dec 2023 | Walk and bus zones for Boise elementary, junior and senior high schools: the only walk zones found |
  | [West Ada](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/West_Ada_Elementary_School_School_District/FeatureServer/23) and [Kuna](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Kuna_Elementary_School_District/FeatureServer/29) school layers | — | Attendance areas (`TITLE`, `Capacity`, `ELEM_DESC`), not walk zones |
  | [`Walk_Bike_Ride_Web_Map`](https://services2.arcgis.com/9rTo9NcUHIKASKwi/arcgis/rest/services/Walk_Bike_Ride_Web_Map/FeatureServer) | Jun 2025 | Neighbourhood walk-bike-ride maps for Collister, Pierce Park, Northwest and Sunset |
  | "LTS Sidewalk Presence" and "LTS Street Trees" on maps.achdidaho.org (`GisData_Planning`) | — | Sidewalk presence and street trees used in the LTS work |

  Also found: `ACHD_LTS_Review_WFL1`, Bike Air and Repair Stations Copy,
  Bike Shops, School Flasher Signal.
- **Coverage:** Ada County; walk and bus zones for the Boise district only.
- **Access:** public ArcGIS Online FeatureServers, no key,
  `maxRecordCount` 2,000. The two LTS layers are on maps.achdidaho.org.
- **License and terms:** `licenseInfo` mostly blank. Boise's school zones:
  "Data is not intended for use in commercial transactions". Internal,
  credited.
- **robots.txt:** services2.arcgis.com 403 (no rules);
  maps.achdidaho.org 404 (no rules); www.arcgis.com has no `Disallow`
  lines. All checked Oct 7.
- **Updates and size:** irregular; check monthly or on demand. Each under
  10 MB.
- **Use cases:** sidewalk gaps by road; crossing opportunities (RRFBs,
  pedestrian hybrid beacons) for the walking and biking routers; micro-paths
  that OpenStreetMap often misses; safe routes to school (Boise's walk zones
  overlaid with high-stress crossings); ACHD's street-tree layer for the
  shade walk.
- **For:** parents (safe routes), pedestrians and wheelchair users, everyday
  cyclists, bike advocates and planners, gardeners. **Needs:** layer
  system, the shared ArcGIS reader, places and search (schools).
- **Risks:** many are working layers owned by staff accounts and may change
  without notice. Skip `PAG_Comments` and any public-comment layer; drop
  creator and editor fields. Show school zones as infrastructure only,
  never tied to students. The Boise zones' description says the area
  within 1.5 miles of a school is normally a non-busing area ⚠️
  (paraphrased, not quoted).
- **Verification:** layer lists and dates confirmed. Corrected: the West
  Ada and Kuna layers are attendance areas, so walk zones exist for Boise
  only; the "suggested new crossings" the research found are the
  `PAG_Comments` layer, which must not be collected; a "Bikeways Public
  Comments" item wasn't found again. Added the LTS street-tree and
  sidewalk-presence layers and the walk-bike-ride maps.
- **Evidence:** the arcgis.com search API (ACHD's organisation; titles
  with pedestrian, sidewalk, SRTS, LTS, zones, school, walk, bike); the
  service links in the table above (each read as `?f=json`, with
  `Enhanced_Ped_Crossings_For_PAGEdits_WFL1/FeatureServer/0` for the
  comments layer); item
  [3806b0fa…](https://www.arcgis.com/sharing/rest/content/items/3806b0faec994fc6954d5fdfa858c4bf?f=json);
  [maps.achdidaho.org robots.txt](https://maps.achdidaho.org/robots.txt).

## COMPASS layers (Ada and Canyon)

### COMPASS ExistingBikeAndPed and Bike/Walk COMPASS

Internal only · verified: confirmed · confidence high · effort S

- **Endpoint:** `swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer`;
  related `swidrdc.org/arcgis/rest/services/BikeAndPed_RegionalRoutes/FeatureServer`
  (layers 5 `RegionalRoutes_2025` and 6 `RegionalRoutes_2025_Seg`).
- **Contents:**
  - 0 Existing Pathway.
  - 1 Existing Bike Facility: 2,445 per
    [ch. 8 §8.9](../08-data-inventory.md#89-second-source-review-oct-6-2026);
    types Bike Friendly Route, Bike Lane, Bikeway, Sharrow and Shoulder
    Bikeway; fields `juristype`, `agency`, `year`, `date`, `surface`,
    `direction`, `pmid`, `linearref`. COMPASS itself calls `year`, `date`,
    `surface` and `direction` "generally unreliable/not updated".
  - 2 Existing Sidewalk: 57,166 per ch. 8.
  - 3 Permanent Counter Locations: 28 rows (next entry).
  - 4 `Pathways_Master`: a routable walking network for both counties (a
    `County` field), typed as campus pathway, bike or pedestrian bridge or
    underpass, crosswalk, driveway, intersection, high- and low-volume
    crossing, micropath connection, non-walkable road, public multi-use
    pathway, sidewalk and more. `f_elev` and `t_elev` are grade-separation
    z-levels (10 at grade, 5 underpass, 20 overpass), not elevations;
    `fwalktime` and `twalktime` are length × 24; also `sides_walk`,
    `width`, `surface`, `piclink`.
- **Coverage:** Ada and Canyon counties: the only bike-facility and
  sidewalk layer found that covers Canyon County. Not the ring.
- **Access:** no key; `maxRecordCount` 2,000; JSON, GeoJSON or PBF. Native
  coordinates are a custom NAD83 Transverse Mercator in US feet, so request
  `outSR=4326`. No `lastEditDate` in the layer metadata.
- **License and terms:** COMPASS's hub items carry a disclaimer only;
  layers that exist only on swidrdc.org have no terms. Internal until
  COMPASS answers; credit COMPASS and its member agencies.
- **robots.txt:** swidrdc.org returns 404 (an IIS page): no rules
  (re-checked Oct 7).
- **Updates and size:** edited 2023–2025; check monthly by count and the
  latest `last_edited_date`. Sidewalks are about 57k lines; with the
  pathway network, 30–60 MB.
- **Use cases:** Canyon County's bike facilities and sidewalks; a routable
  pedestrian network for walksheds (the z-levels keep bridges from joining
  the streets below); regional priority routes for gap analysis; `pmid`
  links to COMPASS's crashes, counts and travel model.
- **For:** everyday cyclists, pedestrians and wheelchair users, bike
  advocates and planners, parents (safe routes). **Needs:** layer system,
  the shared ArcGIS reader, the regular OpenStreetMap load (to reconcile).
- **Risks:** `piclink` points to photos: don't fetch them in bulk. Drop
  `created_user` and `last_edited_user`. Add these layers to the pending
  question to COMPASS about republishing.
- **Verification:** the layer list, fields, `maxRecordCount`, the US-feet
  projection and the two-county coverage confirmed from metadata and field
  descriptions. Clarified: `f_elev` and `t_elev` are z-levels, and COMPASS
  flags its own year, date, surface and direction fields as unreliable.
  The sidewalk and bike-facility counts come from ch. 8 and weren't
  re-counted.
- **Evidence:**
  [services](https://swidrdc.org/arcgis/rest/services?f=json),
  [COMPASSData folder](https://swidrdc.org/arcgis/rest/services/COMPASSData?f=json),
  [service](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer?f=json),
  [layer 1](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer/1?f=json),
  [layer 3](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer/3?f=json),
  [layer 4](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer/4?f=json),
  [regional routes](https://swidrdc.org/arcgis/rest/services/BikeAndPed_RegionalRoutes/FeatureServer?f=json),
  [robots.txt](https://swidrdc.org/robots.txt).

### COMPASS bicycle and pedestrian counters

Needs owner action · verified: corrected · confidence high · effort M

- **Endpoints:** the [counter data page](https://compassidaho.org/bicycle-and-pedestrian-counter-data/)
  ("Updated on April 9, 2026") and `ExistingBikeAndPed/FeatureServer/3`
  for the locations.
- **Contents:** automatic bike and pedestrian counting since fall 2015.
  Layer 3 has 28 rows:
  - 16 COMPASS-owned "EcoCounter Multi" sites. Boise: Eckert Bridge, Anne
    Frank Memorial, Friendship Bridge, Trestle Bridge. Eagle: four
    Greenbelt sites, including HW44 and Merrill Park. Garden City:
    Riverside Park. Meridian: Tully Park. Kuna: Indian Creek Greenbelt.
    Caldwell: Indian Creek Bridge and the Caldwell Greenbelt. Nampa:
    Wilson, Stoddard and Library Square downtown.
  - 12 ACHD rows: the Locust Grove and Eagle Road multi-use pathways (each
    listed twice), the Shamrock and Cassia bikeways, Capitol Blvd and the
    Donna Larson Pathway; 4 are marked "Future" (Anderson Street, Federal
    Way at TK Ave, Meridian Speedway Pathway, Highlander Road).

  The page has annual PDF reports for 2020–2023 at 19 sites (adding Cesar
  Chavez Ln and Julia Davis East and West in 2023; Caldwell's Indian Creek
  counter counts pedestrians only) and notes on counter failures. Earlier
  years' reports are available on request.
- **Coverage:** the Greenbelt and pathways in Ada and Canyon; ACHD's
  on-street bikeway counters at a few sites. Not the ring.
- **Access:** the locations by one small query; counts from the PDFs by
  hand; earlier reports, and any hourly data, by request to COMPASS (an
  owner action). The page doesn't mention hourly data ⚠️, and no public
  Eco-Visio page was checked ⚠️.
- **License and terms:** the page says the counts "are to be used for
  general planning purposes only". Requested data would come with
  COMPASS's terms.
- **robots.txt:** compassidaho.org: `User-agent: *` with an empty
  `Disallow` and Crawl-delay 60 (re-checked Oct 7). swidrdc.org 404: no
  rules.
- **Updates and size:** annual reports (the latest is 2023 as of Oct
  2026); requested data as often as COMPASS agrees. Hourly data for about
  20 sites over 10 years would be under 50 MB.
- **Use cases:** Greenbelt and pathway volumes by hour, weekday, season and
  weather (as readings), if COMPASS shares hourly data; exposure for
  pathway crash rates; how cycling responds to weather (with 511's
  road-weather readings and IEM); before and after where a counter exists.
- **For:** Greenbelt regulars, bike advocates and planners, safety
  researchers, weather watchers. **Needs:** the readings contract and
  time-series card, full replay.
- **Risks:** aggregate counts, so no privacy issue. Counter failures (listed
  on the page) mean gaps must be flagged, not filled. PDF extraction is
  brittle: ask COMPASS for CSV.
- **Verification:** corrected: 28 location rows, not 27 (16 COMPASS and
  12 ACHD, with two ACHD names duplicated and 4 marked "Future"). The 19
  report sites for 2023 and the Apr 9, 2026 update confirmed. The page
  offers earlier years' reports on request but never says hourly data
  exists, so that's an assumption to put to COMPASS. The Eco-Visio check
  is still not done.
- **Evidence:** one attribute-only query at
  `swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer/3/query`
  (28 rows),
  [counter data page](https://compassidaho.org/bicycle-and-pedestrian-counter-data/),
  [robots.txt](https://compassidaho.org/robots.txt).

### COMPASS Walkability web map and Data Bike

Internal only · verified: confirmed · confidence medium · effort S

- **Endpoint:** `swidrdc.org/arcgis/rest/services/COMPASSData/WalkabilityWebmap/FeatureServer`;
  the [Data Bike page](https://compassidaho.org/compass-data-bike/).
- **Contents:** `WalkabilityWebmap` layers: 0 `GapMarkers`, 1–3
  `Elem`/`Mid`/`High_Walkable_FINAL`, 4 `PublicSchool_walkable_mi`, 5
  `VRTstops_walkable_mi`, 6 `GapMarker_edits`, 7 `WestAdaWalksheds_TEMP`.
  Related services in `COMPASSData`: `CaldwellSchoolWalkability` and
  `EquityIndex`. The COMPASS Data Bike (an FHWA Technology Transfer grant
  in 2018; in use since 2020) records pathway roughness and photos on
  off-street facilities in Ada and Canyon; reports are a 2020 pilot and a
  "2023 Data Bike Report" (file dated June 2024). Page updated June 22,
  2026.
- **Coverage:** Ada and Canyon; the Data Bike only on chosen pathway
  segments.
- **Access:** the web map's layers by FeatureServer, no key,
  `maxRecordCount` 2,000. Data Bike: PDF reports only; data by request (an
  owner action).
- **License and terms:** no terms on the swidrdc.org-only layers: internal
  until COMPASS answers. Data Bike data on request.
- **robots.txt:** swidrdc.org 404 (no rules); compassidaho.org Crawl-delay
  60. Both re-checked Oct 7.
- **Updates and size:** irregular; small.
- **Use cases:** school and bus-stop walksheds; COMPASS's own sidewalk-gap
  markers to compare with ACHD's; pathway smoothness for a ride-comfort
  layer (Data Bike, if shared); equity weighting in gap ranking.
- **For:** parents (safe routes), pedestrians and wheelchair users, bike
  advocates and planners, Greenbelt regulars. **Needs:** layer system.
- **Risks:** layers named `TEMP` or `edits` may be working copies.
- **Verification:** the layer list and related services confirmed. The
  Data Bike facts confirmed from the page; the 2023 report's file name shows
  June 2024 publication. No Data Bike download exists.
- **Evidence:**
  [COMPASSData folder](https://swidrdc.org/arcgis/rest/services/COMPASSData?f=json),
  [web map service](https://swidrdc.org/arcgis/rest/services/COMPASSData/WalkabilityWebmap/FeatureServer?f=json),
  [Data Bike page](https://compassidaho.org/compass-data-bike/).

## City layers

### City of Boise Pathways Master Plan

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Pathways_Master_Plan/FeatureServer`
  (the City's ArcGIS Online organisation; analysis by Alta Planning +
  Design).
- **Contents:** one layer, "Boise Pathways Master Plan": existing and
  proposed paved, two-way, non-motorized pathways (10 ft minimum, 8 ft where
  constrained), per the item description. The mileage and project counts
  (about 50 mi existing, 112 mi proposed, over 110 projects) weren't
  re-checked ⚠️. Companion services (Jan 2025): `ExistingPathways`,
  `NaturalSurfaceTrails`, `ProposedPathways`,
  `Request_ACHD_LowStressNetwork_GapClose`. Main item modified 2026-10-05.
- **Coverage:** City of Boise.
- **Access:** no key; `maxRecordCount` 2,000.
- **License and terms:** a City disclaimer only (no warranty; "will change
  over time without notice"); no redistribution limit. Credit "City of
  Boise".
- **robots.txt:** services1.arcgis.com 403 (no rules), re-checked Oct 7.
  opendata.cityofboise.org has Crawl-delay 60 but isn't needed.
- **Updates and size:** updated Oct 2026; check monthly. Under 5 MB.
- **Use cases:** the pathways the cyclist's and walker's routers need;
  planned pathways and gap closures for "what's coming"; gap analysis
  against ACHD's network.
- **For:** everyday cyclists, Greenbelt regulars, bike advocates and
  planners. **Needs:** layer system, the shared ArcGIS reader.
- **Risks:** proposed alignments are plans, not built routes, so the
  router must exclude them.
- **Verification:** the item, its owner (the City's GIS account), the
  modified date, the disclaimer, the description and the companion layers
  confirmed. The mileage figures were in a truncated part of the
  description and weren't re-checked.
- **Evidence:**
  [item](https://www.arcgis.com/sharing/rest/content/items/9668fe460ab143a6b00a53dcfddf14de?f=json),
  [service](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Pathways_Master_Plan/FeatureServer?f=json),
  the arcgis.com search API (the City's organisation; greenbelt, pathway,
  bike, trail, tree),
  [services1 robots.txt](https://services1.arcgis.com/robots.txt),
  [open-data robots.txt](https://opendata.cityofboise.org/robots.txt).

### City of Boise Greenbelt closures

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer/0`.
- **Contents:** layer `Greenbelt_Construction` (polylines): `LOCATION`,
  `PROJECT`, `WORK_DESCRIPTION`, `CONSTRUCTION_SEASON`,
  `CONSTRUCTION_UPDATES`, `RIVER_MILE`, `GREENBELT_MILE`, `LATITUDE` and
  `LONGITUDE` (text), `STATUS`. No start or end dates. Last edited
  2026-09-10.
- **Coverage:** Boise's section of the Greenbelt only (not Eagle, Garden
  City or Caldwell).
- **Access:** a FeatureServer view, no key; tiny.
  `editingInfo.lastEditDate` allows a cheap change check before each fetch.
- **License and terms:** a City disclaimer only; credit "City of Boise-
  Parks and Recreation".
- **robots.txt:** services1.arcgis.com 403 (no rules), re-checked Oct 7.
- **Updates and size:** edited as needed; check `lastEditDate` hourly and
  fetch only on a change. Kilobytes; versions in `raw.record`.
- **Use cases:** live Greenbelt closures and detours as lifecycle events
  (first and last seen are ours); closures in the Valley Feed; with river
  flows from the water plugin, high-water underpass closures.
- **For:** Greenbelt regulars, everyday cyclists. **Needs:** the
  lifecycles contract (`evt.event`), the Valley Feed.
- **Risks:** inactive rows linger and `STATUS` is flipped by hand, so
  lifecycle timing is only as good as our polling and the City's edits. A
  staff account owns the view, so it may move.
- **Verification:** fields, the Sep 10 edit, the disclaimer and the credit
  confirmed. The item's own metadata was last modified 2025-01-24.
- **Evidence:**
  [item](https://www.arcgis.com/sharing/rest/content/items/941ed66cc3b14c9abc85ac26b64694e1?f=json),
  [layer](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer/0?f=json).

### City of Boise Greenbelt markers, repair stations, trees and trails

Use · verified: corrected · confidence medium · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/GreenbeltDOTSMileMarkers/FeatureServer`
  and sibling services in the City's organisation.
- **Contents:**
  - Greenbelt DOTS milepost markers (Oct 2026).
  - Fire GIS 1/10-mile markers, titled Barber Park to Ann Morrison Park but
    described as Lucky Peak Dam to Eagle (Jan 2026).
  - Bike air and repair stations.
  - Parks and Recreation managed park and street trees (two point sets).
  - Urban and Foothills Ridge to Rivers trails
    (`Boise_Parks_Trails_Open_Data`).
  - Greenbelt user-location map sites; Parks and Recreation trailheads.
  - Also found by verification: the Tree Canopy Study's land-cover and
    canopy-change tile services (2024 imagery, published 2025).
- **Coverage:** City of Boise (the Greenbelt markers reach Eagle).
- **Access:** FeatureServers, no key; the canopy layers are cached tile
  MapServers on tiles.arcgis.com.
- **License and terms:** the City disclaimer on most. The fire-GIS markers
  may be redistributed unaltered with the City's full metadata, or altered
  with the City of Boise referenced as the source.
- **robots.txt:** services1.arcgis.com 403 (no rules), re-checked Oct 7.
  tiles.arcgis.com not checked ⚠️.
- **Updates and size:** check monthly. Small; street trees may be tens of
  thousands of points ⚠️.
- **Use cases:** finding yourself on the Greenbelt (search by milepost);
  repair stations on the cyclist's map; street-tree and canopy shade along
  walking routes (with gardening and sky).
- **For:** Greenbelt regulars, everyday cyclists, pedestrians and wheelchair
  users, gardeners. **Needs:** places and search, layer system.
- **Risks:** skip the "City of Trees Challenge" layers (community-planted
  trees on secured or separate services, pointing at private homes). The
  street-tree count wasn't checked.
- **Verification:** items and dates confirmed. Corrected: the fire-GIS
  markers' redistribution terms are now read (metadata or source credit),
  and their description covers Lucky Peak Dam to Eagle. Added the canopy
  layers.
- **Evidence:** the arcgis.com search API (the City's organisation;
  greenbelt, pathway, bike, trail, tree, DOTS), items
  [793ee45f…](https://www.arcgis.com/sharing/rest/content/items/793ee45fab334a4ab40123bfc2c86cc6?f=json)
  and
  [61e4dc96…](https://www.arcgis.com/sharing/rest/content/items/61e4dc96bc0745ecb42c3f3892728bd6?f=json).

### Boise's copy of ACHD's Regional Low-Stress Bikeways (avoid)

Avoid · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/ACHD_RegionalLowStress/FeatureServer`.
- **Contents:** ACHD's Regional Low-Stress Bikeway Network (adopted with the
  2018 Roadways to Bikeways update), as used in Boise's Pathways Master
  Plan story map. Ada County; static since Jan 2025.
- **License and terms:** the item's terms say it is "not to be shared
  beyond those with whom ACHD has provided" it; requests go to ACHD
  Planning and Programming.
- **robots.txt:** services1.arcgis.com 403 (no rules), but being publicly
  readable doesn't override the item's own terms.
- **Instead:** use ACHD's public layers: `PartofRLSBikeway` in the Official
  Bicycle Facility Network, and `Low_Stress_Routes` (layer 1 of the Master
  Bicycle Map).
- **Verification:** the license text read in full; it matches. Modified
  2025-01-24.
- **Evidence:**
  [item](https://www.arcgis.com/sharing/rest/content/items/b10f49d12f97407796643136d021fa24?f=json).

### City of Meridian Pathways Network

Internal only (private schema) · verified: confirmed · confidence high ·
effort S

- **Endpoint:** `services1.arcgis.com/AutSHdEbRDZToajo/arcgis/rest/services/Meridian_Pathways_Network/FeatureServer`.
- **Contents:** existing pathways and micro-paths, plus planned pathways
  adopted in Meridian's Pathways Master Plan, largely along canals, with a
  20–50-year horizon. Item modified 2026-10-06.
- **Coverage:** City of Meridian.
- **Access:** no key.
- **License and terms:** "Please do not re-distribute this record"; also
  Idaho Code 74-120 (no use for marketing or mailing lists).
- **robots.txt:** services1.arcgis.com 403 (no rules), re-checked Oct 7.
- **Updates and size:** check monthly; small.
- **Use cases:** Meridian pathways for routing and gap analysis, shown only
  to the owner; published outputs use aggregates or OpenStreetMap.
- **For:** everyday cyclists, bike advocates and planners. **Needs:**
  private plugins (a private schema, never tiled for others;
  [ch. 15 §15.3](../15-plugins.md#153-private-plugins)).
- **Risks:** canal-side paths may sit on irrigation-district easements that
  aren't open to the public: check before routing on them.
- **Verification:** the license read in full: the no-redistribution
  sentence and Idaho Code 74-120 are there. Modified 2026-10-06.
- **Evidence:**
  [item](https://www.arcgis.com/sharing/rest/content/items/e3a55ac15b994f78a0e9d16959711b90?f=json),
  [robots.txt](https://services1.arcgis.com/robots.txt).

### City of Nampa bike routes and pathways

Use · verified: corrected · confidence medium · effort S

- **Endpoint:** the current layers are item
  [1920988890154b77ba46c8bde9dac469](https://www.arcgis.com/sharing/rest/content/items/1920988890154b77ba46c8bde9dac469?f=json),
  served through a utility.arcgis.com proxy to the City's `NampaOpenData`
  MapServer; the 2021 layers are ArcGIS Online FeatureServers on
  services7.arcgis.com.
- **Contents:** current: "Bike Routes & Pathways" (`NampaOpenData` layer
  23: bike lanes, buffered and separated lanes, bike boulevards, sidepaths
  and more) and "Pathway Markers" (layer 24), both modified 2026-09-02.
  Older plan layers (Sep 2021): `Existing_BikeFacilities`,
  `Proposed_BikeFacilities_2019`, `Existing_Pathways_export`,
  `Proposed_Enhanced_Crossings`. A consultant's "Bicycle and Pedestrian
  Network Web_WFL1" (Apr 2026; no license text, treat it as a draft). Also
  "BikePed PublicInput_Pts" (public comments: skip).
- **Coverage:** City of Nampa.
- **Access:** no key.
- **License and terms:** a disclaimer ("prepared for reference purposes
  only"); no redistribution limit. Credit the City of Nampa.
- **robots.txt:** services7.arcgis.com 403 (no rules).
  utility.arcgis.com's robots.txt redirects to an HTML page on
  www.arcgis.com (no valid rules). Checked Oct 7.
- **Updates and size:** the current layer was edited Sep 2026; check
  monthly. Small.
- **Use cases:** Canyon County bike facilities to check against COMPASS and
  OpenStreetMap; Nampa's pathway markers for search.
- **For:** everyday cyclists, bike advocates and planners. **Needs:**
  layer system.
- **Risks:** proxy URLs can change, so find the direct `NampaOpenData`
  server if it's public. Skip the public-input points.
- **Verification:** the 2021 layers and the disclaimer are as stated, but
  "stale, static since 2021" was wrong: Nampa publishes a current Bike
  Routes & Pathways layer (Sep 2026), and the entry now points to it.
- **Evidence:** items
  [e1ddec03…](https://www.arcgis.com/sharing/rest/content/items/e1ddec03b58f43aa9868b00a6435ffd6?f=json),
  [19209888…](https://www.arcgis.com/sharing/rest/content/items/1920988890154b77ba46c8bde9dac469?f=json)
  and
  [48c930a6…](https://www.arcgis.com/sharing/rest/content/items/48c930a614a8473780b8bfcd791dcc7f?f=json),
  the arcgis.com search API (the City's organisation; bike, pathway,
  trail), [services7 robots.txt](https://services7.arcgis.com/robots.txt),
  [utility robots.txt](https://utility.arcgis.com/robots.txt).

### Ridge to Rivers trail condition reports

Use (owned by the trails theme) · verified: corrected · confidence medium ·
effort M

- **Endpoint:** [condition reports](https://www.ridgetorivers.org/condition-reports/)
  and [trail conditions](https://www.ridgetorivers.org/trail-conditions/);
  the [sitemap](https://www.ridgetorivers.org/sitemapxml) is the usable
  index.
- **Contents:** narrative reports on muddy or closed Foothills trails, plus
  closure updates: 157 report URLs in the sitemap. Slugs such as
  `october-2-weekend-trail-report` carry no year. Footer: "2026 City of
  Boise. All rights reserved."
- **Coverage:** the Boise Foothills.
- **Access:** HTML posts; the listing renders in the browser, so poll the
  sitemap (with `lastmod`) gently. Trail lines are on the City's ArcGIS
  (`Boise_Parks_Trails_Open_Data`, above).
- **License and terms:** City of Boise copyright on the text; Terms of Use
  linked but not read. Summarize the status; don't republish the text.
- **robots.txt:** `User-agent: *` `Allow: /` (re-checked Oct 7).
- **Updates and size:** weekly "weekend trail reports" in the dry season;
  near-daily in wet and winter months (for example, daily Dec 5–14). Tiny.
- **Use cases:** mountain-bike trail status next to the urban bike network.
- **For:** mountain bikers and hikers. **Needs:** the lifecycles contract,
  the Valley Feed.
- **Risks:** narrative text needs parsing and is copyrighted, so leave it to
  the trails theme. Report dates must come from the post page, not the
  slug.
- **Verification:** both URLs answer 200. Corrected the cadence (seasonal:
  weekly to near-daily, not "weekly-ish") and the index (the sitemap, since
  the list page renders client-side and slugs lack years).
- **Evidence:** [robots.txt](https://www.ridgetorivers.org/robots.txt), the
  three pages linked above.

## Crashes

### COMPASS crash data: road-user types (already built)

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `swidrdc.org/arcgis/rest/services/COMPASSData/CrashData/FeatureServer`,
  loaded by the `safety` plugin's `compass_crashes` source every 30 days.
- **Contents:** 174,038 crashes, 2008–2025. `obs.crash.unit_types` is
  built from `restricted.crash_unit`. High-injury segments carry
  `pedestrian_event_sum`, `pedalcycle_event_sum`, fatal and serious
  pedestrian and pedalcycle events, `non_motorized_sum` and
  `bikefacility_type`. COMPASS's `Signalized_Intersections` adds
  pedestrian and bike crashes within 250 ft, plus `LPI_Status` and `APS`
  (loaded by `compass_signals` as `lpi` and `aps`).
- **Coverage:** Ada and Canyon, 2008–2025.
- **License and terms:** a disclaimer; credit COMPASS. Owner decision of
  Oct 6 ([DECISIONS](../DECISIONS.md)): road-user types may be published;
  people stay in `restricted`; aggregates only.
- **robots.txt:** not applicable: already collected under that decision
  (swidrdc.org 404, re-checked Oct 7).
- **Updates and size:** monthly (existing); already loaded.
- **Use cases:** a bike and pedestrian crash heatmap (aggregated); crashes
  against LTS class; crashes in the dark against street lighting; before
  and after for new bikeways.
- **For:** safety researchers, bike advocates and planners, everyday
  cyclists. **Needs:** layer system, full replay (year slider).
- **Risks:** person-level fields stay restricted. Show locations aggregated
  (hex or segment), never single pedestrian points with dates.
- **Verification:** checked against the repo: 174,038 points 2008–2025,
  the 30-day schedule, the `unit_types` update, the high-injury field names
  including `bikefacility_type`, and `LPI_Status` and `APS` loaded; the
  250 ft crash fields are described in ch. 8. The Oct 6 decision text
  matches.
- **Evidence:**
  [`compass_crashes.py`](../../plugins/safety/ingest/sources/compass_crashes.py),
  [`compass_signals.py`](../../plugins/intersections/ingest/sources/compass_signals.py),
  [ch. 8 §8.9](../08-data-inventory.md#89-second-source-review-oct-6-2026),
  [DECISIONS](../DECISIONS.md) (Oct 6).

### ITD crash units: pedestrian and pedalcycle

Use · verified: confirmed · confidence medium · effort S

- **Endpoint:** `gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35`
  ("Crash Unit 2005 to Present", which in practice ends at 2023); yearly
  unit layers too (75 = 2023). Already in [SOURCES](../SOURCES.md) as "ITD
  crash points" (not started).
- **Contents:** statewide crash, person and unit layers, 2005–2023 (66
  layers). Unit fields: `Severity`, `Serial_Number`, `Accident_Year`,
  `Accident_Date_Time`, `Latitude`, `Longitude`, `County`, fatalities and
  injuries, `Contrib_Circ_1`–`3`, `Most_Harmful_Event`, `Unit_Number`,
  `IntersectionRelated`, `Events`, `Vehicle_Type` (including Pedestrian,
  Pedalcycle, Scooter, Moped), `RouteID`, `Measure`. Ada County in 2023
  (reproduced Oct 7): 60 pedestrian, 91 pedalcycle, 2 scooter and 1 moped
  units.
- **Coverage:** statewide, 2005–2023, so the Idaho part of the ring; not
  its Oregon part.
- **Access:** MapServer queries (JSON or GeoJSON; no PBF),
  `maxRecordCount` 70,000, no key.
- **License and terms:** service copyright "ITD"; layer 35 "ITD GIS and
  ITD Office of Highway Safety"; no license. Credit ITD. ITD already
  publishes road-user types (the Oct 6 decision).
- **robots.txt:** gis.itd.idaho.gov 404: no rules (re-checked Oct 7).
- **Updates and size:** yearly, about three years behind (latest 2023 in
  Oct 2026). Bike and pedestrian units in the ring: a few thousand rows.
- **Use cases:** bike and pedestrian crashes in the ring outside Ada and
  Canyon, for road-cycling corridors; history back to 2005, three years
  before COMPASS's copy; a cross-check of COMPASS's unit types.
- **For:** recreational road cyclists, safety researchers. **Needs:**
  areas (the regional ring), layer system.
- **Risks:** completeness against COMPASS unverified ⚠️ (open question 10).
  Unit rows with a date, time and coordinates are personal data for
  pedestrians and cyclists: aggregates only.
- **Verification:** layer structure, fields, `maxRecordCount` and
  copyright confirmed; the Ada 2023 counts reproduced exactly (plus one
  moped). Whether they're low can only be settled against
  `restricted.crash_unit` on the server.
- **Evidence:**
  [MapServer](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer?f=json),
  [layer 35](https://gis.itd.idaho.gov/arcgisprod/rest/services/ArcGISOnline/CrashLayers/MapServer/35?f=json),
  one grouped `Vehicle_Type` query for Ada at `.../MapServer/75/query`,
  [robots.txt](https://gis.itd.idaho.gov/robots.txt).

### NHTSA FARS

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** yearly national CSV zips at
  `static.nhtsa.gov/nhtsa/downloads/FARS/<year>/National/FARS<year>NationalCSV.zip`
  (2023: 34.2 MB; 2024: 32.7 MB; both last modified Apr 1, 2026, by HEAD
  only). The [Crash API](https://crashviewer.nhtsa.dot.gov/CrashAPI) page
  isn't reachable from our client. Already on the SOURCES backlog as a
  benchmark.
- **Contents:** every fatal crash nationwide since 1975, with person type
  (pedestrian, bicyclist), lighting, location and road attributes. The
  2024 national files are out.
- **Coverage:** national, 1975 on, so the whole ring including Oregon.
  Coordinates start only around 1999–2001 ⚠️, so mapping earlier years may
  be county-level only.
- **Access:** by-hand downloads: nhtsa.gov and crashviewer answer our client
  with an Akamai 403.
- **License and terms:** public domain (federal data).
- **robots.txt:** static.nhtsa.gov 404 (no rules). crashviewer.nhtsa.dot.gov
  and www.nhtsa.gov answer robots.txt with an Akamai 403 (a 4xx, so no
  rules), but the sites block our client. Re-checked Oct 7.
- **Updates and size:** yearly; about 33 MB a year nationally, tiny once
  clipped.
- **Use cases:** national and peer-city benchmarks for pedestrian and
  cyclist deaths; fatalities in the ring before 2005.
- **For:** safety researchers. **Needs:** areas.
- **Risks:** fatal records: aggregates only, no victim details.
- **Verification:** file paths, sizes and robots.txt confirmed; the Crash
  API page wasn't reachable.
- **Evidence:** [static robots.txt](https://static.nhtsa.gov/robots.txt),
  [crashviewer robots.txt](https://crashviewer.nhtsa.dot.gov/robots.txt),
  [nhtsa.gov robots.txt](https://www.nhtsa.gov/robots.txt), HEAD requests
  on the
  [2023](https://static.nhtsa.gov/nhtsa/downloads/FARS/2023/National/FARS2023NationalCSV.zip)
  and
  [2024](https://static.nhtsa.gov/nhtsa/downloads/FARS/2024/National/FARS2024NationalCSV.zip)
  zips.

## OpenStreetMap, methods and benchmarks

### OpenStreetMap active-transport tags

Use · verified: corrected · confidence high · effort M

- **Source:** the Idaho extract we already download by hand from Geofabrik
  and keep on the server (the last two extracts). Tag reference:
  [Key:cycleway](https://wiki.openstreetmap.org/wiki/Key:cycleway).
- **Contents available in the extract:** `highway=cycleway`, `path`,
  `footway` (sidewalks and crossings), `pedestrian`, `steps`, `track`,
  `bridleway`, `living_street`, `residential`, `service`, `unclassified`;
  `cycleway*`, `bicycle`, `foot`, `segregated`, `oneway:bicycle`,
  `sidewalk*`, `surface`, `smoothness`, `lit`, `width`, `incline`,
  `layer`/`bridge`/`tunnel`; crossing nodes, `kerb`, `barrier`; and
  `amenity=bicycle_parking`, `bicycle_repair_station`, `drinking_water`.
- **What we load today:** the `osm_valley` pipeline clips the extract to
  the valley box and runs osmium's tags-filter with `w/highway` plus signal
  and level-crossing nodes. That passes every highway way, but `keep_way()`
  then keeps only motorway to tertiary roads (and links) and ways with
  `lanes` or `turn:lanes`. So cycleways, paths, footways and most
  residential streets pass osmium but are dropped in Python, and crossing,
  kerb, barrier and amenity nodes are never exported.
- **Coverage:** the valley box today; the Idaho part of the ring needs a
  second extract. Whether Geofabrik's Idaho polygon reaches the Oregon
  part of the ring (Ontario, Vale) is unverified ⚠️. Completeness varies;
  sidewalks are probably sparse ⚠️.
- **Access:** no new download: widen the keep rule, or add a sibling keep
  function over the same export, plus new node filters (correction 2).
- **License and terms:** ODbL: credit "© OpenStreetMap contributors"; a
  published derived database (our LTS on OSM ways, for example) stays
  ODbL.
- **robots.txt:** not applicable to this step, which reuses the extract
  downloaded by hand. Geofabrik's robots.txt disallows scripted extract
  downloads ([DECISIONS](../DECISIONS.md), Oct 6).
- **Updates and size:** with each weekly hand download. Perhaps 100–200k
  extra ways in the box ⚠️; tens of MB in PostGIS.
- **Use cases:** the network graph for the cyclist's and walker's maps and
  routing; LTS for Canyon County, where no official LTS exists; bike
  parking and repair stations; comparing OSM with ACHD to find mapping
  gaps (hints only).
- **For:** everyday cyclists, pedestrians and wheelchair users, bike
  advocates and planners, OpenStreetMap contributors. **Needs:** the
  regular OpenStreetMap load, layer system, evidence and review.
- **Risks:** ACHD, Meridian and COMPASS data aren't ODbL-compatible: never
  copy them into OSM. Use differences only as places to look, and trace
  from NAIP (public domain) under OSM's rules.
- **Verification:** checked against the loader code. Corrected the
  mechanism: the tags-filter already passes every highway way, `keep_way()`
  drops them, and only signal and level-crossing nodes are exported. The
  extract step clips to the valley box, so the ring needs its own extract.
  The wiki page itself wasn't fetched again.
- **Evidence:**
  [`osm_valley.py`](../../plugins/roads/ingest/sources/osm_valley.py)
  (`TAG_FILTERS`, `keep_way`, the osmium commands),
  [DECISIONS](../DECISIONS.md) (Oct 6, OpenStreetMap),
  [ch. 16 §16.4](../16-ideas-and-personas.md#164-shared-core-pieces-serve-almost-every-persona).

### Level of Traffic Stress method

Use · verified: confirmed · confidence high · effort M

- **Source:** Mekuria, Furth and Nixon,
  [Low-Stress Bicycling and Network Connectivity](https://transweb.sjsu.edu/research/Low-Stress-Bicycling-and-Network-Connectivity),
  Mineta Transportation Institute Report 1005 (May 2012), and Peter Furth's
  [criteria pages](https://peterfurth.sites.northeastern.edu/level-of-traffic-stress/).
- **Contents:** LTS 1 (suitable for children) to LTS 4. Criteria for mixed
  traffic, bike lanes with and without parking, right-turn approaches and
  unsignalized crossings; a weakest-link rule for routes. Furth's page
  comments on "version 1.0, 2012", including ADT of 3,000 or less with no
  marked centerline on two-lane roads. The report (1.7 MB) and brief
  (1.2 MB) are free PDFs.
- **License and terms:** free PDFs; the page reads "© Copyright 2025 Mineta
  Transportation Institute". The method can be implemented freely.
- **robots.txt:** not applicable: a method we implement, not data we
  collect (two documentation pages read).
- **Use cases:** our own LTS engine, for Canyon County and for checking
  ACHD's scores; route stress (weakest link) for the safe-routes planner.
- **For:** bike advocates and planners, everyday cyclists, parents.
  **Needs:** evidence and review (scores with their inputs and
  provenance).
- **Risks:** version drift: ACHD and Alta's 2023 scoring and Furth's later
  criteria differ. Store the method version with every score.
- **Verification:** authors, date, report number and the free PDFs
  confirmed. Furth's page labels its tables as version 1.0 commentary;
  later revisions (2017, for example) aren't shown there ⚠️.
- **Evidence:** the two pages linked above.

### PeopleForBikes Bicycle Network Analysis

Use · verified: confirmed · confidence medium · effort M

- **Source:** [brokenspoke-analyzer](https://github.com/PeopleForBikes/brokenspoke-analyzer)
  3.2.5 (MIT) and PeopleForBikes'
  [City Ratings](https://cityratings.peopleforbikes.org/cities/boise-id).
- **Contents:** the Bicycle Network Analysis (BNA): OSM-based binary stress
  (high or low) plus connectivity scores to destinations (jobs from LODES,
  schools, parks, shopping, transit). City Ratings gives Boise 31 overall
  (2025 rating; rank 1,682 of 3,019); the page's wording on the network
  score was ambiguous ⚠️. The analyzer runs in Docker (PostGIS,
  osm2pgrouting, osm2pgsql, osmium) and accepts
  [custom inputs](https://peopleforbikes.github.io/brokenspoke-analyzer/how-to/custom-input-files.html):
  a boundary, `<region>-latest.osm.pbf` with its `.md5`, a clipped city
  file, a population shapefile, LODES CSVs, and state and city speed CSVs.
- **Coverage:** any US city; we'd run Boise, Meridian, Nampa, Caldwell,
  Eagle, Kuna, Star and Garden City.
- **Access:** run the analyzer on our own inputs, with every file placed
  beforehand so it never downloads anything. The City Ratings pages show
  scores; no data download was found.
- **License and terms:** the analyzer is MIT; outputs on OSM are ODbL
  derivatives. City Ratings data terms not found ⚠️: cite its scores,
  don't store its layers.
- **robots.txt:** cityratings.peopleforbikes.org and bna.peopleforbikes.org
  both have an empty `Disallow` (allow all). Re-checked Oct 7.
- **Updates and size:** re-run after each OSM refresh, or monthly. A few
  hundred MB of working space per city.
- **Use cases:** valley-wide connectivity scores for every city, Canyon
  included; "islands of low stress" and access-to-destinations measures
  for the gap analysis; a national benchmark for Boise.
- **For:** bike advocates and planners, safety researchers. **Needs:** the
  regular OpenStreetMap load.
- **Risks:** place every input file beforehand so it never fetches from a
  host whose robots.txt disallows us (Geofabrik). The speed inputs are city
  and state defaults, not segment speeds (correction 4). Heavy PostGIS
  work: run it off-peak or on the laptop.
- **Verification:** the MIT license, version 3.2.5, the Docker requirement
  and the custom input names confirmed. The docs don't name the default
  download hosts, so placing every input beforehand is required, not
  optional. Boise's 31 and its rank confirmed; the network score unclear.
- **Evidence:** the analyzer repository and docs linked above,
  [City Ratings robots.txt](https://cityratings.peopleforbikes.org/robots.txt),
  [Boise's rating](https://cityratings.peopleforbikes.org/cities/boise-id),
  [BNA robots.txt](https://bna.peopleforbikes.org/robots.txt).

### EPA National Walkability Index and Smart Location Database

Use · verified: corrected · confidence high · effort S

- **Source:** [EPA Smart Location Mapping](https://www.epa.gov/smartgrowth/smart-location-mapping)
  (page updated Sep 8, 2026).
- **Contents:** the block-group National Walkability Index (intersection
  density, employment and housing mix, employment diversity, transit
  proximity) and the Smart Location Database v3.0 (Jan 2021; over 90
  variables), on 2019 block-group geography (2010 census boundaries).
- **Endpoints:** by-hand downloads from edg.epa.gov:
  `EPADataCommons/public/OA/WalkabilityIndex.zip`,
  `.../OA/SLD/SmartLocationDatabaseV3.zip`, and a CSV at
  `.../OA/EPA_SmartLocationDatabase_V3_Jan_2021_Final.csv`. Not the
  geodata.epa.gov MapServers, which robots.txt disallows.
- **Coverage:** national, so the whole ring including Oregon; 2021 vintage.
- **Access:** a one-time zip or CSV download by hand (owner OK).
- **License and terms:** CC0 1.0, per the
  [data.gov entry](https://catalog.data.gov/dataset/walkability-index) for
  the Walkability Index.
- **robots.txt:** www.epa.gov allows content pages; edg.epa.gov 404 (no
  rules); geodata.epa.gov has `Disallow: /arcgis/` for all agents. Checked
  Oct 7.
- **Updates and size:** rarely updated. The national zip is large (hundreds
  of MB ⚠️); clipped to the valley, under 5 MB.
- **Use cases:** a walkability baseline for every block group in the
  valley, to compare with our sidewalk-based measures.
- **For:** pedestrians and wheelchair users, bike advocates and planners,
  neighbours and civic users. **Needs:** layer system.
- **Risks:** coarse and dated (2021); the block-group boundaries predate the
  2020 census, so joining to 2020-based ACS block groups needs a
  crosswalk.
- **Verification:** corrected: the MapServer route is disallowed by
  robots.txt, so only the by-hand zip or CSV is usable; the SLD zip is
  under `/OA/SLD/`; the license is stated as CC0 on data.gov (no longer an
  inference); the geography is 2019 block groups.
- **Evidence:** [EPA page](https://www.epa.gov/smartgrowth/smart-location-mapping),
  [epa.gov robots.txt](https://www.epa.gov/robots.txt),
  [edg robots.txt](https://edg.epa.gov/robots.txt),
  [geodata robots.txt](https://geodata.epa.gov/robots.txt),
  the [EDG metadata record](https://edg.epa.gov/metadata/catalog/search/resource/details.page?uuid=%7B251AFDD9-23A7-4068-9B27-A3048A7E6012%7D)
  (redirects to data.gov),
  [data.gov entry](https://catalog.data.gov/dataset/walkability-index).

### Census ACS means of transportation to work

Needs owner action · verified: confirmed · confidence medium · effort S

- **Source:** ACS 5-year table B08301 (means of transportation to work) by
  tract and block group: bicycle, walked, worked from home, transit. Ada
  (16001) and Canyon (16027).
- **Access:** three routes: the Census Data API with a free key (the
  [user guide](https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html)
  says a key "must be used with all data queries"; 50 variables a query;
  an owner action); tables by hand from data.census.gov; or ACS summary
  files from www2.census.gov. The two by-hand routes avoid the key.
- **Coverage:** national, so Ada, Canyon and the ring; 5-year rolling.
- **License and terms:** public domain (federal statistics); the Census
  API terms of service apply to the API.
- **robots.txt:** api.census.gov answers robots.txt with a WAF "Request
  Rejected" page and HTTP 200 (re-checked Oct 7), so its rules are unknown.
  data.census.gov allows `/` except `/mdat/`; www2.census.gov has no rules
  for `*`.
- **Updates and size:** yearly (usually December); kilobytes.
- **Use cases:** exposure denominators for crash rates by tract; where
  people already walk and bike, for gap ranking.
- **For:** safety researchers, bike advocates and planners. **Needs:**
  layer system.
- **Risks:** commute trips only (no recreation); large margins of error on
  small bike shares.
- **Verification:** the key requirement confirmed on the Query Limits page;
  the WAF response reproduced. Added the two robots-allowed by-hand routes.
- **Evidence:** the [API key](https://www.census.gov/data/developers/guidance/api-user-guide.API_Key.html),
  [query components](https://www.census.gov/data/developers/guidance/api-user-guide.Query_Components.html)
  and [query limits](https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html)
  pages; robots.txt for [api](https://api.census.gov/robots.txt),
  [data](https://data.census.gov/robots.txt) and
  [www2](https://www2.census.gov/robots.txt).

## Micromobility and crowdsourced data

### Lime GBFS feeds (avoid)

Avoid · verified: confirmed · confidence high · effort S

- **What exists:** Lime has been Boise's only shared micromobility provider
  since July 2023 ([City of Boise](https://www.cityofboise.org/departments/finance/how-to-use-e-scooters-and-e-bikes/)).
  Lime publishes partner GBFS feeds for some cities, but MobilityData's
  catalog ([`systems.csv`](https://raw.githubusercontent.com/MobilityData/gbfs/master/systems.csv),
  1,540 systems) lists none in Idaho. No public bike-share feed exists
  either (see the bike-share history below).
- **robots.txt:** data.lime.bike has `User-agent: *` `Disallow: /`
  (allowing only `/juicer` and app-association files), re-checked Oct 7.
  mds.bird.co returns 404 (no rules); that Bird has no Boise feed wasn't
  re-checked.
- **License and terms:** not reached: robots.txt stops us first.
- **Only route:** live vehicle availability with written permission from
  Lime, or through the City (open question 7).
- **Risks:** free-floating vehicle positions can reveal trips if IDs
  persist; even with permission, store aggregates only.
- **Evidence:** [Lime robots.txt](https://data.lime.bike/robots.txt),
  [Bird robots.txt](https://mds.bird.co/robots.txt), the MobilityData
  catalog and the City page linked above.

### Ride Report public micromobility dashboard for Boise

Needs owner action · verified: confirmed · confidence medium · effort S

- **Endpoint:** [public.ridereport.com/boise](https://public.ridereport.com/boise),
  linked from the City's e-scooter page.
- **Contents:** quarterly aggregates for Boise from Q2 2019 to Q3 2026, by
  vehicle class (all, e-bike, scooter): vehicles, trips, distance, speed.
  Active operator: Lime. The page's configuration shows
  `earliest_available_metrics` and `earliest_available_routes` of
  2019-04-21, which suggests a street-level routes map as well ⚠️ (not
  opened). The contact is the City's program mailbox.
- **Coverage:** City of Boise, 2019 to now.
- **Access:** a JavaScript (Next.js) dashboard; download the quarterly
  aggregates by hand (an owner action). No API was found.
- **License and terms:** none found: www.ridereport.com's `/terms`,
  `/terms-of-service` and `/privacy` are 404; only `/privacy-policy` is
  linked. Store internally and ask the City before republishing.
- **robots.txt:** public.ridereport.com 404 (no rules); www.ridereport.com
  disallows only sample and preview paths. Re-checked Oct 7.
- **Updates and size:** quarterly; kilobytes.
- **Use cases:** scooter and e-bike use since 2019 on a time-series card;
  context for scooter crashes (ITD's `Vehicle_Type` "Scooter").
- **For:** e-scooter and e-bike riders, bike advocates and planners.
  **Needs:** the readings contract and time-series card.
- **Risks:** never ask for raw MDS trips (they trace individuals). If a
  routes view exists, use only its aggregates, with the City's OK.
- **Verification:** the quarter range, the operator and the missing terms
  confirmed from the page's embedded configuration. "Citywide only" may be
  wrong, since the configuration advertises route data from 2019 ⚠️.
- **Evidence:** [City page](https://www.cityofboise.org/departments/finance/how-to-use-e-scooters-and-e-bikes/),
  [robots.txt](https://public.ridereport.com/robots.txt),
  [dashboard](https://public.ridereport.com/boise),
  [terms (404)](https://www.ridereport.com/terms),
  [www robots.txt](https://www.ridereport.com/robots.txt).

### Boise bike-share history: GreenBike and Vall-eBike

Use · verified: corrected · confidence high · effort S

- **Source:** Valley Regional Transit's news pages and its
  [bikes page](https://www.valleyregionaltransit.org/bikes/).
- **Contents:**
  - **Boise GreenBike:** April 2015 to September 2020; ended because of the
    pandemic, lost title sponsors and equipment issues. Fleet size not
    found on the pages checked ⚠️.
  - **Vall-eBike:** 50 Drop Mobility e-bikes, July 13 to Oct 31, 2022;
    about 2,400 riders and nearly 3,000 trips (article of Oct 24, 2022).
    The Vall-eBike page says VRT hoped to relaunch in 2024; no current
    system appears.
  - **Bikes and buses:** every bus rack holds "at least two bikes"; secure
    parking at Main Street Station and BikeBOI (the 8th and Main garage).
- **Coverage:** Boise.
- **Access:** news pages only; no station or trip data was found.
- **License and terms:** facts from VRT's pages, cited.
- **robots.txt:** valleyregionaltransit.org disallows only `/wp-admin/`
  (re-checked Oct 7).
- **Updates and size:** static; negligible.
- **Use cases:** a history timeline card for shared micromobility in
  Boise; secure bike parking on the cyclist's map.
- **For:** history buffs, everyday cyclists, bike advocates and planners.
  **Needs:** places and search.
- **Verification:** dates, operator, rider and trip counts, the 2024
  relaunch hope and the parking sites confirmed. Corrected: GreenBike's
  127 bikes isn't on these pages (it needs another source); bus racks hold
  at least two bikes, not exactly two.
- **Evidence:** [robots.txt](https://www.valleyregionaltransit.org/robots.txt),
  [pilot ends](https://www.valleyregionaltransit.org/news/bike-share-vall-ebike-pilot-ends-october-31st/),
  [bike share returns](https://www.valleyregionaltransit.org/news/bike-share-returns-to-boise/),
  [Vall-eBike](https://www.valleyregionaltransit.org/vall-ebike/),
  [bikes](https://www.valleyregionaltransit.org/bikes/).

### Strava Metro and Strava heatmaps (avoid)

Avoid · verified: corrected · confidence high · effort S

- **What exists:** [Strava Metro](https://metro.strava.com/) offers
  de-identified, aggregated activity data to planners free of charge,
  through a partnership application, under the Strava Metro Terms (not
  read). The public Global Heatmap is part of strava.com.
- **Why avoid:** the project excludes Strava:
  [ch. 15 §15.3](../15-plugins.md#153-private-plugins) lists it among
  sites that forbid storing their data. Activity data also comes from
  individuals, a privacy and terms concern.
- **robots.txt:** strava.com disallows ClaudeBot, GPTBot, Google-Extended
  and Meta-ExternalAgent entirely; for `*` it disallows `/api/`,
  `/athletes/*/heatmaps`, `/athletes/*/segments/*`, `/segments/*/compare`
  and many activity paths, but not every heatmap or segment page.
  metro.strava.com has no rules.
- **Only use:** if ACHD or COMPASS publish Strava-derived findings in their
  plans, cite the plan text.
- **Verification:** corrected two details: the exclusion is written in
  ch. 15 §15.3 (and the research brief), not CLAUDE.md; and robots.txt for
  `*` blocks athlete heatmaps and some segment paths, not heatmaps and
  segments wholesale. Verdict unchanged.
- **Evidence:** [Strava Metro](https://metro.strava.com/),
  [strava.com robots.txt](https://www.strava.com/robots.txt),
  [Metro robots.txt](https://metro.strava.com/robots.txt).

### BikeMaps.org (avoid)

Avoid · verified: confirmed · confidence medium · effort S

- **What exists:** [BikeMaps.org](https://bikemaps.org/about/), founded and
  directed by Trisalyn Nelson (UC Santa Barbara), with Simon Fraser
  University: volunteer reports of bike collisions, near misses, hazards
  and thefts worldwide. Treasure Valley coverage unknown.
- **robots.txt:** disallows the four JSON endpoints (`/points.json`,
  `/incidents.json`, `/hazards.json`, `/thefts.json`), the submit forms,
  `/admin/`, `/forum/`, `/edit/` and `/contact/` (re-checked Oct 7).
- **License and terms:** none stated on the about page; data inquiries go
  to the team by email. Account or key unknown ⚠️.
- **Only route:** a research export, if the team grants one (an owner
  action).
- **Risks:** free-text reports may describe people; precise points and
  times can identify reporters.
- **Verification:** the robots.txt rules and the absence of license text
  confirmed.
- **Evidence:** [robots.txt](https://bikemaps.org/robots.txt),
  [about](https://bikemaps.org/about/).

## Ideas by persona

From the research pass, adjusted where verification changed a fact (noted
in each). None is approved. "Correction n" refers to the list under
[What verification changed](#what-verification-changed-in-the-design).

### Everyday cyclists

- **A cyclist's lens.** Every street coloured by LTS 1–4, with line width
  and dash as a second channel, never red and green alone. Off-street
  pathways, the Greenbelt, micro-paths, bike parking, repair stations and
  RRFB and HAWK crossings sit on top. Clicking a segment shows its inputs
  (speed, lanes, ADT, facility width, buffer, parking) and which source set
  each: ACHD's own LTS, Alta's 2023 score, or ours. The research proposed
  LTS 1 wide and solid and LTS 4 thin and dashed; that fits a "where can I
  ride" lens, but a safety view should invert it, and the colours must come
  from ch. 13's data ramp (correction 6). *Sources:* ACHD bike network,
  ACHD bike LTS, OpenStreetMap, Boise pathways, ACHD ArcGIS Online layers,
  Boise markers and repair stations. *Needs:* regular OpenStreetMap load,
  layer system, evidence and review.
- **A low-stress route planner.** Pick A and B and get the least-stress
  route, not the shortest, with its weakest link named ("one LTS 3
  crossing at Fairview & Cole"), the climb from the 1 m terrain, lit and
  unlit sections (Boise's street lights from its open data, OSM `lit=*`),
  and the minutes added against the fastest route. A slider trades stress
  for distance. *Sources:* ACHD bike LTS, OpenStreetMap, the LTS method,
  COMPASS ExistingBikeAndPed. *Needs:* a routing graph (a proposed new
  core piece), regular OpenStreetMap load, places and search.

### Greenbelt regulars

- **A Greenbelt panel.** Live closures and detours as lifecycle events in
  the Valley Feed (first and last seen are ours, since the City's layer has
  no dates); search by DOTS milepost; hourly use at each counter on a
  time-series card, once COMPASS shares hourly data (if it exists:
  correction 1); and a river-flow overlay from the water plugin showing
  when high water closes underpasses, with the threshold measured from
  history, not assumed. *Sources:* Boise Greenbelt closures, Boise markers,
  COMPASS counters. *Needs:* lifecycles contract (`evt.event`), Valley
  Feed, readings contract and time-series card, places and search.

### Parents (safe routes)

- **"Can my kid bike or walk to school?"** For each school, the area
  reachable at LTS 1–2 by bike and PLTS 1–2 on foot, overlaid with the
  district's walk zones, flagging every LTS 3–4 crossing inside a zone
  where children are expected to walk. Only Boise's district has walk
  zones in ACHD's organisation; West Ada's and Kuna's layers are attendance
  areas, so elsewhere the flag needs another basis, such as a 1.5 mi radius
  (the distance Boise's description uses for its busing boundary ⚠️;
  correction 7). Results by school, aggregated, are a publishable research
  finding; zones are shown as infrastructure, never tied to students.
  *Sources:* ACHD walking LTS, ACHD bike LTS, ACHD ArcGIS Online layers
  (Boise zones), COMPASS Walkability. *Needs:* routing graph, places and
  search (schools), layer system.

### Pedestrians and wheelchair users

- **An accessibility view.** Sidewalk presence on each side, width, buffer
  and ADA category; curb ramps by condition (once ACHD explains the codes:
  1–4 for sidewalks, 1–5 for ramps); ADA push buttons; accessible signals
  and leading pedestrian intervals from COMPASS's signal fields; the
  inaccessible-button and inaccessible-ramp flags, pedestrian hybrid
  beacons and intersection lighting (`Lamp_Count`) from ACHD's walking LTS
  (correction 11); and the grade of each block from the 1 m DEM. A
  step-free route planner avoids missing ramps and steep blocks, labelled
  as reference only, as ACHD's disclaimer requires. *Sources:* ACHD
  sidewalks and ramps, ACHD ArcGIS Online layers, ACHD walking LTS, COMPASS
  ExistingBikeAndPed. *Needs:* routing graph, layer system, intersections
  (COMPASS's signal fields are already loaded).

### Bike advocates and planners

- **Gap analysis: "islands of low stress".** Split the LTS 1–2 network
  into connected components, each island in its own colour. Rank the
  single missing links (an LTS 3–4 crossing or segment, a sidewalk gap, an
  unbuilt pathway) by how many people, jobs (LODES), schools and parks
  they'd join. Compare the top 20 with ACHD's Five-Year Plan sidewalk and
  bike projects and Boise's proposed gap closures: which high-value gaps
  have no project? *Sources:* ACHD bike network, ACHD bike LTS, ACHD
  sidewalk projects, Boise pathways, PeopleForBikes BNA, COMPASS
  Walkability, Census ACS. *Needs:* routing graph, regular OpenStreetMap
  load, evidence and review.
- **Canyon County LTS, where no agency publishes one.** Run our LTS engine
  on COMPASS's centerline speeds and lanes, OSM cycleway tags, COMPASS's
  and Nampa's bike facilities, and COMPASS and ITD counts for ADT, after
  calibrating it against ACHD's and Alta's 2023 scores in Ada with a
  published agreement matrix. Then run BNA connectivity scores for every
  valley city side by side (BNA's speed inputs are defaults, so segment
  speeds reach it only through OSM `maxspeed`: correction 4). *Sources:*
  LTS method, ACHD bike LTS, COMPASS ExistingBikeAndPed, Nampa layers,
  OpenStreetMap, PeopleForBikes BNA. *Needs:* regular OpenStreetMap load,
  evidence and review, areas.

### Safety researchers

- **Bike and pedestrian crashes against stress.** Crashes per mile by LTS
  class, and at intersections by intersection LTS, from COMPASS's
  road-user types (aggregated to segments or hexes, never single points
  with dates). Split by light condition against street lighting (with
  ACHD's `Lamp_Count` at intersections: correction 11), and by hour
  against low-sun glare on east–west streets. ITD's units extend this to
  the regional ring, once their completeness is checked against COMPASS
  (correction 12). *Sources:* COMPASS crashes, ITD crash units, ACHD bike
  network, ACHD bike LTS, Census ACS. *Needs:* layer system, full replay
  (year slider).
- **Before and after for new bikeways.** Compare crashes (and pathway
  counts where a counter exists) on each segment for the years before and
  after its facility was built, against matched comparison segments.
  Verification warns that ACHD's `YrBuilt` is text, `YearAdded` probably
  records when a segment entered the GIS ⚠️, and COMPASS calls its own
  year fields unreliable: check a sample against NAIP and older imagery
  first, or limit the study to projects with known construction years
  (Five-Year Plan projects, `CNYear` in `Low_Stress_Routes`;
  correction 3). *Sources:* ACHD bike network, COMPASS crashes, COMPASS
  counters. *Needs:* full replay (year slider), readings contract.

### Recreational road cyclists

- **Road rides in the regional ring.** Rate state highways (SH-21 to Idaho
  City, SH-55 to Horseshoe Bend, SH-44, SH-52, SH-16, US-95) for "shoulder
  comfort" from HPMS shoulder width (already loaded by `itd_hpms`), AADT
  and posted speed. Add bike crashes by corridor from ITD's units, live
  shoulder closures from the WZDx feed where lanes are typed `shoulder` or
  `bike-lane` (whether ITD ever does is open question 9), and wind and
  pavement readings from 511's road-weather stations, which stay in the
  owner's internal view since 511's data isn't republished
  ([DECISIONS](../DECISIONS.md)). *Sources:* ITD crash units,
  OpenStreetMap. *Needs:* areas (regional ring), readings contract,
  lifecycles contract.

### Weather watchers

- **An "is it a good bike day" card.** Wind, temperature and pavement state
  from the nearest road-weather station, sunset time, smoke and air quality
  (hazards plugin) and Greenbelt closures, set against how counter volumes
  have responded to the same weather. This needs hourly counter data from
  COMPASS; 511's station readings would be internal only, so a public card
  needs another weather source. *Sources:* COMPASS counters, Boise
  Greenbelt closures. *Needs:* readings contract and time-series card,
  Valley Feed.

### Gardeners

- **A shade walk** (with the gardening and sky plugins). For a chosen date
  and hour, the share of each sidewalk and pathway block in shade, from
  building heights, the lidar canopy, Boise's street trees and the sun's
  position: the shadiest route to the park at 4 pm in July, with a 3D
  shadow sweep along it. ACHD's "LTS Street Trees" layer and Boise's Tree
  Canopy Study tiles can add to the canopy (correction 11). *Sources:*
  Boise markers and trees, ACHD sidewalks, ACHD walking LTS. *Needs:* 3D
  engine, routing graph, sun position (sky plugin).

### Signal-timing researchers

- **Walk and bike service at signals** (the project's core question). Map
  leading pedestrian intervals and accessible signals (COMPASS
  `Signalized_Intersections`), ADA push buttons, and intersection walking
  and bike LTS. Use the sidewalk method of
  [ch. 7](../07-diy-data-collection.md) to time pedestrian waits (button to
  Walk) and crossing clearance on wide arterials. The question: do the
  arterials with the worst car progression also make pedestrians wait
  longest? *Sources:* ACHD walking LTS, ACHD bike LTS, ACHD ArcGIS Online
  layers. *Needs:* intersections plugin, evidence and review, readings
  contract.

### Transit riders

- **First and last mile to the bus.** For each VRT stop, the area reachable
  on foot (PLTS 1–2) and by bike (LTS 1–2) in 10 minutes; stops with
  high-stress crossings between them and nearby homes; secure bike parking
  (BikeBOI, Main Street Station); and bike-rack space on buses ("at least
  two", not exactly two: correction 10). A ranked list: busy stops with
  poor walk access. *Sources:* COMPASS Walkability (bus-stop walksheds),
  ACHD walking LTS, VRT bike pages. *Needs:* routing graph, transit plugin
  (GTFS stops).

### E-scooter and e-bike riders

- **A small micromobility card.** Boise's quarterly scooter and e-bike
  trips since 2019 (Ride Report, once the City agrees), the bike-share
  timeline (GreenBike 2015–2020, Vall-eBike 2022), and scooter crashes from
  ITD's unit type "Scooter". No live vehicles: Lime's feed host disallows
  all robots. *Sources:* Ride Report, VRT bike-share history, ITD crash
  units. *Needs:* readings contract and time-series card.

### OpenStreetMap contributors

- **Give back to OpenStreetMap.** A review list of places where ACHD or
  COMPASS show a bike lane, sidewalk or pathway that OSM lacks, used only
  as hints. A mapper checks each in NAIP 2025 (public domain, accepted for
  tracing) and maps it by hand under OSM's rules; agency geometry and
  attributes are never copied. *Sources:* OpenStreetMap, ACHD bike network,
  ACHD sidewalks, COMPASS ExistingBikeAndPed. *Needs:* evidence and review,
  regular OpenStreetMap load.

### History buffs

- **The bike network's year slider.** Facilities appear year by year over
  the NAIP year slider, with GreenBike's years marked: the bike lanes,
  Greenbelt extensions and low-stress bikeways spreading since ACHD's
  Roadways to Bikeways plan (2009 per the research ⚠️; the verified pages
  mention only its 2018 update). It shares the dating problem of the
  before-and-after study, so it waits on the same imagery check
  (correction 3). *Sources:* ACHD bike network, Boise pathways, VRT
  bike-share history. *Needs:* full replay (year slider), layer system.

### Mountain bikers and hikers

- **From the city network to the Foothills.** The low-stress route to each
  Ridge to Rivers trailhead, with the latest condition report shown on the
  trailhead (summarized, not copied). Shared with the trails plugin.
  *Sources:* Ridge to Rivers reports, Boise trails and trailheads, ACHD
  bike LTS. *Needs:* routing graph, lifecycles contract, places and search.

## Design notes

The research pass's proposal, with verification's changes folded in where
they apply. The full list of changes follows in the next section.

### What changes the picture

- **ACHD has already scored stress.** Its public layers carry LTS at three
  levels: the Official Bicycle Facility Network's own `LTS` field (1,080
  mi: LTS 1 = 260 mi, 2 = 194, 3 = 152, 4 = 223, blank = 251); Alta
  Planning + Design's bike scores for segments and intersections (2023;
  4,584 segments; edited Dec 2025); and Alta's walking scores (2023; 34,771
  segments; edited Mar 2026, not Mar 2025 as the research first said).
  These layers also hold the inputs we lack elsewhere: AADT, centerline
  presence, facility and buffer widths by direction, parking, pavement
  condition. So in Ada the task is to validate and present, not compute
  from scratch. Our own LTS engine earns its place in Canyon County (no
  official LTS), at intersection approaches, and in keeping scores current
  as speeds and lanes change.
- **Our OpenStreetMap load drops what cyclists and walkers need.** The
  `osm_valley` loader keeps only motorway to tertiary roads and ways with
  lane tags, though the extract itself is on the server. Proposal: a
  sibling source in the same manual pattern (`osm_active`) over the same
  hand-downloaded file, keeping `highway=cycleway`, `path`, `footway`,
  `pedestrian`, `steps`, `track`, `bridleway`, `living_street`,
  `residential`, `service` and `unclassified`; their `cycleway*`,
  `bicycle`, `foot`, `segregated`, `sidewalk*`, `surface`, `smoothness`,
  `lit`, `width` and `incline` tags; and crossing, kerb, barrier,
  bicycle-parking, repair-station and drinking-water nodes. The research
  proposed a second osmium pass; verification found the cheaper change is
  to widen the Python keep rule (or add a sibling keep function) and add
  node filters (correction 2). No new download; ODbL in its own tables.
  This is the "regular OpenStreetMap load" core piece in
  [ch. 16 §16.4](../16-ideas-and-personas.md#164-shared-core-pieces-serve-almost-every-persona)
  doing double duty.

### Where it lives (an owner decision)

- **Option A:** a new `active` plugin (bike and walk network, stress
  scores, counts, Greenbelt closures, micromobility aggregates), depending
  on `roads`, `intersections` and `safety`. Its lens could be "Active" or
  sit inside Traffic.
- **Option B:** extend existing plugins, as
  [ch. 15 §15.7](../15-plugins.md#157-ideas-for-later-plugins) suggests
  (`safety`, `roads`): infrastructure in `roads`, crashes in `safety`, and
  counts perhaps in `flow`.
- The research leaned to A: a distinct subject with its own sources,
  schedules and a router, which switches off cleanly. Meridian's pathways
  ("please do not re-distribute") go in a private plugin schema, like
  parcels.

### Data model sketch

- `core.active_way`: our routable graph, OSM-based, with agency attributes
  joined by the existing segment matcher (buffer and bearing). Respect
  grade separation: OSM `layer`, `bridge` and `tunnel`, and COMPASS
  `Pathways_Master`'s `f_elev`/`t_elev` z-levels (correction 2).
- `core.segment_lts`, in the pattern of `core.segment_lanes`: one row per
  segment, direction, source and method (ACHD official, Alta 2023, ours
  v1); the inputs stored with their provenance; conflicts flagged for the
  evidence-and-review table.
- `core.intersection_lts` for bikes and walking, keyed to
  `core.intersection` where signalized and to OSM nodes otherwise.
- **Lifecycles** in `evt.event`: Greenbelt closures (check `lastEditDate`
  hourly, fetch on a change, versions in `raw.record`; the layer has no
  dates, so first and last seen are ours). Work zones whose WZDx lanes are
  typed `bike-lane`, `sidewalk` or `shoulder`:
  [`itd_wzdx.py`](../../plugins/conditions/ingest/sources/itd_wzdx.py)
  already keeps lane type and status, so this is only a query (open
  question 9).
- **Readings** in `obs`: pathway counter volumes (hourly, if COMPASS shares
  them); Ride Report's quarterly micromobility totals (citywide, or by
  street if the routes view is real ⚠️).

### Our LTS engine (v1)

- **Method:** Mekuria, Furth and Nixon's 2012 segment tables, plus the
  approach and unsignalized-crossing criteria, with the weakest-link rule
  for routes. Store the method version with every score.
- **Inputs, each with provenance:**
  - speed: ACHD posted speed; COMPASS's centerline in Canyon;
  - lanes: `core.segment_lanes`, with its provenance;
  - ADT: COMPASS's latest portable counts and ATRs, ITD AADT, the CIM model
    links; class defaults on local streets, marked estimated;
  - bike facility, width, buffer, parking: ACHD per direction; OSM
    `cycleway:*` and COMPASS's bike facilities in Canyon;
  - centerline: ACHD's bike LTS layer where present;
  - right-turn lanes: OSM `turn:lanes` and COMPASS's right-turn lane
    fields;
  - crossings: lanes crossed, speed, median refuge (OSM `crossing:island`,
    HPMS median).
- **Validation:** an agreement matrix against Alta's 2023 bike LTS in Ada,
  published as a finding.

### Connectivity and routing

- **BNA:** run brokenspoke-analyzer (MIT) for BNA-style scores per city,
  with every input placed by hand: `<region>-latest.osm.pbf` and its `.md5`
  from our extract, Census block population, and LODES CSVs, so it never
  fetches from Geofabrik, whose robots.txt disallows scripted downloads.
  Verification: the speed inputs are state and city default CSVs, so
  ACHD's segment speeds don't plug in (only OSM `maxspeed` reaches BNA);
  and check the LEHD host's robots.txt before reusing
  [`tools/lehd_flows.py`](../../tools/lehd_flows.py)'s source
  (correction 4).
- **A routing graph** is a candidate new core piece: the cyclist, walker,
  hiker, commuter and safe-routes ideas all need one. Options (an owner
  decision):
  - pgRouting on our own graph: cost = length × a stress factor + a hill
    penalty from the 1 m DEM; the simplest way to use our own LTS and
    agency attributes. pgRouting is a separate extension, not part of
    PostGIS: check that the `timescaledb-ha` image ships it
    (`pg_available_extensions`) before choosing it. Adding or changing the
    database image is a server change that needs the owner's OK
    (correction 5).
  - BRouter (MIT; profiles; elevation-aware) or Valhalla (MIT; bicycle and
    pedestrian costing; isochrones), self-hosted. Both run on OSM tags, so
    our LTS would go in as derived tags in a private PBF: an ODbL
    derivative, fine internally and ODbL if published. BRouter builds its
    own segment files and uses coarse SRTM-class elevation, not our 1 m
    DEM, unless custom-built.

### Display (ch. 13 rules)

- Never red and green alone. Map LTS 1–4 onto steps of ch. 13's five-step
  data ramp (blue-teal, yellow, orange, magenta, purple) with monotone
  lightness, keep width and dash as the second channel, show the number on
  hover, and run the colour-blindness simulator check that ch. 13 asks for.
  The research's "teal, blue, purple, orange" isn't an ordered ramp
  (correction 6).
- Drawing LTS 4 thinnest suits a "where can I ride" lens but hides the most
  dangerous roads, so a safety lens should invert it.
- A "plain" mode showing only LTS 1–2, for "where can I ride comfortably"
  (open question 12).
- 3D: route ribbons draped on the terrain with grade shading; shade sweeps
  reuse the sky plugin's sun position and the building and canopy heights.

### Ethics and licenses

- Road network and nature, not people.
- **Crashes:** road-user types may be published (Oct 6); people stay
  restricted; show aggregates (segment or hex), never single pedestrian
  points with dates.
- **No Strava** (project rule, ch. 15 §15.3; its robots.txt also disallows
  ClaudeBot). **No raw MDS trips or Lime feed** (data.lime.bike:
  `Disallow: /`). **No BikeMaps.org JSON** (disallowed).
- **ACHD layers** state no license: internal and credited, like the
  `roads` plugin's ACHD sources; ask ACHD before republishing.
- **Boise's copy of ACHD's low-stress layer** forbids sharing, so use
  ACHD's own public layers instead.
- **Meridian** forbids redistribution: private schema.
- **COMPASS's swidrdc.org-only layers:** internal until COMPASS answers
  (the existing rule).
- **OpenStreetMap:** anything we publish built on OSM ways is an ODbL
  derivative. Never copy agency data into OSM; differences are hints for
  NAIP tracing only.
- **School walk zones** are shown as infrastructure, never tied to
  students.
- **Personal fields dropped at ingest** (correction 8): ACHD's
  `PAG_Comments` layer (not collected at all), Nampa's public-input
  points, `PrjMgr`, creator and editor fields, free-text comments and
  notes, and `Pathways_Master` photos (no bulk fetch).
- The owner's own GPS rides follow ch. 7's consent and trimming rules.

### Counts are the thin spot

- **Public:** 16 COMPASS Eco-Counter MULTI pathway sites with annual PDF
  reports for 2020–2023 (19 report sites), plus ACHD's counter locations
  (four marked "Future").
- **Not public:** on-street bike counts; hourly data (to ask COMPASS for;
  its page doesn't say it exists).
- No public Eco-Visio page turned up, but the web-search budget ran out
  before a full check ⚠️.
- ACHD's turning-movement counts might include pedestrians and bikes, if
  the private table copy has those columns (unknown; open question 8).

### Change detection

The `services1` and `services2` layers expose `editingInfo.lastEditDate`,
so check it before fetching (hourly Greenbelt checks then cost almost
nothing). gis.achdidaho.org and swidrdc.org layers don't: use the hub's
DCAT `modified` date, a count plus the latest `last_edited_date` where that
field exists (ACHD sidewalks, COMPASS layers), or a content hash (ACHD's
bike network). (Correction 9.)

### Effort (rough)

| Piece | Effort |
|---|---|
| ACHD, COMPASS and Boise layers | S each, with the shared ArcGIS reader |
| `osm_active` filter | M |
| LTS engine and validation | M–L |
| BNA runs | M |
| Routing core | L |
| Greenbelt closures | S |
| Counters | M (depends on COMPASS's format) |

### Licensing summary

| Terms | Sources |
|---|---|
| Public domain or CC0 | NHTSA FARS, Census ACS, EPA Walkability Index (CC0) |
| ODbL | OpenStreetMap and anything derived from it (our LTS on OSM ways, BNA outputs, a routing PBF) |
| MIT (code) | brokenspoke-analyzer; BRouter and Valhalla if chosen |
| Disclaimer, no redistribution limit stated; credit the city | Boise Pathways Master Plan, Greenbelt closures, markers and trees; Nampa's layers |
| Redistribute unaltered with metadata, or altered with credit | Boise's fire-GIS Greenbelt markers |
| No license: internal and credited until the agency answers | ACHD's bike, pedestrian, LTS, sidewalk and ArcGIS Online layers; COMPASS's swidrdc.org-only layers |
| Already decided | COMPASS crashes (road-user types publishable, Oct 6); ITD crash units (credit ITD) |
| Facts with a citation | VRT bike-share history, Ridge to Rivers status (summarized), City Ratings scores, the LTS method |
| No redistribution | Meridian pathways (private schema) |
| Avoid | Boise's copy of ACHD's low-stress layer, Lime, Strava, BikeMaps.org |
| Needs the owner | COMPASS counter and Data Bike data, Ride Report, a Census API key (or by-hand tables) |

## What verification changed in the design

Verification on Oct 7 of the design as well as the sources. Numbers are
referred to above.

1. **Counts.** COMPASS's counter layer has 28 rows, not 27: 16 COMPASS
   Eco-Counter MULTI sites and 12 ACHD rows, with two ACHD names listed
   twice and 4 marked "Future". Annual PDFs exist for 19 sites. The page
   offers earlier reports on request and never mentions hourly data, so
   "hourly on request" is our assumption to put to COMPASS. Caldwell's
   Indian Creek counter counts pedestrians only. The Eco-Visio check is
   still not done ⚠️.
2. **The `osm_active` mechanism.** osmium's `w/highway` filter already
   passes every highway way; `keep_way()` drops cycleways, paths, footways
   and plain residential streets afterwards. So the cheaper change is to
   widen the keep rule in Python, or add a sibling keep function over the
   same GeoJSON export, plus new node filters: `n/highway=crossing`,
   `n/kerb`, `n/barrier`, and
   `n/amenity=bicycle_parking,bicycle_repair_station,drinking_water`. Bike
   parking mapped as areas also needs `w/amenity=bicycle_parking`. A second
   full osmium pass isn't needed. The extract step clips to the valley box,
   so the ring needs its own extract, and whether Geofabrik's Idaho polygon
   reaches Ontario and Vale is unverified ⚠️. For a routable graph, respect
   grade separation: OSM `layer`, `bridge` and `tunnel`, and
   `Pathways_Master`'s `f_elev`/`t_elev`, which are z-levels (5 underpass,
   10 grade, 20 overpass), not elevations.
3. **Before and after, and the year slider.** In ACHD's network `YrBuilt`
   is text, and `YearAdded` is an integer that most likely records when a
   segment entered the GIS, not when it was built ⚠️. COMPASS calls its own
   year and date fields "generally unreliable/not updated". Using them as
   treatment dates would bias a before-and-after study. Check a sample
   against NAIP 2023 and 2025 and older imagery first, or limit the study
   to projects with known construction years (Five-Year Plan projects,
   `CNYear` in `Low_Stress_Routes`).
4. **BNA inputs.** The analyzer's speed inputs are `state_fips_speed.csv`
   and `city_fips_speed.csv`, which hold default speeds, so ACHD's
   per-segment speeds don't plug in ⚠️; segment speeds reach BNA only
   through OSM `maxspeed`. BNA also needs a population shapefile (Census
   blocks) and LODES CSVs. www2.census.gov has no robots rules for `*`;
   check the LEHD host's robots.txt before reusing `tools/lehd_flows.py`'s
   source. The docs don't name the analyzer's default download hosts, so
   placing every input beforehand is mandatory.
5. **Routing.** pgRouting is a separate extension, not part of PostGIS.
   Check that the `timescaledb-ha` image ships it
   (`pg_available_extensions`) before choosing it; adding or changing the
   database image is a server change that needs the owner's OK. BRouter
   builds its own segment files and uses coarse SRTM-class elevation, not
   our 1 m DEM, unless custom-built. A PBF with our derived LTS tags is an
   ODbL derivative: fine internally, ODbL if published.
6. **Display.** "Teal, blue, purple, orange" isn't an ordered ramp, and it
   ignores ch. 13's five-step data ramp (blue-teal, yellow, orange, magenta,
   purple). Map LTS 1–4 onto ch. 13's steps with monotone lightness, keep
   width and dash as the second channel, and run the colour-blindness
   check ch. 13 asks for. Drawing LTS 4 as the thinnest line de-emphasizes
   the most dangerous roads: that suits a "where can I ride" lens, but the
   safety lens should invert it.
7. **Safe routes.** Only the Boise district has bus and non-bus (walk)
   zones in ACHD's organisation; the West Ada and Kuna layers are
   attendance areas. Outside Boise, "crossings inside walk zones" needs
   another basis, such as a 1.5 mi radius, which Boise's own description
   uses for its busing boundary ⚠️.
8. **Personal data to drop at ingest:** ACHD's
   `Enhanced_Ped_Crossings` layer 0 `PAG_Comments` (members' names and
   comments); Nampa's `BikePed PublicInput_Pts`; `PrjMgr` (staff names) in
   the sidewalk projects; `created_user`, `last_edited_user`, `Creator` and
   `Editor` fields across ArcGIS Online and COMPASS layers; free-text
   `Comments`, `FieldNotes` and `Notes`; and `Pathways_Master`'s `piclink`
   photos (no bulk fetch).
9. **Change detection.** `services1` and `services2` layers expose
   `editingInfo.lastEditDate`, so check it before fetching (hourly
   Greenbelt checks are then nearly free). gis.achdidaho.org and swidrdc.org
   layers don't: use the DCAT `modified` date, a count plus the latest
   `last_edited_date` where that field exists (ACHD sidewalks, COMPASS
   layers), or a content hash (ACHD's bike network).
10. **Smaller fixes.** Bus racks hold "at least two" bikes. EPA's
    MapServers are disallowed by robots.txt (geodata.epa.gov
    `Disallow: /arcgis/`), so only the by-hand zip works; EPA's data is CC0
    per data.gov, on 2019 block groups. The Strava exclusion comes from
    ch. 15 §15.3, not CLAUDE.md. Nampa has a current (Sep 2026) Bike Routes
    & Pathways layer, so "stale 2021" is dropped. Ramp categories run 1–5,
    so the ACHD question covers both code sets. The walking LTS was last
    edited Mar 2026 (34,771 segments). Ride Report's configuration
    advertises route data, so "citywide only" may be wrong ⚠️. Ridge to
    Rivers reports run near-daily in winter.
11. **Worth adding.** ACHD's "LTS Street Trees" and "LTS Sidewalk
    Presence" (maps.achdidaho.org, robots.txt 404). Boise's Tree Canopy
    Study land-cover and canopy-change tiles, for the shade walk. The
    walking-LTS intersections' `Lamp_Count`, for "crashes in the dark" and
    lit routing. `PHB_flag` and the inaccessible button and ramp flags, for
    the accessibility view.
12. **An open question kept.** ITD's Ada 2023 figures (60 pedestrian, 91
    pedalcycle, 2 scooter and 1 moped units) reproduce exactly. Whether
    they're low can only be settled by comparing with
    `restricted.crash_unit` on the server.

## Open questions

For the owner, one at a time; none is decided.

1. **Where should cycling and walking live:** a new `active` plugin (the
   research's lean) or spread across `roads`, `safety` and `flow`, as
   ch. 15 suggests?
2. **OpenStreetMap:** OK to widen the OSM load (`osm_active`) over the same
   hand-downloaded extract, keeping paths, footways, cycleways, residential
   streets and bike and walk nodes? It's a larger set of ODbL tables. And a
   second extract for the Idaho part of the ring?
3. **LTS in Ada:** show ACHD's own LTS and Alta's 2023 scores as they are,
   our computed LTS, or both with conflicts flagged (as for lanes)?
4. **Routing:** is a routing graph a new core piece, and if so, pgRouting
   on our own graph (if the database image ships it, or with the owner's OK
   to change the image) or a self-hosted BRouter or Valhalla? The cyclist,
   walker, hiker, commuter and safe-routes ideas all need one.
5. **Owner action, COMPASS:** ask for hourly counter data from its 16
   Eco-Counter sites (2015 on), if it exists, and for the Data Bike
   pathway-roughness data; and add the ExistingBikeAndPed, Walkability and
   RegionalRoutes layers to the pending question about republishing.
6. **Owner action, ACHD:** ask whether its bike, pedestrian, LTS and
   sidewalk layers may be republished; what the sidewalk `Category` codes
   (1–4) and the ramp codes (1–5) mean; whether its own counters (Capitol
   Blvd, the Shamrock and Cassia bikeways, the Eagle Road pathway and
   others) have shareable data; and whether a public Eco-Visio page exists.
7. **Owner action (optional), City of Boise:** ask the program mailbox
   whether Ride Report's quarterly download may be stored and republished,
   whether street-level aggregate trip counts can be shared, and whether
   Lime would allow GBFS access (data.lime.bike's robots.txt disallows
   everything).
8. **ACHD's turning-movement copy:** does the private copy include
   pedestrian or bicycle columns per leg? If so, it gives on-street
   exposure counts at about 2,300 peak-hour rows.
9. **Work zones:** does ITD's WZDx feed ever type lanes as `bike-lane`,
   `sidewalk` or `shoulder`? A query on `evt.event` lanes would show
   whether work-zone bike and sidewalk closures can be drawn.
10. **ITD's crash counts:** 60 pedestrian and 91 pedalcycle units in Ada
    for 2023 looks low. Compare with COMPASS's unit types before using ITD
    for the regional ring.
11. **Census ACS:** get a free Census API key (owner), or download the
    tables by hand from data.census.gov or www2.census.gov? api.census.gov
    returned a WAF page instead of a robots.txt to our client.
12. **Display:** should the LTS colour scheme (four of ch. 13's ramp steps
    plus width and dash) be added to ch. 13's tokens, and is a "plain
    mode" (only LTS 1–2) wanted?
13. **Canal-side pathways** (Meridian especially): many run on
    irrigation-district easements. Should the router avoid canal roads
    unless a city lists them as public pathways? This overlaps the lands
    and permissions research.
