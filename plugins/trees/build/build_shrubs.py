"""Build one area's shrubs (docs/19 §19.8). Runs in the worker image (PDAL, GDAL, rasterio, NumPy, SciPy, pyproj), as a
heavy job (plan §4.4: --memory 6g, day windows):

    python plugins/trees/build/build_shrubs.py --area c --dsm .../dsm.tif --dtm .../dtm.tif --mask .../zero_mask_c.npy \\
      --photo .../naip2025/c.tif --points .../USGS_LPC_ID_SouthernGaps_D23_5630_8310.laz ... \\
      --crop $TVT_ARCHIVE/farm/export/<build>/crop_cover.tif \\
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
  and north. The green cut is the area's own (shrubs.ndvi_cut). The photo must give an NDVI on at least
  PHOTO_MIN_COVER of the area's lidar cells, or the build stops.
- --crop: where crops grow, which shrubs leave alone: farm's crop cover (its export's crop_cover.tif, where band 1,
  the crop group, is above 0: crops in any state, decision 15), or a vector of crop fields (e.g. CSB's, filtered by
  --crop-where, OGR SQL). A crop raster must cover the whole grid. Without --crop nothing is called a crop; the
  crop-field rule still reports what it would have dropped (crop_check in build.json).
- --skip-rect x0,y0,x1,y1 (grid CRS, repeatable): part of the grid that belongs to another area (downtown's box
  overlaps the North End's): shrubs centred there are left out, and so is that part of the area's outline.

Frames. A build fetches nothing, so PROJ can't fetch NOAA's datum grids: a source in the grid's UTM zone on another
realisation of NAD83 (NAIP's NAD83) or on WGS 84 (the crop cover) is read with a null datum shift (same_frame); they
differ by a metre or so here, less than the photo shift measured on each area. A source on any other datum (NAD27,
say, about 100 m off) stops the build (check_datum).

Licence (plan C3, the export contract's rules in basemap/ground/manifest.py). Each input carries a licence class,
republish and credit: the lidar and the photo from this plugin's sources (plugin.json), the crop cover from its export
manifest (read and checked: sizes, sha256, licences, sources), or for a crop file without a manifest from
--crop-licence, --crop-republish and --crop-credit. The build's republish is the strictest of its inputs', its
licence the share-alike one or else one of the strictest, its credit every input's. The shrubs are published (the
trees plugin is public), so an input that may not be republished stops the build before any work.

Writes to --out: shrubs.geojson (WGS84 points: id, look, height_m, width_m, ground_m, fit), build.json (the area's
outline, licence, republish, credit, inputs with their sizes and sha256, settings, counts, the crop check and the
score) and why.tif (uint8 per cell: 1 shrub, 2 speck, 3 skirt, 4 gap, 5 crop; 0 elsewhere; for image sheets).

Sources and credit: USGS 3D Elevation Program lidar and USDA NAIP (public domain), and the crop cover's own inputs
(farm's: CSB and CDL, public domain, and Sentinel-2, Copernicus). Nothing here reads a tree inventory."""
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
from pyproj import CRS, Transformer
from rasterio import features as rfeatures
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject, transform_bounds

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
if REPO not in sys.path:
    sys.path.append(REPO)                      # basemap.ground.manifest and ingest.manifest: standard library
import cloud  # noqa: E402
import shrubs as S  # noqa: E402
from basemap.ground import manifest as M  # noqa: E402

MODEL = os.path.join(os.path.dirname(HERE), "model", "shrub_model.json")
OUTLINE_CELLS = 10              # the area's outline is traced on 5 m blocks
PHOTO_MIN_COVER = 0.95          # the share of the area's lidar cells the photo must give an NDVI on
# This plugin's sources (plugin.json) for the lidar and the photo, with their licence classes (manifest.LICENCES).
LIDAR_SOURCE, PHOTO_SOURCE = "trees/usgs_3dep_lidar", "trees/usda_naip"
SOURCE_LICENCE = {LIDAR_SOURCE: "public-domain", PHOTO_SOURCE: "public-domain"}
# Datums read onto each other with a null shift: NAD83's realisations and WGS 84, a metre or so apart here.
NULL_SHIFT_DATUMS = ("North American Datum 1983", "NAD83", "World Geodetic System 1984")


