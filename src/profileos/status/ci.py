"""CI status from GitHub Actions run data (read-only REST, public data).

States: passing | failing | in_progress | queued | cancelled | unknown | not_configured.
`passing` is only ever produced from a *fresh* fetch whose latest runs all concluded `success`. Anything we could not
read, anything stale, and anything ambiguous is `unknown`; a repo with no workflow runs is `not_configured`.

Authentication (least privilege, in order):
  1. PROFILEOS_STATUS_TOKEN — optional fine-grained PAT, read-only (Actions: read, Metadata: read) on the flagship
     repos. Classic tokens carrying any write/admin scope are REFUSED (see `broad_scope`).
  2. the workflow's GITHUB_TOKEN — which cannot be assumed to read other repositories' runs;
  3. no token at all — public repositories expose their Actions runs without authentication (lower rate limit).
A 401/403/404 with an Authorization header is retried once WITHOUT it. We only ever go down in privilege.
"""
import datetime as dt
import re

from ..github.client import GitHubClient, GitHubError
from ..storage.cache import iso, parse_iso

STATES = ("passing", "failing", "in_progress", "queued", "cancelled", "unknown", "not_configured")
SHOWN = ("passing", "failing", "in_progress", "queued", "cancelled")   # unknown / not_configured are never drawn
_RANK = {"failing": 0, "in_progress": 1, "queued": 2, "cancelled": 3, "unknown": 4, "passing": 5}  # worst wins
_FAIL = {"failure", "timed_out", "startup_failure"}
_UNKNOWN_CONCLUSIONS = {"neutral", "skipped", "stale", "action_required", None}
_BROAD = re.compile(r"(^|,\s*)(repo|public_repo|admin:[a-z_]+|write:[a-z_]+|delete_repo|workflow|delete:[a-z_]+|site_admin|user|gist|codespace|project)\b")
_RUNS = "/repos/{full}/actions/runs?branch={branch}&per_page=30&exclude_pull_requests=true"


def broad_scope(scopes_header: str | None) -> bool:
    """True when a classic token advertises more than read-only public access (x-oauth-scopes). Fine-grained tokens
    and GITHUB_TOKEN send no such header, so this cannot vouch for them: docs/PERMISSIONS.md says what to create."""
    return bool(scopes_header) and bool(_BROAD.search(scopes_header))


def classify_run(run: dict) -> str:
    status, conclusion = run.get("status"), run.get("conclusion")
    if status in ("queued", "waiting", "requested", "pending"):
        return "queued"
    if status == "in_progress":
        return "in_progress"
    if status == "completed":
        if conclusion == "success":
            return "passing"
        if conclusion in _FAIL:
            return "failing"
        if conclusion == "cancelled":
            return "cancelled"
        return "unknown"
    return "unknown"


def summarize(runs: list, now: dt.datetime, *, workflow: str | None, max_run_age_days: int) -> dict:
    """Latest run per workflow on the default branch -> one record. Never greener than the worst workflow."""
    latest: dict = {}
    for r in runs or []:
        if not isinstance(r, dict) or r.get("event") == "dynamic":   # dynamic = Pages/Dependabot plumbing, not CI
            continue
        key = r.get("workflow_id") or r.get("name")
        if workflow and workflow.lower() not in (str(r.get("name", "")).lower(), str(r.get("path", "")).rsplit("/", 1)[-1].lower()):
            continue
        cur = latest.get(key)
        if cur is None or (r.get("created_at") or "") > (cur.get("created_at") or ""):
            latest[key] = r
    if not latest:
        return {"state": "not_configured", "reason": "no workflow runs on the default branch"}
    scored = sorted(((classify_run(r), r) for r in latest.values()), key=lambda t: (_RANK[t[0]], t[1].get("name") or ""))
    state, run = scored[0]
    when = run.get("updated_at") or run.get("created_at")
    rec = {
        "state": state,
        "workflow": str(run.get("name") or "")[:60] or None,
        "run_status": run.get("status"), "conclusion": run.get("conclusion"),
        "run_at": when, "url": run.get("html_url"), "workflows": len(latest),
    }
    try:
        age = (now - parse_iso(when)).days
    except (TypeError, ValueError):
        return {**rec, "state": "unknown", "reason": "run time unavailable"}
    if state == "passing" and age > max_run_age_days:
        return {**rec, "state": "unknown", "reason": f"last run {age} days ago"}
    return rec


