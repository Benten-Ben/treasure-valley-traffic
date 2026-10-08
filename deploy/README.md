# deploy: running on the server

One **VM** on the owner's home server, running Docker Compose
([docs/10 §10.4](../docs/10-architecture.md#104-server-plan)). **Creating
the VM, or changing anything else on the host, needs the owner's explicit
go-ahead for that specific action** ([CLAUDE.md](../CLAUDE.md)). The owner
and the local helper session handle the host. Specifics of the owner's
network stay in private notes on the server, never in this repository.

| Service | Image | Role |
|---|---|---|
| `db` | `timescale/timescaledb-ha:pg17-ts2.30` | PostgreSQL 17 + TimescaleDB + PostGIS. Not exposed outside Compose. Checked on the server's CPU. |
| `ingest` | built from [`ingest/`](../ingest) and [`plugins/`](../plugins) | Applies [`db/migrations`](../db/migrations) and the plugins' migrations on start, then runs scheduled sources when due (ACHD's camera list, daily). One-off sources run only by hand. |
| `transit` | the ingest image | Records Valley Regional Transit's live feeds every 30 s: a raw archive in `ARCHIVE_DIR`, plus bus positions in the database |
| `wzdx` | the ingest image | Records ITD's work zones (WZDx feed on 511 Idaho) every 5 minutes: changed snapshots archived in `ARCHIVE_DIR`, every version in `raw.record`, cleaned rows in `evt.event` |
| `idaho511` | the ingest image | Polls the 511 Idaho API (key `IDAHO511_API_KEY` in `.env`), at most 8 calls a minute: events, advisories and truck restrictions into `evt.event`, message signs into `evt.sign_message`, road-weather readings into `obs.weather_reading`, everything versioned in `raw.record`; changed responses archived in `ARCHIVE_DIR/idaho511`. Rebuilds the regional capture list (`ARCHIVE_DIR/lists/regional-cameras.csv`) from the camera list |
| `cameras` | built from [`ingest/Dockerfile.cameras`](../ingest/Dockerfile.cameras) (Ubuntu 24.04, for the benchmarked SVT-AV1 1.7) | Fetches the key cameras ([`plugins/cameras/ingest/key_cameras.csv`](../plugins/cameras/ingest/key_cameras.csv)) from 511 Idaho every 50 s into `ARCHIVE_DIR/cameras/jpeg`, and after local midnight rolls each day into one AV1 video per camera in `ARCHIVE_DIR/cameras/video`. JPEGs are deleted after 2 days, once their video exists. Pauses below 10 GB free. The VM trims its disk daily (`/etc/systemd/system/fstrim.timer.d/daily.conf`), so deleted JPEGs free space in the server's shared storage. |
| `regional` | the cameras image | The same capture for ITD's road-weather camera views statewide plus Oregon DOT views in the regional ring, every 10 minutes, with their own daily videos. The list (`ARCHIVE_DIR/lists/regional-cameras.csv`) is rebuilt by `idaho511` and picked up without a restart |
| `app` | built from [`app/`](../app) | SvelteKit (adapter-node) on port 3000 inside the network. Stores calibration reference frames in `FRAMES_DIR`. |
| `web` | `caddy:2.11-alpine` | The single entry point: serves `/tiles/` from the basemap folder (with range requests), the camera video library at `/videos/` ([`library/`](library/index.html), with the videos read-only from `ARCHIVE_DIR/cameras/video`), and proxies everything else to `app`. Plain HTTP on `HTTP_PORT` for the LAN, and HTTPS (HTTP/2 and HTTP/3) on the VM's Tailscale name (`TVT_HTTPS_HOST`), with the certificate from the VM's Tailscale daemon |

## First-time setup (on the VM)

1. Install Docker Engine, the Compose plugin and git
   (`sudo apt install -y docker.io docker-compose-v2 git` on Ubuntu 24.04).
2. Put the code in `/srv/tvt/repo`: clone it, or push it there from a
   checkout. The server's repo takes pushes over the tailnet
   (`git config receive.denyCurrentBranch updateInstead` in it, so a push
   updates the checked-out files), so the server needs no GitHub access.
3. Create the environment file: `cp deploy/.env.example deploy/.env`, then
   set a database password generated on the server
   (`openssl rand -hex 24`). Never paste it into a chat session.
4. Create the frames and archive folders:
   `sudo mkdir -p /srv/tvt/frames /srv/tvt/archive && sudo chown 1000:1000 /srv/tvt/frames /srv/tvt/archive`.
   The archive holds raw feeds that can't be fetched again later, so back it up.
5. Put the map tiles in `TILES_DIR`: build them (see [basemap/](../basemap)),
   or copy a finished build ([below](#tiles-copied-not-built-on-the-server)).
   They're too big for GitHub, so they're built on our side or copied, never
   committed.
6. Put the private reference files in `PRIVATE_DATA_DIR` (they aren't in
   this repository).
7. Start everything: `docker compose -f deploy/docker-compose.yml up -d --build`.
8. Link the 511 camera views to cameras (one-off, by hand):
   `docker compose -f deploy/docker-compose.yml exec ingest python3 -m ingest run idaho511_views_oneoff`.
9. Open the site on port 8080.

### Tiles: copied, not built on the server

On Oct 5 the pilot built the tiles in the cloud session and copied the
finished build (about 1.2–1.4 GB then) to the VM with `rsync` over
Tailscale, which resumes if the link drops, instead of building them on the
server:

- It saves about an hour of heavy CPU on the home server.
- The VM then needs no GDAL, Go (for `pmtiles`) or DuckDB, which also
  sidesteps most questions about whether those tools run on the server's
  CPU. They get installed later, when the map needs a refresh.
- The cloud session downloads at 25–40 MB/s, so building there was faster
  than setting up GDAL, `pmtiles` and the repo on the owner's laptop. (The
  owner had offered: "I can do things on my local machine if it would be net
  faster".)
- The copy itself is slow: about 2.5 MB/s through the tailnet relay.

## HTTPS on the tailnet

Browsers fetch map tiles about 6 at a time over plain HTTP/1.1, and all at
once over HTTP/2. To serve the site over HTTPS on the tailnet (owner OK,
Oct 6, 2026):

1. In the Tailscale admin console, switch on HTTPS certificates (DNS page).
   Certificate names are published in public certificate-transparency logs.
2. Set `TVT_HTTPS_HOST` in `deploy/.env` to the VM's full Tailscale name.
3. `docker compose -f deploy/docker-compose.yml up -d web`, then open
   `https://<that name>/`.

Caddy gets and renews the certificate through the VM's Tailscale socket,
which the `web` service mounts.

## Remote access

Over Tailscale only: the site and SSH are reachable from the owner's own
devices. Don't forward any ports on the home router. The site has no login
yet, so it must not be exposed to the internet.

No login also means anyone on the owner's home network or tailnet can edit
or overwrite a camera's calibration (noted Oct 5, when the calibrator went
live). Calibrations are hand work, and they live only in the database on the
server's disk: nothing is backed up yet (pending in
[DECISIONS](../docs/DECISIONS.md)). Both argue for settling backups and,
eventually, a login or some edit protection for calibrations.

## Updating

```bash
# push main to /srv/tvt/repo from a checkout (the server has no GitHub access), then:
cd /srv/tvt/repo/deploy
docker compose up -d --build <services>
```

Run Compose from `deploy/` **without `-f`**, so it reads `COMPOSE_FILE` from
`deploy/.env` and includes the overrides that are switched on (live images,
the preview, private plugins). With an explicit `-f`, the overrides are skipped.
[`compose.private.yml`](compose.private.yml) gives the ingest service the
private plugins (docs/15 §15.3), from `PRIVATE_PLUGINS_DIR` (default
`/srv/tvt/plugins-private`), read-only.

### Checking the app by hand

SvelteKit refuses cross-site requests, and `curl` sends no browser `Origin`
header, so a bare `curl -X POST` to the app's API is rejected (Oct 5 smoke
test). Send what the app's own page sends:

