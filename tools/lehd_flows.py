"""Where Treasure Valley workers live and work: LEHD LODES commute flows.

The Census Bureau's LODES data (public domain) counts jobs by the census block
where the worker lives and the block where they work. This script sums them
by county for Ada, Canyon and the counties around them (including Malheur
County, Oregon), and by town for residents outside Ada and Canyon: how many
of their jobs are in Ada or Canyon.

Download the files into one folder first (LODES8, all jobs, one year):

    B=https://lehd.ces.census.gov/data/lodes/LODES8
    for f in id/od/id_od_main_JT00_2023 id/od/id_od_aux_JT00_2023 \\
             or/od/or_od_main_JT00_2023 or/od/or_od_aux_JT00_2023 id/id_xwalk or/or_xwalk; do
      curl -O "$B/$f.csv.gz"; done
    python3 tools/lehd_flows.py data/lehd --year 2023

Caveats: LODES counts jobs, not people or trips. It leaves out the military
and the self-employed, and it places a job at the employer's address, so
remote work and multi-site employers can look like long commutes.
"""

import argparse
import csv
import gzip
import os
from collections import Counter, defaultdict

REGION = {"16001": "Ada", "16027": "Canyon", "16045": "Gem", "16075": "Payette", "16073": "Owyhee",
          "16087": "Washington", "16015": "Boise Co.", "16039": "Elmore", "41045": "Malheur OR"}
OUTSIDE = ["Rest of ID", "Rest of OR", "Other states"]
CORE = ("Ada", "Canyon")


def county_name(fips):
    if fips in REGION:
        return REGION[fips]
    return "Rest of ID" if fips.startswith("16") else "Rest of OR" if fips.startswith("41") else "Other states"


def place_name(raw):
    return (raw or "").replace(" city", "").replace(" CDP", "") or None


def read_crosswalks(folder):
    """Block → (county name, town name or None)."""
    blocks = {}
    for st in ("id", "or"):
        with gzip.open(os.path.join(folder, f"{st}_xwalk.csv.gz"), "rt") as f:
            for r in csv.DictReader(f):
                blocks[r["tabblk2020"]] = (county_name(r["cty"]), place_name(r["stplcname"]))
    return blocks


def flows(folder, year, blocks):
    """(county flows {(home, work): jobs}, town flows {(town, home county): {work county: jobs}})."""
    by_county, by_town = Counter(), defaultdict(Counter)
    for name in (f"id_od_main_JT00_{year}", f"id_od_aux_JT00_{year}",
                 f"or_od_main_JT00_{year}", f"or_od_aux_JT00_{year}"):
        with gzip.open(os.path.join(folder, f"{name}.csv.gz"), "rt") as f:
            for r in csv.DictReader(f):
                home, work, jobs = r["h_geocode"], r["w_geocode"], int(r["S000"])
                hc, town = blocks.get(home, (county_name(home[:5]), None))
                wc = blocks.get(work, (county_name(work[:5]), None))[0]
                if hc not in REGION.values() and wc not in REGION.values():
                    continue
                by_county[(hc, wc)] += jobs
                if hc in REGION.values():
                    by_town[(town or f"rural {hc}", hc)][wc] += jobs
    return by_county, by_town


def report(by_county, by_town, towns=25):
    cols = list(REGION.values())
    lines = ["Jobs by home county (rows) and work county (columns)", "",
             "| Home \\ work | " + " | ".join(cols) + " | Elsewhere | Total | In Ada or Canyon |",
             "|---" * (len(cols) + 4) + "|"]
    for hc in cols + OUTSIDE:
        row = [by_county[(hc, wc)] for wc in cols]
        elsewhere = sum(v for (h, w), v in by_county.items() if h == hc and w not in cols)
        total = sum(row) + elsewhere
        if not total:
            continue
        core = sum(by_county[(hc, c)] for c in CORE)
        share = f" ({100 * core / total:.0f}%)" if hc in cols else ""
        lines.append(f"| {hc} | " + " | ".join(f"{v:,}" for v in row) + f" | {elsewhere:,} | {total:,} | {core:,}{share} |")
    lines += ["", "Towns outside Ada and Canyon, by jobs held in Ada or Canyon", "",
              "| Town | County | Residents' jobs | In Ada | In Canyon | Share |", "|---|---|---|---|---|---|"]
    rows = []
    for (town, hc), work in by_town.items():
        if hc in CORE:
            continue
        total, core = sum(work.values()), sum(work[c] for c in CORE)
        rows.append((core, town, hc, total, work["Ada"], work["Canyon"]))
    for core, town, hc, total, ada, canyon in sorted(rows, reverse=True)[:towns]:
        lines.append(f"| {town} | {hc} | {total:,} | {ada:,} | {canyon:,} | {100 * core / total:.0f}% |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", help="folder with the LODES .csv.gz files")
    ap.add_argument("--year", default="2023")
    ap.add_argument("--towns", type=int, default=25, help="how many towns to list")
    args = ap.parse_args()
    blocks = read_crosswalks(args.folder)
    print(report(*flows(args.folder, args.year, blocks), towns=args.towns))


if __name__ == "__main__":
    main()
