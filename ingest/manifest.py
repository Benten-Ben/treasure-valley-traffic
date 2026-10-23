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
                    "order" (overrides the plugin's for this one entry); a "stream" may
                    also have "stale_after" (e.g. "10 minutes": the longest age of its
                    last good fetch that still reads fresh; ops.source_status judges
                    the stream by it) and, with it, "fetch_sources" (other sources whose
                    fetches count as the stream's: idaho511_api logs one per endpoint)
    tables          the tables (and views) it owns, schema.table
    commands        optional extra `python3 -m ingest` subcommands: {"name",
                    "module", "help"} and optionally "function" (default main),
                    called with the arguments after the command's name
    osm_consumers   optional: what it reads from the OpenStreetMap extract that
                    `python3 -m ingest osm-load` loads (ingest/osm_extract.py):
                    {"source" (one of its "manual" sources: name, module,
                    license, credit and republish live there; the license is
                    ODbL and the credit "© OpenStreetMap contributors"), "tags"
                    (in osmium's tags-filter syntax, e.g.
                    "w/highway=residential,road"; n/ nodes, w/ ways as lines,
                    a/ closed ways and multipolygons as areas, r/ relations),
                    "geometry" (what it gets: "point", "linestring", "polygon",
                    "relation", one for each type its tags name: n/ point, w/
                    linestring, a/ polygon, r/ relation), "tables" (the tables
                    it writes, from its own tables)}
    storage, ethics short notes

Kinds: "source" (run by `run` and `serve`), "stream" (run continuously by
`stream`) and "manual" (loaded by hand, with a plugin command or as one of its
osm_consumers; listed for its license, never scheduled). republish: "yes",
"aggregates", "internal" or "no".

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

_FIELDS = {"name", "title", "depends", "visibility", "order", "sources", "tables", "commands", "osm_consumers",
           "storage", "ethics"}
_REQUIRED = {"name", "title", "depends", "visibility", "sources", "tables", "storage", "ethics"}
_ENTRY_FIELDS = {"name", "module", "kind", "license", "credit", "republish", "order", "stale_after", "fetch_sources"}
_COMMAND_FIELDS = {"name", "module", "help", "function"}
_CONSUMER_FIELDS = {"source", "tags", "geometry", "tables"}
OSM_GEOMETRY = ("point", "linestring", "polygon", "relation")
OSM_TYPE_GEOMETRY = {"n": "point", "w": "linestring", "a": "polygon", "r": "relation"}   # what each type gives
OSM_LICENSE, OSM_CREDIT = "ODbL", "OpenStreetMap contributors"
# An osmium tags-filter expression, the subset consumers use: object types (n, w, r, a for
# areas), a key, and optionally values: "w/highway", "n/crossing:signals=yes",
# "nwr/amenity=parking,parking_space". No "!=", wildcards or regular expressions.
OSM_TAG_EXPRESSION = re.compile(r"^(?P<types>[nwra]{1,4})/(?P<key>[A-Za-z0-9_:.-]+)"
                                r"(?:=(?P<values>[A-Za-z0-9_:.;-]+(?:,[A-Za-z0-9_:.;-]+)*))?$")
# A Postgres interval a stream may be left alone for: a whole number and one unit.
STALE_AFTER = re.compile(r"^[1-9][0-9]{0,5} (second|minute|hour|day)s?$")
_SOURCE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
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

    @property
    def osm_consumers(self):
        return self.manifest.get("osm_consumers", [])


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
        if missing := (_ENTRY_FIELDS - {"order", "stale_after", "fetch_sources"}) - set(e):
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
        if "stale_after" in e:
            if e["kind"] != "stream":
                bad(f"{label}: stale_after is for streams (a source has a schedule)")
            if not isinstance(e["stale_after"], str) or not STALE_AFTER.match(e["stale_after"]):
                bad(f"{label}: stale_after must be a number and a unit, like \"10 minutes\" "
                    "(seconds, minutes, hours or days)")
        if "fetch_sources" in e:
            fs = e["fetch_sources"]
            if "stale_after" not in e:
                bad(f"{label}: fetch_sources needs stale_after")
            if (not isinstance(fs, list) or not fs or len(set(fs)) != len(fs)
                    or not all(isinstance(x, str) and _SOURCE_NAME.match(x) for x in fs)):
                bad(f"{label}: fetch_sources must be a list of distinct source names")
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
    check_osm_consumers(m, bad)


def check_osm_consumers(m, bad):
    consumers = m.get("osm_consumers", [])
    if not isinstance(consumers, list):
        bad("osm_consumers must be a list")
    manual = {e["name"]: e for e in m["sources"] if e["kind"] == "manual"}
    seen = set()
    for i, c in enumerate(consumers):
        label = f"osm_consumers[{i}]"
        if not isinstance(c, dict) or set(c) != _CONSUMER_FIELDS:
            bad(f"{label} must have exactly source, tags, geometry and tables")
        if c["source"] not in manual:
            bad(f"{label}: source must name one of its own \"manual\" sources")
        source = manual[c["source"]]
        if source["license"] != OSM_LICENSE or OSM_CREDIT not in source["credit"]:
            bad(f"{label}: {c['source']} reads OpenStreetMap, so its source's license must be {OSM_LICENSE} and its "
                f"credit \"© {OSM_CREDIT}\" (republish may be stricter than yes)")
        if c["source"] in seen:
            bad(f"{label}: {c['source']} is consumed twice")
        seen.add(c["source"])
        tags = c["tags"]
        if not isinstance(tags, list) or not tags or not all(isinstance(t, str) for t in tags):
            bad(f"{label}: tags must be a non-empty list of osmium tags-filter expressions")
        for t in tags:
            match = OSM_TAG_EXPRESSION.match(t)
            if not match or len(set(match["types"])) != len(match["types"]):
                bad(f"{label}: {t!r} isn't a tags-filter expression we take (TYPES/KEY or TYPES/KEY=V1,V2; "
                    "types from n, w, r, a)")
        geometry = c["geometry"]
        if (not isinstance(geometry, list) or not geometry or len(set(geometry)) != len(geometry)
                or not set(geometry) <= set(OSM_GEOMETRY)):
            bad(f"{label}: geometry must be a list of {', '.join(OSM_GEOMETRY)}")
        # Each type its tags name gives one geometry, and each geometry needs its type: osmium export
        # makes areas only from a/ expressions, so geometry polygon with w/ or nwr/ ones gets nothing.
        types = {t for e in tags for t in OSM_TAG_EXPRESSION.match(e)["types"]}
        problems = [f"geometry {g} needs {'a' if t == 'w' else 'an'} {t}/ expression in tags"
                    for t, g in OSM_TYPE_GEOMETRY.items() if g in geometry and t not in types]
        problems += [f"its {t}/ expressions need geometry {g} (or drop the {t} type)"
                     for t, g in OSM_TYPE_GEOMETRY.items() if t in types and g not in geometry]
        if problems:
            bad(f"{label}: " + "; ".join(problems))
        tables = c["tables"]
        if not isinstance(tables, list) or not tables or not set(tables) <= set(m["tables"]):
            bad(f"{label}: tables must list the tables it writes, each one of the plugin's own tables")


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


def stream_staleness(plugins, name):
    """(stale_after, fetch_sources) of the stream `name` from the manifests, or None when it has no
    stale_after (not a stream, or one judged some other way, like idaho511_frames)."""
    for p in plugins:
        for e in p.entries("stream"):
            if e["name"] == name and "stale_after" in e:
                return e["stale_after"], e.get("fetch_sources")
    return None


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
