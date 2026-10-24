"""What the base bake reads and what it promises (plan C4, C17; package S5b). Standard library only.

Base contributions (water, paving, road surfaces and markings, piece lines, paved paths) draw for every viewer from
z8 to z16, so they're baked after each build into one versioned PMTiles file served from /tiles/, not cut live. The
bake reads the export manifests (basemap/ground/manifest.py): every layer marked `base: true` in each plugin's
newest export becomes one source-layer of `landscape-<digest>.pmtiles`, named `<plugin>.<layer>` (the same key as
core.layer_version's toggled layers).

The rules a base layer meets, beyond the export contract's (a FlatGeobuf with an integer `id`):
- its plugin is a public plugin (plugin.json's visibility), and so is every plugin its inputs name a source of:
  private plugins' data is never tiled (docs/15 §15.3);
- its republish is yes or internal. Sources published only as aggregates (Ridge to Rivers, the City's trails) and
  restricted data stay in side tables that cards read, never in the base (C17);
- none of its inputs is a source NEVER names (IDWR's and the City of Boise's, whatever their republish: C17);
- its fields are numbers, strings or booleans (what a vector tile holds), each `id` unique, from 0 to 2^53 - 1
  (MapLibre's promoteId, the canal season's feature-state);
- each feature's geometry is the layer's type or its multi form (GEOMETRY_FAMILY);
- an integer `minzoom` field, if it has one, is each feature's first zoom (water's ditches from z13, its main canals
  from z10): a bake directive, left out of the tiles.

A base layer whose export holds no features is read (it's in the digest and the entry's `empty`) but not built: the
file has no such source-layer, and the entry's `layers` don't list it, so the app treats it as not built.

The bake's republish is the strictest of its built layers'. While any is internal (roads' widths come from ACHD and
ITD), the file is **tailnet-only**: its tiles-manifest entry and its own metadata say `"access": "tailnet"`, and
`bake.py check --public` fails on it, so a public deploy can refuse it.
"""

import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field

from basemap import lock
from basemap.ground import fgb, grid, inputs as ground_inputs, manifest as M, tiles as ground_tiles

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec.json")
with open(SPEC_PATH, encoding="utf-8") as _f:
    SPEC = json.load(_f)

SPEC_VERSION = SPEC["spec"]
ENTRY = SPEC["entry"]                          # the key in tiles/manifest.json
MINZOOM, MAXZOOM = SPEC["minzoom"], SPEC["maxzoom"]
FORMAT = SPEC["format"]
PROMOTE_ID = SPEC["promoteId"]
WRITER = SPEC["writer"]
KEEP = SPEC["keep"]
BUDGET = SPEC["budget"]

# Bump when the bake writes different tiles from the same inputs and spec (it goes into every file's name).
BAKE_VERSION = 1

ID_FIELD = "id"
MINZOOM_FIELD = "minzoom"
MAX_ID = 2 ** 53 - 1                           # JavaScript's largest safe integer
TILE_TYPES = fgb.INTEGER_TYPES + ("float", "double", "string", "bool")
BAKED = ("yes", "internal")                    # the republish values a base layer may have
FILE_RE = re.compile(r"^landscape-([0-9a-f]{12})\.pmtiles$")
PART_PREFIX = ".landscape-"
SOURCE_LAYER_RE = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z][a-z0-9_]*$")

# The geometries a layer's features may have: its declared type or its multi form (either way round), as PostGIS's
# ST_AsFlatGeobuf mixes them. Collections, curves and other dimensions are refused feature by feature.
GEOMETRY_FAMILY = {t: (t.removeprefix("Multi"), "Multi" + t.removeprefix("Multi")) for t in M.GEOMETRIES}

# Plugin sources whose data never goes into the base, whatever their republish (C17; plan §0 item 11): IDWR's canal
# operators and season windows, and the City of Boise's layers (Ridge to Rivers' names, the City's trail and river
# attributes) stay in side tables that cards read. Patterns over an input's "<plugin>/<source>" (fnmatch, case
# sensitive). A source whose plugin.json credit names IDWR or the City must match one: test_plan checks every
# plugin.json in the repository.
NEVER = {
    "*/idwr*": "IDWR's data (canal operators, the legal season window)",
    "water/canal_season": "the canal season (lifecycles drawn as feature-state, some from IDWR's legal window)",
    "*/boise_*": "a City of Boise layer",
    "trails/r2r_*": "Ridge to Rivers' trails",
    "trails/trails_match": "the trails match (the City's lines linked to OpenStreetMap's)",
}


