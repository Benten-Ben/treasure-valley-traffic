#!/usr/bin/env python3
"""Build extruded-building tiles (buildings.pmtiles) for the valley from Overture Maps.

Overture's building footprints combine OpenStreetMap, Microsoft and other
sources; about 83% in the valley carry a height in meters. This reads the
release's GeoParquet files in place on Overture's public S3 bucket (no
download of the whole theme), keeps footprints in the valley, and tiles them
with tippecanoe. Buildings without a known height keep height = null: the
tiles carry only what the data says. The app draws those at an estimate
(num_floors x 3.2 m, else 4 m) in a lighter tone, and every building at
least 3 m tall (app/src/lib/map/buildings.ts; owner, Oct 7).

License: ODbL. Credit "Overture Maps Foundation, OpenStreetMap contributors".

Needs: pip install duckdb (it fetches its httpfs and spatial extensions), tippecanoe.

Usage:
  python3 basemap/buildings.py                          # -> data/tiles/buildings.pmtiles
  python3 basemap/buildings.py --release 2026-09-23.1 --bbox=-117.05,43.00,-115.95,43.85
"""

import argparse
import datetime
import json
import os
import subprocess
import time
import urllib.parse

import duckdb

BUCKET = "s3://overturemaps-us-west-2"
DEFAULT_RELEASE = "2026-09-23.1"


def connect():
    con = duckdb.connect()
    con.execute("INSTALL httpfs; INSTALL spatial; LOAD httpfs; LOAD spatial;")
    proxy = urllib.parse.urlparse(os.environ.get("HTTPS_PROXY", ""))
    if proxy.hostname:
        con.execute(f"SET http_proxy='{proxy.hostname}:{proxy.port}'")
    # Overture's bucket is public: read it anonymously, whatever AWS credentials
    # the environment happens to carry.
    con.execute(f"CREATE SECRET overture (TYPE s3, KEY_ID '', SECRET '', REGION 'us-west-2', SCOPE '{BUCKET}')")
    return con


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--release", default=DEFAULT_RELEASE)
    ap.add_argument("--bbox", default="-117.05,43.00,-115.95,43.85", help="west,south,east,north")
    ap.add_argument("--minzoom", type=int, default=14, help="lowest zoom with buildings")
    ap.add_argument("--maxzoom", type=int, default=15)
    ap.add_argument("--out", default=os.environ.get("TILES_DIR", "data/tiles"))
    ap.add_argument("--work", default="data/buildings")
    ap.add_argument("--skip-query", action="store_true", help="reuse the downloaded footprints in --work")
    args = ap.parse_args()

    w, s, e, n = (float(v) for v in args.bbox.split(","))
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    seq = os.path.join(args.work, "buildings.geojsonseq")
    t0 = time.time()
    if not args.skip_query:
        con = connect()
        src = f"{BUCKET}/release/{args.release}/theme=buildings/type=building/*"
        print(f"querying Overture {args.release} buildings in {args.bbox} ...", flush=True)
        con.execute(f"""
            COPY (
                SELECT round(height, 1) AS height,
                       round(min_height, 1) AS min_height,
                       num_floors,
                       geometry
                FROM read_parquet('{src}')
                WHERE bbox.xmin < {e} AND bbox.xmax > {w} AND bbox.ymin < {n} AND bbox.ymax > {s}
            ) TO '{seq}' WITH (FORMAT GDAL, DRIVER 'GeoJSONSeq')
        """)
        con.close()
    count = with_height = 0
    with open(seq) as f:                       # a quick scan; GDAL's reader is very slow here
        for line in f:
            line = line.strip().lstrip("\x1e")
            if line:
                count += 1
                with_height += json.loads(line)["properties"].get("height") is not None
    stats = (count, with_height)
    print(f"{stats[0]:,} buildings, {stats[1]:,} with height ({stats[1] / max(stats[0], 1):.0%}); "
          f"{time.time() - t0:.0f} s", flush=True)

    pm = os.path.join(args.out, "buildings.pmtiles")
    part = os.path.join(args.out, "buildings.part.pmtiles")   # tippecanoe picks the format by extension
    subprocess.run(["tippecanoe", "-q", "-f", "-o", part, "-l", "buildings",
                    f"-Z{args.minzoom}", f"-z{args.maxzoom}",
                    "--no-feature-limit", "--no-tile-size-limit", "--no-tile-stats",
                    "--attribution", "Overture Maps Foundation, © OpenStreetMap contributors",
                    seq], check=True)
    os.replace(part, pm)

    path = os.path.join(args.out, "manifest.json")
    m = json.load(open(path)) if os.path.exists(path) else {}
    m["buildings"] = {"file": "buildings.pmtiles", "sourceLayer": "buildings", "minzoom": args.minzoom,
                      "attribution": "Overture Maps Foundation, © OpenStreetMap contributors",
                      "built": datetime.date.today().isoformat(),
                      "source": f"Overture Maps {args.release}, theme=buildings/type=building",
                      "count": stats[0], "withHeight": stats[1]}
    json.dump(m, open(path, "w"), indent=1)
    print(f"wrote {pm} ({os.path.getsize(pm) / 1e6:.0f} MB) and updated {path}; total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
