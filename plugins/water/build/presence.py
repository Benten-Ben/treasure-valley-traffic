"""The presence check's worker step (issue #309): measures five shares of every old-mapped NWI wetland against today's
land and writes the JSON file `python3 -m ingest nwi-presence --from` loads. Worker image (GDAL, NumPy, SciPy), no
network, no database:

    python plugins/water/build/presence.py --nwi $TVT_SOURCES/nwi/nwi_mapbox.gpkg --csb $TVT_SOURCES/csb/csb_mapbox.gpkg \
        --cdl-dir $TVT_SOURCES/cdl/out --archive $TVT_ARCHIVE --keys keys.txt [--out shares.json] [--limit N]

--keys is a text file of the NWI polygon keys to measure, one per line: the old and interim ones (the worker has no
database, so `select key from water.nwi_wetland where era in ('old', 'interim')` makes it); without it every
vegetated palustrine polygon is measured. The keys are the loader's (wetlands.read, so the same numbering of a shared
NWI_ID's parts), and nwi-presence refuses a key it doesn't hold.

Every share is a share of the polygon's area, counted on the ground's grid (basemap/ground/grid.py): the polygon is
burned into a window of the grid around it, at the finest level that keeps the window under 3,000 cells a side (0.5 m,
else 2 m, else 10 m), a cell counting when its centre is inside. The inputs are read with the grid's datum policy
(NAD83 taken as WGS 84, rasterize.srs_of). A polygon is never clipped by the map box: its window may reach past the
grid's extent, where the inputs hold nothing.

    built        mask v0's exact roofs, roads and paving (mask.exact; the newest whole export in --archive)
    developed    CDL 2024 and 2025 (10 m) both in classes 122, 123 or 124. Class 121 (open space) counts for nothing
    cdl_wetland  CDL 2024 or 2025 in 190 or 195 (woody and herbaceous wetlands)
    cultivated   inside a CSB 2018-2025 field coded as a crop, alfalfa or fallow in at least 6 of the 8 years
    hay_pasture  inside a CSB field coded 37 (other hay) or 176 (grassland and pasture) in at least 4 of the 8 years
    hydric       not measured here: SSURGO's hydric share stays a row on the soils card and decides nothing

Standard CSB is a field outline generalised from 30 m pixels (its edges sit 5 to 15 m off the visible field edge), so a
wetland along a field edge picks up a small `cultivated` share that is the outline's, not a crop's. The thresholds that
turn the shares into kept, flagged and retired are wetlands.py's; this file only measures.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

CSB_YEARS = tuple(range(2018, 2026))
CULTIVATED_YEARS = 6                 # a CSB field cropped (crop, alfalfa or fallow) in this many of the 8 years
HAY_YEARS = 4                        # ... or in hay or pasture in this many
DEVELOPED = (122, 123, 124)          # CDL developed classes read (121, open space, counts for nothing)
CDL_WETLAND = (190, 195)             # CDL woody and herbaceous wetlands
HAY_PASTURE = (37, 176)              # CDL other hay and grassland/pasture
# CDL classes that are a crop for `cultivated`: the legend's cropland (1-6, 10-14, 21-35, 38-39, 41-60, 66-72, 74-77,
# 204-250, 254), alfalfa (36) and fallow or idle cropland (61); not other hay (37) or pasture (176).
CROPS = frozenset(set(range(1, 7)) | set(range(10, 15)) | set(range(21, 36)) | {36, 38, 39} | set(range(41, 62))
                  | set(range(66, 73)) | set(range(74, 78)) | set(range(204, 251)) | {254})
LEVELS = (0.5, 2.0, 10.0)            # the grid's levels, finest first
MAX_CELLS = 3000                     # a window is at most this many cells a side, at the finest level that allows it
FIELD_NONE, FIELD_CULTIVATED, FIELD_HAY = 0, 1, 2
CSB_LAYER = "csb_mapbox"


def field_kind(codes):
    """FIELD_CULTIVATED, FIELD_HAY or FIELD_NONE for a CSB field from its eight yearly CDL codes (None or 0 for a
    missing year, which counts for nothing)."""
    cult = sum(1 for c in codes if c in CROPS)
    hay = sum(1 for c in codes if c in HAY_PASTURE)
    if cult >= CULTIVATED_YEARS:
        return FIELD_CULTIVATED
    if hay >= HAY_YEARS:
        return FIELD_HAY
    return FIELD_NONE


def pick_level(width_m, height_m):
    """The finest level (0.5, 2 or 10 m) at which a polygon's bounding box is at most MAX_CELLS cells a side."""
    big = max(width_m, height_m)
    for res in LEVELS:
        if big / res <= MAX_CELLS:
            return res
    return LEVELS[-1]


