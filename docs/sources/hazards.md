# Hazards sources (researched Oct 7, 2026)

Sources for a fire and hazards subject: wildfire (incidents, perimeters,
satellite hotspots, burn history, risk, restrictions and closures), smoke
and air quality, NWS alerts and heat, floods, earthquakes and drought. Each
one is tied back to roads and traffic (closures, smoke and fog visibility,
evacuations, signals that could go dark in a power shutoff) and to replay.
"The ring" below is the proposed regional ring around Ada and Canyon
counties: about west −117.30, south 42.90, east −115.60, north 44.30
([DECISIONS](../DECISIONS.md)). The overview of every new plugin's sources
is in [chapter 17](../17-sources-for-new-plugins.md); the persona ideas
these sources serve are in [chapter 16](../16-ideas-and-personas.md#fire-and-weather-watcher-hazards-weather).

**Status:** research only. Nothing here is approved or built; sources go to
the owner one at a time ([SOURCES](../SOURCES.md)). Every entry was checked
on Oct 7, 2026 against the publisher's official pages, the ArcGIS/REST
metadata, robots.txt (with the project's own RFC 9309 parser in
`ingest/http.py`, matching paths case-insensitively) and the stated terms,
using our honest User-Agent. Of the 34 entries, 20 were confirmed, 13
corrected and 1 couldn't be verified; none was refuted. Each entry's result
is in the **Verified** column and its subsection.

**Requests made.** The research pass made small metadata and count
queries, 1–3 s apart: about 20 to NIFC's ArcGIS host, a few each to the IDL,
USFS and NWS map services, S3 bucket listings, NWPS (one gauge), USGS FDSN
(one count) and NCEI (directory listings), plus one 1.7 MB AirNow
`reportingarea.dat` to confirm the format and a HEAD on one FIRMS CSV. One
metadata request reached `hazards.fema.gov/arcgis` before its robots.txt
had been read; that path is disallowed, and the request wasn't repeated.
The verification pass read robots.txt on about 50 hosts (1 s apart) and
made about 15 NIFC metadata and statistics queries; 3 IDL, 3 USFS and about
8 NWS map-service metadata or 2-record queries; S3 listings for GOES-18
(4), NAQFC (1), RRFS (1) and HRRR (1), one HRRR `.idx` and one HEAD; 2 FIRMS
HEADs; one request each to NWPS (BIGI1), FDSN (a count), IPAWS (`$top=1`)
and IDWR (a status query); NCEI and HMS directory listings; and 4 ArcGIS
item or portal lookups. Neither pass used an account or key or downloaded a
dataset, and the verification sent nothing to `hazards.fema.gov`.

---

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| [NIFC WFIGS incidents and perimeters](https://data-nifc.opendata.arcgis.com/) | NIFC (WFIGS), from IRWIN | Live fire points and perimeters with discovery, containment and out times; 3,921 ring records, 522 perimeters | ArcGIS FeatureServer | None | Disclaimer only; credit NIFC/WFIGS and the IRWIN agencies | Allowed (403, no rules) | Use | Corrected |
| [NIFC Interagency Fire Perimeter History](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0) | IFPH (WFMRDA_Authoritative), in NIFC's org | 2,157 ring perimeters 1908–2019, plus 248 for 2020–2024 | ArcGIS FeatureServer; one-off, then yearly | None | "Strategic use only" disclaimer; credit the agencies and NIFC | Allowed (403) | Use | Corrected |
| [InciWeb](https://inciweb.wildfire.gov/) | USFS, for the interagency community | Incident narratives, closure notices, RSS | Web pages and RSS | None | Federal; not examined | **Disallowed** on both hosts | Avoid (link only) | Confirmed |
| [MTBS](https://burnseverity.cr.usgs.gov/direct-download) | USGS EROS and USFS | Large-fire perimeters and 30 m burn severity, 1984–2024 | One-off download | None | Federal; no license line found ⚠️ | Allowed | Use | Confirmed |
| [FPA FOD, 7th edition](https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.7) | USFS Research Data Archive | 2.66 million ignitions 1992–2024, with cause | One-off download (SQLite 220 MB) | None | "can be used without additional permissions or fees"; cite | Allowed | Use | Confirmed |
| [Wildfire Risk to Communities, 2nd edition](https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2) | USFS | 30 m burn probability, flame length and risk rasters | One-off download (Idaho 6.56 GB ⚠️) | None | Same use statement; cite Scott et al. 2024 | Allowed | Use | Confirmed |
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | NASA LANCE/ESDIS | VIIRS, MODIS and Landsat hotspots with fire radiative power | Keyless hourly CSVs; area API with a MAP_KEY | None (free MAP_KEY optional) | NASA open data; credit NASA FIRMS | Allowed, Crawl-delay 1 | Use | Corrected |
| [NOAA HMS](https://www.ospo.noaa.gov/products/land/hms.html) | NOAA NESDIS OSPO | Analyst-reviewed fire points; light, medium and heavy smoke polygons since 2005 | Daily KML, shapefile, text | None | Public domain; position disclaimer | Allowed (404; no Disallow lines) | Use | Corrected |
| [GOES-18 ABI Level 2 and GLM](https://registry.opendata.aws/noaa-goes/) | NOAA NESDIS via NODD (AWS) | 5-minute fire pixels with FRP, smoke and dust masks, aerosol optical depth, lightning | Anonymous S3, NetCDF4 | None | NODD: "can be used as desired"; credit | Allowed (404) | Use | Corrected |
| [NOAA NGFS](https://fire.data.nesdis.noaa.gov/) | NOAA NESDIS | GOES fire detection and tracking portal | Web portal only | Unknown | No terms found | **Disallowed** | Avoid (link only) | Corrected |
| [IDL fire restrictions](https://www.idl.idaho.gov/fire-restrictions-finder/) | Idaho Department of Lands | Restriction zones and their current stage | ArcGIS MapServer | None | None stated; credit IDL and send a courtesy note | Allowed (redirect to an error page) | Use | Corrected |
| [USFS Region 4 forest orders](https://apps.fs.usda.gov/fsgisx02/rest/services/r04/R04_Alerts_And_Closures_01/MapServer) | USFS Intermountain Region | Closure and prohibition orders with dates | ArcGIS MapServer | None | Federal; credit the region's GIS; link to the order | Allowed (403) | Use | Confirmed |
| [FEMS](https://www.wildfire.gov/page/fems-api) | USFS / interagency | NFDRS fire danger (ERC, burning index) and the RAWS archive | GraphQL API | Account with the API role | Federal; terms not seen | Allowed | Needs owner action | Confirmed |
| [AirNow files and API](https://docs.airnowapi.org/) | EPA AirNow; data from Idaho DEQ | Hourly AQI and concentrations per site; reporting-area forecasts | Keyless hourly files; the API (key) isn't for filling databases | None for the files | Guidelines: preliminary label, no altering, AQI colours, tell the agencies, not for guidance | Allowed | Use | Confirmed |
| [EPA AQS and AirData](https://aqs.epa.gov/aqsweb/documents/data_api.html) | US EPA | Validated monitor data from 1980 | Keyless AirData zips; API with a key | Free key (API only) | Public domain | Allowed (404) | Use | Confirmed |
| [PurpleAir](https://develop.purpleair.com/) | PurpleAir, Inc. | Low-cost PM sensors, many at homes | Paid API | Paid key | Proprietary; staff say redistribution goes against its terms | **Disallowed** | Avoid | Confirmed |
| [HRRR-Smoke](https://registry.opendata.aws/noaa-hrrr-pds/) | NOAA NWS/NCEP via NODD | Hourly 3 km near-surface and column smoke, visibility; forecasts to 18–48 h | Anonymous S3, GRIB2 by byte range | None | NODD terms | Allowed (404) | Use | Corrected |
| [NAQFC and NDGD air-quality services](https://noaa-nws-naqfc-pds.s3.amazonaws.com/) | NOAA NWS | PM2.5, ozone, smoke and dust forecasts | S3 (GRIB2/NetCDF) or ArcGIS ImageServer | None | Public domain; NODD terms | Allowed | Use | Confirmed |
| [DEQ crop residue burn decisions](https://www.deq.idaho.gov/air-quality/smoke-and-burning/crop-residue-burning/) | Idaho DEQ | Daily field-burn approvals and denials | Web map; no feed | None | Not checked | **Disallowed** (`/air/crb/`) | Avoid (link only) | Confirmed |
| [Wildland fire smoke outlooks](https://outlooks.wildlandfiresmoke.net/) | USFS and partners (Air Resource Advisors) | Narrative smoke outlooks during large incidents | Single-page web app; no feed | None | Federal; not checked | No rules | Avoid (link only) | Confirmed |
| [NWS API alerts](https://www.weather.gov/documentation/services-web-api) | NOAA NWS | Live alerts as CAP/GeoJSON, past 7 days | REST API | None | "free to use for any purpose" | **Disallowed** (`Disallow: /`) | Needs owner action | Confirmed |
| [NWS watches, warnings and advisories map service](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer) | NOAA NWS (SPC for outlooks) | Current alert polygons; SPC fire-weather outlooks | ArcGIS MapServer; national tarballs | None | Public domain | Allowed; SPC's own site disallowed | Use | Corrected |
| [IEM NWS warning archive](https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml) | Iowa Environmental Mesonet | Archived warnings: polygons since 2002, VTEC events since Nov 2005 | Scripted request or yearly zips | None | NWS products redistributed; no formal terms, credit IEM ⚠️ | Allowed, Crawl-delay 120 | Use | Confirmed |
| [IPAWS archived alerts](https://www.fema.gov/openfema-data-page/ipaws-archived-alerts-v1) | FEMA via OpenFEMA | 4.9 million CAP alerts since June 2012, 24 h delay | OpenFEMA API; bulk files | None | OpenFEMA terms: required statement; statistical or reporting use | Allowed (403) | Use | Confirmed |
| [Genasys Protect](https://protect.genasys.com/) | Genasys Inc. | Evacuation zones with live status | Viewer; data feed under agreement ⚠️ | Partnership | Proprietary ⚠️ | Allowed, but terms govern the feed | Needs owner action | Corrected |
| [Idaho Power PSPS areas](https://www.idahopower.com/outages-safety/wildfire-safety/psps-event-information/) | Idaho Power | Areas monitored for, or in, a power shutoff | Public ArcGIS web app | Unknown | Not found; ask first | No rules found; data host unchecked | Needs owner action | Corrected |
| [NWS HeatRisk](https://www.wpc.ncep.noaa.gov/heatrisk/) | NWS WPC with the CDC | Daily heat-risk category 0–4 for 7 days (experimental) | KML, GeoTIFF, ImageServer | None | Public domain | Allowed | Use | Confirmed |
| [NWPS river forecasts](https://water.noaa.gov/about/api) | NWS OWP / Northwest RFC | Gauge stage and flow, forecasts, flood categories, historic crests | REST API | None | Public domain | Allowed (404) | Use | Confirmed |
| [USGS Water Data APIs](https://api.waterdata.usgs.gov/) | USGS | 15-minute values at every USGS gauge | New OGC API; legacy WaterServices | None (new API's key policy unchecked ⚠️) | Public domain | **New API's data paths disallowed**; legacy allowed but retiring Q1 2027 | Needs owner action | Confirmed |
| [FEMA NFHL](https://www.fema.gov/flood-maps/national-flood-hazard-layer) | FEMA | Effective flood zones, base flood elevations, levees, map revisions | Hand download from MSC | None | No license stated ⚠️ | **Disallowed** (`/arcgis`, MSC downloads) | Needs owner action | Corrected |
| [USGS post-fire debris-flow assessments](https://www.usgs.gov/programs/landslide-hazards/science/postfire-debris-flow-hazards) | USGS Landslide Hazards Program | Per-fire basin likelihood and volume of debris flows | Dashboard; by hand per fire ⚠️ | None | Public domain ⚠️ | Dashboard host allowed; www.usgs.gov unreachable | Use (by hand) | Unverifiable |
| [USGS earthquakes](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) | USGS Earthquake Hazards Program | Live GeoJSON feeds; FDSN history | GeoJSON feeds and FDSN queries | None | Public domain; credit USGS | Allowed (404) | Use | Confirmed |
| [U.S. Drought Monitor](https://droughtmonitor.unl.edu/) | NDMC with USDA, NOAA and NASA | Weekly D0–D4 drought polygons since 2000 | NDMC's ArcGIS service; statistics API | None | Credit text required | Official `/data/` disallowed; NDMC's ArcGIS and statistics hosts allowed | Use | Corrected |
| [NCEI Storm Events](https://www.ncei.noaa.gov/stormevents/ftp.jsp) | NOAA NCEI | Hazard events by county or zone since 1950 | Yearly CSV.gz | None | Public domain ⚠️ | Allowed (the CSV folder) | Use | Confirmed |

Verdicts: 23 use, 6 need an owner action, 5 avoid. Effort is S (small),
M or L (large).

---

## Fire incidents, perimeters and history

### NIFC WFIGS fire incidents and perimeters

**Use** · effort S · confidence high · no key · verified: corrected.
[data-nifc.opendata.arcgis.com](https://data-nifc.opendata.arcgis.com/).
National Interagency Fire Center, Wildland Fire Interagency Geospatial
Services (WFIGS); data from IRWIN (DOI Office of Wildland Fire, USFS, NPS,
FWS, BIA, BLM, NASF, USFA, NWCG).

- **Contents:** incident points for wildfires (WF), prescribed fires (RX)
  and complexes (CX) from IRWIN, 97 fields: `IncidentName`,
  `FireDiscoveryDateTime`, `ContainmentDateTime`, `ControlDateTime`,
  `FireOutDateTime`, `IncidentSize`, `PercentContained`,
  `FireCauseGeneral`/`Specific`, `TotalIncidentPersonnel`, `POOCounty`,
  landowner, protecting agency, `IrwinID`, `UniqueFireIdentifier`,
  `ModifiedOnDateTime_dt` and more. Perimeters have 119 fields in
  `_Current` and 120 in the all-years service (`poly_*` geometry fields
  such as `poly_MapMethod` and `poly_GISAcres`, plus `attr_*` incident
  fields).
- **Services** in NIFC's org (Oct 7 listing): `WFIGS_Incident_Locations`
  (all years), `_Current`, `_YearToDate`, `_Last24h`,
  `WFIGS_YTDLocs_CmplxInfo`; `WFIGS_Interagency_Perimeters` (all years:
  certified perimeters plus new ones since 2021), `_Current`,
  `_YearToDate`, `_Certified`; `WFIGS_Daily_Perimeters_Public`.
- **Coverage:** US. In the ring (re-queried Oct 7): 3,921 incident records,
  discovered 2008-07-22 to 2026-10-04, and 522 perimeters. The service is
  documented from 2014, when IRWIN began, so earlier rows are sparse legacy
  records. The largest ring wildfires since 2024, by `IncidentSize`:

  | Fire (IRWIN name) | County | Date | Acres |
  |---|---|---|---|
  | Paddock | Washington | 2024-08-06 | 187,185 |
  | Nellie | Boise | 2024-08-06 | 50,073 |
  | Range | Ada | 2025-07-31 | 27,126 |
  | Jump | Owyhee | 2024-08-05 | 25,721 |
  | Bulldog | Boise | 2024-08-05 | 11,423 |
  | Valley | Ada | 2024-10-04 | 9,905 |
  | MM65 I84 | Ada | 2025-07-19 | 8,898 |
  | RA 6 ADA CO CLAREMONT | Ada | 2026-07-06 | 6,628 (contained 2026-08-03; no out date yet) |

- **Endpoint:** `https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/{service}/FeatureServer/0/query`
  with the ring envelope; 2,000 records a page; JSON or GeoJSON; fits the
  shared ArcGIS reader. For lifecycles, poll the all-years services (or
  the `_YearToDate` views) with an absolute filter such as
  `ModifiedOnDateTime_dt > TIMESTAMP '<last seen>'`. NIFC asks clients not
  to query repeatedly with relative dates or `CURRENT_TIMESTAMP`. Treat
  `_Current` as a convenience view only.
- **License or terms:** disclaimer only (item `licenseInfo`): NIFC "shall
  not be held liable for improper or incorrect use of the data". No reuse
  restriction found. Credit NIFC/WFIGS and the IRWIN agencies named in
  `accessInformation`.
- **robots.txt:** `services3.arcgis.com` answers 403, so there are no
  rules: allowed (re-checked Oct 7). The hub `data-nifc.opendata.arcgis.com`
  has Crawl-delay 60 and disallows `/sites/`, `/admin/`, `/sessions/`,
  `/groups/`, `/people/` and `/workspace/`; we don't need it. A 5xx on a
  data query is a failed fetch to retry with backoff; only a 5xx or network
  error on robots.txt itself means "disallow for now".
- **Updates:** "Data are refreshed from IRWIN every 5 minutes"; perimeter
  changes "may take up to 15 minutes to display". `_Current` applies
  fall-off rules hourly: fires under 10 acres drop after 3 days without an
  update, 10–100 acres after 8 days, over 100 acres after 14 days.
- **Size:** KB to a few hundred KB per live ring query. A backfill of about
  4,000 points and 520 polygons is tens of MB.
- **Uses:** a live fire layer (points sized by acres, and perimeters, with
  containment read from the all-years or year-to-date record); fire
  lifecycles in `evt.event` (discovery, containment, control, out), with
  perimeter growth from versioning every change; Valley Feed items (new
  fire, growth, containment, fire near a state route); replay of fire
  growth, joined with 511 closures and road segments; history in the ring
  from 2014 (sparse rows back to 2008).
- **Personas:** fire and weather watcher; commuter; traffic researcher;
  hiker, backpacker, camper, hunter, angler, floater; aviation watcher;
  history buff.
- **Core pieces:** lifecycles contract (`evt.event`), versioned geometry
  history (proposed), shared ArcGIS reader, Valley Feed, full replay, layer
  system, areas (the regional ring).
- **Risks:** `_Current` holds only fires that have "not been declared
  contained, controlled, nor out", aren't certified and started after
  November of the previous year; fall-off rules then drop stale ones. So a
  fire leaving `_Current` has usually just been contained. Read state
  changes from the all-years or year-to-date service and close a lifecycle
  only on `FireOutDateTime`. Year-to-date drops last year's still-burning
  fires on Jan 1. Not every incident has a perimeter. Names are terse or
  prefixed. Cause fields give a class, never a person. ArcGIS Online
  returns occasional 5xx.
- **Verification:** confirmed the endpoints, field counts, license
  disclaimer, 5-minute refresh, fall-off thresholds, ring counts (same
  earliest and latest dates) and robots result. Corrected: (1) `_Current`
  also leaves out fires once they're contained, controlled or out, and
  fires started before December of the previous year, so containment can't
  be watched there; (2) the all-years incident service is documented from
  2014, not 2008; (3) the largest-fires list had missed Jump and Bulldog,
  and Claremont's IRWIN name is "RA 6 ADA CO CLAREMONT"; (4) the all-years
  perimeters have 120 fields; (5) an earlier "5xx means disallow" remark
  had applied the robots rule to data queries.
- **Evidence:** [service list](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services?f=json),
  [`_Current` incidents layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations_Current/FeatureServer/0?f=json),
  [`_Current` perimeters layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0?f=json),
  [all-years incidents query](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0/query)
  (ring statistics; largest fires since 2024),
  [all-years perimeters query](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters/FeatureServer/0/query)
  (ring count), ArcGIS items
  [4181a117](https://www.arcgis.com/sharing/rest/content/items/4181a117dc9e43db8598533e29972015?f=json) (license),
  [d1c32af3](https://www.arcgis.com/sharing/rest/content/items/d1c32af3212341869b3c810f1a215824?f=json),
  [b4402f78](https://www.arcgis.com/sharing/rest/content/items/b4402f7887ca4ea9a6189443f220ef28?f=json),
  [5e72b169](https://www.arcgis.com/sharing/rest/content/items/5e72b1699bf74eefb3f3aff6f4ba5511?f=json),
  [40581490](https://www.arcgis.com/sharing/rest/content/items/405814902c9e411cb4384c49d694e82b?f=json);
  robots.txt for [services3.arcgis.com](https://services3.arcgis.com/robots.txt) (403)
  and [the hub](https://data-nifc.opendata.arcgis.com/robots.txt).

### NIFC Interagency Fire Perimeter History

**Use** · effort S · confidence high · no key · verified: corrected.
[All_Years_View layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0).
Interagency Wildland Fire Perimeter History (IFPH), owned by the
WFMRDA_Authoritative account in NIFC's ArcGIS Online org; built from USFS,
BLM, BIA, FWS, NPS, AICC, CAL FIRE and WFIGS perimeters.

- **Contents:** consolidated historic agency perimeters, 19 fields
  (`INCIDENT`, `FIRE_YEAR_INT`, `GIS_ACRES`, `UNQE_FIRE_ID`, `IRWINID`,
  `DATE_CUR`, `MAP_METHOD`, `AGENCY`, `SOURCE`, `COMMENTS` and others).
  `All_Years_View` runs to the 2019 season. A separate view,
  `InterAgencyFirePerimeterHistory_2020s_Read_Only`, covers 2020–2024:
  WFIGS since mid-2020, with prescribed burns from WFIGS, NPS and CAL FIRE.
  Decade views exist too (e.g. `_1979_And_Prior_Read_Only`).
- **Coverage:** 2,157 perimeters intersect the ring, `FIRE_YEAR_INT`
  1908–2019 (statistics query, Oct 7). The 2020s view has 248 in the ring
  for 2020–2024, so there is no 2020 gap. Its 2021–2024 records overlap
  WFIGS: dedupe on `IRWINID` or `UNQE_FIRE_ID`.
- **Endpoint:** FeatureServer queries on
  `.../InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0` and
  `.../InterAgencyFirePerimeterHistory_2020s_Read_Only/FeatureServer/0`
  (ring envelope; 2,000 records a page). A one-off backfill, then a yearly
  refresh.
- **License or terms:** the item's `licenseInfo` differs from WFIGS's: the
  data are "intended for STRATEGIC USE ONLY" and "not legal documents", and
  the agencies aren't liable for misuse. No reuse restriction stated.
  Credit the contributing agencies and NIFC.
- **robots.txt:** 403, so no rules: allowed (re-checked Oct 7).
- **Updates:** yearly or less often. Layer `editingInfo`: `All_Years_View`
  last edited 2026-06-25; the 2020s view 2026-10-07.
- **Size:** about 2,400 polygons in the ring (2,157 plus 248); tens of MB.
- **Uses:** a fire-history map and year slider (1908–2024 from here, WFIGS
  after); burn-scar context for trails, wildlife winter range and a private
  hazard sheet; long-run counts of fires near the valley's
  wildland–urban interface (WUI) edge.
- **Personas:** history buff; hiker, backpacker, camper, hunter, angler,
  floater; wildlife; homeowner or land buyer (private).
- **Core pieces:** layer system, full replay (year slider), shared ArcGIS
  reader.
- **Risks:** old perimeters are hand-drawn and approximate, so show their
  accuracy (`MAP_METHOD`). Agency sources overlap, and the 2020s view
  overlaps WFIGS, so expect duplicates. Inclusion thresholds vary by
  agency. The "strategic use only" disclaimer should travel with any
  display.
- **Verification:** confirmed the 2,157 perimeters, 1908–2019, and the
  robots result. Corrected: (1) the license hadn't been checked, and it is
  this owner's "strategic use only" disclaimer, not WFIGS's; (2) the "2020
  gap" doesn't exist, because the 2020s view covers 2020–2024; (3) the
  publisher is the IFPH/WFMRDA account within NIFC's org.
- **Evidence:** [service list](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services?f=json),
  [All_Years_View layer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0?f=json),
  [All_Years_View query](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query)
  and [2020s view query](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_2020s_Read_Only/FeatureServer/0/query)
  (ring counts and years), ArcGIS items
  [e02b85c0](https://www.arcgis.com/sharing/rest/content/items/e02b85c0ea784ce7bd8add7ae3d293d0?f=json) (license) and
  [2ec06c73](https://www.arcgis.com/sharing/rest/content/items/2ec06c73fb6143c7bc92ee17c6ce0ee4?f=json).

### InciWeb

**Avoid** (link only) · confidence high · verified: confirmed.
[inciweb.wildfire.gov](https://inciweb.wildfire.gov/). USDA Forest
Service, for the interagency community.

- **Contents:** narrative incident pages, news releases, closure notices,
  maps and photos, plus RSS feeds of incident summaries. Large incidents
  nationwide, updated as incident teams post.
- **Access:** web pages and RSS on `inciweb.wildfire.gov` and
  `inciweb.fs2c.usda.gov`. Federal; the terms weren't examined further
  because of robots.txt.
- **robots.txt:** both hosts answer `User-agent: *` / `Disallow: /`, so
  every path, RSS included, is disallowed (re-checked Oct 7).
- **Uses:** a plain link from our fire card to the incident's InciWeb page,
  never fetched. WFIGS has no field giving the InciWeb page ID, so the link
  may have to be a search link ⚠️.
- **Personas:** fire and weather watcher.
- **Risks:** any scheduled fetch, RSS included, would break robots.txt.
  WFIGS already carries the structured facts.
- **Verification:** both robots files re-fetched; the full disallow was
  confirmed with the project parser.
- **Evidence:** robots.txt for [inciweb.wildfire.gov](https://inciweb.wildfire.gov/robots.txt)
  and [inciweb.fs2c.usda.gov](https://inciweb.fs2c.usda.gov/robots.txt).

### MTBS burned areas and burn severity

**Use** · effort S · confidence medium · no key · verified: confirmed.
[Burn Severity Portal](https://burnseverity.cr.usgs.gov/direct-download).
USGS EROS and USDA Forest Service (GTAC).

- **Contents:** perimeters of fires over 1,000 acres in the West (over 500
  in the East), 1984–2024, with event ID, name, ignition date and acres;
  per-fire 30 m Landsat burn severity (dNBR and classes); annual severity
  mosaics.
- **Coverage:** CONUS, Alaska, Hawaii and Puerto Rico, 1984–2024; covers
  the ring's large fires.
- **Access:** a one-off download from the Burn Severity Portal (the MTBS
  product at `/direct-download?product=MTBS`). `mtbs.gov/direct-download`
  now says the tool "has been consolidated" into the Burn Severity Site.
  Dataset DOI 10.5066/P9IED7RZ; files on `edcintl.cr.usgs.gov`. Kind
  `manual`.
- **License or terms:** a federal USGS/USFS product. data.gov lists it as
  public with no restrictions stated; no specific license line shown ⚠️.
- **robots.txt:** `www.mtbs.gov` and `burnseverity.cr.usgs.gov` (the same
  Drupal file) disallow `/core/`, `/profiles/`, `/README.txt`,
  `/web.config` and similar; `/direct-download` is allowed.
  `edcintl.cr.usgs.gov` answers 404 (no rules).
- **Updates:** yearly, a year or more behind (data.gov record updated
  2025-01-29).
- **Size:** national perimeter shapefile tens to hundreds of MB ⚠️;
  severity rasters for ring fires a few hundred MB ⚠️. The download hub is
  a navigation page, so file sizes weren't seen.
- **Uses:** severity colouring of burn scars; recovery over time with the
  NAIP near-infrared year slider.
- **Personas:** history buff; hiker, backpacker, camper, hunter, angler,
  floater; wildlife; homeowner or land buyer (private).
- **Core pieces:** layer system, full replay (year slider), manual source
  kind.
- **Risks:** small fires are missing, so present it as large fires only.
  It isn't needed for a 2020 perimeter gap: NIFC's 2020s view covers 2020.
- **Verification:** the move to the Burn Severity Portal, the 1984–2024
  range, the size thresholds, the DOI and robots confirmed. The "fill the
  2020 gap" use was dropped.
- **Evidence:** [mtbs.gov download page](https://www.mtbs.gov/direct-download),
  [Burn Severity Portal](https://burnseverity.cr.usgs.gov/direct-download),
  [data.gov record](https://catalog.data.gov/dataset/monitoring-trends-in-burn-severity-burned-areas-boundaries-for-1984-2024),
  robots.txt for [mtbs.gov](https://www.mtbs.gov/robots.txt),
  [burnseverity.cr.usgs.gov](https://burnseverity.cr.usgs.gov/robots.txt)
  and [edcintl.cr.usgs.gov](https://edcintl.cr.usgs.gov/robots.txt) (404).

### FPA FOD wildfire occurrence, 7th edition

**Use** · effort S · confidence high · no key · verified: confirmed.
[RDS-2013-0009.7](https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.7).
USDA Forest Service Research Data Archive (Karen C. Short).

- **Contents:** "Spatial wildfire occurrence data for the United States":
  2.66 million geo-referenced wildfire records (209 million acres) from
  federal, state and local reporting systems, with discovery date, final
  size, cause, location, reporting agency and links to large-fire
  perimeters. Product name `FPA_FOD_20260615`.
- **Coverage:** US, 1992–2024 (7th edition, published 2026). The ring is a
  small subset (thousands of records).
- **Access:** a one-off download, no login: ACCDB 204.66 MB, GDB 157.8 MB,
  GPKG 227.14 MB, SQLite 219.61 MB. The SQLite file's attribute and
  latitude/longitude columns read with the standard library. Kind `manual`.
- **License or terms:** "can be used without additional permissions or
  fees" (the archive's use statement). Cite the archive entry.
- **robots.txt:** `www.fs.usda.gov` restricts only Drupal asset folders;
  `/rds/archive/catalog/...` and `/rds/archive/products/...` are allowed by
  the project parser.
- **Updates:** a new edition every few years.
- **Uses:** ignitions by cause and season around the valley; ignitions
  along highways (roadside starts) per corridor, a road-safety and traffic
  tie; a history heat map.
- **Personas:** history buff; traffic researcher; fire and weather watcher.
- **Core pieces:** layer system, search (by fire name), manual source kind.
- **Risks:** locations can be as coarse as a PLSS section (about one square
  mile) ⚠️ (from the dataset's abstract, not re-read), so show
  section-level dots or aggregates.
- **Verification:** the edition, years, record count, file sizes, use
  statement and no-login access confirmed on the archive page.
- **Evidence:** [archive page](https://www.fs.usda.gov/rds/archive/catalog/RDS-2013-0009.7),
  [robots.txt](https://www.fs.usda.gov/robots.txt).

### Wildfire Risk to Communities, 2nd edition

**Use** · effort M · confidence high · no key · verified: confirmed.
[RDS-2020-0016-2](https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2).
USDA Forest Service (Scott, Dillon et al. 2024).

- **Contents:** 30 m rasters: burn probability (BP), conditional flame
  length (CFL), risk to potential structures (RPS), conditional RPS,
  wildfire hazard potential (WHP), exposure type, FLEP4 and FLEP8. Burn
  probability reflects end-2020 conditions; the intensity layers end-2022.
- **Coverage:** all US lands (CONUS, Alaska, Hawaii); state packages plus
  CONUS composites (up to 33.7 GB).
- **Access:** a one-off download from the Research Data Archive. The Idaho
  package is `RDS-2020-0016-2_Idaho.zip`, 6.56 GB (from the page summary
  ⚠️). wildfirerisk.org also offers downloads (Crawl-delay 10). Kind
  `manual`.
- **License or terms:** "can be used without additional permissions or
  fees". Cite Scott et al. 2024, doi:10.2737/RDS-2020-0016-2. The page
  notes modelling uncertainty.
- **robots.txt:** `www.fs.usda.gov` allows the catalog and product paths.
  wildfirerisk.org has Crawl-delay 10 and disallows only
  `/wp-content/uploads/wpforms/`, so `/download/` is allowed.
- **Updates:** static; a new edition every few years.
- **Size:** the Idaho package about 6.6 GB; cropped to the ring and tiled,
  a few hundred MB.
- **Uses:** a hazard sheet for the owner's own address (private); a
  context layer where the WUI meets high burn probability, next to
  evacuation egress roads; risk along trails and campgrounds.
- **Personas:** homeowner or land buyer (private); hiker, backpacker,
  camper, hunter, angler, floater; fire and weather watcher; neighbor and
  civic.
- **Core pieces:** layer system (raster tiles), areas, manual source kind.
- **Risks:** modelled landscape risk, not a statement about any one
  property; never present it per parcel for other people's homes. The
  download size needs the owner's approval.
- **Verification:** the layers, resolution, citation, use statement and
  robots confirmed. Added the Idaho file size (⚠️, from the page summary)
  and the condition years.
- **Evidence:** [archive page](https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0016-2),
  robots.txt for [wildfirerisk.org](https://wildfirerisk.org/robots.txt)
  and [www.fs.usda.gov](https://www.fs.usda.gov/robots.txt).

---

## Satellite fire and smoke detection

### NASA FIRMS active fire detections

**Use** · effort S · confidence high · no key for the files · verified:
corrected. [firms.modaps.eosdis.nasa.gov](https://firms.modaps.eosdis.nasa.gov/).
NASA LANCE / ESDIS (FIRMS); the US/Canada view is run with the USFS.

- **Contents:** one point per detection: latitude and longitude, brightness
  temperatures, fire radiative power (FRP, MW), confidence, scan and track
  footprint, acquisition date and time, satellite, day or night, type.
  Sensors: VIIRS 375 m (S-NPP, NOAA-20, NOAA-21), MODIS 1 km, Landsat 30 m
  (OLI, "most of North America"). Latency per the FAQ: URT under 1 minute
  from direct readout (select US/Canada areas), RT within 30 minutes, NRT
  1–3 hours. Standard (science-quality) products follow with "a 2-3 month
  lag". Per-sensor start dates, including Landsat's (2022-06-20), weren't
  re-verified ⚠️.
- **Coverage:** global; the contiguous-US-and-Hawaii files cover the ring.
- **Endpoint:** keyless region files, confirmed by HEAD on Oct 7:
  [`J1_VIIRS_C2_USA_contiguous_and_Hawaii_24h.csv`](https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_USA_contiguous_and_Hawaii_24h.csv)
  (200, 148,953 bytes) and the [`_7d.csv`](https://firms.modaps.eosdis.nasa.gov/data/active_fire/noaa-20-viirs-c2/csv/J1_VIIRS_C2_USA_contiguous_and_Hawaii_7d.csv)
  (754,842 bytes). Other sensors' paths are assumed to follow the same
  pattern ⚠️; the listing page is JavaScript-rendered, so they weren't
  confirmed. The area API takes a MAP_KEY:
  `/api/area/csv/[MAP_KEY]/[SOURCE]/[w,s,e,n]/[1..5]/[YYYY-MM-DD]`, with
  SOURCE one of `LANDSAT_NRT`, `MODIS_NRT`, `MODIS_SP`,
  `VIIRS_NOAA20_NRT`, `VIIRS_NOAA20_SP`, `VIIRS_NOAA21_NRT`,
  `VIIRS_SNPP_NRT`, `VIIRS_SNPP_SP`. The archive: the `/download` tool, or
  the `nrt3.modaps.eosdis.nasa.gov` archive folder, which needs an
  Earthdata Login (FAQ).
- **Key or account:** none for the CSVs. A MAP_KEY is free ("sign up for
  free MAP_KEY using your email"), limited to "5000 transactions /
  10-minute interval", with larger requests counting as several. It's an
  owner action, needed for ring-only and back-dated pulls.
- **License or terms:** NASA open data ("NASA promotes full and open
  sharing of data", FAQ). Credit "NASA FIRMS", and the LANCE/ESDIS
  acknowledgment in publications.
- **robots.txt:** allows `/`, `/api/`, `/active_fire/` and others;
  disallows `/admin/`, `/*.json$`, `/private/`, `/temp/`, `/cache/`,
  `/flood/*`, `/dev/`, `/_test/*`, `/dist/` and query strings with `sort=`,
  `filter=` or `page=`; Crawl-delay 1. The CSV and area-API paths are
  allowed by the project parser (re-checked Oct 7).
- **Updates:** the 24 h, 48 h and 7 d SHP, KML and CSV files "update every
  60 minutes"; the fire maps every 5 minutes. Hourly rewrites were
  confirmed by last-modified changing between two HEAD requests.
- **Size:** the CONUS 24 h CSV is about 150 KB per sensor (NOAA-20), the
  7 d about 755 KB. Archiving every hourly 24 h file raw for the three VIIRS
  sensors plus MODIS would be about 10–15 MB a day, so keep ring rows only.
- **Uses:** a hotspot layer drawn at the sensor footprint (375 m VIIRS
  pixels); fire progression in replay, overpass by overpass (past fires
  need the area API with a date, or the download tool); an early sign of
  new fires before an IRWIN record exists; field-burn seasonality,
  aggregated, for the farmer view; FRP time series per fire.
- **Personas:** fire and weather watcher; commuter; farmer; history buff;
  sky watcher and photographer.
- **Core pieces:** a readings or detections contract (point observations
  in time), full replay, layer system, 3D engine (glow on terrain).
- **Risks:** static industrial heat sources and field burns show up as
  hotspots; filter or label them. A hotspot on a house is a structure fire
  at a private address: draw pixels, not pins, and never build house-fire
  alerts. The CSVs are rewritten hourly even when the rows don't change, so
  dedupe by content.
- **Verification:** confirmed the keyless CSVs, robots, the MAP_KEY terms
  and limit, the license wording and hourly updates. Corrected: the
  standard-product lag is 2–3 months (FAQ), not about 5; the archive folder
  needs an Earthdata Login; the raw archive size had been underestimated
  for several sensors.
- **Evidence:** [robots.txt](https://firms.modaps.eosdis.nasa.gov/robots.txt),
  [area API](https://firms.modaps.eosdis.nasa.gov/api/area/),
  [MAP_KEY page](https://firms.modaps.eosdis.nasa.gov/api/map_key/),
  [FAQ](https://www.earthdata.nasa.gov/data/tools/firms/faq),
  [active-fire listing](https://firms.modaps.eosdis.nasa.gov/active_fire/)
  (JavaScript-rendered; no links readable), and the two CSV HEADs above.

### NOAA Hazard Mapping System (HMS) fire points and smoke polygons

**Use** · effort S · confidence high · no key · verified: corrected.
[OSPO product page](https://www.ospo.noaa.gov/products/land/hms.html).
NOAA NESDIS Office of Satellite and Product Operations.

- **Contents:** analyst-reviewed fire points (coordinates, time, satellite,
  method, ecosystem, FRP) and smoke polygons classified "light, medium,
  heavy", with satellite and start and end times.
- **Coverage:** "North America, Hawaii, and the Caribbean", focused on
  CONUS. The smoke archive has yearly folders from 2005; fire points are
  archived too.
- **Endpoint:** files at
  `https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/{Fire_Points|Smoke_Polygons}/{Shapefile|KML|Text}/YYYY/MM/`,
  e.g. `Smoke_Polygons/KML/2026/10/hms_smoke20261006.kml`. The OSPO page
  links latest-analysis KMLs (`latest_fires_final.kml`,
  `latest_smoke_final.kml`), and WFS/ArcGIS services exist. KML and text
  parse with the standard library.
- **License or terms:** NOAA, public domain. Disclaimer: locations "may be
  slightly offset"; don't make tactical decisions without corroboration.
- **robots.txt:** `satepsanone.nesdis.noaa.gov` answers 404 (no rules);
  `www.ospo.noaa.gov` has a wildcard group with no Disallow lines. Both
  allowed (re-checked Oct 7).
- **Updates:** fire detections are "typically published online by 8:00 AM
  Eastern" and updated through the day. The first smoke analysis comes
  between 11:00 AM and 12:00 PM ET, the second generally 7–8 PM ET. The
  archived daily KML is finalised the next morning (the Oct 1–5 files were
  modified about 10:00 the following day).
- **Size:** a day's national smoke KML is 62–454 KB (Oct 1–6, 2026
  listing). Clipped to the ring, KB a day; a 2005–2026 ring backfill is
  small.
- **Uses:** a smoke-over-the-valley layer by density; smoke-day
  classification for traffic research (with AQS); a smoke-sunset
  predictor; replay, with smoke polygons as lifecycles with start and end
  times.
- **Personas:** fire and weather watcher; traffic researcher; sky watcher
  and photographer; gardener; cyclist and pedestrian.
- **Core pieces:** lifecycles contract, full replay, layer system.
- **Risks:** smoke polygons describe smoke anywhere in the column, not at
  the ground, so pair them with AirNow and HRRR near-surface smoke.
  Analyses are daytime only. The same-day file grows through the day, so
  version it and treat the next-morning file as final.
- **Verification:** confirmed the products, schedule, paths, disclaimer,
  robots and the archive from 2005. Corrected: the daily national smoke
  KML is 60–450 KB, not a few MB, and archived files are finalised the next
  morning.
- **Evidence:** [OSPO page](https://www.ospo.noaa.gov/products/land/hms.html),
  [OSPO robots.txt](https://www.ospo.noaa.gov/robots.txt),
  [smoke KML folder for Oct 2026](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/KML/2026/10/),
  [smoke shapefile archive](https://satepsanone.nesdis.noaa.gov/pub/FIRE/web/HMS/Smoke_Polygons/Shapefile/),
  [satepsanone robots.txt](https://satepsanone.nesdis.noaa.gov/robots.txt) (404).

### GOES-18 (GOES-West) fire, smoke, aerosol and lightning products

**Use** · effort M · confidence high · no key · verified: corrected.
[NOAA GOES on AWS](https://registry.opendata.aws/noaa-goes/). NOAA NESDIS
through the NOAA Open Data Dissemination (NODD) program.

- **Contents:** ABI Level 2 fire detection: `ABI-L2-FDCC` (the CONUS
  sector every 5 minutes; for GOES-West this is the PACUS sector, which
  covers Idaho ⚠️), `FDCF` (full disk) and `FDCM` (mesoscale), with fire
  mask, temperature, area and FRP at about 2 km. Also `ABI-L2-ADPC/ADPF/ADPM`
  (smoke and dust masks), `ABI-L2-AODC/AODF` (aerosol optical depth; no
  mesoscale AOD), cloud products (ACHA, ACM and others), ABI flood products
  and `GLM-L2-LCFA` (lightning).
- **Coverage:** GOES-18 is GOES-West and GOES-19 GOES-East (NESDIS page).
  The exact switch dates weren't confirmed: the catalog's 2023-01-10 and
  2025-04-04 differ from the commonly cited Jan 4, 2023 and Apr 7, 2025 ⚠️.
  The `FDCC` archive starts 2022 day 131 (May 11, 2022); data before the
  GOES-West switch are from checkout. For 2018–2022 western fires, GOES-17
  (`noaa-goes17`) was the West satellite.
- **Endpoint:** anonymous S3 over HTTPS: list
  `https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-FDCC/YYYY/DDD/HH/`,
  then GET the NetCDF4 files (e.g. `OR_ABI-L2-FDCC-M6_G18_s2026279120118...nc`).
  SNS topic `arn:aws:sns:us-east-1:123901341784:NewGOES18Object`.
- **License or terms:** NODD data "are open to the public and can be used
  as desired". Attribution requested; don't present modified data as
  original. Program terms from nodd@noaa.gov.
- **robots.txt:** `noaa-goes18.s3.amazonaws.com` answers 404 (no rules):
  allowed (re-checked Oct 7).
- **Updates:** `FDCC` every 5 minutes (12 files in hour 12 UTC of day 279
  confirmed), full disk every 10 minutes, mesoscale every minute when a
  sector is placed. GLM LCFA files every 20 s ⚠️.
- **Size:** `FDCC` files are about 278 KB (Oct 6 sample), 288 a day, so
  about 80 MB a day of transfer; keep only ring fire pixels (bytes to KB a
  day). GLM's 20-second files are about 4,320 a day, so filter on ingest.
- **Uses:** 5-minute FRP curves per fire between VIIRS overpasses; fast
  detection of new starts; a smoke-mask animation in replay; a
  lightning-to-ignition watch (GLM; total lightning, see the risks); AOD as
  a sun-dimming input for the gardener's sun hours (daytime and cloud-free
  only).
- **Personas:** fire and weather watcher; sky watcher and photographer;
  gardener; aviation watcher.
- **Core pieces:** a fields contract for gridded time series (proposed),
  full replay, 3D engine.
- **Risks:** NetCDF4/HDF5 decoding needs libraries or binaries outside the
  standard library (the owner decides). Using only fire-mask codes 10, 11,
  30 and 31 (processed and saturated) is conservative and will miss many
  real fires flagged as high-probability or cloud-contaminated (codes from
  a secondary source ⚠️). Pixels are about 2 km, so draw them as squares.
  GLM reports total lightning (in-cloud and cloud-to-ground) at roughly
  8–14 km, not ground strikes.
- **Verification:** confirmed the license, bucket layout, 5-minute cadence,
  robots and SNS topic. Corrected: files are about 278 KB (so about 80 MB a
  day of transfer); the archive starts May 2022, before the GOES-West
  switch; GLM is total lightning, not strikes. Unverified: the exact
  GOES-West and GOES-East switch dates and the PACUS sector naming ⚠️.
- **Evidence:** [AWS registry](https://registry.opendata.aws/noaa-goes/),
  [bucket top-level prefixes](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/),
  [FDCC listing for 2026 day 279, hour 12](https://noaa-goes18.s3.amazonaws.com/?list-type=2&prefix=ABI-L2-FDCC/2026/279/12/)
  (file sizes, cadence),
  [FDCC listing for 2022](https://noaa-goes18.s3.amazonaws.com/?list-type=2&delimiter=/&prefix=ABI-L2-FDCC/2022/)
  (archive start), [robots.txt](https://noaa-goes18.s3.amazonaws.com/robots.txt) (404),
  [NESDIS satellites page](https://www.nesdis.noaa.gov/our-satellites/currently-flying/geostationary-satellites).

### NOAA Next Generation Fire System (NGFS)

**Avoid** (link only) · confidence medium · verified: corrected.
[fire.data.nesdis.noaa.gov](https://fire.data.nesdis.noaa.gov/) (the
Wildland Fire Data Portal). NOAA NESDIS.

- **Contents:** GOES-based fire detection and tracking that "quickly
  analyzes large volumes of satellite data" for active-fire heat
  signatures, with per-incident time series in the portal. CONUS (GOES-East
  and GOES-West), near real time.
- **Access:** a web portal only, as far as checked; the NESDIS page gives
  no API, file, NODD or account details. Key or account unknown. No terms
  on the NESDIS overview page.
- **robots.txt:** `User-agent: *` / `Disallow: /`: everything disallowed
  (re-checked Oct 7).
- **Uses:** watch for an NODD or file distribution; until then, a link
  out only.
- **Personas:** fire and weather watcher.
- **Risks:** robots.txt forbids automated access. Its status is unclear:
  the NESDIS page presents it as working and says nothing about it being
  experimental or about an operational date.
- **Verification:** the robots disallow confirmed. The research pass's
  claim that NGFS is "experimental" and "expected to become operational
  later in 2026" isn't supported by the NESDIS page and stays unverified.
  Verdict unchanged.
- **Evidence:** [NESDIS portal page](https://www.nesdis.noaa.gov/data-products-research-services/wildland-fire-data-portal),
  [robots.txt](https://fire.data.nesdis.noaa.gov/robots.txt).

---

## Fire restrictions, closures and danger

### Idaho Department of Lands fire restriction areas and zones

**Use** · effort S · confidence high · no key · verified: corrected.
[Fire restrictions finder](https://www.idl.idaho.gov/fire-restrictions-finder/).
Idaho Department of Lands (IDL), for the interagency Idaho Fire
Restrictions Plan.

- **Contents:** layer 0, Fire Restriction Areas; layer 1, Fire Restriction
  Zones, with `Name`, `Stage`, `Rstrct_Are`, `DateEnacted`,
  `DateRescinded`, `UpcomingStage`, `Zones`, `last_edited_user`,
  `last_edited_date` and `GlobalID`. The service keeps only the current
  state: `DateEnacted` is when the present stage took effect (including a
  change back to "None"), and `DateRescinded` was empty in every ring zone.
- **Coverage:** statewide. Zones in the ring on Oct 7: Treasure Valley,
  Owyhee and West Central (Boise Fire Restriction Area); Weiser River and
  Long Valley/Meadows Valley (Payette area); Three Creek (South Idaho
  area). All showed stage "None". Treasure Valley's `DateEnacted` is
  2026-09-03 14:01 UTC, matching BLM Boise District's Sept 3 rescission;
  Three Creek's is 2026-09-11.
- **Endpoint:** `https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer/{0,1}/query`
  (ring envelope, JSON).
- **License or terms:** none stated (no service description or copyright
  text). A state agency's public notice; under the owner's rule for data
  without a license, use it with credit to IDL and a courtesy note.
- **robots.txt:** `gis1.idl.idaho.gov/robots.txt` redirects to an HTML
  error page on `error.idaho.gov`, which the project parser treats as no
  rules (allowed); `gis.idwr.idaho.gov` does the same. `www.idl.idaho.gov`
  has an empty Disallow (allowed).
- **Updates:** when agencies change stage (`last_edited_date` is
  timestamped); poll hourly.
- **Size:** tiny: tens of polygons, with versions only on change.
- **Uses:** restriction-stage lifecycles per zone, built from our own
  versions (the service keeps no history); a "can I have a campfire here?"
  tool; Valley Feed posts on stage changes; replay of the rules in force on
  a given day (only from our first poll, or by hand from BLM's order PDFs).
- **Personas:** hiker, backpacker, camper, hunter, angler, floater; fire
  and weather watcher; gardener; farmer.
- **Core pieces:** lifecycles contract, Valley Feed, full replay, shared
  ArcGIS reader.
- **Risks:** use IDL's service, not NIFC's stale copy
  `Idaho_Fire_Restrictions_v2` (still listed in NIFC's org). History before
  our first poll isn't in the service: the 2026 Stage 1 start date for
  Treasure Valley couldn't be verified (BLM's page now shows only the
  Sept 3 rescission). The legal text is in signed order PDFs, so link to
  them. "Restrictions apply on all lands in a zone" wasn't re-checked.
- **Verification:** the layers, fields, ring zones, stages and dates
  confirmed. Corrected: `DateEnacted` and `DateRescinded` aren't the start
  and end of a restriction (the current "None" stage has `DateEnacted`
  2026-09-03 and no `DateRescinded`), so lifecycles must come from our own
  versions; the robots answer is a redirect to an error page, not a plain
  HTML page. The "Stage 1 on Aug 7" in the ideas is unverified.
- **Evidence:** [MapServer](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer?f=json),
  [zones layer](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer/1?f=json),
  [zones query](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer/1/query)
  (zones in the ring), robots.txt for
  [gis1.idl.idaho.gov](https://gis1.idl.idaho.gov/robots.txt) (redirects to
  error.idaho.gov) and [www.idl.idaho.gov](https://www.idl.idaho.gov/robots.txt),
  [BLM Idaho fire restrictions](https://www.blm.gov/programs/fire/regional-info/idaho/fire-restrictions).

### USFS Intermountain Region forest orders

**Use** · effort S · confidence high · no key · verified: confirmed.
[R04_Alerts_And_Closures_01 MapServer](https://apps.fs.usda.gov/fsgisx02/rest/services/r04/R04_Alerts_And_Closures_01/MapServer).
USDA Forest Service, Region 4 (Intermountain), Information Management GIS.

- **Contents:** layer 0, ForestOrder polygons, with line or point
  prohibitions drawn as buffers. Fields: `forestname`, `unitid`,
  `ordername`, `ordernum`, `ordertype`, `description`, `exemption`, `cfr`,
  `temporaltype`, `signeddate`, `startdate`, `enddate`, `rescinddate`,
  `approvaltype`, `hyperlink`, `acres`, `rev_date`, `accuracy`, `pub_date`,
  `statement`. Boise National Forest orders on Oct 7 included:

  | Order | Type | In force |
  |---|---|---|
  | Claremont Fire Area, Road, and Trail Closure | Fire closure, Stage 3 | 2026-07-08 to 2026-12-31 |
  | Crooked Fire Area, Road, and Trail Closure | Fire closure, Stage 3 | 2026-09-19 to 2026-12-31 |
  | Deer Point Area, Road, and Trail Closure | Safety | 2026-08-17 to 2026-11-30 |
  | Grimes Creek Closure | Safety | 2026-03-26 to 2027-03-26 |
  | Designated Camping Order | | 2025-06-12 to 2030-06-12 |

- **Coverage:** National Forest System lands in Region 4 (the Boise,
  Payette and Sawtooth National Forests in and near the ring).
- **Endpoint:** MapServer layer 0 query (JSON) with the ring envelope.
- **License or terms:** federal (USFS), public. The copyright text credits
  "USDA Forest Service Intermountain Region - Information Management GIS".
  The layer may not show every prohibition, so link to the order.
- **robots.txt:** `apps.fs.usda.gov` answers 403, so no rules: allowed
  (re-checked Oct 7).
- **Updates:** as orders are signed; poll a few times a day in fire season.
- **Size:** tens of polygons, KB.
- **Uses:** closure lifecycles with start, end and rescind dates; fire
  closures tied to WFIGS incidents by name and overlap; the "can I go
  there" tool for hikers and hunters; closed forest roads in the `roads`
  plugin.
- **Personas:** hiker, backpacker, camper, hunter, angler, floater; fire
  and weather watcher; commuter.
- **Core pieces:** lifecycles contract, Valley Feed, full replay, shared
  ArcGIS reader.
- **Risks:** incomplete by its own statement. One order can be split over
  several polygons (duplicate `ordername` rows), so group by `ordernum`.
  BLM's closures layer (`BLM_Fire_Closures_view`, still in NIFC's org
  listing) wasn't re-checked.
- **Verification:** the fields, examples (Claremont, Grimes Creek) and
  robots confirmed. Added the Crooked and Deer Point closures, multi-polygon
  orders and the copyright text.
- **Evidence:** [MapServer](https://apps.fs.usda.gov/fsgisx02/rest/services/r04/R04_Alerts_And_Closures_01/MapServer?f=json),
  [layer 0](https://apps.fs.usda.gov/fsgisx02/rest/services/r04/R04_Alerts_And_Closures_01/MapServer/0?f=json),
  [layer 0 query](https://apps.fs.usda.gov/fsgisx02/rest/services/r04/R04_Alerts_And_Closures_01/MapServer/0/query)
  (Boise NF in the ring), [robots.txt](https://apps.fs.usda.gov/robots.txt) (403).

### FEMS fire danger (NFDRS) and the RAWS archive

**Needs owner action** · effort M · confidence medium · account needed ·
verified: confirmed. [FEMS API page](https://www.wildfire.gov/page/fems-api).
USDA Forest Service / interagency (wildfire.gov); the Fire Environment
Mapping System succeeds WIMS.

- **Contents:** NFDRS station outputs (e.g. burning index and energy
  release component, ERC; queries such as `NfdrsObs`), RAWS observations
  and related climatology through a read-only GraphQL API ⚠️ (field list
  partly seen in the user guide).
- **Coverage:** RAWS stations nationwide, including the Boise District and
  the Boise National Forest ⚠️.
- **Endpoint:** `POST https://fems.fs2c.usda.gov/api/ext-climatology/graphql`
  with Basic authorization: the FEMS user name, and as password an API key
  generated in FEMS.
- **Key or account:** the user guide (Mar 2026) says "Only users with a
  FEMS API or FEMS Admin role" can use it, so it needs an account and a
  role: an owner action.
- **License or terms:** federal; the user guide's terms weren't seen.
- **robots.txt:** `fems.fs2c.usda.gov` is `User-agent: *` / `Disallow:`
  (everything allowed); `www.wildfire.gov` disallows only Drupal asset
  paths (re-checked Oct 7).
- **Updates:** hourly (RAWS), daily (NFDRS). Small per station.
- **Uses:** the fire-danger level (Low to Extreme) per area, as on roadside
  signs; the ERC trend through the fire season; the lightning-to-ignition
  watch with dry fuels.
- **Personas:** fire and weather watcher; hiker, backpacker, camper,
  hunter, angler, floater; farmer.
- **Core pieces:** readings contract.
- **Risks:** the account and role. RAWS observations overlap the weather
  theme.
- **Verification:** the role requirement, Basic authorization with a
  generated key, the endpoint and robots confirmed from the user guide's
  text.
- **Evidence:** [FEMS API page](https://www.wildfire.gov/page/fems-api),
  [read-only API user guide](https://wildfireweb-prod-media-bucket.s3.us-gov-west-1.amazonaws.com/s3fs-public/2026-03/FEMS_Read_Only_API_User_Guide-20206-0326.pdf) (PDF),
  robots.txt for [fems.fs2c.usda.gov](https://fems.fs2c.usda.gov/robots.txt)
  and [www.wildfire.gov](https://www.wildfire.gov/robots.txt).

---

## Smoke and air quality

### AirNow file products and API

**Use** · effort S · confidence high · no key for the files · verified:
confirmed. [AirNow API docs](https://docs.airnowapi.org/). US EPA AirNow
program, with data from state, local and tribal agencies (Idaho DEQ for the
valley).

- **Contents:** `HourlyAQObs_yyyymmddhh.dat` (fact sheet, Mar 2023): site
  AQSID, name, status, EPA region, latitude and longitude, elevation, GMT
  offset, data source, reporting areas, NowCast AQI for ozone, PM10 and
  PM2.5, hourly AQI for NO2, measured flags, and raw hourly concentrations
  for ozone, PM2.5, PM10, NO2, CO and SO2. `reportingarea.dat`: current
  observations and forecasts per reporting area. The API (key) adds
  observations and forecasts by latitude/longitude, ZIP or bounding box.
- **Coverage:** US, Canada and parts of Mexico; hourly files from May 28,
  2019. Valley sites come from Idaho DEQ.
- **Endpoint:** keyless files under
  `https://files.airnowtech.org/?prefix=airnow/YYYY/YYYYMMDD/` and
  `/airnow/today/`. `HourlyAQObs` is updated once an hour at about :35, and
  every file from the preceding 72 hours is re-updated hourly.
  `reportingarea.dat` "is updated twice per hour at :55 and :25". The API
  needs an account and key, and the FAQ says "please do NOT attempt to use
  the web services" to populate databases: use the files.
- **License or terms:** the AirNow Data Exchange Guidelines (Aug 2025).
  Data are preliminary, and displays and products "must indicate that these
  data are preliminary". Data, forecasts and advisories "should not be
  altered in any way". Credit the agencies first, then AirNow. Show the
  data with the AQI RGB colours. Products relying on the data "must be made
  known" to the agencies and AirNow. The data aren't to be used to
  "ascertain trends, act as guidance" or support public decision-making;
  use AQS for that. The form goes back to dmc@airnowtech.org.
- **robots.txt:** `files.airnowtech.org` answers 404, `www.airnowapi.org`
  403, and `docs.airnowapi.org` returns an HTML page: no rules on any of
  them, so allowed (re-checked Oct 7).
- **Updates:** hourly (`HourlyAQObs`, revised for 72 hours); twice an hour
  (`reportingarea.dat`).
- **Size:** `reportingarea.dat` is about 1.7 MB a fetch (about 80 MB a day
  if archived raw every half hour); `HourlyAQObs` about 1 MB an hour
  nationally ⚠️. Keep ring rows only (KB a day).
- **Uses:** live AQI readings per site on a time-series card, labelled
  preliminary; DEQ's daily AQI forecast for Boise, shown unaltered (the
  robots-allowed route to DEQ's forecasts); an ordinance-threshold marker
  for burning, only if the owner accepts the "act as guidance" wording
  (Ada County's AQI-60 rule itself is unverified ⚠️); a ride window and
  garden calendar (see the risks).
- **Personas:** fire and weather watcher; cyclist and pedestrian; gardener;
  commuter; neighbor and civic.
- **Core pieces:** readings contract, time-series card, Valley Feed, full
  replay.
- **Risks:** the guidelines bar using AirNow data to "act as guidance", so
  derived recommendations (a "best ride window", burn thresholds) need the
  owner's judgement and should rest on DEQ's forecasts shown as issued.
  The AQI colours are required, so meet our "never red/green alone" rule by
  adding the category word and number, not by changing colours. Trend
  analyses must use AQS. Fetching only the current hour misses the 72-hour
  revisions: re-fetch a few lagged hours (e.g. t−24 h and t−72 h). Owner
  actions: return the guidelines form and tell Idaho DEQ about the use.
- **Verification:** the guidelines (Aug 2025), fact sheet, file locations,
  update times, 72-hour revisions, the May 28, 2019 start and robots all
  confirmed. Added the "act as guidance" clause, which affects the
  ride-window and burn-threshold ideas, and the mandated AQI colours. The
  Oct 7 Boise reading wasn't re-fetched.
- **Evidence:** [FAQ](https://docs.airnowapi.org/faq),
  [Data Use Guidelines](https://docs.airnowapi.org/docs/DataUseGuidelines.pdf) (PDF),
  [HourlyAQObs fact sheet](https://docs.airnowapi.org/docs/HourlyAQObsFactSheet.pdf) (PDF),
  robots.txt for [files.airnowtech.org](https://files.airnowtech.org/robots.txt) (404)
  and [www.airnowapi.org](https://www.airnowapi.org/robots.txt) (403).

### EPA Air Quality System (AQS) API and AirData files

**Use** · effort S · confidence high · free key for the API only ·
verified: confirmed. [AQS API docs](https://aqs.epa.gov/aqsweb/documents/data_api.html).
US EPA.

- **Contents:** validated regulatory monitor data: raw samples; daily,
  quarterly and annual summaries; monitors and QA; by site, county, state,
  CBSA or bounding box. AirData: keyless zips of hourly, daily and annual
  data by parameter, from 1980 (e.g. daily PM2.5, parameter 88101, for
  2025: 758,834 rows, 8.4 MB).
- **Coverage:** US from 1980, including the Ada and Canyon monitors (Idaho
  DEQ). It "can take 6 months or more" for data to reach AQS.
- **Endpoint:** the API: sign up with an email address for a key. "Do not
  make more than 10 requests per minute", with a 5 s pause between
  requests, at most 1,000,000 rows a query and 5 parameters, and begin and
  end dates in the same year. AirData files at
  [download_files.html](https://aqs.epa.gov/aqsweb/airdata/download_files.html).
- **License or terms:** federal, public domain. "we may disable your
  account without notice" if the terms are broken.
- **robots.txt:** `aqs.epa.gov` answers 404 (no rules): allowed
  (re-checked Oct 7).
- **Updates:** AirData files twice a year: June (the complete prior year)
  and December (the summer ozone season). The API is continuous, with the
  lag.
- **Size:** daily PM2.5 nationally about 8–10 MB a year; national hourly
  zips are larger ⚠️. Valley subsets are small.
- **Uses:** smoke-day classification for traffic and crash research
  (validated data, as AirNow's guidelines require); smoke seasons before
  2019; ground truth for HRRR-Smoke.
- **Personas:** traffic researcher; history buff; fire and weather
  watcher.
- **Core pieces:** readings contract.
- **Risks:** lagged, so not for live use. The API key is an owner action
  (email); the AirData files need no key.
- **Verification:** sign-up, limits, lag, update schedule, coverage and
  robots confirmed on the official pages.
- **Evidence:** [API docs](https://aqs.epa.gov/aqsweb/documents/data_api.html),
  [AirData downloads](https://aqs.epa.gov/aqsweb/airdata/download_files.html),
  [robots.txt](https://aqs.epa.gov/robots.txt) (404).

### PurpleAir sensor API and map

**Avoid** · confidence high · paid key · verified: confirmed.
[develop.purpleair.com](https://develop.purpleair.com/). PurpleAir, Inc.
(a private company; consumer-owned sensors).

- **Contents:** readings every 2 minutes from low-cost PM sensors owned by
  private people, many at homes. Said to be dense in the valley ⚠️.
- **Access:** REST API at `api.purpleair.com` with a key from the developer
  site, paid in points (the free allotment and pricing weren't verified ⚠️;
  the developer page is JavaScript-only).
- **License or terms:** proprietary. PurpleAir staff said on Aug 25, 2022
  that such redistribution "would go against our Terms of Service"; the
  terms they quote restrict use with open-source materials (GPL, MIT).
- **robots.txt:** `api.purpleair.com` has `User-agent: *` / `Disallow: /`
  (the API host is disallowed). `www2.purpleair.com` redirects to
  `www.purpleair.com/robots.txt`, which disallows `/api/` except store,
  blog, pages and community paths.
- **Uses:** none for collection. A sensor the owner buys can be read
  locally on the owner's own network (a household plugin), which doesn't touch
  PurpleAir's API ⚠️.
- **Personas:** household (private).
- **Risks:** robots.txt disallows it, access is paid, redistribution isn't
  allowed, it conflicts with our MIT repository, and the sensors sit at
  private homes (people, not the road network).
- **Verification:** the robots disallow and the staff statement on
  redistribution and open-source licences confirmed. Pricing and free
  points unverified. Confidence raised to high for the "avoid" verdict.
- **Evidence:** robots.txt for [api.purpleair.com](https://api.purpleair.com/robots.txt)
  and [www2.purpleair.com](https://www2.purpleair.com/robots.txt) (redirects
  to www.purpleair.com), [PurpleAir community thread on re-hosting](https://community.purpleair.com/t/any-legal-issues-with-re-using-or-re-hosting-purple-air-data/1743),
  [developer site](https://develop.purpleair.com/) (JavaScript-only).

### HRRR with HRRR-Smoke

**Use** · effort L · confidence medium · no key · verified: corrected.
[NOAA HRRR on AWS](https://registry.opendata.aws/noaa-hrrr-pds/). NOAA
NWS/NCEP (model by NOAA GSL), distributed through NODD on AWS.

- **Contents:** the hourly 3 km CONUS model. In `wrfsfc` (confirmed from
  the 00Z Oct 6 analysis `.idx`): `MASSDEN` at "8 m above ground"
  (near-surface smoke), `COLMD` for the "entire atmosphere" (column smoke)
  and `VIS` at the surface. `AOTK` is also present but is a constant
  188-byte message ⚠️. The 3D fields in `wrfnat` include smoke on native
  levels ⚠️, plus clouds, humidity and wind for the 3D weather work.
  Forecasts run to 18 hours every hour, and to 48 hours at 00, 06, 12 and
  18Z.
- **Coverage:** CONUS. The bucket's archive starts in 2014; smoke since
  HRRRv4 (Dec 2020) ⚠️.
- **Endpoint:** `https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.YYYYMMDD/conus/hrrr.tHHz.wrfsfcfFF.grib2`
  with a `.grib2.idx` sidecar, so only the needed GRIB messages are fetched
  with HTTP Range requests (urllib supports Range). A Zarr copy is in the
  `hrrrzarr` bucket (University of Utah, us-west-1).
- **License or terms:** NODD: "open to the public and can be used as
  desired"; attribution requested; don't claim modified data is original.
- **robots.txt:** `noaa-hrrr-bdp-pds.s3.amazonaws.com` answers 404 (no
  rules): allowed (re-checked Oct 7). `nomads.ncep.noaa.gov` answers 404
  too, but has its own usage limits ⚠️; NODD is the preferred host.
- **Updates:** hourly runs. RRFS v1 is now scheduled for Nov 3, 2026 (SCN
  26-48, updated Oct 2, 2026; moved from Oct 14). It replaces NAM, HREF,
  SREF and HiresW, not HRRR, and REFS even uses HRRR members. A parallel
  feed has been on NOMADS since Aug 12, 2026; the NODD bucket
  `noaa-rrfs-pds` holds only retro and sample prefixes so far. No HRRR
  freeze or retirement notice was found, and the SCN doesn't mention smoke
  or dust in RRFS.
- **Size:** `wrfsfc` f00 is 134.9 MB and `wrfnat` f00 668 MB. By byte
  range, per hour of CONUS: `MASSDEN` about 0.40 MB, `COLMD` about 0.52 MB,
  `VIS` about 1.42 MB. That's about 55 MB a day of transfer for hourly
  analyses of all three, and about 0.45 GB a day for four 48-hour runs.
  Stored ring crops are tens of KB per field-hour. A 3D smoke column from
  `wrfnat` costs about 0.4 MB per level, roughly 20 MB per valid hour for
  about 50 levels ⚠️.
- **Uses:** a smoke forecast along I-84 and the valley for the next 6–48
  hours; a 3D smoke plume volume in the WebGL scene (the owner's 3D weather
  idea); a smoke-sunset predictor; "as forecast then" replay.
- **Personas:** fire and weather watcher; commuter; sky watcher and
  photographer; cyclist and pedestrian; aviation watcher.
- **Core pieces:** a fields contract for gridded time series with run and
  valid time (proposed), 3D engine, full replay.
- **Risks:** GRIB2 decoding needs wgrib2 or eccodes (outside the standard
  library), so the owner decides. Model fields are forecasts, so label
  them. Keep the fields contract model-agnostic, since RRFS arrives Nov 3
  (on NOMADS only so far).
- **Verification:** confirmed the license, buckets, the `.idx` byte-range
  method, field names and levels, and robots. Corrected: RRFS isn't
  operational yet; it goes live Nov 3, 2026, is only on NOMADS (parallel)
  and doesn't retire HRRR; "HRRR is frozen" and "retirement around 2028"
  are unsupported. Smoke messages are smaller (0.4–0.5 MB) and visibility
  larger than first claimed. The real cost is transfer, not storage.
- **Evidence:** [AWS registry](https://registry.opendata.aws/noaa-hrrr-pds/),
  [bucket robots.txt](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/robots.txt) (404),
  [sample `.idx`](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20261006/conus/hrrr.t00z.wrfsfcf00.grib2.idx),
  [sample GRIB2](https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.20261006/conus/hrrr.t00z.wrfsfcf00.grib2) (HEAD),
  [NWS notices](https://www.weather.gov/notification/),
  [SCN 26-48](https://www.weather.gov/media/notification/pdf_2026/scn26-048_Updated_RRFS_and_REFS_Implementation_aae.pdf),
  [PNS 26-70](https://www.weather.gov/media/notification/pdf_2026/pns26-70_HRRR_HRRRDAS_NOMADS_Product_Changes.pdf),
  [RRFS bucket listing](https://noaa-rrfs-pds.s3.amazonaws.com/?list-type=2&delimiter=/),
  [NOMADS robots.txt](https://nomads.ncep.noaa.gov/robots.txt) (404).

### National Air Quality Forecast Capability and NDGD air-quality services

**Use** · effort M · confidence medium · no key · verified: confirmed.
[NAQFC bucket](https://noaa-nws-naqfc-pds.s3.amazonaws.com/). NOAA NWS.

- **Contents:** bucket prefixes on Oct 7: `AQMv5`, `AQMv6`, `AQMv7`,
  `AQMv7_suppl`, `HYSPLIT_Dust`, `HYSPLIT_Smoke`, `RAP_Smoke`, `Temp`.
  ImageServers in `raster/air_quality`: `ndgd_apm25_hr01(_bc)`,
  `ndgd_apm25_hr24(_bc)`, `ndgd_mpm25_hr01(_bc)`, `ndgd_dust_sfc_time`,
  `ndgd_dust_vert_time`, `ndgd_smoke_sfc_1hr_avg_time`,
  `ndgd_smoke_vert_1hr_avg_time`, and ozone 1-hour and 8-hour averages and
  maxima (with `_bc` variants).
- **Coverage:** CONUS.
- **Endpoint:** anonymous S3 over HTTPS (GRIB2/NetCDF), or ArcGIS
  ImageServer `exportImage` and `identify` at
  `https://mapservices.weather.noaa.gov/raster/rest/services/air_quality/`.
- **License or terms:** NOAA, public domain; NODD terms for the bucket.
- **robots.txt:** the NODD bucket answers 404 (no rules).
  `mapservices.weather.noaa.gov/robots.txt` redirects to an HTML page at
  `www.weather.gov/gis/cloudgiswebservices`, so no rules: allowed
  (re-checked Oct 7).
- **Updates:** AQM runs twice daily ⚠️, with hourly fields. HYSPLIT is
  being re-coupled to RRFS (SCN 26-78) ⚠️, which may change the
  `HYSPLIT_Smoke` and `HYSPLIT_Dust` products.
- **Size:** small through ImageServer `identify` or ring exports; the GRIB
  files are larger.
- **Uses:** the official PM2.5 and smoke forecast next to HRRR; a dust
  forecast for blowing-dust days on I-84; an `identify` call per hour at a
  few points (bus stops, the Greenbelt), which avoids GRIB decoding.
- **Personas:** fire and weather watcher; cyclist and pedestrian;
  commuter.
- **Core pieces:** fields contract (proposed); readings contract (point
  `identify`).
- **Risks:** the ImageServer route avoids non-stdlib decoding but depends
  on a live service. Mind the difference between bias-corrected (`_bc`)
  and raw products. Product changes around the RRFS switch are possible.
- **Verification:** the bucket prefixes and image services confirmed; the
  `ndgd_mpm25` services and the HYSPLIT re-coupling notice were added. The
  run cadence wasn't re-verified.
- **Evidence:** [bucket listing](https://noaa-nws-naqfc-pds.s3.amazonaws.com/?list-type=2&delimiter=/),
  [air-quality services](https://mapservices.weather.noaa.gov/raster/rest/services/air_quality?f=json),
  [mapservices robots.txt](https://mapservices.weather.noaa.gov/robots.txt)
  (redirects to HTML), [NWS notices](https://www.weather.gov/notification/).

### Idaho DEQ crop residue burn decisions

**Avoid** (link only) · confidence high · verified: confirmed.
[DEQ crop residue burning](https://www.deq.idaho.gov/air-quality/smoke-and-burning/crop-residue-burning/).
Idaho Department of Environmental Quality.

- **Contents:** daily approve or deny decisions for agricultural field
  burning, by program area, statewide, in burn season.
- **Access:** a web map at `www2.deq.idaho.gov/air/CRB/BurnDecisionMap`;
  no documented feed. State data; terms not checked further because of
  robots.txt.
- **robots.txt:** `www2.deq.idaho.gov` disallows `/air/crb/` (among
  others), which matches `/air/CRB/BurnDecisionMap/Index` under our
  case-insensitive matching, so it's disallowed. `/air/AQIPublic/Forecast`
  is allowed but is HTML; DEQ's forecasts reach us through AirNow.
- **Uses:** a link from the farmer view; ask DEQ whether a feed exists.
- **Personas:** farmer.
- **Risks:** collecting it would break robots.txt. Burn approvals concern
  individual growers' fields, so even with a feed, show only aggregates.
- **Verification:** the robots result reproduced with the project parser.
  The "posted by 11:00" timing wasn't re-checked.
- **Evidence:** [robots.txt](https://www2.deq.idaho.gov/robots.txt).

### Interagency Wildland Fire Air Quality Response Program smoke outlooks

**Avoid** (link only) · confidence medium · verified: confirmed.
[outlooks.wildlandfiresmoke.net](https://outlooks.wildlandfiresmoke.net/).
USDA Forest Service and partners (Air Resource Advisors).

- **Contents:** narrative smoke outlooks with 3-day AQI forecasts for
  communities near large incidents where advisors are deployed; daily
  during deployments, only during large incidents.
- **Access:** web pages; the site is now a single-page app at
  `smoke-outlooks.wildlandfiresmoke.net`, with no documented feed. Federal;
  terms not checked further.
- **robots.txt:** `outlooks.wildlandfiresmoke.net/robots.txt` redirects to
  the new host's home page, and that host's `/robots.txt` returns the app's
  HTML: no rules on either.
- **Uses:** a link from the smoke card when an outlook covers the valley.
- **Personas:** fire and weather watcher.
- **Risks:** a JavaScript app with no documented feed; scraping it isn't
  worth it.
- **Verification:** no robots rules and no feed confirmed; the site moved
  to the smoke-outlooks host.
- **Evidence:** robots.txt for [outlooks](https://outlooks.wildlandfiresmoke.net/robots.txt)
  (redirect) and [smoke-outlooks](https://smoke-outlooks.wildlandfiresmoke.net/robots.txt)
  (HTML), [the app](https://smoke-outlooks.wildlandfiresmoke.net/).

---

## Alerts, evacuations, power shutoffs and heat

### NWS API alerts (api.weather.gov)

**Needs owner action** · effort S · confidence high · no key · verified:
confirmed. [API documentation](https://www.weather.gov/documentation/services-web-api).
NOAA National Weather Service.

- **Contents:** active and recent alerts as GeoJSON, JSON-LD, CAP and
  ATOM, by area, zone, point or event. The `/alerts` endpoint "contains
  alerts issued over the past seven days". US; real time.
- **Endpoint:** `https://api.weather.gov/alerts/active?area=ID` and
  similar. "A User Agent is required". Rate limits aren't published; retry
  after about 5 s.
- **License or terms:** "intended to be open data, free to use for any
  purpose".
- **robots.txt:** `User-agent: *` / `Disallow: /`, so it's disallowed under
  our rule even though the API is documented for programs (re-checked
  Oct 7).
- **Uses:** it would be the cleanest live alert feed, if the owner decides
  it's usable.
- **Personas:** fire and weather watcher; commuter.
- **Risks:** a direct conflict between robots.txt and the published API
  docs. The WWA map service's `url` field links into `api.weather.gov`, so
  those links must stay plain links, never fetched. The owner decides: ask
  the NWS, or keep to the robots-allowed WWA map service.
- **Verification:** the docs' wording and the robots disallow both
  confirmed.
- **Evidence:** [API documentation](https://www.weather.gov/documentation/services-web-api),
  [robots.txt](https://api.weather.gov/robots.txt).

### NWS watches, warnings and advisories map service

**Use** · effort S · confidence high · no key · verified: corrected.
[watch_warn_adv MapServer](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer).
NOAA National Weather Service, with the Storm Prediction Center (SPC) for
outlooks.

- **Contents:** layer 0, CurrentWarnings, and layer 1, WatchesWarnings:
  polygons with `prod_type` (the hazard's name, e.g. "Flood Advisory"),
  `msg_type`, `phenom`, `sig`, `event`, `issuance`, `onset`, `ends`,
  `expiration`, `wfo`, `url`, `cap_id`, `idp_filedate` and
  `idp_ingestdate`. `event` holds the VTEC event tracking number (e.g.
  "0347"), not the hazard's name. `url` and `cap_id` point to
  `api.weather.gov/alerts/<CAP id>`. The `fire_weather` folder has
  `SPC_firewx` (day 1–8 outlooks) and `nws_fire_weather_spot`.
- **Coverage:** US. The Boise forecast office (BOI) covers the ring.
- **Endpoint:** MapServer query by envelope (JSON). `tgftp.nws.noaa.gov/SL.us008001/DF.sha/DC.cap/DS.WWA/`
  has national `current_all.tar.gz` and `current_hazards.tar.gz`, 9.0 MB
  each and refreshed often, so don't poll them every 5 minutes. SPC
  outlooks: `https://mapservices.weather.noaa.gov/vector/rest/services/fire_weather/SPC_firewx/MapServer`.
- **License or terms:** NWS, public domain (service copyright text
  "National Weather Service").
- **robots.txt:** `mapservices.weather.noaa.gov/robots.txt` redirects to an
  HTML page (no rules, allowed); `tgftp.nws.noaa.gov` answers 404 (no
  rules). `www.spc.noaa.gov/robots.txt` disallows `/` for everyone with
  Crawl-delay 10, so don't fetch SPC's own site. The `url` field's target,
  `api.weather.gov`, is disallowed (re-checked Oct 7).
- **Updates:** near real time; records carry `idp_filedate` and
  `idp_ingestdate` about 20 s apart. A 5-minute refresh isn't stated in the
  metadata ⚠️.
- **Size:** KB per ring query; versions only on change.
- **Uses:** alert lifecycles keyed by VTEC (`wfo`, `phenom`, `sig`, event
  tracking number and year), since `cap_id` changes with every update; Red
  Flag Warnings shading fire-weather zones; Dense Smoke and Dense Fog on
  I-84; the Valley Feed; history from now on (IEM covers the past).
- **Personas:** fire and weather watcher; commuter; cyclist and
  pedestrian; gardener; farmer.
- **Core pieces:** lifecycles contract, Valley Feed, full replay, shared
  ArcGIS reader.
- **Risks:** the service gives a subset of CAP; the full text is behind the
  `url` field on `api.weather.gov`, which robots.txt disallows, so show it
  only as a link. Non-VTEC products (e.g. marine statements) have blank
  `phenom`, `sig` and `wfo`. The service is an ArcGIS front end and may
  change.
- **Verification:** the layers, fire-weather services and robots
  confirmed. Corrected: `event` is the VTEC event tracking number;
  "follow the url field for the full text" would fetch `api.weather.gov`,
  which robots.txt disallows; the tgftp files are national 9 MB tarballs;
  the 5-minute cadence isn't documented.
- **Evidence:** [MapServer](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer?f=json),
  [layer 0](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer/0?f=json),
  [layer 1](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer/1?f=json),
  [layer 1 query](https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer/1/query) (2-record sample),
  [fire-weather services](https://mapservices.weather.noaa.gov/vector/rest/services/fire_weather?f=json),
  [tgftp WWA folder](https://tgftp.nws.noaa.gov/SL.us008001/DF.sha/DC.cap/DS.WWA/),
  robots.txt for [SPC](https://www.spc.noaa.gov/robots.txt) and
  [tgftp](https://tgftp.nws.noaa.gov/robots.txt) (404).

### Iowa Environmental Mesonet (IEM) NWS warning archive

**Use** · effort S · confidence high · no key · verified: confirmed.
[IEM watch/warning download](https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml).
Iowa State University's Iowa Environmental Mesonet, archiving NWS products.

- **Contents:** archived NWS events: storm-based polygons from 2002 (only
  the initial polygon: "Polygon updates in the SVS statements are
  ignored"), zone and county VTEC events from Nov 12, 2005, and
  county-based tornado and severe thunderstorm warnings from Jan 1, 1986
  (before VTEC). Shapefile with CSV, KML or Excel. Annual zips under
  `/pickup/wwa/` are rebuilt daily (around 2 AM Central).
- **Coverage:** US; filter by forecast office (BOI) or state (ID).
- **Endpoint:** scripted requests to `/cgi-bin/request/gis/watchwarn.py`
  (see `?help`), one year per request unless filtered by state or office;
  or the `/pickup/wwa/` annual zips.
- **License or terms:** redistributed NWS public-domain products. No
  formal terms found; credit IEM ⚠️.
- **robots.txt:** IEM's robots.txt has no User-agent line, so lenient
  parsing applies its `Crawl-delay: 120` and disallows (`/usage/`, `/tmp/`,
  `/data/NIDS/`, `/data/nexrd2/`, `/data/model/`, `/archive/nexrad/`,
  `/archive/raw/snet/`) to everyone. `watchwarn.py` and `/pickup/wwa/` are
  allowed by the project parser (re-checked Oct 7).
- **Updates:** daily (zips); on demand (the script).
- **Size:** BOI or Idaho, 2005–2026: tens of MB ⚠️.
- **Uses:** a history of Red Flag, Dense Fog and Smoke, Heat and Flood
  alerts for replay and research (overlapping COMPASS crashes 2008–2025);
  a test of the fog → detector fallback → long greens theory
  ([ch. 2 §2.4](../02-treasure-valley-signal-system.md#24-how-timing-works-here-today))
  with Dense Fog Advisory hours.
- **Personas:** traffic researcher; history buff; neighbor and civic.
- **Core pieces:** lifecycles contract, full replay.
- **Risks:** a volunteer-run academic service: keep the 120 s delay and
  pull the yearly zips once. Replay shows only each warning's initial
  polygon.
- **Verification:** the coverage dates, request limits, daily zip rebuild
  and robots confirmed. Added the initial-polygon-only caveat.
- **Evidence:** [robots.txt](https://mesonet.agron.iastate.edu/robots.txt),
  [download page](https://mesonet.agron.iastate.edu/request/gis/watchwarn.phtml).

### IPAWS archived alerts (OpenFEMA)

**Use** · effort M · confidence high · no key · verified: confirmed.
[OpenFEMA data page](https://www.fema.gov/openfema-data-page/ipaws-archived-alerts-v1).
FEMA's Integrated Public Alert and Warning System, through OpenFEMA.

- **Contents:** CAP v1.2 messages from over 1,450 alert originators (EAS,
  WEA, NOAA Weather Radio): identifier, sender, sent, status, message type,
  info (event, urgency, severity, headline, description, instruction),
  areas (polygons, circles, geocodes) and a search geometry. 4,885,907
  records.
- **Coverage:** US, June 2012 to the present, published "with a
  twenty-four (24) hour delay". A keyless sample at 06:26 UTC on Oct 7
  returned a newest `sent` of 2026-10-06T06:01Z.
- **Endpoint:** `https://www.fema.gov/api/open/v1/IpawsArchivedAlerts` with
  OData `$filter`, `$select`, `$orderby` and `$top` (works keyless). Bulk
  JSON, JSONA or JSONL files of 500 MB to 10 GB.
- **License or terms:** the OpenFEMA terms: state that the product "uses
  the Federal Emergency Management Agency's OpenFEMA API, but is not
  endorsed by FEMA"; use "solely for statistical research or as a
  reporting record"; no re-identification.
- **robots.txt:** `www.fema.gov` answers 403, so no rules (allowed); the
  API answered 200 to our User-Agent (re-checked Oct 7).
- **Updates:** every 2 minutes, behind the 24-hour delay.
- **Size:** an Idaho or ring subset is thousands of messages, MBs ⚠️.
- **Uses:** evacuation history: official evacuation and shelter polygons
  for past fires and floods, drawn at their sent time; egress-road analysis
  inside evacuation polygons (only where a polygon exists; many messages
  carry only FIPS/SAME geocodes); a neighborhood alert timeline.
- **Personas:** fire and weather watcher; neighbor and civic; traffic
  researcher; history buff.
- **Core pieces:** lifecycles contract, full replay, Valley Feed (as
  history).
- **Risks:** IPAWS carries AMBER (CAE), Blue (BLU), law-enforcement (LEW)
  and probably missing-and-endangered-person (MEP ⚠️) alerts that describe
  people and vehicles; drop those at ingest. Civil-danger and
  local-emergency alerts (CDW, LAE) have free text that can describe
  suspects, so keep only their event, time and area, not the description.
  FEMA "does not validate the content". The 24-hour delay makes it history
  only.
- **Verification:** the coverage, the 24-hour delay (seen in the live
  sample), record count, formats, terms and keyless access confirmed. The
  ethics filter was widened (MEP, and the CDW and LAE free text).
- **Evidence:** [data page](https://www.fema.gov/openfema-data-page/ipaws-archived-alerts-v1),
  [OpenFEMA terms](https://www.fema.gov/about/openfema/terms-conditions),
  [robots.txt](https://www.fema.gov/robots.txt) (403),
  [one-record sample](https://www.fema.gov/api/open/v1/IpawsArchivedAlerts?$top=1&$select=sent,status,msgType&$orderby=sent%20desc).

### Genasys Protect evacuation zones

**Needs owner action** · effort M · confidence low · partnership needed ·
verified: corrected. [protect.genasys.com](https://protect.genasys.com/).
Genasys Inc. (formerly Zonehaven; private), with participating county
emergency managers.

- **Contents:** pre-drawn evacuation zones with a live status (order,
  warning, normal) set by emergency officials; live during events.
- **Coverage:** Ada County's alert sign-up ("Ada Alert") runs on Genasys
  (`adaalert.genasys.com`), so Genasys Protect zones for Ada are plausible
  but not confirmed. Canyon is unknown ⚠️.
- **Access:** a public viewer. The Zone Map Service is for customers and
  partners under a data-sharing agreement (help-centre material found by
  search ⚠️, not re-read).
- **License or terms:** proprietary; access only under an agreement ⚠️.
- **robots.txt:** `User-agent: *` / `Disallow:` (allowed), but its terms
  govern the data feed (re-checked Oct 7).
- **Uses:** live evacuation zones, if the county uses Protect and Genasys
  agrees.
- **Personas:** fire and weather watcher; neighbor and civic.
- **Core pieces:** lifecycles contract, areas.
- **Risks:** it requires an agreement. A stale copy is dangerous in an
  emergency, so link out rather than mirror. IPAWS gives the history
  without an agreement.
- **Verification:** robots confirmed. New finding: Ada County's alert
  system uses Genasys, which strengthens the case for asking Ada County
  Emergency Management. The agreement terms weren't re-verified (no search
  was available).
- **Evidence:** [robots.txt](https://protect.genasys.com/robots.txt),
  [Ada County Emergency Management](https://adacounty.id.gov/emergencymanagement/).

### Idaho Power public safety power shutoff (PSPS) areas

**Needs owner action** · effort M · confidence low · verified: corrected.
[PSPS event information](https://www.idahopower.com/outages-safety/wildfire-safety/psps-event-information/).
Idaho Power (a private utility).

- **Contents:** a live ArcGIS Experience map
  (`experience.arcgis.com/experience/9b9311486c4742adaa9e0baaaf8932d2`)
  showing areas "being monitored for a PSPS or actively in a PSPS outage".
  A separate layer of areas where shutoffs are "more likely" wasn't seen
  on this page ⚠️.
- **Coverage:** Idaho Power's territory, the valley included; updated
  during events.
- **Access:** a public web app; the underlying layers weren't probed. Key
  or account unknown.
- **License or terms:** not found; a private company's data, so ask first.
- **robots.txt:** `www.idahopower.com` returns HTML for robots.txt (no
  rules); `experience.arcgis.com` answers 404 (no rules). The host of the
  FeatureServer behind the map wasn't identified or checked.
- **Uses:** signals at risk of going dark in a PSPS (with the
  `intersections` plugin); fire-weather context.
- **Personas:** traffic researcher; commuter; fire and weather watcher.
- **Core pieces:** lifecycles contract, layer system.
- **Risks:** the terms are unknown. Outage data mustn't drift toward
  customer-level detail.
- **Verification:** the map link and the monitored and active areas
  confirmed. The "more likely" layer wasn't found on this page. Terms
  still unknown.
- **Evidence:** [PSPS page](https://www.idahopower.com/outages-safety/wildfire-safety/psps-event-information/),
  robots.txt for [idahopower.com](https://www.idahopower.com/robots.txt)
  and [experience.arcgis.com](https://experience.arcgis.com/robots.txt) (404).

### NWS HeatRisk

**Use** · effort M · confidence high · no key · verified: confirmed.
[HeatRisk](https://www.wpc.ncep.noaa.gov/heatrisk/). NOAA NWS Weather
Prediction Center, with the CDC.

- **Contents:** a daily heat-risk category 0–4 (green: little or none;
  yellow: minor; orange: moderate; red: major; magenta: extreme) for 7
  days. Experimental, and "supplementary to official NWS heat products".
- **Coverage:** CONUS (Alaska and probabilistic versions on separate
  pages). An archive is under `/heatrisk/data/archive/`; how far back isn't
  stated ⚠️.
- **Endpoint:** KML (`HeatRisk_Entire_Fcst.kml`,
  `HeatRisk_Day1..7_Fcst.kml`), GeoTIFF (`HeatRisk_[1-7]_Mercator.tif`), a
  REST ImageServer at
  `mapservices.weather.noaa.gov/experimental/rest/services/NWS_HeatRisk/ImageServer`
  (with a time extent), WMS/WMTS and WCS.
- **License or terms:** NWS, public domain; no terms on the page.
- **robots.txt:** `www.wpc.ncep.noaa.gov` answers 404 (no rules);
  `mapservices.weather.noaa.gov` redirects robots.txt to an HTML page (no
  rules). Both allowed (re-checked Oct 7).
- **Updates:** daily (time not stated).
- **Size:** a few MB of CONUS GeoTIFFs a day ⚠️; the ring crop is KB.
- **Uses:** heat days for transit riders (hot, unshaded stops); garden and
  cycling calendars; research on heat days against bus speeds, ridership
  and crashes (depends on the archive's depth).
- **Personas:** gardener; cyclist and pedestrian; commuter; traffic
  researcher; farmer.
- **Core pieces:** fields contract (proposed) or readings at sample
  points; layer system.
- **Risks:** experimental, with a service path under `/experimental/`. Its
  colours include green and red, so add labels. The historical depth for
  research is unknown.
- **Verification:** the experimental status, products, services,
  categories and robots confirmed. The archive's depth is unknown.
- **Evidence:** [HeatRisk page](https://www.wpc.ncep.noaa.gov/heatrisk/),
  [data page](https://www.wpc.ncep.noaa.gov/heatrisk/data.html),
  [ImageServer](https://mapservices.weather.noaa.gov/experimental/rest/services/NWS_HeatRisk/ImageServer?f=json),
  [robots.txt](https://www.wpc.ncep.noaa.gov/robots.txt) (404).

---

## Floods, water and debris flows

### National Water Prediction Service (NWPS) river forecasts and flood categories

**Use** · effort S · confidence high · no key · verified: confirmed.
[NWPS API](https://water.noaa.gov/about/api). NOAA NWS Office of Water
Prediction and the Northwest River Forecast Center.

- **Contents:** per gauge: `lid`, `usgsId`, `reachId`, `rfc`, `wfo`, flood
  categories (action, minor, moderate, major) in stage and flow, historic
  crests, low-water impacts, status (observed and forecast, with flood
  category), datums, inundation, upstream and downstream links, and
  `dataAttribution`. One sample request, for BIGI1, "Boise River at Boise
  (Glenwood Bridge)" (USGS 13206000, NWRFC/BOI):

  | Category | Stage | Flow |
  |---|---|---|
  | Action | 9.7 ft | 6,500 cfs |
  | Minor | 10.1 ft | 7,000 cfs |
  | Moderate | 12.9 ft | 11,000 cfs |
  | Major | (none) | 15,000 cfs |

  Top crests: 2017-06-06 (11.93 ft, 9,590 cfs), 1983-06-13 (11.54 ft,
  9,840 cfs), 1998-05-31 (11.1 ft, 8,350 cfs). Observed 387 cfs (3.6 ft),
  no flooding, at 03:45 UTC on Oct 7.
- **Coverage:** NWS forecast points in the ring (Boise, Payette and Snake
  rivers; the gauge IDs still to list ⚠️).
- **Endpoint:** `https://api.water.noaa.gov/nwps/v1/gauges/{LID}` and
  `/stageflow`; docs at `/nwps/v1/docs/`. No history beyond crests and low
  water, so we keep our own readings.
- **License or terms:** NWS, public domain.
- **robots.txt:** `api.water.noaa.gov` and `water.noaa.gov` answer 404 (no
  rules): allowed (re-checked Oct 7).
- **Updates:** observations about every 15 minutes to hourly; forecasts as
  the River Forecast Center issues them.
- **Size:** 10–50 KB per gauge per poll; about 10 gauges.
- **Uses:** a river and Greenbelt flood watch with category bands;
  observed readings plus forecast runs kept with their issue time, for
  replay; flood-impact statements linked to roads and paths ⚠️.
- **Personas:** hiker, backpacker, camper, hunter, angler, floater;
  cyclist and pedestrian; fire and weather watcher; history buff;
  homeowner or land buyer (private).
- **Core pieces:** readings contract (with forecast runs), time-series
  card, Valley Feed.
- **Risks:** shared with the water plugin, so decide which plugin owns
  gauges. Some categories lack a stage (major reads −9999).
- **Verification:** the flood categories, crests, IDs and robots
  reproduced with one sample request. The third crest (1998) was added;
  the 2006 and 2012 crests in the ideas are unverified.
- **Evidence:** [BIGI1 sample](https://api.water.noaa.gov/nwps/v1/gauges/BIGI1),
  robots.txt for [api.water.noaa.gov](https://api.water.noaa.gov/robots.txt)
  and [water.noaa.gov](https://water.noaa.gov/robots.txt) (both 404).

### USGS Water Data APIs and legacy WaterServices

**Needs owner action** · effort S · confidence high · verified: confirmed.
[api.waterdata.usgs.gov](https://api.waterdata.usgs.gov/). US Geological
Survey.

- **Contents:** continuous (instantaneous) values, daily values,
  monitoring locations and time-series metadata for every USGS gauge,
  canals included; 15-minute data, US-wide, every gauge in the ring.
- **Endpoint:** new: `https://api.waterdata.usgs.gov/ogcapi/{v0|v1}/collections/{continuous,daily,latest-continuous,...}/items`
  (whether a key is optional wasn't verified ⚠️). Legacy:
  `https://waterservices.usgs.gov/nwis/iv/` (JSON).
- **License or terms:** USGS, public domain; credit "U.S. Geological
  Survey" (as quoted in the comments of their robots.txt).
- **robots.txt:** `api.waterdata.usgs.gov` disallows
  `/ogcapi/*/collections/*/items*` (every data endpoint), `/samples-data/*`,
  `/squid/*` and `/statistics/*` (the docs are allowed), so collecting
  through the new API is disallowed. `waterservices.usgs.gov` answers 404
  (allowed), but that service is being retired (re-checked Oct 7).
- **Uses:** gauges that aren't NWS forecast points (canals, small
  streams).
- **Personas:** hiker, backpacker, camper, hunter, angler, floater;
  farmer; fire and weather watcher.
- **Core pieces:** readings contract.
- **Risks:** the decommission blog (updated Oct 2, 2026): no intentional
  degradation before Aug 2026; "Campaign 3" runs Nov 2026 to Feb 2027;
  WaterServices will be "decommissioned in the first quarter of 2027".
  Options for the owner: NWPS (USGS-observed values at forecast points);
  ask USGS whether the robots rule is meant for API clients; or use the
  legacy service until it goes.
- **Verification:** the robots disallow and the decommission timeline
  confirmed. The new API's key policy wasn't checked.
- **Evidence:** robots.txt for [api.waterdata.usgs.gov](https://api.waterdata.usgs.gov/robots.txt)
  and [waterservices.usgs.gov](https://waterservices.usgs.gov/robots.txt) (404),
  [decommission blog](https://waterdata.usgs.gov/blog/api-waterservices-decom/).

### FEMA National Flood Hazard Layer (NFHL)

**Needs owner action** · effort M · confidence high · no key · verified:
corrected. [NFHL page](https://www.fema.gov/flood-maps/national-flood-hazard-layer).
FEMA.

- **Contents:** effective flood zones (A, AE, AO, X and others), base
  flood elevations, cross-sections, levees, letters of map revision and
  amendment (LOMRs, LOMAs), FIRM panels, gauges and high-water marks.
- **Coverage** (from IDWR's FEMA status layer, counties intersecting the
  ring): digital FIRMs for Ada, Canyon, Gem, Valley and Washington; paper
  FIRMs for Boise, Elmore and Payette; none for Owyhee. Adams doesn't
  intersect the ring. Malheur County, Oregon, is in the ring but not in
  IDWR's Idaho layer.
- **Access:** the `hazards.fema.gov` NFHL services and scripted MSC
  product downloads are disallowed by robots.txt. So the owner would
  download Ada (16001) and Canyon (16027) by hand from the Map Service
  Center, as with Geofabrik, and we'd load them as kind `manual`. The page
  also offers Google Earth KMZ. An alternative: Ada County's `FEMA_Layers`
  MapServer at `gisdevapi.adacounty.id.gov` (Ada only, on a "dev" host ⚠️).
- **License or terms:** federal flood maps; the NFHL page states no
  license, terms or attribution ⚠️.
- **robots.txt:** `hazards.fema.gov` disallows `/*?*`, `/arcgis` and
  several archived-flood-data paths. `msc.fema.gov` disallows `/*?*`,
  `/portal/downloadProduct?productID=` and `/arcgis`.
  `gisdevapi.adacounty.id.gov` has only content-signal comments, no rules
  (allowed). `gis.idwr.idaho.gov/robots.txt` redirects to
  `error.idaho.gov` (HTML, no rules). One metadata request from the
  research pass reached `hazards.fema.gov/arcgis` before its robots.txt was
  read; it's disclosed and won't be repeated. The verification made none.
- **Updates:** "New and revised data is being added continuously"; a
  county changes a few times a year.
- **Size:** county NFHL zips are tens of MB ⚠️.
- **Uses:** flood zones along the Greenbelt and the Boise River; a
  homeowner hazard sheet (private); development inside floodplains (with
  COMPASS permits, aggregated).
- **Personas:** homeowner or land buyer (private); cyclist and pedestrian;
  neighbor and civic; hiker, backpacker, camper, hunter, angler, floater.
- **Core pieces:** layer system, manual source kind, areas.
- **Risks:** hand downloads go stale, so record the effective date.
  Parsing a shapefile or geodatabase needs GDAL. The basemap builds use
  GDAL but ran off the server, which has no GDAL today
  ([deploy/README](../../deploy/README.md)), so this is a server-side
  addition for the owner to approve.
- **Verification:** the robots findings confirmed. Corrected: Valley and
  Washington counties have digital FIRMs, and Adams doesn't intersect the
  ring; the assumption that GDAL is already on the server was wrong.
- **Evidence:** [NFHL page](https://www.fema.gov/flood-maps/national-flood-hazard-layer),
  robots.txt for [hazards.fema.gov](https://hazards.fema.gov/robots.txt),
  [msc.fema.gov](https://msc.fema.gov/robots.txt),
  [gisdevapi.adacounty.id.gov](https://gisdevapi.adacounty.id.gov/robots.txt)
  and [gis.idwr.idaho.gov](https://gis.idwr.idaho.gov/robots.txt) (302 to
  error.idaho.gov), [IDWR FEMA status query](https://gis.idwr.idaho.gov/hosting/rest/services/Regulatory/FemaGisDataStatus/FeatureServer/0/query)
  (ring counties).

### USGS post-fire debris-flow hazard assessments

**Use** (by hand) · effort S · confidence low · no key · verified:
unverifiable. [Program page](https://www.usgs.gov/programs/landslide-hazards/science/postfire-debris-flow-hazards).
USGS Landslide Hazards Program.

- **Contents:** per-fire likelihood and volume of debris flows by basin
  for design storms, and the rainfall rates that trigger them; yearly
  collections ⚠️.
- **Coverage:** select western fires only; whether any ring fires were
  assessed is unchecked ⚠️.
- **Access:** a dashboard at [apps.usgs.gov/landslides/pwfdf/](https://apps.usgs.gov/landslides/pwfdf/)
  (answered 200), with per-fire downloads and GIS services, fetched by hand
  per fire ⚠️. Kind `manual`.
- **License or terms:** USGS, public domain ⚠️.
- **robots.txt:** `apps.usgs.gov` answers 404 (no rules, so the dashboard
  is allowed). `landslides.usgs.gov/robots.txt` answers 301 to
  `www.usgs.gov`, and `www.usgs.gov/robots.txt` timed out twice from the
  research network: unreachable, so "disallow for now" under our rule. The
  research pass's "returns HTML (no rules)" couldn't be reproduced.
- **Updates:** per assessed fire. Small per fire.
- **Uses:** after a foothills fire, basins at risk above roads and trails,
  combined with NWS Flash Flood Warnings.
- **Personas:** hiker, backpacker, camper, hunter, angler, floater;
  commuter; homeowner or land buyer (private).
- **Core pieces:** layer system, manual source kind.
- **Risks:** coverage is sparse. The program page timed out, so the claims
  about its contents couldn't be checked.
- **Verification:** `www.usgs.gov` was unreachable (two timeouts), so
  neither the page nor its robots.txt could be confirmed. Only the
  dashboard host checked out. Use by hand from the dashboard; confidence
  lowered.
- **Evidence:** [program page](https://www.usgs.gov/programs/landslide-hazards/science/postfire-debris-flow-hazards)
  (timed out), robots.txt for [www.usgs.gov](https://www.usgs.gov/robots.txt)
  (timed out), [landslides.usgs.gov](https://landslides.usgs.gov/robots.txt)
  (301) and [apps.usgs.gov](https://apps.usgs.gov/robots.txt) (404),
  [dashboard](https://apps.usgs.gov/landslides/pwfdf/) (200).

---

## Earthquakes, drought and storm history

### USGS earthquake feeds and FDSN event service (ComCat)

**Use** · effort S · confidence high · no key · verified: confirmed.
[GeoJSON feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php).
USGS Earthquake Hazards Program.

- **Contents:** GeoJSON summary feeds (past hour, day, week and month;
  significant, M4.5+, M2.5+, M1.0+ and all) with `mag`, `place`, `time`,
  `felt`, `cdi`, `mmi`, `alert`, `tsunami`, `sig` and `ids`; detail feeds
  link ShakeMap and Did You Feel It? products. FDSN `/fdsnws/event/1/query`
  and `/count` for history.
- **Coverage:** global. In the ring: 13 events of M2.5+ since 1970 (FDSN
  count reproduced Oct 7; `maxAllowed` 20,000). The 2020 Stanley M6.5
  (about 44.4°N, 115.1°W) lies outside the ring ⚠️.
- **Endpoint:** `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{level}_{period}.geojson`;
  `https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minlatitude=...`.
- **License or terms:** USGS, public domain; credit USGS.
- **robots.txt:** `earthquake.usgs.gov` answers 404 (no rules): allowed
  (re-checked Oct 7).
- **Updates:** every minute. Tiny.
- **Uses:** live quake pings; ShakeMap intensity over roads and bridges
  for a big regional quake; a history layer.
- **Personas:** fire and weather watcher; neighbor and civic; history
  buff; homeowner or land buyer (private).
- **Core pieces:** lifecycles or point events, Valley Feed, layer system.
- **Risks:** low local activity, so keep it a light layer. Did You Feel It?
  reports are aggregated by USGS, so link out rather than collect.
- **Verification:** the count of 13 and robots reproduced. The feed page
  itself wasn't re-read.
- **Evidence:** [FDSN count for the ring](https://earthquake.usgs.gov/fdsnws/event/1/count?format=geojson&starttime=1970-01-01&minlatitude=42.90&maxlatitude=44.30&minlongitude=-117.30&maxlongitude=-115.60&minmagnitude=2.5),
  [robots.txt](https://earthquake.usgs.gov/robots.txt) (404).

### U.S. Drought Monitor

**Use** · effort S · confidence medium · no key · verified: corrected.
[droughtmonitor.unl.edu](https://droughtmonitor.unl.edu/). National
Drought Mitigation Center (University of Nebraska–Lincoln), with USDA,
NOAA and NASA.

- **Contents:** weekly (Thursday) drought polygons, D0–D4, since 2000
  (fields `DM`, `ValidStartDate`, `ValidEndDate`, `MapDate`,
  `ReleaseDate`, `ReleaseWeek` in NDMC's archive service); statistics of
  percent area per category by county and state.
- **Coverage:** US, including Ada and Canyon counties.
- **Endpoint:** polygons through NDMC's own ArcGIS Online org (portal
  "National Drought Mitigation Center", urlKey `UNLDroughtCenter`), e.g.
  `https://services5.arcgis.com/0OTVzJS4K09zlixn/arcgis/rest/services/USDM_archive/FeatureServer/0`.
  Its `timeInfo` extent reads 2000-01-04 to 2020-11-17, so check coverage
  after 2020 ⚠️. A current-week service also exists. FEMA's mirror
  (`gis.fema.gov .../Partner/Drought_Current/FeatureServer`) is built from
  the robots-disallowed `USDM_current_M.zip`. Statistics come from
  `usdmdataservices.unl.edu/api/...`. The official `/data/` shapefiles and
  `DataArchive.aspx` are disallowed by robots.txt.
- **License or terms:** reproduce with the credit (paraphrasing the
  Permission page): jointly produced by the National Drought Mitigation
  Center at the University of Nebraska-Lincoln, the USDA, NOAA and NASA,
  and "Map courtesy of NDMC". The same wording is in the ArcGIS item's
  `licenseInfo`.
- **robots.txt:** `droughtmonitor.unl.edu` disallows `/data/`,
  `/nadmdata/`, `/webfiles/` and `/DmData/DataArchive.aspx`.
  `usdmdataservices.unl.edu` and `gis.fema.gov` answer 404, and
  `services5.arcgis.com` answers 403: no rules on any of them, so allowed
  (re-checked Oct 7).
- **Updates:** weekly.
- **Size:** KB a week for the ring; the 2000–present ring archive is a few
  MB.
- **Uses:** drought class over farms and canals; fire-season context next
  to restrictions; a weekly lifecycle per category area for replay, with
  history from NDMC's archive service.
- **Personas:** farmer; gardener; fire and weather watcher; hiker,
  backpacker, camper, hunter, angler, floater.
- **Core pieces:** lifecycles or area readings, layer system, full replay.
- **Risks:** FEMA's mirror republishes a file whose own host disallows
  robots; legitimate, but prefer NDMC's ArcGIS service. The archive's
  time-extent metadata may be stale; check it before relying on it after
  2020.
- **Verification:** robots and the credit wording confirmed. Corrected:
  the `USDM_current` and `USDM_archive` services aren't in a personal
  account; their owner belongs to NDMC's own ArcGIS org, so this is the
  publisher's robots-allowed route to the polygon archive. That settles the
  "archive unclear" risk, apart from the time-extent question.
- **Evidence:** [robots.txt](https://droughtmonitor.unl.edu/robots.txt),
  [Permission page](https://droughtmonitor.unl.edu/About/Permission.aspx),
  [FEMA mirror](https://gis.fema.gov/arcgis/rest/services/Partner/Drought_Current/FeatureServer?f=json),
  [ArcGIS item 04b5b078](https://www.arcgis.com/sharing/rest/content/items/04b5b078b7b7478eb5e9a0485c294a6e?f=json),
  [NDMC portal](https://www.arcgis.com/sharing/rest/portals/0OTVzJS4K09zlixn?f=json),
  [USDM_archive layer](https://services5.arcgis.com/0OTVzJS4K09zlixn/arcgis/rest/services/USDM_archive/FeatureServer/0?f=json),
  robots.txt for [services5.arcgis.com](https://services5.arcgis.com/robots.txt) (403)
  and [usdmdataservices.unl.edu](https://usdmdataservices.unl.edu/robots.txt) (404).

### NCEI Storm Events Database

**Use** · effort S · confidence high · no key · verified: confirmed.
[Bulk data page](https://www.ncei.noaa.gov/stormevents/ftp.jsp). NOAA
National Centers for Environmental Information, from NWS reports.

- **Contents:** yearly CSVs: details (event types such as Wildfire, Flood,
  Flash Flood, Dense Smoke, Dense Fog, Dust Storm, Excessive Heat, High
  Wind and Heavy Snow; begin and end; county or zone; damages;
  narratives), locations and fatalities.
- **Coverage:** US, 1950–2026. The Oct 7 listing had d2024 (c20260728),
  d2025 (c20260819) and d2026 (c20260918).
- **Endpoint:** `https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_details-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz`.
- **License or terms:** NOAA, public domain ⚠️ (no license page read).
- **robots.txt:** NCEI disallows `/data*` and `/orders*` at the root (plus
  CRN access paths); `/pub/data/swdi/stormevents/csvfiles/` is allowed by
  the project parser (re-checked Oct 7).
- **Updates:** monthly, a few months behind.
- **Size:** a few MB a year nationally; ring rows are tiny.
- **Uses:** a history of hazards by county or zone (smoke, fog, dust,
  floods, heat); ground truth for the research day classification.
- **Personas:** history buff; traffic researcher; neighbor and civic.
- **Core pieces:** lifecycles contract, full replay.
- **Risks:** narratives can describe injured or killed people, so keep
  counts and don't surface narrative text with personal details.
- **Verification:** the file naming, the 2026 file and robots confirmed.
- **Evidence:** [robots.txt](https://www.ncei.noaa.gov/robots.txt),
  [CSV folder](https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/).

---

## Ideas by persona

From the research, with the verification's corrections applied. Persona
names follow [chapter 16](../16-ideas-and-personas.md); "in hand" means
data we already record.

### Fire and weather watcher

- **Fire board.** A Hazards lens showing every active fire in the ring.
  WFIGS points are sized by acres and perimeters carry a containment ring
  (containment read from the all-years record, since `_Current` drops a
  fire once it's contained); VIIRS 375 m hotspot pixels glow on the 3D
  terrain (fresher ones brighter) and GOES 5-minute fire pixels pulse
  between overpasses. HMS smoke is tinted light, medium or heavy. Tapping a
  fire opens a card: discovery time, acres, percent contained, cause
  class, personnel, a growth chart built from our own perimeter versions,
  an FRP curve, the restriction stage and closures that touch it, and a
  plain link to InciWeb (never fetched).
  *Sources:* WFIGS, FIRMS, GOES-18 FDC, HMS, IDL restrictions, USFS forest
  orders. *Core:* layer system, lifecycles, 3D engine, time-series card,
  Valley Feed.
- **Fire replay.** Choose a past fire (MM65 I84 on 2025-07-19, the Range
  fire on 2025-07-31, Claremont in July 2026) and scrub the time bar.
  Satellite detections appear overpass by overpass (VIIRS, then GOES every
  5 minutes), perimeters grow, smoke polygons drift, the Red Flag Warning
  switches on, and IPAWS evacuation polygons appear at their sent time.
  For fires after Oct 6, 2026, our 511 closures, WZDx and camera frames
  line up too. Everything is drawn as it was known at that moment,
  forecasts included. Back-dated FIRMS needs the MAP_KEY or an Earthdata
  Login (owner actions), and IEM keeps only each warning's first polygon.
  *Sources:* WFIGS, FIRMS archive, GOES-18 FDC (NODD archive), HMS, IEM,
  IPAWS, 511 Idaho API (in hand). *Core:* full replay, fields (proposed),
  lifecycles, 3D engine.
- **Evacuation history and egress.** IPAWS evacuation, shelter-in-place
  and fire-warning polygons since 2012, drawn at their sent time. For each
  one, the map highlights the roads leaving the polygon, with our lanes and
  posted speeds, and estimates egress capacity per exit road (lanes ×
  saturation flow). Only where a polygon exists: many messages carry only
  geocodes. A planning view for the WUI edge that never tracks anyone;
  person-related alerts (AMBER, Blue, law-enforcement, and probably
  missing-person ⚠️) are dropped at ingest. *Sources:* IPAWS, `roads`
  lanes and speeds (in hand), Wildfire Risk to Communities. *Core:*
  lifecycles, full replay, road segments.
- **The owner's 3D weather, smoke edition.** HRRR native-level smoke
  ray-marched as a brown volume over the terrain. Fire pixels become
  glowing columns whose height follows FRP, GOES updates them every 5
  minutes, and VIIRS night detections add an ember glow. Dense smoke and
  fog advisories lower a ground haze whose density follows 511 road-weather
  visibility. All synced to the replay clock; a 3D smoke column costs about
  20 MB of transfer per valid hour ⚠️, so budget it per event. *Sources:*
  HRRR-Smoke, GOES-18 FDC, FIRMS, NWS WWA, 511 road weather (in hand).
  *Core:* 3D engine, fields (proposed), full replay.
- **Lightning-to-ignition watch.** GOES GLM flash density in the last 48
  hours over areas in D2 or worse drought (and high ERC, if the FEMS
  account is set up) is shaded as "holdover risk". The map then shows which
  flash areas turned into FIRMS or GOES hotspots the next day, and replay
  builds a season's record of lightning-to-start lags. GLM is total
  lightning at about 8–14 km, not ground strikes, so the idea speaks of
  flashes. *Sources:* GOES-18 (GLM and FDC), Drought Monitor, FEMS (if an
  account), FIRMS. *Core:* fields (proposed), full replay.
- **Restrictions and closures timeline.** A strip in the time bar per
  restriction zone and forest order (IDL stages, USFS fire closures), so a
  viewer sees the season unfold; the Valley Feed posts each change, and
  "what was in force at this moment" answers it for any past date. IDL's
  service keeps only the current stage, so the timeline exists only from
  our first poll: the 2026 season's Treasure Valley rescission (Sept 3) is
  confirmed, but its Stage 1 start (Aug 7 in the research) is unverified ⚠️.
  *Sources:* IDL restrictions, USFS forest orders. *Core:* lifecycles,
  Valley Feed, full replay.

### Commuter

- **Fire or smoke on my route.** When a fire or a cluster of hotspots
  comes within 2 km of I-84, US-95, SH-55, SH-21, SH-16 or SH-44, the
  Valley Feed posts it next to any matching 511 closure. The post shows the
  nearest calibrated cameras whose view points toward the fire, the Dense
  Smoke Advisory if one is active, visibility readings from 511's
  road-weather stations, and HRRR's near-surface smoke forecast along the
  corridor for the next 6 hours. Fires named for mileposts ("MM65 I84",
  "MM97 I84") show how often I-84 itself is the start. *Sources:* WFIGS,
  FIRMS, NWS WWA, HRRR-Smoke, 511 road weather and camera calibrations (in
  hand). *Core:* Valley Feed, search, fields (proposed), road segments.
- **Hot bus stops.** On HeatRisk 3–4 days, stops ranked by expected
  unshaded wait (shade from NAIP and LiDAR canopy, times VRT headways), so
  riders and planners see where waits are worst; heat days also compared
  with bus-derived speeds and on-time performance (the comparison depends
  on HeatRisk's unknown archive depth ⚠️). *Sources:* HeatRisk, VRT GTFS,
  NAIP and 3DEP canopy (in hand). *Core:* fields (proposed) or readings at
  stops.
- **Visibility band on I-84 and the connectors.** Dense Fog, Dense Smoke
  and Blowing Dust advisories, with 511 road-weather visibility and a
  camera haze index from our own calibrated key cameras (dark-channel or
  far-landmark contrast), drawn as a band along the route with a written
  category. Whether the derived camera index may be published is the
  owner's decision. *Sources:* NWS WWA, 511 road weather and the camera
  archive (in hand), NAQFC dust (HYSPLIT). *Core:* readings, road
  segments, Valley Feed.

### Traffic researcher

- **Smoke, heat and fog days against traffic.** A day-classification
  table (validated AQS PM2.5 daily means, as AirNow's guidelines require
  for analysis; HMS heavy smoke over the valley; HeatRisk 3 or more; Dense
  Fog and Smoke advisory hours from IEM since 2005) joined to COMPASS
  crashes 2008–2025, ITD counter volumes and bus-derived speeds. It answers
  "do smoke days cut volumes or raise crash rates?" and tests chapter 2's
  fog, detector-fallback and long-greens theory on the actual advisory
  hours. HeatRisk's archive depth is unknown ⚠️. *Sources:* AQS/AirData,
  HMS, HeatRisk archive, IEM, Storm Events, COMPASS crashes (in hand).
  *Core:* readings, lifecycles.
- **Dark signals in power shutoffs.** If Idaho Power agrees, PSPS areas
  overlaid with the `intersections` plugin's signals, listing which
  corridors would lose signals, with bus delay during any event (the
  "more likely" areas layer wasn't found ⚠️). Until then, red-flag days are
  only marked on the signal map, without outage data. *Sources:* Idaho
  Power PSPS (needs an OK), NWS WWA, intersections (in hand). *Core:*
  lifecycles, layer system.

### Hiker, backpacker, camper, hunter, angler, floater

- **"Campfire OK here today?"** Tap any spot to see the IDL restriction
  stage for that zone (with a link to the signed order, and when the stage
  last changed, from our own versions rather than IDL's date fields), any
  USFS forest order covering it (closure name, dates, order link), whether
  a Red Flag Warning is active, the nearest active fire and its distance,
  the current AQI (labelled preliminary) and HeatRisk. *Sources:* IDL
  restrictions, USFS forest orders, NWS WWA, WFIGS, AirNow, HeatRisk.
  *Core:* lifecycles, areas, search, layer system.
- **Burn scars on my trail.** Ridge to Rivers and Forest Service trails
  coloured where they cross old fires (MTBS severity, NIFC history back to
  1908, WFIGS since 2021). A year slider uses NAIP's near-infrared to show
  green-up after each fire. After a fire, USGS debris-flow basins above
  trails and roads (where assessed) are combined with NWS Flash Flood
  Warnings. *Sources:* MTBS, NIFC perimeter history, WFIGS, USGS
  debris-flow assessments, NWS WWA, NAIP (in hand). *Core:* layer system,
  full replay (year slider).
- **River and Greenbelt flood watch.** Gauges drawn as dials with flood
  bands (Glenwood: action 6,500 cfs, minor 7,000, moderate 11,000, major
  15,000) and their forecast hydrographs. Flood Warnings appear as
  polygons, FEMA flood zones along the Greenbelt are shaded, and historic
  crests (2017: 9,590 cfs; 1983: 9,840 cfs) are pinned to the time-series
  card. Forecast runs are kept, so replay shows what was forecast against
  what happened. *Sources:* NWPS, NWS WWA, FEMA NFHL (manual), IEM.
  *Core:* readings (with forecast runs), time-series card, Valley Feed.

### Cyclist and pedestrian

- **Ride window.** For a chosen Greenbelt or road ride, an hour-by-hour
  strip for today: AQI now (AirNow) and DEQ's forecast, HRRR or NAQFC
  near-surface smoke, HeatRisk, and wind from 511 road-weather stations.
  Categories are written out (e.g. "Moderate 70"), never shown by colour
  alone, and Greenbelt sections inside an NWPS high-flow band are flagged.
  The research proposed picking the best 2-hour window, but AirNow's
  guidelines bar its data from acting "as guidance", so that pick needs the
  owner's judgement; the safer form shows DEQ's forecast unaltered and
  AirNow values labelled preliminary, without our own recommendation.
  *Sources:* AirNow, HRRR-Smoke, NAQFC/NDGD, HeatRisk, NWPS, 511 road
  weather (in hand). *Core:* readings, fields (proposed), search (routes).

### Neighbor and civic

- **Alerts that touched my neighborhood.** A timeline per neighborhood or
  tract of NWS warnings (IEM since 2005) and IPAWS alerts since 2012, plus
  nearby earthquakes, with counts by type. A civic view adds new building
  permits inside FEMA flood zones and high wildfire-hazard areas,
  aggregated by tract. *Sources:* IEM, IPAWS, USGS earthquakes, FEMA NFHL
  (manual), Wildfire Risk to Communities, COMPASS permits (in hand).
  *Core:* areas, lifecycles, search.

### Homeowner or land buyer (private)

- **Hazard sheet** for the owner's own address or a property under
  consideration, kept in a private plugin and never tiled: FEMA flood zone
  and base flood elevation, wildfire burn probability and risk to
  potential structures, fires within 5 km since 1908 and ignitions since
  1992 by cause, the PSPS area (if Idaho Power allows), last summer's
  HeatRisk days and smoke days, and distance to the nearest mapped fault
  (no fault database has been checked ⚠️). *Sources:* FEMA NFHL (manual),
  Wildfire Risk to Communities, NIFC perimeter history, FPA FOD, HeatRisk,
  HMS, Idaho Power PSPS (if allowed). *Core:* private plugins, search
  (address), layer system.

### Gardener

- **Garden hazard calendar** for the owner's own yard: heat days
  (HeatRisk), smoke days (HMS and AirNow) and the weekly drought class
  (Drought Monitor). The research also proposed an "ordinance threshold"
  marker on days when the AQI reaches the level at which Ada County bans
  open burning (for yard debris; labelled as the threshold, not an official
  ban); the AQI-60 rule is unverified ⚠️, and AirNow's "act as guidance"
  clause makes it the owner's call. Smoke days also feed the sun-and-shade
  model as reduced sunlight (GOES AOD), so a smoky August shows fewer
  effective sun hours. *Sources:* HeatRisk, HMS, AirNow, Drought Monitor,
  GOES-18 AOD. *Core:* readings, fields (proposed), private plugins (home).

### Farmer

- **Drought and heat by crop.** Drought Monitor weekly polygons over USDA
  Cropland Data Layer fields (from the farm theme; not checked here) give
  acres of each crop in D1 or worse, by week since 2000 (statistics API)
  or from now on (polygons), with heat-stress days from HeatRisk.
  Field-burn season appears as a monthly heat map of FIRMS and HMS
  agricultural detections aggregated by township, never by farm, with a
  link to DEQ's burn decisions page (robots.txt forbids collecting it).
  *Sources:* Drought Monitor, HeatRisk, FIRMS, HMS, Cropland Data Layer.
  *Core:* layer system, areas, full replay.

### Sky watcher and photographer

- **Smoke-sunset predictor.** Along the sunset azimuth from a chosen spot,
  sum HRRR's column smoke and HMS density to rate tonight's chance of a red
  sun. The GOES aerosol-detection smoke mask plays in the time bar, and a
  "haze to the Owyhees" index comes from our own calibrated cameras (the
  contrast of a distant ridge). *Sources:* HRRR-Smoke, HMS, GOES-18 ADP,
  camera archive (in hand). *Core:* fields (proposed), 3D engine, full
  replay.

### Aviation watcher

- **Fire aviation.** Aircraft tracks from the `aircraft` plugin matched to
  WFIGS fires by proximity and fire temporary flight restrictions, giving a
  per-fire count of tanker and helicopter sorties by day from the Boise air
  tanker base. No TFR source has been catalogued yet ⚠️. HRRR's 3D smoke is
  drawn in the same scene, so aircraft are seen flying through or over the
  plume. *Sources:* WFIGS, HRRR-Smoke (3D), the aircraft plugin (adsb.lol,
  decided). *Core:* tracks, 3D engine, full replay.

### History buff

- **The valley's fires and floods on a year slider.** Perimeters from
  1908 to today, ignitions 1992–2024 by cause, Storm Events since 1950
  (floods, dust storms, heat, dense smoke), and the Boise River's historic
  crests (1983, 1998 and 2017 confirmed; 2006 and 2012 unverified ⚠️).
  Subdivisions from the NAIP year slider creep toward old burn scars,
  showing the WUI's growth. *Sources:* NIFC perimeter history, WFIGS, FPA
  FOD, MTBS, Storm Events, NWPS crests. *Core:* full replay (year slider),
  layer system, search.

### Wildlife

- **Burned winter range.** Fire perimeters and MTBS severity over mule
  deer winter range, giving acres burned per year and green-up from NAIP
  near-infrared, with the highway crossings next to them. Aggregates only,
  and no sensitive sites (nests, dens, leks). *Sources:* MTBS, NIFC
  perimeter history, WFIGS, NAIP (in hand), a winter range layer (wildlife
  theme). *Core:* layer system, full replay (year slider), areas.

### Household (private)

- **The owner's own air sensor**, read on the home network (not through
  PurpleAir's API), compared with the nearest AirNow site, both written as
  AQI category and number. It flags local smoke, such as neighbourhood
  wood stoves, against regional wildfire smoke when the two diverge.
  *Sources:* AirNow, the owner's own sensor. *Core:* private plugins,
  readings, time-series card.

---

## Design notes (proposals for the owner)

These are the research's proposals, with the verification's corrections
applied; nothing here is decided. The corrections themselves are listed
[at the end](#what-the-verification-changed).

### Plugin shape

[Chapter 15](../15-plugins.md)'s rule is one plugin per subject, with
storage-heavy parts able to switch off on their own. Proposed:

- **`hazards`** (public): fire incidents, perimeters and history,
  hotspots (FIRMS, HMS points), smoke polygons, IDL restrictions, USFS
  orders, NWS alerts plus IEM history, IPAWS history, earthquakes, the
  Drought Monitor and Storm Events. All small and keyless, and mostly
  parseable with the standard library (ArcGIS JSON, CSV, KML through
  `xml.etree`, GeoJSON).
- **`air`** (public): AirNow files, AQS and AirData. It could live inside
  `hazards`, but AirNow's guideline duties (the preliminary label, no
  altering, notifying the agencies) argue for one place to enforce them.
- **Gridded models and satellite fields** (HRRR-Smoke, NAQFC, GOES
  FDC/ADP/AOD/GLM, HeatRisk rasters) belong with the coming `weather`
  plugin and the 3D weather work, since they share decoders, storage and
  the WebGL volume renderer.
- **River gauges:** `water` owns NWPS; `hazards` reads it for flood
  alerts.
- **Manual loads** (kind `manual`): FEMA NFHL county zips, MTBS, FPA FOD,
  Wildfire Risk to Communities, and NIFC perimeter history as a backfill.
- **Dependencies:** `hazards` depends on `roads` (fire-near-road joins,
  egress) and reads `conditions` (511 closures, road-weather visibility);
  `intersections` for signals in PSPS areas.

### Time shapes

Most of this fits the three core contracts
([ch. 15 §15.1](../15-plugins.md#151-whats-core)):

- **Lifecycles (`evt.event`):**
  - WFIGS incidents: start at `FireDiscoveryDateTime`; containment and
    control as state changes; close only on `FireOutDateTime`. Read them
    from the all-years service (or year-to-date), since `_Current` drops
    contained fires and applies fall-off rules; a fire disappearing from
    `_Current` must never close a lifecycle.
  - IDL zone stages: from our own versions; `DateEnacted` and
    `DateRescinded` don't give a restriction's start and end.
  - USFS orders (start, end, rescind dates), grouped by `ordernum`.
  - NWS alerts (onset, ends, expiration), keyed by VTEC: office, phenomenon,
    significance, event tracking number and year.
  - IPAWS (effective, expires); HMS smoke polygons (start and end per
    polygon); Drought Monitor weekly categories.
- **Versioned geometry.** Perimeters change shape over time, and every
  changed polygon is a version in `raw.record`. Suggested: a small
  `evt.event_geometry` history (event ID, valid from, geometry, mapping
  method, acres), so replay draws the perimeter as known at time t. Lanes,
  aircraft and trails may want the same pattern, which argues for core.
- **Readings:** AirNow hourly per site, NWPS stage and flow per gauge,
  quake magnitudes (or zero-length lifecycles). FIRMS and GOES detections
  are instantaneous point observations with FRP, close to readings without
  a fixed station. Suggested: a "detections" variant (time, point or pixel
  footprint, sensor, value).
- **Missing shape: fields.** Gridded fields over time (HRRR, NAQFC, GOES
  products, HeatRisk, and later MRMS and radar for 3D weather) need a
  fourth contract: run time, valid time, variable, level, and ring-cropped
  tiles or arrays. Keeping the forecast's run time lets replay show "what
  was forecast then" as well as "what happened". Core owns the time
  contracts, so this is the owner's decision, shared with the 3D weather
  work.

### Ingest cadence and politeness

All through `ingest/http.py` (robots.txt checked on every request, our
honest User-Agent, versions only on change):

| Cadence | Sources |
|---|---|
| 5 min | WFIGS all-years (or year-to-date) incidents and perimeters, ring envelope, absolute `ModifiedOnDateTime_dt` filter; NWS WWA map service (envelope query, not the national tarballs); USGS quake feed |
| 30–60 min | FIRMS keyless CSVs (ring rows; Crawl-delay 1; dedupe by content); AirNow `HourlyAQObs` at about :40, plus a few lagged hours (e.g. t−24 h and t−72 h) for the 72-hour revisions; `reportingarea.dat` at :30 and :00; IDL restrictions; NWPS gauges (15–30 min in flood season) |
| Daily | HMS (after the 12:00 and 20:00 ET analyses; the next-morning file is final); USFS orders (several a day in fire season); HeatRisk |
| Weekly | Drought Monitor (Thursday) |
| Monthly | Storm Events |
| Yearly zips | IEM (Crawl-delay 120) |
| One-offs | MTBS, FPA FOD, Wildfire Risk to Communities, NIFC history, NFHL (manual), IPAWS backfill (filtered to Idaho or the ring) |
| Gridded, after the decisions below | GOES `FDCC` every 5 min, keeping ring fire pixels only; HRRR analysis hourly plus a 48-hour run four times a day, smoke and visibility only, fetched by `.idx` byte range |

A 5xx from a data query is an ordinary failed fetch, retried with backoff;
only a 5xx or network error on robots.txt itself means "disallow for now".

### Processing

Python is standard-library only by project rule. That covers JSON, CSV,
KML and SQLite (FPA FOD ships as SQLite). It doesn't cover GOES
NetCDF4/HDF5, HRRR and NAQFC GRIB2, the NFHL and MTBS shapefiles and
geodatabases, or the Wildfire Risk GeoTIFFs. Options for the owner:

1. A separate "grids" image with wgrib2 and GDAL binaries called as
   subprocesses, which keeps Python stdlib-only. The basemap builds use
   GDAL, but they ran off the server, which has no GDAL today
   ([deploy/README](../../deploy/README.md)). So this is a new server-side
   install that needs the owner's explicit approval, and its CPU and memory
   needs should be checked against the server's limits (private notes).
2. Allow numpy, h5py or eccodes in that one image.
3. Use NOAA's ImageServer `identify` and `exportImage` endpoints (NDGD,
   HeatRisk) to avoid decoding at all, at the cost of depending on a live
   service.

The research recommends option 1 for files and option 3 where an
ImageServer exists. Ring crops would be stored as small arrays or PNG/WebP
tiles, like the terrain tiles.

### Storage (estimates)

- Phase 1 live sources, archiving ring subsets only: well under 20 MB a
  day. Raw files would be much more: national FIRMS CSVs every hour about
  10–15 MB a day for four sensors, and `reportingarea.dat` every half hour
  about 80 MB a day. So archive ring rows, not raw files.
- GOES fire pixels in the ring: KB a day (about 80 MB a day of transfer).
- HRRR smoke and visibility for the ring: about 5–20 MB a day stored ⚠️;
  about 55 MB a day of transfer for hourly analyses, 0.45 GB a day for
  four 48-hour runs. A 3D smoke column is about 20 MB per valid hour ⚠️:
  budget it per event.
- One-off backfills: about 1–3 GB stored, mostly the Wildfire Risk
  rasters and MTBS severity. The Idaho Wildfire Risk download itself is
  about 6.6 GB ⚠️ before cropping.

### Traffic ties

- Spatial joins of fires and hotspot clusters to road segments within
  2 km (state routes first), and to 511 events by time and place.
- Restriction zones and forest orders mark closed forest roads in the
  `roads` layer.
- Smoke and fog: WWA advisory polygons, 511 road-weather visibility
  (`obs.weather_reading.visibility` already exists), HRRR visibility and
  near-surface smoke, and a camera haze index from our calibrated key
  cameras.
- Evacuations: IPAWS polygons with our lanes and speeds give egress
  capacity (where a polygon exists).
- Dark signals: PSPS areas, if Idaho Power allows.
- Research: smoke, heat and fog day classes against crashes, counts and
  bus speeds, using validated AQS for trend analysis, as AirNow requires.

### Rendering

Following [chapter 13](../13-visual-design.md)'s tokens:

- Hotspots as pixel squares at the true footprint (375 m for VIIRS, about
  2 km for GOES), with a glow fading by age.
- Perimeters with a hatched fill and a containment ring.
- Smoke as translucent density layers.
- AQI and HeatRisk use mandated or conventional colour scales that include
  red and green, so every display also shows the category word and number
  (our rule: never red or green alone). AirNow's guidelines require the AQI
  colours, so they aren't changed.
- 3D: HRRR native-level smoke ray-marched as a volume; fire columns scaled
  by FRP; ground haze from visibility. It's the same machinery as the
  owner's 3D clouds and fog ([ch. 16 §16.5](../16-ideas-and-personas.md#165-weather-in-3d-the-owners-idea-oct-7)),
  so build it once.

### Replay

- "What was active at t" for lifecycles; readings drawn up to t; fields at
  the nearest valid time.
- For forecasts, use the run that existed at t, unless the viewer chooses
  "best hindsight".
- Fires before our collection began can still be replayed from FIRMS
  archives (MAP_KEY or Earthdata Login), the GOES NODD archive (from May
  2022; GOES-17 before that), HMS, IEM (first polygons only) and IPAWS.
  511 and WZDx closures exist only from Oct 6, 2026.

### Licensing and republishing

- **Federal public domain, credit only:** NIFC/WFIGS (disclaimer; the
  perimeter history's "strategic use only" disclaimer travels with it),
  FIRMS (credit NASA FIRMS), HMS, GOES, HRRR, NAQFC, MTBS, FPA FOD,
  Wildfire Risk to Communities (cite), USFS orders, NWS, NWPS, USGS, NCEI
  Storm Events.
- **IEM:** NWS products redistributed by IEM; credit IEM.
- **OpenFEMA/IPAWS:** the required statement.
- **Republish with conditions:**
  - AirNow: the preliminary label, credit DEQ and AirNow, no altering, the
    AQI colours, tell DEQ and AirNow, and not "as guidance".
  - Drought Monitor: the credit text.
  - IDL: no license stated, so credit IDL and send a courtesy note.
- **No:** PurpleAir.
- **Link only:** InciWeb, NGFS, DEQ burn decisions, smoke outlooks, and
  the full alert text on `api.weather.gov`.

### Ethics (road network and nature, not people)

- IPAWS: drop AMBER (CAE), Blue (BLU), law-enforcement (LEW) and
  missing-and-endangered-person (MEP ⚠️) alerts at ingest. For
  civil-danger and local-emergency alerts (CDW, LAE), keep only event, time
  and area, never the description.
- FIRMS: draw hotspots as pixels, never "structure fire at address"
  alerts; filter or label static industrial sources.
- Agricultural burns: aggregate by township.
- Storm Events: keep counts, not narratives about individuals.
- Hazard sheets per parcel only for the owner's own place, in a private
  plugin.
- Evacuation views are about roads and capacity, never people's movement.
- Aircraft over fires follow the `aircraft` plugin's privacy rules.

### robots.txt findings that change plans

robots.txt disallows us at `api.weather.gov`, `api.waterdata.usgs.gov`
(data endpoints), `hazards.fema.gov` (`/arcgis`) and MSC product downloads,
both InciWeb hosts, `fire.data.nesdis.noaa.gov` (NGFS), `www.spc.noaa.gov`,
`droughtmonitor.unl.edu/data/`, DEQ's `/air/crb/` and `api.purpleair.com`.
A robots-allowed alternative exists for each except InciWeb, NGFS, DEQ's
burn decisions and PurpleAir. Found in the verification:

- `www.usgs.gov` timed out twice, so it's "disallow for now" from the
  research network, and `landslides.usgs.gov` redirects to it.
- `nomads.ncep.noaa.gov` answers 404 (allowed; it has its own usage limits
  ⚠️).
- `services5.arcgis.com` answers 403 (allowed).
- Idaho's state GIS hosts (`gis1.idl`, `gis.idwr`) redirect robots.txt to
  `error.idaho.gov`; our parser treats that HTML as no rules.

### Suggested phases

1. **Cheap, keyless and stdlib:** WFIGS, FIRMS keyless CSVs, HMS (KML),
   IDL, USFS orders, NWS WWA, AirNow files, NWPS, quakes, the Drought
   Monitor, with the Valley Feed and the fire board.
2. **History:** NIFC perimeter history, MTBS, FPA FOD, IEM, Storm Events,
   IPAWS, AirData, NFHL (manual), Wildfire Risk to Communities.
3. **After the decoder and "fields" decisions:** GOES FDC, ADP and GLM,
   HRRR-Smoke including 3D, NAQFC, HeatRisk rasters, then the 3D smoke
   renderer.

### What the verification changed

The Oct 7 verification corrected these points in the research's design,
ideas and questions (all applied above):

1. **WFIGS polling:** `_Current` leaves out contained, controlled and out
   fires, so poll the all-years (or year-to-date) services with an
   absolute `ModifiedOnDateTime_dt` filter and close lifecycles only on
   `FireOutDateTime`. History starts in 2014, not 2008; Jump and Bulldog
   were missing from the largest fires.
2. **No 2020 perimeter gap:** the 2020s view covers 2020–2024, so MTBS
   isn't needed for one; the history views carry their own "strategic use
   only" disclaimer; dedupe 2021–2024 against WFIGS.
3. **IDL stages** come from our own versions, not `DateEnacted` and
   `DateRescinded`; "Stage 1 on Aug 7, 2026" is unverified.
4. **NWS WWA:** `event` is the VTEC tracking number; key lifecycles on
   VTEC, not `cap_id`; never fetch the `url` field; the tgftp files are
   national 9 MB tarballs; the 5-minute refresh isn't documented.
5. **HRRR and RRFS:** RRFS goes live Nov 3, 2026 (NOMADS parallel since
   Aug 12; not yet on NODD) and doesn't replace HRRR; no HRRR freeze or
   retirement was found. Message and file sizes corrected; transfer is the
   real cost.
6. **GOES:** about 80 MB a day of `FDCC` transfer; the NODD archive starts
   May 11, 2022 (GOES-17 for 2018–2022); the switch dates look a few days
   off ⚠️; GLM is total lightning, so speak of flash density; filter GLM's
   20-second files on ingest; a narrow fire-mask filter misses real fires
   ⚠️.
7. **AirNow:** the "act as guidance" clause puts the ride window and the
   burn-threshold marker to the owner; AQI colours are mandated; re-fetch
   lagged hours for the 72-hour revisions; a raw `reportingarea.dat`
   archive would be about 80 MB a day.
8. **HMS:** daily national smoke KMLs are 60–450 KB; the archived file is
   final the next morning.
9. **FIRMS:** standard data lag 2–3 months; back-dated replay needs the
   MAP_KEY or an Earthdata Login (owner actions); dedupe the hourly
   rewrites by content.
10. **Drought Monitor:** the archive service is in NDMC's own ArcGIS org
    and robots-allowed; its time extent ends 2020-11-17 ⚠️; prefer it to
    FEMA's mirror.
11. **NFHL coverage:** digital FIRMs for Ada, Canyon, Gem, Valley and
    Washington; paper for Boise, Elmore and Payette; none for Owyhee;
    Adams is outside the ring; Malheur, Oregon, is outside IDWR's layer.
12. **Processing:** GDAL isn't on the server; a "grids" image is a new
    server-side install needing the owner's explicit approval.
13. **robots.txt wording:** a 5xx on a data query isn't a robots result;
    the state GIS redirects and the new USGS, NOMADS and services5 findings
    were added.
14. **IPAWS ethics:** drop MEP alerts too; keep only event, time and area
    for CDW and LAE; the egress analysis works only where a polygon exists;
    the keyless API's newest record was about 24.4 hours old, matching the
    stated delay.
15. **IEM** keeps only the initial storm-based polygon, so replay shows
    warnings as first issued.
16. **Unsourced or unverified inputs in the ideas:** fire temporary flight
    restrictions (no TFR source catalogued); distance to the nearest mapped
    fault (no fault database checked); the Cropland Data Layer (another
    theme); the 2006 and 2012 Boise River crests; Ada County's AQI-60 burn
    rule; HeatRisk's archive depth.
17. **Genasys:** Ada County's alert sign-up runs on Genasys, so the
    question becomes one for Ada County Emergency Management.
18. **USGS water:** WaterServices is decommissioned in Q1 2027, with
    Campaign 3 blackouts from Nov 2026 to Feb 2027; plan on NWPS for
    forecast points now.

---

## Open questions

For the owner, one at a time:

1. **NWS alerts:** `api.weather.gov`'s robots.txt is `User-agent: *` /
   `Disallow: /`, though the NWS documents the API for programs. Keep to
   robots.txt and use the WWA map service (with the tgftp tarballs only
   for occasional checks), or ask the NWS first?
2. **USGS gauges:** the new Water Data API disallows every data endpoint
   in robots.txt, and the allowed legacy WaterServices will be
   decommissioned in the first quarter of 2027 (with Campaign 3 blackouts
   from Nov 2026 to Feb 2027). Rely on NWPS at forecast points, ask USGS,
   or use the legacy service until it goes?
3. **FEMA NFHL:** `hazards.fema.gov/arcgis` and MSC scripted downloads are
   both disallowed. Will the owner download the Ada (16001) and Canyon
   (16027) NFHL zips by hand (a `manual` source like Geofabrik), or should
   we use Ada County's `FEMA_Layers` "dev" map service for Ada only?
   Disclosure: one research request reached `hazards.fema.gov/arcgis`
   before its robots.txt was read; it won't be repeated.
4. **Decoding gridded data** (GOES NetCDF4/HDF5, HRRR and NAQFC GRIB2,
   GeoTIFFs, shapefiles and geodatabases) breaks the stdlib-only rule.
   A separate image calling wgrib2 and GDAL binaries (a new install on the
   server, which needs explicit approval), numpy, h5py or eccodes in that
   image, or NOAA ImageServer endpoints only?
5. **Core time shapes:** should core gain a fourth shape, "fields"
   (gridded time series with run and valid time), shared with the 3D
   weather work, and a versioned geometry history for fire perimeters (and
   later lanes or trails)?
6. **Plugin split:** one `hazards` plugin, or `hazards` plus `air`, with
   gridded models in `weather` and gauges in `water`?
7. **AirNow "guidance":** the guidelines bar using AirNow data to "act as
   guidance". Should the ride window's best-window pick and the
   burn-threshold marker be dropped, or kept with DEQ's forecast shown
   unaltered beside them?
8. **Owner actions to approve:** optional free keys (a FIRMS MAP_KEY, an
   EPA AQS key, an AirNow API key; an Earthdata Login for FIRMS's
   archive). Required for AirNow: returning the Data Exchange Guidelines
   form to dmc@airnowtech.org and telling Idaho DEQ how we use its data. A
   FEMS account with the API role, for fire danger (ERC, burning index).
9. **Courtesy notes:** to IDL about republishing restriction stages (no
   license stated); to Idaho Power asking whether we may use their PSPS
   area layers; to DEQ asking whether a crop-residue burn-decision feed
   exists (their robots.txt disallows `/air/crb/`).
10. **Evacuation zones:** Ada County's alert sign-up runs on Genasys. Ask
    Ada County Emergency Management whether its zones are on Genasys
    Protect and whether a data-sharing agreement is possible, and use
    IPAWS for history meanwhile?
11. **IPAWS policy:** drop AMBER (CAE), Blue (BLU), law-enforcement (LEW)
    and missing-person (MEP ⚠️) alerts entirely at ingest, never storing
    their text, and keep only event, time and area for CDW and LAE? The
    research recommends it.
12. **Camera haze index:** it's a visibility metric derived from 511/ACHD
    camera frames. May it be shown publicly, given that the images
    themselves aren't republished?
13. **AQI and HeatRisk colours** are mandated or conventional and include
    red and green. Keep them while always adding the category word and
    number, under the "never red or green alone" rule?
14. **Download sizes for one-off backfills:** the Wildfire Risk to
    Communities Idaho package (6.56 GB ⚠️), MTBS perimeters and severity
    for the ring (hundreds of MB ⚠️) and the FPA FOD SQLite file (220 MB).
15. **HRRR and RRFS:** RRFS v1 goes live Nov 3, 2026 (on NOMADS only so
    far, with no smoke or dust mentioned), and HRRR isn't being retired.
    Keep HRRR from NODD, and revisit once RRFS reaches NODD and its smoke
    fields are confirmed?