class BakeError(ValueError):
    pass


def access_of(republish):
    """Who may be served a bake with this republish: 'public' only when every layer may be republished."""
    return "public" if republish == "yes" else "tailnet"


@dataclass
class Base:
    """One base layer of an export: one source-layer of the bake."""
    layer: M.Layer

    @property
    def id(self):
        """The source-layer's name: '<plugin>.<layer>'."""
        return f"{self.layer.plugin}.{self.layer.name}"

    @property
    def ref(self):
        return self.layer.ref

    @property
    def minzoom(self):
        return min(max(self.layer.get("minzoom", MINZOOM), MINZOOM), MAXZOOM)

    @property
    def maxzoom(self):
        return min(self.layer.get("maxzoom", MAXZOOM), MAXZOOM)

    @property
    def per_feature_minzoom(self):
        return MINZOOM_FIELD in self.layer["fields"]

    @property
    def fields(self):
        """The fields the tiles carry (name: type): every field but the minzoom directive."""
        return {k: v for k, v in self.layer["fields"].items() if k != MINZOOM_FIELD}

    def summary(self, features=None):
        """Its row in the entry's layers."""
        return {"plugin": self.layer.plugin, "layer": self.layer.name, "build": self.layer.build,
                "geometry": self.layer["geometry"],
                "features": self.layer["features"] if features is None else features,
                "fields": self.fields, "minzoom": self.minzoom, "maxzoom": self.maxzoom,
                "licence": self.layer["licence"], "republish": self.layer["republish"],
                "credit": list(self.layer["credit"])}


@dataclass
class Plan:
    bases: list = field(default_factory=list)           # [Base], by source-layer id
    skipped: list = field(default_factory=list)          # [(plugin, why)]: exports that hold no base layer

    @property
    def built(self):
        """The base layers with features: the file's source-layers. The writer checks each count against the file."""
        return [b for b in self.bases if b.layer["features"]]

    @property
    def empty(self):
        """The source-layers read whose export holds no features: not built, so not in the file or the entry's
        layers."""
        return [b.id for b in self.bases if not b.layer["features"]]

    @property
    def ids(self):
        return [b.id for b in self.built]

    @property
    def status(self):
        return "baked" if self.built else "empty"

    @property
    def reason(self):
        if not self.bases:
            return "no plugin exports a base layer yet"
        return "" if self.built else "every base layer is empty: " + ", ".join(self.empty)

    def why_not_built(self, sid):
        """Why this plan doesn't build source-layer sid ('<plugin>.<layer>'), which a served bake has."""
        plugin, _, layer = sid.partition(".")
        for b in self.bases:
            if b.id == sid:
                return f"{b.ref} is empty"
        for p, why in self.skipped:
            if p == plugin:
                return why
        mine = [b for b in self.bases if b.layer.plugin == plugin]
        if mine:
            return f"{plugin}@{mine[0].layer.build} has no base layer {layer!r}"
        return f"there's no export of {plugin}"

    @property
    def republish(self):
        return M.strictest(b.layer["republish"] for b in self.built)

    @property
    def access(self):
        return access_of(self.republish)

    @property
    def internal(self):
        """[(source-layer, its credits)] of the layers that keep the bake off the public internet."""
        return [(b.id, b.layer["credit"]) for b in self.built if b.layer["republish"] != "yes"]

    @property
    def licences(self):
        """The built layers' licences, strictest first (manifest.strictness), each once."""
        names = {b.layer["licence"] for b in self.built}
        return sorted(names, key=lambda n: (tuple(-x for x in M.strictness(n)), n))

    @property
    def credits(self):
        """Every built layer's credit, once each, in layer order: the bake's attribution."""
        out = []
        for b in self.built:
            for c in b.layer["credit"]:
                if c not in out:
                    out.append(c)
        return out

    @property
    def refs(self):
        """Every base layer read, empty ones included: the bake's inputs."""
        return [b.ref for b in self.bases]

    @property
    def roads(self):
        """Whether roads' base layers are built: the downtown budget binds from then on."""
        return any(b.layer.plugin == "roads" for b in self.built)


