# 7. Do-it-yourself data collection

What a small independent team can legally collect right now, which commercial
sources are off-limits and why, which sources open up with an agency or
university partner, and how to run a first data sprint.

*Not legal advice. Terms were read on Oct 5, 2026 and change often; re-check
them before relying on them.*

---

## 7.1 Summary

- **Harvesting Google is not allowed.**
  - Scraping the Google Maps website is prohibited, and so is bulk-downloading
    from it.
  - The Google Maps Platform APIs forbid storing or bulk-downloading
    directions results.
  - So neither can be used to build a travel-time database.
- **The other commercial APIs are the same.** TomTom, HERE, Mapbox and Waze
  all prohibit, under self-serve terms, the core thing a study needs: storing
  months of results and publishing analysis of them. They allow live use,
  short caching, or evaluation only.
- **Agencies can get these data legitimately.**
  - Google's **Roads Management Insights** stores traffic-aware travel times in
    BigQuery every 10 minutes, but only for public-sector road managers on
    their own roads.
  - **Waze for Cities**, **Google Green Light**, and **NPMRDS/INRIX** via
    COMPASS or ITD are likewise agency paths.
  - For an outside team, partnering is the way to get probe data.
- **What you can do yourself today:**
  1. **GPS "floating car" runs.** The best signal-level data you can own.
  2. **Direct signal-timing observation**: stopwatch or video from the
     sidewalk.
  3. **ACHD camera snapshots**, to document queues. ACHD's image host
     disallows automated access, so get ACHD's permission first.
  4. **Public datasets**: ITD counts and crashes, COMPASS, OpenStreetMap.
  5. **ACHD's published counts table** (24-hour and peak-hour counts):
     browse it by street, or ask ACHD for a CSV export of the whole table.
  6. **Public records requests** for ACHD's own timing and performance data.
- **Tools in `tools/`** automate items 1, 3 and 4. See [tools/README.md](../tools/README.md).

## 7.2 Commercial traffic APIs: what the terms allow

| Source | Useful data | Free tier | Store results long-term? | Key terms |
|---|---|---|---|---|
| **Google Maps Platform** (Routes API, Distance Matrix) | Traffic-aware route duration and free-flow duration; per-segment traffic on polylines (Enterprise) | Traffic-aware routing bills as "Pro": 5,000/month free, then $10 per 1,000[^gpricing] | **No** | §3.2.3(a) "No Scraping … Customer will not: (i) pre-fetch, index, store, reshare, or rehost Google Maps Content outside the services; (ii) bulk download … directions, distance matrix results, roads information…" §3.2.3(b) "No Caching … except as expressly permitted." The Routes caching allowance covers only lat/lng for 30 days.[^gterms][^gservice] |
| **Google Maps website** (typical traffic, travel times) | Same, via the consumer site | — | **No** | Maps terms prohibit "mass download or create bulk feeds of the content" and using Google Maps "to create or augment any other mapping-related dataset"; robots.txt disallows `/maps`.[^gmapsterms] |
| **Waze** (app / web) | Live traffic, alerts | — | **No** | Personal, non-commercial use; no "automated means" and no "mass download Content or create a database." Waze for Cities is for government agencies.[^waze] |
| **TomTom** (Traffic Flow, Routing) | Current vs. free-flow speed and travel time per segment | 20,000/month free; about €1 per 1,000 after[^tomtompricing] | **No** | Free tier is "for Evaluation Use only." Caching only per cache headers; no "secondary or derived database."[^tomtomterms] |
| **HERE** (Traffic API v7) | Speed, free-flow speed and jam factor for *every segment in a bounding box* per call | 5,000/month free; one box per 15 min ≈ 2,900 calls/month[^herepricing] | **No** (≤30 days) | §6.4: no "derivative works"; no providing "Results … to another person or entity"; no caching or storing Results "for more than 30 days" except for internal testing/evaluation or audit.[^hereterms] |
| **Mapbox** (Directions/Matrix, `driving-traffic`) | Duration, typical duration, congestion levels | 100,000/month free | **No** | Product terms: "only query the Services in response to human user queries … not perform bulk or automated queries … not export, download, cache or store."[^mapbox] |

