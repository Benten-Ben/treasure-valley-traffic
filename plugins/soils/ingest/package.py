"""A prepared soil survey: read it, check it, and derive what the soils tables hold. Standard library only.

plugins/soils/build/prepare.py (the worker image, GDAL) turns the Web Soil Survey packages into a folder of plain files:

    prepare.json        what's in it: FORMAT, the box, each survey area (symbol, name, saverest, version, scale,
                        source URL, counts), each output file's sha256 and rows, each input file's sha256
    polygons.geojsonl   one GeoJSON Feature per line: a map-unit polygon touching the map box, kept whole, in WGS 84
                        (EPSG:4326, 7 decimals), properties {id, areasymbol, fid, mukey, musym}; id = areasymbol:fid
    tabular/<table>.csv the rows of each table below for the map units those polygons belong to, with a header row:
                        `areasymbol`, then the table's SSURGO columns (named as in its mdstattabcols)

`read()` opens it and checks every file against its sha256; `derive()` makes the rows of soils.map_unit,
soils.component, soils.horizon and soils.ground_type from the tables (plugins/soils/migrations/0001_soils.sql says
what each column means). The load itself is ingest/load.py.
"""

import csv
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime

FORMAT = "tvt-soils-prepared/1"
BOX = (-117.05, 43.0, -115.95, 43.85)      # the map box (basemap/build.sh; /srv/tvt/tiles/manifest.json)
POLYGONS = "polygons.geojsonl"
MANIFEST = "prepare.json"

# The SSURGO tables (2.3.3) a prepared package carries, and the columns the loader reads from each. prepare.py copies
# every column; these must be there.
TABLES = {
    "mapunit": ("mukey", "musym", "muname", "mukind", "farmlndcl"),
    "muaggatt": ("mukey", "slopegraddcp", "aws025wta", "aws050wta", "aws0100wta", "drclassdcd", "hydgrpdcd",
                 "flodfreqdcd", "pondfreqprs", "brockdepmin", "wtdepannmin", "iccdcd", "niccdcd", "hydclprs"),
    "component": ("cokey", "mukey", "compname", "compkind", "comppct_r", "majcompflag", "slope_l", "slope_r",
                  "slope_h", "drainagecl", "hydgrp", "hydricrating", "irrcapcl", "irrcapscl", "nirrcapcl",
                  "nirrcapscl", "taxclname", "taxorder", "earthcovkind1", "ffd_r", "albedodry_r", "elev_r", "map_r"),
    "corestrictions": ("corestrictkey", "cokey", "reskind", "reshard", "resdept_r", "resdepb_r"),
    "cosurffrags": ("cokey", "sfragcov_r"),
    "copmgrp": ("copmgrpkey", "cokey", "pmgroupname", "rvindicator"),
    "copm": ("copmgrpkey", "pmorder", "pmkind"),
    "cogeomordesc": ("cokey", "geomftname", "geomfname", "rvindicator"),
    "coecoclass": ("coecoclasskey", "cokey", "ecoclasstypename", "ecoclassid", "ecoclassname"),
    "cocropyld": ("cokey", "cropname", "yldunits", "irryield_r", "nonirryield_r"),
    "chorizon": ("chkey", "cokey", "hzname", "desgnmaster", "hzdept_r", "hzdepb_r", "sandtotal_r", "silttotal_r",
                 "claytotal_r", "om_r", "ph1to1h2o_r", "caco3_r", "gypsum_r", "ec_r", "sar_r", "awc_r", "ksat_r",
                 "kwfact", "fraggt10_r", "frag3to10_r"),
    "chtexturegrp": ("chtgkey", "chkey", "texture", "texdesc", "rvindicator"),
    "chtexture": ("chtkey", "chtgkey", "texcl", "lieutex"),
    "chtexturemod": ("chtkey", "texmod"),
}

# Restrictive layers (corestrictions.reskind) that limit roots outright: what "Hardpan or bedrock depth" shows.
# Others (an abrupt textural change, a natric horizon, ...) stay in the component's restrictions list.
HARDPAN = {"duripan", "petrocalcic", "petrogypsic", "cemented horizon", "ortstein", "placic", "petroferric",
           "fragipan"}
BEDROCK = {"lithic bedrock", "paralithic bedrock", "densic bedrock"}

# The show-by codes (soils.map_unit.c_*): 0 is the palest step of the wash, the highest the darkest. Darker means a
# shallower hardpan or bedrock, wetter, more water held, better farmland, more runoff.
DEPTH_BREAKS_CM = (25, 50, 100, 150)   # NRCS depth classes: very shallow, shallow, moderately deep, deep, very deep
DRAINAGE = {"excessively drained": 0, "somewhat excessively drained": 0, "well drained": 1,
            "moderately well drained": 2, "somewhat poorly drained": 3, "poorly drained": 4,
            "very poorly drained": 4, "subaqueous": 4}
