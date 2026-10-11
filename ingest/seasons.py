"""Rules by date: what a set of dated and recurring rules says at a moment, and over a stretch of time.

Core, decided Oct 7 (docs/17 §17.8 Q2): recurring lifecycles and one
rules-by-date evaluator. Built in the landscape sprint (Oct 2026), where
`water`'s canal season is its first user (the New York Canal's gauge, the
districts' dates, IDWR's legal season); trails (directions, even and odd
days), lands (vehicle seasons, closures) and wildlife closures can follow.
Python only in v1: plugins turn its answers into lifecycles (evt.event),
and the app reads those, so there is no TypeScript twin to drift from it.
The shared cases in ingest/tests/seasons_cases.json are written so that a
twin can be checked against them if one is ever needed.

**A rule** says "in these dates, days and hours, the state is X". It's a
dict (or JSON) with these keys:

- `level`: how strong it is. The precedence is fixed: a dated order beats
  a closure, which beats a seasonal rule, which beats the default
  (`order`, `closure`, `seasonal`, `default`). Within a level the rule
  listed later wins, so a file's later entries override its earlier ones.
- `value`: the state while the rule is in force: any JSON value but null
  ("on", "closed", {"bikes": "downhill"}).
- `dates`: {"start": ..., "end": ...}, a one-off window. A date is a local
  day, its whole day included ("2026-04-06" to "2026-10-15"); a date and
  time is a moment ("2026-04-06T10:15" in Boise time, or with Z or an
  offset), the end excluded. Only those two ISO forms are read, so a
  compact "20261015" or a week date is refused rather than quietly read as
  a midnight. Either end may be left out (open). Python dates and datetimes
  work too (naive is Boise time). On a rule that also recurs, the dates
  say which occurrences happen, by when they start: an occurrence counts,
  whole, when it starts within them (see RFC 5545 below).
- `yearly`: {"start": "MM-DD", "end": "MM-DD"}, every year from the start
  day through the end day. An end before the start wraps past New Year
  ("11-16" to "04-30"). A window that starts or ends on Feb 29 simply has
  no Feb 29 in other years.
- `weekdays`: RFC 5545's day codes, ["SA", "SU"].
- `monthdays`: days of the month, [1, 15], or "odd" or "even": parity of
  the Boise date, so the 31st and the 1st are both odd (Ridge to Rivers'
  Hulls Gulch rule; docs/sources/trails.md, correction 3).
- `hours`: {"start": "HH:MM", "end": "HH:MM"}, the hours of each day it's
  in force, the end excluded. An end at or before the start runs past
  midnight into the next day ("22:00" to "06:00"); "24:00" is the next
  midnight.
- `id`, `text`, `source`: a name, the source's own words ("Water is
  expected in the canal about April 6"), and where they came from (a URL,
  a page, "gauge BSEI1"). Kept beside the parsed rule for cards and
  lifecycles; the evaluator never reads them.

A rule with none of dates, yearly, weekdays, monthdays and hours is always
in force (a default). Unknown keys are refused, so a typo in a versioned
file fails loudly instead of being ignored.

**RFC 5545.** The recurring keys are a subset of iCalendar's: `weekdays` is
BYDAY, `monthdays` BYMONTHDAY, `hours` an occurrence's start time and
duration, and `dates` DTSTART and UNTIL. As in RFC 5545, an occurrence
starts on a day that passes every filter (the yearly window, the weekdays,
the monthdays) and runs for its hours, so "FR 22:00-02:00" covers early
Saturday and "Oct 31, 22:00-02:00" covers early Nov 1. The dates, like
DTSTART and UNTIL, bound when occurrences start and never cut one short:
nightly 22:00-02:00 with dates "2026-06-20" to "2026-06-26" runs from the
night of June 20 (not the early hours of June 20, which belong to the
night before) through the night of June 26, to 02:00 on June 27, as the
last day of a yearly window does. An occurrence that starts before a
dates start given as a moment doesn't count at all; to start or stop
part-way through one, add a stronger rule for that stretch.

**Time.** Everything is evaluated in America/Boise. A local time that a
daylight-saving change skips or repeats is read with the offset in force
before the change (Python's fold=0), so a whole day can last 23 or 25
hours. Answers carry UTC datetimes.

    from ingest import seasons
    rules = seasons.parse([
        {"level": "default", "value": "unknown"},
        {"level": "seasonal", "value": "on", "yearly": {"start": "04-01", "end": "10-31"},
         "text": "season of use Apr 1 - Oct 31", "source": "IDWR"},
        {"level": "order", "value": "off", "dates": {"start": "2026-09-28T08:00"}, "source": "gauge BSEI1"},
    ])
    seasons.state_at(rules, datetime(2026, 7, 4, 12)).value      # 'on'
    seasons.timeline(rules, date(2026, 1, 1), date(2027, 1, 1))  # [Span(start, end, value, rule), ...]

Standard library only.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, NamedTuple, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Boise")
LEVELS = ("order", "closure", "seasonal", "default")     # strongest first
WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")   # RFC 5545 BYDAY, in Python's weekday() order
KEYS = {"level", "value", "dates", "yearly", "weekdays", "monthdays", "hours", "id", "text", "source"}
DAY = 24 * 60

_MONTH_DAY = re.compile(r"^(\d{2})-(\d{2})$")
_CLOCK = re.compile(r"^(\d{2}):(\d{2})$")
_DAY_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A date and time in ISO 8601's extended form only: Python reads '20260407' and '2026-W15-1'
# as midnight moments too, which would quietly drop an end day. No hour 24 either, which
# Python 3.14 reads as the next midnight and 3.12 refuses.
_DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]([01]\d|2[0-3]):\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})?$")
_MONTH_LENGTHS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)    # Feb 29 is a valid yearly day


@dataclass(frozen=True, eq=False)
class Rule:
    """One parsed rule. start and end are UTC datetimes (or None, open); yearly is
    ((month, day), (month, day)); weekdays and monthdays are frozensets (weekday()
    numbers, days of the month); hours is (start, end) in minutes after midnight,
    with end past 1440 when it runs into the next day."""
    level: str
    value: Any
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    yearly: Optional[tuple] = None
    weekdays: Optional[frozenset] = None
    monthdays: Optional[frozenset] = None
    hours: Optional[tuple] = None
    id: Optional[str] = None
    text: Optional[str] = None
    source: Optional[str] = None

    @property
    def rank(self):
        return LEVELS.index(self.level)

    @property
    def recurs(self):
        return any(x is not None for x in (self.yearly, self.weekdays, self.monthdays, self.hours))


class Verdict(NamedTuple):
    """What the rules say at a moment: the winning rule's value and the rule, or both None."""
    value: Any
    rule: Optional[Rule]


