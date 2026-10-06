#!/usr/bin/env python3
"""Re-encode a terrain-RGB PMTiles file as lossless WebP, with elevations rounded by zoom.

The terrain from terrain.py is 512-px PNG terrain-RGB (Mapbox encoding, 0.1 m
steps), and it is most of every first load (docs/14 §14.9). This rewrites it
tile for tile, without going back to the DEM:

  1. Read every tile of the input PMTiles (a small v3 reader below; stdlib only).
  2. Decode the PNG, round each elevation to a step that depends on the zoom
     (by default 1 m up to z10, 0.5 m at z11, 0.4 m at z12, 0.2 m at z13,
     and no rounding from z14), and encode the tile as lossless WebP.
     Rounding happens on the encoded integer (0.1 m units, offset 10,000 m),
     so the error is exact: at most half the step. Each new tile is decoded
     again and checked against what was meant to be written.
  3. Write the tiles to MBTiles with the input's metadata (now `format: webp`)
     and convert with `pmtiles convert`, then put the input's exact bounds and
     center back into the new header.
  4. Check the result against the input: the same tile IDs (so the same tile
     count and zoom range), every tile decodes, and the largest elevation
     error per zoom on a sample, which must be at most half that zoom's step.
  5. Optionally write a copy of manifest.json that points at the new file.

The output gets a new, versioned name (terrain-webp-YYYYMMDD.pmtiles by
default) and never replaces an existing file, so browsers and caches can
treat it as immutable and the old file stays for a rollback. Switching the app
over is a separate step: put the manifest copy in place of manifest.json.

Needs numpy, GDAL's Python bindings with the PNG and WEBP drivers, and the
pmtiles CLI, like terrain.py. On Ubuntu, run it with the system Python that
matches the python3-gdal package (here: python3.12).

Usage:
  python3.12 basemap/terrain_reencode.py data/tiles/terrain.pmtiles
      # -> data/tiles/terrain-webp-<today>.pmtiles, report on stdout
  python3.12 basemap/terrain_reencode.py data/tiles/terrain.pmtiles --out data/dev/t/terrain-webp-x.pmtiles \\
      --manifest-out data/dev/t/manifest.json
      # also write a manifest copy (next to the output) that uses the new file
  python3.12 basemap/terrain_reencode.py IN --steps=-11:1,12-13:0.5,14-:0.2
      # rounding per zoom range, in metres (0 = keep every 0.1 m step); this
      # one is the first guess, which terraced flat ground at z13 and z15
  python3.12 basemap/terrain_reencode.py IN --check OUT --sample 0
      # only compare an existing output with its input (0 = every tile)
"""

import argparse
import datetime
import gzip
import json
import math
import multiprocessing
import os
import random
import sqlite3
import struct
import subprocess
import sys
import time
import zlib

# --- PMTiles v3 (https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md) -----------------

HEADER_LEN = 127
TILE_TYPES = {0: "unknown", 1: "mvt", 2: "png", 3: "jpg", 4: "webp", 5: "avif"}
COMPRESSIONS = {0: "unknown", 1: "none", 2: "gzip", 3: "brotli", 4: "zstd"}
# Header bytes 102-126: bounds (4 x int32), center zoom (uint8), center lon/lat (2 x int32), all e7.
PLACE = slice(102, 127)


