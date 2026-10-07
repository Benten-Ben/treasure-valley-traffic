"""Aircraft over the regional ring, from adsb.lol's open API (owner approved Oct 7, 2026).

adsb.lol's data is ODbL 1.0: credit "© adsb.lol contributors", and any derived
database we publish stays ODbL. `python3 -m ingest stream adsblol` asks once
every 10 s for a 60 nm circle around 43.6, -116.45 (it covers every corner of
the regional ring) through ingest/http.py (robots.txt, our User-Agent, gzip),
and then:

1. keeps aircraft inside the regional ring box whose position is at most 60 s
   old, each cleaned into one record (clean());
2. stores aircraft flagged PIA or LADD (adsb.lol's dbFlags 4 and 8) without
   identity: no hex, registration or callsign, and a key that changes every UTC
   day ('anon:' + 12 hex of sha256(salt + hex + date)), so a day's track is
   continuous but days can't be linked. Type and category stay. The salt is
   TVT_AIRCRAFT_SALT (deploy/.env on the server); without it, a random one per
   start (logged);
3. keeps a record only when the aircraft has a new position since its last one
   (Tracker);
4. appends those records to $TVT_ARCHIVE/aircraft/<UTC date>.ndjson.gz, then
   writes them to obs.aircraft_position, and each identified aircraft's latest
   type, category, callsign and registration to core.aircraft_seen. The raw
   response is never archived: it carries LADD identities.

The archive is written before the database, so a database outage loses
nothing: `python3 -m ingest backfill adsblol $TVT_ARCHIVE/aircraft` reloads it.

Any failed request (4xx, 429, 5xx, a network error, an unreadable robots.txt or
body) backs off: 20 s, 40, 80, 160, then every 5 minutes until one works, or
longer when the server sends Retry-After (up to an hour). Each failure is
logged, and recorded in ops.fetch when the database is reachable.
"""

import gzip
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import time
import traceback
import urllib.error
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from ingest import db, http

URL = "https://api.adsb.lol/v2/point/43.6/-116.45/60"
POLL_S = 10                  # one request every 10 s (owner, Oct 7); never faster
MAX_BACKOFF_S = 300          # failed requests back off up to 5 minutes...
MAX_RETRY_AFTER_S = 3600     # ...or as long as the server's Retry-After asks, up to an hour
TIMEOUT_S = 20
MAX_AGE_S = 60               # positions older than this (seen_pos) are skipped
SAME_REPORT_S = 1.0          # the same position, give or take adsb.lol's rounding of seen_pos
FORGET_S = 600               # the tracker forgets aircraft not seen for 10 minutes
COMPACT_AFTER_S = 300        # a day's archive is compacted 5 minutes after it ends
BATCH = 2000                 # backfill: records per insert

WEST, SOUTH, EAST, NORTH = -117.30, 42.90, -115.60, 44.30     # the regional ring box
FLAG_MILITARY, FLAG_PIA, FLAG_LADD = 1, 4, 8                    # adsb.lol's dbFlags bits
SALT_ENV = "TVT_AIRCRAFT_SALT"

SOURCE = {
    "name": "adsblol",
    "title": "Aircraft positions over the regional ring (adsb.lol open API)",
    "url": URL,
    "access": "open",
    "schedule": None,          # a stream: `python3 -m ingest stream adsblol`
    "license": "ODbL 1.0",
    "credit": "© adsb.lol contributors",
    "notes": "Polled every 10 s; aircraft in the regional ring box; LADD- and PIA-flagged aircraft stored "
             "without identity; cleaned records archived by UTC day (never the raw response).",
}

HEX = re.compile(r"^~?[0-9a-f]{6}$")
KEY = re.compile(r"^(~?[0-9a-f]{6}|anon:[0-9a-f]{12})$")
CALLSIGN = re.compile(r"^[A-Z0-9]{1,8}$")
REGISTRATION = re.compile(r"^[A-Z0-9-]{1,10}$")
ICAO_TYPE = re.compile(r"^[A-Z0-9]{2,4}$")
CATEGORY = re.compile(r"^[A-D][0-7]$")
SQUAWK = re.compile(r"^[0-7]{4}$")
EMERGENCY = {"general", "lifeguard", "minfuel", "nordo", "unlawful", "downed", "reserved"}

