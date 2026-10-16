"""The land-cover classes in the ten boxes: the land-cover spike's rules, as the ground's own worker step (G1a).
Pure NumPy, SciPy and scikit-image, no I/O: classes.py reads the inputs and hands them here as 2-D arrays on the
lidar's 0.5 m grid (row 0 at the north). The rules and every number come from the spike's experiments on the ten
boxes' central 500 m (Oct 8; the owner's scheme in docs/DECISIONS.md, Oct 8):

- exp26, variant B: the owner's scheme per 0.5 m cell. Roof; tree (2.4 m and up, and a shrub-height crown's skirt or
  gap); shrub (the shrub rule's kept cells, docs/19 §19.8); crop (pieces the shrub rule gave to a crop field); the rest
  of the 0.3-2.4 m band is tall grass, green or dry by the photo's near-infrared, dry when the lidar calls it a plant,
  and otherwise a hard thing (rock, car, equipment), or a wall or fence when it's a straight thin run; an even patch
  of the band (a sheet: 3 x 3 height spread under SHEET_CUT, under 1.2 m, 10 m^2 or more) is tall grass, not shrub.
  Under 0.3 m: green is short green grass.
- exp28b: flat, not-green ground is surfaced where the photo's NDVI (a 2.5 m median) is below the bare cut, in
  patches of 4 m^2 or more; dark to the lidar (asphalt) or pale (dirt, gravel, concrete, rock). The rest is short
  dry grass.
- exp31, "as of July": one green cut and one bare cut for every box on Sentinel-2's NDVI scale (the photo's NDVI goes
  through its flight day's curve first), and the July rule. Per 10 m Sentinel-2 cell, July 2025's green share of the
  cell's non-tree part (unmixed with the cell's own green and not-green levels and its tree share) is compared with
  the photo's; where they differ by more than the margin, that share of the cell's low cells dries (least green
  first) or greens (greenest first, never mapped roads, lidar-dark ground or roof rings). Where even July's greenest
  view shows no green, all of the cell's green low cells dry; where even its least green view is all green, all its
  eligible low cells green. Cells dried this way are tall dry grass whatever the lidar says.
- exp27: the floor. Under trees, shrubs, hard things and walls the ground is filled from the nearest ground cell
  (the owner: grass grows under trees, "fills the spaces left by trees specifically with what's around it"); under
  closed canopy (trees on 85% of the 30 m around) it's forest floor.
- New in G1a (owner, Oct 8): **mapped tracks.** In box f (photographed May 25) the July rule's bare cut loses every
  dirt track: May's curve lifts bare ground above it. OpenStreetMap's mapped tracks bring them back where the photo
  shows them: short dry grass within TRACK_HALF_M of a track's line becomes pale surfaced ground where the photo's
  brightness (a 2.5 m median) stands TRACK_GAIN above the ground beside the track (TRACK_RING_M).

Water isn't a class: it comes from map data (the owner, Oct 8; mask v0 and water's export). The spike's water cue is
dropped. The crop class from farm's crop cover (decision 15) is the painter's: it paints a cell as crop where the crop
cover says crop and the cell's class may be one (CROP_MAY_BE).

Every array is on one grid: h heights above the bare earth (m), bld buildings, bad cells without lidar, edge the 1 m
ring around buildings, rough the 3 x 3 height spread, plant the lidar's plant cue, kept / treecue / field the shrub
rule's cells (shrub, skirt or gap of a tree, crop piece), p the photo's NDVI on Sentinel-2's scale, dark the lidar's
dark ground, lum the photo's brightness.
"""

import numpy as np
from scipy import ndimage as ndi
from skimage.measure import label as cc_label, regionprops
from skimage.morphology import skeletonize

PX = 0.5                          # metres per cell

