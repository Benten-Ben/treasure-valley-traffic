"""The crop fields' licences and credits, built from the years the data rests on. Standard library only (the worker
build imports it too).

The Sentinel-2 year is the July NDVI median's own, which build.py reads from the raster's tags, never the crop year:
until a newer July median is made, a 2026 crop year still shows July 2025's state, credited as 2025.
"""

from .sources import nass_cdl, nass_csb

SENTINEL_LICENSE = "Copernicus (Sentinel-2)"
NASS_LICENSE = "public domain (USDA NASS CSB, CDL)"
COMPASS_LICENSE = "none stated (COMPASS permits and plats)"
COMPASS_CREDIT = "COMPASS (permits and plats)"


def years(ys):
    """'2025', or '2024, 2025' for several."""
    return ", ".join(str(y) for y in sorted(set(ys)))


def sentinel(july_years):
    """The Copernicus credit for the July NDVI of these years (one int or several)."""
    ys = [july_years] if isinstance(july_years, int) else list(july_years)
    if not ys:
        raise ValueError("a Sentinel-2 credit needs the NDVI's year")
    return f"Contains modified Copernicus Sentinel data {years(ys)}"


def csb(first, last):
    return f"{nass_csb.SOURCE['credit']} {first}-{last}"


def cdl(year=None):
    return nass_cdl.SOURCE["credit"] + (f" {year}" if year else "")


def build(csb_years, cover_year, july_year):
    """A build's credit: crop_cover.tif's CREDIT tag and farm.build.credit."""
    return "; ".join((csb(*csb_years), cdl(cover_year), sentinel(july_year)))


BUILD_LICENSE = f"{NASS_LICENSE}; {SENTINEL_LICENSE}"


def tiles(csb_years=None, july_years=(), compass=True):
    """(licence, credit) of the crop-fields tiles: CSB's window, the July years their states come from (none before a
    build is loaded), and COMPASS when its permits or plats were joined."""
    lic, cred = [NASS_LICENSE], [(csb(*csb_years) if csb_years else nass_csb.SOURCE["credit"])
                                 + " and " + cdl()]
    if july_years:
        lic.append(SENTINEL_LICENSE)
        cred.append(sentinel(july_years))
    if compass:
        lic.append(COMPASS_LICENSE)
        cred.append(COMPASS_CREDIT)
    return "; ".join(lic), "; ".join(cred)
