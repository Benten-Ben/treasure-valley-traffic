"""The ground's grid (C5): one grid for every raster the ground reads or writes. Standard library only.

EPSG:32611 (WGS 84 / UTM 11N) on Sentinel-2's own 10 m pixel edges, cut to the map box: the upper-left corner is
E 495920, N 4855750, and the grid is 8,967 x 9,494 cells of 10 m (E 495920-585590, N 4760810-4855750). The July 2025
NDVI layer and farm's crop_cover.tif are on it at 10 m. The painter's 2 m grid and the class boxes' 0.5 m grid are
exact sub-grids with the same origin (5 and 20 cells to a 10 m cell), so a window on one level is a window on the
others with no resampling and no half-cell drift. The numbers live in spec.json; test_grid.py rebuilds them from the
map box.

Rows count down from the north edge, columns east from the west edge, as in a GDAL raster. A Window is a block of
cells on one level, with its GDAL geotransform; windows() walks a level in blocks, each with a halo for work that
looks past its edges (buffers, feathers), and every window has a stable key so long jobs can resume.

**Datum policy.** Inputs in NAD83 (NAIP, 3DEP and the lidar products are EPSG:26911 or 6340; CDL is NAD83 Albers)
are read with the null datum shift: their coordinates are taken as WGS 84's, as web maps and OpenStreetMap's tracing
imagery do, so OSM, Overture, NAIP and the lidar keep the agreement they were traced or measured with (the true
NAD83(2011)-to-WGS 84 offset here is about 1 m, under the painter's 2 m cell). Never let PROJ pick a grid-based
NAD83-to-WGS 84 transform: with PROJ's network on (conda's default, which the worker image now turns off), PROJ tries
to fetch the grid, and offline that transform returns inf or fails (checked Oct 10 in tvt-worker).
rasterize.py applies the policy for vectors and rasters.

    python3 basemap/ground/ground.py spec      # sizes per level, the boxes, tile counts
"""

import json
import math
import os
from dataclasses import dataclass
from functools import lru_cache

from ingest.utm import from_utm, to_utm

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec.json")


@lru_cache(maxsize=1)
def spec():
    """spec.json, parsed (the contract's numbers)."""
    with open(SPEC_PATH, encoding="utf-8") as f:
        return json.load(f)


_G = spec()["grid"]
CRS = _G["crs"]                                   # "EPSG:32611"
EPSG = int(CRS.split(":")[1])
ORIGIN_X, ORIGIN_Y = _G["origin"]                 # upper-left corner, metres
BASE_RES = _G["res"]                              # 10 m
COLS, ROWS = _G["size"]                           # at 10 m
WEST, NORTH = ORIGIN_X, ORIGIN_Y
EAST, SOUTH = ORIGIN_X + COLS * BASE_RES, ORIGIN_Y - ROWS * BASE_RES
EXTENT = (WEST, SOUTH, EAST, NORTH)
LEVELS = {k: float(v) for k, v in _G["levels"].items()}   # sentinel2 10, painter 2, classes 0.5
MAP_LONLAT = tuple(_G["lonlat"])

# Projected CRSs whose coordinates are the grid's own under the null datum shift (see the module docstring).
NULL_SHIFT_EPSG = {26911: "NAD83 / UTM zone 11N", 3740: "NAD83(HARN) / UTM zone 11N",
                   6340: "NAD83(2011) / UTM zone 11N"}

_EPS = 1e-6   # cells: coordinates closer than this to a grid line count as on it


def same_coordinates(epsg):
    """True when a CRS's coordinates are the grid's, as they are (32611) or under the null datum shift."""
    return int(epsg) == EPSG or int(epsg) in NULL_SHIFT_EPSG


def check_res(res):
    """A resolution the grid has a level for: a whole number of cells to 10 m (10, 5, 2, 1, 0.5, ...) or a whole
    number of 10 m cells (20, 30, ...). Returns it as a float; raises ValueError otherwise."""
    r = float(res)
    if r <= 0:
        raise ValueError(f"resolution {res!r} must be positive")
    per = BASE_RES / r
    if abs(per - round(per)) < 1e-9 or abs(r / BASE_RES - round(r / BASE_RES)) < 1e-9:
        return r
    raise ValueError(f"{res} m isn't a level of the ground grid (it must divide 10 m, or be a multiple of it)")