# The classes, as the box GeoTIFFs' band values (stable: the painter and the sheets read them).
CLASSES = {
    0: "no data",
    1: "roof",
    2: "tree",
    3: "shrub",
    4: "crop",
    5: "tall green grass",
    6: "tall dry grass",
    7: "short green grass",
    8: "short dry grass",
    9: "surfaced, dark",
    10: "surfaced, pale",
    11: "hard thing",
    12: "wall or fence",
    13: "forest floor",
}
C = {name: code for code, name in CLASSES.items()}
NODATA, ROOF, TREE, SHRUB, CROP = 0, 1, 2, 3, 4
TALL_GREEN, TALL_DRY, SHORT_GREEN, SHORT_DRY, DARK, PALE = 5, 6, 7, 8, 9, 10
HARD, WALL, FOREST_FLOOR = 11, 12, 13
_FLAT_NOT_GREEN = 255             # a placeholder inside scheme() until the surfaced split

# What stands on the ground (its floor is filled), and what the floor is filled from (exp27).
COVER = (TREE, SHRUB, HARD, WALL)
GROUND = (CROP, TALL_GREEN, TALL_DRY, SHORT_GREEN, SHORT_DRY, DARK, PALE)
# A cell the painter may paint as crop where farm's crop cover says crop (farm's design: grass of any kind, pale
# surfaced ground (tilled soil), hard things (wheel lines, stubble) and the shrub rule's crop pieces; roofs, trees,
# kept shrubs, dark surfaced ground and walls stay as they are). Read against the class band, before the floor.
CROP_MAY_BE = (CROP, TALL_GREEN, TALL_DRY, SHORT_GREEN, SHORT_DRY, PALE, HARD)

BAND_M = (0.3, 2.4)               # the shrub and tall-grass band; from 2.4 m it's a tree (§19.3)
PLANT_RETURNS = 3                 # the lidar calls a cell a plant: this many returns above the ground ...
PLANT_SCATTER = 0.25              # ... scattered at least this much (the shrub rule's cue)
EDGE_CELLS = 2                    # the 1 m ring around buildings (roof slivers)

# exp26 variant B: sheets. SHEET_CUT is the Youden split of the 3 x 3 height spread between crop-field band cells
# (known sheets) and isolated, single-topped shrubs (known clumps), over the ten boxes.
SHEET_CUT = 0.27                  # m
SHEET_MAX_H = 1.2                 # m
SHEET_MIN_CELLS = 40              # 10 m^2
# exp26: walls and fences, straight thin runs of the band's cells that are green neither time
THIN_MIN_AREA = 12                # cells
THIN_MIN_LENGTH = 12              # cells (major axis)
THIN_AREA_PER_SKELETON = 2.2      # cells of area per cell of skeleton: about one cell wide
THIN_MAX_WIDTH = 3.0              # cells (minor axis)
THIN_STRAIGHT = 0.8               # the major axis at least this share of the skeleton's length

# exp31: the cuts on Sentinel-2's NDVI scale, one for every box (no per-box Otsu, the owner).
GREEN_CUT = 0.45                  # Otsu of the pooled photo NDVI of the low cells, boxes weighted equally
BARE_CUT = 0.16                   # the smallest mean |ours - RCMAP bare ground| over the six boxes with RCMAP
BARE_MEDIAN_CELLS = 5             # 2.5 m median
BARE_MIN_CELLS = 16               # 4 m^2 patches
DARK_CUT = 0.85                   # lidar ground brightness (each point over its flight line's median), 2.5 m median
# exp31: the July rule
MARGIN = 0.35                     # 2 robust standard deviations of x_J - x_P, the median over the boxes
DRY_MAX = 0.30                    # a 10 m cell never green in July: its July maximum at most this ("cured")
WET_MIN = 0.55                    # ... always green: its July minimum at least this ("irrigated")
MIN_VIEWS = 3                     # clear July views a cell needs
MIN_PIX = 200                     # valid 0.5 m cells a 10 m cell needs
MIN_NONTREE = 100                 # ... of them not tree
MAX_TREE = 0.7                    # a cell 70% tree or more is skipped
TREE_CELL_SHARE = 0.8             # a box's July tree level: the median July NDVI of its cells this much tree ...
TREE_LEVEL_MIN_CELLS = 20         # ... when it has this many; else the pooled level
TREE_LEVEL_POOLED = 0.70          # the ten boxes' pooled level (exp31)
LEVEL_MIN_CELLS = 20              # a 10 m cell's own green (V) or not-green (N) level needs this many cells
V_DEFAULT, V_RANGE = 0.80, (0.55, 0.95)
N_DEFAULT, N_RANGE = 0.20, (0.0, 0.30)
S2_CELL = 20                      # 0.5 m cells to a 10 m Sentinel-2 cell
# exp27: the floor
CANOPY_WINDOW_CELLS = 61          # 30 m
CANOPY_SHARE = 0.85
# G1a: mapped tracks (box f)
TRACK_HALF_M = 2.0                # a track's tread: within this of its mapped line
TRACK_RING_M = (6.0, 20.0)        # the ground beside it
TRACK_GAIN = 0.04                 # the tread's brightness over the ring's level, as a share
TRACK_MIN_RING_CELLS = 40         # ring cells the level needs
TRACK_LEVEL_CELLS = 81            # 40 m: the ground beside the track, around each cell

