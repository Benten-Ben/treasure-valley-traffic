"""Image sheets for review: export layers and rasters drawn over the aerial photo, at the places the landscape sprint
checks (basemap/sheets/README.md). Runs in the worker image (GDAL, NumPy, Pillow); on the VM through
/srv/tvt/work/bin/sheets, which writes to the private files.

    python -m basemap.sheets.sheet draw --places cameras --layer roads/surfaces,by=material --out /out
    python -m basemap.sheets.sheet draw --places boxes --raster /in/0/classes_c.tif,kind=cat --label masks
    python -m basemap.sheets.sheet draw --places spots --list          # what it would draw, nothing written

What it reads:
- **the photo:** in the ten test boxes, the NAIP crops the land-cover spike cut ($TVT_NAIP_CROPS/naip2025/<box>.tif,
  0.3 m, or naip2023/ for h, i and j); elsewhere the map's own imagery tiles ($TVT_TILES: imagery.pmtiles, NAIP 2023
  to z14, and imagery-detail.pmtiles, NAIP 2025 at z15-z18), composed coarse to fine and warped to the frame;
- **export layers** (`--layer plugin/layer[@build]`, or `plugin/*` for all of an export's layers as one overlay) from
  $TVT_ARCHIVE through basemap/ground/manifest.py, so their files are checked and their credit, licence and
  republish travel with them; FlatGeobuf layers draw as vectors, GeoTIFF layers as rasters;
- **any vector or raster file** (`--vector PATH`, `--raster PATH`), with `credit=`, `licence=` and `republish=` given
  by hand; a file without `republish=` counts as "unstated", the strictest, on every sheet that draws it.

Each frame gives `<frame id>.png`: the photo beside the photo with the overlays (or the photo alone without any), a
scale bar, a legend with what each overlay drew in the frame, and the credits. Each group of frames gives a contact
sheet, `contact-<group>.png`. `index.json` records every input (paths, builds, sha256, licences) and what each frame
drew; `index.html` links them. Everything goes in a new folder, `<out>/<UTC time>[-label]/`.

Style options follow a layer, comma-separated (`--layer roads/surfaces,by=material,fill=0.4`):
  by=FIELD     colour by a field's values (vectors); a raster with value labels in its manifest is categorical
  color=#hex   one colour (default: the next of the overlay colours)
  fill=0..1    polygon fill opacity (default 0.25; 0.35 with by=; 0 for outlines only)
  width=PX     line and outline width (default 2)      size=PX   point radius (default 4)
  label=FIELD  write a field's value on each feature (at most 300 a frame)
  where=SQL    an OGR attribute filter (no commas)      name=TEXT the legend's name
  layer=NAME   the layer of a multi-layer vector file   band=N    a raster's band (default 1)
  kind=cat|ramp|rgb, min=, max=, clip=1 (clear outside min-max), alpha=0..1 (rasters; default 0.6, rgb 1):
               rgb draws bands 1-3 as they are (a painted picture, such as the ground's tiles)
  credit=TEXT  the credit of a file outside an export
  licence=L    its licence class (basemap/ground/manifest.py's LICENCES; republish defaults to the loosest it allows,
               except none-stated)
  republish=R  what may be published from it: yes, aggregates, internal or no (default: unstated)
"""

import argparse
import datetime as dt
import glob
import html
import io
import json
import math
import os
import re
import sys
import time

import numpy as np
from osgeo import gdal, gdal_array, ogr, osr
from PIL import Image, ImageDraw, ImageFont

from basemap.ground import grid, manifest
from basemap.ground import rasterize as R          # imported for its datum policy (PROJ's network off) too
from basemap.sheets import places as P
from basemap.sheets import pmtiles as PM

gdal.UseExceptions()
ogr.UseExceptions()
gdal.SetCacheMax(128 * 2**20)

VERSION = 1
INK = (20, 24, 32)
MUTED = (88, 92, 102)
BG = (250, 248, 244)
FLAT = (0xEE, 0xE7, 0xDA)                 # the flat Valley ground: where there's no photo
# Overlay colours (Okabe-Ito, plus white): told apart without red against green; the legend names each.
OVERLAY = ["#E69F00", "#56B4E9", "#CC79A7", "#F0E442", "#FFFFFF", "#0072B2", "#D55E00", "#009E73"]
# Category colours: Okabe-Ito, then Paul Tol's bright and light sets; past 20, generated hues.
CATEGORY = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#FFFFFF",
            "#4477AA", "#66CCEE", "#228833", "#CCBB44", "#EE6677", "#AA3377", "#BBBBBB", "#77AADD",
            "#EE8866", "#EEDD88", "#FFAABB", "#99DDFF"]
RAMP = np.array([(68, 1, 84), (59, 81, 139), (33, 144, 141), (92, 200, 99), (253, 231, 37)], float)   # viridis


def _ramp_lut(n=256):
    """(n, 3) uint8: the ramp sampled at n steps (a raster's cells index it, so no full-size float temporaries)."""
    t = np.linspace(0, len(RAMP) - 1, n)
    i = np.minimum(t.astype(int), len(RAMP) - 2)
    f = (t - i)[:, None]
    return (RAMP[i] * (1 - f) + RAMP[i + 1] * f).round().astype(np.uint8)


RAMP_LUT = _ramp_lut()
STYLE_KEYS = {"by", "color", "fill", "width", "size", "label", "where", "name", "layer", "band", "kind", "min",
              "max", "clip", "alpha", "credit", "licence", "republish"}
FILE_ONLY = {"credit", "licence", "republish"}      # an export's come from its manifest
UNSTATED = "unstated"                              # a file overlay's republish when none is given: the strictest
MAX_LABELS = 300
# Pixels a side. Measured in the capped container (1 GB, no swap; Oct 11), both panels: before the photo was blended
# in place, 4,000 px over the imagery tiles peaked at about 1,035 MiB; now 3,000 px peaks at 422 MiB over the tiles
# with a vector overlay, and 610 MiB over a NAIP crop with a vector and a raster overlay (601 with three rasters: they
# don't add up). 4,000 px: 658 and 974 MiB, too close to the cap.
MAX_SIDE = 3000
MAX_FEATURES = 250_000
THUMB = 360
# Bytes a sheet's pixel may take at most, for the disk bound (an RGB PNG compresses to under 3 bytes a pixel; the
# VM's frames were 0.5-1.8; JPEG at quality 92 under 1).
BOUND_BPP = {"png": 3.0, "jpg": 1.0}


class SheetError(ValueError):
    pass


# --- fonts and drawing helpers -------------------------------------------------------------------------------------

_FONTS = {}


def font(size):
    if size not in _FONTS:
        try:
            _FONTS[size] = ImageFont.load_default(size=size)
        except TypeError:                              # Pillow before 10.1: one bitmap size
            _FONTS[size] = ImageFont.load_default()
    return _FONTS[size]


def rgb(hexcolor):
    h = hexcolor.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise SheetError(f"colour {hexcolor!r}: give #RRGGBB")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def wrap(draw, text, fnt, width):
    """Lines of text no wider than width pixels (breaking at spaces)."""
    out, line = [], ""
    for word in text.split(" "):
        trial = f"{line} {word}".strip()
        if line and draw.textlength(trial, font=fnt) > width:
            out.append(line)
            line = word
        else:
            line = trial
    if line:
        out.append(line)
    return out


def nice_length(metres):
    """The largest 1, 2 or 5 x 10^k not over metres."""
    if metres <= 0:
        return 0
    k = 10 ** math.floor(math.log10(metres))
    for m in (5, 2, 1):
        if m * k <= metres:
            return m * k
    return k


