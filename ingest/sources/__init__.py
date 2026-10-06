"""Registered sources.

SOURCES run once per call (`run`), or on their schedule (`serve`), in this
order (`run all` loads cameras before their views, and ACHD's roads before
the lane inventories matched to them). STREAMS run continuously (`stream`),
each as its own service.
"""

from . import (achd_cameras, achd_msm, achd_roads, compass_centerline, idaho511_api, idaho511_frames,
               idaho511_views, itd_hpms, itd_wzdx, vrt_gtfs, vrt_realtime)

SOURCES = {m.SOURCE["name"]: m for m in (achd_cameras, idaho511_views, vrt_gtfs, achd_roads, itd_hpms, achd_msm,
                                         compass_centerline)}
STREAMS = {m.SOURCE["name"]: m for m in (vrt_realtime, idaho511_frames, itd_wzdx, idaho511_api)}
