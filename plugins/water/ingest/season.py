"""The canal season: whether each canal has water (on, off or unknown), as lifecycles in evt.event (plan P5, data
side; the owner's decision 18, Oct 8, 2026). The app reads them and draws each canal filled (on), hollow (off) or
neither (unknown) through feature-state on the baked reaches: wave 2, P5-app.

    python3 -m ingest canal-season [--dry-run [--as-of TIME]] [--canal NAME ...]

Each canal of the water build (water.canal) gets one rule set for core's rules-by-date evaluator
(ingest/seasons.py), and its timeline from Jan 1, 2026 to the end of next year becomes its lifecycles. Strongest
first:

1. **Its gauge.** The New York Canal follows BSEI1, "New York Canal Diversion at Boise", from the NWPS readings the
   nwps_gauges poller keeps in raw.record (stage in ft, flow in kcfs). A reading with a flow of 10 cfs or more is
   on; any lower flow is off. Without a flow (BSEI1 reports none once the canal is off), a stage of 7.3 ft or more
   is on and one of 3.7 ft or less (plus 0.2 ft, as the empty canal's level drifts) is off; in between, the canal
   is filling or draining and the state before holds. The thresholds are the two levels seen at the head, 7.35 ft at
   about 1,670 cfs until Sep 28, 2026, and 3.69-3.73 ft since its shut-off that morning ⚠️ (one season's
   shut-off). **48 hours without a reading, the state is "unknown"**, not on or off, until readings come back:
   between two readings more than 48 hours apart, and from 48 hours after the last one. The gauge's claim starts
   at its first on or off reading; before it, the rules below apply. BSEI1's NWPS record names no USGS site
   (`usgsId` is empty) and no data attribution (checked Oct 11 in what nwps_gauges collected), so its credit is
   NWPS's alone.
2. **The district's dates**: plugins/water/ingest/canal_dates.json, loaded by canal-dates-load into
   water.canal_date (sources/canal_dates.py). Within an entry's year: off before its `on`, on from `on` to `off`
   (to the end of the canal's legal season while no `off` is announced, else the year's; a span that ends on IDWR's
   date says so, credits IDWR and is internal, as the window is), off from `off`. A later entry wins over an earlier
   one; the gauge wins over both, its "unknown" included. A name selects every canal of that name in the valley,
   unless the entry's head_in (IDWR service areas at the head) or canal_ids narrow it; canal-dates-load lists the
   names that select several.
3. **IDWR's legal season of use** at the canal's head (water.canal_season, built by water-build from IDWR's zones):
   on within it, off outside it, labelled as the legal window, not delivery dates. Internal (IDWR states no
   licence): those lifecycles say republish "internal".
4. Nothing: no lifecycle, which the app reads as unknown.

Drains, and canals named for a creek, river, slough or gulch (Fivemile Creek, Mason Creek, Purdam Gulch) without a
canal word (Mason Creek Feeder and Dry Creek Canal are canals), never switch off (the design): one lifecycle each,
on, basis "always". Reaches with no canal (unnamed laterals and ditches) get none.

**Where it runs.** As a source, `canal_season`, every hour inside `ingest serve`, after nwps_gauges, and by hand
(this command; canal-dates-load runs it after a load). It fetches nothing and builds nothing: it turns readings and
dates into lifecycles, as nwps_gauges turns its readings into flood episodes, and the 48-hour rule needs a clock,
or a gauge that falls silent would leave its canal "on". Each statement is limited to 30 s; a run reads one gauge's
readings, about 560 canals and a few dozen dates, and writes only when a lifecycle changed (a few times a season,
a new water build, a new dates file, the new year).

**Lifecycles** (evt.event, source and kind 'canal_season'): one row per canal and span, source_id
'<canal id>@<start, UTC ISO>', declared [start, end) with end null for the gauge's current span (it holds until a
reading changes it or 48 hours pass without one) and for 'always'; severity the state; geom the canal's head;
description the card's words; attributes {canal_id, canal, canal_kind, state, basis ('gauge', 'district',
'legal', 'always'), why, credit [...], republish, and by basis: gauge, gauge_name; entry, district, words, source,
read, off_announced (and end_from 'legal', season, objectid when IDWR's window ends it); season, objectid}. Every
row credits the network (OpenStreetMap, NHD) and HydroShare's canal network (CC BY 4.0, with its DOI) when the
canal's sources include it (131 canals of build 10 have their names from it alone). A row that leaves the derivation (a new build
renumbers a canal, readings fill a gap) turns inactive: the app reads active rows.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple, Optional

from ingest import db, events, manifest, seasons

from . import rules
from .common import iso, parse_time
from .sources import canal_dates, hydroshare_canals

SOURCE = {
    "name": "canal_season",
    "title": "Canal water season: on, off or unknown per canal, from the New York Canal's gauge, the districts' "
             "dates and IDWR's legal season",
    "url": "https://github.com/Benten-Ben/treasure-valley-traffic/blob/main/plugins/water/ingest/season.py",
    "access": "open",
    "schedule": "1 hour",   # fetches nothing: readings and dates to lifecycles (the 48-hour rule needs a clock)
    "license": "derived: NWPS readings (public domain), the water network (ODbL), the HydroShare canal network's "
               "names (CC BY 4.0), the districts' dates (cited), IDWR's season of use (none stated)",
    "credit": "NOAA National Weather Service (NWPS); the irrigation districts, as cited; Idaho Department of Water "
              "Resources (Season of Use); © OpenStreetMap contributors; USGS National Hydrography Dataset; "
              + hydroshare_canals.SOURCE["credit"],
    "notes": "Derived, fetches nothing: each canal's water season as evt.event lifecycles (kind canal_season), from "
             "gauge BSEI1's stage and flow (unknown after 48 h without a reading), canal_dates.json, and IDWR's "
             "legal season (internal rows). Writes only when a lifecycle changed.",
}
KIND = "canal_season"
SINCE = date(2026, 1, 1)          # the first lifecycles: the year the readings start (BSEI1's on Sep 7, 2026)
STALE = timedelta(hours=48)       # without a reading this long, the gauge's canal is "unknown"
STATEMENT_TIMEOUT_S = 30          # inside `ingest serve`: no statement may hold up the sources after it

NETWORK_CREDIT = ["© OpenStreetMap contributors", "USGS National Hydrography Dataset"]
HYDROSHARE_CREDIT = hydroshare_canals.SOURCE["credit"]    # CC BY 4.0, with its DOI: on every canal it named or typed
IDWR_CREDIT = "Idaho Department of Water Resources (Season of Use)"
NWPS_CREDIT = "NOAA National Weather Service (NWPS)"

# A canal-class line that never switches off: a drain, or one named for a natural stream without a canal word.
_STREAM_NAME = re.compile(r"\b(creek|river|slough|gulch|wash|springs?|hollow)\b", re.IGNORECASE)
_CANAL_WORD = re.compile(r"\b(canal|lateral|ditch|feeder)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Gauge:
    """A canal gauge and its thresholds: on at flow_on_cfs or more, or (without a flow) a stage of stage_on_ft or
    more; off below flow_on_cfs, or (without a flow) a stage of stage_off_ft + slack_ft or less."""
    lid: str
    name: str
    stage_on_ft: float
    stage_off_ft: float
    slack_ft: float
    flow_on_cfs: float


# The plan's figures (7.3 ft on, 3.7 ft off), from BSEI1's levels before and after its Sep 28, 2026 shut-off ⚠️.
GAUGES = {"BSEI1": Gauge("BSEI1", "New York Canal Diversion at Boise", stage_on_ft=7.3, stage_off_ft=3.7,
                         slack_ft=0.2, flow_on_cfs=10.0)}


class Reading(NamedTuple):
    t: datetime                   # UTC
    stage_ft: Optional[float]
    flow_cfs: Optional[float]


class GaugeSpan(NamedTuple):
    start: datetime
    end: Optional[datetime]       # None: it holds until a reading changes it
    state: str                    # 'on', 'off' or 'unknown'
    why: str


class Canal(NamedTuple):
    id: int
    name: str
    kind: str
    gauge_lid: Optional[str]
    source_canal_id: Optional[int]
    head: Optional[dict]          # GeoJSON point: the head reach's start
    length_m: float = 0.0
    sources: tuple = ()           # water.canal.sources: 'osm_waterways', 'nhd_hr', 'hydroshare_canals'
    head_in: tuple = ()           # INTERNAL (IDWR): the service areas its head lies in (water.canal_org.at_head)


# ---- the gauge -------------------------------------------------------------------------------------------------

def _number(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def reading(payload):
    """A Reading from an nwps_gauges observation ({lid, pe, t, primary, secondary, units}), or None. A value in ft
    is a stage (unless its PEDTS code says a pool elevation), one in kcfs or cfs a flow."""
    t = parse_time((payload or {}).get("t"))
    if t is None:
        return None
    pe = str(payload.get("pe") or "").upper()
    units = list(payload.get("units") or []) + [None, None]
    stage = flow = None
    for v, unit in ((payload.get("primary"), units[0]), (payload.get("secondary"), units[1])):
        v, unit = _number(v), str(unit or "").lower()
        if v is None:
            continue
        if unit == "ft" and not pe.startswith("HP"):
            stage = v
        elif unit == "kcfs":
            flow = v * 1000.0
        elif unit == "cfs":
            flow = v
    if stage is None and flow is None:
        return None
    return Reading(t, stage, flow)


def classify(gauge, r):
    """'on', 'off', or None (filling or draining, or nothing to go on: the state before holds)."""
    if r.flow_cfs is not None:
        return "on" if r.flow_cfs >= gauge.flow_on_cfs else "off"
    if r.stage_ft is None:
        return None
    if r.stage_ft >= gauge.stage_on_ft:
        return "on"
    if r.stage_ft <= gauge.stage_off_ft + gauge.slack_ft:
        return "off"
    return None


def describe(r):
    """The reading that started a span, in words."""
    parts = []
    if r.flow_cfs is not None:
        parts.append(f"flow {r.flow_cfs:,.0f} cfs")
    if r.stage_ft is not None:
        parts.append(f"stage {r.stage_ft:.2f} ft")
    if r.flow_cfs is None:
        parts.append("no flow reported")
    return ", ".join(parts)


def _silent(stale):
    return f"no reading for {stale.total_seconds() / 3600:g} hours"


def gauge_spans(gauge, readings, now, stale=STALE):
    """The gauge's spans as of `now`, from its readings (any order; those after `now` are left out): on and off from
    its first on or off reading, "unknown" between readings more than `stale` apart (from `stale` after the earlier)
    and from `stale` after the last reading when that's before `now`. The last span's end is None. Readings between
    the thresholds keep the state before (or "unknown" after a silence)."""
    out, cur, last = [], None, None          # cur: [state, start, why]
    for r in sorted(readings, key=lambda r: r.t):
        if r.t > now:
            break
        if cur is not None and r.t - last > stale and cur[0] != "unknown":
            out.append(GaugeSpan(cur[1], last + stale, cur[0], cur[2]))
            cur = ["unknown", last + stale, _silent(stale)]
        state = classify(gauge, r)
        if cur is None:
            if state is None:
                continue                     # no claim before the first on or off reading
            cur = [state, r.t, describe(r)]
        elif state is not None and state != cur[0]:
            out.append(GaugeSpan(cur[1], r.t, cur[0], cur[2]))
            cur = [state, r.t, describe(r)]
        last = r.t
    if cur is None:
        return []
    if cur[0] != "unknown" and now - last >= stale:
        out.append(GaugeSpan(cur[1], last + stale, cur[0], cur[2]))
        cur = ["unknown", last + stale, _silent(stale)]
    out.append(GaugeSpan(cur[1], None, cur[0], cur[2]))
    return out


def gauge_readings(conn, lid):
    """A gauge's readings from raw.record (the newest version of each observation)."""
    out = []
    for (payload,) in conn.execute(
            """select distinct on (source_id) payload from raw.record
               where source = 'nwps_gauges' and source_id like %s
               order by source_id, first_seen desc""", (f"{lid}@%",)).fetchall():
        r = reading(payload)
        if r is not None:
            out.append(r)
    return out


