"""Tests for terrain_reencode.py (docs/14 §14.10, WP17).

    python3.12 -m unittest discover -s basemap -t basemap     # needs numpy and GDAL for most of them

The PMTiles code is plain Python and always runs. The tile tests need numpy
and GDAL (PNG and WEBP drivers); the end-to-end test also needs the pmtiles
CLI. Each says why it skips when something is missing.
"""

import contextlib
import io
import json
import math
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_reencode as T  # noqa: E402

try:
    import numpy as np
    from osgeo import gdal
    gdal.UseExceptions()
    HAVE_GDAL = all(gdal.GetDriverByName(d) for d in ("PNG", "WEBP", "MEM"))
except ImportError:
    HAVE_GDAL = False
HAVE_PMTILES = shutil.which("pmtiles") is not None
needs_gdal = unittest.skipUnless(HAVE_GDAL, "needs numpy and GDAL with PNG and WEBP (run with python3.12)")
needs_cli = unittest.skipUnless(HAVE_GDAL and HAVE_PMTILES, "needs numpy, GDAL and the pmtiles CLI")


# --- synthetic terrain ---------------------------------------------------------------------------

def synthetic_elevation(z, x, y, size=512, seed=0):
    """Metres for one tile: a tilted plane, hills, and a little roughness, like the valley's edge."""
    n = 2 ** z
    px = (x + (np.arange(size) + 0.5) / size) / n          # 0..1 across the world
    py = (y + (np.arange(size) + 0.5) / size) / n
    gx, gy = np.meshgrid(px, py)
    km = 40075.0                                           # world width at the equator, km
    ex, ey = gx * km, gy * km
    h = 800 + 3.0 * (ex - ex.mean()) - 2.0 * (ey - ey.mean())
    h += 250 * np.sin(ex / 3.1) * np.cos(ey / 4.3)
    rng = np.random.default_rng(seed + z * 1000 + x * 7 + y)
    h += rng.normal(0, 0.4, h.shape)
    return h


def load_json(path):
    with open(path) as f:
        return json.load(f)


def encode_png(elev):
    v = np.round((elev.astype(np.float64) + 10000.0) * 10.0).clip(0, 2 ** 24 - 1).astype(np.uint32)
    rows, cols = v.shape
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 3, gdal.GDT_Byte)
    for b, arr in enumerate(((v >> 16) & 255, (v >> 8) & 255, v & 255), start=1):
        mem.GetRasterBand(b).WriteArray(arr.astype(np.uint8))
    name = f"/vsimem/test_terrain_{os.getpid()}.png"
    gdal.GetDriverByName("PNG").CreateCopy(name, mem)
    f = gdal.VSIFOpenL(name, "rb")
    gdal.VSIFSeekL(f, 0, 2)
    size = gdal.VSIFTellL(f)
    gdal.VSIFSeekL(f, 0, 0)
    data = bytes(gdal.VSIFReadL(1, size, f))
    gdal.VSIFCloseL(f)
    gdal.Unlink(name)
    return data, v


def tile_range(z, lon0, lat0, lon1, lat1):
    n = 2 ** z
    def tx(lon): return int((lon + 180) / 360 * n)
    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n)
    return range(tx(lon0), tx(lon1) + 1), range(ty(lat1), ty(lat0) + 1)


def write_pmtiles(path, tiles, meta, tmp):
    """tiles: {(z, x, y): bytes} -> a PMTiles file, the way terrain.py makes one (MBTiles, then
    pmtiles convert)."""
    mbtiles = os.path.join(tmp, os.path.basename(path) + ".mbtiles")
    if os.path.exists(mbtiles):
        os.remove(mbtiles)
    db = sqlite3.connect(mbtiles)
    db.executescript("create table metadata (name text, value text);"
                     "create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);")
    db.executemany("insert into metadata values (?, ?)", meta.items())
    for (z, x, y), data in tiles.items():
        db.execute("insert into tiles values (?, ?, ?, ?)", (z, x, 2 ** z - 1 - y, data))
    db.commit()
    db.close()
    subprocess.run(["pmtiles", "convert", "--quiet", f"--tmpdir={tmp}", mbtiles, path], check=True)
    os.remove(mbtiles)


