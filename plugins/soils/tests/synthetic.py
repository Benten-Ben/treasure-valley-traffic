"""A made-up soil survey for the tests: two survey areas (ZZ001, ZZ002) in the map box, written either as Web Soil
Survey packages (pipe-delimited tables and a shapefile, for prepare.py in the worker image) or as a prepared folder
(what prepare.py writes, for the standard-library loader tests). Nothing here is real SSURGO data: names, keys and
values are invented to exercise the rules (ties, organic horizons, restrictions, misc areas, conditions).

    ZZ001 1001 "141"  Purdam silt loam: Purdam 90% (duripan at 61 cm) and Power 10%; prime if irrigated
          1002 "50"   Elijah-Chilcott complex: Elijah 45% (minor) and Chilcott 45% (major, so dominant), an O horizon
                      over gravelly silt loam, lithic bedrock at 20 cm; statewide if irrigated and reclaimed; C/D
          1003 "W"    Water (a miscellaneous area, no horizons)
          1004 "99"   only outside the box: dropped with its component, horizon and yields
    ZZ002 2001 "7"    Purdam silt loam again (the same ground type as 1001), crossing the box's west edge
          2002 "NOTCOM" No Digital Data Available: no survey (NRCS's NOTCOM), one component of no kind
          2003 "RO"   Rock outcrop: a miscellaneous area with a "Bedrock" texture and lithic bedrock at 0 cm

Each survey area's boundary (soilsa_a) is a rectangle around its polygons; ZZ002's comes in two pieces sharing an
edge.
"""

import csv
import hashlib
import json
import os

AREAS = {
    "ZZ001": {"areaname": "Synthetic County, Idaho", "saverest": "08/31/2026 21:54:36", "saversion": "14",
              "tabularversion": "14", "projectscale": "24000"},
    "ZZ002": {"areaname": "Synthetic Area, Oregon", "saverest": "09/09/2026 14:32:10", "saversion": "9",
              "tabularversion": "9", "projectscale": "20000"},
}


def square(w, s, e, n):
    return [[[w, s], [e, s], [e, n], [w, n], [w, s]]]


# (area, fid, mukey, musym, polygons (lists of rings), touches the box)
POLYGONS = [
    ("ZZ001", 0, "1001", "141", [square(-116.30, 43.50, -116.29, 43.51)], True),
    ("ZZ001", 1, "1002", "50", [square(-116.29, 43.50, -116.28, 43.51)], True),
    ("ZZ001", 2, "1003", "W", [square(-116.27, 43.50, -116.268, 43.502), square(-116.26, 43.50, -116.258, 43.502)],
     True),
    ("ZZ001", 3, "1004", "99", [square(-117.20, 43.50, -117.19, 43.51)], False),          # outside the box
    ("ZZ001", 4, "1001", "141", [square(-117.06, 43.50, -117.05, 43.51)], False),         # shares only an edge
    ("ZZ002", 0, "2001", "7", [square(-117.06, 43.60, -117.04, 43.61)], True),            # half inside
    ("ZZ002", 1, "2002", "NOTCOM", [square(-116.10, 43.70, -116.09, 43.71)], True),
    ("ZZ002", 2, "2003", "RO", [square(-116.08, 43.70, -116.07, 43.71)], True),
]

# Each survey area's boundary pieces (soilsa_a), whole.
SURVEY_AREAS = {
    "ZZ001": [[square(-117.25, 43.45, -116.25, 43.55)]],
    "ZZ002": [[square(-117.10, 43.55, -116.50, 43.75)], [square(-116.50, 43.55, -116.00, 43.75)]],
}

# The columns of each table: the loader's (package.TABLES) plus a few it doesn't read, which prepare must copy too.
EXTRA = {"mapunit": ("muacres", "lkey"), "component": ("localphase",), "chorizon": ("dbthirdbar_r",)}


def _row(**kw):
    return kw