**Bottom line:** these APIs are fine for a *live* look, such as an app that
shows current conditions on a Google map. They're not usable for a
longitudinal study. Building one anyway would breach the terms and could
undermine the credibility of any findings presented to ACHD.

### Licensed or partner paths that do allow storage

| Path | Who can get it | What it gives |
|---|---|---|
| **Google Roads Management Insights** | "Public sector entities and infrastructure managers," for roads they manage[^rmi] | Traffic-aware and static trip durations for chosen routes, updated every 10 min (2 min on the real-time tier), stored in BigQuery. **ACHD and ITD are exactly the intended customers.** |
| **Google Project Green Light** | City/agency traffic engineers | Timing recommendations and measured impact (see [chapter 5](05-ai-and-emerging-tech.md)) |
| **Waze for Cities** | Government agencies, DOTs, 911 centers | Two-way incident and jam data exchange |
| **NPMRDS** | State DOTs and MPOs (COMPASS, ITD) and their contractors | Probe speeds on National Highway System roads |
| **INRIX** arterial data | Already purchased by ITD and used by COMPASS | COMPASS can run analyses (as it did for Nampa's Middleton Rd retiming) |
| **INRIX × MetroLab challenge** | Teams of university researchers plus a local government partner | Free INRIX API access for up to a year. The 2026 cycle closed in March; watch for 2027.[^metrolab] |
| **TomTom MOVE / Traffic Stats, Mapbox Traffic Data, StreetLight** | Paid license (TomTom MOVE has a 30-day trial) | Historical speeds. StreetLight says free academic access is exhausted and funded projects can get discounted licenses.[^streetlight] |

The practical play is a **university plus agency partnership**: Boise State's
transportation lab, which already has a fiber link to ACHD's operations
center, combined with ACHD or COMPASS. That unlocks most of the table above.

## 7.3 Methods you can use today

### A. GPS floating-car runs (the most valuable)

**What it is:** drive a corridor repeatedly with a phone logging GPS once
per second, at the speed of traffic ("float"). Each run records where you
stopped, for how long, and total travel time.

**What it tells you:**

- travel time and its variability by time of day;
- which signals stop you, how often, and for how long;
- whether green waves exist in each direction;
- with enough runs, the signal **cycle length** (see G below).

**How:**

1. **Choose a corridor and limits.** For example Chinden, Cloverdale →
   Eagle Rd, which is the region's most congested segment, or Eagle Rd,
   Fairview → Chinden.
2. **Choose periods:** AM peak, midday, PM peak, and possibly evening.
   Signal plans change by time of day, so analyze each period separately.
3. **Run counts:** aim for **6–10+ runs per direction per period**, more on
   variable corridors. Note the date and time; avoid holidays and incidents,
   or log them.
4. **Apps:** any that record 1-second GPX tracks, e.g. GPSLogger (Android),
   OsmAnd (Android/iOS), or similar iOS trackers. Start the log before the
   corridor and stop it after.
5. **Safety:** set and forget. A passenger handles the phone; the driver never
   touches it.
6. **Analyze:**

   ```
   python3 tools/gps_runs.py runs/*.gpx --signals data/static/osm_traffic_signals.geojson --estimate-cycle
   ```

   This produces runs.csv, stops.csv, and signals.csv (share of runs stopped
   and mean stop at each signal).

**Volunteers:** if friends contribute runs:

- get written consent;
- trim the start and end of each track (a privacy zone of a few hundred
  meters around homes);
- use pseudonymous IDs;
- publish only aggregates, never raw traces;
- set a deletion date.

### B. Direct signal-timing observation

**What it is:** stand on a public sidewalk and record when each signal
indication changes, with a stopwatch app or phone video. This is a classic
manual technique, and it measures timing directly instead of inferring it.

**What it tells you:**

- cycle length;
- green split for each movement;
- whether a phase maxes out (runs to its limit with cars still waiting) or
  gaps out (ends early because no more cars are detected);
- whether left turns or pedestrian phases are skipped;
- with two observers at adjacent signals using phone clocks (both on network
  time), the **offset** between them, i.e., whether the corridor is truly
  coordinated.

**How:**

- Record at least 10 consecutive cycles per site per time period.
- Log the start of green, yellow and red for the main-street through phase
  and at least one side-street phase. Note pedestrian calls and queue
  clearance.
- **Legal and courtesy:** filming from a public sidewalk is generally lawful
  in Idaho.
  - Record video **without audio**, to avoid capturing conversations under
    Idaho's wiretap law.
  - Don't obstruct the sidewalk or attach anything to ACHD poles.
  - Drones need consent to record people for publication and must follow FAA
    rules.[^legal]

### C. ACHD camera snapshots

**What it is:** public traffic cameras in the valley publish **still images,
not video streams**. We measured the ACHD images in Oct 2026: each updates
**about every 59 seconds** and lags real time by about a minute.

**Where they are and how many (checked Oct 4–5, 2026):**

| Source | Cameras | Where to see them | Machine-readable |
|---|---|---|---|
| **ACHD** (Ada County arterials, state highways, and the I-84/I-184 interchanges) | **228** cameras. The GIS layer has 232 records, but 4 cameras are listed twice. At 8:22 pm on Oct 4, **220 were live** (updated within 5 min) and **8 were stale**: two dead for years (I-84 & McDermott, I-84 & Northside), and Hwy 16 & Boise River, State & Hwy 16, State & 21st, State & Moyle, Federal & Apple and Avalon & Kay for 4–52 days. | ACHD's website traffic map, and [511.idaho.gov](https://511.idaho.gov) (which republishes 215 of them) | ACHD GIS layer: `gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer/26`. Image URL pattern: `https://more.achdidaho.org/ATIS/CCTV/CCTV_<id>.jpg` |
| **ITD** traffic cameras (I-84) | **10** listed on 511 in the valley, but **8 are the same physical cameras as ACHD's** (matching ID numbers, within about 120 m). Only **2 are unique**: I-84 at Midland Blvd (Nampa) and I-84 at Laster Lane (Caldwell). | [511.idaho.gov](https://511.idaho.gov) | 511 Idaho API (free key). Images at `https://511.idaho.gov/map/Cctv/<imageId>`, refreshed about every 60 s in the viewer |
| **ITD road-weather stations** (RWIS) | **6 sites, 18 views** on I-84 (Caldwell, Northside, Kuna/Meridian, Eisenman, Broadway, the Wye) | 511.idaho.gov | Same as above; aimed at pavement and weather, not intersections |
| **Nampa, Caldwell** | Both run traffic camera systems, but we found **no public feed**. Nampa police record their traffic cameras ⚠️, so footage may be requestable as a public record subject to retention. | — | — |

ITD's GIS also lists about 17 camera views along I-84 in Nampa and Caldwell
(IDs 301–320) that don't appear on 511, possibly newer installs from the
I-84 widening.

**Totals:** about **230 distinct public traffic cameras** (228 ACHD + 2 ITD)
plus 6 weather-station sites, all still images. Our dated list with
coordinates, image URLs and status is kept with the project's private files,
because parts of it came from 511's camera-list page. The ACHD locations
alone come from ACHD's open GIS layer at any time
([`basemap/camera_points.py`](../basemap/camera_points.py)).

**What it tells you:**

- whether queues are present, and roughly how long, across many samples;
- spillback (queues blocking upstream intersections), turn-bay overflow, and
  incidents.

At one frame a minute it can't resolve individual cycles (typically
90–180 s), but over a week of peaks it gives solid statistics. Later, an
object-detection model could count queued vehicles automatically.

