#!/usr/bin/env python3
"""The base bake (plan C4, C17; package S5b): every export layer marked `base: true` into one versioned PMTiles file
of vector tiles, landscape-<digest>.pmtiles, z8-16, switched in with tiles/manifest.json's "landscape" entry.

    python3 basemap/landscape/bake.py status [--archive DIR] [--tiles DIR] [--no-hash]   # what a bake would hold
    python3 basemap/landscape/bake.py bake --tiles DIR [--archive DIR] [--work DIR]      # bake and switch it in
    python3 basemap/landscape/bake.py check --tiles DIR [--public]                       # the entry and the files
    python3 basemap/landscape/bake.py rollback --tiles DIR                               # back to the previous bake

`bake` runs in the worker image (GDAL's PMTiles writer); the others need only the standard library. The archive is
$TVT_ARCHIVE unless --archive says otherwise. Exit codes: 0 done (or nothing to change); 1 a check failed (`check`)
or the writer failed; 2 refused (a missing folder, a broken export, a layer or feature that may not be baked, a file
already named for this bake that isn't it, or a source-layer the served bake has that this one wouldn't build,
without --allow-drop); 3 nothing to bake (`status`); 4 over the byte budget (nothing switched in).

A bake: the newest export of each plugin that has a base layer is read (its manifest checked, and its base layers'
files with their sha256), each base layer with features is written as one source-layer `<plugin>.<layer>` with its
`id` as both the vector tile's feature id and a property (promoteId), read back, measured against the downtown z16
budget, given the bake's entry and credits in its metadata, and renamed into the tiles folder. Then the manifest's
entry is replaced atomically (the old file becomes `previous`), and every other landscape file is deleted, so the
last two are kept. The same exports give the same file name: a bake with nothing new switches nothing. A bake that
would leave out a source-layer the served one has (or switch to empty) is refused unless --allow-drop says so.
"""

import argparse
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from basemap.ground import grid, manifest as M  # noqa: E402
from basemap.landscape import plan as P, pmtiles  # noqa: E402

EXIT_FAILED, EXIT_REFUSED, EXIT_NOTHING, EXIT_BUDGET = 1, 2, 3, 4
GEOMETRY = {"Point": "wkbPoint", "LineString": "wkbLineString", "Polygon": "wkbPolygon",
            "MultiPoint": "wkbMultiPoint", "MultiLineString": "wkbMultiLineString", "MultiPolygon": "wkbMultiPolygon"}


def _say(*a):
    print(*a, flush=True)


def _err(*a):
    print(*a, file=sys.stderr, flush=True)


# --- the writer (worker image) ----------------------------------------------------------------------------------

def _gdal():
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
    ogr.UseExceptions()
    osr.UseExceptions()
    # Never fetch PROJ grids (the worker image sets PROJ_NETWORK=OFF too; this holds whatever the environment says):
    # UTM 11N to Web Mercator needs none.
    osr.SetPROJEnableNetwork(False)
    gdal.SetConfigOption("PROJ_NETWORK", "OFF")
    os.environ["PROJ_NETWORK"] = "OFF"
    return gdal, ogr, osr


def writer_version():
    gdal, _, _ = _gdal()
    return f"GDAL {gdal.__version__}"


def _ogr_type(ogr, kind):
    """(OGR field type, subtype) for a manifest field type."""
    if kind in ("byte", "ubyte", "short", "ushort", "int"):
        return ogr.OFTInteger, ogr.OFSTNone
    if kind in ("uint", "long", "ulong"):
        return ogr.OFTInteger64, ogr.OFSTNone
    if kind == "bool":
        return ogr.OFTInteger, ogr.OFSTBoolean
    if kind == "float":
        return ogr.OFTReal, ogr.OFSTFloat32
    if kind == "double":
        return ogr.OFTReal, ogr.OFSTNone
    if kind == "string":
        return ogr.OFTString, ogr.OFSTNone
    raise P.BakeError(f"field type {kind} can't go into a vector tile")


