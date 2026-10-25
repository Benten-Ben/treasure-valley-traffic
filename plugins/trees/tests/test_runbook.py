"""The production runbook for migration 0003 (plugins/trees/README.md) is a list of commands someone pastes on the
server. These tests keep the properties the review found missing from it; they read the text only."""
import os
import re
import unittest

README = os.path.join(os.path.dirname(__file__), "..", "README.md")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _steps():
    text = _read(README)
    body = text[text.index("### Runbook: migration 0003 on production"):text.index("The settings were calibrated")]
    parts = re.split(r"\n(?=\d\. \*\*)", body)
    return {int(p[0]): p for p in parts if re.match(r"\d\. \*\*", p)}


class RunbookTest(unittest.TestCase):
    def setUp(self):
        self.s = _steps()

    def test_host_commands_use_the_archive_path_not_the_container_variable(self):
        for n in (1, 3, 7):
            self.assertNotRegex(self.s[n], r"\$TVT_ARCHIVE/", f"step {n}")

    def test_the_server_gets_main_before_the_public_rebuild(self):
        step3 = self.s[3]
        self.assertIn("/srv/tvt/repo:/repo:ro", step3)
        self.assertLess(step3.index("Push `main`"), step3.index("build.py"))

    def test_the_production_load_is_a_heavy_command(self):
        step4 = self.s[4]
        self.assertRegex(step4, r"/srv/tvt/work/bin/heavy --deadline \S+ --runtime \d+ --peak \d+ [^`]*compose.load.yml")
        self.assertIn("cd /srv/tvt/repo/deploy", step4)

    def test_the_preview_is_checked_where_the_trees_layer_runs(self):
        self.assertIn("localhost:8081/api/trees/", self.s[4])
        self.assertIn("localhost:8080/api/trees/", self.s[4])

    def test_the_migration_check_greps_the_line_migrate_prints(self):
        self.assertIn("grep -F 'applied  trees/0003'", self.s[4])
        self.assertNotIn("grep -i migrat", self.s[4])

    def test_an_early_migration_is_said_to_cost_only_transient_gaps(self):
        text = _read(README)
        intro = text[text.index("### Runbook: migration 0003 on production"):text.index("0. **Ordering")]
        self.assertIn("only effect is transient gaps", intro)
        self.assertNotIn("dropped columns", "\n".join(self.s.values()))

    def test_the_migration_keeps_the_city_columns_empty(self):
        sql = _read(os.path.join(os.path.dirname(README), "migrations", "0003_no_city_rows.sql"))
        self.assertNotRegex(sql, r"(?i)drop\s+column")
        self.assertIn("CHECK (catalogue IS NULL AND catalogue_id IS NULL)", sql)

    def test_the_private_matching_build_is_named_like_the_loaded_build(self):
        step5 = self.s[5]
        self.assertIn("basename(--out)", step5)
        self.assertIn("/srv/tvt/work/trees-match/<new build name>", step5)

    def test_the_rebuild_passes_the_mask_and_uses_the_builds_folder(self):
        self.assertIn("--mask /in/", self.s[3])
        self.assertIn("--out /srv/archive/trees/builds/<new build name>", self.s[3])
        self.assertIn("with the same options plus", self.s[5])
        self.assertIn("trees/builds/<new build name>", self.s[4])
        self.assertIn("/srv/tvt/archive/trees/builds", self.s[1])

    def test_old_builds_leave_the_archive_without_the_shrub_builds(self):
        self.assertIn("grep -vx shrubs", self.s[1])
        self.assertIn("mkdir -p <private files>/trees-old-builds &&", self.s[7])
        self.assertIn('echo "grep exit $?"', self.s[7])


if __name__ == "__main__":
    unittest.main()
