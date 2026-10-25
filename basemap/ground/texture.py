"""Texture and the photo's variation (G1b; plan C8). NumPy only, so the rules test anywhere NumPy is.

The painter (paint.py) lays flat colours; this module supplies what makes them look like the valley:

- **Procedural noise** from a ground type's measured texture energy (soils' palette `oct_l` and `oct_c`: the mean
  square of the difference of Gaussians in five octaves, 1.2-19.2 m, for L and for chroma). `octave_noise` is value
  noise on a lattice hashed from the absolute coordinates, so every window and every level samples one field: windows
  meet without a seam, and a tile painted twice is the same tile. An octave finer than two cells would alias and is
  skipped (its energy is what a cell's average removes), so the low zoom levels get no noise at all.
- **The photo's variation.** The NAIP 2 m COG's colour, put on a flat-ground footing by `illumination_gain` (slope and
  aspect from the DEM, at the sun angle of the flight that took the pixel), less the ground type's median, kept where
  it is within `MAHALANOBIS_FULL` of the type in the type's own spread and dropped by `MAHALANOBIS_ZERO` (`variation`),
  and nowhere a shadow, a steep slope, a crop, a vector surface or its 3 m band, or a place the photo doesn't reach.
- **Cast shadows** (`shadow_cells`): dark and blue-shifted next to something tall. They are treated as covered: the
  variation is off there and the base shows, as the floor rule fills them in the box classes.
- **The sun** (`sun_position`) at a flight's time and place, and the flights' local times (`parse_local`).
"""

import math
from datetime import datetime, timedelta, timezone

import numpy as np

OCTAVES_M = (1.2, 2.4, 4.8, 9.6, 19.2)      # soils' octaves (plugins/soils/build/photo.py OCTAVES_M)
LATTICE_PER_OCTAVE = 2.0                    # a feature of octave s spans about 2 s: the lattice spacing is 2 s
MIN_CELLS_PER_LATTICE = 2.0                 # a lattice finer than two cells aliases: that octave is skipped
NOISE_NORM = 1.35                          # makes the smoothstep value noise's variance 1 (measured, test_texture.py)
L_CLIP = 0.06                               # the noise never moves L more than this ...
C_CLIP = 0.025                              # ... or chroma more than this (OKLab units)
SEED_L, SEED_C = 11, 29

MAHALANOBIS_FULL = 2.5                      # the photo's variation is kept at or inside this distance (plan G1b)
MAHALANOBIS_ZERO = 3.0                      # ... and gone by this one (a soft end; beyond it is not this type's ground)
MAX_SLOPE_DEG = 30.0                        # no photo variation on slopes steeper than this; the plan's cut-first
                                            # fallback is 15 degrees (set it here if the normalisation misses)
GAIN_MAX = 2.0                              # the illumination gain is kept within 1 / GAIN_MAX .. GAIN_MAX, else off
MIN_COS_RATIO = 0.25                        # cos(incidence) under this share of the flat value: self-shadowed, off
SHADOW_DL = 0.10                            # a cast shadow is this much darker than the type's median L ...
SHADOW_DB = 0.010                           # ... and this much bluer (OKLab b lower) ...
SHADOW_REACH_M = 40.0                       # ... and within this of something tall
CLUSTER_NDVI = 0.30                         # a crop cluster outside the fields is confirmed when the photo's NDVI >= this
LOCAL_UTC_OFFSET_H = -6                     # NAIP's local times are read as MDT (soils' flights.fgb note)
BALANCE_FLOOR = 2000                        # cells a flight must hold of a ground type before its own median is used: under it
                                            # the median of a few cells follows what happens to be there (a field edge, one
                                            # farmyard) and would pull the type's level off, so the type keeps the palette's
                                            # valley-wide median in that flight
