"""Build one area's trees (docs/19 §19.3, §19.5). Runs in the worker image (NumPy, SciPy, rasterio, pyproj):

    docker run --rm --memory 5g --memory-swap 5g --user $(id -u):$(id -g) -v "$PWD":/repo -v /srv/tvt:/srv/tvt \\
      -w /repo tvt-worker python plugins/trees/build/build.py --area c --dsm .../dsm.tif --dtm .../dtm.tif \\
      --mask .../zero_mask_c.npy --spring .../sentinel2/april2025 \\
      --summer .../sentinel2/july2025 --out $TVT_ARCHIVE/trees/<build-id>

Then `python3 -m ingest trees-load --build <dir>` loads it.

1. The placer fills the area from the lidar alone (place.py), tallest first, then repairs. Each crown's size and shape
   come from the width curve that explains the lidar best. Its type: narrow by the narrow rule (narrow_rule below), not
   by that curve; else conifer when the spring Sentinel-2 cue sees an evergreen crown in an area where its calls were
   checked against labelled trees (--spring and --summer: Seasons, spring_conifer and SPRING_CHECKED_AREAS below); else
   the curve's conifer call stands for now (KEEP_WIDTH_CONIFER), and broadleaf otherwise.
2. Writes trees.geojson (WGS84 points with the tree's fields), log.jsonl (one event per line) and build.json: crowns
   found in the lidar and nothing from an inventory.
3. Only then, when --anchors is given (a CSV of an inventory's trunk points, anchors.py; with --private-out, a folder
   outside the archive): each anchor planted before the lidar flight whose trunk point has lidar 3 m or taller within
   1.5 m, and that is not under a taller tree, is matched to the nearest crown the build already found within 2.5 m of
   it (one anchor to a crown). The anchors change no crown, so the crowns, ids and events in the public files are the
   ones a build without --anchors writes. The links, and the anchors with no such crown (sized from Boise's measured trees of
   the genus, Urban Tree Database, by trunk diameter), go to anchors.jsonl in --private-out, which only the private
   plugin that owns the inventory loads. It is never written into --out.

The area's inputs for the pilot are the land-cover spike's lidar products (0.5 m DSM and DTM in UTM 11N) and its
building mask (aligned footprints, zeroed with a buffer). The spring cue reads the early-April 2025 and July 2025
Sentinel-2 NDVI products on the ground's 10 m grid (basemap/ground/grid.py; "Contains modified Copernicus Sentinel data
2025"). The build never reads an inventory unless --anchors names one."""
import argparse, datetime as dt, hashlib, json, math, os, sys, time
import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anchors as anchor_file  # noqa: E402
from place import Model, Placer, PX  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if REPO not in sys.path:
    sys.path.append(REPO)                                        # basemap.ground's grid, when run as a script
from basemap.ground import grid  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(os.path.dirname(HERE), "model")
CONIFER_GENERA = {"abies", "calocedrus", "cedrus", "chamaecyparis", "cryptomeria", "cupressus", "juniperus", "larix",
                  "metasequoia", "picea", "pinus", "pseudotsuga", "sequoia", "sequoiadendron", "taxodium", "taxus",
                  "thuja", "tsuga"}
