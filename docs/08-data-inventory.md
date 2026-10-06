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
| **Valley Regional Transit GTFS** (new) | Static schedules, stops and route shapes, plus **GTFS-realtime vehicle positions, trip updates and alerts** | Static: `valleyregionaltransit.org/GTFS/vrt_transit1.zip`. Real-time: `s3.amazonaws.com/etatransit.gtfs/valleyregionaltransit.etaspot.net/position_updates.pb` (also `trip_updates.pb`, `alerts.pb`) | VRT: "We provide these files for public use." **Buses act as GPS probes**: their logged positions give real arterial travel times and signal delay on State St, Fairview and other bus routes. The feed was live but empty on a Sunday night. **Measured Oct 5, 2026 (weekday, 2–3:45 PM, 4,637 fixes from 34 buses):** each bus reports every 30 s (p10–p90: 26–35 s; 91% of gaps ≤35 s, 0.5% over a minute), about 4 s before the feed publishes it; a moving bus covers about 200 m between fixes (p90 440 m); 22% of fixes are stationary (stops, signals). No speed field, so speeds come from consecutive fixes. **Fleet coverage, checked Oct 5, 2026 (2–7 PM):** 42 buses reported at once at the peak (5:31 PM), exactly the 42 fixed-route buses NTD lists for peak service (Aug 2026), and 42 distinct buses over the afternoon, so the feed looks complete for the fleet. **Route labels are not complete:** 25% of fixes carry a trip ID that names no route, because the static schedule predates VRT's Oct 1 service changes. Matching those buses to route shapes puts them on routes 7, 8, 16, 28 and 40 (74–99% of their fixes within 40 m of one route), the routes that never appeared labeled. Route 30 was discontinued Oct 1 (VRT's service-changes page); R1 didn't appear. Since Oct 5 the transit stream does this matching every 5 minutes (`ingest/transit_match.py`), which leaves under 1% of fixes unlabeled. Licensed CC BY 3.0. |
| **ITD work zones (WZDx)** (new) | 703 statewide work zones on Oct 6, 2026, 239 of them touching Ada or Canyon, with lane-by-lane status on most, in the USDOT standard format (v4.1) | `https://511.idaho.gov/api/wzdx` | **No key needed.** Published for public use: we may republish it, raw or aggregated, crediting ITD (owner, Oct 6). Checked against the spec in [§8.8](#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026). |
| 511 Idaho official API | Events, cameras, message signs, weather stations, road conditions, restrictions, advisories | `https://511.idaho.gov/developers/doc` (see §8.6) | Free key; **10 calls per 60 s** (confirmed in the docs). Each call returns a whole resource. |
| **511 Idaho camera images** (ACHD's cameras republished by ITD, plus ITD's own) | About 210 of ACHD's 228 cameras, plus ITD cameras; still images refreshed about once a minute | `https://511.idaho.gov/map/Cctv/<imageId>` (IDs from the official API) | 511 serves its own ITD-stamped copies from its own servers, lists ACHD as a provider, and its robots.txt allows this path. Owner decision Oct 5: legitimate. See [ch. 11](11-camera-validation-layer.md). |

**Map, weather, crashes and demographics**

| Source | What it gives | How to get it | Notes |
|---|---|---|---|
| OpenStreetMap | Signal locations (often 2–6 nodes per intersection), road network, lanes | Overpass API or the OSM API | ODbL: attribute it; share-alike for published derived databases |
| **Boise airport weather** (new) | Hourly visibility and weather codes, back many years | Iowa Environmental Mesonet ASOS download (station BOI) | Test the **fog → detector fallback → long greens** link (chapter 2). IEM's `robots.txt` asks for a 120-second crawl delay, so make occasional bulk requests only. |
| **ACHD road centerlines with posted speeds** (new, Oct 5, 2026) | Every road segment in Ada County (38,727) with **posted speed** (`PostSpeed`), functional class, one-way flag, street name and address ranges | ACHD's open GIS: `gis.achdidaho.org/.../Maintenance/Road_Centerline/MapServer/7` (no robots.txt; automated access allowed) | All segments carry a speed: arterials look right (Eagle Rd 45–55 mph, Chinden 35–55, Fairview 35–40, State 35–55); 30,565 local streets are 20 mph, likely a residential default ⚠️ (not verified against signs); a few anomalies (one interstate segment at 20). **Ada County only**: Canyon County needs OSM `maxspeed`, ITD, or city/highway-district data. |
| **ACHD traffic counts layer** (new, Oct 5, 2026) | A `Traffic_Counts` feature layer on ACHD's open GIS (`ArcGIS_Hub` folder), alongside sidewalks, pavement, bike network and the master street map | `gis.achdidaho.org/.../ArcGIS_Hub/Traffic_Counts/FeatureServer` (open) | **Examined Oct 5: locations only.** 3,880 count-location lines, each with a location ID (`PID`), created/edited dates and length, but no counts and no related tables. The counts themselves are only in ACHD's robots-disallowed tables, whose rows don't carry the ID, so joining would mean matching street names and descriptions. The official export we've asked ACHD for is still the clean route. |
| **Census commute flows (LEHD LODES8)** (new, Oct 6, 2026) | Jobs by the census block where the worker lives and where they work, all jobs, 2002–2023; Idaho and Oregon (for Ontario) | `lehd.ces.census.gov/data/lodes/LODES8/` (robots.txt allows all); `tools/lehd_flows.py` | Public domain. **2023:** 20,500 jobs in Ada or Canyon are held by residents of the 7 counties around them. Most tied to Ada and Canyon (share of residents' jobs): Owyhee 62% (Homedale 67%), Boise County 59%, Gem 58% (Emmett 60%), Elmore 44% (Mountain Home 46%, military not counted), Payette 35%, Washington 25% (Weiser), Malheur County OR 12% (Ontario 10%). Payette County and Ontario form their own job market across the river (2,771 Payette County residents work in Malheur County). Caveats: counts jobs, not trips; leaves out the military and self-employed; places a job at its employer's address. |
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
redistribution. Read it before building on the API. **Oct 6, 2026:** the
owner has the key, and ITD is fine with our use. The full API reference
(11 endpoints) is kept with the private files.

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

**The spec.** The Work Zone Data Exchange (WZDx) is USDOT's open format for
work zones, in the public domain (CC0) and kept at
[github.com/usdot-jpo-ode/wzdx](https://github.com/usdot-jpo-ode/wzdx).
Its last version is 4.2 (Feb 2023). It has since become a formal standard,
the Connected Work Zones (CWZ) Implementation Guide and Standard v01.00
(ITE, AASHTO and NEMA with SAE, finalized Dec 2024;
[ITE's validation report](https://www.ite.org/ITEORG/assets/File/CWZ_Validation_Report-final%20v01_00-260122.pdf)).
A few states already publish CWZ feeds; Idaho doesn't yet.

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
| Lanes | Lane-by-lane status on 561 (1–5 lanes; general, shoulder, exit lane); 126 lanes closed and 228 alternating one-way |
| Limits | Width, weight, height and length limits on 263, with values |
| Speeds | Reduced speeds on 228, in km/h converted from round mph (72.42 = 45 mph, 40.234 = 25) |
| Other fields | Type of work on only 24. The description repeats the schedule, width and speed in words. Beginning cross street on all, mileposts on 571. No contact or update interval in the header |
| IDs | 38 ERS event numbers; 82 segments `N-k` of event `N` (in the non-standard `road_event_id`); 583 hash IDs, one per day of a recurring schedule, chained as first and next occurrence (all 934 links resolve). IDs didn't change across three fetches over 6 minutes; whether the daily hashes stay the same over days is still to check |
| HTTP | Rebuilt on every request (new ETag, header time = request time), so asking "changed since?" always returns the whole feed. 1.9 MB raw, 124 KB gzip, 111 KB Brotli. The three fetches were otherwise identical |

So the feed is good for **where and when work is planned** and for
**which lanes it closes**. We clean it on load: drop the `"NaN"` speeds,
move the early end dates forward a day, store speeds in mph, and mark
locations as approximate. Worker presence isn't shown as live.

**Collected since Oct 6, 2026** by the `wzdx` service (`itd_wzdx` in
[ingest/](../ingest/README.md)), every 5 minutes, owner's OK: changed
snapshots archived, every version of each work zone in `raw.record`,
cleaned rows in `evt.event` ([ch. 12 §12.7](12-database-schema.md#127-evt-lifecycles)).

---

**Back to:** [README](../README.md)
