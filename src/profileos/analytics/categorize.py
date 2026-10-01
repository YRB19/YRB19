"""First match wins: manual > topics > description keywords > language hint > fallback."""
import re

from ..storage.cache import parse_iso


def categorize(repo: dict, *, project: dict | None, overrides: dict, categories: dict, earlier_before: str) -> str:
    manual = overrides.get("category_overrides", {}).get(repo["full_name"])
    if manual:
        return manual
    if project and project.get("category"):
        return project["category"]
    topic_map = categories.get("topic_map", {})
    topics = set(repo.get("topics", []))
    for cat, words in topic_map.items():
        if topics & set(words):
            return cat
    desc = (repo.get("description") or "").lower()
    for cat, words in topic_map.items():
        if any(re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", desc) for w in words):
            return cat
    lang = categories.get("language_map", {}).get(repo.get("primary_language") or "")
    if lang:
        return lang
    return "earlier" if parse_iso(repo["created_at"]).date().isoformat() < earlier_before else "experiment"