def aligned_block(z, lon, lat):
    """The 2 x 2 block of zoom-z tiles, aligned to even tile numbers, around a point. The Hilbert
    curve visits such a block's four tiles one after another."""
    xs, ys = tile_range(z, lon, lat, lon, lat)
    x0, y0 = xs[0] & ~1, ys[0] & ~1
    return [(z, x, y) for x in (x0, x0 + 1) for y in (y0, y0 + 1)]


def make_input(folder, size=128, zooms=(6, 7, 8)):
    """A small terrain-RGB PMTiles like terrain.py's, plus a manifest. Two top-zoom tiles that
    follow each other on the Hilbert curve are identical, so the archive has a run
    (run_length 2) for the reader to expand."""
    meta = {"name": "terrain", "format": "png", "type": "baselayer", "encoding": "mapbox",
            "bounds": "-116.6,43.4,-116.0,43.8", "center": "-116.3,43.6,7",
            "minzoom": str(min(zooms)), "maxzoom": str(max(zooms)),
            "attribution": "synthetic test terrain"}
    tiles = [t for z in zooms for t in aligned_block(z, -116.2, 43.6)]
    ids = sorted(T.zxy_to_tileid(*t) for t in tiles if t[0] == max(zooms))
    flat = {T.tileid_to_zxy(t) for t in ids[1:3]}
    values, data = {}, {}
    for z, x, y in tiles:
        elev = np.full((size, size), 812.34) if (z, x, y) in flat else synthetic_elevation(z, x, y, size)
        data[(z, x, y)], values[(z, x, y)] = encode_png(elev)
    pm = os.path.join(folder, "terrain.pmtiles")
    write_pmtiles(pm, data, meta, folder)
    manifest ={"bounds": [-117.05, 43.0, -115.95, 43.85], "zoom": 10,
                "terrain": {"file": "terrain.pmtiles", "encoding": "mapbox", "tileSize": size,
                            "exaggeration": 1.3, "built": "2026-10-05", "attribution": "USGS 3DEP",
                            "source": "synthetic"}}
    with open(os.path.join(folder, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    return pm, values


# --- the browser's fixture (app/tests/e2e/terrain-fixture) ----------------------------------------
# A small synthetic terrain, as PNG and as WebP made by terrain_reencode.py, so the e2e spec can
# check that the browser decodes WebP terrain exactly like PNG. Rebuild it with
#   python3.12 basemap/test_terrain_reencode.py --write-e2e-fixture app/tests/e2e/terrain-fixture

E2E_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "tests", "e2e", "terrain-fixture")
E2E_POINT = (-116.15, 43.65)        # the Boise foothills
E2E_ZOOMS = (10, 11, 12)
E2E_SIZE = 256
WORLD_M = 2 * math.pi * 6378137.0


def e2e_elevation(mx, my, centre):
    """Metres at Web Mercator metres: a tilted plane with one round hill, smooth enough that
    MapLibre's sampling of it matches the formula to within a metre."""
    cx, cy = centre
    h = 900 + 0.01 * (mx - cx) - 0.008 * (my - cy)
    return h + 180 * np.exp(-((mx - cx - 300) ** 2 + (my - cy + 200) ** 2) / (2 * 1200.0 ** 2))


def e2e_tile_bounds(z, x, y):
    size = WORLD_M / 2 ** z
    minx = -WORLD_M / 2 + x * size
    maxy = WORLD_M / 2 - y * size
    return minx, maxy - size, minx + size, maxy


def merc_to_lonlat(mx, my):
    return math.degrees(mx / 6378137.0), math.degrees(2 * math.atan(math.exp(my / 6378137.0)) - math.pi / 2)


def e2e_tiles():
    """{(z, x, y): (Web Mercator bounds)}: the 2 x 2 block at the top zoom and its parents."""
    top = aligned_block(max(E2E_ZOOMS), *E2E_POINT)
    tiles = list(top)
    for z in E2E_ZOOMS[:-1]:
        shift = max(E2E_ZOOMS) - z
        tiles += sorted({(z, x >> shift, y >> shift) for _, x, y in top})
    return top, tiles


def e2e_values(z, x, y, centre):
    x0, y0, x1, y1 = e2e_tile_bounds(z, x, y)
    res = (x1 - x0) / E2E_SIZE
    mx = x0 + (np.arange(E2E_SIZE) + 0.5) * res
    my = y1 - (np.arange(E2E_SIZE) + 0.5) * res
    gx, gy = np.meshgrid(mx, my)
    return e2e_elevation(gx, gy, centre)


def e2e_extent():
    top, _ = e2e_tiles()
    b = [e2e_tile_bounds(*t) for t in top]
    minx, miny = min(v[0] for v in b), min(v[1] for v in b)
    maxx, maxy = max(v[2] for v in b), max(v[3] for v in b)
    return (minx, miny, maxx, maxy), ((minx + maxx) / 2, (miny + maxy) / 2)


def write_e2e_fixture(folder):
    os.makedirs(folder, exist_ok=True)
    (minx, miny, maxx, maxy), centre = e2e_extent()
    data = {t: encode_png(e2e_values(*t, centre))[0] for t in e2e_tiles()[1]}
    w, s = merc_to_lonlat(minx, miny)
    e, n = merc_to_lonlat(maxx, maxy)
    clon, clat = merc_to_lonlat(*centre)
    meta = {"name": "terrain", "format": "png", "type": "baselayer", "encoding": "mapbox",
            "bounds": f"{w + 1e-6:.7f},{s + 1e-6:.7f},{e - 1e-6:.7f},{n - 1e-6:.7f}",
            "center": f"{clon:.7f},{clat:.7f},{max(E2E_ZOOMS)}",
            "minzoom": str(min(E2E_ZOOMS)), "maxzoom": str(max(E2E_ZOOMS)),
            "attribution": "synthetic test terrain (WP17)"}
    png = os.path.join(folder, "synthetic.png.pmtiles")
    webp = os.path.join(folder, "synthetic.webp.pmtiles")
    for p in (png, webp):
        if os.path.exists(p):
            os.remove(p)
    tmp = tempfile.mkdtemp(prefix="terrain_e2e_")
    try:
        write_pmtiles(png, data, meta, tmp)
        with contextlib.redirect_stdout(io.StringIO()):
            code = T.main([png, "--out", webp, "--steps=-:0", "--workers", "1", "--sample", "0", "--work", tmp])
        if code:
            raise RuntimeError("terrain_reencode failed on the e2e fixture")
    finally:
        shutil.rmtree(tmp)
    # Points to sample, in the middle of the block (inside the fixture's view).
    points = []
    for fy in (0.3, 0.4, 0.5, 0.6, 0.7):
        for fx in (0.3, 0.4, 0.5, 0.6, 0.7):
            mx, my = minx + fx * (maxx - minx), maxy - fy * (maxy - miny)
            lon, lat = merc_to_lonlat(mx, my)
            points.append([round(lon, 7), round(lat, 7), round(float(e2e_elevation(mx, my, centre)), 3)])
    info = {
        "about": "Synthetic terrain-RGB for the WP17 e2e spec, made by basemap/test_terrain_reencode.py "
                 "--write-e2e-fixture. Not real elevation data.",
        "png": os.path.basename(png), "webp": os.path.basename(webp), "tileSize": E2E_SIZE,
        "bounds": [round(v, 7) for v in (w, s, e, n)], "center": [round(clon, 7), round(clat, 7)],
        "zoom": max(E2E_ZOOMS), "points": points,
    }
    with open(os.path.join(folder, "synthetic.json"), "w") as f:
        json.dump(info, f, indent=1)
        f.write("\n")
    return info


# --- PMTiles -------------------------------------------------------------------------------------

class TileIdTest(unittest.TestCase):
    def test_known_ids(self):
        # The values in the PMTiles spec's reference tests.
        self.assertEqual(T.zxy_to_tileid(0, 0, 0), 0)
        self.assertEqual(T.zxy_to_tileid(1, 0, 0), 1)
        self.assertEqual(T.zxy_to_tileid(1, 0, 1), 2)
        self.assertEqual(T.zxy_to_tileid(1, 1, 1), 3)
        self.assertEqual(T.zxy_to_tileid(1, 1, 0), 4)
        self.assertEqual(T.zxy_to_tileid(2, 0, 0), 5)
        self.assertEqual(T.tileid_to_zxy(19078479), (12, 3423, 1763))

    def test_round_trip(self):
        for z in range(0, 7):
            seen = set()
            for x in range(2 ** z):
                for y in range(2 ** z):
                    tid = T.zxy_to_tileid(z, x, y)
                    self.assertEqual(T.tileid_to_zxy(tid), (z, x, y))
                    seen.add(tid)
            # Each zoom fills the IDs after all lower zooms, with no gaps.
            start = ((1 << (2 * z)) - 1) // 3
            self.assertEqual(seen, set(range(start, start + 4 ** z)))
        rng = random.Random(5)
        for _ in range(2000):
            z = rng.randint(7, 20)
            x, y = rng.randrange(2 ** z), rng.randrange(2 ** z)
            self.assertEqual(T.tileid_to_zxy(T.zxy_to_tileid(z, x, y)), (z, x, y))

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            T.zxy_to_tileid(2, 4, 0)

    def test_directory(self):
        # Two tiles back to back (second offset written as 0 = "right after"), and a leaf pointer.
        def varint(n):
            out = bytearray()
            while True:
                b = n & 0x7F
                n >>= 7
                out.append(b | (0x80 if n else 0))
                if not n:
                    return bytes(out)
        raw = (varint(3) + varint(5) + varint(1) + varint(10)         # ids 5, 6, 16
               + varint(1) + varint(2) + varint(0)                    # runs (0 = leaf)
               + varint(100) + varint(50) + varint(70)                # lengths
               + varint(1) + varint(0) + varint(201))                 # offsets + 1, 0 = contiguous
        self.assertEqual(T.parse_directory(raw), [(5, 0, 100, 1), (6, 100, 50, 2), (16, 200, 70, 0)])


class StepsTest(unittest.TestCase):
    def test_default(self):
        steps = T.parse_steps(T.DEFAULT_STEPS)
        self.assertEqual([T.step_units(steps, z) for z in range(6, 16)], [10] * 5 + [5, 4, 2, 0, 0])
        self.assertEqual(T.describe_steps(steps, 6, 14),
                         "1 m at z6-10, 0.5 m at z11, 0.4 m at z12, 0.2 m at z13, unrounded at z14")
        # Every default step divides 10,000 m, so rounded heights stay on whole multiples.
        self.assertTrue(all(units == 0 or T.OFFSET_UNITS % units == 0 for *_, units in steps))

    def test_bad(self):
        for text in ("6-11:0.25", "6-11:-1", "6-11:1,10-12:0.5", "x:1", "12-6:1", "6-11:0.3"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                T.parse_steps(text)
        with self.assertRaises(ValueError):
            T.step_units(T.parse_steps("6-11:1"), 12)

    def test_unrounded(self):
        steps = T.parse_steps("-:0")
        self.assertEqual(T.step_units(steps, 14), 0)
        self.assertEqual(T.describe_steps(steps, 6, 14), "unrounded at z6-14")

    def test_half_step_rule(self):
        self.assertTrue(T.within_half_step(5, 10))
        self.assertFalse(T.within_half_step(6, 10))
        self.assertTrue(T.within_half_step(2, 5))
        self.assertFalse(T.within_half_step(3, 5))
        self.assertTrue(T.within_half_step(0, 0))
        self.assertFalse(T.within_half_step(1, 0))


# --- tiles ---------------------------------------------------------------------------------------

@needs_gdal
class RoundingTest(unittest.TestCase):
    def test_error_is_at_most_half_a_step(self):
        rng = np.random.default_rng(1)
        v = rng.integers(90000, 160000, size=(256, 256)).astype(np.uint32)   # -1000 m .. 6000 m
        for units in (2, 5, 10, 20):
            r = T.round_units(v, units)
            err = np.abs(r.astype(np.int64) - v.astype(np.int64))
            self.assertLessEqual(int(err.max()), units // 2, units)
            self.assertFalse(np.any(r % units))
            # Whole metres stay whole metres: rounding is relative to 0 m, not to the encoding's offset.
            if units == 10:
                self.assertFalse(np.any(T.units_to_metres(r) % 1.0))
            order = np.argsort(v, axis=None)
            self.assertTrue(np.all(np.diff(r.ravel()[order].astype(np.int64)) >= 0), "monotonic")

    def test_rgb_round_trip(self):
        v = np.random.default_rng(2).integers(0, 2 ** 24, size=(64, 64)).astype(np.uint32)
        v[0, :3] = (0, 2 ** 24 - 1, 100000)
        self.assertTrue(np.array_equal(T.rgb_to_units(T.units_to_rgb(v)), v))

    def test_tile_reencodes_to_webp(self):
        elev = synthetic_elevation(12, 760, 1490)
        png, v = encode_png(elev)
        for units, limit in ((10, 5), (5, 2), (2, 1), (0, 0)):
            with self.subTest(units=units):
                webp, err = T.reencode_tile(png, units)
                self.assertEqual(webp[:4], b"RIFF")
                self.assertEqual(webp[8:12], b"WEBP")
                self.assertLessEqual(err, limit)
                back = T.rgb_to_units(T.decode_rgb(webp))
                self.assertEqual(back.shape, (512, 512))
                self.assertEqual(int(np.abs(back.astype(np.int64) - v.astype(np.int64)).max()), err)
                if units == 0:
                    self.assertTrue(np.array_equal(back, v), "no rounding means lossless")
        # Rounding is what makes it small: 1 m tiles are smaller than unrounded ones.
        self.assertLess(len(T.reencode_tile(png, 10)[0]), len(T.reencode_tile(png, 0)[0]))


# --- end to end ----------------------------------------------------------------------------------

@needs_cli
class ReencodeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="terrain_reencode_")
        self.addCleanup(shutil.rmtree, self.dir)
        self.src, self.values = make_input(self.dir)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = T.main(list(args))
        return code, out.getvalue()

    def test_reencode(self):
        src = T.PMTiles(self.src)
        self.assertLess(src.header["tile_contents"], src.header["addressed_tiles"], "fixture has a run")
        self.assertTrue(any(run > 1 for *_, run in src.entries()), "an entry with run_length > 1")
        out = os.path.join(self.dir, "terrain-webp-test.pmtiles")
        man = os.path.join(self.dir, "manifest-webp.json")
        steps = "-6:1,7:0.5,8-:0.2"
        code, log = self.run_main(self.src, "--out", out, f"--steps={steps}", "--manifest-out", man,
                                  "--workers", "2", "--sample", "0", "--report", os.path.join(self.dir, "r.json"))
        self.assertEqual(code, 0, log)
        self.assertIn("OK", log)
        self.assertFalse(os.path.exists(out + ".part"))
        self.assertFalse([f for f in os.listdir(self.dir) if f.endswith(".mbtiles")], "work file removed")

        dst = T.PMTiles(out)
        hs, ho = src.header, dst.header
        # The same tiles, zooms and place; WebP now.
        self.assertEqual(set(src.tile_ids()), set(dst.tile_ids()))
        for k in ("addressed_tiles", "minzoom", "maxzoom", "bounds_e7", "center_zoom", "center_e7"):
            self.assertEqual(hs[k], ho[k], k)
        self.assertEqual(T.TILE_TYPES[ho["tile_type"]], "webp")
        self.assertEqual(dst.metadata, dict(src.metadata, format="webp"))
        subprocess.run(["pmtiles", "verify", out], check=True, capture_output=True)

        # Every tile decodes, within half a step of the original values.
        limits = {6: 5, 7: 2, 8: 1}
        for tid, (off, ln) in dst.tile_ids().items():
            z, x, y = T.tileid_to_zxy(tid)
            got = T.rgb_to_units(T.decode_rgb(dst.read_at(off, ln)))
            want = self.values[(z, x, y)]
            err = int(np.abs(got.astype(np.int64) - want.astype(np.int64)).max())
            self.assertLessEqual(err, limits[z], f"{z}/{x}/{y}")
            self.assertEqual(dst.get(z, x, y), dst.read_at(off, ln))

        report = load_json(os.path.join(self.dir, "r.json"))
        self.assertTrue(report["ok"])
        self.assertEqual(report["checked"], hs["addressed_tiles"])
        self.assertEqual(report["per_zoom_all"]["7"]["step_m"], 0.5)

        # The manifest copy points at the new file; the original is untouched.
        m = load_json(man)
        self.assertEqual(m["terrain"]["file"], "terrain-webp-test.pmtiles")
        self.assertEqual(m["terrain"]["format"], "webp")
        self.assertEqual(m["terrain"]["rounding"], "1 m at z6, 0.5 m at z7, 0.2 m at z8")
        self.assertEqual(m["terrain"]["encoding"], "mapbox")
        self.assertEqual(load_json(os.path.join(self.dir, "manifest.json"))["terrain"]["file"],
                         "terrain.pmtiles")

        # A check of the finished file on its own agrees; a wrong step makes it fail.
        code, log = self.run_main(self.src, "--check", out, f"--steps={steps}", "--sample", "5")
        self.assertEqual(code, 0, log)
        code, log = self.run_main(self.src, "--check", out, "--steps=-:0", "--sample", "0")
        self.assertEqual(code, 1)
        self.assertIn("more than half", log)

    def test_check_catches_a_swapped_tile(self):
        out = os.path.join(self.dir, "terrain-webp-swap.pmtiles")
        code, log = self.run_main(self.src, "--out", out, "--workers", "1", "--steps=-:1")
        self.assertEqual(code, 0, log)
        # Build a broken copy: two different z7 tiles trade places.
        dst = T.PMTiles(out)
        ids = dst.tile_ids()
        z7 = [t for t in ids if T.tileid_to_zxy(t)[0] == 7]
        a, b = z7[0], z7[1]
        mbtiles = os.path.join(self.dir, "broken.mbtiles")
        db = sqlite3.connect(mbtiles)
        db.executescript("create table metadata (name text, value text);"
                         "create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);")
        meta = T.mbtiles_metadata(dst)
        db.executemany("insert into metadata values (?, ?)", meta.items())
        for tid, (off, ln) in ids.items():
            src_tid = {a: b, b: a}.get(tid, tid)
            z, x, y = T.tileid_to_zxy(tid)
            db.execute("insert into tiles values (?, ?, ?, ?)", (z, x, 2 ** z - 1 - y, dst.read_at(*ids[src_tid])))
        db.commit()
        db.close()
        broken = os.path.join(self.dir, "broken.pmtiles")
        subprocess.run(["pmtiles", "convert", "--quiet", f"--tmpdir={self.dir}", mbtiles, broken], check=True)
        code, log = self.run_main(self.src, "--check", broken, "--steps=-:1", "--sample", "0")
        self.assertEqual(code, 1)
        self.assertIn("more than half", log)

    def test_refuses_to_overwrite(self):
        out = os.path.join(self.dir, "exists.pmtiles")
        open(out, "w").close()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            T.main([self.src, "--out", out])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            T.main([self.src, "--out", self.src])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            T.main([self.src, "--out", os.path.join(self.dir, "new.pmtiles"),
                    "--manifest-out", os.path.join(self.dir, "manifest.json")])
        self.assertEqual(os.path.getsize(out), 0)

    def test_default_name_is_versioned(self):
        code, log = self.run_main(self.src, "--workers", "1", "--sample", "3")
        self.assertEqual(code, 0, log)
        made = [f for f in os.listdir(self.dir) if f.startswith("terrain-webp-")]
        self.assertEqual(len(made), 1)
        self.assertRegex(made[0], r"^terrain-webp-\d{8}\.pmtiles$")


@needs_gdal
class E2EFixtureTest(unittest.TestCase):
    """The committed browser fixture is what the generator above describes."""

    def test_fixture(self):
        info = load_json(os.path.join(E2E_DIR, "synthetic.json"))
        png = T.PMTiles(os.path.join(E2E_DIR, info["png"]))
        webp = T.PMTiles(os.path.join(E2E_DIR, info["webp"]))
        self.assertEqual(T.TILE_TYPES[png.header["tile_type"]], "png")
        self.assertEqual(T.TILE_TYPES[webp.header["tile_type"]], "webp")
        _, centre = e2e_extent()
        ids = png.tile_ids()
        self.assertEqual(sorted(ids), sorted(T.zxy_to_tileid(*t) for t in e2e_tiles()[1]))
        self.assertEqual(set(ids), set(webp.tile_ids()))
        for tid, at in ids.items():
            z, x, y = T.tileid_to_zxy(tid)
            a = T.rgb_to_units(T.decode_rgb(png.read_at(*at)))
            b = T.rgb_to_units(T.decode_rgb(webp.read_at(*webp.tile_ids()[tid])))
            self.assertTrue(np.array_equal(a, b), f"{z}/{x}/{y}: WebP isn't lossless")
            want = np.round((e2e_values(z, x, y, centre) + 10000) * 10).astype(np.uint32)
            self.assertTrue(np.array_equal(a, want), f"{z}/{x}/{y}: not the formula")
        self.assertLess(os.path.getsize(png.path) + os.path.getsize(webp.path), 200_000, "keep it small")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-e2e-fixture":
        print(json.dumps(write_e2e_fixture(sys.argv[2]), indent=1))
    else:
        unittest.main()
