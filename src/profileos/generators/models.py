"""View-models shared by the Markdown renderers and the SVG components.

Pure data, no markup. Every function returns None (or an empty list) when the data to support it is missing,
so callers hide the visual instead of showing empty labels, zeros that were never measured, or broken shapes.
Nothing here ranks projects by quality; ordering is curated (pin order, then manual priority).
"""
import datetime as dt

from ..analytics import languages, scoring
from ..sanitize import clean_text

STATUS_LABEL = {
    "active": "ACTIVE", "experimental": "EXPERIMENTAL", "maintained": "MAINTAINED",
    "paused": "PAUSED", "archived": "ARCHIVED",
}
EVIDENCE_OK = ("HIGH", "MEDIUM", "STATED")
MAX_LANGUAGES = 6
MAX_ACTIVITY_ROWS = 6
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---- publishing rules --------------------------------------------------------------------------------------
def publishable(project: dict) -> bool:
    """Internal-only projects (`publish: false`, or status private) never appear in generated public output."""
    return project.get("publish", True) is not False and project.get("status") != "private"


def excluded_repos(data: dict) -> set:
    """Lower-case owner/name of every repo that must never reach public output OR the committed cache:
    config/override exclusions (e.g. the profile repo itself) and internal-only (`publish: false`) projects.
    One rule, used by the fetch filters, the cache and the renderers, so they cannot drift apart."""
    handle = data["profile"]["identity"]["handle"].lower()
    hidden = set()
    for slug, p in data["projects"].items():
        if publishable(p):
            continue
        if p.get("repo"):
            hidden.add(p["repo"].lower())
        hidden.update(f"{handle}/{a}".lower() for a, target in data["aliases"]["aliases"].items() if target == slug)
    listed = list(data["config"].get("exclude_repos", [])) + list(data["overrides"].get("exclude_repos", []))
    return hidden | {x.lower() for x in listed}


# ---- Phase 6: CI / deployment health / releases ------------------------------------------------------------------
CI_LABEL = {"passing": "CI passing", "failing": "CI failing", "in_progress": "CI running", "queued": "CI queued", "cancelled": "CI cancelled"}
HEALTH_LABEL = {"online": "Online", "degraded": "Degraded", "offline": "Offline"}


def _chip(rec, labels, *, date_key):
    """A status may be drawn only if it is positive evidence of a known state. unknown / not_configured -> None."""
    if not rec or rec.get("state") not in labels:
        return None
    day = (rec.get(date_key) or "")[:10]
    chip = {"state": rec["state"], "label": labels[rec["state"]]}
    if date_key == "run_at":                      # CI: the chip names the date of the run it describes, cached or not
        if day:
            chip["date"] = day
    elif rec.get("stale"):                        # health served from an old cache: say so, with the date
        chip["as_of"] = (rec.get("checked_at") or "")[:10] or None
    return chip


def ci_chip(ctx, slug):
    p = ctx.projects[slug]
    if not ctx.cfg.get("ci", {}).get("enabled", True) or (p.get("ci") or {}).get("track") is False:
        return None
    r = ctx.resolved.get(slug)
    return _chip(ctx.ci.get(r["full_name"]) if r else None, CI_LABEL, date_key="run_at")


def health_chip(ctx, slug):
    p = ctx.projects[slug]
    if (p.get("deployment") or {}).get("health_check") is not True:
        return None
    return _chip(ctx.health.get(slug), HEALTH_LABEL, date_key="checked_at")


def latest_release(releases) -> dict | None:
    """Newest *published* non-draft release by publish date (the API list is ordered by creation, not publication)."""
    ok = [r for r in releases or [] if not r.get("draft") and not r.get("isDraft") and r.get("published_at") and r.get("tag")]
    return max(ok, key=lambda r: (r["published_at"], r["tag"])) if ok else None


def release_rows(ctx, limit: int = 8) -> list[dict]:
    """Compact release tracker: one row per published project that really has a published release. Curated order."""
    rows = []
    for slug in ordered_projects(ctx):
        rel = latest_release(ctx.releases.get(ctx.resolved[slug]["full_name"], []))
        if not rel:
            continue
        rows.append({"slug": slug, "title": _title(ctx, slug), "repo_url": ctx.resolved[slug]["url"],
                     "tag": clean_text(rel["tag"], 24), "url": rel["url"], "date": rel["published_at"][:10],
                     "prerelease": bool(rel.get("prerelease"))})
    return rows[:limit]


def status_key(ctx, slug):
    """A project's status is displayed only when an evidence record (HIGH/MEDIUM/STATED) backs it."""
    rec = (ctx.d["evidence"].get("projects", {}).get(slug, {}) or {}).get("status")
    if rec and rec.get("confidence") in EVIDENCE_OK:
        return ctx.projects[slug]["status"]
    return None


