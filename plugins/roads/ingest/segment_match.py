"""Which ACHD road segments a source's lines lie along (core.segment_match; docs/12).

Used by itd_hpms, achd_msm, compass_centerline and osm_valley after each run
that changes them, and for all of them after achd_roads changes ACHD's
segments (rematch_all). One source line can lie along many ACHD segments,
and one segment can carry several lines: HPMS's A and D routes and other
divided carriageways are two lines along one ACHD centerline, and both match
it.

The matching itself is core's line matcher (ingest/linematch.py, moved there
in the landscape sprint so trails and water can use it too), with ACHD's
active segments as the targets. Its rules are unchanged since Oct 6: at least
60% of the ACHD segment within the line's buffer, or else at least 60% of a
line of 20 m or more within the segment's buffer ('way_in_' methods), checked
by bearing (within 20°) or, for the Master Street Map, by street name. Two
methods, by name:

- buffer15_bearing20: a 15 m buffer and the bearing check (HPMS, COMPASS,
  OpenStreetMap);
- buffer10_name: a 10 m buffer and the name check (the Master Street Map);
  where the names can't be compared, the bearing decides and the method says
  so (buffer10_bearing20).

share and overlap_m always measure the ACHD segment (0011). What stays here
is ACHD's part: writing core.segment_match, the stats, the staleness check
and rematching every source.

Rematching deletes and rewrites a source's matches in one transaction (the
caller commits). Canyon County has no ACHD segments, so its lines stay
unmatched and keep their own geometry; the stats say how many unmatched
lines lie away from ACHD's network (no segment within 50 m) and how many lie
near it (real misses).

By hand: python3 -m ingest segment-match [itd_hpms achd_msm compass_centerline osm_valley]
"""

import sys
import traceback

from ingest import linematch
# The rules, under the names roads' sources and tests have used since Oct 6.
from ingest.linematch import (BUFFER, MAX_BEARING, MIN_LINE_M, MIN_PROJECTED, MIN_SHARE, SRID, WAY_IN,  # noqa: F401
                              bearing_diff, names_agree, normalize_name, route_numbers)

NEAR_NETWORK_M = linematch.NEAR_NETWORK_M
SEGMENTS_SQL = "select id, name, geom from core.road_segment where active"

METHODS = {
    "buffer15_bearing20": {"near_m": 15, "check": "bearing"},
    "buffer10_name": {"near_m": 10, "check": "name"},
}


def _rule(method):
    return linematch.Rule(**METHODS[method])


def decide(c, method):
    """Whether a candidate is a match under one of METHODS, from its measurements
    (linematch.decide, with the ACHD segment's name as seg_name and the line's as
    src_name). Returns (bearing_diff or None, confidence, method) for a match, else None."""
    return linematch.decide({**c, "target_name": c.get("seg_name"), "line_name": c.get("src_name")}, _rule(method))


def candidates(conn, lines_sql, params=None, near_m=15, segments_sql=None):
    """Measure every (ACHD segment, source line) pair that passes either share.

    lines_sql selects source, source_id, geom (SRID 4326) and name, one row per
    (source, source_id). segments_sql (for tests) replaces the ACHD segments: it
    selects id, name, geom. Returns linematch.candidates()'s dicts with the
    segment as road_segment_id and seg_name, and the line's name as src_name.
    """
    out = []
    for c in linematch.candidates(conn, lines_sql, segments_sql or SEGMENTS_SQL, params,
                                  linematch.Rule(near_m=near_m)):
        c = dict(c)
        c["road_segment_id"], c["seg_name"], c["src_name"] = c.pop("target_id"), c.pop("target_name"), c.pop("line_name")
        out.append(c)
    return out


