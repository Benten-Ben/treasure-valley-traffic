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
# built at run time, so this file passes the repository scan itself (as tools/test_check_public.py does)
ADDR = "100." + "64.1.2"
TS = ".ts" + ".net"

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

    def board(self, *args, env=None, script=BOARD, cwd=None, patterns=True):
        env = {**{
            "PATH": self.bin + os.pathsep + "/usr/bin:/bin",
            "HOME": self.dir,
            "TMPDIR": self.tmp,
            "FAKE_GH_LOG": self.log,
            "BOARD_OWNER": "o",
            "BOARD_NUMBER": "1",
            "BOARD_REPO": "o/r",
        }, **({"TVT_PRIVATE_PATTERNS": self.patterns} if patterns else {}), **(env or {})}
        return subprocess.run(["/bin/bash", script, *args], capture_output=True, text=True, env=env, cwd=cwd or self.cwd, timeout=60)

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
        self.assertRefused(self.board("new", f"Check the box at {ADDR}"))

    def test_a_title_with_a_tailnet_name_is_refused(self):
        self.assertRefused(self.board("new", "Look at machine.example" + TS))

    def test_a_title_that_hits_the_private_pattern_list_is_refused(self):
        self.assertRefused(self.board("new", "Fix the secret-host-name setup"))

    def test_a_missing_pattern_list_refuses_instead_of_dropping_the_private_half(self):
        out = self.board("new", "Fix the secret-host-name setup", env={"TVT_PRIVATE_PATTERNS": os.path.join(self.dir, "nope.txt")})
        self.assertEqual(out.returncode, 2, out.stderr)
        self.assertIn("names no file", out.stderr)
        self.assertEqual(self.calls(), [], "gh must not be called at all")

    def test_none_is_the_explicit_opt_out_and_runs_the_mechanical_checks_only(self):
        ok = self.board("new", "Document the quoting rules", env={"TVT_PRIVATE_PATTERNS": "none"})
        self.assertEqual(ok.returncode, 0, ok.stderr)
        bad = self.board("new", f"Check the box at {ADDR}", env={"TVT_PRIVATE_PATTERNS": "none"})
        self.assertEqual(bad.returncode, 2, bad.stderr)

    # --- the default lookup: no TVT_PRIVATE_PATTERNS, so the list comes from the script's own checkout ---

    def checkout(self, name, with_list):
        """A git checkout holding copies of tools/board and tools/check_public.py (and the list, when with_list)."""
        top = os.path.join(self.dir, name)
        os.makedirs(os.path.join(top, "tools"))
        for f in ("board", "check_public.py"):
            shutil.copy(os.path.join(HERE, f), os.path.join(top, "tools", f))
        if with_list:
            os.makedirs(os.path.join(top, "data", "dev"))
            shutil.copy(self.patterns, os.path.join(top, "data", "dev", "private-patterns.txt"))
        git = ["git", "-C", top, "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "tools"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "x"], check=True)
        return top

    def worktree(self, main):
        wt = os.path.join(self.dir, "wt")
        subprocess.run(["git", "-C", main, "worktree", "add", "-q", "-b", "side", wt], check=True)
        return wt

    def default_board(self, top, *args, cwd=None, env=None):
        return self.board(*args, script=os.path.join(top, "tools", "board"), cwd=cwd, patterns=False, env=env)

    def test_the_default_list_in_the_scripts_checkout_applies_from_any_cwd(self):
        top = self.checkout("main", with_list=True)
        other = self.checkout("other", with_list=False)  # a different checkout as the cwd
        for cwd in (self.cwd, other, top):
            out = self.default_board(top, "new", "Fix the secret-host-name setup", cwd=cwd)
            self.assertEqual(out.returncode, 2, (cwd, out.stderr))
            self.assertIn("refusing to post", out.stderr)
            self.assertEqual(self.calls(), [])

    def test_a_linked_worktree_uses_the_main_checkouts_list_from_any_cwd(self):
        main = self.checkout("main", with_list=True)
        wt = self.worktree(main)
        self.assertFalse(os.path.exists(os.path.join(wt, "data")))
        for cwd in (self.cwd, main, wt):
            out = self.default_board(wt, "new", "Fix the secret-host-name setup", cwd=cwd)
            self.assertEqual(out.returncode, 2, (cwd, out.stderr))
            self.assertIn("refusing to post", out.stderr)
            self.assertEqual(self.calls(), [])
        ok = self.default_board(wt, "new", "Document the quoting rules", cwd=self.cwd)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_no_list_anywhere_refuses_instead_of_posting_on_the_mechanical_checks_alone(self):
        top = self.checkout("main", with_list=False)
        wt = self.worktree(top)
        for script_top in (top, wt):
            for cwd in (self.cwd, top):
                out = self.default_board(script_top, "new", "Document the quoting rules", cwd=cwd)
                self.assertEqual(out.returncode, 2, out.stderr)
                self.assertIn("no private pattern list found", out.stderr)
                self.assertEqual(self.calls(), [], "gh must not be called at all")

    def test_none_skips_the_default_list_too(self):
        top = self.checkout("main", with_list=True)
        out = self.default_board(top, "new", "Fix the secret-host-name setup", env={"TVT_PRIVATE_PATTERNS": "none"})
        self.assertEqual(out.returncode, 0, out.stderr)  # the list is not applied
        bad = self.default_board(top, "new", f"Check the box at {ADDR}", env={"TVT_PRIVATE_PATTERNS": "none"})
        self.assertEqual(bad.returncode, 2, bad.stderr)  # the mechanical checks still are

    def test_an_empty_explicit_list_refuses(self):
        for text in ("", "# only a comment\n\n   \n", "\ufeff# only a comment, saved with a BOM\n\n"):
            empty = os.path.join(self.dir, "empty.txt")
            with open(empty, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            out = self.board("new", "Document the quoting rules", env={"TVT_PRIVATE_PATTERNS": empty})
            self.assertEqual(out.returncode, 2, out.stderr)
            self.assertIn("pattern list is empty", out.stderr)
            self.assertIn(empty, out.stderr)  # says where it looked
            self.assertEqual(self.calls(), [], "gh must not be called at all")
            self.assertEqual(os.listdir(self.tmp), [], "no temporary body left behind")

    def test_an_empty_default_list_refuses_in_a_checkout_and_in_a_linked_worktree(self):
        top = self.checkout("main", with_list=True)
        wt = self.worktree(top)
        for body in ("# nothing yet\n\n", "\ufeff# nothing yet\n\n"):  # the second saved with a BOM
            with open(os.path.join(top, "data", "dev", "private-patterns.txt"), "w", encoding="utf-8", newline="") as f:
                f.write(body)
            for script_top in (top, wt):
                out = self.default_board(script_top, "new", "Document the quoting rules")
                self.assertEqual(out.returncode, 2, out.stderr)
                self.assertIn("pattern list is empty", out.stderr)
                self.assertIn("private-patterns.txt", out.stderr)
                self.assertEqual(self.calls(), [], "gh must not be called at all")

    def test_none_still_opts_out_when_the_default_list_is_empty(self):
        top = self.checkout("main", with_list=True)
        with open(os.path.join(top, "data", "dev", "private-patterns.txt"), "w") as f:
            f.write("# nothing yet\n")
        out = self.default_board(top, "new", "Document the quoting rules", env={"TVT_PRIVATE_PATTERNS": "none"})
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_a_label_is_checked_too(self):
        self.assertRefused(self.board("new", "Fine title", "area:docs", "secret-host-name"))

    def test_a_dry_run_still_runs_the_check(self):
        self.assertRefused(self.board("new", f"Check the box at {ADDR}", "--dry-run"))

    def test_a_clean_dry_run_prints_the_write_and_calls_nothing_that_posts(self):
        out = self.board("new", "Document the quoting rules", "--dry-run")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("DRY-RUN: gh issue create", out.stderr)
        self.assertFalse([c for c in self.calls() if c.startswith("issue create")])

    def test_a_template_body_that_fails_is_refused(self):
        tpl = os.path.join(self.dir, "tpl.md")
        with open(tpl, "w") as f:
            f.write(f"**Goal:** reach {ADDR}\n")
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
