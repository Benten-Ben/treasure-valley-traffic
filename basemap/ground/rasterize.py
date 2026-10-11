"""The window-rasterising helper P2 and G1 share (C6). Runs in the worker image (GDAL, NumPy, SciPy).

Burns vectors into one window of a grid at a time, so no step ever holds a valley-wide raster:

    from basemap.ground import grid, rasterize as R
    for core, padded in grid.windows(grid.LEVELS["painter"], 2048, halo_m=20):
        roofs = R.rasterize(padded, "mask_v0.fgb", "roofs")                 # 1 inside, 0 outside
        sample = R.grow(roofs, 1.0, padded.res)                              # roofs plus 1 m, for sampling
        types = R.rasterize(padded, soils.path, attribute="ground_type", dtype="uint16")
        weight = R.feather(types == 7, 20.0, padded.res)                    # 20 m soft type edge
        weight[core.inner(padded)]                                           # cut back to the core window

- rasterize(): a target window (anything with transform, width, height and crs: a grid.Window, or target_of() for
  a raster's own grid, such as NAIP's 0.6 m windows in P2) and a vector source (a path any OGR driver reads, with a
  layer name, or a manifest.Layer). Only features near the window are read (FlatGeobuf exports carry a spatial
  index). Vectors in another CRS are transformed to the target's, under the grid's datum policy: NAD83 is taken with
  the null shift (grid.py), and PROJ never downloads anything.
- grow(): a mask grown by a distance (the mask's buffers: paving and roads by class width plus 2 m, roofs plus 1 m,
  water plus 5 m), measured between cell centres, so it matches across windows.
- feather(): a 0..1 weight from a mask's signed distance to its edge, 0.5 on the edge, linear across `width` metres
  (soil types' 20 m edges, the class boxes' 50-100 m).
- distance(): metres from each cell to the nearest masked cell.
A buffer or feather of up to `halo_m` computed on `padded` and cut to `core` is the same as one computed on the whole
grid, which test_rasterize.py checks.
"""

import os

import numpy as np
from osgeo import gdal, ogr, osr
from scipy import ndimage

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()
# The worker image turns PROJ's network on (PROJ_NETWORK=ON). Never fetch transformation grids: the datum policy
# (grid.py) needs none, and a fetch would be an unrecorded request to a third party.
osr.SetPROJEnableNetwork(False)
gdal.SetConfigOption("PROJ_NETWORK", "OFF")
os.environ["PROJ_NETWORK"] = "OFF"

_NAD83 = ("NAD83", "NORTH_AMERICAN_DATUM_1983", "NORTH AMERICAN DATUM 1983")
_DTYPES = {"uint8": gdal.GDT_Byte, "uint16": gdal.GDT_UInt16, "int16": gdal.GDT_Int16, "uint32": gdal.GDT_UInt32,
           "int32": gdal.GDT_Int32, "float32": gdal.GDT_Float32, "float64": gdal.GDT_Float64}


class Target:
    """A raster grid to burn into: a GDAL geotransform (north-up), a size and a CRS."""

    def __init__(self, transform, width, height, crs):
        self.transform, self.width, self.height, self.crs = tuple(transform), int(width), int(height), crs

    @property
    def res(self):
        return self.transform[1]

    @property
    def shape(self):
        return self.height, self.width

    @property
    def bounds(self):
        x0, rx, _, y0, _, ry = self.transform
        return x0, y0 + self.height * ry, x0 + self.width * rx, y0


def target_of(path, window=None):
    """The Target of a raster file, or of a window (col, row, width, height) of it."""
    ds = gdal.Open(path)
    gt = list(ds.GetGeoTransform())
    w, h = ds.RasterXSize, ds.RasterYSize
    if window is not None:
        c, r, w, h = window
        gt[0] += c * gt[1]
        gt[3] += r * gt[5]
    return Target(gt, w, h, ds.GetProjection())


def srs_of(crs):
    """An osr.SpatialReference for 'EPSG:n', WKT or an osr object, in x/y (lon/lat) order, with the grid's datum
    policy: a NAD83-based CRS gets WGS 84 as its datum, which is the null shift (grid.py). A compound CRS (the QL1
    lidar's NAD83(2011) / UTM 11N + NAVD88, EPSG:6340+5703) keeps only its horizontal part: the ground is 2D, and
    heights are values, never coordinates."""
    if isinstance(crs, osr.SpatialReference):
        s = crs.Clone()
    else:
        s = osr.SpatialReference()
        s.SetFromUserInput(str(crs))
    if s.IsCompound():
        s.StripVertical()
    if not (s.IsProjected() or s.IsGeographic()) or s.IsCompound():
        raise ValueError(f"{crs}: not a horizontal CRS the ground can place on its grid")
    datum = (s.GetAttrValue("DATUM") or "").upper()
    if any(d in datum for d in _NAD83):
        s.SetWellKnownGeogCS("WGS84")
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def warp_srs(crs):
    """WKT for gdal.Warp's srcSRS (or dstSRS) under the datum policy, e.g. NAIP's EPSG:26911 for the 2 m COG."""
    return srs_of(crs).ExportToWkt()


def _transform(src, dst):
    if src.IsSame(dst):
        return None
    return osr.CoordinateTransformation(src, dst)


def _bounds_in(bounds, ct):
    """bounds (in the target's CRS) as an envelope in the source's CRS (ct: target to source), edges densified."""
    w, s, e, n = bounds
    pts = []
    for i in range(17):
        t = i / 16
        pts += [(w + (e - w) * t, s), (w + (e - w) * t, n), (w, s + (n - s) * t), (e, s + (n - s) * t)]
    out = [ct.TransformPoint(x, y)[:2] for x, y in pts]
    xs, ys = [p[0] for p in out], [p[1] for p in out]
    return min(xs), min(ys), max(xs), max(ys)


