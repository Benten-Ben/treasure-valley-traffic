# Data source backlog

Every data source we've considered, what we've done with it, and what's
left. Kept so nothing gets lost between sessions (owner, Oct 6, 2026). The
full descriptions, access rules and licenses are in
[chapter 8](08-data-inventory.md) (data inventory) and
[chapter 9](09-base-map-data.md) (base-map data); decisions are in
[DECISIONS.md](DECISIONS.md). We go through sources one at a time with the
owner before committing to how each is used. Map layers designed for these
sources but left for a later round (intersections, crashes, lanes, growth)
are tracked in [DEFERRED.md](DEFERRED.md).

Last updated Oct 7, 2026.

## In use

| Source | What we do with it | Since |
|---|---|---|
| ACHD camera inventory | 228 cameras in `core.camera`, refreshed daily (`achd_cameras`) | Oct 5 |
| 511 Idaho camera images | 34 key cameras fetched every 50 s into daily AV1 videos (`cameras` service); calibrations in the app; live pictures in the app's camera windows (UI v2: the recorded cameras from our archive, others fetched only while open, [ch. 11 §11.8](11-camera-validation-layer.md#118-cameras-in-the-app-ui-v2-oct-2026)) | Oct 5 |
| ITD road-weather (RWIS) camera views | All 385 views at 130 stations statewide, plus 4 Oregon DOT views near Ontario and Weiser, every 10 min into daily videos (`regional` service) | Oct 5–6 |
| 511 Idaho camera list | One-off copies (Oct 5), kept privately; replaced on Oct 6 by the API's camera list (hourly), which rebuilds the road-weather capture list | Oct 5 |
| 511 Idaho API | All 11 endpoints (`idaho511` service, at most 8 calls a minute): events, advisories and truck restrictions (`evt.event`), message signs (`evt.sign_message`), road-weather readings from 127 stations (`obs.weather_reading`), winter road conditions, the camera list and the rest versioned; not republished | Oct 6 |
| Valley Regional Transit GTFS and GTFS-realtime | Routes, stops, shapes daily; bus positions every 30 s, archived raw; unlabeled trips matched to routes by path | Oct 5 |
| ACHD road centerlines | 38,727 Ada County segments with posted speed, class, one-way, level; the Streets layer | Oct 5 |
| ACHD counts and turning-movement tables | One-time private copy (owner-approved, Oct 5); not loaded into the database yet | Oct 5 |
| Ada County Assessor parcels, condos and parcel characteristics | One private copy on the server (owner OK, Oct 6): year built, dwelling units, commercial floor area. "Do not re-distribute": aggregates only, never committed or tiled; the county is asked whether its CC0 label applies | Oct 6 |
| Census commute flows (LEHD LODES8) | One-off analysis, `tools/lehd_flows.py`: who commutes between Ada, Canyon and the counties around them (results in ch. 8) | Oct 6 |
| ITD work zones (WZDx feed on 511 Idaho) | Every 5 min (`wzdx` service): versions in `raw.record`, cleaned rows in `evt.event`; 703 statewide, 239 in Ada and Canyon on Oct 6. Open to republish, crediting ITD ([ch. 8 §8.8](08-data-inventory.md#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026)) | Oct 6 |
| Base map | OpenStreetMap (Protomaps), USGS 3DEP terrain, NAIP 2023 imagery, Overture and Boise 3D buildings | Oct 5 |
| ACHD Official Bicycle Facility Network | Monthly (`achd_bike_network`, roads plugin): 3,932 records with curb-to-curb and right-of-way widths, per-direction lanes, bike facilities, buffers and parking, and ACHD's LTS; matched to ACHD's segments for the real-width roads. Internal, credited to ACHD; its free-text notes stay out of every export ([docs/sources/cycling.md](sources/cycling.md#achd-official-bicycle-facility-network)) | Oct 11 (scratch; production at the next deploy) |
| USDA NRCS soil survey (SSURGO), ten survey areas | Yearly, by hand (`soils`): the soil card, the Soils layer, and the ground's base, where each soil type gets its own colour and texture measured from the NAIP 2025 photo over its uncovered ground; the card says "Not for regulatory decisions" ([plugin README](../plugins/soils/README.md)) | Oct 2026 |
| Copernicus Sentinel-2 (2025) | Two images in `trees` for the conifer cue (early April and July); the photo statistics in `soils` (the green rule, the NDVI curves, the colour gains). Credit "Contains modified Copernicus Sentinel data 2025" | Oct 2026 |
| USGS 3DEP lidar | Tree and shrub points in `trees`, by hand: every tree in the lidar, catalogued trees first; each box keeps its own vintage (2019–20 or 2023–24), labelled ([plugin README](../plugins/trees/README.md)) | Oct 2026 |
| USGS National Hydrography Dataset, HU4 1705 | Cut to the map box and loaded by hand into `water` (`nhd_hr`): rivers, creeks, canals and ponds; OpenStreetMap's waterways carry its facts. Downloaded again Oct 11 | Oct 11 |
| U.S. Fish and Wildlife Service (USFWS), National Wetlands Inventory, October 2026 release | One download by hand (owner OK, Oct 22), no schedule: the eight watershed (HU8) files that touch the map box, 337 MB, cut to the box and kept as a GeoPackage on the server with a provenance note: 23,797 wetland polygons, 389 riparian polygons, and the layers that give each area's image year (the valley floor is mapped from July 1981 photos). Not loaded into the database yet. Public domain; credit "U.S. Fish and Wildlife Service, National Wetlands Inventory". When Water draws it (decisions, Oct 22, answer 2), every card will say "Not a legal (regulatory) wetland boundary" | Oct 22 |
| USDA NASS Cropland Data Layer and Crop Sequence Boundaries | `farm`, by hand, each yearly edition with the owner's OK: estimated crop fields with their crops, how sure USDA is, and whether they were green in July; the crop class for the ground. The CDL also feeds `roads`' developed-land check | Oct 2026 |
| HydroShare, Treasure Valley Irrigation System canal network (CC BY 4.0) | `water` (`hydroshare_canals`, by hand): canal names and the canal network, joined to NHD's and OpenStreetMap's lines. Credit Tatum, Bittmann, Stone and Kaiser (2022), doi:10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f | Oct 2026 |
| IDWR irrigation organizations and season of use | `water` (`idwr_irrigation_orgs`, `idwr_season_of_use`): the organizations on the canal cards, and the legal season that sets each canal's season (on, off or unknown). Internal, with a courtesy note to IDWR | Oct 2026 |
| OpenStreetMap street and paving tags | `roads` (`osm_street`, `osm_paving`): street classes, paving surfaces and lane tags from the held extract, loaded by `osm-load`. ODbL; credit "© OpenStreetMap contributors" | Oct 2026 |
| Chapter 17 Wave A pollers (Oct 7) | 22 sources in nine new plugins, started so their history exists from now on: fire restrictions, WFIGS fires and perimeters, FIRMS, NWS alerts and quakes (`hazards`); HMS smoke (`air`); NWPS gauges, SNOTEL, E. coli, river hazards, drought (`water`); R2R conditions and Greenbelt closures (`trails`); forest orders and IDPR closures (`lands`); METARs (`weather`); roadkill (`wildlife`); AgriMet ET (`farm`); aurora and Kp (`sky`). Versions in `raw.record`, lifecycles in `evt.event`; each plugin's README has its endpoints, cadence, licence and what's kept ([ch. 17 §17.4](17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)) | Oct 7 |

## Open sources: on the board

Open source work is an issue on the project's GitHub board, not a row here.
The tracking issue for this list is
[#4](https://github.com/Benten-Ben/treasure-valley-traffic/issues/4). Built
sources awaiting a production load are tracked by the production-load
issues ([#42](https://github.com/Benten-Ben/treasure-valley-traffic/issues/42)–[#50](https://github.com/Benten-Ben/treasure-valley-traffic/issues/50)).

| Theme | Source | Status | Access | Issue |
|---|---|---|---|---|
| Volumes | ITD AADT by segment, 1999–2025 | Prototype script only (`tools/collect_static.py`) | Open GIS | [#85](https://github.com/Benten-Ben/treasure-valley-traffic/issues/85) |
| Volumes | ITD permanent counters, monthly (45 in Ada and Canyon) | Prototype script only | Open GIS | [#86](https://github.com/Benten-Ben/treasure-valley-traffic/issues/86) |
| Volumes | ITD hourly counter reports | Not started | Open PDFs; need extracting | [#87](https://github.com/Benten-Ben/treasure-valley-traffic/issues/87) |
| Volumes | ACHD `Traffic_Counts` layer | Checked Oct 5: 3,880 locations, no counts | Open GIS | [#4](https://github.com/Benten-Ben/treasure-valley-traffic/issues/4) |
| Safety | ITD crash points, 2005–2023 | Not started | Open GIS | [#88](https://github.com/Benten-Ben/treasure-valley-traffic/issues/88) |
| Safety | COMPASS crash data, 2008–2025, and high-injury network | Approved Oct 6; build timing with the owner | Disclaimer; credit COMPASS | [#185](https://github.com/Benten-Ben/treasure-valley-traffic/issues/185) |
| Safety | COMPASS Regional Safety Action Plan layers (`Final_RSAP_Junctions`, `Final_RSAP_Segments_for_Dashboard`) | Found, not examined | COMPASS GIS; terms not checked | [#89](https://github.com/Benten-Ben/treasure-valley-traffic/issues/89) |
| Safety | ITD Numetric safety dashboards | Found, not opened | Web dashboards; not checked | [#90](https://github.com/Benten-Ben/treasure-valley-traffic/issues/90) |
| Events | ACHD live roadwork, incidents, message signs | Not started | Open GIS | [#91](https://github.com/Benten-Ben/treasure-valley-traffic/issues/91) |
| Network | Overture transportation | Not started; the long-term reference network is undecided (ch. 12, decision 5) | ODbL | [#255](https://github.com/Benten-Ben/treasure-valley-traffic/issues/255) |
| Network | ACHD Master Street Map: Collectors service | Not examined (Arterials built) | Open GIS; no license | [#92](https://github.com/Benten-Ben/treasure-valley-traffic/issues/92) |
| Network | ACHD roundabouts (190) and Five-Year Plan intersection projects (574) | Found Oct 6 | Open GIS | [#93](https://github.com/Benten-Ben/treasure-valley-traffic/issues/93) |
| Network | ACHD Five-Year Plan road projects (991 features; 2026–30 plan) | Not started | Open GIS | [#94](https://github.com/Benten-Ben/treasure-valley-traffic/issues/94) |
| Network | Other COMPASS layers: node types, CIM model links, detectors and Bluetooth readers, sidewalks, bike facilities, schools | Found, not examined | COMPASS GIS; not checked | [#95](https://github.com/Benten-Ben/treasure-valley-traffic/issues/95) |
| Congestion | COMPASS `Congestion_Management_Performance_Measures_2018_2021` | Found, not compared | COMPASS GIS; not checked | [#96](https://github.com/Benten-Ben/treasure-valley-traffic/issues/96) |
| Congestion | COMPASS "Change in Motion" dashboard and congestion web app | Found, not examined | Web apps; not checked | [#97](https://github.com/Benten-Ben/treasure-valley-traffic/issues/97) |
| Transit | National Transit Database monthly data (`ntd_id='00011'`) | Used once, Oct 5; could be re-checked monthly | Public domain; robots.txt allows `/resource/` with Crawl-delay 1 | [#98](https://github.com/Benten-Ben/treasure-valley-traffic/issues/98), [#99](https://github.com/Benten-Ben/treasure-valley-traffic/issues/99) |
| Context | Boise airport weather history (IEM ASOS) | Not started | Open; 120 s crawl delay | [#100](https://github.com/Benten-Ben/treasure-valley-traffic/issues/100) |
| Context | ACHD and COMPASS 3-inch aerial imagery, 2024 and 2025 | View on request only (owner, Oct 6) | No license stated | [#101](https://github.com/Benten-Ben/treasure-valley-traffic/issues/101) |
| Context | COMPASS growth and counts (traffic zones, permits, plats, counts) | Approved Oct 6; build timing with the owner | Disclaimer; credit COMPASS | [#186](https://github.com/Benten-Ben/treasure-valley-traffic/issues/186) |
| Context | City of Boise open data (88 entries) | Reviewed Oct 6; queued after the core pieces | City disclaimer | [#102](https://github.com/Benten-Ben/treasure-valley-traffic/issues/102) |
| Context | Federal benchmarks: FARS, ACS commuting, TTI Urban Mobility | Not started | Public domain | [#103](https://github.com/Benten-Ben/treasure-valley-traffic/issues/103) |
| Context | Mapillary street-level photos | Coverage unchecked | Free token; CC BY-SA | [#105](https://github.com/Benten-Ben/treasure-valley-traffic/issues/105) |
| Oregon | ODOT TripCheck cameras and data | New, needs vetting | Registration | [#106](https://github.com/Benten-Ben/treasure-valley-traffic/issues/106) |
| Cameras | ITD's own camera views on 511 | Left out; two ACHD cameras missing from 511's list | 511 route | [#157](https://github.com/Benten-Ben/treasure-valley-traffic/issues/157) |
| Cameras | ITD's ITS layer: 82 CCTV locations statewide | Found, not examined | Open GIS | [#107](https://github.com/Benten-Ben/treasure-valley-traffic/issues/107) |
| Cameras | The 18 ACHD cameras not on 511 | Ongoing capture needs ACHD's OK; a one-off look was suggested Oct 5 | Asked in the draft ACHD note | [#108](https://github.com/Benten-Ben/treasure-valley-traffic/issues/108), [#109](https://github.com/Benten-Ben/treasure-valley-traffic/issues/109) |
| Our own | Volunteer GPS drive runs | Tool ready (`tools/gps_runs.py`), no runs yet | Consent rules (ch. 7) | [#110](https://github.com/Benten-Ben/treasure-valley-traffic/issues/110) |
| Our own | Sidewalk signal observations | Not started | Fully ours | [#111](https://github.com/Benten-Ben/treasure-valley-traffic/issues/111) |

Built sources still to be checked or loaded are on the board too
([#42](https://github.com/Benten-Ben/treasure-valley-traffic/issues/42)–[#50](https://github.com/Benten-Ben/treasure-valley-traffic/issues/50),
[#163](https://github.com/Benten-Ben/treasure-valley-traffic/issues/163)).

### OpenStreetMap first load (Oct 7)

Done by hand on Oct 7 from Geofabrik's Idaho extract of Oct 5 (129 MB):
one download with our honest User-Agent, MD5 checked. These numbers
replace the May 2026 Overpass counts this page gave before (752 signal
nodes, `lanes` on 72% of major roads ⚠️).

| Loaded | Count |
|---|---|
| Valley ways | 13,917 (10,614 with `lanes`) |
| Lane rows | 25,701 |
| Traffic-signal nodes | 767 |
| Crossing signals | 1,742 |
| Level crossings | 345 |
| ACHD segments matched | 14,054, plus 2,222 turn-bay matches (the way-in-buffer rule, [DECISIONS](DECISIONS.md)) |

Which source now sets each ACHD segment's lane count (`core.segment_lanes`,
by the rule in [ch. 9 §9.3](09-base-map-data.md#93-streets-network-and-lanes)):

| Source | ACHD segments |
|---|---|
| OpenStreetMap | 7,636 |
| ACHD Master Street Map | 3,776 |
| ITD HPMS | 1,116 |
| COMPASS centerline | 206 |
| Assumed | 25,699 (33,023 before the load) |

Flagged conflicts rose to 651 (from 207), because OpenStreetMap is a second
opinion on segments other sources already cover. The intersections rebuild
after the load gave 633 in `core.intersection` (585 active, 43 candidates,
5 retired; before, 591 with 1 candidate); 42 of the candidates are new OSM
signal nodes with no COMPASS match and need review
([ingest/README](../ingest/README.md)).

## Built, awaiting a production load or a history load

These are built and checked (scratch or the server), with the deploy, the
history load or the owner's decision still to come. Each row keeps what
the source covers and why it matters; the open items are on the board
(the issue links are in the table above and in [DEFERRED.md](DEFERRED.md)).

| Theme | Source | Status | Why it matters | Access |
|---|---|---|---|---|
| Safety | ITD crash points, 461,521 crashes 2005–2023 | Not started; COMPASS's copy for Ada and Canyon runs to 2025 (below) | High-crash intersections, before/after studies | Open GIS |
| Safety | COMPASS crash data: 174,038 crashes 2008–2025 linked to segments and intersections; high-injury network ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Approved Oct 6; build timing with the owner | Two more years than ITD's layer, already tied to the network | Disclaimer; credit COMPASS |
| Congestion | COMPASS congestion measures 2018–2025 by segment and commute travel times ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Approved Oct 6 for internal use; republishing waits on COMPASS | The official congestion history; a baseline for bus-derived speeds | Not offered as open data |
| Network | ACHD signal-asset points (2022): 2,469 signal **poles** (about 464 intersections), 182 pedestrian signals, 33 school flashers | Built Oct 6 (`achd_signal_points`, monthly; deploy pending); confirms intersections | The backbone: intersections that tie cameras, counts, crashes and bus delay together | Open; frozen since 2022 |
| Network | COMPASS Signalized_Intersections (585, one per intersection, with ACHD's Synchro IDs, coordination groups, right-turn lanes, phasing) and Regional_Signals (1,078) ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Built Oct 6 (`compass_signals`, `compass_regional_signals`, weekly; deploy pending); seeds `core.intersection` (591, 585 active, before the OpenStreetMap load; 633 after it, below) | One record per signalized intersection | No license ("for reference"); credit COMPASS; internal until COMPASS answers |
| Network | FRA highway–rail crossings, 433 in Ada and Canyon (131 open public at grade) | Built Oct 6 (`fra_crossings`, weekly; history not loaded; deploy pending) | Rail crossings near signals; preemption (filled only for Boise Valley Railroad) | Public domain |

## Needs the owner's network, or a request

These are on the board: the owner's network route is
[#176](https://github.com/Benten-Ben/treasure-valley-traffic/issues/176), and
the requests are [#163](https://github.com/Benten-Ben/treasure-valley-traffic/issues/163)
(ACHD: timing sheets, ATSPM, detectors, Connect requests, internal layers) and
[#177](https://github.com/Benten-Ben/treasure-valley-traffic/issues/177) (probe speeds from ITD or COMPASS, police crash narratives).
The Overpass, Geofabrik and Internet Archive routes are covered by
[#78](https://github.com/Benten-Ben/treasure-valley-traffic/issues/78) and the server-side OpenStreetMap processing.

## Candidate sources for new plugins (researched Oct 7)

For the owner's interests beyond traffic, 306 sources were researched on
Oct 7 and checked against their official pages, robots.txt and terms
(160 confirmed, 134 corrected, 7 unverifiable). On Oct 7 the owner asked
the lead to settle the open questions and start polling: Wave A's sources
are in use (above); the rest follow ch. 17's plan. The recommendations, the first thing to build
per persona, the sources to avoid and why, and the open questions are in
[chapter 17](17-sources-for-new-plugins.md). The catalogs:

| Theme | Catalog | Sources |
|---|---|---|
| Weather (radar, satellite, models, observations, climate) | [sources/weather.md](sources/weather.md) | 30 |
| Weather in 3D (data and rendering) | [sources/weather-3d.md](sources/weather-3d.md) | 31 |
| Fire and hazards (smoke, alerts, floods, quakes, drought) | [sources/hazards.md](sources/hazards.md) | 34 |
| Wildlife | [sources/wildlife.md](sources/wildlife.md) | 28 |
| Sky (sun, moon, glare, satellites, night sky) | [sources/sky.md](sources/sky.md) | 43 |
| Gardening (sun and shade, frost, soil, water) | [sources/gardening.md](sources/gardening.md) | 32 |
| Farms and crops | [sources/farm.md](sources/farm.md) | 29 |
| Land ownership and permissions | [sources/lands.md](sources/lands.md) | 22 |
| Trails, camping and recreation | [sources/trails.md](sources/trails.md) | 29 |
| Cycling and walking | [sources/cycling.md](sources/cycling.md) | 28 |

Each catalog's sources are on the board: weather [#112](https://github.com/Benten-Ben/treasure-valley-traffic/issues/112)–[#115](https://github.com/Benten-Ben/treasure-valley-traffic/issues/115), hazards [#116](https://github.com/Benten-Ben/treasure-valley-traffic/issues/116)–[#122](https://github.com/Benten-Ben/treasure-valley-traffic/issues/122), lands [#123](https://github.com/Benten-Ben/treasure-valley-traffic/issues/123)–[#131](https://github.com/Benten-Ben/treasure-valley-traffic/issues/131), wildlife [#140](https://github.com/Benten-Ben/treasure-valley-traffic/issues/140)–[#142](https://github.com/Benten-Ben/treasure-valley-traffic/issues/142), sky [#143](https://github.com/Benten-Ben/treasure-valley-traffic/issues/143)–[#148](https://github.com/Benten-Ben/treasure-valley-traffic/issues/148), trails [#132](https://github.com/Benten-Ben/treasure-valley-traffic/issues/132)–[#137](https://github.com/Benten-Ben/treasure-valley-traffic/issues/137), farm [#151](https://github.com/Benten-Ben/treasure-valley-traffic/issues/151)–[#155](https://github.com/Benten-Ben/treasure-valley-traffic/issues/155), gardening [#149](https://github.com/Benten-Ben/treasure-valley-traffic/issues/149)–[#150](https://github.com/Benten-Ben/treasure-valley-traffic/issues/150), cycling [#138](https://github.com/Benten-Ben/treasure-valley-traffic/issues/138)–[#139](https://github.com/Benten-Ben/treasure-valley-traffic/issues/139). Several of them keep only their current state, so their history exists only
if we poll from now on (ch. 17 §17.1).

## Suggested order

The order is on the board: signals and intersections, crashes, work zones
and incidents, traffic volumes, then the 511 API, which is recording. Each
step's issues are linked from [#4](https://github.com/Benten-Ben/treasure-valley-traffic/issues/4).