BALANCE_BINS = 2048                         # the median is read from a histogram per flight and type (bin 0.0005 in L, a, b)
BLOCK_M = 1024.0                            # the local medians' block, on the grid from its origin (about 1 km: 512 cells at 2 m)
BLOCK_BINS = 512                            # a block's histogram (bin 0.002 in L, a, b: 0.2 dE), so a valley's blocks stay small
BLOCK_STORE = 500                           # a block with fewer cells of a type in a flight is not written down (the floor never goes lower)
BALANCE_RANGE = ((0.0, 1.0), (-0.5, 0.5), (-0.5, 0.5))
NO_FLIGHT = 0xFFFFFFFF                      # the flight id where no flight polygon covers a cell
SUN_LAT, SUN_LON = 43.6, -116.4             # where a flight's sun is computed when it has no place of its own: the valley


# ---- noise -----------------------------------------------------------------------------------------------------------

def _hash01(ix, iy, seed):
    """A repeatable pseudo-random number in [0, 1) for each integer lattice point (any shape)."""
    mask = np.uint64(0xFFFFFFFF)
    h = (ix.astype(np.int64).astype(np.uint64) * np.uint64(374761393)
         + iy.astype(np.int64).astype(np.uint64) * np.uint64(668265263)
         + np.uint64(seed * 2246822519 & 0xFFFFFFFF)) & mask
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & mask
    h = (h ^ (h >> np.uint64(16))) & mask
    return h.astype(np.float64) / 4294967296.0


def value_noise(xs, ys, spacing, seed):
    """Smooth noise of variance 1 and mean 0 on (len(ys), len(xs)): hashed values on a lattice `spacing` metres apart,
    blended with a smoothstep. A function of the absolute coordinates alone. xs, ys: 1-D, metres."""
    gx = np.asarray(xs, np.float64) / spacing
    gy = np.asarray(ys, np.float64) / spacing
    x0, y0 = np.floor(gx), np.floor(gy)
    fx, fy = gx - x0, gy - y0
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    ix, iy = x0.astype(np.int64)[None, :], y0.astype(np.int64)[:, None]
    root12 = math.sqrt(12.0)

    def v(dx, dy):
        return (_hash01(ix + dx, iy + dy, seed) - 0.5) * root12

    top = v(0, 0) * (1 - sx)[None, :] + v(1, 0) * sx[None, :]
    bot = v(0, 1) * (1 - sx)[None, :] + v(1, 1) * sx[None, :]
    return ((top * (1 - sy)[:, None] + bot * sy[:, None]) * NOISE_NORM).astype(np.float32)


def usable_octaves(res):
    """The octave indices a level of `res` metres a cell can draw."""
    return [k for k, s in enumerate(OCTAVES_M) if LATTICE_PER_OCTAVE * s >= MIN_CELLS_PER_LATTICE * res]


def octave_noise(xs, ys, energies, res, seed):
    """Noise whose octave k has the variance energies[k] (None or NaN: none), on (len(ys), len(xs)), float32."""
    out = np.zeros((len(ys), len(xs)), np.float32)
    for k in usable_octaves(res):
        e = energies[k] if k < len(energies) else None
        if e is None or not np.isfinite(e) or e <= 0:
            continue
        out += math.sqrt(float(e)) * value_noise(xs, ys, LATTICE_PER_OCTAVE * OCTAVES_M[k], seed + 101 * k)
    return out


def noise_fields(xs, ys, oct_l, oct_c, res):
    """(dL, dC) for a window whose cells have per-cell energies: oct_l, oct_c are (rows, cols, 5) arrays or length-5
    sequences. Per-cell energies are applied by weighting each octave's unit noise."""
    shape = (len(ys), len(xs))
    dl = np.zeros(shape, np.float32)
    dc = np.zeros(shape, np.float32)
    for k in usable_octaves(res):
        s = LATTICE_PER_OCTAVE * OCTAVES_M[k]
        dl += _amp(oct_l, k, shape) * value_noise(xs, ys, s, SEED_L + 101 * k)
        dc += _amp(oct_c, k, shape) * value_noise(xs, ys, s, SEED_C + 101 * k)
    return np.clip(dl, -L_CLIP, L_CLIP), np.clip(dc, -C_CLIP, C_CLIP)


