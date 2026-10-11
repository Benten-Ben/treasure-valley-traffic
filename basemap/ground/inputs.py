"""What the ground reads, and the rule that keeps it public (C5, C6, C17). Standard library only.

The ground is an ODbL produced work built from public inputs only, so every tile of it may be republished. It reads
two kinds of input:
- RAW: source files it (and mask v0) reads directly: the OSM cut, Overture's roofs, NHD, CDL, CSB, NAIP, 3DEP and
  Sentinel-2;
- USES: plugin export layers (manifest.py), each with a fallback for when the plugin hasn't exported yet.

Every one must be republish "yes": resolve() refuses an export layer (or any input behind it) that isn't, rather
than quietly making the ground internal. The roads build is never read, because its widths come from ACHD and ITD
(internal); the ground keeps OSM's class widths instead (C6).

Without soils' `ground` layer there is nothing to paint on: the ground stays today's flat Valley and Clay ground and
says so (tiles.flat_entry). Every other input has a fallback, named in the plan resolve() returns.

    python3 basemap/ground/ground.py status --archive $TVT_ARCHIVE    # what the ground would read today
"""

from dataclasses import dataclass

from basemap.ground import fgb, manifest as M

GROUND_LICENCE = "ODbL-1.0"
GROUND_ABOUT = "ODbL produced work"


@dataclass(frozen=True)
class Raw:
    """A source the ground reads from files, outside any plugin export."""
    name: str
    licence: str
    republish: str
    credit: str
    what: str

    def entry(self):
        """As a manifest input."""
        return {"name": self.name, "licence": self.licence, "republish": self.republish, "credit": self.credit}


RAW = (
    Raw("osm", "ODbL-1.0", "yes", "© OpenStreetMap contributors",
        "S1's cut of the held Idaho extract, read through GDAL's OSM driver (mask v0). The extract has no Oregon, "
        "so the box's Malheur slice has no OSM"),
    Raw("overture-buildings", "ODbL-1.0", "yes", "Overture Maps Foundation, © OpenStreetMap contributors",
        "roof footprints for mask v0 (the release basemap/buildings.py reads)"),
    Raw("nhd", "public-domain", "yes", "U.S. Geological Survey, National Hydrography Dataset",
        "NHD HU4 1705 (GeoPackage), water for mask v0 until water's export lands"),
    Raw("cdl", "public-domain", "yes", "USDA NASS Cropland Data Layer",
        "CDL 2025 (30 m): crop pixels, and developed land for the masks"),
    Raw("csb", "public-domain", "yes", "USDA NASS Crop Sequence Boundaries",
        "CSB 2025 field polygons, the crop fallback until farm's crop_cover lands (C7)"),
    Raw("naip", "public-domain", "yes", "USDA NAIP",
        "NAIP 2025 county mosaics (0.3 m) for Ada and Canyon; NAIP 2023 (0.6 m) in boxes h-j"),
    Raw("3dep", "public-domain", "yes", "U.S. Geological Survey, 3D Elevation Program",
        "the 2023-24 QL1 lidar products in the class boxes, and the DEM for slope and aspect"),
    Raw("sentinel-2", "Copernicus", "yes", "Contains modified Copernicus Sentinel data 2025",
        "the July 2025 NDVI median on the 10 m grid"),
)


@dataclass(frozen=True)
class Use:
    """A plugin export layer the ground reads. fallback None means the ground can't paint without it."""
    plugin: str
    layer: str
    format: str
    label: str                           # what it is, in plain words (the flat ground's reason uses it)
    what: str                            # what the ground takes from it
    by: str                              # the package that makes it
    fallback: str = None                 # what the ground uses until it exists
    geometry: tuple = ()                 # allowed geometry types (FlatGeobuf)
    fields: tuple = ()                   # ((field, allowed types), ...) that must be present (FlatGeobuf)
    res: float = None                    # the grid level (GeoTIFF)
    schema: str = None                   # the JSON shape

    @property
    def ref(self):
        return f"{self.plugin}/{self.layer}"


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
        "P3-data", fallback="CSB 2025 fields plus CDL 2025 crop pixels (C7)", res=10.0),
    Use("farm", "fields", "FlatGeobuf", "the crop fields",
        "crop fields with their row bearing (degrees from north), for the texture's direction",
        "P3-data", fallback="CSB 2025 polygons, with no row bearing", geometry=_AREAS,
        fields=(("bearing", _REAL + _INT),)),
    Use("water", "mask", "FlatGeobuf", "the water mask",
        "confident water: bodies, and reaches buffered to their widths (piped and dry intermittent channels left out)",
        "P4-data", fallback="mask v0's NHD and OSM water", geometry=_AREAS),
)

