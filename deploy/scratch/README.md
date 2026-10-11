# deploy/scratch: the scratch database and the build role

Set up Oct 11, 2026 for the landscape sprint (package F6). Unmerged code never
touches the production database: a branch's migrations, loads and builds run
against a **scratch copy** of it on the project VM, as the capped **`tvt_build`**
role. Production gets new schemas and loads only later, through the deploy
runbook, and its loads run as `tvt_build` too.

| Piece | What |
|---|---|
| [`setup.sh`](setup.sh) | Installs these scripts in `/srv/tvt/work/scratch/bin/`, makes the secrets, network, volume, container and role |
| [`refresh.sh`](refresh.sh) | Copies production into a scratch database: a heavy job, by hand ([below](#refreshing)) |
| [`run.sh`](run.sh) | Runs a builder's command against scratch ([below](#running-a-job)) |
| [`lib.sh`](lib.sh) | Their shared settings, locks and memory accounting |
| [`scratchq.py`](scratchq.py) | The light-job rules and the mount rule, on top of F7's `heavy` (the windows, the roll-up, a planned restart) |
| [`../tvt_build.sql`](../tvt_build.sql) | The `tvt_build` role: its caps and grants, idempotent, ending with a check |
| [`grant-checks.sql`](grant-checks.sql) | What `tvt_build` can and can't do, checked as `tvt_build` |
| [`tests/`](tests/) | `python3 -m unittest discover -s deploy/scratch/tests` (with `TVT_TEST_DATABASE_URL`, a superuser on a test cluster, the SQL runs too) |

**F6 depends on F7.** The scripts run their heavy jobs under F7's
`/srv/tvt/work/bin/heavy` and ask it for the time windows, the camera roll-up
and a planned VM restart, so those rules live in one place. Its source is
`deploy/bin/heavy`, which F7 adds: merge F7 first (or with F6). The tests
load it from there and fail without it.

## The scratch database

- Container `tvt-scratch-db`: **production's own db image** (TimescaleDB-HA,
  PostgreSQL 17, PostGIS), `--memory 2g --cpus 2`, half the services' CPU
  weight, `shared_buffers` 384 MB, at most 40 connections. A throwaway server,
  so it writes little: `wal_level=minimal`, `synchronous_commit=off`. A query
  whose client has gone ends within 10 s (`client_connection_check_interval`).
  Timescale's telemetry is off.
- Network `tvt-scratch`, **internal**: no host port, and the database can't
  reach out. Jobs also join `tvt-scratch-out`, a plain bridge network of their
  own, for downloads. Production's database is only on the Compose network,
  which neither reaches: a scratch job can't even resolve its name.
- Volume `tvt-scratch-db-data`; database `tvt`, about 0.6 GB, and at most four
  package copies (`tvt_<pkg>`).
- Secrets: random passwords made by `setup.sh` in
  `/srv/tvt/work/scratch/secrets/` (mode 600), never shown.

What's in it: production as of the last refresh, except
- raw.record's rows, but for the sources builders read: `r2r_trails`,
  `boise_greenbelt_closures` (trails), `nifc_wfigs_perimeters` (burn scars),
  `nwps_gauges` (the canal season and gauges), plus `osm_valley` and
  `achd_roads`, which the OpenStreetMap loader's no-change checks and the
  segment matcher's staleness test read (about 160k rows, 65 MB, of 727k);
- `restricted.*`'s rows (people in crashes): the tables are there, empty;
- private plugins: neither their schemas (`city_trees`, any `private_*`, and
  whatever each plugin folder on the server's `TVT_PLUGIN_PATH` names or makes)
  nor their migration rows. A refresh checks the copy has none before using it.

**Internal, not private: City-derived trees.** The City of Boise's inventory
(`city_trees`) never goes into scratch. But the public `trees` schema, which
is in it, holds rows derived from that inventory: `trees.tree`'s catalogued
and estimated trees with `catalogue = 'boise'` (the City's ids, and for
estimated trees the City's trunk points), and `dbh_in`, the City's trunk
diameter, in `trees.tree.fit` and `trees.tree_log.detail`. Builds may read
them (the masks and the bake place trees), but nothing built from them may be
marked `republish: yes`, and no export may carry their ids, trunk points or
diameters.

## Running a job

Builders use the laptop wrapper (`data/dev/scratch-run.sh`, git-ignored because
it holds the server's address). It copies the worktree as it is on disk to
`/srv/tvt/work/scratch/trees/<name>/` (no `.git`, `data/`, `node_modules`,
builds or `.env` files), then runs `run.sh` there with the output streamed back:

```bash
data/dev/scratch-run.sh <worktree> <name> migrate             # the branch's migrations, then the grants
data/dev/scratch-run.sh <worktree> <name> migrate --status
data/dev/scratch-run.sh <worktree> <name> grants --check      # the role's checks, as tvt_build
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
| `grants [--check]` | `tvt_build.sql` only; with `--check`, `grant-checks.sql` (the tree's copy if it has one) | the owner; `tvt_build` |
| `psql [args]` | psql in the database container | `tvt_build` (`--owner`: `tvt`) |

Inside a job:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://tvt_build@tvt-scratch-db:5432/<db>` (the password is in `PGPASSWORD`; libpq and GDAL's PostgreSQL driver read `PGHOST`, `PGUSER`, `PGDATABASE`) |
| `TVT_ARCHIVE` | `/srv/archive`: **the archive of the job's database**, `/srv/tvt/work/scratch/archive/<db>/`: inboxes, exports (`<plugin>/export/<build>/`), build files and **load state**. Its `osm/` holds a copy of production's held extract and its load state (`last-loaded.json`, and per-consumer state in `osm/` or `osm/state/`). It follows its database: a refresh replaces both. Never production's archive |
| `TVT_PROD_ARCHIVE` | `/srv/archive-prod`: production's archive, read-only |
| `TVT_SOURCES` | `/srv/sources`: `/srv/tvt/work/sources` (downloaded sources: CDL, CSB, NHD, SSURGO, Sentinel-2, HydroShare), read-only |
| `TVT_COLD` | the cold drive, read-only, when it's mounted (the scratch dumps hidden) |
| `TVT_SCRATCH` | `1` |

The tree is mounted read-write at `/repo` (the working directory), as uid and
gid of the server's user, `HOME=/tmp`, `TZ=America/Boise`, with no Linux
capabilities. Jobs reach the internet through a bridge network of their own,
`tvt-scratch-out` (for a loader's download, under the usual rules: robots.txt,
our User-Agent, approved sources only); `--offline` drops that.

`--mount SRC:DST[:ro]` adds a folder (resolved, symlinks included, before it's
checked):
- read-write: a folder inside one of `/srv/tvt/work/`'s folders, or inside
  the cold drive's `vm/`;
- read-only: also production's archive, the downloaded sources, the cold drive
  and the scratch archives;
- never: `/srv/tvt/work/` itself or its `bin/`, `scratch/` (but its archives,
  read-only), `e2e/` and `worker-test*/`; the scratch dumps; the private files
  and private plugins; anything with a `secrets/` or `private/` folder in it;
  or a parent of any of these. `DST` can't be the job's own paths (`/repo`,
  `/srv/archive`, ...).

**Light or heavy.** Light caps are 2 GB and 2 CPUs for `ingest` and `python`,
1 GB and 1 CPU for `worker` (plan §4.1: worker jobs over 1 GB or 1 CPU are
heavy). Over them a job is **heavy**: it needs `--heavy '<who and what>'
--deadline HH:MM --runtime MIN [--peak-gb N]`, and runs under F7's
`/srv/tvt/work/bin/heavy` (`--deadline --runtime --peak -w 60`), which checks
its window, the disk and a planned restart, waits for `heavy.lock` (and for a
closed window to open) up to 60 minutes, and stops it and its container at the
deadline.

**The rules** (plan §4.4, the lead's wave-1 rule, the owner's maintenance rule):

- Day (06:00–23:15 Boise): light jobs any time; heavy ones with a deadline by
  23:15. A light job over 1 GB stops at 23:15 (quiet hours; the camera roll-up
  starts at 00:05), and one whose `--runtime` doesn't fit before then is refused.
- Quiet hours (23:15–06:00): until tonight's camera roll-up has finished, jobs
  get 1 GB at most (pass `--memory 1g`) and no heavy job starts. Whether it
  has finished is `heavy`'s rule (both capture services' status files say
  `"rolling_up": false` in a fresh status written after their first roll-up
  check past 00:05). Then heavy jobs may run with a deadline by 05:45.
- A planned VM restart (`/srv/tvt/work/MAINTENANCE`, read by `heavy`'s rule,
  which ignores a note left over from before the VM's last start): every job
  stops 10 minutes before it, and one whose `--runtime` doesn't fit is
  refused. A note whose time can't be read refuses heavy jobs, and light jobs
  that may run over 10 minutes (by `--limit`, not only `--runtime`). A light
  job checks once a minute for a note posted after it started.
- Disk (free bytes on `/`, exactly): a light job needs 12 GB, a heavy one 12 GB
  plus its peak; any job is stopped under 11 GB (exit 123). The camera capture
  pauses under 10.
- Memory: at most 3 jobs at once. The caps of every scratch job going stay
  within 8 GB, counting 6 GB for a heavy job that holds `heavy.lock` without
  going through `run.sh`; and each job needs its cap plus 3 GB available when
  it starts. It waits up to 15 minutes, then gives up. `status` shows the caps
  going; a heavy job over 4 GB started with `heavy` directly should start only
  when they leave room (`heavy` doesn't count them yet).
- One job per name, held from the moment it's asked for (a heavy job's wait
  for `heavy.lock` included) until it ends; the laptop wrapper copies a tree
  only while its name is free, and holds the name while copying.
- A light job is stopped after `--limit` minutes (default 120).
- Exit codes: the command's; 2 refused; 123 stopped for disk; 124 stopped at
  its limit or deadline; 130 interrupted; `heavy`'s 73 (disk) and 75 (not now).
  Ctrl-C or a dropped connection stops the container, and its queries end on
  the server.
- `logs/jobs.tsv` on the server records every job's start and end.

**Sharing one database.** Builders share `tvt`. Migration numbers are fixed per
package (plan's ground rules), so branches don't collide, but an unmerged
migration you change after applying it stops `migrate` ("changed after it was
applied"). Undo it by hand with `--owner psql` (drop what it made, then
`delete from ops.schema_migration where name = '<plugin>/<file>'`) and migrate
again. For work that needs its own copy (repeated loads, a destructive test),
restore one with its own archive: `refresh.sh --db tvt_<pkg> --from-dump
latest` (heavy, about 0.6 GB of disk plus the archive's 0.13 GB; at most four)
and pass `--db tvt_<pkg>`; `refresh.sh --drop tvt_<pkg>` removes it.

Every job, `psql` session and `grants` run holds its database's lock
(`locks/<db>.lock`) shared; a refresh or drop of that database holds it
exclusively, announcing itself first (`locks/<db>.refresh`) so no new job
starts while it waits.

## What tvt_build can do

[`tvt_build.sql`](../tvt_build.sql) is the policy, and its lists are all of it:
each run grants what they say and takes back what they don't (a table narrowed
or dropped from a list, a grant made by hand, a role membership), in one
transaction, then checks what the role can reach, PUBLIC's grants included,
and fails, changing nothing, if that's more. On both servers:

| What | Grant |
|---|---|
| The role | `LOGIN`, no superuser, no `CREATEDB` or `CREATEROLE`, no replication, row security applies, a member of no other role; connection limit 6 on production, 30 on scratch |
| Caps (role settings) | `work_mem 64MB`, `maintenance_work_mem 512MB`, `max_parallel_workers_per_gather 1`, `statement_timeout 45min`, `temp_file_limit 5GB` (only a superuser can lift this one) |
| The database | `CONNECT`, `TEMPORARY` (staging in temporary tables); no `CREATE` |
| Read: `core`, `obs`, `evt`, `raw`, `ops`, `public` and the plugin schemas below | `USAGE` on the schema; `SELECT` on every table, view and sequence; the same for tables `tvt` makes there later (default privileges). No `CREATE` in any |
| Write: plugin schemas `roads`, `soils`, `farm`, `water`, `trails`, `fences`, `hazards`, `trees` (those that exist) | `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `MAINTAIN` (ANALYZE, VACUUM, REFRESH MATERIALIZED VIEW) on every table; `USAGE`, `UPDATE` on their sequences; default privileges likewise. No `CREATE`: tables come from migrations |
| Append only: `trees.tree_log` (a tree's history, which survives rebuilds) | `INSERT` only |
| Write: shared tables the core helpers log to | `ops.source`, `ops.fetch`, `ops.layer_signature`, `raw.record`, `evt.event`: `INSERT`, `UPDATE`; `core.source_link`, `ops.build_pending` (M1): `INSERT`, `UPDATE`, `DELETE`; `core.layer_version` (S2, append-only history): `INSERT` only; `USAGE` on their sequences |
| Never | `restricted` (people in crashes), private plugins' schemas (`city_trees`, `private_*`), anything not listed; DDL; other roles |

A new schema gets its grants when the script runs again: the scratch wrapper's
`migrate` does that, and on production it's a step of the deploy runbook after
the migrations. A package whose build writes somewhere else adds that table to
the lists on its branch, with the least it needs, and says so in its review;
`grant-checks.sql`'s expectations and the tests follow the lists.

Check what it holds, as the role (`run.sh <name> grants --check`, or
`psql -U tvt_build -f deploy/scratch/grant-checks.sql`; it changes nothing),
or by hand:

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
/srv/tvt/work/bin/heavy --deadline HH:MM --runtime MIN --peak 0 "<load> (deploy)" \
  docker run --rm --memory 2g --memory-swap 2g --cpus 2 --network tvt_default \
    --env-file /srv/tvt/private/secrets/tvt_build.env \
    -e TVT_ARCHIVE=/srv/archive -v /srv/tvt/archive:/srv/archive \
    tvt-ingest:latest python3 -m ingest <command>
```

After a deploy's migrations, apply the grants again before the loads (it fails,
changing nothing, if the role could reach more than the lists allow):

```bash
docker exec -i tvt-db-1 psql -X -v ON_ERROR_STOP=1 -U tvt -d tvt -f - < /srv/tvt/repo/deploy/tvt_build.sql
```

## Refreshing

By hand, under the heavy lock (it runs itself under `heavy --deadline
--runtime --peak 3 --cold 1 -w 60`), in a day window or overnight once the
camera roll-up has finished:

```bash
/srv/tvt/work/scratch/bin/refresh.sh --deadline 22:30                # dump production, restore, swap
/srv/tvt/work/scratch/bin/refresh.sh --deadline 22:30 --from-dump latest   # restore the last dump again
/srv/tvt/work/scratch/bin/refresh.sh --deadline 22:30 --from-dump latest --db tvt_s1   # a package's own copy
/srv/tvt/work/scratch/bin/refresh.sh --drop tvt_s1                   # remove that copy and its archive
```

It reads production only (as its owner over the db container's socket): first
the kept raw.record rows (`COPY`), then `pg_dump -Fc` of the rest, leaving out
the private plugins' schemas, to a folder named by the UTC time on the cold
drive, readable by the server's user only (the last two kept; `heavy` refuses
it without the cold drive, with under 200 GB free there, or under 15 GB free
on `/`). It restores into `<db>_restore` (`timescaledb_pre_restore()`,
`pg_restore --no-privileges`, the raw rows, skipping any whose fetch came after
the dump), removes the private plugins' migration rows, and stops there if
anything private came along. It stages the database's new archive (a copy of
production's `osm/`: the held extracts and their load state). Then it waits for
that database's jobs and sessions (15 minutes at most; no new ones start) and
swaps: the old database's background workers stop
(`timescaledb_pre_restore()`), it's dropped, the new one renamed, the old
archive moved to `archive/.before-refresh/<db>/` (until the next refresh) and
the new one put in its place, then `timescaledb_post_restore()`, `ANALYZE` and
the grants. Last, it counts every readable table on both servers and writes
`refresh.json` (`logs/refresh-<db>.json` for a copy): tables that grew since
the dump (the collectors keep running) differ, nothing else should.

A refresh **throws away everything builders put in that database and its
archive** (loads, builds, exports, load state): they run `migrate` and their
loads again. Stopped early (deadline or error), it leaves the old database and
archive as they were, unless it was in the swap's quick steps.

Measured on the first refresh (Oct 11, 02:39 Boise, after the roll-up): the
dump took 10 s (a 65 MB `pg_dump` and 16 MB of raw rows, zstd), the restore
56 s, the whole refresh 91 s. The copy is a 584 MB database (157,183 raw.record
rows; production is 1.7 GB), and the volume about 1.2 GB with its WAL, which
`max_wal_size=256MB` trims as it's reused. Of 48 tables counted against
production, only `ops.fetch` (the collectors kept fetching) and
`ops.schema_migration` (the private plugin's row) differed. A package's own copy
from the last dump (`--from-dump latest --db ...`) took 45 s.

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
`docker network rm tvt-scratch tvt-scratch-out`, then the folder; and on production, `drop
owned by tvt_build; drop role tvt_build;`.
