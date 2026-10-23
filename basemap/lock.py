"""The tile build's locks, kept out of the served tiles folder.

The basemap build (build.sh), the ground paint (ground/tiles.py) and the landscape bake (landscape/plan.py, bake.py)
each rewrite tiles/manifest.json, and a bake holds the landscape lock for its whole run. The lock files are empty and
live in one folder of their own, so the tiles folder (served at /tiles/) holds only what the app may fetch.

The folder is $TVT_TILES_LOCK_DIR. Unset, it is data/locks in the project's main checkout (a worktree uses its main
checkout's, so parallel worktrees on the laptop still queue). On the server the heavy jobs and Compose set it to a
folder under the work area (deploy/README.md).
Nothing in deploy/ sets it yet, and a worker run mounts the checkout read-only, so there the variable must name a
writable folder: ensure() checks that up front and says so.

From a shell (macOS has no flock(1)): `python3 -m basemap.lock manifest.lock -- COMMAND ...` takes the lock, runs
the command, releases the lock and exits with the command's status.
"""
import fcntl
import os
import subprocess
import sys
from contextlib import contextmanager

ENV = "TVT_TILES_LOCK_DIR"
LANDSCAPE = "landscape.lock"      # a landscape bake, start to end
MANIFEST = "manifest.lock"        # one read-modify-write of tiles/manifest.json


def _main_checkout(root):
    """The checkout that owns root's git data: root itself, or for a linked worktree the main checkout."""
    dot = os.path.join(root, ".git")
    if os.path.isfile(dot):
        try:
            with open(dot, encoding="utf-8") as f:
                gitdir = f.read().strip().removeprefix("gitdir:").strip()
            with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as f:
                common = f.read().strip()
            return os.path.dirname(os.path.normpath(os.path.join(gitdir, common)))
        except OSError:
            pass
    return root


def lock_dir():
    d = os.environ.get(ENV)
    if d:
        return d
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(_main_checkout(root), "data", "locks")


def ensure():
    """Make the lock folder and prove it writable now, so a run that would fail at the end fails at the start."""
    d = lock_dir()
    try:
        os.makedirs(d, exist_ok=True)
        if not os.access(d, os.W_OK):
            raise PermissionError(13, "not writable", d)
    except OSError as err:
        raise OSError(err.errno, f"the lock folder {d} is not usable ({err.strerror}): set {ENV} to a writable "
                                 f"folder (e.g. one under the work area)") from err
    return d


@contextmanager
def locked(name):
    """An exclusive lock on the file `name` in the lock folder, held for the block (it waits for another holder)."""
    if not name or os.path.basename(name) != name:
        raise ValueError(f"a lock name is a bare file name, not {name!r}")
    d = ensure()
    fd = os.open(os.path.join(d, name), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def main(argv):
    if len(argv) < 3 or argv[1] != "--":
        print("usage: python3 -m basemap.lock NAME -- COMMAND [ARG ...]", file=sys.stderr)
        return 2
    try:
        with locked(argv[0]):
            return subprocess.call(argv[2:])
    except (ValueError, OSError) as err:
        print(f"basemap.lock: {err}", file=sys.stderr)
        return 127 if isinstance(err, FileNotFoundError) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