def write_tiles(plan, out, threads=2):
    """Write the plan's base layers to a PMTiles file at `out` with GDAL, its tile encoding on `threads` threads (the
    job's CPUs: inside a container GDAL would count the host's). Every layer is read and counted; an empty one gets
    no source-layer. Returns {source layer: features}. Raises BakeError for a feature the bake can't take: no
    geometry, a geometry that isn't the layer's type or its multi form, an id that's missing, out of range or
    repeated in its layer, or a minzoom past its layer's maxzoom."""
    gdal, ogr, osr = _gdal()
    gdal.SetConfigOption("GDAL_NUM_THREADS", str(threads))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(grid.CRS.split(":")[1]))
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    w = P.WRITER
    ds = gdal.GetDriverByName("PMTiles").Create(out, 0, 0, 0, gdal.GDT_Unknown, options=[
        f"MINZOOM={P.MINZOOM}", f"MAXZOOM={P.MAXZOOM}", "NAME=landscape", "TYPE=overlay",
        "DESCRIPTION=Treasure Valley Traffic: the base contributions (basemap/landscape)",
        f"EXTENT={w['extent']}", f"BUFFER={w['buffer']}", f"SIMPLIFICATION={w['simplification']}",
        f"SIMPLIFICATION_MAX_ZOOM={w['simplificationMaxZoom']}", f"MAX_SIZE={w['maxSize']}",
        f"MAX_FEATURES={w['maxFeatures']}"])
    if ds is None:
        raise P.BakeError(f"GDAL couldn't create {out}")
    counts = {}
    try:
        for base in plan.bases:
            counts[base.id] = _write_layer(ds, ogr, srs, base)
    finally:
        ds = None                                      # GDAL writes the tiles when the dataset closes
    return counts


def _write_layer(ds, ogr, srs, base):
    sid, lay = base.id, base.layer
    src = ogr.Open(lay.path)
    if src is None or src.GetLayerCount() != 1:
        raise P.BakeError(f"{lay.ref}: GDAL can't read {lay.path} as one FlatGeobuf layer")
    sl = src.GetLayer(0)
    defn = sl.GetLayerDefn()
    have = {defn.GetFieldDefn(i).GetName(): i for i in range(defn.GetFieldCount())}
    if set(have) != set(lay["fields"]):
        raise P.BakeError(f"{lay.ref}: the file's fields {sorted(have)} aren't the manifest's")
    fields = base.fields
    geom_type = getattr(ogr, GEOMETRY[lay["geometry"]])
    family = {getattr(ogr, GEOMETRY[t]) for t in P.GEOMETRY_FAMILY[lay["geometry"]]}
    targets = {}

    def target(z):
        if z not in targets:
            t = ds.CreateLayer(f"{sid}@z{z}", srs, geom_type, options=[
                f"MINZOOM={z}", f"MAXZOOM={base.maxzoom}", f"NAME={sid}",
                f"DESCRIPTION={lay.get('title', lay.ref)}"])
            for name, kind in fields.items():
                ftype, sub = (ogr.OFTInteger64, ogr.OFSTNone) if name == P.ID_FIELD else _ogr_type(ogr, kind)
                fd = ogr.FieldDefn(name, ftype)
                fd.SetSubType(sub)
                t.CreateField(fd)
            targets[z] = t
        return targets[z]

    seen, bad, n = set(), [], 0
    i_id, i_mz = have[P.ID_FIELD], have.get(P.MINZOOM_FIELD)
    copy = [(name, have[name]) for name in fields]
    for f in sl:
        n += 1
        fid = f.GetFieldAsInteger64(i_id) if f.IsFieldSetAndNotNull(i_id) else None
        g = f.GetGeometryRef()
        why = None
        if fid is None:
            why = "no id"
        elif not 0 <= fid <= P.MAX_ID:
            why = f"id {fid} is outside 0..2^53-1"
        elif fid in seen:
            why = f"id {fid} is repeated"
        elif g is None or g.IsEmpty():
            why = f"id {fid} has no geometry"
        elif ogr.GT_Flatten(g.GetGeometryType()) not in family:
            why = (f"id {fid} is a {ogr.GeometryTypeToName(g.GetGeometryType())}, not a {lay['geometry']} or its "
                   "multi form")
        z = base.minzoom
        if why is None and i_mz is not None and f.IsFieldSetAndNotNull(i_mz):
            fz = min(f.GetFieldAsInteger(i_mz), P.MAXZOOM)
            z = max(z, fz)
            if z > base.maxzoom:
                why = f"id {fid}'s minzoom {f.GetFieldAsInteger(i_mz)} is past the layer's maxzoom {base.maxzoom}"
        if why:
            bad.append(why)
            if len(bad) >= 5:
                break
            continue
        seen.add(fid)
        t = target(z)
        out = ogr.Feature(t.GetLayerDefn())
        out.SetFID(fid)                                  # the vector tile's feature id
        for name, i in copy:
            if not f.IsFieldSetAndNotNull(i):
                out.SetFieldNull(name)
            elif name == P.ID_FIELD:
                out.SetField(name, fid)                  # the promoteId property
            else:
                out.SetField(name, f.GetField(i))
        out.SetGeometry(g)
        t.CreateFeature(out)
    if bad:
        raise P.BakeError(f"{lay.ref}: {len(bad)}{'+' if len(bad) >= 5 else ''} feature(s) can't be baked: "
                          + "; ".join(bad))
    if n != lay["features"]:
        raise P.BakeError(f"{lay.ref}: the file holds {n:,} features, the manifest says {lay['features']:,}")
    src = None
    return len(seen)


