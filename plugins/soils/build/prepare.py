"""Prepare the Web Soil Survey packages for soils-load (plan P1-data; the soils design, build step 1). Worker image (GDAL):

    python plugins/soils/build/prepare.py --sources $TVT_SOURCES/ssurgo/data --out $TVT_ARCHIVE/soils/prepared/<stamp>
    python plugins/soils/build/prepare.py --sources DIR --areas ID001,ID665 --out DIR

--sources holds one folder per survey area, as unzipped from the Web Soil Survey (<AREA>/spatial/soilmu_a_<area>.shp
and <AREA>/tabular/*.txt, SSURGO 2.3.3). For each area it keeps the map-unit polygons touching the map box, whole, and
the tabular rows of their map units, and writes into --out (new or empty):

    polygons.geojsonl     one Feature per line, WGS 84 (EPSG:4326, 7 decimals): {id, areasymbol, fid, mukey, musym}
    tabular/<table>.csv   every column of mapunit, muaggatt, component, corestrictions, cosurffrags, copmgrp, copm,
                          cogeomordesc, coecoclass, cocropyld, chorizon, chtexturegrp, chtexture and chtexturemod for
                          those map units, with a header row (`areasymbol`, then SSURGO's column names)
    prepare.json          the areas (symbol, name, saverest, version, scale, source URL, counts), each output file's
                          sha256 and rows, each input file's sha256; written last

The interpretations (cinterp) and every other table are left out. Then `python3 -m ingest soils-load --from <out>`
(ingest/load.py, standard library) loads it. The worker turns files into files, and ingest stays standard library
(the trees pattern). It needs about 0.5 GB of memory (--memory 1g) and a few minutes for the ten areas.

The shapefiles are in WGS 84 already; nothing is reprojected here (areas are measured on the ellipsoid in PostGIS).
"""

import argparse
import csv
import glob
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from osgeo import gdal, ogr

gdal.UseExceptions()
ogr.UseExceptions()
csv.field_size_limit(1 << 30)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))   # the repository, for plugins.soils
from plugins.soils.ingest import package  # noqa: E402

BOX = package.BOX
PRECISION = 7               # decimals of a degree in polygons.geojsonl: about 1 cm
WSS_URL = "https://websoilsurvey.sc.egov.usda.gov/DSD/Download/Cache/SSA/wss_SSA_{area}_%5B{date}%5D.zip"

# Which rows of each table to keep: (table, its key column, the table and column whose kept values it follows).
# Tables are read in this order, so each follows one already read.
KEEP = (
    ("mapunit", "mukey", "polygons"),
    ("muaggatt", "mukey", "polygons"),
    ("component", "mukey", "polygons"),
    ("corestrictions", "cokey", "component.cokey"),
    ("cosurffrags", "cokey", "component.cokey"),
    ("copmgrp", "cokey", "component.cokey"),
    ("copm", "copmgrpkey", "copmgrp.copmgrpkey"),
    ("cogeomordesc", "cokey", "component.cokey"),
    ("coecoclass", "cokey", "component.cokey"),
    ("cocropyld", "cokey", "component.cokey"),
    ("chorizon", "cokey", "component.cokey"),
    ("chtexturegrp", "chkey", "chorizon.chkey"),
    ("chtexture", "chtgkey", "chtexturegrp.chtgkey"),
    ("chtexturemod", "chtkey", "chtexture.chtkey"),
)
assert {t for t, _, _ in KEEP} == set(package.TABLES)


def file_sha256(path):
    return package.sha256(path)


