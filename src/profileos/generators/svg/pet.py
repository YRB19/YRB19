"""Code Pet: a pixel-art handheld showing a playful snapshot of GitHub contribution activity.

Static and deterministic. The creature (a blob with a 'Y' antenna: YRB19) grows through five stages and its face
follows the weekly mood; none of this is a judgement of the person. No state is punitive: resting is a normal mood,
growth never goes backwards, and no text guilts or scolds.
"""
import math

from .base import PAD, W, css, document, footer, g, num, rect, text

TITLE = "Code Pet"
ANIM = css("@keyframes pet-hop{0%,49%{transform:translateY(0)}50%,100%{transform:translateY(-5px)}}"
           "@keyframes pet-tick{0%,100%{opacity:1}50%{opacity:.35}}"
           ".pet-hop{animation:pet-hop 1.2s steps(1) infinite}"
           ".pet-tick{animation:pet-tick 2s ease-in-out infinite}")
LCD_LIGHT, LCD_DARK, BEZEL, WHITE = "#9BBC0F", "#0F380F", "#0B1220", "#FFFFFF"
GW, GH, CELL = 22, 18, 5                      # LCD grid and pixel size
DEV_X, DEV_Y, DEV_W, DEV_H = PAD, 56, 156, 196
# body (width, height) per growth stage
BODY = ((8, 6), (10, 8), (12, 9), (14, 10), (14, 10))


def alt(m: dict) -> str:
    streak = (f"current streak {m['current_streak']} day{'s' if m['current_streak'] != 1 else ''}" if m["current_streak"]
              else f"longest streak this year {m['longest_streak']} days")
    return (f"{TITLE}, snapshot as of {m['generated_at']}: mood {m['mood']}, food {m['food']}, growth {m['growth_level']}, "
            f"{streak}, {m['weekly_contributions']} contributions in the last 7 days. {m['note']}")


def sprite(stage: int, mood: int) -> set:
    """Set of (x, y) LCD cells that are 'ink'. Pure function of (growth stage, mood index)."""
    w, h = BODY[stage]
    cx = GW / 2
    bottom = GH - 3
    cy = bottom - h / 2
    ink = set()
    for y in range(GH):
        for x in range(GW):
            if ((x + 0.5 - cx) / (w / 2)) ** 2 + ((y + 0.5 - cy) / (h / 2)) ** 2 <= 1.0:
                ink.add((x, y))
    top = int(round(cy - h / 2))
    mid = int(cx)
    if stage >= 2:                                  # the YRB19 antenna: a stalk ending in a 'Y'
        ink |= {(mid, top - 1), (mid, top - 2)}
        if stage >= 3:
            ink |= {(mid - 1, top - 3), (mid + 1, top - 3), (mid - 2, top - 4), (mid + 2, top - 4)}
        else:
            ink |= {(mid, top - 3)}
    if stage >= 3:                                  # feet
        ink |= {(mid - 4, bottom + 1), (mid - 3, bottom + 1), (mid + 3, bottom + 1), (mid + 4, bottom + 1)}
    if stage == 4:                                  # veteran sparkle
        ink |= {(3, 3), (2, 4), (3, 4), (4, 4), (3, 5), (GW - 4, 3), (GW - 5, 4), (GW - 4, 4), (GW - 3, 4), (GW - 4, 5)}
    ex = 3 if w >= 10 else 2
    ey = int(round(cy)) - 1
    L, R = mid - ex, mid + ex - 1
    carve = set()
    if mood == 0:                                   # resting: closed eyes, small 'z'
        carve |= {(L, ey + 1), (L + 1, ey + 1), (R - 1, ey + 1), (R, ey + 1)}
        ink |= {(GW - 7, 2), (GW - 6, 2), (GW - 6, 3), (GW - 7, 4), (GW - 6, 4)}
    elif mood == 1:                                 # warming up: open eyes, flat mouth
        carve |= {(L, ey), (L, ey + 1), (R, ey), (R, ey + 1), (mid - 1, ey + 3), (mid, ey + 3)}
    elif mood == 2:                                 # active: bigger eyes, smile
        carve |= {(L, ey), (L + 1, ey), (L, ey + 1), (L + 1, ey + 1), (R - 1, ey), (R, ey), (R - 1, ey + 1), (R, ey + 1),
                  (mid - 2, ey + 3), (mid + 1, ey + 3), (mid - 1, ey + 4), (mid, ey + 4)}
    else:                                           # thriving: happy '^' eyes, open smile, sparkles
        carve |= {(L, ey + 1), (L + 1, ey), (L + 2, ey + 1), (R - 2, ey + 1), (R - 1, ey), (R, ey + 1),
                  (mid - 1, ey + 3), (mid, ey + 3), (mid - 1, ey + 4), (mid, ey + 4)}
        ink |= {(2, 8), (1, 9), (2, 9), (3, 9), (2, 10)} if stage != 4 else set()
    return {p for p in ink if 0 <= p[0] < GW and 0 <= p[1] < GH} - carve