**How:** sample chosen cameras every minute during a PM peak, for example
for two hours. The Chinden & Cloverdale and Chinden & Meridian cameras cover
the #1 congested segment. Our sampling tool is kept privately: ACHD's image
host disallows automated access, so it only runs by hand, with permission.

**Terms and crawler rules:**

- ACHD's camera images are served from `more.achdidaho.org`, whose
  `robots.txt` disallows all automated access, so **get ACHD's OK first**. Ask Traffic Engineering (208-387-6100) for permission to sample a
  few cameras for research.
- 511 Idaho republishes 215 of the ACHD cameras. Its image URLs aren't
  disallowed, but its camera-list endpoint is, so use 511's **official API**
  (free key) to look up camera IDs.
- ACHD's GIS services carry only "as-is" disclaimers. Keep camera lists short
  and polling at no more than once a minute.

### D. Public datasets

`python3 tools/collect_static.py` downloads:

- **OpenStreetMap traffic signals** with crossing street names (ODbL:
  attribute "© OpenStreetMap contributors"; derived databases you publish
  must stay ODbL);
- **ACHD camera inventory** (228 cameras; duplicate records removed);
- **ITD AADT** by segment for the latest year (2,090 segments in the
  Ada/Canyon box for 2025);
- **ITD automatic traffic recorder monthly volumes** for 45 stations in
  Ada/Canyon. Data runs through roughly two to three months before the
  current date.

