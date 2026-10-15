"""PMTiles v3 (https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md): read tiles from an archive, and
write a small one. Standard library only.

GDAL's PMTiles driver doesn't read WebP raster tiles ("Tile type WEBP not handled", GDAL 3.13 in tvt-worker), and
the map's imagery is WebP, so the sheet tool reads the archive itself:

    with Reader("/srv/tiles/imagery-detail.pmtiles") as r:
        r.header["max_zoom"], r.get(18, x, y)       # the tile's bytes (WebP here), or None

write() makes an archive with a single root directory, for the tests' synthetic imagery.
"""

import gzip
import io
import json
import math
import struct

MAGIC = b"PMTiles"
HEADER_LEN = 127
COMPRESSION = {0: "unknown", 1: "none", 2: "gzip", 3: "brotli", 4: "zstd"}
TILE_TYPES = {0: "unknown", 1: "mvt", 2: "png", 3: "jpeg", 4: "webp", 5: "avif"}
_HEADER = struct.Struct("<7sB QQ QQ QQ QQ QQQ BBBB BB iiii B ii")


class PMTilesError(ValueError):
    pass


# --- tile ids ------------------------------------------------------------------------------------------------------

def zxy_to_tileid(z, x, y):
    """The tile's id: the tiles of every zoom below z, then its position on z's Hilbert curve."""
    if z < 0 or z > 31:
        raise PMTilesError(f"zoom {z} out of range")
    n = 1 << z
    if not (0 <= x < n and 0 <= y < n):
        raise PMTilesError(f"tile {z}/{x}/{y} out of range")
    acc = ((1 << (2 * z)) - 1) // 3
    d = 0
    s = n >> 1
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:                                        # rotate the quadrant
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s >>= 1
    return acc + d


# --- web mercator tile math ----------------------------------------------------------------------------------------

EARTH = 6378137.0
HALF = math.pi * EARTH                                   # 20037508.34...


def lonlat_to_xy(lon, lat):
    """EPSG:3857 metres."""
    return math.radians(lon) * EARTH, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * EARTH


def tile_of(x, y, z):
    """The (column, row) of the z tile holding EPSG:3857 point x, y, as floats."""
    n = 1 << z
    return (x + HALF) / (2 * HALF) * n, (HALF - y) / (2 * HALF) * n


def tile_bounds(z, x, y):
    """(west, south, east, north) of tile z/x/y in EPSG:3857 metres."""
    span = 2 * HALF / (1 << z)
    w, n = -HALF + x * span, HALF - y * span
    return w, n - span, w + span, n


def pixel_m(z, lat, tile_size=512):
    """Ground metres a pixel of a z tile at a latitude."""
    return 2 * HALF / (tile_size * (1 << z)) * math.cos(math.radians(lat))


# --- reading -------------------------------------------------------------------------------------------------------

def _varint(buf, pos):
    shift = value = 0
    while True:
        if pos >= len(buf):
            raise PMTilesError("a directory ends inside a varint")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise PMTilesError("a varint is too long")


def parse_header(data):
    if len(data) < HEADER_LEN or data[:7] != MAGIC:
        raise PMTilesError("not a PMTiles archive")
    f = _HEADER.unpack(data[:HEADER_LEN])
    if f[1] != 3:
        raise PMTilesError(f"PMTiles version {f[1]}; only version 3 is read")
    keys = ("root_offset", "root_length", "metadata_offset", "metadata_length", "leaf_offset", "leaf_length",
            "data_offset", "data_length", "addressed_tiles", "tile_entries", "tile_contents", "clustered",
            "internal_compression", "tile_compression", "tile_type", "min_zoom", "max_zoom", "min_lon_e7",
            "min_lat_e7", "max_lon_e7", "max_lat_e7", "center_zoom", "center_lon_e7", "center_lat_e7")
    h = dict(zip(keys, f[2:]))
    h["tile_type_name"] = TILE_TYPES.get(h["tile_type"], "unknown")
    h["bounds"] = (h["min_lon_e7"] / 1e7, h["min_lat_e7"] / 1e7, h["max_lon_e7"] / 1e7, h["max_lat_e7"] / 1e7)
    return h


def _decompress(data, method):
    if method in (0, 1):
        return data
    if method == 2:
        return gzip.decompress(data)
    raise PMTilesError(f"{COMPRESSION.get(method, method)} compression isn't read here")


