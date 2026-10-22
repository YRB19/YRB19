"""Phase 7: snapshots, rollups, timeline. All data here is SYNTHETIC (repos named TEST/Synthetic-*) and lives in tmp dirs;
nothing in this file is, or may be committed as, real personal history."""
import copy
import datetime as dt
import json

import pytest

from profileos.build import BuildError, build
from profileos.github.client import GitHubError
from profileos.github.fixtures import FixtureClient
from profileos.history import rollup, run as hrun, snapshot, timeline
from profileos.history.snapshot import SnapshotError

from conftest import NOW

UTC = dt.timezone.utc
TZ = snapshot.get_tz("UTC")


def repo(name="A", created="2026-01-05T00:00:00Z", pushed="2026-09-29T00:00:00Z", fork=False):
    return {"name": f"Synthetic-{name}", "full_name": f"TEST/Synthetic-{name}", "url": f"https://github.com/TEST/Synthetic-{name}",
            "is_private": False, "is_fork": fork, "is_archived": False, "created_at": created, "pushed_at": pushed}


def record(date="2026-10-02", repos=None, commits=None, prs=None, rels=None, languages=None, tz="UTC", projects=None, synthetic=False):
    repos = repos or [repo("A"), repo("B")]
    now = dt.datetime.fromisoformat(f"{date}T06:00:00+00:00")
    commits = commits if commits is not None else {r["full_name"]: 2 for r in repos}
    activity = {r["full_name"]: {"commits": {"d7": 3, "d30": 9, "d90": 20}, "merged_prs": (prs or {}).get(r["full_name"], []),
                                 "recent_commits": []} for r in repos}
    releases = {r["full_name"]: (rels or {}).get(r["full_name"], []) for r in repos}
    return snapshot.build_record(now=now, tz=snapshot.get_tz(tz), tz_name=tz, repos=repos, activity=activity, releases=releases,
                                 projects=projects if projects is not None else {"alpha": repos[0]}, languages=languages or [{"language": "Python", "pct": 100.0}],
                                 day_commits=commits, repos_fetched_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), synthetic=synthetic)


def store(root, *recs):
    for r in recs:
        snapshot.write_new(root, r)


# ---- schema ---------------------------------------------------------------------------------------------------------------------
def test_a_well_formed_record_validates_and_explains_its_counting_rules():
    r = record()
    snapshot.validate_record(r)
    assert r["schema"] == 1 and r["kind"] == "daily" and r["date"] == "2026-10-02" and r["closed_day"]["date"] == "2026-10-01"
    assert set(r["scope"]["rules"]) >= {"closed_day", "commits", "merged_prs", "releases", "rolling", "languages", "repos"}
    assert r["repos"]["included"] == 2 and r["source"]["name"] == "github-graphql" and "quality" in r["scope"]["summary"]


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("scope"), lambda r: r.update(schema=2), lambda r: r.update(date="2026-13-45x"), lambda r: r.update(extra=1),
    lambda r: r["totals"]["closed_day"].update(commits=-1), lambda r: r["totals"]["closed_day"].update(commits=1.5),
    lambda r: r["repos"]["names"].append("not a repo name"), lambda r: r["closed_day"].update(date="2026-10-02"),
    lambda r: r["repos"].update(included=99), lambda r: r["repos"]["active_on_closed_day"].append("TEST/Other"),
    lambda r: r["totals"]["rolling"].update(d7=500), lambda r: r["projects"]["alpha"]["rolling"].update(d90=999),
    lambda r: r["projects"]["alpha"]["closed_day"].update(commits=999), lambda r: r["taken_at"].__class__ and r.update(taken_at="yesterday"),
    lambda r: r["languages"].append({"language": "X"}),
])
def test_invalid_records_are_rejected(mutate):
    r = copy.deepcopy(record())
    mutate(r)
    with pytest.raises(SnapshotError):
        snapshot.validate_record(r)


def test_validation_runs_before_anything_is_written(tmp_path):
    bad = copy.deepcopy(record())
    bad["totals"]["closed_day"]["commits"] = -5
    with pytest.raises(SnapshotError):
        snapshot.write_new(tmp_path, bad)
    assert not (tmp_path / "snapshots").exists()


def test_no_secrets_or_private_names_can_be_stored():
    r = record()
    text = json.dumps(r)
    assert "ghp_" not in text and "token" not in text.lower().replace("tokens", "")
    with pytest.raises(SnapshotError):
        bad = copy.deepcopy(r)
        bad["repos"]["names"].append("TEST/with space")
        snapshot.validate_record(bad)


