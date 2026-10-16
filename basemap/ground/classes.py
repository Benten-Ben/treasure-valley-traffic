"""The land-cover classes in the ten boxes (G1a): the ground's own product `ground_classes`, one GeoTIFF per box on its
exact 0.5 m window, from public inputs only. Runs in the worker image (GDAL, PDAL, NumPy, SciPy, scikit-image), as a
heavy job (about 4 GB; a few minutes a box):

    python basemap/ground/classes.py build --recipe /in/recipe.json [--box f ...] [--archive $TVT_ARCHIVE]

The rules are classrules.py's (the land-cover spike's exp26, exp27, exp28b and exp31, and G1a's mapped tracks). This
module reads each box's inputs onto the lidar's 0.5 m grid, as the spike did, runs the rules, moves the classes from
the lidar's frame into the photo's (the shrub build's photo shift; OpenStreetMap and the map are traced on the photo),
and writes them through the export contract (manifest.py) with RAW inputs only (inputs.py).

**The recipe** (JSON) names every input, because they're files on the server, not exports:

    {"osm": "<S1's cut, valley.osm.pbf>",                 # with valley.json beside it (its MD5)
     "july": "<folder with ndvi_median.tif, ndvi_max.tif, ndvi_min.tif, clear_count.tif>",   # the 10 m grid
     "norm": "<the same-day normalisation's fits.json>",
     "boxes": {"f": {"lidar": "<folder with dsm.tif and dtm.tif, the box's 0.5 m lidar products>",
                     "mask": "<the box's building mask, .npy on the lidar grid>",
                     "shrubs": "<the box's shrub build (plugins/trees/build/build_shrubs.py), its why.tif and cue cache>",
                     "points": ["<LAS/LAZ tiles, or an EPT's ept.json>", ...], "points_srs": null,
                     "photo": "<the box's NAIP crop: red, green, blue, near-infrared>",
                     "curve": "naip2025:2025-05-25",       # or "naip2023": the photo's NDVI curve in fits.json
                     "lidar_name": "USGS 3DEP QL1 lidar (ID_SouthernGaps_D23)", "lidar_date": "2023-10-27"}, ...}}

Per box:
- **lidar**: heights above the bare earth (DSM minus DTM), cells without lidar, the building mask (Overture's
  footprints aligned to the lidar, zeroed with a buffer: the trees build's), its 1 m ring, the 3 x 3 height spread;
- **the shrub build** (docs/19 §19.8, same grid): why.tif (1 shrub, 3 skirt and 4 gap are tree, 5 crop) and its cue
  cache (returns above the ground and their scatter: the lidar's plant cue), and the photo shift it measured;
- **the photo**: red and near-infrared averaged onto the grid and moved by the shift, for the NDVI, which goes through
  its flight day's curve onto Sentinel-2's scale; red, green and blue for its brightness (the track rule);
- **July 2025** from Sentinel-2: each cell takes its 10 m cell's median, maximum, minimum and clear views;
- **ground brightness** from the points: each ground point's intensity over its flight line's median, averaged per
  cell (exp28's "bright"; dark ground is asphalt);
- **OpenStreetMap**: roads (maskrules.road's major roads, streets and service ways) within 2 m of their line, which the
  July rule never greens, and tracks (highway=track), for the track rule; moved onto the lidar by the shift.

Writes $TVT_ARCHIVE/ground_classes/export/<build>/: <box>.tif (bands `class` and `floor`, uint8, 0 no data; values in
classrules.CLASSES), manifest.json, and report.json (each box's inputs, shift, July-rule numbers and class shares).
A build of some boxes only is partial (<build>-part): readers skip it (manifest.is_partial), and the command line
refuses to put one in $TVT_ARCHIVE.
"""

import argparse
import fcntl
import hashlib
import json
import math
import os
import shutil
import signal
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np  # noqa: E402
from osgeo import gdal, ogr, osr  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

from basemap.ground import classrules as CR  # noqa: E402
from basemap.ground import grid, inputs, maskrules as MR  # noqa: E402
from basemap.ground import manifest as M  # noqa: E402
from basemap.ground import rasterize as R  # noqa: E402

gdal.UseExceptions()
ogr.UseExceptions()

PRODUCT = "ground_classes"
STAGING = "staging"
LOCK = ".build.lock"
KEEP = 2
OSMCONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osmconf.ini")
ROAD_KINDS = ("major", "street", "service")       # the July rule never greens these (exp28's "surely paved" roads)
ROAD_REACH_M = 2.0                                # within this of the line
NOISE_CLASSES = (7, 18)
WHY_TREE = (3, 4)                                 # the shrub build's why.tif: 3 skirt, 4 gap (of a tree's crown)
WHY_SHRUB, WHY_CROP = 1, 5
S2_SCALE = 10000.0                                # the July rasters: NDVI x 10000, int16
EPT_PART_M = 400.0
OSM_MARGIN_M = 30.0


class ClassError(ValueError):
    pass


# ---- reading -------------------------------------------------------------------------------------------------------

