# 2. The Treasure Valley signal system

This chapter covers who owns and runs the lights in Ada and Canyon counties,
the technology involved, how timing is done today, what has been tried, and
where the gaps are.

> **Research status (Oct 2026).** Facts are sourced inline. Some agency pages
> (achdidaho.org, ktvb.com, boisedev.com) block automated fetching, so a few
> items rest on search-result excerpts and are marked ⚠️. Verify those before
> citing them publicly.

---

## 2.1 Summary

1. **One agency runs nearly all of it in Ada County.** The Ada County Highway
   District (ACHD) is Idaho's only countywide highway district. It owns and
   operates all public roads in Ada County except state highways, and it also
   runs (by agreement) many or all of the ITD signals on state highways
   there. One agency means one budget, one central system, and one elected
   commission to engage.
2. **ACHD has just finished a major technology refresh.** In 2024 it awarded
   Econolite a countywide contract for Centracs Mobility central software and
   Cobalt ATC controllers. In April 2025 it opened a $29.4M Franklin Traffic
   Operations Center. The hardware and software can now support modern
   performance measurement.
3. **The bottleneck looks like operations funding and staff time, not
   equipment.** COMPASS's FY2026 Resource Development Plan lists, as
   *unfunded* needs:
   - about $730K of signal retiming, including downtown Boise's 100 signals
     for $150K;
   - about $6M of signal performance measures (SPM/ATSPM) on major corridors;
   - a $125K study to coordinate signal corridors that ITD and local agencies
     run jointly.

   By comparison, ACHD's FY2026 budget is about $257M.
4. **The region has tried adaptive signals once, and it failed.** A
   Rhythm Engineering (InSync) adaptive system at 22 locations on Eagle,
   Chinden, State and Glenwood was scrapped after detection problems (sun
   glare and fog) and poor side-street service. Since then ACHD has said it
   will focus on "proven technology and signal performance measurement."
5. **Coordination breaks at jurisdictional seams.** As of 2020, ACHD's and
   ITD's central systems came from different vendors and were not
   integrated. Canyon County is split among Nampa, Caldwell, ITD and four
   highway districts.
6. **There's little public evidence of how well signals perform.** We found
   no published ACHD retiming cycle, signals-retimed-per-year figure, or
   before/after study, and no published results from ITD's 2023 Eagle Road
   timing review.

---

## 2.2 Who owns and operates the signals

| Area | Owner / operator | Notes |
|---|---|---|
| **Ada County local roads** (Boise, Meridian, Eagle, Kuna, Star, Garden City, unincorporated) | **ACHD** | Created by voter referendum on May 25, 1971 ⚠️ (source not yet re-checked). Idaho has 63 highway districts, and ACHD is the only countywide one.[^lso] Idaho Code §40-1406 makes a countywide highway district "responsible for all county secondary and city highways"; cities in it don't maintain their own streets. The City of Boise "does not directly operate any ITS infrastructure."[^tsmo] |
| **State highways in Ada County** (SH-55 Eagle Rd, SH-44 State St, US-20/26 Chinden, SH-16, SH-69, US-30, I-84 ramps) | **ITD** owns them; **ACHD** operates most or all signals | ITD said in 2006 that "ACHD has managed the state highway signal system within Ada County for ITD for many years under a service agreement."[^itd2006] A 2015 ACHD paper says ACHD operates "all traffic signals on state highways within the county."[^curns] The 2020 COMPASS plan says only "select ITD traffic signals."[^tsmo] Two ACHD–ITD agreements (ITS operations and fiber use) were last revised in 2011. The second, *Fiber Optic Network Infrastructure Use* (agreement agr1), includes connection to ACHD's real-time ATMS.[^agr] |
| **Nampa** | **City of Nampa** Traffic Division | Operates its signals plus "certain ITD traffic signals."[^tsmo] Awarded Econolite an ATMS + ATSPM platform in April 2024[^nampaecono] and built a $6.1M Integrated Command Center.[^nampaicc] |
| **Caldwell** | **City of Caldwell** | Runs Naztec controllers like ACHD's older fleet, and shares parts and training with ACHD.[^agr7] A Caldwell–Nampa signal interconnect agreement is still "Planned."[^agr8] |
| **Rural Canyon County** | Nampa HD No. 1, Notus-Parma HD No. 2, Golden Gate HD No. 3, Canyon HD No. 4 | Few signals; "rural traffic management."[^el82] ⚠️ Nampa Highway District bid a signal at Middleton Rd and Orchard Ave in 2021 (source not yet re-checked). |
| **Regional planning** | **COMPASS** (the metropolitan planning organization, MPO) | Owns the regional ITS architecture, the TSMO Strategic Plan, Congestion Management reports, and federal funding priorities. Doesn't operate signals. |