class Tabular:
    """One survey area's SSURGO tables: pipe-delimited text, no header; column names from mdstattabcols (mstabcol.txt)
    and file names from mdstattabs (mstab.txt)."""

    def __init__(self, folder):
        self.folder = folder
        self.read = []                      # the files read, for prepare.json's inputs
        cols = defaultdict(list)
        for r in self.rows_of("mstabcol.txt"):
            cols[r[0]].append((int(r[1]), r[2]))
        self.columns = {t: [c for _, c in sorted(v)] for t, v in cols.items()}
        self.files = {r[0]: r[4] for r in self.rows_of("mstab.txt")}

    def rows_of(self, name):
        path = os.path.join(self.folder, name)
        self.read.append(path)
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.reader(f, delimiter="|", quotechar='"'):
                yield [v.strip() for v in row]

    def __call__(self, table):
        """Rows of a table as dicts. A missing file is an empty table (WSS leaves out some)."""
        names = self.columns[table]
        path = os.path.join(self.folder, self.files[table] + ".txt")
        if not os.path.exists(path):
            return
        for row in self.rows_of(self.files[table] + ".txt"):
            if len(row) != len(names):
                raise ValueError(f"{path}: a row has {len(row)} fields, {table} has {len(names)} columns")
            yield dict(zip(names, row))


def box_geometry():
    w, s, e, n = BOX
    return ogr.CreateGeometryFromWkt(f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))")


def touches_box(g, box):
    """Inside the box, or overlapping it with some area (a shared edge alone doesn't count)."""
    if box.Contains(g):
        return True
    if not g.Intersects(box):
        return False
    try:
        return g.Intersection(box).GetArea() > 0
    except RuntimeError:                       # an invalid polygon (GEOS refuses it): measure its repaired shape
        return g.Buffer(0).Intersection(box).GetArea() > 0


def find_areas(sources, only=None):
    """{symbol: folder} for each survey area under sources (a folder with spatial/soilmu_a_<area>.shp)."""
    out = {}
    for shp in sorted(glob.glob(os.path.join(sources, "*", "spatial", "soilmu_a_*.shp"))):
        folder = os.path.dirname(os.path.dirname(shp))
        sym = os.path.basename(shp)[len("soilmu_a_"):-len(".shp")].upper()
        out[sym] = folder
    if only:
        if missing := sorted(set(only) - set(out)):
            raise SystemExit(f"prepare: no survey area {', '.join(missing)} under {sources}")
        out = {k: v for k, v in out.items() if k in only}
    if not out:
        raise SystemExit(f"prepare: no survey areas (<AREA>/spatial/soilmu_a_<area>.shp) under {sources}")
    return out


