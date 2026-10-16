"""The ground's tile writer (G1a): painted windows to 512 px WebP tiles in two PMTiles files, tile by tile, never a
full mosaic. Runs in the worker image (GDAL, NumPy, SciPy, Pillow).

    python basemap/ground/tilewrite.py paint --out DIR [--archive $TVT_ARCHIVE] (--boxes | --valley [--bounds ...])
        [--detail] [--view z8,z9,z10]          # paint blocks into DIR/blocks/ (resumable: a finished block is kept)
    python basemap/ground/tilewrite.py assemble --out DIR [--tiles TILES]   # blocks -> ground-<digest>.pmtiles, ...

**Blocks.** The valley file is painted a z13 tile at a time: its window of the 2 m painter grid
(tiles.tile_window) is painted with the painter's halo, warped onto the z13 tile's Web Mercator square at z15's
pixel size (2,048 px), and cut into its 16 z15 tiles; its z14 tiles are 2 x 2 averages of those pixels, and its z13
tile of the z14 ones. The z13 tile is also kept losslessly (PNG), and z12 to z8 are made from those, four children at
a time (`pyramid`). The detail file is painted a z15 tile at a time at 0.5 m (the box classes' own grid) and cut into
z17 tiles. Each finished block is a file in DIR/blocks/ (its tiles, WebP, with an index), written atomically, so a
stopped run picks up where it was, and the PMTiles files are assembled from the blocks at the end (`assemble`).

**What G1a paints** (valley-wide runs are G1b's): --boxes, the z13 blocks touching the ten boxes; --detail, the
detail file's z17 tiles; --view, given zooms painted straight from a coarser level of the painter grid (z10 from
10 m, z9 from 20 m, z8 from 40 m), which is what a first load at the default view fetches, for the first-load
estimate (`firstload`). A file assembled from these is partial: its name says `-partial` and nothing switches it in.

Tiles: tiles.TILE_SIZE px, lossy WebP at tiles.QUALITY (Pillow, method 6), opaque. Pixels outside the grid are the
flat Valley colour (the painter's).
"""

import argparse
import gzip
import io
import json
import math
import os
import shutil
import signal
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np  # noqa: E402
from osgeo import gdal, osr  # noqa: E402
from PIL import Image  # noqa: E402

from basemap.ground import grid, inputs, paint, pmtw, tiles  # noqa: E402
from basemap.ground import manifest as M  # noqa: E402

gdal.UseExceptions()

BLOCK_Z = 13                      # the valley file's blocks
DETAIL_BLOCK_Z = 15               # the detail file's blocks
PAINT_RES = 2.0                   # the painter grid (z15 at 1.73 m a pixel)
DETAIL_RES = grid.LEVELS["classes"]
VIEW_RES = {8: 40.0, 9: 20.0, 10: 10.0, 11: 10.0, 12: 5.0}
BOX_MARGIN_M = 200.0              # --boxes paints the z13 blocks within this of a box
SIZE = tiles.TILE_SIZE


class TileError(ValueError):
    pass


def webp(rgb, quality=None):
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "WEBP", quality=int(quality or tiles.QUALITY), method=6)
    return buf.getvalue()


def png(rgb):
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def decode(data):
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def _srs(epsg):
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    return s.ExportToWkt()


def warp(rgb, win, z, x, y, n):
    """A painted window (rows, cols, 3) uint8 on the grid, warped onto tile z/x/y's Web Mercator square at n x SIZE
    pixels a side: bilinear, or an average where the window is painted much finer than the tile's pixels."""
    rows, cols = rgb.shape[:2]
    src = gdal.GetDriverByName("MEM").Create("", cols, rows, 3, gdal.GDT_Byte)
    src.SetGeoTransform(win.transform)
    src.SetProjection(_srs(grid.EPSG))
    for b in range(3):
        src.GetRasterBand(b + 1).WriteArray(rgb[..., b])
    w, s, e, nn = tiles.tile_mercator(z, x, y)
    lat = (tiles.tile_lonlat(z, x, y)[1] + tiles.tile_lonlat(z, x, y)[3]) / 2
    px = tiles.mpp(z + int(round(math.log2(n))), lat)         # the tile's pixel on the ground
    resample = "average" if win.res * 1.5 < px else "bilinear"  # painted finer than the tile: average it down
    out = gdal.Warp("", src, format="MEM", dstSRS=_srs(3857), outputBounds=(w, s, e, nn), width=n * SIZE,
                    height=n * SIZE, resampleAlg=resample, multithread=False)
    arr = out.ReadAsArray().reshape(3, n * SIZE, n * SIZE)
    return np.ascontiguousarray(np.moveaxis(arr, 0, -1))


