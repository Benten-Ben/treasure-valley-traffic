"""farm-export's FIELDS_SQL: the column order and the cdl coalesce (plugins/farm/ingest/export.py). Standard library only.

A NULL cdl (a field with no crop code) is written as 0, so it can't shift the columns after it under the FlatGeobuf
bug; acres is the one nullable column left, and it stays last. Run: python3 -m unittest discover -s plugins/farm/tests -t .
"""

import re
import unittest

from plugins.farm.ingest import classes as C
from plugins.farm.ingest import export as E


def _cases():
    return " ".join(f"when '{g}' then {code}" for g, code in C.COVER_CODES.items() if code)


class FieldsSqlTest(unittest.TestCase):
    def setUp(self):
        self.sql = E.FIELDS_SQL.format(cases=_cases())

    def test_column_order(self):
        body = self.sql.split("from (", 1)[1].split("from farm.field", 1)[0]
        self.assertTrue(body.split()[1] == "f.id,")         # the first column is the bare id
        aliases = re.findall(r"\bas (\w+)", body)
        self.assertEqual(aliases, ["csbid", "crop_group", "cdl", "bearing", "acres", "geom"])

    def test_cdl_is_coalesced_to_zero(self):
        self.assertIn("coalesce(f.crops[cardinality(f.crops)]::smallint, 0::smallint) as cdl", self.sql)

    def test_acres_is_the_only_nullable_column_and_stays_last(self):
        self.assertIn("f.acres::float8 as acres,", self.sql)
        self.assertNotIn("coalesce(f.acres", self.sql)
        self.assertLess(self.sql.index(" as cdl"), self.sql.index(" as acres"))


if __name__ == "__main__":
    unittest.main()
