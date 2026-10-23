"""Synthetic tiles for the browser specs (standard library only; nothing here is real data).

The laptop holds neither the landscape bake nor the painted ground, so the specs for baked contributions and the
ground run on these instead (plan v3 §4.1: fixtures are synthetic; §5: specs sample 3 or 4 layer stacks):

- `landscape-<digest>.pmtiles`: gzipped Mapbox vector tiles (extent 4096) cut from every
  `fixtures/<plugin>.<layer>.geojson`, one source-layer each, from the layer's own zooms up to z16 (a feature's
  integer `minzoom` field is a bake directive, left out of the tiles, as in the real bake). The file name follows the
  bake's rule (`landscape-` and 12 hex digits), so the bake's own entry check, `plan.check_entry`, passes on the
  `landscape` entry written beside it.
- `ground-<digest>.pmtiles` and `ground-detail-<digest>.pmtiles`: 512 px lossless WebP tiles of the Valley tone with a
  faint second tone in a checker (so a spec can see the ground drew), and a third tone in the detail file. The tiles
  are three constants below, made once with `cwebp -lossless` from solid 512 x 512 PNGs; no image library is needed
  to run this.
- `fixture-entries.json`: the `landscape` and `ground` entries for tiles/manifest.json. `app/scripts/tiles-fixture.mjs`
  merges them into a copy of the real manifest.

    python3 -m basemap.landscape.fixture --out DIR [--ground painted|flat|none]

A fixture layer's GeoJSON is a FeatureCollection in EPSG:4326 with a foreign member `tvt`: `geometry`, `fields`
(name: type, as the export's), `minzoom`, `maxzoom`, `licence`, `republish`, `credit`. Each feature has an integer `id`.
"""

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import json
import math
import os
import struct
import sys
from dataclasses import replace

from basemap.ground import grid, tiles as ground_tiles
from basemap.ground.pmtw import Writer
from basemap.landscape import pmtiles as P, plan

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
FIXTURE_VERSION = 1                          # bump when the tiles written from the same files change
BUILT = "2026-01-01"                         # fixed, so the same files give the same bytes
EXTENT = plan.SPEC["writer"]["extent"]
BUFFER = plan.SPEC["writer"]["buffer"]
ENTRIES_FILE = "fixture-entries.json"

# Lossless 512 x 512 solid WebP tiles. Made once with: cwebp -lossless -z 9 solid.png -o tile.webp, from PNGs of
# these colours (zlib-written, 512 x 512, 8-bit RGB).
WEBP = {
    "a": base64.b64decode("UklGRi4AAABXRUJQVlA4TCIAAAAv/8F/AAfQ87pXu/8BgUCyv/cMRfQ/4z//+c9//vOf//wf"),        # #EEE7DA
    "b": base64.b64decode("UklGRi4AAABXRUJQVlA4TCIAAAAv/8F/AAdQ8KIXuv8BgUCyv/cMRfQ/4z//+c9//vOf//wf"),        # #E8E0D0
    "d": base64.b64decode("UklGRi4AAABXRUJQVlA4TCIAAAAv/8F/AAfQ7IrXuP8BgUCyv/cMRfQ/4z//+c9//vOf//wf"),        # #E2D9C6
}


class FixtureError(ValueError):
    pass


# --- reading the layers -------------------------------------------------------------------------------------------

class Layer:
    def __init__(self, sid, path, doc):
        self.id, self.path = sid, path
        meta = doc.get("tvt")
        if doc.get("type") != "FeatureCollection" or not isinstance(meta, dict):
            raise FixtureError(f"{sid}: a FeatureCollection with a 'tvt' member")
        self.meta = meta
        for key in ("fields", "geometry"):
            if key not in meta:
                raise FixtureError(f"{sid}: the 'tvt' member needs {key!r}")
        self.fields = dict(meta["fields"])
        self.minzoom = max(int(meta.get("minzoom", plan.MINZOOM)), plan.MINZOOM)
        self.maxzoom = min(int(meta.get("maxzoom", plan.MAXZOOM)), plan.MAXZOOM)
        self.features = doc["features"]
        if not self.features:
            raise FixtureError(f"{sid}: a fixture layer needs a feature (an empty one isn't built)")
        ids = set()
        for f in self.features:
            i = f["properties"].get("id")
            if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i <= plan.MAX_ID or i in ids:
                raise FixtureError(f"{sid}: every feature needs a unique integer id from 0 to 2^53 - 1")
            ids.add(i)
        for name, kind in self.fields.items():
            if kind not in plan.TILE_TYPES:
                raise FixtureError(f"{sid}: field {name!r} is {kind}")
        if self.fields.get("id") not in plan.fgb.INTEGER_TYPES:
            raise FixtureError(f"{sid}: needs an integer id field")

    @property
    def tile_fields(self):
        return {k: v for k, v in self.fields.items() if k != plan.MINZOOM_FIELD}

    def feature_minzoom(self, f):
        return max(self.minzoom, int(f["properties"].get(plan.MINZOOM_FIELD) or 0))


