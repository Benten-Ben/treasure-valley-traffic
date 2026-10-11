"""Export the soil base for the ground: `python3 -m ingest soils-export` (plan C5; basemap/ground/README.md).

Writes $TVT_ARCHIVE/soils/export/<build>/ through the ground's export contract (basemap/ground/manifest.py), with
manifest.json last, from what soils-load put in the database (one snapshot, so the two files agree):

| Layer | File | What |
|---|---|---|
| `ground` | ground.fgb | every map-unit polygon, whole, in EPSG:32611: `id` (soils.polygon.gid), `ground_type` (soils.ground_type.gid, an integer; 0 for none), `misc` (the type's kind of miscellaneous area, or null for a soil; `nodata` is no survey), `mukey` |
| `ground_types` | ground_types.json | schema `soils.ground_types/1`: each ground type by its gid, with its text id, series, surface texture, misc, surface fragment cover, dry albedo, map units and area in the box |

The ground reads `soils/ground` (basemap/ground/inputs.py USES): without it the ground stays flat. The integer
`ground_type` is what the painter rasterises, and the key that P2's palette.json (`soils.palette/1`, added to this
export by P2) uses too. A gid is kept while its type exists and never reused, so the files of one export always agree;
take the palette and the ground from the same export. Neither layer is a base layer.

SSURGO is public domain: republish yes, credit "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)". The
export is checked against the ground's shape and licence rules before it's left in place. Standard library plus
psycopg (and basemap/ground, which the ingest image carries).
"""

import argparse
import json
import os
import shutil
import sys

from basemap.ground import inputs as GI
from basemap.ground import manifest as M

from .sources import ssurgo

COMMAND = "python3 -m ingest soils-export"
TYPES_SCHEMA = "soils.ground_types/1"

GROUND_SQL = """
select ST_AsFlatGeobuf(q, true, 'geom') from (
  select p.gid as id, coalesce(g.gid, 0)::int as ground_type, g.misc, p.mukey, ST_Transform(p.geom, 32611) as geom
  from soils.polygon p join soils.map_unit m on m.mukey = p.mukey
  left join soils.ground_type g on g.id = m.ground_type
  order by p.gid) q"""
TYPES_SQL = """
select gid, id, series, texture, texcl, modifier, misc, frag_cover_pct, albedo_dry, n_mapunits, area_ha
from soils.ground_type order by gid"""
TYPE_FIELDS = ("gid", "id", "series", "texture", "texcl", "modifier", "misc", "frag_cover_pct", "albedo_dry",
               "n_mapunits", "area_ha")


class ExportError(ValueError):
    pass


def ground_types(rows):
    """ground_types.json's list from TYPES_SQL's rows: numbers rounded for a small, stable file."""
    out = []
    for r in rows:
        t = dict(zip(TYPE_FIELDS, r))
        for k, places in (("frag_cover_pct", 2), ("albedo_dry", 3), ("area_ha", 1)):
            if t[k] is not None:
                t[k] = round(float(t[k]), places)
        out.append(t)
    return out


def export(conn, archive, build=None):
    """Write an export folder and its manifest from the database. Returns the Manifest. Reads in one snapshot: a
    read-only repeatable-read transaction of its own, or the caller's when one is open (it's left open)."""
    from psycopg import pq
    own = conn.info.transaction_status == pq.TransactionStatus.IDLE
    if own:
        conn.execute("set transaction isolation level repeatable read, read only")
    areas = conn.execute("""select areasymbol, saverest, build_id from soils.survey_area
                            order by areasymbol""").fetchall()
    if not areas:
        raise ExportError("soils has no survey areas loaded (soils-load first)")
    blob = conn.execute(GROUND_SQL).fetchone()[0]
    if not blob:
        raise ExportError("soils has no polygons to export")
    types = ground_types(conn.execute(TYPES_SQL).fetchall())
    if own:
        conn.rollback()                           # read only: end the snapshot

    loads = sorted({a[2] for a in areas})
    newest = max(a[1] for a in areas)
    folder = M.export_dir(archive, "soils", build or M.build_id())
    os.makedirs(folder)
    try:
        with open(os.path.join(folder, "ground.fgb"), "wb") as f:
            f.write(bytes(blob))
        with open(os.path.join(folder, "ground_types.json"), "w", encoding="utf-8") as f:
            json.dump({"schema": TYPES_SCHEMA, "loads": loads, "types": types}, f, indent=1, ensure_ascii=False)
            f.write("\n")
        inputs = [{
            "name": "ssurgo", "licence": "public-domain", "republish": "yes", "credit": ssurgo.SOURCE["credit"],
            "source": f"soils/{ssurgo.SOURCE['name']}", "url": ssurgo.SOURCE["url"],
            "version": f"{len(areas)} survey areas, versions to {newest:%Y-%m-%d}",
            "note": "saverest: " + ", ".join(f"{a} {s:%Y-%m-%d %H:%M:%S}" for a, s, _ in areas)}]
        layers = [
            {"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "inputs": ["ssurgo"], "base": False,
             "title": "Soil map units with their ground types",
             "note": "ground_type: soils.ground_type.gid (0 none), the key of ground_types.json and P2's palette; "
                     "misc: water, urban, rock, badland, rubble, pits, other, or nodata (not surveyed); null for a "
                     "soil. Polygons are whole, not clipped to the box"},
            {"name": "ground_types", "file": "ground_types.json", "format": "JSON", "schema": TYPES_SCHEMA,
             "inputs": ["ssurgo"], "base": False, "title": "The ground types, by their integer key"},
        ]
        m = M.write(folder, "soils", inputs=inputs, layers=layers, command=COMMAND,
                    note=f"soils loads {', '.join(loads)}; {len(types)} ground types")
        # The ground's own check: the shape it reads, and public inputs only (C17).
        choice = GI.resolve({"soils": m}).choice("soils/ground")
        if choice.fallback:
            raise ExportError(f"the ground wouldn't read soils/ground: {choice.reason}")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(prog=COMMAND, description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    archive = os.environ.get("TVT_ARCHIVE")
    if not archive or not os.path.isdir(archive):
        print("soils-export: set TVT_ARCHIVE to the archive folder", file=sys.stderr)
        return 1
    try:
        from ingest import db
        with db.connect() as conn:
            m = export(conn, archive)
    except (ExportError, M.ManifestError, GI.InputError, OSError) as err:
        print(f"soils-export: {err}", file=sys.stderr, flush=True)
        return 1
    print(f"soils-export: {m.folder}: " + ", ".join(
        f"{lay.name} ({lay['bytes']:,} bytes{', %d features' % lay['features'] if lay['format'] == 'FlatGeobuf' else ''})"
        for lay in m.layers), flush=True)
    print(json.dumps({"licence": [lay["licence"] for lay in m.layers], "republish": m.republish}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
