"""The photo statistics' arithmetic (plan P2; the soils design, build step 3). Worker image (NumPy, SciPy); no GDAL.

photo_stats.py decodes NAIP 2025 window by window and hands each window's pixels to this module, which
- turns the photo's 8-bit red, green and blue into OKLab (colour()), the space our colour checks use;
- puts the photo's NDVI on Sentinel-2's scale with its flight day's curve (Curve, from the same-day
  normalisation's fits.json, "band 4");
- decides which pixels are uncovered ground, the 'photo-v1' mask (sample_mask(), RULES below);
- accumulates, per key (a map unit and a flight day), the pixel count, OKLab sums and cross-products and 256-bin
  histograms (Accumulator), and the texture energy of L and chroma in five octaves (octaves());
- averages a window onto the ground's 2 m grid by area (overlap()), for the NAIP COG G1b reads.

pool.py turns the sums into medians, covariances and the ground types' pooled numbers.

**Texture energy** (the soils design: "isotropic difference-of-Gaussians energy of L and chroma at 1.2-19.2 m,
counted only where 75% of the support is uncovered"). For a channel X and the uncovered mask U, S_s is the masked
Gaussian blur of X at sigma s, G_s*(X U) / G_s*U, so covered pixels never leak in. Octave k (k = 1..5, OCTAVES_M
1.2, 2.4, 4.8, 9.6 and 19.2 m) is the band D_k = S_{s_k/2} - S_{s_k}, and its energy is the mean of D_k^2 over the
points where U holds and G_{s_k}*U is at least SUPPORT (0.75). It's computed on a pyramid: band k on a grid of
0.6 * 2^(k-1) m (the photo's 0.6 m pixels, then 2 x 2 means), where both blurs are 1 and 2 pixels, so each band
costs the same and the whole pyramid about 1.3 times its finest level. octave_energy() is the same measure on any
array; the ground's texture (G1b) measures its own noise with it, so the two agree by construction.
"""

import numpy as np
from scipy import ndimage, sparse

# ---- the photo-v1 rules (the soils design, build step 3) ----------------------------------------------------------

GREEN_CUT = 0.45       # the photo's NDVI on Sentinel-2's scale: at or above it, green (the land-cover spike's one
                       # green cut, exp31: Otsu's split of the boxes' low cells; Youden's best against July is 0.40)
JULY_CUT = 0.30        # the July 2025 Sentinel-2 NDVI median (10 m): at or above it, green in July
EDGE_M = 10.0          # a pixel counts only this far inside its soil polygon (SSURGO lines are about +-12 m)
# Shadow and asphalt: dark, and blue-shifted or neutral (OKLab). Measured on the ten boxes' classes (calibrate).
DARK_L = 0.50          # OKLab L under this is dark ⚠️ (the boxes' asphalt and shadows sit under it, soils above)
NEUTRAL_C = 0.025      # OKLab chroma under this is neutral ⚠️
BLUE_B = 0.0           # OKLab b under this is blue-shifted (shadow is lit by the blue sky) ⚠️
# Inside crop fields only row crops and fallow show soil in a June photo; stubble, hay and pasture aren't soil.
# Farm's crop_cover group codes (plugins/farm/ingest/classes.py COVER_CODES): 1 corn, 4 roots (beets, beans,
# potatoes, onions, vegetables), 6 fallow are kept; 2 hay, 3 grain, 5 specialty (mint, hops, seed, orchards) not.
COVER_KEEP = (0, 1, 4, 6)
FIELD_DROP_GROUPS = ("hay", "grain", "specialty", "pasture")   # a crop field's group (CSB's code) that is dropped

RULES = {
    "green_cut_s2": GREEN_CUT, "july_cut": JULY_CUT, "edge_m": EDGE_M, "dark_l": DARK_L, "neutral_c": NEUTRAL_C,
    "blue_b": BLUE_B, "cover_keep": list(COVER_KEEP), "field_drop_groups": list(FIELD_DROP_GROUPS),
}