TRUNK_H_CELLS, TRUNK_REACH_CELLS = 3, 5   # crown top within 1.5 m of the trunk point; centre within 2.5 m
# The narrow rule (docs/19 §19.3), from the owner's 100 labelled trees (Oct 8): a narrow crown falls 45% of its height
# within 3 m of its top, but not all the way to the ground (a crown that ends within 3 m leaves the cue nothing to
# measure), from an even top (where the heights within 1 m of the top vary by a fifth of its height, the top is a broken
# crown edge or sits between crowns, and the fall measured from it isn't the crown's shape). Only where a typical
# broadleaf crown with that top reaches 3 m out (a top of about 8.3 m; the width curves were fitted on the lone trees'
# tops): below that, what lies 3 m out is the neighbourhood, not the crown. And only from the tree's own top: the
# profile's top is the highest unsmoothed cell, buildings left in, and one more than 2 m above the tree's height (the
# smoothed surface's, usually under 1 m lower) is a neighbour's crown or a roof.
NARROW_REACH_M = 3.0
NARROW_DROP_3M = (0.45, 0.95)
NARROW_ROUGH_MAX = 0.2
NARROW_OWN_TOP_M = 2.0
# Pending the owner (docs/DECISIONS.md): a placed tree that neither the narrow rule nor the spring cue types keeps the
# width curve's conifer call. That call is weak (of the 14 labelled trees the Oct 8 build called conifer, one was);
# False would leave conifers to the spring cue and an inventory's genus (docs/19 §19.3).
KEEP_WIDTH_CONIFER = True
# The spring cue (docs/19 §19.3; decision 24, Oct 8): an early-April 2025 Sentinel-2 image against July's. Evergreen
# crowns are green in early April and broadleaf crowns are still bare. But by then the valley's lawns and pastures are
# green too, under the crowns and around them, and a yard tree is a fraction of a 10 m cell, so in the valley a bare
# crown reads about as green as an evergreen one: there the image can't tell. Over snow it can: the ground reads white,
# so only evergreen foliage is green. So a crown is evergreen when at least half the clear April views of the cells
# within 50 m of it were snow, the crown is at least half a 10 m cell (so its cells' colour is mostly its own), and its
# April NDVI over its cells is 0.2 or more. The cue is one-sided: a crown that reads dark over snow may be a snow-laden
# or misregistered conifer (two of the owner's labelled conifers do), so it says nothing about it. Scored on the owner's
# 100 labelled trees (Oct 11).
SPRING_NEAR_M = 50.0
SPRING_SNOW_MIN = 0.5
SPRING_MIN_CROWN_M2 = 50.0
SPRING_NDVI_MIN = 0.2
# Where the cue types trees (Oct 11, after review): only in the areas (the build's --area) where its calls over snow were
# checked against the owner's labelled trees. Its false calls are untested anywhere: no labelled broadleaf or narrow tree
# over snow has a crown of 50 m² or more. In Bogus Basin (h) every real tree the owner labelled is a conifer, and the
# cue's 10 calls among the labelled crowns were 9 conifers and a part of a bigger tree. In Silver City (j) no labelled
# crown is that big, and two of its five labelled broadleaf trees read 0.22 and 0.30 over the snow, as green as four of
# the nine conifers the cue caught in Bogus Basin (0.20 to 0.25). So there, and in any area not listed, the cue is
# recorded with each tree (fit.spring) but types nothing until the owner labels that area's large green-over-snow crowns.
SPRING_CHECKED_AREAS = {"h": "Bogus Basin"}
SPRING_FILES = {"apr": ("spring", "ndvi_median.tif"), "clear": ("spring", "clear_count.tif"),
                "snow": ("spring", "snow_count.tif"), "jul": ("summer", "ndvi_median.tif")}
SENTINEL2_CREDIT = "Contains modified Copernicus Sentinel data 2025"
LIDAR_CREDIT = "U.S. Geological Survey, 3D Elevation Program"


def model_for(cm):
    """One rule everywhere (owner, Oct 8: no classification by place): every tree tries the three width curves from the
    lone trees and keeps the one that explains its crown best. Broadleaf takes the valley broadleaf curve (which includes
    the small trees), conifer the mountain conifers' (pointed, narrow crowns), narrow the valley conifers' and columnar
    trees'. Conifers and narrow trees share the narrow top shape. The curve sets the crown's size and shape; whether a
    placed tree is narrow comes from the narrow rule (crown_profile, narrow_rule, placed_type)."""
    W, Sh = cm["width"], cm["shape"]
    crowded = cm["crowded_shape_a"]
    narrow_shapes = [(Sh["narrow"]["a"], Sh["narrow"]["n"]), (crowded["narrow"], Sh["narrow"]["n"])]
    shapes = {"broadleaf": [(Sh["broadleaf"]["a"], Sh["broadleaf"]["n"]), (crowded["broadleaf"], Sh["broadleaf"]["n"])],
              "conifer": narrow_shapes, "narrow": narrow_shapes}
    widths = {"broadleaf": (W["valley broadleaf + small"]["a"], W["valley broadleaf + small"]["b"]),
              "conifer": (W["mountain conifer"]["a"], W["mountain conifer"]["b"]),
              "narrow": (W["valley conifer"]["a"], W["valley conifer"]["b"])}
    return Model(widths, shapes, W["valley broadleaf + small"]["sd_log"], ["broadleaf", "conifer", "narrow"])


PROFILE_ANGLES = np.linspace(0, 2 * np.pi, 16, endpoint=False)