**Scale.** Counts vary by source and by what's counted:

| Count | Source |
|---|---|
| 427 signalized intersections | 2015 ACHD paper[^curns] |
| 465 signalized intersections | Feb 2022, per ACHD's Congestion Management Supervisor[^ipress2022] |
| About 544 signalized intersections region-wide | COMPASS 2020 plan[^tsmo] |
| About 600 "signalized intersections and pedestrian crossings" | Econolite's 2024 ACHD case study[^econolite] |

## 2.3 Operations center and technology timeline

| Year | Event | Source |
|---|---|---|
| Jan 2000 | ACHD opens its Traffic Management Center (TMC). ⚠️ The month (January) is from our research notes (source not yet re-checked). | [^tsmo] |
| 2009 | ACHD retimes 32+ intersections for Boise State games | ⚠️ (source not yet re-checked) |
| 2012 | ACHD plans a $600K first phase of 20–30 adaptive signals, using federal money left over from a cancelled bridge project. The Traffic Services Manager warned: "You can't turn the switch on and go to adaptive, find out that it doesn't work and go back." | [^govtech] |
| ~2014 | **Three Cities ITS project**: Rhythm Engineering adaptive system with 22 sensors on Glenwood, Eagle, Chinden and State | [^ktvbadaptive] |
| ~2015 | **ACHD scraps the adaptive system.** Sun glare and fog kept it from detecting queues accurately, and side streets weren't served properly. ACHD's spokesperson said it was flawed and "created issues for drivers rather than eliminating them." ⚠️ Article date not confirmed. | [^ktvbadaptive] |
| 2017 | $2.25M federal ATCMTD grant to replace controllers and detection at **82 intersections** | [^fhwa2017] |
| 2017–19 | ACHD participates in the national SPaT Challenge (signal-timing broadcasts to connected vehicles) at 20 intersections, evaluated by the University of Idaho | [^pactrans] |
| Mar 2018 | ITD and ACHD pilot dynamic "no right turn" signs at Eagle & Ustick | ⚠️ (source not yet re-checked) |
| 2020 | COMPASS TSMO Strategic Plan: ACHD's "forward focus" is "signal performance measurement and data collection." ACHD and ITD central systems "are from different vendors and are not integrated." | [^tsmo] |
| Nov 2021 | **SH-44/SH-55 in Eagle:** a Nov 2, 2021 City of Eagle staff memo says ITD changed the junction from a continuous-flow intersection to an expanded standard intersection after construction began. Eagle asked ACHD to model the delay nearby. | [^eaglememo] |
| 2022 | 465 signals, 220 cameras; emergency-vehicle preemption "up to 65,000 times a month" | [^ipress2022] |
| Fall 2023 | ITD contracts "national traffic engineering experts for review of signal timing and operations" on Eagle Road (18 signals, about 60,000 vehicles/day) | [^itdeagle] |
| Apr 2024 | Nampa awards Econolite ATMS + ATSPM | [^nampaecono] |
| Aug 2024 | **ACHD countywide Econolite contract:** Centracs Mobility central system, Cobalt ATC controllers with EOS software, detection, and cabinets for about 600 locations | [^econolite] |
| Apr 2025 | **Franklin Traffic Operations Center** completed: a $29.4M campus that brings together ACHD's congestion management center and its signal, sign and paint shops | [^cshqa] |
| Aug 2026 | ITD turns on variable speed limits on Eagle Rd (Fairview–Chinden): 45 mph in weekday peaks, 55 mph otherwise; a two-year pilot | [^itdvsl] |

**Operations and infrastructure.**

- **After hours.** The Ada County Sheriff's Office monitors ACHD's cameras
  after hours.[^agr4]
