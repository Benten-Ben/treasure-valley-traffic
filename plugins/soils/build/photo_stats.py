#!/usr/bin/env python3
"""The soil photo statistics and the 2 m NAIP COG (plan P2, C8; the soils design, build step 3). Worker image (GDAL,
NumPy, SciPy), plus LizardTech's MrSID Decode SDK for the county mosaics: internal use only, mounted read-only at
run time (--dsdk), never in this repository, and run with no network (basemap/README.md).

    python plugins/soils/build/photo_stats.py run --out $TVT_ARCHIVE/soils/photo/<build> --cog <a cold-drive folder> \\
        --naip ada=DIR/ortho_..._id001_2025_1.sid --naip canyon=DIR/ortho_..._id027_2025_1.sid --dsdk /dsdk ...
    python plugins/soils/build/photo_stats.py calibrate --out <the same build> ...      # the ten boxes
    python plugins/soils/build/photo_stats.py finish --out <the same build>            # pool, checks, the COG

**run** walks the ground's 2 m grid in windows of CORE_M (1,024 m), each read with a HALO_M (64 m) margin. For each
window it decodes each county mosaic's part at 0.6 m (`mrsiddecode -s 1`, half the 0.3 m resolution) into /tmp (a
tmpfs), and
- gives each pixel to one mosaic: the two county mosaics reach a few kilometres past their county lines and overlap
  by about 390 km2 along the Ada/Canyon line, so a pixel in a county's survey area (soils' areasymbol: ID001 Ada,
  ID665 Canyon) is served by that county's mosaic, and one in neither county by the nearest county's (owner_grid);
  the other mosaic serves it only where the first doesn't cover it;
- puts each flight day's colour on the reference day's scale (--gains: photo.Gains, from same-day Sentinel-2);
- marks the pixels that are uncovered ground, the 'photo-v1' mask (photo.py's rules): inside a soil polygon and at
  least 10 m from its edge; outside mask v0's `covered` (roofs + 1 m, roads + 2 m, paving, water + 5 m, rail,
  aeroways, CDL 2025's developed land); not green (the photo's NDVI put on Sentinel-2's scale by its flight day's
  curve, under 0.45, and the July 2025 Sentinel-2 median under 0.30); not shadow or asphalt; and inside crop fields
  only row crops and fallow (farm's crop_cover and fields);
- adds them up per (map unit, flight day) and per soil polygon: OKLab sums, cross-products and histograms, and the
  texture energy of L and chroma in five octaves (photo.py);
- averages the window onto the 2 m grid (the photo's red, green and blue on the reference day's scale, and its NDVI
  on Sentinel-2's scale), for the COG G1b reads.
It writes `windows/<key>.npz` and `<cog>/parts/<key>.tif`, then deletes the decoded window, so a run stopped by its
deadline resumes where it stopped (run it again with the same --out; `--limit N` does N windows at a time). It uses
--workers processes (3 for `--cpus 3`), each holding one window (about 0.6 GB) and its decoded copy in /tmp (about
20 MB): 1.8 GB in all, measured. The valley is 5,159 windows (452 of them in both counties), about 1.8 s each with
three workers.

**calibrate** measures the mask's bias in the ten land-cover boxes: in each box's 500 m class window (the spike's
"as of July" classes, exp31) it compares, per ground type, the photo-v1 median with the median under the class mask
(flat and not green, or pale surfaced: short dry grass and pale surfaced cells; not hard things, trees, shrubs or
their filled floor). It passes when the median dE over (box, type) pairs is CAL_PASS (3) or less. Boxes h, i and j
have no NAIP 2025: they're measured on their NAIP 2023 crops (0.6 m) with the 2023 curve. In a build folder it uses
the run's own inputs, gains and rules (run.json), and records them in calibration.json; finish takes a calibration
only when they match the run's.

**finish** adds the windows up, pools them to ground types with the fallbacks (pool.py), writes `stats.json` (the
rows `python3 -m ingest soils-photo-load --build DIR` loads), `report.json` (the checks), and assembles the COG:

    <cog>/naip2025_2m.tif    4 bands, uint8, on the ground's 2 m grid (EPSG:32611), over the parts' extent (Ada and
                             Canyon, cut to the grid), DEFLATE, 512 px tiles, no overviews, an internal mask (cells at
                             least half covered by Ada's or Canyon's mosaic):
                             1-3 red, green and blue, the area mean of the 0.6 m DNs (on the reference flight day's
                             scale when the run had gains); 4 ndvi, the photo's NDVI on
                             Sentinel-2's scale by its flight day's curve, coded 1..255 for -1..+1 (photo.encode_ndvi;
                             0 where no flight polygon covers it)
    <cog>/naip2025_2m.json   what it is: bands, coding, grid, flight days, sources and credits, sha256
    <cog>/flights.fgb        the NAIP 2025 flight polygons (USDA's seamlines in the box, EPSG:32611): src_fid, idate
                             (the flight day), sdate and edate (local time), camera; for the sun angle G1b normalises
                             by (C8)

report.json's `flight_days` says how far the same type's colour still differs between flight days, and how far the
flights themselves are apart (`pair_offsets`), after the gains when the run had them.
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
for _p in (_ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
from osgeo import gdal, ogr, osr  # noqa: E402

from basemap.ground import grid as G  # noqa: E402
from basemap.ground import manifest as M  # noqa: E402
from basemap.ground import mask as MK  # noqa: E402
from basemap.ground import rasterize as R  # noqa: E402   (also switches PROJ's network off)

import photo as P  # noqa: E402
import lidar_vintage as LV  # noqa: E402
import pool as PL  # noqa: E402

gdal.UseExceptions()
ogr.UseExceptions()

FORMAT = "tvt-soils-photo/1"
COG_FORMAT = "tvt-naip-2m/1"
RES = 0.6                  # the photo is read at 0.6 m (MrSID scale 1: half the mosaics' 0.3 m)
CORE_M = 1024.0            # a window's core, metres (512 cells of the 2 m grid)
ALIGN = 32                 # decoded windows start on multiples of 32 pixels, so the texture pyramid's coarse pixels
                           # (up to 16 pixels) fall on the same lattice in every window
PAINTER = G.LEVELS["painter"]
COG_NAME = "naip2025_2m.tif"
CAL_PASS = 3.0             # the ten-box calibration passes at a median dE of this or less
CAL_MIN_PX = 2000          # a (box, type) pair is compared when both masks hold this many pixels (720 m2)
CLASS_KEEP = (9, 12, 14)   # exp31's classes: flat, not green; short dry grass; surfaced, pale
CLASS_RES = 0.5
COUNTY_AREAS = {"ada": "ID001", "canyon": "ID665"}       # each county mosaic's own survey area
OWNER_RES = 20.0           # the grid that gives a place in neither county to the nearest county's mosaic (owner_grid)
NAIP_CREDIT = "USDA NAIP 2025 (public domain)"


class StatsError(RuntimeError):
    pass


def log(msg):
    print(f"{datetime.now(timezone.utc):%H:%M:%S} {msg}", flush=True)


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, obj):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


# ---- the photo ----------------------------------------------------------------------------------------------------

class Mosaic:
    """A NAIP raster read at 0.6 m in windows: name, the corner (x0, y0) of its pixel (0, 0), size, CRS."""
    res = RES

    def __init__(self, name, x0, y0, width, height, crs):
        self.name, self.x0, self.y0, self.width, self.height, self.crs = name, x0, y0, width, height, crs

    def region(self, bounds, align=ALIGN):
        """(col, row, width, height) of the pixels covering bounds (west, south, east, north), its start on
        multiples of `align`, clipped to the raster; None when it doesn't reach."""
        w, s, e, n = bounds
        c0 = int(np.floor((w - self.x0) / self.res)) // align * align
        r0 = int(np.floor((self.y0 - n) / self.res)) // align * align
        c1 = int(np.ceil((e - self.x0) / self.res))
        r1 = int(np.ceil((self.y0 - s) / self.res))
        c1 = -(-c1 // align) * align
        r1 = -(-r1 // align) * align
        c0, r0 = max(c0, 0), max(r0, 0)
        c1, r1 = min(c1, self.width), min(r1, self.height)
        if c1 <= c0 or r1 <= r0:
            return None
        return c0, r0, c1 - c0, r1 - r0

    def transform(self, col, row):
        return (self.x0 + col * self.res, self.res, 0.0, self.y0 - row * self.res, 0.0, -self.res)

    def covers(self, bounds):
        return True


class SidMosaic(Mosaic):
    """A county mosaic (MrSID MG4: red, green, blue, near-infrared and the mosaic's mask), read with the SDK's
    mrsiddecode at scale 1 (0.6 m). The mask is the county plus a buffer of a few kilometres, not the county (Ada's
    covers about 3,630 km2, the county 2,747): Context.serves splits the overlap on the county line. The SDK runs
    from --dsdk, with its own libraries."""

    def __init__(self, name, path, dsdk, tmp, cache=None):
        self.path, self.dsdk, self.tmp, self.cache = path, dsdk, tmp, cache
        info = self._run([os.path.join(dsdk, "bin", "mrsidinfo"), "-i", path]).stdout
        get = {k: float(re.search(rf"^\s*{k}:\s*([-\d.]+)", info, re.M).group(1))
               for k in ("width", "height", "X UL", "Y UL", "X res", "Y res", "nband")}
        if get["nband"] != 5:
            raise StatsError(f"{path}: {get['nband']:g} bands; NAIP's county mosaics have 5 (the mask is band 5)")
        full = get["X res"]
        # mrsidinfo gives pixel centres; at scale 1 a pixel is 2 x 2 of the full ones, from the same corner.
        x0, y0 = get["X UL"] - full / 2, get["Y UL"] - get["Y res"] / 2
        if abs(2 * full - RES) > 1e-6:
            raise StatsError(f"{path}: {full} m pixels; P2 reads 0.3 m mosaics at 0.6 m")
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(26911)
        super().__init__(name, x0, y0, int(np.ceil(get["width"] / 2)), int(np.ceil(get["height"] / 2)),
                         srs.ExportToWkt())
        self.full_size = (int(get["width"]), int(get["height"]))
        self.version = self._run([os.path.join(dsdk, "bin", "mrsiddecode"), "-v"]).stdout.strip().splitlines()[0]
        self._overview = None

    def _run(self, args):
        env = dict(os.environ, LD_LIBRARY_PATH=f"{self.dsdk}/lib:{self.dsdk}/bin")
        r = subprocess.run(args, env=env, capture_output=True, text=True)
        if r.returncode:
            raise StatsError(f"{os.path.basename(args[0])} failed ({r.returncode}): {r.stderr.strip()[-500:]}")
        return r

    def decode(self, col, row, width, height, scale=1):
        out = os.path.join(self.tmp, f"{self.name}-{os.getpid()}-{col}-{row}.tif")
        try:
            self._run([os.path.join(self.dsdk, "bin", "mrsiddecode"), "-quiet", "-j", "1", "-i", self.path,
                       "-o", out, "-of", "tifg", "-coord", "image", "-ulxy", str(col), str(row),
                       "-wh", str(width), str(height), "-s", str(scale)])
            gdal.PushErrorHandler("CPLQuietErrorHandler")     # "ExtraSamples" (the decoder's band 4 labelling)
            try:
                ds = gdal.Open(out)
                arr = ds.ReadAsArray()
                gt = ds.GetGeoTransform()
                ds = None
            finally:
                gdal.PopErrorHandler()
        finally:
            if os.path.exists(out):
                os.remove(out)
        return arr, gt

    def read(self, col, row, width, height):
        arr, gt = self.decode(col, row, width, height)
        want = self.transform(col, row)
        if arr.shape != (5, height, width) or abs(gt[0] - want[0]) > 0.01 or abs(gt[3] - want[3]) > 0.01:
            raise StatsError(f"{self.name}: decoded {arr.shape} at {gt[0]:.2f}, {gt[3]:.2f}; wanted "
                             f"{(5, height, width)} at {want[0]:.2f}, {want[3]:.2f}")
        return arr

    def covers(self, bounds):
        """Whether the mosaic's mask has any pixel in bounds (from the mosaic decoded at 1/32, 9.6 m)."""
        if self._overview is None:
            path = os.path.join(self.cache, f"overview-{self.name}.npz") if self.cache else None
            if path and os.path.exists(path):
                with np.load(path) as z:
                    self._overview = (z["mask"], tuple(z["gt"]))
            else:
                arr, gt = self.decode(0, 0, -(-self.full_size[0] // 32), -(-self.full_size[1] // 32), scale=5)
                self._overview = (arr[4] > 0, gt)
                if path:
                    np.savez_compressed(path + ".part.npz", mask=self._overview[0], gt=np.array(gt))
                    os.replace(path + ".part.npz", path)
        m, gt = self._overview
        w, s, e, n = bounds
        c0, c1 = int((w - gt[0]) // gt[1]) - 1, int((e - gt[0]) // gt[1]) + 2
        r0, r1 = int((gt[3] - n) // -gt[5]) - 1, int((gt[3] - s) // -gt[5]) + 2
        c0, r0 = max(c0, 0), max(r0, 0)
        return bool(m[r0:max(r1, r0), c0:max(c1, c0)].any())


class TiffMosaic(Mosaic):
    """A GeoTIFF with red, green, blue and near-infrared bands (and a fifth, the mask, if it has one; otherwise
    every pixel counts) at 0.6 m: NAIP 2023's crops for boxes h-j, and the tests' synthetic county."""

    def __init__(self, name, path):
        ds = gdal.Open(path)
        gt = ds.GetGeoTransform()
        if abs(gt[1] - RES) > 1e-6 or abs(gt[5] + RES) > 1e-6:
            raise StatsError(f"{path}: {gt[1]} m pixels; this reads 0.6 m")
        if ds.RasterCount not in (4, 5):
            raise StatsError(f"{path}: {ds.RasterCount} bands; expected R, G, B, NIR (and a mask)")
        self.path = path
        self.version = os.path.basename(path)
        super().__init__(name, gt[0], gt[3], ds.RasterXSize, ds.RasterYSize, ds.GetProjection())

    def read(self, col, row, width, height):
        ds = gdal.Open(self.path)
        arr = ds.ReadAsArray(col, row, width, height)
        if arr.shape[0] == 4:
            arr = np.concatenate([arr, np.full((1, height, width), 255, np.uint8)])
        return arr

    def covers(self, bounds):
        w, s, e, n = bounds
        return not (e <= self.x0 or w >= self.x0 + self.width * RES or n <= self.y0 - self.height * RES
                    or s >= self.y0)


# ---- the inputs ---------------------------------------------------------------------------------------------------

def read_flights(path):
    """{src_fid: (flight day, local start)} from naip_norm's flights_mapbox.gpkg (USDA's seamlines in the box)."""
    ds = ogr.Open(path)
    lyr = ds.GetLayer(0)
    out = {}
    for f in lyr:
        out[int(f.GetField("src_fid"))] = (f.GetField("idate"), f.GetField("sdate"), f.GetField("edate"))
    return out


def read_soils(folder, hashes=True):
    """The soils export (P1-data): its manifest, ground.fgb's polygons (gid, mukey, ground_type gid, areasymbol, misc)
    and ground_types.json. Returns a dict with the map units in key order and the lookups the windows need."""
    m = M.read(folder, hashes=hashes)
    if m.plugin != "soils" or not m.has("ground") or not m.has("ground_types"):
        raise StatsError(f"{folder}: not a soils export with ground and ground_types")
    with open(m.layer("ground_types").path, encoding="utf-8") as f:
        gt = json.load(f)
    by_gid = {t["gid"]: t for t in gt["types"]}
    ds = ogr.Open(m.layer("ground").path)
    lyr = ds.GetLayer(0)
    lyr.SetIgnoredFields(["OGR_GEOMETRY"])
    has_area = lyr.GetLayerDefn().GetFieldIndex("areasymbol") >= 0
    polys = []
    for f in lyr:
        polys.append((int(f.GetField("id")), f.GetField("mukey"), int(f.GetField("ground_type") or 0),
                      f.GetField("areasymbol") if has_area else None))
    ds = None
    mukeys = sorted({p[1] for p in polys})
    mu_index = {k: i for i, k in enumerate(mukeys)}
    mu_type = {}
    for gid_poly, mukey, tg, _ in polys:
        t = by_gid.get(tg)
        mu_type[mukey] = t["id"] if t else None
    areas = sorted({p[3] for p in polys if p[3]})
    area_index = {a: i for i, a in enumerate(areas)}
    gids = np.array([p[0] for p in polys], np.int64)
    pid_mu = np.full(int(gids.max()) + 1 if len(gids) else 1, -1, np.int32)
    pid_mu[gids] = [mu_index[p[1]] for p in polys]
    pid_area = np.full(len(pid_mu), -1, np.int16)          # the polygon's survey area (an index into areas), -1 none
    pid_area[gids] = [area_index.get(p[3], -1) for p in polys]
    pid_row = np.full(len(pid_mu), -1, np.int32)
    order = np.argsort(gids)
    pid_row[gids[order]] = np.arange(len(gids))
    types = {t["id"]: {k: t.get(k) for k in ("gid", "series", "texcl", "landform", "albedo_dry", "misc")}
             for t in gt["types"]}
    return {"manifest": m, "ground": m.layer("ground"), "mapunits": [{"mukey": k, "type": mu_type[k]} for k in mukeys],
            "types": types, "pid_mu": pid_mu, "pid_row": pid_row, "poly_gid": gids[order],
            "poly_mu": pid_mu[gids[order]], "has_landform": any("landform" in t for t in gt["types"]),
            "areas": areas if has_area else None, "pid_area": pid_area}


def field_drop_lut():
    """bool[256]: CDL codes whose crop fields aren't sampled (photo.FIELD_DROP_GROUPS), from farm's classes."""
    from plugins.farm.ingest import classes as C
    cls = C.read()
    lut = np.zeros(65536, bool)
    for code, c in cls.items():
        lut[code] = c["grp"] in P.FIELD_DROP_GROUPS
    return lut


def sample10(path, target, band=1):
    """A 10 m raster on the ground's grid (the July median, crop_cover), sampled at each pixel centre of target.
    Returns (values, inside) as arrays of target.shape."""
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    if not G.aligned(gt, G.BASE_RES):
        raise StatsError(f"{path} isn't on the ground's 10 m grid")
    x0, rx, _, y0, _, ry = target.transform
    xs = x0 + (np.arange(target.width) + 0.5) * rx
    ys = y0 + (np.arange(target.height) + 0.5) * ry
    cols = np.floor((xs - gt[0]) / gt[1]).astype(np.int64)
    rows = np.floor((gt[3] - ys) / -gt[5]).astype(np.int64)
    c0, c1 = max(int(cols.min()), 0), min(int(cols.max()) + 1, ds.RasterXSize)
    r0, r1 = max(int(rows.min()), 0), min(int(rows.max()) + 1, ds.RasterYSize)
    if c1 <= c0 or r1 <= r0:
        return np.zeros(target.shape, np.float64), np.zeros(target.shape, bool)
    sub = ds.GetRasterBand(band).ReadAsArray(c0, r0, c1 - c0, r1 - r0)
    ci, ri = cols - c0, rows - r0
    okc = (ci >= 0) & (ci < c1 - c0)
    okr = (ri >= 0) & (ri < r1 - r0)
    v = sub[np.clip(ri, 0, r1 - r0 - 1)][:, np.clip(ci, 0, c1 - c0 - 1)]
    return v, okr[:, None] & okc[None, :]


class Context:
    """Everything a window needs, loaded once per process."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.soils = read_soils(cfg["soils"], hashes=False)
        self.mask = MK.check(M.read(cfg["mask"], hashes=False))
        farm = M.read(cfg["farm"], hashes=False)
        self.crop_cover = farm.layer("crop_cover").path
        self.fields = farm.layer("fields").path
        self.july = cfg["july"]
        self.flights_path = cfg["flights"]
        flights = read_flights(cfg["flights"])
        self.days = cfg["days"]
        fid_max = max(flights) if flights else 0
        self.fid_flight = np.zeros(fid_max + 1, np.uint8)
        for fid, (day, _, _) in flights.items():
            if day in self.days:
                self.fid_flight[fid] = self.days.index(day) + 1
        with open(cfg["fits"], encoding="utf-8") as f:
            fits = json.load(f)
        days = fits["naip2025"]["days"]
        self.curves = [P.Curve(days[d]["curve"]["lut_x"], days[d]["curve"]["lut_y"], d) for d in self.days]
        pooled = fits["naip2023_boxes_h_i_j"]["pooled_curve"]
        self.curve_2023 = P.Curve(pooled["lut_x"], pooled["lut_y"], "2023 pooled")
        self.gains = None
        if cfg.get("gains"):
            with open(cfg["gains"], encoding="utf-8") as f:
                self.gains = P.Gains(json.load(f), self.days)
        self.code_drop = field_drop_lut()
        self.nf = len(self.days)
        self.nkeys = len(self.soils["mapunits"]) * self.nf
        self.owner = None
        self.area_mosaic = np.full(1, -1, np.int8)

    def set_mosaics(self, mosaics):
        """Which mosaic serves a place where the county mosaics overlap (owner_grid; the run computes it first)."""
        self.owner = owner_grid(self.soils, mosaics, self.cfg.get("cache"))
        areas = self.soils["areas"] or []
        am = np.full(len(areas) + 1, -1, np.int8)              # the last entry answers area -1 (none): -1
        for i, area in enumerate(county_of(mosaics)):
            if area in areas:
                am[areas.index(area)] = i
        self.area_mosaic = am

    def polygons(self, target):
        """The soil polygon (soils.polygon.gid, 0 none) at each pixel of a window."""
        pid = R.rasterize(target, self.soils["ground"], attribute="id", dtype="uint32").astype(np.int64)
        pid[pid >= len(self.soils["pid_mu"])] = 0
        return pid

    def serves(self, i, target, pid, decoded):
        """True where mosaic i serves a pixel of its window: the pixel's county is i's (by its soil polygon's survey
        area; outside both counties, the nearest county by the owner grid), or the county's own mosaic doesn't cover
        it. decoded: [(mosaic index, array, target, pid)] of the mosaics read for this window."""
        own = self.area_mosaic[self.soils["pid_area"][pid]].astype(np.int16)
        need = own < 0
        if need.any() and self.owner is not None:
            og, ogt = self.owner
            xs, ys = centres(target)
            cols = np.clip(np.floor((xs - ogt[0]) / ogt[1]).astype(np.int64), 0, og.shape[1] - 1)
            rows = np.clip(np.floor((ogt[3] - ys) / -ogt[5]).astype(np.int64), 0, og.shape[0] - 1)
            own = np.where(need, og[rows[:, None], cols[None, :]], own)
        ok = own == i
        there = {j: (a, t) for j, a, t, _ in decoded}
        for j in np.unique(own):
            j = int(j)
            if j == i:
                continue
            if j not in there:
                ok |= own == j                                  # its mosaic doesn't reach this window
            else:
                a, t = there[j]
                ok |= (own == j) & ~on_lattice(a[4] == 255, t, target)
        return ok

    def pixels(self, target, arr, flight_curve=None, pid=None, allowed=None):
        """The photo-v1 mask and what the statistics need, for one decoded window (arr: 5 x h x w uint8). pid: the
        window's soil polygons, if already rasterised; allowed: where this mosaic serves (serves())."""
        r8, g8, b8, n8, mk = arr
        valid = mk == 255
        if allowed is not None:
            valid &= allowed
        raw = P.ndvi(n8, r8)
        if flight_curve is None:
            fid = R.rasterize(target, self.flights_path, attribute="src_fid", dtype="uint32")
            fid = np.minimum(fid, len(self.fid_flight) - 1)
            flight = self.fid_flight[fid]
            ndvi_s2 = P.normalised_ndvi(raw, flight, self.curves)
        else:
            flight = np.ones(raw.shape, np.uint8)
            ndvi_s2 = flight_curve(raw)
        if self.gains is not None and flight_curve is None:
            rgb, lin = self.gains.apply(flight, r8, g8, b8)    # on the reference flight day's scale
            L, a, b = P.colour_linear(*lin)
            del lin
        else:
            rgb = (r8, g8, b8)
            L, a, b = P.colour(r8, g8, b8)
        jv, jin = sample10(self.july, target)
        july = np.where(jin & (jv != -32768), jv / 10000.0, np.nan).astype(np.float32)
        cv, cin = sample10(self.crop_cover, target)
        cover = np.where(cin, cv, 0)
        field = R.rasterize(target, self.fields, attribute="cdl", dtype="uint16")
        crop = P.crop_ok(cover, self.code_drop[field])
        if pid is None:
            pid = self.polygons(target)
        inner_ok = P.inner(pid, RES)
        covered = MK.covered(target, self.mask)
        U, why = P.sample_mask(valid, pid, inner_ok, covered, flight, ndvi_s2, july, L, a, b, crop)
        mu = self.soils["pid_mu"][pid]
        return {"valid": valid, "L": L, "a": a, "b": b, "pid": pid, "mu": mu, "inner": inner_ok, "U": U,
                "why": why, "flight": flight, "ndvi_s2": ndvi_s2, "rgb": rgb}


# ---- which mosaic serves a place ----------------------------------------------------------------------------------

def county_of(mosaics):
    """Each mosaic's county survey area (COUNTY_AREAS, by the mosaic's name), or None."""
    return [COUNTY_AREAS.get(m.name) for m in mosaics]


def owner_grid(soils, mosaics, cache=None):
    """The county mosaics overlap: each reaches a few kilometres past its county line (Ada's mask covers about
    3,630 km2, the county 2,747), so one of them must serve each place, or the overlap would be counted twice and
    blended in the COG. A place in a county's survey area (ID001 Ada, ID665 Canyon: soils' areasymbol, whose shared
    edge is the county line) is its county's mosaic's; a place in neither is the nearest county's. This is the second
    rule on an OWNER_RES grid over the map box: (mosaic index per cell, uint8; its geotransform), cached in the build
    folder. None with one mosaic."""
    if len(mosaics) < 2:
        return None
    if soils["areas"] is None:
        raise StatsError("the soils export has no areasymbol per polygon: re-export soils (soils-export) so the "
                         "county mosaics can be split on the county line")
    path = os.path.join(cache, "owner.npz") if cache else None
    if path and os.path.exists(path):
        with np.load(path) as z:
            return z["owner"], tuple(float(v) for v in z["gt"])
    from scipy import ndimage
    # Over the mosaics' extents (which hold their counties), cut to the map box, on OWNER_RES steps from its corner.
    w = max(G.WEST, min(m.x0 for m in mosaics))
    e = min(G.EAST, max(m.x0 + m.width * m.res for m in mosaics))
    n = min(G.NORTH, max(m.y0 for m in mosaics))
    s_ = max(G.SOUTH, min(m.y0 - m.height * m.res for m in mosaics))
    w = G.WEST + np.floor((w - G.WEST) / OWNER_RES) * OWNER_RES
    n = G.NORTH - np.floor((G.NORTH - n) / OWNER_RES) * OWNER_RES
    width = max(int(np.ceil((e - w) / OWNER_RES)), 1)
    height = max(int(np.ceil((n - s_) / OWNER_RES)), 1)
    gt = (float(w), OWNER_RES, 0.0, float(n), 0.0, -OWNER_RES)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(G.EPSG)
    target = R.Target(gt, width, height, srs.ExportToWkt())
    owner = np.zeros((height, width), np.uint8)
    best = np.full((height, width), np.inf, np.float32)
    for i, area in enumerate(county_of(mosaics)):
        if area not in soils["areas"]:
            continue
        inside = R.rasterize(target, soils["ground"], where=f"areasymbol = '{area}'").astype(bool)
        if not inside.any():
            continue
        d = ndimage.distance_transform_edt(~inside).astype(np.float32)
        nearer = d < best
        owner[nearer] = i
        best = np.minimum(best, d)
        del d, inside, nearer
    if path:
        np.savez_compressed(path + ".part.npz", owner=owner, gt=np.array(gt))
        os.replace(path + ".part.npz", path)
    return owner, gt


def on_lattice(a, src, dst):
    """A bool array on src's pixels, read on dst's pixels (the same 0.6 m lattice, other corners); False where src
    has no pixel."""
    dc = (dst.transform[0] - src.transform[0]) / RES
    dr = (src.transform[3] - dst.transform[3]) / RES
    if abs(dc - round(dc)) > 1e-3 or abs(dr - round(dr)) > 1e-3:
        raise StatsError("the county mosaics' pixels aren't on one lattice")
    dc, dr = int(round(dc)), int(round(dr))
    out = np.zeros((dst.height, dst.width), bool)
    r0, r1 = max(0, -dr), min(dst.height, a.shape[0] - dr)
    c0, c1 = max(0, -dc), min(dst.width, a.shape[1] - dc)
    if r1 > r0 and c1 > c0:
        out[r0:r1, c0:c1] = a[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
    return out


# ---- one window ---------------------------------------------------------------------------------------------------

def centres(target):
    x0, rx, _, y0, _, ry = target.transform
    return x0 + (np.arange(target.width) + 0.5) * rx, y0 + (np.arange(target.height) + 0.5) * ry


def in_core(target, core, step=1):
    """Pixels (of a level `step` times coarser than target's) whose centres lie in core, half-open."""
    x0, rx, _, y0, _, ry = target.transform
    xs = x0 + (np.arange(target.width // step) + 0.5) * rx * step
    ys = y0 + (np.arange(target.height // step) + 0.5) * ry * step
    cx = (xs >= core.west) & (xs < core.east)
    cy = (ys <= core.north) & (ys > core.south)
    return cy[:, None] & cx[None, :]


def pad16(arr):
    """Pad a decoded window (bands x h x w) on the right and bottom to multiples of 16, with zeros (mask 0)."""
    _, h, w = arr.shape
    ph, pw = (-h) % 16, (-w) % 16
    if ph or pw:
        arr = np.pad(arr, ((0, 0), (0, ph), (0, pw)))
    return arr


def process(ctx, core, mosaics):
    """One window: (accumulator dict for np.savez, the 2 m arrays or None, counts)."""
    pad = core.pad_m(P.HALO_M)
    nf = ctx.nf
    acc = P.Accumulator(ctx.nkeys)
    poly_parts = []
    reasons = np.zeros(len(P.REASONS) + 1, np.int64)
    num = np.zeros((4, core.height, core.width))
    den = np.zeros((core.height, core.width))
    den_nd = np.zeros((core.height, core.width))
    decoded = []
    for i, mos in enumerate(mosaics):
        if not mos.covers(pad.bounds):
            continue
        reg = mos.region(pad.bounds)
        if reg is None:
            continue
        arr = pad16(mos.read(*reg))
        target = R.Target(mos.transform(reg[0], reg[1]), arr.shape[2], arr.shape[1], mos.crs)
        decoded.append((i, arr, target, ctx.polygons(target)))
    # Where both counties' mosaics reach, each pixel is served by one of them (Context.serves).
    serve = [ctx.serves(i, target, pid, decoded) if len(decoded) > 1 else None for i, _, target, pid in decoded]
    for (i, arr, target, pid), allowed in zip(decoded, serve):
        px = ctx.pixels(target, arr, pid=pid, allowed=allowed)
        core_px = in_core(target, core)
        key = np.where((px["mu"] >= 0) & (px["flight"] > 0), px["mu"] * nf + px["flight"].astype(np.int64) - 1, -1)
        sel = px["U"] & core_px & (key >= 0)
        acc.add(key[sel], px["L"][sel], px["a"][sel], px["b"][sel])
        poly_parts.append((px["pid"][sel], px["L"][sel], px["a"][sel], px["b"][sel]))
        cv = core_px & px["valid"]
        reasons += np.bincount(px["why"][cv].astype(np.int64) + 1, minlength=len(P.REASONS) + 1)
        C = np.hypot(px["a"], px["b"])
        for k, _, bands, counted in P.octaves([px["L"], C], px["U"], RES):
            step = 2 ** k
            off = step // 2
            hk, wk = counted.shape
            sub_key = key[off::step, off::step][:hk, :wk]
            m = counted & in_core(target, core, step)[:hk, :wk] & (sub_key >= 0)
            acc.add_texture(k, sub_key[m], bands[0][m], bands[1][m])
        # The 2 m grid: area means of the core's cells.
        Ax = P.overlap(target.transform[0], RES, target.width, core.west, PAINTER, core.width)
        Ay = P.overlap(0.0, RES, target.height, target.transform[3] - core.north, PAINTER, core.height)
        w = px["valid"].astype(np.float32)
        den += P.area_sum(Ay, Ax, w)
        for c, band in enumerate(px["rgb"]):
            num[c] += P.area_sum(Ay, Ax, band.astype(np.float32) * w)
        has = px["valid"] & ~np.isnan(px["ndvi_s2"])
        wn = has.astype(np.float32)
        den_nd += P.area_sum(Ay, Ax, wn)
        num[3] += P.area_sum(Ay, Ax, np.where(has, px["ndvi_s2"], 0.0).astype(np.float32))
        del px, C
    del decoded, serve
    out = acc.sparse("c_")
    if poly_parts:
        pid = np.concatenate([p[0] for p in poly_parts])
        uniq, inv = np.unique(pid, return_inverse=True)
        pacc = P.Accumulator(len(uniq), hist_dtype=np.int32)
        pacc.add(inv, *(np.concatenate([p[i] for p in poly_parts]) for i in (1, 2, 3)))
        out.update(pacc.sparse("p_", labels=uniq))
    out["reasons"] = reasons
    cell = PAINTER * PAINTER
    cog = None
    if (den > 0).any():
        cover = den / cell
        keep = cover >= 0.5
        bands = []
        for i in range(3):
            v = np.divide(num[i], den, out=np.zeros_like(den), where=den > 0)
            bands.append(np.clip(np.rint(v), 0, 255).astype(np.uint8))
        nd = np.divide(num[3], den_nd, out=np.full_like(den, np.nan), where=den_nd >= 0.5 * cell)
        bands.append(P.encode_ndvi(nd))
        cog = (np.stack(bands), keep)
    return out, cog, reasons


def write_part(path, core, bands, keep):
    tmp = path + ".part.tif"
    gdal.SetConfigOption("GDAL_TIFF_INTERNAL_MASK", "YES")
    ds = gdal.GetDriverByName("GTiff").Create(tmp, core.width, core.height, 4, gdal.GDT_Byte,
                                              ["TILED=YES", "BLOCKXSIZE=256", "BLOCKYSIZE=256", "COMPRESS=DEFLATE",
                                               "PREDICTOR=2", "INTERLEAVE=PIXEL"])
    ds.SetGeoTransform(core.transform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(G.EPSG)
    ds.SetProjection(srs.ExportToWkt())
    for i in range(4):
        ds.GetRasterBand(i + 1).WriteArray(np.where(keep, bands[i], 0))
    ds.CreateMaskBand(gdal.GMF_PER_DATASET)
    ds.GetRasterBand(1).GetMaskBand().WriteArray(np.where(keep, 255, 0).astype(np.uint8))
    ds = None
    os.replace(tmp, path)


# ---- run ----------------------------------------------------------------------------------------------------------

_CTX = None
_MOSAICS = None


def _init(cfg):
    global _CTX, _MOSAICS
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    P.configure(**cfg.get("rules", {}))
    _CTX = Context(cfg)
    _MOSAICS = open_mosaics(cfg)
    _CTX.set_mosaics(_MOSAICS)


def open_mosaics(cfg):
    tmp = cfg.get("tmp") or tempfile.gettempdir()
    out = []
    for name, path in cfg["naip"]:
        if path.lower().endswith(".sid"):
            out.append(SidMosaic(name, path, cfg["dsdk"], tmp, cfg.get("cache")))
        else:
            out.append(TiffMosaic(name, path))
    return out


def _job(args):
    key, col, row, width, height, out_dir, cog_dir = args
    t0 = time.time()
    core = G.Window(PAINTER, col, row, width, height)
    acc, cog, reasons = process(_CTX, core, _MOSAICS)
    if cog is not None:
        write_part(os.path.join(cog_dir, "parts", f"{key}.tif"), core, *cog)
    tmp = os.path.join(out_dir, "windows", f"{key}.part.npz")
    np.savez_compressed(tmp, **acc, has_part=np.array(cog is not None))
    os.replace(tmp, os.path.join(out_dir, "windows", f"{key}.npz"))
    return key, time.time() - t0, int(reasons[0])


def plan_windows(cfg, mosaics, bounds=None):
    """The 2 m grid's core windows that hold any county pixel (in bounds, when given)."""
    cells = int(round(CORE_M / PAINTER))
    out = []
    for core, _ in G.windows(PAINTER, cells, bounds=bounds):
        if any(m.covers(core.bounds) for m in mosaics):
            out.append(core)
    return out


# The export layers a build reads (and so whose inputs it carries): soils' polygons and types, mask v0's sampling
# mask, farm's crop cover and fields.
READS = (("soils", ("ground", "ground_types")), ("ground_mask", (MK.MR.SAMPLE_LAYER,)),
         ("farm", ("crop_cover", "fields")))


def layer_inputs(m, names):
    """Every input of the named layers of an export, whole, in the manifest's order."""
    want = set()
    for n in names:
        want.update(m.layer(n)["inputs"])
    return [dict(e) for k, e in m.inputs.items() if k in want]


def inputs_of(cfg, soils_m, mask_m, farm_m, mosaics, hashes=True):
    """The build's inputs, as manifest inputs (basemap/ground/manifest.py): the photo and Sentinel-2 entries made
    here, then every input of each export layer read (READS), copied whole with a note of the export it came through,
    so a licence or credit can't drop out ("the strictest input wins"). An input met twice keeps its first entry, adds
    the second's note and the stricter republish, and must have one licence. Also the files and builds read, for
    run.json."""
    naip_files = [{"name": m.name, "file": os.path.basename(m.path),
                   "sha256": sha256(m.path) if hashes else None} for m in mosaics]
    gains = cfg.get("gains")
    s2_version = "the July 2025 NDVI median; the NAIP 2025 flight days' same-day fits (naip_norm, band 4)"
    s2_note = f"fits.json sha256 {sha256(cfg['fits']) if hashes else None}"
    if gains:
        s2_version += "; same-day blue, green and red for the per-flight colour gains (naip_colour)"
        s2_note += f"; gains.json sha256 {sha256(gains) if hashes else None}"
    ins = [
        {"name": "naip", "licence": "public-domain", "republish": "yes", "credit": "USDA NAIP",
         "version": "NAIP 2025 county mosaics, " + ", ".join(f["file"] for f in naip_files) + ", read at 0.6 m",
         "note": "; ".join(f"{f['name']} sha256 {f['sha256']}" for f in naip_files if f["sha256"])},
        {"name": "sentinel-2", "licence": "Copernicus", "republish": "yes",
         "credit": "Contains modified Copernicus Sentinel data 2025", "version": s2_version,
         "sha256": sha256(cfg["july"]) if hashes else None, "note": s2_note},
    ]
    by_name = {i["name"]: i for i in ins}
    for m, (what, names) in zip((soils_m, mask_m, farm_m), READS):
        via = f"through {what} export {m.build} ({', '.join(names)})"
        for e in layer_inputs(m, names):
            have = by_name.get(e["name"])
            if have is None:
                e["note"] = f"{e['note']}; {via}" if e.get("note") else via
                ins.append(e)
                by_name[e["name"]] = e
            else:
                if e.get("licence") != have.get("licence"):
                    raise StatsError(f"input {e['name']!r} comes as {have.get('licence')} and as {e.get('licence')} "
                                     f"({via}): one source, one licence")
                if M.rank(e["republish"]) > M.rank(have["republish"]):
                    have["republish"] = e["republish"]           # the strictest wins
                have["note"] = f"{have['note']}; {via}" if have.get("note") else via
    files = {"soils": soils_m.build, "ground_mask": mask_m.build, "farm": farm_m.build,
             "july": cfg["july"], "fits": cfg["fits"], "flights": cfg["flights"], "gains": gains,
             "naip": {f["name"]: f for f in naip_files},
             "decoder": "; ".join(getattr(m, "version", "") for m in mosaics)}
    return [{k: v for k, v in i.items() if v is not None} for i in ins], files


def config(args):
    archive = os.environ.get("TVT_ARCHIVE")
    soils = args.soils or (M.latest(archive, "soils").folder if archive else None)
    mask = args.mask or (MK.latest(archive).folder if archive else None)
    farm = args.farm or (M.latest(archive, "farm").folder if archive else None)
    for name, v in (("--soils", soils), ("--mask", mask), ("--farm", farm)):
        if not v:
            raise StatsError(f"{name}: no export found (set TVT_ARCHIVE or give the folder)")
    norm = args.norm
    gains = None if args.no_gains else args.gains
    if gains and not os.path.exists(gains):
        raise StatsError(f"--gains: {gains} isn't there (the per-flight colour gains; --no-gains to measure without)")
    return {"soils": soils, "mask": mask, "farm": farm, "july": args.july, "fits": os.path.join(norm, "fits.json"),
            "flights": os.path.join(norm, "flights_mapbox.gpkg"), "gains": gains,
            "naip": [tuple(n.split("=", 1)) for n in args.naip],
            "dsdk": args.dsdk, "tmp": args.tmp, "cache": args.out,
            "days": ["2025-05-25", "2025-05-30", "2025-06-18", "2025-07-24"],
            "rules": {"dark_l": args.dark_l, "neutral_c": args.neutral_c, "blue_b": args.blue_b}}


def colour_params(cfg):
    """What run.json and the build record about the colour: the per-flight gains used (or none)."""
    if not cfg.get("gains"):
        return {"normalised": False, "about": "the photo's DNs as they are, read as sRGB"}
    with open(cfg["gains"], encoding="utf-8") as f:
        doc = json.load(f)
    return {"normalised": True, "gains": os.path.basename(cfg["gains"]), "sha256": sha256(cfg["gains"]),
            "reference_day": doc["reference_day"], "method": doc.get("method"), "made": doc.get("made"),
            "about": f"each flight day's red, green and blue put on the {doc['reference_day']} flight's scale through "
                     "same-day Sentinel-2 reflectance (P.Gains); read as sRGB"}


def same(cfg):
    """What must match for a run to resume: the inputs, not where the decoder or the temporary files are."""
    return json.loads(json.dumps({k: v for k, v in cfg.items() if k not in ("tmp", "cache", "dsdk")}))


def cmd_run(args):
    cfg = config(args)
    P.configure(**cfg["rules"])
    out = args.out
    os.makedirs(os.path.join(out, "windows"), exist_ok=True)
    os.makedirs(os.path.join(args.cog, "parts"), exist_ok=True)
    run_path = os.path.join(out, "run.json")
    mosaics = open_mosaics(cfg)
    bounds = tuple(float(v) for v in args.bounds.split(",")) if args.bounds else None
    windows = plan_windows(cfg, mosaics, bounds)
    soils_m, mask_m, farm_m = M.read(cfg["soils"]), M.read(cfg["mask"]), M.read(cfg["farm"])
    if os.path.exists(run_path):
        with open(run_path, encoding="utf-8") as f:
            run = json.load(f)
        if (same(run["config"]) != same(cfg) or run.get("bounds") != (list(bounds) if bounds else None)
                or run.get("colour") != colour_params(cfg)):
            raise StatsError(f"{out} was started with other inputs; start a new build folder")
        log(f"resuming {run['build_id']}")
    else:
        build_id = os.path.basename(os.path.normpath(out))
        ins, files = inputs_of(cfg, soils_m, mask_m, farm_m, mosaics, hashes=not args.no_hashes)
        run = {"format": FORMAT, "build_id": build_id, "started": utc_now(), "config": cfg,
               "bounds": list(bounds) if bounds else None, "cog": os.path.abspath(args.cog), "inputs": ins,
               "files": files, "rules": P.RULES, "res": RES, "core_m": CORE_M, "halo_m": P.HALO_M,
               "octaves_m": list(P.OCTAVES_M), "support": P.SUPPORT, "bins": P.BINS, "ranges": P.RANGES,
               "mapunits": [m["mukey"] for m in read_soils(cfg["soils"])["mapunits"]], "days": cfg["days"],
               "colour": colour_params(cfg), "counties": dict(zip((m.name for m in mosaics), county_of(mosaics))),
               "windows": len(windows), "partial": bounds is not None}
        write_json(run_path, run)
    owner_grid(read_soils(cfg["soils"], hashes=False), mosaics, cache=out)   # computed once, before the workers
    todo = [w for w in windows if not os.path.exists(os.path.join(out, "windows", f"{w.key}.npz"))]
    before = len(windows) - len(todo)
    if args.limit:
        todo = todo[:args.limit]
    log(f"{len(windows)} windows, {before} done before, {len(todo)} to do now, {args.workers} workers")
    jobs = [(w.key, w.col, w.row, w.width, w.height, out, args.cog) for w in todo]
    t0 = time.time()
    done = 0
    ctx = multiprocessing.get_context("spawn")
    pool = ctx.Pool(args.workers, initializer=_init, initargs=(cfg,), maxtasksperchild=200)

    def stop(signum, _frame):
        pool.terminate()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    try:
        for key, secs, _ in pool.imap_unordered(_job, jobs):
            done += 1
            if done % 25 == 0 or done == len(jobs):
                rate = (time.time() - t0) / done
                log(f"{done}/{len(jobs)} windows, {rate:.1f} s each overall, last {secs:.1f} s; "
                    f"about {rate * (len(jobs) - done) / 60:.0f} min left")
        pool.close()
        pool.join()
    except BaseException:
        pool.terminate()
        raise
    log(f"run: {done} windows in {(time.time() - t0) / 60:.1f} min")
    return 0


# ---- finish -------------------------------------------------------------------------------------------------------

def merge(out, soils, nkeys):
    acc = P.Accumulator(nkeys)
    pacc = P.Accumulator(len(soils["poly_gid"]), hist_dtype=np.int32)
    reasons = np.zeros(len(P.REASONS) + 1, np.int64)
    parts = 0
    files = sorted(f for f in os.listdir(os.path.join(out, "windows")) if f.endswith(".npz") and ".part" not in f)
    for name in files:
        with np.load(os.path.join(out, "windows", name)) as z:
            acc.merge(z, "c_")
            if "p_keys" in z.files:
                pacc.merge(z, "p_", keymap=soils["pid_row"])
            reasons += z["reasons"]
            parts += int(z["has_part"])
    return acc, pacc, reasons, len(files), parts


def cmd_finish(args):
    out = args.out
    with open(os.path.join(out, "run.json"), encoding="utf-8") as f:
        run = json.load(f)
    cfg = run["config"]
    soils = read_soils(cfg["soils"])
    if [m["mukey"] for m in soils["mapunits"]] != run["mapunits"]:
        raise StatsError("the soils export changed since the run started")
    mosaics = open_mosaics(dict(cfg, tmp=args.tmp))
    bounds = tuple(run["bounds"]) if run["bounds"] else None
    planned = plan_windows(cfg, mosaics, bounds)
    nf = len(run["days"])
    acc, pacc, reasons, nwin, parts = merge(out, soils, len(soils["mapunits"]) * nf)
    missing = len(planned) - nwin
    if missing and not args.allow_missing:
        raise StatsError(f"{missing} of {len(planned)} windows aren't done yet: run again to finish them")
    log(f"merged {nwin} windows ({parts} with 2 m parts); {int(acc.n.sum()):,} pixels sampled")
    if not soils["has_landform"]:
        log("note: this soils export has no landform per type; the texture fallback matches on texture class "
            "and no landform")
    polys = {"gid": soils["poly_gid"], "mu": soils["poly_mu"], "acc": pacc}
    colour = run.get("colour") or {"normalised": False}
    rows, report = PL.pool(soils["mapunits"], soils["types"], run["days"], acc, polys,
                           gains_applied=colour["normalised"])
    report["colour"] = colour
    seen = reasons.sum() - reasons[0]
    report["pixels"] = {"in_cores": int(reasons.sum()), "sampled": int(reasons[0]),
                        "not_sampled": {r: int(reasons[i + 1]) for i, r in enumerate(P.REASONS)},
                        "sampled_share_of_valid": round(float(reasons[0] / max(seen + reasons[0], 1)), 4)}
    report["windows"] = {"planned": len(planned), "done": nwin, "with_2m_parts": parts}
    cal_path = os.path.join(out, "calibration.json")
    if os.path.exists(cal_path):
        with open(cal_path, encoding="utf-8") as f:
            cal = json.load(f)
        why = calibration_mismatch(cal, run)
        if why:
            log(f"calibration.json isn't this build's ({why}): left out; run calibrate --out {out} again")
            report["calibration"] = {"verdict": None, "left_out": why}
        else:
            report["calibration"] = cal["summary"]
            report["calibration_palette"] = palette_vs_classes(cal, rows)
    finished = utc_now()
    counts = {"rows": len(rows), "types": report["counts"], "pixels_sampled": int(reasons[0]),
              "windows": nwin, "flight_days": {k: report["flight_days"][k] for k in
                                               ("gains_applied", "types_on_two_or_more", "median_max_de",
                                                "share_over", "over_rule", "gains_needed")},
              "colour": {k: colour.get(k) for k in ("normalised", "reference_day", "sha256")},
              "albedo_fit_r": round(report["albedo_fit"]["r"], 3) if report.get("albedo_fit") else None,
              "variance_explained": report["variance_explained"], "spearman_l_albedo": report["spearman_l_albedo"],
              "polygon_outliers": report["polygon_outliers"]["listed"],
              "calibration": report.get("calibration", {}).get("verdict")}
    stats = {"format": FORMAT, "build_id": run["build_id"], "started": run["started"], "finished": finished,
             "photo": PL.PHOTO, "mask": PL.MASK, "partial": run["partial"] or bool(missing),
             "soils_export": soils["manifest"].build, "inputs": run["inputs"], "files": run["files"],
             "params": {k: run[k] for k in ("rules", "res", "core_m", "halo_m", "octaves_m", "support", "bins",
                                            "ranges", "days")} | {"thresholds": report["thresholds"],
                                                                  "colour": colour,
                                                                  "counties": run.get("counties")},
             "counts": counts, "rows": rows}
    write_json(os.path.join(out, "report.json"), report)
    write_json(os.path.join(out, "stats.json"), stats)
    log(f"finish: {len(rows)} rows; types {report['counts']}; flight days {counts['flight_days']}; variance "
        f"explained {report['variance_explained']}; rho(L, albedo) {report['spearman_l_albedo']}; "
        f"{counts['polygon_outliers']} polygon outliers; calibration {counts['calibration']}")
    if not args.no_cog and not run["partial"] and not missing:
        assemble_cog(run, args.cog or run["cog"])
    return 0


def calibration_mismatch(cal, run):
    """Why a calibration.json isn't the run's own (its rules or inputs differ), or None when it is."""
    rules = cal.get("summary", {}).get("rules") or {}
    for k in ("dark_l", "neutral_c", "blue_b", "green_cut_s2", "july_cut", "edge_m"):
        if rules.get(k) != run["rules"].get(k):
            return f"rule {k} {rules.get(k)} against the run's {run['rules'].get(k)}"
    ins = cal.get("inputs")
    if not ins:
        return "it doesn't record its inputs"
    want = cal_inputs(None, run)
    for k in ("soils", "ground_mask", "farm", "july", "fits", "gains"):
        if ins.get(k) != want.get(k):
            return f"{k} {ins.get(k)} against the run's {want.get(k)}"
    return None


def palette_vs_classes(cal, rows):
    """For the report: each measured type's palette median against the class mask's median in the boxes."""
    pal = {r["key"]: r["lab_med"] for r in rows
           if r["level"] == "ground_type" and r["flight"] is None and r["fallback"] is None}
    des = []
    for p in cal["pairs"]:
        if p["type"] in pal and p.get("class_med"):
            des.append(P.delta_e(pal[p["type"]], p["class_med"]))
    return {"pairs": len(des), "median_de": round(float(np.median(des)), 2) if des else None,
            "about": "the valley-wide photo-v1 median of each measured type against the class mask's median for it "
                     "in each box: spatial spread plus the mask's bias (information, not the pass rule)"}


# ---- the COG ------------------------------------------------------------------------------------------------------

def assemble_cog(run, cog_dir):
    parts_dir = os.path.join(cog_dir, "parts")
    parts = sorted(os.path.join(parts_dir, f) for f in os.listdir(parts_dir)
                   if f.endswith(".tif") and ".part" not in f)
    if not parts:
        raise StatsError(f"no 2 m parts in {parts_dir}")
    log(f"COG: {len(parts)} parts")
    vrt = os.path.join(cog_dir, "parts.vrt")
    gdal.BuildVRT(vrt, parts, xRes=PAINTER, yRes=PAINTER)       # the parts' extent, on the 2 m grid
    ds = gdal.Open(vrt, gdal.GA_Update)                         # names and credits go on before the COG is made
    gt, width, height = ds.GetGeoTransform(), ds.RasterXSize, ds.RasterYSize
    for i, (name, about) in enumerate(BAND_ABOUT):
        ds.GetRasterBand(i + 1).SetDescription(name)
        ds.GetRasterBand(i + 1).SetMetadataItem("ABOUT", about)
    ds.SetMetadataItem("CREDIT", NAIP_CREDIT + "; Contains modified Copernicus Sentinel data 2025 (the ndvi band's "
                       "curves)")
    ds.SetMetadataItem("BUILD", run["build_id"])
    ds = None
    if not G.aligned(gt, PAINTER):
        raise StatsError("the 2 m parts aren't on the ground's 2 m grid")
    tmp = os.path.join(cog_dir, COG_NAME + ".part")
    gdal.SetConfigOption("GDAL_TIFF_INTERNAL_MASK", "YES")
    t0 = time.time()
    gdal.Translate(tmp, vrt, format="COG",
                   creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=YES", "BLOCKSIZE=512", "BIGTIFF=YES",
                                    "OVERVIEWS=NONE", "SPARSE_OK=TRUE", "NUM_THREADS=ALL_CPUS"])
    final = os.path.join(cog_dir, COG_NAME)
    os.replace(tmp, final)
    log(f"COG: {os.path.getsize(final) / 1e9:.2f} GB in {(time.time() - t0) / 60:.1f} min")
    flights = os.path.join(cog_dir, "flights.fgb")
    gdal.VectorTranslate(flights, run["config"]["flights"], format="FlatGeobuf", dstSRS="EPSG:32611",
                         srcSRS=R.warp_srs("EPSG:26911"), layerName="flights",
                         selectFields=["src_fid", "idate", "sdate", "edate", "camera"])
    sidecar = {
        "format": COG_FORMAT, "file": COG_NAME, "bytes": os.path.getsize(final), "sha256": sha256(final),
        "build": run["build_id"], "created": utc_now(), "crs": G.CRS,
        "grid": {"res": PAINTER, "west": gt[0], "north": gt[3], "width": width, "height": height},
        "bands": [{"name": n, "type": "uint8", "about": a} for n, a in BAND_ABOUT],
        "mask": "internal per-dataset mask: 255 where Ada's or Canyon's mosaic covers at least half the cell",
        "ndvi_coding": "ndvi = (code - 128) / 127 for code 1..255; 0 = none",
        "flight_days": run["days"],
        "flights": "flights.fgb: USDA's NAIP 2025 seamline polygons in the box (EPSG:32611): src_fid, idate (the "
                   "flight day), sdate and edate (local time, MM/DD/YYYY hh:mm, read as MDT), camera",
        "colour_normalised": bool((run.get("colour") or {}).get("normalised")),
        "colour": run.get("colour") or {"normalised": False},
        "ndvi_note": "The curves were fitted on 20 m cells that weren't developed, water or mixed: bare and fallow "
                     "ground reads up to 0.1 greener than Sentinel-2, developed land 0.02-0.07. In a July 24 strip "
                     "near lon -116.02, lat 43.38-43.40 (about 13 km2) NAIP's near-infrared is below its red, so "
                     "ndvi reads about -0.06 where Sentinel-2 reads 0.14 (dry rangeland: not green either way). "
                     "Over water it isn't meaningful (naip_norm's caveats).",
        "colour_note": colour_note(run),
        "counties": "Ada's and Canyon's mosaics overlap by a few kilometres along the county line; each cell is "
                    "served by its own county's mosaic (soils' survey areas ID001 and ID665), and a cell in neither "
                    "county by the nearest county's, so the two mosaics' balancing meets at the county line",
        "inputs": [i for i in run["inputs"] if i["name"] in ("naip", "sentinel-2")],
        "licence": "Copernicus (the ndvi band's curves and the colour gains come from Sentinel-2) over public-domain "
                   "NAIP; republish yes, with both credits",
        "credit": [NAIP_CREDIT, "Contains modified Copernicus Sentinel data 2025"],
        "decoder": "LizardTech MrSID Decode SDK (internal use; not redistributed): " + run["files"]["decoder"],
    }
    write_json(os.path.join(cog_dir, "naip2025_2m.json"), sidecar)
    os.remove(vrt)
    log(f"COG: {final} ({sidecar['sha256'][:12]}), flights.fgb, naip2025_2m.json")


def colour_note(run):
    colour = run.get("colour") or {}
    if not colour.get("normalised"):
        return ("The colour bands are the photo's DNs, not normalised per flight day: stats.json's flight-day check "
                "says whether they need to be (report.json flight_days).")
    return (f"The colour bands are on the {colour['reference_day']} flight's scale: each flight day's DNs went "
            "through that day's table (gains.json: NAIP against same-day Sentinel-2 blue, green and red, composed "
            "with the reference day's curve) before the area mean. Pixels outside every flight polygon are as "
            "photographed.")


BAND_ABOUT = (
    ("red", "NAIP 2025 red, the area mean of the 0.6 m pixels on the reference flight day's scale (DN, read as "
            "sRGB; the sidecar's colour says which day, or that it isn't normalised)"),
    ("green", "NAIP 2025 green, the same"),
    ("blue", "NAIP 2025 blue, the same"),
    ("ndvi", "the photo's NDVI on Sentinel-2's scale, by its flight day's curve (naip_norm band 4), averaged; "
             "(code - 128) / 127, 0 for none"),
)


# ---- calibrate ----------------------------------------------------------------------------------------------------

def calibration_config(args):
    """calibrate's inputs. In a build folder with a run.json they're the run's (its soils, mask v0, farm, July, fits,
    gains and rules), so the verdict finish publishes is the build's own; a flag that says otherwise is refused.
    Without one (a sweep in a folder of its own), they're resolved as run resolves them."""
    run_path = os.path.join(args.out, "run.json")
    if not os.path.exists(run_path):
        return config(args), None
    with open(run_path, encoding="utf-8") as f:
        run = json.load(f)
    rc = run["config"]
    given = {"soils": args.soils, "mask": args.mask, "farm": args.farm,
             "rules": {k: v for k, v in (("dark_l", args.dark_l), ("neutral_c", args.neutral_c),
                                         ("blue_b", args.blue_b)) if v is not None}}
    for k in ("soils", "mask", "farm"):
        if given[k] and os.path.abspath(given[k]) != os.path.abspath(rc[k]):
            raise StatsError(f"--{k}: {args.out} was run on {rc[k]}; calibrate a build on its own inputs (or "
                             "calibrate into another folder)")
    for k, v in given["rules"].items():
        if run["rules"].get(k) != v:
            raise StatsError(f"--{k.replace('_', '-')} {v}: the run used {run['rules'].get(k)}; a sweep goes in a "
                             "folder of its own")
    out = dict(rc, naip=[tuple(n.split("=", 1)) for n in args.naip], dsdk=args.dsdk, tmp=args.tmp, cache=args.out,
               rules={k: run["rules"].get(k) for k in ("dark_l", "neutral_c", "blue_b")})
    return out, run


def cal_inputs(cfg, run):
    """What a calibration was measured on: the builds and files read, and the rules (finish compares them)."""
    if run is not None:
        return {"build": run["build_id"], "soils": run["files"]["soils"], "ground_mask": run["files"]["ground_mask"],
                "farm": run["files"]["farm"], "july": run["config"]["july"], "fits": run["config"]["fits"],
                "gains": (run.get("colour") or {}).get("sha256")}
    return {"build": None, "soils": M.read(cfg["soils"], hashes=False).build,
            "ground_mask": M.read(cfg["mask"], hashes=False).build, "farm": M.read(cfg["farm"], hashes=False).build,
            "july": cfg["july"], "fits": cfg["fits"], "gains": sha256(cfg["gains"]) if cfg.get("gains") else None}


def cmd_calibrate(args):
    cfg, run = calibration_config(args)
    P.configure(**cfg["rules"])
    ctx = Context(cfg)
    mosaics = {m.name: m for m in open_mosaics(cfg)}
    with open(args.shifts, encoding="utf-8") as f:
        shifts = json.load(f)["shifts"]
    out_pairs, boxes = [], {}
    explore = {}
    for box in G.boxes():
        wpath, jpath = os.path.join(args.windows, f"{box.id}.json"), os.path.join(args.classes, f"{box.id}_J.npy")
        if not (os.path.exists(wpath) and os.path.exists(jpath)):
            log(f"{box.id}: no classes; skipped")
            boxes[box.id] = {"skipped": "no classes"}
            continue
        with open(wpath, encoding="utf-8") as f:
            r0, c0 = json.load(f)["window_rc"]
        J = np.load(jpath)
        west = box.utm[0] + c0 * CLASS_RES
        north = box.utm[3] - r0 * CLASS_RES
        cw = (west, north - J.shape[0] * CLASS_RES, west + J.shape[1] * CLASS_RES, north)
        sh = shifts.get(box.id, {})
        dx, dy = int(sh.get("dx_cells", 0)), int(sh.get("dy_cells", 0))
        county = {"Ada": "ada", "Canyon": "canyon"}.get(box.county)
        if county and county in mosaics:
            mos, curve, photo = mosaics[county], None, "naip2025"
        else:
            path = os.path.join(args.naip2023, f"{box.id}.tif")
            if not os.path.exists(path):
                log(f"{box.id}: no photo ({box.county}); skipped")
                boxes[box.id] = {"skipped": "no photo"}
                continue
            mos, curve, photo = TiffMosaic(f"naip2023-{box.id}", path), ctx.curve_2023, "naip2023"
        wb = (cw[0] - P.HALO_M, cw[1] - P.HALO_M, cw[2] + P.HALO_M, cw[3] + P.HALO_M)
        reg = mos.region(wb) if mos.covers(cw) else None
        if reg is None:
            log(f"{box.id}: the photo doesn't reach it; skipped")
            boxes[box.id] = {"skipped": "no photo"}
            continue
        arr = pad16(mos.read(*reg))
        target = R.Target(mos.transform(reg[0], reg[1]), arr.shape[2], arr.shape[1], mos.crs)
        px = ctx.pixels(target, arr, flight_curve=curve)
        xs, ys = centres(target)
        rr = np.floor((north - ys) / CLASS_RES).astype(np.int64) - dy
        cc = np.floor((xs - west) / CLASS_RES).astype(np.int64) - dx
        okr = (rr >= 0) & (rr < J.shape[0])
        okc = (cc >= 0) & (cc < J.shape[1])
        inside = okr[:, None] & okc[None, :]
        cls = np.where(inside, J[np.clip(rr, 0, J.shape[0] - 1)][:, np.clip(cc, 0, J.shape[1] - 1)], 0)
        base = inside & px["valid"] & (px["pid"] > 0) & px["inner"]
        cmask = base & np.isin(cls, CLASS_KEEP)
        umask = px["U"] & inside
        types = ctx.soils["mapunits"]
        tkey = np.array([m["type"] or "" for m in types], object)
        tid = np.where(px["mu"] >= 0, tkey[np.clip(px["mu"], 0, len(tkey) - 1)], "")
        res = {"photo": photo, "shift_cells": [dx, dy], "pixels_in_window": int(inside.sum()),
               "photo_v1": int(umask.sum()), "class_mask": int(cmask.sum()),
               "both": int((umask & cmask).sum()),
               "photo_v1_by_class": {}, "types": []}
        names = CLASS_NAMES
        for code in np.unique(cls[umask]):
            res["photo_v1_by_class"][names[int(code)]] = round(float((cls[umask] == code).mean()), 4)
        for t in sorted(set(tid[umask | cmask]) - {""}):
            sel_u = umask & (tid == t)
            sel_c = cmask & (tid == t)
            nu, nc = int(sel_u.sum()), int(sel_c.sum())
            mu_ = [float(np.median(px[ch][sel_u])) for ch in "Lab"] if nu else None
            mc_ = [float(np.median(px[ch][sel_c])) for ch in "Lab"] if nc else None
            row = {"box": box.id, "type": t, "n_photo_v1": nu, "n_class": nc,
                   "photo_med": PL._r(mu_), "class_med": PL._r(mc_)}
            if nu >= CAL_MIN_PX and nc >= CAL_MIN_PX:
                row["de"] = round(P.delta_e(mu_, mc_), 2)
            res["types"].append(row)
            out_pairs.append(row)
        if args.explore:
            C = np.hypot(px["a"], px["b"])
            ex = {}
            for code in np.unique(cls[base]):
                sel = base & (cls == code)
                if sel.sum() < 500:
                    continue
                q = lambda v: [round(float(x), 4) for x in np.percentile(v[sel], (5, 25, 50, 75, 95))]
                ex[names[int(code)]] = {"n": int(sel.sum()), "L": q(px["L"]), "C": q(C), "b": q(px["b"]),
                                        "dark_rule": round(float(P.dark(px["L"][sel], px["a"][sel],
                                                                       px["b"][sel]).mean()), 4)}
            explore[box.id] = ex
        boxes[box.id] = res
        des = [r["de"] for r in res["types"] if "de" in r]
        log(f"{box.id} ({photo}): photo-v1 {res['photo_v1']:,} px, class mask {res['class_mask']:,}, both "
            f"{res['both']:,}; {len(des)} types compared, median dE "
            f"{np.median(des) if des else float('nan'):.2f}")
    des = [r["de"] for r in out_pairs if "de" in r]
    med = float(np.median(des)) if des else None
    summary = {"pairs": len(des), "median_de": round(med, 2) if med is not None else None,
               "p90_de": round(float(np.percentile(des, 90)), 2) if des else None,
               "pass_at": CAL_PASS, "verdict": None if med is None else ("pass" if med <= CAL_PASS else "fail"),
               "per_box": {b: (round(float(np.median([r["de"] for r in v["types"] if "de" in r])), 2)
                               if any("de" in r for r in v.get("types", [])) else None)
                           for b, v in boxes.items()},
               "rules": P.RULES, "class_keep": [CLASS_NAMES[c] for c in CLASS_KEEP], "min_px": CAL_MIN_PX}
    for b, v in boxes.items():
        v["lidar"] = LV.lidar_vintage(b)
    log("lidar vintage by box:\n" + LV.vintage_table(
        [(b, round(float(np.median([r["de"] for r in v["types"] if "de" in r])), 2)
          if v.get("types") and any("de" in r for r in v["types"]) else None) for b, v in boxes.items()]))
    cal = {"format": "tvt-soils-calibration/1", "made": utc_now(), "inputs": cal_inputs(cfg, run),
           "summary": summary, "boxes": boxes, "pairs": out_pairs}
    if args.explore:
        cal["explore"] = explore
    os.makedirs(args.out, exist_ok=True)
    write_json(os.path.join(args.out, "calibration.json"), cal)
    log(f"calibration: {summary['pairs']} pairs, median dE {summary['median_de']} (p90 {summary['p90_de']}): "
        f"{summary['verdict']}")
    return 0


CLASS_NAMES = ("no data", "roof", "water", "tree", "shrub", "crop", "tall green grass", "tall dry grass",
               "short green grass", "flat, not green", "hard thing", "wall or fence", "short dry grass",
               "surfaced, dark", "surfaced, pale")


# ---- the command line ---------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    src = os.environ.get("TVT_SOURCES", "/srv/sources")

    def common(p):
        p.add_argument("--out", required=True, help="the build folder ($TVT_ARCHIVE/soils/photo/<build>)")
        p.add_argument("--soils", help="the soils export (default: the newest in $TVT_ARCHIVE)")
        p.add_argument("--mask", help="mask v0's build (default: the newest whole one in $TVT_ARCHIVE)")
        p.add_argument("--farm", help="farm's export, for crop_cover and fields (default: the newest)")
        p.add_argument("--july", default=os.path.join(src, "sentinel2/july2025/ndvi_median.tif"))
        p.add_argument("--norm", default=os.path.join(src, "sentinel2/naip_norm"),
                       help="the same-day normalisation: fits.json and flights_mapbox.gpkg")
        p.add_argument("--gains", default=os.path.join(src, "sentinel2/naip_colour/gains.json"),
                       help="the per-flight colour gains (photo.Gains)")
        p.add_argument("--no-gains", action="store_true", help="measure the photo's colours as they are")
        p.add_argument("--naip", action="append", default=[], metavar="NAME=PATH",
                       help="a county mosaic (.sid) or a 0.6 m GeoTIFF, e.g. ada=.../ortho_1-1_hm_s_id001_2025_1.sid")
        p.add_argument("--dsdk", default="/dsdk", help="the MrSID Decode SDK's folder (mounted, never committed)")
        p.add_argument("--tmp", default=None, help="where decoded windows go (a tmpfs; default /tmp)")
        p.add_argument("--dark-l", type=float, help=f"the dark rule's L cut (default {P.DARK_L})")
        p.add_argument("--neutral-c", type=float, help=f"its neutral chroma cut (default {P.NEUTRAL_C})")
        p.add_argument("--blue-b", type=float, help=f"its blue b cut (default {P.BLUE_B})")

    r = sub.add_parser("run", help="decode and accumulate, window by window (resumable)")
    common(r)
    r.add_argument("--cog", required=True, help="the folder for the 2 m parts and COG (the cold drive)")
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--bounds", help="west,south,east,north in grid metres: a partial run, for a look")
    r.add_argument("--limit", type=int, help="at most this many windows this time")
    r.add_argument("--no-hashes", action="store_true", help="skip the inputs' sha256 (tests)")
    c = sub.add_parser("calibrate", help="the ten-box calibration against the class mask")
    common(c)
    lc = "/srv/landcover"
    c.add_argument("--classes", default=f"{lc}/exp/july/classes", help="exp31's <box>_J.npy")
    c.add_argument("--windows", default=f"{lc}/exp/search", help="<box>.json with each class window's window_rc")
    c.add_argument("--shifts", default=f"{lc}/exp/lone/candidates.json", help="the NAIP-to-lidar shifts per box")
    c.add_argument("--naip2023", default=f"{lc}/naip2023", help="NAIP 2023 crops for boxes h, i and j")
    c.add_argument("--explore", action="store_true", help="also each class's L, chroma and b percentiles")
    f = sub.add_parser("finish", help="merge, pool, check; then the COG")
    f.add_argument("--out", required=True)
    f.add_argument("--cog", help="the COG folder (default: the run's)")
    f.add_argument("--tmp", default=None)
    f.add_argument("--no-cog", action="store_true", help="stats only")
    f.add_argument("--allow-missing", action="store_true", help="pool what's done (a partial look)")
    args = ap.parse_args(argv)
    try:
        return {"run": cmd_run, "finish": cmd_finish, "calibrate": cmd_calibrate}[args.cmd](args)
    except (StatsError, P.PhotoError, M.ManifestError, MK.MaskError) as err:
        print(f"photo_stats: {err}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