def rematch(conn, sources, lines_sql, params=None, method="buffer15_bearing20", segments_sql=None):
    """Delete and rewrite the matches of `sources` (a list of source names) from
    the lines lines_sql selects. Doesn't commit: the caller does, so the delete
    and the rewrite land together. Returns stats per source."""
    found = linematch.match(conn, lines_sql, segments_sql or SEGMENTS_SQL, _rule(method), params)
    rows = [(m["target_id"], m["source"], m["source_id"], round(m["overlap_m"], 1), round(min(m["share"], 1.0), 3),
             m["bearing_diff"], m["method"], m["confidence"]) for m in found]
    conn.execute("delete from core.segment_match where source = any(%s)", (list(sources),))
    with conn.cursor() as cur:
        cur.executemany(
            """insert into core.segment_match (road_segment_id, source, source_id, overlap_m, share, bearing_diff,
                 method, confidence, matched_at)
               values (%s, %s, %s, %s, %s, %s, %s, %s, now())""", rows)
    stats = {}
    for source, s in linematch.coverage(conn, found, NEAR_NETWORK_M).items():
        stats[source] = {"lines": s["lines"], "matched lines": s["matched lines"], "matches": s["matches"],
                         "unmatched near ACHD": s["unmatched near"], "unmatched away from ACHD": s["unmatched away"]}
        if s["matches"]:
            stats[source].update({"ACHD segments": s["targets"],
                                  "matches on the line's share": s["matches on the line's share"]})
    return stats


def summary(stats):
    """Per-source stats added up, for a one-line report."""
    keys = ("lines", "matched lines", "matches", "matches on the line's share", "ACHD segments",
            "unmatched near ACHD", "unmatched away from ACHD")
    total = {k: sum(s.get(k, 0) for s in stats.values()) for k in keys}
    total["match rate"] = f"{100 * total['matched lines'] / total['lines']:.1f}%" if total["lines"] else "-"
    return total


def stale(conn, sources, raw_sources=None):
    """True when a source's matches are out of date: it has records (raw_sources, by default
    `sources`) but no matches, or its records or ACHD's segments have changed since its
    oldest last match. A source with no records at all has nothing to match."""
    raw_sources = list(raw_sources or sources)
    if not conn.execute("select exists (select 1 from raw.record where source = any(%s) and removed_at is null)",
                        (raw_sources,)).fetchone()[0]:
        return False
    last = conn.execute(
        """select min(m.last) from unnest(%s::text[]) s(source)
           left join lateral (select max(matched_at) as last from core.segment_match where source = s.source) m on true""",
        (list(sources),)).fetchone()[0]
    if last is None:
        return True
    return bool(conn.execute(
        """select exists (select 1 from raw.record where source = any(%s)
                            and (first_seen > %s or removed_at > %s))""",
        (raw_sources + ["achd_roads"], last, last)).fetchone()[0])


def matchers():
    """{source name: (match(conn) -> stats, the match sources it writes, its raw sources)}
    for every source matched to ACHD's segments."""
    from .sources import achd_msm, compass_centerline, itd_hpms, osm_valley
    return {
        "itd_hpms": (itd_hpms.match, itd_hpms.MATCH_SOURCES, itd_hpms.MATCH_SOURCES + [itd_hpms.NAMES_SOURCE]),
        "achd_msm": (achd_msm.match, ["achd_msm"], ["achd_msm"]),
        "compass_centerline": (compass_centerline.match, ["compass_centerline"], ["compass_centerline"]),
        "osm_valley": (osm_valley.match_achd_segments, ["osm_valley"], ["osm_valley"]),
    }


def rematch_all(conn, names=None, only_stale=False):
    """Rematch every source (or the named ones; with only_stale, those whose matches are out
    of date), committing after each. A matcher that fails is rolled back and logged, and the
    rest still run; the failures are in the result. Returns {name: stats or {"failed": error}}."""
    found = matchers()
    unknown = [n for n in names or () if n not in found]
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(unknown)} (choose from {', '.join(found)})")
    out = {}
    for name in names or list(found):
        match, sources, raw_sources = found[name]
        try:
            if only_stale and not stale(conn, sources, raw_sources):
                continue
            out[name] = match(conn)
            conn.commit()
        except Exception as err:
            conn.rollback()
            print(f"segment_match: {name} failed:\n{traceback.format_exc()}", flush=True)
            out[name] = {"failed": f"{type(err).__name__}: {err}"[:300]}
    return out


def main(argv):
    from ingest import db
    with db.connect() as conn:
        try:
            results = rematch_all(conn, argv or None)
        except ValueError as err:
            sys.exit(str(err))
    for name, stats in results.items():
        print(f"{name} matching: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    if any("failed" in s for s in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
