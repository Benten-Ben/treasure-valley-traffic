"""Route colors: the 13-slot palette, the "too similar" rule and assignment
(docs/14 §14.4, "Route colors"; the badge rule in §14.3).

Standard library only. The color science follows the dataviz validator the
palette was checked with: OKLab distances x100, colorblind vision simulated
with Machado, Oliveira & Fernandes (2009) at full severity, WCAG contrast.

- PALETTE: 13 fixed, append-only slots. The first 8 are the colors routes had
  before UI v2. A slot's hex never changes, and contrast is never "fixed" by
  editing one (a test pins them); a future slot is appended only after
  re-validation.
- separation(a, b): 1.0 is exactly at the bar (normal-vision dE 15,
  colorblind dE 8); clash(a, b) is below it, or the same color.
- ghost(color): the pale color a route draws in when no bus is running on it.
- badge(color): the badge numeral color and whether it needs a halo.
- assign(...): colors for routes, so that neighbors (routes drawn side by
  side) never clash, in one of two modes (Q3, answered Oct 6: "rebalance").

By hand: python3 -m ingest.route_colors   (prints the palette table and checks)
"""

import math
from collections import Counter

# -- the palette -------------------------------------------------------------------------------------------------

# (name, hex), in slot order. Append-only: never edit or reorder an entry.
PALETTE_SLOTS = [
    ("blue", "#2a78d6"), ("orange", "#eb6834"), ("aqua", "#1baf7a"), ("yellow", "#eda100"),
    ("pink", "#e87ba4"), ("green", "#008300"), ("violet", "#4a3aa7"), ("red", "#e34948"),
    ("wine", "#99095c"), ("lavender", "#a791fa"), ("brown", "#7f4315"), ("plum", "#9059af"),
    ("lime", "#8cc63f"),
]
PALETTE = [h for _, h in PALETTE_SLOTS]
NAMES = {h: n for n, h in PALETTE_SLOTS}

CLAY = "#f3ede2"         # the Clay base flavor's surface, which colors are validated against
INK = "#2b2a33"          # ch. 13 --ink
WHITE = "#ffffff"
CREAM = "#fffbf4"        # ch. 13 --panel: the halo around ink numerals
UNKNOWN = "#8a857c"      # buses whose route isn't known

# The validator's thresholds (light mode).
BAND = (0.43, 0.77)      # OKLCH lightness
CHROMA_FLOOR = 0.10      # OKLCH chroma
NORMAL_BAR = 15.0        # normal-vision dE x100
CVD_BAR = 8.0            # min(protan, deutan) dE x100
BADGE_MIN = 4.5          # WCAG contrast for 14 px bold numerals (small text)
GHOST_DE = 14.0          # a ghost sits about this far from the surface...
GHOST_T_MIN = 0.30       # ...but keeps at least 30% of its color
GHOST_STEP = 0.001

# -- color science ------------------------------------------------------------------------------------------------

