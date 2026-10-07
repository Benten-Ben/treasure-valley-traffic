"""The registry: SOURCES, STREAMS and COMMANDS, built from the plugin manifests.

Every plugins/<name>/plugin.json (and those on TVT_PLUGIN_PATH, for private
plugins) lists its sources; ingest/manifest.py checks and orders them.

SOURCES run once per call (`run`), or on their schedule (`serve`), in this
order: a plugin's sources after those of the plugins it depends on, otherwise
by the manifests' order numbers. So `run all` loads cameras before their
views, and the signal sources, cameras and crossings before the intersection
build that joins them; the COMPASS data sources come last, so the long crash
download doesn't delay the daily intersection build. STREAMS run continuously
(`stream`), each as its own service. COMMANDS are the plugins' own
`python3 -m ingest` subcommands, imported only when called.
"""

import importlib

from .. import manifest

PLUGINS = manifest.plugin_order(manifest.find())
SOURCES = {}       # name: module (each with SOURCE and run(conn))
STREAMS = {}       # name: module (each with SOURCE and stream())
PLUGIN_OF = {}     # source or stream name: plugin name


def module(plugin, dotted):
    """A plugin's module by its dotted path inside the plugin (e.g. "ingest.sources.vrt_gtfs")."""
    return importlib.import_module(f"plugins.{plugin.name}.{dotted}")


for _kind, _registry in (("source", SOURCES), ("stream", STREAMS)):
    for _plugin, _entry in manifest.entry_order(PLUGINS, _kind):
        _module = module(_plugin, _entry["module"])
        _name = _module.SOURCE["name"]
        if _name != _entry["name"]:
            raise manifest.ManifestError(f"plugin {_plugin.name}: {_entry['module']} registers {_name!r}, "
                                         f"but the manifest lists {_entry['name']!r}")
        if _name in PLUGIN_OF:
            raise manifest.ManifestError(f"{_name} is registered by both {PLUGIN_OF[_name]} and {_plugin.name}")
        _registry[_name] = _module
        PLUGIN_OF[_name] = _plugin.name

# Loaded by hand through a plugin command, never scheduled: listed for their licenses, not imported here.
MANUAL = manifest.entry_order(PLUGINS, "manual")

COMMANDS = {}      # name: (plugin, its manifest entry)
for _plugin in PLUGINS:
    for _command in _plugin.manifest.get("commands", []):
        if _command["name"] in COMMANDS:
            raise manifest.ManifestError(f"command {_command['name']} is registered by both "
                                         f"{COMMANDS[_command['name']][0].name} and {_plugin.name}")
        COMMANDS[_command["name"]] = (_plugin, _command)


def command(name):
    """The function behind a plugin command; it takes the arguments after the command's name."""
    plugin, entry = COMMANDS[name]
    return getattr(module(plugin, entry["module"]), entry.get("function", "main"))
