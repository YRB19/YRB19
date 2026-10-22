"""Monthly history chart: shown only when the data supports it, honest about partial months, safe, themed, mobile-legible.
Data is SYNTHETIC and lives in tmp dirs."""
import datetime as dt
import re
from types import SimpleNamespace

import pytest

from profileos.generators import models
from profileos.generators.svg import bars, safety
from profileos.generators.svg.base import MIN_FONT, PAD, W, text_width
from profileos.generators.svg.tokens import MODES, Theme

from test_svg_components import texts


def ctx_with(months, cfg=None):
    return SimpleNamespace(cfg={"snapshots": cfg or {}}, history=SimpleNamespace(monthly=months, timeline=None))


def mrec(month, commits, complete=True):
    return {"month": month, "coverage": {"complete": complete}, "metrics": {"commits": {"value": commits}}}


def asset(model):
    meta = {"name": "monthly", "title": bars.title(model), "alt": bars.alt(model)}
    return {mode: bars.render(model, Theme(mode), meta) for mode in MODES}, meta["alt"]


def test_no_chart_without_enough_history():
    assert models.monthly_model(ctx_with([])) is None
    assert models.monthly_model(ctx_with([mrec("2026-10", 5)])) is None                  # one month is not a trend
    assert models.monthly_model(SimpleNamespace(cfg={}, history=None)) is None


def test_rows_are_chronological_summed_values_and_partial_months_are_starred():
    m = models.monthly_model(ctx_with([mrec("2026-08", 40), mrec("2026-09", 0), mrec("2026-10", 12, complete=False)]))
    assert [r["label"] for r in m["rows"]] == ["Aug 26", "Sep 26", "Oct 26*"]
    assert [r["value"] for r in m["rows"]] == [40, 0, 12]                                # a recorded zero stays zero; it is data, not a gap
    assert "partial month" in m["note"] and "not a quality measure" in m["note"] and "summed from daily snapshots" in m["note"]
    assert m["title"] == "Commits by month" and m["window"] == "Last 3 months"


def test_complete_months_carry_no_partial_footnote():
    m = models.monthly_model(ctx_with([mrec("2026-08", 4), mrec("2026-09", 5)]))
    assert "partial" not in m["note"] and not any(r["label"].endswith("*") for r in m["rows"])


def test_chart_months_limit_is_respected():
    months = [mrec(f"2026-{i:02d}", i) for i in range(1, 11)]
    assert len(models.monthly_model(ctx_with(months, {"chart_months": 4}))["rows"]) == 4


@pytest.mark.parametrize("mode", MODES)
def test_svg_is_safe_accessible_and_scope_is_stated(mode):
    svgs, alt = asset(models.monthly_model(ctx_with([mrec("2026-08", 40), mrec("2026-09", 10), mrec("2026-10", 12, complete=False)])))
    svg = svgs[mode]
    assert safety.validate(svg) == [] and 'role="img"' in svg and "<title" in svg and "<desc" in svg
    assert "Commits by month" in alt and "Oct 26*" in alt and "partial month" in alt
    for t in texts(svg):
        assert t["size"] >= MIN_FONT                                                      # phone floor
        width = text_width(t["s"], t["size"], bold=t["bold"], tracking=t["track"])
        left = {"start": t["x"], "end": t["x"] - width, "middle": t["x"] - width / 2}[t["anchor"]]
        assert left >= 4 and left + width <= W - 4, (t["s"], round(left), round(left + width))


def test_light_and_dark_variants_differ_and_stay_in_palette():
    model = models.monthly_model(ctx_with([mrec("2026-08", 4), mrec("2026-09", 9)]))
    themes = {mode: Theme(mode) for mode in MODES}
    meta = {"name": "monthly", "title": bars.title(model), "alt": bars.alt(model)}
    svgs = {mode: bars.render(model, themes[mode], meta) for mode in MODES}
    assert svgs["light"] != svgs["dark"]
    for mode in MODES:
        allowed = {c.upper() for c in themes[mode].palette()}               # includes the mixes derived while rendering
        used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", svgs[mode])}
        assert used <= allowed, used - allowed


def test_hostile_values_cannot_inject_markup():
    m = models.monthly_model(ctx_with([mrec("2026-08", 4), mrec("2026-09", 9)]))
    m["title"] = '<script>alert(1)</script>"&'
    svgs, alt = asset(m)
    for svg in svgs.values():
        assert "<script" not in svg and safety.validate(svg) == []


def test_chart_appears_in_a_real_build_once_two_months_exist(repo_copy):
    import json
    from profileos.build import build
    from profileos.github.fixtures import FixtureClient
    from test_history import NOW, record, store, rollup, snapshot
    store(repo_copy, record("2026-08-02"), record("2026-09-02"))
    now = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)
    res = build(repo_copy, client=FixtureClient(now), now=now)
    # the fixture-built records are not real history; this only checks the chart plumbing with two stored months
    assert "monthly" in res.asset_objects and "Commits by month" in res.asset_objects["monthly"].alt
    assert "assets/generated/monthly.light.svg" in res.blocks["ACTIVITY"]