def scale_bar(img, res):
    """A scale bar (bottom left) and a north mark (top right) on a panel."""
    d = ImageDraw.Draw(img)
    w, h = img.size
    length = nice_length(w * res * 0.2)
    px = length / res
    f = font(14)
    label = f"{length:g} m" if length < 1000 else f"{length / 1000:g} km"
    x0, y0 = 12, h - 22
    d.rectangle([x0 - 6, y0 - 22, x0 + px + 8 + d.textlength(label, font=f) + 6, y0 + 10], fill=(255, 255, 255))
    d.rectangle([x0, y0, x0 + px, y0 + 5], fill=INK)
    d.rectangle([x0, y0, x0 + px / 2, y0 + 5], fill=(255, 255, 255), outline=INK)
    d.text((x0 + px + 8, y0 - 8), label, font=f, fill=INK)
    nx, ny = w - 24, 14
    d.rectangle([nx - 12, ny - 6, nx + 12, ny + 34], fill=(255, 255, 255))
    d.polygon([(nx, ny), (nx - 7, ny + 14), (nx + 7, ny + 14)], fill=INK)
    d.text((nx - 5, ny + 15), "N", font=f, fill=INK)


# --- the photo -----------------------------------------------------------------------------------------------------

def _mem(arr, transform, srs):
    """A MEM dataset over a (bands, rows, cols) uint8 array, without copying it (keep the array while the dataset is
    used); the last band alpha when there are 4."""
    ds = gdal_array.OpenArray(np.ascontiguousarray(arr))
    ds.SetGeoTransform(transform)
    ref = osr.SpatialReference()
    ref.SetFromUserInput(srs)
    ds.SetProjection(ref.ExportToWkt())
    if arr.shape[0] == 4:
        ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    return ds


def _blend(out, arr, cover):
    """Lay arr ((4, rows, cols) uint8, the last band alpha) over out ((3, rows, cols) float32) in place, a band at a
    time (no full-size RGB temporaries), and raise cover to its alpha."""
    a = arr[3].astype(np.float32)
    a *= 1 / 255
    tmp = np.empty_like(a)
    for b in range(3):
        np.subtract(arr[b], out[b], out=tmp)
        tmp *= a
        out[b] += tmp
    np.maximum(cover, a, out=cover)


def _warp_rgba(src, frame, src_srs=None, resample="bilinear"):
    """src (a dataset with an alpha band, or none) warped onto the frame: (4, rows, cols) uint8."""
    w = frame.window
    out = gdal.Warp("", src, format="MEM", dstSRS=R.warp_srs(grid.CRS), srcSRS=src_srs,
                    outputBounds=w.bounds, width=w.width, height=w.height, resampleAlg=resample,
                    dstAlpha=True, multithread=False)
    arr = out.ReadAsArray()
    if arr.shape[0] == 2:                                    # one band + alpha (grey)
        arr = np.stack([arr[0], arr[0], arr[0], arr[1]])
    return arr[-4:] if arr.shape[0] >= 4 else np.concatenate([arr, np.full((1,) + arr.shape[1:], 255, np.uint8)])


class Photos:
    """The photo under each frame: a NAIP crop where one covers it, otherwise the map's imagery tiles."""

    def __init__(self, tiles_dir=None, naip_dir=None):
        self.tiles_dir, self.naip_dir = tiles_dir, naip_dir
        self.crops = self._find_crops(naip_dir) if naip_dir else []
        self.levels, self.tiles_note = self._find_tiles(tiles_dir) if tiles_dir else ([], None)
        self._readers = {}

    @staticmethod
    def _find_crops(folder):
        out = []
        flights = {}
        try:
            with open(os.path.join(folder, "naip2025", "flights.json"), encoding="utf-8") as f:
                flights = {k: v.get("dates", []) for k, v in json.load(f).get("boxes", {}).items()}
        except (OSError, ValueError):
            pass
        for year in ("2025", "2023"):
            for path in sorted(glob.glob(os.path.join(folder, f"naip{year}", "*.tif"))):
                ds = gdal.Open(path)
                x0, rx, _, y0, _, ry = ds.GetGeoTransform()
                box = os.path.splitext(os.path.basename(path))[0]
                dates = flights.get(box, []) if year == "2025" else []
                if year == "2023":
                    try:
                        with open(path[:-4] + ".json", encoding="utf-8") as f:
                            dates = list(json.load(f).get("acquired") or [])
                    except (OSError, ValueError, AttributeError, TypeError):
                        pass
                out.append({"path": path, "year": year, "box": box, "res": abs(rx), "crs": ds.GetProjection(),
                            "bounds": (x0, y0 + ds.RasterYSize * ry, x0 + ds.RasterXSize * rx, y0),
                            "bands": ds.RasterCount, "dates": dates})
        return out

    @staticmethod
    def _find_tiles(folder):
        try:
            with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
        except (OSError, ValueError):
            return [], None
        im = m.get("imagery")
        if not im:
            return [], None
        size = int(im.get("tileSize", 512))
        levels = [{"file": im["file"], "min": im.get("minzoom", 0), "max": im.get("maxzoom", 14), "size": size,
                   "source": im.get("source", ""), "built": im.get("built", "")}]
        det = im.get("detail")
        if det:
            levels.append({"file": det["file"], "min": det.get("minzoom", 15), "max": det.get("maxzoom", 18),
                           "size": int(det.get("tileSize", size)), "source": det.get("source", ""),
                           "built": det.get("built", "")})
        note = "; ".join(f"{lv['file']} (z{lv['min']}-{lv['max']}): {lv['source']}" for lv in levels)
        return levels, f"{im.get('attribution', 'USDA NAIP')}: {note}"

    def reader(self, name):
        if name not in self._readers:
            self._readers[name] = PM.Reader(os.path.join(self.tiles_dir, name))
        return self._readers[name]

    def crop_for(self, frame):
        """(crop, share of the frame it covers) for the NAIP crop to draw the frame from, or (None, 0): the newest
        that covers at least 99% of it (crops are cut to the box, give or take a metre), else the one covering most,
        if that's at least half."""
        w, s, e, n = frame.bounds
        scored = []
        for c in self.crops:
            cw, cs, ce, cn = c["bounds"]
            ix = max(0.0, min(e, ce) - max(w, cw))
            iy = max(0.0, min(n, cn) - max(s, cs))
            share = ix * iy / ((e - w) * (n - s))
            whole = share >= 0.99
            scored.append((whole, c["year"] if whole else "", share, c))
        if not scored:
            return None, 0.0
        _whole, _year, share, best = max(scored, key=lambda x: x[:3])
        return (best, share) if share >= 0.5 else (None, 0.0)

    def render(self, frame):
        """((rows, cols, 3) uint8, info) for the frame."""
        w = frame.window
        out = np.empty((3, w.height, w.width), np.float32)          # planar, blended in place
        out[:] = np.array(FLAT, np.float32)[:, None, None]
        cover = np.zeros((w.height, w.width), np.float32)
        info = {"sources": []}
        crop, share = self.crop_for(frame)
        if crop is None or share < 0.999:
            self._tiles(frame, out, cover, info)
        if crop is not None:
            src = gdal.Translate("", crop["path"], format="VRT", bandList=[1, 2, 3], maskBand="mask")
            resample = "average" if frame.res >= 2 * crop["res"] else "bilinear"
            arr = _warp_rgba(src, frame, src_srs=R.warp_srs(crop["crs"]), resample=resample)
            src = None
            _blend(out, arr, cover)
            del arr
            when = f", flown {', '.join(crop['dates'])}" if crop["dates"] else ""
            info["sources"].insert(0, {"kind": "naip-crop", "file": os.path.relpath(crop["path"], self.naip_dir),
                                       "res": round(crop["res"], 3), "share": round(share, 4)})
            info["photo"] = f"NAIP {crop['year']} crop of box {crop['box']} ({crop['res']:.1f} m{when})"
            info["credit"] = f"Photo: USDA NAIP {crop['year']} (public domain)"
        elif info["sources"]:
            zs = sorted({z for s in info["sources"] for z in s["zooms"]})
            info["photo"] = f"the map's imagery tiles, z{zs[0]}-{zs[-1]}"
            info["credit"] = "Photo: USDA NAIP (public domain), from the map's imagery tiles"
        else:
            info["photo"] = "no photo here (flat ground colour)"
            info["credit"] = ""
        info["covered"] = round(float(cover.mean()), 4)
        del cover
        img = np.empty((w.height, w.width, 3), np.uint8)
        for b in range(3):
            np.clip(out[b], 0, 255, out=out[b])
            np.rint(out[b], out=out[b])
            img[..., b] = out[b]
        return img, info

    def _tiles(self, frame, out, cover, info):
        if not self.levels:
            return
        w, s, e, n = grid.lonlat_of(frame.bounds)
        lat = (s + n) / 2
        top = max(lv["max"] for lv in self.levels)
        size = self.levels[-1]["size"]
        want = next((z for z in range(0, top + 1) if PM.pixel_m(z, lat, size) <= frame.res * 1.05), top)
        x0, y0 = PM.lonlat_to_xy(w, n)
        x1, y1 = PM.lonlat_to_xy(e, s)
        for lv in self.levels:
            zooms = [z for z in range(lv["min"], lv["max"] + 1) if z <= want]
            if lv is self.levels[0]:
                zooms = zooms[-1:]                            # the valley layer only once, at its best zoom
            used = []
            for z in zooms:
                got = self._compose(lv["file"], z, (x0, y0, x1, y1), lat, frame, out, cover)
                if got:
                    used.append(z)
                    info["sources"].append({"kind": "tiles", "file": lv["file"], "zooms": [z], "tiles": got})
            if used:
                info.setdefault("tiles_note", self.tiles_note)

    def _compose(self, name, z, xy_bounds, lat, frame, out, cover):
        """Warp level z of an archive onto the frame and lay it over `out`; returns the tiles used."""
        try:
            r = self.reader(name)
        except (OSError, PM.PMTilesError):
            return 0
        x0, y0, x1, y1 = xy_bounds
        c0, r0 = (int(math.floor(v)) for v in PM.tile_of(x0, y0, z))
        c1, r1 = (int(math.floor(v)) for v in PM.tile_of(x1, y1, z))
        n = 1 << z
        c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, n - 1), min(r1, n - 1)
        if (c1 - c0 + 1) * (r1 - r0 + 1) > 400:
            return 0                                          # far too many tiles for one frame at this zoom
        size, mosaic, used = None, None, 0
        for ty in range(r0, r1 + 1):
            for tx in range(c0, c1 + 1):
                data = r.get(z, tx, ty)
                if not data:
                    continue
                im = Image.open(io.BytesIO(data)).convert("RGBA")
                if size is None:
                    size = im.size[0]
                    mosaic = np.zeros((4, (r1 - r0 + 1) * size, (c1 - c0 + 1) * size), np.uint8)
                if im.size != (size, size):
                    im = im.resize((size, size))
                mosaic[:, (ty - r0) * size:(ty - r0 + 1) * size, (tx - c0) * size:(tx - c0 + 1) * size] = \
                    np.asarray(im).transpose(2, 0, 1)
                used += 1
        if not used:
            return 0
        tw, _ts, _te, tn = PM.tile_bounds(z, c0, r0)
        px = 2 * PM.HALF / n / size
        src = _mem(mosaic, (tw, px, 0, tn, 0, -px), "EPSG:3857")
        resample = "average" if frame.res >= 2 * PM.pixel_m(z, lat, size) else "bilinear"
        arr = _warp_rgba(src, frame, src_srs="EPSG:3857", resample=resample)
        src = mosaic = None                                   # the mosaic goes before the blend
        _blend(out, arr, cover)
        return used

    def close(self):
        for r in self._readers.values():
            r.close()
        self._readers = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# --- overlays ------------------------------------------------------------------------------------------------------

