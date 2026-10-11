"""Export manifests (C5): what a plugin's export folder holds, under which licence, and from which inputs.

A plugin's export command writes files to $TVT_ARCHIVE/<plugin>/export/<build>/ and then manifest.json, last, with
write(): an export folder without a manifest is unfinished and readers skip it. The ground (basemap/ground/) and the
base bake (basemap/landscape/) read exports only through read() and latest(). Standard library only, so it runs in
the ingest image that writes the exports as well as in the worker image that reads them.

    {
      "contract": 1,
      "plugin": "soils",
      "build": "20261012T031500Z",              # the folder's name: a UTC time, optionally -suffix
      "created": "2026-10-12T03:15:00Z",
      "command": "python3 -m ingest soils-export",   # optional
      "inputs": [                                # every source the layers were made from
        {"name": "ssurgo", "licence": "public-domain", "republish": "yes",
         "credit": "USDA NRCS Soil Survey Geographic Database (SSURGO)", "version": "FY2027"}
      ],
      "layers": [
        {"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "crs": "EPSG:32611",
         "geometry": "MultiPolygon", "features": 21999, "fields": {"id": "int", "ground_type": "int"},
         "bytes": 1234567, "sha256": "...", "inputs": ["ssurgo"], "licence": "public-domain",
         "republish": "yes", "credit": ["USDA NRCS Soil Survey Geographic Database (SSURGO)"], "base": false}
      ]
    }

Layers are vectors (FlatGeobuf, in the grid's CRS, EPSG:32611). The two non-vector exports are a JSON table
(soils' palette.json: "schema" names its shape) and a GeoTIFF on the ground grid (farm's crop_cover.tif: "grid" and
"bands"). Licences and republish (C3, C17):
- every input names a licence from LICENCES and a republish value no looser than that licence allows;
- a layer's republish is at least as strict as each of its inputs' (strictest wins), its credit carries every
  input's credit, and a layer with a share-alike input (ODbL) is ODbL itself;
- `base: true` marks a layer for the base bake (S5b): a FlatGeobuf with an integer `id` field (MapLibre's promoteId).
republish values are plugin.json's (docs/15): yes, aggregates, internal, no, from loosest to strictest.
"""

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field

from basemap.ground import fgb, grid

CONTRACT = 1
FILE = "manifest.json"
REPUBLISH = ("yes", "aggregates", "internal", "no")          # loosest to strictest
FORMATS = {"FlatGeobuf": (".fgb",), "GeoTIFF": (".tif", ".tiff"), "JSON": (".json",)}
GEOMETRIES = ("Point", "LineString", "Polygon", "MultiPoint", "MultiLineString", "MultiPolygon")
RASTER_TYPES = ("uint8", "int8", "uint16", "int16", "uint32", "int32", "float32", "float64")


@dataclass(frozen=True)
class Licence:
    loosest: str          # the loosest republish value this licence allows
    share_alike: bool     # derived layers must carry the same licence
    about: str


# Licence classes. Add one here (in review) before an export can name it.
LICENCES = {
    "public-domain": Licence("yes", False, "US federal works: USGS (3DEP, NHD), USDA (NAIP, NASS's CDL and CSB, "
                                           "NRCS's SSURGO)"),
    "CC0-1.0": Licence("yes", False, "e.g. ITD's WZDx work zones (owner, Oct 6)"),
    "ODbL-1.0": Licence("yes", True, "OpenStreetMap, and Overture's buildings. Derived databases stay ODbL; a produced "
                                     "work (tiles, images) credits it"),
    "CC-BY-4.0": Licence("yes", False, "e.g. the HydroShare canal network (cite its creators and DOI)"),
    "CDLA-Permissive-2.0": Licence("yes", False, "e.g. Overture's themes other than buildings"),
    "Copernicus": Licence("yes", False, "Sentinel data: free, full and open use; credit 'Contains modified "
                                        "Copernicus Sentinel data <year>'"),
    "none-stated": Licence("aggregates", False, "agency data with no licence grant (ACHD, ITD's tables, IDWR, Ridge "
                                                "to Rivers, the City's trails): internal, or aggregates in public "
                                                "where the owner allowed it"),
    "restricted": Licence("no", False, "data we may use but never publish (private plugins)"),
}

