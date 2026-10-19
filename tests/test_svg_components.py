"""Every SVG component: rendering, light/dark variants, graceful missing data, hostile text, mobile bounds, alt text."""
import datetime as dt
import re
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from profileos.generators import models, visuals
from profileos.generators.svg import badges, bars, cards, ecosystem, heatmap, langbar, pulse, safety
from profileos.generators.svg.base import MIN_FONT, PAD, W, text_width
from profileos.generators.svg.tokens import MODES, Theme

SVGNS = "{http://www.w3.org/2000/svg}"
NOW = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)
THEMES = {m: Theme(m) for m in MODES}

CARD_FULL = {
    "slug": "demo", "title": "Demo", "url": "https://github.com/YRB19/Demo", "status": "active",
    "tagline": "A tagline that is long enough that it has to wrap onto a second line on a phone",
    "stack": ["FastAPI", "PostgreSQL", "React", "Docker"], "release": {"tag": "v1.0", "url": "https://x"},
    "stars": 3, "forks": 1, "last_push": "2026-09-01", "demo": None, "docs": None,
}
CARD_MIN = {k: None for k in CARD_FULL} | {"slug": "demo", "title": "Demo", "url": "u", "stack": []}
PULSE = {"window": "Last 30 days", "note": "Activity indicators, not measures of quality.", "tiles": [
    {"label": "Commits", "noun": ("commit", "commits"), "value": 47},
    {"label": "Repos committed to", "noun": ("repository committed to", "repositories committed to"), "value": 6},
    {"label": "Pull requests", "noun": ("pull request", "pull requests"), "value": 0},
]}
BARS = {"window": "Last 30 days", "note": "n", "rows": [
    {"slug": "a", "label": "UsageOS", "value": 38}, {"slug": "b", "label": "ResearchOS", "value": 22}, {"slug": "c", "label": "ClipOS", "value": 3}]}
LANGS = {"note": "By bytes of code. Not a skill measure.", "items": [
    {"language": "Python", "pct": 57.1}, {"language": "Rust", "pct": 19.6}, {"language": "Other", "pct": 23.3}]}
ECO = {"nodes": [{"slug": s, "label": s, "category": c} for s, c in
                 (("UsageOS", "DEVTOOLS"), ("ResearchOS", "AI"), ("ClipOS", "MEDIA"), ("CompanionOS", "SYSTEMS"))], "edges": []}


def asset(name, mod, model):
    return visuals._make(name, mod, model, THEMES)  # renders both modes and runs the safety gate


HEAT = models.heatmap_model(SimpleNamespace(ds={"contributions": {"calendar": {"total": 120, "days": [
    {"date": (dt.date(2026, 1, 4) + dt.timedelta(days=i)).isoformat(), "count": (i * 3) % 7} for i in range(270)]}}}))
SPECS = {  # name -> (module, view-model)
    "card-demo": (cards, CARD_FULL), "card-min": (cards, CARD_MIN), "pulse": (pulse, PULSE), "activity": (bars, BARS),
    "languages": (langbar, LANGS), "os-series": (ecosystem, ECO), "heatmap": (heatmap, HEAT),
}


def all_assets():
    return [asset(n, mod, model) for n, (mod, model) in SPECS.items()]


def texts(svg):
    out = []
    for t in ET.fromstring(svg).iter(SVGNS + "text"):
        out.append(dict(x=float(t.get("x")), size=float(t.get("font-size")), anchor=t.get("text-anchor", "start"),
                        s="".join(t.itertext()), bold=t.get("font-weight") == "600", track=float(t.get("letter-spacing", 0))))
    return out


# ---- rendering, determinism, themes ----------------------------------------------------------------------
@pytest.mark.parametrize("name", SPECS)
def test_renders_valid_deterministic_svg_in_both_modes(name):
    mod, model = SPECS[name]
    first, second = asset(name, mod, model), asset(name, mod, model)
    assert set(first.svg) == {"light", "dark"}
    for svg in first.svg.values():
        assert safety.validate(svg) == [] and svg.startswith("<svg") and f'viewBox="0 0 {W} ' in svg
    assert first.svg == second.svg  # byte-identical on re-render: no timestamps, random ids or set ordering


