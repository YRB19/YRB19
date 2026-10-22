"""Daily snapshot: time policy, record construction, validation and append-only storage.

One record per local day, written once and never modified afterwards (corrections and migrations are explicit, documented
steps: docs/SNAPSHOTS.md). A snapshot is built only from data that was freshly and completely read; if anything needed is
unavailable no snapshot is written (a gap), never one filled with zeros.
"""
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jsonschema

from ..data import load_schema
from ..storage.cache import iso

SCHEMA_VERSION = 1
PAGE = 10                      # the fetch queries read up to this many recent PRs / releases per repository
DIR = "snapshots"
RULES = {
    "closed_day": "Counts for one complete day in the snapshot timezone (the day before `date`), as the inclusive UTC window "
                  "[start, end]. Closed days never overlap, so they can be summed.",
    "commits": "Commits on each repository's default branch, any author, by committer date, in the window.",
    "merged_prs": "Pull requests merged in the window. null when the repository returned a full page of recent PRs (so a complete "
                  "count cannot be established).",
    "releases": "Published, non-draft releases in the window. null when a full page of releases came back.",
    "rolling": "Rolling default-branch commit counts ending at taken_at (last 7/30/90 days). Windows overlap day to day: point-in-time "
               "readings, never to be summed or compared as monthly totals.",
    "languages": "Share of code bytes across the included repositories, as drawn on the profile. A point-in-time reading.",
    "repos": "Public, non-fork repositories, excluding the profile repository and any project not published. Private repositories are "
             "never read into a snapshot.",
}


class SnapshotError(Exception):
    pass


def get_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError) as e:
        raise SnapshotError(f"unknown snapshot timezone {name!r}") from e


def local_date(now: dt.datetime, tz: ZoneInfo) -> dt.date:
    return now.astimezone(tz).date()


def closed_day(now: dt.datetime, tz: ZoneInfo) -> dict:
    """The complete local day before `now`'s local date, as inclusive UTC instants (end = next local midnight - 1 s)."""
    today = local_date(now, tz)
    day = today - dt.timedelta(days=1)
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=tz).astimezone(dt.timezone.utc)
    end = dt.datetime.combine(today, dt.time(0, 0), tzinfo=tz).astimezone(dt.timezone.utc) - dt.timedelta(seconds=1)
    return {"date": day.isoformat(), "start": iso(start), "end": iso(end)}


def path_for(root: Path, date: str) -> Path:
    return Path(root) / DIR / "daily" / date[:4] / f"{date}.json"


def exists(root: Path, date: str) -> bool:
    return path_for(root, date).exists()


def _sum_or_none(values):
    return None if any(v is None for v in values) else sum(values)


def build_record(*, now, tz, tz_name, repos, activity, releases, projects, languages, day_commits, repos_fetched_at, synthetic=False):
    """repos: included repo dicts (already public/non-fork/not excluded); projects: {slug: repo dict} (published only).
    day_commits: {full_name: int} for the closed day. PRs/releases are matched on the inclusive UTC instants of the window
    (so non-UTC snapshot timezones are handled exactly), never on calendar-date prefixes."""
    cd = closed_day(now, tz)
    missing = [r["full_name"] for r in repos if r["full_name"] not in day_commits]
    if missing:
        raise SnapshotError(f"closed-day commit counts missing for {len(missing)} repositories; refusing to guess")

    def in_window(ts):
        return bool(ts) and cd["start"] <= ts <= cd["end"]

    def counts(full):
        prs = (activity.get(full) or {}).get("merged_prs")
        rels = releases.get(full)
        pr_n = None if prs is None or len(prs) >= PAGE else sum(1 for p in prs if in_window(p.get("merged_at")))
        rel_n = None if rels is None or len(rels) >= PAGE else sum(1 for r in rels if in_window(r.get("published_at")))
        return pr_n, rel_n

    per_repo = {r["full_name"]: (day_commits[r["full_name"]], *counts(r["full_name"])) for r in repos}
    roll = {k: sum((activity.get(r["full_name"]) or {}).get("commits", {}).get(k, 0) for r in repos) for k in ("d7", "d30", "d90")}
    rec = {
        "schema": SCHEMA_VERSION, "kind": "daily", "date": local_date(now, tz).isoformat(), "timezone": tz_name or "UTC",
        "taken_at": iso(now), "closed_day": cd,
        "source": {"name": "github-graphql", "repos_fetched_at": repos_fetched_at},
        "scope": {"summary": "Public non-fork repositories other than the profile repository and unpublished projects. "
                             "Default-branch commit counts; an activity signal, not a quality measure.",
                  "rules": dict(RULES)},
        "repos": {"included": len(repos), "names": sorted(r["full_name"] for r in repos),
                  "active_on_closed_day": sorted(f for f, (c, *_ ) in per_repo.items() if c > 0)},
        "totals": {"closed_day": {"commits": sum(c for c, *_ in per_repo.values()),
                                  "merged_prs": _sum_or_none([p for _, p, _ in per_repo.values()]),
                                  "releases": _sum_or_none([x for _, _, x in per_repo.values()])},
                   "rolling": roll},
        "languages": [{"language": x["language"], "pct": float(x["pct"])} for x in (languages or [])],
        "projects": {},
    }
    for slug, r in sorted(projects.items()):
        full = r["full_name"]
        if full not in per_repo:
            continue
        c, p, x = per_repo[full]
        a = (activity.get(full) or {}).get("commits", {})
        rec["projects"][slug] = {
            "closed_day": {"commits": c, "merged_prs": p, "releases": x},
            "rolling": {k: int(a.get(k, 0)) for k in ("d7", "d30", "d90")},
            "repo_created_on": r["created_at"][:10], "pushed_on": (r.get("pushed_at") or "")[:10] or None,
        }
    if synthetic:
        rec["synthetic"] = True
    validate_record(rec)
    return rec


