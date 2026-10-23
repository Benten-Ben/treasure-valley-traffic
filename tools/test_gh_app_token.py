"""Tests for the agents' App token (tools/lib/gh_app_token.py) and the gh wrapper's routing (tools/agent-bin/gh).

Run: python3 -m unittest discover tools. Nothing here reaches GitHub or reads a real key.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import gh_app_token  # noqa: E402


class TokenLibraryTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.conf = os.path.join(self.dir, "gh-app.env")
        self.cache = os.path.join(self.dir, "cache.json")
        self.saved = (gh_app_token.CONF, gh_app_token.CACHE)
        gh_app_token.CONF, gh_app_token.CACHE = self.conf, self.cache

    def tearDown(self):
        gh_app_token.CONF, gh_app_token.CACHE = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def write_conf(self, text):
        with open(self.conf, "w") as f:
            f.write(text)

    def test_not_configured_exits_1(self):
        with self.assertRaises(SystemExit) as e:
            gh_app_token.load_conf()
        self.assertEqual(e.exception.code, 1)

    def test_a_missing_key_exits_2(self):
        self.write_conf("TVT_GH_APP_ID=1\nTVT_GH_APP_INSTALLATION_ID=2\n")
        with self.assertRaises(SystemExit) as e:
            gh_app_token.load_conf()
        self.assertEqual(e.exception.code, 2)

    def test_the_key_path_expands_home(self):
        self.write_conf('# comment\nTVT_GH_APP_ID=1\nTVT_GH_APP_INSTALLATION_ID=2\nTVT_GH_APP_KEY="~/k.pem"\n')
        conf = gh_app_token.load_conf()
        self.assertEqual(conf["TVT_GH_APP_KEY"], os.path.expanduser("~/k.pem"))

    def cache_with(self, repos, seconds_left):
        exp = datetime.fromtimestamp(time.time() + seconds_left, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(self.cache, "w") as f:
            json.dump({"token": "cached-tok", "expires_at": exp, "repos": repos}, f)

    def test_a_fresh_token_for_the_same_repos_is_reused(self):
        self.cache_with("treasure-valley-traffic", 3600)
        self.assertEqual(gh_app_token.cached({}), "cached-tok")

    def test_a_token_for_other_repos_is_not_reused(self):
        self.cache_with("thrilltown", 3600)
        self.assertEqual(gh_app_token.cached({}), "")

    def test_a_token_near_expiry_is_not_reused(self):
        self.cache_with("treasure-valley-traffic", gh_app_token.MARGIN_S - 60)
        self.assertEqual(gh_app_token.cached({}), "")


class WrapperRoutingTest(unittest.TestCase):
    """Which calls get the App's token: a fake real gh reports what it was given."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        tools = os.path.join(self.dir, "tools")
        os.makedirs(os.path.join(tools, "agent-bin"))
        shutil.copy(os.path.join(HERE, "agent-bin", "gh"), os.path.join(tools, "agent-bin", "gh"))
        self.token_script = os.path.join(tools, "gh-app-token")
        self.set_token_script("echo app-token")
        self.real = os.path.join(self.dir, "real")
        os.makedirs(self.real)
        self.make_exec(os.path.join(self.real, "gh"), '#!/usr/bin/env bash\necho "token=${GH_TOKEN:-none}"\n')
        self.make_exec(os.path.join(tools, "agent-bin", "gh"), None)
        self.path = os.pathsep.join([os.path.join(tools, "agent-bin"), self.real, "/usr/bin", "/bin"])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make_exec(self, path, text):
        if text is not None:
            with open(path, "w") as f:
                f.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def set_token_script(self, body):
        self.make_exec(self.token_script, f"#!/usr/bin/env bash\n{body}\n")

    def run_gh(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "TVT_GH_AS_USER")}
        e.update(PATH=self.path, **env)
        out = subprocess.run([os.path.join(self.dir, "tools", "agent-bin", "gh"), *args], capture_output=True, text=True, env=e)
        return out.stdout.strip()

    def test_ordinary_calls_use_the_app(self):
        self.assertEqual(self.run_gh("issue", "view", "9"), "token=app-token")
        self.assertEqual(self.run_gh("pr", "create", "--draft"), "token=app-token")

    def test_the_board_and_people_stay_on_the_login(self):
        for args in (("project", "list"), ("auth", "status"), ("pr", "review", "1", "--approve"),
                     ("issue", "edit", "9", "--add-assignee", "@me"),
                     ("api", "graphql", "-f", "query=query{user(login:\"x\"){projectV2(number:3){id}}}"),
                     ("api", "graphql", "-f", "query={repository{issue(number:1){projectItems(first:5){nodes{id}}}}}")):
            self.assertEqual(self.run_gh(*args), "token=none", args)

    def test_the_login_switch_and_a_given_token_win(self):
        self.assertEqual(self.run_gh("issue", "view", "9", TVT_GH_AS_USER="1"), "token=none")
        self.assertEqual(self.run_gh("issue", "view", "9", GH_TOKEN="mine"), "token=mine")

    def test_an_unconfigured_app_falls_back_to_the_login(self):
        self.set_token_script("exit 1")
        self.assertEqual(self.run_gh("issue", "view", "9"), "token=none")


if __name__ == "__main__":
    unittest.main()