@pytest.mark.parametrize("a", all_assets(), ids=lambda a: a.name)
def test_light_and_dark_variants_use_their_own_surfaces(a):
    light, dark = a.svg["light"], a.svg["dark"]
    assert THEMES["light"].surface in light and THEMES["dark"].surface in dark
    assert THEMES["dark"].surface not in light and THEMES["light"].surface not in dark
    assert light != dark


@pytest.mark.parametrize("name", SPECS)
@pytest.mark.parametrize("mode", MODES)
def test_every_colour_comes_from_the_token_palette(name, mode):
    mod, model = SPECS[name]
    theme = Theme(mode)
    title = mod.title(model) if hasattr(mod, "title") else mod.TITLE
    svg = mod.render(model, theme, {"name": name, "title": title, "alt": mod.alt(model)})
    palette = {c.upper() for c in theme.palette()}  # read AFTER rendering: derived tints register themselves
    seen = set()
    for el in ET.fromstring(svg).iter():
        for attr in ("fill", "stroke"):
            v = el.get(attr)
            if v and v != "none":
                seen.add(v.upper())
                assert v.upper() in palette, (name, mode, attr, v)
    assert len(seen) >= 2  # the check is looking at real colours, not an empty set


# ---- missing data is omitted, never faked ----------------------------------------------------------------
def test_minimal_card_collapses_without_placeholders():
    a = asset("card-min", cards, CARD_MIN)
    svg = a.svg["light"]
    assert [t["s"] for t in texts(svg)] == ["Demo"]
    assert "ACTIVE" not in svg and "None" not in svg and "null" not in svg.lower() and "undefined" not in svg
    assert a.alt == "Demo."
    full = asset("card-demo", cards, CARD_FULL)
    h = lambda s: float(re.search(r'height="([\d.]+)"', s).group(1))  # noqa: E731
    assert h(svg) < h(full.svg["light"])  # collapses instead of leaving blank rows


@pytest.mark.parametrize("drop", ["tagline", "stack", "release", "last_push", "stars", "forks", "status"])
def test_each_optional_card_field_can_be_absent(drop):
    m = dict(CARD_FULL)
    m[drop] = [] if drop == "stack" else None
    a = asset("card-demo", cards, m)
    body = " ".join(t["s"] for t in texts(a.svg["dark"]))
    probe = {"tagline": "tagline", "stack": "FastAPI", "release": "v1.0", "last_push": "2026-09-01", "stars": "star",
             "forks": "fork", "status": "ACTIVE"}[drop]
    assert probe not in body and probe not in a.alt


def test_zero_stars_are_hidden_but_real_counts_show():
    assert "star" not in " ".join(t["s"] for t in texts(asset("c", cards, CARD_FULL | {"stars": None, "forks": None}).svg["light"]))
    assert "3 stars" in " ".join(t["s"] for t in texts(asset("c", cards, CARD_FULL).svg["light"]))
    assert "1 star" in " ".join(t["s"] for t in texts(asset("c", cards, CARD_FULL | {"stars": 1}).svg["light"]))


def test_unknown_status_is_not_drawn_at_all():
    a = asset("card-demo", cards, CARD_FULL | {"status": "running"})
    assert "RUNNING" not in a.svg["light"].upper() and "Status" not in a.alt
    assert badges.badge(THEMES["light"], "running", 400, 30) == ("", 0.0)


@pytest.mark.parametrize("status", ["active", "experimental", "maintained", "paused", "archived"])
def test_every_status_badge_renders_with_label_and_glyph(status):
    for mode in MODES:
        markup, w = badges.badge(Theme(mode), status, 412, 33)
        assert status.upper() in markup and w > 60 and ("circle" in markup or "<rect" in markup)
        assert 412 - w >= PAD  # never pushes past the left padding


