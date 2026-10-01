"""Markdown renderers for each registered marker. Every string from repo metadata is sanitised."""
import datetime as dt

from ..analytics import discovery, languages, scoring, shipped
from ..sanitize import md
from ..storage.cache import parse_iso

STATUS = {"active": "● ACTIVE", "experimental": "◐ EXPERIMENTAL", "maintained": "○ MAINTAINED", "paused": "◌ PAUSED", "archived": "■ ARCHIVED"}
BAR = "█"


class Context:
    def __init__(self, data, datasets, ages, now, snapshot_date, first_seen):
        self.d, self.ds, self.ages, self.now, self.snapshot_date = data, datasets, ages, now, snapshot_date
        self.cfg, self.prof, self.ov = data["config"], data["profile"], data["overrides"]
        self.display = self.prof.get("display", {})
        self.projects = data["projects"]
        self.warnings: list[str] = []
        self.repos = [r for r in datasets.get("repos", []) if not r["is_private"] and r["full_name"].lower() not in self._excluded()]
        self.by_full = {r["full_name"].lower(): r for r in self.repos}
        self.activity, self.releases = datasets.get("activity", {}), datasets.get("releases", {})
        self.first_seen = first_seen
        self._alias = {}
        for a, slug in data["aliases"]["aliases"].items():
            self._alias.setdefault(slug, []).append(a.lower())
        self.resolved = {}
        if "repos" in datasets:
            for slug, p in self.projects.items():
                if p.get("status") == "private":
                    continue
                r = self._resolve(slug, p)
                if r:
                    self.resolved[slug] = r
                elif p.get("repo"):
                    self.warnings.append(f"{slug}: repo {p['repo']} not found among public repos — omitted")

    def _excluded(self):
        return {x.lower() for x in list(self.cfg.get("exclude_repos", [])) + list(self.ov.get("exclude_repos", []))}

    def _resolve(self, slug, p):
        if not p.get("repo"):
            return None
        r = self.by_full.get(p["repo"].lower())
        if r:
            return r
        for a in self._alias.get(slug, []):
            for repo in self.repos:
                if repo["name"].lower() == a:
                    return repo
        return None

    # ---- helpers -------------------------------------------------------------------------
    def note(self, *names) -> str:
        limit = self.cfg.get("stale_after_h", 24)
        if any(self.ages.get(n, 0) > limit for n in names):
            return f"<sub>as of {self.snapshot_date}</sub>"
        return ""

    def status_label(self, slug) -> str:
        """Manual status is shown only when evidence backs it (HIGH/MEDIUM/STATED); drafts stay internal."""
        rec = (self.d["evidence"].get("projects", {}).get(slug, {}) or {}).get("status")
        p = self.projects[slug]
        return STATUS[p["status"]] if rec and rec.get("confidence") in ("HIGH", "MEDIUM", "STATED") else ""

    def link(self, slug):
        p, r = self.projects[slug], self.resolved.get(slug)
        label = md(p.get("title") or slug)
        return f"[{label}]({r['url']})" if r else label

    def metrics(self, repo, priority=None):
        act = self.activity.get(repo["full_name"], {"commits": {"d7": 0, "d30": 0, "d90": 0}, "merged_prs": []})
        prs = sum(1 for p in act["merged_prs"] if scoring.within(p["merged_at"], self.now, 30))
        rels = sum(1 for x in self.releases.get(repo["full_name"], []) if scoring.within(x["published_at"], self.now, 30))
        c = act["commits"]
        score = scoring.activity_score(commits_7d=c["d7"], commits_30d=c["d30"], prs_30d=prs, releases_30d=rels,
                                       pushed_at=repo["pushed_at"], priority=priority, now=self.now, weights=self.cfg["weights"])
        return {"c7": c["d7"], "c30": c["d30"], "c90": c["d90"], "prs": prs, "releases": rels, "score": score}

    def states(self):
        """[(slug, state, score, priority)] for Currently Building."""
        out = []
        for slug, repo in self.resolved.items():
            p = self.projects[slug]
            m = self.metrics(repo, p.get("priority", 50))
            st = scoring.state_for(p["status"], m["score"], self.ov.get("focus", {}).get(slug), self.cfg["thresholds"])
            if st:
                out.append((slug, st, m["score"], p.get("priority", 50)))
        out.sort(key=lambda t: (0 if t[1] == "active" else 1, -round(t[2], 2), -t[3], t[0]))
        return out


# ---- renderers ---------------------------------------------------------------------------------
def currently_building(ctx: Context) -> str:
    if "repos" not in ctx.ds:
        return ""
    rows = ctx.states()[: ctx.display.get("max_currently_building", 5)]
    lines = [f"{'●' if st == 'active' else '○'} {ctx.link(slug)} — {'active' if st == 'active' else 'quieter'}" for slug, st, *_ in rows]
    return "  \n".join(lines + ([ctx.note("repos", "activity")] if lines and ctx.note("repos", "activity") else []))


