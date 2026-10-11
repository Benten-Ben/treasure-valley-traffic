#!/usr/bin/env bash
# Run a builder's command against the scratch database (landscape sprint plan, F6).
# Builders call it through their laptop wrapper, which first copies their worktree to
# $SCRATCH_ROOT/trees/<name>/. README.md in this folder has the rules.
#
#   run.sh [options] <name> ingest <args...>    python3 -m ingest <args>, in the ingest image
#   run.sh [options] <name> python <args...>    python3 <args>, in the ingest image
#   run.sh [options] <name> worker <cmd...>     <cmd...> in the worker image
#   run.sh [options] <name> migrate [--status]  db/migrate.py as the database's owner, then the grants
#   run.sh [options] <name> grants              the tvt_build grants only (deploy/tvt_build.sql)
#   run.sh [options] psql [psql args...]        psql on the scratch database (as tvt_build)
#   run.sh status                               the database, the jobs going, disk and memory
#
#   <name>   the copied tree, $SCRATCH_ROOT/trees/<name>/ (a-z 0-9 . _ -, max 48); one job per name at once
#
# Options:
#   --owner              connect as the database's owner (tvt), for DDL by hand; builds run as tvt_build
#   --db NAME            another database on the scratch server (default tvt)
#   --memory SIZE        the job's memory cap: 2g by default (worker: 1g)
#   --cpus N             its CPU cap: 2 by default (worker: 1)
#   --offline            no network beyond the scratch database
#   --mount SRC:DST[:ro] an extra bind mount, repeatable: read-write under /srv/tvt/work/ or the cold
#                        drive's vm/ folder, read-only under the archive or the cold drive
#   -e KEY=VALUE         an extra environment variable, repeatable
#   --runtime MIN        how long you expect it to take (default 10; over 10 checks for a planned restart)
#   --limit MIN          stop a light job after this long (default 120)
#   --heavy LABEL        a heavy job (worker over 1g or 1 CPU; ingest over 2g or 2 CPUs): it takes
#                        /srv/tvt/work/heavy.lock and needs --deadline and --runtime
#   --deadline HH:MM     Boise time; a heavy job is stopped there (day: by 23:15; overnight, after the
#                        camera roll-up has finished: by 05:45)
#   --peak-gb N          a heavy job's peak disk use on / (default 1): it needs 12 GB plus this free
#
# Exit code: the command's; 2 refused (a rule, a busy name, no room); 124 stopped at its limit or
# deadline; 130 interrupted.
set -euo pipefail
SCRIPT=scratch-run
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=lib.sh
. "$HERE/lib.sh"
ARGV=("$@")

owner=0 db=tvt memory= cpus= offline=0 runtime=10 limit=120 label= deadline= peak=1
mounts=() envs=()
while [ $# -gt 0 ]; do
	case $1 in
		--owner) owner=1; shift ;;
		--offline) offline=1; shift ;;
		--db) db=${2:?}; shift 2 ;;
		--memory) memory=${2:?}; shift 2 ;;
		--cpus) cpus=${2:?}; shift 2 ;;
		--mount) mounts+=("${2:?}"); shift 2 ;;
		-e) envs+=("${2:?}"); shift 2 ;;
		--runtime) runtime=${2:?}; shift 2 ;;
		--limit) limit=${2:?}; shift 2 ;;
		--heavy) label=${2:?}; shift 2 ;;
		--deadline) deadline=${2:?}; shift 2 ;;
		--peak-gb) peak=${2:?}; shift 2 ;;
		--) shift; break ;;
		-h|--help) sed -n '2,36p' "$0"; exit 0 ;;
		-*) die "unknown option $1" ;;
		*) break ;;
	esac
