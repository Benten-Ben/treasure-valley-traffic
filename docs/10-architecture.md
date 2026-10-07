# 10. Platform architecture (proposed)

How we plan to build our own "god's-eye view" of the valley's road
network: an owned base map, live and historical data layers, and analysis.
This is a **proposal under discussion**. Decided items are marked ✅, open
ones ❓. The decision log is in [DECISIONS.md](DECISIONS.md).

The current `tvt/` package is a **throwaway prototype**. It proved the data
sources and some patterns, but it isn't the foundation. The real platform
will be designed and built step by step with the project owner's sign-off.

---

## 10.1 Goals and principles

- **A view of the road network, not of people.** Infrastructure and
  conditions: signals, volumes, work zones, transit, weather, crashes. No
  tracking or identifying individuals.
- **Only data we're allowed to use.** Respect robots.txt (RFC 9309) and
  terms. Prefer official APIs and publisher-designated feeds. See
  [chapter 8](08-data-inventory.md).
- **Owned and open:** a self-hosted base map and open-source software, with
  no API keys or vendor lock-in where avoidable.
- **History matters:** keep time series so we can measure change and do
  before/after comparisons.
- **Core vs. validation:**
  - **Core sources** (volumes, crashes, transit GPS, events, timing data
    when we get it) drive the analysis.
  - **Validation sources** (cameras) confirm or challenge what the core
    data suggests.

## 10.2 Proposed stack

| Layer | Choice | Status |
|---|---|---|
| Front-end framework | **SvelteKit** (TypeScript) | ✅ owner's preference |
| Map rendering | **MapLibre GL JS** (2.5D: tilt, terrain, 3D building extrusions) + **deck.gl** overlay for heavy layers (bus trails, crash hexbins, time animation) | ✅ v1 is 2.5D |
| True 3D (later, optional) | CesiumJS for LiDAR point clouds / 3D Tiles | ✅ not in v1 |
| Basemap | Self-hosted **Protomaps PMTiles** extract (OpenStreetMap), built by `basemap/build.sh` | ✅ scaffolded; build waits on network access |
| Terrain | Terrain-RGB tiles built from **USGS 3DEP 1 m DEM** | ❓ recommended |
| Imagery | **NAIP 2023** (public domain). ACHD 3-inch as an on-request overlay pending terms. | ❓ recommended |
| Buildings | **Overture** footprints with heights. Boise 3D buildings if terms allow. | ❓ recommended |
| Database | **PostgreSQL + PostGIS + TimescaleDB** (`timescaledb-ha` image) | ✅ owner approved |
| Analysis side tool | DuckDB (+ spatial) for Overture/GeoParquet and heavy one-off analysis | ❓ recommended |
| Vector tile server | Martin (serves tiles from PostGIS); static PMTiles for big static layers (built with tippecanoe) | ❓ recommended |
| Ingestion | **Python**, rebuilt cleanly from the prototype's lessons; simple scheduling (systemd timers or a small scheduler) | ❓ language agreed in practice; design pending |
| Camera vision | PyTorch with a **permissively licensed** detector (Apache/BSD), not AGPL | ❓ recommended |
| Deployment | **Owner's home server**: one dedicated VM running Docker Compose, reached over Tailscale | ✅ running since Oct 5, 2026 |
| Remote access | Tailscale or WireGuard; no open ports | ❓ recommended |
| Key/licensing posture | Open-only, no-key stack (no Google 3D, Esri or MapTiler) | ✅ owner approved |

### Alternatives considered (Oct 5, 2026)

The options the pilot laid out in the stack discussion, and why each choice
went the way it did. The owner's answers are in
[DECISIONS.md](DECISIONS.md).