def parse_spec(text):
    """'REF[,key=value...]' -> (ref, {key: value}). A value may hold commas only if no key= follows them."""
    parts = re.split(r",(?=[a-z]+=)", text)
    ref, style = parts[0], {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        if k not in STYLE_KEYS:
            raise SheetError(f"{text!r}: unknown style option {k!r} (options: {', '.join(sorted(STYLE_KEYS))})")
        style[k] = v
    if not ref:
        raise SheetError(f"{text!r}: name a layer or file first")
    return ref, style


def _float(style, key, default, lo=None, hi=None):
    if key not in style:
        return default
    try:
        v = float(style[key])
    except ValueError:
        raise SheetError(f"{key}={style[key]!r}: not a number") from None
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise SheetError(f"{key}={style[key]!r}: out of range")
    return v


class Overlay:
    """One thing drawn over the photo: an export layer (or every layer of an export), or a file."""

    def __init__(self, kind, ref, parts, style, color, credit=(), licence=None, republish=None, inputs=None):
        self.kind, self.ref, self.parts, self.style = kind, ref, parts, style
        self.color = rgb(style["color"]) if "color" in style else rgb(color)
        self.credit, self.licence, self.republish, self.inputs = list(credit), licence, republish, inputs or []
        # republish None: nothing says what may be published from it, so it counts as the strictest (UNSTATED)
        self.name = style.get("name") or ref
        self.categories = {}                            # value -> colour, in order of first appearance
        self.labels = {}                                # value -> label (a raster's manifest "values")
        self.fill = _float(style, "fill", 0.35 if "by" in style else 0.25, 0, 1)
        self.width = _float(style, "width", 2.0, 0, 40)
        self.size = _float(style, "size", 4.0, 0, 40)
        self.alpha = _float(style, "alpha", 1.0 if style.get("kind") == "rgb" else 0.6, 0, 1)
        _float(style, "min", None)
        _float(style, "max", None)
        if kind == "raster" and style.get("kind") not in (None, "cat", "ramp", "rgb"):
            raise SheetError(f"{ref}: kind must be cat, ramp or rgb")

    def colour_of(self, value):
        if value not in self.categories:
            k = len(self.categories)
            if k < len(CATEGORY):
                c = rgb(CATEGORY[k])
            else:                                       # generated hues past the palette
                hue = (k * 0.618034) % 1
                c = tuple(int(255 * v) for v in _hsv(hue, 0.55, 0.95))
            self.categories[value] = c
        return self.categories[value]

    def describe(self):
        return {"ref": self.ref, "kind": self.kind, "name": self.name, "style": self.style,
                "color": "#%02x%02x%02x" % self.color, "files": [p["describe"] for p in self.parts],
                "credit": self.credit, "licence": self.licence or UNSTATED, "republish": self.republish or UNSTATED}


def strictest_drawn(overlays):
    """The strictest republish of what's drawn: UNSTATED when any overlay states none (a file without republish=),
    else manifest.strictest of theirs ("yes" for the photo alone: NAIP is public domain)."""
    if any(not ov.republish for ov in overlays):
        return UNSTATED
    return manifest.strictest(ov.republish for ov in overlays)


def _hsv(h, s, v):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]


