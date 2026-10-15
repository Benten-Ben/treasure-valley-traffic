"""USGS 3DEP lidar: the heights every tree is found and measured in (docs/19 §19.3, §19.5).

Public domain (a U.S. Government work): credit "U.S. Geological Survey, 3D Elevation Program". Listed in plugin.json
as a manual source, for its licence: this module makes no network requests and has no schedule. The lidar tiles are
fetched by hand on the project's server (robots.txt checked, our User-Agent, paced) and made into height products there
(0.5 m DSM and DTM in UTM 11N, docs/18); plugins/trees/build/build.py reads those products (--dsm, --dtm) in the
worker image. Trees exist only where the products do (the ten test boxes so far)."""

SOURCE = {
    "name": "usgs_3dep_lidar",
    "title": "USGS 3DEP lidar: the trees' heights and crowns",
    "url": "https://www.usgs.gov/3d-elevation-program",
    "access": "open",
    "schedule": None,   # by hand: the products are made on the server and read by the build
    "license": "public domain (U.S. Government work)",
    "credit": "U.S. Geological Survey, 3D Elevation Program",
    "notes": "QL1 lidar (2023-24) and, in some test boxes, older 3DEP surveys; height products made on the project's "
             "server and read by the trees build.",
}
