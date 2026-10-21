"""SSRF guard for deployment health checks: static URL policy + DNS-level address policy (IPv4 and IPv6).

Nothing here talks to the network except `resolve`, which is injectable. The policy is deliberately strict:
  * hostnames only (no IP literals, no userinfo, no query/fragment), http/https, ports from an allow-list;
  * EVERY address a name resolves to must be globally routable — one private answer rejects the whole name
    (split-horizon / "one good, one bad" answers are a classic bypass);
  * IPv6 forms that embed an IPv4 address (::ffff:a.b.c.d, 64:ff9b::/96 NAT64, 2002::/16 6to4, Teredo) are unwrapped
    and the embedded IPv4 must be public too.
"""
import ipaddress
import socket
from urllib.parse import urlsplit

DEFAULT_PORTS = (80, 443)
_BAD_SUFFIX = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet", ".localdomain", ".arpa")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_SIX_TO_FOUR = ipaddress.ip_network("2002::/16")
_TEREDO = ipaddress.ip_network("2001::/32")
_EXTRA_BLOCKED = [ipaddress.ip_network(n) for n in (
    "100.64.0.0/10",      # carrier-grade NAT
    "192.0.0.0/24", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24",   # IETF / documentation
    "198.18.0.0/15",      # benchmarking
    "2001:db8::/32",      # IPv6 documentation
    "64:ff9b:1::/48",     # local-use NAT64
    "fc00::/7", "fe80::/10", "ff00::/8",
)]


class BlockedTarget(Exception):
    """The target must not be contacted. `reason` is safe to log and to show to the owner."""


def ip_problem(addr: str) -> str | None:
    """None when `addr` is a public unicast address, else a short reason."""
    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return "not an IP address"
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = ip.ipv4_mapped
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is None and ip in _SIX_TO_FOUR:
            embedded = ipaddress.IPv4Address((int(ip) >> 80) & 0xFFFFFFFF)
        if embedded is None and ip in _TEREDO:
            embedded = ipaddress.IPv4Address(~int(ip) & 0xFFFFFFFF)       # client IPv4 is stored inverted
        if embedded is not None:
            return ip_problem(str(embedded)) and f"embeds a non-public IPv4 ({embedded})"
    if (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified or not ip.is_global or any(ip in n for n in _EXTRA_BLOCKED)):
        return "non-public address"
    return None


def url_problem(url: str, *, allowed_ports=DEFAULT_PORTS, allow_http: bool = True) -> str | None:
    """Static policy. Returns a reason or None. Does not resolve DNS."""
    if not isinstance(url, str) or not url or len(url) > 300 or any(c in url for c in "\r\n\t \\"):
        return "malformed URL"
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        return "malformed URL"
    if u.scheme not in ("https", "http"):
        return "scheme must be http or https"
    if u.scheme == "http" and not allow_http:
        return "plain http is not allowed (set health.allow_http to permit it)"
    if u.username or u.password or "@" in (u.netloc or ""):
        return "credentials in URL are not allowed"
    host = (u.hostname or "").lower().rstrip(".")
    if not host:
        return "no host"
    try:
        ipaddress.ip_address(host.strip("[]"))
        return "IP-address hosts are not allowed; use a DNS name"
    except ValueError:
        pass
    if host == "localhost" or host.endswith(_BAD_SUFFIX) or "." not in host:
        return "host is not public"
    tld = host.rsplit(".", 1)[-1]
    if tld.isdigit() or (tld.startswith("0x") and all(c in "0123456789abcdefx" for c in tld)):
        return "numeric host names (e.g. 0x7f.1, 127.1) are not allowed"      # inet_aton-style IPv4 spellings
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        return "non-ASCII hostnames must be given in punycode"
    port = port or (443 if u.scheme == "https" else 80)
    if port not in set(allowed_ports):
        return f"port {port} is not in the allowed list {sorted(set(allowed_ports))}"
    if u.query or u.fragment:
        return "query strings and fragments are not allowed (may carry secrets)"
    return None


def system_resolve(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def check_resolution(addrs: list[str]) -> None:
    if not addrs:
        raise BlockedTarget("name did not resolve")
    for a in addrs:
        if (why := ip_problem(a)):
            raise BlockedTarget(f"resolves to {a}: {why}")


def resolve_public(host: str, port: int, resolve=system_resolve) -> list[str]:
    """Resolve TWICE and require both answers to be entirely public and mutually consistent, then return the pinned
    addresses. Callers connect to these addresses directly (never by name again), so a later flip in DNS cannot
    redirect the request: that, plus the post-connect peer check, is the DNS-rebinding defence."""
    first = sorted(set(resolve(host, port)))
    check_resolution(first)
    second = sorted(set(resolve(host, port)))
    check_resolution(second)
    if not set(second) & set(first):
        raise BlockedTarget("DNS answers changed between lookups (possible rebinding)")
    return [a for a in first if a in second] or first
