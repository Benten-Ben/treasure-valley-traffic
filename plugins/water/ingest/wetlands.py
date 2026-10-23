"""Vegetated wetlands for the water build (issue #309; the owner's answer 2 of Oct 22; the wetlands review).

The National Wetlands Inventory (FWS, public domain) is the only source that maps wetlands as wetlands across the
whole map box. Over the valley floor it dates from July 1981, so those polygons are checked against today's land
before they draw. This module holds the parts that are not PostGIS: the Cowardin code decoder, the presence check's
rules, the loaders and the rows the build reads.

    python3 -m ingest nwi-load --from nwi_mapbox.gpkg [--force] [--dry-run]
    python3 -m ingest nwi-presence --from shares.json [--dry-run]
    python3 -m ingest wetland-qa [--build N] [--out DIR] [--boxes]

nwi-load reads the GeoPackage kept on the server (the eight HU8 watershed files cut to the map box: layers `wetlands`
and `project_metadata`, in NAD83 Albers) with the standard library, and keeps only the vegetated palustrine wetlands
(Cowardin classes EM, SS and FO as the first class of the code). NWI's ponds, lakes and riverine polygons are not
kept: Water's bodies and reaches already draw that water, and the card for a pond may say what NWI says later.
Each wetland gets the mapping project whose polygon holds its point, hence its image year and `era`:

    recent    imagery of 1999 or later (2009, 2011, 2017, 2020): drawn as mapped
    old       July 1981 or July 1983 photos: a presence check first (below)
    interim   NWI's "Scalable" product (NWI plus NHD streams, not standard-compliant): the same check
    unknown   no project polygon holds it: drawn as mapped, and counted

The presence check (the review, section 6) measures five shares of an old or interim polygon from public inputs. A
worker step (rasterio, on the ground's grid) computes them and writes a JSON file that nwi-presence loads:

    {"computed_on": "2026-10-24", "inputs": {...},
     "polygons": [{"key": "...", "built": 0.0, "developed": 0.0, "cultivated": 0.0, "hay_pasture": 0.0,
                   "cdl_wetland": 0.0, "hydric": 0.0}, ...]}

    built        under roofs, roads and paving: mask v0's exact vectors (S5a), or P8-data's paving once it's loaded
    developed    CDL classes 122-124 in both 2024 and 2025 (class 121, open space, counts for nothing)
    cultivated   inside CSB fields coded as a crop, alfalfa or fallow in at least 6 of the 8 years 2018-2025
    hay_pasture  inside CSB fields coded 37 or 176 in at least 4 of the 8 years
    cdl_wetland  CDL Woody or Herbaceous Wetlands (190, 195) in 2024 or 2025
    hydric       SSURGO hydric share: listed on the card, decides nothing

`presence()` below turns those and the other support (an overlapping OSM wetland or NHD marsh) into kept, flagged or
retired. A polygon with no shares yet is `unchecked` and is not drawn: an unverified 1981 polygon never reaches the
map. Retired polygons stay in water.wetland_check with the reason and the shares, and `wetland-qa` lists them for
the owner's QA sheet (kept in the private files, never in the repository).
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date

from . import gpkg
from .sources import nwi

BUILD = "water-build"

# ---- the presence check's rules: the review's first guesses, to be tuned on the ten boxes ------------------------

BUILT_RETIRES = 0.5            # built this much or more: retired
BUILT_WITH_DEVELOPED = 0.25    # built this much with ...
DEVELOPED_RETIRES = 0.5        # ... developed this much and no wetland support: retired
CULTIVATED_RETIRES = 0.5       # cultivated this much and no support: retired; with support: kept, flagged
HAY_PASTURE_FLAGS = 0.5        # hay or pasture this much: kept, flagged
CDL_SUPPORT = 0.25             # CDL wetland classes over this share of the polygon count as support
SUPPORT_OVERLAP = 0.1          # an OSM wetland or NHD marsh overlapping this share of the polygon counts as support

ERA_OLD_BEFORE = 1999          # a project whose imagery is older than this is "old"
OVERLAP_SHARE = 0.5            # OSM and NWI outline one wetland when they overlap this much of the smaller of the two

PRESENCES = ("kept", "flagged", "retired", "unchecked")
REASONS = ("built", "farmed", "farmed_supported", "hay_pasture")
SHARES = ("built", "developed", "cultivated", "hay_pasture", "cdl_wetland")


def era_of(image_year, source_type=None):
    """'recent', 'old' or 'interim' for a mapping project (its image year and source type)."""
    if (source_type or "").lower() == "scalable" or image_year is None:
        return "interim"
    return "old" if image_year < ERA_OLD_BEFORE else "recent"


def checked_era(era):
    """Whether polygons of this era go through the presence check."""
    return era in ("old", "interim")


def presence(era, *, built=0.0, developed=0.0, cultivated=0.0, hay_pasture=0.0, support=False):
    """(presence, reason) for one polygon: ('kept', None), ('flagged', reason) or ('retired', reason). Recent and
    unknown eras are kept as mapped. Older ones, in order:
      retired as 'built' when built is half or more, or a quarter or more with developed at half or more and no
        support (CDL's developed classes never retire a polygon on their own);
      retired as 'farmed' when cultivated is half or more and there's no support; with support it stays, flagged
        'farmed_supported' ("in a crop field since at least 2018");
      kept, flagged 'hay_pasture', when hay or pasture is half or more (wet meadows are often hayed or grazed);
      kept otherwise."""
    if not checked_era(era):
        return "kept", None
    if built >= BUILT_RETIRES or (built >= BUILT_WITH_DEVELOPED and developed >= DEVELOPED_RETIRES and not support):
        return "retired", "built"
    if cultivated >= CULTIVATED_RETIRES:
        return ("flagged", "farmed_supported") if support else ("retired", "farmed")
    if hay_pasture >= HAY_PASTURE_FLAGS:
        return "flagged", "hay_pasture"
    return "kept", None


def is_thin(era, mapping_from_nhd=False):
    """The thinned tuft: older mapping (1981-83 photos, the interim product) and NHD's topo-era marsh alone."""
    return checked_era(era) or mapping_from_nhd


# ---- Cowardin codes ---------------------------------------------------------------------------------------------
# From the published standard (Cowardin et al. 1979; FGDC-STD-004): system P, a class with an optional subclass
# digit, optionally a second class after '/', a water regime letter and lower-case special modifiers.

CLASSES = {
    "EM": "emergent wetland (marsh or wet meadow)",
    "SS": "scrub-shrub wetland",
    "FO": "forested wetland",
    "AB": "aquatic bed",
    "UB": "unconsolidated bottom (pond)",
    "US": "unconsolidated shore",
    "OW": "open water",
    "ML": "moss-lichen wetland",
    "RS": "rock shore",
    "RB": "rock bottom",
}
SUBCLASSES = {
    "EM": {"1": "persistent", "2": "non-persistent"},
    "SS": {"1": "broad-leaved deciduous", "2": "needle-leaved deciduous", "3": "broad-leaved evergreen",
           "4": "needle-leaved evergreen", "5": "dead", "6": "deciduous", "7": "evergreen"},
    "FO": {"1": "broad-leaved deciduous", "2": "needle-leaved deciduous", "3": "broad-leaved evergreen",
           "4": "needle-leaved evergreen", "5": "dead", "6": "deciduous", "7": "evergreen"},
    "AB": {"1": "algal", "2": "aquatic moss", "3": "rooted vascular", "4": "floating vascular"},
    "UB": {"1": "cobble-gravel", "2": "sand", "3": "mud", "4": "organic"},
    "US": {"1": "cobble-gravel", "2": "sand", "3": "mud", "4": "organic", "5": "vegetated"},
}
REGIMES = {
    "A": "temporarily flooded", "B": "saturated", "C": "seasonally flooded", "D": "continuously saturated",
    "E": "seasonally flooded and saturated", "F": "semipermanently flooded", "G": "intermittently exposed",
    "H": "permanently flooded", "J": "intermittently flooded", "K": "artificially flooded",
    "W": "intermittently flooded and temporary", "Y": "saturated and semipermanently flooded",
    "Z": "intermittently exposed and permanently flooded", "U": "unknown",
}
MODIFIERS = {
    "b": "beaver-built", "d": "partly drained or ditched", "f": "farmed", "h": "diked or impounded",
    "r": "artificial substrate", "s": "spoil", "x": "excavated",
}
_CODE = re.compile(r"^P(?P<c1>[A-Z]{2})(?P<s1>\d?)(?:/(?P<c2>[A-Z]{2})(?P<s2>\d?))?(?P<regime>[A-Z]?)(?P<mods>[a-z]*)$")
VEGETATED = ("EM", "SS", "FO")


class CodeError(ValueError):
    pass


def parse_code(code):
    """{'cls', 'sub', 'cls2', 'sub2', 'regime', 'modifiers'} for a palustrine Cowardin code such as 'PEM1C',
    'PEM1/SSC' or 'PSS1Ch'. Raises CodeError for anything else."""
    m = _CODE.match((code or "").strip())
    if not m:
        raise CodeError(f"not a palustrine Cowardin code: {code!r}")
    d = m.groupdict()
    for c in (d["c1"], d["c2"]):
        if c is not None and c not in CLASSES:
            raise CodeError(f"{code!r}: unknown class {c}")
    if d["regime"] and d["regime"] not in REGIMES:
        raise CodeError(f"{code!r}: unknown water regime {d['regime']}")
    if bad := [x for x in d["mods"] if x not in MODIFIERS]:
        raise CodeError(f"{code!r}: unknown modifier {bad[0]}")
    return {"cls": d["c1"], "sub": d["s1"] or None, "cls2": d["c2"], "sub2": d["s2"] or None,
            "regime": d["regime"] or None, "modifiers": d["mods"]}


def is_vegetated(code):
    """Whether the code's first class is emergent, scrub-shrub or forested (and the system palustrine)."""
    try:
        return parse_code(code)["cls"] in VEGETATED
    except CodeError:
        return False


def describe(code):
    """The class in words, for the card: 'Freshwater emergent wetland (marsh or wet meadow), seasonally flooded'.
    A subclass is named except the common persistent emergent one (EM1); a second class reads 'mixed with ...'; special
    modifiers come last in brackets. Raises CodeError for a code it can't read."""
    p = parse_code(code)
    text = "Freshwater " + CLASSES[p["cls"]]
    sub = SUBCLASSES.get(p["cls"], {}).get(p["sub"] or "")
    if sub and not (p["cls"] == "EM" and p["sub"] == "1"):
        text += f", {sub}"
    if p["cls2"]:
        text += f", mixed with {CLASSES[p['cls2']].split(' (')[0]}"
    if p["regime"]:
        text += f", {REGIMES[p['regime']]}"
    if p["modifiers"]:
        text += " (" + ", ".join(MODIFIERS[x] for x in p["modifiers"]) + ")"
    return text


# ---- zoom and generalisation ------------------------------------------------------------------------------------

TUFT_Z = 14                    # tufts from z14
THIN_Z = 15                    # thinned tufts from z15
MAX_Z = 16
SIMPLIFY_M = 1.0               # NWI outlines are simplified to this tolerance (under a z16 pixel, 1.8 m at this latitude)
MIN_AREA_M2 = 60.0             # NWI-only polygons under this are dropped: under about 20 pixels even at z16
PIXELS = 20                    # a wetland draws from the first zoom at which it covers this many pixels
EQUATOR_M_PER_PX_Z0 = 156543.03 * 0.7254   # the Web Mercator pixel at 43.4 degrees north, zoom 0 (cos 43.5)


def wetland_minzoom(area_m2, thin=False):
    """First zoom of a wetland: z14 (tufts) or z15 (thinned tufts), later for a small one so that it covers about
    PIXELS pixels where it first draws; at most z16. This is the per-zoom generalisation that keeps the bake inside
    its byte budget: the valley's small polygons appear only when they're big enough on screen to read as tufts."""
    base = THIN_Z if thin else TUFT_Z
    z = base
    while z < MAX_Z and area_m2 < PIXELS * (EQUATOR_M_PER_PX_Z0 / 2 ** z) ** 2:
        z += 1
    return z


# ---- loading NWI ------------------------------------------------------------------------------------------------

class LoadError(ValueError):
    pass


ACCEPTED_SRS = (100000, 100001, 5070)       # NWI's NAD83 Albers, as FWS labels it and as EPSG:5070
WETLAND_COLUMNS = ("NWI_ID", "ATTRIBUTE", "WETLAND_TYPE", "ACRES", "hu8")
PROJECT_COLUMNS = ("PROJECT_NAME", "IMAGE_YR", "IMAGE_DATE", "IMAGE_SCALE", "SOURCE_TYPE", "hu8")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def part_keys(ids):
    """Unique keys for NWI_IDs, which several features may share (parts of one mapped wetland): the NWI_ID, then
    NWI_ID#2, #3 in the order given."""
    seen, out = {}, []
    for i in ids:
        seen[i] = seen.get(i, 0) + 1
        out.append(i if seen[i] == 1 else f"{i}#{seen[i]}")
    return out


def read(path):
    """(wetlands, projects, skipped) from the GeoPackage. wetlands: tuples (key, nwi_id, attribute, wetland_type,
    acres, hu8, wkb) of the vegetated palustrine polygons only; projects: (hu8, name, year, date, scale, source_type,
    wkb); skipped: counts of what was left out and why."""
    with gpkg.open_ro(path) as g:
        have = gpkg.tables(g)
        if missing := sorted({"wetlands", "project_metadata"} - set(have)):
            raise LoadError(f"{path}: no {', '.join(missing)} table: is it the NWI cut (nwi_mapbox.gpkg)?")
        geoms = gpkg.feature_tables(g)
        for t in ("wetlands", "project_metadata"):
            if geoms[t][2] not in ACCEPTED_SRS:
                raise LoadError(f"{path}: {t} is in SRS {geoms[t][2]}, not NWI's NAD83 Albers")
        skipped = {"not vegetated palustrine": 0, "no geometry": 0, "no code": 0}
        rows = []
        for r in gpkg.rows(g, "wetlands", list(WETLAND_COLUMNS) + ["geom"]):
            code = (r["ATTRIBUTE"] or "").strip()
            if not code:
                skipped["no code"] += 1
            elif not is_vegetated(code):
                skipped["not vegetated palustrine"] += 1
            elif r["geom"] is None:
                skipped["no geometry"] += 1
            else:
                rows.append((r["NWI_ID"], code, (r["WETLAND_TYPE"] or "").strip() or None, r["ACRES"],
                             r["hu8"], r["geom"]))
        keys = part_keys([r[0] for r in rows])
        wetlands = [(k, r[0], r[1], r[2], r[3], r[4], r[5]) for k, r in zip(keys, rows)]
        projects = []
        for r in gpkg.rows(g, "project_metadata", list(PROJECT_COLUMNS) + ["geom"]):
            if r["geom"] is not None:
                projects.append((r["hu8"], r["PROJECT_NAME"], r["IMAGE_YR"], r["IMAGE_DATE"], r["IMAGE_SCALE"],
                                 r["SOURCE_TYPE"], r["geom"]))
    if not wetlands:
        raise LoadError(f"{path}: no vegetated palustrine wetlands")
    return wetlands, projects, skipped


GEOM_SQL = ("ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(ST_Force2D(ST_SetSRID(ST_GeomFromWKB(wkb), 5070)), "
            "4326)), 3))")
ERA_SQL = (f"case when p.image_year is null or lower(coalesce(p.source_type, '')) = 'scalable' then 'interim' "
           f"when p.image_year < {ERA_OLD_BEFORE} then 'old' else 'recent' end")


def load(conn, path, force=False, dry_run=False):
    """Load the cut in one transaction (commits unless dry_run). NWI's NAD83 coordinates are read as WGS 84 (the
    ground's null datum shift, basemap/ground/README.md); the Albers projection itself is undone exactly."""
    from ingest import db
    if not conn.execute("select to_regclass('water.nwi_wetland') is not null").fetchone()[0]:
        raise LoadError("water.nwi_wetland is missing: apply water 0003 (python3 db/migrate.py)")
    digest = sha256(path)
    wetlands, projects, skipped = read(path)
    last = conn.execute("select sha256 from water.load where source = 'nwi' order by id desc limit 1").fetchone()
    if last and last[0] == digest and not force:
        return {"loaded": "nothing", "why": f"{os.path.basename(path)} (sha256 {digest[:12]}) is the file loaded last; "
                                           "--force reloads it"}
    counts = {"wetlands": len(wetlands), "projects": len(projects), **{f"skipped, {k}": v for k, v in skipped.items()}}
    if dry_run:
        return {"would load": counts}
    db.ensure_source(conn, nwi.SOURCE)
    conn.commit()
    prep = {"input": {"file": nwi.INPUT_NOTE}, "kept": os.path.basename(path)}
    with db.Fetch(conn, nwi.SOURCE["name"]) as f:        # no request made: robots and status stay empty
        f.bytes = os.path.getsize(path)
        with conn.cursor() as cur:
            load_id = cur.execute(
                """insert into water.load (source, file, sha256, prepared, counts, fetch_id)
                   values ('nwi', %s, %s, %s::jsonb, %s::jsonb, %s) returning id""",
                (os.path.basename(path), digest, json.dumps(prep), json.dumps(counts), f.id)).fetchone()[0]
            cur.execute("delete from water.nwi_project")
            cur.execute("drop table if exists pg_temp.nwi_stage_p")
            cur.execute("drop table if exists pg_temp.nwi_stage_w")
            cur.execute("create temp table nwi_stage_p (hu8 text, name text, image_year smallint, image_date text, "
                        "image_scale integer, source_type text, wkb bytea) on commit drop")
            with cur.copy("copy nwi_stage_p from stdin") as cp:
                for r in projects:
                    cp.write_row(r)
            cur.execute(f"""insert into water.nwi_project (load_id, hu8, name, image_year, image_date, image_scale,
                              source_type, geom)
                            select %s, hu8, name, image_year, nullif(image_date, '<Null>'), image_scale,
                                   source_type, {GEOM_SQL} from nwi_stage_p""", (load_id,))
            cur.execute("create temp table nwi_stage_w (key text, nwi_id text, attribute text, wetland_type text, "
                        "acres real, hu8 text, wkb bytea) on commit drop")
            with cur.copy("copy nwi_stage_w from stdin") as cp:
                for r in wetlands:
                    cp.write_row(r)
            # A polygon whose outline changed loses its presence shares (they were measured on the old outline).
            cur.execute(f"""delete from water.nwi_presence pr using nwi_stage_w s, water.nwi_wetland w
                            where pr.key = s.key and w.key = s.key
                              and not ST_Equals(w.geom, {GEOM_SQL.replace('wkb', 's.wkb')})""")
            cur.execute("delete from water.nwi_wetland w where not exists (select 1 from nwi_stage_w s "
                        "where s.key = w.key)")
            cur.execute(f"""insert into water.nwi_wetland (key, nwi_id, attribute, wetland_type, acres, hu8, era,
                              geom, load_id)
                            select key, nwi_id, attribute, wetland_type, acres, hu8, 'unknown', {GEOM_SQL}, %s
                            from nwi_stage_w
                            on conflict (key) do update set nwi_id = excluded.nwi_id, attribute = excluded.attribute,
                              wetland_type = excluded.wetland_type, acres = excluded.acres, hu8 = excluded.hu8,
                              geom = excluded.geom, load_id = excluded.load_id""", (load_id,))
            cur.execute("delete from water.nwi_wetland where ST_IsEmpty(geom)")
            # The newest project polygon that holds the wetland's point says how it was mapped.
            cur.execute(f"""update water.nwi_wetland w set project = p.name, image_year = p.image_year, era = {ERA_SQL}
                            from (select distinct on (w2.key) w2.key, pr.name, pr.image_year, pr.source_type
                                  from water.nwi_wetland w2 join water.nwi_project pr
                                    on ST_Intersects(pr.geom, ST_PointOnSurface(w2.geom))
                                  order by w2.key, pr.image_year desc nulls last) p
                            where p.key = w.key""")
            cur.execute("update water.nwi_wetland set project = null, image_year = null, era = 'unknown' "
                        "where load_id = %s and not exists (select 1 from water.nwi_project pr "
                        "where ST_Intersects(pr.geom, ST_PointOnSurface(nwi_wetland.geom)))", (load_id,))
            stored = dict(cur.execute("select era, count(*) from water.nwi_wetland group by era").fetchall())
            n = sum(stored.values())
            if n < len(wetlands) * 0.99:
                raise LoadError(f"rows lost on the way in: {len(wetlands)} read, {n} stored")
            cur.execute("update water.load set counts = %s::jsonb where id = %s",
                        (json.dumps({**counts, "stored by era": stored}), load_id))
            if cur.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
                from ingest import builds
                builds.mark(conn, BUILD, by="nwi", reason=f"NWI loaded from {os.path.basename(path)} "
                                                          f"(sha256 {digest[:12]})")
        f.records = n
    return {"load": load_id, **{f"era {k}": v for k, v in sorted(stored.items())}, "projects": len(projects),
            **{f"skipped, {k}": v for k, v in skipped.items() if v}}


# ---- loading the presence shares --------------------------------------------------------------------------------

def read_shares(path):
    """(computed_on, inputs, rows) from the worker's JSON: rows are (key, built, developed, cultivated, hay_pasture,
    cdl_wetland, hydric). Raises LoadError for a share outside 0 to 1 or a missing field."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as err:
        raise LoadError(f"{path}: {err}") from None
    try:
        computed_on = date.fromisoformat(doc["computed_on"])
    except (KeyError, TypeError, ValueError):
        raise LoadError(f"{path}: computed_on must be a date (YYYY-MM-DD)") from None
    rows = []
    for i, p in enumerate(doc.get("polygons") or []):
        if not isinstance(p, dict) or not p.get("key"):
            raise LoadError(f"{path}: polygon {i} has no key")
        vals = []
        for name in SHARES:
            v = p.get(name)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v <= 1:
                raise LoadError(f"{path}: polygon {p['key']}: {name} must be a number from 0 to 1, not {v!r}")
            vals.append(float(v))
        h = p.get("hydric")
        if h is not None and (not isinstance(h, (int, float)) or isinstance(h, bool) or not 0 <= h <= 1):
            raise LoadError(f"{path}: polygon {p['key']}: hydric must be a number from 0 to 1, not {h!r}")
        rows.append((p["key"], *vals, None if h is None else float(h)))
    if not rows:
        raise LoadError(f"{path}: no polygons")
    if len({r[0] for r in rows}) != len(rows):
        raise LoadError(f"{path}: a key appears twice")
    return computed_on, doc.get("inputs") or {}, rows


def load_shares(conn, path, dry_run=False):
    """Store the shares (replacing those of the keys given). Keys that aren't NWI polygons we hold are an error."""
    computed_on, inputs, rows = read_shares(path)
    with conn.cursor() as cur:
        cur.execute("drop table if exists pg_temp.nwi_stage_s")
        cur.execute("create temp table nwi_stage_s (key text, built real, developed real, cultivated real, "
                    "hay_pasture real, cdl_wetland real, hydric real) on commit drop")
        with cur.copy("copy nwi_stage_s from stdin") as cp:
            for r in rows:
                cp.write_row(r)
        unknown = [k for (k,) in cur.execute("select s.key from nwi_stage_s s left join water.nwi_wetland w "
                                             "using (key) where w.key is null limit 5").fetchall()]
        if unknown:
            raise LoadError(f"keys that aren't loaded NWI polygons (nwi-load first?): {unknown}")
        if dry_run:
            return {"would store": len(rows)}
        cur.execute("""insert into water.nwi_presence (key, built, developed, cultivated, hay_pasture, cdl_wetland,
                         hydric, computed_on, inputs)
                       select key, built, developed, cultivated, hay_pasture, cdl_wetland, hydric, %s, %s::jsonb
                       from nwi_stage_s
                       on conflict (key) do update set built = excluded.built, developed = excluded.developed,
                         cultivated = excluded.cultivated, hay_pasture = excluded.hay_pasture,
                         cdl_wetland = excluded.cdl_wetland, hydric = excluded.hydric,
                         computed_on = excluded.computed_on, inputs = excluded.inputs""",
                    (computed_on, json.dumps(inputs)))
        if cur.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]:
            from ingest import builds
            builds.mark(conn, BUILD, by="nwi", reason=f"presence shares loaded ({len(rows)} polygons)")
    return {"stored": len(rows), "computed_on": str(computed_on)}