_TOP = {"contract", "plugin", "build", "created", "command", "inputs", "layers", "note"}
_TOP_REQUIRED = {"contract", "plugin", "build", "created", "inputs", "layers"}
_INPUT = {"name", "licence", "republish", "credit", "version", "url", "doi", "sha256", "retrieved", "note"}
_INPUT_REQUIRED = {"name", "licence", "republish", "credit"}
_LAYER_COMMON = {"name", "file", "format", "bytes", "sha256", "inputs", "licence", "republish", "credit", "base"}
_LAYER_OPTIONAL = {"title", "note"}
_LAYER_FORMAT = {"FlatGeobuf": {"crs", "geometry", "fields", "features"},
                 "GeoTIFF": {"crs", "grid", "bands"},
                 "JSON": {"schema"}}
_LAYER_FORMAT_OPTIONAL = {"FlatGeobuf": {"minzoom", "maxzoom"}, "GeoTIFF": set(), "JSON": set()}
_GRID = {"res", "west", "north", "width", "height"}
_BAND = {"name", "type", "nodata", "values", "about"}

BUILD_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z(-[a-z0-9][a-z0-9-]*)?$")
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_INPUT_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    pass


def rank(republish):
    """0 for yes ... 3 for no."""
    return REPUBLISH.index(republish)


def strictest(values):
    """The strictest of some republish values ("yes" for none)."""
    return max(values, key=rank, default="yes")


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def build_id(when=None, suffix=None):
    """A build folder's name: the UTC time, e.g. 20261012T031500Z, optionally with -suffix."""
    b = (when or now_utc()).astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{b}-{suffix}" if suffix else b


def export_dir(archive, plugin, build):
    return os.path.join(archive, plugin, "export", build)


# --- checking ---------------------------------------------------------------------------------------------------

