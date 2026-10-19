"""Activity bars: commits per project over the window, in curated (not performance) order."""
from .base import PAD, W, document, fit_text, line, rect, text, text_width

TITLE = "Commits by project"
ROW = 34


def alt(m: dict) -> str:
    rows = ", ".join(f"{r['label']} {r['value']:,}" for r in m["rows"])
    return f"{TITLE}, {m['window'].lower()}: {rows}. {m['note']}"


def render(m: dict, theme, meta: dict) -> str:
    rows = m["rows"]
    top = max(r["value"] for r in rows)
    val_w = max(text_width(f"{r['value']:,}", 16, bold=True) for r in rows)
    label_cap = min(128, (W - 2 * PAD) - val_w - 10 - 14 - 90)  # always leave >= 90 units for the bar
    label_w = min(label_cap, max(text_width(r["label"], 16) for r in rows))
    bar_x = PAD + label_w + 14
    bar_end = W - PAD - val_w - 10
    track = bar_end - bar_x
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        text(W - PAD, 34, m["window"], 16, theme.muted, anchor="end"),
        line(PAD, 48, W - PAD, 48, theme.border),
    ]
    for i, r in enumerate(rows):
        cy = 72 + i * ROW
        body.append(text(PAD, cy + 5.5, fit_text(r["label"], 16, label_w), 16, theme.text))
        body.append(rect(bar_x, cy - 5, track, 10, fill=theme.mix(theme.surface, theme.border, 0.7), rx=5))
        if r["value"] > 0:
            body.append(rect(bar_x, cy - 5, max(4.0, track * r["value"] / top), 10, fill=theme.accent, rx=5))
        body.append(text(W - PAD, cy + 5.5, f"{r['value']:,}", 16, theme.text, bold=True, anchor="end"))
    foot_y = 72 + (len(rows) - 1) * ROW + 34
    body.append(text(PAD, foot_y, m["note"], 16, theme.muted))
    return document(meta, theme, foot_y + 22, "".join(body))
