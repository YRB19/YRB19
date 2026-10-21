"""CI status: accurate states, never green on missing/stale/ambiguous data, least-privilege authentication."""
import datetime as dt

import httpx
import pytest

from profileos.github.client import GitHubClient, GitHubError
from profileos.status import ci

from conftest import NOW

REPO = {"full_name": "YRB19/A", "default_branch": "main"}


def run(status="completed", conclusion="success", wf=1, name="CI", days=1, event="push"):
    t = (NOW - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"workflow_id": wf, "name": name, "path": f".github/workflows/{name.lower()}.yml", "event": event, "status": status,
            "conclusion": conclusion, "created_at": t, "updated_at": t, "html_url": f"https://github.com/YRB19/A/actions/runs/{wf}"}


def clients_for(handler, token=None, status_token=None):
    return ci.build_clients(token, status_token, transport=httpx.MockTransport(handler), sleep=lambda s: None)[0]


def ok(runs, headers=None):
    return lambda req: httpx.Response(200, json={"workflow_runs": runs}, headers=headers or {})


def fetch(handler, **kw):
    return ci.fetch_ci(clients_for(handler, **kw), [REPO], NOW)


# ---- state mapping ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("status,conclusion,expected", [
    ("completed", "success", "passing"), ("completed", "failure", "failing"), ("completed", "timed_out", "failing"),
    ("completed", "startup_failure", "failing"), ("completed", "cancelled", "cancelled"),
    ("in_progress", None, "in_progress"), ("queued", None, "queued"), ("waiting", None, "queued"),
    ("completed", "skipped", "unknown"), ("completed", "neutral", "unknown"), ("completed", "action_required", "unknown"),
    ("completed", None, "unknown"), ("weird", None, "unknown"),
])
def test_run_classification(status, conclusion, expected):
    assert ci.classify_run({"status": status, "conclusion": conclusion}) == expected


def test_successful_fetch_records_workflow_time_link_and_source():
    out, warns = fetch(ok([run()]))
    rec = out["YRB19/A"]
    assert rec["state"] == "passing" and rec["workflow"] == "CI" and rec["url"].endswith("/actions/runs/1")
    assert rec["run_at"] and rec["checked_at"] == "2026-09-30T12:00:00Z" and rec["source"] == "github-actions-api" and not warns


def test_failed_run_is_failing():
    assert fetch(ok([run(conclusion="failure")]))[0]["YRB19/A"]["state"] == "failing"


def test_worst_workflow_wins_never_greener_than_evidence():
    runs = [run(wf=1, name="CI"), run(wf=2, name="Lint", conclusion="failure"), run(wf=3, name="Docs", status="in_progress", conclusion=None)]
    assert fetch(ok(runs))[0]["YRB19/A"]["state"] == "failing"
    assert ci.summarize([run(wf=1), run(wf=3, status="in_progress", conclusion=None)], NOW, workflow=None, max_run_age_days=90)["state"] == "in_progress"
    assert ci.summarize([run(wf=1), run(wf=4, conclusion="skipped")], NOW, workflow=None, max_run_age_days=90)["state"] == "unknown"


def test_only_the_latest_run_per_workflow_counts():
    runs = [run(conclusion="failure", days=5), run(conclusion="success", days=1)]
    assert ci.summarize(runs, NOW, workflow=None, max_run_age_days=90)["state"] == "passing"


def test_configured_workflow_selects_by_name_or_file():
    runs = [run(wf=1, name="CI"), run(wf=2, name="Nightly", conclusion="failure")]
    assert ci.summarize(runs, NOW, workflow="ci.yml", max_run_age_days=90)["state"] == "passing"
    assert ci.summarize(runs, NOW, workflow="Nightly", max_run_age_days=90)["state"] == "failing"
    assert ci.summarize(runs, NOW, workflow="missing", max_run_age_days=90)["state"] == "not_configured"


# ---- missing / stale ------------------------------------------------------------------------------------------------------
def test_no_workflow_runs_is_not_configured_not_green():
    assert fetch(ok([]))[0]["YRB19/A"]["state"] == "not_configured"


def test_old_passing_run_is_unknown_not_green():
    rec = ci.summarize([run(days=200)], NOW, workflow=None, max_run_age_days=90)
    assert rec["state"] == "unknown" and "200 days" in rec["reason"]
    assert ci.summarize([run(conclusion="failure", days=200)], NOW, workflow=None, max_run_age_days=90)["state"] == "failing"  # bad news never expires


def test_unparseable_run_time_is_unknown():
    r = run()
    r["updated_at"] = r["created_at"] = "not a date"
    assert ci.summarize([r], NOW, workflow=None, max_run_age_days=90)["state"] == "unknown"


def test_stale_cache_degrades_to_unknown_and_young_cache_is_kept():
    rec = {"state": "passing", "checked_at": "2026-09-30T00:00:00Z"}
    assert ci.effective(rec, NOW, fresh=True, stale_after_h=72) is rec
    young = ci.effective(rec, NOW + dt.timedelta(hours=10), fresh=False, stale_after_h=72)
    assert young["state"] == "passing" and "stale" not in young
    labelled = ci.effective(rec, NOW + dt.timedelta(hours=40), fresh=False, stale_after_h=72)
    assert labelled["state"] == "passing" and labelled["stale"]
    dead = ci.effective(rec, NOW + dt.timedelta(hours=100), fresh=False, stale_after_h=72)
    assert dead["state"] == "unknown" and dead["stale"]
    assert ci.effective({"state": "passing"}, NOW, fresh=False, stale_after_h=72)["state"] == "unknown"   # no timestamp -> untrusted
    assert ci.effective(None, NOW, fresh=False, stale_after_h=72) is None


