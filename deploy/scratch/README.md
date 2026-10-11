# deploy/scratch: the scratch database and the build role

Set up Oct 11, 2026 for the landscape sprint (package F6). Unmerged code never
touches the production database: a branch's migrations, loads and builds run
against a **scratch copy** of it on the project VM, as the capped **`tvt_build`**
role. Production gets new schemas and loads only later, through the deploy
runbook, and its loads run as `tvt_build` too.

| Piece | What |
|---|---|
| [`setup.sh`](setup.sh) | Installs these scripts in `/srv/tvt/work/scratch/bin/`, makes the secrets, network, volume, container and role |
| [`refresh.sh`](refresh.sh) | Copies production into scratch: a heavy job, by hand ([below](#refreshing)) |
| [`run.sh`](run.sh) | Runs a builder's command against scratch ([below](#running-a-job)) |
| [`lib.sh`](lib.sh) | Their shared settings and checks (time windows, camera roll-up, disk, memory) |
| [`../tvt_build.sql`](../tvt_build.sql) | The `tvt_build` role: its caps and grants, idempotent |

## The scratch database

- Container `tvt-scratch-db`: **production's own db image** (TimescaleDB-HA,
  PostgreSQL 17, PostGIS), `--memory 2g --cpus 2`, half the services' CPU
  weight, `shared_buffers` 384 MB, at most 40 connections. A throwaway server,
  so it writes little: `wal_level=minimal`, `synchronous_commit=off`.
  Timescale's telemetry is off.
- Network `tvt-scratch`, **internal**: no host port, and the database can't
  reach out. Production's database is on the Compose network, which the scratch
  network can't reach.
- Volume `tvt-scratch-db-data`; database `tvt`, about 0.7 GB.
- Secrets: random passwords made by `setup.sh` in
  `/srv/tvt/work/scratch/secrets/` (mode 600), never shown.

What's in it: production as of the last refresh, except
- raw.record's rows, but for the sources builders read: `r2r_trails`,
  `boise_greenbelt_closures` (trails), `nifc_wfigs_perimeters` (burn scars),
  `nwps_gauges` (the canal season and gauges), plus `osm_valley` and
  `achd_roads`, which the OpenStreetMap loader's no-change checks and the
  segment matcher's staleness test read (about 160k rows, 65 MB, of 727k);
- `restricted.*`'s rows (people in crashes): the tables are there, empty;
- the private `city_trees` plugin: neither its schema nor its migration row.
  The City of Boise's tree data never goes into scratch.

## Running a job

Builders use the laptop wrapper (`data/dev/scratch-run.sh`, git-ignored because
it holds the server's address). It copies the worktree as it is on disk to
`/srv/tvt/work/scratch/trees/<name>/` (no `.git`, `data/`, `node_modules`,
builds or `.env` files), then runs `run.sh` there with the output streamed back:

```bash
data/dev/scratch-run.sh <worktree> <name> migrate             # the branch's migrations, then the grants
data/dev/scratch-run.sh <worktree> <name> migrate --status
data/dev/scratch-run.sh <worktree> <name> ingest osm-load --only roads.osm_street
data/dev/scratch-run.sh <worktree> <name> python -m plugins.soils.ingest.load ...
data/dev/scratch-run.sh <worktree> <name> worker python basemap/ground/mask.py ...
data/dev/scratch-run.sh psql -c 'select count(*) from roads.osm_street'
data/dev/scratch-run.sh status
```

| Mode | Runs | As |
|---|---|---|
| `ingest <args>` | `python3 -m ingest <args>` in `tvt-ingest:latest`, with the tree as `/repo` | `tvt_build` |
| `python <args>` | `python3 <args>` in `tvt-ingest:latest` | `tvt_build` |
| `worker <cmd>` | `<cmd>` in `tvt-worker:latest` | `tvt_build` |
| `migrate [--status]` | `python3 db/migrate.py`, then `tvt_build.sql` (the tree's copy if it has one) | the owner, `tvt` |
| `grants` | `tvt_build.sql` only | the owner |
| `psql [args]` | psql in the database container | `tvt_build` (`--owner`: `tvt`) |

Inside a job:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://tvt_build@tvt-scratch-db:5432/tvt` (the password is in `PGPASSWORD`; libpq and GDAL's PostgreSQL driver read `PGHOST`, `PGUSER`, `PGDATABASE`) |
| `TVT_ARCHIVE` | `/srv/archive`: **the scratch archive** (`/srv/tvt/work/scratch/archive`), shared by builders: inboxes, exports (`<plugin>/export/<build>/`), build files. Its `osm/` holds a copy of production's held extract and its load state. Never production's archive |
| `TVT_PROD_ARCHIVE` | `/srv/archive-prod`: production's archive, read-only |
| `TVT_SOURCES` | `/srv/sources`: `/srv/tvt/work/sources` (downloaded sources: CDL, CSB, NHD, SSURGO, Sentinel-2, HydroShare), read-only |
| `TVT_COLD` | the cold drive, read-only, when it's mounted |
| `TVT_SCRATCH` | `1` |

The tree is mounted read-write at `/repo` (the working directory), as uid and
gid of the server's user, `HOME=/tmp`, `TZ=America/Boise`. Jobs reach the
internet through a bridge network of their own, `tvt-scratch-out` (for a loader's download, under the
usual rules: robots.txt, our User-Agent, approved sources only); `--offline`
drops that. `--mount SRC:DST[:ro]` adds a folder: read-write under
`/srv/tvt/work/` or the cold drive's `vm/`, read-only under production's archive
or the cold drive. Private files, secrets and the e2e runner's folder can't be
mounted.

**Light or heavy.** Light caps are 2 GB and 2 CPUs for `ingest` and `python`,
1 GB and 1 CPU for `worker` (plan §4.1: worker jobs over 1 GB or 1 CPU are
heavy). Over them a job is **heavy**: it needs `--heavy '<who and what>'
--deadline HH:MM --runtime MIN [--peak-gb N]`, waits for
`/srv/tvt/work/heavy.lock` (through `/srv/tvt/work/bin/heavy`), and is stopped
at its deadline.

**The rules `run.sh` applies** (plan §4.4 and the lead's wave-1 rule):

- Day (06:00–23:15 Boise): light jobs any time; heavy ones with a deadline by
  23:15. A light job over 1 GB still going at 23:15 is stopped (quiet hours;
  the camera roll-up starts at 00:05).
- Quiet hours (23:15–06:00): until the nightly camera roll-up has finished,
  jobs get 1 GB at most (pass `--memory 1g`) and no heavy job starts. The
  roll-up has finished when, after 00:05, both capture services' status files
  (`cameras/status/key_cameras.json`, `regional-cameras.json`) say
  `"rolling_up": false` in a status written at least one capture cycle after
  00:05. Then heavy jobs may run with a deadline by 05:45.
- Disk: a light job needs 10 GB free on `/`; a heavy one 12 GB plus its peak.
- A job expecting more than 10 minutes (`--runtime`), or any heavy one, doesn't
  start while `/srv/tvt/work/MAINTENANCE` announces a VM restart.
- At most 3 jobs at once, each admitted only with its cap plus 3 GB of memory
  available (it waits up to 15 minutes, then gives up). One job per name.
- A light job is stopped after `--limit` minutes (default 120).
- Exit codes: the command's; 2 refused; 124 stopped at its limit or deadline;
  130 interrupted. Ctrl-C or a dropped connection stops the container.
- `logs/jobs.tsv` on the server records every job's start and end.

**Sharing one database.** Builders share `tvt`. Migration numbers are fixed per
package (plan's ground rules), so branches don't collide, but an unmerged
migration you change after applying it stops `migrate` ("changed after it was
applied"). Undo it by hand with `--owner psql` (drop what it made, then
`delete from ops.schema_migration where name = '<plugin>/<file>'`) and migrate
again. For work that needs its own copy (repeated loads, a destructive test),
restore one: `refresh.sh --db tvt_<pkg> --from-dump latest` (heavy, about
0.7 GB of disk; drop it when you're done) and pass `--db tvt_<pkg>`.

## What tvt_build can do

[`tvt_build.sql`](../tvt_build.sql) is the policy. On both servers:

| What | Grant |
|---|---|
| The role | `LOGIN`, no superuser, no `CREATEDB` or `CREATEROLE`, no replication, row security applies; connection limit 6 on production, 30 on scratch |
| Caps (role settings) | `work_mem 64MB`, `maintenance_work_mem 512MB`, `max_parallel_workers_per_gather 1`, `statement_timeout 45min`, `temp_file_limit 5GB` (only a superuser can lift this one) |
| The database | `CONNECT`, `TEMPORARY` (staging in temporary tables); no `CREATE` |
| Read: `core`, `obs`, `evt`, `raw`, `ops`, `public` and the plugin schemas below | `USAGE` on the schema; `SELECT` on every table, view and sequence; the same for tables `tvt` makes there later (default privileges) |
| Write: plugin schemas `roads`, `soils`, `farm`, `water`, `trails`, `fences`, `hazards`, `trees` (those that exist) | `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `MAINTAIN` (ANALYZE, VACUUM, REFRESH MATERIALIZED VIEW) on every table; `USAGE`, `UPDATE` on their sequences; default privileges likewise. No `CREATE`: tables come from migrations |
| Write: shared tables the core helpers log to | `ops.source`, `ops.fetch`, `ops.layer_signature`, `raw.record`, `evt.event`: `INSERT`, `UPDATE`; `core.source_link`, `core.layer_version` (S2), `ops.build_pending` (M1): `INSERT`, `UPDATE`, `DELETE`; `USAGE` on their sequences |
| Never | `restricted` (people in crashes), private plugins' schemas (`city_trees`), anything not listed; DDL on existing tables; other roles |

A new schema gets its grants when the script runs again: the scratch wrapper's
`migrate` does that, and on production it's a step of the deploy runbook after
the migrations. A package whose build writes somewhere else adds that table to
the lists on its branch, with the least it needs, and says so in its review.

Check what it holds:

```sql
select table_schema, table_name, string_agg(privilege_type, ', ' order by privilege_type)
from information_schema.role_table_grants where grantee = 'tvt_build'
group by 1, 2 order by 1, 2;
select rolconfig, rolconnlimit from pg_roles where rolname = 'tvt_build';
```

### On production

The same script made the role in production's database on Oct 11 (connection
limit 6). Its password, and its `DATABASE_URL` on the Compose network, are in
the private files (`/srv/tvt/private/secrets/tvt_build.env`, mode 600). Nothing
else in production changed. A production load runs in its own capped
container, never inside `ingest serve` and never with `exec`. `docker compose
run` has no memory cap option, so it's a plain `docker run` of the deployed
ingest image on the Compose network:

```bash
/srv/tvt/work/bin/heavy "<load> (deploy)" \
  docker run --rm --memory 2g --memory-swap 2g --cpus 2 --network tvt_default \
    --env-file /srv/tvt/private/secrets/tvt_build.env \
    -e TVT_ARCHIVE=/srv/archive -v /srv/tvt/archive:/srv/archive \
    tvt-ingest:latest python3 -m ingest <command>
```

After a deploy's migrations, apply the grants again before the loads:

```bash
docker exec -i tvt-db-1 psql -X -v ON_ERROR_STOP=1 -U tvt -d tvt -f - < /srv/tvt/repo/deploy/tvt_build.sql
```

## Refreshing

By hand, under the heavy lock, in a day window or overnight once the camera
roll-up has finished:

```bash
/srv/tvt/work/scratch/bin/refresh.sh --deadline 22:30                # dump production, restore, swap
/srv/tvt/work/scratch/bin/refresh.sh --deadline 22:30 --from-dump latest   # restore the last dump again
/srv/tvt/work/scratch/bin/refresh.sh --deadline 22:30 --from-dump latest --db tvt_s1   # a package's own copy
```

It reads production only (as its owner over the db container's socket): first
the kept raw.record rows (`COPY`), then `pg_dump -Fc` of the rest, to a folder
named by the UTC time on the cold drive (the last two kept; it refuses without
the cold drive, or with under 200 GB free there, or under 15 GB free on `/`).
It restores into `<db>_restore` (`timescaledb_pre_restore()`, `pg_restore
--no-privileges`, the raw rows, skipping any whose fetch came after the dump),
then swaps: the old database's background workers stop
(`timescaledb_pre_restore()`), it's dropped, the new one renamed, then
`timescaledb_post_restore()`, `ANALYZE` and the grants. Last, it counts every
readable table on both servers and writes `refresh.json`: tables that grew
since the dump (the collectors keep running) differ, nothing else should.

A refresh **throws away everything builders put in the database**: they run
`migrate` and their loads again. It waits up to 15 minutes for running jobs and
starts no new ones meanwhile. Stopped early (deadline or error), it leaves the
old database as it was, unless it was in the swap's two quick steps. Measured
on Oct 11: see `refresh.json` on the server.

## Setting it up again

```bash
# from a checkout of the repository on the server (the laptop wrapper's copy will do):
deploy/scratch/setup.sh              # installs bin/, makes what's missing, applies the role
deploy/scratch/setup.sh --recreate   # new settings or image; the volume stays
/srv/tvt/work/scratch/bin/refresh.sh --deadline HH:MM
```

The server's own settings (the cold drive's mount and dump folder) are in
`/srv/tvt/work/scratch/scratch.conf`, not here. To remove it all: stop the jobs,
`docker rm -f tvt-scratch-db`, `docker volume rm tvt-scratch-db-data`,
`docker network rm tvt-scratch`, then the folder; and on production, `drop
owned by tvt_build; drop role tvt_build;`.
