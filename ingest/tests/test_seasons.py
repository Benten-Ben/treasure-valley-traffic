"""Tests for the rules-by-date evaluator (ingest/seasons.py). Offline.

SharedCasesTest runs the shared cases in seasons_cases.json, the file any
twin of the evaluator must also pass; the rest cover the Python side
(dates and datetimes as input, errors, files, the intervals).

Run: python3 -m unittest discover -s ingest/tests -t .
"""

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from ingest import seasons as S

CASES = os.path.join(os.path.dirname(__file__), "seasons_cases.json")


def local(text):
    """A Boise local time (or a moment with an offset) as an aware datetime in Boise, for messages."""
    return S.moment(text).astimezone(S.TZ)


class SharedCasesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CASES, encoding="utf-8") as f:
            cls.data = json.load(f)

    def test_the_cases(self):
        self.assertGreaterEqual(len(self.data["cases"]), 20)
        for case in self.data["cases"]:
            with self.subTest(case["name"]):
                rules = S.parse(case["rules"])
                for when, value, *rule_id in case.get("at", []):
                    got = S.state_at(rules, when)
                    self.assertEqual(got.value, value, f"at {when}")
                    if rule_id:
                        self.assertEqual(got.rule and got.rule.id, rule_id[0], f"at {when}")
                    if value is None:
                        self.assertIsNone(got.rule)
                t = case.get("timeline")
                if t:
                    got = [(s.start, s.end, s.value, s.rule and s.rule.id)
                           for s in S.timeline(rules, t["start"], t["end"])]
                    want = [(S.moment(a), S.moment(b), v, i) for a, b, v, i in t["spans"]]
                    self.assertEqual(got, want, "\n".join(f"{x[0].astimezone(S.TZ)} {x[1].astimezone(S.TZ)} {x[2]}"
                                                          for x in got))

    def test_spans_cover_the_timeline_end_to_end(self):
        for case in self.data["cases"]:
            t = case.get("timeline")
            if t:
                spans = S.timeline(case["rules"], t["start"], t["end"])
                self.assertEqual(spans[0].start, S.moment(t["start"]))
                self.assertEqual(spans[-1].end, S.moment(t["end"]))
                for a, b in zip(spans, spans[1:]):
                    self.assertEqual(a.end, b.start)
                    self.assertIsNot(a.rule, b.rule)          # neighbours with one winner are joined

    def test_invalid_rules_are_refused(self):
        self.assertGreaterEqual(len(self.data["invalid"]), 20)
        for bad in self.data["invalid"]:
            with self.subTest(bad["why"]), self.assertRaises(ValueError):
                S.rule(bad["rule"])


class InputTest(unittest.TestCase):
    def test_moments(self):
        utc = timezone.utc
        self.assertEqual(S.moment("2026-07-04"), datetime(2026, 7, 4, 6, tzinfo=utc))           # local midnight, MDT
        self.assertEqual(S.moment("2026-07-04", end=True), datetime(2026, 7, 5, 6, tzinfo=utc))  # the day included
        self.assertEqual(S.moment("2026-01-04T10:15"), datetime(2026, 1, 4, 17, 15, tzinfo=utc))  # MST
        self.assertEqual(S.moment("2026-01-04T10:15Z"), datetime(2026, 1, 4, 10, 15, tzinfo=utc))
        self.assertEqual(S.moment(date(2026, 1, 4)), datetime(2026, 1, 4, 7, tzinfo=utc))
        self.assertEqual(S.moment(datetime(2026, 1, 4, 10, 15)), datetime(2026, 1, 4, 17, 15, tzinfo=utc))
        self.assertEqual(S.moment(datetime(2026, 1, 4, 10, 15, tzinfo=utc)), datetime(2026, 1, 4, 10, 15, tzinfo=utc))
        self.assertEqual(S.moment("2026-01-04T10:15", end=True), S.moment("2026-01-04T10:15"))   # a moment is a moment
        with self.assertRaises(ValueError):
            S.moment("Jan 4")
        with self.assertRaises(TypeError):
            S.moment(20260104)

    def test_rules_from_python_dates_and_mixed_with_parsed_ones(self):
        gauge = {"level": "order", "value": "off", "source": "gauge",
                 "dates": {"start": datetime(2026, 9, 28, 8, 0), "end": datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)}}
        season = S.rule({"level": "seasonal", "value": "on", "dates": {"start": date(2026, 4, 1), "end": date(2026, 10, 31)}})
        self.assertEqual(S.state_at([season, gauge], "2026-09-28T08:30").value, "off")
        self.assertEqual(S.state_at([season, gauge], "2026-09-28T09:00").value, "on")      # 15:00 UTC is 09:00 MDT
        self.assertEqual(S.state_at([season, gauge], datetime(2026, 10, 31, 23, 59)).value, "on")
        self.assertIsNone(S.state_at([season, gauge], datetime(2026, 11, 1, 0, 0)).value)

    def test_the_source_and_its_words_stay_with_the_rule(self):
        rules = S.parse([{"id": "idwr", "level": "seasonal", "value": "on", "yearly": {"start": "04-01", "end": "10-31"},
                          "text": "Season of use: April 1 to October 31", "source": "IDWR"}])
        got = S.state_at(rules, "2026-05-01T12:00")
        self.assertEqual((got.rule.id, got.rule.text, got.rule.source), ("idwr", "Season of use: April 1 to October 31",
                                                                         "IDWR"))
        span = S.timeline(rules, "2026-05-01", "2026-05-02")[0]
        self.assertEqual(span.rule.source, "IDWR")

    def test_errors_name_the_rule(self):
        with self.assertRaisesRegex(ValueError, r"rule closure-3: unknown key\(s\) weekday"):
            S.parse([{"level": "default", "value": "x"},
                     {"id": "closure-3", "level": "closure", "value": "closed", "weekday": ["SA"]}])
        with self.assertRaisesRegex(ValueError, r"rule 1: yearly end is a day as MM-DD"):
            S.parse([{"level": "default", "value": "x"},
                     {"level": "seasonal", "value": "on", "yearly": {"start": "04-01", "end": "Oct 31"}}])
        with self.assertRaisesRegex(ValueError, "rules come as a list"):
            S.parse({"level": "default", "value": "x"})

    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "districts.json")
            with open(path, "w") as f:
                json.dump({"version": 3, "notes": "read Oct 10",
                           "rules": [{"level": "order", "value": "on", "dates": {"start": "2026-04-06"},
                                      "source": "https://example.invalid/water-on"}]}, f)
            rules = S.load(path)
            self.assertEqual((len(rules), rules[0].source), (1, "https://example.invalid/water-on"))
            with open(path, "w") as f:
                json.dump([{"level": "default", "value": "unknown"}], f)
            self.assertEqual(S.load(path)[0].value, "unknown")
            with open(path, "w") as f:
                json.dump({"version": 3}, f)
            with self.assertRaisesRegex(ValueError, "no \"rules\" list"):
                S.load(path)


