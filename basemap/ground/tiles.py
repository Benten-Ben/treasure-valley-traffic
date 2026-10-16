"""The ground's tiles (§3.5, C5): what the tile writer makes, how the app finds it, and the first-load budget.
Standard library only; the writer itself (G1a) runs in the worker image.

Two PMTiles files of 512 px lossy WebP tiles (XYZ, Web Mercator), opaque, Valley only:
- valley: z8-z15 over the map box (1.73 m per pixel at z15, which matches the 2 m painter), made from the painter
  grid: z15 tile by tile, each from its own window of the grid (tile_window), never a full mosaic; z14 down to z8
  each from its four children (2 x 2 average), as basemap/imagery.py does. z16 overzooms z15, the boxes included;
- detail: z17 in the tiles touching the ten class boxes (0.43 m per pixel), painted at 0.5 m: the box classes inside
  each box (their edge feathers inside the box) and the valley paint around them, so detail tiles are opaque and the
  step from the valley tiles is never a hole.

Pixels outside the grid are the flat Valley colour. Files are versioned by everything they're made from
(ground-<digest>.pmtiles and ground-detail-<digest>.pmtiles, never overwritten) and switched in with
tiles/manifest.json's "ground" entry, written atomically last. Without a painted ground the entry is
flat_entry(reason) (or absent: not built yet), and the app keeps today's flat Valley and Clay ground and says so.

**Budget** (spec.json "budget"): at the default view (z10, pitch 45, 1280 x 800) in Valley, the ground's requests (the
PMTiles header, directories and tiles) add up to at most 0.6 MB and 14 requests; in Clay, none.
"""

import datetime as dt
import hashlib
import json
import math
import os
import tempfile

from basemap.ground import grid

_S = grid.spec()
TILES = _S["tiles"]
TILE_SIZE = TILES["tileSize"]
FORMAT = TILES["format"]
QUALITY = TILES["quality"]
VALLEY_ZOOMS = (TILES["valley"]["minzoom"], TILES["valley"]["maxzoom"])
DETAIL_ZOOMS = (TILES["detail"]["minzoom"], TILES["detail"]["maxzoom"])
BUDGET = _S["budget"]
FLAT = _S["flat"]
SPEC_VERSION = _S["spec"]
ENTRY = "ground"                          # the key in tiles/manifest.json

_R = 6378137.0
CIRCUMFERENCE = 2 * math.pi * _R
_MERC_MAX = math.pi * _R


def mpp(z, lat):
    """Ground metres per pixel of a TILE_SIZE tile at zoom z and latitude lat."""
    return CIRCUMFERENCE * math.cos(math.radians(lat)) / (TILE_SIZE * 2 ** z)


def _tx(lon, z):
    return (lon + 180.0) / 360.0 * 2 ** z


def _ty(lat, z):
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z


def tile_range(lonlat, z):
    """(x range, y range) of the tiles touching a lon/lat box (west, south, east, north) at zoom z."""
    w, s, e, n = lonlat
    x0, x1 = math.floor(_tx(w, z)), math.ceil(_tx(e, z)) - 1
    y0, y1 = math.floor(_ty(n, z)), math.ceil(_ty(s, z)) - 1
    return range(x0, x1 + 1), range(y0, y1 + 1)


def tile_lonlat(z, x, y):
    """A tile's lon/lat box (west, south, east, north)."""
    def lat(t):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * t / 2 ** z))))
    return x / 2 ** z * 360.0 - 180.0, lat(y + 1), (x + 1) / 2 ** z * 360.0 - 180.0, lat(y)


def tile_mercator(z, x, y):
    """A tile's EPSG:3857 bounds (west, south, east, north), for the writer's warp."""
    size = 2 * _MERC_MAX / 2 ** z
    w, n = -_MERC_MAX + x * size, _MERC_MAX - y * size
    return w, n - size, w + size, n


def tile_window(z, x, y, res, margin_cells=2):
    """The window of the grid at `res` that a tile is made from: the tile's footprint in grid metres, widened to
    whole cells plus margin_cells for the resampling kernel."""
    return grid.window(grid.envelope(tile_lonlat(z, x, y), densify=8), res).pad(margin_cells)


def valley_tiles(z):
    """[(x, y)] of the valley file at zoom z: every tile touching the map box."""
    xs, ys = tile_range(grid.MAP_LONLAT, z)
    return [(x, y) for y in ys for x in xs]


def detail_tiles(z):
    """[(x, y)] of the detail file at zoom z: every tile touching one of the ten boxes."""
    out = set()
    for b in grid.boxes():
        xs, ys = tile_range(grid.lonlat_of(b.utm), z)
        out.update((x, y) for y in ys for x in xs)
    return sorted(out, key=lambda t: (t[1], t[0]))


def counts():
    """{"valley": {z: n}, "detail": {z: n}}."""
    return {"valley": {z: len(valley_tiles(z)) for z in range(VALLEY_ZOOMS[0], VALLEY_ZOOMS[1] + 1)},
            "detail": {z: len(detail_tiles(z)) for z in range(DETAIL_ZOOMS[0], DETAIL_ZOOMS[1] + 1)}}


