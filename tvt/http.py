"""Polite HTTP client: identifies itself, retries, and obeys robots.txt.

Every request checks the host's robots.txt first (cached per host) and raises
RobotsDisallowed if the path is disallowed. Crawl-delay is honored between
requests to the same host within one process.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = ("treasure-valley-traffic/0.2 "
              "(public-interest research; +https://github.com/Benten-Ben/treasure-valley-traffic)")

_robots = {}      # host -> Robots or None (no robots.txt)
_last_hit = {}    # host -> time of last request
AGENT_TOKEN = "treasure-valley-traffic"


class RobotsDisallowed(Exception):
    pass


def _raw_get(url, data=None, timeout=90):
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def lenient_lines(text):
    """Normalize real-world robots.txt quirks so the intended rules apply.

    - strip a UTF-8 byte-order mark (511 Idaho's file starts with one)
    - drop blank and comment lines (ACHD's file has a blank line between
      User-agent and Disallow, which strict parsers read as no rule at all)
    - rules with no User-agent line at all apply to everyone (IEM's file)
    """
    lines = [ln.split("#", 1)[0].strip().lstrip("\ufeff") for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if lines and not lines[0].lower().startswith("user-agent"):
        lines.insert(0, "User-agent: *")
    return lines


class Robots:
    """robots.txt rules per RFC 9309: groups, * and $ wildcards, longest match.

    Matching is deliberately case-insensitive (the RFC says case-sensitive):
    sites like 511 Idaho list one casing of a path their pages use in another,
    and we'd rather over-respect a rule than slip past its intent.
    """

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
            if rx.match(path) and (best is None or length > best[0]
                                   or (length == best[0] and allow)):
                best = (length, allow)
        return True if best is None else best[1]

    def crawl_delay(self):
        group = self._group()
        return group[2] if group else None


DISALLOW_ALL = Robots("User-agent: *\nDisallow: /")


def _robots_for(url):
    """Fetch and cache robots.txt, following RFC 9309.

    2xx: parse the rules. 4xx (including 401/403): no robots.txt, so no
    restrictions. 5xx or network error: assume complete disallow for now,
    without caching, so the next attempt checks again.
    """
    parts = urllib.parse.urlsplit(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host in _robots:
        return host, _robots[host]
    try:
        text = _raw_get(host + "/robots.txt", timeout=30).decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        if 400 <= err.code < 500:
            _robots[host] = None
            return host, None
        return host, DISALLOW_ALL
    except Exception:
        return host, DISALLOW_ALL
    # Some servers answer a missing robots.txt with an HTML page and status 200.
    rules = None if "<html" in text.lower() else Robots(text)
    _robots[host] = rules
    return host, rules


def check_robots(url):
    host, rules = _robots_for(url)
    if rules is not None and not rules.allowed(url):
        raise RobotsDisallowed(f"robots.txt at {host} disallows {url}")
    delay = (rules.crawl_delay() if rules else None) or 0
    wait = _last_hit.get(host, 0) + float(delay) - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def get(url, params=None, data=None, timeout=90, retries=3):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
    check_robots(url)
    for attempt in range(retries):
        try:
            return _raw_get(url, data=data, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if isinstance(err, urllib.error.HTTPError) and err.code < 500:
                raise
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def get_json(url, params=None, data=None, timeout=90):
    return json.loads(get(url, params=params, data=data, timeout=timeout))


def arcgis_query(layer_url, params, page_size=2000):
    """All features from an ArcGIS REST layer query, paging as needed."""
    feats, offset = [], 0
    while True:
        page = get_json(layer_url + "/query", {
            "f": "json", "resultOffset": offset, "resultRecordCount": page_size,
            **params})
        if "error" in page:
            raise RuntimeError(f"{layer_url}: {page['error']}")
        batch = page.get("features", [])
        feats.extend(batch)
        if not batch or not page.get("exceededTransferLimit"):
            return feats
        offset += len(batch)