class LidarGrid:
    """The box's lidar grid: north-west corner, 0.5 m cells, rows x cols, and its CRS (the products')."""

    def __init__(self, x0, y1, rows, cols, wkt):
        self.x0, self.y1, self.rows, self.cols, self.wkt = float(x0), float(y1), int(rows), int(cols), wkt

    @property
    def shape(self):
        return self.rows, self.cols

    @property
    def transform(self):
        return (self.x0, CR.PX, 0.0, self.y1, 0.0, -CR.PX)

    @property
    def bounds(self):
        return self.x0, self.y1 - self.rows * CR.PX, self.x0 + self.cols * CR.PX, self.y1

    def shifted(self, east, north):
        """The same cells, moved by (east, north) metres."""
        return LidarGrid(self.x0 + east, self.y1 + north, self.rows, self.cols, self.wkt)


def read_lidar(folder):
    """(h, bad, LidarGrid) from the box's dsm.tif and dtm.tif."""
    out = []
    for name in ("dsm", "dtm"):
        ds = gdal.Open(os.path.join(folder, f"{name}.tif"))
        b = ds.GetRasterBand(1)
        a = b.ReadAsArray().astype(np.float32)
        nod = b.GetNoDataValue()
        bad = ~np.isfinite(a)
        if nod is not None:
            bad |= a == nod
        out.append((a, bad, ds.GetGeoTransform(), ds.RasterYSize, ds.RasterXSize, ds.GetProjection()))
    (dsm, bad1, gt, rows, cols, wkt), (dtm, bad2, gt2, rows2, cols2, _) = out
    if gt != gt2 or (rows, cols) != (rows2, cols2):
        raise ClassError(f"{folder}: the DSM and DTM aren't on one grid")
    if abs(gt[1] - CR.PX) > 1e-9 or abs(gt[5] + CR.PX) > 1e-9 or gt[2] or gt[4]:
        raise ClassError(f"{folder}: the lidar grid must be {CR.PX} m, north up (got {gt})")
    bad = bad1 | bad2
    h = np.where(bad, 0, np.clip(dsm - dtm, 0, None)).astype(np.float32)
    return h, bad, LidarGrid(gt[0], gt[3], rows, cols, wkt)


def box_offset(box, g):
    """(row, col) of the lidar grid's corner in the box's window. The lidar grid must be on the 0.5 m class grid and
    overlap the box: the spike's rasters are the box's window exactly (spec.json), except box h's, made later from
    another survey, which sits half a metre inside it on each side."""
    w = box.window()
    c, r = (g.x0 - w.west) / CR.PX, (w.north - g.y1) / CR.PX
    if abs(c - round(c)) > 1e-6 or abs(r - round(r)) > 1e-6:
        raise ClassError(f"box {box.id}: the lidar grid (E {g.x0:g} N {g.y1:g}) isn't on the 0.5 m class grid")
    c, r = int(round(c)), int(round(r))
    if c >= w.width or r >= w.height or c + g.cols <= 0 or r + g.rows <= 0:
        raise ClassError(f"box {box.id}: the lidar grid doesn't reach the box's window")
    if not grid.same_coordinates(osr.SpatialReference(wkt=g.wkt).GetAuthorityCode(None) or 0):
        raise ClassError(f"box {box.id}: the lidar's CRS isn't one the grid reads as its own (grid.NULL_SHIFT_EPSG)")
    return r, c


def check_box_grid(box, g):
    """The lidar grid must be the box's window exactly (offset 0, same size)."""
    if box_offset(box, g) != (0, 0) or g.shape != box.window().shape:
        raise ClassError(f"box {box.id}: the lidar grid isn't the box's window")


def embed(a, box, offset):
    """A lidar-grid array placed in the box's window (0, no data, where the lidar has nothing)."""
    w = box.window()
    r, c = offset
    if (r, c) == (0, 0) and a.shape == w.shape:
        return a
    out = np.zeros(w.shape, a.dtype)
    rows, cols = a.shape
    r0, c0 = max(r, 0), max(c, 0)
    r1, c1 = min(r + rows, w.height), min(c + cols, w.width)
    out[r0:r1, c0:c1] = a[r0 - r:r1 - r, c0 - c:c1 - c]
    return out


def preflight(recipe, boxes):
    """Every box's inputs, checked before any heavy work: the files are there, the lidar grid is on the box's, the
    mask and the shrub build's cue cache are on the lidar grid, the curve exists. Raises ClassError."""
    with open(recipe["norm"], encoding="utf-8") as f:
        norm = json.load(f)
    for name in ("ndvi_median", "ndvi_max", "ndvi_min", "clear_count"):
        if not os.path.isfile(os.path.join(recipe["july"], f"{name}.tif")):
            raise ClassError(f"no {name}.tif in {recipe['july']}")
    if not os.path.isfile(recipe["osm"]):
        raise ClassError(f"no OSM cut at {recipe['osm']}")
    for b in boxes:
        spec = recipe["boxes"][b.id]
        ds = gdal.Open(os.path.join(spec["lidar"], "dsm.tif"))
        gt = ds.GetGeoTransform()
        g = LidarGrid(gt[0], gt[3], ds.RasterYSize, ds.RasterXSize, ds.GetProjection())
        box_offset(b, g)
        shape = np.load(spec["mask"], mmap_mode="r").shape
        if shape != g.shape:
            raise ClassError(f"box {b.id}: the building mask is {shape}, the lidar {g.shape}")
        with open(os.path.join(spec["shrubs"], "work", "cues.json"), encoding="utf-8") as f:
            key = json.load(f)["key"]
        if [float(v) for v in key["grid"][:3]] != [g.x0, g.y1, CR.PX] or key["grid"][3:] != [g.rows, g.cols]:
            raise ClassError(f"box {b.id}: the shrub build's cue cache is for another grid")
        for p in [spec["photo"], os.path.join(spec["shrubs"], "why.tif")] + list(spec["points"]):
            if not os.path.isfile(p):
                raise ClassError(f"box {b.id}: no file {p}")
        curve_of(norm, spec["curve"])


