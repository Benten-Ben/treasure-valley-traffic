"""Developed land from USDA NASS's Cropland Data Layer, as polygons for the paving's materials (plan C11). Runs in
the worker image (GDAL, NumPy), from the repository's root, files in and files out:

    python -m plugins.roads.build.developed --cdl $TVT_ARCHIVE/farm/cdl --out $TVT_ARCHIVE/roads/developed/<id>

Then `python3 -m ingest roads-developed-load --build <dir>` loads the polygons into roads.developed_land, where the
osm_paving consumer measures each service way's and lot's share of developed land in PostGIS. The raster is decoded
here, in the worker, and never in the ingest image (docs/17 §17.8 Q9): the ingest side reads only these polygons.
About 0.15 GB of memory and half a minute for the box (a light job at --memory 1g).

--cdl is farm's archived copy of NASS's clips (farm-cdl-load copies them to $TVT_ARCHIVE/farm/cdl/ and indexes each
with its sha256 in farm.cdl_year), so the paving and the crop fields read the same file: a folder, whose newest
cdl_<year>_<res>m.tif is used, or one such file. The raster must be one band on NASS's own grid (EPSG:5070, north
up).

Developed land is the classes 122-124 (developed, low, medium and high intensity; CLASSES in
plugins/roads/ingest/developed.py). Class 121, developed open space, is left out: it's parks, lawns and verges, and
NLCD (where the CDL takes its developed classes from) paints rural roads into it.

The raster is read in windows of 512 x 512 cells, and each window's developed cells are traced into polygons on the
CDL's own grid (gdal.Polygonize, 4-connected): exact cell edges, with a vertex only where an edge turns. A polygon
that crosses a window's edge is cut there. The pieces don't overlap, so shares add up across them, and none is larger
than a window (5.12 km at 10 m), which keeps the loader's subdivision and PostGIS's intersections quick.

Writes, in --out: developed.jsonl.gz (one piece per line: {"n": 1, "geom": a GeoJSON Polygon in EPSG:5070}) and
build.json last (a folder without it is unfinished). An existing finished folder is refused. For the 2025 CDL (10 m):
about 191,000 pieces, 3.1 million vertices and 861 km2 of developed land, in about 25 s at 0.14 GB (Oct 11, 2026).
"""

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sys

import numpy as np
from osgeo import gdal, ogr, osr

from plugins.roads.ingest import developed as D

RASTER = re.compile(r"^cdl_([0-9]{4})_([0-9]+)m\.tif$")
WINDOW_CELLS = 512

gdal.UseExceptions()
ogr.UseExceptions()


class BuildError(ValueError):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick(cdl):
    """(year, res_m, path) of the raster to read: cdl itself, or the newest year's in a folder."""
    if os.path.isdir(cdl):
        found = sorted((int(m.group(1)), float(m.group(2)), os.path.join(cdl, name))
                       for name in os.listdir(cdl) if (m := RASTER.match(name)))
        if not found:
            raise BuildError(f"{cdl}: no cdl_<year>_<res>m.tif")
        if len({y for y, _, _ in found}) != len(found):
            raise BuildError(f"{cdl}: a year has more than one raster")
        return found[-1]
    m = RASTER.match(os.path.basename(cdl))
    if not m or not os.path.isfile(cdl):
        raise BuildError(f"{cdl}: not a cdl_<year>_<res>m.tif file or a folder of them")
    return int(m.group(1)), float(m.group(2)), cdl


def open_raster(path):
    """(dataset, geotransform) for a one-band raster on EPSG:5070, north up."""
    ds = gdal.Open(path)
    if ds.RasterCount != 1:
        raise BuildError(f"{path}: {ds.RasterCount} bands, not one")
    gt = ds.GetGeoTransform()
    if gt[2] or gt[4] or gt[1] <= 0 or gt[5] >= 0:
        raise BuildError(f"{path}: not north up")
    albers = osr.SpatialReference()
    albers.ImportFromEPSG(D.SRID)
    srs = ds.GetSpatialRef()
    if srs is None or not srs.IsSame(albers):
        raise BuildError(f"{path}: not on EPSG:{D.SRID} (NAD83 / Conus Albers), NASS's own grid")
    return ds, gt


def _num(v):
    return int(v) if float(v).is_integer() else v


def polygon(g):
    """An OGR polygon as a GeoJSON dict, whole-metre coordinates as integers."""
    rings = []
    for i in range(g.GetGeometryCount()):
        rings.append([[_num(x), _num(y)] for x, y, *_ in g.GetGeometryRef(i).GetPoints()])
    return {"type": "Polygon", "coordinates": rings}


