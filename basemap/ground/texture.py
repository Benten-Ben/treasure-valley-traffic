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


def confirm_cluster(ndvi, covered):
    """Crop clusters outside the fields (the crop cover's confidence 3) are painted only where the photo confirms
    them: it covers the cell and its NDVI is at least CLUSTER_NDVI."""
    return covered & (np.asarray(ndvi) >= CLUSTER_NDVI)


def decode_ndvi(band):
    """The COG's NDVI band (uint8, 1..255 for -1..+1, 0 = no flight polygon) as (ndvi float32, known bool)."""
    b = np.asarray(band, np.float32)
    return np.where(b > 0, (b - 1.0) / 127.0 - 1.0, np.nan).astype(np.float32), b > 0