class EvaluationTest(unittest.TestCase):
    def test_intervals_are_clipped_and_kept_apart(self):
        r = S.rule({"level": "closure", "value": "closed", "hours": {"start": "22:00", "end": "02:00"}})
        got = S.intervals(r, S.moment("2026-10-10T00:00"), S.moment("2026-10-11T23:00"))
        self.assertEqual([(a.astimezone(S.TZ).isoformat(), b.astimezone(S.TZ).isoformat()) for a, b in got],
                         [("2026-10-10T00:00:00-06:00", "2026-10-10T02:00:00-06:00"),      # from Oct 9, clipped
                          ("2026-10-10T22:00:00-06:00", "2026-10-11T02:00:00-06:00"),
                          ("2026-10-11T22:00:00-06:00", "2026-10-11T23:00:00-06:00")])     # clipped at the end
        whole = S.rule({"level": "seasonal", "value": "on", "yearly": {"start": "10-10", "end": "10-11"}})
        self.assertEqual(len(S.intervals(whole, S.moment("2026-10-01"), S.moment("2026-10-20"))), 2)

    def test_an_empty_or_backward_timeline(self):
        self.assertEqual(S.timeline([{"level": "default", "value": "x"}], "2026-10-10", "2026-10-10"), [])
        self.assertEqual(S.timeline([{"level": "default", "value": "x"}], "2026-10-11", "2026-10-10"), [])

    def test_a_years_timeline_of_a_daily_rule(self):
        rules = S.parse([{"level": "default", "value": "open"},
                         {"level": "closure", "value": "closed", "hours": {"start": "22:00", "end": "05:00"}},
                         {"level": "seasonal", "value": "dogs leashed", "yearly": {"start": "11-16", "end": "04-30"}}])
        spans = S.timeline(rules, date(2026, 1, 1), date(2027, 1, 1))
        self.assertEqual(sum(1 for s in spans if s.value == "closed"), 366)          # Dec 31, 2025's runs into 2026
        hours = sum((s.end - s.start for s in spans if s.value == "closed"), timedelta())
        # Jan 1's first 5 h, 364 whole nights of 7 h (the spring one 6, the autumn one 8), Dec 31's last 2 h.
        self.assertEqual(hours, timedelta(hours=5 + 364 * 7 + 2))
        spring = [s for s in spans if s.value == "closed" and s.start.astimezone(S.TZ).date() == date(2026, 3, 7)]
        autumn = [s for s in spans if s.value == "closed" and s.start.astimezone(S.TZ).date() == date(2026, 10, 31)]
        self.assertEqual((spring[0].end - spring[0].start, autumn[0].end - autumn[0].start),
                         (timedelta(hours=6), timedelta(hours=8)))
        self.assertEqual(spans[0].value, "closed")
        self.assertEqual(spans[-1].value, "closed")

    def test_at_and_the_timeline_agree(self):
        with open(CASES, encoding="utf-8") as f:
            cases = json.load(f)["cases"]
        for case in cases:
            t = case.get("timeline")
            if not t:
                continue
            rules = S.parse(case["rules"])
            for span in S.timeline(rules, t["start"], t["end"]):
                for when in (span.start, span.start + (span.end - span.start) / 2, span.end - timedelta(seconds=1)):
                    got = S.state_at(rules, when)
                    self.assertEqual((got.value, got.rule), (span.value, span.rule), f"{case['name']} at {when}")


if __name__ == "__main__":
    unittest.main()
