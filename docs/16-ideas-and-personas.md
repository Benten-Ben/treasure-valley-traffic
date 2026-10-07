# 16. Ideas by persona

Where the platform could go beyond traffic, and who each idea is for. It
collects the brainstorms from the Oct 4–7 chats (the owner's first
questions, the imagery brainstorm, the persona list that led to
[chapter 15](15-plugins.md), the owner's interests stated on Oct 7, and
research analyses offered but not yet chosen) with every detail kept, so
nothing is lost between sessions. **None of it is approved** unless it says
so; decisions are in [DECISIONS.md](DECISIONS.md), and data sources still
to vet are in [SOURCES.md](SOURCES.md).

The principles that frame every idea here come from [CLAUDE.md](../CLAUDE.md)
and chapter 15:
- **Road network and nature, not people.** No tracking or identifying
  individuals. Aggregate where people are involved.
- **Private changes what we may share, never what we may collect** (§15.3).
  robots.txt and terms of service still govern collection. Data the owner
  produces (a receiver, a weather station, drives) is the cleanest of all,
  since nobody's terms apply.
- **One source at a time with the owner** before committing to how it's
  used.

## 16.1 The owner's interests

### Where it started: traffic (Oct 4–5)

The project began with the valley's traffic, which the owner said on Oct 4
"is bad and getting worse", adding that "a big issue is first just that our
lights are very poorly timed". The owner asked for three things, in this order:
1. how systems like this are run, including local specifics
   ([ch. 1](01-how-signal-systems-work.md), [ch. 2](02-treasure-valley-signal-system.md));
2. how a team would go about starting to improve things
   ([ch. 4](04-improvement-playbook.md));
3. emerging areas, such as how Google teams have tested AI-integrated
   systems ([ch. 5](05-ai-and-emerging-tech.md)).

On Oct 5 the questions widened, then turned into the platform:
- **01:05:** can AI agents, or more automated tools in general, close the
  gap between the retiming resources available and those required
  ([ch. 6](06-automation-and-ai-agents.md))? And what data can we collect
  ourselves: "harvesting from Google if that's allowed/possible via API"
  (it isn't, [ch. 7](07-diy-data-collection.md)), or government,
  alternative-map or OpenStreetMap sources "to supplement or
  cross-compare" ([ch. 7](07-diy-data-collection.md),
  [ch. 8](08-data-inventory.md))?
- **03:49:** "start building ingestors and an aggregator for everything we
  can get our hands on and start building a bit of a gods eye view of the
  region" ([ch. 10](10-architecture.md)).
- **03:55:** "I want like my own map of the valley that we can start
  visually overlaying data on", and does the state provide 3D terrain scans
  and streets "that we can start building together ourselves"
  ([ch. 9](09-base-map-data.md)).

That is where the platform began. These traffic questions remain the
project's starting point; the interests below came later.

### Beyond traffic (Oct 7)

The owner named these as personal interests, so they break ties when we pick
what to build next:

- **wildlife;**
- **the sky;**
- **gardening:** "which sky and building locations, weather, etc would be
  useful for";
- **weather,** including **real weather drawn in 3D** (§16.5);
- **farms and crops;**
- **hiking, camping, land ownership and permissions;**
- **cycling;**
- **fires and hazards.**

## 16.2 Ideas by persona

Each persona lists what they'd see, the data it needs, the plugin it would
live in, and its status as of Oct 7. The Oct 7 source research for the
owner's interests (verified source catalogs, a first thing to build per
persona, and open questions) is in [chapter 17](17-sources-for-new-plugins.md)
and [docs/sources/](sources/).

### Aviation watcher (`aircraft`; the first new plugin)

Aircraft are genuinely transportation, so this plugin is in scope.
- **Live aircraft:** position, altitude, heading, speed and callsign, drawn
  in 3D at their altitude and played back like the buses, through the tracks
  contract (§15.5).
