"""Schema + cross-file validation. Human error must be visible BEFORE anything is written."""
import re
from pathlib import Path

import jsonschema

from .data import NAMES, load_all, load_schema
from .generators.markers import check_markers
from .status import netguard

FORBIDDEN_KEY = re.compile(r"(token|secret|password|api[_-]?key|private[_-]?key)", re.I)
PUBLISHABLE = {"HIGH", "MEDIUM", "STATED"}   # LOW is recorded but never published
ALL_CONF = PUBLISHABLE | {"LOW"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    @property
    def ok(self):
        return not self.errors


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}/{k}", str(k)
            yield from _walk_keys(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def _records(obj, path=""):
    """Yield (path, record) for every {value, confidence, evidence} record in the evidence file."""
    if isinstance(obj, dict):
        if "confidence" in obj:
            yield path, obj
        else:
            for k, v in obj.items():
                yield from _records(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _records(v, f"{path}[{i}]")


def _check_evidence(data, rep):
    ev = (data["evidence"].get("projects") or {})
    projects = data["projects"]
    for slug in ev:
        if slug not in projects:
            rep.err(f"evidence.yml: unknown project '{slug}'")
    for loc, r in _records(ev):
        if r["confidence"] not in ALL_CONF:
            rep.err(f"evidence.yml: {loc}: confidence must be one of {sorted(ALL_CONF)}")
        if not r.get("evidence"):
            rep.err(f"evidence.yml: {loc}: record has no evidence")
    for slug, p in projects.items():
        e = ev.get(slug, {})
        for field in ("tagline", "description", "demo", "docs"):
            if p.get(field):
                rec = e.get(field)
                if not rec:
                    rep.err(f"projects.yml: {slug}.{field} is published but has no evidence record")
                elif rec["confidence"] not in PUBLISHABLE:
                    rep.err(f"projects.yml: {slug}.{field} has {rec['confidence']} confidence — not publishable")
                elif rec["value"] != p[field]:
                    rep.err(f"projects.yml: {slug}.{field} differs from its evidence record")
        have = {s["value"]: s["confidence"] for s in e.get("stack", [])}
        for item in p.get("stack") or []:
            if have.get(item) not in PUBLISHABLE:
                rep.err(f"projects.yml: {slug}.stack '{item}' lacks HIGH/MEDIUM evidence")


def public_url_problem(url: str, *, allowed_ports=netguard.DEFAULT_PORTS, allow_http: bool = False):
    """Static URL policy (shared with the health checker, which adds the DNS-level checks at probe time).
    Validation is offline and deterministic, so it never resolves names; plain http is off unless config allows it."""
    return netguard.url_problem(url, allowed_ports=allowed_ports, allow_http=allow_http)


def _check_deployment(slug, p, data, rep):
    """Health checks are opt-in per project: flag + URL + verified project + publishable evidence for that very URL."""
    dep = p.get("deployment") or {}
    url, enabled = dep.get("health_url"), dep.get("health_check") is True
    hcfg = data["config"].get("health", {})
    ports, http_ok = hcfg.get("allowed_ports", list(netguard.DEFAULT_PORTS)), hcfg.get("allow_http", False)
    if url and (problem := public_url_problem(url, allowed_ports=ports, allow_http=http_ok)):
        rep.err(f"projects.yml: {slug}: deployment.health_url {problem}")
    for host in dep.get("redirect_hosts") or []:
        if public_url_problem(f"https://{host}/", allowed_ports=ports):
            rep.err(f"projects.yml: {slug}: deployment.redirect_hosts '{host}' is not an acceptable public host name")
    if not enabled:
        return
    if not url:
        rep.err(f"projects.yml: {slug}: deployment.health_check is true but health_url is not set")
        return
    if not p.get("verified"):
        rep.err(f"projects.yml: {slug}: health checks require verified: true")
    rec = ((data["evidence"].get("projects") or {}).get(slug) or {}).get("health_url")
    if not rec:
        rep.err(f"projects.yml: {slug}: health_url is probed but has no evidence record (evidence.yml health_url)")
    elif rec.get("confidence") not in PUBLISHABLE:
        rep.err(f"projects.yml: {slug}: health_url evidence has {rec.get('confidence')} confidence — not publishable")
    elif rec.get("value") != url:
        rep.err(f"projects.yml: {slug}: health_url differs from its evidence record")


def _check_event_dispatch(root: Path, data, rep):
    cfg = data["config"].get("event_dispatch") or {}
    if not cfg.get("enabled"):
        return
    handle = data["profile"]["identity"]["handle"].lower()
    target = cfg.get("target_repo")
    if not target:
        rep.err("config.yml: event_dispatch.enabled is true but target_repo is not set")
    elif target.split("/")[0].lower() != handle:
        rep.err("config.yml: event_dispatch.target_repo must belong to the profile owner")
    if not cfg.get("sources"):
        rep.err("config.yml: event_dispatch.enabled is true but sources is empty")
    if not cfg.get("events"):
        rep.err("config.yml: event_dispatch.enabled is true but events is empty")
    wf = root / ".github" / "workflows" / "update-profile.yml"
    if wf.exists():
        import yaml
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        on = doc.get(True, doc.get("on", {})) or {}   # YAML 1.1 parses the key `on` as True
        types = ((on.get("repository_dispatch") or {}).get("types")) or []
        if cfg.get("event_type", "profileos-refresh") not in types:
            rep.err(f"config.yml: event_dispatch.event_type is not a repository_dispatch type in update-profile.yml ({types})")


def validate(root: Path, strict: bool = False) -> Report:
    root = Path(root)
    rep = Report()
    data = load_all(root / "data")

    for n in NAMES:
        if not (root / "data" / f"{n}.yml").exists():
            rep.err(f"data/{n}.yml is missing")
            continue
        validator = jsonschema.Draft7Validator(load_schema(n))
        for e in sorted(validator.iter_errors(data[n]), key=lambda e: list(e.absolute_path)):
            loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
            rep.err(f"data/{n}.yml: {loc}: {e.message}")
        for loc, key in _walk_keys(data[n]):
            if FORBIDDEN_KEY.search(key) or key.lower() == "key":
                rep.err(f"data/{n}.yml: key '{loc}' looks like a secret — secrets never live in YAML")
    if rep.errors:
        return rep  # cross-checks assume schema-valid shapes

    projects, cats = data["projects"], data["categories"]
    handle = data["profile"]["identity"]["handle"].lower()
    seen_repos = {}
    for slug, p in projects.items():
        repo = p.get("repo")
        if not repo and not p.get("show_unlinked"):
            rep.err(f"projects.yml: {slug}: 'repo' is required unless show_unlinked: true")
        if repo:
            if repo.split("/")[0].lower() != handle:
                rep.warn(f"projects.yml: {slug}: repo owner differs from handle @{handle}")
            if repo.lower() in seen_repos:
                rep.err(f"projects.yml: {slug} and {seen_repos[repo.lower()]} point at the same repo")
            seen_repos[repo.lower()] = slug
        if p["category"] not in cats["display"]:
            rep.err(f"projects.yml: {slug}: unknown category '{p['category']}'")
        if p.get("verified") and not (p.get("tagline") and p.get("stack")):
            rep.err(f"projects.yml: {slug}: verified: true requires tagline and stack")
        _check_deployment(slug, p, data, rep)
        for r in p.get("relations", []):
            for end in (r["from"], r["to"]):
                if end not in projects:
                    rep.err(f"projects.yml: {slug}: relation references unknown project '{end}'")

    _check_evidence(data, rep)
    _check_event_dispatch(root, data, rep)

    for alias, target in data["aliases"]["aliases"].items():
        if target not in projects:
            rep.err(f"aliases.yml: '{alias}' -> unknown project '{target}'")
    ov = data["overrides"]
    for key in list(ov.get("focus", {})) + list(ov.get("pin_order", [])) + list(ov.get("hide_fields", {})):
        if key not in projects:
            rep.err(f"overrides.yml: unknown project '{key}'")

    for group, items in data["stack"]["groups"].items():
        for it in items:
            if not it["evidence"]:
                (rep.err if strict else rep.warn)(f"stack.yml: {group}/{it['name']} has no evidence — hidden from README until confirmed")

    readme = root / "README.md"
    if not readme.exists():
        rep.err("README.md is missing")
    else:
        errs, warns = check_markers(readme.read_text(encoding="utf-8"))
        for m in errs:
            rep.err(f"README.md: {m}")
        for m in warns:
            rep.warn(f"README.md: {m}")
    return rep


def check_repos_online(root: Path, timeout: float = 10.0) -> Report:
    """Optional: HEAD each project repo (used by validate.yml)."""
    import httpx

    rep = Report()
    data = load_all(Path(root) / "data")
    for slug, p in data["projects"].items():
        if p.get("repo"):
            try:
                r = httpx.head(f"https://github.com/{p['repo']}", timeout=timeout, follow_redirects=True)
                if r.status_code != 200:
                    rep.warn(f"{slug}: https://github.com/{p['repo']} returned {r.status_code}")
            except httpx.HTTPError as e:
                rep.warn(f"{slug}: could not reach repo ({type(e).__name__})")
    return rep
