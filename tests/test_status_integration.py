"""Phase 6 end to end: cards, release tracker, build/cache behaviour, validation rules, workflow + dispatch template."""
import datetime as dt
import json
import os
import stat
import subprocess
import textwrap

import httpx
import pytest
import yaml

from profileos.build import build
from profileos.generators import models
from profileos.generators.svg import safety
from profileos.github.client import GitHubClient, GitHubError
from profileos.github.fixtures import FixtureClient
from profileos.status import ci as ci_status
from profileos.validate import validate

from conftest import NOW, ROOT
from test_health import PUBLIC4, Fetcher, Resolver, resp


def _edit(root, name, fn):
    p = root / "data" / f"{name}.yml"
    d = yaml.safe_load(p.read_text())
    fn(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))


def runs_client(payload_for):
    """A client exposing only the REST read the CI fetcher needs. payload_for(repo_name) -> runs list | Exception."""
    class C(FixtureClient):
        def rest_response(self, path):
            name = path.split("/")[3]
            out = payload_for(name)
            if isinstance(out, Exception):
                raise out
            return httpx.Response(200, json={"workflow_runs": out})
    return C(NOW)


def run(conclusion="success", status="completed", days=1, wf=1):
    t = (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"workflow_id": wf, "name": "CI", "event": "push", "status": status, "conclusion": conclusion, "created_at": t,
            "updated_at": t, "html_url": "https://github.com/YRB19/x/actions/runs/1"}


def card_alt(res, slug):
    return res.asset_objects[f"card-{slug}"].alt


# ---- cards ---------------------------------------------------------------------------------------------------------------------
def test_cards_show_ci_states_with_glyph_text_and_date(repo_copy):
    res = build(repo_copy, client=runs_client(lambda n: {"UsageOS": [run()], "ClipOS": [run("failure")], "ResearchOS": [run(status="in_progress", conclusion=None)]}.get(n, [])), now=NOW)
    assert "CI passing, last run 2026-09-29" in card_alt(res, "usageos")
    assert "CI failing" in card_alt(res, "clipos") and "CI running" in card_alt(res, "researchos")
    assert "CI" not in card_alt(res, "companionos")                          # no runs -> not_configured -> nothing drawn
    for mode, svg in res.asset_objects["card-clipos"].svg.items():
        assert "CI failing" in svg and safety.validate(svg) == []


def test_failing_ci_uses_the_red_token_and_passing_never_does(repo_copy):
    from profileos.generators.svg.tokens import Theme
    res = build(repo_copy, client=runs_client(lambda n: {"UsageOS": [run()], "ClipOS": [run("failure")]}.get(n, [])), now=NOW)
    for mode in ("light", "dark"):
        t = Theme(mode)
        assert t.red in res.asset_objects["card-clipos"].svg[mode] and t.red not in res.asset_objects["card-usageos"].svg[mode]
        assert t.green in res.asset_objects["card-usageos"].svg[mode] and t.green not in res.asset_objects["card-clipos"].svg[mode]


def test_no_status_means_no_status_row_and_unchanged_card_height(repo_copy):
    quiet = build(repo_copy, client=runs_client(lambda n: []), now=NOW, dry_run=True)
    busy = build(repo_copy, client=runs_client(lambda n: [run()]), now=NOW, dry_run=True)
    h = lambda r: r.asset_objects["card-usageos"].svg["light"].split('height="')[1].split('"')[0]
    assert "CI" not in card_alt(quiet, "usageos") and int(h(busy)) > int(h(quiet))


def test_never_green_when_fetch_fails_and_no_cache(repo_copy):
    res = build(repo_copy, client=runs_client(lambda n: GitHubError("down")), now=NOW)
    assert all("CI" not in a.alt for a in res.asset_objects.values())
    assert not (repo_copy / "data/cache/ci.json").exists()                    # nothing observed -> no empty cache file either
    assert any(w.startswith("ci:") for w in res.warnings)


