#!/usr/bin/env python3
"""Apply db/migrations/NNNN_*.sql in order, each in its own transaction.

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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--status", action="store_true", help="list migrations and whether they're applied")
    args = ap.parse_args()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("set DATABASE_URL")

    files = sorted(glob.glob(os.path.join(HERE, "migrations", "[0-9][0-9][0-9][0-9]_*.sql")))
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("create schema if not exists ops")
        conn.execute("""create table if not exists ops.schema_migration (
                          name text primary key, checksum text not null,
                          applied_at timestamptz not null default now())""")
        applied = dict(conn.execute("select name, checksum from ops.schema_migration").fetchall())
        for path in files:
            name = os.path.basename(path)
            sql = open(path, encoding="utf-8").read()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            if name in applied:
                if applied[name] != checksum:
                    sys.exit(f"{name} changed after it was applied; add a new migration instead")
                if args.status:
                    print(f"applied  {name}")
                continue
            if args.status:
                print(f"pending  {name}")
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("insert into ops.schema_migration (name, checksum) values (%s, %s)", (name, checksum))
            print(f"applied  {name}")


if __name__ == "__main__":
    main()
