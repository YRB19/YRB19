"""GraphQL fetch -> normalised, deterministic datasets."""
import datetime as dt

from ..storage.cache import iso
from .queries import CONTRIBUTIONS_QUERY, REPOS_QUERY

MAX_PAGES = 10  # safety cap


def _ts(now, days):
    return iso(now - dt.timedelta(days=days))


def _norm_commit(n: dict) -> dict:
    author = n.get("author") or {}
    login = ((author.get("user") or {}).get("login")) or ""
    name = author.get("name") or ""
    return {
        "sha": n["oid"],
        "date": n["committedDate"],
        "headline": n.get("messageHeadline") or "",
        "url": n["url"],
        "changed_files": n.get("changedFilesIfAvailable"),
        "is_merge": (n.get("parents") or {}).get("totalCount", 1) > 1,
        "is_bot": login.endswith("[bot]") or name.endswith("[bot]"),
    }


def normalize_repo(n: dict) -> dict:
    branch = n.get("defaultBranchRef") or {}
    target = branch.get("target") or {}
    langs = {e["node"]["name"]: e["size"] for e in (n.get("languages") or {}).get("edges", [])}
    repo = {
        "name": n["name"],
        "full_name": n["nameWithOwner"],
        "url": n["url"],
        "description": n.get("description"),
        "is_private": bool(n["isPrivate"]),
        "is_fork": bool(n["isFork"]),
        "is_archived": bool(n["isArchived"]),
        "created_at": n["createdAt"],
        "pushed_at": n.get("pushedAt"),
        "primary_language": (n.get("primaryLanguage") or {}).get("name"),
        "languages": dict(sorted(langs.items())),
        "stars": n.get("stargazerCount", 0),
        "forks": n.get("forkCount", 0),
        "open_issues": (n.get("openIssues") or {}).get("totalCount", 0),
        "open_prs": (n.get("openPRs") or {}).get("totalCount", 0),
        "topics": sorted(t["topic"]["name"] for t in (n.get("repositoryTopics") or {}).get("nodes", [])),
        "license": (n.get("licenseInfo") or {}).get("spdxId"),
        "default_branch": branch.get("name"),
    }
    activity = {
        "commits": {d: (target.get(k) or {}).get("totalCount", 0) for d, k in (("d7", "c7"), ("d30", "c30"), ("d90", "c90"))},
        "recent_commits": [_norm_commit(c) for c in (target.get("recent") or {}).get("nodes", [])],
        "merged_prs": [
            {"number": p["number"], "title": p["title"], "url": p["url"], "merged_at": p["mergedAt"]}
            for p in (n.get("mergedPRs") or {}).get("nodes", []) if p.get("mergedAt")
        ],
    }
    releases = [
        {"name": r.get("name") or r["tagName"], "tag": r["tagName"], "published_at": r["publishedAt"], "url": r["url"], "prerelease": r["isPrerelease"]}
        for r in (n.get("releases") or {}).get("nodes", []) if not r.get("isDraft") and r.get("publishedAt")
    ]
    return {"repo": repo, "activity": activity, "releases": releases}


def fetch_repos(client, login: str, now: dt.datetime) -> dict:
    variables = {"login": login, "cursor": None, "s7": _ts(now, 7), "s30": _ts(now, 30), "s90": _ts(now, 90)}
    repos, activity, releases = [], {}, {}
    for _ in range(MAX_PAGES):
        page = client.graphql(REPOS_QUERY, variables)["user"]["repositories"]
        for node in page["nodes"]:
            if node["isPrivate"]:  # public-only guard, re-checked in code (never trust the query alone)
                continue
            n = normalize_repo(node)
            repos.append(n["repo"])
            activity[n["repo"]["full_name"]] = n["activity"]
            releases[n["repo"]["full_name"]] = n["releases"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        variables["cursor"] = page["pageInfo"]["endCursor"]
    repos.sort(key=lambda r: r["full_name"].lower())
    return {"repos": repos, "activity": dict(sorted(activity.items())), "releases": dict(sorted(releases.items()))}


def _public_counts(entries, exclude) -> dict:
    """{owner/name: count} for PUBLIC, non-excluded repos only. Private repos are skipped entirely: never named,
    never counted, so a token that can see more than the public profile can never widen the output."""
    out: dict = {}
    for e in entries or []:
        repo = (e or {}).get("repository") or {}
        name = repo.get("nameWithOwner")
        if not name or repo.get("isPrivate") is not False or name.lower() in exclude:
            continue
        out[name] = out.get(name, 0) + int((e.get("contributions") or {}).get("totalCount", 0))
    return dict(sorted(out.items()))


def fetch_contributions(client, login: str, now: dt.datetime, exclude=frozenset()) -> dict:
    v = {"login": login, "f30": _ts(now, 30), "f365": _ts(now, 365), "to": iso(now)}
    u = client.graphql(CONTRIBUTIONS_QUERY, v)["user"]
    pulse, year = u["pulse"], u["year"]["contributionCalendar"]
    days = sorted(
        ({"date": d["date"], "count": d["contributionCount"]} for w in year["weeks"] for d in w["contributionDays"]),
        key=lambda d: d["date"],
    )
    commits = _public_counts(pulse.get("commitContributionsByRepository"), exclude)
    prs = _public_counts(pulse.get("pullRequestContributionsByRepository"), exclude)
    return {
        "pulse": {  # commits/PRs/repos: public, non-excluded repos only ("scope"); reviews/issues are GitHub totals, never displayed
            "scope": "public-shown",
            "commits": sum(commits.values()),
            "pull_requests": sum(prs.values()),
            "reviews": pulse["totalPullRequestReviewContributions"],
            "issues": pulse["totalIssueContributions"],
            "repos_touched": sum(1 for c in commits.values() if c > 0),
        },
        "calendar": {"total": year["totalContributions"], "days": days},
    }