def _amp(energy, k, shape):
    e = np.asarray(energy, np.float64)
    e = e[..., k] if e.ndim else e
    e = np.where(np.isfinite(e) & (e > 0), e, 0.0)
    return np.broadcast_to(np.sqrt(e), shape).astype(np.float32)


def add_texture(lab, dl, dc, weight=None):
    """lab (rows, cols, 3) OKLab with dL added to L and dC to chroma (hue kept), scaled by weight (rows, cols) or 1."""
    out = np.array(lab, np.float32, copy=True)
    w = 1.0 if weight is None else weight
    out[..., 0] += w * dl
    a, b = out[..., 1], out[..., 2]
    chroma = np.hypot(a, b)
    new = np.maximum(chroma + w * dc, 0.0)
    k = np.where(chroma > 1e-4, new / np.maximum(chroma, 1e-4), 1.0)
    out[..., 1], out[..., 2] = a * k, b * k
    return out


# ---- the sun and the light -------------------------------------------------------------------------------------------

def parse_local(text):
    """A NAIP local time ('MM/DD/YYYY hh:mm', read as MDT; ISO dates accepted) as an aware UTC datetime, or None."""
    if not text:
        return None
    text = str(text).strip()
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
                "%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            t = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%H" not in fmt:
            t = t.replace(hour=12)                       # a day without a time: local noon
        return (t - timedelta(hours=LOCAL_UTC_OFFSET_H)).replace(tzinfo=timezone.utc)
    return None


def sun_position(when_utc, lat=SUN_LAT, lon=SUN_LON):
    """(azimuth, elevation) in degrees, azimuth clockwise from north, of the sun at an aware UTC datetime and a place
    (NOAA's low-precision equations: good to a fraction of a degree, plenty for an illumination ratio)."""
    t = when_utc.astimezone(timezone.utc)
    day = t.timetuple().tm_yday
    hours = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * math.pi / 365 * (day - 1 + (hours - 12) / 24)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    solar_min = hours * 60 + eqt + 4 * lon
    ha = math.radians(solar_min / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(decl) + math.cos(la) * math.cos(decl) * math.cos(ha)
    zen = math.acos(max(-1.0, min(1.0, cz)))
    el = 90 - math.degrees(zen)
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(decl) * math.cos(la))) + 180
    return az % 360, el


def slope_aspect(z, res):
    """(slope, aspect) in radians of an elevation grid (rows north to south) at `res` metres a cell: slope from level,
    aspect the compass bearing the surface faces (clockwise from north). NaN elevations give NaN."""
    z = np.asarray(z, np.float64)
    dz_dy_south, dz_dx = np.gradient(z, res)
    dz_dn = -dz_dy_south                                 # rows run south: north is the other way
    slope = np.arctan(np.hypot(dz_dx, dz_dn))
    aspect = np.arctan2(-dz_dx, -dz_dn) % (2 * math.pi)   # the downhill direction
    return slope.astype(np.float32), aspect.astype(np.float32)


def illumination_gain(slope, aspect, sun_az_deg, sun_el_deg):
    """The factor that puts a pixel lit on a slope back to what flat ground would be at that sun: sin(el) / cos(i),
    with cos(i) = cos(slope) sin(el) + sin(slope) cos(el) cos(az - aspect). Returns (gain, ok): ok is False where
    the surface turns from the sun, where the gain would leave 1 / GAIN_MAX .. GAIN_MAX, or the sun is below the
    horizon. sun_az_deg, sun_el_deg: scalars or arrays that broadcast with slope."""
    az = np.radians(np.asarray(sun_az_deg, np.float64))
    el = np.radians(np.asarray(sun_el_deg, np.float64))
    flat = np.sin(el)
    cos_i = np.cos(slope) * flat + np.sin(slope) * np.cos(el) * np.cos(az - aspect)
    with np.errstate(invalid="ignore", divide="ignore"):
        gain = flat / cos_i
        ok = (flat > 0.05) & (cos_i > MIN_COS_RATIO * flat) & (gain <= GAIN_MAX) & (gain >= 1.0 / GAIN_MAX)
    ok &= np.isfinite(gain)
    return np.where(ok, gain, 1.0).astype(np.float32), ok


