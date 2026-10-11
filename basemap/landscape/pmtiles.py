"""Read a PMTiles (version 3) archive with the standard library: its header, metadata and tile directory, and write a
copy with new metadata. The bake (bake.py) uses it to measure tiles against the budget, to read back what it wrote,
and to put its entry and credits into the file; `bake.py check` uses it to say what each file on disk may be served
to. GDAL writes the archives; nothing here decodes a tile.

The format (github.com/protomaps/PMTiles, spec v3): a 127-byte header, then the root directory, the JSON metadata,
the leaf directories and the tile data, each at the offset and length the header gives. Directories (and the
metadata) are compressed as the header's internal compression says. A directory lists entries by tile id (zoom
levels in order, each along a Hilbert curve): tile id, run length (consecutive ids sharing one tile's bytes; 0 points
to a leaf directory), length and offset (from the start of the tile data, or of the leaf directories for a leaf).
"""

import gzip
import json
import os
import struct
from dataclasses import dataclass

MAGIC = b"PMTiles"
VERSION = 3
HEADER_LEN = 127
COMPRESSION = {0: "unknown", 1: "none", 2: "gzip", 3: "brotli", 4: "zstd"}
TILE_TYPES = {0: "unknown", 1: "mvt", 2: "png", 3: "jpeg", 4: "webp", 5: "avif"}
_U64 = ("root_offset", "root_length", "metadata_offset", "metadata_length", "leaf_offset", "leaf_length",
        "data_offset", "data_length", "addressed_tiles", "tile_entries", "tile_contents")


class PMTilesError(ValueError):
    pass


@dataclass
class Header:
    root_offset: int
    root_length: int
    metadata_offset: int
    metadata_length: int
    leaf_offset: int
    leaf_length: int
    data_offset: int
    data_length: int
    addressed_tiles: int
    tile_entries: int
    tile_contents: int
    clustered: bool
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int
    bounds: tuple            # (west, south, east, north), degrees
    center_zoom: int
    center: tuple            # (lon, lat)

    @property
    def tile_type_name(self):
        return TILE_TYPES.get(self.tile_type, f"type {self.tile_type}")

    @property
    def tile_compression_name(self):
        return COMPRESSION.get(self.tile_compression, f"type {self.tile_compression}")


@dataclass(frozen=True)
class Entry:
    tile_id: int
    offset: int              # from the start of the tile data (a tile) or of the leaf directories (a leaf)
    length: int
    run_length: int          # 0: a leaf directory


def parse_header(data):
    if len(data) < HEADER_LEN or data[:7] != MAGIC:
        raise PMTilesError("not a PMTiles archive (bad magic bytes)")
    if data[7] != VERSION:
        raise PMTilesError(f"PMTiles version {data[7]}, expected {VERSION}")
    u = struct.unpack_from("<11Q", data, 8)
    clustered, internal, tile_comp, tile_type, minz, maxz = struct.unpack_from("<6B", data, 96)
    w, s, e, n = struct.unpack_from("<4i", data, 102)
    cz = data[118]
    clon, clat = struct.unpack_from("<2i", data, 119)
    return Header(*u, bool(clustered), internal, tile_comp, tile_type, minz, maxz,
                  (w / 1e7, s / 1e7, e / 1e7, n / 1e7), cz, (clon / 1e7, clat / 1e7))


def pack_header(h):
    """The 127 header bytes."""
    w, s, e, n = (round(v * 1e7) for v in h.bounds)
    clon, clat = (round(v * 1e7) for v in h.center)
    return (MAGIC + bytes([VERSION]) + struct.pack("<11Q", *(getattr(h, k) for k in _U64))
            + struct.pack("<6B", int(h.clustered), h.internal_compression, h.tile_compression, h.tile_type,
                          h.min_zoom, h.max_zoom)
            + struct.pack("<4i", w, s, e, n) + bytes([h.center_zoom]) + struct.pack("<2i", clon, clat))


def read_header(path):
    with open(path, "rb") as f:
        return parse_header(f.read(HEADER_LEN))


def _decompress(data, how):
    if how == 1:
        return bytes(data)
    if how == 2:
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as err:
            raise PMTilesError(f"damaged gzip section: {err}") from None
    raise PMTilesError(f"unsupported internal compression {COMPRESSION.get(how, how)}")


def _compress(data, how):
    if how == 1:
        return data
    if how == 2:
        return gzip.compress(data, mtime=0)
    raise PMTilesError(f"unsupported internal compression {COMPRESSION.get(how, how)}")


def _read(f, offset, length):
    f.seek(offset)
    data = f.read(length)
    if len(data) != length:
        raise PMTilesError(f"truncated archive: {length} bytes at {offset}, got {len(data)}")
    return data


def read_metadata(path):
    """The archive's JSON metadata, as a dict."""
    with open(path, "rb") as f:
        h = parse_header(f.read(HEADER_LEN))
        raw = _decompress(_read(f, h.metadata_offset, h.metadata_length), h.internal_compression)
    try:
        m = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as err:
        raise PMTilesError(f"metadata isn't JSON: {err}") from None
    if not isinstance(m, dict):
        raise PMTilesError("metadata isn't a JSON object")
    return m


