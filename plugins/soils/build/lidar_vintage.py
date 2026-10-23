"""Each test box's lidar vintage, for the calibration report (DECISIONS 2026-10-22, answer 1).

The 2023-24 QL1 gap-fill project covers six boxes (b, c, d, downtown, f, h). Boxes a, e, i and j keep their 2019-20
QL2 lidar (e is on the 2019-20 QL2 survey, 2+ points/m2; docs/09-base-map-data.md). Fits that need one vintage use the
six 2023 boxes; a, e, i and j are held-out checks. Pure functions, no GDAL, so the test runs anywhere.
"""

VINTAGE_2023 = "2023-24 QL1"
VINTAGE_2019 = "2019-20 QL2"

BOX_VINTAGE = {
    "a": VINTAGE_2019, "e": VINTAGE_2019, "i": VINTAGE_2019, "j": VINTAGE_2019,
    "b": VINTAGE_2023, "c": VINTAGE_2023, "d": VINTAGE_2023, "downtown": VINTAGE_2023,
    "f": VINTAGE_2023, "h": VINTAGE_2023,
}

HELD_OUT = ("a", "e", "i", "j")


def lidar_vintage(box_id):
    """The box's lidar vintage label, or 'unknown' for a box this table doesn't list."""
    return BOX_VINTAGE.get(box_id, "unknown")


def vintage_table(rows):
    """A text table for the report: one line per box with its lidar vintage in a column of its own.

    rows: iterable of (box_id, value) pairs; value is printed as-is ('-' when None)."""
    lines = [f"{'box':<9}{'lidar':<14}{'use':<11}{'value'}"]
    for box_id, value in rows:
        use = "held-out" if box_id in HELD_OUT else "fit"
        shown = "-" if value is None else value
        lines.append(f"{box_id:<9}{lidar_vintage(box_id):<14}{use:<11}{shown}")
    return "\n".join(lines)
