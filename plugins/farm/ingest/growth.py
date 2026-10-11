"""Which crop fields have been built over, or are being built (the farm design's growth rule). Standard library only.

From a field's CDL code per year (CSB's eight-year window) and the new-construction permits inside it:

- **built_over**: farmed (a crop, hay, fallow or pasture) in at least 2 of the window's first four years, developed
  (CDL 121-124) in its last two, and low, medium or high intensity (122-124) in the last. For the 2018-2025 edition:
  2 of 2018-21 farmed, developed in 2024 and 2025. 621 fields, 5,680 acres on Oct 8; 86% have a permit since 2018,
  against 3% of the fields still farmed through 2023-25.
- **being_built**: not built over, developed in the last year, farmed in at least one of the first four, and three or
  more new-construction permits inside it since the window began (about 407 on Oct 8).
- **farmed**: everything else (not flagged). A field developed in the last year without the permits isn't flagged;
  its detail says so, for the card.

The CDL's developed classes come from NLCD, so they step with NLCD's editions (2021, 2024): the year a field turned
developed is a "by" year, never a build date. `developed_by` is the first year of the run of developed years that
ends the window; the card says "by 2024", or gives the first permit's year.
"""

from . import classes as C

RULE = "growth/1"
EARLY_YEARS = 4                  # the window's first years, when the field must have been farmed
BUILT_CODES = frozenset((122, 123, 124))
MIN_PERMITS = 3


def classify(crops, first_year, classes, permits=None):
    """(growth, detail) for one field. crops: its CDL codes, one per year from first_year (0 for none).
    permits: None when unknown (no permits table), else {"n": count since first_year, "first": year, "last": year}."""
    crops = [int(c or 0) for c in crops]
    n = len(crops)
    if n < 2:
        raise ValueError("a field needs at least two years of codes")
    early = crops[:EARLY_YEARS]
    farmed_early = sum(1 for c in early if C.group_of(classes, c) in C.FARMED_GROUPS)
    k = n
    while k > 0 and crops[k - 1] in C.DEVELOPED:
        k -= 1
    detail = {"rule": RULE, "farmed_early": farmed_early,
              "early_years": [first_year, first_year + min(EARLY_YEARS, n) - 1]}
    if k < n:
        detail["developed_by"] = first_year + k
    if permits is not None:
        detail["permits"] = int(permits.get("n") or 0)
        if detail["permits"]:
            detail["permit_years"] = [permits.get("first"), permits.get("last")]
    else:
        detail["permits"] = None

    if farmed_early >= 2 and crops[-2] in C.DEVELOPED and crops[-1] in BUILT_CODES:
        return "built_over", detail
    if crops[-1] in C.DEVELOPED and farmed_early >= 1:
        if permits is not None and detail["permits"] >= MIN_PERMITS:
            return "being_built", detail
        detail["unconfirmed"] = ("developed in the newest map, without permits" if permits is not None
                                 else "developed in the newest map; permits not available")
    return "farmed", detail
