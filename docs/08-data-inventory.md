# 8. Data inventory: what exists, what we can reach, what we may use

Every data source found so far, sorted into four buckets. The inventory
dates from Oct 5, 2026; the later sections (§8.8–§8.10, Oct 6–7) carry
their own dates.

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
| `swidrdc.org/arcgis` | COMPASS | Traffic counts (portable and permanent counters, multi-agency), congestion measures, signals, crashes, demographics (reachable from the cloud again since Oct 6; [§8.9](#89-second-source-review-oct-6-2026)) |
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
| ACHD signal-asset points (2022) | 2,469 traffic-signal **poles** (12 at Eagle & Fairview; about 464 intersections when grouped within 45 m), 182 pedestrian signals (96 hybrid beacons, 76 RRFBs, 7 conventional pedestrian signals, 3 of them with a blank purpose, and 3 warning beacons), 33 school flashers, 68 fire signals | `services2.arcgis.com/9rTo9NcUHIKASKwi/...` | Frozen since Aug 2, 2022 ("Official Bike Map 2022"); only an ID and a purpose field. COMPASS's Regional_Signals is newer for pedestrian devices. See [§8.9](#89-second-source-review-oct-6-2026) |

**Transit, work zones and 511**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| **Valley Regional Transit GTFS** (new) | Static schedules, stops and route shapes, plus **GTFS-realtime vehicle positions, trip updates and alerts** | Static: `valleyregionaltransit.org/GTFS/vrt_transit1.zip`. Real-time: `s3.amazonaws.com/etatransit.gtfs/valleyregionaltransit.etaspot.net/position_updates.pb` (also `trip_updates.pb`, `alerts.pb`) | VRT: "We provide these files for public use." **Buses act as GPS probes**: their logged positions give real arterial travel times and signal delay on State St, Fairview and other bus routes. The feed was live but empty on a Sunday night. **Measured Oct 5, 2026 (weekday, 2–3:45 PM, 4,637 fixes from 34 buses):** each bus reports every 30 s (p10–p90: 26–35 s; 91% of gaps ≤35 s, 0.5% over a minute), about 4 s before the feed publishes it; a moving bus covers about 200 m between fixes (p90 440 m); 22% of fixes are stationary (stops, signals). No speed field, so speeds come from consecutive fixes. **Fleet coverage, checked Oct 5, 2026 (2–7 PM):** 42 buses reported at once at the peak (5:31 PM), exactly the 42 fixed-route buses NTD lists for peak service (Aug 2026), and 42 distinct buses over the afternoon, so the feed looks complete for the fleet. **Route labels are not complete:** 25% of fixes carry a trip ID that names no route, because the static schedule predates VRT's Oct 1 service changes. Matching those buses to route shapes puts them on routes 7, 8, 16, 28 and 40 (74–99% of their fixes within 40 m of one route), the routes that never appeared labeled. Route 30 was discontinued Oct 1 (VRT's service-changes page); R1 didn't appear (it's an event shuttle; below). Since Oct 5 the transit stream does this matching every 5 minutes (`ingest/transit_match.py`), which leaves under 1% of fixes unlabeled. Licensed CC BY 3.0. |
| **ITD work zones (WZDx)** (new) | 703 statewide work zones on Oct 6, 2026, 239 of them touching Ada or Canyon, with lane-by-lane status on most, in the USDOT standard format (v4.1) | `https://511.idaho.gov/api/wzdx` | **No key needed.** Published for public use: we may republish it, raw or aggregated, crediting ITD (owner, Oct 6). Checked against the spec in [§8.8](#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026). |
| 511 Idaho official API | Events, cameras, message signs, weather stations, road conditions, restrictions, advisories | `https://511.idaho.gov/developers/doc` (see §8.6) | Free key; **10 calls per 60 s** (confirmed in the docs). Each call returns a whole resource. |
| **511 Idaho camera images** (ACHD's cameras republished by ITD, plus ITD's own) | About 210 of ACHD's 228 cameras, plus ITD cameras; still images refreshed about once a minute | `https://511.idaho.gov/map/Cctv/<imageId>` (IDs from the official API) | 511 serves its own ITD-stamped copies from its own servers, lists ACHD as a provider, and its robots.txt allows this path. Owner decision Oct 5: legitimate. See [ch. 11](11-camera-validation-layer.md). |

**What transit VRT's live feed covers** (National Transit Database: VRT is
NTD ID 00011, data.transportation.gov resource `8bui-9xvu`, queried Oct 5,
2026):

| Service | Size (Aug 2026) | In the GTFS-realtime feed? |
|---|---|---|
| Fixed-route buses, including the Canyon County routes (40, 42, 45) | 42 buses at peak, about 83,000 trips a month: about 92% of VRT's trips | Yes, all 42 (checked above) |
| Demand response: ACCESS paratransit and on-demand service | About 37 vehicles at peak, about 7,000 trips a month | No, which is right for riders' privacy |
| R1 "Treeline" | An event shuttle; its dates line up with Treefort (March) | Listed in the feed; no buses seen so far |

- The 18–19 buses seen at 2 PM on a Monday fit the 42-bus peak: midday
  service is lighter, and the Oct 1 cuts (Nampa's funding, [ch. 3
  §3.5](03-traffic-context-and-data.md#35-major-projects-and-transit))
  reduced service.
- The valley has **no rail transit** (no light rail, commuter rail or
  streetcar), only freight rail.
- Vanpools, university shuttles and intercity buses weren't checked ⚠️ (general
  knowledge only). As far as we know, none of them publishes live
  positions.

