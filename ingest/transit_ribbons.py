"""Moved to the transit plugin (plugins/transit/ingest/transit_ribbons.py): use `python3 -m ingest transit-ribbons`.

This shim keeps `python3 -m ingest.transit_ribbons` working while the server and
the docs catch up (docs/15 §15.6, step 1). Remove it once nothing calls the
old name.
"""

import sys

if __name__ == "__main__":
    print("ingest.transit_ribbons moved: use `python3 -m ingest transit-ribbons` (plugins/transit)", file=sys.stderr,
          flush=True)
    from plugins.transit.ingest import transit_ribbons
    sys.exit(transit_ribbons.main(sys.argv[1:]))
