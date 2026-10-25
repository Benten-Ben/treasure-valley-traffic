#!/usr/bin/env python3
"""The map's own terrain as a GeoTIFF on the ground's grid: the DEM for the painter's `--dem` (G1b).

The map draws its 3D terrain from `terrain.pmtiles` (served tiles, Mapbox terrain-RGB, height = -10000 + value x 0.1 m,
512 px, 3DEP, z14 at about 3.5 m in the Valley). The photo's light is normalised for the slope and aspect of that same
surface, so the paint and the 3D map agree on where the ground faces the sun. Nothing is downloaded: the tiles are
files we already hold.

    python basemap/ground/dem.py build --terrain terrain.pmtiles --out DEM.tif [--limit N]
    python basemap/ground/dem.py check DEM.tif
    python basemap/ground/dem.py slopes DEM.tif [--cuts 15,30]

`build` reads the PMTiles file's highest zoom (z14) and warps it, bilinear, onto the **painter's 2 m grid** (EPSG:32611,
the same origin and cell edges as the 2 m NAIP COG), a block at a time: each block's z14 tiles are laid side by side in
Web Mercator, so a block never sees a seam between tiles, and a block's halo is read from its neighbours' tiles. The
file is Float32 metres, nodata NaN (a missing tile, or outside the file's coverage), tiled and deflated, with a sidecar
`DEM.tif.json` (the source's sha256 and zoom, the grid, the version) that the run's digest can name. It is written to
`DEM.tif.part` and renamed at the end, so a stopped build leaves nothing that looks finished.

Needs GDAL, NumPy and Pillow (the worker image). It reads only the file it is given.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
from io import BytesIO

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402
from osgeo import gdal, osr  # noqa: E402
from PIL import Image  # noqa: E402

from basemap.ground import grid, rasterize as R  # noqa: E402
from basemap.ground import texture as TX  # noqa: E402
from basemap.landscape import pmtiles as P  # noqa: E402

gdal.UseExceptions()

DEM_VERSION = "dem-1"
RES = grid.LEVELS["painter"]                  # 2 m: the painter's own cells
BLOCK = 4096                                   # cells a block writes (8.2 km); its tiles are about 25
HALO_M = 16.0                                  # beyond a block, so bilinear never reads past the mosaic
UNIT, BASE = 0.1, -10000.0                    # Mapbox terrain-RGB
TILE_PX = 512
WEBMERC = 20037508.342789244                  # half the world, metres
NODATA = float("nan")
CREATE = ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=DEFLATE", "PREDICTOR=3", "ZLEVEL=3",
          "BIGTIFF=YES", "NUM_THREADS=1"]


class DemError(ValueError):
    pass


# --- the tiles -------------------------------------------------------------------------------------------------

def decode_tile(data):
    """PNG or WebP terrain-RGB bytes -> (512, 512) float32 metres. Raises DemError on anything else."""
    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception as e:                                          # Pillow raises many kinds
        raise DemError(f"a terrain tile doesn't decode: {e}") from e
    if im.size != (TILE_PX, TILE_PX):
        raise DemError(f"a terrain tile is {im.size[0]} x {im.size[1]} px, not {TILE_PX}")
    a = np.asarray(im.convert("RGB"), dtype=np.uint32)
    return (((a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]).astype(np.float64) * UNIT + BASE).astype(np.float32)


class Terrain:
    """A terrain-RGB PMTiles file: its tile index (read once) and its tiles at one zoom."""

    def __init__(self, path, zoom=None):
        self.path = path
        self.header = P.read_header(path)
        meta = P.read_metadata(path)
        if self.header.tile_type_name not in ("png", "webp"):
            raise DemError(f"{path}: tiles are {self.header.tile_type_name}, not PNG or WebP terrain-RGB")
        if str(meta.get("encoding", "mapbox")).lower() != "mapbox":
            raise DemError(f"{path}: encoding {meta.get('encoding')!r}; only Mapbox terrain-RGB is read")
        self.zoom = int(self.header.max_zoom if zoom is None else zoom)
        if not self.header.min_zoom <= self.zoom <= self.header.max_zoom:
            raise DemError(f"{path}: z{self.zoom} is outside its z{self.header.min_zoom}-{self.header.max_zoom}")
        lo, hi = P._first_id(self.zoom), P._first_id(self.zoom + 1)
        self.index = {}
        for e in P.entries(path):
            for tid in range(max(e.tile_id, lo), min(e.tile_id + e.run_length, hi)):
                self.index[tid] = (e.offset, e.length)
        if not self.index:
            raise DemError(f"{path}: no tiles at z{self.zoom}")
        self._f = None

    @property
    def pixel_m(self):
        """A tile pixel's width in Web Mercator metres at this zoom (ground metres at 43.4 N are 0.725 of it)."""
        return 2 * WEBMERC / (TILE_PX * (1 << self.zoom))

    def tile(self, x, y):
        """(512, 512) float32 metres, or None when the file has no such tile."""
        hit = self.index.get(P.tile_id(self.zoom, x, y))
        if hit is None:
            return None
        if self._f is None:
            self._f = open(self.path, "rb")
        raw = P._read(self._f, self.header.data_offset + hit[0], hit[1])
        return decode_tile(P._decompress(raw, self.header.tile_compression))

    def close(self):
        if self._f:
            self._f.close()
            self._f = None

    def mosaic(self, west, south, east, north):
        """The tiles that cover a Web Mercator box, side by side: (array, geotransform, tiles found, tiles wanted).
        A tile the file lacks is NaN."""
        n = 1 << self.zoom
        size = 2 * WEBMERC / n
        x0 = max(0, int(math.floor((west + WEBMERC) / size)))
        x1 = min(n - 1, int(math.floor((east + WEBMERC) / size)))
        y0 = max(0, int(math.floor((WEBMERC - north) / size)))
        y1 = min(n - 1, int(math.floor((WEBMERC - south) / size)))
        if x1 < x0 or y1 < y0:
            return None, None, 0, 0
        out = np.full(((y1 - y0 + 1) * TILE_PX, (x1 - x0 + 1) * TILE_PX), np.nan, np.float32)
        found = 0
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                t = self.tile(x, y)
                if t is not None:
                    out[(y - y0) * TILE_PX:(y - y0 + 1) * TILE_PX, (x - x0) * TILE_PX:(x - x0 + 1) * TILE_PX] = t
                    found += 1
        gt = (-WEBMERC + x0 * size, size / TILE_PX, 0.0, WEBMERC - y0 * size, 0.0, -size / TILE_PX)
        return out, gt, found, (x1 - x0 + 1) * (y1 - y0 + 1)