EIGHT = np.ones((3, 3), bool)


def roughness(h, bld):
    """The 3 x 3 height spread (standard deviation, m), with buildings at 0 (exp22)."""
    hh = np.where(bld, 0, h).astype(np.float32)
    m3 = ndi.uniform_filter(hh, 3)
    q3 = ndi.uniform_filter(hh * hh, 3)
    return np.sqrt(np.maximum(q3 - m3 * m3, 0)).astype(np.float32)


def edge_ring(bld):
    """The 1 m ring around buildings."""
    return ndi.binary_dilation(bld, iterations=EDGE_CELLS) & ~bld


def plant_cue(n_ag, scat):
    """The lidar calls a cell a plant: 3 or more returns above the ground, scattered 0.25 or more."""
    return (np.asarray(n_ag) >= PLANT_RETURNS) & (np.nan_to_num(scat, nan=0.0) >= PLANT_SCATTER)


def to_s2(ndvi, curve):
    """The photo's NDVI on Sentinel-2's scale through its flight day's curve ({"lut_x", "lut_y"}: the same-day
    normalisation's "band 4"). Where the photo has nothing, the curve's value at 0 (exp31)."""
    x, y = np.asarray(curve["lut_x"], float), np.asarray(curve["lut_y"], float)
    out = np.interp(np.nan_to_num(ndvi, nan=0.0), x, y).astype(np.float32)
    return out


def _sizes(mask):
    lab, n = ndi.label(mask, structure=EIGHT)
    if not n:
        return lab, np.zeros(1, np.int64)
    return lab, np.bincount(lab.ravel(), minlength=n + 1)


def keep_patches(mask, min_cells):
    """The 8-connected patches of mask with at least min_cells cells."""
    lab, sizes = _sizes(mask)
    big = sizes >= min_cells
    big[0] = False
    return big[lab]


def thin_runs(cand):
    """Walls and fences: 8-connected runs of cand that are long, about one cell wide and straight (exp26)."""
    out = np.zeros(cand.shape, bool)
    lab = cc_label(cand, connectivity=2)
    if not lab.max():
        return out
    sizes = np.bincount(lab.ravel())
    for rp in regionprops(lab):
        if sizes[rp.label] < THIN_MIN_AREA:
            continue
        if rp.axis_major_length < THIN_MIN_LENGTH:
            continue
        y0, x0, y1, x1 = rp.bbox
        m = lab[y0:y1, x0:x1] == rp.label
        sk = int(skeletonize(m).sum())
        if (rp.area / max(sk, 1) <= THIN_AREA_PER_SKELETON and rp.axis_minor_length <= THIN_MAX_WIDTH
                and rp.axis_major_length >= THIN_STRAIGHT * sk):
            out[y0:y1, x0:x1] |= m
    return out


