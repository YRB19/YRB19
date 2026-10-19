"""OS-series ecosystem graph: uniform nodes in a neutral grid, edges only where relationships are declared.

Nodes are deliberately identical in size and weight: the graph shows family membership and declared
relationships, never activity or importance.
"""
import math

from .base import PAD, W, document, fit_text, line, num, rect, text, text_width

TITLE = "OS series"
PILL_W, PILL_H = 148, 60
TOP = 64 + PILL_H / 2  # centre of the first row of nodes


def layout(n: int):
    """Return ([(cx, cy)], height). A neutral two-column grid in curated order: position never implies rank,
    hierarchy or flow. An odd last node is centred. (Edges are straight lines; an edge between two nodes in
    the same column passes behind any node between them.)"""
    pts = []
    for i in range(n):
        if n == 1 or (n % 2 == 1 and i == n - 1):
            x = W / 2
        else:
            x = W / 2 + (-108 if i % 2 == 0 else 108)
        pts.append((x, TOP + (i // 2) * 76))
    height = max(cy for _, cy in pts) + PILL_H / 2 + 20
    return pts, height


def _boundary(cx, cy, tx, ty):
    """Point where the ray from the node centre toward (tx, ty) leaves the node rectangle."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (PILL_W / 2) / abs(dx) if dx else float("inf")
    sy = (PILL_H / 2) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def title(m: dict) -> str:
    return TITLE


def alt(m: dict) -> str:
    nodes = ", ".join(f"{n['label']} ({n['category']})" if n["category"] else n["label"] for n in m["nodes"])
    out = f"{TITLE}: {nodes}."
    if m["edges"]:
        rel = "; ".join(f"{e['from']} to {e['to']}" + (f" ({e['label']})" if e.get("label") else "") for e in m["edges"])
        out += f" Declared relationships: {rel}."
    return out


def render(m: dict, theme, meta: dict) -> str:
    nodes = m["nodes"]
    pts, graph_h = layout(len(nodes))
    labelled = [e for e in m["edges"] if e.get("label")]
    height = graph_h + (len(labelled) * 26 + 8 if labelled else 0)
    pos = {n["slug"]: p for n, p in zip(nodes, pts)}
    uid = f"po-{meta['name']}"
    defs = (f'<marker id="{uid}-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
            f'<path d="M0 0L10 5L0 10z" fill="{theme.muted}"/></marker>')
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        line(PAD, 48, W - PAD, 48, theme.border),
    ]
    for e in m["edges"]:
        (ax, ay), (bx, by) = pos[e["from"]], pos[e["to"]]
        x1, y1 = _boundary(ax, ay, bx, by)
        x2, y2 = _boundary(bx, by, ax, ay)
        body.append(
            f'<line x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}" stroke="{theme.muted}" '
            f'stroke-width="1.5" marker-end="url(#{uid}-arrow)"/>'
        )
    for n in nodes:
        cx, cy = pos[n["slug"]]
        body.append(rect(cx - PILL_W / 2, cy - PILL_H / 2, PILL_W, PILL_H, fill=theme.bg, stroke=theme.accent, sw=1.5, rx=12))
        body.append(text(cx, cy - 2, fit_text(n["label"], 18, PILL_W - 16, bold=True), 18, theme.text, bold=True, anchor="middle"))
        if n["category"]:
            body.append(text(cx, cy + 19, fit_text(n["category"], 16, PILL_W - 16, tracking=0.5), 16, theme.muted, anchor="middle", tracking=0.5))
    # edge labels go in a legend under the graph, where they can never collide with a node
    label_by = {n["slug"]: n["label"] for n in nodes}
    for i, e in enumerate(labelled):
        line_ = f"{label_by[e['from']]} → {label_by[e['to']]} · {e['label']}"
        body.append(text(PAD, graph_h + 6 + i * 26 + 16, fit_text(line_, 16, W - 2 * PAD), 16, theme.muted))
    return document(meta, theme, height, "".join(body), defs=defs)
