# ingest: data collectors

Python ingestors that write to the database (see [db/](../db)). This is a
clean rebuild that keeps the prototype's lessons, not its code (the
prototype is [`tvt/`](../tvt)).

**Status:** camera sources (for the calibrator) and Valley Regional Transit (buses).

| Source | Access | Schedule | Writes |
|---|---|---|---|
| `achd_cameras` | open (ACHD GIS, no robots.txt) | daily | `raw.record`, `core.camera` (228), `core.source_link` |
| `idaho511_views_oneoff` | one-off (dated private file `511-camera-views-2026-10-05.csv`, read from `TVT_PRIVATE_DATA`) | never | `core.camera_view` (210 linked within 200 m) |
| `vrt_gtfs` | open (VRT, CC BY 3.0) | daily | `core.transit_route`/`_stop`/`_shape`/`_trip`; each zip archived in `$TVT_ARCHIVE/vrt-gtfs/`. Picks each route's map color (routes sharing streets differ). |
| `vrt_realtime` | open (VRT, CC BY 3.0) | stream, every 30 s | each changed feed archived in `$TVT_ARCHIVE/vrt-gtfs-rt/<date>/`; bus positions in `obs.vehicle_position` |

```bash
pip install -r ingest/requirements.txt
export DATABASE_URL=postgres://tvt:<password>@localhost/tvt
python3 -m ingest sources
python3 -m ingest run all           # or: run achd_cameras
TVT_ARCHIVE=data/archive python3 -m ingest stream vrt_realtime            # live buses, every 30 s
python3 -m ingest backfill vrt_realtime data/archive/vrt-gtfs-rt          # reload positions from the archive
python3 -m unittest discover -s ingest/tests -t .
```

Each run logs to `ops.fetch`. Records are versioned in `raw.record`, so a
re-run that finds nothing new adds nothing.

Rules carried over from the prototype, which all ingestors must follow:

- Check robots.txt before every request, using the lenient RFC 9309 parser
  ([docs/10 §10.5](../docs/10-architecture.md#105-what-the-prototype-taught-us-kept-as-lessons-not-code)),
  and honor crawl-delay.
- Identify ourselves with a descriptive User-Agent.
- Only collect sources marked allowed in
  [docs/08](../docs/08-data-inventory.md). Never store Google, TomTom, HERE,
  Mapbox or Waze data.
- Log every fetch (status and robots decision) so gaps are visible.