def read_tif_on(path, g, band=1):
    ds = gdal.Open(path)
    if ds.RasterXSize != g.cols or ds.RasterYSize != g.rows or any(
            abs(a - b) > 1e-6 for a, b in zip(ds.GetGeoTransform(), g.transform)):
        raise ClassError(f"{path} isn't on the box's lidar grid")
    return ds.GetRasterBand(band).ReadAsArray()


def read_shrubs(folder, g):
    """The shrub build's cells (kept, treecue, field), its cue cache (n_ag, scat) and photo shift (east, north)."""
    why = read_tif_on(os.path.join(folder, "why.tif"), g)
    with open(os.path.join(folder, "build.json"), encoding="utf-8") as f:
        build = json.load(f)
    params = build["params"] if isinstance(build.get("params"), dict) else {}
    shift = tuple(float(v) for v in params.get("photo_shift_m", (0.0, 0.0)))
    work = os.path.join(folder, "work")
    with open(os.path.join(work, "cues.json"), encoding="utf-8") as f:
        key = json.load(f)["key"]
    x0, y1, px, rows, cols = key["grid"]
    if (float(x0), float(y1), float(px), int(rows), int(cols)) != (g.x0, g.y1, CR.PX, g.rows, g.cols):
        raise ClassError(f"{folder}: its cue cache is for another grid ({key['grid']})")
    n = max(1, int(round(float(key["chunk_m"]) / CR.PX)))
    n_ag = np.zeros(g.shape, np.uint16)
    scat = np.full(g.shape, np.nan, np.float32)
    for r0 in range(0, g.rows, n):
        for c0 in range(0, g.cols, n):
            path = os.path.join(work, "chunks", f"{r0}_{c0}.npz")
            if not os.path.exists(path):
                raise ClassError(f"{folder}: its cue cache lacks chunk {r0}_{c0} (rerun the shrub build)")
            with np.load(path) as z:
                n_ag[r0:r0 + n, c0:c0 + n] = z["n_ag"]
                scat[r0:r0 + n, c0:c0 + n] = z["scat"]
    return {"kept": why == WHY_SHRUB, "treecue": np.isin(why, WHY_TREE), "field": why == WHY_CROP,
            "n_ag": n_ag, "scat": scat, "shift": shift, "build": build.get("build_id"),
            "crop": (build.get("inputs") or {}).get("crop") if isinstance(build.get("inputs"), dict) else None}


def warp_onto(path, g, bands, resample="average"):
    """Bands of a raster onto g (any frame): float32 (bands, rows, cols), NaN where it has nothing. The datum policy:
    NAD83 is read as WGS 84 (rasterize.warp_srs)."""
    src = gdal.Open(path)
    vrt = gdal.Translate("", src, format="VRT", bandList=list(bands))
    out = gdal.Warp("", vrt, format="MEM", srcSRS=R.warp_srs(src.GetProjection()), dstSRS=R.warp_srs(g.wkt),
                    outputBounds=g.bounds, width=g.cols, height=g.rows, resampleAlg=resample, dstAlpha=True,
                    outputType=gdal.GDT_Float32, multithread=False)
    arr = out.ReadAsArray().astype(np.float32).reshape(len(bands) + 1, g.rows, g.cols)
    valid = arr[-1] > 0
    data = arr[:-1]
    data[:, ~valid] = np.nan
    return data


def read_photo(path, g, shift):
    """(NDVI, brightness) on g from the photo moved onto the lidar: grid cell (r, c) takes the photo at the grid's
    (r + dy, c + dx), east = dx x 0.5 m, north = -dy x 0.5 m (build_shrubs.photo_ndvi's convention)."""
    east, north = shift
    red, green, blue, nir = warp_onto(path, g.shifted(east, north), (1, 2, 3, 4))
    s = red + nir
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = np.where(s > 0, (nir - red) / np.maximum(s, 1e-6), np.nan).astype(np.float32)
    lum = ((red + green + blue) / 3.0).astype(np.float32)
    return ndvi, lum


def curve_of(norm, name):
    """The photo's NDVI curve in the same-day normalisation's fits.json: "naip2025:<flight day>" or "naip2023" (the
    pooled curve of boxes h, i and j)."""
    if name == "naip2023":
        return norm["naip2023_boxes_h_i_j"]["pooled_curve"]
    kind, _, day = name.partition(":")
    if kind != "naip2025" or day not in norm["naip2025"]["days"]:
        raise ClassError(f"no curve {name!r} in the normalisation (naip2025:<day> or naip2023)")
    return norm["naip2025"]["days"][day]["curve"]


