# Reference datasets

The research uses a few dated reference datasets (Oct 5, 2026). They are
copies of other agencies' data, some collected in one-off checks of pages
whose robots.txt asks crawlers to stay away. So they're kept with the
project's private files on its server, with their full provenance, and
**not published here**.

| Dataset | Source | How it was collected |
|---|---|---|
| ACHD traffic counts: 7,696 rows (one per direction) at 3,827 locations, dated 1994–2026 | ACHD's public [Traffic Counts](https://www.achdidaho.org/my-commute/traffic/traffic-counts) table | A one-time copy, approved by the owner as an exception. Paced requests with our identifying User-Agent. Not repeated without the owner's OK. |
| ACHD turning-movement counts: 2,300 rows at 916 intersections, dated 1997–2026 | ACHD's public [Traffic Turn Movements](https://www.achdidaho.org/my-commute/traffic-turn-movements) table | Same |
| 511 Idaho camera views: one row per image view in the valley | 511 Idaho's website camera list | One-off check. To be replaced by the official 511 API (key required). |
| Camera inventory: 248 rows (ACHD 228, ITD 2, road-weather 18) | ACHD's open GIS camera layer, plus 511's camera list | ACHD's layer allows automated access. The 511 parts came from the one-off check. |

**Published elsewhere, openly:**

- **ACHD camera locations:** ACHD's open GIS layer, read by
  [`basemap/camera_points.py`](../../basemap/camera_points.py) and the
  `achd_cameras` ingest source.
- **Counts and turn movements, with their history:** we've asked ACHD for
  official CSV exports. Anything ACHD publishes or licenses openly can be
  added here later.

Credit: Ada County Highway District; Idaho Transportation Department
(511 Idaho). No license is stated on the source pages.