def read_back(path, plan):
    """Check a fresh file before it's switched in: a PMTiles of gzipped vector tiles at the spec's zooms, whose
    source-layers are exactly the plan's built ones, and which GDAL opens."""
    h = pmtiles.read_header(path)
    if (h.tile_type_name, h.tile_compression_name, h.min_zoom, h.max_zoom) != ("mvt", "gzip", P.MINZOOM, P.MAXZOOM):
        raise P.BakeError(f"{path}: {h.tile_type_name} tiles ({h.tile_compression_name}), z{h.min_zoom}-"
                          f"{h.max_zoom}; the spec is gzipped mvt, z{P.MINZOOM}-{P.MAXZOOM}")
    meta = pmtiles.read_metadata(path)
    got = source_layers(meta)
    want = set(plan.ids)
    if got != want:
        raise P.BakeError(f"{path}: source layers {sorted(got)}, expected {sorted(want)}")
    gdal, _, _ = _gdal()
    ds = gdal.OpenEx(path)
    names = {ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())}
    if not want <= names:
        raise P.BakeError(f"{path}: GDAL reads layers {sorted(names)}, expected {sorted(want)}")
    return meta


def metadata_with(meta, entry):
    """GDAL's metadata plus the bake's credits and entry (`tvt.landscape`), which `check` and `rollback` read, with
    the zooms the file holds tiles at."""
    out = dict(meta)
    out["minzoom"], out["maxzoom"] = str(entry["minzoom"]), str(entry["maxzoom"])
    if isinstance(out.get("center"), str) and out["center"].count(",") == 2:
        lon, lat, z = out["center"].split(",")
        out["center"] = f"{lon},{lat},{min(max(int(float(z)), entry['minzoom']), entry['maxzoom'])}"
    out["attribution"] = entry["attribution"]
    out["description"] = (f"Treasure Valley Traffic's base contributions: {', '.join(entry['layers'])}. Republish "
                          f"{entry['republish']}; served to the {entry['access']} only"
                          if entry["access"] != "public" else
                          f"Treasure Valley Traffic's base contributions: {', '.join(entry['layers'])}")
    out["tvt"] = {"landscape": entry}
    return out


