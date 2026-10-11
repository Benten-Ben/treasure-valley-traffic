"""Versions of the toggled layers' vector tiles (core.layer_version, migration 0020; plan C4).

Toggled layers (soils, crop fields, trails, burn scars, ...) are cut by PostGIS on request at
/api/<plugin>/tiles/<layer>/{z}/{x}/{y}?v= (app/src/lib/server/mvt.ts). The app reports each
layer's newest version in /api/meta as versions.layers['<plugin>.<layer>'] and caches its tiles
per version, so a new row here is what makes viewers fetch new tiles.

A build that changes what a layer's tiles show calls record() **in the same transaction as its
data**, so the version and the data appear together. record() doesn't commit. A version names
content: never reuse one for different data (the default is a fresh one per call).

By hand, after a change made outside a build, and to list the current versions:

  python3 -m ingest.layer_version --list
  python3 -m ingest.layer_version soils.units --licence 'public domain' --republish yes
"""

import argparse
import re
import secrets
from datetime import datetime, timezone

NAME = r"[a-z][a-z0-9_]{0,39}"
LAYER = re.compile(rf"{NAME}\.{NAME}")          # '<plugin>.<layer>', as in the tile route
VERSION = re.compile(r"[A-Za-z0-9._-]{1,64}")    # sent as ?v=, so URL-safe
REPUBLISH = ("yes", "aggregates", "internal", "no")   # the plugin manifests' values (docs/15 §15.2)


def new_version(now=None):
    """A fresh version: the UTC time and a random suffix, e.g. '20261011T0412Z-3fa9c1'."""
    now = now or datetime.now(timezone.utc)
    return f"{now.astimezone(timezone.utc):%Y%m%dT%H%MZ}-{secrets.token_hex(3)}"


def check(layer, version, licence, republish, features=None):
    """Raise ValueError for anything core.layer_version would refuse."""
    if not isinstance(layer, str) or not LAYER.fullmatch(layer):
        raise ValueError(f"layer must be '<plugin>.<layer>' in lower-case letters, digits and _: {layer!r}")
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError(f"version must be 1-64 letters, digits, '.', '_' or '-': {version!r}")
    if not isinstance(licence, str) or not licence.strip():
        raise ValueError("licence is required (the strictest of the layer's inputs)")
    if republish not in REPUBLISH:
        raise ValueError(f"republish must be one of {', '.join(REPUBLISH)}: {republish!r}")
    if features is not None and (not isinstance(features, int) or features < 0):
        raise ValueError(f"features must be a count: {features!r}")


def record(conn, layer, *, licence, republish, version=None, build=None, features=None, note=None):
    """Add a version row for layer ('<plugin>.<layer>') and return the version. Doesn't commit."""
    version = version or new_version()
    check(layer, version, licence, republish, features)
    conn.execute(
        """insert into core.layer_version (layer, version, build, features, licence, republish, note)
           values (%s, %s, %s, %s, %s, %s, %s)""",
        (layer, version, build, features, licence, republish, note))
    return version


def current(conn):
    """{layer: (version, built_at)} for every layer with a version."""
    rows = conn.execute("select layer, version, built_at from core.layer_version_current order by layer").fetchall()
    return {layer: (version, built_at) for layer, version, built_at in rows}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest.layer_version", description=__doc__.split("\n")[0])
    ap.add_argument("layer", nargs="?", help="'<plugin>.<layer>' to give a new version")
    ap.add_argument("--list", action="store_true", help="list each layer's current version")
    ap.add_argument("--licence", help="licence class, the strictest of the layer's inputs")
    ap.add_argument("--republish", choices=REPUBLISH)
    ap.add_argument("--version", help="the version (default: a fresh one)")
    ap.add_argument("--note", help="why, for the record")
    args = ap.parse_args(argv)
    if not args.list and not args.layer:
        ap.error("give a layer, or --list")
    if args.layer and (not args.licence or not args.republish):
        ap.error("a new version needs --licence and --republish")

    from . import db
    with db.connect() as conn:
        if args.layer:
            v = record(conn, args.layer, licence=args.licence, republish=args.republish, version=args.version,
                       build="by hand (python3 -m ingest.layer_version)", note=args.note)
            conn.commit()
            print(f"{args.layer}: {v}")
        if args.list:
            for layer, (version, built_at) in current(conn).items():
                print(f"{layer:40} {version:30} {built_at:%Y-%m-%d %H:%M %Z}")


if __name__ == "__main__":
    main()
