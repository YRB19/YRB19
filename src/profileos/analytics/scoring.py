"""Internal scoring. Never displayed; used only to decide ordering and active/quiet state."""
import datetime as dt
import math

from ..storage.cache import parse_iso


def days_since(ts: str | None, now: dt.datetime) -> float:
    if not ts:
        return 9999.0
    return max(0.0, (now - parse_iso(ts)).total_seconds() / 86400.0)


def within(ts: str | None, now: dt.datetime, days: int) -> bool:
    return bool(ts) and days_since(ts, now) <= days


def activity_score(*, commits_7d, commits_30d, prs_30d, releases_30d, pushed_at, priority, now, weights) -> float:
    recency = math.exp(-days_since(pushed_at, now) / 14)
    volume = min(1.0, math.log1p(commits_30d) / math.log1p(40))
    momentum = min(1.0, (commits_7d * 2 + prs_30d + releases_30d * 3) / 15)
    manual = (priority if priority is not None else 50) / 100
    w = weights
    return w["recency"] * recency + w["volume"] * volume + w["momentum"] * momentum + w["manual"] * manual


def state_for(status: str, score: float, focus: str | None, thresholds: dict):
    """Return 'active' | 'quiet' | None (not shown). Order follows spec §4.4."""
    if focus == "hide":
        return None
    if focus == "force_active":
        return "active"
    if focus == "force_quiet":
        return "quiet"
    if status in ("paused", "archived", "private"):
        return None
    if score >= thresholds["active"]:
        return "active"
    if score >= thresholds["quiet"]:
        return "quiet"
    return None


def priority_index(*, manual_priority, activity, has_release, ci=None, docs=None, tests=None, deployed=None, issue_hygiene=None) -> float:
    """§4.9. Signals we can't observe yet (None) are neutral 0.5 so they neither help nor hurt."""
    n = lambda v: 0.5 if v is None else float(v)  # noqa: E731
    return (
        0.30 * (manual_priority if manual_priority is not None else 50) / 100
        + 0.25 * activity
        + 0.10 * (1.0 if has_release else 0.0)
        + 0.10 * n(ci)
        + 0.10 * n(docs)
        + 0.05 * n(tests)
        + 0.05 * n(deployed)
        + 0.05 * n(issue_hygiene)
    )
