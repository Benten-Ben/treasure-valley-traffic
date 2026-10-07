"""HTTP for ingestors: robots.txt checked before every request, crawl-delay honored.

robots.txt follows RFC 9309 (groups, * and $ wildcards, longest match wins;
4xx means no rules; 5xx or a network error means disallow for now), parsed
leniently for real-world quirks seen in our sources. Every group that names
us is merged, as the RFC requires (or every `*` group if none does), and an
exact tie between an allow and a disallow rule counts as disallow: stricter
than the RFC, like our case-insensitive matching (owner, Oct 7). Ported from the
prototype (tvt/http.py), where these rules were worked out and tested.
"""

import gzip
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import AGENT_TOKEN, USER_AGENT


class RobotsDisallowed(Exception):
    pass


class EditRefused(Exception):
    """An ArcGIS edit operation. Some public services advertise edit capabilities
    (Barber Park's sensors, IDFG's access sites); we only ever read (Oct 7)."""


# ArcGIS operations that change a service's data. Refused for every host, GET or POST.
EDIT_OPS = re.compile(r"/(?:feature|map)server(?:/\d+)?/(?:applyedits|addfeatures|updatefeatures|deletefeatures"
                      r"|calculate|append|truncate|addattachment|updateattachment|deleteattachments)\b", re.IGNORECASE)

# Extra spacing between requests to one host, on top of its crawl-delay (the longer wins):
# for hosts whose robots.txt asks for nothing but that we read often or in bulk.
# Sources add their host here (http.PACE_S["host"] = seconds).
PACE_S = {}


class RobotsUnavailable(RobotsDisallowed):
    """robots.txt couldn't be read (5xx or a network error), so the host counts as
    disallowed for now. Unlike a real disallow, it's worth retrying later."""


def lenient_lines(text):
    """Normalize robots.txt quirks so the intended rules apply.

    - strip a UTF-8 byte-order mark (511 Idaho's file starts with one);
    - drop blank and comment lines (ACHD's file has a blank line between
      User-agent and Disallow, which strict parsers read as no rule);
    - rules with no User-agent line apply to everyone (IEM's file).
    """
    lines = [ln.split("#", 1)[0].strip().lstrip("﻿") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if lines and not lines[0].lower().startswith("user-agent"):
        lines.insert(0, "User-agent: *")
    return lines


class Robots:
    """robots.txt rules. Matching is deliberately case-insensitive (stricter than
    the RFC): 511 Idaho lists one casing of paths its pages use in another."""

    def __init__(self, text):
        self.groups = []  # [(agents, rules, crawl_delay)]
        agents, rules, delay, in_rules = [], [], None, False
        for line in lenient_lines(text):
            key, _, val = line.partition(":")
            key, val = key.strip().lower(), val.strip()
            if key == "user-agent":
                if in_rules:
                    self.groups.append((agents, rules, delay))
                    agents, rules, delay, in_rules = [], [], None, False
                agents.append(val.lower())
            elif key in ("allow", "disallow"):
                in_rules = True
                if val:
                    rules.append((key == "allow", self._regex(val), len(val)))
            elif key == "crawl-delay":
                in_rules = True
                try:
                    delay = float(val)
                except ValueError:
                    pass
        if agents:
            self.groups.append((agents, rules, delay))

    @staticmethod
    def _regex(pattern):
        anchored = pattern.endswith("$")
        body = re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
        return re.compile(body + ("$" if anchored else ""), re.IGNORECASE)

    def _group(self):
        """The rules and crawl-delay that apply to us: every group naming our agent token,
        merged (RFC 9309 §2.2.1), or else every `*` group (Canyon County's and ScienceBase's
        files have two). The longest crawl-delay among them wins. None if no group applies."""
        groups = [g for g in self.groups if any(a != "*" and a in AGENT_TOKEN for a in g[0])] \
            or [g for g in self.groups if "*" in g[0]]
        if not groups:
            return None
        delays = [g[2] for g in groups if g[2] is not None]
        return [rule for g in groups for rule in g[1]], (max(delays) if delays else None)

    def allowed(self, url):
        parts = urllib.parse.urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        group = self._group()
        if not group:
            return True
        best = None  # (length, allow)
        for allow, rx, length in group[0]:
            if rx.match(path) and (best is None or length > best[0] or (length == best[0] and not allow)):
                best = (length, allow)
        return True if best is None else best[1]

    def crawl_delay(self):
        group = self._group()
        return group[1] if group else None


DISALLOW_ALL = Robots("User-agent: *\nDisallow: /")
_robots = {}      # host -> Robots, or None for "no rules"
_last_hit = {}    # host -> time of last request


def forget_robots():
    """Drop the cached robots.txt files, so a long-running stream reads them again
    (RFC 9309 allows caching for up to 24 hours)."""
    _robots.clear()


def _open(url, data=None, timeout=90, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def robots_for(url):
    """(host, rules, decision). decision is 'allowed', 'no_rules', or 'unavailable' (couldn't read it)."""
    parts = urllib.parse.urlsplit(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in _robots:
        try:
            with _open(host + "/robots.txt", timeout=30) as r:
                text = r.read().decode("utf-8", "replace")
            # Some servers answer a missing robots.txt with an HTML page and status 200.
            _robots[host] = None if "<html" in text.lower() else Robots(text)
        except urllib.error.HTTPError as err:
            if 400 <= err.code < 500:
                _robots[host] = None
            else:
                return host, DISALLOW_ALL, "unavailable"  # 5xx: disallow for now, don't cache
        except Exception:
            return host, DISALLOW_ALL, "unavailable"
    rules = _robots[host]
    return host, rules, ("no_rules" if rules is None else "allowed")


def _polite(url):
    """Check an URL before requesting it: never an edit operation, robots.txt must allow
    it, and the host's crawl-delay (or PACE_S, whichever is longer) has passed. Returns
    the robots decision."""
    if EDIT_OPS.search(urllib.parse.urlsplit(url).path):
        raise EditRefused(f"refusing an edit operation: {url}")
    host, rules, decision = robots_for(url)
    if decision == "unavailable":
        raise RobotsUnavailable(f"robots.txt at {host} couldn't be read; treating {url} as disallowed for now")
    if rules is not None and not rules.allowed(url):
        raise RobotsDisallowed(f"robots.txt at {host} disallows {url}")
    delay = max((rules.crawl_delay() if rules else None) or 0, PACE_S.get(urllib.parse.urlsplit(url).netloc, 0))
    wait = _last_hit.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()
    return decision


def get(url, timeout=90, compressed=False):
    """GET with the robots check and crawl-delay. Returns (status, body bytes, robots decision).
    compressed=True asks for gzip (the body returned is always uncompressed)."""
    decision = _polite(url)
    with _open(url, timeout=timeout, headers={"Accept-Encoding": "gzip"} if compressed else None) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return r.status, body, decision


def post(url, data, timeout=90):
    """POST a form body (bytes, URL-encoded) with the same checks as get(): for read-only
    queries too long for a URL (ArcGIS servers on IIS refuse query strings over about
    2,000 characters). Returns (status, body bytes, robots decision)."""
    decision = _polite(url)
    with _open(url, data=data, timeout=timeout,
               headers={"Content-Type": "application/x-www-form-urlencoded"}) as r:
        return r.status, r.read(), decision


def get_json(url, timeout=90):
    status, body, decision = get(url, timeout)
    return status, json.loads(body), decision, len(body)
