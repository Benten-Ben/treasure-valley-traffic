#!/usr/bin/env python3
"""Build aerial-imagery tiles for the valley from USDA NAIP.

NAIP is public-domain aerial imagery (Idaho: 0.6 m, flown July 2023; the
Oregon edge: 0.3 m, 2022). The images are cloud-optimized GeoTIFFs on
Microsoft's Planetary Computer, which needs no account: an anonymous,
short-lived access token comes from its public token endpoint.

Two files, so a missing detail tile never hides the valley layer under it:
  imagery.pmtiles         valley-wide, --minzoom to --maxzoom (default z8-z14;
                          512-px tiles, about 3.5 m per pixel at z14)
  imagery-detail.pmtiles  around --detail points (camera locations), z15 to
                          --detail-maxzoom (default z17, about 0.45 m per
                          pixel), for camera calibration

Steps:
  1. find the newest images per state (STAC search);
  2. prefetch, in parallel, only what's needed: each image's overview level
     closest to 2.4 m for the valley, and full-resolution windows around the
     detail points (reading the images remotely tile by tile was far slower);
  3. render the top zoom and detail tiles from the local copies;
  4. make lower zooms by shrinking the tiles below them;
  5. convert MBTiles to PMTiles (`pmtiles convert`) and update manifest.json.

Needs GDAL's Python bindings (python3.12 here) and the pmtiles CLI.

Usage:
  python3.12 basemap/imagery.py                                         # valley only
  python3.12 basemap/imagery.py --detail data/cameras/cameras.geojson   # plus camera areas
"""

import argparse
import datetime
import json
import math
import multiprocessing
import os
import sqlite3
import subprocess
import time
import urllib.request

from osgeo import gdal, osr

gdal.UseExceptions()

USER_AGENT = ("treasure-valley-traffic/0.2 "
              "(public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)")
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/naip"
TILE = 512
WORLD = 2 * math.pi * 6378137.0
ORIGIN = WORLD / 2
TOKEN_MAX_AGE_S = 25 * 60   # tokens last about an hour
TARGET_RES = {"valley": 2.4, "detail": 0.6}   # meters per pixel to prefetch at
LOCAL_CO = ["TILED=YES", "COMPRESS=JPEG", "PHOTOMETRIC=YCBCR", "JPEG_QUALITY=90"]

for k, v in {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MULTIPLEX": "YES",
             "GDAL_HTTP_VERSION": "2", "GDAL_HTTP_USERAGENT": USER_AGENT,
             "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "5",
             "CPL_VSIL_CURL_USE_HEAD": "NO", "GDAL_CACHEMAX": "256"}.items():
    gdal.SetConfigOption(k, v)


