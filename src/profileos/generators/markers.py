"""Strict marker-block replacement for README.md."""
import re

REGISTERED = [
    "CURRENTLY_BUILDING", "NOW", "PULSE", "RECENTLY_SHIPPED", "OS_SERIES", "SELECTED_SYSTEMS",
    "STACK", "EARLIER_BUILDS", "ACTIVITY", "LINKS", "FOOTER",
]
_ANY_START = re.compile(r"<!-- PROFILEOS:START:([A-Z_]+) -->")


class MarkerError(Exception):
    pass


def _tokens(sid: str):
    return f"<!-- PROFILEOS:START:{sid} -->", f"<!-- PROFILEOS:END:{sid} -->"


def check_markers(text: str, required=REGISTERED):
    """Return (errors, warnings). Every registered ID must appear exactly once, START before END."""
    errors, warnings = [], []
    for sid in required:
        s, e = _tokens(sid)
        ns, ne = text.count(s), text.count(e)
        if ns != 1 or ne != 1:
            errors.append(f"marker {sid}: expected 1 START and 1 END, found {ns} START / {ne} END")
        elif text.index(s) > text.index(e):
            errors.append(f"marker {sid}: END appears before START")
    for sid in set(_ANY_START.findall(text)) - set(required):
        warnings.append(f"unregistered marker {sid} left untouched")
    return errors, warnings


def replace_blocks(text: str, blocks: dict):
    """Replace content between markers. Returns (new_text, warnings). Raises MarkerError on any defect."""
    errors, warnings = check_markers(text, required=list(blocks))
    if errors:
        raise MarkerError("; ".join(errors))
    for sid, content in blocks.items():
        s, e = _tokens(sid)
        pattern = re.compile(re.escape(s) + r".*?" + re.escape(e), re.DOTALL)
        body = (content or "").replace("\r\n", "\n").strip("\n")
        inner = f"\n{body}\n" if body else "\n"
        text = pattern.sub(lambda _m, inner=inner, s=s, e=e: s + inner + e, text, count=1)
    return text, warnings
