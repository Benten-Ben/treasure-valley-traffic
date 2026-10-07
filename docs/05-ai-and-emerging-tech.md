# 5. AI and emerging technology: how Google and others have tested it

This chapter covers what Google's teams have built and how they tested it,
the other AI signal systems on the market, the research frontier, the policy
context, and what it all could mean for the Treasure Valley.

---

## 5.1 Summary

1. **Google's main signal product is Project Green Light.** It's
   deliberately **advisory, not autonomous**. It infers how existing signals
   are timed from aggregated Google Maps driving data, then recommends small
   timing changes that city engineers review and implement themselves. Google
   never touches signal hardware.
2. **The results are real but modest, and mostly self-reported.** Google
   claims "up to 30%" fewer stops and "up to 10%" lower emissions at
   coordinated intersections. The closest thing to independent evidence is
   Boston's INRIX evaluation: **delay −13.5%, stops −20%** across 114
   intersections. Some cities rejected or reverted recommendations.
3. **Google's testing approach is the more transferable lesson.** Across its
   mobility work, Google uses a range of evaluation methods:
   - offline evaluation;
   - calibrated simulation ("digital twins");
   - simulate-then-field-deploy;
   - before/after field measurement;
   - randomized switchback experiments, the strongest design, used for
     routing.
   
   A local pilot can borrow this approach.
4. **Most "AI traffic light" claims elsewhere come from vendors or
   simulation.** Deep reinforcement learning and LLM controllers are still
   almost entirely simulation-only. The field results that do exist (Surtrac,
   NoTraffic, City Brain) are mostly developer- or vendor-reported, without
   control groups.