TABLES = {
    "mapunit": [
        _row(mukey="1001", musym="141", muname="Purdam silt loam, 0 to 2 percent slopes", mukind="Consociation",
             farmlndcl="Prime farmland if irrigated", muacres="1200", lkey="9001"),
        _row(mukey="1002", musym="50", muname="Elijah-Chilcott complex, 2 to 4 percent slopes", mukind="Complex",
             farmlndcl="Farmland of statewide importance, if irrigated and reclaimed of excess salts and sodium",
             muacres="300", lkey="9001"),
        _row(mukey="1003", musym="W", muname="Water", mukind="Consociation", farmlndcl="Not prime farmland",
             muacres="40", lkey="9001"),
        _row(mukey="1004", musym="99", muname="Outside loam", mukind="Consociation", farmlndcl="Not prime farmland",
             muacres="10", lkey="9001"),
        _row(mukey="2001", musym="7", muname="Purdam silt loam, 0 to 2 percent slopes", mukind="Consociation",
             farmlndcl="", muacres="500", lkey="9002"),
        _row(mukey="2002", musym="NOTCOM", muname="No Digital Data Available", mukind="", farmlndcl="",
             muacres="900", lkey="9002"),
        _row(mukey="2003", musym="RO", muname="Rock outcrop", mukind="Consociation", farmlndcl="Not prime farmland",
             muacres="60", lkey="9002"),
    ],
    "muaggatt": [
        _row(mukey="1001", slopegraddcp="1", aws025wta="4.2", aws050wta="7.9", aws0100wta="11.8",
             drclassdcd="Well drained", hydgrpdcd="C", flodfreqdcd="None", pondfreqprs="0", brockdepmin="",
             wtdepannmin="", iccdcd="3", niccdcd="6", hydclprs="0"),
        _row(mukey="1002", slopegraddcp="3", aws025wta="1.1", aws050wta="2.0", aws0100wta="4.0",
             drclassdcd="Somewhat poorly drained", hydgrpdcd="C/D", flodfreqdcd="Rare", pondfreqprs="0",
             brockdepmin="20", wtdepannmin="46", iccdcd="4", niccdcd="7", hydclprs="5"),
        _row(mukey="1003", slopegraddcp="", aws025wta="", aws050wta="", aws0100wta="", drclassdcd="", hydgrpdcd="",
             flodfreqdcd="", pondfreqprs="", brockdepmin="", wtdepannmin="", iccdcd="", niccdcd="", hydclprs="100"),
        _row(mukey="1004", slopegraddcp="1", aws025wta="3", aws050wta="6", aws0100wta="22", drclassdcd="Well drained",
             hydgrpdcd="B", flodfreqdcd="None", pondfreqprs="0", brockdepmin="", wtdepannmin="", iccdcd="",
             niccdcd="", hydclprs="0"),
        _row(mukey="2001", slopegraddcp="1", aws025wta="4.0", aws050wta="7.5", aws0100wta="20.5",
             drclassdcd="Excessively drained", hydgrpdcd="A", flodfreqdcd="None", pondfreqprs="0", brockdepmin="",
             wtdepannmin="", iccdcd="", niccdcd="", hydclprs="0"),
        _row(mukey="2002", slopegraddcp="", aws025wta="", aws050wta="", aws0100wta="", drclassdcd="", hydgrpdcd="",
             flodfreqdcd="", pondfreqprs="", brockdepmin="", wtdepannmin="", iccdcd="", niccdcd="", hydclprs=""),
        _row(mukey="2003", slopegraddcp="40", aws025wta="0", aws050wta="0", aws0100wta="0",
             drclassdcd="", hydgrpdcd="D", flodfreqdcd="None", pondfreqprs="0", brockdepmin="0",
             wtdepannmin="", iccdcd="", niccdcd="8", hydclprs="0"),
    ],
}


