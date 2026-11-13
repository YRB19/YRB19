"""View-models for the eight profile-experience features (docs/FEATURES.md).

Same rules as models.py: pure data, no markup; return None / empty when the data cannot support the visual, so callers
hide it instead of drawing zeros that were never measured. Everything is derived from datasets ProfileOS already
holds (repos, contributions calendar, profile counts). The README SVGs and any future Pages app consume these
functions, so the two presentation layers cannot compute different versions of the same metric.
"""
import datetime as dt
import math

from ..analytics import discovery, shipped
from ..sanitize import clean_text, url as safe_url
from . import models

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---- shared: the contribution calendar (one parse, used by City, Rhythm, Pet) -----------------------------------
def calendar_days(ctx) -> list:
    """[(date, count)] sorted by date, from the SAME calendar the (retired) heatmap used. Nothing is filled in."""
    cal = (ctx.ds.get("contributions") or {}).get("calendar") or {}
    days = cal.get("days") or []
    return sorted(((dt.date.fromisoformat(d["date"]), max(0, int(d["count"]))) for d in days), key=lambda t: t[0])


CALENDAR_SCOPE = "GitHub contribution calendar: all activity, including repositories not featured here"


# ---- 2. Profile Signal -------------------------------------------------------------------------------------------
def signal_model(ctx):
    """Four tiles. A tile whose source is unavailable is omitted (never a made-up zero)."""
    tiles, scopes = [], {}
    if "repos" in ctx.ds and ctx.resolved:
        stars = sum(r["stars"] for r in ctx.resolved.values() if not r["is_fork"] and not r["is_private"])
        tiles.append({"key": "stars", "label": "Stars", "scope": "published projects", "value": int(stars)})
        scopes["stars"] = "Sum of stars across public, non-fork repositories published on this profile (profile repository and unpublished projects excluded)."
    days = calendar_days(ctx)
    if days:
        total = int((ctx.ds["contributions"]["calendar"]).get("total", sum(c for _, c in days)))
        tiles.append({"key": "contributions", "label": "Contributions", "scope": "last 12 months", "value": total})
        scopes["contributions"] = f"{CALENDAR_SCOPE}, {days[0][0].isoformat()} to {days[-1][0].isoformat()}."
    prof = ctx.ds.get("profile") or {}
    if isinstance(prof.get("public_repos"), int):
        tiles.append({"key": "repositories", "label": "Repositories", "scope": "public on GitHub", "value": prof["public_repos"]})
        scopes["repositories"] = "The GitHub account's public repository count (not the number of featured projects)."
    if isinstance(prof.get("followers"), int):
        tiles.append({"key": "followers", "label": "Followers", "scope": "on GitHub", "value": prof["followers"]})
        scopes["followers"] = "The account's current follower count (no history is recorded)."
    if not tiles:
        return None
    # fixed order: stars, contributions, repositories, followers
    order = {"stars": 0, "contributions": 1, "repositories": 2, "followers": 3}
    tiles.sort(key=lambda t: order[t["key"]])
    return {"tiles": tiles, "generated_at": ctx.snapshot_date, "metric_scopes": scopes,
            "note": "Snapshot of the latest update. Activity indicators."}