def source_layers(meta):
    """The source-layers a file's metadata lists (vector_layers' ids)."""
    vl = meta.get("vector_layers")
    return {v.get("id") for v in vl if isinstance(v, dict)} if isinstance(vl, list) else set()


def meta_entry(meta):
    """The bake entry a landscape file's metadata holds, or None."""
    t = meta.get("tvt")
    return t.get("landscape") if isinstance(t, dict) else None


def file_entry(path):
    """The bake entry a landscape file's metadata holds, or None."""
    return meta_entry(pmtiles.read_metadata(path))


# --- commands ---------------------------------------------------------------------------------------------------

def _archive(args):
    return args.archive or os.environ.get("TVT_ARCHIVE")


def _plan(args, verify=True):
    """(plan, None) or (None, exit code) after saying why it was refused."""
    try:
        return P.resolve(P.exports(_archive(args)), verify=verify, hashes=not getattr(args, "no_hash", False)), None
    except (P.BakeError, M.ManifestError) as err:
        _err(f"refused: {err}")
        return None, EXIT_REFUSED


def _describe(plan):
    for b in plan.bases:
        lay = b.layer
        z = f"z{b.minzoom}-{b.maxzoom}" + (", per feature" if b.per_feature_minzoom else "")
        _say(f"  {b.id:24} {lay.ref} ({lay['geometry']}, {lay['features']:,} features, {z}), {lay['licence']}, "
             f"republish {lay['republish']}" + ("" if lay["features"] else ": empty, so not built"))
    for plugin, why in plan.skipped:
        _say(f"  ({why})")
    if plan.built:
        _say(f"Republish {plan.republish}: served to the {plan.access}"
             + (" only, while these carry internal data: " + "; ".join(
                 f"{sid} ({', '.join(c)})" for sid, c in plan.internal) if plan.internal else ""))
        _say("Credit: " + "; ".join(plan.credits))


def cmd_status(args):
    plan, code = _plan(args)
    if plan is None:
        return code
    _say(f"Base layers in the newest exports under {_archive(args)}: {len(plan.bases)}")
    _describe(plan)
    if args.tiles:
        try:
            cur = P.current(args.tiles)
        except P.BakeError as err:
            _err(f"refused: {err}")
            return EXIT_REFUSED
        try:
            if cur is not None:
                P.check_entry(cur)
        except ValueError as err:
            _say(f"Tiles: the landscape entry is broken ({err}); a bake would replace it")
        else:
            _say_tiles(cur, plan)
    if not plan.bases:
        _say(plan.reason)
        return EXIT_NOTHING
    return 0


def _say_tiles(cur, plan):
    """How the tiles folder's entry compares with what a bake would hold."""
    if not cur:
        _say("Tiles: no landscape entry yet")
    elif cur["status"] == "empty":
        _say(f"Tiles: empty ({cur['reason']})" + (", so a bake would switch one in" if plan.built else ""))
    else:
        if cur["inputs"] == plan.refs:
            _say(f"Tiles: {cur['file']}, built {cur['built']} from these exports (up to date)")
        else:
            new, old = set(plan.refs), set(cur["inputs"])
            _say(f"Tiles: {cur['file']}, built {cur['built']} from other exports: a bake would read "
                 f"{', '.join(sorted(new - old)) or 'nothing new'} and no longer "
                 f"{', '.join(sorted(old - new)) or 'anything it reads now'}")
        dropped = sorted(set(cur["layers"]) - set(plan.ids))
        if dropped:
            _say("  It would leave out source-layer(s) the served file has, so it's refused without --allow-drop: "
                 + "; ".join(f"{sid} ({plan.why_not_built(sid)})" for sid in dropped))