def _component(cokey, mukey, name, kind, pct, major, **kw):
    base = dict(cokey=cokey, mukey=mukey, compname=name, compkind=kind, comppct_r=pct, majcompflag=major,
                slope_l="0", slope_r="1", slope_h="2", drainagecl="Well drained", hydgrp="C", hydricrating="No",
                irrcapcl="3", irrcapscl="s", nirrcapcl="6", nirrcapscl="c",
                taxclname="Coarse-silty, mixed, superactive, mesic Xeric Haplodurids", taxorder="Aridisols",
                earthcovkind1="Crop cover", ffd_r="140", albedodry_r="0.23", elev_r="830", map_r="279",
                localphase="")
    base.update(kw)
    return base


TABLES["component"] = [
    _component("1001-1", "1001", "Purdam", "Series", "90", "Yes"),
    _component("1001-2", "1001", "Power", "Series", "10", "No "),
    _component("1002-1", "1002", "Elijah", "Series", "45", "No "),
    _component("1002-2", "1002", "Chilcott", "Series", "45", "Yes", hydgrp="C/D", drainagecl="Somewhat poorly drained"),
    _component("1003-1", "1003", "Water", "Miscellaneous area", "100", "Yes", hydgrp="", drainagecl="",
               irrcapcl="", irrcapscl="", nirrcapcl="8", nirrcapscl="", taxclname="", taxorder="", albedodry_r=""),
    _component("1004-1", "1004", "Outside", "Series", "100", "Yes"),
    _component("2001-1", "2001", "Purdam", "Series", "85", "Yes"),
    _component("2001-2", "2001", "Urban land", "Miscellaneous area", "15", "No "),
    _component("2002-1", "2002", "NOTCOM", "", "100", "Yes", hydgrp="", drainagecl="", irrcapcl="", irrcapscl="",
               nirrcapcl="", nirrcapscl="", taxclname="", taxorder="", earthcovkind1="", ffd_r="", albedodry_r="",
               elev_r="", map_r=""),
    _component("2003-1", "2003", "Rock outcrop", "Miscellaneous area", "100", "Yes", hydgrp="D", drainagecl="",
               irrcapcl="", irrcapscl="", nirrcapcl="8", nirrcapscl="", taxclname="", taxorder="",
               albedodry_r="0.30"),
]


def _horizon(chkey, cokey, name, top, bottom, master=None, **kw):
    base = dict(chkey=chkey, cokey=cokey, hzname=name, desgnmaster=master or name[:1], hzdept_r=top, hzdepb_r=bottom,
                sandtotal_r="20", silttotal_r="65", claytotal_r="15", om_r="2", ph1to1h2o_r="6.7", caco3_r="0",
                gypsum_r="0", ec_r="0.5", sar_r="1", awc_r="0.2", ksat_r="9", kwfact=".49", fraggt10_r="0",
                frag3to10_r="0", dbthirdbar_r="1.4")
    base.update(kw)
    return base