def configure(**rules):
    """Change the dark rule's cuts (dark_l, neutral_c, blue_b) for this process, e.g. for a calibration sweep. A run
    records the rules it used (RULES)."""
    global DARK_L, NEUTRAL_C, BLUE_B
    for k, v in rules.items():
        if v is None:
            continue
        if k == "dark_l":
            DARK_L = float(v)
        elif k == "neutral_c":
            NEUTRAL_C = float(v)
        elif k == "blue_b":
            BLUE_B = float(v)
        else:
            raise PhotoError(f"no rule {k!r} to configure")
        RULES[k] = float(v)


# Why a pixel isn't sampled, in the order sample_mask() tests them (each pixel is counted under its first reason).
REASONS = ("outside", "no_polygon", "edge", "covered", "no_flight", "no_july", "green", "dark", "crop")

# ---- texture ------------------------------------------------------------------------------------------------------

OCTAVES_M = (1.2, 2.4, 4.8, 9.6, 19.2)
SUPPORT = 0.75
TRUNCATE = 3.0         # Gaussian kernels are cut at 3 sigma
HALO_M = 64.0          # how far a window must reach past its core: the 19.2 m blur's 3 sigma, plus the 10 m edge rule
                       # fits inside it too

# ---- histograms ---------------------------------------------------------------------------------------------------

BINS = 256
RANGES = ((0.0, 1.0), (-0.25, 0.25), (-0.25, 0.25))   # L, a, b: bin widths 0.0039 and 0.002 (dE 0.4 and 0.2)
SUMS = ("L", "a", "b", "LL", "La", "Lb", "aa", "ab", "bb")


class PhotoError(ValueError):
    pass


# ---- colour -------------------------------------------------------------------------------------------------------

def _srgb_lut():
    c = np.arange(256, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


_LIN = _srgb_lut()
_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]], np.float32)
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]], np.float32)


def colour(r, g, b):
    """OKLab (L, a, b) as float32 arrays from 8-bit sRGB arrays (the photo's DNs read as sRGB, as the map shows them;
    the same matrices as app/src/lib/map/color.ts and plugins/transit/ingest/route_colors.py)."""
    return colour_linear(_LIN[r], _LIN[g], _LIN[b])


def colour_linear(lr, lg, lb):
    """OKLab (L, a, b) as float32 arrays from linear-light red, green and blue (0..1)."""
    lms = [np.cbrt(_M1[i, 0] * lr + _M1[i, 1] * lg + _M1[i, 2] * lb) for i in range(3)]
    return tuple((_M2[i, 0] * lms[0] + _M2[i, 1] * lms[1] + _M2[i, 2] * lms[2]).astype(np.float32) for i in range(3))


