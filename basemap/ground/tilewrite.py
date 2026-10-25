"""The ground's tile writer (G1a): painted windows to 512 px WebP tiles in two PMTiles files, tile by tile, never a
full mosaic. Runs in the worker image (GDAL, NumPy, SciPy, Pillow).

    python basemap/ground/tilewrite.py paint --out DIR [--archive $TVT_ARCHIVE] (--boxes | --valley [--bounds ...])
        [--detail] [--view z8,z9,z10]          # paint blocks into DIR/blocks/ (resumable: a finished block is kept)
    python basemap/ground/tilewrite.py assemble --out DIR [--partial | --tiles TILES]   # -> ground-<digest>.pmtiles

**Blocks.** The valley file is painted a z13 tile at a time: its window of the 2 m painter grid
(tiles.tile_window) is painted with the painter's halo, warped onto the z13 tile's Web Mercator square at z15's
pixel size (2,048 px), and cut into its 16 z15 tiles; its z14 tiles are 2 x 2 averages of those pixels, and its z13
tile of the z14 ones. The z13 tile is also kept losslessly (PNG), and z12 to z8 are made from those, four children at
a time (`pyramid`). The detail file is painted a z15 tile at a time at 0.5 m (the box classes' own grid) and cut into
z17 tiles. Each finished block is a file in DIR/blocks/ (its tiles, WebP, with an index), written atomically, so a
stopped run picks up where it was, and the PMTiles files are assembled from the blocks at the end (`assemble`).

**One run, one digest.** DIR/run.json records what the run paints from: the digest (tiles.digest over the spec, the
inputs, PAINTER_VERSION and the code, painter_id()), the inputs by name and the painter's report. A run resumes only
when the archive's inputs and the code still give that digest, and every block records it too, so a folder never
mixes paint from two sets of inputs; `assemble` refuses blocks painted for another digest than the inputs give now,
and refuses to make a whole pair of files (one the manifest may switch in) unless every tile of the spec is there.

**What G1a paints** (valley-wide runs are G1b's): --boxes, the z13 blocks touching the ten boxes; --detail, the
detail file's z17 tiles; --view, given zooms painted straight from a coarser level of the painter grid (z10 from
10 m, z9 from 20 m, z8 from 40 m), which is what a first load at the default view fetches, for the first-load
estimate (`first_load`). A file assembled from these is partial: its name says `-partial` and nothing switches it in.

Tiles: tiles.TILE_SIZE px, lossy WebP at tiles.QUALITY (Pillow, method 6), opaque. Pixels outside the grid are the
flat Valley colour (the painter's).
"""

import argparse
import gzip
import hashlib
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

from basemap import lock  # noqa: E402
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

CODE = tiles.code_digest(__file__)   # this module's code and every basemap.ground module it reads (paint.py, ...)
RUN = "run.json"


def painter_id():
    """The painter's version as the tiles' digest names it: PAINTER_VERSION and the code's sha256 (tiles.code_digest),
    so an edit to the painter or the writer gives a new name even when PAINTER_VERSION stays."""
    return f"{paint.PAINTER_VERSION} code {CODE}"


def run_digest(plan):
    """The digest the plan and this code give (tiles.digest)."""
    return tiles.digest(plan, painter=painter_id())


