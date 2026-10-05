#!/usr/bin/env python3
"""Write ACHD's camera locations to GeoJSON, for imagery.py's detail areas.

Reads ACHD's GIS camera layer (automated access allowed; the host has no
robots.txt), merges the 4 cameras listed twice, and writes one point per
camera. Standard library only.

Usage:
  python3 basemap/camera_points.py                 # -> data/cameras/cameras.geojson
  python3 basemap/camera_points.py --out other.geojson
"""

import argparse
import json
import os
import urllib.request

URL = ("https://gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer/26/query"
       "?where=1%3D1&outFields=camID,label&returnGeometry=true&outSR=4326&f=geojson")
USER_AGENT = ("treasure-valley-traffic/0.2 "
              "(public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="data/cameras/cameras.geojson")
    args = ap.parse_args()
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    data = json.load(urllib.request.urlopen(req, timeout=90))
    cams = {}
    for f in data["features"]:
        if f.get("geometry") and f["properties"].get("camID") is not None:
            cams.setdefault(int(f["properties"]["camID"]), f)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": list(cams.values())}, fh)
    print(f"{len(data['features'])} records, {len(cams)} cameras -> {args.out}")


if __name__ == "__main__":
    main()
