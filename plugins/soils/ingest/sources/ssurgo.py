"""The NRCS soil survey (SSURGO): the ten survey areas touching the map box. Loaded by hand, never scheduled.

The owner OKs each download (Oct 8, 2026: once now, then each October after NRCS's yearly refresh). The packages come
from the Web Soil Survey's download cache (one zip per survey area) and are unzipped into $TVT_SOURCES/ssurgo/data/;
the provenance (URLs, dates, sha256 of each zip, robots.txt checks) is kept beside them. This module makes no network
requests. Then:

    python plugins/soils/build/prepare.py --sources $TVT_SOURCES/ssurgo/data --out DIR    # worker image (GDAL)
    python3 -m ingest soils-load --from DIR                                               # ingest image

Licence: a U.S. government work in the public domain ("Access_Constraints: None"). The use constraints ask for USDA
NRCS credit in derived products and say the data isn't meant for regulatory decisions, which the soil card repeats.
"""

SOURCE = {
    "name": "ssurgo",
    "title": "USDA NRCS soil survey (SSURGO): the survey areas touching the map box",
    "url": "https://websoilsurvey.nrcs.usda.gov/",
    "access": "one_off",
    "schedule": None,    # by hand, with the owner's OK for each yearly download
    "license": "public domain",
    "credit": "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)",
    "notes": "Web Soil Survey packages downloaded by hand (ten survey areas: ID001, ID659, ID660, ID665, ID675, ID683, "
             "ID685, OR641, OR644, OR645), prepared in the worker image (plugins/soils/build/prepare.py) and loaded "
             "with python3 -m ingest soils-load. Not for regulatory decisions (NRCS's use constraints).",
}
