"""Profile Signal: up to four large metric tiles (stars, contributions, repositories, followers).

Evolved from the Development Pulse card. A tile exists only if GitHub supplied its number. Scope of every number is
stated on the tile and in the alt text; this is an activity/visibility snapshot, never a quality score.
"""
from .base import PAD, W, css, document, footer, g, line, text, text_width

TITLE = "Profile signal"
TILE_H = 92
ANIM = css("@keyframes sig-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}"
           "@keyframes sig-live{0%,100%{opacity:1}50%{opacity:.25}}"
           ".sig-live{animation:sig-live 2s ease-in-out infinite}"
           + "".join(f".sig-in{i}{{animation:sig-in .6s ease-out {i * 0.12:.2f}s both}}" for i in range(4)))


def alt(m: dict) -> str:
    parts = [f"{t['value']:,} {t['label'].lower()} ({t['scope']})" for t in m["tiles"]]
    scopes = " ".join(m["metric_scopes"][t["key"]] for t in m["tiles"])
    return f"{TITLE}, as of {m['generated_at']}: {', '.join(parts)}. {scopes} {m['note']}"


def render(m: dict, theme, meta: dict) -> str:
    tiles = m["tiles"]
    rows = (len(tiles) + 1) // 2
    col_w = (W - 2 * PAD) / 2
    body = [
        text(PAD, 34, TITLE, 18, theme.text, bold=True),
        text(W - PAD, 34, "GitHub", 16, theme.muted, anchor="end"),
        g("sig-live", f'<circle cx="{W - PAD - 62}" cy="28" r="4" fill="{theme.green}"/>'),
        line(PAD, 48, W - PAD, 48, theme.border),
    ]
    top = 56
    if len(tiles) > 1:
        body.append(line(W / 2, top + 8, W / 2, top + rows * TILE_H - 8, theme.border))
    for r in range(1, rows):
        body.append(line(PAD, top + r * TILE_H, W - PAD, top + r * TILE_H, theme.border))
    for i, t in enumerate(tiles):
        r, c = divmod(i, 2)
        x = PAD + c * col_w + (0 if c == 0 else 14)
        y0 = top + r * TILE_H
        s = f"{t['value']:,}"
        size = 40
        while size > 24 and text_width(s, size, bold=True) > col_w - 28:
            size -= 2
        body.append(g(f"sig-in{i}", text(x, y0 + 40, s, size, theme.accent, bold=True)
                      + text(x, y0 + 62, t["label"], 16, theme.text, bold=True) + text(x, y0 + 82, t["scope"], 16, theme.muted)))
    note_svg, height = footer(m["note"], top + rows * TILE_H + 22, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body), defs=ANIM)
