"""Load the HydroShare canal network: `python3 -m ingest hydroshare-load --from FILE.gpkg` (plan P4-data).

FILE.gpkg is what plugins/water/build/prepare.py hydroshare wrote (its prepare.json beside it): the Treasure Valley
Irrigation System's lines touching the map box, in WGS 84. Standard library plus psycopg, read with sqlite3
(gpkg.py). One transaction: water.hydroshare_canal is replaced, the load recorded in water.load and logged in
ops.fetch under `hydroshare_canals`, and water-build marked out of date. A file already loaded (same sha256) is
skipped unless --force. No request is made: the network was downloaded once by hand (sources/hydroshare_canals.py).

Licence CC BY 4.0: credit Tatum, Bittmann, Stone and Kaiser (2022), HydroShare,
doi:10.4211/hs.24a5f761bf4f41fb9b872b130d9d1a3f, and say "modified" on what we derive.
"""

import argparse
import json
import os
import sys

from . import gpkg
from .nhd import BUILD, LoadError, prepared, sha256, text
from .sources import hydroshare_canals

COLUMNS = ("id", "call_number", "name", "type")
TYPES = ("Canal", "Creek", "Drain", "Field Supply", "Lateral", "Pump Lifter", "Reservoir", "River")


def read(path):
    """[(id, call_number, name, type, wkb)] from the GeoPackage's `canal` layer. Raises LoadError."""
    with gpkg.open_ro(path) as g:
        geoms = gpkg.feature_tables(g)
        if "canal" not in geoms:
            raise LoadError(f"{path}: no canal layer: is it what prepare.py hydroshare wrote?")
        col, _, srs = geoms["canal"]
        if srs != 4326:
            raise LoadError(f"{path}: the canal layer is in SRS {srs}, not WGS 84")
        rows, seen = [], set()
        for r in gpkg.rows(g, "canal", list(COLUMNS) + [col]):
            if r[col] is None:
                continue
            if r["id"] is None or r["id"] in seen:
                raise LoadError(f"{path}: a canal without an id, or with one twice ({r['id']})")
            seen.add(r["id"])
            rows.append((int(r["id"]), text(r["call_number"]), text(r["name"]), text(r["type"]), r[col]))
    if not rows:
        raise LoadError(f"{path}: no canals")
    return rows


def load(conn, path, force=False, dry_run=False):
    from ingest import db
    digest = sha256(path)
    rows = read(path)
    unknown = sorted({r[3] for r in rows if r[3] and r[3] not in TYPES})
    if conn.execute("select to_regclass('water.load') is null").fetchone()[0]:
        raise LoadError("water.load is missing: apply water 0001 (python3 db/migrate.py)")
    last = conn.execute("select sha256 from water.load where source = 'hydroshare_canals' order by id desc limit 1"
                        ).fetchone()
    if last and last[0] == digest and not force:
        return {"loaded": "nothing", "why": f"{os.path.basename(path)} (sha256 {digest[:12]}) is the file loaded last; "
                                           "--force reloads it"}
    if dry_run:
        return {"would load": len(rows), "types we don't know": unknown or "none"}
    db.ensure_source(conn, hydroshare_canals.SOURCE)
    conn.commit()
    with db.Fetch(conn, hydroshare_canals.SOURCE["name"]) as f:
        f.bytes = os.path.getsize(path)
        with conn.cursor() as cur:
            load_id = cur.execute(
                """insert into water.load (source, file, sha256, prepared, counts, fetch_id)
                   values ('hydroshare_canals', %s, %s, %s::jsonb, %s::jsonb, %s) returning id""",
                (os.path.basename(path), digest, json.dumps(prepared(path)), json.dumps({"canal": len(rows)}),
                 f.id)).fetchone()[0]
            cur.execute("delete from water.hydroshare_canal")
            cur.execute("create temp table hs_stage (id int, call_number text, name text, type text, wkb bytea) "
                        "on commit drop")
            with cur.copy("copy hs_stage (id, call_number, name, type, wkb) from stdin") as cp:
                for r in rows:
                    cp.write_row(r)
            n = cur.execute(
                """insert into water.hydroshare_canal (id, call_number, name, type, geom, load_id)
                   select id, call_number, name, type, ST_Multi(ST_Force2D(ST_SetSRID(ST_GeomFromWKB(wkb), 4326))), %s
                   from hs_stage""", (load_id,)).rowcount
            if cur.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
                from ingest import builds
                builds.mark(conn, BUILD, by="hydroshare_canals",
                            reason=f"HydroShare canals loaded from {os.path.basename(path)} (sha256 {digest[:12]})")
        f.records = n
    return {"load": load_id, "canals": n, "types we don't know": unknown or "none"}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest hydroshare-load", description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="path", required=True, help="hydroshare.gpkg as prepare.py hydroshare wrote it")
    ap.add_argument("--force", action="store_true", help="load it even if it's the file loaded last")
    ap.add_argument("--dry-run", action="store_true", help="read the file and say what would load")
    args = ap.parse_args(argv)
    from ingest import db
    try:
        with db.connect() as conn:
            stats = load(conn, args.path, force=args.force, dry_run=args.dry_run)
    except (LoadError, gpkg.GpkgError) as err:
        print(f"hydroshare-load: {err}", file=sys.stderr)
        return 1
    print("hydroshare-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
