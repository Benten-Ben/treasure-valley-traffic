"""Build one area's shrubs (docs/19 §19.8). Runs in the worker image (PDAL, GDAL, rasterio, NumPy, SciPy, pyproj), as a
heavy job (plan §4.4: --memory 6g, day windows):

    python plugins/trees/build/build_shrubs.py --area c --dsm .../dsm.tif --dtm .../dtm.tif --mask .../zero_mask_c.npy \\
      --photo .../naip2025/c.tif --points .../USGS_LPC_ID_SouthernGaps_D23_5630_8310.laz ... \\
      --crop .../csb_mapbox.gpkg --crop-where "CDL2025 BETWEEN 1 AND 61 OR ..." \\
      --lidar "USGS 3DEP QL1 lidar (ID_SouthernGaps_D23)" --lidar-date 2023-10-24 --out $TVT_ARCHIVE/trees/shrubs/<id>

Then `python3 -m ingest shrubs-load --build <out>` loads it.

Inputs, all on or onto the lidar products' 0.5 m grid (the DSM's):
- --dsm, --dtm: the area's lidar surface and bare earth (the trees build's products); --mask: its building mask (.npy
  of the DSM's shape, as the trees build takes).
- --points: the area's point cloud (LAS/LAZ tiles, or an EPT's ept.json; --points-srs when the files' own CRS isn't
  the one to read them in). It gives each cell's returns above the ground and their scatter (cloud.py). Kept in
  <out>/work/ until every chunk is done, so a stopped build picks up where it was.
- --photo: the summer photo (NAIP: red, green, blue, near-infrared), for NDVI, moved onto the lidar: --photo-shift
  auto (the default) measures where its green best meets the lidar's trees (measure_shift); or give it in metres east
  and north. The green cut is the area's own (shrubs.ndvi_cut). A photo or crop raster in the grid's UTM zone on
  another datum (NAIP's NAD83) is read with a null datum shift (same_frame).
- --crop: where crops grow, which shrubs leave alone: farm's fields (a vector of crop fields, or crop_cover.tif, where
  band 1 > 0 is crop). Until farm's fields are built, CSB's crop fields (plan C7). --crop-where filters a vector's
  features (OGR SQL). Without --crop no clump is called a crop; the crop-field rule still reports what it would have
  dropped (crop_check in build.json).
- --skip-rect x0,y0,x1,y1 (grid CRS, repeatable): part of the grid that belongs to another area (downtown's box
  overlaps the North End's): shrubs centred there are left out, and so is that part of the area's outline.

Writes to --out: shrubs.geojson (WGS84 points: id, look, height_m, width_m, ground_m, fit), build.json (the area's
outline, settings, counts, the crop check and the score) and why.tif (uint8 per cell: 1 shrub, 2 speck, 3 skirt,
4 gap, 5 crop; 0 elsewhere; for image sheets).

Sources and credit: USGS 3D Elevation Program lidar and USDA NAIP (public domain); the crop fields' (CSB and CDL:
public domain, USDA NASS). Nothing here reads a tree catalogue."""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time

import numpy as np
import rasterio
import rasterio.windows
from rasterio import features as rfeatures
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject
from pyproj import Transformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cloud  # noqa: E402
import shrubs as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(os.path.dirname(HERE), "model", "shrub_model.json")
OUTLINE_CELLS = 10              # the area's outline is traced on 5 m blocks
CREDIT = "U.S. Geological Survey, 3D Elevation Program; USDA NAIP"


def read_grid(dsm_path, dtm_path):
    with rasterio.open(dsm_path) as ds:
        dsm = ds.read(1).astype(np.float32)
        nod, tf, crs = ds.nodata, ds.transform, ds.crs
    with rasterio.open(dtm_path) as ds:
        dtm = ds.read(1).astype(np.float32)
        if ds.transform != tf or ds.shape != dsm.shape:
            raise SystemExit("the DSM and DTM aren't on one grid")
        dnod = ds.nodata
    if abs(tf.a - S.PX) > 1e-6 or abs(tf.e + S.PX) > 1e-6 or tf.b or tf.d:
        raise SystemExit(f"the lidar grid must be {S.PX} m, north up (got {tf})")
    bad = ~np.isfinite(dsm) | ~np.isfinite(dtm)
    if nod is not None:
        bad |= dsm == nod
    if dnod is not None:
        bad |= dtm == dnod
    return dsm, dtm, bad, tf, crs


