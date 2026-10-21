"""Phase 5 end to end: assets are built from the same data as the README, written safely, and publish only what is supported."""
import datetime as dt
import json
import re
from pathlib import Path

import pytest
import yaml

from conftest import NOW, ROOT
from profileos.build import BuildError, build
from profileos.generators import models, visuals
from profileos.generators.svg import safety
from profileos.github.fixtures import FixtureClient
from test_build import Failing, Patched, assert_readme_inert

ASSETS = "assets/generated"
EXPECTED = {"pulse", "activity", "heatmap", "languages", "os-series",
            "card-usageos", "card-researchos", "card-clipos", "card-companionos"}


def names(root):
    return {p.name.rsplit(".", 2)[0] for p in (root / ASSETS).glob("*.svg")}


def readme(root):
    return (root / "README.md").read_text(encoding="utf-8")


def block(text, sid):
    return text.split(f"<!-- PROFILEOS:START:{sid} -->")[1].split(f"<!-- PROFILEOS:END:{sid} -->")[0].strip()


def visible_text(svg):
    import xml.etree.ElementTree as ET
    return " ".join("".join(t.itertext()) for t in ET.fromstring(svg).iter("{http://www.w3.org/2000/svg}text"))


def edit_yaml(root, name, fn):
    p = root / "data" / f"{name}.yml"
    d = yaml.safe_load(p.read_text())
    fn(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))


@pytest.fixture
def built(repo_copy):
    (repo_copy / ASSETS).mkdir(parents=True, exist_ok=True)
    res = build(repo_copy, client=FixtureClient(NOW), now=NOW)
    return repo_copy, res


# ---- what gets built --------------------------------------------------------------------------------------------
def test_expected_assets_exist_in_both_modes(built):
    root, res = built
    assert names(root) == EXPECTED
    for n in EXPECTED:
        for mode in ("light", "dark"):
            svg = (root / ASSETS / f"{n}.{mode}.svg").read_text()
            assert safety.validate(svg) == []
    assert set(res.assets) == {f"{ASSETS}/{n}.{m}.svg" for n in EXPECTED for m in ("light", "dark")}


def test_readme_references_exactly_the_assets_that_exist(built):
    root, _ = built
    text = readme(root)
    refs = set(re.findall(r'(?:src|srcset)="(assets/generated/[^"]+\.svg)"', text))
    assert refs and all((root / r).exists() for r in refs)
    assert {Path(r).name.rsplit(".", 2)[0] for r in refs} == EXPECTED  # nothing orphaned, nothing dangling
    assert_readme_inert(text)


def test_every_readme_image_has_alt_text_that_matches_the_asset(built):
    root, res = built
    text = readme(root)
    imgs = re.findall(r'<img alt="([^"]*)" src="(assets/generated/[^"]+)" width="(\d+)">', text)
    assert len(imgs) == len(EXPECTED)
    for alt, src, width in imgs:
        assert alt.strip() and width == "432"
        import html as h
        assert h.unescape(alt) == res.asset_objects[Path(src).name.rsplit(".", 2)[0]].alt


def test_picture_uses_light_and_dark_sources_for_every_asset(built):
    root, _ = built
    text = readme(root)
    for n in EXPECTED:
        assert f'srcset="assets/generated/{n}.dark.svg"' in text and f'srcset="assets/generated/{n}.light.svg"' in text
    assert text.count('media="(prefers-color-scheme: dark)"') == len(EXPECTED)


def test_manual_prose_outside_markers_is_untouched(built):
    root, _ = built
    before, after = (ROOT / "README.md").read_text(), readme(root)
    for line in ("# Rishit Babbar", "### CS + AI Student · Systems Builder", "## What I Build", "## Engineering Approach",
                 "The goal isn't to generate more code.", "I use AI throughout the engineering loop"):
        assert line in before and line in after


# ---- same metadata everywhere ---------------------------------------------------------------------------------
def test_cards_and_markdown_share_one_source_of_truth(built):
    root, res = built
    svg = res.assets[f"{ASSETS}/card-usageos.light.svg"]
    assert "Self-hosted multi-account Claude.ai usage tracking platform" in svg
    assert "FastAPI" in svg and "PostgreSQL" in svg
    alt = res.asset_objects["card-usageos"].alt
    assert "Self-hosted multi-account Claude.ai usage tracking platform" in alt
    assert "UsageOS" in res.blocks["OS_SERIES"] and "UsageOS" in res.asset_objects["os-series"].alt


# ---- idempotence, dry run, stale files ----------------------------------------------------------------------
def test_second_run_changes_nothing(built):
    root, _ = built
    snap = {p.name: p.read_bytes() for p in (root / ASSETS).iterdir()}
    mtimes = {p.name: p.stat().st_mtime_ns for p in (root / ASSETS).iterdir()}
    res = build(root, client=FixtureClient(NOW), now=NOW + dt.timedelta(hours=6))
    assert res.asset_changes == [] and not res.changed
    assert {p.name: p.read_bytes() for p in (root / ASSETS).iterdir()} == snap
    assert {p.name: p.stat().st_mtime_ns for p in (root / ASSETS).iterdir()} == mtimes  # not even rewritten


