# intersections

Everywhere traffic streams meet and are controlled
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
COMPASS's signalized intersections and regional signal devices, ACHD's 2022
signal points (signal poles, pedestrian signals, school flashers, fire
signals), FRA's rail crossings, and the daily intersection build that joins
them with OpenStreetMap's signal nodes, ACHD's segments and the cameras.
Later: roundabouts.

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `fra_crossings` | weekly | public domain | Federal Railroad Administration | yes |
| `achd_signal_points` | monthly | none stated | Ada County Highway District | internal |
| `compass_signals` | weekly | none stated ("meant only for reference") | COMPASS and its member agencies | internal until COMPASS answers |
| `compass_regional_signals` | weekly | none stated | COMPASS and its member agencies | internal until COMPASS answers |
| `intersections` | daily (derived, fetches nothing) | derived | COMPASS; ACHD; © OpenStreetMap contributors | internal |

Details of each source: [ingest/README.md](../../ingest/README.md).

**Depends on:** `roads` (segments, OpenStreetMap nodes and ways, street
names) and `cameras` (the build links cameras to intersections).

**Tables:** `core.intersection`, `core.approach`, `core.signal_device`,
`core.rail_crossing` (migration 0011 in `db/migrations/`).

**Code:** `ingest/sources/` (the sources), `ingest/intersections.py` (the
build), `ingest/signal_devices.py` (storing devices),
`ingest/intersection_reviews.json` (the owner's review decisions: confirm,
retire or hold a candidate).

**Commands:**

```bash
python3 -m ingest match-intersections [--dry-run]   # rebuild by hand (the daily source does it too)
python3 -m unittest discover -s plugins/intersections -t .
```

**Ethics:** COMPASS's signal layers are used internally until COMPASS
answers; nothing built from them is republished before then.
