#!/usr/bin/env python3
"""Mask v0 (C6): what covers the ground, from raw inputs, built on the server. Runs in the worker image (GDAL).

    python basemap/ground/mask.py build --roofs DIR/buildings.pmtiles               # into $TVT_ARCHIVE
    python basemap/ground/mask.py build --roofs ... --box d --archive /tmp/a        # one box, for a quick look

What it reads, every one public (inputs.RAW; C17):
- osm: S1's valley cut of the held extract ($TVT_ARCHIVE/osm/cut/valley.osm.pbf, with the valley.json that names
  its extract), through GDAL's OSM driver with osmconf.ini beside this file (every tag, as JSON). The extract has
  no Oregon, so the box's Malheur slice has no OSM;
- overture-buildings: Overture's roofs as the map's buildings.pmtiles holds them at z15 (basemap/buildings.py), the
  release named by the tiles manifest's entry (a buildings.json beside it) or --roofs-release;
- nhd: NHD HU4 1705 ($TVT_SOURCES/nhd/nhd_mapbox.gpkg: waterbodies, areas and flowlines);
- cdl: CDL 2025 at 10 m ($TVT_SOURCES/cdl/out/cdl_2025_10m.tif), its developed land (classes 123 and 124).
NAD83 inputs (NHD, CDL) are read with the grid's null datum shift (rasterize.srs_of).

maskrules.py decides what covers the ground and how wide a line is. mask.py writes its layers (maskrules.LAYERS) as
MultiPolygon FlatGeobufs in EPSG:32611, each with its spatial index, to $TVT_ARCHIVE/ground_mask/export/<build>/,
then manifest.json, last, through manifest.write(): every raw input with its version and sha256. A build that
fails leaves no folder behind. The whole grid took 11 minutes at 474 MB (a light worker job), and 354 MB on disk.

Consumers read it through the shared window-rasterising helper (rasterize.py):

    from basemap.ground import grid, mask
    m = mask.latest(archive)                                    # the newest mask v0, every file checked
    for core, padded in grid.windows(grid.LEVELS["painter"], 2048, halo_m=20):
        sample = ~mask.covered(padded, m)                       # uncovered ground, for the soil sampler
        roofs = mask.exact(padded, m, "roofs")                  # one exact layer, for the painter
        wet = mask.exact(padded, m, "water", where="intermittent = 0")
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np  # noqa: E402
from osgeo import gdal, ogr, osr  # noqa: E402

from basemap.ground import grid, inputs, manifest as M, maskrules as MR  # noqa: E402
from basemap.ground import rasterize as R  # noqa: E402   (also switches PROJ's network off)

gdal.UseExceptions()
ogr.UseExceptions()

PRODUCT = "ground_mask"
OSMCONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osmconf.ini")
ROOF_ZOOM = 15                    # buildings.pmtiles' full-detail zoom (basemap/buildings.py: z14-z15)
# Buffers: mitre joins (bevelled past twice the distance), so a grown roof keeps its corners and a line's bends add
# no arcs. An exact line gets round ends (3 segments a quarter circle: a 5 m radius' chord falls 0.17 m short of the
# arc), as a road's end or a junction looks; a sampling buffer gets square ends, a little more than round ones.
EXACT_LINE = ["ENDCAP_STYLE=ROUND", "QUADRANT_SEGMENTS=3", "JOIN_STYLE=MITRE", "MITRE_LIMIT=2"]
SAMPLE = ["ENDCAP_STYLE=SQUARE", "JOIN_STYLE=MITRE", "MITRE_LIMIT=2"]
NHD_VERSION = "HU4 1705, published 2023-12-09"
CDL_BLOCK_ROWS = 2048             # CDL is polygonised in blocks of rows, so memory stays small

LAYER_INPUTS = {"roofs": ["overture-buildings"], "roads": ["osm"], "paving": ["osm"], "water": ["nhd", "osm"],
                "covered": ["osm", "overture-buildings", "nhd", "cdl"]}

_OGR_TYPES = {"int": ogr.OFTInteger, "long": ogr.OFTInteger64, "double": ogr.OFTReal, "string": ogr.OFTString,
              "bool": ogr.OFTInteger}


class MaskError(ValueError):
    pass


# ---- geometry ------------------------------------------------------------------------------------------------------

def utm():
    return R.srs_of(grid.CRS)


def transformer(src_srs):
    """src (an osr.SpatialReference) -> the grid's CRS, under the datum policy; None when they're the same."""
    src, dst = R.srs_of(src_srs), utm()
    return None if src.IsSame(dst) else osr.CoordinateTransformation(src, dst)


def multipolygon(g):
    """g's polygonal parts as one valid MultiPolygon, or None when it has none (a point, a line, an empty)."""
    if g is None or g.IsEmpty():
        return None
    if not g.IsValid():
        g = g.MakeValid()
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t == ogr.wkbPolygon:
        return ogr.ForceToMultiPolygon(g)
    if t == ogr.wkbMultiPolygon:
        return g
    if t == ogr.wkbGeometryCollection:
        out = ogr.Geometry(ogr.wkbMultiPolygon)
        for i in range(g.GetGeometryCount()):
            part = multipolygon(g.GetGeometryRef(i))
            if part is not None:
                for j in range(part.GetGeometryCount()):
                    out.AddGeometry(part.GetGeometryRef(j))
        return out if out.GetGeometryCount() else None
    return None


