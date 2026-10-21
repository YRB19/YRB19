"""Contribution heatmap: one cell per day, five intensity steps (empty + four accent tints)."""
from .base import PAD, W, document, fit_text, num, text, text_width, footer

GRID_X = PAD  # grid left edge aligns with the title text
GRID_W = W - 2 * GRID_X
LEVEL_MIX = (0.30, 0.55, 0.78, 1.0)


def title(m: dict) -> str:
    return f"{m['total']:,} contributions in the last year"


def alt(m: dict) -> str:
    return (f"Contribution heatmap: {m['total']:,} contributions over the last year across "
            f"{m['active_days']} active days. {m['note']}")


def render(m: dict, theme, meta: dict) -> str:
    pitch = GRID_W / m["ncols"]
    cell = round(pitch * 0.82, 2)
    top = 76
    empty = theme.mix(theme.surface, theme.border, 0.55)
    colors = [empty] + [theme.mix(empty, theme.accent, t) for t in LEVEL_MIX]

    body = [text(PAD, 34, fit_text(title(m), 18, W - 2 * PAD, bold=True), 18, theme.text, bold=True)]
    prev_end = -1e9
    for mo in m["months"]:
        x = GRID_X + mo["col"] * pitch
        w = text_width(mo["label"], 16)
        if x + w > W - 12 or x < prev_end + 6:
            continue
        body.append(text(x, 64, mo["label"], 16, theme.muted))
        prev_end = x + w

    groups = []
    for level in range(5):
        rects = "".join(
            f'<rect x="{num(GRID_X + c["col"] * pitch)}" y="{num(top + c["row"] * pitch)}" width="{num(cell)}" height="{num(cell)}" rx="1.5"/>'
            for c in m["cells"] if c["level"] == level
        )
        if rects:
            groups.append(f'<g fill="{colors[level]}">{rects}</g>')
    body.extend(groups)

    # legend, right-aligned: Less [5 swatches] More
    leg_y = top + 7 * pitch + 28
    more_w = text_width("More", 16)
    sw, gap = 10, 3
    more_x = W - PAD - more_w
    sq_end = more_x - 6
    sq_start = sq_end - (5 * sw + 4 * gap)
    body.append(text(W - PAD, leg_y, "More", 16, theme.muted, anchor="end"))
    for i, col in enumerate(colors):
        body.append(f'<rect x="{num(sq_start + i * (sw + gap))}" y="{num(leg_y - 10)}" width="{sw}" height="{sw}" rx="2" fill="{col}"/>')
    body.append(text(sq_start - 6, leg_y, "Less", 16, theme.muted, anchor="end"))
    foot_y = leg_y + 26
    note_svg, height = footer(m["note"], foot_y, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body))