def now_panel(ctx: Context) -> str:
    lines = []
    building = [ctx.link(s) for s, st, *_ in ctx.states() if st == "active"][: ctx.display.get("max_currently_building", 5)]
    if building:
        lines.append("Building: " + " · ".join(building))
    now = ctx.prof.get("now", {})
    for label, key in (("Exploring", "exploring"), ("Learning", "learning"), ("Planning next", "planning_next")):
        if now.get(key):
            lines.append(f"{label}: " + " · ".join(md(x) for x in now[key]))
    if "repos" in ctx.ds and ctx.repos:
        pub = [r for r in ctx.repos if not r["is_fork"]]
        if pub:
            newest = max(pub, key=lambda r: (r["created_at"], r["name"]))
            lines.append(f"Newest build: [{md(newest['name'])}]({newest['url']}) · created {newest['created_at'][:10]}")
            known = {(p.get("repo") or "").lower() for p in ctx.projects.values()}
            best = max(pub, key=lambda r: (ctx.metrics(r, next((p.get("priority") for p in ctx.projects.values() if (p.get("repo") or "").lower() == r["full_name"].lower()), 50))["score"], r["name"]))
            if ctx.metrics(best)["c30"] > 0:
                lines.append(f"Most active (last 30 days): [{md(best['name'])}]({best['url']})")
            for nb in discovery.new_builds(ctx.first_seen, ctx.repos, known, ctx.now, ctx.cfg.get("new_build_days", 14)):
                lines.append(f"New build: [{md(nb['name'])}]({nb['url']}) · first seen {nb['first_seen']}")
    return "  \n".join(["**NOW**"] + lines) if lines else ""


def pulse(ctx: Context) -> str:
    c = ctx.ds.get("contributions")
    if not c:
        return ""
    p = c["pulse"]
    rels = sum(1 for repo in ctx.repos for x in ctx.releases.get(repo["full_name"], []) if scoring.within(x["published_at"], ctx.now, 30))
    out = [
        "| COMMITS (30d) | REPOSITORIES | PRs | RELEASES |",
        "|:-:|:-:|:-:|:-:|",
        f"| {p['commits']} | {p['repos_touched']} | {p['pull_requests']} | {rels} |",
        "",
        "<sub>Activity indicators, not quality measures.</sub>",
    ]
    if ctx.note("contributions"):
        out.append(ctx.note("contributions"))
    return "\n".join(out)


def recently_shipped(ctx: Context) -> str:
    if "repos" not in ctx.ds:
        return ""
    items = shipped.collect(ctx.repos, ctx.activity, ctx.releases, ctx.now,
                            window_days=ctx.cfg.get("shipped_window_days", 60),
                            max_items=ctx.display.get("max_recently_shipped", 6))
    lines = []
    for it in items:
        d = parse_iso(it["date"])
        lines.append(f"`{d:%m/%d}` **{md(it['repo'])}** — [{it['kind']}]({it['url']})")
    return "  \n".join(lines)


def os_series(ctx: Context) -> str:
    members = [s for s, p in ctx.projects.items() if p.get("family") == "os-series" and p["status"] != "private"
               and (s in ctx.resolved or p.get("show_unlinked") or "repos" not in ctx.ds)]
    if not members:
        return ""
    members.sort(key=lambda s: -ctx.projects[s].get("priority", 50))
    out = ["*Building focused systems around messy real-world problems.*", "", " · ".join(ctx.link(s) for s in members)]
    edges = [f"{md(r['from'])} → {md(r['to'])}" + (f" — {md(r['label'])}" if r.get("label") else "")
             for s in members for r in ctx.projects[s].get("relations", [])]
    if edges:
        out += [""] + ["  \n".join(edges)]
    return "\n".join(out)


def _ordered_flagships(ctx: Context):
    flag = [s for s, p in ctx.projects.items() if p.get("featured") and p["status"] != "private" and s in ctx.resolved]
    pins = [s for s in ctx.ov.get("pin_order", []) if s in flag]
    rest = sorted((s for s in flag if s not in pins), key=lambda s: (-ctx.projects[s].get("priority", 50), s))
    return pins + rest


