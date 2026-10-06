"""Offline tests for the route palette, the "too similar" rule and color
assignment (docs/14 §14.4 "Route colors", the badge rule in §14.3).

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import os
import unittest

from ingest import route_colors as rc

HERE = os.path.dirname(os.path.abspath(__file__))
H = dict(rc.PALETTE_SLOTS)

# docs/14 §14.4's palette table: name, hex, contrast on clay, ghost on clay, badge text and its contrast.
TABLE = [
    ("blue", "#2a78d6", 3.79, "#b1c6e2", "white", 4.42),
    ("orange", "#eb6834", 2.75, "#f5b59a", "ink", 4.43),
    ("aqua", "#1baf7a", 2.42, "#a4d2b2", "ink", 5.03),
    ("yellow", "#eda100", 1.86, "#f1c17b", "ink", 6.55),
    ("pink", "#e87ba4", 2.31, "#f1b3c2", "ink", 5.26),
    ("green", "#008300", 4.24, "#b3cda4", "white", 4.95),
    ("violet", "#4a3aa7", 7.34, "#bab8d4", "white", 8.56),
    ("red", "#e34948", 3.39, "#f4b3a7", "white", 3.95),
    ("wine", "#99095c", 7.07, "#deafb8", "white", 8.24),
    ("lavender", "#a791fa", 2.23, "#cbc0f1", "ink", 5.45),
    ("brown", "#7f4315", 6.64, "#d1b8a4", "white", 7.73),
    ("plum", "#9059af", 4.26, "#d1bad3", "white", 4.96),
    ("lime", "#8cc63f", 1.76, "#b9d88e", "ink", 6.93),
]


class PaletteTest(unittest.TestCase):
    def test_the_13_slots_are_pinned_in_order(self):
        # Contrast is never "fixed" by editing a hex: slots are fixed and append-only.
        self.assertEqual(rc.PALETTE, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
                                      "#e34948", "#99095c", "#a791fa", "#7f4315", "#9059af", "#8cc63f"])
        self.assertEqual([n for n, _ in rc.PALETTE_SLOTS],
                         ["blue", "orange", "aqua", "yellow", "pink", "green", "violet", "red", "wine", "lavender",
                          "brown", "plum", "lime"])
        self.assertEqual(rc.UNKNOWN, "#8a857c")
        self.assertEqual((rc.INK, rc.CLAY, rc.CREAM), ("#2b2a33", "#f3ede2", "#fffbf4"))

    def test_the_first_8_are_the_colors_routes_had_before(self):
        self.assertEqual(rc.PALETTE[:8], ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
                                          "#4a3aa7", "#e34948"])

    def test_python_reproduces_the_validator_within_0_1(self):
        self.assertAlmostEqual(rc.delta_e(H["orange"], H["red"]), 7.1, delta=0.1)               # normal vision
        self.assertAlmostEqual(rc.delta_e(H["orange"], H["green"], "protan"), 3.2, delta=0.1)
        self.assertAlmostEqual(rc.delta_e(H["aqua"], H["pink"], "deutan"), 6.1, delta=0.1)

    def test_every_slot_passes_band_and_chroma(self):
        for name, h in rc.PALETTE_SLOTS:
            s = rc.slot_checks(h)
            self.assertTrue(s["band"], f"{name} L {s['L']:.3f} outside {rc.BAND}")
            self.assertTrue(s["chroma"], f"{name} C {s['C']:.3f} below {rc.CHROMA_FLOOR}")

    def test_the_table_contrast_and_ghosts(self):
        for name, h, on_clay, ghost, text, on_plate in TABLE:
            self.assertEqual(H[name], h)
            self.assertAlmostEqual(rc.contrast(h, rc.CLAY), on_clay, delta=0.006, msg=name)
            self.assertEqual(rc.ghost(h), ghost, name)
            self.assertGreaterEqual(rc.delta_e(ghost, rc.CLAY), 14.0, name)       # ghosts sit about dE 14 from clay
            b = rc.badge(h)
            self.assertEqual(b["text"], rc.WHITE if text == "white" else rc.INK, name)
            self.assertAlmostEqual(b["on_plate"], on_plate, delta=0.006, msg=name)

    def test_the_badge_rule_per_slot(self):
        # Its text color reaches 4.5:1 on the plate, or the slot is flagged halo and its text
        # reaches 4.5:1 on the halo color (ink around white, cream around ink).
        flagged = set()
        for name, h in rc.PALETTE_SLOTS + [("unknown", rc.UNKNOWN)]:
            b = rc.badge(h)
            if b["halo"]:
                flagged.add(name)
                self.assertLess(b["on_plate"], 4.5, name)
                self.assertEqual(b["halo_color"], rc.INK if b["text"] == rc.WHITE else rc.CREAM, name)
                self.assertGreaterEqual(rc.contrast(b["text"], b["halo_color"]), 4.5, name)
            else:
                self.assertGreaterEqual(b["on_plate"], 4.5, name)
                self.assertIsNone(b["halo_color"])
        self.assertEqual(flagged, {"blue", "orange", "red", "unknown"})       # ten slots reach 4.5:1 plain

    def test_twelve_clashing_pairs(self):
        names = {(rc.NAMES[a], rc.NAMES[b]) for a, b in rc.clashing_pairs()}
        self.assertEqual(names, {("blue", "plum"), ("orange", "yellow"), ("orange", "pink"), ("orange", "green"),
                                 ("orange", "red"), ("aqua", "pink"), ("aqua", "red"), ("aqua", "lime"),
                                 ("yellow", "lime"), ("pink", "red"), ("green", "red"), ("green", "brown")})
        # The two the old hand-made list missed on live neighbor routes (10/16 and 28/29).
        self.assertTrue(rc.clash(H["red"], H["green"]))
        self.assertTrue(rc.clash(H["red"], H["aqua"]))

    def test_separation_is_one_at_the_bar(self):
        self.assertTrue(rc.clash("#123456", "#123456"))
        for a, b in [(H["blue"], H["orange"]), (H["violet"], H["lime"])]:
            self.assertGreaterEqual(rc.separation(a, b), 1.0)
            self.assertFalse(rc.clash(a, b))


def colors_ok(test, colors, neighbors):
    for a, ns in neighbors.items():
        for b in ns:
            if a in colors and b in colors:
                test.assertFalse(rc.clash(colors[a], colors[b]), f"{a}/{b}: {colors[a]} {colors[b]}")


class AssignTest(unittest.TestCase):
    def test_valid_stored_colors_are_kept(self):
        nb = {"a": {"b"}, "b": {"a"}}
        colors, info = rc.assign(["a", "b"], nb, {"a": H["blue"], "b": H["orange"]})
        self.assertEqual(colors, {"a": H["blue"], "b": H["orange"]})
        self.assertEqual((info["how"], info["changes"]), ("kept", []))

    def test_only_what_must_change_changes(self):
        # b clashes with a (red/green); only one of them has to move.
        nb = {"a": {"b"}, "b": {"a"}, "c": set()}
        stored = {"a": H["red"], "b": H["green"], "c": H["yellow"]}
        for mode in rc.MODES:
            colors, info = rc.assign(["a", "b", "c"], nb, stored, mode=mode)
            self.assertEqual(len(info["changes"]), 1, mode)
            self.assertEqual(colors["c"], H["yellow"])
            colors_ok(self, colors, nb)

    def test_rebalance_caps_each_color(self):
        # 20 routes, cap ceil(20/13) = 2: four on aqua is too many even with no neighbors.
        routes = [str(i) for i in range(20)]
        stored = {r: rc.PALETTE[i % 13] for i, r in enumerate(routes)}
        for r in ("0", "1", "3"):
            stored[r] = H["aqua"]                                     # with 2 and 15, five on aqua
        self.assertEqual(list(stored.values()).count(H["aqua"]), 5)
        colors, info = rc.assign(routes, {}, stored, mode="rebalance")
        self.assertLessEqual(max(list(colors.values()).count(c) for c in set(colors.values())), 2)
        self.assertEqual(len(info["changes"]), 3)                     # the fewest that meets the cap
        self.assertTrue(info["proven"])
        _, info_min = rc.assign(routes, {}, stored, mode="minimal")
        self.assertEqual(info_min["changes"], [])                     # minimal: no clash, so nothing moves

    def test_minimal_changes_only_clashing_routes(self):
        nb = {"a": {"b"}, "b": {"a", "c"}, "c": {"b"}, "d": set()}
        stored = {"a": H["orange"], "b": H["red"], "c": H["violet"], "d": H["orange"]}
        colors, info = rc.assign(["a", "b", "c", "d"], nb, stored, mode="minimal")
        self.assertTrue({r for r, _, _ in info["changes"]} <= {"a", "b"})
        self.assertEqual(colors["d"], H["orange"])
        colors_ok(self, colors, nb)

    def test_pinned_and_fixed_colors_never_change(self):
        nb = {"a": {"b"}, "b": {"a"}}
        stored = {"a": H["red"], "b": H["green"]}
        colors, _ = rc.assign(["a", "b"], nb, stored, pinned={"b"})
        self.assertEqual(colors["b"], H["green"])
        self.assertNotEqual(colors["a"], H["red"])
        colors, _ = rc.assign(["a"], {"a": {"z"}, "z": {"a"}}, {"a": H["red"]}, fixed={"z": H["green"]})
        self.assertEqual(colors["z"], H["green"])
        self.assertFalse(rc.clash(colors["a"], H["green"]))

    def test_new_routes_get_colors(self):
        nb = {"a": {"b", "c"}, "b": {"a", "c"}, "c": {"a", "b"}}
        colors, info = rc.assign(["a", "b", "c"], nb, {"a": H["red"]})
        self.assertEqual(colors["a"], H["red"])
        self.assertEqual(set(colors), {"a", "b", "c"})
        self.assertEqual(info["clashes"], [])
        colors_ok(self, colors, nb)

    def test_too_many_mutual_neighbors_still_colors_everyone(self):
        routes = [str(i) for i in range(13)]                       # 13 routes all sharing streets
        nb = {r: set(routes) - {r} for r in routes}
        colors, info = rc.assign(routes, nb, {})
        self.assertEqual(info["how"], "fallback")                  # no clash-free coloring exists
        self.assertEqual(len(colors), 13)
        self.assertEqual(len(set(colors.values())), 13)           # every color used

    def test_the_fallback_minimizes_the_shortfall(self):
        routes = [str(i) for i in range(16)]                       # more mutual neighbors than colors
        nb = {r: set(routes) - {r} for r in routes}
        colors, info = rc.assign(routes, nb, {})
        self.assertEqual((info["how"], len(colors)), ("fallback", 16))
        self.assertLessEqual(max(list(colors.values()).count(c) for c in rc.PALETTE), 2)

        def shortfall(cs):
            return sum(max(0.0, 1 - (0.0 if cs[a] == cs[b] else rc.separation(cs[a], cs[b])))
                       for a in routes for b in nb[a] if a < b)

        round_robin = {r: rc.PALETTE[i % 13] for i, r in enumerate(routes)}
        self.assertLess(shortfall(colors), shortfall(round_robin))

    def test_the_real_neighbor_graph_assigns_with_no_clash(self):
        # The neighbor graph of a build on VRT's feed 457 (Oct 6, 2026): route ids only.
        with open(os.path.join(HERE, "fixtures", "vrt_neighbors.json")) as f:
            fx = json.load(f)
        nb = {r: set(v) for r, v in fx["neighbors"].items()}
        for mode in rc.MODES:
            colors, info = rc.assign(fx["order"], nb, fx["stored"], mode=mode)
            self.assertEqual(info["clashes"], [], mode)
            self.assertEqual(rc.clashes(colors, nb), [], mode)
            self.assertTrue(info["proven"], mode)
            colors_ok(self, colors, nb)
            # Assigning again from the result changes nothing.
            again, info2 = rc.assign(fx["order"], nb, colors, mode=mode)
            self.assertEqual((again, info2["changes"]), (colors, []), mode)
        rebalanced, _ = rc.assign(fx["order"], nb, fx["stored"], mode="rebalance")
        self.assertLessEqual(max(list(rebalanced.values()).count(c) for c in rc.PALETTE), 2)

    def test_deterministic(self):
        with open(os.path.join(HERE, "fixtures", "vrt_neighbors.json")) as f:
            fx = json.load(f)
        nb = {r: set(v) for r, v in fx["neighbors"].items()}
        a = rc.assign(fx["order"], nb, fx["stored"])
        b = rc.assign(fx["order"], {r: set(sorted(v, reverse=True)) for r, v in reversed(list(nb.items()))},
                      dict(reversed(list(fx["stored"].items()))))
        self.assertEqual(a[0], b[0])

    def test_dry_run_report(self):
        lines = rc.report({"10": H["red"], "2": H["aqua"]}, {"10": H["green"], "2": H["aqua"]}, {"10": "10", "2": "2"})
        self.assertEqual(lines, ["  route 10: red #e34948 -> green #008300"])


if __name__ == "__main__":
    unittest.main()