# The columns of obs.aircraft_position, in order (lat and lon make geom).
COLUMNS = ("observed_at", "aircraft_key", "lat", "lon", "alt_baro_ft", "alt_geom_ft", "on_ground", "gs_kt",
           "track_deg", "true_heading_deg", "baro_rate_fpm", "geom_rate_fpm", "squawk", "emergency", "category",
           "icao_type", "callsign", "position_source", "extra")
# Kept in extra when present: position quality, the selected altitude, the speeds the aircraft reports.
EXTRA = ("nic", "nac_p", "nav_altitude_mcp", "ias", "tas", "mach")


# --- cleaning ---------------------------------------------------------------

def _num(v):
    """A finite number, or None (bools, strings and NaN aren't numbers here)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def _int(v):
    v = _num(v)
    return None if v is None else int(round(v))


def _round(v, digits=1):
    v = _num(v)
    return None if v is None else round(float(v), digits)


def _text(v, pattern, upper=True):
    if not isinstance(v, str):
        return None
    v = v.strip().upper() if upper else v.strip()
    return v if pattern.match(v) else None


def in_box(lon, lat):
    return WEST <= lon <= EAST and SOUTH <= lat <= NORTH


def anon_key(salt, hex_, day):
    """The key of an aircraft stored without identity: the same all UTC day, a new one the next."""
    return "anon:" + hashlib.sha256((salt + hex_ + day.isoformat()).encode()).hexdigest()[:12]


def is_private(ac):
    """Flagged PIA or LADD in adsb.lol's database: stored without identity."""
    flags = ac.get("dbFlags")
    return isinstance(flags, int) and not isinstance(flags, bool) and bool(flags & (FLAG_PIA | FLAG_LADD))


def position_source(ac):
    """'adsb', 'mlat', 'adsr' (rebroadcast UAT), 'tisb' or 'other': where this position came from."""
    for field, name in (("mlat", "mlat"), ("tisb", "tisb")):
        if "lat" in (ac.get(field) or []):
            return name
    kind = str(ac.get("type") or "").lower()
    if kind.startswith("adsb"):
        return "adsb"
    if kind == "mlat":
        return "mlat"
    if kind.startswith(("adsr", "uat")):
        return "adsr"
    if kind.startswith("tisb"):
        return "tisb"
    return "other"


def response_time(resp):
    """The response's `now` as a UTC datetime (milliseconds in the v2 API; seconds accepted too), or None."""
    now = _num(resp.get("now")) if isinstance(resp, dict) else None
    if now is None or now <= 0:
        return None
    return datetime.fromtimestamp(now / 1000 if now > 1e11 else now, timezone.utc)


def clean(ac, now, salt):
    """One aircraft of the response -> (record, None), or (None, why it was left out).

    now: the response's time. The record's keys are obs.aircraft_position's
    columns, plus "registration" for identified aircraft (for core.aircraft_seen).
    An aircraft flagged PIA or LADD keeps no hex, registration or callsign."""
    lat, lon = _num(ac.get("lat")), _num(ac.get("lon"))
    if lat is None or lon is None:
        return None, "no position"          # rr_lat/rr_lon are rough guesses from receivers: never used
    if not in_box(lon, lat):
        return None, "outside the box"
    seen_pos = _num(ac.get("seen_pos"))
    if seen_pos is None or seen_pos > MAX_AGE_S:
        return None, "stale"
    hex_ = str(ac.get("hex") or "").strip().lower()
    if not HEX.match(hex_):
        return None, "odd hex"
    observed_at = now - timedelta(milliseconds=round(max(seen_pos, 0) * 1000))
    private = is_private(ac)
    flags = ac.get("dbFlags") if isinstance(ac.get("dbFlags"), int) else 0

    alt_baro = ac.get("alt_baro")
    ground = alt_baro == "ground"
    extra = {"src": str(ac.get("type"))} if ac.get("type") else {}
    for k in EXTRA:
        v = _num(ac.get(k))
        if v is not None:
            extra[k] = v
    if flags & FLAG_MILITARY:
        extra["mil"] = True
    emergency = ac.get("emergency")
    rec = {
        "observed_at": observed_at,
        "aircraft_key": anon_key(salt, hex_, observed_at.date()) if private else hex_,
        "lat": float(lat), "lon": float(lon),
        "alt_baro_ft": None if ground else _int(alt_baro),
        "alt_geom_ft": _int(ac.get("alt_geom")),
        "on_ground": True if ground else (False if _num(alt_baro) is not None else None),
        "gs_kt": _round(ac.get("gs")),
        "track_deg": _round(ac.get("track"), 2),
        "true_heading_deg": _round(ac.get("true_heading"), 2),
        "baro_rate_fpm": _int(ac.get("baro_rate")),
        "geom_rate_fpm": _int(ac.get("geom_rate")),
        "squawk": _text(ac.get("squawk"), SQUAWK),
        "emergency": emergency if emergency in EMERGENCY else None,
        "category": _text(ac.get("category"), CATEGORY),
        "icao_type": _text(ac.get("t"), ICAO_TYPE),
        "callsign": None if private else _text(ac.get("flight"), CALLSIGN),
        "position_source": position_source(ac),
        "extra": extra or None,
    }
    if not private and not hex_.startswith("~"):
        rec["registration"] = _text(ac.get("r"), REGISTRATION)
    return rec, None


