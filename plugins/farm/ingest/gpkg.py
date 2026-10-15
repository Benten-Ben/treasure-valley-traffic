"""A GeoPackage's feature table, read with the standard library (sqlite3). Ingest stays standard library, so farm's
loader reads CSB's GeoPackage itself and hands each geometry's WKB to PostGIS.

A GeoPackage is a SQLite database (OGC 12-128r19). Each geometry is a "GeoPackageBinary" blob: a header ("GP", a
version, a flags byte, the srs_id and an optional envelope) followed by standard WKB. strip_header() checks the header
and returns the WKB; extended (non-standard) geometry blobs are refused.

    with gpkg.open("csb_mapbox.gpkg") as gp:
        layer = gp.layer()                       # the only feature table (or by name)
        layer.epsg                               # 5070
        for fid, attrs, wkb in layer.features(["CSBID", "CDL2025"]):
            ...

The file is opened read-only and immutable (no locks, no journal), so it reads from a read-only mount.
"""

import os
import pathlib
import re
import sqlite3
import struct
from dataclasses import dataclass

GPKG_APPLICATION_ID = 0x47504B47          # 'GPKG'
_ENVELOPE_DOUBLES = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}   # envelope indicator -> doubles in the header's envelope
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class GpkgError(ValueError):
    pass


def strip_header(blob):
    """(srs_id, wkb, empty) from a GeoPackageBinary blob. Raises GpkgError for anything that isn't one."""
    if blob is None:
        return None, None, True
    b = bytes(blob)
    if len(b) < 8 or b[:2] != b"GP":
        raise GpkgError("not a GeoPackage geometry (no 'GP' magic)")
    version, flags = b[2], b[3]
    if version != 0:
        raise GpkgError(f"GeoPackage geometry version {version} isn't 0 (version 1)")
    if flags & 0b00100000:
        raise GpkgError("an extended GeoPackage geometry (not standard WKB)")
    order = "<" if flags & 1 else ">"
    envelope = (flags >> 1) & 0b111
    if envelope not in _ENVELOPE_DOUBLES:
        raise GpkgError(f"bad envelope indicator {envelope}")
    empty = bool(flags & 0b00010000)
    (srs_id,) = struct.unpack(order + "i", b[4:8])
    start = 8 + 8 * _ENVELOPE_DOUBLES[envelope]
    if len(b) <= start:
        raise GpkgError("a GeoPackage geometry with no WKB after its header")
    wkb = b[start:]
    if wkb[0] not in (0, 1):
        raise GpkgError("the WKB after the header has no byte-order mark")
    return srs_id, wkb, empty


@dataclass
class Layer:
    gp: "GeoPackage"
    name: str
    geometry_column: str
    geometry_type: str
    srs_id: int
    organization: str
    organization_id: int
    fid_column: str
    columns: list            # [(name, declared type)], the geometry and fid columns left out

    @property
    def epsg(self):
        """The EPSG code of the layer's CRS, or None when it isn't an EPSG one."""
        return self.organization_id if self.organization.upper() == "EPSG" else None

    def count(self):
        return self.gp.db.execute(f'select count(*) from "{self.name}"').fetchone()[0]

    def features(self, columns=None):
        """Yield (fid, {column: value}, wkb or None) in fid order. columns: the attributes to read (default all)."""
        names = [c for c, _ in self.columns] if columns is None else list(columns)
        have = {c for c, _ in self.columns}
        missing = [c for c in names if c not in have]
        if missing:
            raise GpkgError(f"layer {self.name} has no column {', '.join(missing)}")
        cols = ", ".join(f'"{c}"' for c in [self.fid_column, self.geometry_column] + names)
        for row in self.gp.db.execute(f'select {cols} from "{self.name}" order by "{self.fid_column}"'):
            srs_id, wkb, empty = strip_header(row[1])
            if srs_id is not None and srs_id != self.srs_id and srs_id != 0:
                raise GpkgError(f"feature {row[0]}: geometry in srs {srs_id}, the layer's is {self.srs_id}")
            yield row[0], dict(zip(names, row[2:])), (None if empty else wkb)


class GeoPackage:
    def __init__(self, path):
        if not os.path.isfile(path):
            raise GpkgError(f"no file {path}")
        self.path = path
        uri = pathlib.Path(os.path.abspath(path)).as_uri() + "?mode=ro&immutable=1"
        try:
            self.db = sqlite3.connect(uri, uri=True)
        except sqlite3.DatabaseError as err:
            raise GpkgError(f"{path}: can't open it as SQLite ({err})") from None
        try:
            app = self.db.execute("pragma application_id").fetchone()[0]
            tables = {r[0] for r in self.db.execute("select name from sqlite_master where type in ('table', 'view')")}
        except sqlite3.DatabaseError as err:
            self.db.close()
            raise GpkgError(f"{path}: not a SQLite database ({err})") from None
        if not {"gpkg_contents", "gpkg_geometry_columns", "gpkg_spatial_ref_sys"} <= tables:
            self.db.close()
            raise GpkgError(f"{path}: not a GeoPackage (no gpkg_contents, gpkg_geometry_columns or "
                            "gpkg_spatial_ref_sys)")
        self.application_id = app

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def layers(self):
        """The feature tables' names."""
        return [r[0] for r in self.db.execute(
            "select table_name from gpkg_contents where data_type = 'features' order by table_name")]

    def layer(self, name=None):
        names = self.layers()
        if name is None:
            if len(names) != 1:
                raise GpkgError(f"{self.path} has {len(names)} feature tables ({', '.join(names)}): name one")
            name = names[0]
        if name not in names:
            raise GpkgError(f"{self.path} has no feature table {name!r} ({', '.join(names)})")
        if not _IDENT.match(name):
            raise GpkgError(f"feature table name {name!r} isn't a plain identifier")
        row = self.db.execute(
            """select g.column_name, g.geometry_type_name, g.srs_id, s.organization, s.organization_coordsys_id
               from gpkg_geometry_columns g join gpkg_spatial_ref_sys s on s.srs_id = g.srs_id
               where g.table_name = ?""", (name,)).fetchone()
        if row is None:
            raise GpkgError(f"{name}: no geometry column registered")
        geom_col, gtype, srs_id, org, org_id = row
        info = self.db.execute(f'pragma table_info("{name}")').fetchall()
        pks = [r[1] for r in info if r[5]]
        if len(pks) != 1:
            raise GpkgError(f"{name}: no single integer primary key")
        cols = [(r[1], r[2]) for r in info if r[1] not in (pks[0], geom_col)]
        for c, _ in cols + [(geom_col, None), (pks[0], None)]:
            if not _IDENT.match(c):
                raise GpkgError(f"{name}: column name {c!r} isn't a plain identifier")
        return Layer(self, name, geom_col, gtype, srs_id, org or "", org_id, pks[0], cols)


def open(path):    # noqa: A001 - mirrors sqlite3.connect / builtins.open
    return GeoPackage(path)
