"""Read-only GitHub client: retry/backoff, retry-after, rate-limit guard, ETag REST."""
import time

import httpx

API = "https://api.github.com"


class GitHubError(Exception):
    pass


class GitHubClient:
    def __init__(self, token: str | None, transport=None, sleep=time.sleep, max_retries: int = 3):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "profileos"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(headers=headers, timeout=30, transport=transport)
        self._sleep = sleep
        self._max = max_retries
        self.remaining: int | None = None

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        last = None
        for attempt in range(self._max + 1):
            try:
                r = self._http.request(method, url, **kw)
            except httpx.TransportError as e:
                last = e
            else:
                rem = r.headers.get("x-ratelimit-remaining")
                if rem is not None:
                    self.remaining = int(rem)
                limited = r.status_code in (429,) or (r.status_code == 403 and (rem == "0" or "retry-after" in r.headers or "secondary" in r.text.lower()))
                if r.status_code < 500 and not limited:
                    return r
                last = GitHubError(f"HTTP {r.status_code}")
                if attempt < self._max:
                    wait = float(r.headers["retry-after"]) if "retry-after" in r.headers else 2 ** attempt
                    self._sleep(min(wait, 60))
                    continue
            if attempt < self._max:
                self._sleep(2 ** attempt)
        raise GitHubError(f"request failed after {self._max + 1} attempts: {last}")

    def graphql(self, query: str, variables: dict) -> dict:
        r = self._request("POST", f"{API}/graphql", json={"query": query, "variables": variables})
        if r.status_code != 200:
            raise GitHubError(f"GraphQL HTTP {r.status_code}")
        body = r.json()
        if body.get("errors"):
            raise GitHubError("GraphQL errors: " + "; ".join(str(e.get("message")) for e in body["errors"])[:300])
        return body["data"]

    def rest(self, path: str, etags: dict | None = None):
        """GET with conditional request. Returns (status, json|None). 304 -> (304, None)."""
        headers = {}
        if etags is not None and path in etags:
            headers["If-None-Match"] = etags[path]
        r = self._request("GET", f"{API}{path}", headers=headers)
        if r.status_code == 304:
            return 304, None
        if r.status_code != 200:
            raise GitHubError(f"REST {path}: HTTP {r.status_code}")
        if etags is not None and r.headers.get("etag"):
            etags[path] = r.headers["etag"]
        return 200, r.json()

    def low_budget(self, floor: int = 100) -> bool:
        return self.remaining is not None and self.remaining < floor