5. **For ACHD, Green Light is a low-cost, low-risk option worth exploring.**
   It's free, needs no hardware or system integration, and can be exited on
   short notice. But it only helps if engineers have time to implement and
   evaluate recommendations, which is the same staff constraint described in
   [chapter 4](04-improvement-playbook.md#44-the-resource-arithmetic-for-ada-county).

---

## 5.2 Google Project Green Light

### Timeline

| Date | Milestone |
|---|---|
| Oct 2021 | First disclosed: AI-timed lights piloted at 4 locations in Israel (Haifa, Beer-Sheva), claiming 10–20% lower fuel use and intersection delay. Rio de Janeiro next.[^engadget] Google's Kate Brandt disclosed it on **Oct 6, 2021**, and the Israel National Roads Company was a partner alongside Haifa and Beer-Sheva ⚠️ (source not yet re-checked). |
| Late 2022 | Work with Seattle begins (first US city).[^seatoday] |
| Oct 10, 2023 | Public launch at Sustainable with Google: **70 intersections in 12 cities**, including Abu Dhabi, Bali, Bangalore, Budapest, Haifa, Hamburg, Hyderabad, Jakarta, Kolkata, Manchester, Rio de Janeiro and Seattle.[^launch] |
| Jan 2024 | Seattle DOT publishes its experience.[^sdot] |
| Apr 2024 | Boston pilot begins.[^bostonblog] |
| May–Jun 2025 | Boston expands to **114 intersections**; Google says Green Light is in **18 cities across four continents**. Boston publishes INRIX-evaluated results.[^bostonblog][^boston] |
| Jul 2026 | Vancouver joins (pilot through Dec 2027). Coverage says "about 20 participating cities worldwide."[^vancouver] |
| Oct 2026 | Google's program site says Green Light "is now available in over 100 cities worldwide" and affects "up to 47M car rides every month."[^site] |

The city count conflicts. "Available in over 100 cities" on Google's site
probably means something different from "about 20 participating" cities in
July 2026 press coverage. We found no dated announcement explaining the jump.
In the US, only **Seattle and Boston** are confirmed partners. We found **no
evidence that ACHD, ITD, Boise, Nampa or any Treasure Valley agency has
joined**.

### How it works

Google describes four steps:[^site]

1. **Infer the current timing.** Estimate each intersection's "cycle length,
   transition time, green split … coordination and sensor operation
   (actuation)" from aggregated Google Maps trip data. No data from the city
   is needed.
2. **Model traffic patterns.** Stop-and-go behavior, wait times,
   coordination between neighboring intersections, and time-of-day patterns.
3. **Generate recommendations** using AI models: typically small changes to
   splits and offsets, or coordinating adjacent intersections into "waves of
   green."[^bostonblog]
4. **Measure impact.** Stops saved and modeled emissions, from the same Maps
   data after implementation.

**Human in the loop:** engineers see recommendations, supporting data, and
measured impact in a Google interface. They decide whether to implement each
recommendation on their own systems, "in as little as five minutes," and
can revert at any time.[^site] A typical change is small. Seattle "moved four
seconds from a north-south street to an east-west street for a particular
time of day."[^cbs]

### How Google and cities have tested it

| Evidence | Design | What it showed |
|---|---|---|
| Google program claims | Before/after using Maps probe data; "early data points … averaged from coordinated intersections"; emissions "modeled using an emissions model from the Department of Energy, with a single vehicle type" | "Up to 30%" fewer stops, "up to 10%" lower emissions[^site] |
| Google research papers (2024–25) | Methods papers, including a real **before/after field test in Jakarta** of offset coordination for intersection pairs, a **Haifa citywide study** of traffic variability across 162 intersections, and methods to detect unintended plan changes | Technical basis; peer-reviewed or conference-published, but Google-authored[^papers] |
| **Boston (INRIX evaluation)** | Third-party before/after, city-published; no control group described | Delay **−13.5%** average (up to 24%); stops **−20%**; Atlantic Ave & Richmond St: delay −21%, stops −33%; about 4,000 gal fuel/yr per recommendation[^boston] |
| Seattle DOT | Implemented changes at several intersections; reviewed outcomes | Called it "very low-risk, high-potential return." **Reverted one change** that "did not result in a net benefit."[^apa][^sciam] |
| Transport for Greater Manchester | Engineer review of recommendations | One junction improved 9% (AM) and 18% (PM). Recommendations "did not always lead to a change," because signals there also serve bus and pedestrian priority and discourage rat-running.[^tfgm] |

**Limitations and critiques:**

- **Narrow objective.** It optimizes car stops and delay. Transit,
  pedestrian and cycling priorities aren't part of the objective.[^sciam]
- **Baseline dependence.** University of Michigan's Henry Liu: gains are "all
  dependent on the baseline you're comparing to." Badly timed signals improve
  a lot; well-timed ones barely improve.[^sciam]
- **Induced demand.** Smoother driving can attract more driving.[^sciam]
- **Emissions framing.** At launch, Google said pollution at intersections
  can be **29 times** that on open road, and that about half of intersection
  emissions come from stop-and-go traffic.[^launch] Scientific American's
  critique cites the Congressional Budget Office (CBO, 2022): congestion
  accounts for about **2% of US transport emissions**.[^sciam]
- **It retunes static plans offline.** It's not real-time adaptive, so it
  can't respond to incidents or events as they happen.
- **It depends on Maps data density** and on agency staff time to act on
  recommendations.
- **Headline numbers are self-reported "up to" figures.**

### Terms and how to join

- **Cost:** free during the "early research phase."[^site]
- **Privacy:** "User data is never shared with the city or any other third
  party"; recommendations come from aggregated, anonymized data.[^site]
- **Agreement model (Vancouver, 2026):**[^vancouver]
  - zero cost;
  - the city does **not** provide signal timing plans or operational data;
  - Google does **not** connect to city systems;
  - the city can exit on **60 days' notice**;
  - no competitive bid, because the technology is proprietary.
- **How to join:** agencies (city representatives or traffic engineers) fill
  in a waitlist form on the program site.[^site] Individuals can't sign up a
  city, but they can ask their agency to.

### Still to find out

1. **Eligibility minimums:** how dense the probe data must be, whether a
   central signal system is needed, and whether a county highway district
   (like ACHD) is eligible.
2. **Acceptance and persistence:** what share of Green Light
   recommendations cities accept, and whether the benefits persist.
3. **Henry Liu's probe-based retiming case in Birmingham, Michigan:** what
   was done and what it showed ⚠️ (source not yet re-checked).

## 5.3 How Google tests mobility AI more broadly

Google's other mobility projects show the range of evaluation methods it
uses. That range is a useful template for any local pilot.

| Project | What it is | How it was tested |
|---|---|---|
| **DeepMind + Maps ETA prediction** (2020–21) | Graph neural networks predict travel times | Offline comparison against the previous model, then production deployment. Reported up to 50% better ETA accuracy in some cities and "40+%" fewer bad ETAs in Sydney.[^deepmind][^etapaper] |
| **Eco-friendly routing** (2021–) | Suggests the most fuel-efficient route | Modeled counterfactual (chosen vs. fastest route), built with NREL. Google reports more than 3M tCO2e avoided in 2025. Not independently audited.[^ecorouting] |
| **Digital-twin calibration** (2024–25) | Calibrates SUMO simulations to Google Maps travel times | 54 scenarios in six US metros, **including Salt Lake City**. Fit to observed data improved about 44% on average, up to 80%.[^twin] |
| **Seattle stadium exit plans** (2023) | Simulation-designed post-event routing via message signs | Designed in SUMO, deployed with SDOT, and **verified across multiple events**. Average exit travel time cut by about 7 minutes.[^stadium] |
| **Collaborative routing experiment** (published 2026) | Slight rerouting of under 2% of trips to relieve congested segments | **Randomized city-wide switchback design** (treatment and control alternating by day) across 10 US cities for 6 months, analyzed with hierarchical Bayesian models. Speeds +2% on targeted segments, fuel −0.5–1.0%. Published in *Nature Cities*.[^collab] |
| **Mobility AI program** (2025–26) | Umbrella program: measurement, simulation, optimization (signals included) | Names synthetic controls (e.g., NYC congestion pricing), simulation what-ifs, and field studies as its evaluation methods.[^mobilityai] |

**"Routing" vs. "signals."** These are two different things Google can
change:

- **Routing** means the turn-by-turn directions Google Maps gives drivers:
  which roads it tells them to take. Google fully controls this, so it can run
  a true randomized experiment. In the collaborative-routing study, on
  "treatment" days Maps nudged under 2% of trips onto slightly different
  routes to relieve congested segments. On "control" days it routed normally.
  Comparing those days gives a clean causal answer.
- **Signals** means traffic-light timing. Google doesn't control traffic
  lights; city engineers do. Google can only recommend changes, and once a
  city adopts one it usually stays in place. So Green Light's evidence is
  mostly "before vs. after" for the same intersection, which can be confused
  by anything else that changed in between (season, construction, gas
  prices, school schedules).

**Lesson for a local pilot.** Google's strongest evidence comes from
randomized switchback trials and repeated field verification, and those were
used for **routing**, not signals. Green Light evidence is weaker, mostly
before/after comparisons. A Treasure Valley pilot could do better at low cost
by building in the stronger designs:

- untreated **comparison corridors**;
- **switchback** timing (alternating old and new plans by day or week);
- **pre-registered metrics**;
- a **third-party evaluator** (as Boston used INRIX), or a university partner.

**A cautionary case on data access.** Replica, a Sidewalk Labs spin-out,
ran a pilot that Portland approved in Dec 2018 for **$457,300**. It ended
around Feb 2021 after Metro (the Portland region's government) asked for
raw, disaggregated data and Replica refused ⚠️ (source not yet re-checked).

## 5.4 Other AI and adaptive signal systems

| System | Approach | Evidence | Notes |
|---|---|---|---|
| **Surtrac** (CMU → Rapid Flow → Miovision) | Decentralized, real-time schedule-driven adaptive | 9-intersection Pittsburgh pilot (2012): >25% better travel time, stops and wait. Floating-car before/after, run by the developers, no control group.[^surtrackrs] | About 350 intersections when Miovision acquired it in 2022.[^miovision] |
| **NoTraffic** | AI sensors at the intersection + cloud optimization | Phoenix pilot (2020) with university evaluators. Vendor claims PM delay −29%; method not disclosed.[^notraffic] The pilot ran on Glendale Ave from Aug 2020; the Maricopa Association of Governments (MAG) funded it through its emerging-technology program, and ASU, the University of Arizona and NAU evaluated it ⚠️ (source not yet re-checked). | No Idaho deployment found |
| **Maricopa County AI adaptive pilot** | AI adaptive control | ⚠️ Delay −46% (29.5 s to 13.7 s) over one week at one intersection, extrapolated to 170 intersections (USDOT ITS Knowledge Resources, ITS-KRS 2025-b02021, from a search excerpt). Those two delays are a 54% cut, not 46%, so the source needs checking. | Vendor unconfirmed |
| **LYT** | Cloud-based transit and emergency signal priority | San Jose: transit red-light wait −50% (vendor-reported)[^lyt] | Relevant to VRT's State Street priority. Maryland MTA contract for 90 intersections (Sep 2025) ⚠️ (source not yet re-checked) |
| **Econolite Centracs + PTV Flows** | Machine-learning traffic prediction up to 60 min ahead, plugged into Centracs | Vendor-announced (2024)[^econoliteptv] | **ACHD now runs Centracs**, so this is the AI add-on closest to ACHD's platform. Paid product |
| **Yunex (ex-Siemens) Flow AI** | AI adaptive control | 47% less waiting, in simulation (Hagen, Germany)[^yunex] | Simulation only |
| **Alibaba City Brain** (Hangzhou) | City-scale AI traffic management | Vendor/government claims (15% faster passage)[^citybrain] | No independent evaluation |

FHWA's baseline for comparison: conventional adaptive control improves travel
time by more than 10% on average.[^asct] Adaptive control runs on roughly
4–5% of US signals.[^sciam]

**Ownership changes.** Besides Miovision's 2022 purchase of Rapid
Flow,[^miovision] Almaviva bought **Iteris** for $335M (Nov 2024), and
Siemens sold **Yunex Traffic** to Atlantia for €950M (closed Jun 30, 2022)
⚠️ (source not yet re-checked).

## 5.5 The research frontier

- **Deep reinforcement learning.** IntelliLight (2018), PressLight (2019),
  CoLight (2019), and MPLight (2020), the last simulated on 2,510 Manhattan
  signals.[^intellilight][^presslight][^colight][^mplight] Strong results in
  simulators (CityFlow, SUMO, LibSignal).[^cityflow][^libsignal]
- **Max-pressure control.** A decentralized rule with provable throughput
  guarantees; first real-world test at one Jerusalem intersection.[^maxpressure]
  Minnesota has tested it with real controllers in the lab
  (hardware-in-the-loop).[^umn]
- **The sim-to-real gap is the central unsolved problem.**
  - A 2024 review found the field still overwhelmingly simulation-based.[^review]
  - A Sept 2026 paper notes that simulator-trained policies "often fail once
    deployed in the real world" and that there's no standard benchmark for
    real-world transfer.[^sim2signal]
  - Fraunhofer's Lemgo (Germany) project put deep RL on a live junction after
    10–15% simulated gains.[^fraunhofer]
- **LLM-based control.** LLMLight / LightGPT (2023–24) and follow-ons are
  research-only, with no field deployments found.[^llmlight]

**Maturity summary:** probe-data-driven retiming (Green Light, Purdue
connected-vehicle methods) and ATSPM are **deployable now**. Commercial
adaptive and AI sensor systems are **deployable with care**. Reinforcement
learning and LLM controllers are **research**.

## 5.6 Policy and infrastructure context

- **USDOT AI efforts:**
  - The ITS Joint Program Office's "AI for ITS" program lists signal timing
    as a use case. Its 2024 maturity model found that "a large proportion of
    organizations" are at maturity level zero.[^itsjpo]
  - USDOT announced a broader AI initiative for infrastructure in July 2026;
    program details were still emerging at the time of writing.[^usdotai]
    Secretary Duffy and Assistant Secretary Seval Oz announced it on
    **Jul 22, 2026**, with the Department of Energy (DOE) and the National
    Science Foundation (NSF) as partners ⚠️ (source not yet re-checked).
- **SMART grants for signal projects** (the program is listed among
  funding sources in [chapter 4](04-improvement-playbook.md#411-funding-sources)):
  - Regional Transportation Commission (RTC) of Southern Nevada: **$2M**
    (Mar 2023) for cloud signal timing with AI analytics ⚠️ (source not yet
    re-checked).
  - Manchester, NH: **$2M** Stage 1 (Dec 2024), live at 22 intersections by
    Aug 2026 ⚠️ (source not yet re-checked).
- **Connected vehicles (V2X).** The national deployment plan targets V2X at
  25% of signalized intersections in the top 75 metros by 2028.[^v2x]
  Whether Boise is among those 75 metros is still to find out. The FCC's
  C-V2X rules began a **2-year transition on Dec 13, 2024** ⚠️ (source not
  yet re-checked). ACHD already ran a 20-intersection SPaT (Signal Phase and
  Timing broadcast) pilot in 2017–19 (see [chapter 2](02-treasure-valley-signal-system.md#23-operations-center-and-technology-timeline)).
- **Cybersecurity:**
  - In 2024, a controller vulnerability (Intelight X-1, CVE-2024-38944)
    allowed unauthenticated signal control over the internet.[^cve]
  - In Mar 2026, flaws in **Daktronics** sign controllers were patched
    ⚠️ (source not yet re-checked).
  - The 2019 benchmarking report found more than half of agencies had no
    cybersecurity policy.
  - Advisory, offline systems like Green Light avoid adding new network
    connections into signal systems, which is a real advantage.

## 5.7 What this could mean for the Treasure Valley

This is our synthesis, not sourced fact. Options are ranked from lowest to
highest effort and risk:

1. **Probe-data measurement first.** Whatever AI does next, the region needs
   a baseline. Probe data (Purdue connected-vehicle methods, INRIX, ClearGuide)
   plus ATSPM on ACHD's new Econolite controllers would show where timing is
   the problem. This is a precondition for evaluating any AI pilot fairly.
2. **Ask ACHD to join the Green Light waitlist.**
   - **Why it fits:** free; no hardware, data sharing or system connection;
     60-day exit; ACHD is a single operator like Seattle's and Boston's
     agencies.
   - **What it needs:** engineer time to review and implement
     recommendations; enough Maps data on candidate corridors; closely spaced
     signals where offset fixes pay off.
   - **Where it would help most:** where timing is stale. Henry Liu's
     baseline point cuts both ways.
   - **Coordination:** state-highway corridors (Eagle, State, Chinden) need
     ITD on board.
3. **Run any pilot as a real experiment.** Use comparison corridors, a
   switchback design if possible, a third-party or university evaluator, and
   published acceptance and rejection rates for recommendations. That gives
   ACHD the evidence its 2012 Traffic Services Manager said was hard to get,
   and avoids repeating the 2014–15 adaptive experience.
4. **Evaluate the Centracs-native options.** Econolite's prediction and
   adaptive add-ons run on the platform ACHD just bought. They cost money,
   but they keep everything in one system.
5. **Targeted adaptive or AI control only where demand is unpredictable.**
   Candidates include event traffic (Boise State games, the Ford Idaho
   Center), I-84 incident diversion routes, and transit priority on State
   Street. Use radar or thermal detection rather than video, given the
   glare and fog history.
6. **Partner on research.** Google's digital-twin calibration already
   covered Salt Lake City. A COMPASS/ACHD/university SUMO model of a
   Treasure Valley corridor is technically feasible, would let interventions
   be tested before deployment, and is a plausible grant or research
   partnership.

---

**Back to:** [README](../README.md)

[^engadget]: Engadget, Oct 6, 2021. https://www.engadget.com/google-ai-traffic-lights-research-environment-pollution-070132356.html
[^seatoday]: SEAtoday. https://seatoday.6amcity.com/city/google-ai-project-green-light-seattle
[^launch]: Google, Oct 10, 2023. https://blog.google/outreach-initiatives/sustainability/google-transportation-energy-emissions-reduction/ · https://blog.google/company-news/outreach-and-initiatives/sustainability/google-ai-reduce-greenhouse-emissions-project-greenlight/
[^sdot]: SDOT Blog, Jan 4, 2024. https://sdotblog.seattle.gov/2024/01/04/project-green-light/
[^bostonblog]: Google, May 22, 2025. https://blog.google/outreach-initiatives/sustainability/project-green-light-boston-expansion/
[^boston]: City of Boston, June 17, 2025. https://www.boston.gov/news/mayor-wu-announces-expansion-project-green-light-signal-optimization-program
[^vancouver]: Daily Hive, Jul 29, 2026. https://dailyhive.com/vancouver/vancouver-google-project-green-light-traffic-partnership
[^site]: Google Research, Project Green Light (accessed Oct 2026). https://sites.research.google/gr/greenlight/
[^cbs]: CBS News, Jan 4, 2024. https://www.cbsnews.com/news/google-project-green-light-seattle/
[^papers]: Google Research publications: https://research.google/pubs/quantitative-approach-for-coordination-at-scale-of-signalized-2-intersection-pairs/ · https://research.google/pubs/city-wide-probe-based-study-of-traffic-variability/ · https://research.google/pubs/estimating-daily-start-times-of-periodic-traffic-light-plans-from-traffic-trajectories/ · https://research.google/pubs/systematic-data-driven-detection-of-unintentional-changes-in-traffic-light-plans/
[^apa]: APA Planning, Mar 14, 2024. https://w1.planning.org/planning/2024/mar/green-means-go-seattles-ai-solution-to-reduce-stoplight-idling
[^sciam]: Scientific American, Aug 15, 2024. https://www.scientificamerican.com/article/googles-project-green-light-uses-ai-to-take-on-city-traffic/
[^tfgm]: Road Safety GB, Oct 27, 2023. https://roadsafetygb.org.uk/?p=20351
[^deepmind]: DeepMind blog, Sep 3, 2020. https://deepmind.google/blog/traffic-prediction-with-advanced-graph-neural-networks/
[^etapaper]: Derrow-Pinion et al., "ETA Prediction with Graph Neural Networks in Google Maps," CIKM 2021. https://arxiv.org/abs/2108.11482
[^ecorouting]: Google sustainability. https://sustainability.google/ · https://research.google/blog/introducing-mobility-ai-advancing-urban-transportation/
[^twin]: Google Research blog, Feb 10, 2025. https://www.research.google/blog/urban-mobility-solutions-calibrating-digital-twins-at-scale/ · https://arxiv.org/abs/2501.04783
[^stadium]: Google Research blog, Dec 19, 2023. https://research.google/blog/simulations-illuminate-the-path-to-post-event-traffic-flow/
[^collab]: Google Research blog, Jul 7, 2026 (*Nature Cities*). https://research.google/blog/the-power-of-collaboration-how-we-can-reduce-traffic-congestion/
[^mobilityai]: Google Research blog, Apr 23, 2025 (updated Jan 15, 2026). https://research.google/blog/introducing-mobility-ai-advancing-urban-transportation/
[^surtrackrs]: USDOT ITS Knowledge Resources. https://www.itskrs.its.dot.gov/SRC-2012-170fe7b4ac9457d985257aef0065058d · CMU report https://www.ri.cmu.edu/pub_files/2013/1/13-0315.pdf
[^miovision]: Miovision, Oct 2022. https://miovision.com/press-release/miovision-acquires-rapid-flow/
[^notraffic]: KTAR, Aug 24, 2020. https://ktar.com/arizona-news/phoenix-installs-notraffic-light-technology-to-improve-traffic-flow · NoTraffic case study https://www.notraffic.com/?p=1668
[^lyt]: LYT, Jun 12, 2023. https://lyt.ai/blog/lyts-transit-signal-prioritization-technology-reduced-red-light-wait-time-by-50-along-new-san-jose-routes-66-expands-transit-prioritization-to-include-rapid
[^econoliteptv]: Business Wire, Apr 23, 2024. https://www.businesswire.com/news/home/20240423286252/en/Econolite-and-PTV-Group-Introduce-Revolutionary-Cloud-Based-ATMS-Integration-with-Predictive-Traffic-Monitoring-and-Alerting-Capability
[^yunex]: Intertraffic, Dec 2018. https://intertraffic.com/news/big-data/ai-traffic-signal-system-reduces-waiting-time
[^citybrain]: China Daily, Jun 12, 2020. https://regional.chinadaily.com.cn/en/2020-06/12/c_500016.htm
[^asct]: FHWA EDC-1. https://www.fhwa.dot.gov/innovation/everydaycounts/edc-1/asct.cfm
[^intellilight]: Wei et al., KDD 2018. https://faculty.ist.psu.edu/jessieli/Publications/2018-KDD-IntelliLight.pdf
[^presslight]: Wei et al., KDD 2019. https://jhc.sjtu.edu.cn/~gjzheng/paper/kdd2019_presslight/kdd2019_presslight_paper.pdf
[^colight]: Wei et al., CIKM 2019. https://arxiv.org/abs/1905.05717
[^mplight]: Chen et al., AAAI 2020. https://ojs.aaai.org/index.php/AAAI/article/view/5744
[^cityflow]: Zhang et al., WWW 2019. https://arxiv.org/abs/1905.05217
[^libsignal]: Mei et al. https://arxiv.org/abs/2211.10649
[^maxpressure]: Mercader, Uwayid & Haddad, TR-C 2020. https://cris.iucc.ac.il/en/publications/max-pressure-traffic-controller-based-on-travel-times-an-experime/
[^umn]: University of Minnesota CTS, Mar 10, 2025. https://www.cts.umn.edu/news-pubs/news/2025/march/signals
[^review]: *Intelligent Transportation Infrastructure*, May 2024. https://academic.oup.com/iti/article/8125227
[^sim2signal]: arXiv 2609.01676 (Sep 2026). https://arxiv.org/abs/2609.01676
[^fraunhofer]: Fraunhofer, Feb 1, 2022. https://www.fraunhofer.de/en/press/research-news/2022/february-2022/traffic-lights-controlled-using-artificial-intelligence.html
[^llmlight]: Lai et al., LLMLight. https://arxiv.org/abs/2312.16044
[^itsjpo]: ITS JPO AI use cases. https://its-dr.fhwa.dot.gov/research-areas/artificial-intelligence/overview/ai-use-cases/ · Capability Maturity Model (FHWA-JPO-24-136). https://rosap.ntl.bts.gov/view/dot/78879/dot_78879_DS1.pdf
[^usdotai]: American Infrastructure, Jul 2026. https://www.americaninfrastructuremag.com/usdot-launches-ai-initiative-to-modernize-nationwide-transportation/
[^v2x]: Covington summary of USDOT National V2X Deployment Plan (Aug 2024). https://www.covingtonblogs.com/2024/08/30/usdot-releases-plan-to-accelerate-v2x-deployment/
[^cve]: TechCrunch, Jul 18, 2024. https://techcrunch.com/2024/07/18/hackers-could-create-traffic-jams-thanks-to-flaw-in-traffic-light-controller-researcher-says
