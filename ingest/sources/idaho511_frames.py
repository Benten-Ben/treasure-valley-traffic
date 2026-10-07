"""Moved to the cameras plugin (plugins/cameras/ingest/sources/idaho511_frames.py).

Kept only because app/src/lib/server/archive.test.ts runs
`from ingest.sources.idaho511_frames import write_status`; this is the same
module under its old name. Remove it when the app moves to plugins (docs/15
§15.6, step 2). Not registered: the loader reads plugin manifests.
"""

import sys

from plugins.cameras.ingest.sources import idaho511_frames

sys.modules[__name__] = idaho511_frames