TABLES["chorizon"] = [
    _horizon("h1", "1001-1", "Ap", "0", "25"),
    _horizon("h2", "1001-1", "Bkq", "25", "61", ph1to1h2o_r="8.3", caco3_r="5"),
    _horizon("h3", "1001-1", "Bkqm", "61", "150", master="B"),
    _horizon("h4", "1002-2", "Oi", "0", "2", om_r="60"),
    _horizon("h5", "1002-2", "A", "2", "10"),
    _horizon("h6", "1002-2", "R", "20", "40"),
    _horizon("h7", "1004-1", "A", "0", "30"),
    _horizon("h8", "2001-1", "A", "0", "30"),
    _horizon("h9", "1002-1", "A", "0", "15"),
    _horizon("h10", "2003-1", "R", "0", "150"),
]
TABLES["chtexturegrp"] = [
    _row(chtgkey="g1", chkey="h1", texture="SIL", texdesc="Silt loam", rvindicator="Yes"),
    _row(chtgkey="g2", chkey="h2", texture="SIL", texdesc="Silt loam", rvindicator="Yes"),
    _row(chtgkey="g3", chkey="h3", texture="CEM", texdesc="Cemented material", rvindicator="Yes"),
    _row(chtgkey="g4", chkey="h4", texture="SPM", texdesc="Slightly decomposed plant material", rvindicator="Yes"),
    _row(chtgkey="g5", chkey="h5", texture="GR-SIL", texdesc="Gravelly silt loam", rvindicator="Yes"),
    _row(chtgkey="g5b", chkey="h5", texture="SIL", texdesc="Silt loam", rvindicator="No "),
    _row(chtgkey="g6", chkey="h6", texture="BR", texdesc="Bedrock", rvindicator="Yes"),
    _row(chtgkey="g7", chkey="h7", texture="L", texdesc="Loam", rvindicator="Yes"),
    _row(chtgkey="g8", chkey="h8", texture="SIL", texdesc="Silt loam", rvindicator="Yes"),
    _row(chtgkey="g9", chkey="h9", texture="L", texdesc="Loam", rvindicator="Yes"),
    _row(chtgkey="g10", chkey="h10", texture="BR", texdesc="Bedrock", rvindicator="Yes"),
]
TABLES["chtexture"] = [
    _row(chtkey="t1", chtgkey="g1", texcl="Silt loam", lieutex=""),
    _row(chtkey="t2", chtgkey="g2", texcl="Silt loam", lieutex=""),
    _row(chtkey="t3", chtgkey="g3", texcl="", lieutex="Cemented material"),
    _row(chtkey="t4", chtgkey="g4", texcl="", lieutex="Slightly decomposed plant material"),
    _row(chtkey="t5", chtgkey="g5", texcl="Silt loam", lieutex=""),
    _row(chtkey="t5b", chtgkey="g5b", texcl="Silt loam", lieutex=""),
    _row(chtkey="t6", chtgkey="g6", texcl="", lieutex="Bedrock"),
    _row(chtkey="t7", chtgkey="g7", texcl="Loam", lieutex=""),
    _row(chtkey="t8", chtgkey="g8", texcl="Silt loam", lieutex=""),
    _row(chtkey="t9", chtgkey="g9", texcl="Loam", lieutex=""),
    _row(chtkey="t10", chtgkey="g10", texcl="", lieutex="Bedrock"),
]
TABLES["chtexturemod"] = [_row(chtkey="t5", texmod="Gravelly")]
TABLES["corestrictions"] = [
    _row(corestrictkey="r1", cokey="1001-1", reskind="Duripan", reshard="Indurated", resdept_r="61", resdepb_r="150"),
    _row(corestrictkey="r2", cokey="1002-2", reskind="Lithic bedrock", reshard="Indurated", resdept_r="20",
         resdepb_r=""),
    _row(corestrictkey="r3", cokey="1002-2", reskind="Abrupt textural change", reshard="", resdept_r="8",
         resdepb_r=""),
    _row(corestrictkey="r4", cokey="1004-1", reskind="Duripan", reshard="Indurated", resdept_r="40", resdepb_r="80"),
    _row(corestrictkey="r5", cokey="2003-1", reskind="Lithic bedrock", reshard="Indurated", resdept_r="0",
         resdepb_r=""),
]
TABLES["cosurffrags"] = [
    _row(cokey="1002-2", sfragcov_r="2"),
    _row(cokey="1002-2", sfragcov_r="1.5"),
]
TABLES["copmgrp"] = [
    _row(copmgrpkey="p1", cokey="1001-1", pmgroupname="Loess over alluvium", rvindicator="Yes"),
    _row(copmgrpkey="p2", cokey="1001-1", pmgroupname="Alluvium", rvindicator="No "),
]
TABLES["copm"] = [
    _row(copmgrpkey="p1", pmorder="2", pmkind="Alluvium"),
    _row(copmgrpkey="p1", pmorder="1", pmkind="Loess"),
    _row(copmgrpkey="p2", pmorder="1", pmkind="Alluvium"),
]
TABLES["cogeomordesc"] = [
    _row(cokey="1001-1", geomftname="Landscape", geomfname="Valley", rvindicator="Yes"),
    _row(cokey="1001-1", geomftname="Landform", geomfname="Fan remnant", rvindicator="No "),
    _row(cokey="1001-1", geomftname="Landform", geomfname="Stream terrace", rvindicator="Yes"),
    _row(cokey="1002-2", geomftname="Landform", geomfname="Lava plain", rvindicator="No "),
]
TABLES["coecoclass"] = [
    _row(coecoclasskey="e1", cokey="1001-1", ecoclasstypename="SSR4: Forest Habitat Types", ecoclassid="X1",
         ecoclassname="Not this one"),
    _row(coecoclasskey="e2", cokey="1001-1", ecoclasstypename="NRCS Rangeland Site", ecoclassid="R011XY001ID",
         ecoclassname="Loamy 8-12 PZ"),
]
TABLES["cocropyld"] = [
    _row(cokey="1001-1", cropname="Wheat", yldunits="Bu", irryield_r="100", nonirryield_r=""),
    _row(cokey="1001-1", cropname="Alfalfa hay", yldunits="Tons", irryield_r="6", nonirryield_r=""),
    _row(cokey="1004-1", cropname="Corn", yldunits="Bu", irryield_r="90", nonirryield_r=""),
]