def scheme(f, green, browned=None):
    """The classes from a green mask (exp26 variant B, then exp28b's surfaced split), as exp31 builds them.

    f: {h, bld, bad, edge, rough, plant, kept, treecue, field, p, dark}; green: the cells green as of July; browned:
    the cells the July rule dried (tall dry grass whatever the lidar says; never walls or roof slivers)."""
    h, bld, bad = f["h"], f["bld"], f["bad"]
    lo, hi = BAND_M
    band = (h >= lo) & (h < hi) & ~bld & ~bad
    flat = (h < lo) & ~bld & ~bad
    if browned is None:
        browned = np.zeros(h.shape, bool)
    never = ~green & ~browned                       # not green in the photo nor in July
    cls = np.full(h.shape, _FLAT_NOT_GREEN, np.uint8)
    cls[flat & green] = SHORT_GREEN
    rest = band & ~f["kept"] & ~f["treecue"] & ~f["field"]
    shrub = f["kept"].copy()
    even = band & (f["rough"] < SHEET_CUT) & (h < SHEET_MAX_H)
    sheet = keep_patches(even, SHEET_MIN_CELLS) & ~f["field"]
    rest |= sheet & shrub
    shrub &= ~sheet
    thin = thin_runs(rest & never)
    cls[rest & green] = TALL_GREEN
    cls[rest & ~green & (f["plant"] | browned)] = TALL_DRY
    cls[rest & ~green & ~f["plant"] & ~browned] = HARD
    cls[thin] = WALL
    cls[f["edge"] & band & never & ~shrub] = ROOF          # roof slivers in the building's ring
    cls[f["field"] & ~bld & ~bad & (h < hi)] = CROP
    cls[shrub] = SHRUB
    cls[((h >= hi) & ~bld & ~bad) | (band & f["treecue"])] = TREE
    cls[bld] = ROOF
    cls[bad] = NODATA
    # exp28b: flat, not-green ground
    bare = flat & ~green & (ndi.median_filter(f["p"], BARE_MEDIAN_CELLS) < BARE_CUT)
    bare = keep_patches(bare, BARE_MIN_CELLS)
    dark = bare & f["dark"]
    ng = cls == _FLAT_NOT_GREEN
    cls[ng] = SHORT_DRY
    cls[ng & bare & ~dark] = PALE
    cls[ng & bare & dark] = DARK
    return cls


def tree_mask(f):
    lo, hi = BAND_M
    band = (f["h"] >= lo) & (f["h"] < hi) & ~f["bld"] & ~f["bad"]
    return ((f["h"] >= hi) & ~f["bld"] & ~f["bad"]) | (band & f["treecue"])


def _cellsum(cell, m, w=None, n=None):
    return np.bincount(cell[m], weights=None if w is None else w[m], minlength=n).astype(np.float64)


def cell_stats(f, cell, july, T):
    """Per 10 m cell (exp31): the counts, the tree share t, the photo's green share x_P of the non-tree cells, July's
    unmixed green share x_J, whether it's valid, and the literal rule's never / always. july: {med, max, min, n} per
    0.5 m cell (its 10 m cell's), T the box's July tree level."""
    n = int(cell.max()) + 1
    ok = ~f["bad"]
    tree = tree_mask(f)
    P = ok & (f["p"] >= GREEN_CUT)
    nt = ok & ~tree
    n_ok = _cellsum(cell, ok, n=n)
    n_tr = _cellsum(cell, ok & tree, n=n)
    n_nt = _cellsum(cell, nt, n=n)
    g = _cellsum(cell, nt & P, n=n)
    sV = _cellsum(cell, nt & P, f["p"], n)
    sN = _cellsum(cell, nt & ~P, f["p"], n)
    V = np.clip(np.where(g >= LEVEL_MIN_CELLS, sV / np.maximum(g, 1), V_DEFAULT), *V_RANGE)
    N = np.clip(np.where(n_nt - g >= LEVEL_MIN_CELLS, sN / np.maximum(n_nt - g, 1), N_DEFAULT), *N_RANGE)
    fin = np.isfinite(july["med"]) & np.isfinite(july["max"]) & np.isfinite(july["min"])
    nf = _cellsum(cell, fin, n=n)
    Jc, Jx, Jl = (_cellsum(cell, fin, np.nan_to_num(july[k]), n) / np.maximum(nf, 1) for k in ("med", "max", "min"))
    for a in (Jc, Jx, Jl):
        a[nf == 0] = np.nan
    views = np.full(n, 255.0)
    np.minimum.at(views, cell.ravel(), np.asarray(july["n"], float).ravel())
    t = n_tr / np.maximum(n_ok, 1)
    xP = g / np.maximum(n_nt, 1)

    def un(v):
        with np.errstate(invalid="ignore"):
            return (v - t * T - (1 - t) * N) / np.maximum((1 - t) * (V - N), 1e-6)
    with np.errstate(invalid="ignore"):
        xJ = np.clip(un(Jc), 0, 1)
        never = (un(Jx) <= 0) & (Jx <= DRY_MAX) & np.isfinite(Jx)
        always = (un(Jl) >= 1) & (Jl >= WET_MIN) & np.isfinite(Jl)
    valid = (n_ok >= MIN_PIX) & (n_nt >= MIN_NONTREE) & (t < MAX_TREE) & (views >= MIN_VIEWS) & np.isfinite(Jc)
    return {"n": n, "n_ok": n_ok, "n_nt": n_nt, "t": t, "xP": xP, "xJ": np.nan_to_num(xJ), "Jc": Jc,
            "valid": valid, "never": never, "always": always, "P": P, "tree": tree}


