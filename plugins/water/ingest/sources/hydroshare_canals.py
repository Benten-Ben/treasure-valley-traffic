"""The Treasure Valley Irrigation System on HydroShare: a named canal, lateral and drain network (2022). Loaded by
hand, never scheduled (the water design; decision 19a).

Tatum, T., Bittmann, B., Stone, H., Kaiser, K. E. (2022). Treasure Valley Irrigation System, HydroShare,
https://doi.org/10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f. Licence CC BY 4.0: republishable with that credit, and
what we derive from it says "modified". Built at Idaho DEQ from an initial canal coverage, aerial imagery, the
irrigation entities and field checks (docs/sources/farm.md).

Downloaded once by hand on Oct 8, 2026, in a browser at the owner's request: hydroshare.org's robots.txt disallows its
download path (/django_irods/download/) and the page asks for the licence to be accepted. A static 2022 snapshot, so
there's no scripted refresh. This module makes no network requests. Then:

    python plugins/water/build/prepare.py hydroshare --zip $TVT_SOURCES/hydroshare/<id>.zip --out DIR
    python3 -m ingest hydroshare-load --from DIR/hydroshare.gpkg

It's evidence and names for the network, not geometry: water-build names the canals OpenStreetMap and NHD leave
unnamed, and counts where it agrees with them.
"""

DOI = "10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f"
URL = "https://www.hydroshare.org/resource/24a5f761bf4f41fb9b872b130d9d1a3f/"

SOURCE = {
    "name": "hydroshare_canals",
    "title": "Treasure Valley Irrigation System (HydroShare canal network, 2022)",
    "url": URL,
    "access": "one_off",
    "schedule": None,    # downloaded once by hand: the download path is closed to robots, behind a licence click
    "license": "CC BY 4.0",
    "credit": "Tatum, T., Bittmann, B., Stone, H., Kaiser, K. E. (2022), Treasure Valley Irrigation System, HydroShare, "
              f"doi:{DOI} (CC BY 4.0; modified)",
    "notes": "A zipped BagIt bag holding a 7z of one shapefile (2,988 lines; Call_Numbe, Name, Type), unpacked as "
             "untrusted data and prepared in the worker image (plugins/water/build/prepare.py hydroshare); loaded with "
             "python3 -m ingest hydroshare-load. Names and evidence for the canals.",
}
