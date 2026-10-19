"""Language distribution: stacked bar + two-column legend (labels and percentages, never colour alone)."""
from .base import PAD, W, document, fit_text, line, num, rect, text, text_width

TITLE = "Languages"
RAMP = (0.0, 0.20, 0.38, 0.54, 0.68, 0.80)  # accent blended toward the text colour: distinct lightness steps
COL_W = (W - 2 * PAD) / 2


def alt(m: dict) -> str:
    parts = ", ".join(f"{i['language']} {i['pct']:.1f}%" for i in m["items"])
    return f"{TITLE} by bytes of code in public repositories: {parts}. {m['note']}"


def _color(theme, i: int, name: str) -> str:
    if name == "Other":
        return theme.mix(theme.surface, theme.muted, 0.55)
    return theme.mix(theme.accent, theme.text, RAMP[min(i, len(RAMP) - 1)])


def render(m: dict, theme, meta: dict) -> str:
    items = m["items"]
    total = sum(i["pct"] for i in items) or 1.0
    bar_w, bar_y, bar_h = W - 2 * PAD, 62, 14
    uid = f"po-{meta['name']}"
    defs = f'<clipPath id="{uid}-clip"><rect x="{PAD}" y="{bar_y}" width="{num(bar_w)}" height="{bar_h}" rx="7"/></clipPath>'
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        text(W - PAD, 34, "Public repositories", 16, theme.muted, anchor="end"),
        line(PAD, 48, W - PAD, 48, theme.border),
    ]
    segs, x = [], float(PAD)
    for i, it in enumerate(items):
        w = bar_w * it["pct"] / total
        segs.append(rect(x, bar_y, w, bar_h, fill=_color(theme, i, it["language"]), stroke=theme.surface, sw=2))
        x += w
    body.append(f'<g clip-path="url(#{uid}-clip)">{"".join(segs)}</g>')

    pct_w = text_width("100.0%", 16)
    label_w = COL_W - 20 - 18 - pct_w - 8
    for i, it in enumerate(items):
        r, c = divmod(i, 2)
        lx, ly = PAD + c * COL_W, 104 + r * 28
        body.append(rect(lx, ly - 11, 12, 12, fill=_color(theme, i, it["language"]), rx=3))
        body.append(text(lx + 20, ly, fit_text(it["language"], 16, label_w), 16, theme.text))
        pct_x = lx + COL_W - (18 if c == 0 else 0)  # left column keeps a gutter before the next swatch
        body.append(text(pct_x, ly, f"{it['pct']:.1f}%", 16, theme.muted, anchor="end"))
    foot_y = 104 + ((len(items) + 1) // 2 - 1) * 28 + 34
    body.append(text(PAD, foot_y, m["note"], 16, theme.muted))
    return document(meta, theme, foot_y + 22, "".join(body), defs=defs)
