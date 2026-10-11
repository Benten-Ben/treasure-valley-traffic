"""Export the crop fields for the ground: `python3 -m ingest farm-export [--build DIR]` (plan C5, C7).

Writes $TVT_ARCHIVE/farm/export/<build>/ through the ground's export contract (basemap/ground/manifest.py), with
manifest.json last:

| Layer | File | What |
|---|---|---|
| `crop_cover` | crop_cover.tif | the worker build's GeoTIFF on the ground's 10 m grid: bands group, state, confidence |
| `fields` | fields.fgb | every current field (EPSG:32611): id (farm.field.id), csbid, crop_group (crop_cover's group code, 0 when not crop), cdl (the newest year's code), bearing (degrees clockwise from grid north, 0-180: the row direction), acres |

Both are public: CSB and CDL are public domain, Sentinel-2 is Copernicus (credit "Contains modified Copernicus Sentinel
data 2025"). The ground reads them as `farm/crop_cover` and `farm/fields` (basemap/ground/inputs.py USES); the export
is checked against the ground's shape and licence rules before it's left in place. Neither is a base layer.

The build defaults to the one the current fields' stats came from (farm-fields-load), in $TVT_ARCHIVE/farm/build/.
Standard library plus psycopg (and basemap/ground, which the ingest image carries).
"""

import argparse
import json
import os
import shutil
import sys

from basemap.ground import inputs as GI
from basemap.ground import manifest as M

from . import classes as C
from .fields_load import BuildError, read_build
from .sources import nass_cdl, nass_csb

COMMAND = "python3 -m ingest farm-export"
BAND_VALUES = {
    "group": {str(v): k for k, v in C.COVER_CODES.items()},
    "state": {"0": "none", "1": "green", "2": "growing", "3": "bare or harvested"},
    "confidence": {"0": "none", "1": "field interior", "2": "field edge band, the CDL agrees",
                   "3": "CDL crop cluster of at least 0.5 ha outside every field"},
}
BAND_ABOUT = {
    "group": "the crop group in the cover year: the field's CSB code inside fields, the CDL pixel's in clusters",
    "state": "July NDVI median (Sentinel-2) smoothed over 3 x 3 cells: green >= 0.6, growing >= 0.3, else bare",
    "confidence": "interior: the cell and its neighbours in one field; edge: cells a field touches, kept where the "
                  "CDL agrees; cluster: CDL crop pixels outside fields, 8-connected, 0.5 ha or more",
}
FIELDS_SQL = """
select ST_AsFlatGeobuf(q, true, 'geom') from (
  select f.id, f.field_id as csbid,
         (case f.group_now {cases} else 0 end)::smallint as crop_group,
         f.crops[cardinality(f.crops)]::smallint as cdl,
         coalesce(f.bearing, 0)::float8 as bearing, f.acres::float8 as acres,
         ST_Transform(f.geom, 32611) as geom
  from farm.field f where f.valid_to is null order by f.id) q"""


def default_build(conn, archive):
    row = conn.execute("""select build_id, count(*) from farm.field where valid_to is null and build_id is not null
                          group by 1 order by 2 desc limit 1""").fetchone()
    if row is None:
        raise BuildError("no current field has a build's stats yet (farm-fields-load first)")
    return os.path.join(archive, "farm", "build", row[0])