def srgb_to_linear(dn):
    """Linear light (0..1) of sRGB values given as DNs (0..255, any float)."""
    c = np.asarray(dn, np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---- colour gains per flight day ----------------------------------------------------------------------------------

GAINS_FORMAT = "tvt-naip-colour-gains/1"
GAIN_BANDS = ("red", "green", "blue")


class Gains:
    """The per-flight colour gains (the soils design: "only if the same type differs by more than dE 3 across flights
    ... fit per-flight gains"). NAIP 2025 was flown on four days in Ada and Canyon, and each day's colour sits on its
    own scale. gains.json (the one-off colour read beside naip_norm: same-day Sentinel-2 L2A blue, green and red) has,
    per flight day and band, a table from the photo's DN (0..255) to the DN the reference day (June 18, 63% of the
    photo) would have recorded for the same reflectance. The reference day's table is the identity, and a pixel with
    no flight day (index 0) is left as it is. Tables are kept as floats: the statistics and the COG's area means
    don't round to whole DNs on the way."""

    def __init__(self, doc, days):
        if doc.get("format") != GAINS_FORMAT:
            raise PhotoError(f"gains: format {doc.get('format')!r}, not {GAINS_FORMAT}")
        self.reference = doc.get("reference_day")
        lut = np.tile(np.arange(256, dtype=np.float64), (len(days) + 1, 3, 1))
        for i, d in enumerate(days, start=1):
            entry = (doc.get("days") or {}).get(d)
            if entry is None:
                raise PhotoError(f"gains: no tables for flight day {d}")
            for c, band in enumerate(GAIN_BANDS):
                v = np.asarray(entry["lut"][band], np.float64)
                if (v.shape != (256,) or not np.isfinite(v).all() or np.any(np.diff(v) < -1e-9) or v.min() < 0
                        or v.max() > 255):
                    raise PhotoError(f"gains: {d} {band}: a table is 256 values in 0..255 that never fall")
                lut[i, c] = v
        self.days = list(days)
        self.dn = lut.astype(np.float32)
        self.lin = srgb_to_linear(lut).astype(np.float32)

    def apply(self, flight, r, g, b):
        """((red, green, blue) as DNs on the reference day's scale; the same in linear light), float32 arrays, for
        8-bit arrays and the flight index (0 none, i for days[i - 1])."""
        f = np.asarray(flight).astype(np.intp)
        dn = tuple(self.dn[f, c, v] for c, v in enumerate((r, g, b)))
        lin = tuple(self.lin[f, c, v] for c, v in enumerate((r, g, b)))
        return dn, lin


def oklab_to_srgb(lab):
    """8-bit sRGB (r, g, b) of one OKLab colour, clipped (for reports and quick looks)."""
    L, a, b = (float(v) for v in lab)
    lms = [(L + 0.3963377774 * a + 0.2158037573 * b) ** 3, (L - 0.1055613458 * a - 0.0638541728 * b) ** 3,
           (L - 0.0894841775 * a - 1.2914855480 * b) ** 3]
    m = ((4.0767416621, -3.3077115913, 0.2309699292), (-1.2684380046, 2.6097574011, -0.3413193965),
         (-0.0041960863, -0.7034186147, 1.7076147010))
    out = []
    for row in m:
        c = min(1.0, max(0.0, sum(k * v for k, v in zip(row, lms))))
        c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(int(round(c * 255)))
    return tuple(out)


def delta_e(p, q):
    """OKLab distance x 100, the unit of every colour check (docs/14)."""
    return 100.0 * float(np.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(p, q))))


def ndvi(nir, red):
    """The photo's own NDVI from its DNs (0 where both are 0), float32."""
    nir = nir.astype(np.float32)
    red = red.astype(np.float32)
    s = nir + red
    out = np.zeros(s.shape, np.float32)
    np.divide(nir - red, s, out=out, where=s > 0)
    return out


class Curve:
    """A flight day's monotone curve from the photo's NDVI to Sentinel-2's (naip_norm's fits.json, "band 4":
    `naip2025.days.<day>.curve.lut_x/lut_y`, linear between the steps)."""

    def __init__(self, lut_x, lut_y, name=""):
        x, y = np.asarray(lut_x, np.float64), np.asarray(lut_y, np.float64)
        if x.ndim != 1 or x.shape != y.shape or len(x) < 2 or np.any(np.diff(x) <= 0):
            raise PhotoError(f"curve {name!r}: lut_x must rise and match lut_y")
        if np.any(np.diff(y) < 0):
            raise PhotoError(f"curve {name!r}: lut_y must not fall")
        self.x, self.y, self.name = x, y, name

    def __call__(self, v):
        return np.interp(v, self.x, self.y).astype(np.float32)


def normalised_ndvi(raw, flight, curves):
    """The photo's NDVI on Sentinel-2's scale: each pixel through its flight's curve (flight: an index array, 0 for
    no flight, curves[i - 1] for flight i). NaN where there's no flight."""
    out = np.full(raw.shape, np.nan, np.float32)
    for i, c in enumerate(curves, start=1):
        sel = flight == i
        if sel.any():
            out[sel] = c(raw[sel])
    return out


def encode_ndvi(v):
    """NDVI as a byte for the 2 m COG: 1..255 is -1..+1 in steps of 1/127, 0 is none (NaN)."""
    v = np.asarray(v, np.float32)
    code = np.clip(np.rint(v * 127.0) + 128.0, 1, 255)
    return np.where(np.isnan(v), 0, code).astype(np.uint8)