- **Helicopters and special aircraft:**
  - medical helicopters (Air St. Luke's, Life Flight);
  - Gowen Field's Guard units;
  - summer fire tankers from the Boise air tanker base (the National
    Interagency Fire Center is in Boise).
- **FAA open data:** airspace, temporary flight restrictions, drone no-fly
  maps.
- **Sources** (research agent, Oct 7, 00:15 UTC):

  | Source | Terms and access | Use |
  |---|---|---|
  | adsb.lol live data | ODbL; no key needed today; one query covers the whole valley box | **Decided Oct 7** |
  | adsb.lol daily open archives | Each day is about 3.6 GB for the whole world | No backfill for now |
  | FAA aircraft registry | Public domain; gives tail number, type, model and year | Decided Oct 7, for types; owners' names are never stored |
  | adsb.fi | Personal use only, and silent on storing | Not used |
  | ADS-B Exchange | Paid, no redistribution | Not used ([DECISIONS](DECISIONS.md)) |
  | OpenSky | Needs a written agreement | Not used |
  | airplanes.live | Asks to be contacted | Not used |
  | The owner's own receiver | A roughly $30–60 USB radio and antenna running readsb, often with 150+ km range ⚠️. It's radio, so no terms apply | Best long term; a dual-band receiver (1090 and 978 MHz) is suggested |

  The privacy rules (LADD and PIA aircraft, medical flights) are in
  [DECISIONS](DECISIONS.md).
- **A sample** (Tuesday Oct 6, 6:07 pm Boise time): 12 aircraft over the
  valley, three of them helicopters (a Bell 407, a Robinson R22 and a
  Bell 429). Two carried the FAA privacy flags (LADD or PIA, as marked by
  adsb.lol).
- **Storage:** about 33 MB a day at a 5 s poll (about 12 GB a year), and
  half that at 10 s.
- **Gaps:**
  - aircraft without ADS-B don't appear, which may include some of Gowen
    Field's Guard helicopters;
  - light planes on 978 MHz appear only through a ground station's
    rebroadcast, which is why a dual-band receiver is suggested.
- **Polling:** start at 10 s once the courtesy note is sent, and speed up
  later if adsb.lol is fine with it.
- **Build plan** (Oct 7): the collector deploys switched off, behind a
  Compose profile `aircraft`, and starts once the owner has sent the note.
  The map layer comes with the app-plugin step ([§15.6](15-plugins.md#156-refactor-plan)).
- **Status:** the ingestor was half-built when the cloud session stopped,
  and isn't in this repository yet. It deploys switched off until the owner
  sends the courtesy note to adsb.lol.

### Hiker, backpacker, camper, hunter, angler, floater (`lands`, `trails`, water)

- **Who owns what:**
  - PAD-US (USGS, public domain) gives every public parcel with its manager
    and its public access.
  - On top of it: BLM, state endowment lands, the Boise National Forest,
    Fish & Game management areas, and Access Yes! private land open for
    hunting and fishing.
- **Rights and restrictions:**
  - Forest Service motor vehicle use maps (which roads allow what, and when)
    and BLM travel routes;
  - seasonal wildlife closures, fire-restriction stages, hunting units and
    seasons;
  - dispersed-camping rules, mining claims, grazing allotments.
- **Trails:** Ridge to Rivers with its mud closures ⚠️, plus OpenStreetMap
  and Forest Service trails. The Oct 7 OpenStreetMap load kept roads only;
  paths, footways and the Greenbelt need a separate pass
  ([ch. 17](17-sources-for-new-plugins.md)).
- **Water:**
  - Boise River flows from USGS gauges (float season opens around 1,500
    cfs ⚠️);
  - reservoir levels;
  - snowpack (SNOTEL).
- **Campgrounds:** sites and availability from Recreation.gov's open data.
- **Status:** the next plugins after aircraft (§15.6, step 4). Source
  research started Oct 7.

### Fire and weather watcher (`hazards`, weather)

- **Data:**
  - fire perimeters (NIFC);
  - satellite hotspots (NASA FIRMS);
  - smoke and air quality;
  - weather warnings;
  - earthquakes;
  - river flood stages.
- **Ties to traffic:** fire road closures lead straight back to traffic, and
  smoke cuts visibility.
- **Builds on:** the road-weather layer (UI v2 WP16), the 511 events and
  advisories already recorded, and the Valley Feed (deferred).
- **The owner's 3D weather idea** is in §16.5.
- **Status:** not started. It's a cheap win, since most sources are open and
  small.

### Commuter (mostly `flow` and `conditions`)

- **"When should I leave"**, from our own travel-time history (bus-derived
  speeds, later GPS drives).
- **Incidents and work zones on my route**: work zones and 511 events are
  already recorded.
- **Sun glare:** low sun straight down an east–west road at commute time.
  It's computable from the sun's position and each road's bearing, and it's
  also a real crash-risk research question (see Sky).
- **How long buses wait at signals** on State St, Fairview and Chinden, by
  time of day: a research analysis from our own bus GPS (§16.6).
- **Builds on:** the Valley Feed, search and full replay (deferred).
- **Status:** mostly traffic core already; nothing commuter-specific is
  planned.

### Cyclist and pedestrian (`safety`, `roads`)

- **Infrastructure:** bike lanes and the Greenbelt, from ACHD's and COMPASS's
  bike and pedestrian layers (ACHD has already scored Level of Traffic Stress)
  and OpenStreetMap. The Oct 7 OpenStreetMap load kept roads only: on-street
  bike tags on major roads are recorded, but paths, footways and the Greenbelt
  need a separate pass ([ch. 17](17-sources-for-new-plugins.md)).
- **Crashes:** bike and pedestrian crashes. COMPASS's crash data records the
  road-user type, and that type may be published (DECISIONS, Oct 6).
- **Sidewalk gaps,** and **scooter-share feeds** where they're published ⚠️.
- **Status:** waits on the crashes layer (deferred) and source research.

### Neighbor and civic (`development`)

- **What's being built near me:** building permits, plats, zoning hearings.
- **Also:** school boundaries, precincts and results, public meetings.
- **Builds on:** COMPASS permits and plats (loaded), Boise's development
  pipeline (queued after the core pieces), the growth-context layer
  (deferred), and parcels (private).
- **Status:** strong overlap with what's collected; mostly a display
  question.

### Homeowner or land buyer (private, with `parcels`)

- **Data:**
  - ownership and zoning;
  - FEMA floodplains;
  - soils;
  - water rights (Idaho Department of Water Resources) and wells;
  - irrigation districts and canal schedules.
- **Private** because parcel data may not be redistributed. Aggregates only
  in anything shared.

### Gardener (new, Oct 7)

Sun position, building locations and weather combine into a "my yard" view:
- **Sun and shade hours** per spot, by month. They come from the sun's path,
  our building heights (Overture, 351,776 buildings), tree canopy (lidar) and
  the terrain.
- **Last frost and the growing season;**
- **soil type;**
- **when canal water starts and stops;**
- **heat and smoke days.**

It must never expose other people's properties. Per-house analysis is for
the owner's own place. Status: source research started Oct 7.

### Farmer (`farm`)

- **Crop type by field** (USDA's Cropland Data Layer, public).
- **Canal water dates.**
- **Field burning:** the daily burn decisions.
- **Farmland turning into subdivisions** over time (see History, and §16.3).
- **Status:** source research started Oct 7.

### Sky watcher and photographer (`sky`)

- **ISS and Starlink passes** over the 3D map.
- **Sun and moon paths and shadows.**
- **Dark-sky spots.**
- **Days when the sunset lines up with a street.**
- **Sun glare** on east–west roads at commute time, shared with the
  commuter.
- **Builds on:** the per-frame sun context designed for camera calibration
  (Oct 5) and the night map look (deferred).

### History buff (`history`)

- **A year slider** through historic aerials (USDA's service has NAIP back to
  about 2013, every two years) and USGS topo maps ⚠️. Swipe between years
  and watch subdivisions, new roads and widenings appear.
- **The Oregon Trail.**
- **Farmland turning into subdivisions:** a direct measure of where growth,
  and future traffic, is heading.

### Wildlife (`wildlife`)

- **Mule deer winter range and highway crossings.**
- **Wildlife–vehicle collisions:** a road-safety link, through the crashes
  layer.
- **Status:** source research started Oct 7. Never expose sensitive
  locations such as nests or dens.

### Household (private)

The owner's own drives, weather station, air sensor and aircraft receiver.
These are the cleanest data of all.

## 16.3 What the aerial imagery could do (Oct 6 brainstorm)

The owner asked what else the 0.3 m NAIP 2025 imagery could do (trees,
objects, landscape colors, parking lots, "anything I might not be thinking
about"). Two facts shape the answers:
- **There's a fourth band, near-infrared.** It separates living plants from
  pavement, roofs and dirt almost for free.
- **NAIP is public domain,** so anything derived from it can be published,
  unlike ACHD's 3-inch imagery.

The county mosaics we use for the valley-wide layer (Oct 7) carry all four
bands at 0.3 m, and they're kept on the server for exactly this.

**The pilot's pick for the next design round:** painted land cover, the year
slider and driveway density.

### Making the map look better

- **Painted land cover:** classify every pixel into tree canopy, lawn and
  irrigated landscaping, dry grass and sagebrush, bare dirt, pavement, roofs
  and water. The Valley and Clay styles then use our own game-like colors
  instead of photos: green lawns, dark tree clumps, tan desert, gray parking
  lots. Easy, and it fits [chapter 13](13-visual-design.md). How (Oct 7):
  - near-infrared separates vegetation, and irrigated lawns from dry
    sagebrush in a July flight;
  - water absorbs near-infrared, so it reads dark;
  - roofs come from the Overture building footprints;
  - trees and lawn are told apart by canopy height (a lidar surface model
    minus the 1 m bare-earth DEM).
- **3D trees:** find each tree crown and its size, then draw simple low-poly
  trees in the 3D view. The first idea was height from the shadow (the sun's
  angle at flight time is known). But USGS lidar at 8+ points per m² already
  covers Boise, Meridian, Eagle, Star, Kuna, Caldwell and Parma ([ch. 9](09-base-map-data.md)),
  so heights come straight from it. Medium effort.
- **Roof colors** to tint our 3D buildings to match what you'd actually see.
- **Imagery draped over the terrain** in 3D: a light version of Google Earth.
- **A styled photo option:** the imagery slightly desaturated and tinted to
  our colors, so traffic data stands out on top. Cheap.
- **A year slider** (see History).

### Uses for the traffic research

- **Driveways per mile on arterials.** Access density is one of the
  strongest predictors of crashes and slowdowns, and no source gives it
  cleanly.
- **Parking lots as traffic generators:** lot outlines and rough stall counts
  show where trips start and end along each corridor.
- **Farmland turning into subdivisions** over time, especially in Canyon
  County, where we have no parcel data.
- **Road geometry checks:** pavement width, medians and turn-bay lengths.
  These help settle lane conflicts between sources, such as HPMS against
  ACHD and the Chinden case. 30 cm shows turn bays and lane lines, less
  crisply than the 3-inch imagery.
- **Sidewalk and crosswalk gaps** near signals and bus stops, checked against
  COMPASS's sidewalk layer.
- **Shade at bus stops:** tree canopy over each VRT stop, a nice extra for
  transit.
- **Irrigation canal crossings:** the narrow bridges that limit road
  widening.

### Camera work

- **Sharper ground reference points** for the calibrator.
- **Automatic calibration** by matching each camera's view to the overhead
  photo. Research-grade, but it would remove most manual point-picking.
- **Synthetic camera views:** draw the map from a calibrated camera's
  position, with the imagery as the ground, over the live picture. This is
  UI v2's "look through", and the imagery makes the ground line up visibly.

### Fun or speculative

- **Car counts in the snapshot.** At 30 cm a car is about 15×6 pixels, so we
  could count vehicles and see queues at each signal at the moment of
  flight. It's a single summer midday snapshot, counted only in totals, which
  fits the road-network-not-people rule.
- **Speeds from color fringes.** The camera's color bands are captured a
  split second apart, so moving cars can show colored ghosts whose offset
  hints at speed and direction. Whether NAIP's cameras show this clearly is
  unknown ⚠️.
- **Giving back to OpenStreetMap.** NAIP is an accepted source for tracing,
  so we could hand-add missing turn lanes and signals under OSM's editing
  rules.

## 16.4 Shared core pieces serve almost every persona

The pattern across §16.2 (Oct 7): a handful of core pieces unlock most
personas, and most are already on the [deferred list](DEFERRED.md). Building
them after UI v2 gives the most persona value per hour.

| Core piece | Personas it unlocks | Status |
|---|---|---|
| Full replay (time bar, 60x and 600x, scrubbing) | aviation, commuter, history, hazards | Deferred; the tracks contract is done |
| Search (places, roads, cameras, routes, trailheads) | everyone | Deferred; "places and search" is core (§15.1) |
| The Valley Feed (a stream of events) | commuter, hazards, civic | Deferred |
| A regular OpenStreetMap load | cyclist, hiker, lanes, Canyon County | First load done by hand Oct 7, roads only (paths, footways and points of interest aren't loaded yet); weekly hand downloads until Geofabrik answers |
| The 3D engine | aviation, cameras, 3D weather, 3D trees | UI v2 WP9 (wave D) |
| Readings and lifecycles (§15.1) | weather, water, gardening, hazards, trails | Core design; displays come with the time-series card and the Valley Feed |

A proposed order for after UI v2 (Oct 7, **not decided**):
1. Show what's already collected: intersections, lanes, crashes and the
   high-injury network, rail crossings, growth (DEFERRED's next round).
2. The shared core pieces above.
3. Aircraft (waits on the adsb.lol note), then hazards and water as the
   cheapest new plugins: open, keyless and small.
4. Lands and trails, then painted land cover.

## 16.5 Weather in 3D (the owner's idea, Oct 7)

The owner asked for real geometry for weather in the visualization: clouds,
fog and precipitation reconstructed from radar and other data as volumes,
"or however it makes sense".

**Candidate inputs** (research started Oct 7):
- NEXRAD radar volumes from the Boise radar;
- NOAA's MRMS 3D reflectivity mosaics and precipitation type;
- GOES-18 satellite cloud imagery, cloud-top heights and fog/low-stratus
  products, and GOES lightning;
- the HRRR model's 3D cloud, visibility and smoke fields;
- airport ceilings and visibility (ASOS/METAR).

**Rendering** would use our own WebGL scene engine (UI v2 WP9):
- ray-marched 3D textures for clouds and precipitation;
- layered cloud slabs from cloud-top heights and ceilings;
- fog layers from fog products and visibility;
- particles for rain and snow.

It would all be synced to the replay clock. The verified research (Oct 7)
turned this into a phased design, MVP first: radar volumes from MRMS when it's
raining, then HRRR clouds checked against GOES, then fog, inversions and
smoke, then particles, lightning and wind. It's in
[chapter 17](17-sources-for-new-plugins.md), with the sources in
[sources/weather.md](sources/weather.md) and
[sources/weather-3d.md](sources/weather-3d.md).

## 16.6 Research analyses from data we already record

Analyses that answer the research questions in §16.1 from data the
platform already collects. None has been chosen or built.

### How long buses wait at signals (offered Oct 6)

The pilot offered this on Oct 6 as "a first research result from data we're
already recording", option 3 of 4 in a list of next steps. The owner moved
on to the aerial imagery and the source reviews instead, so it was never
chosen or built.
- **What:** with the roughly day and a half of VRT bus GPS on hand then,
  measure how long buses wait at signals along State St, Fairview and
  Chinden, by time of day, with the recorded work zones as context.
- **How:** a standalone analysis script that touches nothing else.
- **Why:** the pilot called it "the project's core question, answered with
  our own data". It's the specific version of
  [§8.7](08-data-inventory.md#87-most-useful-next-additions) item 1 (bus
  travel times through signalized corridors).
- **What the data allows** ([§8.2](08-data-inventory.md#82-bucket-a-reachable-and-allowed),
  VRT row): each bus reports about every 30 s, 22% of fixes are stationary
  (stops and signals), and there's no speed field, so speeds come from
  consecutive fixes. The feed looks complete for the fixed-route fleet (42
  buses at the Oct 5 peak).
