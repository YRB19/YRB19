"""Recently Shipped: releases > merged PRs > meaningful commits."""
import re

from ..storage.cache import parse_iso
from .scoring import within

_NOISE = re.compile(r"^(chore|docs|style|wip|merge|bump)", re.I)
TIER = {"release": 0, "merged": 1, "update": 2}


def meaningful(c: dict) -> bool:
    if c["is_bot"] or c["is_merge"] or _NOISE.match(c["headline"].strip()):
        return False
    files = c.get("changed_files")
    return files is None or files > 0


def collect(repos, activity, releases, now, *, window_days, max_items, per_repo=2) -> list:
    items = []
    for r in repos:
        if r["is_private"]:
            continue
        name = r["full_name"]
        cand = []
        for rel in releases.get(name, []):
            cand.append({"kind": "release", "date": rel["published_at"], "url": rel["url"], "repo": r["name"], "full_name": name})
        for pr in activity.get(name, {}).get("merged_prs", []):
            cand.append({"kind": "merged", "date": pr["merged_at"], "url": pr["url"], "repo": r["name"], "full_name": name})
        for c in activity.get(name, {}).get("recent_commits", []):
            if meaningful(c):
                cand.append({"kind": "update", "date": c["date"], "url": c["url"], "repo": r["name"], "full_name": name})
        cand = [c for c in cand if within(c["date"], now, window_days)]
        cand.sort(key=lambda c: (TIER[c["kind"]], -parse_iso(c["date"]).timestamp()))
        items.extend(cand[:per_repo])
    items.sort(key=lambda c: (-parse_iso(c["date"]).timestamp(), c["full_name"]))
    return items[:max_items]