done
[[ $db =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || die "--db: a plain database name (got '$db')"
[[ $runtime =~ ^[0-9]+$ && $limit =~ ^[0-9]+$ && $peak =~ ^[0-9]+$ ]] || die "--runtime, --limit and --peak-gb take whole numbers"
[ -z "$deadline" ] || [[ $deadline =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "--deadline takes HH:MM (Boise)"
user=tvt_build
[ $owner = 1 ] && user=tvt
running() { [ "$(docker inspect -f '{{.State.Running}}' "$SCRATCH_DB" 2>/dev/null)" = true ]; }

case ${1:-} in
	status)
		echo "scratch database: $(docker inspect -f '{{.State.Status}} since {{.State.StartedAt}}' "$SCRATCH_DB" 2>/dev/null || echo missing)"
		if running; then
			scratch_psql -d postgres -F ' | ' -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database where not datistemplate order by 1" \
				-c "select usename, datname, count(*) from pg_stat_activity where usename is not null and backend_type = 'client backend' group by 1, 2 order by 1, 2"
		fi
		[ -f "$SCRATCH_ROOT/refresh.json" ] && echo "last refresh: $(cat "$SCRATCH_ROOT/refresh.json")"
		echo "jobs going:"
		docker ps --filter label=tvt.scratch=job --format '  {{.Names}}  {{.Status}}  {{.Image}}'
		echo "free: $(free_gb /) GB on /, memory available $(mem_available_mb) MB$( [ -n "$DUMP_ROOT" ] && [ -d "$DUMP_ROOT" ] && echo ", $(free_gb "$DUMP_ROOT") GB on the cold drive")"
		[ -f "$MAINTENANCE_FILE" ] && echo "MAINTENANCE: $(head -c 300 "$MAINTENANCE_FILE")"
		echo "heavy.lock: $(cat "$WORK/heavy.owner" 2>/dev/null || echo free)"
		exit 0 ;;
	psql)
		shift
		running || die "the scratch database isn't running ($SCRATCH_ROOT/bin/setup.sh)"
		t=()
		[ -t 0 ] && [ -t 1 ] && t=(-t)
		exec docker exec -i "${t[@]}" -e PGAPPNAME=scratch-psql "$SCRATCH_DB" psql -X -U "$user" -d "$db" "$@" ;;
esac

[ $# -ge 2 ] || { sed -n '2,36p' "$0" >&2; exit 2; }
name=$1 mode=$2
shift 2
[[ $name =~ ^[a-z0-9][a-z0-9._-]{0,47}$ ]] || die "the name must be 1-48 of a-z 0-9 . _ - (got '$name')"
tree=$SCRATCH_ROOT/trees/$name
[ -f "$tree/db/migrate.py" ] && [ -d "$tree/ingest" ] || die "no copied tree at $tree (the laptop wrapper copies it first)"
case $mode in
	ingest|python) image=$INGEST_IMAGE cmd=(python3) ; [ $mode = ingest ] && cmd+=(-m ingest); cmd+=("$@")
		: "${memory:=2g}" "${cpus:=2}"; light_mb=2048 light_cpus=2 ;;
	worker) [ $# -ge 1 ] || die "worker: give the command to run"
		image=$WORKER_IMAGE cmd=("$@"); : "${memory:=1g}" "${cpus:=1}"; light_mb=1024 light_cpus=1 ;;
	migrate) image=$INGEST_IMAGE cmd=(python3 db/migrate.py "$@"); user=tvt; : "${memory:=1g}" "${cpus:=1}"; light_mb=1024 light_cpus=1 ;;
	grants) image= cmd=(); : "${memory:=0}" "${cpus:=0}"; light_mb=0 light_cpus=0 ;;
	*) die "unknown mode '$mode' (ingest, python, worker, migrate, grants, psql, status)" ;;
esac
mem_mb=$(size_mb "$memory") || die "--memory: e.g. 2g or 1500m (got '$memory')"
[[ $cpus =~ ^[0-9]+(\.[0-9]+)?$ ]] || die "--cpus: a number (got '$cpus')"
heavy_job=0
if [ "$mem_mb" -gt "$light_mb" ] || awk -v a="$cpus" -v b="$light_cpus" 'BEGIN { exit !(a > b) }'; then heavy_job=1; fi
if [ $heavy_job = 1 ]; then
	[ -n "$label" ] || die "$mode with --memory $memory --cpus $cpus is a heavy job: add --heavy '<who and what>' --deadline HH:MM --runtime MIN (or stay within ${light_mb} MB and $light_cpus CPUs)"
	[ -n "$deadline" ] || die "a heavy job needs --deadline HH:MM (Boise)"
elif [ -n "$label" ]; then
	heavy_job=1                                     # asked for: take the lock anyway
	[ -n "$deadline" ] || die "a heavy job needs --deadline HH:MM (Boise)"
fi

# The rules, checked before waiting for anything and again once the heavy lock is ours.
check_rules() {
	check_maintenance "$( [ $heavy_job = 1 ] && echo 99 || echo "$runtime" )"
	local free why
	free=$(free_gb /)
	if [ $heavy_job = 1 ]; then
		[ "$free" -ge $((HEAVY_FLOOR_GB + peak)) ] || die "only $free GB free on /: a heavy job needs $HEAVY_FLOOR_GB GB plus its peak ($peak GB)"
		why=$(timeq window "$deadline" "$runtime") || die "$why"
	else
		[ "$free" -ge "$LIGHT_FLOOR_GB" ] || die "only $free GB free on /: jobs need $LIGHT_FLOOR_GB GB"
		if quiet && [ "$mem_mb" -gt 1024 ] && ! timeq rollup-done >/dev/null; then
			die "quiet hours (23:15-06:00 Boise): until the camera roll-up has finished, jobs get 1 GB at most (--memory 1g), or wait"
		fi
	fi
}
check_rules

