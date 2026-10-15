"""Load NHD HU4 1705 into the water schema: `python3 -m ingest nhd-load --from FILE.gpkg` (plan P4-data).

FILE.gpkg is what plugins/water/build/prepare.py nhd wrote (its prepare.json beside it). Standard library plus
psycopg: the GeoPackage is read with sqlite3 (gpkg.py), and each geometry's WKB goes to PostGIS as it is, 2D, with
NAD83 read as WGS 84 (the ground's datum policy, basemap/ground/README.md).

    python3 -m ingest nhd-load --from $TVT_ARCHIVE/water/prepared/<stamp>/nhd.gpkg [--force] [--dry-run]

One transaction: the water.nhd_* tables are replaced by the file's rows, the load is recorded in water.load (the
file's and the downloaded zip's sha256, the counts), it's logged in ops.fetch under `nhd_hr`, and water-build is
marked out of date. A file whose sha256 is the one loaded last is skipped unless --force. NHD changes about once a
year at most; nothing here makes a request.

    water.nhd_flowline   flowlines with their Strahler order, flags, visibility filter and class
    water.nhd_polygon    NHDWaterbody ('waterbody') and NHDArea ('area')
    water.nhd_line       NHDLine (dams and weirs, flumes, ...)
    water.nhd_point      NHDPoint ('point') and NHDPointEventFC ('event')
    water.nhd_flow       NHDFlow's rows touching the kept flowlines
"""

import argparse
import hashlib
import json
import os
import sys

from . import gpkg
from .sources import nhd_hr

BUILD = "water-build"
FLOWLINE = ("permanent_identifier", "reachcode", "gnis_id", "gnis_name", "ftype", "fcode", "class",
            "hydrographiccategory", "canalditchtype", "pipelinetype", "relationshiptosurface", "flowdir", "streamorder",
            "startflag", "terminalflag", "divergenceflag", "visibilityfilter", "wbarea_permanent_identifier", "fdate",
            "lengthkm")
POLYGON = ("permanent_identifier", "reachcode", "gnis_id", "gnis_name", "ftype", "fcode", "ftype_name",
           "hydrographiccategory", "reservoirtype", "visibilityfilter", "areasqkm", "fdate")
LINE = ("permanent_identifier", "gnis_name", "ftype", "fcode", "ftype_name")
POINT = ("permanent_identifier", "gnis_name", "ftype", "fcode", "ftype_name", "eventtype", "reachcode",
         "source_featureid")
FLOW = ("from_permanent_identifier", "to_permanent_identifier", "direction", "deltalevel")
CLASSES = ("stream_river", "canal_ditch", "pipeline", "artificial_path", "connector", "underground_conduit")

# (GeoPackage table, our table, its column list, layer value or None, geometry column, PostGIS type)
LAYERS = (
    ("flowline", "water.nhd_flowline", FLOWLINE, None, "geom", "MultiLineString"),
    ("waterbody", "water.nhd_polygon", POLYGON, "waterbody", "geom", "MultiPolygon"),
    ("area", "water.nhd_polygon", POLYGON, "area", "geom", "MultiPolygon"),
    ("line", "water.nhd_line", LINE, None, "geom", "MultiLineString"),
    ("point", "water.nhd_point", POINT, "point", "geom", "Point"),
    ("point_event", "water.nhd_point", POINT, "event", "geom", "Point"),
)
REQUIRED = {"flowline", "waterbody", "area", "flow"}
TYPES = {"ftype": "smallint", "fcode": "integer", "flowdir": "smallint", "streamorder": "smallint",
         "startflag": "smallint", "terminalflag": "smallint", "divergenceflag": "smallint",
         "visibilityfilter": "integer", "fdate": "timestamptz", "lengthkm": "real", "areasqkm": "real",
         "eventtype": "integer", "direction": "smallint", "deltalevel": "smallint"}


