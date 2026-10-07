"""Plugin manifests (docs/15 §15.2): find them, check them, put them in order.

Reads plugins/<name>/plugin.json in every folder of plugins.__path__ (this
repository's plugins/, plus the folders on TVT_PLUGIN_PATH for private
plugins) without importing any plugin code, so db/migrate.py can use it as
well as the ingest loader (ingest/sources/__init__.py).

A manifest:

    name, title     the folder's name (a Python identifier) and a title
    depends         plugins it builds on
    visibility      "public" or "private"
    order           where its sources run among plugins it doesn't depend on
                    (lower first; default 100)
    sources         its sources, in the order they run: {"name", "module"
                    (dotted, inside the plugin, e.g. "ingest.sources.achd_roads"),
                    "kind", "license", "credit", "republish"} and optionally
                    "order" (overrides the plugin's for this one entry)
    tables          the tables (and views) it owns, schema.table
    commands        optional extra `python3 -m ingest` subcommands: {"name",
                    "module", "help"} and optionally "function" (default main),
                    called with the arguments after the command's name
    storage, ethics short notes

Kinds: "source" (run by `run` and `serve`), "stream" (run continuously by
`stream`) and "manual" (loaded by hand with a plugin command; listed for its
license, never scheduled). republish: "yes", "aggregates", "internal" or "no".

Order. Plugins: dependencies first, then by order, then by name (migrations
use this). Sources and streams, each kind on its own: a plugin's entries run
in its manifest's order, and after every entry of the plugins it depends on
(directly or not); among entries free to run, the lowest order goes first,
then the plugin order, then the manifest order. Dependencies always win over
order numbers.
"""

import json
import os
import re
from dataclasses import dataclass, field

KINDS = ("source", "stream", "manual")
REPUBLISH = ("yes", "aggregates", "internal", "no")
VISIBILITY = ("public", "private")
DEFAULT_ORDER = 100
FILE = "plugin.json"

_FIELDS = {"name", "title", "depends", "visibility", "order", "sources", "tables", "commands", "storage", "ethics"}
_REQUIRED = {"name", "title", "depends", "visibility", "sources", "tables", "storage", "ethics"}
_ENTRY_FIELDS = {"name", "module", "kind", "license", "credit", "republish", "order"}
_COMMAND_FIELDS = {"name", "module", "help", "function"}
_MODULE = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
_TABLE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
_COMMAND = re.compile(r"^[a-z][a-z0-9-]*$")


class ManifestError(ValueError):
    pass


@dataclass
class Plugin:
    name: str
    folder: str
    manifest: dict = field(repr=False)

    @property
    def depends(self):
        return self.manifest["depends"]

    @property
    def order(self):
        return self.manifest.get("order", DEFAULT_ORDER)

    @property
    def visibility(self):
        return self.manifest["visibility"]

    def entries(self, kind):
        return [e for e in self.manifest["sources"] if e["kind"] == kind]


def plugin_folders():
    """The folders plugins live in: plugins.__path__ (this repository's plugins/, then TVT_PLUGIN_PATH)."""
    import plugins
    return list(plugins.__path__)


def load(folder):
    """Read and check one plugin's manifest. Raises ManifestError."""
    path = os.path.join(folder, FILE)
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError) as err:
        raise ManifestError(f"{path}: {err}") from None
    check_manifest(m, os.path.basename(os.path.normpath(folder)), path)
    return Plugin(m["name"], folder, m)