def columns(table):
    from plugins.soils.ingest import package
    return list(package.TABLES[table]) + list(EXTRA.get(table, ()))


def area_of(table, row):
    """Which survey area a row belongs to (by its map unit's key prefix)."""
    for key in ("mukey", "cokey", "chkey", "chtgkey", "chtkey", "copmgrpkey"):
        if key in row:
            return _AREA_BY_KEY[key](row[key])
    raise KeyError(table)


def _mukey_area(k):
    return "ZZ001" if k.startswith("1") else "ZZ002"


def _cokey_area(k):
    return _mukey_area(k)


def _chkey_area(k):
    return "ZZ002" if k in ("h8", "h10") else "ZZ001"


_AREA_BY_KEY = {
    "mukey": _mukey_area, "cokey": _cokey_area, "chkey": _chkey_area,
    "chtgkey": lambda k: "ZZ002" if k in ("g8", "g10") else "ZZ001",
    "chtkey": lambda k: "ZZ002" if k in ("t8", "t10") else "ZZ001",
    "copmgrpkey": lambda k: "ZZ001",
}


def kept_rows(table, tables=None, polygons=None):
    """The rows a prepared folder holds: those of map units with a polygon touching the box."""
    tables, polygons = tables or TABLES, polygons or POLYGONS
    mukeys = {mukey for _, _, mukey, _, _, inside in polygons if inside}
    cokeys = {r["cokey"] for r in tables["component"] if r["mukey"] in mukeys}
    chkeys = {r["chkey"] for r in tables["chorizon"] if r["cokey"] in cokeys}
    tgkeys = {r["chtgkey"] for r in tables["chtexturegrp"] if r["chkey"] in chkeys}
    tkeys = {r["chtkey"] for r in tables["chtexture"] if r["chtgkey"] in tgkeys}
    pmkeys = {r["copmgrpkey"] for r in tables["copmgrp"] if r["cokey"] in cokeys}
    keep = {"mukey": mukeys, "cokey": cokeys, "chkey": chkeys, "chtgkey": tgkeys, "chtkey": tkeys,
            "copmgrpkey": pmkeys}
    follows = {"mapunit": "mukey", "muaggatt": "mukey", "component": "mukey", "chorizon": "cokey",
               "chtexturegrp": "chkey", "chtexture": "chtgkey", "chtexturemod": "chtkey", "copm": "copmgrpkey"}
    key = follows.get(table, "cokey")
    return [r for r in tables[table] if r[key] in keep[key]]


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def feature(area, fid, mukey, musym, polys):
    return {"type": "Feature",
            "properties": {"id": f"{area}:{fid}", "areasymbol": area, "fid": fid, "mukey": mukey, "musym": musym},
            "geometry": {"type": "MultiPolygon", "coordinates": polys}}