def digest(plan, painter="", spec_text=None):
    """The build's version: sha256 over the tile spec, the painter's version, the version of every RAW input the plan
    reads (the painter's own, and its fallbacks') and the sha256 of every export layer it reads, the ground's products
    (mask v0, the classes) included. A new OSM cut, NAIP release, CDL year, mask v0 or class build gives a new name;
    the same inputs give the same name. Raises ValueError when a raw input the plan reads has no version."""
    if missing := plan.missing_versions:
        raise ValueError(f"the plan reads {', '.join(missing)} without a version: give each one's checksum, release "
                         "or year (inputs.resolve(..., versions=))")
    if spec_text is None:
        with open(grid.SPEC_PATH, encoding="utf-8") as f:
            spec_text = f.read()
    h = hashlib.sha256()
    h.update(spec_text.encode("utf-8"))
    h.update(f"\npainter {painter}\n".encode("utf-8"))
    for name in plan.raw_names:
        h.update(f"raw {name} {plan.versions[name]}\n".encode("utf-8"))
    for c in plan.choices:
        for lay in c.layers:
            h.update(f"export {lay.ref} {lay['sha256']}\n".encode("utf-8"))
        if c.fallback:
            h.update(f"fallback {c.use.ref} {c.use.fallback}\n".encode("utf-8"))
    return h.hexdigest()


def file_names(digest_hex):
    """(valley file, detail file) for a build."""
    d = digest_hex[:12]
    return f"ground-{d}.pmtiles", f"ground-detail-{d}.pmtiles"


def painted_entry(plan, digest_hex, built=None, boxes=None):
    """tiles/manifest.json's "ground" entry for a painted ground."""
    if plan.status != "painted":
        raise ValueError(f"the plan is {plan.status}: {plan.reason}")
    if missing := plan.missing_versions:
        raise ValueError(f"the plan reads {', '.join(missing)} without a version")
    valley, detail = file_names(digest_hex)
    return {
        "status": "painted",
        "file": valley,
        "tileSize": TILE_SIZE,
        "format": FORMAT,
        "minzoom": VALLEY_ZOOMS[0],
        "maxzoom": VALLEY_ZOOMS[1],
        "detail": {"file": detail, "minzoom": DETAIL_ZOOMS[0], "maxzoom": DETAIL_ZOOMS[1],
                   "boxes": [b.id for b in grid.boxes()] if boxes is None else list(boxes)},
        "attribution": "; ".join(plan.credits),
        "licence": plan.licence,
        "republish": plan.republish,
        "inputs": plan.refs + [f"raw/{n}@{plan.versions[n]}" for n in plan.raw_names],
        "fallbacks": [f"{c.use.ref}: {c.use.fallback}" for c in plan.choices if c.fallback],
        "built": built or dt.date.today().isoformat(),
        "spec": SPEC_VERSION,
    }


def flat_entry(reason, built=None):
    """tiles/manifest.json's "ground" entry when there's nothing to paint: the app keeps the flat ground (FLAT) and
    shows reason, in plain words."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("a flat ground says why")
    return {"status": "flat", "reason": reason.strip(), "built": built or dt.date.today().isoformat(),
            "spec": SPEC_VERSION}


def check_entry(e):
    """Raise ValueError unless e is a ground entry the app can read."""
    if not isinstance(e, dict) or e.get("status") not in ("painted", "flat"):
        raise ValueError("the ground entry's status must be painted or flat")
    if e["status"] == "flat":
        if set(e) != {"status", "reason", "built", "spec"} or not e["reason"].strip():
            raise ValueError("a flat entry has exactly status, reason, built and spec, with a reason")
        return
    need = {"status", "file", "tileSize", "format", "minzoom", "maxzoom", "detail", "attribution", "licence",
            "republish", "inputs", "fallbacks", "built", "spec"}
    if set(e) != need:
        raise ValueError(f"a painted entry has exactly {', '.join(sorted(need))}")
    if e["republish"] != "yes":
        raise ValueError("the ground is built from public inputs only (C17): republish must be yes")
    if (e["tileSize"], e["format"], e["minzoom"], e["maxzoom"]) != (TILE_SIZE, FORMAT, *VALLEY_ZOOMS):
        raise ValueError("the valley file doesn't match the tile spec")
    d = e["detail"]
    if (d.get("minzoom"), d.get("maxzoom")) != DETAIL_ZOOMS or not d.get("file"):
        raise ValueError("the detail file doesn't match the tile spec")


def update_manifest(tiles_dir, entry):
    """Put the ground entry into tiles/manifest.json, atomically (the app fetches it with no-cache). The other
    entries are kept as they are."""
    check_entry(entry)
    path = os.path.join(tiles_dir, "manifest.json")
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    m[ENTRY] = entry
    fd, tmp = tempfile.mkstemp(prefix=".manifest-", suffix=".json", dir=tiles_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def first_load(requests, look="valley"):
    """Check a first load's ground requests against the budget. requests: [{"url", "bytes"}] of every request the
    page made (the perf harness records them); those to the ground's files count. Returns (ok, bytes, count)."""
    mine = [r for r in requests if os.path.basename(str(r["url"]).split("?")[0]).startswith("ground-")]
    total = sum(int(r["bytes"]) for r in mine)
    b = BUDGET["valleyDefault" if look == "valley" else "clayDefault"]
    return total <= b["maxBytes"] and len(mine) <= b["maxRequests"], total, len(mine)
