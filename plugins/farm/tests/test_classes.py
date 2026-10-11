"""CDL classes, crop groups and the growth rule (plugins/farm/ingest/classes.py, growth.py). Standard library only.

Run: python3 -m unittest discover -s plugins/farm/tests -t .
"""

import os
import tempfile
import unittest
import zipfile

from plugins.farm.ingest import classes as C
from plugins.farm.ingest import growth as G


class ClassesTest(unittest.TestCase):
    def setUp(self):
        self.classes = C.read()

    def test_the_designs_groups(self):
        # The Oct 8 analysis' grouping, which the farm design's field counts rest on.
        expect = {1: "corn", 228: "corn", 12: "corn", 4: "corn", 36: "hay", 37: "hay", 58: "hay", 24: "grain",
                  23: "grain", 205: "grain", 21: "grain", 41: "roots", 42: "roots", 49: "roots", 43: "roots",
                  53: "roots", 14: "specialty", 56: "specialty", 59: "specialty", 67: "specialty", 68: "specialty",
                  176: "pasture", 61: "fallow", 121: "developed", 122: "developed", 123: "developed",
                  124: "developed", 152: "other", 111: "other", 131: "other", 190: "other"}
        for code, grp in expect.items():
            self.assertEqual(self.classes[code]["grp"], grp, code)
        self.assertEqual(self.classes[1]["name"], "Corn")
        self.assertEqual(self.classes[36]["agrimet"], ["ALFP", "ALFM"])
        self.assertEqual(self.classes[1]["nass_hex"], "#FFD200")

    def test_every_crop_code_has_a_crop_group(self):
        crop_codes = set(range(1, 61)) | set(range(66, 78)) | set(range(204, 255))
        for code in crop_codes & set(self.classes):
            self.assertIn(self.classes[code]["grp"], C.FARMED_GROUPS, code)

    def test_letters_and_cover_codes(self):
        self.assertEqual(C.letters(self.classes, [1, 1, 36, 36, 1, 24, 24, 1]), "cchhcggc")
        self.assertEqual(C.letters(self.classes, [176, 61, 14, 41, 122, 152, 0, 7]), "pfsrdo--")
        table = C.cover_table(self.classes)
        self.assertEqual(len(table), 256)
        self.assertEqual([table[c] for c in (0, 1, 36, 24, 41, 14, 61, 176, 122, 152)], [0, 1, 2, 3, 4, 5, 6, 0, 0, 0])
        self.assertEqual(C.group_of(self.classes, 0), None)
        self.assertEqual(C.group_of(self.classes, 7), "other")       # a code NASS's legend doesn't have

    def test_a_bad_csv_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for body in ("code,name,group,nass_hex,agrimet\n1,Corn,maize,#FFD200,\n",
                         "code,name,group,nass_hex,agrimet\n1,Corn,corn,yellow,\n",
                         "code,name,group,nass_hex,agrimet\n1,Corn,corn,#FFD200,\n1,Corn,corn,#FFD200,\n",
                         "code,name,grp,nass_hex,agrimet\n1,Corn,corn,#FFD200,\n",
                         "code,name,group,nass_hex,agrimet\n1,Corn,corn,#FFD200,fcrn\n"):
                path = os.path.join(tmp, "c.csv")
                with open(path, "w") as f:
                    f.write(body)
                with self.subTest(body=body), self.assertRaises(C.ClassesError):
                    C.read(path)


def _xlsx(path, rows):
    """A minimal workbook with a 'Summary Table' sheet: rows are lists of (column letter, value)."""
    shared, cells = [], []
    for i, row in enumerate(rows, 1):
        out = []
        for col, v in row:
            if isinstance(v, str):
                shared.append(v)
                out.append(f'<c r="{col}{i}" t="s"><v>{len(shared) - 1}</v></c>')
            else:
                out.append(f'<c r="{col}{i}"><v>{v}</v></c>')
        cells.append(f'<row r="{i}">{"".join(out)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rns}><sheets><sheet name="GEE" sheetId="1" r:id="rId1"/>'
                                      f'<sheet name="Summary Table" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData/></worksheet>")
        z.writestr("xl/worksheets/sheet2.xml", f'<worksheet {ns}><sheetData>{"".join(cells)}</sheetData></worksheet>')
        z.writestr("xl/sharedStrings.xml",
                   f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in shared) + "</sst>")


