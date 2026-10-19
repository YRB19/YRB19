"""Project card. Every line is optional: missing data omits the line and the card collapses (no placeholders)."""
from ..models import STATUS_LABEL
from .badges import badge
from .base import PAD, W, document, fit_text, text, text_width, wrap_text

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


def alt(m: dict) -> str:
    head = m["title"] + (f" — {m['tagline']}" if m.get("tagline") else "")
    parts = [head.rstrip(".")]
    if m.get("status") in STATUS_LABEL:
        parts.append(f"Status: {m['status']}")
    if m.get("stack"):
        parts.append("Stack: " + ", ".join(m["stack"]))
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
    bits = _meta_bits(m)
    while bits and text_width(" · ".join(bits), 16) > INNER:
        bits.pop()
    if bits:
        cur += 28
        body.append(text(PAD, cur, " · ".join(bits), 16, theme.muted))
    return document(meta, theme, cur + 24, "".join(body))