class Blocks:
    """DIR/blocks/: one file per finished block (<name>.blk: its tiles' WebP bytes back to back, <name>.json: the
    index and the digest it was painted for), written atomically; DIR/png/ the lossless z13 and pyramid tiles; and
    DIR/run.json, what the run paints from: the digest (inputs, painter and code), the inputs by name and the
    painter's report. One folder holds one digest's blocks: begin() refuses a folder painted from anything else, and
    assemble() refuses blocks that don't carry the digest the archive's inputs give now."""

    def __init__(self, out, digest=None):
        self.out = out
        self.dir = os.path.join(out, "blocks")
        self.png = os.path.join(out, "png")
        self.digest = digest
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(self.png, exist_ok=True)

    def run(self):
        """run.json, or None."""
        path = os.path.join(self.out, RUN)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def names(self):
        return sorted(n[:-5] for n in os.listdir(self.dir) if n.endswith(".json"))

    def begin(self, stamp):
        """Start or resume a run painting from stamp (run_stamp()): its digest must be the folder's, and a folder of
        blocks with no run.json (of unknown origin) is refused. Raises TileError."""
        have = self.run()
        if have is not None and have.get("digest") != stamp["digest"]:
            raise TileError(f"{self.out} holds blocks painted from {str(have.get('digest'))[:12]} (painter "
                            f"{have.get('painter')}, inputs {', '.join(have.get('inputs') or [])}); the archive's "
                            f"inputs and this painter give {stamp['digest'][:12]} (inputs "
                            f"{', '.join(stamp['inputs'])}). Paint into a new folder: a run never mixes the two")
        if have is None and self.names():
            raise TileError(f"{self.out} holds blocks with no {RUN}: what painted them is unknown. Paint into a new "
                            "folder")
        self.digest = stamp["digest"]
        if have is None:
            path = os.path.join(self.out, RUN)
            with open(path + ".part", "w", encoding="utf-8") as f:
                json.dump(dict(stamp, started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), f, indent=1)
            os.replace(path + ".part", path)

    def done(self, name):
        """Whether a block is finished, for this run's digest (a block with another one is refused, never kept)."""
        path = os.path.join(self.dir, name + ".json")
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as f:
            got = json.load(f).get("digest")
        if got != self.digest:
            raise TileError(f"block {name} in {self.out} was painted for {str(got)[:12]}, this run is for "
                            f"{str(self.digest)[:12]}")
        return True

    def write(self, name, tiles_bytes, file="valley", gaps=0):
        """A finished block: its tiles {(z, x, y): bytes}, which file they go to, and (the pyramid's) how many children
        it lacked."""
        if not self.digest:
            raise TileError("a block is written for a digest: begin() the run first")
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
            json.dump({"file": file, "digest": self.digest, "gaps": int(gaps), "tiles": index}, f)
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

    def index(self):
        """{name: {"file", "digest", "gaps", "tiles": [(z, x, y)]}} of every finished block, without its tiles' bytes."""
        out = {}
        for name in self.names():
            with open(os.path.join(self.dir, name + ".json")) as f:
                idx = json.load(f)
            out[name] = {"file": idx["file"], "digest": idx.get("digest"), "gaps": idx.get("gaps", 0),
                         "tiles": [tuple(t[:3]) for t in idx["tiles"]]}
        return out

    def all(self, names=None):
        """Yield (file, z, x, y, bytes) of every finished block's tiles (or those of `names`), a block at a time, so
        only one block's bytes are in memory."""
        for name in (self.names() if names is None else names):
            with open(os.path.join(self.dir, name + ".json")) as f:
                idx = json.load(f)
            with open(os.path.join(self.dir, name + ".blk"), "rb") as f:
                data = f.read()
            for z, x, y, off, ln in idx["tiles"]:
                yield idx["file"], z, x, y, data[off:off + ln]
            del data


