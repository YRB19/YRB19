import httpx
import pytest

from profileos.github.client import GitHubClient, GitHubError


def make(handler, sleeps):
    return GitHubClient("t", transport=httpx.MockTransport(handler), sleep=sleeps.append)


def test_retries_5xx_with_exponential_backoff():
    calls, sleeps = [], []

    def h(req):
        calls.append(1)
        return httpx.Response(500) if len(calls) < 3 else httpx.Response(200, json={"data": {"ok": 1}})

    assert make(h, sleeps).graphql("q", {}) == {"ok": 1}
    assert sleeps == [1, 2]


def test_honours_retry_after_on_rate_limit():
    calls, sleeps = [], []

    def h(req):
        calls.append(1)
        return httpx.Response(403, headers={"retry-after": "7", "x-ratelimit-remaining": "0"}) if len(calls) == 1 else httpx.Response(200, json={"data": {}})

    make(h, sleeps).graphql("q", {})
    assert sleeps == [7.0]


def test_gives_up_after_max_retries():
    sleeps = []
    with pytest.raises(GitHubError):
        make(lambda r: httpx.Response(502), sleeps).graphql("q", {})
    assert sleeps == [1, 2, 4]


def test_graphql_errors_raise():
    with pytest.raises(GitHubError):
        make(lambda r: httpx.Response(200, json={"errors": [{"message": "bad"}]}), []).graphql("q", {})


def test_etag_conditional_requests_and_budget_guard():
    seen = []

    def h(req):
        seen.append(req.headers.get("if-none-match"))
        if req.headers.get("if-none-match") == '"abc"':
            return httpx.Response(304, headers={"x-ratelimit-remaining": "42"})
        return httpx.Response(200, json=[1], headers={"etag": '"abc"', "x-ratelimit-remaining": "4000"})

    c, etags = make(h, []), {}
    assert c.rest("/x", etags) == (200, [1])
    assert c.rest("/x", etags) == (304, None)
    assert seen == [None, '"abc"']
    assert c.low_budget() is True  # remaining 42 < 100
