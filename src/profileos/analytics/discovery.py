"""New repository detection via repo-list diff against the previous snapshot."""
import datetime as dt

from ..storage.cache import parse_iso


def update_first_seen(prev: dict | None, repos: list, now: dt.datetime) -> dict:
    """prev: {full_name: first_seen_date}. First ever run seeds with created_at (nothing looks 'new')."""
    today = now.date().isoformat()
    out = dict(prev or {})
    for r in repos:
        if r["is_private"] or r["is_fork"]:
            continue
        if r["full_name"] not in out:
            out[r["full_name"]] = r["created_at"][:10] if prev is None else today
    return dict(sorted(out.items()))


def new_builds(first_seen: dict, repos: list, known_full_names: set, now: dt.datetime, days: int) -> list:
    out = []
    for r in repos:
        fs = first_seen.get(r["full_name"])
        if not fs or r["is_fork"] or r["is_private"] or r["full_name"].lower() in known_full_names:
            continue
        age = (now.date() - dt.date.fromisoformat(fs)).days
        if 0 <= age <= days:
            out.append({"full_name": r["full_name"], "name": r["name"], "url": r["url"], "first_seen": fs})
    return sorted(out, key=lambda x: (x["first_seen"], x["name"]), reverse=True)