def pieces(ds, gt, classes=D.CLASSES, window=WINDOW_CELLS, counts=None):
    """GeoJSON polygons of the cells whose code is in classes, window by window (see the module's docstring).
    counts, if given, gets 'cells' and 'windows' (windows with any)."""
    band = ds.GetRasterBand(1)
    lut = np.zeros(256, np.uint8)
    lut[list(classes)] = 1
    mem = gdal.GetDriverByName("MEM")
    width, height = ds.RasterXSize, ds.RasterYSize
    for r0 in range(0, height, window):
        for c0 in range(0, width, window):
            w, h = min(window, width - c0), min(window, height - r0)
            mask = lut[band.ReadAsArray(c0, r0, w, h)]
            n = int(mask.sum())
            if not n:
                continue
            if counts is not None:
                counts["cells"] = counts.get("cells", 0) + n
                counts["windows"] = counts.get("windows", 0) + 1
            src = mem.Create("", w, h, 1, gdal.GDT_Byte)
            src.SetGeoTransform((gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r0 * gt[5], 0.0, gt[5]))
            b = src.GetRasterBand(1)
            b.WriteArray(mask)
            vec = mem.Create("", 0, 0, 0, gdal.GDT_Unknown)
            layer = vec.CreateLayer("developed", None, ogr.wkbPolygon)
            layer.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
            gdal.Polygonize(b, b, layer, 0)                 # the mask band masks itself: developed cells only
            for f in layer:
                yield polygon(f.GetGeometryRef())
            layer = vec = b = src = None


def build(cdl, out, window=WINDOW_CELLS, log=print):
    """Write developed.jsonl.gz and build.json in out (see the module's docstring). Returns build.json's content."""
    started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if os.path.exists(os.path.join(out, D.BUILD_FILE)):
        raise BuildError(f"{out}: already a finished build")
    year, res, path = pick(cdl)
    ds, gt = open_raster(path)
    if abs(gt[1] - res) > 1e-6 or abs(-gt[5] - res) > 1e-6:
        raise BuildError(f"{path}: its cells are {gt[1]:g} x {-gt[5]:g} m, not the {res:g} m its name says")
    os.makedirs(out, exist_ok=True)
    log(f"{os.path.basename(path)}: {ds.RasterXSize} x {ds.RasterYSize} cells, classes {list(D.CLASSES)}")
    counts = {}
    n = vertices = 0
    tmp = os.path.join(out, "." + D.LAND_FILE + ".tmp")
    with open(tmp, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        for geom in pieces(ds, gt, D.CLASSES, window, counts):
            n += 1
            vertices += sum(len(r) for r in geom["coordinates"])
            gz.write((json.dumps({"n": n, "geom": geom}, separators=(",", ":")) + "\n").encode())
    os.replace(tmp, os.path.join(out, D.LAND_FILE))
    extent = [gt[0], gt[3] + ds.RasterYSize * gt[5], gt[0] + ds.RasterXSize * gt[1], gt[3]]   # west, south, east, north
    ds = None
    if not n:
        raise BuildError(f"{path}: no developed cells (classes {list(D.CLASSES)})")
    finished = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    land = os.path.join(out, D.LAND_FILE)
    doc = {
        "format": D.FORMAT,
        "build_id": os.path.basename(os.path.normpath(out)),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "classes": list(D.CLASSES),
        "srid": D.SRID,
        "cdl": {"file": os.path.basename(path), "path": os.path.abspath(path), "year": year, "res_m": res,
                "sha256": sha256_of(path), "bytes": os.path.getsize(path), "license": D.LICENSE,
                "credit": D.credit(year)},
        "extent": extent,
        "params": {"window_cells": window, "connectivity": 4},
        "counts": {"pieces": n, "vertices": vertices, "cells": counts.get("cells", 0),
                   "area_km2": round(counts.get("cells", 0) * gt[1] * -gt[5] / 1e6, 6)},
        "files": {D.LAND_FILE: {"sha256": sha256_of(land), "bytes": os.path.getsize(land)}},
    }
    tmp = os.path.join(out, "." + D.BUILD_FILE + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, os.path.join(out, D.BUILD_FILE))
    log(f"done: {out}: {n} pieces, {doc['counts']['area_km2']} km2 ({(finished - started).total_seconds():.0f} s)")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cdl", required=True, help="farm's copy: a folder of cdl_<year>_<res>m.tif ($TVT_ARCHIVE/farm/cdl; "
                                                 "the newest year is read), or one of them")
    ap.add_argument("--out", required=True, help="the build folder ($TVT_ARCHIVE/roads/developed/<id>), new or unfinished")
    ap.add_argument("--window", type=int, default=WINDOW_CELLS, help="window size in cells")
    args = ap.parse_args(argv)
    try:
        build(args.cdl, args.out, args.window, log=lambda m: print(f"roads developed: {m}", flush=True))
    except BuildError as err:
        print(f"roads developed: {err}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
