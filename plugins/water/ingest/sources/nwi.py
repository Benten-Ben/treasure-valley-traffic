"""U.S. Fish and Wildlife Service, National Wetlands Inventory: the vegetated wetlands of the valley. Loaded by hand,
never scheduled (the owner's answer 2 of Oct 22, 2026; issue #82 made the one download).

The eight HU8 watershed files that touch the map box (October 2026 release, 336.8 MB) were downloaded once, cut to the
box and kept on the server as nwi_mapbox.gpkg with their provenance (the download times, sha256s and robots.txt
answers). This module makes no network requests. Then:

    python3 -m ingest nwi-load --from nwi_mapbox.gpkg
    python3 -m ingest nwi-presence --from shares.json      # the worker step's presence shares (wetlands.py)

Licence: a U.S. Government work, public domain. FWS asks for acknowledgement. The inventory uses a biological
definition of wetlands, is not a legal (regulatory) wetland boundary, and does not account for changes in the landscape
after it was mapped; over the valley floor it was mapped from July 1981 photos. A look for a new release each
October, alongside SSURGO's reload, each time with the owner's OK.
"""

URL = "https://www.fws.gov/program/national-wetlands-inventory/data-download"
INPUT_NOTE = "the eight HU8 watershed downloads of the October 2026 release (FWS National Wetlands Inventory)"

SOURCE = {
    "name": "nwi",
    "title": "U.S. Fish and Wildlife Service National Wetlands Inventory, vegetated palustrine wetlands (cut to the map box)",
    "url": URL,
    "access": "one_off",
    "schedule": None,    # by hand: a look each October with the owner's OK
    "license": "public domain",
    "credit": "U.S. Fish and Wildlife Service, National Wetlands Inventory",
    "notes": "The eight HU8 watershed files of the October 2026 release, cut to the map box (NAD83 Albers, read as "
             "WGS 84 by the ground's datum policy) and loaded with python3 -m ingest nwi-load. Not a legal "
             "(regulatory) wetland boundary; the valley floor was mapped from July 1981 photos.",
}
