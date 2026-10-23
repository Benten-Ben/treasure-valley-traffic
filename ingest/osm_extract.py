"""The OpenStreetMap extract, downloaded by hand and loaded into each plugin's consumers (plan C1, C2, C10).

    python3 -m ingest osm-load --inbox                 # the newest extract in $TVT_ARCHIVE/osm/inbox/
    python3 -m ingest osm-load --file PATH             # an extract anywhere (copied into the archive)
    python3 -m ingest osm-load --archived              # the newest extract in the archive again
    python3 -m ingest osm-load --only roads.osm_street # one consumer (on the newest archived extract,
                                                       # unless --inbox or --file says otherwise)
    python3 -m ingest osm-load --cut-only              # just make the valley cut (S5a's mask reads it)
    python3 -m ingest osm-load --list                  # the consumers, what each loaded last, the partition

Where extracts come from: by hand only. Geofabrik's robots.txt (read Oct 6,
2026) disallows its extracts and their .md5 files for every robot, so the
owner downloads the Idaho extract in a browser and copies it (and its .md5)
into $TVT_ARCHIVE/osm/inbox/. Nothing here makes a network request.

One extract, several readers (landscape sprint, Oct 2026). Each plugin that
reads OpenStreetMap lists **consumers** in its plugin.json (`osm_consumers`,
ingest/manifest.py): one of its "manual" sources, the osmium tags-filter
expressions it wants, the geometry types it gets (points, lines, polygons
and multipolygons, relations with their members) and the tables it writes.
A load:

  1. checks the file's MD5 against the .md5 that came with it;
  2. picks the consumers due: each keeps its own MD5 gate, so a consumer added
     later loads the extract we already hold (`--only`) without reloading the
     others. A consumer's gate is its row in ops.osm_consumer (migration 0019),
     unless its module keeps its own: osm_valley keeps $TVT_ARCHIVE/osm/
     last-loaded.json, as before;
  3. cuts the valley box out of the extract **once**, with osmium's `smart`
     strategy: every way with a node in the box, whole, and every multipolygon
     with a member in it, whole (lots and water bodies that cross the edge).
     The cut is kept at $TVT_ARCHIVE/osm/cut/valley.osm.pbf, with valley.json
     saying which extract it came from, and reused while that's the extract.
     Making it is heavy (osmium peaks at about 3.9 GB), so only a run with
     osm_valley due (heavy anyway), `--make-cut` or `--cut-only` makes it;
     any other run stops before loading anything when it's missing;
  4. runs each consumer, osm_valley first, then in plugin order, each in its
     own transaction with its own ops.fetch row. osm_valley runs its own
     unchanged pipeline over the cut (its complete_ways cut of the smart cut is
     the same as of the whole extract). The others get their features from
     `Run.features()`: osmium export of the cut, then their expressions, the
     box and the partition, applied here;
  5. archives the file (the last two extracts are kept) if any consumer loaded it.
A consumer that fails is logged in ops.fetch and the others go on; rerun it
with `--only`. The command exits 1 if any failed or was held back.

Which consumer owns a highway way is decided by `owner()`, by tags alone
(plan C10): osm_valley's keep rule first, unchanged; then the streets and
alleys (osm_street); then sidewalks, crossings and the other service ways
(osm_paving); then paths, tracks and footways (osm_paths). The consumers so
named get only the highway ways the partition gives them, so no way is drawn
twice. The 12 lane-tagged cycleways, tracks and pedestrian ways osm_valley
already keeps are the named exception (`named_exception()`): they stay
osm_valley's, and trails reads them through a view. No way has two owners;
some have none (unbuilt and indoor ways, roads drawn as areas: `unowned_reason()`).
A raceway or escape ramp goes to osm_paving; a raceway with lanes or turn tags stays
osm_valley's (its keep rule runs first).

The partition holds only while its owners hold the same extract: a way that
gained a lanes tag would otherwise be in core.osm_way and roads.osm_street
both, and one that lost it in neither. So they load one extract together:
osm_valley leads, and osm_street, osm_paving and osm_paths load only the
extract osm_valley holds (or loaded in the same run). One that would load
another is held back, and so is osm_valley when a follower that holds another
extract isn't coming along in the same run (`--only osm_valley` on a new
extract), unless `--allow-mixed`. That leaves one way for them to differ: a
follower that fails after osm_valley loaded. Then the load says the owners
differ until the follower is rerun, `--list` says so too, and a build that
reads their tables together calls `check_partition()` first and refuses a
mixed union.

Versioning (plan C2). osm_valley keeps raw.record versions as before. The new
consumers make no raw.record copies: their typed tables keep osm_version,
osm_timestamp, first_seen, last_seen and active, versioned in place
(`store_objects`), and the archive keeps the last two extracts.

License ODbL: credit "© OpenStreetMap contributors". OpenStreetMap stays in
tables of its own (core.osm_*, <plugin>.osm_*), and anything derived from it
that we publish stays ODbL. The Idaho extract has no Oregon, so the box's
Malheur County slice has no OpenStreetMap data.
"""

import argparse
import glob
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import db, manifest

PAGE = "https://download.geofabrik.de/north-america/us/idaho.html"   # where the owner downloads it by hand
BOX = (-117.05, 43.00, -115.95, 43.85)          # left, bottom, right, top: the valley box
CREDIT = "© OpenStreetMap contributors"
COVERAGE = ("Geofabrik's Idaho extract: the box's Oregon part (Malheur County) has no OpenStreetMap data")
OSM_SUFFIXES = (".osm.pbf", ".osm.bz2", ".osm.gz", ".osm")
OSMIUM_TIMEOUT_S = 1800
SHRINK_GUARD = 0.5            # refuse to retire objects when a load brings fewer than half the active ones
CUT_MEMORY = "osmium peaks at about 3.9 GB: give it 5 GB"
STATE_TABLE = "ops.osm_consumer"
CUT_DIR, CUT_NAME, CUT_INFO = "cut", "valley.osm.pbf", "valley.json"


# ---- osm_valley's keep rule ------------------------------------------------
# Moved here unchanged from plugins/roads/ingest/sources/osm_valley.py, which
# imports it back, so the partition's first rule is osm_valley's rule itself.

