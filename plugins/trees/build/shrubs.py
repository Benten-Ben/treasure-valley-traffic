"""Shrubs from the lidar (docs/19 §19.8): which 0.5 m cells are shrub, and how they become shrubs. The owner's rule
(Oct 8): one combination of settings everywhere, no classification by place. Pure NumPy and SciPy, no I/O: the build
(build_shrubs.py) reads the rasters, the photo and the point cloud's cues, and hands them here as 2-D arrays on the
lidar's 0.5 m grid (row 0 at the north):

    h      heights above the bare earth (surface minus ground; 0 where there is no lidar)
    bld    the building mask
    bad    cells with no lidar
    ndvi   the summer photo's NDVI, moved onto the grid (NaN where the photo has nothing)
    n_ag   returns above the ground in the cell (at least GROUND_H over the bare earth)
    scat   their mean scatter (PDAL's covariance features over 20 neighbours; NaN where n_ag is 0)

1. Shrub cells (shrub_cells). A cell 0.3-2.4 m tall that isn't a building is a shrub when the photo's near-infrared
   calls it green (the area's own NDVI cut, ndvi_cut) or the lidar calls it a plant (3 or more returns above the
   ground, with a scatter of 0.25 or more). In the 1 m ring around buildings only green cells count: the rest there
   are roof slivers. The best of 132 settings on three checks at once (RCMAP's shrub cover, shrubs on building edges,
   green cells kept), Oct 8.
2. Clumps into pieces (pieces): the shrub heights' peaks, tallest first, each dropped when it stands closer to a kept
   one than half the two shrubs' model widths (the owner's spacing rule for trees); a watershed from the kept peaks
   splits each clump into pieces.
3. Crops (crop_pieces). The landscape's crop class comes from farm's fields (decision 15, Oct 8). A piece with at
   least half its cells inside a crop field is a crop, not shrubs; so is a piece mostly within 10 m of one (the crop
   cover's own cells) when its clump is mostly crop: the field's fringe that the 10 m cells leave out. Pieces rather
   than whole clumps, so the cut follows the field's edge: a small field touching shrubland goes, and a hedgerow or a
   ditch bank's shrubs touching a field keep all but their first 10 m. The spike's own crop-field rule (field_rule:
   even, all-green, low 25 m blocks) stays as a check on those fields; it no longer removes anything.
4. Pieces into shrubs (split): a piece much bigger than a model shrub of its height is split again (k-means) into
   model-sized shrubs. Each shrub: the piece's top as its height, its equal-area width held within twice the
   model's spread, its centre, and its look, bush (mostly green: yard plantings, hedges, riparian thickets) or sage
   (not green: sagebrush, bitterbrush, rabbitbrush). A hedge becomes a row of bushes.
5. Cleaning, before a piece becomes shrubs (the first images' four false kinds, three here and crops above): a
   speck (one cell, or two under 0.6 m: lidar striping in grass); a crown's skirt (a cell 2.4 m or taller within 1 m
   of the piece's top stands higher than it); a gap in a crown (its surrounding ring is mostly tree).
6. Score: the shrubs' domes rebuild the shrub surface, compared with the lidar on the kept cells.

The rule and its numbers come from the land-cover spike's exp23 (the settings search), exp25c (crops) and exp25d (the
cleaning), on the ten test areas' central 500 m."""
import math
import warnings

import numpy as np
from scipy import ndimage as ndi
from scipy.cluster.vq import kmeans2

PX = 0.5                         # metres per cell
BAND_M = (0.3, 2.4)              # a shrub's height; from 2.4 m a plant is a tree (§19.3)
GROUND_H = 0.15                  # a return this far above the bare earth is above the ground
NDVI_FALLBACK = 0.15             # the green cut when an area has too few shrub-height cells to set its own
MIN_CELLS_FOR_MEDIAN = 200       # canopy or roof cells needed for their NDVI median to bound the cut
PLANT_RETURNS = 3                # the lidar calls a cell a plant: this many returns above the ground ...
PLANT_SCATTER = 0.25             # ... scattered at least this much (PDAL's Scattering, 20 neighbours)
EDGE_CELLS = 2                   # the ring around buildings where only green cells count (1 m)
ROOF_MIN_M = 2.0                 # roofs for the NDVI cut's lower bound
# cleaning
SPECK_TWO_CELLS_UNDER_M = 0.6
SKIRT_REACH_CELLS = 2            # within 1 m of the piece's top
SKIRT_ABOVE_M = 0.2
GAP_RING_TREE_SHARE = 0.6
# splitting
GREEN_LOCAL_CELLS = 5            # a peak's model width is bush's where its 2.5 m square is mostly green
SPACING = 0.5                    # a lower peak closer than this share of the two model widths is dropped
SPLIT_AREA_SLACK = 1.3           # a piece is split into round(cells / (1.3 x a model shrub's cells)) shrubs
WIDTH_CLAMP_SD = 2.0
BUSH_GREEN_SHARE = 0.5
# crops (decision 15) and the spike's crop-field rule, now a check
CROP_PIECE_SHARE = 0.5           # a piece with this share of its cells in a crop field is a crop
CROP_REACH_M = 10.0              # ... or that share within this of one, in a clump with that share in crops
FIELD_BLOCK_CELLS = 50           # 25 m blocks
FIELD_MIN_BAND_CELLS = 50
FIELD_BAND_SHARE = 0.15
FIELD_GREEN_SHARE = 0.9
FIELD_SPREAD_M = 0.35            # interquartile range of the band's heights
FIELD_TALLEST_M = 1.5            # nothing but roofs stands taller
FIELD_REACH_CELLS = 60           # green, low ground joins a field up to 30 m out