# --- inputs: licence and provenance -----------------------------------------------------------------------------

def file_record(path, sha=True):
    """A file as build.json records it: its name, size and (sha) sha256."""
    out = {"file": os.path.basename(path), "bytes": os.path.getsize(path)}
    if sha:
        out["sha256"] = M.sha256_of(path)
    return out


def points_record(path):
    """A point source: a LAS/LAZ tile by name and size (they are big, and USGS's names are stable), an EPT by its
    folder's name and its ept.json's sha256."""
    if cloud.source_kind(path) == "ept":
        return dict(file_record(path), file=os.path.join(os.path.basename(os.path.dirname(os.path.abspath(path))),
                                                         os.path.basename(path)))
    return file_record(path, sha=False)


def source_input(role, source, registry):
    """An input from one of this plugin's sources: its licence class, and republish and credit as plugin.json has them
    (the owner's decision for that source)."""
    e = registry.get(source)
    if e is None:
        raise SystemExit(f"{source} isn't a source in plugin.json")
    return {"name": role, "source": source, "licence": SOURCE_LICENCE[source], "republish": e["republish"],
            "credit": [e["credit"]]}


def crop_input(path, licence=None, republish=None, credit=None, registry=None):
    """The crop input's licence and provenance. An export (farm's crop_cover.tif): its manifest beside it (C5), read
    and checked with the ground's reader (every file's size and sha256, the licence rules, its sources against
    plugin.json); the layer that is this file gives licence, republish and credit, and build.json records the export's
    plugin and build and the file's sha256. A file without a manifest (CSB's GeoPackage, say) needs them given."""
    folder = os.path.dirname(os.path.abspath(path))
    given = (licence, republish, credit)
    if os.path.exists(os.path.join(folder, M.FILE)):
        if any(given):
            raise SystemExit("--crop: its export's manifest states its licence; leave out --crop-licence, "
                             "--crop-republish and --crop-credit")
        try:
            man = M.read(folder, registry=registry)
        except M.ManifestError as err:
            raise SystemExit(f"--crop: {err}") from None
        lay = next((x for x in man.layers if x["file"] == os.path.basename(path)), None)
        if lay is None:
            raise SystemExit(f"--crop: {os.path.basename(path)} isn't a layer of {man.plugin}'s export {man.build}")
        ins = man.inputs
        return {"name": "crop", "plugin": man.plugin, "build": man.build, "layer": lay.name, "file": lay["file"],
                "bytes": lay["bytes"], "sha256": lay["sha256"], "licence": lay["licence"],
                "republish": lay["republish"], "credit": list(lay["credit"]),
                "inputs": [{k: ins[n][k] for k in ("name", "version", "sha256") if k in ins[n]} for n in lay["inputs"]]}
    if not all(given):
        raise SystemExit(f"--crop: {os.path.basename(path)} has no export manifest beside it: give its --crop-licence, "
                         "--crop-republish and --crop-credit")
    if licence not in M.LICENCES:
        raise SystemExit(f"--crop-licence {licence!r} isn't one of {', '.join(M.LICENCES)}")
    if M.LICENCES[licence].per_source:
        raise SystemExit(f"--crop-licence {licence}: what may be published rests on a plugin source's decision; "
                         "export the crops with a manifest that names it")
    if republish not in M.REPUBLISH:
        raise SystemExit(f"--crop-republish must be one of {', '.join(M.REPUBLISH)}")
    if M.rank(republish) < M.rank(M.LICENCES[licence].loosest):
        raise SystemExit(f"--crop-republish {republish} is looser than {licence} allows")
    credits = [c.strip() for c in credit.split(";") if c.strip()]
    if not credits:
        raise SystemExit("--crop-credit is empty")
    return dict(file_record(path), name="crop", licence=licence, republish=republish, credit=credits, given=True)