MAJOR = {"motorway", "trunk", "primary", "secondary", "tertiary"}
MAJOR |= {f"{c}_link" for c in MAJOR}
ROADS = MAJOR | {"unclassified", "residential", "living_street", "service", "road", "busway"}
NOT_ROADS = {"proposed", "planned", "construction", "abandoned", "disused", "razed", "demolished",
             "platform", "bus_stop", "rest_area", "services"}
LANE_KEYS = ("lanes", "lanes:forward", "lanes:backward")


def keep_way(tags):
    hw = tags.get("highway")
    if not hw or hw in NOT_ROADS or tags.get("area") == "yes":
        return False
    if hw in MAJOR:
        return True
    return any(k in tags for k in LANE_KEYS) or any(k.startswith("turn:lanes") for k in tags)


# ---- the partition (plan C10) ----------------------------------------------

STREET_CLASSES = {"residential", "unclassified", "unclassified_link", "living_street", "road", "busway"}
PAVED_OTHER = {"raceway", "escape"}   # built surfaces drawn by material; never routed (Oct 22, answer 9)
PAVING_FOOTWAYS = {"sidewalk", "crossing", "access_aisle", "traffic_island"}   # footway=*
WALKWAYS = {"footway", "path", "cycleway"}
PATH_CLASSES = {"track", "path", "footway", "cycleway", "bridleway", "steps", "pedestrian"}
OWNERS = ("osm_valley", "osm_street", "osm_paving", "osm_paths")
AREA_STREET_CLASSES = {"residential", "unclassified", "unclassified_link", "primary"}   # drawn as areas: no owner
LEADER = OWNERS[0]          # the others load only the extract it holds


def owner(tags):
    """The consumer that owns a highway way, by its tags alone, or None (not a highway way, not
    built, or nothing we draw). In this order:
      1. osm_valley's keep rule (major roads and every way tagged with lanes), unchanged;
      2. osm_street: residential, unclassified, unclassified_link, living_street, road and
         busway, and alleys (highway=service + service=alley), unless drawn as an area (area=yes);
      3. osm_paving: footway=sidewalk|crossing|access_aisle|traffic_island on a footway, path
         or cycleway, every other service way, and raceway and escape (osm_valley keeps a raceway
         with lanes or turn tags, by rule 1; the rest are paving);
      4. osm_paths: track, path, the other footways, cycleway, bridleway, steps, pedestrian.
    Left over: unbuilt and non-way values (proposed, construction, platform, ...), roads and
    streets drawn as areas, and values none of these take (corridor, elevator, ...)."""
    hw = tags.get("highway")
    if not hw:
        return None
    if keep_way(tags):
        return "osm_valley"
    if hw in NOT_ROADS:
        return None
    area = tags.get("area") == "yes"
    if not area and (hw in STREET_CLASSES or (hw == "service" and tags.get("service") == "alley")):
        return "osm_street"
    if (hw in WALKWAYS and tags.get("footway") in PAVING_FOOTWAYS) or hw == "service" or hw in PAVED_OTHER:
        return "osm_paving"
    if hw in PATH_CLASSES:
        return "osm_paths"
    return None


def unowned_reason(tags):
    """Why a highway way has no owner (for reports), or None when it has one."""
    hw = tags.get("highway")
    if not hw or owner(tags):
        return None
    if hw in NOT_ROADS:
        return f"not built or not a way (highway={hw})"
    if tags.get("area") == "yes" and (hw in ROADS):
        return f"a road drawn as an area (highway={hw}, area=yes)"
    return f"not drawn (highway={hw})"


# Built values that no owner takes on purpose: a corridor or an elevator is indoor, and NOT_ROADS
# are unbuilt or not ways at all. Everything else built that has no owner is a gap to close.
INDOOR_OR_NONBUILT = NOT_ROADS | {"corridor", "elevator"}


def ownerless_built(tags):
    """The reason a built highway way has no owner, or None: an area-drawn road (named, expected)
    or a gap (the count the real-extract check reports must be 0 apart from the named areas)."""
    hw = tags.get("highway")
    if not hw or owner(tags) or hw in INDOOR_OR_NONBUILT:
        return None
    if tags.get("area") == "yes" and hw in AREA_STREET_CLASSES:
        return None
    return hw


def count_ownerless(tags_list):
    """Counter of highway values for built ways with no owner (ownerless_built), for the
    real-extract check. Area-drawn streets are counted apart under 'area:<highway>'."""
    counts = Counter()
    for tags in tags_list:
        hw = ownerless_built(tags)
        if hw is None:
            if tags.get("highway") and not owner(tags) and tags.get("highway") not in INDOOR_OR_NONBUILT:
                counts[f"area:{tags['highway']}"] += 1
            continue
        counts[hw] += 1
    return counts


def named_exception(tags):
    """The partition's named exception: a path-class way (a cycleway, track, pedestrian way, ...)
    tagged with lanes, which osm_valley keeps and osm_paths would otherwise get. Trails reads them
    through a view (12 in the Oct 5 extract: 7 cycleways, 4 tracks, 1 pedestrian way)."""
    return keep_way(tags) and tags.get("highway") in PATH_CLASSES


# ---- the archive -----------------------------------------------------------
# Moved here from osm_valley.py (which imports these back), unchanged.

def archive_dir(required=True):
    base = os.environ.get("TVT_ARCHIVE")
    if not base:
        if required:
            raise RuntimeError("set TVT_ARCHIVE: extracts are kept in $TVT_ARCHIVE/osm/")
        return None
    folder = os.path.join(base, "osm")
    os.makedirs(os.path.join(folder, "inbox"), exist_ok=True)
    return folder


