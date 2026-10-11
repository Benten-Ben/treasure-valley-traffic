"""Developed land from USDA NASS's Cropland Data Layer, read with the standard library (plan C11).

The paving consumer (sources/osm_paving.py) gives an untagged service way or parking lot its kind's
material only on developed land, and calls it "surface unknown" elsewhere. Developed land is the
CDL's developed classes 122-124 (low, medium and high intensity), in the 2025 layer at 10 m: the
same classes the farm fields' "built over" rule reads. Class 121, developed open space, is left
out: it's parks, lawns and verges, and NLCD (where the CDL takes its developed classes from) paints
rural roads into it.

The raster is NASS's own cut for the map box (cdl_2025_10m.tif, from the national 10 m layer; the
provenance is kept with the downloaded sources): one band of 8-bit class codes in NAD83 / Conus
Albers (EPSG:5070), 256 x 256 tiles, deflate, 0 for no data. It's read here without GDAL: the
header through the ground contract's stdlib reader (basemap/ground/tif.py), and the tiles inflated
with zlib as they're needed. Coordinates take the ground's datum policy, the null shift: OpenStreetMap's
WGS 84 lon/lat are projected as if they were NAD83's (about 1 m here, a tenth of a cell).

    from plugins.roads.ingest import cdl
    land = cdl.Developed(cdl.Raster(path))
    land.line_share(coords)        # [[lon, lat], ...]: share of samples every 10 m on developed land
    land.area_share(polygons)      # GeoJSON MultiPolygon coordinates: share of the cells inside

USDA NASS Cropland Data Layer: public domain, credit "USDA NASS Cropland Data Layer 2025".
"""

import math
import struct
import zlib

from basemap.ground import tif

DEVELOPED = frozenset({122, 123, 124})   # developed, low to high intensity (121, open space, isn't)
NODATA = 0
EPSG = 5070                              # NAD83 / Conus Albers
CREDIT = "USDA NASS Cropland Data Layer 2025"
LICENSE = "public domain"
STEP_M = 10.0                            # samples along a line, one per cell length


# ---- NAD83 / Conus Albers (EPSG:5070), forward ------------------------------
# Snyder, Map Projections: A Working Manual (USGS PP 1395, 1987), pp. 101-102, on GRS 80.

_A, _F = 6378137.0, 1 / 298.257222101
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)


def _q(phi):
    s = math.sin(phi)
    return (1 - _E2) * (s / (1 - _E2 * s * s) - math.log((1 - _E * s) / (1 + _E * s)) / (2 * _E))


def _m(phi):
    s = math.sin(phi)
    return math.cos(phi) / math.sqrt(1 - _E2 * s * s)


_PHI0, _PHI1, _PHI2, _LAM0 = map(math.radians, (23.0, 29.5, 45.5, -96.0))
_M1, _M2 = _m(_PHI1), _m(_PHI2)
_Q1, _Q2 = _q(_PHI1), _q(_PHI2)
_N = (_M1 * _M1 - _M2 * _M2) / (_Q2 - _Q1)
_C = _M1 * _M1 + _N * _Q1
_RHO0 = _A * math.sqrt(_C - _N * _q(_PHI0)) / _N


def to_albers(lon, lat):
    """lon/lat (NAD83, or WGS 84 by the null shift) to EPSG:5070 metres."""
    rho = _A * math.sqrt(_C - _N * _q(math.radians(lat))) / _N
    theta = _N * (math.radians(lon) - _LAM0)
    return rho * math.sin(theta), _RHO0 - rho * math.cos(theta)


# ---- the raster ------------------------------------------------------------

class RasterError(ValueError):
    pass


_TYPES = {1: ("B", 1), 3: ("H", 2), 4: ("I", 4), 16: ("Q", 8)}
_COMPRESSION = {1: "none", 8: "deflate", 32946: "deflate"}