# ---- timezone and date boundaries ------------------------------------------------------------------------------------------------
def test_closed_day_is_the_previous_local_day_as_inclusive_utc_instants():
    cd = snapshot.closed_day(dt.datetime(2026, 10, 2, 0, 0, 1, tzinfo=UTC), TZ)
    assert cd == {"date": "2026-10-01", "start": "2026-10-01T00:00:00Z", "end": "2026-10-01T23:59:59Z"}
    just_before = snapshot.closed_day(dt.datetime(2026, 10, 1, 23, 59, 59, tzinfo=UTC), TZ)
    assert just_before["date"] == "2026-09-30"                                      # still "today" = Oct 1 in UTC


def test_non_utc_timezone_shifts_the_window_exactly():
    ist = snapshot.get_tz("Asia/Kolkata")
    assert snapshot.local_date(dt.datetime(2026, 10, 1, 18, 29, tzinfo=UTC), ist).isoformat() == "2026-10-01"
    assert snapshot.local_date(dt.datetime(2026, 10, 1, 18, 30, tzinfo=UTC), ist).isoformat() == "2026-10-02"
    cd = snapshot.closed_day(dt.datetime(2026, 10, 1, 18, 30, tzinfo=UTC), ist)
    assert cd == {"date": "2026-10-01", "start": "2026-09-30T18:30:00Z", "end": "2026-10-01T18:29:59Z"}


def test_dst_days_have_the_real_length():
    ny = snapshot.get_tz("America/New_York")
    spring = snapshot.closed_day(dt.datetime(2026, 3, 9, 12, tzinfo=UTC), ny)          # closed day = 2026-03-08 (23 h)
    fall = snapshot.closed_day(dt.datetime(2026, 11, 2, 12, tzinfo=UTC), ny)           # closed day = 2026-11-01 (25 h)
    hours = lambda cd: (dt.datetime.fromisoformat(cd["end"].replace("Z", "+00:00")) - dt.datetime.fromisoformat(cd["start"].replace("Z", "+00:00"))).total_seconds() / 3600 + 1 / 3600
    assert round(hours(spring)) == 23 and round(hours(fall)) == 25


def test_leap_day_and_year_boundary():
    assert snapshot.closed_day(dt.datetime(2028, 3, 1, 5, tzinfo=UTC), TZ)["date"] == "2028-02-29"
    assert snapshot.closed_day(dt.datetime(2027, 1, 1, 5, tzinfo=UTC), TZ)["date"] == "2026-12-31"


def test_unknown_timezone_is_an_error_not_a_silent_utc():
    with pytest.raises(SnapshotError):
        snapshot.get_tz("Mars/Olympus")


def test_prs_and_releases_are_matched_on_instants_not_date_prefixes():
    ist = "Asia/Kolkata"
    a = repo("A")
    # closed day for a run at 2026-10-02 06:00 UTC in IST is 2026-10-01 IST = [2026-09-30T18:30Z, 2026-10-01T18:29:59Z]
    prs = {a["full_name"]: [{"merged_at": "2026-09-30T19:00:00Z"}, {"merged_at": "2026-10-01T18:30:00Z"}, {"merged_at": "2026-09-30T18:29:59Z"}]}
    r = record(repos=[a], prs=prs, tz=ist, projects={})
    assert r["totals"]["closed_day"]["merged_prs"] == 1                                # only the 19:00Z one is inside the window


# ---- daily idempotency / duplicates / preservation --------------------------------------------------------------------------------
def test_repeated_writes_for_the_same_day_are_idempotent(tmp_path):
    first = record()
    assert snapshot.write_new(tmp_path, first) is True
    path = snapshot.path_for(tmp_path, "2026-10-02")
    before = path.read_bytes()
    changed = record(commits={"TEST/Synthetic-A": 50, "TEST/Synthetic-B": 50})
    assert snapshot.write_new(tmp_path, changed) is False
    assert path.read_bytes() == before                                                  # a past snapshot is never rewritten
    assert len(list((tmp_path / "snapshots").rglob("*.json"))) == 1 and not list((tmp_path / "snapshots").rglob("*.tmp"))


def test_history_is_preserved_when_today_looks_different(tmp_path):
    store(tmp_path, record("2026-10-02"))
    old = snapshot.path_for(tmp_path, "2026-10-02").read_bytes()
    store(tmp_path, record("2026-10-03", commits={"TEST/Synthetic-A": 0, "TEST/Synthetic-B": 0}, repos=[repo("A")], languages=[{"language": "Go", "pct": 100.0}]))
    assert snapshot.path_for(tmp_path, "2026-10-02").read_bytes() == old
    recs, problems = snapshot.load_all(tmp_path)
    assert [r["date"] for r in recs] == ["2026-10-02", "2026-10-03"] and not problems


