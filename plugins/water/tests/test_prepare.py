"""plugins/water/build/prepare.py on synthetic inputs (needs GDAL and bsdtar: skipped where they're missing, e.g. the
ingest image; on the VM, `worker-test -C <checkout> plugins.water.tests.test_prepare`, where a skip fails).

nhd: a small File Geodatabase written with GDAL's OpenFileGDB driver, with NHD's layer and table names, zipped as
USGS ships it; what prepare writes must read back through the standard-library loader (nhd.read) with NHDFlow's
rows kept for the flowlines in the box and dropped for the rest. hydroshare: a shapefile packed into a 7z inside a
BagIt zip, as HydroShare's bag holds it; a bag whose payload doesn't match its manifest is refused. Everything is
invented.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

try:
    from osgeo import gdal, ogr, osr
except ImportError:  # pragma: no cover
    gdal = ogr = osr = None

from plugins.water.ingest import hydroshare, nhd

HERE = os.path.dirname(os.path.abspath(__file__))
PREPARE = os.path.join(os.path.dirname(HERE), "build", "prepare.py")
HAVE = gdal is not None and shutil.which("bsdtar") is not None


def load_prepare():
    spec = importlib.util.spec_from_file_location("water_prepare", PREPARE)   # soils has a prepare.py too
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def srs(epsg):
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def write_gdb(path):
    """A File Geodatabase with NHD's names: two flowlines in the box and one far outside it."""
    ds = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(path)
    nad83 = srs(4269)

    def layer(name, gtype, fields):
        lyr = ds.CreateLayer(name, nad83 if gtype != ogr.wkbNone else None, gtype)
        for f, t in fields:
            lyr.CreateField(ogr.FieldDefn(f, t))
        return lyr

    def add(lyr, wkt=None, **values):
        f = ogr.Feature(lyr.GetLayerDefn())
        for k, v in values.items():
            f.SetField(k, v)
        if wkt:
            f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        lyr.CreateFeature(f)

    S, I = ogr.OFTString, ogr.OFTInteger
    common = [("permanent_identifier", S), ("gnis_name", S), ("ftype", I), ("fcode", I)]
    fl = layer("NHDFlowline", ogr.wkbMultiLineString, common + [("flowdir", I), ("visibilityfilter", I),
                                                                ("reachcode", S)])
    add(fl, "MULTILINESTRING ((-116.5 43.4,-116.49 43.4))", permanent_identifier="{F-1}", gnis_name="Test Canal",
        ftype=336, fcode=33600, flowdir=1, visibilityfilter=24000)
    add(fl, "MULTILINESTRING ((-116.49 43.4,-116.49 43.41))", permanent_identifier="{F-2}", ftype=460, fcode=46003,
        flowdir=1)
    add(fl, "MULTILINESTRING ((-114.0 42.0,-114.0 42.01))", permanent_identifier="{F-9}", ftype=460, fcode=46003)
    wb = layer("NHDWaterbody", ogr.wkbMultiPolygon, common)
    add(wb, "MULTIPOLYGON (((-116.4 43.4,-116.39 43.4,-116.39 43.41,-116.4 43.4)))", permanent_identifier="{W-1}",
        ftype=390, fcode=39004)
    layer("NHDArea", ogr.wkbMultiPolygon, common)
    layer("NHDLine", ogr.wkbMultiLineString, common)
    pt = layer("NHDPoint", ogr.wkbPoint, common)
    add(pt, "POINT (-116.45 43.45)", permanent_identifier="{P-1}", ftype=458, fcode=45800)
    layer("NHDPointEventFC", ogr.wkbPoint, [("permanent_identifier", S), ("eventtype", I),
                                            ("source_featureid", S)])
    codes = layer("NHDFCode", ogr.wkbNone, [("fcode", I), ("description", S), ("canalditchtype", S),
                                             ("hydrographiccategory", S)])
    for code, desc, canal, cat in ((33600, "Canal/Ditch", " ", " "), (33601, "Canal/Ditch: Canal Ditch Type = Aqueduct",
                                    "Aqueduct", " "), (46003, "Stream/River: Hydrographic Category = Intermittent",
                                    " ", "Intermittent"), (46000, "Stream/River", " ", " "), (39004, "Lake/Pond", " ",
                                    " "), (39000, "Lake/Pond", " ", " "), (45800, "Spring/Seep", " ", " ")):
        add(codes, fcode=code, description=desc, canalditchtype=canal, hydrographiccategory=cat)
    vaa = layer("NHDFlowlineVAA", ogr.wkbNone, [("permanent_identifier", S), ("streamorder", I), ("streamlevel", I),
                                                 ("startflag", I), ("terminalflag", I), ("divergenceflag", I)])
    add(vaa, permanent_identifier="{F-2}", streamorder=2, streamlevel=4, startflag=1, terminalflag=0, divergenceflag=0)
    flow = layer("NHDFlow", ogr.wkbNone, [("from_permanent_identifier", S), ("to_permanent_identifier", S),
                                           ("direction", I), ("deltalevel", I)])
    add(flow, from_permanent_identifier="{F-1}", to_permanent_identifier="{F-2}", direction=709, deltalevel=0)
    add(flow, from_permanent_identifier="{F-8}", to_permanent_identifier="{F-9}", direction=709, deltalevel=0)
    params = layer("NHDProcessingParameters", ogr.wkbNone, [("parametername", S), ("parametervalue", S)])
    add(params, parametername="ReleaseBuild", parametervalue="test")
    ds = None


