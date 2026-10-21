"""Design tokens and colour maths shared by every SVG component.

GitHub-inspired surfaces, one accent. Contrast is *computed*, not assumed: if the owner picks an accent that
is too pale/dark for a surface, it is nudged toward the text colour until it passes (3:1 for graphics,
4.5:1 for small text).
"""

BASE = {
    "dark": {"bg": "#0D1117", "surface": "#161B22", "border": "#30363D", "text": "#E6EDF3", "muted": "#8B949E"},
    "light": {"bg": "#FFFFFF", "surface": "#F6F8FA", "border": "#D0D7DE", "text": "#1F2328", "muted": "#656D76"},
}
# Status colours (Phase 6). Only ever paired with a glyph AND a word, so colour is never the sole carrier.
RED = {"dark": "#F85149", "light": "#CF222E"}      # failing CI / offline
GREEN = {"dark": "#3FB950", "light": "#1A7F37"}    # passing CI / online (only from fresh, positive evidence)
AMBER = {"dark": "#D29922", "light": "#9A6700"}    # degraded
DEFAULT_ACCENT = "#3B82F6"
MODES = ("light", "dark")


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def mix(a: str, b: str, t: float) -> str:
    """Linear sRGB blend: t=0 -> a, t=1 -> b."""
    return _hex(tuple(round(x + (y - x) * t) for x, y in zip(_rgb(a), _rgb(b))))


def luminance(h: str) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Theme:
    """One resolved palette (light or dark). Every colour an SVG uses must come from `palette()`."""

    def __init__(self, mode: str, accent: str = DEFAULT_ACCENT):
        if mode not in BASE:
            raise ValueError(f"unknown mode {mode!r}")
        base = BASE[mode]
        self.mode = mode
        self.bg, self.surface, self.border = base["bg"], base["surface"], base["border"]
        self.text, self.muted = base["text"], base["muted"]
        self.red, self.green, self.amber = RED[mode], GREEN[mode], AMBER[mode]
        self.derived: set[str] = set()
        accent = accent.upper()
        self.accent = self._toward_text(accent, (self.bg, self.surface), 3.0)        # fills, bars, big numbers
        self.accent_text = self._toward_text(accent, (self.bg, self.surface), 4.5)   # small accent-coloured text

    def _toward_text(self, color: str, backgrounds, ratio: float) -> str:
        for i in range(21):
            c = mix(color, self.text, i / 20)
            if all(contrast(c, b) >= ratio for b in backgrounds):
                return c
        return self.text

    def mix(self, a: str, b: str, t: float) -> str:
        c = mix(a, b, t)
        self.derived.add(c)
        return c

    def palette(self) -> set[str]:
        base = {self.bg, self.surface, self.border, self.text, self.muted, self.accent, self.accent_text, self.red, self.green, self.amber}
        return base | self.derived