def _ifd(f, path):
    """The first image's tags this reader needs: {tag: (values)}. Classic TIFF and BigTIFF."""
    head = f.read(16)
    if head[:2] not in (b"II", b"MM"):
        raise RasterError(f"{path}: not a TIFF file")
    e = "<" if head[:2] == b"II" else ">"
    big = struct.unpack(e + "H", head[2:4])[0] == 43
    f.seek(struct.unpack(e + "Q", head[8:16])[0] if big else struct.unpack(e + "I", head[4:8])[0])
    count = struct.unpack(e + ("Q" if big else "H"), f.read(8 if big else 2))[0]
    size = 20 if big else 12
    raw = f.read(count * size)
    tags = {}
    for k in range(count):
        tag, typ, n, value = struct.unpack(e + ("HHQ8s" if big else "HHI4s"), raw[k * size:(k + 1) * size])
        if tag not in (259, 273, 278, 279, 284, 317, 322, 323, 324, 325) or typ not in _TYPES:
            continue
        code, width = _TYPES[typ]
        if n * width <= len(value):
            data = value[:n * width]
        else:
            here = f.tell()
            f.seek(struct.unpack(e + ("Q" if big else "I"), value)[0])
            data = f.read(n * width)
            f.seek(here)
        tags[tag] = struct.unpack(e + code * n, data)
    return tags