def grown(g, metres, options=SAMPLE):
    """g (a line or polygon, in metres) grown by `metres`, as a MultiPolygon (None when nothing's left)."""
    return multipolygon(g.Buffer(metres, options) if metres > 0 else g)


def inside(g, bounds):
    """True when g's envelope meets bounds (west, south, east, north)."""
    x0, x1, y0, y1 = g.GetEnvelope()
    w, s, e, n = bounds
    return x1 >= w and x0 <= e and y1 >= s and y0 <= n


def envelope_in(bounds, ct):
    """bounds (grid metres) as an envelope in another CRS (ct: grid -> that CRS), its edges densified."""
    w, s, e, n = bounds
    xs, ys = [], []
    for i in range(33):
        t = i / 32
        for x, y in ((w + (e - w) * t, s), (w + (e - w) * t, n), (w, s + (n - s) * t), (e, s + (n - s) * t)):
            p = ct.TransformPoint(x, y)
            xs.append(p[0])
            ys.append(p[1])
    return min(xs), min(ys), max(xs), max(ys)


def filter_rect(lyr, bounds):
    """Limit a source layer to features near bounds (grid metres), in the layer's own CRS."""
    s = lyr.GetSpatialRef()
    if s is None:
        return
    ct = osr.CoordinateTransformation(utm(), R.srs_of(s))
    x0, y0, x1, y1 = envelope_in(bounds, ct)
    pad = 0.001 if R.srs_of(s).IsGeographic() else 100.0
    lyr.SetSpatialFilterRect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)


# ---- writing -------------------------------------------------------------------------------------------------------

class Writer:
    """One of mask v0's layers: a MultiPolygon FlatGeobuf in the grid's CRS, with its spatial index, ids from 1."""

    def __init__(self, folder, name, file=None):
        self.name = name
        self.file = file or f"{name}.fgb"
        self.path = os.path.join(folder, self.file)
        self.fields = MR.LAYERS[name][2]
        self.ds = ogr.GetDriverByName("FlatGeobuf").CreateDataSource(self.path)
        self.lyr = self.ds.CreateLayer(name, utm(), ogr.wkbMultiPolygon, options=["SPATIAL_INDEX=YES"])
        for fname, ftype in self.fields:
            fd = ogr.FieldDefn(fname, _OGR_TYPES[ftype])
            if ftype == "bool":
                fd.SetSubType(ogr.OFSTBoolean)
            self.lyr.CreateField(fd)
        self.defn = self.lyr.GetLayerDefn()
        self.n = 0
        self.kinds = {}

    def add(self, geom, **attrs):
        """Write geom (any geometry; only its polygonal parts are kept) with attrs. Returns its id, or None."""
        g = multipolygon(geom)
        if g is None:
            return None
        self.n += 1
        f = ogr.Feature(self.defn)
        f.SetGeometry(g)
        f.SetField("id", self.n)
        for k, v in attrs.items():
            if v is None:
                f.SetFieldNull(k)
            else:
                f.SetField(k, int(v) if isinstance(v, bool) else v)
        self.lyr.CreateFeature(f)
        key = attrs.get("what") or attrs.get("kind") or self.name
        self.kinds[key] = self.kinds.get(key, 0) + 1
        return self.n

    def close(self):
        self.lyr = self.defn = None
        self.ds = None                     # the FlatGeobuf writer sorts and writes its index here

    def spec(self):
        return {"name": self.name, "file": self.file, "format": "FlatGeobuf", "inputs": LAYER_INPUTS[self.name],
                "features": self.n, "base": False, "note": MR.LAYERS[self.name][1]}


