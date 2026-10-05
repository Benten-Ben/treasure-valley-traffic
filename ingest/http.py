"""HTTP for ingestors: robots.txt checked before every request, crawl-delay honored.

robots.txt follows RFC 9309 (groups, * and $ wildcards, longest match wins;
4xx means no rules; 5xx or a network error means disallow for now), parsed
leniently for real-world quirks seen in our sources. Ported from the
prototype (tvt/http.py), where these rules were worked out and tested.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import AGENT_TOKEN, USER_AGENT


class RobotsDisallowed(Exception):
    pass


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
        specific = [g for g in self.groups if any(a != "*" and a in AGENT_TOKEN for a in g[0])]
        if specific:
            return specific[0]
        wildcard = [g for g in self.groups if "*" in g[0]]
        return wildcard[0] if wildcard else None

    def allowed(self, url):
        parts = urllib.parse.urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        group = self._group()
        if not group:
            return True
        best = None  # (length, allow)
        for allow, rx, length in group[1]:
            if rx.match(path) and (best is None or length > best[0] or (length == best[0] and allow)):
                best = (length, allow)
        return True if best is None else best[1]

    def crawl_delay(self):
        group = self._group()
        return group[2] if group else None


DISALLOW_ALL = Robots("User-agent: *\nDisallow: /")
_robots = {}      # host -> Robots, or None for "no rules"
_last_hit = {}    # host -> time of last request


def _open(url, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
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


def get(url, timeout=90):
    """GET with the robots check and crawl-delay. Returns (status, body bytes, robots decision)."""
    host, rules, decision = robots_for(url)
    if decision == "unavailable":
        raise RobotsUnavailable(f"robots.txt at {host} couldn't be read; treating {url} as disallowed for now")
    if rules is not None and not rules.allowed(url):
        raise RobotsDisallowed(f"robots.txt at {host} disallows {url}")
    delay = (rules.crawl_delay() if rules else None) or 0
    wait = _last_hit.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()
    with _open(url, timeout=timeout) as r:
        return r.status, r.read(), decision


def get_json(url, timeout=90):
    status, body, decision = get(url, timeout)
    return status, json.loads(body), decision, len(body)
