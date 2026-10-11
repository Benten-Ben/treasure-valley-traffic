"""The point cloud's cues for the shrub rule (docs/19 §19.8), per 0.5 m cell of the lidar grid: how many returns stand
above the bare earth (n_ag), and how scattered they are (scat: the mean of PDAL's Scattering over each point's 20
nearest neighbours among the above-ground points; a plant's points scatter in 3-D, a hard thing's lie on surfaces).
Worker image (PDAL, NumPy).

One pass reads the area's points (LAS or LAZ tiles streamed, or an EPT read by parts), drops noise (classes 7 and 18)
and withheld points, keeps those at least GROUND_H above the build's own bare-earth raster (so the heights agree with
the height raster) and spools them to disk per chunk, each chunk with a margin so that neighbours across its edge
count. Then each chunk gets its features and per-cell sums. Memory stays small whatever the area's size, and a
finished chunk is kept: a stopped run picks up where it was (the spool and the chunks are kept until every chunk is
done; then the spool goes).

Grid: the raster's north-west corner (x0, y1), its cell size and shape, in the raster's CRS. Points are read in that
CRS: PDAL reprojects horizontally (filters.reprojection; give a source's own CRS with in_srs when its files say
something else, as the EPT copies in EPSG:3857 did)."""
import json
import math
import os

import numpy as np

GROUND_H = 0.15                     # the shrubs' rule (shrubs.GROUND_H)
NOISE_CLASSES = (7, 18)
KNN = 20
SPOOL_DTYPE = np.dtype([("X", "<f8"), ("Y", "<f8"), ("Z", "<f8")])
EPT_PART_M = 400.0                  # an EPT is read in parts of at most this size


class Grid:
    """A raster grid: north-west corner (x0, y1), cell size px, rows x cols; row 0 at the north."""

    def __init__(self, x0, y1, px, rows, cols):
        self.x0, self.y1, self.px, self.rows, self.cols = float(x0), float(y1), float(px), int(rows), int(cols)

    @property
    def rect(self):
        return (self.x0, self.y1 - self.rows * self.px, self.x0 + self.cols * self.px, self.y1)

    def cells(self, x, y):
        col = np.floor((x - self.x0) / self.px).astype(np.int64)
        row = np.floor((self.y1 - y) / self.px).astype(np.int64)
        return row, col

    def key(self):
        return [self.x0, self.y1, self.px, self.rows, self.cols]


def chunks(grid, size_m):
    """The grid split into chunks of at most size_m a side, on cell edges: [(name, (r0, r1, c0, c1)), ...]."""
    n = max(1, int(round(size_m / grid.px)))
    out = []
    for r0 in range(0, grid.rows, n):
        for c0 in range(0, grid.cols, n):
            out.append((f"{r0}_{c0}", (r0, min(grid.rows, r0 + n), c0, min(grid.cols, c0 + n))))
    return out


def window_rect(grid, win, pad_m=0.0):
    r0, r1, c0, c1 = win
    return (grid.x0 + c0 * grid.px - pad_m, grid.y1 - r1 * grid.px - pad_m,
            grid.x0 + c1 * grid.px + pad_m, grid.y1 - r0 * grid.px + pad_m)


def keep_mask(arr):
    """Points to keep: not noise (classes 7 and 18) and not withheld."""
    names = arr.dtype.names
    keep = ~np.isin(arr["Classification"], NOISE_CLASSES)
    if "Withheld" in names:
        keep &= arr["Withheld"] == 0
    elif "ClassFlags" in names:
        keep &= (arr["ClassFlags"] & 4) == 0
    return keep


def _bounds(rect):
    x0, y0, x1, y1 = rect
    return f"([{x0}, {x1}], [{y0}, {y1}])"


def source_kind(path):
    p = path.lower()
    if p.endswith("ept.json"):
        return "ept"
    if p.endswith((".las", ".laz")):
        return "las"
    raise ValueError(f"{path}: a point source is a .las or .laz file, or an EPT's ept.json")


def _ept_bounds(path, rect, out_crs, in_srs):
    """rect (out_crs) as bounds in the EPT's own CRS, with a margin."""
    from pyproj import CRS, Transformer
    if in_srs:
        src = CRS.from_user_input(in_srs)
    else:
        with open(path) as f:
            srs = json.load(f).get("srs") or {}
        src = CRS.from_wkt(srs["wkt"]) if srs.get("wkt") else CRS.from_epsg(int(srs["horizontal"]))
    tr = Transformer.from_crs(out_crs, src, always_xy=True)
    x0, y0, x1, y1 = rect
    xs = np.r_[np.linspace(x0, x1, 9), np.full(9, x1), np.linspace(x1, x0, 9), np.full(9, x0)]
    ys = np.r_[np.full(9, y0), np.linspace(y0, y1, 9), np.full(9, y1), np.linspace(y1, y0, 9)]
    X, Y = tr.transform(xs, ys)
    m = 2.0
    return (float(np.min(X)) - m, float(np.min(Y)) - m, float(np.max(X)) + m, float(np.max(Y)) + m)