def file_md5(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def parse_md5(text):
    """Geofabrik's .md5 files read '<hex>  idaho-latest.osm.pbf'."""
    m = re.match(r"\s*([0-9a-fA-F]{32})\b", text)
    if not m:
        raise ValueError(f"not an MD5 file: {text[:80]!r}")
    return m.group(1).lower()


def _suffix(path):
    name = os.path.basename(path).lower()
    return next((s for s in OSM_SUFFIXES if name.endswith(s)), None)


def archive_name(path, md5, day):
    """idaho-latest.osm.pbf -> idaho-20261006-1a2b3c4d.osm.pbf"""
    suffix = _suffix(path) or ".osm.pbf"
    stem = os.path.basename(path)[:-len(suffix)] or "extract"
    stem = re.sub(r"-latest$", "", stem)
    return f"{stem}-{day:%Y%m%d}-{md5[:8]}{suffix}"


def extracts(folder):
    """Extracts in the folder (not its inbox), newest first."""
    paths = [p for p in glob.glob(os.path.join(folder, "*")) if os.path.isfile(p) and _suffix(p)]
    return sorted(paths, key=os.path.getmtime, reverse=True)


def prune(folder, keep=2, protect=()):
    """Keep the newest `keep` extracts (and their .md5 files), and never the protected ones."""
    protected = {os.path.abspath(p) for p in protect}
    removed = []
    for p in extracts(folder)[keep:]:
        if os.path.abspath(p) in protected:
            continue
        for q in (p, p + ".md5"):
            if os.path.exists(q):
                os.remove(q)
        removed.append(os.path.basename(p))
    return removed


def inbox_file(folder):
    """The newest extract waiting in $TVT_ARCHIVE/osm/inbox/, or None."""
    files = extracts(os.path.join(folder, "inbox"))
    return files[0] if files else None


def archive_file(path, folder, md5, name=None):
    """Move a file from the inbox (or copy one from elsewhere) into the archive, as `name`
    (default archive_name's). Either way, and for a file already archived (a re-load), its time
    becomes now, which is what pruning goes by."""
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(folder):
        os.utime(path)
        return path
    dest = os.path.join(folder, name or archive_name(path, md5, db.now()))
    inbox = os.path.join(folder, "inbox")
    if os.path.dirname(os.path.abspath(path)) == os.path.abspath(inbox):
        os.replace(path, dest)
        if os.path.exists(path + ".md5"):
            os.replace(path + ".md5", dest + ".md5")
    else:
        shutil.copyfile(path, dest + ".part")
        os.replace(dest + ".part", dest)
    os.utime(dest)
    return dest


def kept_name(path, folder, md5):
    """The name the extract has, or will have, in the archive."""
    if folder and os.path.dirname(os.path.abspath(path)) == os.path.abspath(folder):
        return os.path.basename(path)
    return archive_name(path, md5, db.now())


def check_md5(path):
    """The file's MD5, checked against the published .md5 beside it if it came along."""
    md5 = file_md5(path)
    if os.path.exists(path + ".md5"):
        with open(path + ".md5", encoding="utf-8") as f:
            published = parse_md5(f.read())
        if published != md5:
            raise SystemExit(f"{path}: MD5 {md5} doesn't match its .md5 file ({published})")
    return md5


# ---- consumers -------------------------------------------------------------

@dataclass(frozen=True)
class Consumer:
    """One plugin's reader of the extract (its plugin.json's osm_consumers entry)."""
    plugin: str
    source: dict = field(repr=False)        # its "manual" source entry: name, module, license, credit, republish
    tags: tuple
    geometry: tuple
    tables: tuple

    @property
    def name(self):
        return self.source["name"]

    @property
    def id(self):
        return f"{self.plugin}.{self.name}"

    def module(self):
        return importlib.import_module(f"plugins.{self.plugin}.{self.source['module']}")


def consumers(plugins=None):
    """Every plugin's consumers, in plugin order (dependencies first, then each plugin's order),
    then manifest order. Raises manifest.ManifestError if two plugins consume one source name."""
    plugins = manifest.plugin_order(manifest.find()) if plugins is None else plugins
    out, seen = [], {}
    for p in plugins:
        sources = {e["name"]: e for e in p.manifest["sources"]}
        for c in p.osm_consumers:
            if c["source"] in seen:
                raise manifest.ManifestError(f"OpenStreetMap consumer {c['source']} is in both {seen[c['source']]} "
                                             f"and {p.name}")
            seen[c["source"]] = p.name
            out.append(Consumer(p.name, sources[c["source"]], tuple(c["tags"]), tuple(c["geometry"]),
                                tuple(c["tables"])))
    return out


def select(all_consumers, only):
    """The consumers named in only (each '<plugin>.<source>' or just '<source>'), in load order."""
    if not only:
        return list(all_consumers)
    wanted = set(only)
    known = {c.id for c in all_consumers} | {c.name for c in all_consumers}
    if unknown := sorted(wanted - known):
        raise SystemExit(f"no OpenStreetMap consumer {', '.join(unknown)}; there are: "
                         + ", ".join(c.id for c in all_consumers))
    return [c for c in all_consumers if c.id in wanted or c.name in wanted]


# ---- tag expressions -------------------------------------------------------

class TagFilter:
    """A consumer's tags-filter expressions (osmium's syntax), applied in Python to what osmium
    export writes from the cut: export can't select objects by their tags (it writes every tagged
    node and open way), so this is where a consumer's objects are picked."""

    def __init__(self, expressions):
        self.rules = []
        for e in expressions:
            m = manifest.OSM_TAG_EXPRESSION.match(e)
            if not m:
                raise ValueError(f"not a tags-filter expression we take: {e!r}")
            values = frozenset(m["values"].split(",")) if m["values"] else None
            self.rules.append((frozenset(m["types"]), m["key"], values))
        self.keys = sorted({key for _, key, _ in self.rules})

    def matches(self, kind, tags, area=False):
        """kind: 'n', 'w' or 'r'; area: a closed way or a multipolygon (what osmium's a/ means)."""
        for types, key, values in self.rules:
            if kind in types or (area and "a" in types):
                v = tags.get(key)
                if v is not None and (values is None or v in values):
                    return True
        return False

    def may_match(self, line):
        """A cheap first look at a GeoJSON line: could one of the keys be among its tags?"""
        return any(f'"{key}"' in line for key in self.keys)

    def export_tags(self, types):
        """The expressions for osmium export's linear_tags (types 'w') or area_tags (types 'a'),
        one 'key' or 'key=value' each: they decide whether a closed way is a line or an area."""
        out = []
        for t, key, values in self.rules:
            if t & set(types):
                out += [f"{key}={v}" for v in sorted(values)] if values else [key]
        return out


def relation_expressions(expressions):
    """The expressions that select relations (r/...)."""
    return [e for e in expressions if "r" in manifest.OSM_TAG_EXPRESSION.match(e)["types"]]


# ---- osmium ----------------------------------------------------------------

def osmium(cmd):
    if not shutil.which(cmd[0]):
        raise RuntimeError("osmium-tool isn't installed (the ingest image has it)")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=OSMIUM_TIMEOUT_S)
    if r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:2])} failed ({r.returncode}): {r.stderr.strip()[-500:]}")
    return r.stdout