Also useful, not yet scripted:

- **ITD crash points** (2005–2023);
- **COMPASS's congestion measures** and **count map**;
- the **511 Idaho API** (incidents and work zones; free key; no speed data).

See [chapter 3](03-traffic-context-and-data.md#36-data-sources-what-you-can-actually-get).

### E. ACHD's published traffic counts table

ACHD's [Traffic Counts](https://www.achdidaho.org/my-commute/traffic/traffic-counts)
page embeds a table served from
`more.achdidaho.org/Departments/Engineering/Traffic/trafficCounts.aspx`.
Each row has:

- street and location (e.g., "10TH ST, NORTH OF BANNOCK ST, Approach & Total");
- city;
- count date;
- 24-hour count;
- direction;
- AM peak (7–9) and PM peak (4–6) volumes by direction.

It shows 10 rows per page, filterable by street or city name. Count dates
range from the early 2000s to 2025, so check how old each count is before
using it.

- **Manual use is fine:** filter by a corridor's street name in your browser
  and copy the rows you need.
- **Bulk download isn't:** that server's `robots.txt` disallows automated
  access, so we haven't built a scraper. The table clearly comes from a
  database. **Ask ACHD Traffic Engineering for a CSV export of the whole
  table**, or request it as an existing public record. This is the fastest
  route to every count at once.
- The [Turn Movements](https://www.achdidaho.org/my-commute/traffic-turn-movements)
  page embeds `more.achdidaho.org/Departments/Engineering/Traffic/TurnMovements.aspx`
  (confirmed Oct 5).
  - **What's in it:** for each intersection, the busiest hour in the AM,
    noon, PM and weekend windows, with left, through, right and U-turn
    counts for each approach. That's exactly the input a retiming needs.
  - **Next step:** include it in the same request.
- **Full copy (Oct 5, owner-approved one-time exception):** both tables,
  582 requests about 2.8 s apart. Files and notes are in
  [data/](data/README.md).
  - **Counts:** 3,827 locations.
    - Recency: 1,602 counted 2024 or later; 491 last counted before 2010.
    - Busiest arterial: Eagle Rd, which holds the top five non-freeway
      spots. North of I-84 carries 66,488 a day (Oct 2024).
  - **Turn movements:** 916 intersections.
    - Recency: 487 counted 2021 or later.
    - Busiest single hour: Eagle & Fairview, PM, June 2023, 7,060
      vehicles. Then the I-84 ramps at Meridian Rd (6,911) and Meridian &
      Overland (6,365).
  - **Limit:** the tables seem to show only the latest count per location.
    History needs ACHD's export.

### F. Public records requests

The one route to ACHD's actual signal data. Ask for existing records:

- timing sheets and coordination plans for your corridor;
- the date each signal was last retimed;
- detector configuration and trouble tickets;
- Centracs performance-measure exports or high-resolution event logs for a
  sample week.

Idaho requires a response within 3 working days (extendable to 10), and
residents get the first 2 hours of labor free. See
[chapter 3](03-traffic-context-and-data.md#public-records-idaho-public-records-act).

**Cross-checking:** with observed timing (method B) and the official timing
sheet (method F) side by side, you can tell whether the field matches the
plan. A mismatch can point to detection failures or a clock or coordination
problem.

### G. Inferring signal timing from GPS runs (a mini Green Light)

Coordinated signals repeat on a fixed cycle. When you're stopped at a red
and then leave on green, your departure time marks the start of that
signal's green, give or take a few seconds for queue position. Collect enough
departures within the same time-of-day plan and they line up when you take
the time modulo the true cycle length. `gps_runs.py --estimate-cycle` searches
50–200 s for the cycle that lines them up best. This is the same basic idea
Google's Green Light uses at scale with Maps data.

- **Needs:** at least 5, better 10+, stopped departures at a signal within
  one time-of-day plan (e.g., all PM-peak weekday runs).
- **Pitfall we hit and fixed:** departures that repeat every 150 s also
  repeat every 75 s and 50 s, so the estimator picks the *longest* strong fit.
  Multiples like 300 s fit poorly.
- **Limits:**
  - Actuated (non-coordinated) signals don't hold a fixed cycle, which the
    poor fit score will show.
  - Free (uncoordinated) operation off-peak won't work.
  - Plans that switch mid-period mix two cycles.
- **Tested** on simulated runs: it recovered a 150 s cycle from 9 stopped
  departures. It has **not yet been validated on real Boise data**, so
  compare its estimates against a direct observation (method B) before
  trusting them.

## 7.4 What we verified from this environment (Oct 2026)

| Check | Result |
|---|---|
| ACHD camera inventory service | Works: 232 records = 228 unique cameras; 220 live, 8 stale at check time |
| ACHD camera image refresh | About every 59 s (Last-Modified header over 12 min of polling) |
| ITD AADT service | Works: 2025 data, 2,090 segments in the Ada/Canyon box; e.g. I-84 Eagle→I-184 at 151,500 |
| ITD ATR monthly service | Works: 45 Ada/Canyon stations from 2021, monthly data through Jul 2026 (later months are empty placeholders) |
| OpenStreetMap | The Overpass API was unreachable from our sandbox (it normally works). A small read through the main OSM API worked: **51 signal nodes** along a narrow Eagle Rd strip, many intersections mapped as 2–6 nodes. `gps_runs.py` merges nodes within 60 m into one intersection. |
| ACHD traffic counts and turn-movement pages | HTTP 403 to automated requests. The public "Traffic Counts" GIS layer (3,880 segments) carries only a segment ID, no volumes; ACHD's `GisData_Traffic` and `GisData_Signal` services require a login. |
| ACHD traffic counts page, in a normal browser (checked Oct 5, 2026) | The page embeds a table from `more.achdidaho.org/.../trafficCounts.aspx` (see method E); that host's `robots.txt` disallows automated access. A separate `OpenDataHub_PublicLayers/ACHD_Traffic_Counts` map service exists on `maps.achdidaho.org` but answers "not started", meaning it's switched off. ACHD apparently used to publish count values there; it's worth asking ACHD to turn it back on or provide an export. |
| ACHD "Traffic Signals" layer (bike-map data) | 2,469 points, last edited Aug 2022, with only a "Purpose" field: far more than the ~465–600 signalized intersections, so likely poles or heads, not intersections. Companion layers: 182 pedestrian signals, 33 school flashers, 68 fire signals. |
| COMPASS count map data (swidrdc.org) | Two layers, portable counts and ATR (permanent counter) counts, from multiple agencies. Unreachable from our sandbox (TLS failure at our proxy); works in a normal browser. |
| 511 Idaho developer docs | Reachable; API key required |
| 511 Idaho cameras | 457 camera sites statewide; in the valley, 215 republished ACHD cameras, 10 ITD (8 duplicating ACHD) and 6 weather-station sites. No video URLs: still images only |
| ITD MS2 count database | Blocked (HTTP 403) from our sandbox |

## 7.5 A 4-week data sprint for one corridor (suggested)

**Example corridor:** Chinden Blvd from Cloverdale to Eagle Rd, westbound.
It was the region's worst segment in 2024, with a travel time index (peak
travel time ÷ free-flow travel time) of 3.26.

| Week | Do |
|---|---|
| 1 | Run `collect_static.py`. List the corridor's signals: check the OSM list and trim it to a CSV of name, lat, lon. Pull COMPASS's 2024 congestion figures for the segment. File a records request with ACHD/ITD for timing sheets and last-retimed dates (Chinden is US-20/26, so ask both). |
| 1–3 | 30+ GPS runs: both directions, AM, midday and PM, weekdays. Two observation sessions (method B) at the 2–3 worst intersections the runs reveal. Camera sampling at those intersections during 3–5 PM peaks. |
| 4 | Run `gps_runs.py --estimate-cycle`. Compare: our travel times vs. COMPASS's index; our observed timing vs. the official sheets (if received); the camera queue record. Write a 2-page memo with charts: what's timing-fixable, what's capacity-bound. |

Cost: fuel and time. Output: a credible, reproducible corridor baseline to
bring to ACHD and COMPASS, and the starting point for any partnership.

---

**Next:** [08 — Data inventory](08-data-inventory.md) · **Related:** [06 — Automation and AI agents](06-automation-and-ai-agents.md)

[^gpricing]: Google Maps Platform pricing and SKU details (accessed Oct 2026). https://developers.google.com/maps/billing-and-pricing/pricing · https://developers.google.com/maps/billing-and-pricing/sku-details
[^gterms]: Google Maps Platform Terms of Service, §3.2.3 (last modified Aug 26, 2026). https://cloud.google.com/maps-platform/terms
[^gservice]: Google Maps Platform Service Specific Terms, Routes API (§19). https://cloud.google.com/maps-platform/terms/maps-service-terms
[^gmapsterms]: Google Maps/Google Earth Additional Terms of Service. https://www.google.com/help/terms_maps/
[^waze]: Waze Terms of Service (https://www.waze.com/legal/tos) · Waze for Cities eligibility (https://www.waze.com/discuss/t/waze-for-cities/377967)
[^tomtompricing]: TomTom developer pricing. https://developer.tomtom.com/pricing
[^tomtomterms]: TomTom developer Terms and Conditions, §2.2, §11.4, §11.6.1. https://docs.tomtom.com/legal/terms-and-conditions
[^herepricing]: HERE pricing. https://www.here.com/get-started/pricing
[^hereterms]: HERE Platform Terms (Sept 2023), §6.4. https://www.here.com/en-gb/terms/here-platform-terms-september-2023
[^mapbox]: Mapbox Product Terms, §1.9 and §2.10 (updated Jul 21, 2026). https://www.mapbox.com/legal/product-terms
[^rmi]: Google Roads Management Insights overview and guidelines. https://developers.google.com/maps/documentation/roads-management-insights/overview · https://developers.google.com/maps/documentation/roads-management-insights/guidelines
[^metrolab]: INRIX × MetroLab Challenge 2026. https://fas.org/publication/inrix-metrolab-challenge-2026/
[^streetlight]: StreetLight transportation research access. https://www.streetlightdata.com/transportation-research/
[^legal]: Idaho Code §18-6702 (interception of communications) https://legislature.idaho.gov/statutesrules/idstat/Title18/T18CH67/SECT18-6702/ · §21-213 (unmanned aircraft) https://legislature.idaho.gov/statutesrules/idstat/Title21/T21CH2/SECT21-213/
