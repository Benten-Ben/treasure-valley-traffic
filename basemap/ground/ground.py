#!/usr/bin/env python3
"""The ground's contract on the command line (basemap/ground/README.md). Standard library only.

    python3 basemap/ground/ground.py spec                              # the grid, the boxes, the tiles, the budget
    python3 basemap/ground/ground.py check-export DIR [--no-hash]      # check one export folder and its files
    python3 basemap/ground/ground.py status [--archive DIR] [--no-hash]   # what the ground would read today
    python3 basemap/ground/ground.py flat --tiles DIR (--archive DIR | --reason TEXT)
                                                                       # record a flat ground in tiles/manifest.json

status and flat read each plugin's newest export under $TVT_ARCHIVE (or --archive). status exits 0 when the ground
can be painted, 3 when it would stay flat, and 2 when an export it would read isn't public or isn't the right shape.
"""

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from basemap.ground import grid, inputs, manifest, tiles  # noqa: E402


def cmd_spec(_args):
    print(f"Grid: {grid.CRS}, upper-left E {grid.ORIGIN_X} N {grid.ORIGIN_Y}; extent E {grid.WEST}-{grid.EAST}, "
          f"N {grid.SOUTH}-{grid.NORTH}")
    for name, res in grid.LEVELS.items():
        cols, rows = grid.size(res)
        print(f"  {name:9} {res:>4g} m  {cols:,} x {rows:,} cells")
    print("Class boxes (0.5 m windows):")
    for b in grid.boxes():
        w = b.window()
        print(f"  {b.id:8} {b.name} ({b.county}): E {b.utm[0]}-{b.utm[2]}, N {b.utm[1]}-{b.utm[3]}, "
              f"{w.width:,} x {w.height:,} cells")
    lat = (grid.MAP_LONLAT[1] + grid.MAP_LONLAT[3]) / 2
    c = tiles.counts()
    print(f"Tiles: {tiles.TILE_SIZE} px {tiles.FORMAT} (quality {tiles.QUALITY}), opaque")
    print(f"  valley z{tiles.VALLEY_ZOOMS[0]}-z{tiles.VALLEY_ZOOMS[1]}: {sum(c['valley'].values()):,} tiles "
          f"({', '.join(f'z{z} {n:,}' for z, n in c['valley'].items())}); "
          f"{tiles.mpp(tiles.VALLEY_ZOOMS[1], lat):.2f} m per pixel at z{tiles.VALLEY_ZOOMS[1]}")
    print(f"  detail z{tiles.DETAIL_ZOOMS[0]}-z{tiles.DETAIL_ZOOMS[1]}: {sum(c['detail'].values()):,} tiles "
          f"({', '.join(f'z{z} {n:,}' for z, n in c['detail'].items())}); "
          f"{tiles.mpp(tiles.DETAIL_ZOOMS[1], lat):.2f} m per pixel at z{tiles.DETAIL_ZOOMS[1]}")
    b = tiles.BUDGET
    v = b["view"]
    print(f"First-load budget at z{v['zoom']}, pitch {v['pitch']}, {v['viewport'][0]} x {v['viewport'][1]}: Valley "
          f"<= {b['valleyDefault']['maxBytes'] / 1e6:g} MB and <= {b['valleyDefault']['maxRequests']} requests; "
          f"Clay {b['clayDefault']['maxRequests']} requests")
    return 0


def cmd_check_export(args):
    try:
        m = manifest.read(args.dir, verify=True, hashes=not args.no_hash)
    except manifest.ManifestError as err:
        print(f"not valid: {err}", file=sys.stderr)
        return 2
    print(f"{m.plugin}@{m.build}: {len(m.layers)} layer(s), republish {m.republish}")
    for lay in m.layers:
        extra = (f"{lay['geometry']}, {lay['features']:,} features" if lay["format"] == "FlatGeobuf" else
                 f"{lay['grid']['width']} x {lay['grid']['height']} at {lay['grid']['res']:g} m"
                 if lay["format"] == "GeoTIFF" else lay["schema"])
        print(f"  {lay.name}: {lay['file']} ({lay['format']}; {extra}), {lay['licence']}, republish "
              f"{lay['republish']}{', base' if lay['base'] else ''}")
    print("Credit: " + "; ".join(m.credits))
    return 0


def _plan(args):
    archive = args.archive or os.environ.get("TVT_ARCHIVE")
    if not archive:
        raise SystemExit("give --archive or set TVT_ARCHIVE")
    return inputs.resolve(manifest.find(archive, verify=True, hashes=not args.no_hash))


def cmd_status(args):
    try:
        plan = _plan(args)
    except (manifest.ManifestError, inputs.InputError) as err:
        print(f"refused: {err}", file=sys.stderr)
        return 2
    for c in plan.choices:
        if c.layer is not None:
            print(f"  {c.use.ref:18} {c.layer.ref} ({c.layer['licence']}, republish {c.layer['republish']})")
        else:
            print(f"  {c.use.ref:18} {'FLAT' if c.use.fallback is None else 'fallback: ' + c.use.fallback} "
                  f"({c.reason})")
    print("Raw inputs: " + ", ".join(f"{r.name} ({r.licence})" for r in plan.raw))
    if plan.status == "flat":
        print(plan.reason)
        return 3
    print(f"Painted: {plan.licence} ({inputs.GROUND_ABOUT}), republish {plan.republish}")
    print("Credit: " + "; ".join(plan.credits))
    return 0


def cmd_flat(args):
    if args.reason:
        reason = args.reason
    else:
        plan = _plan(args)
        if plan.status != "flat":
            print("the ground can be painted; nothing to record as flat", file=sys.stderr)
            return 2
        reason = plan.reason
    path = tiles.update_manifest(args.tiles, tiles.flat_entry(reason))
    print(f"{path}: ground is flat ({reason})")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spec", help="the grid, the boxes, the tiles and the budget")
    p = sub.add_parser("check-export", help="check one export folder (its manifest and files)")
    p.add_argument("dir")
    p.add_argument("--no-hash", action="store_true", help="skip the sha256 of each file")
    p = sub.add_parser("status", help="what the ground would read, and whether it can be painted")
    p.add_argument("--archive", help="default: $TVT_ARCHIVE")
    p.add_argument("--no-hash", action="store_true")
    p = sub.add_parser("flat", help="record a flat ground, and why, in tiles/manifest.json")
    p.add_argument("--tiles", required=True, help="the tiles folder (its manifest.json is updated)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--archive", help="take the reason from the exports there")
    g.add_argument("--reason", help="say why, in plain words")
    p.add_argument("--no-hash", action="store_true")
    args = ap.parse_args(argv)
    return {"spec": cmd_spec, "check-export": cmd_check_export, "status": cmd_status, "flat": cmd_flat}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