def export_overlays(spec, archive, color, verify=True):
    """Overlays for '--layer plugin/layer[@build]' or 'plugin/*[@build]'."""
    ref, style = parse_spec(spec)
    given = sorted(FILE_ONLY & set(style))
    if given:
        raise SheetError(f"--layer {ref}: {', '.join(given)} come from the export's manifest (for --vector and "
                         "--raster only)")
    m = re.fullmatch(r"([a-z][a-z0-9_]*)/([A-Za-z0-9_.*-]+)(?:@([0-9TZ]+(?:-[a-z0-9-]+)?))?", ref)
    if not m:
        raise SheetError(f"--layer {ref!r}: give plugin/layer, plugin/layer@build or plugin/*")
    plugin, name, build = m.groups()
    if not archive or not os.path.isdir(archive):
        raise SheetError(f"--layer {ref}: no archive ({archive or 'set --archive or TVT_ARCHIVE'})")
    try:
        if build:
            man = manifest.read(manifest.export_dir(archive, plugin, build), verify=verify, hashes=verify)
        else:
            man = manifest.latest(archive, plugin, verify=verify, hashes=verify)
    except manifest.ManifestError as err:
        raise SheetError(f"--layer {ref}: {err}") from None
    if man is None:
        raise SheetError(f"--layer {ref}: {plugin} has no finished export under {archive}")
    layers = man.layers if name == "*" else [man.layer(name)] if man.has(name) else None
    if layers is None:
        raise SheetError(f"--layer {ref}: {plugin}@{man.build} has no layer {name!r} "
                         f"(it has {', '.join(lay.name for lay in man.layers)})")
    drawable = [lay for lay in layers if lay["format"] in ("FlatGeobuf", "GeoTIFF")]
    if not drawable:
        raise SheetError(f"--layer {ref}: {', '.join(lay['format'] for lay in layers)} isn't drawn (a table, not a map)")
    kinds = {lay["format"] for lay in drawable}
    if len(kinds) > 1:
        raise SheetError(f"--layer {ref}: mixes vectors and rasters; name the layers one at a time")
    kind = "vector" if kinds == {"FlatGeobuf"} else "raster"
    parts = [{"path": lay.path, "layer": None, "spec": lay.spec,
              "describe": {"layer": lay.ref, "path": lay.path, "sha256": lay["sha256"], "bytes": lay["bytes"]}}
             for lay in drawable]
    credit = list(dict.fromkeys(c for lay in drawable for c in lay["credit"]))
    licences = sorted({lay["licence"] for lay in drawable})
    shown = f"{plugin}/{name}@{man.build}"
    ov = Overlay(kind, shown, parts, style, color, credit=credit, licence=", ".join(licences),
                 republish=manifest.strictest(lay["republish"] for lay in drawable))
    if kind == "raster":
        band = int(style.get("band", 1))
        for lay in drawable:
            bands = lay.spec.get("bands") or []
            if len(bands) >= band:
                for code, label in (bands[band - 1].get("values") or {}).items():
                    ov.labels[_code(code)] = str(label)
    return [ov]


def _code(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return v


def file_overlay(spec, kind, color):
    """An overlay for '--vector PATH' or '--raster PATH'."""
    path, style = parse_spec(spec)
    if not os.path.exists(path):
        raise SheetError(f"--{kind} {path}: no such file")
    describe = {"path": path, "bytes": os.path.getsize(path) if os.path.isfile(path) else None,
                "sha256": manifest.sha256_of(path) if os.path.isfile(path) else None}
    try:
        if kind == "vector":
            ds = ogr.Open(path)
            if ds is None or (style.get("layer") and ds.GetLayerByName(style["layer"]) is None):
                raise SheetError(f"--vector {path}: no layer {style.get('layer') or ''}")
        else:
            gdal.Open(path)
    except RuntimeError as err:
        raise SheetError(f"--{kind} {path}: {err}") from None
    credit = [style["credit"]] if style.get("credit") else []
    licence, republish = file_rights(f"--{kind} {path}", style)
    return Overlay(kind, path, [{"path": path, "layer": style.get("layer"), "spec": {}, "describe": describe}],
                   style, color, credit=credit, licence=licence, republish=republish)


def file_rights(where, style):
    """(licence, republish) a file overlay's style states: republish= as given (no looser than licence= allows), or the
    loosest its licence allows, or None (unstated) without either, or with a per-source licence (none-stated)."""
    licence, republish = style.get("licence") or None, style.get("republish") or None
    if licence is not None and licence not in manifest.LICENCES:
        raise SheetError(f"{where}: licence={licence!r}: one of {', '.join(manifest.LICENCES)}")
    if republish is not None and republish not in manifest.REPUBLISH:
        raise SheetError(f"{where}: republish={republish!r}: one of {', '.join(manifest.REPUBLISH)}")
    if licence is not None:
        lic = manifest.LICENCES[licence]
        if republish is None and not lic.per_source:
            republish = lic.loosest
        elif republish is not None and manifest.rank(republish) < manifest.rank(lic.loosest):
            raise SheetError(f"{where}: republish={republish} is looser than {licence} allows ({lic.loosest})")
    return licence, republish


# --- drawing vectors -----------------------------------------------------------------------------------------------

def _transform_to_grid(srs):
    """A transformation from a layer's CRS to the grid's (None when they're the same under the datum policy)."""
    if srs is None:
        return None, None
    src = R.srs_of(srs)
    dst = R.srs_of(grid.CRS)
    if src.IsSame(dst):
        return None, None
    return osr.CoordinateTransformation(src, dst), osr.CoordinateTransformation(dst, src)


def _rings(geom):
    """Yield (kind, [rings]) for each simple part: ('polygon', [exterior, holes...]), ('line', [pts]),
    ('point', [pts])."""
    t = ogr.GT_Flatten(geom.GetGeometryType())
    if t in (ogr.wkbPolygon, ogr.wkbCurvePolygon):
        g = geom.GetLinearGeometry() if t == ogr.wkbCurvePolygon else geom
        yield "polygon", [g.GetGeometryRef(i).GetPoints() or [] for i in range(g.GetGeometryCount())]
    elif t in (ogr.wkbLineString, ogr.wkbCircularString, ogr.wkbCompoundCurve):
        g = geom.GetLinearGeometry() if t != ogr.wkbLineString else geom
        yield "line", [g.GetPoints() or []]
    elif t == ogr.wkbPoint:
        yield "point", [[geom.GetPoint_2D()]]
    elif t in (ogr.wkbMultiPolygon, ogr.wkbMultiLineString, ogr.wkbMultiPoint, ogr.wkbGeometryCollection,
               ogr.wkbMultiSurface, ogr.wkbMultiCurve):
        for i in range(geom.GetGeometryCount()):
            yield from _rings(geom.GetGeometryRef(i))


def draw_vector(ov, frame, ss):
    """(RGBA image at ss times the frame's size, labels, stats) for a vector overlay."""
    w = frame.window
    W, H = w.width * ss, w.height * ss
    fill_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    line_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd, ld = ImageDraw.Draw(fill_img), ImageDraw.Draw(line_img)
    west, south, east, north = w.bounds
    k = ss / w.res
    by, label_field = ov.style.get("by"), ov.style.get("label")
    width = max(1, round(ov.width * ss))
    radius = ov.size * ss
    fill_a = round(ov.fill * 255)
    stats = {"features": 0, "categories": {}}
    labels = []

    def px(pts):
        return [((x - west) * k, (north - y) * k) for x, y, *_ in pts]

    for part in ov.parts:
        ds = ogr.Open(part["path"])
        lyr = ds.GetLayerByName(part["layer"]) if part.get("layer") else ds.GetLayer(0)
        fwd, back = _transform_to_grid(lyr.GetSpatialRef())
        pad = 2 * w.res
        if back is None:
            lyr.SetSpatialFilterRect(west - pad, south - pad, east + pad, north + pad)
        else:
            corners = [back.TransformPoint(x, y)[:2] for x in (west - pad, east + pad) for y in (south - pad, north + pad)]
            xs, ys = [c[0] for c in corners], [c[1] for c in corners]
            lyr.SetSpatialFilterRect(min(xs), min(ys), max(xs), max(ys))
        if ov.style.get("where"):
            try:
                lyr.SetAttributeFilter(ov.style["where"])
            except RuntimeError as err:
                raise SheetError(f"{ov.ref}: where={ov.style['where']!r}: {err}") from None
        defn = lyr.GetLayerDefn()
        for fld in (by, label_field):
            if fld and defn.GetFieldIndex(fld) < 0:
                names = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
                raise SheetError(f"{ov.ref}: no field {fld!r} (fields: {', '.join(names)})")
        for feat in lyr:
            geom = feat.GetGeometryRef()
            if geom is None or geom.IsEmpty():
                continue
            if fwd is not None:
                geom = geom.Clone()
                geom.Transform(fwd)
            stats["features"] += 1
            if stats["features"] > MAX_FEATURES:
                raise SheetError(f"{ov.ref}: over {MAX_FEATURES} features in {frame.id}; use where= or a smaller "
                                 "frame")
            value = _code(feat.GetField(by)) if by else None
            colour = ov.colour_of(value) if by else ov.color
            if by:
                stats["categories"][value] = stats["categories"].get(value, 0) + 1
            for kind, rings in _rings(geom):
                if kind == "polygon" and rings and len(rings[0]) >= 3:
                    ext = px(rings[0])
                    if fill_a:
                        fd.polygon(ext, fill=colour + (fill_a,))
                        for hole in rings[1:]:
                            if len(hole) >= 3:
                                fd.polygon(px(hole), fill=(0, 0, 0, 0))
                    for ring in rings:
                        if len(ring) >= 2:
                            pr = px(ring)
                            ld.line(pr + pr[:1], fill=colour + (255,), width=width, joint="curve")
                elif kind == "line" and len(rings[0]) >= 2:
                    ld.line(px(rings[0]), fill=colour + (255,), width=width, joint="curve")
                elif kind == "point":
                    for x, y in px(rings[0]):
                        ld.ellipse([x - radius, y - radius, x + radius, y + radius], fill=colour + (255,),
                                   outline=(20, 24, 32, 255), width=max(1, ss))
            if label_field and len(labels) < MAX_LABELS:
                text = feat.GetField(label_field)
                if text not in (None, ""):
                    try:
                        p = geom.PointOnSurface() if ogr.GT_Flatten(geom.GetGeometryType()) in (
                            ogr.wkbPolygon, ogr.wkbMultiPolygon) else geom.Centroid()
                    except RuntimeError:
                        p = geom.Centroid()
                    if p is not None and not p.IsEmpty():
                        x, y = p.GetX(), p.GetY()
                        if west <= x <= east and south <= y <= north:
                            labels.append(((x - west) / w.res, (north - y) / w.res, str(text)))
    return Image.alpha_composite(fill_img, line_img), labels, stats


def draw_labels(img, labels):
    d = ImageDraw.Draw(img)
    f = font(13)
    taken = []
    for x, y, text in labels:
        tw = d.textlength(text, font=f)
        box = (x - tw / 2 - 2, y - 9, x + tw / 2 + 2, y + 9)
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in taken):
            continue
        taken.append(box)
        d.text((x - tw / 2, y - 8), text, font=f, fill=INK, stroke_width=2, stroke_fill=(255, 255, 255))


