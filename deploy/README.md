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
| `cameras` | built from [`ingest/Dockerfile.cameras`](../ingest/Dockerfile.cameras) (Ubuntu 24.04, for the benchmarked SVT-AV1 1.7) | Fetches the key cameras ([`plugins/cameras/ingest/key_cameras.csv`](../plugins/cameras/ingest/key_cameras.csv)) from 511 Idaho every 50 s into `ARCHIVE_DIR/cameras/jpeg`, and after local midnight rolls each day into one AV1 video per camera in `ARCHIVE_DIR/cameras/video`. JPEGs are deleted after 2 days, once their video exists; videos older than a week move to the cold drive ([below](#older-camera-videos-on-the-cold-drive)). Pauses below 10 GB free. The VM trims its disk daily (`/etc/systemd/system/fstrim.timer.d/daily.conf`), so deleted JPEGs free space in the server's shared storage. |
| `regional` | the cameras image | The same capture for ITD's road-weather camera views statewide plus Oregon DOT views in the regional ring, every 10 minutes, with their own daily videos. The list (`ARCHIVE_DIR/lists/regional-cameras.csv`) is rebuilt by `idaho511` and picked up without a restart |
| `app` | built from [`app/`](../app) | SvelteKit (adapter-node) on port 3000 inside the network. Stores calibration reference frames in `FRAMES_DIR`. |
| `web` | `caddy:2.11-alpine` | The single entry point: serves `/tiles/` from the basemap folder (with range requests), the camera video library at `/videos/` ([`library/`](library/index.html), with the videos read-only from `ARCHIVE_DIR/cameras/video`, and the older days through their links to the cold drive), and proxies everything else to `app`. Plain HTTP on `HTTP_PORT` for the LAN, and HTTPS (HTTP/2 and HTTP/3) on the VM's Tailscale name (`TVT_HTTPS_HOST`), with the certificate from the VM's Tailscale daemon |

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
plugin's schema (`private_<name>`, `city_trees`), and never the internal
tables on the file's `never_tables` list, inside those schemas
(`roads.bike_facility_note`, ACHD's free-text field notes). The app's tile pool
connects with `TILES_DATABASE_URL`, which `docker-compose.yml` and
`compose.preview.yml` build from `TILES_DB_PASSWORD` in `.env`. It's a login
of its own rather than a role the app's connections switch to, because
those are `tvt`'s, a superuser, which can always switch back.

[`tvt_tiles.sql`](tvt_tiles.sql) makes the login and its grants, and ends
by checking what it can reach (PUBLIC's grants included). It's idempotent;
run it as `tvt` before the first toggled layer goes live, and again after
migrations that add a plugin schema or a table on `never_tables` (a deploy
step, beside `tvt_build.sql`'s). Until it runs again, a new table in a
granted schema is readable by the default privileges, a `never_tables` one
included. The first time, also generate a password on the server
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
  The trees plugin's migration 0003 (removing the City-derived rows) has its
  own order of rebuilds, deploy and loads:
  [its runbook](../plugins/trees/README.md#runbook-migration-0003-on-production).
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
(`ops.build_status`, migration 0021), and the last run of `cold-videos`
([below](#older-camera-videos-on-the-cold-drive)). It reads `heavy`'s rules from the
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

### The tiles folder's locks

These commands take a lock before they rewrite the served tiles folder or its `manifest.json` (`basemap/lock.py`; #291):
the landscape bake and its rollback (`bake.py rollback --tiles`), the ground's switch-in (`tilewrite.py assemble
--tiles`), the ground's flat entry (`ground.py flat --tiles`; both ground commands go through `tiles.py`'s manifest
update) and `basemap/build.sh`. The older layer scripts (`imagery.py`, `imagery_county.py`, `buildings.py`,
`terrain.py`) take no lock, so they are not run against the served folder. The lock files live in one folder of their
own, never in the served tiles folder:

- **The folder** is `/srv/tvt/work/locks`, made group-writable with the setgid bit (mode 2775) so every job user can
  create files in it. `landscape.lock` and `manifest.lock` may be made in it ahead of time with mode 664;
  `basemap/lock.py` also creates a missing file with 664 itself, so this is only a fallback.
- **`TVT_TILES_LOCK_DIR=/srv/tvt/work/locks`** is set by each caller, not by `heavy` (which only adds its label). A
  worker container that writes the tiles or the manifest gets `-e TVT_TILES_LOCK_DIR=/srv/tvt/work/locks -v
  /srv/tvt/work/locks:/srv/tvt/work/locks`: the checkout is mounted read-only there, so without the variable the job
  stops at the start (`lock.ensure()` says which folder is not usable). The landscape bake's command
  ([basemap/landscape/README.md](../basemap/landscape/README.md#commands)) and the ground's switch-in carry both; so
  does the G1a job script (`w.sh`, in the VM's work area, outside this repository).
- **The path is the same inside and out** because a container and a host run must lock the same files, and they do
  only when the folder is one bind mount seen at one path.
- **A host-side run** sets the variable in its environment. That covers `bake.py rollback --tiles` and `ground.py flat
  --tiles` as much as the build: without it the lock lands in the checkout's `data/locks`, where a running bake does
  not see it and both can rewrite the landscape entry. For example `TVT_TILES_LOCK_DIR=/srv/tvt/work/locks
  TILES_DIR=/srv/tvt/tiles basemap/build.sh`, or from the server's checkout `TVT_TILES_LOCK_DIR=/srv/tvt/work/locks
  python3 -m basemap.lock manifest.lock -- COMMAND`.
- **Compose** sets nothing: its only mount of the tiles folder is the app's, read-only (`docker-compose.yml`), and no
  service rewrites the manifest.
- **Checking it** (light, but it goes through `heavy`, so it needs an open window and waits behind any running heavy
  job; out of window `heavy` refuses at once): a worker run through `heavy` with the folder mounted, then `ls` of both
  folders.

  ```bash
  /srv/tvt/work/bin/heavy --deadline HH:MM --runtime 2 --peak 1 "tiles lock check" \
    docker run --rm --memory 512m --memory-swap 512m --cpus 1 --network none --user 1001:1001 \
      -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e TVT_TILES_LOCK_DIR=/srv/tvt/work/locks \
      -v /srv/tvt/repo:/repo:ro -v /srv/tvt/work/locks:/srv/tvt/work/locks -w /repo \
      tvt-worker python -m basemap.lock check.lock -- true
  ls -ln /srv/tvt/work/locks /srv/tvt/tiles     # check.lock is in the first; no *.lock in the second (numeric ids: paste no names)
  ```

## Review sheets on the VM

**`sheets`** ([`bin/sheets`](bin/sheets), installed beside `heavy`) draws
the landscape sprint's image sheets: export layers and rasters over the
aerial photo at the review places ([basemap/sheets](../basemap/sheets/README.md)).
It runs the worker image capped like `worker-test` (1 GB, 1 CPU, no network,
read-only, the checkout at `/repo`), with these mounted read-only: a scratch
database's exports (`--db`, default `tvt`; or `--archive`), the map's tiles,
the land-cover spike's NAIP crops and any `--in` folders. It
writes only to `/srv/tvt/private/sheets/<package>/` (`750`, taking the
private files' group and setgid bit from its parent):

```bash
/srv/tvt/work/bin/sheets -C <checkout on the VM> --pkg p7 -- \
  --places cameras corridors --layer roads/surfaces,by=material --label review-1
```

- It isn't a unit test, so it keeps the quiet-hours rule: from 23:15 it
  starts only once tonight's camera roll-up has finished (heavy's reading
  of the status files), not while a roll-up runs late into the day, and a
  run that starts in the day has its `--timeout` (default 60 min) cut to
  end by 23:15. It doesn't start within its time of a planned restart in
  `MAINTENANCE`.
- It needs 12 GB plus 1 GB free on `/` to start; the drawing then refuses a
  run whose frames could take more than leaves 12 GB (a bound from their
  pixels), and the runner stops the container under 11 GB (exit 123). At
  most two run at once, each with 1 GB plus 3 GB of memory available
  (scratch's reserve).
- An archive (`--db`, default `tvt`; or `--archive`) is mounted one
  plugin's `export/` folder at a time, which is all a sheet reads.
  Production's `trees/` is never mounted, nor any folder holding it (its
  builds carry the City of Boise's inventory), nor, of the land-cover
  spike's folder, anything but `lidar/` and the NAIP crops. `--in` takes
  folders under the work folder (not `bin/`, `e2e/` or the scratch
  folder's tools and secrets; a database's archive is fine) or in
  production's archive (not the archive itself, which holds `trees/`).
  The private files and secrets are never mounted.
- Exit codes: the run's (1 when a frame failed: its error is in the run's
  `index.json`); 2 usage or a refused mount; 73 disk; 75 not now, or no
  slot or memory; 123 stopped under 11 GB free; 124 timed out; 137 killed
  (over its 1 GB: `index.json` lists the frames drawn).

A full run of the 94 frames was 2.3 minutes and 0.23 GB (one panel each,
Oct 11). Sheets are private and never committed; delete runs once reviewed.

## Older camera videos on the cold drive

The daily camera videos grow about 2.1–2.3 GB a day (measured Oct 6–14,
2026), on a VM disk that had 21 GB free on Oct 15. Decision A1 (owner, Oct 8;
the drive inside the VM since Oct 10) put the cold drive in the VM for
finished videos older than about a week. **`cold-videos`**
([`bin/cold-videos`](bin/cold-videos), Python 3, standard library; tests in
[`tests/test_cold_videos.py`](tests/test_cold_videos.py)) moves them there,
daily, from a systemd timer ([`systemd/`](systemd)). The VM's disk then
holds about a week of videos (about 15 GB) instead of every day since Oct 5.

**What moves.** Each finished camera day more than 7 days old (a setting): the
video, `video/<id>/<year>/<id>-<day>.mp4`, and its frame CSV beside it, to the
same place under the camera folder on the cold drive. Never today's or
yesterday's (the setting can't go under 2 days), a day whose JPEGs are still
in the buffer, a day whose encode is going (a `.part` beside it), a file
written in the last 10 minutes, a CSV without its video, the library's
`index-*.json` or the JPEG buffer.

**How.** Each file is copied to a hidden `.cold-part` beside its place on the
drive, synced, and read back from the drive (the VM's cached copy dropped
first) to check its size and sha256 against the original's. The copy is
renamed into place, and then one rename puts a symlink to it where the
original was, so readers see the file or the link, never neither. The copy
keeps the original's mode and times, so Caddy's ETag for it stays the same.
Every move (path, bytes, sha256) is logged to the journal and to
`cameras/cold-videos.log` in the archive, and each run's outcome to
`cameras/cold-videos.json`, which `status` reads. Reads are paced (50 MB/s by
default, both drives together), at idle I/O priority.

**When.** Daily at 02:00 Boise (`tvt-cold-videos.timer`, `Persistent=true`),
as the archive's owner (uid 1000, as the capture containers run). It waits up
to 5 hours for tonight's roll-up: heavy's rule, both capture status files
saying `rolling_up` false after 00:05 (in the day, neither rolling up). It
holds the roll-up's own lock (`cameras/rollup.lock`) while it works, so no
roll-up, nightly or by hand, starts meanwhile. It moves only while the drive's
marker file is there and the drive keeps 200 GB free after each copy
(`COLD_KEEP_GB`, heavy's). It doesn't start from 23:55 until tonight's
roll-up has finished, nor within 15 minutes of a restart planned in
`MAINTENANCE`; a run under way stops between files.

**Idempotent and resumable.** A moved file is a link, and is skipped. A copy
cut short is made again. A copy that finished on the drive but whose original
wasn't replaced yet is checked and used. If a day was encoded again since its
copy was made (`ingest rollup --force` replaces the link with a new file), the
next run replaces the copy on the drive with the new file. SIGTERM (systemd
stopping it) removes the copy being made and leaves its original.

**Readers keep the same paths.** Why links, rather than something cleverer:
every reader already opens `cameras/video/...`, so a link in place changes no
path, no URL and no index entry, and needs no union filesystem or host-side
change. What reads videos, and how each sees a moved day:

- **The video library** (`web`, Caddy 2.11): follows the links, range
  requests included (checked on the VM, Oct 15). The link's target is an
  absolute path on the drive, so [`compose.cold.yml`](compose.cold.yml) mounts
  the drive's mount point read-only at the same path in the containers that
  read videos. The mount point, not a folder on the drive: it's there even
  when the drive isn't, so the containers always start.
- **The roll-up and the library's index** (`cameras`, `regional`): a link
  counts as a finished video (`os.path.lexists`), so a moved day is never
  encoded again, and its JPEGs are pruned as usual. The index marks a moved
  day `"cold": true` and reads its size through the link (the same mount).
- **`status`**: counts last night's videos only, which never move.
- **The app and `app-next`**: read only `cameras/jpeg` and `cameras/status`,
  not videos. No API serves videos.
- **By hand on the VM** (ffmpeg, docs/11 §11.5): the links work as files.

**Without the drive** (unplugged, or the VM started without it): the links
lead nowhere. The library says **"Not available right now"** for those days,
and the other days play; a moved file's URL answers 404 with the same words
(the Caddyfile's `handle_errors`). The index keeps listing the days, the
roll-up doesn't redo them, and `cold-videos` refuses to start (exit 69),
which `status` flags (`! cold-vid`). Plugging the drive back in isn't enough:
a VM started without it sees an empty placeholder in its place, and the
containers' mounts don't see a drive mounted later. Restart the VM once the
drive is back (the drive's own notes say the same); the old days then play
again with nothing else to do.

**The only copy.** A moved video has no other copy: its original on the VM's
disk is replaced by the link, a camera day can't be fetched again, and the
project has no backups yet (Oct 7: "not yet"). The cold drive is one USB
drive with no redundancy, and its own notes keep only-copies off it; decision
A1 makes older camera videos the exception. If the drive fails, every day
more than a week old is lost; the last week stays on the VM's disk.

**Settings.** Paths on the VM stay out of the repo:

- `/srv/tvt/work/heavy.conf`: heavy's `COLD_MOUNT`, `COLD_MARKER` and
  `COLD_KEEP_GB`, plus `COLD_CAMERAS`, the camera folder on the drive (inside
  `COLD_MOUNT`, and a folder of its own: `cold-videos` refuses, exit 2, one
  that is the camera archive, holds it or sits inside it, through links or a
  bind mount too, and stops if a file's copy turns out to be the file itself),
  and optionally `COLD_VIDEO_KEEP_DAYS` (default 7).
- `deploy/.env`: `COLD_MOUNT`, the same mount point, for `compose.cold.yml`,
  and `compose.cold.yml` added to `COMPOSE_FILE`.

**Setting it up** (once, after the merge; the lead, outside 00:00–04:00):

1. Make the camera folder on the drive, owned by uid 1000 and writable by the
   lead's group (setgid): `sudo install -d -o 1000 -g <group> -m 2775
   <COLD_CAMERAS>`. Add `COLD_CAMERAS=<that folder>` to `heavy.conf`.
2. Add `COLD_MOUNT=<mount point>` to `deploy/.env` and `compose.cold.yml` to
   `COMPOSE_FILE`. Once neither capture service is rolling up, from `deploy/`:
   build the capture image (the new index code) under `heavy`, as image builds
   are, with `docker compose build cameras regional`, then `docker compose up
   -d cameras regional web` (the mount). Check that each sees the drive:
   `docker compose exec web ls <COLD_CAMERAS>` (and `cameras`, `regional`).
3. Install the tool beside `heavy`, by rename (as for `heavy`, above):
   `install -m 755 deploy/bin/cold-videos /srv/tvt/work/bin/.cold-videos.new && mv -f /srv/tvt/work/bin/.cold-videos.new /srv/tvt/work/bin/cold-videos`.
4. A dry run as uid 1000: `sudo -u '#1000' /srv/tvt/work/bin/cold-videos --dry-run`
   lists what would move and what stays.
5. The timer: `sudo install -m 644 deploy/systemd/tvt-cold-videos.service
   deploy/systemd/tvt-cold-videos.timer /etc/systemd/system/ && sudo systemctl
   daemon-reload && sudo systemctl enable --now tvt-cold-videos.timer`. The
   first run can start at once (`sudo systemctl start tvt-cold-videos`); follow
   it with `journalctl -u tvt-cold-videos -f`. Afterwards, open an old day in
   the library.

```bash
sudo -u '#1000' /srv/tvt/work/bin/cold-videos --dry-run    # what would move; changes nothing
sudo systemctl start tvt-cold-videos                        # a run now, as the timer would
systemctl list-timers tvt-cold-videos.timer                 # the next run
tail /srv/tvt/archive/cameras/cold-videos.log               # the moves
```

Exit codes: 0 done (or nothing to move); 1 a file failed its check (its
original stays; the next run tries again); 2 usage or settings; 69 the drive
isn't mounted; 73 the drive would fall under 200 GB free; 75 not now (the
roll-up still going after the wait, a restart planned, another run going,
23:55 reached), which systemd counts as success: the next day's run catches
up, and `status` flags two days without a finished run. To bring a day back
onto the VM's disk, as uid 1000, copy it beside its link and rename it over
the link (`cp -p <copy on the drive> <dir>/.<name>.back && mv -f
<dir>/.<name>.back <dir>/<name>`); a day older than a week moves again on the
next run unless `--keep-days` says otherwise.

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
4. Load: `python3 -m ingest osm-load --inbox` (core's loader since the
   landscape sprint, [ingest/osm_extract.py](../ingest/osm_extract.py); the
   old `python3 -m ingest.osm_load` still works). `--file PATH` loads a file
   from anywhere instead; `--only CONSUMER` loads one consumer on the extract
   we hold (`--archived`), `--list` says what each loaded last. Since Oct 11
   it's a **heavy job** in its own capped container, never `exec` in the
   ingest service: the smart cut and osm_valley's own cut each peak at about
   3.9 GB (osmium keeps a bitmap over every node id, and Idaho's run to about
   13 billion), so give it 5 GB; `compose.load.yml`'s 2 GB is too little for
   it. A consumer run on a cut already made peaks at about 0.2 GB. From the
   server, with `DATABASE_URL` set in the shell (never on the command line,
   which heavy's log records):

   ```bash
   /srv/tvt/work/bin/heavy --deadline HH:MM --runtime 10 --peak 1 "osm-load (deploy)" \
     docker run --rm --memory 5g --memory-swap 5g --cpus 2 --network tvt_default -e DATABASE_URL \
       -e TVT_ARCHIVE=/srv/archive -v /srv/tvt/archive:/srv/archive \
       tvt-ingest:latest python3 -m ingest osm-load --inbox
   ```

   Which role: osm_valley writes `core.osm_way` and friends, which
   `tvt_build` can't ([scratch/README.md](scratch/README.md)), so a load
   that includes osm_valley (a new extract) runs as the database owner, as
   its loads always have, until the runbook decides otherwise. The new
   consumers alone (`--only roads.osm_street`, on a cut already made) are
   light and run as `tvt_build`. Run as `tvt_build`, a new extract's load
   fails osm_valley and holds the streets back (below), so nothing loads and
   the file stays in the inbox.

What a load does:

- It takes the newest file in the inbox and checks it against the `.md5`
  beside it.
- Each consumer (`osm_consumers` in the plugins' manifests: `roads.osm_valley`
  first, then `roads.osm_street`, and later paving, paths, water and
  barriers) keeps its own MD5 gate, and one that already has this extract is
  skipped, unless `--force`. Gates: `ops.osm_consumer`, and osm_valley's own
  `$TVT_ARCHIVE/osm/last-loaded.json`.
- It cuts the valley box out of the extract once (osmium's `smart` strategy)
  into `$TVT_ARCHIVE/osm/cut/valley.osm.pbf`, with `valley.json` naming the
  extract; every consumer reads the cut, and the ground's mask reads it too.
  Only a run with osm_valley due (heavy anyway), `--make-cut` or
  `--cut-only` makes the cut. Any other run stops before loading anything
  when it's missing (on production right after the deploy that brings the
  loader, and on scratch after every refresh) and says to make it first.
- osm_valley runs first, then the others. Each runs in its own transaction
  with its own `ops.fetch` row; one that fails is logged and the others go on
  (rerun it with `--only`). The command exits 1 if any failed or was held.
- **One extract for the partition.** `osm_street`, and later `osm_paving` and
  `osm_paths`, load only the extract osm_valley holds (or loaded in the same
  run): otherwise a way that gained or lost a lanes tag would be in
  `core.osm_way` and `roads.osm_street` both, or in neither. One that would
  load another extract is **held back**, and so is osm_valley when a
  follower that holds another extract isn't loading in the same run
  (`--only osm_valley` on a new extract). `--force` doesn't change that;
  `--allow-mixed` does, and shouldn't be needed. Load a new extract without
  `--only`, as the database owner. If a follower fails after osm_valley
  loaded, the load and `--list` say the owners differ, and the roads build
  refuses to run (`check_partition()`) until the follower is loaded with
  `--only`.
- Afterwards, if any consumer loaded it, the file moves to
  `$TVT_ARCHIVE/osm/` (renamed with the date and the start of its MD5) and
  the last two extracts are kept. Pruning never removes the file just
  loaded, and reloading an archived file refreshes its time, so it counts as
  the newest.
- **Shrink guard:** a load that brings fewer than half of the active ways
  (osm_valley: when 1,000 or more are active, as before) or of a consumer's
  active objects (at any size) refuses to retire the rest. Check the file, or
  pass `--allow-shrink`. A consumer's load that brings nothing while anything
  is active is always refused.
- `roads.osm_paving` measures its service ways and lots against
  `roads.developed_land` (plan C11), developed land traced from the Cropland
  Data Layer in the worker image ([plugins/roads](../plugins/roads/README.md)).
  It loads without it, and says so: untagged service ways and lots stay
  unknown until a build is loaded, which measures them again. Once farm's
  `farm-cdl-load` has put the CDL in `/srv/tvt/archive/farm/cdl/`, make a
  build in the worker (light: about 45 s at 0.15 GB, 1 GB and 1 CPU, no
  network) and load it, before or after the paving's first load. The load is
  a production load, so it goes under `heavy` (about a minute; as
  `tvt_build`, `DATABASE_URL` set in the shell). The archive belongs to uid
  1000, as both images run:

  ```bash
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  docker run --rm --memory 1g --memory-swap 1g --cpus 1 --network none --user 1000:1000 \
    -v /srv/tvt/repo:/repo:ro -v /srv/tvt/archive:/srv/archive tvt-worker \
    python -m plugins.roads.build.developed --cdl /srv/archive/farm/cdl --out /srv/archive/roads/developed/$stamp
  /srv/tvt/work/bin/heavy --deadline HH:MM --runtime 5 --peak 1 "roads-developed-load (deploy)" \
    docker run --rm --memory 1g --memory-swap 1g --cpus 1 --network tvt_default -e DATABASE_URL \
      -e TVT_ARCHIVE=/srv/archive -v /srv/tvt/archive:/srv/archive \
      tvt-ingest:latest python3 -m ingest roads-developed-load --build /srv/archive/roads/developed/$stamp
  ```

  Again after each new CDL year (late February, with the owner's OK for the
  download): `farm-cdl-load`, then these two.
- Then the refresh cascade (plan §6): the builds that read the new tables
  (`roads-build`, `water-build`, `trails-match`), the exports, the bake.
  `roads-build` (the real-width roads, roads 0003) is a production load:
  under `heavy` as `tvt_build`, about 10 minutes and 0.6 GB in its own
  container (it measured 579 s on scratch, Oct 11), then `roads-export`
  (about 15 s), whose base layers the bake reads:

  ```bash
  /srv/tvt/work/bin/heavy --deadline HH:MM --runtime 15 --peak 1 "roads-build (deploy)" \
    docker run --rm --memory 2g --memory-swap 2g --cpus 2 --network tvt_default -e DATABASE_URL \
      -e TVT_ARCHIVE=/srv/archive -v /srv/tvt/archive:/srv/archive \
      tvt-ingest:latest sh -c 'python3 -m ingest roads-build && python3 -m ingest roads-export'
  ```

  The build holds its tables until it commits (it truncates them), so
  nothing should read them live meanwhile; `roads-export` waits for it, and
  keeps the newest two exports in `$TVT_ARCHIVE/roads/export/`.

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

The other streets and alleys (`roads.osm_street`, the `osm_street`
consumer), loaded on scratch from the same extract on Oct 11: 22,785 ways
(20,815 residential, 1,003 alleys, 948 unclassified, 17 living streets, 2
roads; about 5,600 km), 11 MB with indexes, in 16 s on the cut. The valley
cut is 32 MB.

Trails' paths (`trails.osm_path`, `osm_area`, `osm_route`: the `osm_paths`
consumer), on scratch on Oct 11: 22,200 ways, 82 areas and 147 route
relations in 21 s on the cut, as `tvt_build`. Then `python3 -m ingest
trails-match` (light, about 25 s) links Ridge to Rivers' trails and the
Greenbelt's closures to them and draws the routes; the load marks it.
On production, after trails 0001: the grants (`tvt_build.sql`, and
`tvt_tiles.sql` again, which keeps the tile login off the views over the
City's rows: `trails.agency_line`, `agency_state`, `way_agency`), then
`osm-load --only trails.osm_paths` on the cut already made, then
`trails-match`, both as `tvt_build` in a capped container, never inside
`ingest serve`. Run `trails-match` again after each water build (its
canal-bank rule reads `water.reach`), until water's build marks it.

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

   **Road-weather stations**, with the owner's OK (a one-off source, run by
   hand): the Road weather layer draws only stations in the database, and
   nothing loads them on a schedule, so without this step the layer is
   empty after deploy ("No road-weather stations are loaded yet"). First
   check that the dated private list is where the loader reads it, the
   private files' data folder (`PRIVATE_DATA_DIR`, mounted read-only in
   `ingest` as `TVT_PRIVATE_DATA`):
   `docker compose exec ingest sh -c 'ls -l "$TVT_PRIVATE_DATA"/511-camera-sites-statewide-2026-10-05.json'`
   (the loader reads exactly this file, `FILE_NAME` in
   `plugins/cameras/ingest/sources/idaho511_rwis_sites.py`).
   Then load it:
   `docker compose exec ingest python3 -m ingest run idaho511_rwis_sites_oneoff`.
   It reads the file only (no request to 511), loads ITD's road-weather
   stations statewide (provider `ITD RWIS`) and Oregon DOT's cameras in the
   regional ring (`ODOT`), each with its views, and changes nothing when run
   again. If the list is missing, it stops with a message saying so: put the
   file back in the private files first, never in the repository.
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
   - road weather: `/api/roadweather` lists the stations (no `note`), and,
     once the `regional` capture service has run a cycle with the new code,
     some views are `capturing` with an `ageS`:

     ```bash
     curl -s http://localhost:8080/api/roadweather -H "Origin: http://localhost:8080" | python3 -c '
     import json, sys; d = json.load(sys.stdin); views = [v for s in d["stations"] for v in s["views"]]
     print(len(d["stations"]), "stations,", len(views), "views,", sum(v["capturing"] for v in views), "capturing,",
           sum(v["ageS"] is not None for v in views), "with a picture", d.get("note", ""))'
     ```

     Then switch Road weather on (key 9) in the app, click a station inside
     the map and check that its window's tabs show pictures with their ages;
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