def crown_profile(h, y, x, reach):
    """How a crown falls away from its top: the cues the owner's labelled trees were measured with (Oct 8).

    h: heights above ground on the 0.5 m grid (not smoothed, buildings left in). The top is the highest cell within
    `reach` cells of (y, x). drop_1m, drop_2m and drop_3m: the median fall from the top over 16 directions 1, 2 and 3 m
    out, as a share of the top's height. rough: the spread (sd) of the heights 0.5-1 m from the top, as a share.
    None when the top or its 3 m ring runs off the grid."""
    rows, cols = h.shape
    yi, xi, r = int(round(y)), int(round(x)), max(2, int(round(reach)))
    if not (0 <= yi < rows and 0 <= xi < cols):
        return None
    win = h[max(0, yi - r):yi + r + 1, max(0, xi - r):xi + r + 1]
    ty, tx = np.unravel_index(int(np.argmax(win)), win.shape)
    ty, tx = ty + max(0, yi - r), tx + max(0, xi - r)
    top = float(h[ty, tx])
    if not (6 <= ty < rows - 6 and 6 <= tx < cols - 6):
        return None
    out = {"top_m": round(top, 2)}
    for m in (1, 2, 3):
        yy = np.rint(ty + m / PX * np.sin(PROFILE_ANGLES)).astype(int)
        xx = np.rint(tx + m / PX * np.cos(PROFILE_ANGLES)).astype(int)
        out[f"drop_{m}m"] = round(float(np.median(top - h[yy, xx])) / max(top, 1.0), 3)
    d = np.hypot(*np.mgrid[-2:3, -2:3]) * PX
    near = (d > 0.25) & (d <= 1.0)                                    # the 12 cells 0.5-1 m from the top
    out["rough"] = round(float(np.std(h[ty - 2:ty + 3, tx - 2:tx + 3][near])) / max(top, 1.0), 3)
    return out


def narrow_min_top(model):
    """The top (m) from which a typical broadleaf crown reaches NARROW_REACH_M out, where the 3 m fall can tell."""
    a, b = model.widths["broadleaf"]
    return (2 * NARROW_REACH_M / a) ** (1 / b)


def narrow_rule(p, H, model):
    """True when a crown's profile (crown_profile) says narrow: the top is the tree's own (under NARROW_OWN_TOP_M above
    its height H), tall enough for the cue (narrow_min_top; the floor is on the top, not on H), the crown falls 45% of
    the top's height within 3 m of it but still stands above the ground there, and the top is even. Scored on the
    owner's 100 labelled trees (docs/19 §19.3)."""
    if p is None:
        return False
    lo, hi = NARROW_DROP_3M
    return (p["top_m"] - H < NARROW_OWN_TOP_M and p["top_m"] >= narrow_min_top(model)
            and lo <= p["drop_3m"] < hi and p["rough"] < NARROW_ROUGH_MAX)


def can_tell_spring(c):
    """True when the spring cue (Seasons.cue, or a stored fit's spring) can tell: an April view under snow around the
    crown, and a crown big enough for its cells' colour to be its own."""
    return (bool(c) and c.get("apr_ndvi") is not None and c.get("snow_share") is not None
            and c["snow_share"] >= SPRING_SNOW_MIN and c["crown_m2"] >= SPRING_MIN_CROWN_M2)


def evergreen(c):
    """True when the spring cue sees an evergreen crown: it can tell (can_tell_spring), and the crown's April NDVI is at
    least SPRING_NDVI_MIN, green over the snow. False says nothing: the cue is one-sided."""
    return can_tell_spring(c) and c["apr_ndvi"] >= SPRING_NDVI_MIN


def spring_conifer(c):
    """True when the spring cue types the crown conifer: it sees it evergreen (evergreen), in an area where its calls
    were checked against labelled trees (the cue's area_checked: the build's area is in SPRING_CHECKED_AREAS)."""
    return evergreen(c) and c.get("area_checked") is True


def placed_type(p, H, width_curve, model, spring=None):
    """A placed tree's type from its profile, its height, the width curve that sized its crown and its spring cue.
    Narrow when the narrow rule says so (first: one labelled narrow tree was sized by the conifer curve). Otherwise
    conifer when the spring cue types it (spring_conifer: an evergreen crown in a checked area). Otherwise conifer when
    that curve was the conifer one and KEEP_WIDTH_CONIFER (pending the owner), else broadleaf. The curve's narrow call
    isn't kept: on the labels, 2 of its 23 narrow calls on real trees were narrow trees (Oct 8: neighbours squeeze
    crowns, so width is a cue to the type only on lone trees)."""
    if narrow_rule(p, H, model):
        return "narrow"
    if spring_conifer(spring):
        return "conifer"
    return "conifer" if KEEP_WIDTH_CONIFER and width_curve == "conifer" else "broadleaf"