def check_manifest(m, folder_name, where):
    def bad(msg):
        raise ManifestError(f"{where}: {msg}")

    if not isinstance(m, dict):
        bad("not a JSON object")
    if missing := _REQUIRED - set(m):
        bad(f"missing {', '.join(sorted(missing))}")
    if extra := set(m) - _FIELDS:
        bad(f"unknown field(s) {', '.join(sorted(extra))}")
    name = m["name"]
    if not isinstance(name, str) or not name.isidentifier() or name != folder_name:
        bad(f"name {name!r} must be a Python identifier equal to its folder's name ({folder_name!r})")
    for key in ("title", "storage", "ethics"):
        if not isinstance(m[key], str) or not m[key].strip():
            bad(f"{key} must be a non-empty string")
    if not isinstance(m["depends"], list) or not all(isinstance(d, str) for d in m["depends"]):
        bad("depends must be a list of plugin names")
    if name in m["depends"]:
        bad("a plugin can't depend on itself")
    if m["visibility"] not in VISIBILITY:
        bad(f"visibility must be one of {', '.join(VISIBILITY)}")
    if not isinstance(m.get("order", DEFAULT_ORDER), int):
        bad("order must be an integer")
    if not isinstance(m["sources"], list):
        bad("sources must be a list")
    for i, e in enumerate(m["sources"]):
        label = f"sources[{i}]"
        if not isinstance(e, dict):
            bad(f"{label} must be an object")
        if missing := (_ENTRY_FIELDS - {"order"}) - set(e):
            bad(f"{label}: missing {', '.join(sorted(missing))}")
        if extra := set(e) - _ENTRY_FIELDS:
            bad(f"{label}: unknown field(s) {', '.join(sorted(extra))}")
        if not isinstance(e["module"], str) or not _MODULE.match(e["module"]):
            bad(f"{label}: module must be a dotted module path inside the plugin")
        if e["kind"] not in KINDS:
            bad(f"{label}: kind must be one of {', '.join(KINDS)}")
        if e["republish"] not in REPUBLISH:
            bad(f"{label}: republish must be one of {', '.join(REPUBLISH)}")
        for key in ("name", "license", "credit"):
            if not isinstance(e[key], str) or not e[key].strip():
                bad(f"{label}: {key} must be a non-empty string")
        if not isinstance(e.get("order", 0), int):
            bad(f"{label}: order must be an integer")
    names = [e["name"] for e in m["sources"]]
    if len(set(names)) != len(names):
        bad("a source is listed twice")
    if not isinstance(m["tables"], list) or not all(isinstance(t, str) and _TABLE.match(t) for t in m["tables"]):
        bad("tables must be a list of schema.table names")
    if len(set(m["tables"])) != len(m["tables"]):
        bad("a table is listed twice")
    commands = m.get("commands", [])
    if not isinstance(commands, list):
        bad("commands must be a list")
    for i, c in enumerate(commands):
        label = f"commands[{i}]"
        if not isinstance(c, dict) or {"name", "module", "help"} - set(c) or set(c) - _COMMAND_FIELDS:
            bad(f"{label} must have name, module and help (and optionally function)")
        if not isinstance(c["name"], str) or not _COMMAND.match(c["name"]):
            bad(f"{label}: name must be lower case, digits and dashes")
        if not isinstance(c["module"], str) or not _MODULE.match(c["module"]):
            bad(f"{label}: module must be a dotted module path inside the plugin")
        if not isinstance(c.get("function", "main"), str) or not c.get("function", "main").isidentifier():
            bad(f"{label}: function must be a Python name")


def find(folders=None):
    """Every plugin in the given folders (default: plugin_folders()), by name. Checks that
    names are unique and that every dependency is there; raises ManifestError."""
    found = {}
    for folder in plugin_folders() if folders is None else folders:
        if not os.path.isdir(folder):
            continue
        for entry in sorted(os.listdir(folder)):
            path = os.path.join(folder, entry)
            if not os.path.isfile(os.path.join(path, FILE)):
                continue
            plugin = load(path)
            if plugin.name in found:
                raise ManifestError(f"two plugins named {plugin.name}: {found[plugin.name].folder} and {path}")
            found[plugin.name] = plugin
    for plugin in found.values():
        for dep in plugin.depends:
            if dep not in found:
                raise ManifestError(f"plugin {plugin.name} depends on {dep}, which isn't installed")
    return [found[n] for n in sorted(found)]


def _kahn(nodes, preds, key):
    """Topological order: repeatedly take the node with the lowest key among those whose
    predecessors are all done. Raises ManifestError on a cycle."""
    done, out, left = set(), [], list(nodes)
    while left:
        ready = [n for n in left if preds(n) <= done]
        if not ready:
            raise ManifestError("dependency cycle among: " + ", ".join(sorted(str(n) for n in left)))
        n = min(ready, key=key)
        left.remove(n)
        done.add(n)
        out.append(n)
    return out


def plugin_order(plugins):
    """Plugins with every dependency first; ties by order, then name."""
    by_name = {p.name: p for p in plugins}
    names = _kahn(list(by_name), lambda n: set(by_name[n].depends),
                  lambda n: (by_name[n].order, n))
    return [by_name[n] for n in names]


def closure(plugins, name):
    """Every plugin `name` depends on, directly or not."""
    by_name = {p.name: p for p in plugins}
    out, todo = set(), list(by_name[name].depends)
    while todo:
        d = todo.pop()
        if d not in out:
            out.add(d)
            todo.extend(by_name[d].depends)
    return out


def entry_order(plugins, kind):
    """[(plugin, entry)] of one kind, in run order (see the module docstring)."""
    ordered = plugin_order(plugins)
    rank = {p.name: i for i, p in enumerate(ordered)}
    nodes, entries = [], {}
    for p in ordered:
        for i, e in enumerate(p.entries(kind)):
            nodes.append((p.name, i))
            entries[(p.name, i)] = (p, e)
    deps = {p.name: closure(ordered, p.name) for p in ordered}

    def preds(node):
        name, i = node
        before = {(name, i - 1)} if i else set()
        return before | {n for n in nodes if n[0] in deps[name]}

    def key(node):
        p, e = entries[node]
        return (e.get("order", p.order), rank[p.name], node[1])

    return [entries[n] for n in _kahn(nodes, preds, key)]