if [ $heavy_job = 1 ] && [ -z "${SCRATCH_IN_HEAVY:-}" ]; then
	[ -x "$HEAVY" ] || die "no $HEAVY"
	say "heavy job '$label': waiting for $WORK/heavy.lock if it's busy"
	exec "$HEAVY" -w 60 "$label (scratch $name)" env SCRATCH_IN_HEAVY=1 "$0" "${ARGV[@]}"
fi
[ -n "${SCRATCH_IN_HEAVY:-}" ] && check_rules       # time may have passed while it waited

running || die "the scratch database isn't running ($SCRATCH_ROOT/bin/setup.sh)"
# One job per name; none while a refresh replaces the database (it takes refresh.lock exclusively).
exec 7>"$SCRATCH_ROOT/runs/$name.lock"
flock -n 7 || die "a job named $name is already going"
exec 8>"$SCRATCH_ROOT/refresh.lock"
flock -s -n 8 || die "a refresh is replacing the scratch database; try again when it's done"

if [ $mode = grants ] || [ $mode = migrate ]; then
	sql=$tree/deploy/tvt_build.sql
	[ -f "$sql" ] || sql=$SCRATCH_ROOT/bin/tvt_build.sql
fi
if [ $mode = grants ]; then
	scratch_psql -d "$db" -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$sql" >/dev/null
	say "tvt_build's grants applied in $db (from ${sql#"$SCRATCH_ROOT/"})"
	exit 0
fi

# A slot (at most $MAX_JOBS jobs at once) and room in memory: wait up to SCRATCH_WAIT_MIN minutes.
waited=0 slot=
until [ -n "$slot" ]; do
	for n in $(seq "$MAX_JOBS"); do
		exec 6>"$SCRATCH_ROOT/slots/$n.lock"
		if flock -n 6; then slot=$n; break; fi
		exec 6>&-
	done
	avail=$(mem_available_mb)
	if [ -n "$slot" ] && [ "$avail" -lt $((mem_mb + MEM_RESERVE_MB)) ]; then
		why="memory: $avail MB available, the job needs $mem_mb MB plus $MEM_RESERVE_MB kept free"
		exec 6>&-; slot=
	elif [ -z "$slot" ]; then
		why="all $MAX_JOBS slots busy"
	fi
	if [ -z "$slot" ]; then
		[ "$waited" -lt "${SCRATCH_WAIT_MIN:-15}" ] || die "gave up waiting: $why"
		[ "$waited" = 0 ] && say "waiting ($why)"
		sleep 60; waited=$((waited + 1))
	fi
done
echo "$name $mode (pid $$, since $(boise '+%F %T'))" > "$SCRATCH_ROOT/slots/$slot.owner"

# When it must stop: a heavy job at its deadline; a light one after --limit, and before midnight
# if it holds more than 1 GB (the camera roll-up starts at 00:05).
now=$(date +%s)
if [ $heavy_job = 1 ]; then
	stop_at=$(timeq deadline "$deadline")
else
	stop_at=$((now + limit * 60))
	if [ "$mem_mb" -gt 1024 ] && ! quiet; then
		midnight=$(timeq deadline 00:00)
		[ "$midnight" -lt "$stop_at" ] && stop_at=$midnight
	fi
fi

# The container. The tree is the code (/repo); TVT_ARCHIVE is the scratch archive (exports and
# inboxes go there, never production's); production's archive, the downloaded sources and the
# cold drive are read-only.
ctr=tvt-scratch-$name
docker container inspect "$ctr" >/dev/null 2>&1 && die "a container named $ctr already exists (docker rm -f $ctr if it's left over)"
args=(run --rm --init --name "$ctr" --label tvt.scratch=job --label "tvt.scratch.name=$name"
	--network "$SCRATCH_NET" --memory "${mem_mb}m" --memory-swap "${mem_mb}m" --cpus "$cpus" --cpu-shares 256
	--pids-limit 2048 --user "$(id -u):$(id -g)" --env-file "$SCRATCH_ROOT/secrets/job-$( [ $user = tvt ] && echo owner || echo build ).env"
	-e "DATABASE_URL=postgresql://$user@$SCRATCH_DB:5432/$db" -e "PGDATABASE=$db" -e PGAPPNAME="scratch-$name"
	-e HOME=/tmp -e TZ=America/Boise -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e TVT_SCRATCH=1
	-e TVT_ARCHIVE=/srv/archive -e TVT_PROD_ARCHIVE=/srv/archive-prod -e TVT_SOURCES=/srv/sources
	-v "$tree":/repo -v "$SCRATCH_ROOT/archive":/srv/archive -v "$PROD_ARCHIVE":/srv/archive-prod:ro
	-v "$WORK/sources":/srv/sources:ro -w /repo)