def clean_response(resp, salt, received_at=None):
    """-> (the response's time, [record], Counter of what was left out and why, {hex of flagged aircraft}).

    The flagged hexes are only for deleting rows from core.aircraft_seen; they
    are never written anywhere."""
    now = response_time(resp) or received_at or db.now()
    records, counts, flagged = [], Counter(), set()
    for ac in resp.get("ac") or []:
        if not isinstance(ac, dict):
            counts["odd"] += 1
            continue
        if is_private(ac):
            hex_ = str(ac.get("hex") or "").strip().lower()
            if re.match(r"^[0-9a-f]{6}$", hex_):
                flagged.add(hex_)
        rec, why = clean(ac, now, salt)
        if rec is None:
            counts[why] += 1
        else:
            records.append(rec)
    return now, records, counts, flagged


class Tracker:
    """Each aircraft's last kept position, so only new ones are stored.

    A position is new when its time is at least SAME_REPORT_S after the last
    one kept, or later with a different place. adsb.lol rounds seen_pos, so the
    same report polled twice can come back a few hundredths of a second apart."""

    def __init__(self):
        self.last = {}          # key: (observed_at, lat, lon)

    def seed(self, rows):
        for key, t, lat, lon in rows:
            if key not in self.last or t > self.last[key][0]:
                self.last[key] = (t, lat, lon)

    def fresh(self, records):
        out = []
        for r in sorted(records, key=lambda r: r["observed_at"]):
            key, t = r["aircraft_key"], r["observed_at"]
            prev = self.last.get(key)
            if prev:
                if t <= prev[0]:
                    continue
                if (t - prev[0]).total_seconds() < SAME_REPORT_S and (r["lat"], r["lon"]) == prev[1:]:
                    continue
            self.last[key] = (t, r["lat"], r["lon"])
            out.append(r)
        return out

    def forget_before(self, when):
        for key in [k for k, v in self.last.items() if v[0] < when]:
            del self.last[key]


# --- the archive -----------------------------------------------------------

def archive_path(root, day):
    return os.path.join(root, "aircraft", f"{day.isoformat()}.ndjson.gz")


def to_json(rec):
    out = {k: v for k, v in rec.items() if v is not None}
    out["observed_at"] = rec["observed_at"].astimezone(timezone.utc).isoformat(timespec="milliseconds") \
        .replace("+00:00", "Z")
    return json.dumps(out, separators=(",", ":"), sort_keys=True)


def from_json(line):
    d = json.loads(line)
    rec = {c: d.get(c) for c in COLUMNS}
    rec["observed_at"] = datetime.fromisoformat(d["observed_at"].replace("Z", "+00:00"))
    if "registration" in d:
        rec["registration"] = d["registration"]
    if not KEY.match(str(rec["aircraft_key"] or "")):
        raise ValueError(f"odd aircraft_key {rec['aircraft_key']!r}")
    if rec["aircraft_key"].startswith("anon:") and (rec["callsign"] or rec.get("registration")):
        raise ValueError("an anonymous record with an identity")
    return rec