class Out:
    """The layers being written (maskrules.LAYERS), as attributes: out.roofs, out.roads, out.paving, out.water, and
    out.raw, every sampling buffer one by one, which dissolve() turns into `covered`."""

    RAW = ".covered-raw.fgb"

    def __init__(self, folder):
        self.folder = folder
        self.exact = {name: Writer(folder, name) for name in MR.PAINT_LAYERS}
        self.roofs, self.roads, self.paving = self.exact["roofs"], self.exact["roads"], self.exact["paving"]
        self.water = self.exact["water"]
        self.raw = Writer(folder, MR.SAMPLE_LAYER, file=self.RAW)
        self.covered = None
        self.cover_kinds = {}

    def cover(self, geom, what, kind, extra=0.0):
        """Add geom to the sampling buffers, grown by what's buffer (plus extra: half a line's width)."""
        buf = MR.SAMPLE_BUFFER[what]
        g = grown(geom, buf + extra)
        if g is not None:
            self.raw.add(g, what=what, buffer=buf)
            key = f"{what}/{kind}"
            self.cover_kinds[key] = self.cover_kinds.get(key, 0) + 1

    def finish(self, bounds, log=print):
        """Close the exact layers, and dissolve the sampling buffers into `covered`."""
        for w in self.exact.values():
            w.close()
        self.raw.close()
        self.covered = Writer(self.folder, MR.SAMPLE_LAYER)
        try:
            dissolve(self.raw.path, self.covered, bounds, log=log)
        finally:
            self.covered.close()
            os.remove(self.raw.path)

    @property
    def writers(self):
        return list(self.exact.values()) + ([self.covered] if self.covered else [])

    def discard(self):
        """Close every file without caring how (a build that failed: its folder is removed next)."""
        for w in list(self.exact.values()) + [self.raw, self.covered]:
            if w is not None:
                try:
                    w.close()
                except Exception:   # noqa: BLE001 (a half-written file, about to be deleted)
                    pass


def rect(w, s, e, n):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((w, s), (e, s), (e, n), (w, n), (w, s)):
        ring.AddPoint_2D(x, y)
    p = ogr.Geometry(ogr.wkbPolygon)
    p.AddGeometry(ring)
    return p


def dissolve(path, out, bounds, block_m=MR.COVER_BLOCK_M, log=print):
    """The sampling buffers in `path` dissolved by what within blocks of block_m on the grid's 10 m edges (each
    piece cut to its block), written to `out`: one feature per block and what. Far fewer features and vertices
    than the buffers one by one (roads, sidewalks and driveways overlap), and the same cells when burned."""
    ds = ogr.Open(path)
    lyr = ds.GetLayer(0)
    step = int(round(block_m / grid.BASE_RES))
    blocks = 0
    for core, _ in grid.windows(grid.BASE_RES, step, bounds=grid.snap_out(bounds, block_m)):   # a global lattice
        w, s, e, n = core.bounds
        lyr.SetSpatialFilterRect(w, s, e, n)
        box = rect(w, s, e, n)
        groups = {}
        for f in lyr:
            g = f.GetGeometryRef()
            x0, x1, y0, y1 = g.GetEnvelope()
            if not (x0 >= w and x1 <= e and y0 >= s and y1 <= n):
                g = g.Intersection(box)
            part = multipolygon(g)
            if part is None:
                continue
            bag = groups.setdefault(f.GetField("what"), ogr.Geometry(ogr.wkbMultiPolygon))
            for i in range(part.GetGeometryCount()):
                bag.AddGeometry(part.GetGeometryRef(i))
        if groups:
            blocks += 1
        for what in sorted(groups):
            out.add(groups[what].UnionCascaded(), what=what, buffer=MR.SAMPLE_BUFFER[what])
    lyr.SetSpatialFilter(None)
    log(f"  covered: {lyr.GetFeatureCount():,} buffers dissolved into {out.n:,} pieces in {blocks:,} blocks")


