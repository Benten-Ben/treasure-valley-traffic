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


def make_input(folder, size=128, zooms=(6, 7, 8)):
    """A small terrain-RGB PMTiles like terrain.py's (MBTiles, then pmtiles convert), plus a
    manifest. Two top-zoom tiles that follow each other on the Hilbert curve are identical, so
    the archive has a run (run_length 2) for the reader to expand."""
    mbtiles = os.path.join(folder, "in.mbtiles")
    db = sqlite3.connect(mbtiles)
    db.executescript("create table metadata (name text, value text);"
                     "create table tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob);")
    meta = {"name": "terrain", "format": "png", "type": "baselayer", "encoding": "mapbox",
            "bounds": "-116.6,43.4,-116.0,43.8", "center": "-116.3,43.6,7",
            "minzoom": str(min(zooms)), "maxzoom": str(max(zooms)),
            "attribution": "synthetic test terrain"}
    db.executemany("insert into metadata values (?, ?)", meta.items())
    # Per zoom, the 2 x 2 block (aligned to even tile numbers) around Boise. The Hilbert curve
    # visits such a block's four tiles one after another, so two of them can form a run.
    tiles = []
    for z in zooms:
        xs, ys = tile_range(z, -116.2, 43.6, -116.2, 43.6)
        x0, y0 = xs[0] & ~1, ys[0] & ~1
        tiles += [(z, x, y) for x in (x0, x0 + 1) for y in (y0, y0 + 1)]
    ids = sorted(T.zxy_to_tileid(*t) for t in tiles if t[0] == max(zooms))
    flat = {T.tileid_to_zxy(t) for t in ids[1:3]}
    values = {}
    for z, x, y in tiles:
        elev = np.full((size, size), 812.34) if (z, x, y) in flat else synthetic_elevation(z, x, y, size)
        data, v = encode_png(elev)
        values[(z, x, y)] = v
        db.execute("insert into tiles values (?, ?, ?, ?)", (z, x, 2 ** z - 1 - y, data))
    db.commit()
    db.close()
    pm = os.path.join(folder, "terrain.pmtiles")
    subprocess.run(["pmtiles", "convert", "--quiet", f"--tmpdir={folder}", mbtiles, pm], check=True)
    os.remove(mbtiles)
    manifest = {"bounds": [-117.05, 43.0, -115.95, 43.85], "zoom": 10,
                "terrain": {"file": "terrain.pmtiles", "encoding": "mapbox", "tileSize": size,
                            "exaggeration": 1.3, "built": "2026-10-05", "attribution": "USGS 3DEP",
                            "source": "synthetic"}}
    with open(os.path.join(folder, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    return pm, values


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
        self.assertEqual([T.step_units(steps, z) for z in range(6, 16)], [10] * 6 + [5, 5, 2, 2])
        self.assertEqual(T.describe_steps(steps, 6, 14), "1 m at z6-11, 0.5 m at z12-13, 0.2 m at z14")

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


if __name__ == "__main__":
    unittest.main()
