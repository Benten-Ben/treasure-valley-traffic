"""The painter (G1a): the ground's colours on any window of the grid. Runs in the worker image (GDAL, NumPy, SciPy).

    from basemap.ground import inputs, paint
    plan = inputs.resolve(inputs.exports(archive), versions=paint.versions(...))
    painter = paint.Painter.from_plan(plan)
    rgb = painter.paint(grid.window(bounds, 2.0))          # (rows, cols, 3) uint8 sRGB

What it paints, bottom to top (plan G1a, C7, C8; the soils, farm and osm-landscape designs' "ground" sections):

1. **The soil base.** Each soil polygon (soils' `ground.fgb`) in its ground type's colour: the palette's measured
   OKLab median (soils' `palette.json`, from NAIP 2025 over the type's uncovered ground), or a flat colour by texture
   where a type has none (status `none`) or there's no palette yet. report() lists those types, and notes() names
   them in the tiles entry's fallbacks and the PMTiles metadata (tilewrite.py). SSURGO's Water units yield to the
   water layer: they take the nearest soil's colour within
   WATER_FILL_M (never a "water" soil average; the soils and water designs). The types meet in a FEATHER_M soft edge
   (a box blur in OKLab: a straight edge between two types becomes a linear ramp FEATHER_M wide, 0.5 on the line),
   because SSURGO's lines are interpretive and often 10-30 m off the photo.
2. **Crops** (decision 15) from farm's `crop_cover` (10 m: group, July state, confidence) inside farm's fields (their
   exact edges, and their row bearing for the rows' direction), and its edge band where the CDL agrees. The July state
   sets the look: green fields a dense crop in natural July colours (no darker than the ground band's lawn), growing
   ones green rows over the soil, bare or harvested ones the soil with tillage rows, small grains straw. Cropland
   clusters outside every field (confidence 3) wait for G1b, which confirms them in the photo. Not on mapped surfaces.
3. **The land-cover classes** in the ten boxes (the ground's product `ground_classes`, 0.5 m): each cell's floor
   class, as tokens over the soil base (short dry grass is the soil itself; pale surfaced ground the soil under 35%
   cream; dark surfaced ground the asphalt token; lawns and tall green grass the band's greens; tall dry grass straw over
   the soil; forest floor the soil darkened), and crop where the crop cover says crop and the class may be one
   (classrules.CROP_MAY_BE). The box edge feathers over BOX_FEATHER_M into the valley paint. Surfaced cells on and
   within BAND_M of a mapped surface (mask v0's roads, paving, roofs, water) are painted from the soil base, so the
   photo's pavement doesn't show beside the vector road (C8).
4. Outside the grid, the flat Valley colour.

Texture (procedural noise from the octave energies) and the photo's variation are G1b's. Windows are painted with a
HALO_M halo and cut back, so neighbouring windows meet without a seam (test_paint.py checks it).
"""

import json
import math
import os

import numpy as np
from osgeo import gdal
from scipy import ndimage as ndi

from basemap.ground import classrules as CR
from basemap.ground import colour as K
from basemap.ground import grid, mask as MASK
from basemap.ground import rasterize as R

gdal.UseExceptions()

PAINTER_VERSION = "g1a-3"
FEATHER_M = 20.0          # soil types' soft edges
WATER_FILL_M = 50.0       # SSURGO Water units take the nearest soil's colour within this
HALO_M = 64.0             # every window is painted this much bigger and cut back (>= WATER_FILL_M + FEATHER_M / 2)
BOX_FEATHER_M = 75.0      # the class boxes' edges feather into the valley paint over this (plan: 50-100 m)
CROP_EDGE_M = 12.0        # a field's edge softens over this (CSB's edges step at 30 m, 5-15 m off the photo)
STATE_BLUR_M = 12.0       # the July states blend over this inside the crop (the crop cover's cells are 10 m)
ROW_PERIOD_M = 8.0        # crop rows (a texture, not the real 0.76 m rows: visible from z15 at 1.73 m a pixel)
BAND_M = 3.0              # the band around vector surfaces painted from the soil base (C8)

