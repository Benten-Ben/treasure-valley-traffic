"""psycopg cancels a query in flight when a SystemExit (the SIGTERM that builds.Stopped raises) interrupts it.

ingest/builds.py relies on this for a build stopped at heavy's deadline (its docstring: "psycopg does that
on SystemExit"). psycopg 3.2 leaves the query running on the server; 3.3 cancels it, which is why
ingest/requirements.txt says psycopg>=3.3.

Needs TVT_TEST_DATABASE_URL (any test database). Run: python3 -m unittest discover -s ingest/tests -t .
"""

import os
import signal
import time
import unittest

DB_URL = os.environ.get("TVT_TEST_DATABASE_URL")


@unittest.skipUnless(DB_URL, "set TVT_TEST_DATABASE_URL to a test database")
@unittest.skipUnless(hasattr(signal, "SIGALRM"), "needs SIGALRM")
class SystemExitCancelsTest(unittest.TestCase):
    def test_a_query_in_flight_is_cancelled(self):
        import psycopg
        conn = psycopg.connect(DB_URL)
        self.addCleanup(conn.close)
        pid = conn.info.backend_pid

        def stop(*_):
            raise SystemExit(128 + signal.SIGTERM)

        old = signal.signal(signal.SIGALRM, stop)
        self.addCleanup(signal.signal, signal.SIGALRM, old)
        signal.alarm(1)
        try:
            with self.assertRaises(SystemExit):
                conn.execute("select pg_sleep(20)")
        finally:
            signal.alarm(0)
        time.sleep(1)
        with psycopg.connect(DB_URL) as other:
            state = other.execute("select state from pg_stat_activity where pid = %s", (pid,)).fetchone()
        self.assertNotEqual(state and state[0], "active",
                            f"the query is still running on the server (psycopg {psycopg.__version__}; needs 3.3)")


if __name__ == "__main__":
    unittest.main()