def box_arg():
    return ",".join(f"{v:.2f}" for v in BOX)


def cut_command(src, out):
    """One smart cut of the box: ways with a node in it whole, multipolygons with a member in it whole."""
    return ["osmium", "extract", "--bbox", box_arg(), "--strategy", "smart", "--set-bounds", "--no-progress",
            "--overwrite", "--output-format", "pbf", "--output", out, src]


def export_config(consumer):
    """osmium export's settings for a consumer: the attributes we read, and which closed ways are
    lines (its w/ expressions) and which are areas (its a/ expressions; multipolygons too)."""
    tag_filter = TagFilter(consumer.tags)
    return {"attributes": {"type": True, "id": True, "version": True, "timestamp": True, "way_nodes": True},
            "linear_tags": tag_filter.export_tags("w") or False,
            "area_tags": tag_filter.export_tags("a") or False}


def consumer_commands(cut, work, consumer):
    """A consumer's osmium steps over the cut, and the files they leave in work: (commands, its
    export settings' file, GeoJSON-lines file or None, OSM XML file of the cut's relations or None).

    No tags-filter: on Idaho's node ids it needs about 1.9 GB even on the cut (a bitmap over every
    id), where an export of the cut needs tens of MB. So osmium export writes the cut's tagged
    objects in the consumer's geometry types, and Run.features picks the consumer's own."""
    config = os.path.join(work, "export.json")
    shapes = [g for g in consumer.geometry if g != "relation"]
    cmds, lines, rels = [], None, None
    if shapes:
        lines = os.path.join(work, "features.geojsonseq")
        cmds.append(["osmium", "export", "--config", config, "--output-format", "geojsonseq", "--format-option",
                     "print_record_separator=false", "--geometry-types", ",".join(shapes),
                     "--add-unique-id", "type_id", "--no-progress", "--overwrite", "--output", lines, cut])
    if "relation" in consumer.geometry:
        rels = os.path.join(work, "relations.osm")
        cmds.append(["osmium", "cat", "--object-type", "relation", "--no-progress", "--overwrite",
                     "--output-format", "xml", "--output", rels, cut])
    return cmds, config, lines, rels


def data_timestamp(src):
    """When the extract's data was cut (Geofabrik's header), or None."""
    try:
        out = osmium(["osmium", "fileinfo", "--get", "header.option.osmosis_replication_timestamp", src]).strip()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    return out or None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_json(path, data):
    tmp = f"{path}.{os.getpid()}.part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def cut_ready(cut_dir, md5):
    """valley.json's info when cut_dir holds the valley cut of this extract (its MD5, and the size
    valley.json recorded), else None."""
    if not cut_dir:
        return None
    path, info = os.path.join(cut_dir, CUT_NAME), read_json(os.path.join(cut_dir, CUT_INFO))
    if info.get("md5") == md5 and os.path.isfile(path) and os.path.getsize(path) == info.get("bytes"):
        return info
    return None


def make_cut(src, md5, extract_name, cut_dir, data_as_of=None):
    """The valley cut of an extract in cut_dir ($TVT_ARCHIVE/osm/cut/ on the server): valley.osm.pbf,
    and valley.json saying which extract it is of. Reused while it's of the same extract (same MD5
    and size). Making it is a heavy job (osmium peaks at about 3.9 GB). Returns (path, info, made)."""
    os.makedirs(cut_dir, exist_ok=True)
    path, info_path = os.path.join(cut_dir, CUT_NAME), os.path.join(cut_dir, CUT_INFO)
    if info := cut_ready(cut_dir, md5):
        return path, info, False
    part = os.path.join(cut_dir, f".{CUT_NAME}.{os.getpid()}.part")
    try:
        osmium(cut_command(src, part))
        info = {"extract": extract_name, "md5": md5, "data_as_of": data_as_of, "box": list(BOX),
                "strategy": "smart", "made_at": db.now().isoformat(timespec="seconds"),
                "bytes": os.path.getsize(part), "sha256": sha256_file(part),
                "license": "ODbL", "credit": CREDIT, "republish": "yes", "coverage": COVERAGE}
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)
    write_json(info_path, info)
    return path, info, True


# ---- features --------------------------------------------------------------

def parse_timestamp(v):
    """osmium writes epoch seconds (1.16) or ISO text, depending on version."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def in_box(coords):
    """Whether any of a GeoJSON geometry's positions lies in the box (edges included)."""
    left, bottom, right, top = BOX
    stack = [coords]
    while stack:
        c = stack.pop()
        if c and isinstance(c[0], (int, float)):
            if left <= c[0] <= right and bottom <= c[1] <= top:
                return True
        elif c:
            stack.extend(c)
    return False


_SHAPES = {"Point": "point", "LineString": "linestring", "Polygon": "polygon", "MultiPolygon": "polygon"}
_TYPES = {"node": "n", "way": "w", "relation": "r"}


def parse_export_line(line):
    """One of osmium export's GeoJSON lines as a feature: {type ('n', 'w' or 'r': the OSM object it
    comes from), osm_id, geometry ('point', 'linestring' or 'polygon'), geom (GeoJSON), tags,
    osm_version, osm_timestamp, way_nodes (lines)}, or None. An area's own id is osmium's area id
    ('a' + twice the way's id, or twice the relation's plus one); its @type and @id name the way
    or relation it was built from."""
    line = line.strip().lstrip("\x1e")
    if not line:
        return None
    feat = json.loads(line)
    props, geom = feat.get("properties") or {}, feat.get("geometry") or {}
    shape = _SHAPES.get(geom.get("type"))
    kind, osm_id = _TYPES.get(props.get("@type")), props.get("@id")
    if kind is None or osm_id is None:                   # no type or id attribute: read the unique id
        fid = str(feat.get("id") or "")
        if fid[:1] in ("n", "w", "r") and fid[1:].isdigit():
            kind, osm_id = fid[:1], int(fid[1:])
    if shape is None or kind is None or osm_id is None:
        return None
    return {"type": kind, "osm_id": int(osm_id), "geometry": shape, "geom": geom,
            "tags": {k: v for k, v in props.items() if not k.startswith("@")},
            "osm_version": props.get("@version"), "osm_timestamp": parse_timestamp(props.get("@timestamp")),
            "way_nodes": props.get("@way_nodes")}