def selected_systems(ctx: Context) -> str:
    cards = []
    for slug in _ordered_flagships(ctx):
        p, r = ctx.projects[slug], ctx.resolved[slug]
        hide = set(ctx.ov.get("hide_fields", {}).get(slug, []))
        head = f"**{ctx.link(slug)}**" + (f" · {ctx.status_label(slug)}" if ctx.status_label(slug) else "")
        verified = p.get("verified")
        blurb = md(p["tagline"]) if verified and p.get("tagline") else (md(r["description"]) if r.get("description") else "")
        bits = []
        stack = p.get("stack") if verified else None
        if stack:
            bits.append(" · ".join(md(x) for x in stack[:4]))
        elif r.get("primary_language"):
            bits.append(md(r["primary_language"]))
        rel = ctx.releases.get(r["full_name"], [])
        if rel:
            bits.append(f"[{md(rel[0]['tag'])}]({rel[0]['url']})")
        show_zero = ctx.display.get("show_zero_stars", False)
        if "stars" not in hide and (r["stars"] or show_zero):
            bits.append(f"★ {r['stars']}")
        if "forks" not in hide and (r["forks"] or show_zero):
            bits.append(f"⑂ {r['forks']}")
        if r.get("pushed_at"):
            bits.append(f"last push {r['pushed_at'][:10]}")
        if p.get("demo"):
            bits.append(f"[demo]({p['demo']})")
        cards.append("  \n".join(x for x in (head, blurb, " · ".join(bits)) if x))
    return "\n\n".join(cards) + (f"\n\n{ctx.note('repos')}" if cards and ctx.note("repos") else "")


def stack(ctx: Context) -> str:
    lines = []
    for group, items in ctx.d["stack"]["groups"].items():
        names = [md(i["name"]) for i in items if i["evidence"]]
        if names:
            lines.append(f"**{md(group)}** · " + " · ".join(names))
    return "  \n".join(lines)


def earlier_builds(ctx: Context) -> str:
    out = []
    groups = [ctx.link(s) for s, p in ctx.projects.items() if p.get("group") == "earlier" and p["status"] != "private" and (s in ctx.resolved or "repos" not in ctx.ds)]
    if groups:
        out.append(" · ".join(groups))
    hist = []
    for e in ctx.d["history"]["entries"]:
        t = md(e["title"])
        hist.append(f"[{t}]({e['link']})" if e.get("link") else t)
    if hist:
        out.append("Also: " + " · ".join(hist))
    return "\n\n".join(out)


def activity(ctx: Context) -> str:
    out = []
    rows = []
    for slug, repo in ctx.resolved.items():
        c30 = ctx.metrics(repo)["c30"]
        if c30 > 0:
            rows.append((c30, slug))
    rows.sort(key=lambda t: (-t[0], t[1]))
    rows = rows[:6]
    if rows:
        top = rows[0][0]
        w = max(len(s) for _, s in rows)
        bars = "\n".join(f"{s:<{w}}  {BAR * max(1, round(c * 15 / top))} {c}" for c, s in rows)
        out.append(f"**Commits, last 30 days**\n\n```text\n{bars}\n```")
    dist = languages.distribution(ctx.repos, exclude_languages=ctx.cfg.get("exclude_languages", []),
                                  exclude_repos=list(ctx.cfg.get("exclude_repos", [])) + list(ctx.ov.get("exclude_repos", [])),
                                  min_pct=ctx.cfg.get("min_language_pct", 2))
    if dist:
        w = max(len(x["language"]) for x in dist)
        lang = "\n".join(f"{x['language']:<{w}}  {BAR * max(1, round(x['pct'] * 15 / dist[0]['pct']))} {x['pct']}%" for x in dist)
        out.append(f"**Languages**\n\n```text\n{lang}\n```")
    if out:
        out.append("<sub>Default-branch commits and bytes of code in public repos. Activity indicators, not measures of quality or skill.</sub>")
        if ctx.note("repos", "activity"):
            out.append(ctx.note("repos", "activity"))
    return "\n\n".join(out)


def links(ctx: Context) -> str:
    return " · ".join(f"[{md(l['label'])}]({l['url']})" for l in ctx.d["links"]["links"])


def footer(ctx: Context) -> str:
    if not ctx.display.get("show_freshness_stamp", True):
        return ""
    return f"<sub>Generated by ProfileOS · data snapshot {ctx.snapshot_date} · Automate facts. Curate identity.</sub>"


RENDERERS = {
    "CURRENTLY_BUILDING": currently_building, "NOW": now_panel, "PULSE": pulse, "RECENTLY_SHIPPED": recently_shipped,
    "OS_SERIES": os_series, "SELECTED_SYSTEMS": selected_systems, "STACK": stack, "EARLIER_BUILDS": earlier_builds,
    "ACTIVITY": activity, "LINKS": links, "FOOTER": footer,
}


def render_all(ctx: Context) -> dict:
    return {sid: fn(ctx) for sid, fn in RENDERERS.items()}
