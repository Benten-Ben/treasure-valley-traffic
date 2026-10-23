#!/usr/bin/env bash
# Run a builder's command against the scratch database (landscape sprint plan, F6).
# Builders call it through their laptop wrapper, which first copies their worktree to
# $SCRATCH_ROOT/trees/<name>/. README.md in this folder has the rules.
#
#   run.sh [options] <name> ingest <args...>    python3 -m ingest <args>, in the ingest image
#   run.sh [options] <name> python <args...>    python3 <args>, in the ingest image
#   run.sh [options] <name> worker <cmd...>     <cmd...> in the worker image
#   run.sh [options] <name> migrate [--status]  db/migrate.py as the database's owner, then the grants
#   run.sh [options] <name> grants [--check]    the tvt_build grants (deploy/tvt_build.sql), or check them
#   run.sh [options] psql [psql args...]        psql on the scratch database (as tvt_build)
#   run.sh status                               the databases, the jobs going, disk and memory
#
#   <name>   the copied tree, $SCRATCH_ROOT/trees/<name>/ (a-z 0-9 . _ -, max 48); one job per name at once
#
# Options:
#   --owner              connect as the database's owner (tvt), for DDL by hand; builds run as tvt_build
#   --db NAME            another database on the scratch server (default tvt; a package's copy)
#   --memory SIZE        the job's memory cap: 2g by default (worker: 1g)
#   --cpus N             its CPU cap: 2 by default (worker: 1)
#   --offline            no network beyond the scratch database
#   --mount SRC:DST[:ro] an extra bind mount of a folder, repeatable: read-write under a folder of
#                        /srv/tvt/work/ or the cold drive's vm/; read-only under production's archive,
#                        the downloaded sources, the cold drive or the scratch archives
#   -e KEY=VALUE         an extra environment variable, repeatable
#   --runtime MIN        how long you expect it to take (default 10)
#   --limit MIN          stop a light job after this long (default 120)
#   --heavy LABEL        a heavy job (worker over 1g or 1 CPU; ingest over 2g or 2 CPUs): it runs under
#                        F7's heavy (/srv/tvt/work/heavy.lock) and needs --deadline and --runtime
#   --deadline HH:MM     Boise time; a heavy job is stopped there (heavy's windows: day by 23:15;
#                        overnight, once the camera roll-up has finished, by 05:45)
#   --peak-gb N          a heavy job's peak disk use on / (default 1): it needs 12 GB plus this free
#
# Exit code: the command's; 2 refused (a rule, a busy name, no room); 123 stopped because / fell
# under 11 GB free; 124 stopped at its limit or deadline; 130 interrupted. heavy's own refusals
# (73 disk, 75 not now) pass through.
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
[[ $db =~ ^[a-z_][a-z0-9_]{0,62}$ ]] && [ "$db" != postgres ] || die "--db: a plain database name (got '$db')"
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
		[ -f "$SCRATCH_ROOT/refresh.json" ] && echo "last refresh of tvt: $(tr -d '\n' < "$SCRATCH_ROOT/refresh.json" | head -c 400)"
		echo "archives: $(cd "$ARCHIVES" 2>/dev/null && ls -d -- */ 2>/dev/null | tr -d / | tr '\n' ' ')"
		echo "jobs going (caps $(committed_mb) MB of $JOBS_BUDGET_MB; a heavy job outside scratch counts $(other_heavy_mb) MB):"
		docker ps --filter label=tvt.scratch=job --format '  {{.Names}}  {{.Status}}  {{.Image}}'
		for f in $(live_slots); do echo "  slot ${f##*/}: $(cat "$f")"; done
		echo "free: $(free_gb /) GB on /, memory available $(mem_available_mb) MB$( [ -n "$DUMP_ROOT" ] && [ -d "$DUMP_ROOT" ] && echo ", $(free_gb "$DUMP_ROOT") GB on the cold drive")"
		echo "heavy.lock: $(cat "$WORK/heavy.owner" 2>/dev/null || echo free)"
		for f in "$LOCKS"/*.refresh; do [ -e "$f" ] && echo "refresh waiting or going: ${f##*/} (pid $(cat "$f"))"; done
		exit 0 ;;
	psql)
		shift
		running || die "the scratch database isn't running ($SCRATCH_ROOT/bin/setup.sh)"
		db_lock_shared "$db"                        # held by docker's client for the session
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
check=0
case $mode in
	ingest|python) image=$INGEST_IMAGE cmd=(python3) ; [ $mode = ingest ] && cmd+=(-m ingest); cmd+=("$@")
		: "${memory:=2g}" "${cpus:=2}"; light_mb=2048 light_cpus=2 ;;
	worker) [ $# -ge 1 ] || die "worker: give the command to run"
		image=$WORKER_IMAGE cmd=("$@"); : "${memory:=1g}" "${cpus:=1}"; light_mb=1024 light_cpus=1 ;;
	migrate) image=$INGEST_IMAGE cmd=(python3 db/migrate.py "$@"); user=tvt; : "${memory:=1g}" "${cpus:=1}"; light_mb=1024 light_cpus=1 ;;
	grants) case ${1:-} in --check) check=1 ;; "") ;; *) die "grants [--check]" ;; esac
		image= cmd=(); : "${memory:=0}" "${cpus:=0}"; light_mb=0 light_cpus=0 ;;
	*) die "unknown mode '$mode' (ingest, python, worker, migrate, grants, psql, status)" ;;