def _floor(v):
    return math.floor(v + _EPS)


def _ceil(v):
    return math.ceil(v - _EPS)


def _whole(v):
    return abs(v - round(v)) < _EPS


@dataclass(frozen=True)
class Window:
    """A block of cells on one level of the grid. col and row count from the grid's west and north edges and may be
    negative or run past its far edges (a halo can reach outside the grid)."""
    res: float
    col: int
    row: int
    width: int
    height: int

    @property
    def west(self):
        return ORIGIN_X + self.col * self.res

    @property
    def north(self):
        return ORIGIN_Y - self.row * self.res

    @property
    def east(self):
        return ORIGIN_X + (self.col + self.width) * self.res

    @property
    def south(self):
        return ORIGIN_Y - (self.row + self.height) * self.res

    @property
    def bounds(self):
        """(west, south, east, north) in metres."""
        return self.west, self.south, self.east, self.north

    @property
    def transform(self):
        """GDAL geotransform (rasterio: Affine.from_gdal(*w.transform))."""
        return (self.west, self.res, 0.0, self.north, 0.0, -self.res)

    @property
    def shape(self):
        """(rows, columns), NumPy order."""
        return self.height, self.width

    crs = CRS

    @property
    def key(self):
        """Stable name for resumable jobs, e.g. '2m-r1024-c2048-2048x2048'."""
        return f"{self.res:g}m-r{self.row}-c{self.col}-{self.width}x{self.height}"

    def pad(self, cells):
        """The window grown by `cells` on every side."""
        return Window(self.res, self.col - cells, self.row - cells, self.width + 2 * cells, self.height + 2 * cells)

    def pad_m(self, metres):
        """The window grown by at least `metres` on every side (whole cells)."""
        return self.pad(_ceil(metres / self.res)) if metres > 0 else self

    def inner(self, outer):
        """(row slice, column slice) that cut this window out of an array covering `outer` (same level)."""
        if outer.res != self.res:
            raise ValueError("windows on different levels")
        r, c = self.row - outer.row, self.col - outer.col
        if r < 0 or c < 0 or r + self.height > outer.height or c + self.width > outer.width:
            raise ValueError(f"{self.key} isn't inside {outer.key}")
        return slice(r, r + self.height), slice(c, c + self.width)

    def at(self, res):
        """The same area on another level. Exact when this window's edges are on that level's grid (always from a
        coarser level to a finer one); otherwise widened outward to whole cells."""
        return window(self.bounds, res, snap="out")

    def clip(self):
        """The part inside the grid's extent, or None."""
        cols, rows = size(self.res)
        c0, r0 = max(self.col, 0), max(self.row, 0)
        c1, r1 = min(self.col + self.width, cols), min(self.row + self.height, rows)
        if c1 <= c0 or r1 <= r0:
            return None
        return Window(self.res, c0, r0, c1 - c0, r1 - r0)


def size(res):
    """(columns, rows) of the whole grid at a level. Coarser levels round up, so they still cover it."""
    r = check_res(res)
    return _ceil(COLS * BASE_RES / r), _ceil(ROWS * BASE_RES / r)


def full(res):
    """The whole grid at a level."""
    cols, rows = size(res)
    return Window(check_res(res), 0, 0, cols, rows)


def window(bounds, res, snap="out"):
    """The window covering bounds (west, south, east, north; metres). snap: "out" widens to whole cells, "in" keeps
    only whole cells inside, "exact" raises ValueError unless every edge is on the grid."""
    r = check_res(res)
    w, s, e, n = bounds
    if not (e > w and n > s):
        raise ValueError(f"empty bounds {bounds}")
    fc, fr = (w - ORIGIN_X) / r, (ORIGIN_Y - n) / r
    lc, lr = (e - ORIGIN_X) / r, (ORIGIN_Y - s) / r
    if snap == "exact":
        if not all(_whole(v) for v in (fc, fr, lc, lr)):
            raise ValueError(f"bounds {bounds} aren't on the {r:g} m grid")
        c0, r0, c1, r1 = round(fc), round(fr), round(lc), round(lr)
    elif snap == "out":
        c0, r0, c1, r1 = _floor(fc), _floor(fr), _ceil(lc), _ceil(lr)
    elif snap == "in":
        c0, r0, c1, r1 = _ceil(fc), _ceil(fr), _floor(lc), _floor(lr)
    else:
        raise ValueError(f"snap must be out, in or exact, not {snap!r}")
    if c1 <= c0 or r1 <= r0:
        raise ValueError(f"bounds {bounds} hold no whole {r:g} m cell")
    return Window(r, c0, r0, c1 - c0, r1 - r0)


