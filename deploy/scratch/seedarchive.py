#!/usr/bin/env python3
"""seedarchive: each scratch database's archive and the load state in it (landscape sprint plan, F6).

A loader that skips "the same extract as the last load" keeps that state as a file in its
archive folder (osm_valley's osm/last-loaded.json; S1's consumers, if they keep theirs in
files, osm/state/). On scratch the state has to describe the database it sits beside, or a
load is skipped against rows the database doesn't have. So refresh.sh:

  1. snapshots production's load state into the dump folder *before* the dump starts, and
     again after it. The earlier snapshot is the one kept: the state can then only be older
     than the dumped database, never newer. A load that finished during the dump runs again
     on scratch (as with --force); it's never skipped. The second snapshot only tells whether
     that happened (meta.json says so).
  2. stages the database's new archive: production's held files as they are now (the
     extracts and their .md5 files) and the load state from the dump's snapshot, whatever
     production's state is by then (a --from-dump restore may come days later).

  seedarchive.py snapshot PROD_ARCHIVE DEST DIR...        the load state of each DIR, into DEST/DIR/
  seedarchive.py same A B                                  exit 0 if two snapshots match, 1 if not
                                                           (what differs, on stdout)
  seedarchive.py stage PROD_ARCHIVE STATE|- STAGE DIR...   a new archive in STAGE (STATE '-': none)

What's load state in an archive folder DIR: its state/ folder and the *.json files at its top.
Its held files: the other files at its top. Never copied: inbox/ (made empty), other folders
(a loader's temporary work), hidden files, partial files (*.part) and symbolic links.

Exit 0: done; 1: the snapshots differ (same); 2: usage or an error.
Tests: deploy/scratch/tests/test_seedarchive.py.
"""
import hashlib
import os
import shutil
import sys

STATE_DIR = "state"
INBOX = "inbox"


def _copy(src, dst):
    """A file's bytes and times; its mode comes from the umask (refresh.sh's 077: the dumps and
    archives are the server user's only)."""
    shutil.copyfile(src, dst)
    st = os.stat(src)
    os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))


def _skipped(name):
    return name.startswith(".") or name.endswith(".part")


def is_state_file(name):
    """A load-state file at the top of an archive folder."""
    return name.endswith(".json")


def _top_files(folder):
    """The plain files at folder's top (no links, hidden or partial files), by name."""
    try:
        entries = sorted(os.scandir(folder), key=lambda e: e.name)
    except FileNotFoundError:
        return []
    return [e for e in entries if not _skipped(e.name) and e.is_file(follow_symlinks=False)]


def copy_state(src, dest):
    """src's load state (top-level *.json, and state/) into dest. Returns what was copied
    (paths relative to dest), sorted."""
    copied = []
    for e in _top_files(src):
        if is_state_file(e.name):
            os.makedirs(dest, exist_ok=True)
            _copy(e.path, os.path.join(dest, e.name))
            copied.append(e.name)
    top = os.path.join(src, STATE_DIR)
    if os.path.isdir(top) and not os.path.islink(top):
        for root, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if not _skipped(d) and not os.path.islink(os.path.join(root, d)))
            rel = os.path.relpath(root, src)
            os.makedirs(os.path.join(dest, rel), exist_ok=True)
            for name in sorted(files):
                path = os.path.join(root, name)
                if _skipped(name) or os.path.islink(path) or not os.path.isfile(path):
                    continue
                _copy(path, os.path.join(dest, rel, name))
                copied.append(os.path.join(rel, name))
    return sorted(copied)


def snapshot(prod, dest, dirs):
    """The load state of each archive folder in dirs, from prod into dest/<dir>/. dest is made
    even when there's no state (an empty snapshot means: none). Returns {dir: [files]}."""
    os.makedirs(dest, exist_ok=True)
    return {d: copy_state(os.path.join(prod, d), os.path.join(dest, d)) for d in dirs}


def _digests(root):
    out = {}
    for path, dirs, files in os.walk(root):
        dirs.sort()
        for name in files:
            p = os.path.join(path, name)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return out


def differences(a, b):
    """What differs between two snapshots (relative paths), sorted; [] if they match."""
    da, db = _digests(a), _digests(b)
    return sorted(p for p in set(da) | set(db) if da.get(p) != db.get(p))


def stage(prod, state, out, dirs):
    """A database's new archive in out: for each archive folder in dirs that production has,
    its held files now, an empty inbox/, and the load state from state/<dir>/ (state None:
    none). Returns {dir: (held files, state files)}."""
    done = {}
    os.makedirs(out, exist_ok=True)
    for d in dirs:
        src = os.path.join(prod, d)
        if not os.path.isdir(src):
            continue
        dest = os.path.join(out, d)
        os.makedirs(os.path.join(dest, INBOX), exist_ok=True)
        held = []
        for e in _top_files(src):
            if not is_state_file(e.name):
                _copy(e.path, os.path.join(dest, e.name))
                held.append(e.name)
        kept = copy_state(os.path.join(state, d), dest) if state else []
        done[d] = (held, kept)
    return done


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "snapshot" and len(args) >= 3:
            got = snapshot(args[0], args[1], args[2:])
            for d, files in got.items():
                print(f"seedarchive: {d}'s load state: {', '.join(files) or 'none'}", file=sys.stderr)
            return 0
        if cmd == "same" and len(args) == 2:
            diff = differences(args[0], args[1])
            if diff:
                print(", ".join(diff))
                return 1
            return 0
        if cmd == "stage" and len(args) >= 4:
            state = None if args[1] == "-" else args[1]
            if state and not os.path.isdir(state):
                raise FileNotFoundError(f"no snapshot of the load state at {state}")
            for d, (held, kept) in stage(args[0], state, args[2], args[3:]).items():
                print(f"seedarchive: {d}: {len(held)} held file(s) from production now; load state "
                      + (f"from the dump: {', '.join(kept) or 'none'}" if state else "none (no snapshot)"),
                      file=sys.stderr)
            return 0
    except OSError as err:
        print(f"seedarchive: {err}", file=sys.stderr)
        return 2
    print(f"seedarchive: unknown command {' '.join(argv)!r} (--help)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