| Question | Options weighed | Chosen | Why |
|---|---|---|---|
| Where it runs | The owner's laptop; a home server or mini PC; a small rented server (about $5–20 a month) | The owner's home server, one VM | Live feeds (buses every 30 s, cameras) need something always on. The map on its own could be hosted as a static site, but the live layers can't. The owner picked the home server: "more in that machine's resource capacity than this laptop". VM vs. container: see §10.4. |
| Map rendering | **MapLibre** (2D/2.5D: tilted views, terrain, extruded buildings) + deck.gl; or **CesiumJS** (true 3D globe, point clouds) | MapLibre, 2.5D first | MapLibre covers terrain, 3D buildings, bus trails and time animation. Cesium is worth adding only if we want LiDAR point clouds, and 3D-first would also mean storing 160 GB+ of raw point clouds (§10.4). |
| Basemap hosting | A self-hosted single map file (Protomaps) or a commercial tile service | Self-hosted | No keys, no limits, fully ours |
| Database | **PostgreSQL + PostGIS (+ TimescaleDB)**; or serverless **DuckDB + data files** | PostGIS as the core; DuckDB only as a side tool | DuckDB is simpler (no server) and great for analysis, but weaker for live layers and many joins, which is what this platform mostly does. It stays for heavy one-off work such as Overture extracts. |
| App front end | React + TypeScript; Svelte/SvelteKit; plain JavaScript | SvelteKit | The pilot recommended React + TypeScript for having the largest map-app ecosystem; the owner prefers Svelte/SvelteKit. |
| Camera vision | A permissively licensed detector (Apache/BSD) with PyTorch; or Ultralytics YOLO (AGPL) | Permissive | So licensing never limits what we do later |
| Keys and licenses | Google Photorealistic 3D Tiles, Esri or MapTiler basemaps; or open, key-free data only | Open-only | Billing, keys and terms that forbid caching or analysis; see [ch. 9 §9.7](09-base-map-data.md#97-3d-tiles-and-basemap-tiles) |

## 10.3 Data flow

```
 public sources ──► ingestors (Python, robots/terms-aware, per-source schedules)
                        │
                        ▼
                 PostgreSQL + PostGIS + TimescaleDB
     features (inventories) · events (lifecycles) · time series · transit GPS
                        │
          ┌─────────────┼───────────────────┐
          ▼             ▼                   ▼
   aggregation jobs   Martin vector     analysis (DuckDB,
   (per intersection, tiles (live)      notebooks, reports)
   per corridor)        │
          │             ▼
          └────► SvelteKit app + MapLibre/deck.gl
                 base: PMTiles (OSM) + terrain (3DEP) + NAIP + buildings
```

Camera images follow a separate path; see [chapter 11](11-camera-validation-layer.md).

## 10.4 Server plan

**Decided and running (Oct 5, 2026):** one dedicated **VM** (Ubuntu 24.04)
on the owner's home server, running Docker Compose with
PostGIS/TimescaleDB, the ingestors, the SvelteKit app and a reverse proxy
([deploy/](../deploy/README.md)). It's reached over Tailscale only, with
no ports open to the internet. Specifics of the owner's network and
hardware stay in private notes on the server.

Why a VM rather than a container (LXC):

- Docker inside an unprivileged LXC needs nesting/keyctl and can misbehave
  with some storage backends.
- GPU passthrough, if one is ever added, is cleaner to a VM.
- Snapshots and backups are simple.

| Resource | Now | Driven by |
|---|---|---|
| CPU | 8 vCPU | Tile builds, later vision. Prebuilt binaries that assume newer CPU features need checking first (details in the private notes). |
| RAM | 16 GB | PostGIS, builds, later vision |
| Disk | 100 GB | Map tiles (about 1.4 GB), terrain build scratch (about 12 GB, deletable), database (under 20 GB in year one). The camera archive (see ch. 11) needs its own disk later. |

### The original sizing (Oct 5, before the VM was made)

The pilot's first recommendation, before it had seen the host:

| Resource | Baseline | Comfortable |
|---|---|---|
| CPU | 4 cores | 8 cores |
| RAM | 16 GB | 32 GB |
| Disk | 200 GB | 500 GB+ |

Disk by use, as estimated then:

| Use | Estimate |
|---|---|
| Database | Under about 20 GB in year one |
| Elevation data | About 32 GB |
| Map tiles | A few GB |
| Camera images, 30-day retention | About 30 GB sampling peaks only; about 400 GB for all cameras all day |
| Raw LiDAR point clouds | 160 GB or more, only if 3D-first (dropped with the 2.5D decision) |

A small vehicle-detection model on the CPU was estimated to handle about 40
cameras a minute; a GPU matters only at full scale.

The VM as made has the comfortable CPU count, the baseline RAM and **half
the baseline disk** (100 GB). Camera storage has since moved to a video
archive with its own numbers ([ch. 11 §11.5](11-camera-validation-layer.md#115-storage)).

### Scaling the camera work: a second worker (design, not built)

Today the VM encodes the daily camera videos itself, four encodes side by
side at low priority until done, so it isn't limited to an overnight
window ([ch. 11 §11.5](11-camera-validation-layer.md#115-storage)). Whether
it ever needs more CPU is a pending owner decision
([DECISIONS.md](DECISIONS.md), "More CPU for the camera videos"). If a
second machine ever takes on camera work (encoding, or vehicle detection on
its GPU), the helper's capacity report (Oct 5) set these rules, and the
pilot agreed:

- **Pull, not push.** The worker asks for a camera-day job only when it's
  ready. This comes from an earlier multi-machine test (details in the
  private notes): a central dispatcher sent work to any node whose
  `/health` answered, a node passed `/health` while still loading and was
  sent work that then failed, and a single good health poll put a node
  straight back into rotation. "Healthy is not ready."
- **Jobs are leases.** If the worker vanishes mid-job, the lease expires
  and the VM does that camera-day itself. The worker is an accelerator,
  never a dependency.
- **Verify before trusting.** The VM decodes each returned video and checks
  its frame count before marking the job done. Frames (JPEGs) are deleted
  only by the normal retention (a week at the time), never on the worker's
  say-so.
- **Idempotent jobs.** Re-running a camera-day overwrites cleanly.

Data volume at 34 cameras: about 4 GB a day to the worker and 1 GB a day
back, a few minutes of transfer.

Testing before relying on a worker:

1. A timing test on the same frozen frames, comparing its ffmpeg and
   SVT-AV1 versions with the VM's.
2. A multi-hour soak at full load (stability, thermals).
3. **Shadow mode for a week:** the worker encodes copies while the VM still
   does the real work; compare frame counts, sizes and quality.
4. **Fault drills:** cut the worker's power mid-job and confirm the lease
   expires and the VM redoes it; reboot it and confirm it takes work only
   once it's ready.
5. Only then switch to "worker first, VM as fallback".

**Verdict (pilot, Oct 6):** not needed for encoding now. Build the job
queue pull-based from the start, so a worker can join later without a
redesign; a worker's GPU is the interesting part, for vehicle detection.

## 10.5 What the prototype taught us (kept as lessons, not code)

- **robots.txt in the wild needs a lenient, RFC 9309 parser.** Seen so far:
  - byte-order marks (511);
  - blank lines inside groups (ACHD);
  - rules with no User-agent line (IEM);
  - `*` wildcards;
  - case variants;
  - 4xx responses (including 401 and 403), which mean "no rules";
  - a missing robots.txt answered with an HTML page and status 200, which
    we also read as "no rules".

  On the first smoke run of the prototype's 12 ingestors (Oct 5), its
  robots check blocked two sources: ACHD's signal assets on ArcGIS Online
  (`services2.arcgis.com`) and VRT's GTFS-realtime feeds on Amazon
  S3 (`s3.amazonaws.com/etatransit.gtfs`). After reading both hosts' files
  and fixing the parser, both ran. Which quirk each host showed wasn't
  recorded, and the ingest README doesn't yet note robots status for VRT's
  S3 host.
- **"Couldn't read robots.txt" isn't "robots.txt says no".** A 5xx or a
  network error counts as disallowed for now (RFC 9309), but it's retryable:
  `ingest/http.py` raises `RobotsUnavailable`, a subclass of
  `RobotsDisallowed`, and doesn't cache the result, while a real disallow
  still stops the request. This came up on Oct 5 when ACHD's GIS server
  dropped connections from the cloud sandbox while we loaded road
  centerlines; the roads source also got retries for dropped connections.
  Readable files are cached, and the long-running streams read them
  again from time to time (RFC 9309 allows caching for up to 24 hours).
- **Inventories, events and time series behave differently.**
  - Inventories need "current vs. history".
  - Events need lifecycles (first seen / last seen / active).
  - Time series need upserts.
- **Source quirks to design for:**
  - ACHD's camera layer lists 4 cameras twice and has a layer-wide
    timestamp, not a per-camera one.
  - ITD AADT IDs collide unless you key on the object ID.
  - WZDx mixes geometry types.
- **ACHD's 2022 signal points cluster into 453 intersections** at 60 m,
  matching ACHD's 465 (2022) closely. That makes them a good intersection
  seed alongside OpenStreetMap.
- **Attaching AADT** to intersections must skip interstate mainlines.
- **Crash data** available via ITD GIS currently ends in 2023.

## 10.6 What the Oct 6 data builds taught us

Every review of the four data-side builders' work (signals, lanes, COMPASS
data, OpenStreetMap; see §10.7) found real defects:

| Builder | What review found |
|---|---|
| A: signals, crossings, intersections | Its ArcGIS paging could skip and duplicate features. |
| B: lanes (ITD's road inventory, ACHD's Master Street Map, COMPASS's centerline) | Six defects. No guard against a short or empty download, which would have retired all of a source's lanes for up to a month; a failed match left stale for a month; one-way and shared-route stretches misread; a one-lane road read as "0 lanes plus a turn lane"; a pager that fell into slow fetches when a server answers fewer rows per page than asked. |
| C: COMPASS crashes, counts, growth, congestion | Four medium defects. An incomplete read could wipe current data while the run logged success; one failing layer re-downloaded the whole crash set every hour; some transient errors weren't retried; paging was unstable. |
| D: OpenStreetMap | A scripted Geofabrik download was still reachable from code, though Geofabrik's robots.txt disallows it; `run all` broke when the OSM source failed. |

The rules that came out of them, for every ingestor:

- **The snapshot guard.** A snapshot source refuses an empty snapshot, or
  one under half its active rows, before writing anything; the fetch is
  logged as failed and nothing is retired (`check_snapshot` in
  `ingest/db.py`, first written for A's signal devices). A partial read must
  not count as a republish either.
- **Match inside the fetch.** A source that matches onto ACHD's segments
  does it inside the fetch transaction (`db.Fetch`), so a failed match
  rolls the store back and the run is retried. `stale()` compares a source's
  own records with its last match.
- **One failure doesn't stop the rest.** A failing matcher is rolled back
  and logged while the others run, with failures reported at the end, and
  `run all` carries on past a failing source.
- **Paging ArcGIS layers** (the shared reader, `ingest/arcgis.py`):
  - page in order of each layer's real unique ID;
  - a listed ID below the highest one an answer returns is fetched by ID;
    IDs above it stay pending;
  - when an answer is cut, shrink the batch to the server's page size (a
    synthetic 12,150-row case takes 13 range requests and none by ID);
  - a by-ID request that returns none of its IDs fails the fetch;
  - retry `IncompleteRead` and unparseable JSON like network errors;
  - COMPASS reads 1,000 IDs a request.
- **Don't redo work.** Skip layers that already succeeded, or haven't
  changed since the last pull.
- **A source robots.txt disallows has no download code at all.** The OSM
  source loads only files the owner downloads by hand, and a test asserts
  it has no network code and no schedule.

## 10.7 How data-side builds are run

The pattern the network and COMPASS build used (Oct 6–7), worth reusing. The UI
build's version, with file ownership and waves, is in
[ch. 14 §14.10](14-ui-v2.md#1410-work-packages).

1. **Shared schema first.** The lead wrote the shared migration
   (`0011_network_sources.sql`) as a fixed contract and tested it on a
   clone of `tvt_template`, which already held ACHD's 38,727 road segments
   to match against.
2. **Parallel builders, isolated.** Four builders (A signals, crossings and
   intersections; B lanes; C COMPASS data, with its own migration 0012; D
   OpenStreetMap) each worked in their own git worktree with their own
   database clone (`tvt_net_a` to `tvt_net_d`), using a local test-database
   password saved outside the repo.
3. **Real sources once, full pulls on the server.** Each builder ran its
   sources once against the real sources into its own database, with
   responses cached. D, which the cloud sandbox couldn't test against
   Geofabrik, was built against made-up test data. Full pulls happen only on
   the server after deploy.
4. **Merge between the UI build's waves**, on an integration branch.
   Parallel builders collided on shared files: A and B each wrote
   `ingest/arcgis.py`, which B then folded into one shared reader; the
   registry and README conflicts were both sides adding, so both were kept.
5. **Dry-run migrations on the server's real database** inside
   `BEGIN … ROLLBACK` before deploying (0011 and 0012, then 0016–0018).
   That was the first run of the TimescaleDB part (`obs.crash` as a
   hypertable). `db/migrate.py` refuses an edited migration, so a fix to one
   already merged is a new migration (0018 drops and recreates the lane
   views).
6. **Refactors prove they changed nothing.** For the ingest-plugin
   refactor ([ch. 15 §15.6](15-plugins.md#156-refactor-plan)), the
   acceptance test was a byte-identical source listing plus all tests (360);
   the new images were built on the server without restarting anything and
   smoke-tested in throwaway containers before the services switched.