esac
mem_mb=$(size_mb "$memory") || die "--memory: e.g. 2g or 1500m (got '$memory')"
[[ $cpus =~ ^[0-9]+(\.[0-9]+)?$ ]] || die "--cpus: a number (got '$cpus')"
heavy_job=0
if [ "$mem_mb" -gt "$light_mb" ] || awk -v a="$cpus" -v b="$light_cpus" 'BEGIN { exit !(a > b) }'; then heavy_job=1; fi
if [ $heavy_job = 1 ]; then
	[ -n "$label" ] || die "$mode with --memory $memory --cpus $cpus is a heavy job: add --heavy '<who and what>' --deadline HH:MM --runtime MIN (or stay within ${light_mb} MB and $light_cpus CPUs)"
	[ -n "$deadline" ] || die "a heavy job needs --deadline HH:MM (Boise)"
	[ "$mem_mb" -le "$JOBS_BUDGET_MB" ] || die "--memory $memory is over the scratch jobs' budget ($JOBS_BUDGET_MB MB): run it with heavy directly, with the scratch slots idle"
elif [ -n "$label" ]; then
	heavy_job=1                                     # asked for: take the lock anyway
	[ -n "$deadline" ] || die "a heavy job needs --deadline HH:MM (Boise)"
fi

# Mounts and variables are checked before anything waits.
extra=()
for m in ${mounts[@]+"${mounts[@]}"}; do
	spec=$(scratchq mount "$m") || die "$spec"
	extra+=(-v "$spec")
done
for e in ${envs[@]+"${envs[@]}"}; do
	[[ $e =~ ^[A-Za-z_][A-Za-z0-9_]*=.*$ ]] || die "-e KEY=VALUE (got '$e')"
	case ${e%%=*} in DATABASE_URL|PG*|TVT_ARCHIVE|TVT_PROD_ARCHIVE|TVT_SOURCES|TVT_COLD|TVT_SCRATCH|HOME)
		die "-e ${e%%=*}: set by the wrapper (use --db or --owner)" ;; esac
	extra+=(-e "$e")
done

# One job per name, from now until it ends: the laptop wrapper copies a tree only while the name
# is free. A heavy job holds it while heavy waits for heavy.lock and runs (heavy keeps this
# descriptor open; the job it starts is this script again, its child).
if [ -z "${SCRATCH_IN_HEAVY:-}" ]; then
	mkdir -p "$SCRATCH_ROOT/runs"
	exec 7>"$SCRATCH_ROOT/runs/$name.lock"
	flock -n 7 || die "a job named $name is already going or waiting for heavy.lock"
else
	[ "$PPID" = "${SCRATCH_NAME_HOLDER:-}" ] || die "SCRATCH_IN_HEAVY is set, but my parent isn't the heavy that holds $name's lock"
fi

