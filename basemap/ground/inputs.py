"""What the ground reads, and the rule that keeps it public (C5, C6, C17). Standard library only.

The ground is an ODbL produced work built from public inputs only, so every tile of it may be republished. It reads
three kinds of input:
- USES, plugin export layers (manifest.py): soils' ground and palette, farm's crop cover and fields, water's mask,
  each with a fallback for when the plugin hasn't exported yet;
- PRODUCTS, the ground's own products, written through the same export contract so that their inputs, licences and
  sha256 are declared and checked: mask v0 (S5a-2) and the 0.5 m land-cover classes in the ten boxes;
- RAW, source files: the only sources a product may be made from, and the ones the painter reads directly, which it
  names with their versions (resolve(..., versions=)) so a new release gives a new tile name (tiles.digest).

Every one must be republish "yes": resolve() refuses an export layer (or any input behind it) that isn't, rather
than quietly making the ground internal, and refuses a product made from anything outside RAW. The roads build is
never read, because its widths come from ACHD and ITD (internal); the ground keeps OSM's class widths instead (C6).

Without soils' `ground` layer or mask v0 there is nothing to paint on: the ground stays today's flat Valley and Clay
ground and says so (tiles.flat_entry). Every other input has a fallback, named in the plan resolve() returns.

    python3 basemap/ground/ground.py status --archive $TVT_ARCHIVE    # what the ground would read today
"""

import os
from dataclasses import dataclass, field

from basemap.ground import fgb, grid, manifest as M, maskrules

GROUND_LICENCE = "ODbL-1.0"
GROUND_ABOUT = "ODbL produced work"


@dataclass(frozen=True)
class Raw:
    """A source the ground's products or its painter read from files, outside any plugin export."""
    name: str
    licence: str
    republish: str
    credit: str
    what: str

    def entry(self, version=None):
        """As a manifest input (a product's manifest names its raw inputs this way)."""
        e = {"name": self.name, "licence": self.licence, "republish": self.republish, "credit": self.credit}
        if version:
            e["version"] = version
        return e


RAW = (
    Raw("osm", "ODbL-1.0", "yes", "© OpenStreetMap contributors",
        "S1's cut of the held Idaho extract, read through GDAL's OSM driver (mask v0). The extract has no Oregon, "
        "so the box's Malheur slice has no OSM"),
    Raw("overture-buildings", "ODbL-1.0", "yes", "Overture Maps Foundation, © OpenStreetMap contributors",
        "roof footprints for mask v0, as the map's buildings.pmtiles holds them at z15 (built by "
        "basemap/buildings.py from the release it names)"),
    Raw("nhd", "public-domain", "yes", "U.S. Geological Survey, National Hydrography Dataset",
        "NHD HU4 1705 (GeoPackage), water for mask v0 until water's export lands"),
    Raw("cdl", "public-domain", "yes", "USDA NASS Cropland Data Layer",
        "CDL 2025 (10 m): crop pixels, and developed land (classes 123-124) for mask v0"),
    Raw("csb", "public-domain", "yes", "USDA NASS Crop Sequence Boundaries",
        "CSB 2025 field polygons, the crop fallback until farm's crop_cover lands (C7)"),
    Raw("naip", "public-domain", "yes", "USDA NAIP",
        "NAIP 2025 county mosaics (0.3 m) for Ada and Canyon; NAIP 2023 (0.6 m) in boxes h-j"),
    Raw("3dep", "public-domain", "yes", "U.S. Geological Survey, 3D Elevation Program",
        "the 2023-24 QL1 lidar products in the class boxes, and the DEM for slope and aspect"),
    Raw("sentinel-2", "Copernicus", "yes", "Contains modified Copernicus Sentinel data 2025",
        "the July 2025 NDVI median on the 10 m grid"),
    Raw("rcmap", "public-domain", "yes",
        "U.S. Geological Survey, Rangeland Condition Monitoring Assessment and Projection (RCMAP)",
        "RCMAP fractional cover (30 m), which calibrates the box classes' bare cut. The spike's copy has no "
        "recorded origin, and its version (v7 or v8) is to be confirmed"),
)
RAW_BY_NAME = {r.name: r for r in RAW}


