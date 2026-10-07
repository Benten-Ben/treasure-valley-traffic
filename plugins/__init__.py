"""Plugins: one folder per subject (docs/15 §15.2).

Each plugins/<name>/ holds a plugin.json manifest, a README, its ingest code
(<name>/ingest/), its own migrations (<name>/migrations/) and its tests. The
ingest loader (ingest/manifest.py, ingest/sources/__init__.py) reads the
manifests; nothing here imports plugin code.

Private plugins live outside this repository (on the server,
/srv/tvt/plugins-private/). Put their parent folders on TVT_PLUGIN_PATH
(separated by os.pathsep) and they import as plugins.<name>, like the public
ones. A folder on the path that doesn't exist is skipped, so a build without
the private folder simply has no private plugins.
"""

import os

for _folder in os.environ.get("TVT_PLUGIN_PATH", "").split(os.pathsep):
    if _folder and os.path.isdir(_folder):
        _folder = os.path.abspath(_folder)
        if _folder not in (os.path.abspath(p) for p in __path__):
            __path__.append(_folder)
