"""Tests for deploy/scratch/run.sh, read as text (it needs Docker and the VM to run).

    python3 -m unittest discover -s deploy/scratch/tests
"""
import os
import unittest

SCRATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ProductionTreesIsHidden(unittest.TestCase):
    """Production's trees/ holds builds in the format from before the City's data left the public tables (#277):
    a scratch job mounts production's archive read-only, so it must see an empty folder there."""
    text = open(os.path.join(SCRATCH, "run.sh")).read()

    def test_an_empty_read_only_tmpfs_is_mounted_over_it(self):
        self.assertIn("destination=/srv/archive-prod/trees,tmpfs-size=1m,tmpfs-mode=0555", self.text)
        self.assertIn('[ ! -d "$PROD_ARCHIVE/trees" ] || args+=(--mount "type=tmpfs,', self.text)

    def test_it_comes_after_the_archive_is_mounted_and_before_the_image(self):
        t = self.text
        bind = t.index('-v "$tree":/repo -v "$ARCHIVES/$db":/srv/archive -v "$PROD_ARCHIVE":/srv/archive-prod:ro')
        hide = t.index("destination=/srv/archive-prod/trees")
        self.assertLess(bind, hide)
        self.assertLess(hide, t.index('args+=(${extra[@]+"${extra[@]}"} "$image"'))


if __name__ == "__main__":
    unittest.main()
