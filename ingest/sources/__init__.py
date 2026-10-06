"""Registered sources.

SOURCES run once per call (`run`), or on their schedule (`serve`), in this
order (`run all` loads cameras before their views). STREAMS run continuously
(`stream`), each as its own service.
"""

from . import (achd_cameras, achd_roads, compass_congestion, compass_counts, compass_crashes, compass_growth,
               compass_plats, idaho511_api, idaho511_frames, idaho511_views, itd_wzdx, vrt_gtfs, vrt_realtime)

SOURCES = {m.SOURCE["name"]: m for m in (achd_cameras, idaho511_views, vrt_gtfs, achd_roads,
                                         compass_crashes, compass_counts, compass_growth, compass_plats,
                                         compass_congestion)}
STREAMS = {m.SOURCE["name"]: m for m in (vrt_realtime, idaho511_frames, itd_wzdx, idaho511_api)}
