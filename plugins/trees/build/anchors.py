"""Anchors: an owner-private list of trunk points that a trees build may use (standard library only).

An anchor is a tree somebody else's inventory says stands at a point: a source name, its id there, a point, a genus, a
trunk diameter in inches and a planting date. The build uses the points to find crowns in the lidar (build.py, step 1)
and sizes the trees the lidar doesn't show from their genus and trunk diameter. What the inventory contributes does not
go into the public build: `trees.geojson` and `log.jsonl` hold only crowns found in the lidar, with no anchor id,
trunk point, trunk diameter, genus or planting date. The links and the estimated trees go to a side file in the build
folder, `anchors.jsonl`, for the private plugin that owns the inventory to load (its `city-trees-load` command). The
public loader (ingest/load.py) never reads that file and refuses a build whose public files carry anything but a
lidar-found tree's fields. The side file holds inventory data: it stays in the archive, never in the repository.

One line of anchors.jsonl:

- kind "matched": an anchor whose crown the lidar shows. `tree_id` is the public tree's id (trees.tree), `fit` how far
  the crown sits from the trunk point and the fit's gain, `events` the tree's private log events.
- kind "estimated": an anchor the lidar doesn't show (planted after the flight, under a taller crown, or too small).
  `tree_id` is private (`<source>-<source_id>`); the line holds the whole tree: type, point, sizes, fit and events.
"""
import csv
import json
import os

ANCHOR_FILE = "anchors.jsonl"
CSV_FIELDS = ("source", "source_id", "lon", "lat", "genus", "trunk_in", "installed_ms")
KINDS = ("matched", "estimated")


def read_rows(path):
    """The anchors CSV's rows as dicts; a missing column stops the build before any work."""
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        missing = [c for c in CSV_FIELDS if c not in (rd.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: anchors need the columns {', '.join(CSV_FIELDS)}; missing {', '.join(missing)}")
        return list(rd)


def matched(tree_id, an, area, build_id, trunk_to_crown_m, gain, flight_at, detail):
    """An anchor whose crown the lidar shows: the link to the public tree and its private log event."""
    return {"kind": "matched", "tree_id": tree_id, "source": an["source"], "source_id": an["source_id"], "area": area,
            "build_id": build_id, "fit": {"trunk_to_crown_m": trunk_to_crown_m, "gain": gain},
            "events": [{"at": flight_at, "event": "measured", "detail": detail}]}


def estimated(an, area, build_id, tree, built_at, detail):
    """An anchor the lidar doesn't show: the tree (type, lon, lat, ground_m, height_m, crown_radius_m, fit) and its
    private log event."""
    return {"kind": "estimated", "tree_id": f'{an["source"]}-{an["source_id"]}', "source": an["source"],
            "source_id": an["source_id"], "area": area, "build_id": build_id, **tree,
            "events": [{"at": built_at, "event": "estimated", "detail": detail}]}


def write(folder, records):
    """anchors.jsonl in a build folder; nothing is written when there are no anchors."""
    if not records:
        return 0
    with open(os.path.join(folder, ANCHOR_FILE), "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return len(records)


def read(folder):
    """The records of a build folder's anchors.jsonl ([] when it has none), checked: a known kind, a source and id."""
    path = os.path.join(folder, ANCHOR_FILE)
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("kind") not in KINDS or not r.get("source") or not r.get("source_id") or not r.get("tree_id"):
                raise ValueError(f"{path}: a line has an unknown kind or no source, source_id or tree_id")
            out.append(r)
    return out
