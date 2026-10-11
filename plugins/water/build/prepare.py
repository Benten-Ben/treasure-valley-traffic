"""Prepare the water plugin's two held files for loading (plan P4-data). Worker image (GDAL), no network:

    python plugins/water/build/prepare.py nhd --zip $TVT_SOURCES/nhd/download/NHD_H_1705_HU4_GDB.zip --out DIR
    python plugins/water/build/prepare.py hydroshare --zip $TVT_SOURCES/hydroshare/24a5f761bf4f41fb9b872b130d9d1a3f.zip \
        --out DIR

Each writes into --out (new or empty) one GeoPackage and prepare.json (written last: the input's sha256, each layer's
count, the output's sha256). Then `python3 -m ingest nhd-load --from DIR/nhd.gpkg` and `hydroshare-load --from
DIR/hydroshare.gpkg` (standard library) load them. The worker turns files into files; ingest stays standard library.

**nhd**: USGS NHD High Resolution for HU4 1705 (the File Geodatabase zip, read in place through /vsizip/). Whole
features touching the map box (not clipped), 2D, in NAD83 as published (EPSG:4269):

    flowline     NHDFlowline with NHDFlowlineVAA's stream order, flags and level, and `class`
    waterbody    NHDWaterbody          area         NHDArea          line   NHDLine
    point        NHDPoint              point_event  NHDPointEventFC
    fcode        the FCode lookup table (attributes)
    flow         NHDFlow rows with either end on a kept flowline (attributes): what each flowline flows into

with `ftype_name` and `fcode_desc` from the lookup, and the canal, pipeline and hydrographic-category words of each
FCode. The same shape as the copy cut on Oct 8 (sources/nhd/nhd_mapbox.gpkg), plus `flow`.

**hydroshare**: the Treasure Valley Irrigation System (HydroShare, CC BY 4.0, doi:10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f),
a zipped BagIt bag holding a 7z of one shapefile. Untrusted: the bag is unpacked with bsdtar into a new empty folder
under --out, its payload checked against the bag's MD5 manifest, the 7z unpacked into another new empty folder, and
the shapefile read with OGR. Its lines touching the map box, 2D, WGS 84, become the layer `canal` (id = the record's
number, call_number, name, type). The unpacked folders are removed afterwards. The bag's own XML isn't parsed.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()

BOX = (-117.05, 43.00, -115.95, 43.85)        # the map box (basemap/build.sh): west, south, east, north
GDB = "NHD_H_1705_HU4_GDB.gdb"
NHD_LAYERS = (                                 # (geodatabase layer, output layer, kind)
    ("NHDFlowline", "flowline", "line"),
    ("NHDWaterbody", "waterbody", "polygon"),
    ("NHDArea", "area", "polygon"),
    ("NHDLine", "line", "line"),
    ("NHDPoint", "point", "point"),
    ("NHDPointEventFC", "point_event", "point"),
)
SKIP = {"shape_length", "shape_area", "enabled", "globalid"}
FCODE_ATTRS = ("canalditchtype", "constructionmaterial", "hydrographiccategory", "inundationcontrolstatus",
               "operationalstatus", "pipelinetype", "positionalaccuracy", "relationshiptosurface", "reservoirtype",
               "stage")
VAA = ("streamorder", "streamlevel", "arbolatesumkm", "divergenceflag", "startflag", "terminalflag")
FLOW_CLASS = {460: "stream_river", 336: "canal_ditch", 428: "pipeline", 558: "artificial_path", 334: "connector",
              420: "underground_conduit"}
HYDROSHARE_ID = "24a5f761bf4f41fb9b872b130d9d1a3f"
HYDROSHARE_7Z = "TreasureValleyIrrigationFinal.7z"
HYDROSHARE_FIELDS = (("Call_Numbe", "call_number"), ("Name", "name"), ("Type", "type"))


class PrepareError(RuntimeError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def md5(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def empty_dir(path):
    """--out must be new or empty."""
    if os.path.exists(path) and os.listdir(path):
        raise PrepareError(f"{path} isn't empty")
    os.makedirs(path, exist_ok=True)


def box_geometry(srs):
    ring = ogr.Geometry(ogr.wkbLinearRing)
    w, s, e, n = BOX
    for x, y in ((w, s), (e, s), (e, n), (w, n), (w, s)):
        ring.AddPoint_2D(x, y)
    g = ogr.Geometry(ogr.wkbPolygon)
    g.AddGeometry(ring)
    g.AssignSpatialReference(srs)
    return g


def srs_of(epsg):
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def flat(geom, kind):
    g = geom.Clone()
    g.FlattenTo2D()
    g.SetMeasured(False)
    if kind == "line":
        return ogr.ForceToMultiLineString(g)
    if kind == "polygon":
        return ogr.ForceToMultiPolygon(g)
    return g


def write_manifest(out, data):
    path = os.path.join(out, "prepare.json")
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)
        f.write("\n")
    os.replace(path + ".part", path)


# ---- NHD ---------------------------------------------------------------------------------------------------------

def clean(v):
    return (v.strip() or None) if isinstance(v, str) else v


def prepare_nhd(zip_path, out):
    empty_dir(out)
    src_path = f"/vsizip/{os.path.abspath(zip_path)}/{GDB}"
    src = gdal.OpenEx(src_path, gdal.OF_VECTOR | gdal.OF_READONLY)
    nad83 = srs_of(4269)
    box = box_geometry(nad83)

    fcodes = {}
    t = src.GetLayerByName("NHDFCode")
    names = [t.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(t.GetLayerDefn().GetFieldCount())]
    for f in t:
        fcodes[f.GetField("fcode")] = {n: f.GetField(n) for n in names}
    vaa = {}
    for f in src.GetLayerByName("NHDFlowlineVAA"):
        vaa[f.GetField("permanent_identifier")] = [f.GetField(n) for n in VAA]

    gpkg = os.path.join(out, "nhd.gpkg")
    dst = ogr.GetDriverByName("GPKG").CreateDataSource(gpkg)
    counts, kept_flowlines = {}, set()
    for src_name, name, kind in NHD_LAYERS:
        lyr = src.GetLayerByName(src_name)
        ldef = lyr.GetLayerDefn()
        fields = [ldef.GetFieldDefn(i) for i in range(ldef.GetFieldCount())
                  if ldef.GetFieldDefn(i).GetName().lower() not in SKIP]
        lyr.SetSpatialFilterRect(*BOX)
        rows = []
        for f in lyr:
            g = f.GetGeometryRef()
            if g is None:
                continue
            g = flat(g, kind)
            g.AssignSpatialReference(nad83)
            if not g.Intersects(box):
                continue
            rows.append((g, {fd.GetName(): f.GetField(fd.GetName()) for fd in fields}))
        code_field = "eventtype" if name == "point_event" else "fcode"
        geom_type = {"line": ogr.wkbMultiLineString, "polygon": ogr.wkbMultiPolygon, "point": ogr.wkbPoint}[kind]
        olyr = dst.CreateLayer(name, nad83, geom_type, options=["GEOMETRY_NAME=geom", "FID=fid"])
        for fd in fields:
            olyr.CreateField(fd)
        extra = ["ftype_name", "fcode_desc"] + (["class"] if name == "flowline" else []) + list(FCODE_ATTRS)
        for n in extra:
            olyr.CreateField(ogr.FieldDefn(n, ogr.OFTString))
        if name == "flowline":
            for n in VAA:
                olyr.CreateField(ogr.FieldDefn(n, ogr.OFTReal if n == "arbolatesumkm" else ogr.OFTInteger))
        odef = olyr.GetLayerDefn()
        olyr.StartTransaction()
        for g, attrs in rows:
            of = ogr.Feature(odef)
            for k, v in attrs.items():
                if v is not None:
                    of.SetField(k, v)
            code = attrs.get(code_field)
            rec = fcodes.get(code, {})
            ftype = attrs.get("ftype") or (code // 100 if isinstance(code, int) and code > 1000 else None)
            type_rec = fcodes.get((ftype or 0) * 100)
            if type_rec:
                of.SetField("ftype_name", type_rec["description"])
            if rec:
                of.SetField("fcode_desc", rec["description"])
            for a in FCODE_ATTRS:
                if clean(rec.get(a)):
                    of.SetField(a, clean(rec[a]))
            if name == "flowline":
                of.SetField("class", FLOW_CLASS.get(ftype, "other"))
                pid = attrs.get("permanent_identifier")
                kept_flowlines.add(pid)
                for n, v in zip(VAA, vaa.get(pid) or ()):
                    if v is not None:
                        of.SetField(n, v)
            of.SetGeometry(g)
            olyr.CreateFeature(of)
        olyr.CommitTransaction()
        counts[name] = len(rows)

    t = dst.CreateLayer("fcode", None, ogr.wkbNone)
    for n in names:
        t.CreateField(ogr.FieldDefn(n, ogr.OFTInteger if n == "fcode" else ogr.OFTString))
    t.StartTransaction()
    for code in sorted(fcodes):
        f = ogr.Feature(t.GetLayerDefn())
        for n in names:
            if fcodes[code][n] is not None:
                f.SetField(n, fcodes[code][n])
        t.CreateFeature(f)
    t.CommitTransaction()
    counts["fcode"] = len(fcodes)

    flow = dst.CreateLayer("flow", None, ogr.wkbNone)
    for n, typ in (("from_permanent_identifier", ogr.OFTString), ("to_permanent_identifier", ogr.OFTString),
                   ("direction", ogr.OFTInteger), ("deltalevel", ogr.OFTInteger)):
        flow.CreateField(ogr.FieldDefn(n, typ))
    flow.StartTransaction()
    n_flow = n_all = 0
    for f in src.GetLayerByName("NHDFlow"):
        n_all += 1
        a, b = f.GetField("from_permanent_identifier"), f.GetField("to_permanent_identifier")
        if a in kept_flowlines or b in kept_flowlines:
            of = ogr.Feature(flow.GetLayerDefn())
            for k, v in (("from_permanent_identifier", a), ("to_permanent_identifier", b),
                         ("direction", f.GetField("direction")), ("deltalevel", f.GetField("deltalevel"))):
                if v is not None:
                    of.SetField(k, v)
            flow.CreateFeature(of)
            n_flow += 1
    flow.CommitTransaction()
    counts["flow"] = n_flow

    params = {f.GetField("parametername"): f.GetField("parametervalue")
              for f in src.GetLayerByName("NHDProcessingParameters")}
    dst = None
    src = None
    write_manifest(out, {
        "what": "nhd", "box": list(BOX), "crs": "EPSG:4269 (NAD83), 2D, whole features touching the box",
        "input": {"file": os.path.basename(zip_path), "bytes": os.path.getsize(zip_path), "sha256": sha256(zip_path)},
        "processing_parameters": params, "flow_rows_in_hu4": n_all, "counts": counts,
        "output": {"file": "nhd.gpkg", "bytes": os.path.getsize(gpkg), "sha256": sha256(gpkg)},
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gdal": gdal.__version__})
    return counts


# ---- HydroShare --------------------------------------------------------------------------------------------------

def bsdtar_extract(archive, into):
    """Unpack an archive (zip or 7z) into a new empty folder with bsdtar (libarchive). Refuses absolute paths and
    '..' in member names (bsdtar does by default; -P is never passed)."""
    os.makedirs(into)
    r = subprocess.run(["bsdtar", "-x", "-f", archive, "-C", into, "--no-same-owner", "--no-same-permissions"],
                       capture_output=True, text=True, timeout=600)
    if r.returncode:
        raise PrepareError(f"bsdtar couldn't unpack {os.path.basename(archive)}: {r.stderr.strip()[-300:]}")


def check_bag(bag):
    """The payload against the bag's manifest-md5.txt. Returns {path: md5}."""
    manifest = os.path.join(bag, "manifest-md5.txt")
    if not os.path.isfile(manifest):
        raise PrepareError("the bag has no manifest-md5.txt")
    out = {}
    with open(manifest, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            digest, rel = line.strip().split(None, 1)
            path = os.path.abspath(os.path.join(bag, rel))
            if not path.startswith(os.path.abspath(bag) + os.sep):
                raise PrepareError(f"the bag's manifest names a path outside it: {rel!r}")
            if md5(path) != digest.lower():
                raise PrepareError(f"{rel}: MD5 doesn't match the bag's manifest")
            out[rel] = digest.lower()
    return out


def prepare_hydroshare(zip_path, out):
    empty_dir(out)
    wgs84 = srs_of(4326)
    box = box_geometry(wgs84)
    work = tempfile.mkdtemp(prefix="unpacked-", dir=out)
    try:
        bsdtar_extract(zip_path, os.path.join(work, "bag"))
        bag = os.path.join(work, "bag", HYDROSHARE_ID)
        payload = check_bag(bag)
        seven = os.path.join(bag, "data", "contents", HYDROSHARE_7Z)
        bsdtar_extract(seven, os.path.join(work, "data"))
        shapes = []
        for root, _, files in os.walk(os.path.join(work, "data")):
            shapes += [os.path.join(root, f) for f in files if f.lower().endswith(".shp")]
        if len(shapes) != 1:
            raise PrepareError(f"expected one shapefile in the 7z, found {len(shapes)}")
        src = gdal.OpenEx(shapes[0], gdal.OF_VECTOR | gdal.OF_READONLY)
        lyr = src.GetLayer(0)
        crs = lyr.GetSpatialRef()
        if crs is None or crs.GetAuthorityCode(None) != "4326":
            raise PrepareError(f"the shapefile isn't in WGS 84 (EPSG:4326): {crs.GetName() if crs else None}")
        have = {lyr.GetLayerDefn().GetFieldDefn(i).GetName() for i in range(lyr.GetLayerDefn().GetFieldCount())}
        if missing := [f for f, _ in HYDROSHARE_FIELDS if f not in have]:
            raise PrepareError(f"the shapefile has no field {', '.join(missing)}")
        gpkg = os.path.join(out, "hydroshare.gpkg")
        dst = ogr.GetDriverByName("GPKG").CreateDataSource(gpkg)
        olyr = dst.CreateLayer("canal", wgs84, ogr.wkbMultiLineString, options=["GEOMETRY_NAME=geom", "FID=fid"])
        olyr.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
        for _, n in HYDROSHARE_FIELDS:
            olyr.CreateField(ogr.FieldDefn(n, ogr.OFTString))
        olyr.StartTransaction()
        total = kept = no_geom = 0
        types = {}
        for f in lyr:
            total += 1
            g = f.GetGeometryRef()
            if g is None or g.IsEmpty():
                no_geom += 1
                continue
            g = flat(g, "line")
            g.AssignSpatialReference(wgs84)
            if not g.Intersects(box):
                continue
            of = ogr.Feature(olyr.GetLayerDefn())
            of.SetField("id", f.GetFID())
            for src_name, n in HYDROSHARE_FIELDS:
                v = clean(f.GetField(src_name))
                if v is not None:
                    of.SetField(n, v)
            of.SetGeometry(g)
            olyr.CreateFeature(of)
            kept += 1
            t = clean(f.GetField("Type")) or "(none)"
            types[t] = types.get(t, 0) + 1
        olyr.CommitTransaction()
        dst = None
        src = None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    write_manifest(out, {
        "what": "hydroshare", "box": list(BOX), "crs": "EPSG:4326, 2D, whole lines touching the box",
        "resource": HYDROSHARE_ID, "doi": "10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f", "licence": "CC BY 4.0",
        "input": {"file": os.path.basename(zip_path), "bytes": os.path.getsize(zip_path), "sha256": sha256(zip_path),
                  "bag_payload_md5": payload},
        "counts": {"records": total, "canal": kept, "no_geometry": no_geom, "by_type": dict(sorted(types.items()))},
        "output": {"file": "hydroshare.gpkg", "bytes": os.path.getsize(gpkg), "sha256": sha256(gpkg)},
        "prepared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "gdal": gdal.__version__})
    return {"records": total, "canal": kept}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("nhd", "hydroshare"))
    ap.add_argument("--zip", required=True, help="the held download")
    ap.add_argument("--out", required=True, help="a new or empty folder")
    args = ap.parse_args(argv)
    try:
        counts = (prepare_nhd if args.what == "nhd" else prepare_hydroshare)(args.zip, args.out)
    except PrepareError as err:
        print(f"prepare {args.what}: {err}", file=sys.stderr)
        return 1
    print(f"prepare {args.what}: {json.dumps(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
