# How agent work runs here

Since Oct 22, 2026 the project's agent work follows the owner's
[agent-dev-kit](https://github.com/Benten-Ben/agent-dev-kit): its `efficient-agent-dev` skill for planning and launching
agents, and its `github-project-board` skill for issues and the board. This page adapts the kit's numbers (measured on
another project) to this one. The goal is the kit's: **the least plan usage per accepted change, at equal quality.**

## Who does what

- **The coordinator** is the one local Claude session that drives the project ([HANDOFF.md](../HANDOFF.md)). It plans,
  answers the questions the owner has delegated, launches agents, reads every result, merges and records decisions. It
  stays on the strong model. Its helpers don't.
- **Small things stay inline:** a one-line fix, a merge conflict, a doc paragraph, a single lookup. An agent call carries
  tens of thousands of tokens before it starts.
- **Everything else** goes through the kit's *build unit*: precheck, build (a draft PR, `Closes #n`), one review, one
  skeptic fix. That's at most four agents, and the coordinator merges.

## Tiers for this project's work

Every agent gets an explicit `model` and `effort`. Without them it inherits the coordinator's, so no helper runs at
xhigh.

| Tier | What it covers here | Build | Review | Fix |
|---|---|---|---|---|
| **light** | docs and copy, legend text, small fixes | inline, or Haiku low | Haiku low | Haiku low |
| **standard** | map layers, cards and legends; pure functions with unit tests; loaders over files we already hold; review sheets | Haiku low, after a precheck | Sonnet medium | Haiku low |
| **deep** | migrations and builds run on the scratch database; the ground painter and land-cover classes; the scene engine and picking; the tile server; layer order | Sonnet medium | Sonnet high | Sonnet medium |
| **critical** | anything that fetches from the network (robots.txt, terms, off-limits hosts, API keys); licence and republish flags; private data (the City's tree inventory, internal agency tables); the public check; deploy, Compose, systemd and the runbook; production migrations and loads; changes on the home server | Sonnet high | whole-PR critical review: 3 Opus-high lenses (data and licences, privacy and the public repo, operations and the server) plus 1 Opus-high skeptic | Sonnet high |

- **Licence values copied from approved sources** (an export or manifest that only restates the licence and republish
  already recorded for its sources) run as **deep** with one Opus-high data-and-licences reviewer, not the full
  critical review (coordinator, Oct 22). Anything that decides a new licence or republish value, or guards what may
  be published, stays critical.
- **Precheck:** Haiku low on every agent-written work order. It corrects stale quotes and values in the issue itself, and
  stops the unit on real design questions. The coordinator or the owner answers those on the issue.
- **Planning a chunk of the sprint:** Opus (medium or high) writes the work orders, with disjoint file ownership, order,
  tier and builder model, and a coverage map back to the sprint plan. Then **one** Opus cross-review fixes overlaps,
  gaps and ordering, before anything is filed.
- **Research and source checks:** Sonnet medium. **Synthesis, decision lists, final judgements:** Opus high.
- Climb a rung (Haiku → Sonnet → Opus) only for the role and tier where this project's own evidence shows the cheaper
  one failed, and record each change below.

## Launching

- **Only from a turn the coordinator started itself.** A workflow launched in a turn that began with the owner's message
  relays that message to every agent, and they answer it instead of working. That happened here on Oct 8 and Oct 15.
  Reply first, start `sleep 15; echo trigger` in the background, and launch from its notification. The kit's guard
  enforces this where its plugin is loaded.
- **Fan-out is fixed by tier before launch**, never one agent per finding. Review rounds are capped at two. Minors are
  fixed without re-review.
- **Each parallel unit gets its own worktree,** owns disjoint files, and has its own test database (`tvt_test_<unit>`) and
  port. Nobody uses `git stash`; that stack is shared by every worktree. Give a worktree its own `app/node_modules` as an
  APFS clone (`cp -cR`), not a symlink.
- **Keep work resumable.** State lives in issues, branches and worktrees. Workflow scripts and helpers live in the
  git-ignored `data/dev/wf/`, never in a temporary folder.
- **Server work** follows the existing rules: the scratch database for unmerged code, `heavy` with a deadline for heavy
  jobs, and the night window around the camera roll-up ([deploy/README.md](../deploy/README.md)).

## The agents' GitHub App

Agents don't act as the owner on GitHub. Since Oct 22 (owner: "yes set up the agents App for TVT") they use the owner's
`bens-agents` GitHub App, the same App the owner's other projects use, with tokens scoped to this repository alone. Their PRs,
comments and issue edits show as the App's bot, and they spend the App's own API budget instead of the owner's.

- **How it works:** `tools/gh-app-token` mints a one-hour installation token from the App's private key and caches it.
  `tools/agent-bin/gh` is a `gh` wrapper that puts that token in `GH_TOKEN` for ordinary calls. Every build unit puts
  `tools/agent-bin` first on its `PATH`.
- **What stays on the owner's login:**
  - the board (a Project on a personal account, which an App can't reach): `tools/board` and
    `tools/board_status_sync.py` set `TVT_GH_AS_USER=1`, and project queries are caught by name;
  - anything naming `@me`;
  - `gh auth`, and approvals (`gh pr review`).
- **Configuration:** `~/.config/tvt/gh-app.env` (mode 600, never in the repository) names the App, its installation and
  the private key's path, with `TVT_GH_APP_REPOS=treasure-valley-traffic`. The cache is `~/.cache/tvt/`. Never print a
  token, the key or the ids into a chat, a prompt or the repository. Without the configuration, the wrapper falls back
  to the login.
- **Check:** `tools/gh-app-token >/dev/null && echo ok`. Then, with `GH_TOKEN=$(tools/gh-app-token)`,
  `gh api /installation/repositories` should list this repository alone. Tests:
  `python3 -m unittest tools.test_gh_app_token`.

## Testing

- Builders run only the tests their change touches: unit tests, `npm run check` and `npm test` behind the build lock,
  worker tests with `worker-test` on the server. The full suite runs once per chunk, at integration (Oct 7 rule).
- Browser specs run where they can pass. The laptop runs them behind its browser lock, and only when it isn't busy:
  under load they time out without anything being wrong. The server runner runs the non-map specs. A timing miss with a
  passing functional result becomes a documented known limit, not a blocker.

## The board

- **The board** is the GitHub Project "Treasure Valley Traffic" (number and owner in `.board.env`). Its Status runs
  Backlog, Ready, In progress, In review, Done, and it has Phase, Area and Size fields. Labels are `area:*`, `phase:*`,
  `size:*`, `review:<tier>`, and the states `blocked`, `decision-needed`, `needs-design` and `owner-action`. The kit's
  `board` CLI is copied to `tools/board` (`tools/board ls|next|new|claim|status|block|sync-blocked`; it reads
  `.board.env`).
- **Board automations** (set in the web UI; no API): item added → Ready; item reopened (issues) → Ready; PR linked
  to an issue → In review; changes requested → In progress; item closed or PR merged → Done; Done closes the issue;
  closed issues archive after two weeks; open issues in this repository and sub-issues are added automatically.
  "Code review approved" stays off, so a card stays In review until its PR merges. Replacing the Status options clears
  these, so set them again after any change. **Views:** All, Board, Ready queue, In flight, Decisions for Ben, Waiting
  on Ben, Chunk B, Chunk C, Backlog by area (grouped by Area) and Stale. A view's grouping saves only through "Save
  view" and its dialog's Save. A "Waiting on" field (nobody, Ben, an agency) marks what waits on someone.
- **What each status means** (owner, Oct 22): **Backlog** is only what is blocked: by an open "blocked by" link, by
  open sub-issues (the tracking issues), or by a wait outside GitHub (label `waiting-agency`: a reply from an agency). **Ready** is every other open issue not started yet, including decision-needed
  and owner-action ones (their labels keep `board next` from handing them to agents). Once a decision-needed or owner-action issue is decided or done, its label comes off with a "Decided (who,
  date):" comment. **In progress** means claimed:
  a builder runs `tools/board claim <n>` first. **In review** follows on its own when a PR with `Closes #n` opens.
  **Done** follows when the issue closes: a merged PR closes it; work finished without a PR (an issue that no longer
  reproduces, an owner action) is closed by hand with a comment saying why; a tracking issue is closed with a summary
  once its sub-issues are closed. After merges and after adding or removing blockers, the coordinator runs
  `python3 tools/board_status_sync.py`, which moves issues between Backlog and Ready and keeps the `blocked` label in
  step.
- **Outstanding work lives on the project's GitHub board.** Each issue is a work order: Goal, Steps, Acceptance, Owns,
  Depends on, Context (`.github/ISSUE_TEMPLATE/task.md`). Decisions go on the issue they decide, as "Decided (who,
  date):", and lasting ones also go in [DECISIONS.md](DECISIONS.md).
- **Issues, PRs and review comments are public, like the repository.** Every body is checked before posting:
  `python3 tools/check_public.py --text <file>`. That runs the repository's mechanical checks plus a private pattern list
  kept outside the repository. Agents tend to quote the exact private value they just removed, so the coordinator also
  reads each PR body before merging.

## Evidence (re-measure as it changes)

- **Through Oct 15, every agent ran on the coordinator's model at its effort.** That's about 250k tokens per agent. For
  example, chunk A was 14 agents and 3.4M tokens, and the UI v2 padding change was 3 agents and 1.0M.
- **The board sweep (Oct 22):** 8 agents (5 Sonnet-medium gatherers, 2 Opus-high planners, 1 Opus-high cross-review),
  about 2.0M tokens, 316 issues planned (315 filed).
- From the landscape sprint's chunk B on, agents follow the tiers above. Record agents, tokens and accepted changes per
  chunk here, to compare.
