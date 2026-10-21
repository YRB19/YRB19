"""Deployment health checks — explicit opt-in, SSRF-hardened, never conclusive on weak evidence.

States: online | offline | degraded | unknown | not_configured.
Only projects with `deployment.health_check: true` AND a `deployment.health_url` are probed; URLs are never taken from
README text. No credential of ours is ever sent: the request is built from a fixed header set in `SocketFetcher`.

Evidence rules ("a timeout is not proof of down"):
  * a timeout, resolver hiccup, blocked/odd redirect, 401/403/429 or any unclassified network error -> `unknown`;
  * 2xx -> `online` (`degraded` if slower than `degraded_ms`); other 4xx and 5xx -> `degraded` (it answered, badly);
  * `offline` needs an active refusal / NXDOMAIN observed in `offline_after` consecutive *runs* (default 2).
"""
import datetime as dt
import http.client
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from ..storage.cache import iso, parse_iso
from . import netguard
from .netguard import BlockedTarget

STATES = ("online", "offline", "degraded", "unknown", "not_configured")
SHOWN = ("online", "offline", "degraded")
DEFAULTS = {"timeout_s": 5, "retries": 1, "max_redirects": 3, "max_bytes": 65536, "degraded_ms": 4000,
            "offline_after": 2, "max_checks": 6, "total_timeout_s": 20, "allowed_ports": [80, 443], "allow_http": False,
            "stale_after_h": 72}
USER_AGENT = "profileos-health/1 (+https://github.com/YRB19/YRB19; read-only status probe)"


class PeerMismatch(Exception):
    pass


@dataclass
class Response:
    status: int
    location: str | None
    peer: str
    bytes_read: int


def _norm(addr: str) -> str:
    import ipaddress
    try:
        return str(ipaddress.ip_address(addr.split("%", 1)[0]))
    except ValueError:
        return addr


class SocketFetcher:
    """One GET to a *pinned IP*. TLS verifies the certificate against the real hostname (server_hostname), the HTTP Host
    header carries the hostname, and the connected peer must equal the pinned IP. Reads are bounded by bytes and time."""

    def __init__(self, connect=socket.create_connection, context=None):
        self._connect = connect
        self._ctx = context

    def fetch(self, scheme, host, ip, port, path, *, timeout, max_bytes, deadline) -> Response:
        sock = self._connect((ip, port), timeout)
        try:
            peer = _norm(sock.getpeername()[0])
            if peer != _norm(ip):
                raise PeerMismatch(f"connected to {peer}, expected {ip}")
            if scheme == "https":
                ctx = self._ctx or ssl.create_default_context()
                sock = ctx.wrap_socket(sock, server_hostname=host)
            sock.settimeout(timeout)
            default = 443 if scheme == "https" else 80
            host_header = host if port == default else f"{host}:{port}"
            req = (f"GET {path or '/'} HTTP/1.1\r\nHost: {host_header}\r\nUser-Agent: {USER_AGENT}\r\n"
                   "Accept: */*\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n")
            sock.sendall(req.encode("ascii"))
            resp = http.client.HTTPResponse(sock, method="GET")
            resp.begin()
            got = 0
            while got < max_bytes:
                if time.monotonic() > deadline:
                    raise TimeoutError("total time budget exceeded")
                chunk = resp.read(min(8192, max_bytes - got))
                if not chunk:
                    break
                got += len(chunk)
            return Response(resp.status, resp.getheader("Location"), peer, got)
        finally:
            try:
                sock.close()
            except OSError:
                pass


def settings(cfg: dict | None) -> dict:
    return {**DEFAULTS, **{k: v for k, v in (cfg or {}).items() if k in DEFAULTS}}


def _rec(state, now, host, *, status=None, reason=None, failures=0, slow=False):
    r = {"state": state, "host": host, "checked_at": iso(now), "consecutive_failures": failures, "source": "http-probe"}
    if status is not None:
        r["http_status"] = status
    if reason:
        r["reason"] = reason
    if slow:
        r["slow"] = True
    return r