# ---- outages and rate limits ------------------------------------------------------------------------------------------------
def test_outage_yields_no_record_so_cache_rules_apply():
    out, warns = fetch(lambda req: httpx.Response(503))
    assert out == {} and any("unavailable" in w for w in warns)


def test_transport_failure_yields_no_record():
    def boom(req):
        raise httpx.ConnectError("down")
    out, warns = fetch(boom)
    assert out == {} and warns


def test_rate_limit_stops_further_calls_and_is_reported():
    calls = []

    def limited(req):
        calls.append(req.url.path)
        return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, text="rate limit exceeded")

    repos = [{"full_name": f"YRB19/R{i}", "default_branch": "main"} for i in range(3)]
    out, warns = ci.fetch_ci(clients_for(limited), repos, NOW)
    assert out == {} and any("rate limited" in w for w in warns)
    assert len({p.split("/")[2] for p in calls}) == 1          # stopped after the first repo; no quota burn


def test_garbage_and_unexpected_shapes_are_rejected():
    for body in ("not json", '{"workflow_runs": "x"}', "[]", '{"other": 1}'):
        out, warns = fetch(lambda req, b=body: httpx.Response(200, text=b))
        assert out == {} and warns, body


def test_unsafe_repo_or_branch_names_are_never_requested():
    seen = []
    handler = lambda req: (seen.append(str(req.url)), httpx.Response(200, json={"workflow_runs": []}))[1]
    out, warns = ci.fetch_ci(clients_for(handler), [{"full_name": "YRB19/A?x=1", "default_branch": "main"},
                                                    {"full_name": "YRB19/A", "default_branch": "main&per_page=1000"}], NOW)
    assert not seen and out == {} and len(warns) == 2


# ---- least privilege ----------------------------------------------------------------------------------------------------------
def test_requests_are_read_only_gets_to_the_runs_endpoint():
    seen = []
    handler = lambda req: (seen.append((req.method, req.url.path)), httpx.Response(200, json={"workflow_runs": [run()]}))[1]
    fetch(handler, token="t", status_token="s")
    assert seen and all(m == "GET" and p == "/repos/YRB19/A/actions/runs" for m, p in seen)


def test_most_specific_credential_is_tried_first_then_it_steps_down_never_up():
    auth = []

    def handler(req):
        auth.append(req.headers.get("authorization"))
        return httpx.Response(403) if req.headers.get("authorization") else httpx.Response(200, json={"workflow_runs": [run()]})

    out, _ = fetch(handler, token="gh-token", status_token="read-only-pat")
    assert auth == ["Bearer read-only-pat", "Bearer gh-token", None]      # decreasing privilege, ending at public data
    assert out["YRB19/A"]["state"] == "passing" and out["YRB19/A"]["auth"] == "public"


def test_public_fallback_works_with_no_token_at_all():
    auth = []
    handler = lambda req: (auth.append(req.headers.get("authorization")), httpx.Response(200, json={"workflow_runs": [run()]}))[1]
    out, _ = fetch(handler)
    assert auth == [None] and out["YRB19/A"]["auth"] == "public"


def test_token_that_cannot_read_falls_back_instead_of_reporting_failure():
    def handler(req):
        return httpx.Response(404) if req.headers.get("authorization") else httpx.Response(200, json={"workflow_runs": [run()]})
    assert fetch(handler, token="x")[0]["YRB19/A"]["state"] == "passing"


def test_invisible_repo_everywhere_is_skipped_not_green():
    out, warns = fetch(lambda req: httpx.Response(404), token="x")
    assert out == {} and any("not visible" in w for w in warns)


@pytest.mark.parametrize("scopes,broad", [
    ("repo", True), ("public_repo", True), ("read:org, repo, workflow", True), ("admin:org", True), ("write:packages", True),
    ("delete_repo", True), ("workflow", True), ("", False), (None, False), ("read:org", False), ("read:user", False)])
def test_broad_classic_token_scopes_are_detected(scopes, broad):
    assert ci.broad_scope(scopes) is broad


def test_broad_status_token_is_refused_and_replaced_by_less_privileged_access():
    sent = []

    def handler(req):
        sent.append(req.headers.get("authorization"))
        hdr = {"x-oauth-scopes": "repo, workflow"} if req.headers.get("authorization") == "Bearer big" else {}
        return httpx.Response(200, json={"workflow_runs": [run()]}, headers=hdr)

    repos = [{"full_name": "YRB19/A", "default_branch": "main"}, {"full_name": "YRB19/B", "default_branch": "main"}]
    out, warns = ci.fetch_ci(clients_for(handler, token="gh", status_token="big"), repos, NOW)
    assert any("NOT used" in w for w in warns)
    assert sent.count("Bearer big") == 1                       # contacted once to learn its scopes, never again
    assert all(r["auth"] == "github-token" for r in out.values()) and len(out) == 2


def test_failures_never_leak_tokens_into_warnings():
    out, warns = fetch(lambda req: httpx.Response(500), token="ghp_SECRETSECRET", status_token="github_pat_SECRET")
    assert "SECRET" not in " ".join(warns)
