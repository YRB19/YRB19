"""Design tokens (contrast is computed, not assumed) and the SVG safety/accessibility gate."""
import pytest

from profileos.generators.svg import safety
from profileos.generators.svg.tokens import BASE, MODES, Theme, contrast, mix

GOOD = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="432" height="60" viewBox="0 0 432 60" role="img" '
    'aria-labelledby="t d"><title id="t">A title</title><desc id="d">A description</desc>'
    '<rect x="0" y="0" width="10" height="10" fill="#FFFFFF"/></svg>'
)


# ---- tokens --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode", MODES)
def test_text_colours_meet_wcag_aa_on_both_surfaces(mode):
    b = BASE[mode]
    for fg in (b["text"], b["muted"]):
        for bg in (b["bg"], b["surface"]):
            assert contrast(fg, bg) >= 4.5, (mode, fg, bg)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("accent", ["#3B82F6", "#FFFFFF", "#000000", "#FFFF00", "#0D1117", "#F6F8FA", "#7F7F7F"])
def test_any_accent_is_nudged_until_it_is_legible(mode, accent):
    t = Theme(mode, accent)
    for bg in (t.bg, t.surface):
        assert contrast(t.accent, bg) >= 3.0, (mode, accent, "graphics")
        assert contrast(t.accent_text, bg) >= 4.5, (mode, accent, "small text")


def test_default_accent_is_kept_where_it_already_passes():
    assert Theme("dark", "#3B82F6").accent == "#3B82F6"   # 5:1 on the dark surface: untouched
    assert Theme("light", "#3B82F6").accent == "#3B82F6"  # 3.5:1 on the light surface: fine for fills and big numbers
    assert Theme("light", "#3B82F6").accent_text != "#3B82F6"  # but small accent text is darkened to pass 4.5:1


def test_light_and_dark_palettes_differ_and_unknown_mode_is_rejected():
    assert Theme("light").bg != Theme("dark").bg and Theme("light").text != Theme("dark").text
    with pytest.raises(ValueError):
        Theme("sepia")


def test_mix_endpoints_and_registration():
    assert mix("#000000", "#FFFFFF", 0) == "#000000" and mix("#000000", "#FFFFFF", 1) == "#FFFFFF"
    t = Theme("dark")
    c = t.mix(t.surface, t.border, 0.5)
    assert c in t.palette()


# ---- safety gate ---------------------------------------------------------------------------------------
def test_good_svg_passes():
    assert safety.validate(GOOD) == []


@pytest.mark.parametrize("snippet,expect", [
    ("<script>alert(1)</script>", "script"),
    ('<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">x</div></foreignObject>', "foreignobject"),
    ("<style>rect{fill:red}</style>", "style"),
    ('<image href="https://evil/x.png" width="1" height="1"/>', "image"),
    ('<use href="#a"/>', "use"),
    ('<a href="https://evil"><rect width="1" height="1"/></a>', "<a>"),
    ('<animate attributeName="x" from="0" to="1" dur="1s"/>', "animate"),
    ('<set attributeName="x" to="1"/>', "set"),
    ('<rect width="1" height="1" onclick="alert(1)"/>', "event handler"),
    ('<rect width="1" height="1" onload="alert(1)"/>', "event handler"),
    ('<rect width="1" height="1" fill="url(https://evil/x)"/>', "external url"),
    ('<rect width="1" height="1" fill="url(//evil/x)"/>', "external url"),
    ('<text x="0" y="0" font-family="javascript:alert(1)">x</text>', "script/data"),
    ('<rect width="1" height="1" data-x="data:text/html,x"/>', "script/data"),
    ('<rect width="1" height="1" data-x="https://evil"/>', "external reference"),
])
def test_unsafe_constructs_are_rejected(snippet, expect):
    svg = GOOD.replace("</svg>", snippet + "</svg>")
    problems = " | ".join(safety.validate(svg)).lower()
    assert problems and expect.lower() in problems, problems


def test_internal_references_are_allowed():
    svg = GOOD.replace("</svg>", '<defs><clipPath id="c"><rect width="5" height="5"/></clipPath></defs><g clip-path="url(#c)"><rect width="9" height="9"/></g></svg>')
    assert safety.validate(svg) == []


def test_doctype_and_entities_are_never_parsed():
    bomb = '<!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>' + GOOD
    problems = safety.validate(bomb)
    assert any("DOCTYPE" in p for p in problems)


def test_oversize_and_malformed_and_wrong_root():
    assert any("larger" in p for p in safety.validate(GOOD.replace("</svg>", "<!--" + "x" * 60_000 + "--></svg>")))
    assert any("well-formed" in p for p in safety.validate("<svg><rect></svg>"))
    assert any("root element" in p for p in safety.validate('<html xmlns="http://www.w3.org/1999/xhtml"/>'))


@pytest.mark.parametrize("mutation,expect", [
    (lambda s: s.replace(' role="img"', ""), 'role="img"'),
    (lambda s: s.replace(' aria-labelledby="t d"', ""), "aria-labelledby"),
    (lambda s: s.replace('<title id="t">A title</title>', ""), "<title>"),
    (lambda s: s.replace("<desc id=\"d\">A description</desc>", ""), "<desc>"),
    (lambda s: s.replace(">A title<", "> <"), "<title>"),
    (lambda s: s.replace(' viewBox="0 0 432 60"', ""), "viewBox"),
])
def test_accessibility_requirements_are_enforced(mutation, expect):
    problems = " ".join(safety.validate(mutation(GOOD)))
    assert expect in problems, problems
