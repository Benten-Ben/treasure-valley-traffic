"""Pool the photo statistics from map units to ground types, with the fallbacks and checks (plan P2; the soils design,
build steps 3 and 4). Worker image (NumPy); photo_stats.py's `finish` runs it.

Input: the sums photo.Accumulator kept per (map unit, flight day) over the whole decode pass, and per soil polygon.
Output: the rows of soils.photo_stats (as dicts) and a report of the checks.

- **Map units:** a row per flight day, and one pooled over the days (flight null). No fallback at this level.
- **Ground types:** the type's map units summed, weighted by pixel count (the sums are added, so the median and
  covariance are those of all the pixels). A type is **measured** when it has at least MIN_PX pixels from at
  least MIN_POLYGONS polygons (a polygon counts when POLY_PX of its pixels were sampled). Otherwise it borrows, in
  this order, and its row says from what (`fallback`):
  1. `series`: every type of the same series, any texture, summed (if that is measured);
  2. `texture`: every soil type with the same surface texture class and landform, summed (if measured);
  3. `albedo`: L from a straight fit of the measured types' L on their dry albedo (SSURGO's albedodry_r), with
     chroma, hue, spread and texture from the types of the same texture class (all measured soils when it has
     none). Needs the type's albedo, and a fit with some skill: when the fit's r is under ALBEDO_MIN_R the type
     takes its texture-class peers' colour as it is, L included, labelled `texture` (the first build's fit had r 0.28:
     L 0.75-0.80 over the whole albedo range, the mean, not an estimate).
  A type with none of these has no row: the ground paints it flat and says so. NRCS's NOTCOM ('nodata') is never
  a soil, and a miscellaneous area borrows nothing (it has no series, texture or albedo of its own): it's measured
  from fewer polygons instead, when it has MIN_PX pixels in at least one.
  NAIP 2025 here is the Ada and Canyon county mosaics, which reach a few kilometres past the county lines (into
  Owyhee, Elmore, Boise, Gem and Payette counties, and a strip of Malheur, Oregon). A type is measured from whatever
  of it those strips hold, and borrows only where it has too little: so the line between measured and flat colours
  follows the mosaics' edges, not the county lines. The 2023 tiles' colour fit beyond them is cut (plan §0).
- **Checks** (report): the same type across flight days (dE over 3 asks for per-flight colour gains; with the gains
  applied, what's left); the share of colour variance the types explain; the Spearman correlation of type L with dry
  albedo; polygons whose own median lies more than OUTLIER_D (Mahalanobis, in the type's own spread) from their type.
"""

import math

import numpy as np

import photo as P

MIN_PX = 20000         # a type is measured from at least this many 0.6 m pixels (0.72 ha)...
MIN_POLYGONS = 3       # ...in at least this many polygons
POLY_PX = 500          # a polygon counts toward that when this many of its pixels were sampled (180 m2)
OUTLIER_PX = 2000      # polygons with at least this many pixels are checked against their type...
OUTLIER_D = 3.0        # ...and listed when their median is this far out (Mahalanobis)
FLIGHT_DE = 3.0        # the same type on two flight days further apart than this (dE) asks for per-flight gains
ALBEDO_MIN_TYPES = 5   # the albedo fit needs at least this many measured types with an albedo...
ALBEDO_MIN_R = 0.5     # ...and this correlation, or it doesn't set L

PHOTO = "naip2025"
MASK = "photo-v1"


class Group:
    """Sums over some (map unit, flight) keys of an Accumulator, with a polygon count."""

    def __init__(self, acc=None, rows=(), polygons=0):
        self.n = 0
        self.s = np.zeros(len(P.SUMS))
        self.h = np.zeros((3, P.BINS))
        self.tn = np.zeros(len(P.OCTAVES_M))
        self.tl = np.zeros(len(P.OCTAVES_M))
        self.tc = np.zeros(len(P.OCTAVES_M))
        self.polygons = polygons
        rows = list(rows)
        if acc is not None and rows:
            self.n = int(acc.n[rows].sum())
            self.s = acc.s[rows].sum(axis=0)
            self.h = acc.h[rows].sum(axis=0).astype(np.float64)
            self.tn = acc.tn[rows].sum(axis=0)
            self.tl = acc.tl[rows].sum(axis=0)
            self.tc = acc.tc[rows].sum(axis=0)

    def __add__(self, other):
        g = Group()
        g.n = self.n + other.n
        for k in ("s", "h", "tn", "tl", "tc"):
            setattr(g, k, getattr(self, k) + getattr(other, k))
        g.polygons = self.polygons + other.polygons
        return g

    @property
    def measured(self):
        return self.n >= MIN_PX and self.polygons >= MIN_POLYGONS

    def summary(self):
        st = P.stats(self.n, self.s, self.h)
        if st is None:
            return None
        st["oct_l"], st["oct_c"] = P.energies(self.tn, self.tl, self.tc)
        return st