# --- the grid --------------------------------------------------------------------------------------------------

def _mem(arr, gt, srs):
    ds = gdal.GetDriverByName("MEM").Create("", arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32)
    ds.SetGeoTransform(gt)
    ds.SetProjection(srs.ExportToWkt())
    b = ds.GetRasterBand(1)
    b.SetNoDataValue(NODATA)
    b.WriteArray(arr)
    return ds


def _utm_to_mercator(bounds):
    """A UTM 11N box as the Web Mercator box that surely covers it (its corners and edge midpoints)."""
    ct = osr.CoordinateTransformation(R.srs_of(grid.CRS), R.srs_of("EPSG:3857"))
    w, s, e, n = bounds
    pts = [(x, y) for x in (w, (w + e) / 2, e) for y in (s, (s + n) / 2, n)]
    xy = [ct.TransformPoint(x, y)[:2] for x, y in pts]
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    return min(xs), min(ys), max(xs), max(ys)


def block(terrain, win):
    """The terrain on the 2 m window `win`: (float32 array, tiles found, tiles wanted). NaN where the file has none."""
    padded = win.pad_m(HALO_M)
    box = _utm_to_mercator(padded.bounds)
    pad = 2 * terrain.pixel_m                       # a couple of source pixels, for the resampler's reach
    mos, gt, found, wanted = terrain.mosaic(box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    if mos is None or not found:
        return np.full(win.shape, np.nan, np.float32), 0, wanted
    merc = R.srs_of("EPSG:3857")
    src = _mem(mos, gt, merc)
    out = gdal.Warp("", src, format="MEM", outputBounds=win.bounds, width=win.width, height=win.height,
                    srcSRS=merc.ExportToWkt(), dstSRS=R.srs_of(grid.CRS).ExportToWkt(), resampleAlg="bilinear",
                    outputType=gdal.GDT_Float32, srcNodata=NODATA, dstNodata=NODATA)
    arr = out.GetRasterBand(1).ReadAsArray().astype(np.float32)
    return arr, found, wanted


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                return h.hexdigest()
            h.update(b)


def sidecar_path(out):
    return out + ".json"


def build(terrain_path, out, window=None, size=BLOCK, zoom=None, limit=None, log=print):
    """Write the DEM to `out` (and `out`.json). window: a grid.Window on the 2 m level (default: the whole map box).
    limit: stop after this many blocks (the file is then left as `out`.part, unfinished). Returns the sidecar dict."""
    if os.path.exists(out):
        raise DemError(f"{out} exists; a DEM is never overwritten (choose a new name)")
    t = Terrain(terrain_path, zoom)
    win = window or grid.full(RES)
    if abs(win.res - RES) > 1e-9:
        raise DemError(f"the DEM is on the 2 m level, not {win.res:g} m")
    part = out + ".part"
    if os.path.exists(part):
        os.remove(part)
    ds = gdal.GetDriverByName("GTiff").Create(part, win.width, win.height, 1, gdal.GDT_Float32, CREATE)
    ds.SetGeoTransform(win.transform)
    ds.SetProjection(R.srs_of(grid.CRS).ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    begun = time.time()
    done = found = wanted = finite = cells = 0
    lo, hi = math.inf, -math.inf
    blocks = [(r, c) for r in range(0, win.height, size) for c in range(0, win.width, size)]
    for r, c in blocks:
        w = grid.Window(RES, win.col + c, win.row + r, min(size, win.width - c), min(size, win.height - r))
        arr, f, n = block(t, w)
        band.WriteArray(arr, c, r)
        done += 1
        found, wanted = found + f, wanted + n
        fin = np.isfinite(arr)
        finite, cells = finite + int(fin.sum()), cells + fin.size
        if fin.any():
            lo, hi = min(lo, float(arr[fin].min())), max(hi, float(arr[fin].max()))
        if done % 10 == 0 or done == len(blocks):
            log(f"  {done}/{len(blocks)} blocks, {time.time() - begun:.0f} s")
        if limit and done >= limit and done < len(blocks):
            band.FlushCache()
            ds = None
            t.close()
            log(f"stopped after {done} of {len(blocks)} blocks; {part} is unfinished")
            return None
    band.FlushCache()
    ds = None
    t.close()
    os.replace(part, out)
    info = {
        "schema": "ground.dem/1", "version": DEM_VERSION,
        "source": {"file": os.path.basename(terrain_path), "sha256": sha256(terrain_path), "zoom": t.zoom,
                   "encoding": "mapbox terrain-RGB", "pixel_m_at_43n": round(t.pixel_m * math.cos(math.radians(43.4)), 2)},
        "grid": {"crs": grid.CRS, "res": RES, "west": win.west, "north": win.north, "width": win.width,
                 "height": win.height},
        "resampling": "bilinear, from the tiles laid side by side in Web Mercator",
        "unit": "metres", "nodata": "NaN",
        "blocks": done, "tiles_read": found, "tiles_wanted": wanted,
        "finite_share": round(finite / cells, 6) if cells else 0.0,
        "min_m": None if lo == math.inf else round(lo, 1), "max_m": None if hi == -math.inf else round(hi, 1),
        "bytes": os.path.getsize(out), "sha256": sha256(out),
        "seconds": round(time.time() - begun),
    }
    with open(sidecar_path(out) + ".part", "w") as f:
        json.dump(info, f, indent=1)
        f.write("\n")
    os.replace(sidecar_path(out) + ".part", sidecar_path(out))
    return info


def _open(path):
    try:
        return gdal.Open(path)
    except RuntimeError as e:                                    # GDAL's exceptions are on: a missing or non-raster file
        raise DemError(f"{path}: not a raster GDAL can open ({e})")


def check(path):
    """Is `path` a DEM the painter can use? Returns the problems found (an empty list: it can)."""
    problems = []
    ds = _open(path)
    gt = ds.GetGeoTransform()
    if ds.RasterCount != 1:
        problems.append(f"{ds.RasterCount} bands, not 1")
    if ds.GetRasterBand(1).DataType != gdal.GDT_Float32:
        problems.append("not Float32")
    if abs(gt[1] - RES) > 1e-9 or abs(gt[5] + RES) > 1e-9:
        problems.append(f"cells are {gt[1]:g} m, not {RES:g}")
    elif not grid.aligned(gt, RES):
        problems.append("not on the ground's grid")
    srs = osr.SpatialReference(wkt=ds.GetProjection())
    if srs.GetAuthorityCode(None) != str(grid.EPSG):
        problems.append(f"CRS {srs.GetAuthorityCode(None)}, not {grid.EPSG}")
    return problems


def _slope_block(ds, col, row, width, height):
    """The slope (degrees, NaN where unknown) of the window (col, row, width, height) of the DEM, from a one-cell halo
    (the painter takes its slope from a bigger one; this is for counting)."""
    c0, r0 = max(col - 1, 0), max(row - 1, 0)
    c1, r1 = min(col + width + 1, ds.RasterXSize), min(row + height + 1, ds.RasterYSize)
    z = ds.GetRasterBand(1).ReadAsArray(c0, r0, c1 - c0, r1 - r0).astype(np.float64)
    deg = np.degrees(TX.slope_aspect(z, RES)[0])
    return deg[row - r0:row - r0 + height, col - c0:col - c0 + width]


def slope_shares(path, cuts=(15.0, 30.0), size=BLOCK):
    """The share of known cells steeper than each cut (degrees), over the whole DEM and in each of the ten boxes:
    {"valley": {"cells": n, "over": {15: share, ...}}, "a": {...}, ..., "skipped_boxes": [ids not wholly inside the DEM]}.
    Refuses (DemError) a file `check` would not accept. For judging the photo variation's slope cut."""
    problems = check(path)
    if problems:
        raise DemError(f"{path}: not usable ({'; '.join(problems)})")
    ds = _open(path)

    def count(windows):
        n, over = 0, {c: 0 for c in cuts}
        for col, row, w, h in windows:
            deg = _slope_block(ds, col, row, w, h)
            fin = np.isfinite(deg)
            n += int(fin.sum())
            for c in cuts:
                over[c] += int((deg[fin] > c).sum())
        return {"cells": n, "over": {c: round(over[c] / n, 5) if n else None for c in cuts}}

    out = {"valley": count([(c, r, min(size, ds.RasterXSize - c), min(size, ds.RasterYSize - r))
                            for r in range(0, ds.RasterYSize, size) for c in range(0, ds.RasterXSize, size)])}
    gt = ds.GetGeoTransform()
    out["skipped_boxes"] = []
    for b in grid.boxes():
        w = b.window(RES)
        c, r = int(round((w.west - gt[0]) / RES)), int(round((gt[3] - w.north) / RES))
        if c >= 0 and r >= 0 and c + w.width <= ds.RasterXSize and r + w.height <= ds.RasterYSize:
            out[b.id] = count([(c, r, w.width, w.height)])
        else:
            out["skipped_boxes"].append(b.id)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="decode terrain.pmtiles onto the painter's 2 m grid")
    b.add_argument("--terrain", required=True, help="terrain.pmtiles (Mapbox terrain-RGB)")
    b.add_argument("--out", required=True, help="the GeoTIFF to write (a new file)")
    b.add_argument("--zoom", type=int, help="the tiles' zoom (default: the file's highest)")
    b.add_argument("--limit", type=int, help="stop after this many blocks (a test)")
    c = sub.add_parser("check", help="is a file a DEM the painter can use?")
    c.add_argument("dem")
    s = sub.add_parser("slopes", help="the share of cells over each slope cut, valley-wide and in the ten boxes")
    s.add_argument("dem")
    s.add_argument("--cuts", default="15,30", help="degrees, comma-separated")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "slopes":
            print(json.dumps(slope_shares(a.dem, tuple(float(x) for x in a.cuts.split(","))), indent=1))
            return 0
        if a.cmd == "build":
            info = build(a.terrain, a.out, zoom=a.zoom, limit=a.limit)
            if info:
                print(json.dumps(info, indent=1))
            return 0 if info else 1
        problems = check(a.dem)
        for p in problems:
            print("DEM:", p)
        print("ok" if not problems else "not usable")
        return 1 if problems else 0
    except DemError as e:
        print("dem:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