def parse_relations(path):
    """Relations with their members from an OSM XML file: features of geometry 'relation', with
    members [{type ('n', 'w' or 'r'), ref, role}] and no geom."""
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "relation":
            yield {"type": "r", "osm_id": int(el.get("id")), "geometry": "relation", "geom": None,
                   "tags": {t.get("k"): t.get("v") for t in el.iter("tag")},
                   "osm_version": int(el.get("version")) if el.get("version") else None,
                   "osm_timestamp": parse_timestamp(el.get("timestamp")),
                   "members": [{"type": m.get("type", "")[:1], "ref": int(m.get("ref")), "role": m.get("role") or ""}
                               for m in el.iter("member")]}
            el.clear()
        elif el.tag in ("node", "way"):
            el.clear()


def closed(geom):
    c = geom.get("coordinates") if geom else None
    return bool(c) and geom.get("type") == "LineString" and len(c) >= 4 and c[0] == c[-1]


def select_features(features, consumer, counts):
    """A consumer's features: its own expressions, the box, and the partition."""
    tag_filter = TagFilter(consumer.tags)
    partitioned = consumer.name in OWNERS
    for f in features:
        if f is None:
            continue
        area = f["geometry"] == "polygon" or closed(f["geom"])
        if not tag_filter.matches(f["type"], f["tags"], area):
            continue                                       # another consumer's (export writes every tagged object)
        if f["geometry"] in ("point", "linestring") or (f["geometry"] == "polygon" and f["type"] == "w"):
            if not in_box(f["geom"]["coordinates"]):
                counts["dropped: outside the box (completing a multipolygon)"] += 1
                continue
        if partitioned and f["type"] == "w" and "highway" in f["tags"]:
            o = owner(f["tags"])
            if o != consumer.name:
                counts[f"dropped: the partition gives it to {o or 'nobody'}"] += 1
                continue
        counts[f"{f['geometry']}s"] += 1
        yield f


@dataclass
class Run:
    """One consumer's load of one extract: what its module's consume(conn, run) gets."""
    consumer: Consumer
    extract: str                 # the extract's path as loaded
    extract_name: str            # its name in the archive
    md5: str
    cut: str                     # the valley cut (a smart cut of the box)
    work: str                    # a folder of its own for intermediate files, removed afterwards
    fetch: object                # the db.Fetch logging this load
    seen_at: datetime            # the load's time: first_seen and last_seen
    allow_shrink: bool = False
    data_as_of: str = None
    work_parent: str = None      # where osm_valley puts its own temporary folder (the archive's disk)
    counts: Counter = field(default_factory=Counter)

    def features(self):
        """This consumer's objects from the cut: osmium export of its geometry types (and the
        cut's relations, with their members, if it takes relations), then its expressions, the
        box and the partition (select_features). A closed way comes as a line if a w/ expression
        matches it and as an area if an a/ one does. A generator."""
        cmds, config, lines, rels = consumer_commands(self.cut, self.work, self.consumer)
        write_json(config, export_config(self.consumer))
        for cmd in cmds:
            osmium(cmd)
        tag_filter = TagFilter(self.consumer.tags)

        def raw():
            if lines:
                with open(lines, encoding="utf-8") as f:
                    for line in f:
                        if tag_filter.may_match(line):
                            yield parse_export_line(line)
            if rels:
                yield from parse_relations(rels)

        yield from select_features(raw(), self.consumer, self.counts)


# ---- storing: versioned in place (plan C2) ---------------------------------

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")


def _ident(name):
    if not _IDENT.match(name):
        raise ValueError(f"not a plain SQL name: {name!r}")
    return name