# Natural July colours, never the map's category colours (farm's design), and no darker than the band's lawn (§3.4).
CROP_GREEN = {1: "#6f8550", 2: "#6c8763", 3: "#7f8c55", 4: "#6f8654", 5: "#73844f"}   # corn, hay, grain, roots, spec.
STRAW = "#c7b07a"         # small grains in July: mostly ripe or cut (84% under NDVI 0.3)
TALL_GREEN = "#6e8650"
TALL_DRY_STRAW = "#bea56e"
FOREST_SHADE = "#5f5542"
GROWING_GREEN = 0.45      # a growing field: the share of green over the soil
ROW_L = 0.010             # rows: OKLab L +- this across a row
STATE_REACH_M = 30.0      # a field's cells beyond the crop cover's take the nearest July state within this
GRAIN = 3
FALLOW = 6

# Flat colours by texture (OKLab L), where a type has no measured colour: labelled in the report and the tiles entry.
FLAT_L = (("sand", 0.80), ("loamy-sand", 0.80), ("sandy-loam", 0.78), ("loam", 0.76), ("silt", 0.76),
          ("clay-loam", 0.72), ("clay", 0.68), ("muck", 0.56), ("peat", 0.56))
FLAT_AB = (0.004, 0.034)
FLAT_ROCK = (0.70, 0.002, 0.016)
FLAT_DEFAULT_L = 0.75


class PaintError(ValueError):
    pass


def _lab(h):
    return K.rgb_to_oklab(np.array(K.hex_rgb(h), float)).astype(np.float32)


def flat_lab(type_id, misc):
    """A flat colour for a ground type without a measured one: by its texture (the text id's part after the colon),
    rock looks grey."""
    if misc in ("rock", "rubble", "badland"):
        return np.array(FLAT_ROCK, np.float32)
    tex = (type_id or "").partition(":")[2]
    hits = [(len(key), l) for key, l in FLAT_L if key in tex]   # the longest match: "silty-clay-loam" is clay-loam
    L = max(hits)[1] if hits else FLAT_DEFAULT_L
    return np.array((L, *FLAT_AB), np.float32)


class Palette:
    """Per ground type (soils' gid): its OKLab colour, how it was got, and whether it yields to the water layer."""
    MEASURED, BORROWED, FLAT, FILL = 1, 2, 3, 4

    def __init__(self, types, palette=None):
        n = max([0] + [int(t["gid"]) for t in types]) + 1
        self.lab = np.zeros((n, 3), np.float32)
        self.how = np.zeros(n, np.uint8)
        self.counts = {"measured": 0, "borrowed": 0, "flat": 0, "water": 0}
        self.flat = []                   # the types painted a flat colour: [{"gid", "id", "series"}]
        pal = {int(t["gid"]): t for t in (palette or {}).get("types", [])}
        measured = [np.asarray(t["lab_med"], np.float32) for t in pal.values()
                    if t.get("status") == "measured" and t.get("lab_med") and not t.get("misc")]
        self.valley = (np.median(np.stack(measured), axis=0).astype(np.float32) if measured
                       else np.array((FLAT_DEFAULT_L, *FLAT_AB), np.float32))
        for t in types:
            gid = int(t["gid"])
            p = pal.get(gid, {})
            misc = t.get("misc") if "misc" in t else p.get("misc")
            if misc == "water":
                self.lab[gid], self.how[gid] = self.valley, self.FILL
                self.counts["water"] += 1
            elif p.get("lab_med") and p.get("status") in ("measured", "series", "texture", "albedo"):
                self.lab[gid] = np.asarray(p["lab_med"], np.float32)
                self.how[gid] = self.MEASURED if p["status"] == "measured" else self.BORROWED
                self.counts["measured" if p["status"] == "measured" else "borrowed"] += 1
            else:
                self.lab[gid], self.how[gid] = flat_lab(t.get("id") or p.get("id"), misc), self.FLAT
                self.counts["flat"] += 1
                self.flat.append({"gid": gid, "id": t.get("id") or p.get("id"),
                                  "series": t.get("series") or p.get("series") or t.get("id") or p.get("id")})
        self.lab[0], self.how[0] = self.valley, self.FLAT

    @classmethod
    def from_files(cls, ground_types_path, palette_path=None):
        with open(ground_types_path, encoding="utf-8") as f:
            types = json.load(f)["types"]
        palette = None
        if palette_path:
            with open(palette_path, encoding="utf-8") as f:
                palette = json.load(f)
        return cls(types, palette)

    def flat_types(self):
        return int(self.counts["flat"])


def _odd(n):
    n = max(1, int(round(n)))
    return n if n % 2 else n + 1


def box_blur(lab, metres, res):
    """Each channel box-blurred over `metres` (a step edge becomes a linear ramp that wide)."""
    k = _odd(metres / res)
    if k <= 1:
        return lab
    out = np.empty_like(lab)
    for c in range(lab.shape[-1]):
        out[..., c] = ndi.uniform_filter(lab[..., c], k, mode="nearest")
    return out


