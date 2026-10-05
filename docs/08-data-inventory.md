# 8. Data inventory: what exists, what we can reach, what we may use

Every data source found so far (as of Oct 5, 2026), sorted into four
buckets:

- **A.** Reachable *and* allowed for automated use.
- **B.** Reachable, but terms or crawler rules forbid automated use or
  storage.
- **C.** Blocked from our cloud sandbox, but fine for a person in a
  browser.
- **D.** Not public: needs permission, a partnership, a license, or a
  records request.

*Not legal advice. "Allowed" means we found no terms or `robots.txt` rule
against the use described. Re-check before publishing anything derived from
a source.*

---

## 8.1 What "map servers" are

Most public agency data here sits on **Esri ArcGIS Server** or **ArcGIS
Online** sites. These are the back-end data services behind the agencies'
web maps. Each service has "layers" (cameras, count segments, AADT, crashes)
that can be queried by URL and return JSON or GeoJSON. They're built for
programmatic use, and none of them publishes a `robots.txt` restriction.

| Server | Who runs it | What's on it (public parts) |
|---|---|---|
| `gis.achdidaho.org/server/rest/services` | ACHD | Open-data hub layers: camera inventory, traffic-count *segments* (no values), Five-Year Plan projects, master street map, sidewalks, pavement, roadwork, message boards, incidents. Aerial imagery under `/imagery`. |
| `maps.achdidaho.org/server/rest/services` | ACHD | Mostly internal: the `GisData_Traffic`, `GisData_Signal`, `Safety` and similar folders need a login. Public: a roadwork layer and a few planning layers. A switched-off `ACHD_Traffic_Counts` service. |
| `services2.arcgis.com/9rTo9NcUHIKASKwi` | ACHD's ArcGIS Online account | Hosted copies, e.g. 2022 signal-asset points (traffic, pedestrian, school, fire signals), bike map, a 2021 pedestrian/bike crash summary |
| `gisp.itd.idaho.gov` and `gis.itd.idaho.gov` | ITD | AADT by segment (1999–2025), monthly volumes at automatic counter stations, crash points (2005–2023), ITS device locations |
| `swidrdc.org/arcgis` | COMPASS | Traffic counts (portable and permanent counters, multi-agency), congestion measures, demographics |
| `arcgis.com` | Esri catalog | Searchable index of all of these agencies' public items |

## 8.2 Bucket A: reachable and allowed

**Agency GIS and counts**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| ITD AADT | Annual average daily traffic by segment, 1999–2025, with truck counts and monthly factors | `gisp.itd.idaho.gov/.../Traffic/MapServer/1` | In `tools/collect_static.py` |
| ITD counter stations, monthly | Monthly average daily traffic at 45 Ada/Canyon counters, 2021 to about two months ago | `.../Traffic/MapServer/0` | In `collect_static.py` |
| **ITD hourly counter reports** (new) | **Hourly volumes for every day of the month** at each permanent counter, as PDFs | `apps.itd.idaho.gov/Apps/roadwaydata/<station>/<year>/...MonthlyHourlyTrafficVolumeReport.pdf` | Shows peak spreading and growth by hour. Text is extractable from the PDFs. |
| ITD crash points | 461,521 crashes, 2005–2023, with an intersection flag | `gis.itd.idaho.gov/.../CrashLayers/MapServer` | Not yet scripted |
| ACHD camera inventory | 228 cameras with locations and image URLs | `gis.achdidaho.org/.../Traffic_Cameras/MapServer/26` | In `collect_static.py`. The *images* are bucket B. |
| **ACHD live roadwork, incident and message-sign layers** (new) | Current roadwork plans (4 now), incidents (0 now), and message-board text (5 signs) | Same service, layers 22, 21 and 28 | Useful for explaining congestion on particular days |
| ACHD open-data layers | Five-Year Plan projects, master street map, count segments (IDs only), sidewalks, pavement | `gis.achdidaho.org/.../ArcGIS_Hub/...` | |
| **ACHD aerial imagery** (new) | **3-inch (0.25 ft) aerial photos of Ada County, 2024 and 2025** | `gis.achdidaho.org/imagery/rest/services/Imagery/Ada_County_Imagery_2025/ImageServer` | Lane counts, turn-bay lengths, signal-head layouts |
| ACHD signal-asset points (2022) | 2,469 traffic-signal points (probably poles or heads), 182 pedestrian signals, 33 school flashers, 68 fire signals | `services2.arcgis.com/9rTo9NcUHIKASKwi/...` | Stale (2022), but useful locations |

