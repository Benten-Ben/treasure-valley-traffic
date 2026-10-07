# 15. Core and plugins (proposed)

The platform began as a traffic-research map, but the owner expects it to
grow into other subjects: aircraft, public land and trails, and more. This
chapter splits the code into a **core** that every subject needs and
**plugins**, one per subject. Some plugins may be **private**, for data
we're allowed to use but not to share.

Status: the boundary and private plugins were agreed on Oct 7, 2026
([DECISIONS](DECISIONS.md)). The plugin list (§15.4) and the refactor plan
(§15.6) are proposals for the owner to approve.

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
| `sources` | each source's name, license, credit, and `republish`: `yes`, `aggregates`, `internal` or `no` |
| `tables` | the tables it owns (for exports and backups) |
| `storage` | expected growth per day, so the disk plan can add them up |
| `ethics` | anything special (e.g. "no plate or face recognition") |

How the pieces plug in:

- **Ingest:** `python3 -m ingest` finds `plugins/*/plugin.json` (and any
  folders on `TVT_PLUGIN_PATH`, for private plugins) and builds its
  `SOURCES` and `STREAMS` from them, in dependency order. Source names
  don't change, so `ops.fetch` history carries on.
- **Database:** tables stay in the shared schemas by kind (`core`
  entities, `obs` time series, `evt` lifecycles), as
  [ch. 12](12-database-schema.md) designs them; the manifest says who owns
  which. Migrations 0001–0017 stay where they are (they're history on the
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

## 15.4 The plugins we already have (proposal)

| Plugin | What's in it today | Depends on | Visibility |
|---|---|---|---|
| `roads` | ACHD's road segments and the road tiles (`/api/tiles/roads`, the Streets layer's data), the lane inventories (ITD HPMS, ACHD's Master Street Map, COMPASS's centerline), OpenStreetMap's ways, lanes and signal nodes, the shared segment matcher, `core.segment_lanes`, and the coming Lanes layer | — | public (OSM parts ODbL) |
| `signals` | COMPASS's signals and Regional_Signals, ACHD's 2022 signal points, the intersection build and its reviews, FRA rail crossings and their links | `roads` | public, internal until COMPASS answers |
| `cameras` | ACHD's camera list, 511's views, the key-camera and road-weather frame streams, daily videos, the video library, calibration | `roads` | public (images not republished) |
| `transit` | VRT's GTFS and live positions, route matching, ribbons, progress, tracks | `roads` | public |
| `conditions` | ITD's work zones (WZDx), the 511 API (events, message signs, advisories, road weather, truck restrictions, winter roads) | `roads` | public (511 data internal) |
| `safety` | COMPASS's crashes and high-injury network; crash people in `restricted` | `roads`, `signals` | public, aggregates only for people |
| `demand` | COMPASS's counts, congestion measures and commute times, traffic zones, permits and plats | `roads` | public (congestion internal) |
| `achd-tables` | ACHD's count and turn-movement copies and their tools | `signals` | **private** |
| `parcels` | Ada County Assessor parcels and characteristics, aggregates by corridor | `roads` | **private** |

Together, `roads` through `demand` make up "traffic". They're separate
plugins so each can be switched off, tested and documented on its own.
A "traffic" lens can still turn several on at once.

Staying in core: `basemap/` (terrain, imagery, streets, buildings), the
GL and 3D engine, the tracks contract and player, the layer system, the
ingest framework, `core.source_link`, deploy and `tools/check_public.py`.

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

## 15.6 Refactor plan (proposal)

Each step leaves the server doing exactly what it did before (same
sources, tables and URLs), with every test green, before the next one starts.

1. **Ingest plugins** (after the lanes fixes are merged):
   - the manifest format and loader;
   - `git mv` each source and its helpers into `plugins/<name>/ingest/`;
   - `SOURCES` and `STREAMS` built from manifests;
   - the migrations runner learns plugin folders (new migrations only);
   - tests move with their plugins.
   Deploy, then compare a day of `ops.fetch` with the day before.
2. **App plugins** (after the UI v2 round now being built finishes, to
   avoid colliding with it):
   - layers, panels and server modules move into `plugins/<name>/app/`;
   - the registry also scans plugin folders;
   - the catch-all API route goes in;
   - `LayerId` is opened up to whatever plugins register.
   Screenshots and the existing end-to-end specs must match before and after.
3. **Private plugins:**
   - the private GitHub repo is created (the owner creates it, or approves
     that we do) and checked out on the server;
   - Compose gets the extra build context;
   - the private tools and parcels move into `achd-tables` and `parcels`;
   - `check_public` gets its new rule.
4. **New plugins,** one source at a time with the owner:
   - `aircraft`, if an existing source's terms fit (research Oct 7), until
     the owner's own receiver arrives;
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