def parse_directory(data):
    """[(tile_id, offset, length, run_length)]; run_length 0 is a leaf directory."""
    n, pos = _varint(data, 0)
    ids, runs, lens, offs = [], [], [], []
    last = 0
    for _ in range(n):
        d, pos = _varint(data, pos)
        last += d
        ids.append(last)
    for _ in range(n):
        v, pos = _varint(data, pos)
        runs.append(v)
    for _ in range(n):
        v, pos = _varint(data, pos)
        lens.append(v)
    for i in range(n):
        v, pos = _varint(data, pos)
        if v == 0:
            if i == 0:
                raise PMTilesError("a directory's first offset can't follow another")
            offs.append(offs[i - 1] + lens[i - 1])
        else:
            offs.append(v - 1)
    return list(zip(ids, offs, lens, runs))


def _find(entries, tile_id):
    lo, hi = 0, len(entries) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c = entries[mid][0]
        if tile_id > c:
            lo = mid + 1
        elif tile_id < c:
            hi = mid - 1
        else:
            return entries[mid]
    if hi >= 0:
        e = entries[hi]
        if e[3] == 0 or tile_id - e[0] < e[3]:          # a leaf, or inside the entry's run
            return e
    return None


class Reader:
    """Tiles from a local archive. Directories are cached (the root and up to `cache` leaves)."""

    def __init__(self, path, cache=64):
        self.path = path
        self._f = open(path, "rb")
        try:
            self.header = parse_header(self._f.read(HEADER_LEN))
            h = self.header
            self._root = parse_directory(_decompress(self._read(h["root_offset"], h["root_length"]),
                                                     h["internal_compression"]))
        except BaseException:
            self._f.close()
            raise
        self._leaves, self._cache = {}, cache

    def _read(self, offset, length):
        self._f.seek(offset)
        data = self._f.read(length)
        if len(data) != length:
            raise PMTilesError(f"{self.path}: short read at {offset}")
        return data

    def _leaf(self, offset, length):
        key = (offset, length)
        d = self._leaves.get(key)
        if d is None:
            h = self.header
            d = parse_directory(_decompress(self._read(h["leaf_offset"] + offset, length),
                                            h["internal_compression"]))
            if len(self._leaves) >= self._cache:
                self._leaves.pop(next(iter(self._leaves)))
            self._leaves[key] = d
        return d

    def get(self, z, x, y):
        """The tile's bytes (decompressed when the archive compresses tiles), or None."""
        h = self.header
        if z < h["min_zoom"] or z > h["max_zoom"]:
            return None
        tid = zxy_to_tileid(z, x, y)
        entries = self._root
        for _ in range(4):
            e = _find(entries, tid)
            if e is None:
                return None
            _id, off, length, run = e
            if run == 0:
                entries = self._leaf(off, length)
                continue
            return _decompress(self._read(h["data_offset"] + off, length), h["tile_compression"])
        raise PMTilesError(f"{self.path}: directories nest too deep")

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --- writing (small archives, for tests) ---------------------------------------------------------------------------

def _put_varint(out, v):
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def write(path, tiles, tile_type=4, bounds=(-180.0, -85.0, 180.0, 85.0), metadata=None):
    """Write tiles ({(z, x, y): bytes}) as a PMTiles v3 archive with one root directory (gzip), tiles uncompressed."""
    items = sorted((zxy_to_tileid(z, x, y), z, data) for (z, x, y), data in tiles.items())
    blob, entries = io.BytesIO(), []
    for tid, _z, data in items:
        entries.append((tid, blob.tell(), len(data)))
        blob.write(data)
    d = bytearray()
    _put_varint(d, len(entries))
    last = 0
    for tid, _o, _l in entries:
        _put_varint(d, tid - last)
        last = tid
    for _ in entries:
        _put_varint(d, 1)
    for _t, _o, length in entries:
        _put_varint(d, length)
    for i, (_t, off, _l) in enumerate(entries):
        _put_varint(d, 0 if i and off == entries[i - 1][1] + entries[i - 1][2] else off + 1)
    root = gzip.compress(bytes(d))
    meta = gzip.compress(json.dumps(metadata or {}).encode())
    data = blob.getvalue()
    zooms = [z for _t, z, _d in items] or [0]
    root_off = HEADER_LEN
    meta_off = root_off + len(root)
    data_off = meta_off + len(meta)
    w, s, e, n = bounds
    header = _HEADER.pack(MAGIC, 3, root_off, len(root), meta_off, len(meta), data_off, 0, data_off, len(data),
                          len(entries), len(entries), len(entries), 1, 2, 1, tile_type, min(zooms), max(zooms),
                          round(w * 1e7), round(s * 1e7), round(e * 1e7), round(n * 1e7), min(zooms),
                          round((w + e) / 2 * 1e7), round((s + n) / 2 * 1e7))
    with open(path, "wb") as f:
        f.write(header)
        f.write(root)
        f.write(meta)
        f.write(data)