def prepare(sources, out, only=None, log=print):
    areas = find_areas(sources, only)
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit(f"prepare: {out} isn't empty")
    os.makedirs(os.path.join(out, "tabular"), exist_ok=True)
    box = box_geometry()
    inputs, meta_areas = {}, []
    writers, handles, rows_out, headers = {}, {}, defaultdict(int), {}

    def writer(table, columns):
        if table not in writers:
            f = open(os.path.join(out, "tabular", f"{table}.csv"), "w", newline="", encoding="utf-8")
            handles[table] = f
            writers[table] = csv.writer(f)
            headers[table] = ["areasymbol"] + columns
            writers[table].writerow(headers[table])
        elif headers[table] != ["areasymbol"] + columns:
            raise SystemExit(f"prepare: {table} has other columns in another survey area (a different SSURGO version?)")
        return writers[table]

    polygons_path = os.path.join(out, package.POLYGONS)
    with open(polygons_path, "w", encoding="utf-8") as poly_out:
        for sym, folder in areas.items():
            tab = Tabular(os.path.join(folder, "tabular"))
            cat = next(tab("sacatalog"))
            legend = next(tab("legend"))
            rest = package.saverest(cat["saverest"])

            # Polygons touching the box, whole.
            shp = os.path.join(folder, "spatial", f"soilmu_a_{sym.lower()}.shp")
            for ext in (".shp", ".shx", ".dbf", ".prj"):
                p = shp[:-4] + ext
                if os.path.exists(p):
                    inputs[os.path.relpath(p, sources)] = file_sha256(p)
            ds = ogr.Open(shp)
            layer = ds.GetLayer(0)
            keep = {"polygons": set()}
            n_poly = 0
            for f in layer:
                g = f.GetGeometryRef()
                if g is None or not touches_box(g, box):
                    continue
                mukey = str(f.GetField("MUKEY")).strip()
                g = ogr.ForceToMultiPolygon(g.Clone())
                feat = {"type": "Feature",
                        "properties": {"id": f"{sym}:{f.GetFID()}", "areasymbol": sym, "fid": f.GetFID(),
                                       "mukey": mukey, "musym": (f.GetField("MUSYM") or "").strip() or None},
                        "geometry": json.loads(g.ExportToJson([f"COORDINATE_PRECISION={PRECISION}"]))}
                poly_out.write(json.dumps(feat, separators=(",", ":")) + "\n")
                keep["polygons"].add(mukey)
                n_poly += 1
            ds = None

            # The tables, each following the keys kept before it.
            counts = {}
            for table, key, follows in KEEP:
                allowed = keep[follows]
                columns = tab.columns[table]
                w = writer(table, columns)
                kept = defaultdict(set)
                n = 0
                for r in tab(table):
                    if r[key] not in allowed:
                        continue
                    w.writerow([sym] + [r[c] for c in columns])
                    for c in columns:
                        if c.endswith("key"):
                            kept[c].add(r[c])
                    n += 1
                for c, values in kept.items():
                    keep[f"{table}.{c}"] = values
                for c in columns:                      # a key with no rows kept is an empty set, not missing
                    if c.endswith("key"):
                        keep.setdefault(f"{table}.{c}", set())
                rows_out[table] += n
                counts[table] = n
            if missing := keep["polygons"] - keep["mapunit.mukey"]:
                raise SystemExit(f"prepare: {sym}: polygons of map units not in its mapunit table: "
                                 f"{', '.join(sorted(missing)[:5])}")
            for path in tab.read:
                inputs.setdefault(os.path.relpath(path, sources), file_sha256(path))
            meta_areas.append({
                "areasymbol": sym, "areaname": cat["areaname"] or legend["areaname"], "saverest": rest,
                "saversion": package.whole(cat["saversion"]), "tabularversion": package.whole(cat["tabularversion"]),
                "scale": package.whole(legend["projectscale"]),
                "source_url": WSS_URL.format(area=sym, date=rest[:10]),
                "polygons": n_poly, "mapunits": counts["mapunit"], "components": counts["component"],
                "horizons": counts["chorizon"]})
            log(f"prepare: {sym} ({cat['areaname']}, {rest}): {n_poly} polygons, {counts['mapunit']} map units, "
                f"{counts['component']} components, {counts['chorizon']} horizons")
    for f in handles.values():
        f.close()

    files = {package.POLYGONS: {"sha256": file_sha256(polygons_path),
                                "rows": sum(a["polygons"] for a in meta_areas)}}
    for table in package.TABLES:
        files[f"tabular/{table}.csv"] = {"sha256": file_sha256(os.path.join(out, "tabular", f"{table}.csv")),
                                         "rows": rows_out[table]}
    meta = {"format": package.FORMAT, "made_by": "plugins/soils/build/prepare.py",
            "made_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "gdal": gdal.__version__,
            "box": list(BOX), "areas": meta_areas, "files": files, "inputs": dict(sorted(inputs.items()))}
    tmp = os.path.join(out, package.MANIFEST + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    os.replace(tmp, os.path.join(out, package.MANIFEST))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default = os.path.join(os.environ["TVT_SOURCES"], "ssurgo", "data") if os.environ.get("TVT_SOURCES") else None
    ap.add_argument("--sources", default=default, required=default is None,
                    help="one folder per survey area, as unzipped (default $TVT_SOURCES/ssurgo/data)")
    ap.add_argument("--out", required=True, help="a new or empty folder")
    ap.add_argument("--areas", help="only these survey areas, comma-separated (e.g. ID001,ID665)")
    args = ap.parse_args(argv)
    only = [a.strip().upper() for a in args.areas.split(",") if a.strip()] if args.areas else None
    meta = prepare(args.sources, args.out, only)
    total = sum(a["polygons"] for a in meta["areas"])
    print(f"prepare: {len(meta['areas'])} survey areas, {total} polygons -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