class Span(NamedTuple):
    """A stretch of time with one winning rule: start and end are UTC datetimes, the
    end excluded. value and rule are None where no rule is in force."""
    start: datetime
    end: datetime
    value: Any
    rule: Optional[Rule]


# --- reading rules -----------------------------------------------------------

def _name(spec, i):
    return f"rule {spec.get('id') or i}" if isinstance(spec, dict) else f"rule {i}"


def _local(day, minutes=0):
    """A local day plus minutes after its midnight (past 1440 runs into the next days), as UTC."""
    day = day + timedelta(days=minutes // DAY)
    minutes %= DAY
    return datetime.combine(day, time(minutes // 60, minutes % 60), tzinfo=TZ).astimezone(timezone.utc)


def moment(value, end=False):
    """A moment as a UTC datetime, from a datetime (naive is Boise time), a date (its local
    midnight; with end=True the midnight after, so the day is included) or ISO text of
    either: 'YYYY-MM-DD', or a date and time with T or a space, minutes, and optionally
    seconds and Z or an offset ('2026-04-06T10:15', '2026-04-06 16:15:30Z',
    '2026-04-06T10:15-06:00'). Other ISO forms ('20260406', '2026-W15-1', '2026-04-06T10',
    hour 24) are refused."""
    if isinstance(value, str):
        text = value.strip()
        try:
            if _DAY_ONLY.match(text):
                value = date.fromisoformat(text)
            elif _DATE_TIME.match(text):
                value = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
            else:
                raise ValueError
        except ValueError:
            raise ValueError(f"not a date (YYYY-MM-DD) or a date and time (YYYY-MM-DDTHH:MM, then optionally "
                             f":SS and Z or an offset): {value!r}") from None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return _local(value + timedelta(days=1) if end else value)
    raise TypeError(f"not a date or a date and time: {value!r}")


def _window(spec, what):
    if not isinstance(spec, dict) or not spec or set(spec) - {"start", "end"}:
        raise ValueError(f"{what} takes start and end (either may be left out): {spec!r}")
    return spec.get("start"), spec.get("end")


def _month_day(text, what):
    m = _MONTH_DAY.match(text) if isinstance(text, str) else None
    if not m or not 1 <= int(m[1]) <= 12 or not 1 <= int(m[2]) <= _MONTH_LENGTHS[int(m[1]) - 1]:
        raise ValueError(f"{what} is a day as MM-DD, not {text!r}")
    return int(m[1]), int(m[2])


def _clock(text, what, allow_24=False):
    m = _CLOCK.match(text) if isinstance(text, str) else None
    minutes = int(m[1]) * 60 + int(m[2]) if m and int(m[2]) < 60 else None
    if minutes is None or minutes > DAY or (minutes == DAY and not allow_24):
        raise ValueError(f"{what} is a time as HH:MM{' (or 24:00)' if allow_24 else ''}, not {text!r}")
    return minutes


def rule(spec, i=0):
    """One rule from its dict (see the module's docstring). i names it in errors when it has no id."""
    if isinstance(spec, Rule):
        return spec
    who = _name(spec, i)
    if not isinstance(spec, dict):
        raise ValueError(f"{who}: a rule is a dict, not {type(spec).__name__}")
    unknown = sorted(set(spec) - KEYS)
    if unknown:
        raise ValueError(f"{who}: unknown key(s) {', '.join(unknown)}")
    if spec.get("level") not in LEVELS:
        raise ValueError(f"{who}: level is one of {', '.join(LEVELS)}, not {spec.get('level')!r}")
    if spec.get("value") is None:
        raise ValueError(f"{who}: a rule needs a value (null means no rule)")
    try:
        start = end = yearly = weekdays = monthdays = hours = None
        if "dates" in spec:
            a, b = _window(spec["dates"], "dates")
            start = None if a is None else moment(a)
            end = None if b is None else moment(b, end=True)
            if start is not None and end is not None and end <= start:
                raise ValueError(f"dates end before they start: {spec['dates']!r}")
        if "yearly" in spec:
            a, b = _window(spec["yearly"], "yearly")
            if a is None or b is None:
                raise ValueError(f"yearly needs both start and end: {spec['yearly']!r}")
            yearly = (_month_day(a, "yearly start"), _month_day(b, "yearly end"))
        if "weekdays" in spec:
            codes = spec["weekdays"]
            if not isinstance(codes, list) or not codes or any(c not in WEEKDAYS for c in codes):
                raise ValueError(f"weekdays is a list of {', '.join(WEEKDAYS)}, not {codes!r}")
            weekdays = frozenset(WEEKDAYS.index(c) for c in codes)
        if "monthdays" in spec:
            days = spec["monthdays"]
            if days == "odd":
                monthdays = frozenset(range(1, 32, 2))
            elif days == "even":
                monthdays = frozenset(range(2, 32, 2))
            elif (isinstance(days, list) and days
                  and all(isinstance(d, int) and not isinstance(d, bool) and 1 <= d <= 31 for d in days)):
                monthdays = frozenset(days)
            else:
                raise ValueError(f"monthdays is 'odd', 'even' or a list of days 1-31, not {days!r}")
        if "hours" in spec:
            a, b = _window(spec["hours"], "hours")
            if a is None or b is None:
                raise ValueError(f"hours needs both start and end: {spec['hours']!r}")
            s, e = _clock(a, "hours start"), _clock(b, "hours end", allow_24=True)
            hours = (s, e if e > s else e + DAY)
    except (ValueError, TypeError) as err:
        raise ValueError(f"{who}: {err}") from None
    for key in ("id", "text", "source"):
        if spec.get(key) is not None and not isinstance(spec[key], str):
            raise ValueError(f"{who}: {key} is text")
    return Rule(level=spec["level"], value=spec["value"], start=start, end=end, yearly=yearly, weekdays=weekdays,
                monthdays=monthdays, hours=hours, id=spec.get("id"), text=spec.get("text"), source=spec.get("source"))


def parse(specs):
    """Rules from a list of dicts (Rules pass through), in order: later wins within a level."""
    if not isinstance(specs, list):
        raise ValueError(f"rules come as a list, not {type(specs).__name__}")
    return [rule(s, i) for i, s in enumerate(specs)]


def load(path):
    """Rules from a JSON file: a list of rules, or an object with a "rules" list (and
    anything else, such as a version or notes, beside it)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "rules" not in data:
            raise ValueError(f"{path}: no \"rules\" list")
        data = data["rules"]
    return parse(data)


# --- evaluating ----------------------------------------------------------------

def _day_passes(r, day):
    if r.yearly is not None:
        (a, b), md = r.yearly, (day.month, day.day)
        if not (a <= md <= b if a <= b else md >= a or md <= b):
            return False
    if r.weekdays is not None and day.weekday() not in r.weekdays:
        return False
    return r.monthdays is None or day.day in r.monthdays


def _occurrence(r, day):
    """The UTC interval of the occurrence that starts on a local day."""
    s, e = r.hours if r.hours is not None else (0, DAY)
    return _local(day, s), _local(day, e)


def _clip(a, b, lo, hi):
    a = a if lo is None else max(a, lo)
    b = b if hi is None else min(b, hi)
    return (a, b) if a < b else None


def _starts_within(r, t):
    return (r.start is None or r.start <= t) and (r.end is None or t < r.end)


def intervals(r, start, end):
    """The UTC intervals in [start, end) when one rule (a Rule or its dict) is in force,
    in order, with adjacent occurrences left separate and cut only at start and end.
    start and end are anything moment() reads."""
    r = rule(r)
    lo, hi = moment(start), moment(end)
    if not r.recurs:
        whole = _clip(lo, hi, r.start, r.end)
        return [] if whole is None else [whole]
    if hi <= lo:
        return []
    # An occurrence can start up to a day (plus its hours) before it shows; none starts
    # on a local day before the dates' start day or after their end day.
    span_days = (r.hours[1] // DAY + 1) if r.hours is not None else 1
    day = lo.astimezone(TZ).date() - timedelta(days=span_days)
    last = hi.astimezone(TZ).date()
    if r.start is not None:
        day = max(day, r.start.astimezone(TZ).date())
    if r.end is not None:
        last = min(last, r.end.astimezone(TZ).date())
    out = []
    while day <= last:
        if _day_passes(r, day):
            a, b = _occurrence(r, day)
            got = _clip(a, b, lo, hi) if _starts_within(r, a) else None
            if got:
                out.append(got)
        day += timedelta(days=1)
    return out


def _rules(rules):
    return parse(list(rules))


def _best(rules, positions):
    """The winner among rule positions: the strongest level, then the latest listed."""
    if not positions:
        return None
    return min(positions, key=lambda p: (rules[p].rank, -p))


def state_at(rules, when):
    """What the rules say at a moment (a datetime, naive is Boise time, or ISO text):
    a Verdict with the winning rule's value and the rule, or (None, None)."""
    rules, t = _rules(rules), moment(when)
    live = [p for p, r in enumerate(rules)
            if any(a <= t < b for a, b in intervals(r, t, t + timedelta(microseconds=1)))]
    p = _best(rules, live)
    return Verdict(None, None) if p is None else Verdict(rules[p].value, rules[p])


def timeline(rules, start, end):
    """The winning rule over [start, end), as Spans that cover it end to end, each with
    one winner (None where no rule is in force); a winner's neighbouring occurrences
    join into one span. start and end are datetimes (naive is Boise time), dates (their
    local midnight; the end is excluded) or ISO text."""
    rules, lo, hi = _rules(rules), moment(start), moment(end)
    if hi <= lo:
        return []
    events = []                    # (time, +1 starts / -1 ends, position)
    for p, r in enumerate(rules):
        for a, b in intervals(r, lo, hi):
            events += [(a, 1, p), (b, -1, p)]
    cuts = sorted({lo, hi} | {t for t, _, _ in events})
    events.sort(key=lambda e: e[0])
    live, i, out = {}, 0, []
    for a, b in zip(cuts, cuts[1:]):
        while i < len(events) and events[i][0] <= a:
            t, d, p = events[i]
            live[p] = live.get(p, 0) + d
            if not live[p]:
                del live[p]
            i += 1
        p = _best(rules, list(live))
        r = None if p is None else rules[p]
        if out and out[-1].rule is r:
            out[-1] = out[-1]._replace(end=b)
        else:
            out.append(Span(a, b, None if r is None else r.value, r))
    return out
