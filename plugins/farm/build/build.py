"""Build the crop fields' stats and crop_cover.tif (the farm design; plan C7). Runs in the worker image (GDAL, NumPy,
SciPy), from the repository's root, files in and files out:

    python -m plugins.farm.build.build --csb $TVT_SOURCES/csb/csb_mapbox.gpkg --cdl $TVT_ARCHIVE/farm/cdl \\
        --ndvi $TVT_SOURCES/sentinel2/july2025/ndvi_median.tif --out $TVT_ARCHIVE/farm/build/<build-id>

Then `python3 -m ingest farm-fields-load --build <dir>` loads the stats, and `farm-export` hands crop_cover.tif and
the fields to the ground. About 0.6 GB of memory and a few minutes for the box (a light job at --memory 1g).

1. **Agreement.** Each CDL raster in --cdl (cdl_<year>_<res>m.tif, on NASS's own grid) is compared with the fields of
   the same year, on that grid, in row strips: the share of each field's pixels (centres inside) whose code is the
   field's CSB code that year. CSB's code is a smoothed majority (97% of fields' majority pixel matches it), so this
   says how mixed a field is, which the card shows as "USDA's map agrees on 82% of this field".
2. **July state.** On the ground's 10 m grid (the July Sentinel-2 NDVI median's own grid), each field's median NDVI
   over the cells whose centres are inside it: green from 0.6, growing from 0.3, bare or harvested below. The state's
   year is the NDVI's own, read from the raster's tags (ACQUISITIONS, the dates of the views it's the median of, as
   the Sentinel-2 composite writes them; else its CREDIT's year), never the crop year: a 2026 crop year built on the
   July 2025 median says July 2025, and credits Sentinel data 2025. --july-year must agree with the tags, and is
   needed only for a raster without them; views outside July, or from two years, are refused.
3. **crop_cover.tif**, on the same grid, three bands (uint8), window by window with a 500 m halo:
   - group: 0 none, 1 corn, 2 hay, 3 grain, 4 roots, 5 specialty, 6 fallow (classes.COVER_CODES). Pasture isn't crop
     (the scheme paints it as grass), and built-over fields aren't either (their newest code is developed);
   - state: per cell, from the NDVI median smoothed over 3 x 3 cells (the mean of the valid ones): 1 green, 2 growing,
     3 bare or harvested, 0 none or no reading;
   - confidence: 1 field interior (the cell and its eight neighbours inside one field); 2 the 10 m edge band (cells a
     field touches that aren't interior), only where the CDL pixel (nearest, on the grid) is the field's group;
     3 CDL crop pixels outside every field, in 8-connected clusters of at least 0.5 ha (50 cells). The 500 m halo
     makes the cluster size exact for every cluster that reaches the window's core.
   The painter (G1a) decides how far to trust each: CSB edges are 5-15 m off, and the edge band absorbs that where the
   CDL agrees.
Growth isn't here: it needs COMPASS's permits, which are in the database, so farm-fields-load works it out.

Datum policy (basemap/ground/grid.py): NAD83 inputs (CSB, CDL) are taken as WGS 84 (the null shift), as the ground
does. Writes, in --out: fields.jsonl (one line per field), crop_cover.tif, and build.json last (a folder without it is
unfinished). An existing finished folder is refused.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

import numpy as np
from osgeo import gdal, ogr, osr
from scipy import ndimage

from basemap.ground import grid, rasterize as R
from plugins.farm.ingest import classes as C
from plugins.farm.ingest import credits

FORMAT = "tvt-farm-build/1"
GREEN, GROWING = 0.6, 0.3                  # July NDVI cuts (farm design; checked on the ten boxes' photos)
STATES = {1: "green", 2: "growing", 3: "bare"}
CONFIDENCE = {1: "field interior", 2: "field edge band where the CDL pixel agrees",
              3: "CDL crop cluster of at least 0.5 ha outside every field"}
CLUSTER_MIN_CELLS = 50                     # 0.5 ha of 10 m cells
HALO_M = 500.0                             # >= CLUSTER_MIN_CELLS cells, so cluster sizes are exact in the core
WINDOW_CELLS = 2048
STRIP_ROWS = 1024
NDVI_SCALE = 10000.0                       # the NDVI median is NDVI x 10000 (int16)
NDVI_NODATA = -32768
RASTER = re.compile(r"^cdl_([0-9]{4})_([0-9]+)m\.tif$")
ACQUISITION = re.compile(r"\b([0-9]{4})-([0-9]{2})-([0-9]{2})\b")
SENTINEL_YEAR = re.compile(r"Sentinel data ([0-9]{4})\b")
JULY = 7
YEAR_COLUMN = re.compile(r"^CDL([0-9]{4})$")

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


def state_of(ndvi):
    """1 green, 2 growing, 3 bare or harvested (NDVI as a fraction); arrays or scalars."""
    return np.where(ndvi >= GREEN, 1, np.where(ndvi >= GROWING, 2, 3)).astype(np.uint8)


# --- inputs ---------------------------------------------------------------------------------------------------------

def read_fields(gpkg_path, work):
    """The fields from CSB's GeoPackage, made valid, written to two FlatGeobufs in `work` with an integer n (1..N):
    one in the file's CRS (for the CDL grids) and one on the ground grid's (EPSG:32611, null datum shift).
    Returns (ids [N+1], years, codes [N+1, years], path_src, path_utm, repaired); row 0 is "no field"."""
    ds = ogr.Open(gpkg_path)
    if ds is None or ds.GetLayerCount() != 1:
        raise BuildError(f"{gpkg_path}: expected one layer")
    lyr = ds.GetLayer(0)
    defn = lyr.GetLayerDefn()
    names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
    years = sorted(int(m.group(1)) for n in names if (m := YEAR_COLUMN.match(n)))
    if len(years) < 2 or years != list(range(years[0], years[-1] + 1)) or "CSBID" not in names:
        raise BuildError(f"{gpkg_path}: no CSBID or no consecutive CDL<year> columns")
    src_srs = lyr.GetSpatialRef()
    utm = R.srs_of(grid.CRS)
    ct = osr.CoordinateTransformation(R.srs_of(src_srs), utm)
    paths = os.path.join(work, "fields_src.fgb"), os.path.join(work, "fields_utm.fgb")
    drv = ogr.GetDriverByName("FlatGeobuf")
    outs = []
    for path, srs in zip(paths, (src_srs, utm)):
        o = drv.CreateDataSource(path)
        layer = o.CreateLayer("fields", srs, ogr.wkbMultiPolygon, ["SPATIAL_INDEX=YES"])
        layer.CreateField(ogr.FieldDefn("n", ogr.OFTInteger))
        outs.append((o, layer))
    ids, codes = [None], [[0] * len(years)]
    repaired = 0
    gdal.PushErrorHandler("CPLQuietErrorHandler")      # GEOS warns once per self-intersecting ring (803 in CSB)
    try:
        for f in lyr:
            g = f.GetGeometryRef()
            if g is None or g.IsEmpty():
                continue
            g = g.Clone()
            if not g.IsValid():
                g = g.MakeValid()
                repaired += 1
            g = ogr.ForceToMultiPolygon(_polygons(g))
            if g.IsEmpty():
                continue
            ids.append(f.GetFieldAsString("CSBID").strip())
            codes.append([f.GetFieldAsInteger(f"CDL{y}") if not f.IsFieldNull(f"CDL{y}") else 0 for y in years])
            n = len(ids) - 1
            for i, (o, layer) in enumerate(outs):
                gg = g.Clone()
                if i == 1:
                    gg.Transform(ct)
                feat = ogr.Feature(layer.GetLayerDefn())
                feat.SetField("n", n)
                feat.SetGeometry(gg)
                layer.CreateFeature(feat)
    finally:
        gdal.PopErrorHandler()
    o = layer = feat = None
    outs.clear()                                  # closes both FlatGeobufs: their index is written on close
    ds = None
    if len(ids) == 1:
        raise BuildError(f"{gpkg_path}: no fields")
    if len(set(ids[1:])) != len(ids) - 1:
        raise BuildError(f"{gpkg_path}: CSBIDs repeat")
    return ids, years, np.asarray(codes, np.int32), paths[0], paths[1], repaired


def _polygons(g):
    """Only the polygon parts of a geometry (MakeValid can return a collection with lines)."""
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
        return g
    out = ogr.Geometry(ogr.wkbMultiPolygon)
    if t == ogr.wkbGeometryCollection:
        for i in range(g.GetGeometryCount()):
            p = g.GetGeometryRef(i)
            pt = ogr.GT_Flatten(p.GetGeometryType())
            if pt == ogr.wkbPolygon:
                out.AddGeometry(p)
            elif pt == ogr.wkbMultiPolygon:
                for j in range(p.GetGeometryCount()):
                    out.AddGeometry(p.GetGeometryRef(j))
    return out


def cdl_rasters(folder):
    """{year: (res_m, path)} for cdl_<year>_<res>m.tif in a folder."""
    out = {}
    for name in sorted(os.listdir(folder)):
        m = RASTER.match(name)
        if m:
            out[int(m.group(1))] = (float(m.group(2)), os.path.join(folder, name))
    if not out:
        raise BuildError(f"{folder}: no cdl_<year>_<res>m.tif")
    return out


# --- 1. agreement ---------------------------------------------------------------------------------------------------

def agreement(path, fields_src, field_codes, n_fields, strip_rows=STRIP_ROWS):
    """(matching, total) pixel counts per field (index n) for one CDL raster, on its own grid, in row strips."""
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    w, h = ds.RasterXSize, ds.RasterYSize
    match = np.zeros(n_fields + 1, np.int64)
    total = np.zeros(n_fields + 1, np.int64)
    for r0 in range(0, h, strip_rows):
        rows = min(strip_rows, h - r0)
        target = R.target_of(path, (0, r0, w, rows))
        ids = R.rasterize(target, fields_src, attribute="n", dtype="int32")
        cdl = band.ReadAsArray(0, r0, w, rows)
        valid = (ids > 0) & (cdl > 0)
        if not valid.any():
            continue
        ii = ids[valid]
        total += np.bincount(ii, minlength=n_fields + 1)
        same = cdl[valid] == field_codes[ii]
        match += np.bincount(ii[same], minlength=n_fields + 1)
    return match, total


# --- 2 and 3. July state and crop_cover -------------------------------------------------------------------------------

def area_of(ds):
    """The grid window a raster covers (it must be on the 10 m grid exactly)."""
    gt = ds.GetGeoTransform()
    if not grid.aligned(gt, grid.BASE_RES):
        raise BuildError(f"the NDVI raster isn't on the ground's 10 m grid ({gt})")
    srs = osr.SpatialReference(wkt=ds.GetProjection())
    if srs.GetAuthorityCode(None) != str(grid.EPSG):
        raise BuildError(f"the NDVI raster is in {srs.GetName()}, not {grid.CRS}")
    w, n = gt[0], gt[3]
    return grid.window((w, n - ds.RasterYSize * 10.0, w + ds.RasterXSize * 10.0, n), grid.BASE_RES, snap="exact")


def ndvi_dates(ds):
    """What the NDVI median's tags say of its dates: (year, [first, last] view dates, or None). ACQUISITIONS lists the
    views it's the median of; without it, CREDIT's "Copernicus Sentinel data <year>". (None, None) when it says
    neither. Views outside July or from more than one year are refused: the state is one year's July state."""
    md = ds.GetMetadata() or {}
    try:
        dates = sorted({dt.date(int(y), int(m), int(d)) for y, m, d in ACQUISITION.findall(md.get("ACQUISITIONS", ""))})
    except ValueError as err:
        raise BuildError(f"the NDVI raster's ACQUISITIONS tag has a date that isn't one ({err})") from None
    if dates:
        ys = sorted({d.year for d in dates})
        if len(ys) > 1:
            raise BuildError(f"the NDVI raster's views are from {ys}: a July median is one year's")
        off = [d for d in dates if d.month != JULY]
        if off:
            raise BuildError(f"the NDVI raster has views outside July ({off[0].isoformat()}): not a July median")
        return dates[0].year, [dates[0].isoformat(), dates[-1].isoformat()]
    m = SENTINEL_YEAR.search(md.get("CREDIT", ""))
    return (int(m.group(1)), None) if m else (None, None)


