"""Tests for the agents' App token (tools/lib/gh_app_token.py) and the gh wrapper's routing (tools/agent-bin/gh).

Run: python3 -m unittest discover tools. Nothing here reaches GitHub or reads a real key.
"""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
sys.path.insert(0, HERE)
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

    # --- malformed caches, the best-effort cache write, exit codes ---
    def write_ready_conf(self):
        self.write_conf("TVT_GH_APP_ID=1\nTVT_GH_APP_INSTALLATION_ID=2\nTVT_GH_APP_KEY=/nowhere.pem\n")

    def run_lib(self):
        out, err = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                gh_app_token.main()
            except SystemExit as e:
                code = e.code
        return code, out.getvalue().strip(), err.getvalue().strip()

    def stub_mint(self):
        return mock.patch.object(gh_app_token, "mint", lambda conf: {"token": "new-tok", "expires_at": "2099-01-01T00:00:00Z"})

    def test_a_malformed_cache_is_replaced_by_a_new_token(self):
        self.write_ready_conf()
        good_exp = "2099-01-01T00:00:00Z"
        for bad in ('[]', 'null', '{"repos": "treasure-valley-traffic", "expires_at": 1, "token": "t"}',
                    '{"repos": "treasure-valley-traffic", "expires_at": "%s", "token": 5}' % good_exp,
                    '{"repos": "treasure-valley-traffic", "expires_at": "%s", "token": ""}' % good_exp, 'not json'):
            with open(self.cache, "w") as f:
                f.write(bad)
            with self.stub_mint():
                code, out, err = self.run_lib()
            self.assertEqual((code, out, err), (0, "new-tok", ""), bad)
            with open(self.cache) as f:
                self.assertEqual(json.load(f)["token"], "new-tok", bad)

    def test_a_cache_that_cannot_be_written_still_prints_the_token(self):
        self.write_ready_conf()
        # the cache's directory can't be made: its parent is a regular file
        gh_app_token.CACHE = os.path.join(self.conf, "sub", "cache.json")
        with self.stub_mint():
            self.assertEqual(self.run_lib(), (0, "new-tok", ""))
        # the cache can't be replaced: a directory sits where it goes; the temp file must not be left behind
        os.makedirs(os.path.join(self.dir, "c2", "cache.json"))
        gh_app_token.CACHE = os.path.join(self.dir, "c2", "cache.json")
        with self.stub_mint():
            self.assertEqual(self.run_lib(), (0, "new-tok", ""))
        self.assertEqual(os.listdir(os.path.join(self.dir, "c2")), ["cache.json"])

    def test_an_unexpected_error_is_one_line_and_exit_2_without_the_token(self):
        self.write_ready_conf()

        def boom(conf):
            raise RuntimeError("it broke")
        with mock.patch.object(gh_app_token, "mint", boom):
            self.assertEqual(self.run_lib(), (2, "", "gh-app-token: RuntimeError: it broke"))

    def test_not_configured_is_exit_1_with_no_output(self):
        self.assertEqual(self.run_lib(), (1, "", ""))


CONCURRENT_DRIVER = r"""
import os, sys, time
sys.path.insert(0, sys.argv[1])
import gh_app_token as g
d = sys.argv[2]
g.CONF, g.CACHE = os.path.join(d, "gh-app.env"), os.path.join(d, "cache", "token.json")
_replace = os.replace


def _record(src, dst):
    with open(os.path.join(d, "tmp-used." + str(os.getpid())), "w") as f:
        f.write(src)
    return _replace(src, dst)


os.replace = _record
g.mint = lambda conf: (time.sleep(0.3), {"token": "stub-token", "expires_at": "2099-01-01T00:00:00Z"})[1]
open(os.path.join(d, "ready." + str(os.getpid())), "w").close()
while not os.path.exists(os.path.join(d, "go")):
    time.sleep(0.005)
g.main()
"""