def parse_header(b):
    if len(b) < HEADER_LEN or b[:7] != b"PMTiles":
        raise ValueError("not a PMTiles archive")
    if b[7] != 3:
        raise ValueError(f"PMTiles version {b[7]}; only version 3 is supported")
    (root_off, root_len, meta_off, meta_len, leaf_off, leaf_len, data_off, data_len,
     addressed, entries, contents) = struct.unpack_from("<11Q", b, 8)
    clustered, internal, tile_comp, tile_type, minzoom, maxzoom = struct.unpack_from("<6B", b, 96)
    min_lon, min_lat, max_lon, max_lat = struct.unpack_from("<4i", b, 102)
    center_zoom = b[118]
    center_lon, center_lat = struct.unpack_from("<2i", b, 119)
    return {
        "root_offset": root_off, "root_length": root_len, "metadata_offset": meta_off,
        "metadata_length": meta_len, "leaf_offset": leaf_off, "leaf_length": leaf_len,
        "data_offset": data_off, "data_length": data_len, "addressed_tiles": addressed,
        "tile_entries": entries, "tile_contents": contents, "clustered": bool(clustered),
        "internal_compression": internal, "tile_compression": tile_comp, "tile_type": tile_type,
        "minzoom": minzoom, "maxzoom": maxzoom,
        "bounds_e7": (min_lon, min_lat, max_lon, max_lat), "center_zoom": center_zoom,
        "center_e7": (center_lon, center_lat),
    }


def _varint(buf, pos):
    shift = result = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7


def parse_directory(raw):
    """[(tile_id, offset, length, run_length)]; run_length 0 marks a leaf directory."""
    n, pos = _varint(raw, 0)
    ids, runs, lengths, offsets = [], [], [], []
    last = 0
    for _ in range(n):
        d, pos = _varint(raw, pos)
        last += d
        ids.append(last)
    for _ in range(n):
        v, pos = _varint(raw, pos)
        runs.append(v)
    for _ in range(n):
        v, pos = _varint(raw, pos)
        lengths.append(v)
    for i in range(n):
        v, pos = _varint(raw, pos)
        # 0 means "right after the previous entry".
        offsets.append(offsets[i - 1] + lengths[i - 1] if v == 0 and i > 0 else v - 1)
    return list(zip(ids, offsets, lengths, runs))


def _rotate(n, x, y, rx, ry):
    if ry == 0:
        if rx == 1:
            x, y = n - 1 - x, n - 1 - y
        x, y = y, x
    return x, y