def _masked_blur(v, m, metres, res):
    """v averaged over `metres` (a box) among the cells where m > 0; v itself where none are near."""
    k = _odd(metres / res)
    if k <= 1:
        return v
    num = ndi.uniform_filter(v * m, k, mode="nearest")
    den = ndi.uniform_filter(m, k, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 1e-6, num / np.maximum(den, 1e-6), v).astype(np.float32)


def centres(win):
    """(x, y) of a window's cell centres, as 1-D arrays (metres from the grid's origin, east and north)."""
    xs = (win.col + np.arange(win.width) + 0.5) * win.res
    ys = -(win.row + np.arange(win.height) + 0.5) * win.res
    return xs, ys


def rows_stripe(win, bearing):
    """0..1 stripes across crop rows running along bearing (degrees clockwise from grid north); NaN bearing: 0.5. On a
    level too coarse to draw them (under three cells a row), their average, 0.5, so they never alias."""
    if win.res * 3 > ROW_PERIOD_M:
        return np.full(win.shape, 0.5, np.float32)
    xs, ys = centres(win)
    th = np.radians(np.nan_to_num(bearing, nan=0.0))
    across = xs[None, :] * np.cos(th) - ys[:, None] * np.sin(th)
    s = 0.5 + 0.5 * np.cos(2 * math.pi * across / ROW_PERIOD_M)
    return np.where(np.isfinite(bearing), s, 0.5).astype(np.float32)


def outside_grid(win):
    xs, ys = centres(win)
    ox = (xs < 0) | (xs > grid.COLS * grid.BASE_RES)
    oy = (ys > 0) | (ys < -grid.ROWS * grid.BASE_RES)
    return oy[:, None] | ox[None, :]