# --- drawing rasters -----------------------------------------------------------------------------------------------

def draw_rgb(ov, frame):
    """(RGBA image at the frame's size, stats) for a kind=rgb raster: bands 1-3 as colours (bilinear), at the
    overlay's alpha where the raster has data."""
    w = frame.window
    rgba = np.zeros((w.height, w.width, 4), np.uint8)
    stats = {"cells": 0, "categories": {}}
    for part in ov.parts:
        ds = gdal.Open(part["path"])
        if ds.RasterCount < 3 or gdal.GetDataTypeName(ds.GetRasterBand(1).DataType) != "Byte":
            raise SheetError(f"{ov.ref}: kind=rgb needs three 8-bit bands; {part['path']} has {ds.RasterCount}")
        src = gdal.Translate("", ds, format="VRT", bandList=[1, 2, 3])
        out = gdal.Warp("", src, format="MEM", srcSRS=R.warp_srs(ds.GetProjection()), dstSRS=R.warp_srs(grid.CRS),
                        outputBounds=w.bounds, width=w.width, height=w.height, resampleAlg="bilinear",
                        dstAlpha=True, multithread=False)
        arr = out.ReadAsArray()
        valid = arr[3] > 0
        if not valid.any():
            continue
        for b in range(3):
            rgba[..., b][valid] = arr[b][valid]
        rgba[..., 3][valid] = round(ov.alpha * 255)
        stats["cells"] += int(valid.sum())
    return Image.fromarray(rgba, "RGBA"), stats


def draw_raster(ov, frame):
    """(RGBA image at the frame's size, stats) for a raster overlay."""
    if ov.style.get("kind") == "rgb":
        return draw_rgb(ov, frame)
    w = frame.window
    band = int(ov.style.get("band", 1))
    rgba = np.zeros((w.height, w.width, 4), np.uint8)
    stats = {"cells": 0, "categories": {}}
    for part in ov.parts:
        ds = gdal.Open(part["path"])
        if band > ds.RasterCount:
            raise SheetError(f"{ov.ref}: band {band}, but {part['path']} has {ds.RasterCount}")
        b = ds.GetRasterBand(band)
        nodata = b.GetNoDataValue()
        dtype = gdal.GetDataTypeName(b.DataType)
        integer = dtype.startswith(("Byte", "Int", "UInt"))
        cat = ov.style.get("kind") == "cat" or (ov.style.get("kind") != "ramp" and (bool(ov.labels) or integer))
        src = gdal.Translate("", ds, format="VRT", bandList=[band])
        out = gdal.Warp("", src, format="MEM", srcSRS=R.warp_srs(ds.GetProjection()), dstSRS=R.warp_srs(grid.CRS),
                        outputBounds=w.bounds, width=w.width, height=w.height,
                        resampleAlg="near" if cat else "bilinear", dstAlpha=True, multithread=False)
        arr = out.GetRasterBand(1).ReadAsArray()
        valid = out.GetRasterBand(2).ReadAsArray() > 0
        if nodata is not None:
            valid &= ~np.isclose(arr, nodata) if not integer else arr != nodata
        if not integer:
            valid &= np.isfinite(arr)
        if not valid.any():
            continue
        if cat and ov.style.get("kind") != "cat" and not ov.labels and len(np.unique(arr[valid])) > 64:
            cat = False                                   # too many values for a legend: a ramp instead
        if cat:
            vals, counts = np.unique(arr[valid], return_counts=True)
            for v, c in zip(vals.tolist(), counts.tolist()):
                v = _code(v)
                colour = ov.colour_of(v)
                sel = valid & (arr == v)
                rgba[sel, :3] = colour
                rgba[sel, 3] = round(ov.alpha * 255)
                stats["categories"][v] = stats["categories"].get(v, 0) + c
        else:
            lo = _float(ov.style, "min", None)
            hi = _float(ov.style, "max", None)
            if lo is None or hi is None:
                p2, p98 = np.percentile(arr[valid], [2, 98])
                lo = float(p2) if lo is None else lo
                hi = float(p98) if hi is None else hi
            if ov.style.get("clip"):
                with np.errstate(invalid="ignore"):
                    valid &= (arr >= lo) & (arr <= hi)
            # Only valid cells are coloured: an undeclared NaN never reaches the integer cast (on x86-64 NaN casts to
            # the most negative int64, which indexed the ramp out of bounds).
            t = arr[valid].astype(np.float32)
            t -= lo
            t *= (len(RAMP_LUT) - 1) / ((hi - lo) or 1)
            np.clip(t, 0, len(RAMP_LUT) - 1, out=t)
            t += 0.5
            rgba[valid, :3] = RAMP_LUT[t.astype(np.uint8)]
            rgba[valid, 3] = round(ov.alpha * 255)
            stats["ramp"] = [round(lo, 4), round(hi, 4)]
        stats["cells"] += int(valid.sum())
    return Image.fromarray(rgba, "RGBA"), stats


