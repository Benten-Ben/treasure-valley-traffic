# transit

Valley Regional Transit's buses
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have),
[docs/14 §14.4](../../docs/14-ui-v2.md)): the static GTFS (routes, stops,
shapes, trips), live positions every 30 s, matching unlabeled trips to
routes, placing each fix along its route for playback (the tracks contract,
docs/15 §15.5), and the side-by-side route ribbons and colors.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `vrt_gtfs` | daily | CC BY 3.0 | Valley Regional Transit | yes |
| `vrt_realtime` | stream, every 30 s | CC BY 3.0 | Valley Regional Transit | yes |

Details of each source: [ingest/README.md](../../ingest/README.md).

**Tables:** `core.transit_route`, `core.transit_stop`, `core.transit_shape`,
`core.transit_trip`, `core.transit_ribbon`, `obs.vehicle_position`,
`obs.trip_route_match`, `obs.vehicle_progress` (migrations 0003 and
0005–0007 in `db/migrations/`).

**Code:** `ingest/sources/` (the feeds), `ingest/transit_match.py` (trips
to routes), `ingest/transit_progress.py` (playback matcher),
`ingest/transit_ribbons.py` and `ingest/route_colors.py` (ribbons and
colors; the app pins the same palette).

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest stream vrt_realtime
python3 -m ingest backfill vrt_realtime data/archive/vrt-gtfs-rt    # reload positions from the archive
python3 -m ingest match-routes [--hours 24]
python3 -m ingest transit-progress --hours 24                       # backfill playback matches
python3 -m ingest transit-ribbons [--force] [--dry-run]
python3 -m ingest route-colors                                      # the palette table and its checks
python3 -m unittest discover -s plugins/transit -t .
```
