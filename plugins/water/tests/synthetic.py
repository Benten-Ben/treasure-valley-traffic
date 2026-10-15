"""Synthetic GeoPackages for the water loaders' tests, written with the standard library (sqlite3 and struct).

Everything here is invented: identifiers, names and coordinates (a few kilometres south-west of Kuna, in the map box).
The files have the tables and columns plugins/water/build/prepare.py writes, with GeoPackageBinary geometries: an
envelope on some, none on others, and one big-endian header, so the reader sees each form.
"""

import os
import sqlite3
import struct

ORIGIN = (-116.50, 43.40)          # lon, lat of the invented landscape's south-west corner
M_LON, M_LAT = 1 / 81000.0, 1 / 111000.0     # about a metre in degrees here


def at(x_m, y_m):
    """Metres east and north of ORIGIN as (lon, lat)."""
    return (ORIGIN[0] + x_m * M_LON, ORIGIN[1] + y_m * M_LAT)


def wkb_point(p):
    return struct.pack("<BIdd", 1, 1, *p)


def wkb_linestring(points):
    return struct.pack("<BII", 1, 2, len(points)) + b"".join(struct.pack("<dd", *p) for p in points)


def wkb_multilinestring(lines):
    return struct.pack("<BII", 1, 5, len(lines)) + b"".join(wkb_linestring(line) for line in lines)


def wkb_polygon(rings):
    out = struct.pack("<BII", 1, 3, len(rings))
    for ring in rings:
        out += struct.pack("<I", len(ring)) + b"".join(struct.pack("<dd", *p) for p in ring)
    return out


def wkb_multipolygon(polygons):
    return struct.pack("<BII", 1, 6, len(polygons)) + b"".join(wkb_polygon(p) for p in polygons)


def gp(wkb, srs=4269, envelope=None, big_endian=False, empty=False):
    """A GeoPackageBinary blob: 'GP', version 0, flags, the SRS id, an optional xy envelope, then the WKB."""
    flags = (0 if big_endian else 1) | ((1 if envelope else 0) << 1) | (0x10 if empty else 0)
    head = b"GP" + bytes([0, flags]) + struct.pack(">i" if big_endian else "<i", srs)
    if envelope:
        head += struct.pack(">dddd" if big_endian else "<dddd", *envelope)
    return head + wkb


def box_square(x0, y0, size):
    return [[at(x0, y0), at(x0 + size, y0), at(x0 + size, y0 + size), at(x0, y0 + size), at(x0, y0)]]


class Gpkg:
    """A minimal GeoPackage: gpkg_contents, gpkg_geometry_columns, and the tables added."""

    def __init__(self, path):
        if os.path.exists(path):
            os.remove(path)                    # a new file each time
        self.conn = sqlite3.connect(path)
        self.conn.executescript("""
            create table gpkg_spatial_ref_sys (srs_name text, srs_id integer primary key, organization text,
              organization_coordsys_id integer, definition text, description text);
            create table gpkg_contents (table_name text primary key, data_type text, identifier text,
              description text, last_change text, min_x real, min_y real, max_x real, max_y real, srs_id integer);
            create table gpkg_geometry_columns (table_name text, column_name text, geometry_type_name text,
              srs_id integer, z integer, m integer);""")

    def table(self, name, columns, geometry=None, geometry_type="GEOMETRY", srs=4269):
        cols = ["fid integer primary key autoincrement"] + [f'"{c}" {t}' for c, t in columns]
        if geometry:
            cols.append(f'"{geometry}" blob')
        self.conn.execute(f'create table "{name}" ({", ".join(cols)})')
        self.conn.execute("insert into gpkg_contents (table_name, data_type, srs_id) values (?, ?, ?)",
                          (name, "features" if geometry else "attributes", srs if geometry else None))
        if geometry:
            self.conn.execute("insert into gpkg_geometry_columns values (?, ?, ?, ?, 0, 0)",
                              (name, geometry, geometry_type, srs))

    def insert(self, table, row):
        names = list(row)
        self.conn.execute(f'insert into "{table}" ({", ".join(chr(34) + n + chr(34) for n in names)}) '
                          f'values ({", ".join("?" for _ in names)})', [row[n] for n in names])

    def close(self):
        self.conn.commit()
        self.conn.close()


