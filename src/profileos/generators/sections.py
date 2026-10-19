"""Markdown renderers for each registered marker. Every string from repo metadata is sanitised.

Visual blocks (pulse, activity, selected systems, ecosystem) embed the SVG assets built from the same
view-models in `models.py`, so the README and the images can never disagree.
"""
import html

from ..analytics import discovery, scoring, shipped
from ..sanitize import md
from ..storage.cache import parse_iso
from . import models, visuals


class Context:
    def __init__(self, data, datasets, ages, now, snapshot_date, first_seen):
        self.d, self.ds, self.ages, self.now, self.snapshot_date = data, datasets, ages, now, snapshot_date
        self.cfg, self.prof, self.ov = data["config"], data["profile"], data["overrides"]
        self.display = self.prof.get("display", {})
        self.projects = data["projects"]
        self.warnings: list[str] = []
        self._assets = None
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
                if not models.publishable(p):
                    continue  # internal-only: never resolved, never warned about, never rendered
                r = self._resolve(slug, p)
                if r:
                    self.resolved[slug] = r
                elif p.get("repo"):
                    self.warnings.append(f"{slug}: repo {p['repo']} not found among public repos — omitted")

    def _excluded(self):
        """Repos that must never reach public output: config/override exclusions plus internal-only projects."""
        hidden = {(p.get("repo") or "").lower() for p in self.projects.values() if not models.publishable(p)}
        hidden.discard("")
        return {x.lower() for x in list(self.cfg.get("exclude_repos", [])) + list(self.ov.get("exclude_repos", []))} | hidden

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

    @property
    def assets(self) -> dict:
        """name -> Asset, built once from the shared view-models (raises AssetError if any SVG is unsafe)."""
        if self._assets is None:
            self._assets = visuals.build_assets(self)
        return self._assets

    # ---- helpers -------------------------------------------------------------------------
    def note(self, *names) -> str:
        limit = self.cfg.get("stale_after_h", 24)
        if any(self.ages.get(n, 0) > limit for n in names):
            return f"<sub>as of {self.snapshot_date}</sub>"
        return ""

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


def _img(ctx: Context, name: str) -> str:
    a = ctx.assets.get(name)
    return visuals.picture(a) if a else ""


def _join(parts, sep="\n\n") -> str:
    return sep.join(p for p in parts if p)


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
            busiest = max(pub, key=lambda r: (ctx.metrics(r)["c30"], r["name"].lower()))  # commits only, never priority
            if ctx.metrics(busiest)["c30"] > 0:
                lines.append(f"Most commits (last 30 days): [{md(busiest['name'])}]({busiest['url']})")
            for nb in discovery.new_builds(ctx.first_seen, ctx.repos, known, ctx.now, ctx.cfg.get("new_build_days", 14)):
                lines.append(f"New build: [{md(nb['name'])}]({nb['url']}) · first seen {nb['first_seen']}")
    return "  \n".join(["**NOW**"] + lines) if lines else ""


def pulse(ctx: Context) -> str:
    img = _img(ctx, "pulse")
    return _join([img, ctx.note("contributions", "repos") if img else ""])


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
    members = models.os_members(ctx)
    if not members:
        return ""
    return _join([
        "*Building focused systems around messy real-world problems.*",
        _img(ctx, "os-series"),
        " · ".join(ctx.link(s) for s in members),
    ])


def selected_systems(ctx: Context) -> str:
    blocks = []
    for card in models.card_models(ctx):
        a = ctx.assets.get(visuals.card_name(card["slug"]))
        if not a:
            continue
        links = [f"[{label}]({url})" for label, url in (("Demo", card.get("demo")), ("Docs", card.get("docs"))) if url]
        blocks.append(_join([f'<a href="{html.escape(card["url"], quote=True)}">\n{visuals.picture(a)}\n</a>', " · ".join(links)], "\n\n"))
    return _join(blocks + ([ctx.note("repos")] if blocks and ctx.note("repos") else []))


def stack(ctx: Context) -> str:
    lines = []
    for group, items in ctx.d["stack"]["groups"].items():
        names = [md(i["name"]) for i in items if i["evidence"]]
        if names:
            lines.append(f"**{md(group)}** · " + " · ".join(names))
    return "  \n".join(lines)


def earlier_builds(ctx: Context) -> str:
    out = []
    groups = [ctx.link(s) for s, p in ctx.projects.items()
              if p.get("group") == "earlier" and models.publishable(p) and (s in ctx.resolved or "repos" not in ctx.ds)]
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
    visuals_ = [_img(ctx, n) for n in ("heatmap", "activity", "languages")]
    if not any(visuals_):
        return ""
    return _join(visuals_ + [ctx.note("repos", "activity", "contributions")])


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
