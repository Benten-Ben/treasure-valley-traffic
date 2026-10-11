"""soils-photo-load and the palette in soils-export, against a database, on the synthetic survey.

Runs only with TVT_TEST_DATABASE_URL (a migrated test database with PostGIS); each test rolls back, and exports go to
a temporary archive. The stats.json here is written by hand in photo_stats.py's format (the worker's own test,
test_photo_stats, checks that it writes that format).

Run: TVT_TEST_DATABASE_URL=postgresql://... python3 -m unittest plugins.soils.tests.test_photo_load
"""

import contextlib
import io
import json
import os
import struct
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from basemap.ground import fgb
from basemap.ground import inputs as GI
from basemap.ground import manifest as M
from plugins.soils.ingest import export, load, package, photo_load
from plugins.soils.tests import synthetic
from plugins.soils.tests.test_load import MIGRATION, NOW, URL, psycopg

INPUTS = [
    {"name": "naip", "licence": "public-domain", "republish": "yes", "credit": "USDA NAIP", "version": "synthetic"},
    {"name": "ssurgo", "licence": "public-domain", "republish": "yes",
     "credit": "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)", "source": "soils/ssurgo"},
    {"name": "osm", "licence": "ODbL-1.0", "republish": "yes", "credit": "© OpenStreetMap contributors",
     "version": "md5 0123"},
    {"name": "cdl", "licence": "public-domain", "republish": "yes", "credit": "USDA NASS Cropland Data Layer 2025",
     "source": "farm/nass_cdl", "version": "2025"},
    {"name": "sentinel-2", "licence": "Copernicus", "republish": "yes",
     "credit": "Contains modified Copernicus Sentinel data 2025", "sha256": "ab" * 32},
]


def row(level, key, flight=None, n=30000, L=0.8, fallback=None, polygons=4):
    return {"level": level, "key": key, "photo": "naip2025", "flight": flight, "mask": "photo-v1", "n_px": n,
            "n_polygons": None if flight else polygons, "lab_med": [L, 0.005, 0.035],
            "lab_cov": [0.004, 0.0, 0.0, 0.0001, 0.0, 0.0002], "l_p10": L - 0.07, "l_p90": L + 0.07,
            "oct_l": [1e-4, 1e-4, 9e-5, 8e-5, 5e-5], "oct_c": [3e-6, 3e-6, 3e-6, 2e-6, 2e-6], "fallback": fallback}


