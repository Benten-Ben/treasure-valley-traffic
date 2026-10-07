"""Moved to the transit plugin (plugins/transit/ingest/transit_progress.py): use `python3 -m ingest transit-progress`.

This shim keeps `python3 -m ingest.transit_progress` working while the server and
the docs catch up (docs/15 §15.6, step 1). Remove it once nothing calls the
old name.
"""

import sys

if __name__ == "__main__":
    print("ingest.transit_progress moved: use `python3 -m ingest transit-progress` (plugins/transit)", file=sys.stderr,
          flush=True)
    from plugins.transit.ingest import transit_progress
    sys.exit(transit_progress.main(sys.argv[1:]))
