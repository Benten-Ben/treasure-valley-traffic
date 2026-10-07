# 15. Core and plugins (proposed)

The platform began as a traffic-research map, but the owner expects it to
grow into other subjects: aircraft, public land and trails, and more. This
chapter splits the code into a **core** that every subject needs and
**plugins**, one per subject. Some plugins may be **private**, for data
we're allowed to use but not to share.

Status: agreed with the owner on Oct 7, 2026 ([DECISIONS](DECISIONS.md)):
the boundary, private plugins, the plugin list after one more pass (§15.4)
and the refactor plan (§15.6), which the lead carries out step by step.
Step 1 (ingest plugins) is built: `plugins/<name>/` in the repository.

## 15.1 What's core

Core is everything a plugin needs, and nothing tied to one subject:

- **The base map:** terrain, aerial imagery, streets, buildings and the 3D
  view (`basemap/`, the map and its GL layers in `app/`).
- **Time:** live, recorded and played back on one clock. Anything that
  moves (a bus today, an aircraft or a helicopter tomorrow) uses one
  **tracks** contract and the same player (§15.5).
- **The app shell:** the layer registry and manager, lenses, windows and
  panels, selection and picking, the UI kit, and the meta, health and
  versions APIs.
- **The ingest framework:** polite HTTP (robots.txt, pacing, honest
  User-Agent), versioned records (`raw.record`), sources and fetch logs
  (`ops`), schedules (`run`, `serve`, `stream`), the archive, the shared
  ArcGIS reader and event lifecycles (`evt`).
- **Licensing and visibility:** every source states its license and whether
  we may republish it, and every plugin is public or private (§15.3).
- **Deploy:** Compose, Caddy, migrations, backups.

The rule for anything else: it moves into core when any subject could use
it, or when two plugins already need it. By that rule, four more pieces
are core:

- **Three shapes of time.** Everything we collect is one of:
  - **tracks**: things that move (buses; aircraft next), §15.5;
  - **readings**: values at a fixed place over time (counts, road weather,
    river flows, camera frames);
  - **lifecycles**: things that start and end (work zones, incidents,
    closures, flight and fire restrictions, trail mud closures), today's
    `evt.event`.
  Core owns all three contracts and their generic displays: the player for
  tracks, a time-series card for readings, and the Valley Feed and "what
  was active at this moment" for lifecycles. A new plugin mostly fills
  them.
- **Evidence and review.** Intersections are built from several sources
  with confidence, candidates and a review file; lanes pick a winner per
  segment with conflicts flagged. Land ownership, trails and aircraft
  identity will need the same. Core gives entities one way to carry
  evidence and confidence, and one review table for human decisions
  (confirm, retire, hold until new evidence), replacing per-plugin files
  such as `plugins/intersections/ingest/intersection_reviews.json`.
- **Places and search.** Each plugin adds its searchable names (roads,
  intersections, stops, cameras, trailheads, airports) to one index.
- **Areas.** The valley box and the regional ring become named areas;
  aircraft want a circle of about 250 km, lands the national forest. Each
  plugin says which area it covers.

