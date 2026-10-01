import pytest

from profileos.generators.markers import MarkerError, check_markers, replace_blocks

S, E = "<!-- PROFILEOS:START:{} -->", "<!-- PROFILEOS:END:{} -->"


def doc(*ids, body="old"):
    return "hand-written\n" + "\n".join(f"{S.format(i)}\n{body}\n{E.format(i)}" for i in ids) + "\ntail\n"


def test_replaces_only_inside_markers():
    out, _ = replace_blocks(doc("PULSE", "NOW"), {"PULSE": "new"})
    assert "new" in out and out.startswith("hand-written\n") and out.endswith("tail\n")
    assert out.count("old") == 1  # NOW untouched


def test_missing_marker_fails():
    with pytest.raises(MarkerError):
        replace_blocks("no markers", {"PULSE": "x"})


def test_duplicate_marker_fails():
    with pytest.raises(MarkerError):
        replace_blocks(doc("PULSE") + doc("PULSE"), {"PULSE": "x"})


def test_end_before_start_fails():
    bad = E.format("PULSE") + "\n" + S.format("PULSE")
    with pytest.raises(MarkerError):
        replace_blocks(bad, {"PULSE": "x"})


def test_unregistered_marker_warns_and_is_untouched():
    text = doc("PULSE", "MYSTERY")
    errors, warnings = check_markers(text, required=["PULSE"])
    assert not errors and any("MYSTERY" in w for w in warnings)
    out, _ = replace_blocks(text, {"PULSE": "x"})
    assert out.count("old") == 1


def test_idempotent():
    once, _ = replace_blocks(doc("PULSE"), {"PULSE": "same"})
    twice, _ = replace_blocks(once, {"PULSE": "same"})
    assert once == twice


def test_empty_block_and_crlf():
    out, _ = replace_blocks(doc("PULSE"), {"PULSE": ""})
    assert f"{S.format('PULSE')}\n{E.format('PULSE')}" in out
    out, _ = replace_blocks(doc("PULSE"), {"PULSE": "a\r\nb"})
    assert "\r" not in out
