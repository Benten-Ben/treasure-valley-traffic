# Ingest image: the ingest service (migrations, then scheduled sources), the
# transit service (`python3 -m ingest stream vrt_realtime`) and the cameras
# service (`python3 -m ingest stream idaho511_frames`) all run it.
# Build context is the repository root (see deploy/docker-compose.yml).
FROM python:3.12-slim
# ffmpeg with SVT-AV1 for the daily camera videos (ingest/camera_video.py).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY ingest/requirements.txt ingest/requirements.txt
RUN pip install --no-cache-dir -r ingest/requirements.txt
COPY db db
COPY ingest ingest
# uid 1000 owns the archive and frames folders on the server.
USER 1000:1000
CMD ["sh", "-c", "python3 db/migrate.py && exec python3 -m ingest serve"]