class AccuracyTest(unittest.TestCase):
    def test_reads_producers_and_users_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "acc.xlsx")
            _xlsx(path, [
                [("A", "Overall"), ("C", 510026), ("D", 600337), ("E", 0.8495)],
                [("A", "Category"), ("C", "Correct"), ("D", "Total"), ("E", "Producer"), ("H", "Total"),
                 ("I", "User")],
                [("A", "Corn"), ("B", 1), ("C", 4743), ("D", 5034), ("E", 0.94219308700834326), ("H", 5252),
                 ("I", 0.90308453922315313)],
                [("A", "Cotton"), ("B", 2), ("C", 0), ("D", 0), ("E", "#DIV/0!"), ("H", 0), ("I", "#DIV/0!")],
                [("A", "Misc"), ("B", 47), ("C", 0), ("D", 1), ("E", 0), ("H", 0), ("I", "#DIV/0!")],
            ])
            acc = C.read_accuracy(path)
        self.assertEqual(acc[1], {"state": "ID", "year": 2025, "producer": 0.9422, "user": 0.9031, "ref_px": 5034,
                                  "map_px": 5252})
        self.assertNotIn(2, acc)
        self.assertEqual(acc[47]["user"], None)

    def test_refuses_a_workbook_without_the_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.xlsx")
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/'
                                              'main"><sheets/></workbook>')
                z.writestr("xl/_rels/workbook.xml.rels", "<Relationships/>")
            with self.assertRaises(C.ClassesError):
                C.read_accuracy(path)
            with open(path, "w") as f:
                f.write("not a zip")
            with self.assertRaises(C.ClassesError):
                C.read_accuracy(path)


class GrowthTest(unittest.TestCase):
    def setUp(self):
        self.classes = C.read()

    def classify(self, crops, permits=None):
        return G.classify(crops, 2018, self.classes, permits)

    def test_built_over(self):
        state, d = self.classify([36, 36, 1, 36, 176, 121, 122, 123])
        self.assertEqual(state, "built_over")
        self.assertEqual((d["rule"], d["farmed_early"], d["developed_by"], d["early_years"]),
                         ("growth/1", 4, 2023, [2018, 2021]))
        self.assertIsNone(d["permits"])
        # two farmed early years are enough; open space (121) in the last year isn't
        self.assertEqual(self.classify([1, 152, 152, 176, 152, 152, 121, 124])[0], "built_over")
        self.assertEqual(self.classify([1, 1, 1, 1, 1, 1, 122, 121])[0], "farmed")
        # one farmed early year isn't enough for built over
        self.assertEqual(self.classify([1, 152, 152, 152, 152, 152, 122, 122])[0], "farmed")
        # the year before the last must be developed too
        self.assertEqual(self.classify([1, 1, 1, 1, 1, 1, 1, 122])[0], "farmed")

    def test_being_built_needs_three_permits(self):
        crops = [176, 24, 24, 41, 41, 42, 1, 122]
        state, d = self.classify(crops, {"n": 3, "first": 2021, "last": 2024})
        self.assertEqual(state, "being_built")
        self.assertEqual((d["permits"], d["permit_years"]), (3, [2021, 2024]))
        state, d = self.classify(crops, {"n": 2, "first": 2022, "last": 2023})
        self.assertEqual(state, "farmed")
        self.assertIn("without permits", d["unconfirmed"])
        state, d = self.classify(crops, None)
        self.assertEqual(state, "farmed")
        self.assertIn("not available", d["unconfirmed"])
        # never farmed early: not flagged, whatever the permits
        self.assertEqual(self.classify([152, 152, 152, 152, 152, 152, 152, 122], {"n": 9})[0], "farmed")

    def test_still_farmed(self):
        state, d = self.classify([1, 1, 36, 36, 1, 24, 24, 1], {"n": 0})
        self.assertEqual(state, "farmed")
        self.assertNotIn("developed_by", d)
        self.assertNotIn("unconfirmed", d)
        self.assertEqual(d["permits"], 0)

    def test_short_windows(self):
        with self.assertRaises(ValueError):
            G.classify([1], 2018, self.classes)
        # A window under eight years: its first four years still count as early, developed ones included.
        self.assertEqual(G.classify([1, 122, 123], 2023, self.classes)[0], "farmed")   # one farmed year
        state, d = G.classify([1, 1, 122, 123], 2022, self.classes)
        self.assertEqual((state, d["early_years"], d["developed_by"]), ("built_over", [2022, 2025], 2024))


if __name__ == "__main__":
    unittest.main()