**Transit, work zones and 511**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| **Valley Regional Transit GTFS** (new) | Static schedules, stops and route shapes, plus **GTFS-realtime vehicle positions, trip updates and alerts** | Static: `valleyregionaltransit.org/GTFS/vrt_transit1.zip`. Real-time: `s3.amazonaws.com/etatransit.gtfs/valleyregionaltransit.etaspot.net/position_updates.pb` (also `trip_updates.pb`, `alerts.pb`) | VRT: "We provide these files for public use." **Buses act as GPS probes**: their logged positions give real arterial travel times and signal delay on State St, Fairview and other bus routes. The feed was live but empty on a Sunday night. **Measured Oct 5, 2026 (weekday, 2–3:45 PM, 4,637 fixes from 34 buses):** each bus reports every 30 s (p10–p90: 26–35 s; 91% of gaps ≤35 s, 0.5% over a minute), about 4 s before the feed publishes it; a moving bus covers about 200 m between fixes (p90 440 m); 22% of fixes are stationary (stops, signals). No speed field, so speeds come from consecutive fixes. Licensed CC BY 3.0. |
| **ITD work zones (WZDx)** (new) | 649 statewide work zones, **about 220 in the valley**, in a standard format | `https://511.idaho.gov/api/wzdx` | **No key needed** |
| 511 Idaho official API | Events, cameras, message signs, weather stations, road conditions, restrictions, advisories | `https://511.idaho.gov/developers/doc` (see §8.6) | Free key; **10 calls per 60 s** (confirmed in the docs). Each call returns a whole resource. |
| **511 Idaho camera images** (ACHD's cameras republished by ITD, plus ITD's own) | About 210 of ACHD's 228 cameras, plus ITD cameras; still images refreshed about once a minute | `https://511.idaho.gov/map/Cctv/<imageId>` (IDs from the official API) | 511 serves its own ITD-stamped copies from its own servers, lists ACHD as a provider, and its robots.txt allows this path. Owner decision Oct 5: legitimate. See [ch. 11](11-camera-validation-layer.md). |

**Map, weather, crashes and demographics**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| OpenStreetMap | Signal locations (often 2–6 nodes per intersection), road network, lanes | Overpass API or the OSM API | ODbL: attribute it; share-alike for published derived databases |
| **Boise airport weather** (new) | Hourly visibility and weather codes, back many years | Iowa Environmental Mesonet ASOS download (station BOI) | Test the **fog → detector fallback → long greens** link (chapter 2). IEM's `robots.txt` asks for a 120-second crawl delay, so make occasional bulk requests only. |
| **ACHD road centerlines with posted speeds** (new, Oct 5, 2026) | Every road segment in Ada County (38,727) with **posted speed** (`PostSpeed`), functional class, one-way flag, street name and address ranges | ACHD's open GIS: `gis.achdidaho.org/.../Maintenance/Road_Centerline/MapServer/7` (no robots.txt; automated access allowed) | All segments carry a speed: arterials look right (Eagle Rd 45–55 mph, Chinden 35–55, Fairview 35–40, State 35–55); 30,565 local streets are 20 mph, likely a residential default ⚠️ (not verified against signs); a few anomalies (one interstate segment at 20). **Ada County only**: Canyon County needs OSM `maxspeed`, ITD, or city/highway-district data. |
| **ACHD traffic counts layer** (new, Oct 5, 2026) | A `Traffic_Counts` feature layer on ACHD's open GIS (`ArcGIS_Hub` folder), alongside sidewalks, pavement, bike network and the master street map | `gis.achdidaho.org/.../ArcGIS_Hub/Traffic_Counts/FeatureServer` (open) | Not examined yet. If it carries the counts, it's an open, automatable route to the data we copied once from the robots-disallowed tables. |
| **FRA rail-crossing inventory** (new) | Every highway–rail crossing: 4,589 in Idaho, **433 in Ada and Canyon**. Includes a field for whether a highway traffic signal is nearby (no preemption field). | `data.transportation.gov` (Socrata API) | Shows which signals sit near tracks, where railroad preemption likely disrupts coordination (Nampa, Meridian, Kuna) |
| Federal datasets | HPMS road data, FARS fatal crashes, census commute data, LEHD job-to-home flows, TTI Urban Mobility data | FHWA, NHTSA, Census, TTI | Public domain or open |
| Mapillary | Crowd-sourced street-level photos | Free API token | CC BY-SA. Coverage in Boise unchecked. |
| City of Boise open data portal | City datasets (contents not yet reviewed) | `opendata.cityofboise.org` | Reachable |

**Our own data**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| **GPS drive logs** | Travel times, stops, and delay per signal | `tools/gps_runs.py` | Fully ours. Consent and privacy rules for volunteers (chapter 7). |
| **Sidewalk signal observation** | Cycle lengths, green splits, offsets | Stopwatch or video, no audio | Fully ours |

## 8.3 Bucket B: reachable, but terms or crawler rules forbid automated use

