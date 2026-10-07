# Data source backlog

Every data source we've considered, what we've done with it, and what's
left. Kept so nothing gets lost between sessions (owner, Oct 6, 2026). The
full descriptions, access rules and licenses are in
[chapter 8](08-data-inventory.md) (data inventory) and
[chapter 9](09-base-map-data.md) (base-map data); decisions are in
[DECISIONS.md](DECISIONS.md). We go through sources one at a time with the
owner before committing to how each is used.

Last updated Oct 7, 2026.

## In use

| Source | What we do with it | Since |
|---|---|---|
| ACHD camera inventory | 228 cameras in `core.camera`, refreshed daily (`achd_cameras`) | Oct 5 |
| 511 Idaho camera images | 34 key cameras fetched every 50 s into daily AV1 videos (`cameras` service); calibrations in the app | Oct 5 |
| ITD road-weather (RWIS) camera views | All 385 views at 130 stations statewide, plus 4 Oregon DOT views near Ontario and Weiser, every 10 min into daily videos (`regional` service) | Oct 5–6 |
| 511 Idaho camera list | One-off copies (Oct 5), kept privately; replaced on Oct 6 by the API's camera list (hourly), which rebuilds the road-weather capture list | Oct 5 |
| 511 Idaho API | All 11 endpoints (`idaho511` service, at most 8 calls a minute): events, advisories and truck restrictions (`evt.event`), message signs (`evt.sign_message`), road-weather readings from 127 stations (`obs.weather_reading`), winter road conditions, the camera list and the rest versioned; not republished | Oct 6 |
| Valley Regional Transit GTFS and GTFS-realtime | Routes, stops, shapes daily; bus positions every 30 s, archived raw; unlabeled trips matched to routes by path | Oct 5 |
| ACHD road centerlines | 38,727 Ada County segments with posted speed, class, one-way, level; the Streets lens | Oct 5 |
| ACHD counts and turning-movement tables | One-time private copy (owner-approved, Oct 5); not loaded into the database yet | Oct 5 |
| Ada County Assessor parcels, condos and parcel characteristics | One private copy on the server (owner OK, Oct 6): year built, dwelling units, commercial floor area. "Do not re-distribute": aggregates only, never committed or tiled; the county is asked whether its CC0 label applies | Oct 6 |
| Census commute flows (LEHD LODES8) | One-off analysis, `tools/lehd_flows.py`: who commutes between Ada, Canyon and the counties around them (results in ch. 8) | Oct 6 |
| ITD work zones (WZDx feed on 511 Idaho) | Every 5 min (`wzdx` service): versions in `raw.record`, cleaned rows in `evt.event`; 703 statewide, 239 in Ada and Canyon on Oct 6. Open to republish, crediting ITD ([ch. 8 §8.8](08-data-inventory.md#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026)) | Oct 6 |
| Base map | OpenStreetMap (Protomaps), USGS 3DEP terrain, NAIP 2023 imagery, Overture and Boise 3D buildings | Oct 5 |

## Not started, or only partly

"Found, not examined" means a layer turned up during the Oct 4–6 source
reviews and nobody has opened it since.

| Theme | Source | Status | Why it matters | Access |
|---|---|---|---|---|
| Volumes | ITD AADT by segment, 1999–2025 | Prototype script only (`tools/collect_static.py`) | Long-term growth on state routes | Open GIS |
| Volumes | ITD permanent counters, monthly (45 in Ada and Canyon) | Prototype script only | Seasonal and year-over-year trends | Open GIS |
| Volumes | ITD hourly counter reports | Not started | Peak spreading and growth by hour | Open PDFs; need extracting |
| Volumes | ACHD `Traffic_Counts` layer | Checked Oct 5: 3,880 count locations, no counts | Locations only; the counts are in the private table copy | Open GIS |
| Safety | ITD crash points, 461,521 crashes 2005–2023 | Not started; COMPASS's copy for Ada and Canyon runs to 2025 (below) | High-crash intersections, before/after studies | Open GIS |
| Safety | COMPASS crash data: 174,038 crashes 2008–2025 linked to segments and intersections; high-injury network ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Approved Oct 6; build timing with the owner | Two more years than ITD's layer, already tied to the network | Disclaimer; credit COMPASS |
| Safety | COMPASS Regional Safety Action Plan dashboard layers: `Final_RSAP_Junctions` and `Final_RSAP_Segments_for_Dashboard` | Found, not examined | The plan's own junctions and segments (its findings are in [ch. 3](03-traffic-context-and-data.md)) | COMPASS GIS; terms not checked |
| Safety | ITD's Numetric safety dashboards (`itd.numetric.net/itd-safety-dashboards`) | Found, not opened | ITD's own safety summaries, a check on the crash layers | Web dashboards; not checked |
| Events | ACHD live roadwork, incidents, message signs | Not started | Same | Open GIS |
| Network | ACHD signal-asset points (2022): 2,469 signal **poles** (about 464 intersections), 182 pedestrian signals, 33 school flashers | Built Oct 6 (`achd_signal_points`, monthly; deploy pending); confirms intersections | The backbone: intersections that tie cameras, counts, crashes and bus delay together | Open; frozen since 2022 |
| Network | COMPASS Signalized_Intersections (585, one per intersection, with ACHD's Synchro IDs, coordination groups, right-turn lanes, phasing) and Regional_Signals (1,078) ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Built Oct 6 (`compass_signals`, `compass_regional_signals`, weekly; deploy pending); seeds `core.intersection` (591, 585 active, before the OpenStreetMap load; 633 after it, below) | One record per signalized intersection | No license ("for reference"); credit COMPASS; internal until COMPASS answers |
| Network | OpenStreetMap signals and lane tags (`lanes`, `turn:lanes`): 767 signal nodes, 10,614 valley ways with `lanes` | Built Oct 6 (`osm_valley`); **first load by hand Oct 7** ([below](#openstreetmap-first-load-oct-7)). By hand only, since Geofabrik's robots.txt disallows scripted downloads; the owner downloads the Idaho extract weekly and a note asks Geofabrik | Signal locations; lane counts and turn lanes where mapped | ODbL; own tables |
| Network | ITD HPMS road inventory (19,801 through-lane records in the box) | Built (`itd_hpms`, monthly); sets the lanes on 1,116 ACHD segments after the Oct 7 load | Through lanes on state routes (unreliable on ACHD arterials), turn lanes, medians | Open GIS; credit ITD |
| Network | Overture transportation | Not started; the long-term reference network is still undecided (ch. 12, decision 5) | Stable segment IDs; speed limits on about 14k segments | ODbL |
| Network | ACHD Master Street Map: Arterials layer (1,049 arterial segments) | Built (`achd_msm`, monthly); sets the lanes on 3,776 ACHD segments after the Oct 7 load. A separate **Collectors** service exists and hasn't been examined | Existing, funded and planned lanes on Ada arterials (blank on state routes) | Open GIS; no license |
| Network | ACHD roundabouts (190) and Five-Year Plan intersection projects (574) | Found Oct 6 | Intersection control types; planned changes for before/after | Open GIS |
| Network | ACHD Five-Year Plan road projects (`gis.achdidaho.org/server/rest/services/ArcGIS_Hub/FYP_Road_Projects/FeatureServer/1`): 991 project features with design, right-of-way and construction years and cost. Example: State St, Pierce Park to Collister, widened to 7 lanes, design 2029–30. The 2026–30 plan has 266 projects, about $1.2B ([ch. 3](03-traffic-context-and-data.md)) | Not started | Planned changes, for before/after | Open GIS |
| Network | COMPASS RegionalCenterline (62,213 segments, Ada and Canyon) | Built (`compass_centerline`, monthly); sets the lanes on 206 ACHD segments after the Oct 7 load | Canyon County speeds and lanes; `pm_id` links COMPASS's counts, crashes and model | Disclaimer; reachable again |
| Network | Other COMPASS layers: Intersection Nodes with Type, the Communities in Motion (CIM) model links, detectors and Bluetooth readers, sidewalks and bike facilities, schools | Found, not examined | Intersection types; the regional model's network; where agencies already sense traffic | COMPASS GIS; not checked |
| Network | FRA highway–rail crossings, 433 in Ada and Canyon (131 open public at grade) | Built Oct 6 (`fra_crossings`, weekly; history not loaded; deploy pending) | Rail crossings near signals; preemption (filled only for Boise Valley Railroad) | Public domain |
| Congestion | COMPASS congestion measures 2018–2025 by segment and commute travel times ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Approved Oct 6 for internal use; republishing waits on COMPASS | The official congestion history; a baseline for bus-derived speeds | Not offered as open data |
| Congestion | COMPASS `Congestion_Management_Performance_Measures_2018_2021` | Found, not examined; not yet compared with the 2018–2025 measures above | A second congestion-measures layer; how it differs from the one above is unknown | COMPASS GIS; not checked |
| Congestion | COMPASS "Change in Motion" dashboard and the interactive congestion measures 2018–2024 web app ([ch. 3](03-traffic-context-and-data.md) links the congestion map) | Found, not examined | COMPASS's own presentation of the measures | Web apps; not checked |
| Transit | National Transit Database monthly data (data.transportation.gov resource `8bui-9xvu`; `ntd_id='00011'` is VRT): by mode, type of service (`tos`) and month (`date`), vehicles operated at peak (`voms`) and trips (`upt`) | Used once, Oct 5, to confirm the bus feed covers the whole 42-bus peak fleet ([ch. 8](08-data-inventory.md)); could be re-checked monthly | A monthly check of the buses we see against VRT's peak fleet; ridership over time (ch. 3 cites it for 2019–2025 ridership) | Public domain; robots.txt allows `/resource/` with Crawl-delay 1 (as for FRA) |
| Context | Boise airport weather history (IEM ASOS) | Not started | Tests the fog → detector fallback → long greens theory (ch. 2) | Open; 120 s crawl delay |
| Context | ACHD 3-inch aerial imagery, 2024 and 2025 (really COMPASS's) | View on request only (owner, Oct 6); asked of ACHD and COMPASS; if yes, a private 2–4 GB copy around signals and cameras | Lane markings, turn-bay lengths, signal heads, calibration points | No license stated |
| Context | COMPASS growth and counts: traffic-zone demographics (forecasts to 2055), building permits since 2000, preliminary plats, latest counts from every agency ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Approved Oct 6; build timing with the owner | Growth and demand; Canyon County volumes | Disclaimer; credit COMPASS |
| Context | City of Boise open data (88 entries) ([ch. 8 §8.9](08-data-inventory.md#89-second-source-review-oct-6-2026)) | Reviewed Oct 6; development pipeline and police-call aggregates queued after the core pieces (owner) | Development pipeline; crash-call timing by tract; street lights and parking meters | City disclaimer |
| Context | Federal: FARS fatal crashes, census commuting (ACS), TTI Urban Mobility | Not started | Benchmarks | Public domain |
| Context | Mapillary street-level photos | Coverage unchecked | Lane and sign checks | Free token; CC BY-SA |
| Oregon | ODOT TripCheck cameras and data | New, needs vetting | The Ontario end of the I-84 corridor | Registration |
| Cameras | ITD's own camera views on 511 | Left out: PNGs of 0.4–2.5 MB, mostly ACHD cameras republished. Two of them (I-184 Exit 0, I-184 & Chinden) are ACHD cameras missing from 511's ACHD list | Two more angles | 511 route |
| Cameras | ITD's ITS layer (`IntelligentTransportationSystems/FeatureServer/0`): 82 CCTV locations statewide | Found, not examined | Where ITD's own cameras are, to check against 511's list | Open GIS; ITD's GIS contact is GIS-Info@itd.idaho.gov |
| Cameras | The 18 ACHD cameras not on 511: mostly IDs 717–729 and a few I-184 cameras (e.g. Chinden & SH-16 southbound ramp, 619) | Ongoing capture needs ACHD's OK. A one-off look at ACHD's own images of them, to see what they cover, was suggested Oct 5 under the one-off-checks rule; no record that it was done. Only 619 is described ([ch. 11](11-camera-validation-layer.md)) | Missing angles | Asked in the draft ACHD note |
| Our own | Volunteer GPS drive runs | Tool ready (`tools/gps_runs.py`), no runs yet | Travel time and stops per signal | Consent rules (ch. 7) |
| Our own | Sidewalk signal observations | Not started | Cycle lengths and splits | Fully ours |

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

## Needs the owner's network (the local helper could fetch these)

- ACHD's main website (agendas, minutes, budget documents): blocks
  datacenter traffic.
- ITD's count database (`itd.ms2soft.com`): detailed count records.
- Overpass (OSM queries), Geofabrik's downloads and the Internet Archive (OpenStreetMap is processed on the server instead).

## Needs a request

| Data | Holder | Route |
|---|---|---|
| Signal timing sheets, coordination plans, last-retimed dates | ACHD (ITD for state routes) | Records request; the draft note to ACHD waits on the owner |
| **High-resolution controller event logs (ATSPM)**: the single most valuable dataset | ACHD | Records request or data-sharing agreement |
| Detector configuration and trouble tickets | ACHD | Records request |
| ACHD Connect service requests (e.g. "signal malfunction") | ACHD | Records request |
| ACHD's internal traffic and signal GIS layers | ACHD | Login only |
| Probe speeds (NPMRDS, INRIX) | ITD, COMPASS | Partnership |
| Police crash narratives | Police, ITD | $7 per report, or records request |

## Suggested order

1. **Signals and intersections** (COMPASS's signals, ACHD's poles,
   OpenStreetMap), then **rail crossings** and **lanes** (Master Street
   Map, ITD HPMS, OpenStreetMap): approved Oct 6.
2. **Crashes** (COMPASS's linked copy to 2025, ITD's for history).
3. **Work zones and incidents** (ITD WZDx: recording since Oct 6; ACHD live layers).
4. **Traffic volumes** (ITD AADT, counters, hourly reports).
5. **The 511 API**: recording since Oct 6.
