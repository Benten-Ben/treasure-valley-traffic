# safety

Crashes and the high-injury network
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
COMPASS's crash data for Ada and Canyon (2008 on, from ITD's crash reports),
the people involved (restricted), and COMPASS's high-injury junctions and
segments.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `compass_crashes` | monthly (unchanged layers skipped; 6 h back-off) | none stated (COMPASS's disclaimer only) | COMPASS and COMPASS member agencies | yes for crashes; the people only as aggregates |

Read with core's COMPASS reader (`ingest/compass_layer.py`). Details:
[ingest/README.md](../../ingest/README.md).

**Depends on:** `roads` and `intersections` (crashes carry COMPASS's segment
and intersection IDs).

**Tables:** `obs.crash`, `restricted.crash_unit`, `core.hin_junction`,
`core.hin_segment` (migration 0012 in `db/migrations/`).

```bash
TVT_COMPASS_MAX_PAGES=3 python3 -m ingest run compass_crashes   # dev only: at most 3 pages per layer, logged as failed
python3 -m unittest discover -s plugins/safety -t .
```

**Ethics:** the people in crashes are personal data. They go only to the
`restricted` schema, coded and coarsened (age group, Idaho resident or not,
coded citations; no sex; never in `raw.record`), and leave it only as
aggregates: never exported or tiled.
