"""Ingestors: fetch sources we're allowed to collect, keep every record version
in raw.record, and update our own entities in core (docs/12).

Run from the repository root:
    python3 -m ingest sources                 # list sources
    python3 -m ingest run achd_cameras        # run one or more sources
"""

USER_AGENT = ("treasure-valley-traffic/0.2 "
              "(public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)")
AGENT_TOKEN = "treasure-valley-traffic"
