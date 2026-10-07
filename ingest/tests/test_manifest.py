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
