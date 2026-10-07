# db: database schema

PostgreSQL + PostGIS + TimescaleDB ([decision log](../docs/DECISIONS.md)).

**Status:** design draft in [docs/12](../docs/12-database-schema.md), waiting on
the owner's review of its decisions. Migrations come after that.

Starting points from the prototype ([docs/10 §10.5](../docs/10-architecture.md#105-what-the-prototype-taught-us-kept-as-lessons-not-code)).
Each kind of data behaves differently:

- **Inventories** (cameras, signals, count stations) need both the current
  state and a history of changes.
- **Events** (work zones, incidents) need lifecycles: first seen, last
  seen, active.
- **Time series** (counts, bus positions, weather, camera measurements)
  need upserts and TimescaleDB hypertables.
- **Fetch log:** every request with its source, status and robots decision.

## Migrations

Plain SQL files in `db/migrations/`, applied in order by `db/migrate.py`,
which records each one (with a checksum) in `ops.schema_migration`. Never
edit an applied migration; add a new one.

Plugins ([docs/15](../docs/15-plugins.md)) keep their own migrations in
`plugins/<name>/migrations/NNNN_*.sql`. They apply after core's, plugin by
plugin in dependency order (private plugins' too, from `TVT_PLUGIN_PATH`),
and are recorded as `<plugin>/<file>` under the same checksum rule.
Migrations 0001–0018 stay here: the server has them recorded by name. New
migrations for one subject go in its plugin.

| File | What |
|---|---|
| `0001_foundation.sql` | `ops.source` (it refuses to schedule one-off sources), `ops.fetch`, `raw.record` |
| `0002_cameras.sql` | `core.source_link`, `core.camera`, `core.camera_view`, `core.camera_calibration` (versioned, one current per view) |

```bash
pip install -r ingest/requirements.txt
export DATABASE_URL=postgres://tvt:<password>@localhost/tvt
python3 db/migrate.py            # apply pending migrations
python3 db/migrate.py --status
```

**Local development:** PostgreSQL 16 + PostGIS 3 from apt is enough for
these migrations. The server uses the `timescaledb-ha` image
([deploy/](../deploy)).
