"""Tests for the registry built from this repository's plugin manifests (ingest/sources/__init__.py).

The lists below are what `python3 -m ingest` registered before the plugin
split (Oct 7, 2026): the refactor must not change them, nor their order,
which `run all` and `serve` follow. Private plugins on TVT_PLUGIN_PATH are
left out of the comparison.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import contextlib
import glob
import importlib
import io
import os
import re
import unittest

from ingest import manifest
from ingest import sources as registry
from ingest.__main__ import BUILTINS, main

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGINS_DIR = os.path.join(REPO, "plugins")

SOURCES_BEFORE = ["achd_cameras", "idaho511_views_oneoff", "vrt_gtfs", "achd_roads", "itd_hpms", "achd_msm",
                  "compass_centerline", "fra_crossings", "achd_signal_points", "compass_signals",
                  "compass_regional_signals", "intersections",
                  # ch. 17 Wave A (Oct 7): hazards (order 60) runs before safety's crashes, the rest after
                  "idl_fire_restrictions", "nifc_wfigs_incidents", "nifc_wfigs_perimeters", "nasa_firms", "nws_wwa",
                  "usgs_quakes", "compass_crashes", "noaa_hms_smoke", "nwps_gauges", "nrcs_snotel", "boise_ecoli",
                  "boise_river_hazards", "usdm_drought", "r2r_trails", "boise_greenbelt_closures", "usfs_r4_orders",
                  "idpr_route_closures", "idpr_area_restrictions", "awc_metar", "idfg_roadkill", "agrimet_et",
                  "swpc_ovation", "swpc_kp_1m", "compass_counts", "compass_growth", "compass_plats", "compass_congestion"]
STREAMS_BEFORE = ["vrt_realtime", "idaho511_frames", "itd_wzdx", "idaho511_api"]

WHERE = {  # source: plugin (docs/15 §15.4)
    "idl_fire_restrictions": "hazards", "nifc_wfigs_incidents": "hazards", "nifc_wfigs_perimeters": "hazards",
    "nasa_firms": "hazards", "nws_wwa": "hazards", "usgs_quakes": "hazards", "noaa_hms_smoke": "air",
    "nwps_gauges": "water", "nrcs_snotel": "water", "boise_ecoli": "water", "boise_river_hazards": "water",
    "usdm_drought": "water", "r2r_trails": "trails", "boise_greenbelt_closures": "trails",
    "usfs_r4_orders": "lands", "idpr_route_closures": "lands", "idpr_area_restrictions": "lands",
    "awc_metar": "weather", "idfg_roadkill": "wildlife", "agrimet_et": "farm", "swpc_ovation": "sky",
    "swpc_kp_1m": "sky",
    "achd_cameras": "cameras", "idaho511_views_oneoff": "cameras", "idaho511_frames": "cameras",
    "vrt_gtfs": "transit", "vrt_realtime": "transit",
    "achd_roads": "roads", "itd_hpms": "roads", "achd_msm": "roads", "compass_centerline": "roads",
    "fra_crossings": "intersections", "achd_signal_points": "intersections", "compass_signals": "intersections",
    "compass_regional_signals": "intersections", "intersections": "intersections",
    "itd_wzdx": "conditions", "idaho511_api": "conditions",
    "compass_crashes": "safety", "compass_counts": "flow", "compass_congestion": "flow",
    "compass_growth": "development", "compass_plats": "development",
}


def ours():
    """The plugins in this repository (not on TVT_PLUGIN_PATH)."""
    return [p for p in registry.PLUGINS if os.path.dirname(os.path.abspath(p.folder)) == PLUGINS_DIR]


class RegistryTest(unittest.TestCase):
    def names(self, reg):
        mine = {p.name for p in ours()}
        return [n for n in reg if registry.PLUGIN_OF[n] in mine]

    def test_sources_and_streams_are_what_they_were(self):
        self.assertEqual(self.names(registry.SOURCES), SOURCES_BEFORE)
        self.assertEqual(self.names(registry.STREAMS), STREAMS_BEFORE)

    def test_each_source_lives_in_its_plugin(self):
        for name, plugin in WHERE.items():
            self.assertEqual(registry.PLUGIN_OF[name], plugin, name)
            module = (registry.SOURCES.get(name) or registry.STREAMS[name]).__name__
            self.assertTrue(module.startswith(f"plugins.{plugin}.ingest."), module)
        self.assertEqual([e["name"] for _, e in registry.MANUAL if _.name == "roads"], ["osm_valley"])

    def test_the_plugins(self):
        self.assertEqual(sorted(p.name for p in ours()),
                         ["air", "cameras", "conditions", "development", "farm", "flow", "hazards", "intersections",
                          "lands", "roads", "safety", "sky", "trails", "transit", "water", "weather", "wildlife"])

    def test_manifests_agree_with_their_modules(self):
        for plugin in ours():
            for entry in plugin.manifest["sources"]:
                with self.subTest(entry["name"]):
                    m = importlib.import_module(f"plugins.{plugin.name}.{entry['module']}")
                    self.assertEqual(m.SOURCE["name"], entry["name"])
                    self.assertEqual(m.SOURCE["license"], entry["license"])
                    self.assertEqual(m.SOURCE["credit"], entry["credit"])
                    if entry["kind"] == "stream":
                        self.assertTrue(hasattr(m, "stream"))
                    elif entry["kind"] == "source":
                        self.assertTrue(hasattr(m, "run"))
                    else:
                        self.assertIsNone(m.SOURCE.get("schedule"))      # manual: never scheduled

    def test_every_plugin_has_its_parts_and_is_public(self):
        for plugin in ours():
            with self.subTest(plugin.name):
                self.assertEqual(plugin.visibility, "public")
                for part in ("__init__.py", "README.md", "ingest/__init__.py", "tests/__init__.py", "migrations"):
                    self.assertTrue(os.path.exists(os.path.join(plugin.folder, part)), part)

    def test_commands_resolve_and_keep_clear_of_the_built_ins(self):
        self.assertEqual(sorted(registry.COMMANDS),
                         ["match-intersections", "match-routes", "osm-load", "rollup", "route-colors", "segment-match",
                          "transit-progress", "transit-ribbons"])
        self.assertFalse(set(registry.COMMANDS) & set(BUILTINS))
        for name in registry.COMMANDS:
            self.assertTrue(callable(registry.command(name)), name)

    def test_tables_exist_and_have_one_owner(self):
        created = set()
        for path in glob.glob(os.path.join(REPO, "db", "migrations", "*.sql")) + \
                glob.glob(os.path.join(PLUGINS_DIR, "*", "migrations", "*.sql")):
            with open(path, encoding="utf-8") as f:
                created |= set(re.findall(r"create (?:or replace )?(?:table|view) (?:if not exists )?(\w+\.\w+)",
                                          f.read(), re.I))
        owner = {}
        for plugin in ours():
            for table in plugin.manifest["tables"]:
                self.assertIn(table, created, f"{plugin.name}: {table}")
                self.assertNotIn(table, owner, f"{table}: {owner.get(table)} and {plugin.name}")
                owner[table] = plugin.name

    def test_the_order_follows_dependencies(self):
        ordered = [p.name for p in manifest.plugin_order(ours())]
        for p in ours():
            for dep in p.depends:
                self.assertLess(ordered.index(dep), ordered.index(p.name), (dep, p.name))


class CommandLineTest(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as cm:
            main(list(argv))
        return cm.exception.code, out.getvalue()

    def test_a_plugin_command_gets_its_own_arguments(self):
        code, out = self.run_main("route-colors")
        self.assertIn(code, (None, 0))
        self.assertIn("Route palette", out)
        code, _ = self.run_main("match-intersections", "--no-such-flag")
        self.assertEqual(code, 2)                     # the command's own parser refused it

    def test_help_lists_the_plugin_commands(self):
        code, out = self.run_main("-h")
        self.assertEqual(code, 0)
        for name in registry.COMMANDS:
            self.assertIn(name, out)


if __name__ == "__main__":
    unittest.main()