def same_frame(src_crs, grid_crs):
    """True when src_crs is the grid's UTM zone, on whatever datum: it is then read as if it were on the grid's (a null
    datum shift). NAD83's realisations (NAIP's NAD83, the lidar's NAD83(2011)) and WGS 84 differ by a metre or so
    here: less than the photo shift measured on each area, and far less than a crop field's edge. Doing it properly
    takes NOAA's grids, which PROJ would fetch from the network, and a build fetches nothing."""
    from pyproj import CRS
    a, b = CRS.from_user_input(src_crs), CRS.from_user_input(grid_crs)
    return a.utm_zone is not None and a.utm_zone == b.utm_zone


def read_onto(path, bands, tf, crs, shape, resampling, pad=0):
    """Bands of a raster onto the grid (grown by pad cells each side), float32, 0 where it has nothing."""
    out = np.zeros((len(bands), shape[0] + 2 * pad, shape[1] + 2 * pad), np.float32)
    dst = tf @ Affine.translation(-pad, -pad)
    with rasterio.open(path) as ds:
        if max(bands) > ds.count:
            raise SystemExit(f"{path}: has {ds.count} bands, needs {max(bands)}")
        src_crs = crs if same_frame(ds.crs, crs) else ds.crs
        win = None
        if src_crs is crs:                 # read only the grid's part (and 5 m around it)
            x0, y1 = dst.c, dst.f
            x1, y0 = x0 + out.shape[2] * S.PX, y1 - out.shape[1] * S.PX
            inv = ~ds.transform
            cs, rs = zip(*(inv @ (x, y) for x in (x0 - 5, x1 + 5) for y in (y0 - 5, y1 + 5)))
            c0, r0 = max(0, math.floor(min(cs))), max(0, math.floor(min(rs)))
            c1, r1 = min(ds.width, math.ceil(max(cs))), min(ds.height, math.ceil(max(rs)))
            if c1 <= c0 or r1 <= r0:
                raise SystemExit(f"{path} doesn't reach the area")
            win = rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0)
        for i, b in enumerate(bands):
            src = ds.read(b, window=win) if win is not None else ds.read(b)
            stf = ds.window_transform(win) if win is not None else ds.transform
            reproject(src, out[i], src_transform=stf, src_crs=src_crs, src_nodata=ds.nodata, dst_transform=dst,
                      dst_crs=crs, dst_nodata=0, resampling=resampling)
    return out


def ndvi_of(red, nir):
    s = red + nir
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, (nir - red) / np.maximum(s, 1e-6), np.nan).astype(np.float32)


SHIFT_REACH = 12          # cells (6 m) each way
SHIFT_MIN_TREE_CELLS = 4000
SHIFT_MIN_IOU = 0.1


def measure_shift(ndvi_pad, h, bld, bad):
    """The photo's shift onto the lidar, in whole cells, as the spike measured it: the offset (up to 6 m each way)
    where the photo's green best overlaps the lidar's trees (2.4 m and up, not buildings), by IoU. None of it where
    there are too few trees or the overlap is weak (deserts): no shift. Returns ((dx, dy), detail)."""
    P = SHIFT_REACH
    rows, cols = h.shape
    trees = (h >= S.BAND_M[1]) & ~bld & ~bad
    nt = int(trees.sum())
    at = lambda dx, dy: ndvi_pad[P + dy:P + dy + rows, P + dx:P + dx + cols]  # noqa: E731
    cut, _ = S.ndvi_cut(at(0, 0), h, bld, bad)

    def iou(dx, dy):
        g = np.nan_to_num(at(dx, dy), nan=-1.0) >= cut
        u = int((g | trees).sum())
        return int((g & trees).sum()) / u if u else 0.0
    i0 = iou(0, 0)
    detail = {"tree_cells": nt, "iou_at_0": round(i0, 3)}
    if nt < SHIFT_MIN_TREE_CELLS:
        detail["why"] = "too few trees to measure it: no shift"
        return (0, 0), detail
    scores = {(dx, dy): iou(dx, dy) for dx in range(-P, P + 1, 2) for dy in range(-P, P + 1, 2)}
    bx, by = max(scores, key=scores.get)
    for dx in range(max(-P, bx - 1), min(P, bx + 1) + 1):
        for dy in range(max(-P, by - 1), min(P, by + 1) + 1):
            if (dx, dy) not in scores:
                scores[(dx, dy)] = iou(dx, dy)
    best = max(scores, key=lambda k: (scores[k], -abs(k[0]) - abs(k[1])))
    detail["iou_best"] = round(scores[best], 3)
    if scores[best] < SHIFT_MIN_IOU:
        detail["why"] = "the photo's green barely meets the trees anywhere: no shift"
        return (0, 0), detail
    detail["why"] = "the best overlap of the photo's green and the lidar's trees"
    return best, detail


