"""Monthly rollups, derived ONLY from stored daily snapshots.

Statistics (never mixed):
  * commits / merged PRs / releases: SUM of closed-day counts. Closed days never overlap, so nothing is double counted.
    A snapshot dated D describes closed day D-1; a closed day belongs to the month it falls in.
  * active repositories: unique repositories with >= 1 commit on a covered day (a union, not a sum of daily counts).
  * languages: month-end reading = the last daily snapshot whose closed day is in the month.
  * Rolling d7/d30/d90 readings are point-in-time and are NEVER summed.
Missing days are not zero: coverage is reported, a month with gaps is `complete: false`, and nothing is extrapolated.
"""
import calendar
import datetime as dt
import json
import os
from pathlib import Path

import jsonschema

from ..data import load_schema
from .snapshot import DIR, SnapshotError


def month_of(day: str) -> str:
    return day[:7]


def days_in(month: str) -> int:
    y, m = int(month[:4]), int(month[5:7])
    return calendar.monthrange(y, m)[1]


def monthly_record(month: str, dailies: list, tz_name: str) -> dict | None:
    """Rollup for `month` from the daily records whose closed day falls in it, or None if there are none."""
    by_day: dict = {}
    for r in sorted(dailies, key=lambda r: r["date"]):
        d = r["closed_day"]["date"]
        if month_of(d) == month:
            by_day[d] = r                      # one record per closed day; a duplicate can only replace, never add
    if not by_day:
        return None
    days = sorted(by_day)
    recs = [by_day[d] for d in days]
    all_days = [f"{month}-{n:02d}" for n in range(1, days_in(month) + 1)]
    missing = [d for d in all_days if d not in by_day]

    def total(key):
        vals = [r["totals"]["closed_day"][key] for r in recs]
        known = [v for v in vals if v is not None]
        if not known:
            return None, True
        return sum(known), len(known) != len(vals)

    commits = sum(r["totals"]["closed_day"]["commits"] for r in recs)
    active = sorted({n for r in recs for n in r["repos"]["active_on_closed_day"]})
    prs, prs_lb = total("merged_prs")
    rels, rels_lb = total("releases")
    per_project: dict = {}
    for r in recs:
        for slug, p in r["projects"].items():
            per_project[slug] = {"commits": per_project.get(slug, {}).get("commits", 0) + p["closed_day"]["commits"]}
    last = recs[-1]
    rec = {
        "schema": 1, "kind": "monthly", "month": month, "timezone": tz_name,
        "coverage": {"days_in_month": len(all_days), "closed_days_covered": len(days), "first_day": days[0], "last_day": days[-1],
                     "missing_days": missing, "complete": not missing},
        "metrics": {
            "commits": {"statistic": "sum of closed-day counts over the covered days", "value": commits},
            "active_repos": {"statistic": "unique repositories with at least one commit on a covered day", "value": len(active)},
            "merged_prs": {"statistic": "sum of closed-day counts over the covered days", "value": prs, "lower_bound": prs_lb},
            "releases": {"statistic": "sum of closed-day counts over the covered days", "value": rels, "lower_bound": rels_lb},
        },
        "per_project": dict(sorted(per_project.items())),
        "languages": {"statistic": "month-end reading: the last daily snapshot whose closed day is in the month",
                      "as_of": last["date"], "items": last["languages"]},
        "repos_included_at_month_end": last["repos"]["included"],
    }
    validate_monthly(rec)
    return rec


def validate_monthly(rec: dict) -> None:
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
            for e in jsonschema.Draft7Validator(load_schema("monthly")).iter_errors(rec)]
    if errs:
        raise SnapshotError("invalid monthly rollup: " + "; ".join(errs))


def path_for(root: Path, month: str) -> Path:
    return Path(root) / DIR / "monthly" / f"{month}.json"


def load_monthly(root: Path) -> tuple[list, list]:
    recs, problems = [], []
    base = Path(root) / DIR / "monthly"
    for p in sorted(base.glob("*.json")) if base.is_dir() else []:
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
            validate_monthly(rec)
            if p.name != f"{rec['month']}.json":
                raise SnapshotError("file name does not match its month")
        except (OSError, ValueError, SnapshotError) as e:
            problems.append(f"{p.relative_to(root)}: {e}")
            continue
        recs.append(rec)
    return sorted(recs, key=lambda r: r["month"]), problems


def plan(root: Path, dailies: list, tz_name: str) -> dict:
    """{month: record} that SHOULD be (re)written: months with no file yet, and the two most recent months with data
    (a snapshot taken on the 1st carries the previous month's last day). Older months are frozen: once written they are
    never regenerated, so a later gap-fill or edit cannot silently rewrite published history (verify warns on drift)."""
    months = sorted({month_of(r["closed_day"]["date"]) for r in dailies})
    hot = set(months[-2:])
    out = {}
    for m in months:
        have = path_for(root, m).exists()
        if have and m not in hot:
            continue
        rec = monthly_record(m, dailies, tz_name)
        if rec is None:
            continue
        if have:
            try:
                if json.loads(path_for(root, m).read_text(encoding="utf-8")) == rec:
                    continue                    # change-only
            except (OSError, ValueError):
                pass
        out[m] = rec
    return out


def write(root: Path, rec: dict) -> None:
    validate_monthly(rec)
    path = path_for(root, rec["month"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def drift(root: Path, dailies: list, tz_name: str) -> list[str]:
    """Warnings for stored rollups that no longer match a recomputation from the daily snapshots."""
    out = []
    recs, _ = load_monthly(root)
    for rec in recs:
        fresh = monthly_record(rec["month"], dailies, tz_name)
        if fresh is None:
            out.append(f"monthly/{rec['month']}.json has no supporting daily snapshots")
        elif fresh != rec:
            out.append(f"monthly/{rec['month']}.json differs from a recomputation of its daily snapshots (late gap-fill or manual edit?)")
    return out
