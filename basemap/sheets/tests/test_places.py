"""The places (places.py, places.json): standard library only.

    python3 -m unittest discover -s basemap/sheets -t .
"""

import contextlib
import io
import json
import math
import unittest

from basemap.ground import grid
from basemap.sheets import places as P
from ingest.utm import to_utm


class PlacesFileTest(unittest.TestCase):
    def setUp(self):
        self.places = P.load()

    def test_every_key_camera_has_a_centre_and_nothing_else_does(self):
        cams = {i for i, _n, _w in P.key_cameras()}
        self.assertEqual(len(cams), 34)
        self.assertEqual({c["image_id"] for c in self.places["cameras"]}, cams)

    def test_every_place_is_in_the_map_box(self):
        pts = [c["lonlat"] for c in self.places["cameras"]] + [s["lonlat"] for s in self.places["spots"]]
        pts += [p for c in self.places["corridors"] for p in c["line"]]
        for lon, lat in pts:
            x, y = to_utm(lon, lat)
            self.assertTrue(grid.WEST <= x <= grid.EAST and grid.SOUTH <= y <= grid.NORTH, (lon, lat))

    def test_osm_credit_and_extract_are_recorded(self):
        self.assertEqual(self.places["credit"], "© OpenStreetMap contributors")
        self.assertEqual(self.places["licence"], "ODbL-1.0")
        self.assertIn("osm.pbf", self.places["osm"]["extract"])
        for c in self.places["cameras"] + self.places["spots"]:
            self.assertTrue(c.get("osm"), c)

    def test_the_named_spots_and_corridors(self):
        self.assertEqual([s["id"] for s in self.places["spots"]], ["table-rock", "airport", "industrial"])
        self.assertEqual([c["id"] for c in self.places["corridors"]], ["eagle-rd", "chinden-blvd"])


class FramesTest(unittest.TestCase):
    def test_sets_and_counts(self):
        sets = P.all_frames()
        self.assertEqual(len(sets["boxes"]), 10)
        self.assertEqual(len(sets["cameras"]), 34)
        self.assertEqual(len(sets["spots"]), 3)
        self.assertGreater(len(sets["corridors"]), 20)
        ids = [f.id for s in sets.values() for f in s]
        self.assertEqual(len(ids), len(set(ids)))

    def test_box_frames_are_the_boxes_exactly(self):
        for f in P.all_frames()["boxes"]:
            self.assertEqual(f.window.bounds, grid.box(f.box).utm)
            self.assertEqual(f.res, 1.0)

    def test_frames_sit_on_the_grid(self):
        for frames in P.all_frames().values():
            for f in frames:
                self.assertTrue(grid.aligned(f.window.transform, f.res), f.id)

    def test_camera_frames_are_squares_centred_on_the_intersection(self):
        where = {c["image_id"]: c for c in P.load()["cameras"]}
        for f in P.all_frames()["cameras"]:
            c = where[int(f.id[4:])]
            size, res = c.get("size", 240), c.get("res", 0.25)
            self.assertEqual((f.window.width, f.window.height), (round(size / res),) * 2)
            x, y = to_utm(*c["lonlat"])
            cx, cy = f.centre
            self.assertLessEqual(math.hypot(cx - x, cy - y), res)

    def test_corridor_frames_follow_the_line_and_cover_it(self):
        frames = [f for f in P.all_frames()["corridors"] if f.group == "eagle-rd"]
        line = [to_utm(*p) for p in next(c for c in P.load()["corridors"] if c["id"] == "eagle-rd")["line"]]
        length = sum(math.dist(line[i], line[i + 1]) for i in range(len(line) - 1))
        self.assertEqual(len(frames), math.ceil(length / 580))
        ys = [f.centre[1] for f in frames]
        self.assertEqual(ys, sorted(ys))                       # south to north, as drawn
        for a, b in zip(frames, frames[1:]):                   # neighbours touch or overlap
            self.assertLessEqual(math.dist(a.centre, b.centre), 600)
        self.assertEqual(frames[2].name, f"Eagle Road, 3 of {len(frames)}")
        self.assertLessEqual(frames[0].window.south, line[0][1])
        self.assertGreaterEqual(frames[-1].window.north, line[-1][1])

    def test_overrides(self):
        f = P.select(["cam-752"], res=0.5, size=100)[0]
        self.assertEqual((f.res, f.window.width), (0.5, 200))
        b = P.select(["c"], size=500)[0]
        self.assertEqual((b.window.width, b.window.height), (500, 500))
        with self.assertRaises(ValueError):
            P.select(["cam-752"], res=0.3)                    # not a level of the grid


class SelectTest(unittest.TestCase):
    def test_names(self):
        ids = [f.id for f in P.select(["a", "box-b", "752", "cam-655", "table-rock", "eagle-rd-02"])]
        self.assertEqual(ids, ["box-a", "box-b", "cam-752", "cam-655", "table-rock", "eagle-rd-02"])

    def test_sets_groups_and_commas_once_each(self):
        frames = P.select(["spots,airport", "boxes", "a"])
        self.assertEqual([f.id for f in frames][:3], ["table-rock", "airport", "industrial"])
        self.assertEqual(len(frames), 13)
        chinden = P.select(["chinden-blvd"])
        self.assertTrue(all(f.group == "chinden-blvd" for f in chinden))
        self.assertEqual(len(P.select(["all"])), sum(len(v) for v in P.all_frames().values()))

    def test_at(self):
        f = P.select(["at:-116.2,43.61,300,0.5"])[0]
        self.assertEqual((f.id, f.set, f.window.width, f.res), ("at-43.61000n-116.20000w", "at", 600, 0.5))
        self.assertEqual(P.select(["at:-116.2,43.61"])[0].window.width, 1000)
        for bad in ("at:-116.2", "at:x,43", "at:-120,43.5", "at:-116.2,43.61,300,0.3"):
            with self.assertRaises(ValueError, msg=bad):
                P.select([bad])

    def test_unknown(self):
        with self.assertRaisesRegex(P.PlaceError, "no place 'nowhere'"):
            P.select(["nowhere"])

    def test_cli(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(P.main(["--json", "spots"]), 0)
            self.assertEqual(P.main(["nowhere"]), 2)
        self.assertEqual([json.loads(line)["id"] for line in out.getvalue().splitlines()],
                         ["table-rock", "airport", "industrial"])
        self.assertIn("no place 'nowhere'", err.getvalue())

    def test_describe(self):
        d = P.select(["cam-752"])[0].describe()
        self.assertEqual(d["crs"], "EPSG:32611")
        self.assertEqual(d["size_px"], [960, 960])
        json.dumps(d)


class AlongTest(unittest.TestCase):
    def test_spacing(self):
        pts = P.along([(0, 0), (1000, 0)], 300)
        self.assertEqual(len(pts), 4)
        self.assertEqual([round(x) for x, _ in pts], [125, 375, 625, 875])

    def test_bends_and_short_lines(self):
        pts = P.along([(0, 0), (100, 0), (100, 100)], 50)
        self.assertEqual(pts, [(25.0, 0.0), (75.0, 0.0), (100.0, 25.0), (100.0, 75.0)])
        self.assertEqual(P.along([(0, 0), (10, 0)], 500), [(5.0, 0.0)])


if __name__ == "__main__":
    unittest.main()