# Available water storage, 0-100 cm, in cm: very low, low, moderate, high, very high. ⚠️ Our scaling of the Soil
# Survey Manual's classes for a 150 cm (60 in) profile (3, 6, 9 and 12 in) to the top metre.
AWS_BREAKS_CM = (5, 10, 15, 20)
HSG = {"A": 0, "B": 1, "C": 2, "D": 3}
MISC = (("water", "water"), ("urban", "urban"), ("rock outcrop", "rock"), ("badland", "badland"),
        ("rubble", "rubble"), ("pit", "pits"))


class PackageError(ValueError):
    pass


# ---- values ------------------------------------------------------------------------------------------------------

def text(v):
    """A SSURGO string: stripped, '' as None."""
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def whole(v):
    """A whole number (SSURGO's integer columns, rounded); None when missing."""
    x = num(v)
    return None if x is None else int(round(x))


def yes(v):
    v = text(v)
    return None if v is None else v.lower() == "yes"


def saverest(v):
    """NRCS's 'MM/DD/YYYY HH:MM:SS' (sacatalog.saverest) as an ISO timestamp, no zone."""
    return datetime.strptime(v.strip(), "%m/%d/%Y %H:%M:%S").isoformat()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def ground_type_id(series, texture):
    """'purdam:silt-loam': the dominant component's name and its surface texture with modifier, as one key.
    Miscellaneous areas have no texture: 'water', 'urban-land'."""
    s, t = slug(series), slug(texture)
    if not s:
        return None
    return f"{s}:{t}" if t else s


def misc_kind(compname, compkind):
    """For a miscellaneous area (Water, Urban land, Rock outcrop, Badland, Rubble land, Pits, ...): its kind."""
    if (text(compkind) or "").lower() != "miscellaneous area":
        return None
    name = (compname or "").lower()
    for needle, kind in MISC:
        if needle in name:
            return kind
    return "other"


def bin_index(value, breaks):
    """0 below breaks[0], 1 below breaks[1], ..., len(breaks) at or above the last."""
    return sum(1 for b in breaks if value >= b)


def depth_code(top_cm):
    """c_restr: 0 none within 150 cm, 1 at 100-150, 2 at 50-100, 3 at 25-50, 4 under 25 cm."""
    if top_cm is None:
        return 0
    return len(DEPTH_BREAKS_CM) - bin_index(top_cm, DEPTH_BREAKS_CM)


def aws_code(cm):
    return None if cm is None else bin_index(cm, AWS_BREAKS_CM)


def drainage_code(cls):
    return DRAINAGE.get((text(cls) or "").lower())


def hsg_code(group):
    """(c_hsg, dual) from a hydrologic group: 'C' -> (2, False); 'A/D' -> (0, True), the group when drained, hatched
    because it's D where undrained."""
    g = (text(group) or "").upper()
    if not g:
        return None, None
    first = g.split("/")[0].strip()
    if first not in HSG:
        return None, None
    return HSG[first], "/" in g


def farm_code(farmlndcl):
    """(c_farm, farm_cond) from mapunit.farmlndcl. c_farm: 0 not prime, 1 of statewide, local or unique importance,
    2 prime. farm_cond names the condition the class needs: 'reclaimed' (of excess salts and sodium), 'drained',
    'protected' (from flooding), 'irrigated', 'other', or None for none. The wash hatches 'drained' and 'reclaimed'."""
    v = (text(farmlndcl) or "").lower()
    if not v:
        return None, None
    if v.startswith("not prime"):
        return 0, None
    if v.startswith("all areas are prime") or v.startswith("prime farmland"):
        code = 2
    elif v.startswith("farmland of"):
        code = 1
    else:
        return None, None
    cond = v.split(" if ", 1)[1] if " if " in v else ""
    if not cond:
        return code, None
    for needle, name in (("reclaimed", "reclaimed"), ("drained", "drained"), ("protected", "protected"),
                         ("flooded", "protected"), ("irrigated", "irrigated")):
        if needle in cond:
            return code, name
    return code, "other"