def test_dry_run_writes_no_assets(repo_copy):
    (repo_copy / ASSETS).mkdir(parents=True, exist_ok=True)
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    assert res.assets and list((repo_copy / ASSETS).glob("*.svg")) == []


def test_stale_generated_assets_are_removed_and_unrelated_files_are_not(built):
    root, _ = built
    keep = {".gitkeep": "", "notes.txt": "mine", "custom.svg": "<svg/>", "Logo.light.svg": "x", "x.light.svg.bak": "y"}
    for k, v in keep.items():
        (root / ASSETS / k).write_text(v)
    edit_yaml(root, "projects", lambda d: d["ClipOS"].update(publish=False))
    res = build(root, client=FixtureClient(NOW), now=NOW + dt.timedelta(hours=1))
    assert "card-clipos" not in names(root)
    assert any("card-clipos.light.svg" in c for c in res.asset_changes)
    for k in keep:
        assert (root / ASSETS / k).exists(), k


def test_unsafe_svg_aborts_before_anything_is_written(repo_copy, monkeypatch):
    (repo_copy / ASSETS).mkdir(parents=True, exist_ok=True)
    before = readme(repo_copy)
    monkeypatch.setattr(safety, "MAX_BYTES", 200)  # every real asset now "fails" the gate
    with pytest.raises(BuildError, match="nothing was written"):
        build(repo_copy, client=FixtureClient(NOW), now=NOW)
    assert readme(repo_copy) == before
    assert list((repo_copy / ASSETS).glob("*.svg")) == []
    assert list((repo_copy / "data" / "cache").glob("*.json")) == []  # not even the data cache


# ---- publishing rules ------------------------------------------------------------------------------------------
def test_netos_and_freya_are_absent_from_every_public_output(built):
    root, res = built
    blobs = [readme(root), *res.assets.values(), *[a.alt + a.title for a in res.asset_objects.values()],
             *[p.read_text() for p in (root / ASSETS).glob("*.svg")]]
    for blob in blobs:
        assert "NetOS" not in blob and "FREYA" not in blob
    assert [n["label"] for n in models.ecosystem_model(_ctx(root))["nodes"]] == ["UsageOS", "ResearchOS", "ClipOS", "CompanionOS"]


def _ctx(root, now=NOW):
    from test_build import _ctx as c
    return c(root, now=now)


def test_internal_projects_stay_in_the_data_files(repo_copy):
    d = yaml.safe_load((repo_copy / "data" / "projects.yml").read_text())
    assert d["NetOS"]["publish"] is False and d["FREYA"]["publish"] is False
    assert "publish" not in d["UsageOS"]


def test_publishing_is_a_single_explicit_switch(repo_copy):
    edit_yaml(repo_copy, "projects", lambda d: d["NetOS"].update(publish=True))
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    assert "card-netos" in res.asset_objects
    assert "NetOS" in res.asset_objects["os-series"].alt
    assert "FREYA" not in res.asset_objects["os-series"].alt


def test_unpublished_repo_is_excluded_from_language_totals_too(repo_copy):
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    langs = res.asset_objects["languages"].alt
    assert "C++" not in langs  # NetOS (the only C++ repo in the fixture) is internal-only


def test_status_is_shown_only_where_evidence_backs_it(built):
    root, res = built
    assert "Status: active" in res.asset_objects["card-companionos"].alt
    for n in ("card-usageos", "card-researchos", "card-clipos"):
        assert "Status" not in res.asset_objects[n].alt and "ACTIVE" not in res.assets[f"{ASSETS}/{n}.light.svg"]


def test_stack_items_without_evidence_never_appear(built):
    root, res = built
    stack = block(readme(root), "STACK")
    everything = " ".join([stack, *map(visible_text, res.assets.values()), *(a.alt for a in res.asset_objects.values())])
    assert "Python" in stack and "Rust" in stack  # the check is looking at a real, populated block
    for hidden in ("C++", "RAG", "Linux"):
        assert hidden not in everything, hidden


def test_profile_content_is_exactly_what_was_supplied(built):
    root, _ = built
    text = readme(root)
    now = block(text, "NOW")
    assert "Exploring: Agentic systems · AI infrastructure" in now and "Learning: Systems design · Distributed workflows" in now
    assert "Planning next" not in now
    assert block(text, "LINKS") == "[GitHub](https://github.com/YRB19)"


# ---- activity is a signal, never an importance ranking -----------------------------------------------------
def _boost(slug, commits):
    def tamper(nodes):
        for n in nodes:
            if n["name"] == slug:
                t = n["defaultBranchRef"]["target"]
                t["c30"]["totalCount"] = t["c7"]["totalCount"] = commits
    return tamper


