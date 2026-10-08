"""Crown placement (docs/19 §19.3; the owner's method, Oct 8): fill each canopy cluster with model crowns, tallest first.

A crown is a dome on the 0.5 m height grid: z(d) = H * (1 - a * (d / R)^n) for d <= R, nothing beyond. R comes from the
crown-width model for the tree's height and type (from the owner's kept lone trees), within the spread those trees showed.
The surface the placed crowns explain is their upper envelope E (the lidar only sees the top crown where two overlap).

1. Seeds: every local peak of the smoothed height, tallest first. A seed becomes a tree only where the height there is
   meaningfully above E ("unexplained": at least max(1 m, 15% of the height)).
2. For a seed, try crown centres near it and the allowed widths of each type; keep the one that best explains the surface
   (least absolute height error over the patch), subject to the overlap rule: the overlap area of two crown discs, as a share
   of the smaller disc, stays at or under theta.
3. Keep the tree only if it lowers the error by at least lam (a per-tree cost, so noise doesn't become trees).
4. When the seeds run out, look for leftover unexplained blobs bigger than the smallest crown and seed them; repeat.
5. Repair: per tree, try deleting, moving, resizing, reshaping, splitting into two and merging with a neighbour; keep any
   change that lowers error + lam * trees + the size costs. Up to a few sweeps. Trees marked "fixed" (catalogued trees,
   placed first by the build) are never touched or merged.

Pure numpy/scipy; no I/O here. Coordinates are (row, col) in cells; distances in cells unless named _m."""
import math
import numpy as np
from scipy import ndimage

PX = 0.5  # metres per cell


class Model:
    """Crown width and top shape per type. widths: {type: (a, b)} for width_m = a * H^b; spread_log: sd of log width;
    shapes: {type: [(a, n), ...]} the lone-tree dome and a crowded one whose edge stays higher (crowns in a cluster meet
    high); types: the types to try in this area; kappa: the size prior's weight."""

    def __init__(self, widths, shapes, spread_log, types, kappa=0.25):
        self.widths, self.shapes, self.sd, self.types, self.kappa = widths, shapes, spread_log, types, kappa

    def size_cost(self, t):
        """A crown pays for straying from the typical width for its height: kappa * z^2 * H * (typical crown area),
        z = log(width / typical) / spread. Same units as the height error (metres x cells)."""
        R0 = self.radius_cells(t["H"], t["type"])
        z = math.log(t["R"] / R0) / self.sd
        return self.kappa * z * z * t["H"] * math.pi * R0 * R0

    def radius_cells(self, H, t, k=1.0):
        a, b = self.widths[t]
        return k * 0.5 * a * H ** b / PX

    def scales(self):
        # the widths a lone tree of this height and type showed: median and about 1 sd either side, plus a squeezed one
        s = self.sd
        return (math.exp(-1.5 * s), math.exp(-0.75 * s), 1.0, math.exp(0.75 * s), math.exp(1.5 * s))