if [ $heavy_job = 1 ] && [ -z "${SCRATCH_IN_HEAVY:-}" ]; then
	[ -x "$HEAVY" ] || die "no $HEAVY (F7's heavy)"
	say "heavy job '$label': heavy checks its window, disk and a planned restart, and waits for heavy.lock (60 min at most)"
	# heavy (F7) checks the window, the disk and a planned restart, waits for the lock, and stops
	# the job and its labelled containers at the deadline (or 10 minutes before a planned restart).
	exec "$HEAVY" --deadline "$deadline" --runtime "$runtime" --peak "$peak" -w 60 "$label (scratch $name)" \
		env SCRATCH_IN_HEAVY=1 SCRATCH_NAME_HOLDER=$$ "$0" "${ARGV[@]}"
fi

# A light job: the disk, quiet hours, the 23:15 stop and a planned restart (scratchq, with heavy's rules).
if [ $heavy_job = 0 ]; then
	[ "$(free_bytes /)" -ge "$(gib "$START_FLOOR_GB")" ] || die "only $(free_gb /) GB free on /: a job needs $START_FLOOR_GB GB (the camera capture pauses under 10)"
	if [ $mode != grants ]; then
		out=$(scratchq light "$mem_mb" "$runtime" "$limit") || die "$out"
		stop_at=$out
	fi
else
	stop_at=${HEAVY_DEADLINE_EPOCH:?inside heavy, HEAVY_DEADLINE_EPOCH should be set}
fi

running || die "the scratch database isn't running ($SCRATCH_ROOT/bin/setup.sh)"
db_lock_shared "$db"
[ "$(scratch_psql -d postgres -c "select count(*) from pg_database where datname = '$db'")" = 1 ] || die "no database $db on the scratch server (refresh.sh --db $db makes a copy)"
[ -d "$ARCHIVES/$db" ] || die "no archive folder for $db ($ARCHIVES/$db): refresh it (refresh.sh --db $db --from-dump latest)"

if [ $mode = grants ] || [ $mode = migrate ]; then
	sql=$tree/deploy/tvt_build.sql
	[ -f "$sql" ] || sql=$SCRATCH_ROOT/bin/tvt_build.sql
fi
if [ $mode = grants ]; then
	if [ $check = 1 ]; then
		checks=$tree/deploy/scratch/grant-checks.sql
		[ -f "$checks" ] || checks=$SCRATCH_ROOT/bin/grant-checks.sql
		docker exec -i -e PGAPPNAME="scratch-$name" "$SCRATCH_DB" psql -X -q -v ON_ERROR_STOP=1 -U tvt_build -d "$db" -f - < "$checks"
		exit $?
	fi
	scratch_psql -d "$db" -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$sql" >/dev/null
	say "tvt_build's grants applied in $db (from ${sql#"$SCRATCH_ROOT/"})"
	exit 0
fi

# A slot (at most $MAX_JOBS jobs at once), within the jobs' memory budget, and room in memory:
# wait up to SCRATCH_WAIT_MIN minutes. One admission at a time (slots/.admit), so two jobs
# starting together can't both fit in the same room.
waited=0 slot=
until [ -n "$slot" ]; do
	exec 5>"$SCRATCH_ROOT/slots/.admit"
	flock -w 60 5 || die "another job's admission is stuck (slots/.admit)"
	for n in $(seq "$MAX_JOBS"); do
		exec 6>"$SCRATCH_ROOT/slots/$n.lock"
		if flock -n 6; then slot=$n; break; fi
		exec 6>&-
	done
	if [ -n "$slot" ]; then
		rm -f "$SCRATCH_ROOT/slots/$slot.owner"     # a stale one (this slot was free)
		avail=$(mem_available_mb) committed=$(committed_mb) other=$(other_heavy_mb)
		if [ $((committed + other + mem_mb)) -gt "$JOBS_BUDGET_MB" ]; then
			why="the scratch jobs' caps: $committed MB going$( [ "$other" = 0 ] || echo " and $other MB for the heavy job holding heavy.lock"), $mem_mb MB more is over $JOBS_BUDGET_MB MB"
			exec 6>&-; slot=
		elif [ "$avail" -lt $((mem_mb + MEM_RESERVE_MB)) ]; then
			why="memory: $avail MB available, the job needs $mem_mb MB plus $MEM_RESERVE_MB kept free"
			exec 6>&-; slot=
		fi
	else
		why="all $MAX_JOBS slots busy"
	fi
	if [ -z "$slot" ]; then
		exec 5>&-
		[ "$waited" -lt "${SCRATCH_WAIT_MIN:-15}" ] || die "gave up waiting: $why"
		[ "$waited" = 0 ] && say "waiting ($why)"
		[ $heavy_job = 0 ] || [ $(( $(date +%s) + 60 + runtime * 60 )) -le "$stop_at" ] || die "gave up waiting before the deadline: $why"
		sleep 60; waited=$((waited + 1))
	fi