def read_july(folder, g):
    """Each cell's 10 m Sentinel-2 cell: {med, max, min, n} per 0.5 m cell, and the 10 m cell index (local to the
    box). Cells are placed by the lidar grid's coordinates (the spike's way; under a centimetre from 32611 here)."""
    xs = g.x0 + (np.arange(g.cols) + 0.5) * CR.PX
    ys = g.y1 - (np.arange(g.rows) + 0.5) * CR.PX
    ci = np.floor((xs - grid.ORIGIN_X) / grid.BASE_RES).astype(np.int64)
    ri = np.floor((grid.ORIGIN_Y - ys) / grid.BASE_RES).astype(np.int64)
    c0, r0 = int(ci.min()), int(ri.min())
    w, h = int(ci.max()) - c0 + 1, int(ri.max()) - r0 + 1
    lc, lr = ci - c0, ri - r0
    out = {}
    for key, name in (("med", "ndvi_median"), ("max", "ndvi_max"), ("min", "ndvi_min"), ("n", "clear_count")):
        ds = gdal.Open(os.path.join(folder, f"{name}.tif"))
        gt = ds.GetGeoTransform()
        if not grid.aligned(gt, grid.BASE_RES) or (gt[0], gt[3]) != (grid.ORIGIN_X, grid.ORIGIN_Y):
            raise ClassError(f"{name}.tif isn't on the ground's 10 m grid")
        b = ds.GetRasterBand(1)
        a = b.ReadAsArray(c0, r0, w, h)
        if key == "n":
            out[key] = a[lr[:, None], lc[None, :]].astype(np.uint8)
        else:
            v = a.astype(np.float32)
            nod = b.GetNoDataValue()
            if nod is not None:
                v[a == nod] = np.nan
            out[key] = (v / S2_SCALE)[lr[:, None], lc[None, :]]
    cell = (lr[:, None] * w + lc[None, :]).astype(np.int64)
    return out, cell


def _keep(arr):
    names = arr.dtype.names
    keep = ~np.isin(arr["Classification"], NOISE_CLASSES)
    if "Withheld" in names:
        keep &= arr["Withheld"] == 0
    elif "ClassFlags" in names:
        keep &= (arr["ClassFlags"] & 4) == 0
    return keep


def _pdal_bounds(rect):
    x0, y0, x1, y1 = rect
    return f"([{x0}, {x1}], [{y0}, {y1}])"


def read_points(sources, g, in_srs=None, batch=2_000_000):
    """Yield arrays of the box's points from LAS/LAZ tiles or an EPT, in the lidar grid's CRS. The same reading as the
    shrub build's (plugins/trees/build/cloud.py): PDAL's reprojection to the grid's CRS, an EPT read in parts."""
    import pdal
    out_srs = g.wkt
    rect = g.bounds
    reproject = {"type": "filters.reprojection", "out_srs": out_srs}
    if in_srs:
        reproject["in_srs"] = in_srs
    crop = {"type": "filters.crop", "bounds": _pdal_bounds(rect)}
    for path in sources:
        low = path.lower()
        if low.endswith((".las", ".laz")):
            stages = [{"type": "readers.las", "filename": path}]
            if in_srs or not _same_frame(path, out_srs):
                stages.append(reproject)
            stages.append(crop)
            for arr in pdal.Pipeline(json.dumps(stages)).iterator(chunk_size=batch):
                if len(arr):
                    yield arr
        elif low.endswith("ept.json"):
            src = osr.SpatialReference()
            if in_srs:
                src.SetFromUserInput(in_srs)
            else:
                src.ImportFromWkt(_ept_wkt(path))
            ct = osr.CoordinateTransformation(R.srs_of(osr.SpatialReference(wkt=out_srs)), R.srs_of(src))
            x0, y0, x1, y1 = rect
            nx, ny = max(1, math.ceil((x1 - x0) / EPT_PART_M)), max(1, math.ceil((y1 - y0) / EPT_PART_M))
            xs, ys = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
            for i in range(nx):
                for j in range(ny):
                    part = (float(xs[i]), float(ys[j]), float(xs[i + 1]), float(ys[j + 1]))
                    pts = [ct.TransformPoint(px, py)[:2] for px in (part[0], part[2]) for py in (part[1], part[3])]
                    eb = (min(p[0] for p in pts) - 2, min(p[1] for p in pts) - 2,
                          max(p[0] for p in pts) + 2, max(p[1] for p in pts) + 2)
                    stages = [{"type": "readers.ept", "filename": path, "bounds": _pdal_bounds(eb)}, reproject,
                              {"type": "filters.crop", "bounds": _pdal_bounds(part)}]
                    p = pdal.Pipeline(json.dumps(stages))
                    p.execute()
                    for arr in p.arrays:
                        if not len(arr):
                            continue
                        X, Y = arr["X"], arr["Y"]
                        ok = (X >= part[0]) & (Y >= part[1]) & ((X < part[2]) | (i == nx - 1)) & \
                             ((Y < part[3]) | (j == ny - 1))
                        if ok.any():
                            yield arr[ok]
        else:
            raise ClassError(f"{path}: a point source is a .las or .laz file, or an EPT's ept.json")