def append_archive(root, records):
    """Append cleaned records to their UTC day's file, one gzip member per poll and day.
    Returns the days written."""
    by_day = defaultdict(list)
    for r in records:
        by_day[r["observed_at"].astimezone(timezone.utc).date()].append(to_json(r))
    for day, lines in by_day.items():
        path = archive_path(root, day)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "ab") as f:
            f.write(gzip.compress(("\n".join(lines) + "\n").encode()))
    return set(by_day)


def read_archive(path, out=print):
    """The records in one day's file. A file cut short (a crash mid-write) yields what's readable."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if line.strip():
                    try:
                        yield from_json(line)
                    except (ValueError, KeyError, TypeError) as err:
                        out(f"adsblol: {path} line {n} skipped: {err}")
    except (EOFError, OSError, zlib.error) as err:
        out(f"adsblol: {path} is cut short ({err}); kept what was readable")


def compact(path):
    """Rewrite a finished day's file as one gzip stream. Appending per poll makes a small
    stream per poll, which compresses about half as well. Leaves the file alone on any error."""
    tmp = path + ".tmp"
    try:
        with gzip.open(path, "rb") as src, gzip.open(tmp, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        os.replace(tmp, path)
        return True
    except (EOFError, OSError, zlib.error):
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


# --- the database ----------------------------------------------------------

INSERT = f"""insert into obs.aircraft_position ({", ".join(c for c in COLUMNS if c not in ("lat", "lon"))}, geom)
   values ({", ".join(f"%({c})s" + ("::jsonb" if c == "extra" else "")
                      for c in COLUMNS if c not in ("lat", "lon"))},
           st_setsrid(st_makepoint(%(lon)s, %(lat)s), 4326))
   on conflict (aircraft_key, observed_at) do nothing"""

UPSERT_SEEN = """insert into core.aircraft_seen as s (hex, icao_type, category, callsign, registration, military,
                   first_seen, last_seen)
   values (%(hex)s, %(icao_type)s, %(category)s, %(callsign)s, %(registration)s, %(military)s,
           %(first_seen)s, %(last_seen)s)
   on conflict (hex) do update set
     icao_type = case when excluded.last_seen >= s.last_seen then coalesce(excluded.icao_type, s.icao_type)
                      else coalesce(s.icao_type, excluded.icao_type) end,
     category = case when excluded.last_seen >= s.last_seen then coalesce(excluded.category, s.category)
                     else coalesce(s.category, excluded.category) end,
     callsign = case when excluded.last_seen >= s.last_seen then coalesce(excluded.callsign, s.callsign)
                     else coalesce(s.callsign, excluded.callsign) end,
     registration = case when excluded.last_seen >= s.last_seen then coalesce(excluded.registration, s.registration)
                         else coalesce(s.registration, excluded.registration) end,
     military = case when excluded.last_seen >= s.last_seen then excluded.military else s.military end,
     first_seen = least(s.first_seen, excluded.first_seen),
     last_seen = greatest(s.last_seen, excluded.last_seen)"""


def seen_rows(records):
    """One core.aircraft_seen row per identified aircraft in records (its latest values)."""
    out = {}
    for r in sorted(records, key=lambda r: r["observed_at"]):
        hex_ = r["aircraft_key"]
        if hex_.startswith(("anon:", "~")):
            continue
        row = out.setdefault(hex_, {"hex": hex_, "icao_type": None, "category": None, "callsign": None,
                                    "registration": None, "first_seen": r["observed_at"]})
        for k in ("icao_type", "category", "callsign", "registration"):
            row[k] = r.get(k) or row[k]
        row["military"] = bool((r.get("extra") or {}).get("mil"))
        row["last_seen"] = r["observed_at"]
    return list(out.values())


def store(conn, records, flagged=()):
    """Insert new positions (one already stored is skipped), update core.aircraft_seen, and delete
    the rows of aircraft now flagged PIA or LADD. Returns (positions inserted, aircraft_seen rows deleted)."""
    inserted = deleted = 0
    if records:
        rows = [{**r, "extra": json.dumps(r["extra"]) if r.get("extra") else None} for r in records]
        with conn.cursor() as cur:
            cur.executemany(INSERT, rows)
            inserted = max(cur.rowcount, 0)
            seen = seen_rows(records)
            if seen:
                cur.executemany(UPSERT_SEEN, seen)
    if flagged:
        deleted = conn.execute("delete from core.aircraft_seen where hex = any(%s)", (sorted(flagged),)).rowcount
    return inserted, deleted


def recent(conn, minutes=5):
    """(key, observed_at, lat, lon) of each aircraft's latest stored position in the last few minutes."""
    return conn.execute(
        """select distinct on (aircraft_key) aircraft_key, observed_at, st_y(geom), st_x(geom)
           from obs.aircraft_position where observed_at > now() - make_interval(mins => %s)
           order by aircraft_key, observed_at desc""", (minutes,)).fetchall()