def test_activity_bars_follow_curated_order_not_commit_counts(repo_copy):
    res = build(repo_copy, client=Patched(NOW, _boost("ClipOS", 500)), dry_run=True, now=NOW)
    alt = res.asset_objects["activity"].alt
    order = [alt.index(n) for n in ("UsageOS", "ResearchOS", "ClipOS")]
    assert order == sorted(order)  # ClipOS has by far the most commits but stays in its curated position
    assert "ClipOS 500" in alt


def test_most_commits_line_uses_commits_only(repo_copy):
    res = build(repo_copy, client=Patched(NOW, _boost("ResearchOS", 500)), dry_run=True, now=NOW)
    assert "Most commits (last 30 days): [ResearchOS]" in res.blocks["NOW"]  # not the higher-priority UsageOS
    assert "Most active" not in res.blocks["NOW"]


def test_flagship_card_order_ignores_activity(repo_copy):
    res = build(repo_copy, client=Patched(NOW, _boost("CompanionOS", 500)), dry_run=True, now=NOW)
    sel = res.blocks["SELECTED_SYSTEMS"]
    order = [sel.index(f"card-{n}.light") for n in ("usageos", "researchos", "clipos", "companionos")]
    assert order == sorted(order)


def test_no_quality_scores_or_rankings_are_rendered(built):
    root, res = built
    shown = " ".join([block(readme(root), "PULSE"), block(readme(root), "ACTIVITY"), *map(visible_text, res.assets.values()),
                      *(a.alt for a in res.asset_objects.values())]).lower()
    assert "activity indicators" in shown  # the framing sentence is present, so this scans real output
    for word in ("score", "rank", "grade", "top contributor", "best ", "leaderboard", "rating"):
        assert word not in shown, word


# ---- outages ------------------------------------------------------------------------------------------------
def test_api_outage_with_cache_keeps_assets_and_labels_staleness(built):
    root, _ = built
    snap = {p.name: p.read_bytes() for p in (root / ASSETS).iterdir()}
    res = build(root, client=Failing(), now=NOW + dt.timedelta(days=3))
    assert {p.name: p.read_bytes() for p in (root / ASSETS).iterdir()} == snap
    assert "as of 2026-09-30" in readme(root) and any("failed" in w for w in res.warnings)


def test_outage_with_no_cache_draws_only_what_curated_data_supports(repo_copy):
    res = build(repo_copy, client=Failing(), now=NOW)
    assert set(res.asset_objects) == {"os-series"}      # no fabricated metrics, no empty cards
    for sid in ("PULSE", "ACTIVITY", "SELECTED_SYSTEMS", "CURRENTLY_BUILDING", "RECENTLY_SHIPPED"):
        assert res.blocks[sid] == "", sid
    assert "UsageOS" in res.asset_objects["os-series"].alt


# ---- read-only guarantees ------------------------------------------------------------------------------------
def test_the_github_client_is_read_only_and_cannot_touch_pins():
    src = (ROOT / "src" / "profileos" / "github" / "queries.py").read_text().lower()
    assert "mutation" not in src and "pinitems" not in src and "pinnable" not in src
    client = (ROOT / "src" / "profileos" / "github" / "client.py").read_text()
    assert set(re.findall(r'_request\("([A-Z]+)"', client)) == {"POST", "GET"}  # POST only for the /graphql query endpoint
    assert '"POST", f"{API}/graphql"' in client


def test_verification_claims_stay_within_the_evidence():
    """Updated for the live run (the old premise, "never run live", is no longer true). The guard's purpose is unchanged:
    docs must not claim more than was evidenced. The live run is credited to what was observable, and Phase 6 stays unverified."""
    for doc in ("README_DEV.md", "PLAN.md"):
        text = " ".join((ROOT / doc).read_text().lower().split())
        assert "phase 6" in text and "not live-verified" in text.replace("**", ""), doc
        assert "actions logs" in text and "not readable" in text, doc          # run-level details are not claimed
        assert "production-verified" not in text.replace("not production-verified", ""), doc


# ---- CLI ------------------------------------------------------------------------------------------------------
def test_preview_command_writes_review_files_and_never_touches_the_repo(repo_copy, tmp_path, capsys):
    from profileos.cli import main

    (repo_copy / ASSETS).mkdir(parents=True, exist_ok=True)
    before = readme(repo_copy)
    assert main(["--root", str(repo_copy), "preview", "--fixtures", "--out", str(tmp_path / "pv")]) == 0
    html = (tmp_path / "pv" / "index.html").read_text()
    assert "SYNTHETIC ACTIVITY DATA" in html and "360px" in html
    assert len(list((tmp_path / "pv" / "assets").glob("*.svg"))) == len(EXPECTED) * 2
    assert readme(repo_copy) == before and list((repo_copy / ASSETS).glob("*.svg")) == []


def test_build_command_reports_asset_counts(repo_copy, capsys):
    from profileos.cli import main

    assert main(["--root", str(repo_copy), "build", "--fixtures"]) == 0
    assert "assets: 18 files" in capsys.readouterr().out
