"""Shared SVG helpers: geometry constants, text fitting, element builders, document wrapper.

Mobile rule: every SVG is drawn on a 432-unit wide canvas. GitHub scales README images to the container
(about 328px on a phone), which puts a 16-unit font at roughly 12px. So 16 units is the floor for any text.
"""
import html

from ...sanitize import clean_text

W = 432            # canvas width in user units
PAD = 20           # horizontal padding inside cards
MIN_FONT = 16      # smallest permitted font size (units)
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

_NARROW = set("iljtfI.,:;|!'`()[]/ ·-–")
_WIDE = set("mwMW@%")


def num(x) -> str:
    s = f"{float(x):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def esc(value, max_len=None) -> str:
    """Clean control characters, then escape for XML text and attribute context."""
    return html.escape(clean_text(value, max_len) or "", quote=True)


# ---- text measurement (a conservative estimate; real system fonts come out narrower) ----------------------
def _cw(c: str) -> float:
    if c in _NARROW:
        return 0.30
    if c in _WIDE:
        return 0.86
    if c.isupper():
        return 0.68
    if c.isdigit():
        return 0.58
    return 0.55


def text_width(s: str, size: float, *, bold: bool = False, tracking: float = 0.0) -> float:
    w = sum(_cw(c) for c in s) * size
    if bold:
        w *= 1.07
    return w + tracking * len(s)


def fit_text(s: str, size: float, max_w: float, *, bold: bool = False, tracking: float = 0.0) -> str:
    """Truncate with an ellipsis so the estimated width fits max_w."""
    s = clean_text(s, None) or ""
    if text_width(s, size, bold=bold, tracking=tracking) <= max_w:
        return s
    while s and text_width(s + "…", size, bold=bold, tracking=tracking) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def wrap_text(s: str, size: float, max_w: float, max_lines: int, *, bold: bool = False) -> list[str]:
    words = (clean_text(s, None) or "").split()
    lines, cur = [], ""
    overflow = False
    for i, w in enumerate(words):
        trial = f"{cur} {w}".strip()
        if text_width(trial, size, bold=bold) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            overflow = True
            break
    if not overflow and cur:
        lines.append(cur)
    if len(lines) > max_lines or overflow:
        lines = lines[:max_lines]
        overflow = True
    out = [fit_text(l, size, max_w, bold=bold) for l in lines]
    if overflow and out:
        out[-1] = fit_text(out[-1].rstrip(".,;:…") + "…", size, max_w, bold=bold)
    return out


# ---- element builders ------------------------------------------------------------------------------------
def text(x, y, s, size, fill, *, bold=False, anchor="start", tracking=0.0) -> str:
    attrs = [f'x="{num(x)}"', f'y="{num(y)}"', f'font-size="{num(size)}"', f'font-family="{FONT}"', f'fill="{fill}"']
    if bold:
        attrs.append('font-weight="600"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if tracking:
        attrs.append(f'letter-spacing="{num(tracking)}"')
    return f"<text {' '.join(attrs)}>{esc(s)}</text>"


def rect(x, y, w, h, *, fill="none", stroke=None, sw=1, rx=0) -> str:
    a = f'x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}"'
    if rx:
        a += f' rx="{num(rx)}"'
    a += f' fill="{fill}"'
    if stroke:
        a += f' stroke="{stroke}" stroke-width="{num(sw)}"'
    return f"<rect {a}/>"


def line(x1, y1, x2, y2, stroke, sw=1) -> str:
    return f'<line x1="{num(x1)}" y1="{num(y1)}" x2="{num(x2)}" y2="{num(y2)}" stroke="{stroke}" stroke-width="{num(sw)}"/>'


def document(meta: dict, theme, height, body: str, defs: str = "") -> str:
    """Wrap a component body in an accessible, self-contained SVG document (card background + border)."""
    uid = f"po-{meta['name']}"
    h = num(height)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
        f'role="img" aria-labelledby="{uid}-t {uid}-d">'
        f'<title id="{uid}-t">{esc(meta["title"], 120)}</title>'
        f'<desc id="{uid}-d">{esc(meta["alt"], 600)}</desc>'
        f"{defs}"
        f'<rect x=".5" y=".5" width="{W - 1}" height="{num(float(height) - 1)}" rx="12" '
        f'fill="{theme.surface}" stroke="{theme.border}"/>'
        f"{body}</svg>\n"
    )


def footer(note: str, y: float, theme, max_lines: int = 3) -> tuple[str, float]:
    """Footnote wrapped to the canvas (a scope statement must never be clipped or shrunk below the font floor).
    Returns (markup, canvas height). One line costs exactly what the old single-line footer did."""
    lines = wrap_text(note, 16, W - 2 * PAD, max_lines)
    markup = "".join(text(PAD, y + i * 22, ln, 16, theme.muted) for i, ln in enumerate(lines))
    return markup, y + (len(lines) - 1) * 22 + 22