def photo_ndvi(path, tf, crs, shape, shift, h, bld, bad):
    """NDVI on the grid from the photo's red (band 1) and near-infrared (band 4), averaged onto the 0.5 m cells and
    moved onto the lidar. shift: where the photo's features sit against the lidar's, (east, north) in metres, rounded
    to whole cells, or "auto" (measure_shift). Grid cell (r, c) takes the photo at the grid's (r + dy, c + dx), so
    east = dx x 0.5 m and north = -dy x 0.5 m, as the spike recorded its shifts. Returns (ndvi, (east_m, north_m),
    detail)."""
    P = SHIFT_REACH
    red, nir = read_onto(path, (1, 4), tf, crs, shape, Resampling.average, pad=P)
    ndvi_pad = ndvi_of(red, nir)
    if shift == "auto":
        (dx, dy), detail = measure_shift(ndvi_pad, h, bld, bad)
    else:
        dx, dy = int(round(shift[0] / S.PX)), int(round(-shift[1] / S.PX))
        if max(abs(dx), abs(dy)) > P:
            raise SystemExit(f"a photo shift of {shift} m is more than {P * S.PX} m")
        detail = {"why": "given"}
    rows, cols = shape
    return ndvi_pad[P + dy:P + dy + rows, P + dx:P + dx + cols].copy(), (dx * S.PX, -dy * S.PX), detail


def crop_mask(path, where, tf, crs, shape):
    """Crop fields on the grid: a raster (band 1 > 0) or a vector's polygons (filtered by where). A vector on another
    datum is moved onto the grid's with a null datum shift, as same_frame says why."""
    if path.lower().endswith((".tif", ".tiff")):
        out = read_onto(path, (1,), tf, crs, shape, Resampling.nearest)[0]
        return out > 0, {"crop_raster": os.path.basename(path)}
    from osgeo import ogr, osr
    ogr.UseExceptions()
    osr.UseExceptions()
    ds = ogr.Open(path)
    lyr = ds.GetLayer(0)
    if where:
        lyr.SetAttributeFilter(where)
    src = lyr.GetSpatialRef()
    dst = osr.SpatialReference()
    dst.ImportFromWkt(crs.to_wkt())
    src_g, dst_g = src.CloneGeogCS(), dst.CloneGeogCS()
    for r in (src, dst, src_g, dst_g):
        r.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    unproject = osr.CoordinateTransformation(src, src_g)     # to longitude and latitude on its own datum
    project = osr.CoordinateTransformation(dst_g, dst)       # from the grid's datum's: the null datum shift
    x0, y1 = tf.c, tf.f
    x1, y0 = x0 + shape[1] * tf.a, y1 + shape[0] * tf.e
    box = ogr.CreateGeometryFromWkt(f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))")
    geoms = []
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None:
            continue
        g = g.Clone()
        g.Transform(unproject)
        g.Transform(project)
        if g.Intersects(box):
            geoms.append(json.loads(g.ExportToJson()))
    if not geoms:
        return np.zeros(shape, bool), {"crop_fields": 0}
    m = rfeatures.rasterize(((g, 1) for g in geoms), out_shape=shape, transform=tf, fill=0, dtype="uint8")
    return m > 0, {"crop_fields": len(geoms)}


def parse_rect(s):
    v = [float(x) for x in s.split(",")]
    if len(v) != 4 or v[0] >= v[2] or v[1] >= v[3]:
        raise argparse.ArgumentTypeError("x0,y0,x1,y1 with x0 < x1 and y0 < y1")
    return tuple(v)


def in_rects(x, y, rects):
    out = np.zeros(np.shape(x), bool)
    for x0, y0, x1, y1 in rects:
        out |= (x >= x0) & (x < x1) & (y >= y0) & (y < y1)
    return out


