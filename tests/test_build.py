import datetime as dt
import json

import pytest

from profileos.build import BuildError, build
from profileos.github.client import GitHubError
from profileos.github.fixtures import FixtureClient

from conftest import NOW


class Failing:
    remaining = None

    def graphql(self, *a, **k):
        raise GitHubError("boom")


class Patched(FixtureClient):
    """Fixture client with a hook to tamper with nodes."""

    def __init__(self, now, tamper):
        super().__init__(now)
        self.tamper = tamper

    def _nodes(self):
        nodes = super()._nodes()
        self.tamper(nodes)
        return nodes


def cache_files(root):
    return sorted(p.name for p in (root / "data" / "cache").glob("*.json"))


def test_build_twice_is_idempotent(repo_copy):
    r1 = build(repo_copy, fixtures=True, now=NOW)
    assert r1.changed
    snap = {p.name: p.read_text() for p in (repo_copy / "data" / "cache").glob("*.json")}
    readme = (repo_copy / "README.md").read_text()
    r2 = build(repo_copy, client=FixtureClient(NOW), now=NOW + dt.timedelta(hours=6))  # later run, same upstream data
    assert not r2.changed
    assert (repo_copy / "README.md").read_text() == readme
    assert {p.name: p.read_text() for p in (repo_copy / "data" / "cache").glob("*.json")} == snap


def test_manual_text_outside_markers_untouched(repo_copy):
    before = (repo_copy / "README.md").read_text()
    build(repo_copy, fixtures=True, now=NOW)
    after = (repo_copy / "README.md").read_text()
    assert "## What I Build" in after and "Engineering Approach" in after
    strip = lambda t: "".join(l for l in t.splitlines(True) if "PROFILEOS" not in l)  # noqa: E731
    for line in ("# Rishit Babbar", "The goal isn't to generate more code."):
        assert line in before and line in after


def test_dry_run_writes_nothing(repo_copy):
    before = (repo_copy / "README.md").read_text()
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    assert res.blocks["CURRENTLY_BUILDING"]
    assert (repo_copy / "README.md").read_text() == before and cache_files(repo_copy) == []


def test_api_failure_falls_back_to_last_cache(repo_copy):
    build(repo_copy, fixtures=True, now=NOW)
    good = (repo_copy / "README.md").read_text()
    res = build(repo_copy, client=Failing(), now=NOW + dt.timedelta(hours=6))
    assert any("failed" in w for w in res.warnings)
    assert (repo_copy / "README.md").read_text() == good  # still renders, no crash, nothing lost
    res = build(repo_copy, client=Failing(), now=NOW + dt.timedelta(days=3))
    assert "as of 2026-09-30" in (repo_copy / "README.md").read_text()  # stale > 24 h is labelled


def test_no_cache_and_no_api_hides_sections_never_fabricates(repo_copy):
    res = build(repo_copy, client=Failing(), now=NOW)
    for sid in ("CURRENTLY_BUILDING", "PULSE", "RECENTLY_SHIPPED", "SELECTED_SYSTEMS"):
        assert res.blocks[sid] == "", sid
    assert "github.com" not in res.blocks["OS_SERIES"]  # curated names only, no fetched facts or links
    text = (repo_copy / "README.md").read_text()
    assert "github.com/YRB19/UsageOS" not in text and "last push" not in text and "data snapshot" in text


def test_private_repos_never_leak(repo_copy):
    def add_private(nodes):
        leak = json.loads(json.dumps(nodes[0]))
        leak.update(name="SecretRepo", nameWithOwner="YRB19/SecretRepo", isPrivate=True)
        nodes.append(leak)

    build(repo_copy, client=Patched(NOW, add_private), now=NOW)
    blob = (repo_copy / "README.md").read_text() + "".join(p.read_text() for p in (repo_copy / "data" / "cache").glob("*.json"))
    assert "SecretRepo" not in blob


def test_repo_text_is_sanitised(repo_copy):
    evil = "Nice\x00tool <script>alert(1)</script> ![x](https://evil/x.png) [click](javascript:alert(1))\n\n# heading"

    def tamper(nodes):
        nodes[0]["description"] = evil

    build(repo_copy, client=Patched(NOW, tamper), now=NOW)
    text = (repo_copy / "README.md").read_text()
    assert "<script>" not in text and "\x00" not in text
    assert "![x](" not in text and "[click](javascript" not in text


def test_invalid_data_blocks_build_and_writes_nothing(repo_copy):
    (repo_copy / "data" / "projects.yml").write_text("UsageOS: {repo: bad, category: nope, status: active}\n")
    before = (repo_copy / "README.md").read_text()
    with pytest.raises(BuildError):
        build(repo_copy, fixtures=True, now=NOW)
    assert (repo_copy / "README.md").read_text() == before and cache_files(repo_copy) == []


def test_broken_marker_fails_without_writing(repo_copy):
    p = repo_copy / "README.md"
    p.write_text(p.read_text().replace("<!-- PROFILEOS:START:PULSE -->", ""))
    with pytest.raises(BuildError):
        build(repo_copy, fixtures=True, now=NOW)


def test_unverified_projects_show_no_tagline_or_stack(repo_copy):
    build(repo_copy, fixtures=True, now=NOW)
    text = (repo_copy / "README.md").read_text()
    sel = text.split("PROFILEOS:START:SELECTED_SYSTEMS")[1].split("PROFILEOS:END:SELECTED_SYSTEMS")[0]
    assert "FastAPI" not in sel  # brief-backed stack only appears once verified:true


def test_manual_override_wins(repo_copy):
    (repo_copy / "data" / "overrides.yml").write_text("focus: {NetOS: force_active, UsageOS: hide}\n")
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    cb = res.blocks["CURRENTLY_BUILDING"]
    assert "NetOS" in cb and "UsageOS" not in cb


def test_display_limit_respected(repo_copy):
    (repo_copy / "data" / "profile.yml").write_text((repo_copy / "data" / "profile.yml").read_text().replace("max_currently_building: 5", "max_currently_building: 2"))
    res = build(repo_copy, fixtures=True, dry_run=True, now=NOW)
    assert res.blocks["CURRENTLY_BUILDING"].count("\n") == 1
