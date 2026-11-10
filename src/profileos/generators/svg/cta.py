"""Collaboration CTA: a minimal closing banner. Text only: the clickable links are real Markdown links under the image
(links inside a README image are not clickable). It makes no promise of availability."""
from .base import PAD, W, css, document, g, line, num, rect, text, wrap_text

TITLE = "Let's build something"
ANIM = css("@keyframes cta-dot{0%,80%,100%{opacity:.2}40%{opacity:1}}"
           "@keyframes cta-bar{0%,100%{opacity:1}50%{opacity:.45}}"
           ".cta-bar{animation:cta-bar 3s ease-in-out infinite}"
           + "".join(f".cta-d{i}{{animation:cta-dot 1.4s ease-in-out {i * 0.2:.1f}s infinite}}" for i in range(3)))


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
    dots = "".join(g(f"cta-d{i}", f'<circle cx="{num(PAD + 22 + i * 14)}" cy="{num(y + 2)}" r="4" fill="{theme.accent}"/>') for i in range(3))
    height = y + 30
    bar = g("cta-bar", rect(PAD, 24, 4, height - 48, fill=theme.accent, rx=2))
    return document(meta, theme, height, bar + "".join(out) + dots, defs=ANIM)