@dataclass(frozen=True)
class Use:
    """An export the ground reads: one layer of a plugin's export, or every layer of one of its own products
    (layer None). fallback None means the ground can't paint without it."""
    plugin: str                          # the export's folder under $TVT_ARCHIVE (a plugin, or a product's name)
    layer: str
    format: str
    label: str                           # what it is, in plain words (the flat ground's reason uses it)
    what: str                            # what the ground takes from it
    by: str                              # the package that makes it
    fallback: str = None                 # what the ground uses until it exists
    fallback_reads: tuple = ()           # the RAW inputs that fallback reads (their versions go into the digest)
    geometry: tuple = ()                 # allowed geometry types (FlatGeobuf)
    fields: tuple = ()                   # ((field, allowed types), ...) that must be present (FlatGeobuf)
    res: float = None                    # the grid level (GeoTIFF)
    bands: tuple = ()                    # band names, in order (GeoTIFF)
    schema: str = None                   # the JSON shape
    boxes: bool = False                  # one GeoTIFF per class box, named by its id, exactly on the box's window
    raw_only: bool = False               # a product: made only from RAW inputs, under RAW's licences
    required: tuple = ()                 # a product: the layers it must have

    @property
    def ref(self):
        return f"{self.plugin}/{self.layer}" if self.layer else self.plugin

    @property
    def product(self):
        return self.layer is None


_INT = fgb.INTEGER_TYPES
_REAL = ("float", "double")
_AREAS = ("Polygon", "MultiPolygon")

USES = (
    Use("soils", "ground", "FlatGeobuf", "the soil survey's ground types",
        "the soil base: one polygon per map-unit piece, with its ground type (an integer id) and misc flags",
        "P1-data", geometry=_AREAS, fields=(("ground_type", _INT),)),
    Use("soils", "palette", "JSON", "the measured soil colours",
        "each ground type's OKLab median and covariance, L p10/p90, octave energies and fragments",
        "P2", fallback="flat colours per ground type, labelled as such", schema="soils.palette/1"),
    Use("farm", "crop_cover", "GeoTIFF", "the crop cover",
        "crop group, July state and confidence per 10 m cell (bands group, state, confidence)",
        "P3-data", fallback="CSB 2025 fields plus CDL 2025 crop pixels (C7)", fallback_reads=("csb", "cdl"), res=10.0,
        bands=("group", "state", "confidence")),
    Use("farm", "fields", "FlatGeobuf", "the crop fields",
        "crop fields with their row bearing (degrees from north), for the texture's direction",
        "P3-data", fallback="CSB 2025 polygons, with no row bearing", fallback_reads=("csb",), geometry=_AREAS,
        fields=(("bearing", _REAL + _INT),)),
    Use("water", "mask", "FlatGeobuf", "the water mask",
        "confident water: bodies, and reaches buffered to their widths (piped and dry intermittent channels left out)",
        "P4-data", fallback="mask v0's NHD and OSM water", geometry=_AREAS),
    Use("ground_mask", None, "FlatGeobuf", "mask v0",
        "the masks from raw inputs (C6): exact areas for painting (roofs, roads at OSM's widths, paving, water) "
        "and `covered`, grown for sampling (maskrules.py)", "S5a-2", geometry=_AREAS, raw_only=True,
        required=tuple(maskrules.LAYERS)),
    Use("ground_classes", None, "GeoTIFF", "the box classes",
        "the 0.5 m land-cover classes, one GeoTIFF per box (named by the box's id, on its exact window)",
        "G1a", fallback="no classes: the boxes show the valley paint", res=grid.LEVELS["classes"], boxes=True,
        raw_only=True),
)

# The ground's own products: folders under $TVT_ARCHIVE that no plugin may take.
PRODUCTS = tuple(u.plugin for u in USES if u.product)

# Plugins whose exports the ground must never read, and why.
NEVER = {"roads": "its widths come from ACHD and ITD (internal); the ground keeps OSM's class widths (C6)"}


class InputError(ValueError):
    pass


