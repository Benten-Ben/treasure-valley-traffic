#!/usr/bin/env python3
"""Build terrain-RGB tiles (terrain.pmtiles) for the valley from USGS 3DEP elevation.

  1. Sources: 3DEP 1 m DEM tiles from The National Map (TNM Access API),
     stacked oldest project first so the newest survey wins where they
     overlap. Underneath sits a ring of the 1/3 arc-second (~10 m) 3DEP DEM,
     so the terrain doesn't drop off a cliff at the edge of the 1 m data.
     For the zoomed-out view there's a wide layer from the 1 arc-second
     (~30 m) DEM, covering the whole --minzoom tile around the valley.
  2. Prefetch, 8 at a time: the 2 m level of each 1 m COG (a quarter of the
     bytes), just the needed part of each ring tile, and the ~60 m level of
     each wide tile, to local disk.
  3. Warp: one float32 elevation raster in Web Mercator, aligned to the
     512-px tile grid at the top zoom; and a wide one at z10's resolution,
     with the fine raster averaged in on top.
  4. Tiles: Mapbox terrain-RGB encoding (0.1 m steps), 512-px PNG tiles,
     written to MBTiles and converted with `pmtiles convert`. Zooms up to
     z10 come from the wide raster; above that, the fine raster, with its
     edges filled from the wide one instead of smeared outward.
  5. Manifest: adds a "terrain" entry to manifest.json for the app.

All sources are public domain (USGS). Needs GDAL's Python bindings, numpy
and the pmtiles CLI. On Ubuntu, run it with the system Python that matches
the python3-gdal package (here: python3.12).

Usage:
  python3.12 basemap/terrain.py                     # full valley -> data/tiles/terrain.pmtiles
  python3.12 basemap/terrain.py --bbox=-116.37,43.61,-116.34,43.63 --pad 0 \
      --out /tmp/terrain-test                       # quick test on a small area
"""

import argparse
import datetime
import json
import math
import multiprocessing
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from osgeo import gdal

gdal.UseExceptions()

USER_AGENT = ("treasure-valley-traffic/0.2 "
              "(public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)")
TNM = "https://tnmaccess.nationalmap.gov/api/v1/products"
RING = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/{t}/USGS_13_{t}.tif"
WIDE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/1/TIFF/current/{t}/USGS_1_{t}.tif"
WIDE_MAXZOOM = 10        # zooms up to this come from the wide raster (z10 is ~55 m per pixel here)
NODATA = -999999.0
# Oldest first: later sources overwrite earlier ones where they have data.
PROJECT_ORDER = ["OR_Malheur_2016", "ID_FEMAHQ_2018", "ID_SouthernID_2018_D19",
                 "OR_SouthEast_D22", "NV_USFSR4_D23", "ID_SouthernGaps_D23"]
TILE = 512
WORLD = 2 * math.pi * 6378137.0          # Web Mercator world width, m
ORIGIN = WORLD / 2

for k, v in {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
             "GDAL_HTTP_MULTIPLEX": "YES", "GDAL_HTTP_VERSION": "2", "VSI_CACHE": "TRUE",
             "GDAL_HTTP_USERAGENT": USER_AGENT, "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "5"}.items():
    gdal.SetConfigOption(k, v)


# --- tile math --------------------------------------------------------------

def lonlat_to_merc(lon, lat):
    x = math.radians(lon) * 6378137.0
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137.0
    return x, y


def tile_range(bounds, z):
    """Inclusive x/y tile ranges covering lon/lat bounds at zoom z (XYZ, y down)."""
    w, s, e, n = bounds
    n_t = 2 ** z
    def tx(lon): return int((lon + 180) / 360 * n_t)
    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n_t)
    return range(tx(w), tx(e) + 1), range(ty(n), ty(s) + 1)


def tile_bounds_merc(z, x, y):
    size = WORLD / 2 ** z
    minx = -ORIGIN + x * size
    maxy = ORIGIN - y * size
    return minx, maxy - size, minx + size, maxy


def merc_to_lonlat(x, y):
    return math.degrees(x / 6378137.0), math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2)