def ordered_flagships(ctx) -> list[str]:
    flag = [s for s, p in ctx.projects.items() if p.get("featured") and publishable(p) and s in ctx.resolved]
    pins = [s for s in ctx.ov.get("pin_order", []) if s in flag]
    rest = sorted((s for s in flag if s not in pins), key=lambda s: (-ctx.projects[s].get("priority", 50), s))
    return pins + rest


def ordered_projects(ctx) -> list[str]:
    """Flagships first (curated order), then secondary projects by manual priority then name."""
    flag = ordered_flagships(ctx)
    rest = sorted((s for s in ctx.resolved if s not in flag), key=lambda s: (-ctx.projects[s].get("priority", 50), s))
    return flag + rest


def _title(ctx, slug) -> str:
    return clean_text(ctx.projects[slug].get("title") or slug, 40)


# ---- Development Pulse -------------------------------------------------------------------------------------
def pulse_model(ctx):
    c = ctx.ds.get("contributions")
    if not c:
        return None
    p = c["pulse"]
    tiles = [
        {"label": "Commits", "noun": ("commit", "commits"), "value": int(p["commits"])},
        {"label": "Repos committed to", "noun": ("repository committed to", "repositories committed to"), "value": int(p["repos_touched"])},
        {"label": "Pull requests", "noun": ("pull request", "pull requests"), "value": int(p["pull_requests"])},
    ]
    if "repos" in ctx.ds:  # a release count is only honest when release data exists
        rels = sum(1 for r in ctx.repos for x in ctx.releases.get(r["full_name"], []) if scoring.within(x["published_at"], ctx.now, 30))
        tiles.append({"label": "Releases", "noun": ("release", "releases"), "value": rels})
    if p.get("scope") == "public-shown":
        note = "Public repositories shown on this profile. Activity indicators, not measures of quality."
    else:  # cache written before scope filtering existed: do not claim a scope we cannot vouch for
        note = "GitHub contribution counts. Activity indicators, not measures of quality."
    return {"window": "Last 30 days", "tiles": tiles, "note": note}


# ---- Commits by project ------------------------------------------------------------------------------------
def activity_model(ctx):
    rows = []
    for slug in ordered_projects(ctx):
        c30 = ctx.metrics(ctx.resolved[slug])["c30"]
        if c30 > 0:
            rows.append({"slug": slug, "label": _title(ctx, slug), "value": int(c30)})
    rows = rows[:MAX_ACTIVITY_ROWS]
    if not rows:
        return None
    return {"window": "Last 30 days", "rows": rows, "note": "Projects shown on this profile, default-branch commits. An activity signal."}