def halve(rgb):
    """2 x 2 average (the parent's pixels), rounded."""
    h, w = rgb.shape[:2]
    a = rgb.reshape(h // 2, 2, w // 2, 2, 3).astype(np.uint16).sum(axis=(1, 3))
    return ((a + 2) // 4).astype(np.uint8)


def cut(rgb, z, x, y, n):
    """The n x n child tiles of z/x/y at zoom z + log2(n) from its mosaic: {(z', x', y'): (SIZE, SIZE, 3)}."""
    k = int(round(math.log2(n)))
    out = {}
    for j in range(n):
        for i in range(n):
            out[(z + k, x * n + i, y * n + j)] = rgb[j * SIZE:(j + 1) * SIZE, i * SIZE:(i + 1) * SIZE]
    return out


# ---- blocks ---------------------------------------------------------------------------------------------------------

class Blocks:
    """DIR/blocks/: one file per finished block (<name>.blk: its tiles' WebP bytes back to back, <name>.json: the
    index), written atomically; and DIR/z13/ the lossless z13 tiles (PNG) for the pyramid."""

    def __init__(self, out):
        self.dir = os.path.join(out, "blocks")
        self.png = os.path.join(out, "png")
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.png, exist_ok=True)

    def done(self, name):
        return os.path.exists(os.path.join(self.dir, name + ".json"))

    def write(self, name, tiles_bytes, file="valley"):
        data, index = bytearray(), []
        for (z, x, y), b in sorted(tiles_bytes.items()):
            index.append([z, x, y, len(data), len(b)])
            data += b
        tmp = os.path.join(self.dir, name + ".blk.part")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, os.path.join(self.dir, name + ".blk"))
        tmp = os.path.join(self.dir, name + ".json.part")
        with open(tmp, "w") as f:
            json.dump({"file": file, "tiles": index}, f)
        os.replace(tmp, os.path.join(self.dir, name + ".json"))

    def keep_png(self, z, x, y, rgb):
        path = os.path.join(self.png, f"{z}-{x}-{y}.png")
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(png(rgb))
        os.replace(tmp, path)

    def read_png(self, z, x, y):
        path = os.path.join(self.png, f"{z}-{x}-{y}.png")
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return decode(f.read())

    def all(self):
        """[(file, z, x, y, bytes)] of every finished block's tiles."""
        out = []
        for name in sorted(os.listdir(self.dir)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(self.dir, name)) as f:
                idx = json.load(f)
            with open(os.path.join(self.dir, name[:-5] + ".blk"), "rb") as f:
                data = f.read()
            for z, x, y, off, ln in idx["tiles"]:
                out.append((idx["file"], z, x, y, data[off:off + ln]))
        return out


def valley_set(z):
    xs, ys = tiles.tile_range(grid.MAP_LONLAT, z)
    return xs, ys


def in_valley(z, x, y):
    xs, ys = valley_set(z)
    return x in xs and y in ys


def paint_valley_block(painter, blocks, x, y, quality, keep=True):
    """One z13 block: its z15, z14 and z13 tiles (those touching the map box) and its lossless z13 tile."""
    name = f"v{BLOCK_Z}-{x}-{y}"
    if blocks.done(name):
        return 0
    n = 2 ** (tiles.VALLEY_ZOOMS[1] - BLOCK_Z)
    win = tiles.tile_window(BLOCK_Z, x, y, PAINT_RES)
    rgb = painter.paint(win)
    mosaic = warp(rgb, win, BLOCK_Z, x, y, n)
    out = {}
    level = mosaic
    for k in range(tiles.VALLEY_ZOOMS[1] - BLOCK_Z + 1):
        z = tiles.VALLEY_ZOOMS[1] - k
        m = 2 ** (z - BLOCK_Z)
        for (zz, tx, ty), t in cut(level, BLOCK_Z, x, y, m).items() if m > 1 else [((BLOCK_Z, x, y), level)]:
            if in_valley(zz, tx, ty):
                out[(zz, tx, ty)] = webp(t, quality)
        if z > BLOCK_Z:
            level = halve(level)
    if keep:
        blocks.keep_png(BLOCK_Z, x, y, level)
    blocks.write(name, out)
    return len(out)