def _previous(tiles_dir, raw, name):
    """The file the new entry keeps as previous: the one served until now (or, for an unchanged bake or an empty
    entry, the one it kept), if it's still there. raw: the manifest's entry as it is, even a broken one, so the file
    it names is kept while clients may still be reading it."""
    if not isinstance(raw, dict):
        return None
    for prev in (raw.get("file"), raw.get("previous")):
        if (isinstance(prev, str) and P.FILE_RE.match(prev) and prev != name
                and os.path.isfile(os.path.join(tiles_dir, prev))):
            return prev
    return None


def _checked(raw):
    """The manifest's landscape entry when it's sound, else None (saying why)."""
    if raw is None:
        return None
    try:
        P.check_entry(raw)
    except ValueError as err:
        _err(f"the manifest's landscape entry is broken ({err}); this bake replaces it, keeping the file it names "
             "(if that's there) as previous")
        return None
    return raw


def _served(tiles_dir, raw, old):
    """(the file served now, its source-layers): from the entry, or for a broken entry from the file's own
    metadata. (None, []) when nothing is served."""
    if old is not None:
        return (old["file"], sorted(old["layers"])) if old["status"] == "baked" else (None, [])
    name = raw.get("file") if isinstance(raw, dict) else None
    if not (isinstance(name, str) and P.FILE_RE.match(name) and os.path.isfile(os.path.join(tiles_dir, name))):
        return None, []
    try:
        made = file_entry(os.path.join(tiles_dir, name))
        P.check_entry(made, in_manifest=False)
    except (pmtiles.PMTilesError, ValueError) as err:
        _err(f"{name}'s own metadata doesn't say what it serves ({err}), so a bake can't tell what it would drop")
        return name, []
    return name, sorted(made["layers"])


def _switch_empty(tiles_dir, raw, old, reason):
    """Record that there's nothing to bake: an empty entry that keeps the file served until now as previous."""
    entry = P.empty_entry(reason, previous=_previous(tiles_dir, raw, None))
    if old and old.get("status") == "empty" and old["reason"] == entry["reason"] \
            and old["previous"] == entry["previous"]:
        _say(f"landscape-bake: nothing to bake, and the entry already says so ({reason})")
        return 0
    P.update_manifest(tiles_dir, entry)
    gone = P.prune(tiles_dir, entry)
    _say(f"landscape-bake: nothing to bake ({reason}); entry set to empty"
         + (f", removed {', '.join(gone)}" if gone else ""))
    return 0


def _bake_file(plan, tiles_dir, work, digest, writer, threads=2):
    """Write, read back, measure and rename one bake into the tiles folder. Returns (its entry, None), ("empty",
    None) when every layer is empty (GDAL writes no file then; the writer still counts each), or (None, exit code)
    after saying why."""
    name = P.file_name(digest)
    mine_work = work is None
    work = work or tempfile.mkdtemp(prefix="landscape-")
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, f"raw-{os.getpid()}.pmtiles")
    part = os.path.join(tiles_dir, f"{P.PART_PREFIX}{digest[:12]}.pmtiles.{os.getpid()}.part")
    try:
        try:
            counts = write_tiles(plan, raw, threads)
            if counts != {b.id: b.layer["features"] for b in plan.bases}:     # _write_layer refuses a mismatch
                raise P.BakeError(f"the writer's counts {counts} aren't the manifests'")
            if not plan.built:
                return "empty", None
            meta = read_back(raw, plan)
        except P.BakeError as err:
            _err(f"refused: {err}")
            return None, EXIT_REFUSED
        except (RuntimeError, OSError, pmtiles.PMTilesError) as err:   # GDAL's, or a file it wrote badly
            _err(f"failed: {err}")
            return None, EXIT_FAILED
        sizes = pmtiles.tile_sizes(raw)
        report(sizes)
        mine = {t: sizes[t] for t in P.budget_tiles() if t in sizes}
        budget = P.measure_budget(mine, plan.roads)
        over = P.over_budget(mine)
        _say(f"Budget: z{budget['zoom']} {budget['box']}: {budget['tiles']} tile(s), largest "
             f"{budget['largest']:,} bytes{' at ' + budget['at'] if budget['at'] else ''} (at most "
             f"{budget['maxBytes']:,})" + ("" if plan.roads else "; roads isn't in the bake yet"))
        if over:
            _err("over budget, so nothing is switched in: " + ", ".join(
                f"{'/'.join(map(str, t))} {n:,} bytes" for t, n in over[:10]))
            return None, EXIT_BUDGET
        zooms = pmtiles.zoom_range(sizes)
        made = P.baked_entry(plan, digest, budget, writer, zooms=zooms)
        P.check_entry(made, in_manifest=False)
        pmtiles.write_with_metadata(raw, part, metadata_with(meta, made), zooms)
        os.chmod(part, 0o644)
        os.replace(part, os.path.join(tiles_dir, name))
        P.fsync_dir(tiles_dir)
        return made, None
    finally:
        if os.path.exists(part):
            os.unlink(part)
        if mine_work:
            shutil.rmtree(work, ignore_errors=True)
        else:
            for f in os.listdir(work):
                if f.startswith(f"raw-{os.getpid()}.pmtiles"):
                    os.unlink(os.path.join(work, f))


