"""Recently Shipped: releases > merged PRs > meaningful commits."""
import re

from ..storage.cache import parse_iso
from .scoring import within

_NOISE = re.compile(r"^(chore|docs|style|wip|merge|bump)", re.I)
TIER = {"release": 0, "merged": 1, "update": 2}
# Headlines that say nothing about what shipped: dropped rather than shown ("update", "fix", "Update README.md" ...).
_GENERIC = re.compile(
    r"^(initial commit|first commit|init|update|updates|updated|fix|fixes|fixed|changes?|minor( changes| fixes)?|"
    r"misc|stuff|test|tests|testing|commit|save|progress|done|cleanup|clean up|refactor|tweaks?|"
    r"(update|create|add|delete|upload|rename|edit)(d)? ([\w./-]*\.(md|txt|json|ya?ml|toml|lock)|\.gitignore))\.?$", re.I)


def is_generic(text: str) -> bool:
    t = (text or "").strip()
    return len(t) < 4 or len(t.split()) < 2 and not re.search(r"[A-Za-z]{6,}", t) or bool(_GENERIC.match(t))


def clean(text: str, limit: int = 72) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


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
            tag = rel.get("tag") or rel.get("name") or ""
            if not tag:
                continue
            cand.append({"kind": "release", "date": rel["published_at"], "url": rel["url"], "repo": r["name"], "full_name": name,
                         "text": f"Release {clean(tag, 40)}"})
        for pr in activity.get(name, {}).get("merged_prs", []):
            if is_generic(pr.get("title", "")):
                continue
            cand.append({"kind": "merged", "date": pr["merged_at"], "url": pr["url"], "repo": r["name"], "full_name": name,
                         "text": clean(pr["title"])})
        for c in activity.get(name, {}).get("recent_commits", []):
            if meaningful(c) and not is_generic(c["headline"]):
                cand.append({"kind": "update", "date": c["date"], "url": c["url"], "repo": r["name"], "full_name": name,
                             "text": clean(c["headline"])})
        cand = [c for c in cand if within(c["date"], now, window_days)]
        cand.sort(key=lambda c: (TIER[c["kind"]], -parse_iso(c["date"]).timestamp()))
        items.extend(cand[:per_repo])
    items.sort(key=lambda c: (-parse_iso(c["date"]).timestamp(), c["full_name"]))
    return items[:max_items]