# ---- the inputs ----------------------------------------------------------------------------------------------------

def read_osm(path, bounds, out, log=print):
    """S1's valley cut: highway, water, rail and aeroway ways, and parking, highway, water, aeroway and railway
    areas (maskrules)."""
    ds = gdal.OpenEx(path, gdal.OF_VECTOR, allowed_drivers=["OSM"],
                     open_options=[f"CONFIG_FILE={OSMCONF}", "INTERLEAVED_READING=YES"])
    ct = transformer(ds.GetLayerByName("lines").GetSpatialRef())
    seen = {"lines": 0, "multipolygons": 0}
    while True:
        f, lyr = ds.GetNextFeature()
        if f is None:
            break
        name = lyr.GetName()
        if name not in seen:
            continue
        seen[name] += 1
        tags = json.loads(f.GetField("all_tags") or "{}")
        if name == "lines":
            road, water, other = MR.road(tags), MR.waterway(tags), MR.other_line(tags)
            if not (road or water or other):
                continue
            ref = f"w{f.GetField('osm_id')}"
        else:
            road = None
            water, paving, other = MR.water_area(tags), MR.paving_area(tags), MR.other_area(tags)
            if not (water or paving or other):
                continue
            rel = f.GetField("osm_id")
            ref = f"r{rel}" if rel else f"w{f.GetField('osm_way_id')}"
        g = f.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        g = g.Clone()
        if ct:
            g.Transform(ct)
        if not inside(g, bounds):
            continue
        if name == "lines":
            if road:
                kind, surface, width, width_from = road
                out.roads.add(grown(g, width / 2, EXACT_LINE), ref=ref, highway=tags["highway"], kind=kind,
                              surface=surface, width=width, width_from=width_from, bridge=MR.bridge(tags))
                out.cover(g, "road", kind, width / 2)
            if water:
                kind, dry, width = water
                out.water.add(grown(g, width / 2, EXACT_LINE), source="osm", ref=ref, kind=kind, intermittent=dry,
                              width=width)
                if not dry:
                    out.cover(g, "water", kind, width / 2)
            if other:
                what, kind, width = other
                out.cover(g, what, kind, width / 2)
        else:
            area = multipolygon(g)
            if area is None:
                continue
            if paving:
                kind, surface = paving
                out.paving.add(area, ref=ref, kind=kind, surface=surface)
                out.cover(area, "paving", kind)
            if water:
                kind, dry = water
                out.water.add(area, source="osm", ref=ref, kind=kind, intermittent=dry, width=None)
                if not dry:
                    out.cover(area, "water", kind)
            if other:
                what, kind = other
                out.cover(area, what, kind)
    log(f"  osm: {seen['lines']:,} lines and {seen['multipolygons']:,} areas read")


def open_gpkg(path):
    """A GeoPackage opened read-only and immutable (it may sit on a read-only mount)."""
    return gdal.OpenEx(path, gdal.OF_VECTOR | gdal.OF_READONLY, allowed_drivers=["GPKG"],
                       open_options=["IMMUTABLE=YES"])


NHD_FIELDS = ("permanent_identifier", "ftype_name", "hydrographiccategory", "class", "relationshiptosurface",
              "streamorder")


