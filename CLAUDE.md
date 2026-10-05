# CLAUDE.md

Guidance for Claude sessions working in this repository.

## What this project is

Independent, non-commercial research into traffic signal timing and
congestion in Idaho's Treasure Valley (Ada and Canyon counties), plus an
in-progress platform for a self-hosted "god's-eye view" of the road network:
our own base map with live and historical data layers.

- Research write-up: `README.md` and `docs/01`–`docs/08`.
- Platform design: `docs/09` (base-map data), `docs/10` (architecture),
  `docs/11` (camera validation layer).
- Decisions: `docs/DECISIONS.md`. Read it before proposing anything
  structural.
- How the two Claude sessions work together: `HANDOFF.md`.

## How we work with the owner

- **The owner wants to be closely involved.** Propose structural choices
  (stack, schema, deployment, what counts as "core", how a source is used)
  and wait for a decision. Don't build big pieces on assumptions. Record
  decisions in `docs/DECISIONS.md`.
- Go through data sources one at a time with the owner before committing to
  how each is used.
- The cloud session is the primary pilot. A local helper session (owner's
  laptop) does anything needing local files or the home network. The owner
  relays between them.
- **Never** change the home server (create, modify or delete VMs,
  containers, storage or network) without the owner's explicit approval for
  that specific action.

## This repository is public

Never commit any of these. They belong in the project's **private files on
its server** (`/srv/tvt/private`; its `README.md` lists what's there):

- **The owner's network or hardware:** addresses, host or machine names,
  user names, hardware, hypervisor, other guests or devices, backup or
  power arrangements. Public docs say "the owner's home server" and "a VM".
- **Third-party data copies:** ACHD's tables, 511's lists, camera images,
  and anything else whose license doesn't clearly allow redistribution.
- **Tools that touch hosts whose robots.txt disallows us,** and unsent
  drafts to agencies.
- **Secrets** of any kind.

Before every push, check the diff for these.

## Data ethics and legal rules (non-negotiable)

- **Respect robots.txt** per RFC 9309, leniently parsed: BOMs, blank lines,
  rules without a User-agent line, `*`/`$` wildcards; 4xx means no rules;
  5xx or a network error means disallow for now. We match paths
  case-insensitively, which is deliberately stricter.
- **Respect terms of service.** Don't store Google Maps, Waze, TomTom, HERE
  or Mapbox traffic results, and don't scrape their sites.
- **Off-limits for automated collection** (no schedules, ingestors,
  collectors, and no whole-table downloads without the owner's explicit OK
  for that run; one was approved for ACHD's tables on Oct 5):
  - `more.achdidaho.org` (ACHD counts and turn-movement tables, camera
    images);
  - 511's `/list/getdata/` and `/map/map*/` endpoints.
- **One-off research checks are fine** (owner, Oct 5). Requests made at
  the owner's request to look something up are not robot access. Keep them
  small and paced, use our honest User-Agent, and note where any resulting
  facts came from.
- **Tools for those checks** are kept with the private files, not in this
  repo. They must:
  - require an explicit flag (`--one-off`, `--have-permission`);
  - be run by hand only;
  - cap their work and pause between requests.
  Never call them from `ingest/`, cron or any scheduler.
- **Allowed camera route:** 511 Idaho's republished images at
  `/map/Cctv/<id>`, with IDs from the official 511 API (key required;
  10 calls per 60 s).
- **Road network, not people:** no plate or face recognition and no
  tracking individuals. Volunteer GPS tracks get consent, trimmed ends and
  aggregate-only publishing.
- **Licenses:** credit "© OpenStreetMap contributors" (ODbL; derived
  databases we publish stay ODbL) and ITD; don't redistribute Ada County
  Assessor data.
- Identify our client honestly (User-Agent with a link to this repo).
  Honor Crawl-delay (IEM: 120 s). Poll gently.

## Repository layout

```
README.md               research summary and index
docs/01-08              research chapters (signals, local system, data, playbook, AI, automation, DIY data, inventory)
docs/09-13              platform: base-map data, architecture, camera layer, DB schema (draft), visual design
docs/DECISIONS.md       decision log + pending questions + owner actions
docs/data/README.md     what the reference datasets are (kept privately, not published)
app/                    SvelteKit + MapLibre map (the platform front end)
basemap/                builds self-hosted map layers into data/tiles/ (served at /tiles/)
db/                     migrations (db/migrations/*.sql) and the runner db/migrate.py; design in docs/12
ingest/                 clean Python ingestors (cameras so far; psycopg is the one dependency)
deploy/                 Docker Compose + Caddy for the server VM
tools/                  standalone research scripts (GPS run analysis, etc.)
tvt/                    THROWAWAY PROTOTYPE ingestion package; lessons only, not the foundation
tests/                  tests for tvt/
data/, site/data/       local data and outputs (git-ignored)
```

## Commands

```bash
python3 -m unittest discover tests     # tvt prototype tests (offline)
python3 -m unittest discover tools     # tools tests
python3 -m tvt sources|ingest|status|build   # prototype CLI

cd app && npm install && npm run check && npm run build   # front end
cd app && npm run dev                  # map at http://localhost:5173 (needs data/tiles/)
basemap/build.sh                       # build self-hosted basemap into data/tiles/

export DATABASE_URL=postgres://tvt:<password>@localhost/tvt   # never commit a real password
python3 db/migrate.py                  # apply db/migrations/
python3 -m ingest run all              # camera list + views
python3 -m unittest discover -s ingest/tests -t .
```

Front-end rules:

- The map loads only **self-hosted** tiles, fonts and sprites: built
  layers from `/tiles/`, and data layers from the app's own `/api/`
  (e.g. road tiles cut by PostGIS). Never point the style at a
  third-party tile host or anything that needs a key.
- If a layer isn't built, the app says so; it doesn't silently substitute
  another source.
- The project uses SvelteKit 3 / Svelte 5 runes, with `#lib/...` imports
  (not `$lib`).
- Follow the visual design in `docs/13-visual-design.md`: a friendly,
  game-inspired command center. Use its tokens, fonts (self-hosted), lens
  model and usability rules. Never use red/green alone.

Python 3.11, standard library only, except `gtfs-realtime-bindings` for
live bus positions (`requirements.txt`).

## Environment notes (cloud session)

- Outbound traffic goes through a proxy. `achdidaho.org`, `swidrdc.org`
  (COMPASS), `overpass-api.de` and `web.archive.org` are unreachable or
  blocked from the cloud sandbox but work from a normal network.
- The cloud session reaches the project server only over Tailscale. It
  joins the owner's tailnet (the owner approves a login link and removes
  the machine when the session ends). The host and user names are in the
  private server notes; ask the owner for them. Tailscale and
  `openssh-client` are installed per session. After a container restart,
  start `tailscaled` again with the same `--state` file; it rejoins without
  a new approval.
- **Deploying:** the server's repo (`/srv/tvt/repo`) accepts pushes over
  the tailnet, so the server needs no GitHub access. Push, then rebuild
  with Compose on the server ([deploy/](deploy/README.md)).
- **GitHub:** public repositories can be cloned through the session's git
  proxy (`add_repo` explains the steps). Release-asset downloads and the
  GitHub API are not available, so tools like `pmtiles` are built from
  source with Go (`go build`), whose modules come from proxy.golang.org.

## Conventions

- Match the surrounding style. Cite sources inline in docs, and mark
  anything resting on secondary sources with ⚠️.
- Commit messages: imperative summary plus a short body. Develop on the
  assigned branch, then fast-forward `main` (the default branch) once the
  checks pass and the diff has been checked for private details.