def read_layers(folder=FIXTURES):
    """[Layer] from every `<plugin>.<layer>.geojson` in folder, by source-layer id."""
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".geojson"):
            continue
        sid = name[:-len(".geojson")]
        if not plan.SOURCE_LAYER_RE.match(sid):
            raise FixtureError(f"{name}: not named <plugin>.<layer>.geojson")
        path = os.path.join(folder, name)
        with open(path, encoding="utf-8") as f:
            out.append(Layer(sid, path, json.load(f)))
    if not out:
        raise FixtureError(f"no fixture layers in {folder}")
    return out


# --- cutting tiles --------------------------------------------------------------------------------------------------

def _world(lon, lat, z):
    """Tile units (fractional x, y) of a lon/lat at zoom z."""
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n


def _walk(geom, fn):
    """geom with fn applied to every [lon, lat] position."""
    def go(c):
        return fn(c) if c and isinstance(c[0], (int, float)) else [go(x) for x in c]
    return {"type": geom["type"], "coordinates": go(geom["coordinates"])}


def _positions(c):
    if c and isinstance(c[0], (int, float)):
        yield c
    else:
        for x in c:
            yield from _positions(x)


def _clip_line(pts, lo, hi):
    """A polyline cut to the square [lo, hi]: a list of pieces (Liang-Barsky per segment, joined while they run on)."""
    pieces, cur = [], []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy, t0, t1 = x1 - x0, y1 - y0, 0.0, 1.0
        for p, q in ((-dx, x0 - lo), (dx, hi - x0), (-dy, y0 - lo), (dy, hi - y0)):
            if p == 0:
                if q < 0:
                    t0, t1 = 1.0, 0.0
                    break
            else:
                r = q / p
                if p < 0:
                    t0 = max(t0, r)
                else:
                    t1 = min(t1, r)
        if t0 > t1:
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
            continue
        a, b = (x0 + t0 * dx, y0 + t0 * dy), (x0 + t1 * dx, y0 + t1 * dy)
        if cur and cur[-1] != a:
            if len(cur) > 1:
                pieces.append(cur)
            cur = []
        if not cur:
            cur = [a]
        cur.append(b)
        if t1 < 1.0:
            pieces.append(cur)
            cur = []
    if len(cur) > 1:
        pieces.append(cur)
    return pieces


def _clip_ring(ring, lo, hi):
    """A closed ring (without its repeated end point) cut to the square [lo, hi] (Sutherland-Hodgman)."""
    def edge(pts, inside, cut):
        out = []
        for i, b in enumerate(pts):
            a = pts[i - 1]
            if inside(b):
                if not inside(a):
                    out.append(cut(a, b))
                out.append(b)
            elif inside(a):
                out.append(cut(a, b))
        return out

    def at_x(v):
        return lambda a, b: (v, a[1] + (b[1] - a[1]) * (v - a[0]) / (b[0] - a[0]))

    def at_y(v):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (v - a[1]) / (b[1] - a[1]), v)

    pts = ring
    for inside, cut in ((lambda p: p[0] >= lo, at_x(lo)), (lambda p: p[0] <= hi, at_x(hi)),
                        (lambda p: p[1] >= lo, at_y(lo)), (lambda p: p[1] <= hi, at_y(hi))):
        if not pts:
            break
        pts = edge(pts, inside, cut)
    return pts


