"""Export the real-width roads for the base bake: `python3 -m ingest roads-export` (landscape sprint P7; plan C5,
C17, §3.2, §3.5; basemap/landscape/README.md).

Writes $TVT_ARCHIVE/roads/export/<build>/ through the export contract (basemap/ground/manifest.py), manifest.json
last, from the current roads build (roads.build where current). Every layer is a base layer: FlatGeobuf in
EPSG:32611 with an integer `id` (the build's own: cards key on the way and ACHD's segment, never on it) and, where
features start at different zooms, an integer `minzoom`. The bake names each source-layer `roads.<layer>`.

| Layer | Zooms | Geometry | Fields |
|---|---|---|---|
| `lines` | 14-16 | LineString | the pieces' centrelines: `class` (highway=*), `w` (the pavement's width, m), `material`, `tier` (the width's: inventoried, measured, counted, estimated), `deck`, `tunnel`, `layer`; alleys and service ways from z15 |
| `surfaces_z15` | 15 | MultiPolygon | the surfaces generalised for z15 (0.5 m; the smallest left out): `kind` (carriageway, junction, deck, median, island), `material`, `tier`, `layer` |
| `surfaces` | 16 | MultiPolygon | the same at full detail (overzoomed past z16) |
| `edges` | 16 | MultiLineString | the surfaces' outer edges: `kind` (curb, shoulder, deck), `tier`, `layer` |
| `markings` | 16 | MultiLineString | `kind` (edge, lane, centre_double, twltl, bike, stop_bar), `dash` (solid, dashed, double, solid_dashed) |
| `crosswalks` | 16 | MultiPolygon | marked crossings only |
| `arrows` | 16 | Point | `turns` ('left;through'), `bearing` (degrees from grid north, the way the lane travels) |

**Licence.** The geometry is OpenStreetMap's (ODbL: the bake's tiles are a produced work, a derived database
published stays ODbL), and the widths and lane counts rest on ACHD's and ITD's layers (no licence stated: internal).
So every layer's republish is **internal**: the bake that holds it is tailnet-only (C17, decision 4) until a public
variant is rebuilt from public inputs. The ground never reads these (basemap/ground/inputs.py NEVER). The inputs and
their versions come from roads.build.inputs.

Other roads layers join this export as they come (P8-app's paving: add a Layer to LAYERS), since the bake reads each
plugin's newest export whole. Standard library plus psycopg, and basemap/ground and basemap/landscape's checks.
"""

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass

from basemap.ground import manifest as M
from basemap.landscape import plan as LP

from ingest import builds

COMMAND = "python3 -m ingest roads-export"
BUILD = "roads-export"
THEN = ("landscape-bake",)


@dataclass(frozen=True)
class Layer:
    name: str
    geometry: str
    sql: str                 # selects id, the fields and geom (EPSG:32611), one row per feature
    title: str
    minzoom: int
    maxzoom: int
    note: str = ""


_MINZOOM_LINES = "case when p.highway = 'service' then 15 else 14 end"

LAYERS = (
    Layer("lines", "LineString", f"""
      select p.id, p.highway as class, round(x.total_w_m::numeric, 1)::float4 as w, x.material, x.width_tier as tier,
             p.bridge as deck, p.tunnel, p.layer::int as layer, ({_MINZOOM_LINES})::int as minzoom, p.geom
      from roads.piece p join roads.xsection x on x.piece_id = p.id order by p.id""",
          "Real-width roads: the pieces' centrelines with their widths", 14, 16,
          "w: the pavement's width in metres (draw the line that wide from z14); tier: how it's known"),
    Layer("surfaces_z15", "MultiPolygon", """
      select s.id, s.kind, s.material, s.tier, s.layer::int as layer, s.geom_z15 as geom
      from roads.surface s where s.geom_z15 is not null order by s.id""",
          "Real-width roads: surfaces generalised for z15", 15, 15, "0.5 m; surfaces under 4 m² left out"),
    Layer("surfaces", "MultiPolygon", """
      select s.id, s.kind, s.material, s.tier, s.layer::int as layer, s.geom from roads.surface s order by s.id""",
          "Real-width roads: surfaces", 16, 16,
          "carriageways overlap where they meet: one opaque fill, with edges drawn from the edges layer"),
    Layer("edges", "MultiLineString", """
      select e.id, e.kind, e.tier, e.layer::int as layer, e.geom from roads.edge e order by e.id""",
          "Real-width roads: surface edges", 16, 16, "a crisp curb where tier is inventoried or measured"),
    Layer("markings", "MultiLineString", """
      select m.id, m.kind, m.dash, m.geom from roads.marking m where m.kind <> 'crosswalk' order by m.id""",
          "Real-width roads: lane markings and stop bars", 16, 16, "only where a source gives the lane count"),
    Layer("crosswalks", "MultiPolygon", """
      select m.id, m.geom from roads.marking m where m.kind = 'crosswalk' order by m.id""",
          "Real-width roads: crosswalks on marked crossings", 16, 16, "OpenStreetMap's marked crossings only"),
    Layer("arrows", "Point", """
      select a.id, array_to_string(a.turns, ';') as turns, round(a.bearing)::int as bearing, a.geom
      from roads.arrow a order by a.id""",
          "Real-width roads: turn arrows", 16, 16, "turn:lanes"),
)


