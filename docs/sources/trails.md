# Trails sources (researched Oct 7, 2026)

Sources for a `trails` plugin and the float-season part of a `water`
plugin: Ridge to Rivers and the other foothills trails with their live mud
and closure status, the Greenbelt, Forest Service, BLM and state OHV routes
and the rules on them, Park N' Ski routes, campgrounds and dispersed-camping
rules, the Boise River float, and the snow and river readings behind them.
"The box" is the valley box (W −117.05, S 43.00, E −115.95, N 43.85) and
"the ring" the proposed regional ring (about W −117.30, S 42.90, E −115.60,
N 44.30; [DECISIONS](../DECISIONS.md)). This page belongs to
[chapter 17](../17-sources-for-new-plugins.md) (sources for the new
plugins); the ideas behind it are in
[chapter 16](../16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water).

**Status: research only; nothing here is approved.** Each source goes to
the owner one at a time before anything is built ([SOURCES](../SOURCES.md)).
Every entry was checked against its official pages, robots.txt and terms on
Oct 7, 2026: of the 29 sources, 16 were confirmed and 13 corrected; none
was refuted or left unverifiable. Some claims inside entries were refuted:
that the Idaho Centennial Trail crosses the ring (it has 0 segments there),
that the USGS Water Data API needs a key (it's optional), that the Foothills
imagery has no known owner, that getoutside.idaho.gov's robots.txt
disallows us (it serves a bot challenge instead), and the license quote
given for COMPASS's pathways (it was the City of Boise's). Each entry's
result is in the **Verified** column and its subsection. "Not re-run" marks
figures from the research pass that verification didn't repeat; ⚠️ marks
anything resting on secondary sources or not checked at all.

