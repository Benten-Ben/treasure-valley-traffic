# ingest: data collectors

Python ingestors that write to the database (see [db/](../db)). This is a
clean rebuild that keeps the prototype's lessons, not its code (the
prototype is [`tvt/`](../tvt)).

**Status:** first two sources, for the camera calibrator.

| Source | Access | Schedule | Writes |
|---|---|---|---|
| `achd_cameras` | open (ACHD GIS, no robots.txt) | daily | `raw.record`, `core.camera` (228), `core.source_link` |
| `idaho511_views_oneoff` | one-off (dated private file `511-camera-views-2026-10-05.csv`, read from `TVT_PRIVATE_DATA`) | never | `core.camera_view` (210 linked within 200 m) |

```bash
pip install -r ingest/requirements.txt
export DATABASE_URL=postgres://tvt:<password>@localhost/tvt
python3 -m ingest sources
python3 -m ingest run all           # or: run achd_cameras
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