def skip_mask(tf, shape, rects):
    """Cells whose centres fall in any of the rectangles."""
    xs = tf.c + (np.arange(shape[1]) + 0.5) * tf.a
    ys = tf.f + (np.arange(shape[0]) + 0.5) * tf.e
    out = np.zeros(shape, bool)
    for x0, y0, x1, y1 in rects:
        out |= ((ys >= y0) & (ys < y1))[:, None] & ((xs >= x0) & (xs < x1))[None, :]
    return out


def outline(bad, tf, crs, skip):
    """The area's outline in WGS84 (a GeoJSON MultiPolygon): the 5 m blocks with any lidar, cut exactly to the grid's
    edges, less the skipped rectangles (exactly too, so two areas' outlines meet without a gap or an overlap).
    Returns (geometry, hectares of lidar cells in it)."""
    from osgeo import ogr, osr
    ogr.UseExceptions()
    osr.UseExceptions()
    B = OUTLINE_CELLS
    rows, cols = bad.shape
    nr, nc = math.ceil(rows / B), math.ceil(cols / B)
    pad = np.ones((nr * B, nc * B), bool)
    pad[:rows, :cols] = bad
    has = ~pad.reshape(nr, B, nc, B).all(axis=(1, 3))
    btf = tf @ Affine.scale(B)
    rect = lambda x0, y0, x1, y1: ogr.CreateGeometryFromWkt(  # noqa: E731
        f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))")
    geom = ogr.Geometry(ogr.wkbMultiPolygon)
    for g, _ in rfeatures.shapes(has.astype(np.uint8), mask=has, transform=btf, connectivity=4):
        geom.AddGeometry(ogr.CreateGeometryFromJson(json.dumps(g)))
    geom = geom.UnionCascaded().Intersection(rect(tf.c, tf.f + rows * tf.e, tf.c + cols * tf.a, tf.f))
    for r in skip:
        geom = geom.Difference(rect(*r))
    src = osr.SpatialReference()
    src.ImportFromWkt(crs.to_wkt())
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    for r in (src, dst):
        r.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geom.Segmentize(50.0)                  # a straight edge in UTM bends a little in degrees
    geom.Transform(osr.CoordinateTransformation(src, dst))
    out = json.loads(geom.ExportToJson())
    if out["type"] == "Polygon":
        out = {"type": "MultiPolygon", "coordinates": [out["coordinates"]]}
    out["coordinates"] = [[[[round(x, 7), round(y, 7)] for x, y in ring] for ring in poly]
                          for poly in out["coordinates"]]
    valid = ~bad & ~skip_mask(tf, bad.shape, skip)
    return out, float(valid.sum()) * S.PX * S.PX / 1e4


