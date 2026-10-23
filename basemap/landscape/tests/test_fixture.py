"""The browser-spec fixtures (fixture.py): standard library only, no GDAL. The written tiles are decoded back and
checked against the fixture files, and the entries against the bake's and the ground's own checks."""

import gzip
import json
import os
import shutil
import struct
import tempfile
import unittest

from basemap.ground import tiles as ground_tiles
from basemap.landscape import fixture as F, pmtiles as P, plan


def _read_varint(b, i):
    v, shift = 0, 0
    while True:
        c = b[i]
        i += 1
        v |= (c & 0x7F) << shift
        if not c & 0x80:
            return v, i
        shift += 7


def _fields(b):
    """[(number, wire type, value)] of one protobuf message (a length-delimited value is bytes)."""
    out, i = [], 0
    while i < len(b):
        key, i = _read_varint(b, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            v, i = _read_varint(b, i)
        elif wire == 1:
            v, i = b[i:i + 8], i + 8
        elif wire == 2:
            n, i = _read_varint(b, i)
            v, i = b[i:i + n], i + n
        else:
            raise AssertionError(f"wire type {wire}")
        out.append((num, wire, v))
    return out


def _value(b):
    (num, _, v), = _fields(b)
    return {1: lambda: v.decode("utf-8"), 3: lambda: struct.unpack("<d", v)[0], 5: lambda: v,
            6: lambda: (v >> 1) ^ -(v & 1), 7: lambda: bool(v)}[num]()


def _geometry(ints, kind):
    """The rings or lines of a geometry (lists of absolute points)."""
    parts, cur, x, y, i = [], None, 0, 0, 0
    while i < len(ints):
        cmd, count = ints[i] & 7, ints[i] >> 3
        i += 1
        for _ in range(count if cmd != 7 else 1):
            if cmd == 7:
                break
            dx, dy = ints[i], ints[i + 1]
            i += 2
            x, y = x + ((dx >> 1) ^ -(dx & 1)), y + ((dy >> 1) ^ -(dy & 1))
            if cmd == 1 and kind != 1:
                cur = []
                parts.append(cur)
            if kind == 1:
                parts.append((x, y))
            else:
                cur.append((x, y))
    return parts


def decode_tile(data):
    """{layer name: [{"id", "props", "type", "geometry"}]} from a gzipped vector tile."""
    out = {}
    for num, _, layer in _fields(gzip.decompress(data)):
        assert num == 3
        name, keys, values, feats, extent = None, [], [], [], None
        for n, _, v in _fields(layer):
            if n == 1:
                name = v.decode("utf-8")
            elif n == 2:
                feats.append(v)
            elif n == 3:
                keys.append(v.decode("utf-8"))
            elif n == 4:
                values.append(_value(v))
            elif n == 5:
                extent = v
        assert extent == 4096
        decoded = []
        for fb in feats:
            f = dict(_fields_by_num(fb))
            tags = [t for t, _ in _packed(f[2])]
            props = {keys[tags[j]]: values[tags[j + 1]] for j in range(0, len(tags), 2)}
            ints = [t for t, _ in _packed(f[4])]
            decoded.append({"id": f[1], "props": props, "type": f[3], "geometry": _geometry(ints, f[3])})
        out[name] = decoded
    return out


def _fields_by_num(b):
    return [(n, v) for n, _, v in _fields(b)]


def _packed(b):
    i, out = 0, []
    while i < len(b):
        v, i = _read_varint(b, i)
        out.append((v, None))
    return out


def area2(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="tvt-fixture-")
        cls.entries = F.build(cls.dir, "painted")
        cls.layers = {lay.id: lay for lay in F.read_layers()}
        cls.entry = cls.entries["landscape"]
        cls.path = os.path.join(cls.dir, cls.entry["file"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def tile(self, z, x, y):
        data = P.tile_data(self.path, z, x, y)
        return decode_tile(data) if data else {}

    def tiles_at(self, z):
        return [self.tile(*t) for t in P.tile_sizes(self.path) if t[0] == z]

    def ids_at(self, z, layer):
        return {f["id"] for t in self.tiles_at(z) for f in t.get(layer, [])}

    def test_the_entry_passes_the_bakes_check(self):
        plan.check_entry(self.entry)
        self.assertEqual((self.entry["status"], self.entry["promoteId"], self.entry["access"]),
                         ("baked", "id", "tailnet"))
        self.assertEqual(set(self.entry["layers"]), set(self.layers))
        self.assertEqual(self.entry["empty"], [])

    def test_the_file_says_what_it_is(self):
        h = P.read_header(self.path)
        self.assertEqual((h.tile_type_name, h.tile_compression_name), ("mvt", "gzip"))
        self.assertEqual((h.min_zoom, h.max_zoom), (self.entry["minzoom"], self.entry["maxzoom"]))
        self.assertEqual(self.entry["maxzoom"], 16)
        meta = P.read_metadata(self.path)
        self.assertEqual(meta["tvt"]["landscape"], {k: v for k, v in self.entry.items() if k != "previous"})
        plan.check_entry(meta["tvt"]["landscape"], in_manifest=False)
        self.assertEqual({v["id"] for v in meta["vector_layers"]}, set(self.layers))

    def test_every_feature_is_there_with_its_id_and_fields(self):
        for sid, lay in self.layers.items():
            top = {}
            for t in self.tiles_at(lay.maxzoom):
                for f in t.get(sid, []):
                    top[f["id"]] = f
            want = {f["properties"]["id"]: f["properties"] for f in lay.features}
            self.assertEqual(set(top), set(want), sid)
            for i, f in top.items():
                props = want[i]
                self.assertEqual(top[i]["props"]["id"], i)
                self.assertNotIn("minzoom", top[i]["props"])
                self.assertEqual(set(top[i]["props"]), set(lay.tile_fields), (sid, i))
                for k, v in props.items():
                    if k != "minzoom":
                        self.assertEqual(top[i]["props"][k], v, (sid, i, k))
            self.assertEqual(self.entry["layers"][sid]["features"], len(want))

    def test_a_features_own_first_zoom_is_kept(self):
        # water.reaches: the main canal from z10, a lateral z12, a ditch z13
        self.assertNotIn(7001, self.ids_at(9, "water.reaches"))
        self.assertIn(7001, self.ids_at(10, "water.reaches"))
        self.assertNotIn(7002, self.ids_at(11, "water.reaches"))
        self.assertIn(7002, self.ids_at(12, "water.reaches"))
        self.assertNotIn(7003, self.ids_at(12, "water.reaches"))
        self.assertIn(7003, self.ids_at(13, "water.reaches"))
        # roads.lines: alleys and service ways from z15; the layer itself from z14
        self.assertEqual(self.ids_at(14, "roads.lines"), {1001, 1002})
        self.assertEqual(self.ids_at(15, "roads.lines"), {1001, 1002, 1003, 1004})
        self.assertEqual(self.ids_at(13, "roads.lines"), set())
        self.assertEqual(self.ids_at(15, "roads.surfaces"), set())
        self.assertTrue(self.ids_at(15, "roads.surfaces_z15"))
        self.assertEqual(self.ids_at(16, "roads.surfaces_z15"), set())

    def test_a_large_id_survives(self):
        self.assertIn(2 ** 51 + 991, self.ids_at(16, "water.reaches"))

    def test_polygons_wind_as_the_spec_says(self):
        for t in self.tiles_at(16):
            for f in t.get("roads.surfaces", []) + t.get("water.bodies", []):
                self.assertEqual(f["type"], 3)
                self.assertTrue(all(area2(r) > 0 for r in f["geometry"]), f["id"])

    def test_geometry_types(self):
        kinds = {"roads.arrows": 1, "roads.lines": 2, "roads.markings": 2, "roads.edges": 2, "roads.surfaces": 3,
                 "roads.crosswalks": 3, "water.reaches": 2, "water.bodies": 3}
        seen = {}
        for t in self.tiles_at(16):
            for sid, feats in t.items():
                for f in feats:
                    seen.setdefault(sid, set()).add(f["type"])
        for sid, k in kinds.items():
            self.assertEqual(seen[sid], {k}, sid)

    def test_the_downtown_budget_is_met(self):
        b = self.entry["budget"]
        self.assertGreater(b["tiles"], 0)
        self.assertLessEqual(b["largest"], b["maxBytes"])

    def test_it_is_deterministic(self):
        again = tempfile.mkdtemp(prefix="tvt-fixture-")
        try:
            F.build(again, "painted")
            for name in os.listdir(self.dir):
                with open(os.path.join(self.dir, name), "rb") as a, open(os.path.join(again, name), "rb") as b:
                    self.assertEqual(a.read(), b.read(), name)
        finally:
            shutil.rmtree(again, ignore_errors=True)

    def test_a_layer_with_a_duplicate_id_is_refused(self):
        folder = tempfile.mkdtemp(prefix="tvt-fixture-")
        try:
            with open(os.path.join(F.FIXTURES, "water.bodies.geojson"), encoding="utf-8") as f:
                doc = json.load(f)
            doc["features"].append(doc["features"][0])
            with open(os.path.join(folder, "water.bodies.geojson"), "w", encoding="utf-8") as f:
                json.dump(doc, f)
            with self.assertRaises(F.FixtureError):
                F.read_layers(folder)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_long_field_and_a_missing_member(self):
        folder = tempfile.mkdtemp(prefix="tvt-fixture-")
        try:
            doc = {"type": "FeatureCollection",
                   "tvt": {"geometry": "Point", "fields": {"id": "long", "n": "ulong"}, "minzoom": 14,
                           "maxzoom": 16, "licence": "ODbL-1.0", "republish": "yes", "credit": ["© Somebody"]},
                   "features": [{"type": "Feature", "properties": {"id": 1, "n": 5},
                                 "geometry": {"type": "Point", "coordinates": [-116.2, 43.615]}}]}
            with open(os.path.join(folder, "paving.marks.geojson"), "w", encoding="utf-8") as f:
                json.dump(doc, f)
            out = tempfile.mkdtemp(prefix="tvt-fixture-")
            try:
                self.assertIn("paving.marks", F.build(out, "none", fixtures=folder)["landscape"]["layers"])
            finally:
                shutil.rmtree(out, ignore_errors=True)
            del doc["tvt"]["fields"]
            with open(os.path.join(folder, "paving.marks.geojson"), "w", encoding="utf-8") as f:
                json.dump(doc, f)
            with self.assertRaises(F.FixtureError):
                F.read_layers(folder)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_a_new_layer_file_joins_the_bake(self):
        folder = tempfile.mkdtemp(prefix="tvt-fixture-")
        try:
            for name in ("water.bodies.geojson", "roads.arrows.geojson"):
                shutil.copy(os.path.join(F.FIXTURES, name), folder)
            doc = {"type": "FeatureCollection",
                   "tvt": {"geometry": "Point", "fields": {"id": "int", "kind": "string"}, "minzoom": 14,
                           "maxzoom": 16, "licence": "ODbL-1.0", "republish": "yes", "credit": ["© Somebody"]},
                   "features": [{"type": "Feature", "properties": {"id": 1, "kind": "x"},
                                 "geometry": {"type": "Point", "coordinates": [-116.2, 43.615]}}]}
            with open(os.path.join(folder, "paving.marks.geojson"), "w", encoding="utf-8") as f:
                json.dump(doc, f)
            out = tempfile.mkdtemp(prefix="tvt-fixture-")
            try:
                entries = F.build(out, "none", fixtures=folder)
                self.assertIn("paving.marks", entries["landscape"]["layers"])
                self.assertIn("© Somebody", entries["landscape"]["attribution"])
                self.assertNotIn("ground", entries)
            finally:
                shutil.rmtree(out, ignore_errors=True)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class Ground(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="tvt-fixture-")
        cls.entries = F.build(cls.dir, "painted")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_the_entry_passes_the_grounds_check(self):
        e = self.entries["ground"]
        ground_tiles.check_entry(e)
        self.assertEqual((e["status"], e["tileSize"], e["format"], e["republish"]), ("painted", 512, "webp", "yes"))
        self.assertEqual((e["minzoom"], e["maxzoom"]), (8, 15))
        self.assertEqual((e["detail"]["minzoom"], e["detail"]["maxzoom"]), (17, 17))

    def test_the_tiles_are_webp_in_a_checker(self):
        e = self.entries["ground"]
        valley = os.path.join(self.dir, e["file"])
        h = P.read_header(valley)
        self.assertEqual((h.tile_type_name, h.min_zoom, h.max_zoom), ("webp", 8, 15))
        sizes = P.tile_sizes(valley)
        self.assertEqual({z for z, _, _ in sizes}, set(range(8, 16)))
        seen = {}
        for z, x, y in sizes:
            data = P.tile_data(valley, z, x, y)
            self.assertEqual((data[:4], data[8:12]), (b"RIFF", b"WEBP"))
            seen[(x + y) % 2] = data
        self.assertEqual(set(seen), {0, 1})
        self.assertNotEqual(seen[0], seen[1])

    def test_the_default_view_and_downtown_are_covered(self):
        valley = os.path.join(self.dir, self.entries["ground"]["file"])
        sizes = P.tile_sizes(valley)
        z, x, y = 10, 179, 372                   # inside the default view at z10
        self.assertIn((z, x, y), sizes)
        _, ys = ground_tiles.tile_range((-116.2069, 43.6110, -116.1819, 43.6292), 15)
        self.assertTrue(any(t[0] == 15 and t[2] in ys for t in sizes))

    def test_the_detail_file_holds_z17_for_one_box(self):
        e = self.entries["ground"]
        detail = os.path.join(self.dir, e["detail"]["file"])
        h = P.read_header(detail)
        self.assertEqual((h.tile_type_name, h.min_zoom, h.max_zoom), ("webp", 17, 17))
        self.assertEqual(e["detail"]["boxes"], ["downtown"])
        self.assertTrue(P.tile_sizes(detail))

    def test_flat_and_none(self):
        for mode in ("flat", "none"):
            out = tempfile.mkdtemp(prefix="tvt-fixture-")
            try:
                entries = F.build(out, mode)
                self.assertEqual(sorted(os.listdir(out)),
                                 sorted([entries["landscape"]["file"], F.ENTRIES_FILE]))
                if mode == "flat":
                    ground_tiles.check_entry(entries["ground"])
                    self.assertEqual(entries["ground"]["status"], "flat")
                    self.assertTrue(entries["ground"]["reason"])
                else:
                    self.assertNotIn("ground", entries)
            finally:
                shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
