import datetime as dt

from profileos.analytics import categorize, discovery, languages, shipped
from profileos.github.fetch import normalize_repo

NOW = dt.datetime(2026, 9, 30, 12, tzinfo=dt.timezone.utc)


def commit(headline, *, bot=False, merge=False, files=2, days=1):
    d = (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"sha": "a" * 40, "date": d, "headline": headline, "url": "https://x/c", "changed_files": files, "is_merge": merge, "is_bot": bot}


def test_meaningful_commit_rules():
    assert shipped.meaningful(commit("Add parser"))
    assert not shipped.meaningful(commit("chore: bump"))
    assert not shipped.meaningful(commit("Docs: readme"))
    assert not shipped.meaningful(commit("Add thing", bot=True))
    assert not shipped.meaningful(commit("Add thing", merge=True))
    assert not shipped.meaningful(commit("Add thing", files=0))


def _repo(name="A", private=False):
    return {"name": name, "full_name": f"YRB19/{name}", "is_private": private, "is_fork": False, "is_archived": False}


def test_shipped_limits_prefers_releases_and_skips_private():
    repos = [_repo("A"), _repo("B", private=True)]
    rel = {"YRB19/A": [{"name": "v1", "tag": "v1", "published_at": "2026-09-29T00:00:00Z", "url": "https://x/r"}], "YRB19/B": [{"name": "v", "tag": "v", "published_at": "2026-09-29T00:00:00Z", "url": "https://x/b"}]}
    act = {"YRB19/A": {"merged_prs": [], "recent_commits": [commit("Add a", days=2), commit("Add b", days=3), commit("Add c", days=4)]}}
    items = shipped.collect(repos, act, rel, NOW, window_days=60, max_items=6)
    assert [i["kind"] for i in items] == ["release", "update"]  # <=2 per repo, release first
    assert all(i["repo"] == "A" for i in items)


def test_shipped_respects_window():
    repos = [_repo("A")]
    act = {"YRB19/A": {"merged_prs": [], "recent_commits": [commit("Add a", days=90)]}}
    assert shipped.collect(repos, act, {}, NOW, window_days=60, max_items=6) == []


def test_language_distribution_folds_small_and_excludes():
    repos = [
        {**_repo("A"), "languages": {"Python": 9000, "Go": 100, "HTML": 900}},
        {**_repo("B"), "is_fork": True, "languages": {"Rust": 99999}},
    ]
    out = languages.distribution(repos, exclude_languages=["HTML"], min_pct=2)
    assert out[0]["language"] == "Python" and all(x["language"] != "Rust" for x in out)
    assert {x["language"] for x in out} == {"Python", "Go"} or out[-1]["language"] == "Other"


def test_categorize_precedence():
    repo = {"full_name": "YRB19/A", "topics": ["llm"], "description": "video tool", "primary_language": "Rust", "created_at": "2024-01-01T00:00:00Z"}
    cats = {"topic_map": {"ai": ["llm"], "ai-media": ["video"]}, "language_map": {"Rust": "systems"}}
    kw = dict(categories=cats, earlier_before="2025-01-01")
    assert categorize.categorize(repo, project={"category": "web"}, overrides={}, **kw) == "web"            # manual wins
    assert categorize.categorize(repo, project=None, overrides={"category_overrides": {"YRB19/A": "fintech"}}, **kw) == "fintech"
    assert categorize.categorize(repo, project=None, overrides={}, **kw) == "ai"                             # topics
    assert categorize.categorize({**repo, "topics": []}, project=None, overrides={}, **kw) == "ai-media"     # description
    assert categorize.categorize({**repo, "topics": [], "description": None}, project=None, overrides={}, **kw) == "systems"  # language
    assert categorize.categorize({**repo, "topics": [], "description": None, "primary_language": None}, project=None, overrides={}, **kw) == "earlier"


def test_discovery_seed_then_new():
    repos = [{**_repo("Old"), "created_at": "2024-01-01T00:00:00Z", "url": "u"}]
    seed = discovery.update_first_seen(None, repos, NOW)
    assert seed == {"YRB19/Old": "2024-01-01"}
    repos.append({**_repo("Fresh"), "created_at": "2024-02-01T00:00:00Z", "url": "u2"})
    nxt = discovery.update_first_seen(seed, repos, NOW)
    assert nxt["YRB19/Fresh"] == "2026-09-30"
    nb = discovery.new_builds(nxt, repos, set(), NOW, 14)
    assert [x["name"] for x in nb] == ["Fresh"]
    assert discovery.new_builds(nxt, repos, {"yrb19/fresh"}, NOW, 14) == []  # curated repos are not "new"


def test_normalize_handles_missing_default_branch():
    node = {"name": "E", "nameWithOwner": "YRB19/E", "url": "u", "description": None, "isPrivate": False, "isFork": False, "isArchived": False,
            "createdAt": "2026-01-01T00:00:00Z", "pushedAt": None, "updatedAt": "2026-01-01T00:00:00Z", "primaryLanguage": None,
            "languages": {"edges": []}, "stargazerCount": 0, "forkCount": 0, "openIssues": {"totalCount": 0}, "openPRs": {"totalCount": 0},
            "repositoryTopics": {"nodes": []}, "licenseInfo": None, "defaultBranchRef": None, "releases": {"nodes": []}, "mergedPRs": {"nodes": []}}
    n = normalize_repo(node)
    assert n["activity"]["commits"] == {"d7": 0, "d30": 0, "d90": 0} and n["repo"]["primary_language"] is None
