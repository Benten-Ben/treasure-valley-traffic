"""photo_stats.py end to end on a synthetic county (needs GDAL, NumPy and SciPy: skipped where they're missing; on the
VM, `worker-test -C <checkout> plugins.soils.tests.test_photo_stats`, where a skip fails).

The county is a 0.6 m GeoTIFF read through TiffMosaic, as NAIP 2023's crops are (the MrSID decoder isn't in the
image). Every other input is a small synthetic copy of the real one: the soils export, mask v0, farm's export, the
July median, and the same-day normalisation's fits and flight polygons. Nothing here is real data.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

try:
    import numpy as np
    from osgeo import gdal, ogr, osr
except ImportError:  # pragma: no cover
    gdal = None

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(os.path.dirname(HERE), "build")
if BUILD not in sys.path:
    sys.path.insert(0, BUILD)

from basemap.ground import manifest as M  # noqa: E402

# The synthetic county: 960 m square at 0.6 m, over box f's class window (E 549090-549590, N 4801778.5-4802278.5).
X0, Y0, SIZE = 548640.0, 4802400.0, 1600
WEST_SOIL = (200, 180, 150, 190)       # R, G, B, NIR: bright, not green
EAST_SOIL = (150, 130, 110, 140)
GREEN = (60, 120, 50, 200)
DAY = {"2025-06-18": 900, "2025-05-25": 1700}
BUILD_ID = "20261011T000000Z"
MAY_GAIN = 10           # the synthetic gains: May 25's DNs read 10 higher on June 18's scale (June 18 is the reference)
CANYON_LIFT = 20        # the two-county case: Canyon's mosaic is balanced 20 DN brighter than Ada's


def srs(code):
    s = osr.SpatialReference()
    s.ImportFromEPSG(code)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def rect(w, s, e, n):
    return f"MULTIPOLYGON((({w} {s},{e} {s},{e} {n},{w} {n},{w} {s})))"


def write_vector(path, epsg, fields, features, driver="FlatGeobuf", layer="layer"):
    types = {"int": ogr.OFTInteger, "string": ogr.OFTString, "double": ogr.OFTReal}
    ds = ogr.GetDriverByName(driver).CreateDataSource(path)
    opts = ["SPATIAL_INDEX=YES"] if driver == "FlatGeobuf" else []
    lyr = ds.CreateLayer(layer, srs(epsg), ogr.wkbMultiPolygon, options=opts)
    for name, t in fields:
        lyr.CreateField(ogr.FieldDefn(name, types[t]))
    for wkt, props in features:
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        for k, v in props.items():
            if v is not None:
                f.SetField(k, v)
        lyr.CreateFeature(f)
    ds = None


def write_raster(path, gt, arrays, epsg, dtype=None):
    a0 = arrays[0]
    dt = dtype or {np.uint8: gdal.GDT_Byte, np.int16: gdal.GDT_Int16}[a0.dtype.type]
    ds = gdal.GetDriverByName("GTiff").Create(path, a0.shape[1], a0.shape[0], len(arrays), dt, ["COMPRESS=DEFLATE"])
    ds.SetGeoTransform(gt)
    ds.SetProjection(srs(epsg).ExportToWkt())
    for i, a in enumerate(arrays):
        ds.GetRasterBand(i + 1).WriteArray(a)
    ds = None


RAW = {"osm": ("ODbL-1.0", "© OpenStreetMap contributors"),
       "overture-buildings": ("ODbL-1.0", "Overture Maps Foundation, © OpenStreetMap contributors"),
       "nhd": ("public-domain", "U.S. Geological Survey, National Hydrography Dataset"),
       "cdl": ("public-domain", "USDA NASS Cropland Data Layer")}


def make_inputs(root, two_counties=False):
    """The synthetic inputs under root; returns the photo_stats arguments that point at them. two_counties: Ada's
    mosaic and Canyon's overlap over the middle 560 m, the county line between soil A (Canyon, ID665, the west) and
    soil B (Ada, ID001, the east); Canyon's is balanced CANYON_LIFT brighter, so a blend or a double count shows."""
    archive = os.path.join(root, "archive")
    xs = np.arange(SIZE) * 0.6 + X0 + 0.3
    ys = Y0 - np.arange(SIZE) * 0.6 - 0.3
    X, Y = np.meshgrid(xs, ys)
    mid = X0 + SIZE * 0.6 / 2                                         # 549,120 m: soils A west, B east

    # The county mosaic (EPSG:26911; read with the null datum shift): R, G, B, NIR, county mask.
    rng = np.random.default_rng(5)
    bands = []
    for i in range(4):
        v = np.where(X < mid, WEST_SOIL[i], EAST_SOIL[i]).astype(np.float64)
        v = np.where((X > 548800) & (X < 548880) & (Y > 4802100) & (Y < 4802180), GREEN[i], v)
        bands.append(np.clip(v + rng.normal(0, 4, v.shape), 0, 255).astype(np.uint8))
    mask = np.where(Y < 4801500, 0, 255).astype(np.uint8)            # the county ends 60 m above the raster's foot
    county = os.path.join(root, "county.tif")
    naip = [f"ada={county}"]
    if two_counties:
        ada_mask = np.where(X >= X0 + 200, mask, 0).astype(np.uint8)
        write_raster(county, (X0, 0.6, 0, Y0, 0, -0.6), bands + [ada_mask], 26911)
        canyon = os.path.join(root, "canyon.tif")
        lifted = [np.clip(b.astype(np.int16) + CANYON_LIFT, 0, 255).astype(np.uint8) for b in bands]
        write_raster(canyon, (X0, 0.6, 0, Y0, 0, -0.6), lifted + [np.where(X < X0 + 760, mask, 0).astype(np.uint8)],
                     26911)
        naip = [f"ada={county}", f"canyon={canyon}"]
    else:
        write_raster(county, (X0, 0.6, 0, Y0, 0, -0.6), bands + [mask], 26911)

    # The soils export: three strips of soil A in the west, three of B in the east, and a water pond.
    folder = os.path.join(archive, "soils", "export", BUILD_ID)
    os.makedirs(folder)
    feats = []
    w = X0
    for i, (gid, mukey) in enumerate([(1, "A1")] * 3 + [(2, "B1")] * 3):
        e = w + 160
        feats.append((rect(w, Y0 - 960, e, Y0), {"id": i + 1, "ground_type": gid, "mukey": mukey,
                                                  "areasymbol": "ID665" if gid == 1 else "ID001", "misc": None}))
        w = e
    feats.append((rect(549400, 4801900, 549450, 4801950), {"id": 7, "ground_type": 3, "mukey": "W1",
                                                           "areasymbol": "ID001", "misc": "water"}))
    write_vector(os.path.join(folder, "ground.fgb"), 32611,
                 (("id", "int"), ("ground_type", "int"), ("mukey", "string"), ("areasymbol", "string"),
                  ("misc", "string")), feats)
    types = [
        {"gid": 1, "id": "alpha:silt-loam", "series": "Alpha", "texture": "Silt loam", "texcl": "Silt loam",
         "modifier": None, "misc": None, "landform": "terraces", "frag_cover_pct": None, "albedo_dry": 0.3,
         "n_mapunits": 1, "area_ha": 46.0},
        {"gid": 2, "id": "beta:loam", "series": "Beta", "texture": "Loam", "texcl": "Loam", "modifier": None,
         "misc": None, "landform": "fan remnants", "frag_cover_pct": 5.0, "albedo_dry": 0.2, "n_mapunits": 1,
         "area_ha": 46.0},
        {"gid": 3, "id": "water", "series": "Water", "texture": None, "texcl": None, "modifier": None,
         "misc": "water", "landform": None, "frag_cover_pct": None, "albedo_dry": None, "n_mapunits": 1,
         "area_ha": 0.25},
        {"gid": 4, "id": "alpha:loam", "series": "Alpha", "texture": "Loam", "texcl": "Loam", "modifier": None,
         "misc": None, "landform": "terraces", "frag_cover_pct": None, "albedo_dry": 0.25, "n_mapunits": 1,
         "area_ha": 3.0},
    ]
    with open(os.path.join(folder, "ground_types.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": "soils.ground_types/1", "loads": ["load-x"], "types": types}, f)
    M.write(folder, "soils",
            inputs=[{"name": "ssurgo", "licence": "public-domain", "republish": "yes",
                     "credit": "Soils: USDA NRCS, Soil Survey Geographic Database (SSURGO)",
                     "source": "soils/ssurgo", "version": "synthetic"}],
            layers=[{"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "inputs": ["ssurgo"],
                     "base": False},
                    {"name": "ground_types", "file": "ground_types.json", "format": "JSON",
                     "schema": "soils.ground_types/1", "inputs": ["ssurgo"], "base": False}])

    # Mask v0: a road strip across soil A's third strip covers the ground, and a pond in B; a roof, a lot.
    mfolder = os.path.join(archive, "ground_mask", "export", BUILD_ID)
    os.makedirs(mfolder)
    road = rect(549000, Y0 - 960, 549020, Y0)
    write_vector(os.path.join(mfolder, "roofs.fgb"), 32611, (("id", "int"),),
                 [(rect(549300, 4802300, 549310, 4802310), {"id": 1})])
    write_vector(os.path.join(mfolder, "roads.fgb"), 32611, (("id", "int"), ("kind", "string")),
                 [(road, {"id": 1, "kind": "street"})])
    write_vector(os.path.join(mfolder, "paving.fgb"), 32611, (("id", "int"),),
                 [(rect(549500, 4802300, 549510, 4802310), {"id": 1})])
    write_vector(os.path.join(mfolder, "water.fgb"), 32611, (("id", "int"),),
                 [(rect(549400, 4801900, 549450, 4801950), {"id": 1})])
    write_vector(os.path.join(mfolder, "covered.fgb"), 32611, (("id", "int"), ("what", "string"), ("buffer", "double")),
                 [(rect(548998, Y0 - 960, 549022, Y0), {"id": 1, "what": "road", "buffer": 2.0}),
                  (rect(549395, 4801895, 549455, 4801955), {"id": 2, "what": "water", "buffer": 5.0})])
    lay = lambda n, i: {"name": n, "file": f"{n}.fgb", "format": "FlatGeobuf", "inputs": i, "base": False}
    M.write(mfolder, "ground_mask",
            inputs=[{"name": k, "licence": v[0], "republish": "yes", "credit": v[1], "version": "synthetic"}
                    for k, v in RAW.items()],
            layers=[lay("roofs", ["overture-buildings"]), lay("roads", ["osm"]), lay("paving", ["osm"]),
                    lay("water", ["nhd", "osm"]), lay("covered", ["osm", "overture-buildings", "nhd", "cdl"])])

    # Farm's export: an alfalfa field (hay: dropped) in soil A's middle strip; crop_cover says hay there.
    ffolder = os.path.join(archive, "farm", "export", BUILD_ID)
    os.makedirs(ffolder)
    field = (548820, 4801700, 548940, 4801900)
    write_vector(os.path.join(ffolder, "fields.fgb"), 32611,
                 (("id", "int"), ("csbid", "string"), ("crop_group", "int"), ("cdl", "int"), ("bearing", "double"),
                  ("acres", "double")),
                 [(rect(*field), {"id": 1, "csbid": "x", "crop_group": 2, "cdl": 36, "bearing": 0.0, "acres": 6.0})])
    gw, gn = 548600.0, 4802450.0                                      # a 10 m grid window around the county
    cols, rows = 110, 110
    cx = gw + (np.arange(cols) + 0.5) * 10
    cy = gn - (np.arange(rows) + 0.5) * 10
    CX, CY = np.meshgrid(cx, cy)
    in_field = (CX > field[0]) & (CX < field[2]) & (CY > field[1]) & (CY < field[3])
    group = np.where(in_field, 2, 0).astype(np.uint8)
    write_raster(os.path.join(ffolder, "crop_cover.tif"), (gw, 10, 0, gn, 0, -10),
                 [group, np.where(in_field, 1, 0).astype(np.uint8), np.where(in_field, 1, 0).astype(np.uint8)],
                 32611)
    M.write(ffolder, "farm",
            inputs=[{"name": "csb", "licence": "public-domain", "republish": "yes",
                     "credit": "USDA NASS Crop Sequence Boundaries 2018-2025", "source": "farm/nass_csb"},
                    {"name": "cdl", "licence": "public-domain", "republish": "yes",
                     "credit": "USDA NASS Cropland Data Layer 2025", "source": "farm/nass_cdl"},
                    {"name": "sentinel-2", "licence": "Copernicus", "republish": "yes",
                     "credit": "Contains modified Copernicus Sentinel data 2025"}],
            layers=[{"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "crs": "EPSG:32611",
                     "grid": {"res": 10, "west": gw, "north": gn, "width": cols, "height": rows},
                     "bands": [{"name": n, "type": "uint8"} for n in ("group", "state", "confidence")],
                     "inputs": ["csb", "cdl", "sentinel-2"], "licence": "Copernicus", "base": False},
                    {"name": "fields", "file": "fields.fgb", "format": "FlatGeobuf", "inputs": ["csb"],
                     "base": False}])

    # The July median: 0.20 everywhere but a block green in July in soil B.
    july = np.where((CX > 549100) & (CX < 549200) & (CY > 4802000) & (CY < 4802100), 6000, 2000).astype(np.int16)
    jdir = os.path.join(root, "sources", "sentinel2", "july2025")
    os.makedirs(jdir)
    write_raster(os.path.join(jdir, "ndvi_median.tif"), (gw, 10, 0, gn, 0, -10), [july], 32611)
    ds = gdal.Open(os.path.join(jdir, "ndvi_median.tif"), gdal.GA_Update)
    ds.GetRasterBand(1).SetNoDataValue(-32768)
    ds = None

    # The same-day normalisation: June 18 (the west) reads 0.1 greener on Sentinel-2's scale; May 25 as it is.
    norm = os.path.join(root, "sources", "sentinel2", "naip_norm")
    os.makedirs(norm)
    ident = {"lut_x": [-1, 1], "lut_y": [-1, 1]}
    fits = {"naip2025": {"days": {"2025-05-25": {"curve": ident}, "2025-05-30": {"curve": ident},
                                  "2025-06-18": {"curve": {"lut_x": [-1, 0.9, 1], "lut_y": [-0.9, 1, 1]}},
                                  "2025-07-24": {"curve": ident}}},
            "naip2023_boxes_h_i_j": {"pooled_curve": ident}}
    with open(os.path.join(norm, "fits.json"), "w", encoding="utf-8") as f:
        json.dump(fits, f)
    flights = [(rect(X0 - 100, Y0 - 1100, mid, Y0 + 100), {"src_fid": DAY["2025-06-18"], "idate": "2025-06-18",
                                                            "sdate": "06/18/2025 10:15", "edate": "06/18/2025 10:15",
                                                            "camera": "synthetic"}),
               (rect(mid, Y0 - 1100, X0 + 1100, Y0 + 100), {"src_fid": DAY["2025-05-25"], "idate": "2025-05-25",
                                                             "sdate": "05/25/2025 11:30", "edate": "05/25/2025 11:30",
                                                             "camera": "synthetic"})]
    write_vector(os.path.join(norm, "flights_mapbox.gpkg"), 26911,
                 (("src_fid", "int"), ("idate", "string"), ("sdate", "string"), ("edate", "string"),
                  ("camera", "string")), flights, driver="GPKG", layer="flights")

    # The per-flight colour gains: June 18 is the reference; May 25 reads MAY_GAIN higher on its scale.
    gdir = os.path.join(root, "sources", "sentinel2", "naip_colour")
    os.makedirs(gdir)
    ident = list(range(256))
    lift = [min(v + MAY_GAIN, 255) for v in range(256)]
    gains = {"format": "tvt-naip-colour-gains/1", "reference_day": "2025-06-18", "made": "2026-10-11T00:00:00Z",
             "method": "synthetic",
             "days": {d: {"lut": {b: (lift if d == "2025-05-25" else ident) for b in ("red", "green", "blue")}}
                      for d in ("2025-05-25", "2025-05-30", "2025-06-18", "2025-07-24")}}
    with open(os.path.join(gdir, "gains.json"), "w", encoding="utf-8") as f:
        json.dump(gains, f)
    out = ["--soils", folder, "--mask", mfolder, "--farm", ffolder, "--july", os.path.join(jdir, "ndvi_median.tif"),
           "--norm", norm, "--gains", os.path.join(gdir, "gains.json")]
    for n in naip:
        out += ["--naip", n]
    return out


