"""A small PMTiles v3 writer for the tests (standard library), so the reader is checked against archives with run
lengths, contiguous and non-contiguous offsets and leaf directories, without GDAL."""

import gzip
import json

from basemap.landscape import pmtiles as P


def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def encode_directory(entries):
    """entries: [(tile_id, offset, length, run_length)], by tile id."""
    out = bytearray(varint(len(entries)))
    last = 0
    for tid, _, _, _ in entries:
        out += varint(tid - last)
        last = tid
    for _, _, _, run in entries:
        out += varint(run)
    for _, _, length, _ in entries:
        out += varint(length)
    for i, (_, off, _, _) in enumerate(entries):
        prev = entries[i - 1] if i else None
        out += varint(0 if prev and off == prev[1] + prev[2] else off + 1)
    return bytes(out)


def write(path, tiles, metadata=None, minzoom=0, maxzoom=None, leaf_size=None, internal=2, gap=False,
          bounds=(-117.05, 43.0, -115.95, 43.85)):
    """tiles: {(z, x, y): bytes}. Consecutive ids with equal bytes share one entry (a run). leaf_size: split the
    entries into leaf directories of that many. gap: leave a byte between tiles, so offsets aren't contiguous."""
    comp = (lambda b: gzip.compress(b, mtime=0)) if internal == 2 else (lambda b: b)
    by_id = sorted((P.tile_id(*t), b) for t, b in tiles.items())
    data, entries = bytearray(), []
    for tid, b in by_id:
        last = entries[-1] if entries else None
        if last and last[0] + last[3] == tid and bytes(data[last[1]:last[1] + last[2]]) == b:
            entries[-1] = (last[0], last[1], last[2], last[3] + 1)
            continue
        if gap and data:
            data += b"\0"
        entries.append((tid, len(data), len(b), 1))
        data += b
    leaves = b""
    if leaf_size:
        root = []
        for i in range(0, len(entries), leaf_size):
            chunk = comp(encode_directory(entries[i:i + leaf_size]))
            root.append((entries[i][0], len(leaves), len(chunk), 0))
            leaves += chunk
        root_bytes = comp(encode_directory(root))
    else:
        root_bytes = comp(encode_directory(entries))
    meta = comp(json.dumps(metadata or {}).encode("utf-8"))
    zs = [t[0] for t in tiles] or [0]
    h = P.Header(P.HEADER_LEN, len(root_bytes), P.HEADER_LEN + len(root_bytes), len(meta),
                 P.HEADER_LEN + len(root_bytes) + len(meta), len(leaves),
                 P.HEADER_LEN + len(root_bytes) + len(meta) + len(leaves), len(data),
                 sum(e[3] for e in entries), len(entries), len(entries), True, internal, 2, 1,
                 minzoom, max(zs) if maxzoom is None else maxzoom, bounds, minzoom,
                 ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2))
    with open(path, "wb") as f:
        f.write(P.pack_header(h))
        f.write(root_bytes)
        f.write(meta)
        f.write(leaves)
        f.write(bytes(data))
    return path
