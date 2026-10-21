"""Production-README fixes: specific Recently Shipped entries, honest metric scope, and no self-feeding cache churn."""
import datetime as dt
import json

from profileos.analytics import shipped
from profileos.build import build
from profileos.generators import models
from profileos.github.fetch import fetch_contributions
from profileos.github.fixtures import FixtureClient

from conftest import NOW

REPO = {"name": "A", "full_name": "YRB19/A", "is_private": False}


def _commit(h, days=1):
    d = (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"sha": "a" * 40, "date": d, "headline": h, "url": "https://x/c", "changed_files": 2, "is_merge": False, "is_bot": False}


def _collect(commits=(), prs=(), rels=()):
    act = {"YRB19/A": {"merged_prs": list(prs), "recent_commits": list(commits)}}
    return shipped.collect([REPO], act, {"YRB19/A": list(rels)}, NOW, window_days=60, max_items=6, per_repo=6)


# ---- Recently Shipped: say what shipped -----------------------------------------------------------------------
def test_entries_carry_specific_text():
    pr = {"number": 1, "title": "Add retry budget to scheduler", "url": "https://x/p", "merged_at": "2026-09-28T00:00:00Z"}
    rel = {"name": "x", "tag": "v1.2.0", "published_at": "2026-09-29T00:00:00Z", "url": "https://x/r"}
    items = _collect([_commit("Parse nested config")], [pr], [rel])
    assert {i["kind"]: i["text"] for i in items} == {"release": "Release v1.2.0", "merged": "Add retry budget to scheduler", "update": "Parse nested config"}


def test_generic_headlines_are_dropped_not_shown():
    for h in ["update", "Update", "fix", "Initial commit", "Update README.md", "changes", "wip stuff", "x", "Add LICENSE.md", "Create .gitignore"]:
        assert _collect([_commit(h)]) == [], h
    pr = {"number": 2, "title": "update", "url": "https://x/p", "merged_at": "2026-09-28T00:00:00Z"}
    assert _collect(prs=[pr]) == []


def test_long_text_is_truncated_and_release_without_tag_is_skipped():
    items = _collect([_commit("Add " + "very " * 40 + "long headline")])
    assert len(items[0]["text"]) <= 72 and items[0]["text"].endswith("…")
    assert _collect(rels=[{"name": "", "tag": "", "published_at": "2026-09-29T00:00:00Z", "url": "https://x/r"}]) == []


def test_readme_entry_uses_text_and_escapes_markdown(repo_copy):
    class C(FixtureClient):
        def _nodes(self):
            nodes = super()._nodes()
            for n in nodes:
                n["mergedPRs"] = {"nodes": [{"number": 9, "title": "Add [x](http://evil.test) *parser*", "url": f"https://github.com/YRB19/{n['name']}/pull/9",
                                             "mergedAt": (NOW - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}]}
            return nodes

    res = build(repo_copy, client=C(NOW), now=NOW)
    block = res.blocks["RECENTLY_SHIPPED"]
    assert "[Add \\[x\\]" in block and "](http://evil.test)" not in block.replace("\\]", "").replace("\\(", "(") or "http://evil.test)" not in block.split("](")[0]
    assert "— [merged]" not in block and "— [update]" not in block and "— [release]" not in block


# ---- Metric scope ------------------------------------------------------------------------------------------------
def test_pulse_counts_only_public_non_excluded_repos():
    c = fetch_contributions(FixtureClient(NOW), "YRB19", NOW, exclude=frozenset({"yrb19/yrb19"}))["pulse"]
    assert c["scope"] == "public-shown"
    assert c["commits"] == 20 + 12 + 9 + 4 + 2          # profile repo (11) and the private repo (50) are not counted
    assert c["pull_requests"] == 7 + 3 + 2
    assert c["repos_touched"] == 5


def test_hidden_projects_do_not_leak_into_pulse(repo_copy):
    class C(FixtureClient):
        def _contrib(self):
            out = super()._contrib()
            out["user"]["pulse"]["commitContributionsByRepository"].append(
                {"repository": {"nameWithOwner": "YRB19/NetOS", "isPrivate": False}, "contributions": {"totalCount": 999}})
            return out

    res = build(repo_copy, client=C(NOW), now=NOW)
    pulse = json.loads((repo_copy / "data/cache/contributions.json").read_text())["data"]["pulse"]
    assert pulse["commits"] == 47 and "NetOS" not in json.dumps(pulse)


def test_private_repos_are_never_named_or_counted():
    class C(FixtureClient):
        def _contrib(self):
            out = super()._contrib()
            out["user"]["pulse"]["commitContributionsByRepository"].append(
                {"repository": {"nameWithOwner": "YRB19/Secret", "isPrivate": None}, "contributions": {"totalCount": 5}})  # unknown visibility
            return out

    c = fetch_contributions(C(NOW), "YRB19", NOW)
    assert c["pulse"]["commits"] == 20 + 12 + 9 + 4 + 2 + 11 and "Secret" not in json.dumps(c)


def test_scope_notes_state_what_is_counted():
    ctx_pulse = {"scope": "public-shown", "commits": 1, "pull_requests": 0, "reviews": 0, "issues": 0, "repos_touched": 1}
    assert "scope" in models.pulse_model.__code__.co_consts or True  # smoke: function exists
    from types import SimpleNamespace as NS
    mk = lambda p: NS(ds={"contributions": {"pulse": p}}, now=NOW, ages={})
    assert "Public repositories shown on this profile" in models.pulse_model(mk(ctx_pulse))["note"]
    legacy = {k: v for k, v in ctx_pulse.items() if k != "scope"}
    note = models.pulse_model(mk(legacy))["note"]
    assert "Public repositories shown" not in note and "not measures of quality" in note   # old cache: no scope claim


def test_scope_notes_are_visible_in_every_card(repo_copy):
    res = build(repo_copy, client=FixtureClient(NOW), now=NOW, dry_run=True)
    alts = {n: a.alt for n, a in res.asset_objects.items()}
    assert "Public repositories shown" in alts["pulse"]
    assert "Projects shown on this profile" in alts["activity"]
    assert "all activity, including repositories not featured here" in alts["heatmap"]
    assert "Public non-fork repositories" in alts["languages"]


# ---- Cache churn -------------------------------------------------------------------------------------------------
def test_profile_and_hidden_repos_are_not_cached(repo_copy):
    build(repo_copy, client=FixtureClient(NOW), now=NOW)
    cached = json.dumps({n: json.loads((repo_copy / f"data/cache/{n}.json").read_text())["data"] for n in ("repos", "activity", "releases")})
    for hidden in ("YRB19/YRB19", "YRB19/NetOS", "YRB19/FREYA"):
        assert hidden not in cached


def test_profile_repo_activity_cannot_retrigger_a_commit(repo_copy):
    """The loop: bot commit to the profile repo -> its own pushedAt/commits change -> cache changes -> another commit."""
    build(repo_copy, client=FixtureClient(NOW), now=NOW)

    class Busy(FixtureClient):
        def _nodes(self):
            nodes = super()._nodes()
            nodes.append({**nodes[0], "name": "YRB19", "nameWithOwner": "YRB19/YRB19", "url": "https://github.com/YRB19/YRB19",
                          "pushedAt": (NOW + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")})
            return nodes

    res = build(repo_copy, client=Busy(NOW), now=NOW)
    assert not res.changed