def wide_area(bounds_ll, z):
    """Extent of the zoom-z tiles covering bounds_ll: (Web Mercator bounds, lon/lat bounds)."""
    xr, yr = tile_range(bounds_ll, z)
    minx, miny = tile_bounds_merc(z, xr[0], yr[-1])[:2]
    maxx, maxy = tile_bounds_merc(z, xr[-1], yr[0])[2:]
    eps = 1e-7                                   # stay inside, so tile_range doesn't pick up neighbours
    w, s = merc_to_lonlat(minx, miny)
    e, n = merc_to_lonlat(maxx, maxy)
    return (minx, miny, maxx, maxy), (w + eps, s + eps, e - eps, n - eps)


# --- 1. sources -------------------------------------------------------------

def tnm_1m(bounds):
    items, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"datasets": "Digital Elevation Model (DEM) 1 meter",
                                    "bbox": ",".join(map(str, bounds)), "prodFormats": "GeoTIFF",
                                    "max": 500, "offset": offset})
        req = urllib.request.Request(f"{TNM}?{q}", headers={"User-Agent": USER_AGENT})
        d = json.load(urllib.request.urlopen(req, timeout=120))
        items += d["items"]
        offset += len(d["items"])
        if not d["items"] or offset >= d["total"]:
            break
    urls = sorted({i["downloadURL"] for i in items})
    def rank(u):
        p = u.split("/Projects/")[1].split("/")[0]
        return PROJECT_ORDER.index(p) if p in PROJECT_ORDER else -1   # unknown projects go first
    return sorted(urls, key=rank)


def ring_tiles(bounds, template=RING):
    """URLs of the 1-degree USGS tiles covering bounds (named by their NW corner)."""
    w, s, e, n = bounds
    out = []
    for lat in range(math.floor(s), math.floor(n - 1e-9) + 1):
        for lon in range(math.floor(w), math.floor(e - 1e-9) + 1):
            out.append(template.format(t=f"n{lat + 1:02d}w{-lon:03d}"))
    return out


# --- 2. prefetch ------------------------------------------------------------
# Reading 170 remote files one after another inside a single warp is limited
# by per-request latency (~3 MB/s here). Fetching the needed resolution of
# each file in parallel first, then warping from local disk, is much faster.

def _fetch(job):
    url, local, kind, padded = job
    if os.path.exists(local):
        return local, 0.0
    t0 = time.time()
    tmp = local + ".part"
    co = ["TILED=YES", "COMPRESS=ZSTD", "PREDICTOR=3", "BIGTIFF=IF_SAFER"]
    if kind in ("1m", "wide"):
        # Overview level 0 of the 1 m COGs is the 2 m version: plenty for
        # ~3.5 m tiles at the top zoom, and a quarter of the bytes. For the
        # 1 arc-second tiles it's ~2 arc-seconds, plenty for z10.
        try:
            src = gdal.OpenEx("/vsicurl/" + url, open_options=["OVERVIEW_LEVEL=0"])
        except RuntimeError:
            if kind == "wide":                       # no tile there (e.g. outside the US)
                return None, 0.0
            raise
        gdal.Translate(tmp, src, format="GTiff", creationOptions=co)
    else:
        w, s, e, n = padded                                  # ring: only the part we need
        gdal.Translate(tmp, "/vsicurl/" + url, format="GTiff", projWin=[w, n, e, s], projWinSRS="EPSG:4326",
                       creationOptions=co)
    os.replace(tmp, local)
    return local, time.time() - t0


PREFIX = {"ring": "ring_", "wide": "wide_", "1m": ""}


def prefetch(sources, padded, folder, workers=8):
    """sources: {kind: [url, ...]}. Returns {kind: [local file, ...]} in the given order."""
    os.makedirs(folder, exist_ok=True)
    jobs = [(u, os.path.join(folder, PREFIX[k] + os.path.basename(u)), k, padded)
            for k, urls in sources.items() for u in urls]
    print(f"prefetch: {len(jobs)} files with {workers} parallel downloads -> {folder}", flush=True)
    done, t0, missing = 0, time.time(), set()
    with multiprocessing.Pool(workers) as pool:
        for job, (local, _secs) in zip(jobs, pool.imap(_fetch, jobs)):
            done += 1
            if local is None:
                missing.add(job[1])
            if done % 20 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} files, {time.time() - t0:.0f} s", flush=True)
    return {k: [j[1] for j in jobs if j[2] == k and j[1] not in missing] for k in sources}