def read_keys(path):
    """The keys in a text file, one per line (blank lines and #comments skipped), in file order, no repeats."""
    seen, out = set(), []
    with open(path, encoding="utf-8") as f:
        for line in f:
            k = line.strip()
            if k and not k.startswith("#") and k not in seen:
                seen.add(k)
                out.append(k)
    return out


def share(count, total):
    """count / total as a float rounded to 4 places and held to 0..1 (0 for an empty polygon)."""
    if total <= 0:
        return 0.0
    return round(min(1.0, max(0.0, count / total)), 4)


def shares_of(poly, built, dev24, dev25, wet24, wet25, kind):
    """The five shares of one polygon from boolean arrays on its window (poly the polygon's cells, built the mask's
    roofs, roads or paving, dev24 and dev25 CDL developed in each year, wet24 and wet25 CDL wetland classes) and
    kind (the CSB field kind in each cell, FIELD_*). Returns the dict nwi-presence's file holds, without the key."""
    n = int(poly.sum())
    return {"built": share(int((poly & built).sum()), n),
            "developed": share(int((poly & dev24 & dev25).sum()), n),
            "cultivated": share(int((poly & (kind == FIELD_CULTIVATED)).sum()), n),
            "hay_pasture": share(int((poly & (kind == FIELD_HAY)).sum()), n),
            "cdl_wetland": share(int((poly & (wet24 | wet25)).sum()), n)}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# ---- the raster side (worker image) -----------------------------------------------------------------------------

class Inputs:
    """What the shares are measured against. built(target) is a callable returning the mask's covered cells as a bool
    array on a Target (the real one reads mask v0; a test passes its own); the CDL years are rasters, the CSB fields a
    layer in memory."""

    def __init__(self, built, cdl24, cdl25, fields):
        self.built, self.cdl24, self.cdl25, self.fields = built, cdl24, cdl25, fields


def _gdal():
    from osgeo import gdal, ogr, osr
    from basemap.ground import grid, rasterize as R
    return gdal, ogr, osr, grid, R


def open_mask(archive):
    """(built callable, the mask's manifest) for the newest whole mask v0 in the archive."""
    from basemap.ground import mask
    m = mask.latest(archive)
    if m is None:
        raise SystemExit(f"presence: no whole mask v0 in {archive}/ground_mask/export")

    def built(target):
        out = None
        for layer in ("roofs", "roads", "paving"):
            a = mask.exact(target, m, layer)
            out = a if out is None else (out | a)
        return out
    return built, m


def csb_fields(path):
    """A layer in memory (EPSG:32611, field `v` = FIELD_*) of the CSB fields that are cultivated or hay and pasture,
    from the eight CDL20xx columns. Returns (data source, layer, counts)."""
    gdal, ogr, osr, grid, R = _gdal()
    ds = ogr.Open(path)
    lyr = ds.GetLayerByName(CSB_LAYER) or ds.GetLayer(0)
    src = R.srs_of(lyr.GetSpatialRef())
    dst = R.srs_of(grid.CRS)
    ct = osr.CoordinateTransformation(src, dst)
    defn = lyr.GetLayerDefn()
    cols = [defn.GetFieldIndex(f"CDL{y}") for y in CSB_YEARS]
    if min(cols) < 0:
        raise SystemExit(f"presence: {path} has no CDL{CSB_YEARS[0]}..CDL{CSB_YEARS[-1]} columns: is it the CSB cut?")
    mem = R._mem_vector()
    out = mem.CreateLayer("fields", dst, ogr.wkbUnknown)
    out.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    counts = {"fields": 0, "cultivated": 0, "hay_pasture": 0}
    for f in lyr:
        counts["fields"] += 1
        codes = [None if f.IsFieldNull(i) else f.GetFieldAsInteger(i) for i in cols]
        kind = field_kind(codes)
        if kind == FIELD_NONE:
            continue
        g = f.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        g = g.Clone()
        g.Transform(ct)
        o = ogr.Feature(out.GetLayerDefn())
        o.SetGeometry(g)
        o.SetField("v", kind)
        out.CreateFeature(o)
        counts["cultivated" if kind == FIELD_CULTIVATED else "hay_pasture"] += 1
    return mem, out, counts