def windows(res, size_cells=2048, bounds=None, halo_m=0.0):
    """Walk a level in blocks of size_cells x size_cells (smaller at the far edges), north to south, west to east.
    Yields (core, padded): core tiles the grid (or the part of it covering `bounds`) with no overlap; padded is core
    grown by halo_m, so a buffer or feather of up to halo_m computed on padded and cut back to core (core.inner(padded))
    is the same as one computed on the whole grid."""
    area = full(res) if bounds is None else window(bounds, res).clip()
    if area is None:
        return
    for r in range(area.row, area.row + area.height, size_cells):
        for c in range(area.col, area.col + area.width, size_cells):
            core = Window(area.res, c, r, min(size_cells, area.col + area.width - c),
                          min(size_cells, area.row + area.height - r))
            yield core, core.pad_m(halo_m)


def aligned(transform, res=None):
    """True when a GDAL geotransform is north-up on the grid: square cells of `res` (or of any level when res is
    None), with its corner on that level's cell edges."""
    x0, rx, rot1, y0, rot2, ry = transform
    if rot1 or rot2 or ry >= 0 or abs(rx + ry) > 1e-9 * abs(rx):
        return False
    try:
        r = check_res(rx if res is None else res)
    except ValueError:
        return False
    if abs(rx - r) > 1e-9 * r:
        return False
    return _whole((x0 - ORIGIN_X) / r) and _whole((ORIGIN_Y - y0) / r)


def envelope(lonlat, densify=64):
    """The grid-metre envelope (west, south, east, north) of a lon/lat box, with each edge densified, since the
    box's straight edges curve in UTM."""
    w, s, e, n = lonlat
    xs, ys = [], []
    for i in range(densify + 1):
        t = i / densify
        for lon, lat in ((w + (e - w) * t, s), (w + (e - w) * t, n), (w, s + (n - s) * t), (e, s + (n - s) * t)):
            x, y = to_utm(lon, lat)
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def lonlat_of(bounds, densify=16):
    """The lon/lat envelope (west, south, east, north) of a box in grid metres."""
    w, s, e, n = bounds
    lons, lats = [], []
    for i in range(densify + 1):
        t = i / densify
        for x, y in ((w + (e - w) * t, s), (w + (e - w) * t, n), (w, s + (n - s) * t), (e, s + (n - s) * t)):
            lon, lat = from_utm(x, y)
            lons.append(lon)
            lats.append(lat)
    return min(lons), min(lats), max(lons), max(lats)


def snap_out(bounds, step):
    """bounds widened to multiples of step metres (relative to the grid origin, which is on every level)."""
    w, s, e, n = bounds
    return (ORIGIN_X + _floor((w - ORIGIN_X) / step) * step, ORIGIN_Y - _ceil((ORIGIN_Y - s) / step) * step,
            ORIGIN_X + _ceil((e - ORIGIN_X) / step) * step, ORIGIN_Y - _floor((ORIGIN_Y - n) / step) * step)


@dataclass(frozen=True)
class Box:
    """One of the ten land-cover test boxes, where the ground paints its 0.5 m classes."""
    id: str
    name: str
    county: str
    lonlat: tuple
    utm: tuple

    def window(self, res=None):
        """The box on a level (default: the class grid, where it is exact)."""
        return window(self.utm, LEVELS["classes"] if res is None else res, snap="out")


@lru_cache(maxsize=1)
def boxes():
    """The ten boxes, in spec order (a-f, downtown, h-j)."""
    return tuple(Box(b["id"], b["name"], b["county"], tuple(b["lonlat"]) if b["lonlat"] else None, tuple(b["utm"]))
                 for b in spec()["boxes"])


def box(box_id):
    for b in boxes():
        if b.id == box_id:
            return b
    raise KeyError(f"no box {box_id!r} (boxes: {', '.join(b.id for b in boxes())})")