def type_placed(h, t, model, spring=None):
    """A placed tree's type and fit (placed_type). The fit keeps the width curve, the profile and the spring cue (None
    when the build had no Sentinel-2 inputs); its width is compared with the typical width on the curve that sized it,
    as the placer's size cost is."""
    prof = crown_profile(h, t["y"], t["x"], 0.6 * t["R"])
    typ = placed_type(prof, round(t["H"], 2), t["type"], model, spring)  # the height as stored, so a build can be retyped
    z = math.log(t["R"] / model.radius_cells(t["H"], t["type"])) / model.sd
    crowded = t["a"] < 0.6 if t["type"] == "broadleaf" else t["a"] < 0.8      # the curve's crowded top shape
    return typ, {"width_vs_typical_sd": round(z, 2), "crowded": crowded, "width_curve": t["type"], "profile": prof,
                 "spring": spring}


def horizontal_epsg(crs):
    """The EPSG code of a raster CRS's horizontal part (the QL1 lidar's products can open as NAD83(2011) / UTM 11N plus
    NAVD88 heights), or None."""
    c = CRS.from_user_input(crs.to_wkt())
    if c.is_compound:
        c = c.sub_crs_list[0]
    return c.to_epsg()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Seasons:
    """The spring cue's inputs around one area: the early-April 2025 Sentinel-2 NDVI median with its clear and snow
    view counts (spring_dir: ndvi_median.tif, clear_count.tif, snow_count.tif) and the July 2025 NDVI median (summer_dir:
    ndvi_median.tif), all on the ground's 10 m grid (basemap/ground/grid.py), read once as a window around the area's
    bounds (metres in UTM 11N: the lidar's NAD83 coordinates are the grid's under the null datum shift). area is the
    build's --area: the cue types trees only where it is in SPRING_CHECKED_AREAS."""

    def __init__(self, spring_dir, summer_dir, bounds, area=None):
        self.area, self.area_checked = area, area in SPRING_CHECKED_AREAS
        west, south, east, north = bounds
        res, pad = grid.BASE_RES, SPRING_NEAR_M + grid.BASE_RES
        self.col0 = math.floor((west - pad - grid.ORIGIN_X) / res)
        self.row0 = math.floor((grid.ORIGIN_Y - north - pad) / res)
        cols = math.ceil((east + pad - grid.ORIGIN_X) / res) - self.col0
        rows = math.ceil((grid.ORIGIN_Y - south + pad) / res) - self.row0
        self.west, self.north = grid.ORIGIN_X + self.col0 * res, grid.ORIGIN_Y - self.row0 * res
        self.a, self.nodata, self.files, self.tags = {}, {}, {}, {}
        for key, (which, name) in SPRING_FILES.items():
            path = os.path.join(spring_dir if which == "spring" else summer_dir, name)
            with rasterio.open(path) as ds:
                t = ds.transform
                if horizontal_epsg(ds.crs) != grid.EPSG or (t.a, t.e) != (res, -res) or t.b or t.d:
                    raise ValueError(f"{path}: not on the ground's 10 m grid (EPSG:{grid.EPSG})")
                c, r = (t.c - grid.ORIGIN_X) / res, (grid.ORIGIN_Y - t.f) / res
                if abs(c - round(c)) > 1e-6 or abs(r - round(r)) > 1e-6:
                    raise ValueError(f"{path}: its cells aren't the ground grid's")
                win = Window(self.col0 - round(c), self.row0 - round(r), cols, rows)
                fill = ds.nodata if ds.nodata is not None else 0
                self.a[key] = ds.read(1, window=win, boundless=True, fill_value=fill)
                self.nodata[key] = ds.nodata
                self.tags[which] = self.tags.get(which) or ds.tags()
            self.files[f"{which}/{name}"] = {"bytes": os.path.getsize(path), "sha256": sha256(path)}
        k = int(math.ceil(SPRING_NEAR_M / res)) + 1
        self.near_i, self.near_j = (v.ravel() for v in np.mgrid[-k:k + 1, -k:k + 1])

    def about(self):
        """What the build records of its Sentinel-2 inputs (no paths): acquisitions, credit, files' bytes and sha256, the
        rule, and whether the cue types trees in this area (area_checked, with the areas where it does)."""
        return {"april": self.tags["spring"].get("ACQUISITIONS"), "july": self.tags["summer"].get("ACQUISITIONS"),
                "credit": SENTINEL2_CREDIT, "files": self.files,
                "rule": {"near_m": SPRING_NEAR_M, "snow_min": SPRING_SNOW_MIN, "min_crown_m2": SPRING_MIN_CROWN_M2,
                         "ndvi_min": SPRING_NDVI_MIN},
                "area_checked": self.area_checked, "checked_areas": sorted(SPRING_CHECKED_AREAS)}

    def cue(self, x, y, R):
        """The spring cue for a crown of radius R (m) centred at (x, y) (metres): its April and July NDVI (the cells its
        disc covers, weighted by its area in each, sampled every 0.5 m), the snow share of the clear April views of the
        cells within SPRING_NEAR_M of its centre, its fewest clear April views, its area, whether it's evergreen, and
        whether the cue types trees in this area (area_checked; spring_conifer)."""
        rows, cols = self.a["apr"].shape
        res = grid.BASE_RES
        n = int(math.ceil(R / PX))
        off = np.arange(-n, n + 1) * PX
        dx, dy = np.meshgrid(off, off)
        inside = dx * dx + dy * dy <= R * R
        cc = np.floor((x + dx[inside] - self.west) / res).astype(int)
        rr = np.floor((self.north - (y + dy[inside])) / res).astype(int)
        ok = (rr >= 0) & (rr < rows) & (cc >= 0) & (cc < cols)
        if not ok.any():
            return None
        cells, w = np.unique(rr[ok] * cols + cc[ok], return_counts=True)
        r_i, c_i = cells // cols, cells % cols
        out = {}
        for key, name in (("apr", "apr_ndvi"), ("jul", "jul_ndvi")):
            v = self.a[key][r_i, c_i].astype(float)
            good = v != self.nodata[key]
            out[name] = round(float((v[good] * w[good]).sum() / w[good].sum()) / 1e4, 3) if good.any() else None
        out["april_views"] = int(self.a["clear"][r_i, c_i].min())
        rr = int(math.floor((self.north - y) / res)) + self.near_i
        cc = int(math.floor((x - self.west) / res)) + self.near_j
        near = (np.hypot(self.west + (cc + 0.5) * res - x, self.north - (rr + 0.5) * res - y) <= SPRING_NEAR_M)
        near &= (rr >= 0) & (rr < rows) & (cc >= 0) & (cc < cols)
        clear = self.a["clear"][rr[near], cc[near]].astype(float)
        snow = self.a["snow"][rr[near], cc[near]][clear > 0]
        out["snow_share"] = round(float((snow / clear[clear > 0]).mean()), 2) if (clear > 0).any() else None
        out["crown_m2"] = round(math.pi * R * R, 1)
        out["evergreen"] = evergreen(out)
        out["area_checked"] = self.area_checked
        return out