def get_json(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT,
                                                          "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


_token = {"value": None, "at": 0.0}


def token():
    """The current access token, refreshed when it gets old (per process)."""
    if time.time() - _token["at"] > TOKEN_MAX_AGE_S:
        _token.update(value=get_json(TOKEN)["token"], at=time.time())
    return _token["value"]


def naip_items(bbox):
    """Newest NAIP year per state, as dicts sorted oldest first so newer images win."""
    items, body, url = [], {"collections": ["naip"], "bbox": list(bbox), "limit": 250}, STAC
    while True:
        d = get_json(url, body)
        items += d["features"]
        nxt = [l for l in d.get("links", []) if l.get("rel") == "next"]
        if not nxt:
            break
        body, url = nxt[0].get("body", body), nxt[0]["href"]
    newest = {}
    for i in items:
        state, year = i["properties"].get("naip:state"), i["properties"].get("naip:year")
        newest[state] = max(newest.get(state, ""), year)
    keep = [{"year": i["properties"]["naip:year"], "href": i["assets"]["image"]["href"], "bbox": i["bbox"]}
            for i in items if i["properties"]["naip:year"] == newest[i["properties"].get("naip:state")]]
    return sorted(keep, key=lambda i: (i["year"], i["href"])), newest


# --- tile math --------------------------------------------------------------

def tile_range(bounds, z):
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


def around(lon, lat, radius_m):
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# --- 2. prefetch ------------------------------------------------------------

def pick_overview(ds, target):
    """OVERVIEW_LEVEL to read (-1 = full resolution): the coarsest level still as sharp as target."""
    res, band, best = ds.GetGeoTransform()[1], ds.GetRasterBand(1), -1
    for i in range(band.GetOverviewCount()):
        if res * ds.RasterXSize / band.GetOverview(i).XSize <= target * 1.05:
            best = i
    return best


def src_window(ds, window):
    """Pixel window (xoff, yoff, xsize, ysize) of ds covering an EPSG:3857 window, clipped to the image."""
    merc = osr.SpatialReference()
    merc.ImportFromEPSG(3857)
    srs = ds.GetSpatialRef()
    for s in (merc, srs):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(merc, srs)
    minx, miny, maxx, maxy = window
    pts = [ct.TransformPoint(x, y)[:2] for x in (minx, maxx) for y in (miny, maxy)]
    gt = ds.GetGeoTransform()
    x0 = max(0, math.floor((min(p[0] for p in pts) - gt[0]) / gt[1]))
    x1 = min(ds.RasterXSize, math.ceil((max(p[0] for p in pts) - gt[0]) / gt[1]))
    y0 = max(0, math.floor((max(p[1] for p in pts) - gt[3]) / gt[5]))
    y1 = min(ds.RasterYSize, math.ceil((min(p[1] for p in pts) - gt[3]) / gt[5]))
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def _fetch(job):
    """Copy one image (or a window of it) at the wanted resolution to a local JPEG GeoTIFF."""
    kind, href, local, window = job
    if os.path.exists(local):
        return local, 0.0, None
    t0 = time.time()
    try:
        url = f"/vsicurl/{href}?{token()}"
        level = pick_overview(gdal.Open(url), TARGET_RES[kind])
        src = gdal.OpenEx(url, open_options=[f"OVERVIEW_LEVEL={level}"] if level >= 0 else [])
        kw = {}
        if window:
            win = src_window(src, window)
            if not win:
                return None, 0.0, None
            kw["srcWin"] = list(win)
        gdal.Translate(local + ".part", src, format="GTiff", bandList=[1, 2, 3], creationOptions=LOCAL_CO, **kw)
        os.replace(local + ".part", local)
        return local, time.time() - t0, None
    except RuntimeError as e:
        return None, time.time() - t0, f"{os.path.basename(href)}: {e}"


def prefetch(jobs, workers=8):
    """Run fetch jobs in parallel; retry failures once (e.g. after a token expired)."""
    t0, done, failed, got = time.time(), 0, [], {}
    with multiprocessing.Pool(workers) as pool:
        for attempt in (1, 2):
            todo = jobs if attempt == 1 else [j for j in jobs if j[2] in failed]
            failed = []
            for job, (local, _secs, err) in zip(todo, pool.imap(_fetch, todo)):
                done += 1
                if err:
                    failed.append(job[2])
                    print(f"  failed (attempt {attempt}): {err}", flush=True)
                elif local:
                    got[job[2]] = local
                if done % 25 == 0:
                    print(f"  {done} fetched, {time.time() - t0:.0f} s", flush=True)
            if not failed:
                break
    if failed:
        raise SystemExit(f"{len(failed)} downloads failed twice; rerun to resume (finished files are kept)")
    print(f"  prefetch done: {len(got)} files in {time.time() - t0:.0f} s", flush=True)
    return [j[2] for j in jobs if j[2] in got]    # in job order: newer images last, so they win


def build_vrts(files, folder, name):
    """One VRT per coordinate system (BuildVRT needs one), in the order the CRSs first appear.

    Each gets an alpha band that is transparent wherever no image covers it.
    Without one, the gaps between detail windows count as valid black pixels
    and paint over the valley imagery underneath."""
    groups = {}
    for f in files:
        groups.setdefault(gdal.Open(f).GetSpatialRef().GetAuthorityCode(None) or "unknown", []).append(f)
    out = []
    for crs, fs in groups.items():
        path = os.path.join(folder, f"{name}_{crs}.vrt")
        gdal.BuildVRT(path, fs, addAlpha=True)
        out.append(path)
    return out


# --- 3. rendering -----------------------------------------------------------

_state = {}


def _init(sources):
    _state.update(sources={k: [gdal.Open(p) for p in v] for k, v in sources.items()})


def encode(ds):
    name = f"/vsimem/t{os.getpid()}.webp"
    gdal.GetDriverByName("WEBP").CreateCopy(name, ds, options=["QUALITY=82"])
    f = gdal.VSIFOpenL(name, "rb")
    gdal.VSIFSeekL(f, 0, 2)
    size = gdal.VSIFTellL(f)
    gdal.VSIFSeekL(f, 0, 0)
    data = gdal.VSIFReadL(1, size, f)
    gdal.VSIFCloseL(f)
    gdal.Unlink(name)
    return data


def render(job):
    """One tile from the local copies: RGB where fully covered, RGBA (transparent outside) at the edges."""
    layer, z, x, y = job
    minx, miny, maxx, maxy = tile_bounds_merc(z, x, y)
    ds = gdal.Warp("", _state["sources"][layer], format="MEM", dstSRS="EPSG:3857",
                   outputBounds=(minx, miny, maxx, maxy), width=TILE, height=TILE,
                   resampleAlg="cubic", dstAlpha=True, multithread=False)
    lo, hi = ds.GetRasterBand(4).ComputeRasterMinMax(False)
    if hi == 0:
        return None
    if lo == 255:
        ds = gdal.Translate("", ds, format="MEM", bandList=[1, 2, 3])
    return layer, z, x, y, encode(ds)


def children(db, z, x, y):
    """The (dx, dy, data) of the up-to-four tiles one zoom down that make up tile z/x/y."""
    out = []
    for dx in (0, 1):
        for dy in (0, 1):
            cx, cy = 2 * x + dx, 2 * y + dy
            row = db.execute("select tile_data from tiles where zoom_level=? and tile_column=? and tile_row=?",
                             (z + 1, cx, 2 ** (z + 1) - 1 - cy)).fetchone()
            if row:
                out.append((dx, dy, row[0]))
    return out


def shrink(job):
    """Make a tile from its children one zoom down (2x2 average). The main process reads the
    children and passes them in: workers forked from a process with an open SQLite connection
    must not use SQLite themselves (their copied lock state makes reads unsafe)."""
    import numpy as np
    _layer, z, x, y, kids = job
    if not kids:
        return None
    big = np.zeros((4, 2 * TILE, 2 * TILE), dtype=np.float32)
    for dx, dy, data in kids:
        name = f"/vsimem/c{os.getpid()}.webp"
        gdal.FileFromMemBuffer(name, data)
        arr = gdal.Open(name).ReadAsArray()
        gdal.Unlink(name)
        if arr.shape[0] == 3:                              # no alpha band: fully opaque
            arr = np.concatenate([arr, np.full((1, TILE, TILE), 255, arr.dtype)])
        big[:, dy * TILE:(dy + 1) * TILE, dx * TILE:(dx + 1) * TILE] = arr
    a = big[3:4] / 255.0                                   # alpha-weighted, so edges don't darken
    rgb = (big[:3] * a).reshape(3, TILE, 2, TILE, 2).sum(axis=(2, 4))
    wsum = a.reshape(1, TILE, 2, TILE, 2).sum(axis=(2, 4))
    small = np.concatenate([np.where(wsum > 0, rgb / np.maximum(wsum, 1e-9), 0), wsum / 4 * 255])
    small = small.round().clip(0, 255).astype("uint8")
    bands = 3 if small[3].min() == 255 else 4
    mem = gdal.GetDriverByName("MEM").Create("", TILE, TILE, bands, gdal.GDT_Byte)
    for b in range(bands):
        mem.GetRasterBand(b + 1).WriteArray(small[b])
    if bands == 4:
        mem.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    return _layer, z, x, y, encode(mem)


def new_mbtiles(path, name, bounds, minzoom, maxzoom):
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.executescript("create table metadata (name text, value text);"
                     "create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);"
                     "create unique index tile_index on tiles (zoom_level, tile_column, tile_row);")
    w, s, e, n = bounds
    db.executemany("insert into metadata values (?, ?)", {
        "name": name, "format": "webp", "type": "baselayer", "bounds": f"{w},{s},{e},{n}",
        "center": f"{(w + e) / 2},{(s + n) / 2},{minzoom}", "minzoom": str(minzoom),
        "maxzoom": str(maxzoom), "attribution": "USDA NAIP"}.items())
    db.commit()
    return db


def to_pmtiles(mbtiles, out):
    subprocess.run(["pmtiles", "convert", mbtiles, out + ".part"], check=True)
    os.replace(out + ".part", out)
    return os.path.getsize(out)


# --- main -------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", default="-117.05,43.00,-115.95,43.85", help="west,south,east,north")
    ap.add_argument("--minzoom", type=int, default=8)
    ap.add_argument("--maxzoom", type=int, default=14, help="valley-wide top zoom (512-px tiles)")
    ap.add_argument("--detail", help="GeoJSON of points to add full-detail imagery around")
    ap.add_argument("--detail-radius", type=float, default=250.0, help="meters around each detail point")
    ap.add_argument("--detail-maxzoom", type=int, default=17)
    ap.add_argument("--out", default=os.environ.get("TILES_DIR", "data/tiles"))
    ap.add_argument("--work", default="data/imagery")
    ap.add_argument("--workers", type=int, default=8, help="parallel downloads")
    args = ap.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split(","))
    src = os.path.join(args.work, "src")
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(src, exist_ok=True)
    t0 = time.time()

    # 1. images
    items, years = naip_items(bbox)
    print(f"NAIP: {len(items)} images, newest per state {years}", flush=True)

    # 2. prefetch: whole images at ~2.4 m, then full-resolution windows for the detail tiles
    jobs = [("valley", i["href"], os.path.join(src, "v_" + os.path.basename(i["href"])), None) for i in items]
    detail_tiles, n_pts = set(), 0
    if args.detail:
        pts = [f["geometry"]["coordinates"][:2] for f in json.load(open(args.detail))["features"]
               if f.get("geometry")]
        n_pts = len(pts)
        for n, (lon, lat) in enumerate(pts):
            area = around(lon, lat, args.detail_radius)
            for z in range(args.maxzoom + 1, args.detail_maxzoom + 1):
                xr, yr = tile_range(area, z)
                detail_tiles |= {("detail", z, x, y) for x in xr for y in yr}
            # Fetch what the top-zoom detail tiles cover: the tiles' extent, not just the circle.
            xr, yr = tile_range(area, args.detail_maxzoom)
            window = (tile_bounds_merc(args.detail_maxzoom, xr[0], yr[-1])[0],
                      tile_bounds_merc(args.detail_maxzoom, xr[0], yr[-1])[1],
                      tile_bounds_merc(args.detail_maxzoom, xr[-1], yr[0])[2],
                      tile_bounds_merc(args.detail_maxzoom, xr[-1], yr[0])[3])
            sw, ne = merc_to_lonlat(window[0], window[1]), merc_to_lonlat(window[2], window[3])
            for i in items:
                if overlaps(i["bbox"], (sw[0], sw[1], ne[0], ne[1])):
                    name = f"d{n:03d}_" + os.path.basename(i["href"])
                    jobs.append(("detail", i["href"], os.path.join(src, name), window))
        print(f"detail: {n_pts} points, {args.detail_radius:.0f} m radius, z{args.maxzoom + 1}-"
              f"z{args.detail_maxzoom}: {len(detail_tiles)} tiles", flush=True)
    print(f"prefetch: {len(jobs)} downloads, {args.workers} at a time -> {src}", flush=True)
    files = prefetch(jobs, args.workers)
    kinds = {j[2]: j[0] for j in jobs}
    sources = {"valley": build_vrts([f for f in files if kinds[f] == "valley"], args.work, "valley")}
    if detail_tiles:
        sources["detail"] = sources["valley"] + build_vrts([f for f in files if kinds[f] == "detail"],
                                                           args.work, "detail")

    # 3-4. render, then shrink
    valley_mb = os.path.join(args.work, "imagery.mbtiles")
    detail_mb = os.path.join(args.work, "imagery-detail.mbtiles")
    dbs = {"valley": new_mbtiles(valley_mb, "imagery", bbox, args.minzoom, args.maxzoom)}
    if detail_tiles:
        dbs["detail"] = new_mbtiles(detail_mb, "imagery-detail", bbox, args.maxzoom + 1, args.detail_maxzoom)
    nbytes = {"valley": 0, "detail": 0}

    def store(r):
        if r:
            layer, z, x, y, data = r
            nbytes[layer] += len(data)
            dbs[layer].execute("insert or replace into tiles values (?, ?, ?, ?)", (z, x, 2 ** z - 1 - y, data))

    top = [("valley", args.maxzoom, x, y) for x in tile_range(bbox, args.maxzoom)[0]
           for y in tile_range(bbox, args.maxzoom)[1]]
    render_jobs = top + sorted(detail_tiles)
    print(f"render: {len(top)} valley tiles at z{args.maxzoom}, {len(detail_tiles)} detail tiles", flush=True)
    t1 = time.time()
    with multiprocessing.Pool(os.cpu_count(), initializer=_init, initargs=(sources,)) as pool:
        for done, r in enumerate(pool.imap_unordered(render, render_jobs, chunksize=4), start=1):
            store(r)
            if done % 500 == 0 or done == len(render_jobs):
                for db in dbs.values():
                    db.commit()
                print(f"  {done}/{len(render_jobs)} tiles, valley {nbytes['valley'] / 1e6:.0f} MB, "
                      f"detail {nbytes['detail'] / 1e6:.0f} MB, {time.time() - t1:.0f} s", flush=True)
        for z in range(args.maxzoom - 1, args.minzoom - 1, -1):
            jobs_z = [("valley", z, x, y, children(dbs["valley"], z, x, y))
                      for x in tile_range(bbox, z)[0] for y in tile_range(bbox, z)[1]]
            for r in pool.imap_unordered(shrink, jobs_z, chunksize=8):
                store(r)
            dbs["valley"].commit()
            print(f"  z{z}: {len(jobs_z)} tiles made from z{z + 1}", flush=True)
    for db in dbs.values():
        db.close()

    # 5. PMTiles and manifest
    pm = os.path.join(args.out, "imagery.pmtiles")
    size = to_pmtiles(valley_mb, pm)
    path = os.path.join(args.out, "manifest.json")
    m = json.load(open(path)) if os.path.exists(path) else {}
    m["imagery"] = {"file": "imagery.pmtiles", "tileSize": TILE, "attribution": "USDA NAIP",
                    "built": datetime.date.today().isoformat(), "maxzoom": args.maxzoom,
                    "source": f"NAIP via Microsoft Planetary Computer; newest per state {years}"}
    print(f"wrote {pm} ({size / 1e6:.0f} MB)", flush=True)
    if detail_tiles:
        pm_d = os.path.join(args.out, "imagery-detail.pmtiles")
        size_d = to_pmtiles(detail_mb, pm_d)
        m["imagery"]["detail"] = {"file": "imagery-detail.pmtiles", "minzoom": args.maxzoom + 1,
                                  "maxzoom": args.detail_maxzoom, "points": n_pts,
                                  "radius": args.detail_radius}
        print(f"wrote {pm_d} ({size_d / 1e6:.0f} MB)", flush=True)
    json.dump(m, open(path, "w"), indent=1)
    print(f"total {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
