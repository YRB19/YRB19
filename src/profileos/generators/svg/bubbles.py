"""Language bubbles: circle AREA is proportional to the language's share of code bytes. Deterministic spiral packing.

Not a skill, expertise or time-spent measure. Every language is also listed as text (name + percentage), so size and
colour are never the only carriers.
"""
import math

from .base import PAD, W, css, document, fit_text, footer, g, line, num, text, text_width

TITLE = "Languages"
ANIM = css("@keyframes bb-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.035)}}"
           + "".join(f".bb{i}{{transform-box:fill-box;transform-origin:50% 50%;animation:bb-breathe {3 + i * 0.4:.1f}s ease-in-out {i * 0.3:.1f}s infinite}}" for i in range(3)))
RAMP = (0.0, 0.20, 0.38, 0.54, 0.68, 0.80, 0.88)
GAP = 4.0
BOX_W = W - 2 * PAD
BOX_H_MAX = 230
COL_W = (W - 2 * PAD) / 2


def alt(m: dict) -> str:
    parts = ", ".join(f"{i['language']} {i['percentage']:.1f}%" for i in m["items"])
    return f"{TITLE} by bytes of code in public repositories, bubble area proportional to share: {parts}. {m['note']}"


def pack(shares: list) -> tuple:
    """Return ([(cx, cy, r)], (w, h)) with circle area proportional to share, no overlaps, centred; pure function of
    the input order (largest first), no randomness."""
    total = float(sum(shares)) or 1.0
    radii = [math.sqrt(s / total) * 100.0 for s in shares]  # arbitrary unit; rescaled below
    placed = []
    for r in radii:
        if not placed:
            placed.append((0.0, 0.0, r))
            continue
        best = None
        theta = 0.0
        step = 0.05
        while best is None and theta < 400:
            rad = 0.8 * theta + radii[0] * 0.2
            x, y = rad * math.cos(theta), rad * math.sin(theta) * 0.8   # slight squash: wider than tall
            if all(math.hypot(x - px, y - py) >= r + pr + GAP / 3 for px, py, pr in placed):
                best = (x, y, r)
            theta += step
        placed.append(best)
    minx = min(x - r for x, y, r in placed); maxx = max(x + r for x, y, r in placed)
    miny = min(y - r for x, y, r in placed); maxy = max(y + r for x, y, r in placed)
    scale = min(BOX_W / (maxx - minx), BOX_H_MAX / (maxy - miny))
    out = [((x - minx) * scale, (y - miny) * scale, r * scale) for x, y, r in placed]
    return out, ((maxx - minx) * scale, (maxy - miny) * scale)


def _color(theme, i, name):
    if name == "Other":
        return theme.mix(theme.surface, theme.muted, 0.55)
    return theme.mix(theme.accent, theme.text, RAMP[min(i, len(RAMP) - 1)])


def render(m: dict, theme, meta: dict) -> str:
    items = m["items"]
    circles, (w, h) = pack([i["percentage"] for i in items])
    ox, oy = PAD + (BOX_W - w) / 2, 62
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        text(W - PAD, 34, "Public repositories", 16, theme.muted, anchor="end"),
        line(PAD, 48, W - PAD, 48, theme.border),
    ]
    for i, (it, (cx, cy, r)) in enumerate(zip(items, circles)):
        fill = _color(theme, i, it["language"])
        body.append(g(f"bb{i % 3}", f'<circle cx="{num(ox + cx)}" cy="{num(oy + cy)}" r="{num(max(r - GAP / 2, 2))}" fill="{fill}" stroke="{theme.border}" stroke-width="1"/>'))
        label = it["language"]
        pct = f"{it['percentage']:.0f}%" if it["percentage"] >= 10 else ""
        inner = 2 * r - 14
        if r >= 26 and text_width(label, 16) <= inner:
            lum_dark = sum(int(fill[k:k + 2], 16) for k in (1, 3, 5)) < 3 * 140
            ink = "#FFFFFF" if lum_dark else "#0D1117"
            theme.register(ink)
            body.append(text(ox + cx, oy + cy + (0 if not pct else -2), fit_text(label, 16, inner), 16, ink, bold=True, anchor="middle"))
            if pct and r >= 34:
                body.append(text(ox + cx, oy + cy + 18, pct, 16, ink, anchor="middle"))
    y = oy + h + 30
    label_w = COL_W - 20 - 18 - text_width("100.0%", 16) - 8
    for i, it in enumerate(items):
        r_, c = divmod(i, 2)
        lx, ly = PAD + c * COL_W, y + r_ * 28
        body.append(f'<circle cx="{num(lx + 6)}" cy="{num(ly - 5)}" r="6" fill="{_color(theme, i, it["language"])}" stroke="{theme.border}" stroke-width="1"/>')
        body.append(text(lx + 20, ly, fit_text(it["language"], 16, label_w), 16, theme.text))
        body.append(text(lx + COL_W - (18 if c == 0 else 0), ly, f"{it['percentage']:.1f}%", 16, theme.muted, anchor="end"))
    foot_y = y + ((len(items) + 1) // 2 - 1) * 28 + 34
    note_svg, height = footer(m["note"], foot_y, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body), defs=ANIM)
