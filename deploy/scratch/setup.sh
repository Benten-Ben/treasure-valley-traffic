#!/usr/bin/env bash
# The scratch database for builders (landscape sprint plan, F6): set it up on the project VM.
#
#   setup.sh              install bin/, then create what's missing: folders, secrets, the network,
#                         the volume, the container and the tvt_build role
#   setup.sh --recreate   also replace the container (new settings or a new image; the data stays)
#
# Run it from a checkout of the repository on the server (it installs this folder's scripts and
# deploy/tvt_build.sql into $SCRATCH_ROOT/bin/). The database starts empty: load it with
# bin/refresh.sh (a heavy job). README.md in this folder has the design.
#
# The container: production's db image (timescaledb-ha), --memory 2g --cpus 2, half the
# services' CPU weight, on its own internal Docker network (no host port, no way out), its own
# volume. A throwaway server, so it writes little: wal_level minimal, synchronous_commit off.
set -euo pipefail
SCRIPT=scratch-setup
HERE=$(cd "$(dirname "$0")" && pwd -P)
# shellcheck source=lib.sh
. "$HERE/lib.sh"

recreate=0
case ${1:-} in --recreate) recreate=1 ;; "") ;; *) sed -n '2,15p' "$0" >&2; exit 2 ;; esac

mkdir -p "$SCRATCH_ROOT"/{bin,trees,runs,slots,archive,logs}
install -m 755 "$HERE"/lib.sh "$HERE"/setup.sh "$HERE"/run.sh "$HERE"/refresh.sh "$SCRATCH_ROOT/bin/"
install -m 644 "$HERE/../tvt_build.sql" "$SCRATCH_ROOT/bin/tvt_build.sql"
install -m 644 "$HERE/README.md" "$SCRATCH_ROOT/bin/README-repo.md"
# The scratch archive's OpenStreetMap folder starts as a copy of production's (the held extracts
# and their load state), so loaders see what production has seen; jobs never write production's.
if [ ! -d "$SCRATCH_ROOT/archive/osm" ] && [ -d "$PROD_ARCHIVE/osm" ]; then
	mkdir -p "$SCRATCH_ROOT/archive/osm/inbox"
	find "$PROD_ARCHIVE/osm" -maxdepth 1 -type f \( -name '*.osm.pbf' -o -name '*.md5' -o -name 'last-loaded.json' \) \
		-exec cp -p {} "$SCRATCH_ROOT/archive/osm/" \;
fi

# Secrets: the scratch server's own random passwords, made here, never shown.
umask 077
mkdir -p "$SCRATCH_ROOT/secrets"
if [ ! -f "$SCRATCH_ROOT/secrets/passwords.env" ]; then
	printf 'OWNER_PASSWORD=%s\nBUILD_PASSWORD=%s\n' "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" \
		> "$SCRATCH_ROOT/secrets/passwords.env"
fi
# shellcheck disable=SC1091
. "$SCRATCH_ROOT/secrets/passwords.env"
printf 'POSTGRES_PASSWORD=%s\n' "$OWNER_PASSWORD" > "$SCRATCH_ROOT/secrets/db.env"
# The jobs' libpq settings (run.sh adds DATABASE_URL without the password; libpq reads PGPASSWORD).
for who in build owner; do
	if [ $who = build ]; then user=tvt_build pw=$BUILD_PASSWORD; else user=tvt pw=$OWNER_PASSWORD; fi
	printf 'PGHOST=%s\nPGPORT=5432\nPGUSER=%s\nPGPASSWORD=%s\n' "$SCRATCH_DB" "$user" "$pw" > "$SCRATCH_ROOT/secrets/job-$who.env"
done
chmod 600 "$SCRATCH_ROOT/secrets/"*
umask 022

IMG=${SCRATCH_DB_IMAGE:-$(docker inspect -f '{{.Config.Image}}' "$PROD_DB_CONTAINER" 2>/dev/null || true)}
[ -n "$IMG" ] || die "can't tell production's db image (is $PROD_DB_CONTAINER running?); set SCRATCH_DB_IMAGE"

