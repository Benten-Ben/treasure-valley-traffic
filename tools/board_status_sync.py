#!/usr/bin/env python3
"""Keep the project board's statuses to the rule in docs/agent-work.md (owner, Oct 22).

  Backlog      an open issue that is blocked: an open "blocked by" link, open sub-issues (a tracking issue), or the label
               `waiting-agency` (it waits on a reply from an agency, outside GitHub)
  Ready        every other open issue that hasn't started
  In progress, In review   left as they are (a claim and an open PR set them)
  Done         closed issues

It also keeps the `blocked` label in step with the open "blocked by" links. Run it after merges and after adding or
removing blockers. It reads the issues one by one rather than the board's own listing, which can lag.

usage: python3 tools/board_status_sync.py [--dry-run]     (reads .board.env; needs gh with the project scope)
Standard library only.
"""
import json
import os
import subprocess
import sys
import time
from collections import Counter

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def use_login() -> None:
    """The board is a Project on a personal account, which the agents' App can't reach: always call the real gh on
    the login. Drop an App token a wrapped gh left in GH_TOKEN, and every */agent-bin directory from PATH (a wrapper
    from another project may be on it and doesn't know TVT_GH_AS_USER)."""
    os.environ["TVT_GH_AS_USER"] = "1"
    if os.environ.get("TVT_GH_APP_TOKEN") == "1":
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("TVT_GH_APP_TOKEN", None)
    os.environ["PATH"] = os.pathsep.join(
        d for d in os.environ.get("PATH", "").split(os.pathsep) if d and os.path.basename(d.rstrip("/")) != "agent-bin")


use_login()

QUERY = ("query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){issue(number:$n){number state "
         "labels(first:30){nodes{name}} blockedBy(first:50){nodes{state}} subIssuesSummary{total completed} "
         "projectItems(first:5){nodes{id project{number} fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}")


def gh(*args, parse=False):
    for attempt in range(6):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout) if parse else r.stdout.strip()
        time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"gh {' '.join(args[:3])}: {r.stderr[:300]}")


def wanted(state, current, open_blockers, open_subs, waiting_outside=False):
    """The status the rule asks for."""
    if state == "CLOSED":
        return "Done"
    if current in ("In progress", "In review"):
        return current
    return "Backlog" if open_blockers or open_subs or waiting_outside else "Ready"


def main(argv):
    dry = "--dry-run" in argv
    env = dict(l.strip().split("=", 1) for l in open(os.path.join(REPO_DIR, ".board.env")) if "=" in l and not l.startswith("#"))
    owner, number, repo = env["BOARD_OWNER"], env["BOARD_NUMBER"], env["BOARD_REPO"]
    o, r = repo.split("/")
    fields = {f["name"]: f for f in gh("project", "field-list", number, "--owner", owner, "--format", "json", parse=True)["fields"]}
    status = fields["Status"]
    opt = {x["name"]: x["id"] for x in status["options"]}
    pid = gh("project", "view", number, "--owner", owner, "--format", "json", parse=True)["id"]
    issues = gh("issue", "list", "-R", repo, "--state", "all", "--limit", "2000", "--json", "number", parse=True)
    moved, labelled = [], []
    for row in sorted(issues, key=lambda x: x["number"]):
        n = row["number"]
        iss = gh("api", "graphql", "-f", f"query={QUERY}", "-f", f"o={o}", "-f", f"r={r}", "-F", f"n={n}", parse=True)["data"]["repository"]["issue"]
        item = next((i for i in iss["projectItems"]["nodes"] if str(i["project"]["number"]) == str(number)), None)
        if not item:
            continue
        cur = (item.get("fieldValueByName") or {}).get("name")
        blockers = sum(1 for b in iss["blockedBy"]["nodes"] if b["state"] == "OPEN")
        subs = iss["subIssuesSummary"]["total"] - iss["subIssuesSummary"]["completed"]
        names = {l["name"] for l in iss["labels"]["nodes"]}
        want = wanted(iss["state"], cur, blockers, subs, "waiting-agency" in names)
        if want != cur:
            moved.append((n, cur, want))
            if not dry:
                gh("project", "item-edit", "--id", item["id"], "--project-id", pid, "--field-id", status["id"],
                   "--single-select-option-id", opt[want])
                time.sleep(1)
        has_label = "blocked" in names
        if iss["state"] == "OPEN" and bool(blockers) != has_label:
            labelled.append(n)
            if not dry:
                gh("issue", "edit", str(n), "-R", repo, "--add-label" if blockers else "--remove-label", "blocked")
                time.sleep(1)
    print(f"{len(issues)} issues checked; {len(moved)} status changes {dict(Counter(f'{a}->{b}' for _, a, b in moved))}; "
          f"{len(labelled)} blocked-label changes{' (dry run)' if dry else ''}")
    for n, a, b in moved:
        print(f"  #{n}: {a} -> {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
