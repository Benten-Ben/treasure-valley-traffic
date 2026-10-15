"""roads-build's marks (ops.build_pending, migration 0021; M1): a source whose new data the real-width roads build
reads marks it, in the same transaction as its data (ingest/builds.py). The build runs by hand: `python3 -m ingest
roads-build`. Its inputs: osm_valley and osm_street (the carriageways), osm_paving (sidewalks and crossings; it
marks on its own), achd_roads (the segments pieces are matched to), the lane sources (itd_hpms, achd_msm,
compass_centerline), achd_bike_network (curb-to-curb widths), roads-developed-load (developed land; it marks on
its own), a segment-match by hand (the lanes rule's matches), and the intersections' daily rebuild when the
signals the build reads change (signals())."""

from ingest import builds

BUILD = "roads-build"
SIGNAL_CONTROLS = ("signal", "half_signal", "signal_uturn")     # the core.intersection controls the build reads


def ready(conn):
    return conn.execute("select to_regclass('ops.build_pending') is not null").fetchone()[0]


def mark(conn, source, changed, what="records"):
    """Mark roads-build when a load changed anything (changed: a count, or True). Doesn't commit. Before migration
    0021 it does nothing."""
    if not changed or not ready(conn):
        return False
    n = "" if changed is True else f"{changed:,} "
    builds.mark(conn, BUILD, by=source, reason=f"{source}: {n}{what} changed")
    return True


def signals(conn):
    """What roads-build reads of core.intersection (its junctions' kind, stop bars): the active signals' id, control
    and place, as a set. The intersections rebuild compares it before and after, and marks the build by what
    changed."""
    return set(conn.execute(
        """select id, control, ST_AsText(ST_SnapToGrid(geom, 0.000001)) from core.intersection
           where status = 'active' and control = any(%s)""", (list(SIGNAL_CONTROLS),)).fetchall())