class Cdl:
    """A CDL raster warped, nearest neighbour, onto any window of the grid."""

    def __init__(self, path):
        gdal, ogr, osr, grid, R = _gdal()
        self.ds = gdal.Open(path)
        self.src_wkt = R.warp_srs(self.ds.GetProjection())
        self.dst_wkt = R.srs_of(grid.CRS).ExportToWkt()
        self.gdal = gdal

    def read(self, target):
        w, s, e, n = target.bounds
        out = self.gdal.Warp("", self.ds, format="MEM", outputBounds=(w, s, e, n), width=target.width,
                             height=target.height, srcSRS=self.src_wkt, dstSRS=self.dst_wkt, resampleAlg="near")
        return out.GetRasterBand(1).ReadAsArray()


def burn_polygon(wkb, target, ct):
    """The polygon (WKB in the source CRS, ct taking it to the grid's) as a bool array on the target."""
    gdal, ogr, osr, grid, R = _gdal()
    g = ogr.CreateGeometryFromWkb(bytes(wkb))
    g.Transform(ct)
    if not g.IsValid():
        g = g.MakeValid()
    mem = R._mem_vector()
    lyr = mem.CreateLayer("p", R.srs_of(grid.CRS), ogr.wkbUnknown)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(g)
    lyr.CreateFeature(feat)
    ras = gdal.GetDriverByName("MEM").Create("", target.width, target.height, 1, gdal.GDT_Byte)
    ras.SetGeoTransform(target.transform)
    gdal.RasterizeLayer(ras, [1], lyr, burn_values=[1])
    a = ras.GetRasterBand(1).ReadAsArray().astype(bool)
    if not a.any():                       # a sliver with no cell centre inside: count the cells it touches
        gdal.RasterizeLayer(ras, [1], lyr, burn_values=[1], options=["ALL_TOUCHED=TRUE"])
        a = ras.GetRasterBand(1).ReadAsArray().astype(bool)
    return a, g.GetEnvelope()


def window_for(wkb, ct):
    """The Target on the grid for a polygon (a cell of margin all round) at the finest allowed level."""
    gdal, ogr, osr, grid, R = _gdal()
    g = ogr.CreateGeometryFromWkb(bytes(wkb))
    g.Transform(ct)
    x0, x1, y0, y1 = g.GetEnvelope()
    res = pick_level(x1 - x0, y1 - y0)
    win = grid.window((x0 - res, y0 - res, x1 + res, y1 + res), res, snap="out")
    return R.Target(win.transform, win.width, win.height, grid.CRS)


def measure(wkb, inputs, ct):
    """The five shares of one polygon, and the level it was measured at."""
    gdal, ogr, osr, grid, R = _gdal()
    target = window_for(wkb, ct)
    poly, _ = burn_polygon(wkb, target, ct)
    w, s, e, n = target.bounds
    inputs.fields.SetSpatialFilterRect(w, s, e, n)
    kras = gdal.GetDriverByName("MEM").Create("", target.width, target.height, 1, gdal.GDT_Byte)
    kras.SetGeoTransform(target.transform)
    gdal.RasterizeLayer(kras, [1], inputs.fields, options=["ATTRIBUTE=v"])
    kind = kras.GetRasterBand(1).ReadAsArray()
    inputs.fields.SetSpatialFilter(None)
    c24, c25 = inputs.cdl24.read(target), inputs.cdl25.read(target)
    dev = lambda a: (a >= DEVELOPED[0]) & (a <= DEVELOPED[-1])      # noqa: E731 (122 to 124)
    wet = lambda a: (a == CDL_WETLAND[0]) | (a == CDL_WETLAND[1])   # noqa: E731
    out = shares_of(poly, inputs.built(target), dev(c24), dev(c25), wet(c24), wet(c25), kind)
    return out, target.res


