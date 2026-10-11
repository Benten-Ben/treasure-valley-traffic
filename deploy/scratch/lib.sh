# Shared by run.sh and refresh.sh (sourced, not run): settings, the time windows and the checks
# that every scratch job and refresh makes. README.md in this folder explains them.
#
# Settings come from $SCRATCH_ROOT/scratch.conf on the server when it exists (shell syntax,
# KEY=value); everything below is a default. The server's own paths that aren't the project's
# (the cold drive's mount, for instance) live only in that file.

SCRATCH_ROOT=${SCRATCH_ROOT:-/srv/tvt/work/scratch}
# shellcheck disable=SC1091
[ -f "$SCRATCH_ROOT/scratch.conf" ] && . "$SCRATCH_ROOT/scratch.conf"

SCRATCH_NET=${SCRATCH_NET:-tvt-scratch}            # internal: the database and the jobs
SCRATCH_OUT_NET=${SCRATCH_OUT_NET:-tvt-scratch-out}  # a plain bridge: the jobs' way out (not the database's)
SCRATCH_DB=${SCRATCH_DB:-tvt-scratch-db}
SCRATCH_VOLUME=${SCRATCH_VOLUME:-tvt-scratch-db-data}
PROD_DB_CONTAINER=${PROD_DB_CONTAINER:-tvt-db-1}
PROD_ARCHIVE=${PROD_ARCHIVE:-/srv/tvt/archive}
WORK=${WORK:-/srv/tvt/work}
HEAVY=${HEAVY:-$WORK/bin/heavy}
MAINTENANCE_FILE=${MAINTENANCE_FILE:-$WORK/MAINTENANCE}
CAMERA_STATUS_DIR=${CAMERA_STATUS_DIR:-$PROD_ARCHIVE/cameras/status}
INGEST_IMAGE=${INGEST_IMAGE:-tvt-ingest:latest}
WORKER_IMAGE=${WORKER_IMAGE:-tvt-worker:latest}
# The cold drive: dumps go there. Unset means "no cold drive": refresh refuses to dump.
DUMP_ROOT=${DUMP_ROOT:-}
COLD_MARKER=${COLD_MARKER:-}
COLD_MOUNT=${COLD_MOUNT:-}
# tvt_build's connection limit on the scratch server (production's is set when the role is made there).
SCRATCH_CONN_LIMIT=${SCRATCH_CONN_LIMIT:-30}
# Free space on / below which nothing starts (GB): light jobs, and the base for heavy ones (plus their peak).
LIGHT_FLOOR_GB=${LIGHT_FLOOR_GB:-10}
HEAVY_FLOOR_GB=${HEAVY_FLOOR_GB:-12}
# Memory kept free for the services when admitting a job (MB), on top of the job's own cap.
MEM_RESERVE_MB=${MEM_RESERVE_MB:-3072}
MAX_JOBS=${MAX_JOBS:-3}

boise() { TZ=America/Boise date "$@"; }
say() { echo "${SCRIPT:-scratch}: $*" >&2; }
die() { say "$*"; exit "${DIE_CODE:-2}"; }

# Time and camera roll-up questions, answered in Python (zoneinfo) so the arithmetic across
# midnight and daylight saving stays right.
#   timeq hm                    minutes since Boise midnight, now
#   timeq deadline HH:MM        epoch seconds of the next HH:MM in Boise (today, or tomorrow if it's passed)
#   timeq rollup-done           exit 0 when tonight's camera roll-up has finished (see README)
#   timeq window HH:MM MIN      exit 0 if a heavy job of MIN minutes may run now with that deadline; else say why
timeq() {
	python3 - "$CAMERA_STATUS_DIR" "$@" <<'PY'
import json, os, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Boise")
status_dir, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
now = datetime.now(TZ)
today = now.replace(hour=0, minute=0, second=0, microsecond=0)

def at(hhmm, day=today):
    h, m = (int(x) for x in hhmm.split(":"))
    return day.replace(hour=h, minute=m)

def next_at(hhmm):
    t = at(hhmm)
    return t if t > now else at(hhmm, today + timedelta(days=1))

def rollup_done():
    """After 00:05, both capture services say no roll-up is going, in a status written at least one
    capture cycle after 00:05 (each writes it once a cycle: 50 s and 600 s) and still fresh."""
    start = at("00:05")
    if not (start <= now < at("06:00")):
        return False, "it's not between 00:05 and 06:00 in Boise"
    for name in ("key_cameras.json", "regional-cameras.json"):
        try:
            with open(os.path.join(status_dir, name)) as f:
                s = json.load(f)
            beat = datetime.fromisoformat(s["heartbeat_at"].replace("Z", "+00:00"))
            cadence = timedelta(seconds=float(s.get("cadence_s", 600)))
        except (OSError, ValueError, KeyError) as err:
            return False, f"can't read {name}: {err}"
        if s.get("rolling_up"):
            return False, f"{name}: the roll-up is still going"
        if beat < start + cadence + timedelta(seconds=60):
            return False, f"{name}: no status since the roll-up could start (last {beat.astimezone(TZ):%H:%M})"
        if now - beat > 2 * cadence + timedelta(seconds=120):
            return False, f"{name}: its status is stale (last {beat.astimezone(TZ):%H:%M})"
    return True, "the roll-up has finished"

if cmd == "hm":
    print(now.hour * 60 + now.minute)
elif cmd == "deadline":
    print(int(next_at(args[0]).timestamp()))
elif cmd == "rollup-done":
    ok, why = rollup_done()
    print(why)
    sys.exit(0 if ok else 1)
elif cmd == "window":
    deadline, minutes = next_at(args[0]), int(args[1])
    day = at("06:00") <= now < at("23:15")
    if day:
        if deadline > at("23:15"):
            print(f"in the day a heavy job's deadline is 23:15 at the latest (asked {args[0]})")
            sys.exit(1)
    else:
        ok, why = rollup_done()
        if not ok:
            print(f"quiet hours (23:15-06:00 Boise): heavy jobs wait for the camera roll-up to finish ({why})")
            sys.exit(1)
        if deadline > at("05:45"):
            print(f"overnight a heavy job's deadline is 05:45 at the latest (asked {args[0]})")
            sys.exit(1)
    if now + timedelta(minutes=minutes) > deadline:
        print(f"{minutes} min from now ({now:%H:%M}) runs past the deadline {deadline:%H:%M}")
        sys.exit(1)
    print(f"ok until {deadline:%H:%M} Boise")
else:
    sys.exit(f"timeq: unknown question {cmd}")
PY
}

# quiet: 0 when it's 23:15-06:00 in Boise.
quiet() { local hm; hm=$(timeq hm); [ "$hm" -ge 1395 ] || [ "$hm" -lt 360 ]; }

free_gb() { df -P -BG "${1:-/}" | awk 'NR == 2 { sub("G", "", $4); print $4 }'; }
mem_available_mb() { awk '/^MemAvailable:/ { print int($2 / 1024) }' /proc/meminfo; }

# check_maintenance MINUTES: a job of more than 10 minutes doesn't start while a planned VM restart is posted.
check_maintenance() {
	[ -f "$MAINTENANCE_FILE" ] || return 0
	if [ "${1:-0}" -gt 10 ]; then
		die "a VM restart is planned ($MAINTENANCE_FILE: $(head -c 300 "$MAINTENANCE_FILE")); jobs over 10 minutes wait until it's done"
	fi
	say "note: a VM restart is planned ($MAINTENANCE_FILE: $(head -c 300 "$MAINTENANCE_FILE"))"
}

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
