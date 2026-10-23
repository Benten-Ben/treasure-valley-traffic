"""Anchors: an owner-private list of trunk points that a trees build may match to the crowns it found (standard library only).

An anchor is a tree somebody else's inventory says stands at a point: a source name, its id there, a point, a genus, a
trunk diameter in inches and a planting date. The build places crowns from the lidar alone, as it would without anchors,
and only afterwards matches each anchor to the nearest crown within 2.5 m of its trunk point (match below); the genus
and trunk diameter size the trees the lidar doesn't show. What the inventory contributes does not go into the public
build: `trees.geojson`, `log.jsonl` and `build.json` hold only crowns found in the lidar, the same ones a build without
anchors writes, with no anchor id, trunk point, trunk diameter, genus or planting date. The links and the estimated trees
go to a side file, `anchors.jsonl`, for the private plugin that owns the inventory to load. The public loader
(ingest/load.py) never reads that file and refuses a build whose public files carry anything but a lidar-found tree's
fields. The side file holds inventory data. It is written to the build's `--private-out` folder, never to the build
folder or anywhere under the archive (check_private_dir: scratch jobs mount production's archive), and never into the
repository.

One line of anchors.jsonl:

- kind "matched": an anchor whose crown the lidar shows. `tree_id` is the public tree's id (trees.tree), `fit` how far
  the crown sits from the trunk point, `events` the tree's private log events.
- kind "estimated": an anchor the lidar doesn't show (planted after the flight, under a taller crown, too small, or with
  no crown near it). `tree_id` is private (`<source>-<source_id>`); the line holds the whole tree: type, point, sizes,
  fit and events.
"""
import csv
import json
import math
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


def matched(tree_id, an, area, build_id, trunk_to_crown_m, flight_at, detail):
    """An anchor whose crown the lidar shows: the link to the public tree and its private log event."""
    return {"kind": "matched", "tree_id": tree_id, "source": an["source"], "source_id": an["source_id"], "area": area,
            "build_id": build_id, "fit": {"trunk_to_crown_m": trunk_to_crown_m},
            "events": [{"at": flight_at, "event": "measured", "detail": detail}]}


def estimated(an, area, build_id, tree, built_at, detail):
    """An anchor the lidar doesn't show: the tree (type, lon, lat, ground_m, height_m, crown_radius_m, fit) and its
    private log event."""
    return {"kind": "estimated", "tree_id": f'{an["source"]}-{an["source_id"]}', "source": an["source"],
            "source_id": an["source_id"], "area": area, "build_id": build_id, **tree,
            "events": [{"at": built_at, "event": "estimated", "detail": detail}]}


def match(points, centres, reach):
    """One anchor to one crown: {point index: (centre index, distance)} for the points (row, col) and crown centres
    (row, col), in cells, pairing nearest first within `reach`. A crown goes to one anchor only (the nearer; a tie
    goes to the lower index), and the rest of the anchors are unmatched. The crowns are not changed by this."""
    pairs = sorted((math.hypot(py - cy, px - cx), i, j)
                   for i, (py, px) in enumerate(points) for j, (cy, cx) in enumerate(centres)
                   if abs(py - cy) <= reach and abs(px - cx) <= reach and math.hypot(py - cy, px - cx) <= reach)
    out, used = {}, set()
    for d, i, j in pairs:
        if i not in out and j not in used:
            out[i] = (j, d)
            used.add(j)
    return out


# Where the project keeps its private files, and production's archive, on the server. The guard names them itself and
# does not depend on the container's environment (a docker run has none of $TVT_ARCHIVE unless it was passed in).
PRIVATE_ROOT = "/srv/tvt/private"
PROD_ARCHIVE = "/srv/tvt/archive"


def check_private_dir(private, out, archives=(), private_root=None):
    """Refuse a place for anchors.jsonl that the public side can see. Every path is taken with its symlinks resolved.
    Refused: inside the build folder (or holding it); under production's archive (/srv/tvt/archive) or under any of the
    archive folders given (the environment's, as an extra check); and anywhere outside the private root
    (/srv/tvt/private, or private_root when given). Raises ValueError."""
    def inside(a, b):
        a, b = os.path.realpath(a), os.path.realpath(b)
        return a == b or a.startswith(b.rstrip(os.sep) + os.sep)
    root = private_root or PRIVATE_ROOT
    if inside(private, out) or inside(out, private):
        raise ValueError(f"--private-out {private} and the build folder {out} must be separate folders: "
                         f"the inventory's side file never goes beside the public files")
    for arc in (PROD_ARCHIVE, *archives):
        if arc and inside(private, arc):
            raise ValueError(f"--private-out {private} is under the archive {arc}: scratch jobs can read it. "
                             f"Use the project's private files")
    if not inside(private, root):
        raise ValueError(f"--private-out {private} is outside the private files ({root}; --private-root names another): "
                         f"the inventory's side file goes only there")


def write(folder, records):
    """anchors.jsonl in `folder` (made if needed); nothing is written when there are no anchors."""
    if not records:
        return 0
    os.makedirs(folder, exist_ok=True)
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