# Plugins whose exports the ground must never read, and why.
NEVER = {"roads": "its widths come from ACHD and ITD (internal); the ground keeps OSM's class widths (C6)"}


class InputError(ValueError):
    pass


@dataclass
class Choice:
    use: Use
    layer: object = None        # manifest.Layer when the export is read
    reason: str = ""            # why the fallback, when it is used

    @property
    def fallback(self):
        return self.layer is None


@dataclass
class Plan:
    """What the ground would read: status "painted" or "flat" (with reason), and a Choice per Use."""
    status: str
    reason: str
    choices: list
    raw: tuple = RAW

    def choice(self, ref):
        for c in self.choices:
            if c.use.ref == ref:
                return c
        raise KeyError(ref)

    @property
    def credits(self):
        """Credits for the ground's attribution: the raw inputs', then each export layer's, once each."""
        out = [r.credit for r in self.raw]
        for c in self.choices:
            if c.layer is not None:
                out.extend(x for x in c.layer["credit"] if x not in out)
        return list(dict.fromkeys(out))

    @property
    def republish(self):
        values = [r.republish for r in self.raw] + [c.layer["republish"] for c in self.choices if c.layer is not None]
        return M.strictest(values)

    @property
    def licence(self):
        return GROUND_LICENCE

    @property
    def refs(self):
        """The export layers read, e.g. ['soils/ground@20261012T031500Z']."""
        return [c.layer.ref for c in self.choices if c.layer is not None]


def check_public(layer, m):
    """Raise InputError unless an export layer, and every input behind it, may be republished."""
    if layer["republish"] != "yes":
        raise InputError(f"{layer.ref} is republish {layer['republish']!r}: the ground reads public inputs only (C17)")
    for name in layer["inputs"]:
        src = m.inputs[name]
        if src["republish"] != "yes" or M.LICENCES[src["licence"]].loosest != "yes":
            raise InputError(f"{layer.ref} reads {name!r} ({src['licence']}, republish {src['republish']!r}): the "
                             "ground reads public inputs only (C17)")


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
    if use.schema is not None and layer["schema"] != use.schema:
        raise InputError(f"{layer.ref} has schema {layer['schema']!r}; the ground reads {use.schema!r}")


def resolve(manifests):
    """The ground's plan from each plugin's newest export ({plugin: Manifest}, as manifest.find() gives). Raises
    InputError when an export the ground would read isn't public or has the wrong shape."""
    for plugin, why in NEVER.items():
        if any(u.plugin == plugin for u in USES):
            raise InputError(f"the ground must not read {plugin}: {why}")
    choices = []
    for use in USES:
        m = manifests.get(use.plugin)
        if m is None:
            choices.append(Choice(use, reason=f"no {use.plugin} export yet ({use.by})"))
            continue
        if not m.has(use.layer):
            choices.append(Choice(use, reason=f"{use.plugin}@{m.build} has no {use.layer!r} layer ({use.by})"))
            continue
        layer = m.layer(use.layer)
        check_public(layer, m)
        check_use(use, layer)
        choices.append(Choice(use, layer))
    missing = [c for c in choices if c.fallback and c.use.fallback is None]
    if missing:
        needs = " and ".join(c.use.label for c in missing)
        return Plan("flat", f"Flat ground: the painted ground needs {needs}, which isn't built yet.", choices)
    plan = Plan("painted", "", choices)
    if plan.republish != "yes":                       # can't happen after check_public; kept as the last guard
        raise InputError(f"the ground would be republish {plan.republish!r}")
    return plan