# Internal: the database can't reach out (and Timescale's telemetry stays off besides). Jobs also
# join a plain bridge network of their own for downloads (Docker won't mix the default bridge in).
docker network inspect "$SCRATCH_NET" >/dev/null 2>&1 ||
	docker network create --internal --label tvt.scratch=net "$SCRATCH_NET" >/dev/null
docker network inspect "$SCRATCH_OUT_NET" >/dev/null 2>&1 ||
	docker network create --label tvt.scratch=net "$SCRATCH_OUT_NET" >/dev/null
docker volume inspect "$SCRATCH_VOLUME" >/dev/null 2>&1 ||
	docker volume create --label tvt.scratch=db "$SCRATCH_VOLUME" >/dev/null
if [ $recreate = 1 ] && docker container inspect "$SCRATCH_DB" >/dev/null 2>&1; then
	say "replacing the container (the volume stays)"
	docker stop -t 60 "$SCRATCH_DB" >/dev/null && docker rm "$SCRATCH_DB" >/dev/null
fi
if ! docker container inspect "$SCRATCH_DB" >/dev/null 2>&1; then
	say "creating $SCRATCH_DB from $IMG"
	docker run -d --name "$SCRATCH_DB" --network "$SCRATCH_NET" --restart unless-stopped \
		--memory 2g --memory-swap 2g --cpus 2 --cpu-shares 512 --shm-size 256m --pids-limit 1024 \
		--env-file "$SCRATCH_ROOT/secrets/db.env" -e POSTGRES_USER=tvt -e POSTGRES_DB=tvt -e NO_TS_TUNE=true \
		--label tvt.scratch=db -v "$SCRATCH_VOLUME":/home/postgres/pgdata/data \
		"$IMG" postgres \
		-c shared_buffers=384MB -c effective_cache_size=1GB -c max_connections=40 \
		-c work_mem=16MB -c maintenance_work_mem=256MB -c max_locks_per_transaction=256 \
		-c max_worker_processes=12 -c max_parallel_workers=2 -c max_parallel_workers_per_gather=1 \
		-c max_parallel_maintenance_workers=1 -c timescaledb.max_background_workers=4 \
		-c timescaledb.telemetry_level=off -c jit=off -c random_page_cost=1.1 \
		-c wal_level=minimal -c max_wal_senders=0 -c archive_mode=off -c synchronous_commit=off \
		-c max_wal_size=1GB -c min_wal_size=128MB -c checkpoint_timeout=15min \
		-c log_temp_files=100MB -c log_min_duration_statement=-1 >/dev/null
fi
[ "$(docker inspect -f '{{.State.Running}}' "$SCRATCH_DB")" = true ] || docker start "$SCRATCH_DB" >/dev/null
# Over TCP: during its first start the image runs a socket-only server that then restarts.
for _ in $(seq 180); do docker exec "$SCRATCH_DB" pg_isready -q -h 127.0.0.1 -U tvt && break; sleep 1; done
docker exec "$SCRATCH_DB" pg_isready -h 127.0.0.1 -U tvt >/dev/null || die "the scratch database didn't come up"

# The owner's password follows the secrets file (the image sets it only on first start).
printf "alter role tvt password '%s'\n" "$OWNER_PASSWORD" | scratch_psql -d postgres >/dev/null
# tvt_build: the role, its caps and its grants in the scratch database, then its password.
scratch_psql -d tvt -v conn_limit="$SCRATCH_CONN_LIMIT" -f - < "$SCRATCH_ROOT/bin/tvt_build.sql" >/dev/null
printf "alter role tvt_build password '%s'\n" "$BUILD_PASSWORD" | scratch_psql -d postgres >/dev/null

scratch_psql -d postgres -F ' ' -c "select datname, pg_size_pretty(pg_database_size(datname)) from pg_database where not datistemplate order by 1"
say "ready: $SCRATCH_DB on $SCRATCH_NET ($IMG); load it with $SCRATCH_ROOT/bin/refresh.sh"