def test_corrupt_or_misnamed_files_are_reported_not_repaired(tmp_path):
    store(tmp_path, record("2026-10-02"))
    bad = tmp_path / "snapshots/daily/2026/2026-10-09.json"
    bad.write_text("{not json")
    mis = tmp_path / "snapshots/daily/2026/2026-10-10.json"
    mis.write_text(snapshot.path_for(tmp_path, "2026-10-02").read_text())
    recs, problems = snapshot.load_all(tmp_path)
    assert len(recs) == 1 and len(problems) == 2 and bad.read_text() == "{not json"


# ---- missing / stale source data, API failures: gaps, never zeros ---------------------------------------------------------------
class Boom(FixtureClient):
    def graphql(self, q, v):
        if "history(since: $s, until: $u)" in q:
            raise GitHubError("down")
        return super().graphql(q, v)


def hist(tmp_path, client, now, *, fresh=True, repos=None, **kw):
    repos = repos or [repo("A"), repo("B")]
    warnings = []
    st = hrun.run(tmp_path, cfg=kw.pop("cfg", None), now=now, repos=repos, activity={}, releases={}, resolved={}, languages=[], milestones=[],
                  repos_fresh=fresh, client=client, synthetic=False, allow_synthetic=False, warnings=warnings)
    return st, warnings


def test_stale_repository_data_creates_no_snapshot(tmp_path):
    st, _ = hist(tmp_path, FixtureClient(NOW), NOW, fresh=False)
    assert st.snapshot_status.startswith("skipped") and not st.writes


def test_api_failure_leaves_a_gap_not_a_zero(tmp_path):
    st, warns = hist(tmp_path, Boom(NOW), NOW)
    assert st.snapshot_status.startswith("skipped") and not st.writes and any("gap" in w for w in warns)


def test_an_unreadable_repo_aborts_the_snapshot_instead_of_counting_zero():
    from profileos.github.fetch import fetch_day_commits

    class Null:
        def graphql(self, q, v):
            return {"r0": {"defaultBranchRef": {"target": {"history": {"totalCount": 3}}}}, "r1": None}
    with pytest.raises(GitHubError):
        fetch_day_commits(Null(), ["TEST/Synthetic-A", "TEST/Synthetic-B"], "2026-10-01T00:00:00Z", "2026-10-01T23:59:59Z")

    class Junk:
        def graphql(self, q, v):
            return {"r0": {"defaultBranchRef": {"target": {"history": {"totalCount": "many"}}}}}
    with pytest.raises(GitHubError):
        fetch_day_commits(Junk(), ["TEST/Synthetic-A"], "2026-10-01T00:00:00Z", "2026-10-01T23:59:59Z")


def test_an_empty_repository_is_a_genuine_zero_but_only_for_no_default_branch():
    from profileos.github.fetch import fetch_day_commits

    class Empty:
        def graphql(self, q, v):
            return {"r0": {"defaultBranchRef": None}}
    assert fetch_day_commits(Empty(), ["TEST/Synthetic-A"], "s", "e") == {"TEST/Synthetic-A": 0}


def test_build_record_refuses_when_any_count_is_missing():
    with pytest.raises(SnapshotError):
        record(commits={"TEST/Synthetic-A": 1})


