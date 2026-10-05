#!/usr/bin/env python3
"""Analyze GPS "floating car" runs through signalized corridors.

Drive a corridor with a phone logging GPS (e.g., GPSLogger for Android,
OsmAnd, or any app that exports GPX with timestamps at 1-second intervals),
then run:

  python3 tools/gps_runs.py runs/*.gpx --signals data/static/osm_traffic_signals.geojson

--signals accepts the GeoJSON written by collect_static.py or a CSV with
columns name,lat,lon (handy for listing just one corridor's signals by hand).

Outputs (in --out, default data/gps):
  runs.csv     one row per run: duration, distance, average speed, stops, stopped time
  stops.csv    one row per stop: run, time, duration, nearest signal, distance to it
  signals.csv  one row per signal: runs passing it, share that stopped, mean stop time

--estimate-cycle (experimental) looks for a common cycle length at each signal
from the times vehicles started moving after a stop. Coordinated signals repeat
on a fixed cycle, so with enough departures (roughly 10+ in the same time-of-day
plan) the departure times line up modulo the cycle. This is the same basic idea
Google's Green Light uses at scale with Maps data.
"""

import argparse
import csv
import json
import math
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

STOP_SPEED_MS = 2.0       # below ~4.5 mph counts as stopped
MIN_STOP_S = 3            # ignore shorter slowdowns
SIGNAL_RADIUS_M = 150     # queue can extend this far back from the stop bar
PASS_RADIUS_M = 40        # a run "passes" a signal if it comes this close


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_time(text):
    return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))


def read_gpx(path):
    """Return [(epoch_seconds, lat, lon), ...] sorted by time."""
    points = []
    for el in ET.parse(path).iter():
        if el.tag.endswith("trkpt"):
            t = next((c.text for c in el if c.tag.endswith("time")), None)
            if t:
                points.append((parse_time(t).timestamp(), float(el.get("lat")),
                               float(el.get("lon"))))
    return sorted(points)