def total(groups):
    out = Group()
    for g in groups:
        out = out + g
    return out


def _row(level, key, flight, st, n_px, n_polygons, fallback=None):
    return {"level": level, "key": key, "photo": PHOTO, "flight": flight, "mask": MASK, "n_px": int(n_px),
            "n_polygons": n_polygons, "lab_med": _r(st["med"]), "lab_cov": _r(st["cov"], 8),
            "l_p10": _r(st["l_p10"]), "l_p90": _r(st["l_p90"]), "oct_l": _r(st["oct_l"], 8),
            "oct_c": _r(st["oct_c"], 8), "fallback": fallback}


def _r(v, places=5):
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return [None if x is None else round(float(x), places) for x in v]
    return round(float(v), places)


def _maha(x, centre, cov6):
    c = np.array([[cov6[0], cov6[1], cov6[2]], [cov6[1], cov6[3], cov6[4]], [cov6[2], cov6[4], cov6[5]]])
    d = np.asarray(x, np.float64) - np.asarray(centre, np.float64)
    try:
        return float(math.sqrt(max(float(d @ np.linalg.solve(c, d)), 0.0)))
    except np.linalg.LinAlgError:
        return None


def spearman(x, y):
    """Spearman's rho of two equal-length sequences (average ranks for ties), or None under 3 pairs."""
    if len(x) < 3:
        return None

    def ranks(v):
        v = np.asarray(v, np.float64)
        order = np.argsort(v, kind="mergesort")
        r = np.empty(len(v))
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            r[order[i:j + 1]] = (i + j) / 2.0
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def pool(mapunits, types, flights, acc, polygons, gains_applied=False):
    """Pool everything. mapunits: [{mukey, type}] in key order (map unit i, flight f is key i * len(flights) + f);
    types: {type id: {gid, series, texcl, landform, albedo_dry, misc}}; flights: ['2025-05-25', ...]; acc: the
    merged Accumulator; polygons: {"gid": array, "mu": array (map-unit index), "acc": Accumulator over them};
    gains_applied: whether the colours were put on one flight day's scale first (photo.Gains). Returns (rows,
    report)."""
    nf = len(flights)
    rows, report = [], {"thresholds": {"min_px": MIN_PX, "min_polygons": MIN_POLYGONS, "polygon_px": POLY_PX}}

    # Polygons that count, per map unit.
    pacc = polygons["acc"]
    counts = np.zeros(len(mapunits), np.int64)
    big = pacc.n >= POLY_PX
    np.add.at(counts, polygons["mu"][big], 1)

    mu_groups, mu_flight = [], []
    for i, mu in enumerate(mapunits):
        per = [Group(acc, [i * nf + f]) for f in range(nf)]
        g = total(per)
        g.polygons = int(counts[i])
        mu_groups.append(g)
        mu_flight.append(per)
        if g.n == 0:
            continue
        for f, pg in enumerate(per):
            if pg.n:
                rows.append(_row("mapunit", mu["mukey"], flights[f], pg.summary(), pg.n, None))
        rows.append(_row("mapunit", mu["mukey"], None, g.summary(), g.n, g.polygons))

    # Ground types: their map units summed.
    by_type = {}
    for i, mu in enumerate(mapunits):
        if mu["type"]:
            by_type.setdefault(mu["type"], []).append(i)
    tg, tflight = {}, {}
    for tid in types:
        idx = by_type.get(tid, [])
        tg[tid] = total(mu_groups[i] for i in idx)
        tflight[tid] = [total(mu_flight[i][f] for i in idx) for f in range(nf)]
    # A miscellaneous area can't borrow (it has no series, texture or albedo of its own), so it keeps its own
    # measurement from fewer polygons, as long as it has the pixels: one dune field is better than none.
    measured = {t for t, g in tg.items() if types[t].get("misc") != "nodata"
                and (g.measured or (types[t].get("misc") and g.n >= MIN_PX and g.polygons >= 1))}
    soils = [t for t in types if types[t].get("misc") is None]

    # The albedo fit over measured soils.
    fit_pts = [(types[t]["albedo_dry"], tg[t].summary()["med"][0]) for t in sorted(measured)
               if types[t].get("misc") is None and types[t].get("albedo_dry") is not None]
    fit = None
    if len(fit_pts) >= ALBEDO_MIN_TYPES:
        x = np.array([p[0] for p in fit_pts])
        y = np.array([p[1] for p in fit_pts])
        if x.std() > 0:
            slope, icept = np.polyfit(x, y, 1)
            fit = {"slope": float(slope), "intercept": float(icept), "n": len(fit_pts),
                   "r": float(np.corrcoef(x, y)[0, 1])}
            fit["sets_l"] = fit["r"] >= ALBEDO_MIN_R
            fit["l_range"] = [round(icept + slope * float(np.percentile(x, 5)), 4),
                              round(icept + slope * float(np.percentile(x, 95)), 4)]
    report["albedo_fit"] = fit

    def peers(pred):
        return total(tg[t] for t in soils if pred(types[t]))

    status, weak_fit = {}, []
    for tid in sorted(types):
        t, g = types[tid], tg[tid]
        if tid in measured:
            st = g.summary()
            for f in range(nf):
                fg = tflight[tid][f]
                if fg.n:
                    rows.append(_row("ground_type", tid, flights[f], fg.summary(), fg.n, None))
            rows.append(_row("ground_type", tid, None, st, g.n, g.polygons))
            status[tid] = {"status": "measured", "n_px": g.n, "n_polygons": g.polygons, "med": st["med"]}
            continue
        if t.get("misc") is not None:
            status[tid] = {"status": "none", "n_px": g.n, "n_polygons": g.polygons,
                           "why": "a miscellaneous area borrows nothing" if t["misc"] != "nodata" else "not surveyed"}
            continue
        borrowed = None
        series = (t.get("series") or "").lower()
        sp = peers(lambda o: (o.get("series") or "").lower() == series)
        if series and sp.measured:
            borrowed = ("series", sp.summary(), f"series {t.get('series')}: {sp.n} px, {sp.polygons} polygons")
        if borrowed is None and t.get("texcl"):
            tp = peers(lambda o: o.get("texcl") == t.get("texcl") and o.get("landform") == t.get("landform"))
            if tp.measured:
                borrowed = ("texture", tp.summary(),
                            f"{t.get('texcl')} on {t.get('landform') or 'no landform'}: {tp.n} px, "
                            f"{tp.polygons} polygons")
        if borrowed is None and fit is not None and t.get("albedo_dry") is not None:
            cp = peers(lambda o: t.get("texcl") is not None and o.get("texcl") == t.get("texcl"))
            label = f"texture class {t.get('texcl')}"
            if not cp.measured:
                cp = total(tg[o] for o in soils if o in measured)
                label = "all measured soils"
            st = cp.summary()
            if st is not None and fit["sets_l"]:
                L = fit["intercept"] + fit["slope"] * t["albedo_dry"]
                shift = L - st["med"][0]
                st["med"] = [L, st["med"][1], st["med"][2]]
                st["l_p10"] = st["l_p10"] + shift
                st["l_p90"] = st["l_p90"] + shift
                borrowed = ("albedo", st, f"L from dry albedo {t['albedo_dry']:g}; chroma, hue, spread and texture "
                                          f"from {label} ({cp.n} px)")
            elif st is not None:
                weak_fit.append(tid)
                borrowed = ("texture", st, f"{label} on any landform ({cp.n} px), L included: the dry-albedo fit is "
                                           f"too weak to set L (r {fit['r']:.2f} under {ALBEDO_MIN_R:g})")
        if borrowed is None:
            status[tid] = {"status": "none", "n_px": g.n, "n_polygons": g.polygons,
                           "why": "no series, texture-class or albedo peers measured"}
            continue
        kind, st, what = borrowed
        rows.append(_row("ground_type", tid, None, st, g.n, g.polygons, fallback=kind))
        status[tid] = {"status": kind, "n_px": g.n, "n_polygons": g.polygons, "med": st["med"], "from": what}
    for tid, s in status.items():
        s["gid"] = types[tid].get("gid")
        if s.get("med"):
            s["med"] = _r(s["med"])
            s["srgb"] = "#%02x%02x%02x" % P.oklab_to_srgb(s["med"])
    report["types"] = status
    # Said in the report too: types that would have taken L from dry albedo but keep their peers' L (labelled texture).
    report["albedo_fallback"] = {
        "taken": bool(weak_fit), "types": len(weak_fit), "fit_r": round(fit["r"], 3) if fit else None,
        "min_r": ALBEDO_MIN_R,
        "note": (f"{len(weak_fit)} types would have taken L from dry albedo, but the fit has almost no skill "
                 f"(r {fit['r']:.2f}, the cut is {ALBEDO_MIN_R:g}): they take their texture-class peers' L and are "
                 f"labelled texture" if weak_fit and fit else "no type fell back for a weak albedo fit")}
    report["counts"] = {k: sum(1 for s in status.values() if s["status"] == k)
                        for k in ("measured", "series", "texture", "albedo", "none")}

    # Check: the same type on different flight days.
    spread = []
    for tid in sorted(measured):
        meds = [(flights[f], tflight[tid][f].summary()["med"]) for f in range(nf) if tflight[tid][f].n >= MIN_PX]
        if len(meds) >= 2:
            worst = max(P.delta_e(a[1], b[1]) for i, a in enumerate(meds) for b in meds[i + 1:])
            spread.append({"type": tid, "flights": [m[0] for m in meds], "max_de": round(worst, 2)})
    des = [s["max_de"] for s in spread]
    # How much of that is the flight, not the place: per pair of days, the median over types of the paired difference
    # (later day minus earlier). A flight's own offset shows as a median far from 0 with a narrow spread; a type's
    # spread over the valley shows as a wide one around 0.
    pairs = {}
    for tid in sorted(measured):
        meds = {flights[f]: tflight[tid][f].summary()["med"] for f in range(nf) if tflight[tid][f].n >= MIN_PX}
        days = sorted(meds)
        for i, d1 in enumerate(days):
            for d2 in days[i + 1:]:
                pairs.setdefault(f"{d1}/{d2}", []).append([100 * (meds[d2][c] - meds[d1][c]) for c in range(3)])
    offsets = {}
    for k, v in pairs.items():
        arr = np.array(v)
        med = np.median(arr, axis=0)
        q1, q3 = np.percentile(arr[:, 0], (25, 75))
        offsets[k] = {"types": len(v), "dL": round(float(med[0]), 2), "da": round(float(med[1]), 2),
                      "db": round(float(med[2]), 2), "dE": round(float(np.sqrt(np.sum(med ** 2))), 2),
                      "dL_iqr": [round(float(q1), 2), round(float(q3), 2)]}
    over = bool(des) and float(np.median(des)) > FLIGHT_DE
    report["flight_days"] = {
        "gains_applied": bool(gains_applied),
        "types_on_two_or_more": len(spread),
        "median_max_de": round(float(np.median(des)), 2) if des else None,
        "share_over": round(sum(d > FLIGHT_DE for d in des) / len(des), 3) if des else None,
        "over_rule": over,
        "gains_needed": over and not gains_applied,
        "rule": f"per-flight colour gains are needed when the median type's largest dE between flight days is over "
                f"{FLIGHT_DE:g}; with the gains applied (gains_applied), the same numbers are what's left, mostly "
                f"each type's spread over the valley (pair_offsets separates the flights' own offsets)",
        "types": spread,
        "pair_offsets": offsets,
        "pair_offsets_about": "per pair of flight days, the median over the types measured on both of the paired "
                              "difference (later minus earlier, OKLab x 100), with L's interquartile range: the "
                              "flights' own offset, apart from the types' spread over the valley",
    }

    # Check: how much of the colour variance the types explain (pixels of measured types, by their means).
    gs = [tg[t] for t in measured]
    N = sum(g.n for g in gs)
    if N > 1 and gs:
        mean = sum(g.s[:3] for g in gs) / N
        second = sum(g.s[3:] for g in gs) / N
        tot = (second[0] - mean[0] ** 2) + (second[3] - mean[1] ** 2) + (second[5] - mean[2] ** 2)
        between = sum(g.n * float(np.sum((g.s[:3] / g.n - mean) ** 2)) for g in gs) / N
        report["variance_explained"] = round(between / tot, 4) if tot > 0 else None
    else:
        report["variance_explained"] = None

    # Check: type L against dry albedo.
    report["spearman_l_albedo"] = _r(spearman([p[0] for p in fit_pts], [p[1] for p in fit_pts]), 4)
    report["spearman_n"] = len(fit_pts)

    # Check: polygons far from their type.
    out = []
    type_stats = {t: tg[t].summary() for t in measured}
    for j in np.nonzero(pacc.n >= OUTLIER_PX)[0]:
        tid = mapunits[polygons["mu"][j]]["type"]
        ts = type_stats.get(tid)
        if ts is None:
            continue
        med = [P.hist_quantile(pacc.h[j, c], 0.5, c) for c in range(3)]
        d = _maha(med, ts["med"], ts["cov"])
        if d is not None and d > OUTLIER_D:
            out.append({"polygon": int(polygons["gid"][j]), "mukey": mapunits[polygons["mu"][j]]["mukey"],
                        "type": tid, "n_px": int(pacc.n[j]), "med": _r(med), "type_med": _r(ts["med"]),
                        "mahalanobis": round(d, 2), "de": round(P.delta_e(med, ts["med"]), 2)})
    out.sort(key=lambda o: -o["mahalanobis"])
    report["polygon_outliers"] = {"checked": int((pacc.n >= OUTLIER_PX).sum()), "listed": len(out),
                                  "rule": f"median more than {OUTLIER_D:g} from the type (Mahalanobis, the type's "
                                          f"pixel covariance); polygons with {OUTLIER_PX}+ pixels",
                                  "polygons": out}
    return rows, report