**Requests made.** Verification read robots.txt on every host, read
service and item metadata (`?f=json`) and a few small JSON responses
(one NWPS gauge, one NRCS station list, R2R's article list), and made a
single statistics or count query wherever it re-checked a figure (each is
listed in that entry's evidence; the Barber Park sensor table took two),
plus one HEAD request on the RIDB export. No account or key was used, no dataset was
downloaded, and no edit operation or Survey123 form layer was touched.

---

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| **Ridge to Rivers, Boise and pathways** | | | | | | | | |
| [Ridge to Rivers trails and conditions](https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer) | City of Boise Parks & Recreation | 271 foothills trails with R2R's own condition (7 states), allowed uses, dogs, e-bikes, horses; trailhead amenities | ArcGIS FeatureServer, one call | None | City disclaimer only; the City's site terms forbid redistributing site content | 403, no rules | Use | Confirmed |
| [R2R weekly condition reports](https://www.ridgetorivers.org/condition-reports/) | City of Boise Parks & Recreation | "Weekend Trail Report" articles and closure posts | JSON list (title, link) | None | City site terms: no redistribution | Allowed | Internal only (title and link) | Confirmed |
| [Boise Parks GIS](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_Parks_Trails_Open_Data/FeatureServer/0) | City of Boise Parks & Recreation | City trails, facilities (including campgrounds), trailheads, off-leash areas, repair stations | ArcGIS FeatureServer | None | Disclaimer only; some items allow redistribution with credit | 403, no rules; hub Crawl-delay 60 | Use | Confirmed |
| [Greenbelt closures and mile markers](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer) | City of Boise Parks & Recreation; Boise Fire GIS | Greenbelt closures and detours; 1/10-mile markers | ArcGIS FeatureServer | None | Closures: disclaimer only. Markers: redistribution allowed with metadata or credit | 403, no rules | Use | Confirmed |
| [COMPASS bike and pedestrian network](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer) | COMPASS | Pathways, bike facilities, sidewalks, 28 permanent counter locations (no counts) | ArcGIS FeatureServer | None | None stated; credit COMPASS | 404, no rules | Use | Corrected |
| [Foothills Imagery 2026](https://tiles.arcgis.com/tiles/ocXK9Gg6fvIH5GTf/arcgis/rest/services/FoothillsImagery2026/MapServer) | Ridge to Rivers account; imagery's origin unknown | Tile cache over the Boise Front, updated June 2026 | Esri tile cache | None | None stated | 404, no rules | Needs owner action | Corrected |
| **The Boise River and the float season** | | | | | | | | |
| [Boise River hazards and access](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_River_Hazards_and_Access_-_VIEW/FeatureServer/10) | Boise Fire Department GIS | 119 hazards, rapids, put-ins and take-outs with status | ArcGIS FeatureServer | None | None stated; credit Boise Fire / City of Boise | 403, no rules | Use | Confirmed |
| [Boise River E. coli results](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/BPR_EColi_Testing/FeatureServer/0) | City of Boise Parks & Recreation | Latest sampling round at 7 river sites; no history | ArcGIS FeatureServer | None | Not stated; treat as a City layer (credit the City) | 403, no rules | Use | Corrected |
| [Barber Park floater information](https://gisprodapi.adacounty.id.gov/arcgis/rest/services/ParksAndWaterways/Barber_Park_Floater_Information/FeatureServer) | Ada County Parks & Waterways | Parking occupancy, floater count; a river sensor's temperature since 2023 | ArcGIS FeatureServer (advertises edits: query only) | None | None stated; credit Ada County | Blank file, no rules | Use | Corrected |
| [Float the Boise season facts](https://www.floattheboise.org/pages/floater-faq) | Ada County, Boise Parks & Recreation, Boise Fire | Season dates, typical flow range, rules | Facts entered by hand each season | None | Agency web content: facts, not text | Crawl-delay 60; arcgis.com allowed | Use | Confirmed |
| [NOAA NWPS, Glenwood Bridge (BIGI1)](https://api.water.noaa.gov/nwps/v1/gauges/BIGI1) | NOAA NWS (NWRFC forecasts; USGS observations) | Flow and stage now, forecasts, flood categories, historic crests | REST JSON | None | US government; credit NOAA/NWS and USGS | 404, no rules | Use | Corrected |
| [USGS Water Data APIs](https://api.waterdata.usgs.gov/) | USGS | Flow history, water temperature, statistics | OGC API; legacy NWIS until Feb 22, 2027 | None (a key is optional) | Public domain | New API: data paths **disallowed**; legacy: no rules | Needs owner action | Corrected |
| [IDFG fishing and boating access sites](https://gisportal-idfg.idaho.gov/hosting/rest/services/Access/IDFG_Fishing_and_Boating_Access_Sites_Public/FeatureServer/0) | IDFG | Access sites with ramps, docks, camping, restrooms | ArcGIS FeatureServer (advertises edits: query only) | None | IDFG disclaimer (not re-read); credit IDFG | 404, no rules | Use | Confirmed |
| **Forest, BLM and state routes and rules** | | | | | | | | |
| [USFS National Forest System trails](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer/0) | USDA Forest Service | 426 ring segments with allowed uses, class, surface, grade, e-bike classes | ArcGIS MapServer | None | Copyright "USDA Forest Service"; public domain assumed ⚠️ | 403, no rules | Use | Confirmed |
| [USFS Motor Vehicle Use Map (MVUM)](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_02/MapServer) | USDA Forest Service | Legal motor-vehicle designations by vehicle class and open dates | ArcGIS MapServer | None | Federal; public domain assumed ⚠️ | 403, no rules | Use | Confirmed |
| [USFS Region 4 forest orders](https://services1.arcgis.com/gGHDlz6USftL5Pau/arcgis/rest/services/R04_Forest_Orders_PUBLIC_VIEW/FeatureServer/0) | USDA Forest Service, Intermountain Region | Closures, fire closures, designated-camping orders, with dates (5 orders in the ring) | ArcGIS FeatureServer | None | FS disclaimer ("not legal documents"); credit USFS | 403, no rules | Use | Confirmed |
| [BLM GTLF roads and trails](https://gis.blm.gov/arcgis/rest/services/transportation/BLM_Natl_GTLF_Public_Display/MapServer) | Bureau of Land Management | Routes by public use, OHV designation, season restrictions | ArcGIS MapServer | None | "As is"; federal, public domain assumed ⚠️ | 404, no rules | Use | Confirmed |
| [IDPR Idaho Recreation Trails](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer) | Idaho Department of Parks and Recreation | Statewide routes with seasons by vehicle type; emergency closures; area restrictions; trailheads and OHV areas | ArcGIS FeatureServer | None | Not for commercial use; attribution required | 403, no rules; trails.idaho.gov redirects to an HTML page | Use | Confirmed |
| [IDPR winter and water layers](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Park_N__Ski_replace_view/FeatureServer) | Idaho Department of Parks and Recreation | Park N' Ski trails and parking, Idaho City yurts, life-jacket stations; the Idaho Centennial Trail (outside the ring) | ArcGIS FeatureServer | None | Liability disclaimer; credit IDPR | 403, no rules | Use | Corrected |
| **Campgrounds and reservations** | | | | | | | | |
| [USFS recreation sites](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_InfraRecreationSites_01/MapServer/0) | USDA Forest Service | 72 ring sites (campgrounds, trailheads, lookouts) with capacity, season, dated alerts and closures | ArcGIS MapServer | None | Copyright "USDA Forest Service"; public domain assumed ⚠️ | 403, no rules | Use | Corrected |
| [BLM recreation sites](https://gis.blm.gov/idarcgis/rest/services/recreation/BLM_ID_Recreation_Site_Point/FeatureServer/0) | BLM Idaho State Office; BLM HQ | Idaho site points; a national service refreshed nightly from RIDB | ArcGIS FeatureServer and MapServer | None | "As is"; credit BLM; RIDB content CC BY 4.0 ⚠️ | 404, no rules | Use | Corrected |
| [RIDB export and API](https://ridb.recreation.gov/download) | Recreation.gov / RIDB | Federal recreation areas, facilities and campsites; a 248 MB daily export | Export download; API needs a key | Account (API only) | CC BY 4.0 per data.gov ⚠️ | `/api` **disallowed**; `/downloads/` allowed, Crawl-delay 10 | Needs owner action | Confirmed |
| [Recreation.gov availability](https://www.recreation.gov/) | Recreation.gov | Live campsite availability | The site's internal `/api` only | None | Terms unread | `/api` **disallowed** | Avoid (link only) | Confirmed |
| [Idaho State Parks reservations](https://getoutside.idaho.gov/) | Idaho Department of Parks and Recreation | State-park campsite, cabin and yurt availability | Web app | None | Not checked | Bot challenge (405) | Avoid (link only) | Corrected |
| **Shared and context layers** | | | | | | | | |
| [OpenStreetMap paths and recreation tags](https://download.geofabrik.de/north-america/us/idaho.html) | OpenStreetMap contributors (Geofabrik extract) | Paths, tracks, cycleways, route relations, campsites, toilets, water | A second pass over the hand-downloaded extract | None | ODbL | Geofabrik: scripted downloads **disallowed**; hand downloads only | Use (needs a loader change) | Corrected |
| [NRCS SNOTEL](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:ID:SNTL) | USDA NRCS | Snow and weather at 4 ring stations, decades of history | REST JSON | None | Federal; public domain assumed ⚠️; credit NRCS | 404, no rules | Use | Confirmed |
| [Oregon National Historic Trail](https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/OREG_NHT/FeatureServer) | National Park Service, National Trails Office | The congressionally designated alignment at 1:100,000 | ArcGIS FeatureServer | None | Credit NPS; a BLM copy says public domain | 403, no rules | Use | Confirmed |
| [IDL publicly accessible lands](https://services2.arcgis.com/1cvrwLhZRFh3okEF/ArcGIS/rest/services/IDL_Public_Access/FeatureServer/0) | Idaho Department of Lands | Endowment lands reachable by public road or adjoining public land | ArcGIS FeatureServer | None | Disclaimer; credit IDL | 403, no rules | Use | Corrected |
| **Not used** | | | | | | | | |
| [Commercial and social trail platforms](https://www.trailforks.com/) | Strava, Trailforks, AllTrails, onX, Gaia, RainoutLine and others | User trails, conditions, activity heatmaps | Proprietary apps | Account | Proprietary | AllTrails disallows AI crawlers; long disallow lists elsewhere | Avoid | Corrected |

**Verdicts:** 22 use, 1 internal only, 3 need an owner action, 3 avoid.

## Ridge to Rivers, Boise and pathways

### Ridge to Rivers trails and live conditions

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer`,
  item title "Ada County R2R Interactive App Layers" (owner Boise_GIS).
  Ridge to Rivers' official map runs on Ada County's server
  (`gisprod.adacounty.id.gov/apps/r2r/main.js`) and reads layers 2 and 7,
  the web map 819709ab (owned by the RIDGE2RIVERS account) and the
  [Foothills Imagery 2026](#foothills-imagery-2026-tile-cache) tile cache.
- **Contents:** layers 0 Amenities, 2 Trails, 4 "Slow Zone" and 7 Trail
  Regions/Reserves; no tables. Trail fields (confirmed): `TrailID`,
  `TrailName`, `SystemName`, `TrailSubSystem`, agency name and type,
  `TrailMiles`, `TrailDescription`, `Rating` (Easy, Intermediate,
  Difficult, Road), `Motorized` (allowed, seasonal, prohibited), `R2R_Use`
  (Bike Only, Motorized, Multi-use motorized, Multi-use non-motorized,
  Pedestrian Only, Ski area Cat track, Access Road), `FamilyFriendly`,
  `R2R_DogOnL` (Controlled Dogs Off-Leash, Dogs Allowed On-Leash, Dogs Not
  Allowed), `DogComment`, `AllWeather`, `LevelOfUse`, `Accessible`
  (Accessible, Not Accessible, Ineligible, Not Evaluated), `Handbike`,
  `Ebike` (three values: allowed on motorized trails and roads, permit
  only, no), `PilotProgram` and `SpecialManagement` (each with a comment),
  `Condition`, `ConditionNotes`, `ConditionDate`, `Horses` (Yes, No), and
  the staff fields `Editor`, `EditDate`, `created_user` and
  `last_edited_user`. `Condition` has exactly seven values. Amenities:
  subtypes Mutt Mitt, Mutt Mitt w/ Trash, Trash, Parking, Restroom, Gate,
  Alert and Other; fields `Parking_Surface`, `Parking_Spaces`,
  `Horse_Trailers`, `ADA_Info`, `Notes`, `Status`.
- **Conditions on Oct 7:** 271 trails: 238 Dry/Tacky (latest
  `ConditionDate` Sep 11), 7 CLOSED (latest Sep 28), 26 Not Evaluated.
- **Coverage:** the Boise Front foothills, from Eagle, Avimor and Hidden
  Springs to Lucky Peak and up to Bogus Basin and Shafer Butte: the north
  edge of the box. Nothing in Canyon County (OpenStreetMap is the fill
  there). Current state only, so history needs our own polling.
- **Access:** `.../FeatureServer/2/query?where=1=1&outFields=*&f=json`,
  no key; the layer's `maxRecordCount` is 2000, so one call. Capabilities
  Query, Extract, Sync. The cheapest change check is the layer's `?f=json`
  `editingInfo.dataLastEditDate`.
- **Open-data sibling:** item 25eedd01 (in
  [Boise Parks GIS](#city-of-boise-parks-gis)) adds `TrailStatus`,
  `TrlSurface`, `YearOpen`, `Width` and `CityMuni`; its count of 367
  trails wasn't re-run.
- **License and terms:** the item's `licenseInfo` is the City's
  disclaimer only ("Every effort is made to keep data accurate..."), with
  `accessInformation` "City of Boise". The City's
  [site terms](https://www.cityofboise.org/terms-of-use-and-privacy-policy/)
  cover content on the City's sites and say "You may not sell,
  redistribute, reproduce or make derivate works" (in their Software
  paragraph). They don't mention GIS or open data.
- **robots.txt:** `services1.arcgis.com/robots.txt` answers 403 "Invalid
  URL": no rules under RFC 9309, so allowed. ridgetorivers.org:
  `User-agent: *`, `Allow: /`. `gisprod.adacounty.id.gov/robots.txt`: 200
  with only comments and blank lines, no groups (allowed).
- **Updates and size:** edited by staff. `dataLastEditDate` 2026-10-06
  21:01Z, and the schema was edited Oct 6 too (the item metadata dates
  from Oct 5, 2024). Conditions are set in batches (all 238 Dry/Tacky rows
  date from Sep 11 or earlier), so expect daily changes only in the wet
  season. 271 rows: attributes under 100 KB a poll, 1–2 MB with geometry;
  48 calls a day at 30 minutes, fewer if gated on `dataLastEditDate`.
- **Use cases:** R2R's own per-trail mud and closure status, replayable;
  what's allowed on a trail today (direction, even or odd days, bikes,
  dogs, e-bikes, horses); labels for a mud and thaw forecast (sparse,
  since statuses are set in batches); trailhead cards (parking spaces,
  horse trailers, restroom and alert status); closures in the Valley Feed.
- **For:** hikers and trail runners, mountain bikers and e-bikers, dog
  owners, equestrians, families and accessibility, traffic researchers.
  **Needs:** lifecycles (CLOSED and muddy intervals), the layer system,
  the clock and full replay, a rules-by-date evaluator (new), places and
  search (trails, trailheads), the Valley Feed, the shared ArcGIS reader,
  evidence and review (conflation with OSM, USFS and BLM).
- **Risks:** `Condition` is advice, not a closure order: label it as
  R2R's. `ConditionDate` is when staff last set the status, so "updated
  N days ago" and model labels are coarse. Drop `Editor`, `created_user`
  and `last_edited_user`. The schema changed on Oct 6: store attributes as
  jsonb and alert on schema changes. The app computes the Hulls Gulch
  even/odd rule as day-of-month parity on the viewer's own clock
  (`new Date().getDate() % 2` in main.js), so the 31st and the 1st are
  both odd days. Republishing the raw table waits for a courtesy note to
  the City.
- **Verification:** re-fetched the service, layers 0 and 2, the item and
  main.js; one statistics query reproduced the 271 / 238 / 7 / 26 split
  and the Sep 28 latest CLOSED date. Small fixes: layer 4's name, the item
  title, and the dates (item metadata 2024, data and schema Oct 6, 2026).
  The Survey123 layer in the web map was deliberately left unopened.
- **Evidence:** robots.txt for
  [services1.arcgis.com](https://services1.arcgis.com/robots.txt),
  [ridgetorivers.org](https://www.ridgetorivers.org/robots.txt) and
  [gisprod.adacounty.id.gov](https://gisprod.adacounty.id.gov/robots.txt);
  [main.js](https://gisprod.adacounty.id.gov/apps/r2r/main.js);
  [FeatureServer](https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer?f=json),
  [layer 2](https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer/2?f=json),
  [layer 0](https://services1.arcgis.com/WHM6qC35aMtyAAlN/ArcGIS/rest/services/Ridge_to_Rivers_Trails_Assessment_Map_WFL1/FeatureServer/0?f=json);
  one statistics query grouped by `Condition` at `.../FeatureServer/2/query`;
  items [0fee607a](https://www.arcgis.com/sharing/rest/content/items/0fee607a47e6469f82884a924667bb5d?f=json),
  [819709ab](https://www.arcgis.com/sharing/rest/content/items/819709ab413f40778b0848bfd4bd7818?f=json) and
  [25eedd01](https://www.arcgis.com/sharing/rest/content/items/25eedd01c4e0404ea0f235d9033d2715?f=json);
  [City terms](https://www.cityofboise.org/terms-of-use-and-privacy-policy/).

### Ridge to Rivers weekly condition reports

Internal only · verified: confirmed · confidence high · effort S

- **Endpoint:** `ridgetorivers.org/umbraco/api/NewsListApi/GetNewsArticles?nodeName=conditionreports&page=1&pageSize=8`
  (JSON, no key), behind the
  [condition reports page](https://www.ridgetorivers.org/condition-reports/).
- **Contents:** free-text "Weekend Trail Report" articles. Each list item
  has five fields: `title`, `description`, `imageUrl`, `imageAltText`,
  `url`. There's no date field; the date is only in the title. Latest on
  Oct 7: the October 2, September 25, September 18 and September 11
  Weekend Trail Reports, a "Cottonwood Creek Trail Closure Update", and
  others. The page also lists the RainoutLine app ("Boise Parks and
  Recreation"), a phone line (208-231-0001 ext. 11), Facebook and
  Instagram, and the interactive map.
- **Coverage:** the Ridge to Rivers system; recent posts.
- **License and terms:** City website content; the City's
  [terms](https://www.cityofboise.org/terms-of-use-and-privacy-policy/)
  forbid redistributing or reproducing it.
- **robots.txt:** ridgetorivers.org: `User-agent: *`, `Allow: /`.
- **Updates and size:** about weekly (Fridays), plus closure posts as
  needed; a few KB a call.
- **Use cases:** a "latest trail report" link-out card beside the
  structured status; the headline (title and link) in the Valley Feed.
- **For:** hikers and trail runners, mountain bikers and e-bikers.
  **Needs:** the Valley Feed.
- **Risks:** store the title and link only, and link out. Dates have to
  be parsed from titles, which is fragile. Don't collect from RainoutLine
  or Facebook.
- **Verification:** confirmed the endpoint, its five fields (not four),
  the missing date field, and the phone line and channels on the page.
  The individual report article wasn't re-read.
- **Evidence:** [robots.txt](https://www.ridgetorivers.org/robots.txt),
  [condition reports](https://www.ridgetorivers.org/condition-reports/),
  [article list](https://www.ridgetorivers.org/umbraco/api/NewsListApi/GetNewsArticles?nodeName=conditionreports&page=1&pageSize=8),
  [City terms](https://www.cityofboise.org/terms-of-use-and-privacy-policy/).

### City of Boise Parks GIS

Use · verified: confirmed · confidence high · effort S

- **Endpoints:** trails
  `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_Parks_Trails_Open_Data/FeatureServer/0`
  (item 25eedd01); facilities `.../Boise_Parks_Facilities_Open_Data/FeatureServer/0`.
  The City's other layers turn up in an ArcGIS search for
  `orgid:WHM6qC35aMtyAAlN`.
- **Contents:** trails, with R2R's fields plus `CityMuni`, `TrailStatus`,
  `TrlSurface`, `YearOpen`, `Width` and `LCWFProt`. "Parks & Recreation
  Public and Administrative Facilities" (points): `FacilType` is Special
  Purpose, Wilderness or back-Country, Other, Public Campground, Group
  Campground or Primitive Camping; `FacilityStatus` is Open, Open_Fee,
  Open_Restricted, Closed, Decommissioned, Unknown, Planned or Proposed.
  The other layers came from the research pass's search and weren't
  re-opened: trailheads, parks and reserves, Foothills reserves and levy
  acquisitions, Dogs Off Leash Areas, Bike Air and Repair Stations, Oregon
  Trail Monuments, Treasures of the Boise Front, Open Space Monitoring
  plots and the Pathways Master Plan.
- **Coverage:** the City of Boise and its Foothills reserves; current
  state only.
- **Access:** ArcGIS FeatureServer queries, no key; `maxRecordCount` 2000.
- **License and terms:** the trails item carries the City's disclaimer
  with no grant. Some City items (the Greenbelt mile markers, below)
  explicitly allow redistribution with metadata or credit.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
  opendata.cityofboise.org: `User-agent: *`, Crawl-delay 60, disallowing
  `/sites/`, `/admin/`, `/sessions/`, `/groups/`, `/people/` and
  `/workspace/`; the REST services aren't on that host.
- **Updates and size:** varies; the trails and facilities layers were last
  edited Oct 5, 2026. Each layer is under 5 MB.
- **Use cases:** trailhead and campground points for search; off-leash
  areas for dog owners; the urban trail network beyond R2R; planned
  pathways for before-and-after work.
- **For:** hikers and trail runners, dog owners, cyclists, families and
  accessibility, neighbors. **Needs:** places and search, the layer
  system, the shared ArcGIS reader.
- **Risks:** disclaimer-only license. Skip the Survey123 layers and
  "Police Calls". Filter facilities to public ones, since the status
  domain includes Decommissioned, Planned and Proposed.
- **Verification:** re-read the trails and facilities layer metadata and
  domains and the trails item's license. Not re-run: the counts (367
  trails, 109 facilities, 96 services) and the other layers.
- **Evidence:** [services1 robots.txt](https://services1.arcgis.com/robots.txt),
  [open-data robots.txt](https://opendata.cityofboise.org/robots.txt),
  [trails layer](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_Parks_Trails_Open_Data/FeatureServer/0?f=json),
  [facilities layer](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_Parks_Facilities_Open_Data/FeatureServer/0?f=json),
  [trails item](https://www.arcgis.com/sharing/rest/content/items/25eedd01c4e0404ea0f235d9033d2715?f=json).

### Greenbelt closures, detours and mile markers

Use · verified: confirmed · confidence high · effort S

- **Endpoints:** closures
  `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer`
  (item owner jvgearhart_boise, City of Boise Parks & Recreation); mile
  markers, item 793ee45f "Boise Greenbelt Mile Markers Barber Park to Ann
  Morrison Park" (owner firegis_boise, Boise Fire GIS), for orientation and
  public safety.
- **Contents:** layer 0 `Greenbelt_Construction` (lines: `LOCATION`,
  `PROJECT`, `WORK_DESCRIPTION`, `CONSTRUCTION_SEASON`,
  `CONSTRUCTION_UPDATES`, `RIVER_MILE`, `GREENBELT_MILE`, `LATITUDE`,
  `LONGITUDE`, `STATUS`); layer 1 `Greenbelt_Detour` (`LOCATION`, `STATUS`,
  `PROJECT`, `Project_Status`). Markers every 1/10 mile. The research
  pass counted 2 closures and 1 detour (not re-run).
- **Coverage:** the Greenbelt in Boise. The checked markers item covers
  Barber Park to Ann Morrison Park only; a `GreenbeltDOTSMileMarkers`
  layer for Lucky Peak to Eagle wasn't checked ⚠️.
- **Access:** ArcGIS FeatureServer, no key.
- **License and terms:** closures carry the City's disclaimer only. The
  markers item says the data "may be redistributed" if the City's metadata
  goes with it unaltered, or with credit to the City of Boise if altered.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
- **Updates and size:** closures last edited Sep 10, 2026; the markers
  item modified Jan 2, 2026. Tiny.
- **Use cases:** closures and detours as lifecycles on the map and in the
  Valley Feed; searchable places such as "Greenbelt marker 3.4"; routing
  caveats for commuting cyclists.
- **For:** cyclists and commuters, runners, floaters, traffic
  researchers. **Needs:** lifecycles, the Valley Feed, places and search.
- **Risks:** there are no start or end date fields, only the
  `CONSTRUCTION_SEASON` text, so lifecycles come from first and last seen.
- **Verification:** fields, the last edit date and both licenses confirmed
  from the services and items. Not checked: the Lucky Peak–Eagle markers
  and the feature counts.
- **Evidence:** [robots.txt](https://services1.arcgis.com/robots.txt),
  [closures item](https://www.arcgis.com/sharing/rest/content/items/941ed66cc3b14c9abc85ac26b64694e1?f=json),
  [layer 0](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer/0?f=json),
  [layer 1](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Greenbelt_Closures_View/FeatureServer/1?f=json),
  [markers item](https://www.arcgis.com/sharing/rest/content/items/793ee45fab334a4ab40123bfc2c86cc6?f=json).

### COMPASS bike and pedestrian network

Use · verified: corrected · confidence medium · effort S

- **Endpoint:** `swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer`.
- **Contents:** layers 0 Existing Pathway, 1 Existing Bike Facility,
  2 Existing Sidewalk, 3 Permanent Counter Locations (`id`, `name`,
  `agency`, `counts`, `technology`, `pm_id`, `corridor`, `description`,
  `corridorside`, `owner`, plus `created_user` and `last_edited_user`),
  4 Pathways_Master (`f_elev`, `t_elev`, `length`, walk times, `yearadd`,
  `county`, `name`, `citytype`, `type`, `cityplan`, `surface`, `width`,
  `piclink`, `pmid` (not `pm_id`), `linearref`). The research pass's
  counts (22,996; 28; 81,195) weren't re-run.
- **Coverage:** Ada and Canyon counties.
- **Access:** ArcGIS FeatureServer, no key (Query, Extract;
  `maxRecordCount` 2000). Reachable from a normal network, as with
  COMPASS's other services.
- **License and terms:** the service's `copyrightText` and description are
  empty, so it states no license or disclaimer. Use the project's standing
  COMPASS treatment: disclaimer only, credit COMPASS.
- **robots.txt:** `swidrdc.org/robots.txt`: 404, no rules (allowed).
- **Updates and size:** unknown (perhaps yearly ⚠️). Pathways about
  10–30 MB.
- **Use cases:** the valley-wide Greenbelt and pathway network, Canyon
  County included; counter locations on the map; pathway use counts if
  COMPASS shares them.
- **For:** cyclists and commuters, runners, traffic researchers.
  **Needs:** the layer system; readings, if counts arrive.
- **Risks:** the counts live in Eco-Counter's platform: ask COMPASS (an
  owner action) rather than scraping. Drop `created_user` and
  `last_edited_user`.
- **Verification:** layers and fields confirmed. Corrected: the license
  quote the research gave ("Every effort is made...") is the City of
  Boise's and isn't on this service; the Pathways_Master key is `pmid`.
- **Evidence:** [robots.txt](https://swidrdc.org/robots.txt),
  [FeatureServer](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer?f=json),
  [layer 3](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer/3?f=json),
  [layer 4](https://swidrdc.org/arcgis/rest/services/COMPASSData/ExistingBikeAndPed/FeatureServer/4?f=json).

### Foothills Imagery 2026 tile cache

Needs owner action · verified: corrected · confidence medium · effort S

- **Endpoint:** `tiles.arcgis.com/tiles/ocXK9Gg6fvIH5GTf/arcgis/rest/services/FoothillsImagery2026/MapServer`,
  used by Ridge to Rivers' map.
- **Publisher:** item f149133c is owned by the RIDGE2RIVERS account (which
  also owns R2R's web map), and the service's author is RIDGE2RIVERS. Who
  flew the imagery is unknown.
- **Contents:** a tile cache (Map, TilesOnly, Tilemap) over the Boise
  Front, about −116.32 to −116.08 longitude and 43.56 to 43.77 latitude;
  24 levels down to 0.0187 m nominal (the real resolution is unknown). The
  description and copyright are empty. The item's note, "Updated June
  2026 to include Sweet Connie trail", suggests trails may be drawn into
  the tiles, so it may be a cartographic basemap rather than plain
  imagery ⚠️.
- **Coverage:** the Boise foothills only.
- **License and terms:** none stated on the item or the service.
- **robots.txt:** `tiles.arcgis.com/robots.txt`: 404, no rules (allowed).
- **Updates and size:** a 2026 one-off, updated June 2026; size unknown.
- **Use cases:** fresh trail-level imagery for the foothills, if Ridge to
  Rivers and the imagery's original owner allow it.
- **For:** hikers, mountain bikers. **Needs:** a base-map imagery layer.
- **Risks:** it may be COMPASS or county imagery reshared, so treat it like
  ACHD's 3-inch imagery (view on request only, [DECISIONS](../DECISIONS.md),
  Oct 6) and ask Ridge to Rivers who flew it before fetching any tiles.
  The front-end rules also forbid pointing the map's style at a
  third-party tile host.
- **Verification:** the publisher isn't unknown (RIDGE2RIVERS, item
  f149133c); robots.txt checked; the June 2026 trail note is new. The
  imagery's source and license are still unknown.
- **Evidence:** [main.js](https://gisprod.adacounty.id.gov/apps/r2r/main.js),
  [robots.txt](https://tiles.arcgis.com/robots.txt),
  [MapServer](https://tiles.arcgis.com/tiles/ocXK9Gg6fvIH5GTf/arcgis/rest/services/FoothillsImagery2026/MapServer?f=json),
  an ArcGIS search for `FoothillsImagery2026`.

## The Boise River and the float season

### Boise River hazards and access (Float the Boise)

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_River_Hazards_and_Access_-_VIEW/FeatureServer/10`
  (item owner firegis_boise, Boise Fire Department GIS, for Float the
  Boise); a separate `Swift_Water_Launch_Sites_view` service has one layer,
  "Swift Water Launch Sites".
- **Contents:** 119 points (confirmed): `Name`, `Type`, `Status`,
  `Comments`, `Descriptions`, `Marker`, `CreationDate`, `Creator`,
  `EditDate`, `Editor`. `Type`: Temporary hazard, Permanent hazard,
  Extreme hazard, Rapid, Put-in, Take-out. `Status`: Active, Remediated,
  Inactive, Potential. Values are stored as one-letter codes (T, P, E, R,
  I, O; A, R, I, P), but 14 rows hold the literal text "Remediated" and 2
  have no status.
- **Coverage:** the float stretch, Barber Park to Ann Morrison Park.
- **Access:** ArcGIS FeatureServer, no key.
- **License and terms:** the item's license and access fields are empty;
  credit Boise Fire / City of Boise.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
- **Updates and size:** seasonal; last edited Jul 18, 2026. Tiny.
- **Use cases:** a float-day map of hazards by type and status; put-ins
  and take-outs; a season replay of hazards added and remediated (using
  `CreationDate` and `EditDate`).
- **For:** floaters and paddlers, families. **Needs:** lifecycles (active
  to remediated), the layer system, the clock.
- **Risks:** safety-critical. Use the agencies' wording: the Float the
  Boise FAQ says the river is "never deemed completely safe to float".
  Normalize the mixed codes, text and nulls before building lifecycles.
  Drop `Creator` and `Editor`.
- **Verification:** the count, the domains and the last edit date
  confirmed with one statistics query. New: the stored values mix codes,
  free text and nulls.
- **Evidence:** [robots.txt](https://services1.arcgis.com/robots.txt),
  [item](https://www.arcgis.com/sharing/rest/content/items/eb0bdc42d5334ea5a69965e353e7943f?f=json),
  [layer 10](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Boise_River_Hazards_and_Access_-_VIEW/FeatureServer/10?f=json),
  one statistics query grouped by `Type` and `Status` at
  `.../FeatureServer/10/query`,
  [launch sites](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Swift_Water_Launch_Sites_view/FeatureServer?f=json),
  [Float the Boise FAQ data](https://www.arcgis.com/sharing/rest/content/items/3d651814db6b4b9dad8639528f9c3f22/data?f=json).

### Boise River E. coli results

Use · verified: corrected · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/BPR_EColi_Testing/FeatureServer/0`
  ("E. coli Testing Sites", City of Boise Parks & Recreation).
- **Contents:** `LabNumber`, `SampleDatetime` (a date-only field),
  `SampleName`, `SampleDescription`, `AnalysisDatetime`,
  `FinalResultNumeric`, `Units`, `MostRecent`. On Oct 7 it held exactly 7
  rows, all sampled Sep 28, 2026: it keeps the latest round only, not a
  history.
- **Coverage:** swimming and floating spots on the Boise River in Boise.
- **Access:** ArcGIS FeatureServer, no key.
- **License and terms:** no `copyrightText` on the layer; the item's
  license wasn't read. Treat it like the City's other layers (disclaimer
  only, credit the City).
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
- **Updates and size:** each sampling round, still running in late
  September (latest Sep 28); the layer was edited Oct 6, 2026. Tiny.
- **Use cases:** water-quality readings on the float panel and a
  time-series card; spots where dogs swim.
- **For:** floaters and paddlers, dog owners, families. **Needs:** the
  readings contract and time-series card.
- **Risks:** each round overwrites the last, so a daily poll is the only
  way to keep history. Key readings on (`SampleName`, `SampleDatetime`,
  `LabNumber`). Show the City's or DEQ's thresholds and wording, and make
  no swim or no-swim call of our own.
- **Verification:** answered the research pass's open question: no
  history is kept (all 7 rows share the Sep 28 date, in a date-only
  field). Confidence raised to high.
- **Evidence:** [robots.txt](https://services1.arcgis.com/robots.txt),
  [layer 0](https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/BPR_EColi_Testing/FeatureServer/0?f=json),
  one count, minimum and maximum query on `SampleDatetime` at
  `.../FeatureServer/0/query`.

### Barber Park floater information

Use · verified: corrected · confidence medium · effort S

- **Endpoint:** `gisprodapi.adacounty.id.gov/arcgis/rest/services/ParksAndWaterways/Barber_Park_Floater_Information/FeatureServer`
  (Ada County Parks & Waterways and Ada County IT). Its description says
  it feeds the "Barber Park Floater Dashboard".
- **Contents:** layers 1 Barber Park boundary; 2 `BarberPark_Parking`
  (`Cars_In`, `Cars_Out`, `Parking_Occupancy`, `Parking_Spots_Left`,
  `Updated_Date`, `ParkingPercentFull`); 3 `BarberPark_LabelPoints`;
  4 `BarberPark_RiverFloaters` (`FloaterCount`, `Updated_Date`). Table 5,
  "iMonnit River Sensor" (`Date`, `Battery`, `SignalStrength`,
  `Temperature`): 54,435 rows on Oct 7, from 2023-07-31 to Oct 7, 2026,
  with a minimum of −62 (a glitch) and a maximum of 79.3. The newest rows
  were 66.2 at 06:16Z and 67.1 at 05:06Z when the clock read 06:28Z, so
  `Date` looks like true UTC. OBJECTIDs (up to about 210,106 for 54k rows)
  aren't in time order, and readings come at irregular intervals (gaps of
  30 minutes to 4 hours). Whether it measures water or air is
  undocumented ⚠️.
- **Coverage:** the Barber Park put-in. The sensor since July 2023;
  parking and floaters current state only.
- **Access:** ArcGIS FeatureServer on Ada County's server, no key. The
  separate `BarberPark` folder answers 499 "Token Required": leave it
  alone. The service advertises Query, Create, Update, Delete, Uploads and
  Editing: use query only and never call an edit operation.
- **License and terms:** no license or copyright text on the service;
  credit Ada County Parks & Waterways.
- **robots.txt:** `gisprodapi.adacounty.id.gov/robots.txt`: 200, blank, no
  rules (allowed). adacounty.id.gov: `User-agent: *` disallows `/Portals/`
  and `/cgi-bin/` only.
- **Updates and size:** the sensor irregularly, roughly every 30 minutes
  with gaps; the parking and floater cadence wasn't verified ⚠️. Parking
  and floaters are one row per poll; the sensor about 1.5 MB a year.
- **Use cases:** live "spots left at Barber Park" on the float panel; a
  recreation demand signal for traffic research on Warm Springs Ave and
  Eckert Rd; a temperature series once its meaning is confirmed.
- **For:** floaters and paddlers, traffic researchers, commuters.
  **Needs:** the readings contract, the clock and replay, the shared
  ArcGIS reader.
- **Risks:** (1) The public edit capabilities weren't tested and mustn't
  be; either way values could be altered, so treat them as unverified. The
  owner may want to give Ada County a courtesy heads-up. (2) Key sensor
  rows on `Date`, not OBJECTID: `orderByFields=OBJECTID DESC` doesn't
  return the latest reading, and the server's `max(Date)` statistic said
  00:26Z while a 06:16Z row existed, so don't trust server-side date
  statistics. (3) The counts are aggregates, which is fine. (4) Poll in
  season only. With no license stated, publish displays and aggregates
  only until the county answers.
- **Verification:** layers, fields, the token folder and robots.txt
  confirmed. Corrected: the row count, the latest reading, the irregular
  intervals, OBJECTIDs out of time order, and the public edit
  capabilities, which the research pass missed.
- **Evidence:** robots.txt for
  [gisprodapi.adacounty.id.gov](https://gisprodapi.adacounty.id.gov/robots.txt)
  and [adacounty.id.gov](https://adacounty.id.gov/robots.txt);
  [services list](https://gisprodapi.adacounty.id.gov/arcgis/rest/services?f=json),
  [BarberPark folder](https://gisprodapi.adacounty.id.gov/arcgis/rest/services/BarberPark?f=json),
  [FeatureServer](https://gisprodapi.adacounty.id.gov/arcgis/rest/services/ParksAndWaterways/Barber_Park_Floater_Information/FeatureServer?f=json),
  [table 5](https://gisprodapi.adacounty.id.gov/arcgis/rest/services/ParksAndWaterways/Barber_Park_Floater_Information/FeatureServer/5?f=json);
  two queries on table 5 (statistics, and the top 4 rows by OBJECTID).

### Float the Boise season facts

Use · verified: confirmed · confidence high · effort S

- **Page:** the [Floater FAQ](https://www.floattheboise.org/pages/floater-faq)
  on floattheboise.org, an ArcGIS Hub site run by Ada County Parks &
  Waterways, Boise Parks & Recreation and Boise Fire (FAQ item owner
  csallabanks_boise).
- **Contents (confirmed from the FAQ item's text):** flows in a typical
  season run between 500 and 1,500 cfs, usually reached around late June.
  The 2026 season opens June 20 and closes on Labor Day, September 7,
  2026. Drinking alcohol on the river is illegal. Barber Park's floater
  amenities end on Labor Day. Parking is $7 a vehicle from 9:30 a.m. to
  7:30 p.m., free before 9:30 a.m. The river is "never deemed completely
  safe to float". No gauge is named; the Glenwood Bridge "about 1,500 cfs
  to open" figure comes from news reports only ⚠️.
- **Coverage:** one season at a time.
- **Access:** Hub pages render with JavaScript; the text is in item
  3d651814's `/data`. Copy the facts into config by hand each season.
- **License and terms:** agency web content: store facts, not text.
- **robots.txt:** floattheboise.org: `User-agent: *`, Crawl-delay 60,
  disallowing `/sites/`, `/admin/`, `/sessions/`, `/groups/`, `/people/`,
  `/workspace/`. www.arcgis.com: `User-agent: *` and a Sitemap line, no
  Disallow.
- **Updates and size:** yearly (the FAQ item was modified Jun 18, 2026);
  manual config, no data.
- **Use cases:** a season band on the time slider; the float panel's range
  (500–1,500 cfs, labelled as the agencies' typical range).
- **For:** floaters and paddlers. **Needs:** the clock (season bands).
- **Risks:** the range is guidance, not a go or no-go: show the agencies'
  announced status.
- **Verification:** every fact confirmed word for word from the item's
  data. The cityofboise.org news release wasn't re-read.
- **Evidence:** robots.txt for
  [floattheboise.org](https://www.floattheboise.org/robots.txt) and
  [www.arcgis.com](https://www.arcgis.com/robots.txt);
  [FAQ item](https://www.arcgis.com/sharing/rest/content/items/3d651814db6b4b9dad8639528f9c3f22?f=json),
  [its data](https://www.arcgis.com/sharing/rest/content/items/3d651814db6b4b9dad8639528f9c3f22/data?f=json).

### NOAA NWPS: Boise River at Glenwood Bridge

Use · verified: corrected · confidence high · effort S

- **Endpoint:** `api.water.noaa.gov/nwps/v1/gauges/BIGI1` (NOAA's National
  Water Prediction Service; NWRFC forecasts, USGS observations). Spec at
  `/nwps/v1/docs/swagger.json` (contact nws.nwc.ops@noaa.gov); paths
  `/gauges`, `/gauges/{id}`, `/ratings`, `/riverflow`, `/stageflow`,
  `/stageflow/{product}`, `/monitor`, `/products/stageflow/{id}/{pedts}`,
  `/reaches/{reachId}`, `/reaches/{reachId}/streamflow`.
- **Contents (confirmed):** BIGI1 is USGS 13206000, "Boise River at Boise
  (Glenwood Bridge)", at 43.6606, −116.2792 in Ada County; WFO BOI, RFC
  NWRFC, reach 23398831. Historic crests are included. Flood categories:

  | Category | Stage | Flow |
  |---|---|---|
  | Action | 9.7 ft | 6,500 cfs |
  | Minor | 10.1 ft | 7,000 cfs |
  | Moderate | 12.9 ft | 11,000 cfs |
  | Major | none given | 15,000 cfs |

  On Oct 7: observed 0.387 kcfs and 3.6 ft at 03:45Z; forecast 0.413 kcfs
  at 12:00Z. Its `dataAttribution` reads "Observations courtesy of U.S.
  Geological Survey".
- **Coverage:** any NWPS gauge; the others in the ring are still to be
  listed.
- **Access:** REST JSON, no key.
- **License and terms:** US government work; the spec states no terms.
  Credit NOAA/NWS, and USGS for observations.
- **robots.txt:** `api.water.noaa.gov`, `water.noaa.gov` and
  `www.nwrfc.noaa.gov`: 404, no rules (allowed).
- **Updates and size:** observations are 15-minute values but arrive in
  delayed batches: at 06:27Z the newest was from 03:45Z (about 2.7 hours
  late). Forecasts are issued routinely year-round. A few KB a call.
- **Use cases:** flow now and over the next days against the 500–1,500 cfs
  range; a 3D river ribbon animated by flow; flood-stage context for the
  hazards plugin; a replayable flow series.
- **For:** floaters and paddlers, anglers, fire and hazard watchers,
  traffic researchers. **Needs:** the readings contract and time-series
  card, the 3D engine (river ribbon).
- **Risks:** no published service level. Since observations lag by hours,
  a 15-minute poll mostly re-reads the same values: poll every 30–60
  minutes, or dedupe on `validTime`.
- **Verification:** everything confirmed except the cadence, corrected to
  observations arriving about 2–3 hours late.
- **Evidence:** robots.txt for
  [api.water.noaa.gov](https://api.water.noaa.gov/robots.txt),
  [water.noaa.gov](https://water.noaa.gov/robots.txt) and
  [www.nwrfc.noaa.gov](https://www.nwrfc.noaa.gov/robots.txt);
  [BIGI1](https://api.water.noaa.gov/nwps/v1/gauges/BIGI1),
  [spec](https://api.water.noaa.gov/nwps/v1/docs/swagger.json).

### USGS Water Data APIs and legacy NWIS

Needs owner action · verified: corrected · confidence high · effort S

- **Endpoints:** the new OGC API at `api.waterdata.usgs.gov/ogcapi/v1/collections/...`
  (for example `/collections/continuous`); the legacy NWIS Water Services
  at `waterservices.usgs.gov`.
- **Contents:** continuous and daily values, monitoring locations,
  time-series metadata, statistics, samples.
- **Coverage:** national, with decades of history.
- **Access:** an API key is optional; the docs say it allows more requests
  an hour before rate limiting (429s). The legacy service will be
  "permanently shut down on February 22nd, 2027", with intentional outages
  from January 2027.
- **License and terms:** public domain (USGS data).
- **robots.txt:** `api.waterdata.usgs.gov`, `User-agent: *`: disallows
  `/ogcapi/*/collections/*/items*`, `/samples-data/*`, `/squid/*` and
  `/statistics/*`, so every data endpoint is blocked (the docs are
  allowed). `waterservices.usgs.gov`: 404, no rules. `waterdata.usgs.gov`:
  an empty `Disallow:`, so everything is allowed.
- **Updates and size:** 15-minute data, delivered hourly to daily; small
  per call.
- **Use cases:** long flow history ("is this a normal June?"); water
  temperature where measured; a backfill for float-season replay.
- **For:** floaters and paddlers, anglers, water watchers. **Needs:** the
  readings contract.
- **Risks:** under our robots.txt rule the new API's data paths are
  off-limits, key or no key. Ask USGS whether API clients are meant to be
  covered. Use NWPS for current flow, and the legacy service only for an
  owner-approved one-off backfill before January 2027.
- **Verification:** the robots.txt conflict and the shutdown date
  confirmed. Corrected: no key is needed (it only raises rate limits). The
  research pass's claim that anonymous use gets IP blocks wasn't
  verified ⚠️.
- **Evidence:** [API robots.txt](https://api.waterdata.usgs.gov/robots.txt),
  [API](https://api.waterdata.usgs.gov/),
  [keys](https://api.waterdata.usgs.gov/docs/ogcapi/keys/),
  [Water Services](https://waterservices.usgs.gov/),
  [Water Services robots.txt](https://waterservices.usgs.gov/robots.txt),
  [waterdata robots.txt](https://waterdata.usgs.gov/robots.txt).

### IDFG fishing and boating access sites

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `gisportal-idfg.idaho.gov/hosting/rest/services/Access/IDFG_Fishing_and_Boating_Access_Sites_Public/FeatureServer/0`
  (copyright "IDFG, IFWIS").
- **Contents:** `region`, `status`, `site_name`, `public_info_notes`,
  `county`, `dd_x`, `dd_y`, `camp`, `rest`, `ramp`, `dock`, `ada_fish`,
  `fishing_boating`, `ID`: sites managed or co-managed by IDFG. The
  research pass counted 48 in the ring (not re-run).
- **Coverage:** statewide (Idaho Transverse Mercator, EPSG 8826).
- **Access:** ArcGIS FeatureServer, no key; `maxRecordCount` 2000,
  pagination not advertised. The service advertises Query, Update,
  Uploads, Editing and Extract: query only.
- **License and terms:** an IDFG disclaimer ("considered a best
  representation only"), per the research pass; not re-read ⚠️. Credit
  IDFG.
- **robots.txt:** `gisportal-idfg.idaho.gov`: 404, no rules (allowed).
  data-idfggis.opendata.arcgis.com: Crawl-delay 60, disallowing `/sites/`,
  `/admin/` and similar.
- **Updates and size:** irregular; tiny.
- **Use cases:** river and reservoir access (Boise River, Lucky Peak,
  Snake River); put-ins for floaters and anglers beyond the Barber Park
  stretch.
- **For:** anglers, floaters and paddlers, hunters. **Needs:** places and
  search.
- **Risks:** it overlaps the wildlife and lands themes (see
  [wildlife](wildlife.md)), so one plugin should own it. Never call an
  edit operation; treat values as the agency's assertion.
- **Verification:** fields, robots.txt and the endpoint confirmed. New:
  the advertised edit capabilities. Not re-checked: the count and the
  disclaimer's wording.
- **Evidence:** robots.txt for
  [gisportal-idfg.idaho.gov](https://gisportal-idfg.idaho.gov/robots.txt)
  and [the IDFG hub](https://data-idfggis.opendata.arcgis.com/robots.txt);
  [layer 0](https://gisportal-idfg.idaho.gov/hosting/rest/services/Access/IDFG_Fishing_and_Boating_Access_Sites_Public/FeatureServer/0?f=json),
  [FeatureServer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Access/IDFG_Fishing_and_Boating_Access_Sites_Public/FeatureServer?f=json).

## Forest, BLM and state routes and rules

### USFS National Forest System trails

Use · verified: confirmed · confidence high · effort M

- **Endpoint:** `apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer/0`,
  "Trans_Trail_NFS_Publish" (Forest Service Enterprise Data Warehouse).
  Downloads on the [EDW clearinghouse](https://data.fs.usda.gov/geodata/edw/datasets.php).
- **Contents (confirmed):** `trail_no`, `trail_name`, `trail_type`,
  `trail_class`, `trail_surface`, `surface_firmness`,
  `typical_trail_grade`, `typical_tread_width`,
  `typical_tread_cross_slope`, `accessibility_status`,
  `national_trail_designation`, `special_mgmt_area`, `mvum_symbol`,
  `allowed_terra_use` and `allowed_snow_use`; managed, accepted,
  discouraged and restricted flags for hikers, pack and saddle, bicycles,
  motorcycles, ATVs, 4WD, snowmobiles, snowshoes, cross-country skis and
  motorized and non-motorized watercraft; and the same four for e-bike
  classes 1, 2 and 3.
- **Coverage:** national; 426 segments intersect the ring (confirmed),
  mostly in the Boise National Forest (the ring's north-east).
- **Access:** ArcGIS MapServer query, no key; `maxRecordCount` 2000;
  pagination supported (server 11.5).
- **License and terms:** `copyrightText` "USDA Forest Service"; no license
  stated. Treated as public domain as a federal work ⚠️ (our inference).
  The service says data readiness "varies between Forests".
- **robots.txt:** `apps.fs.usda.gov`: 403 "Access forbidden!", no rules
  (allowed). `data.fs.usda.gov`: 404 (allowed).
- **Updates and size:** refresh cadence unknown ⚠️ (stated on neither the
  service nor the clearinghouse). About 1–3 MB for the ring.
- **Use cases:** forest trails with allowed uses; elevation profiles and
  3D drapes; conflation with OpenStreetMap and IDPR.
- **For:** hikers and backpackers, mountain bikers, equestrians, OHV
  riders, skiers and snowmobilers. **Needs:** named areas (the ring),
  evidence and review (conflation), the 3D engine, the shared ArcGIS
  reader.
- **Risks:** the allowed-use fields aren't the legal motor-vehicle
  designation (MVUM is). Our built terrain covers the ring only at
  10–30 m, so drapes and profiles there need a terrain build (correction 1
  below).
- **Verification:** fields, the 426 count, `maxRecordCount` and paging
  confirmed. The research pass's "weekly to monthly" refresh couldn't be
  confirmed and is now "unknown".
- **Evidence:** robots.txt for
  [apps.fs.usda.gov](https://apps.fs.usda.gov/robots.txt) and
  [data.fs.usda.gov](https://data.fs.usda.gov/robots.txt);
  [MapServer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer?f=json),
  [layer 0](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSPublish_01/MapServer/0?f=json);
  one count query on the ring at `.../MapServer/0/query`;
  [clearinghouse](https://data.fs.usda.gov/geodata/edw/datasets.php).

### USFS Motor Vehicle Use Map (MVUM)

Use · verified: confirmed · confidence high · effort M

- **Endpoint:** `apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_02/MapServer`:
  query layers 1 (Roads) and 2 (Trails); layers 4 and 5 repeat them with
  Visitor Map symbols.
- **Contents:** the motor-vehicle designations under 36 CFR 212.56.
  Fields: `symbol`, `seasonal`, and for each vehicle class a flag and a
  `*_datesopen` field (passenger vehicle, high-clearance vehicle, truck,
  bus, motorhome, 4WD over 50 in, 2WD over 50 in, tracked OHV over and
  under 50 in, other OHV over and under 50 in, ATV, motorcycle, other
  wheeled OHV); `e_bike_class1`–`3` with durations; `operationalmaintlevel`
  and `surfacetype` (roads), `trailclass` (trails), `districtname`,
  `forestname`. The Trails layer has motorized trails only (non-motorized
  trails aren't included). The research pass counted 512 roads and 178
  trails in the ring (not re-run).
- **Coverage:** national-forest system routes in the ring.
- **Access:** ArcGIS MapServer query, no key; `maxRecordCount` 2000;
  pagination supported.
- **License and terms:** federal; treated as public domain ⚠️. Credit
  USDA Forest Service.
- **robots.txt:** `apps.fs.usda.gov`: 403, no rules (allowed).
- **Updates and size:** a yearly MVUM cycle plus edits (not stated on the
  service ⚠️). About 2–5 MB for the ring.
- **Use cases:** "open to my vehicle on this date" from the `*_datesopen`
  fields, replayable; e-bike legality on forest routes; seasonal gate
  dates for reaching campsites.
- **For:** OHV and motorcycle riders, campers, e-bikers, hunters.
  **Needs:** the rules-by-date evaluator (new), the clock, the layer
  system.
- **Risks:** the date fields are free text and need a tested parser. Query
  layers 1 and 2, not the duplicates. Forest orders override MVUM, so
  check against the R4 orders.
- **Verification:** layers, fields and the CFR description confirmed.
  Counts not re-run.
- **Evidence:** [robots.txt](https://apps.fs.usda.gov/robots.txt),
  [MapServer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_02/MapServer?f=json),
  [layer 1](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_02/MapServer/1?f=json),
  [layer 2](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_02/MapServer/2?f=json).

### USFS Region 4 forest orders

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/gGHDlz6USftL5Pau/arcgis/rest/services/R04_Forest_Orders_PUBLIC_VIEW/FeatureServer/0`
  ("ForestOrder" polygons, Intermountain Region); dashboard 5298fa47
  ("R4_Closure_Map_Dashboard"), web map ed5bd978.
- **Contents:** `forestname`, `unitid`, `ordername`, `ordernum`,
  `ordertype`, `description`, `exemption`, `cfr`, `temporaltype`,
  `signeddate`, `startdate`, `enddate`, `rescinddate`, `approvaltype`,
  `hyperlink`, `acres`, `rev_date`, `data_source`, `accuracy`,
  `forest_order`, `pub_date`, `statement`.
- **In the ring on Oct 7:** 7 polygons, but only 5 orders:

  | Order | Name | Type | Area | In force |
  |---|---|---|---|---|
  | 0402-05-101 | Designated Camping Order | Recreation Restriction | 9,120 ac | Jun 12, 2025 – Jun 12, 2030 |
  | 0402-03-134 | Grimes Creek Closure | Safety | 213 ac | Mar 26, 2026 – Mar 26, 2027 |
  | 0402-01-119 | Claremont Fire | Fire Closure – Stage 3 | 617 ac | Jul 8 – Dec 31, 2026 |
  | 0402-01-122 | Deer Point | Safety Closure (timber harvest for the Deer Point Stewardship Project, per the Boise NF alerts page) | 2 polygons: 361 and 201 ac | Aug 17 – Nov 30, 2026 |
  | 0402-03-140 | Crooked Fire | Fire Closure – Stage 3 | 2 polygons: 10,450 and 1,069 ac | Sep 19 – Dec 31, 2026 |

  The forest-wide occupancy order 0402-00-62 (Jul 31, 2022; no more than
  14 days in any 30-day period) is on the
  [alerts page](https://www.fs.usda.gov/r04/boise/alerts) but has no
  polygon in the ring.
- **Coverage:** Region 4's forests; current orders.
- **Access:** ArcGIS FeatureServer, no key; `maxRecordCount` 2000.
- **License and terms:** the dashboard item carries the Forest Service
  disclaimer that the data "are not legal documents"; no license. Credit
  USDA Forest Service.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
  `www.fs.usda.gov/r04/boise/alerts` is allowed.
- **Updates and size:** when orders are signed or rescinded; last edited
  Oct 3, 2026. Small.
- **Use cases:** closures as lifecycles with real start and end dates, in
  the Valley Feed and on replay; a "can I camp here?" overlay; a check on
  Ridge to Rivers' CLOSED trails.
- **For:** campers, hikers, OHV riders, fire and hazard watchers, hunters.
  **Needs:** lifecycles, the Valley Feed, the clock and replay.
- **Risks:** key lifecycles on `ordernum`, not on polygons, since one
  order can have several. Forest-wide orders (occupancy) may not be drawn,
  so carry them as rules. Link the signed order (`hyperlink`) as the
  authority.
- **Verification:** all seven polygons and their dates confirmed; the
  alerts page confirms the occupancy order and Deer Point's purpose.
  Clarified: 7 polygons are 5 orders, and Deer Point's type is "Safety
  Closure".
- **Evidence:** [robots.txt](https://services1.arcgis.com/robots.txt),
  [layer 0](https://services1.arcgis.com/gGHDlz6USftL5Pau/arcgis/rest/services/R04_Forest_Orders_PUBLIC_VIEW/FeatureServer/0?f=json);
  one attributes-only query on the ring at `.../FeatureServer/0/query`;
  [dashboard item](https://www.arcgis.com/sharing/rest/content/items/5298fa472cbf40b2b54a8e73a3a00ebe?f=json),
  [Boise NF alerts](https://www.fs.usda.gov/r04/boise/alerts).

### BLM Ground Transportation Linear Features (GTLF)

Use · verified: confirmed · confidence high · effort M

- **Endpoint:** `gis.blm.gov/arcgis/rest/services/transportation/BLM_Natl_GTLF_Public_Display/MapServer`
  (national); BLM Idaho's GTLF is also published as a FeatureServer and a
  MapServer under `gis.blm.gov/idarcgis/rest/services/transportation`. Hub
  item f94999eb, "BLM Natl GTLF Public Motorized Roads" (modified Sep 22,
  2026).
- **Contents:** layers 0–7 (confirmed): Roads Managed for Public Motorized
  Use; Roads for Limited Public Motorized Use; Trails for Public Motorized
  Use; Trails for Limited Public Motorized Use; Trails for Public
  Non-Motorized Use; Trails for Public Non-Mechanized Use; Trails Not
  Assessed for Public; Trails Managed for Public. Fields include
  `PLAN_OHV_ROUTE_DSGNTN`, `OHV_ROUTE_DSGNTN_LIM` (with an explanation),
  `PLAN_ALLOW_MODE_TRNSPRT`, `PLAN_ACCESS_RSTRCT`,
  `PLAN_SEASON_RSTRCT_CODE`, `OBSRVE_SRFCE_TYPE`, `ROUTE_PRMRY_NM`,
  `ROUTE_SPCL_DSGNTN_TYPE`, `NEPA_DOC_NUM`, `TMA_ID`, `COORD_SRC_TYPE`,
  `ACCURACY_FT`.
- **Coverage:** BLM land in the ring (Boise Front parcels, the Owyhee
  Front, the Birds of Prey NCA, OHV areas). Ring counts not re-run.
- **Access:** ArcGIS MapServer query, no key; `maxRecordCount` 2000;
  pagination supported.
- **License and terms:** "provided by BLM 'as is' and may contain errors
  or omissions" (item f94999eb). Federal; treated as public domain ⚠️.
  Credit BLM.
- **robots.txt:** `gis.blm.gov`: 404, no rules (allowed).
- **Updates and size:** periodic (the hub item was modified Sep 22, 2026).
  About 5–15 MB for the ring.
- **Use cases:** motorized and non-motorized BLM routes; access to
  dispersed camping; conflation with OpenStreetMap tracks.
- **For:** OHV and motorcycle riders, campers, hunters, mountain bikers.
  **Needs:** evidence and review (conflation), named areas, the shared
  ArcGIS reader, the rules-by-date evaluator (`PLAN_SEASON_RSTRCT_CODE`).
- **Risks:** `PLAN_SEASON_RSTRCT_CODE` holds some seasonal restrictions,
  but district orders can add others: link to the BLM office. Position
  accuracy varies (`ACCURACY_FT`).
- **Verification:** layers, the license quote and robots.txt confirmed.
  Added the season-restriction and accuracy fields. Counts not re-run.
- **Evidence:** [robots.txt](https://gis.blm.gov/robots.txt),
  [MapServer](https://gis.blm.gov/arcgis/rest/services/transportation/BLM_Natl_GTLF_Public_Display/MapServer?f=json),
  [layer 0](https://gis.blm.gov/arcgis/rest/services/transportation/BLM_Natl_GTLF_Public_Display/MapServer/0?f=json),
  [BLM Idaho transportation folder](https://gis.blm.gov/idarcgis/rest/services/transportation?f=json),
  [hub item](https://www.arcgis.com/sharing/rest/content/items/f94999eb674d4085be0c86729fe4a151?f=json).

### IDPR Idaho Recreation Trails

Use · verified: confirmed · confidence high · effort M

- **Endpoint:** `services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer`,
  the data behind trails.idaho.gov (item owner aernst_idpr; credits IDPR,
  USFS and BLM). The public app is an
  [ArcGIS Experience](https://experience.arcgis.com/experience/97a42a2a73c944ba918042faf518c689).
- **Contents:** layers 127 Emergency Route Closures (`ID`, `NAME`,
  `MILES`, `JURISDICTION`, `OFFICE`, `PHONE`, `Date_Order_Signed`,
  `Date_Order_Expires`, `DateStart`, `DateEnd`, `Narrative`, `URL_1`/`2`,
  `EditDate`); 130 Points of Interest (`SITE_NAME`, `SITE_TYPE`,
  `Narrative`, URLs); 128 Idaho Routes (`System_Type`, `ID`, `NAME`,
  `Miles`, `SYMBOL`, `JURISDICTION`, `OFFICE`, `PHONE`, `Narrative`,
  `URL_1`/`2`, `Season_NonMotor`, `Season_Auto`, `Season_Jeep`,
  `Season_UTV`, `Season_ATV`, `Season_Motorcycle`, `EditDate`,
  `Unique_ID`, `Major_Division_Name`); 123 Area Restrictions (name and
  type, order and start, end and expiry dates, `Acres`); and boundary
  layers 124–126, 129, 131 and 132. The description says Idaho Routes holds
  over 57,000 route segments statewide and that consumers must filter by
  `SYMBOL`.
- **Coverage:** statewide; ring counts not re-run. Changes appear "in real
  time" in the app and the service (item description).
- **Access:** ArcGIS FeatureServer, no key. The service reports
  `maxRecordCount` 1000 but layer 128 reports 2000 with pagination, so
  read each layer's own value.
- **License and terms:** "Not for commercial use and may not be used in
  3rd party apps without source attribution", plus liability text and a
  contact (maps@idpr.idaho.gov) for schema questions. The Experience item
  adds that content from agencies other than IDPR and IDL is
  "representative" and authoritative only at its source. Fine for our
  non-commercial use with visible credit.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
  `trails.idaho.gov/robots.txt` redirects (301) to an HTML page on
  parksandrecreation.idaho.gov, so after following the redirect, as
  RFC 9309 says to, there are no rules. parksandrecreation.idaho.gov:
  `User-agent: *` with an empty `Disallow:` (allowed).
- **Updates and size:** live edits; layers edited Oct 5–6, 2026. About
  10–20 MB of geometry for the ring; closures tiny.
- **Use cases:** an open-by-vehicle-type-by-date layer; emergency closures
  as lifecycles with dates; OHV areas and trailheads in search.
- **For:** OHV and motorcycle riders, Jeep and UTV drivers, hikers,
  hunters, campers. **Needs:** the rules-by-date evaluator (new),
  lifecycles, evidence and review (overlaps with MVUM and GTLF), named
  areas, the Valley Feed.
- **Risks:** it repackages MVUM and GTLF ("representative", per IDPR), so
  prefer the agency's own source where both exist. No editor-name fields,
  only `EditDate`. Filtering by `SYMBOL` is required.
- **Verification:** layer IDs, fields, the license text and edit dates
  confirmed. Noted the service and layer `maxRecordCount` differ. Ring
  counts not re-run.
- **Evidence:** robots.txt for
  [trails.idaho.gov](https://trails.idaho.gov/robots.txt) and
  [parksandrecreation.idaho.gov](https://parksandrecreation.idaho.gov/robots.txt);
  [FeatureServer](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer?f=json),
  layers [128](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer/128?f=json),
  [127](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer/127?f=json),
  [123](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer/123?f=json),
  [130](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Recreation_Trails/FeatureServer/130?f=json);
  items [5a08280a](https://www.arcgis.com/sharing/rest/content/items/5a08280a853b41b69115a3fc0abbd2bc?f=json)
  and [97a42a2a](https://www.arcgis.com/sharing/rest/content/items/97a42a2a73c944ba918042faf518c689?f=json).

### IDPR winter and water layers

Use · verified: corrected · confidence high · effort S

- **Endpoints:** Park N' Ski (view only)
  `services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Park_N__Ski_replace_view/FeatureServer`:
  layers 7 `Parking_final_replace`, 26 `ParkN_SkiTrails_replace`,
  25 `StateParkWinterTrails_final_replace`. Separate services:
  `Idaho_City_Yurts_view`; the Idaho Centennial Trail (Official Route view,
  mile markers, resupply points, points of interest, alternates); and
  several life-jacket services ("Life Jacket Loaner Stations Public View",
  a `_OLD` copy, "IDPR Life Jacket Stations (Point layer)",
  `Life_Jacket_Stations`).
- **Coverage:** statewide. In the ring: the Idaho City and Mores Creek
  Summit Park N' Ski areas and the Idaho City yurts. The official Idaho
  Centennial Trail has **0 segments in the ring**, so it's outside our
  area. The research pass's "17 areas" and Idaho City area names weren't
  re-run.
- **Access:** ArcGIS FeatureServer, no key.
- **License and terms:** the Park N' Ski item has IDPR's liability
  disclaimer only; credit IDPR.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
- **Updates and size:** seasonal (the Park N' Ski item was modified
  Dec 16, 2025). Small.
- **Use cases:** a winter trail layer; yurt locations; life-jacket
  stations on the float and boating panel.
- **For:** cross-country skiers and snowshoers, yurt campers, floaters and
  boaters. **Needs:** the layer system, places and search.
- **Risks:** use the current life-jacket service ("Public View"), not the
  `_OLD` copies. Grooming reports are posted only on Facebook: link out.
  Drop the Centennial Trail from the backpacker idea, or mark it out of
  area.
- **Verification:** layers and services confirmed. Corrected: the
  Centennial Trail doesn't enter the ring, and the life-jacket data exists
  in several old and new services.
- **Evidence:** [Park N' Ski item](https://www.arcgis.com/sharing/rest/content/items/be6752532ab44bcf878099667e09cd8b?f=json),
  [Park N' Ski FeatureServer](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Park_N__Ski_replace_view/FeatureServer?f=json),
  an ArcGIS search of IDPR's organization for yurt, Centennial, life-jacket
  and Park N' Ski items,
  [Centennial Trail service](https://services1.arcgis.com/CNPdEkvnGl65jCX8/arcgis/rest/services/Idaho_Centennial_Trail_%28Official_Route%29_view/FeatureServer?f=json),
  and one count query on the ring at `.../FeatureServer/52/query` (0).

## Campgrounds and reservations

### USFS recreation sites and Recreation Opportunities

Use · verified: corrected · confidence high · effort S

- **Endpoints:** `apps.fs.usda.gov/arcx/rest/services/EDW/EDW_InfraRecreationSites_01/MapServer/0`
  ("Recreation Sites INFRA") and `.../EDW/EDW_RecreationOpportunities_01/MapServer/0`.
  The clearinghouse's "Recreation Sites Public Information" was updated
  Oct 4, 2026 (9 MB geodatabase, 11 MB shapefile).
- **Contents:** 72 INFRA sites in the ring (confirmed): 22 campgrounds,
  19 trailheads, 5 group campgrounds, 5 recreation residences, 4 boating
  sites, 4 info sites or fee stations, 3 lookouts or cabins, 2
  interpretive sites, 2 picnic sites, and 1 each of camping area, day-use
  area, horse camp, hotel/lodge/resort, alpine ski area and snowpark. Only
  1 has an `nrrs_id`. Fields include `total_capacity`, `fee_charged`,
  `open_season`, `current_conditions`, `restrictions`,
  `water_availability`, `restroom_availability`; dated alerts and closures
  (`alerts_description`, `alerts_start_date`, `alerts_end_date`,
  `closure_reason`, `unit_closure_description`,
  `unit_closure_start_date`, `unit_closure_end_date`); opening and season
  dates; campsite attributes (`fire_pit`, `tent_pad`,
  `max_vehicle_length`, `www_reservable`); and `last_update`. Recreation
  Opportunities: `recareaname`, `markeractivity`, `open_season_start` and
  `_end`, `openstatus`, `feedescription`, `reservation_info`,
  `restrictions`, `accessibility`, `recareaurl`, `infra_cn`; the research
  pass's count of 54 wasn't re-run.
- **Coverage:** the Boise National Forest and a corner of the Payette
  inside the ring.
- **Access:** ArcGIS MapServer query, no key; `maxRecordCount` 2000.
- **License and terms:** Recreation Opportunities' `copyrightText` is
  "USDA Forest Service"; Region 4 items carry the disclaimer that the data
  are "not legal documents". Treated as public domain ⚠️.
- **robots.txt:** `apps.fs.usda.gov`: 403, no rules (allowed).
  www.fs.usda.gov, `User-agent: *`: disallows `/admin`, `/comment/reply`,
  `/contact`, `/logout`, `/node`, `/search`, `/user/register`,
  `/user/password` and `/user/login`, and their `?q=` forms; forest pages such as
  `/r04/boise/...` are allowed.
- **Updates and size:** unknown ⚠️; each row carries `last_update`. Under
  1 MB for the ring.
- **Use cases:** campground and trailhead points with capacity and season;
  the search index; links to Recreation.gov by `nrrs_id`; a season-aware
  "probably open" display, with dated alerts and unit closures as
  lifecycles.
- **For:** campers, hikers and backpackers, equestrians, skiers.
  **Needs:** places and search, the layer system, named areas, lifecycles
  (alerts and unit closures).
- **Risks:** leave out recreation residences: privately owned cabins on
  forest land under special-use permits, not public sites; keep them out
  of search and the map. Seasons are free text and `openstatus` is mostly
  empty, so never show them as live status. Alert and closure dates are
  the agency's and may be stale.
- **Verification:** the count of 72 confirmed. Corrected: the subtype list
  was incomplete (recreation residences, info sites, interpretive, picnic,
  day-use, camping area, lodge and ski area were missing), and the
  research pass missed the dated alert and closure fields.
- **Evidence:** [INFRA layer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_InfraRecreationSites_01/MapServer/0?f=json);
  one query grouped by `site_subtype` on the ring at `.../MapServer/0/query`;
  [Recreation Opportunities layer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_RecreationOpportunities_01/MapServer/0?f=json),
  [www.fs.usda.gov robots.txt](https://www.fs.usda.gov/robots.txt),
  [clearinghouse](https://data.fs.usda.gov/geodata/edw/datasets.php).

### BLM recreation sites

Use · verified: corrected · confidence high · effort S

- **Endpoints:** BLM Idaho's site points,
  `gis.blm.gov/idarcgis/rest/services/recreation/BLM_ID_Recreation_Site_Point/FeatureServer/0`;
  the national "BLM Natl Recreation Sites and Facilities" MapServer,
  `gis.blm.gov/arcgis/rest/services/recreation/BLM_Natl_Recreation_Sites_Facilities/MapServer`.
- **Contents:** Idaho points: `FET_TYPE`, `FET_SUBTYPE`, `FET_NAME`,
  `ADM_UNIT_CD`, `LAT`, `LONG`, `WEB_DISPLAY`, `PHOTO_THUMB`,
  `DESCRIPTION`, `UNIT_NAME`, `WEB_LINK`, `COORD_SRC_TYPE`. National
  service: layers 0 Facilities, 1 Sites, and 2–8 RIDB Camping, Boating,
  Day Use, Info Centers, OHV Designated Areas, Trailhead and Facilities
  Camping; its description says it is retrieved from ridb.recreation.gov
  and updated nightly. The research pass's count of 58 sites in the ring
  wasn't re-run.
- **Coverage:** the BLM Boise District in the ring.
- **Access:** ArcGIS FeatureServer (Query, Extract) and MapServer, no key;
  `maxRecordCount` 2000.
- **License and terms:** `copyrightText` names the BLM Idaho State Office
  and Headquarters; BLM's "as is" disclaimer; federal, credit BLM. RIDB is
  listed as CC BY 4.0 on data.gov ⚠️ (see [RIDB](#ridb-export-and-api)).
- **robots.txt:** `gis.blm.gov`: 404, no rules (allowed).
- **Updates and size:** the national service nightly from RIDB; the Idaho
  points irregularly. Tiny.
- **Use cases:** OHV staging areas; primitive campsites; climbing and
  boating access; RIDB's BLM content without the RIDB API or the 248 MB
  export.
- **For:** OHV riders, campers, climbers, floaters and paddlers.
  **Needs:** places and search.
- **Risks:** the coordinate source is often unknown (`COORD_SRC_TYPE`; the
  research pass's "50 of 58 unknown" wasn't re-run), so mark positions as
  approximate.
- **Verification:** fields and layers confirmed. Corrected: the national
  service updates nightly from RIDB, not irregularly, which makes it a
  robots-clean route to RIDB's BLM content. Site counts not re-run.
- **Evidence:** [robots.txt](https://gis.blm.gov/robots.txt),
  [Idaho points](https://gis.blm.gov/idarcgis/rest/services/recreation/BLM_ID_Recreation_Site_Point/FeatureServer/0?f=json),
  [national service](https://gis.blm.gov/arcgis/rest/services/recreation/BLM_Natl_Recreation_Sites_Facilities/MapServer?f=json).

### RIDB export and API

Needs owner action · verified: confirmed · confidence high · effort M

- **Endpoints:** the bulk export
  `ridb.recreation.gov/downloads/RIDBFullExport_V1_CSV.zip`, listed on the
  [download page](https://ridb.recreation.gov/download); the API at
  `ridb.recreation.gov/api/v1` needs an account and key (not re-read). The
  data.gov record names the Forest Service as publisher.
- **Contents:** federal recreation areas, facilities, campsites and their
  attributes, permit entrances, activities, media and links, for USFS,
  BLM, USACE, BOR, NPS and FWS. Historical reservation and visitation
  files are also listed, per the research pass ⚠️ (the download page is a
  JavaScript app verification couldn't read).
- **Coverage:** national; filter to the ring locally.
- **Access:** a HEAD request on Oct 7 gave 200, `application/zip`,
  247,775,845 bytes, last modified Oct 6, 2026 18:46:56 GMT; no key.
- **License and terms:** the data.gov catalog record lists
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with a
  dataset date of Aug 25, 2022 ⚠️. The API Access Agreement wasn't
  re-read.
- **robots.txt:** ridb.recreation.gov, `User-agent: *`: disallows `/api`
  and `/api/*`, Crawl-delay 10. `/downloads/` is allowed (honor the 10 s
  delay); the API is off-limits.
- **Updates and size:** the export looks refreshed about daily (one
  observation: Oct 6, 2026). 248 MB per download; the ring is a tiny
  slice.
- **Use cases:** reservable federal campgrounds and campsites with
  Recreation.gov links; Lucky Peak's Corps of Engineers sites; aggregated
  historical reservations to explain weekend traffic, if ever approved.
- **For:** campers, traffic researchers. **Needs:** places and search;
  the ingest framework (a large download honoring Crawl-delay).
- **Risks:** the owner decides between a periodic 248 MB download and
  relying on the USFS and BLM services. BLM's national service is already
  a nightly RIDB copy, so the export mainly adds USACE (Lucky Peak) and
  BOR. Never use the API while robots.txt disallows it. The research
  pass's claim that the reservation files include customer ZIP codes is
  unverified ⚠️; if they're ever used, aggregates only.
- **Verification:** robots.txt, the export's size and date, and the
  CC BY 4.0 catalog listing confirmed. The API agreement and the
  historical-reservation fields couldn't be re-read (JavaScript pages).
- **Evidence:** [robots.txt](https://ridb.recreation.gov/robots.txt),
  [download page](https://ridb.recreation.gov/download), a HEAD on the
  export, [data.gov record](https://catalog.data.gov/dataset/recreation-information-database-ridb).

### Recreation.gov availability (avoid)

Avoid · verified: confirmed · confidence high

- **Site:** [recreation.gov](https://www.recreation.gov/), run for the
  federal partners (the research pass named Booz Allen Hamilton as the
  operator, from secondary sources ⚠️).
- **Contents:** live availability by campsite and date, served only from
  the site's internal `/api` endpoints; reservable federal sites.
- **License and terms:** the Terms of Service page is a JavaScript app and
  wasn't read.
- **robots.txt:** `User-agent: *`: disallows `/account/*`, `/cart`,
  `/cart/*`, `/api` and `/api/*`; Crawl-delay 10. Availability is
  disallowed.
- **Use cases:** "check availability" link-out buttons only.
- **For:** campers.
- **Risks:** any polling would break robots.txt.
- **Verification:** robots.txt confirmed word for word.
- **Evidence:** [robots.txt](https://www.recreation.gov/robots.txt),
  [rules and reservation policies](https://www.recreation.gov/rules-reservation-policies).

### Idaho State Parks reservations (avoid)

Avoid · verified: corrected · confidence high

- **Site:** [getoutside.idaho.gov](https://getoutside.idaho.gov/) (IDPR's
  reservation system; the research pass's vendor name wasn't verified ⚠️).
- **Contents:** state-park camping, cabin and yurt reservations and
  availability; a web app only.
- **License and terms:** not checked, because of the bot check below.
- **robots.txt:** `/robots.txt` returns HTTP 405 with a "Human
  Verification" (WAF) page instead of a file. Our parser would read a 4xx
  as "no rules", but this is an active bot challenge, and getting past bot
  detection is prohibited. So no automated access, whatever the status
  code.
- **Use cases:** link-out only.
- **For:** campers and yurt campers.
- **Risks:** bot detection; never try to get past it.
- **Verification:** reasoning corrected: the response is a 405 carrying a
  bot challenge, not a disallow. "Avoid" stands. IDPR's press release
  wasn't re-read.
- **Evidence:** [robots.txt](https://getoutside.idaho.gov/robots.txt).

## Shared and context layers

### OpenStreetMap paths and recreation tags

Use (needs a loader change) · verified: corrected · confidence high · effort M

- **Source:** Geofabrik's
  [Idaho extract](https://download.geofabrik.de/north-america/us/idaho.html),
  downloaded by hand by the owner, plus Oregon's extract for the ring's
  Oregon slice.
- **What's loaded today:** checked in
  [osm_valley.py](../../plugins/roads/ingest/sources/osm_valley.py):
  `keep_way` keeps motorway to tertiary (and their links) plus any highway
  way tagged `lanes`, `lanes:forward`, `lanes:backward` or `turn:lanes*`,
  cut to the valley box, and `raw.record` keeps all tags of the kept ways.
  So footways, paths, tracks, bridleways and cycleways (the Greenbelt) are
  **not loaded**. On-street bike tags (`cycleway=*`, `bicycle=*`) on major
  and lane-tagged roads are in `raw.record`; on residential streets without
  lane tags and on off-street paths they aren't.
  [Chapter 16](../16-ideas-and-personas.md) once listed OpenStreetMap
  trails and bike tags as "loaded Oct 7"; its wording now matches the
  loader.
- **Contents wanted:** paths, tracks and recreation tags: `highway=path`,
  `footway`, `track`, `bridleway`, `cycleway` and `steps`; hiking, mountain
  bike and bicycle route relations; and points such as campsites,
  trailheads, toilets, drinking water, shelters, viewpoints, peaks,
  guideposts, protected areas and canoe put-ins.
- **Coverage:** the Idaho extract covers Idaho's part of the ring. The
  Oregon slice is more than "west of about −117.03": south of about 43.8°
  the border is the −117.027 meridian, but north of there the Snake River
  forms it, so Oregon reaches east to about −116.9 (Nyssa, Ontario, Annex,
  Farewell Bend). That slice needs Geofabrik's Oregon extract.
- **Access:** a second osmium pass over the archived extract
  (`$TVT_ARCHIVE/osm/`, the last two kept, per the loader's docstring):
  extract to the ring box, then a tags filter for paths, route relations
  and recreation points. No new Idaho download.
- **License and terms:** ODbL ("© OpenStreetMap contributors"); keep it in
  its own tables.
- **robots.txt:** Geofabrik serves different robots.txt files by
  User-Agent. A browser-like User-Agent gets 200 with `User-agent: *`
  disallowing `*.osm.pbf`, `*.osm.bz2`, `*.osc.gz`, `*.shp.zip`,
  `state.txt`, `*updates*` and `*.md5`; our honest User-Agent gets a 301
  to `/robots.txt/` and then a 404. The intent is clearly to disallow
  automated downloads, so hand downloads continue (decided Oct 6,
  [DECISIONS](../DECISIONS.md)). overpass-api.de disallows `/api/` and
  `/munin/`; taginfo.geofabrik.de disallows `/api`, `/tags`, `/keys`,
  `/relations` and more.
- **Updates and size:** weekly, with the owner's hand download. Size
  unknown until measured on the server ⚠️; likely tens of thousands of
  path ways in the ring.
- **Use cases:** the trail network where agencies don't map it (Eagle,
  Avimor, Canyon County, BLM land); campsite, water and toilet points;
  geometry detail for conflation; the Greenbelt route relation.
- **For:** hikers, mountain bikers, cyclists, campers, equestrians.
  **Needs:** a regular OpenStreetMap load (paths, points, the ring box, the
  Oregon extract), named areas (the ring), evidence and review
  (conflation).
- **Risks:** informal and social trails, some on closed or private land or
  under seasonal wildlife closures: show the agency's status first and
  flag OSM-only trails. Never use OSM's GPS traces. Geofabrik treating
  non-browser User-Agents differently is one more reason not to script
  downloads.
- **Verification:** the trails part of the chapter 16 correction
  confirmed; the bike-tags part was overstated. The Oregon slice's extent
  is corrected, and Geofabrik's User-Agent-dependent robots.txt is new
  (read with our User-Agent and with a browser's).
- **Evidence:** [osm_valley.py](../../plugins/roads/ingest/sources/osm_valley.py)
  (docstring; `keep_way`, `MAJOR`, `LANE_KEYS`, `BOX`),
  [chapter 16](../16-ideas-and-personas.md),
  [DECISIONS](../DECISIONS.md) (Oct 6, OpenStreetMap);
  robots.txt for [Geofabrik](https://download.geofabrik.de/robots.txt),
  [Overpass](https://overpass-api.de/robots.txt) and
  [taginfo](https://taginfo.geofabrik.de/robots.txt).

### NRCS SNOTEL

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** the AWDB REST API,
  `wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:ID:SNTL`
  (`/stations`, `/data`), USDA NRCS.
- **Contents:** 87 active Idaho SNOTEL stations, 4 of them inside the
  ring:

  | Station | Elevation | Position | Since |
  |---|---|---|---|
  | 978 Bogus Basin | 6,370 ft | 43.764, −116.097 | 1999 |
  | 423 Cozy Cove | 5,410 ft | 44.288, −115.655 (the ring's north-east corner) | 1978 |
  | 637 Mores Creek Summit | 6,090 ft | — | 1978 |
  | 2029 Reynolds Creek | 5,590 ft | 43.289, −116.843 | 1999 |

  Their element lists (snow water, depth, precipitation, temperature)
  weren't re-requested.
- **Coverage:** the ring, with decades of history. Oregon SNOTEL in the
  ring's Oregon slice wasn't checked.
- **Access:** REST JSON, no key.
- **License and terms:** federal (USDA NRCS); public domain ⚠️ (our
  inference). Credit NRCS.
- **robots.txt:** `wcc.sc.egov.usda.gov`: 404, no rules (allowed).
- **Updates and size:** hourly; tiny.
- **Use cases:** snow depth near trailheads and Park N' Ski areas; inputs
  to a mud and thaw model; a float-season outlook from snowpack.
- **For:** cross-country skiers and snowshoers, hikers, floaters, weather
  watchers. **Needs:** the readings contract and time-series card.
- **Risks:** shared with weather and water: one ingestor.
- **Verification:** the four stations, their elevations and positions
  confirmed with one stations call.
- **Evidence:** [robots.txt](https://wcc.sc.egov.usda.gov/robots.txt),
  [stations call](https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:ID:SNTL&returnForecastPointMetadata=false&returnReservoirMetadata=false&returnStationElements=false&activeOnly=true).

### Oregon National Historic Trail

Use · verified: confirmed · confidence high · effort S

- **Endpoint:** `services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/OREG_NHT/FeatureServer`
  (National Park Service, National Trails Office; item beea1da3, owner
  ntirres_nps).
- **Contents:** layer 0 `OREG_100k_line`, a 1:100,000-scale line
  described as the congressionally designated alignment. The item says it
  is "not a fully developed hiking trail" and not to cross private land
  without permission.
- **Coverage:** the whole trail (−122.8 to −94.4), passing through the
  ring.
- **Access:** ArcGIS FeatureServer, no key; `maxRecordCount` 1000;
  Query, Extract, Sync.
- **License and terms:** the NPS item text as above. A BLM Oregon/Washington
  copy (item 2a3d7508) says the data "are considered public domain".
  Credit NPS.
- **robots.txt:** `services1.arcgis.com`: 403, no rules (allowed).
- **Updates and size:** rarely; under 1 MB.
- **Use cases:** a history overlay with the historic-aerials year slider;
  interpretive hikes (Bonneville Point, the Oregon Trail Reserve).
- **For:** history buffs, hikers. **Needs:** the layer system.
- **Risks:** it isn't a walkable trail. At 1:100,000 positions can be off
  by tens of metres, so don't draw it as a precise path in 3D or snap it to
  roads.
- **Verification:** the item, owner, wording and layer confirmed. New: the
  line is at 1:100,000.
- **Evidence:** [FeatureServer](https://services1.arcgis.com/fBc8EJBxQRMcHlei/arcgis/rest/services/OREG_NHT/FeatureServer?f=json),
  an ArcGIS search for "Oregon National Historic Trail" feature services.

### IDL publicly accessible endowment lands

Use · verified: corrected · confidence medium · effort S

- **Endpoint:** `services2.arcgis.com/1cvrwLhZRFh3okEF/ArcGIS/rest/services/IDL_Public_Access/FeatureServer/0`
  ("PubliclyAccessibleLands", Idaho Department of Lands).
- **Contents:** polygons with `GISACRES`, `Access`, `created_user` and
  `last_edited_user`. The description says these lands were identified as
  reachable by public road or by adjoining another accessible state or
  federal parcel. The research pass's count of 668 in the ring wasn't
  re-run.
- **Coverage:** statewide.
- **Access:** ArcGIS FeatureServer, no key (Query only; `maxRecordCount`
  2000).
- **License and terms:** the disclaimer says the dataset "does not imply
  or grant permission to cross private land"; reference only, locations
  approximate. `copyrightText` "Idaho Department of Lands"; credit IDL.
- **robots.txt:** `services2.arcgis.com`: 403 "Invalid URL", no rules
  (allowed). www.idl.idaho.gov: `User-agent: *` with an empty `Disallow:`
  (allowed).
- **Updates and size:** stale: last edited Mar 27, 2024. A few MB.
- **Use cases:** which state endowment land can be reached by public
  access (the `lands` plugin owns it; `trails` reads it).
- **For:** campers, hunters, hikers. **Needs:** the `lands` plugin, named
  areas.
- **Risks:** it shows access, not permission to camp: don't use it as a
  "dispersed camping allowed" layer. IDL's camping rules are still an open
  question. The data is from 2024. Drop the user-name fields.
- **Verification:** robots.txt checked. Corrected: the use case is
  narrowed to access only (the layer says nothing about camping), and the
  2024 edit date added.
- **Evidence:** robots.txt for [IDL](https://www.idl.idaho.gov/robots.txt)
  and [services2.arcgis.com](https://services2.arcgis.com/robots.txt);
  [layer 0](https://services2.arcgis.com/1cvrwLhZRFh3okEF/ArcGIS/rest/services/IDL_Public_Access/FeatureServer/0?f=json).

## Not used

### Commercial and social trail platforms (avoid)

Avoid · verified: corrected · confidence high

- **Platforms:** Strava, Trailforks, AllTrails, onX (MTB Project, Hiking
  Project), Gaia, RainoutLine, and IDPR's Park N' Ski grooming posts on
  Facebook.
- **Contents:** user-contributed trails, conditions, ratings and activity
  heatmaps. RainoutLine relays Boise Parks' status notices; IDPR posts
  grooming only on Facebook.
- **License and terms:** proprietary. Trailforks' terms page returned 403
  (unread) ⚠️. Strava is off-limits by project rule.
- **robots.txt:** Trailforks, `User-agent: *`: Crawl-delay 1 and a long
  disallow list, not just `/region/*/planner`: `/*/gpx`, `/*/kml`,
  `/*/rss`, `/*/*/3dmap`, `/*/*/activity`, `/*/*/ridelogs`, `/*/*/stats`,
  `/profile/`, `/user/` and others; a separate ClaudeBot group sets
  Crawl-delay 1. AllTrails: ClaudeBot, Claude-User, Claude-SearchBot,
  GPTBot and others get `Disallow: /` (home pages allowed); `*` disallows
  `/api/`, `/api-v4/`, `/api-v5/`, `/*?lat=`, `/members/`,
  `/explore/map/`. RainoutLine: `*` disallows `/home/`, `/admin/`,
  `/subscribe/`, `/sign_up/step_2`.
- **Use cases:** none: agency data plus OpenStreetMap cover the same
  ground.
- **Risks:** activity heatmaps track people, and the terms forbid storing.
  Not needed.
- **Verification:** Trailforks' robots.txt was misdescribed (its `*`
  group disallows many paths, GPX and KML exports included). AllTrails and
  RainoutLine confirmed. Confidence raised, since the verdict doesn't
  depend on the unread terms.
- **Evidence:** robots.txt for
  [Trailforks](https://www.trailforks.com/robots.txt),
  [AllTrails](https://www.alltrails.com/robots.txt) and
  [RainoutLine](https://www.rainoutline.com/robots.txt);
  [Trailforks terms](https://www.trailforks.com/about/terms/) (403).

## Ideas by persona

From the research pass, adjusted where verification changed a fact (noted
in each). None is approved. "Correction n" refers to the list under
[What verification changed](#what-verification-changed-in-the-design).

### Hikers and trail runners

- **Trail status layer (official).** Every Ridge to Rivers trail drawn in
  one of R2R's seven `Condition` states: dry or tacky; frozen or snow;
  frozen early then muddy; muddy further out; muddy, do not use; CLOSED;
  not evaluated. Each state has a color, a dash pattern and an icon, never
  red and green alone. The trail's card shows R2R's note and "set 3 days
  ago" from `ConditionDate` (when staff set it, which isn't when the trail
  changed; correction 11). Because we poll and version it, the time slider
  can replay a wet season: the foothills going muddy after a storm and
  drying out trail by trail. *Sources:* Ridge to Rivers trails. *Needs:*
  lifecycles, the clock and full replay, the layer system.
- **What's allowed here today** (also for mountain bikers). Clicking a
  trail answers what's legal on the date the clock shows: direction of
  travel (animated arrows), the Lower Hulls Gulch even/odd-day downhill
  bike rule, bike-only and pedestrian-only trails, dogs (off-leash,
  on-leash, none), horses and e-bikes (allowed, permit only, no). The
  research pass's examples (counter-clockwise on Around the Mountain and
  Hawkins, clockwise on Polecat, north to south on Harrow, bike-only
  Bucktail, pedestrian-only Two Point) weren't re-checked ⚠️. The even/odd
  rule must follow R2R's app: day-of-month parity on the America/Boise
  date, so the 31st and the 1st are both odd (correction 3). Replay a past
  date and the rules change with it. *Sources:* Ridge to Rivers trails,
  Boise Parks GIS. *Needs:* the rules-by-date evaluator (new), the clock.
- **Thaw clock and shade finder** (the owner's sky and gardening
  interests). For each trail segment, sun hours by date and time, so it
  can estimate when a frozen trail thaws, which is what R2R's "frozen
  early then muddy" state asks walkers to know; in summer it ranks the
  shadiest loop for an evening run. The research pass expected
  north-facing Hulls Gulch to stay frozen longer than south-facing Table
  Rock ⚠️ (not yet modelled). Verification changed the method (correction
  2): a horizon profile per sample point, computed once from the 1 m DEM
  with far-field terrain from the 10 m DEM, so any sun position is a
  lookup; tree shade from a canopy height model built from the lidar point
  cloud (NAIP's near-infrared shows where trees are, not how tall), with
  deciduous canopy changing by season. Outside the valley the terrain is
  only 10–30 m (correction 1). Shown as an estimate beside the official
  status. *Sources:* Ridge to Rivers trails, OpenStreetMap paths, SNOTEL.
  *Needs:* the 3D engine (terrain sampling), the sky plugin (sun
  position), the land-cover plugin, the clock.
- **Mud forecast (research model).** Record a full wet season of R2R
  condition changes, then learn when trails go muddy and dry from radar
  precipitation, temperature, freeze-thaw cycles, soil, aspect, sun hours
  and R2R's `AllWeather` flag. The map shows "likely muddy by tomorrow" as
  a hatched estimate with its confidence, always beside R2R's status and
  never replacing it. Labels are weaker than first assumed: statuses are
  set in batches, so grading against R2R's next update measures staff
  cadence as much as mud. Pair the labels with the weekly Friday reports
  and treat them as interval-censored (correction 11). *Sources:* Ridge to
  Rivers trails and reports, SNOTEL. *Needs:* readings, the weather plugin
  (radar, temperature), evidence and review.
- **3D trail fly-along and elevation profile** (also for families). Pick
  any trail, from R2R, the Forest Service, BLM or OpenStreetMap, and get
  total climb, steepest pitch, the shade along it at a chosen time, and a
  camera flight along the line in our own WebGL scene. Filter for
  family-friendly, handbike or "Accessible" trails (R2R's and the Forest
  Service's accessibility, surface, grade and width fields). Profiles come
  from the 1 m COGs on the server, not the map's terrain tiles, which are
  quantized and about 3.5 m at best; in most of the ring only 10–30 m
  terrain exists until a ring terrain build is approved (correction 1).
  *Sources:* Ridge to Rivers trails, USFS trails, BLM GTLF, OpenStreetMap
  paths. *Needs:* the 3D engine, evidence and review (one trail from many
  sources), places and search.

### Mountain bikers and e-bikers

- **E-bike legality across agencies.** One layer answers "can I ride my
  class 1 here?": R2R's `Ebike` field (allowed, permit only, no), MVUM's
  e-bike classes with their durations, and BLM's and IDPR's motorized
  designations. Where the agencies disagree or a trail has no data, it
  says so ("no data, check with the manager"). *Sources:* Ridge to Rivers
  trails, MVUM, BLM GTLF, IDPR Idaho Recreation Trails. *Needs:* the
  rules-by-date evaluator (new), evidence and review.

### OHV, motorcycle and UTV riders

- **Open to my vehicle on this date.** Pick a vehicle class (motorcycle,
  ATV, UTV over 50 in, Jeep, car) and a date. Routes light up from MVUM's
  `*_datesopen` fields and IDPR's `Season_*` fields (free text, through a
  tested parser; anything unparseable reads "see manager"). IDPR's
  emergency closures and area restrictions and the Forest Service's fire
  closures cut across them with their real start and end dates. OHV
  staging areas are in search; the research pass named Little Gem, Clay
  Peak, Hemingway Butte and Wilson Creek ⚠️ (BLM's site list wasn't
  re-counted). *Sources:* MVUM, IDPR Idaho Recreation Trails, R4 forest
  orders, BLM recreation sites. *Needs:* the rules-by-date evaluator
  (new), lifecycles, the clock, named areas (the ring).

### Campers

- **Where can I sleep tonight.** Campgrounds from the Forest Service
  (capacity, fee, season; recreation residences left out, correction 10),
  BLM's primitive sites, the City's campground facilities, the RIDB export
  if approved (reservable ones link to Recreation.gov, never scraped) and
  OpenStreetMap campsites. Underneath, a "dispersed camping allowed?"
  shading by land manager carries each manager's stay limit: the Boise NF's
  14 days in any 30 (order 0402-00-62, confirmed); BLM's 14 in 28, within
  150 ft of roads and 200 ft from water, per the research pass ⚠️ (not
  checked against BLM's rules). State endowment land shows as "check with
  IDL": IDL's public-access layer shows access, not camping, and IDL's
  stay limit wasn't found (correction 10). Private land shows as no. On
  top: the designated-camping order 0402-05-101 (9,120 acres; the research
  pass places it near Lowman ⚠️) and the active closures (Crooked and
  Claremont fires, Deer Point, Grimes Creek), then fire restrictions (the
  hazards plugin) and winter road conditions on the access road (511,
  already recorded, shown only in the owner's internal view, since 511
  data isn't republished). A stay-limit calculator turns "arrive Friday"
  into "leave by". *Sources:* USFS recreation sites, R4 forest orders, BLM
  recreation sites, IDL public access, RIDB, OpenStreetMap paths, Boise
  Parks GIS. *Needs:* the `lands` plugin, lifecycles, the rules-by-date
  evaluator (new), places and search, named areas (the ring).

### Floaters and paddlers

- **Float-day panel.** Glenwood Bridge flow now and NWRFC's forecast,
  against the agencies' typical 500–1,500 cfs range, with the season band
  (June 20 – September 7, 2026) on the time bar. Also: Boise Fire's
  hazards by type and status (extreme, permanent, temporary, remediated),
  put-ins and take-outs, the City's latest E. coli round at 7 sites (our
  daily poll is the only history, correction 5), Barber Park's spots left
  and floater count (live in season), the Barber Park sensor's
  temperature (water or air still to be confirmed), life-jacket loaner
  stations and IDFG access sites. The river is drawn in 3D as a ribbon
  whose speed scales with flow. Wording comes from the agencies (the river
  is "never deemed completely safe to float"), never "safe", and the panel
  makes no "floatable" call of its own. NWPS observations arrive 2–3 hours
  late, so the panel shows their time (correction 6). *Sources:* NWPS
  Glenwood Bridge, Boise River hazards, E. coli results, Barber Park,
  Float the Boise facts, IDPR life-jacket stations, IDFG access sites.
  *Needs:* readings and the time-series card, the 3D engine (river
  ribbon), the clock (season bands), the layer system.

### Traffic researchers

- **Recreation as a traffic generator** (the project's core question).
  Line up Barber Park's parking occupancy and floater counts, the
  float-season start date and Glenwood flow against traffic on Warm
  Springs Ave, Eckert Rd and Parkcenter (cameras, buses, counts where we
  have them). The season opening is a natural experiment. The same goes
  for trailhead demand (R2R's parking capacity; mud and closure days) on
  Bogus Basin Rd and Hill Rd, and for weekend camping on SH-21 and SH-55
  from aggregated RIDB reservations, only if the owner approves them
  (whether they carry customer ZIP codes is unverified ⚠️). The output is
  a chart of weekend peaks explained by recreation. *Sources:* Barber
  Park, NWPS Glenwood Bridge, Ridge to Rivers trails, RIDB. *Needs:*
  readings, full replay, the flow plugin.

### Greenbelt cyclists, commuters and runners

- **Greenbelt today.** City closures and detours as lifecycles on the map
  and in the Valley Feed ("Greenbelt closed at river mile X, detour
  via..."), from first and last seen, since the layer has no dates. The
  1/10-mile markers are searchable ("marker 3.4"), for orientation and to
  share an exact spot; only the Barber Park–Ann Morrison Park markers were
  checked. COMPASS's pathway network carries the Greenbelt on into the
  rest of Ada and Canyon counties. Pathway counter locations are on the
  map, with counts if COMPASS shares them. Bike air and repair stations
  too (layer not re-opened). *Sources:* Greenbelt closures and markers,
  COMPASS bike and pedestrian network, Boise Parks GIS. *Needs:*
  lifecycles, the Valley Feed, places and search.

### Cross-country skiers, snowshoers and yurt campers

- **Winter in the high country.** Park N' Ski trails and parking (the
  Idaho City areas), the Idaho City yurts, and snow depth and snow water at
  Bogus Basin, Mores Creek Summit and Cozy Cove as time-series cards. To
  answer "can I get there": 511's winter road conditions (already
  recorded; internal view only) and our archived ITD road-weather camera
  views on SH-21 near Mores Creek Summit (we record every ITD view
  statewide; which station covers the summit wasn't checked ⚠️). R2R's
  frozen or snow-covered trails cover the Bogus Basin area. Grooming stays
  a link to IDPR's posts: no Facebook collection. *Sources:* IDPR winter
  layers, SNOTEL, Ridge to Rivers trails. *Needs:* readings, the cameras
  plugin (existing archive), the conditions plugin (511 winter roads).

### The owner's god's-eye view

- **One closures feed for the outdoors.** One lifecycle stream merges
  R2R's CLOSED trails, Greenbelt closures, Forest Service orders (keyed on
  order number, with real start and end dates), the Forest Service
  recreation sites' dated alerts and unit closures (correction 4), IDPR's
  emergency closures and area restrictions, and Boise Fire's river hazards.
  They sit beside work zones (WZDx, which may be republished) and, in the
  owner's internal view, 511 events, with "what was closed on July 4?"
  through replay. *Sources:* Ridge to Rivers trails, Greenbelt closures,
  R4 forest orders, USFS recreation sites, IDPR Idaho Recreation Trails,
  Boise River hazards. *Needs:* lifecycles, the Valley Feed, full replay.
- **My own hikes and rides** (private). The owner's own GPS tracks go in
  the private `home` plugin (never Strava). They're compared with the
  conflated trail network to find mapping errors worth fixing in
  OpenStreetMap, and replayed in 3D with that day's weather and trail
  status. Ends are trimmed and tracks never published (the volunteer-GPS
  rules). *Sources:* OpenStreetMap paths, Ridge to Rivers trails.
  *Needs:* the tracks contract, the `home` plugin (private), the 3D engine.

### Dog owners

- **Dog map.** Off-leash areas (the City's layer, not re-opened), each
  trail's dog rule (controlled off-leash, on-leash, not allowed, plus R2R's
  `DogComment`), mutt-mitt stations (R2R's amenities), and E. coli results
  at river spots where dogs swim, filtered to "off-leash and dry today".
  *Sources:* Ridge to Rivers trails, Boise Parks GIS, E. coli results.
  *Needs:* the layer system, the rules-by-date evaluator (new).

### Trailhead-goers

- **Trailhead cards.** Parking spaces and surface, horse-trailer parking,
  restroom and amenity alerts (R2R's amenity `Status`), the trails leaving
  the trailhead with their current condition, and the nearest bus stop
  with its next departure (the transit plugin), all searchable by name.
  *Sources:* Ridge to Rivers trails, USFS recreation sites, BLM recreation
  sites. *Needs:* places and search, the transit plugin.

### Anglers and hunters

- **Access points and rules.** IDFG's fishing and boating access sites
  (the research pass counted 48 in the ring; not re-run) with flow from
  the nearest gauge. Hunting units, Access Yes! land and restrictions come
  from the `lands` plugin (see [wildlife](wildlife.md)). Seasonal wildlife
  closures on the Boise Front appear as dated rules; the research pass
  found them as Boise River WMA trails in R2R's data ⚠️ (not re-checked).
  *Sources:* IDFG access sites, NWPS Glenwood Bridge, Ridge to Rivers
  trails. *Needs:* the `lands` plugin, readings, the rules-by-date
  evaluator (new).

### History buffs

- **Walk the Oregon Trail.** The congressionally designated Oregon NHT
  line, Boise's Oregon Trail monuments (a City layer, not re-opened),
  Bonneville Point and the Oregon Trail Reserve trails, drawn over the
  historic aerials and topo maps on the year slider. A 3D fly-along of the
  wagon route down to the Boise River shows today's subdivisions beside
  it. The NHT line is at 1:100,000, so it isn't drawn as a precise path in
  3D or snapped to roads. *Sources:* Oregon NHT, Boise
  Parks GIS, BLM recreation sites, Ridge to Rivers trails. *Needs:* the
  history plugin (year slider), the 3D engine.

### Backpackers

- **Beyond the valley.** Forest Service trails in the Boise NF with
  surface, grade and allowed uses, Forest Service fire closures cutting
  routes, and snowpack at nearby SNOTEL sites to judge when high trails
  melt out. A route planner over the conflated network (agency first, OSM
  to fill) gives distance and climb. The research pass included the Idaho
  Centennial Trail with its mile markers and resupply points, but it has
  0 segments in the ring: drop it or mark it out of area (correction 10).
  Climb in the ring rests on 10–30 m terrain until a ring build
  (correction 1). *Sources:* USFS trails, R4 forest orders, SNOTEL,
  OpenStreetMap paths. *Needs:* evidence and review (conflation), routing
  on a trail graph (new), named areas (the ring).

## Design notes

The research pass's proposal, with verification's changes folded in where
they apply. The full list of changes follows in the next section. None of
it is decided.

### Where this lives

- **`trails`** (public) holds:
  - trails from five sources: Ridge to Rivers and the City, USFS trails,
    MVUM, BLM GTLF, IDPR Idaho Routes;
  - OpenStreetMap paths, read from the same archived Idaho extract the
    roads loader uses;
  - trailheads, amenities and campgrounds (USFS INFRA and Recreation
    Opportunities, BLM, the City's facilities, RIDB if approved,
    OpenStreetMap);
  - the rules: directions, even/odd days, dogs, e-bikes, vehicle seasons,
    stay limits;
  - closures: R2R's CLOSED trails, the Greenbelt, R4 forest orders, the
    Forest Service sites' dated alerts and closures, IDPR's emergency
    closures and area restrictions.
- **`water`** holds the float season: NWPS flow and forecast, Barber Park,
  E. coli, Boise Fire's hazards, season bands. It shares SNOTEL with
  weather (one ingestor). This matches ch. 15 §15.7's `water` plugin.
- **`trails` depends on `lands`** for manager shading and dispersed-camping
  eligibility (PAD-US, IDL), and reads `hazards` (fire restrictions) and
  `conditions` (511 winter roads) without owning them.
- Both plugins are public. Raw tables with no license (City of Boise, Ada
  County's Barber Park) stay displays and aggregates until a courtesy note
  is answered. RIDB waits on the owner's download decision.

### Core pieces this theme needs

Most are already planned in [ch. 15 §15.1](../15-plugins.md#151-whats-core):

- **Lifecycles:** R2R condition intervals per trail (CLOSED is also a
  closure); Greenbelt closures from first and last seen, since there are no
  dates; forest orders keyed on `ordernum` (several polygons can be one
  order) and IDPR closures, with real start, end and rescind dates; the
  Forest Service sites' alerts and unit closures; river hazards from active
  to remediated, after normalizing their mixed codes (correction 4).
- **Readings:** river flow and stage, Barber Park temperature, parking
  occupancy and floater count, E. coli, SNOTEL.
- **Places and search:** trail names, trailheads, campgrounds, Greenbelt
  markers, access sites.
- **Named areas:** the ring (−117.30, 42.90, −115.60, 44.30); the Boise NF.
- **Evidence and review:** one "trail" entity built from several sources,
  matched by buffer and bearing like the roads segment matcher, with a
  review table for conflicts (for example, OSM says `bicycle=no` while R2R
  says multi-use).
- **3D engine:** trails draped on terrain, profiles, the river ribbon (with
  the terrain limits in correction 1).
- **A new small core piece, a rules-by-date evaluator.** These rules share
  one shape, "given a date, time and mode, is X allowed on Y?": R2R's
  directions and even/odd days (Hulls Gulch), MVUM's `*_datesopen` by
  vehicle class, IDPR's `Season_*` fields, the float season, stay limits.
  One pure function per rule type, fed by the clock, so replay and "what
  about next Saturday?" come for free. It needs a tested parser for
  free-text date ranges ("06/01-10/31", "Mid May – End of September"), and
  anything it can't parse becomes "see manager", never a guess. Parity
  rules use the America/Boise date (correction 3). It qualifies as core
  under ch. 15's rule, since trails, water and lands all need it
  (correction 12).

### OpenStreetMap needs a loader change

Today's `osm_valley` keeps only motorway to tertiary and lane-tagged ways,
and only in the valley box, so no paths are in the database. Proposal:

- a second osmium pass over the same archived extract, writing to separate
  ODbL tables (`trails.osm_path`, `trails.osm_poi`), keeping:
  - `highway=path`, `footway`, `track`, `bridleway`, `cycleway`, `steps`;
  - hiking, mountain bike and bicycle route relations;
  - campsites, trailheads, toilets, drinking water, shelters, viewpoints,
    peaks, guideposts, protected areas and canoe put-ins;
- the ring box, which needs Geofabrik's Oregon extract for the Oregon slice
  (reaching east to about −116.9 north of Nyssa, correction 8): one more
  file in the owner's weekly hand download;
- no new Idaho download;
- tags kept verbatim in `raw.record`, as for roads.

### Polling budget

All ArcGIS or REST JSON, with our honest User-Agent and robots.txt
checked; figures as corrected (correction 6):

| Source | Cadence |
|---|---|
| R2R conditions | Every 30 min, attributes only, gated on `dataLastEditDate` (about 48 checks a day, under 100 KB each); geometry weekly |
| Greenbelt closures, forest orders, IDPR closures and area restrictions | Hourly to every 6 h |
| NWPS BIGI1 | Every 30–60 min, or dedupe on `validTime` (observations arrive 2–3 h late); later more gauges, such as below Diversion Dam and on the Payette |
| Barber Park | June to Labor Day only: one service-level query with `layerDefs` every 10 min (144 a day), skipping the sensor table when nothing changed |
| E. coli | Daily |
| SNOTEL | Hourly |
| Static layers (USFS trails, MVUM, recreation sites, BLM, IDPR routes, Boise parks, IDFG, COMPASS, NPS) | Weekly or monthly, through the shared ArcGIS reader with an envelope filter on the ring |

The shared reader must read each layer's own `maxRecordCount` (IDPR's
service says 1000, its layer 128 says 2000), honor
`exceededTransferLimit`, and page with `resultOffset` (supported on the
EDW, BLM and IDPR layers checked). Gate the R2R and City pulls on
`editingInfo.dataLastEditDate`; R2R's schema changed on Oct 6, so store
attributes as jsonb and alert on schema changes. The research pass's "under
about 200 calls a day per host" was wrong for Ada County's server with
separate per-layer polls in season (300–600 a day); the single
`layerDefs` query fixes that.

### Read-only safety

The Barber Park service advertises Create, Update, Delete and Editing, and
IDFG's access-sites service advertises Update and Editing. The client is
query-only and never calls `applyEdits`; values from those services are
treated as unverified, since anyone may be able to change them
(correction 7).

### Robots outcomes worth remembering

- `services1.arcgis.com` and `services2.arcgis.com` answer 403 ("Invalid
  URL") and `apps.fs.usda.gov` 403; `tiles.arcgis.com`, `gis.blm.gov`,
  `swidrdc.org`, NOAA NWPS, NRCS and `gisportal-idfg.idaho.gov` answer 404.
  A 4xx means no rules under RFC 9309 and our lenient parser, so all are
  allowed. `trails.idaho.gov` redirects to an HTML page: no rules after
  following it.
- Disallowed or blocked:
  - ridb.recreation.gov and www.recreation.gov disallow `/api` (so the
    RIDB API and availability are out);
  - api.waterdata.usgs.gov disallows `/ogcapi/*/collections/*/items*` (the
    new USGS data endpoints);
  - getoutside.idaho.gov serves a bot challenge (a 405), avoided as bot
    detection rather than as a disallow;
  - Overpass and Geofabrik's taginfo disallow their APIs; Geofabrik
    disallows scripted extract downloads (shown only to browser-like
    User-Agents);
  - Trailforks' `*` group disallows GPX and KML exports and much else;
    AllTrails disallows AI crawlers outright.

### Privacy and ethics

- Drop staff user-name fields (`Editor`, `Creator`, `created_user`,
  `last_edited_user`) from every agency layer.
- Never read the Survey123 form layers that sit beside the R2R and park
  layers in the same organizations.
- Counts (cars, floaters, pathway counters) are aggregates and fine.
- RIDB's historical reservations may carry customer ZIP codes ⚠️
  (unverified): aggregates only, if ever approved.
- No Strava, Trailforks or AllTrails heatmaps or trails, and no
  social-media scraping (RainoutLine and Facebook posts are link-outs).
- Leave the Forest Service's recreation residences (private cabins) out of
  search and the map.
- The map always says whose status it is ("Ridge to Rivers says: muddy, do
  not use, Oct 6"). Our models (mud, thaw) are hatched estimates beside it
  and never override it, following the "if a layer isn't built, say so"
  rule.

### 3D and visual

- Trails draw as thin lines on the terrain at trail zoom. The map's
  terrain tiles come from the 2 m overview of the 1 m DEM up to z14 (about
  3.5 m a pixel) and are rounded by zoom, so switchbacks read only roughly;
  profiles are sampled on the server from the 1 m COGs, not from the tiles
  (correction 1).
- Condition styling uses color, dash pattern and icon, per
  [docs/13](../13-visual-design.md); CLOSED uses a strike pattern.
- The river ribbon reuses the GL engine's animated-line approach (as for
  the bus ribbons), with speed tied to cfs.
- The thaw and shade model uses per-point horizon profiles and a lidar
  canopy height model (correction 2), with the sky plugin's sun vector.

### Tables (a sketch for ch. 12)

- `core.trail`: the conflated entity, with evidence;
- `trails.source_trail`: one row per source feature (source, source_id,
  geometry, attributes as jsonb);
- `trails.rule`: typed rule rows (kind, parameters, what it applies to,
  source);
- `trails.poi`: trailheads, campgrounds, amenities;
- `evt.event`: closures, hazards, condition intervals;
- `obs` tables for river, sensor, parking and E. coli readings.

### Suggested order

One source at a time with the owner:

1. Ridge to Rivers trails and conditions, plus Greenbelt closures: the
   smallest, the most valuable, and it starts this wet season's history
   now.
2. The float panel's pieces: NWPS, Barber Park and hazards. Built now but
   quiet until June.
3. Forest orders and IDPR closures (lifecycles).
4. The OpenStreetMap paths pass.
5. USFS, BLM and IDPR geometry with conflation.
6. Campgrounds and camping rules (after `lands`).
7. The mud and thaw models, after a season of labels.

## What verification changed in the design

Verification on Oct 7 of the design as well as the sources, against the
repo and the live services. Numbers are referred to above.

1. **Terrain claims were overstated.** `basemap/terrain.py` builds
   terrain-RGB from the 2 m overview of the 1 m COGs, up to z14 (about
   3.5 m a pixel on 512-px tiles), and since the Oct 6 re-encode heights
   are rounded by zoom (1 m up to z10, 0.5 m at z11, 0.4 m at z12, 0.2 m
   at z13; [ch. 9 §9.2](../09-base-map-data.md#92-elevation-terrain-and-lidar)).
   The fine data covers only the valley; around it is a 1/3 arc-second
   (about 10 m) ring and a 30 m layer for zoomed-out views. So "trails pick
   up the 1 m DEM so switchbacks read" and "profiles sample the same
   terrain-RGB tiles" fail twice: profiles from the tiles are quantized and
   about 3.5 m at best, and most of the ring (the Boise NF, where the USFS
   trails are, and the Owyhee Front) has only 10–30 m terrain. Fixes:
   sample profiles on the server from the 1 m COGs (GDAL or PostGIS), and
   make a ring terrain build an owner decision before promising 3D drapes
   there.
2. **The thaw and shade model needs different inputs.** The 3DEP DEM is
   bare earth, so trees aren't in it, and NAIP's near-infrared shows where
   canopy is, not its height. Tree shade needs a canopy height model from
   the lidar point cloud (QL1, 2023–24, over Boise), and deciduous canopy
   changes with the season. Don't precompute "per segment per half-hour for
   a day-of-year grid": precompute a horizon profile per sample point once
   (for example 360 azimuth bins, with far-field terrain from the 10 m DEM
   so distant ridges count). Any sun position is then an exact lookup: the
   sun's altitude against the horizon angle at its azimuth.
3. **The Hulls Gulch even/odd rule is day-of-month parity.** R2R's own app
   computes `new Date().getDate() % 2` on the viewer's clock. The evaluator
   must use the America/Boise date, not UTC, and reproduce the month-end
   double odd day (the 31st, then the 1st), not "fix" it.
4. **Lifecycle keys.** Key R4 forest orders on `ordernum`, not polygons: in
   the ring 7 polygons are 5 orders (Deer Point and Crooked have two each).
   Forest-wide orders, such as the 14-in-30-days occupancy order
   0402-00-62, have no polygon in the ring, so carry them as rules. The
   Forest Service recreation sites' dated `alerts_*` and `unit_closure_*`
   fields are a further closure source the design missed. Boise Fire's
   hazards mix one-letter codes, the text "Remediated" and nulls: normalize
   them before building intervals; `CreationDate` and `EditDate` mean
   lifecycles needn't rest only on first seen.
5. **History assumptions.** The E. coli layer keeps only the latest round
   (7 rows, all Sep 28, 2026), so our daily poll is the only history. In
   the Barber Park sensor table OBJECTIDs aren't in time order (about 210k
   IDs for 54k rows) and the server's `max(Date)` disagreed with the rows:
   key and order on `Date`, and don't trust server-side date statistics.
   Readings arrive irregularly (gaps of 30 minutes to 4 hours).
6. **Polling budget errors.** "Under about 200 calls a day per host" is
   wrong for Ada County's server in season: parking and floaters every
   5–10 minutes on separate layers, plus the sensor hourly, is about
   300–600 calls a day. Use one service-level query with `layerDefs` every
   10 minutes (144 a day) and skip the sensor when nothing changed. NWPS
   observations arrive 2–3 hours late (the newest was 03:45Z at 06:27Z), so
   15-minute polling mostly re-reads them: poll every 30–60 minutes or
   dedupe on `validTime`. Gate R2R and City pulls on
   `editingInfo.dataLastEditDate`, and since R2R's schema changed on Oct 6,
   store attributes as jsonb and alert on schema changes. The shared reader
   must read each layer's `maxRecordCount`, because service and layer
   values differ (IDPR: 1000 and 2000), honor `exceededTransferLimit`, and
   page with `resultOffset`.
7. **Read-only safety.** Barber Park advertises Create, Update, Delete and
   Editing; IDFG's access sites advertise Update and Editing. The client
   must be query-only (never `applyEdits`) and treat the values as
   unverified, since anyone may be able to change them. The owner may want
   to give Ada County a courtesy heads-up.
8. **OpenStreetMap.** The loader correction is right for trails: paths,
   footways, tracks, bridleways and cycleways (the Greenbelt) aren't
   loaded. It was wrong for bike tags: `raw.record` stores all tags of kept
   ways, so on-street `cycleway=*` and `bicycle=*` on major and lane-tagged
   roads are loaded (ch. 16 now says so). The ring's Oregon slice runs east
   to about −116.9 north of Nyssa (the Snake River border at Ontario and
   Farewell Bend), not just west of −117.03. Geofabrik now shows its
   disallowing robots.txt only to browser-like User-Agents; ours gets a 301
   to a 404. Keep hand downloads.
9. **Robots summary fixes.** `tiles.arcgis.com` (404) and
   `services2.arcgis.com` (403) both mean no rules. getoutside.idaho.gov is
   a 405 with a WAF "Human Verification" page, avoided as bot detection,
   not because robots.txt disallows. Trailforks' `*` group disallows many
   paths, `/*/gpx` and `/*/kml` included, with Crawl-delay 1.
   `trails.idaho.gov/robots.txt` redirects to an HTML page on
   parksandrecreation.idaho.gov; following it per RFC 9309 gives no rules.
10. **Coverage and idea fixes.** The Idaho Centennial Trail has 0 segments
    in the ring: drop it from the backpacker idea or mark it out of area.
    IDL's public-access layer shows land reachable by public road or
    contiguity, not where camping is allowed, and was last edited March
    2024. USFS INFRA includes 5 recreation residences (privately owned
    cabins under permit): leave them out of search and the map. BLM's
    national recreation service is a nightly RIDB copy, which narrows the
    case for the 248 MB RIDB export to mainly USACE (Lucky Peak) and BOR
    sites. The Foothills imagery cache belongs to the RIDGE2RIVERS account,
    not an unknown owner, and may have trails drawn in ("Updated June 2026
    to include Sweet Connie trail").
11. **Mud-model labels are weaker than assumed.** R2R sets statuses in
    batches (238 trails share a `ConditionDate` of Sep 11 or earlier), and
    `ConditionDate` is when staff set the status, not when the trail
    changed. Grading the model against R2R's next update measures staff
    cadence as much as mud. Pair it with the weekly Friday reports and
    treat labels as interval-censored.
12. **Small factual fixes.** R2R's layer 4 is "Slow Zone". R2R's
    `Condition` has exactly seven values; `Ebike` has three, the first
    being "E-Bikes allowed (motorized trails/roads)". COMPASS's
    Pathways_Master key is `pmid`. The "Every effort is made..." disclaimer
    is the City of Boise's and isn't on the COMPASS service. USGS needs no
    key (it's optional and only raises rate limits). The rules-by-date
    evaluator qualifies as core under ch. 15's rule (trails, water and
    lands all need it), and placing the float season in `water` matches
    ch. 15 §15.7.

## Open questions

For the owner, one at a time; none is decided.

1. **OpenStreetMap paths:** the roads loader drops paths and covers only
   the valley box. Approve a second osmium pass (paths and recreation
   points, ring box) over the archived Idaho extract, and adding Geofabrik's
   Oregon extract to the weekly hand download for the ring's Oregon slice
   (which reaches east to about −116.9)? Ch. 16's "loaded Oct 7" wording
   has already been corrected.
2. **Ridge to Rivers conditions:** start polling now (attributes every 30
   minutes, gated on the last-edit date) so we capture this wet season's
   history, and send the City (Boise Parks GIS / Ridge to Rivers) a
   courtesy note asking whether the trail layer and its condition history
   may be republished? Their site terms forbid redistributing site content,
   while the ArcGIS item states only a disclaimer.
3. **USGS:** the new Water Data API's robots.txt disallows
   `/ogcapi/*/collections/*/items*` for all user agents. Use NOAA's NWPS
   for current flow (allowed) and ask USGS (the WDFN team) whether API
   clients are meant to be covered? The legacy waterservices.usgs.gov (no
   robots rules) shuts down Feb 22, 2027: approve a one-off backfill of
   Glenwood Bridge history before then?
4. **RIDB:** the API is disallowed (and needs an account and key), but the
   daily export (about 248 MB) at `/downloads/` is allowed. Approve a
   monthly export download filtered to the ring, or rely on the Forest
   Service and BLM services, which already carry most RIDB content here
   (BLM's nightly)? And should aggregated historical reservations ever be
   used for traffic research, given they may include customer ZIP codes ⚠️
   (unverified)?
5. **Barber Park:** is the "iMonnit River Sensor" temperature water or air
   (maximum 79.3; 66.2 just after midnight local time on Oct 7; the units
   aren't stated, °F per the research pass ⚠️)? Ask Ada County
   Parks & Waterways before labelling it, ask whether the parking and
   floater counts may be republished, and mention that the service
   advertises public edit capabilities?
6. **Float season thresholds:** the official FAQ gives only a typical
   500–1,500 cfs and names no gauge; news reports say about 1,500 cfs at
   Glenwood Bridge to open ⚠️. Should the panel show only the agencies'
   range and announced dates, with no computed "floatable" verdict?
7. **Plugin homes:** should the float season live in `water` (river flows,
   reservoirs, snowpack, float season, per §15.7) or in `trails`? And who
   owns shared sources (SNOTEL, IDFG access sites, IDL lands, PAD-US) among
   `trails`, `lands`, `water` and weather?
8. **Rules-by-date evaluator:** approve it as a new core piece (directions
   and even/odd days, MVUM and IDPR seasons, stay limits, the float
   season), or keep rules inside each plugin for now?
9. **IDL camping:** IDL's stay limit on endowment land couldn't be found on
   its pages. Ask IDL, or show "check with IDL" until known?
10. **Foothills Imagery 2026:** the Ridge to Rivers map's tile cache states
    no license, and who flew it is unknown. Treat it like ACHD's 3-inch
    imagery (view on request) and ask Ridge to Rivers?
11. **Pathway counters:** COMPASS's 28 permanent bike and pedestrian
    counters are mapped, but their counts sit in Eco-Counter's platform.
    Ask COMPASS for the counts (a natural fit for the flow and cycling
    work)?
12. **Bogus Basin:** its snow and Nordic grooming report wasn't examined
    (its `/mountain-report/` page was a 404; robots.txt allows most paths;
    terms unknown). Worth a look, or rely on SNOTEL 978 at Bogus Basin?
13. **Ring terrain** (added by verification): build finer terrain for the
    ring before promising 3D drapes and climb figures on Forest Service and
    BLM trails, or label those as coarse (10–30 m)?

See [chapter 17](../17-sources-for-new-plugins.md) for every new plugin's
sources and [chapter 16](../16-ideas-and-personas.md) for the ideas by
persona.