def read(sources, rect, out_crs, in_srs=None, batch=1_000_000):
    """Yield arrays of the points inside rect (out_crs), reprojected to out_crs, from LAS/LAZ files (streamed) or EPTs
    (read in parts of EPT_PART_M, each point once)."""
    import pdal
    reproject = {"type": "filters.reprojection", "out_srs": str(out_crs)}
    if in_srs:
        reproject["in_srs"] = in_srs
    for path in sources:
        if source_kind(path) == "las":
            stages = [{"type": "readers.las", "filename": path}, reproject,
                      {"type": "filters.crop", "bounds": _bounds(rect)}]
            for arr in pdal.Pipeline(json.dumps(stages)).iterator(chunk_size=batch):
                if len(arr):
                    yield arr
            continue
        x0, y0, x1, y1 = rect
        nx, ny = max(1, math.ceil((x1 - x0) / EPT_PART_M)), max(1, math.ceil((y1 - y0) / EPT_PART_M))
        xs, ys = np.linspace(x0, x1, nx + 1), np.linspace(y0, y1, ny + 1)
        for i in range(nx):
            for j in range(ny):
                part = (xs[i], ys[j], xs[i + 1], ys[j + 1])
                stages = [{"type": "readers.ept", "filename": path,
                           "bounds": _bounds(_ept_bounds(path, part, out_crs, in_srs))},
                          reproject, {"type": "filters.crop", "bounds": _bounds(part)}]
                p = pdal.Pipeline(json.dumps(stages))
                p.execute()
                for arr in p.arrays:
                    if not len(arr):
                        continue
                    # half-open parts, so a point on a shared edge is read once (the outer edges stay closed)
                    X, Y = arr["X"], arr["Y"]
                    ok = ((X >= part[0]) & ((X < part[2]) | (i == nx - 1)) &
                          (Y >= part[1]) & ((Y < part[3]) | (j == ny - 1)))
                    if ok.any():
                        yield arr[ok]