def zip_folder(folder, zpath):
    with zipfile.ZipFile(zpath, "w") as z:
        for root, _, files in os.walk(folder):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, os.path.dirname(folder)))


@unittest.skipUnless(HAVE, "GDAL and bsdtar not installed")
class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.prepare = load_prepare()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_nhd(self):
        gdb = os.path.join(self.dir, "src", "NHD_H_1705_HU4_GDB.gdb")
        os.makedirs(os.path.dirname(gdb))
        write_gdb(gdb)
        zpath = os.path.join(self.dir, "NHD_H_1705_HU4_GDB.zip")
        zip_folder(gdb, zpath)
        out = os.path.join(self.dir, "out")
        counts = self.prepare.prepare_nhd(zpath, out)
        self.assertEqual((counts["flowline"], counts["waterbody"], counts["point"], counts["flow"]), (2, 1, 1, 1))
        with open(os.path.join(out, "prepare.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["processing_parameters"], {"ReleaseBuild": "test"})
        data, _ = nhd.read(os.path.join(out, "nhd.gpkg"))                # the loader reads what prepare writes
        rows = {r[0]: dict(zip(nhd.FLOWLINE, r[:-1])) for r in data["flowline"]}
        self.assertEqual(set(rows), {"{F-1}", "{F-2}"})
        self.assertEqual((rows["{F-1}"]["class"], rows["{F-2}"]["class"]), ("canal_ditch", "stream_river"))
        self.assertEqual((rows["{F-2}"]["streamorder"], rows["{F-2}"]["hydrographiccategory"]), (2, "Intermittent"))
        self.assertEqual(data["flow"], [("{F-1}", "{F-2}", 709, 0)])
        with self.assertRaises(self.prepare.PrepareError):                # --out must be new or empty
            self.prepare.prepare_nhd(zpath, out)

    def bag(self, tamper=False):
        shp_dir = os.path.join(self.dir, "shp", "TreasureValleyIrrigationFinal")
        os.makedirs(shp_dir)
        ds = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(os.path.join(shp_dir, "Test.shp"))
        lyr = ds.CreateLayer("Test", srs(4326), ogr.wkbLineString25D)
        for name in ("Call_Numbe", "Name", "Type"):
            lyr.CreateField(ogr.FieldDefn(name, ogr.OFTString))
        for call, name, kind, wkt in (("N1", "11.5 Lateral", "Lateral", "LINESTRING Z (-116.5 43.4 0,-116.49 43.4 0)"),
                                      ("N2", "Far Drain", "Drain", "LINESTRING Z (-114.0 42.0 0,-114.0 42.01 0)")):
            f = ogr.Feature(lyr.GetLayerDefn())
            f.SetField("Call_Numbe", call)
            f.SetField("Name", name)
            f.SetField("Type", kind)
            f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            lyr.CreateFeature(f)
        ds = None
        bag = os.path.join(self.dir, "bag", self.prepare.HYDROSHARE_ID)
        contents = os.path.join(bag, "data", "contents")
        os.makedirs(contents)
        seven = os.path.join(contents, self.prepare.HYDROSHARE_7Z)
        subprocess.run(["bsdtar", "--format", "7zip", "-cf", seven, "-C", os.path.join(self.dir, "shp"),
                        "TreasureValleyIrrigationFinal"], check=True)
        with open(seven, "rb") as f:
            digest = hashlib.md5(f.read(), usedforsecurity=False).hexdigest()
        with open(os.path.join(bag, "manifest-md5.txt"), "w") as f:
            f.write(f"{'0' * 32 if tamper else digest}    data/contents/{self.prepare.HYDROSHARE_7Z}\n")
        zpath = os.path.join(self.dir, "bag.zip")
        zip_folder(bag, zpath)
        return zpath

    def test_hydroshare(self):
        out = os.path.join(self.dir, "out")
        counts = self.prepare.prepare_hydroshare(self.bag(), out)
        self.assertEqual(counts, {"records": 2, "canal": 1})              # the far drain is outside the box
        rows = hydroshare.read(os.path.join(out, "hydroshare.gpkg"))
        self.assertEqual([r[1:4] for r in rows], [("N1", "11.5 Lateral", "Lateral")])
        self.assertEqual(sorted(os.listdir(out)), ["hydroshare.gpkg", "prepare.json"])   # the unpacked files are gone

    def test_hydroshare_bag_checked(self):
        with self.assertRaisesRegex(self.prepare.PrepareError, "MD5"):
            self.prepare.prepare_hydroshare(self.bag(tamper=True), os.path.join(self.dir, "out"))


if __name__ == "__main__":
    unittest.main()
