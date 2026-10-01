"""SYNTHETIC client for offline dry-runs and tests. Numbers here are NOT real data."""
import datetime as dt

from ..storage.cache import iso

# name -> (days since push, c7, c30, c90, release age days | None, language)
_SPEC = {
    "UsageOS": (1, 14, 38, 80, 6, "Python"),
    "ResearchOS": (3, 6, 22, 60, None, "Python"),
    "FREYA": (9, 1, 9, 30, None, "TypeScript"),
    "ClipOS": (20, 0, 3, 25, 25, "Python"),
    "CompanionOS": (41, 0, 0, 12, None, "Rust"),
    "NetOS": (120, 0, 0, 0, None, "C++"),
    "Finwise": (200, 0, 0, 0, None, "TypeScript"),
}


def _days_ago(now, d):
    return iso(now - dt.timedelta(days=d))


class FixtureClient:
    remaining = 4999

    def __init__(self, now: dt.datetime, login: str = "YRB19"):
        self.now, self.login = now, login

    def low_budget(self, floor=100):
        return False

    def rest(self, path, etags=None):
        return 200, {}

    def graphql(self, query, variables):
        if "contributionsCollection" in query:
            return self._contrib()
        return {"user": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": self._nodes()}}}

    def _nodes(self):
        nodes = []
        for name, (push, c7, c30, c90, rel, lang) in _SPEC.items():
            releases = [{"name": f"{name} v1.0", "tagName": "v1.0", "publishedAt": _days_ago(self.now, rel), "url": f"https://github.com/YRB19/{name}/releases/tag/v1.0", "isPrerelease": False, "isDraft": False}] if rel is not None else []
            sha = (name.lower() * 8)[:40].encode().hex()[:40]
            nodes.append({
                "name": name, "nameWithOwner": f"YRB19/{name}", "url": f"https://github.com/YRB19/{name}",
                "description": f"Synthetic fixture description for {name}", "isPrivate": False, "isFork": False, "isArchived": False,
                "createdAt": _days_ago(self.now, 300), "pushedAt": _days_ago(self.now, push), "updatedAt": _days_ago(self.now, push),
                "primaryLanguage": {"name": lang},
                "languages": {"edges": [{"size": 10000 + 100 * len(name), "node": {"name": lang}}, {"size": 500, "node": {"name": "Shell"}}]},
                "stargazerCount": 0, "forkCount": 0, "openIssues": {"totalCount": 1}, "openPRs": {"totalCount": 0},
                "repositoryTopics": {"nodes": []}, "licenseInfo": {"spdxId": "MIT"},
                "defaultBranchRef": {"name": "main", "target": {
                    "c7": {"totalCount": c7}, "c30": {"totalCount": c30}, "c90": {"totalCount": c90},
                    "recent": {"nodes": [
                        {"oid": sha, "committedDate": _days_ago(self.now, push), "messageHeadline": "Add feature pipeline", "url": f"https://github.com/YRB19/{name}/commit/{sha}",
                         "changedFilesIfAvailable": 3, "parents": {"totalCount": 1}, "author": {"name": "Rishit", "user": {"login": "YRB19"}}},
                        {"oid": "b" * 40, "committedDate": _days_ago(self.now, push + 1), "messageHeadline": "chore: bump deps", "url": f"https://github.com/YRB19/{name}/commit/{'b' * 40}",
                         "changedFilesIfAvailable": 1, "parents": {"totalCount": 1}, "author": {"name": "dependabot[bot]", "user": None}},
                    ]},
                }},
                "releases": {"nodes": releases},
                "mergedPRs": {"nodes": []},
            })
        return nodes

    def _contrib(self):
        days = [{"date": (self.now - dt.timedelta(days=i)).date().isoformat(), "contributionCount": (i * 7) % 5} for i in range(364, -1, -1)]
        weeks = [{"contributionDays": days[i:i + 7]} for i in range(0, len(days), 7)]
        return {"user": {
            "pulse": {"totalCommitContributions": 47, "totalPullRequestContributions": 12, "totalPullRequestReviewContributions": 0,
                      "totalIssueContributions": 3, "totalRepositoryContributions": 1, "commitContributionsByRepository": [{"contributions": {"totalCount": 1}}] * 6},
            "year": {"contributionCalendar": {"totalContributions": sum(d["contributionCount"] for d in days), "weeks": weeks}},
        }}
