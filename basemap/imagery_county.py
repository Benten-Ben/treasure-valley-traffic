#!/usr/bin/env python3
"""Build imagery-detail.pmtiles from NAIP county mosaics: county-wide z15-z17, z18 around points.

The windows come from naip_ccm.py: JPEG GeoTIFFs at 0.3 m (NAIP 2025) with each
county's boundary as their mask. Every zoom-17 tile (512 px, about 0.43 m per
pixel here) that touches a window is rendered from the windows under it, and
kept unless it's fully outside the counties. Zooms 16 and 15 are made by
shrinking the tiles below them. Zoom 18 (about 0.22 m) is rendered only within
--detail-radius of the --detail points (cameras, signals), as imagery.py's
detail layer was. Outside the counties the tiles are transparent, so the
valley-wide layer (imagery.pmtiles, z8-z14) shows through.

It reuses imagery.py's tile math, WebP encoding, shrinking and PMTiles
conversion, and needs the same things: GDAL's Python bindings and the pmtiles
CLI. Nothing is downloaded.

Usage:
  python3 basemap/imagery_county.py --tifs data/naip2025/tifs \\
      --detail data/cameras/cameras.geojson@250 --detail data/imagery/points/compass-signals.geojson@150 \\
      --manifest data/tiles/manifest.json --out data/tiles-new
"""

import argparse
import datetime
import json
import math
import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import imagery as im                     # noqa: E402  tile math, encode, shrink, mbtiles, pmtiles
from osgeo import gdal, osr              # noqa: E402

gdal.UseExceptions()
CACHE = 24                               # open windows kept per worker


# --- the windows -------------------------------------------------------------