def export(conn, archive, build_dir=None, build=None):
    """Write an export folder and its manifest. Returns the Manifest."""
    build_dir = build_dir or default_build(conn, archive)
    b, _ = read_build(build_dir)
    loaded = conn.execute("select count(*) from farm.field where valid_to is null and build_id = %s",
                          (b["build_id"],)).fetchone()[0]
    if not loaded:
        raise BuildError(f"build {b['build_id']} isn't the one loaded (farm-fields-load it first)")
    edition, first, last, sha = conn.execute(
        "select edition, first_year, last_year, sha256 from farm.edition order by last_year desc, loaded_at desc "
        "limit 1").fetchone()
    if b["inputs"]["csb"]["sha256"] != sha:
        raise BuildError(f"build {b['build_id']} was made from another CSB file than {edition}'s")
    cover_year, july_year = b["cover_year"], b["july_year"]
    cdl_in = b["inputs"]["cdl"][str(cover_year)]

    folder = M.export_dir(archive, "farm", build or M.build_id())
    os.makedirs(folder)
    try:
        shutil.copyfile(os.path.join(build_dir, "crop_cover.tif"), os.path.join(folder, "crop_cover.tif"))
        cases = " ".join(f"when '{g}' then {code}" for g, code in C.COVER_CODES.items() if code)
        blob = conn.execute(FIELDS_SQL.format(cases=cases)).fetchone()[0]
        if not blob:
            raise BuildError("no current fields to export")
        with open(os.path.join(folder, "fields.fgb"), "wb") as f:
            f.write(bytes(blob))
        g = b["grid"]
        inputs = [
            {"name": "csb", "licence": "public-domain", "republish": "yes",
             "credit": f"{nass_csb.SOURCE['credit']} {first}-{last}", "source": f"farm/{nass_csb.SOURCE['name']}",
             "version": edition, "sha256": sha, "url": nass_csb.SOURCE["url"]},
            {"name": "cdl", "licence": "public-domain", "republish": "yes",
             "credit": f"{nass_cdl.SOURCE['credit']} {cover_year}", "source": f"farm/{nass_cdl.SOURCE['name']}",
             "version": str(cover_year), "sha256": cdl_in["sha256"], "url": nass_cdl.SOURCE["url"]},
            {"name": "sentinel-2", "licence": "Copernicus", "republish": "yes",
             "credit": f"Contains modified Copernicus Sentinel data {july_year}",
             "version": f"July {july_year} NDVI median", "sha256": b["inputs"]["ndvi"]["sha256"]},
        ]
        layers = [
            {"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": g["crs"],
             "grid": {"res": g["res"], "west": g["west"], "north": g["north"], "width": g["width"],
                      "height": g["height"]},
             "bands": [{"name": n, "type": "uint8", "values": BAND_VALUES[n], "about": BAND_ABOUT[n]}
                       for n in ("group", "state", "confidence")],
             "inputs": ["csb", "cdl", "sentinel-2"], "licence": "Copernicus", "base": False,
             "title": f"Crop cover, {cover_year} crops, July {july_year} state",
             "note": f"farm build {b['build_id']}"},
            {"name": "fields", "file": "fields.fgb", "format": "FlatGeobuf", "inputs": ["csb"], "base": False,
             "title": f"Crop fields ({edition}) with their row bearing",
             "note": "bearing: the long axis of the field's minimum-area rectangle, degrees clockwise from grid "
                     "north (EPSG:32611), 0-180; crop_group: crop_cover's group codes"},
        ]
        m = M.write(folder, "farm", inputs=inputs, layers=layers, command=COMMAND,
                    note=f"CSB {edition}, CDL {cover_year}, Sentinel-2 July {july_year}; build {b['build_id']}")
        # The ground's own check: the shapes it reads, and public inputs only (C17).
        plan = GI.resolve({"farm": m})
        for ref in ("farm/crop_cover", "farm/fields"):
            if plan.choice(ref).fallback:
                raise BuildError(f"the ground wouldn't read {ref}: {plan.choice(ref).reason}")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest farm-export", description=__doc__.split("\n")[0])
    ap.add_argument("--build", help="a build folder (default: the one farm-fields-load loaded)")
    args = ap.parse_args(argv)
    archive = os.environ.get("TVT_ARCHIVE")
    if not archive or not os.path.isdir(archive):
        print("farm-export: set TVT_ARCHIVE to the archive folder", file=sys.stderr)
        return 1
    try:
        from ingest import db
        with db.connect() as conn:
            m = export(conn, archive, args.build)
    except (BuildError, M.ManifestError, GI.InputError, OSError) as err:
        print(f"farm-export: {err}", file=sys.stderr, flush=True)
        return 1
    print(f"farm-export: {m.folder}: " + ", ".join(
        f"{lay.name} ({lay['bytes']:,} bytes{', %d features' % lay['features'] if lay['format'] == 'FlatGeobuf' else ''})"
        for lay in m.layers), flush=True)
    print(json.dumps({"licence": [lay["licence"] for lay in m.layers], "republish": m.republish}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
