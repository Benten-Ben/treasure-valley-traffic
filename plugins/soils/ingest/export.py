"""Export the soil base for the ground: `python3 -m ingest soils-export` (plan C5; basemap/ground/README.md).

Writes $TVT_ARCHIVE/soils/export/<build>/ through the ground's export contract (basemap/ground/manifest.py), with
manifest.json last, from what soils-load and soils-photo-load put in the database (one snapshot, so the files agree):

| Layer | File | What |
|---|---|---|
| `ground` | ground.fgb | every map-unit polygon, whole, in EPSG:32611: `id` (soils.polygon.gid), `ground_type` (soils.ground_type.gid, an integer; 0 for none), `mukey`, `areasymbol` (its survey area: ID001 is Ada County, ID665 Canyon), `misc` (the type's kind of miscellaneous area, or null for a soil; `nodata` is no survey), in that order |
| `ground_types` | ground_types.json | schema `soils.ground_types/1`: each ground type by its gid, with its text id, series, surface texture, misc, landform, surface fragment cover, dry albedo, map units and area in the box |
| `palette` | palette.json | schema `soils.palette/1`, once a photo build is loaded (P2): each ground type's colour, spread and texture from soils.ground_colour, keyed by the same gid |

The ground reads `soils/ground` (basemap/ground/inputs.py USES; without it the ground stays flat) and `soils/palette`
(without it, flat colours per type). The integer `ground_type` is what the painter rasterises, and the palette's key.
A gid is kept while its type exists and never reused, so the files of one export always agree: take the palette and
the ground from the same export. None is a base layer.

misc, the one nullable column, is written last: PostGIS's ST_AsFlatGeobuf writes the column after a null under the
null's index, so a null misc before mukey read back as misc = the mukey and mukey = null.

SSURGO is public domain: the ground layers are republish yes, credit "Soils: USDA NRCS, Soil Survey Geographic
Database (SSURGO)". The palette was measured from NAIP through mask v0 (OpenStreetMap, Overture, NHD, CDL), farm's
crop cover (CSB, CDL, Sentinel-2) and the July Sentinel-2 median, so it carries those inputs (from the photo builds'
records): ODbL-1.0, republish yes. The export is checked against the ground's shape and licence rules before it's left
in place. Standard library plus psycopg (and basemap/ground, which the ingest image carries).
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

# misc, the one column that can be null, comes last. PostGIS's ST_AsFlatGeobuf (3.6.4 on the VM) writes the column
# after a null under the null's index (a running count, not the column's own index), so a null misc before mukey
# read back as misc = the mukey and mukey = null. Last, a null misc is simply left out, which readers take as null.
GROUND_SQL = """
select ST_AsFlatGeobuf(q, true, 'geom') from (
  select p.gid as id, coalesce(g.gid, 0)::int as ground_type, p.mukey, p.areasymbol, g.misc,
         ST_Transform(p.geom, 32611) as geom
  from soils.polygon p join soils.map_unit m on m.mukey = p.mukey
  left join soils.ground_type g on g.id = m.ground_type
  order by p.gid) q"""
# landform: the landform of the type's map units' dominant components, the one covering most of the box (ties by
# name); P2's texture fallback matches types on texture class and landform.
TYPES_SQL = """
with lf as (
  select m.ground_type, c.landform, sum(m.area_in_box_ha) as ha
  from soils.map_unit m join soils.component c on c.cokey = m.dom_cokey
  where m.ground_type is not null and c.landform is not null
  group by 1, 2
), best as (
  select distinct on (ground_type) ground_type, landform from lf order by ground_type, ha desc, landform
)
select g.gid, g.id, g.series, g.texture, g.texcl, g.modifier, g.misc, b.landform, g.frag_cover_pct, g.albedo_dry,
       g.n_mapunits, g.area_ha
from soils.ground_type g left join best b on b.ground_type = g.id order by g.gid"""
TYPE_FIELDS = ("gid", "id", "series", "texture", "texcl", "modifier", "misc", "landform", "frag_cover_pct",
               "albedo_dry", "n_mapunits", "area_ha")


PALETTE_SCHEMA = "soils.palette/1"
# Each ground type with its colour from soils.ground_colour (the newest finished photo build that has it), and the
# flight days its own build measured it on.
PALETTE_SQL = """
select g.gid, g.id, g.misc, g.modifier, g.frag_cover_pct, c.build_id, c.photo, c.mask, c.n_px, c.n_polygons,
       c.lab_med, c.lab_cov, c.l_p10, c.l_p90, c.oct_l, c.oct_c, c.fallback,
       (select coalesce(array_agg(s.flight::text order by s.flight), '{}') from soils.photo_stats s
        where s.build_id = c.build_id and s.level = 'ground_type' and s.key = g.id and s.flight is not null
          and s.photo = c.photo and s.mask = c.mask) as flights