# --- 3. warp ----------------------------------------------------------------

def progress(label):
    last = [time.time()]
    def cb(frac, msg, data):
        if time.time() - last[0] > 30 or frac >= 1:
            print(f"  {label}: {frac:5.1%}", flush=True)
            last[0] = time.time()
        return 1
    return cb


def warp(bounds_ll, maxzoom, files_1m, files_ring, dst):
    xr, yr = tile_range(bounds_ll, maxzoom)
    minx, _, _, maxy = tile_bounds_merc(maxzoom, xr[0], yr[0])
    _, miny, maxx, _ = tile_bounds_merc(maxzoom, xr[-1], yr[-1])
    res = WORLD / (TILE * 2 ** maxzoom)
    common = dict(srcNodata=NODATA, dstNodata=NODATA, multithread=True, warpMemoryLimit=1024,
                  warpOptions=["NUM_THREADS=ALL_CPUS"])
    if os.path.exists(dst):
        os.remove(dst)                                  # gdal.Warp would update an old file in place
    print(f"warp: {len(files_ring)} ring tiles (~10 m), then {len(files_1m)} 1 m tiles -> {dst}", flush=True)
    # The ring is upsampled (bilinear); the 1 m data is downsampled (average) on top of it.
    ds = gdal.Warp(dst, files_ring, dstSRS="EPSG:3857", outputBounds=(minx, miny, maxx, maxy),
                   xRes=res, yRes=res, resampleAlg="bilinear", outputType=gdal.GDT_Float32,
                   creationOptions=["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=ZSTD",
                                    "PREDICTOR=3", "BIGTIFF=YES"],
                   callback=progress("ring"), **common)
    gdal.Warp(ds, files_1m, resampleAlg="average", callback=progress("1 m"), **common)  # in place
    print("overviews", flush=True)
    gdal.SetConfigOption("COMPRESS_OVERVIEW", "ZSTD")
    ds.BuildOverviews("AVERAGE", [2, 4, 8, 16, 32, 64, 128, 256], callback=progress("overviews"))
    ds = None