def read_nhd(path, bounds, out, log=print):
    """NHD's open water: waterbodies, Stream/River and Canal/Ditch areas, and flowlines grown to their widths."""
    ds = open_gpkg(path)
    n = 0
    for layer, rule in (("waterbody", MR.nhd_waterbody), ("area", MR.nhd_area), ("flowline", MR.nhd_flowline)):
        lyr = ds.GetLayerByName(layer)
        if lyr is None:
            raise MaskError(f"{path} has no layer {layer!r} (NHD's GeoPackage: waterbody, area, flowline)")
        ct = transformer(lyr.GetSpatialRef())
        filter_rect(lyr, bounds)
        defn = lyr.GetLayerDefn()
        have = [k for k in NHD_FIELDS if defn.GetFieldIndex(k) >= 0]
        for f in lyr:
            n += 1
            fields = {k: f.GetField(k) for k in have}
            r = rule(fields)
            g = f.GetGeometryRef()
            if r is None or g is None or g.IsEmpty():
                continue
            g = g.Clone()
            if ct:
                g.Transform(ct)
            if not inside(g, bounds):
                continue
            ref = f"nhd:{fields.get('permanent_identifier')}"
            if layer == "flowline":
                kind, dry, width = r
                out.water.add(grown(g, width / 2, EXACT_LINE), source="nhd", ref=ref, kind=kind, intermittent=dry,
                              width=width)
                if not dry:
                    out.cover(g, "water", kind, width / 2)
            else:
                kind, dry = r
                area = multipolygon(g)
                if area is None:
                    continue
                out.water.add(area, source="nhd", ref=ref, kind=kind, intermittent=dry, width=None)
                if not dry:
                    out.cover(area, "water", kind)
    log(f"  nhd: {n:,} features read")


def read_roofs(path, bounds, out, log=print):
    """Overture's roofs: every polygon of the source's first layer (buildings.pmtiles at its full-detail zoom)."""
    opts = [f"ZOOM_LEVEL={ROOF_ZOOM}"] if path.endswith(".pmtiles") else []
    ds = gdal.OpenEx(path, gdal.OF_VECTOR, open_options=opts)
    lyr = ds.GetLayer(0)
    ct = transformer(lyr.GetSpatialRef())
    filter_rect(lyr, bounds)
    n = 0
    for f in lyr:
        n += 1
        g = f.GetGeometryRef()
        if g is None or g.IsEmpty():
            continue
        g = g.Clone()
        if ct:
            g.Transform(ct)
        if not inside(g, bounds):
            continue
        roof = multipolygon(g)
        if roof is None:
            continue
        out.roofs.add(roof)
        out.cover(roof, "roof", "roof")
    log(f"  roofs: {n:,} features read")


