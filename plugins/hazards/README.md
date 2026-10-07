# hazards

Fire and hazards around the valley: fire-restriction stages, wildfire incidents
and perimeters, satellite hotspots, NWS watches, warnings and advisories, and
earthquakes. This is the "start the clocks" part of
[ch. 17 §17.4](../../docs/17-sources-for-new-plugins.md#174-proposed-order-with-rough-effort)
(Wave A): each of these sources keeps only its current state, so history exists
only from the day we start polling. Ingest only for now; no map layers yet.
Persona and source choices:
[ch. 17 §17.2, Fire and hazards](../../docs/17-sources-for-new-plugins.md#fire-and-hazards).

Everything goes into core's tables (ch. 17 Q8): every record version into
`raw.record`, and lifecycles (restriction stages, fires, perimeters, alerts)
into `evt.event` through `ingest/events.py`. Hotspots and quakes are
occurrences, so they're in `raw.record` only. No migrations. Everything is cut
to the regional ring (west −117.30, south 42.90, east −115.60, north 44.30, as
in the catalogs; proposed in [DECISIONS](../../docs/DECISIONS.md)).

| Source | Runs | License | Credit | Republish |
|---|---|---|---|---|
| `idl_fire_restrictions` | hourly | none stated | Idaho Department of Lands and the Idaho Fire Restrictions Plan partners | internal, until IDL answers a courtesy note (Q17) |
| `nifc_wfigs_incidents` | every 10 min | none stated (NIFC disclaimer only) | National Interagency Fire Center (WFIGS), from IRWIN | yes |
| `nifc_wfigs_perimeters` | every 15 min | none stated (NIFC disclaimer only) | National Interagency Fire Center (WFIGS), from IRWIN | yes |
| `nasa_firms` | hourly | NASA open data | NASA FIRMS (LANCE/ESDIS) | yes, as pixel footprints |
| `nws_wwa` | every 10 min | public domain | NOAA National Weather Service | yes |
| `usgs_quakes` | hourly | public domain | U.S. Geological Survey, Earthquake Hazards Program | yes |

## Sources

**`idl_fire_restrictions`**: IDL's Fire Restriction Zones, layer 1 of
`https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer`
([hazards catalog](../../docs/sources/hazards.md#idaho-department-of-lands-fire-restriction-areas-and-zones),
[lands catalog](../../docs/sources/lands.md#idaho-fire-restrictions-interagency-stage-map)).
Stage (None, Stage I, Stage II), DateEnacted, DateRescinded, UpcomingStage per
zone; six zones touch the ring (all at None on Oct 7, 2026). Hourly, one
attributes-only read (about 5 KB); the outlines (about 850 KB) are read only
when a zone changed. Kept: one versioned record per zone (GlobalID), without
`last_edited_user` or the shape statistics, as a full snapshot refused below
half the zones we hold; a lifecycle per stage in force (zone, stage and
DateEnacted), closed when the zone goes back to None, and one per announced
UpcomingStage. robots.txt redirects to an HTML error page: no rules.

**`nifc_wfigs_incidents`**: the all-years incident service,
`https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Incident_Locations/FeatureServer/0`
([catalog](../../docs/sources/hazards.md#nifc-wfigs-fire-incidents-and-perimeters)).
`_Current` drops fires once they're contained, so we read every record changed
since an absolute time (`ModifiedOnDateTime_dt >= TIMESTAMP '…'`, the newest we
hold less two hours, floored to the hour; NIFC asks for no relative dates). The
first run reads the year so far. Kept: every version of every record (IrwinID),
and one lifecycle per fire from discovery to out. It stays open through
containment and closes when the fire is declared out, withdrawn, or its record
goes quiet past NIFC's own fall-off window (3, 8 or 14 days by size); a later
update reopens it. A fire first seen already out is kept in `raw.record` only.
robots.txt: 403, no rules.

**`nifc_wfigs_perimeters`**: the all-years perimeter service,
`…/WFIGS_Interagency_Perimeters/FeatureServer/0`, read the same way on
`attr_ModifiedOnDateTime_dt` or `poly_DateCurrent`. Kept: every perimeter
version per fire (poly_IRWINID; a final perimeter wins over a daily one in the
same read), geometry at about a metre, multipart fires as MultiPolygons; the
current perimeter as a lifecycle with the incidents' rules.

**`nasa_firms`**: the keyless 24-hour contiguous-US files under
`https://firms.modaps.eosdis.nasa.gov/data/active_fire/`: VIIRS on NOAA-20,
NOAA-21 and Suomi NPP, and MODIS
([catalog](../../docs/sources/hazards.md#nasa-firms-active-fire-detections)).
All four paths confirmed Oct 7, 2026; about 200 KB each, rewritten hourly.
Kept: the ring's rows, one record per detection (sensor, satellite, time and
position), every column typed. A file that fails is reported and the rest
stored. robots.txt allows it, Crawl-delay 1 (honored); 2 s between files.

**`nws_wwa`**: layer 1 (WatchesWarnings, all 111 product types) of
`https://mapservices.weather.noaa.gov/eventdriven/rest/services/WWA/watch_warn_adv/MapServer`
([catalog](../../docs/sources/hazards.md#nws-watches-warnings-and-advisories-map-service)),
not api.weather.gov, whose robots.txt disallows everything (Q13). One query of
the ring a run. Alerts are grouped by VTEC event (office, phenomenon,
significance, ETN, year); cap_id, objectid and the idp_ times change on every
update or reload and aren't keys. Kept: one record per event (its products and
merged area) as a full snapshot, and one lifecycle per event from onset to end.
If an unexpired alert vanishes, the layer is read again after 30 s, since NWS
reloads it every few minutes. The `url` field (api.weather.gov) is never
fetched. robots.txt redirects to an HTML page: no rules.

**`usgs_quakes`**: the all-magnitude past-week summary feed,
`https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson`
([catalog](../../docs/sources/hazards.md#usgs-earthquake-feeds-and-fdsn-event-service-comcat)),
hourly, so a week of revisions is seen. Kept: the ring's events, one record per
event with each revision a version, without the links and title, point in 2D
with the depth in the payload; an event keeps its first ID when USGS changes
the preferred one. robots.txt: 404, no rules.

**Storage:** under 1 MB a day typical, a few MB on a busy fire day (perimeter
versions are 10–100 KB). About 60 MB a day of transfer before gzip, mostly FIRMS and the
USGS week feed, cut to the ring before storing.

**Commands:**

```bash
python3 -m ingest run idl_fire_restrictions nifc_wfigs_incidents nifc_wfigs_perimeters nasa_firms nws_wwa usgs_quakes
python3 -m ingest serve                      # runs them on their schedules with everything else
python3 -m unittest discover -s plugins/hazards/tests -t .
```

**Ethics:** road network and nature, not people. NWS alerts about people (Child
Abduction Emergency, Blue Alert, Law Enforcement Warning, Missing and
Endangered Person) are dropped before anything is stored. FIRMS hotspots are
375 m or 1 km pixels: draw footprints, never pins on houses, and never build
structure-fire alerts. WFIGS cause fields give a class, never a person. IDL
states no license: internal and credited until IDL answers a courtesy note.

**Known data quirks:** some outlines are invalid as published (self-
intersecting slivers in two IDL zones, a zero-area ring in a WFIGS perimeter,
Oct 7, 2026). They're stored as published; use `ST_MakeValid` before joins.
