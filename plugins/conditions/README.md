# conditions

Live road conditions
([docs/15 §15.4](../../docs/15-plugins.md#154-the-plugins-we-already-have)):
ITD's work zones from its WZDx feed, and the 511 Idaho API's events,
advisories, truck restrictions, message signs, road-weather stations and
readings, and winter roads. Events of every kind go into core's lifecycle
table (`evt.event`, through `ingest/events.py`).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `itd_wzdx` | stream, every 5 min | public use (WZDx asks for CC0) | ITD (511 Idaho) | yes, raw or aggregated (owner, Oct 6) |
| `idaho511_api` | stream, per endpoint (2 min to daily; at most 8 calls a minute) | 511 Idaho developer terms | ITD (511 Idaho) | internal: not republished |

Details of each source: [ingest/README.md](../../ingest/README.md).

**Tables:** `core.message_sign`, `evt.sign_message`, `core.weather_station`,
`obs.weather_reading` (migration 0010), plus rows in core's `evt.event`
(migration 0009).

**Commands:**

```bash
TVT_ARCHIVE=data/archive python3 -m ingest stream itd_wzdx
TVT_ARCHIVE=data/archive IDAHO511_API_KEY=... python3 -m ingest stream idaho511_api   # key never committed
python3 -m ingest backfill itd_wzdx data/archive/wzdx       # load snapshots the database missed
python3 -m unittest discover -s plugins/conditions -t .
```

**Ethics:** the 511 API key lives only in the server's `deploy/.env`. The
API also rebuilds the regional camera capture list (on the server only; it's
511's data), which the cameras plugin's `regional` service reads.