[ $offline = 1 ] || args+=(--network "$SCRATCH_OUT_NET")
if [ -n "$COLD_MOUNT" ] && [ -n "$COLD_MARKER" ] && [ -e "$COLD_MARKER" ]; then
	args+=(-v "$COLD_MOUNT:$COLD_MOUNT:ro" -e "TVT_COLD=$COLD_MOUNT")
fi
for m in "${mounts[@]}"; do
	IFS=: read -r src dst ro <<<"$m"
	[ -n "$src" ] && [ -n "$dst" ] && [[ $dst = /* ]] && { [ -z "$ro" ] || [ "$ro" = ro ]; } || die "--mount SRC:DST[:ro] (got '$m')"
	src=$(realpath -m "$src")
	case $src/ in
		"$WORK"/*|"${COLD_MOUNT:-/nonexistent}"/vm/*) ;;
		"$PROD_ARCHIVE"/*|"${COLD_MOUNT:-/nonexistent}"/*) [ "$ro" = ro ] || die "--mount $src: read-only only (add :ro)" ;;
		*) die "--mount $src: only under $WORK/, the cold drive or (read-only) $PROD_ARCHIVE/" ;;
	esac
	case $src/ in */private/*|*/plugins-private/*|*/secrets/*|"$WORK"/e2e/*) die "--mount $src: private files and secrets stay out of scratch jobs" ;; esac
	[ "$src" != "$WORK" ] || die "--mount $src: too broad; mount the folder you need"
	[ -e "$src" ] || die "--mount $src: no such path"
	args+=(-v "$src:$dst${ro:+:ro}")
done
for e in "${envs[@]}"; do
	[[ $e =~ ^[A-Za-z_][A-Za-z0-9_]*=.*$ ]] || die "-e KEY=VALUE (got '$e')"
	case ${e%%=*} in DATABASE_URL|PG*) die "-e ${e%%=*}: set by the wrapper (use --db or --owner)" ;; esac
	args+=(-e "$e")
done
args+=("$image" "${cmd[@]}")

log=$SCRATCH_ROOT/logs/jobs.tsv
t0=$(date +%s)
printf '%s\t%s\t%s\t%s\t%s\t%s MB\t%s CPU\t%s\tstart\t%s\n' "$(boise '+%F %T')" "$name" "$mode" "$user" "$db" "$mem_mb" "$cpus" \
	"$( [ $heavy_job = 1 ] && echo "heavy:$label" || echo light)" "${cmd[*]}" >> "$log"
say "$mode as $user on $db: ${mem_mb} MB, $cpus CPUs, until $(TZ=America/Boise date -d "@$stop_at" '+%H:%M') Boise ($( [ $heavy_job = 1 ] && echo heavy || echo light))"

stopped= watch=
stop() {                                            # $1: why
	stopped=$1
	say "stopping $ctr: $1"
	docker stop -t 30 "$ctr" >/dev/null 2>&1 || true
}
trap 'set +e; rm -f "$SCRATCH_ROOT/slots/$slot.owner"; [ -z "$watch" ] || kill "$watch" 2>/dev/null' EXIT
ended() {                                           # $1: exit code; logs the end
	printf '%s\t%s\t%s\t%s\t%s\t\t\t\tend\texit %s after %s s\n' "$(boise '+%F %T')" "$name" "$mode" "$user" "$db" "$1" "$(( $(date +%s) - t0 ))" >> "$log"
	say "$name $mode: exit $1 after $(( $(date +%s) - t0 )) s"
}
trap 'stop interrupted; wait "$pid" 2>/dev/null; ended 130; exit 130' INT TERM HUP
trap 'stop "its time is up"' USR1
docker "${args[@]}" &
pid=$!
# The watchdog: signals this script at the stop time. It holds none of the locks, and its sleep
# goes with it, so nothing outlives the job.
secs=$((stop_at - $(date +%s)))
[ "$secs" -ge 1 ] || secs=1
( exec 6>&- 7>&- 8>&- 9>&-; sleep "$secs" & s=$!; trap 'kill $s 2>/dev/null; exit 0' TERM
  wait $s && kill -USR1 $$ 2>/dev/null ) &
watch=$!
set +e
while :; do
	wait "$pid"; code=$?
	# A trapped signal interrupts wait with a code over 128 while the container still runs.
	kill -0 "$pid" 2>/dev/null || break
done
set -e
[ -n "$stopped" ] && code=124

if [ $mode = migrate ] && [ $code = 0 ] && [[ " ${cmd[*]} " != *" --status "* ]]; then
	scratch_psql -d "$db" -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$sql" >/dev/null
	say "tvt_build's grants applied in $db (from ${sql#"$SCRATCH_ROOT/"})"
fi
ended "$code"
exit "$code"