def warp_wide(merc_bounds, files_wide, dem, dst):
    """The wide raster at z10's resolution: 1 arc-second tiles, with the fine DEM averaged in on top
    (gdal.Warp reads the fine DEM from its matching overview)."""
    res = WORLD / (TILE * 2 ** WIDE_MAXZOOM)
    if os.path.exists(dst):
        os.remove(dst)
    print(f"wide: {len(files_wide)} 1 arc-second tiles + the fine DEM -> {dst}", flush=True)
    ds = gdal.Warp(dst, files_wide + [dem], dstSRS="EPSG:3857", outputBounds=merc_bounds, xRes=res, yRes=res,
                   resampleAlg="average", outputType=gdal.GDT_Float32, srcNodata=NODATA, dstNodata=NODATA,
                   multithread=True, warpOptions=["NUM_THREADS=ALL_CPUS"],
                   creationOptions=["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=ZSTD",
                                    "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
    ds.BuildOverviews("AVERAGE", [2 ** k for k in range(1, WIDE_MAXZOOM)])
    ds = None


# --- 3. tiles ---------------------------------------------------------------

_ds = None
_wide = None


def _open(path, wide_path):
    global _ds, _wide
    gdal.SetCacheMax(256 * 1024 * 1024)        # keep each worker's block cache small
    _ds = gdal.Open(path)
    _wide = gdal.Open(wide_path)


def encode_png(elev):
    v = np.round((elev.astype(np.float64) + 10000.0) * 10.0).clip(0, 2 ** 24 - 1).astype(np.uint32)
    mem = gdal.GetDriverByName("MEM").Create("", TILE, TILE, 3, gdal.GDT_Byte)
    for b, arr in enumerate(((v >> 16) & 255, (v >> 8) & 255, v & 255), start=1):
        mem.GetRasterBand(b).WriteArray(arr.astype(np.uint8))
    name = f"/vsimem/t{os.getpid()}.png"
    gdal.GetDriverByName("PNG").CreateCopy(name, mem, options=["ZLEVEL=9"])
    f = gdal.VSIFOpenL(name, "rb")
    gdal.VSIFSeekL(f, 0, 2)
    size = gdal.VSIFTellL(f)
    gdal.VSIFSeekL(f, 0, 0)
    data = gdal.VSIFReadL(1, size, f)
    gdal.VSIFCloseL(f)
    gdal.Unlink(name)
    return data


def read_tile(ds, top, z, x, y):
    """A tile from a raster aligned to zoom `top`'s pixel grid, read from the overview level that
    matches z (no resampling, small reads): level k is 2**(k+1) times coarser than `top`."""
    gt = ds.GetGeoTransform()
    scale = 2 ** (top - z)
    band = ds.GetRasterBand(1)
    if scale > 1:
        band = band.GetOverview(int(math.log2(scale)) - 1)
    minx, _, _, maxy = tile_bounds_merc(z, x, y)
    px = round((minx - gt[0]) / gt[1] / scale)
    py = round((maxy - gt[3]) / gt[5] / scale)
    x0, y0 = max(px, 0), max(py, 0)
    x1, y1 = min(px + TILE, band.XSize), min(py + TILE, band.YSize)
    out = np.full((TILE, TILE), NODATA, dtype=np.float32)
    if x1 > x0 and y1 > y0:
        out[y0 - py:y1 - py, x0 - px:x1 - px] = band.ReadAsArray(x0, y0, x1 - x0, y1 - y0)
    return out


def render(job):
    z, x, y, maxzoom = job
    if z <= WIDE_MAXZOOM:
        out = read_tile(_wide, WIDE_MAXZOOM, z, x, y)
    else:
        out = read_tile(_ds, maxzoom, z, x, y)
        missing = out < -1000
        if missing.any() and not missing.all():
            # Past the fine data: use the wide raster, upsampled, rather than smearing the edge.
            wide = gdal.Warp("", _wide, format="MEM", outputBounds=tile_bounds_merc(z, x, y),
                             width=TILE, height=TILE, resampleAlg="bilinear",
                             srcNodata=NODATA, dstNodata=NODATA).ReadAsArray()
            out[missing] = wide[missing]
    valid = out > -1000
    if not valid.any():
        return None
    if not valid.all():
        # Last resort, at the outer edge of everything: extend the edge instead of dropping to sea level.
        mem = gdal.GetDriverByName("MEM").Create("", TILE, TILE, 1, gdal.GDT_Float32)
        b = mem.GetRasterBand(1)
        b.SetNoDataValue(NODATA)
        b.WriteArray(out)
        gdal.FillNodata(b, None, maxSearchDist=TILE * 2, smoothingIterations=0)
        out = b.ReadAsArray()
        out[out < -1000] = float(out[out > -1000].mean()) if (out > -1000).any() else 0.0
    return z, x, y, encode_png(out)


def write_tiles(dem, wide, bounds_ll, wide_ll, minzoom, maxzoom, mbtiles):
    jobs = [(z, x, y, maxzoom) for z in range(minzoom, maxzoom + 1)
            for b in [wide_ll if z <= WIDE_MAXZOOM else bounds_ll]
            for x in tile_range(b, z)[0] for y in tile_range(b, z)[1]]
    print(f"tiles: {len(jobs)} (z{minzoom}-z{maxzoom}; up to z{WIDE_MAXZOOM} from the wide raster)", flush=True)
    if os.path.exists(mbtiles):
        os.remove(mbtiles)
    db = sqlite3.connect(mbtiles)
    db.executescript("create table metadata (name text, value text);"
                     "create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);"
                     "create unique index tile_index on tiles (zoom_level, tile_column, tile_row);")
    w, s, e, n = wide_ll
    cx, cy = (bounds_ll[0] + bounds_ll[2]) / 2, (bounds_ll[1] + bounds_ll[3]) / 2
    meta = {"name": "terrain", "format": "png", "type": "baselayer", "encoding": "mapbox",
            "bounds": f"{w},{s},{e},{n}", "center": f"{cx},{cy},{maxzoom - 4}",
            "minzoom": str(minzoom), "maxzoom": str(maxzoom),
            "attribution": "USGS 3D Elevation Program (public domain)"}
    db.executemany("insert into metadata values (?, ?)", meta.items())
    done, nbytes, t0 = 0, 0, time.time()
    with multiprocessing.Pool(os.cpu_count(), initializer=_open, initargs=(dem, wide)) as pool:
        for r in pool.imap_unordered(render, jobs, chunksize=8):
            done += 1
            if r:
                z, x, y, data = r
                nbytes += len(data)
                db.execute("insert into tiles values (?, ?, ?, ?)", (z, x, 2 ** z - 1 - y, data))
            if done % 500 == 0:
                db.commit()
                print(f"  {done}/{len(jobs)} tiles, {nbytes / 1e6:.0f} MB, {time.time() - t0:.0f} s", flush=True)
    db.commit()
    db.close()
    print(f"tiles done: {done}, {nbytes / 1e6:.0f} MB", flush=True)


# --- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", default="-117.05,43.00,-115.95,43.85", help="west,south,east,north")
    ap.add_argument("--pad", type=float, default=0.2, help="degrees of ~10 m ring around the 1 m area")
    ap.add_argument("--minzoom", type=int, default=6)
    ap.add_argument("--maxzoom", type=int, default=14)
    ap.add_argument("--exaggeration", type=float, default=1.3)
    ap.add_argument("--out", default=os.environ.get("TILES_DIR", "data/tiles"), help="tiles folder")
    ap.add_argument("--work", default="data/terrain", help="folder for the intermediate DEM")
    ap.add_argument("--skip-warp", action="store_true", help="reuse an existing DEM in --work")
    args = ap.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split(","))
    padded = (bbox[0] - args.pad, bbox[1] - args.pad, bbox[2] + args.pad, bbox[3] + args.pad)
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    # Gap filling writes scratch files; keep them in the work folder, not the current directory.
    gdal.SetConfigOption("CPL_TMPDIR", os.path.abspath(args.work))
    dem = os.path.join(args.work, "dem_3857.tif")
    wide = os.path.join(args.work, "dem_wide_3857.tif")
    wide_merc, wide_ll = wide_area(padded, args.minzoom)
    src = os.path.join(args.work, "src")
    t0 = time.time()
    if not args.skip_warp:
        sources = tnm_1m(bbox)
        with open(os.path.join(args.work, "sources.txt"), "w") as f:
            f.write("\n".join(ring_tiles(padded) + sources) + "\n")
        got = prefetch({"ring": ring_tiles(padded), "1m": sources}, padded, src)
        warp(padded, args.maxzoom, got["1m"], got["ring"], dem)
        print(f"warp + overviews: {time.time() - t0:.0f} s", flush=True)
    if not args.skip_warp or not os.path.exists(wide):
        got = prefetch({"wide": ring_tiles(wide_ll, WIDE)}, padded, src)
        warp_wide(wide_merc, got["wide"], dem, wide)
        print(f"wide raster: {time.time() - t0:.0f} s", flush=True)
    mbtiles = os.path.join(args.work, "terrain.mbtiles")
    write_tiles(dem, wide, padded, wide_ll, args.minzoom, args.maxzoom, mbtiles)
    pm = os.path.join(args.out, "terrain.pmtiles")
    subprocess.run(["pmtiles", "convert", mbtiles, pm + ".part"], check=True)
    os.replace(pm + ".part", pm)

    path = os.path.join(args.out, "manifest.json")
    m = json.load(open(path)) if os.path.exists(path) else {}
    m["terrain"] = {"file": "terrain.pmtiles", "encoding": "mapbox", "tileSize": TILE,
                    "exaggeration": args.exaggeration, "built": datetime.date.today().isoformat(),
                    "attribution": "USGS 3DEP",
                    "source": "USGS 3DEP 1 m DEM (newest project wins), 1/3 arc-second DEM in a "
                              f"{args.pad} degree ring around it, 1 arc-second DEM for z{args.minzoom}-"
                              f"z{WIDE_MAXZOOM} and beyond the ring"}
    json.dump(m, open(path, "w"), indent=1)
    print(f"wrote {pm} ({os.path.getsize(pm) / 1e6:.0f} MB) and updated {path}; total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
