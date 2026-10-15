"""Moved: use `python3 -m ingest osm-load` (core's loader, ingest/osm_extract.py).

This shim keeps `python3 -m ingest.osm_load --inbox|--file PATH` working
while the server and the docs catch up (docs/15 §15.6, step 1). Remove it
once nothing calls the old name.
"""

import sys

if __name__ == "__main__":
    print("ingest.osm_load moved: use `python3 -m ingest osm-load` (ingest/osm_extract.py)", file=sys.stderr, flush=True)
    from ingest import osm_extract
    sys.exit(osm_extract.main(sys.argv[1:]))
