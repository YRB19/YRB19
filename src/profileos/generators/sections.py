"""Markdown renderers for each registered marker. Every string from repo metadata is sanitised.

Visual blocks (pulse, activity, selected systems, ecosystem) embed the SVG assets built from the same
view-models in `models.py`, so the README and the images can never disagree.
"""
import html

from ..analytics import discovery, scoring, shipped
from ..sanitize import md, url as safe_url
from ..storage.cache import parse_iso
from . import features, models, visuals


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
        self.pet_peak = 0                          # growth high-water mark from the cache (set by build(); never decreases)
        self.history = None                        # set by build() after the history step (snapshots, rollups, timeline)
        self.ci, self.health = datasets.get("ci", {}), datasets.get("health", {})   # already staleness-checked (build.py)
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
        """Repos that must never reach public output: see models.excluded_repos (shared with the cache filter)."""
        return models.excluded_repos(self.d)

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
        return f"[{label}]({safe_url(r['url'])})" if r and safe_url(r["url"]) else label

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


def _titled(title: str, body: str, level: int = 2) -> str:
    """A heading that exists only when its content does: a profile with no data for a section shows no empty heading."""
    return f"{'#' * level} {title}\n\n{body}" if body else ""


def _centered(inner: str) -> str:
    return f'<div align="center">\n\n{inner}\n\n</div>' if inner else ""


def _group(ctx: Context, group: str, members: list) -> str:
    """The two-column composite for a group of cards (stacked for phones); a lone member is shown on its own."""
    if group in ctx.assets:
        return _centered(_img(ctx, group))
    return _centered(_join([_img(ctx, m) for m in members]))


# ---- renderers ---------------------------------------------------------------------------------
def signal(ctx: Context) -> str:
    """The dashboard: Profile Signal and commit bars beside the Code Pet and weekly rhythm."""
    body = _group(ctx, "overview", ["profile-signal", "activity", "code-pet", "activity-rhythm"])
    return _join([body, ctx.note("contributions", "repos", "profile", "activity") if body else ""])


def building(ctx: Context) -> str:
    """BUILDING IN PUBLIC: declared (Building / Exploring / Learning) and derived (Recent activity, Recently shipped) parts are
    labelled differently. Commit volume is never presented as what I am working on."""
    m = features.building_model(ctx)
    if not m:
        return ""
    head = []
    if m["building"]:
        head.append("**Building** · " + " · ".join(f"[{md(b['title'])}]({safe_url(b['url'])})" if b["url"] and safe_url(b["url"]) else md(b["title"]) for b in m["building"]))
    for label, key in (("Exploring", "exploring"), ("Learning", "learning")):
        if m[key]:
            head.append(f"**{label}** · " + " · ".join(md(x) for x in m[key]))
    derived = []
    if m["active_repositories"]:
        derived.append("**Recent activity** · " + " · ".join(f"[{md(a['title'])}]({safe_url(a['url'])})" for a in m["active_repositories"] if safe_url(a["url"]))
                       + " <sub>public commits, last 30 days (from GitHub, not a statement of intent)</sub>")
    for nb in m["new_builds"]:
        derived.append(f"**New on GitHub** · [{md(nb['name'])}]({safe_url(nb['url'])}) <sub>first seen {nb['first_seen']}</sub>")
    ships = recently_shipped(ctx)
    parts = ["  \n".join(head), "  \n".join(derived), ("**Recently shipped**  \n" + ships) if ships else ""]
    return _titled("Building in Public", _join(parts + [ctx.note("repos", "activity")]))


def recently_shipped(ctx: Context) -> str:
    if "repos" not in ctx.ds:
        return ""
    items = shipped.collect(ctx.repos, ctx.activity, ctx.releases, ctx.now,
                            window_days=ctx.cfg.get("shipped_window_days", 60),
                            max_items=ctx.display.get("max_recently_shipped", 6))
    lines = []
    for it in items:
        d = parse_iso(it["date"])
        link = safe_url(it["url"])
        what = f"[{md(it['text'])}]({link})" if link else md(it["text"])
        lines.append(f"`{d:%m/%d}` **{md(it['repo'])}** — {what}")
    return "  \n".join(lines)