done
printf 'name=%s mode=%s mem_mb=%s kind=%s pid=%s since=%s\n' "$name" "$mode" "$mem_mb" \
	"$( [ $heavy_job = 1 ] && echo heavy || echo light )" "$$" "$(boise '+%FT%T')" > "$SCRATCH_ROOT/slots/$slot.owner"
exec 5>&-

# The container. The tree is the code (/repo); TVT_ARCHIVE is this database's scratch archive
# (exports, inboxes and load state: it follows the database, a refresh replaces it); production's
# archive (but for its trees/), the downloaded sources and the cold drive are read-only, the scratch dumps hidden.
ctr=tvt-scratch-$name
docker container inspect "$ctr" >/dev/null 2>&1 && die "a container named $ctr already exists (docker rm -f $ctr if it's left over)"
args=(run --rm --init --name "$ctr" --label tvt.scratch=job --label "tvt.scratch.name=$name"
	--network "$SCRATCH_NET" --memory "${mem_mb}m" --memory-swap "${mem_mb}m" --cpus "$cpus" --cpu-shares 256
	--pids-limit 2048 --cap-drop ALL --security-opt no-new-privileges --user "$(id -u):$(id -g)" --env-file "$SCRATCH_ROOT/secrets/job-$( [ $user = tvt ] && echo owner || echo build ).env"
	-e "DATABASE_URL=postgresql://$user@$SCRATCH_DB:5432/$db" -e "PGDATABASE=$db" -e PGAPPNAME="scratch-$name"
	-e HOME=/tmp -e TZ=America/Boise -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e TVT_SCRATCH=1
	-e TVT_ARCHIVE=/srv/archive -e TVT_PROD_ARCHIVE=/srv/archive-prod -e TVT_SOURCES=/srv/sources
	-v "$tree":/repo -v "$ARCHIVES/$db":/srv/archive -v "$PROD_ARCHIVE":/srv/archive-prod:ro
	-v "$WORK/sources":/srv/sources:ro -w /repo)
[ $offline = 1 ] || args+=(--network "$SCRATCH_OUT_NET")
# Production's trees/ holds builds from the City of Boise's inventory (the pre-#277 format): hidden under an empty
# read-only tmpfs, as deploy/bin/sheets never mounts it. Nothing to hide (and no mount point to make in a read-only
# mount) when production has no trees/ folder.
[ ! -d "$PROD_ARCHIVE/trees" ] || args+=(--mount "type=tmpfs,destination=/srv/archive-prod/trees,tmpfs-size=1m,tmpfs-mode=0555")
[ -n "${HEAVY_LABEL:-}" ] && args+=(--label "$HEAVY_LABEL")       # so heavy's deadline stops it too
if [ -n "$COLD_MOUNT" ] && [ -n "$COLD_MARKER" ] && [ -e "$COLD_MARKER" ]; then
	args+=(-v "$COLD_MOUNT:$COLD_MOUNT:ro" -e "TVT_COLD=$COLD_MOUNT")
	# The scratch dumps are production's data: hidden under an empty read-only tmpfs.
	[ -n "$DUMP_ROOT" ] && [ -d "$DUMP_ROOT" ] && args+=(--mount "type=tmpfs,destination=$DUMP_ROOT,tmpfs-size=1m,tmpfs-mode=0555")
fi
args+=(${extra[@]+"${extra[@]}"} "$image" "${cmd[@]}")

log=$SCRATCH_ROOT/logs/jobs.tsv
t0=$(date +%s)
printf '%s\t%s\t%s\t%s\t%s\t%s MB\t%s CPU\t%s\tstart\t%s\n' "$(boise '+%F %T')" "$name" "$mode" "$user" "$db" "$mem_mb" "$cpus" \
	"$( [ $heavy_job = 1 ] && echo "heavy:$label" || echo light)" "${cmd[*]}" >> "$log"
