"""Where the sheet tool draws: named places, each one or more square frames on the ground grid. Standard library only.

    python3 -m basemap.sheets.places                     # every set, with each frame's size
    python3 -m basemap.sheets.places cameras eagle-rd    # some of them
    python3 -m basemap.sheets.places --json at:-116.2,43.61,300,0.5

The sets (places.json; the boxes come from basemap/ground/spec.json):

| Set | Frames | Default frame |
|---|---|---|
| `boxes` | the ten land-cover test boxes, `a` ... `j`, `downtown` | the whole box at 1 m |
| `cameras` | the 34 key-camera intersections, `cam-<image id>` | 240 m at 0.25 m (interchanges larger) |
| `corridors` | Eagle Road and Chinden Boulevard, `eagle-rd-01` ... | 600 m at 0.5 m, every 580 m along the road |
| `spots` | `table-rock`, `airport`, `industrial` | as each says |

A selection is a list of set names, place ids (`a`, `box-a`, `cam-752`, `752`, `eagle-rd`, `eagle-rd-03`,
`table-rock`), `all`, or an ad-hoc frame `at:LON,LAT[,SIZE_M[,RES_M]]`. Each frame is a grid.Window: north-up on
EPSG:32611, its edges on the grid at its resolution, so rasters on the ground grid draw without resampling.
"""

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass

from basemap.ground import grid
from ingest.utm import from_utm, to_utm

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PLACES_PATH = os.path.join(HERE, "places.json")
KEY_CAMERAS = os.path.join(REPO, "plugins", "cameras", "ingest", "key_cameras.csv")
SETS = ("boxes", "cameras", "corridors", "spots")


@dataclass(frozen=True)
class Frame:
    id: str                    # 'box-a', 'cam-752', 'eagle-rd-03', 'table-rock', 'at-...'
    set: str                   # boxes, cameras, corridors, spots, at
    group: str                 # the contact sheet it goes on: the set, or the corridor's id
    name: str
    window: grid.Window        # EPSG:32611, north-up, on the grid at its resolution
    note: str = ""             # where the frame's centre came from
    box: str = ""              # the test box it shows, for boxes

    @property
    def res(self):
        return self.window.res

    @property
    def bounds(self):
        return self.window.bounds

    @property
    def centre(self):
        w, s, e, n = self.window.bounds
        return (w + e) / 2, (s + n) / 2

    @property
    def lonlat(self):
        return from_utm(*self.centre)

    def describe(self):
        w, s, e, n = self.window.bounds
        lon, lat = self.lonlat
        return {"id": self.id, "set": self.set, "group": self.group, "name": self.name, "note": self.note,
                "box": self.box or None, "res": self.res, "size_px": [self.window.width, self.window.height],
                "bounds": [w, s, e, n], "crs": grid.CRS, "centre_lonlat": [round(lon, 6), round(lat, 6)]}


class PlaceError(ValueError):
    pass