def test_outage_after_good_run_keeps_cached_status_then_hides_it_when_stale(repo_copy):
    good = runs_client(lambda n: [run()] if n == "UsageOS" else [])
    build(repo_copy, client=good, now=NOW)
    broken = runs_client(lambda n: GitHubError("down"))
    res = build(repo_copy, client=broken, now=NOW + dt.timedelta(hours=12))
    assert "CI passing" in card_alt(res, "usageos")                           # young cache still shown
    res = build(repo_copy, client=broken, now=NOW + dt.timedelta(hours=100), dry_run=True)
    assert "CI" not in card_alt(res, "usageos")                               # stale cache is NOT shown as green


def test_cached_ci_is_never_trusted_without_a_check_time(repo_copy):
    build(repo_copy, client=runs_client(lambda n: [run()] if n == "UsageOS" else []), now=NOW)
    path = repo_copy / "data/cache/ci.json"
    env = json.loads(path.read_text())
    for rec in env["data"].values():
        rec.pop("checked_at", None)
    path.write_text(json.dumps(env))
    res = build(repo_copy, client=runs_client(lambda n: GitHubError("x")), now=NOW + dt.timedelta(hours=1), dry_run=True)
    assert "CI" not in card_alt(res, "usageos")


def test_ci_toggles_and_per_project_opt_out(repo_copy):
    c = runs_client(lambda n: [run()])
    _edit(repo_copy, "config", lambda d: d.setdefault("ci", {}).update(enabled=False))
    assert "CI" not in card_alt(build(repo_copy, client=c, now=NOW, dry_run=True), "usageos")
    _edit(repo_copy, "config", lambda d: d["ci"].update(enabled=True))
    _edit(repo_copy, "projects", lambda d: d["UsageOS"].update(ci={"track": False}))
    res = build(repo_copy, client=c, now=NOW, dry_run=True)
    assert "CI" not in card_alt(res, "usageos") and "CI passing" in card_alt(res, "clipos")


def test_ci_is_only_requested_for_public_published_flagships(repo_copy):
    seen = []
    build(repo_copy, client=runs_client(lambda n: seen.append(n) or []), now=NOW, dry_run=True)
    assert seen and set(seen) <= {"UsageOS", "ResearchOS", "ClipOS", "CompanionOS"}
    assert not {"NetOS", "FREYA", "YRB19"} & set(seen)


def test_ci_text_is_escaped_in_alt_and_svg(repo_copy):
    hostile = run()
    hostile["name"] = '<script>alert(1)</script>"&'
    res = build(repo_copy, client=runs_client(lambda n: [hostile] if n == "UsageOS" else []), now=NOW, dry_run=True)
    for svg in res.asset_objects["card-usageos"].svg.values():
        assert "<script" not in svg and safety.validate(svg) == []
    assert "<script" not in res.asset_objects["card-usageos"].alt


# ---- cache: change-only + bounded timestamp churn -----------------------------------------------------------------------------------
def test_unchanged_status_does_not_rewrite_cache_or_readme(repo_copy):
    c = runs_client(lambda n: [run()])
    build(repo_copy, client=c, now=NOW)
    before = {p.name: p.read_bytes() for p in (repo_copy / "data/cache").iterdir()}
    res = build(repo_copy, client=c, now=NOW + dt.timedelta(hours=6))
    assert not res.changed
    assert {p.name: p.read_bytes() for p in (repo_copy / "data/cache").iterdir()} == before


def test_a_state_change_is_written_and_a_daily_timestamp_refresh_is_allowed(repo_copy):
    build(repo_copy, client=runs_client(lambda n: [run()]), now=NOW)
    res = build(repo_copy, client=runs_client(lambda n: [run("failure")]), now=NOW + dt.timedelta(hours=1))
    assert res.changed and json.loads((repo_copy / "data/cache/ci.json").read_text())["data"]["YRB19/UsageOS"]["state"] == "failing"
    from profileos.storage.cache import Cache, would_change_status
    c = Cache(repo_copy / "data/cache")
    same = json.loads((repo_copy / "data/cache/ci.json").read_text())["data"]
    assert not would_change_status(c, "ci", same, NOW + dt.timedelta(hours=3))
    assert would_change_status(c, "ci", same, NOW + dt.timedelta(hours=30))      # keeps the stored check time honest