def check(m, where="manifest", folder=None):
    """Check a manifest's shape and its licence rules. Raises ManifestError naming the first problem. folder, when
    given, is the export folder: its name must be the build id."""

    def bad(msg):
        raise ManifestError(f"{where}: {msg}")

    if not isinstance(m, dict):
        bad("not a JSON object")
    if missing := _TOP_REQUIRED - set(m):
        bad(f"missing {', '.join(sorted(missing))}")
    if extra := set(m) - _TOP:
        bad(f"unknown field(s) {', '.join(sorted(extra))}")
    if m["contract"] != CONTRACT or isinstance(m["contract"], bool):
        bad(f"contract {m['contract']!r}: this reader knows contract {CONTRACT}")
    if not isinstance(m["plugin"], str) or not m["plugin"].isidentifier():
        bad("plugin must be the plugin's name")
    if not isinstance(m["build"], str) or not BUILD_RE.match(m["build"]):
        bad(f"build {m['build']!r} must look like 20261012T031500Z (optionally -suffix)")
    if folder is not None and os.path.basename(os.path.normpath(folder)) != m["build"]:
        bad(f"build {m['build']!r} isn't the folder's name ({os.path.basename(os.path.normpath(folder))!r})")
    try:
        dt.datetime.strptime(m["created"], "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        bad("created must be a UTC time like 2026-10-12T03:15:00Z")
    for key in ("command", "note"):
        if key in m and (not isinstance(m[key], str) or not m[key].strip()):
            bad(f"{key} must be a non-empty string")

    inputs = m["inputs"]
    if not isinstance(inputs, list) or not inputs:
        bad("inputs must be a non-empty list")
    by_name = {}
    for i, e in enumerate(inputs):
        label = f"inputs[{i}]"
        if not isinstance(e, dict):
            bad(f"{label} must be an object")
        if missing := _INPUT_REQUIRED - set(e):
            bad(f"{label}: missing {', '.join(sorted(missing))}")
        if extra := set(e) - _INPUT:
            bad(f"{label}: unknown field(s) {', '.join(sorted(extra))}")
        if not isinstance(e["name"], str) or not _INPUT_NAME.match(e["name"]):
            bad(f"{label}: name must be lower case letters, digits, '.', '_' or '-'")
        label = f"input {e['name']!r}"
        if e["name"] in by_name:
            bad(f"{label} is listed twice")
        _check_licence(bad, label, e["licence"], e["republish"])
        if not isinstance(e["credit"], str) or not e["credit"].strip():
            bad(f"{label}: credit must be a non-empty string")
        for key in _INPUT - _INPUT_REQUIRED:
            if key in e and (not isinstance(e[key], str) or not e[key].strip()):
                bad(f"{label}: {key} must be a non-empty string")
        if "sha256" in e and not _SHA.match(e["sha256"]):
            bad(f"{label}: sha256 must be 64 lower-case hex digits")
        by_name[e["name"]] = e

    layers = m["layers"]
    if not isinstance(layers, list) or not layers:
        bad("layers must be a non-empty list")
    names, files, used = set(), set(), set()
    for i, lay in enumerate(layers):
        if not isinstance(lay, dict):
            bad(f"layers[{i}] must be an object")
        label = f"layer {lay.get('name')!r}" if isinstance(lay.get("name"), str) else f"layers[{i}]"
        fmt = lay.get("format")
        if fmt not in FORMATS:
            bad(f"{label}: format must be one of {', '.join(FORMATS)}")
        required = _LAYER_COMMON | _LAYER_FORMAT[fmt]
        if missing := required - set(lay):
            bad(f"{label}: missing {', '.join(sorted(missing))}")
        if extra := set(lay) - required - _LAYER_OPTIONAL - _LAYER_FORMAT_OPTIONAL[fmt]:
            bad(f"{label}: unknown field(s) for a {fmt} layer: {', '.join(sorted(extra))}")
        if not isinstance(lay["name"], str) or not _NAME.match(lay["name"]):
            bad(f"{label}: name must be lower case letters, digits and '_'")
        if lay["name"] in names:
            bad(f"{label} is listed twice")
        names.add(lay["name"])
        f = lay["file"]
        if (not isinstance(f, str) or not f or f != os.path.basename(f) or "\\" in f or f.startswith(".")
                or f == FILE):
            bad(f"{label}: file must be a plain file name in the export folder")
        if not f.lower().endswith(FORMATS[fmt]):
            bad(f"{label}: a {fmt} file ends in {' or '.join(FORMATS[fmt])}")
        if f in files:
            bad(f"{label}: file {f} is listed twice")
        files.add(f)
        if not isinstance(lay["bytes"], int) or isinstance(lay["bytes"], bool) or lay["bytes"] < 0:
            bad(f"{label}: bytes must be a whole number")
        if not isinstance(lay["sha256"], str) or not _SHA.match(lay["sha256"]):
            bad(f"{label}: sha256 must be 64 lower-case hex digits")
        for key in ("title", "note"):
            if key in lay and (not isinstance(lay[key], str) or not lay[key].strip()):
                bad(f"{label}: {key} must be a non-empty string")

        # licence, republish, credit: the strictest of the layer's inputs
        lin = lay["inputs"]
        if not isinstance(lin, list) or not lin or not all(isinstance(n, str) for n in lin) or len(set(lin)) != len(lin):
            bad(f"{label}: inputs must be a non-empty list of input names, each once")
        for n in lin:
            if n not in by_name:
                bad(f"{label}: input {n!r} isn't in the manifest's inputs")
        used.update(lin)
        _check_licence(bad, label, lay["licence"], lay["republish"])
        for n in lin:
            src = by_name[n]
            if rank(lay["republish"]) < rank(src["republish"]):
                bad(f"{label}: republish {lay['republish']!r} is looser than input {n!r} ({src['republish']!r})")
            if LICENCES[src["licence"]].share_alike and lay["licence"] != src["licence"]:
                bad(f"{label}: input {n!r} is {src['licence']} (share-alike), so the layer must be too")
        credit = lay["credit"]
        if not isinstance(credit, list) or not credit or not all(isinstance(c, str) and c.strip() for c in credit):
            bad(f"{label}: credit must be a non-empty list of strings")
        for n in lin:
            if by_name[n]["credit"] not in credit:
                bad(f"{label}: credit lacks input {n!r}'s credit ({by_name[n]['credit']!r})")
        if not isinstance(lay["base"], bool):
            bad(f"{label}: base must be true or false")

        if fmt == "FlatGeobuf":
            _check_vector(bad, label, lay)
        elif fmt == "GeoTIFF":
            _check_raster(bad, label, lay)
        else:
            s = lay["schema"]
            if not isinstance(s, str) or not re.match(rf"^{re.escape(m['plugin'])}\.[a-z][a-z0-9_]*/[0-9]+$", s):
                bad(f"{label}: schema must look like {m['plugin']}.<name>/<version>")
        if lay["base"] and fmt != "FlatGeobuf":
            bad(f"{label}: only FlatGeobuf layers can go into the base bake")
    if unused := set(by_name) - used:
        bad(f"input(s) no layer uses: {', '.join(sorted(unused))}")


def _check_licence(bad, label, licence, republish):
    if licence not in LICENCES:
        bad(f"{label}: licence {licence!r} isn't one of {', '.join(LICENCES)} (add it to LICENCES in review)")
    if republish not in REPUBLISH:
        bad(f"{label}: republish must be one of {', '.join(REPUBLISH)}")
    if rank(republish) < rank(LICENCES[licence].loosest):
        bad(f"{label}: republish {republish!r} is looser than {licence} allows ({LICENCES[licence].loosest!r})")


def _check_vector(bad, label, lay):
    if lay["crs"] != grid.CRS:
        bad(f"{label}: crs must be {grid.CRS} (the ground grid's), not {lay['crs']!r}")
    if lay["geometry"] not in GEOMETRIES:
        bad(f"{label}: geometry must be one of {', '.join(GEOMETRIES)}")
    if not isinstance(lay["features"], int) or isinstance(lay["features"], bool) or lay["features"] < 0:
        bad(f"{label}: features must be a whole number")
    flds = lay["fields"]
    if not isinstance(flds, dict):
        bad(f"{label}: fields must be an object of name: type")
    for k, v in flds.items():
        if not _FIELD.match(k):
            bad(f"{label}: field name {k!r} must be letters, digits and '_'")
        if v not in fgb.COLUMN_TYPES:
            bad(f"{label}: field {k!r} has type {v!r}, not one of {', '.join(fgb.COLUMN_TYPES)}")
    for key in ("minzoom", "maxzoom"):
        if key in lay and (not isinstance(lay[key], int) or isinstance(lay[key], bool) or not 0 <= lay[key] <= 22):
            bad(f"{label}: {key} must be a zoom from 0 to 22")
    if lay.get("minzoom", 0) > lay.get("maxzoom", 22):
        bad(f"{label}: minzoom is above maxzoom")
    if lay["base"] and flds.get("id") not in fgb.INTEGER_TYPES:
        bad(f"{label}: a base layer needs an integer 'id' field (the bake's promoteId)")


def _check_raster(bad, label, lay):
    if lay["crs"] != grid.CRS:
        bad(f"{label}: crs must be {grid.CRS} (the ground grid's), not {lay['crs']!r}")
    g = lay["grid"]
    if not isinstance(g, dict) or set(g) != _GRID:
        bad(f"{label}: grid must have exactly {', '.join(sorted(_GRID))}")
    for key in ("width", "height"):
        if not isinstance(g[key], int) or isinstance(g[key], bool) or g[key] <= 0:
            bad(f"{label}: grid {key} must be a positive whole number")
    for key in ("res", "west", "north"):
        if not isinstance(g[key], (int, float)) or isinstance(g[key], bool):
            bad(f"{label}: grid {key} must be a number")
    if not grid.aligned((g["west"], g["res"], 0.0, g["north"], 0.0, -g["res"]), g["res"]):
        bad(f"{label}: the raster isn't on the ground grid ({g['res']} m cells from E {grid.ORIGIN_X} "
            f"N {grid.ORIGIN_Y})")
    bands = lay["bands"]
    if not isinstance(bands, list) or not bands:
        bad(f"{label}: bands must be a non-empty list")
    seen = set()
    for j, b in enumerate(bands):
        if not isinstance(b, dict) or {"name", "type"} - set(b) or set(b) - _BAND:
            bad(f"{label}: bands[{j}] needs name and type (and optionally nodata, values, about)")
        if not isinstance(b["name"], str) or not _NAME.match(b["name"]) or b["name"] in seen:
            bad(f"{label}: bands[{j}] needs a unique lower-case name")
        seen.add(b["name"])
        if b["type"] not in RASTER_TYPES:
            bad(f"{label}: band {b['name']!r} type must be one of {', '.join(RASTER_TYPES)}")
        if "nodata" in b and (not isinstance(b["nodata"], (int, float)) or isinstance(b["nodata"], bool)):
            bad(f"{label}: band {b['name']!r} nodata must be a number")
        vals = b.get("values", {})
        if not isinstance(vals, dict) or not all(re.match(r"^-?[0-9]+$", k) and isinstance(v, str) and v.strip()
                                                 for k, v in vals.items()):
            bad(f"{label}: band {b['name']!r} values must map whole-number codes to labels")


# --- reading ----------------------------------------------------------------------------------------------------

@dataclass
class Layer:
    plugin: str
    build: str
    path: str                  # the file's full path
    spec: dict = field(repr=False)

    @property
    def name(self):
        return self.spec["name"]

    @property
    def ref(self):
        """'soils/ground@20261012T031500Z'."""
        return f"{self.plugin}/{self.name}@{self.build}"

    def __getitem__(self, key):
        return self.spec[key]

    def get(self, key, default=None):
        return self.spec.get(key, default)


@dataclass
class Manifest:
    folder: str
    data: dict = field(repr=False)

    @property
    def plugin(self):
        return self.data["plugin"]

    @property
    def build(self):
        return self.data["build"]

    @property
    def inputs(self):
        """name -> input entry."""
        return {e["name"]: e for e in self.data["inputs"]}

    @property
    def layers(self):
        return [Layer(self.plugin, self.build, os.path.join(self.folder, lay["file"]), lay)
                for lay in self.data["layers"]]

    def layer(self, name):
        for lay in self.layers:
            if lay.name == name:
                return lay
        raise KeyError(f"{self.plugin}@{self.build} has no layer {name!r}")

    def has(self, name):
        return any(lay["name"] == name for lay in self.data["layers"])

    @property
    def republish(self):
        """The strictest republish of its layers."""
        return strictest(lay["republish"] for lay in self.data["layers"])

    @property
    def credits(self):
        """Every layer's credit, once each, in order."""
        out = []
        for lay in self.data["layers"]:
            for c in lay["credit"]:
                if c not in out:
                    out.append(c)
        return out


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path, verify=True, hashes=True):
    """Read and check an export's manifest (path: the export folder or its manifest.json). verify also checks each
    file: it exists, has its bytes and (with hashes) its sha256, and a FlatGeobuf's header agrees with its entry."""
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    mpath = os.path.join(folder, FILE)
    try:
        with open(mpath, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as err:
        raise ManifestError(f"{mpath}: {err}") from None
    check(data, mpath, folder)
    m = Manifest(folder, data)
    if verify:
        for lay in m.layers:
            verify_layer(lay, hashes=hashes)
    return m


def verify_layer(lay, hashes=True):
    """Check one layer's file against its manifest entry. Raises ManifestError."""
    where = f"{lay.ref} ({lay.path})"
    try:
        size = os.path.getsize(lay.path)
    except OSError as err:
        raise ManifestError(f"{where}: {err}") from None
    if size != lay["bytes"]:
        raise ManifestError(f"{where}: {size} bytes, the manifest says {lay['bytes']}")
    if hashes and sha256_of(lay.path) != lay["sha256"]:
        raise ManifestError(f"{where}: sha256 differs from the manifest's")
    if lay["format"] == "FlatGeobuf":
        try:
            h = fgb.read_header(lay.path)
        except fgb.FgbError as err:
            raise ManifestError(f"{where}: {err}") from None
        check_header(where, lay.spec, h)


def check_header(where, spec, h):
    """A FlatGeobuf header against its manifest entry. The header may leave the geometry type (Unknown), the feature
    count (0, as without a spatial index) or the CRS unstated; whatever it states must match."""
    if h.geometry_type != "Unknown" and h.geometry_type != spec["geometry"]:
        raise ManifestError(f"{where}: the file holds {h.geometry_type}, the manifest says {spec['geometry']}")
    if h.has_z or h.has_m:
        raise ManifestError(f"{where}: exports are 2D (the file has Z or M)")
    if h.columns != spec["fields"]:
        raise ManifestError(f"{where}: the file's fields {h.columns} differ from the manifest's {spec['fields']}")
    if h.features_count and h.features_count != spec["features"]:
        raise ManifestError(f"{where}: the file holds {h.features_count} features, the manifest says "
                            f"{spec['features']}")
    if h.crs and h.crs != spec["crs"]:
        raise ManifestError(f"{where}: the file's CRS is {h.crs}, the manifest says {spec['crs']}")


def builds(archive, plugin):
    """The plugin's finished export builds (folders with a manifest), oldest first."""
    root = os.path.join(archive, plugin, "export")
    if not os.path.isdir(root):
        return []
    return sorted(b for b in os.listdir(root)
                  if BUILD_RE.match(b) and os.path.isfile(os.path.join(root, b, FILE)))


def latest(archive, plugin, verify=True, hashes=True):
    """The plugin's newest finished export, read and checked; None when it has none. A newest export that fails its
    checks raises ManifestError rather than falling back to an older one silently."""
    b = builds(archive, plugin)
    return read(export_dir(archive, plugin, b[-1]), verify=verify, hashes=hashes) if b else None


def find(archive, verify=True, hashes=True):
    """Every plugin's newest export under the archive: {plugin: Manifest}."""
    out = {}
    if not os.path.isdir(archive):
        return out
    for plugin in sorted(os.listdir(archive)):
        if plugin.isidentifier() and os.path.isdir(os.path.join(archive, plugin, "export")):
            m = latest(archive, plugin, verify=verify, hashes=hashes)
            if m is not None:
                out[plugin] = m
    return out


# --- writing ----------------------------------------------------------------------------------------------------

def write(folder, plugin, inputs, layers, build=None, created=None, command=None, note=None):
    """Write an export's manifest.json after its files, filling in what the files say: bytes and sha256 for every
    layer; for a FlatGeobuf, its geometry type, fields and feature count from the header when the layer doesn't give
    them; credit (every input's), republish (the strictest input's) and licence (a share-alike input's, or the one
    licence all its inputs share) when not given. The manifest is checked before it's written, and written
    atomically, last. Returns the Manifest.

    inputs: [{"name", "licence", "republish", "credit", ...}]; layers: [{"name", "file", "format", "inputs",
    "base", ...}] (for FlatGeobuf, "crs" defaults to the grid's). build defaults to the folder's name."""
    build = build or os.path.basename(os.path.normpath(folder))
    by_name = {e["name"]: e for e in inputs}
    out_layers = []
    for spec in layers:
        lay = dict(spec)
        path = os.path.join(folder, lay["file"])
        lay["bytes"] = os.path.getsize(path)
        lay["sha256"] = sha256_of(path)
        srcs = [by_name[n] for n in lay.get("inputs", []) if n in by_name]
        if "credit" not in lay:
            lay["credit"] = list(dict.fromkeys(s["credit"] for s in srcs))
        if "licence" not in lay:
            every = {s["licence"] for s in srcs}
            shared = {name for name in every if name in LICENCES and LICENCES[name].share_alike}
            if len(shared) == 1:
                lay["licence"] = shared.pop()
            elif len(every) == 1:
                lay["licence"] = every.pop()
            else:
                raise ManifestError(f"layer {lay['name']!r}: its inputs have several licences ({sorted(every)}); "
                                    "name the layer's licence")
        if "republish" not in lay:
            values = [s["republish"] for s in srcs if s.get("republish") in REPUBLISH]
            if lay["licence"] in LICENCES:
                values.append(LICENCES[lay["licence"]].loosest)
            lay["republish"] = strictest(values)
        if lay.get("format") == "FlatGeobuf":
            lay.setdefault("crs", grid.CRS)
            try:
                h = fgb.read_header(path)
            except fgb.FgbError as err:
                raise ManifestError(str(err)) from None
            if "geometry" not in lay:
                if h.geometry_type not in GEOMETRIES:
                    raise ManifestError(f"layer {lay['name']!r}: the file's geometry type is {h.geometry_type}; "
                                        "name the layer's geometry")
                lay["geometry"] = h.geometry_type
            lay.setdefault("fields", dict(h.columns))
            if "features" not in lay:
                if not h.features_count:
                    raise ManifestError(f"layer {lay['name']!r}: the file doesn't state its feature count (write it "
                                        "with a spatial index, ST_AsFlatGeobuf(q, true, 'geom')) or give features")
                lay["features"] = h.features_count
        out_layers.append(lay)
    m = {"contract": CONTRACT, "plugin": plugin, "build": build,
         "created": (created or now_utc()).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if command:
        m["command"] = command
    if note:
        m["note"] = note
    m["inputs"] = [dict(e) for e in inputs]
    m["layers"] = out_layers
    check(m, os.path.join(folder, FILE), folder)
    result = Manifest(folder, m)
    for lay in result.layers:
        if lay["format"] == "FlatGeobuf":
            check_header(lay.ref, lay.spec, fgb.read_header(lay.path))
    fd, tmp = tempfile.mkstemp(prefix=".manifest-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=1, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(folder, FILE))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return result