def decode_ndvi(code):
    code = np.asarray(code)
    return np.where(code == 0, np.nan, (code.astype(np.float32) - 128.0) / 127.0)


# ---- the photo-v1 mask --------------------------------------------------------------------------------------------

def inner(pid, res, edge_m=EDGE_M):
    """True where every pixel within edge_m (along the rows and columns, so at least edge_m in any direction) has the
    same polygon id, and that id isn't 0: at least edge_m inside the polygon, no buffer for slivers."""
    r = int(np.ceil(edge_m / res - 1e-9))
    size = 2 * r + 1
    hi = ndimage.maximum_filter(pid, size=size, mode="nearest")
    lo = ndimage.minimum_filter(pid, size=size, mode="nearest")
    return (hi == lo) & (pid > 0)


def dark(L, a, b):
    """Shadow or asphalt: dark, and neutral or blue-shifted (DARK_L, NEUTRAL_C, BLUE_B)."""
    C = np.hypot(a, b)
    return (L < DARK_L) & ((C < NEUTRAL_C) | (b < BLUE_B))


def sample_mask(valid, pid, inner_ok, covered, flight, ndvi_s2, july, L, a, b, crop_ok):
    """The photo-v1 mask: True where a pixel is sampled as uncovered ground. All arguments are arrays of one shape:
    valid (inside the county mosaic), pid (soil polygon, 0 none), inner_ok (inner()), covered (mask v0's sampling
    mask), flight (0 none), ndvi_s2 (normalised_ndvi()), july (the July median, NaN none), L, a, b, crop_ok.
    Returns (mask, first reason per pixel as an index into REASONS, -1 when sampled)."""
    why = np.full(valid.shape, -1, np.int8)
    tests = (~valid, pid == 0, ~inner_ok, covered, flight == 0, np.isnan(july),
             (ndvi_s2 >= GREEN_CUT) | (july >= JULY_CUT), dark(L, a, b), ~crop_ok)
    for i, t in enumerate(tests):
        why[(why < 0) & t] = i
    return why < 0, why


def crop_ok(cover_group, field_group_drop):
    """True where the crop rule keeps a pixel: farm's crop_cover group (10 m) is none, corn, roots or fallow, and the
    pixel isn't in a crop field whose group is dropped (field_group_drop, a bool array)."""
    return np.isin(cover_group, COVER_KEEP) & ~field_group_drop


# ---- accumulators -------------------------------------------------------------------------------------------------

def bins(v, channel):
    lo, hi = RANGES[channel]
    i = np.floor((v - lo) * (BINS / (hi - lo))).astype(np.int64)
    return np.clip(i, 0, BINS - 1)


