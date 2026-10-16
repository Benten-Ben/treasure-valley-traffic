"""Write a PMTiles (version 3) archive of raster tiles with the standard library, a tile at a time (G1a's ground
tiles). The reader, the header and the tile ids are the bake's (basemap/landscape/pmtiles.py).

    w = Writer(path, tile_type=4, metadata={...})      # 4: WebP
    w.add(15, x, y, data)                              # any order; a tile whose bytes repeat another's is stored once
    w.finish(bounds=(w, s, e, n), center=(lon, lat, z))

Tiles are spooled to `<path>.tiles` as they come and copied into the archive in tile-id order when it's finished, so
the archive is clustered and memory holds only the directory (24 bytes a tile). Directories are gzip-compressed; the
root directory and the header fit the first 16,384 bytes (the spec's first request), with leaf directories when the
tiles need them. The archive is written to `<path>.part` and renamed into place, so a reader never sees half of one.
"""

import gzip
import hashlib
import json
import os

from basemap.landscape import pmtiles as P

ROOT_BUDGET = 16384 - P.HEADER_LEN       # the header and the root directory fit one 16 KiB request
LEAF_SIZE = 4096                         # entries a leaf directory holds, to start with


def _put_varint(out, v):
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def encode_directory(entries):
    """A directory's bytes (uncompressed) from [P.Entry] in tile-id order."""
    d = bytearray()
    _put_varint(d, len(entries))
    last = 0
    for e in entries:
        _put_varint(d, e.tile_id - last)
        last = e.tile_id
    for e in entries:
        _put_varint(d, e.run_length)
    for e in entries:
        _put_varint(d, e.length)
    for i, e in enumerate(entries):
        prev = entries[i - 1] if i else None
        if prev is not None and e.offset == prev.offset + prev.length:
            _put_varint(d, 0)
        else:
            _put_varint(d, e.offset + 1)
    return bytes(d)


def _gz(b):
    return gzip.compress(b, mtime=0)


def directories(entries):
    """(root bytes, leaves bytes) compressed, with leaves only when the root alone won't fit ROOT_BUDGET."""
    root = _gz(encode_directory(entries))
    if len(root) <= ROOT_BUDGET:
        return root, b""
    size = LEAF_SIZE
    while True:
        leaves, roots, off = bytearray(), [], 0
        for i in range(0, len(entries), size):
            chunk = entries[i:i + size]
            body = _gz(encode_directory(chunk))
            roots.append(P.Entry(chunk[0].tile_id, off, len(body), 0))
            leaves += body
            off += len(body)
        root = _gz(encode_directory(roots))
        if len(root) <= ROOT_BUDGET:
            return root, bytes(leaves)
        size *= 2


class Writer:
    def __init__(self, path, tile_type=4, metadata=None):
        self.path, self.tile_type, self.metadata = path, tile_type, dict(metadata or {})
        self.spool_path = path + ".tiles"
        self.spool = open(self.spool_path, "wb")
        self.at = {}                     # tile id -> (spool offset, length, sha)
        self.zooms = set()

    def add(self, z, x, y, data):
        tid = P.tile_id(z, x, y)
        if tid in self.at:
            raise ValueError(f"tile {z}/{x}/{y} added twice")
        off = self.spool.tell()
        self.spool.write(data)
        self.at[tid] = (off, len(data), hashlib.sha256(data).digest())
        self.zooms.add(z)

    def finish(self, bounds, center):
        """Write the archive. bounds (west, south, east, north) and center (lon, lat, zoom), degrees. Returns the
        header."""
        self.spool.close()
        if not self.at:
            os.remove(self.spool_path)
            raise ValueError("no tiles to write")
        ids = sorted(self.at)
        by_sha, entries, order, data_len = {}, [], [], 0
        for tid in ids:
            off, length, sha = self.at[tid]
            if sha in by_sha:
                doff = by_sha[sha]
                last = entries[-1]
                if last.offset == doff and last.tile_id + last.run_length == tid and last.length == length:
                    entries[-1] = P.Entry(last.tile_id, last.offset, last.length, last.run_length + 1)
                else:
                    entries.append(P.Entry(tid, doff, length, 1))
                continue
            by_sha[sha] = data_len
            entries.append(P.Entry(tid, data_len, length, 1))
            order.append((off, length))
            data_len += length
        root, leaves = directories(entries)
        meta = _gz(json.dumps(self.metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        root_off = P.HEADER_LEN
        meta_off = root_off + len(root)
        leaf_off = meta_off + len(meta)
        data_off = leaf_off + len(leaves)
        cz = int(center[2]) if len(center) > 2 else min(self.zooms)
        h = P.Header(root_off, len(root), meta_off, len(meta), leaf_off, len(leaves), data_off, data_len,
                     len(ids), len(entries), len(by_sha), True, 2, 1, self.tile_type, min(self.zooms),
                     max(self.zooms), tuple(bounds), min(max(cz, min(self.zooms)), max(self.zooms)),
                     (center[0], center[1]))
        part = self.path + ".part"
        with open(part, "wb") as out, open(self.spool_path, "rb") as src:
            out.write(P.pack_header(h))
            out.write(root)
            out.write(meta)
            out.write(leaves)
            for off, length in order:
                src.seek(off)
                out.write(src.read(length))
            out.flush()
            os.fsync(out.fileno())
        os.replace(part, self.path)
        os.remove(self.spool_path)
        return h

    def abort(self):
        try:
            self.spool.close()
        finally:
            for p in (self.spool_path, self.path + ".part"):
                if os.path.exists(p):
                    os.remove(p)


def first_request(path, length=16384):
    """The bytes a client's first request reads (the header and the root directory, by the spec's 16 KiB), and the
    leaf directories' total, for the first-load estimate: (first, leaves)."""
    h = P.read_header(path)
    return min(length, os.path.getsize(path)), h.leaf_length
