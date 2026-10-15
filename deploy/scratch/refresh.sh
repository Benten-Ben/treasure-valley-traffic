#!/usr/bin/env bash
# Refresh a scratch database from production (landscape sprint plan, F6). A heavy job, by hand.
#
#   refresh.sh --deadline HH:MM [--runtime MIN] [--from-dump DIR|latest] [--db NAME] [--keep N]
#   refresh.sh --drop NAME          drop a package's copy and its archive (not tvt)
#
#   --deadline HH:MM   Boise time; everything stops there (heavy's windows: day by 23:15;
#                      overnight, once the camera roll-up has finished, by 05:45). A fresh dump
#                      of production runs in a day window only (06:00-23:15; plan §4.4)
#   --runtime MIN      the expected time (default 30); it must fit before the deadline
#   --from-dump DIR    restore a dump made earlier (a folder under $DUMP_ROOT, or "latest") instead
#                      of dumping production again
#   --db NAME          restore into this database instead of tvt (a package's own copy, tvt_<pkg>;
#                      at most $MAX_COPIES of them)
#   --keep N           dumps kept on the cold drive (default 2)
#
# What it does, under /srv/tvt/work/heavy.lock (it runs itself under F7's heavy):
#   1. Production, read only (as its owner, over the db container's socket): first a snapshot of
#      its archive's load state (osm/last-loaded.json and the like: seedarchive.py), then
#      raw.record's rows for the sources builders read ($KEEP_RAW_SOURCES), then pg_dump -Fc of
#      everything else: no rows from raw.record or restricted.*, and no private plugin's schema
#      (city_trees, private_*, and each plugin folder in $PRIVATE_PLUGINS_DIR). To
#      $DUMP_ROOT/<UTC stamp>/ on the cold drive (mode 700: production's data), with meta.json.
#   2. The scratch server: a new database <db>_restore: timescaledb_pre_restore(), pg_restore
#      (no grants), the raw rows (any whose fetch isn't in the dump is skipped and counted), the
#      private plugins' migration rows removed, and a check that nothing private came along.
#   3. The swap, once <db>'s jobs have finished (it waits up to 15 minutes; none start meanwhile):
#      the old <db> is dropped and <db>_restore renamed, timescaledb_post_restore(), ANALYZE,
#      the tvt_build grants; and <db>'s archive (TVT_ARCHIVE in its jobs) is replaced by one
#      holding production's held OSM extracts and the load state from the dump's snapshot (so
#      it describes the restored database: a loader skips only what the copy has), the old one
#      kept in archive/.before-refresh/ until the next refresh.
#   4. Row counts against production, refresh.json, and the old dumps pruned.
#
# A refresh throws away everything builders put in that database and its archive (their
# migrations, loads, builds, exports and load state): they run `migrate` and their loads again.
# If it stops (deadline, error), the old database and archive are left as they were, unless it
# had reached the swap's quick steps.
set -euo pipefail
umask 077                                           # the dumps and logs are production's data
SCRIPT=scratch-refresh
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=lib.sh
. "$HERE/lib.sh"
ARGV=("$@")

# The sources whose raw.record rows builders read: R2R and the Greenbelt (trails), WFIGS
# perimeters (burn scars), NWPS (the canal season and gauges), plus osm_valley and achd_roads,
# which S1's no-change checks and the segment matcher's staleness test read.
KEEP_RAW_SOURCES=${KEEP_RAW_SOURCES:-r2r_trails boise_greenbelt_closures nifc_wfigs_perimeters nwps_gauges osm_valley achd_roads}
APP=tvt-scratch-refresh                             # application_name of our sessions on both servers

