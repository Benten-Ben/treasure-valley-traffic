"""Read a GeoPackage with the standard library: its tables, and each row with its geometry as plain WKB.

A GeoPackage is a SQLite database. A geometry column holds GeoPackageBinary: a small header (the magic 'GP', a
version, a flags byte, the SRS id and an optional envelope) followed by ordinary WKB, which PostGIS reads with
ST_GeomFromWKB. Only that header is parsed here; the WKB goes to the database as it is (OGC GeoPackage 1.3, §2.1.3).

    from plugins.water.ingest import gpkg
    with gpkg.open_ro(path) as g:
        gpkg.feature_tables(g)                      # {'flowline': ('geom', 'MULTILINESTRING', 4269), ...}
        for row in gpkg.rows(g, "flowline"):        # dicts, the geometry as WKB bytes (None when empty)
            ...

The file is opened read-only and immutable, so reading never writes to it.
"""

import contextlib
import os
import re
import sqlite3
import struct
import urllib.parse

MAGIC = b"GP"
# Envelope sizes by the flags' bits 1-3: none, xy, xyz, xym, xyzm.
ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class GpkgError(ValueError):
    pass


@contextlib.contextmanager
def open_ro(path):
    """A read-only connection to the GeoPackage at path."""
    if not os.path.isfile(path):
        raise GpkgError(f"{path}: no such file")
    uri = "file:" + urllib.parse.quote(os.path.abspath(path)) + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        try:
            conn.execute("select count(*) from gpkg_contents").fetchone()
        except sqlite3.DatabaseError as err:
            raise GpkgError(f"{path}: not a GeoPackage ({err})") from None
        yield conn
    finally:
        conn.close()


def _name(name):
    if not isinstance(name, str) or not _NAME.match(name):
        raise GpkgError(f"not a plain table or column name: {name!r}")
    return name


def tables(conn):
    """{table: data_type} from gpkg_contents ('features' or 'attributes')."""
    return dict(conn.execute("select table_name, data_type from gpkg_contents order by table_name").fetchall())


def feature_tables(conn):
    """{table: (geometry column, geometry type name, srs_id)} from gpkg_geometry_columns."""
    rows = conn.execute("select table_name, column_name, geometry_type_name, srs_id from gpkg_geometry_columns")
    return {t: (c, g, s) for t, c, g, s in rows.fetchall()}


def columns(conn, table):
    return [r[1] for r in conn.execute(f'pragma table_info("{_name(table)}")').fetchall()]


def wkb(blob):
    """The WKB inside a GeoPackageBinary blob, or None for an empty geometry. Raises GpkgError for anything else."""
    if blob is None:
        return None
    blob = bytes(blob)
    if len(blob) < 8 or blob[:2] != MAGIC:
        raise GpkgError("not a GeoPackage geometry (no 'GP' magic)")
    flags = blob[3]
    if flags & 0x20:
        raise GpkgError("an extended GeoPackage geometry type, which we don't read")
    envelope = (flags >> 1) & 0x07
    if envelope not in ENVELOPE_BYTES:
        raise GpkgError(f"an invalid envelope code {envelope}")
    start = 8 + ENVELOPE_BYTES[envelope]
    if flags & 0x10:                      # the empty-geometry flag
        return None
    body = blob[start:]
    if len(body) < 5 or body[0] not in (0, 1):
        raise GpkgError("the geometry's WKB is cut short or has no byte-order mark")
    return body


def srs_id(blob):
    """The SRS id in a GeoPackageBinary blob's header."""
    blob = bytes(blob)
    if len(blob) < 8 or blob[:2] != MAGIC:
        raise GpkgError("not a GeoPackage geometry (no 'GP' magic)")
    return struct.unpack("<i" if blob[3] & 0x01 else ">i", blob[4:8])[0]


def rows(conn, table, wanted=None):
    """Each row of a table as a dict. A feature table's geometry column holds plain WKB bytes (None when empty).
    wanted: the columns to read (default every one); a missing one raises GpkgError."""
    table = _name(table)
    have = columns(conn, table)
    if not have:
        raise GpkgError(f"no table {table}")
    names = list(wanted) if wanted else have
    if missing := [c for c in names if c not in have]:
        raise GpkgError(f"{table} has no column {', '.join(missing)}")
    geometry = feature_tables(conn).get(table, (None,))[0]
    cur = conn.execute(f"select {', '.join(chr(34) + _name(c) + chr(34) for c in names)} from \"{table}\"")
    for values in cur:
        row = dict(zip(names, values))
        if geometry in row:
            row[geometry] = wkb(row[geometry])
        yield row
