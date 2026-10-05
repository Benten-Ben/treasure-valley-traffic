# 4. How a team would go about improving signal timing

This chapter covers the standard process, the evidence on what works, the
resource arithmetic for Ada County, the data tools available, and a phased
plan for a small team. The plan works whether the team is inside an agency,
a consultant, a university group, or a civic group or startup on the
outside.

---

## 4.1 Treat timing as maintenance, not a project

Signal timing decays. Traffic grows, land use changes, and detectors fail.
Without monitoring and periodic retiming, a well-timed corridor degrades
within a few years. Most US agencies find problems the same way:

- **More than 95%** of agencies find operational problems through public
  complaints and field observation; only **41%** use automated
  monitoring.[^bench2019]
- FHWA's 2016 fact sheet says "citizen complaints [are] the primary measure
  of performance" for most agencies.[^edcfact]
- The 2012 National Traffic Signal Report Card graded the US a **D+**
  overall and an **F** on "Monitoring & Data Collection."[^reportcard]
  [^reportcardgrades] The 2019 Benchmarking report gave a **C+**, using a
  different method.[^bench2019]

The Treasure Valley follows the same pattern. ACHD has said public reports
are how it finds broken detection, and Nampa's engineer described the city
as "reliant on reactive fixes" (see [chapter 2](02-treasure-valley-signal-system.md#24-how-timing-works-here-today)).
The highest-value change is moving from reacting to complaints to measuring
continuously.

## 4.2 The standard process

The **Signal Timing Manual, 2nd Edition** (NCHRP Report 812, 2015) is the
reference document. It lays out an eight-step, outcome-based process:[^stm2]

1. **Define the operating environment.** Corridor context, land use,
   adjacent jurisdictions.
2. **Identify users.** Drivers, freight, transit, pedestrians, cyclists.
3. **Set priorities** by user and movement, location and time of day.
4. **Select operational objectives.** For example: progression on the
   arterial at peak, minimum pedestrian delay downtown, no split failures on
   left turns.
5. **Establish performance measures** tied to those objectives.
6. **Develop timing strategies and values.** Model in Synchro/Vistro and
   simulate where needed.
7. **Implement and observe.** Load the plans, fine-tune in the field, and
   run before/after studies.
8. **Monitor and maintain.** Ongoing performance tracking, detection repair,
   periodic retiming.

STM2 warns against "hit the optimize button" timing, where results "largely
reflect the model's priorities (generally some version of vehicle delay)"
instead of local goals.[^stm2] It also names "communication and detection
issues" as "often significant contributors to poor operations."

At the program level, FHWA's **Traffic Signal Management Plan (TSMP)**
framework (FHWA-HOP-15-038) ties goals and performance measures to design,
operations, maintenance and staffing. Its central idea is "good basic
service": "doing the most important things given a finite set of
resources."[^tsmp] Ask ACHD whether it has a TSMP.

## 4.3 Evidence: retiming pays, a lot

| Program / source | Scope | Result |
|---|---|---|
| FHWA Traffic Signal Timing Manual (2008) | Literature synthesis | Benefits "outweigh the costs 40:1 (or more)"; delay −15–40%, stops −10–40%, travel time up to −25%, fuel up to −10%[^stm2008] |
| Texas TLS Program I (TTI, 1992) | 2,243 signals, 44 cities, $7.9M | Delay −24.6%, stops −14.2%, fuel −9.1%; about $62 of benefit per $1[^texas] |
| California FETSIM (1983–93) | 12,245 signals, 334 projects | Delay −14%, stops −13%, travel time −7%, fuel −8%; fuel savings alone more than 5× program cost[^fetsim] |
| Dallas–Fort Worth regional retiming, Phase V | 201 signals | Signal delay about −8%; about $32M/yr user benefit[^nctcog] |
| UDOT ATSPM, 10-year | 2,111 signals | $11.6M cost vs. $108.0M benefit; **$57.9M of the benefit came from faster detector repair**[^atspmbc][^udotdetect] |
| Indiana (Purdue/INDOT) connected-vehicle-targeted retiming | 11 changes at 9 signals | Delay cut by up to 53 s/veh; split failures down up to 30%[^indot] |
| Boston + Google Green Light (INRIX evaluation) | 114 intersections | Delay −13.5% average (up to 24%); unnecessary stops −20%[^boston] |

**How often to retime:** FHWA says "every three to five years and more often
if" demand changes. It suggests retiming after a 5–10% demand increase, or
less if near capacity.[^stm2008ch7] Few agencies keep up: only 12% scored top
marks on retiming frequency in the NTOC survey, and most go longer than 30–36
months because of limited resources.[^staffing][^nchrp409]

In a region where population and traffic grow several percent a year, the
5–10% demand-change trigger is hit about every **1–3 years** on growing
corridors. A 3–5 year cycle is already slow for the Treasure Valley.

## 4.4 The resource arithmetic for Ada County

This applies published benchmarks to ACHD's scale. The inputs are cited;
the arithmetic is ours and is meant to give a sense of scale, not to grade
ACHD.

| Benchmark | Source | Applied to ~500 ACHD signalized intersections |
|---|---|---|
| 1 traffic engineer per 75–100 signals | ITE, FHWA[^staffing] | **5–7 signal timing/operations engineers** |
| 1 technician per 40–50 signals (30–40 per the 2005 Report Card) | FHWA[^staffing] | **10–17 signal technicians** |
| Retime every 3–5 years | FHWA[^stm2008ch7] | **100–170 signals per year** |
| $2,500–$4,500 per intersection per retime | FHWA[^staffing][^edcfact] | **≈ $250K–$750K per year** |
| 20–30 labor hours per intersection | STM2, NCHRP 409[^stm2][^nchrp409] | **≈ 2,000–5,000 staff hours per year** |

"~500" is our working number, between ACHD's 465 signalized intersections
(2022) and Econolite's "about 600 signalized intersections and pedestrian
crossings" (2024).

Compare that with ACHD's **≈$257M FY2026 budget**. A full countywide
retiming program is on the order of **0.1–0.3%** of annual spending. Surveyed
agencies average **185 signals per engineer**,[^staffing] roughly twice the
benchmark. So the most likely constraint is staff time, which matches the
regional unfunded list (see [chapter 2](02-treasure-valley-signal-system.md#25-whats-on-the-unfunded-list))
and the national pattern. FHWA also notes that agencies often assume new
technology will reduce maintenance needs, and so under-budget staff after
upgrades.[^staffing] That's a risk to watch after ACHD's 2024–25 Econolite
rollout.

**Key questions for ACHD:** How many FTEs work on signal timing and on signal
maintenance? When was each corridor last retimed?

## 4.5 Why a specific light seems bad: a diagnostic checklist

| Symptom | Likely cause | How to confirm |
|---|---|---|
| Green for an empty approach every cycle | Failed detector on max recall; fog/glare video fallback | ATSPM phase-termination chart shows constant max-outs; overnight max-outs >90% is a classic detector-fault flag[^watchdog] |
| Long wait on a side street or left turn at off-peak hours | Coordinated plan running when traffic is light, or a long cycle | Check time-of-day schedule; probe data by hour |
| Platoons always arrive on red | Bad offsets / stale plan / clock drift / recovering from preemption | Purdue Coordination Diagram; floating-car runs |
| Queue doesn't clear in one green (repeatedly) | Under-allocated split, or demand above capacity | Split failure measure; v/c analysis |
| Progression breaks at a specific point | Jurisdiction seam (ACHD↔ITD, Nampa↔Caldwell) or different cycle lengths | Compare cycle lengths on each side; time-space diagram |
| Everything is bad at 5:15 pm and fine at 7 pm | Demand over capacity; timing can only move delay around | Volume vs capacity; this needs network or capacity solutions |

Long cycles also have a hidden cost: they can *increase* congestion through
turn-bay spillback and less efficient long greens (STM2 §7.4.2).[^stm2]

## 4.6 Automated Traffic Signal Performance Measures (ATSPM)

ATSPM is the most important modern practice to understand.

- **What it is.** Modern controllers log every phase change and detector
  actuation at 0.1-second resolution (the "Indiana hi-res enumerations"
  developed by Purdue and INDOT).[^enum] Software turns those logs into
  charts and alerts, so engineers can see how every signal performs every
  cycle without anyone driving out.
- **Origin.** Developed by Purdue/INDOT and Utah DOT, which began building
  its system in 2012. FHWA promoted it nationally in Every Day Counts round 4.
  By 2018, 31 states were at demonstration or later stages.[^edc4]
- **Adoption today.** In 2026, 83% of responding state DOTs used ATSPM
  (controller-based or probe-based), but only 18% at full scale. The top
  barriers are staff and outdated controllers or detection.[^nchrp659]
- **Key charts:**
  - Purdue Coordination Diagram (progression quality)
  - Arrivals on green/red
  - Split failures
  - Approach delay and volume
  - Pedestrian delay
  - Phase termination (max-out / gap-out / force-off)
  - Split monitor
  - Preemption details
  - Yellow/red actuations
  - Left-turn gap analysis[^udotatspm]
- **Software.** The **open-source ATSPM v5** is at
  [github.com/OpenSourceTransportation/atspm](https://github.com/OpenSourceTransportation/atspm).
  It's Apache-2.0 licensed and Docker-deployable; the latest release is
  v5.3.1 (Aug 2026). Vendors also sell versions; Nampa bought Econolite's in
  2024.[^nampaecono]
- **Requirements:**
  - Controllers with hi-res logging (Econolite, Siemens, McCain, Intelight,
    Trafficware and others).
  - Communications to pull logs, about 19 MB per signal per day.
  - The right detection for each metric. Advance detectors 350–400 ft back
    are needed for progression measures, and stop-bar lane-by-lane detection
    for split failures. Split monitor and phase termination need no extra
    detection.[^udotatspm]
- **Results.** Utah: **$108M** of benefit for **$11.6M** over 10 years, more
  than half of it from catching broken detectors faster.[^atspmbc]
- **Public transparency precedent.** UDOT and Georgia DOT run public,
  read-only ATSPM websites.[^gdot] A public ATSPM portal for Ada County would
  be a concrete, precedented ask.

**Local status:** ACHD's new Econolite Cobalt controllers should support
hi-res logging. COMPASS's regional ITS architecture listed ACHD/ITD ATSPM as
"Planned" in 2019. The FY2026 unfunded list still contains about $6M of
"Signal Performance Measures" upgrades on Cole/Overland, State, Fairview,
Franklin, Ustick and the Three Cities river crossings. That suggests coverage
is partial, possibly because of detection or communications gaps. This is the
single most useful thing to clarify with ACHD.

## 4.7 Probe data: measurement without controller access

Connected-vehicle and probe data has changed what outsiders can measure. You
can now estimate signal performance from vehicle trajectories without
touching agency equipment.

| Source | What it gives | Notes |
|---|---|---|
| **Purdue/INDOT connected-vehicle methods** | Arrivals on green, split failures, LOS, and downstream blockage for thousands of signals | 4,700+ signals from 910M+ trajectories across all 50 states (2023); published methods[^purdueCV] |
| **INRIX Signal Analytics** | Control delay, split failures, turn ratios, volumes at about 210,000 US intersections | Commercial[^inrix] |
| **Iteris ClearGuide Signal Trends** | Connected-vehicle trajectory metrics updated every 10–15 min | Commercial, launched 2024[^clearguide] |
| **StreetLight** | Turning-movement counts, O-D patterns | Commercial[^streetlight] |
| **Google Project Green Light** | Infers cycle, splits and offsets from Maps data and recommends changes | Free to partner cities; agencies only (see [chapter 5](05-ai-and-emerging-tech.md)) |
| **DIY floating-car runs** | GPS-logged drives through a corridor (stops, delay, travel time) | Cheap and credible for before/after if done systematically (STM2 Ch. 8) |

Vendor risk is real. Wejo, a connected-vehicle data source Purdue used,
collapsed in 2023.[^wejo]

## 4.8 Adaptive signal control: when it helps

- **FHWA (EDC-1):** adaptive improves travel time by more than 10% on
  average, and by 50% or more where timing was badly outdated.[^asct]
- **NCHRP 20-07/414 (2019) review of deployments:**[^nchrp414]
  - Cost: about **$55K per intersection** to install, about $10K for
    licensing, and about **$4K per intersection per year** to maintain.
  - Only 36% of deployments followed the required systems-engineering
    process.
  - Benefits ranged widely; side-street delay *rose* 3.4% on average.
    Benefits were larger on 35K–55K AADT corridors than above 55K.
  - 78% were fully operational, 10% partially decommissioned, and 2% fully
    decommissioned. The main reasons were detection and communications
    problems, unmet expectations, and maintenance.
- **Removals.** An FDOT memo describes agencies removing OPAC and SCOOT
  where well-tuned conventional timing did as well or better on predictable
  traffic.[^fdot]
- **The Ada County experience** (InSync, about 2014–15) fits the typical
  failure pattern: detection problems plus side-street complaints.

**Takeaway:** adaptive pays off on corridors with **variable, unpredictable
demand** (event traffic, incident diversions, seasonal swings), with **robust
detection** and **staff to maintain it**. For predictable commuter peaks,
well-maintained time-of-day plans plus ATSPM monitoring capture most of the
benefit at a fraction of the cost. Federally funded adaptive projects require
a systems-engineering analysis (23 CFR 940.11), and FHWA publishes templates
for it.[^se]

## 4.9 Tools of the trade

| Tool | Used for |
|---|---|
| **Synchro / SimTraffic** (Cubic/Trafficware) | The US standard for timing optimization (cycle/split/offset) plus basic simulation |
| **PTV Vistro / Vissim** | Optimization and detailed microsimulation, including transit, pedestrians and oversaturation |
| **Aimsun** | Microsimulation and mesoscopic network modeling |
| **SUMO** (open source, DLR) | Free microsimulation; scriptable via its TraCI interface; used by Google's digital-twin research and most AI research |
| **Tru-Traffic** | Time-space diagrams and coordination, often with GPS travel-run data |
| **ATSPM v5** (open source) | Performance monitoring from controller logs |
| **HCM methods** | Standard delay/LOS calculations |

STM2 warns that "a sophisticated tool in the hands of an inexperienced
analyst may not produce a satisfactory result."[^stm2] Engineering judgment
and field verification matter more than the software.

## 4.10 Working with the agency from outside

**Possible team roles:** a licensed traffic engineer (PE) for credibility and
judgment; a data analyst or engineer for probe data, ATSPM, and SUMO; someone
to handle agency relations and policy (commission meetings, COMPASS
committees); and volunteers for field data collection.

**Approaches that work:**

1. **Public records requests (Idaho Public Records Act).** Agencies must
   respond within 3 working days, extendable to 10, and silence counts as a
   denial.[^pra] Expect critical-infrastructure and cybersecurity details to
   be withheld (§74-105). Ask for:
   - timing sheets and the last-retimed date for each signal;
   - detector trouble tickets from the last 24 months;
   - a list of signals with communications and hi-res logging;
   - signal operations staffing and budget;
   - ACHD–ITD signal agreements;
   - ITD's 2023 Eagle Road timing review.
2. **Meet staff before going to the board.** Brief ACHD traffic operations
   staff privately with data first. Elected commissioners respond to
   evidence, but surprising staff in public tends to backfire.
3. **Use COMPASS.** It runs the TSMO program and a Regional Operations
   Working Group, and it prioritizes CMAQ/STBG funding. The unfunded items in
   [chapter 2](02-treasure-valley-signal-system.md#25-whats-on-the-unfunded-list)
   are already in its pipeline, so supporting them is easier than proposing
   something new.
4. **Partner with a university.** The Purdue–INDOT partnership is the model.
   Locally, Boise State and the University of Idaho are natural partners.
   University of Idaho researchers evaluated ACHD's 2017–19
   connected-vehicle pilot, and the university runs the NIATT transportation
   institute.[^niatt]
5. **Pilot agreements.** Pittsburgh's Surtrac went from a 9-intersection
   CMU pilot to city ownership.[^surtrac] Google Green Light uses a no-cost,
   60-day-exit agreement model (Vancouver, 2026).

**Pitfalls:**

- **Cybersecurity.** Signal controllers have known weaknesses. The
  University of Michigan's "Green Lights Forever" study found unencrypted
  radios, default passwords, and an open debug port.[^greenlights] Ask only
  for read-only data exports, never network or NTCIP access. Agencies will
  rightly refuse anything else.
- **Liability and risk aversion.** Agencies carry tort exposure for signal
  operations. Proposals should come with rollback plans.
- **Vendor fatigue.** After the adaptive experience, ACHD will be skeptical
  of "black box" pitches.[^fdot] Lead with transparency and measurement.

## 4.11 Funding sources

| Program | Fits | Notes |
|---|---|---|
| **CMAQ** | "Projects to improve signalization," ITS | Ada County is a CMAQ priority area in ITD policy; programmed via COMPASS[^cmaq][^itdcmaq] |
| **STBG** | Capital *and operating* costs for traffic monitoring and control | Programmed via COMPASS[^stbg] |
| **HSIP** | Intersection safety improvements, including signal changes | Safety framing (e.g., LPIs, yellow/red timing)[^hsip] |
| **SMART grants** | Tech demonstrations; Stage 1 up to $2M | Federal program, FY22–26[^smart] |
| **ATTAIN** (formerly ATCMTD) | Advanced traffic tech deployment, up to $12M | ACHD won $2.25M in 2017 under ATCMTD[^attain] |

**Federal uncertainty:** the IIJA surface-transportation authorizations
expired Sept 30, 2026, and an extension or reauthorization was being debated
in Congress at the time of writing.[^iija] Check current status before
counting on SMART or ATTAIN.

## 4.12 A phased starter plan

This is a synthesis built from the steps above. The corridors were chosen
from the evidence in chapters [2](02-treasure-valley-signal-system.md) and
[3](03-traffic-context-and-data.md).

### Phase 0: pick corridors (week 1)

Choose 3–5 corridors that cover different problem types:

- **Fairview Ave** or **Franklin Rd.** An ACHD arterial on the unfunded
  performance-measures list; tests "plain ACHD timing."
- **State St / SH-44.** An ITD route operated by ACHD, with transit signal
  priority and on both the performance-measures and retiming lists; tests the
  ACHD↔ITD seam and transit.
- **Eagle Rd / SH-55.** 18 signals and 60,000 vehicles/day; ITD reviewed its
  timing in 2023 and is now piloting variable speed limits.
- **Chinden / US-20/26** near SH-16. Among the most congested segments in
  COMPASS's 2022 report.
- **Nampa-Caldwell Blvd** or **SH-55 Karcher.** Tests the Canyon County
  multi-agency seam.

### Phase 1: baseline (days 1–30)

- File records requests (list in §4.10).
- Collect travel-time data for the corridors: your own GPS runs plus free
  public sources (chapters [3](03-traffic-context-and-data.md) and
  [7](07-diy-data-collection.md)). Commercial probe data needs a license or
  an agency partner.
- Run GPS floating-car runs: at least 6–10 per direction per time period.
- Note every observed problem with a timestamp and report it to ACHD. Track
  response times.

### Phase 2: diagnose (days 31–60)

- Build a corridor scorecard: travel time and reliability, stops, estimated
  arrivals on green and split failures, and each signal's last-retimed date.
- Sort problems into **timing-fixable** (stale plans, detection, offsets,
  seams) and **capacity-bound** (demand over capacity at peak).
- Write a 2-page gap memo against the FHWA TSMP framework and the staffing
  benchmarks.

### Phase 3: propose (days 61–90)

- Brief ACHD (and ITD District 3 for state routes) privately. Offer the data
  and analysis free.
- Make a concrete, precedented ask. Options:
  - **Fund the existing unfunded retiming and performance-measures items.**
    About $730K of retiming and about $6M of SPM are already on COMPASS's
    list.
  - **A public, read-only ATSPM dashboard** like Utah's or Georgia's.
  - **A measured Green Light or probe-based retiming pilot** on 10–20
    signals, with untreated comparison corridors and a pre-registered
    evaluation plan.
  - **A regular retiming cycle**, with published "last retimed" dates.
- Present to the ACHD Commission and the COMPASS board with before/after
  framing.

### Beyond 90 days

- Pursue a university partnership for ongoing evaluation.
- Push for a regional ACHD–ITD–Nampa–Caldwell timing coordination study,
  already listed as a $125K unfunded item.
- Track results publicly. Visible measurement is what keeps a retiming
  program funded.

---

**Next:** [05 — AI and emerging technology](05-ai-and-emerging-tech.md)

[^bench2019]: NTOC, *2019 Traffic Signal Benchmarking and State of the Practice Report*. https://transportationops.org/trafficsignals/benchmarkingreport
[^edcfact]: FHWA EDC-4 ATSPM fact sheet (2016). https://www.fhwa.dot.gov/innovation/pdfs/factsheets/edc/automated_traffic_signal.pdf
[^reportcard]: NTOC, *2012 National Traffic Signal Report Card*. https://transportationops.org/publications/2012-national-traffic-signal-report-card
[^reportcardgrades]: Category grades as reported by Roads & Bridges. https://www.roadsbridges.com/2012-national-traffic-signal-report-card-reveals-minor-progress
[^stm2]: *Signal Timing Manual, 2nd Edition* (NCHRP Report 812, 2015). https://nap.nationalacademies.org/catalog/22097 · PDF: https://transops.s3.amazonaws.com/uploaded_files/Signal%20Timing%20Manual%20812.pdf
[^tsmp]: FHWA, *Traffic Signal Management Plans* (FHWA-HOP-15-038). https://ops.fhwa.dot.gov/publications/fhwahop15038/ch1.htm
[^stm2008]: FHWA, *Traffic Signal Timing Manual* (FHWA-HOP-08-024), Ch. 1. https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter1.htm
[^stm2008ch7]: Ibid., Ch. 7. https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter7.htm
[^texas]: TTI, Texas TLS Program evaluation (1992). https://static.tti.tamu.edu/tti.tamu.edu/documents/TTI-1992-ID14823.pdf
[^fetsim]: UC Berkeley ITS, FETSIM evaluation. https://its.berkeley.edu/publications/evaluation-fuel-efficient-traffic-signal-management-fetsim-program-1983-1993
[^nctcog]: NCTCOG Regional Traffic Signal Retiming Program Phase V. https://nctcog.org/getmedia/bc85573a-3652-430b-82f9-c4dbd6feb7f0/RTSRP_Ph5_ExecSummary_HDR.pdf
[^atspmbc]: FHWA, *Evaluating the Benefits and Costs of Implementing ATSPM* (FHWA-HOP-20-003). https://ops.fhwa.dot.gov/publications/fhwahop20003/exec.htm
[^udotdetect]: Ibid., Appendix A. https://ops.fhwa.dot.gov/publications/fhwahop20003/appa.htm
[^indot]: Purdue JTRP-2024/33. https://docs.lib.purdue.edu/jtrp/1872
[^boston]: City of Boston, June 17, 2025. https://www.boston.gov/news/mayor-wu-announces-expansion-project-green-light-signal-optimization-program
[^staffing]: FHWA, *Traffic Signal O&M Staffing Guidelines* (FHWA-HOP-09-006). https://ops.fhwa.dot.gov/publications/fhwahop09006/chap_2.htm and Appendix C https://ops.fhwa.dot.gov/publications/fhwahop09006/app_c.htm
[^nchrp409]: NCHRP Synthesis 409. https://nap.nationalacademies.org/catalog/22915
[^watchdog]: FHWA-HOP-20-002, Ch. 4. https://ops.fhwa.dot.gov/publications/fhwahop20002/ch4.htm
[^enum]: Sturdevant, Bullock et al., *Indiana Traffic Signal Hi Resolution Data Logger Enumerations* (2012; updated 2020). https://docs.lib.purdue.edu/jtrpdata/3 · https://docs.lib.purdue.edu/jtrpdata/4
[^edc4]: FHWA-HOP-20-002, Ch. 3. https://ops.fhwa.dot.gov/publications/fhwahop20002/ch3.htm
[^nchrp659]: NCHRP Synthesis 659 (2026). https://www.nationalacademies.org/read/29326/chapter/2
[^udotatspm]: UDOT ATSPM portal and FAQ. https://udottraffic.utah.gov/ATSPM · https://udottraffic.utah.gov/atspm/FAQs/Display
[^nampaecono]: Econolite, Nampa award (Apr 2024). https://econolite.com/?p=11681
[^gdot]: Georgia DOT ATSPM FAQ. https://traffic.dot.ga.gov/ATSPM/FAQs/Display
[^purdueCV]: Purdue JTRP affiliated documents. https://docs.lib.purdue.edu/jtrpaffdocs/46 · https://docs.lib.purdue.edu/jtrpaffdocs/44
[^inrix]: INRIX Signal Analytics press release (Jan 2021). https://inrix.com/press-releases/inrix-iq-signal-analytics/
[^clearguide]: Iteris ClearGuide Signal Trends (Mar 2024). https://www.iteris.com/news/iteris-launches-new-clearguide-signal-trends-probe-based-option-improving-intersection
[^streetlight]: StreetLight intersection studies. https://www.streetlightdata.com/intersection-studies/
[^wejo]: https://en.wikipedia.org/wiki/Wejo
[^asct]: FHWA EDC-1, Adaptive Signal Control Technology. https://www.fhwa.dot.gov/innovation/everydaycounts/edc-1/asct.cfm
[^nchrp414]: NCHRP 20-07/Task 414 final report (2019). https://onlinepubs.trb.org/Onlinepubs/nchrp/docs/NCHRP20-07_Task414FinalReport.pdf
[^fdot]: FDOT ASCT memo (2016). https://www.fdot.gov/docs/default-source/traffic/its/arterialmanagement/FDOT_ASCT.pdf
[^se]: FHWA-HOP-11-027, *Model Systems Engineering Documents for ASCT*. https://ops.fhwa.dot.gov/publications/fhwahop11027/es.htm · 23 CFR 940.11 https://www.law.cornell.edu/cfr/text/23/940.11
[^pra]: Idaho Code §74-103. https://legislature.idaho.gov/statutesrules/idstat/Title74/T74CH1/SECT74-103/ · §74-105 https://legislature.idaho.gov/statutesrules/idstat/Title74/T74CH1/SECT74-105/
[^niatt]: University of Idaho NIATT. https://www.uidaho.edu/engr/research/niatt
[^surtrac]: CMU Surtrac final report. https://ppms.cit.cmu.edu/media/project_files/193_-_Final_Report.pdf
[^greenlights]: Ghena et al., "Green Lights Forever," USENIX WOOT 2014. https://www.usenix.org/conference/woot14/workshop-program/presentation/ghena
[^cmaq]: 23 U.S.C. §149. https://www.law.cornell.edu/uscode/text/23/149
[^itdcmaq]: ITD policy A-11-05. https://itd.idaho.gov/wp-content/uploads/2025/08/A1105.pdf
[^stbg]: 23 U.S.C. §133. https://www.law.cornell.edu/uscode/text/23/133
[^hsip]: 23 U.S.C. §148. https://www.law.cornell.edu/uscode/text/23/148
[^smart]: USDOT SMART grants. https://www.transportation.gov/rural/grant-toolkit/strengthening-mobility-and-revolutionizing-transportation-smart-grants
[^attain]: FHWA ATTAIN fact sheet. https://highways.dot.gov/iija/fact-sheets/advanced-transportation-technologies-and-innovation
[^iija]: NACo, "IIJA authorities expire September 30." https://www.naco.org/news/iija-authorities-expire-september-30-naco-urges-congress-uphold-full-funding-levels-highway