def cmd_bake(args):
    tiles_dir = args.tiles
    if not os.path.isdir(tiles_dir):
        _err(f"refused: no tiles folder at {tiles_dir}")
        return EXIT_REFUSED
    with P.locked(tiles=tiles_dir):
        for f in os.listdir(tiles_dir):                       # an earlier bake that was stopped
            if f.startswith(P.PART_PREFIX):
                os.unlink(os.path.join(tiles_dir, f))
        plan, code = _plan(args)
        if plan is None:
            return code
        try:
            raw = P.current(tiles_dir)
        except P.BakeError as err:
            _err(f"refused: {err}")
            return EXIT_REFUSED
        old = _checked(raw)
        _say(f"Base layers: {len(plan.bases)}")
        _describe(plan)

        served, layers = _served(tiles_dir, raw, old)
        dropped = sorted(set(layers) - set(plan.ids))
        if dropped and not args.allow_drop:
            _err(f"refused: {served} is served with source-layer(s) this bake wouldn't build: "
                 + "; ".join(f"{sid} ({plan.why_not_built(sid)})" for sid in dropped)
                 + (". It would switch the landscape to empty" if not plan.built else
                    ". They would vanish from the map")
                 + ". If that's meant, bake again with --allow-drop (the served file is kept as previous, for "
                 "rollback)")
            return EXIT_REFUSED
        if not plan.bases:
            return _switch_empty(tiles_dir, raw, old, plan.reason)
        try:
            writer = writer_version()
        except ImportError as err:
            _err(f"refused: the bake needs GDAL (the worker image): {err}")
            return EXIT_REFUSED
        digest = P.digest(plan, writer)
        name = P.file_name(digest)
        final = os.path.join(tiles_dir, name)

        if os.path.exists(final):
            try:
                made = file_entry(final)
                if not made or made.get("digest") != digest:
                    raise P.BakeError("its metadata names another bake")
                P.check_entry(made, in_manifest=False)
            except (P.BakeError, pmtiles.PMTilesError, ValueError) as err:
                _err(f"refused: {final} exists but isn't this bake ({err}); it's never overwritten: move it away "
                     "if it isn't served")
                return EXIT_REFUSED
            _say(f"{name} already holds these exports")
        else:
            made, code = _bake_file(plan, tiles_dir, args.work, digest, writer, args.threads)
            if made is None:
                return code
            if made == "empty":
                return _switch_empty(tiles_dir, raw, old, plan.reason)

        entry = dict(made, previous=_previous(tiles_dir, raw, name))
        if old == entry:
            _say(f"landscape-bake: {name} is already switched in; nothing changed")
            return 0
        P.update_manifest(tiles_dir, entry)
        gone = P.prune(tiles_dir, entry)
        total = sum(v["features"] for v in entry["layers"].values())
        _say(f"landscape-bake: switched in {name} ({len(entry['layers'])} layer(s), {total:,} features, "
             f"{os.path.getsize(final) / 1e6:.1f} MB), republish {entry['republish']}, "
             f"served to the {entry['access']}{' only' if entry['access'] != 'public' else ''}; kept "
             f"{entry['previous'] or 'no previous file'}" + (f"; removed {', '.join(gone)}" if gone else "")
             + (f"; empty, so not built: {', '.join(entry['empty'])}" if entry["empty"] else "")
             + (f"; dropped {', '.join(dropped)} (--allow-drop)" if dropped else ""))
        return 0