@dataclass
class Choice:
    use: Use
    layers: list = field(default_factory=list)   # manifest.Layer, when the export is read
    reason: str = ""                               # why the fallback, when it is used

    @property
    def fallback(self):
        return not self.layers

    @property
    def layer(self):
        """The one layer of a plugin export (None when it falls back)."""
        return self.layers[0] if self.layers else None


@dataclass
class Plan:
    """What the ground would read: status "painted" or "flat" (with reason), a Choice per Use, and the versions of
    the RAW inputs the painter reads directly."""
    status: str
    reason: str
    choices: list
    versions: dict = field(default_factory=dict)

    def choice(self, ref):
        for c in self.choices:
            if c.use.ref == ref:
                return c
        raise KeyError(ref)

    @property
    def layers(self):
        return [lay for c in self.choices for lay in c.layers]

    @property
    def raw_names(self):
        """The RAW inputs read: those the painter names, and those its fallbacks read, in RAW's order."""
        names = set(self.versions)
        for c in self.choices:
            if c.fallback:
                names.update(c.use.fallback_reads)
        return [r.name for r in RAW if r.name in names]

    @property
    def raw(self):
        return tuple(RAW_BY_NAME[n] for n in self.raw_names)

    @property
    def missing_versions(self):
        """RAW inputs read without a version (tiles.digest refuses a plan with any)."""
        return [n for n in self.raw_names if not self.versions.get(n)]

    @property
    def credits(self):
        """Credits for the ground's attribution: the raw inputs read, then each export layer's, once each."""
        out = [r.credit for r in self.raw]
        for lay in self.layers:
            out.extend(lay["credit"])
        return list(dict.fromkeys(out))

    @property
    def republish(self):
        return M.strictest([r.republish for r in self.raw] + [lay["republish"] for lay in self.layers])

    @property
    def licence(self):
        return GROUND_LICENCE

    @property
    def refs(self):
        """The export layers read, e.g. ['soils/ground@20261012T031500Z']."""
        return [lay.ref for lay in self.layers]


def check_public(layer, m):
    """Raise InputError unless an export layer, and every input behind it, may be republished."""
    if layer["republish"] != "yes":
        raise InputError(f"{layer.ref} is republish {layer['republish']!r}: the ground reads public inputs only (C17)")
    for name in layer["inputs"]:
        src = m.inputs[name]
        if src["republish"] != "yes" or M.LICENCES[src["licence"]].loosest != "yes":
            raise InputError(f"{layer.ref} reads {name!r} ({src['licence']}, republish {src['republish']!r}): the "
                             "ground reads public inputs only (C17)")


def check_raw_only(layer, m):
    """Raise InputError unless a product's layer reads RAW inputs only, each under RAW's licence."""
    for name in layer["inputs"]:
        src, raw = m.inputs[name], RAW_BY_NAME.get(name)
        if raw is None:
            raise InputError(f"{layer.ref} reads {name!r}, which isn't one of the ground's raw inputs "
                             f"({', '.join(RAW_BY_NAME)}): its products are made from those only (C17). Add a "
                             "public source to inputs.RAW in review first")
        if src["licence"] != raw.licence:
            raise InputError(f"{layer.ref} gives {name!r} the licence {src['licence']}; it is {raw.licence}")


def check_use(use, layer):
    """Raise InputError unless an export layer has the shape the ground reads."""
    if layer["format"] != use.format:
        raise InputError(f"{layer.ref} is {layer['format']}; the ground reads {use.ref} as {use.format}")
    if use.geometry and layer["geometry"] not in use.geometry:
        raise InputError(f"{layer.ref} holds {layer['geometry']}; the ground reads {' or '.join(use.geometry)}")
    for fname, types in use.fields:
        if layer["fields"].get(fname) not in types:
            raise InputError(f"{layer.ref} needs a field {fname!r} of type {' or '.join(types)}")
    if use.res is not None and float(layer["grid"]["res"]) != use.res:
        raise InputError(f"{layer.ref} is at {layer['grid']['res']} m; the ground reads it at {use.res:g} m")
    if use.bands and tuple(b["name"] for b in layer["bands"]) != use.bands:
        raise InputError(f"{layer.ref} has bands {[b['name'] for b in layer['bands']]}; the ground reads "
                         f"{list(use.bands)}")
    if use.schema is not None and layer["schema"] != use.schema:
        raise InputError(f"{layer.ref} has schema {layer['schema']!r}; the ground reads {use.schema!r}")
    if use.boxes:
        ids = [b.id for b in grid.boxes()]
        if layer.name not in ids:
            raise InputError(f"{layer.ref}: a class layer is named by its box ({', '.join(ids)})")
        w = grid.box(layer.name).window()
        g = layer["grid"]
        if (g["west"], g["north"], g["width"], g["height"]) != (w.west, w.north, w.width, w.height):
            raise InputError(f"{layer.ref} covers E {g['west']} N {g['north']}, {g['width']} x {g['height']} cells; "
                             f"box {layer.name} is E {w.west:g} N {w.north:g}, {w.width} x {w.height}")


