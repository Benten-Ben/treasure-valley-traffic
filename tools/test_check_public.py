"""Tests for check_public.py: passes on this repository, fails on planted fixtures.

Run: python3 -m unittest discover tools

The planted names and addresses are assembled at run time, so this file
itself stays clean for the check.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import check_public  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TS = "." + "ts" + ".net"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64 + b"\xff\xd9"


def run_git(root, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.org")
    subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, env=env)


def opts(**kw):
    return argparse.Namespace(staged=kw.get("staged", False), since=kw.get("since"))


class CheckPublicTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        run_git(self.root, "init", "-q")
        self.write("README.md", "Reach the server at <machine>.<tailnet>" + TS + " or *" + TS + ".\n"
                   "The tailnet range is 100.64.0.0/10; the LAN is 10.0.0.0/8 and 192.168.1.1.\n"
                   "Version 1.100.64.1.2 isn't an address. 100.63.255.255 is outside the range.\n")
        self.write("app/src/lib/assets/favicon.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.write("deploy/.env.example", "POSTGRES_PASSWORD=change-me\n")
        self.add_commit()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, path, content):
        full = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(content if isinstance(content, bytes) else content.encode())

    def add_commit(self):
        run_git(self.root, "add", "-A", "-f")
        run_git(self.root, "commit", "-q", "-m", "x", "--allow-empty")

    def problems(self, **kw):
        return check_public.check(self.root, opts(**kw))[1]

    def plant(self, path, content):
        self.write(path, content)
        run_git(self.root, "add", "-f", path)
        found = self.problems()
        self.assertTrue(found, f"{path} should have been caught")
        return " ".join(found)

    def test_clean_fixture_passes(self):
        self.assertEqual(self.problems(), [])

    def test_this_repository_passes(self):
        n, found = check_public.check(REPO, opts())
        self.assertGreater(n, 50)
        self.assertEqual(found, [])

    def test_images_outside_the_allowlist(self):
        self.assertIn("image", self.plant("docs/frame.jpg", JPEG))

    def test_images_by_content_whatever_the_name(self):
        self.assertIn("JPEG", self.plant("notes/frame.txt", JPEG))

    def test_tailscale_names(self):
        self.assertIn("Tailscale name", self.plant("docs/x.md", "ssh owner@tvt.tail1234" + TS + "\n"))

    def test_cgnat_addresses(self):
        found = self.plant("deploy/notes.md", "server: " + ".".join(["100", "101", "7", "12"]) + "\n")
        self.assertIn("CGNAT", found)
        self.assertNotIn("100.1", found)  # the match is masked

    def test_tailscale_ipv6_and_keys(self):
        self.assertIn("IPv6", self.plant("a.md", "fd7a" + ":115c:a1e0::1\n"))
        self.assertIn("auth key", self.plant("b.md", "tskey" + "-auth-kAbCdEf123456\n"))

    def test_env_files(self):
        self.assertIn(".env", self.plant("deploy/.env", "POSTGRES_PASSWORD=x\n"))

    def test_data_files(self):
        self.assertIn("data/", self.plant("data/achd/counts.csv", "a,b\n1,2\n"))

    def test_staged_mode_sees_only_staged_changes(self):
        self.assertEqual(self.problems(staged=True), [])
        self.write("docs/frame.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        self.assertEqual(self.problems(staged=True), [])  # not staged yet
        run_git(self.root, "add", "docs/frame.png")
        self.assertTrue(self.problems(staged=True))

    def test_since_mode_sees_the_branch_diff(self):
        run_git(self.root, "tag", "base")
        self.assertEqual(self.problems(since="base"), [])
        self.write("data/x.json", "{}")
        self.add_commit()
        self.assertTrue(self.problems(since="base"))

    def test_main_exit_status(self):
        self.assertEqual(check_public.main(["--root", self.root]), 0)
        self.write("data/x.csv", "1")
        run_git(self.root, "add", "-f", "data/x.csv")
        self.assertEqual(check_public.main(["--root", self.root]), 1)


if __name__ == "__main__":
    unittest.main()