def licence_of(inputs):
    """(licence, republish, credit) of what the build writes, by the export contract's rules (C3): republish the
    strictest of its inputs'; the licence the share-alike one when there is one, otherwise one of the strictest (one
    with terms ahead of public domain, which has none); every input's credit, once each, in order."""
    lics = [i["licence"] for i in inputs]
    share = [x for x in lics if M.LICENCES[x].share_alike]
    if share:
        lic = share[0]
    else:
        top = max(M.strictness(x) for x in lics)
        tied = [x for x in lics if M.strictness(x) == top]
        lic = next((x for x in tied if x != "public-domain"), tied[0])
    rep = M.strictest(i["republish"] for i in inputs)
    return lic, rep, list(dict.fromkeys(c for i in inputs for c in i["credit"]))


def require_republish(inputs):
    """The shrubs are published (the trees plugin is public): stop when an input may not be republished."""
    held = [f"{i['name']} ({i['republish']})" for i in inputs if i["republish"] != "yes"]
    if held:
        raise SystemExit(f"the shrubs are published, but {', '.join(held)} may not be republished: that needs the "
                         "owner's decision first")


# --- frames ------------------------------------------------------------------------------------------------------

def datum_of(crs):
    g = CRS.from_user_input(crs).geodetic_crs
    return g.datum.name if g is not None and g.datum is not None else "an unknown datum"


def check_datum(src_crs, grid_crs, what):
    """Stop unless src_crs can be read onto the grid without a datum grid: the grid's own datum, or both on NAD83's
    realisations or WGS 84 (a metre or so apart here). NAD27, say, is about 100 m off, and offline PROJ would quietly
    fall back to a null shift."""
    a, b = datum_of(src_crs), datum_of(grid_crs)
    if a == b or (a.startswith(NULL_SHIFT_DATUMS) and b.startswith(NULL_SHIFT_DATUMS)):
        return
    raise SystemExit(f"{what} is on {a}, the lidar on {b}: only NAD83's realisations and WGS 84 are read onto each "
                     "other here (with a null datum shift); reproject it onto NAD83 or WGS 84 first")


def same_frame(src_crs, grid_crs):
    """True when src_crs is the grid's UTM zone, on the grid's datum or another check_datum allows: it is then read as
    if it were on the grid's (a null datum shift). NAD83's realisations (NAIP's NAD83, the lidar's NAD83(2011)) and
    WGS 84 differ by a metre or so here: less than the photo shift measured on each area, and far less than a crop
    field's edge. Doing it properly takes NOAA's grids, which PROJ would fetch from the network, and a build fetches
    nothing. A source in the zone on another datum stops the build."""
    a, b = CRS.from_user_input(src_crs), CRS.from_user_input(grid_crs)
    if a.utm_zone is None or a.utm_zone != b.utm_zone:
        return False
    check_datum(a, b, a.name)
    return True


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


def covers(ds, src_crs, crs, rect):
    """Whether the raster ds, read in src_crs (crs itself when same_frame), covers rect (x0, y0, x1, y1 in crs)."""
    x0, y0, x1, y1 = rect
    if src_crs is not crs:
        x0, y0, x1, y1 = transform_bounds(crs, src_crs, x0, y0, x1, y1, densify_pts=21)
    b, tol = ds.bounds, 1e-6
    return b.left <= x0 + tol and b.bottom <= y0 + tol and b.right >= x1 - tol and b.top >= y1 - tol


