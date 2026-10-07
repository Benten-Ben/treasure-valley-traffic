"""UTM zone 11N (WGS84) in pure Python: lon/lat to metres and back.

Shared by the transit ribbons and the intersection build (both work in metres
in the valley). The Krueger series to n^6 is sub-millimetre in the zone, and
matches PostGIS's ST_Transform(..., 32611) (ingest/tests/test_utm.py).
Standard library only.
"""

import math

# -- UTM zone 11N (WGS84), Krueger series to n^6: sub-millimetre in the zone ------------------------------------

_A, _F = 6378137.0, 1 / 298.257223563
_N = _F / (2 - _F)
_E = math.sqrt(_F * (2 - _F))
_K0, _LON0, _E0 = 0.9996, math.radians(-117.0), 500000.0
_AA = _A / (1 + _N) * (1 + _N ** 2 / 4 + _N ** 4 / 64 + _N ** 6 / 256)
_n = _N
_ALPHA = (
    _n / 2 - 2 * _n ** 2 / 3 + 5 * _n ** 3 / 16 + 41 * _n ** 4 / 180 - 127 * _n ** 5 / 288 + 7891 * _n ** 6 / 37800,
    13 * _n ** 2 / 48 - 3 * _n ** 3 / 5 + 557 * _n ** 4 / 1440 + 281 * _n ** 5 / 630 - 1983433 * _n ** 6 / 1935360,
    61 * _n ** 3 / 240 - 103 * _n ** 4 / 140 + 15061 * _n ** 5 / 26880 + 167603 * _n ** 6 / 181440,
    49561 * _n ** 4 / 161280 - 179 * _n ** 5 / 168 + 6601661 * _n ** 6 / 7257600,
    34729 * _n ** 5 / 80640 - 3418889 * _n ** 6 / 1995840,
    212378941 * _n ** 6 / 319334400)
_BETA = (
    _n / 2 - 2 * _n ** 2 / 3 + 37 * _n ** 3 / 96 - _n ** 4 / 360 - 81 * _n ** 5 / 512 + 96199 * _n ** 6 / 604800,
    _n ** 2 / 48 + _n ** 3 / 15 - 437 * _n ** 4 / 1440 + 46 * _n ** 5 / 105 - 1118711 * _n ** 6 / 3870720,
    17 * _n ** 3 / 480 - 37 * _n ** 4 / 840 - 209 * _n ** 5 / 4480 + 5569 * _n ** 6 / 90720,
    4397 * _n ** 4 / 161280 - 11 * _n ** 5 / 504 - 830251 * _n ** 6 / 7257600,
    4583 * _n ** 5 / 161280 - 108847 * _n ** 6 / 3991680,
    20648693 * _n ** 6 / 638668800)


def to_utm(lon, lat):
    """WGS84 lon/lat to UTM 11N metres (EPSG:26911/32611 agree to centimetres here)."""
    phi, lam = math.radians(lat), math.radians(lon) - _LON0
    s = math.sin(phi)
    t = math.sinh(math.atanh(s) - _E * math.atanh(_E * s))
    xi_, eta_ = math.atan2(t, math.cos(lam)), math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi, eta = xi_, eta_
    for j, a in enumerate(_ALPHA, 1):
        xi += a * math.sin(2 * j * xi_) * math.cosh(2 * j * eta_)
        eta += a * math.cos(2 * j * xi_) * math.sinh(2 * j * eta_)
    return _E0 + _K0 * _AA * eta, _K0 * _AA * xi


def from_utm(x, y):
    """UTM 11N metres to WGS84 lon/lat."""
    xi, eta = y / (_K0 * _AA), (x - _E0) / (_K0 * _AA)
    xi_, eta_ = xi, eta
    for j, b in enumerate(_BETA, 1):
        xi_ -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        eta_ -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    tau_ = math.sin(xi_) / math.sqrt(math.sinh(eta_) ** 2 + math.cos(xi_) ** 2)
    lam = math.atan2(math.sinh(eta_), math.cos(xi_))
    tau = tau_
    for _ in range(10):
        sig = math.sinh(_E * math.atanh(_E * tau / math.sqrt(1 + tau * tau)))
        ti = tau * math.sqrt(1 + sig * sig) - sig * math.sqrt(1 + tau * tau)
        d = (tau_ - ti) / math.sqrt(1 + ti * ti) * (1 + (1 - _E * _E) * tau * tau) / (
            (1 - _E * _E) * math.sqrt(1 + tau * tau))
        tau += d
        if abs(d) < 1e-14:
            break
    return math.degrees(lam + _LON0), math.degrees(math.atan(tau))