| Source | What's there | The rule | What to do instead |
|---|---|---|---|
| **ACHD counts table** (`more.achdidaho.org/.../trafficCounts.aspx`) | 24-hour and AM/PM peak counts by direction for every count location (3,827), dated 1994–2026 | That host's `robots.txt` disallows automated access. One-off research checks are fine (owner, Oct 5); collectors aren't. | **Full copy taken once, Oct 5** (owner-approved exception; [data/](data/README.md)). For history and updates, **ask ACHD for exports**. |
| **ACHD turn-movement counts** (`more.achdidaho.org/.../TurnMovements.aspx`, confirmed) | Busiest-hour turning counts per intersection and approach: AM, noon, PM and weekend, including U-turns | Same | Same: full copy taken once Oct 5; exports and updates via ACHD |
| **ACHD camera images** (`more.achdidaho.org/ATIS/CCTV/...jpg`) | About 220 live still images, refreshed every minute | Same `robots.txt` | Use 511 Idaho's republished copies (bucket A) instead. About 18 cameras not on 511 would need ACHD's permission. |
| 511 Idaho website data endpoints (`/list/getdata/`, `/map/map*/`) | Camera and event lists behind the 511 website | 511's `robots.txt` disallows them | Use the official API with a key |
| Google Maps Platform (Routes, Distance Matrix) | Live traffic-aware travel times | Terms forbid storing or bulk-downloading results | Agency-only Roads Management Insights; own GPS runs |
| Google Maps and Waze websites | Live traffic | Terms forbid scraping and mass download | Same |
| TomTom, HERE, Mapbox APIs | Segment speeds and travel times | Self-serve terms: evaluation or live use only; no stored datasets | Paid license, or a partner |

## 8.4 Bucket C: blocked from our cloud sandbox, fine for a person

| Source | Why we can't reach it | What it gives |
|---|---|---|
| `www.achdidaho.org` (main website) | Akamai blocks datacenter traffic (403) | Page text, links, commission agendas and minutes, budget documents |
| COMPASS data server (`swidrdc.org`) | Our sandbox's network proxy fails to reach it (502 / certificate error) | Multi-agency count map data, congestion measures |
| ITD count database (`itd.ms2soft.com`) | 403 from our sandbox | Detailed count records |
| Overpass (OSM queries), `web.archive.org` | Sandbox network | OSM queries, archived pages |

On your own machine these should all work. A Claude session running there
(Desktop app or `claude remote-control`) could also reach them.

## 8.5 Bucket D: not public (permission, partnership, license, or records request)

| Data | Holder | Route |
|---|---|---|
| **Signal timing sheets**, coordination plans, last-retimed dates | ACHD (and ITD for state routes) | Public records request |
| **High-resolution controller event logs** / ATSPM exports (Centracs) | ACHD | Records request or data-sharing agreement. The single most valuable dataset. |
| Detector configuration and trouble tickets | ACHD | Records request |
| **ACHD Connect service requests** (e.g., "signal malfunction" reports with time and place) | ACHD | Records request. No public feed found. |
| ACHD internal traffic and signal GIS layers | ACHD | Login-only (`GisData_Traffic`, `GisData_Signal`) |
| The switched-off `ACHD_Traffic_Counts` map service | ACHD | Ask ACHD to restart it |
| **Live camera video** | Nobody publishes it. All public cameras are still images. | Not available. Nampa police reportedly record their traffic cameras ⚠️, which may be requestable subject to retention. |
| NPMRDS probe speeds; ITD's purchased INRIX arterial data | ITD, COMPASS | Partner with COMPASS or ITD |
| Google Roads Management Insights, Green Light; Waze for Cities | Google, for agencies | ACHD or ITD would have to sign up |
| INRIX, StreetLight, Replica, TomTom MOVE, Iteris ClearGuide | Vendors | Paid license; INRIX × MetroLab challenge (university plus agency team) |
| Police crash reports (narratives) | Police and ITD | $7 per report from ITD, or records request |

## 8.6 Registering for the 511 Idaho API

Yes, there's an official API:

1. Create an account at **https://511.idaho.gov/my511/register**.
2. Log in, then request a **developer API key** on
   **https://511.idaho.gov/developers/doc**. The key appears on that page
   once issued.
3. Resources include **Cameras**, **Events** (incidents and construction),
   **Message Signs**, **Weather Stations**, **Road Conditions**,
   **Restrictions**, **Advisories** and others. Throttling is **10 calls per 60 seconds** per key (confirmed in the developer docs). Each call returns a whole resource, so a full polling plan uses about 2 calls a minute.
4. The **WZDx work-zone feed** at `https://511.idaho.gov/api/wzdx` needs no
   key.

The developer agreement shown at signup may restrict storage or
redistribution. Read it before building on the API.

## 8.7 Most useful next additions

1. **VRT bus positions:** log the real-time feed on weekdays to measure bus
   travel times through signalized corridors. Open data, and arterial coverage
   we can't get anywhere else for free.
2. **ITD hourly counter PDFs:** extract into tables for peak-hour growth on
   state routes.
3. **ACHD CSV export request:** counts plus turning movements, and in the
   same request, timing sheets and last-retimed dates.
4. **511 API key:** official camera and event data.
5. **Boise airport fog history:** pair it with complaint dates or corridor
   travel times to test the video-detection-in-fog explanation.

---

**Back to:** [README](../README.md)