# --- polling ----------------------------------------------------------------

def backoff_s(failures, retry_after=None):
    """Seconds to wait after `failures` failed requests in a row: 20, 40, 80, 160, then 300;
    longer if the server asked (Retry-After), up to an hour."""
    wait = min(MAX_BACKOFF_S, POLL_S * 2 ** max(failures, 1))
    if retry_after:
        wait = max(wait, min(retry_after, MAX_RETRY_AFTER_S))
    return wait


def retry_after_s(err):
    if isinstance(err, urllib.error.HTTPError) and err.headers is not None:
        try:
            return max(0, int(str(err.headers.get("Retry-After", "")).strip()))
        except ValueError:
            return None
    return None


def describe(err):
    if isinstance(err, urllib.error.HTTPError):
        return f"HTTP {err.code}"
    if isinstance(err, urllib.error.URLError):
        return f"network error: {err.reason}"
    return f"{type(err).__name__}: {err}"


def load_salt(env=None, out=print):
    salt = (os.environ if env is None else env).get(SALT_ENV, "").strip()
    if salt:
        return salt
    out(f"adsblol: WARNING: {SALT_ENV} isn't set, so anonymous aircraft are keyed with a random salt for this "
        "run only (their keys change at a restart). Set it in deploy/.env on the server.")
    return secrets.token_hex(32)


