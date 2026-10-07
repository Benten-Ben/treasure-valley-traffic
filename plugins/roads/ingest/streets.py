"""Street names as our sources write them, made comparable.

COMPASS writes "FAIRVIEW & EAGLE RD" or "I-84B & 11TH AVENUE S.", ACHD's
centerlines "W Fairview Ave" or "WB Interstate 84 Off Exit 50B", ACHD's camera
labels "Eagle & Fairview". `core()` reduces each street to the part that names
it ("FAIRVIEW", "EAGLE", "11TH", "I 84"), so they can be matched.
"""

import re

DIRECTIONS = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "NB", "SB", "EB", "WB",
              "NORTH", "SOUTH", "EAST", "WEST", "NORTHBOUND", "SOUTHBOUND", "EASTBOUND", "WESTBOUND"}
DIRECTION_ABBR = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "NORTHBOUND": "NB",
                  "SOUTHBOUND": "SB", "EASTBOUND": "EB", "WESTBOUND": "WB"}
TYPES = {"AVE": "Ave", "AVENUE": "Ave", "AV": "Ave", "ST": "St", "STREET": "St", "RD": "Rd", "ROAD": "Rd",
         "BLVD": "Blvd", "BOULEVARD": "Blvd", "DR": "Dr", "DRIVE": "Dr", "LN": "Ln", "LANE": "Ln",
         "WAY": "Way", "PKWY": "Pkwy", "PARKWAY": "Pkwy", "CT": "Ct", "COURT": "Ct", "PL": "Pl",
         "PLACE": "Pl", "CIR": "Cir", "CIRCLE": "Cir", "LOOP": "Loop", "TRL": "Trl", "TRAIL": "Trl",
         "TER": "Ter", "EXPY": "Expy", "XING": "Xing", "SQ": "Sq", "HWY": "Hwy", "HIGHWAY": "Hwy"}
HIGHWAY_WORDS = {"HWY", "HIGHWAY", "SH", "ID"}

_SPLIT = re.compile(r"\s*(?:&|@|\+|\bAND\b|\s/\s)\s*", re.I)
_DASHED_ROUTE = re.compile(r"\b([A-Z]{1,2})-?(\d)")


def split_location(location):
    """'FAIRVIEW & EAGLE RD' -> ['FAIRVIEW', 'EAGLE RD']; also splits on @, 'and', ' / ', '+'.
    '20/26' stays whole."""
    return [p for p in (" ".join(s.split()) for s in _SPLIT.split(location or "")) if p]


def tokens(name):
    """Upper-case tokens with punctuation dropped and route numbers spaced: 'I-84B' -> ['I', '84B'],
    'US 20-26' -> ['US', '20/26']."""
    t = (name or "").upper().replace(".", " ").replace(",", " ").replace("'", "").replace("#", " ")
    t = t.replace("(", " ").replace(")", " ")
    t = _DASHED_ROUTE.sub(r"\1 \2", t)            # I-84 / SH-44 / US-20 / I84 -> I 84 ...
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1/\2", t)   # 20-26 -> 20/26
    return t.replace("-", " ").split()


def _routes(toks):
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if t == "INTERSTATE":
            out.append("I")
        elif t == "STATE" and nxt in ("HWY", "HIGHWAY") and i + 2 < len(toks) and toks[i + 2][:1].isdigit():
            out += ["SH"]
            i += 1
        elif t in HIGHWAY_WORDS and nxt[:1].isdigit() and (not out or out[-1] != "US"):
            out.append("SH")
        elif t in ("HWY", "HIGHWAY") and out and out[-1] == "US":
            pass                                        # US HWY 20 -> US 20
        else:
            out.append(t)
        i += 1
    return out


ORDINAL_WORDS = {"FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5", "SIXTH": "6",
                 "SEVENTH": "7", "EIGHTH": "8", "NINTH": "9", "TENTH": "10"}
NUMBER_WORDS = {"3": "THREE", "5": "FIVE", "6": "SIX", "10": "TEN"}      # '5 Mile' -> 'FIVE MILE'

# Local names for numbered routes, and abbreviations COMPASS uses ⚠️ (checked against ACHD's
# centerlines at COMPASS's points, Oct 6, 2026). Used only to match streets near one point.
ALIASES = {
    "SH 44": {"STATE"},                    # State St (Boise to Star)
    "SH 55": {"EAGLE", "KARCHER"},         # Eagle Rd; Karcher Rd in Nampa
    "SH 69": {"MERIDIAN"},                 # Meridian Rd south of I-84 (to Kuna)
    "SH 21": {"GOWEN", "WARM SPRINGS"},
    "US 20/26": {"CHINDEN"},
    "VMP": {"VETERANS MEMORIAL"},
    "BRDWY": {"BROADWAY"},
}


