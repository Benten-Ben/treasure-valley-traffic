# Handoff: how Claude sessions work on this project

Since Oct 7, 2026, **one Claude Code session on the owner's laptop drives
the project**. It combines the two earlier roles: a cloud "pilot" session
(research, code, git, deploys) and a local "helper" (the home server). The
change came when the cloud session's account reached its weekly usage
limit. The cloud session was asked only to finish UI wave D and hand its
work back.

| Session | Where it runs | Role |
|---|---|---|
| **Driver** | Claude Code on the owner's laptop | Everything: research, design, code, docs, git, deploys, and the home server |
| **Cloud session** (optional) | Claude Code in the cloud | Only for a bounded task the owner starts. It joins the tailnet with a login link the owner approves, hands its work back on a branch, and its machine is removed from the tailnet afterwards |

## Rules

1. **The project's VM:** the owner's standing OK (Oct 7) covers deploying,
   restarting, cleaning up and editing its configuration.
2. **Everything else on the home server needs the owner's explicit OK for
   that exact action.** That covers the host (the hypervisor), its storage,
   network and backups, and its other VMs and containers. Inspecting and
   listing are fine. Never change router or firewall settings.
3. **Git:**
   - Work on a branch.
   - Run the checks, including `python3 tools/check_public.py`, and read
     the diff for private details.
   - Then fast-forward `main` and push it to GitHub and to the server's
     repository. The server has no GitHub access.
   - Commits are authored by the owner, with Claude as co-author.
4. **Private plugins** live in their own private repository. It has a copy
   on the server and a private one on GitHub, and the laptop pushes to both
   ([docs/15](docs/15-plugins.md) §15.3).
5. **Never paste secrets** (passwords, API keys, private keys, tokens) into
   a session or the repo. Say where a credential lives instead.
6. **This repo is public.** Host details, addresses and user names go in
   the private server notes ([CLAUDE.md](CLAUDE.md)).
7. Follow the data rules in `CLAUDE.md`. They apply to anything a session
   fetches.

## Current state (2026-10-07)

- **Research:** chapters 1–8 are done (`README.md`).
- **Decided:** see `docs/DECISIONS.md`.
- **Running on the server:**
  - the database (TimescaleDB + PostGIS);
  - the app and the video library over HTTPS on the tailnet;
  - the collectors: cameras (34 key cameras, daily videos), road-weather
    views, the 511 API, ITD work zones and VRT buses;
  - the data builds: intersections, crossings, lanes, COMPASS and NAIP 2025
    detail imagery.

  The collectors run on the plugin code from refactor step 1.
- **UI v2** ([docs/14](docs/14-ui-v2.md)):
  - waves A–C are on `main`, not yet deployed;
  - wave D came back from the cloud session on its branch, and waves E–H
    were built here on the integration branch (WP15 last: docs, the
    screenshot matrix and the owner's review page);
  - deploying follows the runbook in [deploy/](deploy/README.md#deploying-ui-v2-runbook);
    what's left for the next round is in [docs/DEFERRED.md](docs/DEFERRED.md).
- **Plugins** ([docs/15](docs/15-plugins.md)):
  - step 1 (ingest) is done;
  - the private plugins have started;
  - aircraft is in progress and will deploy switched off until the courtesy
    note to adsb.lol is sent.
- **Waiting on the owner:** see "Owner actions" in `docs/DECISIONS.md`.
- **Data sources still to go through:** `docs/SOURCES.md`.

## Handing a task to a cloud session

Keep the message self-contained: what to do, where to push, what to send
back, and when to stop. Ask for this hand-back:

```
## Hand-back: <task>
Pushed: <branch> at <sha> (where)
Checks: <real counts>
Not finished, and why:
Open threads or promises not in docs/DECISIONS.md:
```
