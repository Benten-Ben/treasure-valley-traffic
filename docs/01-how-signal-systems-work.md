# 1. How traffic signal systems work

A primer on the hardware, the timing logic, and the operating practices behind
a signalized road network. You need this vocabulary to read agency documents,
ask useful questions, and tell which complaints timing can fix and which it
can't.

> This chapter covers general US traffic engineering practice. Treasure
> Valley specifics are in [02 — The Treasure Valley signal system](02-treasure-valley-signal-system.md).

---

## 1.1 The physical system

| Component | What it is | Why it matters for "bad timing" |
|---|---|---|
| **Signal heads** | The lights themselves, including flashing yellow arrow (FYA) left-turn heads | FYA allows permissive lefts during gaps, which cuts left-turn waits when used well |
| **Cabinet** | The roadside box holding the electronics | Older cabinets limit which features can be used |
| **Controller** | The computer that runs the timing logic. Standards include NEMA TS-1/TS-2, the Caltrans 2070, and ATC (Advanced Transportation Controller) | Holds the timing plans; modern ones log high-resolution event data |
| **Conflict monitor / MMU** | An independent safety device that puts the intersection into flash if it ever sees conflicting greens | Safety is enforced in hardware, separate from timing. Even badly tuned timing can't show conflicting greens |
| **Detection** | Sensors that tell the controller a vehicle or pedestrian is waiting or approaching: inductive loops cut into pavement, video, radar, thermal cameras, pedestrian push buttons | **Broken detection is one of the most common causes of lights that "make no sense."** A failed detector usually falls back to placing a constant call, so that approach gets green every cycle even when it's empty |
| **Communications** | Fiber, copper, wireless, or cellular links from the cabinet to a central system | Without communications, an agency can't see, monitor, or remotely fix a signal; someone has to drive out to it |
| **Central management system (ATMS)** | Software that stores and pushes timing, monitors alarms, and shows status (e.g., Econolite Centracs, Cubic/Trafficware ATMS, Siemens/Yunex, Q-Free Kinetic, McCain Transparity) | Lets a small staff manage hundreds of signals |
| **Traffic Management Center (TMC)** | The room where operators watch cameras and the central system, respond to incidents, and adjust timing | Where real-time intervention happens |

## 1.2 Phases, rings, and barriers

Most US signals use the **NEMA dual-ring, eight-phase** structure:

```
        Ring 1:  | ø1 (L) | ø2 (Thru) || ø3 (L) | ø4 (Thru) |
        Ring 2:  | ø5 (L) | ø6 (Thru) || ø7 (L) | ø8 (Thru) |
                 <---- Main street ----><---- Side street ---->
                                      barrier
```

- **Even phases** are usually through movements: 2 and 6 for the main street,
  4 and 8 for the side street.
- **Odd phases** are the protected left turns that pair with them.
- The **barrier** separates main-street movements from side-street movements.
  Both rings have to cross it together, which is why a single long side-street
  movement can hold up everything.
- **Lead/lag** left turns, **protected-only** vs **protected-permissive**
  lefts, and **phase omits** by time of day are all timing decisions.

Each extra phase adds roughly 3–5 seconds of **lost time** per cycle, from
start-up delay and yellow/red clearance. Big suburban intersections where two
6-lane arterials meet with dual protected lefts on every approach spend a lot
of every cycle on clearance and serve each movement only once per cycle.

## 1.3 Timing parameters (what a "timing sheet" contains)

| Parameter | Meaning |
|---|---|
| **Minimum green** | Shortest green a phase can get once served |
| **Passage / gap / extension time** | How long the green holds after the last detected vehicle. Too long and the green stays on for stragglers; too short and the green cuts off a platoon |
| **Maximum green** | Cap on how long a phase can extend when other phases are waiting |
| **Yellow change** | Set by approach speed. The common ITE formula is `Y = t + v / (2a + 2Gg)` (perception time, speed, deceleration, grade) |
| **Red clearance (all-red)** | Time for vehicles already in the intersection to clear |
| **Walk / Flashing Don't Walk** | Pedestrian timing. MUTCD clearance is based on a 3.5 ft/s walking speed, so a 100-ft crossing needs about 29 s of flashing Don't Walk plus the Walk interval |
| **Recall** | Forces a phase to be served even without a detected call. Often used on the main street, or as a fallback for failed detectors |
| **Cycle length** | Time for one full rotation of all phases (in coordinated operation) |
| **Splits** | How the cycle is divided among phases |
| **Offset** | When each signal's cycle starts relative to a master clock. This creates "green waves" |
| **Time-of-day (TOD) schedule** | Which timing plan (cycle/split/offset set) runs when, e.g., AM peak, midday, PM peak, evening, weekend, overnight free or flash |

## 1.4 Modes of operation

1. **Pre-timed (fixed-time).** Same sequence and durations every cycle. Mostly
   used in dense downtown grids.
2. **Fully actuated (isolated).** Each phase responds to detection and the
   signal isn't coordinated with its neighbors. Common at isolated
   intersections and overnight.
