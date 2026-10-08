"""Build one area's trees (docs/19 §19.3, §19.5). Runs in the worker image (NumPy, SciPy, rasterio, pyproj):

    docker run --rm --memory 5g --memory-swap 5g --user $(id -u):$(id -g) -v "$PWD":/repo -v /srv/tvt:/srv/tvt \\
      -w /repo tvt-worker python plugins/trees/build/build.py --area c --dsm .../dsm.tif --dtm .../dtm.tif \\
      --mask .../zero_mask_c.npy --anchors .../anchors_c.csv --out $TVT_ARCHIVE/trees/<build-id>

Then `python3 -m ingest trees-load --build <dir>` loads it.

1. Catalogued trees first (when --anchors is given: a CSV of catalogue trunk points). A catalogue tree planted before the
   lidar flight whose trunk point has a crown 3 m or taller within 1.5 m becomes a catalogued tree: its crown is centred
   within 2.5 m of the trunk point where it best explains the lidar, sized from the crown model for its height and type
   (the genus says conifer or broadleaf). It is fixed: the placer builds around it. Otherwise it is an estimated tree,
   sized from Boise's measured trees of its genus (Urban Tree Database) by trunk diameter.
2. The placer fills the rest (place.py), then repairs.
3. Writes trees.geojson (WGS84 points with the tree's fields), log.jsonl (one event per line) and build.json.

The area's inputs for the pilot are the land-cover spike's lidar products (0.5 m DSM and DTM in UTM 11N) and its
building mask (aligned footprints, zeroed with a buffer)."""
import argparse, csv, datetime as dt, json, math, os, sys, time
import numpy as np
import rasterio
from pyproj import Transformer
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from place import Model, Placer, PX  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(os.path.dirname(HERE), "model")
CONIFER_GENERA = {"abies", "calocedrus", "cedrus", "chamaecyparis", "cryptomeria", "cupressus", "juniperus", "larix",
                  "metasequoia", "picea", "pinus", "pseudotsuga", "sequoia", "sequoiadendron", "taxodium", "taxus",
                  "thuja", "tsuga"}
TRUNK_H_CELLS, TRUNK_REACH_CELLS = 3, 5   # crown top within 1.5 m of the trunk point; centre within 2.5 m


def model_for(cm):
    """One rule everywhere (owner, Oct 8: no classification by place): every tree tries the three types, each with its
    own width-for-height curve from the lone trees, and keeps the one that explains its crown best. Broadleaf takes the
    valley broadleaf curve (which includes the small trees), conifer the mountain conifers' (pointed, narrow crowns),
    narrow the valley conifers' and columnar trees'. Conifers and narrow trees share the narrow top shape."""
    W, Sh = cm["width"], cm["shape"]
    crowded = cm["crowded_shape_a"]
    narrow_shapes = [(Sh["narrow"]["a"], Sh["narrow"]["n"]), (crowded["narrow"], Sh["narrow"]["n"])]
    shapes = {"broadleaf": [(Sh["broadleaf"]["a"], Sh["broadleaf"]["n"]), (crowded["broadleaf"], Sh["broadleaf"]["n"])],
              "conifer": narrow_shapes, "narrow": narrow_shapes}
    widths = {"broadleaf": (W["valley broadleaf + small"]["a"], W["valley broadleaf + small"]["b"]),
              "conifer": (W["mountain conifer"]["a"], W["mountain conifer"]["b"]),
              "narrow": (W["valley conifer"]["a"], W["valley conifer"]["b"])}
    return Model(widths, shapes, W["valley broadleaf + small"]["sd_log"], ["broadleaf", "conifer", "narrow"])


def utd_size(utd, genus, dbh_in, conifer):
    """Height and crown width (m) for a trunk diameter, from Boise's measured trees of the genus (else of the type)."""
    d_cm = max(2.5, (dbh_in or 2.0) * 2.54)
    f = utd["by_genus"].get((genus or "").capitalize()) or utd["by_type"]["CEL" if conifer else "BDL"]
    h = f["height"]["a"] * d_cm ** f["height"]["b"]
    w = f["crown_width"]["a"] * d_cm ** f["crown_width"]["b"]
    return round(h, 2), round(w, 2)