def zxy_to_tileid(z, x, y):
    """PMTiles tile ID: tiles of all lower zooms first, then the Hilbert index within zoom z."""
    if z > 31 or not (0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise ValueError(f"tile {z}/{x}/{y} out of range")
    acc = ((1 << (2 * z)) - 1) // 3          # 4^0 + ... + 4^(z-1)
    n = 1 << z
    d = 0
    s = n >> 1
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        x, y = _rotate(s, x, y, rx, ry)
        s >>= 1
    return acc + d


def tileid_to_zxy(i):
    z = 0
    acc = 0
    while True:
        n_tiles = 1 << (2 * z)
        if i < acc + n_tiles:
            break
        acc += n_tiles
        z += 1
        if z > 31:
            raise ValueError(f"tile id {i} out of range")
    t = i - acc
    x = y = 0
    s = 1
    n = 1 << z
    while s < n:
        rx = 1 & (t >> 1)
        ry = 1 & (t ^ rx)
        x, y = _rotate(s, x, y, rx, ry)
        x += s * rx
        y += s * ry
        t >>= 2
        s <<= 1
    return z, x, y


class PMTiles:
    """A read-only PMTiles v3 archive on local disk."""

    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        with open(path, "rb") as f:
            self.header = parse_header(f.read(HEADER_LEN))
        h = self.header
        if h["internal_compression"] not in (1, 2):
            raise ValueError(f"internal compression {COMPRESSIONS.get(h['internal_compression'])} isn't supported")
        if h["tile_compression"] not in (0, 1):
            raise ValueError("compressed tile data (gzip etc.) isn't expected for image tiles")
        self.metadata = json.loads(self._internal(h["metadata_offset"], h["metadata_length"]) or b"{}")

    def _read(self, offset, length):
        with open(self.path, "rb") as f:
            f.seek(offset)
            data = f.read(length)
        if len(data) != length:
            raise ValueError(f"{self.path}: short read at {offset}")
        return data

    def _internal(self, offset, length):
        raw = self._read(offset, length)
        return gzip.decompress(raw) if self.header["internal_compression"] == 2 else raw

    def entries(self):
        """Every tile entry, in tile ID order: (tile_id, absolute offset, length, run_length)."""
        h = self.header

        def walk(offset, length):
            for tid, off, ln, run in parse_directory(self._internal(offset, length)):
                if run == 0:                                # a leaf directory
                    yield from walk(h["leaf_offset"] + off, ln)
                else:
                    yield tid, h["data_offset"] + off, ln, run

        yield from walk(h["root_offset"], h["root_length"])

    def tile_ids(self):
        """{tile_id: (absolute offset, length)} for every addressed tile (runs expanded)."""
        out = {}
        for tid, off, ln, run in self.entries():
            for k in range(run):
                out[tid + k] = (off, ln)
        return out

    def get(self, z, x, y):
        want = zxy_to_tileid(z, x, y)
        for tid, off, ln, run in self.entries():
            if tid <= want < tid + run:
                return self._read(off, ln)
            if tid > want:
                break
        return None

    def read_at(self, offset, length):
        return self._read(offset, length)


# --- rounding steps --------------------------------------------------------------------------------

UNIT = 0.1               # Mapbox terrain-RGB: height = -10000 + value * 0.1 m
OFFSET_UNITS = 100000    # the 10,000 m offset in units; a multiple of every allowed step
# Tuned by before/after screenshots (Oct 6, docs/14 §14.10 WP17). Rounding shows as contour
# lines on flat ground once the step is large next to a pixel: MapLibre's hillshade sees a
# step of s over a pixel of p metres, and boosts slopes more the lower the zoom. These steps
# keep that about where the source's own 0.1 m steps are at z14. z14 is not rounded: every
# view from z14 in (cameras, intersections, calibrating) is drawn from it, and 0.2 m there
# drew faint contours across the flat valley floor even at the app's shading.
DEFAULT_STEPS = "-10:1,11:0.5,12:0.4,13:0.2,14-:0"


def parse_steps(text):
    """'-11:1,12-13:0.5,14-:0.2' -> [(lo, hi, units)], with each step a whole number of 0.1 m units."""
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            zooms, metres = part.split(":")
            if "-" in zooms:
                lo, hi = zooms.split("-")
                lo, hi = int(lo) if lo else 0, int(hi) if hi else 31
            else:
                lo = hi = int(zooms)
            m = float(metres)
        except ValueError:
            raise ValueError(f"bad step {part!r}: use ZOOMS:METRES, e.g. 12-13:0.5, -11:1 or 14-:0.2")
        units = round(m / UNIT)
        if m < 0 or abs(units * UNIT - m) > 1e-9 or (units and OFFSET_UNITS % units):
            raise ValueError(f"step {m} m: must be 0 or a multiple of 0.1 m that divides 10,000 m")
        if lo > hi:
            raise ValueError(f"bad zoom range {zooms!r}")
        out.append((lo, hi, units))
    for i, a in enumerate(out):
        for b in out[i + 1:]:
            if a[0] <= b[1] and b[0] <= a[1]:
                raise ValueError(f"zoom ranges overlap: {a[0]}-{a[1]} and {b[0]}-{b[1]}")
    return out


def step_units(steps, z):
    for lo, hi, units in steps:
        if lo <= z <= hi:
            return units
    raise ValueError(f"no rounding step given for z{z}")


def within_half_step(err_units, units):
    """The acceptance rule: the error is at most half the step (none at all without rounding)."""
    return err_units == 0 if units <= 1 else 2 * err_units <= units


def describe_steps(steps, minzoom, maxzoom):
    parts = []
    for lo, hi, units in sorted(steps):
        lo, hi = max(lo, minzoom), min(hi, maxzoom)
        if lo > hi:
            continue
        zooms = f"z{lo}" if lo == hi else f"z{lo}-{hi}"
        parts.append(f"{units * UNIT:g} m at {zooms}" if units > 1 else f"unrounded at {zooms}")
    return ", ".join(parts)


# --- tiles -----------------------------------------------------------------------------------------
# numpy and GDAL are imported lazily, so the PMTiles code above works without them.

_gdal = None
_np = None


def _libs():
    global _gdal, _np
    if _gdal is None:
        import numpy
        from osgeo import gdal
        gdal.UseExceptions()
        _gdal, _np = gdal, numpy
    return _gdal, _np


def decode_rgb(data):
    """PNG or WebP bytes -> (rows, cols, 3) uint8 array."""
    gdal, np = _libs()
    name = f"/vsimem/terrain_reencode_{os.getpid()}_{id(data)}"
    gdal.FileFromMemBuffer(name, bytes(data))
    try:
        ds = gdal.Open(name)
        if ds is None or ds.RasterCount < 3:
            raise ValueError("not an RGB image")
        arr = np.dstack([ds.GetRasterBand(b).ReadAsArray() for b in (1, 2, 3)]).astype(np.uint8)
        ds = None
    finally:
        gdal.Unlink(name)
    return arr


def rgb_to_units(rgb):
    np = _libs()[1]
    rgb = rgb.astype(np.uint32)
    return (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]


def units_to_rgb(v):
    np = _libs()[1]
    return np.dstack([(v >> 16) & 255, (v >> 8) & 255, v & 255]).astype(np.uint8)


def units_to_metres(v):
    return v.astype("float64") * UNIT - 10000.0


def round_units(v, units):
    """Round encoded values to a multiple of `units` (ties up), staying inside 24 bits."""
    np = _libs()[1]
    if units <= 1:
        return v.copy()
    v = v.astype(np.int64)
    out = (v + units // 2) // units * units
    top = (2 ** 24 - 1) // units * units
    return np.clip(out, 0, top).astype(np.uint32)


def encode_webp(rgb, effort=75, method=4):
    """Lossless WebP. `effort` is libwebp's quality (in lossless mode: how hard it tries), `method` 0-6."""
    gdal, np = _libs()
    rows, cols, _ = rgb.shape
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 3, gdal.GDT_Byte)
    for b in range(3):
        mem.GetRasterBand(b + 1).WriteArray(rgb[..., b])
    name = f"/vsimem/terrain_reencode_{os.getpid()}.webp"
    gdal.GetDriverByName("WEBP").CreateCopy(
        name, mem, options=["LOSSLESS=TRUE", f"QUALITY={effort}", f"METHOD={method}", "EXACT=1"])
    mem = None
    f = gdal.VSIFOpenL(name, "rb")
    try:
        gdal.VSIFSeekL(f, 0, 2)
        size = gdal.VSIFTellL(f)
        gdal.VSIFSeekL(f, 0, 0)
        data = bytes(gdal.VSIFReadL(1, size, f))
    finally:
        gdal.VSIFCloseL(f)
        gdal.Unlink(name)
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise RuntimeError("GDAL didn't write a WebP file")
    return data


def reencode_tile(data, units, effort=75, method=4):
    """One tile: (webp bytes, largest error in 0.1 m units). Raises if the WebP doesn't decode back exactly."""
    np = _libs()[1]
    rgb = decode_rgb(data)
    v = rgb_to_units(rgb)
    r = round_units(v, units)
    out = encode_webp(units_to_rgb(r), effort, method)
    back = rgb_to_units(decode_rgb(out))
    if back.shape != v.shape or not np.array_equal(back, r):
        raise RuntimeError("the WebP tile doesn't decode to the rounded values")
    err = int(np.abs(back.astype(np.int64) - v.astype(np.int64)).max())
    return out, err


# --- workers ---------------------------------------------------------------------------------------

_job_path = None
_job_opts = None


def _init(path, opts):
    global _job_path, _job_opts
    _job_path, _job_opts = path, opts
    _libs()[0].SetCacheMax(64 * 1024 * 1024)


def _work(job):
    """job: (tile_ids, z, offset, length, units). Returns (tile_ids, z, in_len, webp, err)."""
    tids, z, offset, length, units = job
    with open(_job_path, "rb") as f:
        f.seek(offset)
        data = f.read(length)
    out, err = reencode_tile(data, units, *_job_opts)
    return tids, z, length, out, err


# --- writing ---------------------------------------------------------------------------------------

def mbtiles_metadata(src):
    """The input's metadata as MBTiles rows, now `format: webp`. pmtiles convert moves `bounds`
    and `center` into the header (the input's exact values are put back afterwards)."""
    h = src.header
    meta = {}
    for k, v in src.metadata.items():
        meta[k] = v if isinstance(v, str) else json.dumps(v)
    meta["format"] = "webp"
    w, s, e, n = (c / 1e7 for c in h["bounds_e7"])
    cx, cy = (c / 1e7 for c in h["center_e7"])
    meta["bounds"] = f"{w:.7f},{s:.7f},{e:.7f},{n:.7f}"
    meta["center"] = f"{cx:.7f},{cy:.7f},{h['center_zoom']}"
    meta.setdefault("minzoom", str(h["minzoom"]))
    meta.setdefault("maxzoom", str(h["maxzoom"]))
    return meta


def restore_place(path, header_bytes):
    """Put the input's exact bounds and center (header bytes 102-126) into the output's header."""
    with open(path, "r+b") as f:
        f.seek(PLACE.start)
        f.write(header_bytes[PLACE])


def reencode(src_path, out_path, steps, work_dir, workers, effort=75, method=4, log=print):
    """Write `out_path`; returns the per-zoom statistics."""
    src = PMTiles(src_path)
    h = src.header
    if TILE_TYPES.get(h["tile_type"]) not in ("png", "webp"):
        raise SystemExit(f"{src_path}: tile type {TILE_TYPES.get(h['tile_type'])}; expected PNG terrain-RGB")
    encoding = src.metadata.get("encoding", "mapbox")
    if encoding != "mapbox":
        raise SystemExit(f"{src_path}: encoding {encoding!r}; only Mapbox terrain-RGB is supported")
    for z in range(h["minzoom"], h["maxzoom"] + 1):
        step_units(steps, z)                        # every zoom needs a step

    # One job per distinct tile content; identical tiles share a job.
    by_offset = {}
    for tid, off, ln, run in src.entries():
        z = tileid_to_zxy(tid)[0]
        key = (off, ln, z)
        by_offset.setdefault(key, []).extend(range(tid, tid + run))
    jobs = [(tids, z, off, ln, step_units(steps, z)) for (off, ln, z), tids in by_offset.items()]
    log(f"{src_path}: {h['addressed_tiles']} tiles, z{h['minzoom']}-{h['maxzoom']}, "
        f"{src.size / 1e6:.1f} MB; rounding {describe_steps(steps, h['minzoom'], h['maxzoom'])}; "
        f"{len(jobs)} encodes on {workers} workers")

    os.makedirs(work_dir, exist_ok=True)
    stem = os.path.basename(out_path)
    mbtiles = os.path.join(work_dir, stem + ".mbtiles")
    part = out_path + ".part"
    for p in (mbtiles, part):
        if os.path.exists(p):
            os.remove(p)
    stats = {}
    db = sqlite3.connect(mbtiles)
    try:
        db.executescript(
            "create table metadata (name text, value text);"
            "create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);"
            "create unique index tile_index on tiles (zoom_level, tile_column, tile_row);")
        db.executemany("insert into metadata values (?, ?)", mbtiles_metadata(src).items())
        t0 = time.time()
        done = 0
        with multiprocessing.Pool(workers, initializer=_init, initargs=(src_path, (effort, method))) as pool:
            for tids, z, in_len, out, err in pool.imap_unordered(_work, jobs, chunksize=4):
                s = stats.setdefault(z, {"tiles": 0, "in": 0, "out": 0, "max_err_units": 0,
                                         "step_units": step_units(steps, z)})
                s["tiles"] += len(tids)
                s["in"] += in_len * len(tids)
                s["out"] += len(out) * len(tids)
                s["max_err_units"] = max(s["max_err_units"], err)
                for tid in tids:
                    tz, x, y = tileid_to_zxy(tid)
                    db.execute("insert into tiles values (?, ?, ?, ?)", (tz, x, (1 << tz) - 1 - y, out))
                done += 1
                if done % 250 == 0 or done == len(jobs):
                    db.commit()
                    tin = sum(v["in"] for v in stats.values())
                    tout = sum(v["out"] for v in stats.values())
                    log(f"  {done}/{len(jobs)} tiles, {tin / 1e6:.0f} -> {tout / 1e6:.0f} MB, "
                        f"{time.time() - t0:.0f} s")
        db.commit()
    finally:
        db.close()
    subprocess.run(["pmtiles", "convert", "--quiet", f"--tmpdir={work_dir}", mbtiles, part], check=True)
    with open(src_path, "rb") as f:
        restore_place(part, f.read(HEADER_LEN))
    os.remove(mbtiles)
    os.replace(part, out_path)
    return stats


# --- checking --------------------------------------------------------------------------------------

def check(src_path, out_path, steps, sample=200, seed=1, log=print):
    """Compare an output with its input. Returns a report dict; report['ok'] says if it passed."""
    src, out = PMTiles(src_path), PMTiles(out_path)
    hs, ho = src.header, out.header
    problems = []
    ids_in, ids_out = src.tile_ids(), out.tile_ids()
    if set(ids_in) != set(ids_out):
        problems.append(f"tile IDs differ: {len(set(ids_in) - set(ids_out))} missing, "
                        f"{len(set(ids_out) - set(ids_in))} extra")
    for k in ("addressed_tiles", "minzoom", "maxzoom", "bounds_e7", "center_zoom", "center_e7"):
        if hs[k] != ho[k]:
            problems.append(f"header {k}: {hs[k]} in, {ho[k]} out")
    if TILE_TYPES.get(ho["tile_type"]) != "webp":
        problems.append(f"output tile type is {TILE_TYPES.get(ho['tile_type'])}, not webp")
    want_meta = dict(src.metadata, format="webp")
    if out.metadata != want_meta:
        diff = sorted(k for k in set(want_meta) | set(out.metadata) if want_meta.get(k) != out.metadata.get(k))
        problems.append(f"metadata differs in {diff}")

    common = sorted(set(ids_in) & set(ids_out))
    if sample and sample < len(common):
        # Every zoom gets its share, and at least a few tiles.
        rng = random.Random(seed)
        by_zoom = {}
        for tid in common:
            by_zoom.setdefault(tileid_to_zxy(tid)[0], []).append(tid)
        per = max(3, sample // max(1, len(by_zoom)))
        picked = []
        for z in sorted(by_zoom):
            pool = by_zoom[z]
            picked += pool if len(pool) <= per else rng.sample(pool, per)
    else:
        picked = common
    np = _libs()[1]
    per_zoom = {}
    for tid in picked:
        z, x, y = tileid_to_zxy(tid)
        units = step_units(steps, z)
        a = rgb_to_units(decode_rgb(src.read_at(*ids_in[tid])))
        try:
            b_rgb = decode_rgb(out.read_at(*ids_out[tid]))
        except Exception as e:   # noqa: BLE001 - any decode failure is a finding
            problems.append(f"tile {z}/{x}/{y} doesn't decode: {e}")
            continue
        b = rgb_to_units(b_rgb)
        if b.shape != a.shape:
            problems.append(f"tile {z}/{x}/{y}: {b.shape} pixels, input {a.shape}")
            continue
        err = int(np.abs(b.astype(np.int64) - a.astype(np.int64)).max())
        if units > 1 and np.any(b % units):
            problems.append(f"tile {z}/{x}/{y}: values not on the {units * UNIT:g} m grid")
        s = per_zoom.setdefault(z, {"checked": 0, "max_err_m": 0.0, "step_m": units * UNIT})
        s["checked"] += 1
        s["max_err_m"] = max(s["max_err_m"], round(err * UNIT, 3))
        if not within_half_step(err, units):
            problems.append(f"tile {z}/{x}/{y}: error {err * UNIT:.1f} m is more than half the "
                            f"{units * UNIT:g} m step")
    report = {
        "input": {"path": src_path, "bytes": src.size, "tiles": hs["addressed_tiles"],
                  "zooms": [hs["minzoom"], hs["maxzoom"]], "type": TILE_TYPES.get(hs["tile_type"])},
        "output": {"path": out_path, "bytes": out.size, "tiles": ho["addressed_tiles"],
                   "zooms": [ho["minzoom"], ho["maxzoom"]], "type": TILE_TYPES.get(ho["tile_type"])},
        "saving": round(1 - out.size / src.size, 4),
        "checked": len(picked),
        "per_zoom": {str(z): per_zoom[z] for z in sorted(per_zoom)},
        "problems": problems,
        "ok": not problems,
    }
    return report


# --- manifest --------------------------------------------------------------------------------------

def write_manifest(manifest_in, manifest_out, out_path, steps, header):
    """A copy of manifest.json whose terrain entry uses the new file. The file name is relative
    to the manifest's folder, which the app serves as /tiles/."""
    with open(manifest_in) as f:
        m = json.load(f)
    if "terrain" not in m:
        raise SystemExit(f"{manifest_in} has no terrain entry")
    rel = os.path.relpath(os.path.abspath(out_path), os.path.dirname(os.path.abspath(manifest_out)))
    if rel.startswith(".."):
        raise SystemExit(f"{out_path} isn't inside the manifest copy's folder, so /tiles/ can't serve it")
    t = dict(m["terrain"])
    t["file"] = rel.replace(os.sep, "/")
    t["format"] = "webp"
    t["reencoded"] = datetime.date.today().isoformat()
    t["rounding"] = describe_steps(steps, header["minzoom"], header["maxzoom"])
    m["terrain"] = t
    tmp = manifest_out + ".part"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=1)
    os.replace(tmp, manifest_out)


# --- main ------------------------------------------------------------------------------------------

def print_report(report, stats=None, log=print):
    i, o = report["input"], report["output"]
    log(f"input:  {i['path']}: {i['bytes'] / 1e6:.1f} MB, {i['tiles']} {i['type']} tiles, z{i['zooms'][0]}-{i['zooms'][1]}")
    log(f"output: {o['path']}: {o['bytes'] / 1e6:.1f} MB, {o['tiles']} {o['type']} tiles, z{o['zooms'][0]}-{o['zooms'][1]}")
    log(f"saving: {report['saving']:.1%} of the file")
    if stats:
        log("zoom  tiles   step   in MB  out MB  saving  max error (all tiles)")
        for z in sorted(stats):
            s = stats[z]
            log(f"z{z:<3} {s['tiles']:6d} {s['step_units'] * UNIT:5.1f} m {s['in'] / 1e6:7.1f} {s['out'] / 1e6:7.1f}"
                f"  {1 - s['out'] / s['in']:6.1%}  {s['max_err_units'] * UNIT:.1f} m")
    log(f"check: {report['checked']} tiles decoded from the new file; largest error per zoom: " +
        ", ".join(f"z{z} {v['max_err_m']:g} m (step {v['step_m']:g})" for z, v in report["per_zoom"].items()))
    for p in report["problems"]:
        log(f"PROBLEM: {p}")
    log("OK" if report["ok"] else "FAILED")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog="\n".join(__doc__.split("\n")[1:]))
    ap.add_argument("input", help="terrain-RGB PMTiles (e.g. data/tiles/terrain.pmtiles)")
    ap.add_argument("--out", help="output file (default: terrain-webp-YYYYMMDD.pmtiles next to the input)")
    ap.add_argument("--steps", default=DEFAULT_STEPS,
                    help=f"rounding per zoom range in metres, ZOOMS:METRES,... (default {DEFAULT_STEPS})")
    ap.add_argument("--manifest", help="manifest.json to copy (default: the one next to the input)")
    ap.add_argument("--manifest-out", help="write a copy of the manifest that uses the new file here")
    ap.add_argument("--work", help="folder for the temporary MBTiles (default: the output's folder)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    # libwebp's defaults. 100 and 6 are about 25 times slower for at most 1-3% smaller tiles (Oct 6).
    ap.add_argument("--effort", type=int, default=75, help="libwebp lossless effort, 0-100 (default 75)")
    ap.add_argument("--method", type=int, default=4, help="libwebp method, 0-6 (default 4)")
    ap.add_argument("--sample", type=int, default=200, help="tiles to compare afterwards (0 = every tile)")
    ap.add_argument("--check", metavar="OUTPUT", help="only compare an existing output with the input")
    ap.add_argument("--report", help="also write the report as JSON here")
    args = ap.parse_args(argv)

    try:
        steps = parse_steps(args.steps)
    except ValueError as e:
        ap.error(str(e))
    if args.check:
        report = check(args.input, args.check, steps, args.sample)
        print_report(report)
        if args.report:
            with open(args.report, "w") as f:
                json.dump(report, f, indent=1)
        return 0 if report["ok"] else 1

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.input)),
                                   f"terrain-webp-{datetime.date.today():%Y%m%d}.pmtiles")
    if os.path.abspath(out) == os.path.abspath(args.input):
        ap.error("the output must be a new file")
    if os.path.exists(out):
        ap.error(f"{out} exists; the output is versioned and never overwritten (pick another --out)")
    manifest_in = args.manifest or os.path.join(os.path.dirname(os.path.abspath(args.input)), "manifest.json")
    if args.manifest_out:
        if not os.path.exists(manifest_in):
            ap.error(f"no manifest to copy at {manifest_in} (use --manifest)")
        if os.path.abspath(args.manifest_out) == os.path.abspath(manifest_in):
            ap.error("--manifest-out must be a copy, not the manifest the app reads now")
        rel = os.path.relpath(os.path.abspath(out), os.path.dirname(os.path.abspath(args.manifest_out)))
        if rel.startswith(".."):
            ap.error("the output must be inside the manifest copy's folder")
    t0 = time.time()
    stats = reencode(args.input, out, steps, args.work or os.path.dirname(os.path.abspath(out)),
                     args.workers, args.effort, args.method)
    report = check(args.input, out, steps, args.sample)
    report["seconds"] = round(time.time() - t0)
    report["steps"] = describe_steps(steps, report["input"]["zooms"][0], report["input"]["zooms"][1])
    report["per_zoom_all"] = {str(z): {"tiles": s["tiles"], "in_bytes": s["in"], "out_bytes": s["out"],
                                       "step_m": s["step_units"] * UNIT,
                                       "max_err_m": round(s["max_err_units"] * UNIT, 3)}
                              for z, s in sorted(stats.items())}
    for z, s in stats.items():
        if not within_half_step(s["max_err_units"], s["step_units"]):
            report["problems"].append(f"z{z}: error {s['max_err_units'] * UNIT:.1f} m over half the step")
            report["ok"] = False
    print_report(report, stats)
    print(f"{report['seconds']} s")
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=1)
    if not report["ok"]:
        return 1
    if args.manifest_out:
        write_manifest(manifest_in, args.manifest_out, out, steps, PMTiles(out).header)
        print(f"wrote {args.manifest_out}: terrain.file = {os.path.basename(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