def _same_frame(path, out_srs):
    """Whether a LAS/LAZ file's horizontal CRS is out_srs (from its header): it's then cropped without reprojecting,
    as the shrub build reads it (a reprojection to a 2-D CRS would leave the heights as they are anyway)."""
    import pdal
    qi = pdal.Reader.las(filename=path).pipeline().quickinfo["readers.las"]
    srs = qi.get("srs") or {}
    wkt = srs.get("horizontal") or srs.get("wkt")
    if not wkt:
        return False
    a, b = osr.SpatialReference(), osr.SpatialReference(wkt=out_srs)
    try:
        a.SetFromUserInput(wkt)
    except RuntimeError:
        return False
    if a.IsCompound():
        a.StripVertical()
    return bool(a.IsSame(b))


def _ept_wkt(path):
    with open(path, encoding="utf-8") as f:
        srs = json.load(f).get("srs") or {}
    if srs.get("wkt"):
        return srs["wkt"]
    s = osr.SpatialReference()
    s.ImportFromEPSG(int(srs["horizontal"]))
    return s.ExportToWkt()


def ground_brightness(sources, g, in_srs=None, log=print):
    """Per cell, the mean of its ground points' (class 2) intensity, each over its flight line's median (exp28's
    "bright"; lines differ); NaN where a cell has none. One pass, keeping each ground point's cell, line and
    intensity compactly (8 bytes)."""
    cells, lines, inten = [], [], []
    n_read = 0
    for arr in read_points(sources, g, in_srs):
        n_read += len(arr)
        keep = _keep(arr) & (arr["Classification"] == 2)
        if not keep.any():
            continue
        a = arr[keep]
        col = np.floor((a["X"] - g.x0) / CR.PX).astype(np.int64)
        row = np.floor((g.y1 - a["Y"]) / CR.PX).astype(np.int64)
        ok = (col >= 0) & (col < g.cols) & (row >= 0) & (row < g.rows)
        cells.append((row[ok] * g.cols + col[ok]).astype(np.int32))
        line = a["PointSourceId"] if "PointSourceId" in a.dtype.names else np.zeros(len(a), np.uint16)
        lines.append(line[ok].astype(np.uint16))
        inten.append(a["Intensity"][ok].astype(np.uint16))
    if not cells:
        return np.full(g.shape, np.nan, np.float32), {"points": n_read, "ground_points": 0, "lines": 0}
    cell, line, inten = np.concatenate(cells), np.concatenate(lines), np.concatenate(inten)
    del cells, lines
    norm = np.ones(len(inten), np.float32)
    medians = {}
    for L in np.unique(line):
        sel = line == L
        if sel.sum() > 100:
            m = float(np.median(inten[sel]))
            medians[int(L)] = m
            norm[sel] = max(m, 1.0)
    w = inten.astype(np.float32) / norm
    n = np.bincount(cell, minlength=g.rows * g.cols)
    s = np.bincount(cell, weights=w, minlength=g.rows * g.cols)
    with np.errstate(invalid="ignore", divide="ignore"):
        bright = np.where(n > 0, s / np.maximum(n, 1), np.nan).astype(np.float32).reshape(g.shape)
    st = {"points": n_read, "ground_points": int(len(cell)), "lines": len(medians)}
    log(f"    brightness: {st['ground_points']:,} ground points of {n_read:,}, {len(medians)} flight lines")
    return bright, st


def read_osm_lines(path, boxes, log=print):
    """One pass over the OSM cut: {box id: (roads, tracks)} as lists of OGR geometries in the grid's CRS (the photo's
    frame), for highway lines near each box. Roads: maskrules.road's major roads, streets and service ways; tracks:
    highway=track. Ways under the ground aren't read."""
    gdal.SetConfigOption("CPL_TMPDIR", tempfile.gettempdir())       # the OSM driver's temporary files
    ds = gdal.OpenEx(path, gdal.OF_VECTOR, allowed_drivers=["OSM"],
                     open_options=[f"CONFIG_FILE={OSMCONF}", "INTERLEAVED_READING=YES"])
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(grid.EPSG)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    src = ds.GetLayerByName("lines").GetSpatialRef().Clone()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(src, utm)
    rects = {}
    for b in boxes:
        w, s, e, n = b.utm
        rects[b.id] = (w - OSM_MARGIN_M, s - OSM_MARGIN_M, e + OSM_MARGIN_M, n + OSM_MARGIN_M)
    lon0, lat0, lon1, lat1 = grid.lonlat_of(_union(rects.values()))
    out = {b.id: ([], []) for b in boxes}
    n = 0
    while True:
        f, lyr = ds.GetNextFeature()
        if f is None:
            break
        if lyr.GetName() != "lines":
            continue
        g = f.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        x0, x1, y0, y1 = g.GetEnvelope()
        if x1 < lon0 or x0 > lon1 or y1 < lat0 or y0 > lat1:
            continue
        tags = json.loads(f.GetField("all_tags") or "{}")
        hw = tags.get("highway")
        if not hw or MR.below_ground(tags):
            continue
        road = MR.road(tags)
        is_road = bool(road) and road[0] in ROAD_KINDS
        is_track = hw == "track"
        if not (is_road or is_track):
            continue
        g = g.Clone()
        g.Transform(ct)
        ex0, ex1, ey0, ey1 = g.GetEnvelope()
        for bid, (w, s, e, nn) in rects.items():
            if ex1 < w or ex0 > e or ey1 < s or ey0 > nn:
                continue
            out[bid][0 if is_road else 1].append(g)
            n += 1
    log(f"  osm: {n:,} road and track lines near the boxes")
    return out