def exports(archive, verify=True, hashes=True, registry=None):
    """The newest export of each plugin and product the ground reads ({name: Manifest}), read and checked. Nothing
    else in the archive is opened, so another plugin's export can't hold the ground up. Raises InputError when the
    archive folder doesn't exist (a typo or an unmounted drive isn't "nothing exported yet"), and ManifestError when
    a newest export the ground reads is broken."""
    if not archive or not os.path.isdir(archive):
        raise InputError(f"no archive folder at {archive!r}")
    out = {}
    for name in dict.fromkeys(u.plugin for u in USES):
        m = M.latest(archive, name, verify=verify, hashes=hashes, registry=registry)
        if m is not None:
            out[name] = m
    return out


def resolve(manifests, versions=None):
    """The ground's plan from the newest exports ({name: Manifest}, as exports() gives) and the versions of the RAW
    inputs the painter reads directly ({raw name: version}, e.g. the OSM cut's MD5 or NAIP's release). Raises
    InputError when an export the ground would read isn't public, has the wrong shape or is a partial build."""
    for plugin, why in NEVER.items():
        if any(u.plugin == plugin for u in USES):
            raise InputError(f"the ground must not read {plugin}: {why}")
    versions = dict(versions or {})
    for name, v in versions.items():
        if name not in RAW_BY_NAME:
            raise InputError(f"{name!r} isn't one of the ground's raw inputs ({', '.join(RAW_BY_NAME)})")
        if not isinstance(v, str) or not v.strip():
            raise InputError(f"raw input {name!r} needs a version (a checksum, release or year), not {v!r}")
    choices = []
    for use in USES:
        m = manifests.get(use.plugin)
        if m is None:
            choices.append(Choice(use, reason=f"no {use.plugin} export yet ({use.by})"))
            continue
        if m.plugin != use.plugin:
            raise InputError(f"{m.folder} is {m.plugin}'s export, read as {use.plugin}'s")
        if M.is_partial(m.build):
            raise InputError(f"{use.plugin}@{m.build} is a partial build (a quick look at part of it): the ground "
                             "reads whole builds only")
        if use.product:
            layers = m.layers
            missing = [n for n in use.required if not m.has(n)]
            if missing:
                raise InputError(f"{use.plugin}@{m.build} lacks the layer(s) {', '.join(missing)} ({use.by})")
        elif m.has(use.layer):
            layers = [m.layer(use.layer)]
        else:
            choices.append(Choice(use, reason=f"{use.plugin}@{m.build} has no {use.layer!r} layer ({use.by})"))
            continue
        for layer in layers:
            check_public(layer, m)
            if use.raw_only:
                check_raw_only(layer, m)
            check_use(use, layer)
        choices.append(Choice(use, layers))
    missing = [c for c in choices if c.fallback and c.use.fallback is None]
    if missing:
        needs = " and ".join(c.use.label for c in missing)
        verb = "isn't" if len(missing) == 1 else "aren't"
        return Plan("flat", f"Flat ground: the painted ground needs {needs}, which {verb} built yet.", choices,
                    versions)
    plan = Plan("painted", "", choices, versions)
    if plan.republish != "yes":                       # can't happen after check_public; kept as the last guard
        raise InputError(f"the ground would be republish {plan.republish!r}")
    return plan
