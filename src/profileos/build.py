"""fetch -> analyse -> generate. Nothing is written if validation fails; nothing is committed-worthy unless content changed."""
import datetime as dt
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .analytics import discovery
from .data import load_all
from .generators import visuals
from .generators.models import excluded_repos
from .generators.markers import MarkerError, replace_blocks
from .generators.sections import Context, render_all
from .github.client import GitHubClient, GitHubError
from .github.fetch import fetch_contributions, fetch_repos
from .github.fixtures import FixtureClient
from .status import ci as ci_status, health as health_status
from .generators import models
from .history import run as history_run
from .storage.cache import Cache, iso, parse_iso, would_change, would_change_status
from .validate import validate

FETCHED = ("repos", "activity", "releases", "contributions")
_GENERATED_ASSET = re.compile(r"^[a-z0-9-]+\.(light|dark)\.svg$")  # only files we generate are ever deleted


_SOURCE = {"ci": "github-actions-api", "health": "http-probe"}


class BuildError(Exception):
    pass


@dataclass
class BuildResult:
    changed: bool
    blocks: dict
    warnings: list = field(default_factory=list)
    dry_run: bool = False
    assets: dict = field(default_factory=dict)          # relative path -> SVG text (every asset, both modes)
    asset_changes: list = field(default_factory=list)   # relative paths added/updated/removed vs what is on disk
    asset_objects: dict = field(default_factory=dict)   # name -> Asset (title/alt/svg per mode), for previews
    history_status: str = "disabled"                    # created | exists | skipped: <reason> | disabled
    history_written: list = field(default_factory=list)  # snapshots/ paths created or updated (empty on dry runs)


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _scrub(fresh: dict, hidden: set) -> dict:
    """Drop repos that must never be public (the profile repo itself, internal-only projects) from what is cached.
    Without this the profile repo's own commit/data churn lands in the cached datasets, which changes them on every
    run, which triggers another commit: a self-feeding loop. Also keeps hidden repo data out of the public cache."""
    out = dict(fresh)
    if "repos" in out:
        out["repos"] = [r for r in out["repos"] if r["full_name"].lower() not in hidden]
    for k in ("activity", "releases"):
        if k in out:
            out[k] = {n: v for n, v in out[k].items() if n.lower() not in hidden}
    return out


def _status_clients(client, explicit):
    """Credentials for CI reads, least privilege first (see status/ci.py). A client without REST reads => no CI fetch."""
    if explicit is not None:
        return explicit
    if isinstance(client, GitHubClient):
        clients, _ = ci_status.build_clients(os.environ.get("GITHUB_TOKEN"), os.environ.get("PROFILEOS_STATUS_TOKEN"))
        return clients
    if hasattr(client, "rest_response"):
        return [("injected", client)]
    return None


def _merge_status(cache, name, fresh: dict, wanted: set) -> dict:
    """fresh entries win; entries we could not refresh keep their last cached record (staleness is judged later);
    entries no longer wanted are dropped."""
    prev = cache.read(name)
    old = prev["data"] if prev and prev.get("ok") and isinstance(prev["data"], dict) else {}
    return {k: v for k, v in sorted({**{k: v for k, v in old.items() if k in wanted}, **{k: v for k, v in fresh.items() if k in wanted}}.items())}


