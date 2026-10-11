#!/usr/bin/env python3
"""scratchq: the rules run.sh and refresh.sh apply to scratch jobs (landscape sprint plan, F6).

The time windows, the camera roll-up and a planned VM restart are F7's `heavy` rules: this
loads the installed heavy as a module and asks it, so they live in one place. What's left
here is what only light jobs need (quiet hours' 1 GB rule, the 23:15 stop, the restart
cut) and which folders a job may mount.

  scratchq.py light MEM_MB RUNTIME_MIN LIMIT_MIN   may a light job start now? prints the epoch it stops by
  scratchq.py restart-cut                           the epoch 10 minutes before a planned restart, or nothing
  scratchq.py mount SRC:DST[:ro]                    SRC:DST[:ro] with SRC resolved, if a job may mount it
  scratchq.py quiet                                 exit 0 in quiet hours (23:15-06:00 Boise)

Exit 0: yes (notes on stderr); 1: refused (why, on stdout); 2: usage. Settings come from the
environment lib.sh exports: HEAVY (the installed heavy), WORK, CAMERA_STATUS_DIR,
SCRATCH_ROOT, PROD_ARCHIVE, COLD_MOUNT, DUMP_ROOT, PRIVATE_DIRS (colon-separated).

Tests: deploy/scratch/tests (they load heavy from deploy/bin/heavy, which F7 adds).
"""
import datetime as dt
import importlib.machinery
import importlib.util
import os
import sys

LIGHT_MB = 1024                 # in quiet hours, until the roll-up has finished: 1 GB at most
RESTART_CHECK_MIN = 10          # a job that may run longer than this checks for a planned restart


class Refused(Exception):
    pass