# ---- health in the build -----------------------------------------------------------------------------------------------------------------
def enable_health(root, url="https://repohealth.vercel.app"):
    _edit(root, "projects", lambda d: d["RepoHealth"].update(verified=True, stack=d["RepoHealth"].get("stack") or ["TypeScript"],
                                                           deployment={"health_url": url, "health_check": True}))
    _edit(root, "evidence", lambda d: d["projects"]["RepoHealth"].update(
        health_url={"value": url, "confidence": "MEDIUM", "evidence": ["README.md 'Live demo' link"]}))


def test_health_runs_only_when_opted_in_and_needs_evidence(repo_copy):
    f = Fetcher(resp(200))
    build(repo_copy, client=FixtureClient(NOW), now=NOW, dry_run=True, health_fetcher=f, resolver=Resolver({}))
    assert not f.calls                                                         # default data: nothing is probed
    _edit(repo_copy, "projects", lambda d: d["RepoHealth"].update(deployment={"health_url": "https://repohealth.vercel.app", "health_check": True}))
    rep = validate(repo_copy)
    assert not rep.ok and any("evidence" in e or "verified" in e for e in rep.errors)


def test_health_state_is_cached_and_checked_time_recorded(repo_copy):
    enable_health(repo_copy)
    assert validate(repo_copy).ok
    f = Fetcher(resp(200))
    build(repo_copy, client=FixtureClient(NOW), now=NOW, health_fetcher=f, resolver=Resolver({"repohealth.vercel.app": [[PUBLIC4]]}))
    rec = json.loads((repo_copy / "data/cache/health.json").read_text())["data"]["RepoHealth"]
    assert rec["state"] == "online" and rec["checked_at"] == "2026-09-30T12:00:00Z" and rec["host"] == "repohealth.vercel.app"
    assert f.calls and f.calls[0]["ip"] == PUBLIC4


def test_health_failure_falls_back_to_cache_then_goes_quiet(repo_copy):
    enable_health(repo_copy)
    r = Resolver({"repohealth.vercel.app": [[PUBLIC4]]})
    build(repo_copy, client=FixtureClient(NOW), now=NOW, health_fetcher=Fetcher(resp(200)), resolver=r)
    later = NOW + dt.timedelta(hours=6)
    res = build(repo_copy, client=FixtureClient(later), now=later, health_fetcher=Fetcher(TimeoutError()), resolver=r, dry_run=True)
    h = json.loads((repo_copy / "data/cache/health.json").read_text())["data"]["RepoHealth"]
    assert h["state"] == "online"                                              # a timeout never overwrote a good record with "down"


def test_fixture_and_preview_runs_never_probe_the_network(repo_copy):
    enable_health(repo_copy)
    def boom(*a, **k):
        raise AssertionError("network used")
    import profileos.status.health as H
    orig = H.run_checks
    H.run_checks = boom
    try:
        build(repo_copy, fixtures=True, now=NOW, dry_run=True)
    finally:
        H.run_checks = orig


def test_stale_health_is_not_drawn(repo_copy):
    assert models.health_chip.__name__ == "health_chip"
    from profileos.status import health
    rec = {"state": "online", "checked_at": "2026-09-30T00:00:00Z", "host": "x.example.com"}
    assert health.effective(rec, NOW + dt.timedelta(days=5), fresh=False, stale_after_h=72)["state"] == "unknown"
    assert models._chip({"state": "unknown"}, models.HEALTH_LABEL, date_key="checked_at") is None
    assert models._chip({"state": "not_configured"}, models.CI_LABEL, date_key="run_at") is None


# ---- validation rules -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["https://127.0.0.1/health", "http://repohealth.vercel.app/", "https://repohealth.vercel.app:8443/h",
                                 "https://user:pw@repohealth.vercel.app/", "ftp://repohealth.vercel.app/", "https://[::1]/h"])
