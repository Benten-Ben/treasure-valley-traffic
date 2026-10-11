"""Load a crop-fields build: `python3 -m ingest farm-fields-load --build DIR`.

DIR is what plugins/farm/build/build.py wrote in the worker image: build.json (written last), fields.jsonl (one line
per field: its CDL agreement per year and its July state) and crop_cover.tif (which farm-export hands to the ground).
Standard library plus psycopg:

    python3 -m ingest farm-fields-load --build $TVT_ARCHIVE/farm/build/<id>
    python3 -m ingest farm-fields-load --build DIR --dry-run

In one transaction: the build is recorded in farm.build; each current field's agree, july and build_id are set from
it; then derive.py works out growth (with COMPASS's permits), plats, the z8-10 dissolves and a new version of the
crop-fields tiles. The build must have been made from the GeoPackage of the edition loaded now (the same sha256), so
its stats belong to these outlines.
"""

import argparse
import hashlib
import json
import os
import sys

from . import classes as C
from . import derive

FORMAT = "tvt-farm-build/1"
FILES = ("fields.jsonl", "crop_cover.tif")
STATES = ("green", "growing", "bare")
LICENSE = "public domain (USDA NASS CSB, CDL); Copernicus (Sentinel-2)"
CREDIT = ("USDA NASS Crop Sequence Boundaries; USDA NASS Cropland Data Layer; Contains modified Copernicus Sentinel "
          "data 2025")


class BuildError(ValueError):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_build(folder, verify=True):
    """(build.json, [field rows]) from a build folder, checked: the format, every file's sha256, each row's shape."""
    path = os.path.join(folder, "build.json")
    if not os.path.isfile(path):
        raise BuildError(f"{folder}: no build.json (unfinished, or not a farm build)")
    with open(path, encoding="utf-8") as f:
        b = json.load(f)
    if b.get("format") != FORMAT:
        raise BuildError(f"{path}: format {b.get('format')!r}, expected {FORMAT}")
    if b.get("build_id") != os.path.basename(os.path.normpath(folder)):
        raise BuildError(f"{path}: build_id {b.get('build_id')!r} isn't the folder's name")
    for name in FILES:
        spec = (b.get("files") or {}).get(name)
        fp = os.path.join(folder, name)
        if not spec or not os.path.isfile(fp):
            raise BuildError(f"{folder}: {name} is missing")
        if os.path.getsize(fp) != spec.get("bytes") or (verify and sha256_of(fp) != spec.get("sha256")):
            raise BuildError(f"{folder}: {name} isn't the file build.json describes")
    csb = (b.get("inputs") or {}).get("csb") or {}
    if not csb.get("sha256"):
        raise BuildError(f"{path}: no CSB input sha256")
    rows, seen = [], set()
    with open(os.path.join(folder, "fields.jsonl"), encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            r = json.loads(line)
            fid = r.get("field_id")
            if not isinstance(fid, str) or not fid or fid in seen:
                raise BuildError(f"fields.jsonl line {i}: field_id {fid!r} missing or repeated")
            seen.add(fid)
            agree = r.get("agree") or {}
            if not all(k.isdigit() and isinstance(v, (int, float)) and 0 <= v <= 1 for k, v in agree.items()):
                raise BuildError(f"fields.jsonl line {i}: agree {agree!r}")
            july = r.get("july")
            if july is not None and (july.get("state") not in STATES or not isinstance(july.get("ndvi"), (int, float))):
                raise BuildError(f"fields.jsonl line {i}: july {july!r}")
            rows.append((fid, json.dumps(agree) if agree else None, json.dumps(july) if july else None))
    if b.get("counts", {}).get("fields") != len(rows):
        raise BuildError(f"{folder}: fields.jsonl has {len(rows)} fields, build.json says "
                         f"{b.get('counts', {}).get('fields')}")
    return b, rows


def current_edition(conn):
    return conn.execute("select edition, sha256 from farm.edition order by last_year desc, loaded_at desc "
                        "limit 1").fetchone()


def load(conn, folder, b, rows):
    """Load a build. Doesn't commit. Returns stats."""
    ed = current_edition(conn)
    if ed is None:
        raise BuildError("no CSB edition loaded yet (farm-csb-load first)")
    edition, sha = ed
    if b["inputs"]["csb"]["sha256"] != sha:
        raise BuildError(f"the build was made from another CSB file than {edition}'s (sha256 "
                         f"{b['inputs']['csb']['sha256'][:12]}..., loaded {sha[:12]}...): rebuild it")
    bid = b["build_id"]
    with conn.cursor() as cur:
        cur.execute(
            """insert into farm.build (build_id, edition, started_at, finished_at, params, inputs, counts, license,
                 republish, credit)
               values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, 'yes', %s)
               on conflict (build_id) do update set edition = excluded.edition, loaded_at = now(),
                 params = excluded.params, inputs = excluded.inputs, counts = excluded.counts""",
            (bid, edition, b.get("started_at"), b.get("finished_at"),
             json.dumps({**b.get("params", {}), "cover_year": b.get("cover_year"), "july_year": b.get("july_year"),
                         "grid": b.get("grid"), "folder": os.path.abspath(folder)}),
             json.dumps(b.get("inputs", {})), json.dumps(b.get("counts", {})), LICENSE, CREDIT))
        cur.execute("""create temporary table if not exists farm_stats_in (field_id text primary key, agree jsonb,
                         july jsonb) on commit drop""")
        cur.execute("truncate farm_stats_in")
        with cur.copy("copy farm_stats_in (field_id, agree, july) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
        updated = cur.execute(
            """update farm.field f set agree = s.agree, july = s.july, build_id = %s
               from farm_stats_in s where f.field_id = s.field_id and f.valid_to is null""", (bid,)).rowcount
        unknown = cur.execute(
            """select count(*) from farm_stats_in s
               where not exists (select 1 from farm.field f where f.field_id = s.field_id and f.valid_to is null)"""
        ).fetchone()[0]
        if unknown:
            raise BuildError(f"{unknown} of the build's fields aren't current fields of {edition}")
        stale = cur.execute("""update farm.field set agree = null, july = null, build_id = null
                               where valid_to is null and build_id is distinct from %s""", (bid,)).rowcount
    stats = {"build": bid, "edition": edition, "fields updated": updated}
    if stale:
        stats["fields the build lacks (cleared)"] = stale
    stats.update(derive.run(conn, bid, f"farm-fields-load {bid}", C.read()))
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest farm-fields-load", description=__doc__.split("\n")[0])
    ap.add_argument("--build", required=True, help="a folder written by plugins/farm/build/build.py")
    ap.add_argument("--dry-run", action="store_true", help="check the build; write nothing")
    args = ap.parse_args(argv)
    try:
        b, rows = read_build(args.build)
        if args.dry_run:
            print(f"farm-fields-load (dry run): {b['build_id']}: {len(rows)} fields, "
                  f"{sum(1 for r in rows if r[2])} with a July state", flush=True)
            return 0
        from ingest import db
        with db.connect() as conn:
            stats = load(conn, args.build, b, rows)
            conn.commit()
            conn.execute("analyze farm.field, farm.field_lo")
            conn.commit()
    except (BuildError, C.ClassesError, OSError, ValueError) as err:
        print(f"farm-fields-load: {err}", file=sys.stderr, flush=True)
        return 1
    print("farm-fields-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
