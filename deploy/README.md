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

## Toggled layers' tiles: the tvt_tiles login

The app's tiles for toggled layers (soils, crop fields, trails, ...:
`/api/<plugin>/tiles/<layer>/…`, `app/src/lib/server/mvt.ts`) go to anyone
who can open the map, so their cuts log in as **`tvt_tiles`**: a plain login
(no superuser, a member of no other role) that can't write and is granted
only core and the tile plugins' own schemas, never `restricted` or a private
plugin's schema (`private_<name>`, `city_trees`). The app's tile pool
connects with `TILES_DATABASE_URL`, which `docker-compose.yml` and
`compose.preview.yml` build from `TILES_DB_PASSWORD` in `.env`. It's a login
of its own rather than a role the app's connections switch to, because
those are `tvt`'s, a superuser, which can always switch back.

[`tvt_tiles.sql`](tvt_tiles.sql) makes the login and its grants, and ends
by checking what it can reach (PUBLIC's grants included). It's idempotent;
run it as `tvt` before the first toggled layer goes live, and again after
migrations that add a plugin schema (a deploy step, beside
`tvt_build.sql`'s). The first time, also generate a password on the server
(`openssl rand -hex 24`), put it in `.env` as `TILES_DB_PASSWORD`, set it
in the database, and recreate the app:

```bash
docker compose exec -T db psql -X -v ON_ERROR_STOP=1 -U tvt -d tvt -f - < tvt_tiles.sql
# First time only. The password goes from .env to the database without being
# typed or shown (it's hex, so the quotes are safe):
grep '^TILES_DB_PASSWORD=.' .env | cut -d= -f2- | sed "s/.*/ALTER ROLE tvt_tiles PASSWORD '&';/" \
  | docker compose exec -T db psql -X -q -v ON_ERROR_STOP=1 -U tvt -d tvt
docker compose up -d app    # and app-next while the preview is on
```

Until both are done, those tiles answer 500 (the login fails), logged in
`docker compose logs app`; nothing else in the app uses the login. A schema
added since the last run answers empty tiles with `x-tile-status: denied`.
To serve tiles from a new plugin's schema, add it to the file's
`tile_schemas` list; the app's unit tests check the list against the
registered layers.

## Heavy jobs and worker tests on the VM

Three small tools from [`bin/`](bin), installed in `/srv/tvt/work/bin` on the
VM (Python 3, standard library; tests in [`tests/`](tests), run on the VM
with `python3 -m unittest discover -s deploy/tests`). After a change, copy
them in by rename, so a job already running keeps its copy:
`install -m 755 deploy/bin/heavy /srv/tvt/work/bin/.heavy.new && mv -f /srv/tvt/work/bin/.heavy.new /srv/tvt/work/bin/heavy`
(the same for `worker-test` and `status`).

**`heavy`** runs a heavy job: a worker container over 1 GB or 1 CPU, any
production load, an image build, a `pg_dump`, a tile, imagery or lidar
build. It came out of the landscape sprint's plan (v3 §4.4) after an
uncapped build stalled the VM during the nightly camera roll-up on Oct 7.

```bash
/srv/tvt/work/bin/heavy --deadline 22:30 --runtime 90 --peak 3 "P2 decode (B2)" \
  docker run --rm --memory 3g --memory-swap 3g --cpus 3 -v ... tvt-worker python ...
/srv/tvt/work/bin/heavy --status      # the lock, the window, the roll-up, free disk, recent jobs
```

- **One at a time.** It takes `/srv/tvt/work/heavy.lock` exclusively and
  waits while another heavy job or a browser-spec run (which holds it
  shared) is going; while it waits, no new browser run starts. `-n` doesn't
  wait, `-w MIN` waits at most that long, also for a closed window to open.
- **Windows** (Boise time; the VM's clock is UTC): 06:00–23:15, and at
  night only once the camera roll-up (from 00:05) has finished, as both
  capture services' status files show, until 05:45. Nothing from 23:15
  until then: the roll-up needs the memory. A roll-up still going after
  06:00 holds day jobs too.
- **The deadline is enforced.** The job doesn't start past its deadline or
  when its stated runtime doesn't fit before it. At the deadline it gets
  SIGTERM (its whole process group, and every container labelled
  `tvt.heavy=<id>`), then SIGKILL a minute later. `heavy` adds the label to
  `docker run` and `docker compose run`; scripts that start containers
  themselves pass `--label "$HEAVY_LABEL"`.
- **What the deadline can't reach:** a command run with `docker exec`
  inside another container (a `pg_dump` in the database's). Killing the
  `docker exec` client leaves it running there, so it has to stop itself,
  for example under `timeout`, which the database image has:

  ```bash
  /srv/tvt/work/bin/heavy --deadline 17:00 --runtime 20 --peak 0 --cold 1 "pg_dump (deploy)" sh -c \
    'docker exec tvt-db-1 timeout -k 60 $((HEAVY_DEADLINE_EPOCH - $(date +%s))) pg_dump ...'
  ```
- **A planned VM restart.** The lead writes it in `/srv/tvt/work/MAINTENANCE`,
  on a line of its own: `restart: 2026-10-12 23:30` (Boise; a bare `23:30`
  means the next one). The deadline moves to 10 minutes before it. A note
  with no time, or with several and no `restart:` line, refuses every job.
- **Disk.** It starts only with 12 GB plus the job's stated peak free on
  `/` (an image build's peak is the image plus its build cache), and stops
  the job if `/` falls under 11 GB (the camera capture pauses under 10); it
  checks every 2 seconds. `--cold GB` is for a job that writes to the cold
  drive: it must be mounted, with room to spare (its mount is in the VM's
  `/srv/tvt/work/heavy.conf`, not here).
- **Caps.** A `docker run` without `--memory` is refused. `docker compose
  run` can't take a cap, so the service it runs needs `mem_limit` in the
  compose files the command reads; `heavy` checks with `docker compose
  config` and refuses one without. A production load at a deploy adds
  [`compose.load.yml`](compose.load.yml) (2 GB, 2 CPUs) on the command line:

  ```bash
  cd /srv/tvt/repo/deploy && /srv/tvt/work/bin/heavy --deadline 17:00 --runtime 30 --peak 1 \
    "roads load (deploy)" \
    docker compose -f docker-compose.yml -f compose.private.yml -f compose.load.yml \
      run --rm --no-deps -e DATABASE_URL ingest python3 -m ingest ...
  ```

  (`DATABASE_URL`, the load's role, comes from the shell: `heavy.log`
  records the command.) A `heavy` inside a heavy job runs at once, under
  that job's lock and deadline, with its caps still checked.
- Exit codes: the command's; 73 not enough disk; 75 not now; 123 stopped
  for disk; 124 stopped at the deadline (`heavy -h` has the rest).

**`worker-test`** runs unit tests in the worker image
([`ingest/Dockerfile.worker`](../ingest/Dockerfile.worker)), capped at
1 GB and 1 CPU with no network and the checkout read-only, and fails the
run when any test is skipped or none ran: in that image every dependency is
there, so a skip means a test didn't run. It's light, so it may run at any
hour, but at most two at once: a third waits for a slot.

```bash
/srv/tvt/work/bin/worker-test -C <checkout on the VM> discover -s basemap/ground -t .
```

**`status`** is the VM at a glance, which the lead runs at the start of each
session: free disk against `heavy`'s start and floor, the cold drive,
`heavy.lock`'s holder and how long it has held it, last night's camera
roll-up (going or finished, and the day's videos made, failed or missing),
a planned restart, and from the database the scheduled sources by state
(`ops.source_status`) and the builds that are marked, running or failed
(`ops.build_status`, migration 0021). It reads `heavy`'s rules from the
`heavy` beside it, and the database read-only (psql in its container, as
its owner, with a 10 s statement timeout); keys and passwords in errors are
hidden. A line that needs a look starts with `!`, and it exits 1 if any
does.

```bash
/srv/tvt/work/bin/status                                   # production (tvt-db-1, database tvt)
/srv/tvt/work/bin/status --db-container tvt-scratch-db --db tvt_s1   # a scratch copy
/srv/tvt/work/bin/status --no-db
```

The job table (each job's caps and window this sprint) and the work area's
disk notes are in the VM's `/srv/tvt/work/README.md`.

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

## Unmerged code and builds: the scratch database and tvt_build

Since Oct 11 (landscape sprint, F6), **unmerged code never touches the
production database**. A branch's migrations, loads and builds run against
`tvt-scratch-db`, a capped copy of production on its own internal network,
refreshed by hand. Builds and loads run as **`tvt_build`**, a role with caps
(`statement_timeout` 45 min, `temp_file_limit` 5 GB, `work_mem` 64 MB, one
parallel worker) and only the grants builds need, on scratch and on
production alike. Production gets new schemas through its migrations, then the
role's grants again, then its loads, each in its own capped container. How it
works, the grants and the commands: [scratch/README.md](scratch/README.md).

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