def read_cdl(path, bounds, out, log=print):
    """CDL's developed land (maskrules.CDL_DEVELOPED), polygonised on its own 10 m grid (no resampling), in blocks of
    rows, then carried to the grid's CRS. A polygon crossing a block's edge is split there."""
    src = gdal.Open(path)
    gt = src.GetGeoTransform()
    if gt[2] or gt[4]:
        raise MaskError(f"{path}: a rotated raster")
    ct_in = osr.CoordinateTransformation(utm(), R.srs_of(src.GetSpatialRef()))
    x0, y0, x1, y1 = envelope_in(bounds, ct_in)
    c0 = max(0, int((x0 - gt[0]) / gt[1]) - 1)
    c1 = min(src.RasterXSize, int((x1 - gt[0]) / gt[1]) + 2)
    r0 = max(0, int((y1 - gt[3]) / gt[5]) - 1)
    r1 = min(src.RasterYSize, int((y0 - gt[3]) / gt[5]) + 2)
    if c1 <= c0 or r1 <= r0:
        log("  cdl: nothing inside the bounds")
        return
    ct = transformer(src.GetSpatialRef())
    band = src.GetRasterBand(1)
    classes = np.array(sorted(MR.CDL_DEVELOPED), dtype=np.uint16)
    mem_drv = gdal.GetDriverByName("MEM")
    n = 0
    for r in range(r0, r1, CDL_BLOCK_ROWS):
        h = min(CDL_BLOCK_ROWS, r1 - r)
        a = band.ReadAsArray(c0, r, c1 - c0, h)
        a = np.where(np.isin(a, classes), a, 0).astype(np.uint8)
        if not a.any():
            continue
        block = mem_drv.Create("", c1 - c0, h, 1, gdal.GDT_Byte)
        block.SetGeoTransform((gt[0] + c0 * gt[1], gt[1], 0.0, gt[3] + r * gt[5], 0.0, gt[5]))
        block.SetSpatialRef(src.GetSpatialRef())
        b = block.GetRasterBand(1)
        b.WriteArray(a)
        vds = R._mem_vector()
        vl = vds.CreateLayer("dev", src.GetSpatialRef(), ogr.wkbPolygon)
        vl.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
        gdal.Polygonize(b, b, vl, 0, [])
        for f in vl:
            g = f.GetGeometryRef().Clone()
            if ct:
                g.Transform(ct)
            if not inside(g, bounds):
                continue
            n += 1
            out.cover(g, "developed", MR.CDL_DEVELOPED[f.GetField("v")])
        del vl, vds, block
    log(f"  cdl: {n:,} developed polygons")


# ---- versions ------------------------------------------------------------------------------------------------------

def osm_entry(path, version=None):
    """The osm input: the extract's MD5 (valley.json beside the cut names it), and the cut's sha256."""
    sha = M.sha256_of(path)
    info = {}
    j = os.path.join(os.path.dirname(path), "valley.json")
    if os.path.isfile(j):
        with open(j, encoding="utf-8") as f:
            info = json.load(f)
        if info.get("sha256") and info["sha256"] != sha:
            raise MaskError(f"{path} isn't the cut {j} describes (sha256 differs): remake it with osm-load --cut-only")
    version = version or info.get("md5")
    if not version:
        raise MaskError(f"no valley.json beside {path}: give --osm-version (the extract's MD5)")
    e = inputs.RAW_BY_NAME["osm"].entry(version)
    e["sha256"] = sha
    note = "S1's valley cut (osmium extract --strategy smart)"
    if info.get("extract"):
        note += f" of {info['extract']}"
    if info.get("data_as_of"):
        note += f", OpenStreetMap data as of {info['data_as_of']}"
    e["note"] = note + ". The extract has no Oregon, so the box's Malheur slice has no OpenStreetMap data"
    return e


_RELEASE = re.compile(r"\b(\d{4}-\d{2}-\d{2}(?:\.\d+)?)\b")


def roofs_entry(path, release=None):
    """The overture-buildings input: Overture's release (from buildings.json beside a buildings.pmtiles, the tiles
    manifest's entry, or given) and the file's sha256."""
    built = None
    j = os.path.join(os.path.dirname(path), "buildings.json")
    if not release and os.path.isfile(j):
        with open(j, encoding="utf-8") as f:
            b = json.load(f).get("buildings", {})
        m = _RELEASE.search(b.get("source", ""))
        release, built = (m.group(1) if m else None), b.get("built")
    if not release:
        raise MaskError(f"name Overture's release of {path}: --roofs-release, or a buildings.json beside it")
    e = inputs.RAW_BY_NAME["overture-buildings"].entry(release)
    e["sha256"] = M.sha256_of(path)
    note = f"Overture Maps {release}, theme=buildings/type=building, read from {os.path.basename(path)}"
    if path.endswith(".pmtiles"):
        note += f" at z{ROOF_ZOOM} (the map's buildings{', built ' + built if built else ''}); a roof crossing a " \
                f"z{ROOF_ZOOM} tile's edge is split there"
    e["note"] = note
    return e


def file_entry(name, path, version, note=None):
    e = inputs.RAW_BY_NAME[name].entry(version)
    e["sha256"] = M.sha256_of(path)
    if note:
        e["note"] = note
    return e