3. **Actuated-coordinated.** The most common arterial mode in US suburbs. A
   fixed cycle length keeps signals in sync, the coordinated main-street
   phases get the slack, and side-street and left-turn phases are actuated
   within their splits.
4. **Traffic-responsive plan selection.** The system switches among stored
   plans based on detector volumes instead of by clock.
5. **Adaptive signal control technology (ASCT).** Software continuously
   adjusts splits, offsets, and/or cycle lengths based on measured demand.
   Examples include SCATS, SCOOT, InSync, SynchroGreen, Surtrac, ACS Lite,
   KADENCE, and Centracs Adaptive. Results vary widely and depend heavily on
   detection quality and maintenance (see [04](04-improvement-playbook.md)).

## 1.5 Coordination and the trade-offs it forces

Coordination lines up offsets so platoons of cars released by one signal
arrive at the next one on green. Engineers design it with **time-space
diagrams**. Some unavoidable trade-offs:

- **Main street vs. side street.** Progression on the arterial is "paid for"
  by side streets and left turns, which wait for their slot in a long common
  cycle. Many "this light is terrible" complaints come from a side-street
  driver who is waiting by design.
- **Two-directional progression depends on geometry.** Good two-way green
  waves need signal spacing that fits the cycle length and travel speed.
  Uneven spacing, which is typical where commercial driveways got signals,
  makes perfect two-way progression mathematically impossible, so engineers
  favor the peak direction.
- **Cycle length.** Longer cycles waste less time on clearances and so move
  more vehicles per hour, but they make every waiting driver wait longer and
  build longer queues. Agencies often run long peak cycles (120–180 s) on
  busy suburban arterials.
- **Pedestrians.** A pedestrian call on a wide arterial can require a 40–50 s
  side-street phase. If that's longer than the vehicle split, the
  coordination can be knocked out of step for a cycle or more.
- **Preemption and priority.** Emergency vehicle preemption, railroad
  preemption, and transit signal priority interrupt the normal cycle. After a
  preemption, a signal can take several cycles of **transition** to get back
  in step with its neighbors, and drivers notice this as "random" timing.
- **Jurisdictional seams.** Where one agency's signals meet another's (for
  example, a state highway crossing a county arterial), cycle lengths and
  clocks may not match, and progression breaks.

## 1.6 What timing can and can't fix

This framing matters most when deciding where to put effort:

- **Below capacity**, good timing pays off a lot. Typical retiming projects
  report delay and stop reductions in the 10–25% range, and better on
  corridors with very stale plans. See [04](04-improvement-playbook.md) for
  sourced figures.
- **At or above capacity**, where demand exceeds what the intersection can
  physically serve, timing can only **allocate** delay among movements. It
  can't remove it. A signalized through lane serves roughly 1,800–1,900
  vehicles per hour of green (the HCM base saturation flow is
  1,900 pc/h/ln). If that lane gets green 40% of the cycle, it moves about
  750 veh/h. When demand grows past that, queues grow no matter how clever
  the timing is.
- In a fast-growing region, much of the peak-hour pain at the busiest
  arterial intersections is likely a **capacity and network** problem (land
  use, missing parallel routes, few alternatives to driving). Off-peak and
  shoulder-hour waits, poor progression, failed detectors, and stale plans
  are timing problems. Separating the two is the first analytical step.

## 1.7 How performance is measured

| Measure | What it tells you |
|---|---|
| **Control delay (s/veh)** and **HCM Level of Service** | LOS A ≤10 s, B ≤20, C ≤35, D ≤55, E ≤80, F >80 s/veh of delay at a signal |
| **Volume-to-capacity (v/c)** | Whether a movement is undersaturated (<1.0) or oversaturated |
| **Travel time / travel time reliability** | Corridor-level user experience, often from probe data |
| **Arrivals on green (AOG) / Purdue Coordination Diagram** | How well progression works, from high-resolution controller data |
| **Split failures** | Cycles where a queue didn't fully clear; a direct sign of under-served movements |
| **Number of stops** | Driver experience; fuel use and emissions |
| **Pedestrian delay** | Wait time between pushing the button and getting Walk |
| **Detector health** | Share of detectors reporting plausibly; a leading indicator of bad timing |

## 1.8 Who does what inside an agency

- **Traffic engineers** design timing plans (often in Synchro/Vistro), set
  objectives, and sign off on changes.
- **Signal technicians** maintain cabinets, controllers, and detection, and
  respond to malfunctions and knock-downs.
- **TMC operators** watch cameras and system alarms, respond to incidents,
  implement special-event plans, and pass complaints along.
- **Consultants** often do large corridor retiming projects: counts,
  modeling, implementation, and fine-tuning.
- **Elected boards** (for a highway district, its commissioners) set budgets
  and priorities. For outsiders, they're the lever on funding and staffing.

---

**Next:** [02 — The Treasure Valley signal system](02-treasure-valley-signal-system.md)
