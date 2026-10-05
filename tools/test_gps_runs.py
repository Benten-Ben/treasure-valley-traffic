"""Tests for gps_runs.py using simulated runs through a synthetic corridor.

Run: python3 -m unittest discover tools
"""

import csv
import os
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import gps_runs  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CYCLE = 150          # s, common coordinated cycle
GREEN = 60           # s of through green per cycle
SPEED = 20.0         # m/s cruise
M_PER_DEG_LAT = 111_320.0
LON = -116.3545
START_LAT = 43.672
# Signals every ~800 m with their own offsets, as on a coordinated arterial.
SIGNALS = [(800 * (k + 1), (17 * k) % CYCLE) for k in range(5)]


def simulate_run(t0, rng):
    """1 Hz trackpoints for one southbound run.

    On red, the car waits until green plus start-up loss and its queue
    position (2-8 s after the green starts), as real departures vary.
    """
    pts, t, pos = [], t0, 0.0
    end = SIGNALS[-1][0] + 400
    next_sig = 0
    while pos < end:
        pts.append((t, START_LAT - pos / M_PER_DEG_LAT, LON))
        nxt = pos + SPEED
        if next_sig < len(SIGNALS) and nxt >= SIGNALS[next_sig][0]:
            sig_pos, offset = SIGNALS[next_sig]
            arrive = t + (sig_pos - pos) / SPEED
            phase = (arrive - offset) % CYCLE
            if phase >= GREEN:  # red: wait at the stop bar until next green
                depart = arrive + (CYCLE - phase) + rng.uniform(2, 8)
                for s in range(int(arrive), int(depart)):
                    pts.append((s, START_LAT - (sig_pos - 5) / M_PER_DEG_LAT, LON))
                t, pos = depart, sig_pos
            next_sig += 1
            continue
        t, pos = t + 1, nxt
    return pts


def write_gpx(path, pts):
    with open(path, "w") as f:
        f.write('<?xml version="1.0"?><gpx version="1.1" creator="test" '
                'xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>')
        for t, lat, lon in pts:
            ts = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"><time>{ts}</time></trkpt>')
        f.write("</trkseg></trk></gpx>")


class GpsRunsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Two nodes per intersection (as OSM maps divided roads) to exercise clustering.
        sig_csv = os.path.join(self.tmp, "signals.csv")
        with open(sig_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["name", "lat", "lon"])
            for k, (pos, _) in enumerate(SIGNALS):
                lat = START_LAT - pos / M_PER_DEG_LAT
                w.writerow([f"Main St & Cross {k}", lat, LON - 0.0002])
                w.writerow([f"Main St & Cross {k}", lat, LON + 0.0002])
        self.sig_csv = sig_csv
        rng = random.Random(7)
        base = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc).timestamp()
        self.gpx = []
        for i in range(25):
            p = os.path.join(self.tmp, f"run{i:02d}.gpx")
            write_gpx(p, simulate_run(base + rng.uniform(0, 7200), rng))
            self.gpx.append(p)

    def test_clusters_duplicate_nodes(self):
        self.assertEqual(len(gps_runs.read_signals(self.sig_csv)), len(SIGNALS))

    def test_detects_stops_and_cycle(self):
        out = os.path.join(self.tmp, "out")
        subprocess.run([sys.executable, os.path.join(HERE, "gps_runs.py"), *self.gpx,
                        "--signals", self.sig_csv, "--out", out, "--estimate-cycle"],
                       check=True, capture_output=True)
        with open(os.path.join(out, "signals.csv")) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(SIGNALS))
        for r in rows:
            self.assertEqual(int(r["passes"]), 25)
            self.assertLessEqual(int(r["stopped"]), 25)
            if int(r["stopped"]) >= 8:
                self.assertAlmostEqual(float(r["est_cycle_s"]), CYCLE, delta=2,
                                       msg=r["signal"])
        with open(os.path.join(out, "runs.csv")) as f:
            runs = list(csv.DictReader(f))
        self.assertEqual(len(runs), 25)


if __name__ == "__main__":
    unittest.main()