# ---- 3. Building in Public ---------------------------------------------------------------------------------------
def building_model(ctx):
    """building / exploring / learning are HUMAN-declared (profile.yml). recent_ships and active_repositories are derived
    from GitHub and labelled as such; commit volume is never read as intent."""
    now = ctx.prof.get("now", {})
    building = []
    for slug in now.get("building", []):
        p = ctx.projects.get(slug)
        if p and models.publishable(p):
            r = ctx.resolved.get(slug)
            building.append({"slug": slug, "title": models._title(ctx, slug), "url": r["url"] if r else None})
    ships = []
    active = []
    new_builds = []
    if "repos" in ctx.ds:
        for it in shipped.collect(ctx.repos, ctx.activity, ctx.releases, ctx.now,
                                  window_days=ctx.cfg.get("shipped_window_days", 60),
                                  max_items=ctx.display.get("max_recently_shipped", 6)):
            ships.append(it)
        limit = ctx.display.get("max_currently_building", 5)
        for slug, st, *_ in ctx.states()[:limit]:
            if st == "active":
                active.append({"slug": slug, "title": models._title(ctx, slug), "url": ctx.resolved[slug]["url"]})
        known = {(p.get("repo") or "").lower() for p in ctx.projects.values()}
        for nb in discovery.new_builds(ctx.first_seen, ctx.repos, known, ctx.now, ctx.cfg.get("new_build_days", 14)):
            new_builds.append(nb)
    out = {"building": building, "exploring": list(now.get("exploring", [])), "learning": list(now.get("learning", [])),
           "recent_ships": ships, "active_repositories": active, "new_builds": new_builds}
    return out if any(out.values()) else None


# ---- 1. Project Map ----------------------------------------------------------------------------------------------
SIG_LANG_PCT = 15.0        # a language links two projects only if it is >= 15% of the bytes in BOTH repositories
MAX_EDGES_PER_NODE = 3     # static README only: strongest N per node; the complete list stays in `edges`
R_MIN, R_MAX, R_FULL_AT = 11.0, 20.0, 50   # node radius bounds; stars saturate the scale at 50


def star_radius(stars: int) -> float:
    """Bounded logarithmic scale: 0 stars -> R_MIN (always visible); >= 50 stars -> R_MAX (can never dominate)."""
    t = min(1.0, math.log1p(max(0, stars)) / math.log1p(R_FULL_AT))
    return round(R_MIN + (R_MAX - R_MIN) * t, 2)


def significant_languages(languages: dict, primary=None) -> set:
    total = sum(languages.values())
    out = {l for l, b in languages.items() if total and b * 100.0 / total >= SIG_LANG_PCT}
    if primary and languages.get(primary):
        out.add(primary)
    return out


def map_edges(nodes: list) -> list:
    """Evidence-based relationships only: shared significant language, or shared GitHub topic. Never by name."""
    edges = []
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            langs = sorted(set(a["languages"]) & set(b["languages"]))
            topics = sorted(set(a["topics"]) & set(b["topics"]))
            if langs or topics:
                edges.append({"source": a["slug"], "target": b["slug"], "shared_languages": langs, "shared_topics": topics,
                              "strength": len(langs) + len(topics)})
    return edges


def cap_edges(edges: list, per_node: int = MAX_EDGES_PER_NODE) -> list:
    """Keep an edge if it is among the strongest `per_node` of EITHER endpoint (deterministic tie-break by names)."""
    def rank(e):
        return (-e["strength"], -len(e["shared_topics"]), e["source"], e["target"])
    keep = set()
    nodes = {x for e in edges for x in (e["source"], e["target"])}
    for n in sorted(nodes):
        mine = sorted((e for e in edges if n in (e["source"], e["target"])), key=rank)
        keep.update((e["source"], e["target"]) for e in mine[:per_node])
    return [e for e in sorted(edges, key=rank) if (e["source"], e["target"]) in keep]


def project_map_model(ctx):
    display = ctx.d["categories"]["display"]
    nodes = []
    for slug in models.ordered_projects(ctx):      # ctx.resolved: published, public, resolved to a real repository
        p, r = ctx.projects[slug], ctx.resolved[slug]
        if r["is_fork"] or r["is_private"]:
            continue
        langs = significant_languages(r.get("languages") or {}, r.get("primary_language"))
        nodes.append({
            "slug": slug, "name": models._title(ctx, slug), "url": r["url"], "category": p["category"],
            "category_label": display.get(p["category"], {}).get("label", ""),
            "language": r.get("primary_language"), "languages": sorted(langs), "topics": list(r.get("topics") or []),
            "stars": int(r["stars"]), "radius": star_radius(int(r["stars"])), "os_series": p.get("family") == "os-series",
        })
    if len(nodes) < 2:
        return None
    edges = map_edges(nodes)
    return {"nodes": nodes, "edges": edges, "static_edges": cap_edges(edges),
            "show_stars": bool(ctx.display.get("show_zero_stars", False)),
            "pages_url": (ctx.cfg.get("pages") or {}).get("url")}


