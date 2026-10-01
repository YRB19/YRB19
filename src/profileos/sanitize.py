"""Text sanitisation for anything that originates from repo metadata."""
import html
import re

_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|&~])")


def clean_text(value, max_len: int = 90):
    """Strip control chars, collapse whitespace, truncate. None stays None."""
    if value is None:
        return None
    s = " ".join(_CTRL.sub(" ", str(value)).split())
    if max_len and len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def md(value, max_len: int = 90) -> str:
    """Clean + escape for inline Markdown."""
    s = clean_text(value, max_len) or ""
    return _MD_SPECIAL.sub(r"\\\1", s)


def xml(value, max_len: int = 90) -> str:
    """Clean + escape for XML/SVG text nodes and attributes."""
    return html.escape(clean_text(value, max_len) or "", quote=True)
