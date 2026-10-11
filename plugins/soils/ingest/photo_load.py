"""Load a photo-statistics build into soils.photo_stats: `python3 -m ingest soils-photo-load --build DIR` (plan P2).

DIR is a build folder plugins/soils/build/photo_stats.py wrote ($TVT_ARCHIVE/soils/photo/<build>/) after `finish`:
its stats.json (format tvt-soils-photo/1) holds each map unit's and ground type's measured colour, spread and
texture, per NAIP flight day and pooled, and the ground types' fallbacks. Standard library plus psycopg:

    python3 -m ingest soils-photo-load --build $TVT_ARCHIVE/soils/photo/photo-20261011T190000Z
    python3 -m ingest soils-photo-load --build DIR --dry-run       # check it against the database only

One transaction: the build's soils.build row (kind 'photo': its settings, counts, inputs, licence, republish and
credit) and its rows. The build is finished when it commits, so soils.ground_colour picks it up for every type it
has a pooled row for. A build is loaded once (its id is the folder's name); a partial build (a quick look at part
of the grid, or one with windows missing) is refused, and so is one whose map units or ground types aren't in the
database any more (a soils reload since: run the photo build again). Then `python3 -m ingest soils-export` writes
palette.json beside the ground.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# The photo statistics as a source (plugin.json "manual"): a derived product, not a download. Its rows were measured
# from NAIP 2025 through mask v0 (OpenStreetMap and Overture), farm's crop cover (CSB, CDL, Sentinel-2) and
# Sentinel-2's July median, NDVI curves and colour gains: ODbL as a whole, crediting every input. Each build records
# its own inputs, licence and credit in soils.build (licence_of).
SOURCE = {
    "name": "naip_photo",
    "license": "derived: ODbL-1.0 (measured through mask v0, from OpenStreetMap and Overture), from USDA NAIP 2025 "
               "(public domain), Copernicus Sentinel-2 (free, full and open), SSURGO, NHD, CDL and CSB (public domain)",
    "credit": "USDA NAIP; Contains modified Copernicus Sentinel data 2025; © OpenStreetMap contributors; Overture "
              "Maps Foundation; U.S. Geological Survey, National Hydrography Dataset; USDA NASS Cropland Data Layer "
              "and Crop Sequence Boundaries; Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)",
    "republish": "yes",
}

FORMAT = "tvt-soils-photo/1"
FILE = "stats.json"
COLUMNS = ("build_id", "level", "key", "photo", "flight", "mask", "n_px", "n_polygons", "lab_med", "lab_cov", "l_p10",
           "l_p90", "oct_l", "oct_c", "fallback")
LEVELS = ("mapunit", "ground_type")
FALLBACKS = (None, "series", "texture", "albedo")
LENGTHS = {"lab_med": 3, "lab_cov": 6, "oct_l": 5, "oct_c": 5}


class PhotoLoadError(ValueError):
    pass


def read(folder):
    """stats.json from a build folder, checked. Returns the parsed document."""
    path = os.path.join(folder, FILE)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as err:
        raise PhotoLoadError(f"{path}: {err}") from None
    if doc.get("format") != FORMAT:
        raise PhotoLoadError(f"{path}: format {doc.get('format')!r}, expected {FORMAT!r}")
    for k in ("build_id", "started", "finished", "photo", "mask", "inputs", "params", "counts", "rows"):
        if k not in doc:
            raise PhotoLoadError(f"{path}: no {k!r}")
    if doc["build_id"] != os.path.basename(os.path.normpath(folder)):
        raise PhotoLoadError(f"{path}: build {doc['build_id']!r} isn't its folder's name")
    seen = set()
    for i, r in enumerate(doc["rows"]):
        where = f"{path}: row {i}"
        if r.get("level") not in LEVELS or not r.get("key"):
            raise PhotoLoadError(f"{where}: level must be one of {LEVELS} with a key")
        if r.get("fallback") not in FALLBACKS or (r["fallback"] and (r["level"] != "ground_type" or r["flight"])):
            raise PhotoLoadError(f"{where}: a fallback is for a ground type's pooled row only")
        if not isinstance(r.get("n_px"), int) or r["n_px"] < 0:
            raise PhotoLoadError(f"{where}: n_px must be a whole number")
        for k, n in LENGTHS.items():
            v = r.get(k)
            if v is not None and (not isinstance(v, list) or len(v) != n):
                raise PhotoLoadError(f"{where}: {k} must have {n} values")
        ident = (r["level"], r["key"], r["photo"], r.get("flight"), r["mask"])
        if ident in seen:
            raise PhotoLoadError(f"{where}: repeats {ident}")
        seen.add(ident)
    for inp in doc["inputs"]:
        if not all(inp.get(k) for k in ("name", "licence", "republish", "credit")):
            raise PhotoLoadError(f"{path}: every input needs a name, licence, republish and credit")
    return doc


def licence_of(inputs):
    """soils.build's licence, republish and credit from the build's inputs, by the ground's export rule
    (basemap/ground/manifest.py write): the share-alike input's licence when there is one (ODbL: the rows were
    measured through mask v0), else the one strictest; the strictest republish; every credit, once each."""
    from basemap.ground import manifest as M
    every = list(dict.fromkeys(i["licence"] for i in inputs))
    unknown = [lic for lic in every if lic not in M.LICENCES]
    if unknown:
        raise PhotoLoadError(f"inputs with licences the ground doesn't know: {', '.join(unknown)}")
    shared = [lic for lic in every if M.LICENCES[lic].share_alike]
    top = [lic for lic in every if M.strictness(lic) == max(map(M.strictness, every))]
    if len(shared) > 1:
        raise PhotoLoadError(f"inputs under two share-alike licences ({', '.join(shared)})")
    if shared:
        licence = shared[0]
    elif len(top) == 1:
        licence = top[0]
    else:
        raise PhotoLoadError(f"inputs under several licences, none share-alike ({', '.join(top)}): the build's "
                             "licence would have to be named")
    republish = M.strictest(i["republish"] for i in inputs)
    credits = list(dict.fromkeys(i["credit"] for i in inputs))
    return licence, republish, "; ".join(credits)


def load(conn, folder, now=None):
    """Load a build folder's stats. Doesn't commit. Returns a summary."""
    doc = read(folder)
    if doc.get("partial"):
        raise PhotoLoadError(f"{doc['build_id']} is partial (part of the grid, or windows missing): not loaded")
    bid = doc["build_id"]
    if conn.execute("select 1 from soils.build where build_id = %s", (bid,)).fetchone():
        raise PhotoLoadError(f"{bid} is loaded already")
    mus = {r["key"] for r in doc["rows"] if r["level"] == "mapunit"}
    types = {r["key"] for r in doc["rows"] if r["level"] == "ground_type"}
    have_mu = {r[0] for r in conn.execute("select mukey from soils.map_unit where mukey = any(%s)", (sorted(mus),))}
    have_t = {r[0] for r in conn.execute("select id from soils.ground_type where id = any(%s)", (sorted(types),))}
    missing = sorted(mus - have_mu) + sorted(types - have_t)
    if missing:
        raise PhotoLoadError(f"{bid} has {len(missing)} map units or ground types the database doesn't (e.g. "
                             f"{', '.join(missing[:4])}): the soils were reloaded since; run the photo build again")
    licence, republish, credit = licence_of(doc["inputs"])
    params = dict(doc["params"], inputs=doc["inputs"], files=doc.get("files"), soils_export=doc.get("soils_export"),
                  photo=doc["photo"], mask=doc["mask"], folder=os.path.abspath(folder))
    inputs = {i["name"]: i.get("sha256") or i.get("version") for i in doc["inputs"]}
    counts = dict(doc["counts"], loaded=len(doc["rows"]))
    with conn.cursor() as cur:
        cur.execute(
            """insert into soils.build (build_id, kind, started_at, params, counts, inputs, license, republish,
                                        credit)
               values (%s, 'photo', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)""",
            (bid, doc["started"], json.dumps(params), json.dumps(counts), json.dumps(inputs), licence, republish,
             credit))
        cols = ", ".join(COLUMNS)
        with cur.copy(f"copy soils.photo_stats ({cols}) from stdin") as cp:
            for r in doc["rows"]:
                cp.write_row(tuple(bid if c == "build_id" else _pg(r.get(c)) for c in COLUMNS))
        # Finished: from here soils.ground_colour reads it.
        cur.execute("update soils.build set finished_at = %s where build_id = %s",
                    (now or datetime.now(timezone.utc), bid))
    by = {}
    for r in doc["rows"]:
        if r["level"] == "ground_type" and r.get("flight") is None:
            by[r["fallback"] or "measured"] = by.get(r["fallback"] or "measured", 0) + 1
    return {"build": bid, "rows": len(doc["rows"]), "ground types": by,
            "calibration": (doc["counts"].get("calibration") or "not run")}


def _pg(v):
    """A Python value as COPY wants it: lists as PostgreSQL array literals."""
    if isinstance(v, list):
        return "{" + ",".join("NULL" if x is None else repr(float(x)) for x in v) + "}"
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest soils-photo-load", description=__doc__.split("\n")[0])
    ap.add_argument("--build", required=True, help="a photo build folder (stats.json), from photo_stats.py finish")
    ap.add_argument("--dry-run", action="store_true", help="check it against the database; write nothing")
    args = ap.parse_args(argv)
    try:
        from ingest import db
        with db.connect() as conn:
            stats = load(conn, args.build)
            if args.dry_run:
                conn.rollback()
                print("soils-photo-load (dry run): " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
                return 0
            conn.commit()
            conn.execute("analyze soils.photo_stats")
            conn.commit()
    except PhotoLoadError as err:
        print(f"soils-photo-load: {err}", file=sys.stderr, flush=True)
        return 1
    print("soils-photo-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
