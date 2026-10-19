"""Safety + accessibility gate for generated SVGs (spec §10.1, §14).

README images are static: no scripts, no external references, no animation, no embedded HTML. Anything that
fails here aborts the build before a single file is written.
"""
import re
import xml.etree.ElementTree as ET

MAX_BYTES = 50_000
SVG_NS = "http://www.w3.org/2000/svg"
FORBIDDEN_TAGS = {
    "script", "foreignobject", "iframe", "object", "embed", "image", "style", "use", "a", "video", "audio",
    "link", "meta", "animate", "animatetransform", "animatemotion", "set", "feimage",
}
_EXTERNAL_URL = re.compile(r"url\(\s*(?!['\"]?#)", re.I)
_SCHEME = re.compile(r"(?:javascript|data|vbscript):", re.I)
_HTTP = re.compile(r"https?://", re.I)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def validate(svg: str) -> list[str]:
    """Return a list of problems (empty = safe and accessible)."""
    problems: list[str] = []
    if len(svg.encode("utf-8")) > MAX_BYTES:
        problems.append(f"larger than {MAX_BYTES} bytes")
    if re.search(r"<!(DOCTYPE|ENTITY)", svg, re.I):
        problems.append("DOCTYPE/ENTITY declarations are not allowed")
        return problems  # never feed those to a parser
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        return problems + [f"not well-formed XML: {e}"]
    if root.tag != f"{{{SVG_NS}}}svg":
        problems.append("root element is not <svg> in the SVG namespace")
    if not root.get("viewBox"):
        problems.append("missing viewBox")
    for el in root.iter():
        name = _local(el.tag)
        if name in FORBIDDEN_TAGS:
            problems.append(f"forbidden element <{name}>")
        for key, val in el.attrib.items():
            k = _local(key)
            if k.startswith("on"):
                problems.append(f"event handler attribute {k}")
            if k == "href" and not val.startswith("#"):
                problems.append("non-local href")
            if _SCHEME.search(val):
                problems.append(f"script/data URL in attribute {k}")
            if _EXTERNAL_URL.search(val):
                problems.append(f"external url() in attribute {k}")
            if _HTTP.search(val):
                problems.append(f"external reference in attribute {k}")
    # accessibility: labelled image with title + desc
    if root.get("role") != "img":
        problems.append('root must have role="img"')
    if not root.get("aria-labelledby"):
        problems.append("root must have aria-labelledby")
    title = root.find(f"{{{SVG_NS}}}title")
    desc = root.find(f"{{{SVG_NS}}}desc")
    if title is None or not (title.text or "").strip():
        problems.append("missing <title>")
    if desc is None or not (desc.text or "").strip():
        problems.append("missing <desc>")
    return problems