@unittest.skipIf(gdal is None, "GDAL not installed")
class PhotoStatsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import photo_stats
        cls.S = photo_stats
        cls.tmp = tempfile.mkdtemp()
        cls.args = make_inputs(cls.tmp)
        cls.out = os.path.join(cls.tmp, "archive", "soils", "photo", "photo-20261011T000000Z")
        cls.cog = os.path.join(cls.tmp, "cold", "naip2025-2m")
        cls.log = io.StringIO()
        with contextlib.redirect_stdout(cls.log):
            cls.rc = photo_stats.main(["run", "--out", cls.out, "--cog", cls.cog, "--workers", "1", "--no-hashes"]
                                      + cls.args)
            cls.rc_cal = photo_stats.main(["calibrate", "--out", cls.out] + cls.args + cls.cal_args())
            cls.rc_fin = photo_stats.main(["finish", "--out", cls.out])
        with open(os.path.join(cls.out, "stats.json"), encoding="utf-8") as f:
            cls.stats = json.load(f)
        with open(os.path.join(cls.out, "report.json"), encoding="utf-8") as f:
            cls.report = json.load(f)

    @classmethod
    def cal_args(cls, fresh=True):
        lc = os.path.join(cls.tmp, "landcover")
        if not fresh:
            return ["--classes", os.path.join(lc, "classes"), "--windows", os.path.join(lc, "search"),
                    "--shifts", os.path.join(lc, "shifts.json"), "--naip2023", os.path.join(lc, "none")]
        os.makedirs(os.path.join(lc, "classes"))
        os.makedirs(os.path.join(lc, "search"))
        J = np.full((1000, 1000), 12, np.uint8)               # short dry grass...
        J[:, 900:] = 3                                        # ...and trees along the east edge
        np.save(os.path.join(lc, "classes", "f_J.npy"), J)
        with open(os.path.join(lc, "search", "f.json"), "w", encoding="utf-8") as f:
            json.dump({"window_rc": [955, 970]}, f)
        with open(os.path.join(lc, "shifts.json"), "w", encoding="utf-8") as f:
            json.dump({"shifts": {"f": {"dx_cells": 0, "dy_cells": 0}}}, f)
        return ["--classes", os.path.join(lc, "classes"), "--windows", os.path.join(lc, "search"),
                "--shifts", os.path.join(lc, "shifts.json"), "--naip2023", os.path.join(lc, "none")]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def rows(self, **kw):
        return [r for r in self.stats["rows"] if all(r.get(k) == v for k, v in kw.items())]

    def test_ran_and_finished(self):
        self.assertEqual((self.rc, self.rc_cal, self.rc_fin), (0, 0, 0), self.log.getvalue())
        self.assertEqual(self.stats["format"], "tvt-soils-photo/1")
        self.assertEqual(self.stats["build_id"], "photo-20261011T000000Z")
        self.assertFalse(self.stats["partial"])
        self.assertEqual(self.stats["soils_export"], BUILD_ID)
        names = [i["name"] for i in self.stats["inputs"]]
        # Every input of every export layer read, once each: soils' ground, mask v0's covered, farm's crop cover
        # and fields.
        self.assertEqual(names, ["naip", "sentinel-2", "ssurgo", "osm", "overture-buildings", "nhd", "cdl", "csb"])
        s2 = self.stats["inputs"][1]
        self.assertIn("colour gains", s2["version"])
        self.assertIn("farm export", s2["note"])                     # crop_cover's Sentinel-2, the same input
        self.assertTrue(self.stats["params"]["colour"]["normalised"])
        self.assertEqual(self.stats["params"]["colour"]["reference_day"], "2025-06-18")

    def test_each_soil_is_measured_on_its_own_flight_day(self):
        a = self.rows(level="ground_type", key="alpha:silt-loam", flight=None)[0]
        b = self.rows(level="ground_type", key="beta:loam", flight=None)[0]
        self.assertIsNone(a["fallback"])
        self.assertIsNone(b["fallback"])
        self.assertEqual((a["n_polygons"], b["n_polygons"]), (3, 3))
        import photo
        want_a = photo.colour(*(np.array([[v]], np.uint8) for v in WEST_SOIL[:3]))
        want_b = photo.colour(*(np.array([[v + MAY_GAIN]], np.uint8) for v in EAST_SOIL[:3]))   # May 25's gains
        self.assertLess(photo.delta_e(a["lab_med"], [float(c[0, 0]) for c in want_a]), 1.0)
        self.assertLess(photo.delta_e(b["lab_med"], [float(c[0, 0]) for c in want_b]), 1.0)
        self.assertEqual([r["flight"] for r in self.rows(level="ground_type", key="alpha:silt-loam")
                          if r["flight"]], ["2025-06-18"])
        self.assertEqual([r["flight"] for r in self.rows(level="ground_type", key="beta:loam") if r["flight"]],
                         ["2025-05-25"])
        self.assertTrue(all(v is not None and v > 0 for v in a["oct_l"]))
        # alpha:loam has no pixels: it borrows its series.
        al = self.rows(level="ground_type", key="alpha:loam", flight=None)[0]
        self.assertEqual((al["fallback"], al["n_px"]), ("series", 0))
        self.assertEqual(self.rows(level="mapunit", key="A1", flight=None)[0]["n_px"], a["n_px"])

    def test_the_mask_left_out_what_it_should(self):
        px = self.report["pixels"]["not_sampled"]
        for reason in ("edge", "covered", "green", "crop"):
            self.assertGreater(px[reason], 0, reason)
        # The July-green block (100 x 100 m in soil B) and the photo's green square (80 x 80 m in A).
        self.assertGreater(px["green"], (100 * 100 + 80 * 80) / 0.36 * 0.6)    # less their 10 m edges
        self.assertEqual(px["no_flight"], 0)
        self.assertGreater(self.report["pixels"]["sampled_share_of_valid"], 0.3)
        self.assertEqual(self.report["windows"], {"planned": 4, "done": 4, "with_2m_parts": 2})

    def test_the_2m_cog(self):
        path = os.path.join(self.cog, "naip2025_2m.tif")
        with open(os.path.join(self.cog, "naip2025_2m.json"), encoding="utf-8") as f:
            side = json.load(f)
        self.assertEqual(side["format"], "tvt-naip-2m/1")
        self.assertEqual([b["name"] for b in side["bands"]], ["red", "green", "blue", "ndvi"])
        ds = gdal.Open(path)
        self.assertEqual(ds.RasterCount, 4)
        gt = ds.GetGeoTransform()
        from basemap.ground import grid as G
        self.assertTrue(G.aligned(gt, 2.0))
        self.assertEqual((gt[0], gt[3]), (side["grid"]["west"], side["grid"]["north"]))
        self.assertIn("LAYOUT=COG", gdal.Info(ds))

        def at(x, y):
            c, r = int((x - gt[0]) / 2), int((gt[3] - y) / 2)
            vals = [int(ds.GetRasterBand(i + 1).ReadAsArray(c, r, 1, 1)[0, 0]) for i in range(4)]
            m = int(ds.GetRasterBand(1).GetMaskBand().ReadAsArray(c, r, 1, 1)[0, 0])
            return vals, m

        west, m = at(548700, 4802300)
        self.assertEqual(m, 255)
        for got, want in zip(west[:3], WEST_SOIL[:3]):
            self.assertLessEqual(abs(got - want), 2)
        import photo
        raw = (WEST_SOIL[3] - WEST_SOIL[0]) / (WEST_SOIL[3] + WEST_SOIL[0])
        self.assertAlmostEqual(float(photo.decode_ndvi(west[3])), raw + 0.1, delta=0.03)   # June 18's curve
        east, _ = at(549500, 4802300)
        for got, want in zip(east[:3], EAST_SOIL[:3]):
            self.assertLessEqual(abs(got - (want + MAY_GAIN)), 2)                     # on June 18's scale
        self.assertTrue(side["colour_normalised"])
        self.assertAlmostEqual(float(photo.decode_ndvi(east[3])),
                               (EAST_SOIL[3] - EAST_SOIL[0]) / (EAST_SOIL[3] + EAST_SOIL[0]), delta=0.03)
        _, m = at(548700, 4801490)                                            # outside the county
        self.assertEqual(m, 0)
        self.assertTrue(os.path.exists(os.path.join(self.cog, "flights.fgb")))

    def test_calibration_compares_the_box_class_window(self):
        with open(os.path.join(self.out, "calibration.json"), encoding="utf-8") as f:
            cal = json.load(f)
        self.assertEqual(cal["boxes"]["a"], {"skipped": "no classes", "lidar": "2019-20 QL2"})   # box a keeps its 2019-20 lidar (#283)
        f_box = cal["boxes"]["f"]
        self.assertGreater(f_box["photo_v1"], 0)
        self.assertGreater(f_box["class_mask"], f_box["photo_v1"] * 0.5)
        des = [p["de"] for p in cal["pairs"] if "de" in p]
        self.assertTrue(des)
        self.assertEqual(cal["summary"]["verdict"], "pass")
        self.assertEqual(self.report["calibration"]["verdict"], "pass")
        self.assertEqual(cal["inputs"]["build"], "photo-20261011T000000Z")
        self.assertEqual(cal["inputs"]["soils"], BUILD_ID)

    def test_calibrate_keeps_to_the_runs_inputs(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.S.main(["calibrate", "--out", self.out, "--dark-l", "0.6"] + self.args
                                         + self.cal_args(fresh=False)), 1)
        self.assertIn("folder of its own", err.getvalue())
        # A calibration that isn't the run's is left out of finish's verdict.
        with open(os.path.join(self.out, "run.json"), encoding="utf-8") as f:
            run = json.load(f)
        with open(os.path.join(self.out, "calibration.json"), encoding="utf-8") as f:
            cal = json.load(f)
        self.assertIsNone(self.S.calibration_mismatch(cal, run))
        other = dict(cal, inputs=dict(cal["inputs"], ground_mask="20991231T000000Z"))
        self.assertIn("ground_mask", self.S.calibration_mismatch(other, run))
        other = dict(cal, summary=dict(cal["summary"], rules=dict(cal["summary"]["rules"], dark_l=0.7)))
        self.assertIn("dark_l", self.S.calibration_mismatch(other, run))

    def test_inputs_keep_the_strictest(self):
        import copy
        arg = lambda k: self.args[self.args.index(k) + 1]
        soils_m, mask_m, farm_m = (M.read(arg(k), hashes=False) for k in ("--soils", "--mask", "--farm"))
        cfg = {"july": arg("--july"), "fits": os.path.join(arg("--norm"), "fits.json"), "gains": None,
               "flights": os.path.join(arg("--norm"), "flights_mapbox.gpkg")}
        farm = copy.deepcopy(farm_m)
        for e in farm.data["inputs"]:
            if e["name"] == "cdl":
                e["republish"] = "internal"                     # stricter than mask v0's cdl
        ins, _ = self.S.inputs_of(cfg, soils_m, mask_m, farm, [], hashes=False)
        cdl = [i for i in ins if i["name"] == "cdl"]
        self.assertEqual(len(cdl), 1)
        self.assertEqual(cdl[0]["republish"], "internal")
        self.assertIn("ground_mask export", cdl[0]["note"])
        self.assertIn("farm export", cdl[0]["note"])
        for e in farm.data["inputs"]:
            if e["name"] == "cdl":
                e["licence"] = "none-stated"
        with self.assertRaisesRegex(self.S.StatsError, "one licence"):
            self.S.inputs_of(cfg, soils_m, mask_m, farm, [], hashes=False)

    def test_a_second_run_resumes_and_other_inputs_are_refused(self):
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            self.assertEqual(self.S.main(["run", "--out", self.out, "--cog", self.cog, "--workers", "1",
                                          "--no-hashes"] + self.args), 0)
        self.assertIn("0 to do", log.getvalue())
        other = list(self.args)
        other[other.index("--july") + 1] = os.path.join(self.tmp, "elsewhere.tif")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.S.main(["run", "--out", self.out, "--cog", self.cog, "--no-hashes"] + other), 1)
        self.assertIn("other inputs", err.getvalue())



