"""CDL class codes and our crop groups (farm.crop_class). Standard library only.

crop_classes.csv (beside this file) is NASS's legend for the CDL (names and colours, public domain) with three columns
of ours: the crop group, and the AgriMet crops whose water use the field card can show (our mapping ⚠️). The groups
are the farm design's (Oct 8): corn and sorghum, hay and alfalfa, small grains, roots, vegetables and beans,
specialty (mint, hops, seed, orchards, vineyards), pasture and fallow, plus developed and other. The codes the
Oct 8 analysis grouped are as it had them (its field counts rest on them); the rest of NASS's crop codes are placed
by kind, and none of them is in the box's 2025 fields.

Group codes in crop_cover.tif's band 1 (COVER_CODES): 0 none, 1 corn, 2 hay, 3 grain, 4 roots, 5 specialty,
6 fallow. Pasture isn't crop on the ground: the land-cover scheme paints it as grass (decision 15).

    python3 -m ingest farm-cdl-load --accuracy NASS_CDL_ID25_accuracy.xlsx    # adds NASS's Idaho accuracy
"""

import csv
import os
import re
import zipfile
import xml.etree.ElementTree as ET

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crop_classes.csv")

GROUPS = ("corn", "hay", "grain", "roots", "specialty", "pasture", "fallow", "developed", "other")
CROP_GROUPS = ("corn", "hay", "grain", "roots", "specialty", "fallow")          # crop on the ground (decision 15)
FARMED_GROUPS = CROP_GROUPS + ("pasture",)                                        # still farmed, for growth and plats
LETTERS = {"corn": "c", "hay": "h", "grain": "g", "roots": "r", "specialty": "s", "pasture": "p", "fallow": "f",
           "developed": "d", "other": "o"}
UNKNOWN_LETTER = "-"                     # a year with no code, or a code NASS's legend doesn't have
COVER_CODES = {"none": 0, "corn": 1, "hay": 2, "grain": 3, "roots": 4, "specialty": 5, "fallow": 6}
DEVELOPED = frozenset((121, 122, 123, 124))     # Developed/Open Space, Low, Medium and High Intensity

GROUP_TITLES = {"corn": "Corn and sorghum", "hay": "Hay and alfalfa", "grain": "Small grains",
                "roots": "Roots, vegetables and beans", "specialty": "Specialty (mint, hops, seed, orchards, vineyards)",
                "pasture": "Pasture", "fallow": "Fallow", "developed": "Developed", "other": "Not farmed"}


class ClassesError(ValueError):
    pass


def read(path=CSV_PATH):
    """{code: {"code", "name", "grp", "letter", "nass_hex", "agrimet"}} from the classes CSV, checked."""
    out = {}
    with open(path, encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f)
        if rows.fieldnames != ["code", "name", "group", "nass_hex", "agrimet"]:
            raise ClassesError(f"{path}: columns must be code, name, group, nass_hex, agrimet")
        for r in rows:
            code = int(r["code"])
            if not 1 <= code <= 255 or code in out:
                raise ClassesError(f"{path}: code {code} is out of range or repeated")
            if r["group"] not in GROUPS:
                raise ClassesError(f"{path}: code {code}: unknown group {r['group']!r}")
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", r["nass_hex"]):
                raise ClassesError(f"{path}: code {code}: colour {r['nass_hex']!r}")
            agrimet = r["agrimet"].split()
            if not all(re.fullmatch(r"[A-Z]{4}", a) for a in agrimet):
                raise ClassesError(f"{path}: code {code}: AgriMet crops {r['agrimet']!r}")
            out[code] = {"code": code, "name": r["name"].strip(), "grp": r["group"], "letter": LETTERS[r["group"]],
                         "nass_hex": r["nass_hex"].upper(), "agrimet": agrimet}
    return out


def group_of(classes, code):
    """A code's crop group ('other' for a code the legend doesn't have, None for no code)."""
    if not code:
        return None
    c = classes.get(int(code))
    return c["grp"] if c else "other"


def letters(classes, crops):
    """One letter per year: the crop group's (classes.LETTERS), '-' for no code or one NASS doesn't name."""
    return "".join(classes[c]["letter"] if c in classes else UNKNOWN_LETTER for c in crops)


def cover_code(classes, code):
    """crop_cover band 1's value for a CDL code: its crop group's code, 0 when it isn't crop."""
    return COVER_CODES.get(group_of(classes, code) or "none", 0)