def core(name):
    """The part of a street name that identifies it: no direction, no street type.
    'W Fairview Ave' -> 'FAIRVIEW'; '11TH AVENUE S.' -> '11'; 'WB Interstate 84' -> 'I 84';
    'Hwy 44' -> 'SH 44'; '5 Mile Rd' -> 'FIVE MILE'; 'Ave (b)' -> 'AVENUE B'. Ordinals become
    numbers ('23rd', '23th', 'Twenty...' aside). A note in parentheses is dropped:
    'YALE ST (3RD ST S)' -> 'YALE'."""
    text = (name or "").replace('"', " ")
    text = re.sub(r"\bAVE(?:NUE)?\.?\s*\(?\s*([A-Za-z])\s*\)?\s*$", r"AVENUE \1", text, flags=re.I)  # Ave (b)
    toks = _routes(tokens(re.sub(r"\(.*?(\)|$)", " ", text)))
    while len(toks) > 1 and toks[0] in DIRECTIONS:
        toks = toks[1:]
    while len(toks) > 1 and toks[-1] in DIRECTIONS:
        toks = toks[:-1]
    if len(toks) > 1 and toks[-1] in TYPES and not (toks[-1] in ("HWY", "HIGHWAY")):
        toks = toks[:-1]
    while len(toks) > 1 and toks[-1] in DIRECTIONS:
        toks = toks[:-1]
    out = []
    for i, t in enumerate(toks):
        t = ORDINAL_WORDS.get(t, t)
        m = re.fullmatch(r"(\d+)(ST|ND|RD|TH)", t)
        if m:
            t = m.group(1)
        if t in NUMBER_WORDS and i + 1 < len(toks) and toks[i + 1] == "MILE":
            t = NUMBER_WORDS[t]
        out.append(t)
    return " ".join(out)


def route(c):
    """The numbered route a core name is on: 'I 84 N RAMP' and 'I 84 OFF EXIT 50B' -> 'I 84';
    None for ordinary streets."""
    t = (c or "").split()
    if len(t) >= 2 and t[0] in ("I", "US", "SH") and t[1][:1].isdigit():
        return f"{t[0]} {t[1]}"
    return None


def _osa(a, b):
    """Edit distance counting an adjacent swap as one edit ('KOOTENIA' / 'KOOTENAI')."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _match(a, b):
    if a == b:
        return True
    ra, rb = route(a), route(b)
    if ra or rb:
        return ra == rb
    sa, sb = a.replace(" ", ""), b.replace(" ", "")
    if sa == sb:                                        # 'PARK CENTER' / 'PARKCENTER'
        return True
    ta, tb = a.split(), b.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len("".join(short)) >= 2 and long_[:len(short)] == short:
        return True
    # A misspelling: same first letter, long enough, one edit apart (two from 10 letters).
    n = min(len(sa), len(sb))
    if n >= 6 and sa[0] == sb[0] and sa[0].isalpha():
        return _osa(sa, sb) <= (2 if n >= 10 else 1)
    return False


def same_street(a, b):
    """Two core names name the same street: equal (spaces aside), on the same numbered route
    ('I 84 N RAMP' and 'I 84 OFF EXIT 50B'), one the other's leading words ('BROADWAY' and
    'BROADWAY RAMP'), a known local name for a route ('STATE' and 'SH 44'), or a near-identical
    spelling ('KOOTENIA' and 'KOOTENAI'). Meant for streets near one place, not across the valley."""
    if not a or not b:
        return False
    return (_match(a, b) or any(_match(x, b) for x in ALIASES.get(a, ()))
            or any(_match(a, y) for y in ALIASES.get(b, ())))


def shares_street(names_a, names_b):
    """Any street of one list is the same street as any of the other (core names)."""
    return any(same_street(a, b) for a in names_a for b in names_b)


def key_part(part):
    """A location part normalized for use in a stable key: upper case, no punctuation,
    standard abbreviations ('11TH AVENUE S.' -> '11TH AVE S')."""
    out = []
    for t in _routes(tokens(part)):
        t = DIRECTION_ABBR.get(t, t)
        out.append(TYPES[t].upper() if t in TYPES else t)
    return " ".join(out)


def location_key(location):
    """'FAIRVIEW & EAGLE RD' and 'Eagle Road & Fairview' -> 'eagle rd & fairview'-style keys:
    parts normalized and sorted, so the order the source writes them in doesn't matter."""
    return " & ".join(sorted(key_part(p) for p in split_location(location))).lower()


def _word(t, first):
    if t in TYPES and not first:                        # 'Avenue B' keeps its Avenue
        return TYPES[t]
    if t in DIRECTION_ABBR:
        return DIRECTION_ABBR[t]
    if t in DIRECTIONS or t in ("I", "US", "SH", "VMP") or (t[:1].isalpha() and any(c.isdigit() for c in t)):
        return t                                        # N, I, US, SH stay upper case
    if re.fullmatch(r"\d+(ST|ND|RD|TH)", t):
        return t.lower()                                # 11TH -> 11th
    if t[:1].isdigit():
        return t                                        # 50B
    return "-".join(p.capitalize() for p in t.split("-"))      # CALDWELL-NAMPA -> Caldwell-Nampa


def display(name):
    """A street as we show it: 'FAIRVIEW' -> 'Fairview', '11TH AVENUE S.' -> '11th Ave S',
    'W Fairview Ave' -> 'Fairview Ave' (a leading direction dropped), 'I-84B' -> 'I-84B'.
    Words already in mixed case ('ParkCenter') are kept as written."""
    raw = " ".join((name or "").replace(".", " ").split()).replace("( ", "(").replace(" )", ")")
    words = raw.split()
    if len(words) > 1 and words[0].upper() in DIRECTIONS:
        words = words[1:]
    out = []
    for i, w in enumerate(words):
        if re.fullmatch(r"[A-Za-z]{1,2}-\d[\w/]*", w):  # I-84B, SH-44, US-20/26
            out.append(w.upper())
        elif w.isupper() or w.islower() or w.upper() in TYPES or w.upper() in DIRECTIONS:
            out.append(_word(w.upper(), i == 0))
        else:
            out.append(w)
    return " ".join(out)


def display_location(location):
    """'FAIRVIEW & EAGLE RD' -> 'Fairview & Eagle Rd'."""
    parts = split_location(location)
    return " & ".join(display(p) for p in parts) if parts else display(location)