def window_bounds(path):
    """A window's bounds in EPSG:3857, from its edges (11 points a side, so the UTM-to-Mercator
    bend can't cut a corner off)."""
    ds = gdal.Open(path)
    gt, w, h = ds.GetGeoTransform(), ds.RasterXSize, ds.RasterYSize
    src = ds.GetSpatialRef()
    merc = osr.SpatialReference()
    merc.ImportFromEPSG(3857)
    for s in (src, merc):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, merc)
    pts = []
    for k in range(11):
        f = k / 10
        for px, py in ((f * w, 0), (f * w, h), (0, f * h), (w, f * h)):
            x, y = gt[0] + px * gt[1] + py * gt[2], gt[3] + px * gt[4] + py * gt[5]
            pts.append(ct.TransformPoint(x, y)[:2])
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def merc_tile_range(b, z):
    """Tiles at zoom z overlapping an EPSG:3857 box (inclusive ranges)."""
    size = im.WORLD / 2 ** z
    x0, x1 = int((b[0] + im.ORIGIN) // size), int((b[2] + im.ORIGIN) // size)
    y0, y1 = int((im.ORIGIN - b[3]) // size), int((im.ORIGIN - b[1]) // size)
    return range(x0, x1 + 1), range(y0, y1 + 1)


# --- rendering -----------------------------------------------------------------

_state = {}


def _init(windows):
    _state.update(windows=windows, open={}, order=[])


def _open(path):
    cache, order = _state["open"], _state["order"]
    if path not in cache:
        if len(order) >= CACHE:
            cache.pop(order.pop(0), None)
        cache[path] = gdal.Open(path)
        order.append(path)
    return cache[path]


def render(job):
    """One tile from the windows under it. The windows' masks (the county boundary) become the
    tile's alpha: RGB where it's all county, RGBA at the edges, nothing outside."""
    layer, z, x, y = job
    b = im.tile_bounds_merc(z, x, y)
    srcs = [_open(p) for p, wb in _state["windows"] if im.overlaps(b, wb)]
    if not srcs:
        return None
    ds = gdal.Warp("", srcs, format="MEM", dstSRS="EPSG:3857", outputBounds=b,
                   width=im.TILE, height=im.TILE, resampleAlg="cubic", dstAlpha=True, multithread=False)
    lo, hi = ds.GetRasterBand(4).ComputeRasterMinMax(False)
    if hi == 0:
        return None
    if lo == 255:
        ds = gdal.Translate("", ds, format="MEM", bandList=[1, 2, 3])
    return layer, z, x, y, im.encode(ds)


# --- main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tifs", required=True, help="folder of naip_ccm.py windows")
    ap.add_argument("--detail", action="append", default=[], metavar="GEOJSON[@METERS]",
                    help="points to add zoom 18 around, optionally with their own radius; repeatable")
    ap.add_argument("--detail-radius", type=float, default=250.0)
    ap.add_argument("--minzoom", type=int, default=15)
    ap.add_argument("--maxzoom", type=int, default=17, help="top zoom everywhere in the counties")
    ap.add_argument("--detail-maxzoom", type=int, default=18, help="top zoom around the points")
    ap.add_argument("--manifest", required=True, help="the manifest.json to update (copied to --out)")
    ap.add_argument("--source", default="NAIP 2025 (0.3 m), USDA NRCS county mosaics")
    ap.add_argument("--out", required=True, help="folder for imagery-detail.pmtiles and manifest.json")
    ap.add_argument("--work", default="data/imagery")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--keep-mbtiles", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    t0 = time.time()

    # Windows and their bounds
    paths = sorted(os.path.join(args.tifs, f) for f in os.listdir(args.tifs) if f.endswith(".tif"))
    if not paths:
        sys.exit(f"no windows in {args.tifs}")
    with multiprocessing.Pool(args.workers) as pool:
        windows = list(zip(paths, pool.map(window_bounds, paths, chunksize=8)))
    print(f"windows: {len(windows)} in {time.time() - t0:.0f} s", flush=True)

    # Tiles: every top-zoom tile touching a window; z18 within the detail radius of each point
    top = set()
    for _p, wb in windows:
        xr, yr = merc_tile_range(wb, args.maxzoom)
        top |= {("detail", args.maxzoom, x, y) for x in xr for y in yr}
    deep, sets = set(), []
    for spec in args.detail:
        path, _, radius = spec.partition("@")
        radius = float(radius) if radius else args.detail_radius
        pts = [f["geometry"]["coordinates"][:2] for f in json.load(open(path))["features"] if f.get("geometry")]
        sets.append({"file": os.path.basename(path), "points": len(pts), "radius": radius})
        for lon, lat in pts:
            for z in range(args.maxzoom + 1, args.detail_maxzoom + 1):
                xr, yr = im.tile_range(im.around(lon, lat, radius), z)
                deep |= {("detail", z, x, y) for x in xr for y in yr}
        print(f"detail: {len(pts)} points from {path}, {radius:.0f} m radius", flush=True)
    sw = im.merc_to_lonlat(min(wb[0] for _p, wb in windows), min(wb[1] for _p, wb in windows))
    ne = im.merc_to_lonlat(max(wb[2] for _p, wb in windows), max(wb[3] for _p, wb in windows))
    bounds = (round(sw[0], 5), round(sw[1], 5), round(ne[0], 5), round(ne[1], 5))
    print(f"tiles: {len(top)} at z{args.maxzoom} to try, {len(deep)} at z{args.maxzoom + 1}-"
          f"{args.detail_maxzoom} around points; bounds {bounds}", flush=True)

    mb = os.path.join(args.work, "imagery-detail.mbtiles")
    db = im.new_mbtiles(mb, "imagery-detail", bounds, args.minzoom, args.detail_maxzoom)
    n_bytes, n_tiles = 0, 0

    def store(r):
        nonlocal n_bytes, n_tiles
        if r:
            _layer, z, x, y, data = r
            n_bytes += len(data)
            n_tiles += 1
            db.execute("insert or replace into tiles values (?, ?, ?, ?)", (z, x, 2 ** z - 1 - y, data))

    # Render the top zoom in x, y order (neighbors share windows), then the points' deeper zooms
    jobs = sorted(top, key=lambda j: (j[2] // 8, j[3], j[2])) + sorted(deep)
    t1 = time.time()
    with multiprocessing.Pool(args.workers, initializer=_init, initargs=(windows,)) as pool:
        for done, r in enumerate(pool.imap_unordered(render, jobs, chunksize=16), start=1):
            store(r)
            if done % 2000 == 0 or done == len(jobs):
                db.commit()
                rate = done / max(1e-9, time.time() - t1)
                print(f"  {done}/{len(jobs)} tried, {n_tiles} kept, {n_bytes / 1e9:.2f} GB, "
                      f"{rate:.0f}/s, about {(len(jobs) - done) / max(rate, 1e-9) / 60:.0f} min left", flush=True)
        # Shrink: each zoom from the one below, in batches. The children are read here, in the
        # main thread: the SQLite connection belongs to it, and a whole zoom's worth of tiles
        # wouldn't fit in memory.
        for z in range(args.maxzoom - 1, args.minzoom - 1, -1):
            shift = args.maxzoom - z
            parents = sorted({(x >> shift, y >> shift) for (_l, _z, x, y) in top})
            before = n_tiles
            for i in range(0, len(parents), 2000):
                batch = [("detail", z, x, y, im.children(db, z, x, y)) for x, y in parents[i:i + 2000]]
                for r in pool.imap_unordered(im.shrink, batch, chunksize=8):
                    store(r)
                db.commit()
            print(f"  z{z}: {n_tiles - before} tiles made from z{z + 1}", flush=True)
    db.close()
    print(f"render: {n_tiles} tiles, {n_bytes / 1e9:.2f} GB in {time.time() - t1:.0f} s", flush=True)

    # PMTiles and manifest
    pm = os.path.join(args.out, "imagery-detail.pmtiles")
    size = im.to_pmtiles(mb, pm)
    if not args.keep_mbtiles:
        os.remove(mb)
    m = json.load(open(args.manifest))
    if "imagery" not in m:
        sys.exit("the manifest has no imagery entry; build the valley layer (imagery.py) first")
    m["imagery"]["detail"] = {
        "file": "imagery-detail.pmtiles", "minzoom": args.minzoom, "maxzoom": args.detail_maxzoom,
        "countyMaxzoom": args.maxzoom, "points": sum(s["points"] for s in sets),
        "radius": max((s["radius"] for s in sets), default=0), "sets": sets, "bounds": list(bounds),
        "built": datetime.date.today().isoformat(),
        "source": f"{args.source}; z{args.minzoom}-z{args.maxzoom} across the counties, "
                  f"z{args.maxzoom + 1}-z{args.detail_maxzoom} around the points"}
    json.dump(m, open(os.path.join(args.out, "manifest.json"), "w"), indent=1)
    print(f"wrote {pm} ({size / 1e9:.2f} GB) and manifest.json in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