class Raster:
    """A one-band 8-bit GeoTIFF, tiled or in strips, uncompressed or deflate (with or without the
    horizontal predictor), read a block at a time. Inflated blocks are kept: the box's CDL is at
    most about 120 MB inflated, and a load reads a few hundred of its 64 KB tiles."""

    def __init__(self, path):
        self.path = path
        head = tif.read_header(path)
        if head.bands != 1 or head.sample_types != ("uint8",):
            raise RasterError(f"{path}: expected one band of 8-bit values, not {head.bands} {head.sample_types}")
        if head.transform is None or head.transform[2] or head.transform[4]:
            raise RasterError(f"{path}: no north-up georeferencing")
        self.epsg, self.width, self.height = head.epsg, head.width, head.height
        self.x0, self.sx, _, self.y0, _, sy = head.transform
        self.sy = -sy
        with open(path, "rb") as f:
            tags = _ifd(f, path)
        self.compression = _COMPRESSION.get(tags.get(259, (1,))[0])
        if self.compression is None:
            raise RasterError(f"{path}: compression {tags[259][0]} isn't read here (none or deflate only)")
        self.predictor = tags.get(317, (1,))[0]
        if self.predictor not in (1, 2):
            raise RasterError(f"{path}: predictor {self.predictor} isn't read here")
        if 322 in tags:
            self.bw, self.bh = tags[322][0], tags[323][0]
            offsets, counts = tags[324], tags[325]
        else:
            self.bw, self.bh = self.width, tags.get(278, (self.height,))[0]
            offsets, counts = tags[273], tags[279]
        self.across = -(-self.width // self.bw)
        if len(offsets) != len(counts) or len(offsets) != self.across * -(-self.height // self.bh):
            raise RasterError(f"{path}: {len(offsets)} blocks for a {self.width} x {self.height} image")
        self.blocks = list(zip(offsets, counts))
        self.cache = {}
        self.file = open(path, "rb")

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _block(self, i):
        data = self.cache.get(i)
        if data is None:
            offset, count = self.blocks[i]
            self.file.seek(offset)
            data = self.file.read(count)
            if self.compression == "deflate":
                data = zlib.decompress(data)
            if self.predictor == 2:
                rows = bytearray(data)
                for r in range(0, len(rows), self.bw):
                    acc = 0
                    for c in range(r, r + self.bw):
                        acc = (acc + rows[c]) & 0xFF
                        rows[c] = acc
                data = bytes(rows)
            self.cache[i] = data
        return data

    def cell(self, x, y):
        """(column, row) of the cell holding (x, y) in the raster's CRS, or None outside it."""
        col, row = math.floor((x - self.x0) / self.sx), math.floor((self.y0 - y) / self.sy)
        if 0 <= col < self.width and 0 <= row < self.height:
            return col, row
        return None

    def at(self, col, row):
        """The value of a cell (None for no data)."""
        i = (row // self.bh) * self.across + col // self.bw
        data = self._block(i)
        k = (row % self.bh) * self.bw + col % self.bw
        if k >= len(data):
            raise RasterError(f"{self.path}: block {i} is cut short")
        v = data[k]
        return None if v == NODATA else v

    def value(self, x, y):
        """The value at (x, y) in the raster's CRS, or None outside it or on no data."""
        c = self.cell(x, y)
        return None if c is None else self.at(*c)


# ---- developed land --------------------------------------------------------

class Developed:
    """Shares of lines and areas on developed land, from a CDL Raster in EPSG:5070."""

    def __init__(self, raster):
        if raster.epsg != EPSG:
            raise RasterError(f"{raster.path}: EPSG:{raster.epsg}, expected the CDL's EPSG:{EPSG}")
        self.raster = raster

    def _share(self, values):
        values = [v for v in values if v is not None]
        if not values:
            return None
        return round(sum(1 for v in values if v in DEVELOPED) / len(values), 3)

    def line_share(self, coords, step=STEP_M):
        """The share of a line's samples (one every `step` metres, the first half a step in; the
        midpoint for a line shorter than that) on developed land; None when none falls on data."""
        pts = [to_albers(lon, lat) for lon, lat in coords]
        lengths = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
        total = sum(lengths)
        if total < step:
            targets = [total / 2]
        else:
            targets = [step / 2 + k * step for k in range(int((total - step / 2) // step) + 1)]
        samples, i, start = [], 0, 0.0
        for t in targets:
            while i < len(lengths) - 1 and start + lengths[i] < t:
                start += lengths[i]
                i += 1
            if not lengths:
                x, y = pts[0]
            else:
                f = (t - start) / lengths[i] if lengths[i] else 0.0
                (ax, ay), (bx, by) = pts[i], pts[i + 1]
                x, y = ax + f * (bx - ax), ay + f * (by - ay)
            samples.append(self.raster.value(x, y))
        return self._share(samples)

    def area_share(self, polygons):
        """The share of the cells whose centres lie inside a MultiPolygon's (GeoJSON coordinates:
        polygons of rings, the first outer, holes after) on developed land; for an area too small
        to hold a cell centre, its outer rings' mean vertex. None when none falls on data."""
        rings = [[to_albers(lon, lat) for lon, lat in ring] for poly in polygons for ring in poly]
        rings = [r for r in rings if len(r) >= 3]
        if not rings:
            return None
        r = self.raster
        xs, ys = [p[0] for ring in rings for p in ring], [p[1] for ring in rings for p in ring]
        c0, c1 = math.floor((min(xs) - r.x0) / r.sx), math.floor((max(xs) - r.x0) / r.sx)
        r0, r1 = math.floor((r.y0 - max(ys)) / r.sy), math.floor((r.y0 - min(ys)) / r.sy)
        values = []
        for row in range(max(r0, 0), min(r1, r.height - 1) + 1):
            y = r.y0 - (row + 0.5) * r.sy
            for col in range(max(c0, 0), min(c1, r.width - 1) + 1):
                if inside(r.x0 + (col + 0.5) * r.sx, y, rings):
                    values.append(r.at(col, row))
        if not values:
            outer = [poly[0] for poly in polygons if poly and len(poly[0]) >= 3]
            pts = [to_albers(lon, lat) for ring in outer for lon, lat in ring[:-1] or ring]
            if not pts:
                return None
            values = [r.value(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))]
        return self._share(values)


def inside(x, y, rings):
    """Whether (x, y) is inside rings (outer rings and holes together), by the even-odd rule."""
    hit = False
    for ring in rings:
        for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
            if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                hit = not hit
    return hit


def area_m2(polygons):
    """A MultiPolygon's area in square metres (GeoJSON coordinates), in the equal-area Albers."""
    total = 0.0
    for poly in polygons:
        for k, ring in enumerate(poly):
            pts = [to_albers(lon, lat) for lon, lat in ring]
            a = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2
            total += a if k == 0 else -a
    return max(total, 0.0)
