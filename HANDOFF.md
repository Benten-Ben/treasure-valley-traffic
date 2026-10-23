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
   - Push the branch to origin and open a draft PR into `main` with
     `Closes #n` (the PR template lists the lines). Its required check is
     `ci` ([CLAUDE.md](CLAUDE.md) Conventions: what CI runs and where the
     other suites run). One review, then the coordinator merges the PR on
     GitHub. Nobody fast-forwards `main` by hand.
   - After the merge, push `main` to the server's repository (it has no
     GitHub access), then rebuild with Compose ([deploy/](deploy/README.md)).
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

## Current state

This file does not restate status. One session drives the project (since Oct 7, 2026). Outstanding work lives on the
project's GitHub board as work-order issues. Decisions are logged in [docs/DECISIONS.md](docs/DECISIONS.md). How agents
work, with their tiers and checks, is in [docs/agent-work.md](docs/agent-work.md).

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