def report(sizes):
    """The largest tile and the total per zoom."""
    by_z = {}
    for (z, x, y), n in sizes.items():
        c, tot, big, at = by_z.get(z, (0, 0, -1, None))
        by_z[z] = (c + 1, tot + n, max(big, n), (x, y) if n > big else at)
    for z in sorted(by_z):
        c, tot, big, at = by_z[z]
        _say(f"  z{z}: {c:,} tiles, {tot / 1e6:.2f} MB, largest {big:,} bytes at {z}/{at[0]}/{at[1]}")


def check(tiles_dir, public=False):
    """[problem] with the tiles folder's landscape entry and files (none: fine). With public, also every landscape
    file there that may not be served beyond the tailnet: everything in the folder is served, the kept previous
    file included."""
    problems = []
    try:
        entry = P.current(tiles_dir)
    except P.BakeError as err:
        return [str(err)]
    if entry is not None:
        try:
            P.check_entry(entry)
        except ValueError as err:
            problems.append(f"the manifest's landscape entry: {err}")
            entry = None
    if entry and entry["status"] == "baked":
        path = os.path.join(tiles_dir, entry["file"])
        if not os.path.isfile(path):
            problems.append(f"{entry['file']}: the entry's file is missing")
        else:
            try:
                h = pmtiles.read_header(path)
                meta = pmtiles.read_metadata(path)
                made = meta_entry(meta)
                if source_layers(meta) != set(entry["layers"]):
                    problems.append(f"{entry['file']}: its source-layers {sorted(source_layers(meta))} aren't the "
                                    f"entry's layers {sorted(entry['layers'])}")
                if (h.tile_type_name, h.tile_compression_name, h.min_zoom, h.max_zoom) != (
                        "mvt", "gzip", entry["minzoom"], entry["maxzoom"]):
                    problems.append(f"{entry['file']}: not gzipped mvt at the entry's z{entry['minzoom']}-"
                                    f"{entry['maxzoom']}")
                if made != {k: v for k, v in entry.items() if k != "previous"}:
                    problems.append(f"{entry['file']}: its metadata's entry isn't the manifest's")
                mine = pmtiles.tile_sizes(path, P.budget_tiles())
                b = P.measure_budget(mine, entry["budget"]["roads"])
                if b != entry["budget"]:
                    problems.append(f"{entry['file']}: its tiles measure {b}, the entry says {entry['budget']}")
            except pmtiles.PMTilesError as err:
                problems.append(f"{entry['file']}: {err}")
    if entry and entry.get("previous") and not os.path.isfile(os.path.join(tiles_dir, entry["previous"])):
        problems.append(f"{entry['previous']}: the previous file is missing")
    if public:
        if entry and entry["status"] == "baked" and entry["access"] != "public":
            problems.append(f"{entry['file']}: republish {entry['republish']}, tailnet only (the manifest serves it)")
        for f in P.files(tiles_dir):
            try:
                made = file_entry(os.path.join(tiles_dir, f))
            except pmtiles.PMTilesError as err:
                problems.append(f"{f}: unreadable, so its access is unknown ({err})")
                continue
            if not isinstance(made, dict) or "republish" not in made:
                problems.append(f"{f}: its metadata doesn't say who may see it")
            elif made["republish"] != "yes" or made.get("access") != "public":
                problems.append(f"{f}: republish {made['republish']}, tailnet only (it's in the served folder)")
        for f in sorted(os.listdir(tiles_dir)):
            if f.startswith(P.PART_PREFIX):
                problems.append(f"{f}: a stopped bake's part file, a full copy of its tiles, in the served folder "
                                "(the next bake removes it; or delete it)")
    return problems