# ---- the photo's variation -------------------------------------------------------------------------------------------

def cov_matrices(upper):
    """(n, 3, 3) symmetric matrices from soils' lab_cov rows (LL, La, Lb, aa, ab, bb), or None where a row is missing."""
    out = []
    for row in upper:
        if row is None or len(row) != 6 or not np.all(np.isfinite(np.asarray(row, np.float64))):
            out.append(None)
            continue
        ll, la, lb, aa, ab, bb = (float(v) for v in row)
        out.append(np.array([[ll, la, lb], [la, aa, ab], [lb, ab, bb]]))
    return out


def inverse_covariance(cov, floor=1e-6):
    """The inverse of a 3 x 3 covariance with its diagonal floored (a type with a near-zero spread must not make every
    pixel an outlier by a rounding error); None stays None."""
    if cov is None:
        return None
    c = np.array(cov, np.float64)
    c[np.diag_indices(3)] = np.maximum(np.diag(c), floor)
    try:
        return np.linalg.inv(c)
    except np.linalg.LinAlgError:
        return None


def mahalanobis(dev, inv):
    """The Mahalanobis distance of each deviation dev (..., 3) under inv (..., 3, 3) (or one (3, 3) for all)."""
    d = np.asarray(dev, np.float64)
    if inv.ndim == 2:
        q = np.einsum("...i,ij,...j->...", d, inv, d)
    else:
        q = np.einsum("...i,...ij,...j->...", d, inv, d)
    return np.sqrt(np.maximum(q, 0.0)).astype(np.float32)


def variation_weight(dist):
    """1 inside MAHALANOBIS_FULL, 0 from MAHALANOBIS_ZERO, a straight ramp between."""
    return np.clip((MAHALANOBIS_ZERO - dist) / (MAHALANOBIS_ZERO - MAHALANOBIS_FULL), 0.0, 1.0).astype(np.float32)


def grow(mask, cells):
    """A boolean mask dilated by `cells` (a square; NumPy only)."""
    m = np.asarray(mask, bool)
    for _ in range(int(cells)):
        p = np.pad(m, 1)
        m = (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:])
    return m


def shadow_cells(photo_lab, type_lab, near_tall):
    """Cast-shadow cells: dark (L under the type's median by SHADOW_DL), blue-shifted (b under its median by SHADOW_DB)
    and next to something tall (near_tall, a bool array; None means the colour test alone), grown by one cell
    (the penumbra)."""
    dark = photo_lab[..., 0] < type_lab[..., 0] - SHADOW_DL
    blue = photo_lab[..., 2] < type_lab[..., 2] - SHADOW_DB
    s = dark & blue
    if near_tall is not None:
        s &= near_tall
    return grow(s, 1)


def photo_variation(photo_lab, type_lab, inv_cov, ok):
    """(delta OKLab, weight) of the photo's variation on a window. photo_lab: the photo's OKLab on a flat-light
    footing; type_lab: each cell's ground type median (rows, cols, 3); inv_cov: (rows, cols, 3, 3) inverse covariances
    (NaN rows for a type without one); ok: bool, where the photo can be used (covered, not shadow, not steep, ...).
    The delta is the photo less the type's median; the weight is 1 inside MAHALANOBIS_FULL, ramps to 0 by
    MAHALANOBIS_ZERO, and is 0 wherever ok is False or the type has no spread."""
    dev = (photo_lab - type_lab).astype(np.float32)
    has = np.all(np.isfinite(inv_cov), axis=(-2, -1))
    inv = np.where(has[..., None, None], inv_cov, np.eye(3))
    dist = mahalanobis(dev, inv)
    w = variation_weight(dist) * (ok & has)
    return dev, w.astype(np.float32)


