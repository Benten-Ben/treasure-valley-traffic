# Ingest service: applies database migrations, then runs scheduled sources.
# Build context is the repository root (see deploy/docker-compose.yml).
FROM python:3.12-slim
WORKDIR /repo
COPY ingest/requirements.txt ingest/requirements.txt
RUN pip install --no-cache-dir -r ingest/requirements.txt
COPY db db
COPY ingest ingest
USER nobody
CMD ["sh", "-c", "python3 db/migrate.py && exec python3 -m ingest serve"]