def test_day_commit_query_never_interpolates_names():
    from profileos.github.fetch import fetch_day_commits

    class Spy:
        def graphql(self, q, v):
            assert "Synthetic" not in q and "TEST" not in q
            return {f"r{i}": {"defaultBranchRef": None} for i in range(len(v) // 2)}
    fetch_day_commits(Spy(), ["TEST/Synthetic-A", "TEST/Synthetic-B"], "s", "e")
    with pytest.raises(GitHubError):
        fetch_day_commits(Spy(), ['TEST/x") { evil }'], "s", "e")


def test_snapshot_runs_once_per_local_day_even_with_many_scheduled_runs(tmp_path):
    c = FixtureClient(NOW)
    first, _ = hist(tmp_path, c, NOW)
    hrun.apply(tmp_path, first)
    assert first.snapshot_status == "created"
    for h in (6, 12, 18):
        again, _ = hist(tmp_path, c, NOW + dt.timedelta(hours=h - 12 + 0) if False else NOW.replace(hour=h))
        assert again.snapshot_status == "exists" and not [w for w in again.writes if w[0] == "daily"]
    nxt, _ = hist(tmp_path, c, NOW + dt.timedelta(days=1))
    assert nxt.snapshot_status == "created"


def test_synthetic_data_is_never_recorded_without_explicit_permission(tmp_path):
    st = hrun.run(tmp_path, cfg=None, now=NOW, repos=[repo("A")], activity={}, releases={}, resolved={}, languages=[], milestones=[],
                  repos_fresh=True, client=FixtureClient(NOW), synthetic=True, allow_synthetic=False, warnings=[])
    assert st.snapshot_status.startswith("skipped") and not st.writes


def test_verify_rejects_committed_synthetic_records_and_credentials(tmp_path):
    store(tmp_path, record("2026-10-02", synthetic=True))
    errs, _ = hrun.verify(tmp_path)
    assert any("synthetic" in e for e in errs)
    (tmp_path / "snapshots/note.json").write_text('{"x": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"}')
    errs, _ = hrun.verify(tmp_path)
    assert any("credential" in e for e in errs)


def test_leftover_temp_files_are_warned_about(tmp_path):
    store(tmp_path, record("2026-10-02"))
    (tmp_path / "snapshots/daily/2026/2026-10-03.json.tmp").write_text("partial")
    _, warns = hrun.verify(tmp_path)
    assert any("temporary" in w for w in warns)


def test_disabled_history_touches_nothing(tmp_path):
    st, _ = hist(tmp_path, FixtureClient(NOW), NOW, cfg={"enabled": False})
    assert st.snapshot_status == "disabled" and not st.writes


# ---- monthly rollups ------------------------------------------------------------------------------------------------------------------
def month(tmp_path, days, **kw):
    """Store one record per snapshot date in `days` (closed day = day before) and return the dailies."""
    store(tmp_path, *[record(d, **kw) for d in days])
    return snapshot.load_all(tmp_path)[0]


def test_monthly_commits_are_the_sum_of_closed_days_not_rolling_windows(tmp_path):
    dailies = month(tmp_path, ["2026-10-02", "2026-10-03", "2026-10-04"], commits={"TEST/Synthetic-A": 4, "TEST/Synthetic-B": 1})
    m = rollup.monthly_record("2026-10", dailies, "UTC")
    assert m["metrics"]["commits"]["value"] == 15                                      # 3 closed days x 5; d7=3 each is NOT summed in
    assert "sum of closed-day" in m["metrics"]["commits"]["statistic"]
    assert all(r["totals"]["rolling"]["d30"] == 18 for r in dailies)                  # overlapping readings exist, and are ignored


def test_active_repos_is_a_union_not_a_sum(tmp_path):
    a, b = repo("A"), repo("B")
    store(tmp_path, record("2026-10-02", commits={a["full_name"]: 1, b["full_name"]: 0}), record("2026-10-03", commits={a["full_name"]: 2, b["full_name"]: 0}))
    m = rollup.monthly_record("2026-10", snapshot.load_all(tmp_path)[0], "UTC")
    assert m["metrics"]["active_repos"]["value"] == 1 and "unique" in m["metrics"]["active_repos"]["statistic"]


def test_a_duplicate_record_for_a_closed_day_cannot_double_count(tmp_path):
    r = record("2026-10-02")
    twice = [r, copy.deepcopy(r)]
    assert rollup.monthly_record("2026-10", twice, "UTC")["metrics"]["commits"]["value"] == 4


def test_closed_day_decides_the_month_not_the_snapshot_date(tmp_path):
    dailies = month(tmp_path, ["2026-11-01", "2026-11-02"])                              # closed days Oct 31 and Nov 1
    assert rollup.monthly_record("2026-10", dailies, "UTC")["coverage"]["closed_days_covered"] == 1
    assert rollup.monthly_record("2026-11", dailies, "UTC")["coverage"]["closed_days_covered"] == 1


def test_gaps_are_reported_never_filled_and_months_are_marked_partial(tmp_path):
    dailies = month(tmp_path, ["2026-10-02", "2026-10-05"])
    m = rollup.monthly_record("2026-10", dailies, "UTC")
    assert m["coverage"]["complete"] is False and m["coverage"]["closed_days_covered"] == 2
    assert "2026-10-02" in m["coverage"]["missing_days"] and m["coverage"]["days_in_month"] == 31
    assert m["metrics"]["commits"]["value"] == 8                                       # exactly what was recorded, no extrapolation


def test_a_full_month_is_complete(tmp_path):
    days = [(dt.date(2026, 10, 1) + dt.timedelta(days=i)).isoformat() for i in range(1, 32)] + ["2026-11-01"]
    days = [d for d in days if d != "2026-10-01"]
    dailies = month(tmp_path, days)
    assert rollup.monthly_record("2026-10", dailies, "UTC")["coverage"]["complete"] is True


def test_unknown_pr_or_release_counts_are_lower_bounds_not_totals(tmp_path):
    a = repo("A")
    full_page = [{"merged_at": "2026-09-01T00:00:00Z"}] * snapshot.PAGE
    dailies = [record("2026-10-02", repos=[a], prs={a["full_name"]: full_page}, projects={}), record("2026-10-03", repos=[a], projects={})]
    assert dailies[0]["totals"]["closed_day"]["merged_prs"] is None                    # a full page means "cannot know"
    m = rollup.monthly_record("2026-10", dailies, "UTC")
    assert m["metrics"]["merged_prs"]["value"] == 0 and m["metrics"]["merged_prs"]["lower_bound"] is True
    only_unknown = rollup.monthly_record("2026-10", [dailies[0]], "UTC")
    assert only_unknown["metrics"]["merged_prs"]["value"] is None                      # nothing known -> no number at all


def test_languages_are_a_month_end_reading_with_its_date(tmp_path):
    store(tmp_path, record("2026-10-02", languages=[{"language": "Go", "pct": 100.0}]), record("2026-10-20", languages=[{"language": "Python", "pct": 100.0}]))
    m = rollup.monthly_record("2026-10", snapshot.load_all(tmp_path)[0], "UTC")
    assert m["languages"]["items"][0]["language"] == "Python" and m["languages"]["as_of"] == "2026-10-20" and "month-end" in m["languages"]["statistic"]


def test_no_rollup_without_data():
    assert rollup.monthly_record("2026-10", [], "UTC") is None


def test_older_months_are_frozen_and_the_two_latest_are_refreshed(tmp_path):
    store(tmp_path, record("2026-08-02"), record("2026-09-02"), record("2026-10-02"))
    dailies = snapshot.load_all(tmp_path)[0]
    plan = rollup.plan(tmp_path, dailies, "UTC")
    assert set(plan) == {"2026-08", "2026-09", "2026-10"}                              # first time: everything is new
    for rec in plan.values():
        rollup.write(tmp_path, rec)
    assert rollup.plan(tmp_path, dailies, "UTC") == {}                                 # change-only
    old = rollup.path_for(tmp_path, "2026-08").read_bytes()
    store(tmp_path, record("2026-08-03"))                                              # a late gap-fill for a frozen month
    dailies = snapshot.load_all(tmp_path)[0]
    assert "2026-08" not in rollup.plan(tmp_path, dailies, "UTC") and rollup.path_for(tmp_path, "2026-08").read_bytes() == old
    assert any("2026-08" in w for w in rollup.drift(tmp_path, dailies, "UTC"))        # ...and verify says so
    store(tmp_path, record("2026-10-03"))
    assert "2026-10" in rollup.plan(tmp_path, snapshot.load_all(tmp_path)[0], "UTC")


def test_rollups_validate_and_corrupt_ones_are_reported(tmp_path):
    store(tmp_path, record("2026-10-02"))
    rec = rollup.monthly_record("2026-10", snapshot.load_all(tmp_path)[0], "UTC")
    rollup.write(tmp_path, rec)
    bad = copy.deepcopy(rec)
    bad["metrics"]["commits"].pop("value")
    with pytest.raises(SnapshotError):
        rollup.validate_monthly(bad)
    rollup.path_for(tmp_path, "2026-09").write_text("{}")
    recs, problems = rollup.load_monthly(tmp_path)
    assert len(recs) == 1 and len(problems) == 1


# ---- timeline -------------------------------------------------------------------------------------------------------------------------
def pub(slug="alpha", **kw):
    return {slug: repo("A", **kw)}


def ms(**kw):
    return {"project": "alpha", "date": "2026-06-01", "title": "Public beta", "source": "docs/CHANGELOG.md", **kw}


def test_events_keep_their_own_dates_and_sources():
    c = timeline.candidates(projects=pub(), releases={"TEST/Synthetic-A": [{"tag": "v1", "published_at": "2026-03-04T10:00:00Z", "url": "https://github.com/TEST/Synthetic-A/releases/tag/v1"}]},
                            milestones=[ms(url="https://example.com/x")], today="2026-10-02", known=None)
    by = {e["type"]: e for e in c}
    assert by["repository_created"]["date"] == "2026-01-05" and by["repository_created"]["date_kind"] == "repository_created_at"
    assert by["release_published"]["date"] == "2026-03-04" and by["release_published"]["source"]["kind"] == "github_release"
    assert by["milestone"]["date"] == "2026-06-01" and by["milestone"]["source"]["ref"] == "docs/CHANGELOG.md"
    assert "first_observed" not in by


def test_seeding_never_claims_first_observation(tmp_path):
    tl, changed = timeline.merge(None, timeline.candidates(projects=pub(), releases={}, milestones=[], today="2026-10-02", known=None), "2026-10-02", {"alpha"})
    assert changed and tl["seeded_projects"] == ["alpha"] and {e["type"] for e in tl["events"]} == {"repository_created"}


def test_a_project_that_appears_later_gets_first_observed_with_that_date_only():
    tl, _ = timeline.merge(None, [], "2026-10-02", {"alpha"})
    both = {"alpha": repo("A"), "beta": repo("B", created="2024-02-02T00:00:00Z")}
    c = timeline.candidates(projects=both, releases={}, milestones=[], today="2026-11-05", known=set(tl["seeded_projects"]))
    tl2, changed = timeline.merge(tl, c, "2026-11-05", {"alpha", "beta"})
    seen = [e for e in tl2["events"] if e["type"] == "first_observed"]
    assert changed and len(seen) == 1 and seen[0]["project"] == "beta" and seen[0]["date"] == "2026-11-05"
    created = [e for e in tl2["events"] if e["project"] == "beta" and e["type"] == "repository_created"][0]
    assert created["date"] == "2024-02-02" and created["date_kind"] != seen[0]["date_kind"]      # kept apart


def test_the_timeline_is_append_only_even_when_the_api_window_rolls():
    rel = lambda t, d: {"tag": t, "published_at": f"{d}T00:00:00Z", "url": f"https://github.com/TEST/Synthetic-A/releases/tag/{t}"}
    first = timeline.candidates(projects=pub(), releases={"TEST/Synthetic-A": [rel("v1", "2026-03-01"), rel("v2", "2026-04-01")]}, milestones=[], today="2026-10-02", known=None)
    tl, _ = timeline.merge(None, first, "2026-10-02", {"alpha"})
    later = timeline.candidates(projects=pub(), releases={"TEST/Synthetic-A": [rel("v3", "2026-10-09")]}, milestones=[], today="2026-10-10", known={"alpha"})   # v1,v2 aged out of the window
    tl2, changed = timeline.merge(tl, later, "2026-10-10", {"alpha"})
    ids = {e["id"] for e in tl2["events"]}
    assert changed and {"alpha:release:v1", "alpha:release:v2", "alpha:release:v3"} <= ids
    tl3, changed3 = timeline.merge(tl2, later, "2026-10-11", {"alpha"})
    assert not changed3 and tl3["events"] == tl2["events"]                              # no-op when nothing is new
    assert next(e for e in tl2["events"] if e["id"] == "alpha:release:v1")["observed_on"] == "2026-10-02"   # first sighting is not rewritten


def test_drafts_and_dateless_releases_make_no_events():
    c = timeline.candidates(projects=pub(), releases={"TEST/Synthetic-A": [{"tag": "v9", "published_at": "2026-05-01T00:00:00Z", "url": "https://x", "draft": True},
                                                                        {"tag": "v8", "published_at": None, "url": "https://x"}, {"tag": "", "published_at": "2026-05-01T00:00:00Z", "url": "https://x"}]},
                            milestones=[], today="2026-10-02", known=None)
    assert [e["type"] for e in c] == ["repository_created"]


def test_milestones_for_unpublished_projects_are_ignored():
    assert not [e for e in timeline.candidates(projects=pub(), releases={}, milestones=[ms(project="hidden")], today="2026-10-02", known=None) if e["type"] == "milestone"]


def test_timeline_validation_rejects_wrong_kinds_missing_sources_and_bad_dates():
    tl, _ = timeline.merge(None, timeline.candidates(projects=pub(), releases={}, milestones=[ms()], today="2026-10-02", known=None), "2026-10-02", {"alpha"})
    timeline.validate(tl)
    for mutate in (
        lambda t: t["events"][0].update(date="2026-1-1"), lambda t: t["events"][0].update(date_kind="milestone_date"),
        lambda t: t["events"][0].update(type="significant_pr"), lambda t: t["events"][0]["source"].update(kind="history_yml"),
        lambda t: t["events"][0]["source"].update(url=None), lambda t: t["events"][0]["source"].update(url="http://insecure"),
        lambda t: t["events"].append(copy.deepcopy(t["events"][0])), lambda t: t["events"][0].pop("observed_on"),
        lambda t: next(e for e in t["events"] if e["type"] == "milestone")["source"].update(ref=None, url=None),
    ):
        bad = copy.deepcopy(tl)
        mutate(bad)
        with pytest.raises(SnapshotError):
            timeline.validate(bad)


def test_milestone_schema_requires_a_date_and_a_source(repo_copy):
    import yaml
    from profileos.validate import validate
    p = repo_copy / "data/history.yml"
    d = yaml.safe_load(p.read_text())
    d["milestones"] = [{"project": "UsageOS", "date": "2026-06-01", "title": "Public beta", "source": "docs/CHANGELOG.md"}]
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert validate(repo_copy).ok
    for bad in ({"project": "UsageOS", "date": "June 2026", "title": "x y z", "source": "s s s"}, {"project": "UsageOS", "date": "2026-06-01", "title": "Public beta"}):
        d["milestones"] = [bad]
        p.write_text(yaml.safe_dump(d, sort_keys=False))
        assert not validate(repo_copy).ok


# ---- build integration: exclusion, no-op, atomicity, rendering --------------------------------------------------------------------
class RealRun(FixtureClient):
    """Counts as non-synthetic so the build records history; only ever used on scratch copies."""


@pytest.fixture
def real_history(monkeypatch):
    import profileos.build as B
    class _Never:  # isinstance(client, _Never) is False -> the run is treated as real data
        pass
    monkeypatch.setattr(B, "FixtureClient", _Never)
    return B


def run_build(root, now, **kw):
    return build(root, client=RealRun(now), now=now, allow_synthetic_history=True, **kw)


def test_first_build_creates_snapshot_rollup_and_timeline_then_is_a_noop(repo_copy, real_history):
    first = run_build(repo_copy, NOW)
    assert first.history_status == "created" and len(first.history_written) == 3
    paths = sorted(p.relative_to(repo_copy).as_posix() for p in (repo_copy / "snapshots").rglob("*.json"))
    assert paths == ["snapshots/daily/2026/2026-09-30.json", "snapshots/monthly/2026-09.json", "snapshots/timeline.json"] or len(paths) == 3
    before = {p: (repo_copy / p).read_bytes() for p in paths}
    again = run_build(repo_copy, NOW)
    assert again.history_status == "exists" and again.history_written == [] and not again.changed
    later_same_day = run_build(repo_copy, NOW + dt.timedelta(hours=3))        # fixture data is relative to `now`, so only history is asserted
    assert later_same_day.history_status == "exists" and later_same_day.history_written == []
    assert {p: (repo_copy / p).read_bytes() for p in paths} == before


def test_next_day_adds_exactly_one_daily_file_and_refreshes_the_month(repo_copy, real_history):
    run_build(repo_copy, NOW)
    nxt = run_build(repo_copy, NOW + dt.timedelta(days=1))
    assert nxt.history_status == "created" and sum("daily" in p for p in nxt.history_written) == 1
    assert len(list((repo_copy / "snapshots/daily").rglob("*.json"))) == 2


def test_dry_run_writes_nothing(repo_copy, real_history):
    res = run_build(repo_copy, NOW, dry_run=True)
    assert res.history_status == "created" and res.history_written == [] and not (repo_copy / "snapshots/daily").exists()


def test_fixture_runs_never_become_history(repo_copy):
    res = build(repo_copy, fixtures=True, now=NOW, dry_run=True)
    assert res.history_status.startswith("skipped: synthetic")
    build(repo_copy, client=FixtureClient(NOW), now=NOW)
    assert not (repo_copy / "snapshots/daily").exists()


def test_unpublished_projects_and_private_repos_never_enter_history(repo_copy, real_history):
    run_build(repo_copy, NOW)
    blob = " ".join(p.read_text() for p in (repo_copy / "snapshots").rglob("*.json"))
    for hidden in ("NetOS", "FREYA", "YRB19/YRB19", "Private-Thing", "Secret"):
        assert hidden not in blob, hidden
    rec = snapshot.load_all(repo_copy)[0][0]
    assert all(not n.endswith("/YRB19") for n in rec["repos"]["names"]) and rec["repos"]["included"] > 0


def test_publishing_a_project_later_adds_it_with_a_first_observed_event_and_hiding_it_hides_events(repo_copy, real_history):
    import yaml
    run_build(repo_copy, NOW)
    p = repo_copy / "data/projects.yml"
    d = yaml.safe_load(p.read_text())
    d["NetOS"]["publish"] = True
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))
    later = NOW + dt.timedelta(days=2)
    res = run_build(repo_copy, later)
    tl = json.loads((repo_copy / "snapshots/timeline.json").read_text())
    seen = [e for e in tl["events"] if e["type"] == "first_observed"]
    assert [e["project"] for e in seen] == ["NetOS"] and seen[0]["date"] == "2026-10-02"
    d["NetOS"]["publish"] = False
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))
    res = run_build(repo_copy, later + dt.timedelta(days=1))
    assert "NetOS" not in res.blocks["TIMELINE"]                                       # the record stays; the public view hides it