def utd_size(utd, genus, trunk_in, conifer):
    """Height and crown width (m) for a trunk diameter, from Boise's measured trees of the genus (else of the type)."""
    d_cm = max(2.5, (trunk_in or 2.0) * 2.54)
    f = utd["by_genus"].get((genus or "").capitalize()) or utd["by_type"]["CEL" if conifer else "BDL"]
    h = f["height"]["a"] * d_cm ** f["height"]["b"]
    w = f["crown_width"]["a"] * d_cm ** f["crown_width"]["b"]
    return round(h, 2), round(w, 2)


def read_anchors(path, to_rc, shape, lidar_ms):
    out = []
    for r in anchor_file.read_rows(path):
        inst = r.get("installed_ms")
        if inst and lidar_ms and float(inst) > lidar_ms:
            continue                                             # planted after the flight: not in the lidar
        row, col = to_rc(float(r["lon"]), float(r["lat"]))
        if not (0 <= row < shape[0] and 0 <= col < shape[1]):
            continue
        genus = (r.get("genus") or "").strip().lower()
        out.append({"source": r["source"], "source_id": r["source_id"], "row": row, "col": col,
                    "genus": genus, "trunk_in": float(r["trunk_in"]) if r.get("trunk_in") else None,
                    "conifer": genus in CONIFER_GENERA, "after_flight": False})
    return out


def sources(a, seasons):
    """The outside data a build read, for build.json's params: the lidar and Sentinel-2 by their names in
    plugins/trees/plugin.json (its manual sources). Anchors (--anchors) are not a source of the public build and are not
    recorded in it."""
    out = [{"source": "trees/usgs_3dep_lidar", "credit": LIDAR_CREDIT, "version": a.lidar}]
    if seasons:
        ab = seasons.about()
        out.append({"source": "trees/sentinel2", "credit": SENTINEL2_CREDIT,
                    "version": f"early April 2025 ({ab['april']}); July 2025 ({ab['july']})"})
    return out