def pyramid(blocks, quality, lowest=None, log=print):
    """z12 down to z8 (or lowest) from the kept lossless tiles, four children at a time; missing children are the
    flat Valley colour. Returns the tiles written."""
    lowest = tiles.VALLEY_ZOOMS[0] if lowest is None else lowest
    flat = np.array([int(tiles.FLAT["valley"][i:i + 2], 16) for i in (1, 3, 5)], np.uint8)
    n = 0
    for z in range(BLOCK_Z - 1, lowest - 1, -1):
        xs, ys = valley_set(z)
        out = {}
        for ty in ys:
            for tx in xs:
                kids = [blocks.read_png(z + 1, 2 * tx + i, 2 * ty + j) for j in (0, 1) for i in (0, 1)]
                if all(k is None for k in kids):
                    continue
                kids = [k if k is not None else np.broadcast_to(flat, (SIZE, SIZE, 3)) for k in kids]
                big = np.concatenate([np.concatenate(kids[0:2], axis=1), np.concatenate(kids[2:4], axis=1)], axis=0)
                t = halve(np.ascontiguousarray(big))
                blocks.keep_png(z, tx, ty, t)
                out[(z, tx, ty)] = webp(t, quality)
        if out:
            blocks.write(f"p{z}", out)
            n += len(out)
            log(f"  pyramid z{z}: {len(out)} tiles")
    return n


def paint_detail_block(painter, blocks, x, y, quality):
    """One z15 block of the detail file: its z17 tiles touching a box, painted at 0.5 m."""
    name = f"d{DETAIL_BLOCK_Z}-{x}-{y}"
    if blocks.done(name):
        return 0
    want = set(tiles.detail_tiles(tiles.DETAIL_ZOOMS[0]))
    n = 2 ** (tiles.DETAIL_ZOOMS[0] - DETAIL_BLOCK_Z)
    win = tiles.tile_window(DETAIL_BLOCK_Z, x, y, DETAIL_RES)
    rgb = painter.paint(win)
    mosaic = warp(rgb, win, DETAIL_BLOCK_Z, x, y, n)
    out = {}
    for (z, tx, ty), t in cut(mosaic, DETAIL_BLOCK_Z, x, y, n).items():
        if (tx, ty) in want:
            out[(z, tx, ty)] = webp(t, quality)
    blocks.write(name, out, file="detail")
    return len(out)


def paint_view_tile(painter, blocks, z, x, y, quality):
    """One valley tile painted straight from a coarser level of the grid (VIEW_RES), for the first-load estimate."""
    name = f"w{z}-{x}-{y}"
    if blocks.done(name):
        return 0
    res = VIEW_RES[z]
    win = tiles.tile_window(z, x, y, res)
    rgb = painter.paint(win)
    t = warp(rgb, win, z, x, y, 1)
    blocks.write(name, {(z, x, y): webp(t, quality)}, file="view")
    return 1


def blocks_near_boxes(z, margin_m=BOX_MARGIN_M):
    """[(x, y)] of the zoom-z tiles within margin_m of a box."""
    out = set()
    for b in grid.boxes():
        w, s, e, n = b.utm
        xs, ys = tiles.tile_range(grid.lonlat_of((w - margin_m, s - margin_m, e + margin_m, n + margin_m)), z)
        out.update((x, y) for y in ys for x in xs)
    return sorted(out, key=lambda t: (t[1], t[0]))