# ---- 7. Language bubbles -----------------------------------------------------------------------------------------
MAX_BUBBLES = 7


def bubbles_model(ctx):
    """Bytes of code per language across public, non-fork, non-archived, non-excluded repositories (the same dataset
    and filters as the retired language bar). Size = byte share; not skill, expertise or time spent."""
    excl_l = set(ctx.cfg.get("exclude_languages", []))
    excl_r = {x.lower() for x in list(ctx.cfg.get("exclude_repos", [])) + list(ctx.ov.get("exclude_repos", []))}
    totals, repos = {}, {}
    for r in ctx.repos:
        if r["is_private"] or r["is_fork"] or r["is_archived"] or r["full_name"].lower() in excl_r:
            continue
        for lang, size in (r.get("languages") or {}).items():
            if lang in excl_l or size <= 0:
                continue
            totals[lang] = totals.get(lang, 0) + size
            repos.setdefault(lang, []).append(r["name"])
    grand = sum(totals.values())
    if not grand:
        return None
    min_pct = ctx.cfg.get("min_language_pct", 2)
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    named = [(l, b) for l, b in ranked if b * 100.0 / grand >= min_pct][:MAX_BUBBLES]
    shown = {l for l, _ in named}
    other_bytes = sum(b for l, b in ranked if l not in shown)
    items = [{"language": clean_text(l, 24), "bytes": b, "percentage": round(b * 100.0 / grand, 1),
              "repositories": sorted(repos[l], key=str.lower)} for l, b in named]
    if other_bytes > 0:
        items.append({"language": "Other", "bytes": other_bytes, "percentage": round(other_bytes * 100.0 / grand, 1),
                      "repositories": sorted({n for l, _ in ranked if l not in shown for n in repos[l]}, key=str.lower)})
    return {"items": items, "total_bytes": grand,
            "note": ""}


# ---- 5. Contribution City ----------------------------------------------------------------------------------------
LEVEL_HEIGHTS = (0, 5, 10, 16, 24)     # level 0 = flat ground tile; 1-4 = bounded building heights (SVG units)


def city_model(ctx):
    """One tile per calendar day, levels from the shared heatmap model (so City and the data agree exactly).
    Level 0 = no contributions; level L (1-4) = 1 + min(3, (count-1)*4 // busiest_day)."""
    hm = models.heatmap_model(ctx)
    if not hm:
        return None
    days = calendar_days(ctx)
    return {"cells": hm["cells"], "ncols": hm["ncols"], "total": hm["total"], "active_days": hm["active_days"],
            "max_day": hm["max_day"], "date_range": [days[0][0].isoformat(), days[-1][0].isoformat()],
            "source_scope": CALENDAR_SCOPE, "heights": list(LEVEL_HEIGHTS),
            "note": "One tile per day, height = relative daily contributions."}


# ---- 6. Activity Rhythm ------------------------------------------------------------------------------------------
MIN_RHYTHM_DAYS = 56       # fewer days of calendar than this, or too few contributions: the visual is hidden
MIN_RHYTHM_TOTAL = 14


def rhythm_model(ctx):
    days = calendar_days(ctx)
    if len(days) < MIN_RHYTHM_DAYS:
        return None
    counts = [0] * 7
    for d, c in days:
        counts[d.weekday()] += c
    total = sum(counts)
    if total < MIN_RHYTHM_TOTAL:
        return None
    rows = [{"weekday": WEEKDAYS[i], "name": WEEKDAY_NAMES[i], "count": counts[i], "percentage": round(counts[i] * 100.0 / total, 1)}
            for i in range(7)]
    return {"rows": rows, "total": total, "window": [days[0][0].isoformat(), days[-1][0].isoformat()],
            "source_scope": CALENDAR_SCOPE,
            "note": "Contributions by calendar weekday over the last 12 months."}


