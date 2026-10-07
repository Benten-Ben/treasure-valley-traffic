#!/usr/bin/env python3
"""Apply db/migrations/NNNN_*.sql, then each plugin's migrations, in order, each in its own transaction.

Core's migrations (db/migrations/) come first, by name. Then each plugin's
plugins/<name>/migrations/NNNN_*.sql (and those of private plugins on
TVT_PLUGIN_PATH), plugin by plugin in dependency order (ingest/manifest.py),
by name within a plugin. Plugin migrations are recorded as
'<plugin>/<file>', core's by file name as before.

Applied files are recorded in ops.schema_migration with a checksum. A file
that changed after it was applied stops the run: write a new migration
instead of editing an old one.

Usage:
  DATABASE_URL=postgres://user:pass@host/db python3 db/migrate.py
  python3 db/migrate.py --status
"""

import argparse
import glob
import hashlib
import os
import sys

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
PATTERN = "[0-9][0-9][0-9][0-9]_*.sql"


def plugin_order():
    """The installed plugins in dependency order (this repository's and TVT_PLUGIN_PATH's)."""
    root = os.path.dirname(HERE)
    if root not in sys.path:
        sys.path.insert(0, root)
    from ingest import manifest
    return manifest.plugin_order(manifest.find())


def migrations(core_dir=os.path.join(HERE, "migrations"), plugins=None):
    """[(name, path)] in the order they apply: core's, then each plugin's as '<plugin>/<file>'."""
    out = [(os.path.basename(p), p) for p in sorted(glob.glob(os.path.join(core_dir, PATTERN)))]
    for plugin in plugin_order() if plugins is None else plugins:
        for p in sorted(glob.glob(os.path.join(plugin.folder, "migrations", PATTERN))):
            out.append((f"{plugin.name}/{os.path.basename(p)}", p))
    return out


def apply(conn, files, status=False, out=print):
    """Apply what's pending of files ([(name, path)]), each in its own transaction (a savepoint when
    the connection is already inside one). With status, only report."""
    conn.execute("create schema if not exists ops")
    conn.execute("""create table if not exists ops.schema_migration (
                      name text primary key, checksum text not null,
                      applied_at timestamptz not null default now())""")
    applied = dict(conn.execute("select name, checksum from ops.schema_migration").fetchall())
    for name, path in files:
        with open(path, encoding="utf-8") as f:
            sql = f.read()
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        if name in applied:
            if applied[name] != checksum:
                sys.exit(f"{name} changed after it was applied; add a new migration instead")
            if status:
                out(f"applied  {name}")
            continue
        if status:
            out(f"pending  {name}")
            continue
        with conn.transaction():
            conn.execute(sql)
            conn.execute("insert into ops.schema_migration (name, checksum) values (%s, %s)", (name, checksum))
        out(f"applied  {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--status", action="store_true", help="list migrations and whether they're applied")
    args = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("set DATABASE_URL")

    files = migrations()
    with psycopg.connect(url, autocommit=True) as conn:
        apply(conn, files, status=args.status)


if __name__ == "__main__":
    main()
