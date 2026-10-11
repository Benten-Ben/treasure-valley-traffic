"""Read a FlatGeobuf file's header with the standard library: geometry type, columns, feature count, CRS and envelope.

The export contract (manifest.py) checks each FlatGeobuf layer against what its manifest declares without GDAL, so
an export can be checked in the ingest image that wrote it. Only the header is read (the first few kilobytes).

The format (flatgeobuf.org, version 3): 8 magic bytes ("fgb", the major version 3, "fgb", the patch version), a
little-endian uint32 header length, then the header as a FlatBuffers table (header.fbs):

    Header: name, envelope [double], geometry_type ubyte, has_z, has_m, has_t, has_tm, columns [Column],
            features_count ulong (0 = unknown), index_node_size ushort (default 16; 0 = no spatial index), crs Crs,
            title, description, metadata
    Column: name, type ubyte, title, description, width, precision, scale, nullable, unique, primary_key, metadata
    Crs:    org, code int, name, description, wkt, code_string
"""

import struct
from dataclasses import dataclass, field

MAGIC = b"fgb"
MAJOR = 3

GEOMETRY_TYPES = ("Unknown", "Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon",
                  "GeometryCollection", "CircularString", "CompoundCurve", "CurvePolygon", "MultiCurve",
                  "MultiSurface", "Curve", "Surface", "PolyhedralSurface", "TIN", "Triangle")
# Column types, lower case (the manifest's field types use these names).
COLUMN_TYPES = ("byte", "ubyte", "bool", "short", "ushort", "int", "uint", "long", "ulong", "float", "double",
                "string", "json", "datetime", "binary")
INTEGER_TYPES = ("byte", "ubyte", "short", "ushort", "int", "uint", "long", "ulong")


class FgbError(ValueError):
    pass


@dataclass
class Header:
    name: str = ""
    geometry_type: str = "Unknown"
    has_z: bool = False
    has_m: bool = False
    columns: dict = field(default_factory=dict)       # name -> type (lower case), in file order
    features_count: int = 0                            # 0 = unknown
    index_node_size: int = 16                          # 0 = no spatial index
    crs_org: str = ""
    crs_code: int = 0                                  # 0 = not given
    envelope: tuple = ()
    title: str = ""

    @property
    def crs(self):
        """'EPSG:32611', or '' when the file names none."""
        if not self.crs_code:
            return ""
        return f"{(self.crs_org or 'EPSG').upper()}:{self.crs_code}"


class _Table:
    """A FlatBuffers table: fields by slot number."""

    def __init__(self, buf, pos):
        self.buf, self.pos = buf, pos
        vt = pos - struct.unpack_from("<i", buf, pos)[0]
        self.vt_len = struct.unpack_from("<H", buf, vt)[0]
        self.vt = vt

    def _off(self, slot):
        o = 4 + 2 * slot
        if o >= self.vt_len:
            return 0
        return struct.unpack_from("<H", self.buf, self.vt + o)[0]

    def scalar(self, slot, fmt, default):
        o = self._off(slot)
        return struct.unpack_from("<" + fmt, self.buf, self.pos + o)[0] if o else default

    def _target(self, slot):
        o = self._off(slot)
        if not o:
            return None
        at = self.pos + o
        return at + struct.unpack_from("<I", self.buf, at)[0]

    def string(self, slot):
        t = self._target(slot)
        if t is None:
            return ""
        n = struct.unpack_from("<I", self.buf, t)[0]
        return bytes(self.buf[t + 4:t + 4 + n]).decode("utf-8")

    def vector(self, slot):
        """(start of the elements, length) or (None, 0)."""
        t = self._target(slot)
        if t is None:
            return None, 0
        return t + 4, struct.unpack_from("<I", self.buf, t)[0]

    def table(self, slot):
        t = self._target(slot)
        return None if t is None else _Table(self.buf, t)


def parse_header(data):
    """Parse a FlatGeobuf header from the file's first bytes (at least 12 + the header length)."""
    if len(data) < 12 or data[0:3] != MAGIC or data[4:7] != MAGIC:
        raise FgbError("not a FlatGeobuf file (bad magic bytes)")
    if data[3] != MAJOR:
        raise FgbError(f"FlatGeobuf major version {data[3]}, expected {MAJOR}")
    size = struct.unpack_from("<I", data, 8)[0]
    if size < 8 or len(data) < 12 + size:
        raise FgbError(f"header of {size} bytes runs past the data read ({len(data)} bytes)")
    buf = memoryview(data)[12:12 + size]
    try:
        root = _Table(buf, struct.unpack_from("<I", buf, 0)[0])
        h = Header()
        h.name = root.string(0)
        start, n = root.vector(1)
        h.envelope = tuple(struct.unpack_from(f"<{n}d", buf, start)) if n else ()
        g = root.scalar(2, "B", 0)
        h.geometry_type = GEOMETRY_TYPES[g] if g < len(GEOMETRY_TYPES) else f"type {g}"
        h.has_z = bool(root.scalar(3, "B", 0))
        h.has_m = bool(root.scalar(4, "B", 0))
        start, n = root.vector(7)
        for i in range(n):
            at = start + 4 * i
            col = _Table(buf, at + struct.unpack_from("<I", buf, at)[0])
            t = col.scalar(1, "B", 0)
            h.columns[col.string(0)] = COLUMN_TYPES[t] if t < len(COLUMN_TYPES) else f"type {t}"
        h.features_count = root.scalar(8, "Q", 0)
        h.index_node_size = root.scalar(9, "H", 16)
        crs = root.table(10)
        if crs is not None:
            h.crs_org = crs.string(0)
            h.crs_code = crs.scalar(1, "i", 0)
        h.title = root.string(11)
    except (struct.error, IndexError, UnicodeDecodeError) as err:
        raise FgbError(f"damaged FlatGeobuf header: {err}") from None
    return h


def read_header(path):
    """The header of a FlatGeobuf file."""
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12:
            raise FgbError(f"{path}: too short for a FlatGeobuf file")
        size = struct.unpack_from("<I", head, 8)[0]
        if head[0:3] == MAGIC and size > 64 * 1024 * 1024:
            raise FgbError(f"{path}: a {size}-byte header isn't plausible")
        data = head + f.read(size)
    try:
        return parse_header(data)
    except FgbError as err:
        raise FgbError(f"{path}: {err}") from None
