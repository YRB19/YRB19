"""Orchestration: take today's snapshot (if due and reliable), refresh rollups and the timeline, verify stored history."""
import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..github.client import GitHubError
from ..github.fetch import fetch_day_commits
from ..storage.cache import iso
from . import rollup, snapshot, timeline

DEFAULTS = {"enabled": True, "timezone": "UTC", "chart_months": 12, "timeline_max_items": 8, "min_timeline_events": 3}
_SECRET = re.compile(r"(ghp_|gho_|ghs_|github_pat_|Bearer\s+[A-Za-z0-9_-]{20,})")


def settings(cfg: dict | None) -> dict:
    return {**DEFAULTS, **(cfg or {})}


@dataclass
class State:
    daily: list = field(default_factory=list)
    monthly: list = field(default_factory=list)
    timeline: dict | None = None
    snapshot_status: str = "disabled"          # created | exists | skipped: <reason> | disabled
    writes: list = field(default_factory=list)  # (kind, key, record) pending or performed
    problems: list = field(default_factory=list)


def run(root: Path, *, cfg: dict | None, now: dt.datetime, repos: list, activity: dict, releases: dict, resolved: dict,
        languages: list, milestones: list, repos_fresh: bool, client, synthetic: bool, allow_synthetic: bool,
        warnings: list) -> State:
    s = settings(cfg)
    st = State()
    tz = snapshot.get_tz(s["timezone"])
    st.daily, problems = snapshot.load_all(root)
    st.monthly, mproblems = rollup.load_monthly(root)
    st.problems = problems + mproblems
    for p in st.problems:
        warnings.append(f"history: {p}")
    if not s["enabled"]:
        return st
    today = snapshot.local_date(now, tz).isoformat()

    # ---- daily snapshot -------------------------------------------------------------------------------------------------
    if snapshot.exists(root, today):
        st.snapshot_status = "exists"
    elif not repos_fresh:
        st.snapshot_status = "skipped: repository data was not freshly fetched"
    elif synthetic and not allow_synthetic:
        st.snapshot_status = "skipped: synthetic data is never recorded as history"
    else:
        included = [r for r in repos if not r["is_fork"]]
        cd = snapshot.closed_day(now, tz)
        try:
            counts = fetch_day_commits(client, [r["full_name"] for r in included], cd["start"], cd["end"])
            projects = {slug: r for slug, r in resolved.items()}
            rec = snapshot.build_record(now=now, tz=tz, tz_name=s["timezone"], repos=included, activity=activity, releases=releases,
                                        projects=projects, languages=languages, day_commits=counts, repos_fetched_at=iso(now), synthetic=synthetic)
            st.daily = sorted(st.daily + [rec], key=lambda r: r["date"])
            st.writes.append(("daily", rec["date"], rec))
            st.snapshot_status = "created"
        except (GitHubError, snapshot.SnapshotError, AttributeError) as e:
            st.snapshot_status = f"skipped: {type(e).__name__}"
            warnings.append(f"history: no snapshot for {today} ({e}); history keeps a gap, never a guessed value")

    # ---- monthly rollups (from stored dailies only) ---------------------------------------------------------------------------
    plan = rollup.plan(root, st.daily, s["timezone"])
    for month, rec in sorted(plan.items()):
        st.writes.append(("monthly", month, rec))
    by_month = {r["month"]: r for r in st.monthly}
    by_month.update(plan)
    st.monthly = [by_month[m] for m in sorted(by_month)]

    # ---- timeline (verified events only; append-only) -------------------------------------------------------------------------
    if resolved:
        existing, tproblems = timeline.load(root)
        for p in tproblems:
            warnings.append(f"history: {p}")
            st.problems.append(p)
        if not tproblems:
            known = None
            if existing is not None:
                known = set(existing["seeded_projects"]) | {e["project"] for e in existing["events"]}
            cands = timeline.candidates(projects=resolved, releases=releases, milestones=milestones, today=today, known=known)
            tl, changed = timeline.merge(existing, cands, today, set(resolved))
            st.timeline = tl
            if changed:
                st.writes.append(("timeline", "timeline", tl))
    elif existing_tl := timeline.load(root)[0]:
        st.timeline = existing_tl

    return st


def apply(root: Path, st: State) -> list:
    """Perform the pending writes (each atomic, daily records create-only). Called by build() only after every output rendered,
    so a failed run leaves snapshots untouched. Returns the relative paths created or updated."""
    done = []
    for kind, key, rec in st.writes:
        if kind == "daily":
            if snapshot.write_new(root, rec):
                done.append(str(snapshot.path_for(Path("."), key)))
        elif kind == "monthly":
            rollup.write(root, rec)
            done.append(str(rollup.path_for(Path("."), key)))
        else:
            timeline.write(root, rec)
            done.append(str(timeline.path(Path("."))))
    return done


def verify(root: Path, tz_name: str = "UTC") -> tuple[list, list]:
    """(errors, warnings) for everything stored under snapshots/. Used by `profileos validate`."""
    errors, warnings = [], []
    dailies, p1 = snapshot.load_all(root)
    monthly, p2 = rollup.load_monthly(root)
    _, p3 = timeline.load(root)
    errors += p1 + p2 + p3
    seen = set()
    for r in dailies:
        if r.get("synthetic"):
            errors.append(f"snapshots/daily/{r['date']}.json is marked synthetic: synthetic records must never be committed as history")
        if r["date"] in seen:
            errors.append(f"duplicate snapshot for {r['date']}")
        seen.add(r["date"])
    base = Path(root) / snapshot.DIR
    for p in sorted(base.rglob("*.json")) if base.is_dir() else []:
        try:
            if _SECRET.search(p.read_text(encoding="utf-8")):
                errors.append(f"{p.relative_to(root)}: contains something that looks like a credential")
        except OSError:
            pass
    for p in sorted(base.rglob("*.tmp")) if base.is_dir() else []:
        warnings.append(f"{p.relative_to(root)}: leftover temporary file from an interrupted write (safe to delete)")
    warnings += rollup.drift(root, dailies, tz_name)
    return errors, warnings