def tree_level(f, cell, july):
    """The box's July tree level: the median July NDVI of its 10 m cells that are 80% tree or more, when it has 20
    of them; otherwise the ten boxes' pooled level (exp31)."""
    cs = cell_stats(f, cell, july, TREE_LEVEL_POOLED)
    m = (cs["n_ok"] >= MIN_PIX) & (cs["t"] >= TREE_CELL_SHARE) & np.isfinite(cs["Jc"])
    if int(m.sum()) >= TREE_LEVEL_MIN_CELLS:
        return float(np.median(cs["Jc"][m])), int(m.sum())
    return TREE_LEVEL_POOLED, int(m.sum())


def ranked(cand, cell, key, n_per_cell):
    """In each 10 m cell, the first n_per_cell[cell] of the cand cells by key (ascending)."""
    idx = np.flatnonzero(cand.ravel())
    out = np.zeros(cand.size, bool)
    if not len(idx):
        return out.reshape(cand.shape)
    cc = cell.ravel()[idx]
    kv = key.ravel()[idx]
    o = np.lexsort((kv, cc))
    idx, cc = idx[o], cc[o]
    rank = np.arange(len(idx)) - np.searchsorted(cc, cc, side="left")
    out[idx[rank < n_per_cell[cc]]] = True
    return out.reshape(cand.shape)


def july_rule(f, cell, july, on_road, T=None):
    """The July rule (exp31): (green as of July, browned, greened, stats). on_road: cells of mapped roads (never
    greened)."""
    if T is None:
        T, _ = tree_level(f, cell, july)
    cs = cell_stats(f, cell, july, T)
    h, bld, bad = f["h"], f["bld"], f["bad"]
    lo, hi = BAND_M
    band = (h >= lo) & (h < hi) & ~bld & ~bad
    flat = (h < lo) & ~bld & ~bad
    low = ~bad & ~cs["tree"] & ~bld & (h < hi)
    P, valid = cs["P"], cs["valid"]
    nb = np.where(valid & (cs["xP"] - cs["xJ"] > MARGIN), np.round((cs["xP"] - cs["xJ"]) * cs["n_nt"]), 0)
    ngr = np.where(valid & (cs["xJ"] - cs["xP"] > MARGIN), np.round((cs["xJ"] - cs["xP"]) * cs["n_nt"]), 0)
    nb, ngr = nb.astype(np.int64), ngr.astype(np.int64)
    by_margin = int((nb > 0).sum()), int((ngr > 0).sum())
    nb[valid & cs["never"]] = 10 ** 6
    ngr[valid & cs["always"] & ~cs["never"]] = 10 ** 6
    browned = ranked(P & low, cell, f["p"], nb)
    gcand = ~P & low & ~on_road & ~(flat & f["dark"]) & ~(f["edge"] & band)
    greened = ranked(gcand, cell, -f["p"], ngr)
    green = (P & ~browned) | greened
    stats = {"tree_level": round(float(T), 3), "cells_10m": int(cs["n"]), "cells_used": int(valid.sum()),
             "cells_drying_by_margin": by_margin[0], "cells_greening_by_margin": by_margin[1],
             "cells_dry_all_july": int((valid & cs["never"]).sum()),
             "cells_green_all_july": int((valid & cs["always"] & ~cs["never"]).sum()),
             "photo_green_low_cells": int((P & low).sum()), "browned": int(browned.sum()),
             "greened": int(greened.sum())}
    return green, browned, greened, stats