- **Backup center.** The backup control center on the unfunded list (§2.5) is
  requested because the current facility is "located in a
  floodplain."[^rdp]
- **Fiber.** More than 545 miles region-wide (2020). Shared downtown fiber
  (ACHD, Boise, Boise State) saved about $600K. ⚠️ (source not yet
  re-checked)

**ACHD cameras over time.**

| When | Cameras | Source / note |
|---|---|---|
| 2009 | 74 | ⚠️ (source not yet re-checked) |
| 2022 | 220 | [^ipress2022] |
| Oct 4, 2026 | 232 records in ACHD's GIS camera layer | 228 distinct cameras ([ch. 11](11-camera-validation-layer.md#111-the-source)) |
| Undated | About 160 arterial cameras | A COMPASS item ⚠️ (source not yet re-checked) |

## 2.4 How timing works here today

- **Time-of-day plans.** ACHD typically runs AM, midday and PM plans, and
  "free" (actuated) operation off-peak.[^achd206] ⚠️ No ACHD signal runs
  late-night flash.[^curns]
- **Downtown vs. suburbs.** Downtown Boise signals run "predetermined time
  intervals," i.e., pre-timed. Most signals elsewhere use detection.[^ipress2022]
- **Detection.** Much of it is video. In fog, video detection falls back to
  **recall mode**, which gives each direction its maximum green.[^kivifog]
  This explains a common foggy-morning complaint. Some Chinden intersections
  use radar.
