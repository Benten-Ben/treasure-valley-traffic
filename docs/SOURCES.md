# Data source backlog

Every data source we've considered, what we've done with it, and what's
left. Kept so nothing gets lost between sessions (owner, Oct 6, 2026). The
full descriptions, access rules and licenses are in
[chapter 8](08-data-inventory.md) (data inventory) and
[chapter 9](09-base-map-data.md) (base-map data); decisions are in
[DECISIONS.md](DECISIONS.md). We go through sources one at a time with the
owner before committing to how each is used.

Last updated Oct 6, 2026.

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
| Census commute flows (LEHD LODES8) | One-off analysis, `tools/lehd_flows.py`: who commutes between Ada, Canyon and the counties around them (results in ch. 8) | Oct 6 |
| ITD work zones (WZDx feed on 511 Idaho) | Every 5 min (`wzdx` service): versions in `raw.record`, cleaned rows in `evt.event`; 703 statewide, 239 in Ada and Canyon on Oct 6. Open to republish, crediting ITD ([ch. 8 §8.8](08-data-inventory.md#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026)) | Oct 6 |
| Base map | OpenStreetMap (Protomaps), USGS 3DEP terrain, NAIP 2023 imagery, Overture and Boise 3D buildings | Oct 5 |

## Not started, or only partly

| Theme | Source | Status | Why it matters | Access |
|---|---|---|---|---|
| Volumes | ITD AADT by segment, 1999–2025 | Prototype script only (`tools/collect_static.py`) | Long-term growth on state routes | Open GIS |
| Volumes | ITD permanent counters, monthly (45 in Ada and Canyon) | Prototype script only | Seasonal and year-over-year trends | Open GIS |
| Volumes | ITD hourly counter reports | Not started | Peak spreading and growth by hour | Open PDFs; need extracting |
| Volumes | ACHD `Traffic_Counts` layer | Checked Oct 5: 3,880 count locations, no counts | Locations only; the counts are in the private table copy | Open GIS |
| Safety | ITD crash points, 461,521 crashes 2005–2023 | Not started | High-crash intersections, before/after studies | Open GIS |
| Events | ACHD live roadwork, incidents, message signs | Not started | Same | Open GIS |
| Network | ACHD signal-asset points (2022): 2,469 signal points, 182 pedestrian signals, 33 school flashers | Not started | The backbone: intersections that tie cameras, counts, crashes and bus delay together | Open |
| Network | OpenStreetMap signals and lane tags (`lanes`, `turn:lanes`) | In the map tiles only | Signal locations; lane counts and turn lanes where mapped | ODbL |
| Network | ITD HPMS road inventory | Not started | Through lanes by direction, turn lanes, lane width, medians on state and major roads | Open GIS |
| Network | Overture transportation | Not started; the long-term reference network is still undecided (ch. 12, decision 5) | Stable segment IDs; speed limits on about 14k segments | ODbL |
| Network | ACHD Master Street Map | Not started | Existing and planned lanes on arterials and collectors | Open GIS |
| Network | ACHD Five-Year Plan projects | Not started | Planned changes, for before/after | Open GIS |
| Network | COMPASS regional centerlines | Blocked from the cloud session | Links to the travel model and crash data | Needs a normal network |
| Network | FRA highway–rail crossings, 433 in Ada and Canyon | Not started | Rail crossings near signals; trains blocking crossings | Open API |
| Context | Boise airport weather history (IEM ASOS) | Not started | Tests the fog → detector fallback → long greens theory (ch. 2) | Open; 120 s crawl delay |
| Context | ACHD 3-inch aerial imagery, 2024 and 2025 | Not started (we use NAIP) | Lane markings, turn-bay lengths, signal heads | No license stated |
| Context | COMPASS open data: demographics by traffic zone, land use, building permits, crashes, counts | Not started | Growth and demand context | Disclaimer only |
| Context | City of Boise open data (64 datasets) | Not reviewed | Unknown | Open portal |
| Context | Ada County Assessor: parcels, address points | Not started | Land use near corridors | Don't redistribute |
| Context | Federal: FARS fatal crashes, census commuting (ACS), TTI Urban Mobility | Not started | Benchmarks | Public domain |
| Context | Mapillary street-level photos | Coverage unchecked | Lane and sign checks | Free token; CC BY-SA |
| Oregon | ODOT TripCheck cameras and data | New, needs vetting | The Ontario end of the I-84 corridor | Registration |
| Cameras | ITD's own camera views on 511 | Left out: PNGs of 0.4–2.5 MB, mostly ACHD cameras republished. Two of them (I-184 Exit 0, I-184 & Chinden) are ACHD cameras missing from 511's ACHD list | Two more angles | 511 route |
| Cameras | The 18 ACHD cameras not on 511 (e.g. Chinden & SH-16 southbound ramp, 619) | Needs ACHD's OK | Missing angles | Asked in the draft ACHD note |
| Our own | Volunteer GPS drive runs | Tool ready (`tools/gps_runs.py`), no runs yet | Travel time and stops per signal | Consent rules (ch. 7) |
| Our own | Sidewalk signal observations | Not started | Cycle lengths and splits | Fully ours |

## Needs the owner's network (the local helper could fetch these)

- ACHD's main website (agendas, minutes, budget documents): blocks
  datacenter traffic.
- COMPASS data server (`swidrdc.org`): count map data, congestion measures.
- ITD's count database (`itd.ms2soft.com`): detailed count records.
- Overpass (OSM queries) and the Internet Archive.

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

1. **Signals and intersections** (ACHD signal points plus OpenStreetMap):
   the backbone.
2. **Crashes** (ITD).
3. **Work zones and incidents** (ITD WZDx: recording since Oct 6; ACHD live layers).
4. **Traffic volumes** (ITD AADT, counters, hourly reports).
5. **The 511 API**: recording since Oct 6.