def store_objects(conn, table, columns, rows, seen_at, key=("osm_id",), geometry="geom",
                  geometry_sql="ST_SetSRID(ST_GeomFromGeoJSON({}), 4326)", allow_shrink=False):
    """Write one load of a consumer's objects into its typed table, versioned in place: an object
    seen again is updated and keeps first_seen; every object in the load gets last_seen = seen_at
    and active; one missing from the load becomes inactive (it's never deleted). No raw.record copy.

    columns: [(name, SQL type)] staged as given, the geometry column left out; rows: tuples in that
    order, then the geometry as GeoJSON text (geometry_sql turns it into the column's type). With
    geometry=None (objects without one: route relations and their members), rows hold the columns
    only. The table needs active, first_seen and last_seen, and a unique key. Refuses to retire when
    the load has fewer than half the active objects (SHRINK_GUARD, at any size), unless
    allow_shrink, and refuses an empty load whenever anything is active, even then (like
    db.check_snapshot): a broken export or a wrong filter looks like that. Doesn't commit.
    Returns {objects, new, changed, unchanged, reactivated, retired}."""
    table = _ident(table)
    geometry = _ident(geometry) if geometry is not None else None
    names = [_ident(c) for c, _ in columns]
    key = [_ident(k) for k in key]
    stage = _ident("osm_stage_" + table.replace(".", "_"))
    staged = names + ([geometry] if geometry else [])
    defs = [f"{c} {t}" for c, t in columns] + ([f"{geometry} text"] if geometry else [])
    conn.execute(f"drop table if exists pg_temp.{stage}")
    conn.execute(f"create temp table {stage} ({', '.join(defs)}) on commit drop")
    with conn.cursor() as cur:
        with cur.copy(f"copy {stage} ({', '.join(staged)}) from stdin") as cp:
            for r in rows:
                cp.write_row(r)
    keys = ", ".join(key)
    n, distinct = conn.execute(f"select count(*), count(distinct ({keys})) from {stage}").fetchone()
    if n != distinct:
        raise RuntimeError(f"{table}: {n - distinct} objects twice in one load (key {keys})")
    active = conn.execute(f"select count(*) from {table} where active").fetchone()[0]
    if n == 0 and active:
        raise RuntimeError(f"{table}: no objects in this load against {active} active; not retiring them (check "
                           "the file and the consumer's tags; an empty load is never taken)")
    if not allow_shrink and n < active * SHRINK_GUARD:
        raise RuntimeError(f"{table}: only {n} objects in this extract against {active} active; not retiring "
                           "the rest (check the file, or load it with --allow-shrink)")
    join = " and ".join(f"t.{k} = s.{k}" for k in key)
    rest = [c for c in names if c not in key]
    values = [f"s.{c}" for c in names]
    differs = [f"t.{c} is distinct from s.{c}" for c in rest]
    updates = [f"{c} = excluded.{c}" for c in rest]
    if geometry:
        geom_expr = geometry_sql.format(f"s.{geometry}")
        values.append(geom_expr)
        differs.append(f"ST_AsBinary(t.{geometry}) is distinct from ST_AsBinary({geom_expr})")
        updates.append(f"{geometry} = excluded.{geometry}")
    new, reactivated, changed = conn.execute(
        f"""select count(*) filter (where t.{key[0]} is null),
                   count(*) filter (where t.{key[0]} is not null and not t.active),
                   count(*) filter (where t.{key[0]} is not null and t.active and ({' or '.join(differs) or 'false'}))
            from {stage} s left join {table} t on {join}""").fetchone()
    updates += ["active = true", "last_seen = excluded.last_seen"]
    conn.execute(
        f"""insert into {table} ({', '.join(staged)}, active, first_seen, last_seen)
            select {', '.join(values)}, true, %(seen)s, %(seen)s from {stage} s
            on conflict ({keys}) do update set {', '.join(updates)}""", {"seen": seen_at})
    retired = conn.execute(f"update {table} set active = false where active and last_seen < %s", (seen_at,)).rowcount
    conn.execute(f"drop table pg_temp.{stage}")
    return {"objects": n, "new": new, "changed": changed, "unchanged": n - new - reactivated - changed,
            "reactivated": reactivated, "retired": retired}


# ---- each consumer's gate --------------------------------------------------

def state_table_ready(conn):
    return conn.execute("select to_regclass(%s) is not null", (STATE_TABLE,)).fetchone()[0]


def db_state(conn, consumer_id):
    """A consumer's last load as ops.osm_consumer has it (a dict), or {}."""
    if not state_table_ready(conn):
        return {}
    row = conn.execute(
        """select md5, extract_file, data_as_of, loaded_at, fetch_id, objects, counts
           from ops.osm_consumer where consumer = %s""", (consumer_id,)).fetchone()
    if not row:
        return {}
    return dict(zip(("md5", "extract_file", "data_as_of", "loaded_at", "fetch_id", "objects", "counts"), row))


def set_db_state(conn, consumer, md5, extract_name, data_as_of, fetch_id, objects, counts):
    conn.execute(
        """insert into ops.osm_consumer (consumer, source, md5, extract_file, data_as_of, loaded_at, fetch_id, objects,
             counts)
           values (%s, %s, %s, %s, %s, now(), %s, %s, %s::jsonb)
           on conflict (consumer) do update set source = excluded.source, md5 = excluded.md5,
             extract_file = excluded.extract_file, data_as_of = excluded.data_as_of, loaded_at = excluded.loaded_at,
             fetch_id = excluded.fetch_id, objects = excluded.objects, counts = excluded.counts""",
        (consumer.id, consumer.name, md5, extract_name, data_as_of, fetch_id, objects,
         json.dumps(counts, default=str)))


def own_gate(module):
    """Whether a consumer's module keeps its own state (osm_valley's last-loaded.json)."""
    return hasattr(module, "loaded_md5") and hasattr(module, "mark_loaded")


def loaded_md5(conn, consumer, module, folder):
    """The MD5 of the extract the consumer loaded last (None if it hasn't, or can't tell)."""
    if own_gate(module):
        return module.loaded_md5(folder) if folder else None
    return db_state(conn, consumer.id).get("md5") if conn is not None else None


# ---- the partition's owners hold one extract -------------------------------

def partition_gates(conn, all_consumers, folder):
    """[(consumer, MD5 of the extract it loaded last, or None)] for each installed partition owner,
    in OWNERS order. None: it hasn't loaded one, or its gate can't be read (osm_valley's needs the
    archive folder; the others' need conn)."""
    out = []
    for name in OWNERS:
        for c in all_consumers:
            if c.name == name:
                try:
                    out.append((c, loaded_md5(conn, c, c.module(), folder)))
                except Exception:
                    # A follower whose module won't import still has its row in ops.osm_consumer;
                    # osm_valley's gate needs its module, so it holds nothing we know.
                    try:
                        held = db_state(conn, c.id).get("md5") if conn is not None and c.name != LEADER else None
                    except Exception:
                        held = None
                    out.append((c, held))
    return out


def partition_note(gates):
    """A warning when the partition's owners that have loaded an extract hold different ones, else None."""
    held = [(c, m) for c, m in gates if m]
    if len({m for _, m in held}) <= 1:
        return None
    return ("partition: its owners hold different extracts (" + ", ".join(f"{c.id} {m[:8]}" for c, m in held)
            + "), so a way can be in two of their tables or in none; a build that reads them together refuses "
            "until they match: load the ones behind with --only")