def probe_once(url, s, *, fetcher, resolve, redirect_hosts, deadline):
    """Follow redirects manually, re-validating every hop. Returns (Response|None, outcome, detail, slow)."""
    cur, hops = url, 0
    origin = urlsplit(url)
    allowed = {origin.hostname.lower().rstrip(".")} | {h.lower() for h in redirect_hosts}
    t0 = time.monotonic()
    while True:
        if (why := netguard.url_problem(cur, allowed_ports=s["allowed_ports"], allow_http=s["allow_http"])):
            return None, "blocked", f"{'redirect target' if hops else 'URL'} rejected: {why}", False
        u = urlsplit(cur)
        host = u.hostname.lower().rstrip(".")
        if hops and host not in allowed:
            return None, "blocked", "redirected to a host that is not approved", False
        if hops and origin.scheme == "https" and u.scheme != "https":
            return None, "blocked", "redirect downgrades https to http", False
        port = u.port or (443 if u.scheme == "https" else 80)
        try:
            ips = netguard.resolve_public(host, port, resolve)
        except BlockedTarget as e:
            return None, "blocked", f"target not public: {e}", False
        except socket.gaierror as e:
            hard = e.errno == socket.EAI_NONAME
            return None, "dns_hard" if hard else "transient", f"DNS lookup failed ({e.strerror or e.errno})", False
        resp, last = None, None
        for ip in ips[:2]:
            try:
                resp = fetcher.fetch(u.scheme, host, ip, port, u.path or "/", timeout=s["timeout_s"], max_bytes=s["max_bytes"], deadline=deadline)
                break
            except PeerMismatch as e:
                return None, "blocked", f"peer address mismatch ({e})", False
            except ssl.SSLCertVerificationError:
                return None, "tls", "TLS certificate did not verify", False
            except (TimeoutError, socket.timeout):
                last = ("timeout", "request timed out")
            except ConnectionRefusedError:
                last = ("refused", "connection refused")
            except (OSError, http.client.HTTPException) as e:
                last = ("transient", f"network error ({type(e).__name__})")
        if resp is None:
            return None, last[0], last[1], False
        if 300 <= resp.status < 400 and resp.status != 304:
            hops += 1
            if hops > s["max_redirects"] or not resp.location:
                return None, "transient", "too many or empty redirects", False
            cur = urljoin(cur, resp.location)
            continue
        slow = (time.monotonic() - t0) * 1000 > s["degraded_ms"]
        return resp, "http", "", slow


def classify(resp, outcome, detail, slow, prev_failures, s, now, host) -> dict:
    if outcome == "http":
        st = resp.status
        if 200 <= st < 300:
            return _rec("degraded" if slow else "online", now, host, status=st, reason="slow response" if slow else None, slow=slow)
        if st in (401, 403, 429):
            return _rec("unknown", now, host, status=st, reason=f"probe was refused (HTTP {st}); not proof of an outage")
        return _rec("degraded", now, host, status=st, reason=f"HTTP {st} from the health URL")
    if outcome in ("refused", "dns_hard"):
        n = prev_failures + 1
        if n >= s["offline_after"]:
            return _rec("offline", now, host, reason=f"{detail}, seen in {n} consecutive runs", failures=n)
        return _rec("unknown", now, host, reason=f"{detail}; unconfirmed until it repeats", failures=n)
    if outcome == "tls":
        return _rec("degraded", now, host, reason=detail)
    # timeout / transient / blocked: never evidence of an outage
    return _rec("unknown", now, host, reason=detail)


def check_one(url, cfg, *, fetcher, resolve, now, prev=None, sleep=time.sleep, redirect_hosts=()) -> dict:
    s = settings(cfg)
    host = (urlsplit(url).hostname or "").lower()
    deadline = time.monotonic() + s["total_timeout_s"]
    prev_f = int((prev or {}).get("consecutive_failures", 0))
    resp = outcome = detail = slow = None
    for attempt in range(int(s["retries"]) + 1):
        resp, outcome, detail, slow = probe_once(url, s, fetcher=fetcher, resolve=resolve, redirect_hosts=redirect_hosts, deadline=deadline)
        transient = outcome in ("timeout", "transient") or (outcome == "http" and resp.status >= 500)
        if not transient or time.monotonic() > deadline:
            break
        sleep(min(0.5 * (attempt + 1), 2))
    return classify(resp, outcome, detail, slow, prev_f, s, now, host)


def eligible(projects: dict, publishable) -> dict:
    """slug -> {url, redirect_hosts}. Opt-in only: a flag AND a url, on a published project."""
    out = {}
    for slug, p in projects.items():
        d = p.get("deployment") or {}
        if d.get("health_check") is True and d.get("health_url") and publishable(p):
            out[slug] = {"url": d["health_url"], "redirect_hosts": list(d.get("redirect_hosts") or [])}
    return out


def run_checks(targets: dict, cfg, *, fetcher=None, resolve=netguard.system_resolve, now, prev=None, sleep=time.sleep):
    """Returns ({slug: record}, warnings). Targets beyond `max_checks` are skipped (they fall back to cache)."""
    s = settings(cfg)
    fetcher = fetcher or SocketFetcher()
    prev = prev or {}
    out, warnings = {}, []
    for i, (slug, t) in enumerate(sorted(targets.items())):
        if i >= s["max_checks"]:
            warnings.append(f"health: {slug}: skipped (max_checks={s['max_checks']})")
            continue
        out[slug] = check_one(t["url"], cfg, fetcher=fetcher, resolve=resolve, now=now, prev=prev.get(slug),
                              sleep=sleep, redirect_hosts=t["redirect_hosts"])
    return out, warnings


def effective(rec, now, *, fresh: bool, stale_after_h: float, label_after_h: float = 24):
    if not rec:
        return None
    if fresh:
        return rec
    try:
        age_h = (now - parse_iso(rec["checked_at"])).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return {**rec, "state": "unknown", "reason": "no check time", "stale": True}
    if age_h > stale_after_h:
        return {**rec, "state": "unknown", "reason": "cached health is stale", "stale": True}
    return {**rec, "stale": True} if age_h > label_after_h else rec   # young cache: shown as-is (no churn on a short outage)
