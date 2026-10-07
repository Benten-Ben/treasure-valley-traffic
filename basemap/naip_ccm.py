#!/usr/bin/env python3
"""Turn USDA's NAIP county mosaics (MrSID) into local JPEG GeoTIFF windows for imagery_county.py.

USDA NRCS publishes each county's NAIP as one compressed county mosaic: a
MrSID MG4 file (public-domain imagery). Ada's 2025 mosaic is 171,190 x
278,030 pixels at 0.3 m, about 200 GB uncompressed, in 4.8 GB. Our GDAL
can't read MrSID. LizardTech's MrSID Decode SDK can: free, closed source,
licensed for internal use only, so it is never included or committed
(basemap/README.md says how it was used). Its `mrsiddecode` cuts windows out
of the mosaic. This script plans those windows and converts each one, so a
whole county is never decoded at once.

Bands in USDA's 2025 Idaho mosaics: 1-3 red, green and blue; 4 near-infrared;
5 the county mask (255 inside the county, 0 outside). The TIFF header the
decoder writes calls band 4 "alpha"; it isn't.

  plan     reads the county decoded at 1/32 (`mrsiddecode -s 5`) and writes
           one line per window that holds county pixels:
           `name ulx uly width height` (full-resolution pixels)
  convert  turns each decoded window in RAW (from naip_ccm_decode.sh) into
           TIFS/<name>.tif: RGB as JPEG (quality 90, YCbCr) with the county
           mask as its internal mask, then deletes the decoded window. It
           keeps going until RAW/DONE exists and RAW is empty, so it runs
           alongside the decoder.

Usage (inside a GDAL container; basemap/README.md has the docker commands):
  python3 basemap/naip_ccm.py plan overview.tif --size 171190 278030 --prefix ada > windows.txt
  python3 basemap/naip_ccm.py convert raw/ tifs/ --workers 2
"""

import argparse
import multiprocessing
import os
import sys
import time

from osgeo import gdal

gdal.UseExceptions()

WINDOW = 8192          # full-resolution pixels per window side (2.46 km at 0.3 m)
OVERVIEW = 32          # the plan's overview is decoded at 1/32 (mrsiddecode -s 5)
MASK_BAND = 5
JPEG_CO = ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=JPEG",
           "PHOTOMETRIC=YCBCR", "JPEG_QUALITY=90"]


def plan(args):
    ds = gdal.Open(args.overview)
    if ds.RasterCount < MASK_BAND:
        sys.exit(f"{args.overview}: {ds.RasterCount} bands; expected the county mask in band {MASK_BAND}")
    mask = ds.GetRasterBand(MASK_BAND).ReadAsArray()
    width, height = args.size
    kept = skipped = 0
    for j in range(0, (height + WINDOW - 1) // WINDOW):
        for i in range(0, (width + WINDOW - 1) // WINDOW):
            x0, y0 = i * WINDOW, j * WINDOW
            w, h = min(WINDOW, width - x0), min(WINDOW, height - y0)
            # The window in overview pixels, one pixel wider on every side so slivers aren't missed.
            ox0, oy0 = max(0, x0 // OVERVIEW - 1), max(0, y0 // OVERVIEW - 1)
            ox1, oy1 = (x0 + w) // OVERVIEW + 2, (y0 + h) // OVERVIEW + 2
            if mask[oy0:oy1, ox0:ox1].any():
                print(f"{args.prefix}_{j:03d}_{i:03d} {x0} {y0} {w} {h}")
                kept += 1
            else:
                skipped += 1
    print(f"plan: {kept} windows with county pixels, {skipped} empty", file=sys.stderr)


def convert_one(job):
    raw, out = job
    t0 = time.time()
    try:
        src = gdal.Open(raw)
        m = src.GetRasterBand(MASK_BAND).ComputeRasterMinMax(False)
        if m[1] == 0:                                    # no county pixels after all
            src = None
            os.remove(raw)
            return out, "empty", time.time() - t0
        gdal.Translate(out + ".part", src, format="GTiff", bandList=[1, 2, 3], maskBand=MASK_BAND,
                       creationOptions=JPEG_CO)
        src = None
        os.replace(out + ".part", out)
        os.remove(raw)
        return out, "ok", time.time() - t0
    except RuntimeError as e:
        return out, f"error: {e}", time.time() - t0


def convert(args):
    gdal.SetConfigOption("GDAL_TIFF_INTERNAL_MASK", "YES")
    os.makedirs(args.tifs, exist_ok=True)
    done = set()
    t0, n_ok, n_empty, n_err = time.time(), 0, 0, 0
    with multiprocessing.Pool(args.workers) as pool:
        while True:
            ready = sorted(f for f in os.listdir(args.raw)
                           if f.endswith(".tif") and not f.endswith(".part.tif") and f not in done)
            if not ready:
                if os.path.exists(os.path.join(args.raw, "DONE")):
                    break
                time.sleep(2)
                continue
            jobs = [(os.path.join(args.raw, f), os.path.join(args.tifs, f)) for f in ready]
            done.update(ready)
            for out, status, secs in pool.imap_unordered(convert_one, jobs):
                if status == "ok":
                    n_ok += 1
                elif status == "empty":
                    n_empty += 1
                else:
                    n_err += 1
                    print(f"  {os.path.basename(out)}: {status}", flush=True)
                if (n_ok + n_empty) % 25 == 0:
                    print(f"  {n_ok} converted, {n_empty} empty, {n_err} failed, "
                          f"{time.time() - t0:.0f} s (last {secs:.1f} s)", flush=True)
    print(f"convert: {n_ok} converted, {n_empty} empty, {n_err} failed in {time.time() - t0:.0f} s", flush=True)
    if n_err:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="list the windows that hold county pixels")
    p.add_argument("overview", help="the mosaic decoded at 1/32, all 5 bands")
    p.add_argument("--size", type=int, nargs=2, required=True, metavar=("WIDTH", "HEIGHT"),
                   help="the mosaic's full size in pixels (mrsidinfo)")
    p.add_argument("--prefix", required=True, help="window name prefix, e.g. the county")
    c = sub.add_parser("convert", help="convert decoded windows as they arrive")
    c.add_argument("raw")
    c.add_argument("tifs")
    c.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    plan(args) if args.cmd == "plan" else convert(args)


if __name__ == "__main__":
    main()
