"""Small synthetic GeoTIFFs for the tests, written with the standard library (test_tif.py checks tif.py reads them as
GDAL does; test_rasterize.py checks GDAL's own files in the worker image).

write_geotiff() writes one uncompressed strip of zeros (or, with data=False, the tags alone, for a large grid whose
pixels no test reads), classic TIFF or BigTIFF, either byte order, with PixelIsArea or PixelIsPoint tie points.
"""

import struct

_FORMATS = {"uint8": (8, 1), "int8": (8, 2), "uint16": (16, 1), "int16": (16, 2), "uint32": (32, 1),
            "int32": (32, 2), "float32": (32, 3), "float64": (64, 3)}
SHORT, LONG, DOUBLE, LONG8 = 3, 4, 12, 16
_SIZE = {SHORT: ("H", 2), LONG: ("I", 4), DOUBLE: ("d", 8), LONG8: ("Q", 8)}


def write_geotiff(path, width, height, transform, epsg=32611, types=("uint8",), point=False, big=False,
                  order="<", data=True, matrix=False):
    """transform: a GDAL geotransform (x0, rx, 0, y0, 0, ry) of the pixel corners. matrix writes it as a
    ModelTransformation instead of a tie point and pixel scale."""
    x0, rx, rxy, y0, ryx, ry = transform
    bits = [_FORMATS[t][0] for t in types]
    fmts = [_FORMATS[t][1] for t in types]
    nbytes = width * height * sum(bits) // 8 if data else 1
    tags = [(256, LONG, [width]), (257, LONG, [height]), (258, SHORT, bits), (259, SHORT, [1]),
            (262, SHORT, [1]), (273, LONG8 if big else LONG, [0]), (277, SHORT, [len(types)]),
            (278, LONG, [height]), (279, LONG8 if big else LONG, [nbytes]), (284, SHORT, [1]),
            (339, SHORT, fmts)]
    if matrix:
        sx, sy = x0, y0
        if point:
            sx, sy = x0 + (rx + rxy) / 2, y0 + (ryx + ry) / 2
        tags.append((34264, DOUBLE, [rx, rxy, 0.0, sx, ryx, ry, 0.0, sy, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]))
    else:
        tx, ty = (x0 + rx / 2, y0 + ry / 2) if point else (x0, y0)
        tags.append((33550, DOUBLE, [rx, -ry, 0.0]))
        tags.append((33922, DOUBLE, [0.0, 0.0, 0.0, tx, ty, 0.0]))
    keys = [(1024, 0, 1, 1), (1025, 0, 1, 2 if point else 1), (3072, 0, 1, epsg)]
    tags.append((34735, SHORT, [1, 1, 0, len(keys)] + [v for k in keys for v in k]))
    tags.sort()

    head = 16 if big else 8
    entry = 20 if big else 12
    inline = 8 if big else 4
    ifd_size = (8 if big else 2) + len(tags) * entry + (8 if big else 4)
    extra_at = head + ifd_size
    extra = bytearray()
    entries = []
    pixels_at = None
    for tag, typ, values in tags:
        code, size = _SIZE[typ]
        blob = struct.pack(order + code * len(values), *values)
        if tag == 273:
            entries.append([tag, typ, len(values), None])          # filled once the pixels' place is known
            continue
        if len(blob) <= inline:
            entries.append([tag, typ, len(values), blob.ljust(inline, b"\0")])
        else:
            while (extra_at + len(extra)) % 2:
                extra += b"\0"
            where = extra_at + len(extra)
            extra += blob
            entries.append([tag, typ, len(values), struct.pack(order + ("Q" if big else "I"), where)])
    pixels_at = extra_at + len(extra)
    for e in entries:
        if e[0] == 273:
            e[3] = struct.pack(order + ("Q" if big else "I"), pixels_at)
    out = bytearray()
    out += b"II" if order == "<" else b"MM"
    if big:
        out += struct.pack(order + "HHHQ", 43, 8, 0, head)
        out += struct.pack(order + "Q", len(entries))
        for tag, typ, n, value in entries:
            out += struct.pack(order + "HHQ", tag, typ, n) + value
        out += struct.pack(order + "Q", 0)
    else:
        out += struct.pack(order + "HI", 42, head)
        out += struct.pack(order + "H", len(entries))
        for tag, typ, n, value in entries:
            out += struct.pack(order + "HHI", tag, typ, n) + value
        out += struct.pack(order + "I", 0)
    out += extra
    out += bytes(nbytes)
    with open(path, "wb") as f:
        f.write(out)
    return path


def grid_tiff(path, g, bands, **kw):
    """A GeoTIFF exactly on a manifest's grid entry ({res, west, north, width, height}) with the given band types."""
    return write_geotiff(path, g["width"], g["height"], (g["west"], g["res"], 0.0, g["north"], 0.0, -g["res"]),
                         types=tuple(b["type"] for b in bands), **kw)