def july_year_of(ds, given=None):
    """(the July state's year, its views' first and last dates or None): the NDVI's tags, which --july-year must
    agree with; --july-year alone only for a raster without tags."""
    year, span = ndvi_dates(ds)
    if given and year and given != year:
        raise BuildError(f"--july-year {given}, but the NDVI raster's tags say {year}")
    if not (given or year):
        raise BuildError("the NDVI raster doesn't say its year (no ACQUISITIONS or CREDIT tag): pass --july-year")
    return given or year, span


def read_padded(band, area, win, fill, dtype):
    """A window of a band whose raster covers `area` (both on one grid level), filled outside the raster."""
    out = np.full(win.shape, fill, dtype)
    c0, r0 = max(win.col, area.col), max(win.row, area.row)
    c1, r1 = min(win.col + win.width, area.col + area.width), min(win.row + win.height, area.row + area.height)
    if c1 > c0 and r1 > r0:
        out[r0 - win.row:r1 - win.row, c0 - win.col:c1 - win.col] = band.ReadAsArray(
            c0 - area.col, r0 - area.row, c1 - c0, r1 - r0)
    return out


def warp_cdl(path, win):
    """The CDL raster resampled (nearest) onto a grid window, under the null datum shift; 0 where it has no data."""
    src = gdal.Open(path)
    w, s, e, n = win.bounds
    out = gdal.Warp("", src, format="MEM", outputBounds=(w, s, e, n), width=win.width, height=win.height,
                    srcSRS=R.warp_srs(src.GetProjection()), dstSRS=R.warp_srs(grid.CRS), resampleAlg="near",
                    srcNodata=0, dstNodata=0, outputType=gdal.GDT_Byte, multithread=False)
    arr = out.GetRasterBand(1).ReadAsArray()
    if arr.shape != win.shape:
        raise BuildError(f"warped CDL is {arr.shape}, the window {win.shape}")
    return arr


