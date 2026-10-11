"""Read a GeoTIFF's size, bands and georeferencing with the standard library.

The export contract (manifest.py) checks each GeoTIFF layer against its manifest entry without GDAL: its size, its
bands' count and sample types, its pixel corners (from the tie point and pixel scale, or the model transformation)
and its EPSG code, so a raster written half a cell off the ground grid, or at the wrong size, is refused before
anything reads it. Only the first image's tags are read (classic TIFF and BigTIFF, either byte order), never the
pixels; a cloud-optimised GeoTIFF's first image is its full-resolution one.

Tags (TIFF 6.0, GeoTIFF 1.1): ImageWidth 256, ImageLength 257, BitsPerSample 258, SamplesPerPixel 277, SampleFormat
339, ModelPixelScale 33550, ModelTiepoint 33922, ModelTransformation 34264, GeoKeyDirectory 34735 (keys
GTRasterType 1025, ProjectedCSType 3072, GeographicType 2048).
"""

import struct
from dataclasses import dataclass

# TIFF field types: struct code and size of one value.
_TYPES = {1: ("B", 1), 2: ("B", 1), 3: ("H", 2), 4: ("I", 4), 5: ("I", 4), 6: ("b", 1), 7: ("B", 1),
          8: ("h", 2), 9: ("i", 4), 10: ("i", 4), 11: ("f", 4), 12: ("d", 8), 16: ("Q", 8), 17: ("q", 8),
          18: ("Q", 8)}
_RATIONAL = (5, 10)
_WANT = {256, 257, 258, 277, 339, 33550, 33922, 34264, 34735}
_MAX_VALUES = 4096                      # far more than any tag read here holds

# (bits, SampleFormat) -> the manifest's band type
SAMPLE_TYPES = {(8, 1): "uint8", (8, 2): "int8", (16, 1): "uint16", (16, 2): "int16", (32, 1): "uint32",
                (32, 2): "int32", (32, 3): "float32", (64, 3): "float64"}


class TiffError(ValueError):
    pass


@dataclass
class Header:
    width: int
    height: int
    bands: int
    sample_types: tuple            # per band, e.g. ("uint8", "uint8"); "unknown" for a type the contract lacks
    transform: tuple = None        # GDAL geotransform of the pixel corners, or None when the file isn't georeferenced
    epsg: int = 0                  # the projected (or geographic) CRS's EPSG code; 0 when unstated or user-defined
    pixel_is_point: bool = False
    bigtiff: bool = False


def read_header(path):
    """The first image's Header. Raises TiffError when the file isn't a TIFF or its tags are cut short."""
    try:
        with open(path, "rb") as f:
            return _parse(f)
    except OSError as err:
        raise TiffError(f"{path}: {err}") from None
    except (struct.error, IndexError) as err:
        raise TiffError(f"{path}: cut short or malformed ({err})") from None


def _parse(f):
    head = f.read(16)
    if len(head) < 8 or head[:2] not in (b"II", b"MM"):
        raise TiffError("not a TIFF file")
    e = "<" if head[:2] == b"II" else ">"
    version = struct.unpack(e + "H", head[2:4])[0]
    if version == 42:
        big, ifd = False, struct.unpack(e + "I", head[4:8])[0]
    elif version == 43:
        if len(head) < 16 or struct.unpack(e + "HH", head[4:8]) != (8, 0):
            raise TiffError("a BigTIFF header with an unknown offset size")
        big, ifd = True, struct.unpack(e + "Q", head[8:16])[0]
    else:
        raise TiffError(f"not a TIFF file (version {version})")
    if ifd == 0:
        raise TiffError("the TIFF has no image")
    tags = _read_ifd(f, e, ifd, big)
    for tag in (256, 257):
        if tag not in tags:
            raise TiffError(f"the TIFF has no tag {tag} (image size)")
    width, height = int(tags[256][0]), int(tags[257][0])
    n = int(tags.get(277, (1,))[0])
    bits = list(tags.get(258, (1,)))
    fmts = list(tags.get(339, (1,)))
    bits = bits * n if len(bits) == 1 else bits
    fmts = fmts * n if len(fmts) == 1 else fmts
    if len(bits) != n or len(fmts) != n:
        raise TiffError("BitsPerSample or SampleFormat doesn't give one value per band")
    types = tuple(SAMPLE_TYPES.get((int(b), int(s)), "unknown") for b, s in zip(bits, fmts))

    keys = _geokeys(tags.get(34735))
    point = keys.get(1025) == 2
    epsg = keys.get(3072) or keys.get(2048) or 0
    if epsg == 32767:                   # user-defined
        epsg = 0
    transform = None
    if 33922 in tags and 33550 in tags:
        tie, scale = tags[33922], tags[33550]
        if len(tie) < 6 or len(scale) < 2:
            raise TiffError("ModelTiepoint or ModelPixelScale is too short")
        i, j, _, x, y, _ = tie[:6]
        sx, sy = scale[:2]
        x0, y0 = x - i * sx, y + j * sy
        if point:
            x0, y0 = x0 - sx / 2, y0 + sy / 2
        transform = (x0, sx, 0.0, y0, 0.0, -sy)
    elif 34264 in tags:
        m = tags[34264]
        if len(m) < 16:
            raise TiffError("ModelTransformation is too short")
        a, b, d, c, e_, h = m[0], m[1], m[3], m[4], m[5], m[7]
        x0, y0 = d, h
        if point:
            x0, y0 = x0 - (a + b) / 2, y0 - (c + e_) / 2
        transform = (x0, a, b, y0, c, e_)
    return Header(width, height, n, types, transform, int(epsg), point, big)


def _read_ifd(f, e, offset, big):
    f.seek(offset)
    if big:
        count = struct.unpack(e + "Q", _exact(f, 8))[0]
        size, entry = 20, e + "HHQ8s"
    else:
        count = struct.unpack(e + "H", _exact(f, 2))[0]
        size, entry = 12, e + "HHI4s"
    if count > 4096:
        raise TiffError(f"an image directory with {count} entries")
    raw = _exact(f, count * size)
    tags = {}
    for k in range(count):
        tag, typ, n, value = struct.unpack(entry, raw[k * size:(k + 1) * size])
        if tag not in _WANT or typ not in _TYPES:
            continue
        code, width = _TYPES[typ]
        values = n * (2 if typ in _RATIONAL else 1)
        if values > _MAX_VALUES:
            raise TiffError(f"tag {tag} holds {n} values")
        nbytes = values * width
        if nbytes <= len(value):
            data = value[:nbytes]
        else:
            where = struct.unpack(e + ("Q" if big else "I"), value)[0]
            here = f.tell()
            f.seek(where)
            data = _exact(f, nbytes)
            f.seek(here)
        vals = struct.unpack(e + code * values, data)
        if typ in _RATIONAL:
            vals = tuple(vals[2 * i] / vals[2 * i + 1] if vals[2 * i + 1] else 0.0 for i in range(n))
        tags[tag] = vals
    return tags


def _exact(f, n):
    data = f.read(n)
    if len(data) != n:
        raise TiffError("cut short")
    return data


def _geokeys(values):
    """GeoKeyDirectory's directly stored keys: {key id: value}."""
    if not values or len(values) < 4:
        return {}
    out = {}
    n = values[3]
    for k in range(n):
        entry = values[4 + 4 * k:8 + 4 * k]
        if len(entry) < 4:
            raise TiffError("GeoKeyDirectory is cut short")
        key, location, _count, value = entry
        if location == 0:
            out[int(key)] = int(value)
    return out