def test_pulse_without_release_data_has_no_release_tile():
    ctx = SimpleNamespace(ds={"contributions": {"pulse": {"commits": 4, "repos_touched": 2, "pull_requests": 0, "reviews": 0, "issues": 0}}},
                          repos=[], releases={}, now=NOW)
    m = models.pulse_model(ctx)
    assert [t["label"] for t in m["tiles"]] == ["Commits", "Repos committed to", "Pull requests"]
    svg = asset("pulse", pulse, m).svg["light"]
    assert "Releases" not in svg and ">0<" in svg  # a measured zero is shown; an unmeasured metric is not invented
    assert models.pulse_model(SimpleNamespace(ds={}, repos=[], releases={}, now=NOW)) is None


def test_pulse_alt_text_pluralises_and_carries_the_numbers():
    m = {**PULSE, "tiles": [{"label": "Commits", "noun": ("commit", "commits"), "value": 1}, PULSE["tiles"][2]]}
    alt = asset("pulse", pulse, m).alt
    assert "1 commit," in alt and "0 pull requests" in alt and "Last 30 days".lower() in alt.lower()


def test_activity_bars_zero_rows_have_no_fill_and_long_labels_truncate():
    m = {**BARS, "rows": [{"slug": "a", "label": "A" * 60, "value": 10}, {"slug": "b", "label": "B", "value": 0}]}
    svg = asset("activity", bars, m).svg["light"]
    labels = [t["s"] for t in texts(svg)]
    assert any(s.endswith("…") for s in labels) and "B" in labels
    one = asset("activity", bars, {**BARS, "rows": [BARS["rows"][0]]})
    assert "38" in one.svg["light"]


def test_language_bar_single_item_and_alt_percentages():
    a = asset("languages", langbar, {**LANGS, "items": [{"language": "Python", "pct": 100.0}]})
    assert "Python 100.0%" in a.alt and "100.0%" in a.svg["dark"]
    assert models.language_model(SimpleNamespace(repos=[], cfg={}, ov={})) is None


def test_language_model_folds_the_tail_into_other():
    repos = [{"full_name": f"o/r{i}", "is_private": False, "is_fork": False, "is_archived": False,
              "languages": {f"L{j}": 1000 - j * 40 for j in range(9)}} for i in range(1)]
    m = models.language_model(SimpleNamespace(repos=repos, cfg={"min_language_pct": 0}, ov={}))
    assert len(m["items"]) == models.MAX_LANGUAGES + 1 and m["items"][-1]["language"] == "Other"
    assert abs(sum(i["pct"] for i in m["items"]) - 100) < 0.6


# ---- heatmap -----------------------------------------------------------------------------------------------
def _heat(days):
    return models.heatmap_model(SimpleNamespace(ds={"contributions": {"calendar": {"total": sum(c for _, c in days), "days": [
        {"date": d, "count": c} for d, c in days]}}}))


def test_heatmap_all_zero_year_is_honest_and_valid():
    days = [((dt.date(2026, 1, 4) + dt.timedelta(days=i)).isoformat(), 0) for i in range(120)]
    m = _heat(days)
    assert {c["level"] for c in m["cells"]} == {0} and m["active_days"] == 0
    a = asset("heatmap", heatmap, m)
    assert "0 contributions" in a.svg["light"] and "0 active days" in a.alt


def test_heatmap_single_day_and_missing_calendar():
    m = _heat([("2026-03-04", 5)])
    assert m["ncols"] == 1 and m["cells"][0]["level"] == 4
    asset("heatmap", heatmap, m)
    assert models.heatmap_model(SimpleNamespace(ds={})) is None
    assert models.heatmap_model(SimpleNamespace(ds={"contributions": {"calendar": {"days": []}}})) is None


