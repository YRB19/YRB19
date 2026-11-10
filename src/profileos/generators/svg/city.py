"""Contribution City: an isometric voxel skyline, one tile per calendar day.

Columns are weeks, rows are weekdays (Sunday first, like GitHub's grid). Height AND shade both encode the same bounded
level (0 = flat ground tile, 1-4 = building), so the picture reads without colour. Painter's order: tiles are drawn
by diagonal (col+row) from far to near; tiles on one diagonal never overlap, so each diagonal is emitted as a few merged
paths per shade. That keeps a full year well under the 50 KB SVG cap.
"""
from .base import PAD, W, css, document, footer, g, num, text, text_width

TITLE = "Contribution city"
LEVEL_MIX = (0.30, 0.55, 0.78, 1.0)
LEFT_SHADE, RIGHT_SHADE = 0.22, 0.40
ROWS = 7
HS = 0.36                        # tile half-height / half-width: a low, skyline-like camera
FILL = 0.9                       # footprint inside its tile (leaves thin streets between blocks)
TOP_Y = 48
BLACK = "#000000"
STAGES = 14                      # the skyline rises in a left-to-right wave, one stage per band of diagonals
ANIM = css("@keyframes city-rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}"
           + "".join(f".city-w{i}{{animation:city-rise .7s ease-out {i * 0.09:.2f}s both}}" for i in range(STAGES)))


def alt(m: dict) -> str:
    a, b = m["date_range"]
    return (f"{TITLE}: isometric view of {m['total']:,} contributions from {a} to {b} across {m['active_days']} active days. "
            f"Each tile is one day; taller tiles mean more contributions relative to the busiest day ({m['max_day']:,}). "
            f"{m['source_scope']}. {m['note']}")


def _f(v) -> str:
    return num(round(v, 1))


def render(m: dict, theme, meta: dict) -> str:
    ncols = m["ncols"]
    box = W - 2 * PAD
    a = box / (ncols + ROWS)                     # half tile width
    ea = a * FILL
    heights = m["heights"]
    maxh = max(heights)
    empty = theme.mix(theme.surface, theme.border, 0.55)
    tops = [empty] + [theme.mix(empty, theme.accent, t) for t in LEVEL_MIX]
    lefts = [theme.mix(c, BLACK, LEFT_SHADE) for c in tops]
    rights = [theme.mix(c, BLACK, RIGHT_SHADE) for c in tops]
    ox = PAD
    oy = TOP_Y + maxh

    def centre(col, row):
        return ox + (col - row + ROWS - 1) * a + a, oy + (col + row) * a * HS + a * HS

    diag: dict = {}
    for c in m["cells"]:
        diag.setdefault(c["col"] + c["row"], []).append(c)
    parts = []
    order = sorted(diag)
    for di, d in enumerate(order):
        acc: dict = {}
        start = len(parts)
        for c in diag[d]:
            cx, cy = centre(c["col"], c["row"])
            h = heights[c["level"]]
            lv = c["level"]
            top = f"M{_f(cx)} {_f(cy - ea * HS - h)}l{_f(ea)} {_f(ea * HS)}l{_f(-ea)} {_f(ea * HS)}l{_f(-ea)} {_f(-ea * HS)}z"
            if h:
                left = f"M{_f(cx - ea)} {_f(cy - h)}l{_f(ea)} {_f(ea * HS)}v{_f(h)}l{_f(-ea)} {_f(-ea * HS)}z"
                right = f"M{_f(cx)} {_f(cy + ea * HS - h)}l{_f(ea)} {_f(-ea * HS)}v{_f(h)}l{_f(-ea)} {_f(ea * HS)}z"
                acc.setdefault(("L", lv), []).append(left)
                acc.setdefault(("R", lv), []).append(right)
            acc.setdefault(("T", lv), []).append(top)
        for kind in ("L", "R", "T"):                 # sides first, then roofs: roofs never get covered by their own sides
            for lv in range(5):
                segs = acc.get((kind, lv))
                if segs:
                    fill = {"L": lefts, "R": rights, "T": tops}[kind][lv]
                    parts.append(f'<path fill="{fill}" d="{"".join(segs)}"/>')
        parts[start:] = [g(f"city-w{di * STAGES // len(order)}", "".join(parts[start:]))]

    skyline_bottom = oy + (ncols - 1 + ROWS - 1) * a * HS + 2 * a * HS
    body = [text(PAD, 34, TITLE, 18, theme.text, bold=True),
            text(W - PAD, 34, f"{m['total']:,} contributions", 16, theme.muted, anchor="end")]
    body.extend(parts)
    # legend: Less [5 mini blocks] More
    leg_y = skyline_bottom + 30
    more_w = text_width("More", 16)
    sw, gap = 14, 4
    sq_end = W - PAD - more_w - 6
    sq_start = sq_end - (5 * sw + 4 * gap)
    body.append(text(W - PAD, leg_y, "More", 16, theme.muted, anchor="end"))
    for i in range(5):
        x = sq_start + i * (sw + gap)
        hh = 3 + i * 2
        body.append(f'<rect x="{num(x)}" y="{num(leg_y - hh - 2)}" width="{sw}" height="{hh + 2}" rx="2" fill="{tops[i]}"/>')
    body.append(text(sq_start - 6, leg_y, "Less", 16, theme.muted, anchor="end"))
    a0, b0 = m["date_range"]
    note = f"{a0} to {b0}. {m['note']}"
    note_svg, height = footer(note, leg_y + 28, theme)
    body.append(note_svg)
    return document(meta, theme, height, "".join(body), defs=ANIM)