def run(args, log=print, mask_opener=None):
    gdal, ogr, osr, grid, R = _gdal()
    from plugins.water.ingest import wetlands
    wets, _projects, skipped = wetlands.read(args.nwi)
    keys = read_keys(args.keys) if args.keys else [w[0] for w in wets]
    held = {w[0]: w for w in wets}
    missing = [k for k in keys if k not in held]
    if missing:
        raise SystemExit(f"presence: {len(missing)} keys aren't vegetated palustrine polygons of {args.nwi}: "
                         f"{missing[:5]}")
    if args.limit:
        keys = keys[:args.limit]
    built, m = (mask_opener or open_mask)(args.archive)
    log(f"presence: mask v0 build {m.build}")
    fields_ds, fields, csb_counts = csb_fields(args.csb)
    log(f"presence: CSB {csb_counts}")
    cdl24 = Cdl(os.path.join(args.cdl_dir, "cdl_2024_10m.tif"))
    cdl25 = Cdl(os.path.join(args.cdl_dir, "cdl_2025_10m.tif"))
    inputs = Inputs(built, cdl24, cdl25, fields)
    src = R.srs_of("EPSG:5070")
    ct = osr.CoordinateTransformation(src, R.srs_of(grid.CRS))
    polys, by_level = [], {}
    for i, k in enumerate(keys, 1):
        sh, res = measure(held[k][6], inputs, ct)
        polys.append({"key": k, **sh})
        by_level[f"{res:g} m"] = by_level.get(f"{res:g} m", 0) + 1
        if i % 200 == 0 or i == len(keys):
            log(f"presence: {i} of {len(keys)} polygons")
    doc = {"computed_on": date.today().isoformat(),
           "inputs": {"mask": {"build": m.build, "layers": {n: m.layer(n)["sha256"] for n in ("roofs", "roads", "paving")}},
                      "cdl": {"files": ["cdl_2024_10m.tif", "cdl_2025_10m.tif"],
                              "sha256": {n: sha256(os.path.join(args.cdl_dir, n))
                                         for n in ("cdl_2024_10m.tif", "cdl_2025_10m.tif")}},
                      "csb": {"file": os.path.basename(args.csb), "sha256": sha256(args.csb), **csb_counts,
                              "years": f"{CSB_YEARS[0]}-{CSB_YEARS[-1]}", "cultivated_years": CULTIVATED_YEARS,
                              "hay_pasture_years": HAY_YEARS},
                      "nwi": {"file": os.path.basename(args.nwi), "sha256": wetlands.sha256(args.nwi),
                              "polygons": len(wets), "measured": len(polys)},
                      "levels": by_level, "max_cells": MAX_CELLS},
           "polygons": polys}
    out = args.out or os.path.join(args.archive, "water", "nwi-presence", f"shares-{doc['computed_on']}.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    os.replace(tmp, out)
    wetlands.read_shares(out)                 # the loader's own check of what was written
    log(f"presence: {len(polys)} polygons written to {out}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nwi", required=True, help="nwi_mapbox.gpkg, the NWI cut kept on the server")
    ap.add_argument("--csb", required=True, help="csb_mapbox.gpkg, the CSB 2018-2025 cut")
    ap.add_argument("--cdl-dir", required=True, help="the CDL folder holding cdl_2024_10m.tif and cdl_2025_10m.tif")
    ap.add_argument("--archive", default=os.environ.get("TVT_ARCHIVE"), help="the archive holding ground_mask/export")
    ap.add_argument("--keys", help="a text file of the NWI keys to measure, one per line (default: all)")
    ap.add_argument("--out", help="the shares JSON (default: <archive>/water/nwi-presence/shares-<date>.json)")
    ap.add_argument("--limit", type=int, help="measure only the first N keys (a quick look)")
    args = ap.parse_args(argv)
    if not args.archive:
        ap.error("--archive (or TVT_ARCHIVE) is required")
    run(args)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    sys.exit(main())