def _refresh_status(data, datasets, ages, cache, client, now, warnings, *, fixtures, status_clients, health_fetcher, resolver, sleep):
    """CI + deployment health. Returns ({name: dataset-to-cache}, {name: dataset-to-render}). Never raises: any failure
    leaves the old cache entry in place and the staleness rules decide whether it may still be shown."""
    cfg = data["config"]
    to_cache, to_render = {}, {}
    probe = Context(data, datasets, ages, now, "", {})
    # ---- CI (public flagship repos only) ----
    if "repos" in datasets and cfg.get("ci", {}).get("enabled", True):
        targets = []
        for slug in models.ordered_flagships(probe):
            if (data["projects"][slug].get("ci") or {}).get("track") is False:
                continue
            r = probe.resolved[slug]
            if not r["is_archived"]:
                targets.append({"full_name": r["full_name"], "default_branch": r.get("default_branch"),
                                "workflow": (data["projects"][slug].get("ci") or {}).get("workflow")})
        wanted = {t["full_name"] for t in targets}
        clients, fresh = _status_clients(client, status_clients), {}
        if clients and targets:
            try:
                fresh, w = ci_status.fetch_ci(clients, targets, now, cfg=cfg.get("ci"))
                warnings += w
            except Exception as e:  # noqa: BLE001 - status is best-effort by design; the profile must still build
                warnings.append(f"ci: fetch aborted ({type(e).__name__}); using cache")
        elif targets and not clients:
            warnings.append("ci: no REST-capable client; using cache")
        merged = _merge_status(cache, "ci", fresh, wanted)
        limit = cfg.get("ci", {}).get("stale_after_h", 72)
        to_cache["ci"] = merged
        to_render["ci"] = {k: ci_status.effective(v, now, fresh=k in fresh, stale_after_h=limit) for k, v in merged.items()}
    # ---- deployment health (explicit opt-in only) ----
    targets = health_status.eligible(data["projects"], models.publishable)
    if targets:
        prev_env = cache.read("health")
        prev = prev_env["data"] if prev_env and prev_env.get("ok") else {}
        fresh = {}
        if not (fixtures and health_fetcher is None):          # fixture/preview runs never touch the network
            kw = {"resolve": resolver} if resolver else {}
            if sleep:
                kw["sleep"] = sleep
            fresh, w = health_status.run_checks(targets, cfg.get("health"), fetcher=health_fetcher, now=now, prev=prev, **kw)
            warnings += w
        merged = _merge_status(cache, "health", fresh, set(targets))
        limit = health_status.settings(cfg.get("health"))["stale_after_h"]
        to_cache["health"] = merged
        to_render["health"] = {k: health_status.effective(v, now, fresh=k in fresh, stale_after_h=limit) for k, v in merged.items()}
    return to_cache, to_render