deadline= runtime=30 from= db=tvt keep=2 drop=
while [ $# -gt 0 ]; do
	case $1 in
		--deadline) deadline=${2:?}; shift 2 ;;
		--runtime) runtime=${2:?}; shift 2 ;;
		--from-dump) from=${2:?}; shift 2 ;;
		--db) db=${2:?}; shift 2 ;;
		--keep) keep=${2:?}; shift 2 ;;
		--drop) drop=${2:?}; shift 2 ;;
		-h|--help) sed -n '2,35p' "$0"; exit 0 ;;
		*) die "unknown argument $1 (--help)" ;;
	esac
done
running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ]; }
S() { docker exec -i -e PGAPPNAME=$APP "$SCRATCH_DB" psql -X -v ON_ERROR_STOP=1 -U tvt -At "$@"; }
db_exists() { [ "$(S -d postgres -c "select count(*) from pg_database where datname = '$1'")" = 1 ]; }

# lock_db DB: the exclusive per-database lock (fd 8), announced first so no new job starts while
# it waits; waits up to 15 minutes for the jobs and sessions going there.
lock_db() {
	mkdir -p "$LOCKS"
	echo $$ > "$LOCKS/$1.refresh"
	trap 'rm -f "$LOCKS/'"$1"'.refresh"' EXIT
	exec 8>"$LOCKS/$1.lock"
	if ! flock -x -n 8; then
		say "waiting for the jobs and psql sessions on $1 to finish (15 min at most)"
		flock -x -w 900 8 || die "jobs on $1 still going after 15 minutes; try later"
	fi
}

if [ -n "$drop" ]; then
	[[ $drop =~ ^[a-z_][a-z0-9_]{0,50}$ ]] && [ "$drop" != tvt ] && [ "$drop" != postgres ] || die "--drop: a package's copy, not tvt (got '$drop')"
	running "$SCRATCH_DB" || die "the scratch database isn't running (setup.sh)"
	lock_db "$drop"
	db_exists "$drop" && S -d postgres -c "drop database $drop with (force)" >/dev/null
	rm -rf "${ARCHIVES:?}/$drop" "$ARCHIVES/.before-refresh/$drop"
	say "dropped $drop and its archive"
	exit 0
fi

