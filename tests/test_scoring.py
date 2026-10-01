import datetime as dt

from profileos.analytics import scoring

NOW = dt.datetime(2026, 9, 30, tzinfo=dt.timezone.utc)
W = {"recency": 0.35, "volume": 0.25, "momentum": 0.25, "manual": 0.15}
T = {"active": 0.45, "quiet": 0.15}


def score(**kw):
    base = dict(commits_7d=0, commits_30d=0, prs_30d=0, releases_30d=0, pushed_at="2026-09-30T00:00:00Z", priority=50, now=NOW, weights=W)
    base.update(kw)
    return scoring.activity_score(**base)


def test_fresh_busy_repo_is_active():
    assert score(commits_7d=10, commits_30d=30, releases_30d=1) >= T["active"]


def test_dormant_repo_is_hidden():
    s = score(pushed_at="2025-01-01T00:00:00Z", priority=50)
    assert scoring.state_for("active", s, None, T) is None


def test_commit_count_alone_does_not_decide():
    stale_but_many = score(commits_30d=40, pushed_at="2026-06-01T00:00:00Z", priority=0)
    assert stale_but_many < T["active"]


def test_override_and_status_order():
    assert scoring.state_for("active", 0.0, "force_active", T) == "active"
    assert scoring.state_for("active", 1.0, "force_quiet", T) == "quiet"
    assert scoring.state_for("active", 1.0, "hide", T) is None
    assert scoring.state_for("paused", 1.0, None, T) is None
    assert scoring.state_for("archived", 1.0, None, T) is None
    assert scoring.state_for("archived", 0.0, "force_active", T) == "active"  # spec order: override first


def test_threshold_boundaries():
    assert scoring.state_for("active", 0.45, None, T) == "active"
    assert scoring.state_for("active", 0.449, None, T) == "quiet"
    assert scoring.state_for("active", 0.15, None, T) == "quiet"
    assert scoring.state_for("active", 0.149, None, T) is None


def test_priority_index_neutral_for_unknown_signals():
    a = scoring.priority_index(manual_priority=50, activity=0.5, has_release=False)
    b = scoring.priority_index(manual_priority=50, activity=0.5, has_release=False, ci=0.5, docs=0.5)
    assert a == b