def write_why(path, why, tf, crs):
    with rasterio.open(path + ".part", "w", driver="GTiff", width=why.shape[1], height=why.shape[0], count=1,
                       dtype="uint8", crs=crs, transform=tf, compress="deflate", nodata=None) as ds:
        ds.write(why, 1)
        ds.update_tags(1, codes=json.dumps(S.WHY))
    os.replace(path + ".part", path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--area", required=True)
    ap.add_argument("--dsm", required=True)
    ap.add_argument("--dtm", required=True)
    ap.add_argument("--mask", help="building mask (.npy, the DSM's shape)")
    ap.add_argument("--points", nargs="+", required=True, help="LAS/LAZ files, or an EPT's ept.json")
    ap.add_argument("--points-srs", help="the points' CRS when their files say otherwise (e.g. EPSG:3857)")
    ap.add_argument("--photo", required=True, help="the summer photo: 4 bands, red, green, blue, near-infrared")
    ap.add_argument("--photo-shift", default="auto",
                    help="where the photo's features sit against the lidar's, metres east,north (whole cells), "
                         "or auto (measured; the default)")
    ap.add_argument("--photo-name", default="USDA NAIP", help="the photo, for the record")
    ap.add_argument("--crop", help="crop fields: farm's fields (a vector) or crop_cover.tif (band 1 > 0)")
    ap.add_argument("--crop-where", help="OGR SQL filter on the crop vector's features")
    ap.add_argument("--skip-rect", type=parse_rect, action="append", default=[],
                    help="x0,y0,x1,y1 in the grid's CRS: another area's part (repeatable)")
    ap.add_argument("--lidar", default="USGS 3DEP lidar", help="the survey's name, for the record")
    ap.add_argument("--lidar-date", help="the flight date (YYYY-MM-DD)")
    ap.add_argument("--window", help="row0,col0,rows,cols: build only this part (tests)")
    ap.add_argument("--chunk-m", type=float, default=250.0, help="the point cloud's chunks (m a side)")
    ap.add_argument("--threads", type=int, default=1, help="threads for the covariance features")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    t0 = time.time()
    started = dt.datetime.now(dt.timezone.utc)
    log = lambda m: print(f"[{time.time() - t0:6.0f} s] {m}", flush=True)  # noqa: E731
    with open(MODEL) as f:
        spec = json.load(f)
    model = S.ShrubModel(spec)
    shift = a.photo_shift
    if shift != "auto":
        shift = tuple(float(v) for v in shift.split(","))
        if len(shift) != 2:
            ap.error("--photo-shift is east,north in metres, or auto")

    dsm, dtm, bad, tf, crs = read_grid(a.dsm, a.dtm)
    bld = np.load(a.mask).astype(bool) if a.mask else np.zeros(dsm.shape, bool)
    if bld.shape != dsm.shape:
        raise SystemExit(f"the building mask is {bld.shape}, the DSM {dsm.shape}")
    if a.window:
        r0, c0, nr, nc = (int(v) for v in a.window.split(","))
        sl = (slice(r0, r0 + nr), slice(c0, c0 + nc))
        dsm, dtm, bad, bld = dsm[sl], dtm[sl], bad[sl], bld[sl]
        tf = tf @ Affine.translation(c0, r0)
    shape = dsm.shape
    h = np.where(bad, 0, np.clip(dsm - dtm, 0, None)).astype(np.float32)
    treeh = np.where(bld, 0, h)
    log(f"area {a.area}: {shape[1]} x {shape[0]} cells, {float((~bad).mean()):.0%} with lidar")

    ndvi, shift_m, shift_detail = photo_ndvi(a.photo, tf, crs, shape, shift, h, bld, bad)
    log(f"photo: its features sit {shift_m[0]:+.1f} m east, {shift_m[1]:+.1f} m north of the lidar's, moved back "
        f"({shift_detail['why']})")
    cut, cut_detail = S.ndvi_cut(ndvi, h, bld, bad)
    alive = np.nan_to_num(ndvi, nan=-1.0) >= cut
    log(f"photo: green cut NDVI {cut:.3f} ({cut_detail['from']})")

    grid = cloud.Grid(tf.c, tf.f, S.PX, shape[0], shape[1])
    os.makedirs(a.out, exist_ok=True)
    n_ag, scat, cloud_stats = cloud.cues(a.points, grid, crs.to_string(), dtm, ~bad, os.path.join(a.out, "work"),
                                         chunk_m=a.chunk_m, threads=a.threads, in_srs=a.points_srs, log=log)
    shrub, band = S.shrub_cells(h, bld, bad, alive, n_ag, scat)
    log(f"rule: {int(shrub.sum()):,} shrub cells of {int(band.sum()):,} in the band")

    crop, crop_info = (np.zeros(shape, bool), {}) if not a.crop else crop_mask(a.crop, a.crop_where, tf, crs, shape)
    drop_crop, crop_clumps = S.crop_clumps(shrub, crop)
    field, blocks_first, blocks = S.field_rule(h, bld, alive)
    m = shrub & ~drop_crop
    crop_check = {
        "crop_input": crop_info or None,
        "crop_cells": int(crop.sum()),
        "clumps_called_crop": crop_clumps,
        "shrub_cells_called_crop": int(drop_crop.sum()),
        "rule_field_blocks": blocks_first,
        "rule_field_blocks_joined": blocks,
        "rule_field_cells": int(field.sum()),
        "rule_field_cells_in_crop": int((field & crop).sum()),
        "rule_shrub_cells": int((shrub & field).sum()),
        "rule_shrub_cells_left_by_crop": int((m & field).sum()),
    }
    log(f"crops: {crop_clumps} clumps ({int(drop_crop.sum()):,} cells) in crop fields; the field rule's "
        f"{blocks} blocks, {crop_check['rule_shrub_cells_left_by_crop']:,} of their shrub cells left as shrubs")

    found, why, dropped = S.split(h, m, alive, treeh, model)
    why[drop_crop] = S.WHY["crop"]
    dropped["crop"] = crop_clumps
    kept = why == S.WHY["shrub"]
    to_ll = Transformer.from_crs(crs, 4326, always_xy=True)
    if found:
        rows = np.array([s["row"] for s in found])
        cols = np.array([s["col"] for s in found])
        X, Y = tf @ (cols + 0.5, rows + 0.5)
        keep = ~in_rects(np.asarray(X), np.asarray(Y), a.skip_rect)
        found = [dict(s, x=float(x), y=float(y)) for s, x, y, k in zip(found, X, Y, keep) if k]
    in_field = sum(1 for s in found if field[min(int(s["row"]), shape[0] - 1), min(int(s["col"]), shape[1] - 1)])
    crop_check["rule_shrubs"] = in_field          # shrubs the spike's rule would have called a field
    log(f"split: {len(found):,} shrubs ({in_field:,} in the field rule's fields); dropped pieces {dropped}")

    geom, area_ha = outline(bad, tf, crs, a.skip_rect)
    out_feats, seen = [], {}
    for s in found:
        lon, lat = to_ll.transform(s["x"], s["y"])
        sid = f"{a.area}-{int(round(s['x'] * 10))}-{int(round(s['y'] * 10))}"
        seen[sid] = seen.get(sid, -1) + 1
        if seen[sid]:
            sid = f"{sid}-{seen[sid]}"
        gy = int(min(max(round(s["row"]), 0), shape[0] - 1))
        gx = int(min(max(round(s["col"]), 0), shape[1] - 1))
        out_feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]},
                          "properties": {"id": sid, "look": s["look"], "height_m": round(s["height_m"], 2),
                                         "width_m": round(s["width_m"], 2),
                                         "ground_m": None if bad[gy, gx] else round(float(dtm[gy, gx]), 2),
                                         "fit": {"cells": s["cells"], "green": s["green"], "split": s["split"],
                                                 "model_width_m": s["model_width_m"]}}})
    kept &= ~skip_mask(tf, shape, a.skip_rect)   # the score covers the area's own part only
    sc = S.score(h, kept, found, model)
    counts = S.summarise(found, area_ha)
    counts.update({"area_ha": round(area_ha, 2), "band_cells": int(band.sum()), "shrub_cells": int(shrub.sum()),
                   "kept_cells": int(kept.sum()), "dropped_pieces": dropped, "crop_check": crop_check, "score": sc,
                   "cloud": cloud_stats, "seconds": round(time.time() - t0)})
    params = {"lidar": a.lidar, "lidar_date": a.lidar_date, "points": [os.path.basename(p) for p in a.points],
              "points_srs": a.points_srs, "photo": a.photo_name, "photo_file": os.path.basename(a.photo),
              "photo_shift_m": list(shift_m), "photo_shift_detail": shift_detail, "ndvi_cut": round(cut, 3),
              "ndvi_cut_detail": cut_detail,
              "crop": os.path.basename(a.crop) if a.crop else None, "crop_where": a.crop_where,
              "skip_rects": [list(r) for r in a.skip_rect], "window": a.window, "grid_crs": crs.to_string(),
              "model": spec["source"][:200], "width": spec["width"],
              "rule": {"band_m": list(S.BAND_M), "plant_returns": S.PLANT_RETURNS, "plant_scatter": S.PLANT_SCATTER,
                       "ground_h_m": S.GROUND_H, "knn": cloud.KNN, "edge_m": S.EDGE_CELLS * S.PX,
                       "crop_clump_share": S.CROP_CLUMP_SHARE},
              "credit": CREDIT}
    build = {"build_id": os.path.basename(os.path.normpath(a.out)), "area": a.area, "started_at": started.isoformat(),
             "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "geom": geom, "params": params,
             "counts": counts}
    with open(os.path.join(a.out, "shrubs.geojson.part"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": out_feats}, f)
    os.replace(os.path.join(a.out, "shrubs.geojson.part"), os.path.join(a.out, "shrubs.geojson"))
    write_why(os.path.join(a.out, "why.tif"), why, tf, crs)
    with open(os.path.join(a.out, "build.json.part"), "w") as f:
        json.dump(build, f, indent=1)
    os.replace(os.path.join(a.out, "build.json.part"), os.path.join(a.out, "build.json"))
    log(json.dumps({k: counts[k] for k in ("shrubs", "per_hectare", "bush_share", "median_height_m", "score")}))


if __name__ == "__main__":
    main()
