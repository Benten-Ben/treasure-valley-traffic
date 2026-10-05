"""Registered sources.

SOURCES run once per call (`run`), or on their schedule (`serve`), in this
order (`run all` loads cameras before their views). STREAMS run continuously
(`stream`), each as its own service.
"""

from . import achd_cameras, achd_roads, idaho511_views, vrt_gtfs, vrt_realtime

SOURCES = {m.SOURCE["name"]: m for m in (achd_cameras, idaho511_views, vrt_gtfs, achd_roads)}
STREAMS = {m.SOURCE["name"]: m for m in (vrt_realtime,)}
