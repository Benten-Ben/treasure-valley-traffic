"""Synthetic Cropland Data Layer rasters for the tests, written with the standard library.

write() writes one band of 8-bit values as a GeoTIFF: tiled (as NASS's cut is: 256 x 256 tiles,
deflate) or in strips, uncompressed or deflate, with or without the horizontal predictor, classic
TIFF or BigTIFF, either byte order. synthetic_cdl() makes the raster the paving tests read:
developed land (class 122) west of a meridian's Albers x, crops (class 1) east of it.
"""

import math
import struct
import zlib

from plugins.roads.ingest import cdl

SHORT, LONG, DOUBLE, LONG8 = 3, 4, 12, 16
_SIZE = {SHORT: ("H", 2), LONG: ("I", 4), DOUBLE: ("d", 8), LONG8: ("Q", 8)}


def write(path, rows, x0, y0, res, epsg=cdl.EPSG, tile=256, deflate=True, predictor=1, rows_per_strip=None,
          big=False, order="<", bands=1):
    """rows: a list of equal-length bytes, north row first; (x0, y0) the north-west corner."""
    height, width = len(rows), len(rows[0])
    blocks = []
    if tile:
        bw = bh = tile
        for by in range(0, height, bh):
            for bx in range(0, width, bw):
                block = bytearray()
                for r in range(by, by + bh):
                    line = rows[r][bx:bx + bw] if r < height else b""
                    block += line.ljust(bw, b"\0")
                blocks.append(bytes(block))
    else:
        bw, bh = width, rows_per_strip or height
        for by in range(0, height, bh):
            blocks.append(b"".join(rows[by:by + bh]))
    if predictor == 2:
        out = []
        for block in blocks:
            b = bytearray(block)
            for start in range(0, len(b), bw):
                for c in range(start + bw - 1, start, -1):
                    b[c] = (b[c] - b[c - 1]) & 0xFF
            out.append(bytes(b))
        blocks = out
    if deflate:
        blocks = [zlib.compress(b) for b in blocks]
    off_type = LONG8 if big else LONG
    tags = [(256, LONG, [width]), (257, LONG, [height]), (258, SHORT, [8] * bands), (259, SHORT, [8 if deflate else 1]),
            (262, SHORT, [1]), (277, SHORT, [bands]), (284, SHORT, [1]), (317, SHORT, [predictor]),
            (339, SHORT, [1] * bands), (33550, DOUBLE, [res, res, 0.0]), (33922, DOUBLE, [0.0, 0.0, 0.0, x0, y0, 0.0])]
    if tile:
        tags += [(322, SHORT, [bw]), (323, SHORT, [bh]), (324, off_type, [0] * len(blocks)),
                 (325, off_type, [len(b) for b in blocks])]
    else:
        tags += [(273, off_type, [0] * len(blocks)), (278, LONG, [bh]), (279, off_type, [len(b) for b in blocks])]
    keys = [(1024, 0, 1, 1), (1025, 0, 1, 1), (3072, 0, 1, epsg)]
    tags.append((34735, SHORT, [1, 1, 0, len(keys)] + [v for k in keys for v in k]))
    tags.sort()
    offsets_tag = 324 if tile else 273

    head, entry, inline = (16, 20, 8) if big else (8, 12, 4)
    extra_at = head + (8 if big else 2) + len(tags) * entry + (8 if big else 4)
    blobs = {}
    size = 0
    for tag, typ, values in tags:
        code, n = _SIZE[typ]
        if len(values) * n > inline:
            size += (-size) % 8
            blobs[tag] = extra_at + size
            size += len(values) * n
    data_at = extra_at + size
    data_at += (-data_at) % 8
    where, offsets = data_at, []
    for b in blocks:
        offsets.append(where)
        where += len(b)
    out = bytearray(b"II" if order == "<" else b"MM")
    out += struct.pack(order + "HHHQ", 43, 8, 0, head) if big else struct.pack(order + "HI", 42, head)
    out += struct.pack(order + ("Q" if big else "H"), len(tags))
    extra = bytearray()
    for tag, typ, values in tags:
        if tag == offsets_tag:
            values = offsets
        code, n = _SIZE[typ]
        blob = struct.pack(order + code * len(values), *values)
        if tag in blobs:
            pad = blobs[tag] - extra_at - len(extra)
            extra += b"\0" * pad + blob
            value = struct.pack(order + ("Q" if big else "I"), blobs[tag])
        else:
            value = blob.ljust(inline, b"\0")
        out += struct.pack(order + ("HHQ" if big else "HHI"), tag, typ, len(values)) + value
    out += struct.pack(order + ("Q" if big else "I"), 0)
    out += extra
    out += b"\0" * (data_at - len(out))
    for b in blocks:
        out += b
    with open(path, "wb") as f:
        f.write(out)


SPLIT_LON = -116.275              # developed land west of it (at the fixture's latitude), crops east
WEST, SOUTH, EAST, NORTH = -116.62, 42.99, -116.24, 43.62


def synthetic_cdl(path, res=100.0, split_lon=SPLIT_LON, bounds=(WEST, SOUTH, EAST, NORTH), **kwargs):
    """A raster covering bounds (lon/lat; by default the paving fixture): class 122 (developed, low
    intensity) where a cell's centre lies west of split_lon's Albers x at 43.6, class 1 (corn) east
    of it, 0 (no data) in the north-east corner's cell. Returns the split's x."""
    west, south, east, north = bounds
    xs = [cdl.to_albers(lon, lat)[0] for lon in (west, east) for lat in (south, north)]
    ys = [cdl.to_albers(lon, lat)[1] for lon in (west, east) for lat in (south, north)]
    x0, y0 = math.floor(min(xs) / res) * res, math.ceil(max(ys) / res) * res
    width, height = math.ceil((max(xs) - x0) / res), math.ceil((y0 - min(ys)) / res)
    split = cdl.to_albers(split_lon, 43.6)[0]
    row = bytes(122 if x0 + (c + 0.5) * res < split else 1 for c in range(width))
    rows = [row] * height
    rows[0] = row[:-1] + b"\0"
    write(path, rows, x0, y0, res, **kwargs)
    return split
