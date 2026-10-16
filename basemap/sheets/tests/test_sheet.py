"""The sheet tool (sheet.py) on a synthetic export, a synthetic NAIP crop and synthetic imagery tiles. Needs the worker
image (GDAL, NumPy, Pillow): the tests skip elsewhere, and in the worker image (worker-test) a skip is a failure.

    /srv/tvt/work/bin/worker-test -C <checkout> discover -s basemap/sheets -t .
"""

import contextlib
import datetime as dt
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import numpy as np
    from osgeo import gdal, ogr, osr
    from PIL import Image
    from basemap.sheets import sheet as S
    from basemap.ground.tests.test_rasterize import square, write_layer
except ImportError:                                  # outside the worker image
    np = None

from basemap.ground import grid as G, manifest as M
from basemap.sheets import places as P, pmtiles as PM

BUILD = "20261011T120000Z"
CSB = {"name": "csb", "licence": "public-domain", "republish": "yes", "credit": "USDA NASS Crop Sequence Boundaries"}
OSM = {"name": "osm", "licence": "ODbL-1.0", "republish": "yes", "credit": "© OpenStreetMap contributors"}
BOX = G.box("c")                                     # 563401-564868 E, 4830190-4831649 N


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = S.main(argv)
    return code, out.getvalue(), err.getvalue()


