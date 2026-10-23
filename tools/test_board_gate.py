"""Tests that tools/board never posts text that fails the public check (tools/check_public.py --text).

A fake gh records every call it gets; nothing here reaches GitHub. Run: python3 -m unittest discover tools
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "board")

FAKE_GH = """#!/bin/bash
echo "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "issue create") echo "https://github.com/o/r/issues/77" ;;
  "project field-list") echo "F1 O1" ;;
  "project view") echo "P1" ;;
  "project item-add") echo "ITEM1" ;;
  "api graphql") echo "I1" ;;
esac
exit 0
"""


class BoardPublicGateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.bin = os.path.join(self.dir, "bin")
        os.mkdir(self.bin)
        gh = os.path.join(self.bin, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.log = os.path.join(self.dir, "gh.log")
        open(self.log, "w").close()
        self.patterns = os.path.join(self.dir, "patterns.txt")
        with open(self.patterns, "w") as f:
            f.write("# a stand-in for the private list\nsecret-host-name\n")
        self.cwd = os.path.join(self.dir, "work")  # not a git checkout: board reads no .board.env here
        os.mkdir(self.cwd)
        self.tmp = os.path.join(self.dir, "tmp")
        os.mkdir(self.tmp)

    def board(self, *args, env=None):
        env = {**{
            "PATH": self.bin + os.pathsep + "/usr/bin:/bin",
            "HOME": self.dir,
            "TMPDIR": self.tmp,
            "FAKE_GH_LOG": self.log,
            "BOARD_OWNER": "o",
            "BOARD_NUMBER": "1",
            "BOARD_REPO": "o/r",
            "TVT_PRIVATE_PATTERNS": self.patterns,
        }, **(env or {})}
        return subprocess.run(["/bin/bash", BOARD, *args], capture_output=True, text=True, env=env, cwd=self.cwd, timeout=60)

    def calls(self):
        with open(self.log) as f:
            return f.read().splitlines()

    def assertRefused(self, out):
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("refusing to post", out.stderr)
        self.assertIn("check_public:", out.stderr)  # the check's own report is shown
        self.assertEqual(self.calls(), [], "gh must not be called at all")
        self.assertEqual(os.listdir(self.tmp), [], "no temporary body left behind")

    def test_a_clean_title_is_posted(self):
        out = self.board("new", "Document the quoting rules", "area:docs")
        self.assertEqual(out.returncode, 0, out.stderr)
        calls = self.calls()
        self.assertTrue(any(c.startswith("issue create") for c in calls), calls)
        self.assertTrue(any(c.startswith("project item-edit") for c in calls), calls)

    def test_a_title_with_a_tailnet_address_is_refused(self):
        self.assertRefused(self.board("new", "Check the box at 100.64.1.2"))

    def test_a_title_with_a_tailnet_name_is_refused(self):
        self.assertRefused(self.board("new", "Look at machine.example.ts.net"))

    def test_a_title_that_hits_the_private_pattern_list_is_refused(self):
        self.assertRefused(self.board("new", "Fix the secret-host-name setup"))

    def test_a_label_is_checked_too(self):
        self.assertRefused(self.board("new", "Fine title", "area:docs", "secret-host-name"))

    def test_a_dry_run_still_runs_the_check(self):
        self.assertRefused(self.board("new", "Check the box at 100.64.1.2", "--dry-run"))

    def test_a_clean_dry_run_prints_the_write_and_calls_nothing_that_posts(self):
        out = self.board("new", "Document the quoting rules", "--dry-run")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("DRY-RUN: gh issue create", out.stderr)
        self.assertFalse([c for c in self.calls() if c.startswith("issue create")])

    def test_a_template_body_that_fails_is_refused(self):
        tpl = os.path.join(self.dir, "tpl.md")
        with open(tpl, "w") as f:
            f.write("**Goal:** reach 100.64.1.2\n")
        self.assertRefused(self.board("new", "Fine title", env={"BOARD_TEMPLATE": tpl}))

    def test_only_new_posts_text_and_it_gates_first(self):
        """No other command sends free text; a new one that does must call public_gate (see the header of tools/board)."""
        with open(BOARD) as f:
            lines = [ln for ln in f.read().splitlines() if not ln.lstrip().startswith("#")]
        creates = [n for n, ln in enumerate(lines) if "gh issue create" in ln]
        gate = [n for n, ln in enumerate(lines) if "public_gate " in ln and "()" not in ln]
        self.assertTrue(gate and creates and all(gate[0] < n for n in creates))
        for flag in ("--body ", "--body=", "issue comment", "pr comment", "pr create", "issue edit --title"):
            self.assertEqual([ln for ln in lines if flag in ln], [], flag)


if __name__ == "__main__":
    unittest.main()
