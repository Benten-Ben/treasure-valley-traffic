"""Registered sources.

SOURCES run once per call (`run`), or on their schedule (`serve`), in this
order (`run all` loads cameras before their views, and the signal sources,
cameras and crossings before the intersection build that joins them). STREAMS
run continuously (`stream`), each as its own service.
"""

from .. import intersections
from . import (achd_cameras, achd_roads, achd_signal_points, compass_congestion, compass_counts, compass_crashes,
               compass_growth, compass_plats, compass_regional_signals, compass_signals, fra_crossings,
               idaho511_api, idaho511_frames, idaho511_views, itd_wzdx, vrt_gtfs, vrt_realtime)

# The COMPASS data sources come last: they depend on nothing above them, and
# the long crash download shouldn't delay the daily intersection build.
SOURCES = {m.SOURCE["name"]: m for m in (achd_cameras, idaho511_views, vrt_gtfs, achd_roads, fra_crossings,
                                         achd_signal_points, compass_signals, compass_regional_signals,
                                         intersections, compass_crashes, compass_counts, compass_growth,
                                         compass_plats, compass_congestion)}
STREAMS = {m.SOURCE["name"]: m for m in (vrt_realtime, idaho511_frames, itd_wzdx, idaho511_api)}