class ConcurrentMintTest(unittest.TestCase):
    def test_simultaneous_mints_all_print_the_token_and_leave_one_valid_cache(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, "gh-app.env"), "w") as f:
            f.write("TVT_GH_APP_ID=1\nTVT_GH_APP_INSTALLATION_ID=2\nTVT_GH_APP_KEY=/nowhere.pem\n")
        driver = os.path.join(d, "driver.py")
        with open(driver, "w") as f:
            f.write(CONCURRENT_DRIVER)
        cache_dir, go = os.path.join(d, "cache"), os.path.join(d, "go")
        for rnd in range(10):
            shutil.rmtree(cache_dir, ignore_errors=True)
            for name in os.listdir(d):
                if name.startswith(("tmp-used.", "ready.")):
                    os.unlink(os.path.join(d, name))
            if os.path.exists(go):
                os.unlink(go)
            procs = [subprocess.Popen([sys.executable, "-I", driver, os.path.join(HERE, "lib"), d], stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(6)]
            deadline = time.time() + 30
            while sum(n.startswith("ready.") for n in os.listdir(d)) < 6 and time.time() < deadline:
                time.sleep(0.01)
            open(go, "w").close()
            for p in procs:
                out, err = p.communicate(timeout=30)
                self.assertEqual((p.returncode, out.strip(), err.strip()), (0, "stub-token", ""), f"round {rnd}")
            self.assertEqual(os.listdir(cache_dir), ["token.json"], f"round {rnd}")
            used = set()
            for name in os.listdir(d):
                if name.startswith("tmp-used."):
                    with open(os.path.join(d, name)) as f:
                        used.add(f.read())
            self.assertEqual(len(used), 6, f"every mint writes its own temp file (round {rnd})")
            path = os.path.join(cache_dir, "token.json")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path) as f:
                self.assertEqual(json.load(f)["token"], "stub-token")