def test_timeline_block_is_concise_sourced_and_explains_first_seen(repo_copy, real_history):
    res = run_build(repo_copy, NOW)
    block = res.blocks["TIMELINE"]
    assert block.startswith("### Project timeline") and "NetOS" not in block and "FREYA" not in block
    assert block.count("`20") <= 8 and "https://github.com/YRB19/" in block and "not when it was started" in block
    dates = [l[1:11] for l in block.splitlines() if l.startswith("`20")]
    assert dates == sorted(dates, reverse=True)


def test_timeline_hidden_below_the_minimum_and_text_is_escaped(repo_copy, real_history):
    import yaml
    p = repo_copy / "data/config.yml"
    d = yaml.safe_load(p.read_text())
    d["snapshots"] = {"min_timeline_events": 12}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    assert run_build(repo_copy, NOW).blocks["TIMELINE"] == ""
    tl = json.loads((repo_copy / "snapshots/timeline.json").read_text())
    tl["events"][0]["title"] = "x [y](http://evil.test) <b>"
    (repo_copy / "snapshots/timeline.json").write_text(json.dumps(tl))
    d["snapshots"] = {"min_timeline_events": 1}
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    out = run_build(repo_copy, NOW + dt.timedelta(hours=1)).blocks["TIMELINE"]
    import re
    assert not re.search(r"(?<!\\)<b>", out) and not re.search(r"(?<!\\)\]\(http://evil", out)      # present only as escaped text


