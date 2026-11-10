"""Strict marker-block replacement for README.md."""
import re

REGISTERED = [
    "SIGNAL", "BUILDING", "RELEASES", "SELECTED_SYSTEMS", "PROJECT_MAP", "STACK",
    "CITY", "EARLIER_BUILDS", "TIMELINE", "CTA", "FOOTER",
]
# Blocks whose visuals are now composed into a neighbouring section (SIGNAL = signal + pet, PROJECT_MAP = map + languages,
# CITY = city + rhythm + commit bars). Old READMEs that still carry them have those blocks (and a heading right above) removed.
LEGACY_ABSORBED = ("LANGUAGE_BUBBLES", "RHYTHM", "PET", "ACTIVITY")
# Marker migration (profile-experience enhancement). Old READMEs are upgraded in memory before validation and build.
LEGACY_RENAMES = {"PULSE": "SIGNAL", "OS_SERIES": "PROJECT_MAP", "LINKS": "CTA"}
LEGACY_MERGED_INTO_BUILDING = ("CURRENTLY_BUILDING", "NOW", "RECENTLY_SHIPPED")
# new marker -> (heading, anchor marker, "before" | "after"): inserted only when the new marker is missing
INSERTIONS = [
    ("CITY", "Activity", "ACTIVITY", "before"),
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


def migrate_legacy(text: str):
    """Upgrade a README that still uses the pre-enhancement markers. Returns (new_text, notes). Safe by construction:
    only generated marker blocks are renamed/removed (their content is regenerated on every build); every line outside a
    marker block is untouched; a README already on the new markers is returned unchanged (idempotent)."""
    notes = []
    for old, new in LEGACY_RENAMES.items():
        so, eo = _tokens(old)
        sn, _ = _tokens(new)
        if text.count(so) == 1 and text.count(eo) == 1 and sn not in text:
            text = text.replace(so, _tokens(new)[0]).replace(eo, _tokens(new)[1])
            notes.append(f"migrated marker {old} -> {new}")
    present = [m for m in LEGACY_MERGED_INTO_BUILDING if _tokens(m)[0] in text]
    if present:
        has_new = _tokens("BUILDING")[0] in text
        for i, m in enumerate(present):
            s_, e_ = _tokens(m)
            if text.count(s_) != 1 or text.count(e_) != 1:
                continue  # malformed: leave it for check_markers to report
            if i == 0 and not has_new:
                text = text.replace(s_, _tokens("BUILDING")[0]).replace(e_, _tokens("BUILDING")[1])
                notes.append(f"migrated marker {m} -> BUILDING")
            else:
                text = re.sub(r"\n*" + re.escape(s_) + r".*?" + re.escape(e_) + r"\n*", "\n\n", text, count=1, flags=re.DOTALL)
                notes.append(f"merged marker {m} into BUILDING (block removed; content now regenerated there)")
    for new, heading, anchor, where in INSERTIONS:
        sn, en = _tokens(new)
        sa, ea = _tokens(anchor)
        if sn in text or sa not in text:
            continue
        block = f"### {heading}\n{sn}\n{en}\n\n"
        if where == "before":
            text = text.replace(sa, block + sa, 1)
        else:
            text = text.replace(ea, ea + "\n\n" + block.rstrip("\n"), 1)
        notes.append(f"added missing marker {new}")
    for old in LEGACY_ABSORBED:
        so, eo = _tokens(old)
        if text.count(so) == 1 and text.count(eo) == 1:
            text = re.sub(r"(?:^#{2,4} [^\n]*\n+)?" + re.escape(so) + r".*?" + re.escape(eo) + r"\n*", "", text, count=1, flags=re.DOTALL | re.MULTILINE)
            notes.append(f"removed marker {old} (now composed into another section)")
    return text, notes