def smooth_ndvi(raw):
    """The NDVI (fraction) averaged over each cell's 3 x 3 valid cells; NaN where none is valid."""
    valid = raw != NDVI_NODATA
    v = np.where(valid, raw.astype(np.float32) / NDVI_SCALE, 0.0).astype(np.float32)
    s = ndimage.uniform_filter(v, size=3, mode="constant")
    k = ndimage.uniform_filter(valid.astype(np.float32), size=3, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(k > 0, s / k, np.nan).astype(np.float32)


def cover_window(core, padded, fields_utm, cover_of_field, cdl_cover, ndvi_raw, n_fields):
    """crop_cover's three bands for one core window (arrays of core.shape), and the (field n, NDVI) pairs of its
    cells whose centres are inside a field."""
    ids_in = R.rasterize(padded, fields_utm, attribute="n", dtype="int32")
    ids_touch = R.rasterize(padded, fields_utm, attribute="n", dtype="int32", all_touched=True)
    lo = ndimage.minimum_filter(ids_in, size=3, mode="nearest")
    hi = ndimage.maximum_filter(ids_in, size=3, mode="nearest")
    interior = (ids_in > 0) & (lo == ids_in) & (hi == ids_in)
    owner = np.where(ids_in > 0, ids_in, ids_touch)
    fgroup = cover_of_field[owner]                       # the field's crop group code (0 when none or not crop)

    group = np.zeros(padded.shape, np.uint8)
    conf = np.zeros(padded.shape, np.uint8)
    inner = interior & (fgroup > 0)
    group[inner], conf[inner] = fgroup[inner], 1
    edge = (owner > 0) & ~interior & (fgroup > 0) & (cdl_cover == fgroup)
    group[edge], conf[edge] = fgroup[edge], 2
    outside = (ids_touch == 0) & (cdl_cover > 0)
    if outside.any():
        labels, n = ndimage.label(outside, structure=np.ones((3, 3), bool))
        sizes = np.bincount(labels.ravel(), minlength=n + 1)
        border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
        keep = sizes >= CLUSTER_MIN_CELLS
        keep[border] = True
        keep[0] = False
        cluster = keep[labels]
        group[cluster], conf[cluster] = cdl_cover[cluster], 3

    smooth = smooth_ndvi(ndvi_raw)
    state = np.zeros(padded.shape, np.uint8)
    crop = (group > 0) & np.isfinite(smooth)
    state[crop] = state_of(smooth[crop])

    cut = core.inner(padded)
    in_core = ids_in[cut]
    raw = ndvi_raw[cut]
    pick = (in_core > 0) & (raw != NDVI_NODATA)
    return group[cut], state[cut], conf[cut], in_core[pick].astype(np.int32), raw[pick].astype(np.int16)


def medians(ns, values, n_fields):
    """(median, count) per field index from (n, value) pairs; NaN where a field has none."""
    count = np.bincount(ns, minlength=n_fields + 1)
    med = np.full(n_fields + 1, np.nan)
    if ns.size == 0:
        return med, count
    order = np.lexsort((values, ns))
    v = values[order].astype(np.float64)
    start = np.concatenate([[0], np.cumsum(count)[:-1]])
    have = count > 0
    lo = start[have] + (count[have] - 1) // 2
    hi = start[have] + count[have] // 2
    med[have] = (v[lo] + v[hi]) / 2
    return med, count


def create_cover(path, area, meta):
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, area.width, area.height, 3, gdal.GDT_Byte,
                    ["TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512", "COMPRESS=DEFLATE", "PREDICTOR=2",
                     "BIGTIFF=NO"])
    ds.SetGeoTransform(area.transform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(grid.EPSG)
    ds.SetProjection(srs.ExportToWkt())
    ds.SetMetadata(meta)
    for i, name in enumerate(("group", "state", "confidence"), start=1):
        b = ds.GetRasterBand(i)
        b.SetDescription(name)
        b.Fill(0)
    return ds


# --- the build ------------------------------------------------------------------------------------------------------

def build(csb, cdl_dir, ndvi, out, cover_year=None, july_year=None, window_cells=WINDOW_CELLS, log=print):
    started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if os.path.exists(os.path.join(out, "build.json")):
        raise BuildError(f"{out} already holds a finished build")
    classes = C.read()
    rasters = cdl_rasters(cdl_dir)
    nds = gdal.Open(ndvi)
    july_year, july_span = july_year_of(nds, july_year)      # before anything is written
    area = area_of(nds)
    os.makedirs(out, exist_ok=True)
    gdal.SetCacheMax(128 * 1024 * 1024)
    work = tempfile.mkdtemp(prefix="farm-build-", dir=out)
    try:
        ids, years, codes, fields_src, fields_utm, repaired = read_fields(csb, work)
        n_fields = len(ids) - 1
        log(f"fields: {n_fields} ({repaired} made valid), years {years[0]}-{years[-1]}")
        cover_year = cover_year or years[-1]
        if cover_year not in rasters or cover_year not in years:
            raise BuildError(f"the cover year {cover_year} needs both a CDL raster and a CSB year")
        if july_year != cover_year:
            log(f"the July state is {july_year}'s (the NDVI's), the crops {cover_year}'s")

        # 1. agreement per CDL year held
        agree, px = {}, {}
        for year in sorted(rasters):
            if year not in years:
                log(f"agreement: skipping CDL {year} (outside CSB's {years[0]}-{years[-1]})")
                continue
            match, total = agreement(rasters[year][1], fields_src, codes[:, years.index(year)], n_fields)
            agree[year], px[year] = match, total
            have = total[1:] > 0
            share = match[1:][have].sum() / max(total[1:][have].sum(), 1)
            log(f"agreement {year}: {have.sum()} fields with pixels, {share:.3f} of their pixels match")

        # 2 and 3. July state and crop_cover, window by window
        nband = nds.GetRasterBand(1)
        nodata = nband.GetNoDataValue()
        if nodata is not None and int(nodata) != NDVI_NODATA:
            raise BuildError(f"the NDVI raster's nodata is {nodata}, expected {NDVI_NODATA}")
        table = np.asarray(C.cover_table(classes), np.uint8)
        cover_of_field = table[np.clip(codes[:, years.index(cover_year)], 0, 255)]
        cover_of_field[0] = 0
        cover_path = os.path.join(out, "crop_cover.tif")
        meta = {"CREDIT": credits.build((years[0], years[-1]), cover_year, july_year),
                "JULY": f"July {july_year} NDVI median" + (f" ({july_span[0]} to {july_span[1]})" if july_span else ""),
                "BANDS": "group (0 none, 1 corn, 2 hay, 3 grain, 4 roots, 5 specialty, 6 fallow); state (0 none, "
                         "1 green, 2 growing, 3 bare or harvested); confidence (0 none, 1 field interior, 2 field "
                         "edge band where the CDL agrees, 3 CDL crop cluster >= 0.5 ha outside every field)",
                "SOURCE": "plugins/farm/build/build.py"}
        cds = create_cover(cover_path, area, meta)
        ns_all, v_all = [], []
        cells = np.zeros((7, 4), np.int64)              # [group, confidence]
        states = np.zeros(4, np.int64)
        windows = list(grid.windows(grid.BASE_RES, window_cells, bounds=area.bounds, halo_m=HALO_M))
        for i, (core, padded) in enumerate(windows, 1):
            cdl_cover = table[warp_cdl(rasters[cover_year][1], padded)]
            raw = read_padded(nband, area, padded, NDVI_NODATA, np.int16)
            g, s, c, ns, vs = cover_window(core, padded, fields_utm, cover_of_field, cdl_cover, raw, n_fields)
            x0, y0 = core.col - area.col, core.row - area.row
            for b, arr in enumerate((g, s, c), start=1):
                cds.GetRasterBand(b).WriteArray(arr, x0, y0)
            cells += np.bincount(g.ravel().astype(np.int64) * 4 + c.ravel(), minlength=28).reshape(7, 4)
            states += np.bincount(s.ravel(), minlength=4)
            ns_all.append(ns)
            v_all.append(vs)
            if i % 10 == 0 or i == len(windows):
                log(f"crop_cover: {i}/{len(windows)} windows")
        cds.FlushCache()
        del cds
        med, n_px = medians(np.concatenate(ns_all), np.concatenate(v_all), n_fields)
        del ns_all, v_all

        # fields.jsonl
        fields_path = os.path.join(out, "fields.jsonl")
        july_counts = {"green": 0, "growing": 0, "bare": 0, "none": 0}
        with open(fields_path, "w", encoding="utf-8") as fh:
            for n in range(1, n_fields + 1):
                row = {"field_id": ids[n],
                       "agree": {str(y): round(float(agree[y][n] / px[y][n]), 3) for y in agree if px[y][n]},
                       "px": {str(y): int(px[y][n]) for y in agree if px[y][n]}}
                if n_px[n]:
                    v = float(med[n]) / NDVI_SCALE
                    st = STATES[int(state_of(np.float64(v)))]
                    row["july"] = {"year": july_year, "ndvi": round(v, 3), "state": st, "px": int(n_px[n])}
                    july_counts[st] += 1
                else:
                    row["july"] = None
                    july_counts["none"] += 1
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    names = {v: k for k, v in C.COVER_CODES.items()}
    finished = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    doc = {
        "format": FORMAT,
        "build_id": os.path.basename(os.path.normpath(out)),
        "started_at": started.isoformat().replace("+00:00", "Z"),
        "finished_at": finished.isoformat().replace("+00:00", "Z"),
        "csb_years": [years[0], years[-1]],
        "cover_year": cover_year, "july_year": july_year,
        "credit": credits.build((years[0], years[-1]), cover_year, july_year),
        "grid": {"crs": grid.CRS, "res": grid.BASE_RES, "west": area.west, "north": area.north,
                 "width": area.width, "height": area.height},
        "params": {"green": GREEN, "growing": GROWING, "state_smoothing": "3x3 mean of valid cells",
                   "interior": "the cell and its 8 neighbours' centres inside one field",
                   "edge": "cells a field touches, not interior, kept where the CDL pixel is the field's group",
                   "cluster_min_cells": CLUSTER_MIN_CELLS, "cluster_connectivity": 8, "halo_m": HALO_M,
                   "datum": "NAD83 taken as WGS 84 (null shift)", "cover_codes": C.COVER_CODES,
                   "states": STATES, "confidence": CONFIDENCE},
        "inputs": {
            "csb": {"path": os.path.abspath(csb), "sha256": sha256_of(csb), "bytes": os.path.getsize(csb)},
            "cdl": {str(y): {"path": os.path.abspath(p), "sha256": sha256_of(p), "res_m": r}
                    for y, (r, p) in sorted(rasters.items())},
            "ndvi": {"path": os.path.abspath(ndvi), "sha256": sha256_of(ndvi), "bytes": os.path.getsize(ndvi),
                     "year": july_year, "acquired": july_span},
        },
        "files": {name: {"sha256": sha256_of(os.path.join(out, name)), "bytes": os.path.getsize(os.path.join(out, name))}
                  for name in ("fields.jsonl", "crop_cover.tif")},
        "counts": {
            "fields": n_fields, "made_valid": repaired,
            "fields_with_july": n_fields - july_counts["none"], "july": july_counts,
            "agreement_fields": {str(y): int((px[y][1:] > 0).sum()) for y in agree},
            "agreement_share": {str(y): round(float(agree[y][1:].sum() / max(px[y][1:].sum(), 1)), 4) for y in agree},
            "cover_cells": {names[g]: {CONFIDENCE[c]: int(cells[g, c]) for c in (1, 2, 3) if cells[g, c]}
                            for g in range(1, 7) if cells[g].any()},
            "cover_states": {STATES[s]: int(states[s]) for s in (1, 2, 3)},
        },
    }
    tmp = os.path.join(out, ".build.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, os.path.join(out, "build.json"))
    log(f"done: {out} ({(finished - started).total_seconds():.0f} s)")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csb", required=True, help="CSB cut to the map box (GeoPackage)")
    ap.add_argument("--cdl", required=True, help="a folder of cdl_<year>_<res>m.tif ($TVT_ARCHIVE/farm/cdl)")
    ap.add_argument("--ndvi", required=True, help="the July NDVI median on the ground's 10 m grid (NDVI x 10000, int16)")
    ap.add_argument("--out", required=True, help="the build folder ($TVT_ARCHIVE/farm/build/<id>), new or unfinished")
    ap.add_argument("--cover-year", type=int, help="the crop year crop_cover shows (default: CSB's newest)")
    ap.add_argument("--july-year", type=int, help="the NDVI's year, only for a raster whose tags don't say it "
                                                   "(ACQUISITIONS or CREDIT); otherwise it must agree with them")
    ap.add_argument("--window", type=int, default=WINDOW_CELLS, help="window size in 10 m cells")
    args = ap.parse_args(argv)
    try:
        build(args.csb, args.cdl, args.ndvi, args.out, args.cover_year, args.july_year, args.window,
              log=lambda m: print(f"farm build: {m}", flush=True))
    except BuildError as err:
        print(f"farm build: {err}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
