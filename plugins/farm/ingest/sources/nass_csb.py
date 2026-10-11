"""USDA NASS Crop Sequence Boundaries (CSB): the field outlines and their crop history. Loaded by hand, never scheduled.

The owner OKs each edition's download (Oct 8, 2026: the 2018-2025 edition now; each later one, about late March, with
its own OK). The national file (a 3.8 GB zip holding a File Geodatabase) is cut to the map box in the worker image and
kept as a GeoPackage in $TVT_SOURCES/csb/, with its provenance (URL, Last-Modified, sha256, robots.txt check) beside it.
This module makes no network requests. Then:

    python3 -m ingest farm-csb-load --gpkg $TVT_SOURCES/csb/csb_mapbox.gpkg --edition csb-2018-2025-rev23

Licence: the metadata's Use_Constraints call CSB "public domain and free to redistribute". The outlines are modelled
from the Cropland Data Layer's 30 m pixels, so the map calls them "estimated fields".
"""

SOURCE = {
    "name": "nass_csb",
    "title": "USDA NASS Crop Sequence Boundaries (field outlines and eight years of crops)",
    "url": "https://www.nass.usda.gov/Research_and_Science/Crop-Sequence-Boundaries/index.php",
    "access": "one_off",
    "schedule": None,    # by hand, with the owner's OK for each yearly edition
    "license": "public domain",
    "credit": "USDA NASS Crop Sequence Boundaries",
    "notes": "The national edition (File Geodatabase in a zip) cut to the map box by hand in the worker image and "
             "loaded with python3 -m ingest farm-csb-load. Field outlines are modelled from 30 m CDL pixels: "
             "estimated fields. Never joined to the Assessor's parcels in anything public.",
}
