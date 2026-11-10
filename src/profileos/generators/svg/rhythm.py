"""Activity Rhythm: seven weekday bars, relative to the busiest weekday. Counts and shares are printed, so colour is never the carrier."""
from .base import PAD, W, css, document, fit_text, footer, g, line, num, rect, text

TITLE = "Activity rhythm"
ANIM = css("@keyframes rh-grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
           + "".join(f".rh-b{i}{{transform-box:fill-box;transform-origin:50% 100%;animation:rh-grow .7s ease-out {i * 0.08:.2f}s both}}" for i in range(7)))


def alt(m: dict) -> str:
    rows = ", ".join(f"{r['name']} {r['count']:,} ({r['percentage']:.0f}%)" for r in m["rows"])
    return f"{TITLE}, {m['window'][0]} to {m['window'][1]}: contributions by weekday: {rows}. {m['source_scope']}. {m['note']}"


def render(m: dict, theme, meta: dict) -> str:
    rows = m["rows"]
    top_v = max(r["count"] for r in rows) or 1
    slot = (W - 2 * PAD) / 7
    base, chart_h = 150, 74
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        text(W - PAD, 34, "Last 12 months", 16, theme.muted, anchor="end"),
        line(PAD, 48, W - PAD, 48, theme.border),
        line(PAD, base, W - PAD, base, theme.border),
    ]
    peak = max(range(7), key=lambda i: (rows[i]["count"], -i))
    for i, r in enumerate(rows):
        cx = PAD + slot * i + slot / 2
        h = max(3.0, chart_h * r["count"] / top_v) if r["count"] else 2.0
        fill = theme.accent if i == peak else theme.mix(theme.accent, theme.surface, 0.55)
        body.append(g(f"rh-b{i}", rect(cx - 13, base - h, 26, h, fill=fill, rx=4)))
        body.append(text(cx, base - h - 6, f"{r['count']:,}", 16, theme.text, bold=True, anchor="middle"))
        body.append(text(cx, base + 20, r["weekday"], 16, theme.text, anchor="middle"))
        body.append(text(cx, base + 40, f"{r['percentage']:.0f}%", 16, theme.muted, anchor="middle"))
    note_svg, height = footer(m["note"], base + 66, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body), defs=ANIM)