def _pips(x, y, n, total, theme):
    out = []
    for i in range(total):
        out.append(rect(x + i * 20, y, 14, 14, fill=theme.accent if i < n else "none",
                        stroke=theme.accent if i < n else theme.muted, sw=1.5, rx=3))
    return "".join(out)


def render(m: dict, theme, meta: dict) -> str:
    body_col = theme.mix(theme.accent, "#000000", 0.28)
    rim = theme.mix(theme.accent, "#000000", 0.45)
    button = theme.mix(theme.accent, WHITE, 0.55)
    for c in (LCD_LIGHT, LCD_DARK, BEZEL, WHITE):
        theme.register(c)
    parts = [text(PAD, 34, TITLE, 18, theme.text, bold=True),
             text(W - PAD, 34, f"As of {m['generated_at']}", 16, theme.muted, anchor="end")]
    # handheld
    parts.append(rect(DEV_X, DEV_Y, DEV_W, DEV_H, fill=body_col, stroke=rim, sw=2, rx=46))
    sx, sy = DEV_X + (DEV_W - GW * CELL) / 2, DEV_Y + 26
    parts.append(rect(sx - 8, sy - 8, GW * CELL + 16, GH * CELL + 16, fill=BEZEL, rx=10))
    parts.append(rect(sx, sy, GW * CELL, GH * CELL, fill=LCD_LIGHT, rx=2))
    px = sorted(sprite(m["growth_index"], m["mood_index"]))
    d = "".join(f"M{num(sx + x * CELL)} {num(sy + y * CELL)}h{CELL}v{CELL}h-{CELL}z" for x, y in px)
    parts.append(g("pet-hop", f'<path fill="{LCD_DARK}" d="{d}"/>'))
    parts.append(text(DEV_X + DEV_W / 2, sy + GH * CELL + 38, "YRB19", 16, WHITE, bold=True, anchor="middle", tracking=2))
    by = DEV_Y + DEV_H - 28
    for i in (-1, 0, 1):
        c = f'<circle cx="{num(DEV_X + DEV_W / 2 + i * 30)}" cy="{num(by)}" r="7" fill="{button}"/>'
        parts.append(g("pet-tick", c) if i == 0 else c)
    # readout
    x = DEV_X + DEV_W + 28
    y = 74
    streak_label, streak_val = (("Streak", f"{m['current_streak']} day{'s' if m['current_streak'] != 1 else ''}") if m["current_streak"]
                                else ("Longest streak", f"{m['longest_streak']} days"))
    rows = [("Mood", m["mood"]), ("Food", m["food"]), ("Growth", m["growth_level"]), (streak_label, streak_val),
            ("Last 7 days", f"{m['weekly_contributions']:,} contributions")]
    for label, val in rows:
        parts.append(text(x, y, label, 16, theme.muted))
        parts.append(text(x, y + 20, val, 16, theme.text, bold=True))
        if label == "Food":      # three pips: filled = light / fed / well fed (none filled = no activity this week)
            parts.append(_pips(W - PAD - 3 * 20 + 6, y + 4, m["food_index"], 3, theme))
        y += 40
    note_svg, height = footer(m["note"], DEV_Y + DEV_H + 28, theme)
    parts.append(note_svg)
    return document(meta, theme, height, "".join(parts), defs=ANIM)
