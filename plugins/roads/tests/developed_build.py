"""Synthetic developed-land builds for the tests, written with the standard library in the worker step's format
(plugins/roads/build/developed.py): developed.jsonl.gz, then build.json.

write() takes GeoJSON Polygons on NASS's grid (EPSG:5070) and fills build.json as the worker would: the CDL's
details (a made-up sha256), the pieces, and their area (the shoelace formula, holes taken out). Keyword arguments
override build.json's top-level fields, for the refusals.
"""

import gzip
import json
import os

from plugins.roads.ingest import developed as D


def ring_area(ring):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:]))) / 2


def polygon_area(polygon):
    if polygon["type"] != "Polygon":
        return 0.0                         # a malformed piece, for the refusals
    rings = polygon["coordinates"]
    return ring_area(rings[0]) - sum(ring_area(r) for r in rings[1:])


def square(x, y, size):
    """A square cell block on the grid: (x, y) its south-west corner, in EPSG:5070 metres."""
    return {"type": "Polygon", "coordinates": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]}


def write(folder, polygons, year=2025, res=10.0, cdl_sha256="c" * 64, **override):
    """A finished build in folder (made if needed). Returns build.json's content."""
    os.makedirs(folder, exist_ok=True)
    land = os.path.join(folder, D.LAND_FILE)
    with open(land, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        for n, p in enumerate(polygons, 1):
            gz.write((json.dumps({"n": n, "geom": p}, separators=(",", ":")) + "\n").encode())
    area = sum(polygon_area(p) for p in polygons)
    doc = {
        "format": D.FORMAT,
        "build_id": os.path.basename(os.path.normpath(folder)),
        "started_at": "2026-10-11T12:00:00Z",
        "finished_at": "2026-10-11T12:00:30Z",
        "classes": list(D.CLASSES),
        "srid": D.SRID,
        "cdl": {"file": f"cdl_{year}_{res:g}m.tif", "path": f"/srv/archive/farm/cdl/cdl_{year}_{res:g}m.tif",
                "year": year, "res_m": res, "sha256": cdl_sha256, "bytes": 1000, "license": D.LICENSE,
                "credit": D.credit(year)},
        "extent": [0, 0, 0, 0],
        "params": {"window_cells": 512, "connectivity": 4},
        "counts": {"pieces": len(polygons), "vertices": sum(len(r) for p in polygons for r in p["coordinates"]),
                   "cells": round(area / (res * res)), "area_km2": round(area / 1e6, 6)},
        "files": {D.LAND_FILE: {"sha256": D.sha256_of(land), "bytes": os.path.getsize(land)}},
    }
    doc.update(override)
    with open(os.path.join(folder, D.BUILD_FILE), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    return doc