def write_build(root, build_id="photo-20261011T190000Z", rows=None, partial=False):
    folder = os.path.join(root, "soils", "photo", build_id)
    os.makedirs(folder)
    rows = rows if rows is not None else [
        row("mapunit", "1001", "2025-06-18"), row("mapunit", "1001"),
        row("mapunit", "2001", "2025-05-25", n=5000, L=0.78), row("mapunit", "2001", n=5000, L=0.78, polygons=1),
        row("ground_type", "purdam:silt-loam", "2025-06-18", n=30000),
        row("ground_type", "purdam:silt-loam", "2025-05-25", n=5000, L=0.78),
        row("ground_type", "purdam:silt-loam", n=35000, L=0.797, polygons=5),
        row("ground_type", "chilcott:gravelly-silt-loam", n=0, L=0.76, fallback="albedo", polygons=0),
    ]
    doc = {"format": "tvt-soils-photo/1", "build_id": build_id, "started": "2026-10-11T19:00:00Z",
           "finished": "2026-10-11T21:00:00Z", "photo": "naip2025", "mask": "photo-v1", "partial": partial,
           "soils_export": "20261011T160000Z", "inputs": INPUTS, "files": {},
           "params": {"rules": {"green_cut_s2": 0.45}, "res": 0.6, "octaves_m": [1.2, 2.4, 4.8, 9.6, 19.2]},
           "counts": {"rows": len(rows), "calibration": "pass", "flight_days": {"gains_needed": False}},
           "rows": rows}
    with open(os.path.join(folder, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return folder


def fgb_properties(path):
    """Each feature's properties from a FlatGeobuf, decoded with the standard library: [{column: value}], for the
    int and string columns the soils export writes. It reads each property's column index from the file, so a
    writer that labels a column wrongly shows here."""
    with open(path, "rb") as f:
        data = f.read()
    h = fgb.parse_header(data)
    names = list(h.columns)
    pos = 12 + struct.unpack_from("<I", data, 8)[0]
    if h.index_node_size and h.features_count:
        n, level_nodes, total = h.features_count, h.features_count, 0
        while True:                                            # the packed Hilbert R-tree's size (FlatGeobuf spec)
            total += level_nodes
            if level_nodes == 1:
                break
            level_nodes = -(-level_nodes // h.index_node_size)
        pos += total * 40
    out = []
    while pos < len(data):
        size = struct.unpack_from("<I", data, pos)[0]
        buf = memoryview(data)[pos + 4:pos + 4 + size]
        t = fgb._Table(buf, struct.unpack_from("<I", buf, 0)[0])
        start, n = t.vector(1)
        props, i = {}, 0
        raw = bytes(buf[start:start + n]) if start is not None else b""
        while i < len(raw):
            col = struct.unpack_from("<H", raw, i)[0]
            i += 2
            name = names[col]
            if h.columns[name] == "int":
                props[name] = struct.unpack_from("<i", raw, i)[0]
                i += 4
            elif h.columns[name] == "string":
                length = struct.unpack_from("<I", raw, i)[0]
                props[name] = raw[i + 4:i + 4 + length].decode("utf-8")
                i += 4 + length
            else:
                raise ValueError(f"column type {h.columns[name]} isn't decoded here")
        out.append(props)
        pos += 4 + size
    return out


@unittest.skipUnless(URL and psycopg, "set TVT_TEST_DATABASE_URL (and install psycopg) for the database tests")
class PhotoLoadTest(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg.connect(URL)
        if not self.conn.execute("select to_regclass('ops.source') is not null").fetchone()[0]:
            self.conn.close()
            self.skipTest("the test database isn't migrated (db/migrate.py)")
        if not self.conn.execute("select to_regclass('soils.map_unit') is not null").fetchone()[0]:
            with open(MIGRATION, encoding="utf-8") as f:
                self.conn.execute(f.read())
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = os.path.join(self.tmp.name, "archive")
        os.makedirs(self.archive)
        prepared = os.path.join(self.tmp.name, "prepared")
        synthetic.write_prepared(prepared)
        load.load(self.conn, package.read(prepared), now=NOW)

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()
        self.tmp.cleanup()

    def test_loads_a_build_and_the_view_reads_it(self):
        folder = write_build(self.archive)
        stats = photo_load.load(self.conn, folder, now=datetime(2026, 10, 11, 21, 5, tzinfo=timezone.utc))
        self.assertEqual(stats["rows"], 8)
        self.assertEqual(stats["ground types"], {"measured": 1, "albedo": 1})
        b = self.conn.execute("select kind, finished_at, license, republish, credit, inputs, counts "
                              "from soils.build where build_id = 'photo-20261011T190000Z'").fetchone()
        self.assertEqual(b[0], "photo")
        self.assertIsNotNone(b[1])
        self.assertEqual(b[2], "public-domain; ODbL-1.0; Copernicus")
        self.assertEqual(b[3], "yes")
        self.assertIn("© OpenStreetMap contributors", b[4])
        self.assertEqual(b[5]["sentinel-2"], "ab" * 32)
        self.assertEqual(b[6]["calibration"], "pass")
        colour = dict(self.conn.execute(
            "select ground_type, fallback from soils.ground_colour order by 1").fetchall())
        self.assertEqual(colour, {"chilcott:gravelly-silt-loam": "albedo", "purdam:silt-loam": None})
        med, cov, octl, flight = self.conn.execute(
            """select lab_med, lab_cov, oct_l, flight from soils.photo_stats
               where level = 'ground_type' and key = 'purdam:silt-loam' and flight = '2025-05-25'""").fetchone()
        self.assertAlmostEqual(med[0], 0.78, places=5)
        self.assertEqual(len(cov), 6)
        self.assertAlmostEqual(octl[3], 8e-5, places=9)
        self.assertEqual(str(flight), "2025-05-25")

    def test_refuses_partial_repeated_and_stale_builds(self):
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "partial"):
            photo_load.load(self.conn, write_build(self.archive, "photo-a", partial=True))
        folder = write_build(self.archive, "photo-b")
        photo_load.load(self.conn, folder)
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "loaded already"):
            photo_load.load(self.conn, folder)
        stale = write_build(self.archive, "photo-c", rows=[row("mapunit", "9999"), row("ground_type", "gone:loam")])
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "reloaded since"):
            photo_load.load(self.conn, stale)

    def test_refuses_a_malformed_file(self):
        bad = [row("mapunit", "1001", fallback="series")]
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "fallback"):
            photo_load.read(write_build(self.archive, "photo-d", rows=bad))
        bad = [dict(row("mapunit", "1001"), lab_cov=[0.1])]
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "lab_cov"):
            photo_load.read(write_build(self.archive, "photo-e", rows=bad))
        bad = [row("mapunit", "1001"), row("mapunit", "1001")]
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "repeats"):
            photo_load.read(write_build(self.archive, "photo-f", rows=bad))
        folder = write_build(self.archive, "photo-g")
        os.rename(folder, folder + "-renamed")
        with self.assertRaisesRegex(photo_load.PhotoLoadError, "folder's name"):
            photo_load.read(folder + "-renamed")

    def test_the_export_carries_the_palette(self):
        m = export.export(self.conn, self.archive, build="20261011T160000Z")
        self.assertFalse(m.has("palette"))                       # no photo build yet: the ground's flat colours
        photo_load.load(self.conn, write_build(self.archive))
        m = export.export(self.conn, self.archive, build="20261011T220000Z")
        again = M.read(m.folder)
        pal = again.layer("palette")
        self.assertEqual((pal["format"], pal["schema"], pal["licence"], pal["republish"], pal["base"]),
                         ("JSON", "soils.palette/1", "ODbL-1.0", "yes", False))
        self.assertEqual(pal["inputs"], ["ssurgo", "naip", "osm", "cdl", "sentinel-2"])
        self.assertIn("Contains modified Copernicus Sentinel data 2025", pal["credit"])
        self.assertEqual(again.inputs["cdl"]["source"], "farm/nass_cdl")
        self.assertEqual(again.layer("ground")["licence"], "public-domain")   # the ground layer stays SSURGO's
        plan = GI.resolve({"soils": again})
        self.assertFalse(plan.choice("soils/palette").fallback)
        with open(pal.path, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["schema"], "soils.palette/1")
        types = {t["id"]: t for t in doc["types"]}
        gids = dict(self.conn.execute("select id, gid from soils.ground_type").fetchall())
        self.assertEqual({k: t["gid"] for k, t in types.items()}, gids)
        p = types["purdam:silt-loam"]
        self.assertEqual((p["status"], p["n_px"], p["n_polygons"], p["flights"]),
                         ("measured", 35000, 5, ["2025-05-25", "2025-06-18"]))
        self.assertAlmostEqual(p["lab_med"][0], 0.797, places=5)
        self.assertEqual(types["chilcott:gravelly-silt-loam"]["status"], "albedo")
        self.assertEqual(types["rock-outcrop"]["status"], "none")
        self.assertIsNone(types["rock-outcrop"]["lab_med"])
        self.assertEqual(doc["builds"][0]["build"], "photo-20261011T190000Z")
        self.assertEqual(doc["builds"][0]["calibration"], "pass")

    def test_ground_fgb_columns_read_back_right(self):
        # PostGIS's ST_AsFlatGeobuf writes the column after a null under the null's index; misc, the one nullable
        # column, is last so nothing follows it.
        m = export.export(self.conn, self.archive, build="20261011T160000Z")
        props = fgb_properties(m.layer("ground").path)
        self.assertEqual(len(props), 6)
        db = dict(self.conn.execute("select gid, mukey from soils.polygon").fetchall())
        for p in props:
            self.assertEqual(p["mukey"], db[p["id"]])
            self.assertIn(p.get("misc"), (None, "water", "rock", "nodata"))
        self.assertEqual(list(fgb.read_header(m.layer("ground").path).columns),
                         ["id", "ground_type", "mukey", "misc"])

    def test_command(self):
        folder = write_build(self.archive)
        out = io.StringIO()
        with mock.patch("ingest.db.connect", return_value=_Keep(self.conn)), contextlib.redirect_stdout(out):
            self.assertEqual(photo_load.main(["--build", folder, "--dry-run"]), 0)
        self.assertIn("dry run", out.getvalue())
        self.assertIsNone(self.conn.execute(
            "select 1 from soils.build where build_id = 'photo-20261011T190000Z'").fetchone())
        err = io.StringIO()
        with mock.patch("ingest.db.connect", return_value=_Keep(self.conn)), contextlib.redirect_stderr(err):
            self.assertEqual(photo_load.main(["--build", os.path.join(self.archive, "nowhere")]), 1)
        self.assertIn("stats.json", err.getvalue())


class _Keep:
    """A connection the command can't close or commit (the test rolls back)."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        if name in ("commit", "close"):
            return lambda: None
        return getattr(self.conn, name)


if __name__ == "__main__":
    unittest.main()
