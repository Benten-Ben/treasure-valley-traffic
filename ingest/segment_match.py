"""Moved to the roads plugin (plugins/roads/ingest/segment_match.py): use `python3 -m ingest segment-match`.

This shim keeps `python3 -m ingest.segment_match [names...]` working while
the server and the docs catch up (docs/15 §15.6, step 1). Remove it once
nothing calls the old name.
"""

import sys

if __name__ == "__main__":
    print("ingest.segment_match moved: use `python3 -m ingest segment-match` (plugins/roads)", file=sys.stderr,
          flush=True)
    from plugins.roads.ingest import segment_match
    sys.exit(segment_match.main(sys.argv[1:]))