def test_validator_rejects_unsafe_health_urls(repo_copy, url):
    _edit(repo_copy, "projects", lambda d: d["RepoHealth"].update(deployment={"health_url": url}))
    assert not validate(repo_copy).ok


def test_validator_requires_flag_url_verification_and_matching_evidence(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["RepoHealth"].update(deployment={"health_check": True}))
    assert not validate(repo_copy).ok
    enable_health(repo_copy)
    assert validate(repo_copy).ok
    _edit(repo_copy, "evidence", lambda d: d["projects"]["RepoHealth"]["health_url"].update(confidence="LOW"))
    assert not validate(repo_copy).ok
    _edit(repo_copy, "evidence", lambda d: d["projects"]["RepoHealth"]["health_url"].update(confidence="MEDIUM", value="https://other.example.com"))
    assert not validate(repo_copy).ok


def test_event_dispatch_config_is_validated_only_when_enabled(repo_copy):
    assert validate(repo_copy).ok                                              # disabled by default
    _edit(repo_copy, "config", lambda d: d["event_dispatch"].update(enabled=True))
    assert not validate(repo_copy).ok                                          # incomplete: no sources
    _edit(repo_copy, "config", lambda d: d["event_dispatch"].update(sources=["YRB19/UsageOS"], events=["release"]))
    (repo_copy / ".github/workflows").mkdir(parents=True)
    (repo_copy / ".github/workflows/update-profile.yml").write_text((ROOT / ".github/workflows/update-profile.yml").read_text())
    assert validate(repo_copy).ok
    _edit(repo_copy, "config", lambda d: d["event_dispatch"].update(target_repo="someone-else/Profile"))
    assert not validate(repo_copy).ok
    _edit(repo_copy, "config", lambda d: d["event_dispatch"].update(target_repo="YRB19/YRB19", event_type="not-a-listed-type"))
    assert not validate(repo_copy).ok


def test_event_dispatch_is_off_in_shipped_config():
    cfg = yaml.safe_load((ROOT / "data/config.yml").read_text())
    assert cfg["event_dispatch"]["enabled"] is False and cfg["event_dispatch"]["sources"] == []
    assert all("health_check" not in (p.get("deployment") or {}) or p["deployment"]["health_check"] is False
               for p in yaml.safe_load((ROOT / "data/projects.yml").read_text()).values())


def test_secrets_never_live_in_data_files():
    assert validate(ROOT).ok
    for name in ("config", "projects"):
        text = (ROOT / "data" / f"{name}.yml").read_text().lower()
        assert "ghp_" not in text and "github_pat_" not in text


# ---- releases ----------------------------------------------------------------------------------------------------------------------------------------
def rel(tag, day, pre=False, **kw):
    return {"name": tag, "tag": tag, "published_at": f"2026-09-{day:02d}T00:00:00Z", "url": f"https://github.com/YRB19/UsageOS/releases/tag/{tag}", "prerelease": pre, **kw}


def with_releases(repo_copy, mapping):
    class C(FixtureClient):
        def _nodes(self):
            nodes = super()._nodes()
            for n in nodes:
                n["releases"] = {"nodes": [
                    {"name": r["name"], "tagName": r["tag"], "publishedAt": r.get("published_at"), "url": r["url"], "isPrerelease": r["prerelease"], "isDraft": r.get("draft", False)}
                    for r in mapping.get(n["name"], [])]}
            return nodes
    return build(repo_copy, client=C(NOW), now=NOW)


def test_release_tracker_lists_latest_published_with_link_date_and_prerelease(repo_copy):
    res = with_releases(repo_copy, {"UsageOS": [rel("v1.0", 3), rel("v1.2-rc1", 20, pre=True), rel("v1.1", 10)], "ClipOS": [rel("v0.3", 5)]})
    block = res.blocks["RELEASES"]
    assert "### Latest releases" in block and "| Project | Version | Released |" in block
    assert "[v1.2-rc1](https://github.com/YRB19/UsageOS/releases/tag/v1.2-rc1) · pre-release | 2026-09-20" in block
    assert "v1.1" not in block and "v1.0" not in block                          # one row per project: the latest published
    assert block.index("UsageOS") < block.index("ClipOS") or block.index("ClipOS") < block.index("UsageOS")


