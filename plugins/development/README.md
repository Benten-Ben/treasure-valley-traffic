# development

Why traffic will change
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
COMPASS's traffic-analysis zones with their census figures, estimates and
forecasts to 2055, building permits since 2000, and development
applications (preliminary plats). Later: Boise's development pipeline.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `compass_growth` | monthly (unchanged layers skipped) | none stated (COMPASS's disclaimer only) | COMPASS and COMPASS member agencies | yes |
| `compass_plats` | weekly | none stated (COMPASS's disclaimer only) | COMPASS and COMPASS member agencies | yes |

Read with core's COMPASS reader (`ingest/compass_layer.py`). Details:
[ingest/README.md](../../ingest/README.md).

**Tables:** `core.taz`, `obs.taz_demographic`, `obs.building_permit`,
`core.plat` (migration 0012 in `db/migrations/`).

```bash
TVT_COMPASS_FORCE=1 python3 -m ingest run compass_growth   # skip the freshness and change checks
python3 -m unittest discover -s plugins/development -t .
```

**Ethics:** permits are stored without addresses, parcel numbers or
comments, and plats without comments. Ada County's parcels belong only in
the private `parcels` plugin.