def load_heavy(path):
    """F7's heavy as a module (it runs nothing on import)."""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"no heavy at {path!r}: the scratch scripts need F7's heavy "
                                "(deploy/bin/heavy, installed in /srv/tvt/work/bin)")
    loader = importlib.machinery.SourceFileLoader("heavy_for_scratch", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# --- time -------------------------------------------------------------------------

def quiet(h, t):
    """23:15-06:00 Boise: outside heavy's day window."""
    return not (h.DAY[0] <= t.time() < h.DAY[1])


def rollup_done(h, t, statuses):
    """(done, why): tonight's camera roll-up has finished, by heavy's rule. Never before 00:05."""
    if not (h.NIGHT[0] <= t.time() < h.DAY[0]):
        return False, "tonight's roll-up starts at 00:05"
    return h.rollup_finished(t, statuses)


def next_at(h, t, clock):
    """The next `clock` (a time) in Boise after t."""
    when = h.at(t.date(), clock)
    return when if when > t else h.at(t.date() + dt.timedelta(days=1), clock)


def light_job(h, t, mem_mb, runtime_min, limit_min, statuses, maint):
    """(stop time, notes) for a light job asked to start at t, or raise Refused.

    - In quiet hours (23:15-06:00), until tonight's roll-up has finished, 1 GB at most.
    - A job over 1 GB stops at the next 23:15, and must fit before it.
    - It stops after its --limit.
    - A planned VM restart (heavy's reading of MAINTENANCE, a leftover note ignored): the job
      stops 10 minutes before it, and must fit before that. A note whose time can't be read
      refuses every job that may run more than 10 minutes (by its limit, not only its runtime).
    """
    stop, notes = t + dt.timedelta(minutes=limit_min), []
    if mem_mb > LIGHT_MB:
        if quiet(h, t):
            done, why = rollup_done(h, t, statuses)
            if not done:
                raise Refused(f"quiet hours (23:15-06:00 Boise): until tonight's camera roll-up has finished "
                              f"({why}), jobs get 1 GB at most (--memory 1g), or wait")
        cut = next_at(h, t, h.DAY[1])
        if t + dt.timedelta(minutes=runtime_min) > cut:
            raise Refused(f"a job over 1 GB stops at {h.hm(cut)} (quiet hours), and {runtime_min} min from "
                          f"{h.hm(t)} doesn't fit: use --memory 1g, or start it earlier")
        if cut < stop:
            stop = cut
    if maint is not None:
        text, restart = maint
        if restart is None:
            if max(runtime_min, limit_min) > RESTART_CHECK_MIN:
                raise Refused("a VM restart is planned and MAINTENANCE gives no one time heavy can read "
                              f"({text[:200]!r}): jobs that may run over {RESTART_CHECK_MIN} minutes "
                              f"(--limit {limit_min}) wait until it's fixed or done")
            notes.append(f"a VM restart is planned: {text[:200]!r}")
        else:
            cut = restart - h.MAINTENANCE_MARGIN
            if t + dt.timedelta(minutes=runtime_min) > cut:
                raise Refused(f"a VM restart is planned at {restart:%Y-%m-%d %H:%M} Boise: {runtime_min} min "
                              f"from {h.hm(t)} doesn't fit before {h.hm(cut)}")
            if cut < stop:
                stop = cut
                notes.append(f"a VM restart is planned at {h.hm(restart)}: the job stops at {h.hm(cut)}")
    return stop, notes


def restart_cut(h, t, maint):
    """10 minutes before a planned restart, or None."""
    if maint is None or maint[1] is None:
        return None
    return maint[1] - h.MAINTENANCE_MARGIN


# --- mounts -----------------------------------------------------------------------

def _inside(path, root):
    """path is root or under it (both resolved)."""
    return bool(root) and (path == root or path.startswith(root.rstrip("/") + "/"))


def _first(path, root):
    """The first folder of path below root ('' for root itself)."""
    rest = path[len(root.rstrip("/")) + 1:] if path != root else ""
    return rest.split("/", 1)[0]


# Folders of the work folder no job may mount: the tools that enforce the rules, their locks,
# the scratch scripts and secrets, the browser runner's and worker-test's state.
WORK_NEVER = ("bin", "scratch", "e2e", "worker-test", "worker-test.slots")
RESERVED_DST = ("/", "/repo", "/srv/archive", "/srv/archive-prod", "/srv/sources", "/tmp", "/proc", "/sys",
                "/dev", "/etc", "/usr", "/bin", "/lib", "/sbin", "/var")


def check_mount(spec, roots):
    """'SRC:DST[:ro]' -> (src, dst, ro) with SRC resolved, or raise Refused. roots: work,
    scratch_root, prod_archive, cold_mount, dump_root, private (a list).

    Read-write: a folder under a folder of the work folder (not bin/, scratch/, e2e/,
    worker-test*/ or sources/), or under the cold drive's vm/ (not the scratch dumps).
    Read-only as well: production's archive, the downloaded sources, the cold drive (not the
    scratch dumps), the scratch archive. Never: private files, secrets, or a folder that
    holds any of those (a parent of one is refused because it isn't inside an allowed root)."""
    parts = spec.split(":")
    if len(parts) not in (2, 3) or not parts[0] or not parts[1] or (len(parts) == 3 and parts[2] != "ro"):
        raise Refused(f"--mount SRC:DST[:ro] (got {spec!r})")
    src, dst, ro = os.path.realpath(parts[0]), os.path.normpath(parts[1]), len(parts) == 3
    if not os.path.isabs(parts[1]) or "," in dst:
        raise Refused(f"--mount {spec}: DST must be an absolute path in the container")
    reserved = RESERVED_DST + ((roots["cold_mount"],) if roots.get("cold_mount") else ())
    if any(dst == r or (r != "/" and _inside(dst, r)) for r in reserved):
        raise Refused(f"--mount {spec}: {dst} is the job's own (pick another place, e.g. /mnt/in)")
    if not os.path.isdir(src):
        raise Refused(f"--mount {src}: no such folder (only folders can be mounted)")
    for p in roots.get("private") or ():
        if p and (_inside(src, p) or _inside(p, src)):
            raise Refused(f"--mount {src}: private files stay out of scratch jobs")
    work, scratch = roots.get("work"), roots.get("scratch_root")
    cold, dumps, prod = roots.get("cold_mount"), roots.get("dump_root"), roots.get("prod_archive")
    for root in (work, cold, prod):                     # a private or secrets folder below a root
        if root and _inside(src, root):
            below = set(src[len(root.rstrip("/")):].split("/"))
            if below & {"secrets", "private", "plugins-private", ".ssh"}:
                raise Refused(f"--mount {src}: private files and secrets stay out of scratch jobs")
    if dumps and _inside(src, dumps):
        raise Refused(f"--mount {src}: the scratch dumps (production's data) stay out of jobs")
    rw_ok = ro_ok = False
    if work and _inside(src, work) and src != work:
        top = _first(src, work)
        if top in WORK_NEVER or top.startswith("worker-test"):
            if scratch and _inside(src, os.path.join(scratch, "archive")) and src != os.path.join(scratch, "archive"):
                ro_ok = True                                    # another database's archive: read only
            else:
                raise Refused(f"--mount {src}: {os.path.join(work, top)} holds the tools, locks and secrets "
                              "that enforce the rules; it can't be mounted")
        elif top == "sources":
            ro_ok = True
        else:
            rw_ok = True
    if cold and _inside(src, cold):
        if src == cold or (dumps and _inside(dumps, src)):
            raise Refused(f"--mount {src}: it holds the scratch dumps; mount a folder beside them")
        if _inside(src, os.path.join(cold, "vm")) and src != os.path.join(cold, "vm"):
            rw_ok = True
        else:
            ro_ok = True
    if prod and _inside(src, prod):
        ro_ok = True
    if not (rw_ok or ro_ok):
        raise Refused(f"--mount {src}: only folders under {work}/ (read-write), the cold drive's vm/ "
                      f"(read-write), or read-only production's archive and the cold drive")
    if not rw_ok and not ro:
        raise Refused(f"--mount {src}: read-only only (add :ro)")
    return src, dst, ro


# --- the command line -------------------------------------------------------------

def _env_roots():
    return {"work": os.environ.get("WORK", "/srv/tvt/work"),
            "scratch_root": os.environ.get("SCRATCH_ROOT", "/srv/tvt/work/scratch"),
            "prod_archive": os.environ.get("PROD_ARCHIVE", "/srv/tvt/archive"),
            "cold_mount": os.environ.get("COLD_MOUNT") or None,
            "dump_root": os.environ.get("DUMP_ROOT") or None,
            "private": [p for p in os.environ.get("PRIVATE_DIRS", "").split(":") if p]}


def _real(roots):
    return {k: ([os.path.realpath(p) for p in v] if isinstance(v, list) else (os.path.realpath(v) if v else v))
            for k, v in roots.items()}


def main(argv, heavy=None):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "mount" and len(args) == 1:
            src, dst, ro = check_mount(args[0], _real(_env_roots()))
            print(f"{src}:{dst}" + (":ro" if ro else ""))
            return 0
        h = heavy or load_heavy(os.environ.get("HEAVY", "/srv/tvt/work/bin/heavy"))
        t = h.now()
        work = os.environ.get("WORK", h.WORK)
        if cmd == "quiet" and not args:
            return 0 if quiet(h, t) else 1
        if cmd == "restart-cut" and not args:
            cut = restart_cut(h, t, h.maintenance(t, work))
            if cut is not None:
                print(int(cut.timestamp() - getattr(h, "OFFSET", 0.0)))
            return 0
        if cmd == "light" and len(args) == 3 and all(a.isdigit() for a in args):
            statuses = h.read_statuses(os.environ.get("CAMERA_STATUS_DIR") or None)
            stop, notes = light_job(h, t, int(args[0]), int(args[1]), int(args[2]), statuses,
                                    h.maintenance(t, work))
            for note in notes:
                print(f"note: {note}", file=sys.stderr)
            print(int(stop.timestamp() - getattr(h, "OFFSET", 0.0)))
            return 0
    except Refused as err:
        print(err)
        return 1
    print(f"scratchq: unknown question {' '.join(argv)!r} (--help)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
