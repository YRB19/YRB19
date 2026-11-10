"""Project Map: an evidence-based network of the published projects.

Node size = stars on a bounded log scale (zero stars stay visible, a popular repo cannot dominate). Node colour = project
category from the central tokens, AND a letter code inside the node, so the map reads without colour. Lines come only from
shared repository metadata: a shared significant language (dashed) or a shared GitHub topic (solid). The layout is a
deterministic force simulation (no randomness, no trigonometry) followed by rectangle de-overlap, so repeat builds are
byte-identical and neither nodes nor labels collide. The README draws the strongest few lines per node; the complete
relationship list stays in the model for the interactive version.
"""
from ...sanitize import clean_text
from .base import PAD, W, css, document, fit_text, footer, g, num, text, text_width

TITLE = "Project map"
ANIM = css("@keyframes map-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}"
           "@keyframes map-flow{to{stroke-dashoffset:-18}}"
           ".map-flow{animation:map-flow 2.4s linear infinite}"
           + "".join(f".map-f{i}{{animation:map-float {3.4 + i * 0.5:.1f}s ease-in-out {i * 0.6:.1f}s infinite}}" for i in range(3)))
RING = 4.0               # extra radius of the ring that marks OS-series membership
MARGIN = 8.0
TOP = 62
ITER = 320


def _lines(n: dict, show_stars: bool) -> list:
    out = []
    second = " · ".join(x for x in (n.get("language"), f"★ {n['stars']}" if (n["stars"] or show_stars) and n["stars"] >= 0 and (n["stars"] > 0 or show_stars) else None) if x)
    if second:
        out.append(second)
    return out


def _boxes(nodes, show_stars):
    info = []
    for n in nodes:
        ring = RING if n["os_series"] else 0.0
        r = n["radius"] + ring
        lw = max([text_width(n["name"], 16, bold=True)] + [text_width(l, 16) for l in _lines(n, show_stars)])
        lw = min(lw, 150.0)
        extra = 6 + 20 * (1 + len(_lines(n, show_stars)))
        info.append({"r": r, "hw": max(r, lw / 2), "up": r, "down": r + extra})
    return info


def overlaps(pos: list, info: list, margin: float = 0.0) -> list:
    """Pairs of (node + label) boxes that intersect. Used by the layout and by tests."""
    bad = []
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            dx = abs(pos[i][0] - pos[j][0]) - (info[i]["hw"] + info[j]["hw"] + margin)
            a_top, a_bot = pos[i][1] - info[i]["up"], pos[i][1] + info[i]["down"]
            b_top, b_bot = pos[j][1] - info[j]["up"], pos[j][1] + info[j]["down"]
            dy = max(a_top - b_bot, b_top - a_bot) - margin
            if dx < 0 and dy < 0:
                bad.append((i, j))
    return bad


def _sqrt(v):
    return v ** 0.5


