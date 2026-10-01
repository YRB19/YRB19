"""Schema + cross-file validation. Human error must be visible BEFORE anything is written."""
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

import jsonschema

from .data import NAMES, load_all, load_schema
from .generators.markers import check_markers

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


def public_url_problem(url: str):
    """Static check only (DNS-level check lands with the health fetcher)."""
    u = urlparse(url)
    if u.scheme != "https":
        return "must be https"
    host = (u.hostname or "").lower()
    if not host:
        return "no host"
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return "host is not public"
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return "private IP address"
    except ValueError:
        pass
    if u.query:
        return "query strings are not allowed (may carry secrets)"
    return None


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
        url = (p.get("deployment") or {}).get("health_url")
        if url and (problem := public_url_problem(url)):
            rep.err(f"projects.yml: {slug}: deployment.health_url {problem}")
        for r in p.get("relations", []):
            for end in (r["from"], r["to"]):
                if end not in projects:
                    rep.err(f"projects.yml: {slug}: relation references unknown project '{end}'")

    _check_evidence(data, rep)

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