[[ $deadline =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "--deadline HH:MM (Boise) is required"
[[ $runtime =~ ^[0-9]+$ && $keep =~ ^[1-9][0-9]*$ ]] || die "--runtime and --keep take whole numbers"
[[ $db =~ ^[a-z_][a-z0-9_]{0,50}$ ]] && [ "$db" != postgres ] && [[ $db != *_restore ]] || die "--db: a plain database name (got '$db')"
[ -n "$DUMP_ROOT" ] && [ -n "$COLD_MARKER" ] || die "DUMP_ROOT and COLD_MARKER aren't set ($SCRATCH_ROOT/scratch.conf)"
[ -e "$COLD_MARKER" ] || die "the cold drive isn't there ($COLD_MARKER missing): dumps go only to it"
running "$SCRATCH_DB" || die "the scratch database isn't running (setup.sh)"
if [ "$db" != tvt ] && ! db_exists "$db"; then
	copies=$(S -d postgres -c "select count(*) from pg_database where not datistemplate
	                            and datname not in ('postgres', 'tvt') and datname not like '%\_restore'")
	[ "$copies" -lt "$MAX_COPIES" ] || die "already $copies package copies (at most $MAX_COPIES): drop one first (refresh.sh --drop NAME)"
fi
# A fresh dump reads production: day windows only (plan §4.4). A restore of an earlier dump
# touches only scratch, so heavy's windows apply (overnight once the roll-up has finished).
day_only() {
	local q=0
	[ -z "$from" ] || return 0
	scratchq quiet || q=$?
	[ $q != 0 ] || die "a fresh dump of production runs in a day window (06:00-23:15 Boise; plan §4.4): wait, or restore the last dump (--from-dump latest)"
	[ $q = 1 ] || die "can't tell the time window (scratchq quiet: exit $q)"
}
if [ -z "${SCRATCH_IN_HEAVY:-}" ]; then
	[ -x "$HEAVY" ] || die "no $HEAVY (F7's heavy)"
	day_only
	say "heavy checks the window, the disk and a planned restart, and waits for heavy.lock if it's busy"
	# heavy (F7) stops this script (SIGTERM: it ends our database sessions) at the deadline, or
	# 10 minutes before a planned VM restart.
	exec "$HEAVY" --deadline "$deadline" --runtime "$runtime" --peak 3 --cold "$( [ -n "$from" ] && echo 0 || echo 1 )" -w 60 \
		"scratch refresh (F6, $db)" env SCRATCH_IN_HEAVY=1 "$0" "${ARGV[@]}"
fi
running "$PROD_DB_CONTAINER" || die "production's database isn't running"

if [ -n "$from" ]; then
	[ "$from" = latest ] && from=$(find "$DUMP_ROOT" -mindepth 2 -maxdepth 2 -name COMPLETE -printf '%h\n' | sort | tail -1)
	[[ $from = /* ]] || from=$DUMP_ROOT/$from
	[ -f "$from/COMPLETE" ] || die "no complete dump in '$from'"
fi

# Private plugins: their names (folders with a plugin.json) and the schemas they make. The dump
# leaves those schemas out, and private_* whatever they are; the copy drops their migration rows.
private_plugins=() private_schemas=(city_trees)
for d in "$PRIVATE_PLUGINS_DIR"/*/; do
	[ -f "$d/plugin.json" ] || continue
	n=$(basename "$d")
	private_plugins+=("$n")
	private_schemas+=("$n" "private_$n")
	while read -r s; do [ -n "$s" ] && private_schemas+=("$s"); done < <(
		cat "$d"/migrations/*.sql 2>/dev/null | grep -oiE 'create schema( if not exists)? +"?[a-z_][a-z0-9_]*' | awk '{ print tolower($NF) }' | tr -d '"')
done
[ ${#private_plugins[@]} -gt 0 ] || [ ! -d "$PRIVATE_PLUGINS_DIR" ] || say "note: no private plugins found in $PRIVATE_PLUGINS_DIR (can this user read it?)"
mapfile -t private_schemas < <(printf '%s\n' "${private_schemas[@]}" | sort -u)
exclude=(--exclude-schema='private_*')
for s in "${private_schemas[@]}"; do exclude+=(--exclude-schema="$s"); done
arr() { local IFS=,; echo "'{$*}'::text[]"; }
private_plugins_sql=$(arr city_trees ${private_plugins[@]+"${private_plugins[@]}"})
private_schemas_sql=$(arr "${private_schemas[@]}")

# Nothing may use <db> while it's replaced: wait for its jobs, start none meanwhile.
lock_db "$db"

# The deadline: a watchdog ends our sessions on both servers (so the clients inside the
# containers stop too), then this script.
stop_at=${HEAVY_DEADLINE_EPOCH:?inside heavy, HEAVY_DEADLINE_EPOCH should be set}
cancel() {
	local q="select count(pg_terminate_backend(pid)) from pg_stat_activity where application_name = '$APP' and pid <> pg_backend_pid()"
	docker exec "$PROD_DB_CONTAINER" psql -X -U tvt -d postgres -Atc "$q" >/dev/null 2>&1 || true
	docker exec "$SCRATCH_DB" psql -X -U tvt -d postgres -Atc "$q" >/dev/null 2>&1 || true
}
stopped= staged=
cleanup() {
	set +e
	kill "$watch" 2>/dev/null
	rm -f "$LOCKS/$db.refresh"
	[ -z "$staged" ] || rm -rf "$staged"
	[ -z "$stopped" ] || say "stopped at the deadline: the old database is untouched unless the swap had begun"
}
trap 'stopped=1' USR1
trap 'cancel; exit 130' INT HUP
trap 'cancel; exit 143' TERM
secs=$((stop_at - $(date +%s)))
[ "$secs" -ge 1 ] || secs=1
( exec 8>&- 9>&-; sleep "$secs" & s=$!; trap 'kill $s 2>/dev/null; exit 0' TERM
  wait $s && { echo "scratch-refresh: deadline $deadline reached; stopping" >&2; kill -USR1 $$; cancel; } ) &
watch=$!
trap cleanup EXIT

t0=$(date +%s)
P() { docker exec -i -e PGAPPNAME=$APP "$PROD_DB_CONTAINER" psql -X -v ON_ERROR_STOP=1 -U tvt -d tvt -At "$@"; }
sources_sql="'{$(echo $KEEP_RAW_SOURCES | tr ' ' ',')}'::text[]"

# 1. The dump. The archives' load state goes first, so it can only be older than the dumped
# database (a load that lands meanwhile runs again on scratch; it's never skipped against rows
# the copy lacks). Then raw.record's rows: every fetch they point to is then in the dump's ops.fetch.
if [ -z "$from" ]; then
	day_only
	from=$DUMP_ROOT/$(date -u +%Y%m%dT%H%MZ)
	mkdir -p -m 700 "$from"
	chmod 700 "$from"
	say "dumping production to $from"
	seedarchive snapshot "$PROD_ARCHIVE" "$from/archive-state" $SEED_ARCHIVE_DIRS
	P -c "copy (select * from raw.record where source = any($sources_sql)) to stdout" | zstd -q -3 > "$from/raw-record.copy.zst.part"
	mv "$from/raw-record.copy.zst.part" "$from/raw-record.copy.zst"
	# pg_dump writes to stdout here: the file lands on the cold drive, outside the container.
	docker exec -e PGAPPNAME=$APP "$PROD_DB_CONTAINER" pg_dump -U tvt -d tvt -Fc --compress=zstd:3 \
		"${exclude[@]}" --exclude-table-data='restricted.*' --exclude-table-data=raw.record \
		> "$from/tvt.dump.part"
	mv "$from/tvt.dump.part" "$from/tvt.dump"
	# Did a load finish during the dump? The earlier snapshot stays either way; this only says so.
	seedarchive snapshot "$PROD_ARCHIVE" "$from/archive-state.after" $SEED_ARCHIVE_DIRS
	state_changed=0
	changed=$(seedarchive same "$from/archive-state" "$from/archive-state.after") || state_changed=$?
	rm -rf "$from/archive-state.after"
	[ $state_changed -le 1 ] || die "couldn't compare the load state's snapshots (seedarchive same: exit $state_changed)"
	[ $state_changed = 0 ] || say "production's load state changed during the dump ($changed): a load finished meanwhile; the copy keeps the earlier state, so that load runs again on scratch"
	P -F $'\t' -c "select version(), (select extversion from pg_extension where extname = 'timescaledb'),
	                      (select extversion from pg_extension where extname = 'postgis'),
	                      pg_database_size(current_database()), now()" > "$from/production.tsv"
	python3 - "$from" "$KEEP_RAW_SOURCES" "${private_schemas[*]}" "$SEED_ARCHIVE_DIRS" "$state_changed" <<'PY'
import json, os, sys
d, keep, private, seed_dirs, changed = sys.argv[1], sys.argv[2].split(), sys.argv[3].split(), sys.argv[4].split(), sys.argv[5]
version, ts, postgis, size, at = open(os.path.join(d, "production.tsv")).read().rstrip("\n").split("\t")
meta = {"dumped_at": at, "server": version, "timescaledb": ts, "postgis": postgis, "production_bytes": int(size),
        "raw_record_sources": keep,
        "left_out": ["raw.record's other rows", "restricted.* rows", "schemas private_*"] + [f"schema {s}" for s in private],
        "files": {f: os.path.getsize(os.path.join(d, f)) for f in ("tvt.dump", "raw-record.copy.zst")},
        "archive_state": {"dirs": seed_dirs, "taken": "before the dump",
                          "files": sorted(os.path.relpath(os.path.join(p, f), os.path.join(d, "archive-state"))
                                          for p, _, fs in os.walk(os.path.join(d, "archive-state")) for f in fs),
                          "changed_during_dump": changed != "0"}}
json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
PY
	touch "$from/COMPLETE"
	say "dump done in $(( $(date +%s) - t0 )) s: $(du -sh "$from" | cut -f1)"
fi
[ -z "$stopped" ] || exit 124

# 2. The restore, into <db>_restore; the old database stays as it is until the swap.
new=${db}_restore
t1=$(date +%s)
say "restoring into $new"
S -d postgres -c "drop database if exists $new with (force)" >/dev/null
docker exec "$SCRATCH_DB" createdb -U tvt -O tvt -T template0 -E UTF8 --locale-provider=libc --locale=C.UTF-8 "$new"
S -d "$new" -c "create extension if not exists timescaledb" -c "select timescaledb_pre_restore()" >/dev/null
docker exec -i -e PGAPPNAME=$APP "$SCRATCH_DB" pg_restore -U tvt -d "$new" --no-privileges --exit-on-error < "$from/tvt.dump"
[ -z "$stopped" ] || exit 124
raw=$(zstd -dc "$from/raw-record.copy.zst" | S -d "$new" -F ' ' \
	-c "create temp table raw_in (like raw.record)" \
	-c '\copy raw_in from pstdin' \
	-c "insert into raw.record select r.* from raw_in r where r.first_fetch is null or exists (select 1 from ops.fetch f where f.id = r.first_fetch)" \
	-c "select count(*), count(*) filter (where r.first_fetch is not null and not exists (select 1 from ops.fetch f where f.id = r.first_fetch)) from raw_in r" | tail -1)
read -r raw_rows raw_skipped <<<"$raw"
# The private plugins' migrations aren't in this copy (their schemas were left out); and nothing
# private may have come along (an older dump, a schema named otherwise): stop before the swap.
S -d "$new" -c "delete from ops.schema_migration where split_part(name, '/', 1) = any($private_plugins_sql)" >/dev/null
leak=$(S -d "$new" -c "select string_agg(nspname, ', ') from pg_namespace
                        where nspname like 'private\_%' or nspname = any($private_schemas_sql)")
[ -z "$leak" ] || die "the copy has private schemas ($leak): not swapping it in; $new left for a look (drop it by hand)"
say "restored in $(( $(date +%s) - t1 )) s; raw.record: $raw_rows rows ($raw_skipped skipped: their fetch came after the dump)"
[ -z "$stopped" ] || exit 124

# The new archive, staged beside the old: production's held files in its OSM folder as they are
# now (the extracts and their .md5), an empty inbox, and the load state from the dump's
# snapshot (not production's now: a load since the dump isn't in this copy). A dump made before
# the snapshot existed has none: then each loader's next load runs.
state=$from/archive-state
if [ -d "$state" ]; then
	archive_state="from the dump's snapshot"
else
	state=- archive_state="none: the dump has no snapshot"
	say "$from has no snapshot of the archives' load state (made before Oct 11's fix): $db's archive gets none, so each loader's next load runs"
fi
staged=$ARCHIVES/.staged-$db-$$
seedarchive stage "$PROD_ARCHIVE" "$state" "$staged" $SEED_ARCHIVE_DIRS
chmod -R u+rwX,go-rwx "$staged"
[ -z "$stopped" ] || exit 124

# 3. The swap: quick steps. timescaledb_pre_restore() stops the old database's background
# workers so it can be dropped; the new one stays in restore mode until it has its name.
if db_exists "$db"; then
	S -d "$db" -c "do \$\$ begin if exists (select 1 from pg_extension where extname = 'timescaledb')
	                 then perform timescaledb_pre_restore(); end if; end \$\$" >/dev/null
	S -d postgres -c "drop database $db with (force)" >/dev/null
fi
S -d postgres -c "alter database $new rename to $db" >/dev/null
mkdir -p "$ARCHIVES/.before-refresh"
rm -rf "$ARCHIVES/.before-refresh/$db"
old_archive="no archive before"
if [ -d "$ARCHIVES/$db" ]; then mv "$ARCHIVES/$db" "$ARCHIVES/.before-refresh/$db"; old_archive="the old one in archive/.before-refresh/$db"; fi
mv "$staged" "$ARCHIVES/$db"; staged=
S -d "$db" -c "select timescaledb_post_restore()" >/dev/null
S -d "$db" -c "analyze" >/dev/null
S -d "$db" -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$SCRATCH_ROOT/bin/tvt_build.sql" >/dev/null
say "swapped in as $db ($(S -d postgres -c "select pg_size_pretty(pg_database_size('$db'))")), with a fresh archive ($ARCHIVES/$db; $old_archive)"

# 4. Row counts: every table builders can read, production (now) against the copy. Tables
# that grew since the dump (the collectors keep running) show a difference; nothing else should.
tables=$(S -d "$db" -c "select format('%I.%I', schemaname, tablename) from pg_tables
                        where schemaname in ('core','obs','evt','ops','trees','public','raw') order by 1")
count_sql() {
	local t first=1
	echo "select * from (values "
	for t in $tables; do
		if [ "$t" = raw.record ]; then
			printf "%s('%s', (select count(*) from raw.record where source = any(%s)))\n" "$( [ $first = 1 ] || echo ,)" "$t" "$sources_sql"
		else
			printf "%s('%s', (select count(*) from %s))\n" "$( [ $first = 1 ] || echo ,)" "$t" "$t"
		fi
		first=0
	done
	echo ") v(t, n) order by 1"
}
count_sql | P -F $'\t' -f - > "$SCRATCH_ROOT/logs/counts-production.tsv"
count_sql | S -d "$db" -F $'\t' -f - > "$SCRATCH_ROOT/logs/counts-scratch.tsv"
python3 - "$SCRATCH_ROOT" "$from" "$db" "$raw_rows" "$raw_skipped" "$(( $(date +%s) - t0 ))" \
	"$(S -d postgres -c "select pg_database_size('$db')")" "$archive_state" <<'PY'
import json, os, sys
root, dump, db, raw_rows, raw_skipped, secs, size, archive_state = sys.argv[1:]
read = lambda p: dict(l.rstrip("\n").split("\t") for l in open(os.path.join(root, "logs", p)) if l.strip())
prod, scratch = read("counts-production.tsv"), read("counts-scratch.tsv")
diff = {t: {"production": int(prod.get(t, -1)), "scratch": int(n)} for t, n in scratch.items() if prod.get(t) != n}
meta = json.load(open(os.path.join(dump, "meta.json")))
out = {"db": db, "dump": dump, "dumped_at": meta["dumped_at"], "refresh_seconds": int(secs), "bytes": int(size),
       "tables_checked": len(scratch), "tables_differing": diff, "archive_load_state": archive_state,
       "raw_record": {"sources": meta["raw_record_sources"], "rows": int(raw_rows), "skipped": int(raw_skipped)}}
if db == "tvt":
    json.dump(out, open(os.path.join(root, "refresh.json"), "w"), indent=1)
json.dump(out, open(os.path.join(root, "logs", f"refresh-{db}.json"), "w"), indent=1)
print(f"{len(scratch)} tables checked; {len(diff)} differ from production now"
      + (": " + ", ".join(f"{t} {v['scratch']}/{v['production']}" for t, v in sorted(diff.items())) if diff else ""))
PY

# 5. Keep the newest dumps (never the one just used).
find "$DUMP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*Z' | sort | head -n -"$keep" | while read -r old; do
	[ "$old" = "$from" ] || { say "removing the old dump $old"; rm -rf "$old"; }
done
say "done in $(( $(date +%s) - t0 )) s"