from soils.ground_type g left join soils.ground_colour c on c.ground_type = g.id
order by g.gid"""
PALETTE_FIELDS = ("gid", "id", "misc", "modifier", "frag_cover_pct", "build", "photo", "mask", "n_px", "n_polygons",
                  "lab_med", "lab_cov", "l_p10", "l_p90", "oct_l", "oct_c", "fallback", "flights")
PALETTE_ABOUT = {
    "status": "measured: from the type's own uncovered ground (at least 20,000 pixels of 0.6 m in 3 polygons); "
              "series, texture, albedo: borrowed (the same series; the same texture class and landform; L from the "
              "dry albedo with chroma and hue from texture-class peers), so a flat type colour, labelled; none: no "
              "colour (paint it flat and say so)",
    "lab_med": "OKLab median (L, a, b) of the photo's pixels, read as sRGB; raw, never styled",
    "lab_cov": "OKLab covariance, upper triangle (LL, La, Lb, aa, ab, bb): the spread a pixel is measured against "
               "(Mahalanobis) for the photo-variation pass",
    "l_p10": "L's 10th percentile", "l_p90": "L's 90th percentile",
    "oct_l": "texture energy of L at 1.2, 2.4, 4.8, 9.6 and 19.2 m: the mean square of the masked difference of "
             "Gaussians S(s/2) - S(s) (plugins/soils/build/photo.py octave_energy)",
    "oct_c": "the same for OKLab chroma",
    "n_px": "the type's own sampled pixels (0.6 m); n_polygons: its polygons with at least 500 of them",
    "flights": "the NAIP flight days the type's own pixels were flown",
    "modifier": "SSURGO's surface-texture modifier (gravelly, cobbly, stony, ...): stones close up, which a 0.3 m "
                "photo can't resolve; frag_cover_pct: surface fragment cover",
}


class ExportError(ValueError):
    pass


def palette_rows(rows):
    """palette.json's types from PALETTE_SQL's rows."""
    out = []
    for r in rows:
        t = dict(zip(PALETTE_FIELDS, r))
        fallback = t.pop("fallback")
        t["status"] = "none" if t["build"] is None else (fallback or "measured")
        if t["frag_cover_pct"] is not None:
            t["frag_cover_pct"] = round(float(t["frag_cover_pct"]), 2)
        for k in ("lab_med", "lab_cov", "oct_l", "oct_c"):
            if t[k] is not None:
                t[k] = [None if v is None else float(v) for v in t[k]]
        for k in ("l_p10", "l_p90"):
            if t[k] is not None:
                t[k] = float(t[k])
        t["flights"] = list(t["flights"] or [])
        out.append(t)
    return out


def photo_inputs(builds):
    """The photo builds' inputs as one manifest list: by name, the newest build's entry, with the other builds'
    versions added when they differ."""
    out = {}
    for b in builds:
        for i in (b["params"] or {}).get("inputs", []):
            e = out.get(i["name"])
            if e is None:
                out[i["name"]] = {k: v for k, v in i.items() if k in INPUT_KEYS}
            elif i.get("version") and i.get("version") != e.get("version"):
                e["version"] = f"{e.get('version', '')}; {i['version']}".strip("; ")
                e.pop("sha256", None)
    return list(out.values())


INPUT_KEYS = ("name", "licence", "republish", "credit", "source", "version", "url", "doi", "sha256", "retrieved",
              "note")


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
    palette = palette_rows(conn.execute(PALETTE_SQL).fetchall())
    build_ids = sorted({t["build"] for t in palette if t["build"]})
    builds = [dict(zip(("build_id", "finished_at", "params", "counts"), r)) for r in conn.execute(
        """select build_id, finished_at, params, counts from soils.build where build_id = any(%s)
           order by finished_at desc, build_id desc""", (build_ids,)).fetchall()] if build_ids else []
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
        if builds:
            p_inputs = [i for i in photo_inputs(builds) if i["name"] != "ssurgo"]
            doc = {"schema": PALETTE_SCHEMA, "colour_space": "OKLab", "about": PALETTE_ABOUT,
                   "builds": [{"build": b["build_id"], "finished": b["finished_at"].isoformat(),
                               "photo": b["params"].get("photo"), "mask": b["params"].get("mask"),
                               "octaves_m": b["params"].get("octaves_m"), "rules": b["params"].get("rules"),
                               "calibration": (b["counts"] or {}).get("calibration"),
                               "flight_days": (b["counts"] or {}).get("flight_days")} for b in builds],
                   "types": palette}
            with open(os.path.join(folder, "palette.json"), "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=1, ensure_ascii=False)
                f.write("\n")
            inputs.extend(p_inputs)
        layers = [
            {"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "inputs": ["ssurgo"], "base": False,
             "title": "Soil map units with their ground types",
             "note": "ground_type: soils.ground_type.gid (0 none), the key of ground_types.json and P2's palette; "
                     "areasymbol: the survey area (ID001 Ada County, ID665 Canyon; their shared edge is the county "
                     "line P2 splits the two NAIP mosaics on); misc: water, urban, rock, badland, rubble, pits, "
                     "other, or nodata (not surveyed); null for a soil. Polygons are whole, not clipped to the box"},
            {"name": "ground_types", "file": "ground_types.json", "format": "JSON", "schema": TYPES_SCHEMA,
             "inputs": ["ssurgo"], "base": False, "title": "The ground types, by their integer key"},
        ]
        if builds:
            layers.append({"name": "palette", "file": "palette.json", "format": "JSON", "schema": PALETTE_SCHEMA,
                           "inputs": ["ssurgo"] + [i["name"] for i in p_inputs], "base": False,
                           "title": "Each ground type's colour, spread and texture, measured from NAIP 2025",
                           "note": "photo builds " + ", ".join(b["build_id"] for b in builds) + "; keyed by "
                                   "ground_type gid, as ground.fgb"})
        m = M.write(folder, "soils", inputs=inputs, layers=layers, command=COMMAND,
                    note=f"soils loads {', '.join(loads)}; {len(types)} ground types"
                         + (f"; photo builds {', '.join(build_ids)}" if builds else ""))
        # The ground's own check: the shape it reads, and public inputs only (C17).
        plan = GI.resolve({"soils": m})
        for ref in ("soils/ground",) + (("soils/palette",) if builds else ()):
            if plan.choice(ref).fallback:
                raise ExportError(f"the ground wouldn't read {ref}: {plan.choice(ref).reason}")
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