def _area2(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or out[-1] != p:
            out.append(p)
    return out


# --- the vector tile --------------------------------------------------------------------------------------------

def _varint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _zig(n):
    return (n << 1) ^ (n >> 63)


def _field(num, wire, payload):
    return _varint(num << 3 | wire) + payload


def _len(num, data):
    return _field(num, 2, _varint(len(data)) + data)


def _geometry(kind, parts):
    """MVT geometry commands. kind: 1 point, 2 line, 3 polygon; parts: points, polylines or rings (integer tile
    coordinates; a ring has no repeated end point and is already wound the right way)."""
    out, cx, cy = [], 0, 0

    def move(pt):
        nonlocal cx, cy
        out.extend((_zig(pt[0] - cx), _zig(pt[1] - cy)))
        cx, cy = pt

    if kind == 1:
        out.append(1 | len(parts) << 3)
        for pt in parts:
            move(pt)
    else:
        for part in parts:
            out.append(1 | 1 << 3)
            move(part[0])
            out.append(2 | (len(part) - 1) << 3)
            for pt in part[1:]:
                move(pt)
            if kind == 3:
                out.append(7 | 1 << 3)
    return b"".join(_varint(v) for v in out)


def _value(kind, v):
    if kind == "bool":
        return _field(7, 0, _varint(1 if v else 0))
    if kind == "string":
        return _len(1, str(v).encode("utf-8"))
    if kind in ("float", "double"):
        return _field(3, 1, struct.pack("<d", float(v)))
    v = int(v)
    return _field(5, 0, _varint(v)) if v >= 0 else _field(6, 0, _varint(_zig(v)))


class TileLayer:
    def __init__(self, layer):
        self.layer, self.keys, self.values, self.features = layer, [], {}, []
        self.fields = layer.tile_fields

    def add(self, feature, kind, geometry):
        props = feature["properties"]
        tags = []
        for name, ftype in self.fields.items():
            if props.get(name) is None:
                continue
            if name not in self.keys:
                self.keys.append(name)
            value = _value(ftype, props[name])
            tags += [self.keys.index(name), self.values.setdefault(value, len(self.values))]
        body = (_field(1, 0, _varint(props["id"])) + _len(2, b"".join(_varint(t) for t in tags))
                + _field(3, 0, _varint(kind)) + _len(4, geometry))
        self.features.append(_len(2, body))

    def encode(self):
        out = _field(15, 0, _varint(2)) + _len(1, self.layer.id.encode("utf-8"))
        out += b"".join(self.features)
        out += b"".join(_len(3, k.encode("utf-8")) for k in self.keys)
        out += b"".join(_len(4, v) for v in self.values)
        return out + _field(5, 0, _varint(EXTENT))


def _cut(feature, z, tx, ty):
    """(kind, geometry bytes) of a feature inside tile z/tx/ty (with the buffer), or None when nothing is left."""
    g = feature["geometry"]
    lo, hi = -BUFFER, EXTENT + BUFFER

    def local(c):
        x, y = _world(c[0], c[1], z)
        return ((x - tx) * EXTENT, (y - ty) * EXTENT)

    def snap(p):
        return (round(p[0]), round(p[1]))

    kind = g["type"]
    c = g["coordinates"]
    if kind in ("Point", "MultiPoint"):
        pts = [snap(local(p)) for p in ([c] if kind == "Point" else c)]
        pts = [p for p in pts if lo <= p[0] <= hi and lo <= p[1] <= hi]
        return (1, _geometry(1, pts)) if pts else None
    if kind in ("LineString", "MultiLineString"):
        pieces = []
        for line in ([c] if kind == "LineString" else c):
            for piece in _clip_line([local(p) for p in line], lo, hi):
                piece = _dedupe([snap(p) for p in piece])
                if len(piece) > 1:
                    pieces.append(piece)
        return (2, _geometry(2, pieces)) if pieces else None
    if kind in ("Polygon", "MultiPolygon"):
        rings = []
        for poly in ([c] if kind == "Polygon" else c):
            kept = []
            for i, ring in enumerate(poly):
                pts = _dedupe([snap(p) for p in _clip_ring([local(p) for p in ring[:-1]], lo, hi)])
                if len(pts) > 1 and pts[0] == pts[-1]:
                    pts.pop()
                if len(pts) < 3 or _area2(pts) == 0:
                    if i == 0:
                        break
                    continue
                if (_area2(pts) > 0) != (i == 0):        # exterior rings wind positive (y down), holes negative
                    pts.reverse()
                kept.append(pts)
            else:
                rings += kept
        return (3, _geometry(3, rings)) if rings else None
    raise FixtureError(f"{feature['properties'].get('id')}: geometry {kind}")


def cut_tiles(layers):
    """{(z, x, y): gzipped vector tile bytes} for every layer, every feature from its first zoom to its layer's last."""
    tiles = {}
    for lay in layers:
        for f in lay.features:
            pts = list(_positions(f["geometry"]["coordinates"]))
            for z in range(lay.feature_minzoom(f), lay.maxzoom + 1):
                xs, ys = zip(*(_world(p[0], p[1], z) for p in pts))
                pad = BUFFER / EXTENT
                n = 2 ** z
                for tx in range(max(0, math.floor(min(xs) - pad)), min(n - 1, math.floor(max(xs) + pad)) + 1):
                    for ty in range(max(0, math.floor(min(ys) - pad)), min(n - 1, math.floor(max(ys) + pad)) + 1):
                        cut = _cut(f, z, tx, ty)
                        if cut:
                            tiles.setdefault((z, tx, ty), {}).setdefault(lay.id, TileLayer(lay)).add(f, *cut)
    order = {lay.id: i for i, lay in enumerate(layers)}
    return {k: gzip.compress(b"".join(_len(3, tl.encode()) for tl in sorted(v.values(), key=lambda t: order[t.layer.id])),
                             mtime=0) for k, v in tiles.items()}


# --- the landscape file and its entry -------------------------------------------------------------------------------

def landscape_digest(layers):
    h = hashlib.sha256(f"landscape fixture {FIXTURE_VERSION}\n".encode())
    for lay in layers:
        with open(lay.path, "rb") as f:
            h.update(lay.id.encode() + b"\n" + f.read())
    return h.hexdigest()


def landscape_entry(layers, digest, zooms, sizes):
    summary = {}
    for lay in layers:
        summary[lay.id] = {
            "plugin": lay.id.split(".")[0], "layer": lay.id.split(".")[1], "build": "fixture",
            "geometry": lay.meta["geometry"], "features": len(lay.features), "fields": lay.tile_fields,
            "minzoom": lay.minzoom, "maxzoom": lay.maxzoom, "licence": lay.meta["licence"],
            "republish": lay.meta["republish"], "credit": list(lay.meta["credit"])}
    credits = []
    for lay in layers:
        credits += [c for c in lay.meta["credit"] if c not in credits]
    republish = plan.M.strictest(lay.meta["republish"] for lay in layers)
    budget_sizes = {t: sizes[t] for t in plan.budget_tiles() if t in sizes}
    return {
        "status": "baked", "file": plan.file_name(digest), "digest": digest, "format": plan.FORMAT,
        "minzoom": zooms[0], "maxzoom": zooms[1], "promoteId": plan.PROMOTE_ID,
        "layers": summary, "empty": [], "attribution": "; ".join(credits),
        "licences": sorted({lay.meta["licence"] for lay in layers}), "republish": republish,
        "access": plan.access_of(republish), "inputs": [f"{sid.replace('.', '/')}@fixture" for sid in summary],
        "budget": plan.measure_budget(budget_sizes, any(s.startswith("roads.") for s in summary)),
        "writer": "tvt landscape fixture", "built": BUILT, "spec": plan.SPEC_VERSION, "previous": None}


def write_landscape(out, layers):
    """Write the landscape file into out; returns its entry (checked with the bake's own check)."""
    digest = landscape_digest(layers)
    tiles = cut_tiles(layers)
    path = os.path.join(out, plan.file_name(digest))
    xs = [p[0] for lay in layers for f in lay.features for p in _positions(f["geometry"]["coordinates"])]
    ys = [p[1] for lay in layers for f in lay.features for p in _positions(f["geometry"]["coordinates"])]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    zooms = (min(z for z, _, _ in tiles), max(z for z, _, _ in tiles))
    fields = {t: "Number" for t in plan.fgb.INTEGER_TYPES}
    fields.update({"double": "Number", "float": "Number", "bool": "Boolean", "string": "String"})
    sizes = {k: len(v) for k, v in tiles.items()}
    # The entry is checked, then put in the file's own metadata (tvt.landscape), as the bake does.
    entry = landscape_entry(layers, digest, zooms, sizes)
    meta_entry = {k: v for k, v in entry.items() if k != "previous"}
    plan.check_entry(entry)
    plan.check_entry(meta_entry, in_manifest=False)
    metadata = {
        "name": "Treasure Valley Traffic landscape fixture", "format": "pbf",
        "minzoom": str(zooms[0]), "maxzoom": str(zooms[1]), "attribution": entry["attribution"],
        "description": "Synthetic tiles for the browser specs: nothing here is real data",
        "vector_layers": [{"id": lay.id, "fields": {k: fields[v] for k, v in lay.tile_fields.items()},
                           "minzoom": lay.minzoom, "maxzoom": lay.maxzoom} for lay in layers],
        "tvt": {"landscape": meta_entry}}
    w = Writer(path, tile_type=1, metadata=metadata)
    for (z, x, y), data in sorted(tiles.items()):
        w.add(z, x, y, data)
    header = w.finish(bounds, ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2, 14))
    with open(path, "r+b") as f:                       # the writer says "no compression"; these tiles are gzipped
        f.write(P.pack_header(replace(header, tile_compression=2)))
    return entry