def tracks(cls, track_line, lum):
    """Mapped tracks (G1a, box f): short dry grass within TRACK_HALF_M of a mapped track's line becomes pale surfaced
    ground where the photo's brightness (lum, a 2.5 m median) is TRACK_GAIN above the level of the ground beside the
    track: the mean brightness of the short dry grass and pale surfaced cells TRACK_RING_M from the line, within
    TRACK_LEVEL_CELLS around each cell. track_line: the tracks' centrelines burned into the grid (every cell a line
    touches). Returns (classes, cells changed)."""
    if not track_line.any():
        return cls, 0
    d = ndi.distance_transform_edt(~track_line, sampling=PX)
    tread = (d <= TRACK_HALF_M) & (cls == SHORT_DRY)
    if not tread.any():
        return cls, 0
    ring = (d >= TRACK_RING_M[0]) & (d <= TRACK_RING_M[1]) & np.isin(cls, (SHORT_DRY, PALE))
    lm = ndi.median_filter(np.nan_to_num(lum, nan=0.0).astype(np.float32), BARE_MEDIAN_CELLS)
    n = TRACK_LEVEL_CELLS
    num = ndi.uniform_filter(np.where(ring, lm, 0).astype(np.float32), n)
    den = ndi.uniform_filter(ring.astype(np.float32), n)
    enough = den * n * n >= TRACK_MIN_RING_CELLS
    with np.errstate(invalid="ignore", divide="ignore"):
        level = np.where(enough, num / np.maximum(den, 1e-9), np.nan)
        bright = tread & enough & (lm >= level * (1 + TRACK_GAIN))
    out = cls.copy()
    out[bright] = PALE
    return out, int(bright.sum())


def floor(cls):
    """The floor (exp27): under trees, shrubs, hard things and walls, the nearest ground cell's class; under closed
    canopy (trees on CANOPY_SHARE of the 30 m around), forest floor. Roofs and no data stay."""
    ground = np.isin(cls, GROUND)
    out = cls.copy()
    if not ground.any():
        return out
    cover = np.isin(cls, COVER)
    _, (iy, ix) = ndi.distance_transform_edt(~ground, return_indices=True)
    out[cover] = cls[iy[cover], ix[cover]]
    canopy = ndi.uniform_filter((cls == TREE).astype(np.float32), CANOPY_WINDOW_CELLS)
    out[(cls == TREE) & (canopy >= CANOPY_SHARE)] = FOREST_FLOOR
    return out


def shares(cls, land=None):
    """{class name: % of land} (land: default every cell with data)."""
    land = cls != NODATA if land is None else land
    n = max(int(land.sum()), 1)
    counts = np.bincount(cls[land].ravel(), minlength=len(CLASSES))
    return {CLASSES[k]: round(100.0 * int(v) / n, 2) for k, v in enumerate(counts) if v and k in CLASSES}


def classify(f, cell, july, on_road, track_line, lum):
    """Every step for one box: the July rule, the scheme, mapped tracks, the floor. Returns (class, floor, stats)."""
    green, browned, _greened, st = july_rule(f, cell, july, on_road)
    cls = scheme(f, green, browned)
    cls, n_track = tracks(cls, track_line, lum)
    st["track_cells"] = n_track
    fl = floor(cls)
    st["shares"] = shares(cls)
    st["floor_shares"] = shares(fl)
    return cls, fl, st