def _get(clients, path):
    """Try each (label, client) in decreasing privilege order. Returns (response, label)."""
    last_exc = None
    for label, client in clients:
        try:
            resp = client.rest_response(path)
        except GitHubError as e:
            if e.rate_limited:
                raise
            last_exc = e
            continue
        if resp.status_code in (401, 403, 404) and label != clients[-1][0]:
            continue                                  # not permitted with this credential: try a less privileged one
        return resp, label
    raise last_exc or GitHubError("no client available")


def build_clients(token: str | None, status_token: str | None, *, transport=None, sleep=None):
    """[(label, client)] in decreasing privilege. A broad classic status token is dropped (and reported) up front."""
    kw = {"transport": transport, **({"sleep": sleep} if sleep else {})}
    out, notes = [], []
    if status_token:
        out.append(("status-token", GitHubClient(status_token, **kw)))
    if token:
        out.append(("github-token", GitHubClient(token, **kw)))
    out.append(("public", GitHubClient(None, **kw)))
    return out, notes


def fetch_ci(clients, repos: list, now: dt.datetime, *, cfg: dict | None = None) -> tuple[dict, list]:
    """repos: [{full_name, default_branch, workflow?}]. Returns ({full_name: record}, warnings). A repo whose fetch
    failed is simply absent: the caller keeps its last cache entry (marked stale) or shows nothing."""
    cfg = cfg or {}
    out, warnings = {}, []
    max_age = int(cfg.get("max_run_age_days", 90))
    refused: set = set()
    for repo in repos[: int(cfg.get("max_repos", 12))]:
        full, branch = repo["full_name"], repo.get("default_branch") or "main"
        if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", full) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", branch):
            warnings.append(f"ci: skipped {full!r} (unsafe name)")
            continue
        usable = [(l, c) for l, c in clients if l not in refused]
        try:
            resp, label = _get(usable, _RUNS.format(full=full, branch=branch))
        except GitHubError as e:
            warnings.append(f"ci: {full}: {'rate limited' if e.rate_limited else 'unavailable'} ({e})")
            if e.rate_limited:
                break                                   # stop spending quota; remaining repos fall back to cache
            continue
        if label == "status-token" and broad_scope(resp.headers.get("x-oauth-scopes")):
            refused.add("status-token")
            warnings.append("ci: PROFILEOS_STATUS_TOKEN has write/admin scopes and was NOT used (create a read-only fine-grained token)")
            try:
                resp, label = _get([(l, c) for l, c in clients if l not in refused], _RUNS.format(full=full, branch=branch))
            except GitHubError as e:
                warnings.append(f"ci: {full}: unavailable ({e})")
                continue
        if resp.status_code == 404:
            warnings.append(f"ci: {full}: not visible")
            continue
        if resp.status_code != 200:
            warnings.append(f"ci: {full}: HTTP {resp.status_code}")
            continue
        try:
            body = resp.json()
            runs = body.get("workflow_runs") if isinstance(body, dict) else None
        except ValueError:
            runs = None
        if not isinstance(runs, list):
            warnings.append(f"ci: {full}: unexpected response shape")
            continue
        rec = summarize(runs, now, workflow=repo.get("workflow"), max_run_age_days=max_age)
        out[full] = {**rec, "checked_at": iso(now), "auth": label, "source": "github-actions-api"}
    return out, warnings


def effective(rec: dict | None, now: dt.datetime, *, fresh: bool, stale_after_h: float, label_after_h: float = 24) -> dict | None:
    """What may be *shown*: a cached record is only trusted while young; otherwise it degrades to unknown (hidden)."""
    if not rec:
        return None
    if fresh:
        return rec
    try:
        age_h = (now - parse_iso(rec["checked_at"])).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return {**rec, "state": "unknown", "reason": "no check time", "stale": True}
    if age_h > stale_after_h:
        return {**rec, "state": "unknown", "reason": "cached status is stale", "stale": True}
    return {**rec, "stale": True} if age_h > label_after_h else rec   # young cache: shown as-is (no churn on a short outage)
