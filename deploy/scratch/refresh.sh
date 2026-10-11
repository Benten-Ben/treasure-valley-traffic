#!/usr/bin/env bash
# Refresh the scratch database from production (landscape sprint plan, F6). A heavy job, by hand.
#
#   refresh.sh --deadline HH:MM [--runtime MIN] [--from-dump DIR|latest] [--db NAME] [--keep N]
#
#   --deadline HH:MM   Boise time; everything stops there. Day: by 23:15. Overnight: only once the
#                      camera roll-up has finished, by 05:45
#   --runtime MIN      the expected time (default 30); it must fit before the deadline
#   --from-dump DIR    restore a dump made earlier (a folder under $DUMP_ROOT, or "latest") instead
#                      of dumping production again
#   --db NAME          restore into this database instead of tvt (e.g. a package's own copy)
#   --keep N           dumps kept on the cold drive (default 2)
#
# What it does, under /srv/tvt/work/heavy.lock:
#   1. Production, read only (as its owner, over the db container's socket):
#      raw.record's rows for the sources builders read ($KEEP_RAW_SOURCES), then pg_dump -Fc of
#      everything else: no rows from raw.record or restricted.*, and no city_trees schema at all.
#      To $DUMP_ROOT/<UTC stamp>/ on the cold drive, with meta.json.
#   2. The scratch server: a new database <db>_restore: timescaledb_pre_restore(), pg_restore
#      (no grants), the raw rows (any whose fetch isn't in the dump is skipped and counted),
#      then the swap: the old <db> is dropped and <db>_restore renamed, timescaledb_post_restore(),
#      ANALYZE, the tvt_build grants.
#   3. Row counts against production, $SCRATCH_ROOT/refresh.json, and the old dumps pruned.
#
# A refresh throws away everything builders put in that database (their migrations, loads and
# builds): they run `migrate` and their loads again. It waits up to 15 minutes for the jobs going
# to finish and no new ones start meanwhile. If it stops (deadline, error), the old database is
# left as it was, unless it had reached the swap's two quick steps.
set -euo pipefail
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

deadline= runtime=30 from= db=tvt keep=2
while [ $# -gt 0 ]; do
	case $1 in
		--deadline) deadline=${2:?}; shift 2 ;;
		--runtime) runtime=${2:?}; shift 2 ;;
		--from-dump) from=${2:?}; shift 2 ;;
		--db) db=${2:?}; shift 2 ;;
		--keep) keep=${2:?}; shift 2 ;;
		-h|--help) sed -n '2,32p' "$0"; exit 0 ;;
		*) die "unknown argument $1 (--help)" ;;
	esac