# ---- 4. Code Pet -------------------------------------------------------------------------------------------------
MOODS = ("Resting", "Warming up", "Active", "Thriving")        # by ACTIVE DAYS in the last 7 days: 0 / 1-2 / 3-4 / 5+
FOODS = ("No activity", "Light", "Fed", "Well fed")           # by CONTRIBUTIONS in the last 7 days: 0 / 1-9 / 10-24 / 25+
GROWTH = ("Newborn", "Growing", "Young", "Adult", "Veteran")  # by contributions over the calendar window
GROWTH_AT = (0, 100, 400, 800, 1500)


def _index(value: int, floors) -> int:
    return max(i for i, f in enumerate(floors) if value >= f)


def mood_index(active_days: int) -> int:
    return 0 if active_days <= 0 else 1 if active_days <= 2 else 2 if active_days <= 4 else 3


def food_index(week_total: int) -> int:
    return 0 if week_total <= 0 else 1 if week_total <= 9 else 2 if week_total <= 24 else 3


def streaks(days):
    """(current, longest). The calendar's last day is the day the data was fetched, so it may still be in progress: it extends
    the streak if it has contributions and is otherwise skipped, never counted as a miss. Pure arithmetic over the real
    calendar (no wall clock, so a stale cache renders identically until fresh data arrives)."""
    by = dict(days)
    last = days[-1][0]
    cur_end = last if by[last] > 0 else last - dt.timedelta(days=1)
    cur, d = 0, cur_end
    while by.get(d, 0) > 0:
        cur += 1
        d -= dt.timedelta(days=1)
    longest = run = 0
    prev = None
    for d, c in days:
        run = run + 1 if c > 0 and prev is not None and (d - prev).days == 1 and run > 0 else (1 if c > 0 else 0)
        longest = max(longest, run)
        prev = d
    return cur, longest


def pet_model(ctx):
    days = calendar_days(ctx)
    if not days:
        return None
    last = days[-1][0]
    week = [(d, c) for d, c in days if (last - d).days < 7]
    week_total = sum(c for _, c in week)
    active = sum(1 for _, c in week if c > 0)
    window_total = sum(c for _, c in days)
    cur, longest = streaks(days)
    completed = last - dt.timedelta(days=1)       # the last calendar day is the fetch day: possibly incomplete
    latest = dict(days).get(completed)
    computed = _index(window_total, GROWTH_AT)
    peak = max(computed, int(getattr(ctx, "pet_peak", 0) or 0))   # growth never goes backwards (high-water mark, real data only)
    return {
        "mood": MOODS[mood_index(active)], "mood_index": mood_index(active),
        "food": FOODS[food_index(week_total)], "food_index": food_index(week_total),
        "growth_level": GROWTH[peak], "growth_index": peak, "growth_computed_index": computed,
        "weekly_contributions": week_total, "active_days_week": active, "growth_period_total": window_total,
        "current_streak": cur, "longest_streak": longest, "latest_completed_day": completed.isoformat(),
        "latest_completed_day_count": latest, "window": [days[0][0].isoformat(), last.isoformat()],
        "generated_at": ctx.snapshot_date,
        "note": "A playful snapshot of GitHub contributions.",
    }


# ---- 8. Collaboration CTA ----------------------------------------------------------------------------------------
def collaboration_model(ctx):
    c = ctx.prof.get("collaboration") or {}
    if not c.get("headline"):
        return None
    links = []
    for l in ctx.d["links"]["links"]:           # only links approved in links.yml, each re-checked as a safe public URL
        if safe_url(l["url"]):
            links.append({"label": clean_text(l["label"], 30), "url": l["url"]})
    pages = (ctx.cfg.get("pages") or {}).get("url")
    return {"headline": clean_text(c["headline"], 90), "description": clean_text(c.get("description"), 200) or None,
            "approved_links": links, "pages_url": pages if pages and safe_url(pages) else None}
