# flow

How traffic moves
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
COMPASS's traffic counts from every agency (the latest short count per
location, plus permanent counters), its congestion measures by segment and
year, and commute travel times. Later: speeds from buses and GPS drives.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `compass_counts` | monthly | none stated (COMPASS's disclaimer only) | COMPASS and COMPASS member agencies | yes |
| `compass_congestion` | monthly (unchanged layers skipped) | none stated; not offered as open data | COMPASS and COMPASS member agencies | internal until COMPASS answers |

Read with core's COMPASS reader (`ingest/compass_layer.py`). Details:
[ingest/README.md](../../ingest/README.md). `compass_congestion` carries
order 90 in the manifest so it still runs last, after the development
plugin's sources, as it did before the plugin split.

**Depends on:** `roads` (counts are matched to COMPASS's segments).

**Tables:** `obs.traffic_count`, `obs.congestion_measure`,
`obs.commute_travel_time` (migration 0012 in `db/migrations/`).

```bash
python3 -m unittest discover -s plugins/flow -t .
```

**Ethics:** congestion measures and commute travel times are used
internally until COMPASS answers. ACHD's own count and turn-movement tables
are not here: they belong to the private `achd_tables` plugin.