class ExportError(RuntimeError):
    pass


def current_build(conn):
    row = conn.execute("select id, inputs, counts from roads.build where current").fetchone()
    if row is None:
        raise ExportError("no current roads build (python3 -m ingest roads-build first)")
    return row


def manifest_inputs(build_inputs):
    """roads.build.inputs as the manifest's inputs (empty values dropped)."""
    keys = ("name", "licence", "republish", "credit", "source", "version", "note")
    return [{k: str(i[k]) for k in keys if i.get(k) not in (None, "")} for i in build_inputs]


def export(conn, archive, build=None, layers=LAYERS):
    """Write an export folder from the current build, and check it as the bake would. Returns the Manifest."""
    build_id, build_inputs, _ = current_build(conn)
    inputs = manifest_inputs(build_inputs)
    names = [i["name"] for i in inputs]
    folder = M.export_dir(archive, "roads", build or M.build_id())
    os.makedirs(folder)
    try:
        specs = []
        for lay in layers:
            blob = conn.execute(f"select ST_AsFlatGeobuf(q, true, 'geom') from ({lay.sql}) q").fetchone()[0]
            if not blob:
                continue                   # nothing of this kind (the bake would list it empty)
            path = os.path.join(folder, f"{lay.name}.fgb")
            with open(path, "wb") as f:
                f.write(bytes(blob))
            specs.append({"name": lay.name, "file": f"{lay.name}.fgb", "format": "FlatGeobuf",
                          "geometry": lay.geometry, "inputs": names, "base": True, "minzoom": lay.minzoom,
                          "maxzoom": lay.maxzoom, "title": lay.title,
                          "note": f"roads build {build_id}" + (f"; {lay.note}" if lay.note else "")})
        if not specs:
            raise ExportError(f"roads build {build_id} has nothing to export")
        m = M.write(folder, "roads", inputs=inputs, layers=specs, command=COMMAND,
                    note=f"real-width roads, build {build_id}")
        LP.resolve({"roads": m})           # the bake's own checks: ids, field types, republish, sources
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(prog=COMMAND, description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    archive = os.environ.get("TVT_ARCHIVE")
    if not archive or not os.path.isdir(archive):
        print("roads-export: set TVT_ARCHIVE to the archive folder", file=sys.stderr)
        return 1
    try:
        from ingest import db
        with db.connect() as conn:
            with builds.Run(conn, BUILD, then=THEN) as run:
                m = export(conn, archive)
                run.note = f"{os.path.basename(m.folder)}: " + ", ".join(
                    f"{lay.name} {lay['features']:,}" for lay in m.layers)
    except (ExportError, M.ManifestError, LP.BakeError, OSError) as err:
        print(f"roads-export: {err}", file=sys.stderr, flush=True)
        return 1
    print(f"roads-export: {m.folder}: " + ", ".join(
        f"{lay.name} ({lay['bytes']:,} bytes, {lay['features']:,} features)" for lay in m.layers), flush=True)
    print(json.dumps({"licence": sorted({lay["licence"] for lay in m.layers}), "republish": m.republish}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