def detail_blocks():
    want = set(tiles.detail_tiles(tiles.DETAIL_ZOOMS[0]))
    k = 2 ** (tiles.DETAIL_ZOOMS[0] - DETAIL_BLOCK_Z)
    return sorted({(x // k, y // k) for x, y in want}, key=lambda t: (t[1], t[0]))


# ---- assembling -----------------------------------------------------------------------------------------------------

def plan_of(archive):
    """The ground's plan from the archive's exports (inputs.resolve), refused unless it can be painted."""
    plan = inputs.resolve(inputs.exports(archive), versions=paint.versions())
    if plan.status != "painted":
        raise TileError(plan.reason)
    return plan


def assemble(out, plan, partial, log=print):
    """The PMTiles files from DIR/blocks/: (valley path, detail path, entry). Names carry the plan's digest; a
    partial set of blocks says so in its names and gets no tiles-manifest entry."""
    blocks = Blocks(out)
    digest = tiles.digest(plan, painter=paint.PAINTER_VERSION)
    valley_name, detail_name = tiles.file_names(digest)
    if partial:
        valley_name = valley_name.replace(".pmtiles", "-partial.pmtiles")
        detail_name = detail_name.replace(".pmtiles", "-partial.pmtiles")
    meta = {"name": "ground", "attribution": "; ".join(plan.credits), "licence": plan.licence,
            "republish": plan.republish, "inputs": plan.refs + [f"raw/{n}@{plan.versions[n]}" for n in plan.raw_names],
            "painter": paint.PAINTER_VERSION, "spec": tiles.SPEC_VERSION, "partial": bool(partial),
            "about": "The painted Valley ground (basemap/ground). ODbL produced work built from public inputs."}
    w_v = pmtw.Writer(os.path.join(out, valley_name), 4, dict(meta, file="valley"))
    w_d = pmtw.Writer(os.path.join(out, detail_name), 4, dict(meta, file="detail"))
    seen = set()
    counts = {"valley": 0, "detail": 0}
    try:
        for file, z, x, y, data in blocks.all():
            target = w_d if file == "detail" else w_v
            key = ("d" if file == "detail" else "v", z, x, y)
            if key in seen:
                continue                           # a view tile and a pyramid tile for the same z/x/y: the first
            seen.add(key)
            target.add(z, x, y, data)
            counts["detail" if file == "detail" else "valley"] += 1
        lon0, lat0, lon1, lat1 = grid.MAP_LONLAT
        center = ((lon0 + lon1) / 2, (lat0 + lat1) / 2, 10)
        paths = []
        for w, n in ((w_v, counts["valley"]), (w_d, counts["detail"])):
            if n:
                w.finish((lon0, lat0, lon1, lat1), center)
                paths.append(w.path)
            else:
                w.abort()
                paths.append(None)
    except BaseException:
        w_v.abort()
        w_d.abort()
        raise
    log(f"assembled: valley {counts['valley']} tiles, detail {counts['detail']} tiles ({digest[:12]})")
    entry = None if partial else tiles.painted_entry(plan, digest)
    return paths[0], paths[1], entry, digest


def readback(pmtiles_path, z, bounds_m, out_path):
    """The zoom-z tiles of a PMTiles file covering bounds_m (grid metres) mosaicked into a GeoTIFF in Web Mercator,
    as the map will show them (WebP and all), for the review sheets; tiles the file lacks are left clear. Returns the
    tiles found and missing."""
    from basemap.landscape import pmtiles as PM
    xs, ys = tiles.tile_range(grid.lonlat_of(bounds_m), z)
    nx, ny = len(xs), len(ys)
    arr = np.zeros((4, ny * SIZE, nx * SIZE), np.uint8)
    found = missing = 0
    for j, ty in enumerate(ys):
        for i, tx in enumerate(xs):
            data = PM.tile_data(pmtiles_path, z, tx, ty)
            if data is None:
                missing += 1
                continue
            t = decode(data)
            arr[:3, j * SIZE:(j + 1) * SIZE, i * SIZE:(i + 1) * SIZE] = np.moveaxis(t, -1, 0)
            arr[3, j * SIZE:(j + 1) * SIZE, i * SIZE:(i + 1) * SIZE] = 255
            found += 1
    w, _s, _e, n = tiles.tile_mercator(z, xs[0], ys[0])
    px = (2 * tiles._MERC_MAX / 2 ** z) / SIZE
    ds = gdal.GetDriverByName("GTiff").Create(out_path, nx * SIZE, ny * SIZE, 4, gdal.GDT_Byte,
                                              options=["COMPRESS=DEFLATE", "TILED=YES", "PHOTOMETRIC=RGB",
                                                       "ALPHA=YES"])
    ds.SetGeoTransform((w, px, 0.0, n, 0.0, -px))
    ds.SetProjection(_srs(3857))
    for b in range(4):
        ds.GetRasterBand(b + 1).WriteArray(arr[b])
    ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    ds = None
    return found, missing


def first_load(view_tiles, sizes, first_request=16384):
    """The default view's first load from a full valley file, estimated from tile sizes (G1a paints only some of its
    tiles): view_tiles [(z, x, y)] as the map library asked for them (app/scripts/ground-firstload.mjs), sizes
    {(z, x, y): bytes} of the painted tiles. The full file's directory is laid out as pmtw writes it, with every valley
    tile at a size drawn (seeded) from the painted ones at its zoom, or from all of them, so the directory compresses
    as a real one would, to find the leaf directories the view reads. Returns {requests, bytes, tiles, tile_bytes,
    leaves, leaf_bytes, missing, ok, budget}."""
    import random
    from basemap.landscape import pmtiles as PM
    by_zoom = {}
    for (z, _x, _y), n in sizes.items():
        by_zoom.setdefault(z, []).append(n)
    every = sorted(n for v in by_zoom.values() for n in v) or [40000]
    med = {z: sorted(v)[len(v) // 2] for z, v in by_zoom.items()}
    rnd = random.Random(15)
    entries, off = [], 0
    ids = sorted(PM.tile_id(z, x, y) for z in range(tiles.VALLEY_ZOOMS[0], tiles.VALLEY_ZOOMS[1] + 1)
                 for x, y in tiles.valley_tiles(z))
    for tid in ids:
        z = PM.zxy(tid)[0]
        n = rnd.choice(by_zoom.get(z, every))
        entries.append(PM.Entry(tid, off, n, 1))
        off += n
    root, leaves = pmtw.directories(entries)
    leaf_bytes, touched = 0, set()
    if leaves:
        roots = PM.decode_directory(gzip.decompress(root))
        for z, x, y in view_tiles:
            tid = PM.tile_id(z, x, y)
            e = max((e for e in roots if e.tile_id <= tid), key=lambda e: e.tile_id)
            if e.run_length:                                    # a tile in the root itself: no leaf to read
                continue
            if e.tile_id not in touched:
                touched.add(e.tile_id)
                leaf_bytes += e.length
    missing = [t for t in view_tiles if t not in sizes]
    tile_bytes = sum(sizes.get(t, med.get(t[0], every[len(every) // 2])) for t in view_tiles)
    head = first_request                       # the client's first read: the header and root directory, 16 KiB
    total = head + leaf_bytes + tile_bytes
    requests = 1 + len(touched) + len(view_tiles)
    b = tiles.BUDGET["valleyDefault"]
    return {"requests": requests, "bytes": total, "tiles": len(view_tiles), "tile_bytes": tile_bytes,
            "first_request": head, "leaves": len(touched), "leaf_bytes": leaf_bytes, "root_bytes": len(root),
            "missing": [list(t) for t in missing], "ok": total <= b["maxBytes"] and requests <= b["maxRequests"],
            "budget": b}


def _stopped(signum, _frame):
    raise SystemExit(128 + signum)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("paint", help="paint blocks into DIR/blocks/")
    p.add_argument("--out", required=True)
    p.add_argument("--archive", help="default $TVT_ARCHIVE")
    p.add_argument("--boxes", action="store_true", help="the z13 blocks near the ten boxes")
    p.add_argument("--valley", action="store_true", help="every z13 block (G1b), or those in --bounds")
    p.add_argument("--bounds", help="west,south,east,north in grid metres (with --valley)")
    p.add_argument("--detail", action="store_true", help="the detail file's z17 tiles")
    p.add_argument("--view", help="zooms painted straight from a coarser level, e.g. 8,9,10")
    p.add_argument("--view-tiles", help="a JSON list of [z, x, y] to paint with --view (default: every valley tile)")
    p.add_argument("--quality", type=int, default=tiles.QUALITY)
    p.add_argument("--limit", type=int, help="stop after this many blocks (a chunk at a time)")
    p.add_argument("--pyramid", action="store_true", help="z12-z8 from the kept z13 tiles, after --valley")
    p = sub.add_parser("assemble", help="the PMTiles files from DIR/blocks/")
    p.add_argument("--out", required=True)
    p.add_argument("--archive", help="default $TVT_ARCHIVE")
    p.add_argument("--partial", action="store_true", help="name the files -partial (no manifest entry)")
    p.add_argument("--tiles", help="a tiles folder: write the files there and switch the manifest's ground entry")
    p = sub.add_parser("readback", help="a file's tiles around the boxes as GeoTIFFs, for the review sheets")
    p.add_argument("--pmtiles", required=True)
    p.add_argument("--zoom", type=int, required=True)
    p.add_argument("--out", required=True, help="a folder: <box>-z<zoom>.tif")
    p.add_argument("--margin", type=float, default=100.0, help="metres around each box")
    p.add_argument("--all", action="store_true", help="one file of the whole map box (low zooms) instead")
    p = sub.add_parser("estimate", help="the default view's first load from a full valley file, from tile sizes")
    p.add_argument("--pmtiles", required=True, help="a valley file holding (at least) the view's tiles")
    p.add_argument("--view", required=True, help="app/scripts/ground-firstload.mjs's result (JSON, --out)")
    args = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _stopped)
    if args.cmd == "estimate":
        from basemap.landscape import pmtiles as PM
        with open(args.view) as f:
            view = [tuple(int(v) for v in t.split("/")) for t in json.load(f)["tiles"]]
        print(json.dumps(first_load(view, PM.tile_sizes(args.pmtiles)), indent=1))
        return 0
    if args.cmd == "readback":
        os.makedirs(args.out, exist_ok=True)
        if args.all:
            path = os.path.join(args.out, f"valley-z{args.zoom}.tif")
            found, missing = readback(args.pmtiles, args.zoom, grid.EXTENT, path)
            print(f"  the map box: {found} tiles, {missing} missing -> {path}")
            return 0
        for b in grid.boxes():
            w, s, e, n = b.utm
            m = args.margin
            path = os.path.join(args.out, f"{b.id}-z{args.zoom}.tif")
            found, missing = readback(args.pmtiles, args.zoom, (w - m, s - m, e + m, n + m), path)
            print(f"  {b.id}: {found} tiles, {missing} missing -> {path}")
        return 0
    archive = args.archive or os.environ.get("TVT_ARCHIVE")
    try:
        plan = plan_of(archive)
    except (TileError, inputs.InputError, M.ManifestError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    if args.cmd == "assemble":
        if args.tiles and args.partial:
            print("refused: a partial set of tiles is never switched in", file=sys.stderr)
            return 2
        v, d, entry, digest = assemble(args.out, plan, args.partial)
        if args.tiles:
            for p in (v, d):
                shutil.copy2(p, os.path.join(args.tiles, os.path.basename(p) + ".part"))
                os.replace(os.path.join(args.tiles, os.path.basename(p) + ".part"),
                           os.path.join(args.tiles, os.path.basename(p)))
            tiles.update_manifest(args.tiles, entry)
        print(json.dumps({"valley": v, "detail": d, "digest": digest}))
        return 0
    painter = paint.Painter.from_plan(plan)
    blocks = Blocks(args.out)
    with open(os.path.join(args.out, "paint.json"), "w") as f:
        json.dump(paint.report(painter, plan), f, indent=1)
    t0, n_blocks, n_tiles = time.time(), 0, 0

    def tick(label, k):
        nonlocal n_blocks, n_tiles
        n_blocks += 1
        n_tiles += k
        if n_blocks % 10 == 0 or k:
            print(f"  {label}: {k} tiles ({n_blocks} blocks, {n_tiles} tiles, {time.time() - t0:.0f} s)", flush=True)
        if args.limit and n_blocks >= args.limit:
            raise StopIteration

    try:
        if args.boxes or args.valley:
            todo = blocks_near_boxes(BLOCK_Z) if args.boxes else _valley_blocks(args.bounds)
            for x, y in todo:
                tick(f"z{BLOCK_Z} {x}/{y}", paint_valley_block(painter, blocks, x, y, args.quality))
            if args.pyramid:
                pyramid(blocks, args.quality)
        if args.detail:
            for x, y in detail_blocks():
                tick(f"detail z{DETAIL_BLOCK_Z} {x}/{y}", paint_detail_block(painter, blocks, x, y, args.quality))
        if args.view:
            zs = [int(z) for z in args.view.split(",")]
            want = None
            if args.view_tiles:
                with open(args.view_tiles) as f:
                    want = {tuple(t) for t in json.load(f)}
            for z in zs:
                for x, y in tiles.valley_tiles(z):
                    if want is None or (z, x, y) in want:
                        tick(f"view z{z} {x}/{y}", paint_view_tile(painter, blocks, z, x, y, args.quality))
    except StopIteration:
        print(f"stopped at --limit {args.limit}; run again to go on", flush=True)
    print(f"painted {n_tiles} tiles in {n_blocks} blocks, {time.time() - t0:.0f} s", flush=True)
    return 0


def _valley_blocks(bounds):
    if bounds:
        w, s, e, n = (float(v) for v in bounds.split(","))
        xs, ys = tiles.tile_range(grid.lonlat_of((w, s, e, n)), BLOCK_Z)
    else:
        xs, ys = valley_set(BLOCK_Z)
    return [(x, y) for y in ys for x in xs]


if __name__ == "__main__":
    sys.exit(main())