def _mem_vector():
    """An in-memory vector dataset (GDAL 3.11 folded the Memory driver into MEM)."""
    if int(gdal.VersionInfo()) >= 3110000:
        return gdal.GetDriverByName("MEM").Create("", 0, 0, 0, gdal.GDT_Unknown)
    return ogr.GetDriverByName("Memory").CreateDataSource("")


def _open(source, layer):
    """(datasource, layer) for a path or a manifest.Layer."""
    if hasattr(source, "path") and hasattr(source, "spec"):            # a manifest.Layer
        path = source.path
    else:
        path = os.fspath(source)
    ds = ogr.Open(path)
    if ds is None:
        raise ValueError(f"can't open {path}")
    lyr = ds.GetLayerByName(layer) if layer else ds.GetLayer(0)
    if lyr is None:
        raise ValueError(f"{path} has no layer {layer!r}")
    return ds, lyr


def rasterize(target, source, layer=None, *, burn=1, attribute=None, where=None, all_touched=False,
              dtype="uint8", fill=0):
    """Burn a vector layer into the target window. Returns a NumPy array of target.shape.

    burn: the value for every feature (default 1), or attribute: a numeric field's value per feature; later features
    win where they overlap. where: an OGR attribute filter. all_touched: burn every cell a feature touches (default:
    cells whose centre is inside, which is what areas want). fill: the value where nothing burns."""
    if dtype not in _DTYPES:
        raise ValueError(f"dtype must be one of {', '.join(_DTYPES)}")
    ds, lyr = _open(source, layer)
    dst = srs_of(target.crs)
    lsrs = lyr.GetSpatialRef()
    src = srs_of(lsrs) if lsrs is not None else dst
    w, s, e, n = target.bounds
    to_src = _transform(dst, src)
    fw, fs, fe, fn = _bounds_in((w, s, e, n), to_src) if to_src else (w, s, e, n)
    lyr.SetSpatialFilterRect(fw, fs, fe, fn)
    lyr.SetAttributeFilter(where)

    mem_v = _mem_vector()
    out = mem_v.CreateLayer("burn", dst, ogr.wkbUnknown)
    if attribute:
        defn = lyr.GetLayerDefn()
        idx = defn.GetFieldIndex(attribute)
        if idx < 0:
            raise ValueError(f"no field {attribute!r} in {lyr.GetName()}")
        out.CreateField(ogr.FieldDefn("v", ogr.OFTReal))
    to_dst = _transform(src, dst)
    for f in lyr:
        g = f.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        g = g.Clone()
        if to_dst:
            g.Transform(to_dst)
        o = ogr.Feature(out.GetLayerDefn())
        o.SetGeometry(g)
        if attribute:
            if f.IsFieldNull(idx):
                continue
            o.SetField("v", f.GetFieldAsDouble(idx))
        out.CreateFeature(o)
    lyr.SetSpatialFilter(None)
    lyr.SetAttributeFilter(None)

    mem_r = gdal.GetDriverByName("MEM").Create("", target.width, target.height, 1, _DTYPES[dtype])
    mem_r.SetGeoTransform(target.transform)
    mem_r.SetProjection(dst.ExportToWkt())
    band = mem_r.GetRasterBand(1)
    band.Fill(fill)
    opts = ["ALL_TOUCHED=TRUE"] if all_touched else []
    if attribute:
        gdal.RasterizeLayer(mem_r, [1], out, options=opts + ["ATTRIBUTE=v"])
    else:
        gdal.RasterizeLayer(mem_r, [1], out, burn_values=[burn], options=opts)
    arr = band.ReadAsArray()
    del mem_r, mem_v, ds
    return arr


def distance(mask, res):
    """Metres from each cell's centre to the nearest masked cell's centre (0 on the mask)."""
    mask = np.asarray(mask, bool)
    if not mask.any():
        return np.full(mask.shape, np.inf, np.float32)
    return ndimage.distance_transform_edt(~mask, sampling=res).astype(np.float32)


def grow(mask, metres, res):
    """The mask grown by `metres`: every cell whose centre is within that distance of a masked cell's centre."""
    mask = np.asarray(mask, bool)
    if metres <= 0:
        return mask.copy()
    return distance(mask, res) <= metres + 1e-6


def signed_distance(mask, res):
    """Metres from each cell's centre to the mask's edge (half a cell beyond the outermost centres): positive inside,
    negative outside."""
    mask = np.asarray(mask, bool)
    if mask.all():
        return np.full(mask.shape, np.inf, np.float32)
    if not mask.any():
        return np.full(mask.shape, -np.inf, np.float32)
    inside = ndimage.distance_transform_edt(mask, sampling=res)
    outside = ndimage.distance_transform_edt(~mask, sampling=res)
    return np.where(mask, inside - res / 2, -(outside - res / 2)).astype(np.float32)


def feather(mask, width, res):
    """A 0..1 weight: 0.5 on the mask's edge, rising linearly to 1 at width/2 inside and falling to 0 at width/2
    outside. Weights of neighbouring regions feathered with the same width sum to about 1 across their shared edge."""
    if width <= 0:
        return np.asarray(mask, np.float32)
    d = signed_distance(mask, res)
    return np.clip(0.5 + d / width, 0.0, 1.0).astype(np.float32)