# --- reading ----------------------------------------------------------------------------------------------------

def plugin_visibility(folders=None):
    """{plugin: 'public' | 'private'} from every plugin.json (this repository's and TVT_PLUGIN_PATH's)."""
    try:
        from ingest import manifest as plugin_manifest
    except ImportError as err:
        raise BakeError(f"can't read the plugins' manifests to check who owns an export ({err})") from None
    try:
        return {p.name: p.visibility for p in plugin_manifest.find(folders)}
    except plugin_manifest.ManifestError as err:
        raise BakeError(f"can't read the plugins' manifests ({err})") from None


class Exports(dict):
    """{plugin: Manifest} of the exports the bake reads, with `skipped`: [(plugin, why)] for those it doesn't."""

    def __init__(self):
        super().__init__()
        self.skipped = []


def names_no_base(folder):
    """Whether an export's manifest plainly holds no base layer: it parses, and every layer says "base": false.
    Anything else (a base layer, or a manifest that isn't plain) is read and checked in full."""
    try:
        with open(os.path.join(folder, M.FILE), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        return False
    layers = m.get("layers") if isinstance(m, dict) else None
    return (isinstance(layers, list) and bool(layers)
            and all(isinstance(lay, dict) and lay.get("base") is False for lay in layers))


def exports(archive, registry=None):
    """The newest export of each plugin that has a base layer, its manifest checked but its files not yet: an
    Exports ({plugin: Manifest}, with .skipped). An export whose manifest plainly holds no base layer isn't the bake's
    business and isn't checked, so a broken or private-sourced export of another plugin can't hold the bake up; any
    other newest manifest that fails its checks raises ManifestError (the bake can't tell what it would hold). The
    ground's own products (mask v0, the box classes) are never read. Raises BakeError when the archive folder is
    missing."""
    if not archive or not os.path.isdir(archive):
        raise BakeError(f"no archive folder at {archive!r} (give --archive or set TVT_ARCHIVE)")
    out = Exports()
    for plugin in sorted(os.listdir(archive)):
        if plugin in ground_inputs.PRODUCTS or not plugin.isidentifier():
            continue
        builds = M.builds(archive, plugin)
        if not builds:
            continue
        if names_no_base(M.export_dir(archive, plugin, builds[-1])):
            out.skipped.append((plugin, f"{plugin}@{builds[-1]} has no base layer"))
            continue
        out[plugin] = M.latest(archive, plugin, verify=False, registry=registry)
    return out


def never(source):
    """Why a plugin source ("<plugin>/<source>") may never go into the base, or None."""
    for pattern, what in NEVER.items():
        if fnmatch.fnmatchcase(source, pattern):
            return what
    return None


def check_base(lay, visibility, inputs=None):
    """Raise BakeError unless an export's base layer may be baked (the rules in the module docstring).
    lay: manifest.Layer; visibility: {plugin: 'public' | 'private'} from every plugin.json; inputs: the export's
    inputs by name (manifest.Manifest.inputs), whose plugin sources are checked."""
    where = lay.ref
    if visibility.get(lay.plugin) is None:
        raise BakeError(f"{where}: no plugin.json names plugin {lay.plugin!r}, so who may see its data is unknown")
    if visibility[lay.plugin] != "public":
        raise BakeError(f"{where}: {lay.plugin} is a private plugin, and private data is never tiled "
                        "(docs/15 §15.3)")
    if lay["format"] != "FlatGeobuf":
        raise BakeError(f"{where}: only FlatGeobuf layers are baked")
    if lay["republish"] not in BAKED:
        raise BakeError(f"{where}: republish {lay['republish']!r}. Sources published only as aggregates, and "
                        "restricted data, stay in side tables that cards read, never in the base (C17)")
    for name in lay["inputs"]:
        source = (inputs or {}).get(name, {}).get("source")
        if source is None:
            continue
        if what := never(source):
            raise BakeError(f"{where}: input {name!r} is {source}, {what}: it stays in side tables that cards "
                            "read, never in the base (C17)")
        owner = source.split("/", 1)[0]
        if visibility.get(owner) != "public":
            raise BakeError(f"{where}: input {name!r} is {source}, a source of "
                            + ("a private plugin" if visibility.get(owner) else f"{owner!r}, which no plugin.json "
                               "names") + ", and private data is never tiled (docs/15 §15.3)")
    flds = lay["fields"]
    if flds.get(ID_FIELD) not in fgb.INTEGER_TYPES:
        raise BakeError(f"{where}: a base layer needs an integer {ID_FIELD!r} field (the bake's promoteId)")
    for name, kind in flds.items():
        if kind not in TILE_TYPES:
            raise BakeError(f"{where}: field {name!r} is {kind}; vector tiles hold numbers, strings and booleans "
                            f"({', '.join(TILE_TYPES)})")
    if MINZOOM_FIELD in flds and flds[MINZOOM_FIELD] not in fgb.INTEGER_TYPES:
        raise BakeError(f"{where}: {MINZOOM_FIELD!r} is each feature's first zoom, so it must be an integer")
    if lay.get("maxzoom", MAXZOOM) < MINZOOM:
        raise BakeError(f"{where}: maxzoom {lay['maxzoom']} is below the bake's first zoom ({MINZOOM})")


def resolve(manifests, visibility=None, verify=True, hashes=True):
    """The bake's plan from exports(): each export's base layers, checked (check_base) and, with verify, their files
    against their manifests (size, sha256, header). visibility: {plugin: 'public' | 'private'}
    (plugin_visibility() when None and there's a base layer). Raises BakeError or ManifestError."""
    plan = Plan(skipped=list(getattr(manifests, "skipped", [])))
    for plugin in sorted(manifests):
        m = manifests[plugin]
        base = [lay for lay in m.layers if lay["base"]]
        if not base:
            plan.skipped.append((plugin, f"{plugin}@{m.build} has no base layer"))
            continue
        if visibility is None:
            visibility = plugin_visibility()
        for lay in base:
            check_base(lay, visibility, m.inputs)
            if verify:
                M.verify_layer(lay, hashes=hashes)
            plan.bases.append(Base(lay))
    plan.bases.sort(key=lambda b: b.id)
    return plan


# --- the file and its entry -------------------------------------------------------------------------------------

def digest(plan, writer):
    """The bake's version: sha256 over the spec, the bake's own version, the writer (GDAL's version) and every base
    layer's reference, zooms and sha256. The same exports give the same name; a new export, spec or writer gives a
    new one."""
    if not plan.bases:
        raise ValueError("an empty plan has nothing to bake")
    with open(SPEC_PATH, encoding="utf-8") as f:
        spec_text = f.read()
    h = hashlib.sha256()
    h.update(spec_text.encode("utf-8"))
    h.update(f"\nbake {BAKE_VERSION}\nwriter {writer}\n".encode("utf-8"))
    for b in plan.bases:
        h.update(f"layer {b.id} {b.ref} {b.layer['sha256']} z{b.minzoom}-{b.maxzoom}\n".encode("utf-8"))
    return h.hexdigest()


def file_name(digest_hex):
    return SPEC["file"].format(digest=digest_hex[:12])


def budget_tiles():
    """[(z, x, y)] the budget covers: every z16 tile touching the downtown box."""
    z = BUDGET["zoom"]
    xs, ys = ground_tiles.tile_range(grid.lonlat_of(grid.box(BUDGET["box"]).utm), z)
    return [(z, x, y) for y in ys for x in xs]


def measure_budget(sizes, roads):
    """The budget's result from {(z, x, y): stored bytes} of the budget's tiles (tiles without data are absent)."""
    worst = max(sizes.items(), key=lambda kv: (kv[1], kv[0]), default=None)
    return {"zoom": BUDGET["zoom"], "box": BUDGET["box"], "maxBytes": BUDGET["maxBytes"],
            "tiles": len(sizes), "largest": worst[1] if worst else 0,
            "at": "/".join(map(str, worst[0])) if worst else None, "roads": bool(roads)}


def over_budget(sizes):
    """[((z, x, y), bytes)] of the budget's tiles over it, largest first."""
    return sorted(((t, n) for t, n in sizes.items() if n > BUDGET["maxBytes"]), key=lambda kv: (-kv[1], kv[0]))


def baked_entry(plan, digest_hex, budget, writer, zooms=(MINZOOM, MAXZOOM), built=None):
    """The bake's entry, as its file's metadata holds it (the tiles manifest adds `previous`). Its layers are the
    built ones (with features); `empty` names the others. zooms: the lowest and highest zoom the file holds tiles at
    (its header's)."""
    if not plan.built:
        raise ValueError("a bake with no features is an empty entry")
    return {
        "status": "baked",
        "file": file_name(digest_hex),
        "digest": digest_hex,
        "format": FORMAT,
        "minzoom": zooms[0],
        "maxzoom": zooms[1],
        "promoteId": PROMOTE_ID,
        "layers": {b.id: b.summary() for b in plan.built},
        "empty": plan.empty,
        "attribution": "; ".join(plan.credits),
        "licences": plan.licences,
        "republish": plan.republish,
        "access": plan.access,
        "inputs": plan.refs,
        "budget": budget,
        "writer": writer,
        "built": built or dt.date.today().isoformat(),
        "spec": SPEC_VERSION,
    }


def empty_entry(reason, previous=None, built=None):
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("an empty bake says why")
    return {"status": "empty", "reason": reason.strip(), "previous": previous,
            "built": built or dt.date.today().isoformat(), "spec": SPEC_VERSION}


_BAKED_KEYS = {"status", "file", "digest", "format", "minzoom", "maxzoom", "promoteId", "layers", "empty",
               "attribution", "licences", "republish", "access", "inputs", "budget", "writer", "built", "spec"}
_LAYER_KEYS = {"plugin", "layer", "build", "geometry", "features", "fields", "minzoom", "maxzoom", "licence",
               "republish", "credit"}


def check_entry(e, in_manifest=True):
    """Raise ValueError unless e is a landscape entry the app can read: a tiles-manifest entry (with `previous`),
    or with in_manifest False, the copy a baked file's metadata holds (without it)."""
    try:
        _check_entry(e, in_manifest)
    except (KeyError, TypeError, AttributeError) as err:
        raise ValueError(f"the landscape entry is malformed ({err!r})") from None


def _check_entry(e, in_manifest):
    if not isinstance(e, dict) or e.get("status") not in ("baked", "empty"):
        raise ValueError("the landscape entry's status must be baked or empty")
    if e["status"] == "empty":
        if set(e) != {"status", "reason", "previous", "built", "spec"} or not str(e["reason"]).strip():
            raise ValueError("an empty entry has exactly status, reason, previous, built and spec, with a reason")
        if e["previous"] is not None and not FILE_RE.match(str(e["previous"])):
            raise ValueError("previous must be a landscape file's name or null")
        return
    need = _BAKED_KEYS | ({"previous"} if in_manifest else set())
    if set(e) != need:
        raise ValueError(f"a baked entry has exactly {', '.join(sorted(need))}")
    m = FILE_RE.match(str(e["file"]))
    if not m or not re.match(r"^[0-9a-f]{64}$", str(e["digest"])) or m.group(1) != e["digest"][:12]:
        raise ValueError("file must be landscape-<the digest's first 12 hex digits>.pmtiles")
    if in_manifest and e["previous"] is not None and (not FILE_RE.match(str(e["previous"]))
                                                      or e["previous"] == e["file"]):
        raise ValueError("previous must be another landscape file's name, or null")
    if (e["format"], e["promoteId"], e["spec"]) != (FORMAT, PROMOTE_ID, SPEC_VERSION):
        raise ValueError("the entry doesn't match the bake's spec (format, promoteId)")
    if not (isinstance(e["minzoom"], int) and isinstance(e["maxzoom"], int)
            and MINZOOM <= e["minzoom"] <= e["maxzoom"] <= MAXZOOM):
        raise ValueError(f"the entry's zooms must lie in z{MINZOOM}-{MAXZOOM}")
    layers = e["layers"]
    if not isinstance(layers, dict) or not layers:
        raise ValueError("a baked entry has at least one layer")
    for sid, lay in layers.items():
        if not isinstance(lay, dict) or set(lay) != _LAYER_KEYS:
            raise ValueError(f"layer {sid!r} has exactly {', '.join(sorted(_LAYER_KEYS))}")
        if sid != f"{lay['plugin']}.{lay['layer']}" or not SOURCE_LAYER_RE.match(sid):
            raise ValueError(f"layer {sid!r} isn't named <plugin>.<layer>")
        if not isinstance(lay["features"], int) or isinstance(lay["features"], bool) or lay["features"] < 1:
            raise ValueError(f"layer {sid!r} has no features: an empty layer isn't built, so it's listed in empty")
        if lay["republish"] not in BAKED:
            raise ValueError(f"layer {sid!r} is republish {lay['republish']!r}: never baked")
        if lay["fields"].get(ID_FIELD) not in fgb.INTEGER_TYPES:
            raise ValueError(f"layer {sid!r} has no integer {ID_FIELD!r}")
        if not MINZOOM <= lay["minzoom"] <= lay["maxzoom"] <= MAXZOOM:
            raise ValueError(f"layer {sid!r}'s zooms are outside z{MINZOOM}-{MAXZOOM}")
        for c in lay["credit"]:
            if c not in e["attribution"]:
                raise ValueError(f"the attribution lacks layer {sid!r}'s credit {c!r}")
    empty = e["empty"]
    if (not isinstance(empty, list) or empty != sorted(set(empty))
            or not all(isinstance(s, str) and SOURCE_LAYER_RE.match(s) for s in empty) or set(empty) & set(layers)):
        raise ValueError("empty must list the empty source-layers, sorted, each once, none of them in layers")
    strictest = M.strictest(lay["republish"] for lay in layers.values())
    if e["republish"] != strictest:
        raise ValueError(f"republish must be the strictest of the layers' ({strictest!r})")
    if e["access"] != access_of(e["republish"]):
        raise ValueError(f"access must be {access_of(e['republish'])!r} for a republish-{e['republish']} bake")
    if sorted(e["licences"]) != sorted({lay["licence"] for lay in layers.values()}):
        raise ValueError("licences must list every layer's licence")
    b = e["budget"]
    if not isinstance(b, dict) or b.get("maxBytes") != BUDGET["maxBytes"] or b.get("largest", 0) > b["maxBytes"]:
        raise ValueError("the budget must be the spec's, and met")


# --- tiles/manifest.json ----------------------------------------------------------------------------------------

def locked(name=lock.LANDSCAPE, tiles=None):
    """An exclusive lock (basemap/lock.py: a file in the lock folder, not the served tiles folder), held for the block.
    `tiles` is the tiles folder the block writes (a host run outside the checkout needs TVT_TILES_LOCK_DIR)."""
    return lock.locked(name, tiles)


def read_tiles_manifest(tiles_dir):
    path = os.path.join(tiles_dir, "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
    except FileNotFoundError:
        raise BakeError(f"no {path}: build the basemap first (basemap/build.sh)") from None
    except ValueError as err:
        raise BakeError(f"{path}: {err}") from None
    if not isinstance(m, dict):
        raise BakeError(f"{path} isn't a JSON object")
    return m


def current(tiles_dir):
    """The tiles manifest's landscape entry, or None."""
    return read_tiles_manifest(tiles_dir).get(ENTRY)


def update_manifest(tiles_dir, entry):
    """Put the landscape entry into tiles/manifest.json atomically (the app fetches it with no-cache), keeping every
    other entry as it is."""
    check_entry(entry)
    with locked(lock.MANIFEST, tiles_dir):
        m = read_tiles_manifest(tiles_dir)
        m[ENTRY] = entry
        fd, tmp = tempfile.mkstemp(prefix=".manifest-", suffix=".json", dir=tiles_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(m, f, indent=1, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, os.path.join(tiles_dir, "manifest.json"))
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        fsync_dir(tiles_dir)
    return os.path.join(tiles_dir, "manifest.json")


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def files(tiles_dir):
    """Every landscape file in the tiles folder, by name."""
    return sorted(f for f in os.listdir(tiles_dir) if FILE_RE.match(f))


def prune(tiles_dir, entry):
    """Delete every landscape file but the entry's and its previous one (the last two), and any unfinished bake's
    part files. Returns the names removed."""
    keep = {entry.get("file"), entry.get("previous")} - {None}
    gone = []
    for f in os.listdir(tiles_dir):
        if (FILE_RE.match(f) and f not in keep) or f.startswith(PART_PREFIX):
            os.unlink(os.path.join(tiles_dir, f))
            gone.append(f)
    return sorted(gone)