The base map's streets (for drawing) are core; the road network as data
(ACHD's segments, lanes) is the `roads` plugin.

## 15.2 What a plugin is

A plugin is one folder with everything about one subject:

```
plugins/<name>/
  plugin.json      the manifest (below)
  README.md        what it shows, its sources, licenses and ethics notes
  ingest/          Python: its sources and streams (registered from the manifest)
  migrations/      its own SQL migrations, applied after core's, in dependency order
  app/             its map layers (layers/<id>/def.ts), lens, panels and API handlers
  tests/
```

The manifest says:

| Field | Example (transit) |
|---|---|
| `name`, `title` | `transit`, "Buses (Valley Regional Transit)" |
| `depends` | `["roads"]` (other plugins it builds on) |
| `visibility` | `public` or `private` |
| `order` | where its sources run among plugins it doesn't depend on (lower first) |
| `sources` | each source's name, module, kind (`source`, `stream`, or `manual` for by-hand loads), license, credit, and `republish`: `yes`, `aggregates`, `internal` or `no` |
| `tables` | the tables it owns (for exports and backups) |
| `commands` | its own `python3 -m ingest` subcommands (e.g. `osm-load`) |
| `storage` | expected growth per day, so the disk plan can add them up |
| `ethics` | anything special (e.g. "no plate or face recognition") |

How the pieces plug in:

- **Ingest:** `python3 -m ingest` finds `plugins/*/plugin.json` (and any
  folders on `TVT_PLUGIN_PATH`, for private plugins) and builds its
  `SOURCES` and `STREAMS` from them, in dependency order, then by each
  plugin's `order`. Source names don't change, so `ops.fetch` history
  carries on. Plugin folder names are Python names (`achd_tables`), so a
  plugin imports as `plugins.<name>`.
- **Database:** tables stay in the shared schemas by kind (`core`
  entities, `obs` time series, `evt` lifecycles), as
  [ch. 12](12-database-schema.md) designs them; the manifest says who owns
  which. Migrations 0001–0018 stay where they are (they're history on the
  server); new ones live in each plugin and are recorded as
  `<plugin>/<file>`. A private plugin keeps its tables in its own schema
  (`private_<name>`), so exports and published tiles can leave it out by
  schema. `restricted` stays for personal or do-not-redistribute data
  inside public plugins (the people in crash records).
- **App:** the layer registry already finds layers by folder
  (`import.meta.glob`); it will also look in `plugins/*/app/layers/` and the
  private folder. One catch-all API route, `/api/<plugin>/…`, hands requests
  to the plugin's handlers, so today's URLs (`/api/transit/…`,
  `/api/cameras/…`) stay the same.

## 15.3 Private plugins

A private plugin is for data **we may collect and use but not
redistribute**: Ada County's parcels ("do not re-distribute"), the 511
API's data, COMPASS's internal layers, ACHD's count tables, and ACHD's
3-inch imagery if COMPASS allows a private copy. Data the owner produces
(an aircraft receiver, a weather station, GPS drives) can go in either.

**Private changes what we may share, not what we may collect.**
robots.txt and terms of service govern collecting whether or not we
republish, so a private plugin is never a way around a disallowed endpoint
or a site that forbids storing its data (Google, Waze, Strava, 511's list
pages).

Where they live (owner, Oct 7: a private GitHub repo and/or the server):

- **Code:** a private GitHub repository, checked out on the server at
  `/srv/tvt/plugins-private/`, beside today's private files
  (`/srv/tvt/private/`). Nothing private enters this public repo;
  `tools/check_public.py` also rejects any `plugins-private/` path.
- **Data:** in each private plugin's own schema, and in its own archive
  folder.
- **Build:** Compose gives the app and ingest images the private folder as
  an extra build context, so a build without it simply has no private
  plugins.
- **Showing it:** private layers are shown only to the owner. Today
  everyone who can reach the site (the owner's tailnet) is the owner. If
  guests ever get access, Caddy will pass the viewer's Tailscale identity
  and the app will hide private layers from them. Published tiles,
  exports and screenshots for others never include private layers.

The private files we already have fit this: the ACHD table tools and
copies, the 511 probe, the parcels copy and its terms, and the camera
sampler.

## 15.4 The plugins we already have

| Plugin | What's in it today | Depends on | Visibility |
|---|---|---|---|
| `roads` | ACHD's road segments and the road tiles (`/api/tiles/roads`, the Streets layer's data), the lane inventories (ITD HPMS, ACHD's Master Street Map, COMPASS's centerline), OpenStreetMap's ways, lanes and signal nodes, the shared segment matcher, `core.segment_lanes`, and the coming Lanes layer | — | public (OSM parts ODbL) |
| `intersections` | Everywhere traffic streams meet and are controlled: COMPASS's signals and Regional_Signals, ACHD's 2022 signal points (signals, beacons, school and fire signals), the intersection build and its reviews, FRA rail crossings and their links; later roundabouts | `roads`, `cameras` | public, internal until COMPASS answers |
| `cameras` | ACHD's camera list, 511's views, the key-camera and road-weather frame streams, daily videos, the video library, calibration | — | public (images not republished) |
| `transit` | VRT's GTFS and live positions, route matching, ribbons, progress, tracks | — | public |
| `conditions` | Live road conditions: ITD's work zones (WZDx), the 511 API (events, message signs, advisories, road weather, truck restrictions, winter roads) | — | public (511 data internal) |
| `safety` | COMPASS's crashes and high-injury network; crash people in `restricted` | `roads`, `intersections` | public, aggregates only for people |
| `flow` | How traffic moves: COMPASS's counts, congestion measures and commute travel times; later speeds from buses and GPS drives | `roads` | public (congestion internal) |
| `development` | Why traffic will change: COMPASS's traffic zones and forecasts, building permits and plats; later Boise's development pipeline | — | public |
| `achd_tables` | ACHD's count and turn-movement copies and their tools (extends `flow`) | `flow`, `intersections` | **private** |
| `parcels` | Ada County Assessor parcels and characteristics, aggregates by corridor | `development` | **private** |

The dependencies are what the ingest code needs (step 1): the intersection
build links cameras, and nothing in the camera, transit or conditions
ingest uses the road tables, so those three load first, as they did before
the split. Step 2 adds a dependency where an app layer needs one.

Lenses group plugins: **Traffic** (roads, intersections, cameras,
conditions, safety, flow), **Transit**, **Land** (development and the
coming lands and trails, with parcels for the owner) and **Sky** (the
coming aircraft).

Considered and rejected: plugins by agency (ACHD, COMPASS, ITD), because
subjects cross agencies; one big "traffic" plugin, because cameras alone
are most of the storage and should switch off on their own. Earlier drafts
had `signals` (rail crossings fit better under `intersections`) and a
`demand` grab bag (now `flow` and `development`).

Staying in core: `basemap/` (terrain, imagery, streets, buildings), the
GL and 3D engine, the three time contracts and their displays, evidence
and review, places and search, areas, the layer system, the ingest
framework, `core.source_link`, deploy and `tools/check_public.py`.

## 15.5 Tracks: one contract for everything that moves

Buses already play back through the tracks contract
(`#lib/contracts/tracks`, `/api/transit/tracks`). It becomes core:

- **Database:** each moving-things plugin keeps its own hypertable; transit
  keeps its own, and aircraft gets `obs.aircraft_position`. Every row has
  at least: id, time, position (with altitude for aircraft), heading,
  speed, and the plugin's own fields.
- **API:** every such plugin answers `/api/<plugin>/tracks?from&to&bbox`
  in the same shape, so the player, the time bar and "follow" work the same
  for a bus or a helicopter.
- **3D:** the GL engine draws each kind with its own model (bus, airliner,
  small plane, helicopter), at its altitude for aircraft.

## 15.6 Refactor plan

Each step leaves the server doing exactly what it did before (same
sources, tables and URLs), with every test green, before the next one starts.

1. **Ingest plugins.** **Done, Oct 7:** merged and pushed; the new images
   were built on the server and list the same sources (the services switch
   at their next restart):
   - the manifest format and loader (`ingest/manifest.py`,
     `ingest/sources/__init__.py`);
   - each source and its helpers moved with `git mv` into
     `plugins/<name>/ingest/`; what two plugins share went to core
     (`compass_layer.py`, the UTM projection, the snapshot guard);
   - `SOURCES` and `STREAMS` built from manifests, with the same names and
     run order (a test pins them), and plugin commands
     (`python3 -m ingest osm-load`, `segment-match`, ...);
   - the migrations runner learns plugin folders (new migrations only),
     recorded as `<plugin>/<file>`;
   - tests moved with their plugins (`python3 -m unittest discover -s
     plugins -t .`);
   - `tools/check_public.py` rejects `plugins-private/` paths and private
     manifests.
   The old module entry points (`python3 -m ingest.osm_load`, ...) remain
   as shims, and three paths the app reads (`ingest/key_cameras.csv`,
   `ingest/route_colors.py`, `ingest.sources.idaho511_frames`) are kept
   until step 2 points the app at the plugins.
   Deploy, then compare a day of `ops.fetch` with the day before.
2. **App plugins** (after the UI v2 round now being built finishes, to
   avoid colliding with it):
   - layers, panels and server modules move into `plugins/<name>/app/`;
   - the registry also scans plugin folders;
   - the catch-all API route goes in;
   - `LayerId` is opened up to whatever plugins register.
   Screenshots and the existing end-to-end specs must match before and after.
3. **Private plugins.** **Started, Oct 7:**
   - the private repo is on the server (`/srv/tvt/plugins-private`, a git
     repository); a private GitHub copy (approved) needs the owner to
     create the repo and give Claude's GitHub app access to it, since this
     session's GitHub access can't create repositories;
   - `achd_tables` holds the ACHD table tool and its tests, `parcels` the
     Assessor copy's manifest and terms, and `tools/` the one-off 511 probe
     and camera sampler; the data stays in `/srv/tvt/private/data`, which
     the ingest service mounts read-only;
   - Compose gets the extra build context when a private plugin first has
     code a service runs (none yet).
4. **New plugins,** one source at a time with the owner:
   - `aircraft` (being built Oct 7): adsb.lol's live data (ODbL) every
     10 s, with the FAA registry for types; it starts once the owner has
     sent adsb.lol a courtesy note, and moves to the owner's own receiver
     later;
   - then `lands` (ownership, management, access and restrictions) and
     `trails`.

## 15.7 Ideas for later plugins (Oct 7 chat)

Kept here so they aren't lost; none is approved yet.

- **aircraft:** live and recorded positions with altitude, in 3D; medical
  and Guard helicopters, fire aviation; FAA airspace and flight
  restrictions.
- **lands:** who owns and manages what (PAD-US, BLM, state endowment lands,
  Boise National Forest, Fish & Game), public access, Access Yes!,
  vehicle-use maps, seasonal closures, fire restrictions, mining claims,
  grazing allotments.
- **trails:** Ridge to Rivers and its mud closures, OpenStreetMap and Forest
  Service trails, trailheads, campgrounds.
- **water:** river flows (USGS gauges), reservoirs, snowpack, floating
  season, canals.
- **hazards:** fire perimeters and hotspots, smoke and air quality, weather
  warnings, earthquakes.
- **sky:** sun and moon paths and shadows (and sun glare on east–west roads
  at commute time), satellite passes, dark-sky spots.
- **history:** historic aerials and topo maps on a year slider.
- **civic:** development near me, hearings, school boundaries, precincts.
- **home** (private): the owner's own sensors, drives and receiver.

More from the same Oct 6–7 brainstorm, restored from the chat (Oct 7). Some
of it belongs in existing plugins:
- **commuter** (`flow`, `conditions`): "when should I leave", from our own
  travel-time history; incidents and work zones on my route.
- **cyclist and pedestrian** (`safety`, `roads`): bike lanes and the
  Greenbelt, bike and pedestrian crashes (COMPASS records the road-user
  type), sidewalk gaps, scooter-share feeds where they're published ⚠️.
- **homeowner or land buyer** (private, with `parcels`): ownership, zoning,
  FEMA floodplains, soils, water rights (Idaho Department of Water
  Resources), wells, irrigation districts and canal schedules.
- **farmer:** crop type by field (USDA's Cropland Data Layer), canal water
  dates, field burning.
- **wildlife** (`safety`): mule deer winter range and highway crossings,
  wildlife–vehicle collisions.
- **from the aerial imagery** (Oct 6), for the next design round:
  - painted land cover, classifying every pixel (tree canopy, lawn,
    sagebrush, bare dirt, pavement, roofs, water) so the Valley and Clay
    styles can draw it;
  - the year slider (NAIP back to about 2013, see history above);
  - driveway density along corridors (with `parcels`).