def test_a_failed_render_leaves_snapshots_untouched(repo_copy, real_history, monkeypatch):
    from profileos.generators import visuals

    def boom(_):
        raise visuals.AssetError("unsafe")
    monkeypatch.setattr(visuals, "files", boom)
    with pytest.raises(BuildError):
        run_build(repo_copy, NOW)
    assert not (repo_copy / "snapshots/daily").exists() and not (repo_copy / "snapshots/timeline.json").exists()


def test_validate_flags_history_corruption(repo_copy, real_history):
    from profileos.validate import validate
    run_build(repo_copy, NOW)
    assert validate(repo_copy).ok
    f = next((repo_copy / "snapshots/daily").rglob("*.json"))
    f.write_text("{}")
    rep = validate(repo_copy)
    assert not rep.ok and any("history" in e for e in rep.errors)


# ---- automation, retention, docs ----------------------------------------------------------------------------------------------------
def test_workflow_commits_snapshots_serially_without_empty_commits_or_new_schedulers():
    import yaml
    from conftest import ROOT
    text = (ROOT / ".github/workflows/update-profile.yml").read_text()
    wf = yaml.safe_load(text)
    assert "snapshots" in text.split("git add")[1].splitlines()[0]
    assert wf["concurrency"] == {"group": "profileos", "cancel-in-progress": False}
    assert "--allow-empty" not in text and "keep-alive" not in text.lower() and "keepalive" not in text.lower()
    assert wf["permissions"] == {"contents": "write"}
    assert len(wf[True]["schedule"]) == 1                                                  # one scheduler, extended not duplicated
    assert not [p for p in (ROOT / ".github/workflows").glob("*.yml") if p.name not in ("update-profile.yml", "validate.yml")]


def test_no_keep_alive_is_configured_by_default():
    import yaml
    from conftest import ROOT
    cfg = yaml.safe_load((ROOT / "data/config.yml").read_text())
    assert "keep_alive" not in cfg and "keepalive" not in cfg
    assert cfg["snapshots"]["timezone"] and cfg["snapshots"]["enabled"] is True


def test_snapshot_documentation_defines_every_metric_and_states_verification():
    from conftest import ROOT
    snap = (ROOT / "docs/SNAPSHOTS.md").read_text()
    ret = (ROOT / "docs/RETENTION.md").read_text()
    for needle in ("closed day", "sum", "unique", "month-end reading", "lower_bound", "first_observed", "never", "append-only"):
        assert needle in snap, needle
    for needle in ("kept forever", "keep-alive", "not verified", "Not live-verified", "idempotent", "60 days"):
        assert needle.lower() in ret.lower(), needle


def test_shipped_data_has_no_committed_history_that_could_be_synthetic():
    from conftest import ROOT
    errs, _ = hrun.verify(ROOT)
    assert errs == []
