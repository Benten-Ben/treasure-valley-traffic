# ingest: data collectors

Python ingestors that write to the database (see [db/](../db)). This is a
clean rebuild that keeps the prototype's lessons, not its code (the
prototype is [`tvt/`](../tvt)).

**Status:** camera sources (for the calibrator), Valley Regional Transit (buses), ITD's work zones and the 511 Idaho API.

| Source | Access | Schedule | Writes |
|---|---|---|---|
| `achd_cameras` | open (ACHD GIS, no robots.txt) | daily | `raw.record`, `core.camera` (228), `core.source_link` |
| `idaho511_views_oneoff` | one-off (dated private file `511-camera-views-2026-10-05.csv`, read from `TVT_PRIVATE_DATA`) | never | `core.camera_view` (210 linked within 200 m) |
| `achd_roads` | open (ACHD GIS, no robots.txt) | weekly | `raw.record`, `core.road_segment` (38,727 Ada County segments: posted speed, class, one-way, level, community), `core.source_link` |
| `vrt_gtfs` | open (VRT, CC BY 3.0) | daily | `core.transit_route`/`_stop`/`_shape`/`_trip`; each zip archived in `$TVT_ARCHIVE/vrt-gtfs/`. Picks each route's map color (routes sharing streets differ). |
| `vrt_realtime` | open (VRT, CC BY 3.0) | stream, every 30 s | each changed feed archived in `$TVT_ARCHIVE/vrt-gtfs-rt/<date>/`; bus positions in `obs.vehicle_position` |
| `itd_wzdx` | open (ITD's WZDx feed on 511 Idaho; may be republished, crediting ITD) | stream, every 5 min | each changed snapshot archived in `$TVT_ARCHIVE/wzdx/<date>/`; every work zone's versions in `raw.record`; cleaned rows in `evt.event` (fixes listed per row; [docs/08 §8.8](../docs/08-data-inventory.md#88-itds-work-zone-feed-checked-against-the-wzdx-spec-oct-6-2026)) |
| `idaho511_api` | API key (`IDAHO511_API_KEY`; 511 Idaho developer terms; not republished) | stream, per endpoint: events and signs 2 min, weather and advisories 5, truck restrictions and winter roads 15, cameras hourly, the rest daily; at most 8 calls a minute | changed responses archived in `$TVT_ARCHIVE/idaho511/<endpoint>/<date>/`; versions in `raw.record` (one source per endpoint, `idaho511_<endpoint>`); `evt.event` (events, advisories, truck restrictions), `core.message_sign` + `evt.sign_message`, `core.weather_station` + `obs.weather_reading`; the regional capture list in `$TVT_ARCHIVE/lists/` |

```bash
pip install -r ingest/requirements.txt
export DATABASE_URL=postgres://tvt:<password>@localhost/tvt
python3 -m ingest sources
python3 -m ingest run all           # or: run achd_cameras
TVT_ARCHIVE=data/archive python3 -m ingest stream vrt_realtime            # live buses, every 30 s
python3 -m ingest backfill vrt_realtime data/archive/vrt-gtfs-rt          # reload positions from the archive
TVT_ARCHIVE=data/archive python3 -m ingest stream itd_wzdx                # ITD work zones, every 5 min
TVT_ARCHIVE=data/archive IDAHO511_API_KEY=... python3 -m ingest stream idaho511_api   # the 511 API (key never committed)
python3 -m ingest backfill itd_wzdx data/archive/wzdx                     # load snapshots the database missed
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