def photo_variation_by_type(photo_lab, type_lab, gt, inv_table, ok):
    """photo_variation with the spread given per ground type (inv_table (n, 3, 3), gt the cells' type ids): one 3x3 per
    type instead of a gathered (rows, cols, 3, 3), which at a 2 m block with its halo is hundreds of MB."""
    dev = (photo_lab - type_lab).astype(np.float32)
    dist = np.zeros(gt.shape, np.float32)
    has = np.zeros(gt.shape, bool)
    for t in np.unique(gt):
        inv = inv_table[t]
        if not np.all(np.isfinite(inv)):
            continue
        sel = gt == t
        dist[sel] = mahalanobis(dev[sel], inv)
        has[sel] = True
    w = variation_weight(dist) * (ok & has)
    return dev, w.astype(np.float32)


class FlightBalance:
    """The photo's median OKLab per ground type within each flight, and within each flight and block (#415). Two flights
    of different days differ in level (light, haze, sensor) by more than the soil's own spread, so the photo less one
    valley-wide type median carries the step between them into the paint. Measured against the median of the type within
    the flight that took the pixel, a flight that is lighter or darker overall adds nothing, and what varies inside a
    flight stays. A flight is not one level all over (a dark band along its own edge, a sliver whose whole-flight median
    does not describe the ground beside it), so the same medians are also kept per block of BLOCK_M on the grid.

    Fed windows with `add` (the photo's flat-light OKLab on the cells the variation can use, the flight id and the ground
    type of each, and where the cells are), it keeps a histogram per (flight, type) and per (flight, type, block), so a
    valley of 2 m cells is read a window at a time and the median is the histogram's. `medians` gives
    {(flight, type): (n, (L, a, b))} and `block_medians` {(flight, type, bx, by): (n, (L, a, b))}; `to_json` and
    Balance.from_json carry them."""
    SCHEMA = "ground.flight-balance/2"

    def __init__(self, inputs=None, block_m=BLOCK_M):
        self.block_m = float(block_m)
        self.hist = {}                                  # (flight, gid) -> int64 (3, BALANCE_BINS)
        self.block_hist = {}                            # (flight, gid, bx, by) -> int32 (3, BLOCK_BINS)
        self.inputs = dict(inputs or {})                # what it was measured from: sha256 of the COG, flights and DEM (None: none)

    @staticmethod
    def _bins(vals, c, bins):
        lo, hi = BALANCE_RANGE[c]
        return np.clip(((vals[:, c] - lo) / (hi - lo) * bins).astype(np.int64), 0, bins - 1)

    def add(self, fid, gt, lab, keep, xs=None, ds=None):
        """Count the cells of `keep` (bool) by (flight id, type id): fid (uint32, NO_FLIGHT outside the flights), gt (type
        ids), lab (rows, cols, 3). xs, ds (1-D, metres east and south of the grid's origin, one per column and row) say
        where the cells are, for the per-block counts; without them only the flight's are kept."""
        sel = np.asarray(keep, bool) & (np.asarray(fid) != NO_FLIGHT) & np.all(np.isfinite(lab), axis=-1)
        if not sel.any():
            return
        f, g, v = np.asarray(fid)[sel].astype(np.int64), np.asarray(gt)[sel].astype(np.int64), np.asarray(lab)[sel]
        key = f * 65536 + g
        if xs is not None and ds is not None:
            rr, cc = np.nonzero(sel)
            bx = np.floor(np.asarray(xs)[cc] / self.block_m).astype(np.int64)
            by = np.floor(np.asarray(ds)[rr] / self.block_m).astype(np.int64)
            bkey = (key * 4096 + (bx + 2048)) * 4096 + (by + 2048)
            order = np.argsort(bkey, kind="stable")
            sk, sv = bkey[order], v[order]
            cuts = np.flatnonzero(np.diff(sk)) + 1
            for k, vals in zip(sk[np.r_[0, cuts]], np.split(sv, cuts)):
                k, byy = divmod(int(k), 4096)
                k, bxx = divmod(k, 4096)
                h = self.block_hist.setdefault((k // 65536, k % 65536, bxx - 2048, byy - 2048),
                                               np.zeros((3, BLOCK_BINS), np.int32))
                for c in range(3):
                    h[c] += np.bincount(self._bins(vals, c, BLOCK_BINS), minlength=BLOCK_BINS).astype(np.int32)
        order = np.argsort(key, kind="stable")
        key, v = key[order], v[order]
        cuts = np.flatnonzero(np.diff(key)) + 1
        for k, vals in zip(key[np.r_[0, cuts]], np.split(v, cuts)):
            h = self.hist.setdefault((int(k // 65536), int(k % 65536)), np.zeros((3, BALANCE_BINS), np.int64))
            for c in range(3):
                h[c] += np.bincount(self._bins(vals, c, BALANCE_BINS), minlength=BALANCE_BINS)

    @staticmethod
    def _median(h, bins):
        n = int(h[0].sum())
        med = []
        for c, (lo, hi) in enumerate(BALANCE_RANGE):
            i = int(np.searchsorted(np.cumsum(h[c]), (n + 1) / 2.0))
            med.append(lo + (min(i, bins - 1) + 0.5) * (hi - lo) / bins)
        return n, tuple(round(m, 5) for m in med)

    def medians(self):
        return {key: self._median(h, BALANCE_BINS) for key, h in self.hist.items()}

    def block_medians(self):
        return {key: self._median(h, BLOCK_BINS) for key, h in self.block_hist.items()}

    def to_json(self):
        """Blocks with fewer than BLOCK_STORE cells are left out (under any floor in use they fall back to the flight)."""
        blocks = {f"{f}:{g}:{bx}:{by}": {"n": n, "med": list(m)}
                  for (f, g, bx, by), (n, m) in sorted(self.block_medians().items()) if n >= BLOCK_STORE}
        return {"schema": self.SCHEMA, "floor": BALANCE_FLOOR, "bins": BALANCE_BINS, "block_m": self.block_m,
                "block_bins": BLOCK_BINS, "inputs": self.inputs,
                "cells": {f"{f}:{g}": {"n": n, "med": list(m)} for (f, g), (n, m) in sorted(self.medians().items())},
                "blocks": blocks}


class Balance:
    """FlightBalance's medians as a lookup: for any window, the median each cell is measured against. Within a flight and
    ground type the reference is carried between the centres of the blocks of BLOCK_M, bilinearly, so the blocks themselves
    never show. A block counts only where it holds `floor` cells of the type in the flight: a cell between a block that
    does and one that does not (past the flight's edge, a sliver) takes the one that does, not a mean with the flight's
    median, which would pull an edge band half way to the level it differs from; where none of the four blocks around a
    cell counts it takes the flight's median, and the blocks' level fades into the flight's median as their total weight
    falls from 1/2 to 0, so no step appears where their support ends; where the flight itself is under `floor`, the valley's."""

    def __init__(self, cells, floor=BALANCE_FLOOR, inputs=None, blocks=None, block_m=BLOCK_M):
        self.floor = floor
        self.inputs = dict(inputs or {})
        self.block_m = float(block_m)
        self.cells = {k: (n, np.asarray(m, np.float32)) for k, (n, m) in cells.items()}
        self.blocks = {}                                    # (flight, gid) -> {(bx, by): (n, med)}
        for (f, g, bx, by), (n, m) in (blocks or {}).items():
            self.blocks.setdefault((f, g), {})[(bx, by)] = (n, np.asarray(m, np.float32))

    @classmethod
    def from_json(cls, doc):
        if not isinstance(doc, dict) or doc.get("schema") != FlightBalance.SCHEMA:
            raise ValueError(f"not a flight balance (schema {FlightBalance.SCHEMA!r})")
        cells, blocks = {}, {}
        for key, v in doc["cells"].items():
            f, _, g = key.partition(":")
            cells[(int(f), int(g))] = (int(v["n"]), v["med"])
        for key, v in doc.get("blocks", {}).items():
            f, g, bx, by = (int(p) for p in key.split(":"))
            blocks[(f, g, bx, by)] = (int(v["n"]), v["med"])
        return cls(cells, inputs=doc.get("inputs"), blocks=blocks, block_m=doc.get("block_m", BLOCK_M))

    def medians(self, fid, gt, default, xs=None, ds=None):
        """default (rows, cols, 3), the valley-wide median of each cell's type, with the reference of the cell's flight
        where its flight holds at least `floor` cells of the type. xs, ds: where the cells are (1-D, metres east and south
        of the grid's origin); without them the flight's median alone."""
        out = np.array(default, np.float32)
        f, g = np.asarray(fid).astype(np.int64), np.asarray(gt).astype(np.int64)
        B = self.block_m
        if xs is not None and ds is not None:
            u = np.asarray(xs, np.float64) / B - 0.5            # block centres sit at integers
            v = np.asarray(ds, np.float64) / B - 0.5
            iu, iv = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
            tu, tv = (u - iu).astype(np.float32), (v - iv).astype(np.float32)
        for fl in np.unique(f[f != NO_FLIGHT]):
            in_f = f == fl
            for ty in np.unique(g[in_f]):
                n, med = self.cells.get((int(fl), int(ty)), (0, None))
                if n < self.floor:
                    continue
                sel = in_f & (g == ty)
                blocks = self.blocks.get((int(fl), int(ty)))
                if not blocks or xs is None or ds is None:
                    out[sel] = med
                    continue
                rr, cc = np.nonzero(sel)
                u0, v0 = iu[cc], iv[rr]
                bx0, bx1, by0, by1 = int(u0.min()), int(u0.max()) + 1, int(v0.min()), int(v0.max()) + 1
                val = np.zeros((by1 - by0 + 1, bx1 - bx0 + 1, 3), np.float32)
                has = np.zeros(val.shape[:2], np.float32)
                for (bx, by), (bn, bm) in blocks.items():
                    if bn >= self.floor and bx0 <= bx <= bx1 and by0 <= by <= by1:
                        val[by - by0, bx - bx0], has[by - by0, bx - bx0] = bm, 1.0
                a, b = (u0 - bx0), (v0 - by0)
                wu, wv = tu[cc], tv[rr]
                num, den = 0.0, 0.0
                for da, db, w in ((0, 0, (1 - wu) * (1 - wv)), (1, 0, wu * (1 - wv)), (0, 1, (1 - wu) * wv), (1, 1, wu * wv)):
                    w = w * has[b + db, a + da]                      # a corner block short of the floor counts for nothing ...
                    num = num + w[:, None] * val[b + db, a + da]
                    den = den + w
                # ... and the valid blocks' level fades into the flight's median as their total weight falls from 1/2 to 0, so the
                # reference has no step where the valid blocks' support ends (cells beside a valid block keep its full level)
                s = np.clip(den / 0.5, 0.0, 1.0)
                s = (s * s * (3.0 - 2.0 * s))[:, None].astype(np.float32)
                ref = s * (num / np.maximum(den, 1e-6)[:, None]) + (1.0 - s) * med
                out[rr, cc] = ref
        return out


def confirm_cluster(ndvi, covered):
    """Crop clusters outside the fields (the crop cover's confidence 3) are painted only where the photo confirms
    them: it covers the cell and its NDVI is at least CLUSTER_NDVI."""
    return covered & (np.asarray(ndvi) >= CLUSTER_NDVI)


def decode_ndvi(band):
    """The COG's NDVI band (uint8, 1..255 for -1..+1, 0 = no flight polygon) as (ndvi float32, known bool)."""
    b = np.asarray(band, np.float32)
    return np.where(b > 0, (b - 1.0) / 127.0 - 1.0, np.nan).astype(np.float32), b > 0
