"""Development Pulse card: up to four big numbers (2x2 so labels stay legible on a phone)."""
from .base import PAD, W, document, line, text, text_width, footer

TITLE = "Development pulse"


def alt(m: dict) -> str:
    parts = [f"{t['value']:,} {t['noun'][0 if t['value'] == 1 else 1]}" for t in m["tiles"]]
    return f"{TITLE}, {m['window'].lower()}: {', '.join(parts)}. {m['note']}"


def render(m: dict, theme, meta: dict) -> str:
    tiles = m["tiles"]
    rows = (len(tiles) + 1) // 2
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        text(W - PAD, 34, m["window"], 16, theme.muted, anchor="end"),
        line(PAD, 48, W - PAD, 48, theme.border),
    ]
    col_w = (W - 2 * PAD) / 2
    for i, t in enumerate(tiles):
        r, c = divmod(i, 2)
        x, y0 = PAD + c * col_w, 62 + r * 76
        size = 40
        while size > 24 and text_width(f"{t['value']:,}", size, bold=True) > col_w - 16:  # shrink, never overflow
            size -= 2
        body.append(text(x, y0 + 42, f"{t['value']:,}", size, theme.accent, bold=True))
        body.append(text(x, y0 + 66, t["label"], 16, theme.muted))
    foot_y = 62 + rows * 76 + 20
    note_svg, height = footer(m["note"], foot_y, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body))