def write_prepared(folder, tables=None, polygons=None, areas=None, bounds=None):
    """What prepare.py would write for this survey, without GDAL. tables, polygons, areas and bounds replace the
    module's (a test's variant of the survey)."""
    from plugins.soils.ingest import package
    tables, polygons, areas = tables or TABLES, polygons or POLYGONS, areas or AREAS
    bounds = SURVEY_AREAS if bounds is None else bounds
    os.makedirs(os.path.join(folder, "tabular"), exist_ok=True)
    files = {}
    path = os.path.join(folder, package.POLYGONS)
    with open(path, "w", encoding="utf-8") as f:
        n = 0
        for area in sorted(areas):
            for a, fid, mukey, musym, polys, inside in polygons:
                if a == area and inside:
                    f.write(json.dumps(feature(a, fid, mukey, musym, polys), separators=(",", ":")) + "\n")
                    n += 1
    files[package.POLYGONS] = {"sha256": _sha(path), "rows": n}
    path = os.path.join(folder, package.SURVEY_AREAS)
    with open(path, "w", encoding="utf-8") as f:
        n = 0
        for area in sorted(areas):
            for fid, polys in enumerate(bounds.get(area, [])):
                f.write(json.dumps({"type": "Feature", "properties": {"areasymbol": area, "fid": fid},
                                    "geometry": {"type": "MultiPolygon", "coordinates": polys}},
                                   separators=(",", ":")) + "\n")
                n += 1
    files[package.SURVEY_AREAS] = {"sha256": _sha(path), "rows": n}
    for table in package.TABLES:
        cols = columns(table)
        path = os.path.join(folder, "tabular", f"{table}.csv")
        rows = sorted(kept_rows(table, tables, polygons), key=lambda r: sorted(areas).index(area_of(table, r)))
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["areasymbol"] + cols)
            for r in rows:
                w.writerow([area_of(table, r)] + [r.get(c, "").strip() for c in cols])     # as prepare strips
        files[f"tabular/{table}.csv"] = {"sha256": _sha(path), "rows": len(rows)}
    meta = {"format": package.FORMAT, "made_by": "plugins/soils/tests/synthetic.py", "made_at": "2026-10-11T10:00:00Z",
            "box": list(package.BOX), "files": files, "inputs": {},
            "areas": [{"areasymbol": a, "areaname": v["areaname"], "saverest": package.saverest(v["saverest"]),
                       "saversion": int(v["saversion"]), "tabularversion": int(v["tabularversion"]),
                       "scale": int(v["projectscale"]), "source_url": f"https://example.invalid/{a}",
                       "polygons": sum(1 for p in polygons if p[0] == a and p[5])} for a, v in sorted(areas.items())]}
    with open(os.path.join(folder, package.MANIFEST), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    return meta


# ---- as Web Soil Survey packages (the worker test) ---------------------------------------------------------------

WSS_FILES = {  # table: its file in a Web Soil Survey package (mdstattabs)
    "mapunit": "mapunit", "muaggatt": "muaggatt", "component": "comp", "corestrictions": "crstrcts",
    "cosurffrags": "csfrags", "copmgrp": "cpmatgrp", "copm": "cpmat", "cogeomordesc": "cgeomord",
    "coecoclass": "cecoclas", "cocropyld": "ccrpyd", "chorizon": "chorizon", "chtexturegrp": "chtexgrp",
    "chtexture": "chtextur", "chtexturemod": "chtexmod", "sacatalog": "sacatlog", "legend": "legend",
}


def _pipe(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="|", quotechar='"', lineterminator="\r\n")
        for r in rows:
            w.writerow(r)


def write_raw(sources):
    """One folder per survey area under sources, as the Web Soil Survey's zips unpack: tabular/*.txt (with
    mstab.txt and mstabcol.txt) and spatial/soilmu_a_<area>.shp. Needs GDAL."""
    from osgeo import ogr, osr
    from plugins.soils.ingest import package
    files = dict(WSS_FILES)                              # short file names, as WSS's are
    cols = {t: columns(t) for t in package.TABLES}
    cols["sacatalog"] = ["areasymbol", "areaname", "saversion", "saverest", "tabularversion", "fgdcmetadata",
                         "sacatalogkey"]
    cols["legend"] = ["areatypename", "areasymbol", "areaname", "projectscale", "lkey"]
    for area, info in AREAS.items():
        tab = os.path.join(sources, area, "tabular")
        spatial = os.path.join(sources, area, "spatial")
        os.makedirs(tab)
        os.makedirs(spatial)
        _pipe(os.path.join(tab, "mstab.txt"), [[t, t, "", "", f] for t, f in files.items()])
        _pipe(os.path.join(tab, "mstabcol.txt"),
              [[t, str(i), c, c] for t, cs in cols.items() for i, c in enumerate(cs, 1)])
        _pipe(os.path.join(tab, "sacatlog.txt"),
              [[area, info["areaname"], info["saversion"], info["saverest"], info["tabularversion"],
                "<metadata>\nspans lines | and has pipes</metadata>", "1"]])
        _pipe(os.path.join(tab, "legend.txt"),
              [["Non-MLRA Soil Survey Area", area, info["areaname"], info["projectscale"], "9001"]])
        for table in package.TABLES:
            rows = [r for r in TABLES[table] if area_of(table, r) == area]
            if table == "chtexturemod" and not rows:
                continue                                  # a table WSS left out: read as empty
            _pipe(os.path.join(tab, files[table] + ".txt"), [[r.get(c, "") for c in cols[table]] for r in rows])

        drv = ogr.GetDriverByName("ESRI Shapefile")
        ds = drv.CreateDataSource(os.path.join(spatial, f"soilmu_a_{area.lower()}.shp"))
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        layer = ds.CreateLayer(f"soilmu_a_{area.lower()}", srs, ogr.wkbPolygon)
        for name in ("AREASYMBOL", "SPATIALVER", "MUSYM", "MUKEY"):
            layer.CreateField(ogr.FieldDefn(name, ogr.OFTString))
        for a, fid, mukey, musym, polys, _ in POLYGONS:
            if a != area:
                continue
            f = ogr.Feature(layer.GetLayerDefn())
            for k, v in (("AREASYMBOL", area), ("SPATIALVER", "3"), ("MUSYM", musym), ("MUKEY", mukey)):
                f.SetField(k, v)
            geom = {"type": "MultiPolygon", "coordinates": polys} if len(polys) > 1 else \
                {"type": "Polygon", "coordinates": polys[0]}
            f.SetGeometry(ogr.CreateGeometryFromJson(json.dumps(geom)))
            layer.CreateFeature(f)
        ds = None

        ds = drv.CreateDataSource(os.path.join(spatial, f"soilsa_a_{area.lower()}.shp"))
        layer = ds.CreateLayer(f"soilsa_a_{area.lower()}", srs, ogr.wkbPolygon)
        for name in ("AREASYMBOL", "SPATIALVER", "LKEY"):
            layer.CreateField(ogr.FieldDefn(name, ogr.OFTString))
        for polys in SURVEY_AREAS[area]:
            f = ogr.Feature(layer.GetLayerDefn())
            for k, v in (("AREASYMBOL", area), ("SPATIALVER", "3"), ("LKEY", "9001")):
                f.SetField(k, v)
            f.SetGeometry(ogr.CreateGeometryFromJson(json.dumps({"type": "Polygon", "coordinates": polys[0]})))
            layer.CreateFeature(f)
        ds = None