def cdl_version(path, given=None):
    if given:
        return given
    m = re.search(r"cdl_(\d{4})_", os.path.basename(path))
    if not m:
        raise MaskError(f"name CDL's year for {path}: --cdl-version")
    return m.group(1)


# ---- the build -----------------------------------------------------------------------------------------------------

def build(archive, osm, nhd, roofs, cdl, bounds=None, build_id=None, osm_version=None, roofs_release=None,
          nhd_version=NHD_VERSION, cdl_ver=None, command=None, log=print):
    """Build mask v0 into <archive>/ground_mask/export/<build>/ and return its Manifest. bounds (west, south, east,
    north; grid metres) limits it to part of the grid (default: all of it)."""
    bounds = tuple(bounds) if bounds else grid.EXTENT
    for label, p in (("osm", osm), ("nhd", nhd), ("roofs", roofs), ("cdl", cdl)):
        if not p or not os.path.isfile(p):
            raise MaskError(f"no {label} file at {p!r}")
    entries = [osm_entry(osm, osm_version), roofs_entry(roofs, roofs_release),
               file_entry("nhd", nhd, nhd_version, "NHD High Resolution, HU4 1705 cut to the map box (waterbodies, "
                                                   "areas, flowlines)"),
               file_entry("cdl", cdl, cdl_version(cdl, cdl_ver), "CDL at 10 m, NASS's national file cut to the map "
                                                                  "box; classes 123-124 (developed) read")]
    build_id = build_id or M.build_id()
    folder = M.export_dir(archive, PRODUCT, build_id)
    if os.path.exists(folder):
        raise MaskError(f"{folder} already exists")
    os.makedirs(folder)
    t0 = time.time()
    out = None
    try:
        out = Out(folder)
        for label, fn, path in (("osm", read_osm, osm), ("nhd", read_nhd, nhd), ("roofs", read_roofs, roofs),
                                ("cdl", read_cdl, cdl)):
            t = time.time()
            fn(path, bounds, out, log=log)
            log(f"  {label} done in {time.time() - t:.0f} s")
        log("  sampling buffers: " + ", ".join(f"{k} {v:,}" for k, v in sorted(out.cover_kinds.items())))
        t = time.time()
        out.finish(bounds, log=log)
        log(f"  dissolved in {time.time() - t:.0f} s")
        note = (f"Mask v0 (C6), from raw inputs only, over E {bounds[0]:g}-{bounds[2]:g}, N {bounds[1]:g}-"
                f"{bounds[3]:g}. Exact layers for painting (roofs, roads, paving, water); covered, for sampling, "
                f"grown by {', '.join(f'{k} {v:g} m' for k, v in MR.SAMPLE_BUFFER.items())} and dissolved by what "
                f"in {MR.COVER_BLOCK_M / 1000:g} km blocks. Widths are OpenStreetMap's (width, else lanes, else "
                "class) ⚠️")
        m = M.write(folder, PRODUCT, entries, [w.spec() for w in out.writers], build=build_id,
                    command=command, note=note)
    except BaseException:
        if out is not None:
            out.discard()
        shutil.rmtree(folder, ignore_errors=True)
        raise
    for w in out.writers:
        log(f"  {w.name}: {w.n:,} features, {os.path.getsize(w.path) / 1e6:.1f} MB; " +
            ", ".join(f"{k} {v:,}" for k, v in sorted(w.kinds.items())))
    log(f"mask v0 {build_id}: {folder} in {time.time() - t0:.0f} s")
    return m


# ---- reading it back -----------------------------------------------------------------------------------------------

def check(m):
    """Raise MaskError unless m (a manifest.Manifest) is mask v0 with every layer maskrules names."""
    if m.plugin != PRODUCT:
        raise MaskError(f"{m.folder} is {m.plugin}'s export, not mask v0")
    missing = [n for n in MR.LAYERS if not m.has(n)]
    if missing:
        raise MaskError(f"{PRODUCT}@{m.build} has no {', '.join(missing)} layer(s)")
    return m