def check_partition(conn, names=(LEADER, "osm_street"), all_consumers=None, folder=None):
    """For a build that reads several partition owners' tables together (P7: core.osm_way with
    roads.osm_street): the MD5 of the one extract they all hold. Raises RuntimeError when one isn't
    installed, hasn't loaded an extract (or its gate can't be read: osm_valley's needs TVT_ARCHIVE),
    or holds another extract than the rest, since their union would then have a way twice or not
    at all."""
    if unknown := sorted(set(names) - set(OWNERS)):
        raise ValueError(f"not partition owners: {', '.join(unknown)} (they are {', '.join(OWNERS)})")
    every = consumers() if all_consumers is None else all_consumers
    folder = archive_dir(required=False) if folder is None else folder
    gates = {c.name: (c, m) for c, m in partition_gates(conn, every, folder) if c.name in names}
    if missing := [n for n in names if n not in gates]:
        raise RuntimeError(f"partition: {', '.join(missing)} isn't installed")
    if unloaded := [c.id for c, m in gates.values() if not m]:
        raise RuntimeError(f"partition: {', '.join(unloaded)} hasn't loaded an extract (or its gate can't be read: "
                           "osm_valley's is in $TVT_ARCHIVE/osm/)")
    if len({m for _, m in gates.values()}) > 1:
        raise RuntimeError(partition_note(list(gates.values())))
    return next(iter(gates.values()))[1]


# ---- a load ----------------------------------------------------------------

def _stats_text(stats):
    return ", ".join(f"{k} {v}" for k, v in stats.items())


def load_extract(conn, path, chosen, *, every=None, force=False, allow_mixed=False, make_cut_ok=False,
                 allow_shrink=False, keep=True, out=print):
    """Load one extract into the chosen consumers (each by its own gate, unless force). every: all
    the installed consumers (default: chosen), where the partition's leader is found.

    The partition's owners load one extract together: osm_valley (the leader) runs first, and
    osm_street, osm_paving and osm_paths load only the extract it holds or loaded in this run; one
    that would load another is 'held'. So is the leader, when an installed follower that holds
    another extract isn't due in this run (not chosen, or its module won't import): it would be
    left on the old extract. allow_mixed lifts both holds; force doesn't. The valley cut is
    made when osm_valley is due (that run is heavy anyway, even if it's held) or with make_cut_ok;
    otherwise a missing cut stops the load before anything runs. A consumer whose module won't
    import, or whose source row can't be written, fails alone. With keep (--inbox, --file), the file is archived once any
    consumer has loaded it, and the archive pruned to the last two.
    Returns {consumer id: 'loaded' | 'skipped' | 'held' | 'failed'}."""
    if not _suffix(path):
        raise SystemExit(f"{path}: expected a .osm.pbf, .osm, .osm.bz2 or .osm.gz file")
    folder = archive_dir(required=False)
    md5 = check_md5(path)
    name = kept_name(path, folder, md5) if keep else os.path.basename(path)
    every = list(chosen) if every is None else list(every)
    leader = next((c for c in every if c.name == LEADER), None)
    result, modules = {}, {}
    for c in chosen:
        try:
            modules[c.id] = c.module()
        except Exception as err:                                 # the others go on
            result[c.id] = "failed"
            out(f"{c.id}: FAILED (its module didn't import: {type(err).__name__}: {err})")
    ready = [c for c in chosen if c.id in modules]
    if any(not own_gate(modules[c.id]) for c in ready) and not state_table_ready(conn):
        raise SystemExit(f"{STATE_TABLE} is missing: apply migration 0019 (python3 db/migrate.py)")
    due = []
    for c in ready:
        if not force and loaded_md5(conn, c, modules[c.id], folder) == md5:
            result[c.id] = "skipped"
            out(f"{c.id}: skipped, extract {md5[:8]} already loaded")
        else:
            due.append(c)
    due.sort(key=lambda c: c.name != LEADER)                     # the leader first; the rest keep their order
    leader_due = heavy = any(c.name == LEADER for c in due)  # a run with the leader due is heavy, held or not
    together = (f"Load them together, as the database owner ({LEADER} writes core.osm_way): osm-load without "
                "--only, or name each of them with --only. Or pass --allow-mixed")

    if leader_due and not allow_mixed:
        # The leader alone would leave a follower on another extract (--only osm_valley on a new one).
        coming = {c.name for c in due}
        behind = [(c, m) for c, m in partition_gates(conn, every, folder)
                  if c.name != LEADER and c.name not in coming and m and m != md5]
        if behind:
            lead = next(c for c in due if c.name == LEADER)
            result[lead.id] = "held"
            out(f"{lead.id}: held back: {', '.join(f'{c.id} holds extract {m[:8]}' for c, m in behind)} and "
                f"isn't loading {md5[:8]} in this run, and the partition's owners load one extract together. "
                + together)
            due, leader_due = [c for c in due if c is not lead], False

    def held_back(c):
        """Whether c, a follower, must wait for the leader to hold this extract (and say so)."""
        if leader is None or allow_mixed or c.name not in OWNERS or c.name == LEADER:
            return False
        if result.get(leader.id) == "loaded":
            return False
        try:
            holds = loaded_md5(conn, leader, modules.get(leader.id) or leader.module(), folder)
        except Exception:
            holds = None
        if holds == md5:
            return False
        result[c.id] = "held"
        out(f"{c.id}: held back: {leader.id} holds {'extract ' + holds[:8] if holds else 'no extract'}, not "
            f"{md5[:8]}, and the partition's owners load one extract together. " + together)
        return True

    if not leader_due:
        due = [c for c in due if not held_back(c)]
    if not due:
        if keep:
            out(f"nothing to load from {os.path.basename(path)} (left in place)")
        return result

    cut_dir = os.path.join(folder, CUT_DIR) if folder else None
    if not (heavy or make_cut_ok or cut_ready(cut_dir, md5)):
        raise SystemExit(f"no valley cut of {name} yet ({cut_dir or 'set TVT_ARCHIVE'}): make it first with "
                         f"'osm-load --cut-only', or add --make-cut, in a heavy job ({CUT_MEMORY}). A consumer's "
                         "load on a cut already made is light (under 0.2 GB)")
    stamp = data_timestamp(path)
    with tempfile.TemporaryDirectory(prefix="osm-load-", dir=folder) as work:
        cut, info, made = make_cut(path, md5, name, cut_dir or os.path.join(work, CUT_DIR), stamp)
        out(f"cut: {cut} ({'made' if made else 'reused'}, {info['bytes'] / 1e6:.1f} MB, extract {md5[:8]})")
        for c in due:
            if held_back(c):                                     # the leader ran in this run and failed
                continue
            module = modules[c.id]
            try:
                db.ensure_source(conn, module.SOURCE)
                conn.commit()
                with tempfile.TemporaryDirectory(prefix=f"{c.name}-", dir=work) as cwork:
                    with db.Fetch(conn, c.name) as f:            # no request made: robots and status stay empty
                        f.bytes = os.path.getsize(path)
                        run = Run(c, path, name, md5, cut, cwork, f, f.started_at, allow_shrink, stamp,
                                  work_parent=folder)
                        stats = module.consume(conn, run)
                        if f.records is None:
                            f.records = stats.get("objects")
                        if not own_gate(module):
                            set_db_state(conn, c, md5, name, stamp, f.id, stats.get("objects"),
                                         {**stats, **{k: v for k, v in run.counts.items()}})
            except Exception as err:                 # logged in ops.fetch (once it has a row); the others go on
                conn.rollback()
                result[c.id] = "failed"
                out(f"{c.id}: FAILED ({type(err).__name__}: {err})")
                continue
            result[c.id] = "loaded"
            out(f"{c.id}: {_stats_text({**stats, **run.counts})}")
    if keep and folder and "loaded" in result.values():
        kept = archive_file(path, folder, md5, name)
        for c in due:
            if result[c.id] == "loaded" and own_gate(modules[c.id]):
                modules[c.id].mark_loaded(folder, md5, kept)
        out(f"archived: {os.path.basename(kept)}")
        if pruned := prune(folder, protect=(kept,)):
            out(f"pruned: {', '.join(pruned)}")
    elif not keep and folder:
        for c in due:
            if result[c.id] == "loaded" and own_gate(modules[c.id]):
                modules[c.id].mark_loaded(folder, md5, path)
    if note := partition_note(partition_gates(conn, every, folder)):
        out(note)
    return result