def cover_table(classes):
    """A 256-entry list mapping every CDL code to crop_cover band 1's value (for NumPy: np.asarray(...)[cdl])."""
    return [cover_code(classes, c) if c else 0 for c in range(256)]


# --- NASS's accuracy workbook --------------------------------------------------------------------------------------

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_SHEET = "Summary Table"
_MAX_XML = 64 * 1024 * 1024           # an accuracy workbook's parts are a few MB at most


def _xml(z, name):
    info = z.getinfo(name)
    if info.file_size > _MAX_XML:
        raise ClassesError(f"{name} in the workbook is {info.file_size} bytes; refusing to parse it")
    return ET.fromstring(z.read(name))


def _number(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None                      # '#DIV/0!' (no reference pixels), blanks
    return v if v == v else None


def read_accuracy(path, state="ID", year=2025):
    """{code: {"state", "year", "producer", "user", "ref_px", "map_px"}} from NASS's CDL accuracy workbook (its
    'Summary Table' sheet: one row per code with Correct, Total, Producer's ... User's accuracy), for codes with a
    number. Standard library: the .xlsx is a zip of XML parts."""
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as err:
        raise ClassesError(f"{path}: not an .xlsx workbook ({err})") from None
    with z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in _xml(z, "xl/sharedStrings.xml").findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        wb = _xml(z, "xl/workbook.xml")
        rels = _xml(z, "xl/_rels/workbook.xml.rels")
        rid = next((s.get(f"{{{_NS['r']}}}id") for s in wb.iter(f"{{{_NS['m']}}}sheet") if s.get("name") == _SHEET),
                   None)
        if rid is None:
            raise ClassesError(f"{path}: no sheet named {_SHEET!r}")
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        target = target.lstrip("/")
        ws = _xml(z, target if target.startswith("xl/") else "xl/" + target)

        def cells(row):
            out = {}
            for c in row.findall("m:c", _NS):
                v = c.find("m:v", _NS)
                val = None if v is None else v.text
                if c.get("t") == "s" and val is not None:
                    val = shared[int(val)]
                elif c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
                out[re.sub(r"[0-9]+", "", c.get("r") or "")] = val
            return out

        header, out = None, {}
        for row in ws.iter(f"{{{_NS['m']}}}row"):
            c = cells(row)
            if c.get("A") == "Category" and c.get("E") == "Producer" and c.get("I") == "User":
                header = c
                continue
            if header is None or not (c.get("B") or "").strip().isdigit():
                continue
            code = int(c["B"])
            producer, user = _number(c.get("E")), _number(c.get("I"))
            if producer is None and user is None:
                continue
            ref, mapped = _number(c.get("D")), _number(c.get("H"))
            out[code] = {"state": state, "year": year,
                         "producer": None if producer is None else round(producer, 4),
                         "user": None if user is None else round(user, 4),
                         "ref_px": None if ref is None else int(ref), "map_px": None if mapped is None else int(mapped)}
        if header is None:
            raise ClassesError(f"{path}: the {_SHEET!r} sheet has no 'Category ... Producer ... User' header row")
        return out


def ensure(conn, classes=None, accuracy=None):
    """Upsert farm.crop_class from the CSV (names, groups, letters, colours, AgriMet crops). accuracy, when given,
    replaces each code's accuracy ({code: {...}}; codes it lacks get none); otherwise accuracy is kept. Doesn't
    commit. Returns the number of classes."""
    import json
    classes = classes or read()
    rows = [(c["code"], c["name"], c["grp"], c["letter"], c["nass_hex"], c["agrimet"]) for c in classes.values()]
    with conn.cursor() as cur:
        cur.executemany(
            """insert into farm.crop_class (code, name, grp, letter, nass_hex, agrimet) values (%s, %s, %s, %s, %s, %s)
               on conflict (code) do update set name = excluded.name, grp = excluded.grp, letter = excluded.letter,
                 nass_hex = excluded.nass_hex, agrimet = excluded.agrimet""", rows)
        cur.execute("delete from farm.crop_class where code <> all(%s)", (list(classes),))
        if accuracy is not None:
            cur.execute("update farm.crop_class set accuracy = null")
            cur.executemany("update farm.crop_class set accuracy = %s::jsonb where code = %s",
                            [(json.dumps(a), code) for code, a in accuracy.items() if code in classes])
    return len(rows)