def releases(ctx: Context) -> str:
    """Release tracker. The heading lives inside the block so a profile with no published releases shows nothing."""
    rows = models.release_rows(ctx)
    if not rows:
        return ""
    lines = ["### Latest releases", "", "| Project | Version | Released |", "| --- | --- | --- |"]
    for r in rows:
        link, repo = safe_url(r["url"]), safe_url(r["repo_url"])
        ver = (f"[{md(r['tag'])}]({link})" if link else md(r["tag"])) + (" · pre-release" if r["prerelease"] else "")
        lines.append(f"| {f'[{md(r['title'])}]({repo})' if repo else md(r['title'])} | {ver} | {r['date']} |")
    note = ctx.note("repos")
    return "\n".join(lines) + (f"\n\n{note}" if note else "")


def timeline(ctx: Context) -> str:
    rows = models.timeline_rows(ctx)
    if not rows:
        return ""
    lines = []
    for r in rows:
        link = safe_url(r["url"])
        what = f"[{md(r['title'])}]({link})" if link else md(r["title"])
        lines.append(f"`{r['date']}` **{md(r['project'])}** — {what}  ")
    lines.append("")
    lines.append("<sub>Dates come from GitHub (repository creation, release publication) or sourced milestones. "
                 "\"First seen\" is when ProfileOS first listed a project, not when it was started.</sub>")
    return "### Project timeline\n\n" + "\n".join(lines)


def project_map(ctx: Context) -> str:
    """Project Map beside the contribution city and the language bubbles. The map is an image, so every project is also a link below."""
    members = ["project-map", "contribution-city", "language-bubbles"]
    if not any(m in ctx.assets for m in members):
        return ""
    m = features.project_map_model(ctx)
    names = " · ".join(f"[{md(n['name'])}]({safe_url(n['url'])})" for n in m["nodes"]) if m else ""
    body = _join([_group(ctx, "systems", members), f'<div align="center">{names}</div>' if names else "",
                  ctx.note("repos", "contributions")])
    return _titled("Systems & Activity", body)


def city(ctx: Context) -> str:
    """Month-by-month commit history: appears once two months of real history exist."""
    return _titled("Commit History", _join([_centered(_img(ctx, "monthly")), ctx.note("repos", "activity")])) if "monthly" in ctx.assets else ""


def cta(ctx: Context) -> str:
    m = features.collaboration_model(ctx)
    if not m:  # never leave the visitor without the verified links, even if the banner text is removed
        return " · ".join(f"[{md(l['label'])}]({l['url']})" for l in ctx.d["links"]["links"])
    links = [f"[{md(l['label'])}]({l['url']})" for l in m["approved_links"]]
    if m["pages_url"]:
        links.append(f"[Interactive project map]({m['pages_url']})")
    return _join([_centered(_img(ctx, "collaboration")), f'<div align="center">{" · ".join(links)}</div>'])


def selected_systems(ctx: Context) -> str:
    """Featured systems as a two-column grid of cards (stacked on phones) with real links underneath."""
    cards_ = [c for c in models.card_models(ctx) if visuals.card_name(c["slug"]) in ctx.assets]
    if not cards_:
        return ""
    links = []
    for card in cards_:
        bits = [f"**[{md(card['title'])}]({safe_url(card['url'])})**"]
        bits += [f"[{label}]({url})" for label, url in (("Demo", card.get("demo")), ("Docs", card.get("docs"))) if url]
        links.append(" · ".join(bits))
    body = _join([_group(ctx, "featured", [visuals.card_name(c["slug"]) for c in cards_]),
                  '<div align="center">' + "&nbsp;&nbsp;|&nbsp;&nbsp;".join(links) + "</div>", ctx.note("repos")])
    return _titled("Featured Systems", body)


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


def footer(ctx: Context) -> str:
    if not ctx.display.get("show_freshness_stamp", True):
        return ""
    return f"<sub>Generated by ProfileOS · data snapshot {ctx.snapshot_date} · Automate facts. Curate identity.</sub>"


RENDERERS = {
    "SIGNAL": signal, "BUILDING": building, "RELEASES": releases, "SELECTED_SYSTEMS": selected_systems,
    "PROJECT_MAP": project_map, "STACK": stack, "CITY": city,
    "EARLIER_BUILDS": earlier_builds, "TIMELINE": timeline, "CTA": cta, "FOOTER": footer,
}


def render_all(ctx: Context) -> dict:
    return {sid: fn(ctx) for sid, fn in RENDERERS.items()}