@unittest.skipIf(gdal is None, "GDAL not installed")
class TwoCountiesTest(unittest.TestCase):
    """Ada's and Canyon's mosaics overlap: each place is counted once, from its own county's mosaic, and the COG
    takes each side's values, not a blend."""

    @classmethod
    def setUpClass(cls):
        import photo_stats
        cls.S = photo_stats
        cls.tmp = tempfile.mkdtemp()
        cls.log = io.StringIO()
        cls.out = {}
        for case, two in (("one", False), ("two", True)):
            root = os.path.join(cls.tmp, case)
            os.makedirs(root)
            args = make_inputs(root, two_counties=two)
            out = os.path.join(root, "archive", "soils", "photo", "photo-20261011T000000Z")
            cog = os.path.join(root, "cold")
            with contextlib.redirect_stdout(cls.log):
                rc = photo_stats.main(["run", "--out", out, "--cog", cog, "--workers", "1", "--no-hashes",
                                       "--no-gains"] + args)
                rc_fin = photo_stats.main(["finish", "--out", out])
            cls.out[case] = (rc, rc_fin, out, cog)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def doc(self, case, name):
        with open(os.path.join(self.out[case][2], name), encoding="utf-8") as f:
            return json.load(f)

    def test_each_place_is_counted_once(self):
        self.assertEqual(self.out["two"][:2], (0, 0), self.log.getvalue())
        one, two = self.doc("one", "report.json"), self.doc("two", "report.json")
        self.assertEqual(two["pixels"]["in_cores"], one["pixels"]["in_cores"])
        self.assertEqual(two["pixels"]["sampled"], one["pixels"]["sampled"])
        rows = {(r["level"], r["key"], r["flight"]): r for r in self.doc("two", "stats.json")["rows"]}
        rows1 = {(r["level"], r["key"], r["flight"]): r for r in self.doc("one", "stats.json")["rows"]}
        for t in ("alpha:silt-loam", "beta:loam"):
            self.assertEqual(rows[("ground_type", t, None)]["n_px"], rows1[("ground_type", t, None)]["n_px"], t)
        import photo
        # Soil A is in Canyon: Canyon's (brighter) mosaic; soil B in Ada: Ada's.
        want_a = photo.colour(*(np.array([[v + CANYON_LIFT]], np.uint8) for v in WEST_SOIL[:3]))
        want_b = photo.colour(*(np.array([[v]], np.uint8) for v in EAST_SOIL[:3]))
        self.assertLess(photo.delta_e(rows[("ground_type", "alpha:silt-loam", None)]["lab_med"],
                                      [float(c[0, 0]) for c in want_a]), 1.0)
        self.assertLess(photo.delta_e(rows[("ground_type", "beta:loam", None)]["lab_med"],
                                      [float(c[0, 0]) for c in want_b]), 1.0)
        self.assertEqual(self.doc("two", "run.json")["counties"], {"ada": "ID001", "canyon": "ID665"})

    def test_the_cog_takes_each_side_not_a_blend(self):
        ds = gdal.Open(os.path.join(self.out["two"][3], "naip2025_2m.tif"))
        gt = ds.GetGeoTransform()

        def at(x, y):
            c, r = int((x - gt[0]) / 2), int((gt[3] - y) / 2)
            return [int(ds.GetRasterBand(i + 1).ReadAsArray(c, r, 1, 1)[0, 0]) for i in range(3)]
        for x, base, lift in ((X0 + 100, WEST_SOIL, CANYON_LIFT),      # Canyon only
                              (X0 + 300, WEST_SOIL, CANYON_LIFT),      # the overlap, Canyon's side
                              (X0 + 600, EAST_SOIL, 0),                # the overlap, Ada's side
                              (X0 + 900, EAST_SOIL, 0)):               # Ada only
            for got, want in zip(at(x, 4802300), base[:3]):
                self.assertLessEqual(abs(got - (want + lift)), 2, x)


if __name__ == "__main__":
    unittest.main()