class WrapperRoutingTest(unittest.TestCase):
    """Which calls get the App's token: a fake real gh reports what it was given."""

    ENV_OFF = ("GH_TOKEN", "TVT_GH_AS_USER", "TVT_GH_WRAPPED", "TVT_GH_APP_TOKEN")

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        tools = os.path.join(self.dir, "tools")
        os.makedirs(os.path.join(tools, "agent-bin"))
        shutil.copy(os.path.join(HERE, "agent-bin", "gh"), os.path.join(tools, "agent-bin", "gh"))
        self.wrapper = os.path.join(tools, "agent-bin", "gh")
        self.token_script = os.path.join(tools, "gh-app-token")
        self.set_token_script("echo app-token")
        self.real = os.path.join(self.dir, "real")
        os.makedirs(self.real)
        self.make_exec(os.path.join(self.real, "gh"),
                       '#!/usr/bin/env bash\necho "token=${GH_TOKEN:-none}"\n'
                       '[ -z "${FAKE_GH_SHOW:-}" ] || echo "marker=${TVT_GH_APP_TOKEN:-} wrapped=${TVT_GH_WRAPPED:-}"\n')
        self.make_exec(self.wrapper, None)
        # the bash that runs the scripts (the test run's first on PATH: macOS's 3.2 or a newer one), alone in its
        # directory, so no gh of the machine's is ever found
        bash_dir = os.path.join(self.dir, "bash-only")
        os.makedirs(bash_dir)
        os.symlink(shutil.which("bash") or "/bin/bash", os.path.join(bash_dir, "bash"))
        self.tail = [bash_dir, "/usr/bin", "/bin"]
        self.path = os.pathsep.join([os.path.join(tools, "agent-bin"), self.real] + self.tail)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def make_exec(self, path, text):
        if text is not None:
            with open(path, "w") as f:
                f.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def set_token_script(self, body):
        self.make_exec(self.token_script, f"#!/usr/bin/env bash\n{body}\n")

    def run_full(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in self.ENV_OFF}
        e.update(PATH=self.path, **env)
        return subprocess.run([self.wrapper, *args], capture_output=True, text=True, env=e, timeout=10)

    def run_gh(self, *args, **env):
        return self.run_full(*args, **env).stdout.strip()

    def test_ordinary_calls_use_the_app(self):
        self.assertEqual(self.run_gh("issue", "view", "9"), "token=app-token")
        self.assertEqual(self.run_gh("pr", "create", "--draft"), "token=app-token")

    def test_the_wrapper_marks_its_token_and_the_nested_guard(self):
        self.assertEqual(self.run_gh("issue", "view", "9", FAKE_GH_SHOW="1"), "token=app-token\nmarker=1 wrapped=1")

    def test_the_board_and_people_stay_on_the_login(self):
        missing = os.path.join(self.dir, "no-such-query.graphql")
        with open(os.path.join(self.dir, "q.graphql"), "w") as f:
            f.write("query { repository(owner:\"o\", name:\"r\") { projectsV2(first:1) { nodes { id } } } }")
        queryfile = os.path.join(self.dir, "q.graphql")
        for args in (("project", "list"), ("auth", "status"), ("pr", "review", "1", "--approve"),
                     ("issue", "edit", "9", "--add-assignee", "@me"),
                     ("api", "graphql", "-f", "query=query{user(login:\"x\"){projectV2(number:3){id}}}"),
                     ("api", "graphql", "-f", "query={repository{issue(number:1){projectItems(first:5){nodes{id}}}}}"),
                     # gh's project flags
                     ("issue", "create", "--project", "X"), ("issue", "create", "--project=X"),
                     ("issue", "create", "-p", "X"), ("pr", "edit", "3", "-p", "X"),
                     ("issue", "edit", "9", "--add-project", "X"), ("issue", "edit", "9", "--remove-project=X"),
                     # the user's own identity
                     ("api", "user"), ("api", "/user"), ("api", "graphql", "-f", "query=query{viewer{login}}"),
                     ("api", "graphql", "-F", "query=@" + queryfile), ("api", "graphql", "--field=query=@" + queryfile),
                     ("api", "graphql", "-F", "query=@" + missing),
                     ("issue", "list", "--assignee", "@me"), ("issue", "list", "--assignee=@me"),
                     ("issue", "list", "--assignee", "bob,@me"), ("issue", "list", "--assignee", "@me,bob"),
                     ("issue", "list", "--search", "is:open assignee:@me"),
                     ("issue", "list", "--search", "assignee:@me,x")):
            self.assertEqual(self.run_gh(*args), "token=none", args)

    def test_text_that_only_mentions_these_words_stays_on_the_app(self):
        with open(os.path.join(self.dir, "ok.graphql"), "w") as f:
            f.write("query { repository(owner:\"o\", name:\"r\") { issue(number:1) { title } } }")
        for args in (("pr", "create", "--body", "uses @media queries"),
                     ("pr", "create", "--title", "fix @me and projectV2", "--body-file", "-"),
                     ("issue", "comment", "9", "--body", "see projectItems"),
                     ("issue", "comment", "9", "--body=see projectItems and viewer"),
                     ("issue", "comment", "9", "--body", "@me"), ("issue", "comment", "9", "--body=@me"),
                     ("issue", "create", "--title=assignee:@me", "--body=x"),
                     ("issue", "comment", "9", "-F", "projectV2.md"),
                     ("api", "repos/o/r/issues/9/comments", "-f", "body=see projectItems"),
                     ("api", "repos/o/r/issues/9/comments", "-F", "body=@me"),
                     ("api", "graphql", "-F", "query=@" + os.path.join(self.dir, "ok.graphql")),
                     ("issue", "list", "--search", "@media in:title"),
                     # -p is a project flag only on issue|pr create|edit: on gist create it is --public
                     ("gist", "create", "-p", "notes.txt")):
            self.assertEqual(self.run_gh(*args), "token=app-token", args)

    def test_the_login_switch_and_a_given_token_win(self):
        self.assertEqual(self.run_gh("issue", "view", "9", TVT_GH_AS_USER="1"), "token=none")
        self.assertEqual(self.run_gh("issue", "view", "9", GH_TOKEN="mine"), "token=mine")
        self.assertEqual(self.run_gh("issue", "view", "9", GH_TOKEN="mine", TVT_GH_AS_USER="1"), "token=mine")

    def test_an_app_token_left_in_the_environment_never_goes_to_the_login(self):
        marked = dict(GH_TOKEN="inherited", TVT_GH_APP_TOKEN="1")
        self.assertEqual(self.run_gh("issue", "view", "9", TVT_GH_AS_USER="1", **marked), "token=none")
        self.assertEqual(self.run_gh("project", "list", **marked), "token=none")
        self.assertEqual(self.run_gh("issue", "list", "--assignee", "@me", **marked), "token=none")
        # for the App's own calls it is kept (and not minted again)
        self.set_token_script("exit 1")
        self.assertEqual(self.run_gh("issue", "view", "9", **marked), "token=inherited")

    def test_an_unconfigured_app_falls_back_to_the_login_silently(self):
        self.set_token_script("exit 1")
        out = self.run_full("issue", "view", "9")
        self.assertEqual((out.stdout.strip(), out.stderr), ("token=none", ""))

    def test_a_failing_app_falls_back_with_one_warning_and_no_secrets(self):
        self.set_token_script("echo leaked-token; echo leaked-stderr >&2; exit 2")
        out = self.run_full("issue", "view", "9")
        self.assertEqual(out.stdout.strip(), "token=none")
        self.assertEqual(out.stderr.strip(), "agent-bin/gh: the App token isn't available (gh-app-token exit 2); using the login")
        self.assertNotIn("leaked", out.stdout + out.stderr)

    def test_several_copies_of_the_wrapper_on_path_reach_the_real_gh(self):
        other = os.path.join(self.dir, "other", "agent-bin")      # another project's wrapper: execs the next gh on PATH
        second = os.path.join(self.dir, "second", "tools", "agent-bin")
        os.makedirs(other)
        os.makedirs(second)
        self.make_exec(os.path.join(other, "gh"), '#!/usr/bin/env bash\nexec gh "$@"\n')
        shutil.copy(self.wrapper, os.path.join(second, "gh"))
        self.make_exec(os.path.join(second, "gh"), None)
        shutil.copy(self.token_script, os.path.join(self.dir, "second", "tools", "gh-app-token"))
        first = os.path.dirname(self.wrapper)
        self.path = os.pathsep.join([first, other, second, self.real] + self.tail)
        self.assertEqual(self.run_gh("issue", "view", "9"), "token=app-token")
        # a call that arrives at either copy
        self.wrapper = os.path.join(second, "gh")
        self.assertEqual(self.run_gh("issue", "view", "9"), "token=app-token")

    def test_a_nested_call_does_no_routing(self):
        # TVT_GH_WRAPPED=1: straight to the real gh, environment untouched (no token minted, none dropped)
        self.assertEqual(self.run_gh("issue", "view", "9", TVT_GH_WRAPPED="1"), "token=none")
        self.assertEqual(self.run_gh("project", "list", TVT_GH_WRAPPED="1", GH_TOKEN="x", TVT_GH_APP_TOKEN="1"), "token=x")

    def test_no_real_gh_is_exit_127(self):
        self.path = os.pathsep.join([os.path.dirname(self.wrapper)] + self.tail)
        out = self.run_full("issue", "view", "9")
        self.assertEqual((out.returncode, out.stdout), (127, ""))
        self.assertIn("no real gh", out.stderr)


