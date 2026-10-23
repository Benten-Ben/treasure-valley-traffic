"""Tests for the plugin manifests (ingest/manifest.py, plugins/__init__.py), on made-up plugins
in temporary folders.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from ingest import manifest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def entry(name, kind="source", **kw):
    return {"name": name, "module": f"ingest.sources.{name}", "kind": kind, "license": "test", "credit": "test",
            "republish": "no", **kw}


def plugin(name, sources=(), depends=(), **kw):
    return {"name": name, "title": name.title(), "depends": list(depends), "visibility": "public",
            "sources": list(sources), "tables": [], "storage": "none", "ethics": "none", **kw}


class Folder:
    """A temporary plugin folder: write(manifest) adds <folder>/<name>/plugin.json."""

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.path = tmp.name

    def write(self, m, folder_name=None):
        d = os.path.join(self.path, folder_name or m["name"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, manifest.FILE), "w") as f:
            json.dump(m, f)
        return d


def names(pairs):
    return [e["name"] for _, e in pairs]


class OrderTest(unittest.TestCase):
    def setUp(self):
        self.folder = Folder(self)

    def find(self):
        return manifest.find([self.folder.path])

    def test_plugins_dependencies_first_then_order_then_name(self):
        self.folder.write(plugin("zeta", order=10))
        self.folder.write(plugin("alpha", depends=["zeta"], order=5))
        self.folder.write(plugin("beta", order=50))
        self.folder.write(plugin("gamma", order=50))
        self.assertEqual([p.name for p in manifest.plugin_order(self.find())], ["zeta", "alpha", "beta", "gamma"])

    def test_entries_keep_manifest_order_and_follow_their_dependencies(self):
        self.folder.write(plugin("late", [entry("l1")], order=90))
        self.folder.write(plugin("base", [entry("b1"), entry("b2", order=1)], order=50))
        self.folder.write(plugin("user", [entry("u1"), entry("u2")], depends=["base"], order=10))
        self.folder.write(plugin("free", [entry("f1"), entry("f2", order=95)], order=20))
        # b2's own order (1) can't take it before b1; user (10) waits for all of base;
        # f2 (95) runs after late's l1 (90) although free comes first.
        self.assertEqual(names(manifest.entry_order(self.find(), "source")), ["f1", "b1", "b2", "u1", "u2", "l1", "f2"])

    def test_dependencies_count_through_plugins_without_entries(self):
        self.folder.write(plugin("a", [entry("a1")], order=90))
        self.folder.write(plugin("b", [entry("b1", kind="stream")], depends=["a"], order=1))
        self.folder.write(plugin("c", [entry("c1")], depends=["b"], order=1))
        self.assertEqual(names(manifest.entry_order(self.find(), "source")), ["a1", "c1"])

    def test_kinds_are_ordered_separately(self):
        self.folder.write(plugin("a", [entry("a1"), entry("as", kind="stream"), entry("am", kind="manual")], order=2))
        self.folder.write(plugin("b", [entry("bs", kind="stream", order=1)], order=3))
        plugins = self.find()
        self.assertEqual(names(manifest.entry_order(plugins, "stream")), ["bs", "as"])
        self.assertEqual(names(manifest.entry_order(plugins, "source")), ["a1"])
        self.assertEqual(names(manifest.entry_order(plugins, "manual")), ["am"])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.folder = Folder(self)

    def refused(self, m, folder_name=None):
        self.folder.write(m, folder_name)
        with self.assertRaises(manifest.ManifestError) as cm:
            manifest.find([self.folder.path])
        return str(cm.exception)

    def test_a_missing_dependency(self):
        self.assertIn("isn't installed", self.refused(plugin("a", depends=["nowhere"])))

    def test_a_cycle(self):
        self.folder.write(plugin("a", depends=["b"]))
        self.folder.write(plugin("b", depends=["a"]))
        with self.assertRaises(manifest.ManifestError):
            manifest.plugin_order(manifest.find([self.folder.path]))

    def test_names(self):
        self.assertIn("folder", self.refused(plugin("roads"), folder_name="streets"))
        self.assertIn("identifier", self.refused(plugin("achd-tables")))

    def test_two_folders_with_one_name(self):
        other = Folder(self)
        other.write(plugin("roads"))
        self.folder.write(plugin("roads"))
        with self.assertRaises(manifest.ManifestError) as cm:
            manifest.find([self.folder.path, other.path])
        self.assertIn("two plugins named roads", str(cm.exception))

    def test_field_values(self):
        cases = [
            (plugin("a", visibility="secret"), "visibility"),
            (plugin("b", [entry("x", kind="cron")]), "kind"),
            (plugin("c", [entry("x", republish="maybe")]), "republish"),
            (plugin("d", [entry("x", module="../x")]), "module"),
            (plugin("e", tables=["no_schema"]), "tables"),
            (plugin("f", colour="red"), "unknown field"),
            (plugin("g", commands=[{"name": "Do It", "module": "ingest.x", "help": "x"}]), "commands"),
            (plugin("h", [entry("x"), entry("x")]), "twice"),
        ]
        for m, word in cases:
            with self.subTest(m["name"]):
                folder = Folder(self)
                folder.write(m)
                with self.assertRaises(manifest.ManifestError) as cm:
                    manifest.find([folder.path])
                self.assertIn(word, str(cm.exception))

    def test_stale_after_and_fetch_sources(self):
        ok = plugin("a", [entry("x", "stream", stale_after="10 minutes", fetch_sources=["x_one", "x_two"])])
        self.folder.write(ok)
        found = manifest.find([self.folder.path])
        self.assertEqual(manifest.stream_staleness(found, "x"), ("10 minutes", ["x_one", "x_two"]))
        self.assertIsNone(manifest.stream_staleness(found, "nowhere"))
        cases = [
            (plugin("b", [entry("x", "source", stale_after="10 minutes")]), "for streams"),
            (plugin("c", [entry("x", "stream", stale_after="soon")]), "stale_after must be"),
            (plugin("d", [entry("x", "stream", stale_after="0 minutes")]), "stale_after must be"),
            (plugin("e", [entry("x", "stream", stale_after="1 fortnight")]), "stale_after must be"),
            (plugin("f", [entry("x", "stream", fetch_sources=["y"])]), "needs stale_after"),
            (plugin("g", [entry("x", "stream", stale_after="1 hour", fetch_sources=[])]), "fetch_sources"),
            (plugin("h", [entry("x", "stream", stale_after="1 hour", fetch_sources=["y", "y"])]), "fetch_sources"),
            (plugin("i", [entry("x", "stream", stale_after="1 hour", fetch_sources=["Y; drop"])]), "fetch_sources"),
        ]
        for m, word in cases:
            with self.subTest(m["name"]):
                folder = Folder(self)
                folder.write(m)
                with self.assertRaises(manifest.ManifestError) as cm:
                    manifest.find([folder.path])
                self.assertIn(word, str(cm.exception))

    def test_this_repositorys_streams(self):
        """The live streams carry a stale_after (ops.source_status judges them by it); idaho511_frames is
        judged by its status file instead (migration 0022)."""
        found = manifest.find([os.path.join(REPO, "plugins")])
        self.assertEqual(manifest.stream_staleness(found, "vrt_realtime"), ("1 hour", None))
        self.assertEqual(manifest.stream_staleness(found, "itd_wzdx"), ("30 minutes", None))
        stale, parts = manifest.stream_staleness(found, "idaho511_api")
        self.assertEqual(stale, "30 minutes")
        self.assertIn("idaho511_event", parts)
        self.assertIsNone(manifest.stream_staleness(found, "idaho511_frames"))

    def test_osm_consumers(self):
        def consumer(**kw):
            return {"source": "osm_x", "tags": ["w/highway=path,track", "r/route=hiking"],
                    "geometry": ["linestring", "relation"], "tables": ["t.osm_x"], **kw}

        def with_consumer(name, c, kind="manual", **source):
            osm = {"license": "ODbL", "credit": "© OpenStreetMap contributors", "republish": "yes", **source}
            return plugin(name, [entry("osm_x", kind=kind, **osm)], tables=["t.osm_x"], osm_consumers=[c])

        self.folder.write(with_consumer("good", consumer()))
        self.folder.write(with_consumer("lots", consumer(tags=["a/amenity=parking", "n/amenity=parking_space"],
                                                         geometry=["polygon", "point"])))
        self.folder.write(with_consumer("strict", consumer(), republish="internal"))    # stricter than yes is fine
        p = {p.name: p for p in manifest.find([self.folder.path])}
        self.assertEqual(p["good"].osm_consumers[0]["source"], "osm_x")
        self.assertEqual(len(p), 3)
        cases = [
            (with_consumer("a", consumer(), kind="source"), "manual"),
            (with_consumer("b", consumer(source="osm_y")), "manual"),
            (with_consumer("c", {**consumer(), "help": "x"}), "exactly"),
            (with_consumer("d", consumer(tags=["highway=path"])), "tags-filter"),
            (with_consumer("e", consumer(tags=["w/highway!=path"])), "tags-filter"),
            (with_consumer("f", consumer(tags=["ww/highway"])), "tags-filter"),
            (with_consumer("g", consumer(tags=[])), "tags"),
            (with_consumer("h", consumer(geometry=["multipolygon"])), "geometry"),
            (with_consumer("i", consumer(geometry=["linestring", "linestring"])), "geometry"),
            (with_consumer("j", consumer(tags=["w/highway=path"])), "relation needs"),
            (with_consumer("k", consumer(tables=["other.table"])), "tables"),
            (plugin("l", [entry("osm_x", kind="manual", license="ODbL", credit="© OpenStreetMap contributors")],
                    tables=["t.osm_x"], osm_consumers=[consumer(), consumer()]), "twice"),
            (plugin("m", [entry("osm_x", kind="manual")], tables=["t.osm_x"], osm_consumers={}), "list"),
            # The osm-landscape design's paving filter as written: osmium export would make no areas of it.
            (with_consumer("n", consumer(tags=["nwr/amenity=parking,parking_space"], geometry=["polygon"])),
             "polygon needs an a/"),
            (with_consumer("o", consumer(tags=["w/highway=service", "a/amenity=parking"], geometry=["linestring"])),
             "a/ expressions need geometry polygon"),
            (with_consumer("p", consumer(tags=["nw/barrier"], geometry=["linestring"])), "n/ expressions need"),
            (with_consumer("q", consumer(geometry=["linestring", "relation", "point"])), "point needs an n/"),
            (with_consumer("r", consumer(), license="CC0"), "ODbL"),
            (with_consumer("s", consumer(), credit="OSM"), "OpenStreetMap contributors"),
        ]
        for m, word in cases:
            with self.subTest(m["name"]):
                folder = Folder(self)
                folder.write(m)
                with self.assertRaises(manifest.ManifestError) as cm:
                    manifest.find([folder.path])
                self.assertIn(word, str(cm.exception))

    def test_folders_without_a_manifest_are_not_plugins(self):
        os.makedirs(os.path.join(self.folder.path, "notes"))
        os.makedirs(os.path.join(self.folder.path, "__pycache__"))
        self.assertEqual(manifest.find([self.folder.path]), [])


class PluginPathTest(unittest.TestCase):
    def test_private_plugins_import_as_plugins_dot_name(self):
        private = Folder(self)
        d = private.write(plugin("tvt_test_private", visibility="private"))
        with open(os.path.join(d, "__init__.py"), "w") as f:
            f.write("WHERE = 'private'\n")
        env = {**os.environ, "TVT_PLUGIN_PATH": os.pathsep.join([private.path, "/nonexistent/tvt-plugins"])}
        code = ("import plugins, plugins.tvt_test_private as p; from ingest import manifest; "
                "print(p.WHERE, [x.name for x in manifest.find() if x.name == 'tvt_test_private'])")
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "private ['tvt_test_private']")

    def test_without_the_variable_only_this_repository(self):
        env = {k: v for k, v in os.environ.items() if k != "TVT_PLUGIN_PATH"}
        out = subprocess.run([sys.executable, "-c", "import plugins; print(len(plugins.__path__))"], cwd=REPO, env=env,
                             capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