def read_anchors(path, to_rc, shape, lidar_ms):
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            inst = r.get("installed_ms")
            if inst and lidar_ms and float(inst) > lidar_ms:
                continue                                         # planted after the flight: not in the lidar
            row, col = to_rc(float(r["lon"]), float(r["lat"]))
            if not (0 <= row < shape[0] and 0 <= col < shape[1]):
                continue
            genus = (r.get("genus") or "").strip().lower()
            out.append({"catalogue": r["catalogue"], "catalogue_id": r["catalogue_id"], "row": row, "col": col,
                        "genus": genus, "dbh_in": float(r["dbh_in"]) if r.get("dbh_in") else None,
                        "conifer": genus in CONIFER_GENERA, "after_flight": False})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--area", required=True)
    ap.add_argument("--dsm", required=True)
    ap.add_argument("--dtm", required=True)
    ap.add_argument("--mask", help="building mask (.npy, the DSM's grid)")
    ap.add_argument("--anchors", help="catalogue trunk points (CSV: catalogue, catalogue_id, lon, lat, genus, dbh_in, installed_ms)")
    ap.add_argument("--lidar", default="USGS 3DEP QL1 lidar", help="the survey's name, for the log")
    ap.add_argument("--lidar-date", help="the flight date (YYYY-MM-DD); later catalogue plantings are 'estimated'")
    ap.add_argument("--theta", type=float, default=0.2, help="overlap limit (share of the smaller crown); 0.2 calibrated Oct 8")
    ap.add_argument("--lam", type=float, default=20.0, help="per-tree cost (metres x cells)")
    ap.add_argument("--sweeps", type=int, default=2)
    ap.add_argument("--window", help="row0,col0,rows,cols: build only this part (tests)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    t0 = time.time(); started = dt.datetime.now(dt.timezone.utc)
    cm = json.load(open(os.path.join(MODEL_DIR, "crown_model.json")))
    utd = json.load(open(os.path.join(MODEL_DIR, "utd_boise.json")))
    with rasterio.open(a.dsm) as ds:
        dsm = ds.read(1).astype(np.float32); nod = ds.nodata; tf = ds.transform; crs = ds.crs
    with rasterio.open(a.dtm) as ds:
        dtm = ds.read(1).astype(np.float32)
    bad = (dsm == nod) | (dtm == nod) | ~np.isfinite(dsm) | ~np.isfinite(dtm)
    h = np.where(bad, 0, np.clip(dsm - dtm, 0, None))
    bld = np.load(a.mask) if a.mask else np.zeros(h.shape, bool)
    r0 = c0 = 0
    if a.window:
        r0, c0, nr, nc = (int(v) for v in a.window.split(","))
        sl = (slice(r0, r0 + nr), slice(c0, c0 + nc))
        h, bld, bad, dtm = h[sl], bld[sl], bad[sl], dtm[sl]
    s = ndimage.gaussian_filter(np.where(bld, 0, h), 1.0)
    valid = ~bld & ~bad
    model = model_for(cm)
    # seeds within 1 m of a building must be 6 m or taller: shorter ones there are mostly roof slivers
    near_bld = ndimage.binary_dilation(bld, iterations=2) & ~bld
    pl = Placer(s, valid, model, theta=a.theta, lam=a.lam, avoid=near_bld)
    to_xy = Transformer.from_crs(crs, 4326, always_xy=True)
    from_ll = Transformer.from_crs(4326, crs, always_xy=True)
    inv = ~tf
    def to_rc(lon, lat):
        x, y = from_ll.transform(lon, lat); col, row = inv * (x, y)
        return row - r0, col - c0
    def to_ll(row, col):
        x, y = tf * (col + c0 + 0.5, row + r0 + 0.5); lon, lat = to_xy.transform(x, y)
        return x, y, lon, lat
    lidar_ms = None
    if a.lidar_date:
        lidar_ms = dt.datetime.fromisoformat(a.lidar_date).replace(tzinfo=dt.timezone.utc).timestamp() * 1000 + 86400000
    flight_at = (a.lidar_date + "T12:00:00Z") if a.lidar_date else started.isoformat()
    built_at = started.isoformat()
    out_trees, log = [], []
    # 1. catalogued trees first, the tallest crowns first
    anchors = read_anchors(a.anchors, to_rc, h.shape, lidar_ms) if a.anchors else []
    for an in anchors:
        y, x = int(round(an["row"])), int(round(an["col"]))
        r = TRUNK_H_CELLS
        win = s[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
        an["H"] = float(win.max()) if win.size else 0.0
    anchors.sort(key=lambda an: -an["H"])
    n_cat = n_est = 0
    for an in anchors:
        tid = f'{an["catalogue"]}-{an["catalogue_id"]}'
        y, x = int(round(an["row"])), int(round(an["col"]))
        exp_h, _ = utd_size(utd, an["genus"], an["dbh_in"], an["conifer"]) if an["dbh_in"] else (None, None)
        under = exp_h is not None and an["H"] > max(1.8 * exp_h, exp_h + 6)     # the crown above is another tree's
        an["under"] = under
        if an["H"] >= pl.tree_h and not under and valid[min(max(y, 0), h.shape[0] - 1), min(max(x, 0), h.shape[1] - 1)]:
            types = ["conifer", "narrow"] if an["conifer"] else ["broadleaf", "narrow"]
            g, t = pl.best_near(y, x, an["H"], types, TRUNK_REACH_CELLS, overlap=False)
            if t is not None:
                t["fixed"] = True; t["kind"] = "catalogued"; t["anchor"] = an; t["gain"] = g
                pl.add(t); n_cat += 1
                continue
        hh, ww = utd_size(utd, an["genus"], an["dbh_in"], an["conifer"])
        _, _, lon, lat = to_ll(an["row"], an["col"])
        gy, gx = min(max(y, 0), h.shape[0] - 1), min(max(x, 0), h.shape[1] - 1)
        out_trees.append({"id": tid, "kind": "estimated", "type": "conifer" if an["conifer"] else "broadleaf",
                          "lon": lon, "lat": lat, "ground_m": float(dtm[gy, gx]) if not bad[gy, gx] else None,
                          "height_m": hh, "crown_radius_m": round(ww / 2, 2), "crown_a": None, "crown_n": None, "lidar": None,
                          "catalogue": an["catalogue"], "catalogue_id": an["catalogue_id"],
                          "fit": {"from": "Urban Tree Database, Boise, by genus and trunk diameter", "dbh_in": an["dbh_in"],
                                  "under_taller_crown": bool(an.get("under")), "lidar_height_there_m": round(an["H"], 1)}})
        why = ("under a taller tree's crown: the lidar there is far taller than its trunk diameter predicts" if an.get("under")
               else "no crown 3 m or taller within 1.5 m of its trunk point in the lidar")
        log.append({"tree_id": tid, "at": built_at, "event": "estimated",
                    "detail": {"why": why,
                               "height_m": hh, "crown_width_m": ww, "dbh_in": an["dbh_in"]}})
        n_est += 1
    print(f"catalogue: {len(anchors)} trees in the area, {n_cat} catalogued, {n_est} estimated ({time.time() - t0:.0f} s)", flush=True)
    # 2. the placer fills the rest
    pl.run_greedy(log=lambda m: print(m, flush=True))
    pl.repair(sweeps=a.sweeps, log=lambda m: print(m, flush=True))
    # 3. write
    n_placed = 0
    for t in pl.alive():
        x_m, y_m, lon, lat = to_ll(t["y"], t["x"])
        gy, gx = int(min(max(round(t["y"]), 0), h.shape[0] - 1)), int(min(max(round(t["x"]), 0), h.shape[1] - 1))
        ground = float(dtm[gy, gx]) if not bad[gy, gx] else None
        common = {"lon": lon, "lat": lat, "ground_m": ground, "height_m": round(t["H"], 2),
                  "crown_radius_m": round(t["R"] * PX, 2), "crown_a": round(t["a"], 3), "crown_n": round(t["n"], 3), "lidar": a.lidar}
        if t.get("kind") == "catalogued":
            an = t["anchor"]; tid = f'{an["catalogue"]}-{an["catalogue_id"]}'
            off = math.hypot(t["y"] - an["row"], t["x"] - an["col"]) * PX
            typ = "conifer" if an["conifer"] else "broadleaf"
            out_trees.append({"id": tid, "kind": "catalogued", "type": typ, **common, "catalogue": an["catalogue"],
                              "catalogue_id": an["catalogue_id"], "fit": {"trunk_to_crown_m": round(off, 2), "gain": round(t["gain"], 1)}})
            log.append({"tree_id": tid, "at": flight_at, "event": "measured",
                        "detail": {"lidar": a.lidar, "height_m": round(t["H"], 2), "crown_width_m": round(2 * t["R"] * PX, 2),
                                   "trunk_to_crown_m": round(off, 2)}})
        else:
            tid = f"{a.area}-{int(round(x_m))}-{int(round(y_m))}"
            typ = t["type"]
            z = math.log(t["R"] / model.radius_cells(t["H"], t["type"])) / model.sd
            out_trees.append({"id": tid, "kind": "placed", "type": typ, **common, "catalogue": None, "catalogue_id": None,
                              "fit": {"width_vs_typical_sd": round(z, 2), "crowded": t["a"] < 0.6 if t["type"] == "broadleaf" else t["a"] < 0.8}})
            log.append({"tree_id": tid, "at": flight_at, "event": "placed",
                        "detail": {"lidar": a.lidar, "height_m": round(t["H"], 2), "crown_width_m": round(2 * t["R"] * PX, 2),
                                   "theta": a.theta}})
            n_placed += 1
    # placed ids can collide when two crowns round to the same metre: suffix them
    seen = {}
    for tr in out_trees:
        k = tr["id"]
        if k in seen:
            seen[k] += 1; tr["id"] = f"{k}-{seen[k]}"
        else:
            seen[k] = 0
    os.makedirs(a.out, exist_ok=True)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(tr["lon"], 7), round(tr["lat"], 7)]},
         "properties": {k: v for k, v in tr.items() if k not in ("lon", "lat")}} for tr in out_trees]}
    json.dump(fc, open(os.path.join(a.out, "trees.geojson"), "w"))
    with open(os.path.join(a.out, "log.jsonl"), "w") as f:
        for e in log:
            f.write(json.dumps(e) + "\n")
    canopy = (s >= 2) & valid
    err = np.abs(s - pl.E)[canopy]
    build = {"build_id": os.path.basename(os.path.normpath(a.out)), "area": a.area, "started_at": started.isoformat(),
             "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "params": {"theta": a.theta, "lam": a.lam, "sweeps": a.sweeps, "lidar": a.lidar, "lidar_date": a.lidar_date,
                        "window": a.window, "model": cm["source"][:200]},
             "counts": {"trees": len(out_trees), "catalogued": n_cat, "estimated": n_est, "placed": n_placed,
                        "surface_mae_m": round(float(err.mean()), 3) if err.size else None,
                        "surface_within_1_5m": round(float((err <= 1.5).mean()), 3) if err.size else None,
                        "seconds": round(time.time() - t0)}}
    json.dump(build, open(os.path.join(a.out, "build.json"), "w"), indent=1)
    print(json.dumps(build["counts"]), flush=True)


if __name__ == "__main__":
    main()