**Map, weather, crashes and demographics**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| OpenStreetMap | Signal locations (often 2–6 nodes per intersection), road network, lanes | Overpass API or the OSM API | ODbL: attribute it; share-alike for published derived databases |
| **Boise airport weather** (new) | Hourly visibility and weather codes, back many years | Iowa Environmental Mesonet ASOS download (station BOI) | Test the **fog → detector fallback → long greens** link (chapter 2). IEM's `robots.txt` asks for a 120-second crawl delay, so make occasional bulk requests only. |
| **ACHD road centerlines with posted speeds** (new, Oct 5, 2026) | Every road segment in Ada County (38,727) with **posted speed** (`PostSpeed`), functional class, one-way flag, street name and address ranges | ACHD's open GIS: `gis.achdidaho.org/.../Maintenance/Road_Centerline/MapServer/7` (no robots.txt; automated access allowed) | All segments carry a speed: arterials look right (Eagle Rd 45–55 mph, Chinden 35–55, Fairview 35–40, State 35–55); 30,565 local streets are 20 mph, likely a residential default ⚠️ (not verified against signs); a few anomalies (one interstate segment at 20). **Ada County only**: Canyon County needs OSM `maxspeed`, ITD, or city/highway-district data. |
| **ACHD traffic counts layer** (new, Oct 5, 2026) | A `Traffic_Counts` feature layer on ACHD's open GIS (`ArcGIS_Hub` folder), alongside sidewalks, pavement, bike network and the master street map | `gis.achdidaho.org/.../ArcGIS_Hub/Traffic_Counts/FeatureServer` (open) | **Examined Oct 5: locations only.** 3,880 count-location lines, each with a location ID (`PID`), created/edited dates and length, but no counts and no related tables. The counts themselves are only in ACHD's robots-disallowed tables, whose rows don't carry the ID, so joining would mean matching street names and descriptions. The official export we've asked ACHD for is still the clean route. |
| **Census commute flows (LEHD LODES8)** (new, Oct 6, 2026) | Jobs by the census block where the worker lives and where they work, all jobs, 2002–2023; Idaho and Oregon (for Ontario) | `lehd.ces.census.gov/data/lodes/LODES8/` (robots.txt allows all); `tools/lehd_flows.py` | Public domain. **2023:** 20,500 jobs in Ada or Canyon are held by residents of the 7 counties around them. Most tied to Ada and Canyon (share of residents' jobs): Owyhee 62% (Homedale 67%), Boise County 59%, Gem 58% (Emmett 60%), Elmore 44% (Mountain Home 46%, military not counted), Payette 35%, Washington 25% (Weiser), Malheur County OR 12% (Ontario 10%). Payette County and Ontario form their own job market across the river (2,771 Payette County residents work in Malheur County). Caveats: counts jobs, not trips; leaves out the military and self-employed; places a job at its employer's address. |
| **FRA rail-crossing inventory** (new) | Every highway–rail crossing: 4,589 in Idaho, **433 in Ada and Canyon**. Includes signal-nearby, interconnection and preemption fields, but they're filled only for Boise Valley Railroad crossings ([§8.9](#89-second-source-review-oct-6-2026)). | `data.transportation.gov` (Socrata API) | Shows which signals sit near tracks, where railroad preemption likely disrupts coordination (Nampa, Meridian, Kuna) |
| Federal datasets | HPMS road data, FARS fatal crashes, census commute data, LEHD job-to-home flows, TTI Urban Mobility data | FHWA, NHTSA, Census, TTI | Public domain or open |
| Mapillary | Crowd-sourced street-level photos | Free API token | CC BY-SA. Coverage in Boise unchecked. |
| City of Boise open data portal | City datasets (reviewed Oct 6; [§8.9](#89-second-source-review-oct-6-2026)) | `opendata.cityofboise.org` | Reachable |

**Aircraft** (new, Oct 7, 2026; details in [§8.10](#810-aircraft-sources-oct-7-2026))

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| **adsb.lol** | Live aircraft positions, altitude, speed, heading, callsign and type, from volunteer receivers | `api.adsb.lol/v2/point/{lat}/{lon}/{nm}` (no key yet; no robots rules) | ODbL ("© adsb.lol contributors"). Chosen Oct 7 ([DECISIONS](DECISIONS.md)): one request every 10 s, after a courtesy note to adsb.lol |
| **FAA aircraft registry** | Type, make, model, year built and registrant type for every US-registered aircraft, joined on the ADS-B hex code | FAA's releasable aircraft download (daily, about 60 MB) | Public domain. Owners' names and addresses are never stored |

**Our own data**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| **GPS drive logs** | Travel times, stops, and delay per signal | `tools/gps_runs.py` | Fully ours. Consent and privacy rules for volunteers (chapter 7). |
| **Sidewalk signal observation** | Cycle lengths, green splits, offsets | Stopwatch or video, no audio | Fully ours |

## 8.3 Bucket B: reachable, but terms or crawler rules forbid automated use

| Source | What's there | The rule | What to do instead |
|---|---|---|---|
| **ACHD counts table** (`more.achdidaho.org/.../trafficCounts.aspx`) | 24-hour and AM/PM peak counts by direction for every count location (3,827), dated 1994–2026 | That host's `robots.txt` disallows automated access. One-off research checks are fine (owner, Oct 5); collectors aren't. | **Full copy taken once, Oct 5** (owner-approved exception; [data/](data/README.md)). For history and updates, **ask ACHD for exports**. |
| **ACHD turn-movement counts** (`more.achdidaho.org/.../TurnMovements.aspx`, confirmed) | Busiest-hour turning counts per intersection and approach: the single busiest hour inside each two-hour peak (AM 7–9, noon 11–1, PM 4–6) and a weekend window whose hours the page doesn't state, including U-turns | Same | Same: full copy taken once Oct 5; exports and updates via ACHD |
| **ACHD camera images** (`more.achdidaho.org/ATIS/CCTV/...jpg`) | About 220 live still images, refreshed every minute | Same `robots.txt` | Use 511 Idaho's republished copies (bucket A) instead. About 18 cameras not on 511 would need ACHD's permission. |
| 511 Idaho website data endpoints (`/list/getdata/`, `/map/map*/`) | Camera and event lists behind the 511 website | 511's `robots.txt` disallows them | Use the official API with a key |
| Google Maps Platform (Routes, Distance Matrix) | Live traffic-aware travel times | Terms forbid storing or bulk-downloading results | Agency-only Roads Management Insights; own GPS runs |
| Google Maps and Waze websites | Live traffic | Terms forbid scraping and mass download | Same |
| TomTom, HERE, Mapbox APIs | Segment speeds and travel times | Self-serve terms: evaluation or live use only; no stored datasets | Paid license, or a partner |
| Other aircraft feeds: adsb.fi, OpenSky, airplanes.live, ADS-B Exchange | Live aircraft positions (OpenSky also a history database) | adsb.fi: personal, non-commercial use only. OpenSky: any operational use needs a written agreement ⚠️. airplanes.live: now asks callers to contact it first. ADS-B Exchange: paid, `robots.txt` disallows `/api/`, no sharing ⚠️ ([§8.10](#810-aircraft-sources-oct-7-2026)) | adsb.lol (bucket A); later the owner's own receiver |

### ACHD's counts and turn-movement tables in detail (Oct 5, 2026)

**The pages.** ACHD's [Traffic Counts](https://www.achdidaho.org/my-commute/traffic/traffic-counts)
and [Traffic Turn Movements](https://www.achdidaho.org/my-commute/traffic-turn-movements)
pages each embed a table from
`more.achdidaho.org/Departments/Engineering/Traffic/` (`trafficCounts.aspx`
and `TurnMovements.aspx`). Both are ASP.NET pages that page by postback,
with a street or location filter.

- ACHD says Traffic Engineering compiles the counts from data ACHD collects
  and updates them regularly. The turn-movement page notes that its table
  is designed for a tablet or larger screen.
- Pages hold 10 count locations or 12 turn-movement rows. No page-size
  setting shows in the HTML, and the server ignores one in the URL (the
  owner had suggested asking for 100 rows), so every page costs one
  request.

**Corridor checks first.** Before the full copy, one-off pulls of two
corridors (Eagle Rd and Chinden Blvd, 34 requests, 2 s apart):

| Corridor | Count locations | Busiest | Turn-movement dates |
|---|---|---|---|
| Eagle Rd | 28, most counted 2023–2026 | North of I-84, 66,488 a day (Oct 2024); then north of Franklin, 64,272 (Nov 2025) | Mostly 2020–2023 |
| Chinden Blvd | 25, almost all 2024–2026 | East of Glenwood, 41,805 a day (May 2026) | Mostly 2022, a few from 2001–2011 |

**The full copy.** The owner approved one pull of both tables (a one-time
exception; [DECISIONS](DECISIONS.md), Oct 5).

- **Sizing** took 4 requests, jumping to each table's last page. Counts: 390
  pages of 10 locations (about 3,900 locations, about 7,800 rows by
  direction). Turn movements: 192 pages of 12 rows (about 2,300 peak-hour
  rows, estimated at about 800 intersections). 582 requests in all, about
  30 MB. The copy turned out to hold 3,827 locations (7,696 rows) and 916
  intersections ([data/](data/README.md)).
- **The alternative we didn't take.** The pilot recommended sending the
  note to ACHD first, waiting about two weeks, and pulling only if there was
  no reply, because a full pull is what that `robots.txt` discourages and an
  official export might include count history. The owner chose to pull
  right away ("in line with my comfort").
- **Safeguards:** an `--all` mode still behind `--one-off`, a cap of 600
  pages a table, retries for brief network errors, each page saved as it
  arrived, and a stop if the pager failed to advance.
- **The run:** 4–5 s a page (the 2 s pause plus ACHD's response time), 12:54
  to 1:21 AM MDT, with no retries or paging problems. Every page was
  distinct, and the earlier Eagle and Chinden rows came back unchanged.
- **Afterwards** the draft note to ACHD was reworded to say plainly that we
  made one slow, identified copy, and to ask for official exports with
  history. Its old line, that we'd rather ask than scrape, was no longer
  true.

**What the copy shows** (totals and recency in [ch. 7
§7.3E](07-diy-data-collection.md#e-achds-published-traffic-counts-table)):

- Count dates run back to 1994, and turn-movement dates 1997–2026. Many
  counts are 7-day or permanent counts, not single-day ones.
- The busiest single hours: Eagle & Fairview, PM, 7,060 vehicles; the I-84
  ramps at Meridian Rd, 6,911; Meridian & Overland, 6,365; Eagle & Franklin,
  PM, 6,056.
- Eagle & Fairview's PM peak hour (June 2023) includes 475 left turns from
  one approach and 1,755 through vehicles on another.
- Turning volumes per approach are the main input to a retiming: they let
  us check whether left-turn phases and green splits match demand.

**Quirks in ACHD's own data,** kept as published: 19 locations are listed
twice with identical numbers, one row is an empty placeholder, and peak
labels come in mixed case (`NOON` and `Noon`).

## 8.4 Bucket C: blocked from our cloud sandbox, fine for a person

| Source | Why we can't reach it | What it gives |
|---|---|---|
| `www.achdidaho.org` (main website) | Akamai blocks datacenter traffic (403) | Page text, links, commission agendas and minutes, budget documents |
| ITD count database (`itd.ms2soft.com`) | 403 from our sandbox | Detailed count records |
| Overpass (OSM queries), `download.geofabrik.de`, `web.archive.org` | Sandbox network | OSM queries and extracts (processed on the server instead), archived pages |

COMPASS's data server (`swidrdc.org`) was listed here until Oct 6, 2026; it answers from the cloud again.

**ACHD's main site blocks by origin, and we don't get around it** (Oct 5,
2026). Akamai, in front of `www.achdidaho.org`, blocks by where a request
comes from (data-center addresses), not how it's made: a real headless
Chromium in the cloud container, with the proxy's certificate trusted,
still got Akamai's "Access Denied". The same pages load normally from a home
connection.

- The site runs on CivicPlus (Vision Internet). In the owner's browser
  capture of the counts page, the page itself made only a font-size script
  call and Google Analytics requests. The data comes from the embedded
  `trafficCounts.aspx` frame on `more.achdidaho.org`, which answers from the
  cloud but whose `robots.txt` disallows automated access (bucket B).
- **Policy:** we don't evade origin blocks. A person, or the local session,
  visits instead.

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
| FAA SWIM flight data (SFDPS en route, STDDS/TAIS terminal) | FAA | Free, but needs a signed Service Access Agreement ⚠️ ([§8.10](#810-aircraft-sources-oct-7-2026)) |

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
redistribution. Read it before building on the API. **Oct 6, 2026:** the
owner has the key, and ITD is fine with our use. The full API reference
(11 endpoints) is kept with the private files.

**What each feed carries** (from the developer docs: the index and 11
endpoint pages, read Oct 6). Every feed returns the current state of the
whole state in one call, so history exists only if we poll and keep it.

| Feed | Fields |
|---|---|
| Events | The affected stretch as a line, lanes affected, a full-closure flag, severity, cause, detour route, recurring schedules |
| Advisories | The regions they apply to, a high-importance flag, start and end times |
| Message signs | Current text, location, road, direction |
| Weather stations | 29 readings per station: pavement, air and below-surface temperature; surface status, friction and ice percentage; wind and gusts; humidity; visibility; precipitation over the last 1–24 h. Each station names its camera |
| Road conditions (winter roads) | Overall status, weather and special conditions per stretch, drawn as a line |
| Cameras | Each camera's views, with the same image IDs we capture |
| Mountain passes | Elevation and maximum grade, with the pass's camera and weather station |
| Restrictions | Same shape as events |
| Rest areas, truck ramps, weigh stations | Fixed sites |

`obs.weather_reading` (migration 0010) keeps the below-surface
temperature, ice percentage and gusts too, though [ch. 12's
table](12-database-schema.md#126-obs-time-series-timescaledb) doesn't list
them.

**First call to each endpoint (Oct 6, 2026, 15:57 UTC):**

| Endpoint | Returned | Notes |
|---|---|---|
| Events | 179 statewide, 42 in the valley: 154 roadwork, 24 closures, 1 notice | All from ERS, 511's event system; `SourceId` is the number WZDx uses for the same event (120 of them link to WZDx work zones) |
| Message signs | 67 statewide, 21 in the valley; 15 showing something (variable speed limits, an exit closure, wildlife warnings) | Blank signs say `NO_MESSAGE` |
| Weather stations | 127 road-weather stations, 9 in the valley | Air, pavement and dew-point temperatures, humidity, wind, precipitation, visibility, surface status and friction; all stations updated within the same minute, about every 15 minutes. Each names its camera, and all 127 match the camera list |
| Winter road conditions | 237 stretches | All "No Report" in October |
| Cameras | 664 cameras, 937 views (730 enabled) | ACHD 215, ITD 265, road-weather 130, Oregon 8 and a few from neighbors; all 34 key cameras and all 389 road-weather capture views are in it |
| Advisories | None | |
| Truck restrictions | 75 | 67 are also in Events, with restriction values (length, width, height, weight) |
| Mountain passes, rest areas, runaway-truck ramps, weigh stations | 32, 29, 7, 22 | Change rarely |

Responses are gzip-compressed and rebuilt on every request (a new ETag
each time), like WZDx. **Collected since Oct 6** by the `idaho511` service
([ingest/](../ingest/README.md)).

**The website's camera list, before the API.** The one-off copy of 511's
website camera list (Oct 5; refreshed once on Oct 6, unchanged) held 457
camera sites and 730 views statewide. Sites by provider: ACHD 215, RWIS
(road weather) 130, ITDNET 64, Idaho511 12, ODOT 8, WYDOT 7, UDOT 6, MTD 4,
WSDOT 2, DriveBC 2, NDot 2, Private 1, plus a `USER` group whose count
was cut off. Its 730 views match the API's 730 enabled views. The copy is
511's data and stays in the private files; only these counts are ours to
publish.

## 8.7 Most useful next additions

1. **VRT bus positions:** log the real-time feed on weekdays to measure bus
   travel times through signalized corridors. Open data, and arterial coverage
   we can't get anywhere else for free.
2. **ITD hourly counter PDFs:** extract into tables for peak-hour growth on
   state routes.
3. **ACHD CSV export request:** counts plus turning movements, and in the
   same request, timing sheets and last-retimed dates.
4. **511 API** (key received Oct 6, 2026): official camera and event data.
5. **Boise airport fog history:** pair it with complaint dates or corridor
   travel times to test the video-detection-in-fog explanation.

## 8.8 ITD's work-zone feed, checked against the WZDx spec (Oct 6, 2026)

**First look (Oct 5, about 03:25 UTC).** The first fetch of
`https://511.idaho.gov/api/wzdx` (no key) returned HTTP 200: 1,726,083
bytes of uncompressed JSON, WZDx version 4.1, 649 work zones statewide. A
day later there were 703 (below). Fetched with gzip, the feed is about 15
times smaller (1.9 MB raw to 124 KB on Oct 6).

**The spec.** The Work Zone Data Exchange (WZDx) is USDOT's open format for
work zones, in the public domain (CC0) and kept at
[github.com/usdot-jpo-ode/wzdx](https://github.com/usdot-jpo-ode/wzdx).
Its last version is 4.2 (Feb 2023). It has since become a formal standard,
the Connected Work Zones (CWZ) Implementation Guide and Standard v01.00
(ITE, AASHTO and NEMA with SAE, finalized Dec 2024;
[ITE's validation report](https://www.ite.org/ITEORG/assets/File/CWZ_Validation_Report-final%20v01_00-260122.pdf)).
Illinois, Colorado and Massachusetts already publish CWZ feeds; Idaho
doesn't yet.

WZDx defines two feeds:

- a **work zone feed**: closures, lanes, detours;
- a **device feed**: live arrow boards, message signs, cameras, traffic
  sensors and temporary signals in work zones.

USDOT's feed registry (data.transportation.gov, dataset `69qe-yiui`, read
Oct 6) lists one Idaho feed: ITD's work zone feed, version 4.1, updated
every minute, no key, active since Sept 2025. There's no Idaho device feed.
Neighbors with feeds: Oregon DOT (v4.0, key needed, which would cover
Ontario), Utah DOT (v4.0) and WSDOT (v4.2).

The spec's rules that matter to us:

- An event is split into segments wherever a required value or the lanes
  change.
- A lane list must cover every lane, numbered from 1 at the left.
- Times are UTC.
- The license field is optional, but the spec says public feeds "must be
  licensed" CC0 and that the field will become required. Idaho's feed leaves
  it out; the owner treats the feed as open (Oct 6).

**Idaho's feed against it.** Snapshot of Oct 6, 15:39 UTC: 703 work zones
statewide, 239 with a point in the Ada and Canyon box. The publisher is
Arcadis, and the data source is "ERS", 511's event system.

| Check | Result |
|---|---|
| Schema v4.1 | Passes except 4 work zones whose reduced speed is the text `"NaN"` |
| Version | Says 4.1 but also uses two 4.2 fields (`work_zone_type`, `impacted_cds_curb_zones`); against 4.2 it fails 27 times (the 4 above plus 24 with `work_zone_type` set to `""`) |
| Times | 24 overnight closures (e.g. W Chinden Blvd, 10 PM–6 AM) end the day before they start: the end date is one day early |
| How sure | Every "verified" flag is false and every location method is "unknown": times and places are as planned, not confirmed in the field. 279 work zones are a single point, 424 are lines (median 11 points) |
| Workers present | On 535 work zones, always true, last confirmed 16 hours to 1.5 years earlier (median 60 days), even for closures days away: a planning field, not live |
| Traffic impact | All lanes open 278; one lane with alternating directions (flaggers) 173; some lanes closed 24; all lanes closed 26; unknown 202 |
| Lanes | Lane-by-lane status on 561 (1–5 lanes; general, shoulder, exit lane); 126 lanes closed and 228 alternating one-way |
| Limits | Width, weight, height and length limits on 263, with values |
| Speeds | Reduced speeds on 228, in km/h converted from round mph (72.42 = 45 mph, 40.234 = 25) |
| Other fields | Type of work on only 24. The description repeats the schedule, width and speed in words. Beginning cross street on all, mileposts on 571. No contact or update interval in the header |
| IDs | 38 ERS event numbers; 82 segments `N-k` of event `N` (in the non-standard `road_event_id`); 583 hash IDs, one per day of a recurring schedule, chained as first and next occurrence (all 934 links resolve). Each entry carries today's occurrence plus a link to the next, so "is this work zone active now?" is easy to answer. IDs didn't change across three fetches over 6 minutes; whether the daily hashes stay the same over days is still to check |
| HTTP | Rebuilt on every request (new ETag, header time = request time), so asking "changed since?" always returns the whole feed. 1.9 MB raw, 124 KB gzip, 111 KB Brotli. The three fetches were otherwise identical |

So the feed is good for **where and when work is planned** and for
**which lanes it closes**. We clean it on load: drop the `"NaN"` speeds,
move the early end dates forward a day, store speeds in mph, and mark
locations as approximate. Worker presence isn't shown as live.

**Collected since Oct 6, 2026** by the `wzdx` service (`itd_wzdx` in
[ingest/](../ingest/README.md)), every 5 minutes, owner's OK: changed
snapshots archived, every version of each work zone in `raw.record`,
cleaned rows in `evt.event` ([ch. 12 §12.7](12-database-schema.md#127-evt-lifecycles)).

- **First poll on the server** (16:05 UTC): 709 work zones stored, 239 in
  Ada and Canyon. At that moment 42 were scheduled to be active in the
  valley, and 31 were closing lanes statewide.
- **Fixes applied on load:** 24 overnight end dates moved forward, 4 `"NaN"`
  speeds dropped, 24 blank work-zone types dropped.
- A changed snapshot archives at about 105 KB. The second poll (16:10:48
  UTC) found no change, so the collector only marked all 709 as seen.

## 8.9 Second source review (Oct 6, 2026)

At the owner's request, four background agents reviewed the remaining
sources with paced, robots-checked metadata requests (no bulk downloads).
Their working notes, and any third-party copies, stay out of the
repository. The COMPASS and City of Boise catalog review alone made 397
metadata requests, 1.5–4 s apart, honoring the 60 s Crawl-delay where a
host sets one.

**Access checks** (robots.txt read Oct 6, 2026):

| Host | Rules |
|---|---|
| `gis.achdidaho.org` | `robots.txt` returns 404: no rules |
| ACHD's open-data hub | Allows `/api/`, with a 60 s Crawl-delay (kept) |
| `compassidaho.org` | Allows everything, with a 60 s Crawl-delay; its orthophoto page returned 403 from the site itself (not retried) |
| `swidrdc.org` (COMPASS) | No `robots.txt` |
| `services6.arcgis.com`, `services8.arcgis.com` (ArcGIS Online) | No robots rules |
| `data.transportation.gov` (FRA, NTD, WZDx registry) | Allows `/resource/` and `/api/views/`, Crawl-delay 1 |
| `apps.geo.fpac.usda.gov` (USDA's NAIP image service) | No robots rules, and not on our off-limits list, but a scripted bulk pull still needed the owner's OK (given Oct 6; [ch. 9 §9.5](09-base-map-data.md#95-imagery)) |

**COMPASS** (`share-open-data-compassidaho.hub.arcgis.com`, plus 42
services and 159 layers on `swidrdc.org`, plus layers on ArcGIS Online).
The hub's catalog (DCAT) has 64 entries, 35 of them hub datasets. The most
useful layers:

| Layer | What it gives | Where |
|---|---|---|
| Congestion performance measures | 47,293 rows, 2018–2025: travel-time index, reliability (LOTTR, TTTR), hours of delay, congested vs free-flow speed by road segment (the federal measures; probably from NPMRDS ⚠️). The layer reaches beyond Ada and Canyon | `swidrdc.org`, not on the hub |
| Commute travel times | 16 commutes, AM and PM, 2025 (e.g. Caldwell to Boise AM: 23 min free-flow, 31 average, 52 at the 95th percentile) | `swidrdc.org`, not on the hub |
| Signalized_Intersections | 585 signals, one point per intersection (Ada 465, Canyon 120), with operator, owner, coordination group, ACHD's Synchro ID, right-turn lanes, turn phasing and peak-hour turn volumes per approach. Built summer 2019 for the regional signal operations plan, last edited Aug 7, 2026. Details below | ArcGIS Online (`services6.arcgis.com/2S9FP4vfcUQQ8G1T/arcgis/rest/services/Signalized_Intersections/FeatureServer/0`) |
| Regional_Signals | 1,078 signal points across operators (ACHD 833, Nampa 166, Caldwell 28, ITD 23, highway districts 18) with coordination groups; no edit date ⚠️. **Reconciled with the 585 (Oct 6):** it adds essentially no signals (below) | `swidrdc.org`, not on the hub |
| RegionalCenterline | 62,213 segments in Ada and Canyon with `pm_id` (the key for COMPASS's counts, crashes and model), posted speed and lanes; monthly | hub |
| Crash data | 174,038 crashes 2008–2025 (two more years than ITD's layer), linked to segments and intersections; the high-injury network (1,924 junctions, 14,487 segments); a person-level table (aggregates only) | hub |
| Count tables | The latest count at 4,387 locations from every agency, Canyon County's included (Portable_Latest); 115 permanent counters (ATR_Latest) | hub |
| Growth | Traffic-zone demographics (2,498 zones, estimates to 2026, forecasts of population, households and jobs to 2055), building permits since 2000 (174,244, through 2025; the layer's statistics queries see only 97,684 and stop at 2023, so count records directly), 1,061 preliminary plats with units still to build | hub |

Other COMPASS layers found in the same review:

| Layer | What it gives |
|---|---|
| Intersection Nodes with Type (hub #17) | 570 signals, 87 pedestrian signals and 15 roundabouts, with `int_id`, the key that links crashes |
| Travel-model links (`CIM/CompleteNetwork/1`) | 9,130 links with capacity, lanes, speed, demand over capacity, and peak-hour counts with their dates; `pm_id` |
| Detectors; Bluetooth readers | 184; 16 |
| Roundabouts; unsignalized intersections | 144; 47 |
| I-84 detours | 95 closures, 93 routes |
| Existing sidewalks; bike facilities | 57,166; 2,445 |
| TIP intersections | 312 (for before/after studies) |
| Schools | 157 points, with enrollment |

Fields of layers already listed:

- **HIN segments:** volume, average and 85th-percentile speed against the
  limit, lane width, median, shoulders, bike lane and sidewalk, crashes.
- **Crash points:** severity, light, weather, surface, a work-zone flag,
  the segment key and `int_id`.
- **Portable_Latest** (4,387) by agency: ACHD 3,093, Nampa Highway District
  364, Canyon Highway District 261, City of Nampa 145, Golden Gate Highway
  District 101, ITD 93.

Caveats: the CIM 2040 entries point to a stopped service; one preliminary
plat is dated in the future; some Portable_Latest `pm_id` values are
`#NYA`.

Terms: the hub's disclaimer appears on only 9 of its 64 entries; the
others state nothing. Credit "COMPASS and COMPASS member agencies". Layers
only on `swidrdc.org` have no catalog entry or terms: used internally until
COMPASS answers ([DECISIONS](DECISIONS.md)). Agency fiber routes (also
there) are never republished.

**COMPASS Signalized_Intersections in detail** (no license: "meant only
for reference").

- **Operator:** Ada 465 (ACHD 464, ITD 1); Canyon 120 (Nampa 79, Caldwell
  22, ITD 19). **Owner:** ACHD 354, ITD 167, Nampa 42, Caldwell 22.
- **Type:** full 578, half 4, U-turn 3. 365 are coordinated.
- **Fields:** `location`, `jurisdicti`, `owner`, `city`, `county`,
  `CrossingTy`, `coordinated`, `coor_group`; `ACHD_Synchro_ID` (on all 464
  ACHD signals); per-approach volumes `SBL_Vol`…`EBR_Vol` and a total (`TEV`),
  model or Synchro volumes of unknown year ⚠️; `*_RT_Lanes`,
  `*_LT_Phasing`, `*_RT_Phasing`, `Skew`, `five_legged`; `LPI_Status`
  (leading pedestrian interval) and `APS` (accessible pedestrian signals);
  pedestrian and bike crashes within 250 ft; an ADT estimate.
- Synchro IDs 215, 256 and 428 each appear on two points (two of the pairs
  are kilometres apart), so those are keyed by Synchro ID plus location.
- `LPI_Status` and `APS` are worth a layer of their own, or a check of
  where ACHD has added leading pedestrian intervals ([ch. 2
  §2.4](02-treasure-valley-signal-system.md#24-how-timing-works-here-today)).

**Regional_Signals against the 585** (Oct 6). 1,076 devices have geometry
(2 have none). Only 586 are traffic signals, and 584 of those lie within
10 m of a Signalized_Intersections point:

| Operator | Traffic signals within 10 m of a COMPASS intersection |
|---|---|
| ACHD | 459 of 460 |
| Nampa | 80 of 80 |
| Caldwell | 22 of 22 |
| ITD | 20 of 20 |
| Blank | 3 of 4 |

The other 490 are school flashers, RRFBs, hybrid beacons (HAWKs), other
beacons and fire signals. For pedestrian devices it's newer than ACHD's
2022 layer: it holds all 96 of ACHD's hybrid beacons and all 76 RRFBs, plus
more.

**City of Boise** (`opendata.cityofboise.org`; its catalog has 88 entries,
65 of them datasets, plus 291 public services in the City's ArcGIS Online
account). Mostly parks and administrative layers. Useful:

- the development pipeline: Development Tracker (1,035, daily), Zoning
  Activities (2,129, daily), New Residential Permits (10,996, 1998–2026)
  and high-impact building permits (`PDS_BuildingPermits_HighImpact`, 159);
- police calls for service since 2017 (1.37 million calls, including 69,104
  crashes and 324,981 traffic calls; by census tract only, so aggregates
  only);
- street lights (14,049) and parking meters (693).

Terms: 77 of the 88 entries carry the City's disclaimer, 4 a shorter one,
and 6 nothing. The City's "Ada County Addresses" layer carries the
Assessor's "do not re-distribute" notice (Idaho Code 74-120).
`services8.arcgis.com` hosts VRT's plan layers (no robots rules).

**Ada County parcels.** The Assessor's downloads (updated twice a month)
say "Do not re-distribute this record"; County IT's open-data hub labels
the same parcels, address points and centerlines "CC0 (Public Domain)".
Year built, dwelling units and commercial floor area are only in the
Assessor's parcel-characteristics download. Canyon County publishes
110,890 parcels (daily) without those fields; the statewide layer is stale.

**FRA rail crossings.** Public domain, refreshed daily.

- **Datasets** on data.transportation.gov: `m2f8-22s6` "Crossing Inventory
  Data (Form 71) - Current", `vhwz-raag` (history; 6,645 versions back to
  1970, not loaded) and `xp92-5xme` (raw codes). The query:
  `https://data.transportation.gov/resource/m2f8-22s6.json?$where=statecode='16' AND countycode in('16001','16027')&$limit=1000&$order=crossingid`.
  265 columns, about 1.7 MB a call.
- **Counts:** 433 crossings in Ada (158) and Canyon (275). 197 are closed
  (kept and flagged). Of the 236 open: 152 public highway crossings, 83
  private, 1 private path. 131 open public crossings at grade (Boise Valley
  Railroad 78, Union Pacific 53) and 21 grade separations. 367 have a point
  in the box; 62 have no point.
- **Warning devices** on the 131 open public at-grade crossings: crossbucks
  43, gates 38, stop signs 28, flashing lights 20, highway signals with
  bells 2. The field arrives as text labels (e.g. "All other Gates"), not
  digits, so the code maps both.
- **Trains:** Union Pacific's mainline carries 8 day and 5 night through
  trains (about 13 a day) at up to 70 mph; Boise Valley Railroad about 2 a
  day at 25 mph or less. FRA's road AADT is stale (years 1970–2024; only 37
  of the 131 from 2023–24).
- **Preemption fields** are filled only for Boise Valley Railroad; 79 of the
  131 are blank, Union Pacific's among them, so we work out "signal near a
  crossing" ourselves. Cole Rd: interconnected, advance preemption.
  Milwaukee St: interconnected, simultaneous preemption. Allumbaugh: signal
  nearby. Malad: signal nearby, not interconnected.
- **OpenStreetMap** has 342 `railway=level_crossing` nodes, none with
  `ref:usdot`, so they match FRA by distance.

**Crossings near signals** (the build, Oct 6). 26 crossings lie within
200 m of an active signal, 14 of them open at grade, all Boise Valley
Railroad: Cole Rd 37 m (interconnected, advance preemption), Allumbaugh
57 m, Milwaukee 77 m (simultaneous preemption), then Benjamin, Robert,
Curtis, Maple Grove, Federal Way, Main St, Phillippi, Kootenai, Idaho Center
Blvd, Overland and Orchard at 114–200 m. No open Union Pacific crossing is
within 200 m: the nearest is 238 m (Karcher Rd, Nampa), and Caldwell's are
279–307 m from the Blaine St signals. So crossings link to the nearest
signal within 300 m for every railroad, with the distance stored, and
analysis can filter on 61 m (200 ft, the distance at which a crossing must
be interconnected with the signal) ([DECISIONS](DECISIONS.md), Oct 6).

**Signals.** ACHD's 2022 points are poles, not intersections (above).
COMPASS's 585-point layer gives one point per signalized intersection, and
OpenStreetMap has 752 `traffic_signals` nodes in the box (May 2026 data ⚠️).
ACHD also publishes 190 roundabouts and 574 Five-Year Plan intersection
projects. Nothing newer on ACHD's public GIS; ten of its folders need a
login.

**Lanes.** Summarized in [ch. 9 §9.3](09-base-map-data.md#93-streets-network-and-lanes),
with the rule for which source wins where.

**Aerial imagery.** ACHD's 2024 and 2025 3-inch imagery is COMPASS's
(flown by GeoTerra); [ch. 9 §9.5](09-base-map-data.md#95-imagery).

## 8.10 Aircraft sources (Oct 7, 2026)

For the `aircraft` plugin ([ch. 16 §16.2](16-ideas-and-personas.md#aviation-watcher-aircraft-the-first-new-plugin)).
Checked Oct 7 UTC with about 59 requests, robots-checked through
`ingest/http.py` and at least 3 s apart. ⚠️ marks what rests on search
snippets. The decision (adsb.lol, every 10 s, after a courtesy note) is in
[DECISIONS](DECISIONS.md), Oct 7.

**The area.** The box is W −117.30, S 42.90, E −115.60, N 44.30 (2.38
square degrees). One 60 nm point query at 43.6, −116.45 covers every corner
(the farthest is about 56 nm).

**The live feeds compared**

| Source | Terms | Access and limits |
|---|---|---|
| **adsb.lol** (chosen) | Data ODbL 1.0; code BSD-3-Clause. The API page says it's available to everyone | `api.adsb.lol` `robots.txt` 404 (no rules). No key; rate limits are dynamic, and a 4xx means the request is wrong. The README says a future API key will come from feeding data to adsb.lol. A drop-in for ADS-B Exchange's RapidAPI. `/v2/point/{lat}/{lon}/{nm}`, `/v2/lat/../lon/../dist/..` |
| adsb.fi | Personal, non-commercial use only; cite adsb.fi with a link. Storage and redistribution not addressed | `opendata.adsb.fi` `robots.txt` 400 (no rules). 1 request a second; bad requests can bring a temporary IP ban. `/api/v3/lat/{lat}/lon/{lon}/dist/{nm}` (up to 250 nm); `/v2/snapshot` is for feeders only |
| airplanes.live | Terms page is a Termly script embed we couldn't read. Its old guide (archived Apr 29, 2026): 1 request a second, non-commercial, no SLA ⚠️ | Now gated: HTTP 403 asking callers to email airplanes.live with a project description. OpenAPI spec (Apache-2.0): `/v2/point` (up to 250 nm), `/v2/mil`, `/v2/squawk`, `/v2/hex/{hex}/last` |
| OpenSky Network | ⚠️ (terms page 403s): non-profit research and education only; any operational use, including integration into a live product, service or automated system, even an internal one, needs a prior written agreement; the conditions travel with the data. The Impala history database is for research institutions only ⚠️ | OAuth2 client credentials only (Basic auth no longer accepted). Credits: anonymous 400 a day (current state only, 10 s resolution), account 4,000, active feeder (at least 30% uptime) 8,000, licensed 14,400 an hour. Signed-in users get 5 s resolution and up to 1 h back. `/states/all` costs 1 credit for 25 square degrees or less. `position_source`: 0 ADS-B, 1 ASTERIX, 2 MLAT, 3 FLARM |
| ADS-B Exchange | Owned by JETNET. Data policy bars sharing or derivative works ⚠️ | `robots.txt` disallows `/api/`. "Community API" via RapidAPI: $10 a month for 10,000 requests (about one poll every 4.3 min) |

**adsb.lol in more detail**

- Data comes from adsb.lol's feeders, FlyItalyADSB and TheAirTraffic.com.
- Nothing is filtered: LADD, PIA and military aircraft all appear (the
  sample had a LADD-flagged aircraft).
- **History** is at `github.com/adsblol/globe_history_2026`, ODbL (the
  release notes also carry CC0 text). One day per release, whole world
  only: e.g. `v2026.10.05-planes-readsb-prod-0` in two tar parts (1.86 and
  1.77 GB), plus `-prod-1`, `-staging-0` and `-mlatonly-0` releases. A
  valley backfill would mean downloading about 3.6 GB a day and filtering
  it; not done for now.

**One sample from each** (2026-10-07 00:07 UTC, i.e. Oct 6, 6:07 PM MDT;
60 nm):

| Source | Returned | In the box | Notes |
|---|---|---|---|
| adsb.lol | 15 | 12 | 14 `adsb_icao`, 1 `adsr_icao` (UAT rebroadcast as ADS-R). 3 helicopters: a B407 (LADD-flagged), an R22 via ADS-R, a B429. 7.3 KB JSON, 2.0 KB gzip |
| adsb.fi | 12 | 9 | |
| OpenSky, anonymous | | 10 | All ADS-B; no aircraft category without `extended=1`; 1.4 KB; `X-Rate-Limit-Remaining` 380 |
| airplanes.live | 403 | | |

The mix in the box: C172 ×6, B748, A306, A319, BCS1, E55P, EPIC; 3 on the
ground, 2 above 25,000 ft (overflights). No MLAT positions in any sample.

**adsb.lol's fields** (readsb v2): `hex`, `type`, `flight`, `r`
(registration), `t` (ICAO type), `category`, `lat`, `lon`, `alt_baro` (ft,
or `ground`), `alt_geom`, `gs` (kt), `track`, `true_heading`, `baro_rate`,
`geom_rate`, `squawk`, `emergency`, `nav_qnh`/`nav_altitude_mcp`/`nav_heading`,
`nic`/`nac_p`/`nac_v`/`sil`/`sda`/`gva`, `mlat[]`, `tisb[]`, `seen`,
`seen_pos`, `rssi`, `dst`, `dir`, `messages`, and `dbFlags` (1 military, 2
interesting, 4 PIA, 8 LADD). adsb.fi adds `desc`, `year` and `ownOp`
(owner or operator: never stored). Helicopters are picked out by
transponder category A7 plus the FAA registry's aircraft type (rotorcraft).

**Expected volume at one request every 10 s**

- 8,640 requests a day (17,280 at 5 s, which would be a fifth of the 1
  request a second adsb.fi publishes). Back off on any 4xx or 429.
- About 3–8 aircraft in the box overnight and 15–30 at daytime peaks ⚠️;
  measure in the first week.
- At 12 aircraft on average, keeping only new positions (skipping an
  unchanged `seen_pos`): about 104,000 rows a day, about 17 MB a day with
  the index (about 6 GB a year). The raw gzip archive adds about 17 MB a
  day. At 5 s: 207,000 rows and 33 MB a day, about 12 GB a year.

**Coverage gaps** ⚠️

- Gowen Field's Army Guard helicopters may fly without ADS-B Out: then
  they're visible only through MLAT (which needs Mode S and 3 or more
  receivers), or not at all.
- Aircraft with only Mode A/C transponders never show.
- Many light aircraft use UAT on 978 MHz and appear only through ADS-R or
  TIS-B rebroadcasts, or to a 978 MHz receiver.
- Fire traffic (the National Interagency Fire Center and Boise's air tanker
  base) is mostly fixed-wing tankers and lead planes, which broadcast ADS-B.
  Helicopters on fires work far from feeders.
- The three sample helicopters were at 2,700–5,350 ft barometric (Boise's
  airport field is about 2,870 ft), so low-level coverage exists near Boise.

**FAA aircraft registry** (the releasable aircraft database on faa.gov)

- `registry.faa.gov` `robots.txt` 403, so no rules. Refreshed daily at
  11:30 PM Central. Comma-delimited, about 60 MB.
- Files: Master, Dealer, Document Index, Aircraft Reference (make and
  model), Deregistered, Engine Reference, Reserved N-Number.
- No license stated; a US government work, so public domain (17 U.S.C.
  § 105).
- Joined on `MODE S CODE HEX`, the ADS-B hex code.
- Private owners can ask for their names and addresses to be withheld (49
  U.S.C. § 44114(b)); eligible aircraft are used for private purposes and
  not owned by a government entity.
- **What we may show:** N-number, ICAO type, make, model and series,
  aircraft and engine type, seats, weight class, year built, certification
  and airworthiness class, the registrant's *type* (individual,
  partnership, corporation, co-owned, government, LLC, non-citizen) and
  status. ⚠️ Field names are from the FAA's layout document, not re-read.
- **Never shown for private registrants:** name, street, city, ZIP, county,
  other names. The research proposed showing an owner's name only for
  government and airline or air-carrier registrants; the Oct 7 decision
  goes further, and owners' names and addresses are never stored.
- LADD and PIA aircraft (`dbFlags` 8 and 4) are treated as "do not
  identify", even though the sources publish them: kept only as an
  anonymous type and track whose key changes daily (DECISIONS, Oct 7).

**Other FAA data**

- **Temporary flight restrictions:** `tfr.faa.gov` `robots.txt` 404 (no
  rules). A JSON list at `/tfrapi/exportTfrList` ⚠️ (from an apis.io
  listing; not fetched).
- **SWIM / SCDS** ⚠️ (search snippets): free, but needs a signed Service
  Access Agreement. JMS (Solace) feeds: SFDPS (en route) and STDDS/TAIS
  (terminal). Not meant for uses that affect the National Airspace System,
  and redistributors must pass on outage notices.

---

**Back to:** [README](../README.md)
