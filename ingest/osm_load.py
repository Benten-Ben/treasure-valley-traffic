"""Moved to the roads plugin (plugins/roads/ingest/osm_load.py): use `python3 -m ingest osm-load`.

This shim keeps `python3 -m ingest.osm_load --inbox|--file PATH` working
while the server and the docs catch up (docs/15 §15.6, step 1). Remove it
once nothing calls the old name.
"""

import sys

if __name__ == "__main__":
    print("ingest.osm_load moved: use `python3 -m ingest osm-load` (plugins/roads)", file=sys.stderr, flush=True)
    from plugins.roads.ingest import osm_load
    sys.exit(osm_load.main(sys.argv[1:]))