def _union(rects):
    rects = list(rects)
    return (min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects))


def burn_lines(geoms, g, shift, reach_m=None):
    """Lines (grid CRS, photo frame) moved onto the lidar (minus the shift) and burned into g: every cell a line
    touches, or every cell within reach_m of one."""
    mask = np.zeros(g.shape, bool)
    if not geoms:
        return mask
    east, north = shift
    mem = gdal.GetDriverByName("MEM").Create("", g.cols, g.rows, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(g.transform)
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(grid.EPSG)
    mem.SetProjection(utm.ExportToWkt())
    vds = R._mem_vector()
    lyr = vds.CreateLayer("l", utm, ogr.wkbUnknown)
    for geom in geoms:
        gg = geom.Clone()
        _move(gg, -east, -north)
        ft = ogr.Feature(lyr.GetLayerDefn())
        ft.SetGeometry(gg)
        lyr.CreateFeature(ft)
    gdal.RasterizeLayer(mem, [1], lyr, burn_values=[1], options=["ALL_TOUCHED=TRUE"])
    mask = mem.GetRasterBand(1).ReadAsArray() > 0
    if reach_m:
        mask = R.grow(mask, reach_m, CR.PX)
    return mask


def _move(g, dx, dy):
    if g.GetGeometryCount():
        for i in range(g.GetGeometryCount()):
            _move(g.GetGeometryRef(i), dx, dy)
        return
    for i in range(g.GetPointCount()):
        x, y = g.GetX(i), g.GetY(i)
        g.SetPoint_2D(i, x + dx, y + dy)


def to_photo_frame(a, shift):
    """A lidar-frame array moved into the photo's frame: lidar cell (r, c) goes to (r + dy, c + dx), where
    east = dx x 0.5 m and north = -dy x 0.5 m. Cells moved in from outside are 0 (no data)."""
    dx, dy = int(round(shift[0] / CR.PX)), int(round(-shift[1] / CR.PX))
    if not dx and not dy:
        return a
    out = np.zeros_like(a)
    rows, cols = a.shape
    sr = slice(max(0, -dy), min(rows, rows - dy))
    sc = slice(max(0, -dx), min(cols, cols - dx))
    dr = slice(max(0, dy), min(rows, rows + dy))
    dc = slice(max(0, dx), min(cols, cols + dx))
    out[dr, dc] = a[sr, sc]
    return out


# ---- one box -------------------------------------------------------------------------------------------------------

def classify_box(box, spec, osm_lines, july_dir, norm, log=print):
    """(class, floor, report) for one box, in the photo's frame on the box's window."""
    t0 = time.time()
    h, bad, g = read_lidar(spec["lidar"])
    offset = box_offset(box, g)
    bld = np.load(spec["mask"]).astype(bool)
    if bld.shape != g.shape:
        raise ClassError(f"box {box.id}: the building mask is {bld.shape}, the lidar {g.shape}")
    sh = read_shrubs(spec["shrubs"], g)
    shift = sh["shift"]
    ndvi, lum = read_photo(spec["photo"], g, shift)
    cover = float(np.isfinite(ndvi[~bad]).mean()) if (~bad).any() else 0.0
    if cover < 0.95:
        raise ClassError(f"box {box.id}: the photo gives an NDVI on {cover:.0%} of the lidar's cells (95% needed)")
    curve = curve_of(norm, spec["curve"])
    july, cell = read_july(july_dir, g)
    bright, bst = ground_brightness(spec["points"], g, spec.get("points_srs"), log=log)
    dark = ndi.median_filter(np.nan_to_num(bright, nan=1.0), CR.BARE_MEDIAN_CELLS) < CR.DARK_CUT
    roads, tracks = osm_lines.get(box.id, ([], []))
    flat = (h < CR.BAND_M[0]) & ~bld & ~bad
    on_road = burn_lines(roads, g, shift, ROAD_REACH_M) & flat
    track_line = burn_lines(tracks, g, shift)
    f = {"h": h, "bld": bld, "bad": bad, "edge": CR.edge_ring(bld), "rough": CR.roughness(h, bld),
         "plant": CR.plant_cue(sh["n_ag"], sh["scat"]), "kept": sh["kept"], "treecue": sh["treecue"],
         "field": sh["field"], "p": CR.to_s2(ndvi, curve), "dark": dark}
    cls, fl, st = CR.classify(f, cell, july, on_road, track_line, lum)
    cls, fl = embed(to_photo_frame(cls, shift), box, offset), embed(to_photo_frame(fl, shift), box, offset)
    report = {"box": box.id, "name": box.name, "shift_m": list(shift), "photo_cover": round(cover, 4),
              "lidar_offset_cells": list(offset),
              "curve": spec["curve"], "shrub_build": sh["build"], "brightness": bst,
              "osm_lines": {"roads": len(roads), "tracks": len(tracks)}, "road_cells": int(on_road.sum()),
              "track_line_cells": int(track_line.sum()), **st, "seconds": round(time.time() - t0, 1)}
    log(f"  box {box.id}: " + ", ".join(f"{k} {v}" for k, v in st["shares"].items() if v >= 1) +
        f"; tracks {st['track_cells']:,} cells; {report['seconds']:.0f} s")
    return cls, fl, report, sh


# ---- writing -------------------------------------------------------------------------------------------------------

def write_box(path, box, cls, fl):
    w = box.window()
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, w.width, w.height, 2, gdal.GDT_Byte,
                    options=["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BLOCKXSIZE=512", "BLOCKYSIZE=512"])
    ds.SetGeoTransform(w.transform)
    s = osr.SpatialReference()
    s.ImportFromEPSG(grid.EPSG)
    ds.SetProjection(s.ExportToWkt())
    for i, (a, name) in enumerate(((cls, "class"), (fl, "floor")), start=1):
        b = ds.GetRasterBand(i)
        b.WriteArray(a)
        b.SetNoDataValue(0)
        b.SetDescription(name)
    ds.FlushCache()
    ds = None