def build(root, *, fixtures=False, dry_run=False, force=False, now=None, client=None, status_clients=None,
          health_fetcher=None, resolver=None, sleep=None, allow_synthetic_history=False) -> BuildResult:
    root = Path(root)
    now = now or utcnow()
    rep = validate(root)
    if not rep.ok:  # human error must be visible, and nothing gets written
        raise BuildError("validation failed:\n  " + "\n  ".join(rep.errors))
    data = load_all(root / "data")
    handle = data["profile"]["identity"]["handle"]
    cache = Cache(root / "data" / "cache")
    warnings: list[str] = []

    if client is None:
        if fixtures:
            client = FixtureClient(now, handle)
        else:
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                raise BuildError("GITHUB_TOKEN is not set (use --fixtures for an offline dry-run)")
            client = GitHubClient(token)

    hidden = excluded_repos(data)
    fresh, api_ok = {}, {}
    try:
        fresh.update(_scrub(fetch_repos(client, handle, now), hidden))
        api_ok["repos"] = True
    except GitHubError as e:
        api_ok["repos"] = False
        warnings.append(f"repos fetch failed, using last valid cache: {e}")
    try:
        fresh["contributions"] = fetch_contributions(client, handle, now, hidden)
        api_ok["contributions"] = True
    except GitHubError as e:
        api_ok["contributions"] = False
        warnings.append(f"contributions fetch failed, using last valid cache: {e}")

    # resolve each dataset: fresh -> last valid cache -> absent (section hidden, never fabricated)
    datasets, ages, snap = {}, {}, {}
    for name in FETCHED:
        if name in fresh:
            datasets[name], ages[name] = fresh[name], 0.0
        else:
            env = cache.read(name)
            if env and env.get("ok"):
                datasets[name], ages[name] = env["data"], Cache.age_hours(env, now)
                snap[name] = env["generated_at"][:10]

    status_cache, status_render = _refresh_status(
        data, datasets, ages, cache, client, now, warnings, fixtures=fixtures, status_clients=status_clients,
        health_fetcher=health_fetcher, resolver=resolver, sleep=sleep)
    datasets.update(status_render)

    # discovery (repo-list diff) — only advances when repos were freshly fetched
    prev_env = cache.read("discovery")
    prev_seen = prev_env["data"] if prev_env and prev_env.get("ok") else None
    first_seen = prev_seen or {}
    if "repos" in fresh:
        first_seen = discovery.update_first_seen(prev_seen, fresh["repos"], now)

    # cache writes (change-only) — skipped entirely on dry runs
    to_write = {n: fresh[n] for n in FETCHED if n in fresh}
    if "repos" in fresh:
        to_write["discovery"] = first_seen
    changed_data = [n for n, d in to_write.items() if would_change(cache, n, d)]
    for n, d in status_cache.items():
        if not d and not cache.read(n):
            continue                      # nothing observed and nothing cached: do not create an empty file
        to_write[n] = d
        if would_change_status(cache, n, d, now):
            changed_data.append(n)
    gen_env = cache.read("generated_at")
    if changed_data:
        snapshot_date = now.date().isoformat()
    elif gen_env and gen_env.get("ok"):
        snapshot_date = parse_iso(gen_env["generated_at"]).date().isoformat()
    else:
        snapshot_date = now.date().isoformat()
    # staleness label uses the cache's own date for datasets that fell back
    ctx_snapshot = min(snap.values()) if snap else snapshot_date
    ctx = Context(data, datasets, ages, now, ctx_snapshot if snap else snapshot_date, first_seen)
    # ---- Phase 7: history (computed here, written only after everything rendered) -----------------------------------------
    hist = history_run.run(
        root, cfg=data["config"].get("snapshots"), now=now, repos=ctx.repos, activity=ctx.activity, releases=ctx.releases,
        resolved=ctx.resolved, languages=(models.language_model(ctx) or {}).get("items", []) if "repos" in datasets else [],
        milestones=data["history"].get("milestones", []), repos_fresh="repos" in fresh, client=client,
        synthetic=isinstance(client, FixtureClient), allow_synthetic=allow_synthetic_history, warnings=warnings)
    ctx.history = hist
    try:
        blocks = render_all(ctx)
        assets = visuals.files(ctx.assets)
    except visuals.AssetError as e:
        raise BuildError(f"SVG generation failed (nothing was written): {e}") from e
    if "FOOTER" in blocks and data["profile"].get("display", {}).get("show_freshness_stamp", True):
        blocks["FOOTER"] = f"<sub>Generated by ProfileOS · data snapshot {snapshot_date} · Automate facts. Curate identity.</sub>"
    warnings += ctx.warnings

    readme_path = root / "README.md"
    old = readme_path.read_text(encoding="utf-8")
    try:
        new, w = replace_blocks(old, blocks)
    except MarkerError as e:
        raise BuildError(f"README marker problem: {e}") from e
    warnings += w
    readme_changed = new != old

    # assets: change-only writes, stale generated files removed (never anything else in the directory)
    asset_dir = root / visuals.ASSET_DIR
    asset_changes = _plan_assets(asset_dir, assets)

    written: list = []
    # ---- everything rendered and checked; only now touch the disk ----------------------------------------
    if not dry_run:
        for n in changed_data:
            cache.write(n, to_write[n], _SOURCE.get(n, "github-graphql"), now)
        if changed_data:
            cache.write("generated_at", {"api_ok": api_ok, "changed_at": iso(now)}, "profileos", now)
        _apply_assets(root, assets, asset_changes)
        written = history_run.apply(root, hist)
        if readme_changed:
            readme_path.write_text(new, encoding="utf-8")
    return BuildResult(
        changed=readme_changed or bool(changed_data) or bool(asset_changes) or bool(hist.writes),
        history_status=hist.snapshot_status, history_written=written,
        blocks=blocks, warnings=warnings, dry_run=dry_run, assets=assets, asset_changes=asset_changes,
        asset_objects=ctx.assets,
    )


def _plan_assets(asset_dir: Path, assets: dict) -> list:
    changes = []
    for rel, svg in sorted(assets.items()):
        path = asset_dir / Path(rel).name
        if not path.exists() or path.read_text(encoding="utf-8") != svg:
            changes.append(rel)
    keep = {Path(rel).name for rel in assets}
    if asset_dir.is_dir():
        for p in sorted(asset_dir.iterdir()):
            if _GENERATED_ASSET.match(p.name) and p.name not in keep:
                changes.append(f"{visuals.ASSET_DIR}/{p.name}")
    return changes


def _apply_assets(root: Path, assets: dict, changes: list) -> None:
    for rel in changes:
        path = root / rel
        if rel in assets:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(assets[rel], encoding="utf-8", newline="\n")
            os.replace(tmp, path)
        elif path.exists():
            path.unlink()