MACHADO = {
    "protan": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deutan": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritan": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


def _hex(h):
    h = h.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"not a #rrggbb color: {h!r}")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _s2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin2s(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def linear_rgb(h):
    return tuple(_s2lin(c) for c in _hex(h))


def _oklab_from_linear(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _linear_from_oklab(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def oklab(h):
    return _oklab_from_linear(*linear_rgb(h))


def oklch(h):
    """(L, C) in OKLCH."""
    L, a, b = oklab(h)
    return L, math.hypot(a, b)


def _simulate(h, kind):
    r, g, b = linear_rgb(h)
    M = MACHADO[kind]
    return tuple(max(0.0, min(1.0, M[i][0] * r + M[i][1] * g + M[i][2] * b)) for i in range(3))


def delta_e(a, b, kind=None):
    """OKLab distance x100; kind 'protan', 'deutan' or 'tritan' simulates that vision first."""
    pa = _oklab_from_linear(*(_simulate(a, kind) if kind else linear_rgb(a)))
    pb = _oklab_from_linear(*(_simulate(b, kind) if kind else linear_rgb(b)))
    return 100 * math.dist(pa, pb)


def separation(a, b):
    """1.0 = exactly at the bar: normal-vision dE 15, colorblind dE 8."""
    return min(delta_e(a, b) / NORMAL_BAR, min(delta_e(a, b, "protan"), delta_e(a, b, "deutan")) / CVD_BAR)


def clash(a, b):
    """Two route colors that can't sit side by side: the same, or too similar."""
    return a == b or separation(a, b) < 1.0


def luminance(h):
    r, g, b = linear_rgb(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def to_hex(rgb_linear):
    return "#" + "".join("%02x" % round(_lin2s(c) * 255) for c in rgb_linear)


def ghost(color, surface=CLAY):
    """The route's ghost: an OKLab mix from the surface toward the color, at the
    first step (from 30%, by 0.1%) whose hex sits at least dE 14 from the
    surface. Reproduces the palette table in docs/14 §14.4 exactly."""
    s, c = oklab(surface), oklab(color)
    step = 0
    while True:
        t = GHOST_T_MIN + step * GHOST_STEP
        if t >= 1:
            return color.lower()
        g = to_hex(_linear_from_oklab(*(s[i] + t * (c[i] - s[i]) for i in range(3))))
        if delta_e(g, surface) >= GHOST_DE:
            return g
        step += 1


def badge_text_color(color):
    """White or ink, whichever reads better on the route color."""
    return WHITE if contrast(color, WHITE) >= contrast(color, INK) else INK


def badge(color):
    """The badge rule (docs/14 §14.3): numerals in the text color; if that's
    under 4.5:1 on the plate, they get a 2 px halo in the opposite tone (ink
    around white, cream around ink), and the halo is what they're measured
    against."""
    text = badge_text_color(color)
    on_plate = contrast(color, text)
    halo = on_plate < BADGE_MIN
    halo_color = (INK if text == WHITE else CREAM) if halo else None
    return {"text": text, "on_plate": on_plate, "halo": halo, "halo_color": halo_color,
            "on_halo": contrast(text, halo_color) if halo else None}


def slot_checks(color):
    """The validator's per-slot checks: lightness band and chroma floor."""
    L, C = oklch(color)
    return {"L": L, "C": C, "band": BAND[0] <= L <= BAND[1], "chroma": C >= CHROMA_FLOOR}


def clashing_pairs(palette=PALETTE):
    return [(a, b) for i, a in enumerate(palette) for b in palette[i + 1:] if clash(a, b)]


# -- assignment ---------------------------------------------------------------------------------------------------

MODES = ("rebalance", "minimal")
DEFAULT_MODE = "rebalance"   # the owner's Q3 answer, Oct 6: (a) a one-time rebalance
SEARCH_BUDGET = 1_000_000    # search nodes per search before giving up on it


def cap_for(n_routes, palette=PALETTE):
    """At most this many routes per color (2 for today's 20 routes)."""
    return max(1, math.ceil(n_routes / len(palette)))


def _pair_sep(palette):
    return {(a, b): separation(a, b) for a in palette for b in palette}


def _edges(neighbors, routes):
    """Undirected neighbor pairs, both ends in routes, in a fixed order."""
    keep = set(routes)
    out = set()
    for a, ns in neighbors.items():
        for b in ns:
            if a != b and a in keep and b in keep:
                out.add((a, b) if a < b else (b, a))
    return sorted(out)


def clashes(colors, neighbors):
    """Neighbor pairs whose colors clash (each pair once, sorted)."""
    return [(a, b) for a, b in _edges(neighbors, colors) if clash(colors[a], colors[b])]


def assign(order, neighbors, stored, mode=DEFAULT_MODE, pinned=(), fixed=None, palette=PALETTE,
           n_routes=None, budget=SEARCH_BUDGET):
    """Colors for the routes in `order` (display order) so that neighbors don't clash.

    order: the routes to color. neighbors: route -> set of routes drawn beside
    it. stored: route -> current color (or None). pinned: routes whose stored
    color is kept whatever happens (color_pinned). fixed: other routes whose
    colors are kept but still count toward the per-color cap (dormant routes:
    they keep their color and take no slot). n_routes: how many routes share
    the palette (default: order plus fixed), for the cap.

    Priorities (docs/14 §14.4): 1. no clash between neighbors; 2. at most
    ceil(routes / 13) routes per color (rebalance only); 3. fewest changes
    from the stored colors; 4. the largest worst-case neighbor separation;
    5. then palette order. The search is DSATUR backtracking that tries each
    route's current color first, raising the number of allowed changes from
    0. In minimal mode only routes in a clash (or without a palette color) may
    change. When nothing fits, it falls back to minimizing the sum of
    max(0, 1 - sep) over neighbors.

    Returns (colors, info): colors for every route in order and fixed; info
    says how it got there ('kept', 'search' or 'fallback'), the changes and
    the clashes left.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    fixed = dict(fixed or {})
    sep = _pair_sep(palette)
    pal_index = {c: i for i, c in enumerate(palette)}
    stored = {r: (c.lower() if c else None) for r, c in stored.items()}
    pinned_colors = {r: stored[r] for r in order if r in pinned and stored.get(r)}
    fixed.update(pinned_colors)
    fixed = {r: c.lower() for r, c in fixed.items() if c}
    routes = [r for r in order if r not in fixed]
    n_routes = n_routes if n_routes is not None else len(set(order) | set(fixed))
    cap = cap_for(n_routes, palette) if mode == "rebalance" else None
    nb = {r: sorted(n for n in neighbors.get(r, ()) if n != r and (n in fixed or n in routes)) for r in order}
    for r in fixed:
        nb.setdefault(r, sorted(n for n in neighbors.get(r, ()) if n != r and (n in fixed or n in routes)))
    current = {r: stored.get(r) if stored.get(r) in pal_index else None for r in routes}

    def ok_cap(colors):
        return cap is None or all(v <= cap for v in Counter(colors.values()).values())

    def worst(colors):
        vals = [sep[(colors[a], colors[b])] for a, b in _edges(nb, colors) if a in current or b in current]
        return min(vals) if vals else math.inf

    start = {**fixed, **{r: current[r] for r in routes if current[r]}}
    if len(start) == len(fixed) + len(routes) and not clashes(start, nb) and ok_cap(start):
        return start, {"how": "kept", "changes": [], "clashes": [], "worst": worst(start)}
    rank = {r: i for i, r in enumerate(order)}
    P = len(palette)
    full = (1 << P) - 1
    clash_mask = [sum(1 << j for j, b in enumerate(palette) if clash(a, b)) for a in palette]
    S = [[sep[(a, b)] for b in palette] for a in palette]
    cur_i = {r: pal_index[current[r]] if current[r] else -1 for r in routes}
    exhausted = [False]   # a search ran out of budget, so "fewest changes" isn't proven

    def search(variables, max_changes, first_only=False):
        """The best assignment of `variables` (the other routes as they are) with
        at most max_changes changes, or None. Backtracking with forward checking:
        the most constrained route next (DSATUR's idea, by remaining colors),
        its current color first, then palette order; it bounds on forced
        changes and on the worst separation, so among equally good assignments
        the first found (in palette order) wins."""
        var = set(variables)
        color = {r: pal_index[c] for r, c in fixed.items()}
        color.update({r: cur_i[r] for r in routes if r not in var and cur_i[r] >= 0})
        usage = [0] * P
        for c in color.values():
            usage[c] += 1
        dom = {}
        for v in variables:
            d = full
            for n in nb[v]:
                if n in color:
                    d &= ~clash_mask[color[n]]
            if cap is not None:
                for c in range(P):
                    if usage[c] >= cap:
                        d &= ~(1 << c)
            dom[v] = d
        if any(d == 0 for d in dom.values()):
            return None
        steps = [budget]
        best = [None, -1.0]
        var_nb = {v: [n for n in nb[v] if n in var] for v in variables}

        def rec(dom, changes, worst_so_far):
            if not dom:
                if worst_so_far > best[1]:
                    best[0], best[1] = dict(color), worst_so_far
                return first_only
            steps[0] -= 1
            if steps[0] <= 0:
                exhausted[0] = True
                return True
            forced = sum(1 for u, d in dom.items() if cur_i[u] >= 0 and not (d >> cur_i[u]) & 1)
            if changes + forced > max_changes:
                return False
            v = min(dom, key=lambda u: (bin(dom[u]).count("1"), -len(var_nb[u]), rank[u]))
            d = dom[v]
            cands = [c for c in range(P) if (d >> c) & 1]
            if cur_i[v] >= 0 and (d >> cur_i[v]) & 1:
                cands.remove(cur_i[v])
                cands.insert(0, cur_i[v])
            rest = {u: du for u, du in dom.items() if u != v}
            for c in cands:
                cost = 1 if cur_i[v] >= 0 and c != cur_i[v] else 0
                if changes + cost > max_changes:
                    continue
                w = worst_so_far
                for n in nb[v]:
                    if n in color:
                        w = min(w, S[c][color[n]])
                if w <= best[1]:
                    continue
                nd = dict(rest)
                for n in var_nb[v]:
                    if n in nd:
                        nd[n] &= ~clash_mask[c]
                usage[c] += 1
                if cap is not None and usage[c] >= cap:
                    for u in nd:
                        nd[u] &= ~(1 << c)
                if all(nd.values()):
                    color[v] = c
                    stop = rec(nd, changes + cost, w)
                    del color[v]
                else:
                    stop = False
                usage[c] -= 1
                if stop:
                    return True
            return False

        rec(dom, 0, math.inf)
        if best[0] is None:
            return None
        return {r: palette[c] for r, c in best[0].items()}

    def deepen(variables):
        if not variables or search(variables, len(variables), first_only=True) is None:
            return None
        for k in range(len(variables) + 1):
            found = search(variables, k)
            if found is not None:
                return found
        return None

    if mode == "minimal":
        trouble = {r for r in routes if current[r] is None}
        for a, b in clashes(start, nb):
            trouble.update(x for x in (a, b) if x in current)
        result = deepen([r for r in routes if r in trouble]) or deepen(routes)
    else:
        result = deepen(routes)
    how = "search"
    if result is None:
        result, how = _fallback(order, routes, nb, current, fixed, palette, sep, cap), "fallback"
    changes = [(r, current[r], result[r]) for r in routes if current[r] != result[r]]
    return result, {"how": how, "changes": changes, "clashes": clashes(result, nb), "worst": worst(result),
                    "proven": not exhausted[0]}


def _fallback(order, routes, nb, current, fixed, palette, sep, cap):
    """No clash-free coloring: minimize the sum of max(0, 1 - sep) over
    neighbors (then fewest changes, then even use, then palette order) by
    deterministic local search from the current colors."""
    colors = dict(fixed)
    usage = Counter(fixed.values())
    pal_index = {c: i for i, c in enumerate(palette)}

    def penalty(r, c):
        return sum(max(0.0, 1.0 - (0.0 if c == colors[n] else sep[(c, colors[n])])) for n in nb[r] if n in colors)

    def pick(r):
        allowed = [c for c in palette if cap is None or usage[c] < cap or colors.get(r) == c] or palette
        return min(allowed, key=lambda c: (round(penalty(r, c), 9), 0 if c == current[r] else 1,
                                           usage[c] - (1 if colors.get(r) == c else 0), pal_index[c]))

    by_degree = sorted(routes, key=lambda r: (-len(nb[r]), order.index(r)))
    for r in by_degree:
        colors[r] = pick(r)
        usage[colors[r]] += 1
    for _ in range(50):
        moved = False
        for r in by_degree:
            usage[colors[r]] -= 1
            c = pick(r)
            if c != colors[r] and penalty(r, c) < penalty(r, colors[r]) - 1e-9:
                colors[r], moved = c, True
            usage[colors[r]] += 1
        if not moved:
            break
    return colors


def report(old, new, names=None):
    """Lines 'route 5: aqua #1baf7a -> wine #99095c' for a dry run, in route-number order."""
    names = names or {}

    def key(r):
        n = names.get(r, r)
        return (0, int(n), n) if n.isdigit() else (1, 0, n)

    lines = []
    for r in sorted(set(old) | set(new), key=key):
        a, b = old.get(r), new.get(r)
        if a != b:
            was = f"{NAMES.get(a, '?')} {a}" if a else "none"
            lines.append(f"  route {names.get(r, r)}: {was} -> {NAMES.get(b, '?')} {b}")
    return lines


def main():
    print(f"Route palette: {len(PALETTE)} slots, validated on clay {CLAY}\n")
    print(f"  #  {'name':9} hex      L     C     band chroma  on clay  ghost    badge")
    for i, (name, h) in enumerate(PALETTE_SLOTS, 1):
        s, b = slot_checks(h), badge(h)
        text = "white" if b["text"] == WHITE else "ink"
        print(f"  {i:<2} {name:9} {h}  {s['L']:.3f} {s['C']:.3f} {'ok' if s['band'] else 'FAIL':4} "
              f"{'ok' if s['chroma'] else 'FAIL':6} {contrast(h, CLAY):5.2f}    {ghost(h)}  {text} {b['on_plate']:.2f}"
              + (f", halo {b['on_halo']:.1f}" if b["halo"] else ""))
    u = badge(UNKNOWN)
    print(f"  -  unknown   {UNKNOWN}  badge ink {u['on_plate']:.2f}" + (", halo" if u["halo"] else ""))
    pairs = clashing_pairs()
    print(f"\nClashing pairs ({len(pairs)} of {len(PALETTE) * (len(PALETTE) - 1) // 2}): "
          + ", ".join(f"{NAMES[a]}/{NAMES[b]}" for a, b in pairs))


if __name__ == "__main__":
    main()