def band_specs():
    values = {str(k): v for k, v in CR.CLASSES.items() if k}
    return [{"name": "class", "type": "uint8", "nodata": 0, "values": values,
             "about": "the owner's scheme as of July (classrules.py): what covers each 0.5 m cell"},
            {"name": "floor", "type": "uint8", "nodata": 0, "values": values,
             "about": "the ground under it: under trees, shrubs, hard things and walls the nearest ground's class; "
                      "under closed canopy, forest floor (the painter paints this band)"}]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _osm_entry(path):
    """The osm input as mask v0 names it (the extract's MD5 from valley.json, the cut's sha256), with what's read."""
    from basemap.ground import mask
    try:
        e = mask.osm_entry(path)
    except mask.MaskError as err:
        raise ClassError(str(err)) from None
    e["note"] += ("; read here: roads (never greened by the July rule) and highway=track lines (the track rule)")
    return e


def entries(recipe, boxes, reports, shrubs):
    """The product's manifest inputs: RAW names only (inputs.check_raw_only), each with its version and a note on
    which files it came through."""
    used = [recipe["boxes"][b.id] for b in boxes]
    lidar = sorted({f"{s['lidar_name']} ({s['lidar_date']})" for s in used})
    july = recipe["july"]
    s2_sha = sha256_file(os.path.join(july, "ndvi_median.tif"))
    norm_sha = sha256_file(recipe["norm"])
    crop_inputs = {}
    for sh in shrubs:
        for i in ((sh.get("crop") or {}).get("inputs") or []):
            crop_inputs.setdefault(i["name"], i.get("version"))
    photos = sorted({s["curve"] for s in used})
    E = inputs.RAW_BY_NAME
    out = [
        dict(E["3dep"].entry("; ".join(lidar)), note="the boxes' 0.5 m lidar products (DSM, DTM), their point clouds "
             "(ground brightness) and the shrub builds' cues (returns above the ground and their scatter)"),
        dict(E["overture-buildings"].entry("the trees build's building masks"),
             note="Overture's footprints aligned to the lidar and zeroed with a buffer (one mask per box)"),
        dict(E["naip"].entry("NAIP 2025 county mosaics (boxes a-f, downtown); NAIP 2023 (boxes h-j)"),
             note=f"the boxes' NAIP crops; NDVI curves {', '.join(photos)}"),
        dict(E["sentinel-2"].entry(f"July 2025 NDVI median, max, min and clear views; same-day normalisation "
                                   f"fits.json sha256 {norm_sha[:12]}"), sha256=s2_sha,
             note="July 2025 per 10 m cell (the July rule) and the photo NDVI's curve onto Sentinel-2's scale"),
        _osm_entry(recipe["osm"]),
    ]
    for name in ("csb", "cdl"):
        if name in crop_inputs:
            out.append(dict(E[name].entry(str(crop_inputs[name] or "as farm's crop cover read")),
                            note="through farm's crop cover, which the shrub builds read (the shrub rule's crop "
                                 "pieces)"))
    return out