def layout(nodes: list, edges: list, show_stars: bool = False, height: float = 300.0):
    """Return ([(x, y)], info) for a canvas of W x (TOP + height). Deterministic."""
    n = len(nodes)
    info = _boxes(nodes, show_stars)
    idx = {nd["slug"]: i for i, nd in enumerate(nodes)}
    pairs = [(idx[e["source"]], idx[e["target"]], e["strength"]) for e in edges if e["source"] in idx and e["target"] in idx]
    left, right = PAD, W - PAD
    top, bottom = TOP, TOP + height
    cols = 3
    pos = [[left + (right - left) * (0.17 + 0.33 * (i % cols)), top + 40 + (height - 110) * ((i // cols) / max(1, (n - 1) // cols))] for i in range(n)]

    def clamp(i):
        pos[i][0] = min(max(pos[i][0], left + info[i]["hw"]), right - info[i]["hw"])
        pos[i][1] = min(max(pos[i][1], top + info[i]["up"]), bottom - info[i]["down"])

    def separate(passes):
        for _ in range(passes):
            moved = False
            for i in range(n):
                for j in range(i + 1, n):
                    ox = info[i]["hw"] + info[j]["hw"] + MARGIN - abs(pos[i][0] - pos[j][0])
                    a_top, a_bot = pos[i][1] - info[i]["up"], pos[i][1] + info[i]["down"]
                    b_top, b_bot = pos[j][1] - info[j]["up"], pos[j][1] + info[j]["down"]
                    oy = min(a_bot, b_bot) - max(a_top, b_top) + MARGIN
                    if ox > 0 and oy > 0:
                        moved = True
                        if ox < oy:
                            s = 1.0 if pos[i][0] <= pos[j][0] else -1.0
                            pos[i][0] -= s * ox / 2; pos[j][0] += s * ox / 2
                        else:
                            s = 1.0 if pos[i][1] <= pos[j][1] else -1.0
                            pos[i][1] -= s * oy / 2; pos[j][1] += s * oy / 2
            for i in range(n):
                clamp(i)
            if not moved:
                break

    cx, cy = (left + right) / 2, (top + bottom) / 2
    for it in range(ITER):
        temp = 10.0 * (1 - it / ITER) + 0.5
        force = [[0.0, 0.0] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                dx, dy = pos[i][0] - pos[j][0], (pos[i][1] - pos[j][1]) * 1.6   # stretch y: boxes are tall, push sideways first
                d2 = dx * dx + dy * dy + 0.01
                d = _sqrt(d2)
                f = 9000.0 / d2
                force[i][0] += f * dx / d; force[i][1] += f * dy / d / 1.6
                force[j][0] -= f * dx / d; force[j][1] -= f * dy / d / 1.6
        for a, b, s in pairs:
            dx, dy = pos[b][0] - pos[a][0], pos[b][1] - pos[a][1]
            d = _sqrt(dx * dx + dy * dy) + 0.01
            f = 0.035 * max(0.0, d - 150.0) * _sqrt(s)
            force[a][0] += f * dx / d; force[a][1] += f * dy / d
            force[b][0] -= f * dx / d; force[b][1] -= f * dy / d
        for i in range(n):
            force[i][0] += 0.004 * (cx - pos[i][0]); force[i][1] += 0.004 * (cy - pos[i][1])
            fx, fy = force[i]
            m = _sqrt(fx * fx + fy * fy)
            if m > temp:
                fx, fy = fx * temp / m, fy * temp / m
            pos[i][0] += fx; pos[i][1] += fy
            clamp(i)
        separate(1)
    separate(200)
    return [(round(x, 1), round(y, 1)) for x, y in pos], info


def solve(nodes, edges, show_stars=False):
    """Grow the canvas until the layout is overlap-free (or the cap is reached). Returns (pos, info, graph_height)."""
    for height in (300, 360, 430, 520, 640):
        pos, info = layout(nodes, edges, show_stars, height)
        if not overlaps(pos, info):
            break
    return pos, info, height


def _legend(m, theme, y):
    out, x, row = [], PAD, 0
    seen = []
    for n in m["nodes"]:
        if n["category"] not in [c for c, _ in seen]:
            seen.append((n["category"], n["category_label"] or n["category"]))
    for cat, label in seen:
        code, col = theme.category(cat)
        w = 26 + text_width(label, 16) + 14
        if x + w > W - PAD and x > PAD:
            x, row = PAD, row + 1
        cy = y + row * 28
        out.append(f'<circle cx="{num(x + 9)}" cy="{num(cy - 5)}" r="9" fill="{theme.mix(theme.surface, col, 0.30)}" stroke="{col}" stroke-width="2"/>')
        out.append(text(x + 9, cy, code, 16, theme.text, bold=True, anchor="middle"))
        out.append(text(x + 24, cy, label, 16, theme.muted))
        x += w
    return out, y + row * 28


def title(m):
    return TITLE


def alt(m: dict) -> str:
    nodes = ", ".join(f"{n['name']} ({n['category_label'] or n['category']}{', OS series' if n['os_series'] else ''}"
                      f"{', ' + n['language'] if n['language'] else ''}{(', 1 star' if n['stars'] == 1 else ', ' + str(n['stars']) + ' stars') if n['stars'] else ''})" for n in m["nodes"])
    by = {}
    for e in m["static_edges"]:
        for l in e["shared_languages"]:
            by.setdefault(f"language {l}", set()).update((e["source"], e["target"]))
        for t in e["shared_topics"]:
            by.setdefault(f"topic {t}", set()).update((e["source"], e["target"]))
    name = {n["slug"]: n["name"] for n in m["nodes"]}
    rel = "; ".join(f"shared {k}: {', '.join(sorted(name[s] for s in v))}" for k, v in sorted(by.items()))
    return (f"Project map of {len(m['nodes'])} published projects: {nodes}. "
            + (f"Connections from shared repository metadata: {rel}. " if rel else "No shared languages or topics connect these projects. ")
            + "Node size reflects stars on a bounded scale.")


def render(m: dict, theme, meta: dict) -> str:
    nodes, edges = m["nodes"], m["static_edges"]
    show = m["show_stars"]
    pos, info, gh = solve(nodes, edges, show)
    where = {n["slug"]: p for n, p in zip(nodes, pos)}
    body = [text(PAD, 34, TITLE, 18, theme.text, bold=True),
            text(W - PAD, 34, f"{len(nodes)} projects", 16, theme.muted, anchor="end")]
    for e in edges:
        (x1, y1), (x2, y2) = where[e["source"]], where[e["target"]]
        op = 0.35 + 0.15 * min(e["strength"], 3)
        sw = 1 + 0.5 * min(e["strength"] - 1, 2)
        dash = "" if e["shared_topics"] else ' stroke-dasharray="5 4" class="map-flow"'
        body.append(f'<line x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}" stroke="{theme.muted}" '
                    f'stroke-width="{num(sw)}" stroke-opacity="{num(op)}"{dash}/>')
    for k, (n, (x, y), inf) in enumerate(zip(nodes, pos, info)):
        code, col = theme.category(n["category"])
        node = []
        if n["os_series"]:
            node.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(n["radius"] + RING)}" fill="none" stroke="{col}" stroke-width="1.5"/>')
        node.append(f'<circle cx="{num(x)}" cy="{num(y)}" r="{num(n["radius"])}" fill="{theme.mix(theme.surface, col, 0.30)}" stroke="{col}" stroke-width="2"/>')
        node.append(text(x, y + 5.5, code, 16, theme.text, bold=True, anchor="middle"))
        body.append(g(f"map-f{k % 3}", "".join(node)))
        ly = y + inf["r"] + 18
        body.append(text(x, ly, fit_text(n["name"], 16, 150, bold=True), 16, theme.text, bold=True, anchor="middle", halo=theme.surface))
        for k, line_ in enumerate(_lines(n, show)):
            body.append(text(x, ly + 20 * (k + 1), fit_text(line_, 16, 150), 16, theme.muted, anchor="middle", halo=theme.surface))
    # legend
    y = TOP + gh + 34
    leg, y = _legend(m, theme, y)
    body.extend(leg)
    y += 30
    kinds = []
    if any(e["shared_topics"] for e in edges):
        kinds.append(("solid", "shared topic"))
    if any(e["shared_languages"] and not e["shared_topics"] for e in edges):
        kinds.append(("dash", "shared language"))
    x = PAD
    for kind, label in kinds:
        d = "" if kind == "solid" else ' stroke-dasharray="5 4"'
        body.append(f'<line x1="{num(x)}" y1="{num(y - 5)}" x2="{num(x + 28)}" y2="{num(y - 5)}" stroke="{theme.muted}" stroke-width="1.5"{d}/>')
        body.append(text(x + 36, y, label, 16, theme.muted))
        x += 36 + text_width(label, 16) + 20
    if any(n["os_series"] for n in nodes):
        body.append(f'<circle cx="{num(x + 9)}" cy="{num(y - 5)}" r="9" fill="none" stroke="{theme.muted}" stroke-width="1.5"/>')
        body.append(f'<circle cx="{num(x + 9)}" cy="{num(y - 5)}" r="5" fill="none" stroke="{theme.muted}" stroke-width="1.5"/>')
        body.append(text(x + 24, y, "OS series", 16, theme.muted))
    if kinds or any(n["os_series"] for n in nodes):
        y += 28
    note = "Lines: shared repository metadata. Size: stars (bounded scale)."
    _, h0 = footer(note, y + 2, theme)
    extra = max(0.0, float(meta.get("min_height", 0)) - h0)      # card stretched to match its neighbour: centre the graph, pin the note
    if extra:
        body = body[:2] + [f'<g transform="translate(0 {num(extra / 2)})">{"".join(body[2:])}</g>']
    note_svg, height = footer(note, y + 2 + extra, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body), defs=ANIM)