class Accumulator:
    """Sums per integer key: n, the OKLab sums and cross-products (SUMS), a BINS-bin histogram per channel, and the
    texture sums per octave (count, sum of D^2 for L and for chroma). Keys are rows; only rows used are stored."""

    def __init__(self, nkeys, hist_dtype=np.int64):
        self.nkeys = nkeys
        self.n = np.zeros(nkeys, np.int64)
        self.s = np.zeros((nkeys, len(SUMS)), np.float64)
        self.h = np.zeros((nkeys, 3, BINS), hist_dtype)
        self.tn = np.zeros((nkeys, len(OCTAVES_M)), np.int64)
        self.tl = np.zeros((nkeys, len(OCTAVES_M)), np.float64)
        self.tc = np.zeros((nkeys, len(OCTAVES_M)), np.float64)

    def add(self, key, L, a, b):
        """Add pixels (1-D arrays of one length)."""
        if key.size == 0:
            return
        k = self.nkeys
        self.n += np.bincount(key, minlength=k)
        L64, a64, b64 = L.astype(np.float64), a.astype(np.float64), b.astype(np.float64)
        for j, w in enumerate((L64, a64, b64, L64 * L64, L64 * a64, L64 * b64, a64 * a64, a64 * b64, b64 * b64)):
            self.s[:, j] += np.bincount(key, weights=w, minlength=k)
        for c, v in enumerate((L, a, b)):
            self.h[:, c, :] += np.bincount(key * BINS + bins(v, c), minlength=k * BINS).reshape(k, BINS).astype(
                self.h.dtype)

    def add_texture(self, octave, key, d_l, d_c):
        if key.size == 0:
            return
        k = self.nkeys
        self.tn[:, octave] += np.bincount(key, minlength=k)
        self.tl[:, octave] += np.bincount(key, weights=d_l.astype(np.float64) ** 2, minlength=k)
        self.tc[:, octave] += np.bincount(key, weights=d_c.astype(np.float64) ** 2, minlength=k)

    def used(self):
        return np.nonzero((self.n > 0) | (self.tn.sum(axis=1) > 0))[0]

    def sparse(self, prefix="", labels=None):
        """The used rows, for np.savez: {prefix + name: array}. labels: each row's key when the rows are local
        indices (a window's own keys)."""
        rows = self.used()
        keys = rows if labels is None else np.asarray(labels)[rows]
        return {prefix + "keys": keys.astype(np.int64), prefix + "n": self.n[rows], prefix + "s": self.s[rows],
                prefix + "h": self.h[rows], prefix + "tn": self.tn[rows], prefix + "tl": self.tl[rows],
                prefix + "tc": self.tc[rows]}

    def merge(self, z, prefix="", keymap=None):
        """Add a sparse() dict (or an npz) into this one. keymap maps its keys to ours (an array), when they differ."""
        rows = z[prefix + "keys"]
        if keymap is not None:
            rows = keymap[rows]
        np.add.at(self.n, rows, z[prefix + "n"])
        np.add.at(self.s, rows, z[prefix + "s"])
        np.add.at(self.h, rows, z[prefix + "h"].astype(self.h.dtype))
        np.add.at(self.tn, rows, z[prefix + "tn"])
        np.add.at(self.tl, rows, z[prefix + "tl"])
        np.add.at(self.tc, rows, z[prefix + "tc"])


def hist_quantile(h, q, channel):
    """A quantile of one channel from its histogram (linear within the bin), or None for an empty histogram."""
    h = np.asarray(h, np.float64)
    total = h.sum()
    if total <= 0:
        return None
    lo, hi = RANGES[channel]
    width = (hi - lo) / BINS
    cum = np.cumsum(h)
    target = q * total
    i = int(np.searchsorted(cum, target, side="left"))
    i = min(i, BINS - 1)
    before = cum[i - 1] if i > 0 else 0.0
    frac = (target - before) / h[i] if h[i] > 0 else 0.5
    return float(lo + (i + min(max(frac, 0.0), 1.0)) * width)


def stats(n, s, h):
    """Medians, covariance (upper triangle LL, La, Lb, aa, ab, bb) and L p10/p90 from one row's sums."""
    if n <= 0:
        return None
    mean = s[:3] / n
    second = np.array([s[3], s[4], s[5], s[6], s[7], s[8]]) / n
    idx = ((0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2))
    cov = [float(second[k] - mean[i] * mean[j]) * (n / (n - 1) if n > 1 else 1.0) for k, (i, j) in enumerate(idx)]
    return {"n": int(n), "mean": [float(v) for v in mean], "med": [hist_quantile(h[c], 0.5, c) for c in range(3)],
            "cov": cov, "l_p10": hist_quantile(h[0], 0.10, 0), "l_p90": hist_quantile(h[0], 0.90, 0)}


def energies(tn, tl, tc):
    """Mean texture energy per octave for L and for chroma (None where no point counted)."""
    out_l = [float(tl[k] / tn[k]) if tn[k] > 0 else None for k in range(len(OCTAVES_M))]
    out_c = [float(tc[k] / tn[k]) if tn[k] > 0 else None for k in range(len(OCTAVES_M))]
    return out_l, out_c


# ---- texture ------------------------------------------------------------------------------------------------------

def _blur(a, sigma):
    return ndimage.gaussian_filter(a, sigma, mode="constant", cval=0.0, truncate=TRUNCATE)


def _ratio(n, d):
    out = np.zeros(n.shape, np.float32)
    np.divide(n, d, out=out, where=d > 1e-6)
    return out


