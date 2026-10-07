"""Load an OpenStreetMap extract the owner downloaded by hand (sources/osm_valley.py).

    python3 -m ingest osm-load --inbox          # the newest file in $TVT_ARCHIVE/osm/inbox/
    python3 -m ingest osm-load --file PATH      # a .osm.pbf (or OSM XML) file anywhere

Geofabrik's robots.txt disallows scripted downloads of its extracts, so the
weekly extract is downloaded by hand in a browser (owner, Oct 6, 2026),
copied into the inbox, and loaded with this command, which is the only way
OpenStreetMap data comes in. It registers the source, logs the load in
ops.fetch, and moves the file into $TVT_ARCHIVE/osm/ (the last two are
kept). If its .md5 file sits next to it, the MD5 is checked first. Loading
the same extract twice is skipped unless you pass --force.
"""

import argparse
import os
import sys

from ingest import db
from .sources import osm_valley


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest osm-load", description=__doc__.splitlines()[0])
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--inbox", action="store_true", help="load the newest extract in $TVT_ARCHIVE/osm/inbox/")
    which.add_argument("--file", help="load this .osm.pbf or OSM XML file")
    ap.add_argument("--force", action="store_true", help="load it even if it's the extract loaded last time")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="retire ways even when this extract has fewer than half the active ones")
    args = ap.parse_args(argv)

    path = args.file
    if args.inbox:
        if not os.environ.get("TVT_ARCHIVE"):
            sys.exit("set TVT_ARCHIVE (the inbox is $TVT_ARCHIVE/osm/inbox/)")
        folder = osm_valley.archive_dir()
        path = osm_valley.inbox_file(folder)
        if not path:
            sys.exit(f"no .osm.pbf, .osm, .osm.bz2 or .osm.gz file in {folder}/inbox/")
    with db.connect() as conn:
        stats = osm_valley.load_file(conn, path, force=args.force, allow_shrink=args.allow_shrink)
        conn.commit()
    print("osm_valley: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)


if __name__ == "__main__":
    main()