class BoardLoginOnlyTest(unittest.TestCase):
    """tools/board runs its marked block first thing: the login, never an App token, never a wrapper on PATH."""

    def block(self):
        with open(os.path.join(HERE, "board")) as f:
            text = f.read()
        start = text.index("# >>> login-only")
        end = text.index("# <<< login-only")
        return text[start:end]

    def run_block(self, **env):
        e = {k: v for k, v in os.environ.items() if k not in WrapperRoutingTest.ENV_OFF}
        e.update(env)
        script = self.block() + '\necho "path=$PATH"\necho "token=${GH_TOKEN:-none}"\necho "marker=${TVT_GH_APP_TOKEN:-}"\necho "user=$TVT_GH_AS_USER"\n'
        out = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, env=e, timeout=10)
        self.assertEqual(out.returncode, 0, out.stderr)
        return dict(line.split("=", 1) for line in out.stdout.splitlines())

    def test_agent_bin_directories_leave_path(self):
        got = self.run_block(PATH="/x/tools/agent-bin:/usr/bin:/y/agent-bin/:/bin::/z/agent-bin-not:agent-bin")
        self.assertEqual(got["path"], "/usr/bin:/bin:/z/agent-bin-not")
        self.assertEqual(got["user"], "1")

    def test_an_app_token_is_dropped_and_the_callers_own_is_kept(self):
        got = self.run_block(PATH="/usr/bin", GH_TOKEN="app", TVT_GH_APP_TOKEN="1")
        self.assertEqual((got["token"], got["marker"]), ("none", ""))
        got = self.run_block(PATH="/usr/bin", GH_TOKEN="mine")
        self.assertEqual(got["token"], "mine")

    def test_the_status_sync_does_the_same(self):
        import board_status_sync
        env = {"PATH": os.pathsep.join(["/x/agent-bin", "/usr/bin", "/y/tools/agent-bin/"]), "GH_TOKEN": "app", "TVT_GH_APP_TOKEN": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            board_status_sync.use_login()
            self.assertEqual((os.environ["PATH"], os.environ["TVT_GH_AS_USER"]), ("/usr/bin", "1"))
            self.assertNotIn("GH_TOKEN", os.environ)
            self.assertNotIn("TVT_GH_APP_TOKEN", os.environ)
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin", "GH_TOKEN": "mine"}, clear=True):
            board_status_sync.use_login()
            self.assertEqual(os.environ["GH_TOKEN"], "mine")


if __name__ == "__main__":
    unittest.main()