class _Lock:
    def __init__(self, archive):
        root = os.path.join(archive, PRODUCT)
        os.makedirs(root, exist_ok=True)
        self.f = open(os.path.join(root, LOCK), "a")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise ClassError(f"another class build is running in {root}") from None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def build(archive, recipe, box_ids=None, build_id=None, command=None, keep=KEEP, log=print):
    """Build the box classes into <archive>/ground_classes/export/<build>/ and return its Manifest. box_ids: some
    boxes only (a partial build, <build>-part)."""
    all_ids = [b.id for b in grid.boxes()]
    box_ids = list(box_ids or all_ids)
    unknown = [b for b in box_ids if b not in all_ids]
    if unknown:
        raise ClassError(f"no box {', '.join(unknown)} ({', '.join(all_ids)})")
    missing = [b for b in box_ids if b not in recipe.get("boxes", {})]
    if missing:
        raise ClassError(f"the recipe has no inputs for box {', '.join(missing)}")
    is_whole = set(box_ids) == set(all_ids)
    build_id = build_id or (M.build_id() if is_whole else M.build_id(suffix="part"))
    if M.is_partial(build_id) == is_whole:
        raise ClassError(f"build {build_id!r}: a build of some boxes, and only one, ends in {M.PARTIAL_SUFFIX}")
    boxes = [grid.box(b) for b in all_ids if b in box_ids]
    with open(recipe["norm"], encoding="utf-8") as f:
        norm = json.load(f)
    final = M.export_dir(archive, PRODUCT, build_id)
    if os.path.exists(final):
        raise ClassError(f"{final} already exists")
    with _Lock(archive):
        root = os.path.join(archive, PRODUCT, STAGING)
        for old in (os.listdir(root) if os.path.isdir(root) else []):
            shutil.rmtree(os.path.join(root, old), ignore_errors=True)
        folder = os.path.join(root, build_id)
        os.makedirs(folder)
        t0 = time.time()
        try:
            preflight(recipe, boxes)
            osm_lines = read_osm_lines(recipe["osm"], boxes, log=log)
            reports, shrubs, layers = [], [], []
            for b in boxes:
                cls, fl, rep, sh = classify_box(b, recipe["boxes"][b.id], osm_lines, recipe["july"], norm, log=log)
                write_box(os.path.join(folder, f"{b.id}.tif"), b, cls, fl)
                reports.append(rep)
                shrubs.append(sh)
                del cls, fl
            ent = entries(recipe, boxes, reports, shrubs)
            names = [e["name"] for e in ent]
            for b in boxes:
                w = b.window()
                layers.append({"name": b.id, "file": f"{b.id}.tif", "format": "GeoTIFF", "crs": grid.CRS,
                               "grid": {"res": w.res, "west": w.west, "north": w.north, "width": w.width,
                                        "height": w.height},
                               "bands": band_specs(), "inputs": names, "base": False,
                               "title": f"Land-cover classes, box {b.id} ({b.name})"})
            with open(os.path.join(folder, "report.json"), "w", encoding="utf-8") as f:
                json.dump({"build": build_id, "rules": rules(), "boxes": reports}, f, indent=1)
            extent = "all ten boxes" if is_whole else f"boxes {', '.join(box_ids)} (a partial build)"
            note = ("The land-cover classes as of July (classrules.py: the land-cover spike's exp26 variant B, exp27, "
                    f"exp28b and exp31, and G1a's mapped tracks), {extent}, in the photo's frame. Band class: what "
                    "covers each 0.5 m cell; band floor: the ground under it (the painter's).")
            m = M.write(folder, PRODUCT, ent, layers, build=build_id, command=command, note=note)
            os.makedirs(os.path.dirname(final), exist_ok=True)
            os.rename(folder, final)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        m = M.Manifest(final, m.data)
        log(f"ground_classes {build_id}: {final} in {time.time() - t0:.0f} s")
        if is_whole:
            have = M.builds(archive, PRODUCT)
            for old in have[:-keep]:
                if old == build_id:
                    continue
                d = M.export_dir(archive, PRODUCT, old)
                os.remove(os.path.join(d, M.FILE))
                shutil.rmtree(d)
                log(f"  pruned {old}")
    return m


def rules():
    names = [n for n in dir(CR) if n.isupper() and n not in ("C", "CLASSES", "EIGHT")]
    out = {}
    for n in names:
        v = getattr(CR, n)
        if isinstance(v, (int, float, tuple, str)):
            out[n] = list(v) if isinstance(v, tuple) else v
    out["classes"] = {str(k): v for k, v in CR.CLASSES.items()}
    return out


# ---- reading it back -----------------------------------------------------------------------------------------------

def latest(archive, verify=True, hashes=True, partial=False):
    """The newest box classes (manifest.latest), or None."""
    return M.latest(archive, PRODUCT, verify=verify, hashes=hashes, partial=partial)


def _stopped(signum, _frame):
    raise SystemExit(128 + signum)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build", help="build the box classes")
    p.add_argument("--recipe", required=True, help="the inputs (JSON; see the module's docstring)")
    p.add_argument("--box", action="append", help="one box (repeat); a partial build")
    p.add_argument("--archive", help="default $TVT_ARCHIVE")
    p.add_argument("--build", help="the build id (default: the UTC time)")
    p.add_argument("--keep", type=int, default=KEEP)
    args = ap.parse_args(argv)
    signal.signal(signal.SIGTERM, _stopped)
    archive = args.archive or os.environ.get("TVT_ARCHIVE")
    if not archive:
        print("refused: give --archive or set TVT_ARCHIVE", file=sys.stderr)
        return 2
    env = os.environ.get("TVT_ARCHIVE")
    if args.box and env and os.path.realpath(archive) == os.path.realpath(env) and \
            set(args.box) != {b.id for b in grid.boxes()}:
        print("refused: a build of some boxes is partial; give --archive another folder", file=sys.stderr)
        return 2
    with open(args.recipe, encoding="utf-8") as f:
        recipe = json.load(f)
    try:
        m = build(archive, recipe, args.box, args.build,
                  command="python basemap/ground/classes.py " + " ".join(argv or sys.argv[1:]), keep=args.keep)
    except (ClassError, M.ManifestError, inputs.InputError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    print(f"{m.folder}: {len(m.layers)} box(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