@unittest.skipIf(np is None, "needs the worker image (GDAL, NumPy, Pillow)")
class SheetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.archive = os.path.join(self.tmp, "archive")
        self.naip = os.path.join(self.tmp, "naip")
        self.tiles = os.path.join(self.tmp, "tiles")
        self.out = os.path.join(self.tmp, "out")
        for d in (self.archive, os.path.join(self.naip, "naip2025"), self.tiles, self.out):
            os.makedirs(d)
        self.write_crop()
        self.write_exports()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    # --- fixtures ----------------------------------------------------------------------------------------------

    def write_crop(self):
        """Box c's 'NAIP 2025 crop': 4 bands at 3 m in NAD83 / UTM 11N, a grey ramp west to east."""
        w, s, e, n = BOX.utm
        cols, rows = round((e - w) / 3), round((n - s) / 3)
        ds = gdal.GetDriverByName("GTiff").Create(os.path.join(self.naip, "naip2025", "c.tif"), cols, rows, 4,
                                                  gdal.GDT_Byte)
        ds.SetGeoTransform((w, 3, 0, n, 0, -3))
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(26911)
        ds.SetProjection(ref.ExportToWkt())
        ramp = np.tile(np.linspace(40, 200, cols).astype(np.uint8), (rows, 1))
        for b in range(4):
            ds.GetRasterBand(b + 1).WriteArray(ramp)
        ds = None
        with open(os.path.join(self.naip, "naip2025", "flights.json"), "w") as f:
            json.dump({"boxes": {"c": {"dates": ["2025-06-18"]}}}, f)

    def write_exports(self):
        """soils/ground: three squares in box c (one with a hole); farm/crop_cover: a 10 m GeoTIFF on the grid."""
        w, s, e, n = BOX.utm
        folder = M.export_dir(self.archive, "soils", BUILD)
        os.makedirs(folder)
        x, y = w + 200, s + 200
        holed = (f"POLYGON(({x} {y},{x + 400} {y},{x + 400} {y + 400},{x} {y + 400},{x} {y}),"
                 f"({x + 150} {y + 150},{x + 250} {y + 150},{x + 250} {y + 250},{x + 150} {y + 250},"
                 f"{x + 150} {y + 150}))")
        write_layer(os.path.join(folder, "ground.fgb"), 32611, [
            (holed, {"id": 1, "ground_type": 7, "misc": "loam"}),
            (square(w + 800, s + 200, 300), {"id": 2, "ground_type": 9, "misc": "sand"}),
            (square(w + 800, s + 800, 300), {"id": 3, "ground_type": 7, "misc": ""}),
            (square(w - 5000, s - 5000, 100), {"id": 4, "ground_type": 11, "misc": "far away"}),
        ], fields=(("id", "int"), ("ground_type", "int"), ("misc", "string")))
        M.write(folder, "soils", inputs=[dict(OSM)],
                layers=[{"name": "ground", "file": "ground.fgb", "format": "FlatGeobuf", "inputs": ["osm"],
                         "base": False}])
        folder = M.export_dir(self.archive, "farm", BUILD)
        os.makedirs(folder)
        win = G.window(BOX.utm, 10, snap="out")
        ds = gdal.GetDriverByName("GTiff").Create(os.path.join(folder, "crop_cover.tif"), win.width, win.height,
                                                  1, gdal.GDT_Byte)
        ds.SetGeoTransform(win.transform)
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(32611)
        ds.SetProjection(ref.ExportToWkt())
        arr = np.zeros((win.height, win.width), np.uint8)
        arr[:, : win.width // 2] = 1
        arr[: win.height // 2, win.width // 2:] = 2
        ds.GetRasterBand(1).WriteArray(arr)
        ds.GetRasterBand(1).SetNoDataValue(0)
        ds = None
        self.crop_cover_win = win
        M.write(folder, "farm", inputs=[dict(CSB)],
                layers=[{"name": "crop_cover", "file": "crop_cover.tif", "format": "GeoTIFF", "inputs": ["csb"],
                         "base": False, "crs": "EPSG:32611",
                         "grid": {"res": 10, "west": win.west, "north": win.north, "width": win.width,
                                  "height": win.height},
                         "bands": [{"name": "group", "type": "uint8", "nodata": 0,
                                    "values": {"1": "corn", "2": "hay"}}]}])

    def write_tiles(self, frame, valley=(10, 200, 30), detail=(200, 20, 160), west_only=True):
        """imagery.pmtiles (z14, one colour) and imagery-detail.pmtiles (z16, another, only in the frame's western
        tile column), with a manifest like the map's."""
        w, s, e, n = G.lonlat_of(frame.bounds)
        x0, y0 = PM.lonlat_to_xy(w, n)
        x1, y1 = PM.lonlat_to_xy(e, s)

        def tiles_over(z, colour, west=False):
            c0, r0 = (int(v) for v in PM.tile_of(x0, y0, z))
            c1, r1 = (int(v) for v in PM.tile_of(x1, y1, z))
            buf = io.BytesIO()
            Image.new("RGB", (512, 512), colour).save(buf, "WEBP", lossless=True)
            return {(z, c, r): buf.getvalue() for c in range(c0, (c0 if west else c1) + 1) for r in range(r0, r1 + 1)}

        PM.write(os.path.join(self.tiles, "imagery.pmtiles"), tiles_over(14, valley))
        PM.write(os.path.join(self.tiles, "imagery-detail.pmtiles"), tiles_over(16, detail, west_only))
        with open(os.path.join(self.tiles, "manifest.json"), "w") as f:
            json.dump({"imagery": {"file": "imagery.pmtiles", "tileSize": 512, "attribution": "USDA NAIP",
                                   "maxzoom": 14, "source": "synthetic valley",
                                   "detail": {"file": "imagery-detail.pmtiles", "minzoom": 15, "maxzoom": 18,
                                              "source": "synthetic detail"}}}, f)

    # --- tests -------------------------------------------------------------------------------------------------

    def test_draws_an_export_over_the_crop(self):
        code, out, err = run(["draw", "--places", "c", "--res", "2", "--archive", self.archive, "--naip", self.naip,
                              "--tiles", self.tiles, "--out", self.out, "--label", "Test run",
                              "--layer", "soils/ground,by=ground_type,label=misc",
                              "--layer", "farm/crop_cover,alpha=0.5"])
        self.assertEqual(code, 0, err)
        [folder] = os.listdir(self.out)
        self.assertTrue(folder.endswith("-test-run"))
        files = set(os.listdir(os.path.join(self.out, folder)))
        self.assertEqual(files, {"box-c.png", "contact-boxes.png", "index.json", "index.html"})
        with open(os.path.join(self.out, folder, "index.json")) as f:
            index = json.load(f)
        self.assertEqual(index["failed"], [])
        self.assertTrue(index["complete"])
        self.assertEqual(index["republish"], "yes")
        [ground, crops] = index["overlays"]
        self.assertEqual(ground["ref"], f"soils/ground@{BUILD}")
        self.assertEqual(ground["files"][0]["sha256"], M.sha256_of(os.path.join(
            M.export_dir(self.archive, "soils", BUILD), "ground.fgb")))
        self.assertEqual((ground["licence"], ground["republish"]), ("ODbL-1.0", "yes"))
        self.assertEqual(crops["credit"], ["USDA NASS Crop Sequence Boundaries"])
        [frame] = index["frames"]
        self.assertEqual(frame["photo"], "NAIP 2025 crop of box c (3.0 m, flown 2025-06-18)")
        self.assertEqual(frame["photo_sources"][0]["kind"], "naip-crop")
        self.assertGreater(frame["photo_covered"], 0.99)            # the crop is a metre short in the south
        st = frame["overlays"][f"soils/ground@{BUILD}"]
        self.assertEqual(st["features"], 3)                        # the far square isn't in the frame
        self.assertEqual(st["categories"], {"7": 2, "9": 1})
        cc = frame["overlays"][f"farm/crop_cover@{BUILD}"]
        self.assertEqual(set(cc["categories"]), {"1", "2"})
        self.assertEqual(frame["panels"], ["photo: " + frame["photo"], "with the overlays"])
        with Image.open(os.path.join(self.out, folder, "box-c.png")) as img:
            self.assertGreater(img.size[0], 2 * frame["size_px"][0])   # photo beside the overlays
        with open(os.path.join(self.out, folder, "index.html")) as f:
            self.assertIn("box-c", f.read())

    def test_vector_fill_outline_and_hole(self):
        frame = P.select(["c"], res=2)[0]
        ov = S.export_overlays("soils/ground,by=ground_type,fill=0.5", self.archive, "#E69F00")[0]
        img, labels, stats = S.draw_vector(ov, frame, 1)
        a = np.asarray(img)[..., 3]
        w, s, e, n = frame.bounds

        def at(x, y):
            return a[int((n - y) / frame.res), int((x - w) / frame.res)]
        x0, y0 = BOX.utm[0] + 200, BOX.utm[1] + 200
        self.assertEqual(at(x0 + 50, y0 + 50), 128)                 # filled at 0.5
        self.assertEqual(at(x0 + 200, y0 + 200), 0)                 # the hole
        self.assertEqual(at(x0 + 500, y0 + 50), 0)                  # between the squares
        self.assertEqual(at(x0 + 400, y0 + 100), 255)               # on an outline
        c7, c9 = ov.categories[7], ov.categories[9]
        self.assertNotEqual(c7, c9)
        rgb = np.asarray(img)[..., :3]
        self.assertEqual(tuple(rgb[int((n - (y0 + 50)) / 2), int((x0 + 50 - w) / 2)]), c7)
        self.assertEqual(stats["features"], 3)

    def test_an_rgb_raster_draws_as_it_is(self):
        frame = P.select(["c"], res=2)[0]
        path = os.path.join(self.tmp, "painted.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 100, 100, 3, gdal.GDT_Byte)
        ds.SetGeoTransform((BOX.utm[0], 5, 0, BOX.utm[3], 0, -5))
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(32611)
        ds.SetProjection(ref.ExportToWkt())
        for b, v in ((1, 116), (2, 131), (3, 87)):
            ds.GetRasterBand(b).WriteArray(np.full((100, 100), v, np.uint8))
        ds = None
        ov = S.file_overlay(f"{path},kind=rgb,licence=ODbL-1.0", "raster", "#ffffff")
        self.assertEqual(ov.alpha, 1.0)
        img, st = S.draw_raster(ov, frame)
        a = np.asarray(img)
        self.assertEqual(tuple(a[5, 5]), (116, 131, 87, 255))
        self.assertGreater(st["cells"], 0)
        self.assertEqual(S.legend_rows([ov], {ov.ref: st})[0][0], "head")
        one = os.path.join(self.tmp, "one.tif")
        ds = gdal.GetDriverByName("GTiff").Create(one, 10, 10, 1, gdal.GDT_Byte)
        ds.SetGeoTransform((BOX.utm[0], 5, 0, BOX.utm[3], 0, -5))
        ds.SetProjection(ref.ExportToWkt())
        ds = None
        with self.assertRaises(S.SheetError):
            S.draw_raster(S.file_overlay(f"{one},kind=rgb", "raster", "#ffffff"), frame)

    def test_raster_categories_ramp_and_nodata(self):
        frame = P.select(["c"], res=2)[0]
        ov = S.export_overlays("farm/crop_cover,alpha=1", self.archive, "#56B4E9")[0]
        self.assertEqual(ov.labels, {1: "corn", 2: "hay"})
        img, stats = S.draw_raster(ov, frame)
        a = np.asarray(img)
        win = self.crop_cover_win
        rows, cols = a.shape[:2]
        self.assertEqual(stats["categories"].keys(), {1, 2})
        self.assertEqual(a[rows - 5, 5, 3], 255)                       # west half: corn
        self.assertEqual(tuple(a[rows - 5, 5, :3]), ov.categories[1])
        self.assertEqual(a[rows - 5, cols - 5, 3], 0)                  # south-east quarter: nodata
        # a float raster with nodata, as a ramp
        path = os.path.join(self.tmp, "chm.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 100, 100, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((BOX.utm[0], 5, 0, BOX.utm[3], 0, -5))
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(6340)
        ds.SetProjection(ref.ExportToWkt())
        arr = np.tile(np.linspace(0, 30, 100, dtype=np.float32), (100, 1))
        arr[:10, :10] = -9999
        ds.GetRasterBand(1).WriteArray(arr)
        ds.GetRasterBand(1).SetNoDataValue(-9999)
        ds = None
        ov2 = S.file_overlay(f"{path},min=0,max=30,credit=USGS 3DEP", "raster", "#ffffff")
        img2, st2 = S.draw_raster(ov2, frame)
        self.assertEqual(st2["ramp"], [0.0, 30.0])
        a2 = np.asarray(img2)
        self.assertEqual(a2[2, 2, 3], 0)                               # nodata
        self.assertEqual(a2[100, 2, 3], round(0.6 * 255))
        self.assertLess(a2[100, 2, :3].sum(), a2[100, 240, :3].sum())  # dark violet to yellow
        self.assertEqual(ov2.credit, ["USGS 3DEP"])
        ov3 = S.file_overlay(f"{path},min=10,max=30,clip=1", "raster", "#ffffff")
        img3, st3 = S.draw_raster(ov3, frame)
        a3 = np.asarray(img3)
        self.assertEqual(a3[100, 2, 3], 0)                             # under 10: clear
        self.assertGreater(a3[100, 240, 3], 0)
        rows = S.legend_rows([ov3], {ov3.ref: st3})
        self.assertEqual([r[0] for r in rows], ["head", "ramp"])
        self.assertEqual(rows[1][2], "10 to 30, clear outside")
        # a float raster with NaN and no nodata tag (canopy height, NDVI): NaN cells are clear, the rest ramp
        path = os.path.join(self.tmp, "ndvi.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 100, 100, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((BOX.utm[0], 5, 0, BOX.utm[3], 0, -5))
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(32611)
        ds.SetProjection(ref.ExportToWkt())
        arr = np.tile(np.linspace(-1, 1, 100, dtype=np.float32), (100, 1))
        arr[:20, :20] = np.nan
        ds.GetRasterBand(1).WriteArray(arr)
        ds = None
        for style in ("", ",min=-1,max=1", ",min=0,max=1,clip=1"):
            ov4 = S.file_overlay(path + style, "raster", "#ffffff")
            img4, st4 = S.draw_raster(ov4, frame)
            a4 = np.asarray(img4)
            self.assertEqual(a4[5, 5, 3], 0, style)                         # NaN: clear
            self.assertGreater(a4[200, 200, 3], 0, style)                    # 0.6: drawn
            self.assertGreater(st4["cells"], 0, style)
        self.assertEqual(st4["ramp"], [0.0, 1.0])
        self.assertTrue(np.array_equal(S.RAMP_LUT[0], S.RAMP[0]) and np.array_equal(S.RAMP_LUT[-1], S.RAMP[-1]))

    def test_photo_from_the_imagery_tiles(self):
        frame = P.select(["at:-116.33447,43.66286,600,1"])[0]
        self.write_tiles(frame)
        photos = S.Photos(self.tiles, self.naip)
        self.assertEqual(photos.crop_for(frame), (None, 0.0))
        img, info = photos.render(frame)
        files = [(s["file"], s["zooms"]) for s in info["sources"]]
        self.assertEqual(files, [("imagery.pmtiles", [14]), ("imagery-detail.pmtiles", [16])])
        self.assertEqual(info["covered"], 1.0)
        self.assertTrue(np.abs(img[300, 2].astype(int) - (200, 20, 160)).max() <= 3, img[300, 2])   # west: detail
        self.assertTrue(np.abs(img[300, -3].astype(int) - (10, 200, 30)).max() <= 3, img[300, -3])  # east: valley
        photos.close()

    def test_the_newest_crop_that_covers_the_frame(self):
        # A 2023 crop covering all of box c, and the 2025 one a metre short: the 2025 one is drawn.
        w, s, e, n = BOX.utm
        os.makedirs(os.path.join(self.naip, "naip2023"))
        ds = gdal.GetDriverByName("GTiff").Create(os.path.join(self.naip, "naip2023", "c.tif"), 245, 244, 4,
                                                  gdal.GDT_Byte)
        ds.SetGeoTransform((w - 1, 6, 0, n + 1, 0, -6))
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(26911)
        ds.SetProjection(ref.ExportToWkt())
        ds = None
        photos = S.Photos(None, self.naip)
        crop, share = photos.crop_for(P.select(["c"])[0])
        self.assertEqual((crop["year"], crop["box"]), ("2025", "c"))
        self.assertGreater(share, 0.99)
        # a frame the 2025 crop covers only half of: the 2023 one covers more of it
        frame = P.select([f"at:{(G.lonlat_of(BOX.utm)[0] + 0.0005):.5f},43.6285,600,1"])[0]
        crop, share = photos.crop_for(frame)
        self.assertEqual(crop["year"], "2023")

    def test_no_photo_says_so(self):
        frame = P.select(["at:-116.33447,43.66286,200,1"])[0]
        img, info = S.Photos(None, None).render(frame)
        self.assertEqual(info["photo"], "no photo here (flat ground colour)")
        self.assertEqual(tuple(img[0, 0]), S.FLAT)

    def test_a_file_in_another_crs_with_where_points_and_lines(self):
        path = os.path.join(self.tmp, "things.geojson")
        lon, lat = G.lonlat_of(BOX.utm)[:2]
        lon2, lat2 = G.lonlat_of(BOX.utm)[2:]
        mid = ((lon + lon2) / 2, (lat + lat2) / 2)
        with open(path, "w") as f:
            json.dump({"type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {"kind": "gate", "n": 1},
                 "geometry": {"type": "Point", "coordinates": list(mid)}},
                {"type": "Feature", "properties": {"kind": "fence", "n": 2},
                 "geometry": {"type": "LineString", "coordinates": [[lon, lat], [lon2, lat2]]}},
                {"type": "Feature", "properties": {"kind": "fence", "n": 3},
                 "geometry": {"type": "LineString", "coordinates": [[lon, lat2], [lon2, lat]]}}]}, f)
        frame = P.select(["c"], res=2)[0]
        ov = S.file_overlay(f"{path},by=kind,where=n > 1", "vector", "#ffffff")
        img, _labels, stats = S.draw_vector(ov, frame, 2)
        self.assertEqual(stats["categories"], {"fence": 2})
        a = np.asarray(img)[..., 3]
        self.assertGreater((a > 0).sum(), 2 * 2 * 700)                  # two lines across the frame, 4 px wide
        ov2 = S.file_overlay(f"{path},by=kind", "vector", "#ffffff")
        _img, _l, stats2 = S.draw_vector(ov2, frame, 1)
        self.assertEqual(stats2["categories"], {"gate": 1, "fence": 2})

    def test_photo_only_run_over_tiles_and_list(self):
        frame = P.select(["cam-752"], res=0.5, size=200)[0]
        self.write_tiles(frame, west_only=False)
        code, out, err = run(["draw", "--places", "cam-752", "--res", "0.5", "--size", "200", "--tiles", self.tiles,
                              "--naip", self.naip, "--list"])
        self.assertEqual(code, 0, err)
        self.assertIn("cam-752", out)
        self.assertIn("imagery tiles", out)
        self.assertEqual(os.listdir(self.out), [])
        code, out, err = run(["draw", "--places", "cam-752", "--res", "0.5", "--size", "200", "--tiles", self.tiles,
                              "--naip", self.naip, "--out", self.out])
        self.assertEqual(code, 0, err)
        [folder] = os.listdir(self.out)
        with open(os.path.join(self.out, folder, "index.json")) as f:
            index = json.load(f)
        [fr] = index["frames"]
        self.assertEqual(fr["photo"], "the map's imagery tiles, z14-16")
        self.assertEqual(index["overlays"], [])
        self.assertEqual(fr["panels"], ["photo: the map's imagery tiles, z14-16"])   # the photo alone
        self.assertTrue(os.path.isfile(os.path.join(self.out, folder, "cam-752.png")))
        code, out, err = run(["draw", "--places", "cam-752", "--res", "0.5", "--size", "200", "--tiles", self.tiles,
                              "--out", self.out, "--format", "jpg", "--label", "jpeg"])
        self.assertEqual(code, 0, err)
        folder = [d for d in os.listdir(self.out) if d.endswith("-jpeg")][0]
        self.assertIn("cam-752.jpg", os.listdir(os.path.join(self.out, folder)))

    def test_refusals(self):
        args = ["draw", "--places", "c", "--res", "2", "--archive", self.archive, "--out", self.out]
        for extra, msg in ((["--layer", "soils/nope"], "has no layer 'nope'"),
                           (["--layer", "water/mask"], "water has no finished export"),
                           (["--layer", "soils/ground,colour=#fff"], "unknown style option 'colour'"),
                           (["--layer", "soils/ground,by=nope"], "no field 'nope'"),
                           (["--layer", "soils/ground,fill=2"], "out of range"),
                           (["--vector", "/no/such.fgb"], "no such file"),
                           (["--layer", "soils/ground", "--layer", "soils/ground"], "named twice"),
                           (["--panels", "map"], "--panels"),
                           (["--layer", "soils/ground,republish=yes"], "come from the export's manifest"),
                           (["--raster", os.path.join(self.naip, "naip2025", "c.tif") + ",republish=maybe"],
                            "republish='maybe'"),
                           (["--res", "0.25", "--size", "1000"], "over 3000 pixels a side")):
            code, _out, err = run(args + extra)
            self.assertIn(code, (1, 2), extra)
            if code == 1:                                             # failed in a frame: recorded, not fatal
                [folder] = [d for d in os.listdir(self.out)]
                with open(os.path.join(self.out, folder, "index.json")) as f:
                    self.assertIn(msg, json.load(f)["frames"][0]["error"])
                shutil.rmtree(os.path.join(self.out, folder))
            else:
                self.assertIn(msg, err, extra)
        self.assertEqual(os.listdir(self.out), [])

    def test_a_changed_export_is_refused_unless_told(self):
        path = os.path.join(M.export_dir(self.archive, "soils", BUILD), "ground.fgb")
        with open(path, "r+b") as f:
            f.seek(-4, 2)
            f.write(b"\0\0\0\1")
        args = ["draw", "--places", "c", "--res", "5", "--archive", self.archive, "--naip", self.naip,
                "--layer", "soils/ground", "--list"]
        code, _out, err = run(args)
        self.assertEqual(code, 2)
        self.assertIn("sha256", err)
        code, _out, err = run(args + ["--no-verify"])
        self.assertEqual(code, 0, err)

    def test_a_file_without_republish_is_unstated_and_strictest(self):
        path = os.path.join(self.tmp, "chm.tif")
        ds = gdal.GetDriverByName("GTiff").Create(path, 50, 50, 1, gdal.GDT_Float32)
        ds.SetGeoTransform((BOX.utm[0], 10, 0, BOX.utm[3], 0, -10))
        ref = osr.SpatialReference()
        ref.ImportFromEPSG(32611)
        ds.SetProjection(ref.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(np.ones((50, 50), np.float32))
        ds = None
        args = ["draw", "--places", "c", "--res", "5", "--archive", self.archive, "--naip", self.naip,
                "--out", self.out, "--layer", "soils/ground"]
        code, _out, err = run(args + ["--raster", f"{path},credit=USGS 3DEP", "--label", "unstated"])
        self.assertEqual(code, 0, err)
        index = self.index("unstated")
        self.assertEqual(index["republish"], "unstated")
        self.assertEqual([o["republish"] for o in index["overlays"]], ["yes", "unstated"])
        self.assertEqual(index["overlays"][1]["licence"], "unstated")
        ov = S.file_overlay(path, "raster", "#ffffff")
        self.assertIn("strictest republish drawn here: unstated", S.credit_line([ov], {}))
        # stated by hand: licence= gives its loosest, republish= may be stricter, not looser
        self.assertEqual(S.file_overlay(f"{path},licence=public-domain", "raster", "#ffffff").republish, "yes")
        self.assertIsNone(S.file_overlay(f"{path},licence=none-stated", "raster", "#ffffff").republish)
        ov = S.file_overlay(f"{path},licence=none-stated,republish=internal", "raster", "#ffffff")
        self.assertEqual((ov.licence, ov.republish), ("none-stated", "internal"))
        with self.assertRaisesRegex(S.SheetError, "looser than restricted allows"):
            S.file_overlay(f"{path},licence=restricted,republish=yes", "raster", "#ffffff")
        code, _out, err = run(args + ["--raster", f"{path},licence=none-stated,republish=internal", "--label", "int"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.index("int")["republish"], "internal")
        self.assertEqual(S.strictest_drawn([]), "yes")

    def index(self, label):
        [folder] = [d for d in os.listdir(self.out) if d.endswith("-" + label)]
        with open(os.path.join(self.out, folder, "index.json")) as f:
            return json.load(f)

    def test_one_bad_frame_is_recorded_and_the_run_goes_on(self):
        real = S.draw_frame

        def flaky(frame, *a, **kw):
            if frame.id == "box-c":
                raise KeyError("something unexpected")
            return real(frame, *a, **kw)
        with mock.patch.object(S, "draw_frame", flaky):
            code, _out, err = run(["draw", "--places", "c", "d", "--res", "10", "--naip", self.naip, "--out",
                                   self.out, "--label", "flaky"])
        self.assertEqual(code, 1, err)
        index = self.index("flaky")
        self.assertEqual(index["failed"], ["box-c"])
        self.assertIn("KeyError", index["frames"][0]["error"])
        self.assertEqual(index["frames"][1]["file"], "box-d.png")
        self.assertEqual(index["contact_sheets"][0]["file"], "contact-boxes.png")

    def test_disk_bound_and_floor(self):
        args = ["draw", "--places", "c", "d", "--res", "10", "--naip", self.naip, "--out", self.out]
        code, _out, err = run(args + ["--min-free-gb", "1e9"])
        self.assertEqual(code, 2)
        self.assertIn("could take up to", err)
        self.assertEqual(os.listdir(self.out), [])
        frames = P.select(["c", "d"], res=10)
        self.assertGreater(S.bound_bytes(frames, {"photo", "overlay"}, "png", ["x"]),
                           S.bound_bytes(frames, {"overlay"}, "jpg", ["x"]))
        # free space falls under the floor after the first frame: the rest aren't drawn, the index is written
        frees = iter([100.0, 100.0, 5.0])
        saved = []
        real = S.save_index

        def spy(folder, index):
            saved.append((len(index["frames"]), index["complete"]))
            real(folder, index)
        with mock.patch.object(S, "free_gb", lambda _p: next(frees, 5.0)), mock.patch.object(S, "save_index", spy):
            code, _out, err = run(args + ["--min-free-gb", "11", "--label", "low"])
        self.assertEqual(saved, [(1, False), (2, True)])        # after the frame drawn, then complete
        self.assertEqual(code, 1, err)
        index = self.index("low")
        self.assertEqual(index["failed"], ["box-d"])
        self.assertIn("not drawn: stopped drawing: 5.0 GB free, under 11 GB", index["frames"][1]["error"])

    def test_contact_sheets_carry_the_overlays_credits(self):
        seen = []
        real = S.credit_line

        def spy(overlays, info):
            text = real(overlays, info)
            seen.append(text)
            return text
        with mock.patch.object(S, "credit_line", spy):
            code, _out, err = run(["draw", "--places", "c", "--res", "10", "--archive", self.archive, "--naip",
                                   self.naip, "--out", self.out, "--layer", "farm/crop_cover", "--panels", "overlay"])
        self.assertEqual(code, 0, err)
        self.assertEqual(len(seen), 2)                                  # the frame's and the contact sheet's
        self.assertIn("USDA NASS Crop Sequence Boundaries", seen[1])
        self.assertIn("strictest republish drawn here: yes", seen[1])

    def test_style_parsing(self):
        self.assertEqual(S.parse_spec("roads/x,by=kind,where=a = 1 and b in (1, 2),fill=0"),
                         ("roads/x", {"by": "kind", "where": "a = 1 and b in (1, 2)", "fill": "0"}))
        self.assertEqual(S.nice_length(730), 500)
        self.assertEqual(S.nice_length(0.3), 0.2)
        self.assertEqual(S.run_id("Roads: review 1!", dt.datetime(2026, 10, 11, 12, 0, tzinfo=dt.timezone.utc)),
                         "20261011T120000Z-roads-review-1")


if __name__ == "__main__":
    unittest.main()