FLOWLINE_COLUMNS = [("permanent_identifier", "text"), ("fdate", "datetime"), ("gnis_id", "text"),
                    ("gnis_name", "text"), ("lengthkm", "real"), ("reachcode", "text"), ("flowdir", "integer"),
                    ("wbarea_permanent_identifier", "text"), ("ftype", "integer"), ("fcode", "integer"),
                    ("visibilityfilter", "integer"), ("ftype_name", "text"), ("fcode_desc", "text"),
                    ("class", "text"), ("canalditchtype", "text"), ("hydrographiccategory", "text"),
                    ("pipelinetype", "text"), ("relationshiptosurface", "text"), ("streamorder", "integer"),
                    ("streamlevel", "integer"), ("arbolatesumkm", "real"), ("divergenceflag", "integer"),
                    ("startflag", "integer"), ("terminalflag", "integer")]
POLYGON_COLUMNS = [("permanent_identifier", "text"), ("fdate", "datetime"), ("gnis_id", "text"),
                   ("gnis_name", "text"), ("areasqkm", "real"), ("reachcode", "text"), ("ftype", "integer"),
                   ("fcode", "integer"), ("visibilityfilter", "integer"), ("ftype_name", "text"),
                   ("hydrographiccategory", "text"), ("reservoirtype", "text")]
LINE_COLUMNS = [("permanent_identifier", "text"), ("gnis_name", "text"), ("ftype", "integer"), ("fcode", "integer"),
                ("ftype_name", "text")]
POINT_COLUMNS = [("permanent_identifier", "text"), ("gnis_name", "text"), ("reachcode", "text"),
                 ("ftype", "integer"), ("fcode", "integer"), ("ftype_name", "text")]
EVENT_COLUMNS = [("permanent_identifier", "text"), ("reachcode", "text"), ("source_featureid", "text"),
                 ("eventtype", "integer"), ("ftype_name", "text")]
FLOW_COLUMNS = [("from_permanent_identifier", "text"), ("to_permanent_identifier", "text"),
                ("direction", "integer"), ("deltalevel", "integer")]


def flowline(pid, points, cls="canal_ditch", name=None, category=None, order=None, vis=None, flowdir=1, ftype=336):
    return {"permanent_identifier": pid, "fdate": "2015-03-02T00:00:00Z", "gnis_name": name, "lengthkm": 1.0,
            "reachcode": "17050114000" + pid[-3:], "flowdir": flowdir, "ftype": ftype, "fcode": ftype * 100,
            "visibilityfilter": vis, "class": cls, "hydrographiccategory": category, "streamorder": order,
            "geom": gp(wkb_multilinestring([[at(*p) for p in points]]))}


def nhd(path, flowlines=(), polygons=(), lines=(), points=(), events=(), flow=()):
    """An nhd.gpkg as prepare.py nhd writes it. polygons: dicts with layer 'waterbody' or 'area'."""
    g = Gpkg(path)
    g.table("flowline", FLOWLINE_COLUMNS, "geom", "MULTILINESTRING")
    g.table("waterbody", POLYGON_COLUMNS, "geom", "MULTIPOLYGON")
    g.table("area", POLYGON_COLUMNS[:-1], "geom", "MULTIPOLYGON")
    g.table("line", LINE_COLUMNS, "geom", "MULTILINESTRING")
    g.table("point", POINT_COLUMNS, "geom", "POINT")
    g.table("point_event", EVENT_COLUMNS, "geom", "POINT")
    g.table("fcode", [("fcode", "integer"), ("description", "text")])
    g.table("flow", FLOW_COLUMNS)
    for f in flowlines:
        g.insert("flowline", f)
    for p in polygons:
        p = dict(p)
        layer = p.pop("layer")
        if layer == "area":
            p.pop("reservoirtype", None)
        g.insert(layer, p)
    for f in lines:
        g.insert("line", f)
    for f in points:
        g.insert("point", f)
    for f in events:
        g.insert("point_event", f)
    for a, b in flow:
        g.insert("flow", {"from_permanent_identifier": a, "to_permanent_identifier": b, "direction": 709,
                          "deltalevel": 0})
    g.insert("fcode", {"fcode": 33600, "description": "Canal/Ditch"})
    g.close()


def hydroshare(path, canals):
    """A hydroshare.gpkg as prepare.py hydroshare writes it: canals [(id, call_number, name, type, points)]."""
    g = Gpkg(path)
    g.table("canal", [("id", "integer"), ("call_number", "text"), ("name", "text"), ("type", "text")], "geom",
            "MULTILINESTRING", srs=4326)
    for cid, call, name, kind, points in canals:
        g.insert("canal", {"id": cid, "call_number": call, "name": name, "type": kind,
                           "geom": gp(wkb_multilinestring([[at(*p) for p in points]]), srs=4326)})
    g.close()