def cut_only(path, out=print):
    """Make (or reuse) the valley cut of an extract, without loading anything."""
    folder = archive_dir(required=True)
    md5 = check_md5(path)
    cut, info, made = make_cut(path, md5, kept_name(path, folder, md5), os.path.join(folder, CUT_DIR),
                               data_timestamp(path))
    out(f"cut: {cut} ({'made' if made else 'reused'}, {info['bytes'] / 1e6:.1f} MB, extract {info['extract']}, "
        f"sha256 {info['sha256'][:12]})")
    return cut


def list_consumers(all_consumers, out=print):
    folder = archive_dir(required=False)
    conn = None
    if os.environ.get("DATABASE_URL"):
        conn = db.connect()
    try:
        for c in all_consumers:
            module = c.module()
            if own_gate(module):
                md5, where = (module.loaded_md5(folder) if folder else None), "its own file"
            elif conn is not None:
                md5, where = db_state(conn, c.id).get("md5"), STATE_TABLE
            else:
                md5, where = None, f"{STATE_TABLE} (set DATABASE_URL)"
            out(f"{c.id:24} {', '.join(c.geometry):32} last loaded {md5[:8] if md5 else '-':8} ({where})")
            out(f"{'':24} tags {' '.join(c.tags)}")
            out(f"{'':24} writes {', '.join(c.tables)}; {c.source['license']}, republish {c.source['republish']}")
        gates = partition_gates(conn, all_consumers, folder)
        if note := partition_note(gates):
            out(note)
        elif conn is not None and folder:
            held = {m for _, m in gates if m}
            waiting = [c.id for c, m in gates if not m]
            out("partition: " + (f"one extract ({held.pop()[:8]})" if held else "nothing loaded yet")
                + (f"; not loaded yet: {', '.join(waiting)}" if held and waiting else ""))
    finally:
        if conn is not None:
            conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest osm-load", description=__doc__.splitlines()[0])
    which = ap.add_mutually_exclusive_group()
    which.add_argument("--inbox", action="store_true", help="the newest extract in $TVT_ARCHIVE/osm/inbox/")
    which.add_argument("--file", help="this .osm.pbf or OSM XML file (copied into the archive)")
    which.add_argument("--archived", action="store_true",
                       help="the newest extract in the archive (the default with --only)")
    ap.add_argument("--only", action="append", metavar="CONSUMER",
                    help="just this consumer ('roads.osm_street' or 'osm_street'); repeat for more")
    ap.add_argument("--force", action="store_true", help="load it even into consumers that already have it")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="retire objects even when this extract has fewer than half the active ones")
    ap.add_argument("--allow-mixed", action="store_true",
                    help="let osm_street, osm_paving and osm_paths load an extract osm_valley doesn't hold, "
                         "or osm_valley load one they don't (their tables and core.osm_way then disagree)")
    ap.add_argument("--cut-only", action="store_true",
                    help=f"just make the valley cut, in $TVT_ARCHIVE/osm/cut/ (heavy: {CUT_MEMORY})")
    ap.add_argument("--make-cut", action="store_true",
                    help="make the valley cut if it's missing (heavy); a run with osm_valley due makes it anyway")
    ap.add_argument("--list", action="store_true", help="list the consumers and the extract each loaded last")
    args = ap.parse_args(argv)

    every = consumers()
    if args.list:
        list_consumers(every)
        return 0
    if not (args.inbox or args.file or args.archived or args.only or args.cut_only):
        ap.error("say which extract: --inbox, --file PATH or --archived (or --only, --cut-only, --list)")
    path, keep = args.file, bool(args.file)
    if args.inbox or args.archived or (not args.file):
        if not os.environ.get("TVT_ARCHIVE"):
            sys.exit("set TVT_ARCHIVE (extracts are kept in $TVT_ARCHIVE/osm/)")
        folder = archive_dir()
        if args.inbox:
            path, keep = inbox_file(folder), True
            if not path:
                sys.exit(f"no .osm.pbf, .osm, .osm.bz2 or .osm.gz file in {folder}/inbox/")
        else:
            held = extracts(folder)
            if not held:
                sys.exit(f"no extract in {folder}/ (load one with --inbox or --file)")
            path = held[0]
    if args.cut_only:
        cut_only(path)
        return 0
    chosen = select(every, args.only)
    with db.connect() as conn:
        result = load_extract(conn, path, chosen, every=every, force=args.force, allow_mixed=args.allow_mixed,
                              make_cut_ok=args.make_cut, allow_shrink=args.allow_shrink, keep=keep)
    return 1 if {"failed", "held"} & set(result.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
