# Ingest image: the ingest service (migrations, then scheduled sources) and the
# transit service (`python3 -m ingest stream vrt_realtime`) both run it.
# Build context is the repository root (see deploy/docker-compose.yml).
FROM python:3.12-slim
WORKDIR /repo
# osmium-tool cuts and filters OpenStreetMap extracts (plugins/roads/ingest/sources/osm_valley.py);
# owner decision, Oct 6, 2026. Adds about 4 MB.
RUN apt-get update \
 && apt-get install -y --no-install-recommends osmium-tool \
 && rm -rf /var/lib/apt/lists/*
COPY ingest/requirements.txt ingest/requirements.txt
RUN pip install --no-cache-dir -r ingest/requirements.txt
COPY db db
COPY ingest ingest
# The plugins: their code, manifests (read at start) and migrations (db/migrate.py).
COPY plugins plugins
# uid 1000 owns the archive and frames folders on the server.
USER 1000:1000
CMD ["sh", "-c", "python3 db/migrate.py && exec python3 -m ingest serve"]
