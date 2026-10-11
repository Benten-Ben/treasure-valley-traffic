"""The irrigation districts' canal dates: a versioned file, loaded by hand (plan P5; the owner's decision 18).

Each district announces when it turns water into its canals and when it shuts it off. Those dates are looked up by
hand when the owner asks, one page at a time (never scraped, never scheduled), and kept in
plugins/water/ingest/canal_dates.json, which is the record: the server keeps no backups, so the dates live in the
repository, each with the page it came from and the day we read it. The file started empty (Oct 11, 2026).

    python3 -m ingest canal-dates-load [--file PATH] [--dry-run]

checks the file (unknown keys, malformed dates, an entry without its page are refused), replaces water.canal_date
with it, records the load in water.load, and then derives the canal season again (season.py), so the map follows
the file within the minute. Names that match no canal of the current water build are reported, not refused: a
canal renamed in OpenStreetMap shouldn't stop the load, but the entry then selects nothing until it's fixed.

An entry (see the file's "about"): id, district, canals (water.canal names; "branches": true adds the canals fed
from them, through water.canal.source_canal_id), on and/or off (a date, 'YYYY-MM-DD', meaning that day's start in
Boise, or a date and time), text (the district's words), source (the page's URL), read (YYYY-MM-DD) and optionally
republish (default yes). Both dates fall in one calendar year, its season. How an entry becomes rules: season.py.

Licence: the dates are facts, each cited to the district's page; the words are quoted, a sentence at most.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from ingest import manifest, seasons

from .. import rules

FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "canal_dates.json")
TABLE = "water.canal_date"

SOURCE = {
    "name": "canal_dates",
    "title": "The irrigation districts' canal dates (water on and off), entered by hand from their own pages",
    "url": "https://github.com/Benten-Ben/treasure-valley-traffic/blob/main/plugins/water/ingest/canal_dates.json",
    "access": "one_off",
    "schedule": None,    # by hand, when the owner asks for the lookups: python3 -m ingest canal-dates-load
    "license": "facts (dates) from each district's own page, cited",
    "credit": "The irrigation districts, as each entry of canal_dates.json cites",
    "notes": "A versioned file (plugins/water/ingest/canal_dates.json), loaded into water.canal_date by "
             "canal-dates-load. Each entry cites its page and the day it was read. Read by the canal_season source.",
}

TOP_KEYS = {"about", "seasons"}
KEYS = {"id", "district", "canals", "branches", "on", "off", "text", "source", "read", "republish"}
ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL = re.compile(r"^https?://\S+$")
TEXT_MAX = 500


@dataclass(frozen=True)
class Season:
    """One district's season for some canals, as loaded. on_at and off_at are UTC datetimes (or None)."""
    id: str
    position: int
    district: str
    canals: tuple
    branches: bool
    season: int
    on_at: Optional[datetime]
    off_at: Optional[datetime]
    on_given: Optional[str]
    off_given: Optional[str]
    words: Optional[str]
    source: str
    read_on: date
    republish: str = "yes"


def _local_year(t):
    return t.astimezone(seasons.TZ).year


def entry(spec, position):
    """One entry of the file as a Season. Raises ValueError naming the entry."""
    who = f"entry {spec.get('id') or position + 1}" if isinstance(spec, dict) else f"entry {position + 1}"
    if not isinstance(spec, dict):
        raise ValueError(f"{who}: an entry is an object, not {type(spec).__name__}")
    unknown = sorted(set(spec) - KEYS)
    if unknown:
        raise ValueError(f"{who}: unknown key(s) {', '.join(unknown)}")
    sid = spec.get("id")
    if not isinstance(sid, str) or not ID.match(sid):
        raise ValueError(f"{who}: id is lower-case letters, digits, '.', '_' and '-', not {sid!r}")
    district = spec.get("district")
    if not isinstance(district, str) or not district.strip():
        raise ValueError(f"{who}: district (its name) is required")
    canals = spec.get("canals")
    if (not isinstance(canals, list) or not canals
            or any(not isinstance(c, str) or not _key(c) for c in canals)):
        raise ValueError(f"{who}: canals is a list of canal names, not {canals!r}")
    branches = spec.get("branches", False)
    if not isinstance(branches, bool):
        raise ValueError(f"{who}: branches is true or false, not {branches!r}")
    at = {}
    for key in ("on", "off"):
        given = spec.get(key)
        if given is None:
            at[key] = None
            continue
        if not isinstance(given, str):
            raise ValueError(f"{who}: {key} is a date as text ('YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM'), not {given!r}")
        try:
            at[key] = seasons.moment(given)        # a date: that day's start in Boise; a time as given
        except ValueError as err:
            raise ValueError(f"{who}: {key}: {err}") from None
    if at["on"] is None and at["off"] is None:
        raise ValueError(f"{who}: give on, off or both")
    years = {_local_year(t) for t in at.values() if t is not None}
    if len(years) > 1:
        raise ValueError(f"{who}: on and off fall in different years; one entry is one season")
    if at["on"] is not None and at["off"] is not None and at["off"] <= at["on"]:
        raise ValueError(f"{who}: off ({spec['off']}) isn't after on ({spec['on']})")
    words = spec.get("text")
    if words is not None and (not isinstance(words, str) or len(words) > TEXT_MAX):
        raise ValueError(f"{who}: text is the district's words, at most {TEXT_MAX} characters")
    source = spec.get("source")
    if not isinstance(source, str) or not URL.match(source):
        raise ValueError(f"{who}: source is the page's URL (http or https), not {source!r}")
    read = spec.get("read")
    if not isinstance(read, str) or not DAY.match(read):
        raise ValueError(f"{who}: read is the day the page was read, YYYY-MM-DD, not {read!r}")
    try:
        read_on = date.fromisoformat(read)
    except ValueError:
        raise ValueError(f"{who}: read is not a date: {read!r}") from None
    republish = spec.get("republish", "yes")
    if republish not in manifest.REPUBLISH:
        raise ValueError(f"{who}: republish is one of {', '.join(manifest.REPUBLISH)}, not {republish!r}")
    return Season(id=sid, position=position, district=district.strip(), canals=tuple(c.strip() for c in canals),
                  branches=branches, season=years.pop(), on_at=at["on"], off_at=at["off"],
                  on_given=spec.get("on"), off_given=spec.get("off"), words=words, source=source, read_on=read_on,
                  republish=republish)


