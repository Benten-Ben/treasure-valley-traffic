"""Tests for the board status rule (board_status_sync.wanted). Run: python3 -m unittest discover tools"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from board_status_sync import wanted  # noqa: E402


class StatusRuleTest(unittest.TestCase):
    def test_closed_is_done(self):
        self.assertEqual(wanted("CLOSED", "In review", 0, 0), "Done")
        self.assertEqual(wanted("CLOSED", "Ready", 2, 0), "Done")

    def test_work_in_flight_is_left_alone(self):
        self.assertEqual(wanted("OPEN", "In progress", 1, 0), "In progress")
        self.assertEqual(wanted("OPEN", "In review", 0, 0), "In review")

    def test_blocked_or_tracking_is_backlog(self):
        self.assertEqual(wanted("OPEN", "Ready", 1, 0), "Backlog")
        self.assertEqual(wanted("OPEN", None, 0, 3), "Backlog")

    def test_unblocked_and_not_started_is_ready(self):
        self.assertEqual(wanted("OPEN", "Backlog", 0, 0), "Ready")
        self.assertEqual(wanted("OPEN", None, 0, 0), "Ready")


if __name__ == "__main__":
    unittest.main()