def read_onto(path, bands, tf, crs, shape, resampling, pad=0, whole=False):
    """Bands of a raster onto the grid (grown by pad cells each side), float32, 0 where it has nothing (or a value that
    isn't finite). whole: the raster must cover the whole grid (pad left out)."""
    out = np.zeros((len(bands), shape[0] + 2 * pad, shape[1] + 2 * pad), np.float32)
    dst = tf @ Affine.translation(-pad, -pad)
    with rasterio.open(path) as ds:
        if max(bands) > ds.count:
            raise SystemExit(f"{path}: has {ds.count} bands, needs {max(bands)}")
        check_datum(ds.crs, crs, path)
        src_crs = crs if same_frame(ds.crs, crs) else ds.crs
        grid_rect = (tf.c, tf.f - shape[0] * S.PX, tf.c + shape[1] * S.PX, tf.f)
        if whole and not covers(ds, src_crs, crs, grid_rect):
            raise SystemExit(f"{path} doesn't cover the whole area")
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
            # No destination nodata: with one, GDAL nudges a real 0 to the next float up (1e-45), so it isn't nodata.
            reproject(src, out[i], src_transform=stf, src_crs=src_crs, src_nodata=ds.nodata, dst_transform=dst,
                      dst_crs=crs, dst_nodata=None, resampling=resampling)
    out[~np.isfinite(out)] = 0             # a reprojection that failed (PROJ without its grids) gives inf
    return out


def ndvi_of(red, nir):
    s = red + nir
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(s > 0, (nir - red) / np.maximum(s, 1e-6), np.nan).astype(np.float32)


SHIFT_REACH = 12          # cells (6 m) each way
SHIFT_MIN_TREE_CELLS = 4000
SHIFT_MIN_IOU = 0.1
# A shift must earn its distance: the IoU it gains over no shift must be at least this much for each metre it moves the
# photo, or there is no shift. On the ten boxes (Oct 11) the shifts that agree with the spike's gained 0.003 (0.5 m,
# downtown) to 0.023 (2 m, Barber Pool); South Meridian's 2 m gained 0.005 at an IoU of 0.1, noise, and didn't agree.
SHIFT_GAIN_PER_M = 0.004


def shift_needs(k):
    """The IoU a shift of k (dx, dy cells) must gain over no shift."""
    return SHIFT_GAIN_PER_M * math.hypot(*k) * S.PX


def best_shift(scores):
    """The shift of scores ({(dx, dy) cells: IoU}) with the best IoU; ties go to the shorter."""
    return max(scores, key=lambda k: (scores[k], -math.hypot(*k)))


def choose_shift(scores):
    """The best shift of scores ((0, 0) among them) when it gains over no shift what its distance needs (shift_needs);
    otherwise none, (0, 0). A shift that is taken is taken whole, not shortened."""
    best = best_shift(scores)
    return best if scores[best] - scores[(0, 0)] >= shift_needs(best) else (0, 0)


def measure_shift(ndvi_pad, h, bld, bad):
    """The photo's shift onto the lidar, in whole cells, as the spike measured it: the offset (up to 6 m each way)
    where the photo's green best overlaps the lidar's trees (2.4 m and up, not buildings), by IoU. None of it where there
    are too few trees or the overlap is weak (deserts), or where the best shift doesn't gain enough over none for its
    distance (choose_shift): no shift. Returns ((dx, dy), detail)."""
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
    detail = {"tree_cells": nt, "iou_at_0": round(i0, 4)}
    if nt < SHIFT_MIN_TREE_CELLS:
        detail["why"] = "too few trees to measure it: no shift"
        return (0, 0), detail
    scores = {(dx, dy): iou(dx, dy) for dx in range(-P, P + 1, 2) for dy in range(-P, P + 1, 2)}
    bx, by = best_shift(scores)
    for dx in range(max(-P, bx - 1), min(P, bx + 1) + 1):       # refine around it by single cells
        for dy in range(max(-P, by - 1), min(P, by + 1) + 1):
            if (dx, dy) not in scores:
                scores[(dx, dy)] = iou(dx, dy)
    top = best_shift(scores)
    detail.update(iou_best=round(scores[top], 4), best_at_m=[top[0] * S.PX, -top[1] * S.PX],
                  gain=round(scores[top] - i0, 4), needed=round(shift_needs(top), 4))
    if scores[top] < SHIFT_MIN_IOU:
        detail["why"] = "the photo's green barely meets the trees anywhere: no shift"
        return (0, 0), detail
    if choose_shift(scores) == (0, 0) and top != (0, 0):
        detail["why"] = "the best shift doesn't gain enough over none for its distance: no shift"
        return (0, 0), detail
    detail["why"] = "the best overlap of the photo's green and the lidar's trees"
    return top, detail


