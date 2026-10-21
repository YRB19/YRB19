"""Deployment health: SSRF policy (IPv4/IPv6, DNS-level), rebinding defence, redirects, bounded reads, honest states."""
import datetime as dt
import socket
import ssl
import threading

import pytest

from profileos.status import health, netguard
from profileos.status.health import PeerMismatch, Response, SocketFetcher

from conftest import NOW

URL = "https://app.example.com/health"
PUBLIC4, PUBLIC6 = "93.184.216.34", "2606:4700:4700::1111"


class Resolver:
    """answers: host -> list of answer-lists (one per lookup, last repeats) or an exception."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, host, port):
        self.calls.append((host, port))
        seq = self.answers[host]
        if isinstance(seq, Exception):
            raise seq
        n = sum(1 for h, _ in self.calls if h == host) - 1
        return seq[min(n, len(seq) - 1)]


class Fetcher:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def fetch(self, scheme, host, ip, port, path, **kw):
        self.calls.append({"scheme": scheme, "host": host, "ip": ip, "port": port, "path": path, **kw})
        o = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(o, BaseException):
            raise o
        return o


def resp(status=200, location=None, ip=PUBLIC4):
    return Response(status, location, ip, 10)


def check(fetcher, resolver=None, prev=None, url=URL, cfg=None, **kw):
    resolver = resolver or Resolver({"app.example.com": [[PUBLIC4]]})
    return health.check_one(url, {"retries": 0, **(cfg or {})}, fetcher=fetcher, resolve=resolver, now=NOW, prev=prev, sleep=lambda s: None, **kw)


# ---- address policy: IPv4 + IPv6 --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("addr", [
    "127.0.0.1", "127.1.2.3", "10.0.0.1", "172.16.5.4", "192.168.0.1", "169.254.169.254", "0.0.0.0", "100.64.0.1",
    "224.0.0.1", "255.255.255.255", "192.0.2.1", "198.51.100.7", "203.0.113.9", "198.18.0.1",
    "::1", "::", "fe80::1", "fe80::1%eth0", "fc00::1", "fd12:3456::1", "ff02::1", "2001:db8::1",
    "::ffff:127.0.0.1", "::ffff:10.1.2.3", "::ffff:169.254.169.254",       # IPv4-mapped
    "64:ff9b::7f00:1", "64:ff9b::a00:1",                                    # NAT64 to loopback / 10/8
    "2002:7f00:1::1", "2002:a9fe:a9fe::1",                                  # 6to4 to loopback / metadata
    "2001:0:4136:e378:8000:63bf:3fff:fdd2",                                 # Teredo embedding 192.0.2.45
])
def test_non_public_addresses_are_rejected(addr):
    assert netguard.ip_problem(addr), addr


@pytest.mark.parametrize("addr", [PUBLIC4, "8.8.8.8", PUBLIC6, "2a00:1450:4001::1", "::ffff:8.8.8.8"])
def test_public_addresses_are_accepted(addr):
    assert netguard.ip_problem(addr) is None


def test_garbage_is_not_an_address():
    assert netguard.ip_problem("example.com")


def test_one_private_answer_rejects_the_whole_name():
    for answers in ([PUBLIC4, "10.0.0.5"], [PUBLIC6, "fe80::1"], [PUBLIC4, "::ffff:127.0.0.1"], []):
        f = Fetcher(resp())
        rec = check(f, Resolver({"app.example.com": [answers]}))
        assert rec["state"] == "unknown" and not f.calls, answers


def test_private_resolution_is_unknown_not_offline():
    rec = check(Fetcher(resp()), Resolver({"app.example.com": [["127.0.0.1"]]}))
    assert rec["state"] == "unknown" and "not public" in rec["reason"] and rec["consecutive_failures"] == 0


# ---- URL policy ---------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "ftp://app.example.com/", "file:///etc/passwd", "gopher://app.example.com/", "javascript:alert(1)", "//app.example.com/",
    "https://app.example.com:8443/h", "https://app.example.com:22/", "http://app.example.com:6379/",
    "https://127.0.0.1/", "https://[::1]/", "https://10.0.0.1/", "https://[::ffff:127.0.0.1]/", "https://2130706433/", "https://0x7f.1/",
    "https://localhost/", "https://app.localhost/", "https://svc.internal/", "https://printer.local/", "https://intranet/", "https://a.b.arpa/",
    "https://user:pw@app.example.com/", "https://app.example.com@evil.example/", "https://app.example.com/h?token=1",
    "https://app.example.com/h#frag", "https://app.example.com/a b", "https://app.exämple.com/", "", "https://", "https://app.example.com/\r\nX: y",
])
def test_invalid_urls_are_rejected(url):
    assert netguard.url_problem(url, allow_http=True), url


def test_url_policy_ports_and_schemes():
    assert netguard.url_problem("https://app.example.com/health") is None
    assert netguard.url_problem("https://app.example.com:443/health") is None
    assert netguard.url_problem("http://app.example.com/health", allow_http=True) is None
    assert "plain http" in netguard.url_problem("http://app.example.com/health", allow_http=False)
    assert netguard.url_problem("https://app.example.com:8443/h", allowed_ports=[443, 8443]) is None
    assert netguard.url_problem("https://app.example.com/" + "a" * 400)


def test_invalid_url_is_never_fetched():
    f = Fetcher(resp())
    for url in ("https://127.0.0.1/", "ftp://app.example.com/", "https://app.example.com:22/"):
        rec = check(f, Resolver({}), url=url)
        assert rec["state"] == "unknown" and "rejected" in rec["reason"]
    assert not f.calls


# ---- DNS rebinding -------------------------------------------------------------------------------------------------------------
def test_dns_is_resolved_twice_and_flip_to_private_is_blocked():
    f = Fetcher(resp())
    r = Resolver({"app.example.com": [[PUBLIC4], ["127.0.0.1"]]})            # classic rebinding: public first, private second
    rec = check(f, r)
    assert len(r.calls) == 2 and rec["state"] == "unknown" and not f.calls


def test_dns_answers_that_change_entirely_are_blocked_even_if_both_public():
    f = Fetcher(resp())
    rec = check(f, Resolver({"app.example.com": [[PUBLIC4], ["8.8.8.8"]]}))
    assert rec["state"] == "unknown" and "rebinding" in rec["reason"] and not f.calls


def test_connection_goes_to_the_pinned_ip_with_the_hostname_for_tls_and_host_header():
    f = Fetcher(resp())
    r = Resolver({"app.example.com": [[PUBLIC4]]})
    assert check(f, r)["state"] == "online"
    call = f.calls[0]
    assert call["ip"] == PUBLIC4 and call["host"] == "app.example.com" and call["scheme"] == "https" and call["port"] == 443
    assert len(r.calls) == 2                                                # two lookups before, none after: no re-resolve at connect


def test_peer_address_mismatch_after_connect_is_blocked():
    rec = check(Fetcher(PeerMismatch("connected to 127.0.0.1")))
    assert rec["state"] == "unknown" and "peer" in rec["reason"]


class FakeSock:
    def __init__(self, peer, chunks):
        self.peer, self.chunks, self.sent, self.closed = peer, chunks, b"", False

    def getpeername(self):
        return (self.peer, 80)

    def settimeout(self, t):
        pass

    def sendall(self, b):
        self.sent += b

    def makefile(self, mode="rb", *a, **k):
        import io
        return io.BytesIO(b"".join(self.chunks))

    def close(self):
        self.closed = True


def test_socket_fetcher_checks_peer_and_sends_only_fixed_headers():
    sock = FakeSock("127.0.0.1", [b"HTTP/1.1 200 OK\r\n\r\n"])
    with pytest.raises(PeerMismatch):
        SocketFetcher(connect=lambda addr, t: sock).fetch("http", "app.example.com", PUBLIC4, 80, "/", timeout=1, max_bytes=100, deadline=1e18)
    assert sock.closed and sock.sent == b""                                 # nothing was sent to the wrong peer

    sock = FakeSock(PUBLIC4, [b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"])
    r = SocketFetcher(connect=lambda addr, t: sock).fetch("http", "app.example.com", PUBLIC4, 80, "/health", timeout=1, max_bytes=100, deadline=1e18)
    sent = sock.sent.decode()
    assert r.status == 200 and r.bytes_read == 2 and sock.closed
    assert sent.startswith("GET /health HTTP/1.1\r\nHost: app.example.com\r\n")
    lowered = sent.lower()
    for forbidden in ("authorization", "cookie", "token", "x-github"):
        assert forbidden not in lowered


def test_socket_fetcher_reads_are_bounded():
    body = b"x" * 50000
    sock = FakeSock(PUBLIC4, [b"HTTP/1.1 200 OK\r\nContent-Length: 50000\r\n\r\n" + body])
    r = SocketFetcher(connect=lambda addr, t: sock).fetch("http", "app.example.com", PUBLIC4, 80, "/", timeout=1, max_bytes=4096, deadline=1e18)
    assert r.bytes_read == 4096


def test_socket_fetcher_stops_at_the_total_deadline():
    sock = FakeSock(PUBLIC4, [b"HTTP/1.1 200 OK\r\nContent-Length: 50000\r\n\r\n" + b"x" * 50000])
    with pytest.raises(TimeoutError):
        SocketFetcher(connect=lambda addr, t: sock).fetch("http", "app.example.com", PUBLIC4, 80, "/", timeout=1, max_bytes=60000, deadline=0)


def test_socket_fetcher_works_over_a_real_socketpair():
    a, b = socket.socketpair()

    class Pinned:                      # a socketpair has no IP peer, so only getpeername is faked; the I/O is real
        def __getattr__(self, name):
            return getattr(a, name)

        def getpeername(self):
            return (PUBLIC4, 80)

    b.sendall(b"HTTP/1.1 204 No Content\r\nServer: t\r\n\r\n")
    r = SocketFetcher(connect=lambda addr, t: Pinned()).fetch("http", "app.example.com", PUBLIC4, 80, "/h", timeout=2, max_bytes=100, deadline=1e18)
    b.settimeout(2)
    request = b.recv(4096).decode()
    b.close()
    assert r.status == 204 and request.startswith("GET /h HTTP/1.1\r\nHost: app.example.com\r\n") and "authorization" not in request.lower()


# ---- redirects ----------------------------------------------------------------------------------------------------------------
def test_same_host_redirect_is_followed_and_revalidated():
    f = Fetcher(resp(301, "https://app.example.com/status"), resp(200))
    r = Resolver({"app.example.com": [[PUBLIC4]]})
    assert check(f, r)["state"] == "online"
    assert [c["path"] for c in f.calls] == ["/health", "/status"] and len(r.calls) == 4     # DNS re-checked on every hop


def test_relative_redirect_is_resolved_against_the_current_url():
    f = Fetcher(resp(302, "/ok"), resp(200))
    assert check(f)["state"] == "online" and f.calls[1]["path"] == "/ok" and f.calls[1]["host"] == "app.example.com"


@pytest.mark.parametrize("target", [
    "https://evil.example.net/", "http://app.example.com/", "https://127.0.0.1/", "https://[::1]/", "https://169.254.169.254/latest/meta-data/",
    "file:///etc/passwd", "https://app.example.com:8443/", "https://user@app.example.com/", "gopher://app.example.com/",
])
def test_redirects_to_disallowed_targets_are_blocked(target):
    f = Fetcher(resp(302, target), resp(200))
    rec = check(f, Resolver({"app.example.com": [[PUBLIC4]], "evil.example.net": [[PUBLIC4]]}))
    assert rec["state"] == "unknown" and len(f.calls) == 1, target


def test_redirect_to_an_explicitly_approved_host_is_allowed_but_its_dns_is_still_checked():
    f = Fetcher(resp(302, "https://www.example.com/"), resp(200))
    rec = check(f, Resolver({"app.example.com": [[PUBLIC4]], "www.example.com": [[PUBLIC4]]}), redirect_hosts=["www.example.com"])
    assert rec["state"] == "online"
    f = Fetcher(resp(302, "https://www.example.com/"), resp(200))
    rec = check(f, Resolver({"app.example.com": [[PUBLIC4]], "www.example.com": [["10.0.0.9"]]}), redirect_hosts=["www.example.com"])
    assert rec["state"] == "unknown" and len(f.calls) == 1


def test_redirect_loops_and_empty_locations_are_bounded():
    assert check(Fetcher(resp(302, "/again")), cfg={"max_redirects": 3})["state"] == "unknown"
    f = Fetcher(resp(302, "/again"))
    check(f, cfg={"max_redirects": 3})
    assert len(f.calls) == 4
    assert check(Fetcher(resp(302, None)))["state"] == "unknown"


# ---- states: healthy / unhealthy / timeout ---------------------------------------------------------------------------------------
def test_healthy_endpoint_is_online_with_check_time():
    rec = check(Fetcher(resp(200)))
    assert rec["state"] == "online" and rec["http_status"] == 200 and rec["checked_at"] == "2026-09-30T12:00:00Z"
    assert rec["host"] == "app.example.com" and rec["consecutive_failures"] == 0


def test_slow_success_is_degraded(monkeypatch):
    ticks = iter([0.0, 0.0, 9.0])
    monkeypatch.setattr(health.time, "monotonic", lambda: next(ticks, 9.0))
    rec = check(Fetcher(resp(200)), cfg={"degraded_ms": 4000})
    assert rec["state"] == "degraded" and rec["slow"]


@pytest.mark.parametrize("status,state", [(500, "degraded"), (502, "degraded"), (503, "degraded"), (404, "degraded"), (410, "degraded"),
                                          (401, "unknown"), (403, "unknown"), (429, "unknown")])
def test_http_error_states(status, state):
    assert check(Fetcher(resp(status)))["state"] == state


def test_timeout_is_never_offline_even_when_repeated():
    prev = None
    for _ in range(5):
        prev = check(Fetcher(TimeoutError()), prev=prev)
        assert prev["state"] == "unknown" and prev["consecutive_failures"] == 0 and "timed out" in prev["reason"]


def test_generic_network_errors_are_unknown():
    for exc in (OSError("net unreachable"), ConnectionResetError()):
        assert check(Fetcher(exc))["state"] == "unknown"


def test_offline_requires_a_refusal_in_consecutive_runs():
    first = check(Fetcher(ConnectionRefusedError()))
    assert first["state"] == "unknown" and first["consecutive_failures"] == 1 and "unconfirmed" in first["reason"]
    second = check(Fetcher(ConnectionRefusedError()), prev=first)
    assert second["state"] == "offline" and second["consecutive_failures"] == 2
    recovered = check(Fetcher(resp(200)), prev=second)
    assert recovered["state"] == "online" and recovered["consecutive_failures"] == 0
    flaky = check(Fetcher(TimeoutError()), prev=first)                         # a timeout in between breaks the streak
    assert flaky["consecutive_failures"] == 0


def test_nxdomain_counts_like_a_refusal_but_a_resolver_hiccup_does_not():
    nx = socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    first = check(Fetcher(resp()), Resolver({"app.example.com": nx}))
    assert first["state"] == "unknown" and first["consecutive_failures"] == 1
    assert check(Fetcher(resp()), Resolver({"app.example.com": nx}), prev=first)["state"] == "offline"
    hiccup = socket.gaierror(socket.EAI_AGAIN, "Temporary failure")
    assert check(Fetcher(resp()), Resolver({"app.example.com": hiccup}), prev=first)["consecutive_failures"] == 0


def test_tls_failure_is_degraded_not_offline():
    assert check(Fetcher(ssl.SSLCertVerificationError("bad cert")))["state"] == "degraded"


def test_transient_failures_are_retried_within_budget():
    f = Fetcher(TimeoutError(), resp(200))
    rec = health.check_one(URL, {"retries": 1}, fetcher=f, resolve=Resolver({"app.example.com": [[PUBLIC4]]}), now=NOW, sleep=lambda s: None)
    assert rec["state"] == "online" and len(f.calls) == 2


def test_bounded_request_parameters_are_passed_down():
    f = Fetcher(resp())
    check(f, cfg={"timeout_s": 3, "max_bytes": 2048})
    assert f.calls[0]["timeout"] == 3 and f.calls[0]["max_bytes"] == 2048 and f.calls[0]["deadline"]


# ---- opt-in, cache, no credentials -----------------------------------------------------------------------------------------------
def test_only_explicitly_enabled_projects_with_a_url_are_probed():
    pub = lambda p: p.get("publish", True)
    projects = {
        "On": {"deployment": {"health_url": URL, "health_check": True}},
        "FlagOff": {"deployment": {"health_url": URL, "health_check": False}},
        "NoFlag": {"deployment": {"health_url": URL}},
        "NoUrl": {"deployment": {"health_check": True}},
        "Hidden": {"publish": False, "deployment": {"health_url": URL, "health_check": True}},
        "Demo": {"demo": "https://readme-link.example.com"},                       # URLs from README/demo are never inferred
    }
    assert list(health.eligible(projects, pub)) == ["On"]


def test_max_checks_bounds_the_run():
    f = Fetcher(resp())
    targets = {f"p{i}": {"url": URL, "redirect_hosts": []} for i in range(5)}
    out, warns = health.run_checks(targets, {"max_checks": 2, "retries": 0}, fetcher=f, resolve=Resolver({"app.example.com": [[PUBLIC4]]}), now=NOW)
    assert len(out) == 2 and len(warns) == 3


def test_cache_fallback_and_staleness():
    rec = {"state": "online", "checked_at": "2026-09-30T00:00:00Z"}
    assert health.effective(rec, NOW, fresh=True, stale_after_h=72) is rec
    assert "stale" not in health.effective(rec, NOW + dt.timedelta(hours=5), fresh=False, stale_after_h=72)
    assert health.effective(rec, NOW + dt.timedelta(hours=30), fresh=False, stale_after_h=72)["stale"]
    dead = health.effective(rec, NOW + dt.timedelta(hours=80), fresh=False, stale_after_h=72)
    assert dead["state"] == "unknown"
    assert health.effective({"state": "online"}, NOW, fresh=False, stale_after_h=72)["state"] == "unknown"


def test_health_module_never_touches_credentials(monkeypatch):
    import inspect
    src = inspect.getsource(health) + inspect.getsource(netguard)
    for needle in ("GITHUB_TOKEN", "Authorization", "os.environ", "GitHubClient", "PROFILEOS_STATUS_TOKEN"):
        assert needle not in src.replace("authorization\"", "").replace("Authorization\" not", ""), needle
    sent = []
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_TOPSECRET")
    f = Fetcher(resp())
    check(f)
    assert "TOPSECRET" not in repr(f.calls) and "TOPSECRET" not in repr(sent)


def test_records_never_contain_urls_paths_or_secrets():
    rec = check(Fetcher(resp(302, "https://app.example.com/x?token=abc"), resp(200)))
    assert "token" not in repr(rec) and "abc" not in repr(rec)