# ---- what the build reads ---------------------------------------------------------------------------------------

SUPPORT_SQL = f"""
select w.key, w.attribute, w.era, p.key is not null checked, p.built, p.developed, p.cultivated, p.hay_pasture,
       p.cdl_wetland,
       exists (select 1 from water.osm_feature o
               where o.active and o.shape = 'area' and o.kind = 'wetland' and ST_Intersects(o.geom, w.geom)
                 and ST_Area(ST_Intersection(ST_MakeValid(o.geom), w.geom)) >= {SUPPORT_OVERLAP} * ST_Area(w.geom))
         osm,
       exists (select 1 from water.nhd_polygon n
               where n.ftype_name = 'Swamp/Marsh' and ST_Intersects(n.geom, w.geom)
                 and ST_Area(ST_Intersection(ST_MakeValid(n.geom), w.geom)) >= {SUPPORT_OVERLAP} * ST_Area(w.geom))
         nhd
from water.nwi_wetland w left join water.nwi_presence p using (key)"""


def verdict(row):
    """The build's call on one row of SUPPORT_SQL (a dict): presence, reason, drawn, thin, the support found and the
    code's regime and modifiers."""
    support = [s for s, on in (("cdl", (row["cdl_wetland"] or 0) >= CDL_SUPPORT), ("osm", row["osm"]),
                               ("nhd", row["nhd"])) if on]
    try:
        p = parse_code(row["attribute"])
    except CodeError:
        p = {"regime": None, "modifiers": ""}
    out = {"key": row["key"], "era": row["era"], "support": support, "regime": p["regime"],
           "modifiers": p["modifiers"] or None}
    if checked_era(row["era"]) and not row["checked"]:
        return {**out, "presence": "unchecked", "reason": None, "drawn": False, "thin": False}
    pres, reason = presence(row["era"], built=row["built"] or 0.0, developed=row["developed"] or 0.0,
                            cultivated=row["cultivated"] or 0.0, hay_pasture=row["hay_pasture"] or 0.0,
                            support=bool(support))
    return {**out, "presence": pres, "reason": reason, "drawn": pres != "retired", "thin": is_thin(row["era"])}


