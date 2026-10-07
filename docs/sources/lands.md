# Lands sources (researched Oct 7, 2026)

Who owns and manages each piece of land in Ada and Canyon counties and the
regional ring, whether the public may enter it, which vehicles may use
which routes and when, and the rules laid over it: closures, fire
restrictions, hunting units and seasons, grazing allotments, mining claims,
access easements and special designations. It serves the proposed `lands`
plugin ([ch. 15 §15.7](../15-plugins.md#157-ideas-for-later-plugins), next
after `aircraft` in [§15.6](../15-plugins.md#156-refactor-plan)) and the
hiker, camper, hunter and angler persona in
[ch. 16](../16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water).
Parcel sources belong to the private `parcels` plugin
([ch. 16](../16-ideas-and-personas.md#homeowner-or-land-buyer-private-with-parcels)).
The overview of every theme is in
[chapter 17](../17-sources-for-new-plugins.md); the ideas across all themes
are in [chapter 16](../16-ideas-and-personas.md).

**Status: research only; nothing here is approved.** Sources go to the
owner one at a time ([CLAUDE.md](../../CLAUDE.md)). The research pass ran
on Oct 7; the same day a verifier re-read each entry's official pages,
ArcGIS REST metadata, robots.txt and terms. Of the 22 entries, 12 were
confirmed, 9 corrected and 1 couldn't be verified (Idaho Parks and
Recreation's boundary service, whose host didn't answer). No entry was
refuted, though one claim inside an entry was: the research found no BLM
wilderness study area in the ring, and there are four, in Oregon. Each
entry gives its result, and the text below is the corrected version.

**Requests made.** The research pass made small metadata, count and point
queries to the agencies' map services (the ring counts in
[design note 4](#design-notes) and point checks at Lucky Peak and Lake
Lowell). The verifier made a few small attribute-only queries to
`gis.blm.gov` (GTLF statistics over the ring, wilderness and WSA counts,
and Idaho SMA and GTLF counts in an Oregon box), one IDL fire-zone query,
and Federal Register API lookups for the Roadless Rule. It fetched
ScienceBase's PAD-US item page once before reading that host's
robots.txt, which turned out to block all bots and Claude-named agents,
and made no further requests there. Web search ran out partway through,
so some items stay marked ⚠️. Neither pass reports creating an account or
downloading a dataset.

How to read this page:

- **Verdicts:** **use** (fits our rules as described), **internal only**
  (owner only, or aggregates in anything shared, until the publisher
  answers), **needs owner action** (a check, request or by-hand step comes
  first), **avoid**.
- **Effort** (S, M, L) is the researcher's rough size of the work;
  **confidence** (high, medium, low) is the research's.
- **Needs from core** names the core pieces from
  [ch. 15 §15.1](../15-plugins.md#151-whats-core): the layer system,
  lifecycles, evidence and review, areas, places and search, the Valley
  Feed, the time and replay clock, selection and picking, private plugins,
  the 3D engine and the app shell. "A regular OpenStreetMap load" means a
  repeatable one; today OpenStreetMap is loaded by hand only
  ([SOURCES](../SOURCES.md#openstreetmap-first-load-oct-7)).
- **The ring** is the regional ring proposed in
  [DECISIONS](../DECISIONS.md) (about 117.30°W to 115.60°W, 42.90°N to
  44.30°N). It includes a strip of Malheur County, Oregon (Ontario, Nyssa,
  Vale, Lake Owyhee, Leslie Gulch, Succor Creek) where Idaho-only sources
  return nothing ([correction 1](#design-corrections-from-verification)).
  "The valley box" is the Ada and Canyon box.
- **robots.txt** results follow CLAUDE.md: a 4xx means no rules; a 5xx or
  a network error means disallow for now.

---

## Summary

| Source | Publisher | What it gives | Access | Key or account | License or terms | robots.txt | Verdict | Verified |
|---|---|---|---|---|---|---|---|---|
| [PAD-US 4.1](https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-download) | USGS Gap Analysis Project | Every public and protected parcel: owner, manager, designation, public-access code; easements | File download by hand (Idaho 150 MB, Oregon 291 MB); ArcGIS web views; a GeoParquet re-host | None | Public domain; cite the DOI | ScienceBase: the operator blocks all bots (hand download only); ArcGIS 403, no rules | use | corrected |
| [BLM Surface Management Agency](https://gis.blm.gov/idarcgis/rest/services/lands/BLM_ID_Surface_Management_Agency/FeatureServer) | BLM Idaho (national layer: BLM HQ) | Surface manager polygons (not owner) | FeatureServer | None | Federal work, "PUBLIC"; not legal documents | 404, no rules | use | corrected |
| [IDL State Ownership](https://services2.arcgis.com/1cvrwLhZRFh3okEF/arcgis/rest/services/State_Ownership/FeatureServer) | Idaho Department of Lands | State endowment and other state land, surface and subsurface, with beneficiary | FeatureServer | None | None stated; credit IDL | 403, no rules; hub Crawl-delay 60 | use | corrected |
| [USFWS refuge boundaries](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer/0) | US Fish and Wildlife Service, Division of Realty | National wildlife refuge boundaries (Deer Flat) | FeatureServer | None | Federal work; credit FWS Realty | 403, no rules | use | confirmed |
| [USFS boundaries and designations](https://data.fs.usda.gov/geodata/edw/datasets.php) | USDA Forest Service (EDW) | Forests, districts, Idaho Roadless areas, wilderness, ownership, MAPLand easements, allotments, trails | MapServers; clearinghouse zips | None | Public domain; not legal documents | 403 and 404, no rules | use | corrected |
| [IDPR state park boundaries](https://gis2.idaho.gov/arcgis/rest/services/DPR/IDPR_State_Parks/MapServer) | Idaho Parks and Recreation | State park boundaries | MapServer (host unreachable) | None | Not checked | Unreachable; treated as disallow | needs owner action | unverifiable |
| [Reclamation Land Ownership](https://services1.arcgis.com/ixD30sld6F8MQ7V5/arcgis/rest/services/ReclamationLandOwnership/FeatureServer/0) | US Bureau of Reclamation | Reclamation land interests | FeatureServer | None | **Forbids downloading, republishing, derived products and dissemination** | 403, no rules | avoid | confirmed |
| [NCED](https://conservationeasement.us/) | NCED partnership | Conservation easements | Points to PAD-US | None | None stated | Unreachable; treated as disallow | avoid | confirmed |
| [Canyon County parcels and parks](https://maps.canyoncounty.id.gov/arcgisserver/rest/services/General/Canyon_County_Public_Tax_Parcels/FeatureServer/0) | Canyon County | Tax parcels (no owner names); county parks as points | FeatureServer; full data by FTP | None (FTP needs credentials) | None on the services | 404, no rules | internal only | corrected |
| [BLM Idaho GTLF](https://gis.blm.gov/idarcgis/rest/services/transportation/BLM_ID_Ground_Transportation_Linear_Features_GTLF/FeatureServer/0) | BLM Idaho | Travel-plan route designations and allowed modes | FeatureServer | None | Public domain; credit BLM Idaho | 404, no rules | use | corrected |
| [USFS MVUM](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_01/MapServer) | USDA Forest Service | Which vehicles may use which forest roads and trails, and when | MapServer; GDB downloads | None | Federal work; the printed MVUM is the legal map | 403 and 404, no rules | use | confirmed |
| [BLM access easements (PLAD, MAPLand)](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_PLAD/MapServer) | BLM HQ | Federal access rights across non-federal land | MapServer | None | Public domain | 404, no rules | use | confirmed |
| [BLM Idaho advisories and closures](https://www.blm.gov/idaho/advisories-and-closures) | BLM Idaho | Closure orders with PDF orders and maps | Web page and PDFs | None | Public domain | Allowed | use | confirmed |
| [Boise NF alerts and forest orders](https://www.fs.usda.gov/r04/boise/alerts) | USDA Forest Service, Boise NF | Closures, restrictions and stay limits, with order numbers | Web pages and PDFs | None | Public domain | Allowed | use | confirmed |
| [Idaho fire restrictions](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer) | IDL with USFS, BLM, BIA, tribes and local agencies | Current fire-restriction stage per zone | MapServer | None | None stated; credit IDL and partners | Redirects to an HTML page, no rules | use | confirmed |
| [IDFG open data](https://data-idfggis.opendata.arcgis.com/) | Idaho Fish and Game (IFWIS) | WMAs, hunting units, controlled hunts, restrictions, access sites, migration priority areas | Feature services | None | Varies by item; site Terms: personal viewing only | Hub Crawl-delay 60; services no rules | internal only | corrected |
| [IDFG Access Yes!](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hosted/Access_Yes_2026_public/FeatureServer/0) | Idaho Fish and Game | Private land open for hunting and fishing, with dates and rules | FeatureServer | None | None on the service; IDFG Terms on pages | 404, no rules | internal only | confirmed |
| [IDFG rules booklets and Hunt Planner](https://idfg.idaho.gov/rules) | Idaho Fish and Game | Seasons and rules | PDFs; interactive planner | None | Personal, non-commercial viewing only | Allowed | internal only | confirmed |
| [BLM grazing allotments and range layers](https://gis.blm.gov/arcgis/rest/services/range/BLM_Natl_Grazing_Allotment/MapServer/12) | BLM HQ and Idaho | Allotments, pastures, sheep trailing routes, range improvements | MapServer, FeatureServer | None | Public domain | 404, no rules | use | confirmed |
| [BLM mining claims (MLRS, not closed)](https://gis.blm.gov/nlsdb/rest/services/HUB/BLM_Natl_MLRS_Mining_Claims_Not_Closed/FeatureServer/0) | BLM (Mineral and Land Records System) | Active mining claims as approximate polygons | FeatureServer; hub downloads | None | Public domain | 404, no rules; `mlrs.blm.gov` disallows all but help pages | use | confirmed |
| [BLM special designations and planning](https://gis.blm.gov/idarcgis/rest/services/special_designations?f=json) | BLM Idaho and HQ | Birds of Prey NCA, WSAs, ACECs, Orchard impact areas, disposal lands, PLSS | MapServers, FeatureServers | None | Public domain | 404, no rules | use | corrected |
| [Idaho trespass, stream and open-range statutes](https://legislature.idaho.gov/statutesrules/idstat/Title6/T6CH2/SECT6-202/) | Idaho Legislature | Help text with citations (not data) | Read by hand | None | Public law text | `/statutesrules/` allowed | use | corrected |

---

## Ownership and management

### PAD-US 4.1 (Protected Areas Database of the United States)

[USGS PAD-US data download](https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-download).
USGS Gap Analysis Project. **use**, corrected; confidence high.

The national inventory of public and protected land. The full geodatabase
has five feature classes: Fee, Designation, Easement, Proclamation and
Marine. Its fields include `Category`, `Own_Type`/`Own_Name`,
`Mang_Type`/`Mang_Name`, `Des_Tp`, `Unit_Nm`, `Pub_Access`, `GAP_Sts`,
`IUCN_Cat` and `GIS_Acres`, combining federal, state, local and land-trust
land with the NCED easements. The USGS "PAD-US Public Access" web view has
a reduced schema (`Category`, `FeatClass`, `Unit_Nm`, `Pub_Access`,
`GAP_Sts`, `IUCN_Cat`, `MngTp_Desc`, `MngNm_Desc`, `DesTp_Desc`,
`BndryName`, `GIS_Acres`): no owner fields, and its `Pub_Access` domain
lists only OA, RA and XA (no UK). Proclamation features, such as
proclaimed national forest boundaries, include private inholdings and must
never be read as public.

- **Coverage:** national, but the state files are clipped by state, so the
  Idaho file misses the ring's Oregon strip; that needs the Oregon file or
  the national or GeoParquet copy. Version 4.1 was published Mar 31, 2025.
  Whether it is still the newest in Oct 2026 couldn't be checked
  (www.usgs.gov timed out or answered 504) ⚠️. The Public Access view's
  `dataLastEditDate` is 2025-06-11, consistent with 4.1, though all nine
  USGS PAD-US view items had metadata edits on 2026-07-30. The
  researcher's ring sample (586 features) wasn't re-checked.
- **Access:** ScienceBase state-downloads item `6759abcfd34edfeb8710a004`
  (`PADUS4_1_State_ID_GDB_KMZ.zip`, 149.87 MB; Oregon 291.35 MB), by hand
  in a browser only (see robots.txt). ArcGIS Online web views at
  `services.arcgis.com/v01gqwM5QqNysAAi` (`PADUS_Public_Access` and
  others; 2,000 records a page). A re-host on Source Cooperative by the
  Boettiger Lab (UC Berkeley), which says it isn't an official USGS
  distribution: `combined.parquet` and `combined.pmtiles` under
  `padus-4-1`. The `s3://public-padus/...` path wasn't tested. No key.
- **License:** public domain ("Public Domain" on the ScienceBase item).
  Cite USGS GAP PAD-US 4.1, doi:10.5066/P96WBCHS. The web view carries a
  USGS no-liability disclaimer; Source Cooperative also states public
  domain and asks for credit to USGS GAP.
- **robots.txt:** www.sciencebase.gov has two `User-agent: *` groups. The
  first, inside a block marked as Cloudflare-managed, carries a content
  signal (`ai-train=no`) and `Allow: /`. The operator's own section after
  it says it blocks everything for all bots by default (`Disallow: /`),
  and it also disallows ClaudeBot, Claude-Web and Claude-User. A strict
  RFC 9309 merge gives an equal-length tie, which the RFC says should go
  to Allow, but the operator's intent is plain: treat ScienceBase as
  disallowed for any automated client. A one-time hand download in the
  owner's browser isn't robot access. Elsewhere: services.arcgis.com 403
  (no rules); edits.nationalmap.gov 503 (disallow for now);
  data.source.coop 404 (no rules); source.coop allows `/` but disallows
  `/api/` and `/*/*/`.
- **Updates and size:** about yearly (4.0 Apr 2024, 4.1 Mar 2025; a 2026
  release unverifiable). 150 MB for the Idaho zip plus 291 MB for Oregon,
  or a bounding-box read of the GeoParquet; a ring clip is a few MB.
- **Use cases:** the base "who manages this land, and is it open to the
  public" layer, using Fee plus Easement for access, never Proclamation;
  designations (NCA, WMA, NWR, state parks, city open space) as overlays;
  acres by manager and access code; the baseline for the landlocked-land
  analysis.
- **Personas:** hiker, camper, hunter, angler, researcher, homeowner.
- **Needs from core:** layer system, evidence and review, areas, places
  and search. **Effort** S.
- **Risks:** updated about once a year; `Pub_Access` isn't reviewed
  locally; not a legal boundary; confidential easements are withheld.
  Proclamation and Designation features overlap Fee and include private
  inholdings, so flatten them by class before any "is it public" answer.
- **Checked:** confirmed the file name and size, publication date, DOI,
  public-domain statement, web-view endpoint and page size, the re-host's
  status, and robots.txt for ArcGIS, nationalmap and Source Cooperative.
  Corrected the ScienceBase robots reading (the `Allow: /` comes from the
  Cloudflare preamble; the operator blocks all bots), the web-view schema
  (no owner fields, no UK code) and the coverage (the Idaho file misses
  Oregon). Unverifiable: whether 4.1 is still the newest. The verifier
  fetched the ScienceBase item page once before reading its robots.txt
  and stopped there. Evidence:
  [ScienceBase item](https://www.sciencebase.gov/catalog/item/6759abcfd34edfeb8710a004),
  [ScienceBase robots.txt](https://www.sciencebase.gov/robots.txt),
  [Public Access view](https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/PADUS_Public_Access/FeatureServer/0?f=json),
  [view item](https://www.arcgis.com/sharing/rest/content/items/c91a5655a1be428daeb778888e60db24?f=json),
  [Source Cooperative](https://source.coop/cboettig/padus), robots.txt for
  [source.coop](https://source.coop/robots.txt),
  [data.source.coop](https://data.source.coop/robots.txt) and
  [edits.nationalmap.gov](https://edits.nationalmap.gov/robots.txt);
  [PAD-US data history](https://www.usgs.gov/programs/gap-analysis-project/pad-us-data-history)
  (504 on Oct 7). An ArcGIS Online search of USGS's PAD-US items gave the
  metadata-edit dates.

### BLM Surface Management Agency (SMA)

[BLM_ID_Surface_Management_Agency](https://gis.blm.gov/idarcgis/rest/services/lands/BLM_ID_Surface_Management_Agency/FeatureServer).
Bureau of Land Management, Idaho State Office (the national layer is BLM
headquarters'). **use**, corrected; confidence high.

Surface-manager polygons. Idaho layer fields: `OBJECTID`, `MGMT_AGNCY`,
`AGNCY_NAME`, `GIS_ACRES` and `BLM_ACRES`. The `MGMT_AGNCY` domain includes
BLM, BOR, LU_DOI, NPS, NWR, USFS, LU_USDA, COE, MIL, DOE, OTHER, IR, STATE,
STATEFG, STATEPR, STATEOTH, PRIVATE and HSTRCWT(R). National services
under `gis.blm.gov/arcgis/rest/services/lands/`: `BLM_Natl_SMA_LimitedScale`,
the `Cached_*` variants and `BLM_Natl_SMA_PriUnk_Only_NoAccess` (national
field names such as `ADMIN_AGENCY_CODE` weren't re-checked).

- **Coverage:** Idaho only. A count over an Oregon-only box inside the
  ring (−117.30, 43.00, −117.10, 43.60) returned 0, so the Malheur County
  strip (Ontario, Nyssa, Vale, Lake Owyhee, Leslie Gulch) needs the
  national SMA or BLM Oregon data. Overlay units such as Deer Flat NWR
  don't appear, since SMA shows the surface manager only. The researcher
  counted about 2,150 polygons in the Idaho part of the ring (not
  re-checked).
- **Access:** FeatureServer and MapServer queries, 2,000 records a page,
  JSON, GeoJSON or PBF. Hub downloads on `gbp-blm-egis.hub.arcgis.com`.
  No key.
- **License:** federal work. The national SMA metadata says "PUBLIC.
  BLM.", provided as is, and that the data "are neither legal documents
  nor land surveys, and must not be used as such"; it also says they
  don't depict ownership. The research's quote "should not be used to
  depict boundaries" wasn't found verbatim.
- **robots.txt:** gis.blm.gov 404 (no rules). The hub host sets
  Crawl-delay 60 and disallows `/sites/`, `/admin/` and similar.
- **Updates and size:** "may be updated by the BLM without notification";
  refresh monthly. A few MB for the Idaho part of the ring.
- **Use cases:** the surface manager under every Idaho point, cross-checked
  against PAD-US; finding state, BLM, Reclamation and military land around
  the valley; the "Can I be here?" panel (Idaho part of the ring only).
- **Personas:** hiker, hunter, researcher, homeowner.
- **Needs from core:** layer system, evidence and review. **Effort** S.
- **Risks:** shows the manager, not the owner. The researcher's point
  checks gave surprising values (STATEFG at a Lucky Peak point, PRIVATE
  near Lake Lowell), so treat it as one piece of evidence. It's silent
  about Oregon, so the UI must say "no data" there and never imply
  private.
- **Checked:** confirmed the endpoint, fields, domain codes, page size,
  formats, robots.txt and the national metadata's "PUBLIC. BLM." and "as
  is" language. Corrected the coverage (Idaho only) and the disclaimer
  wording. Ring counts not re-checked. Evidence:
  [Idaho layer](https://gis.blm.gov/idarcgis/rest/services/lands/BLM_ID_Surface_Management_Agency/FeatureServer/0?f=json),
  [Idaho lands folder](https://gis.blm.gov/idarcgis/rest/services/lands?f=json),
  [national lands folder](https://gis.blm.gov/arcgis/rest/services/lands?f=json),
  [national SMA metadata](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_SMA_LimitedScale/MapServer/info/metadata),
  robots.txt for [gis.blm.gov](https://gis.blm.gov/robots.txt) and
  [the hub](https://gbp-blm-egis.hub.arcgis.com/robots.txt).

### Idaho Department of Lands State Ownership

[State_Ownership FeatureServer](https://services2.arcgis.com/1cvrwLhZRFh3okEF/arcgis/rest/services/State_Ownership/FeatureServer).
Idaho Department of Lands (IDL). **use**, corrected; confidence high.

Layer 0 `StateOwnership_Surface` and layer 1 `StateOwnership_Subsurface`.
Fields: `PARCELID`, `GISACRES`, `L_ACRES`, `OWNERTYPE` ("Beneficiary: IDL
Endowment" or "Beneficiary: Other State Agency"), `SURF_ENDOWMENT` (coded:
1 Public Schools, 8 University of ID, 15 Dept. of Fish and Game, plus split
and other codes), `SURF_ENDOWMENT_DESC`, `SURF_ALPHACODE`, and
`created_user`/`last_edited_user` (IDL staff user names) with dates.
Related IDL items (leases, surveys) weren't re-checked.

- **Coverage:** Idaho only. Last edited Oct 2, 2026. IDL's Endowment Land
  Locator says more than 96% of endowment land is publicly accessible. The
  researcher counted about 1,400 polygons in the ring (not re-checked).
- **Access:** ArcGIS Online FeatureServer, 2,000 records a page; also on
  `gis1.idl.idaho.gov`, with downloads through the IDL hub. The item is
  owned by IDL staff and has no license or access information. No key.
- **License:** none stated: neither the service nor the ArcGIS item
  carries any license, disclaimer or copyright text, and no redistribution
  restriction was found. The research quoted an IDL disclaimer ("not
  suitable for legal, engineering, or surveying purposes") that the
  verifier couldn't find on the IDL GIS program or Endowment Land Locator
  pages; treat it as unverified. Credit IDL and add our own "not a legal
  determination" line.
- **robots.txt:** services2.arcgis.com 403 (no rules). The IDL hub
  (`idl-geoportal-idl.hub.arcgis.com`) sets Crawl-delay 60 and disallows
  `/sites/`, `/admin/`, `/sessions/`, `/groups/`, `/people/` and
  `/workspace/`. `gis1.idl.idaho.gov/robots.txt` redirects (302) to
  `error.idaho.gov/`, an HTML page answering 200 (and
  `error.idaho.gov/robots.txt` is 404), so no rules. `www.idl.idaho.gov`
  allows everything. `landfoliogis.idl.idaho.gov` was unreachable again
  (treated as disallowed).
- **Updates and size:** edited continuously; refresh weekly. A few MB for
  the ring.
- **Use cases:** state endowment land on the Land lens with its
  beneficiary; "Can I be here?" answers citing IDAPA 20.05.01 (recreational
  use of endowment land) and Idaho Code 58-156; growth context, since
  endowment land near the valley can be sold or leased.
- **Personas:** hiker, hunter, OHV rider, traffic researcher, researcher.
- **Needs from core:** layer system, evidence and review. **Effort** S.
- **Risks:** drop `created_user` and `last_edited_user` (staff user
  names). Lease layers may carry lessee names; check their fields before
  any use. Endowment land can be sold, so keep versions. "Accessible" in
  IDL's 96% figure includes access by any means; it isn't parcel-level
  legal access.
- **Checked:** confirmed the endpoint, layers, fields, owner-type values,
  last edit, the 96% figure and robots.txt for every IDL host. Corrected
  the license and disclaimer. Added the staff user-name fields to drop.
  Evidence:
  [service](https://services2.arcgis.com/1cvrwLhZRFh3okEF/arcgis/rest/services/State_Ownership/FeatureServer?f=json),
  [layer 0](https://services2.arcgis.com/1cvrwLhZRFh3okEF/arcgis/rest/services/State_Ownership/FeatureServer/0?f=json),
  [item search](https://www.arcgis.com/sharing/rest/search?q=title:%22State%20Ownership%22%20AND%20orgid:1cvrwLhZRFh3okEF&num=10&f=json),
  [IDL GIS program](https://www.idl.idaho.gov/idl-gis-program-idaho-maps-and-land-records/),
  [Endowment Land Locator](https://www.idl.idaho.gov/endowment-land-and-recreation/endowment-land-locator/),
  [recreation policy](https://www.idl.idaho.gov/endowment-land-and-recreation/recreation-policy/),
  robots.txt for [the hub](https://idl-geoportal-idl.hub.arcgis.com/robots.txt),
  [gis1](https://gis1.idl.idaho.gov/robots.txt) and
  [www.idl.idaho.gov](https://www.idl.idaho.gov/robots.txt).

### USFWS National Wildlife Refuge System boundaries

[National_Wildlife_Refuge_System_Boundaries](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer/0).
US Fish and Wildlife Service, Division of Realty. **use**, confirmed;
confidence high.

One layer, `FWSBoundaries`, with `ORGNAME`, `ORGCODE`, `LIT`, `RSL_TYPE`,
`CostCenter` and `FWSREGION`. Its description says the boundaries are
"simplified from" the FWS Real Estate Interest layer and that not all
areas are open to the public. What the `RSL_TYPE` codes mean (acquired or
approved) wasn't confirmed. Deer Flat NWR (Lake Lowell and the Snake River
islands) is in the ring. Its official rules: motorized and non-motorized
boating on Lake Lowell Apr 15–Sep 30, with only human-powered craft near
the dams in the off-season; all refuge islands closed to entry Feb 1–Jun 14
(some nesting islands through Jun 30); hunting on Lake Lowell only in the
East and South Side recreation areas, with non-toxic shot.

- **Coverage:** national; last data edit Aug 24, 2026.
- **Access:** FeatureServer query. No key.
- **License:** federal work; `copyrightText` credits the FWS NWRS Division
  of Realty, with no license text beyond that.
- **robots.txt:** services.arcgis.com 403 (no rules); www.fws.gov allows
  the refuge pages.
- **Updates and size:** irregular; tiny for the ring.
- **Use cases:** refuge boundaries that SMA hides under Reclamation; the
  refuge's seasonal rules (boating season, island closures) as recurring
  lifecycles; wildlife-viewing places.
- **Personas:** wildlife watcher, angler, boater, hunter.
- **Needs from core:** layer system, lifecycles. **Effort** S.
- **Risks:** boundaries are simplified, and the outer boundary includes
  land and water where entry is restricted seasonally.
- **Checked:** confirmed the endpoint, fields and description. The Deer
  Flat seasonal rules, ⚠️ in the research, are now confirmed from the
  official FWS rules page. `RSL_TYPE` meanings remain unverified.
  Evidence:
  [service](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer?f=json),
  [layer](https://services.arcgis.com/QVENGdaPbd4LUkLV/arcgis/rest/services/National_Wildlife_Refuge_System_Boundaries/FeatureServer/0?f=json),
  [Deer Flat NWR](https://www.fws.gov/refuge/deer-flat),
  [Deer Flat rules](https://www.fws.gov/refuge/deer-flat/visit-us/rules-policies),
  [robots.txt](https://www.fws.gov/robots.txt).

### USFS boundaries and designations

[FSGeodata Clearinghouse](https://data.fs.usda.gov/geodata/edw/datasets.php)
and the EDW map services. USDA Forest Service. **use**, corrected;
confidence high.

Administrative forest boundaries, ranger districts, national wilderness
areas, surface ownership parcels (and a "detailed" variant), Idaho Roadless
Rule areas, MAPLand easements, range allotments, NFS trails and recreation
sites.

- **Idaho Roadless Rule areas** (refreshed Apr 28, 2026):
  `ROADLESSAREANAME`, `MGMTCLASSIFICATION` (7 classes: Managed as
  Designated Wilderness, Wild Land Recreation, Primitive, Backcountry
  Restoration, GFRG, Forest Plan Special Area, Special Area of Historic or
  Tribal Significance), `FORESTNAME_CA2008`, `GIS_ACRES`.
- **MAPLand easements** (Sep 28): layer 0 `Leg_MAPLand_Easement`,
  polygons with `feature_name`, `restrictions`, recording type, number,
  location and date, and `origin_agency`; no grantor names.
- **Range allotments** (Oct 2): `allot_name`, `allot_status`, livestock
  flags (cattle, sheep, horses, bison, goats and more), acres and NEPA and
  AMP years; no permittee names.
- **Boundaries, districts, wilderness and surface ownership:** refreshed
  Oct 4, 2026. The research said Surface Ownership is "updated weekly and
  more current than PAD-US"; that text belongs to the `PADUS FS …` staging
  datasets (`EDW_PADUS_01`), which USFS says are "not intended for regular
  use", not to Surface Ownership, which states no cadence.
- **Roadless Rule status,** now confirmed from the Federal Register API
  (it was ⚠️ on news sources): USDA proposed rescinding the 2001 Roadless
  Rule on Aug 20, 2026 (document 2026-16965, 91 FR 53827), and a Sep 11
  notice (2026-18648) extended comments to Oct 6, 2026. The Aug 29, 2025
  notice (2025-16581) says the Idaho and Colorado rules (36 CFR 294
  Subparts C and D) are retained. Idaho's roadless areas fall under the
  2008 Idaho rule, so the rescission has little direct effect in the ring.

- **Coverage:** national. The researcher's ring contents (Boise NF
  districts, 26 Idaho Roadless areas, 119 MAPLand easements, 27 allotments)
  weren't re-checked. The verifier's query found no BLM wilderness in the
  ring; no USFS wilderness there is plausible from geography but wasn't
  queried.
- **Access:** MapServers under `apps.fs.usda.gov/arcx/rest/services/EDW/`:
  `EDW_RangerDistricts_01`/`03`, `EDW_InventoriedRoadlessAreas2008Id_01`,
  `EDW_Wilderness_01`/`02`, `EDW_SurfaceOwnership_01`,
  `EDW_MAPLandEasement_01`, `EDW_RangeManagement_01`,
  `EDW_TrailNFSPublish_01`, `EDW_PADUS_01`,
  `EDW_RecreationOpportunities_01`. Clearinghouse zips: range allotments
  GDB 24 MB, Idaho Roadless 5 MB, MAPLand 25 MB, administrative forests
  40 MB. No key.
- **License:** federal work, public domain, with the "not legal documents"
  use constraint (as for the MVUM).
- **robots.txt:** apps.fs.usda.gov 403 and data.fs.usda.gov 404, both no
  rules.
- **Updates and size:** the clearinghouse refresh dates above; refresh
  monthly. Under 10 MB for the ring across all layers.
- **Use cases:** national forest and district boundaries for the Land lens;
  Idaho Roadless classes as backcountry context; easements that give
  public access across private land; grazing allotments with livestock
  type.
- **Personas:** hiker, hunter, camper, rancher, researcher.
- **Needs from core:** layer system, areas, places and search. **Effort**
  M.
- **Risks:** don't treat the `PADUS FS` staging layers as authoritative;
  USFS says they aren't for regular use.
- **Checked:** confirmed the service names, refresh dates, Roadless
  classes, the allotment and MAPLand schemas (no personal names) and
  robots.txt. Corrected the weekly-update claim. The Roadless rescission
  moved from ⚠️ to confirmed. Ring counts not re-checked. Evidence:
  [clearinghouse](https://data.fs.usda.gov/geodata/edw/datasets.php),
  [EDW services](https://apps.fs.usda.gov/arcx/rest/services/EDW?f=json),
  [Idaho Roadless layer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_InventoriedRoadlessAreas2008Id_01/MapServer/0?f=json),
  [MAPLand layer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MAPLandEasement_01/MapServer/0?f=json),
  [range layer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_RangeManagement_01/MapServer/0?f=json),
  Federal Register [search](https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=%22Roadless%20Area%20Conservation%22&conditions%5Bagencies%5D%5B%5D=forest-service&order=newest&per_page=10),
  [2026-16965](https://www.federalregister.gov/api/v1/documents/2026-16965.json),
  [2026-18648](https://www.federalregister.gov/api/v1/documents/2026-18648.json)
  and [robots.txt](https://www.federalregister.gov/robots.txt).

### Idaho Parks and Recreation state park boundaries

[IDPR_State_Parks MapServer](https://gis2.idaho.gov/arcgis/rest/services/DPR/IDPR_State_Parks/MapServer).
Idaho Department of Parks and Recreation (IDPR). **needs owner action**,
unverifiable; confidence low.

State park boundaries (Lucky Peak, Eagle Island, and Bruneau Dunes at the
ring's edge). Not inspected: `gis2.idaho.gov` was unreachable again on
Oct 7. IDPR's ArcGIS Online items include boat ramps, life-jacket loaner
stations (`services1.arcgis.com/CNPdEkvnGl65jCX8`), state-park web apps and
maps, and no park-boundary polygon service. IDL's State Ownership has a
"Dept. of Parks and Recreation" beneficiary code for state-owned park
parcels; parks on federal land (Lucky Peak is on Corps of Engineers land)
wouldn't appear there.

- **Coverage:** statewide (unverified).
- **Access:** the MapServer above (unreachable); IDPR items on ArcGIS
  Online. No key.
- **License:** not checked (host unreachable). IDPR's ArcGIS items carry
  no-warranty and no-liability disclaimers.
- **robots.txt:** gis2.idaho.gov unreachable (connection failed again), so
  treated as disallowed. parksandrecreation.idaho.gov allows everything.
- **Updates and size:** unknown; tiny.
- **Use cases:** state park units. Meanwhile PAD-US, SMA's STATEPR code
  and IDL's parks beneficiary code cover them.
- **Personas:** camper, boater, hiker.
- **Needs from core:** layer system. **Effort** S.
- **Risks:** the local helper could check `gis2.idaho.gov` from the
  owner's network.
- **Checked:** host still unreachable. Confirmed that IDPR has no
  park-boundary polygons on ArcGIS Online, and robots.txt for
  parksandrecreation.idaho.gov. Evidence:
  [IDPR's ArcGIS items](https://www.arcgis.com/sharing/rest/search?q=owner:Idaho_Department_of_Parks_and_Recreation&num=50&f=json),
  [parks site robots.txt](https://parksandrecreation.idaho.gov/robots.txt);
  `gis2.idaho.gov/robots.txt` unreachable.

### Bureau of Reclamation Land Ownership (avoid)

[ReclamationLandOwnership](https://services1.arcgis.com/ixD30sld6F8MQ7V5/arcgis/rest/services/ReclamationLandOwnership/FeatureServer/0).
US Bureau of Reclamation. **avoid**, confirmed; confidence high.

Reclamation's land interests: `assettype`, `acquisitioninterest`,
`acquisitiondate`, `wdordernumber`, `usbrregion`, `areaoffice`,
`usbrproject`, `gisacres` (fields not re-checked). National; item modified
Feb 10, 2026; public FeatureServer, no key.

- **Terms:** the item's license says Reclamation "does not authorize
  downloading or republishing, deriving new data products". It also bars
  dissemination into other systems, which rules out proxying it through
  our `/api/` as well.
- **robots.txt:** services1.arcgis.com 403 (no rules); the terms forbid
  storage regardless.
- **Instead:** SMA's BOR polygons and PAD-US cover Reclamation land
  (Arrowrock, Lake Lowell). Personas it would have served: boater, angler,
  hunter. **Effort** S.
- **Checked:** confirmed the license text and the owner (Reclamation's
  public account); added the dissemination clause. Evidence:
  [item](https://www.arcgis.com/sharing/rest/content/items/8809290b35c6499ebe06e84b1597d410?f=json),
  [robots.txt](https://services1.arcgis.com/robots.txt).

### National Conservation Easement Database (avoid)

[conservationeasement.us](https://conservationeasement.us/). NCED
partnership (Ducks Unlimited, TPL, NatureServe and others). **avoid**,
confirmed; confidence high.

Conservation easements. The site says that "as of January 2025" NCED is no
longer actively updated or supported, for lack of funding, and points users
to PAD-US, whose Easement class carries them.

- **Coverage:** national, frozen at Jan 2025. No license stated (not
  re-checked).
- **robots.txt:** couldn't be reached on Oct 7 (connection failed), so
  treated as disallowed; the research's earlier reading (all allowed but
  `/wp-admin/`) couldn't be re-confirmed. That doesn't change the verdict.
- **Use instead:** PAD-US's Easement class. Persona: researcher. **Effort**
  S.
- **Checked:** confirmed the funding notice and the pointer to PAD-US.
  Evidence: [site](https://conservationeasement.us/); its robots.txt was
  unreachable.

### Canyon County public tax parcels and parks (private)

[Canyon_County_Public_Tax_Parcels](https://maps.canyoncounty.id.gov/arcgisserver/rest/services/General/Canyon_County_Public_Tax_Parcels/FeatureServer/0).
Canyon County (Assessor; Parks, Cultural & Natural Resources). **internal
only**, corrected; confidence medium.

Tax parcels with `DXF_TEXT`, `PIN`, `ACRES`, `SiteAddress`, `SiteCity`,
`SiteZIP`, `SubName`, `Legal`, `FCVLand`, `FCVImp`, `FCVTotal`, `TaxCode`
and `InCity`; no owner-name or mailing fields. `Parks/PublicParks` is a
point layer (the research called it polygons) with amenity flags
(`ADA_Parking`, `ATV`, `Birding`, `Boating`, `Camping`, `Disc_Golf`,
`Fishing`, `Hiking`, `Horseback`, `Hunting_Shooting`, `Picnic`,
`Potable_Water`, `Restrooms`, `Swimming`) plus `created_user` and
`last_edited_user`. [Ch. 9 §9.6](../09-base-map-data.md#96-parcels-zoning-land-use-addresses)
already covers the parcels.

- **Coverage:** Canyon County only. Ch. 9's "110,890 parcels, refreshed
  daily" wasn't re-checked; the layer has no edit tracking.
- **Access:** public ArcGIS FeatureServer and MapServer (General, Assessor
  and Parks folders), no login. Full Assessor GIS data comes by FTP; the
  Assessor's page says to email the Plat Room for FTP credentials. Base
  GIS data are free.
- **License:** none on the services. The Assessor's page says base GIS
  data are free by FTP, and its distribution policy covers government
  agencies and contractors at no cost. Idaho Code 74-120 (no mailing-list
  use) isn't mentioned on the Assessor's page; it rests on ch. 9 ⚠️.
- **robots.txt:** maps.canyoncounty.id.gov 404 (no rules).
  www.canyoncounty.id.gov has two `User-agent: *` groups: one disallows
  `/wp-admin/` (allowing `admin-ajax.php`), the other
  `/wp-content/uploads/wpo/wpo-plugins-tables-list.json`. That's a real
  case for the robots.txt merge fix ([design note 8](#design-notes)).
- **Updates and size:** unverified (said to be daily). About 111k parcels,
  about 60–100 MB of GeoJSON.
- **Use cases:** Canyon County in the private `parcels` plugin (owner only;
  aggregates in anything shared); county parks as points with amenities on
  the Land lens.
- **Personas:** homeowner, land buyer, researcher, camper.
- **Needs from core:** private plugins, layer system. **Effort** M.
- **Risks:** site addresses and assessed values are close to personal, so
  keep them private and publish aggregates only. FTP credentials are an
  owner action. Drop the parks layer's user-name fields.
- **Checked:** corrected the access (the public service needs no account;
  only FTP does) and the parks geometry (points). Confirmed that the parcel
  fields have no owner names, the FTP process and robots.txt. Evidence:
  [parcels layer](https://maps.canyoncounty.id.gov/arcgisserver/rest/services/General/Canyon_County_Public_Tax_Parcels/FeatureServer/0?f=json),
  [parks layer](https://maps.canyoncounty.id.gov/arcgisserver/rest/services/Parks/PublicParks/FeatureServer/0?f=json),
  [Assessor GIS page](https://www.canyoncounty.id.gov/elected-officials/assessor/gis-information/),
  robots.txt for [maps](https://maps.canyoncounty.id.gov/robots.txt) and
  [www](https://www.canyoncounty.id.gov/robots.txt).

---

## Routes and travel rules

### BLM Idaho Ground Transportation Linear Features (GTLF)

[GTLF FeatureServer](https://gis.blm.gov/idarcgis/rest/services/transportation/BLM_ID_Ground_Transportation_Linear_Features_GTLF/FeatureServer/0).
BLM Idaho. **use**, corrected; confidence high.

Travel-management route designations. The layer includes external
connectivity routes that BLM doesn't manage: its description says BLM Idaho
maintains only routes recorded in a travel management plan (TMP), and all
other data are non-authoritative reference only. Fields:

- `PLAN_OHV_ROUTE_DSGNTN`: OPEN, CLOSED, LIMITED or UNKNOWN.
- `OHV_ROUTE_DSGNTN_LIM` (limited by vehicle type, season, time of day or
  combinations) and `OHV_DSGNTN_LIM_EXPLAIN`.
- `PLAN_ALLOW_MODE_TRNSPRT`: 22 codes such as HIK_ONLY, BIKE_ONLY,
  MTC_ATV_UTV_SHARED and SNOW_MOTO_ONLY; some shared classes include
  e-mountain bikes.
- `PLAN_ADD_MODE_TRNSPRT_RSTRT_CD` (YES, NO, UNK); `PLAN_ACCESS_RSTRCT`
  (ALL, ADMIN ONLY, AUTHORIZED/PERMITTED USER ONLY, NONE, UNKNOWN).
- `PLAN_SEASON_RSTRCT_CODE`: only a YES/NO/UNK flag. **There are no season
  dates anywhere in the layer** (the research expected a lookup table);
  the dates are in each travel plan or NEPA document.
- `DSTRBTE_EXTRNL_CODE`, `TMA_ID`, `TMP_ID`, `NEPA_DOC_NUM`,
  `OBSRVE_SRFCE_TYPE`, `OBSRVE_FUNC_CLASS`, `ROUTE_PRMRY_NM`, `GIS_MILES`,
  `BLM_MILES`.

- **Coverage:** Idaho only (0 features in an Oregon-only box inside the
  ring). One statistics query over the ring:

  | Designation | Routes | GIS miles |
  |---|---|---|
  | None | 19,209 | 12,867 |
  | OPEN | 4,633 | 1,582 |
  | LIMITED | 450 | 342 |
  | CLOSED | 700 | 266 |
  | UNKNOWN | 36 | — |

  By `BLM_MILES`, only about 7,000 of the about 15,070 GIS miles are on BLM
  land, and about 4,940 of those (about 70%) have no designation. The other
  about 7,900 undesignated miles are off BLM land (external connectivity
  routes). The research's "about 12,900 of 15,000 BLM miles undesignated"
  counted those too.
- **Access:** FeatureServer query, 2,000 records a page, JSON, GeoJSON or
  PBF. Page by object IDs, or by `resultOffset` ordered by `OBJECTID`, not
  by envelope: lines crossing an envelope's edge come back twice. No key.
- **License:** federal work, public domain, with an as-is disclaimer;
  `copyrightText` credits the BLM Idaho State Office.
- **robots.txt:** gis.blm.gov 404 (no rules).
- **Updates and size:** irregular; refresh monthly. About 25k lines in the
  ring (about 12.5k on BLM land), about 20–40 MB of GeoJSON.
- **Use cases:** "what can I drive or ride here" on BLM land (designation
  and allowed modes); how much of BLM's own mileage still lacks a
  designation; routes with a seasonal or time-of-day restriction shown as
  a flag with a link to the travel plan. The layer can't drive dated
  seasonal windows on the time slider.
- **Personas:** OHV rider, hunter, camper, cyclist.
- **Needs from core:** layer system, lifecycles, a regular OpenStreetMap
  load. **Effort** M.
- **Risks:** an undesignated route isn't permission to drive it. On BLM
  land it falls under the area's OHV designation in the resource
  management plan (open, limited or closed area), and BLM Idaho publishes
  no OHV-area layer (none in the transportation, lands, planning or
  recreation folders). Many undesignated features aren't on BLM land at
  all. Season windows must be entered by hand from travel-plan documents.
- **Checked:** confirmed the endpoint, fields, designation codes, ring
  counts and miles. Corrected the season data (a flag only), the
  undesignated share, the Idaho-only coverage, and the absence of an
  OHV-area layer. Evidence:
  [transportation folder](https://gis.blm.gov/idarcgis/rest/services/transportation?f=json),
  [layer](https://gis.blm.gov/idarcgis/rest/services/transportation/BLM_ID_Ground_Transportation_Linear_Features_GTLF/FeatureServer/0?f=json)
  (plus one statistics query grouped by `PLAN_OHV_ROUTE_DSGNTN` and
  `DSTRBTE_EXTRNL_CODE` over the ring envelope),
  [robots.txt](https://gis.blm.gov/robots.txt).

### USFS Motor Vehicle Use Map (MVUM) roads and trails

[EDW_MVUM_01 MapServer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_01/MapServer).
USDA Forest Service (Enterprise Data Warehouse). **use**, confirmed;
confidence high.

Designated motor-vehicle routes. For each vehicle class there is a flag and
a `*_datesopen` field: `passengervehicle`, `highclearancevehicle`, `truck`,
`bus`, `motorhome`, `fourwd_gt50inches`, `twowd_gt50inches`,
`tracked_ohv_gt50inches`, `other_ohv_gt50inches`, `atv`, `motorcycle`,
`otherwheeled_ohv`, `tracked_ohv_lt50inches` and `other_ohv_lt50inches`.
Also `e_bike_class1`/`2`/`3` with `*_dur`, `symbol`, `seasonal`,
`operationalmaintlevel` and `jurisdiction`. The clearinghouse notes that
only roads with `SYMBOL` 1, 2, 3, 4, 11 or 12 are Forest Service system
roads carrying OHV data. "Dates open" means when that vehicle is legal,
not road conditions.

- **Coverage:** national. The national Roads and Trails GDBs were last
  refreshed Oct 1, 2026. The researcher counted 512 road segments
  (1,160 mi) and 178 trail segments (513 mi) in the ring, all Boise NF
  (not re-checked; Boise NF being the only forest in the ring is plausible
  from geography).
- **Access:** MapServer layers 1 (Roads) and 2 (Trails); layers 4 and 5
  are the same data under Visitor Map symbology, so query 1 and 2 only.
  Map, Query and Data capabilities; 2,000 records a page; JSON, GeoJSON or
  PBF. `EDW_MVUM_02` also exists. Downloads on data.fs.usda.gov: Road_MVUM
  GDB 118 MB (shapefile 227 MB), Trail GDB 35 MB (shapefile 69 MB). No key.
- **License:** federal work. FGDC metadata: access constraints "None"; use
  constraints are an as-is no-warranty disclaimer, the data aren't legal
  documents, and the printed MVUM is the legal map. Updated "as needed".
- **robots.txt:** apps.fs.usda.gov answers 403 with an HTML "Access
  forbidden!" page, which under RFC 9309 means no rules; it may be a
  firewall response, so keep requests sparse. data.fs.usda.gov 404 (no
  rules).
- **Updates and size:** unit by unit, as needed; refresh weekly. About 700
  segments in the ring, under 5 MB.
- **Use cases:** "what can I ride on date X" with a per-vehicle filter
  including e-bike classes; seasonal openings on the time slider (parsed
  from `*_datesopen`); legal-access analysis for national forest land.
- **Personas:** OHV rider, motorcyclist, e-biker, hunter, camper.
- **Needs from core:** layer system, lifecycles, time and replay clock, 3D
  engine. **Effort** M.
- **Risks:** the dates-open strings need parsing into recurring intervals.
  Forest orders override the MVUM (for example the Crooked Fire closure,
  order 0402-03-140, to Dec 31, 2026). Filter by `SYMBOL` before reading
  the OHV flags.
- **Checked:** confirmed the layers, fields (including the e-bike and
  tracked-OHV classes), page size, formats, refresh date, file sizes, use
  constraints and robots.txt. Added the `SYMBOL` filter and the duplicate
  layers 4 and 5. Evidence:
  [service](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_01/MapServer?f=json),
  [Roads layer](https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MVUM_01/MapServer/1?f=json),
  [EDW folder](https://apps.fs.usda.gov/arcx/rest/services/EDW?f=json),
  [clearinghouse](https://data.fs.usda.gov/geodata/edw/datasets.php),
  [Road_MVUM metadata](https://data.fs.usda.gov/geodata/edw/edw_resources/meta/S_USA.Road_MVUM.xml),
  robots.txt for [apps](https://apps.fs.usda.gov/robots.txt) and
  [data](https://data.fs.usda.gov/robots.txt).

### BLM access easements: PLAD and MAPLand Act layers

[BLM_Natl_PLAD MapServer](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_PLAD/MapServer).
BLM headquarters. **use**, confirmed; confidence medium.

Federal access interests in non-federal land, digitized under the MAPLand
Act. The PLAD (Public Lands Access Database) line layer has `SN_FULL`,
`MLRS_SRL_NO`, `ACS_RGHTS_TYPE`, `ACS_RGHTS_EXPRTN_DT`, `LEGAL_USE_TYPE`,
`SSNL_USE_TYPE`, `SSNL_USE_START`/`END` (strings) and `SSNL_USE_DTL`,
`TRVL_PLAN_YN`/`URL`, `ROUTE_NO`, `WIDTH_FT`, `BLM_FLD_OFC`,
`TITLE_REC`/`TITLE_REC_DT`, and also `APRSD_VALUE` (appraised value) and
`PYMNT_MADE` (payment made). The MAPLand service
(`recreation/BLM_Natl_MAPLand`) has layer 0 "MAPLand Act Easement Lines
BLM" and layer 1 "Easement Areas BLM", from several agencies (BLM, NPS,
FWS, USBR, USACE, FS).

- **Coverage:** national. The researcher found 57 lines in each service
  and no polygons in the ring (not re-checked).
- **Access:** MapServer queries: `lands/BLM_Natl_PLAD` (layers 0 and 1)
  and `recreation/BLM_Natl_MAPLand` (layers 0 and 1). No key.
- **License:** federal work, public domain (`copyrightText`: BLM HQ).
- **robots.txt:** gis.blm.gov 404 (no rules).
- **Updates and size:** MAPLand digitizing is ongoing; refresh monthly.
  Tiny.
- **Use cases:** legal routes across private land to BLM land; input to the
  landlocked-land analysis; seasonal easements on the time slider (parsing
  the start and end strings).
- **Personas:** hunter, hiker, OHV rider, researcher.
- **Needs from core:** layer system, lifecycles. **Effort** S.
- **Risks:** coverage is still being built, so a missing easement doesn't
  mean there's no access. Privacy: drop `APRSD_VALUE` and `PYMNT_MADE`
  (amounts tied to identifiable private parcels) and don't publish case
  numbers with them. The seasonal start and end are free text.
- **Checked:** confirmed the endpoints, layer names and PLAD fields,
  including the seasonal ones. Added the appraisal and payment fields.
  Evidence:
  [PLAD layer](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_PLAD/MapServer/0?f=json),
  [MAPLand service](https://gis.blm.gov/arcgis/rest/services/recreation/BLM_Natl_MAPLand/MapServer?f=json),
  [lands folder](https://gis.blm.gov/arcgis/rest/services/lands?f=json).

---

## Closures and restrictions

### BLM Idaho advisories and closures

[blm.gov/idaho/advisories-and-closures](https://www.blm.gov/idaho/advisories-and-closures).
BLM Idaho. **use**, confirmed; confidence medium.

Area closure orders, each with a PDF order and map. Example: the Big Grass
Fire closure (Bruneau and Owyhee field offices) runs through Oct 15, 2026,
11:59 p.m.; burned land within the perimeter stays closed. It links an
order PDF (`/sites/default/files/docs/2026-09/20260919_OwyheeFieldOfficeClosure.pdf`)
and a map PDF (`SUTR_BigGrass_Closure_20260916-1015.pdf`). The page also
lists seasonal closures statewide (for example Wood River Valley OHV Jan
1–Apr 30, South Hills motorized Jan 16–Mar 15).

- **Coverage:** Idaho statewide; the Boise District covers the Idaho part
  of the ring. The Oregon strip falls under BLM's Vale District, which
  isn't on this page.
- **Access:** web page plus PDF orders and maps; no GIS feed found. No key.
- **License:** federal work, public domain.
- **robots.txt:** www.blm.gov disallows only Drupal admin, search, user,
  oembed and asset paths, so this page and `/sites/default/files/docs/`
  are allowed.
- **Updates and size:** event-driven; a handful of orders a year in the
  ring.
- **Use cases:** closure lifecycles on the time bar and in the Valley
  Feed; "Can I be here?" warnings.
- **Personas:** hiker, hunter, OHV rider, fire watcher.
- **Needs from core:** lifecycles, Valley Feed, evidence and review.
  **Effort** M.
- **Risks:** polygons must be digitized by hand from the PDF maps. A page
  watcher must be polite and must not fetch PDFs in bulk.
- **Checked:** confirmed the Big Grass Fire closure, its end date, the PDF
  links and robots.txt. Added that Vale District (Oregon) isn't covered.
  Evidence: [page](https://www.blm.gov/idaho/advisories-and-closures),
  [robots.txt](https://www.blm.gov/robots.txt).

### Boise National Forest alerts and forest orders

[fs.usda.gov/r04/boise/alerts](https://www.fs.usda.gov/r04/boise/alerts).
USDA Forest Service, Boise National Forest. **use**, confirmed; confidence
medium.

Area, fire, road and trail closures, fire restrictions, occupancy and use
orders, and resource-protection closures, each with a forest order (FO)
number. Examples on the page:

| Order | What | When |
|---|---|---|
| FO 0402-03-140 | Crooked Fire area, road and trail closure (updated Sep 19, 2026) | Through Dec 31, 2026 |
| FO 0402-01-122 | Deer Point project closure | Aug 17–Nov 30, 2026, weekdays 6 a.m.–6 p.m. |
| FO 0402-05-101 | Lowman dispersed-camping closure | |
| FO 0402-06-84 | Lava Fire road closures | |
| FO 0402-04-113 | Rainbow Point Campground closure | Through Nov 2027 |
| FO 0402-00-62 | Forest-wide stay limit: no camping more than 14 days in any 30-day period | Standing |

- **Coverage:** Boise NF (the north-east part of the ring).
- **Access:** web pages and order PDFs, plus an interactive alerts map
  whose layer wasn't found (nothing in EDW). No key.
- **License:** federal work, public domain.
- **robots.txt:** www.fs.usda.gov's `*` group disallows only admin,
  comment, contact, logout, node, search and user paths (and `?q=` forms),
  so the alerts page is allowed.
- **Updates and size:** event-driven; dozens of orders a year.
- **Use cases:** forest closures as lifecycles that override the MVUM,
  including weekday and time-of-day windows; Valley Feed items when orders
  appear; the official stay limit for the "Can I be here?" panel.
- **Personas:** hiker, camper, OHV rider, hunter, fire watcher.
- **Needs from core:** lifecycles, Valley Feed. **Effort** M.
- **Risks:** no machine-readable geometry, so entry is by hand. Some orders
  apply only on weekdays or at set hours, which a simple start and end
  can't express (design note 2).
- **Checked:** confirmed the page, its examples and robots.txt. Added the
  order numbers, the Deer Point weekday and hour window, and the 14-in-30
  stay limit, which settles the stay-limit ⚠️ for Forest Service land.
  Evidence: [alerts](https://www.fs.usda.gov/r04/boise/alerts),
  [robots.txt](https://www.fs.usda.gov/robots.txt).

### Idaho fire restrictions (interagency stage map)

[FireRestrictions MapServer](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer).
Idaho Department of Lands with USFS, BLM, BIA, tribes and local fire
agencies. **use**, confirmed; confidence high.

Layer 1, Fire Restriction Zones: `Name`, `Stage` (None, Stage I, Stage II),
`Rstrct_Are`, `DateEnacted`, `DateRescinded`, `UpcomingStage`, `Zones`,
`last_edited_user` and `last_edited_date`. It backs IDL's Fire
Restrictions Finder. One query of the valley box returned three zones
(Owyhee, West Central, Treasure Valley) in the "Boise Fire Restriction
Area", all at Stage None, with `DateEnacted` 2026-09-03 14:01 UTC: the date
restrictions were **lifted**. The layer holds only the current state; there
is no history.

- **Coverage:** Idaho only. IDL says restrictions apply to "Federal, State,
  Tribal and private lands" outside city limits within the zones. The ring
  crosses more zones than the three in the valley box; the Oregon strip is
  under Oregon and BLM Vale restrictions.
- **Access:** MapServer query (Map, Query, Data; 2,000 records a page;
  JSON, GeoJSON or PBF). No key.
- **License:** no license, description or copyright text on the layer. The
  stages are public notices; credit IDL and the interagency partners.
- **robots.txt:** `gis1.idl.idaho.gov/robots.txt` redirects (302) to
  `error.idaho.gov/`, an HTML page answering 200, so no rules; the HTML
  check in `ingest/http.py` already reads it that way. Poll gently.
- **Updates and size:** changed by hand during fire season (last edit
  Sep 3, 2026). Hourly from June to October is ample, daily otherwise.
  Under 100 KB a poll.
- **Use cases:** the fire-restriction stage as a lifecycle on the time
  bar, built from our own polling history; a Valley Feed item when a stage
  changes or `UpcomingStage` is set; "Can I have a campfire here today?"
- **Personas:** camper, fire watcher, hunter, hiker.
- **Needs from core:** lifecycles, Valley Feed, time and replay clock.
  **Effort** S.
- **Risks:** history from before we start polling can't be rebuilt from
  the service. Stage None with a `DateEnacted` marks the **end** of the
  previous restriction, not a new lifecycle. Drop `last_edited_user`. The
  research said two once-official fire-information domains
  (`idahofireinfo.com`, and `firerestrictions.us` at the bare domain) now
  serve gambling content; that wasn't verified, and the verifier
  deliberately didn't fetch them ⚠️. Keep the blocklist proposal
  (question 13), but don't cite it as fact.
- **Checked:** confirmed the fields, stage codes, the three valley zones
  at Stage None, the last-edit date, IDL's land-coverage statement and the
  robots.txt behaviour. Added that the layer is current-state only.
  Evidence:
  [Fire Restrictions Finder](https://www.idl.idaho.gov/fire-management/fire-restrictions-finder/),
  [zones layer](https://gis1.idl.idaho.gov/arcgis/rest/services/Portal/FireRestrictions/MapServer/1?f=json)
  (plus one attributes-only query over the valley box), robots.txt for
  [gis1](https://gis1.idl.idaho.gov/robots.txt) and
  [error.idaho.gov](https://error.idaho.gov/robots.txt).

---

## Hunting and fishing

### IDFG open data

[data-idfggis.opendata.arcgis.com](https://data-idfggis.opendata.arcgis.com/).
Idaho Department of Fish and Game (IFWIS). **internal only**, corrected;
confidence medium.

Wildlife Management Areas (WMAs), Game Management Units (GMUs), controlled
hunt areas, areas with hunting restrictions, GMUs with motorized hunting
rules, fishing and boating access sites, other access agreements, and the
"Big Game Winter Range and Migration Priority Areas" layer.

- **WMAs:** `WMAID`, `Name`, `Acres`; 31 statewide, 275 to 85,000 acres;
  last edited Sep 8, 2026. The Boise River WMA page: 41,500 acres; Boise
  Front roads open May 1–Nov 15; Charcoal roads Sep 1–Dec 31; dogs leashed
  Nov 16–Apr 30; part of the Cornell segment closed Feb 1–Apr 14.
- **GMUs with Motorized Hunting Rules:** `NAME` only. Its description says
  that from Aug 30 to Dec 1, big-game hunters may use motor vehicles only
  on established roads open to traffic and passable by full-sized
  automobiles; upland game is no longer covered.
- **Big Game Winter Range and Migration Priority Areas:** just `Name` and
  five broad SO 3362 priority complexes statewide (for example the
  Smoky-Boise Complex), from the 2023 Idaho Action Plan v5.0. **It is not
  mapped winter range** (the research read it as such).
- Controlled hunts, restrictions and access sites weren't re-checked field
  by field.

- **Coverage:** Idaho only (the Oregon strip is under ODFW).
- **Access:** feature services on `services.arcgis.com/FjJI5xHF2dUPVrgK`
  and `gisportal-idfg.idaho.gov/hosting/rest/services` (confirmed for
  WMAs, GMUsWithMotorizedHuntingRules, AreasWithHuntingRestrictions and
  the priority-areas layer). No key.
- **License:** varies by item. WMAs: "best representation only".
  AreasWithHuntingRestrictions: "for public-use for informational purposes
  only". Conservation Sites: "free, unrestricted access and use". The
  priority-areas layer: no license, with a citation to IDFG 2023. IDFG's
  website [Terms](https://idfg.idaho.gov/terms) allow only personal,
  non-commercial transitory viewing and forbid copying, public display,
  transfer or mirroring, with no carve-out for GIS or open data.
- **robots.txt:** the hub sets Crawl-delay 60 and disallows `/sites/`,
  `/admin/`, `/sessions/`, `/groups/`, `/people/` and `/workspace/`.
  services.arcgis.com 403 and gisportal-idfg.idaho.gov 404 (no rules).
  idfg.idaho.gov disallows only Drupal admin, search, user and oembed
  paths.
- **Updates and size:** yearly with the regulations (WMAs edited Sep
  2026); under 20 MB statewide for these layers.
- **Use cases:** hunting overlays (units, controlled hunts, closed areas,
  the motorized-hunting rule); WMA boundaries with their seasonal rules,
  dates entered by hand from the WMA pages; the priority complexes as
  coarse context only, never as winter range.
- **Personas:** hunter, angler, wildlife watcher, driver.
- **Needs from core:** layer system, lifecycles, places and search, time
  and replay clock. **Effort** S.
- **Risks:** ask IFWIS before republishing: some items grant unrestricted
  use, but the site Terms don't carve out data. Boundaries are "best
  representation"; the rules booklet is authoritative. The WMA copyright
  text names an individual analyst, so credit IDFG, not the person.
- **Checked:** confirmed the Terms, robots.txt, the WMA schema and count,
  the motorized rule and its dates, and the Boise River WMA seasons.
  Corrected the winter-range reading. Added the per-item license
  differences and the Idaho-only coverage. Evidence:
  [Terms](https://idfg.idaho.gov/terms),
  [IDFG GIS](https://idfg.idaho.gov/data/gis),
  [hub robots.txt](https://data-idfggis.opendata.arcgis.com/robots.txt),
  [hub search](https://data-idfggis.opendata.arcgis.com/api/search/v1/collections/dataset/items?q=Wildlife%20Management%20Areas&limit=5),
  [WMAs](https://services.arcgis.com/FjJI5xHF2dUPVrgK/arcgis/rest/services/WildlifeManagementAreas/FeatureServer/0?f=json),
  [motorized rule GMUs](https://services.arcgis.com/FjJI5xHF2dUPVrgK/arcgis/rest/services/GMUsWithMotorizedHuntingRules/FeatureServer/0?f=json),
  [priority areas](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hosted/Big_Game_Winter_Range_and_Migration_Priority_Areas/FeatureServer/0?f=json),
  [Boise River WMA](https://idfg.idaho.gov/wma/boise-river),
  [robots.txt](https://idfg.idaho.gov/robots.txt).

### IDFG Access Yes! properties (2026)

[Access_Yes_2026_public](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hosted/Access_Yes_2026_public/FeatureServer/0).
Idaho Department of Fish and Game. **internal only**, confirmed;
confidence medium.

Private land enrolled for public hunting and fishing access. Polygons with
`active`, `bidid`, `generalarea`, `contactname`, `description`,
`directions`, `acreage`, `accesspublicacres`, `accesspublicdesc`,
`accessbegin`/`accessend` (dates), `agreementstatus`, `publishstatus`,
`biggame`, `uplandgame`, `smallgame`, `waterfowl`, `trapping`, `fishing`,
`landnotify`, `vehroads`, `vehgame`, `noveh`, `nocamp`, `nofire`,
`aud_cdate` and `name`. IDFG's page says the program had 328,066 private
acres and gave access to 525,115 public acres as of 2019.

- **Coverage:** Idaho, 2026 enrolment.
- **Access:** FeatureServer query; IDFG also offers a property list and
  map. No key.
- **License:** none on the service (no license, description or
  copyright). IDFG's website Terms apply to its pages (personal,
  non-commercial viewing only).
- **robots.txt:** gisportal-idfg.idaho.gov 404 (no rules).
- **Updates and size:** yearly enrolment, edited through the season; under
  2 MB.
- **Use cases:** hunter and angler access with each property's dates and
  rules on the time slider (owner only); seasonal access to landlocked
  public land (not general legal access).
- **Personas:** hunter, angler.
- **Needs from core:** lifecycles, layer system. **Effort** S.
- **Risks:** privacy: drop `contactname` and `bidid`, and never index
  them. It's private land: show IDFG's rules (the page says to ask for
  written permission) and link to IDFG. Access is for hunting and fishing
  only, and time-limited.
- **Checked:** confirmed the fields (including `contactname`), the 2019
  acreage figures, the missing license and robots.txt. Evidence:
  [layer](https://gisportal-idfg.idaho.gov/hosting/rest/services/Hosted/Access_Yes_2026_public/FeatureServer/0?f=json),
  [Access Yes! page](https://idfg.idaho.gov/access/yes).

### IDFG seasons and rules booklets and the Hunt Planner

[idfg.idaho.gov/rules](https://idfg.idaho.gov/rules). Idaho Department of
Fish and Game. **internal only**, confirmed; confidence medium.

Booklets: Big Game 2026 (4.05 MB), Upland Game, Turkey and Furbearer
2026–27 (7.95 MB), Migratory Game Birds 2026–27 (4.64 MB), Moose, Sheep and
Goat 2025–26 (4.13 MB) and Fishing 2025–27 (7.51 MB). The Hunt Planner is
an interactive tool with no documented API.

- **Coverage:** Idaho.
- **Access:** PDF downloads and web pages only. No key.
- **License:** IDFG's Terms: personal, non-commercial transitory viewing
  only; no copying, public display or mirroring.
- **robots.txt:** idfg.idaho.gov's `*` group disallows only `/web.config`
  and admin, comment, filter, `node/add`, search, user and oembed paths,
  so `/rules` and `/ifwis/` are allowed.
- **Updates and size:** yearly; negligible.
- **Use cases:** an owner-only season calendar, key dates entered by hand
  with a link to the booklet.
- **Personas:** hunter, angler.
- **Needs from core:** lifecycles, time and replay clock. **Effort** M.
- **Risks:** don't scrape the Hunt Planner or parse the booklets
  automatically. Season facts aren't copyrightable, but link out and enter
  by hand only what the owner wants.
- **Checked:** confirmed the booklet list and sizes, the Terms and
  robots.txt; the Hunt Planner page itself wasn't re-fetched. Evidence:
  [rules](https://idfg.idaho.gov/rules),
  [Terms](https://idfg.idaho.gov/terms),
  [robots.txt](https://idfg.idaho.gov/robots.txt).

---

## Grazing, mining and special designations

### BLM grazing allotments, pastures, sheep trailing routes and range improvements

[BLM_Natl_Grazing_Allotment layer 12](https://gis.blm.gov/arcgis/rest/services/range/BLM_Natl_Grazing_Allotment/MapServer/12).
BLM headquarters and BLM Idaho. **use**, confirmed; confidence high.

National allotment polygons (layer 12) with `ALLOT_NO`, `ALLOT_NAME`,
`GIS_ACRES`, `ADMIN_ST`, `ADM_OFC_CD`, `ADM_UNIT_CD`, `ST_ALLOT`,
`ACTIVE_DT` and `LAST_EDITED_EPOCH_TIME`; it calls itself "a subset …
intended for public release". BLM Idaho's range folder has
Grazing_Allotments, Grazing_Pastures, Permitted_Sheep_Allotments_and_Pastures,
Sheep_Allotments_and_Pastures_Permitted, Sheep_Trailing_Routes_Line,
Range_Improvement line, point and polygon layers, and Wild Horse and Burro
herd areas and HMAs.

- **Coverage:** national (the Idaho folder Idaho only). The researcher
  counted 297 allotments in the ring (not re-checked).
- **Access:** MapServer and FeatureServer queries under
  `gis.blm.gov/arcgis/rest/services/range/` and
  `gis.blm.gov/idarcgis/rest/services/range/`. No key.
- **License:** federal work, public domain (`copyrightText` "BLM Admin
  State").
- **robots.txt:** gis.blm.gov 404 (no rules).
- **Updates and size:** irregular; refresh monthly. Under 5 MB for the
  ring.
- **Use cases:** livestock-on-the-road risk on open-range highways; gate
  etiquette and sheep-trailing awareness for hikers and cyclists; a
  rancher's view of allotments.
- **Personas:** rancher, driver, cyclist, hiker.
- **Needs from core:** layer system. **Effort** S.
- **Risks:** no permittee names in the GIS; don't join it to BLM's
  rangeland administration (RAS) reports. Sheep-trailing dates aren't in
  the layers seen, so seasonal shading needs another source.
- **Checked:** confirmed the fields, the public-release statement, the
  Idaho service list and robots.txt; trailing-route dates weren't found.
  Evidence:
  [national layer](https://gis.blm.gov/arcgis/rest/services/range/BLM_Natl_Grazing_Allotment/MapServer/12?f=json),
  [Idaho range folder](https://gis.blm.gov/idarcgis/rest/services/range?f=json).

### BLM mining claims (MLRS, not closed)

[BLM_Natl_MLRS_Mining_Claims_Not_Closed](https://gis.blm.gov/nlsdb/rest/services/HUB/BLM_Natl_MLRS_Mining_Claims_Not_Closed/FeatureServer/0).
BLM (Mineral and Land Records System). **use**, confirmed; confidence
medium.

Polygons with `ID`, `CSE_NAME`, `STAGE_ID`, `BLM_PROD`, `CSE_TYPE_NR`,
`CSE_NR`, `LEG_CSE_NR`, `SF_ID`, `CSE_DISP`, `SRC`, `QLTY`, `CSE_META`,
`RCRD_ACRS`, `Created` and `Modified`. Data.gov says the geometries are
"primarily derived from Legal Land Descriptions", geocoded with the PLSS;
the layer itself has no description.

- **Coverage:** national. The researcher counted 1,792 claims in the
  valley box and 3,992 in the ring (not re-checked).
- **Access:** FeatureServer query, 2,000 records a page. Hub downloads
  (CSV, GDB, GeoJSON, KML, shapefile) through `gbp-blm-egis.hub.arcgis.com`
  (item `abec5ef96dc8495d9c29a01b30cc04ee`), listed on catalog.data.gov.
  No key.
- **License:** public domain: data.gov lists the
  [public-domain label](http://www.usa.gov/publicdomain/label/1.0/) and
  access level public.
- **robots.txt:** gis.blm.gov 404 (no rules). `mlrs.blm.gov` has
  `User-agent: *` with `Disallow: /`, allowing only `/s/$`,
  `/s/help-center`, `/s/article/`, `/s/topic/` and `/s/topiccatalog`
  (indented lines, which RFC 9309 permits): never fetch case pages.
  catalog.data.gov sets Crawl-delay 10; the hub host Crawl-delay 60.
- **Updates and size:** not stated (data.gov metadata dated Feb 11, 2025);
  refresh weekly. About 4k polygons in the ring, under 10 MB.
- **Use cases:** active claims for rockhounds ("don't prospect here");
  land-use context on the Owyhee front; claims opened and closed over time
  (lifecycles).
- **Personas:** rockhound, hiker, researcher, homeowner.
- **Needs from core:** layer system, lifecycles. **Effort** S.
- **Risks:** `CSE_NAME` can hold personal names, so keep it out of search
  and show it only on click. Drop `SF_ID` and `CSE_META` (internal).
  Polygons are approximate (aliquot parts). That unpatented claims stay
  open to public recreation is still unverified ⚠️: BLM's mining-claims
  page doesn't address it.
- **Checked:** confirmed the fields, license, PLSS-derived geometry,
  robots.txt for both BLM hosts and the download formats. "Updated daily
  in MLRS" and the ring counts weren't verified. Evidence:
  [layer](https://gis.blm.gov/nlsdb/rest/services/HUB/BLM_Natl_MLRS_Mining_Claims_Not_Closed/FeatureServer/0?f=json),
  [data.gov entry](https://catalog.data.gov/dataset/blm-natl-mlrs-mining-claims-not-closed),
  robots.txt for [data.gov](https://catalog.data.gov/robots.txt) and
  [MLRS](https://mlrs.blm.gov/robots.txt),
  [BLM mining claims](https://www.blm.gov/programs/energy-and-minerals/mining-and-minerals/locatable-minerals/mining-claims).

### BLM special designations and planning

[BLM Idaho special_designations folder](https://gis.blm.gov/idarcgis/rest/services/special_designations?f=json).
BLM Idaho and headquarters. **use**, corrected; confidence medium.

The Morley Nelson Snake River Birds of Prey National Conservation Area
(NCA), wilderness study areas (WSAs), areas of critical environmental
concern (ACECs), the Orchard training area's military impact areas, lands
potentially available for disposal (LPAD), and the PLSS and Master Title
Plats. BLM Idaho folders:

- `special_designations`: NLCS national monuments and NCAs, NLCS
  wilderness, and WSAs (current, released, historical).
- `planning`: Boise District Orchard Training Area Military Artillery
  Impact Area, Impact Area and Proposed polygons; land use planning.
- `lands`: ACEC (designated and historical), right-of-way line, point and
  polygon, SMA.
- `recreation`: recreation area polygons and site points.
- `cadastral`: PLSS and Master Title Plats (contents not re-checked).

National services: `lands/BLM_Natl_LPAD` (FLTFA, re-authorized 2018;
disposal types Sale, Exchange, Sale Exchange and Other),
`BLM_Natl_NLCS_WLD_WSA` (layer 0 wilderness, layer 1 WSA),
`BLM_Natl_NLCS_WSR` (wild and scenic rivers), `BLM_Natl_ACEC` and
`BLM_Natl_LandUsePlanningBoundaries`.

- **Coverage:** the ring **does** contain BLM WSAs, all in Oregon: the
  national WSA layer returned 5 polygons for the ring envelope (Honeycombs
  WSA in 2 parts, Upper Leslie Gulch, Wild Horse Basin and Slocum Creek;
  `ADMIN_ST` OR). BLM Idaho's WSA layer can't see them. The national
  wilderness layer returned none in the ring. The Birds of Prey NCA and
  the Orchard training area are in the ring.
- **Access:** MapServer and FeatureServer on `gis.blm.gov/idarcgis`
  (`special_designations`, `planning`, `lands`, `recreation`, `cadastral`)
  and `gis.blm.gov/arcgis` (`lands/BLM_Natl_LPAD`,
  `lands/BLM_Natl_NLCS_WLD_WSA`, `Cadastral/BLM_Natl_PLSS_CadNSDI`). No
  key.
- **License:** federal work, public domain.
- **robots.txt:** gis.blm.gov 404 (no rules).
- **Updates and size:** irregular. Under 10 MB for the ring without the
  PLSS; PLSS sections about 20 MB.
- **Use cases:** hazard areas (live-fire impact areas) on the Land lens;
  the Oregon WSAs (Leslie Gulch, Honeycombs) with their non-impairment
  rules; township, range and section for any point; future development,
  from BLM land identified for disposal near the valley.
- **Personas:** hiker, researcher, traffic researcher, shooter.
- **Needs from core:** layer system, places and search. **Effort** M.
- **Risks:** the NCA's rules (any seasonal shooting restrictions, for
  example) are still unverified ⚠️; BLM's NCA page answered 404 again.
  Right-of-way layers may carry holder names; check before use.
- **Checked:** confirmed the folder structure, the Orchard layers in
  `planning`, ACEC and rights-of-way in `lands`, the LPAD description, and
  no BLM wilderness in the ring. Refuted "no BLM WSA in the ring". Added
  the national wild and scenic rivers layer as a check. Evidence:
  [BLM Idaho services](https://gis.blm.gov/idarcgis/rest/services?f=json),
  folders [special_designations](https://gis.blm.gov/idarcgis/rest/services/special_designations?f=json),
  [planning](https://gis.blm.gov/idarcgis/rest/services/planning?f=json),
  [lands](https://gis.blm.gov/idarcgis/rest/services/lands?f=json) and
  [recreation](https://gis.blm.gov/idarcgis/rest/services/recreation?f=json);
  [national lands](https://gis.blm.gov/arcgis/rest/services/lands?f=json),
  [LPAD](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_LPAD/MapServer?f=json),
  [wilderness and WSA](https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_NLCS_WLD_WSA/MapServer?f=json)
  (plus one attributes-only query of layers 0 and 1 over the ring
  envelope).

---

## Law for help text

### Idaho trespass, navigable-stream and open-range statutes

[Idaho Code 6-202](https://legislature.idaho.gov/statutesrules/idstat/Title6/T6CH2/SECT6-202/)
and others. Idaho Legislature. **use** (help text, not data), corrected;
confidence high.

A summary for help text only, **never legal advice**:

- **Civil trespass (6-202):** entering or remaining on another's land
  without permission. Unfenced, uncultivated land must be posted (signs,
  or bright orange or fluorescent paint) at property corners and where
  streams, roads, gates and rights-of-way enter. Fenced land that
  **adjoins public land** must be posted along the fence at the corners
  adjoining public land, and where streams, roads, gates and rights-of-way
  enter from public land; other fenced or cultivated land needs no
  posting. Civil damages: at least $500, or treble damages where the
  damage exceeds $1,000. Posting doesn't bar access to navigable streams
  below the high-water mark.
- **Criminal trespass (18-7008):** a third offense within 10 years is a
  misdemeanor with higher penalties. It's a felony only when the trespass
  caused damage over $1,000 and the person has two or more prior
  violations in 10 years (the research said any third offense).
- **Navigable streams (36-1601):** the public may use them between the
  ordinary high-water lines for boating, swimming, fishing, hunting and
  recreation, and may cross private land only to portage around an
  obstruction, re-entering at the nearest safe point. **36-1603** ties
  hunting, fishing and trapping trespass to 18-7008 and forbids
  misrepresenting public land as private.
- **Open range (25-2118):** owners of livestock on open range ("all
  uninclosed lands outside of cities, villages and herd districts") have
  no duty to keep them off highways.

- **Coverage:** Idaho only; Oregon law differs for the Malheur County
  strip.
- **Access:** web pages, read by hand. No key.
- **License:** state law text, public.
- **robots.txt:** legislature.idaho.gov disallows `/wp-admin/`,
  committee-calendar views and a few plugin paths; `/statutesrules/` is
  allowed. It also blocks several named bots (Semrush, Ahrefs,
  PerplexityBot, Applebot and others).
- **Updates and size:** changes with legislative sessions.
- **Use cases:** help text with citations in the "Can I be here?" panel;
  an open-range warning on rural Idaho highways.
- **Personas:** hiker, hunter, angler, driver, landowner.
- **Needs from core:** the app shell (help panels). **Effort** S.
- **Risks:** never present it as legal advice. Corner crossing: no Idaho
  statute or ruling found (not re-checked) ⚠️, so show such parcels as "no
  known legal access". BLM stay limits: 43 CFR 8365.1-2 wasn't re-read
  (eCFR redirected to an unblock page) ⚠️. The Boise NF limit of 14 days
  in 30 is confirmed (FO 0402-00-62).
- **Checked:** corrected the 18-7008 felony threshold and the posting rule
  for fenced land next to public land; added 36-1603's misrepresentation
  clause; confirmed 36-1601's portage rule, 25-2118's open-range
  definition and robots.txt. Evidence:
  [6-202](https://legislature.idaho.gov/statutesrules/idstat/Title6/T6CH2/SECT6-202/),
  [18-7008](https://legislature.idaho.gov/statutesrules/idstat/Title18/T18CH70/SECT18-7008/),
  [36-1601](https://legislature.idaho.gov/statutesrules/idstat/Title36/T36CH16/SECT36-1601/),
  [36-1603](https://legislature.idaho.gov/statutesrules/idstat/Title36/T36CH16/SECT36-1603/),
  [25-2118](https://legislature.idaho.gov/statutesrules/idstat/Title25/T25CH21/SECT25-2118/),
  [robots.txt](https://legislature.idaho.gov/robots.txt).

---

## Ideas by persona

From the research pass, none approved, with the verifier's corrections
applied and marked. Each lists the sources it would use and what it needs
from core. These extend the hiker, camper, hunter and angler list in
[ch. 16](../16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water).

### Hiker, camper, anyone outdoors

- **"Can I be here?"** Tap any point on the 2D or 3D map. The answer
  stacks the evidence with citations: who manages it (PAD-US, SMA, IDL,
  FWS), PAD-US's public-access code, any active closure order (BLM, Boise
  NF), today's fire-restriction stage for that zone, stay limits (Boise NF
  14 days in 30; BLM's still ⚠️), and the nearest legal access. It carries
  a "not a legal determination" banner, in line with the federal "not
  legal documents" statements (the IDL disclaimer the research cited
  wasn't found, so the banner is our own). When sources disagree (SMA says
  PRIVATE, PAD-US says WMA), it says so. In the Oregon strip it says "no
  data (Oregon)" unless Oregon sources are added (correction 1).
  *Sources:* PAD-US 4.1, BLM SMA, IDL State Ownership, IDL fire
  restrictions, BLM Idaho closures, Boise NF orders, USFWS refuge
  boundaries, Idaho Code 6-202, 18-7008 and 36-1601. *Needs:* selection
  and picking, layer system, lifecycles, evidence and review.

### Hunter, hiker, researcher

- **Landlocked public land finder.** Flag every public parcel in the ring
  with no known legal access, and report the acres locked up by manager.
  The research's test was "touches no public road, MVUM route, GTLF route,
  MAPLand or PLAD easement, or Access Yes property"; the verifier's fixes
  (correction 9): accessibility is connectivity through public parcels (a
  parcel sharing an edge with an accessible public parcel is accessible
  too); OpenStreetMap ways are candidates, not proof of a public
  right-of-way; navigable streams give water access only, with portage on
  the bank; Access Yes is seasonal and for hunting and fishing only, so it
  doesn't count as general access; and it runs per state. Parcels touching
  only at a corner show as "no known legal access (corner crossing
  unsettled in Idaho ⚠️)", never as a route. *Sources:* PAD-US 4.1, BLM
  SMA, IDL State Ownership, USFS MVUM, BLM Idaho GTLF, BLM PLAD and
  MAPLand easements, USFS MAPLand easements, IDFG Access Yes!. *Needs:* a
  regular OpenStreetMap load, layer system, areas.

### OHV rider, dirt-bike rider, e-biker

- **"What can I ride on this date?"** Pick a vehicle class (ATV,
  motorcycle, high-clearance car, e-bike class 1, 2 or 3) and a date. MVUM
  routes are coloured open or closed from their dates-open fields; the
  picker maps our classes onto all 14 MVUM classes (correction 11). BLM
  routes show OPEN, LIMITED or CLOSED, and undesignated ones say "not
  designated: check the resource management plan or travel plan", never
  "no travel plan" (about 4,940 of the about 7,000 BLM miles in the ring;
  the research's 12,900 of 15,000 counted routes off BLM land, correction
  2). Routes with a seasonal restriction carry a flag and a link to the
  travel plan, since GTLF has no season dates. Forest closure orders
  override both. Scrub the time slider through the year to watch MVUM's
  seasonal gates open and close. *Sources:* USFS MVUM, BLM Idaho GTLF,
  Boise NF orders, BLM Idaho closures. *Needs:* time and replay clock,
  lifecycles, layer system, 3D engine.

### Hunter

- **A season clock** (owner only until IDFG answers). Game management
  units and controlled hunt areas, areas closed to hunting, GMUs under the
  motorized-hunting rule (Aug 30–Dec 1), WMA vehicle seasons (for example
  the Boise Front roads open May 1–Nov 15), and Access Yes properties
  active between their access dates. Key season dates are entered by hand
  with a link to the booklet. *Sources:* IDFG open data (GMUs, controlled
  hunts, restrictions, WMAs), IDFG Access Yes!, IDFG booklets, USFS MVUM.
  *Needs:* lifecycles, time and replay clock, places and search.

### Angler and floater

- **Public water, private banks.** Highlight navigable reaches where Idaho
  Code 36-1601 allows public use below the high-water line, with IDFG's
  fishing and boating access sites and Access Yes fishing properties. A
  note explains that crossing private banks is allowed only to portage.
  Combined with the water plugin's river flows for "can I float today".
  *Sources:* Idaho Code 36-1601, IDFG fishing and boating access sites
  (fields not re-checked), IDFG Access Yes!, PAD-US 4.1. *Needs:* layer
  system, places and search.

### Fire watcher

- **Fire-restriction history.** Each zone's stage changes (Treasure
  Valley, Owyhee, West Central and the others the ring crosses) become
  lifecycles, so the time bar shows when Stage I or II was in force. The
  research proposed building them from `DateEnacted` and `DateRescinded`;
  the layer holds only the current state, so the history starts with our
  own polling, Stage None closes the previous lifecycle, and
  `UpcomingStage` gives advance feed items (correction 6). Fire closure
  areas (the Big Grass Fire closure to Oct 15, 2026) go on the same
  timeline, linked to the 511 road events already recorded. A stage
  change posts to the Valley Feed. *Sources:* IDL fire restrictions, BLM
  Idaho closures, Boise NF orders. *Needs:* lifecycles, Valley Feed, time
  and replay clock.

### Wildlife watcher

- **A winter-wildlife layer.** The research proposed IDFG's "Big Game
  Winter Range and Migration Priority Areas", shaded by season; the
  verifier found that layer is five coarse statewide priority complexes,
  not mapped winter range, so it shows as "priority area" context only
  (correction 12). The closures that protect wildlife are confirmed: the
  Boise River WMA's Cornell segment is closed Feb 1–Apr 14, and dogs must
  be leashed Nov 16–Apr 30. Overlaying COMPASS animal-involved crashes and
  the wildlife plugin's roadkill data to find highway stretches through
  winter range needs real winter-range data first. *Sources:* IDFG open
  data (priority areas, WMAs), BLM Idaho closures. *Needs:* lifecycles,
  layer system, time and replay clock.

### Traffic researcher (the core project)

- **Where can the valley grow?** Land status around the urban edge:
  private against public; BLM land potentially available for disposal;
  state endowment land IDL can sell or lease for development; Reclamation,
  WMA and refuge land that won't develop. Overlay COMPASS permits, plats
  and 2055 forecasts to explain where new traffic will come from.
  *Sources:* BLM SMA, BLM special designations (LPAD), IDL State
  Ownership, PAD-US 4.1. *Needs:* areas, layer system.

### Rural driver and commuter on ring highways

- **Open-range warning.** Highways that cross BLM and USFS grazing
  allotments (with livestock type) and sheep trailing routes outside herd
  districts, where Idaho Code 25-2118 puts no duty on owners to keep
  animals off the road; joined with crashes involving livestock, and
  seasonal shading for sheep trailing. Two gaps: herd-district boundaries
  weren't found, and trailing dates aren't in the layers seen.
  *Sources:* BLM grazing allotments and Idaho range layers, USFS range
  allotments, Idaho Code 25-2118. *Needs:* layer system, lifecycles.

### Rockhound and prospector

- **Active mining claims** (about 3,990 in the ring by the researcher's
  count, many on the Owyhee front around Silver City), shown as
  approximate PLSS polygons with case number and status, and a note that
  prospecting on someone's claim isn't allowed. Claim names appear only on
  click and stay out of search. *Sources:* BLM MLRS mining claims.
  *Needs:* layer system, lifecycles.

### Hiker, recreational shooter, drone pilot

- **Hazard and special-rule areas:** the Orchard training area's
  artillery and impact areas inside the Birds of Prey NCA, the NCA
  boundary, and Idaho Roadless classes, with a hazard pattern, each linked
  to the managing agency's rules page (the NCA's own rules are still ⚠️).
  *Sources:* BLM special designations and planning, USFS boundaries and
  designations (Idaho Roadless). *Needs:* layer system.

### Homeowner or land buyer (private, with `parcels`)

- **What's next to my parcel** (owner only): adjacent public land and its
  manager, grazing allotments, active mining claims, BLM rights-of-way
  (power lines), IDL leasing activity and public access easements. Ada and
  Canyon parcels stay in the private plugin; nothing per parcel is
  published. Right-of-way and lease layers get checked for holder and
  lessee names first. *Sources:* Canyon County parcels, PAD-US 4.1, BLM
  grazing allotments, BLM MLRS mining claims, IDL State Ownership, BLM
  PLAD and MAPLand easements. *Needs:* private plugins, selection and
  picking.

### Anyone (3D showcase)

- **An ownership drape in 3D.** Land-manager polygons draped on the 1 m
  terrain, with thin extruded "fences" along manager boundaries; restricted
  and closed access shown with hatching and labels, not red and green
  alone. A scripted flyover of the Boise Front shows city reserves, the
  WMA, BLM, endowment sections and the national forest, with their access
  rules appearing as you pass. The verifier: draw the fences only at close
  zoom, simplified and labelled approximate, since the state-section
  checkerboard gets noisy and the lines aren't surveyed (correction 15).
  *Sources:* PAD-US 4.1, BLM SMA, IDL State Ownership, USFS boundaries and
  designations. *Needs:* 3D engine, layer system.

### Researcher and civic

- **A public-access ledger for the ring:** acres by manager and access
  code, acres landlocked, MAPLand easements digitized so far, and
  endowment land sold or acquired, recomputed whenever PAD-US, EDW or IDL
  changes so the trend shows. *Sources:* PAD-US 4.1, BLM SMA, IDL State
  Ownership, BLM PLAD and MAPLand easements, USFS boundaries and
  designations. *Needs:* areas, evidence and review.

### Stargazer and camper

- **Dark, legal and reachable.** Open-access public land (PAD-US OA)
  reachable on a passenger-vehicle MVUM road or an OPEN BLM route, ranked
  by darkness from the sky plugin's light-pollution layer
  ([sky sources](sky.md)), and filtered out when fire restrictions ban
  campfires. *Sources:* PAD-US 4.1, USFS MVUM, BLM Idaho GTLF, IDL fire
  restrictions. *Needs:* layer system, lifecycles.

---

## Design notes

The researcher's proposals for a public `lands` plugin (IDFG layers
internal; parcels in the existing private `parcels` plugin), with the
verifier's corrections folded in and marked. None is decided.

1. **Layered ownership with evidence, not one "truth" layer.** No source is
   right everywhere: SMA shows the surface manager, not the owner, and
   hides overlay units (Deer Flat NWR over Reclamation's Lake Lowell);
   PAD-US is complete and adds access codes and designations but lags a
   year; IDL is authoritative for state land and FWS realty for refuges.
   (The research also said USFS Surface Ownership is weekly and newer than
   PAD-US; that describes the `PADUS FS` staging datasets, correction 3.)
   Each source is stored as its own rows in a proposed `core.land_unit`
   (geometry, manager, owner type, designation, `Pub_Access`, source,
   source ID, valid from and to, version), and disagreements go through
   core's evidence and review, as lanes and intersections do; the point
   checks already found suspicious SMA values. The research proposed one
   winner per area (agency layer, then PAD-US, then SMA); the verifier
   calls that the wrong model: keep owner, manager and designation as
   separate attributes, let designations stack as overlays, and take
   authority per manager (correction 4).
2. **Rules and seasons are lifecycles.** They map onto the `evt` lifecycle
   contract, which gives the time slider and "what was active at this
   moment": MVUM dates open per vehicle class, PLAD seasonal easements, WMA
   vehicle seasons and winter closures, Access Yes dates, fire-restriction
   stages, and BLM and USFS closure orders. GTLF's season data is a yes/no
   flag with no dates, so it can't feed this (correction 2), and
   fire-restriction history comes only from our own polling (correction
   6). Recurring windows need a core addition. The research proposed a
   yearly recurrence rule, so "Jun 16–Oct 15 every year" isn't 30 rows,
   shared with trails (mud closures) and water (float season); the
   verifier says yearly windows aren't enough and proposes an RFC 5545
   subset with weekday sets and daily hours, plus override lifecycles
   (correction 5).
3. **Rule-bearing route segments.** MVUM and GTLF become `lands.route_rule`
   rows (segment geometry plus per-vehicle-class permissions and season
   windows), matched to the OpenStreetMap ways already loaded with the
   shared segment matcher, so the "what can I ride" filter can also colour
   OpenStreetMap tracks. (The Oct 7 load kept roads only; paths need the
   separate pass [ch. 16](../16-ideas-and-personas.md#hiker-backpacker-camper-hunter-angler-floater-lands-trails-water)
   mentions.) The landlocked analysis uses the same roads plus MVUM, GTLF
   and easements as its legal-access graph. The verifier: the matched
   result is an ODbL derivative, the agency geometry stays the authority,
   and OpenStreetMap colouring carries a match-confidence flag
   (correction 10); OpenStreetMap ways aren't proof of a public
   right-of-way (correction 9).
4. **Fetch plan,** all through core's polite HTTP and the shared ArcGIS
   reader:
   - BLM, USFS EDW, IDL ownership and FWS: monthly or weekly queries
     clipped to the ring, 2,000 a page, a few seconds apart. Not by
     envelope: fetch object IDs for the ring geometry, then pages by ID or
     offset (correction 7).
   - IDL fire restrictions: hourly June–October, daily otherwise (the
     zones, under 100 KB).
   - PAD-US: one hand download a year (the 150 MB Idaho GDB, plus Oregon's
     if the ring keeps its Oregon strip), or a bounding-box read of the
     Source Cooperative GeoParquet, a public-domain re-host by the
     Boettiger Lab, as a download the owner approves (correction 16).
   - IDFG layers: yearly, with the regulations.
   - Closure orders (BLM Idaho, Boise NF): no GIS exists, so they're
     entered by hand as lifecycles with the order PDF linked. A polite
     weekly page check could alert the owner, without fetching PDFs in
     bulk.

   Ring sizes from the research's samples:

   | Layer | In the ring | Re-checked |
   |---|---|---|
   | SMA polygons | about 2,150 (Idaho part) | No |
   | IDL state parcels | about 1,400 | No |
   | BLM GTLF routes | about 25,000 (about 15,070 GIS mi; about 7,000 on BLM land) | Yes, corrected |
   | MVUM | 512 road segments (1,160 mi) and 178 trail segments (513 mi), Boise NF only | No |
   | Non-closed mining claims | 3,992 | No |
   | BLM allotments | 297 | No |
   | USFS allotments | 27 | No |
   | Idaho Roadless areas | 26 | No |
   | BLM easement lines | 57 | No |
   | USFS MAPLand easements | 119 | No |
   | Designated wilderness | 0 (BLM queried; USFS not) | Partly |
   | BLM WSAs | 5 polygons (4 WSAs), all in Oregon; the research said 0 | Yes, refuted |

   Total storage is well under 200 MB; the raw inputs are bigger
   (correction 16).
5. **Rendering.** Polygons are cut into self-hosted tiles (PostGIS through
   `/api/`, or PMTiles in `basemap/`) and draped on the terrain in 3D.
   Following [ch. 13](../13-visual-design.md), access is never red and
   green alone: open is a solid tint, restricted a diagonal hatch, closed
   a cross-hatch with an icon; manager colours come from the lens tokens.
   Boundary "fences" are thin extruded walls in the GL engine, at close
   zoom only and labelled approximate (correction 15). The "Can I be
   here?" panel is a stacked card per source, each with its license credit
   and disclaimer: USFS's "not legal documents" and BLM's "neither legal
   documents nor land surveys". The IDL disclaimer the research quoted
   wasn't found, so IDL cards carry our own "not a legal determination"
   line.
6. **Licensing summary:**
   - Public domain: PAD-US, all the BLM layers (including MLRS claims),
     USFS EDW, FWS.
   - No license stated, credit the agency: IDL ownership and fire
     restrictions (corrected: there's no disclaimer on either).
   - Internal until asked: IDFG. Its website Terms allow only "personal,
     non-commercial transitory viewing", with no open-data carve-out,
     though some items grant unrestricted use.
   - Private plugin, aggregates only: Canyon County parcels, like Ada's.
   - Avoid: Reclamation Land Ownership (its terms forbid downloading,
     derived products and dissemination into other systems) and NCED
     (frozen since Jan 2025, superseded by PAD-US).
7. **Ethics and privacy:**
   - Drop at ingest (correction 7): Access Yes `contactname` and `bidid`;
     PLAD `APRSD_VALUE` and `PYMNT_MADE`; `created_user` and
     `last_edited_user` on IDL ownership, IDL fire restrictions and
     Canyon County parks; MLRS `SF_ID` and `CSE_META`.
   - Keep MLRS claim names out of search; they can be personal names.
   - Never touch `mlrs.blm.gov` (robots.txt disallows it); claimant names
     live there.
   - Check IDL land-use (lease) layers and BLM rights-of-way for lessee
     or holder names before use.
   - Canyon parcels: no owner names in the public layer, but addresses and
     values make it private.
   - The landlocked analysis labels parcels "no known legal access". It
     never draws a crossing route or names adjacent private owners.
   - The research says two once-official fire-information domains,
     `idahofireinfo.com` and `firerestrictions.us` (bare domain), now
     serve gambling content, and proposes blocklisting both and checking
     old links in the docs. Unverified and deliberately not fetched ⚠️
     (correction 6). No page in this repo links either domain (checked
     when writing this page).
8. **Robots.txt findings for core** (corrected by the verifier,
   correction 8):
   - `_group()` in `ingest/http.py` returns only the first matching group
     (the first specific group, else the first `*` group), while RFC 9309
     §2.2.1 says matching groups must be combined. Real cases:
     www.canyoncounty.id.gov's second `*` group adds a Disallow the parser
     ignores; www.sciencebase.gov's first `*` group is the Cloudflare
     `Allow: /`, so today's parser reads ScienceBase as allowed.
   - A plain merge still allows ScienceBase, because the equal-length
     `Allow: /` and `Disallow: /` tie and RFC 9309 says ties should go to
     Allow (`allowed()` in `ingest/http.py` breaks ties toward Allow
     today). Since we already match paths case-insensitively as a
     deliberately stricter choice, the verifier also proposes that
     Disallow wins exact ties, which the RFC's "should" permits. Tests for
     both files' shapes.
   - ScienceBase also disallows Claude-User, so research agents shouldn't
     fetch it.
   - Hub hosts (IDFG, IDL, BLM's hub) set Crawl-delay 60 and
     catalog.data.gov 10. The data sits on `services*.arcgis.com` and
     `gis.blm.gov`, which have no rules, but pace gently anyway.
   - `gis1.idl.idaho.gov/robots.txt` redirects to an HTML error page: no
     rules, which the `<html` check already gives. `apps.fs.usda.gov`'s
     403 is correctly "no rules" (RFC 9309 §2.3.1.3).
   - `landfoliogis.idl.idaho.gov`, `gis2.idaho.gov` and
     `edits.nationalmap.gov` were unreachable or answered 503: disallowed
     for now; retry later or through the local helper.
9. **Scope gaps:**
   - The ring has no designated wilderness (BLM's layer queried; USFS
     plausible but not queried), but it does have four BLM WSAs in Oregon.
     If wilderness matters to the owner, the lands area could reach the
     whole Boise NF and the Owyhee wildernesses (core areas allow
     per-plugin areas).
   - The Oregon strip: Idaho-only sources return nothing there
     (correction 1).
   - Corps of Engineers land (Lucky Peak) wasn't researched separately;
     PAD-US covers it.
   - Herd-district boundaries (where open range doesn't apply) weren't
     found.
   - Malheur County, Oregon's tax lots (ORMAP) weren't verified.
10. **Items the research left ⚠️,** and where they stand after
    verification:

    | Item | Status |
    |---|---|
    | The 2001 Roadless Rule rescission | Confirmed from the Federal Register (USFS boundaries above) |
    | Deer Flat NWR seasonal rules | Confirmed from the FWS rules page |
    | Boise NF stay limit | Confirmed: 14 days in 30 (FO 0402-00-62) |
    | BLM's 14-day stay limit (43 CFR 8365.1-2) | Still ⚠️: eCFR redirected to an unblock page |
    | Birds of Prey NCA shooting rules | Still ⚠️: BLM's NCA page answered 404 |
    | Unpatented mining claims staying open to recreation | Still ⚠️: BLM's page doesn't say |
    | Corner crossing in Idaho | Still ⚠️: no statute or ruling found |

---

## Design corrections from verification

The verifier checked the design against official pages, the ArcGIS REST
metadata and robots.txt, with the few attribute-only queries listed under
Requests made. The corrections, numbered as the notes and ideas refer to
them:

1. **Oregon coverage gap.** The ring (−117.30 to −115.60) includes a strip
   of Malheur County, Oregon: Ontario, Nyssa, Vale, Lake Owyhee, Leslie
   Gulch and Succor Creek. BLM Idaho's SMA and GTLF both returned 0 for an
   Oregon box inside the ring, and the same holds for IDL ownership, IDL
   fire restrictions, IDFG, Access Yes and the Idaho statutes; the PAD-US
   Idaho file is clipped to Idaho. The national NLCS layer shows four BLM
   WSAs (five polygons) in that strip, so "no BLM WSA in the ring" was
   wrong. Two options: (a) clip the `lands` area to Idaho and show "no
   data (Oregon)", never implying private; or (b) add Oregon sources:
   national SMA, BLM Oregon travel data, PAD-US Oregon, ODFW, Oregon fire
   restrictions and Oregon trespass law, which differs. Pick one before
   building "Can I be here?" (question 2).
2. **GTLF was misread in three places.** (a) `PLAN_SEASON_RSTRCT_CODE` is
   only YES/NO/UNK and the layer has no season dates, so "GTLF season codes
   become lifecycles" is impossible: show "seasonal restriction: see
   travel plan" (with `TMP_ID` and `NEPA_DOC_NUM`) and enter windows by
   hand only where the owner wants them. (b) The layer includes external
   connectivity routes, which BLM calls non-authoritative. By `BLM_MILES`
   the ring has about 7,000 BLM miles, about 4,940 (about 70%) of them
   undesignated; "about 12,900 of 15,000 BLM miles" counted about 7,900
   miles off BLM land. (c) An undesignated BLM route falls under the
   area's OHV designation in the resource management plan, and BLM Idaho
   publishes no OHV-area layer, so the map must say "not designated: check
   the RMP or travel plan", never "no travel plan".
3. **USFS "weekly and more current than PAD-US" is misattributed.** It
   describes the `PADUS FS …` staging datasets (`EDW_PADUS_01`), which USFS
   says are "not intended for regular use". Surface Ownership Parcels was
   refreshed Oct 4, 2026, with no stated cadence.
4. **"One winner per area" is the wrong model.** Owner, manager and
   designation are different attributes: store them separately and let
   designations (an NWR over Reclamation land, a WMA, an NCA) stack as
   overlays. Authority is per manager: IDL for state land, FWS realty for
   refuges, USFS Surface Ownership for national forest land, SMA for BLM
   surface, PAD-US Fee and Easement for local, NGO and easement land.
   Never use PAD-US Proclamation (or an undissolved combined layer) for
   access. The USGS web views lack `Own_Type`, `Own_Name` and the UK code;
   use the GDB or GeoParquet for owner fields.
5. **Lifecycles need more than yearly recurrence.** The Deer Point order
   runs weekdays 6 a.m.–6 p.m. (FO 0402-01-122); GTLF limits include time
   of day; Deer Flat islands close Feb 1–Jun 14 (some to Jun 30) and Lake
   Lowell boating runs Apr 15–Sep 30; PLAD's seasonal start and end are
   free text. Propose an RRULE-style recurrence (an RFC 5545 subset: yearly
   date windows, weekday sets, daily hours) evaluated in America/Boise
   local time, plus "override" lifecycles (forest and BLM orders) that
   beat the MVUM. Keep the raw text beside the parsed rule for review.
6. **Fire restrictions are current-state only.** The valley's three zones
   are at Stage None with `DateEnacted` Sep 3, 2026, the date restrictions
   were lifted. History can come only from our own polling (`raw.record`
   versions). Map Stage None to closing the previous lifecycle and use
   `UpcomingStage` for advance feed items. The ring crosses more zones than
   the valley box's three. Hourly polling in season is fine; the layer is
   edited a few times a year. The gambling-domain claim wasn't verified
   and the domains weren't fetched; label it unverified in DECISIONS if it
   goes there.
7. **Fetch mechanics.** Don't page by envelope: polygons and lines that
   cross an envelope's edge come back twice or split. Use `returnIdsOnly`
   with the ring geometry, then fetch by `objectIds` in batches of up to
   2,000, or by `resultOffset` with `orderByFields=OBJECTID` where
   `supportsPagination` is true (USFS EDW MapServers may not support
   offsets). Request `f=geojson` or `pbf` with `outSR=4326` and dedupe on
   `GlobalID`. Hub hosts set Crawl-delay 60 and catalog.data.gov 10; keep
   a few seconds between pages elsewhere. Drop the personal and staff
   fields listed in design note 7 at ingest.
8. **Robots.txt core fix.** Confirmed: `_group()` returns only the first
   matching group, against RFC 9309 §2.2.1. The Canyon County and
   ScienceBase files are real cases. A plain merge still allows
   ScienceBase (equal-length tie goes to Allow), so also propose
   Disallow-wins on exact ties, with tests for both shapes. Research
   agents shouldn't fetch ScienceBase (it disallows Claude-User); the
   verifier fetched its item page once before reading robots.txt and
   stopped. The `gis1.idl.idaho.gov` redirect and the `apps.fs.usda.gov`
   403 are both handled correctly as "no rules".
9. **Landlocked-land analysis.** Accessibility is graph connectivity over
   public parcels, not "touches a road": a parcel sharing an edge with an
   accessible public parcel is accessible. OpenStreetMap ways aren't proof
   of a legal public right-of-way; use public-road evidence (highway
   district and county road status) and treat OpenStreetMap tracks as
   candidates. Navigable streams (36-1601) give water access between the
   high-water lines, with only portage rights on the bank. Access Yes is
   seasonal and for hunting and fishing only, so it isn't general legal
   access. Count only edge adjacency; corner-only contact is "no known
   legal access (corner crossing unsettled ⚠️)". Run it per state: Oregon
   parcels can't be assessed with Idaho data.
10. **OpenStreetMap matching and licensing.** Matching MVUM and GTLF
    attributes onto OpenStreetMap ways creates a derived database:
    anything published from it is ODbL with "© OpenStreetMap
    contributors", while the agency attributes stay public domain. Keep
    the legal source geometry as the authority and show OpenStreetMap
    colouring with a match-confidence flag, so an OpenStreetMap track is
    never implied to be legal by proximity.
11. **MVUM detail.** Only `SYMBOL` 1, 2, 3, 4, 11 and 12 are Forest
    Service system roads with OHV data. Layers 4 and 5 repeat 1 and 2, so
    query 1 and 2 only. "Dates open" is legality, not conditions. The
    vehicle picker should map our classes onto all 14 MVUM classes,
    including tracked and other OHVs above and below 50 inches.
12. **Wildlife idea.** IDFG's priority-areas layer is five coarse SO 3362
    complexes statewide, not mapped winter range: present it as "priority
    area", not habitat, and make no collision-hotspot claims from it. The
    Boise River WMA rules are confirmed: Boise Front roads May 1–Nov 15,
    Charcoal Sep 1–Dec 31, leashes Nov 16–Apr 30, the Cornell portion
    closed Feb 1–Apr 14.
13. **Roadless.** Confirmed from the Federal Register API: the proposed
    rescission of the 2001 rule (Aug 20, 2026; 2026-16965, 91 FR 53827),
    comments extended to Oct 6, 2026 (2026-18648), and the Idaho and
    Colorado rules retained (the Aug 29, 2025 notice). Idaho's roadless
    areas fall under the 2008 Idaho rule, so the effect in the ring is
    minimal; show the Idaho rule's seven classes.
14. **Statute help text.** The 18-7008 felony needs damage over $1,000
    plus two priors in 10 years; fenced land next to public land must be
    posted at the fence corners and entry points from public land;
    36-1603 also bars misrepresenting public land as private; the Boise NF
    stay limit is 14 days in 30 (FO 0402-00-62). Still ⚠️: BLM stay
    limits, the Birds of Prey NCA rules, recreation on unpatented claims
    and corner crossing.
15. **3D fences.** Extruded fences along every manager boundary will be
    noisy across the checkerboard of state sections, and the boundaries
    aren't surveyed: draw them only at close zoom, simplified, labelled
    approximate. The access patterns (solid, hatch, cross-hatch with icon)
    meet [ch. 13](../13-visual-design.md); keep them.
16. **Sizes and versions.** Ring storage stays small, but the raw inputs
    don't: PAD-US's Idaho zip is 150 MB and Oregon's 291 MB; the MVUM
    national road GDB is 118 MB. Prefer service queries clipped to the
    ring, or a bounding-box read of the PAD-US GeoParquet as a download
    the owner approves. Whether PAD-US 4.1 is still the newest release
    couldn't be checked (www.usgs.gov 504 or timeout); the USGS views
    still show `dataLastEditDate` 2025-06-11, though their item metadata
    changed Jul 30, 2026. Re-check before the first load.
17. **Verdicts.** None flips to avoid. GTLF, USFS boundaries, IDL
    ownership, IDFG open data, special designations, Canyon County and
    the statutes have corrected fields. IDPR stays unverifiable and needs
    an owner action; Reclamation and NCED stay avoid.

---

## Open questions

For the owner, one at a time. Question 2 and the `edits.nationalmap.gov`
part of question 14 were added when writing this page, from the
verifier's findings; questions 3, 4, 5, 8, 10, 11 and 13 are reworded to
carry its corrections.

1. **A first `lands` slice?** Suggested: PAD-US 4.1 (hand download), BLM
   SMA (Idaho), IDL State Ownership, USFS administrative boundaries,
   districts, Idaho Roadless and MVUM, BLM Idaho GTLF, IDL fire
   restrictions as lifecycles, and the "Can I be here?" panel. Then IDFG,
   easements, allotments and mining claims.
2. **Oregon:** clip the `lands` area to Idaho and show "no data (Oregon)"
   in the Malheur County strip, or add Oregon sources (national SMA, BLM
   Oregon travel data, PAD-US Oregon, ODFW, Oregon fire restrictions and
   Oregon trespass law)? Needed before "Can I be here?" is built
   (correction 1).
3. **IDFG:** may the owner (or a draft from us, kept in the private files)
   ask IFWIS whether the open-data layers (WMAs, GMUs, Access Yes, hunting
   restrictions, priority areas) may be republished in our tiles, given
   the website Terms allow only personal, non-commercial viewing? Until
   then they stay owner-only.
4. **PAD-US:** a hand download of the 150 MB Idaho GDB from ScienceBase in
   the owner's browser (its operator blocks all bots, so never scripted),
   a bounding-box read of the Source Cooperative GeoParquet re-host, or
   paging the USGS ArcGIS views (reduced schema, no owner fields)? The
   research called ScienceBase's robots.txt ambiguous; the verifier reads
   the operator's own section as a block on all bots.
5. **Robots.txt fix:** change `ingest/http.py` to merge same-agent groups
   as RFC 9309 §2.2.1 requires, and also let Disallow win exact ties (the
   verifier's addition, since a plain merge still allows ScienceBase)? A
   small core change with tests for the Canyon County and ScienceBase
   shapes.
6. **Canyon County:** ask the Assessor's Plat Room for FTP access (which
   needs credentials), or keep to the public FeatureServer (no owner
   names) as a private `parcels` source like Ada's?
7. **Reclamation:** its terms forbid downloads, derived products and
   dissemination. Rely on SMA and PAD-US for Arrowrock and Lake Lowell, or
   ask Reclamation?
8. **Recurring lifecycles in core:** should seasons and rules (MVUM dates,
   WMA seasons, Access Yes dates, hunting seasons, refuge closures) use a
   new recurrence feature in core, shared with trails' mud closures and
   the water plugin's float season? The verifier proposes an RFC 5545
   subset (yearly windows, weekday sets, daily hours, America/Boise) plus
   override lifecycles for orders (correction 5).
9. **Closure orders** (BLM Idaho, Boise NF) have no GIS: enter them by
   hand as lifecycles with the PDF linked, and optionally run a polite
   weekly page-change check that alerts the owner?
10. **The landlocked-land analysis:** publish the ring totals and maps, or
    keep it owner-only? Proposed rule: "no known legal access", never
    drawing corner-crossing routes, computed per state with the
    verifier's connectivity rules (correction 9).
11. **Extend the `lands` area** beyond the ring (the whole Boise NF, the
    Owyhee wildernesses)? The ring has no designated wilderness, though
    it does hold four BLM WSAs in Oregon.
12. **Fire-restriction polling:** hourly June–October, daily otherwise. OK?
13. **Repurposed fire domains:** the research says `idahofireinfo.com` and
    `firerestrictions.us` now serve gambling content (unverified ⚠️; not
    fetched). Blocklist them in `tools/check_public.py` or a docs link
    checker anyway, or have the owner look first? No doc links them today.
14. **Unreachable hosts:** have the local helper check `gis2.idaho.gov`
    (IDPR state parks), `landfoliogis.idl.idaho.gov` and Malheur County's
    ORMAP terms from the owner's network, and retry
    `edits.nationalmap.gov`'s robots.txt (503 on Oct 7)?
