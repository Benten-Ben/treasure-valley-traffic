"""Tests for the water plugin's pollers.

Offline, except the DatabaseTest classes, which run only against a scratch
database named by TVT_TEST_DATABASE_URL (core's migrations applied: raw.record
and evt.event), inside a transaction that is rolled back.

Fixtures: the NWPS and NRCS ones are trimmed real responses (US government
works, Oct 7, 2026); the City of Boise (E. coli, river hazards) and Drought
Monitor ones are synthetic, with the real field names and made-up values.

Run: python3 -m unittest discover -s plugins/water/tests -t .
"""

import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


def fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    """Answers a store's lookups from canned rows: {a piece of the SQL: rows}. Records what ran."""

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.executed = []

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        for piece, rows in self.answers.items():
            if piece in sql:
                return _Result(rows)
        return _Result([])

    def commit(self):
        pass

    def rollback(self):
        pass


def db_conn(test, *tables):
    """A connection to the scratch database for a DatabaseTest, or skip if it lacks a table."""
    import psycopg
    conn = psycopg.connect(DB_URL)
    for table in tables:
        if not conn.execute("select to_regclass(%s) is not null", (table,)).fetchone()[0]:
            conn.close()
            test.skipTest(f"{table} is missing: apply core's migrations")
    return conn


def fake_fetch(conn, source, at):
    """An ops.fetch row for the store steps to point at (rolled back with the test)."""
    return conn.execute("insert into ops.fetch (source, started_at, ok) values (%s, %s, true) returning id",
                        (source, at)).fetchone()[0]