def prepare(conn, out=print):
    """Create the temp table w_verdict for the build: one row per NWI polygon with its presence call. Returns the
    counts the build records. Does nothing (an empty table) when no NWI has been loaded."""
    cur = conn.execute(SUPPORT_SQL)
    cols = [c.name for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.execute("""create temp table w_verdict (key text primary key, era text, presence text, reason text,
                      drawn boolean, thin boolean, regime text, modifiers text, support text[],
                      built real, developed real, cultivated real, hay_pasture real, cdl_wetland real)
                    on commit drop""")
    stats = {"nwi_polygons": len(rows), "nwi_kept": 0, "nwi_flagged": 0, "nwi_retired": 0, "nwi_unchecked": 0}
    with conn.cursor() as cur2:
        with cur2.copy("copy w_verdict from stdin") as cp:
            for r in rows:
                v = verdict(r)
                stats["nwi_" + v["presence"]] += 1
                cp.write_row((v["key"], v["era"], v["presence"], v["reason"], v["drawn"], v["thin"], v["regime"],
                              v["modifiers"], "{" + ",".join(v["support"]) + "}", r["built"], r["developed"],
                              r["cultivated"], r["hay_pasture"], r["cdl_wetland"]))
    conn.execute("analyze w_verdict")
    if stats["nwi_unchecked"]:
        out(f"water-build: {stats['nwi_unchecked']} old-mapped NWI polygons have no presence shares yet "
            "(nwi-presence): they are not drawn")
    return stats


# ---- the QA sheet's rows ----------------------------------------------------------------------------------------

QA_SQL = """
select c.key, w.attribute, w.era, w.image_year, w.project, w.acres, c.presence, c.reason, c.drawn,
       c.built, c.developed, c.cultivated, c.hay_pasture, c.cdl_wetland, c.support,
       round(ST_X(ST_PointOnSurface(w.geom))::numeric, 6) lon, round(ST_Y(ST_PointOnSurface(w.geom))::numeric, 6) lat
from water.wetland_check c join water.nwi_wetland w using (key)
where c.build_id = %(build)s and c.era in ('old', 'interim')
order by (c.presence = 'retired') desc, c.reason nulls last, w.project, c.key"""
QA_COLUMNS = ("key", "attribute", "era", "image_year", "project", "acres", "presence", "reason", "drawn", "built",
              "developed", "cultivated", "hay_pasture", "cdl_wetland", "support", "lon", "lat")


def box_counts(conn, build_id, boxes):
    """{box id: {presence or 'unchecked': count}} of the old and interim polygons whose point lies in each box.
    boxes: {id: (west, south, east, north)} in EPSG:32611, as basemap.sheets.places gives them."""
    out = {}
    for bid, (w, s, e, n) in boxes.items():
        rows = conn.execute(
            """select c.presence, count(*) from water.wetland_check c join water.nwi_wetland k using (key)
               where c.build_id = %s and c.era in ('old', 'interim')
                 and ST_Intersects(ST_Transform(ST_PointOnSurface(k.geom), 32611),
                                   ST_MakeEnvelope(%s, %s, %s, %s, 32611))
               group by 1""", (build_id, w, s, e, n)).fetchall()
        out[bid] = dict(rows)
    return out


def write_qa(conn, build_id, out_dir):
    """Write qa-old-mapped.csv (every old or interim polygon's outcome, the retired first) into out_dir, which
    belongs in the private files. Returns the path and the number of rows."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "qa-old-mapped.csv")
    cur = conn.execute(QA_SQL, {"build": build_id})
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(QA_COLUMNS)
        for r in cur:
            w.writerow([",".join(x) if isinstance(x, list) else x for x in r])
            n += 1
    return path, n


def qa_main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest wetland-qa",
                                 description="the presence check's counts and the QA sheet's rows for a water-build")
    ap.add_argument("--build", type=int, help="a water.build id (default: the newest finished one)")
    ap.add_argument("--out", help="a folder in the private files for qa-old-mapped.csv (never in the repository)")
    ap.add_argument("--boxes", action="store_true", help="counts per test box (basemap.sheets.places)")
    args = ap.parse_args(argv)
    from ingest import db
    with db.connect() as conn:
        build_id = args.build or (conn.execute("select max(id) from water.build where finished_at is not null")
                                  .fetchone()[0])
        if build_id is None:
            print("wetland-qa: no finished water-build", file=sys.stderr)
            return 1
        by = dict(conn.execute("select presence || coalesce('/' || reason, ''), count(*) from water.wetland_check "
                               "where build_id = %s and era in ('old', 'interim') group by 1 order by 1",
                               (build_id,)).fetchall())
        print(f"wetland-qa: build {build_id}: old and interim polygons by outcome: {json.dumps(by)}")
        if args.boxes:
            from basemap.sheets import places
            boxes = {f.box or f.id: f.bounds for f in places.select(["boxes"])}
            for b, c in box_counts(conn, build_id, boxes).items():
                print(f"  box {b}: {json.dumps(c)}")
        if args.out:
            path, n = write_qa(conn, build_id, args.out)
            print(f"wetland-qa: {n} rows in {path}")
    return 0


# ---- command line -----------------------------------------------------------------------------------------------

def load_main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest nwi-load", description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="path", required=True, help="nwi_mapbox.gpkg, the NWI cut kept on the server")
    ap.add_argument("--force", action="store_true", help="load it even if it's the file loaded last")
    ap.add_argument("--dry-run", action="store_true", help="read the file and say what would load")
    args = ap.parse_args(argv)
    from ingest import db
    try:
        with db.connect() as conn:
            stats = load(conn, args.path, force=args.force, dry_run=args.dry_run)
    except (LoadError, gpkg.GpkgError) as err:
        print(f"nwi-load: {err}", file=sys.stderr)
        return 1
    print("nwi-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


def presence_main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest nwi-presence",
                                 description="load the presence check's shares the worker step wrote")
    ap.add_argument("--from", dest="path", required=True, help="the shares JSON")
    ap.add_argument("--dry-run", action="store_true", help="check the file and say what would load")
    args = ap.parse_args(argv)
    from ingest import db
    try:
        with db.connect() as conn:
            stats = load_shares(conn, args.path, dry_run=args.dry_run)
    except LoadError as err:
        print(f"nwi-presence: {err}", file=sys.stderr)
        return 1
    print("nwi-presence: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0


if __name__ == "__main__":
    sys.exit(load_main())