class Painter:
    """Paints windows of the grid from resolved inputs. soils: soils' `ground` layer; palette: a Palette; crop_cover:
    the GeoTIFF's path (or None); fields: farm's `fields` layer (or None); mask: mask v0's Manifest; water: water's
    `mask` layer (or None: mask v0's water, intermittent = 0); classes: {box id: GeoTIFF path}."""

    def __init__(self, soils, palette, mask, crop_cover=None, fields=None, water=None, classes=None):
        self.soils, self.palette, self.mask = soils, palette, mask
        self.crop_cover, self.fields, self.water = crop_cover, fields, water
        self.classes = dict(classes or {})
        self.green = {g: _lab(h) for g, h in CROP_GREEN.items()}
        self.straw = _lab(STRAW)
        self.flat_valley = K.token_lab("flat_valley").astype(np.float32)
        self.cls_lab = {CR.SHORT_GREEN: K.token_lab("lawn").astype(np.float32), CR.TALL_GREEN: _lab(TALL_GREEN),
                        CR.DARK: K.token_lab("asphalt").astype(np.float32)}
        self.cream = K.token_lab("cream").astype(np.float32)
        self.tall_dry = _lab(TALL_DRY_STRAW)
        self.forest = _lab(FOREST_SHADE)
        self._cc = None

    @classmethod
    def from_plan(cls, plan):
        """A Painter from inputs.resolve()'s painted plan."""
        if plan.status != "painted":
            raise PaintError(plan.reason)
        soils = plan.choice("soils/ground").layer
        folder = os.path.dirname(soils.path)
        types_path = os.path.join(folder, "ground_types.json")
        if not os.path.isfile(types_path):
            raise PaintError(f"{folder} has no ground_types.json beside ground.fgb (soils' export)")
        pal = plan.choice("soils/palette").layer
        palette = Palette.from_files(types_path, pal.path if pal else None)
        cc = plan.choice("farm/crop_cover").layer
        fields = plan.choice("farm/fields").layer
        if cc is None or fields is None:             # resolve() makes farm's export required: the plan is flat then
            raise PaintError("farm's export (crop_cover and fields) is needed; run farm-export")
        water = plan.choice("water/mask").layer
        mask_layers = plan.choice("ground_mask").layers
        mask_m = _ManifestOf(mask_layers)
        classes = {lay.name: lay.path for lay in plan.choice("ground_classes").layers}
        return cls(soils, palette, mask_m, crop_cover=cc.path if cc else None, fields=fields, water=water,
                   classes=classes)

    # --- the layers ------------------------------------------------------------------------------------------------

    def soil_base(self, P):
        """The feathered soil base on the padded window P: OKLab (rows, cols, 3) float32."""
        gt = R.rasterize(P, self.soils, attribute="ground_type", dtype="uint16")
        gt = np.minimum(gt, len(self.palette.lab) - 1)
        lab = self.palette.lab[gt]
        fill = self.palette.how[gt] == Palette.FILL
        if fill.any():
            src = ~fill
            if src.any():
                d, (iy, ix) = ndi.distance_transform_edt(fill, sampling=P.res, return_indices=True)
                near = fill & (d <= WATER_FILL_M)
                lab[near] = lab[iy[near], ix[near]]
        return box_blur(lab, FEATHER_M, P.res), gt

    def surfaces(self, P):
        """Mask v0's exact surfaces (roads, paving, roofs) and the water (water's mask, else mask v0's standing and
        running water) on P: bool."""
        s = MASK.exact(P, self.mask, "roads") | MASK.exact(P, self.mask, "paving") | MASK.exact(P, self.mask, "roofs")
        if self.water is not None:
            s |= R.rasterize(P, self.water).astype(bool)
        else:
            s |= MASK.exact(P, self.mask, "water", where="intermittent = 0")
        return s

    def crop_cells(self, P):
        """(group, state, confidence) of each cell of P from the 10 m crop cover (nearest), uint8 each; zeros without
        one."""
        z = np.zeros(P.shape, np.uint8)
        if not self.crop_cover:
            return z, z.copy(), z.copy()
        if self._cc is None:
            self._cc = gdal.Open(self.crop_cover)
        ds = self._cc
        xs, ys = centres(P)
        ci = np.floor(xs / grid.BASE_RES).astype(np.int64)
        ri = np.floor(-ys / grid.BASE_RES).astype(np.int64)
        c0, c1 = max(int(ci.min()), 0), min(int(ci.max()) + 1, ds.RasterXSize)
        r0, r1 = max(int(ri.min()), 0), min(int(ri.max()) + 1, ds.RasterYSize)
        if c1 <= c0 or r1 <= r0:
            return z, z.copy(), z.copy()
        arr = ds.ReadAsArray(c0, r0, c1 - c0, r1 - r0).reshape(3, r1 - r0, c1 - c0)
        okc = (ci >= c0) & (ci < c1)
        okr = (ri >= r0) & (ri < r1)
        lc = np.clip(ci - c0, 0, c1 - c0 - 1)
        lr = np.clip(ri - r0, 0, r1 - r0 - 1)
        out = []
        for b in range(3):
            v = arr[b][lr[:, None], lc[None, :]]
            v[~(okr[:, None] & okc[None, :])] = 0
            out.append(v.astype(np.uint8))
        return tuple(out)

    def crops(self, P, base, surf):
        """(crop colour OKLab, weight 0..1) on P: crop fields to their own edges (the field's 2025 group) and the crop
        cover's edge band where the CDL agrees; the July state from the crop cover's 10 m cells (where a field reaches
        past them, the nearest within STATE_REACH_M); rows along the field's bearing."""
        group, state, conf = self.crop_cells(P)
        if self.fields is not None:
            in_field = R.rasterize(P, self.fields).astype(bool)
            fgroup = R.rasterize(P, self.fields, attribute="crop_group", dtype="uint8")
            bearing = R.rasterize(P, self.fields, attribute="bearing", dtype="float32", fill=-1.0)
            bearing = np.where(in_field & (bearing >= 0), bearing, np.nan).astype(np.float32)
            field_crop = in_field & (fgroup > 0)                    # the field's own edge, not the 10 m cells'
            crop = field_crop | ((conf == 2) & (group > 0))         # and the edge band where the CDL agrees
            grp = np.where(field_crop, fgroup, group)
        else:
            bearing = np.full(P.shape, np.nan, np.float32)
            crop = (conf >= 1) & (conf <= 2) & (group > 0)
            grp = group
        crop &= ~surf
        st = state.copy()
        need = crop & (st == 0)                                     # a field's edge the 10 m cells don't reach
        if need.any() and (st > 0).any():
            d, (iy, ix) = ndi.distance_transform_edt(st == 0, sampling=P.res, return_indices=True)
            near = need & (d <= STATE_REACH_M)
            st[near] = st[iy[near], ix[near]]
        st = np.where(crop & (st == 0), 2, st)                      # still none: growing
        # The look per July state, as fractions blended over STATE_BLUR_M inside the crop (the crop cover's 10 m
        # cells, and CSB's stepped edges, would otherwise show as blocks): how green, and how much straw.
        green_frac = np.where(st == 1, 1.0, np.where(st == 2, GROWING_GREEN, 0.0)).astype(np.float32)
        green_frac[grp == FALLOW] = 0.0
        straw_frac = ((st == 3) & (grp == GRAIN)).astype(np.float32)
        green = np.zeros(base.shape, np.float32)
        for g, lab in self.green.items():
            green[grp == g] = lab
        has_green = np.isin(grp, list(self.green)) & crop
        m = crop.astype(np.float32)
        gf = _masked_blur(green_frac, m, STATE_BLUR_M, P.res)
        sf = _masked_blur(straw_frac, m, STATE_BLUR_M, P.res)
        gcol = np.stack([_masked_blur(green[..., c], has_green.astype(np.float32), STATE_BLUR_M, P.res)
                         for c in range(3)], axis=-1)
        under = base + sf[..., None] * (self.straw - base)
        paint = under + gf[..., None] * (gcol - under)
        stripe = rows_stripe(P, bearing)
        paint[..., 0] += np.where(crop, ROW_L * (stripe - 0.5) * 2, 0.0)
        w = box_blur(crop.astype(np.float32)[..., None], CROP_EDGE_M, P.res)[..., 0]
        w = np.where(surf, 0.0, w)
        return paint, w

    def boxes_over(self, v, P, base, crop_paint, crop_w):
        """v (OKLab on P) with the boxes' classes laid over it, each painted at 0.5 m and averaged onto P's cells, its
        edge feathered; a later box over an earlier one where both have classes (downtown over the North End)."""
        for box in grid.boxes():
            path = self.classes.get(box.id)
            if not path:
                continue
            w, s, e, n = box.utm
            pw, ps, pe, pn = P.bounds
            if e <= pw or w >= pe or n <= ps or s >= pn:
                continue
            S = _inside(grid.window((max(w, pw), max(s, ps), min(e, pe), min(n, pn)), P.res, snap="out"), P)
            if S is None:
                continue
            c, wb = self._box_at(box, path, S, P, base, crop_paint, crop_w)
            sl = S.inner(P)
            v[sl] = v[sl] + wb[..., None] * (c - v[sl])
        return v

    def _box_at(self, box, path, S, P, base, crop_paint, crop_w):
        """One box's classes on S (a sub-window of P on P's level): painted at 0.5 m, averaged to S's cells."""
        k = int(round(S.res / grid.LEVELS["classes"]))
        F = S.at(grid.LEVELS["classes"])                            # exact: S's edges are on the finer grid
        bw = box.window()
        ds = gdal.Open(path)
        cls = np.zeros(F.shape, np.uint8)
        flo = np.zeros(F.shape, np.uint8)
        c0, r0 = F.col - bw.col, F.row - bw.row
        rc0, rr0 = max(c0, 0), max(r0, 0)
        rc1, rr1 = min(c0 + F.width, bw.width), min(r0 + F.height, bw.height)
        if rc1 > rc0 and rr1 > rr0:
            a = ds.ReadAsArray(rc0, rr0, rc1 - rc0, rr1 - rr0).reshape(2, rr1 - rr0, rc1 - rc0)
            cls[rr0 - r0:rr1 - r0, rc0 - c0:rc1 - c0] = a[0]
            flo[rr0 - r0:rr1 - r0, rc0 - c0:rc1 - c0] = a[1]
        sl = S.inner(P)
        up = (lambda a: np.repeat(np.repeat(a, k, 0), k, 1)) if k > 1 else (lambda a: a)
        b = up(base[sl])
        cp = up(crop_paint[sl])
        cw = up(crop_w[sl])
        surf = self.surfaces(F)
        band = R.grow(surf, BAND_M, F.res)
        out = b.copy()                                                  # short dry grass, roofs: the soil itself
        for code, lab in self.cls_lab.items():
            out[flo == code] = lab
        sel = flo == CR.PALE
        out[sel] = b[sel] + 0.35 * (self.cream - b[sel])
        sel = flo == CR.TALL_DRY
        out[sel] = b[sel] + 0.45 * (self.tall_dry - b[sel])
        sel = flo == CR.FOREST_FLOOR
        out[sel] = b[sel] + 0.5 * (self.forest - b[sel])
        sel = flo == CR.CROP                                           # the shrub rule's tall crop: green
        out[sel] = self.cls_lab[CR.TALL_GREEN]
        may = np.isin(cls, CR.CROP_MAY_BE) & (cw > 0.5)
        out[may] = cp[may]
        paved = np.isin(flo, (CR.DARK, CR.PALE)) & band                # C8: the band beside vector surfaces
        out[paved] = b[paved]
        xs, ys = centres(F)
        x = grid.ORIGIN_X + xs
        y = grid.ORIGIN_Y + ys
        w, s, e, n = box.utm
        d = np.minimum(np.minimum(x[None, :] - w, e - x[None, :]), np.minimum(y[:, None] - s, n - y[:, None]))
        wb = np.clip(d / BOX_FEATHER_M, 0, 1).astype(np.float32) * (flo != CR.NODATA)
        if k > 1:
            wsum = wb.reshape(S.height, k, S.width, k).sum(axis=(1, 3))
            csum = (out * wb[..., None]).reshape(S.height, k, S.width, k, 3).sum(axis=(1, 3))
            c = csum / np.maximum(wsum, 1e-6)[..., None]
            return c.astype(np.float32), (wsum / (k * k)).astype(np.float32)
        return out, wb

    # --- a window --------------------------------------------------------------------------------------------------

    def paint_lab(self, win):
        """The ground on win: OKLab (rows, cols, 3) float32."""
        P = win.pad_m(HALO_M)
        base, _gt = self.soil_base(P)
        surf = self.surfaces(P)
        crop_paint, crop_w = self.crops(P, base, surf)
        v = base + crop_w[..., None] * (crop_paint - base)
        if self.classes:
            v = self.boxes_over(v, P, base, crop_paint, crop_w)
        v = v[win.inner(P)]
        v[outside_grid(win)] = self.flat_valley
        return v

    def paint(self, win):
        """The ground on win: sRGB (rows, cols, 3) uint8."""
        return K.oklab_to_rgb8(self.paint_lab(win))