def validate_record(rec: dict) -> None:
    """Schema + cross-field consistency. Raises SnapshotError listing every problem."""
    problems = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
                for e in sorted(jsonschema.Draft7Validator(load_schema("snapshot")).iter_errors(rec), key=lambda e: list(e.absolute_path))]
    if not problems:
        try:
            d = dt.date.fromisoformat(rec["date"])
            if rec["closed_day"]["date"] != (d - dt.timedelta(days=1)).isoformat():
                problems.append("closed_day.date must be the day before date")
            if rec["repos"]["included"] != len(rec["repos"]["names"]):
                problems.append("repos.included does not match repos.names")
            if not set(rec["repos"]["active_on_closed_day"]) <= set(rec["repos"]["names"]):
                problems.append("active_on_closed_day names a repository that is not included")
            total = rec["totals"]["closed_day"]["commits"]
            if sum(p["closed_day"]["commits"] for p in rec["projects"].values()) > total:
                problems.append("project commits exceed the total")
            for k in ("d7", "d30", "d90"):
                if sum(p["rolling"][k] for p in rec["projects"].values()) > rec["totals"]["rolling"][k]:
                    problems.append(f"project rolling {k} exceeds the total")
            r = rec["totals"]["rolling"]
            if not (r["d7"] <= r["d30"] <= r["d90"]):
                problems.append("rolling windows must be non-decreasing (d7 <= d30 <= d90)")
            if not rec["closed_day"]["start"] < rec["closed_day"]["end"]:
                problems.append("closed_day window is empty")
        except ValueError as e:
            problems.append(str(e))
    if problems:
        raise SnapshotError("invalid snapshot: " + "; ".join(problems))


def write_new(root: Path, rec: dict) -> bool:
    """Write the day's record if (and only if) none exists. Atomic. Returns True when a file was created."""
    validate_record(rec)
    path = path_for(root, rec["date"])
    if path.exists():
        return False                                  # past snapshots are never rewritten
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return True


def load_all(root: Path) -> tuple[list, list]:
    """(records sorted by date, problems). Unreadable/invalid files are reported, never silently skipped or repaired."""
    recs, problems = [], []
    base = Path(root) / DIR / "daily"
    for p in sorted(base.glob("*/*.json")) if base.is_dir() else []:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            validate_record(rec)
            if p.name != f"{rec['date']}.json" or p.parent.name != rec["date"][:4]:
                raise SnapshotError(f"file name does not match its date {rec['date']}")
        except (OSError, ValueError, SnapshotError) as e:
            problems.append(f"{p.relative_to(root)}: {e}")
            continue
        recs.append(rec)
    return sorted(recs, key=lambda r: r["date"]), problems
