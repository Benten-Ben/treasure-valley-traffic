# farm

Farms and crops
([ch. 16](../../docs/16-ideas-and-personas.md#farmer-farm);
[ch. 17 §17.2](../../docs/17-sources-for-new-plugins.md#farms-and-crops)).
For now it collects one source: Reclamation's AgriMet crop water use (ET)
at the six AgriMet stations in the ring. It's part of Wave A, "start the
clocks" ([ch. 17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)):
the daily crop charts keep only their last four days, so their history
exists only if we read them. Later it holds the "farm water today" card,
the field card and the farmland story (ch. 17 §17.2).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `agrimet_et` | daily April to October; weekly November to March | U.S. Government work (public domain, inferred ⚠️); provisional data | U.S. Bureau of Reclamation, AgriMet | yes, labelled provisional |

**Tables:** none of its own. Everything goes to core's `raw.record` until
core's `met_station` and readings tables land
([ch. 17 §17.8](../../docs/17-sources-for-new-plugins.md#178-decisions-on-the-open-questions-oct-7),
Q8); its stations will then be the `agrimet` network.

## `agrimet_et`: AgriMet crop water use

Catalog entries: [farm.md](../../docs/sources/farm.md#usbr-agrimet-crop-water-use-charts-static-files),
[gardening.md](../../docs/sources/gardening.md#agrimet-crop-water-use-charts).

- **What:** daily evapotranspiration in inches of water a day: ETr (1982
  Kimberly-Penman alfalfa reference ET) all year, and each crop's ET while
  Reclamation's crop calendar for it runs. Parma, Nampa, Ontario and Grand
  View carry crops (alfalfa, pasture, lawn, grains, beets, onions,
  potatoes, beans, corn, peas, peppermint, grapes, apples and more); Boise
  and Boise Fairgrounds carry only ETr and lawn.
- **Stations** (Reclamation's `location.csv`, read Oct 7, 2026; all inside
  the ring, four of them in the valley box):

  | Code | Place | Since |
  |---|---|---|
  | BOII | Boise | 1995 |
  | BFGI | Boise Fairgrounds | 2013 |
  | NMPI | Nampa | 1996 |
  | PMAI | Parma | 1986 |
  | ONTO | Ontario, Oregon | 1992 |
  | GDVI | Grand View | 1992 |

- **Endpoints:** static text files on `www.usbr.gov`:
  - `/pn/agrimet/chart/<stn><yy>et.txt`, the year's ET summary, one row per
    day (cumulative, so each read covers the year so far; 5–41 KB);
  - `/pn/agrimet/chart/<stn>ch.txt`, the day's crop chart, "Estimated Crop
    Water Use" (CSV, about 1.6 KB): each crop's assumed calendar (start,
    full cover, terminate), the last four days, a forecast for the next
    day, the season's total and 7- and 14-day use. April to October only.
- **robots.txt:** `www.usbr.gov` disallows only `/pn-bin` and `/gp-bin`,
  so `/pn/agrimet/chart/` is allowed (checked Oct 7, 2026, and on every
  run through `ingest/http.py`). No crawl-delay; we space requests 3 s
  apart. `/pn-bin` (AgriMet's weather archives) and `data.usbr.gov`'s RISE
  API are disallowed and never used. GET only: the host resets HEAD.
- **Cadence:** Reclamation updates the files once a day (about 5:30–6:30
  MT), 1–3 days behind. April to October we read each station's chart and
  year file once a day (12 requests). November to March no chart is
  published, so we read only the year files, once a week (6 requests; 12 in
  the first two weeks of January, to close out December from last year's
  file).
- **What we keep** (`raw.record`, as readings: nothing is ever retired):
  - `PMAI:2026-10-05`, one station-day from the year file:
    `{"station", "date", "et_in": {"ETr": 0.14, "ALFP": 0.14, ...}}`.
    Crops not growing that day (`--`) are left out; anything that isn't a
    number is kept as written under `flags`.
  - `PMAI:chart:2026-10-06`, one day's chart: `{"station", "chart_date",
    "days", "crops": {label: {"start", "full_cover", "terminate", "et_in"
    (four days, oldest first), "forecast_in", "season_in", "use_7d_in",
    "use_14d_in"}}}`.
  - Each with the station's point. A value Reclamation revises adds a
    version; an unchanged day only moves `last_seen`.
- **Column labels:** repeated crop names are separate crop calendars
  (Parma has BEET twice and FCRN three times), so both files' columns are
  labelled by position: `BEET`, `BEET#2`. On the Oct 7 sample the chart's
  older days matched the year file for every crop, and each repeated
  crop's last day in the year file was its own calendar's terminate date.
- **Guards:** a file whose title names another station or year is refused;
  so is a year file with fewer than half the days we already hold for it
  (the file only grows during a year, so a short one is cut off). Other
  stations' files are still kept, and the run is logged as failed so it's
  seen. A missing file (404) is noted, not an error.
- **Limits:** the static files hold no temperature, rain, wind or
  humidity, so "lawn water use (ET)" can't subtract rain and degree-days
  can't come from here (farm.md, "Risks"). ETr is the only
  weather-derived value. Its Kimberly-Penman ETr isn't gridMET's ASCE
  ETr: convert before comparing. The crop calendars are Reclamation's
  assumptions, not observed planting. Past seasons are in the same static
  files (`<stn><yy>et.txt` for earlier years) but aren't loaded yet; that
  would be a one-off backfill.
- **Storage:** a station-day is about 80–350 bytes, a chart 0.5 KB (Boise)
  to 4 KB (Parma): roughly 30 KB a day in season, 6 MB a season; under
  1 KB a day off season.

**Commands:**

```bash
python3 -m ingest run agrimet_et
python3 -m unittest discover -s plugins/farm/tests -t .
```

**Ethics:** a federal agency's weather stations, nothing about people.
Values are provisional (Reclamation's
[disclaimer](https://www.usbr.gov/pn/agrimet/disclaimer.html)) and are
labelled so wherever we show them, credited to Reclamation AgriMet.
Collecting AgriMet's weather archives under `/pn-bin` would need
Reclamation's OK, an owner action
([ch. 17 §17.7](../../docs/17-sources-for-new-plugins.md#177-owner-actions-consolidated)).
