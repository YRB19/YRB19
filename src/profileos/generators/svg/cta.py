"""Collaboration CTA: a minimal closing banner. Text only: the clickable links are real Markdown links under the image
(links inside a README image are not clickable). It makes no promise of availability."""
from .base import PAD, W, document, line, rect, text, wrap_text

TITLE = "Let's build something"


def alt(m: dict) -> str:
    return f"{m['headline']} {m['description'] or ''}".strip()


def render(m: dict, theme, meta: dict) -> str:
    head = wrap_text(m["headline"], 20, W - 2 * PAD - 16, 3, bold=True)
    desc = wrap_text(m["description"] or "", 16, W - 2 * PAD - 16, 4) if m["description"] else []
    body = [rect(PAD, 24, 4, 1, fill=theme.accent)]  # replaced below once the height is known
    y = 52
    out = []
    for ln in head:
        out.append(text(PAD + 16, y, ln, 20, theme.text, bold=True))
        y += 28
    y += 2
    for ln in desc:
        out.append(text(PAD + 16, y, ln, 16, theme.muted))
        y += 24
    height = y + 10
    bar = rect(PAD, 24, 4, height - 48, fill=theme.accent, rx=2)
    return document(meta, theme, height, bar + "".join(out))