```bash
curl -X POST http://localhost:8080/api/views/<id>/frame \
  -H "Origin: http://localhost:8080" -H "Content-Type: application/json" -d '{}'
```

That call writes: it keeps the view's newest frame as its calibration
reference in `FRAMES_DIR`, so try it on a view nobody has calibrated.

## Loading an OpenStreetMap extract (by hand)

Geofabrik's robots.txt disallows scripted downloads, so OpenStreetMap comes
in only from a file the owner downloads in a browser, loaded by hand; there
is no schedule ([DECISIONS](../docs/DECISIONS.md), Oct 6; what's kept:
[ch. 12](../docs/12-database-schema.md), [plugins/roads](../plugins/roads/README.md)).
The steps (Builder D's first-run notes, Oct 6):

1. Rebuild the ingest image, which carries `osmium-tool` (about 4 MB more:
   osmium-tool 1.5 MB plus Boost program_options about 2.4 MB):
   `docker compose up -d --build ingest` from `deploy/`. ACHD's roads
   (`achd_roads`) must already be loaded, so matching has segments.
2. Check it: `docker compose -f deploy/docker-compose.yml exec ingest osmium --version`
   (1.18 on Oct 6).
3. The owner downloads `idaho-latest.osm.pbf` **and** its `.md5` from
   [Geofabrik's Idaho page](https://download.geofabrik.de/north-america/us/idaho.html)
   in a browser, and puts both in `${ARCHIVE_DIR:-/srv/tvt/archive}/osm/inbox/`,
   owned by uid 1000.
4. Load: `docker compose -f deploy/docker-compose.yml exec ingest python3 -m ingest osm-load --inbox`
   (the old `python3 -m ingest.osm_load` still works). `--file PATH` loads a
   file from anywhere instead.

What a load does:

- It takes the newest file in the inbox and checks it against the `.md5`
  beside it.
- An extract with the same MD5 as last time is skipped, unless `--force`.
- Afterwards the file moves to `$TVT_ARCHIVE/osm/` (renamed with the date
  and the start of its MD5) and the last two extracts are kept. Pruning
  never removes the file just loaded, and reloading an archived file
  refreshes its time, so it counts as the newest.
- **Shrink guard:** when 1,000 or more ways are active, a load that brings
  fewer than half of them refuses to retire the rest. Check the file, or
  pass `--allow-shrink`.

Timing at server scale, estimated Oct 6:

| Step | Time |
|---|---|
| Download (in a browser) | 10–60 s |
| osmium cuts the extract to the valley box | 15–30 s |
| Tag filter, export and parse | 10–15 s |
| Store | about 5 s |
| Match to ACHD's segments | about 47 s (21 s before the turn-bay rule) |
| **Whole load** | **about 1.5–2 minutes** |

Disk: about 250 MB of archived extracts, plus about 150 MB of temporary
files while processing.

Expected rows, estimated Oct 6 from the May 2026 Overpass counts ⚠️, beside
the first real load on Oct 7 (Geofabrik's Oct 5 extract, 129 MB;
[SOURCES](../docs/SOURCES.md#openstreetmap-first-load-oct-7)). Where they
differ, the Oct 7 load is the fact; the Oct 6 numbers were sizing guesses.

| Table | Estimate (Oct 6) | First load (Oct 7) |
|---|---|---|
| `core.osm_way` | about 13,500 (7,823 major ways + about 5,600 other ways with lanes) | 13,917 (10,614 with `lanes`) |
| `core.osm_lane` | about 40,000–50,000 | 25,701 |
| `core.osm_node` | about 2,800 (752 intersection signals, about 1,709 crossing signals, 342 level crossings, less overlaps) | 767 signals, 1,742 crossing signals, 345 level crossings |
| `core.segment_match` | about 6,000–9,000 | 14,054 ACHD segments matched, plus 2,222 turn-bay matches |
| `raw.record` | about 16,300 rows (5–8 MB) on the first load, then about 150–500 new versions (60–200 KB) a week | not recorded |

## Preview of main's app (UI v2)

While UI v2 lands a wave at a time (docs/14 §14.10),
[`compose.preview.yml`](compose.preview.yml) runs `main`'s app as `app-next`
beside the live app:
- the live app keeps the LAN port and the tailnet HTTPS name;
- the preview is on LAN port 8081 and on port 8444 of the tailnet name.

The live `app` stays pinned to the image tagged `tvt-app:live`, so a rebuild
can't ship the unfinished UI. Both apps share the database, frames and tiles.
The override's header has the commands to switch it on, update it and retire
it at a checkpoint.

## Deploying UI v2 (runbook)

The steps for putting UI v2 ([docs/14](../docs/14-ui-v2.md)) live, from
§14.11 "After deploy". The lead runs them, only with the owner's OK for that
deploy. Every gate question was answered on Oct 6 (§14.14), so nothing is
held back: migrations 0006 and 0007 are in `db/migrations/` (Q4), live
images are on (Q5), and the hillshade comes from the terrain source (Q7,
the default in the app). Run Compose from `deploy/` without `-f`
([Updating](#updating)).

0. **Pick the window.** Never between 00:00 and 04:00 local: the daily AV1
   roll-up runs in `cameras` and `regional` from 00:05, its encodes take 2–3
   hours, and restarting a capture service mid-roll-up kills it. Before
   step 3, also check that neither is still rolling up: their status files
   say so once the new capture code runs
   (`grep -l '"rolling_up":true' $ARCHIVE_DIR/cameras/status/*.json` finds
   none), and until then their logs show a "roll-up finished" (or
   "stopped") line after the last start
   (`docker compose logs --since 6h cameras regional | grep roll-up`).
   Heavy one-off jobs on the VM (the terrain re-encode below) run outside
   that window too, with a memory cap: an uncapped build stalled the VM on
   Oct 7 ([DECISIONS](../docs/DECISIONS.md)).
1. **Back up the database** (and check the free space first, `df -h`):
   `docker compose exec -T db pg_dump -U tvt -Fc tvt > ~/tvt-before-ui-v2-$(date +%F).dump`.
   Nothing else backs the calibrations up yet.
2. **Migrations.** Push `main` to the server's repository, then
   `docker compose up -d --build ingest`. The ingest service applies
   `db/migrations/` (0006 `core.transit_ribbon` and `color_pinned`, 0007
   `obs.vehicle_progress`) and the plugins' migrations (the camera
   `provider` column, `cameras/0001`) on start, before the app needs them.
   Check: `docker compose logs ingest | grep -i migrat`.
3. **The web server, the app and the services that changed.**
   - Glyphs precompressed, so Caddy serves them gzipped (about −90 KB on a
     first view): `basemap/build.sh --precompress-glyphs` on the tiles
     folder (seconds). The Caddyfile already sends `manifest.json` with
     `no-cache` and serves the `.gz` files.
   - Live images: add `compose.live-images.yml` to `COMPOSE_FILE` in
     `deploy/.env`. Start the capture services before the app, so they
     create `cameras/status` (a folder Docker creates for a bind mount
     belongs to root, and the capture services can't write in it).
   - Retire the preview, since `main` becomes the live app: take
     `compose.preview.yml` out of `COMPOSE_FILE` and
     `docker compose rm -sf app-next`. Its header has the details.
   - Then `docker compose up -d --build cameras regional transit` (capture
     status files, and the online matcher after each stored batch of bus
     positions), and `docker compose up -d --build app web`.

   Until step 4 finishes, `/api/transit/network` serves each route's plain
   shapes (`n = 1`, `bundled: false`), so Transit isn't blank. It stays that
   way if the ribbon build fails.
4. **Route colors and ribbons.** First the dry run, for the owner:
   `docker compose exec ingest python3 -m ingest transit-ribbons --dry-run`
   prints every color change (old → new). The default mode is the owner's
   Q3 answer, the one-time rebalance. On the local copy of the server's data
   (Oct 7) it changed 7 routes (8, 16, 21, 28, 29, 42 and R1) with 0
   clashes, 255 segments, at most 11 routes on one street, in under 3 s.
   Then build: `docker compose exec ingest python3 -m ingest run vrt_gtfs`
   (the daily run, which also rebuilds the ribbons), or
   `python3 -m ingest transit-ribbons` alone.
5. **Backfill playback:**
   `docker compose exec ingest python3 -m ingest transit-progress --hours 24`.
   It takes the matcher's advisory lock, so the transit stream skips
   matching meanwhile and catches up afterwards; positions keep being
   recorded throughout.
6. **Check:**
   - `curl` (with the `Origin` header, [above](#checking-the-app-by-hand))
     `/api/meta`, `/api/cameras/live?views=<a few view ids>` and
     `/api/transit/tracks`;
   - from the laptop, the smoke specs against the tailnet HTTPS address:
     `cd app && TVT_E2E_URL=https://<tailnet name> npx playwright test tests/e2e/boot.spec.ts`
     (every request same-origin, no console errors, at both screen sizes);
   - S1, S2 and S6 for real on the owner's laptop:
     `node scripts/perf.mjs --real --channel chrome --url https://<tailnet name> --scenarios S1,S2,S6`;
   - once a full weekday hour has been recorded with the online matcher, the
     hour-long playback checks on the server's data
     (`python3 -m ingest transit-progress --from <hour start> --to <hour end> --report`):
     90% or more of labeled-bus steps along or still, no along step over
     30 m/s and no backward motion over 20 m, which the report prints; and
     under 2% of bus-seconds waiting at the 90 s delay, from `seen_at` with
     backfilled rows left out, which no tool computes yet (a query to write
     then; [DEFERRED](../docs/DEFERRED.md)).
7. **The owner saves one calibration** with the new calibrator (Calibrate
   in a camera's window). Then `/v1/calibrate/[id]` and `lib/v1/` can go.

**Terrain as WebP** (WP17, owner OK Oct 6; optional, any later day): the
re-encoded terrain is about 45% smaller, so the first load drops by about
another 1 MB ([basemap/](../basemap/README.md#switching-terrain-to-webp)).
Run `basemap/terrain_reencode.py` where GDAL's Python bindings and the
`pmtiles` CLI are installed, put the new `terrain-webp-<date>.pmtiles` and
the manifest copy in the tiles folder, keep the old manifest, and move the
copy into place. The app picks it up on the next load (`manifest.json` is
`no-cache`); restoring the old manifest goes back.

**Rolling back:** the previous image is still tagged (`tvt-app:live`, if the
preview was on). Put `compose.preview.yml` back in `COMPOSE_FILE` and
`docker compose up -d app` to serve it again. The new tables are additive
(the old app ignores them), and the route colors can be set back from the
dry run's list.