def test_heatmap_levels_scale_to_the_busiest_day_and_months_do_not_collide():
    days = [((dt.date(2025, 10, 5) + dt.timedelta(days=i)).isoformat(), i % 9) for i in range(364)]
    m = _heat(days)
    assert {c["level"] for c in m["cells"]} == {0, 1, 2, 3, 4}
    cols = [mo["col"] for mo in m["months"]]
    assert cols == sorted(cols) and all(b - a >= 4 for a, b in zip(cols, cols[1:]))
    svg = asset("heatmap", heatmap, m).svg["light"]
    xs = sorted((t["x"], t["x"] + text_width(t["s"], 16)) for t in texts(svg) if t["s"] in {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"})
    assert all(b[0] >= a[1] + 3 for a, b in zip(xs, xs[1:]))


# ---- ecosystem graph ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("n", range(1, 9))
def test_ecosystem_layout_never_overlaps_and_stays_in_canvas(n):
    pts, height = ecosystem.layout(n)
    rects = [(x - ecosystem.PILL_W / 2, y - ecosystem.PILL_H / 2, x + ecosystem.PILL_W / 2, y + ecosystem.PILL_H / 2) for x, y in pts]
    for r in rects:
        assert r[0] >= 8 and r[2] <= W - 8 and r[1] >= 50 and r[3] <= height
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_ecosystem_has_edges_only_when_declared_and_labels_go_in_a_legend():
    plain = asset("os-series", ecosystem, ECO).svg["light"]
    assert "marker-end" not in plain  # no declared relationships => no arrows
    m = ECO | {"edges": [{"from": "UsageOS", "to": "ResearchOS", "label": "feeds"}]}
    a = asset("os-series", ecosystem, m)
    assert a.svg["light"].count("marker-end") == 1
    assert "UsageOS → ResearchOS · feeds" in [t["s"] for t in texts(a.svg["light"])]
    assert "Declared relationships: UsageOS to ResearchOS (feeds)" in a.alt


def test_ecosystem_nodes_are_uniform_so_nothing_implies_rank():
    svg = asset("os-series", ecosystem, ECO).svg["light"]
    pills = [r for r in ET.fromstring(svg).iter(SVGNS + "rect") if r.get("stroke") == THEMES["light"].accent]
    assert len(pills) == 4 and len({(r.get("width"), r.get("height"), r.get("stroke-width")) for r in pills}) == 1


# ---- hostile text --------------------------------------------------------------------------------------------
HOSTILE = '<script>alert(1)</script> "quoted" & \'single\' ]]> <!-- c --> \x00\x1b[31m'


@pytest.mark.parametrize("field", ["title", "tagline"])
def test_hostile_card_text_is_escaped_and_the_svg_stays_valid(field):
    a = asset("card-demo", cards, CARD_FULL | {field: HOSTILE})
    for svg in a.svg.values():
        assert safety.validate(svg) == [] and "<script" not in svg and "\x00" not in svg and "\x1b" not in svg
        root = ET.fromstring(svg)  # still well-formed XML
        assert not [e for e in root.iter() if e.tag.rsplit("}", 1)[-1] in ("script", "foreignObject", "style")]
        # the hostile string survives only as inert text content inside a <text> node
        assert any("<script>alert(1)</script>" in "".join(t.itertext()) for t in root.iter(SVGNS + "text"))


def test_hostile_language_and_node_labels():
    asset("languages", langbar, {**LANGS, "items": [{"language": HOSTILE, "pct": 100.0}]})
    asset("os-series", ecosystem, {"nodes": [{"slug": "a", "label": HOSTILE, "category": HOSTILE}, {"slug": "b", "label": "B", "category": ""}], "edges": []})


# ---- mobile readability ---------------------------------------------------------------------------------------
def test_phone_scale_keeps_the_smallest_font_at_least_12px():
    assert MIN_FONT * 328 / W >= 12  # 360px phone: 328px of README content width


def assert_fits(a):
    """Every text >= the font floor and (by a conservative width estimate) inside the canvas, in both modes."""
    for mode, svg in a.svg.items():
        for t in texts(svg):
            assert t["size"] >= MIN_FONT, (a.name, mode, t)
            width = text_width(t["s"], t["size"], bold=t["bold"], tracking=t["track"])
            left = {"start": t["x"], "end": t["x"] - width, "middle": t["x"] - width / 2}[t["anchor"]]
            assert left >= 4 and left + width <= W - 4, (a.name, mode, t["s"], round(left), round(left + width))


@pytest.mark.parametrize("a", all_assets(), ids=lambda a: a.name)
def test_fonts_are_never_below_the_floor_and_text_fits_the_canvas(a):
    assert_fits(a)


LONG = "Extraordinarily-long-project-name-that-cannot-possibly-fit-on-one-line-of-a-phone"
STRESS = {
    "card: long everything": (cards, CARD_FULL | {"title": LONG, "tagline": " ".join([LONG] * 5), "stack": [LONG, "A", "B", "C"],
                                                  "release": {"tag": LONG, "url": "x"}, "stars": 1234567, "forks": 7654321}),
    "card: long title, no status": (cards, CARD_MIN | {"title": LONG}),
    "card: unbroken tagline": (cards, CARD_FULL | {"tagline": "x" * 300}),
    "card: wide caps and digits": (cards, CARD_FULL | {"title": "WWWWWWWWWWWWWWWWWWWW", "stack": ["MMMMMMMMMM", "WWWWWWWWWW"]}),
    "pulse: huge numbers": (pulse, PULSE | {"tiles": [{"label": "Commits", "noun": ("c", "c"), "value": 123456789},
                                                      {"label": "Repos committed to", "noun": ("r", "r"), "value": 99999999},
                                                      {"label": "Pull requests", "noun": ("p", "p"), "value": 88888888},
                                                      {"label": "Releases", "noun": ("x", "x"), "value": 77777777}]}),
    "bars: huge values, long labels": (bars, BARS | {"rows": [{"slug": str(i), "label": LONG, "value": 10 ** (i + 3)} for i in range(6)]}),
    "langs: long names, many items": (langbar, LANGS | {"items": [{"language": LONG, "pct": 100 / 7} for _ in range(7)]}),
    "eco: six long nodes": (ecosystem, {"nodes": [{"slug": f"n{i}", "label": LONG, "category": LONG} for i in range(6)], "edges": []}),
    "eco: labelled edges": (ecosystem, {"nodes": [{"slug": f"n{i}", "label": f"Node{i}", "category": "AI"} for i in range(4)],
                                        "edges": [{"from": "n0", "to": "n1", "label": LONG}, {"from": "n2", "to": "n3", "label": "x"}]}),
}


@pytest.mark.parametrize("case", STRESS)
def test_long_text_and_huge_numbers_are_truncated_never_overflowing(case):
    mod, model = STRESS[case]
    assert_fits(asset("stress", mod, model))


def test_heatmap_with_a_huge_total_still_fits():
    m = HEAT | {"total": 123456789}
    assert_fits(asset("heatmap", heatmap, m))


def test_canvas_is_fixed_width_so_github_scales_every_asset_identically():
    for a in all_assets():
        for svg in a.svg.values():
            root = ET.fromstring(svg)
            assert root.get("width") == str(W) and root.get("viewBox").split()[2] == str(W)


# ---- accessibility ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("a", all_assets(), ids=lambda a: a.name)
def test_every_asset_has_title_desc_and_matching_alt(a):
    assert a.title.strip() and a.alt.strip() and "<" not in a.alt
    for svg in a.svg.values():
        root = ET.fromstring(svg)
        assert root.get("role") == "img"
        ids = {e.get("id") for e in root if e.get("id")}
        assert set(root.get("aria-labelledby").split()) <= ids
        assert root.find(SVGNS + "title").text == a.title
        assert root.find(SVGNS + "desc").text.strip() == a.alt.strip()


def test_alt_text_carries_the_key_data():
    assert "FastAPI, PostgreSQL, React, Docker" in cards.alt(CARD_FULL) and "Status: active" in cards.alt(CARD_FULL)
    assert "Release v1.0" in cards.alt(CARD_FULL) and "Last push 2026-09-01" in cards.alt(CARD_FULL)
    assert "UsageOS 38" in bars.alt(BARS) and "Python 57.1%" in langbar.alt(LANGS)
    assert "UsageOS (DEVTOOLS)" in ecosystem.alt(ECO)


def test_picture_markup_is_accessible_and_escapes_alt():
    a = asset("card-demo", cards, CARD_FULL | {"tagline": 'He said "hi" <b>'})
    html = visuals.picture(a)
    assert 'prefers-color-scheme: dark' in html and a.name + ".dark.svg" in html and a.name + ".light.svg" in html
    assert re.search(r'<img alt="[^"]+" src="assets/generated/card-demo.light.svg" width="432">', html)
    assert "<b>" not in html and "&lt;b&gt;" in html and "&quot;hi&quot;" in html