def _varint(buf, pos):
    out, shift = 0, 0
    while True:
        if pos >= len(buf):
            raise PMTilesError("damaged directory (a varint runs past its end)")
        b = buf[pos]
        pos += 1
        out |= (b & 0x7F) << shift
        if not b & 0x80:
            return out, pos
        shift += 7
        if shift > 63:
            raise PMTilesError("damaged directory (a varint over 64 bits)")


def decode_directory(buf):
    """[Entry] of one decompressed directory."""
    n, pos = _varint(buf, 0)
    ids, last = [], 0
    for _ in range(n):
        v, pos = _varint(buf, pos)
        last += v
        ids.append(last)
    runs, lengths, offsets = [], [], []
    for _ in range(n):
        v, pos = _varint(buf, pos)
        runs.append(v)
    for _ in range(n):
        v, pos = _varint(buf, pos)
        lengths.append(v)
    for i in range(n):
        v, pos = _varint(buf, pos)
        if v == 0 and i > 0:
            offsets.append(offsets[i - 1] + lengths[i - 1])
        elif v == 0:
            raise PMTilesError("damaged directory (the first entry has no offset)")
        else:
            offsets.append(v - 1)
    return [Entry(ids[i], offsets[i], lengths[i], runs[i]) for i in range(n)]


def entries(path):
    """Every tile entry (run_length >= 1) in tile-id order, leaf directories followed."""
    with open(path, "rb") as f:
        h = parse_header(f.read(HEADER_LEN))
        out = []

        def walk(offset, length, depth):
            if depth > 4:
                raise PMTilesError("leaf directories nested too deep")
            for e in decode_directory(_decompress(_read(f, offset, length), h.internal_compression)):
                if e.run_length == 0:
                    walk(h.leaf_offset + e.offset, e.length, depth + 1)
                else:
                    out.append(e)

        walk(h.root_offset, h.root_length, 0)
    return out


# --- tile ids --------------------------------------------------------------------------------------------------

def _rotate(n, x, y, rx, ry):
    if ry == 0:
        if rx == 1:
            x, y = n - 1 - x, n - 1 - y
        x, y = y, x
    return x, y


def _first_id(z):
    """The tile id of zoom z's first tile: the count of tiles in every lower zoom."""
    return ((1 << (2 * z)) - 1) // 3


def tile_id(z, x, y):
    """The PMTiles tile id of z/x/y (XYZ)."""
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise ValueError(f"{z}/{x}/{y} is outside zoom {z}")
    d, s = 0, n >> 1
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        x, y = _rotate(n, x, y, rx, ry)
        s >>= 1
    return _first_id(z) + d


def zxy(tid):
    """(z, x, y) of a tile id."""
    z = 0
    while _first_id(z + 1) <= tid:
        z += 1
    t = tid - _first_id(z)
    n, x, y, s = 1 << z, 0, 0, 1
    while s < n:
        rx = 1 & (t // 2)
        ry = 1 & (t ^ rx)
        x, y = _rotate(s, x, y, rx, ry)
        x += s * rx
        y += s * ry
        t //= 4
        s *= 2
    return z, x, y


def tile_sizes(path, tiles=None):
    """{(z, x, y): stored bytes} of every tile in the archive (tiles: only these (z, x, y))."""
    want = None if tiles is None else {tile_id(*t): t for t in tiles}
    out = {}
    for e in entries(path):
        for tid in range(e.tile_id, e.tile_id + e.run_length):
            if want is None:
                out[zxy(tid)] = e.length
            elif tid in want:
                out[want[tid]] = e.length
    return out


def tile_data(path, z, x, y):
    """A tile's stored bytes (compressed as the header's tile compression says), or None when it has none."""
    tid = tile_id(z, x, y)
    for e in entries(path):
        if e.tile_id <= tid < e.tile_id + e.run_length:
            h = read_header(path)
            with open(path, "rb") as f:
                return _read(f, h.data_offset + e.offset, e.length)
    return None


# --- writing ---------------------------------------------------------------------------------------------------

def _copy(src, dst, offset, length, chunk=1 << 20):
    src.seek(offset)
    left = length
    while left:
        b = src.read(min(chunk, left))
        if not b:
            raise PMTilesError(f"truncated archive: {length} bytes at {offset}")
        dst.write(b)
        left -= len(b)


def write_with_metadata(src_path, dst_path, metadata):
    """Copy an archive to dst_path with new JSON metadata, in the spec's order (header, root directory, metadata,
    leaf directories, tile data). Directories and tiles are copied byte for byte: their offsets are relative to
    their own sections, so only the header's section offsets change. dst_path is written and fsynced, not renamed."""
    body = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(src_path, "rb") as src:
        h = parse_header(src.read(HEADER_LEN))
        meta = _compress(body, h.internal_compression)
        h.root_offset, old_root = HEADER_LEN, h.root_offset
        h.metadata_offset, h.metadata_length = HEADER_LEN + h.root_length, len(meta)
        old_leaf, h.leaf_offset = h.leaf_offset, h.metadata_offset + h.metadata_length
        old_data, h.data_offset = h.data_offset, h.leaf_offset + h.leaf_length
        with open(dst_path, "wb") as dst:
            dst.write(pack_header(h))
            _copy(src, dst, old_root, h.root_length)
            dst.write(meta)
            _copy(src, dst, old_leaf, h.leaf_length)
            _copy(src, dst, old_data, h.data_length)
            dst.flush()
            os.fsync(dst.fileno())
    return h
