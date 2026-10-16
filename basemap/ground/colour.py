"""Colour for the painter: sRGB and OKLab (Björn Ottosson's, 2020, the space soils' palette is measured in), and the
ground's tokens. NumPy only.

The painter blends and feathers in OKLab, where a straight mix looks even, and writes sRGB. Soils' palette gives each
ground type's OKLab median as measured from NAIP 2025 (on the June 18 flight's scale), never styled: the ground paints
it as it is (the photo's own colours; plan §1), and the tokens below are the ground band's and the materials' from the
plan's §3.4.
"""

import numpy as np

# The ground band's extremes and the materials (plan §3.4; docs/13's tokens), in sRGB hex.
TOKENS = {
    "flat_valley": "#eee7da",      # today's flat Valley ground (spec.json "flat")
    "lawn": "#748357",             # the ground band's lawn extreme
    "bare": "#b9a07f",             # ... its bare extreme
    "asphalt": "#989088",          # the materials' asphalt (Valley)
    "concrete": "#d2cec6",         # ... concrete
    "pale_lot": "#f7edd6",         # the band's pale lot extreme
    "cream": "#fffbf4",            # markings' cream: gravel is cream at 35% over the ground
    "umber": "#6f5a43",            # dirt: umber at 18% over the ground (the trails' umber family)
}


def hex_rgb(h):
    """'#rrggbb' -> (r, g, b) in 0..255."""
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M2_INV = np.linalg.inv(_M2)
_M1_INV = np.linalg.inv(_M1)


def rgb_to_oklab(rgb):
    """sRGB in 0..255 (..., 3) -> OKLab (..., 3)."""
    lin = srgb_to_linear(np.asarray(rgb, np.float64) / 255.0)
    lms = lin @ _M1.T
    return np.cbrt(lms) @ _M2.T


def oklab_to_rgb(lab):
    """OKLab (..., 3) -> sRGB in 0..255 as float (..., 3), clipped to the gamut."""
    lms_ = np.asarray(lab, np.float64) @ _M2_INV.T
    lin = (lms_ ** 3) @ _M1_INV.T
    return linear_to_srgb(lin) * 255.0


def oklab_to_rgb8(lab):
    """OKLab (..., 3) -> sRGB uint8 (..., 3)."""
    return np.clip(np.rint(oklab_to_rgb(lab)), 0, 255).astype(np.uint8)


def token_lab(name):
    """A token's OKLab, (3,)."""
    return rgb_to_oklab(np.array(hex_rgb(TOKENS[name]), float))


def mix(a, b, t):
    """a + t (b - a), in whatever space a and b are in (OKLab here)."""
    return np.asarray(a) + np.asarray(t)[..., None] * (np.asarray(b) - np.asarray(a)) \
        if np.ndim(t) else np.asarray(a) + t * (np.asarray(b) - np.asarray(a))


def delta_e(a, b):
    """OKLab distance x 100 (the dE the soils palette's checks use)."""
    return 100.0 * np.linalg.norm(np.asarray(a, float) - np.asarray(b, float), axis=-1)
