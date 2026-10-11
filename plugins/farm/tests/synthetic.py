"""Synthetic CSB editions for the tests: a GeoPackage written with the standard library (sqlite3), shaped like
NASS's (a feature table with CSBID, CSBYEARS, CSBACRES, CDL<year>, ..., INSIDE_X/INSIDE_Y and a MultiPolygon column
named Shape), so the stdlib reader, the loader and the worker build (through GDAL) read the same file.

Three fields in NASS's Albers (EPSG:5070), a few km south of Nampa (the map box), each with eight years of codes:
- F1, 161825000000001: a 400 m x 100 m rectangle, its long side east-west; corn, alfalfa, wheat; corn in 2025.
- F2, 161825000000002: 100 m x 300 m, long side north-south; farmed in 2018-21, developed from 2023 (121, 122, 123):
  built over by the growth rule.
- F3, 161825000000003: a "bowtie" whose ring crosses itself (as 803 of CSB's do), farmed, then developed (122) in
  2025 only: being built when three permits are inside it, otherwise not flagged.
None of this is real data.
"""

import os
import sqlite3
import struct

X0, Y0 = -1650000.0, 2450000.0           # NASS Albers metres, south of Nampa
EPSG = 5070
WKT_5070 = (
    'PROJCS["NAD83 / Conus Albers",GEOGCS["NAD83",DATUM["North_American_Datum_1983",SPHEROID["GRS 1980",6378137,'
    '298.257222101,AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6269"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4269"]],'
    'PROJECTION["Albers_Conic_Equal_Area"],PARAMETER["latitude_of_center",23],PARAMETER["longitude_of_center",-96],'
    'PARAMETER["standard_parallel_1",29.5],PARAMETER["standard_parallel_2",45.5],PARAMETER["false_easting",0],'
    'PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],'
    'AXIS["Northing",NORTH],AUTHORITY["EPSG","5070"]]')
WKT_32611 = (
    'PROJCS["WGS 84 / UTM zone 11N",GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
    'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-117],'
    'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],'
    'UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH],AUTHORITY["EPSG","32611"]]')
WKTS = {5070: WKT_5070, 32611: WKT_32611}
YEARS = list(range(2018, 2026))
ACRE_M2 = 4046.8564224


def rect(x, y, w, h):
    return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]


def field(csbid, polygons, codes, county="Canyon", cntyfips="027", inside=None, years=None):
    """A field's row: polygons is a list of polygons, each a list of rings of (x, y)."""
    years = years or YEARS
    if len(codes) != len(years):
        raise ValueError("one code per year")
    ring = polygons[0][0]
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return {"CSBID": csbid, "CSBYEARS": f"{years[0] % 100:02d}{years[-1] % 100:02d}",
            "CSBACRES": round(sum(_area(p[0]) for p in polygons) / ACRE_M2, 3),
            **{f"CDL{y}": c for y, c in zip(years, codes)},
            "STATEFIPS": "16", "STATEASD": "1610", "ASD": "10", "CNTY": county, "CNTYFIPS": cntyfips,
            "INSIDE_X": inside[0] if inside else (min(xs) + max(xs)) / 2,
            "INSIDE_Y": inside[1] if inside else (min(ys) + max(ys)) / 2,
            "_polygons": polygons}


def _area(ring):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))) / 2


F1 = "161825000000001"
F2 = "161825000000002"
F3 = "161825000000003"


def fields(x0=X0, y0=Y0):
    """The three fields, placed from (x0, y0) (Albers metres)."""
    bowtie = [[(x0 + 1000, y0), (x0 + 1200, y0 + 200), (x0 + 1200, y0), (x0 + 1000, y0 + 200), (x0 + 1000, y0)]]
    return [
        field(F1, [rect(x0, y0, 400, 100)], [1, 1, 36, 36, 1, 24, 24, 1]),
        field(F2, [rect(x0 + 500, y0, 100, 300)], [36, 36, 1, 36, 176, 121, 122, 123]),
        field(F3, [bowtie], [176, 24, 24, 41, 41, 42, 1, 122], inside=(x0 + 1050, y0 + 100)),
    ]


def wkb_multipolygon(polygons):
    out = struct.pack("<BII", 1, 6, len(polygons))
    for rings in polygons:
        out += struct.pack("<BII", 1, 3, len(rings))
        for ring in rings:
            out += struct.pack("<I", len(ring)) + b"".join(struct.pack("<dd", x, y) for x, y in ring)
    return out


def gpkg_geometry(polygons, srs_id, empty=False):
    """A GeoPackageBinary blob: 'GP', version 0, flags (little-endian, an xy envelope), srs_id, envelope, WKB."""
    pts = [p for rings in polygons for ring in rings for p in ring]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    flags = 0b00000011 | (0b00010000 if empty else 0)
    head = b"GP" + bytes([0, flags]) + struct.pack("<i", srs_id)
    return head + struct.pack("<dddd", min(xs), max(xs), min(ys), max(ys)) + wkb_multipolygon(polygons)


def write_gpkg(path, rows, epsg=EPSG, table="csb_mapbox", years=None):
    """A GeoPackage with one feature table of CSB-shaped rows (field() dicts)."""
    years = years or YEARS
    if os.path.exists(path):
        os.unlink(path)
    db = sqlite3.connect(path)
    db.execute("pragma application_id = 1196444487")      # 'GPKG'
    db.execute("pragma user_version = 10300")
    db.executescript("""
      create table gpkg_spatial_ref_sys (srs_name text not null, srs_id integer primary key, organization text not null,
        organization_coordsys_id integer not null, definition text not null, description text);
      create table gpkg_contents (table_name text primary key, data_type text not null, identifier text unique,
        description text default '', last_change datetime not null default (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        min_x double, min_y double, max_x double, max_y double, srs_id integer);
      create table gpkg_geometry_columns (table_name text not null, column_name text not null,
        geometry_type_name text not null, srs_id integer not null, z tinyint not null, m tinyint not null,
        primary key (table_name, column_name));""")
    db.executemany("insert into gpkg_spatial_ref_sys values (?, ?, ?, ?, ?, ?)", [
        ("Undefined cartesian SRS", -1, "NONE", -1, "undefined", None),
        ("Undefined geographic SRS", 0, "NONE", 0, "undefined", None),
        (f"EPSG:{epsg}", epsg, "EPSG", epsg, WKTS[epsg], None)])
    cols = ["CSBID text", "CSBYEARS text", "CSBACRES real"] + [f"CDL{y} integer" for y in years] + [
        "STATEFIPS text", "STATEASD text", "ASD text", "CNTY text", "CNTYFIPS text", "INSIDE_X real", "INSIDE_Y real"]
    db.execute(f"create table {table} (OBJECTID integer primary key autoincrement not null, Shape blob, "
               + ", ".join(cols) + ")")
    names = [c.split()[0] for c in cols]
    pts = [p for r in rows for rings in r["_polygons"] for ring in rings for p in ring]
    db.execute("insert into gpkg_contents (table_name, data_type, identifier, min_x, min_y, max_x, max_y, srs_id) "
               "values (?, 'features', ?, ?, ?, ?, ?, ?)",
               (table, table, min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts),
                max(p[1] for p in pts), epsg))
    db.execute("insert into gpkg_geometry_columns values (?, 'Shape', 'MULTIPOLYGON', ?, 0, 0)", (table, epsg))
    for r in rows:
        db.execute(f"insert into {table} (Shape, {', '.join(names)}) values (?, {', '.join('?' * len(names))})",
                   [gpkg_geometry(r["_polygons"], epsg)] + [r[n] for n in names])
    db.commit()
    db.close()
    return path