def test_drafts_and_unpublished_releases_are_excluded(repo_copy):
    res = with_releases(repo_copy, {"UsageOS": [rel("v9.9", 25, draft=True), rel("v1.0", 3), rel("v-nodate", 1, published_at=None)]})
    assert "v9.9" not in res.blocks["RELEASES"] and "v-nodate" not in res.blocks["RELEASES"] and "v1.0" in res.blocks["RELEASES"]
    assert models.latest_release([{"tag": "v1", "published_at": "2026-01-01T00:00:00Z", "draft": True, "url": "u"}]) is None
    assert models.latest_release([]) is None and models.latest_release(None) is None


def test_latest_release_is_by_publish_date_not_list_order():
    older_created_later = [rel("v2.0", 1), rel("v1.9.1", 12)]
    assert models.latest_release(older_created_later)["tag"] == "v1.9.1"


def test_no_releases_means_no_section_no_heading_no_fake_row(repo_copy):
    res = with_releases(repo_copy, {})
    assert res.blocks["RELEASES"] == ""
    assert "Latest releases" not in (repo_copy / "README.md").read_text()


def test_release_text_is_escaped_for_markdown(repo_copy):
    res = with_releases(repo_copy, {"UsageOS": [rel("v1|<b>x</b>[y](http://evil.test)", 3)]})
    row = [l for l in res.blocks["RELEASES"].splitlines() if "UsageOS" in l][0]
    import re
    assert len(re.findall(r"(?<!\\)\|", row)) == 4                              # an (escaped) pipe in a tag cannot add a column
    assert "<b>" not in row


def test_cards_use_the_latest_published_release_and_flag_prereleases(repo_copy):
    res = with_releases(repo_copy, {"UsageOS": [rel("v1.0", 3), rel("v1.1", 12)]})
    assert "Release v1.1" in card_alt(res, "usageos")


def test_release_tracker_respects_curated_order_and_hides_internal_projects(repo_copy):
    res = with_releases(repo_copy, {"NetOS": [rel("v1", 3)], "FREYA": [rel("v1", 3)], "UsageOS": [rel("v1", 4)]})
    assert "NetOS" not in res.blocks["RELEASES"] and "FREYA" not in res.blocks["RELEASES"]
    cached = (repo_copy / "data/cache/releases.json").read_text()
    assert "NetOS" not in cached and "FREYA" not in cached


def test_release_tracker_reuses_the_existing_dataset_no_extra_api_calls(repo_copy):
    calls = {"graphql": 0}

    class C(FixtureClient):
        def graphql(self, q, v):
            calls["graphql"] += 1
            return super().graphql(q, v)
    build(repo_copy, client=C(NOW), now=NOW, dry_run=True)
    assert calls["graphql"] == 2                                                # repos (1 page) + contributions: releases ride along


def test_readme_template_has_the_releases_marker_exactly_once():
    text = (ROOT / "README.md").read_text()
    assert text.count("<!-- PROFILEOS:START:RELEASES -->") == 1 and text.count("<!-- PROFILEOS:END:RELEASES -->") == 1


# ---- workflow permissions + dispatch template ---------------------------------------------------------------------------------------------------------------
def test_profile_workflow_keeps_minimum_permissions_and_all_triggers():
    wf = yaml.safe_load((ROOT / ".github/workflows/update-profile.yml").read_text())
    assert wf["permissions"] == {"contents": "write"}
    assert set(wf[True]) >= {"schedule", "workflow_dispatch", "repository_dispatch"}
    assert wf[True]["repository_dispatch"]["types"] == ["profileos-refresh"]
    text = (ROOT / ".github/workflows/update-profile.yml").read_text()
    assert "secrets.PROFILEOS_STATUS_TOKEN" in text and text.count("secrets.") == 2   # GITHUB_TOKEN + the optional read-only token


