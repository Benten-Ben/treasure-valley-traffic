"""Load the CDL's classes and index its rasters: `python3 -m ingest farm-cdl-load --cdl DIR [--accuracy XLSX]`.

    python3 -m ingest farm-cdl-load --cdl $TVT_SOURCES/cdl/out \\
        --accuracy $TVT_SOURCES/cdl/docs/NASS_CDL_ID25_accuracy.xlsx
    python3 -m ingest farm-cdl-load --cdl DIR --dry-run

In one transaction:
- farm.crop_class from crop_classes.csv (NASS's names and colours, our crop groups and AgriMet crops), with NASS's
  Idaho accuracy per code from the workbook when given (producer's and user's accuracy; the year and state are the
  workbook's, --accuracy-year, --accuracy-state);
- each raster in DIR named cdl_<year>_<res>m.tif is copied into $TVT_ARCHIVE/farm/cdl/ (unless the same file is there)
  and indexed in farm.cdl_year with its sha256: the worker build reads them from there;
- when the classes' groups changed and fields are loaded, derive.py runs again (letters, growth, the dissolves and a
  new tile version).
The load is logged in ops.fetch under the source nass_cdl (no request is made). Standard library plus psycopg.
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

from . import classes as C
from . import derive
from .csb_load import sha256_of
from .sources import nass_cdl

RASTER = re.compile(r"^cdl_([0-9]{4})_([0-9]+)m\.tif$")
NEW_METHOD_FROM = 2024                 # NASS's 10 m method (Google Earth Engine random forest, NLCD 2024 imperviousness)
ARCHIVE_DIR = os.path.join("farm", "cdl")


class CdlError(ValueError):
    pass


def rasters(folder):
    """[(year, res_m, path)] for the cdl_<year>_<res>m.tif files in a folder, by year."""
    out = []
    for name in sorted(os.listdir(folder)):
        m = RASTER.match(name)
        if m:
            out.append((int(m.group(1)), float(m.group(2)), os.path.join(folder, name)))
    years = [y for y, _, _ in out]
    if len(years) != len(set(years)):
        raise CdlError(f"{folder}: a year has more than one raster")
    if not out:
        raise CdlError(f"{folder}: no cdl_<year>_<res>m.tif files")
    return out


def method(year, res):
    return "10m-2024" if year >= NEW_METHOD_FROM else f"{res:g}m"


def archive_copy(src, archive, sha):
    """Copy a raster into $TVT_ARCHIVE/farm/cdl/ (atomically, unless the same file is there). Returns its path
    relative to the archive."""
    rel = os.path.join(ARCHIVE_DIR, os.path.basename(src))
    dest = os.path.join(archive, rel)
    if os.path.exists(dest) and sha256_of(dest) == sha:
        return rel
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".cdl-", suffix=".tif", dir=os.path.dirname(dest))
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return rel


def class_rows(conn):
    return conn.execute("select code, grp from farm.crop_class order by code").fetchall()


def load(conn, folder, archive, accuracy=None, now=None):
    """Load the classes and index the rasters. Doesn't commit. Returns stats."""
    now = now or datetime.now(timezone.utc)
    found = rasters(folder)
    classes = C.read()
    before = class_rows(conn)
    n = C.ensure(conn, classes, accuracy=accuracy)
    changed = class_rows(conn) != before
    indexed = []
    with conn.cursor() as cur:
        for year, res, path in found:
            sha = sha256_of(path)
            rel = archive_copy(path, archive, sha)
            cur.execute(
                """insert into farm.cdl_year (year, res_m, method, path, bytes, sha256, license, republish, credit,
                     loaded_at)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   on conflict (year) do update set res_m = excluded.res_m, method = excluded.method,
                     path = excluded.path, bytes = excluded.bytes, sha256 = excluded.sha256,
                     license = excluded.license, republish = excluded.republish, credit = excluded.credit,
                     loaded_at = excluded.loaded_at""",
                (year, res, method(year, res), rel, os.path.getsize(path), sha, nass_cdl.SOURCE["license"],
                 nass_cdl.REPUBLISH, f"{nass_cdl.SOURCE['credit']} {year}", now))
            indexed.append(f"{year} ({res:g} m)")
    stats = {"classes": n, "with accuracy": len(accuracy) if accuracy is not None else "kept",
             "rasters": ", ".join(indexed)}
    fields = conn.execute("select count(*) from farm.field where valid_to is null").fetchone()[0]
    if changed and fields:
        stats.update(derive.run(conn, "farm-cdl-load", "farm-cdl-load: crop classes changed", classes))
    return stats


def run(conn, folder, archive, accuracy=None):
    """load() with the source registered and the load logged in ops.fetch; commits."""
    from ingest import db
    db.ensure_source(conn, nass_cdl.SOURCE)
    with db.Fetch(conn, nass_cdl.SOURCE["name"]) as f:       # no request made: robots and status stay empty
        f.bytes = sum(os.path.getsize(p) for _, _, p in rasters(folder))
        stats = load(conn, folder, archive, accuracy)
        f.records = len(rasters(folder))
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest farm-cdl-load", description=__doc__.split("\n")[0])
    ap.add_argument("--cdl", required=True, help="a folder of CDL clips named cdl_<year>_<res>m.tif")
    ap.add_argument("--accuracy", help="NASS's accuracy workbook for a state and year (.xlsx)")
    ap.add_argument("--accuracy-state", default="ID")
    ap.add_argument("--accuracy-year", type=int, default=2025)
    ap.add_argument("--dry-run", action="store_true", help="read and check everything; write nothing")
    args = ap.parse_args(argv)
    archive = os.environ.get("TVT_ARCHIVE")
    try:
        found = rasters(args.cdl)
        classes = C.read()
        accuracy = (C.read_accuracy(args.accuracy, args.accuracy_state, args.accuracy_year)
                    if args.accuracy else None)
        if args.dry_run:
            print(f"farm-cdl-load (dry run): {len(classes)} classes, "
                  f"{len(accuracy) if accuracy is not None else 'no'} accuracy rows, rasters "
                  + ", ".join(f"{y} ({r:g} m)" for y, r, _ in found), flush=True)
            return 0
        if not archive:
            raise CdlError("set TVT_ARCHIVE (the rasters are copied to $TVT_ARCHIVE/farm/cdl/)")
        from ingest import db
        with db.connect() as conn:
            stats = run(conn, args.cdl, archive, accuracy)
            conn.commit()
    except (CdlError, C.ClassesError, OSError) as err:
        print(f"farm-cdl-load: {err}", file=sys.stderr, flush=True)
        return 1
    print("farm-cdl-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