def cmd_check(args):
    problems = check(args.tiles, public=args.public)
    for p in problems:
        _err(f"problem: {p}")
    if problems:
        return EXIT_FAILED
    try:
        entry = P.current(args.tiles)
    except P.BakeError as err:
        _err(str(err))
        return EXIT_FAILED
    if not entry:
        _say("no landscape entry yet")
    elif entry["status"] == "empty":
        _say(f"landscape: empty ({entry['reason']})")
    else:
        _say(f"landscape: {entry['file']} ({len(entry['layers'])} layer(s), built {entry['built']}), republish "
             f"{entry['republish']}, served to the {entry['access']}; budget {entry['budget']['largest']:,} of "
             f"{entry['budget']['maxBytes']:,} bytes")
    if args.public:
        _say("every landscape file in the folder may be served publicly")
    return 0


def cmd_rollback(args):
    tiles_dir = args.tiles
    with P.locked(tiles=tiles_dir):
        try:
            old = P.current(tiles_dir)
        except P.BakeError as err:
            _err(f"refused: {err}")
            return EXIT_REFUSED
        prev = old.get("previous") if isinstance(old, dict) else None
        if not isinstance(prev, str) or not P.FILE_RE.match(prev) or not os.path.isfile(os.path.join(tiles_dir, prev)):
            _err("refused: there's no previous landscape file to go back to")
            return EXIT_REFUSED
        try:
            made = file_entry(os.path.join(tiles_dir, prev))
            P.check_entry(made, in_manifest=False)
        except (pmtiles.PMTilesError, ValueError, TypeError) as err:
            _err(f"refused: {prev} doesn't hold a bake entry ({err})")
            return EXIT_REFUSED
        entry = dict(made, previous=_previous(tiles_dir, old, prev))
        P.update_manifest(tiles_dir, entry)
        _say(f"landscape: back to {prev} (built {made['built']}); {entry['previous'] or 'nothing'} kept as previous")
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status", help="what a bake would hold, and whether the tiles are up to date")
    p.add_argument("--archive", help="default: $TVT_ARCHIVE")
    p.add_argument("--tiles", help="compare with this tiles folder's entry")
    p.add_argument("--no-hash", action="store_true", help="skip the sha256 of each base layer's file")
    p = sub.add_parser("bake", help="bake the base layers and switch the file in (worker image)")
    p.add_argument("--tiles", required=True, help="the tiles folder (its manifest.json is updated)")
    p.add_argument("--archive", help="default: $TVT_ARCHIVE")
    p.add_argument("--work", help="where GDAL writes before the file moves in (default: a temporary folder)")
    p.add_argument("--threads", type=int, default=2, help="GDAL's threads for encoding tiles: the job's CPUs "
                   "(default 2, the heavy-job table's)")
    p.add_argument("--allow-drop", action="store_true",
                   help="switch in a bake without a source-layer the served one has, or switch to empty")
    p = sub.add_parser("check", help="check the entry and the files (exit 1 on a problem)")
    p.add_argument("--tiles", required=True)
    p.add_argument("--public", action="store_true",
                   help="also fail when any landscape file in the folder is tailnet-only")
    p = sub.add_parser("rollback", help="switch back to the previous bake (both files are kept)")
    p.add_argument("--tiles", required=True)
    args = ap.parse_args(argv)
    return {"status": cmd_status, "bake": cmd_bake, "check": cmd_check, "rollback": cmd_rollback}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