class LoadError(ValueError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def prepared(path):
    """prepare.json beside the GeoPackage ({} when there's none)."""
    p = os.path.join(os.path.dirname(os.path.abspath(path)), "prepare.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def text(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def read_rows(g, table, wanted, geometry):
    """(values tuples, skipped) for one GeoPackage table: our columns (missing ones null), then the WKB."""
    have = set(gpkg.columns(g, table))
    cols = [c for c in wanted if c in have]
    out, skipped = [], 0
    for r in gpkg.rows(g, table, cols + [geometry]):
        if r[geometry] is None:
            skipped += 1
            continue
        vals = []
        for c in wanted:
            v = r.get(c)
            vals.append(text(v) if isinstance(v, str) else v)
        out.append(tuple(vals) + (r[geometry],))
    return out, skipped


def read(path):
    """Everything to load from the GeoPackage: {table: rows}, plus 'flow'. Raises LoadError for a file that isn't
    what prepare.py writes."""
    with gpkg.open_ro(path) as g:
        have = gpkg.tables(g)
        if missing := sorted(REQUIRED - set(have)):
            raise LoadError(f"{path}: no {', '.join(missing)} table: is it what prepare.py nhd wrote?")
        geoms = gpkg.feature_tables(g)
        data, skipped = {}, {}
        for table, _, wanted, _, geometry, _ in LAYERS:
            if table not in have:
                data[table] = []
                continue
            col, _, srs = geoms[table]
            if srs not in (4269, 4326):
                raise LoadError(f"{path}: {table} is in SRS {srs}, not NAD83 or WGS 84 lon/lat")
            data[table], skipped[table] = read_rows(g, table, wanted, col)
        flow = []
        for r in gpkg.rows(g, "flow", FLOW):
            if r["from_permanent_identifier"] and r["to_permanent_identifier"]:
                flow.append(tuple(r[c] for c in FLOW))
        data["flow"] = flow
    bad = [r[6] for r in data["flowline"] if r[6] not in CLASSES]
    if len(bad) > len(data["flowline"]) * 0.01:
        raise LoadError(f"{path}: {len(bad)} flowlines of an unknown class (e.g. {bad[:3]})")
    if not data["flowline"]:
        raise LoadError(f"{path}: no flowlines")
    return data, skipped


def _copy(cur, stage, columns, rows):
    cols = ", ".join(columns)
    with cur.copy(f"copy {stage} ({cols}) from stdin") as cp:
        for r in rows:
            cp.write_row(r)


def load(conn, path, force=False, dry_run=False, out=print):
    """Load the file in one transaction (commits unless dry_run). Returns stats."""
    from ingest import db
    digest = sha256(path)
    prep = prepared(path)
    data, skipped = read(path)
    last = None
    if conn.execute("select to_regclass('water.load') is not null").fetchone()[0]:
        last = conn.execute("select sha256 from water.load where source = 'nhd_hr' order by id desc limit 1").fetchone()
    else:
        raise LoadError("water.load is missing: apply water 0001 (python3 db/migrate.py)")
    if last and last[0] == digest and not force:
        return {"loaded": "nothing", "why": f"{os.path.basename(path)} (sha256 {digest[:12]}) is the file loaded last; "
                                           "--force reloads it"}
    counts = {t: len(rows) for t, rows in data.items()}
    if dry_run:
        return {"would load": counts, "skipped (no geometry)": skipped}

    db.ensure_source(conn, nhd_hr.SOURCE)
    conn.commit()
    with db.Fetch(conn, nhd_hr.SOURCE["name"]) as f:          # no request made: robots and status stay empty
        f.bytes = os.path.getsize(path)
        with conn.cursor() as cur:
            load_id = cur.execute(
                """insert into water.load (source, file, sha256, prepared, counts, fetch_id)
                   values ('nhd_hr', %s, %s, %s::jsonb, %s::jsonb, %s) returning id""",
                (os.path.basename(path), digest, json.dumps(prep), json.dumps(counts), f.id)).fetchone()[0]
            for t in ("water.nhd_flow", "water.nhd_point", "water.nhd_line", "water.nhd_polygon", "water.nhd_flowline"):
                cur.execute(f"delete from {t}")
            for table, target, wanted, layer, _, pg_type in LAYERS:
                rows = data[table]
                if not rows:
                    continue
                stage = f"nhd_stage_{table}"
                cur.execute(f"drop table if exists pg_temp.{stage}")
                cur.execute(f"create temp table {stage} ({', '.join(f'{c} text' for c in wanted)}, wkb bytea) "
                            "on commit drop")
                _copy(cur, stage, list(wanted) + ["wkb"],
                      [tuple(None if v is None else str(v) for v in r[:-1]) + (r[-1],) for r in rows])
                cast = ", ".join(f"{c}::{TYPES.get(c, 'text')}" if c != "fdate" else
                                 "nullif(fdate, '')::timestamptz" for c in wanted)
                geom = "ST_Force2D(ST_SetSRID(ST_GeomFromWKB(wkb), 4326))"
                if pg_type.startswith("Multi"):
                    geom = f"ST_Multi({geom})"
                layer_col = ", layer" if layer else ""
                layer_val = f", '{layer}'" if layer else ""
                cur.execute(f"""insert into {target} ({', '.join(wanted)}{layer_col}, geom, load_id)
                                select {cast}{layer_val}, {geom}, %s from {stage}
                                on conflict (permanent_identifier) do nothing""", (load_id,))
            stage = "nhd_stage_flow"
            cur.execute(f"drop table if exists pg_temp.{stage}")
            cur.execute(f"create temp table {stage} (a text, b text, direction smallint, deltalevel smallint) "
                        "on commit drop")
            _copy(cur, stage, ["a", "b", "direction", "deltalevel"], data["flow"])
            cur.execute("""insert into water.nhd_flow (from_pid, to_pid, direction, deltalevel, load_id)
                           select a, b, min(direction), min(deltalevel), %s from nhd_stage_flow group by a, b""",
                        (load_id,))
            stored = dict(zip(("flowlines", "polygons", "lines", "points", "flow"), cur.execute(
                """select (select count(*) from water.nhd_flowline), (select count(*) from water.nhd_polygon),
                          (select count(*) from water.nhd_line), (select count(*) from water.nhd_point),
                          (select count(*) from water.nhd_flow)""").fetchone()))
            expected = {"flowlines": counts["flowline"], "polygons": counts["waterbody"] + counts["area"],
                        "lines": counts["line"], "points": counts["point"] + counts["point_event"]}
            if lost := {k: (stored[k], v) for k, v in expected.items() if stored[k] != v}:
                raise LoadError(f"rows lost on the way in (a repeated permanent identifier?): {lost}")
            cur.execute("update water.load set counts = %s::jsonb where id = %s",
                        (json.dumps({**counts, "stored": stored}), load_id))
            if cur.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
                from ingest import builds
                builds.mark(conn, BUILD, by="nhd_hr", reason=f"NHD loaded from {os.path.basename(path)} "
                                                             f"(sha256 {digest[:12]})")
        f.records = sum(stored.values())
    return {"load": load_id, **stored, "skipped (no geometry)": sum(skipped.values()),
            "product": (prep.get("input") or {}).get("sha256", "?")[:12]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest nhd-load", description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="path", required=True, help="nhd.gpkg as prepare.py nhd wrote it")
    ap.add_argument("--force", action="store_true", help="load it even if it's the file loaded last")
    ap.add_argument("--dry-run", action="store_true", help="read the file and say what would load")
    args = ap.parse_args(argv)
    from ingest import db
    try:
        with db.connect() as conn:
            stats = load(conn, args.path, force=args.force, dry_run=args.dry_run)
    except (LoadError, gpkg.GpkgError) as err:
        print(f"nhd-load: {err}", file=sys.stderr)
        return 1
    print("nhd-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
