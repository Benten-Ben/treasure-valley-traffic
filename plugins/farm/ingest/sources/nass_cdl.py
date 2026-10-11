"""USDA NASS Cropland Data Layer (CDL): crop and land-cover pixels by year. Loaded by hand, never scheduled.

The owner OKs each year's download (Oct 8, 2026: 2019, 2020 and 2023 at 30 m, 2024 and 2025 at 10 m; each later year,
about late February, with its own OK). The clips on the CDL's own grid, the legend and NASS's Idaho accuracy workbook
are kept in $TVT_SOURCES/cdl/ with their provenance. This module makes no network requests. Then:

    python3 -m ingest farm-cdl-load --cdl $TVT_SOURCES/cdl/out --accuracy $TVT_SOURCES/cdl/docs/NASS_CDL_ID25_accuracy.xlsx

which loads farm.crop_class (names, NASS colours, our crop groups, AgriMet crops, Idaho accuracy) and copies the
rasters into $TVT_ARCHIVE/farm/cdl/, indexed in farm.cdl_year. They're inputs to the worker build, not map tiles.

Licence: the metadata's Use_Constraints call the CDL "public domain and free to redistribute". 2024 on is NASS's new
10 m method; earlier years are 30 m, and the change moves hay into grass/pasture and developed land up, which the
field card says.
"""

SOURCE = {
    "name": "nass_cdl",
    "title": "USDA NASS Cropland Data Layer (crop pixels by year)",
    "url": "https://www.nass.usda.gov/Research_and_Science/Cropland/Release/index.php",
    "access": "one_off",
    "schedule": None,    # by hand, with the owner's OK for each yearly download
    "license": "public domain",
    "credit": "USDA NASS Cropland Data Layer",
    "notes": "Clips of the national rasters on the CDL's own grid (EPSG:5070): 2019, 2020, 2023 at 30 m; 2024, 2025 "
             "at 10 m (NASS's new method). Inputs to the crop-fields build (agreement, crop cover), never served "
             "as tiles. Loaded with python3 -m ingest farm-cdl-load.",
}