- **Preemption.** Emergency vehicles preempt signals "up to 65,000 times a
  month" countywide, each affecting about a half-mile radius.[^ipress2022]
  As explained in [chapter 1](01-how-signal-systems-work.md#15-coordination-and-the-trade-offs-it-forces),
  coordination takes several cycles to recover after each preemption.
- **Pedestrians and safety.** ACHD has been adding leading pedestrian
  intervals (LPIs) after crashes, e.g., 11th & State in 2023.[^lpi] It was an
  early adopter of the flashing yellow arrow.[^curns]
- **Complaints get detection fixed.** ACHD said in 2022 that "by getting that
  input from the public, we've been able to get some intersections back to a
  more efficient operation by fixing the detection."[^ipress2022]
- **The same pattern in Nampa.** Its Transportation Engineer Manager said in
  2023: "we're reliant on reactive fixes. When a citizen sees a light doesn't
  turn for them right, they call us."[^nampaicc]
- **What Nampa expects from retiming.** Nampa's lead transportation engineer
  said on Nov 10, 2022 that corridor retiming generally gives "a 10 to 15
  percent decrease in travel times." ⚠️ (source not yet re-checked)

## 2.5 What's on the unfunded list

COMPASS's **FY2026 Resource Development Plan** lists member-agency needs that
COMPASS will help find outside funding for.[^rdp] The signal-related ACHD
items are:

| Item | Scope | Request |
|---|---|---|
| Signal timing updates: downtown Boise | 100 signals | $150,000 |
| Signal timing updates: Cole/Overland, Boise Towne Square, Franklin, Ustick, Fairview | multiple corridors | $200,000 |
| Signal timing updates: Federal Way, State, Parkcenter, Orchard, Curtis | multiple corridors | $200,000 |
| Signal timing updates: Broadway Ave | corridor | $100,000 |
| Signal timing updates: Vista Ave (Rose Hill–Wright) | corridor | $80,000 |
| Curtis Rd signal timing enhancement (new technology) | corridor | $200,000 |
| Signal Performance Measures (SPM) upgrades: Cole/Overland (15), State St east of Glenwood (15), Fairview (10), Franklin (10), Ustick (8) | 58 signals | $2,275,000 |
| Three Cities River Crossing ITS: SPM at 20 key intersections | 20 signals | $3,800,000 |
| Transit signal priority Phase 2 and Phase 3 (State St expansion, 20 signals each) | 40 signals | $400,000 |
| Arterial Management Regional Concept for Transportation Operations, incl. "coordination and operational strategies for joint ITD/local agency operated signal corridors" | region | $125,000 |
| Signal and ITS asset management system | county | $200,000 |
| Backup control center (current facility "located in a floodplain") | — | $100,000 |

**Why this matters:** retiming an entire 100-signal downtown costs about the
same as a few hundred feet of road widening. As the next chapters explain,
retiming and performance monitoring are among the highest benefit-per-dollar
tools there are, and here they sit on an unfunded wish list. They're the most
direct lever for anyone trying to improve signal timing.

> Caveat: the Resource Development Plan lists needs COMPASS wants to find
> *outside* (grant) money for. ACHD may fund some of this work from its own
> budget. Ask ACHD what is already planned in-house before assuming nothing
> is happening.

**Other plans and grants.**

- COMPASS's FY2023–29 Transportation Improvement Program (TIP) holds **19
  TSMO/ITS projects totaling $119.6M**.[^tip]
- **IROC**, a joint operations center, is still listed as "Planned." ⚠️
  (source not yet re-checked)
- **RAISE grant:** $8.5M to Valley Regional Transit (VRT) on Aug 11, 2022 for
  6.5 miles of transit improvements on State St/SH-44. Signal priority isn't
  mentioned. ⚠️ (source not yet re-checked)
- **I-84 ramp metering** appears only as an unfunded need. There are no ramp
  meters today. ⚠️ (source not yet re-checked)

## 2.6 Seams and coordination problems

- **ACHD ↔ ITD.** In 2020, separate central systems from different vendors,
  not integrated.[^tsmo] Whether the 2024 Econolite rollout covers ITD signals
  that ACHD operates is an open question.
- **Who decides timing on state highways?** ITD hired the Eagle Road timing
  review, while ACHD runs the signal system. It's unclear who signs off on
  timing changes on SH-55, SH-44 and US-20/26.
- **Canyon County.** Caldwell wants "stronger coordination with City of Nampa
  and ITD District 3."[^tsmo] A 2023 public comment on SH-55 Karcher said there
  "seems to be no coordination between Cities of Nampa and Caldwell and
  ITD."[^d3comments]
- **No physical regional TMC.** COMPASS is pursuing a "virtual regional TMC"
  that links ACHD, ITD, Nampa and Caldwell systems; it's unfunded.[^rdp]
- **Most congested segments (2022 Congestion Management report):** Chinden
  near SH-16 and near Eagle Rd, Nampa-Caldwell Blvd, SH-55 Karcher, Eagle Rd
  at I-84, and 11th Ave in Nampa.[^cms2022] Most are state highways or cross
  a jurisdiction line.

## 2.7 Lessons from the failed adaptive pilot

The 2014–15 episode explains ACHD's caution today. It also shows what any new
proposal, AI included, has to address:

1. **Detection is the foundation.** Video detection that fails in glare and
   fog will break any responsive system. Radar or thermal detection costs more
   but is more robust.
2. **Side streets and pedestrians are where adaptive systems fail
   publicly.** A system tuned for arterial flow that starves side streets
   generates complaints quickly.
3. **"All or nothing" deployments are risky.** Pilots need a clean rollback
   path and a pre-agreed evaluation method (see [chapter 4](04-improvement-playbook.md)).
4. **Proposals will be judged against that experience.** Any pitch to ACHD
   for adaptive or AI timing should be framed as measurable, reversible, and
   built on performance measures, which is the direction ACHD has said it
   wants to go.

## 2.8 Funding and governance

- **ACHD Commission:** five elected commissioners from five subdistricts,
  four-year terms.[^commission] They're the body that approves budgets and
  the Five-Year Work Plan.
- **Budget:** FY2026 about $257M, with a $125M capital program; FY2027 about
  $261M with about $133M capital.[^budget26][^budget27] ⚠️ Revenue includes
  property tax (about $55M), the state Highway Users Fund (about $51M), impact
  fees (about $23M) and vehicle registration fees (about $14M).[^revenue]
- **Five-Year Work Plan 2026–2030:** 266 projects, about $1.2B, mostly
  capital.[^fyp]
- **Staff:** about 300 total employees, per Wikipedia ⚠️.[^wiki]
  We found no published traffic-engineering or signal-operations headcount,
  which is a key question given the staffing benchmarks in
  [chapter 4](04-improvement-playbook.md).
- **Headquarters:** ACHD bought **5800 N. Meeker Ave.** for **$16.4M** as a
  new headquarters. ⚠️ (source not yet re-checked) Our research notes left
  open whether the TMC moved there; §2.3 puts the congestion management
  center in the Franklin Traffic Operations Center (Apr 2025), which may
  answer it.
- **State constraints:**
  - Idaho allows local-option sales taxes only in small resort cities, so
    Valley Regional Transit has no dedicated funding source.[^localoption]
  - SB 1180 (2025) effectively ended Boise's planned red-light camera pilot.[^redlight]

## 2.9 How to report a problem

| Agency | How |
|---|---|
| ACHD (all Ada County signals) | 208-387-6100 during business hours; after hours, Ada County non-emergency dispatch 208-377-6790; or the **ACHD Connect** app ⚠️[^report] |
| ITD District 3 | 208-334-8300[^itdd3] |
| City of Nampa | Online form or 208-468-5511[^nampatraffic] |

Specific, timestamped reports work best: intersection, approach, direction,
time of day, and what happened (e.g., "eastbound left on Fairview at Locust
Grove gets no green for 3+ cycles at 7:15 am"). That kind of detail is how
broken detectors get found.

## 2.10 Open questions to resolve, by asking or through a records request

1. The current ACHD signal count, and the current ACHD–ITD signal operations
   agreement (scope, who approves timing on state routes).
2. Signal-operations staffing: how many traffic engineers and signal
   technicians per signal?
3. Retiming cycle: when was each major corridor last retimed?
4. Whether ATSPM-style performance measures are live in the new Centracs
   system, and on how many signals.
5. Detection inventory and failure rate: how many detectors are down at any
   given time?
6. Results of ITD's 2023 Eagle Road signal timing review.
7. Whether the TMC is now staffed around the clock. The architect describes
   "around-the-clock monitoring"[^cshqa]; the 2019 ITS architecture listed
   weekday hours of 5:30 am–6:30 pm.[^el22]
8. Whether ACHD has looked at Google's Project Green Light (see
   [chapter 5](05-ai-and-emerging-tech.md)).

---

**Next:** [03 — Regional traffic context and data](03-traffic-context-and-data.md)

[^tsmo]: COMPASS, *Treasure Valley TSMO Strategic Plan* (IBI Group, Jan 16, 2020), pp. 14–18. https://compassidaho.org/wp-content/uploads/COMPASSTSMOPlan_FINAL.pdf
[^lso]: Idaho Legislative Services Office briefing, Jan 16, 2018.
[^itd2006]: ITD Transporter, Aug 25, 2006. https://apps.itd.idaho.gov/apps/MediaManagerMVC/Transporter/2006/082506_Trans/082506_Board.html
[^curns]: ACHD paper, ITE Western District annual meeting, 2015. https://www.westernite.org/annualmeetings/15_Las_Vegas/Papers/2C-Curns.pdf
[^agr]: COMPASS Regional ITS Architecture, agreements. https://its-architecture.compassidaho.org/html/agree/agr2.html and https://its-architecture.compassidaho.org/html/agree/agr1.html
[^agr4]: COMPASS Regional ITS Architecture, agreement agr4. https://its-architecture.compassidaho.org/html/agree/agr4.html
[^agr7]: https://its-architecture.compassidaho.org/html/agree/agr7.html
[^agr8]: https://its-architecture.compassidaho.org/html/agree/agr8.html
[^el82]: https://its-architecture.compassidaho.org/html/inv/el82.html
[^el22]: https://its-architecture.compassidaho.org/html/inv/el22.html
[^nampaecono]: Econolite, Nampa ATMS/ATSPM award (Apr 2024). https://econolite.com/?p=11681
[^nampaicc]: KIVI, "Nampa's Integrated Command Center." https://www.kivitv.com/nampa/nampas-integrated-command-center-a-proactive-approach-to-incident-response
[^ipress2022]: Idaho Press, "ACHD using adjusted traffic light intervals to manage growing traffic," Feb 2022. https://www.idahopress.com/news/local/ada-county-highway-district-using-adjusted-traffic-light-intervals-to-manage-growing-traffic/article_b2da4cbb-1b08-5b46-9e72-db70b249249b.html
[^econolite]: Econolite case study, Aug 21, 2024. https://www.econolite.com/in-action/case-study/achd-traffic-signal-software-atc-controllers/
[^govtech]: Government Technology, "Smart Traffic Signals Get a Green Light," Feb 15, 2012. https://www.govtech.com/transportation/Smart-Traffic-Signals-Get-a-Green-Light.html
[^ktvbadaptive]: KTVB, "ACHD scraps adaptive traffic light program." https://www.ktvb.com/article/news/local/achd-scraps-adaptive-traffic-light-program/277-22736840
[^fhwa2017]: FHWA press release, Oct 4, 2017. https://www.fhwa.dot.gov/pressroom/fhwa1717d.cfm
[^pactrans]: PacTrans, "Field Evaluation of V2I Connected Vehicle Deployment in Ada County." https://depts.washington.edu/pactrans/research/projects/field-evaluation-of-v2i-connected-vehicle-deployment-in-ada-county-idaho-validating-communication-architecture-and-control-technology-readiness
[^itdeagle]: ITD, Eagle Road safety corridor page. https://itd.idaho.gov/?p=57877
[^eaglememo]: City of Eagle staff memo, Nov 2, 2021 (SH-44/SH-55 junction).
[^cshqa]: CSHQA project page, ACHD Franklin Traffic Operations Center. https://www.cshqa.com/project/achd-franklin-traffic-operations-center/
[^itdvsl]: ITD news release, Aug 5, 2026. https://itd.idaho.gov/news/itd-activates-variable-speed-limit-signs-on-eagle-road/
[^achd206]: ACHD public info item (search excerpt only). https://www.achdidaho.org/community-resources/public-info-and-alerts/-item-206
[^kivifog]: KIVI, "Dense fog affecting traffic lights throughout Ada County." https://www.kivitv.com/news/dense-fog-affecting-traffic-lights-throughout-ada-county
[^lpi]: Idaho Press, 2023. https://www.idahopress.com/news/local/ada-county-highway-district-makes-changes-to-downtown-boise-intersection-in-hopes-of-improving-safety/article_21165e1e-2bef-11ee-957c-efe1d2b47f6a.html
[^rdp]: COMPASS, *Resource Development Plan FY2026*, pp. 2–5. https://compassidaho.org/wp-content/uploads/2026ResourceDevelopmentPlan.pdf
[^tip]: COMPASS, FY2023–2029 Transportation Improvement Program (TIP).
[^d3comments]: COMPASS, ITD D3 ITIP public comments 2023. https://compassidaho.org/wp-content/uploads/D3ITIP_Comments2023_Revised.pdf
[^cms2022]: COMPASS, *2022 Congestion Management System Report*. https://compassidaho.org/wp-content/uploads/2022CongestionManagementSystemReport.pdf
[^commission]: Idaho Code §40-1404A. https://legislature.idaho.gov/statutesrules/idstat/Title40/T40CH14/SECT40-1404A/
[^budget26]: ACHD, FY2026 budget. https://engage.achdidaho.org/budget-fiscal-year-2026
[^budget27]: ACHD, FY2027 budget hearing. https://engage.achdidaho.org/budget-fiscal-year-2027/news_feed/2027-budget-public-hearing
[^revenue]: ACHD budget document (search excerpt). https://www.achdidaho.org/home/showpublisheddocument/1766/638961385597700000
[^fyp]: ACHD, 2026–2030 Five Year Plan adoption. https://engage.achdidaho.org/five-year-plan-2026-2030/news_feed/achd-commissioners-adopt-2026-2030-five-year-plan
[^wiki]: Wikipedia, "Ada County Highway District" (total employees). ⚠️ Secondary source.
[^localoption]: Idaho Code §50-1044. https://legislature.idaho.gov/statutesrules/idstat/Title50/T50CH10/SECT50-1044/
[^redlight]: KIVI, "New Idaho law forces Boise to abandon red light camera program." https://www.kivitv.com/downtown-boise/new-idaho-law-forces-boise-to-abandon-red-light-camera-program
[^report]: ACHD, Report an Issue. https://www.achdidaho.org/community-resources/report-an-issue
[^itdd3]: ITD District 3. https://itd.idaho.gov/district-3-southwest-idaho/
[^nampatraffic]: City of Nampa Traffic Division. https://www.cityofnampa.us/1720/Traffic-Division