def run_stamp(plan, painter=None):
    """What a run paints from, for run.json: the digest, the painter's version and code, the inputs by name, and the
    painter's report (paint.report: the flat soil types among it), which the files' metadata and entry carry."""
    return {"digest": run_digest(plan), "painter": paint.PAINTER_VERSION, "code": CODE, "spec": tiles.SPEC_VERSION,
            "inputs": plan.refs + [f"raw/{n}@{plan.versions[n]}" for n in plan.raw_names],
            "paint": paint.report(painter, plan) if painter is not None else None}


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
    flat Valley colour. Each zoom's block records its gaps: children inside the map box that weren't painted yet (a
    whole file refuses a pyramid with any: run it again once every z13 block is painted). Returns the tiles written."""
    lowest = tiles.VALLEY_ZOOMS[0] if lowest is None else lowest
    flat = np.array([int(tiles.FLAT["valley"][i:i + 2], 16) for i in (1, 3, 5)], np.uint8)
    n = 0
    for z in range(BLOCK_Z - 1, lowest - 1, -1):
        xs, ys = valley_set(z)
        cxs, cys = valley_set(z + 1)
        out, gaps = {}, 0
        for ty in ys:
            for tx in xs:
                at = [(2 * tx + i, 2 * ty + j) for j in (0, 1) for i in (0, 1)]
                kids = [blocks.read_png(z + 1, cx, cy) for cx, cy in at]
                if all(k is None for k in kids):
                    continue
                gaps += sum(1 for (cx, cy), k in zip(at, kids) if k is None and cx in cxs and cy in cys)
                kids = [k if k is not None else np.broadcast_to(flat, (SIZE, SIZE, 3)) for k in kids]
                big = np.concatenate([np.concatenate(kids[0:2], axis=1), np.concatenate(kids[2:4], axis=1)], axis=0)
                t = halve(np.ascontiguousarray(big))
                blocks.keep_png(z, tx, ty, t)
                out[(z, tx, ty)] = webp(t, quality)
        if out:
            blocks.write(f"p{z}", out, gaps=gaps)
            n += len(out)
            log(f"  pyramid z{z}: {len(out)} tiles" + (f" ({gaps} children not painted yet)" if gaps else ""))
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

def sha256_of(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def photo_of(naip_dir=None, dem=None):
    """(paint.Photo or None, the raw-input versions it adds) from soils' COG folder (naip2025_2m.tif, its sidecar
    naip2025_2m.json and flights.fgb) and optionally a DEM: naip-2m is named by the sidecar's sha256 (the COG's, written
    when it was assembled), 3dep by the DEM's own. Without a folder there is no photo, and the ground is G1a's plus the
    procedural noise."""
    if not naip_dir:
        if dem:
            raise TileError("--dem needs --naip-2m: the DEM only normalises the photo's light")
        return None, {}
    cog = os.path.join(naip_dir, "naip2025_2m.tif")
    side = os.path.join(naip_dir, "naip2025_2m.json")
    for path in (cog, side):
        if not os.path.isfile(path):
            raise TileError(f"{naip_dir} has no {os.path.basename(path)} (soils' photo build: plugins/soils/build/photo_stats.py)")
    with open(side, encoding="utf-8") as f:
        sha = (json.load(f) or {}).get("sha256")
    if not sha:
        raise TileError(f"{side} names no sha256 for the COG")
    flights = os.path.join(naip_dir, "flights.fgb")
    if dem and not os.path.isfile(dem):
        raise TileError(f"--dem: {dem} isn't there")
    versions = paint.versions(**{"naip-2m": sha, "3dep": sha256_of(dem) if dem else None})
    return paint.Photo(cog, flights if os.path.isfile(flights) else None, dem), versions


def plan_of(archive, versions=None):
    """The ground's plan from the archive's exports (inputs.resolve), refused unless it can be painted. versions: the
    raw inputs the painter adds (photo_of)."""
    plan = inputs.resolve(inputs.exports(archive), versions=paint.versions(**(versions or {})))
    if plan.status != "painted":
        raise TileError(plan.reason)
    return plan


def expected():
    """{"valley": {(z, x, y)}, "detail": {(z, x, y)}}: every tile a whole pair of files holds (tiles.counts())."""
    return {"valley": {(z, x, y) for z in range(tiles.VALLEY_ZOOMS[0], tiles.VALLEY_ZOOMS[1] + 1)
                       for x, y in tiles.valley_tiles(z)},
            "detail": {(z, x, y) for z in range(tiles.DETAIL_ZOOMS[0], tiles.DETAIL_ZOOMS[1] + 1)
                       for x, y in tiles.detail_tiles(z)}}


def _by_zoom(keys):
    zs = {}
    for z, _x, _y in keys:
        zs[z] = zs.get(z, 0) + 1
    return ", ".join(f"z{z} {n}" for z, n in sorted(zs.items()))


def assemble(out, plan, partial, log=print):
    """The PMTiles files from DIR/blocks/: (valley path, detail path, entry, digest). The blocks must all have been
    painted for the digest the plan and this code give now (run.json and each block say which), so a file's name never
    claims inputs its tiles weren't painted from. A whole pair (partial false) must hold every tile of the spec
    (expected()): the valley file's z8-z15 from the z13 blocks and the pyramid (view tiles, painted for the first-load
    estimate, are left out), the detail file's z17. Names carry the digest; a partial set says so in its names, keeps
    the view tiles and gets no tiles-manifest entry. Raises TileError."""
    blocks = Blocks(out)
    digest = run_digest(plan)
    run = blocks.run()
    if run is None:
        raise TileError(f"{out} has no {RUN}: what painted its blocks is unknown")
    if run.get("digest") != digest:
        raise TileError(f"{out}'s blocks were painted from {str(run.get('digest'))[:12]} (painter {run.get('painter')}, "
                        f"inputs {', '.join(run.get('inputs') or [])}); the archive's inputs and this painter give "
                        f"{digest[:12]} (inputs {', '.join(plan.refs)}). Paint them again into a new folder")
    index = blocks.index()
    stale = sorted(n for n, b in index.items() if b["digest"] != digest)
    if stale:
        raise TileError(f"{len(stale)} block(s) in {out} weren't painted for {digest[:12]} ({', '.join(stale[:5])}"
                        f"{', ...' if len(stale) > 5 else ''})")
    names = [n for n, b in index.items() if partial or b["file"] != "view"]
    if not partial:
        want = expected()
        have = {"valley": set(), "detail": set()}
        for n in names:
            have["detail" if index[n]["file"] == "detail" else "valley"].update(index[n]["tiles"])
        gaps = {k: want[k] - have[k] for k in want}
        if gaps["valley"] or gaps["detail"]:
            raise TileError("a whole pair of files holds every tile of the spec, and these blocks lack "
                            + "; ".join(f"{len(g):,} {k} tiles ({_by_zoom(g)})" for k, g in gaps.items() if g)
                            + ": paint the rest (paint --valley --pyramid --detail, resumable), or assemble --partial")
        early = sorted(n for n in names if index[n]["gaps"])
        if early:
            raise TileError(f"the pyramid ({', '.join(early)}) was built before every z13 block was painted: run "
                            "paint --valley --pyramid again")
        skipped = len(index) - len(names)
        if skipped:
            log(f"  left out {skipped} view block(s): the whole file's low zooms are the pyramid's")
    valley_name, detail_name = tiles.file_names(digest)
    if partial:
        valley_name = valley_name.replace(".pmtiles", "-partial.pmtiles")
        detail_name = detail_name.replace(".pmtiles", "-partial.pmtiles")
    rep = run.get("paint") or {}
    notes = paint.notes(rep)
    meta = {"name": "ground", "attribution": "; ".join(plan.credits), "licence": plan.licence,
            "republish": plan.republish, "inputs": plan.refs + [f"raw/{n}@{plan.versions[n]}" for n in plan.raw_names],
            "fallbacks": [f"{c.use.ref}: {c.use.fallback}" for c in plan.choices if c.fallback] + notes,
            "painter": paint.PAINTER_VERSION, "code": CODE, "digest": digest, "spec": tiles.SPEC_VERSION,
            "partial": bool(partial), "paint": rep,
            "about": "The painted Valley ground (basemap/ground). ODbL produced work built from public inputs."}
    w_v = pmtw.Writer(os.path.join(out, valley_name), 4, dict(meta, file="valley"))
    w_d = pmtw.Writer(os.path.join(out, detail_name), 4, dict(meta, file="detail"))
    seen = set()
    counts = {"valley": 0, "detail": 0}
    try:
        for file, z, x, y, data in blocks.all(names):
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
    entry = None if partial else tiles.painted_entry(plan, digest, notes=notes)
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
    p.add_argument("--limit", type=int, help="stop after painting this many blocks (a chunk at a time; blocks done "
                                             "before are kept and don't count)")
    p.add_argument("--pyramid", action="store_true", help="z12-z8 from the kept z13 tiles, after --valley")
    p.add_argument("--naip-2m", help="soils' 2 m COG folder (naip2025_2m.tif, .json, flights.fgb): G1b's photo variation; "
                                     "the same value for paint and assemble")
    p.add_argument("--dem", help="a DEM GeoTIFF that normalises the photo's light by slope and aspect (with --naip-2m)")
    p = sub.add_parser("assemble", help="the PMTiles files from DIR/blocks/")
    p.add_argument("--out", required=True)
    p.add_argument("--archive", help="default $TVT_ARCHIVE")
    p.add_argument("--partial", action="store_true", help="name the files -partial (no manifest entry)")
    p.add_argument("--tiles", help="a tiles folder: write the files there and switch the manifest's ground entry")
    p.add_argument("--naip-2m", help="soils' 2 m COG folder (naip2025_2m.tif, .json, flights.fgb): G1b's photo variation; "
                                     "the same value for paint and assemble")
    p.add_argument("--dem", help="a DEM GeoTIFF that normalises the photo's light by slope and aspect (with --naip-2m)")
    p = sub.add_parser("readback", help="a file's tiles around the boxes as GeoTIFFs, for the review sheets")
    p.add_argument("--pmtiles", required=True)
    p.add_argument("--zoom", type=int, required=True)
    p.add_argument("--out", required=True, help="a folder: <box>-z<zoom>.tif")
    p.add_argument("--margin", type=float, default=100.0, help="metres around each box")
    p.add_argument("--all", action="store_true", help="one file of the whole map box (low zooms) instead")
    p = sub.add_parser("estimate", help="the default view's first load from a full valley file, from tile sizes")
    p.add_argument("--pmtiles", required=True, help="a valley file holding (at least) the view's tiles")
    p.add_argument("--view", required=True, help="app/scripts/ground-firstload.mjs's result (JSON, --out)")
    p.add_argument("--budget", action="store_true", help="exit 1 when the estimate is over the budget (a check)")
    args = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _stopped)
    if args.cmd == "estimate":
        from basemap.landscape import pmtiles as PM
        with open(args.view) as f:
            view = [tuple(int(v) for v in t.split("/")) for t in json.load(f)["tiles"]]
        est = first_load(view, PM.tile_sizes(args.pmtiles))
        print(json.dumps(est, indent=1))
        if args.budget and not est["ok"]:
            print(f"over the budget: {est['bytes']:,} bytes in {est['requests']} requests (at most "
                  f"{est['budget']['maxBytes']:,} and {est['budget']['maxRequests']})", file=sys.stderr)
            return 1
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
        photo, extra = photo_of(args.naip_2m, args.dem)
        plan = plan_of(archive, extra)
    except (TileError, inputs.InputError, M.ManifestError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    if args.cmd == "assemble":
        if args.tiles and args.partial:
            print("refused: a partial set of tiles is never switched in", file=sys.stderr)
            return 2
        if args.tiles:
            try:
                lock.ensure(args.tiles)  # fail now, not after the files are copied
            except OSError as err:
                print(f"refused: {err}", file=sys.stderr)
                return 2
        try:
            v, d, entry, digest = assemble(args.out, plan, args.partial)
            if args.tiles:
                switch_in(args.tiles, (v, d), entry)
        except TileError as err:
            print(f"refused: {err}", file=sys.stderr)
            return 2
        print(json.dumps({"valley": v, "detail": d, "digest": digest}))
        return 0
    try:
        painter = paint.Painter.from_plan(plan, photo=photo)
        blocks = Blocks(args.out)
        blocks.begin(run_stamp(plan, painter))
    except (TileError, paint.PaintError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    t0, n_blocks, n_tiles, n_kept = time.time(), 0, 0, 0

    def tick(label, k):
        """One block visited: k tiles painted, or 0 when it was already done (kept). --limit counts painted blocks,
        so each run of a chunked job paints that many more."""
        nonlocal n_blocks, n_tiles, n_kept
        if not k:
            n_kept += 1
            return
        n_blocks += 1
        n_tiles += k
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
    except TileError as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    print(f"painted {n_tiles} tiles in {n_blocks} blocks ({n_kept} done before, kept), {time.time() - t0:.0f} s",
          flush=True)
    return 0


def switch_in(tiles_dir, paths, entry):
    """Copy a whole pair of files into the tiles folder and switch the manifest's ground entry to them, last. A file
    of the same name already there must be the same bytes (names are versions: never overwritten)."""
    for p in paths:
        dest = os.path.join(tiles_dir, os.path.basename(p))
        if os.path.exists(dest):
            if not _same_file(p, dest):
                raise TileError(f"{dest} exists with other bytes: a name is a version, never overwritten")
            continue
        shutil.copy2(p, dest + ".part")
        os.replace(dest + ".part", dest)
    tiles.update_manifest(tiles_dir, entry)


def _same_file(a, b):
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def _valley_blocks(bounds):
    if bounds:
        w, s, e, n = (float(v) for v in bounds.split(","))
        xs, ys = tiles.tile_range(grid.lonlat_of((w, s, e, n)), BLOCK_Z)
    else:
        xs, ys = valley_set(BLOCK_Z)
    return [(x, y) for y in ys for x in xs]


if __name__ == "__main__":
    sys.exit(main())