def parse(data):
    """The file's entries as Seasons, in order. Raises ValueError."""
    if not isinstance(data, dict) or not isinstance(data.get("seasons"), list):
        raise ValueError('the file is an object with a "seasons" list')
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise ValueError(f"unknown key(s) at the top: {', '.join(unknown)}")
    out = [entry(spec, i) for i, spec in enumerate(data["seasons"])]
    seen = set()
    for s in out:
        if s.id in seen:
            raise ValueError(f"entry {s.id}: the id is used twice")
        seen.add(s.id)
    return out


def read_file(path=FILE):
    """(Seasons, the file's sha256)."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValueError(f"{path}: not JSON: {err}") from None
    try:
        return parse(data), hashlib.sha256(raw).hexdigest()
    except ValueError as err:
        raise ValueError(f"{path}: {err}") from None


def _key(name):
    return rules.name_key(name)


def from_row(row):
    """A Season from a water.canal_date row (select COLUMNS)."""
    (sid, position, district, canals, branches, season, on_at, off_at, on_given, off_given, words, source, read_on,
     republish) = row
    utc = (lambda t: t.astimezone(timezone.utc) if t is not None else None)
    return Season(id=sid, position=position, district=district, canals=tuple(canals), branches=branches,
                  season=season, on_at=utc(on_at), off_at=utc(off_at), on_given=on_given, off_given=off_given,
                  words=words, source=source, read_on=read_on, republish=republish)


COLUMNS = ("entry_id, position, district, canals, branches, season, on_at, off_at, on_given, off_given, words, source, "
           "read_on, republish")


def loaded(conn):
    """The Seasons in water.canal_date, in the file's order."""
    return [from_row(r) for r in conn.execute(f"select {COLUMNS} from {TABLE} order by position").fetchall()]


def last_load(conn):
    """(sha256, loaded_at) of the last canal-dates-load, or None."""
    return conn.execute("""select sha256, loaded_at from water.load where source = %s
                           order by loaded_at desc, id desc limit 1""", (SOURCE["name"],)).fetchone()


def unmatched(conn, entries):
    """The names entries give that match no canal of the current build: [(entry id, name)]."""
    known = {_key(n) for (n,) in conn.execute("select name from water.canal").fetchall()}
    return [(s.id, n) for s in entries for n in s.canals if _key(n) not in known]


def store(conn, entries, path, digest):
    """Replace water.canal_date with entries (in the caller's transaction) and record the load. Returns stats."""
    from ingest import db
    db.ensure_source(conn, SOURCE)
    missing = unmatched(conn, entries)
    counts = {"entries": len(entries), "names": sum(len(s.canals) for s in entries),
              "names matching no canal": len(missing)}
    load_id = conn.execute(
        "insert into water.load (source, file, sha256, counts) values (%s, %s, %s, %s::jsonb) returning id",
        (SOURCE["name"], os.path.basename(path), digest,
         json.dumps({**counts, "unmatched": [f"{i}: {n}" for i, n in missing]}))).fetchone()[0]
    conn.execute(f"delete from {TABLE}")
    for s in entries:
        conn.execute(
            f"""insert into {TABLE} (entry_id, position, district, canals, branches, season, on_at, off_at, on_given,
                                     off_given, words, source, read_on, republish, load_id)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (s.id, s.position, s.district, list(s.canals), s.branches, s.season, s.on_at, s.off_at, s.on_given,
             s.off_given, s.words, s.source, s.read_on, s.republish, load_id))
    return counts, missing


def ready(conn):
    return conn.execute("select to_regclass('water.canal_date') is not null").fetchone()[0]


def main(argv=None):
    """`python3 -m ingest canal-dates-load` (registered in ../../plugin.json)."""
    ap = argparse.ArgumentParser(prog="python3 -m ingest canal-dates-load", description=__doc__.splitlines()[0])
    ap.add_argument("--file", default=FILE, help="the dates file (default: the repository's canal_dates.json)")
    ap.add_argument("--dry-run", action="store_true", help="check and report, then roll back")
    args = ap.parse_args(argv)
    try:
        entries, digest = read_file(args.file)
    except (OSError, ValueError) as err:
        sys.exit(f"canal-dates-load: {err}")
    from ingest import db
    from .. import season
    with db.connect() as conn:
        if not ready(conn):
            sys.exit("canal-dates-load: water 0002 isn't applied (python3 db/migrate.py)")
        counts, missing = store(conn, entries, args.file, digest)
        print("canal-dates-load: " + ", ".join(f"{k} {v}" for k, v in counts.items()), flush=True)
        for sid, name in missing:
            print(f"canal-dates-load: entry {sid}: no canal named {name!r} in the current water build", flush=True)
        if args.dry_run:
            conn.rollback()
            print("(dry run: nothing written)", flush=True)
            return 0
        conn.commit()
        stats = season.run(conn)
        print("canal_season: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0
