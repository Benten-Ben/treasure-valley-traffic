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
| CPU | 8 vCPU | Tile builds, later vision. The host's CPUs lack AVX2, so prebuilt binaries that assume it need checking first. |
| RAM | 16 GB | PostGIS, builds, later vision |
| Disk | 100 GB | Map tiles (about 1.4 GB), terrain build scratch (about 12 GB, deletable), database (under 20 GB in year one). The camera archive (see ch. 11) needs its own disk later. |

## 10.5 What the prototype taught us (kept as lessons, not code)

- **robots.txt in the wild needs a lenient, RFC 9309 parser.** Seen so far:
  - byte-order marks (511);
  - blank lines inside groups (ACHD);
  - rules with no User-agent line (IEM);
  - `*` wildcards;
  - case variants;
  - 4xx responses, which mean "no rules".
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
  seed alongside OSM.
- **Attaching AADT** to intersections must skip interstate mainlines.
- **Crash data** available via ITD GIS currently ends in 2023.