# ---- rules -----------------------------------------------------------------------------------------------------

def seasonal(kind, name):
    """Whether a canal switches off: not a drain, nor named for a natural stream without a canal word."""
    if kind == "drain":
        return False
    return not (name and _STREAM_NAME.search(name) and not _CANAL_WORD.search(name))


def _midnight(day):
    return seasons.moment(day)


def legal_window(row):
    """((start month, day), (end month, day), season text, objectid) from a water.canal_season row, or None."""
    if row is None:
        return None
    objectid, season, sm, sd, em, ed = row
    if None in (sm, sd, em, ed):
        return None
    return (sm, sd), (em, ed), season or f"{sm}/{sd} - {em}/{ed}", objectid


def legal_end(legal, year):
    """The moment the legal season ends in a year (the midnight after its last day), or None."""
    if legal is None:
        return None
    (sm, sd), (em, ed), _, _ = legal
    if (em, ed) < (sm, sd):                    # a window across New Year: no end inside one season's year
        return None
    if (em, ed) == (2, 29) and not (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        return _midnight(date(year, 3, 1))     # as the evaluator reads it: no Feb 29 that year
    return _midnight(date(year, em, ed) + timedelta(days=1))


def legal_rules(legal):
    if legal is None:
        return []
    (sm, sd), (em, ed), text, objectid = legal
    base = {"basis": "legal", "season": text, "objectid": objectid}
    return [
        seasons.rule({"level": "default", "value": {"state": "off", **base}, "id": f"idwr-season-{objectid}",
                      "text": f"outside IDWR's season of use {text}", "source": IDWR_CREDIT}),
        seasons.rule({"level": "seasonal", "value": {"state": "on", **base},
                      "yearly": {"start": f"{sm:02d}-{sd:02d}", "end": f"{em:02d}-{ed:02d}"},
                      "id": f"idwr-season-{objectid}", "text": f"IDWR's season of use {text}",
                      "source": IDWR_CREDIT})]


def district_rules(entry, legal):
    """An entry's rules on one canal. Its legal window bounds an 'on' with no 'off' yet: that span's value carries
    'until_legal' (the window's text and objectid), and a row whose end is that bound says so (row())."""
    y0, y1 = _midnight(date(entry.season, 1, 1)), _midnight(date(entry.season + 1, 1, 1))
    base = {"basis": "district", "entry": entry.id, "district": entry.district, "words": entry.words,
            "source": entry.source, "read": entry.read_on.isoformat(), "republish": entry.republish}
    meta = {"id": entry.id, "text": entry.words, "source": entry.source}
    out = []

    def add(state, start, end, **extra):
        if start < end:
            out.append(seasons.rule({"level": "order", "value": {"state": state, **base, **extra},
                                     "dates": {"start": start, "end": end}, **meta}))

    if entry.on_at is not None:
        end, extra = entry.off_at, {}
        if end is None:
            end = legal_end(legal, entry.season)
            if end is not None and end > entry.on_at:
                extra = {"until_legal": {"season": legal[2], "objectid": legal[3]}}
            else:
                end = y1
        add("off", y0, entry.on_at)
        add("on", entry.on_at, end, off_announced=entry.off_at is not None, **extra)
    if entry.off_at is not None:
        add("off", entry.off_at, y1)
    return out


def gauge_rules(gauge, spans):
    out = []
    for s in spans:
        dates = {"start": s.start} if s.end is None else {"start": s.start, "end": s.end}
        out.append(seasons.rule({"level": "order", "dates": dates, "id": f"gauge-{gauge.lid}",
                                 "source": f"gauge {gauge.lid}", "text": s.why,
                                 "value": {"state": s.state, "basis": "gauge", "gauge": gauge.lid,
                                           "gauge_name": gauge.name, "why": s.why}}))
    return out


def canal_rules(legal, entries, gauge=None, spans=()):
    """One canal's rules, weakest first: IDWR's legal season (a default off and a seasonal on), the district entries
    that select it in the file's order (a later one wins), then its gauge's spans (which win over all)."""
    out = legal_rules(legal)
    for e in entries:
        out += district_rules(e, legal)
    if gauge is not None:
        out += gauge_rules(gauge, spans)
    return out


def _open(rule):
    """A rule that runs on with no end of its own (the gauge's current span)."""
    return rule.start is not None and rule.end is None and not rule.recurs


def spans(rule_list, since, until):
    """The canal's timeline as [(start, end or None, value, rule)], leaving out stretches no rule covers. A span
    that reaches `until` under an open-ended rule stays open (end None)."""
    out = []
    for s in seasons.timeline(rule_list, since, until):
        if s.rule is None:
            continue
        out.append((s.start, None if s.end == until and _open(s.rule) else s.end, s.value, s.rule))
    return out


# ---- rows ------------------------------------------------------------------------------------------------------

def _why(value, rule):
    if value["basis"] == "gauge":
        return value["why"]
    if value["basis"] == "legal":
        return rule.text
    if value["basis"] == "district":
        if value.get("end_from") == "legal":
            return (f"{value['district']}: water on; its shut-off isn't announced yet, so the span ends with IDWR's "
                    f"legal season ({value['season']})")
        if value["state"] == "on" and not value.get("off_announced", True):
            return f"{value['district']}: water on; its shut-off isn't announced yet"
        return f"{value['district']}'s dates"
    return value.get("why") or ""


def description(canal, value, rule):
    name, state, basis = canal.name, value["state"], value["basis"]
    if basis == "gauge":
        if state == "unknown":
            return f"{name}: unknown (gauge {value['gauge']}: {_silent(STALE)})"
        return f"{name}: {'water on' if state == 'on' else 'off'} (gauge {value['gauge']}, {value['gauge_name']})"
    if basis == "district":
        if value.get("end_from") == "legal":
            return f"{name}: water on ({value['district']}'s dates; no shut-off announced: until the legal season ends)"
        return f"{name}: {'water on' if state == 'on' else 'off'} ({value['district']}'s dates)"
    if basis == "legal":
        where = "in" if state == "on" else "outside"
        return f"{name}: {where} IDWR's legal irrigation season ({value['season']}), not delivery dates"
    return f"{name}: water all year ({value['why']})"


def strictest(*classes):
    """The strictest of republish classes (manifest.REPUBLISH runs from the loosest to the strictest)."""
    return max(classes, key=manifest.REPUBLISH.index)


def network_credit(canal):
    """The canal's own credits: the network's, and HydroShare's (CC BY 4.0) when it named, typed or matched the
    canal (water.canal.sources): its name shows on every row."""
    return [*NETWORK_CREDIT, *([HYDROSHARE_CREDIT] if "hydroshare_canals" in (canal.sources or ()) else [])]


def credit_and_republish(canal, value):
    basis, network = value["basis"], network_credit(canal)
    if basis == "gauge":
        return [f"{NWPS_CREDIT}, gauge {value['gauge']}", *network], "yes"
    if basis == "district":
        credit, republish = [f"{value['district']} ({value['source']})"], value.get("republish", "yes")
        if value.get("end_from") == "legal":         # its end is IDWR's date: internal, as IDWR's window is
            credit.append(IDWR_CREDIT)
            republish = strictest(republish, "internal")
        return [*credit, *network], republish
    if basis == "legal":
        return [IDWR_CREDIT, *network], "internal"
    return network, "yes"


def row(canal, start, end, value, rule):
    """One evt.event row (as events.upsert takes it). A district span whose end is its legal window's (no shut-off
    announced) says so: end_from 'legal', the window's season and objectid, IDWR's credit, republish internal. One cut
    short by a stronger or later rule ends there instead, and doesn't."""
    value = dict(value)
    until = value.pop("until_legal", None)
    if until is not None and rule is not None and end is not None and end == rule.end:
        value.update({"end_from": "legal", "season": until["season"], "objectid": until["objectid"]})
    credit, republish = credit_and_republish(canal, value)
    attributes = {"canal_id": canal.id, "canal": canal.name, "canal_kind": canal.kind,
                  **{k: v for k, v in value.items() if k not in ("why",)},
                  "why": _why(value, rule), "credit": credit, "republish": republish}
    return {"source_id": f"{canal.id}@{iso(start)}", "kind": KIND, "geom": canal.head, "start": start, "end": end,
            "severity": value["state"], "description": description(canal, value, rule), "attributes": attributes}


def always_row(canal, since):
    why = "a drain" if canal.kind == "drain" else "named for a natural stream"
    value = {"state": "on", "basis": "always", "why": f"{why}; drains and creeks never switch off"}
    return row(canal, since, None, value, None)


# ---- reading the database --------------------------------------------------------------------------------------

def ready(conn):
    """Whether water 0001 and 0002 are applied."""
    return conn.execute("select to_regclass('water.canal') is not null and to_regclass('water.canal_date') is not null"
                        ).fetchone()[0]


def canals(conn):
    return [Canal(i, name, kind, lid, src, json.loads(head) if head else None, length, tuple(sources or ()),
                  tuple(head_in or ()))
            for i, name, kind, lid, src, head, length, sources, head_in in conn.execute(
                """select c.id, c.name, c.kind, c.gauge_lid, c.source_canal_id, ST_AsGeoJSON(ST_StartPoint(r.geom), 6),
                          c.length_m, c.sources,
                          array(select o.name from water.canal_org o where o.canal_id = c.id and o.at_head
                                order by o.name)
                   from water.canal c left join water.reach r on r.id = c.head_reach_id
                   order by c.id""").fetchall()]


def legal_windows(conn):
    return {r[0]: legal_window(r[1:]) for r in conn.execute(
        "select canal_id, objectid, season, start_month, start_day, end_month, end_day from water.canal_season"
    ).fetchall()}


class Note(NamedTuple):
    """What a dates entry's name selects, when it's worth a look: 'none' (no canal of the build, or none within the
    entry's scope), 'several' (canals far apart can share a name), or 'unused id' (a canal_ids id none of its names
    selects). canals: the Canals the name selects (for 'several'), or the id's (for 'unused id'); named: how many
    canals carry the name before the entry's head_in and canal_ids narrow it."""
    entry: str
    name: str
    what: str
    canals: tuple = ()
    named: int = 0


def _scope(entry, found):
    """The named canals an entry keeps: those with their head in a head_in service area (water.canal_org), and of
    those, the canal_ids ones, when the entry gives either."""
    if entry.head_in:
        keys = {rules.name_key(n) for n in entry.head_in}
        found = [c for c in found if keys & {rules.name_key(n) for n in c.head_in}]
    if entry.canal_ids:
        found = [c for c in found if c.id in entry.canal_ids]
    return found


def selections(entries, all_canals):
    """{canal id: [entries selecting it, in the file's order]} over the seasonal canals, and the Notes: names that
    select no canal or several, and canal_ids none of an entry's names selects. A name selects every canal of that
    name (matched without case or punctuation) in the valley, narrowed by the entry's head_in and canal_ids;
    'branches' adds the canals fed from those, and those fed from them."""
    by_key, children = defaultdict(list), defaultdict(list)
    for c in all_canals:
        by_key[rules.name_key(c.name)].append(c)
        if c.source_canal_id is not None:
            children[c.source_canal_id].append(c)
    out, notes, by_id = defaultdict(list), [], {c.id: c for c in all_canals}
    for e in sorted(entries, key=lambda e: e.position):
        chosen, named = {}, set()
        for name in e.canals:
            everywhere = by_key.get(rules.name_key(name), [])
            found = _scope(e, everywhere)
            named.update(c.id for c in found)
            if not found:
                notes.append(Note(e.id, name, "none", named=len(everywhere)))
            elif len(found) > 1:
                notes.append(Note(e.id, name, "several", tuple(sorted(found, key=lambda c: -c.length_m)),
                                  len(everywhere)))
            todo = list(found)
            while todo:
                c = todo.pop()
                if c.id in chosen:
                    continue
                chosen[c.id] = c
                if e.branches:
                    todo += children.get(c.id, [])
        for i in e.canal_ids or ():
            if i not in named:
                notes.append(Note(e.id, f"canal id {i}", "unused id", (by_id[i],) if i in by_id else ()))
        for c in chosen.values():
            if seasonal(c.kind, c.name):
                out[c.id].append(e)
    return out, notes


def _where(c):
    return f"head in {', '.join(c.head_in)}" if c.head_in else "head in no service area"


def note_text(note):
    """A Note in words, for canal-dates-load and its dry run."""
    if note.what == "none":
        if note.named:
            return (f"entry {note.entry}: {note.name!r} names {note.named} canal(s) of the current water build, none "
                    f"within the entry's head_in and canal_ids")
        return f"entry {note.entry}: no canal named {note.name!r} in the current water build"
    if note.what == "several":
        listed = "; ".join(f"{c.id} ({c.length_m / 1000:.1f} km, {_where(c)})" for c in note.canals)
        return (f"entry {note.entry}: {note.name!r} selects {len(note.canals)} canals of that name: {listed}. "
                f"If that isn't meant, narrow it with head_in or canal_ids")
    if note.canals:
        c = note.canals[0]
        return f"entry {note.entry}: {note.name} is {c.name!r}, which none of its names selects"
    return f"entry {note.entry}: {note.name} isn't a canal of the current water build"


def check(conn, entries):
    """canal-dates-load's report on entries against the current build: ({entry id: canals it selects}, [Notes])."""
    chosen, notes = selections(entries, canals(conn))
    counts = defaultdict(int)
    for picked in chosen.values():
        for e in picked:
            counts[e.id] += 1
    return dict(counts), notes


# ---- deriving and storing --------------------------------------------------------------------------------------

def window(now):
    """[since, until): Jan 1, 2026 to the end of next year, Boise time."""
    year = now.astimezone(seasons.TZ).year
    return _midnight(SINCE), _midnight(date(year + 2, 1, 1))


def derive(conn, now):
    """Every canal's lifecycles as of `now`: (rows, stats), or (None, stats) when there's nothing to derive from
    (water 0002 isn't applied, or no water build). Reads only; writes nothing."""
    if not ready(conn):
        return None, {"skipped": "water 0001 or 0002 isn't applied"}
    cs = canals(conn)
    if not cs:
        return None, {"skipped": "no water build (water.canal is empty)"}
    since, until = window(now)
    legal = legal_windows(conn)
    entries = canal_dates.loaded(conn)
    chosen, notes = selections(entries, cs)
    gauged = {}
    for c in cs:
        g = GAUGES.get(c.gauge_lid or "")
        if g is not None and g.lid not in gauged:
            gauged[g.lid] = gauge_spans(g, gauge_readings(conn, g.lid), now)
    rows, cache, counts = [], {}, defaultdict(int)
    for c in cs:
        if not seasonal(c.kind, c.name):
            rows.append(always_row(c, since))
            counts["always"] += 1
            continue
        g = GAUGES.get(c.gauge_lid or "")
        key = (legal.get(c.id), tuple(e.id for e in chosen.get(c.id, ())), g.lid if g else None)
        if key not in cache:
            cache[key] = spans(canal_rules(legal.get(c.id), chosen.get(c.id, ()), g, gauged.get(g.lid, ()) if g else ()),
                               since, until)
        got = cache[key]
        if not got:
            counts["no rule"] += 1
        for start, end, value, rule in got:
            rows.append(row(c, start, end, value, rule))
        basis_now = next((v["basis"] for s, e, v, _ in got if s <= now and (e is None or now < e)), "none")
        state_now = next((v["state"] for s, e, v, _ in got if s <= now and (e is None or now < e)), "unknown")
        counts[f"now {state_now} ({basis_now})"] += 1
    stats = {"canals": len(cs), "lifecycles": len(rows), **dict(sorted(counts.items()))}
    for lid, sp in gauged.items():
        if sp:
            stats[f"gauge {lid}"] = f"{sp[-1].state} since {iso(sp[-1].start)}"
        else:
            stats[f"gauge {lid}"] = "no on or off reading yet"
    for lid in GAUGES:
        if lid not in gauged:
            stats[f"gauge {lid}"] = "linked to no canal in this build"
    for what, label in (("none", "dates names selecting no canal"), ("several", "dates names selecting several"),
                        ("unused id", "dates canal_ids unused")):
        n = sum(1 for x in notes if x.what == what)
        if n:
            stats[label] = n
    return rows, stats


def held(conn):
    return {sid: (active, bytes(h)) for sid, active, h in conn.execute(
        "select source_id, active, content_hash from evt.event where source = %s", (SOURCE["name"],)).fetchall()}


def unchanged(stored, rows):
    """Whether rows are exactly the active lifecycles stored."""
    want = {r["source_id"]: events.content_hash(r) for r in rows}
    if any(stored.get(sid) != (True, h) for sid, h in want.items()):
        return False
    return not any(active and sid not in want for sid, (active, _) in stored.items())


def write(conn, rows, now):
    """Store rows as the whole snapshot of canal_season's lifecycles (evt.event), only when one changed."""
    if unchanged(held(conn), rows):
        return {"new": 0, "changed": 0, "gone": 0}
    counts = events.upsert(conn, SOURCE["name"], rows, now)
    return {k: counts[k] for k in ("new", "changed", "gone")}


def run(conn):
    """The hourly source (and canal-season, canal-dates-load): derive and store, logged in ops.fetch."""
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        conn.execute(f"set local statement_timeout = {int(STATEMENT_TIMEOUT_S * 1000)}")
        rows, stats = derive(conn, f.started_at)
        if rows is not None:
            stats.update(write(conn, rows, f.started_at))
            f.records = len(rows)
        stats.update(dates_file(conn))
    return stats


def dates_file(conn):
    """A note when the repository's canal_dates.json isn't the one loaded (canal-dates-load wasn't run after an
    edit or a deploy); nothing when they agree, or the file is empty and was never loaded."""
    try:
        entries, digest = canal_dates.read_file()
    except (OSError, ValueError) as err:
        return {"dates file": f"unreadable ({err})"[:200]}
    last = canal_dates.last_load(conn)
    if last is None:
        return {"dates file": "not loaded: run canal-dates-load"} if entries else {}
    if last[0] != digest:
        return {"dates file": "changed since its last load: run canal-dates-load"}
    return {}


# ---- the command -----------------------------------------------------------------------------------------------

def _show(conn, rows, names, out):
    keys = {rules.name_key(n) for n in names}
    for r in rows:
        a = r["attributes"]
        if rules.name_key(a["canal"]) in keys:
            end = iso(r["end"]) if r["end"] else "(open)"
            out(f"  {a['canal']} ({a['canal_id']}): {iso(r['start'])} .. {end}  {a['state']:8} {a['basis']:8} "
                f"{a['why']}")


def main(argv=None):
    """`python3 -m ingest canal-season` (registered in ../plugin.json)."""
    ap = argparse.ArgumentParser(prog="python3 -m ingest canal-season", description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="derive and report, then roll back")
    ap.add_argument("--as-of", help="with --dry-run: derive as of this moment (ISO; readings after it left out)")
    ap.add_argument("--canal", action="append", default=[], help="print this canal's lifecycles (repeatable)")
    args = ap.parse_args(argv)
    if args.as_of and not args.dry_run:
        ap.error("--as-of goes with --dry-run")
    out = (lambda msg: print(msg, flush=True))
    with db.connect() as conn:
        if not ready(conn):
            sys.exit("canal-season: water 0001 or 0002 isn't applied (python3 db/migrate.py)")
        if args.dry_run:
            now = seasons.moment(args.as_of) if args.as_of else db.now()
            rows, stats = derive(conn, now)
            out("canal-season: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
            if rows is not None:
                out(f"would write: {'nothing (unchanged)' if unchanged(held(conn), rows) else 'the new snapshot'}")
                _show(conn, rows, args.canal, out)
            conn.rollback()
            out("(dry run: nothing written)")
            return 0
        stats = run(conn)
        out("canal_season: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
        if args.canal:
            rows, _ = derive(conn, db.now())
            _show(conn, rows or [], args.canal, out)
    return 0
