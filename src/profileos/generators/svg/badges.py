"""Status badge: a drawn glyph (no font dependency) + label. Active/experimental use the accent; the rest are muted."""
from ..models import STATUS_LABEL
from .base import num, rect, text, text_width

PAD_X, GLYPH, GAP, HEIGHT, TRACK = 12, 10, 8, 28, 0.6


def glyph(theme, status: str, cx: float, cy: float) -> str:
    c, y = num(cx), num(cy)
    if status == "active":
        return f'<circle cx="{c}" cy="{y}" r="5" fill="{theme.accent}"/>'
    if status == "experimental":
        return (f'<circle cx="{c}" cy="{y}" r="4.25" fill="none" stroke="{theme.accent}" stroke-width="1.5"/>'
                f'<path d="M{c} {num(cy - 4.25)}A4.25 4.25 0 0 0 {c} {num(cy + 4.25)}Z" fill="{theme.accent}"/>')
    if status == "maintained":
        return f'<circle cx="{c}" cy="{y}" r="4.25" fill="none" stroke="{theme.muted}" stroke-width="1.5"/>'
    if status == "paused":
        return f'<circle cx="{c}" cy="{y}" r="4.25" fill="none" stroke="{theme.muted}" stroke-width="1.5" stroke-dasharray="2.5 2"/>'
    return rect(cx - 4.5, cy - 4.5, 9, 9, fill=theme.muted, rx=1)  # archived


def width(status: str) -> float:
    return PAD_X + GLYPH + GAP + text_width(STATUS_LABEL[status], 16, bold=True, tracking=TRACK) + PAD_X


def badge(theme, status: str, right: float, cy: float):
    """Return (markup, width) for a right-aligned badge, or ("", 0) for a status that must not be shown."""
    if status not in STATUS_LABEL:
        return "", 0.0
    w = width(status)
    x = right - w
    label_fill = theme.accent_text if status in ("active", "experimental") else theme.muted
    markup = (
        rect(x, cy - HEIGHT / 2, w, HEIGHT, fill="none", stroke=theme.border, rx=HEIGHT / 2)
        + glyph(theme, status, x + PAD_X + GLYPH / 2, cy)
        + text(x + PAD_X + GLYPH + GAP, cy + 5.5, STATUS_LABEL[status], 16, label_fill, bold=True, tracking=TRACK)
    )
    return markup, w