class Poller:
    """One poll at a time: poll() fetches, cleans, archives and stores, and returns the
    seconds to wait before the next one. Never raises."""

    def __init__(self, root, salt, every=POLL_S, get=http.get, connect=db.connect, clock=time.time,
                 out=print):
        self.root, self.salt, self.every = root, salt, max(every, POLL_S)
        self.get, self.connect, self.clock, self.out = get, connect, clock, out
        self.tracker = Tracker()
        self.conn = None
        self.seeded = False
        self.failures = 0
        self.open_days = set()      # archive days written by this process, compacted once they're over
        self.stats = Counter()
        self.keys = set()
        self.report_at = clock() + 3600
        self.robots_at = clock() + 86400

    def connection(self):
        if self.conn is None:
            self.conn = self.connect()
            db.ensure_source(self.conn, SOURCE)
            self.conn.commit()
            if not self.seeded:
                self.tracker.seed(recent(self.conn))
                self.conn.commit()
                self.seeded = True
        return self.conn

    def drop_connection(self):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        self.conn = None

    def log_failure(self, err, status=None):
        """Record a failed request in ops.fetch, if the database is reachable."""
        try:
            with db.Fetch(self.connection(), SOURCE["name"]) as f:
                f.http_status = status
                raise err
        except Exception as e:
            if e is not err:
                self.drop_connection()

    def poll(self):
        started = self.clock()
        received_at = db.now()
        try:
            status, data, decision = self.get(URL, timeout=TIMEOUT_S, compressed=True)
            resp = json.loads(data)
            if not isinstance(resp, dict) or not isinstance(resp.get("ac") or [], list):
                raise ValueError("not an adsb.lol response")
        except Exception as err:
            self.failures += 1
            self.stats["failed"] += 1
            wait = backoff_s(self.failures, retry_after_s(err))
            self.out(f"adsblol: request failed ({describe(err)}); {self.failures} in a row, "
                     f"next try in {wait:.0f} s")
            self.log_failure(err, getattr(err, "code", None))
            return wait
        if self.failures:
            self.out(f"adsblol: answering again after {self.failures} failed requests")
        self.failures = 0
        self.stats["polls"] += 1

        now, records, skipped, flagged = clean_response(resp, self.salt, received_at)
        fresh = self.tracker.fresh(records)
        self.tracker.forget_before(now - timedelta(seconds=FORGET_S))
        self.stats["in box"] = max(self.stats["in box"], len(records))
        self.stats["new positions"] += len(fresh)
        self.stats.update({f"skipped ({k})": v for k, v in skipped.items()})
        self.keys.update(r["aircraft_key"] for r in fresh)

        try:
            self.open_days |= append_archive(self.root, fresh)
        except Exception:
            self.out(f"adsblol: archive write failed:\n{traceback.format_exc()}")
        try:
            conn = self.connection()
            with db.Fetch(conn, SOURCE["name"]) as f:
                f.http_status, f.robots, f.bytes = status, decision, len(data)
                inserted, deleted = store(conn, fresh, flagged)
                f.records = inserted
            if deleted:
                self.out(f"adsblol: {deleted} aircraft now flagged LADD or PIA removed from core.aircraft_seen "
                         "(earlier positions keep their hex)")
        except Exception:
            self.out(f"adsblol: database write failed (records archived; backfill later):\n{traceback.format_exc()}")
            self.drop_connection()

        self.compact_finished_days(now)
        self.housekeeping()
        return max(1.0, self.every - (self.clock() - started))

    def compact_finished_days(self, now):
        for day in sorted(self.open_days):
            end = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(days=1)
            if now >= end + timedelta(seconds=COMPACT_AFTER_S):
                self.open_days.discard(day)
                if not compact(archive_path(self.root, day)):
                    self.out(f"adsblol: couldn't compact {archive_path(self.root, day)} (left as written)")

    def housekeeping(self):
        if self.clock() >= self.report_at:
            anonymous = sum(1 for k in self.keys if k.startswith("anon:"))
            self.out(f"adsblol: last hour: {self.stats['polls']} polls, {self.stats['failed']} failed; "
                     f"{len(self.keys)} aircraft ({anonymous} anonymous), {self.stats['new positions']} new positions, "
                     f"at most {self.stats['in box']} in the box at once"
                     + "".join(f"; {k} {v}" for k, v in sorted(self.stats.items()) if k.startswith("skipped")))
            self.stats, self.keys = Counter(), set()
            self.report_at = self.clock() + 3600
        if self.clock() >= self.robots_at:
            http.forget_robots()
            self.robots_at = self.clock() + 86400


def stream(every=POLL_S):
    """Poll forever, once every 10 s (never faster), backing off on errors. Never raises."""
    root = os.environ.get("TVT_ARCHIVE")
    if not root:
        sys.exit("set TVT_ARCHIVE: the cleaned records are archived there")
    if every < POLL_S:
        print(f"adsblol: polling every {POLL_S} s, not {every}: that's the rate agreed for this source", flush=True)
    poller = Poller(root, load_salt(out=lambda s: print(s, flush=True)), every,
                    out=lambda s: print(s, flush=True))
    print(f"adsblol: polling {URL} every {poller.every} s; aircraft in the box "
          f"{WEST}, {SOUTH}, {EAST}, {NORTH}; cleaned records archived in {root}/aircraft", flush=True)
    while True:
        time.sleep(poller.poll())


def backfill(conn, root):
    """Load every archived day under root (oldest first). Positions already stored are skipped,
    so it's safe to run more than once."""
    db.ensure_source(conn, SOURCE)
    files = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs if f.endswith(".ndjson.gz"))
    records = inserted = 0
    for path in files:
        batch = []
        for rec in read_archive(path):
            batch.append(rec)
            if len(batch) >= BATCH:
                inserted += store(conn, batch)[0]
                records += len(batch)
                batch = []
        if batch:
            inserted += store(conn, batch)[0]
            records += len(batch)
        conn.commit()
        print(f"  {os.path.basename(path)}: {records} records so far, {inserted} new positions", flush=True)
    return {"files": len(files), "records": records, "new positions": inserted}
