"""Project timeline: an append-only list of VERIFIED events, each keeping its own source and date.

Four different dates are kept apart and never substituted for one another:
  repository_created  <- GitHub `createdAt` of the repository (not a launch date)
  release_published   <- GitHub `publishedAt` of a non-draft release
  milestone           <- an explicit, dated, sourced entry the owner wrote in data/history.yml
  first_observed      <- the day ProfileOS first recorded a project; ONLY for projects that appeared after the timeline was
                         seeded. Projects already known at seeding get none: their first sighting says nothing about the project.
No event is inferred from commits, and "significant pull request" is deliberately not an event type (significance cannot be
established from API data without ranking work, which this profile never does).
"""
import json
import os
from pathlib import Path

import jsonschema

from ..data import load_schema
from ..sanitize import clean_text
from .snapshot import DIR, SnapshotError

FILE = "timeline.json"
LABEL = {"repository_created": "created", "release_published": "release", "milestone": "milestone", "first_observed": "observed"}
DATE_KIND = {"repository_created": "repository_created_at", "release_published": "release_published_at",
             "milestone": "milestone_date", "first_observed": "first_observed_by_profileos"}


def path(root: Path) -> Path:
    return Path(root) / DIR / FILE


def validate(tl: dict) -> None:
    errs = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
            for e in jsonschema.Draft7Validator(load_schema("timeline")).iter_errors(tl)]
    seen = set()
    for ev in tl.get("events", []) if not errs else []:
        if ev["id"] in seen:
            errs.append(f"duplicate event id {ev['id']}")
        seen.add(ev["id"])
        if ev["date_kind"] != DATE_KIND[ev["type"]]:
            errs.append(f"{ev['id']}: date_kind {ev['date_kind']} does not belong to type {ev['type']}")
        kind, need_url = ev["source"]["kind"], {"repository_created": "github_repository", "release_published": "github_release",
                                                 "milestone": "history_yml", "first_observed": "profileos_observation"}[ev["type"]]
        if kind != need_url:
            errs.append(f"{ev['id']}: source kind {kind} does not support type {ev['type']}")
        if ev["type"] in ("repository_created", "release_published") and not ev["source"].get("url"):
            errs.append(f"{ev['id']}: GitHub-sourced events need a source url")
        if ev["type"] == "milestone" and not (ev["source"].get("ref") or ev["source"].get("url")):
            errs.append(f"{ev['id']}: a milestone needs a documented source")
    if errs:
        raise SnapshotError("invalid timeline: " + "; ".join(errs))


def load(root: Path) -> tuple[dict | None, list]:
    p = path(root)
    if not p.exists():
        return None, []
    try:
        tl = json.loads(p.read_text(encoding="utf-8"))
        validate(tl)
        return tl, []
    except (OSError, ValueError, SnapshotError) as e:
        return None, [f"{p.name}: {e}"]


def candidates(*, projects: dict, releases: dict, milestones: list, today: str, known: set | None):
    """Events derivable from current data. projects: {slug: repo dict} for PUBLISHED projects only."""
    out = []
    for slug, r in sorted(projects.items()):
        out.append({"id": f"{slug}:created", "project": slug, "type": "repository_created", "date": r["created_at"][:10],
                    "title": "Repository created", "source": {"kind": "github_repository", "url": r["url"], "ref": None}})
        for rel in releases.get(r["full_name"], []):
            if rel.get("draft") or not rel.get("published_at") or not rel.get("tag"):
                continue
            out.append({"id": f"{slug}:release:{clean_text(rel['tag'], 40)}", "project": slug, "type": "release_published",
                        "date": rel["published_at"][:10], "title": clean_text(f"Release {rel['tag']}", 80),
                        "source": {"kind": "github_release", "url": rel["url"], "ref": None}})
        if known is not None and slug not in known:
            out.append({"id": f"{slug}:first-observed", "project": slug, "type": "first_observed", "date": today,
                        "title": "First seen by ProfileOS", "source": {"kind": "profileos_observation", "url": None, "ref": "profileos project discovery"}})
    for m in milestones or []:
        if m["project"] in projects:
            out.append({"id": f"{m['project']}:milestone:{m['date']}:{clean_text(m['title'], 40)}", "project": m["project"], "type": "milestone",
                        "date": m["date"], "title": clean_text(m["title"], 80),
                        "source": {"kind": "history_yml", "url": m.get("url"), "ref": clean_text(m["source"], 200)}})
    for ev in out:
        ev["date_kind"] = DATE_KIND[ev["type"]]
    return out


def merge(existing: dict | None, cands: list, today: str, project_slugs: set) -> tuple[dict, bool]:
    """Append events not yet recorded. Recorded events are NEVER altered or removed (the API's release window rolls
    forward; the timeline must not). Returns (timeline, changed)."""
    if existing is None:
        tl = {"schema": 1, "seeded_on": today, "seeded_projects": sorted(project_slugs), "events": []}
        # at seeding no project may claim a "first observed" event
        cands = [c for c in cands if c["type"] != "first_observed"]
    else:
        tl = {**existing, "events": list(existing["events"])}
    have = {e["id"] for e in tl["events"]}
    added = []
    for c in cands:
        if c["id"] in have:
            continue
        added.append({**c, "observed_on": today})
        have.add(c["id"])
    tl["events"] = sorted(tl["events"] + added, key=lambda e: (e["date"], e["project"], e["type"], e["id"]))
    return tl, bool(added) or existing is None


def write(root: Path, tl: dict) -> None:
    validate(tl)
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(tl, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)