def load(path=PLACES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def key_cameras(path=KEY_CAMERAS):
    """[(image_id, name, why)] in the list's order."""
    with open(path, newline="", encoding="utf-8") as f:
        return [(int(r["image_id"]), r["name"].strip(), r.get("why", "").strip()) for r in csv.DictReader(f)]


def square(centre, size_m, res):
    """The window of a size_m square (rounded to whole cells) centred on centre (grid metres), as near the centre as
    the grid's cells allow."""
    res = grid.check_res(res)
    if not size_m > 0:
        raise PlaceError(f"a frame's size must be positive (got {size_m})")
    n = max(1, round(size_m / res))
    x, y = centre
    col = round((x - grid.ORIGIN_X) / res - n / 2)
    row = round((grid.ORIGIN_Y - y) / res - n / 2)
    return grid.Window(res, col, row, n, n)


def along(line_xy, step):
    """Centres every `step` metres along a polyline (grid metres), spread so the first and last fall half a step in
    from its ends (at least one)."""
    seg = [math.dist(line_xy[i], line_xy[i + 1]) for i in range(len(line_xy) - 1)]
    total = sum(seg)
    n = max(1, math.ceil(total / step))
    out = []
    for k in range(n):
        d = total * (k + 0.5) / n
        for i, length in enumerate(seg):
            if d <= length or i == len(seg) - 1:
                t = d / length if length else 0.0
                (x0, y0), (x1, y1) = line_xy[i], line_xy[i + 1]
                out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
                break
            d -= length
    return out


def _num(v, what):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise PlaceError(f"{what}: not a number ({v!r})") from None


def _pick(entry, defaults, key, override):
    return override if override is not None else entry.get(key, defaults.get(key))


def all_frames(places=None, cameras=None, res=None, size=None):
    """{set: [Frame]} for every set. res and size override every frame's (size doesn't apply to corridors' step)."""
    places = places or load()
    cams = cameras if cameras is not None else key_cameras()
    d = places["defaults"]
    out = {s: [] for s in SETS}

    for b in grid.boxes():
        if size is None:
            win = grid.window(b.utm, grid.check_res(res or d["boxes"]["res"]), snap="out")
        else:
            w, s, e, n = b.utm
            win = square(((w + e) / 2, (s + n) / 2), size, res or d["boxes"]["res"])
        out["boxes"].append(Frame(f"box-{b.id}", "boxes", "boxes", f"{b.name} (box {b.id})", win,
                                  "the land-cover test box (basemap/ground/spec.json)", box=b.id))

    where = {c["image_id"]: c for c in places["cameras"]}
    for image_id, name, _why in cams:
        c = where.get(image_id)
        if c is None:
            raise PlaceError(f"key camera {image_id} ({name}) has no centre in places.json")
        lon, lat = c["lonlat"]
        win = square(to_utm(lon, lat), _pick(c, d["cameras"], "size", size), _pick(c, d["cameras"], "res", res))
        out["cameras"].append(Frame(f"cam-{image_id}", "cameras", "cameras", name, win, f"OSM: {c['osm']}"))

    for cor in places["corridors"]:
        xy = [to_utm(lon, lat) for lon, lat in cor["line"]]
        step = cor.get("step", d["corridors"]["step"])
        centres = along(xy, step)
        for k, centre in enumerate(centres, 1):
            win = square(centre, _pick(cor, d["corridors"], "size", size), _pick(cor, d["corridors"], "res", res))
            out["corridors"].append(Frame(f"{cor['id']}-{k:02d}", "corridors", cor["id"],
                                          f"{cor.get('short', cor['name'])}, {k} of {len(centres)}", win,
                                          f"{cor['name']}: the OSM centreline, a frame every {step:g} m"))

    for sp in places["spots"]:
        lon, lat = sp["lonlat"]
        win = square(to_utm(lon, lat), _pick(sp, d["spots"], "size", size), _pick(sp, d["spots"], "res", res))
        out["spots"].append(Frame(sp["id"], "spots", "spots", sp["name"], win, f"OSM: {sp['osm']}"))
    return out


def at(spec, res=None, size=None):
    """An ad-hoc frame from 'at:LON,LAT[,SIZE_M[,RES_M]]'."""
    parts = spec[3:].split(",")
    if len(parts) < 2 or len(parts) > 4:
        raise PlaceError(f"{spec!r}: at:LON,LAT[,SIZE_M[,RES_M]]")
    lon, lat = _num(parts[0], spec), _num(parts[1], spec)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise PlaceError(f"{spec!r}: lon, lat out of range")
    sz = size if size is not None else (_num(parts[2], spec) if len(parts) > 2 else 500)
    r = res if res is not None else (_num(parts[3], spec) if len(parts) > 3 else 0.5)
    x, y = to_utm(lon, lat)
    if not (grid.WEST <= x <= grid.EAST and grid.SOUTH <= y <= grid.NORTH):
        raise PlaceError(f"{spec!r}: outside the map box")
    ns, ew = ("N" if lat >= 0 else "S"), ("W" if lon < 0 else "E")
    name = f"{abs(lat):.5f} {ns}, {abs(lon):.5f} {ew}"
    fid = f"at-{abs(lat):.5f}{ns}-{abs(lon):.5f}{ew}".lower()
    return Frame(fid, "at", "at", name, square((x, y), sz, r), "an ad-hoc frame")


def _number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def split_selection(raw):
    """A comma-separated selection as its selectors: an at: selector keeps the numbers after it, up to its four
    (`cameras,at:-116.2,43.61,300` is two)."""
    out = []
    for tok in (t.strip() for t in raw.split(",")):
        if not tok:
            continue
        if out and out[-1].startswith("at:") and out[-1].count(",") < 3 and _number(tok):
            out[-1] += "," + tok
        else:
            out.append(tok)
    return out


def select(tokens, places=None, cameras=None, res=None, size=None):
    """The frames a selection names, in order, each once. Raises PlaceError on a name it doesn't know."""
    sets = all_frames(places, cameras, res=res, size=size)
    by_id, by_group = {}, {}
    for frames in sets.values():
        for f in frames:
            by_id[f.id] = f
            by_group.setdefault(f.group, []).append(f)
    out, seen = [], set()

    def add(frames):
        for f in frames:
            if f.id not in seen:
                seen.add(f.id)
                out.append(f)

    for raw in tokens:
        for tok in split_selection(raw):
            if tok == "all":
                add(f for s in SETS for f in sets[s])
            elif tok in sets:
                add(sets[tok])
            elif tok.startswith("at:"):
                add([at(tok, res=res, size=size)])
            elif tok in by_id:
                add([by_id[tok]])
            elif f"box-{tok}" in by_id:
                add([by_id[f"box-{tok}"]])
            elif f"cam-{tok}" in by_id:
                add([by_id[f"cam-{tok}"]])
            elif tok in by_group:
                add(by_group[tok])
            else:
                raise PlaceError(f"no place {tok!r}: name a set ({', '.join(SETS)}), a box (a ... j, downtown), "
                                 "cam-<image id>, a corridor (eagle-rd, chinden-blvd) or one of its frames, a spot "
                                 "(table-rock, airport, industrial), all, or at:LON,LAT[,SIZE_M[,RES_M]]")
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m basemap.sheets.places", description=__doc__.split("\n\n")[0])
    p.add_argument("places", nargs="*", default=["all"], help="sets, place ids or at:LON,LAT[,SIZE_M[,RES_M]]")
    p.add_argument("--res", type=float, help="metres a pixel for every frame (a level of the ground grid)")
    p.add_argument("--size", type=float, help="every frame's width in metres")
    p.add_argument("--json", action="store_true", help="print each frame as JSON")
    a = p.parse_args(argv)
    try:
        frames = select(a.places, res=a.res, size=a.size)
    except (PlaceError, ValueError) as err:
        print(f"places: {err}", file=sys.stderr)
        return 2
    for f in frames:
        if a.json:
            print(json.dumps(f.describe()))
        else:
            lon, lat = f.lonlat
            print(f"{f.id:16} {f.window.width:5} x {f.window.height:<5} px at {f.res:g} m  "
                  f"{lat:.5f}, {lon:.5f}  {f.name}")
    if not a.json:
        print(f"{len(frames)} frames", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