def _down(a):
    """2 x 2 means (the array's sides are even)."""
    h, w = a.shape
    return a.reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3), dtype=np.float32)


def octaves(channels, U, res):
    """The texture bands of each channel over the mask U (a bool or 0..1 array): yields (k, level_pixel_m, bands,
    counted), one per octave k = 0..4, where bands[i] is channel i's band D_k on that level's grid and counted says
    where it counts. A level's pixel (r, c) covers the input's pixels [r * 2^k, (r + 1) * 2^k). The input's sides
    must be multiples of 16 (pad with U = 0)."""
    h, w = U.shape
    if h % 16 or w % 16:
        raise PhotoError(f"octaves() needs sides that are multiples of 16, not {U.shape}")
    U = U.astype(np.float32)
    nums = [np.asarray(x, np.float32) * U for x in channels]
    den = U
    u_level = U
    sigma = 0.0                       # the blur so far, in this level's pixels
    for k in range(len(OCTAVES_M)):
        if sigma < 1.0:               # the finer blur: 1 pixel (on coarser levels the 2 x 2 means leave about 1.03)
            inc = np.sqrt(1.0 - sigma * sigma)
            nums = [_blur(x, inc) for x in nums]
            den = _blur(den, inc)
            sigma = 1.0
        s_a = [_ratio(x, den) for x in nums]
        inc = np.sqrt(4.0 - sigma * sigma)                     # the coarser blur: 2 pixels
        nums = [_blur(x, inc) for x in nums]
        den = _blur(den, inc)
        s_b = [_ratio(x, den) for x in nums]
        counted = (u_level >= 0.5) & (den >= SUPPORT)
        yield k, res * (2 ** k), [a - b for a, b in zip(s_a, s_b)], counted
        if k + 1 < len(OCTAVES_M):
            nums = [_down(x) for x in nums]
            den = _down(den)
            u_level = _down(u_level)
            sigma = np.sqrt(4.0 + 0.25) / 2.0      # 2 pixels, then a 2 x 2 mean (variance 1/4), in the new pixels


def octave_energy(x, U, res=0.6):
    """Mean D_k^2 per octave of one channel over the whole array (see the module docstring), or None where nothing
    counts. For G1b's noise and the tests."""
    h, w = U.shape
    ph, pw = (-h) % 16, (-w) % 16
    if ph or pw:
        x = np.pad(np.asarray(x, np.float32), ((0, ph), (0, pw)))
        U = np.pad(np.asarray(U), ((0, ph), (0, pw)))
    out = []
    for _, _, bands, counted in octaves([x], U, res):
        d = bands[0][counted]
        out.append(float(np.mean(d.astype(np.float64) ** 2)) if d.size else None)
    return out


# ---- the 2 m grid -------------------------------------------------------------------------------------------------

def overlap(src_start, src_res, n_src, dst_start, dst_res, n_dst):
    """A sparse matrix (n_dst x n_src) of the length each source cell shares with each target cell, along one axis.
    Starts are the first cell's edge, and both axes run the same way (east, or south as distance from a northing)."""
    per = int(np.ceil(dst_res / src_res)) + 2
    j = np.repeat(np.arange(n_dst), per)
    first = np.floor((dst_start + np.arange(n_dst) * dst_res - src_start) / src_res).astype(np.int64)
    k = (first[:, None] + np.arange(per)[None, :]).ravel()
    lo = np.maximum(dst_start + j * dst_res, src_start + k * src_res)
    hi = np.minimum(dst_start + (j + 1) * dst_res, src_start + (k + 1) * src_res)
    length = hi - lo
    keep = (length > 1e-9) & (k >= 0) & (k < n_src)
    return sparse.csr_matrix((length[keep].astype(np.float32), (j[keep], k[keep])), shape=(n_dst, n_src))


def area_sum(Ay, Ax, v):
    """The sum of v times the area each source cell shares with each target cell: Ay @ v @ Ax.T, as float64. Ay is
    applied first, so the large array is read once."""
    t = Ay @ np.asarray(v, np.float32)                   # (target rows, source columns)
    return np.asarray(Ax @ t.T, np.float64).T