say "$mode as $user on $db: ${mem_mb} MB, $cpus CPUs, until $(TZ=America/Boise date -d "@$stop_at" '+%H:%M') Boise ($( [ $heavy_job = 1 ] && echo heavy || echo light))"

stopped= watch= pid=
stop() {                                            # $1: why; $2: time|disk|interrupted
	stopped=${2:-time}
	say "stopping $ctr: $1"
	docker stop -t 30 "$ctr" >/dev/null 2>&1 || true
	# Its queries may still run on the server until they notice the client went: end them.
	scratch_psql -d postgres -c "select count(pg_terminate_backend(pid)) from pg_stat_activity
	  where application_name = 'scratch-$name' and datname = '$db'" >/dev/null 2>&1 || true
}
trap 'set +e; rm -f "$SCRATCH_ROOT/slots/$slot.owner"; [ -z "$watch" ] || kill "$watch" 2>/dev/null' EXIT
ended() {                                           # $1: exit code; logs the end
	printf '%s\t%s\t%s\t%s\t%s\t\t\t\tend\texit %s after %s s\n' "$(boise '+%F %T')" "$name" "$mode" "$user" "$db" "$1" "$(( $(date +%s) - t0 ))" >> "$log"
	say "$name $mode: exit $1 after $(( $(date +%s) - t0 )) s"
}
interrupted() {                                     # heavy's SIGTERM at its deadline counts as the deadline
	local c=130
	[ -n "${HEAVY_DEADLINE_EPOCH:-}" ] && [ "$(date +%s)" -ge $((HEAVY_DEADLINE_EPOCH - 5)) ] && c=124
	stop "$( [ $c = 124 ] && echo "heavy's deadline" || echo interrupted )" interrupted
	[ -z "$pid" ] || wait "$pid" 2>/dev/null
	ended $c
	exit $c
}
trap interrupted INT TERM HUP
trap 'stop "its time is up" time' USR1
trap 'stop "under '"$STOP_FLOOR_GB"' GB free on /" disk' USR2
docker "${args[@]}" &
pid=$!
# The watchdog: every 5 s it checks the free disk (a job is stopped under STOP_FLOOR_GB), and
# the stop time; for a light job, once a minute, a VM restart posted since it started. It
# signals this script, holds none of the locks, and its sleep goes with it.
light=$(( 1 - heavy_job ))
(
	exec 5>&- 6>&- 7>&- 8>&- 9>&-
	s=
	trap '[ -z "$s" ] || kill "$s" 2>/dev/null; exit 0' TERM
	floor=$(gib "$STOP_FLOOR_GB") next_m=$(( $(date +%s) + 60 ))
	while :; do
		sleep 5 & s=$!; wait "$s"; s=
		now=$(date +%s)
		if [ "$(free_bytes /)" -lt "$floor" ]; then kill -USR2 $$ 2>/dev/null; exit 0; fi
		if [ "$light" = 1 ] && [ "$now" -ge "$next_m" ]; then
			next_m=$((now + 60))
			cut=$(scratchq restart-cut 2>/dev/null || true)
			if [ -n "$cut" ] && [ "$cut" -lt "$stop_at" ]; then
				stop_at=$cut
				say "a VM restart was posted: $name stops at $(TZ=America/Boise date -d "@$cut" '+%H:%M') Boise"
			fi
		fi
		[ "$now" -lt "$stop_at" ] || { kill -USR1 $$ 2>/dev/null; exit 0; }
	done
) &
watch=$!
set +e
while :; do
	wait "$pid"; code=$?
	# A trapped signal interrupts wait with a code over 128 while the container still runs.
	kill -0 "$pid" 2>/dev/null || break
done
set -e
case $stopped in time) code=124 ;; disk) code=123 ;; esac

if [ $mode = migrate ] && [ $code = 0 ] && [[ " ${cmd[*]} " != *" --status "* ]]; then
	scratch_psql -d "$db" -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$sql" >/dev/null
	say "tvt_build's grants applied in $db (from ${sql#"$SCRATCH_ROOT/"})"
fi
ended "$code"
exit "$code"
