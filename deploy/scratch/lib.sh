# Shared by run.sh, refresh.sh and setup.sh (sourced, not run): settings, locks and the checks
# every scratch job and refresh makes. README.md in this folder explains them.
#
# Settings come from $SCRATCH_ROOT/scratch.conf on the server when it exists (shell syntax,
# KEY=value); everything below is a default. The server's own paths that aren't the project's
# (the cold drive's mount, for instance) live only in that file.
#
# The time windows, the camera roll-up and a planned VM restart are F7's heavy's rules:
# scratchq.py asks the installed heavy, so they live in one place.

SCRATCH_ROOT=${SCRATCH_ROOT:-/srv/tvt/work/scratch}
# shellcheck disable=SC1091
[ -f "$SCRATCH_ROOT/scratch.conf" ] && . "$SCRATCH_ROOT/scratch.conf"
SCRATCH_BIN=${SCRATCH_BIN:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)}

SCRATCH_NET=${SCRATCH_NET:-tvt-scratch}            # internal: the database and the jobs
SCRATCH_OUT_NET=${SCRATCH_OUT_NET:-tvt-scratch-out}  # a plain bridge: the jobs' way out (not the database's)
SCRATCH_DB=${SCRATCH_DB:-tvt-scratch-db}
SCRATCH_VOLUME=${SCRATCH_VOLUME:-tvt-scratch-db-data}
PROD_DB_CONTAINER=${PROD_DB_CONTAINER:-tvt-db-1}
PROD_ARCHIVE=${PROD_ARCHIVE:-/srv/tvt/archive}
WORK=${WORK:-/srv/tvt/work}
HEAVY=${HEAVY:-$WORK/bin/heavy}
CAMERA_STATUS_DIR=${CAMERA_STATUS_DIR:-$PROD_ARCHIVE/cameras/status}
INGEST_IMAGE=${INGEST_IMAGE:-tvt-ingest:latest}
WORKER_IMAGE=${WORKER_IMAGE:-tvt-worker:latest}
# Private plugins (TVT_PLUGIN_PATH's folder): a refresh leaves their schemas and migration rows
# out. With the private files, never mounted into a job.
PRIVATE_PLUGINS_DIR=${PRIVATE_PLUGINS_DIR:-/srv/tvt/plugins-private}
PRIVATE_DIRS=${PRIVATE_DIRS:-/srv/tvt/private:$PRIVATE_PLUGINS_DIR}
# The cold drive: dumps go there. Unset means "no cold drive": refresh refuses to dump.
DUMP_ROOT=${DUMP_ROOT:-}
COLD_MARKER=${COLD_MARKER:-}
COLD_MOUNT=${COLD_MOUNT:-}
# Each scratch database's archive (TVT_ARCHIVE in its jobs): $ARCHIVES/<db>/. A refresh replaces it.
ARCHIVES=$SCRATCH_ROOT/archive
LOCKS=$SCRATCH_ROOT/locks
# Archive folders a refresh seeds: production's held files now, and the load state (state/ and
# top-level *.json) from the dump's snapshot, taken before the dump (seedarchive.py).
SEED_ARCHIVE_DIRS=${SEED_ARCHIVE_DIRS:-osm}
# tvt_build's connection limit on the scratch server (production's is set when the role is made there).
SCRATCH_CONN_LIMIT=${SCRATCH_CONN_LIMIT:-30}
# Free space on / (GiB, as heavy and the camera collector count it, which pauses under 10):
# a light job starts with START_FLOOR_GB free and is stopped under STOP_FLOOR_GB. Heavy jobs: heavy's rule.
START_FLOOR_GB=${START_FLOOR_GB:-12}
STOP_FLOOR_GB=${STOP_FLOOR_GB:-11}
# Memory. Each job needs its cap plus MEM_RESERVE_MB available when it starts, and the caps of
# every scratch job going (light and heavy) stay within JOBS_BUDGET_MB. A heavy job not started
# through run.sh counts as HEAVY_OTHER_MB (plan §4.4's largest is 6 GB).
MEM_RESERVE_MB=${MEM_RESERVE_MB:-3072}
JOBS_BUDGET_MB=${JOBS_BUDGET_MB:-8192}
HEAVY_OTHER_MB=${HEAVY_OTHER_MB:-6144}
MAX_JOBS=${MAX_JOBS:-3}
# Package copies (refresh.sh --db tvt_<pkg>) besides tvt.
MAX_COPIES=${MAX_COPIES:-4}

boise() { TZ=America/Boise date "$@"; }
say() { echo "${SCRIPT:-scratch}: $*" >&2; }
die() { say "$*"; exit "${DIE_CODE:-2}"; }