# ---- the package -------------------------------------------------------------------------------------------------

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class Package:
    """A prepared folder. `meta` is prepare.json; `areas` its survey areas by symbol."""

    def __init__(self, folder, meta):
        self.folder, self.meta = folder, meta
        self.areas = {a["areasymbol"]: a for a in meta["areas"]}
        self._tables = {}

    def path(self, name):
        return os.path.join(self.folder, name)

    def table(self, name):
        """A table's rows as dicts (every column, strings as written), cached."""
        if name not in self._tables:
            with open(self.path(f"tabular/{name}.csv"), newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self._tables[name] = rows
        return self._tables[name]

    def polygons(self, areas=None):
        """(id, areasymbol, mukey, geometry as GeoJSON text) for each polygon, in file order."""
        with open(self.path(POLYGONS), encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                feat = json.loads(line)
                p = feat.get("properties") or {}
                geom = feat.get("geometry") or {}
                if geom.get("type") not in ("Polygon", "MultiPolygon"):
                    raise PackageError(f"{POLYGONS} line {n}: a {geom.get('type')}, not a polygon")
                if areas is not None and p.get("areasymbol") not in areas:
                    continue
                yield p["id"], p["areasymbol"], str(p["mukey"]), json.dumps(geom, separators=(",", ":"))


def read(folder, check=True):
    """Open a prepared folder. With check, every file listed in prepare.json must match its sha256, and every
    table the loader reads must be there with its columns."""
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError) as err:
        raise PackageError(f"{folder}: no readable {MANIFEST} ({err}); run plugins/soils/build/prepare.py first")
    if meta.get("format") != FORMAT:
        raise PackageError(f"{folder}: format {meta.get('format')!r}, expected {FORMAT!r}")
    if [round(x, 6) for x in meta.get("box", [])] != list(BOX):
        raise PackageError(f"{folder}: prepared for the box {meta.get('box')}, not {list(BOX)}")
    files = meta.get("files") or {}
    needed = [POLYGONS] + [f"tabular/{t}.csv" for t in TABLES]
    if missing := [n for n in needed if n not in files]:
        raise PackageError(f"{folder}: prepare.json lists no {', '.join(missing)}")
    if not meta.get("areas"):
        raise PackageError(f"{folder}: no survey areas")
    pkg = Package(folder, meta)
    if check:
        for name, info in sorted(files.items()):
            got = sha256(pkg.path(name))
            if got != info["sha256"]:
                raise PackageError(f"{folder}/{name}: sha256 {got[:12]}..., prepare.json says {info['sha256'][:12]}...")
        for table, cols in TABLES.items():
            with open(pkg.path(f"tabular/{table}.csv"), newline="", encoding="utf-8") as f:
                header = next(csv.reader(f), [])
            if missing := [c for c in ("areasymbol",) + cols if c not in header]:
                raise PackageError(f"{folder}/tabular/{table}.csv: no column(s) {', '.join(missing)}")
    return pkg


# ---- deriving the rows -------------------------------------------------------------------------------------------

def _group(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def dominant(components):
    """The dominant component: the largest share; ties go to a major component, then the lowest cokey."""
    if not components:
        return None
    return sorted(components, key=lambda c: (-(num(c["comppct_r"]) or 0), yes(c["majcompflag"]) is not True,
                                             c["cokey"]))[0]


def is_organic(h):
    return (text(h.get("desgnmaster")) or text(h.get("hzname")) or "").upper().startswith("O")


def surface(horizons):
    """The surface horizon: the topmost mineral one (O horizons skipped), else the topmost."""
    hs = sorted(horizons, key=lambda h: (num(h["hzdept_r"]) if num(h["hzdept_r"]) is not None else 1e9, h["chkey"]))
    mineral = [h for h in hs if not is_organic(h)]
    return (mineral or hs or [None])[0]


def restrictions(rows):
    """[{kind, top_cm, bottom_cm, hard}] by depth."""
    out = [{"kind": text(r["reskind"]), "top_cm": whole(r["resdept_r"]), "bottom_cm": whole(r["resdepb_r"]),
            "hard": text(r["reshard"])} for r in rows]
    return sorted(out, key=lambda r: (r["top_cm"] if r["top_cm"] is not None else 1e9, r["kind"] or ""))


def restriction_class(kind):
    k = (kind or "").lower()
    return "hardpan" if k in HARDPAN else "bedrock" if k in BEDROCK else None


class Derived:
    """The rows to load. map_units, components and horizons are lists of dicts named as the table columns;
    ground_types maps an id to its fixed attributes (the counts and areas are summed in the database)."""

    def __init__(self):
        self.map_units, self.components, self.horizons = [], [], []
        self.ground_types = {}


def derive(pkg, areas):
    """Derive the rows of the given survey areas (symbols) from a package."""
    areas = set(areas)

    def rows(table):
        return [r for r in pkg.table(table) if r["areasymbol"] in areas]

    out = Derived()
    muagg = {r["mukey"]: r for r in rows("muaggatt")}
    comps = _group(rows("component"), "mukey")
    hz = _group(rows("chorizon"), "cokey")
    res = _group(rows("corestrictions"), "cokey")
    frag = defaultdict(float)
    has_frag = set()
    for r in rows("cosurffrags"):
        if num(r["sfragcov_r"]) is not None:
            frag[r["cokey"]] += num(r["sfragcov_r"])
            has_frag.add(r["cokey"])
    pmg = {}
    for r in sorted(rows("copmgrp"), key=lambda r: (yes(r["rvindicator"]) is not True, r["copmgrpkey"])):
        pmg.setdefault(r["cokey"], r)
    pm = _group(rows("copm"), "copmgrpkey")
    landform = {}
    for r in sorted(rows("cogeomordesc"), key=lambda r: (yes(r["rvindicator"]) is not True,)):
        if (text(r["geomftname"]) or "").lower() == "landform" and text(r["geomfname"]):
            landform.setdefault(r["cokey"], text(r["geomfname"]))
    eco = {}
    for r in sorted(rows("coecoclass"), key=lambda r: (not (text(r["ecoclasstypename"]) or "").startswith("NRCS"),
                                                       r["ecoclasstypename"], r["coecoclasskey"])):
        if text(r["ecoclassid"]):
            eco.setdefault(r["cokey"], r)
    crops = _group(rows("cocropyld"), "cokey")
    texgrp = {}
    for r in sorted(rows("chtexturegrp"), key=lambda r: (yes(r["rvindicator"]) is not True, r["chtgkey"])):
        texgrp.setdefault(r["chkey"], r)
    textures = _group(rows("chtexture"), "chtgkey")
    mods = _group(rows("chtexturemod"), "chtkey")

    def texture_of(h):
        """(texture with modifier, texture class, modifier) of a horizon's representative texture group."""
        g = texgrp.get(h["chkey"]) if h else None
        if not g:
            return None, None, None
        desc = text(g["texdesc"])
        ts = sorted(textures.get(g["chtgkey"], []), key=lambda t: t["chtkey"])
        cls = "; ".join(dict.fromkeys(text(t["texcl"]) or text(t["lieutex"]) for t in ts
                                      if text(t["texcl"]) or text(t["lieutex"]))) or None
        modifier = None
        if desc and cls and ";" not in cls and desc.lower().endswith(cls.lower()) and len(desc) > len(cls):
            modifier = desc[:-len(cls)].strip().rstrip(",").strip() or None
        if modifier is None:
            ms = [text(m["texmod"]) for t in ts for m in mods.get(t["chtkey"], []) if text(m["texmod"])]
            modifier = "; ".join(dict.fromkeys(ms)) or None
        return desc, cls, modifier

    for mu in rows("mapunit"):
        mukey = mu["mukey"]
        cs = comps.get(mukey, [])
        dom = dominant(cs)
        for c in cs:
            ck = c["cokey"]
            e = eco.get(ck)
            group = pmg.get(ck)
            kinds = sorted(pm.get(group["copmgrpkey"], []), key=lambda k: num(k["pmorder"]) or 0) if group else []
            out.components.append({
                "cokey": ck, "mukey": mukey, "compname": text(c["compname"]) or "(unnamed)",
                "compkind": text(c["compkind"]), "comppct_r": whole(c["comppct_r"]), "majcomp": yes(c["majcompflag"]),
                "slope_l": num(c["slope_l"]), "slope_r": num(c["slope_r"]), "slope_h": num(c["slope_h"]),
                "drainagecl": text(c["drainagecl"]), "hydgrp": text(c["hydgrp"]),
                "hydricrating": text(c["hydricrating"]),
                "irrcapcl": whole(c["irrcapcl"]), "irrcapscl": text(c["irrcapscl"]),
                "nirrcapcl": whole(c["nirrcapcl"]), "nirrcapscl": text(c["nirrcapscl"]),
                "taxclname": text(c["taxclname"]), "taxorder": text(c["taxorder"]),
                "earthcov": text(c["earthcovkind1"]), "landform": landform.get(ck),
                "pm_kind": "; ".join(dict.fromkeys(text(k["pmkind"]) for k in kinds if text(k["pmkind"]))) or None,
                "ffd_r": whole(c["ffd_r"]), "albedodry_r": num(c["albedodry_r"]), "elev_r": num(c["elev_r"]),
                "map_r": whole(c["map_r"]),
                "surf_frag_cover_pct": round(frag[ck], 3) if ck in has_frag else None,
                "eco_id": text(e["ecoclassid"]) if e else None, "eco_name": text(e["ecoclassname"]) if e else None,
                "restrictions": restrictions(res.get(ck, [])),
                "crop_yields": [{"crop": text(y["cropname"]), "units": text(y["yldunits"]),
                                 "irr": num(y["irryield_r"]), "nonirr": num(y["nonirryield_r"])}
                                for y in sorted(crops.get(ck, []), key=lambda y: (y["cropname"], y["yldunits"]))],
            })
            for h in hz.get(ck, []):
                desc, cls, _ = texture_of(h)
                out.horizons.append({
                    "chkey": h["chkey"], "cokey": ck, "hzname": text(h["hzname"]),
                    "top_cm": whole(h["hzdept_r"]), "bottom_cm": whole(h["hzdepb_r"]), "texture": desc, "texcl": cls,
                    "sand": num(h["sandtotal_r"]), "silt": num(h["silttotal_r"]), "clay": num(h["claytotal_r"]),
                    "om": num(h["om_r"]), "ph": num(h["ph1to1h2o_r"]), "caco3": num(h["caco3_r"]),
                    "gypsum": num(h["gypsum_r"]), "ec": num(h["ec_r"]), "sar": num(h["sar_r"]),
                    "awc": num(h["awc_r"]), "ksat": num(h["ksat_r"]), "kwfact": num(h["kwfact"]),
                    "frag_gt10": num(h["fraggt10_r"]), "frag_3to10": num(h["frag3to10_r"]),
                })

        agg = muagg.get(mukey, {})
        row = {
            "mukey": mukey, "areasymbol": mu["areasymbol"], "musym": text(mu["musym"]), "muname": text(mu["muname"]),
            "mukind": text(mu["mukind"]), "farmlndcl": text(mu["farmlndcl"]),
            "slopegraddcp": num(agg.get("slopegraddcp")), "aws025wta": num(agg.get("aws025wta")),
            "aws050wta": num(agg.get("aws050wta")), "aws0100wta": num(agg.get("aws0100wta")),
            "drclassdcd": text(agg.get("drclassdcd")), "hydgrpdcd": text(agg.get("hydgrpdcd")),
            "flodfreqdcd": text(agg.get("flodfreqdcd")), "pondfreqprs": whole(agg.get("pondfreqprs")),
            "brockdepmin": whole(agg.get("brockdepmin")), "wtdepannmin": whole(agg.get("wtdepannmin")),
            "iccdcd": text(agg.get("iccdcd")), "niccdcd": text(agg.get("niccdcd")),
            "hydclprs": whole(agg.get("hydclprs")),
            "dom_cokey": dom["cokey"] if dom else None, "ground_type": None,
            "restr_kind": None, "restr_top_cm": None, "restr_hard": None, "c_restr": None, "pat": None,
        }
        if dom:
            rs = restrictions(res.get(dom["cokey"], []))
            if rs:
                row.update(restr_kind=rs[0]["kind"], restr_top_cm=rs[0]["top_cm"], restr_hard=rs[0]["hard"])
            limiting = [r for r in rs if restriction_class(r["kind"]) and r["top_cm"] is not None]
            if limiting or hz.get(dom["cokey"]):
                # Rated when the dominant component has a root-limiting layer or horizon data; a miscellaneous area
                # with neither (Water, Urban land, Pits, ...) is left unrated.
                top = limiting[0]["top_cm"] if limiting else None
                row["c_restr"] = depth_code(top if top is not None and top < DEPTH_BREAKS_CM[-1] else None)
                row["pat"] = restriction_class(limiting[0]["kind"]) if limiting and top < 50 else "none"
            desc, cls, modifier = texture_of(surface(hz.get(dom["cokey"], [])))
            series = text(dom["compname"])
            gid = ground_type_id(series, desc)
            if gid:
                row["ground_type"] = gid
                if gid not in out.ground_types:
                    out.ground_types[gid] = {"id": gid, "series": series, "texture": desc, "texcl": cls,
                                             "modifier": modifier, "misc": misc_kind(series, dom["compkind"])}
        row["c_drain"] = drainage_code(row["drclassdcd"])
        row["c_aws"] = aws_code(row["aws0100wta"])
        row["c_farm"], row["farm_cond"] = farm_code(row["farmlndcl"])
        row["c_hsg"], row["hsg_dual"] = hsg_code(row["hydgrpdcd"])
        out.map_units.append(row)

    known = {m["mukey"] for m in out.map_units}
    if orphans := sorted({c["mukey"] for c in rows("component")} - known):
        raise PackageError(f"components of map units the package doesn't have: {', '.join(orphans[:5])}")
    return out