def spring_counts(trees):
    """Among placed trees: how many the spring cue could tell, how many it saw evergreen, how many it typed conifer,
    and how many evergreen crowns it left untyped because the area isn't checked (held_back)."""
    placed = [t for t in trees if t["kind"] == "placed"]
    sp = [t["fit"].get("spring") for t in placed]
    return {"can_tell": sum(1 for c in sp if can_tell_spring(c)),
            "evergreen": sum(1 for c in sp if evergreen(c)),
            "conifer": sum(1 for t, c in zip(placed, sp) if spring_conifer(c) and t["type"] == "conifer"),
            "held_back": sum(1 for c in sp if evergreen(c) and not spring_conifer(c))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--area", required=True)
    ap.add_argument("--dsm", required=True)
    ap.add_argument("--dtm", required=True)
    ap.add_argument("--mask", help="building mask (.npy, the DSM's grid)")
    ap.add_argument("--anchors", help="an inventory's trunk points (CSV: " + ", ".join(anchor_file.CSV_FIELDS) + "); see anchors.py")
    ap.add_argument("--private-out", help="with --anchors: the folder for anchors.jsonl, under the private root and "
                                          "outside --out and the archive (never a folder the scratch jobs can read)")
    ap.add_argument("--private-root", help="the private files' folder that --private-out must be under "
                                           "(default " + anchor_file.PRIVATE_ROOT + ")")
    ap.add_argument("--lidar", default="USGS 3DEP QL1 lidar", help="the survey's name, for the log")
    ap.add_argument("--lidar-date", help="the flight date (YYYY-MM-DD); later plantings are not matched to a crown")
    ap.add_argument("--theta", type=float, default=0.2, help="overlap limit (share of the smaller crown); 0.2 calibrated Oct 8")
    ap.add_argument("--lam", type=float, default=40.0, help="per-tree cost (metres x cells); 40 from the owner's 100 labelled trees (Oct 8)")
    ap.add_argument("--sweeps", type=int, default=2)
    ap.add_argument("--window", help="row0,col0,rows,cols: build only this part (tests)")
    ap.add_argument("--spring", help="the early-April Sentinel-2 folder (ndvi_median.tif, clear_count.tif, snow_count.tif)"
                                     " for the spring cue; with --summer")
    ap.add_argument("--summer", help="the July Sentinel-2 folder (ndvi_median.tif); with --spring")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if bool(a.spring) != bool(a.summer):
        ap.error("--spring and --summer go together")
    if bool(a.anchors) != bool(a.private_out):
        ap.error("--anchors and --private-out go together")
    if a.anchors:
        try:
            anchor_file.check_private_dir(a.private_out, a.out,
                                          [os.environ.get(v) for v in ("TVT_ARCHIVE", "TVT_PROD_ARCHIVE")],
                                          a.private_root)
        except ValueError as e:
            ap.error(str(e))
    t0 = time.time(); started = dt.datetime.now(dt.timezone.utc)
    cm = json.load(open(os.path.join(MODEL_DIR, "crown_model.json")))
    utd = json.load(open(os.path.join(MODEL_DIR, "utd_boise.json")))
    with rasterio.open(a.dsm) as ds:
        dsm = ds.read(1).astype(np.float32); nod = ds.nodata; tf = ds.transform; crs = ds.crs
    with rasterio.open(a.dtm) as ds:
        dtm = ds.read(1).astype(np.float32)
    bad = (dsm == nod) | (dtm == nod) | ~np.isfinite(dsm) | ~np.isfinite(dtm)
    h = np.where(bad, 0, np.clip(dsm - dtm, 0, None))
    bld = np.load(a.mask) if a.mask else np.zeros(h.shape, bool)
    r0 = c0 = 0
    if a.window:
        r0, c0, nr, nc = (int(v) for v in a.window.split(","))
        sl = (slice(r0, r0 + nr), slice(c0, c0 + nc))
        h, bld, bad, dtm = h[sl], bld[sl], bad[sl], dtm[sl]
    seasons = None
    if a.spring:
        epsg = horizontal_epsg(crs)
        if epsg is None or not grid.same_coordinates(epsg):
            sys.exit(f"--spring: the lidar's CRS ({crs}) isn't UTM 11N, so it can't be read on the Sentinel-2 grid")
        (xa, ya), (xb, yb) = tf * (c0, r0), tf * (c0 + h.shape[1], r0 + h.shape[0])
        seasons = Seasons(a.spring, a.summer, (min(xa, xb), min(ya, yb), max(xa, xb), max(ya, yb)), a.area)
        if not seasons.area_checked:
            print(f"spring cue: area {a.area!r} isn't one where its calls were checked against labelled trees "
                  f"({', '.join(sorted(SPRING_CHECKED_AREAS))}): it is recorded with each tree but types none", flush=True)
    s = ndimage.gaussian_filter(np.where(bld, 0, h), 1.0)
    valid = ~bld & ~bad
    model = model_for(cm)
    # seeds within 1 m of a building must be 6 m or taller: shorter ones there are mostly roof slivers
    near_bld = ndimage.binary_dilation(bld, iterations=2) & ~bld
    pl = Placer(s, valid, model, theta=a.theta, lam=a.lam, avoid=near_bld)
    to_xy = Transformer.from_crs(crs, 4326, always_xy=True)
    from_ll = Transformer.from_crs(4326, crs, always_xy=True)
    inv = ~tf
    def to_rc(lon, lat):
        x, y = from_ll.transform(lon, lat); col, row = inv * (x, y)
        return row - r0, col - c0
    def to_ll(row, col):
        x, y = tf * (col + c0 + 0.5, row + r0 + 0.5); lon, lat = to_xy.transform(x, y)
        return x, y, lon, lat
    lidar_ms = None
    if a.lidar_date:
        lidar_ms = dt.datetime.fromisoformat(a.lidar_date).replace(tzinfo=dt.timezone.utc).timestamp() * 1000 + 86400000
    flight_at = (a.lidar_date + "T12:00:00Z") if a.lidar_date else started.isoformat()
    built_at = started.isoformat()
    out_trees, log, private = [], [], []
    build_id = os.path.basename(os.path.normpath(a.out))
    # 1. the anchors, measured and not used: they take no part in placing crowns (see step 4)
    anchors = read_anchors(a.anchors, to_rc, h.shape, lidar_ms) if a.anchors else []
    for an in anchors:
        y, x = int(round(an["row"])), int(round(an["col"]))
        r = TRUNK_H_CELLS
        win = s[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
        an["H"] = float(win.max()) if win.size else 0.0
        exp_h, _ = utd_size(utd, an["genus"], an["trunk_in"], an["conifer"]) if an["trunk_in"] else (None, None)
        an["under"] = exp_h is not None and an["H"] > max(1.8 * exp_h, exp_h + 6)    # the crown above is another tree's
        gy, gx = min(max(y, 0), h.shape[0] - 1), min(max(x, 0), h.shape[1] - 1)
        an["can_match"] = an["H"] >= pl.tree_h and not an["under"] and bool(valid[gy, gx])
    # 2. the placer fills the area from the lidar alone: the same crowns with or without anchors
    pl.run_greedy(log=lambda m: print(m, flush=True))
    pl.repair(sweeps=a.sweeps, log=lambda m: print(m, flush=True))
    # 3. write
    for t in pl.alive():
        x_m, y_m, lon, lat = to_ll(t["y"], t["x"])
        gy, gx = int(min(max(round(t["y"]), 0), h.shape[0] - 1)), int(min(max(round(t["x"]), 0), h.shape[1] - 1))
        ground = float(dtm[gy, gx]) if not bad[gy, gx] else None
        common = {"lon": lon, "lat": lat, "ground_m": ground, "height_m": round(t["H"], 2),
                  "crown_radius_m": round(t["R"] * PX, 2), "crown_a": round(t["a"], 3), "crown_n": round(t["n"], 3), "lidar": a.lidar}
        # Every crown is a tree found in the lidar, sized, shaped and typed from its own profile (and the spring cue).
        # Anchors play no part in finding it, so the public rows are the ones a build without --anchors writes.
        tid = f"{a.area}-{int(round(x_m))}-{int(round(y_m))}"
        spring = seasons.cue(x_m, y_m, t["R"] * PX) if seasons else None
        typ, fit = type_placed(h, t, model, spring)
        tr = {"id": tid, "kind": "placed", "type": typ, **common, "fit": fit}
        ev = {"at": flight_at, "event": "placed",
              "detail": {"lidar": a.lidar, "height_m": round(t["H"], 2), "crown_width_m": round(2 * t["R"] * PX, 2),
                         "theta": a.theta}, "_tree": tr}
        out_trees.append(tr); log.append(ev)
    # ids can collide when two crowns round to the same metre: suffix them
    seen = {}
    for tr in out_trees:
        k = tr["id"]
        if k in seen:
            seen[k] += 1; tr["id"] = f"{k}-{seen[k]}"
        else:
            seen[k] = 0
    for e in log:
        e["tree_id"] = e.pop("_tree")["id"]
    # 4. only now the anchors: each is matched to the nearest crown the build already found within 2.5 m of its trunk
    # point (one anchor to a crown), and the rest are the inventory's trees the lidar doesn't show. The crowns are never
    # changed by this, so nothing in the public rows tells a matched crown from any other.
    crowns = pl.alive()                                         # in the order of out_trees
    can = [i for i, an in enumerate(anchors) if an["can_match"]]
    pairs = anchor_file.match([(anchors[i]["row"], anchors[i]["col"]) for i in can], [(t["y"], t["x"]) for t in crowns],
                              TRUNK_REACH_CELLS)
    pos = {i: n for n, i in enumerate(can)}
    n_cat = n_est = 0
    for k, an in enumerate(anchors):
        j = pairs.get(pos.get(k))
        if j is not None:
            ci, dist = j
            tr, t = out_trees[ci], crowns[ci]
            off = round(dist * PX, 2)
            private.append(anchor_file.matched(
                tr["id"], an, a.area, build_id, off, flight_at,
                {"lidar": a.lidar, "height_m": round(t["H"], 2), "crown_width_m": round(2 * t["R"] * PX, 2),
                 "trunk_to_crown_m": off}))
            n_cat += 1
            continue
        y, x = int(round(an["row"])), int(round(an["col"]))
        gy, gx = min(max(y, 0), h.shape[0] - 1), min(max(x, 0), h.shape[1] - 1)
        hh, ww = utd_size(utd, an["genus"], an["trunk_in"], an["conifer"])
        _, _, lon, lat = to_ll(an["row"], an["col"])
        why = ("under a taller tree's crown: the lidar there is far taller than its trunk diameter predicts" if an["under"]
               else "no crown the build found within 2.5 m of its trunk point" if an["H"] >= pl.tree_h
               else "no crown 3 m or taller within 1.5 m of its trunk point in the lidar")
        private.append(anchor_file.estimated(
            an, a.area, build_id,
            {"type": "conifer" if an["conifer"] else "broadleaf", "lon": lon, "lat": lat,
             "ground_m": float(dtm[gy, gx]) if not bad[gy, gx] else None, "height_m": hh,
             "crown_radius_m": round(ww / 2, 2), "crown_a": None, "crown_n": None, "lidar": None,
             "fit": {"from": "Urban Tree Database, Boise, by genus and trunk diameter", "trunk_in": an["trunk_in"],
                     "under_taller_crown": bool(an["under"]), "lidar_height_there_m": round(an["H"], 1)}},
            built_at, {"why": why, "height_m": hh, "crown_width_m": ww, "trunk_in": an["trunk_in"]}))
        n_est += 1
    print(f"anchors: {len(anchors)} in the area, {n_cat} matched to a crown, {n_est} estimated", flush=True)
    os.makedirs(a.out, exist_ok=True)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(tr["lon"], 7), round(tr["lat"], 7)]},
         "properties": {k: v for k, v in tr.items() if k not in ("lon", "lat")}} for tr in out_trees]}
    json.dump(fc, open(os.path.join(a.out, "trees.geojson"), "w"))
    with open(os.path.join(a.out, "log.jsonl"), "w") as f:
        for e in log:
            f.write(json.dumps(e) + "\n")
    anchor_file.write(a.private_out, private)
    canopy = (s >= 2) & valid
    err = np.abs(s - pl.E)[canopy]
    build = {"build_id": build_id, "area": a.area, "started_at": started.isoformat(),
             "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "params": {"theta": a.theta, "lam": a.lam, "sweeps": a.sweeps, "lidar": a.lidar, "lidar_date": a.lidar_date,
                        "window": a.window, "model": cm["source"][:200],
                        "narrow_rule": {"drop_3m": list(NARROW_DROP_3M), "rough_max": NARROW_ROUGH_MAX,
                                        "min_top_m": round(narrow_min_top(model), 2), "own_top_m": NARROW_OWN_TOP_M},
                        "conifer_from_width_curve": KEEP_WIDTH_CONIFER,
                        "spring": seasons.about() if seasons else None, "sources": sources(a, seasons)},
             "counts": {"trees": len(out_trees),
                        "types": {k: sum(1 for tr in out_trees if tr["type"] == k) for k in ("broadleaf", "conifer", "narrow")},
                        "spring": spring_counts(out_trees) if seasons else None,
                        "surface_mae_m": round(float(err.mean()), 3) if err.size else None,
                        "surface_within_1_5m": round(float((err <= 1.5).mean()), 3) if err.size else None,
                        "seconds": round(time.time() - t0)}}
    json.dump(build, open(os.path.join(a.out, "build.json"), "w"), indent=1)
    print(json.dumps(build["counts"]), flush=True)


if __name__ == "__main__":
    main()