# --- the ground -----------------------------------------------------------------------------------------------------

# The default view (z10, centre -116.4, 43.6) at z8-12, and downtown at z13-15 and (detail) z17.
VIEW = (-116.85, 43.3, -115.95, 43.9)
DOWNTOWN = "downtown"


def ground_tile_list():
    """([(z, x, y)] of the valley file, [(z, x, y)] of the detail file)."""
    box = next(b for b in grid.boxes() if b.id == DOWNTOWN)
    town = grid.lonlat_of(box.utm)
    valley = []
    for z in range(ground_tiles.VALLEY_ZOOMS[0], 13):
        xs, ys = ground_tiles.tile_range(VIEW, z)
        valley += [(z, x, y) for y in ys for x in xs]
    for z in range(13, ground_tiles.VALLEY_ZOOMS[1] + 1):
        xs, ys = ground_tiles.tile_range(town, z)
        valley += [(z, x, y) for y in ys for x in xs]
    xs, ys = ground_tiles.tile_range(town, ground_tiles.DETAIL_ZOOMS[0])
    detail = [(ground_tiles.DETAIL_ZOOMS[0], x, y) for y in ys for x in xs]
    return valley, detail, [DOWNTOWN]


def write_ground(out):
    """Write the two ground files into out; returns the painted entry (checked with the ground's own check)."""
    valley, detail, boxes = ground_tile_list()
    digest = hashlib.sha256(("ground fixture %d\n" % FIXTURE_VERSION).encode()
                            + b"".join(WEBP[k] for k in sorted(WEBP))
                            + repr((valley, detail)).encode()).hexdigest()
    v_name, d_name = ground_tiles.file_names(digest)
    meta = {"name": "Treasure Valley Traffic ground fixture", "format": "webp",
            "description": "Synthetic tiles for the browser specs: nothing here is real data"}
    for name, tiles, pick in ((v_name, valley, lambda z, x, y: WEBP["a" if (x + y) % 2 == 0 else "b"]),
                              (d_name, detail, lambda z, x, y: WEBP["d"])):
        w = Writer(os.path.join(out, name), tile_type=4, metadata=meta)
        for t in tiles:
            w.add(*t, pick(*t))
        w.finish(grid.MAP_LONLAT, (-116.4, 43.6, 10))
    entry = {
        "status": "painted", "file": v_name, "tileSize": ground_tiles.TILE_SIZE, "format": ground_tiles.FORMAT,
        "minzoom": ground_tiles.VALLEY_ZOOMS[0], "maxzoom": ground_tiles.VALLEY_ZOOMS[1],
        "detail": {"file": d_name, "minzoom": ground_tiles.DETAIL_ZOOMS[0], "maxzoom": ground_tiles.DETAIL_ZOOMS[1],
                   "boxes": boxes},
        "attribution": "Synthetic fixture: no real data", "licence": "ODbL-1.0", "republish": "yes",
        "inputs": ["fixture/ground@1"], "fallbacks": [], "built": BUILT, "spec": ground_tiles.SPEC_VERSION}
    ground_tiles.check_entry(entry)
    return entry


def build(out, ground="painted", fixtures=FIXTURES):
    """Write the fixture files and fixture-entries.json into out; returns the entries."""
    if ground not in ("painted", "flat", "none"):
        raise FixtureError("--ground is painted, flat or none")
    os.makedirs(out, exist_ok=True)
    entries = {"landscape": write_landscape(out, read_layers(fixtures))}
    if ground == "painted":
        entries["ground"] = write_ground(out)
    elif ground == "flat":
        entries["ground"] = ground_tiles.flat_entry("Synthetic fixture: the ground is flat on purpose.", built=BUILT)
        ground_tiles.check_entry(entries["ground"])
    with open(os.path.join(out, ENTRIES_FILE), "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=1, ensure_ascii=False)
        f.write("\n")
    return entries


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the folder to write the fixture files into")
    ap.add_argument("--ground", default="painted", choices=("painted", "flat", "none"))
    args = ap.parse_args(argv)
    try:
        entries = build(args.out, args.ground)
    except (FixtureError, ValueError) as err:
        print(f"fixture: {err}", file=sys.stderr)
        return 1
    for key, e in entries.items():
        print(f"{key}: {e.get('file') or e['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