def photo_ndvi(path, tf, crs, shape, shift, h, bld, bad):
    """NDVI on the grid from the photo's red (band 1) and near-infrared (band 4), averaged onto the 0.5 m cells and
    moved onto the lidar. shift: where the photo's features sit against the lidar's, (east, north) in metres, rounded
    to whole cells, or "auto" (measure_shift). Grid cell (r, c) takes the photo at the grid's (r + dy, c + dx), so
    east = dx x 0.5 m and north = -dy x 0.5 m, as the spike recorded its shifts. Returns (ndvi, (east_m, north_m),
    detail); NaN where the photo has nothing."""
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


def photo_cover(ndvi, bad):
    """The share of the lidar's cells the photo gives an NDVI on."""
    ok = ~bad
    return float(np.isfinite(ndvi[ok]).mean()) if ok.any() else 0.0


def crop_mask(path, where, tf, crs, shape):
    """Crop fields on the grid: a raster (band 1 > 0), which must cover the whole grid, or a vector's polygons
    (filtered by where). A vector is moved onto the grid through longitude and latitude on each one's own datum (a
    null datum shift), so it must be on a datum check_datum allows."""
    if path.lower().endswith((".tif", ".tiff")):
        out = read_onto(path, (1,), tf, crs, shape, Resampling.nearest, whole=True)[0]
        return out > 0, {"crop_raster": os.path.basename(path)}
    from osgeo import ogr, osr
    ogr.UseExceptions()
    osr.UseExceptions()
    ds = ogr.Open(path)
    lyr = ds.GetLayer(0)
    if where:
        lyr.SetAttributeFilter(where)
    src = lyr.GetSpatialRef()
    if src is None:
        raise SystemExit(f"{path}: its layer has no CRS")
    check_datum(src.ExportToWkt(), crs, path)
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
    ap.add_argument("--crop", help="crops: farm's crop_cover.tif (band 1 > 0), or a vector of crop fields")
    ap.add_argument("--crop-where", help="OGR SQL filter on the crop vector's features")
    ap.add_argument("--crop-licence", help="a crop file without an export manifest: its licence class "
                                           "(basemap/ground/manifest.py's LICENCES, e.g. public-domain)")
    ap.add_argument("--crop-republish", help="... and its republish (yes, aggregates, internal, no)")
    ap.add_argument("--crop-credit", help="... and its credit (several separated by ';')")
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

    # The inputs' licences first: a build that couldn't be published stops before any work. Then what they are.
    if not a.crop and (a.crop_licence or a.crop_republish or a.crop_credit):
        ap.error("--crop-licence, --crop-republish and --crop-credit go with --crop")
    registry = M.plugin_sources()
    lidar_in, photo_in = source_input("lidar", LIDAR_SOURCE, registry), source_input("photo", PHOTO_SOURCE, registry)
    inputs = [lidar_in, photo_in]
    if a.crop:
        inputs.append(crop_input(a.crop, a.crop_licence, a.crop_republish, a.crop_credit, registry))
    require_republish(inputs)
    licence, republish, credit = licence_of(inputs)
    log(f"inputs: licence {licence}, republish {republish}; credit {'; '.join(credit)}")
    lidar_in.update(survey=a.lidar, date=a.lidar_date, points_srs=a.points_srs,
                    files={"dsm": file_record(a.dsm), "dtm": file_record(a.dtm),
                           "mask": file_record(a.mask) if a.mask else None},
                    points=[points_record(p) for p in a.points])
    photo_in.update(title=a.photo_name, **file_record(a.photo))

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
    crop, crop_info = (np.zeros(shape, bool), {}) if not a.crop else crop_mask(a.crop, a.crop_where, tf, crs, shape)

    ndvi, shift_m, shift_detail = photo_ndvi(a.photo, tf, crs, shape, shift, h, bld, bad)
    cover = photo_cover(ndvi, bad)
    if cover < PHOTO_MIN_COVER:
        raise SystemExit(f"the photo gives an NDVI on {cover:.1%} of the area's lidar cells, under "
                         f"{PHOTO_MIN_COVER:.0%}: is it this area's, and does its CRS reproject here offline?")
    log(f"photo: an NDVI on {cover:.2%} of the lidar's cells; its features sit {shift_m[0]:+.1f} m east, "
        f"{shift_m[1]:+.1f} m north of the lidar's, moved back ({shift_detail['why']})")
    cut, cut_detail = S.ndvi_cut(ndvi, h, bld, bad)
    alive = np.nan_to_num(ndvi, nan=-1.0) >= cut
    log(f"photo: green cut NDVI {cut:.3f} ({cut_detail['from']})")

    grid = cloud.Grid(tf.c, tf.f, S.PX, shape[0], shape[1])
    os.makedirs(a.out, exist_ok=True)
    n_ag, scat, cloud_stats = cloud.cues(a.points, grid, crs.to_string(), dtm, ~bad, os.path.join(a.out, "work"),
                                         chunk_m=a.chunk_m, threads=a.threads, in_srs=a.points_srs, log=log)
    shrub, band = S.shrub_cells(h, bld, bad, alive, n_ag, scat)
    log(f"rule: {int(shrub.sum()):,} shrub cells of {int(band.sum()):,} in the band")

    found, why, dropped = S.split(h, shrub, alive, treeh, model, crop=crop if a.crop else None)
    drop_crop = why == S.WHY["crop"]
    field, blocks_first, blocks = S.field_rule(h, bld, alive)
    m = shrub & ~drop_crop
    crop_check = {
        "crop_input": crop_info or None,
        "crop_cells": int(crop.sum()),
        "pieces_called_crop": dropped["crop"],
        "shrub_cells_called_crop": int(drop_crop.sum()),
        "shrub_cells_in_crop_left": int((m & crop).sum()),     # in pieces mostly outside the crops
        "rule_field_blocks": blocks_first,
        "rule_field_blocks_joined": blocks,
        "rule_field_cells": int(field.sum()),
        "rule_field_cells_in_crop": int((field & crop).sum()),
        "rule_shrub_cells": int((shrub & field).sum()),
        "rule_shrub_cells_left_by_crop": int((m & field).sum()),
    }
    log(f"crops: {dropped['crop']:,} pieces ({int(drop_crop.sum()):,} cells) in crop fields; the field rule's "
        f"{blocks} blocks, {crop_check['rule_shrub_cells_left_by_crop']:,} of their shrub cells left as shrubs")
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
              "points_srs": a.points_srs, "chunk_m": a.chunk_m, "photo": a.photo_name,
              "photo_file": os.path.basename(a.photo), "photo_cover": round(cover, 4),
              "photo_shift_m": list(shift_m), "photo_shift_detail": shift_detail, "ndvi_cut": round(cut, 3),
              "ndvi_cut_detail": cut_detail,
              "crop": os.path.basename(a.crop) if a.crop else None, "crop_where": a.crop_where,
              "skip_rects": [list(r) for r in a.skip_rect], "window": a.window, "grid_crs": crs.to_string(),
              "model": spec["source"][:200], "width": spec["width"],
              "rule": {"band_m": list(S.BAND_M), "plant_returns": S.PLANT_RETURNS, "plant_scatter": S.PLANT_SCATTER,
                       "ground_h_m": S.GROUND_H, "knn": cloud.KNN, "edge_m": S.EDGE_CELLS * S.PX,
                       "crop_piece_share": S.CROP_PIECE_SHARE, "shift_gain_per_m": SHIFT_GAIN_PER_M,
                       "photo_min_cover": PHOTO_MIN_COVER}}
    build = {"build_id": os.path.basename(os.path.normpath(a.out)), "area": a.area, "started_at": started.isoformat(),
             "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "geom": geom,
             "license": licence, "republish": republish, "credit": "; ".join(credit),
             "inputs": {i["name"]: i for i in inputs}, "params": params, "counts": counts}
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