def cluster_signals(nodes, radius_m=60):
    """Merge signal nodes that belong to one intersection.

    OSM often maps a signal node per approach on divided roads, so one
    intersection can appear as 2-6 nodes. Nodes within radius_m of each other
    (transitively) are merged into one point with the combined street names.
    """
    parent = list(range(len(nodes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if haversine_m(nodes[i]["lat"], nodes[i]["lon"],
                           nodes[j]["lat"], nodes[j]["lon"]) < radius_m:
                parent[find(i)] = find(j)

    groups = {}
    for i, n in enumerate(nodes):
        groups.setdefault(find(i), []).append(n)
    merged = []
    for members in groups.values():
        streets = sorted({s.strip() for m in members for s in m["name"].split("&")
                          if s.strip() and not s.strip().startswith("osm ")})
        merged.append({
            "name": " & ".join(streets) or members[0]["name"],
            "lat": sum(m["lat"] for m in members) / len(members),
            "lon": sum(m["lon"] for m in members) / len(members),
        })
    return merged


def read_signals(path):
    signals = []
    if path.endswith((".geojson", ".json")):
        with open(path) as f:
            for ft in json.load(f)["features"]:
                lon, lat = ft["geometry"]["coordinates"][:2]
                props = ft.get("properties", {})
                name = props.get("streets") or props.get("name") or f"osm {props.get('osm_id')}"
                signals.append({"name": name, "lat": lat, "lon": lon})
    else:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                signals.append({"name": row["name"], "lat": float(row["lat"]),
                                "lon": float(row["lon"])})
    return cluster_signals(signals)


def nearest_signal(signals, lat, lon):
    best, best_d = None, float("inf")
    for i, s in enumerate(signals):
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if d < best_d:
            best, best_d = i, d
    return best, best_d


def find_stops(points):
    """Group consecutive slow points into stop events."""
    stops, current = [], []
    for (t0, la0, lo0), (t1, la1, lo1) in zip(points, points[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        speed = haversine_m(la0, lo0, la1, lo1) / dt
        if speed < STOP_SPEED_MS:
            current.append((t0, la0, lo0))
            current.append((t1, la1, lo1))
        elif current:
            stops.append(current)
            current = []
    if current:
        stops.append(current)

    events = []
    for pts in stops:
        start, end = pts[0][0], pts[-1][0]
        if end - start >= MIN_STOP_S:
            lat = sum(p[1] for p in pts) / len(pts)
            lon = sum(p[2] for p in pts) / len(pts)
            events.append({"start": start, "end": end, "duration": end - start,
                           "lat": lat, "lon": lon})
    return events


def best_cycle(departures, lo=50, hi=200):
    """Find the cycle length (s) that best aligns departure times.

    For each candidate cycle C, map each departure to an angle 2*pi*(t mod C)/C
    and measure how tightly the angles cluster (mean resultant length R, 0..1).
    Returns (cycle, R). Departures that repeat every C seconds also repeat
    every C/2, C/3, ..., so those fractions score as well as the true cycle,
    while multiples (2C, 3C) split into separate clusters and score poorly.
    The longest strong peak is therefore preferred.
    """
    if len(departures) < 5:
        return None, 0.0
    scores = []
    for c10 in range(lo * 10, hi * 10 + 1, 5):   # 0.5 s steps
        c = c10 / 10
        xs = sum(math.cos(2 * math.pi * (t % c) / c) for t in departures)
        ys = sum(math.sin(2 * math.pi * (t % c) / c) for t in departures)
        scores.append((c, math.hypot(xs, ys) / len(departures)))
    top = max(r for _, r in scores)
    for c, r in reversed(scores):    # longest cycle within 90% of the best score
        if r >= 0.9 * top:
            return c, r
    return None, 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("gpx", nargs="+")
    ap.add_argument("--signals", required=True)
    ap.add_argument("--out", default="data/gps")
    ap.add_argument("--estimate-cycle", action="store_true")
    args = ap.parse_args()

    signals = read_signals(args.signals)
    if not signals:
        sys.exit("no signals loaded")
    os.makedirs(args.out, exist_ok=True)

    run_rows, stop_rows = [], []
    per_signal = {i: {"passes": 0, "stopped": 0, "stop_s": 0.0, "departures": []}
                  for i in range(len(signals))}

    for path in args.gpx:
        pts = read_gpx(path)
        if len(pts) < 2:
            print(f"{path}: no timestamped points, skipped", file=sys.stderr)
            continue
        run = os.path.basename(path)
        dist = sum(haversine_m(a[1], a[2], b[1], b[2]) for a, b in zip(pts, pts[1:]))
        dur = pts[-1][0] - pts[0][0]

        # Which signals did this run pass?
        passed = {i for i, s in enumerate(signals)
                  if any(haversine_m(p[1], p[2], s["lat"], s["lon"]) < PASS_RADIUS_M
                         for p in pts)}
        for i in passed:
            per_signal[i]["passes"] += 1

        stops = find_stops(pts)
        stopped_at = set()
        for ev in stops:
            idx, d = nearest_signal(signals, ev["lat"], ev["lon"])
            at_signal = d <= SIGNAL_RADIUS_M
            if at_signal:
                ps = per_signal[idx]
                if idx not in stopped_at:
                    ps["stopped"] += 1
                    stopped_at.add(idx)
                ps["stop_s"] += ev["duration"]
                ps["departures"].append(ev["end"])
            stop_rows.append({
                "run": run,
                "start": datetime.fromtimestamp(ev["start"]).astimezone().isoformat(),
                "duration_s": round(ev["duration"]),
                "signal": signals[idx]["name"] if at_signal else "",
                "dist_to_signal_m": round(d) if at_signal else "",
            })

        run_rows.append({
            "run": run,
            "start": datetime.fromtimestamp(pts[0][0]).astimezone().isoformat(),
            "duration_s": round(dur), "distance_km": round(dist / 1000, 2),
            "avg_speed_mph": round(dist / dur * 2.23694, 1) if dur else "",
            "stops": len(stops),
            "stopped_s": round(sum(e["duration"] for e in stops)),
            "signals_passed": len(passed),
        })

    sig_rows = []
    for i, ps in per_signal.items():
        if not ps["passes"] and not ps["stopped"]:
            continue
        row = {"signal": signals[i]["name"], "lat": signals[i]["lat"],
               "lon": signals[i]["lon"], "passes": ps["passes"],
               "stopped": ps["stopped"],
               "share_stopped": round(ps["stopped"] / ps["passes"], 2) if ps["passes"] else "",
               "mean_stop_s": round(ps["stop_s"] / ps["stopped"]) if ps["stopped"] else 0}
        if args.estimate_cycle:
            c, r = best_cycle(ps["departures"])
            row["est_cycle_s"], row["cycle_fit"] = (c or "", round(r, 2))
        sig_rows.append(row)
    sig_rows.sort(key=lambda r: (-r["stopped"], -r["mean_stop_s"]))

    for name, rows in (("runs", run_rows), ("stops", stop_rows), ("signals", sig_rows)):
        if not rows:
            continue
        with open(os.path.join(args.out, f"{name}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    print(f"{len(run_rows)} runs, {len(stop_rows)} stops -> {args.out}/")
    for r in sig_rows[:15]:
        extra = f"  cycle~{r['est_cycle_s']}s (fit {r['cycle_fit']})" if args.estimate_cycle and r.get("est_cycle_s") else ""
        print(f"  {r['signal'][:40]:40} stopped {r['stopped']}/{r['passes']}"
              f"  mean stop {r['mean_stop_s']}s{extra}")


if __name__ == "__main__":
    main()
