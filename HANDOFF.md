# Handoff: two-session workflow

This project is run by two Claude sessions, with the owner relaying between
them.

| Session | Where it runs | Role |
|---|---|---|
| **Pilot** | Claude Code in the cloud, on this repo | Primary: research, design, code, docs, git. Joins the owner's tailnet when needed, to deploy to and test on the project server. |
| **Local helper** | Claude Code on the owner's laptop | Anything that needs the owner's machines or home network, above all the host the project's VM runs on. |

**How relaying works:**

- The owner copies messages between the sessions. Keep them
  self-contained: what to run, why, and what to send back.
- The helper reports **raw command output verbatim**, plus a short summary
  (template at the end).
- **Never paste secrets** (passwords, API keys, private keys, tokens) into
  either session or into the repo. Say where a credential lives instead.
  Tailscale logins use links the owner opens in a browser, not keys.
- **This repo is public.** Reports that describe the owner's network or
  hardware stay out of it. Anything worth keeping goes in the private notes
  on the server ([CLAUDE.md](CLAUDE.md)).

## Rules for the local helper

1. **Decisions about the host are made by the owner and the helper.** That
   covers VMs or containers, their size, storage, network and backups. The
   pilot only recommends.
2. **Nothing changes on the host without the owner's explicit OK** for that
   exact action. Inspecting and listing is fine.
3. Tell the owner which host and user you'll use before connecting.
4. Don't change router or firewall settings, or existing VMs and
   containers.
5. Don't commit or push to this repo. The pilot owns git; send file
   contents or diffs back through the owner.
6. Follow the data rules in `CLAUDE.md`. They apply to anything the helper
   fetches.

## Current state (2026-10-05)

- **Research:** chapters 1–8 are done (`README.md`).
- **Decided:** see `docs/DECISIONS.md`. The parts that matter here:
  - the platform runs in one VM on the owner's home server, with Docker
    Compose, reached over Tailscale;
  - the first real feature is the **camera calibrator**;
  - the map shows only the foundation (terrain, imagery, streets,
    buildings) plus cameras for now.
- **Running on the server (Oct 5):**
  - the database (TimescaleDB + PostGIS), with migrations applied;
  - ingest: ACHD's camera list, daily, plus the 511 camera views, linked
    once;
  - the app, with two lenses: Transit (live buses) and Cameras (nodes,
    view cones, and the calibrator at `/calibrate/<id>`);
  - transit recording: VRT's live feeds every 30 s (raw archive plus bus
    positions) and its schedule daily;
  - the map tiles: streets, terrain, buildings, aerial imagery, and
    sharper imagery around the cameras.
- **The helper's server setup is done.** The steps and the host details are
  in the private notes on the server.
- **Still waiting on the owner:**
  - the 511 developer key;
  - sending the ACHD note (the draft is in the private files);
  - schema decisions 3–7 (`docs/12-database-schema.md` §12.9);
  - where backups go (`docs/DECISIONS.md`).

## Message template (helper → pilot)

```
## Helper report: <task>
Commands run (host/user): ...
Raw output:
<verbatim>
Summary / anything unexpected:
Questions for the pilot or owner:
```