# --- one frame -----------------------------------------------------------------------------------------------------

def legend_rows(overlays, stats):
    """[(swatch kind, colour, text)] for a frame's legend."""
    rows = []
    for ov in overlays:
        st = stats.get(ov.ref, {})
        if ov.kind == "vector":
            n = st.get("features", 0)
            head = f"{ov.name}: {n} feature{'s' if n != 1 else ''} here"
        else:
            head = f"{ov.name}: {st.get('cells', 0):,} cells here"
        cats = st.get("categories") or {}
        rows.append(("head", None if cats or st.get("ramp") else ov.color, head))
        if st.get("ramp"):
            lo, hi = st["ramp"]
            clip = ", clear outside" if ov.style.get("clip") else ""
            rows.append(("ramp", None, f"{lo:g} to {hi:g}{clip}"))
        if cats:
            items = sorted(cats.items(), key=lambda kv: -kv[1])
            for value, count in items[:24]:
                shown = "(empty)" if value is None else f"{value}: {ov.labels[value]}" if value in ov.labels else value
                rows.append(("cat", ov.categories.get(value, ov.color), f"{shown} ({count:,})"))
            if len(items) > 24:
                rows.append(("more", None, f"and {len(items) - 24} more values"))
    return rows


def compose(frame, photo, overlays, stats, layer_img, labels, info, run, panels):
    """The frame's sheet: header, panels, legend and credits."""
    h, w = photo.shape[:2]
    base = Image.fromarray(photo, "RGB").convert("RGBA")
    shown = []
    if "photo" in panels or not overlays:
        p = base.copy()
        scale_bar(p, frame.res)
        shown.append(("photo: " + info["photo"], p))
    if overlays and "overlay" in panels:
        o = Image.alpha_composite(base, layer_img)
        draw_labels(o, labels)
        scale_bar(o, frame.res)
        shown.append(("with the overlays", o))
    gap, m = 16, 16
    width = max(len(shown) * w + (len(shown) - 1) * gap + 2 * m, 900)
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    rows = legend_rows(overlays, stats)
    f_title, f_text, f_small = font(26), font(16), font(14)
    lon, lat = frame.lonlat
    size_m = frame.window.width * frame.res
    sub = (f"{frame.id}; {size_m:g} m square at {frame.res:g} m a pixel; centre {lat:.5f}, {lon:.5f}; "
           f"{frame.note}")
    sub_lines = wrap(scratch, sub, f_text, width - 2 * m)
    credits = credit_line(overlays, info)
    credit_lines = wrap(scratch, credits, f_small, width - 2 * m)
    leg_cols = max(1, (width - 2 * m) // 420)
    per_col = max(math.ceil(len(rows) / leg_cols), min(len(rows), 8)) if rows else 0
    leg_h = per_col * 22
    top = m + 36 + 22 * len(sub_lines) + 8
    height = top + 26 + h + 12 + leg_h + 10 + 19 * len(credit_lines) + m
    sheet = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(sheet)
    d.text((m, m), frame.name, font=f_title, fill=INK)
    if run.get("title"):
        tw = d.textlength(run["title"], font=f_text)
        d.text((width - m - tw, m + 8), run["title"], font=f_text, fill=MUTED)
    y = m + 36
    for line in sub_lines:
        d.text((m, y), line, font=f_text, fill=MUTED)
        y += 22
    for i, (caption, img) in enumerate(shown):
        x = m + i * (w + gap)
        d.text((x, top), caption, font=f_small, fill=INK)
        sheet.paste(img.convert("RGB"), (x, top + 22))
    y = top + 26 + h + 12
    col_w = (width - 2 * m) // leg_cols
    for i, (kind, colour, text) in enumerate(rows):
        cx = m + (i // per_col) * col_w
        cy = y + (i % per_col) * 22
        indent = 0 if kind == "head" else 18
        if colour is not None:
            d.rectangle([cx + indent, cy + 2, cx + indent + 16, cy + 16], fill=colour, outline=INK)
            indent += 22
        elif kind == "ramp":
            for k in range(60):
                t = k / 59 * (len(RAMP) - 1)
                j = min(int(t), len(RAMP) - 2)
                c = RAMP[j] * (1 - (t - j)) + RAMP[j + 1] * (t - j)
                d.line([cx + indent + k, cy + 2, cx + indent + k, cy + 16], fill=tuple(int(v) for v in c))
            d.rectangle([cx + indent, cy + 2, cx + indent + 59, cy + 16], outline=INK)
            indent += 66
        fnt = f_small if kind != "head" else f_text
        while len(text) > 8 and d.textlength(text, font=fnt) > col_w - indent - 8:
            text = text[:-4].rstrip() + "..."
        d.text((cx + indent, cy + 1), text, font=fnt, fill=INK)
    y += leg_h + 10
    for line in credit_lines:
        d.text((m, y), line, font=f_small, fill=MUTED)
        y += 19
    return sheet, shown[-1][1], [caption for caption, _img in shown]


def credit_line(overlays, info):
    parts = []
    if info.get("credit"):
        parts.append(info["credit"] + ".")
    seen = []
    for ov in overlays:
        for c in ov.credit:
            if c not in seen:
                seen.append(c)
    if seen:
        parts.append("Overlays: " + "; ".join(seen) + ".")
    parts.append("Places: © OpenStreetMap contributors.")
    worst = strictest_drawn(overlays)
    stated = "" if worst != UNSTATED else ", as a file drawn here doesn't say what may be published"
    parts.append(f"A private review sheet, not for publication (the strictest republish drawn here: {worst}{stated}).")
    return " ".join(parts)


def draw_frame(frame, photos, overlays, run, panels):
    """(sheet image, thumbnail panel, record) for one frame."""
    t0 = time.monotonic()
    photo, info = photos.render(frame)
    w = frame.window
    ss = 2 if max(w.width, w.height) <= 2000 else 1
    layer_img = Image.new("RGBA", (w.width, w.height), (0, 0, 0, 0))
    stats, labels = {}, []
    for ov in overlays:
        if ov.kind == "vector":
            img, lab, st = draw_vector(ov, frame, ss)
            if ss > 1:
                img = img.resize((w.width, w.height), Image.LANCZOS)
            labels += lab
        else:
            img, st = draw_raster(ov, frame)
        layer_img = Image.alpha_composite(layer_img, img)
        stats[ov.ref] = st
    sheet, panel, captions = compose(frame, photo, overlays, stats, layer_img, labels, info, run, panels)
    record = dict(frame.describe())
    record.update({"photo": info["photo"], "photo_sources": info["sources"], "photo_covered": info["covered"],
                   "panels": captions, "overlays": stats, "seconds": round(time.monotonic() - t0, 2)})
    return sheet, panel, record


# --- contact sheets and the index ----------------------------------------------------------------------------------

def contact_sheet(group, items, overlays, run):
    """A grid of thumbnails (frame id and name under each)."""
    cols = min(6, max(1, len(items)))
    rows = math.ceil(len(items) / cols)
    m, gap, cap = 16, 12, 38
    width = 2 * m + cols * THUMB + (cols - 1) * gap
    title = f"{run.get('title') or 'Sheets'}: {group} ({len(items)} frame{'s' if len(items) != 1 else ''})"
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    names = [f"{ov.name} ({'#%02x%02x%02x' % ov.color})" for ov in overlays]
    sub = f"run {run['run']}; " + ("overlays: " + "; ".join(names) if names else "the photo only")
    sub_lines = wrap(scratch, sub, font(14), width - 2 * m)
    # the frames' credits: the photo (NAIP crops or the map's NAIP tiles), every overlay's, the strictest republish
    foot = credit_line(overlays, {"credit": "Photo: USDA NAIP (public domain)"})
    foot_lines = wrap(scratch, foot, font(13), width - 2 * m)
    head = m + 34 + 19 * len(sub_lines) + 8
    height = head + rows * (THUMB + cap + gap) + 12 + 18 * len(foot_lines) + m
    sheet = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(sheet)
    d.text((m, m), title, font=font(24), fill=INK)
    y = m + 34
    for line in sub_lines:
        d.text((m, y), line, font=font(14), fill=MUTED)
        y += 19
    for i, (frame, panel) in enumerate(items):
        r, c = divmod(i, cols)
        x, y = m + c * (THUMB + gap), head + r * (THUMB + cap + gap)
        if panel is not None:
            t = panel.convert("RGB")
            t.thumbnail((THUMB, THUMB), Image.LANCZOS)
            sheet.paste(t, (x, y))
        else:
            d.rectangle([x, y, x + THUMB, y + THUMB], outline=INK)
            d.text((x + 8, y + 8), "failed: see index.json", font=font(14), fill=INK)
        name = frame.name if d.textlength(frame.name, font=font(13)) < THUMB else frame.name[:44] + "..."
        d.text((x, y + THUMB + 3), frame.id, font=font(14), fill=INK)
        d.text((x, y + THUMB + 20), name, font=font(13), fill=MUTED)
    y = height - m - 18 * len(foot_lines)
    for line in foot_lines:
        d.text((m, y), line, font=font(13), fill=MUTED)
        y += 18
    return sheet


def save_index(folder, index):
    """Write index.json (by rename): after every frame, so a run that's stopped or killed still says what it drew."""
    tmp = os.path.join(folder, ".index.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, os.path.join(folder, "index.json"))


def write_html(folder, index):
    rows = []
    for g in index["contact_sheets"]:
        rows.append(f'<h2>{html.escape(g["group"])}</h2>' + (
            f'<p><a href="{html.escape(g["file"])}"><img src="{html.escape(g["file"])}" style="max-width:100%"></a>'
            "</p><ul>" if g.get("file") else f"<p>(its contact sheet failed: {html.escape(g.get('error', ''))})</p><ul>"))
        for fr in index["frames"]:
            if fr["group"] == g["group"]:
                link = (f'<a href="{html.escape(fr["file"])}">{html.escape(fr["id"])}</a>' if fr.get("file")
                        else html.escape(fr["id"]) + " (failed)")
                rows.append(f"<li>{link}: {html.escape(fr['name'])}</li>")
        rows.append("</ul>")
    ovs = "".join(f"<li>{html.escape(o['ref'])}: {html.escape('; '.join(o['credit']))} "
                  f"({html.escape(str(o['licence']))}, republish {html.escape(str(o['republish']))})</li>"
                  for o in index["overlays"])
    page = (f"<!doctype html><meta charset=utf-8><title>Sheets {html.escape(index['run'])}</title>"
            f"<style>body{{font:15px/1.4 system-ui,sans-serif;margin:24px;background:#faf8f4;color:#141820}}</style>"
            f"<h1>{html.escape(index.get('title') or 'Sheets')}</h1><p>Run {html.escape(index['run'])}, "
            f"{len(index['frames'])} frames. A private review sheet, not for publication (the strictest republish "
            f"drawn: {html.escape(index['republish'])}).</p>"
            f"<ul>{ovs or '<li>the photo only</li>'}</ul>" + "".join(rows))
    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


def free_gb(where):
    st = os.statvfs(where)
    return st.f_bavail * st.f_frsize / 2**30


def bound_bytes(frames, panels, fmt, overlays):
    """At most how many bytes a run writes: each sheet at BOUND_BPP of its pixels (the panels plus the header,
    legend and credits around them), and the contact sheets."""
    n = len(panels) if overlays else 1
    total = 0
    for f in frames:
        w, h = f.window.width, f.window.height
        total += (max(n * w + (n - 1) * 16 + 32, 900)) * (h + 600) * BOUND_BPP[fmt]
    total += math.ceil(len(frames) / 6) * 6 * (THUMB + 62) ** 2 * 3 + 2e6          # contact sheets, index
    return int(total)


def run_id(label=None, when=None):
    stamp = (when or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    if label:
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40]
        if slug:
            return f"{stamp}-{slug}"
    return stamp


# --- the command ---------------------------------------------------------------------------------------------------

def build_overlays(args):
    overlays = []
    colours = iter(OVERLAY * 4)
    for spec in args.layer or []:
        overlays += export_overlays(spec, args.archive, next(colours), verify=not args.no_verify)
    for spec in args.vector or []:
        overlays.append(file_overlay(spec, "vector", next(colours)))
    for spec in args.raster or []:
        overlays.append(file_overlay(spec, "raster", next(colours)))
    refs = [ov.ref for ov in overlays]
    if len(refs) != len(set(refs)):
        raise SheetError("the same layer is named twice")
    return base_first(overlays)


def base_first(overlays):
    """A picture drawn as it is (kind=rgb, the painted ground) is a base: it goes under the data layers, whatever
    order the arguments came in (it is opaque, so drawn last it would hide them all). Otherwise the order stays."""
    return sorted(overlays, key=lambda ov: ov.style.get("kind") != "rgb")


def draw(args):
    frames = P.select(args.places, res=args.res, size=args.size)
    big = [f.id for f in frames if max(f.window.width, f.window.height) > MAX_SIDE]
    if big:
        raise SheetError(f"{', '.join(big[:5])}: over {MAX_SIDE} pixels a side (the run is capped at 1 GB of "
                         "memory); give a coarser --res or a smaller --size")
    if args.max_frames and len(frames) > args.max_frames:
        raise SheetError(f"{len(frames)} frames, over --max-frames {args.max_frames}")
    overlays = build_overlays(args)
    panels = set(args.panels.split(","))
    if not panels <= {"photo", "overlay"}:
        raise SheetError("--panels takes photo, overlay or photo,overlay")
    if args.out and args.min_free_gb and not args.list:
        need = bound_bytes(frames, panels, args.format, overlays) / 2**30
        have = free_gb(args.out)
        if have - need < args.min_free_gb + 1:
            raise SheetError(f"{len(frames)} frames could take up to {need:.1f} GB, and {have:.1f} GB is free: a run "
                             f"starts with {args.min_free_gb:g} + 1 GB left after it. Draw fewer places, or use "
                             "--panels overlay or --format jpg")
    with Photos(args.tiles, args.naip) as photos:
        return _draw(args, frames, overlays, panels, photos)


def _draw(args, frames, overlays, panels, photos):
    if args.list:
        for f in frames:
            crop, share = photos.crop_for(f)
            src = f"NAIP {crop['year']} crop {crop['box']} ({share:.0%})" if crop else (
                "imagery tiles" if photos.levels else "no photo")
            print(f"{f.id:16} {f.window.width:5} x {f.window.height:<5} px at {f.res:g} m  {src:28} {f.name}")
        for ov in overlays:
            print(f"overlay {ov.ref}: {ov.kind}, {len(ov.parts)} file(s), {ov.licence or 'licence unstated'}, "
                  f"republish {ov.republish or UNSTATED}")
        print(f"{len(frames)} frames; photo: {len(photos.crops)} NAIP crops, "
              f"{'imagery tiles' if photos.levels else 'no imagery tiles'}", file=sys.stderr)
        return 0
    if not args.out:
        raise SheetError("--out: where to write (a new run folder is made inside)")
    run = {"run": run_id(args.label), "title": args.title or args.label or ""}
    folder = os.path.join(args.out, run["run"])
    try:
        os.makedirs(folder)
    except FileExistsError:
        raise SheetError(f"{folder} exists already; wait a second or give another --label") from None
    index = {"tool": "basemap/sheets", "version": VERSION, "run": run["run"], "title": run["title"],
             "created": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "argv": sys.argv[1:], "places": {"file": "basemap/sheets/places.json",
                                              "credit": "© OpenStreetMap contributors"},
             "photo": {"tiles": photos.tiles_note, "naip_crops": [os.path.relpath(c["path"], args.naip)
                                                                   for c in photos.crops]},
             "overlays": [ov.describe() for ov in overlays],
             "republish": strictest_drawn(overlays),
             "frames": [], "contact_sheets": [], "failed": [], "complete": False}
    groups = {}
    t0 = time.monotonic()
    low = None
    for i, frame in enumerate(frames, 1):
        if low is None and args.min_free_gb:
            have = free_gb(folder)
            if have < args.min_free_gb:
                low = f"stopped drawing: {have:.1f} GB free, under {args.min_free_gb:g} GB"
                print(f"sheets: {low}", file=sys.stderr, flush=True)
        if low is not None:
            record = dict(frame.describe())
            record["error"] = f"not drawn: {low}"
            index["failed"].append(frame.id)
            groups.setdefault(frame.group, []).append((frame, None))
            index["frames"].append(record)
            continue
        try:
            sheet, panel, record = draw_frame(frame, photos, overlays, run, panels)
            name = f"{frame.id}.{args.format}"
            if args.format == "png":
                sheet.save(os.path.join(folder, name), compress_level=6)
            else:
                sheet.save(os.path.join(folder, name), quality=92, subsampling=0)
            record["file"] = name
            record["bytes"] = os.path.getsize(os.path.join(folder, name))
            thumb = panel.convert("RGB")
            thumb.thumbnail((THUMB, THUMB), Image.LANCZOS)
            sheet = panel = None                       # freed before the next frame is drawn
            groups.setdefault(frame.group, []).append((frame, thumb))
            print(f"sheets: {i}/{len(frames)} {frame.id}: {record['photo']}; {record['seconds']} s", flush=True)
        except Exception as err:                       # noqa: BLE001 - one bad frame is recorded; the run goes on
            record = dict(frame.describe())
            record["error"] = f"{type(err).__name__}: {err}"
            index["failed"].append(frame.id)
            groups.setdefault(frame.group, []).append((frame, None))
            print(f"sheets: {i}/{len(frames)} {frame.id}: FAILED: {err}", file=sys.stderr, flush=True)
        index["frames"].append(record)
        save_index(folder, index)
    for group, items in groups.items():
        name = f"contact-{group}.png"
        try:
            contact_sheet(group, items, overlays, run).save(os.path.join(folder, name))
            index["contact_sheets"].append({"group": group, "file": name, "frames": len(items)})
        except Exception as err:                       # noqa: BLE001 - the index is still written
            index["contact_sheets"].append({"group": group, "file": None, "frames": len(items),
                                            "error": f"{type(err).__name__}: {err}"})
            index["failed"].append(f"contact-{group}")
            print(f"sheets: contact sheet {group}: FAILED: {err}", file=sys.stderr, flush=True)
    index["seconds"] = round(time.monotonic() - t0, 1)
    index["bytes"] = sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder))
    index["complete"] = True
    save_index(folder, index)
    write_html(folder, index)
    drawn = sum(1 for r in index["frames"] if r.get("file"))
    print(f"sheets: {drawn} of {len(frames)} frames in {folder} "
          f"({index['bytes'] / 1e6:.1f} MB, {index['seconds']} s)")
    return 1 if index["failed"] else 0


def parser():
    p = argparse.ArgumentParser(prog="python -m basemap.sheets.sheet",
                                description="Draw export layers and rasters over the photo (README.md).")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw", help="draw sheets", formatter_class=argparse.RawDescriptionHelpFormatter,
                       description=__doc__.split("\n\n", 1)[1])
    d.add_argument("--places", nargs="+", default=["all"], metavar="SEL",
                   help="sets, place ids or at:LON,LAT[,SIZE_M[,RES_M]] (places.py; default all)")
    d.add_argument("--layer", action="append", metavar="PLUGIN/LAYER[@BUILD][,k=v...]",
                   help="an export layer (or plugin/* for all of one export's layers)")
    d.add_argument("--vector", action="append", metavar="PATH[,k=v...]", help="a vector file any OGR driver reads")
    d.add_argument("--raster", action="append", metavar="PATH[,k=v...]", help="a raster file GDAL reads")
    d.add_argument("--archive", default=os.environ.get("TVT_ARCHIVE"), help="exports (default $TVT_ARCHIVE)")
    d.add_argument("--tiles", default=os.environ.get("TVT_TILES"), help="the map's tiles folder ($TVT_TILES)")
    d.add_argument("--naip", default=os.environ.get("TVT_NAIP_CROPS"),
                   help="the NAIP crops: a folder with naip2025/ and naip2023/ ($TVT_NAIP_CROPS)")
    d.add_argument("--out", help="where the run's folder is made")
    d.add_argument("--label", help="a short name for the run (its folder's suffix)")
    d.add_argument("--title", help="a title on every sheet (default: the label)")
    d.add_argument("--res", type=float, help="metres a pixel for every frame (a level of the ground grid)")
    d.add_argument("--size", type=float, help="every frame's width in metres")
    d.add_argument("--panels", default="photo,overlay", help="photo,overlay (default), overlay or photo")
    d.add_argument("--format", choices=("png", "jpg"), default="png",
                   help="the frames' format (default png; jpg, at quality 92, is about a fifth of the size)")
    d.add_argument("--max-frames", type=int, default=120, help="refuse a run of more frames (default 120; all the "
                   "places are 94)")
    d.add_argument("--min-free-gb", type=float, default=float(os.environ.get("TVT_SHEETS_MIN_FREE_GB") or 0),
                   help="refuse a run unless this + 1 GB stays free after its frames' bound, and stop drawing under "
                   "it ($TVT_SHEETS_MIN_FREE_GB; the VM's runner sets heavy's 11)")
    d.add_argument("--no-verify", action="store_true", help="skip the exports' file checks (sizes, sha256)")
    d.add_argument("--list", action="store_true", help="list the frames, their photo and the overlays; draw nothing")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return draw(args)
    except (SheetError, P.PlaceError, ValueError) as err:
        print(f"sheets: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