class Spool:
    """Above-ground points per chunk (with its margin), appended to one binary file per chunk."""

    def __init__(self, folder, grid, wins, pad_m):
        self.folder, self.grid, self.pad = folder, grid, pad_m
        self.names = [n for n, _ in wins]
        self.rects = np.array([window_rect(grid, w, pad_m) for _, w in wins])
        os.makedirs(folder, exist_ok=True)

    def path(self, name):
        return os.path.join(self.folder, name + ".bin")

    def add(self, X, Y, Z):
        if not len(X):
            return
        pts = np.empty(len(X), SPOOL_DTYPE)
        pts["X"], pts["Y"], pts["Z"] = X, Y, Z
        for k, name in enumerate(self.names):
            x0, y0, x1, y1 = self.rects[k]
            ok = (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
            if ok.any():
                with open(self.path(name), "ab") as f:
                    f.write(pts[ok].tobytes())

    def load(self, name):
        p = self.path(name)
        if not os.path.exists(p):
            return np.zeros(0, SPOOL_DTYPE)
        return np.fromfile(p, SPOOL_DTYPE)


def above_ground(arr, grid, dtm, dtm_ok):
    """(X, Y, Z) of the kept points at least GROUND_H above the bare earth, and counts."""
    keep = keep_mask(arr)
    X, Y, Z = arr["X"][keep], arr["Y"][keep], arr["Z"][keep]
    row, col = grid.cells(X, Y)
    inside = (row >= 0) & (row < grid.rows) & (col >= 0) & (col < grid.cols)
    X, Y, Z, row, col = X[inside], Y[inside], Z[inside], row[inside], col[inside]
    ok = dtm_ok[row, col]
    X, Y, Z, row, col = X[ok], Y[ok], Z[ok], row[ok], col[ok]
    ag = (Z - dtm[row, col]) >= GROUND_H
    return X[ag], Y[ag], Z[ag], {"read": int(len(arr)), "kept": int(keep.sum()), "above_ground": int(ag.sum())}


def scattering(pts, knn=KNN, threads=1):
    """PDAL's Scattering per point (filters.covariancefeatures, Dimensionality, knn neighbours). NaN for every point
    when there are too few points for the neighbourhood."""
    import pdal
    if len(pts) <= knn:
        return np.full(len(pts), np.nan)
    p = pdal.Pipeline(json.dumps([{"type": "filters.covariancefeatures", "knn": knn, "threads": threads,
                                   "feature_set": "Dimensionality"}]), arrays=[pts])
    p.execute()
    return np.asarray(p.arrays[0]["Scattering"], np.float64)


def chunk_cues(pts, grid, win, knn=KNN, threads=1):
    """n_ag and scat for the cells of win (r0, r1, c0, c1) from that chunk's spooled points (its margin included)."""
    r0, r1, c0, c1 = win
    shape = (r1 - r0, c1 - c0)
    n_ag = np.zeros(shape, np.uint16)
    scat = np.full(shape, np.nan, np.float32)
    if not len(pts):
        return n_ag, scat
    s = scattering(pts, knn, threads)
    row, col = grid.cells(pts["X"], pts["Y"])
    core = (row >= r0) & (row < r1) & (col >= c0) & (col < c1)
    idx = (row[core] - r0) * shape[1] + (col[core] - c0)
    n = np.bincount(idx, minlength=shape[0] * shape[1])
    sv = s[core]
    fin = np.isfinite(sv)
    tot = np.bincount(idx[fin], weights=sv[fin], minlength=shape[0] * shape[1])
    nf = np.bincount(idx[fin], minlength=shape[0] * shape[1])
    n_ag[:] = np.minimum(n, np.iinfo(np.uint16).max).reshape(shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        scat[:] = np.where(nf > 0, tot / np.maximum(nf, 1), np.nan).reshape(shape)
    return n_ag, scat


def cues(sources, grid, out_crs, dtm, dtm_ok, work, chunk_m=250.0, pad_m=2.0, knn=KNN, threads=1, in_srs=None,
         log=print):
    """n_ag (uint16) and scat (float32) on the grid, from the point sources. work: a folder for the spool and the
    finished chunks (reused when the same sources and grid come again). Returns (n_ag, scat, stats)."""
    wins = chunks(grid, chunk_m)
    key = {"sources": [os.path.abspath(s) for s in sources], "grid": grid.key(), "chunk_m": chunk_m, "pad_m": pad_m,
           "knn": knn, "ground_h": GROUND_H, "in_srs": in_srs}
    os.makedirs(work, exist_ok=True)
    key_path = os.path.join(work, "cues.json")
    if os.path.exists(key_path):
        with open(key_path) as f:
            old = json.load(f)
        if old.get("key") != key:
            raise SystemExit(f"{work} holds cues from other inputs; remove it or use another --out")
        state = old
    else:
        state = {"key": key, "spooled": False, "stats": {}}
    done_dir = os.path.join(work, "chunks")
    os.makedirs(done_dir, exist_ok=True)
    done = lambda name: os.path.exists(os.path.join(done_dir, name + ".npz"))  # noqa: E731
    spool = Spool(os.path.join(work, "spool"), grid, wins, pad_m)
    if not all(done(n) for n, _ in wins) and not state["spooled"]:
        for n, _ in wins:                  # a pass stopped half way left partial files
            if os.path.exists(spool.path(n)):
                os.remove(spool.path(n))
        stats = {"read": 0, "kept": 0, "above_ground": 0}
        rect = window_rect(grid, (0, grid.rows, 0, grid.cols), pad_m)
        for arr in read(sources, rect, out_crs, in_srs):
            X, Y, Z, st = above_ground(arr, grid, dtm, dtm_ok)
            spool.add(X, Y, Z)
            for k in stats:
                stats[k] += st[k]
        state.update(spooled=True, stats=stats)
        with open(key_path + ".part", "w") as f:
            json.dump(state, f)
        os.replace(key_path + ".part", key_path)
        log(f"cues: spooled {stats['above_ground']:,} above-ground points of {stats['read']:,} read")
    n_ag = np.zeros((grid.rows, grid.cols), np.uint16)
    scat = np.full((grid.rows, grid.cols), np.nan, np.float32)
    for i, (name, win) in enumerate(wins):
        path = os.path.join(done_dir, name + ".npz")
        if not os.path.exists(path):
            a, s = chunk_cues(spool.load(name), grid, win, knn, threads)
            np.savez_compressed(path + ".part.npz", n_ag=a, scat=s)
            os.replace(path + ".part.npz", path)
            log(f"cues: chunk {i + 1}/{len(wins)} ({name})")
        with np.load(path) as z:
            r0, r1, c0, c1 = win
            n_ag[r0:r1, c0:c1], scat[r0:r1, c0:c1] = z["n_ag"], z["scat"]
    for n, _ in wins:                      # every chunk is done: the spool goes (a later rerun reads again)
        if os.path.exists(spool.path(n)):
            os.remove(spool.path(n))
    if state.get("spooled"):
        state["spooled"] = False
        with open(key_path + ".part", "w") as f:
            json.dump(state, f)
        os.replace(key_path + ".part", key_path)
    return n_ag, scat, state.get("stats", {})