def latest(archive, verify=True, hashes=True):
    """The newest mask v0 under the archive, read and checked (manifest.latest), or None when none is built."""
    m = M.latest(archive, PRODUCT, verify=verify, hashes=hashes)
    return None if m is None else check(m)


def exact(target, m, layer, where=None, all_touched=False):
    """One exact layer (roofs, roads, paving, water) burned into a window: a bool array of target.shape."""
    if layer not in MR.PAINT_LAYERS:
        raise MaskError(f"{layer!r} isn't an exact layer ({', '.join(MR.PAINT_LAYERS)})")
    return R.rasterize(target, m.layer(layer), where=where, all_touched=all_touched).astype(bool)


def covered(target, m, what=None, all_touched=False):
    """The sampling mask in a window: True where the ground isn't uncovered (anything in `covered`, or only the
    `what` values given, e.g. ("roof", "water"))."""
    where = None
    if what:
        bad = set(what) - set(MR.SAMPLE_BUFFER)
        if bad:
            raise MaskError(f"no such what: {', '.join(sorted(bad))} ({', '.join(MR.SAMPLE_BUFFER)})")
        where = "what IN (" + ", ".join(f"'{w}'" for w in what) + ")"
    return R.rasterize(target, m.layer(MR.SAMPLE_LAYER), where=where, all_touched=all_touched).astype(bool)


# ---- the command line ----------------------------------------------------------------------------------------------

def _bounds(text):
    v = [float(x) for x in text.split(",")]
    if len(v) != 4 or not (v[2] > v[0] and v[3] > v[1]):
        raise argparse.ArgumentTypeError("west,south,east,north in grid metres")
    return tuple(v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build mask v0 into the archive")
    archive = os.environ.get("TVT_ARCHIVE")
    sources = os.environ.get("TVT_SOURCES")
    b.add_argument("--archive", default=archive, help="default $TVT_ARCHIVE")
    b.add_argument("--osm", help="the valley cut (default $TVT_ARCHIVE/osm/cut/valley.osm.pbf)")
    b.add_argument("--nhd", default=sources and os.path.join(sources, "nhd", "nhd_mapbox.gpkg"),
                   help="NHD's GeoPackage (default $TVT_SOURCES/nhd/nhd_mapbox.gpkg)")
    b.add_argument("--cdl", default=sources and os.path.join(sources, "cdl", "out", "cdl_2025_10m.tif"),
                   help="CDL (default $TVT_SOURCES/cdl/out/cdl_2025_10m.tif)")
    b.add_argument("--roofs", required=True, help="Overture's roofs: the map's buildings.pmtiles (a copy)")
    b.add_argument("--roofs-release", help="Overture's release (default: from buildings.json beside the file)")
    b.add_argument("--osm-version", help="the extract's MD5 (default: from valley.json beside the cut)")
    b.add_argument("--nhd-version", default=NHD_VERSION)
    b.add_argument("--cdl-version", help="CDL's year (default: from the file name)")
    g = b.add_mutually_exclusive_group()
    g.add_argument("--bounds", type=_bounds, help="west,south,east,north in grid metres (default: the whole grid)")
    g.add_argument("--box", help="one of the ten boxes, e.g. d")
    b.add_argument("--build", help="the build id (default: now, UTC)")
    args = ap.parse_args(argv)
    if not args.archive:
        ap.error("give --archive or set TVT_ARCHIVE")
    osm = args.osm or os.path.join(args.archive, "osm", "cut", "valley.osm.pbf")
    bounds = args.bounds or (grid.box(args.box).utm if args.box else None)
    build_id = args.build or (M.build_id(suffix=f"box-{args.box}") if args.box else None)
    command = "python basemap/ground/mask.py " + " ".join(argv if argv is not None else sys.argv[1:])
    try:
        build(args.archive, osm, args.nhd, args.roofs, args.cdl, bounds=bounds, build_id=build_id,
              osm_version=args.osm_version, roofs_release=args.roofs_release, nhd_version=args.nhd_version,
              cdl_ver=args.cdl_version, command=command)
    except (MaskError, M.ManifestError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