# scratchq <question...>: scratchq.py, with the settings it reads.
scratchq() {
	HEAVY=$HEAVY WORK=$WORK CAMERA_STATUS_DIR=$CAMERA_STATUS_DIR SCRATCH_ROOT=$SCRATCH_ROOT \
	PROD_ARCHIVE=$PROD_ARCHIVE COLD_MOUNT=$COLD_MOUNT DUMP_ROOT=$DUMP_ROOT PRIVATE_DIRS=$PRIVATE_DIRS \
		python3 "$SCRATCH_BIN/scratchq.py" "$@"
}

# seedarchive <command...>: seedarchive.py (each database's archive and its load state).
seedarchive() { python3 "$SCRATCH_BIN/seedarchive.py" "$@"; }

# Free bytes on a filesystem, exact (df rounds -BG up).
free_bytes() { df -P -B1 "${1:-/}" | awk 'NR == 2 { print $4 }'; }
gib() { echo $(( $1 * 1073741824 )); }
free_gb() { awk -v b="$(free_bytes "${1:-/}")" 'BEGIN { printf "%.1f", b / 1073741824 }'; }
mem_available_mb() { awk '/^MemAvailable:/ { print int($2 / 1024) }' /proc/meminfo; }

# size_mb 2g|1500m|1024 -> megabytes
size_mb() {
	local v=${1,,}
	case $v in
		*g) awk -v n="${v%g}" 'BEGIN { printf "%d", n * 1024 }' ;;
		*m) awk -v n="${v%m}" 'BEGIN { printf "%d", n }' ;;
		*[0-9]) awk -v n="$v" 'BEGIN { printf "%d", n }' ;;
		*) return 1 ;;
	esac
}

# Run SQL on the scratch server as its owner (tvt) over the container's local socket.
scratch_psql() { docker exec -i "$SCRATCH_DB" psql -X -v ON_ERROR_STOP=1 -U tvt -At "$@"; }

# --- per-database locks -------------------------------------------------------------
# $LOCKS/<db>.lock: every job, psql session and grants run on <db> holds it shared; a refresh
# or drop of <db> holds it exclusively. $LOCKS/<db>.refresh (its pid) says a refresh is
# waiting or going, so no new job starts meanwhile (flock alone would let new ones in).

# db_lock_shared DB: on fd 8, for as long as this process (and what it execs) lives.
db_lock_shared() {
	local p
	mkdir -p "$LOCKS"
	p=$(cat "$LOCKS/$1.refresh" 2>/dev/null || true)
	if [ -n "$p" ] && [ -d "/proc/${p%% *}" ]; then
		die "a refresh of $1 is waiting or going (pid ${p%% *}); try again when it's done"
	fi
	exec 8>"$LOCKS/$1.lock"
	flock -s -n 8 || die "a refresh or drop is replacing $1; try again when it's done"
}

# --- memory -------------------------------------------------------------------------
# slots/<n>.owner: name=... mode=... mem_mb=N kind=light|heavy pid=... since=...

# The slot files of the scratch jobs going (their slot lock is still held; others are stale).
live_slots() {
	local f n
	for f in "$SCRATCH_ROOT"/slots/*.owner; do
		[ -e "$f" ] || continue
		n=${f##*/}; n=${n%.owner}
		( exec 9>"$SCRATCH_ROOT/slots/$n.lock"; ! flock -n 9 ) && echo "$f"
	done
	return 0
}

# The caps (MB) of the scratch jobs going.
committed_mb() {
	local f mb total=0
	for f in $(live_slots); do
		mb=$(sed -n 's/.*mem_mb=\([0-9][0-9]*\).*/\1/p' "$f")
		total=$((total + ${mb:-0}))
	done
	echo "$total"
}

# What a heavy job running outside run.sh counts for (MB): HEAVY_OTHER_MB while one holds
# heavy.lock (heavy.id's pid lives) and it isn't a scratch job (those hold a slot), else 0.
# A heavy scratch job asks while its own heavy holds the lock, before it has its slot: that
# holder is this job (heavy.id's id is the HEAVY_ID heavy gave it), not another one.
other_heavy_mb() {
	local id pid f
	id=$(cat "$WORK/heavy.id" 2>/dev/null) || { echo 0; return; }
	pid=$(echo "$id" | awk '{ print $2 }')
	[ -n "$pid" ] && [ -d "/proc/$pid" ] || { echo 0; return; }
	if [ -n "${SCRATCH_IN_HEAVY:-}" ] && [ -n "${HEAVY_ID:-}" ] && [ "$(echo "$id" | awk '{ print $1 }')" = "$HEAVY_ID" ]; then
		echo 0; return
	fi
	for f in $(live_slots); do
		grep -qs 'kind=heavy' "$f" && { echo 0; return; }
	done
	echo "$HEAVY_OTHER_MB"
}
