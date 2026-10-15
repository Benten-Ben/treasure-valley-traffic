"""The ingest image holds what its commands import (ingest/Dockerfile and the repository's .dockerignore).

Lays out the image's /repo in a temporary folder from the Dockerfile's COPY lines, less what .dockerignore leaves out
of the build context, and there, in a new interpreter that can't see this checkout, imports the registry (every
source and stream) and every command: core's and this repository's plugins'. A command that imports repository code
the image lacks fails here, not at a deploy (water-export's basemap.landscape, review of P4-data, Oct 11).

A third-party package missing from the interpreter running the tests (psycopg on a bare laptop) isn't this test's
business: the image installs ingest/requirements.txt. Such modules are skipped and named.

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCKERFILE = os.path.join(REPO, "ingest", "Dockerfile")
DOCKERIGNORE = os.path.join(REPO, ".dockerignore")


def copy_lines(path):
    """[(source, destination)] from a Dockerfile's plain COPY lines (no --from), relative to the context and WORKDIR."""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 3 and parts[0].upper() == "COPY" and not parts[1].startswith("--"):
                out.append((parts[1].rstrip("/"), parts[2].rstrip("/")))
    return out


def _pattern(pat):
    """A .dockerignore pattern as a regex over a slash-separated path: '**' any number of folders, '*' and '?'
    within one name."""
    pat = pat.strip("/")
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(out + r"\Z")


def ignore_rules(path):
    """[(exception, regex)] in order, from a .dockerignore."""
    rules = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            exception = line.startswith("!")
            rules.append((exception, _pattern(line[1:] if exception else line)))
    return rules


def ignored(rel, rules):
    """Docker's rule: the last pattern matching the path or one of its folders decides."""
    parts = rel.split("/")
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    out = False
    for exception, rx in rules:
        if any(rx.match(p) for p in prefixes):
            out = not exception
    return out


def lay_out(dest, repo=REPO):
    """The image's /repo as the Dockerfile builds it, under dest. Returns the files copied (relative paths)."""
    rules = ignore_rules(os.path.join(repo, ".dockerignore"))
    copied = []
    for src, dst in copy_lines(os.path.join(repo, "ingest", "Dockerfile")):
        root = os.path.join(repo, src)
        if os.path.isfile(root):
            pairs = [(src, dst)]
        else:
            pairs = []
            for folder, dirs, files in os.walk(root):
                dirs.sort()
                for name in sorted(files):
                    rel = os.path.relpath(os.path.join(folder, name), repo).replace(os.sep, "/")
                    pairs.append((rel, dst + rel[len(src):]))
        for rel, to in pairs:
            if ignored(rel, rules):
                continue
            target = os.path.join(dest, to)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(os.path.join(repo, rel), target)
            copied.append(to)
    return copied


CHILD = r"""
import importlib, json, sys
out = {"ok": [], "missing": [], "error": []}

def attempt(label, fn):
    try:
        fn()
        out["ok"].append(label)
    except ModuleNotFoundError as e:
        out["missing"].append([label, e.name or str(e)])
    except Exception as e:
        out["error"].append([label, f"{type(e).__name__}: {e}"])

registry = {}
def load_registry():
    from ingest import sources
    from ingest.__main__ import CORE_COMMANDS
    registry["sources"], registry["core"] = sources, CORE_COMMANDS
attempt("the registry (ingest.sources)", load_registry)
if "sources" in registry:
    for name, (module, _) in sorted(registry["core"].items()):
        attempt(f"core command {name}", lambda m=module: importlib.import_module(m).main)
    for name in sorted(registry["sources"].COMMANDS):
        attempt(f"command {name}", lambda n=name: registry["sources"].command(n))
print(json.dumps(out))
"""


class LayoutTest(unittest.TestCase):
    def test_dockerignore_rules(self):
        rules = ignore_rules(DOCKERIGNORE)
        self.assertFalse(ignored("ingest/http.py", rules))
        self.assertTrue(ignored("ingest/tests/test_image.py", rules))
        self.assertTrue(ignored("plugins/water/ingest/__pycache__/build.cpython-312.pyc", rules))
        self.assertTrue(ignored("app/package.json", rules))
        self.assertFalse(ignored("basemap/ground/manifest.py", rules))
        self.assertTrue(ignored("basemap/ground/tests/test_manifest.py", rules))
        self.assertTrue(ignored("basemap/sheets/sheet.py", rules))

    def test_pattern(self):
        self.assertTrue(_pattern("**/__pycache__").match("a/b/__pycache__"))
        self.assertTrue(_pattern("**/__pycache__").match("__pycache__"))
        self.assertTrue(_pattern("plugins/*/tests").match("plugins/water/tests"))
        self.assertFalse(_pattern("plugins/*/tests").match("plugins/water/ingest/tests"))


class ImageImportTest(unittest.TestCase):
    def test_every_command_imports_with_only_the_images_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied = lay_out(tmp)
            self.assertIn("ingest/__main__.py", copied)
            self.assertFalse(any("/tests/" in c for c in copied))
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "TVT_PLUGIN_PATH")}
            run = subprocess.run([sys.executable, "-B", "-c", CHILD], cwd=tmp, env=env, capture_output=True,
                                 text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            got = json.loads(run.stdout.strip().splitlines()[-1])
        ours = set(os.listdir(REPO))
        lacking = [(label, name) for label, name in got["missing"] if name.split(".")[0] in ours]
        self.assertEqual(lacking, [], "repository code the ingest image doesn't carry")
        self.assertEqual(got["error"], [])
        third_party = sorted({name for _, name in got["missing"] if name.split(".")[0] not in ours})
        if third_party:
            print(f"\n(test_image: not installed here, so not checked: {', '.join(third_party)})", file=sys.stderr)
        if not third_party:
            self.assertIn("command water-export", got["ok"])


if __name__ == "__main__":
    unittest.main()
