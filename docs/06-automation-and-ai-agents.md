# 6. Can automation and AI agents close the staffing gap?

[Chapter 4](04-improvement-playbook.md#44-the-resource-arithmetic-for-ada-county)
found that keeping ACHD's roughly 500 signals retimed on a 3–5 year cycle
takes more engineer and technician time than most agencies have. This
chapter asks whether automation, from plain data tools to AI agents, can
close that gap.

---

## 6.1 Short answer

**For retiming and monitoring, largely yes. For field maintenance, only
partly. For AI agents specifically, it's plausible but unproven.**

- **Most of the labor in a traditional retiming is data collection, and
  that's already automatable.** Agencies with automated performance
  measures (ATSPM) and probe data have stopped doing manual counts and
  test-drive studies. Utah and Georgia did this years ago.
- **The proven gains come from "boring" automation:** controller logs, probe
  data, automated alerts, remote timing uploads. They don't come from AI
  controllers. ACHD's new Econolite hardware can support most of this.
- **Automation shifts the bottleneck rather than removing it.** Dashboards
  and alerts create a new job: someone has to look at them and act. Nationally,
  limited staff is the #1 barrier *even to using ATSPM*, and 78% of state DOTs
  review ATSPM reports only ad hoc.
- **That gap between dashboard and action is where AI agents could matter
  most.** An agent could:
  - watch hundreds of signals' data every day;
  - rank the problems;
  - draft a fix with supporting evidence;
  - hand a short, reviewable list to an engineer.

  Nobody has shown this working in the field yet, so it's a pilot
  opportunity, not a proven tool.
- **Some things stay human:** physical repair of detectors and cabinets,
  safety-critical clearance timing, value trade-offs (arterial vs. side
  street vs. pedestrians), and professional-engineer accountability.

## 6.2 Where the hours go in a traditional retiming

FHWA's staffing guide gives a consultant's estimate of person-hours per
intersection:[^hop09006]

| Task | Hours | Share | Automatable today? |
|---|---|---|---|
| Weekday turning-movement counts | 19.8 | 46% | **Yes.** Controller/ATSPM counts, video analytics, probe-based estimates |
| Saturday turning-movement counts | 4.6 | 11% | **Yes**, same |
| Signal timing analysis (modeling and optimization) | 7.5 | 17% | **Partly.** Optimizers are mature; network coding is increasingly automated; an engineer must review |
| Fine tuning in the field | 6.0 | 14% | **Partly.** ATSPM charts allow much tuning from the desk; some field observation remains |
| Field inventory | 1.5 | 3.5% | Partly (aerial imagery, existing GIS, controller database) |
| Qualitative assessment | 1.5 | 3.5% | Mostly human |
| Final delivery / documentation | 1.3 | 3% | **Yes.** Drafting reports is a good LLM task |
| Project management | 0.8 | 2% | Mostly human |
| **Total** | **43.0** | | |

Before/after evaluation isn't in that table; it was often a separate
cost. Utah once had a full-time employee who did nothing but drive
corridors for before/after studies.[^appa]

**About 57% of the hours are counting cars.** That's the part automation has
already eliminated where agencies invested in it.

**What counts cost.** Fort Bend County, TX's 2025 bids ran $220–325 for a
4-hour peak turning-movement count and $450–630 for a 12-hour count.
Maricopa estimated $400 per intersection. ⚠️ (source not yet re-checked)

## 6.3 What automation has already delivered

| Agency | What changed | Documented effect |
|---|---|---|
| **Utah DOT** (ATSPM) | Counts come from controllers. Modeling is "limited to the development of offsets." Daily automated detector checks. | "No longer collects turning movement counts using traditional methods, and no longer uses an FTE for floating-car studies." In Feb 2019, 226 public calls produced only 137 work orders (vs. 226 before). Detector problems are seen "about a month before a call might come in."[^appa] |
| **Georgia DOT** (ATSPM) | Field visits only when a ticket or ATSPM alert points to a problem | **70% fewer** locations needing field visits: 12,600 fewer visits a year, about $630K/yr.[^appa] |
| **Anne Arundel County, MD** (Miovision ATSPM + consultant) | 8-signal corridor retimed "without traditional traffic counts and models" | "No field observations were needed"; timeline "from months to weeks"; benefit-cost 14:1.[^annearundel] |
| **Purdue/INDOT** (connected-vehicle data) | Offsets set from vehicle trajectories, no detectors needed. Statewide ranking of 2,000+ signals to decide where to look. | CV offsets comparable to detector-based ones; "two weeks of data may be sufficient."[^day2016] 11 timing changes at 9 signals cut delay by up to 53 s/veh.[^jtrp2024] Retiming SR-9 in Anderson, IN raised arrivals on green from 62% to 69% ⚠️ (source not yet re-checked). |
| **Utah, again** | Retiming is now needs-based | "We no longer go out to retime signals every three to five years. Now, we do it only when it's needed."[^hop18048] |

**What Utah's switch cost.** The floating-car FTE UDOT no longer needs cost
about $116,000 a year. Implementation took 8,000 hours (2012–2018), and
ATSPM upkeep is about 10% of one FTE. ⚠️ (source not yet re-checked)

**Staffing benchmark.** UDOT operates **1,252 signals** with 1 engineering
manager, 2 statewide timing engineers, 4 region signal engineers, 4 timing
technicians and 8 maintenance technicians, plus 3 consultant firms.[^ch4]
That's well over the "1 engineer per 75–100 signals" rule of thumb,
achievable because of automation plus consultants. Georgia runs 6,804
signals with 70–80 FTE including consultants.[^ch4]

## 6.4 Newer AI products (vendor claims, not yet independently evaluated)

| Product | What it automates | Claim |
|---|---|---|
| **Google Project Green Light** | Infers existing timing from Maps data; recommends changes | Engineers implement "in as little as five minutes"; no figure for review time.[^greenlight] Some cities rejected recommendations (see [chapter 5](05-ai-and-emerging-tech.md)). |
| **Flow Labs Optimus Gen2** (Apr 2026) | Retiming from connected-vehicle data with a transformer model | Retiming "from months to minutes"; automates "months of manual model building and calibration"[^flowlabs] |
| **Miovision One** (May 2026) | Includes "Mateo," a generative-AI assistant for plain-language questions about network performance, plus an optimizer and remote deployment | "Up to 50% faster retiming"; engineers review before implementation[^miovision] |
| **Iteris ClearGuide Signal Trends**, **INRIX Signal Analytics** | Probe-based signal performance monitoring | "Eliminates the need for traffic counting studies"[^clearguide]; INRIX reports agencies in 20 states monitoring 10,000+ intersections[^inrix] |
| **Econolite Centracs SPM** (ACHD's platform family) | Performance analytics and heat maps | "Eliminate the cost of manual traffic counts." No automated timing recommendations described.[^centracs] Econolite's real-time optimization is a separate product, **Edaptive** ⚠️ (source not yet re-checked). |

Other vendors: NoTraffic claims 24% less delay in Oklahoma City. We found no
evidence of Rekor doing signal timing. ⚠️ (source not yet re-checked)

The direction is clear: vendors are racing to automate the analysis step.
None of these labor claims has been independently evaluated yet.

## 6.5 LLM agents: what they're good and bad at here

**Research status (2023–2026):** almost all simulation or prototype work.

- **Tool-using agents.** TrafficGPT and Open-TI are LLMs that call traffic
  models.[^trafficgpt][^openti] **ChatSUMO Agent** builds SUMO simulations from
  conversation and reports "reducing manual configuration effort by over
  80%."[^chatsumo] SUMO-MCP exposes the SUMO simulator as tools an agent can
  call.[^sumomcp]
- **Reading timing plans.** **Chat2SPaT** turns plain-language timing-plan
  descriptions into exact phase and timing plans with >94% accuracy.[^chat2spat]
  That's impressive, but it still means about 1 in 20 plans has an error.
- **Engineering reasoning.** On TransportBench (140 undergraduate
  transportation-engineering problems), the best model tested scored 67%.
  It also changed correct answers to wrong ones when asked to
  double-check.[^transportbench] Newer models will do better, but the lesson
  holds: **safety-critical numbers must come from deterministic code.**
- **Agencies.**
  - MnDOT is piloting a generative-AI chatbot for questions about the MUTCD
    (the federal traffic-control manual).
  - Pennsylvania's ChatGPT pilot found it is "not… a substitute for the
    nuance and experience of current employees."
  - "Nearly all statewide AI policies include a 'human in the loop'
    requirement."[^ltrc]
- **Federal direction.** FHWA's August 2026 AI roadmap lists "AI assurance"
  and "agentic AI" as research areas.[^fhwaai] ⚠️

**Where agents fit well:**

- Wrangling data across systems (ATSPM exports, probe data, GIS, timing
  databases, work orders).
- Daily triage: "which 10 of 500 signals got worse this week, and why?"
- Drafting change packages with charts and before/after predictions from a
  simulator.
- Writing documentation, public-records responses, commission reports and
  complaint replies.
- Linking a citizen complaint to the specific signal and phase and checking
  it against the data before anyone drives out.

**Where they must not go:**

- Computing yellow and all-red clearance or pedestrian clearance. The MUTCD
  requires these to be set by engineering practice; use the deterministic
  formulas.[^mutcd]
- Writing to controllers or central systems directly. This is a
  cybersecurity and liability boundary: networked controllers have known
  exploits, and the conflict monitor prevents conflicting greens but not
  malicious timing.[^cve]
- Making value trade-offs on their own, such as side-street vs. arterial
  priority or pedestrian service levels.

## 6.6 The catch: automation shifts work

- **Using the tools is itself labor.** FHWA's model of Utah's system counts
  tool use as new work: engineers and technicians each spending about
  10 h/week.[^appa] The model puts that new tool-use work at about
  **$1.2M a year** (about 18,200 hours). ⚠️ (source not yet re-checked)
- **Few agencies measure the payoff.** Only 2 of 7 agencies studied tracked
  ATSPM benefits quantitatively. ⚠️ (source not yet re-checked)
- **Staff is the barrier even for ATSPM.** In NCHRP Synthesis 659 (2026),
  23 of 24 state DOTs said limited staff was the top barrier to expanding
  ATSPM. 78% review ATSPM reports ad hoc, and only about 12% routinely for
  timing. North Carolina flagged "the potential for information overload."[^nchrp659]
- **Open-source ATSPM strained smaller agencies.** Lake County, IL and
  PennDOT struggled with crashes and upgrades and moved to vendor
  platforms.[^ch4]
- **Adaptive systems get switched off when staff can't maintain them.**
  FHWA: adaptive systems "have been deactivated well before the end of their
  useful life due either to a lack of adequate resources or agency
  capability."[^asctse] Gahanna, OH dropped ACS Lite for lack of staff
  ⚠️ (source not yet re-checked). ACHD's 2014–15 InSync removal (see
  [chapter 2](02-treasure-valley-signal-system.md#27-lessons-from-the-failed-adaptive-pilot))
  is a local example of a related failure.

**Implication.** The design target for any automation, AI or not, should be
**fewer, better decisions for humans**, not more data. Success looks like
"every Monday the engineer gets the 10 signals that most need attention, each
with a diagnosis, evidence, and a drafted fix to approve or reject."

## 6.7 What this could mean for ACHD (our estimates)

This is rough arithmetic built on the sourced inputs above; treat it as
order-of-magnitude:

| | Traditional | With mature automation |
|---|---|---|
| Retimes per year (≈500 signals, 3-year cycle) | ≈167 | ≈167, or fewer with needs-based retiming as in Utah |
| Hours per retime | ≈43 | ≈12–18 (counts and evaluation automated; analysis partly) |
| **Retiming labor per year** | **≈7,200 h** (≈3.5 FTE) | **≈2,000–3,000 h** (≈1–1.5 FTE) |
| Engineer-type hours | ≈3,000 h | ≈1,500–2,000 h |
| Technician field visits | Routine checks plus every complaint | 50–70% fewer, per GDOT and UDOT |

- **AI agents on top of that:** perhaps another 10–30% on triage and
  documentation. This is unproven and is the part worth piloting.
- **What doesn't shrink:** detector, cabinet and knockdown repair. Automation
  reduces wasted trips (perhaps 1.2–1.5× technician capacity), but the
  physical work remains.

**Staffing benchmarks from 2019**, by agency size ⚠️ (source not yet
re-checked):

| Agency size | Engineers | Technicians | All staff |
|---|---|---|---|
| 150–450 signals | 2.4 | 6.4 | 20.9 |
| 450–1,000 signals | | | 43.5 |

ACHD's working number of about 500 signals sits just inside the larger
band. A peer under strain: New Orleans (about 462 signals) had 2
maintenance employees in May 2024 and 2,000+ pending 311 signal requests.
⚠️ (source not yet re-checked)

**Preconditions:**

- reliable communications to every signal;
- high-resolution logging enabled on the Cobalt controllers;
- detection good enough for the metrics;
- someone assigned to own the monitoring workflow.

Several of the unfunded COMPASS items in [chapter 2](02-treasure-valley-signal-system.md#25-whats-on-the-unfunded-list)
(the $6M of signal performance measures and the $200K asset management system)
are exactly these preconditions.

## 6.8 Guardrails for an agent-assisted pipeline

If ACHD, or a research team working with ACHD, piloted an AI-assisted
workflow, these rules would keep it safe and credible:

1. **Read-only access.** The agent reads exports (ATSPM, probe data, timing
   database); it never connects to controllers or the central system.
2. **Deterministic safety math.** Clearance intervals, pedestrian timing and
   minimum greens are computed by audited code using ITE/MUTCD methods, and
   locked against agent edits.
3. **Engineer approval gate.** Every change is a proposal with evidence; a
   licensed engineer approves and an existing staff workflow implements it.
4. **Simulation before field.** Proposed changes are run in a calibrated
   model (SUMO or Synchro/Vissim) of the corridor first.
5. **Measured outcomes.** Before/after with comparison corridors, or
   switchback (alternating plans) where feasible; results published.
6. **Easy rollback** and a full audit trail of what changed, when, why, and
   who approved it.
7. **Track acceptance rates.** How many agent proposals were accepted,
   modified or rejected, and why. This is the honest measure of whether the
   agent saves engineer time.

## 6.9 What an outside team could prototype now

Without any agency access, a team could build and demonstrate the
**triage-and-propose** layer using the data in [chapter 7](07-diy-data-collection.md):

- Combine probe travel times, GPS floating-car runs and camera snapshots
  into a weekly corridor scorecard.
- Have an agent rank problem locations, explain the evidence, and draft a
  short memo per location.
- Use our cycle-length estimator (`tools/gps_runs.py --estimate-cycle`) to
  infer basic timing at a few signals.
- Show the workflow to ACHD as a demo of what it could look like on its own
  ATSPM data.

That would be a concrete, low-risk proposal that fits ACHD's stated
preference for "proven technology and signal performance measurement."

---

**Next:** [07 — Do-it-yourself data collection](07-diy-data-collection.md)

[^hop09006]: FHWA, *Traffic Signal Operations and Maintenance Staffing Guidelines* (FHWA-HOP-09-006, 2009), Table 2.15; also the source of the survey average of 185 signals per engineer. https://ops.fhwa.dot.gov/publications/fhwahop09006/fhwahop09006.pdf
[^appa]: FHWA-HOP-20-003, Appendix A (ATSPM agency case studies). https://ops.fhwa.dot.gov/publications/fhwahop20003/appa.htm
[^ch4]: FHWA-HOP-20-003, Chapter 4. https://ops.fhwa.dot.gov/publications/fhwahop20003/ch4.htm
[^hop18048]: FHWA-HOP-18-048. https://ops.fhwa.dot.gov/publications/fhwahop18048/index.htm
[^annearundel]: NOCoE case study, Anne Arundel County (Oct 2024). https://www.transportationops.org/system/files/uploaded_files/2024-10/Anne%20Arundel%20County%20-%20Applying%20Emerging%20Technologies%20for%20Smarter%20Traffic%20Signal%20Optimization%20Processes%20-%20NOCoE%20Case%20Study.pdf
[^day2016]: Day et al. (2016), Purdue. https://docs.lib.purdue.edu/civeng/43
[^jtrp2024]: Purdue JTRP-2024/33. https://docs.lib.purdue.edu/jtrp/1872
[^greenlight]: Google, Jul 2024. https://blog.google/outreach-initiatives/sustainability/google-ai-project-greenlight/
[^flowlabs]: Traffic Technology Today, Apr 2026. https://www.traffictechnologytoday.com/news/artificial-intelligence-ai/flow-labs-launches-ai-powered-signal-retiming-tool-optimus-gen2.html
[^miovision]: Miovision, May 20, 2026. https://miovision.com/press-release/miovision-delivers-the-future-of-proactive-signal-retiming-with-new-ai-driven-end-to-end-traffic-optimization-solution/
[^clearguide]: Iteris, Mar 2024. https://www.iteris.com/news/iteris-launches-new-clearguide-signal-trends-probe-based-option-improving-intersection
[^inrix]: AJOT. https://www.ajot.com/news/agencies-in-20-states-use-inrix-signal-analytics-to-identify-and-reduce-excessive-delays-and-emissions
[^centracs]: Econolite Centracs Mobility SPM datasheet (2024). https://www.econolite.com/wp-content/uploads/2024/03/Centracs-Mobility-SPM_datasheet_2024_digital.pdf
[^trafficgpt]: Zhang et al., TrafficGPT. https://arxiv.org/abs/2309.06719v1
[^openti]: Da et al., Open-TI. https://arxiv.org/pdf/2401.00211
[^chatsumo]: ChatSUMO Agent, *Transportation Research Part C* (Sept 2026). https://trid.trb.org/View/2704119
[^sumomcp]: SUMO-MCP. https://arxiv.org/abs/2506.03548
[^chat2spat]: Chat2SPaT. https://arxiv.org/abs/2507.05283
[^transportbench]: TransportBench. https://arxiv.org/html/2408.08302
[^ltrc]: Louisiana Transportation Research Center, FR-722 (Jan 2026). https://www.ltrc.lsu.edu/pdf/2026/FR_722.pdf
[^fhwaai]: FHWA, AI for Safety and Efficiency roadmap (FHWA-HRT-26-063, Aug 2026); content from search summaries. https://highways.dot.gov/sites/fhwa.dot.gov/files/FHWA-HRT-26-063.pdf
[^mutcd]: MUTCD (2009 ed.) §4D.26 and §1A.13. https://mutcd.fhwa.dot.gov/htm/2009/part4/part4d.htm · https://mutcd.fhwa.dot.gov/htm/2009/part1/part1a.htm
[^cve]: TechCrunch, Jul 18, 2024. https://techcrunch.com/2024/07/18/hackers-could-create-traffic-jams-thanks-to-flaw-in-traffic-light-controller-researcher-says
[^nchrp659]: NCHRP Synthesis 659 (2026). https://www.nationalacademies.org/read/29326/chapter/7 · https://www.nationalacademies.org/read/29326/chapter/6
[^asctse]: FHWA-HOP-11-027. https://ops.fhwa.dot.gov/publications/fhwahop11027/es.htm
