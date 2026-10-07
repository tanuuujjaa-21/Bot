"""
ssrf_protection.py

NoobSync Knowledge Base AI — Week 3, Task 2 (Scraper Security Audit)
Owner: Akshada (Security/CRM/Docs)
Used by: Anushka's URL scraper (Week 3, Task 1)

WHAT THIS PROTECTS AGAINST
---------------------------
SSRF (Server-Side Request Forgery): a user submits a URL like
"http://192.168.1.1/admin" or "http://localhost:8000/secrets" instead of
a real external website. If the scraper blindly fetches whatever URL it's
given, it becomes a proxy an attacker can use to probe or reach OUR
internal network / internal services / cloud metadata endpoints — from
OUR server, using OUR server's network access.

This is a genuinely serious, well-known vulnerability class (it's on the
OWASP Top 10). Any "give me a URL and I'll fetch it for you" feature is a
classic SSRF target.

WHAT THIS BLOCKS
----------------
1. Private/internal IP ranges (RFC 1918): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
2. Loopback: 127.0.0.0/8, ::1
3. Link-local: 169.254.0.0/16 (this includes cloud metadata endpoints like
   AWS's 169.254.169.254 — a very common SSRF target used to steal cloud
   credentials)
4. "localhost" and other loopback hostnames
5. DNS rebinding: resolves the hostname and checks the ACTUAL IP it
   points to — not just the hostname string. A malicious domain can point
   its DNS record at 127.0.0.1, so checking the hostname alone isn't enough.
6. Non-http(s) schemes (file://, ftp://, gopher://, etc.) which have their
   own history of being used for SSRF-adjacent attacks.

HOW ANUSHKA PLUGS THIS IN
--------------------------
    from ssrf_protection import is_safe_url, SSRFValidationError

    for url in urls_to_crawl:
        try:
            is_safe_url(url)  # raises SSRFValidationError if unsafe
        except SSRFValidationError as e:
            print(f"Rejected unsafe URL: {url} ({e})")
            continue
        # ... proceed with robots_compliance.py checks, then fetch ...

This should run BEFORE robots_compliance.can_visit() — no point checking
robots.txt rules for a URL we're never going to fetch anyway.
"""

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFValidationError(Exception):
    """Raised when a URL fails SSRF safety checks."""
    pass


# Private, loopback, and link-local ranges to block.
# (ipaddress module's is_private / is_loopback / is_link_local properties
# cover IPv4 + IPv6 correctly, but we're explicit here for clarity in
# code review / the security audit doc.)
def _is_blocked_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private       # covers 10.x, 172.16-31.x, 192.168.x, and IPv6 equivalents
        or ip.is_loopback   # 127.x.x.x, ::1
        or ip.is_link_local # 169.254.x.x (cloud metadata endpoints), fe80::/10
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified  # 0.0.0.0
    )


def is_safe_url(url: str, allowed_schemes=("http", "https")) -> bool:
    """
    Validates a URL is safe to fetch (not pointing at internal
    infrastructure). Returns True if safe. Raises SSRFValidationError
    with a specific reason if unsafe.

    IMPORTANT: this resolves DNS to check the actual destination IP,
    protecting against DNS rebinding (a malicious hostname that resolves
    to an internal IP). Call this validation immediately before making
    the request — not earlier in a batch — since DNS can change between
    validation and the actual fetch in a determined attack (TOCTOU). For
    the strongest protection, pin the resolved IP and connect to that IP
    directly rather than re-resolving at request time.
    """
    parsed = urlparse(url)

    # 1. Scheme check
    if parsed.scheme not in allowed_schemes:
        raise SSRFValidationError(
            f"Scheme '{parsed.scheme}' not allowed (only {allowed_schemes})"
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL has no hostname")

    # 2. Obvious loopback hostnames (belt-and-suspenders alongside IP check)
    blocked_hostnames = {"localhost", "0.0.0.0"}
    if hostname.lower() in blocked_hostnames:
        raise SSRFValidationError(f"Hostname '{hostname}' is blocked")

    # 3. Resolve DNS and check the ACTUAL IP (defends against DNS rebinding)
    try:
        # getaddrinfo returns all resolved addresses (IPv4 + IPv6) — check ALL
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFValidationError(f"DNS resolution failed for '{hostname}': {e}")

    resolved_ips = {info[4][0] for info in addr_info}
    for ip_str in resolved_ips:
        if _is_blocked_ip(ip_str):
            raise SSRFValidationError(
                f"'{hostname}' resolves to blocked internal IP {ip_str}"
            )

    return True


# ==========================================================================
# DEMO / SELF-TEST
# ==========================================================================
if __name__ == "__main__":
    test_cases = [
        ("https://github.com/", True, "normal external site"),
        ("http://192.168.1.1/admin", False, "private IP directly in URL"),
        ("http://127.0.0.1:8000/secrets", False, "loopback IP"),
        ("http://localhost/", False, "localhost hostname"),
        ("http://169.254.169.254/latest/meta-data/", False, "cloud metadata endpoint (link-local)"),
        ("file:///etc/passwd", False, "non-http(s) scheme"),
        ("http://10.0.0.5/internal-api", False, "private class A range"),
    ]

    print("=" * 70)
    print("SSRF PROTECTION TEST")
    print("=" * 70)
    all_passed = True
    for url, expected_safe, description in test_cases:
        try:
            is_safe_url(url)
            actual_safe = True
            reason = "allowed"
        except SSRFValidationError as e:
            actual_safe = False
            reason = str(e)

        status = "PASS" if actual_safe == expected_safe else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"  [{status}] {description:40s} -> "
              f"{'SAFE' if actual_safe else 'BLOCKED'} ({reason})")

    print()
    print("ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED — review above")