# Why a cell isn't (or is) a shrub, as the build's why.tif writes it.
WHY = {"none": 0, "shrub": 1, "speck": 2, "skirt": 3, "gap": 4, "crop": 5}
EIGHT = np.ones((3, 3), bool)


class ShrubModel:
    """Width for height per look (model/shrub_model.json): width_m = a * H^b, spread sd_log in log width."""

    def __init__(self, spec):
        self.spec = spec
        self.width = {look: (float(v["a"]), float(v["b"]), float(v["sd_log"])) for look, v in spec["width"].items()}
        self.dome = (float(spec["dome"]["a"]), float(spec["dome"]["n"]))

    def width_m(self, H, look):
        a, b, _ = self.width[look]
        return a * np.maximum(H, BAND_M[0]) ** b

    def sd(self, look):
        return self.width[look][2]


def otsu(v, bins=128):
    """Otsu's split of the values v (the threshold between two classes that maximises the between-class variance)."""
    hist, edges = np.histogram(v, bins=bins)
    c = (edges[:-1] + edges[1:]) / 2
    w = hist.astype(float)
    best, t = -1.0, float(c[len(c) // 2])
    for k in range(1, len(c)):
        w0, w1 = w[:k].sum(), w[k:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0, m1 = (w[:k] * c[:k]).sum() / w0, (w[k:] * c[k:]).sum() / w1
        b = w0 * w1 * (m0 - m1) ** 2
        if b > best:
            best, t = b, float(c[k])
    return t


def ndvi_cut(ndvi, h, bld, bad):
    """The area's own green cut: Otsu's split of the shrub-height cells' NDVI, kept between the roofs' and the tree
    canopy's medians where both have enough cells (spike exp16, Oct 8). Returns (cut, detail)."""
    ok = ~bad & np.isfinite(ndvi)
    lo, hi = BAND_M
    v_s = ndvi[(h >= lo) & (h < hi) & ~bld & ok]
    v_c = ndvi[(h >= hi) & ~bld & ok]
    v_r = ndvi[bld & ok & (h >= ROOF_MIN_M)]
    med = lambda v: round(float(np.median(v)), 3) if v.size > MIN_CELLS_FOR_MEDIAN else None  # noqa: E731
    detail = {"shrub_height_cells": int(v_s.size), "median_canopy": med(v_c), "median_roofs": med(v_r)}
    if v_s.size <= MIN_CELLS_FOR_MEDIAN:
        detail["from"] = "too few shrub-height cells: the fallback"
        return NDVI_FALLBACK, detail
    t = otsu(v_s)
    detail["otsu"] = round(t, 3)
    if detail["median_canopy"] is not None and detail["median_roofs"] is not None:
        t = min(max(t, detail["median_roofs"]), detail["median_canopy"])
    detail["from"] = "Otsu on the shrub-height cells, between the roofs' and the canopy's medians"
    return float(t), detail


def edge_ring(bld):
    """The 1 m ring around buildings."""
    return ndi.binary_dilation(bld, iterations=EDGE_CELLS) & ~bld


def shrub_cells(h, bld, bad, alive, n_ag, scat):
    """The rule (step 1): (shrub cells, the band's cells). alive: green by the area's NDVI cut."""
    lo, hi = BAND_M
    band = (h >= lo) & (h < hi) & ~bld & ~bad
    plant = (n_ag >= PLANT_RETURNS) & (np.nan_to_num(scat, nan=0.0) >= PLANT_SCATTER)
    shrub = band & (alive | plant)
    shrub &= ~(edge_ring(bld) & ~alive)
    return shrub, band


def crop_pieces(seg, crop):
    """Which pieces (labels of seg, 0 outside; a piece never spans two clumps) are crops: at least CROP_PIECE_SHARE of
    their cells in a crop field; or, in a clump (8-connected) with at least that share of its cells in crop fields, at
    least that share within CROP_REACH_M of one. Farm's crop cover has 10 m cells and keeps a field's edge cells only
    where the CDL agrees, so a field's outer rows can fall just outside it (most of NY Canal's within 5 m, Oct 11); the
    reach takes them with their field, and only there. A bool array indexed by label (label 0 never)."""
    n = int(seg.max())
    out = np.zeros(n + 1, bool)
    if crop is None or n == 0 or not (crop & (seg > 0)).any():
        return out
    m = seg > 0
    lab = seg.ravel()
    size = np.bincount(lab, minlength=n + 1)
    inside = np.bincount(lab, weights=(crop & m).ravel(), minlength=n + 1)
    out = inside >= CROP_PIECE_SHARE * size
    clump, nclump = ndi.label(m, structure=EIGHT)
    csize = np.bincount(clump.ravel(), minlength=nclump + 1)
    cinside = np.bincount(clump.ravel(), weights=(crop & m).ravel(), minlength=nclump + 1)
    crop_clump = (cinside >= CROP_PIECE_SHARE * csize) & (cinside > 0)
    crop_clump[0] = False
    clump_of = np.zeros(n + 1, np.int64)
    clump_of[seg[m]] = clump[m]
    if crop_clump.any():
        near = ndi.distance_transform_edt(~crop) * PX <= CROP_REACH_M
        within = np.bincount(lab, weights=(near & m).ravel(), minlength=n + 1)
        out |= crop_clump[clump_of] & (within >= CROP_PIECE_SHARE * size)
    out &= size > 0
    out[0] = False
    return out


def field_rule(h, bld, alive):
    """The spike's crop-field rule (exp25c), now a check on farm's fields (decision 15): a 25 m block is a field when at
    least 15% of its cells are in the shrub band, at least 90% of those are green, their heights are even (interquartile
    range under 0.35 m) and nothing but roofs stands over 1.5 m. A block next to a field that is just as green and low
    joins it, and so does green, low ground connected to it up to 30 m out. Returns (field cells, blocks before the
    join, blocks after it). Blocks start at the grid's north-west corner; a part block at the south or east edge isn't
    tested."""
    B = FIELD_BLOCK_CELLS
    lo, hi = BAND_M
    rows, cols = h.shape
    nbr, nbc = rows // B, cols // B
    band = (h >= lo) & (h < hi) & ~bld
    treeh = np.where(bld, 0, h)
    fld = np.zeros((nbr, nbc), bool)
    low = np.zeros((nbr, nbc), bool)
    for i in range(nbr):
        for j in range(nbc):
            sl = (slice(i * B, (i + 1) * B), slice(j * B, (j + 1) * B))
            bm = band[sl]
            nb = int(bm.sum())
            green = float(alive[sl][bm].mean()) if nb >= FIELD_MIN_BAND_CELLS else 0.0
            tallest = float(treeh[sl].max())
            low[i, j] = tallest <= FIELD_TALLEST_M and green >= FIELD_GREEN_SHARE
            if nb / bm.size >= FIELD_BAND_SHARE and green >= FIELD_GREEN_SHARE and tallest <= FIELD_TALLEST_M:
                hb = h[sl][bm]
                fld[i, j] = (np.percentile(hb, 75) - np.percentile(hb, 25)) <= FIELD_SPREAD_M
    first = int(fld.sum())
    fld |= ndi.binary_dilation(fld, structure=EIGHT) & low
    field = np.zeros(h.shape, bool)
    field[:nbr * B, :nbc * B] = np.kron(fld, np.ones((B, B), bool)).astype(bool)
    if fld.any():
        gl = alive & (treeh < FIELD_TALLEST_M) & ~bld
        lab_g, _ = ndi.label(gl, structure=EIGHT)
        touch = np.unique(lab_g[field & gl])
        touch = touch[touch > 0]
        near = ndi.binary_dilation(field, iterations=FIELD_REACH_CELLS)
        field |= np.isin(lab_g, touch) & near
    return field, first, int(fld.sum())


def keep_spaced(ys, xs, R):
    """Peaks (tallest first) kept by the spacing rule: none closer to a kept one than SPACING x (R_i + R_j), in cells."""
    keep = np.zeros(len(ys), bool)
    grid = {}
    G = 16
    reach = max(1, int(math.ceil(SPACING * 2 * float(R.max()) / G))) if len(R) else 1
    for i in range(len(ys)):
        y, x, r = int(ys[i]), int(xs[i]), float(R[i])
        ok = True
        for gy in range(y // G - reach, y // G + reach + 1):
            for gx in range(x // G - reach, x // G + reach + 1):
                for j in grid.get((gy, gx), ()):
                    if (ys[j] - y) ** 2 + (xs[j] - x) ** 2 < (SPACING * (R[j] + r)) ** 2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            keep[i] = True
            grid.setdefault((y // G, x // G), []).append(i)
    return keep


def pieces(h, m, alive, model):
    """Watershed pieces of the shrub cells m: an int32 label array (0 outside m). Peaks of the shrub heights, tallest
    first, spaced by keep_spaced. The watershed floods the whole grid, so a piece is cut where it leaves its clump: a
    piece never spans two clumps."""
    hm = np.where(m, h, 0).astype(np.float32)
    pk = m & (hm == ndi.maximum_filter(hm, size=3))
    ys, xs = np.nonzero(pk)
    order = np.argsort(-hm[ys, xs], kind="stable")
    ys, xs = ys[order], xs[order]
    loc_green = ndi.uniform_filter(alive.astype(np.float32), GREEN_LOCAL_CELLS) >= 0.5
    hp = hm[ys, xs]
    R = np.where(loc_green[ys, xs], model.width_m(hp, "bush"), model.width_m(hp, "sage")) / 2 / PX
    keep = keep_spaced(ys, xs, R)
    markers = np.zeros(h.shape, np.int32)
    kk = np.nonzero(keep)[0]
    markers[ys[kk], xs[kk]] = np.arange(1, len(kk) + 1, dtype=np.int32)
    surface = np.clip(255 - hm / BAND_M[1] * 255, 0, 255).astype(np.uint8)
    seg = ndi.watershed_ift(surface, markers) if len(kk) else np.zeros(h.shape, np.int32)
    seg = np.where(m, seg, 0)
    clump, nclump = ndi.label(m, structure=EIGHT)
    key = seg.astype(np.int64) * (nclump + 1) + clump
    key[~m] = 0
    uniq, inv = np.unique(key, return_inverse=True)
    out = inv.reshape(h.shape).astype(np.int32)
    if uniq[0] != 0:                      # m covers every cell
        out += 1
    out[~m] = 0
    return out


def _kmeans(pts, k, seed):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            _, lab = kmeans2(pts, k, minit="++", seed=seed)
        except TypeError:                 # SciPy versions that only take rng
            _, lab = kmeans2(pts, k, minit="++", rng=seed)
    return lab


def split(h, m, alive, treeh, model, crop=None):
    """Steps 2 to 5: the shrub cells m into shrubs. treeh: heights with buildings at 0 (only plants make a skirt or a
    gap). crop: crop fields (bool, or None for none): a piece mostly in them is a crop. Returns (shrubs, why, dropped):
    shrubs a list of dicts (row and col of the centre in cells, from the grid's north-west corner; height_m, width_m,
    look, cells, green, split, model_width_m); why a uint8 array (WHY codes for the cells of m); dropped the pieces
    dropped as crops and by each cleaning rule."""
    lo, hi = BAND_M
    why = np.zeros(h.shape, np.uint8)
    dropped = {"crop": 0, "speck": 0, "skirt": 0, "gap": 0}
    shrubs = []
    if not m.any():
        return shrubs, why, dropped
    seg = pieces(h, m, alive, model)
    is_crop = crop_pieces(seg, crop)
    if is_crop.any():
        why[is_crop[seg]] = WHY["crop"]
        dropped["crop"] = int(is_crop.sum())
    objs = ndi.find_objects(seg)
    rows, cols = h.shape
    for sid, sl in enumerate(objs, start=1):
        if sl is None or is_crop[sid]:
            continue
        yy, xx = np.nonzero(seg[sl] == sid)
        yy = yy + sl[0].start
        xx = xx + sl[1].start
        hh = h[yy, xx]
        top = int(np.argmax(hh))
        Hs = float(hh[top])
        n = len(yy)
        if n == 1 or (n == 2 and Hs < SPECK_TWO_CELLS_UNDER_M):
            dropped["speck"] += 1
            why[yy, xx] = WHY["speck"]
            continue
        ty, tx = int(yy[top]), int(xx[top])
        r = SKIRT_REACH_CELLS
        w0, w1, v0, v1 = max(0, ty - r), min(rows, ty + r + 1), max(0, tx - r), min(cols, tx + r + 1)
        win = treeh[w0:w1, v0:v1]
        own = seg[w0:w1, v0:v1] == sid
        if ((win >= hi) & (win > Hs + SKIRT_ABOVE_M) & ~own).any():
            dropped["skirt"] += 1
            why[yy, xx] = WHY["skirt"]
            continue
        b0, b1 = max(0, sl[0].start - 1), min(rows, sl[0].stop + 1)
        c0, c1 = max(0, sl[1].start - 1), min(cols, sl[1].stop + 1)
        me = seg[b0:b1, c0:c1] == sid
        ring = ndi.binary_dilation(me, structure=EIGHT) & ~me
        if ring.any() and float((treeh[b0:b1, c0:c1][ring] >= hi).mean()) >= GAP_RING_TREE_SHARE:
            dropped["gap"] += 1
            why[yy, xx] = WHY["gap"]
            continue
        why[yy, xx] = WHY["shrub"]
        green_cells = alive[yy, xx]
        look = "bush" if float(green_cells.mean()) >= BUSH_GREEN_SHARE else "sage"
        Rm = float(model.width_m(Hs, look)) / 2 / PX
        k = max(1, int(round(n / (math.pi * Rm * Rm * SPLIT_AREA_SLACK))))
        if k > 1 and n >= 2 * k:
            lab = _kmeans(np.vstack([yy, xx]).T.astype(float), k, sid)
            parts = [np.nonzero(lab == q)[0] for q in range(k)]
        else:
            k = 1
            parts = [np.arange(n)]
        sd = model.sd(look)
        for p in parts:
            if len(p) == 0:
                continue
            Hp = float(hh[p].max())
            if Hp < lo:
                continue
            W0 = float(model.width_m(Hp, look))
            Wp = float(np.clip(2 * math.sqrt(len(p) * PX * PX / math.pi),
                               W0 * math.exp(-WIDTH_CLAMP_SD * sd), W0 * math.exp(WIDTH_CLAMP_SD * sd)))
            shrubs.append({"row": float(yy[p].mean()), "col": float(xx[p].mean()), "height_m": Hp, "width_m": Wp,
                           "look": look, "cells": int(len(p)), "green": round(float(green_cells[p].mean()), 2),
                           "split": k, "model_width_m": round(W0, 2)})
    return shrubs, why, dropped


def dome_surface(shape, shrubs, model):
    """The shrubs' upper envelope: each a dome z = H * (1 - a * (d/R)^n) inside its width."""
    A, N = model.dome
    E = np.zeros(shape, np.float32)
    rows, cols = shape
    for s in shrubs:
        y, x, H, r = s["row"], s["col"], s["height_m"], max(s["width_m"] / 2 / PX, 0.5)
        r0, r1 = int(max(0, y - r - 1)), int(min(rows, y + r + 2))
        c0, c1 = int(max(0, x - r - 1)), int(min(cols, x + r + 2))
        if r0 >= r1 or c0 >= c1:
            continue
        gy, gx = np.mgrid[r0:r1, c0:c1]
        d = np.hypot(gy - y, gx - x) / r
        z = np.where(d <= 1, H * (1 - A * d ** N), 0).astype(np.float32)
        E[r0:r1, c0:c1] = np.maximum(E[r0:r1, c0:c1], z)
    return E


def score(h, kept, shrubs, model):
    """How well the shrubs explain the shrub cells they came from: the share of kept cells under a dome, the share of
    the domes' cells outside the kept cells, and the mean height error on the kept cells."""
    E = dome_surface(h.shape, shrubs, model)
    cov = E > 0
    return {"kept_cells_covered": round(float((cov & kept).sum() / max(1, kept.sum())), 3),
            "drawn_outside_kept": round(float((cov & ~kept).sum() / max(1, cov.sum())), 3),
            "height_error_m": round(float(np.abs(E - h)[kept].mean()), 2) if kept.any() else None}


def summarise(shrubs, area_ha):
    """Counts for build.json."""
    n = len(shrubs)
    hs = np.array([s["height_m"] for s in shrubs]) if n else np.zeros(0)
    ws = np.array([s["width_m"] for s in shrubs]) if n else np.zeros(0)
    bush = sum(1 for s in shrubs if s["look"] == "bush")
    return {"shrubs": n, "bush": bush, "sage": n - bush,
            "per_hectare": round(n / area_ha, 1) if area_ha else None,
            "bush_share": round(bush / n, 2) if n else None,
            "median_height_m": round(float(np.median(hs)), 2) if n else None,
            "median_width_m": round(float(np.median(ws)), 2) if n else None}
