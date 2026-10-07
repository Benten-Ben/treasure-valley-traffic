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
   checkout.
3. Create the environment file: `cp deploy/.env.example deploy/.env`, then
   set a database password generated on the server
   (`openssl rand -hex 24`). Never paste it into a chat session.
4. Create the frames and archive folders:
   `sudo mkdir -p /srv/tvt/frames /srv/tvt/archive && sudo chown 1000:1000 /srv/tvt/frames /srv/tvt/archive`.
   The archive holds raw feeds that can't be fetched again later, so back it up.
5. Put the map tiles in `TILES_DIR`: build them (see [basemap/](../basemap)),
   or copy a finished build.
6. Put the private reference files in `PRIVATE_DATA_DIR` (they aren't in
   this repository).
7. Start everything: `docker compose -f deploy/docker-compose.yml up -d --build`.
8. Link the 511 camera views to cameras (one-off, by hand):
   `docker compose -f deploy/docker-compose.yml exec ingest python3 -m ingest run idaho511_views_oneoff`.
9. Open the site on port 8080.

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

## Updating

```bash
# push main to /srv/tvt/repo from a checkout (the server has no GitHub access), then:
cd /srv/tvt/repo/deploy
docker compose up -d --build <services>
```

Run Compose from `deploy/` **without `-f`**, so it reads `COMPOSE_FILE` from
`deploy/.env` and includes the overrides that are switched on (live images,
the preview). With an explicit `-f`, the overrides are skipped.

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