def lens_area(d, r1, r2):
    """Area where two discs overlap (cells^2)."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * min(r1, r2) ** 2
    a1 = r1 * r1 * math.acos((d * d + r1 * r1 - r2 * r2) / (2 * d * r1))
    a2 = r2 * r2 * math.acos((d * d + r2 * r2 - r1 * r1) / (2 * d * r2))
    a3 = 0.5 * math.sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2)))
    return a1 + a2 - a3


def overlap_share(t1, t2):
    d = math.hypot(t1["y"] - t2["y"], t1["x"] - t2["x"])
    return lens_area(d, t1["R"], t2["R"]) / (math.pi * min(t1["R"], t2["R"]) ** 2)


class Placer:
    def __init__(self, s, valid, model, theta=1 / 3, lam=12.0, tree_h=3.0, canopy_h=2.0, bucket=32, avoid=None, avoid_h=6.0):
        self.s = s.astype(np.float32)
        self.valid = valid                       # cells that count in the error (not buildings, not missing)
        # cells where a short seed isn't trusted (next to buildings: roof slivers the building mask missed)
        self.avoid, self.avoid_h = avoid, avoid_h
        self.m, self.theta, self.lam, self.tree_h, self.canopy_h = model, theta, lam, tree_h, canopy_h
        self.E = np.zeros_like(self.s)
        self.trees = []
        self.B = bucket
        self.grid = {}
        self.min_cells = math.pi * model.radius_cells(tree_h, model.types[0], model.scales()[0]) ** 2

    # --- crowns and the envelope -------------------------------------------------------------------------------
    def crown(self, t, r0, r1, c0, c1):
        yy, xx = np.ogrid[r0:r1, c0:c1]
        d = np.hypot(yy - t["y"], xx - t["x"]) / t["R"]
        a, n = t["a"], t["n"]
        z = t["H"] * (1 - a * np.minimum(d, 1.0) ** n)
        return np.where(d <= 1.0, z, 0.0).astype(np.float32)

    def bbox(self, t, pad=1):
        R = t["R"] + pad
        return (max(0, int(math.floor(t["y"] - R))), min(self.s.shape[0], int(math.ceil(t["y"] + R)) + 1),
                max(0, int(math.floor(t["x"] - R))), min(self.s.shape[1], int(math.ceil(t["x"] + R)) + 1))

    def _keys(self, b):
        r0, r1, c0, c1 = b
        return [(i, j) for i in range(r0 // self.B, (r1 - 1) // self.B + 1) for j in range(c0 // self.B, (c1 - 1) // self.B + 1)]

    def near(self, b, skip=()):
        ids = set()
        for k in self._keys(b):
            ids |= self.grid.get(k, set())
        return [i for i in ids if self.trees[i]["alive"] and i not in skip]

    def envelope(self, b, skip=(), extra=()):
        r0, r1, c0, c1 = b
        E = np.zeros((r1 - r0, c1 - c0), np.float32)
        for i in self.near(b, skip):
            E = np.maximum(E, self._crown_in(self.trees[i], b))
        for t in extra:
            E = np.maximum(E, self._crown_in(t, b))
        return E

    def _crown_in(self, t, b):
        r0, r1, c0, c1 = b
        tb = self.bbox(t, 0)
        i0, i1, j0, j1 = max(r0, tb[0]), min(r1, tb[1]), max(c0, tb[2]), min(c1, tb[3])
        out = np.zeros((r1 - r0, c1 - c0), np.float32)
        if i0 < i1 and j0 < j1:
            out[i0 - r0:i1 - r0, j0 - c0:j1 - c0] = self.crown(t, i0, i1, j0, j1)
        return out

    def err(self, b, E):
        r0, r1, c0, c1 = b
        v = self.valid[r0:r1, c0:c1]
        return float(np.abs(self.s[r0:r1, c0:c1] - E)[v].sum())

    def union(self, *bs):
        return (min(b[0] for b in bs), max(b[1] for b in bs), min(b[2] for b in bs), max(b[3] for b in bs))

    def add(self, t):
        t["alive"] = True
        self.trees.append(t)
        i = len(self.trees) - 1
        for k in self._keys(self.bbox(t, 0)):
            self.grid.setdefault(k, set()).add(i)
        b = self.bbox(t, 0)
        self.E[b[0]:b[1], b[2]:b[3]] = self.envelope(b)
        return i

    def kill(self, i):
        self.trees[i]["alive"] = False
        b = self.bbox(self.trees[i], 0)
        self.E[b[0]:b[1], b[2]:b[3]] = self.envelope(b)

    def ok_overlap(self, t, skip=()):
        for j in self.near(self.bbox(t, 0), skip):
            if overlap_share(t, self.trees[j]) > self.theta + 1e-9:
                return False
        return True

    # --- placing one tree ---------------------------------------------------------------------------------------
    def gain(self, t):
        """Error saved by adding crown t on top of the current envelope: only cells inside its disc change."""
        b = self.bbox(t, 0)
        r0, r1, c0, c1 = b
        if r0 >= r1 or c0 >= c1:
            return 0.0
        z = self.crown(t, r0, r1, c0, c1)
        S, E0, V = self.s[r0:r1, c0:c1], self.E[r0:r1, c0:c1], self.valid[r0:r1, c0:c1]
        E1 = np.maximum(E0, z)
        return float((np.abs(S - E0) - np.abs(S - E1))[V].sum())

    def best_near(self, y, x, H, types, reach, overlap=True):
        """The best crown centred within `reach` cells of (y, x) (a catalogued tree's trunk point): any of `types`, any
        allowed width and shape. overlap=False skips the overlap rule (a catalogue says the tree exists)."""
        best = (-math.inf, None)
        for typ in types:
            for k in self.m.scales():
                R = self.m.radius_cells(H, typ, k)
                if R < 1.5:
                    continue
                for a, n in self.m.shapes[typ]:
                    for dy in range(-reach, reach + 1):
                        for dx in range(-reach, reach + 1):
                            if dy * dy + dx * dx > reach * reach:
                                continue
                            t = {"y": y + dy, "x": x + dx, "H": H, "R": R, "type": typ, "a": a, "n": n}
                            if overlap and not self.ok_overlap(t):
                                continue
                            g = self.gain(t) - self.m.size_cost(t)
                            if g > best[0]:
                                best = (g, t)
        return best

    def best_at(self, y, x, H, step=2):
        """The best crown for a seed at (y, x) of height H: centre within 0.6 R of the seed, any type and allowed width,
        on top of the current envelope. Returns (gain, tree) or (0, None)."""
        best = (0.0, None)
        for typ in self.m.types:
            for k in self.m.scales():
                R = self.m.radius_cells(H, typ, k)
                if R < 1.5:
                    continue
                reach = int(max(1, round(0.6 * R)))
                for a, n in self.m.shapes[typ]:
                    for dy in range(-reach, reach + 1, step):
                        for dx in range(-reach, reach + 1, step):
                            if dy * dy + dx * dx > reach * reach:
                                continue
                            t = {"y": y + dy, "x": x + dx, "H": H, "R": R, "type": typ, "a": a, "n": n}
                            if not self.ok_overlap(t):
                                continue
                            g = self.gain(t) - self.m.size_cost(t)
                            if g > best[0]:
                                best = (g, t)
        if best[1] is not None and step > 1:          # refine the centre by single cells
            t0 = best[1]
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == dx == 0:
                        continue
                    t = dict(t0, y=t0["y"] + dy, x=t0["x"] + dx)
                    if self.ok_overlap(t):
                        g = self.gain(t) - self.m.size_cost(t)
                        if g > best[0]:
                            best = (g, t)
        return best

    def unexplained(self, y, x):
        h = self.s[y, x]
        return h >= self.tree_h and (h - self.E[y, x]) >= max(1.0, 0.15 * h)

    def place_seeds(self, seeds):
        placed = 0
        for y, x in seeds:
            if not self.valid[y, x] or not self.unexplained(y, x):
                continue
            if self.avoid is not None and self.avoid[y, x] and self.s[y, x] < self.avoid_h:
                continue
            # the tree's height: the highest point within 1 m of the seed
            r0, r1, c0, c1 = max(0, y - 2), y + 3, max(0, x - 2), x + 3
            H = float(self.s[r0:r1, c0:c1].max())
            g, t = self.best_at(y, x, H)
            if t is not None and g >= self.lam:
                self.add(t)
                placed += 1
        return placed

    def leftover_seeds(self):
        X = (self.s - self.E) >= np.maximum(1.0, 0.15 * self.s)
        X &= (self.s >= self.tree_h) & self.valid
        lab, n = ndimage.label(X)
        if n == 0:
            return []
        sizes = ndimage.sum(X, lab, np.arange(1, n + 1))
        tops = ndimage.maximum_position(self.s, lab, np.arange(1, n + 1))
        seeds = [(int(p[0]), int(p[1])) for p, z in zip(tops, sizes) if z >= self.min_cells]
        seeds.sort(key=lambda p: -self.s[p])
        return seeds

    def run_greedy(self, rounds=3, log=None):
        peaks = (self.s == ndimage.maximum_filter(self.s, size=3)) & (self.s >= self.tree_h) & self.valid
        ys, xs = np.nonzero(peaks)
        order = np.argsort(-self.s[ys, xs])
        n = self.place_seeds(list(zip(ys[order].tolist(), xs[order].tolist())))
        if log: log(f"  greedy: {n} trees from {len(ys)} peaks")
        for r in range(rounds):
            seeds = self.leftover_seeds()
            if not seeds:
                break
            k = self.place_seeds(seeds)
            if log: log(f"  leftover round {r + 1}: {len(seeds)} blobs, {k} trees")
            if k == 0:
                break

    # --- repair ------------------------------------------------------------------------------------------------
    def total_err(self):
        return float(np.abs(self.s - self.E)[self.valid].sum())

    def try_replace(self, olds, news):
        """Error change (with the per-tree cost) of replacing trees `olds` by `news`; < 0 is better."""
        bs = [self.bbox(self.trees[i]) for i in olds] + [self.bbox(t) for t in news]
        b = self.union(*bs)
        for t in news:
            if not self.ok_overlap(t, skip=olds):
                return math.inf
        before = self.err(b, self.envelope(b)) + sum(self.m.size_cost(self.trees[i]) for i in olds)
        after = self.err(b, self.envelope(b, skip=olds, extra=news)) + sum(self.m.size_cost(t) for t in news)
        return (after - before) + self.lam * (len(news) - len(olds))

    def apply(self, olds, news):
        for i in olds:
            self.kill(i)
        for t in news:
            self.add(dict(t))

    def repair(self, sweeps=3, log=None):
        for sw in range(sweeps):
            changed = 0
            for i in range(len(self.trees)):
                t = self.trees[i]
                if not t["alive"] or t.get("fixed"):
                    continue
                cands = [[]]                                            # delete
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-2, 0), (2, 0), (0, -2), (0, 2)):
                    cands.append([dict(t, y=t["y"] + dy, x=t["x"] + dx)])  # move
                for f in (0.9, 1.1):
                    R = t["R"] * f
                    lo = self.m.radius_cells(t["H"], t["type"], self.m.scales()[0])
                    hi = self.m.radius_cells(t["H"], t["type"], self.m.scales()[-1])
                    if lo <= R <= hi:
                        cands.append([dict(t, R=R)])                     # resize
                for a, n in self.m.shapes[t["type"]]:
                    if (a, n) != (t["a"], t["n"]):
                        cands.append([dict(t, a=a, n=n)])                       # lone vs crowded shape
                for other in self.m.types:
                    if other != t["type"]:
                        a, n = self.m.shapes[other][0]
                        cands.append([dict(t, type=other, R=self.m.radius_cells(t["H"], other), a=a, n=n)])  # retype
                # split into two along each of four axes
                for ang in (0, 45, 90, 135):
                    uy, ux = math.sin(math.radians(ang)), math.cos(math.radians(ang))
                    pair = []
                    for sgn in (-1, 1):
                        y, x = t["y"] + sgn * 0.45 * t["R"] * uy, t["x"] + sgn * 0.45 * t["R"] * ux
                        yi, xi = int(round(y)), int(round(x))
                        if not (0 <= yi < self.s.shape[0] and 0 <= xi < self.s.shape[1]):
                            break
                        H = float(self.s[max(0, yi - 2):yi + 3, max(0, xi - 2):xi + 3].max())
                        if H < self.tree_h:
                            break
                        pair.append({"y": y, "x": x, "H": H, "R": self.m.radius_cells(H, t["type"]), "type": t["type"], "a": t["a"], "n": t["n"]})
                    if len(pair) == 2 and overlap_share(pair[0], pair[1]) <= self.theta:
                        cands.append(pair)
                best, arg = 0.0, None
                for news in cands:
                    dlt = self.try_replace([i], news)
                    if dlt < best - 1e-6:
                        best, arg = dlt, news
                # merge with the nearest neighbour: one crown at the taller one's place
                for j in self.near(self.bbox(t)):
                    if j == i or self.trees[j].get("fixed"):
                        continue
                    u = self.trees[j]
                    if math.hypot(t["y"] - u["y"], t["x"] - u["x"]) > t["R"] + u["R"]:
                        continue
                    top = t if t["H"] >= u["H"] else u
                    for k in self.m.scales():
                        news = [dict(top, R=self.m.radius_cells(top["H"], top["type"], k))]
                        dlt = self.try_replace([i, j], news)
                        if dlt < best - 1e-6:
                            best, arg = dlt, ("merge", j, news)
                if arg is not None:
                    if isinstance(arg, tuple):
                        self.apply([i, arg[1]], arg[2])
                    else:
                        self.apply([i], arg)
                    changed += 1
            if log: log(f"  repair sweep {sw + 1}: {changed} changes, {self.count()} trees")
            if changed == 0:
                break

    def count(self):
        return sum(1 for t in self.trees if t["alive"])

    def alive(self):
        return [t for t in self.trees if t["alive"]]

    def labels(self):
        """Each cell to the tree whose crown is the top surface there (0 = none)."""
        lab = np.zeros(self.s.shape, np.int32)
        top = np.zeros(self.s.shape, np.float32)
        for k, t in enumerate(self.alive(), 1):
            b = self.bbox(t, 0)
            z = self.crown(t, *b)
            r0, r1, c0, c1 = b
            win = z > top[r0:r1, c0:c1]
            lab[r0:r1, c0:c1][win] = k
            top[r0:r1, c0:c1] = np.maximum(top[r0:r1, c0:c1], z)
        return lab