# ---- Contribution heatmap ----------------------------------------------------------------------------------
def heatmap_model(ctx):
    cal = (ctx.ds.get("contributions") or {}).get("calendar") or {}
    days = cal.get("days") or []
    if not days:
        return None
    parsed = sorted(((dt.date.fromisoformat(d["date"]), max(0, int(d["count"]))) for d in days), key=lambda t: t[0])
    first = parsed[0][0]
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # the Sunday on/before the first day
    top = max(c for _, c in parsed)
    cells = []
    for d, c in parsed:
        col, row = divmod((d - start).days, 7)
        level = 0 if c <= 0 else 1 + min(3, (c - 1) * 4 // max(1, top))
        cells.append({"col": col, "row": row, "date": d.isoformat(), "count": c, "level": level})
    ncols = cells[-1]["col"] + 1
    months, prev = [], None
    for col in range(ncols):
        m = (start + dt.timedelta(days=7 * col)).month
        if m != prev:
            months.append({"col": col, "label": MONTHS[m - 1]})
            prev = m
    if len(months) > 1 and months[1]["col"] - months[0]["col"] < 4:
        months = months[1:]  # a partial first month would collide with the next label
    total = int(cal.get("total", sum(c for _, c in parsed)))
    return {
        "ncols": ncols, "cells": cells, "months": months, "total": total,
        "active_days": sum(1 for _, c in parsed if c > 0), "max_day": top,
        "note": "GitHub's contribution calendar: all activity, including repositories not featured here. Activity indicators, not measures of quality.",
    }


# ---- Phase 7: history -----------------------------------------------------------------------------------------------
MONTH_NAMES = MONTHS


def monthly_model(ctx):
    """Commits per month = SUM of stored closed-day counts (docs/SNAPSHOTS.md). Shown only once at least two months have
    recorded data; partial months are starred and say so. Nothing is estimated or extrapolated."""
    st = getattr(ctx, "history", None)
    cfg = ctx.cfg.get("snapshots", {})
    months = (st.monthly if st else [])[-int(cfg.get("chart_months", 12)):]
    if len(months) < 2:
        return None
    rows, partial = [], False
    for m in months:
        y, mo = m["month"].split("-")
        star = "" if m["coverage"]["complete"] else "*"
        partial = partial or bool(star)
        rows.append({"label": f"{MONTH_NAMES[int(mo) - 1]} {y[2:]}{star}", "value": int(m["metrics"]["commits"]["value"])})
    note = ("Commits per month, summed from daily snapshots of the public repositories shown here. "
            + ("* = partial month: only recorded days are counted. " if partial else "")
            + "An activity signal, not a quality measure.")
    return {"title": "Commits by month", "window": f"Last {len(rows)} months", "rows": rows, "note": note}


def timeline_rows(ctx):
    """Newest-first verified events for projects that are CURRENTLY published (the stored file is a faithful record; what it
    shows publicly is decided here). Hidden until there are at least `min_timeline_events`."""
    st = getattr(ctx, "history", None)
    cfg = ctx.cfg.get("snapshots", {})
    if not st or not st.timeline:
        return []
    ok = {s for s, p in ctx.projects.items() if publishable(p)}
    events = [e for e in st.timeline["events"] if e["project"] in ok]
    if len(events) < int(cfg.get("min_timeline_events", 3)):
        return []
    events.sort(key=lambda e: (e["date"], e["id"]), reverse=True)
    out = []
    for e in events[: int(cfg.get("timeline_max_items", 8))]:
        out.append({"date": e["date"], "project": _title(ctx, e["project"]), "title": clean_text(e["title"], 80),
                    "url": e["source"].get("url"), "type": e["type"]})
    return out


# ---- Language distribution ---------------------------------------------------------------------------------
def language_model(ctx, max_items: int = MAX_LANGUAGES):
    dist = languages.distribution(
        ctx.repos,
        exclude_languages=ctx.cfg.get("exclude_languages", []),
        exclude_repos=list(ctx.cfg.get("exclude_repos", [])) + list(ctx.ov.get("exclude_repos", [])),
        min_pct=ctx.cfg.get("min_language_pct", 2),
    )
    if not dist:
        return None
    named = [x for x in dist if x["language"] != "Other"]
    other = sum(x["pct"] for x in dist if x["language"] == "Other")
    if len(named) > max_items:
        other += sum(x["pct"] for x in named[max_items:])
        named = named[:max_items]
    items = [{"language": clean_text(x["language"], 24), "pct": x["pct"]} for x in named]
    if other > 0:
        items.append({"language": "Other", "pct": round(other, 1)})
    return {"items": items, "note": "Public non-fork repositories, by bytes of code. Not a skill measure."}


# ---- Project cards -----------------------------------------------------------------------------------------
def card_models(ctx) -> list[dict]:
    out = []
    show_zero = ctx.display.get("show_zero_stars", False)
    for slug in ordered_flagships(ctx):
        p, r = ctx.projects[slug], ctx.resolved[slug]
        hide = set(ctx.ov.get("hide_fields", {}).get(slug, []))
        verified = bool(p.get("verified"))
        # verified cards use evidence-backed text; unverified cards fall back to GitHub's own description only
        tagline = clean_text(p.get("tagline"), 90) if verified and p.get("tagline") else clean_text(r.get("description"), 90)
        stack = [clean_text(x, 30) for x in (p.get("stack") or [])[:4]] if verified else []
        if not stack and r.get("primary_language"):
            stack = [clean_text(r["primary_language"], 30)]
        rel = latest_release(ctx.releases.get(r["full_name"], []))
        out.append({
            "slug": slug,
            "title": _title(ctx, slug),
            "url": r["url"],
            "status": status_key(ctx, slug),
            "tagline": tagline or None,
            "stack": stack,
            "release": {"tag": clean_text(rel["tag"], 24), "url": rel["url"], "prerelease": bool(rel.get("prerelease"))} if rel else None,
            "ci": ci_chip(ctx, slug),
            "health": health_chip(ctx, slug),
            "stars": r["stars"] if "stars" not in hide and (r["stars"] or show_zero) else None,
            "forks": r["forks"] if "forks" not in hide and (r["forks"] or show_zero) else None,
            "last_push": r["pushed_at"][:10] if r.get("pushed_at") else None,
            "demo": p.get("demo"),
            "docs": p.get("docs"),
        })
    return out


# ---- OS-series ecosystem -----------------------------------------------------------------------------------
def os_members(ctx) -> list[str]:
    """Published OS-series projects in curated order. Names are curated facts, so they survive an API outage."""
    members = [
        s for s, p in ctx.projects.items()
        if p.get("family") == "os-series" and publishable(p)
        and (s in ctx.resolved or p.get("show_unlinked") or "repos" not in ctx.ds)
    ]
    return sorted(members, key=lambda s: (-ctx.projects[s].get("priority", 50), s))


def ecosystem_model(ctx):
    members = os_members(ctx)
    if len(members) < 2:
        return None
    display = ctx.d["categories"]["display"]
    nodes = [{
        "slug": s, "label": _title(ctx, s),
        "category": display.get(ctx.projects[s]["category"], {}).get("label", ""),
    } for s in members]
    names = set(members)
    edges = [
        {"from": r["from"], "to": r["to"], "label": clean_text(r.get("label"), 24) or None}
        for s in members for r in ctx.projects[s].get("relations", [])
        if r["from"] in names and r["to"] in names
    ]
    return {"nodes": nodes, "edges": edges}
