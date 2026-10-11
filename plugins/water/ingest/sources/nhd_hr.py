"""USGS NHD High Resolution, HU4 1705 (Middle Snake): the valley's mapped streams, canals, ponds and springs. Loaded
by hand, never scheduled (the water design; decision 19c).

The owner approved two downloads of one file: on Oct 8, 2026 (the cut kept as sources/nhd/nhd_mapbox.gpkg, without
NHDFlow) and once more on Oct 11 to keep NHDFlow, from the same S3 URL (same ETag and sha256: the product published
2023-12-09). The provenance (URLs, times, robots.txt answers, sha256) is kept beside the file on the server. This
module makes no network requests. Then:

    python plugins/water/build/prepare.py nhd --zip $TVT_SOURCES/nhd/download/NHD_H_1705_HU4_GDB.zip --out DIR
    python3 -m ingest nhd-load --from DIR/nhd.gpkg

Licence: a U.S. Government work, public domain. Credit "USGS National Hydrography Dataset". Its geometry is mostly
1:24,000 topo-era, with Lower Boise canal updates in 2013-15: NHD-only canals may since have been piped or built over,
which the map says. Check for a new HU4 product or 3DHP work units over the box about once a year (the 3DHP service had
none on Sep 4, 2026).
"""

URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Hydrography/NHD/HU4/GDB/NHD_H_1705_HU4_GDB.zip"

SOURCE = {
    "name": "nhd_hr",
    "title": "USGS National Hydrography Dataset, High Resolution, HU4 1705 (cut to the map box)",
    "url": URL,
    "access": "one_off",
    "schedule": None,    # by hand: about once a year, a new HU4 product or 3DHP, with the owner's OK
    "license": "public domain",
    "credit": "USGS National Hydrography Dataset",
    "notes": "The HU4 1705 File Geodatabase (product of 2023-12-09), prepared in the worker image "
             "(plugins/water/build/prepare.py nhd) and loaded with python3 -m ingest nhd-load. NAD83 read as WGS 84 "
             "(the ground's datum policy). Mostly 1:24,000 topo-era geometry.",
}
