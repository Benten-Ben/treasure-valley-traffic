#!/usr/bin/env python3
"""Write ACHD's camera locations (or COMPASS's signals) to GeoJSON, for imagery.py's detail areas.

Reads ACHD's GIS camera layer (automated access allowed; the host has no
robots.txt), merges the 4 cameras listed twice, and writes one point per
camera. With --signals, writes COMPASS's 585 signalized intersections
instead (ArcGIS Online, no robots rules), as bare points: the layer is
internal-only until COMPASS answers, so nothing but the locations is kept,
and only locally. Standard library only.

Usage:
  python3 basemap/camera_points.py                 # -> data/cameras/cameras.geojson
  python3 basemap/camera_points.py --signals       # -> data/imagery/points/compass-signals.geojson
  python3 basemap/camera_points.py --out other.geojson
"""

import argparse
import json
import os
import urllib.request

URL = ("https://gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer/26/query"
       "?where=1%3D1&outFields=camID,label&returnGeometry=true&outSR=4326&f=geojson")
SIGNALS_URL = ("https://services6.arcgis.com/2S9FP4vfcUQQ8G1T/arcgis/rest/services/Signalized_Intersections/"
               "FeatureServer/0/query?where=1%3D1&outFields=OBJECTID&returnGeometry=true&outSR=4326"
               "&resultRecordCount=2000&f=geojson")
USER_AGENT = ("treasure-valley-traffic/0.2 "
              "(public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return json.load(urllib.request.urlopen(req, timeout=90))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--signals", action="store_true", help="COMPASS's signalized intersections instead")
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.signals:
        out = args.out or "data/imagery/points/compass-signals.geojson"
        data = fetch(SIGNALS_URL)
        feats = [{"type": "Feature", "properties": {}, "geometry": f["geometry"]}
                 for f in data["features"] if f.get("geometry")]
        note = f"{len(data['features'])} records, {len(feats)} signals"
    else:
        out = args.out or "data/cameras/cameras.geojson"
        data = fetch(URL)
        cams = {}
        for f in data["features"]:
            if f.get("geometry") and f["properties"].get("camID") is not None:
                cams.setdefault(int(f["properties"]["camID"]), f)
        feats = list(cams.values())
        note = f"{len(data['features'])} records, {len(cams)} cameras"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as fh:
        json.dump({"type": "FeatureCollection", "features": feats}, fh)
    print(f"{note} -> {out}")


if __name__ == "__main__":
    main()