def _inside(S, P):
    """S cut to P (both on one level), or None."""
    c0, r0 = max(S.col, P.col), max(S.row, P.row)
    c1, r1 = min(S.col + S.width, P.col + P.width), min(S.row + S.height, P.row + P.height)
    if c1 <= c0 or r1 <= r0:
        return None
    return grid.Window(S.res, c0, r0, c1 - c0, r1 - r0)


class _ManifestOf:
    """The few things mask.exact needs from mask v0's Manifest, from its layers (plan.choice(...).layers)."""

    def __init__(self, layers):
        self._layers = {lay.name: lay for lay in layers}

    def layer(self, name):
        return self._layers[name]


def versions(**given):
    """The raw-input versions the painter names for inputs.resolve(..., versions=), e.g. {"naip-2m": <sha256>}. G1a's
    painter reads exports only, so none; G1b's photo variation adds naip-2m. Kept as the one place that names them."""
    return {k: v for k, v in given.items() if v}


def report(painter, plan):
    """What the painter used, for the run's record (tilewrite.py's run.json) and the files' metadata: per-type colour
    sources (the flat types by name), fallbacks."""
    return {"painter": PAINTER_VERSION, "types": painter.palette.counts,
            "flat_types": painter.palette.flat,
            "flat_types_note": "types without a measured or borrowed colour are a flat colour by texture, labelled",
            "crop_cover": bool(painter.crop_cover), "fields": painter.fields is not None,
            "water": "water/mask" if painter.water is not None else "mask v0's water (intermittent = 0)",
            "boxes": sorted(painter.classes), "fallbacks": [f"{c.use.ref}: {c.use.fallback}" for c in plan.choices
                                                           if c.fallback],
            "rules": {"feather_m": FEATHER_M, "water_fill_m": WATER_FILL_M, "box_feather_m": BOX_FEATHER_M,
                      "band_m": BAND_M, "crop_edge_m": CROP_EDGE_M, "row_period_m": ROW_PERIOD_M}}


def notes(rep):
    """What the painter fell back on, from report(), for the tiles entry's fallbacks ("<input>: <what>")."""
    flat = rep.get("flat_types") or []
    if not flat:
        return []
    names = sorted({str(t["series"]) for t in flat})
    return [f"soils/palette: {len(flat)} ground type{'s' if len(flat) != 1 else ''} without a measured or borrowed "
            f"colour, painted a flat colour by texture ({', '.join(names)})"]


__all__ = ["Painter", "Palette", "PaintError", "versions", "report", "notes", "PAINTER_VERSION"]
