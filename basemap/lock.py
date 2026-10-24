"""The tile build's locks, kept out of the served tiles folder.

The basemap build (build.sh), the ground paint (ground/tiles.py) and the landscape bake (landscape/plan.py, bake.py)
each rewrite tiles/manifest.json, and a bake holds the landscape lock for its whole run. The lock files are empty and
live in one folder of their own, so the tiles folder (served at /tiles/) holds only what the app may fetch.

The folder is $TVT_TILES_LOCK_DIR. Unset, it is data/locks in the project's main checkout (a worktree uses its main
checkout's, so parallel worktrees on the laptop still queue). On the server the heavy jobs and Compose set it to a
folder under the work area (deploy/README.md sets it). A worker run mounts the checkout read-only, so there the
variable must name a writable folder: ensure() checks that up front and says so.

The folder is setgid and shared by the job users, so a lock file is made mode 0o664 (whatever the umask), and ensure()
opens every lock a run takes read-write, so a file another user left at 0o644 fails at the start, naming the file.

A run that writes a tiles folder says which (ensure(tiles=...), locked(name, tiles=...)). When that folder is outside
the main checkout and the variable is unset, the run refuses: the default folder would be an unshared one in the
checkout, and a bake running elsewhere would never see its locks (deploy/README.md, "The tiles folder's locks").

From a shell (macOS has no flock(1)): `python3 -m basemap.lock [--tiles DIR] NAME -- COMMAND ...` takes the lock,
runs the command, releases the lock and exits with the command's status. --tiles names the folder the command
writes, for the check above; the command line states it, the environment is not read for it.
"""
import errno
import fcntl
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager

ENV = "TVT_TILES_LOCK_DIR"
LANDSCAPE = "landscape.lock"      # a landscape bake, start to end
MANIFEST = "manifest.lock"        # one read-modify-write of tiles/manifest.json
LOCKS = (LANDSCAPE, MANIFEST)     # the locks a run takes; ensure() opens each up front
MODE = 0o664                      # the folder is setgid, so the group is shared


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


def _checkout():
    return _main_checkout(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def lock_dir():
    d = os.environ.get(ENV)
    if d:
        return d
    return os.path.join(_checkout(), "data", "locks")


def _check_shared(tiles):
    """Refuse a tiles folder outside the main checkout when the variable is unset (see the module note)."""
    if not tiles or os.environ.get(ENV):
        return
    root = os.path.realpath(_checkout())
    path = os.path.realpath(tiles)
    if os.path.commonpath([root, path]) != root:
        raise OSError(errno.EINVAL, f"the tiles folder {tiles} is outside the checkout, so {ENV} must be set: "
                                    f"without it the lock is an unshared one in the checkout's data/locks, which a "
                                    f"bake running elsewhere never sees (deploy/README.md, \"The tiles folder's "
                                    f"locks\")")


def _open(path):
    """Open (creating if missing) a lock file read-write. A file made here gets MODE exactly: os.open's mode is
    masked by the umask (022 gives 0o644), so it is made under a temporary name, set to MODE, and linked into place,
    so no other user ever sees it at the wrong mode (a second job user starting at the same time would fail to open it).
    The temporary name is random, not the pid: in a worker container the job is often pid 1, so two containers would
    share a pid-named file."""
    try:
        return os.open(path, os.O_RDWR)
    except FileNotFoundError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path))
    try:
        os.fchmod(fd, MODE)
        try:
            os.link(tmp, path)
        except FileExistsError:
            os.close(fd)
            fd = os.open(path, os.O_RDWR)
    except OSError:
        os.close(fd)
        raise
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return fd


def ensure(tiles=None):
    """Make the lock folder and prove it writable now, so a run that would fail at the end fails at the start.
    Also open each lock the run will take, so a file another user left unwritable fails here, naming it. `tiles` is
    the tiles folder the run writes, if any (see the module note)."""
    _check_shared(tiles)
    d = lock_dir()
    try:
        os.makedirs(d, exist_ok=True)
        if not os.access(d, os.W_OK):
            raise PermissionError(13, "not writable", d)
    except OSError as err:
        raise OSError(err.errno, f"the lock folder {d} is not usable ({err.strerror}): set {ENV} to a writable "
                                 f"folder (e.g. one under the work area)") from err
    for name in LOCKS:
        path = os.path.join(d, name)
        try:
            os.close(_open(path))
        except OSError as err:
            raise OSError(err.errno, f"the lock file {path} can't be opened for writing ({err.strerror}): "
                                     f"make it writable by the job users (chmod 664 it, or remove it so it is "
                                     f"recreated)") from err
    return d


@contextmanager
def locked(name, tiles=None):
    """An exclusive lock on the file `name` in the lock folder, held for the block (it waits for another holder).
    `tiles` is the tiles folder the block writes, if any."""
    if not name or os.path.basename(name) != name:
        raise ValueError(f"a lock name is a bare file name, not {name!r}")
    d = ensure(tiles)
    fd = _open(os.path.join(d, name))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def main(argv):
    tiles = None
    if len(argv) >= 2 and argv[0] == "--tiles":
        tiles, argv = argv[1], argv[2:]
    if len(argv) < 3 or argv[1] != "--":
        print("usage: python3 -m basemap.lock [--tiles DIR] NAME -- COMMAND [ARG ...]", file=sys.stderr)
        return 2
    try:
        with locked(argv[0], tiles):
            return subprocess.call(argv[2:])
    except (ValueError, OSError) as err:
        print(f"basemap.lock: {err}", file=sys.stderr)
        return 127 if isinstance(err, FileNotFoundError) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
