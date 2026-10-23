# The tests' lock folder: a temporary one (the checkout may be read-only, as in the worker image).
import atexit
import os
import shutil
import tempfile

if not os.environ.get("TVT_TILES_LOCK_DIR"):
    _locks = tempfile.mkdtemp(prefix="tvt-locks-")
    os.environ["TVT_TILES_LOCK_DIR"] = _locks
    atexit.register(shutil.rmtree, _locks, True)
