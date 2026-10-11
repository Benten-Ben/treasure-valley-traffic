"""USDA NAIP: the summer photo whose near-infrared tells a green shrub (bush) from one that isn't (sage), docs/19 §19.8.

Public domain (a U.S. Government work): credit "USDA NAIP". Listed in plugin.json as a manual source, for its
licence: this module makes no network requests and has no schedule. The photo's 4-band crops (red, green, blue,
near-infrared; NAIP 2025, or 2023 where 2025's isn't held) are read on the project's server by
plugins/trees/build/build_shrubs.py (--photo) in the worker image, which measures each area's shift onto the lidar
and its own green cut. Nothing from the photo is stored but each shrub's look and green share."""

SOURCE = {
    "name": "usda_naip",
    "title": "USDA NAIP: the shrubs' near-infrared",
    "url": "https://www.fsa.usda.gov/programs-and-services/aerial-photography/imagery-programs/naip-imagery/",
    "access": "open",
    "schedule": None,   # by hand: crops of the photo held on the project's server
    "license": "public domain (U.S. Government work)",
    "credit": "USDA NAIP",
    "notes": "NAIP 2025 (2023 where 2025's crop isn't held) 4-band photo crops over the shrub areas, read by the "
             "shrubs build for NDVI.",
}