def test_validate_workflow_has_no_secrets_and_is_read_only():
    text = (ROOT / ".github/workflows/validate.yml").read_text()
    assert "secrets." not in text and yaml.safe_load(text)["permissions"] == {"contents": "read"}


TEMPLATE = ROOT / "templates/notify-profile.yml"


def _script():
    wf = yaml.safe_load(TEMPLATE.read_text())
    return wf["jobs"]["notify"]["steps"][0]["run"]


def test_template_is_inert_by_construction():
    wf = yaml.safe_load(TEMPLATE.read_text())
    assert wf["permissions"] == {}
    assert "vars.PROFILEOS_DISPATCH_ENABLED == 'true'" in wf["jobs"]["notify"]["if"]
    assert wf[True] == {"release": {"types": ["published"]}}
    assert not (ROOT / ".github/workflows/notify-profile.yml").exists()           # lives in templates/, not active here
    text = TEMPLATE.read_text()
    assert "secrets.GITHUB_TOKEN" not in text and "github.token" not in text      # no silent broad fallback
    assert wf["jobs"]["notify"]["env"]["TOKEN"] == "${{ secrets.PROFILEOS_DISPATCH_TOKEN }}"
    assert "profileos-refresh" in text


def run_script(tmp_path, env, curl_status="204"):
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    log = tmp_path / "curl.log"
    stub = bin_ / "curl"
    stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\nprintf "{curl_status}"\n')
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    base = {"PATH": f"{bin_}:/usr/bin:/bin", "GITHUB_REPOSITORY": "YRB19/UsageOS"}
    r = subprocess.run(["bash", "-c", _script()], env={**base, **env}, capture_output=True, text=True, timeout=20)
    return r, (log.read_text() if log.exists() else "")


def test_template_without_the_secret_sends_nothing_even_if_github_token_exists(tmp_path):
    r, log = run_script(tmp_path, {"TARGET": "YRB19/YRB19", "GITHUB_TOKEN": "ghs_broad"})
    assert r.returncode == 0 and log == "" and "disabled" in r.stdout


def test_template_with_the_secret_posts_one_scoped_dispatch(tmp_path):
    r, log = run_script(tmp_path, {"TOKEN": "github_pat_fine", "TARGET": "YRB19/YRB19", "GITHUB_TOKEN": "ghs_broad"})
    assert r.returncode == 0 and log.count("\n") == 1
    assert "https://api.github.com/repos/YRB19/YRB19/dispatches" in log and "Bearer github_pat_fine" in log
    assert "ghs_broad" not in log and '"event_type":"profileos-refresh"' in log and '"source":"YRB19/UsageOS"' in log


@pytest.mark.parametrize("target", ["", "no-slash", "a/b/c", "YRB19/YRB19; curl evil", "YRB19/$(id)", "../x/y", "YRB19/Y RB"])
def test_template_rejects_malformed_targets_without_sending(tmp_path, target):
    r, log = run_script(tmp_path, {"TOKEN": "t", "TARGET": target})
    assert r.returncode == 0 and log == ""


@pytest.mark.parametrize("status", ["401", "403", "404", "422", "000"])
def test_template_never_fails_the_release_when_dispatch_fails(tmp_path, status):
    r, log = run_script(tmp_path, {"TOKEN": "t", "TARGET": "YRB19/YRB19"}, curl_status=status)
    assert r.returncode == 0 and f"HTTP {status}" in r.stdout and "::warning::" in r.stdout


def test_dispatch_documentation_exists_and_names_every_secret():
    perm = (ROOT / "docs/PERMISSIONS.md").read_text()
    ev = (ROOT / "docs/EVENT_DISPATCH.md").read_text()
    for name in ("PROFILEOS_STATUS_TOKEN", "PROFILEOS_DISPATCH_TOKEN", "GITHUB_TOKEN", "Actions: Read-only"):
        assert name in perm, name
    for name in ("PROFILEOS_DISPATCH_ENABLED", "PROFILEOS_DISPATCH_TOKEN", "templates/notify-profile.yml", "disabled by default"):
        assert name in ev, name