done
[[ $deadline =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "--deadline HH:MM (Boise) is required"
[[ $runtime =~ ^[0-9]+$ && $keep =~ ^[1-9][0-9]*$ ]] || die "--runtime and --keep take whole numbers"
[[ $db =~ ^[a-z_][a-z0-9_]{0,50}$ ]] && [ "$db" != postgres ] || die "--db: a plain database name (got '$db')"
[ -n "$DUMP_ROOT" ] && [ -n "$COLD_MARKER" ] || die "DUMP_ROOT and COLD_MARKER aren't set ($SCRATCH_ROOT/scratch.conf)"
[ -e "$COLD_MARKER" ] || die "the cold drive isn't there ($COLD_MARKER missing): dumps go only to it"

check() {
	check_maintenance 99
	local free why
	free=$(free_gb /)
	[ "$free" -ge $((HEAVY_FLOOR_GB + 3)) ] || die "only $free GB free on /: a refresh needs $HEAVY_FLOOR_GB GB plus about 3 GB"
	mkdir -p "$DUMP_ROOT"
	free=$(free_gb "$DUMP_ROOT")
	[ "$free" -ge 201 ] || die "only $free GB free on the cold drive: keep 200 GB free there"
	why=$(timeq window "$deadline" "$runtime") || die "$why"
}
check
if [ -z "${SCRATCH_IN_HEAVY:-}" ]; then
	say "waiting for $WORK/heavy.lock if it's busy"
	exec "$HEAVY" -w 60 "scratch refresh (F6, $db)" env SCRATCH_IN_HEAVY=1 "$0" "${ARGV[@]}"
fi
check
[ "$(docker inspect -f '{{.State.Running}}' "$SCRATCH_DB" 2>/dev/null)" = true ] || die "the scratch database isn't running (setup.sh)"
[ "$(docker inspect -f '{{.State.Running}}' "$PROD_DB_CONTAINER" 2>/dev/null)" = true ] || die "production's database isn't running"

if [ -n "$from" ]; then
	[ "$from" = latest ] && from=$(find "$DUMP_ROOT" -mindepth 2 -maxdepth 2 -name COMPLETE -printf '%h\n' | sort | tail -1)
	[[ $from = /* ]] || from=$DUMP_ROOT/$from
	[ -f "$from/COMPLETE" ] || die "no complete dump in '$from'"
fi

# No scratch job may be going while the database is replaced; new ones wait for this lock.
exec 8>"$SCRATCH_ROOT/refresh.lock"
if [ "$db" = tvt ]; then
	say "waiting for the scratch jobs going to finish (15 min at most)"
	flock -x -w 900 8 || die "scratch jobs still going after 15 minutes; try later"
fi

# The deadline: a watchdog ends our sessions on both servers (so the clients inside the
# containers stop too), then this script.
stop_at=$(timeq deadline "$deadline")
cancel() {
	local q="select count(pg_terminate_backend(pid)) from pg_stat_activity where application_name = '$APP' and pid <> pg_backend_pid()"
	docker exec "$PROD_DB_CONTAINER" psql -X -U tvt -d postgres -Atc "$q" >/dev/null 2>&1 || true
	docker exec "$SCRATCH_DB" psql -X -U tvt -d postgres -Atc "$q" >/dev/null 2>&1 || true
}
stopped=
trap 'stopped=1' USR1
trap 'cancel; exit 130' INT HUP
trap 'cancel; exit 143' TERM
secs=$((stop_at - $(date +%s)))
[ "$secs" -ge 1 ] || secs=1
( exec 8>&- 9>&-; sleep "$secs" & s=$!; trap 'kill $s 2>/dev/null; exit 0' TERM
  wait $s && { echo "scratch-refresh: deadline $deadline reached; stopping" >&2; kill -USR1 $$; cancel; } ) &
watch=$!
trap 'set +e; kill $watch 2>/dev/null; [ -z "$stopped" ] || say "stopped at the deadline: the old database is untouched unless the swap had begun"' EXIT

t0=$(date +%s)
P() { docker exec -i -e PGAPPNAME=$APP "$PROD_DB_CONTAINER" psql -X -v ON_ERROR_STOP=1 -U tvt -d tvt -At "$@"; }
S() { docker exec -i -e PGAPPNAME=$APP "$SCRATCH_DB" psql -X -v ON_ERROR_STOP=1 -U tvt -At "$@"; }
sources_sql="'{$(echo $KEEP_RAW_SOURCES | tr ' ' ',')}'::text[]"

# 1. The dump. raw.record's rows go first: every fetch they point to is then in the dump's ops.fetch.
if [ -z "$from" ]; then
	from=$DUMP_ROOT/$(date -u +%Y%m%dT%H%MZ)
	mkdir -p "$from"
	say "dumping production to $from"
	P -c "copy (select * from raw.record where source = any($sources_sql)) to stdout" | zstd -q -3 > "$from/raw-record.copy.zst.part"
	mv "$from/raw-record.copy.zst.part" "$from/raw-record.copy.zst"
	# pg_dump writes to stdout here: the file lands on the cold drive, outside the container.
	docker exec -e PGAPPNAME=$APP "$PROD_DB_CONTAINER" pg_dump -U tvt -d tvt -Fc --compress=zstd:3 \
		--exclude-schema=city_trees --exclude-table-data='restricted.*' --exclude-table-data=raw.record \
		> "$from/tvt.dump.part"
	mv "$from/tvt.dump.part" "$from/tvt.dump"
	P -F $'\t' -c "select version(), (select extversion from pg_extension where extname = 'timescaledb'),
	                      (select extversion from pg_extension where extname = 'postgis'),
	                      pg_database_size(current_database()), now()" > "$from/production.tsv"
	python3 - "$from" "$KEEP_RAW_SOURCES" <<'PY'
import json, os, sys
d, keep = sys.argv[1], sys.argv[2].split()
version, ts, postgis, size, at = open(os.path.join(d, "production.tsv")).read().rstrip("\n").split("\t")
meta = {"dumped_at": at, "server": version, "timescaledb": ts, "postgis": postgis, "production_bytes": int(size),
        "raw_record_sources": keep, "left_out": ["raw.record's other rows", "restricted.* rows", "schema city_trees"],
        "files": {f: os.path.getsize(os.path.join(d, f)) for f in ("tvt.dump", "raw-record.copy.zst")}}
json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
PY
	touch "$from/COMPLETE"
	say "dump done in $(( $(date +%s) - t0 )) s: $(du -sh "$from" | cut -f1)"
fi
[ -z "$stopped" ] || exit 124

# 2. The restore, into <db>_restore; the old database stays usable until the swap.
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
# The private plugin's migration isn't in this copy (its schema was left out).
S -d "$new" -c "delete from ops.schema_migration where name like 'city\_trees/%'" >/dev/null
say "restored in $(( $(date +%s) - t1 )) s; raw.record: $raw_rows rows ($raw_skipped skipped: their fetch came after the dump)"
[ -z "$stopped" ] || exit 124

# 3. The swap: two quick steps. timescaledb_pre_restore() stops the old database's background
# workers so it can be dropped; the new one stays in restore mode until it has its name.
if [ "$(S -d postgres -c "select count(*) from pg_database where datname = '$db'")" = 1 ]; then
	S -d "$db" -c "do \$\$ begin if exists (select 1 from pg_extension where extname = 'timescaledb')
	                 then perform timescaledb_pre_restore(); end if; end \$\$" >/dev/null
	S -d postgres -c "drop database $db with (force)" >/dev/null
fi
S -d postgres -c "alter database $new rename to $db" >/dev/null
S -d "$db" -c "select timescaledb_post_restore()" >/dev/null
S -d "$db" -c "analyze" >/dev/null
S -d "$db" -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$SCRATCH_ROOT/bin/tvt_build.sql" >/dev/null
say "swapped in as $db ($(S -d postgres -c "select pg_size_pretty(pg_database_size('$db'))"))"

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
	"$(S -d postgres -c "select pg_database_size('$db')")" <<'PY'
import json, os, sys
root, dump, db, raw_rows, raw_skipped, secs, size = sys.argv[1:]
read = lambda p: dict(l.rstrip("\n").split("\t") for l in open(os.path.join(root, "logs", p)) if l.strip())
prod, scratch = read("counts-production.tsv"), read("counts-scratch.tsv")
diff = {t: {"production": int(prod.get(t, -1)), "scratch": int(n)} for t, n in scratch.items() if prod.get(t) != n}
meta = json.load(open(os.path.join(dump, "meta.json")))
out = {"db": db, "dump": dump, "dumped_at": meta["dumped_at"], "refresh_seconds": int(secs), "bytes": int(size),
       "tables_checked": len(scratch), "tables_differing": diff,
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
