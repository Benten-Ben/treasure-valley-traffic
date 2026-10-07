"""What the trails plugin's two sources share: the ring they're cut to, polite reads of the
City of Boise's ArcGIS Online layers, the snapshot guard and the edit-date gate.

Both layers live on services1.arcgis.com, whose robots.txt answers 403 (no rules under
RFC 9309; re-checked through ingest/http.py on Oct 7, 2026). Requests to that host are
spaced at least PACE_S apart (http.PACE_S), on top of arcgis.fetch_layer's own pause, so
the metadata check and the reads after it never come back to back. Reads ask for gzip.

The gate keeps its state in core's ops.layer_signature (migration 0012, the table the
COMPASS reader uses to skip unchanged layers): one row per source with the layer's edit
dates and a digest of its fields. No new tables.
"""

import hashlib
import json
import time

from ingest import arcgis, http

HOST = "services1.arcgis.com"
PACE_S = 2.0
http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), PACE_S)

# The regional ring (docs/DECISIONS.md, "How far the study area reaches"; the trails and
# cycling catalogs use the same one): west, south, east, north in degrees. Trails context
# is cut to the ring; both layers lie well inside the valley box anyway.
RING = (-117.30, 42.90, -115.60, 44.30)

SNAPSHOT_MIN_SHARE = 0.5     # as ingest/db.py: a snapshot under half of what's current is refused

# Staff names, never stored from either layer: ArcGIS Online's editor tracking (Creator, Editor),
# ArcGIS Enterprise's (created_user, last_edited_user) and R2R's own Editor field. Listed for both
# layers, so turning editor tracking on later doesn't start storing who edited a row.
STAFF_FIELDS = {"creator", "editor", "created_user", "last_edited_user"}


def get(url):
    """http.get for these layers: robots.txt, pacing and the edit guard (ingest/http.py), gzip."""
    return http.get(url, timeout=180, compressed=True)


# --- the ring ---------------------------------------------------------------------

def bbox(geom):
    """(west, south, east, north) of a GeoJSON geometry, or None if it has no coordinates."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c, (list, tuple)) and len(c) >= 2 and all(isinstance(v, (int, float)) for v in c[:2]):
            xs.append(float(c[0]))
            ys.append(float(c[1]))
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)

    walk((geom or {}).get("coordinates"))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def in_ring(geom, ring=RING):
    """True if the geometry's extent touches the ring (as the server's envelope test would).
    A row without a geometry can't be placed, so it's kept: both layers are the City's own."""
    box = bbox(geom)
    if box is None:
        return True
    w, s, e, n = ring
    return box[0] <= e and box[2] >= w and box[1] <= n and box[3] >= s


# --- reading ----------------------------------------------------------------------

def parse_json(body, url):
    data = json.loads(body)
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(f"ArcGIS error from {url}: {data['error']}")
    return data


def describe(url, label, get=get, sleep=time.sleep):
    """A layer's description (?f=json), retried like arcgis.fetch_layer's requests.
    Returns (http status, description, robots decision, bytes)."""
    status, body, decision, data = arcgis.get_with_retries(url + "?f=json", label, get, sleep=sleep,
                                                           parse=lambda b: parse_json(b, url))
    return status, data, decision, len(body)


def missing_fields(meta, required):
    """Required fields the layer no longer has (a renamed field would otherwise read as blanks)."""
    have = {f.get("name") for f in meta.get("fields") or []}
    return sorted(set(required) - have)


# --- the snapshot guard -------------------------------------------------------------

def refuse(n, current, floor=0):
    """True if a snapshot of n rows mustn't be taken as complete, given `current` rows we hold.
    A layer that holds fewer than `floor` rows may shrink or empty (two closures ending is
    normal); a larger one is refused when empty or under half of what's current."""
    if current < floor:
        return False
    return n == 0 or n < SNAPSHOT_MIN_SHARE * current


def current_records(conn, source):
    return conn.execute("select count(distinct source_id) from raw.record where source = %s and removed_at is null",
                        (source,)).fetchone()[0]


def check_snapshot(conn, source, n, label, floor=0):
    """db.check_snapshot's rule against raw.record: raise (the fetch fails, nothing is retired)
    rather than take a suspiciously small snapshot as complete."""
    current = current_records(conn, source)
    if refuse(n, current, floor):
        raise RuntimeError(f"{label}: only {n} records against {current} current; not taken as a full snapshot")


def heartbeat(conn, source, seen_at):
    """An unchanged layer: every current version was seen again (as the WZDx stream does)."""
    return conn.execute("update raw.record set last_seen = %s where source = %s and removed_at is null",
                        (seen_at, source)).rowcount


# --- the edit-date gate ---------------------------------------------------------------

def signature(meta, domains=()):
    """What decides whether a layer changed: its edit dates (editingInfo), a digest of its
    fields, and the coded values of the named fields' domains (a new condition label is a
    schema change worth a read)."""
    edit = meta.get("editingInfo") or {}
    fields = [(f.get("name"), f.get("type")) for f in meta.get("fields") or []]
    sig = {"last_edit": edit.get("lastEditDate"), "data_last_edit": edit.get("dataLastEditDate"),
           "schema_last_edit": edit.get("schemaLastEditDate"),
           "fields": hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()[:16]}
    for name in domains:
        f = next((f for f in meta.get("fields") or [] if f.get("name") == name), {})
        sig[f"{name} values"] = [c.get("code") for c in ((f.get("domain") or {}).get("codedValues") or [])]
    return sig


def unchanged(sig, stored, now, max_age):
    """True if the layer can be skipped: it reports an edit date, the signature matches the one
    saved at the last full read, and that read is younger than max_age (a timedelta)."""
    if sig.get("last_edit") is None or stored is None:
        return False
    saved, read_at = stored
    return saved == sig and read_at is not None and now - read_at < max_age


def stored_signature(conn, source):
    """(signature, read_at) from ops.layer_signature, or None."""
    return conn.execute("select signature, read_at from ops.layer_signature where source = %s",
                        (source,)).fetchone()


def save_signature(conn, source, sig, read):
    """As ingest/compass_layer.py: checked_at always moves; read_at only after a full read."""
    conn.execute(
        """insert into ops.layer_signature (source, signature, read_at, checked_at) values (%s, %s, now(), now())
           on conflict (source) do update set signature = excluded.signature, checked_at = excluded.checked_at,
             read_at = case when %s then excluded.read_at else ops.layer_signature.read_at end""",
        (source, json.dumps(sig), read))
