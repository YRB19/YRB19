"""Project card. Every line is optional: missing data omits the line and the card collapses (no placeholders)."""
from ..models import STATUS_LABEL
from .badges import badge
from .base import PAD, W, document, fit_text, num, text, text_width, wrap_text

INNER = W - 2 * PAD


def title(m: dict) -> str:
    return m["title"]


def _meta_bits(m: dict) -> list[str]:
    bits = []
    if m.get("release"):
        bits.append(f"Release {m['release']['tag']}")
    if m.get("last_push"):
        bits.append(f"Last push {m['last_push']}")
    if m.get("stars") is not None:
        bits.append(f"{m['stars']} star{'s' if m['stars'] != 1 else ''}")
    if m.get("forks") is not None:
        bits.append(f"{m['forks']} fork{'s' if m['forks'] != 1 else ''}")
    return bits


def _status_items(m: dict) -> list[dict]:
    items = []
    for key in ("ci", "health"):
        c = m.get(key)
        if c:
            suffix = f"as of {c['as_of']}" if c.get("as_of") else (c.get("date", "")[5:].replace("-", "/") if c.get("date") else "")
            items.append({**c, "kind": key, "text": c["label"] + (f" · {suffix}" if suffix else "")})
    return items


def _status_alt(it: dict) -> str:
    when = f", as of {it['as_of']}" if it.get("as_of") else (f", last run {it['date']}" if it.get("date") else "")
    return f"{it['label']}{when}"


def _glyph(theme, state: str, cx: float, cy: float) -> str:
    """Shape differs per state, so colour is never the only signal."""
    c, y = num(cx), num(cy)
    col = {"passing": theme.green, "online": theme.green, "failing": theme.red, "offline": theme.red,
           "degraded": theme.amber, "in_progress": theme.accent, "queued": theme.muted, "cancelled": theme.muted}[state]
    sw = 'fill="none" stroke="%s" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"' % col
    if state in ("passing", "online"):
        return (f'<circle cx="{c}" cy="{y}" r="5.5" fill="{col}"/>'
                f'<path d="M{num(cx - 2.6)} {y}l1.9 2l3.2-3.8" fill="none" stroke="{theme.bg}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
    if state in ("failing", "offline"):
        return f'<circle cx="{c}" cy="{y}" r="5.5" fill="{col}"/><path d="M{num(cx - 2.4)} {num(cy - 2.4)}l4.8 4.8M{num(cx + 2.4)} {num(cy - 2.4)}l-4.8 4.8" fill="none" stroke="{theme.bg}" stroke-width="1.6" stroke-linecap="round"/>'
    if state == "degraded":
        return f'<path d="M{c} {num(cy - 5.5)}L{num(cx + 5.5)} {num(cy + 4.5)}H{num(cx - 5.5)}Z" fill="{col}"/><path d="M{c} {num(cy - 1.8)}v3" stroke="{theme.bg}" stroke-width="1.5" stroke-linecap="round"/>'
    if state == "in_progress":
        return f'<circle cx="{c}" cy="{y}" r="4.75" {sw}/><path d="M{c} {num(cy - 4.75)}A4.75 4.75 0 0 1 {num(cx + 4.75)} {y}" fill="none" stroke="{col}" stroke-width="3"/>'
    if state == "queued":
        return f'<circle cx="{c}" cy="{y}" r="4.75" {sw} stroke-dasharray="2.2 2"/>'
    return f'<circle cx="{c}" cy="{y}" r="4.75" {sw}/><path d="M{num(cx - 3.4)} {num(cy + 3.4)}L{num(cx + 3.4)} {num(cy - 3.4)}" {sw}/>'


def alt(m: dict) -> str:
    head = m["title"] + (f" — {m['tagline']}" if m.get("tagline") else "")
    parts = [head.rstrip(".")]
    if m.get("status") in STATUS_LABEL:
        parts.append(f"Status: {m['status']}")
    if m.get("stack"):
        parts.append("Stack: " + ", ".join(m["stack"]))
    parts.extend(_status_alt(it) for it in _status_items(m))
    parts.extend(_meta_bits(m))
    return ". ".join(parts) + "."


def render(m: dict, theme, meta: dict) -> str:
    body, badge_w = [], 0.0
    if m.get("status") in STATUS_LABEL:
        markup, bw = badge(theme, m["status"], W - PAD, 33)
        body.append(markup)
        badge_w = bw + 12
    cur = 40
    body.append(text(PAD, cur, fit_text(m["title"], 20, INNER - badge_w, bold=True), 20, theme.text, bold=True))
    if m.get("tagline"):
        for i, line_ in enumerate(wrap_text(m["tagline"], 16, INNER, 2)):
            cur += 30 if i == 0 else 22
            body.append(text(PAD, cur, line_, 16, theme.text))
    stack = list(m.get("stack") or [])
    while stack and text_width(" · ".join(stack), 16) > INNER:
        stack.pop()
    if stack:
        cur += 30
        body.append(text(PAD, cur, " · ".join(stack), 16, theme.accent_text))
    items, used, x = _status_items(m), 0.0, PAD
    placed = []
    for it in items:  # a status that does not fit is dropped (never squeezed below the font floor)
        w = 18 + text_width(it["text"], 16) + (20 if placed else 0)
        if used + w <= INNER:
            placed.append(it)
            used += w
    if placed:
        cur += 30
        for i, it in enumerate(placed):
            if i:
                x += 20
            body.append(_glyph(theme, it["state"], x + 6, cur - 5.5))
            body.append(text(x + 18, cur, it["text"], 16, theme.text))
            x += 18 + text_width(it["text"], 16)
    bits = _meta_bits(m)
    while bits and text_width(" · ".join(bits), 16) > INNER:
        bits.pop()
    if bits:
        cur += 28
        body.append(text(PAD, cur, " · ".join(bits), 16, theme.muted))
    return document(meta, theme, cur + 24, "".join(body))
